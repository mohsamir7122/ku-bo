from __future__ import annotations

import unittest

from kubo.analysts import analyze_fundamentals, analyze_price_window, analyze_sentiment


class AnalystTests(unittest.TestCase):
    def test_price_window_is_descriptive_and_detects_negative_activity(self) -> None:
        rows = [
            {"close_fils": 100, "volume": 1000},
            {"close_fils": 102, "volume": 1100},
            {"close_fils": 103, "volume": 900},
            {"close_fils": 104, "volume": 1000},
            {"close_fils": 98, "volume": 4000},
        ]
        signals = analyze_price_window(rows)
        activity = next(item for item in signals if item.signal_kind == "PRICE_ACTIVITY")
        self.assertEqual(activity.direction, "NEGATIVE")
        self.assertEqual(activity.claim_boundary, "DESCRIPTIVE_RESEARCH_SIGNAL_NOT_PROBABILITY")
        self.assertFalse(hasattr(activity, "probability"))

    def test_price_window_keeps_missing_and_zero_liquidity_visible(self) -> None:
        rows = [
            {"close_fils": 100, "volume": 1000},
            {"close_fils": 100, "volume": 0},
            {"close_fils": 100, "volume": None},
            {"close_fils": 100, "volume": 0},
            {"close_fils": 100, "volume": 1000},
        ]
        liquidity = next(item for item in analyze_price_window(rows) if item.signal_kind == "LIQUIDITY")
        self.assertEqual(liquidity.direction, "NEGATIVE")
        self.assertIn("missing_volume_sessions=1", liquidity.rationale)
        self.assertIn("zero_volume_sessions=2", liquidity.rationale)

    def test_fundamental_quality_uses_cash_and_leverage_not_profit_alone(self) -> None:
        current = {"revenue": 120, "net_income": 20, "operating_cash_flow": 25, "total_debt": 30, "equity": 100}
        prior = {"revenue": 100, "net_income": 10, "operating_cash_flow": 8, "total_debt": 40, "equity": 90}
        signal = analyze_fundamentals(current, prior)
        self.assertEqual(signal.direction, "POSITIVE")
        self.assertIn("quality_vote_share=1.00000000", signal.rationale)

    def test_sentiment_deduplicates_origin_and_requires_multiple_authors(self) -> None:
        duplicate_only = [
            {"origin_id": "same", "author_id": "a", "tone": 1, "author_reliability": 0.8},
            {"origin_id": "same", "author_id": "b", "tone": 1, "author_reliability": 0.7},
        ]
        self.assertEqual(analyze_sentiment(duplicate_only).direction, "NEUTRAL")
        independent = duplicate_only + [{"origin_id": "other", "author_id": "b", "tone": 0.8, "author_reliability": 0.7}]
        signal = analyze_sentiment(independent)
        self.assertEqual(signal.direction, "POSITIVE")
        self.assertIn("tone_is_not_claim_truth", signal.rationale)


if __name__ == "__main__":
    unittest.main()
