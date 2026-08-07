from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from kubo.cli_v3 import main
from kubo.pipeline import ResearchPipeline
from kubo.reporting import build_report, render_report
from kubo.request_contracts import AnalysisRequest
from kubo.synthetic_network import build_synthetic_network_run


ROOT = Path(__file__).resolve().parents[1]


class RequestReportingTests(unittest.TestCase):
    def test_claim_types_are_strictly_bound_to_request_scope(self) -> None:
        cases = (
            (
                {
                    "request_id": "single-wrong-scope",
                    "product_id": "next_session_rank",
                    "scope": "CANDIDATE_SET",
                    "claim_type": "SINGLE_SECURITY",
                    "security_codes": ["101"],
                },
                "SINGLE_SECURITY requires scope NAMED_SECURITIES",
            ),
            (
                {
                    "request_id": "comparison-wrong-scope",
                    "product_id": "next_session_rank",
                    "scope": "CANDIDATE_SET",
                    "claim_type": "COMPARISON",
                    "security_codes": ["101", "102"],
                },
                "COMPARISON requires scope NAMED_SECURITIES",
            ),
            (
                {
                    "request_id": "rank-wrong-scope",
                    "product_id": "next_session_rank",
                    "scope": "NAMED_SECURITIES",
                    "claim_type": "RESEARCH_RANK",
                    "security_codes": ["101"],
                },
                "RESEARCH_RANK requires scope CANDIDATE_SET or FULL_MARKET",
            ),
        )
        for payload, message in cases:
            with self.subTest(claim_type=payload["claim_type"]), self.assertRaisesRegex(
                ValueError, message
            ):
                AnalysisRequest.from_dict(payload)

    def test_request_identifiers_and_security_codes_are_canonical_json_strings(self) -> None:
        invalid_payloads = (
            {"request_id": 7, "product_id": "next_session_rank"},
            {"request_id": "request-7", "product_id": 7},
            {"request_id": " request-7", "product_id": "next_session_rank"},
            {"request_id": "request-7\nforged", "product_id": "next_session_rank"},
            {"request_id": "request-7", "product_id": "next_session_rank", "mode": 1},
            {
                "request_id": "request-7",
                "product_id": "next_session_rank",
                "output_format": "JSON",
            },
            {"request_id": "request-7", "product_id": "next_session_rank", "top_k": True},
            {"request_id": "request-7", "product_id": "next_session_rank", "top_k": "5"},
            {
                "request_id": "request-7",
                "product_id": "next_session_rank",
                "claim_type": "EVIDENCE_AUDIT",
                "security_codes": [101],
            },
            {
                "request_id": "request-7",
                "product_id": "next_session_rank",
                "claim_type": "EVIDENCE_AUDIT",
                "security_codes": [" 101"],
            },
            {
                "request_id": "request-7",
                "product_id": "next_session_rank",
                "claim_type": "EVIDENCE_AUDIT",
                "security_codes": ["1234567890123"],
            },
        )
        for payload in invalid_payloads:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                AnalysisRequest.from_dict(payload)

    def test_named_scope_requires_security_codes(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires security_codes"):
            AnalysisRequest.from_dict(
                {
                    "request_id": "r1",
                    "product_id": "next_session_rank",
                    "scope": "NAMED_SECURITIES",
                }
            )

    def test_comparison_requires_two_securities(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least two"):
            AnalysisRequest.from_dict(
                {
                    "request_id": "r1",
                    "product_id": "next_session_rank",
                    "scope": "NAMED_SECURITIES",
                    "claim_type": "COMPARISON",
                    "security_codes": ["101"],
                }
            )

    def test_research_mode_rejects_probability_and_execution_fields(self) -> None:
        for field in (
            "probability",
            "Probability",
            "PROBABILITY",
            "buy_recommendation",
            "buy recommendation",
            "entry_price",
            "entryPrice",
            "ENTRY-PRICE",
            "exit_price",
            "exitPrice",
            "احتمال_الارتفاع",
            "سعر_الدخول",
            "سعر_الخروج",
        ):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "cannot request"):
                AnalysisRequest.from_dict(
                    {
                        "request_id": "r1",
                        "product_id": "next_session_rank",
                        "requested_fields": [field],
                    }
                )

    def test_deep_report_strips_forbidden_fields_recursively(self) -> None:
        request = AnalysisRequest.from_dict(
            {
                "request_id": "strict-deep-report",
                "product_id": "next_session_rank",
                "detail_level": "deep",
            }
        )
        plan = ResearchPipeline(ROOT).plan(
            "next_session_rank",
            mode="research_network",
            network_run_root=ROOT / "examples" / "synthetic_source_network_run",
        )
        injected = dict(plan["ranked_candidates"][0])
        injected.update(
            {
                "Probability": 0.99,
                "entryPrice": 123,
                "exit-price": 150,
                "recommendation": "BUY",
                "nested": {
                    "safe_note": "kept",
                    "buy_recommendation": "BUY",
                    "execution": {"ENTRY_PRICE": 123},
                },
            }
        )
        hostile_plan = {**plan, "ranked_candidates": [injected]}
        candidate = build_report(hostile_plan, request)["candidates"][0]
        self.assertNotIn("Probability", candidate)
        self.assertNotIn("entryPrice", candidate)
        self.assertNotIn("exit-price", candidate)
        self.assertNotIn("recommendation", candidate)
        self.assertNotIn("nested", candidate)

    def test_report_rejects_request_plan_mode_or_product_mismatch(self) -> None:
        request = AnalysisRequest.from_dict(
            {"request_id": "mismatch", "product_id": "next_session_rank"}
        )
        plan = ResearchPipeline(ROOT).plan(
            "next_session_rank",
            network_run_root=ROOT / "examples" / "synthetic_source_network_run",
        )
        mismatch = {
            **plan,
            "mode": "validated_forecast",
            "product": {**plan["product"], "product_id": "three_session_rank"},
        }
        report = build_report(mismatch, request)
        self.assertEqual(report["status"], "REQUEST_SCOPE_UNSATISFIED")
        self.assertEqual(report["candidates"], [])
        self.assertIn("REQUEST_MODE_DOES_NOT_MATCH_PIPELINE_PLAN", report["reasons"])
        self.assertIn("REQUEST_PRODUCT_DOES_NOT_MATCH_PIPELINE_PLAN", report["reasons"])

    def test_report_rechecks_claim_scope_for_directly_constructed_requests(self) -> None:
        plan = ResearchPipeline(ROOT).plan(
            "next_session_rank",
            network_run_root=ROOT / "examples" / "synthetic_source_network_run",
        )
        valid = AnalysisRequest.from_dict(
            {"request_id": "direct-constructor-defense", "product_id": "next_session_rank"}
        )
        hostile_requests = (
            (
                replace(
                    valid,
                    claim_type="SINGLE_SECURITY",
                    scope="CANDIDATE_SET",
                    security_codes=("101",),
                ),
                "SINGLE_SECURITY_CLAIM_REQUIRES_NAMED_SECURITIES_SCOPE",
            ),
            (
                replace(
                    valid,
                    claim_type="COMPARISON",
                    scope="CANDIDATE_SET",
                    security_codes=("101", "102"),
                ),
                "COMPARISON_CLAIM_REQUIRES_NAMED_SECURITIES_SCOPE",
            ),
            (
                replace(
                    valid,
                    claim_type="RESEARCH_RANK",
                    scope="NAMED_SECURITIES",
                    security_codes=("101",),
                ),
                "RESEARCH_RANK_CLAIM_REQUIRES_CANDIDATE_OR_FULL_MARKET_SCOPE",
            ),
        )
        for request, reason in hostile_requests:
            with self.subTest(reason=reason):
                report = build_report(plan, request)
                self.assertEqual(report["status"], "REQUEST_SCOPE_UNSATISFIED")
                self.assertEqual(report["candidates"], [])
                self.assertIn("REQUEST_CONTRACT_INVALID", report["reasons"])
                self.assertIn(reason, report["reasons"])
        invalid_identifier_report = build_report(
            plan, replace(valid, request_id=7)  # type: ignore[arg-type]
        )
        self.assertEqual(
            invalid_identifier_report["status"], "REQUEST_SCOPE_UNSATISFIED"
        )
        self.assertIn(
            "REQUEST_CONTRACT_INVALID", invalid_identifier_report["reasons"]
        )

    def test_report_filters_named_security_and_preserves_claim_boundary(self) -> None:
        request = AnalysisRequest.from_dict(
            {
                "request_id": "r1",
                "product_id": "next_session_rank",
                "scope": "NAMED_SECURITIES",
                "claim_type": "SINGLE_SECURITY",
                "security_codes": ["102"],
                "output_format": "json",
            }
        )
        with tempfile.TemporaryDirectory() as temp:
            run = build_synthetic_network_run(Path(temp) / "run")
            contract_path = run / "research_run.json"
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
            contract["scope"] = "NAMED_SECURITIES"
            contract_path.write_text(
                json.dumps(contract, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
            plan = ResearchPipeline(ROOT).plan(
                "next_session_rank",
                mode="research_network",
                network_run_root=run,
            )
            report = build_report(plan, request)
        self.assertEqual([row["security_code"] for row in report["candidates"]], ["102"])
        self.assertFalse(report["claim_boundaries"]["research_score_is_probability"])
        self.assertFalse(report["claim_boundaries"]["blocked_official_site_blocks_entire_market_run"])
        rendered = json.loads(render_report(report, "json"))
        self.assertEqual(rendered["request"]["request_id"], "r1")

    def test_named_request_cannot_reuse_candidate_discovery_packet(self) -> None:
        request = AnalysisRequest.from_dict(
            {
                "request_id": "named-over-candidates",
                "product_id": "next_session_rank",
                "scope": "NAMED_SECURITIES",
                "claim_type": "SINGLE_SECURITY",
                "security_codes": ["101"],
            }
        )
        plan = ResearchPipeline(ROOT).plan(
            "next_session_rank",
            network_run_root=ROOT / "examples" / "synthetic_source_network_run",
        )
        report = build_report(plan, request)
        self.assertEqual(report["status"], "REQUEST_SCOPE_UNSATISFIED")
        self.assertEqual(report["candidates"], [])
        self.assertIn(
            "REQUEST_SCOPE_INCOMPATIBLE_WITH_PACKET:NAMED_SECURITIES:CANDIDATE_SET",
            report["reasons"],
        )

    def test_named_request_cannot_reuse_nonexact_full_market_packet(self) -> None:
        request = AnalysisRequest.from_dict(
            {
                "request_id": "named-over-nonexact-full-market",
                "product_id": "next_session_rank",
                "scope": "NAMED_SECURITIES",
                "claim_type": "SINGLE_SECURITY",
                "security_codes": ["101"],
            }
        )
        with tempfile.TemporaryDirectory() as temp:
            run = build_synthetic_network_run(Path(temp) / "run")
            contract_path = run / "research_run.json"
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
            contract["scope"] = "FULL_MARKET"
            contract_path.write_text(
                json.dumps(contract, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
            findings_path = run / "findings.jsonl"
            rows = [
                json.loads(line)
                for line in findings_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            for row in rows:
                if row["security_code"] == "102":
                    row["security_code"] = "101"
                    row["ticker"] = "AAA"
            findings_path.write_text(
                "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
                encoding="utf-8",
            )
            plan = ResearchPipeline(ROOT).plan(
                "next_session_rank", network_run_root=run
            )
            plan["exact_universe_reconciled"] = True
            report = build_report(plan, request)
        self.assertFalse(plan["network_run"]["exact_universe_reconciled"])
        self.assertFalse(report["exact_universe_reconciled"])
        self.assertEqual(report["status"], "REQUEST_SCOPE_UNSATISFIED")
        self.assertIn(
            "NAMED_SECURITIES_OVER_FULL_MARKET_REQUIRES_EXACT_POINT_IN_TIME_UNIVERSE",
            report["reasons"],
        )

    def test_report_hash_must_match_the_validator_packet_hash(self) -> None:
        request = AnalysisRequest.from_dict(
            {"request_id": "hash-mismatch", "product_id": "next_session_rank"}
        )
        plan = ResearchPipeline(ROOT).plan(
            "next_session_rank",
            network_run_root=ROOT / "examples" / "synthetic_source_network_run",
        )
        plan["evidence_packet_hash"] = "f" * 64
        report = build_report(plan, request)
        self.assertEqual(report["status"], "REQUEST_SCOPE_UNSATISFIED")
        self.assertIsNone(report["evidence_packet_hash"])
        self.assertIn(
            "EVIDENCE_PACKET_HASH_DOES_NOT_MATCH_VALIDATION",
            report["reasons"],
        )

    def test_markdown_never_labels_evidence_score_as_probability(self) -> None:
        request = AnalysisRequest.from_dict(
            {
                "request_id": "r2",
                "product_id": "next_session_rank",
                "output_format": "markdown",
            }
        )
        plan = ResearchPipeline(ROOT).plan(
            "next_session_rank",
            mode="research_network",
            network_run_root=ROOT / "examples" / "synthetic_source_network_run",
        )
        markdown = render_report(build_report(plan, request), "markdown")
        self.assertIn("Evidence Score", markdown)
        self.assertIn("ليس Probability", markdown)
        self.assertNotIn("احتمال الارتفاع", markdown)

    def test_markdown_escapes_hostile_dynamic_values_from_plan_and_report(self) -> None:
        valid_request = AnalysisRequest.from_dict(
            {
                "request_id": "markdown-defense",
                "product_id": "next_session_rank",
                "output_format": "markdown",
            }
        )
        plan = deepcopy(
            ResearchPipeline(ROOT).plan(
                "next_session_rank",
                network_run_root=ROOT / "examples" / "synthetic_source_network_run",
            )
        )
        plan["status"] = "RESEARCH_READY\r\n# forged-status"
        candidate = plan["ranked_candidates"][0]
        candidate["rank"] = "1\n# forged-rank *bold*"
        candidate["ticker"] = "AAA`tick\n## forged-ticker"
        candidate["security_code"] = "101\r\n# forged-security"
        candidate["reason_codes"] = ["reason```code", "risk\n# forged-reason"]
        plan["network_run"]["warnings"] = ["warning\n## forged-warning"]
        plan["network_run"]["degraded_source_ids"] = [
            "source`id\n# forged-source"
        ]
        report = build_report(plan, valid_request)
        report["request"]["request_id"] = "request`id\n## forged-request"
        report["evidence_summary"]["coverage_gaps"] = [
            "gap\r\n## forged-report"
        ]
        markdown = render_report(report, "markdown")
        self.assertNotIn("\r", markdown)
        self.assertNotRegex(
            markdown,
            r"(?m)^#{1,6}\s+forged-(?:request|status|rank|ticker|security|reason|warning|source|report)",
        )
        self.assertIn("\\# forged\\-rank \\*bold\\*", markdown)
        self.assertIn("`` request`id ## forged-request ``", markdown)
        self.assertIn("```` reason```code ````", markdown)

    def test_missing_packet_renders_an_explicit_empty_result(self) -> None:
        request = AnalysisRequest.from_dict({"request_id": "r3", "product_id": "next_session_rank"})
        plan = ResearchPipeline(ROOT).plan("next_session_rank", mode="research_network")
        report = build_report(plan, request)
        self.assertEqual(report["status"], "SOURCE_NETWORK_REQUIRED")
        self.assertEqual(report["candidates"], [])

    def test_detail_level_changes_output_shape_without_changing_rank(self) -> None:
        plan = ResearchPipeline(ROOT).plan(
            "next_session_rank",
            mode="research_network",
            network_run_root=ROOT / "examples" / "synthetic_source_network_run",
        )
        brief = build_report(
            plan,
            AnalysisRequest.from_dict(
                {"request_id": "brief", "product_id": "next_session_rank", "detail_level": "brief"}
            ),
        )
        deep = build_report(
            plan,
            AnalysisRequest.from_dict(
                {"request_id": "deep", "product_id": "next_session_rank", "detail_level": "deep"}
            ),
        )
        self.assertEqual(brief["candidates"][0]["rank"], deep["candidates"][0]["rank"])
        self.assertNotIn("signal_contributions", brief["candidates"][0])
        self.assertIn("signal_contributions", deep["candidates"][0])
        self.assertNotIn("diagnostics", brief)
        self.assertIn("diagnostics", deep)

    def test_requested_fields_create_a_strict_auditable_projection(self) -> None:
        plan = ResearchPipeline(ROOT).plan(
            "next_session_rank",
            mode="research_network",
            network_run_root=ROOT / "examples" / "synthetic_source_network_run",
        )
        request = AnalysisRequest.from_dict(
            {
                "request_id": "custom-fields",
                "product_id": "next_session_rank",
                "detail_level": "standard",
                "requested_fields": ["evidenceCoverage"],
            }
        )
        candidate = build_report(plan, request)["candidates"][0]
        self.assertIn("evidence_coverage", candidate)
        self.assertIn("security_code", candidate)
        self.assertIn("score_kind", candidate)
        self.assertNotIn("source_conflict", candidate)
        self.assertNotIn("signal_contributions", candidate)

    def test_requested_fields_reject_unknown_or_excess_detail(self) -> None:
        plan = ResearchPipeline(ROOT).plan(
            "next_session_rank",
            mode="research_network",
            network_run_root=ROOT / "examples" / "synthetic_source_network_run",
        )
        for detail_level, field, message in (
            ("deep", "invented_metric", "unsupported requested_fields"),
            ("brief", "evidence_coverage", "exceed brief detail level"),
        ):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, message):
                build_report(
                    plan,
                    AnalysisRequest.from_dict(
                        {
                            "request_id": "invalid-custom-fields",
                            "product_id": "next_session_rank",
                            "detail_level": detail_level,
                            "requested_fields": [field],
                        }
                    ),
                )

    def test_english_markdown_is_rendered_in_english(self) -> None:
        request = AnalysisRequest.from_dict(
            {
                "request_id": "english",
                "product_id": "next_session_rank",
                "output_format": "markdown",
                "language": "en",
            }
        )
        plan = ResearchPipeline(ROOT).plan("next_session_rank", mode="research_network")
        markdown = render_report(build_report(plan, request), "markdown")
        self.assertIn("KU-BO research report", markdown)
        self.assertIn("not a probability", markdown.lower())

    def test_full_market_request_cannot_use_candidate_set_packet(self) -> None:
        request = AnalysisRequest.from_dict(
            {
                "request_id": "full-market",
                "product_id": "next_session_rank",
                "scope": "FULL_MARKET",
            }
        )
        plan = ResearchPipeline(ROOT).plan(
            "next_session_rank",
            mode="research_network",
            network_run_root=ROOT / "examples" / "synthetic_source_network_run",
        )
        report = build_report(plan, request)
        self.assertEqual(report["status"], "REQUEST_SCOPE_UNSATISFIED")
        self.assertEqual(report["candidates"], [])
        self.assertIn("FULL_MARKET_REQUEST_REQUIRES_EXACT_POINT_IN_TIME_UNIVERSE", report["reasons"])

    def test_unresolved_named_security_is_explicitly_blocked(self) -> None:
        request = AnalysisRequest.from_dict(
            {
                "request_id": "missing-security",
                "product_id": "next_session_rank",
                "scope": "NAMED_SECURITIES",
                "claim_type": "SINGLE_SECURITY",
                "security_codes": ["999"],
            }
        )
        plan = ResearchPipeline(ROOT).plan(
            "next_session_rank",
            mode="research_network",
            network_run_root=ROOT / "examples" / "synthetic_source_network_run",
        )
        report = build_report(plan, request)
        self.assertEqual(report["status"], "REQUEST_SCOPE_UNSATISFIED")
        self.assertIn("REQUESTED_SECURITIES_NOT_RESOLVED:999", report["reasons"])

    def test_cli_run_request_writes_requested_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            request_path = root / "request.json"
            output_path = root / "report.md"
            request_path.write_text(
                json.dumps(
                    {
                        "request_id": "cli-request",
                        "product_id": "next_session_rank",
                        "output_format": "markdown",
                    }
                ),
                encoding="utf-8",
            )
            code = main(
                [
                    "--project-root",
                    str(ROOT),
                    "run-request",
                    "--request",
                    str(request_path),
                    "--network-run",
                    str(ROOT / "examples" / "synthetic_source_network_run"),
                    "--output",
                    str(output_path),
                ]
            )
            self.assertEqual(code, 0)
            self.assertIn("تقرير KU-BO", output_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
