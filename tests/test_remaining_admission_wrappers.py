from __future__ import annotations

from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch


class RemainingAdmissionWrapperTests(unittest.TestCase):
    def _exercise(
        self,
        *,
        module_name: str,
        public_name: str,
        unchecked_name: str,
        boundary_id: str,
        public_kwargs: dict[str, object],
        unchecked_kwargs: dict[str, object],
        boundary_inputs: dict[str, Path],
        has_logical_output: bool,
        admit_patch_target: str | None = None,
    ) -> None:
        module = __import__(module_name, fromlist=[public_name])
        public = getattr(module, public_name)
        events: list[object] = []
        request = Mock(name="admission_request")
        request.decision_at = "2026-08-13T10:00:00+03:00"
        token = Mock(name="admission_token")
        token.revalidate_before_commit.side_effect = lambda: events.append(
            "revalidate"
        )
        token.materialize_receipt.side_effect = lambda staging: events.append(
            ("materialize", staging)
        )
        token.materialize_lineage.side_effect = lambda staging: events.append(
            ("lineage", token, staging)
        )
        report = {"status": "WRAPPER_TEST"}

        def admit_side_effect(actual_request, **kwargs):
            events.append(("admit", actual_request, kwargs))
            return token

        def unchecked_side_effect(**kwargs):
            events.append(("unchecked", kwargs))
            return report

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "final-output"
            staging = target.parent / ".final-output.staging-wrapper-test"

            def atomic_side_effect(actual_target, worker, before_commit=None):
                events.append(("atomic", Path(actual_target)))
                staging.mkdir()
                value = worker(staging)
                events.append("worker-complete")
                self.assertIsNotNone(before_commit)
                before_commit(staging)
                events.append("commit")
                return value

            with ExitStack() as stack:
                admit = stack.enter_context(
                    patch(
                        admit_patch_target or f"{module_name}.admit_boundary",
                        side_effect=admit_side_effect,
                    )
                )
                atomic = stack.enter_context(
                    patch(f"{module_name}.run_atomic_output", side_effect=atomic_side_effect)
                )
                unchecked = stack.enter_context(
                    patch(
                        f"{module_name}.{unchecked_name}",
                        side_effect=unchecked_side_effect,
                    )
                )
                final_lineages = None
                if boundary_id == "build_data_foundation_packet":
                    final_lineages = stack.enter_context(
                        patch(
                            "kubo.tri_security_lineage.verify_final_predecessor_lineages",
                            return_value=(),
                        )
                    )
                result = public(
                    **public_kwargs,
                    output_root=target,
                    admission_request=request,
                )

            self.assertIs(result, report)
            admit.assert_called_once()
            atomic.assert_called_once()
            unchecked.assert_called_once()
            token.revalidate_before_commit.assert_called_once_with()
            token.materialize_receipt.assert_called_once_with(staging)
            token.materialize_lineage.assert_called_once_with(staging)
            if final_lineages is not None:
                final_lineages.assert_called_once()
            self.assertEqual(events[0][0], "admit")
            self.assertEqual(events[1], ("atomic", target.resolve()))
            self.assertEqual(events[2][0], "unchecked")
            self.assertEqual(
                events[3:],
                [
                    ("materialize", staging),
                    ("lineage", token, staging),
                    "worker-complete",
                    "revalidate",
                    "commit",
                ],
            )

            admitted = events[0][2]
            self.assertEqual(admitted["boundary_id"], boundary_id)
            self.assertEqual(admitted["output_root"], target.resolve())
            self.assertEqual(admitted["boundary_inputs"], boundary_inputs)
            self.assertEqual(
                admitted["operation_binding"]["decision_at"],
                request.decision_at,
            )

            actual_unchecked = events[2][1]
            self.assertEqual(actual_unchecked["output_root"], staging)
            for key, expected in unchecked_kwargs.items():
                self.assertEqual(actual_unchecked[key], expected)
            if has_logical_output:
                self.assertEqual(
                    actual_unchecked["logical_output_root"],
                    target.resolve(),
                )
            else:
                self.assertNotIn("logical_output_root", actual_unchecked)

    def test_status_history_admit_stages_then_revalidates(self) -> None:
        self._exercise(
            module_name="kubo.status_history_import",
            public_name="import_status_history",
            unchecked_name="_import_status_history_unchecked",
            boundary_id="import_status_history",
            public_kwargs={
                "status_corporate_root": Path("status-corporate"),
                "workspace": Path("history-workspace"),
            },
            unchecked_kwargs={
                "status_corporate_root": Path("status-corporate"),
                "workspace": Path("history-workspace"),
            },
            boundary_inputs={
                "status_corporate_root": Path("status-corporate"),
                "workspace": Path("history-workspace"),
            },
            has_logical_output=True,
        )

    def test_benchmark_admit_stages_then_revalidates(self) -> None:
        self._exercise(
            module_name="kubo.benchmark_import",
            public_name="import_benchmark_history",
            unchecked_name="_import_benchmark_history_unchecked",
            boundary_id="import_benchmark_history",
            public_kwargs={
                "config_dir": Path("config"),
                "official_foundation_root": Path("official"),
                "workspace": Path("benchmark-workspace"),
                "imported_at": "2026-08-13T08:00:00+03:00",
            },
            unchecked_kwargs={
                "config_dir": Path("config"),
                "official_foundation_root": Path("official"),
                "workspace": Path("benchmark-workspace"),
                "imported_at": "2026-08-13T08:00:00+03:00",
            },
            boundary_inputs={
                "config_dir": Path("config"),
                "official_foundation_root": Path("official"),
                "workspace": Path("benchmark-workspace"),
            },
            has_logical_output=True,
        )

    def test_official_eod_admit_stages_then_revalidates(self) -> None:
        registry = Mock(name="runtime_trust_registry")
        registry.registry_id = "runtime-registry-v1"
        registry.issued_at = datetime(2026, 8, 12, tzinfo=timezone.utc)
        registry.expires_at = datetime(2026, 8, 14, tzinfo=timezone.utc)
        registry.entries = ()
        registry.authenticated_key_id = "runtime-key-v1"
        registry.content_sha256 = "a" * 64
        self._exercise(
            module_name="kubo.official_eod_import",
            public_name="import_official_daily_eod",
            unchecked_name="_import_official_daily_eod_unchecked",
            boundary_id="import_official_eod",
            public_kwargs={
                "workspace_root": Path("eod-workspace"),
                "official_foundation_root": Path("official"),
                "status_history_root": Path("status-history"),
                "run_id": "run-1",
                "imported_at": "2026-08-13T08:00:00+03:00",
                "runtime_trust_registry": registry,
            },
            unchecked_kwargs={
                "workspace_root": Path("eod-workspace"),
                "official_foundation_root": Path("official"),
                "status_history_root": Path("status-history"),
                "run_id": "run-1",
                "imported_at": "2026-08-13T08:00:00+03:00",
                "runtime_trust_registry": registry,
            },
            boundary_inputs={
                "workspace_root": Path("eod-workspace"),
                "official_foundation_root": Path("official"),
                "status_history_root": Path("status-history"),
            },
            has_logical_output=True,
        )

    def test_final_reconciliation_admit_stages_then_revalidates(self) -> None:
        inputs = {
            "official_foundation_root": Path("official"),
            "status_history_root": Path("status-history"),
            "ca_enrichment_root": Path("ca-enrichment"),
            "research_price_history_root": Path("research-prices"),
            "benchmark_root": Path("benchmark"),
            "official_eod_root": Path("official-eod"),
            "project_root": Path("project"),
            "outcome_session_policy_path": Path("policy.json"),
        }
        self._exercise(
            module_name="kubo.data_foundation_reconciliation",
            public_name="build_data_foundation_packet",
            unchecked_name="_build_data_foundation_packet_unchecked",
            boundary_id="build_data_foundation_packet",
            public_kwargs=inputs,
            unchecked_kwargs=inputs,
            boundary_inputs=inputs,
            has_logical_output=False,
            admit_patch_target="kubo.tri_security_admission.admit_boundary",
        )


if __name__ == "__main__":
    unittest.main()
