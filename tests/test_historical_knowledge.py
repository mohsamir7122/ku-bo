from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import tempfile
import unittest

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover
    Draft202012Validator = None  # type: ignore[assignment,misc]

from kubo.cli_v3 import main
from kubo.historical_knowledge import (
    HistoricalKnowledgeCatalog,
    compile_research_plan,
    parse_as_of,
    validate_company_annual_history_record,
    validate_claim_support,
    validate_historical_event_record,
)


ROOT = Path(__file__).resolve().parents[1]
AS_OF = date(2026, 8, 14)


class HistoricalKnowledgeCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = HistoricalKnowledgeCatalog(ROOT / "config")

    def test_registry_is_defined_only_and_has_six_layers(self) -> None:
        report = self.catalog.report()
        self.assertEqual(report["status"], "PASS_CONTRACT")
        self.assertEqual(report["readiness_status"], "DEFINED_ONLY")
        self.assertEqual(report["source_count"], 28)
        self.assertEqual(report["layer_count"], 6)
        self.assertFalse(report["claim_boundaries"]["historical_corpus_collected"])

    def test_every_source_is_https_and_defined_only(self) -> None:
        for source in self.catalog.sources:
            with self.subTest(source=source.source_id):
                self.assertEqual(source.capability_status, "DEFINED_ONLY")
                self.assertTrue(all(url.startswith("https://") for url in source.base_urls))

    def test_year_1500_does_not_receive_modern_sources(self) -> None:
        sources = self.catalog.sources_for_roles(("NATIONAL_HISTORY",), year=1500)
        self.assertIn("qatar_digital_library", sources)
        self.assertIn("kuwait_government_history", sources)
        self.assertNotIn("kuna_archive", sources)
        self.assertNotIn("central_bank_kuwait", sources)

    def test_company_status_requires_primary_identity_evidence(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires primary registry"):
            validate_claim_support(
                self.catalog,
                fact_type="COMPANY_STATUS",
                source_ids=["alqabas_archive"],
            )
        validate_claim_support(
            self.catalog,
            fact_type="COMPANY_STATUS",
            source_ids=["moci_commercial_registry"],
        )

    def test_community_and_wikipedia_cannot_establish_facts(self) -> None:
        for source_id in (
            "facebook_social",
            "instagram_social",
            "tiktok_social",
            "kuwait_community_forums",
            "wikipedia_routing",
        ):
            with self.subTest(source=source_id):
                with self.assertRaisesRegex(ValueError, "cannot establish factual claims"):
                    validate_claim_support(
                        self.catalog,
                        fact_type="HISTORICAL_EVENT",
                        source_ids=[source_id],
                    )

    def test_social_sources_may_only_support_social_sentiment(self) -> None:
        validate_claim_support(
            self.catalog,
            fact_type="SOCIAL_SENTIMENT",
            source_ids=["facebook_social"],
        )

    def test_each_social_platform_is_routed_only_after_its_launch_year(self) -> None:
        roles = ("SOCIAL_ROUTING",)
        self.assertEqual(self.catalog.sources_for_roles(roles, year=2003), ())
        self.assertEqual(self.catalog.sources_for_roles(roles, year=2004), ("facebook_social",))
        self.assertEqual(self.catalog.sources_for_roles(roles, year=2009), ("facebook_social",))
        self.assertEqual(
            self.catalog.sources_for_roles(roles, year=2010),
            ("facebook_social", "instagram_social"),
        )
        self.assertEqual(
            self.catalog.sources_for_roles(roles, year=2016),
            ("facebook_social", "instagram_social"),
        )
        self.assertEqual(
            self.catalog.sources_for_roles(roles, year=2017),
            ("facebook_social", "instagram_social", "tiktok_social"),
        )

    def test_legal_claim_requires_official_role_and_procedural_status(self) -> None:
        with self.assertRaisesRegex(ValueError, "court, regulator"):
            validate_claim_support(
                self.catalog,
                fact_type="LEGAL_ALLEGATION",
                source_ids=["kuwait_times_archive"],
                legal_status="ALLEGED",
            )
        with self.assertRaisesRegex(ValueError, "procedural status"):
            validate_claim_support(
                self.catalog,
                fact_type="LEGAL_ALLEGATION",
                source_ids=["nazaha_kuwait"],
            )
        validate_claim_support(
            self.catalog,
            fact_type="LEGAL_ALLEGATION",
            source_ids=["nazaha_kuwait"],
            legal_status="REFERRED",
        )


class HistoricalResearchPlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = HistoricalKnowledgeCatalog(ROOT / "config")
        self.plan = compile_research_plan(self.catalog, as_of=AS_OF)

    def test_plan_has_every_requested_annual_span(self) -> None:
        spans = {
            row["layer_id"]: (row["start_year"], row["end_year"], row["year_count"])
            for row in self.plan["layers"]
        }
        self.assertEqual(spans["KUWAIT_YEARBOOK_1500_PRESENT"], (1500, 2026, 527))
        self.assertEqual(spans["COMMERCIAL_CRISIS_CHRONOLOGY_1927_PRESENT"], (1927, 2026, 100))
        self.assertEqual(spans["COMPANY_LIFECYCLE_1970_PRESENT"], (1970, 2026, 57))
        self.assertEqual(spans["COMPANY_MEDIA_HISTORY_1980_PRESENT"], (1980, 2026, 47))
        self.assertEqual(spans["COMPANY_CASES_ROLLING_20Y"], (2007, 2026, 20))
        self.assertEqual(spans["RECENT_ECONOMIC_EVENTS_ROLLING_5Y"], (2022, 2026, 5))
        self.assertEqual(len(self.plan["tasks"]), 756)

    def test_each_layer_has_one_task_per_year_without_gaps(self) -> None:
        for layer in self.plan["layers"]:
            years = [
                task["year"]
                for task in self.plan["tasks"]
                if task["layer_id"] == layer["layer_id"]
            ]
            self.assertEqual(years, list(range(layer["start_year"], layer["end_year"] + 1)))

    def test_plan_is_deterministic_and_context_only(self) -> None:
        repeated = compile_research_plan(self.catalog, as_of=AS_OF)
        self.assertEqual(self.plan, repeated)
        self.assertEqual(self.plan["decision_use"], "CONTEXT_ONLY")
        self.assertFalse(self.plan["claim_boundaries"]["direct_trading_decision_allowed"])
        self.assertTrue(all(task["coverage_status"] == "NOT_COLLECTED" for task in self.plan["tasks"]))
        self.assertTrue(all(len(task["queries"]) >= 2 for task in self.plan["tasks"]))
        self.assertTrue(all("{year}" not in query for task in self.plan["tasks"] for query in task["queries"]))

    def test_company_layers_require_official_universe_enumeration(self) -> None:
        company_tasks = [task for task in self.plan["tasks"] if task["grain"] == "COMPANY_YEAR"]
        annual_tasks = [task for task in self.plan["tasks"] if task["grain"] == "YEAR"]
        self.assertTrue(company_tasks)
        self.assertTrue(all(task["company_enumeration_required"] for task in company_tasks))
        self.assertTrue(all(not task["company_enumeration_required"] for task in annual_tasks))

    def test_plan_schema_accepts_compiled_plan(self) -> None:
        if Draft202012Validator is None:
            self.skipTest("jsonschema optional dependency unavailable")
        schema = json.loads(
            (ROOT / "schemas" / "historical-research-plan.schema.json").read_text(encoding="utf-8")
        )
        Draft202012Validator.check_schema(schema)
        errors = list(Draft202012Validator(schema).iter_errors(self.plan))
        self.assertEqual(errors, [])

    def test_future_and_malformed_cutoffs_fail(self) -> None:
        with self.assertRaisesRegex(ValueError, "future"):
            compile_research_plan(self.catalog, as_of=date(9999, 1, 1))
        with self.assertRaisesRegex(ValueError, "YYYY-MM-DD"):
            parse_as_of("14/08/2026")

    def test_cli_validates_and_writes_without_overwriting(self) -> None:
        self.assertEqual(main(["--project-root", str(ROOT), "validate-historical-knowledge"]), 0)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "plan.json"
            rc = main(
                [
                    "--project-root",
                    str(ROOT),
                    "plan-historical-research",
                    "--as-of",
                    AS_OF.isoformat(),
                    "--output",
                    str(output),
                ]
            )
            self.assertEqual(rc, 0)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["status"], "PLANNED_NOT_EXECUTED")
            with self.assertRaises(FileExistsError):
                main(
                    [
                        "--project-root",
                        str(ROOT),
                        "plan-historical-research",
                        "--as-of",
                        AS_OF.isoformat(),
                        "--output",
                        str(output),
                    ]
                )


