from __future__ import annotations

import unittest

from kubo.liquidity import calculate_liquidity_metrics, simulate_liquidity_constrained_fill


class LiquidityTests(unittest.TestCase):
    def test_zero_volume_is_not_missing_volume(self) -> None:
        metrics = calculate_liquidity_metrics(
            [
                {"close_fils": 100, "volume": 1000, "turnover_kwd": 100},
                {"close_fils": 100, "volume": 0, "turnover_kwd": 0},
                {"close_fils": 102, "volume": None, "turnover_kwd": None},
            ]
        )
        self.assertEqual(metrics.zero_volume_sessions, 1)
        self.assertEqual(metrics.missing_volume_sessions, 1)
        self.assertEqual(metrics.traded_sessions, 1)
        self.assertAlmostEqual(metrics.nontrading_ratio, 2 / 3)

    def test_no_trade_session_is_no_fill(self) -> None:
        fill = simulate_liquidity_constrained_fill(
            side="BUY",
            quantity=1000,
            session_volume=0,
            bid_fils=99,
            ask_fils=100,
            trading_status="TRADED",
        )
        self.assertEqual(fill.status, "NO_FILL")
        self.assertIn("ZERO_SESSION_VOLUME", fill.reason_codes)

    def test_suspension_blocks_fill(self) -> None:
        fill = simulate_liquidity_constrained_fill(
            side="BUY",
            quantity=1000,
            session_volume=100000,
            bid_fils=99,
            ask_fils=100,
            trading_status="SUSPENDED",
        )
        self.assertEqual(fill.status, "NO_FILL")
        self.assertIn("TRADING_NOT_AVAILABLE", fill.reason_codes)

    def test_limit_queue_blocks_optimistic_execution(self) -> None:
        fill = simulate_liquidity_constrained_fill(
            side="BUY",
            quantity=1000,
            session_volume=100000,
            bid_fils=109,
            ask_fils=110,
            trading_status="TRADED",
            upper_limit_queue=True,
        )
        self.assertEqual(fill.status, "NO_FILL")
        self.assertIn("UPPER_LIMIT_QUEUE_NO_FILL_ASSUMPTION", fill.reason_codes)

    def test_large_order_is_partial_and_costed(self) -> None:
        fill = simulate_liquidity_constrained_fill(
            side="BUY",
            quantity=20000,
            session_volume=100000,
            bid_fils=99,
            ask_fils=100,
            trading_status="TRADED",
            max_participation=0.05,
        )
        self.assertEqual(fill.status, "PARTIAL_FILL")
        self.assertEqual(fill.filled_quantity, 5000)
        self.assertEqual(fill.unfilled_quantity, 15000)
        self.assertGreater(fill.fill_price_fils or 0, 100)
        self.assertGreater(fill.estimated_cost_kwd, 0)


if __name__ == "__main__":
    unittest.main()
