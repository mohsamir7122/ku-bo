from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover
    Draft202012Validator = None

from kubo.codex_live_bootstrap import EXPECTED_PRODUCTS, EXPECTED_STAGES
from kubo.hashing import hash_json
import kubo.live_dry_run as live_module
from kubo.live_dry_run import (
    LiveDryRunError,
    LiveDryRunLockError,
    run_daily_dry_run,
    validate_live_dry_run,
)
from kubo.recovery import acquire_recovery_lease, load_recovery_policy
from kubo.source_access_executor import PROBE_PURPOSE, PROBE_VERSION
from tests.helpers import synthetic_pack


ROOT = Path(__file__).resolve().parents[1]
_REAL_CANONICAL_VALIDATOR = live_module._canonical_validate_input


def _canonical_access_probe(root: Path) -> Path:
    payload = {
        "schema_version": "3.1-access-probe",
        "probe_id": "",
        "probe_version": PROBE_VERSION,
        "observed_at": "2026-08-24T07:59:00+03:00",
        "expires_at": "2026-08-25T07:59:00+03:00",
        "purpose": PROBE_PURPOSE,
        "sources": [
            {
                "source_id": "boursa_current",
                "state": "BLOCKED",
                "tested_url": "https://www.boursakuwait.com.kw/",
                "final_url": "https://www.boursakuwait.com.kw/",
                "attempted_at": "2026-08-24T07:58:00+03:00",
                "http_status": 503,
                "observation": "Access unavailable; this receipt is not collection evidence.",
                "data_quality_flags": ["SOURCE_ACCESS_BLOCKED"],
                "artifact": None,
            }
        ],
    }
    payload["probe_id"] = "public-access-probe-" + hash_json(payload)[:24]
    path = root / "access-probe.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _freeze(product_id: str, horizon: int) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "freeze_id": f"freeze-2026-08-23-{product_id}",
        "status": "APPROVED_CHAMPION",
        "product_id": product_id,
        "horizon_sessions": horizon,
        "model_version": "champion-v1",
        "policy_version": "policy-v1",
        "source_session_date": "2026-08-23",
        "effective_from_session_date": "2026-08-24",
        "approved_at": "2026-08-23T16:00:00+03:00",
        "artifacts": {
            "code_sha256": "1" * 64,
            "model_sha256": "2" * 64,
            "feature_policy_sha256": "3" * 64,
            "training_manifest_sha256": "4" * 64,
        },
        "approval": {
            "approved_by_role": "AUTHORIZED_REVIEWER",
            "decision_id": "KU-BO-FREEZE-001",
        },
        "outcomes": {
            "available_through": "2026-08-23T14:00:00+03:00",
            "same_session_outcomes_included": False,
        },
        "claim_boundaries": {
            "previous_approved_freeze_only": True,
            "same_day_challenger_used": False,
            "live_or_accuracy_claim_allowed": False,
            "buy_recommendation_claim_allowed": False,
            "automatic_promotion_allowed": False,
        },
    }


