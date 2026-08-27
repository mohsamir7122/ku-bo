from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator, FormatChecker

from kubo.research_network import (
    ResearchNetworkError,
    build_conflict_ledger,
    build_research_observation,
    detect_copied_news,
    resolve_trusted_source,
    run_research_network,
    strict_forecast_gate,
    validate_research_observation,
    validate_research_source_registry,
)
from kubo.hashing import canonical_json_bytes, hash_json


ROOT = Path(__file__).resolve().parents[1]
KNOWN = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)


SOURCE_DETAILS = {
    "boursa_current": (
        "OFFICIAL_PRIMARY",
        "https://www.boursakuwait.com.kw/en/announcements/example",
        "Boursa Kuwait",
    ),
    "investing_history": (
        "STRUCTURED_SECONDARY",
        "https://sa.investing.com/equities/kuwait",
        "Investing.com",
    ),
    "mubasher_kuwait": (
        "STRUCTURED_SECONDARY",
        "https://english.mubasher.info/markets/BK/stock/example",
        "Mubasher",
    ),
    "reuters_middle_east": (
        "RELIABLE_NEWS",
        "https://www.reuters.com/world/middle-east/example-2026-08-27/",
        "Reuters",
    ),
    "kuwait_times_editorial": (
        "RELIABLE_NEWS",
        "https://kuwaittimes.com/article/example",
        "Kuwait Times",
    ),
    "indexsignal_forum": (
        "COMMUNITY_DISCOVERY",
        "https://www.indexsignal.com/community/threads/example/",
        "IndexSignal",
    ),
}


def input_row(
    source_id: str = "boursa_current",
    *,
    observation_id: str = "obs-001",
    claim_type: str = "OFFICIAL_FACT",
    claim_key: str = "KFH.disclosure.20260827",
    field_name: str = "disclosure_status",
    claim_value="PUBLISHED",
    origin_id: str = "origin-001",
    claim_text: str = "The issuer published a material disclosure before the cutoff.",
) -> dict[str, object]:
    role, url, publisher = SOURCE_DETAILS[source_id]
    observed = KNOWN - timedelta(minutes=10)
    return {
        "observation_id": observation_id,
        "market": "KUWAIT",
        "evidence_class": "SYNTHETIC_CONTRACT",
        "source_id": source_id,
        "claimed_source_role": role,
        "security_code": "KFH",
        "claim_id": observation_id.replace("obs", "claim"),
        "claim_key": claim_key,
        "claim_type": claim_type,
        "field_name": field_name,
        "claim_value": claim_value,
        "claim_text": claim_text,
        "publisher": publisher,
        "canonical_url": url,
        "published_at": (KNOWN - timedelta(minutes=20)).isoformat(),
        "event_at": (KNOWN - timedelta(minutes=15)).isoformat(),
        "observed_at": observed.isoformat(),
        "fetched_at": (KNOWN + timedelta(minutes=5)).isoformat(),
        "provider_as_of": observed.isoformat(),
        "content_hash": hashlib.sha256((observation_id + source_id).encode()).hexdigest(),
        "access_method": "PUBLIC_PAGE",
        "transformation_history": [],
        "origin_id": origin_id,
    }


class ResearchSourceRegistryTests(unittest.TestCase):
    def test_registry_is_schema_valid_and_bound_to_catalog(self) -> None:
        schema = json.loads(
            (ROOT / "schemas" / "research-source-registry.schema.json").read_text()
        )
        payload = json.loads(
            (ROOT / "config" / "research_source_registry.json").read_text()
        )
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(payload)
        report = validate_research_source_registry(ROOT)
        self.assertEqual(report["status"], "PASS_TRUSTED_SOURCE_REGISTRY")
        self.assertGreater(report["mapped_source_count"], 40)
        self.assertEqual(report["required_named_source_count"], 11)

    def test_source_role_is_resolved_not_trusted_from_caller(self) -> None:
        resolved = resolve_trusted_source(
            ROOT, "indexsignal_forum", claimed_source_role="COMMUNITY_DISCOVERY"
        )
        self.assertEqual(resolved.source_role, "COMMUNITY_DISCOVERY")
        self.assertEqual(resolved.credibility_ceiling, 25)
        with self.assertRaisesRegex(ResearchNetworkError, "caller-supplied"):
            resolve_trusted_source(
                ROOT, "indexsignal_forum", claimed_source_role="OFFICIAL_PRIMARY"
            )


