from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from jsonschema import Draft202012Validator

from kubo.research_workflow import (
    WORKFLOW_ID,
    catalog_registrable_domains,
    integrate_research_reports,
    load_research_workflow,
)
from kubo.source_network import SourceNetworkCatalog


ROOT = Path(__file__).resolve().parents[1]


class ResearchWorkflowTests(unittest.TestCase):
    def test_catalog_can_attempt_at_least_fifty_research_domains(self) -> None:
        spec = load_research_workflow(ROOT / "config")
        domains = catalog_registrable_domains(SourceNetworkCatalog(ROOT / "config"))
        self.assertGreaterEqual(len(domains), 50)
        self.assertEqual(len(domains), 54)
        self.assertEqual(spec.catalog_distinct_registrable_domains, len(domains))
        self.assertNotIn("google.com", domains)

    def test_active_workflow_cross_validates_product_and_policy(self) -> None:
        spec = load_research_workflow(ROOT / "config")
        self.assertEqual(spec.workflow_id, WORKFLOW_ID)
        self.assertEqual(spec.context_calendar_days, 120)
        self.assertEqual(spec.transient_attempts_per_strategy, 2)
        self.assertEqual(spec.empty_result_query_strategies, 4)
        self.assertEqual(spec.target_distinct_registrable_domains, 50)
        self.assertEqual(spec.decision_sessions, 40)
        self.assertEqual(spec.required_consecutive_official_sessions, 41)
        self.assertEqual(spec.primary_target, "GROSS_ADJUSTED_RETURN_GT_0")
        self.assertEqual(spec.ranking_rule, "SCORE_DESC_SECURITY_CODE_ASC")
        self.assertTrue(spec.execution_grade_required)
        self.assertEqual(
            spec.nontrading_outcome_policy,
            "STOP_BACKTEST_WHILE_KU_BO_008_D01_OPEN",
        )
        self.assertEqual(spec.minimum_universe_coverage, 1.0)
        self.assertEqual(spec.minimum_evaluable_rate, 1.0)
        self.assertEqual(spec.maximum_nonfill_rate, 0.0)

    def test_active_workflow_config_matches_its_closed_schema(self) -> None:
        schema = json.loads(
            (ROOT / "schemas" / "research-workflow.schema.json").read_text()
        )
        payload = json.loads(
            (ROOT / "config" / "research_workflows.json").read_text()
        )
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(payload)

    def test_mutated_retry_contract_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary)
            for name in (
                "methods.json",
                "products.json",
                "research_policies.json",
                "source_capabilities.json",
                "source_network.json",
                "source_query_strategies.json",
                "sources.json",
            ):
                (config / name).write_bytes((ROOT / "config" / name).read_bytes())
            payload = json.loads((ROOT / "config" / "research_workflows.json").read_text(encoding="utf-8"))
            payload["workflows"][0]["source_search"]["transient_attempts_per_strategy"] = 99
            (config / "research_workflows.json").write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "retry"):
                load_research_workflow(config)

    def test_search_budgets_cannot_be_silently_lowered_or_expanded(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary)
            for name in (
                "methods.json",
                "products.json",
                "research_policies.json",
                "source_capabilities.json",
                "source_network.json",
                "source_query_strategies.json",
                "sources.json",
            ):
                (config / name).write_bytes((ROOT / "config" / name).read_bytes())
            payload = json.loads(
                (ROOT / "config" / "research_workflows.json").read_text(encoding="utf-8")
            )
            payload["workflows"][0]["source_search"]["maximum_requests"] = 601
            (config / "research_workflows.json").write_text(
                json.dumps(payload), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "budgets"):
                load_research_workflow(config)

    def test_stop_backtest_withholds_metrics_across_integration(self) -> None:
        spec = load_research_workflow(ROOT / "config")
        report = integrate_research_reports(
            spec,
            source_search={"status": "DEGRADED"},
            context={"status": "PARTIAL"},
            factors={"status": "PASS"},
            evaluation={"status": "STOP_BACKTEST", "metrics": None},
        )
        self.assertEqual(report["status"], "STOP_BACKTEST")
        self.assertIsNone(report["metrics"])
        self.assertFalse(report["claim_boundaries"]["accuracy_claim_allowed"])

    def test_stopped_evaluation_cannot_smuggle_metrics(self) -> None:
        spec = load_research_workflow(ROOT / "config")
        with self.assertRaisesRegex(ValueError, "must not expose"):
            integrate_research_reports(
                spec,
                source_search={"status": "PASS"},
                context={"status": "PASS"},
                factors={"status": "PASS"},
                evaluation={"status": "STOP_BACKTEST", "metrics": {"agreement": 1.0}},
            )

    def test_stop_inference_is_rejected_as_an_unreachable_evaluator_status(self) -> None:
        spec = load_research_workflow(ROOT / "config")
        with self.assertRaisesRegex(ValueError, "unknown status"):
            integrate_research_reports(
                spec,
                source_search={"status": "PASS"},
                context={"status": "PASS"},
                factors={"status": "PASS"},
                evaluation={"status": "STOP_INFERENCE", "metrics": None},
            )

    def test_product_requires_execution_grade_and_matching_tape_capabilities(self) -> None:
        payload = json.loads((ROOT / "config" / "products.json").read_text())
        product = next(
            row
            for row in payload["products"]
            if row["product_id"] == WORKFLOW_ID
        )
        self.assertTrue(product["execution_grade_required"])
        self.assertTrue(
            {"intraday_bars", "l1_quotes", "execution_fields"}.issubset(
                product["required_capabilities"]
            )
        )

        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary)
            for name in (
                "methods.json",
                "products.json",
                "research_policies.json",
                "research_workflows.json",
                "source_capabilities.json",
                "source_network.json",
                "source_query_strategies.json",
                "sources.json",
            ):
                (config / name).write_bytes((ROOT / "config" / name).read_bytes())
            mutated = json.loads((config / "products.json").read_text())
            target = next(
                row
                for row in mutated["products"]
                if row["product_id"] == WORKFLOW_ID
            )
            target["execution_grade_required"] = False
            (config / "products.json").write_text(json.dumps(mutated))
            with self.assertRaisesRegex(ValueError, "active research workflow"):
                load_research_workflow(config)

    def test_ranking_and_open_nontrading_stop_contracts_are_frozen(self) -> None:
        for field, replacement in (
            ("ranking_rule", "CALLER_SUPPLIED_RANK"),
            ("nontrading_outcome_policy", "ASSUME_ZERO_RETURN"),
            ("execution_grade_required", False),
        ):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary:
                config = Path(temporary)
                for name in (
                    "methods.json",
                    "products.json",
                    "research_policies.json",
                    "source_capabilities.json",
                    "source_network.json",
                    "source_query_strategies.json",
                    "sources.json",
                ):
                    (config / name).write_bytes((ROOT / "config" / name).read_bytes())
                workflow = json.loads(
                    (ROOT / "config" / "research_workflows.json").read_text()
                )
                workflow["workflows"][0]["evaluation"][field] = replacement
                (config / "research_workflows.json").write_text(json.dumps(workflow))
                with self.assertRaises(ValueError):
                    load_research_workflow(config)

    def test_caller_authored_pass_cannot_unlock_accuracy(self) -> None:
        spec = load_research_workflow(ROOT / "config")
        with self.assertRaisesRegex(ValueError, "independent authority verifier"):
            integrate_research_reports(
                spec,
                source_search={"status": "PASS"},
                context={"status": "PASS"},
                factors={"status": "PASS"},
                evaluation={
                    "status": "PASS_BACKTEST",
                    "metrics": {"agreement": 1.0},
                    "claim_boundaries": {
                        "independent_final_authority_receipt_verified": True,
                        "metrics_withheld_on_stop": False,
                    },
                },
            )

    def test_boolean_evaluation_rate_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary)
            for name in (
                "methods.json",
                "products.json",
                "research_policies.json",
                "source_capabilities.json",
                "source_network.json",
                "source_query_strategies.json",
                "sources.json",
            ):
                (config / name).write_bytes((ROOT / "config" / name).read_bytes())
            payload = json.loads(
                (ROOT / "config" / "research_workflows.json").read_text(encoding="utf-8")
            )
            payload["workflows"][0]["evaluation"]["minimum_universe_coverage"] = True
            (config / "research_workflows.json").write_text(
                json.dumps(payload), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "booleans"):
                load_research_workflow(config)

    def test_text_rate_and_reordered_secondary_targets_are_rejected(self) -> None:
        for mutation in ("text-rate", "secondary-order"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                config = Path(temporary)
                for name in (
                    "methods.json",
                    "products.json",
                    "research_policies.json",
                    "source_capabilities.json",
                    "source_network.json",
                    "source_query_strategies.json",
                    "sources.json",
                ):
                    (config / name).write_bytes((ROOT / "config" / name).read_bytes())
                payload = json.loads(
                    (ROOT / "config" / "research_workflows.json").read_text(encoding="utf-8")
                )
                evaluation = payload["workflows"][0]["evaluation"]
                if mutation == "text-rate":
                    evaluation["minimum_universe_coverage"] = "1.0"
                else:
                    evaluation["secondary_targets"].reverse()
                (config / "research_workflows.json").write_text(
                    json.dumps(payload), encoding="utf-8"
                )
                with self.assertRaises(ValueError):
                    load_research_workflow(config)


if __name__ == "__main__":
    unittest.main()
