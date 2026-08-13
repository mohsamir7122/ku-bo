from __future__ import annotations

from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from kubo import ca_enrichment_import
from kubo import official_foundation_import
from kubo import status_corporate_import
from kubo import user_price_export


class _AdmissionToken:
    def __init__(self, events: list[tuple[object, ...]]) -> None:
        self._events = events

    def revalidate_before_commit(self) -> None:
        self._events.append(("revalidate",))

    def materialize_receipt(self, staging_root: Path) -> None:
        self._events.append(("materialize", staging_root))

    def materialize_lineage(self, staging_root: Path) -> None:
        self._events.append(("lineage", staging_root))


class ImporterAtomicAdmissionTests(unittest.TestCase):
    def _assert_wrapper(
        self,
        *,
        module: object,
        public_name: str,
        private_name: str,
        boundary_id: str,
        arguments: dict[str, object],
        boundary_input_roles: tuple[str, ...],
    ) -> None:
        events: list[tuple[object, ...]] = []
        request = SimpleNamespace(decision_at="2026-08-13T10:00:00+03:00")
        target = Path(arguments["output_root"])  # type: ignore[arg-type]
        expected_target = Path(target.absolute())
        staging = target.parent / f".{target.name}.staging-test"
        token = _AdmissionToken(events)
        expected_inputs = {
            role: arguments[role] for role in boundary_input_roles
        }

        def admit(
            actual_request: object,
            *,
            boundary_id: str,
            output_root: Path,
            boundary_inputs: dict[str, Path],
            operation_binding: dict[str, object],
        ) -> _AdmissionToken:
            self.assertIs(actual_request, request)
            self.assertFalse(target.exists())
            self.assertEqual(boundary_inputs, expected_inputs)
            self.assertEqual(
                operation_binding["decision_at"],
                request.decision_at,
            )
            events.append(("admit", boundary_id, output_root, boundary_inputs))
            return token

        def unchecked(**actual: object) -> dict[str, str]:
            self.assertFalse(target.exists())
            events.append(("worker", actual))
            return {"output_root": str(actual["logical_output_root"])}

        def atomic(
            output_root: Path,
            worker: object,
            *,
            before_commit: object,
        ) -> dict[str, str]:
            self.assertEqual(
                events,
                [("admit", boundary_id, expected_target, expected_inputs)],
            )
            self.assertEqual(output_root, expected_target)
            events.append(("staging", staging))
            result = worker(staging)  # type: ignore[operator]
            before_commit(staging)  # type: ignore[operator]
            events.append(("commit",))
            return result

        with (
            patch.object(module, "admit_boundary", side_effect=admit),
            patch.object(module, private_name, side_effect=unchecked),
            patch.object(module, "run_atomic_output", side_effect=atomic),
        ):
            result = getattr(module, public_name)(
                **arguments,
                admission_request=request,
            )

        self.assertEqual(result, {"output_root": str(expected_target)})
        self.assertEqual(
            events[0],
            ("admit", boundary_id, expected_target, expected_inputs),
        )
        self.assertEqual(events[1], ("staging", staging))
        worker_arguments = events[2][1]
        self.assertEqual(worker_arguments["output_root"], staging)
        self.assertEqual(worker_arguments["logical_output_root"], expected_target)
        self.assertEqual(
            events[3:],
            [
                ("materialize", staging),
                ("lineage", staging),
                ("revalidate",),
                ("commit",),
            ],
        )

    def test_user_price_export_wrapper_admits_stages_and_revalidates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._assert_wrapper(
                module=user_price_export,
                public_name="import_investing_user_exports",
                private_name="_import_investing_user_exports_unchecked",
                boundary_id="import_user_price_exports",
                boundary_input_roles=("config_dir", "input_dir"),
                arguments={
                    "config_dir": root / "config",
                    "input_dir": root / "input",
                    "output_root": root / "output",
                    "observed_at": "2026-08-13T09:00:00+03:00",
                    "decision_at": "2026-08-13T10:00:00+03:00",
                },
            )

    def test_official_foundation_wrapper_admits_stages_and_revalidates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._assert_wrapper(
                module=official_foundation_import,
                public_name="import_official_foundation",
                private_name="_import_official_foundation_unchecked",
                boundary_id="import_official_foundation",
                boundary_input_roles=("config_dir", "workspace"),
                arguments={
                    "config_dir": root / "config",
                    "workspace": root / "workspace",
                    "output_root": root / "output",
                },
            )

    def test_status_corporate_wrapper_admits_stages_and_revalidates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._assert_wrapper(
                module=status_corporate_import,
                public_name="import_status_corporate",
                private_name="_import_status_corporate_unchecked",
                boundary_id="import_status_corporate",
                boundary_input_roles=("official_foundation_root", "workspace"),
                arguments={
                    "config_dir": root / "config",
                    "official_foundation_root": root / "official",
                    "workspace": root / "workspace",
                    "output_root": root / "output",
                },
            )

    def test_ca_enrichment_wrapper_admits_stages_and_revalidates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._assert_wrapper(
                module=ca_enrichment_import,
                public_name="import_ca_enrichment",
                private_name="_import_ca_enrichment_unchecked",
                boundary_id="import_ca_enrichment",
                boundary_input_roles=("status_corporate_root", "workspace"),
                arguments={
                    "status_corporate_root": root / "status",
                    "workspace": root / "workspace",
                    "output_root": root / "output",
                },
            )


if __name__ == "__main__":
    unittest.main()
