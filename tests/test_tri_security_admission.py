from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

try:
    from jsonschema import Draft202012Validator, ValidationError
    from referencing import Registry, Resource
except ModuleNotFoundError:  # Core-only local runs omit the optional test extra.
    Draft202012Validator = None  # type: ignore[assignment,misc]
    ValidationError = ValueError  # type: ignore[assignment,misc]
    Registry = None  # type: ignore[assignment,misc]
    Resource = None  # type: ignore[assignment,misc]

from kubo.foundation_io import TreeSnapshotChangedError
from kubo.hashing import canonical_json_bytes, sha256_bytes
from kubo.tri_security_admission import (
    BOUNDARY_STAGE_MAP,
    RUN_AUTHORITY_ROOT,
    SEMANTIC_ADMISSION_CLAIM_BOUNDARY,
    SEMANTIC_ADMISSION_FILE,
    STAGE_PREDECESSORS,
    BoundaryAdmissionError,
    BoundaryAdmissionRequest,
    admit_boundary,
    admit_serialized_boundary,
    build_boundary_operation_binding,
    issue_semantic_boundary_admission,
)
from kubo.tri_security_pilot import prepare_tri_security_batch_workspace
from kubo.tri_security_receipts import (
    RUN_RECEIPT_FILE,
    STAGE_BINDING_FILE,
    issue_tri_security_run_receipt,
    issue_tri_security_stage_binding,
    verify_tri_security_run_receipt,
    verify_tri_security_stage_binding,
)


ROOT = Path(__file__).resolve().parents[1]
RUN_KEY = b"semantic-admission-run-key-32-bytes-v1"
RUN_KEY_ID = "semantic-run-key-v1"
STAGE_KEY = b"semantic-admission-stage-key-32-bytes-v1"
STAGE_KEY_ID = "semantic-stage-key-v1"
SEMANTIC_KEY = b"semantic-admission-v2-key-32-bytes-v1"
SEMANTIC_KEY_ID = "semantic-v2-key-v1"
RUN_ID = "semantic-admission-run"
BATCH_ID = "tri-001-kfh-ship-aznoula"
ISSUED_AT = "2026-08-12T21:30:00+00:00"
EXPIRES_AT = "2026-08-14T21:30:00+00:00"
DECISION_AT = "2026-08-13T10:00:00+03:00"


def _semantic_schema_validator():
    if Draft202012Validator is None or Registry is None or Resource is None:
        raise RuntimeError("jsonschema test extra is unavailable")
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
        if schema.get("$id", "").endswith(
            "/tri-security-semantic-admission.schema.json"
        )
    )
    return Draft202012Validator(
        schema,
        registry=registry,
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    )


class TriSecurityAdmissionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.root = Path(self._temporary.name)
        self.workspace = self.root / "workspace"
        prepared = prepare_tri_security_batch_workspace(
            config_dir=ROOT / "config",
            output_root=self.workspace,
            batch_id=BATCH_ID,
            run_id=RUN_ID,
            window_from="2026-08-01",
            window_to="2026-08-12",
            prepared_by="semantic-admission-test",
        )
        self.plan_sha256 = prepared["batch_plan_sha256"]
        self.scoped_sha256 = prepared["scoped_config_manifest_sha256"]
        receipt_root = self.root / "run-receipt"
        issue_tri_security_run_receipt(
            workspace_root=self.workspace,
            output_root=receipt_root,
            expected_batch_plan_sha256=self.plan_sha256,
            expected_scoped_config_manifest_sha256=self.scoped_sha256,
            receipt_id="semantic-test-receipt",
            issuer_id="semantic-test-authority",
            issued_at=ISSUED_AT,
            expires_at=EXPIRES_AT,
            key=RUN_KEY,
            key_id=RUN_KEY_ID,
        )
        self.receipt_path = receipt_root / RUN_RECEIPT_FILE
        self.receipt = verify_tri_security_run_receipt(
            receipt_path=self.receipt_path,
            workspace_root=self.workspace,
            expected_batch_plan_sha256=self.plan_sha256,
            expected_scoped_config_manifest_sha256=self.scoped_sha256,
            decision_at=DECISION_AT,
            key=RUN_KEY,
            expected_key_id=RUN_KEY_ID,
            expected_run_id=RUN_ID,
            expected_batch_id=BATCH_ID,
        )
        self.input_root = self.root / "official-foundation-stage"
        self.input_root.mkdir()
        raw = self.input_root / "raw" / "evidence.bin"
        raw.parent.mkdir()
        raw.write_bytes(b"semantic-stage-evidence")
        manifest = {
            "schema_version": "3.0",
            "artifacts": [
                {
                    "path": "raw/evidence.bin",
                    "sha256": sha256_bytes(raw.read_bytes()),
                    "size_bytes": raw.stat().st_size,
                }
            ],
        }
        manifest_bytes = canonical_json_bytes(manifest)
        (self.input_root / "manifest.json").write_bytes(manifest_bytes)
        self.stage_manifest_sha256 = sha256_bytes(manifest_bytes)
        binding_root = self.root / "v1-stage-binding"
        issue_tri_security_stage_binding(
            verified_receipt=self.receipt,
            workspace_root=self.workspace,
            stage_root=self.input_root,
            output_root=binding_root,
            expected_stage_manifest_sha256=self.stage_manifest_sha256,
            binding_id="semantic-v1-stage-binding",
            stage_id="OFFICIAL_FOUNDATION",
            bound_at="2026-08-13T09:00:00+03:00",
            key=STAGE_KEY,
            key_id=STAGE_KEY_ID,
        )
        self.stage_binding_path = binding_root / STAGE_BINDING_FILE
        self.stage = verify_tri_security_stage_binding(
            binding_path=self.stage_binding_path,
            receipt_path=self.receipt_path,
            workspace_root=self.workspace,
            stage_root=self.input_root,
            expected_batch_plan_sha256=self.plan_sha256,
            expected_scoped_config_manifest_sha256=self.scoped_sha256,
            expected_stage_manifest_sha256=self.stage_manifest_sha256,
            decision_at=DECISION_AT,
            key=STAGE_KEY,
            expected_key_id=STAGE_KEY_ID,
            receipt_key=RUN_KEY,
            expected_receipt_key_id=RUN_KEY_ID,
            expected_stage_id="OFFICIAL_FOUNDATION",
            expected_run_id=RUN_ID,
            expected_batch_id=BATCH_ID,
        )
        self.admission_path = self.root / "semantic-admission.json"
        issue_semantic_boundary_admission(
            output_path=self.admission_path,
            **self.issue_arguments(),
        )

    def issue_arguments(self, **overrides: object) -> dict[str, object]:
        values: dict[str, object] = {
            "boundary_id": "import_official_foundation",
            "verified_receipt": self.receipt,
            "v1_stage_report": self.stage.report(),
            "v1_stage_binding_sha256": self.stage.report()["binding_sha256"],
            "input_root": self.input_root,
            "boundary_inputs": {
                "config_dir": ROOT / "config",
                "workspace": self.input_root,
            },
            "operation_binding": build_boundary_operation_binding(
                "import_official_foundation",
                decision_at=DECISION_AT,
            ),
            "admission_id": "semantic-admission-official-foundation",
            "issued_at": "2026-08-13T09:30:00+03:00",
            "key": SEMANTIC_KEY,
            "key_id": SEMANTIC_KEY_ID,
        }
        values.update(overrides)
        return values

    def request(self, **overrides: object) -> BoundaryAdmissionRequest:
        values: dict[str, object] = {
            "admission_path": self.admission_path,
            "receipt_path": self.receipt_path,
            "stage_binding_path": self.stage_binding_path,
            "workspace_root": self.workspace,
            "input_root": self.input_root,
            "expected_batch_plan_sha256": self.plan_sha256,
            "expected_scoped_config_manifest_sha256": self.scoped_sha256,
            "expected_stage_manifest_sha256": self.stage_manifest_sha256,
            "decision_at": DECISION_AT,
            "expected_run_id": RUN_ID,
            "expected_batch_id": BATCH_ID,
            "run_key": RUN_KEY,
            "run_key_id": RUN_KEY_ID,
            "v1_stage_key": STAGE_KEY,
            "v1_stage_key_id": STAGE_KEY_ID,
            "semantic_key": SEMANTIC_KEY,
            "semantic_key_id": SEMANTIC_KEY_ID,
            "boundary_inputs": {
                "config_dir": ROOT / "config",
                "workspace": self.input_root,
            },
            "operation_binding": build_boundary_operation_binding(
                "import_official_foundation",
                decision_at=DECISION_AT,
            ),
        }
        values.update(overrides)
        return BoundaryAdmissionRequest(**values)

    def test_exact_boundary_stage_map_and_dag_are_locked(self) -> None:
        self.assertEqual(len(BOUNDARY_STAGE_MAP), 8)
        self.assertEqual(
            BOUNDARY_STAGE_MAP["build_data_foundation_packet"],
            "FINAL_DATA_FOUNDATION_RECONCILIATION",
        )
        self.assertEqual(STAGE_PREDECESSORS["OFFICIAL_FOUNDATION"], (RUN_AUTHORITY_ROOT,))
        self.assertEqual(
            STAGE_PREDECESSORS["OFFICIAL_EOD"],
            ("OFFICIAL_FOUNDATION", "STATUS_HISTORY"),
        )

    @unittest.skipIf(
        Draft202012Validator is None,
        "jsonschema optional test dependency is unavailable",
    )
    def test_schema_validates_issued_admission_and_rejects_unknown_fields(
        self,
    ) -> None:
        payload = json.loads(self.admission_path.read_text(encoding="utf-8"))
        validator = _semantic_schema_validator()

        validator.validate(payload)

        top_level_unknown = copy.deepcopy(payload)
        top_level_unknown["untrusted_extension"] = True
        with self.assertRaises(ValidationError):
            validator.validate(top_level_unknown)

        nested_unknown = copy.deepcopy(payload)
        nested_unknown["input_tree"]["untrusted_extension"] = True
        with self.assertRaises(ValidationError):
            validator.validate(nested_unknown)

    def test_valid_root_stage_admission_returns_immutable_prewrite_token(self) -> None:
        output = self.root / "production-output"
        verified = admit_boundary(
            self.request(),
            boundary_id="import_official_foundation",
            output_root=output,
            boundary_inputs=self.request().boundary_inputs,
            operation_binding=self.request().operation_binding,
        )
        self.assertEqual(verified.stage_id, "OFFICIAL_FOUNDATION")
        self.assertEqual(verified.run_id, RUN_ID)
        self.assertEqual(verified.payload["claim_boundary"], SEMANTIC_ADMISSION_CLAIM_BOUNDARY)
        self.assertIn("manifest.json", verified.input_files)
        with self.assertRaises(TypeError):
            verified.payload["claims"]["full_market"] = True
        with self.assertRaises(TypeError):
            verified.payload["input_tree"]["inventory"][0]["sha256"] = "0" * 64
        with self.assertRaises(TypeError):
            self.request().operation_binding["arguments"]["unexpected"] = True
        refreshed = verified.revalidate_before_commit()
        self.assertEqual(refreshed.admission_sha256, verified.admission_sha256)
        self.assertFalse(output.exists())

    def test_wrapper_supplied_operation_binding_must_match_signed_request(self) -> None:
        mismatched = build_boundary_operation_binding(
            "import_official_foundation",
            decision_at="2026-08-13T10:01:00+03:00",
        )
        with self.assertRaises(BoundaryAdmissionError) as raised:
            admit_boundary(
                self.request(),
                boundary_id="import_official_foundation",
                output_root=self.root / "operation-mismatch-output",
                boundary_inputs=self.request().boundary_inputs,
                operation_binding=mismatched,
            )
        self.assertEqual(
            raised.exception.failure_code,
            "OPERATION_BINDING_MISMATCH",
        )
        self.assertEqual(raised.exception.failure_phase, "ENTRY_PRE_WRITE")

    def test_behavioral_operation_fields_are_boundary_specific(self) -> None:
        user_binding = build_boundary_operation_binding(
            "import_user_price_exports",
            decision_at=DECISION_AT,
            observed_at="2026-08-13T09:00:00+03:00",
        )
        self.assertEqual(
            user_binding["arguments"],
            {"observed_at": "2026-08-13T09:00:00+03:00"},
        )
        benchmark_binding = build_boundary_operation_binding(
            "import_benchmark_history",
            decision_at=DECISION_AT,
            imported_at="2026-08-13T09:30:00+03:00",
        )
        self.assertEqual(
            benchmark_binding["arguments"],
            {"imported_at": "2026-08-13T09:30:00+03:00"},
        )
        with self.assertRaises(BoundaryAdmissionError) as raised:
            build_boundary_operation_binding(
                "import_official_foundation",
                decision_at=DECISION_AT,
                imported_at="2026-08-13T09:30:00+03:00",
            )
        self.assertEqual(
            raised.exception.failure_code,
            "OPERATION_BINDING_MISMATCH",
        )

    def _assert_tree_rejection_in_object_and_serialized_channels(
        self,
        expected_code: str,
    ) -> None:
        for admit, phase, suffix in (
            (admit_boundary, "ENTRY_PRE_WRITE", "object"),
            (
                admit_serialized_boundary,
                "ARTIFACT_VALIDATION_PRE_WRITE",
                "serialized",
            ),
        ):
            with self.subTest(phase=phase):
                with self.assertRaises(BoundaryAdmissionError) as raised:
                    admit(
                        self.request(),
                        boundary_id="import_official_foundation",
                        output_root=self.root / f"tree-drift-{suffix}",
                        boundary_inputs=self.request().boundary_inputs,
                        operation_binding=self.request().operation_binding,
                    )
                self.assertEqual(raised.exception.failure_code, expected_code)
                self.assertEqual(raised.exception.failure_phase, phase)

    def test_signed_tree_addition_has_precise_channel_phase(self) -> None:
        (self.input_root / "raw" / "unbound.bin").write_bytes(b"unbound")
        self._assert_tree_rejection_in_object_and_serialized_channels(
            "STAGE_TREE_ADDITION_DETECTED"
        )

    def test_signed_tree_deletion_has_precise_channel_phase(self) -> None:
        (self.input_root / "raw" / "evidence.bin").unlink()
        self._assert_tree_rejection_in_object_and_serialized_channels(
            "STAGE_TREE_DELETION_DETECTED"
        )

    def test_signed_tree_byte_drift_has_precise_channel_phase(self) -> None:
        (self.input_root / "raw" / "evidence.bin").write_bytes(b"changed-same-tree")
        self._assert_tree_rejection_in_object_and_serialized_channels(
            "STAGE_TREE_HASH_MISMATCH"
        )

    def test_materialize_receipt_carries_exact_authenticated_bytes_once(self) -> None:
        verified = admit_boundary(
            self.request(),
            boundary_id="import_official_foundation",
            output_root=self.root / "production-output",
            boundary_inputs=self.request().boundary_inputs,
            operation_binding=self.request().operation_binding,
        )
        staging = self.root / "staging"
        staging.mkdir()
        sidecar = verified.materialize_receipt(staging)
        self.assertEqual(sidecar, staging / SEMANTIC_ADMISSION_FILE)
        self.assertEqual(sidecar.read_bytes(), self.admission_path.read_bytes())
        with self.assertRaises(BoundaryAdmissionError) as raised:
            verified.materialize_receipt(staging)
        self.assertEqual(raised.exception.failure_code, "OUTPUT_ROOT_ALREADY_EXISTS")
        self.assertEqual(raised.exception.failure_phase, "PRE_COMMIT_RECHECK")

    def test_distinct_runtime_authorities_are_mandatory(self) -> None:
        with self.assertRaises(BoundaryAdmissionError) as raised:
            admit_boundary(
                self.request(semantic_key=RUN_KEY),
                boundary_id="import_official_foundation",
                output_root=self.root / "output-authority",
                boundary_inputs=self.request().boundary_inputs,
                operation_binding=self.request().operation_binding,
            )
        self.assertEqual(raised.exception.failure_code, "AUTHORITY_KEYS_NOT_INDEPENDENT")
        self.assertEqual(raised.exception.failure_phase, "ENTRY_PRE_WRITE")

    def test_missing_authority_artifacts_use_required_codes(self) -> None:
        missing = self.root / "missing.json"
        with self.assertRaises(BoundaryAdmissionError) as raised:
            admit_boundary(
                self.request(receipt_path=missing),
                boundary_id="import_official_foundation",
                output_root=self.root / "output-missing-receipt",
                boundary_inputs=self.request().boundary_inputs,
                operation_binding=self.request().operation_binding,
            )
        self.assertEqual(raised.exception.failure_code, "RUN_RECEIPT_REQUIRED")

        for field in ("stage_binding_path", "admission_path"):
            with self.subTest(field=field):
                with self.assertRaises(BoundaryAdmissionError) as raised:
                    admit_boundary(
                        self.request(**{field: missing}),
                        boundary_id="import_official_foundation",
                        output_root=self.root / f"output-missing-{field}",
                        boundary_inputs=self.request().boundary_inputs,
                        operation_binding=self.request().operation_binding,
                    )
                self.assertEqual(
                    raised.exception.failure_code,
                    "STAGE_BINDING_REQUIRED",
                )

    def test_none_authority_paths_use_structured_required_codes(self) -> None:
        for field, expected_code in (
            ("receipt_path", "RUN_RECEIPT_REQUIRED"),
            ("stage_binding_path", "STAGE_BINDING_REQUIRED"),
        ):
            with self.subTest(field=field):
                request = self.request(**{field: None})
                with self.assertRaises(BoundaryAdmissionError) as raised:
                    admit_boundary(
                        request,
                        boundary_id="import_official_foundation",
                        output_root=self.root / f"output-none-{field}",
                        boundary_inputs=request.boundary_inputs,
                        operation_binding=request.operation_binding,
                    )
                self.assertEqual(raised.exception.failure_code, expected_code)
                self.assertEqual(
                    raised.exception.failure_phase,
                    "ENTRY_PRE_WRITE",
                )

    def test_wrapper_cannot_substitute_different_boundary_inputs(self) -> None:
        with self.assertRaises(BoundaryAdmissionError) as raised:
            admit_boundary(
                self.request(),
                boundary_id="import_status_corporate",
                output_root=self.root / "output-wrong-stage",
                boundary_inputs={
                    "official_foundation_root": self.input_root,
                    "workspace": self.input_root,
                },
                operation_binding=build_boundary_operation_binding(
                    "import_status_corporate",
                    decision_at=DECISION_AT,
                ),
            )
        self.assertEqual(raised.exception.failure_code, "STAGE_ARTIFACT_INVENTORY_MISMATCH")

    def test_claim_promotion_is_rejected_with_stable_code(self) -> None:
        payload = json.loads(self.admission_path.read_text(encoding="utf-8"))
        payload["claims"]["full_market"] = True
        # Re-sign to prove that a correctly authenticated authority still cannot
        # weaken a claim boundary.
        authentication = payload["authentication"]
        authenticated = {
            "document": {key: value for key, value in payload.items() if key != "authentication"},
            "algorithm": authentication["algorithm"],
            "key_id": authentication["key_id"],
        }
        import hashlib
        import hmac

        authentication["tag"] = hmac.new(
            SEMANTIC_KEY, canonical_json_bytes(authenticated), hashlib.sha256
        ).hexdigest()
        self.admission_path.write_bytes(canonical_json_bytes(payload))
        with self.assertRaises(BoundaryAdmissionError) as raised:
            admit_boundary(
                self.request(),
                boundary_id="import_official_foundation",
                output_root=self.root / "output-full-market",
                boundary_inputs=self.request().boundary_inputs,
                operation_binding=self.request().operation_binding,
            )
        self.assertEqual(raised.exception.failure_code, "FULL_MARKET_CLAIM_FORBIDDEN")

    def test_input_tree_drift_and_output_race_fail_precommit(self) -> None:
        token = admit_boundary(
            self.request(),
            boundary_id="import_official_foundation",
            output_root=self.root / "output-drift",
            boundary_inputs=self.request().boundary_inputs,
            operation_binding=self.request().operation_binding,
        )
        (self.input_root / "raw" / "evidence.bin").write_bytes(b"changed")
        with self.assertRaises(BoundaryAdmissionError) as raised:
            token.revalidate_before_commit()
        self.assertEqual(
            raised.exception.failure_code,
            "STAGE_TREE_HASH_MISMATCH",
        )
        self.assertEqual(raised.exception.failure_phase, "PRE_COMMIT_RECHECK")

    def test_predecessor_lineage_addition_is_rejected_by_precommit_tree_recheck(
        self,
    ) -> None:
        token = admit_boundary(
            self.request(),
            boundary_id="import_official_foundation",
            output_root=self.root / "output-lineage-drift",
            boundary_inputs=self.request().boundary_inputs,
            operation_binding=self.request().operation_binding,
        )
        lineage = self.input_root / "reports" / "tri_security_lineage.json"
        lineage.parent.mkdir()
        lineage.write_bytes(b"post-admission-lineage-tamper")
        with self.assertRaises(BoundaryAdmissionError) as raised:
            token.revalidate_before_commit()
        self.assertEqual(
            raised.exception.failure_code,
            "STAGE_TREE_ADDITION_DETECTED",
        )
        self.assertEqual(raised.exception.failure_phase, "PRE_COMMIT_RECHECK")

    def test_mid_snapshot_tree_race_keeps_generic_precommit_code(self) -> None:
        token = admit_boundary(
            self.request(),
            boundary_id="import_official_foundation",
            output_root=self.root / "output-mid-snapshot-race",
            boundary_inputs=self.request().boundary_inputs,
            operation_binding=self.request().operation_binding,
        )
        with patch(
            "kubo.tri_security_admission.snapshot_regular_tree",
            side_effect=ValueError(
                "semantic admission input tree changed while being snapshotted"
            ),
        ):
            with self.assertRaises(BoundaryAdmissionError) as raised:
                token.revalidate_before_commit()
        self.assertEqual(
            raised.exception.failure_code,
            "STAGE_TREE_CHANGED_DURING_VERIFICATION",
        )
        self.assertEqual(raised.exception.failure_phase, "PRE_COMMIT_RECHECK")

    def test_typed_snapshot_change_uses_structured_entry_code(self) -> None:
        request = self.request()
        with patch(
            "kubo.tri_security_admission.snapshot_regular_tree",
            side_effect=TreeSnapshotChangedError(
                "semantic admission input tree changed while being snapshotted"
            ),
        ):
            with self.assertRaises(BoundaryAdmissionError) as raised:
                admit_boundary(
                    request,
                    boundary_id="import_official_foundation",
                    output_root=self.root / "output-entry-snapshot-race",
                    boundary_inputs=request.boundary_inputs,
                    operation_binding=request.operation_binding,
                )
        self.assertEqual(
            raised.exception.failure_code,
            "STAGE_TREE_CHANGED_DURING_VERIFICATION",
        )
        self.assertEqual(raised.exception.failure_phase, "ENTRY_PRE_WRITE")

    def test_output_creation_after_admission_is_a_precommit_change(self) -> None:
        output = self.root / "output-race"
        token = admit_boundary(
            self.request(),
            boundary_id="import_official_foundation",
            output_root=output,
            boundary_inputs=self.request().boundary_inputs,
            operation_binding=self.request().operation_binding,
        )
        output.mkdir()
        with self.assertRaises(BoundaryAdmissionError) as raised:
            token.revalidate_before_commit()
        self.assertEqual(raised.exception.failure_code, "OUTPUT_ROOT_CHANGED_DURING_COMMIT")
        self.assertEqual(raised.exception.failure_phase, "PRE_COMMIT_RECHECK")

    def test_predecessor_paths_must_be_fixed_sidecars_of_bound_roots(self) -> None:
        upstream = self.root / "upstream-official-output"
        upstream.mkdir()
        fixed_sidecar = upstream / SEMANTIC_ADMISSION_FILE
        fixed_sidecar.write_bytes(self.admission_path.read_bytes())

        with self.assertRaises(BoundaryAdmissionError) as raised:
            issue_semantic_boundary_admission(
                output_path=self.root / "status-corporate-admission.json",
                **self.issue_arguments(
                    boundary_id="import_status_corporate",
                    v1_stage_report={**self.stage.report(), "stage_id": "STATUS_CORPORATE"},
                    boundary_inputs={
                        "official_foundation_root": upstream,
                        "workspace": self.input_root,
                    },
                    predecessor_admission_paths=(self.admission_path,),
                    admission_id="status-corporate-mix-and-match",
                    operation_binding=build_boundary_operation_binding(
                        "import_status_corporate",
                        decision_at=DECISION_AT,
                    ),
                ),
            )
        self.assertEqual(raised.exception.failure_code, "PREDECESSOR_STAGE_MISMATCH")

        report = issue_semantic_boundary_admission(
            output_path=self.root / "status-corporate-fixed-admission.json",
            **self.issue_arguments(
                boundary_id="import_status_corporate",
                v1_stage_report={**self.stage.report(), "stage_id": "STATUS_CORPORATE"},
                boundary_inputs={
                    "official_foundation_root": upstream,
                    "workspace": self.input_root,
                },
                predecessor_admission_paths=(fixed_sidecar,),
                admission_id="status-corporate-fixed-sidecar",
                operation_binding=build_boundary_operation_binding(
                    "import_status_corporate",
                    decision_at=DECISION_AT,
                ),
            ),
        )
        self.assertEqual(report["status"], "PASS")

    def test_installed_predecessor_sidecar_is_rechecked_when_admitted(self) -> None:
        upstream = self.root / "admitted-official-output"
        upstream.mkdir()
        fixed_sidecar = upstream / SEMANTIC_ADMISSION_FILE
        fixed_sidecar.write_bytes(self.admission_path.read_bytes())
        status_admission_path = self.root / "status-corporate-admission-valid.json"
        issue_semantic_boundary_admission(
            output_path=status_admission_path,
            **self.issue_arguments(
                boundary_id="import_status_corporate",
                v1_stage_report={**self.stage.report(), "stage_id": "STATUS_CORPORATE"},
                boundary_inputs={
                    "official_foundation_root": upstream,
                    "workspace": self.input_root,
                },
                predecessor_admission_paths=(fixed_sidecar,),
                admission_id="status-corporate-fixed-sidecar-admit",
                operation_binding=build_boundary_operation_binding(
                    "import_status_corporate",
                    decision_at=DECISION_AT,
                ),
            ),
        )
        request = self.request(
            admission_path=status_admission_path,
            boundary_inputs={
                "official_foundation_root": upstream,
                "workspace": self.input_root,
            },
            predecessor_admission_paths=(fixed_sidecar,),
            operation_binding=build_boundary_operation_binding(
                "import_status_corporate",
                decision_at=DECISION_AT,
            ),
        )
        # This fixture deliberately reuses the official v1 binding, so admission
        # advances through the fixed predecessor proof and then fails at the v1
        # current-stage binding rather than trusting an authority-store path.
        with self.assertRaises(BoundaryAdmissionError) as raised:
            admit_boundary(
                request,
                boundary_id="import_status_corporate",
                output_root=self.root / "status-corporate-output",
                boundary_inputs=request.boundary_inputs,
                operation_binding=request.operation_binding,
            )
        self.assertEqual(raised.exception.failure_code, "STAGE_BINDING_STAGE_ID_MISMATCH")

    def test_unknown_field_or_existing_output_fails_before_write(self) -> None:
        payload = json.loads(self.admission_path.read_text(encoding="utf-8"))
        payload["unknown"] = True
        self.admission_path.write_bytes(canonical_json_bytes(payload))
        with self.assertRaises(BoundaryAdmissionError) as raised:
            admit_boundary(
                self.request(),
                boundary_id="import_official_foundation",
                output_root=self.root / "output-unknown",
                boundary_inputs=self.request().boundary_inputs,
                operation_binding=self.request().operation_binding,
            )
        self.assertEqual(raised.exception.failure_code, "STAGE_BINDING_SCHEMA_INVALID")

        output = self.root / "existing-output"
        output.mkdir()
        with self.assertRaises(BoundaryAdmissionError) as raised:
            admit_boundary(
                self.request(),
                boundary_id="import_official_foundation",
                output_root=output,
                boundary_inputs=self.request().boundary_inputs,
                operation_binding=self.request().operation_binding,
            )
        self.assertEqual(raised.exception.failure_code, "OUTPUT_ROOT_ALREADY_EXISTS")

    def test_issue_requires_safe_existing_disjoint_parent_without_side_effects(self) -> None:
        missing_parent = self.root / "missing-parent"
        with self.assertRaises(BoundaryAdmissionError) as raised:
            issue_semantic_boundary_admission(
                output_path=missing_parent / "admission.json",
                **self.issue_arguments(admission_id="missing-parent-admission"),
            )
        self.assertEqual(raised.exception.failure_code, "UNSAFE_STAGE_ENTRY")
        self.assertFalse(missing_parent.exists())

        nested_output = self.input_root / "nested-admission.json"
        with self.assertRaises(BoundaryAdmissionError) as raised:
            issue_semantic_boundary_admission(
                output_path=nested_output,
                **self.issue_arguments(admission_id="overlap-admission"),
            )
        self.assertEqual(raised.exception.failure_code, "STAGE_ROOT_NOT_DISJOINT")
        self.assertFalse(nested_output.exists())

        real_parent = self.root / "real-parent"
        real_parent.mkdir()
        alias_parent = self.root / "alias-parent"
        try:
            alias_parent.symlink_to(real_parent, target_is_directory=True)
        except (NotImplementedError, OSError):
            return
        alias_output = alias_parent / "admission.json"
        with self.assertRaises(BoundaryAdmissionError) as raised:
            issue_semantic_boundary_admission(
                output_path=alias_output,
                **self.issue_arguments(admission_id="alias-parent-admission"),
            )
        self.assertEqual(raised.exception.failure_code, "UNSAFE_STAGE_ENTRY")
        self.assertFalse((real_parent / "admission.json").exists())


if __name__ == "__main__":
    unittest.main()
