from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from kubo.market_scope import MarketScopeError, validate_market_scope


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class MarketScopeTests(unittest.TestCase):
    def test_repository_scope_is_locked_to_kuwait(self) -> None:
        report = validate_market_scope(PROJECT_ROOT)

        self.assertEqual(report["status"], "PASS_KUWAIT_ONLY_MARKET_SCOPE")
        self.assertEqual(report["jurisdiction_code"], "KW")
        self.assertEqual(report["currency"], "KWD")
        self.assertFalse(report["foreign_market_adapters_allowed"])
        self.assertGreater(report["product_count"], 0)

    def test_scope_rejects_another_market(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config").mkdir()
            scope = json.loads((PROJECT_ROOT / "config" / "market_scope.json").read_text())
            products = json.loads((PROJECT_ROOT / "config" / "products.json").read_text())
            scope["jurisdiction_code"] = "ZZ"
            (root / "config" / "market_scope.json").write_text(json.dumps(scope), encoding="utf-8")
            (root / "config" / "products.json").write_text(json.dumps(products), encoding="utf-8")

            with self.assertRaisesRegex(MarketScopeError, "market identity"):
                validate_market_scope(root)

    def test_scope_rejects_runtime_market_switching(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config").mkdir()
            scope = json.loads((PROJECT_ROOT / "config" / "market_scope.json").read_text())
            products = json.loads((PROJECT_ROOT / "config" / "products.json").read_text())
            scope["policy"]["runtime_market_override_allowed"] = True
            (root / "config" / "market_scope.json").write_text(json.dumps(scope), encoding="utf-8")
            (root / "config" / "products.json").write_text(json.dumps(products), encoding="utf-8")

            with self.assertRaisesRegex(MarketScopeError, "market policy"):
                validate_market_scope(root)

    def test_scope_rejects_product_timezone_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config").mkdir()
            scope = json.loads((PROJECT_ROOT / "config" / "market_scope.json").read_text())
            products = json.loads((PROJECT_ROOT / "config" / "products.json").read_text())
            products["timezone"] = "Etc/UTC"
            (root / "config" / "market_scope.json").write_text(json.dumps(scope), encoding="utf-8")
            (root / "config" / "products.json").write_text(json.dumps(products), encoding="utf-8")

            with self.assertRaisesRegex(MarketScopeError, "timezone"):
                validate_market_scope(root)


if __name__ == "__main__":
    unittest.main()
