from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import tempfile
import unittest

from jsonschema import Draft202012Validator, ValidationError
from referencing import Registry, Resource

from kubo.hashing import canonical_json_bytes, hash_json, sha256_bytes
from kubo.tri_security_pilot import prepare_tri_security_batch_workspace
from kubo.tri_security_receipts import (
    RECEIPT_CLAIM_BOUNDARY,
    RUN_RECEIPT_FILE,
    STAGE_BINDING_FILE,
    TriSecurityReceiptError,
    issue_tri_security_run_receipt,
    issue_tri_security_stage_binding,
    verify_tri_security_run_receipt,
    verify_tri_security_stage_binding,
)


ROOT = Path(__file__).resolve().parents[1]
FIRST_BATCH_ID = "tri-001-kfh-ship-aznoula"
KEY = b"tri-security-receipt-unit-key-v1-32bytes"
OTHER_KEY = b"tri-security-receipt-other-key-32bytes"
KEY_ID = "tri-receipt-unit-key-v1"
STAGE_KEY = b"tri-security-stage-unit-key-v1-32bytes!"
STAGE_KEY_ID = "tri-stage-unit-key-v1"
ISSUED_AT = "2026-08-12T21:30:00+00:00"
EXPIRES_AT = "2026-08-14T21:30:00+00:00"
DECISION_AT = "2026-08-13T08:00:00+03:00"


def _write_canonical(path: Path, payload: dict[str, object]) -> None:
    path.write_bytes(canonical_json_bytes(payload))


def _schema_validator(name: str) -> Draft202012Validator:
    schemas = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (ROOT / "schemas").glob("*.schema.json")
    ]
    registry = Registry().with_resources(
        [
            (schema["$id"], Resource.from_contents(schema))
            for schema in schemas
            if "$id" in schema
        ]
    )
    schema = next(
        schema
        for schema in schemas
        if schema.get("$id", "").endswith(f"/{name}")
    )
    return Draft202012Validator(
        schema,
        registry=registry,
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    )


class TriSecurityReceiptTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.root = Path(self._temporary.name)
        self.workspace = self.root / "workspace"
        self.workspace_report = prepare_tri_security_batch_workspace(
            config_dir=ROOT / "config",
            output_root=self.workspace,
            batch_id=FIRST_BATCH_ID,
            run_id="tri-receipt-test-run",
            window_from="2026-08-01",
            window_to="2026-08-12",
            prepared_by="receipt-unit-test",
        )
        self.plan_sha256 = self.workspace_report["batch_plan_sha256"]
        self.scoped_manifest_sha256 = self.workspace_report[
            "scoped_config_manifest_sha256"
        ]
        self._receipt_number = 0
        self._stage_number = 0

    def _issue_receipt(
        self,
        *,
        receipt_id: str | None = None,
        output_root: Path | None = None,
    ) -> tuple[Path, dict[str, object]]:
        self._receipt_number += 1
        number = self._receipt_number
        target = output_root or self.root / f"receipt-{number}"
        report = issue_tri_security_run_receipt(
            workspace_root=self.workspace,
            output_root=target,
            expected_batch_plan_sha256=self.plan_sha256,
            expected_scoped_config_manifest_sha256=self.scoped_manifest_sha256,
            receipt_id=receipt_id or f"tri-receipt-{number}",
            issuer_id="unit-test-authority",
            issued_at=ISSUED_AT,
            expires_at=EXPIRES_AT,
            key=KEY,
            key_id=KEY_ID,
        )
        return target / RUN_RECEIPT_FILE, report

    def _verify_receipt(
        self,
        receipt_path: Path,
        **overrides: object,
    ):
        arguments: dict[str, object] = {
            "receipt_path": receipt_path,
            "workspace_root": self.workspace,
            "expected_batch_plan_sha256": self.plan_sha256,
            "expected_scoped_config_manifest_sha256": self.scoped_manifest_sha256,
            "decision_at": DECISION_AT,
            "key": KEY,
            "expected_key_id": KEY_ID,
            "expected_run_id": "tri-receipt-test-run",
            "expected_batch_id": FIRST_BATCH_ID,
        }
        arguments.update(overrides)
        return verify_tri_security_run_receipt(**arguments)

    def _stage(self, *, content: bytes = b"stage-evidence-v1") -> tuple[Path, str]:
        self._stage_number += 1
        stage = self.root / f"stage-{self._stage_number}"
        stage.mkdir()
        artifact = stage / "raw" / "evidence.bin"
        artifact.parent.mkdir()
        artifact.write_bytes(content)
        manifest = {
            "schema_version": "3.0",
            "artifacts": [
                {
                    "path": "raw/evidence.bin",
                    "sha256": sha256_bytes(content),
                    "size_bytes": len(content),
                }
            ],
        }
        manifest_bytes = canonical_json_bytes(manifest)
        (stage / "manifest.json").write_bytes(manifest_bytes)
        return stage, sha256_bytes(manifest_bytes)

    def _issue_stage_binding(
        self,
        *,
        receipt,
        stage: Path,
        stage_manifest_sha256: str,
        output_root: Path | None = None,
        binding_id: str = "tri-stage-binding-1",
        bound_at: str = "2026-08-13T09:00:00+03:00",
        key: bytes = STAGE_KEY,
        key_id: str = STAGE_KEY_ID,
    ) -> tuple[Path, dict[str, object]]:
        target = output_root or self.root / f"binding-{self._stage_number}"
        report = issue_tri_security_stage_binding(
            verified_receipt=receipt,
            workspace_root=self.workspace,
            stage_root=stage,
            output_root=target,
            expected_stage_manifest_sha256=stage_manifest_sha256,
            binding_id=binding_id,
            stage_id="OFFICIAL_FOUNDATION",
            bound_at=bound_at,
            key=key,
            key_id=key_id,
        )
        return target / STAGE_BINDING_FILE, report

    def _verify_stage_binding(
        self,
        *,
        binding_path: Path,
        receipt_path: Path,
        stage: Path,
        stage_manifest_sha256: str,
        **overrides: object,
    ) -> dict[str, object]:
        arguments: dict[str, object] = {
            "binding_path": binding_path,
            "receipt_path": receipt_path,
            "workspace_root": self.workspace,
            "stage_root": stage,
            "expected_batch_plan_sha256": self.plan_sha256,
            "expected_scoped_config_manifest_sha256": self.scoped_manifest_sha256,
            "expected_stage_manifest_sha256": stage_manifest_sha256,
            "decision_at": "2026-08-13T10:00:00+03:00",
            "key": STAGE_KEY,
            "expected_key_id": STAGE_KEY_ID,
            "receipt_key": KEY,
            "expected_receipt_key_id": KEY_ID,
            "expected_stage_id": "OFFICIAL_FOUNDATION",
            "expected_run_id": "tri-receipt-test-run",
            "expected_batch_id": FIRST_BATCH_ID,
        }
        arguments.update(overrides)
        return verify_tri_security_stage_binding(**arguments)

    def test_issue_and_verify_binds_dynamic_kuwait_date_and_exact_tri_scope(self) -> None:
        receipt_path, issuance = self._issue_receipt()

        self.assertEqual(issuance["status"], "PASS")
        self.assertEqual(issuance["run_date"], "2026-08-13")
        verified = self._verify_receipt(receipt_path)
        report = verified.report()

        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["run_date"], "2026-08-13")
        self.assertEqual(report["security_count"], 3)
        self.assertEqual(report["batch_plan_sha256"], self.plan_sha256)
        self.assertEqual(
            report["scoped_config_manifest_sha256"],
            self.scoped_manifest_sha256,
        )
        cohort = verified.binding["cohort"]
        self.assertEqual(
            [row["security_code"] for row in cohort["securities"]],
            ["108", "506", "826"],
        )
        self.assertEqual(
            [row["ticker"] for row in cohort["securities"]],
            ["KFH", "SHIP", "AZNOULA"],
        )
        benchmark = report["benchmark_scope"]
        self.assertEqual(
            benchmark["scope_state"],
            "CONFIGURED_SERIES_INCOMPATIBLE_WITH_TRI_COHORT",
        )
        self.assertEqual(benchmark["comparison_scope"], "NAMED_TRI_SECURITY_COHORT")
        self.assertEqual(benchmark["comparison_security_count"], 3)
        self.assertEqual(
            benchmark["comparison_security_codes"], ["108", "506", "826"]
        )
        self.assertEqual(
            benchmark["comparison_sectors"], ["Banks", "Industrials", "Utilities"]
        )
        self.assertEqual(
            benchmark["missing_cohort_sector_series"], ["Industrials", "Utilities"]
        )
        self.assertFalse(benchmark["five_security_scope_allowed"])
        self.assertFalse(benchmark["full_market_scope_allowed"])
        self.assertFalse(benchmark["benchmark_qualification_allowed"])
        self.assertEqual(report["claim_boundary"], RECEIPT_CLAIM_BOUNDARY)
        self.assertTrue(report["claim_boundaries"]["three_security_cohort"])
        self.assertFalse(report["claim_boundaries"]["five_security_claim_allowed"])
        self.assertFalse(report["claim_boundaries"]["full_market_claim_allowed"])
        self.assertFalse(report["claim_boundaries"]["backtest_ready"])
        self.assertFalse(report["claim_boundaries"]["forecast_allowed"])

    def test_receipt_rejects_wrong_key_key_id_expiry_and_tampering(self) -> None:
        receipt_path, _ = self._issue_receipt()

        with self.assertRaisesRegex(TriSecurityReceiptError, "authentication failed"):
            self._verify_receipt(receipt_path, key=OTHER_KEY)
        with self.assertRaisesRegex(TriSecurityReceiptError, "key_id mismatch"):
            self._verify_receipt(receipt_path, expected_key_id="another-key")
        with self.assertRaisesRegex(TriSecurityReceiptError, "not valid at decision_at"):
            self._verify_receipt(receipt_path, decision_at=EXPIRES_AT)

        payload = json.loads(receipt_path.read_text(encoding="utf-8"))
        payload["binding"]["run_id"] = "tampered-run"
        _write_canonical(receipt_path, payload)
        with self.assertRaisesRegex(TriSecurityReceiptError, "authentication failed"):
            self._verify_receipt(receipt_path)

    def test_receipt_rejects_expected_hash_mismatch_and_workspace_mutation(self) -> None:
        receipt_path, _ = self._issue_receipt()

        with self.assertRaisesRegex(ValueError, "batch plan SHA-256 mismatch"):
            self._verify_receipt(
                receipt_path,
                expected_batch_plan_sha256="0" * 64,
            )
        with self.assertRaisesRegex(
            ValueError,
            "scoped (configuration binding|manifest SHA-256) mismatch",
        ):
            self._verify_receipt(
                receipt_path,
                expected_scoped_config_manifest_sha256="0" * 64,
            )

        plan_path = self.workspace / "plan" / "tri_security_batch_plan.json"
        original_plan = plan_path.read_bytes()
        plan = json.loads(original_plan)
        plan["prepared_by"] = "mutated-after-receipt"
        _write_canonical(plan_path, plan)
        with self.assertRaisesRegex(ValueError, "batch plan SHA-256 mismatch"):
            self._verify_receipt(receipt_path)
        plan_path.write_bytes(original_plan)

        scoped_file = self.workspace / "scoped_config" / "pilot" / "security_master_seed.json"
        original_scoped_file = scoped_file.read_bytes()
        scoped_file.write_bytes(original_scoped_file + b"\n")
        with self.assertRaisesRegex(ValueError, "configuration hash mismatch"):
            self._verify_receipt(receipt_path)

    def test_receipt_rejects_five_security_scope_and_weakened_nonclaims(self) -> None:
        receipt_path, _ = self._issue_receipt()
        original = json.loads(receipt_path.read_text(encoding="utf-8"))
        forged = copy.deepcopy(original)
        cohort = forged["binding"]["cohort"]
        cohort["securities"].extend(copy.deepcopy(cohort["securities"][:2]))
        cohort["security_count"] = 5
        cohort["cohort_sha256"] = hash_json(
            {
                "security_count": cohort["security_count"],
                "securities": cohort["securities"],
            }
        )
        forged["binding"]["benchmark_scope"]["comparison_scope"] = (
            "FIVE_SECURITY_PILOT"
        )
        forged["binding"]["benchmark_scope"]["comparison_security_count"] = 5
        forged["binding"]["benchmark_scope"]["comparison_security_codes"] = [
            row["security_code"] for row in cohort["securities"]
        ]
        forged["binding"]["benchmark_scope"]["five_security_scope_allowed"] = True
        _write_canonical(receipt_path, forged)
        with self.assertRaisesRegex(TriSecurityReceiptError, "not exactly three"):
            self._verify_receipt(receipt_path)

        second_path, _ = self._issue_receipt()
        weakened = json.loads(second_path.read_text(encoding="utf-8"))
        weakened["claim_boundaries"]["five_security_claim_allowed"] = True
        _write_canonical(second_path, weakened)
        with self.assertRaisesRegex(TriSecurityReceiptError, "were weakened"):
            self._verify_receipt(second_path)

    def test_stage_binding_issue_verify_and_artifact_mutation(self) -> None:
        receipt_path, _ = self._issue_receipt()
        receipt = self._verify_receipt(receipt_path)
        stage, stage_manifest_sha256 = self._stage()
        binding_path, issuance = self._issue_stage_binding(
            receipt=receipt,
            stage=stage,
            stage_manifest_sha256=stage_manifest_sha256,
        )

        self.assertEqual(issuance["status"], "PASS")
        verified = self._verify_stage_binding(
            binding_path=binding_path,
            receipt_path=receipt_path,
            stage=stage,
            stage_manifest_sha256=stage_manifest_sha256,
        )
        report = verified.report()
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["stage_id"], "OFFICIAL_FOUNDATION")
        self.assertEqual(report["run_date"], "2026-08-13")
        self.assertEqual(report["stage_manifest_sha256"], stage_manifest_sha256)
        self.assertFalse(report["claim_boundaries"]["five_security_claim_allowed"])
        self.assertFalse(report["claim_boundaries"]["full_market_claim_allowed"])
        self.assertIn("raw/evidence.bin", verified.files)

        (stage / "raw" / "evidence.bin").write_bytes(b"stage-evidence-v2")
        with self.assertRaisesRegex(ValueError, "stage artifact changed or mismatched"):
            self._verify_stage_binding(
                binding_path=binding_path,
                receipt_path=receipt_path,
                stage=stage,
                stage_manifest_sha256=stage_manifest_sha256,
            )

    def test_stage_binding_rejects_cross_receipt_mix(self) -> None:
        first_path, _ = self._issue_receipt(receipt_id="receipt-first")
        first = self._verify_receipt(first_path)
        second_path, _ = self._issue_receipt(receipt_id="receipt-second")
        self._verify_receipt(second_path)
        stage, stage_manifest_sha256 = self._stage()
        binding_path, _ = self._issue_stage_binding(
            receipt=first,
            stage=stage,
            stage_manifest_sha256=stage_manifest_sha256,
        )

        with self.assertRaisesRegex(TriSecurityReceiptError, "mixes a different"):
            self._verify_stage_binding(
                binding_path=binding_path,
                receipt_path=second_path,
                stage=stage,
                stage_manifest_sha256=stage_manifest_sha256,
            )

    def test_stage_binding_rejects_wrong_manifest_hash_and_binding_tampering(self) -> None:
        receipt_path, _ = self._issue_receipt()
        receipt = self._verify_receipt(receipt_path)
        stage, stage_manifest_sha256 = self._stage()
        with self.assertRaisesRegex(TriSecurityReceiptError, "manifest SHA-256 mismatch"):
            self._issue_stage_binding(
                receipt=receipt,
                stage=stage,
                stage_manifest_sha256="0" * 64,
            )

        binding_path, _ = self._issue_stage_binding(
            receipt=receipt,
            stage=stage,
            stage_manifest_sha256=stage_manifest_sha256,
        )
        binding = json.loads(binding_path.read_text(encoding="utf-8"))
        binding["stage_id"] = "STATUS_CORPORATE"
        _write_canonical(binding_path, binding)
        with self.assertRaisesRegex(TriSecurityReceiptError, "authentication failed"):
            self._verify_stage_binding(
                binding_path=binding_path,
                receipt_path=receipt_path,
                stage=stage,
                stage_manifest_sha256=stage_manifest_sha256,
            )

    def test_output_roots_refuse_overwrite_and_unsafe_placement(self) -> None:
        output_root = self.root / "receipt-output"
        receipt_path, _ = self._issue_receipt(output_root=output_root)
        receipt = self._verify_receipt(receipt_path)
        with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
            self._issue_receipt(output_root=output_root)
        with self.assertRaisesRegex(TriSecurityReceiptError, "outside bound workspaces"):
            self._issue_receipt(output_root=self.workspace / "unsafe-receipt")

        stage, stage_manifest_sha256 = self._stage()
        with self.assertRaisesRegex(TriSecurityReceiptError, "outside bound workspaces"):
            self._issue_stage_binding(
                receipt=receipt,
                stage=stage,
                stage_manifest_sha256=stage_manifest_sha256,
                output_root=stage / "unsafe-binding",
            )

        unsafe_stage = self.workspace / "unsafe-stage"
        unsafe_stage.mkdir()
        with self.assertRaisesRegex(TriSecurityReceiptError, "outside the prepared workspace"):
            self._issue_stage_binding(
                receipt=receipt,
                stage=unsafe_stage,
                stage_manifest_sha256="0" * 64,
                output_root=self.root / "unused-binding",
            )

    def test_stage_issue_rejects_reverse_overlap_and_different_workspace(self) -> None:
        receipt_path, _ = self._issue_receipt()
        receipt = self._verify_receipt(receipt_path)
        ancestor_stage = self.root
        with self.subTest("stage root is workspace ancestor"):
            with self.assertRaisesRegex(
                TriSecurityReceiptError,
                "outside the prepared workspace",
            ):
                self._issue_stage_binding(
                    receipt=receipt,
                    stage=ancestor_stage,
                    stage_manifest_sha256="0" * 64,
                    output_root=self.root.parent / "unused-overlap-binding",
                )

        different_workspace = self.root / "different-workspace"
        different_workspace.mkdir()
        stage, stage_manifest_sha256 = self._stage()
        with self.subTest("receipt verified against another workspace"):
            with self.assertRaisesRegex(
                TriSecurityReceiptError,
                "differs from the verified run receipt",
            ):
                issue_tri_security_stage_binding(
                    verified_receipt=receipt,
                    workspace_root=different_workspace,
                    stage_root=stage,
                    output_root=self.root / "unused-different-workspace-binding",
                    expected_stage_manifest_sha256=stage_manifest_sha256,
                    binding_id="different-workspace-binding",
                    stage_id="OFFICIAL_FOUNDATION",
                    bound_at="2026-08-13T09:00:00+03:00",
                    key=STAGE_KEY,
                    key_id=STAGE_KEY_ID,
                )

    def test_stage_verification_rejects_binding_or_stage_inside_workspace(self) -> None:
        receipt_path, _ = self._issue_receipt()
        receipt = self._verify_receipt(receipt_path)
        stage, stage_manifest_sha256 = self._stage()
        binding_path, _ = self._issue_stage_binding(
            receipt=receipt,
            stage=stage,
            stage_manifest_sha256=stage_manifest_sha256,
        )

        internal_binding = self.workspace / "unsafe-stage-binding.json"
        internal_binding.write_bytes(binding_path.read_bytes())
        with self.subTest("binding path"):
            with self.assertRaisesRegex(
                TriSecurityReceiptError,
                "outside bound workspaces",
            ):
                self._verify_stage_binding(
                    binding_path=internal_binding,
                    receipt_path=receipt_path,
                    stage=stage,
                    stage_manifest_sha256=stage_manifest_sha256,
                )

        internal_stage = self.workspace / "copied-stage"
        (internal_stage / "raw").mkdir(parents=True)
        (internal_stage / "raw" / "evidence.bin").write_bytes(
            (stage / "raw" / "evidence.bin").read_bytes()
        )
        (internal_stage / "manifest.json").write_bytes(
            (stage / "manifest.json").read_bytes()
        )
        with self.subTest("stage path"):
            with self.assertRaisesRegex(
                TriSecurityReceiptError,
                "outside the prepared workspace",
            ):
                self._verify_stage_binding(
                    binding_path=binding_path,
                    receipt_path=receipt_path,
                    stage=internal_stage,
                    stage_manifest_sha256=stage_manifest_sha256,
                )

    def test_run_and_stage_authentication_keys_must_be_independent(self) -> None:
        receipt_path, _ = self._issue_receipt()
        receipt = self._verify_receipt(receipt_path)
        stage, stage_manifest_sha256 = self._stage()
        binding_path, _ = self._issue_stage_binding(
            receipt=receipt,
            stage=stage,
            stage_manifest_sha256=stage_manifest_sha256,
        )

        with self.subTest("same key bytes"):
            with self.assertRaisesRegex(
                TriSecurityReceiptError,
                "run and stage HMAC keys must be independent",
            ):
                self._verify_stage_binding(
                    binding_path=binding_path,
                    receipt_path=receipt_path,
                    stage=stage,
                    stage_manifest_sha256=stage_manifest_sha256,
                    key=KEY,
                )
        with self.subTest("same key id"):
            with self.assertRaisesRegex(
                TriSecurityReceiptError,
                "run and stage HMAC key IDs must be independent",
            ):
                self._verify_stage_binding(
                    binding_path=binding_path,
                    receipt_path=receipt_path,
                    stage=stage,
                    stage_manifest_sha256=stage_manifest_sha256,
                    expected_key_id=KEY_ID,
                    expected_receipt_key_id=KEY_ID,
                )

    def test_stage_binding_before_receipt_issuance_is_rejected(self) -> None:
        receipt_path, _ = self._issue_receipt()
        receipt = self._verify_receipt(receipt_path)
        stage, stage_manifest_sha256 = self._stage()

        with self.assertRaisesRegex(
            TriSecurityReceiptError,
            "outside the run receipt validity",
        ):
            self._issue_stage_binding(
                receipt=receipt,
                stage=stage,
                stage_manifest_sha256=stage_manifest_sha256,
                bound_at="2026-08-12T21:29:59+00:00",
            )

    def test_complete_stage_tree_binds_unlisted_normalized_and_report_bytes(self) -> None:
        receipt_path, _ = self._issue_receipt()
        receipt = self._verify_receipt(receipt_path)
        stage, stage_manifest_sha256 = self._stage()
        normalized_path = stage / "normalized" / "rows.json"
        normalized_path.parent.mkdir()
        normalized_bytes = b'{"rows":[{"security_code":"108"}]}'
        normalized_path.write_bytes(normalized_bytes)
        report_path = stage / "reports" / "qualification.json"
        report_path.parent.mkdir()
        report_bytes = b'{"status":"PENDING_EXTERNAL_EVIDENCE"}'
        report_path.write_bytes(report_bytes)
        binding_path, _ = self._issue_stage_binding(
            receipt=receipt,
            stage=stage,
            stage_manifest_sha256=stage_manifest_sha256,
        )

        verified = self._verify_stage_binding(
            binding_path=binding_path,
            receipt_path=receipt_path,
            stage=stage,
            stage_manifest_sha256=stage_manifest_sha256,
        )
        self.assertEqual(verified.files["normalized/rows.json"], normalized_bytes)
        self.assertEqual(
            verified.files["reports/qualification.json"],
            report_bytes,
        )

        normalized_path.write_bytes(b'{"rows":[]}')
        self.assertEqual(verified.files["normalized/rows.json"], normalized_bytes)
        with self.subTest("unlisted normalized file"):
            with self.assertRaisesRegex(
                TriSecurityReceiptError,
                "stage artifacts changed after binding",
            ):
                self._verify_stage_binding(
                    binding_path=binding_path,
                    receipt_path=receipt_path,
                    stage=stage,
                    stage_manifest_sha256=stage_manifest_sha256,
                )
        normalized_path.write_bytes(normalized_bytes)

        report_path.write_bytes(b'{"status":"PASS"}')
        self.assertEqual(
            verified.files["reports/qualification.json"],
            report_bytes,
        )
        with self.subTest("unlisted report file"):
            with self.assertRaisesRegex(
                TriSecurityReceiptError,
                "stage artifacts changed after binding",
            ):
                self._verify_stage_binding(
                    binding_path=binding_path,
                    receipt_path=receipt_path,
                    stage=stage,
                    stage_manifest_sha256=stage_manifest_sha256,
                )

    def test_stage_tree_rejects_symlink_when_supported(self) -> None:
        receipt_path, _ = self._issue_receipt()
        receipt = self._verify_receipt(receipt_path)
        stage, stage_manifest_sha256 = self._stage()
        link = stage / "normalized" / "evidence-link.bin"
        link.parent.mkdir()
        try:
            link.symlink_to(Path("../raw/evidence.bin"))
        except (NotImplementedError, OSError) as exc:
            self.skipTest(f"symlink creation unavailable: {exc}")

        with self.assertRaisesRegex(ValueError, "symlinks or reparse points"):
            self._issue_stage_binding(
                receipt=receipt,
                stage=stage,
                stage_manifest_sha256=stage_manifest_sha256,
            )

    def test_stage_tree_rejects_special_file_when_supported(self) -> None:
        make_fifo = getattr(os, "mkfifo", None)
        if make_fifo is None:
            self.skipTest("FIFO creation is unavailable on this platform")
        receipt_path, _ = self._issue_receipt()
        receipt = self._verify_receipt(receipt_path)
        stage, stage_manifest_sha256 = self._stage()
        fifo = stage / "reports" / "evidence.pipe"
        fifo.parent.mkdir()
        try:
            make_fifo(fifo)
        except (NotImplementedError, OSError) as exc:
            self.skipTest(f"FIFO creation unavailable: {exc}")

        with self.assertRaisesRegex(ValueError, "only regular files and directories"):
            self._issue_stage_binding(
                receipt=receipt,
                stage=stage,
                stage_manifest_sha256=stage_manifest_sha256,
            )

    def test_schemas_validate_issued_documents_and_reject_unknown_fields(self) -> None:
        receipt_path, _ = self._issue_receipt()
        receipt = self._verify_receipt(receipt_path)
        stage, stage_manifest_sha256 = self._stage()
        binding_path, _ = self._issue_stage_binding(
            receipt=receipt,
            stage=stage,
            stage_manifest_sha256=stage_manifest_sha256,
        )
        receipt_payload = json.loads(receipt_path.read_text(encoding="utf-8"))
        binding_payload = json.loads(binding_path.read_text(encoding="utf-8"))
        receipt_validator = _schema_validator("tri-security-run-receipt.schema.json")
        binding_validator = _schema_validator("tri-security-stage-binding.schema.json")

        receipt_validator.validate(receipt_payload)
        binding_validator.validate(binding_payload)

        receipt_with_unknown = copy.deepcopy(receipt_payload)
        receipt_with_unknown["untrusted_extension"] = True
        with self.assertRaises(ValidationError):
            receipt_validator.validate(receipt_with_unknown)
        binding_with_unknown = copy.deepcopy(binding_payload)
        binding_with_unknown["stage_artifact"]["untrusted_extension"] = True
        with self.assertRaises(ValidationError):
            binding_validator.validate(binding_with_unknown)

    def test_receipt_and_binding_reject_duplicate_or_noncanonical_json(self) -> None:
        duplicate_path, _ = self._issue_receipt()
        original = duplicate_path.read_bytes()
        duplicate_path.write_bytes(
            b'{"audience":"kubo-tri-security-run",' + original[1:]
        )
        with self.subTest("duplicate receipt key"):
            with self.assertRaisesRegex(ValueError, "contains duplicate key"):
                self._verify_receipt(duplicate_path)

        noncanonical_path, _ = self._issue_receipt()
        payload = json.loads(noncanonical_path.read_text(encoding="utf-8"))
        noncanonical_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        with self.subTest("noncanonical receipt"):
            with self.assertRaisesRegex(TriSecurityReceiptError, "canonical JSON"):
                self._verify_receipt(noncanonical_path)

        receipt_path, _ = self._issue_receipt()
        receipt = self._verify_receipt(receipt_path)
        stage, stage_manifest_sha256 = self._stage()
        binding_path, _ = self._issue_stage_binding(
            receipt=receipt,
            stage=stage,
            stage_manifest_sha256=stage_manifest_sha256,
        )
        binding = json.loads(binding_path.read_text(encoding="utf-8"))
        binding_path.write_text(
            json.dumps(binding, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        with self.subTest("noncanonical stage binding"):
            with self.assertRaisesRegex(TriSecurityReceiptError, "canonical JSON"):
                self._verify_stage_binding(
                    binding_path=binding_path,
                    receipt_path=receipt_path,
                    stage=stage,
                    stage_manifest_sha256=stage_manifest_sha256,
                )

    def test_forged_later_batch_execution_remains_locked(self) -> None:
        plan_path = self.workspace / "plan" / "tri_security_batch_plan.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        plan["execution"] = {
            "sequence": 2,
            "predecessor_batch_id": FIRST_BATCH_ID,
            "predecessor_qualification_required": True,
        }
        plan_bytes = canonical_json_bytes(plan)
        plan_path.write_bytes(plan_bytes)
        output = self.root / "forged-second-batch-receipt"

        with self.assertRaisesRegex(
            TriSecurityReceiptError,
            "locked to batch one",
        ):
            issue_tri_security_run_receipt(
                workspace_root=self.workspace,
                output_root=output,
                expected_batch_plan_sha256=sha256_bytes(plan_bytes),
                expected_scoped_config_manifest_sha256=self.scoped_manifest_sha256,
                receipt_id="forged-second-batch-receipt",
                issuer_id="unit-test-authority",
                issued_at=ISSUED_AT,
                expires_at=EXPIRES_AT,
                key=KEY,
                key_id=KEY_ID,
            )
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
