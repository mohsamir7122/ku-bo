from __future__ import annotations

from pathlib import Path
import unittest

from kubo.capabilities import CAPABILITY_ALLOWED_ROLES
from kubo.catalog import CAPABILITY_VOCABULARY, DAILY_BENCHMARK_RULES, Catalog


ROOT = Path(__file__).resolve().parents[1]


class BenchmarkCapabilityCatalogTests(unittest.TestCase):
    def test_benchmark_history_has_only_official_or_authorized_roles(self) -> None:
        self.assertIn("benchmark_history", CAPABILITY_VOCABULARY)
        self.assertEqual(
            CAPABILITY_ALLOWED_ROLES["benchmark_history"],
            frozenset({"OFFICIAL_TRUTH", "AUTHORIZED_TAPE"}),
        )

    def test_only_declared_official_or_licensed_sources_offer_benchmark_history(self) -> None:
        catalog = Catalog(ROOT / "config")
        self.assertIn(
            "benchmark_history",
            catalog.sources["boursa_kuwait"].capabilities,
        )
        self.assertIn(
            "benchmark_history",
            catalog.sources["authorized_market_feed_unconfigured"].capabilities,
        )
        self.assertNotIn(
            "benchmark_history",
            catalog.sources["investing_com"].capabilities,
        )

    def test_every_daily_benchmark_product_requires_strict_benchmark_history(self) -> None:
        catalog = Catalog(ROOT / "config")
        daily = {
            product.product_id
            for product in catalog.products.values()
            if product.benchmark_rule in DAILY_BENCHMARK_RULES
        }
        self.assertTrue(daily)
        self.assertTrue(
            all(
                "benchmark_history"
                in catalog.products[product_id].required_capabilities
                for product_id in daily
            )
        )
        self.assertNotIn(
            "benchmark_history",
            catalog.products["next_session_plus_10_event"].required_capabilities,
        )


if __name__ == "__main__":
    unittest.main()
