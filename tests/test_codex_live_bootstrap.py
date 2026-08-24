from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - optional test dependency
    Draft202012Validator = None

from kubo.codex_live_bootstrap import (
    CodexBootstrapError,
    EXPECTED_PRODUCTS,
    validate_codex_live_bootstrap,
)


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "codex_live_bootstrap.json"


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


class CodexLiveBootstrapTests(unittest.TestCase):
    def _mutated_path(self, payload: object, directory: str) -> Path:
        path = Path(directory) / "bootstrap.json"
        _write(path, payload)
        return path

    def test_repository_bootstrap_passes_as_handoff_only(self) -> None:
        report = validate_codex_live_bootstrap(ROOT)
        self.assertEqual(report["status"], "PASS_HANDOFF_CONTRACT")
        self.assertEqual(report["mission_status"], "READY_FOR_CODEX_EXECUTION")
        self.assertEqual(report["live_runtime_status"], "NOT_IMPLEMENTED")
        self.assertEqual(
            report["scheduled_runtime_status"], "DISABLED_UNTIL_AUTHORIZED"
        )
        self.assertEqual(report["factor9_status"], "RESEARCH_ASSET_PENDING_ADMISSION")
        self.assertEqual(report["development_event_count"], 250)
        self.assertEqual(report["locked_test_range"], [500, 600])
        self.assertEqual(report["products"], EXPECTED_PRODUCTS)
        self.assertTrue(all(value is False for value in report["claim_boundaries"].values()))

    def test_json_schema_accepts_the_locked_config(self) -> None:
        if Draft202012Validator is None:
            self.skipTest("jsonschema optional dependency unavailable")
        schema = _load(ROOT / "schemas" / "codex-live-bootstrap.schema.json")
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(_load(CONFIG))

    def test_factor9_counts_are_reconciled_and_not_promoted(self) -> None:
        payload = _load(CONFIG)
        factor9 = payload["factor9"]
        self.assertEqual(
            factor9["original_price_rows"] - factor9["clean_price_rows"],
            factor9["excluded_price_rows"],
        )
        self.assertEqual(factor9["promotion_ceiling"], "RESEARCH_INPUT_ONLY")
        self.assertEqual(len(factor9["admission_gates"]), 7)

    def test_config_contains_no_private_drive_locator(self) -> None:
        serialized = CONFIG.read_text(encoding="utf-8").lower()
        for forbidden in (
            "drive.google.com",
            "docs.google.com",
            "/folders/",
            "access_token",
            "refresh_token",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, serialized)

    def test_weakened_claim_boundary_is_rejected(self) -> None:
        payload = _load(CONFIG)
        payload["claim_boundaries"]["automatic_code_merge_allowed"] = True
        with tempfile.TemporaryDirectory() as temporary:
            path = self._mutated_path(payload, temporary)
            with self.assertRaisesRegex(CodexBootstrapError, "claim_boundaries"):
                validate_codex_live_bootstrap(ROOT, config_path=path)

    def test_factor9_count_mutation_is_rejected(self) -> None:
        payload = _load(CONFIG)
        payload["factor9"]["clean_price_rows"] += 1
        with tempfile.TemporaryDirectory() as temporary:
            path = self._mutated_path(payload, temporary)
            with self.assertRaisesRegex(CodexBootstrapError, "factor9"):
                validate_codex_live_bootstrap(ROOT, config_path=path)

    def test_locked_test_overlap_is_rejected(self) -> None:
        payload = _load(CONFIG)
        payload["event_training"]["locked_test_may_overlap_development"] = True
        with tempfile.TemporaryDirectory() as temporary:
            path = self._mutated_path(payload, temporary)
            with self.assertRaisesRegex(CodexBootstrapError, "event_training"):
                validate_codex_live_bootstrap(ROOT, config_path=path)

    def test_stage_reordering_is_rejected(self) -> None:
        payload = _load(CONFIG)
        stages = payload["daily_runtime"]["stages"]
        stages[5], stages[7] = stages[7], stages[5]
        with tempfile.TemporaryDirectory() as temporary:
            path = self._mutated_path(payload, temporary)
            with self.assertRaisesRegex(CodexBootstrapError, "daily_runtime.stages"):
                validate_codex_live_bootstrap(ROOT, config_path=path)

    def test_product_horizon_mismatch_is_rejected(self) -> None:
        payload = _load(CONFIG)
        payload["daily_runtime"]["products"][0]["horizon_sessions"] = 5
        with tempfile.TemporaryDirectory() as temporary:
            path = self._mutated_path(payload, temporary)
            with self.assertRaisesRegex(CodexBootstrapError, "daily_runtime.products"):
                validate_codex_live_bootstrap(ROOT, config_path=path)

    def test_private_drive_url_is_rejected(self) -> None:
        payload = _load(CONFIG)
        payload["drive"]["canonical_data_root"] = (
            "https://drive.google.com/drive/folders/private"
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = self._mutated_path(payload, temporary)
            with self.assertRaises(CodexBootstrapError):
                validate_codex_live_bootstrap(ROOT, config_path=path)

    def test_unknown_field_is_rejected(self) -> None:
        payload = _load(CONFIG)
        payload["drive"]["folder_id"] = "private"
        with tempfile.TemporaryDirectory() as temporary:
            path = self._mutated_path(payload, temporary)
            with self.assertRaisesRegex(CodexBootstrapError, "drive"):
                validate_codex_live_bootstrap(ROOT, config_path=path)

    def test_duplicate_json_key_is_rejected(self) -> None:
        text = CONFIG.read_text(encoding="utf-8").replace(
            '"schema_version": "1.0",',
            '"schema_version": "1.0",\n  "schema_version": "1.0",',
            1,
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "duplicate.json"
            path.write_text(text, encoding="utf-8")
            with self.assertRaisesRegex(CodexBootstrapError, "duplicate JSON key"):
                validate_codex_live_bootstrap(ROOT, config_path=path)


class CodexLiveBootstrapCatalogBindingTests(unittest.TestCase):
    def test_daily_products_are_exactly_bound_to_catalog(self) -> None:
        catalog = _load(ROOT / "config" / "products.json")
        mapping = {
            row["product_id"]: row["horizon_sessions"] for row in catalog["products"]
        }
        self.assertEqual(
            [(row["product_id"], mapping[row["product_id"]]) for row in EXPECTED_PRODUCTS],
            [(row["product_id"], row["horizon_sessions"]) for row in EXPECTED_PRODUCTS],
        )


if __name__ == "__main__":
    unittest.main()
