from __future__ import annotations

import json
from pathlib import Path
import unittest

try:
    from jsonschema import Draft202012Validator
except ModuleNotFoundError:
    Draft202012Validator = None

from kubo.disclosure_reaction import (
    DisclosureReactionError,
    analyze_disclosure_reaction,
    validate_disclosure_reaction_packet,
)
from disclosure_reaction_fixture import opinion, packet


class DisclosureReactionTests(unittest.TestCase):

    def test_json_schemas_accept_ready_packet_and_result(self) -> None:
        if Draft202012Validator is None:
            self.skipTest("jsonschema is not installed")
        root = Path(__file__).resolve().parents[1]
        packet_schema = json.loads(
            (root / "schemas" / "disclosure-reaction-packet.schema.json").read_text(
                encoding="utf-8"
            )
        )
        result_schema = json.loads(
            (root / "schemas" / "disclosure-reaction-result.schema.json").read_text(
                encoding="utf-8"
            )
        )
        Draft202012Validator.check_schema(packet_schema)
        Draft202012Validator.check_schema(result_schema)
        Draft202012Validator(
            packet_schema, format_checker=Draft202012Validator.FORMAT_CHECKER
        ).validate(packet())
        Draft202012Validator(
            result_schema, format_checker=Draft202012Validator.FORMAT_CHECKER
        ).validate(analyze_disclosure_reaction(packet()))

    def test_ready_output_is_qualitative_only(self) -> None:
        result = analyze_disclosure_reaction(packet())
        self.assertEqual(result["status"], "QUALITATIVE_REACTION_READY")
        self.assertFalse(result["numbers_exposed"])
        self.assertFalse(result["causality_claim_allowed"])
        self.assertNotIn("return", result["price_behavior"])
        self.assertIsInstance(result["narrative_ar"], str)

    def test_rise_started_before_and_continued_after(self) -> None:
        result = analyze_disclosure_reaction(
            packet(pre_start=100, pre_end=103, immediate_end=104, post_end=107)
        )
        self.assertEqual(
            result["price_behavior"]["timing_conclusion"],
            "RISE_STARTED_BEFORE_AND_CONTINUED_AFTER",
        )
        self.assertEqual(
            result["price_behavior"]["disclosure_association"],
            "MOVE_PRECEDED_DISCLOSURE",
        )

    def test_rise_started_before_only(self) -> None:
        result = analyze_disclosure_reaction(
            packet(pre_start=100, pre_end=103, immediate_end=103, post_end=101)
        )
        self.assertEqual(
            result["price_behavior"]["timing_conclusion"],
            "RISE_STARTED_BEFORE_DISCLOSURE",
        )

    def test_rise_started_immediately_after(self) -> None:
        result = analyze_disclosure_reaction(
            packet(pre_start=100, pre_end=100, immediate_end=103, post_end=106)
        )
        self.assertEqual(
            result["price_behavior"]["timing_conclusion"],
            "RISE_STARTED_IMMEDIATELY_AFTER_DISCLOSURE",
        )

    def test_short_rise_after_then_faded(self) -> None:
        result = analyze_disclosure_reaction(
            packet(pre_start=100, pre_end=100, immediate_end=103, post_end=100)
        )
        self.assertEqual(
            result["price_behavior"]["timing_conclusion"],
            "SHORT_RISE_AFTER_DISCLOSURE_THEN_FADED",
        )

    def test_delayed_rise_after(self) -> None:
        result = analyze_disclosure_reaction(
            packet(pre_start=100, pre_end=100, immediate_end=100, post_end=104)
        )
        self.assertEqual(
            result["price_behavior"]["timing_conclusion"],
            "RISE_APPEARED_LATER_AFTER_DISCLOSURE",
        )

    def test_no_clear_rise(self) -> None:
        result = analyze_disclosure_reaction(packet())
        self.assertEqual(
            result["price_behavior"]["timing_conclusion"],
            "NO_CLEAR_RISE_AROUND_DISCLOSURE",
        )

    def test_public_opinion_after_disclosure_is_classified(self) -> None:
        base = packet()
        when = base["post_sessions"][0]["observed_at"]
        base["public_opinion"] = [opinion(when=when, stance="POSITIVE")]
        result = analyze_disclosure_reaction(base)
        self.assertEqual(
            result["public_opinion"]["before_disclosure"],
            "INSUFFICIENT_EVIDENCE",
        )
        self.assertEqual(result["public_opinion"]["after_disclosure"], "POSITIVE")
        self.assertEqual(
            result["public_opinion"]["discussion_timing"],
            "PUBLIC_DISCUSSION_STARTED_AFTER_DISCLOSURE",
        )

    def test_verified_pre_disclosure_discussion_is_flagged_without_leakage_claim(self) -> None:
        base = packet()
        when = base["pre_sessions"][-1]["observed_at"]
        base["public_opinion"] = [opinion(when=when, stance="POSITIVE")]
        result = analyze_disclosure_reaction(base)
        self.assertEqual(
            result["public_opinion"]["discussion_timing"],
            "PUBLIC_DISCUSSION_EXISTED_BEFORE_DISCLOSURE",
        )
        self.assertIn(
            "PRE_DISCLOSURE_PUBLIC_DISCUSSION_REQUIRES_REVIEW_BUT_DOES_NOT_PROVE_LEAKAGE",
            result["warnings"],
        )
        self.assertFalse(result["causality_claim_allowed"])

    def test_mixed_independent_public_opinion(self) -> None:
        base = packet()
        when = base["post_sessions"][0]["observed_at"]
        base["public_opinion"] = [
            opinion(when=when, stance="POSITIVE", group="source-a"),
            opinion(when=when, stance="NEGATIVE", group="source-b"),
        ]
        result = analyze_disclosure_reaction(base)
        self.assertEqual(result["public_opinion"]["after_disclosure"], "MIXED")

    def test_duplicate_disclosure_document_is_rejected(self) -> None:
        base = packet()
        base["disclosure"]["duplicate_of"] = "canonical-event"
        with self.assertRaisesRegex(DisclosureReactionError, "canonical disclosure"):
            validate_disclosure_reaction_packet(base)

    def test_unadjusted_price_basis_is_rejected(self) -> None:
        base = packet()
        base["policy"]["price_basis"] = "RAW_CLOSE"
        with self.assertRaisesRegex(DisclosureReactionError, "TOTAL_RETURN_INDEX"):
            validate_disclosure_reaction_packet(base)

    def test_missing_benchmark_evidence_is_rejected(self) -> None:
        base = packet()
        base["post_sessions"][0]["market_benchmark_evidence_sha256"] = None
        with self.assertRaisesRegex(DisclosureReactionError, "lowercase SHA-256"):
            validate_disclosure_reaction_packet(base)

    def test_signed_or_credential_url_is_rejected(self) -> None:
        base = packet()
        base["disclosure"]["official_source_url"] = (
            "https://example.com/disclosure?access_token=secret"
        )
        with self.assertRaisesRegex(DisclosureReactionError, "credential"):
            validate_disclosure_reaction_packet(base)

    def test_packet_created_before_post_observations_is_rejected(self) -> None:
        base = packet()
        base["created_at"] = base["disclosure"]["available_at"]
        with self.assertRaisesRegex(DisclosureReactionError, "precedes an included"):
            validate_disclosure_reaction_packet(base)

    def test_wrong_window_count_stops(self) -> None:
        base = packet()
        base["post_sessions"].pop()
        result = analyze_disclosure_reaction(base)
        self.assertEqual(result["status"], "STOP_INSUFFICIENT_EVIDENCE")
        self.assertIsNone(result["price_behavior"])
        self.assertFalse(result["numbers_exposed"])

    def test_result_never_exposes_numeric_market_values(self) -> None:
        result = analyze_disclosure_reaction(
            packet(pre_start=100, pre_end=103, immediate_end=105, post_end=108)
        )
        serialized = str(result)
        self.assertNotIn("movement_threshold_pct", serialized)
        self.assertNotIn("stock_total_return_index", serialized)
        self.assertNotIn("market_total_return_index", serialized)
        self.assertNotIn("sector_total_return_index", serialized)


if __name__ == "__main__":
    unittest.main()
