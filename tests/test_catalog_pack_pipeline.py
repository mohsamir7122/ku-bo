from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from kubo.catalog import Catalog
from kubo.hashing import sha256_file
from kubo.pack import PackValidator
from kubo.pipeline import ResearchPipeline

from helpers import synthetic_pack


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

    def test_synthetic_pack_passes_but_model_remains_unbound(self):
        with tempfile.TemporaryDirectory() as directory:
            pack = synthetic_pack(Path(directory) / "pack")
            validation = PackValidator(pack, self.catalog).validate()
            self.assertEqual(validation.status, "PASS", validation.to_dict())
            plan = self.pipeline.plan("next_session_rank", pack_root=pack, mode="validated_forecast")
            self.assertEqual(plan["status"], "DATA_READY_MODEL_UNBOUND")

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
            plan = self.pipeline.plan("next_session_rank", pack_root=pack, source_access_path=access, mode="validated_forecast")
            self.assertEqual(plan["status"], "DATA_READY_MODEL_UNBOUND")
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
