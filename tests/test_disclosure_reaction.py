from __future__ import annotations

import unittest

from kubo.disclosure_reaction import analyze_disclosure_reaction
from disclosure_reaction_fixture import opinion, packet


class DisclosureReactionTests(unittest.TestCase):
    def test_ready_output_is_qualitative_only(self):
        result = analyze_disclosure_reaction(packet())
        self.assertEqual(result["status"], "QUALITATIVE_REACTION_READY")
        self.assertFalse(result["numbers_exposed"])
        self.assertFalse(result["causality_claim_allowed"])
        serialized = str(result)
        for forbidden in ("stock_total_return_index", "market_total_return_index", "movement_threshold_pct"):
            self.assertNotIn(forbidden, serialized)

    def test_rise_started_before_and_continued_after(self):
        result = analyze_disclosure_reaction(packet(pre_start=100, pre_end=103, immediate_end=104, post_end=107))
        self.assertEqual(result["price_behavior"]["timing_conclusion"], "RISE_STARTD_BEFORE_AND_CONTINUED_AFTER")

    def test_rise_started_before_only(self):
        result = analyze_disclosure_reaction(packet(pre_start=100, pre_end=103, immediate_end=103, post_end=101))
        self.assertEqual(result["price_behavior"]["timing_conclusion"], "RISE_STARTED_BEFORE_DISCLOSURE")

    def test_rise_started_immediately_after(self):
        result = analyze_disclosure_reaction(packet(pre_start=100, pre_end=100, immediate_end=103, post_end=106))
        self.assertEqual(result["price_behavior"]["timing_conclusion"], "RISE_STARTD_IMMEDIATELY_AFTER_DISCLOSURE")

    def test_short_rise_then_faded(self):
        result = analyze_disclosure_reaction(packet(pre_start=100, pre_end=100, immediate_end=103, post_end=100))
        self.assertEqual(result["price_behavior"]["timing_conclusion"], "SHORT_RISE_AFTER_DISCLOSURE_THEN_FADED")

    def test_delayed_rise_after(self):
        result = analyze_disclosure_reaction(packet(pre_start=100, pre_end=100, immediate_end=100, post_end=104))
        self.assertEqual(result["price_behavior"]["timing_conclusion"], "RISE_APPEARED_LATER_AFTER_DISCLOSURE")

    def test_no_clear_rise(self):
        result = analyze_disclosure_reaction(packet())
        self.assertEqual(result["price_behavior"]["timing_conclusion"], "NO_CLEAR_RISE_AROUND_DISCLOSURE")

    def test_public_opinion_after_disclosure(self):
        base = packet()
        when = base["historical_market_window"]["post_sessions"][0]["observed_at"]
        base["public_opinion_archive"]["items"] = [opinion(when=when, stance="POSITIVE")]
        result = analyze_disclosure_reaction(base)
        self.assertEqual(result["public_opinion"]["after_disclosure"], "POSITIVE")
        self.assertEqual(result["public_opinion"]["discussion_timing"], "PUBLIC_DISCUSSION_STARTED_AFTER_DISCLOSURE")

    def test_pre_disclosure_discussion_does_not_prove_leakage(self):
        base = packet()
        when = base["historical_market_window"]["pre_sessions"][-1]["observed_at"]
        base["public_opinion_archive"]["items"] = [opinion(when=when, stance="POSITIVE")]
        result = analyze_disclosure_reaction(base)
        self.assertEqual(result["public_opinion"]["discussion_timing"], "PUBLIC_DISCUSSION_EXISTED_BEFORE_DISCLOSURE")
        self.assertIn("PRE_DISCLOSURE_PUBLIC_DISCUSSION_DOES_NOT_PROVE_LEAKAGE", result["warnings"])
        self.assertFalse(result["causality_claim_allowed"])

    def test_mixed_independent_public_opinion(self):
        base = packet()
        when = base["historical_market_window"]["post_sessions"][0]["observed_at"]
        base["public_opinion_archive"]["items"] = [
            opinion(when=when, stance="POSITIVE", group="a"),
            opinion(when=when, stance="NEGATIVE", group="b"),
        ]
        result = analyze_disclosure_reaction(base)
        self.assertEqual(result["public_opinion"]["after_disclosure"], "MIXED")

    def test_invalid_window_stops_without_guessing(self):
        base = packet()
        base["historical_market_window"]["post_sessions"].pop()
        result = analyze_disclosure_reaction(base)
        self.assertEqual(result["status"], "STOP_INSUFFICIENT_EVIDENCE")
        self.assertIsNone(result["price_behavior"])
        self.assertFalse(result["numbers_exposed"])


if __name__ == "__main__":
    unittest.main()
