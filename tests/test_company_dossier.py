from __future__ import annotations

import copy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from jsonschema import Draft202012Validator, FormatChecker

from kubo.cli_v3 import main as cli_main
from kubo.company_dossier import (
    CompanyDossierError,
    validate_company_dossier,
    validate_company_research_bundle,
    validate_company_research_bundle_files,
    validate_issuer_universe,
    write_company_dossier_report,
)


ROOT = Path(__file__).resolve().parents[1]


def load_example(name: str) -> dict[str, object]:
    return json.loads((ROOT / "examples" / name).read_text(encoding="utf-8"))


def universe() -> dict[str, object]:
    return load_example("synthetic_issuer_universe.json")


def dossier() -> dict[str, object]:
    return load_example("synthetic_company_dossier.json")


def fact(document: dict[str, object], section: str, field_name: str) -> dict[str, object]:
    section_value = document["sections"][section]  # type: ignore[index]
    return next(
        item for item in section_value["facts"] if item["field_name"] == field_name  # type: ignore[index]
    )


def quality(document: dict[str, object], source_id: str) -> dict[str, object]:
    return next(
        item for item in document["source_quality"] if item["source_id"] == source_id  # type: ignore[index]
    )


def make_missing(
    document: dict[str, object],
    *,
    section: str,
    field_name: str,
    reason: str = "NOT_DISCLOSED",
) -> None:
    row = fact(document, section, field_name)
    row.update(
        {
            "value": None,
            "unit": None,
            "effective_at": None,
            "published_at": None,
            "available_at": None,
            "fact_status": None,
            "evidence_ids": [],
            "missing_reason": reason,
        }
    )
    field_key = f"{section}.{field_name}"
    issuer_quality = quality(document, "synthetic_issuer_fixture")
    exchange_quality = quality(document, "synthetic_exchange_fixture")
    source_row = issuer_quality if field_key in issuer_quality["resolved_fields"] else exchange_quality
    source_row["resolved_fields"].remove(field_key)  # type: ignore[union-attr]
    document["data_gaps"].append(  # type: ignore[union-attr]
        {
            "section": section,
            "field_name": field_name,
            "reason_code": reason,
            "detail": "Synthetic explicit gap for an adversarial contract test.",
            "last_attempted_at": "2026-08-03T13:30:00+03:00",
            "source_ids": [source_row["source_id"]],
        }
    )


