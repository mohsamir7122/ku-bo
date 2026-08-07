from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

from kubo.pipeline import ResearchPipeline
from kubo.research_rank import rank_research_candidates
from kubo.source_network import (
    NetworkRunContract,
    NetworkRunValidation,
    ResearchFinding,
    SourceNetworkCatalog,
    SourceNetworkRunValidator,
)
from kubo.synthetic_network import build_synthetic_network_run


ROOT = Path(__file__).resolve().parents[1]


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def read_findings(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_findings(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )


class SourceNetworkHardeningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = SourceNetworkCatalog(ROOT / "config")
        self.pipeline = ResearchPipeline(ROOT)

    def test_quorum_is_enforced_per_security_at_ranking_time(self):
        with tempfile.TemporaryDirectory() as directory:
            run = build_synthetic_network_run(Path(directory) / "run")
            plan = self.pipeline.plan("next_session_rank", network_run_root=run)
            self.assertEqual(plan["status"], "RESEARCH_READY", plan)
            stock = next(
                row for row in plan["ranked_candidates"] if row["security_code"] == "102"
            )
            self.assertNotEqual(stock["decision_status"], "RESEARCH_CANDIDATE")
            self.assertFalse(stock["selected"])
            self.assertEqual(stock["per_security_role_coverage"]["NEWS_ARCHIVE"], 1)
            self.assertIn(
                "PER_SECURITY_ROLE_QUORUM:NEWS_ARCHIVE:1/2",
                stock["reason_codes"],
            )

    def test_long_term_policy_excludes_all_community_risk_contribution(self):
        policy = self.catalog.policy_for(
            "two_hundred_fifty_two_session_annual_investment"
        )
        decision_at = datetime(2026, 8, 7, tzinfo=timezone.utc)
        contract = NetworkRunContract(
            "community-cap-test",
            "two_hundred_fifty_two_session_annual_investment",
            decision_at,
            "Asia/Kuwait",
            "CANDIDATE_SET",
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
        )
        finding = ResearchFinding(
            "community-risk",
            "101",
            "AAA",
            "telegram_kuwaitstockex",
            "https://t.me/s/kuwaitstockex",
            decision_at,
            decision_at,
            "PROSPECTIVE",
            "B",
            "0" * 64,
            frozenset({"COMMUNITY_SENTIMENT"}),
            "RISK",
            "POSITIVE",
            1.0,
            1.0,
            "community-risk-origin",
            "community-risk-event",
            "Community risk must not enter a long-term score.",
            "RUMOR_LEAD",
        )
        validation = NetworkRunValidation(
            "PASS",
            (),
            (),
            (),
            contract,
            policy,
            (),
            (),
            (finding,),
            {},
            1,
            False,
            False,
        )
        row = rank_research_candidates(
            validation,
            source_map=self.catalog.sources,
        )[0]
        self.assertEqual(policy.sentiment_contribution_cap, 0.0)
        self.assertEqual(row["signal_contributions"]["RISK"], 0.0)
        self.assertEqual(row["community_contribution_total"], 0.0)
        self.assertEqual(row["independent_source_groups"], 0)

    def test_official_confirmation_is_not_lost_when_editorial_copy_scores_higher(self):
        with tempfile.TemporaryDirectory() as directory:
            run = build_synthetic_network_run(Path(directory) / "run")
            rows = read_findings(run / "findings.jsonl")
            for row in rows:
                if row["finding_id"] == "f-101-catalyst-confirmation":
                    row["strength"] = 0.1
                    row["materiality"] = 0.1
                elif row["finding_id"] == "f-102-kuna-context":
                    row.update(
                        {
                            "finding_id": "f-101-kuna-risk",
                            "security_code": "101",
                            "ticker": "AAA",
                            "direction": "POSITIVE",
                            "strength": 0.6,
                            "materiality": 0.6,
                            "origin_id": "kuna-independent-101",
                            "event_key": "kuna-risk-101",
                            "claim_text": "Independent synthetic risk context.",
                        }
                    )
            write_findings(run / "findings.jsonl", rows)
            plan = self.pipeline.plan("next_session_rank", network_run_root=run)
            stock = next(
                row
                for row in plan["ranked_candidates"]
                if row["security_code"] == "101"
            )
            self.assertTrue(plan["network_run"]["official_confirmation_available"])
            self.assertTrue(stock["official_catalyst_confirmed"])
            self.assertTrue(stock["all_directional_catalysts_primary_confirmed"])
            self.assertEqual(stock["decision_status"], "RESEARCH_CANDIDATE")
            self.assertNotIn(
                "DIRECTIONAL_CATALYST_NOT_PRIMARY_CONFIRMED",
                stock["reason_codes"],
            )

    def test_zero_result_does_not_fill_role_or_source_quorum(self):
        with tempfile.TemporaryDirectory() as directory:
            run = build_synthetic_network_run(
                Path(directory) / "run", include_boursa=False
            )
            observations = read_json(run / "source_observations.json")
            kuna = next(
                row for row in observations["sources"] if row["source_id"] == "kuna"
            )
            kuna.update(
                {
                    "query_status": "ZERO_RESULT",
                    "qualified_items": 0,
                    "zero_result": True,
                }
            )
            write_json(run / "source_observations.json", observations)
            findings = [
                row
                for row in read_findings(run / "findings.jsonl")
                if row["source_id"] != "kuna"
            ]
            write_findings(run / "findings.jsonl", findings)
            result = SourceNetworkRunValidator(
                run, self.catalog, "next_session_rank"
            ).validate()
            self.assertEqual(result.status, "PARTIAL", result.to_dict())
            self.assertEqual(result.role_coverage.get("NEWS_ARCHIVE"), 1)
            self.assertEqual(result.independent_sources, 4)

    def test_neutral_and_zero_value_findings_do_not_raise_candidate_coverage(self):
        with tempfile.TemporaryDirectory() as directory:
            run = build_synthetic_network_run(Path(directory) / "run")
            rows = read_findings(run / "findings.jsonl")
            zero = dict(next(row for row in rows if row["finding_id"] == "f-101-sentiment"))
            zero.update(
                {
                    "finding_id": "f-102-zero-sentiment",
                    "security_code": "102",
                    "ticker": "BBB",
                    "strength": 0.0,
                    "origin_id": "zero-sentiment-102",
                    "event_key": "zero-sentiment-102",
                }
            )
            rows.append(zero)
            write_findings(run / "findings.jsonl", rows)
            plan = self.pipeline.plan("next_session_rank", network_run_root=run)
            stock = next(
                row for row in plan["ranked_candidates"] if row["security_code"] == "102"
            )
            self.assertEqual(stock["independent_source_groups"], 3)
            self.assertAlmostEqual(stock["evidence_coverage"], 0.5)
            self.assertEqual(stock["signal_contributions"]["SENTIMENT"], 0.0)

    def test_stale_finding_is_rejected_from_rank_without_blocking_fresh_packet(self):
        with tempfile.TemporaryDirectory() as directory:
            run = build_synthetic_network_run(Path(directory) / "run")
            rows = read_findings(run / "findings.jsonl")
            sentiment = next(row for row in rows if row["finding_id"] == "f-101-sentiment")
            sentiment["published_at"] = "2026-08-01T00:00:00+03:00"
            sentiment["available_at"] = "2026-08-01T00:00:00+03:00"
            write_findings(run / "findings.jsonl", rows)
            plan = self.pipeline.plan("next_session_rank", network_run_root=run)
            self.assertEqual(plan["status"], "RESEARCH_READY", plan)
            self.assertIn("STALE_FINDING_REJECTED:f-101-sentiment", plan["reasons"])
            stock = next(
                row for row in plan["ranked_candidates"] if row["security_code"] == "101"
            )
            self.assertEqual(stock["signal_contributions"]["SENTIMENT"], 0.0)

    def test_declared_raw_byte_usage_must_reconcile_to_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            run = build_synthetic_network_run(Path(directory) / "run")
            contract = read_json(run / "research_run.json")
            contract["usage"]["raw_bytes"] += 1
            write_json(run / "research_run.json", contract)
            result = SourceNetworkRunValidator(
                run, self.catalog, "next_session_rank"
            ).validate()
            self.assertEqual(result.status, "BLOCKED")
            self.assertTrue(
                any("RAW_BYTE_USAGE_MISMATCH" in item for item in result.structural_errors)
            )

    def test_explicit_fact_type_must_be_in_source_fact_eligibility(self):
        with tempfile.TemporaryDirectory() as directory:
            run = build_synthetic_network_run(Path(directory) / "run")
            rows = read_findings(run / "findings.jsonl")
            rows[0]["fact_type"] = "OFFICIAL_COMPANY_FACT"
            write_findings(run / "findings.jsonl", rows)
            result = SourceNetworkRunValidator(
                run, self.catalog, "next_session_rank"
            ).validate()
            self.assertEqual(result.status, "BLOCKED")
            self.assertTrue(
                any("fact_eligibility" in item for item in result.structural_errors)
            )

    def test_fact_type_is_required_for_every_finding(self):
        with tempfile.TemporaryDirectory() as directory:
            run = build_synthetic_network_run(Path(directory) / "run")
            rows = read_findings(run / "findings.jsonl")
            rows[0].pop("fact_type")
            write_findings(run / "findings.jsonl", rows)
            result = SourceNetworkRunValidator(
                run, self.catalog, "next_session_rank"
            ).validate()
            self.assertEqual(result.status, "BLOCKED")
            self.assertTrue(
                any("fact_type is required" in item for item in result.structural_errors)
            )

    def test_bare_boolean_cannot_activate_dynamic_issuer_domain(self):
        with tempfile.TemporaryDirectory() as directory:
            run = build_synthetic_network_run(Path(directory) / "run")
            manifest = read_json(run / "manifest.json")
            disclosure_artifact = next(
                row
                for row in manifest["artifacts"]
                if row["source_id"] == "boursa_disclosure_archive"
            )
            disclosure_artifact.update(
                {
                    "source_id": "issuer_ir_verified",
                    "source_url": "https://issuer.example/ir",
                    "runtime_authority_verified": True,
                }
            )
            write_json(run / "manifest.json", manifest)
            observations = read_json(run / "source_observations.json")
            disclosure_observation = next(
                row
                for row in observations["sources"]
                if row["source_id"] == "boursa_disclosure_archive"
            )
            disclosure_observation.update(
                {
                    "source_id": "issuer_ir_verified",
                    "roles_observed": ["OFFICIAL_EVENT", "NEWS_ARCHIVE"],
                }
            )
            write_json(run / "source_observations.json", observations)
            rows = read_findings(run / "findings.jsonl")
            for row in rows:
                if row["source_id"] == "boursa_disclosure_archive":
                    row.update(
                        {
                            "source_id": "issuer_ir_verified",
                            "source_url": "https://issuer.example/ir",
                        }
                    )
            write_findings(run / "findings.jsonl", rows)
            result = SourceNetworkRunValidator(
                run, self.catalog, "next_session_rank"
            ).validate()
            self.assertEqual(result.status, "BLOCKED")
            self.assertTrue(
                any("structured runtime_authority" in item for item in result.structural_errors)
            )

    def test_licensed_source_requires_entitlement_receipt_and_activation(self):
        with tempfile.TemporaryDirectory() as directory:
            run = build_synthetic_network_run(Path(directory) / "run")
            manifest = read_json(run / "manifest.json")
            artifact = next(
                row
                for row in manifest["artifacts"]
                if row["source_id"] == "tradingview_screeners"
            )
            artifact.update(
                {
                    "source_id": "ice_kuwait_archive",
                    "source_url": "https://developer.ice.com/kuwait/export",
                }
            )
            write_json(run / "manifest.json", manifest)
            observations = read_json(run / "source_observations.json")
            observation = next(
                row
                for row in observations["sources"]
                if row["source_id"] == "tradingview_screeners"
            )
            observation.update(
                {
                    "source_id": "ice_kuwait_archive",
                    "access_mode": "LICENSED_VENDOR",
                    "enabled_for_run": True,
                    "activation_id": "licensed-test-activation",
                    "activation_evidence_sha256": artifact["sha256"],
                }
            )
            write_json(run / "source_observations.json", observations)
            rows = read_findings(run / "findings.jsonl")
            for row in rows:
                if row["source_id"] == "tradingview_screeners":
                    row.update(
                        {
                            "source_id": "ice_kuwait_archive",
                            "source_url": "https://developer.ice.com/kuwait/export",
                        }
                    )
            write_findings(run / "findings.jsonl", rows)
            result = SourceNetworkRunValidator(
                run, self.catalog, "next_session_rank"
            ).validate()
            self.assertEqual(result.status, "BLOCKED")
            self.assertTrue(
                any("entitlement_evidence_sha256" in item for item in result.structural_errors)
            )

    def test_social_connectors_are_disabled_runtime_bound_and_community_only(self):
        source_ids = (
            "facebook_public_community",
            "instagram_public_community",
            "x_public_community",
            "tiktok_public_community",
        )
        for source_id in source_ids:
            source = self.catalog.sources[source_id]
            self.assertEqual(source.source_class, "COMMUNITY")
            self.assertEqual(source.roles, frozenset({"COMMUNITY_SENTIMENT"}))
            self.assertFalse(source.enabled_by_default)
            self.assertTrue(source.requires_runtime_domain_registry)
            self.assertNotIn("COMPANY_FACT", source.fact_eligibility)
        self.assertEqual(
            self.catalog.sources["facebook_public_community"].independence_group,
            self.catalog.sources["instagram_public_community"].independence_group,
        )

    def test_near_duplicate_text_with_new_ids_does_not_change_score(self):
        with tempfile.TemporaryDirectory() as directory:
            run = build_synthetic_network_run(Path(directory) / "run")
            rows = read_findings(run / "findings.jsonl")
            reuters = next(row for row in rows if row["finding_id"] == "f-101-catalyst-news")
            reuters["claim_text"] = (
                "Company announced a major new contract award with material positive revenue impact"
            )
            write_findings(run / "findings.jsonl", rows)
            baseline = self.pipeline.plan("next_session_rank", network_run_root=run)
            baseline_score = next(
                row
                for row in baseline["ranked_candidates"]
                if row["security_code"] == "101"
            )["research_score"]

            rows = read_findings(run / "findings.jsonl")
            duplicate = dict(next(row for row in rows if row["finding_id"] == "f-101-catalyst-news"))
            kuna_hash = next(
                row["raw_sha256"] for row in rows if row["source_id"] == "kuna"
            )
            duplicate.update(
                {
                    "finding_id": "f-101-near-duplicate-news",
                    "source_id": "kuna",
                    "source_url": "https://www.kuna.net.kw/",
                    "raw_sha256": kuna_hash,
                    "fact_type": "GOVERNMENT_NEWS",
                    "timing_grade": "B",
                    "strength": 0.35,
                    "materiality": 0.35,
                    "origin_id": "new-apparently-independent-origin",
                    "event_key": "new-apparently-independent-event",
                    "claim_text": (
                        "Company announced a major new contract award with material positive revenue impact today"
                    ),
                }
            )
            rows.append(duplicate)
            write_findings(run / "findings.jsonl", rows)
            hardened = self.pipeline.plan("next_session_rank", network_run_root=run)
            hardened_score = next(
                row
                for row in hardened["ranked_candidates"]
                if row["security_code"] == "101"
            )["research_score"]
            self.assertEqual(hardened_score, baseline_score)

    def test_candidate_set_identity_binding_rejects_fake_ticker(self):
        with tempfile.TemporaryDirectory() as directory:
            run = build_synthetic_network_run(Path(directory) / "run")
            rows = read_findings(run / "findings.jsonl")
            rows[0]["ticker"] = "FAKE"
            write_findings(run / "findings.jsonl", rows)
            result = SourceNetworkRunValidator(
                run, self.catalog, "next_session_rank"
            ).validate()
            self.assertEqual(result.status, "BLOCKED")
            self.assertTrue(
                any("ticker mismatch" in item for item in result.structural_errors)
            )

    def test_effective_identity_bindings_are_required_for_every_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            for scope in ("NAMED_SECURITIES", "CANDIDATE_SET", "FULL_MARKET"):
                with self.subTest(scope=scope):
                    run = build_synthetic_network_run(Path(directory) / scope)
                    contract = read_json(run / "research_run.json")
                    contract["scope"] = scope
                    write_json(run / "research_run.json", contract)
                    universe = read_json(run / "universe.json")
                    universe.pop("securities")
                    write_json(run / "universe.json", universe)
                    result = SourceNetworkRunValidator(
                        run, self.catalog, "next_session_rank"
                    ).validate()
                    self.assertEqual(result.status, "BLOCKED")
                    self.assertTrue(
                        any(
                            "securities must be a non-empty list" in item
                            for item in result.structural_errors
                        )
                    )

    def test_candidate_set_rejects_stale_membership_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            run = build_synthetic_network_run(Path(directory) / "run")
            universe = read_json(run / "universe.json")
            universe["membership_as_of"] = "2026-08-06T23:59:00+03:00"
            write_json(run / "universe.json", universe)
            result = SourceNetworkRunValidator(
                run, self.catalog, "next_session_rank"
            ).validate()
            self.assertEqual(result.status, "BLOCKED")
            self.assertTrue(
                any(
                    "membership_as_of must be on the decision_at date" in item
                    for item in result.structural_errors
                )
            )

    def test_finding_url_must_equal_the_referenced_artifact_url(self):
        with tempfile.TemporaryDirectory() as directory:
            run = build_synthetic_network_run(Path(directory) / "run")
            rows = read_findings(run / "findings.jsonl")
            finding = next(
                row for row in rows if row["source_id"] == "investing_history"
            )
            finding["source_url"] = "https://www.investing.com/equities/another-security"
            write_findings(run / "findings.jsonl", rows)
            result = SourceNetworkRunValidator(
                run, self.catalog, "next_session_rank"
            ).validate()
            self.assertEqual(result.status, "BLOCKED")
            self.assertTrue(
                any("does not match" in item for item in result.structural_errors),
                result.to_dict(),
            )

    def test_full_market_label_requires_substantive_coverage_for_every_member(self):
        with tempfile.TemporaryDirectory() as directory:
            run = build_synthetic_network_run(Path(directory) / "run")
            contract = read_json(run / "research_run.json")
            contract["scope"] = "FULL_MARKET"
            write_json(run / "research_run.json", contract)
            rows = read_findings(run / "findings.jsonl")
            for row in rows:
                if row["security_code"] == "102":
                    row["security_code"] = "101"
                    row["ticker"] = "AAA"
            write_findings(run / "findings.jsonl", rows)
            plan = self.pipeline.plan("next_session_rank", network_run_root=run)
            self.assertEqual(plan["status"], "RESEARCH_READY", plan)
            self.assertFalse(plan["network_run"]["exact_universe_reconciled"])
            self.assertEqual(len(plan["ranked_candidates"]), 1)
            self.assertEqual(
                plan["ranked_candidates"][0]["scope_label"],
                "CANDIDATE_SET_RESEARCH_RANK",
            )
            self.assertIn(
                "FULL_MARKET_SUBSTANTIVE_FINDING_COVERAGE_INCOMPLETE:102",
                plan["reasons"],
            )

    def test_neutral_findings_cannot_fill_global_source_or_role_quorum(self):
        with tempfile.TemporaryDirectory() as directory:
            run = build_synthetic_network_run(Path(directory) / "run")
            rows = read_findings(run / "findings.jsonl")
            for row in rows:
                if row["source_id"] in {"kuna", "boursa_disclosure_archive"}:
                    row["direction"] = "NEUTRAL"
            write_findings(run / "findings.jsonl", rows)
            result = SourceNetworkRunValidator(
                run, self.catalog, "next_session_rank"
            ).validate()
            self.assertEqual(result.status, "PARTIAL", result.to_dict())
            self.assertEqual(result.role_coverage.get("NEWS_ARCHIVE"), 1)
            self.assertIn("ROLE_QUORUM:NEWS_ARCHIVE:1/2", result.coverage_gaps)


if __name__ == "__main__":
    unittest.main()
