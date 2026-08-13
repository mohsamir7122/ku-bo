from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from kubo.benchmark_history import BENCHMARK_HISTORY_HEADERS
from kubo.benchmark_import import _import_benchmark_history_unchecked
from tests.benchmark_fixture_helpers import (
    ROOT,
    accept_fixture_manifest,
    prepare_fixture_workspace,
)


class BenchmarkImportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.official, self.workspace, self.trading_dates = prepare_fixture_workspace(
            self.root
        )
        self.output = self.root / "benchmark-output"
        self.manifest_path = (
            self.workspace / "manifests" / "benchmark_history_manifest.json"
        )

    def _accept(self, **kwargs: object) -> dict[str, object]:
        return accept_fixture_manifest(
            self.workspace,
            self.trading_dates,
            **kwargs,
        )

    def _load_manifest(self) -> dict[str, object]:
        return json.loads(self.manifest_path.read_text(encoding="utf-8"))

    def _save_manifest(self, manifest: dict[str, object]) -> None:
        self.manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )

    def _import(self) -> dict[str, object]:
        return _import_benchmark_history_unchecked(
            config_dir=ROOT / "config",
            official_foundation_root=self.official,
            workspace=self.workspace,
            output_root=self.output,
            imported_at="2026-08-10T10:00:00+03:00",
        )

    def test_recorded_fixture_materializes_contract_but_never_real_readiness(self) -> None:
        self._accept()
        report = self._import()
        self.assertEqual(report["status"], "PARTIAL")
        self.assertEqual(report["contract_status"], "PASS")
        self.assertEqual(report["evidence_classification"], "RECORDED_AUTHORIZED_FIXTURE")
        self.assertEqual(
            {entry["rights_status"] for entry in report["benchmark_entries"]},
            {"FIXTURE_ONLY"},
        )
        self.assertEqual(report["query_and_pagination_status"], "PASS")
        self.assertEqual(report["available_benchmark_count"], 10)
        self.assertEqual(report["row_count"], 10 * len(self.trading_dates))
        self.assertFalse(
            report["claim_boundaries"]["benchmark_history_ready_for_declared_window"]
        )
        self.assertTrue((self.output / "manifest.json").is_file())
        self.assertTrue((self.output / "benchmark_registry.json").is_file())
        self.assertTrue((self.output / "benchmark_history_manifest.json").is_file())
        self.assertTrue((self.output / "upstream_calendar_receipt.json").is_file())
        normalized = self.output / "normalized" / "benchmark_history.csv"
        self.assertTrue(normalized.is_file())
        with normalized.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(tuple(rows[0]), BENCHMARK_HISTORY_HEADERS)
        self.assertEqual(len(rows), report["row_count"])
        self.assertEqual(
            {row["evidence_classification"] for row in rows},
            {"RECORDED_AUTHORIZED_FIXTURE"},
        )
        evidence = json.loads((self.output / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(len(evidence["artifacts"]), 10)
        self.assertTrue(
            all(
                row["capture_kind"] == "RECORDED_AUTHORIZED_FIXTURE"
                for row in evidence["artifacts"]
            )
        )

    def test_licensed_exports_remain_feed_dependent_without_external_trust(self) -> None:
        manifest = self._accept()
        for row in manifest["artifacts"]:
            row["capture_mode"] = "LICENSED_VENDOR_EXPORT"
            row["rights_status"] = "RESEARCH_USE_AUTHORIZED"
        self._save_manifest(manifest)
        report = self._import()
        self.assertEqual(report["status"], "PARTIAL")
        self.assertEqual(report["contract_status"], "PASS")
        self.assertEqual(report["evidence_classification"], "LICENSED_FEED_DEPENDENT")
        self.assertEqual(
            {entry["rights_status"] for entry in report["benchmark_entries"]},
            {"RESEARCH_USE_AUTHORIZED"},
        )
        self.assertFalse(
            report["claim_boundaries"][
                "licensed_manifest_claim_is_external_authenticated_trust"
            ]
        )

    def test_synthetic_rows_are_explicit_and_never_real_readiness(self) -> None:
        manifest = self._accept()
        for row in manifest["artifacts"]:
            row["capture_mode"] = "SYNTHETIC_GENERATED"
            row["rights_status"] = "FIXTURE_ONLY"
        self._save_manifest(manifest)
        report = self._import()
        self.assertEqual(report["status"], "PARTIAL")
        self.assertEqual(report["contract_status"], "PASS")
        self.assertEqual(report["evidence_classification"], "SYNTHETIC_ONLY")
        self.assertTrue(
            report["claim_boundaries"]["synthetic_benchmark_rows_created"]
        )
        self.assertFalse(
            report["claim_boundaries"]["synthetic_fixture_is_real_evidence"]
        )
        evidence = json.loads(
            (self.output / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            {row["capture_kind"] for row in evidence["artifacts"]},
            {"SYNTHETIC_GENERATED"},
        )

    def test_manifest_relabel_cannot_prove_official_capture_bytes(self) -> None:
        manifest = self._accept()
        registry_payload = json.loads(
            (ROOT / "config" / "pilot" / "benchmark_registry.json").read_text(
                encoding="utf-8"
            )
        )
        for definition in registry_payload["benchmarks"]:
            definition["source_access"] = "PUBLIC_OFFICIAL_EXPORT"
            definition["rights_requirement"] = "PUBLIC_RESEARCH_ALLOWED"
            definition["registry_state"] = "VERIFIED_DEFINITION"
        config_dir = self.root / "verified-config"
        registry_path = config_dir / "pilot" / "benchmark_registry.json"
        registry_path.parent.mkdir(parents=True)
        registry_bytes = json.dumps(
            registry_payload,
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
        registry_path.write_bytes(registry_bytes)
        (self.workspace / "manifests" / "benchmark_registry.json").write_bytes(
            registry_bytes
        )
        manifest["registry_sha256"] = hashlib.sha256(registry_bytes).hexdigest()
        for row in manifest["artifacts"]:
            row["capture_mode"] = "PUBLIC_OFFICIAL_EXPORT"
            row["rights_status"] = "RESEARCH_USE_AUTHORIZED"
        self._save_manifest(manifest)

        report = _import_benchmark_history_unchecked(
            config_dir=config_dir,
            official_foundation_root=self.official,
            workspace=self.workspace,
            output_root=self.output,
            imported_at="2026-08-10T10:00:00+03:00",
        )

        self.assertEqual(report["status"], "PARTIAL")
        self.assertEqual(report["contract_status"], "PASS")
        self.assertEqual(report["evidence_classification"], "LIVE_DEPENDENT")
        self.assertFalse(
            report["claim_boundaries"][
                "artifact_bound_capture_authority_verified"
            ]
        )
        self.assertFalse(
            report["claim_boundaries"][
                "benchmark_history_ready_for_declared_window"
            ]
        )

    def test_daily_close_observed_at_must_follow_official_session_close(self) -> None:
        manifest = self._accept()
        latest = max(self.trading_dates)
        for row in manifest["artifacts"]:
            row["observed_at"] = f"{latest}T00:01:00+03:00"
        self._save_manifest(manifest)
        with self.assertRaisesRegex(
            ValueError,
            "observed_at precedes official session close",
        ):
            self._import()
        self.assertFalse(self.output.exists())

    def test_observed_at_must_not_follow_declared_import_time(self) -> None:
        manifest = self._accept()
        for row in manifest["artifacts"]:
            row["observed_at"] = "2026-08-10T10:01:00+03:00"
        self._save_manifest(manifest)
        with self.assertRaisesRegex(ValueError, "after benchmark imported_at"):
            self._import()
        self.assertFalse(self.output.exists())

    def test_declared_import_time_must_not_be_in_the_future(self) -> None:
        self._accept()
        with self.assertRaisesRegex(ValueError, "imported_at must not be in the future"):
            _import_benchmark_history_unchecked(
                config_dir=ROOT / "config",
                official_foundation_root=self.official,
                workspace=self.workspace,
                output_root=self.output,
                imported_at="2099-01-01T00:00:00+03:00",
            )
        self.assertFalse(self.output.exists())

    def test_zero_and_unavailable_are_explicit_and_never_substituted(self) -> None:
        pending = self._load_manifest()["artifacts"]
        zero_code = pending[0]["benchmark_code"]
        unavailable_code = pending[1]["benchmark_code"]
        self._accept(
            availability={
                zero_code: "ZERO_RESULT",
                unavailable_code: "UNAVAILABLE",
            }
        )
        report = self._import()
        self.assertEqual(report["status"], "PARTIAL")
        by_code = {row["benchmark_code"]: row for row in report["benchmark_entries"]}
        self.assertEqual(by_code[zero_code]["availability_status"], "ZERO_RESULT")
        self.assertEqual(by_code[unavailable_code]["availability_status"], "UNAVAILABLE")
        self.assertEqual(by_code[unavailable_code]["rights_status"], "RESTRICTED")
        self.assertEqual(by_code[zero_code]["row_count"], 0)
        self.assertEqual(by_code[unavailable_code]["row_count"], 0)
        self.assertIn(f"BENCHMARK_ZERO_RESULT:{zero_code}", report["errors"])
        self.assertTrue(
            any(
                error.startswith(f"BENCHMARK_UNAVAILABLE:{unavailable_code}")
                for error in report["errors"]
            )
        )
        self.assertFalse(report["claim_boundaries"]["fallback_benchmark_substitution_used"])
        normalized = (self.output / "normalized" / "benchmark_history.csv").read_text(
            encoding="utf-8"
        )
        self.assertNotIn(zero_code, normalized)
        self.assertNotIn(unavailable_code, normalized)

    def test_all_unavailable_is_blocked_with_a_licensed_dependency(self) -> None:
        codes = [row["benchmark_code"] for row in self._load_manifest()["artifacts"]]
        self._accept(availability={code: "UNAVAILABLE" for code in codes})
        report = self._import()
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(report["contract_status"], "BLOCKED")
        self.assertEqual(report["evidence_classification"], "LICENSED_FEED_DEPENDENT")
        self.assertEqual(report["row_count"], 0)

    def test_calendar_gap_is_partial_and_no_row_is_filled(self) -> None:
        code = self._load_manifest()["artifacts"][0]["benchmark_code"]
        missing_date = self.trading_dates[1]
        self._accept(omitted_dates={code: {missing_date}})
        report = self._import()
        self.assertEqual(report["status"], "PARTIAL")
        self.assertEqual(report["contract_status"], "BLOCKED")
        entry = next(row for row in report["benchmark_entries"] if row["benchmark_code"] == code)
        self.assertEqual(entry["missing_trading_dates"], [missing_date])
        self.assertFalse(report["claim_boundaries"]["forward_fill_used"])
        with (self.output / "normalized" / "benchmark_history.csv").open(
            encoding="utf-8", newline=""
        ) as handle:
            rows = list(csv.DictReader(handle))
        self.assertFalse(
            any(
                row["benchmark_code"] == code and row["trade_date"] == missing_date
                for row in rows
            )
        )

    def test_pagination_mismatch_fails_before_output(self) -> None:
        manifest = self._accept()
        manifest["artifacts"][0]["pages_received"] = 0
        self._save_manifest(manifest)
        with self.assertRaisesRegex(ValueError, "pagination is incomplete"):
            self._import()
        self.assertFalse(self.output.exists())

    def test_result_count_mismatch_fails_before_output(self) -> None:
        manifest = self._accept()
        manifest["artifacts"][0]["result_count_declared"] += 1
        manifest["artifacts"][0]["row_count"] += 1
        self._save_manifest(manifest)
        with self.assertRaisesRegex(ValueError, "row_count mismatch"):
            self._import()
        self.assertFalse(self.output.exists())

    def test_raw_hash_mismatch_fails_before_output(self) -> None:
        manifest = self._accept()
        manifest["artifacts"][0]["file_sha256"] = "0" * 64
        self._save_manifest(manifest)
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            self._import()
        self.assertFalse(self.output.exists())

    def test_stale_upstream_calendar_receipt_fails_before_output(self) -> None:
        self._accept()
        calendar = self.official / "normalized" / "trading_calendar.csv"
        calendar.write_bytes(calendar.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "stale or mismatched upstream"):
            self._import()
        self.assertFalse(self.output.exists())

    def test_impossible_value_fails_before_output(self) -> None:
        code = self._load_manifest()["artifacts"][0]["benchmark_code"]
        values = ["1000.0"] * len(self.trading_dates)
        values[0] = "0"
        self._accept(value_overrides={code: values})
        with self.assertRaisesRegex(ValueError, "outside the allowed positive range"):
            self._import()
        self.assertFalse(self.output.exists())

    def test_duplicate_available_evidence_hashes_are_rejected_as_substitution(self) -> None:
        manifest = self._accept()
        first, second = manifest["artifacts"][:2]
        raw_dir = self.workspace / "raw_exports" / "benchmarks"
        content = (raw_dir / first["file_name"]).read_bytes()
        (raw_dir / second["file_name"]).write_bytes(content)
        second["file_sha256"] = hashlib.sha256(content).hexdigest()
        self._save_manifest(manifest)
        with self.assertRaisesRegex(ValueError, "distinct evidence hashes"):
            self._import()
        self.assertFalse(self.output.exists())

    def test_duplicate_or_windows_unsafe_file_name_is_rejected(self) -> None:
        manifest = self._accept()
        for name, expected in (
            (manifest["artifacts"][0]["file_name"], "duplicate file_name"),
            ("benchmark.csv:secret", "path-safe component"),
        ):
            with self.subTest(name=name):
                mutated = json.loads(json.dumps(manifest))
                mutated["artifacts"][1]["file_name"] = name
                self._save_manifest(mutated)
                with self.assertRaisesRegex(ValueError, expected):
                    self._import()
                self.assertFalse(self.output.exists())

    def test_observation_time_cannot_precede_export_history(self) -> None:
        manifest = self._accept()
        manifest["artifacts"][0]["observed_at"] = "2026-08-01T09:00:00+03:00"
        self._save_manifest(manifest)
        with self.assertRaisesRegex(ValueError, "data after observed_at"):
            self._import()
        self.assertFalse(self.output.exists())

    def test_import_refuses_nonempty_output(self) -> None:
        self._accept()
        self._import()
        with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
            self._import()

    def test_symlinked_raw_artifact_is_rejected(self) -> None:
        manifest = self._accept()
        row = manifest["artifacts"][0]
        target = self.workspace / "external.csv"
        target.write_bytes(
            self.workspace.joinpath("raw_exports", "benchmarks", row["file_name"]).read_bytes()
        )
        artifact = self.workspace / "raw_exports" / "benchmarks" / row["file_name"]
        artifact.unlink()
        try:
            artifact.symlink_to(target)
        except OSError as exc:
            self.skipTest(f"symlink creation unavailable: {exc}")
        with self.assertRaisesRegex(ValueError, "must not contain symlinks"):
            self._import()
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
