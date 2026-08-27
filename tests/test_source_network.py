from __future__ import annotations

import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest

from kubo.pipeline import ResearchPipeline
from kubo.cli_v3 import main as cli_main
from kubo.reporting import build_report
from kubo.request_contracts import AnalysisRequest
from kubo.source_network import SourceNetworkCatalog, SourceNetworkRunValidator, validate_live_probe
from kubo.synthetic_network import build_synthetic_network_run


ROOT = Path(__file__).resolve().parents[1]


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def read_findings(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_findings(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def mark_sources_blocked(run: Path, source_ids: set[str]) -> None:
    observations = read_json(run / "source_observations.json")
    for row in observations["sources"]:
        if row["source_id"] in source_ids:
            row.update(
                {
                    "state": "BLOCKED",
                    "query_status": "BLOCKED",
                    "qualified_items": 0,
                    "zero_result": False,
                }
            )
    write_json(run / "source_observations.json", observations)
    write_findings(
        run / "findings.jsonl",
        [
            row
            for row in read_findings(run / "findings.jsonl")
            if row["source_id"] not in source_ids
        ],
    )


def make_kuna_context_substantive(run: Path) -> None:
    findings = read_findings(run / "findings.jsonl")
    for row in findings:
        if row["source_id"] == "kuna":
            row["direction"] = "POSITIVE"
    write_findings(run / "findings.jsonl", findings)


class SourceNetworkTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = SourceNetworkCatalog(ROOT / "config")
        self.pipeline = ResearchPipeline(ROOT)

    def test_network_catalog_is_research_only(self):
        report = self.catalog.report()
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["sources"], 69)
        self.assertEqual(report["independence_groups"], 63)
        self.assertEqual(report["profiles"], 5)
        self.assertEqual(
            report["capability_status_counts"],
            {"DEFINED_ONLY": 67, "END_TO_END_TESTED": 2},
        )
        self.assertEqual(report["live_operational_sources"], [])
        self.assertFalse(report["claim_boundaries"]["probability_allowed"])
        self.assertFalse(report["claim_boundaries"]["recommendation_allowed"])

    def test_kuwait_clearing_company_is_registered_as_primary_official(self):
        source = self.catalog.sources["kcc_maqasa_official"]
        self.assertEqual(source.source_class, "PRIMARY_OFFICIAL")
        self.assertEqual(source.independence_group, "kuwait_clearing_company")
        self.assertIn("OFFICIAL_EVENT", source.roles)
        self.assertIn("CORPORATE_ACTION", source.fact_eligibility)
        self.assertEqual(source.start_urls, ("https://www.maqasa.com/ar/",))

    def test_same_platform_surfaces_share_one_independence_group(self):
        self.assertEqual(
            self.catalog.sources["investing_history"].independence_group,
            self.catalog.sources["investing_commentary"].independence_group,
        )
        self.assertEqual(
            self.catalog.sources["tradingview_screeners"].independence_group,
            self.catalog.sources["tradingview_ideas"].independence_group,
        )

    def test_agreed_telegram_source_set_is_registered_as_community_only(self):
        source_ids = {
            "telegram_boursakw",
            "telegram_kuwaitstockex",
            "telegram_kuwaitse",
            "telegram_kapsola",
            "telegram_ajanews",
            "telegram_kuwaitnews",
            "telegram_arab24bot",
        }
        self.assertTrue(source_ids.issubset(self.catalog.sources))
        for source_id in source_ids:
            source = self.catalog.sources[source_id]
            self.assertEqual(source.source_class, "COMMUNITY")
            self.assertEqual(source.roles, frozenset({"COMMUNITY_SENTIMENT"}))
            self.assertNotIn("OFFICIAL_EVENT", source.roles)

    def test_non_primary_source_cannot_declare_official_event_role(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory)
            network = read_json(ROOT / "config" / "source_network.json")
            investing = next(row for row in network["sources"] if row["source_id"] == "investing_history")
            investing["roles"].append("OFFICIAL_EVENT")
            write_json(config / "source_network.json", network)
            write_json(config / "research_policies.json", read_json(ROOT / "config" / "research_policies.json"))
            write_json(config / "source_capabilities.json", read_json(ROOT / "config" / "source_capabilities.json"))
            with self.assertRaisesRegex(ValueError, "non-primary source declares OFFICIAL_EVENT"):
                SourceNetworkCatalog(config)

    def test_confirmation_roles_cannot_be_weakened_to_editorial_news(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory)
            write_json(config / "source_network.json", read_json(ROOT / "config" / "source_network.json"))
            policies = read_json(ROOT / "config" / "research_policies.json")
            policies["profiles"][0]["confirmation_roles"] = ["NEWS_ARCHIVE"]
            write_json(config / "research_policies.json", policies)
            write_json(config / "source_capabilities.json", read_json(ROOT / "config" / "source_capabilities.json"))
            with self.assertRaisesRegex(ValueError, "official confirmation roles"):
                SourceNetworkCatalog(config)

    def test_policy_allowed_output_must_use_registered_research_allowlist(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory)
            write_json(config / "source_network.json", read_json(ROOT / "config" / "source_network.json"))
            policies = read_json(ROOT / "config" / "research_policies.json")
            policies["profiles"][0]["allowed_output"] = "CALIBRATED_PROBABILITY"
            write_json(config / "research_policies.json", policies)
            write_json(config / "source_capabilities.json", read_json(ROOT / "config" / "source_capabilities.json"))
            with self.assertRaisesRegex(ValueError, "forbidden or unregistered"):
                SourceNetworkCatalog(config)

    def test_community_and_web_archives_cannot_fill_news_quorum(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory)
            network = read_json(ROOT / "config" / "source_network.json")
            telegram = next(row for row in network["sources"] if row["source_id"] == "telegram_kuwaitstockex")
            telegram["roles"].append("NEWS_ARCHIVE")
            write_json(config / "source_network.json", network)
            write_json(config / "research_policies.json", read_json(ROOT / "config" / "research_policies.json"))
            write_json(config / "source_capabilities.json", read_json(ROOT / "config" / "source_capabilities.json"))
            with self.assertRaisesRegex(ValueError, "community source declares non-community roles"):
                SourceNetworkCatalog(config)
            network = read_json(ROOT / "config" / "source_network.json")
            crawl = next(row for row in network["sources"] if row["source_id"] == "common_crawl")
            crawl["roles"].append("NEWS_ARCHIVE")
            write_json(config / "source_network.json", network)
            with self.assertRaisesRegex(ValueError, "web archive declares non-archive roles"):
                SourceNetworkCatalog(config)

    def test_source_network_runs_without_historical_pack_or_model(self):
        with tempfile.TemporaryDirectory() as directory:
            run = build_synthetic_network_run(Path(directory) / "run")
            plan = self.pipeline.plan("next_session_rank", network_run_root=run)
            self.assertEqual(plan["status"], "RESEARCH_READY", plan)
            self.assertEqual(plan["mode"], "research_network")
            self.assertGreater(len(plan["ranked_candidates"]), 0)
            top = plan["ranked_candidates"][0]
            self.assertEqual(top["security_code"], "101")
            self.assertEqual(top["score_kind"], "SOURCE_MOSAIC_EVIDENCE_SCORE_NOT_PROBABILITY")
            self.assertIsNone(top["probability"])
            self.assertIsNone(top["recommendation"])

    def test_cli_returns_nonzero_when_per_run_packet_is_missing(self):
        with redirect_stdout(StringIO()):
            exit_code = cli_main(
                ["--project-root", str(ROOT), "plan", "--product", "next_session_rank"]
            )
        self.assertEqual(exit_code, 1)

    def test_boursa_can_fail_without_stopping_research_network(self):
        with tempfile.TemporaryDirectory() as directory:
            run = build_synthetic_network_run(Path(directory) / "run")
            mark_sources_blocked(
                run,
                {"boursa_disclosure_archive"},
            )
            make_kuna_context_substantive(run)
            plan = self.pipeline.plan("next_session_rank", network_run_root=run)
            self.assertEqual(plan["status"], "RESEARCH_READY", plan)
            self.assertFalse(plan["network_run"]["official_confirmation_available"])
            self.assertEqual(
                plan["network_run"]["source_states"]["boursa_disclosure_archive"],
                "BLOCKED",
            )
            self.assertEqual(
                plan["network_run"]["source_query_statuses"]["boursa_current"],
                "QUALIFIED",
            )
            self.assertEqual(
                plan["network_run"]["degraded_source_ids"],
                ["boursa_disclosure_archive"],
            )
            stock = next(row for row in plan["ranked_candidates"] if row["security_code"] == "101")
            self.assertEqual(stock["decision_status"], "WATCH")
            self.assertIn("DIRECTIONAL_CATALYST_NOT_PRIMARY_CONFIRMED", stock["reason_codes"])
            report = build_report(
                plan,
                AnalysisRequest.from_dict(
                    {"request_id": "blocked-boursa", "product_id": "next_session_rank"}
                ),
            )
            self.assertEqual(
                report["evidence_summary"]["source_states"]["boursa_current"],
                "AVAILABLE",
            )
            self.assertEqual(
                report["evidence_summary"]["degraded_source_ids"],
                ["boursa_disclosure_archive"],
            )

    def test_two_source_failures_are_visible_and_do_not_block_when_quorum_survives(self):
        with tempfile.TemporaryDirectory() as directory:
            run = build_synthetic_network_run(Path(directory) / "run")
            mark_sources_blocked(
                run,
                {"boursa_disclosure_archive", "telegram_kuwaitstockex"},
            )
            make_kuna_context_substantive(run)
            plan = self.pipeline.plan("next_session_rank", network_run_root=run)
            self.assertEqual(plan["status"], "RESEARCH_READY", plan)
            self.assertEqual(
                plan["network_run"]["degraded_source_ids"],
                ["boursa_disclosure_archive", "telegram_kuwaitstockex"],
            )
            self.assertEqual(
                plan["network_run"]["source_query_statuses"]["telegram_kuwaitstockex"],
                "BLOCKED",
            )

    def test_open_official_channel_without_finding_is_not_confirmation(self):
        with tempfile.TemporaryDirectory() as directory:
            run = build_synthetic_network_run(Path(directory) / "run")
            findings = [
                row
                for row in read_findings(run / "findings.jsonl")
                if row["source_id"] != "boursa_disclosure_archive"
            ]
            write_findings(run / "findings.jsonl", findings)
            make_kuna_context_substantive(run)
            plan = self.pipeline.plan("next_session_rank", network_run_root=run)
            self.assertEqual(plan["status"], "RESEARCH_READY")
            self.assertFalse(plan["network_run"]["official_confirmation_available"])
            stock = next(row for row in plan["ranked_candidates"] if row["security_code"] == "101")
            self.assertEqual(stock["decision_status"], "WATCH")
            self.assertIn("DIRECTIONAL_CATALYST_NOT_PRIMARY_CONFIRMED", stock["reason_codes"])

    def test_available_source_without_resolved_evidence_is_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            run = build_synthetic_network_run(Path(directory) / "run")
            payload = read_json(run / "source_observations.json")
            payload["sources"][0]["raw_sha256s"] = []
            write_json(run / "source_observations.json", payload)
            result = SourceNetworkRunValidator(run, self.catalog, "next_session_rank").validate()
            self.assertEqual(result.status, "BLOCKED")
            self.assertTrue(any("raw evidence" in item for item in result.structural_errors))

    def test_qualified_source_requires_a_positive_item_count(self):
        with tempfile.TemporaryDirectory() as directory:
            run = build_synthetic_network_run(Path(directory) / "run")
            payload = read_json(run / "source_observations.json")
            payload["sources"][0]["qualified_items"] = 0
            write_json(run / "source_observations.json", payload)
            result = SourceNetworkRunValidator(run, self.catalog, "next_session_rank").validate()
            self.assertEqual(result.status, "BLOCKED")
            self.assertTrue(any("QUALIFIED must" in item for item in result.structural_errors))

    def test_cross_source_raw_hash_cannot_be_relabelled(self):
        with tempfile.TemporaryDirectory() as directory:
            run = build_synthetic_network_run(Path(directory) / "run")
            observations = read_json(run / "source_observations.json")
            tradingview = next(row for row in observations["sources"] if row["source_id"] == "tradingview_screeners")
            investing = next(row for row in observations["sources"] if row["source_id"] == "investing_history")
            tradingview["raw_sha256s"] = list(investing["raw_sha256s"])
            write_json(run / "source_observations.json", observations)
            result = SourceNetworkRunValidator(run, self.catalog, "next_session_rank").validate()
            self.assertEqual(result.status, "BLOCKED")
            self.assertTrue(any("same source" in item for item in result.structural_errors))

    def test_artifact_captured_after_decision_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            run = build_synthetic_network_run(Path(directory) / "run")
            manifest = read_json(run / "manifest.json")
            manifest["artifacts"][0]["observed_at"] = "2026-08-07T01:01:00+03:00"
            write_json(run / "manifest.json", manifest)
            result = SourceNetworkRunValidator(run, self.catalog, "next_session_rank").validate()
            self.assertEqual(result.status, "BLOCKED")
            self.assertTrue(any("artifact observed_at" in item for item in result.structural_errors))

    def test_access_receipt_cannot_support_a_finding(self):
        with tempfile.TemporaryDirectory() as directory:
            run = build_synthetic_network_run(Path(directory) / "run")
            manifest = read_json(run / "manifest.json")
            manifest["artifacts"][0]["capture_kind"] = "ACCESS_RECEIPT"
            write_json(run / "manifest.json", manifest)
            result = SourceNetworkRunValidator(run, self.catalog, "next_session_rank").validate()
            self.assertEqual(result.status, "BLOCKED")
            self.assertTrue(any("access receipt" in item for item in result.structural_errors))

    def test_community_only_packet_is_partial_not_market_research(self):
        with tempfile.TemporaryDirectory() as directory:
            run = build_synthetic_network_run(Path(directory) / "run")
            observations = read_json(run / "source_observations.json")
            observations["sources"] = [
                row
                for row in observations["sources"]
                if row["source_id"] in {"telegram_kuwaitstockex", "cma_ifsah"}
            ]
            write_json(run / "source_observations.json", observations)
            findings = [row for row in read_findings(run / "findings.jsonl") if row["source_id"] == "telegram_kuwaitstockex"]
            write_findings(run / "findings.jsonl", findings)
            result = SourceNetworkRunValidator(run, self.catalog, "next_session_rank").validate()
            self.assertEqual(result.status, "PARTIAL", result.to_dict())
            self.assertTrue(any(item.startswith("ROLE_QUORUM:MARKET_DISCOVERY") for item in result.coverage_gaps))

    def test_future_available_finding_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            run = build_synthetic_network_run(Path(directory) / "run")
            rows = read_findings(run / "findings.jsonl")
            rows[0]["available_at"] = "2026-08-07T01:01:00+03:00"
            write_findings(run / "findings.jsonl", rows)
            result = SourceNetworkRunValidator(run, self.catalog, "next_session_rank").validate()
            self.assertEqual(result.status, "BLOCKED")
            self.assertTrue(any("after decision_at" in item for item in result.structural_errors))

    def test_community_cannot_be_relabelled_as_catalyst_truth(self):
        with tempfile.TemporaryDirectory() as directory:
            run = build_synthetic_network_run(Path(directory) / "run")
            rows = read_findings(run / "findings.jsonl")
            sentiment = next(row for row in rows if row["source_id"] == "telegram_kuwaitstockex")
            sentiment["signal_kind"] = "CATALYST"
            write_findings(run / "findings.jsonl", rows)
            result = SourceNetworkRunValidator(run, self.catalog, "next_session_rank").validate()
            self.assertEqual(result.status, "BLOCKED")
            self.assertTrue(any("community findings" in item for item in result.structural_errors))

    def test_evidence_role_must_match_the_source_and_observation(self):
        with tempfile.TemporaryDirectory() as directory:
            run = build_synthetic_network_run(Path(directory) / "run")
            rows = read_findings(run / "findings.jsonl")
            sentiment = next(row for row in rows if row["source_id"] == "telegram_kuwaitstockex")
            sentiment["evidence_roles"] = ["NEWS_ARCHIVE"]
            write_findings(run / "findings.jsonl", rows)
            result = SourceNetworkRunValidator(run, self.catalog, "next_session_rank").validate()
            self.assertEqual(result.status, "BLOCKED")
            self.assertTrue(any("evidence_roles" in item for item in result.structural_errors))

    def test_search_index_or_snippet_cannot_create_a_finding(self):
        with tempfile.TemporaryDirectory() as directory:
            run = build_synthetic_network_run(Path(directory) / "run")
            rows = read_findings(run / "findings.jsonl")
            rows[0]["capture_mode"] = "SEARCH_INDEX"
            write_findings(run / "findings.jsonl", rows)
            result = SourceNetworkRunValidator(run, self.catalog, "next_session_rank").validate()
            self.assertEqual(result.status, "BLOCKED")
            self.assertTrue(any("search index" in item for item in result.structural_errors))

    def test_repost_does_not_increase_score(self):
        with tempfile.TemporaryDirectory() as directory:
            run = build_synthetic_network_run(Path(directory) / "run")
            original_plan = self.pipeline.plan("next_session_rank", network_run_root=run)
            original_score = original_plan["ranked_candidates"][0]["research_score"]
            rows = read_findings(run / "findings.jsonl")
            duplicate = dict(next(row for row in rows if row["source_id"] == "telegram_kuwaitstockex"))
            duplicate["finding_id"] = "f-101-sentiment-repost"
            rows.append(duplicate)
            write_findings(run / "findings.jsonl", rows)
            second_plan = self.pipeline.plan("next_session_rank", network_run_root=run)
            self.assertEqual(second_plan["status"], "RESEARCH_READY")
            self.assertEqual(second_plan["ranked_candidates"][0]["research_score"], original_score)
            self.assertTrue(any(item.startswith("REPOST_ORIGIN_CLUSTERS_DEDUPED") for item in second_plan["reasons"]))

    def test_independent_signal_conflict_forces_watch(self):
        with tempfile.TemporaryDirectory() as directory:
            run = build_synthetic_network_run(Path(directory) / "run")
            rows = read_findings(run / "findings.jsonl")
            conflict = dict(next(row for row in rows if row["finding_id"] == "f-101-technical"))
            conflict.update(
                {
                    "finding_id": "f-101-technical-conflict",
                    "source_id": "tradingview_screeners",
                    "source_url": "https://www.tradingview.com/markets/stocks-kuwait/",
                    "raw_sha256": next(row["raw_sha256"] for row in rows if row["source_id"] == "tradingview_screeners"),
                    "fact_type": "TECHNICAL_CONTEXT",
                    "direction": "NEGATIVE",
                    "strength": 0.9,
                    "materiality": 0.9,
                    "origin_id": "independent-negative-technical-101",
                }
            )
            rows.append(conflict)
            write_findings(run / "findings.jsonl", rows)
            plan = self.pipeline.plan("next_session_rank", network_run_root=run)
            stock = next(row for row in plan["ranked_candidates"] if row["security_code"] == "101")
            self.assertEqual(stock["decision_status"], "WATCH")
            self.assertTrue(stock["source_conflict"])

    def test_same_publisher_contradiction_is_not_independent_confirmation(self):
        with tempfile.TemporaryDirectory() as directory:
            run = build_synthetic_network_run(Path(directory) / "run")
            rows = read_findings(run / "findings.jsonl")
            contradiction = dict(next(row for row in rows if row["finding_id"] == "f-101-technical"))
            contradiction.update(
                {
                    "finding_id": "f-101-technical-same-provider-conflict",
                    "direction": "NEGATIVE",
                    "strength": 0.9,
                    "materiality": 0.9,
                    "origin_id": "same-provider-negative-technical-101",
                }
            )
            rows.append(contradiction)
            write_findings(run / "findings.jsonl", rows)
            plan = self.pipeline.plan("next_session_rank", network_run_root=run)
            stock = next(row for row in plan["ranked_candidates"] if row["security_code"] == "101")
            self.assertFalse(stock["source_conflict"])

    def test_opposite_directions_for_different_events_are_not_a_conflict(self):
        with tempfile.TemporaryDirectory() as directory:
            run = build_synthetic_network_run(Path(directory) / "run")
            rows = read_findings(run / "findings.jsonl")
            negative = dict(next(row for row in rows if row["finding_id"] == "f-101-technical"))
            negative.update(
                {
                    "finding_id": "f-101-unrelated-negative-technical",
                    "source_id": "tradingview_screeners",
                    "source_url": "https://www.tradingview.com/markets/stocks-kuwait/",
                    "raw_sha256": next(
                        row["raw_sha256"]
                        for row in rows
                        if row["source_id"] == "tradingview_screeners"
                    ),
                    "fact_type": "TECHNICAL_CONTEXT",
                    "direction": "NEGATIVE",
                    "strength": 0.9,
                    "materiality": 0.9,
                    "origin_id": "independent-unrelated-negative-technical-101",
                    "event_key": "different-technical-event-101",
                }
            )
            rows.append(negative)
            write_findings(run / "findings.jsonl", rows)
            plan = self.pipeline.plan("next_session_rank", network_run_root=run)
            stock = next(
                row for row in plan["ranked_candidates"] if row["security_code"] == "101"
            )
            self.assertFalse(stock["source_conflict"])

    def test_primary_confirmation_must_match_the_same_catalyst_event(self):
        with tempfile.TemporaryDirectory() as directory:
            run = build_synthetic_network_run(Path(directory) / "run")
            rows = read_findings(run / "findings.jsonl")
            reported = next(row for row in rows if row["finding_id"] == "f-101-catalyst-news")
            reported["event_key"] = "different-unconfirmed-positive-event"
            write_findings(run / "findings.jsonl", rows)
            plan = self.pipeline.plan("next_session_rank", network_run_root=run)
            stock = next(row for row in plan["ranked_candidates"] if row["security_code"] == "101")
            self.assertEqual(stock["decision_status"], "WATCH")
            self.assertFalse(stock["all_directional_catalysts_primary_confirmed"])
            self.assertIn("DIRECTIONAL_CATALYST_NOT_PRIMARY_CONFIRMED", stock["reason_codes"])

    def test_same_news_event_cannot_manufacture_quorum_across_publishers(self):
        with tempfile.TemporaryDirectory() as directory:
            run = build_synthetic_network_run(Path(directory) / "run", include_boursa=False)
            rows = read_findings(run / "findings.jsonl")
            reuters = next(row for row in rows if row["finding_id"] == "f-101-catalyst-news")
            for row in rows:
                if "NEWS_ARCHIVE" in row["evidence_roles"]:
                    row["event_key"] = reuters["event_key"]
            write_findings(run / "findings.jsonl", rows)
            result = SourceNetworkRunValidator(run, self.catalog, "next_session_rank").validate()
            self.assertEqual(result.status, "PARTIAL", result.to_dict())
            self.assertIn("ROLE_QUORUM:NEWS_ARCHIVE:1/2", result.coverage_gaps)

    def test_incomplete_universe_cannot_claim_full_market_best(self):
        with tempfile.TemporaryDirectory() as directory:
            run = build_synthetic_network_run(Path(directory) / "run")
            payload = read_json(run / "research_run.json")
            payload.update({"scope": "FULL_MARKET", "expected_universe_count": 10, "covered_universe_count": 2})
            write_json(run / "research_run.json", payload)
            universe = read_json(run / "universe.json")
            universe["expected_security_codes"] = [str(code) for code in range(101, 111)]
            write_json(run / "universe.json", universe)
            plan = self.pipeline.plan("next_session_rank", network_run_root=run)
            self.assertEqual(plan["status"], "RESEARCH_READY")
            self.assertTrue(all(row["scope_label"] == "CANDIDATE_SET_RESEARCH_RANK" for row in plan["ranked_candidates"]))
            self.assertIn("FULL_MARKET_LABEL_FORBIDDEN_UNRECONCILED_UNIVERSE", plan["reasons"])

    def test_counts_alone_cannot_claim_full_market(self):
        with tempfile.TemporaryDirectory() as directory:
            run = build_synthetic_network_run(Path(directory) / "run")
            (run / "universe.json").unlink()
            payload = read_json(run / "research_run.json")
            payload["scope"] = "FULL_MARKET"
            write_json(run / "research_run.json", payload)
            plan = self.pipeline.plan("next_session_rank", network_run_root=run)
            self.assertEqual(plan["status"], "SOURCE_NETWORK_BLOCKED")
            self.assertFalse(plan["network_run"]["exact_universe_reconciled"])
            self.assertFalse(plan["network_run"]["claim_boundaries"]["full_market_claim_allowed"])
            self.assertEqual(plan["ranked_candidates"], [])
            self.assertIn("MISSING_SECURITY_IDENTITY_RECEIPT", plan["reasons"])

    def test_exact_universe_with_a_member_role_gap_cannot_claim_full_market(self):
        with tempfile.TemporaryDirectory() as directory:
            run = build_synthetic_network_run(Path(directory) / "run")
            payload = read_json(run / "research_run.json")
            payload["scope"] = "FULL_MARKET"
            write_json(run / "research_run.json", payload)
            plan = self.pipeline.plan("next_session_rank", network_run_root=run)
            self.assertEqual(plan["status"], "RESEARCH_PARTIAL")
            self.assertTrue(plan["network_run"]["exact_universe_reconciled"])
            self.assertFalse(plan["full_market_claim_allowed"])
            self.assertFalse(plan["network_run"]["claim_boundaries"]["full_market_claim_allowed"])
            self.assertTrue(
                all(
                    row["scope_label"] == "CANDIDATE_SET_RESEARCH_RANK"
                    for row in plan["ranked_candidates"]
                )
            )

    def test_legacy_live_probe_without_bytes_is_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "probe.json"
            write_json(
                path,
                {
                    "schema_version": "3.0-access-probe",
                    "observed_at": "2026-08-07T01:00:00+03:00",
                    "sources": [
                        {
                            "source_id": "tradingview_screeners",
                            "state": "AVAILABLE",
                            "tested_url": "https://www.tradingview.com/markets/stocks-kuwait/",
                            "observation": "Page opened",
                            "data_quality_flags": [],
                        }
                    ],
                },
            )
            report = validate_live_probe(path, self.catalog)
            self.assertEqual(report["status"], "BLOCKED")
            self.assertIn("unknown or missing top-level fields", report["errors"][0])


if __name__ == "__main__":
    unittest.main()