class LiveDryRunTests(unittest.TestCase):
    def _controlled_validator(self, kind: str, path: Path, **kwargs):
        if kind == "champion_freeze":
            return _REAL_CANONICAL_VALIDATOR(kind, path, **kwargs)
        return live_module._validation_record(
            path,
            validator_id=live_module.VALIDATOR_IDS[kind],
            object_id=f"controlled-{kind}",
            errors=[],
            facts={"controlled_orchestration_test_double": True},
            authorized=True,
        )

    def _run_controlled(self, **kwargs):
        with patch(
            "kubo.live_dry_run._canonical_validate_input",
            side_effect=self._controlled_validator,
        ):
            return run_daily_dry_run(project_root=ROOT, **kwargs)

    def _runtime(self, temporary: str):
        root = Path(temporary)
        inputs = root / "inputs"
        inputs.mkdir()
        paths = {}
        for name in ("probe", "raw", "normalized", "factor"):
            path = inputs / f"{name}.json"
            path.write_text(json.dumps({"kind": name}), encoding="utf-8")
            paths[name] = path.relative_to(root)
        freezes = {}
        for row in EXPECTED_PRODUCTS:
            path = inputs / f"freeze-{row['product_id']}.json"
            path.write_text(
                json.dumps(_freeze(row["product_id"], row["horizon_sessions"])),
                encoding="utf-8",
            )
            freezes[row["product_id"]] = path.relative_to(root)
        return root, paths, freezes

    def _complete(self, root: Path, paths, freezes, *, run_id="dry-run-001"):
        return self._run_controlled(
            private_runtime_root=root,
            output_root="runs",
            run_id=run_id,
            decision_session_date="2026-08-24",
            source_probe_receipts=[paths["probe"]],
            raw_evidence_manifest=paths["raw"],
            normalized_snapshot=paths["normalized"],
            factor_snapshot=paths["factor"],
            champion_freezes=freezes,
            recorded_at="2026-08-24T08:00:00+03:00",
        )

    def test_no_input_run_blocks_without_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = self._run_controlled(
                private_runtime_root=root,
                output_root="runs",
                run_id="dry-run-empty",
                decision_session_date="2026-08-24",
                recorded_at="2026-08-24T08:00:00+03:00",
            )
            self.assertEqual(report["status"], "DRY_RUN_BLOCKED")
            self.assertEqual(report["blocked_stage"], EXPECTED_STAGES[1])
            self.assertEqual(report["candidate_count"], 0)
            self.assertFalse((root / "runs/dry-run-empty/sealed_research_output.json").exists())

    def test_complete_contract_run_seals_abstain_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, paths, freezes = self._runtime(temporary)
            report = self._complete(root, paths, freezes)
            self.assertEqual(report["status"], "DRY_RUN_COMPLETE_NO_RECOMMENDATION")
            sealed = json.loads(
                (root / "runs/dry-run-001/sealed_research_output.json").read_text(encoding="utf-8")
            )
            self.assertTrue(all(row["decision"] == "ABSTAIN" for row in sealed["products"]))
            self.assertTrue(all(row["candidates"] == [] for row in sealed["products"]))

    def test_exact_ten_stage_order_is_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, paths, freezes = self._runtime(temporary)
            self._complete(root, paths, freezes)
            receipts = root / "runs/dry-run-001/receipts"
            stages = [
                json.loads(path.read_text(encoding="utf-8"))["stage"]
                for path in sorted(receipts.glob("*.json"))
            ]
            self.assertEqual(stages, EXPECTED_STAGES)

    def test_training_and_change_proposal_are_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, paths, freezes = self._runtime(temporary)
            self._complete(root, paths, freezes)
            receipts = root / "runs/dry-run-001/receipts"
            ninth = json.loads((receipts / f"09_{EXPECTED_STAGES[8]}.json").read_text(encoding="utf-8"))
            tenth = json.loads((receipts / f"10_{EXPECTED_STAGES[9]}.json").read_text(encoding="utf-8"))
            self.assertEqual(ninth["status"], "SKIPPED")
            self.assertEqual(tenth["status"], "SKIPPED")

    def test_missing_raw_manifest_blocks_stage_three(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, paths, _ = self._runtime(temporary)
            report = self._run_controlled(
                private_runtime_root=root,
                output_root="runs",
                run_id="dry-run-no-raw",
                decision_session_date="2026-08-24",
                source_probe_receipts=[paths["probe"]],
            )
            self.assertEqual(report["blocked_stage"], EXPECTED_STAGES[2])

    def test_missing_normalized_snapshot_blocks_stage_four(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, paths, _ = self._runtime(temporary)
            report = self._run_controlled(
                private_runtime_root=root,
                output_root="runs",
                run_id="dry-run-no-normalized",
                decision_session_date="2026-08-24",
                source_probe_receipts=[paths["probe"]],
                raw_evidence_manifest=paths["raw"],
            )
            self.assertEqual(report["blocked_stage"], EXPECTED_STAGES[3])

    def test_missing_factor_snapshot_blocks_stage_five(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, paths, _ = self._runtime(temporary)
            report = self._run_controlled(
                private_runtime_root=root,
                output_root="runs",
                run_id="dry-run-no-factor",
                decision_session_date="2026-08-24",
                source_probe_receipts=[paths["probe"]],
                raw_evidence_manifest=paths["raw"],
                normalized_snapshot=paths["normalized"],
            )
            self.assertEqual(report["blocked_stage"], EXPECTED_STAGES[4])

    def test_missing_freeze_set_blocks_champion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, paths, _ = self._runtime(temporary)
            report = self._run_controlled(
                private_runtime_root=root,
                output_root="runs",
                run_id="dry-run-no-freeze",
                decision_session_date="2026-08-24",
                source_probe_receipts=[paths["probe"]],
                raw_evidence_manifest=paths["raw"],
                normalized_snapshot=paths["normalized"],
                factor_snapshot=paths["factor"],
            )
            self.assertEqual(report["blocked_stage"], EXPECTED_STAGES[5])

    def test_same_day_freeze_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, paths, freezes = self._runtime(temporary)
            target = root / freezes[EXPECTED_PRODUCTS[0]["product_id"]]
            payload = json.loads(target.read_text(encoding="utf-8"))
            payload["approved_at"] = "2026-08-24T07:00:00+03:00"
            target.write_text(json.dumps(payload), encoding="utf-8")
            report = self._complete(root, paths, freezes)
            self.assertEqual(report["blocked_stage"], EXPECTED_STAGES[5])
            self.assertFalse((root / "runs/dry-run-001/sealed_research_output.json").exists())

    def test_challenger_freeze_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, paths, freezes = self._runtime(temporary)
            target = root / freezes[EXPECTED_PRODUCTS[0]["product_id"]]
            payload = json.loads(target.read_text(encoding="utf-8"))
            payload["status"] = "CHALLENGER"
            target.write_text(json.dumps(payload), encoding="utf-8")
            report = self._complete(root, paths, freezes)
            self.assertEqual(report["blocked_stage"], EXPECTED_STAGES[5])

    def test_product_horizon_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, paths, freezes = self._runtime(temporary)
            target = root / freezes[EXPECTED_PRODUCTS[0]["product_id"]]
            payload = json.loads(target.read_text(encoding="utf-8"))
            payload["horizon_sessions"] = 5
            target.write_text(json.dumps(payload), encoding="utf-8")
            report = self._complete(root, paths, freezes)
            self.assertEqual(report["blocked_stage"], EXPECTED_STAGES[5])

    def test_same_input_resume_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, paths, freezes = self._runtime(temporary)
            first = self._complete(root, paths, freezes)
            second = self._complete(root, paths, freezes)
            self.assertEqual(first, second)

    def test_replay_with_changed_input_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, paths, freezes = self._runtime(temporary)
            self._complete(root, paths, freezes)
            (root / paths["factor"]).write_text('{"kind":"changed"}', encoding="utf-8")
            with self.assertRaises(LiveDryRunError):
                self._complete(root, paths, freezes)

    def test_lock_conflict_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            lease_root = root / "runs/.leases"
            lease_root.mkdir(parents=True)
            policy, _ = load_recovery_policy(ROOT)
            acquire_recovery_lease(
                lease_root,
                fingerprint=live_module._dry_run_lease_fingerprint("dry-run-lock"),
                run_id="dry-run-lock",
                owner="other-owner",
                process_identity="github:other-run:job",
                now=datetime.now(timezone.utc),
                policy=policy,
            )
            with self.assertRaises(LiveDryRunLockError):
                run_daily_dry_run(
                    project_root=ROOT,
                    private_runtime_root=root,
                    output_root="runs",
                    run_id="dry-run-lock",
                    decision_session_date="2026-08-24",
                )

    def test_lock_is_released(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_daily_dry_run(
                project_root=ROOT,
                private_runtime_root=root,
                output_root="runs",
                run_id="dry-run-release",
                decision_session_date="2026-08-24",
            )
            self.assertEqual(list((root / "runs/.leases").glob("*.lease.json")), [])

    def test_expired_lease_requires_active_run_probe_before_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            lease_root = root / "runs/.leases"
            lease_root.mkdir(parents=True)
            policy, _ = load_recovery_policy(ROOT)
            fingerprint = live_module._dry_run_lease_fingerprint("dry-run-stale")
            acquire_recovery_lease(
                lease_root,
                fingerprint=fingerprint,
                run_id="dry-run-stale",
                owner="stale-owner",
                process_identity="github:stale-run:job",
                now=datetime.now(timezone.utc) - timedelta(minutes=16),
                policy=policy,
            )
            with self.assertRaises(LiveDryRunLockError):
                run_daily_dry_run(
                    project_root=ROOT,
                    private_runtime_root=root,
                    output_root="runs",
                    run_id="dry-run-stale",
                    decision_session_date="2026-08-24",
                )
            report = run_daily_dry_run(
                project_root=ROOT,
                private_runtime_root=root,
                output_root="runs",
                run_id="dry-run-stale",
                decision_session_date="2026-08-24",
                active_run_probe=lambda _: False,
            )
            self.assertEqual(report["status"], "DRY_RUN_BLOCKED")

    def test_canonical_access_receipt_passes_only_access_stage(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            probe = _canonical_access_probe(root)
            report = run_daily_dry_run(
                project_root=ROOT,
                private_runtime_root=root,
                output_root="runs",
                run_id="dry-run-canonical-probe",
                decision_session_date="2026-08-24",
                source_probe_receipts=[probe.relative_to(root)],
                recorded_at="2026-08-24T08:00:00+03:00",
            )
            self.assertEqual(report["blocked_stage"], EXPECTED_STAGES[2])
            contract = json.loads(
                (root / "runs/dry-run-canonical-probe/run_contract.json").read_text()
            )
            validation = contract["input_validations"]["source_probe"][0]
            self.assertEqual(validation["validator_status"], "PASS")
            self.assertFalse(
                validation["validator_result"]["facts"]["access_receipt_is_collection"]
            )

    def test_generic_and_fixture_inputs_are_rejected_by_canonical_validator(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, paths, freezes = self._runtime(temporary)
            report = run_daily_dry_run(
                project_root=ROOT,
                private_runtime_root=root,
                output_root="runs",
                run_id="dry-run-generic-inputs",
                decision_session_date="2026-08-24",
                source_probe_receipts=[paths["probe"]],
                raw_evidence_manifest=paths["raw"],
                normalized_snapshot=paths["normalized"],
                factor_snapshot=paths["factor"],
                champion_freezes=freezes,
                recorded_at="2026-08-24T08:00:00+03:00",
            )
            self.assertEqual(report["blocked_stage"], EXPECTED_STAGES[1])
            contract = json.loads(
                (root / "runs/dry-run-generic-inputs/run_contract.json").read_text()
            )
            self.assertEqual(
                contract["input_validations"]["source_probe"][0]["authorization_status"],
                "REJECTED_INPUT",
            )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = root / "fixtures"
            fixture.mkdir()
            probe = _canonical_access_probe(fixture)
            report = run_daily_dry_run(
                project_root=ROOT,
                private_runtime_root=root,
                output_root="runs",
                run_id="dry-run-fixture-path",
                decision_session_date="2026-08-24",
                source_probe_receipts=[probe.relative_to(root)],
                recorded_at="2026-08-24T08:00:00+03:00",
            )
            self.assertEqual(report["blocked_stage"], EXPECTED_STAGES[1])

    def test_synthetic_pack_is_rejected_before_raw_stage_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            probe = _canonical_access_probe(root)
            pack = synthetic_pack(root / "pack")
            report = run_daily_dry_run(
                project_root=ROOT,
                private_runtime_root=root,
                output_root="runs",
                run_id="dry-run-synthetic-pack",
                decision_session_date="2026-08-24",
                source_probe_receipts=[probe.relative_to(root)],
                raw_evidence_manifest=(pack / "manifests/file_manifest.json").relative_to(root),
                recorded_at="2026-08-24T08:00:00+03:00",
            )
            self.assertEqual(report["blocked_stage"], EXPECTED_STAGES[2])
            contract = json.loads(
                (root / "runs/dry-run-synthetic-pack/run_contract.json").read_text()
            )
            self.assertEqual(
                contract["input_validations"]["raw_evidence_manifest"]["validator_status"],
                "BLOCKED",
            )

    def test_receipt_binds_artifact_and_validator_report_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, paths, freezes = self._runtime(temporary)
            self._complete(root, paths, freezes, run_id="dry-run-validator-binding")
            run_root = root / "runs/dry-run-validator-binding"
            contract = json.loads((run_root / "run_contract.json").read_text())
            validation = contract["input_validations"]["source_probe"][0]
            receipt = json.loads(
                (
                    run_root
                    / "receipts"
                    / f"02_{EXPECTED_STAGES[1]}.json"
                ).read_text()
            )
            self.assertEqual(
                set(receipt["input_sha256"]),
                {
                    validation["artifact_sha256"],
                    validation["validator_report_sha256"],
                },
            )
            contract["input_validations"]["source_probe"][0][
                "validator_report_sha256"
            ] = "f" * 64
            (run_root / "run_contract.json").write_text(json.dumps(contract))
            with self.assertRaisesRegex(LiveDryRunError, "validator report hash mismatch"):
                validate_live_dry_run(run_root)

    def test_input_path_escape_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryDirectory() as outside:
            path = Path(outside) / "probe.json"
            path.write_text("{}", encoding="utf-8")
            with self.assertRaises(LiveDryRunError):
                run_daily_dry_run(
                    private_runtime_root=temporary,
                    output_root="runs",
                    run_id="dry-run-escape",
                    decision_session_date="2026-08-24",
                    source_probe_receipts=[path],
                )

    def test_output_path_escape_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryDirectory() as outside:
            with self.assertRaises(LiveDryRunError):
                run_daily_dry_run(
                    private_runtime_root=temporary,
                    output_root=outside,
                    run_id="dry-run-output-escape",
                    decision_session_date="2026-08-24",
                )

    @unittest.skipIf(os.name == "nt", "creating directory symlinks requires Windows privilege")
    def test_resume_rejects_receipts_directory_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryDirectory() as outside:
            root = Path(temporary)
            run_daily_dry_run(
                private_runtime_root=root,
                output_root="runs",
                run_id="dry-run-receipt-link",
                decision_session_date="2026-08-24",
            )
            receipts = root / "runs/dry-run-receipt-link/receipts"
            shutil.rmtree(receipts)
            receipts.symlink_to(Path(outside), target_is_directory=True)

            with self.assertRaisesRegex(LiveDryRunError, "symlinks or reparse points"):
                run_daily_dry_run(
                    private_runtime_root=root,
                    output_root="runs",
                    run_id="dry-run-receipt-link",
                    decision_session_date="2026-08-24",
                )

    def test_duplicate_probe_bytes_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, paths, _ = self._runtime(temporary)
            copy = root / "inputs/probe-copy.json"
            copy.write_bytes((root / paths["probe"]).read_bytes())
            with self.assertRaises(LiveDryRunError):
                run_daily_dry_run(
                    private_runtime_root=root,
                    output_root="runs",
                    run_id="dry-run-duplicate-probe",
                    decision_session_date="2026-08-24",
                    source_probe_receipts=[paths["probe"], copy.relative_to(root)],
                )

    def test_receipt_reordering_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_daily_dry_run(
                private_runtime_root=root,
                output_root="runs",
                run_id="dry-run-tamper",
                decision_session_date="2026-08-24",
            )
            run_root = root / "runs/dry-run-tamper"
            path = run_root / f"receipts/02_{EXPECTED_STAGES[1]}.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["stage"] = EXPECTED_STAGES[2]
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(LiveDryRunError):
                validate_live_dry_run(run_root)

    def test_unexpected_receipt_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_daily_dry_run(
                private_runtime_root=root,
                output_root="runs",
                run_id="dry-run-extra-receipt",
                decision_session_date="2026-08-24",
            )
            run_root = root / "runs/dry-run-extra-receipt"
            (run_root / "receipts/11_FORGED.json").write_text("{}", encoding="utf-8")
            with self.assertRaises(LiveDryRunError):
                validate_live_dry_run(run_root)

    def test_input_binding_shape_tamper_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_daily_dry_run(
                private_runtime_root=root,
                output_root="runs",
                run_id="dry-run-binding-tamper",
                decision_session_date="2026-08-24",
            )
            run_root = root / "runs/dry-run-binding-tamper"
            path = run_root / "run_contract.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            del payload["input_bindings"]["champion_freeze_sha256"][
                EXPECTED_PRODUCTS[0]["product_id"]
            ]
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(LiveDryRunError):
                validate_live_dry_run(run_root)

    def test_sealed_output_requires_exact_four_product_abstention(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, paths, freezes = self._runtime(temporary)
            self._complete(root, paths, freezes, run_id="dry-run-seal-tamper")
            run_root = root / "runs/dry-run-seal-tamper"
            sealed = run_root / "sealed_research_output.json"
            payload = json.loads(sealed.read_text(encoding="utf-8"))
            payload["products"] = []
            sealed.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(LiveDryRunError):
                validate_live_dry_run(run_root)

    def test_private_locator_leak_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_daily_dry_run(
                private_runtime_root=root,
                output_root="runs",
                run_id="dry-run-private",
                decision_session_date="2026-08-24",
            )
            run_root = root / "runs/dry-run-private"
            path = run_root / "run_contract.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["input_bindings"]["raw_evidence_manifest_sha256"] = (
                "https://example.invalid/private"
            )
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(LiveDryRunError):
                validate_live_dry_run(run_root)

    def test_all_dry_run_schemas_accept_output(self) -> None:
        if Draft202012Validator is None:
            self.skipTest("jsonschema unavailable")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_daily_dry_run(
                private_runtime_root=root,
                output_root="runs",
                run_id="dry-run-schema",
                decision_session_date="2026-08-24",
            )
            run_root = root / "runs/dry-run-schema"
            report_schema = json.loads(
                (ROOT / "schemas/live-dry-run-report.schema.json").read_text(encoding="utf-8")
            )
            receipt_schema = json.loads(
                (ROOT / "schemas/live-dry-run-receipt.schema.json").read_text(encoding="utf-8")
            )
            contract_schema = json.loads(
                (ROOT / "schemas/live-dry-run-contract.schema.json").read_text(encoding="utf-8")
            )
            sealed_schema = json.loads(
                (ROOT / "schemas/live-dry-run-sealed-output.schema.json").read_text(
                    encoding="utf-8"
                )
            )
            for schema in (report_schema, receipt_schema, contract_schema, sealed_schema):
                Draft202012Validator.check_schema(schema)
            report = json.loads((run_root / "dry_run_report.json").read_text(encoding="utf-8"))
            receipt = json.loads(
                (run_root / f"receipts/01_{EXPECTED_STAGES[0]}.json").read_text(encoding="utf-8")
            )
            contract = json.loads((run_root / "run_contract.json").read_text(encoding="utf-8"))
            self.assertEqual(list(Draft202012Validator(report_schema).iter_errors(report)), [])
            self.assertEqual(list(Draft202012Validator(receipt_schema).iter_errors(receipt)), [])
            self.assertEqual(list(Draft202012Validator(contract_schema).iter_errors(contract)), [])

            _, paths, freezes = self._runtime(temporary)
            self._complete(root, paths, freezes, run_id="dry-run-schema-complete")
            sealed = json.loads(
                (root / "runs/dry-run-schema-complete/sealed_research_output.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(list(Draft202012Validator(sealed_schema).iter_errors(sealed)), [])


if __name__ == "__main__":
    unittest.main()