class ResearchObservationTests(unittest.TestCase):
    def build(self, row: dict[str, object]) -> dict[str, object]:
        return build_research_observation(ROOT, row, known_at=KNOWN)

    def test_full_provenance_and_claim_level_credibility_are_emitted(self) -> None:
        observation = self.build(input_row())
        required = {
            "publisher",
            "canonical_url",
            "published_at",
            "event_at",
            "observed_at",
            "fetched_at",
            "provider_as_of",
            "content_hash",
            "source_role",
            "access_method",
            "transformation_history",
        }
        self.assertTrue(required <= set(observation))
        self.assertEqual(observation["source_role"], "OFFICIAL_PRIMARY")
        self.assertIsInstance(observation["credibility_score"], int)
        self.assertGreaterEqual(observation["credibility_score"], 0)
        self.assertLessEqual(observation["credibility_score"], 100)
        self.assertFalse(observation["credibility_score_is_stock_probability"])
        self.assertEqual(observation["admission_status"], "WATCH_ONLY")
        schema = json.loads(
            (ROOT / "schemas" / "research-observation.schema.json").read_text()
        )
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(observation)

    def test_indexsignal_is_capped_and_cannot_supply_price_or_official_fact(self) -> None:
        discovery = self.build(
            input_row(
                "indexsignal_forum",
                claim_type="DISCOVERY",
                field_name="rumor_lead",
                claim_value="UNVERIFIED_LEAD",
            )
        )
        self.assertLessEqual(discovery["credibility_score"], 25)
        self.assertEqual(discovery["source_role"], "COMMUNITY_DISCOVERY")
        for forbidden in ("PRICE", "OFFICIAL_FACT"):
            row = input_row("indexsignal_forum", claim_type=forbidden)
            with self.subTest(forbidden=forbidden), self.assertRaisesRegex(
                ResearchNetworkError, "claim type"
            ):
                self.build(row)

    def test_temporal_leakage_is_rejected(self) -> None:
        for field in ("published_at", "event_at", "observed_at", "provider_as_of"):
            row = input_row()
            row[field] = (KNOWN + timedelta(seconds=1)).isoformat()
            with self.subTest(field=field), self.assertRaisesRegex(
                ResearchNetworkError, "TEMPORAL_LEAKAGE"
            ):
                self.build(row)

    def test_foreign_domain_and_broken_transformation_chain_are_rejected(self) -> None:
        foreign = input_row()
        foreign["canonical_url"] = "https://evil.example/copied"
        with self.assertRaisesRegex(ResearchNetworkError, "trusted source domains"):
            self.build(foreign)
        broken = input_row()
        broken["transformation_history"] = [
            {
                "step_id": "parse-1",
                "tool_version": "1.0",
                "applied_at": (KNOWN + timedelta(minutes=6)).isoformat(),
                "input_sha256": "f" * 64,
                "output_sha256": "e" * 64,
            }
        ]
        with self.assertRaisesRegex(ResearchNetworkError, "hash chain"):
            self.build(broken)

    def test_nan_claim_value_is_rejected(self) -> None:
        row = input_row(claim_value=float("nan"))
        with self.assertRaisesRegex(ResearchNetworkError, "finite canonical JSON"):
            self.build(row)

    def test_serialized_credibility_self_promotion_is_rejected(self) -> None:
        observation = self.build(input_row())
        observation["credibility_score"] = 100
        with self.assertRaisesRegex(ResearchNetworkError, "do not recompute"):
            validate_research_observation(ROOT, observation)

    def test_evidence_class_must_be_explicit(self) -> None:
        row = input_row()
        row["evidence_class"] = "REAL_OR_SYNTHETIC_UNKNOWN"
        with self.assertRaisesRegex(ResearchNetworkError, "evidence_class"):
            self.build(row)


