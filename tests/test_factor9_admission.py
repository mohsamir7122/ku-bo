from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover
    Draft202012Validator = None

from kubo.factor9_admission import (
    EXPECTED_BLOCKERS,
    EXPECTED_GATES,
    Factor9AdmissionError,
    validate_factor9_admission_manifest,
    write_factor9_admission_report,
)


ROOT = Path(__file__).resolve().parents[1]
ROLES = [
    "RAW_PRICE_FILES",
    "CLEAN_PRICE_FILE",
    "EXCLUDED_ROW_FILE",
    "FAILURE_LEDGER",
    "COMPANY_MASTER",
    "PRICE_FACTOR_OUTPUTS",
    "EVENT_LIBRARY",
    "REVIEW_QUEUE",
]
SAMPLE_COUNTS = {
    "company_master_rows": 4,
    "price_tickers": 3,
    "original_price_rows": 100,
    "clean_price_rows": 98,
    "excluded_price_rows": 2,
    "reported_validation_issues": 7,
}


def _materialize_artifacts(root: Path, payload: dict[str, object]) -> None:
    digests: list[str] = []
    for row in payload["artifacts"]:
        logical = row["logical_path"]
        if (
            not isinstance(logical, str)
            or not logical.startswith("PRIVATE_INVENTORY/")
            or ".." in Path(logical).parts
            or "\\" in logical
        ):
            continue
        relative = Path(*Path(logical).parts[1:])
        try:
            number = int(relative.stem)
        except ValueError:
            number = len(digests)
        content = bytes([(number % 250) + 1]) * (number + 1)
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        digest = hashlib.sha256(content).hexdigest()
        default_digest = f"{number + 1:064x}"
        if row["sha256"] == default_digest:
            row["sha256"] = digest
        if row["size_bytes"] == number + 1:
            row["size_bytes"] = len(content)
        digests.append(digest)
    if digests:
        for index, row in enumerate(payload["gates"]):
            if row["status"] == "PASS" and row["evidence_sha256"] == [f"{100 + index:064x}"]:
                row["evidence_sha256"] = [digests[index % len(digests)]]
        for index, row in enumerate(payload["blockers"]):
            if row["status"] == "RESOLVED" and row["evidence_sha256"] == [f"{200 + index:064x}"]:
                row["evidence_sha256"] = [digests[index % len(digests)]]


def _manifest(*, admitted: bool = False) -> dict[str, object]:
    rights = "LICENSED" if admitted else "REQUIRES_RUNTIME_REVIEW"
    point_in_time = "PROVEN" if admitted else "UNPROVEN"
    review = "APPROVED" if admitted else "REVIEW_REQUIRED"
    return {
        "schema_version": "1.0",
        "inventory_id": "factor9-inventory-20260825",
        "generated_at": "2026-08-25T12:00:00+03:00",
        "asset": {
            "status": "RESEARCH_ASSET_PENDING_ADMISSION",
            "promotion_ceiling": "RESEARCH_INPUT_ONLY",
        },
        "counts": dict(SAMPLE_COUNTS),
        "artifacts": [
            {
                "logical_path": f"PRIVATE_INVENTORY/factor9/{index:02d}.bin",
                "sha256": f"{index + 1:064x}",
                "size_bytes": index + 1,
                "artifact_role": role,
                "original_source": "MUBASHER_SECONDARY",
                "capture_method": "HISTORICAL_PROJECT_ARTIFACT",
                "rights_status": rights,
                "point_in_time_status": point_in_time,
                "review_status": review,
                "duplicate_disposition": "CANONICAL_CANDIDATE",
            }
            for index, role in enumerate(ROLES)
        ],
        "gates": [
            {
                "gate_id": gate,
                "status": "PASS" if admitted else "NOT_REVIEWED",
                "evidence_sha256": [f"{100 + index:064x}"] if admitted else [],
            }
            for index, gate in enumerate(EXPECTED_GATES)
        ],
        "blockers": [
            {
                "blocker_id": blocker,
                "status": "RESOLVED" if admitted else "OPEN",
                "evidence_sha256": [f"{200 + index:064x}"] if admitted else [],
            }
            for index, blocker in enumerate(EXPECTED_BLOCKERS)
        ],
        "claim_boundaries": {
            "storage_presence_grants_rights": False,
            "asset_is_training_truth": False,
            "asset_is_validated_model": False,
            "probability_allowed": False,
            "recommendation_allowed": False,
            "automatic_promotion_allowed": False,
        },
    }


