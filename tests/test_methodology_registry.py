from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]


class MethodologyRegistryTests(unittest.TestCase):
    def test_registry_is_structured_and_references_primary_material(self) -> None:
        value = json.loads((ROOT / "research" / "methodology_registry.json").read_text(encoding="utf-8"))
        checked_at = datetime.fromisoformat(value["checked_at"])
        now = datetime.now(timezone.utc)
        self.assertIsNotNone(checked_at.tzinfo)
        self.assertLessEqual(checked_at.astimezone(timezone.utc), now + timedelta(days=1))
        self.assertGreaterEqual(checked_at.astimezone(timezone.utc), now - timedelta(days=365))
        rows = value["methods"]
        self.assertGreaterEqual(len(rows), 8)
        self.assertEqual(len({row["method_id"] for row in rows}), len(rows))
        for row in rows:
            with self.subTest(method=row["method_id"]):
                self.assertTrue(row["production_state"])
                self.assertTrue(row["rules"])
                self.assertTrue(row["required_tests"])
                self.assertTrue(row["references"])
                for reference in row["references"]:
                    self.assertEqual(urlparse(reference["url"]).scheme, "https")
                    self.assertIn(reference["kind"], {"official_documentation", "official_standard", "peer_reviewed_paper", "research_paper"})

    def test_operational_methods_resolve_to_methodology_registry(self) -> None:
        catalog = json.loads(
            (ROOT / "config" / "methods.json").read_text(encoding="utf-8")
        )
        registry = json.loads(
            (ROOT / "research" / "methodology_registry.json").read_text(
                encoding="utf-8"
            )
        )
        registry_ids = {row["method_id"] for row in registry["methods"]}
        self.assertEqual(
            len({row["method_id"] for row in catalog["methods"]}),
            len(catalog["methods"]),
        )
        for method in catalog["methods"]:
            with self.subTest(method=method["method_id"]):
                references = method.get("methodology_refs")
                self.assertIsInstance(references, list)
                self.assertGreaterEqual(len(references), 1)
                self.assertEqual(len(references), len(set(references)))
                self.assertTrue(set(references).issubset(registry_ids))

    def test_official_rules_reference_registered_primary_sources(self) -> None:
        source_network = json.loads(
            (ROOT / "config" / "source_network.json").read_text(encoding="utf-8")
        )
        sources = {row["source_id"]: row for row in source_network["sources"]}
        registry = json.loads(
            (ROOT / "research" / "official_rules_registry.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertGreaterEqual(len(registry["rules"]), 1)
        for rule in registry["rules"]:
            with self.subTest(rule=rule["rule_id"]):
                self.assertIn(rule["source_id"], sources)
                self.assertIn(
                    sources[rule["source_id"]]["source_class"],
                    {"PRIMARY_OFFICIAL", "PRIMARY_ISSUER"},
                )
                self.assertEqual(urlparse(rule["url"]).scheme, "https")


if __name__ == "__main__":
    unittest.main()