class CopyAndConflictTests(unittest.TestCase):
    def build(self, row: dict[str, object]) -> dict[str, object]:
        return build_research_observation(ROOT, row, known_at=KNOWN)

    def test_syndicated_news_from_one_origin_is_one_confirmation(self) -> None:
        text = (
            "A material company event was reported with the same detailed wording "
            "and attribution to one original newswire source before the cutoff."
        )
        reuters = self.build(
            input_row(
                "reuters_middle_east",
                observation_id="obs-news-1",
                claim_type="NEWS_EVENT",
                origin_id="reuters:wire-123",
                claim_text=text,
            )
        )
        copied = self.build(
            input_row(
                "kuwait_times_editorial",
                observation_id="obs-news-2",
                claim_type="NEWS_EVENT",
                origin_id="reuters:wire-123",
                claim_text=text,
            )
        )
        report = detect_copied_news([reuters, copied])
        self.assertEqual(report["news_observation_count"], 2)
        self.assertEqual(report["independent_origin_count"], 1)
        self.assertTrue(report["clusters"][0]["copied_or_syndicated"])
        self.assertEqual(report["clusters"][0]["independent_confirmation_units"], 1)

    def test_price_conflict_abstains_without_averaging(self) -> None:
        investing = self.build(
            input_row(
                "investing_history",
                observation_id="obs-price-1",
                claim_type="PRICE",
                claim_key="KFH.close.20260827",
                field_name="close_kwd",
                claim_value=0.725,
            )
        )
        mubasher = self.build(
            input_row(
                "mubasher_kuwait",
                observation_id="obs-price-2",
                claim_type="PRICE",
                claim_key="KFH.close.20260827",
                field_name="close_kwd",
                claim_value=0.735,
            )
        )
        ledger = build_conflict_ledger([investing, mubasher])
        self.assertEqual(ledger["overall_disposition"], "ABSTAIN")
        self.assertEqual(ledger["conflict_count"], 1)
        self.assertEqual(ledger["conflicts"][0]["aggregation_method"], "NO_AVERAGING")
        self.assertIsNone(ledger["conflicts"][0]["resolved_value"])
        self.assertFalse(ledger["conflicting_values_averaged"])


class ResearchModeSeparationTests(unittest.TestCase):
    def test_current_repository_strict_forecast_is_locked(self) -> None:
        gate = strict_forecast_gate(ROOT)
        self.assertEqual(gate["status"], "LOCKED")
        self.assertFalse(gate["publish_allowed"])
        self.assertIn("TRAINING_VALIDATION_RECEIPT_MISSING", gate["blockers"])
        self.assertIn("BLIND_TEST_VALIDATION_RECEIPT_MISSING", gate["blockers"])

    def test_empty_research_network_is_operational_but_abstains(self) -> None:
        report = run_research_network(ROOT, [], generated_at=KNOWN)
        self.assertTrue(report["software_operational"])
        self.assertFalse(report["live_evidence_operational"])
        self.assertEqual(report["decision"], "ABSTAIN")
        self.assertEqual(report["real_observation_count"], 0)
        self.assertEqual(report["strict_forecast"]["status"], "LOCKED")
        schema = json.loads(
            (ROOT / "schemas" / "research-network-run.schema.json").read_text()
        )
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(report)

    def test_synthetic_observation_never_contributes_to_live_rank(self) -> None:
        synthetic = build_research_observation(ROOT, input_row(), known_at=KNOWN)
        report = run_research_network(ROOT, [synthetic], generated_at=KNOWN)
        self.assertEqual(report["synthetic_observation_count"], 1)
        self.assertEqual(report["real_observation_count"], 0)
        self.assertEqual(report["securities"][0]["decision"], "ABSTAIN")
        self.assertIn("NO_REAL_OBSERVATIONS", report["securities"][0]["reasons"])

    def test_readiness_receipt_requires_real_counts_blind_controls_and_digest(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "artifacts" / "validated" / "forecast-readiness.json"
            path.parent.mkdir(parents=True)
            payload = {
                "schema_version": "1.0",
                "market": "KUWAIT",
                "evidence_class": "REAL_MARKET_EVIDENCE",
                "run_id": "validated-readiness-fixture",
                "code_sha": "a" * 40,
                "training": {
                    "status": "VALIDATED",
                    "ten_year_events": 20,
                    "five_year_events": 50,
                    "additional_events": 300,
                    "unique_events": 370,
                    "temporal_split": "PASS",
                    "leakage_test": "PASS",
                    "report_sha256": "b" * 64,
                },
                "blind_test": {
                    "status": "VALIDATED",
                    "locked_predictions": 10,
                    "revealed_outcomes": 10,
                    "identity_hidden": True,
                    "future_hidden": True,
                    "baseline_compared": True,
                    "metrics_sha256": "c" * 64,
                    "report_sha256": "d" * 64,
                },
            }
            payload["readiness_digest"] = hash_json(payload)
            path.write_bytes(canonical_json_bytes(payload))
            gate = strict_forecast_gate(root)
            self.assertEqual(gate["status"], "READY")
            self.assertTrue(gate["publish_allowed"])
            payload["training"]["unique_events"] = 0
            payload["readiness_digest"] = "f" * 64
            path.write_bytes(canonical_json_bytes(payload))
            with self.assertRaisesRegex(ResearchNetworkError, "digest mismatch"):
                strict_forecast_gate(root)


if __name__ == "__main__":
    unittest.main()