class HistoricalArtifactSchemaTests(unittest.TestCase):
    @staticmethod
    def _validator(name: str) -> Draft202012Validator:
        if Draft202012Validator is None:
            raise unittest.SkipTest("jsonschema optional dependency unavailable")
        schema = json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        return Draft202012Validator(schema)

    def test_all_new_schemas_are_valid(self) -> None:
        if Draft202012Validator is None:
            self.skipTest("jsonschema optional dependency unavailable")
        for name in (
            "historical-research-plan.schema.json",
            "historical-event-record.schema.json",
            "company-annual-history.schema.json",
        ):
            with self.subTest(schema=name):
                schema = json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))
                Draft202012Validator.check_schema(schema)

    def test_official_confirmed_event_rejects_routing_only_evidence(self) -> None:
        record = {
            "schema_version": "1.0",
            "event_id": "hist-event-" + "a" * 24,
            "year": 2026,
            "occurred_at": "2026-08-14",
            "date_precision": "DAY",
            "published_at": "2026-08-14T08:00:00Z",
            "first_available_at": "2026-08-14T08:00:00Z",
            "captured_at": "2026-08-14T09:00:00Z",
            "scope": "KUWAIT",
            "event_type": "HISTORICAL_EVENT",
            "summary_ar": "حدث تجريبي",
            "summary_en": "Synthetic event",
            "source_evidence": [
                {
                    "source_id": "wikipedia_routing",
                    "url": "https://en.wikipedia.org/wiki/Kuwait",
                    "content_sha256": "b" * 64,
                    "capture_sha256": "c" * 64,
                    "evidence_role": "ROUTING",
                }
            ],
            "factual_status": "OFFICIAL_CONFIRMED",
            "legal_status": "NOT_APPLICABLE",
            "correction_status": "CURRENT",
            "decision_use": "CONTEXT_ONLY",
        }
        self.assertTrue(list(self._validator("historical-event-record.schema.json").iter_errors(record)))
        catalog = HistoricalKnowledgeCatalog(ROOT / "config")
        with self.assertRaisesRegex(ValueError, "official primary evidence"):
            validate_historical_event_record(catalog, record)
        record["source_evidence"][0].update(
            {
                "source_id": "kuwait_government_history",
                "url": "https://e.gov.kw/",
                "evidence_role": "PRIMARY",
            }
        )
        self.assertEqual(
            list(self._validator("historical-event-record.schema.json").iter_errors(record)),
            [],
        )
        validate_historical_event_record(catalog, record)

    def test_legal_event_rejects_not_applicable_procedural_status(self) -> None:
        record = {
            "schema_version": "1.0",
            "event_id": "hist-event-" + "d" * 24,
            "year": 2026,
            "occurred_at": "2026-08-14",
            "date_precision": "DAY",
            "published_at": "2026-08-14T08:00:00Z",
            "first_available_at": "2026-08-14T08:00:00Z",
            "captured_at": "2026-08-14T09:00:00Z",
            "scope": "COMPANY",
            "event_type": "COURT_OUTCOME",
            "summary_ar": "حالة قانونية تجريبية",
            "summary_en": "Synthetic legal event",
            "source_evidence": [
                {
                    "source_id": "ministry_justice_kuwait",
                    "url": "https://www.moj.gov.kw/",
                    "content_sha256": "e" * 64,
                    "capture_sha256": "f" * 64,
                    "evidence_role": "PRIMARY",
                }
            ],
            "factual_status": "OFFICIAL_CONFIRMED",
            "legal_status": "NOT_APPLICABLE",
            "correction_status": "CURRENT",
            "decision_use": "CONTEXT_ONLY",
        }
        self.assertTrue(list(self._validator("historical-event-record.schema.json").iter_errors(record)))
        catalog = HistoricalKnowledgeCatalog(ROOT / "config")
        with self.assertRaisesRegex(ValueError, "procedural status"):
            validate_historical_event_record(catalog, record)
        record["legal_status"] = "DECIDED"
        self.assertEqual(
            list(self._validator("historical-event-record.schema.json").iter_errors(record)),
            [],
        )
        validate_historical_event_record(catalog, record)

    def test_no_verified_event_requires_complete_bound_search_receipts(self) -> None:
        record = {
            "schema_version": "1.0",
            "company_id": "company-1",
            "official_registration_id": "registration-1",
            "year": 2026,
            "legal_names": ["Synthetic Company"],
            "founding": {
                "founded_at": None,
                "date_precision": "UNKNOWN",
                "jurisdiction": "KW",
                "circumstances_summary": None,
            },
            "annual_status": "UNKNOWN",
            "founders": [],
            "event_ids": [],
            "source_evidence_hashes": [],
            "declared_source_ids": [],
            "search_receipts": [],
            "coverage_status": "NO_VERIFIED_EVENT_FOUND",
        }
        self.assertTrue(list(self._validator("company-annual-history.schema.json").iter_errors(record)))
        catalog = HistoricalKnowledgeCatalog(ROOT / "config")
        with self.assertRaisesRegex(ValueError, "declared sources"):
            validate_company_annual_history_record(catalog, record)
        receipt_hash = "1" * 64
        record.update(
            {
                "source_evidence_hashes": [receipt_hash],
                "declared_source_ids": ["moci_commercial_registry"],
                "search_receipts": [
                    {
                        "source_id": "moci_commercial_registry",
                        "query": "Synthetic Company 2026",
                        "searched_at": "2026-08-14T09:00:00Z",
                        "capture_sha256": receipt_hash,
                        "access_status": "COMPLETED",
                        "query_complete": True,
                        "pagination_complete": True,
                    }
                ],
            }
        )
        self.assertEqual(
            list(self._validator("company-annual-history.schema.json").iter_errors(record)),
            [],
        )
        validate_company_annual_history_record(catalog, record)


if __name__ == "__main__":
    unittest.main()
