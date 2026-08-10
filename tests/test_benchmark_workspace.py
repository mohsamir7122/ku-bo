from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from kubo.benchmark_registry import load_benchmark_registry
from kubo.benchmark_workspace import (
    load_official_calendar_receipt,
    prepare_benchmark_workspace,
)
from tests.foundation_fixture_helpers import ROOT, build_official_foundation_output


class BenchmarkWorkspaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.official = build_official_foundation_output(self.root)

    def _prepare(self, output_name: str = "workspace") -> tuple[Path, dict[str, object]]:
        output = self.root / output_name
        report = prepare_benchmark_workspace(
            config_dir=ROOT / "config",
            official_foundation_root=self.official,
            output_root=output,
            run_id="benchmark-workspace-001",
            window_from="2026-08-03",
            window_to="2026-08-09",
            prepared_by="workspace-test",
        )
        return output, report

    def test_workspace_freezes_registry_and_upstream_calendar_receipt(self) -> None:
        output, report = self._prepare()
        registry = load_benchmark_registry(ROOT / "config")
        manifest = json.loads(
            (output / "manifests" / "benchmark_history_manifest.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(manifest["registry_sha256"], registry.sha256)
        self.assertEqual(manifest["upstream"]["status"], "CURRENT_IDENTITY_AND_CALENDAR_READY")
        self.assertEqual(len(manifest["artifacts"]), 10)
        self.assertTrue(
            all(row["availability_status"] == "PENDING" for row in manifest["artifacts"])
        )
        self.assertEqual(
            (output / "manifests" / "benchmark_registry.json").read_bytes(),
            registry.source_bytes,
        )
        self.assertFalse(report["claim_boundaries"]["workspace_contains_benchmark_evidence"])

    def test_workspace_emits_one_non_evidence_placeholder_per_series(self) -> None:
        output, _ = self._prepare()
        placeholders = sorted(
            (output / "raw_exports" / "benchmarks").glob("*.placeholder")
        )
        self.assertEqual(len(placeholders), 10)
        text = placeholders[0].read_text(encoding="utf-8")
        self.assertIn("trade_date,benchmark_value", text)
        self.assertIn("Do not invent", text)
        self.assertIn("ZERO_RESULT", text)

    def test_official_calendar_receipt_rehashes_upstream_raw_evidence(self) -> None:
        manifest = json.loads((self.official / "manifest.json").read_text(encoding="utf-8"))
        raw_path = self.official / manifest["artifacts"][0]["path"]
        raw_path.write_bytes(raw_path.read_bytes() + b"tamper")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            load_official_calendar_receipt(self.official)

    def test_workspace_rejects_window_outside_official_calendar_before_creation(self) -> None:
        output = self.root / "not-created"
        with self.assertRaisesRegex(ValueError, "outside the official calendar"):
            prepare_benchmark_workspace(
                config_dir=ROOT / "config",
                official_foundation_root=self.official,
                output_root=output,
                run_id="benchmark-workspace-002",
                window_from="2025-12-31",
                window_to="2026-01-02",
            )
        self.assertFalse(output.exists())

    def test_workspace_refuses_nonempty_output(self) -> None:
        output, _ = self._prepare()
        with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
            prepare_benchmark_workspace(
                config_dir=ROOT / "config",
                official_foundation_root=self.official,
                output_root=output,
                run_id="benchmark-workspace-003",
                window_from="2026-08-03",
                window_to="2026-08-09",
            )

    def test_workspace_rejects_symlinked_official_root(self) -> None:
        link = self.root / "official-link"
        try:
            link.symlink_to(self.official, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"symlink creation unavailable: {exc}")
        with self.assertRaisesRegex(ValueError, "must not contain symlinks"):
            prepare_benchmark_workspace(
                config_dir=ROOT / "config",
                official_foundation_root=link,
                output_root=self.root / "symlink-rejected",
                run_id="benchmark-workspace-004",
                window_from="2026-08-03",
                window_to="2026-08-09",
            )


if __name__ == "__main__":
    unittest.main()
