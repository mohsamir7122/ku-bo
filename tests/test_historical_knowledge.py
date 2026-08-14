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
    validate_claim_support,
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
        self.assertEqual(report["source_count"], 26)
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
        for source_id in ("social_platforms", "kuwait_community_forums", "wikipedia_routing"):
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
            source_ids=["social_platforms"],
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


if __name__ == "__main__":
    unittest.main()