class Factor9AdmissionTests(unittest.TestCase):
    def _validate(self, payload: object, after_materialize=None) -> dict[str, object]:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            artifact_root = base / "artifacts"
            artifact_root.mkdir()
            materialized = deepcopy(payload)
            if isinstance(materialized, dict) and isinstance(materialized.get("artifacts"), list):
                _materialize_artifacts(artifact_root, materialized)
            if after_materialize is not None:
                after_materialize(artifact_root, materialized)
            path = base / "manifest.json"
            path.write_text(json.dumps(materialized), encoding="utf-8")
            return validate_factor9_admission_manifest(path, artifact_root)

    def test_pending_manifest_reconciles_counts(self) -> None:
        report = self._validate(_manifest())
        self.assertEqual(report["status"], "RESEARCH_ASSET_PENDING_ADMISSION")
        self.assertEqual(report["counts"]["reported_validation_issues"], 7)
        self.assertEqual(
            report["counts"]["original_price_rows"] - report["counts"]["clean_price_rows"],
            report["counts"]["excluded_price_rows"],
        )
        self.assertFalse(report["model_training_allowed"])

    def test_fully_reviewed_manifest_reaches_research_input_only(self) -> None:
        report = self._validate(_manifest(admitted=True))
        self.assertEqual(report["status"], "ADMITTED_RESEARCH_INPUT_ONLY")
        self.assertTrue(report["admission_allowed"])
        self.assertEqual(report["promotion_ceiling"], "RESEARCH_INPUT_ONLY")
        self.assertEqual(report["artifact_integrity_status"], "PASS_REOPENED_AND_HASHED")
        self.assertEqual(report["reopened_artifact_count"], len(ROLES))

    def test_schema_accepts_manifest(self) -> None:
        if Draft202012Validator is None:
            self.skipTest("jsonschema unavailable")
        schema = json.loads(
            (ROOT / "schemas/factor9-admission-manifest.schema.json").read_text(encoding="utf-8")
        )
        Draft202012Validator.check_schema(schema)
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(_manifest())), [])

    def test_issue_flags_cannot_replace_excluded_row_count(self) -> None:
        payload = _manifest()
        payload["counts"]["excluded_price_rows"] = payload["counts"][
            "reported_validation_issues"
        ]
        with self.assertRaises(Factor9AdmissionError):
            self._validate(payload)

    def test_unreconciled_count_rejected(self) -> None:
        payload = _manifest()
        payload["counts"]["clean_price_rows"] -= 1
        with self.assertRaises(Factor9AdmissionError):
            self._validate(payload)

    def test_private_drive_url_rejected(self) -> None:
        payload = _manifest()
        payload["artifacts"][0]["logical_path"] = "https://example.invalid/private"
        with self.assertRaises(Factor9AdmissionError):
            self._validate(payload)

    def test_path_escape_rejected(self) -> None:
        payload = _manifest()
        payload["artifacts"][0]["logical_path"] = "PRIVATE_INVENTORY/../secret.bin"
        with self.assertRaises(Factor9AdmissionError):
            self._validate(payload)

    def test_duplicate_path_rejected(self) -> None:
        payload = _manifest()
        payload["artifacts"][1]["logical_path"] = payload["artifacts"][0]["logical_path"]
        with self.assertRaises(Factor9AdmissionError):
            self._validate(payload)

    def test_duplicate_hash_without_quarantine_rejected(self) -> None:
        payload = _manifest()
        payload["artifacts"][1]["sha256"] = payload["artifacts"][0]["sha256"]
        with self.assertRaises(Factor9AdmissionError):
            self._validate(payload)

    def test_uppercase_and_non_string_hashes_are_rejected(self) -> None:
        payload = _manifest()
        payload["artifacts"][0]["sha256"] = "A" * 64
        with self.assertRaises(Factor9AdmissionError):
            self._validate(payload)

        payload = _manifest()
        payload["gates"][0]["evidence_sha256"] = [{}]
        with self.assertRaises(Factor9AdmissionError):
            self._validate(payload)

    def test_missing_artifact_role_stays_pending(self) -> None:
        payload = _manifest(admitted=True)
        payload["artifacts"].pop()
        report = self._validate(payload)
        self.assertEqual(report["status"], "RESEARCH_ASSET_PENDING_ADMISSION")
        self.assertEqual(report["missing_artifact_roles"], ["REVIEW_QUEUE"])

    def test_gate_reordering_rejected(self) -> None:
        payload = _manifest()
        payload["gates"][0], payload["gates"][1] = payload["gates"][1], payload["gates"][0]
        with self.assertRaises(Factor9AdmissionError):
            self._validate(payload)

    def test_pass_gate_requires_hash_evidence(self) -> None:
        payload = _manifest()
        payload["gates"][0]["status"] = "PASS"
        with self.assertRaises(Factor9AdmissionError):
            self._validate(payload)

    def test_resolved_blocker_requires_hash_evidence(self) -> None:
        payload = _manifest()
        payload["blockers"][0]["status"] = "RESOLVED"
        with self.assertRaises(Factor9AdmissionError):
            self._validate(payload)

    def test_unknown_rights_remains_pending(self) -> None:
        payload = _manifest(admitted=True)
        payload["artifacts"][0]["rights_status"] = "UNKNOWN"
        report = self._validate(payload)
        self.assertFalse(report["admission_allowed"])

    def test_missing_or_changed_artifact_is_rejected(self) -> None:
        def remove_first(root: Path, payload: dict[str, object]) -> None:
            (root / "factor9" / "00.bin").unlink()

        with self.assertRaisesRegex(Factor9AdmissionError, "cannot reopen"):
            self._validate(_manifest(), remove_first)

        def change_first(root: Path, payload: dict[str, object]) -> None:
            (root / "factor9" / "00.bin").write_bytes(b"changed")

        with self.assertRaisesRegex(Factor9AdmissionError, "mismatch"):
            self._validate(_manifest(), change_first)

    def test_symlink_artifact_is_rejected(self) -> None:
        def replace_with_symlink(root: Path, payload: dict[str, object]) -> None:
            target = root / "outside.bin"
            target.write_bytes(b"outside")
            artifact = root / "factor9" / "00.bin"
            artifact.unlink()
            artifact.symlink_to(target)

        try:
            with self.assertRaisesRegex(Factor9AdmissionError, "cannot reopen"):
                self._validate(_manifest(), replace_with_symlink)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")

    def test_passed_gate_must_reference_a_reopened_artifact(self) -> None:
        def forge_evidence(root: Path, payload: dict[str, object]) -> None:
            payload["gates"][0]["evidence_sha256"] = ["f" * 64]

        with self.assertRaisesRegex(Factor9AdmissionError, "reopened manifest artifact"):
            self._validate(_manifest(admitted=True), forge_evidence)

    def test_report_is_no_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = root / "manifest.json"
            artifact_root = root / "artifacts"
            artifact_root.mkdir()
            output = root / "report.json"
            payload = _manifest()
            _materialize_artifacts(artifact_root, payload)
            manifest.write_text(json.dumps(payload), encoding="utf-8")
            write_factor9_admission_report(manifest, artifact_root, output)
            with self.assertRaises(Factor9AdmissionError):
                write_factor9_admission_report(manifest, artifact_root, output)

    def test_duplicate_json_key_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "manifest.json"
            artifact_root = Path(temporary) / "artifacts"
            artifact_root.mkdir()
            path.write_text('{"schema_version":"1.0","schema_version":"1.0"}', encoding="utf-8")
            with self.assertRaises(Factor9AdmissionError):
                validate_factor9_admission_manifest(path, artifact_root)


if __name__ == "__main__":
    unittest.main()
