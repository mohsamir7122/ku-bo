from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from kubo.benchmark_registry import (
    PILOT_SECTORS,
    REGISTRY_CLAIM_BOUNDARY,
    REGISTRY_DATE_BASIS,
    load_benchmark_registry,
)


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "config" / "pilot" / "benchmark_registry.json"


class BenchmarkRegistryTests(unittest.TestCase):
    def _mutated_registry(self, mutation: object) -> Path:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        path = Path(temp.name) / "benchmark_registry.json"
        payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        mutation(payload)
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_registry_uses_internal_requirement_codes_and_exact_pilot_roles(self) -> None:
        registry = load_benchmark_registry(ROOT / "config")
        self.assertEqual(len(registry.benchmarks), 10)
        self.assertEqual(registry.required_codes, frozenset(registry.by_code))
        self.assertEqual(
            {item.sector for item in registry.benchmarks if item.sector},
            set(PILOT_SECTORS),
        )
        self.assertEqual(
            {item.calculation_basis for item in registry.benchmarks},
            {"PRICE_INDEX", "TOTAL_RETURN_INDEX"},
        )
        self.assertEqual(
            {item.source_id for item in registry.benchmarks},
            {"authorized_market_feed_unconfigured"},
        )
        self.assertTrue(
            all(item.benchmark_code.startswith("KU_BO_") for item in registry.benchmarks)
        )
        self.assertTrue(
            all(item.registry_state == "UNVERIFIED_SEED" for item in registry.benchmarks)
        )

    def test_registry_date_basis_forbids_launch_or_inception_claim(self) -> None:
        registry = load_benchmark_registry(ROOT / "config")
        self.assertEqual(registry.registry_date_basis, REGISTRY_DATE_BASIS)
        self.assertEqual(registry.claim_boundary, REGISTRY_CLAIM_BOUNDARY)
        self.assertTrue(
            all(
                item.effective_from == registry.registry_observed_on
                for item in registry.benchmarks
            )
        )

    def test_broad_market_definition_cannot_be_labeled_as_sector(self) -> None:
        path = self._mutated_registry(
            lambda payload: payload["benchmarks"][0].update({"sector": "Banks"})
        )
        with self.assertRaisesRegex(ValueError, "must not declare sector"):
            load_benchmark_registry(path)

    def test_sector_definition_requires_a_sector(self) -> None:
        path = self._mutated_registry(
            lambda payload: payload["benchmarks"][1].update({"sector": ""})
        )
        with self.assertRaisesRegex(ValueError, "sector benchmarks require sector"):
            load_benchmark_registry(path)

    def test_price_and_total_return_roles_cannot_collapse(self) -> None:
        def mutate(payload: dict[str, object]) -> None:
            rows = payload["benchmarks"]
            rows[5]["calculation_basis"] = "PRICE_INDEX"

        path = self._mutated_registry(mutate)
        with self.assertRaisesRegex(ValueError, "ambiguous duplicate comparison roles"):
            load_benchmark_registry(path)

    def test_registry_rejects_invented_provider_metadata_field(self) -> None:
        def mutate(payload: dict[str, object]) -> None:
            payload["benchmarks"][0]["provider_launch_date"] = "2000-01-01"

        path = self._mutated_registry(mutate)
        with self.assertRaisesRegex(ValueError, "unknown or missing fields"):
            load_benchmark_registry(path)

    def test_registry_rejects_access_and_rights_conflict(self) -> None:
        path = self._mutated_registry(
            lambda payload: payload["benchmarks"][0].update(
                {"rights_requirement": "PUBLIC_RESEARCH_ALLOWED"}
            )
        )
        with self.assertRaisesRegex(ValueError, "source_access and rights_requirement conflict"):
            load_benchmark_registry(path)

    def test_registry_observation_basis_requires_matching_effective_date(self) -> None:
        path = self._mutated_registry(
            lambda payload: payload["benchmarks"][0].update(
                {"effective_from": "2020-01-01"}
            )
        )
        with self.assertRaisesRegex(ValueError, "must equal registry_observed_on"):
            load_benchmark_registry(path)


if __name__ == "__main__":
    unittest.main()
