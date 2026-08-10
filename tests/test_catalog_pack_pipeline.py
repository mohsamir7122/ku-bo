from __future__ import annotations

import csv
from datetime import date
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from kubo.benchmark_history import BENCHMARK_HISTORY_HEADERS
from kubo.benchmark_registry import load_benchmark_registry
from kubo.catalog import Catalog
from kubo.hashing import sha256_file
from kubo.pack import (
    CollectionContract,
    PackValidator,
    _validate_benchmark_history_capability,
)
from kubo.pipeline import ResearchPipeline

from tests.helpers import synthetic_pack
from tests.test_rank_execution_decision_model import (
    write_prospectively_validated_card,
)


ROOT = Path(__file__).resolve().parents[1]


class CatalogPackPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = Catalog(ROOT / "config")
        self.pipeline = ResearchPipeline(ROOT)

    def test_catalog_cross_references(self):
        report = self.catalog.report()
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["sources"], 18)
        self.assertGreaterEqual(report["products"], 13)

    def test_no_pack_never_becomes_ready(self):
        plan = self.pipeline.plan("next_session_rank", mode="validated_forecast")
        self.assertEqual(plan["status"], "EVIDENCE_REQUIRED")
        self.assertEqual(plan["passed_capabilities"], [])

    def test_primary_mode_requires_per_run_source_packet_not_historical_pack(self):
        plan = self.pipeline.plan("next_session_rank")
        self.assertEqual(plan["status"], "SOURCE_NETWORK_REQUIRED")
        self.assertFalse(plan["claim_boundaries"]["historical_archive_required_to_start_research"])
        self.assertFalse(plan["claim_boundaries"]["validated_model_required_to_start_research"])

    def test_manual_capability_injection_interface_removed(self):
        with self.assertRaises(TypeError):
            self.pipeline.plan("next_session_rank", available_capabilities={"daily_eod"})  # type: ignore[call-arg]

    def test_synthetic_pack_passes_contract_but_never_promotes_readiness(self):
        with tempfile.TemporaryDirectory() as directory:
            pack = synthetic_pack(Path(directory) / "pack")
            validation = PackValidator(pack, self.catalog).validate()
            self.assertEqual(validation.status, "PASS", validation.to_dict())
            plan = self.pipeline.plan(
                "next_session_plus_10_event",
                pack_root=pack,
                mode="validated_forecast",
            )
            self.assertEqual(plan["status"], "SYNTHETIC_CONTRACT_ONLY")
            self.assertIn(
                "SYNTHETIC_PACK_CANNOT_PROMOTE_READINESS",
                plan["reasons"],
            )
            self.assertTrue(plan["pack"]["collection"]["synthetic"])

    def test_daily_benchmark_product_is_blocked_without_benchmark_history(self):
        with tempfile.TemporaryDirectory() as directory:
            pack = synthetic_pack(Path(directory) / "pack")
            plan = self.pipeline.plan(
                "next_session_rank",
                pack_root=pack,
                mode="validated_forecast",
            )
            self.assertEqual(plan["status"], "CAPABILITY_BLOCKED")
            self.assertIn("benchmark_history", plan["missing_capabilities"])

    def test_opening_is_blocked_by_missing_authorized_feed(self):
        with tempfile.TemporaryDirectory() as directory:
            pack = synthetic_pack(Path(directory) / "pack")
            plan = self.pipeline.plan("opening_gap_or_limit", pack_root=pack, mode="validated_forecast")
            self.assertEqual(plan["status"], "EXECUTION_BLOCKED")
            self.assertIn("opening_auction", plan["missing_capabilities"])

    def test_available_source_status_is_not_a_capability(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "source_access.json"
            report.write_text(json.dumps({"observed_at": "2026-08-06T12:00:00+03:00", "sources": [{"source_id": "boursa_kuwait", "state": "AVAILABLE"}]}), encoding="utf-8")
            plan = self.pipeline.plan("next_session_rank", source_access_path=report, mode="validated_forecast")
            self.assertEqual(plan["status"], "EVIDENCE_REQUIRED")
            self.assertEqual(plan["source_access"]["states"]["boursa_kuwait"], "AVAILABLE")

    def test_blocked_current_site_does_not_corrupt_valid_historical_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            pack = synthetic_pack(Path(directory) / "pack")
            access = Path(directory) / "access.json"
            access.write_text(json.dumps({"observed_at": "2026-08-06T12:00:00+03:00", "sources": [{"source_id": "boursa_kuwait", "state": "BLOCKED"}]}), encoding="utf-8")
            plan = self.pipeline.plan(
                "next_session_plus_10_event",
                pack_root=pack,
                source_access_path=access,
                mode="validated_forecast",
            )
            self.assertEqual(plan["status"], "SYNTHETIC_CONTRACT_ONLY")
            self.assertEqual(plan["source_access"]["states"]["boursa_kuwait"], "BLOCKED")

    def test_mutated_raw_bytes_block_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            pack = synthetic_pack(Path(directory) / "pack")
            (pack / "raw" / "eod.json").write_bytes(b"mutated")
            validation = PackValidator(pack, self.catalog).validate()
            self.assertEqual(validation.status, "BLOCKED")
            self.assertTrue(any("artifact" in item.lower() and "mismatch" in item.lower() for item in validation.errors))

    def test_mutated_normalized_file_blocks_capability(self):
        with tempfile.TemporaryDirectory() as directory:
            pack = synthetic_pack(Path(directory) / "pack")
            with (pack / "normalized" / "eod_ohlcv.csv").open("a", encoding="utf-8") as handle:
                handle.write("\n")
            validation = PackValidator(pack, self.catalog).validate()
            self.assertEqual(validation.status, "BLOCKED")
            self.assertTrue(any("NORMALIZED_HASH_MISMATCH" in item for item in validation.errors))

    def test_secondary_source_cannot_establish_daily_eod(self):
        with tempfile.TemporaryDirectory() as directory:
            pack = synthetic_pack(Path(directory) / "pack")
            path = pack / "manifests" / "capability_report.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            for row in payload["attestations"]:
                if row["capability"] == "daily_eod":
                    row["source_ids"] = ["investing_com"]
            path.write_text(json.dumps(payload), encoding="utf-8")
            validation = PackValidator(pack, self.catalog).validate()
            self.assertEqual(validation.status, "BLOCKED")
            self.assertTrue(any("daily_eod" in item or "does not declare" in item for item in validation.errors))

    def test_benchmark_capability_uses_strict_validator_not_generic_hash_check(self):
        with tempfile.TemporaryDirectory() as directory:
            pack = synthetic_pack(Path(directory) / "pack")
            manifest = json.loads(
                (pack / "manifests" / "file_manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            raw_hash = next(
                row["sha256"]
                for row in manifest["artifacts"]
                if row["path"] == "raw/eod.json"
            )
            normalized = pack / "normalized" / "malformed_benchmark.csv"
            normalized.write_text(
                f"raw_sha256\n{raw_hash}\n",
                encoding="utf-8",
            )
            report_path = pack / "manifests" / "capability_report.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["attestations"].append(
                {
                    "capability": "benchmark_history",
                    "status": "PASS",
                    "source_ids": ["boursa_kuwait"],
                    "evidence_hashes": [raw_hash],
                    "normalized_path": "normalized/malformed_benchmark.csv",
                    "normalized_sha256": sha256_file(normalized),
                    "validator_id": "kubo.benchmark_history",
                    "validator_version": "1.0",
                    "validated_at": "2026-08-06T14:00:00+03:00",
                    "access_class": "PUBLIC_OFFICIAL",
                    "coverage_numerator": 1,
                    "coverage_denominator": 1,
                    "limitations": ["SYNTHETIC_TEST_DATA_ONLY"],
                }
            )
            report_path.write_text(json.dumps(report), encoding="utf-8")

            validation = PackValidator(pack, self.catalog).validate()
            self.assertEqual(validation.status, "BLOCKED")
            self.assertTrue(
                any("BENCHMARK_HISTORY_READ" in item for item in validation.errors),
                validation.errors,
            )

    def test_unverified_internal_benchmark_definitions_cannot_become_ready(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = load_benchmark_registry(ROOT / "config")
            path = Path(directory) / "benchmark_history.csv"
            hashes_by_source: dict[str, set[str]] = {}
            rows = []
            for index, definition in enumerate(registry.benchmarks, start=1):
                digest = f"{index:064x}"
                hashes_by_source.setdefault(definition.source_id, set()).add(digest)
                rows.append(
                    {
                        field: ""
                        for field in BENCHMARK_HISTORY_HEADERS
                    }
                    | {
                        "benchmark_code": definition.benchmark_code,
                        "source_url": definition.source_url,
                        "raw_sha256": digest,
                        "observed_at": "2026-08-10T09:00:00+03:00",
                        "capture_mode": "LICENSED_VENDOR_EXPORT",
                        "rights_status": "RESEARCH_USE_AUTHORIZED",
                        "evidence_classification": "PROVEN_REAL_EVIDENCE",
                    }
                )
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=BENCHMARK_HISTORY_HEADERS,
                    lineterminator="\n",
                )
                writer.writeheader()
                writer.writerows(rows)

            strict_pass = SimpleNamespace(
                status="PASS",
                errors=(),
                rows=len(rows),
                benchmarks=len(rows),
                coverage={
                    row["benchmark_code"]: {
                        "evidence_classification": "PROVEN_REAL_EVIDENCE"
                    }
                    for row in rows
                },
                claim_boundaries={},
            )
            collection = CollectionContract(
                pack_id="contract-test",
                as_of="2026-08-10T10:00:00+03:00",
                window_from=date(2026, 8, 10),
                window_to=date(2026, 8, 10),
                timezone="Asia/Kuwait",
                included_boards=("cash",),
                run_status="QUALIFIED",
                synthetic=False,
            )
            with patch(
                "kubo.pack.validate_benchmark_history_rows",
                return_value=((), strict_pass),
            ):
                result = _validate_benchmark_history_capability(
                    path,
                    manifest_hashes=frozenset().union(*hashes_by_source.values()),
                    manifest_hashes_by_source={
                        source: frozenset(hashes)
                        for source, hashes in hashes_by_source.items()
                    },
                    calendar={date(2026, 8, 10): {"is_trading_day": True}},
                    collection=collection,
                    catalog=self.catalog,
                )

            self.assertEqual(result.status, "BLOCKED")
            self.assertIn(
                "BENCHMARK_REGISTRY_DEFINITION_NOT_VERIFIED",
                result.errors,
            )
            self.assertFalse(result.details["definitions_verified"])

    def test_packet_local_fixture_relabeling_cannot_promote_data_readiness(self):
        with tempfile.TemporaryDirectory() as directory:
            pack = synthetic_pack(Path(directory) / "pack")
            collection_path = pack / "manifests" / "collection_run.json"
            collection = json.loads(collection_path.read_text(encoding="utf-8"))
            collection["synthetic"] = False
            collection_path.write_text(json.dumps(collection), encoding="utf-8")

            report_path = pack / "manifests" / "capability_report.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            for attestation in report["attestations"]:
                attestation["limitations"] = ["RECORDED_CONTRACT_DATA_ONLY"]
            report_path.write_text(json.dumps(report), encoding="utf-8")

            validation = PackValidator(pack, self.catalog).validate()
            self.assertEqual(validation.status, "PASS", validation.to_dict())
            plan = self.pipeline.plan(
                "next_session_plus_10_event",
                pack_root=pack,
                mode="validated_forecast",
            )
            self.assertIn(
                "FINAL_DATA_FOUNDATION_GATE_REQUIRED_FOR_DATA_READINESS",
                plan["reasons"],
            )
            self.assertEqual(
                plan["status"],
                "EVIDENCE_CONTRACT_VALIDATED_MODEL_UNBOUND",
            )
            self.assertNotEqual(plan["status"], "DATA_READY_MODEL_UNBOUND")

            model_root = Path(directory) / "model-card"
            model_root.mkdir()
            model_path, _, _ = write_prospectively_validated_card(
                model_root,
                self.catalog.products["next_session_plus_10_event"],
            )
            with_model = self.pipeline.plan(
                "next_session_plus_10_event",
                pack_root=pack,
                model_card_path=model_path,
                mode="validated_forecast",
            )
            self.assertEqual(
                with_model["status"],
                "EVIDENCE_AND_MODEL_CONTRACT_VALIDATED",
            )
            self.assertIn(
                "FINAL_DATA_FOUNDATION_GATE_REQUIRED_FOR_FORECAST_READINESS",
                with_model["reasons"],
            )
            self.assertNotEqual(with_model["status"], "FORECAST_POLICY_READY")

    def test_official_attestation_cannot_resolve_secondary_source_bytes(self):
        """An official source label must bind the exact raw evidence hash."""

        with tempfile.TemporaryDirectory() as directory:
            pack = synthetic_pack(Path(directory) / "pack")
            path = pack / "manifests" / "file_manifest.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            eod = next(row for row in payload["artifacts"] if row["path"] == "raw/eod.json")
            eod["source_id"] = "investing_com"
            eod["source_url"] = "https://www.investing.com/equities/kuwait"
            path.write_text(json.dumps(payload), encoding="utf-8")

            validation = PackValidator(pack, self.catalog).validate()
            self.assertEqual(validation.status, "BLOCKED")
            self.assertTrue(
                any("not bound to a declared source" in item for item in validation.errors),
                validation.errors,
            )

    def test_normalized_raw_hash_must_belong_to_its_capability_evidence(self):
        """A globally valid hash from another dataset cannot back an EOD row."""

        with tempfile.TemporaryDirectory() as directory:
            pack = synthetic_pack(Path(directory) / "pack")
            manifest = json.loads(
                (pack / "manifests" / "file_manifest.json").read_text(encoding="utf-8")
            )
            eod_hash = next(
                row["sha256"] for row in manifest["artifacts"] if row["path"] == "raw/eod.json"
            )
            master_hash = next(
                row["sha256"] for row in manifest["artifacts"] if row["path"] == "raw/master.json"
            )
            normalized = pack / "normalized" / "eod_ohlcv.csv"
            normalized.write_text(
                normalized.read_text(encoding="utf-8").replace(eod_hash, master_hash),
                encoding="utf-8",
            )
            report_path = pack / "manifests" / "capability_report.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            daily_eod = next(
                row for row in report["attestations"] if row["capability"] == "daily_eod"
            )
            daily_eod["normalized_sha256"] = sha256_file(normalized)
            report_path.write_text(json.dumps(report), encoding="utf-8")

            validation = PackValidator(pack, self.catalog).validate()
            self.assertEqual(validation.status, "BLOCKED")
            self.assertTrue(
                any("daily_eod" in item and "raw_sha256 does not resolve" in item for item in validation.errors),
                validation.errors,
            )

    def test_artifact_observed_after_collection_cutoff_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            pack = synthetic_pack(Path(directory) / "pack")
            path = pack / "manifests" / "file_manifest.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["artifacts"][0]["observed_at"] = "2026-08-06T14:00:01+03:00"
            path.write_text(json.dumps(payload), encoding="utf-8")

            validation = PackValidator(pack, self.catalog).validate()
            self.assertEqual(validation.status, "BLOCKED")
            self.assertTrue(
                any("observed_at is after the collection cutoff" in item for item in validation.errors),
                validation.errors,
            )

    def test_capability_report_and_validation_times_respect_collection_cutoff(self):
        with tempfile.TemporaryDirectory() as directory:
            pack = synthetic_pack(Path(directory) / "pack")
            path = pack / "manifests" / "capability_report.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["attestations"][0]["validated_at"] = "2026-08-06T14:00:01+03:00"
            path.write_text(json.dumps(payload), encoding="utf-8")

            validation = PackValidator(pack, self.catalog).validate()
            self.assertEqual(validation.status, "BLOCKED")
            self.assertTrue(
                any("validated_at is after the collection cutoff" in item for item in validation.errors),
                validation.errors,
            )

    def test_capability_report_as_of_respects_collection_cutoff(self):
        with tempfile.TemporaryDirectory() as directory:
            pack = synthetic_pack(Path(directory) / "pack")
            path = pack / "manifests" / "capability_report.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["as_of"] = "2026-08-06T14:00:01+03:00"
            path.write_text(json.dumps(payload), encoding="utf-8")

            validation = PackValidator(pack, self.catalog).validate()
            self.assertEqual(validation.status, "BLOCKED")
            self.assertTrue(
                any("capability report as_of is after the collection cutoff" in item for item in validation.errors),
                validation.errors,
            )

    def test_normalized_availability_timestamp_respects_collection_cutoff(self):
        with tempfile.TemporaryDirectory() as directory:
            pack = synthetic_pack(Path(directory) / "pack")
            normalized = pack / "normalized" / "eod_ohlcv.csv"
            lines = normalized.read_text(encoding="utf-8").splitlines()
            lines[0] += ",observed_at"
            lines[1] += ",2026-08-06T14:00:01+03:00"
            normalized.write_text("\n".join(lines) + "\n", encoding="utf-8")
            report_path = pack / "manifests" / "capability_report.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            daily_eod = next(
                row for row in report["attestations"] if row["capability"] == "daily_eod"
            )
            daily_eod["normalized_sha256"] = sha256_file(normalized)
            report_path.write_text(json.dumps(report), encoding="utf-8")

            validation = PackValidator(pack, self.catalog).validate()
            self.assertEqual(validation.status, "BLOCKED")
            self.assertTrue(
                any("observed_at is after collection as_of" in item for item in validation.errors),
                validation.errors,
            )

    def test_google_drive_cannot_establish_market_capability(self):
        source = self.catalog.sources["project_google_drive"]
        self.assertEqual(source.role, "STORAGE_ONLY")
        self.assertFalse(source.market_evidence_allowed)


if __name__ == "__main__":
    unittest.main()
