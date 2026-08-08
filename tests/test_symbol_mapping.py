from __future__ import annotations

import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from kubo.live_pilot import (
    MAX_LIVE_PILOT_CAPTURE_TASKS,
    build_investing_seed_capture_plan,
)
from kubo.symbol_mapping import SymbolMappingCatalog


ROOT = Path(__file__).resolve().parents[1]


class SymbolMappingTests(unittest.TestCase):
    def _payload(self) -> dict:
        return json.loads(
            (ROOT / "config" / "symbol_mapping.json").read_text(encoding="utf-8")
        )

    def _catalog(self, payload: dict) -> SymbolMappingCatalog:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        config = Path(temporary.name)
        (config / "symbol_mapping.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )
        return SymbolMappingCatalog(config)

    def test_live_pilot_symbol_mapping_seed_is_valid(self) -> None:
        catalog = SymbolMappingCatalog(ROOT / "config")
        report = catalog.report()
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["schema_version"], "1.0")
        self.assertEqual(report["as_of"], "2026-08-08")
        self.assertEqual(report["scope"], "LIVE_PILOT_SEED")
        self.assertEqual(report["security_count"], 5)
        self.assertEqual(report["with_investing_url"], 5)
        self.assertEqual(report["mapping_states"]["CANDIDATE_URL_OBSERVED"], 5)
        self.assertEqual(
            report["symbols"], ["HUMANSOFT", "KFH", "MABANEE", "NBK", "ZAIN"]
        )

    def test_schema_as_of_and_coverage_count_are_enforced(self) -> None:
        cases = (
            ("schema_version", "2.0", "schema_version"),
            ("as_of", "08/08/2026", "ISO date"),
        )
        for field, value, error in cases:
            with self.subTest(field=field):
                payload = self._payload()
                payload[field] = value
                with self.assertRaisesRegex(ValueError, error):
                    self._catalog(payload)

        payload = self._payload()
        payload["coverage"]["security_count"] = 999
        with self.assertRaisesRegex(ValueError, "number of mapping rows"):
            self._catalog(payload)

    def test_security_code_is_numeric_and_identifiers_are_unique(self) -> None:
        payload = self._payload()
        payload["mappings"][0]["security_code"] = "10/8"
        with self.assertRaisesRegex(ValueError, "ASCII digits"):
            self._catalog(payload)

        duplicate_code = self._payload()
        duplicate_code["mappings"][1]["security_code"] = (
            "0" + duplicate_code["mappings"][0]["security_code"]
        )
        with self.assertRaisesRegex(ValueError, "duplicate security_code"):
            self._catalog(duplicate_code)

        duplicate_isin = self._payload()
        duplicate_isin["mappings"][1]["isin"] = duplicate_isin["mappings"][0]["isin"]
        with self.assertRaisesRegex(ValueError, "duplicate isin"):
            self._catalog(duplicate_isin)

    def test_isin_ticker_domain_and_slug_are_strict(self) -> None:
        mutations = (
            ("isin", "KW0EQ0100084", "valid uppercase ISIN"),
            ("boursa_symbol", "../KFH", "path-safe ASCII ticker"),
            ("investing_slug", "../kfh", "path-safe slug"),
            (
                "investing_url",
                "https://example.com/equities/kwt-fin-house-historical-data",
                "approved Investing.com domain",
            ),
        )
        for field, value, error in mutations:
            with self.subTest(field=field):
                payload = self._payload()
                payload["mappings"][0][field] = value
                with self.assertRaisesRegex(ValueError, error):
                    self._catalog(payload)

    def test_capture_candidates_include_raw_validated_mapping(self) -> None:
        payload = self._payload()
        payload["mappings"][0]["mapping_state"] = "VALIDATED_BY_RAW_CAPTURE"
        catalog = self._catalog(payload)
        candidates = catalog.capture_candidates()
        self.assertEqual(
            [mapping.boursa_symbol for mapping in candidates],
            ["KFH", "NBK", "ZAIN", "HUMANSOFT", "MABANEE"],
        )
        self.assertEqual(candidates[0].mapping_state, "VALIDATED_BY_RAW_CAPTURE")

    def test_live_pilot_seed_contains_expected_identity_values(self) -> None:
        catalog = SymbolMappingCatalog(ROOT / "config")
        expected = {
            "NBK": ("101", "KW0EQ0100010"),
            "KFH": ("108", "KW0EQ0100085"),
            "MABANEE": ("413", "KW0EQ0400725"),
            "ZAIN": ("605", "KW0EQ0601058"),
            "HUMANSOFT": ("623", "KW0EQ0601694"),
        }
        actual = {
            symbol: (mapping.security_code, mapping.isin)
            for symbol, mapping in catalog.mappings.items()
        }
        self.assertEqual(actual, expected)
        self.assertEqual(catalog.mappings["KFH"].security_code, "108")

    def test_live_pilot_capture_plan_contains_only_executable_fields(self) -> None:
        catalog = SymbolMappingCatalog(ROOT / "config")
        plan = build_investing_seed_capture_plan(catalog)
        self.assertEqual(set(plan), {"schema_version", "tasks"})
        self.assertEqual(plan["schema_version"], "1.0")
        self.assertEqual(len(plan["tasks"]), 5)
        self.assertEqual(
            [task["source_id"] for task in plan["tasks"]],
            ["investing_history"] * 5,
        )
        self.assertTrue(all("symbol_binding" not in task for task in plan["tasks"]))
        self.assertTrue(
            all(
                task["source_url"].startswith(
                    "https://www.investing.com/equities/"
                )
                for task in plan["tasks"]
            )
        )

    def test_static_live_pilot_example_matches_current_generator(self) -> None:
        catalog = SymbolMappingCatalog(ROOT / "config")
        generated = build_investing_seed_capture_plan(catalog)
        static = json.loads(
            (ROOT / "examples" / "live_pilot_investing_capture_plan.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(static, generated)
        self.assertEqual(catalog.mappings["KFH"].security_code, "108")

    def test_live_pilot_generator_rejects_more_than_32_tasks(self) -> None:
        candidates = [SimpleNamespace() for _ in range(MAX_LIVE_PILOT_CAPTURE_TASKS + 1)]
        catalog = SimpleNamespace(capture_candidates=lambda: candidates)
        with self.assertRaisesRegex(ValueError, "explicit limit of 32 tasks"):
            build_investing_seed_capture_plan(catalog)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
