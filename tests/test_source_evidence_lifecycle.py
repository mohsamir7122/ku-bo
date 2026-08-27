from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from jsonschema import Draft202012Validator, FormatChecker

from kubo.cli_v3 import main as cli_main
from kubo.source_evidence_lifecycle import (
    INPUT_SCHEMA_VERSION,
    REPORT_SCHEMA_VERSION,
    SourceEvidenceLifecycleError,
    load_source_evidence_document,
    reconcile_source_evidence,
    validate_source_attempt,
    write_reconciliation_report,
)


ROOT = Path(__file__).resolve().parents[1]
H1 = "1" * 64
H2 = "2" * 64
H3 = "3" * 64
F1 = "a" * 64
F2 = "b" * 64


def attempt(
    *,
    attempt_id: str = "a1",
    source_id: str = "exchange",
    publisher: str = "Official Exchange",
    source_family: str = "exchange",
    source_url: str = "https://example.test/exchange",
    started_at: str = "2026-08-03T13:24:00+03:00",
    finished_at: str = "2026-08-03T13:25:00+03:00",
    raw_sha256: str | None = H1,
    **changes: object,
) -> dict[str, object]:
    row: dict[str, object] = {
        "attempt_id": attempt_id,
        "source_id": source_id,
        "publisher": publisher,
        "source_family": source_family,
        "source_url": source_url,
        "access_mode": "OFFICIAL_DOWNLOAD",
        "started_at": started_at,
        "finished_at": finished_at,
        "http_status": 200,
        "outcome": "COLLECTED",
        "content_class": "DATA",
        "qualified_rows": 1,
        "byte_count": 100,
        "raw_sha256": raw_sha256,
        "parser_version": "parser-v1",
        "schema_fingerprint": F1,
        "expected_schema_fingerprint": F1,
        "rights_status": "PERMITTED",
        "robots_status": "ALLOWED",
    }
    row.update(changes)
    return row


def observation(
    *,
    observation_id: str = "o1",
    attempt_id: str = "a1",
    source_id: str = "exchange",
    publisher: str = "Official Exchange",
    source_family: str = "exchange",
    source_url: str = "https://example.test/exchange",
    raw_sha256: str = H1,
    origin_id: str = "exchange-original",
    source_record_id: str = "record-1",
    value: object = 100,
    published_at: str = "2026-08-03T13:20:00+03:00",
    available_at: str = "2026-08-03T13:20:00+03:00",
    retrieved_at: str = "2026-08-03T13:25:00+03:00",
    **changes: object,
) -> dict[str, object]:
    row: dict[str, object] = {
        "observation_id": observation_id,
        "attempt_id": attempt_id,
        "artifact_id": f"artifact-{attempt_id}",
        "source_id": source_id,
        "publisher": publisher,
        "source_family": source_family,
        "origin_id": origin_id,
        "source_record_id": source_record_id,
        "entity_id": "SYN1",
        "field_name": "close_fils",
        "value": value,
        "unit": "FILS",
        "effective_at": "2026-08-03T13:15:00+03:00",
        "published_at": published_at,
        "available_at": available_at,
        "retrieved_at": retrieved_at,
        "availability_evidence_status": "CAPTURED_BEFORE_CUTOFF",
        "revision": 1,
        "source_grade": "A",
        "verification_status": "CONFIRMED",
        "evidence_role": "EXCHANGE_OFFICIAL",
        "source_url": source_url,
        "raw_sha256": raw_sha256,
        "parser_version": "parser-v1",
    }
    row.update(changes)
    return row


def second_attempt(**changes: object) -> dict[str, object]:
    defaults: dict[str, object] = {
        "attempt_id": "a2",
        "source_id": "issuer",
        "publisher": "Issuer",
        "source_family": "issuer",
        "source_url": "https://issuer.example.test/data",
        "started_at": "2026-08-03T13:26:00+03:00",
        "finished_at": "2026-08-03T13:27:00+03:00",
        "raw_sha256": H2,
    }
    defaults.update(changes)
    return attempt(**defaults)


def second_observation(**changes: object) -> dict[str, object]:
    defaults: dict[str, object] = {
        "observation_id": "o2",
        "attempt_id": "a2",
        "source_id": "issuer",
        "publisher": "Issuer",
        "source_family": "issuer",
        "source_url": "https://issuer.example.test/data",
        "raw_sha256": H2,
        "origin_id": "issuer-original",
        "source_record_id": "issuer-record-1",
        "published_at": "2026-08-03T13:21:00+03:00",
        "available_at": "2026-08-03T13:21:00+03:00",
        "retrieved_at": "2026-08-03T13:27:00+03:00",
        "evidence_role": "ISSUER_PRIMARY",
    }
    defaults.update(changes)
    return observation(**defaults)


