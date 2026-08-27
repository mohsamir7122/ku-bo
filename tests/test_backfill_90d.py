from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from jsonschema import Draft202012Validator, FormatChecker

from kubo.backfill_90d import (
    PACKAGE_NAME,
    REQUIRED_FILES,
    build_rights_aware_bundle,
    validate_backfill_policy,
    validate_rights_aware_bundle,
)
from kubo.priority_runtime import BlockedCheckpointStore

from tests.backfill_90d_helpers import (
    CODE_SHA,
    FINISHED_AT,
    ROOT,
    build_fixture_bundle,
    make_receipt,
    read_json,
    read_jsonl,
)


def _validate(schema_name: str, value: object) -> None:
    schema = read_json(ROOT / "schemas" / schema_name)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(value)


class RightsAwareBackfillTests(unittest.TestCase):
    def test_policy_is_exact_and_schema_valid(self) -> None:
        policy = read_json(ROOT / "config/rights-aware-backfill-policy.json")
        _validate("rights-aware-backfill-policy.schema.json", policy)
        report = validate_backfill_policy(ROOT)
        self.assertEqual(report["status"], "PASS_FAIL_CLOSED_BACKFILL_POLICY")
        self.assertEqual(report["package_name"], PACKAGE_NAME)
        self.assertEqual(report["required_source_count"], 11)
        self.assertEqual(report["required_independence_group_count"], 11)
        self.assertEqual(report["planned_date_shard_count"], 990)
        self.assertEqual(
            report["production_checkpoint_store_status"],
            "BLOCKED_CHECKPOINT_STORE",
        )

    def test_blocked_receipt_builds_reopenable_incomplete_package(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle, report = build_fixture_bundle(Path(directory))
            self.assertEqual(set(REQUIRED_FILES), {path.name for path in bundle.iterdir() if path.is_file()})
            attempts = read_jsonl(bundle / "source-attempts.jsonl")
            blocked = read_jsonl(bundle / "blocked-records.jsonl")
            coverage = read_json(bundle / "coverage-report.json")
            manifest = read_json(bundle / "run-manifest.json")
            _validate("rights-aware-source-attempt.schema.json", attempts[0])
            _validate("rights-aware-blocked-record.schema.json", blocked[0])
            _validate("rights-aware-coverage-report.schema.json", coverage)
            _validate("rights-aware-backfill-manifest.schema.json", manifest)
            reopened = validate_rights_aware_bundle(ROOT, bundle)

        self.assertEqual(report, reopened)
        self.assertEqual(report["research_network_status"], "SOFTWARE_OPERATIONAL_ABSTAIN")
        self.assertEqual(report["strict_forecast_status"], "LOCKED")
        self.assertFalse(report["scheduled_workflows_active"])
        self.assertEqual(attempts[0]["classification"], "BLOCKED_ACCESS")
        self.assertEqual(attempts[0]["source_role"], "OFFICIAL_PRIMARY")
        self.assertEqual(blocked[0]["retry_allowed_in_same_run"], False)
        self.assertEqual(coverage["counts"]["source_attempts"], 1)
        self.assertEqual(coverage["counts"]["blocked_sources"], 1)
        self.assertEqual(coverage["counts"]["planned_date_shards"], 990)
        self.assertEqual(coverage["counts"]["blocked_before_fetch_date_shards"], 90)
        self.assertEqual(coverage["counts"]["unattempted_date_shards"], 900)
        self.assertEqual(coverage["counts"]["real_observations"], 0)
        self.assertEqual(coverage["counts"]["unique_events"], 0)
        self.assertEqual(coverage["counts"]["training_candidates"], 0)
        self.assertEqual(coverage["classification_counts"]["BLOCKED_ACCESS"], 2)
        self.assertEqual(manifest["package_status"], PACKAGE_NAME)
        self.assertFalse(manifest["claim_boundaries"]["training_allowed"])

    def test_readable_probe_remains_unverified_and_creates_no_observation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            receipt = make_receipt(root, readable=True)
            bundle, report = build_fixture_bundle(root, receipt_bindings=[receipt])
            attempt = read_jsonl(bundle / "source-attempts.jsonl")[0]
            coverage = read_json(bundle / "coverage-report.json")
            embedded_probe = bundle / attempt["probe_path"]
            probe = read_json(embedded_probe)
            raw_relative = Path(probe["sources"][0]["artifact"]["path"])

            self.assertTrue((embedded_probe.parent / raw_relative).is_file())
            self.assertEqual(attempt["classification"], "UNVERIFIED")
            self.assertIsNotNone(attempt["artifact"])
            self.assertEqual(coverage["counts"]["readable_raw_artifacts"], 1)
            self.assertEqual(coverage["counts"]["unverified_date_shards"], 90)
            self.assertEqual(read_jsonl(bundle / "provenance-records.jsonl"), [])
            self.assertEqual(read_jsonl(bundle / "research-context-90d.jsonl"), [])
            self.assertEqual(read_jsonl(bundle / "training-candidates.jsonl"), [])
            self.assertEqual(report["strict_forecast_status"], "LOCKED")

    def test_archive_alias_counts_once_in_boursa_denominator_group(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            receipts = [
                make_receipt(root, source_id="boursa_reports_archive"),
                make_receipt(root, source_id="kcc_maqasa_official"),
            ]
            bundle, _report = build_fixture_bundle(
                root,
                receipt_bindings=receipts,
            )
            coverage = read_json(bundle / "coverage-report.json")
        self.assertEqual(coverage["counts"]["source_attempts"], 2)
        self.assertEqual(coverage["counts"]["attempted_denominator_sources"], 2)
        self.assertEqual(
            coverage["counts"]["blocked_before_fetch_date_shards"],
            180,
        )
        self.assertEqual(coverage["counts"]["unattempted_date_shards"], 810)

    def test_empty_receipt_set_is_truthfully_missing_not_collected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle, report = build_fixture_bundle(root, receipt_bindings=[])
            coverage = read_json(bundle / "coverage-report.json")
        self.assertEqual(report["counts"]["source_attempts"], 0)
        self.assertEqual(coverage["counts"]["unattempted_date_shards"], 990)
        self.assertEqual(coverage["counts"]["completed_date_shards"], 0)
        self.assertEqual(coverage["counts"]["real_observations"], 0)

    def test_production_requires_durable_checkpoint_store(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            receipt = make_receipt(root)
            with self.assertRaises(BlockedCheckpointStore):
                build_rights_aware_bundle(
                    ROOT,
                    root / "production",
                    run_id="production-fixture",
                    code_sha=CODE_SHA,
                    scheduled_at="2026-08-27T03:00:00Z",
                    actual_started_at="2026-08-27T03:01:00Z",
                    finished_at=FINISHED_AT,
                    receipt_bindings=[receipt],
                    production=True,
                )
            self.assertFalse((root / "production").exists())


if __name__ == "__main__":
    unittest.main()