class CompanyDossierTests(unittest.TestCase):
    def test_clean_synthetic_bundle_is_structural_only(self) -> None:
        report = validate_company_research_bundle(universe(), [dossier()])
        self.assertEqual(report["status"], "STRUCTURE_VALID_ONLY")
        self.assertEqual(report["dossier_summary"]["expected_field_count"], 21)
        self.assertEqual(report["dossier_summary"]["data_coverage_score"], 1.0)
        self.assertFalse(report["claim_boundaries"]["real_collection_complete"])
        self.assertFalse(report["claim_boundaries"]["training_permitted"])
        self.assertFalse(report["claim_boundaries"]["recommendation_permitted"])

    def test_input_and_report_schemas_validate_examples(self) -> None:
        checker = FormatChecker()
        cases = (
            ("issuer-universe.schema.json", universe()),
            ("company-dossier.schema.json", dossier()),
            (
                "company-dossier-validation-report.schema.json",
                validate_company_research_bundle(universe(), [dossier()]),
            ),
        )
        for name, payload in cases:
            with self.subTest(schema=name):
                schema = json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))
                Draft202012Validator.check_schema(schema)
                Draft202012Validator(schema, format_checker=checker).validate(payload)

    def test_report_hash_is_deterministic(self) -> None:
        first = validate_company_research_bundle(universe(), [dossier()])
        second = validate_company_research_bundle(universe(), [dossier()])
        self.assertEqual(first, second)
        self.assertEqual(first["report_sha256"], second["report_sha256"])

    def test_cli_writes_exclusive_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            with redirect_stdout(io.StringIO()):
                rc = cli_main(
                    [
                        "--project-root",
                        str(ROOT),
                        "validate-company-dossier-bundle",
                        "--universe",
                        str(ROOT / "examples/synthetic_issuer_universe.json"),
                        "--dossier",
                        str(ROOT / "examples/synthetic_company_dossier.json"),
                        "--output",
                        str(output),
                    ]
                )
            self.assertEqual(rc, 0)
            self.assertEqual(json.loads(output.read_text())["status"], "STRUCTURE_VALID_ONLY")
            with self.assertRaisesRegex(FileExistsError, "refusing to overwrite"):
                write_company_dossier_report(
                    output,
                    validate_company_research_bundle(universe(), [dossier()]),
                )

    def test_file_loader_and_validator_round_trip(self) -> None:
        report = validate_company_research_bundle_files(
            ROOT / "examples/synthetic_issuer_universe.json",
            [ROOT / "examples/synthetic_company_dossier.json"],
        )
        self.assertEqual(report["status"], "STRUCTURE_VALID_ONLY")

    def test_exact_universe_cannot_hide_missing_security(self) -> None:
        value = universe()
        value["expected_security_codes"].append("999002")  # type: ignore[union-attr]
        with self.assertRaisesRegex(CompanyDossierError, "EXACT universe"):
            validate_issuer_universe(value)

    def test_partial_universe_preserves_gap_and_blocks_bundle(self) -> None:
        value = universe()
        value["universe_status"] = "PARTIAL"
        value["expected_security_codes"].append("999002")  # type: ignore[union-attr]
        report = validate_company_research_bundle(value, [dossier()])
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(report["universe_summary"]["missing_security_count"], 1)

    def test_identity_intervals_cannot_overlap(self) -> None:
        value = universe()
        identity = copy.deepcopy(value["issuers"][0]["security_identities"][0])  # type: ignore[index]
        identity.update({"valid_from": "2025-01-01", "ticker": "SYN2"})
        value["issuers"][0]["security_identities"].append(identity)  # type: ignore[index]
        with self.assertRaisesRegex(CompanyDossierError, "intervals overlap"):
            validate_issuer_universe(value)

    def test_overlapping_isin_collision_is_rejected(self) -> None:
        value = universe()
        second = copy.deepcopy(value["issuers"][0])  # type: ignore[index]
        second["issuer_id"] = "SYNTHETIC-ISSUER-2"
        second["official_registration_id"] = "SYNTHETIC-REGISTRATION-2"
        second["security_identities"][0].update(  # type: ignore[index]
            {"security_code": "999002", "ticker": "SYN2"}
        )
        value["issuers"].append(second)  # type: ignore[union-attr]
        value["expected_security_codes"].append("999002")  # type: ignore[union-attr]
        with self.assertRaisesRegex(CompanyDossierError, "ISIN collision"):
            validate_issuer_universe(value)

    def test_ticker_collision_is_rejected(self) -> None:
        value = universe()
        second = copy.deepcopy(value["issuers"][0])  # type: ignore[index]
        second["issuer_id"] = "SYNTHETIC-ISSUER-2"
        second["official_registration_id"] = "SYNTHETIC-REGISTRATION-2"
        second["security_identities"][0].update(  # type: ignore[index]
            {"security_code": "999002", "isin": "KW0EQ9990028"}
        )
        value["issuers"].append(second)  # type: ignore[union-attr]
        value["expected_security_codes"].append("999002")  # type: ignore[union-attr]
        with self.assertRaisesRegex(CompanyDossierError, "ticker collision"):
            validate_issuer_universe(value)

    def test_registration_gap_must_be_explicit(self) -> None:
        value = universe()
        value["issuers"][0]["official_registration_id"] = None  # type: ignore[index]
        with self.assertRaisesRegex(CompanyDossierError, "registration gap"):
            validate_issuer_universe(value)

    def test_universe_rejects_unknown_identity_evidence(self) -> None:
        value = universe()
        value["issuers"][0]["security_identities"][0]["evidence_ids"] = ["missing"]  # type: ignore[index]
        with self.assertRaisesRegex(CompanyDossierError, "unknown evidence"):
            validate_issuer_universe(value)

    def test_universe_rejects_post_cutoff_evidence(self) -> None:
        value = universe()
        value["evidence"][0]["available_at"] = "2026-08-04T13:05:00+03:00"  # type: ignore[index]
        value["evidence"][0]["accessed_at"] = "2026-08-04T13:05:00+03:00"  # type: ignore[index]
        with self.assertRaisesRegex(CompanyDossierError, "post-cutoff"):
            validate_issuer_universe(value)

    def test_missing_evidence_dates_must_be_explicit(self) -> None:
        value = universe()
        value["evidence"][0]["published_at"] = None  # type: ignore[index]
        with self.assertRaisesRegex(CompanyDossierError, "date gaps"):
            validate_issuer_universe(value)

    def test_historical_late_retrieval_requires_verified_archive(self) -> None:
        value = universe()
        value["capture_mode"] = "HISTORICAL_POINT_IN_TIME"
        value["evidence"][0]["accessed_at"] = "2026-08-04T13:05:00+03:00"  # type: ignore[index]
        with self.assertRaisesRegex(CompanyDossierError, "VERIFIED_ARCHIVE"):
            validate_issuer_universe(value)

    def test_dossier_unknown_issuer_is_blocked_without_fabrication(self) -> None:
        value = dossier()
        value["issuer_id"] = "UNKNOWN"
        report = validate_company_research_bundle(universe(), [value])
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(report["dossier_summary"]["valid_dossier_count"], 0)

    def test_dossier_security_codes_must_match_identity(self) -> None:
        value = dossier()
        value["security_codes"] = ["999002"]
        with self.assertRaisesRegex(CompanyDossierError, "point-in-time identity"):
            validate_company_dossier(value, universe=validate_issuer_universe(universe()))

    def test_section_cannot_omit_required_expected_field(self) -> None:
        value = dossier()
        section = value["sections"]["financials"]  # type: ignore[index]
        section["expected_fields"].remove("total_equity")  # type: ignore[union-attr]
        section["facts"] = [  # type: ignore[index]
            item for item in section["facts"] if item["field_name"] != "total_equity"  # type: ignore[index]
        ]
        with self.assertRaisesRegex(CompanyDossierError, "omits required"):
            validate_company_dossier(value, universe=validate_issuer_universe(universe()))

    def test_section_cannot_weaken_required_critical_fields(self) -> None:
        value = dossier()
        value["sections"]["market"]["critical_fields"] = ["reference_price"]  # type: ignore[index]
        with self.assertRaisesRegex(CompanyDossierError, "weakens"):
            validate_company_dossier(value, universe=validate_issuer_universe(universe()))

    def test_noncritical_missing_fact_is_explicit_and_degraded(self) -> None:
        value = dossier()
        make_missing(value, section="governance_ownership", field_name="ownership_coverage")
        report = validate_company_research_bundle(universe(), [value])
        self.assertEqual(report["status"], "STRUCTURE_VALID_ONLY_WITH_EXPLICIT_GAPS")
        self.assertEqual(report["dossier_summary"]["missing_field_count"], 1)
        self.assertEqual(report["dossier_summary"]["missing_critical_field_count"], 0)

    def test_missing_critical_fact_blocks_bundle(self) -> None:
        value = dossier()
        make_missing(value, section="market", field_name="reference_price")
        report = validate_company_research_bundle(universe(), [value])
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(report["dossier_summary"]["missing_critical_field_count"], 1)

    def test_missing_fact_without_gap_is_rejected(self) -> None:
        value = dossier()
        make_missing(value, section="governance_ownership", field_name="ownership_coverage")
        value["data_gaps"] = []
        with self.assertRaisesRegex(CompanyDossierError, "must match missing facts"):
            validate_company_dossier(value, universe=validate_issuer_universe(universe()))

    def test_resolved_fact_cannot_have_gap(self) -> None:
        value = dossier()
        value["data_gaps"].append(  # type: ignore[union-attr]
            {
                "section": "governance_ownership",
                "field_name": "ownership_coverage",
                "reason_code": "NOT_DISCLOSED",
                "detail": "Contradictory synthetic gap.",
                "last_attempted_at": "2026-08-03T13:30:00+03:00",
                "source_ids": ["synthetic_issuer_fixture"],
            }
        )
        with self.assertRaisesRegex(CompanyDossierError, "must match missing facts"):
            validate_company_dossier(value, universe=validate_issuer_universe(universe()))

    def test_resolved_fact_requires_known_evidence(self) -> None:
        value = dossier()
        fact(value, "business", "sector")["evidence_ids"] = ["unknown"]
        with self.assertRaisesRegex(CompanyDossierError, "known evidence"):
            validate_company_dossier(value, universe=validate_issuer_universe(universe()))

    def test_confirmed_fact_requires_confirmed_evidence(self) -> None:
        value = dossier()
        value["evidence"][1]["fact_status"] = "unverified"  # type: ignore[index]
        with self.assertRaisesRegex(CompanyDossierError, "confirmed fact"):
            validate_company_dossier(value, universe=validate_issuer_universe(universe()))

    def test_social_context_cannot_satisfy_critical_fact(self) -> None:
        value = dossier()
        value["evidence"][1]["evidence_role"] = "SOCIAL_CONTEXT_LEAD_ONLY"  # type: ignore[index]
        with self.assertRaisesRegex(CompanyDossierError, "critical fact"):
            validate_company_dossier(value, universe=validate_issuer_universe(universe()))

    def test_source_quality_must_cover_every_source(self) -> None:
        value = dossier()
        value["source_quality"] = value["source_quality"][:1]  # type: ignore[index]
        with self.assertRaisesRegex(CompanyDossierError, "cover evidence"):
            validate_company_dossier(value, universe=validate_issuer_universe(universe()))

    def test_source_quality_must_match_admitted_evidence(self) -> None:
        value = dossier()
        quality(value, "synthetic_issuer_fixture")["publisher"] = "Different Publisher"
        with self.assertRaisesRegex(CompanyDossierError, "disagrees"):
            validate_company_dossier(value, universe=validate_issuer_universe(universe()))

    def test_fact_cannot_use_post_cutoff_information(self) -> None:
        value = dossier()
        fact(value, "market", "reference_price")["available_at"] = (
            "2026-08-04T13:05:00+03:00"
        )
        with self.assertRaisesRegex(CompanyDossierError, "post-cutoff"):
            validate_company_dossier(value, universe=validate_issuer_universe(universe()))

    def test_prospective_last_update_cannot_exceed_cutoff(self) -> None:
        value = dossier()
        value["last_updated_at"] = "2026-08-03T13:31:00+03:00"
        with self.assertRaisesRegex(CompanyDossierError, "prospective last_updated_at"):
            validate_company_dossier(value, universe=validate_issuer_universe(universe()))

    def test_admitted_evidence_source_must_remain_available(self) -> None:
        value = dossier()
        quality(value, "synthetic_issuer_fixture")["access_status"] = "BLOCKED_ACCESS"
        with self.assertRaisesRegex(CompanyDossierError, "remain AVAILABLE"):
            validate_company_dossier(value, universe=validate_issuer_universe(universe()))

    def test_source_quality_cannot_inflate_resolved_fields(self) -> None:
        value = dossier()
        issuer_quality = quality(value, "synthetic_issuer_fixture")
        issuer_quality["expected_fields"].append("market.reference_price")  # type: ignore[union-attr]
        issuer_quality["resolved_fields"].append("market.reference_price")  # type: ignore[union-attr]
        with self.assertRaisesRegex(CompanyDossierError, "not evidence-derived"):
            validate_company_dossier(value, universe=validate_issuer_universe(universe()))

    def test_unused_evidence_is_rejected(self) -> None:
        value = dossier()
        extra = copy.deepcopy(value["evidence"][1])  # type: ignore[index]
        extra["evidence_id"] = "unused-evidence"
        value["evidence"].append(extra)  # type: ignore[union-attr]
        with self.assertRaisesRegex(CompanyDossierError, "unused evidence"):
            validate_company_dossier(value, universe=validate_issuer_universe(universe()))

    def test_duplicate_dossier_is_blocked(self) -> None:
        report = validate_company_research_bundle(universe(), [dossier(), dossier()])
        self.assertEqual(report["status"], "BLOCKED")
        self.assertTrue(any("duplicate issuer dossier" in item for item in report["errors"]))


if __name__ == "__main__":
    unittest.main()