def document(
    *,
    attempts: list[dict[str, object]] | None = None,
    observations: list[dict[str, object]] | None = None,
    **changes: object,
) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": INPUT_SCHEMA_VERSION,
        "evidence_class": "SYNTHETIC_FIXTURE",
        "capture_mode": "PROSPECTIVE",
        "decision_at": "2026-08-03T14:00:00+03:00",
        "max_zero_yield_attempts_per_family": 2,
        "critical_fields": ["close_fils"],
        "expected_cells": [
            {
                "entity_id": "SYN1",
                "field_name": "close_fils",
                "effective_at": "2026-08-03T13:15:00+03:00",
            }
        ],
        "attempts": [attempt()] if attempts is None else attempts,
        "observations": [observation()] if observations is None else observations,
    }
    value.update(changes)
    return value


class SourceEvidenceLifecycleTests(unittest.TestCase):
    def test_clean_reconciliation_is_structural_only(self) -> None:
        report = reconcile_source_evidence(document())
        self.assertEqual(report["schema_version"], REPORT_SCHEMA_VERSION)
        self.assertEqual(report["evidence_class"], "SYNTHETIC_FIXTURE")
        self.assertEqual(report["status"], "STRUCTURE_AND_RECONCILIATION_VALID_ONLY")
        self.assertEqual(report["quality"]["data_coverage_score"], 1.0)
        self.assertEqual(report["accepted"][0]["fact_status"], "confirmed")
        self.assertFalse(report["claim_boundaries"]["model_fitting_permitted"])
        self.assertFalse(report["claim_boundaries"]["recommendation_permitted"])

    def test_source_failure_does_not_erase_unaffected_evidence(self) -> None:
        blocked = second_attempt(
            http_status=403,
            outcome="BLOCKED_ACCESS",
            content_class="ACCESS_DENIED",
            qualified_rows=0,
            byte_count=0,
            raw_sha256=None,
            schema_fingerprint=None,
            expected_schema_fingerprint=None,
            rights_status="UNKNOWN",
            robots_status="UNKNOWN",
        )
        report = reconcile_source_evidence(document(attempts=[attempt(), blocked]))
        self.assertEqual(report["status"], "DEGRADED_STRUCTURE_VALID_ONLY")
        self.assertEqual(report["quality"]["resolved_expected_cell_count"], 1)
        self.assertEqual(report["attempt_summary"]["source_failure_count"], 1)

    def test_403_cannot_be_relabelled_as_collected(self) -> None:
        invalid = attempt(http_status=403)
        report = reconcile_source_evidence(document(attempts=[invalid]))
        self.assertEqual(report["status"], "BLOCKED")
        self.assertTrue(
            any("401/403" in item["detail"] for item in report["quarantine"])
        )

    def test_blocked_bytes_cannot_enter_evidence(self) -> None:
        with self.assertRaisesRegex(
            SourceEvidenceLifecycleError,
            "cannot enter evidence",
        ):
            validate_source_attempt(
                attempt(
                    http_status=403,
                    outcome="BLOCKED_ACCESS",
                    content_class="ACCESS_DENIED",
                    qualified_rows=0,
                    byte_count=10,
                    raw_sha256=H1,
                    schema_fingerprint=None,
                    expected_schema_fingerprint=None,
                    rights_status="UNKNOWN",
                    robots_status="UNKNOWN",
                )
            )

    def test_failure_outcome_cannot_pose_as_data(self) -> None:
        with self.assertRaisesRegex(SourceEvidenceLifecycleError, "cannot use content_class"):
            validate_source_attempt(
                attempt(
                    outcome="NETWORK_ERROR",
                    content_class="DATA",
                    qualified_rows=0,
                    byte_count=0,
                    raw_sha256=None,
                    schema_fingerprint=None,
                    expected_schema_fingerprint=None,
                )
            )

    def test_network_access_mode_requires_http_status(self) -> None:
        with self.assertRaisesRegex(SourceEvidenceLifecycleError, "HTTP status"):
            validate_source_attempt(attempt(http_status=None))

    def test_parser_drift_is_preserved_and_blocks_missing_critical_cell(self) -> None:
        drift = attempt(
            outcome="PARSER_DRIFT",
            qualified_rows=0,
            schema_fingerprint=F2,
        )
        report = reconcile_source_evidence(document(attempts=[drift], observations=[]))
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(report["attempt_summary"]["outcome_counts"], {"PARSER_DRIFT": 1})
        self.assertEqual(report["quality"]["missing_critical_cell_count"], 1)

    def test_collected_schema_drift_is_quarantined(self) -> None:
        bad = attempt(schema_fingerprint=F2)
        report = reconcile_source_evidence(document(attempts=[bad]))
        self.assertEqual(report["status"], "BLOCKED")
        self.assertTrue(
            any("schema drift" in item["detail"] for item in report["quarantine"])
        )

    def test_post_cutoff_observation_is_quarantined(self) -> None:
        late = observation(
            published_at="2026-08-03T14:00:01+03:00",
            available_at="2026-08-03T14:00:01+03:00",
            retrieved_at="2026-08-03T14:00:02+03:00",
        )
        late_attempt = attempt(
            started_at="2026-08-03T14:00:01+03:00",
            finished_at="2026-08-03T14:00:02+03:00",
        )
        report = reconcile_source_evidence(
            document(attempts=[late_attempt], observations=[late])
        )
        self.assertEqual(report["status"], "BLOCKED")
        self.assertTrue(
            any(item["reason_code"] in {"ATTEMPT_INVALID", "POST_CUTOFF"} for item in report["quarantine"])
        )

    def test_historical_late_retrieval_requires_verified_archive(self) -> None:
        late_attempt = attempt(
            started_at="2026-08-04T13:24:00+03:00",
            finished_at="2026-08-04T13:25:00+03:00",
        )
        late_row = observation(
            retrieved_at="2026-08-04T13:25:00+03:00",
            availability_evidence_status="UNVERIFIED",
        )
        report = reconcile_source_evidence(
            document(
                attempts=[late_attempt],
                observations=[late_row],
                capture_mode="HISTORICAL_POINT_IN_TIME",
            )
        )
        self.assertEqual(report["status"], "BLOCKED")
        self.assertTrue(
            any("VERIFIED_ARCHIVE" in item["detail"] for item in report["quarantine"])
        )

    def test_verified_archive_can_support_historical_point_in_time(self) -> None:
        late_attempt = attempt(
            started_at="2026-08-04T13:24:00+03:00",
            finished_at="2026-08-04T13:25:00+03:00",
        )
        late_row = observation(
            retrieved_at="2026-08-04T13:25:00+03:00",
            availability_evidence_status="VERIFIED_ARCHIVE",
        )
        report = reconcile_source_evidence(
            document(
                attempts=[late_attempt],
                observations=[late_row],
                capture_mode="HISTORICAL_POINT_IN_TIME",
            )
        )
        self.assertEqual(report["status"], "STRUCTURE_AND_RECONCILIATION_VALID_ONLY")

    def test_unique_grade_a_primary_value_resolves_conflict(self) -> None:
        secondary = second_observation(
            value=101,
            source_grade="B",
            verification_status="UNVERIFIED",
            evidence_role="FINANCIAL_CONTEXT",
        )
        report = reconcile_source_evidence(
            document(
                attempts=[attempt(), second_attempt()],
                observations=[observation(), secondary],
            )
        )
        self.assertEqual(report["accepted"][0]["value"], 100)
        self.assertEqual(
            report["conflicts"][0]["status"],
            "RESOLVED_BY_UNIQUE_AUTHORITATIVE_VALUE",
        )

    def test_two_conflicting_grade_a_primary_values_block(self) -> None:
        conflicting = second_observation(value=101)
        report = reconcile_source_evidence(
            document(
                attempts=[attempt(), second_attempt()],
                observations=[observation(), conflicting],
            )
        )
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(report["quality"]["unresolved_conflict_count"], 1)

    def test_copy_count_does_not_outvote_primary_evidence(self) -> None:
        attempts = [attempt()]
        observations = [observation()]
        for index in range(2, 6):
            digest = str(index) * 64
            attempts.append(
                second_attempt(
                    attempt_id=f"a{index}",
                    source_id=f"news-{index}",
                    publisher=f"News {index}",
                    source_family="press",
                    source_url=f"https://news{index}.example.test/story",
                    raw_sha256=digest,
                    started_at=f"2026-08-03T13:{20 + index}:00+03:00",
                    finished_at=f"2026-08-03T13:{21 + index}:00+03:00",
                )
            )
            observations.append(
                second_observation(
                    observation_id=f"o{index}",
                    attempt_id=f"a{index}",
                    source_id=f"news-{index}",
                    publisher=f"News {index}",
                    source_family="press",
                    source_url=f"https://news{index}.example.test/story",
                    raw_sha256=digest,
                    origin_id="same-wire-origin",
                    source_record_id=f"copy-{index}",
                    value=101,
                    source_grade="C",
                    verification_status="UNVERIFIED",
                    evidence_role="NEWS_CONTEXT",
                    published_at=f"2026-08-03T13:{20 + index}:00+03:00",
                    available_at=f"2026-08-03T13:{20 + index}:00+03:00",
                    retrieved_at=f"2026-08-03T13:{21 + index}:00+03:00",
                )
            )
        report = reconcile_source_evidence(
            document(attempts=attempts, observations=observations)
        )
        self.assertEqual(report["accepted"][0]["value"], 100)
        self.assertEqual(report["conflicts"][0]["independent_origin_count"], 2)

    def test_exact_copies_are_counted_as_duplicates(self) -> None:
        mirror_attempt = second_attempt(
            source_id="mirror",
            publisher="Mirror",
            source_family="mirror",
            source_url="https://mirror.example.test/data",
            raw_sha256=H1,
        )
        mirror_row = second_observation(
            source_id="mirror",
            publisher="Mirror",
            source_family="mirror",
            source_url="https://mirror.example.test/data",
            raw_sha256=H1,
            origin_id="exchange-original",
            source_record_id="mirror-record",
        )
        report = reconcile_source_evidence(
            document(
                attempts=[attempt(), mirror_attempt],
                observations=[observation(), mirror_row],
            )
        )
        self.assertEqual(report["quality"]["exact_duplicate_observation_count"], 1)

    def test_same_value_from_distinct_confirmed_origins_is_support(self) -> None:
        report = reconcile_source_evidence(
            document(
                attempts=[attempt(), second_attempt()],
                observations=[observation(), second_observation()],
            )
        )
        self.assertEqual(
            report["quality"]["same_value_distinct_confirmed_origin_support_count"],
            1,
        )

    def test_revision_chain_must_begin_at_one(self) -> None:
        report = reconcile_source_evidence(
            document(observations=[observation(revision=2)])
        )
        self.assertEqual(report["status"], "BLOCKED")
        self.assertTrue(
            any(item["reason_code"] == "REVISION_START_INVALID" for item in report["quarantine"])
        )

    def test_consecutive_revision_chain_selects_latest_revision(self) -> None:
        revision_two_attempt = second_attempt(
            source_id="exchange",
            publisher="Official Exchange",
            source_family="exchange",
            source_url="https://example.test/exchange",
        )
        revision_two = second_observation(
            source_id="exchange",
            publisher="Official Exchange",
            source_family="exchange",
            source_url="https://example.test/exchange",
            origin_id="exchange-original",
            source_record_id="record-1",
            value=101,
            revision=2,
            evidence_role="EXCHANGE_OFFICIAL",
        )
        report = reconcile_source_evidence(
            document(
                attempts=[attempt(), revision_two_attempt],
                observations=[observation(), revision_two],
            )
        )
        self.assertEqual(report["status"], "STRUCTURE_AND_RECONCILIATION_VALID_ONLY")
        self.assertEqual(report["accepted"][0]["value"], 101)

    def test_social_context_cannot_satisfy_critical_fact(self) -> None:
        social = observation(
            source_grade="D",
            verification_status="UNVERIFIED",
            evidence_role="SOCIAL_CONTEXT_LEAD_ONLY",
        )
        report = reconcile_source_evidence(document(observations=[social]))
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(report["missing_expected_cells"][0]["fact_status"], "missing")

    def test_noncritical_missing_cell_is_explicit_and_degraded(self) -> None:
        value = document()
        value["expected_cells"].append(
            {
                "entity_id": "SYN1",
                "field_name": "volume",
                "effective_at": "2026-08-03T13:15:00+03:00",
            }
        )
        report = reconcile_source_evidence(value)
        self.assertEqual(report["status"], "DEGRADED_STRUCTURE_VALID_ONLY")
        self.assertEqual(report["missing_expected_cells"][0]["field_name"], "volume")
        self.assertFalse(report["missing_expected_cells"][0]["critical"])

    def test_denominator_must_include_every_critical_field_for_each_scope(self) -> None:
        value = document(critical_fields=["close_fils", "volume"])
        with self.assertRaisesRegex(
            SourceEvidenceLifecycleError,
            "omits critical fields",
        ):
            reconcile_source_evidence(value)

    def test_observation_outside_denominator_is_quarantined(self) -> None:
        extra_attempt = second_attempt(qualified_rows=1)
        extra = second_observation(field_name="volume", unit="SHARES")
        report = reconcile_source_evidence(
            document(
                attempts=[attempt(), extra_attempt],
                observations=[observation(), extra],
            )
        )
        self.assertEqual(report["status"], "DEGRADED_STRUCTURE_VALID_ONLY")
        self.assertTrue(
            any(item["reason_code"] == "OUTSIDE_EXPECTED_DENOMINATOR" for item in report["quarantine"])
        )

    def test_sensitive_query_parameter_is_rejected(self) -> None:
        with self.assertRaisesRegex(SourceEvidenceLifecycleError, "credential"):
            validate_source_attempt(
                attempt(source_url="https://example.test/data?access_token=secret-value")  # secret-guard: allow — rejection fixture
            )

    def test_quarantine_does_not_reflect_rejected_sensitive_material(self) -> None:
        marker = "fixture-redaction-marker"
        bad_attempt = attempt(
            source_url=f"https://example.test/data?access_token={marker}"  # secret-guard: allow — rejection fixture
        )
        report = reconcile_source_evidence(
            document(attempts=[bad_attempt], observations=[])
        )
        serialized = json.dumps(report, sort_keys=True)
        self.assertNotIn(marker, serialized)
        self.assertNotIn("access_token", serialized)
        self.assertEqual(report["status"], "BLOCKED")
        reference = report["quarantine"][0]["row"]
        self.assertEqual(reference["identifiers"]["attempt_id"], "a1")
        self.assertEqual(len(reference["record_sha256"]), 64)

    def test_forbidden_rights_and_robots_cannot_collect(self) -> None:
        with self.assertRaisesRegex(SourceEvidenceLifecycleError, "FORBIDDEN"):
            validate_source_attempt(attempt(rights_status="FORBIDDEN"))
        with self.assertRaisesRegex(SourceEvidenceLifecycleError, "robots"):
            validate_source_attempt(attempt(robots_status="DISALLOWED"))

    def test_strict_loader_rejects_duplicate_keys_and_nan(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            duplicate = root / "duplicate.json"
            duplicate.write_text('{"a": 1, "a": 2}', encoding="utf-8")
            with self.assertRaisesRegex(SourceEvidenceLifecycleError, "duplicate JSON key"):
                load_source_evidence_document(duplicate)
            nonfinite = root / "nonfinite.json"
            nonfinite.write_text('{"a": NaN}', encoding="utf-8")
            with self.assertRaisesRegex(SourceEvidenceLifecycleError, "non-JSON numeric"):
                load_source_evidence_document(nonfinite)

    def test_report_writer_refuses_overwrite(self) -> None:
        report = reconcile_source_evidence(document())
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "report.json"
            target.write_text("keep", encoding="utf-8")
            with self.assertRaisesRegex(FileExistsError, "refusing to overwrite"):
                write_reconciliation_report(target, report)
            self.assertEqual(target.read_text(encoding="utf-8"), "keep")

    def test_input_and_report_validate_against_schemas(self) -> None:
        input_schema = json.loads(
            (ROOT / "schemas/source-evidence-lifecycle.schema.json").read_text(encoding="utf-8")
        )
        report_schema = json.loads(
            (ROOT / "schemas/source-evidence-reconciliation-report.schema.json").read_text(
                encoding="utf-8"
            )
        )
        checker = FormatChecker()
        Draft202012Validator(input_schema, format_checker=checker).validate(document())
        Draft202012Validator(report_schema, format_checker=checker).validate(
            reconcile_source_evidence(document())
        )

    def test_report_hash_is_deterministic(self) -> None:
        first = reconcile_source_evidence(document())
        second = reconcile_source_evidence(document())
        self.assertEqual(first["report_sha256"], second["report_sha256"])

    def test_cli_writes_exclusive_reconciliation_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "input.json"
            target = root / "report.json"
            source.write_text(json.dumps(document()), encoding="utf-8")
            output = io.StringIO()
            with redirect_stdout(output):
                code = cli_main(
                    [
                        "--project-root",
                        str(ROOT),
                        "reconcile-source-evidence",
                        "--input",
                        str(source),
                        "--output",
                        str(target),
                    ]
                )
            self.assertEqual(code, 0)
            written = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(written["status"], "STRUCTURE_AND_RECONCILIATION_VALID_ONLY")
            self.assertIn("report_sha256", output.getvalue())


if __name__ == "__main__":
    unittest.main()
