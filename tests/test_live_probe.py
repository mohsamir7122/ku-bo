from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest

from kubo.hashing import sha256_bytes
from kubo.source_network import SourceNetworkCatalog, validate_live_probe


ROOT = Path(__file__).resolve().parents[1]


class LiveProbeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = SourceNetworkCatalog(ROOT / "config")
        self.now = datetime.fromisoformat("2026-08-07T10:00:00+03:00")

    def _write_probe(self, directory: Path) -> tuple[Path, dict[str, object]]:
        raw = directory / "raw" / "boursa.html"
        raw.parent.mkdir(parents=True)
        content = b"<html><body>generated access receipt</body></html>"
        raw.write_bytes(content)
        payload: dict[str, object] = {
            "schema_version": "3.1-access-probe",
            "probe_id": "probe-generated-contract-001",
            "probe_version": "generated-contract-v1",
            "observed_at": "2026-08-07T09:55:00+03:00",
            "expires_at": "2026-08-08T09:55:00+03:00",
            "purpose": "Access-only contract test; not market evidence.",
            "sources": [
                {
                    "source_id": "boursa_current",
                    "state": "AVAILABLE",
                    "tested_url": "https://www.boursakuwait.com.kw/",
                    "final_url": "https://www.boursakuwait.com.kw/",
                    "attempted_at": "2026-08-07T09:54:00+03:00",
                    "http_status": 200,
                    "observation": "Generated contract fixture was readable.",
                    "data_quality_flags": ["GENERATED_CONTRACT_FIXTURE"],
                    "artifact": {
                        "path": "raw/boursa.html",
                        "sha256": sha256_bytes(content),
                        "size_bytes": len(content),
                        "content_type": "text/html",
                        "capture_kind": "USER_EXPORT",
                    },
                }
            ],
        }
        path = directory / "probe.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path, payload

    def test_hash_bound_fresh_probe_passes_access_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path, _ = self._write_probe(Path(temporary))
            report = validate_live_probe(path, self.catalog, now=self.now)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(len(report["probe_hash"]), 64)
        self.assertFalse(report["claim_boundaries"]["access_probe_is_market_evidence"])
        self.assertFalse(report["claim_boundaries"]["access_probe_is_forecast"])

    def test_expired_probe_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path, _ = self._write_probe(Path(temporary))
            report = validate_live_probe(
                path,
                self.catalog,
                now=datetime.fromisoformat("2026-08-08T10:00:00+03:00"),
            )
        self.assertEqual(report["status"], "BLOCKED")
        self.assertIn("expired", report["errors"][0])

    def test_available_probe_with_hash_mismatch_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path, payload = self._write_probe(Path(temporary))
            changed = deepcopy(payload)
            changed["sources"][0]["artifact"]["sha256"] = "0" * 64
            path.write_text(json.dumps(changed), encoding="utf-8")
            report = validate_live_probe(path, self.catalog, now=self.now)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertIn("bytes do not match", report["errors"][0])

    def test_available_probe_without_artifact_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path, payload = self._write_probe(Path(temporary))
            changed = deepcopy(payload)
            changed["sources"][0]["artifact"] = None
            path.write_text(json.dumps(changed), encoding="utf-8")
            report = validate_live_probe(path, self.catalog, now=self.now)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertIn("requires a hash-bound raw artifact", report["errors"][0])

    def test_probe_rejects_unstable_quality_flags(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path, payload = self._write_probe(Path(temporary))
            changed = deepcopy(payload)
            changed["sources"][0]["data_quality_flags"] = ["free form"]
            path.write_text(json.dumps(changed), encoding="utf-8")
            report = validate_live_probe(path, self.catalog, now=self.now)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertIn("stable uppercase codes", report["errors"][0])

    def test_probe_rejects_attempt_after_observation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path, payload = self._write_probe(Path(temporary))
            changed = deepcopy(payload)
            changed["sources"][0]["attempted_at"] = "2026-08-07T09:56:00+03:00"
            path.write_text(json.dumps(changed), encoding="utf-8")
            report = validate_live_probe(path, self.catalog, now=self.now)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertIn("attempted_at is after", report["errors"][0])

    def test_probe_rejects_symlinked_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            path, _ = self._write_probe(directory)
            raw = directory / "raw" / "boursa.html"
            target = directory / "raw" / "target.html"
            raw.rename(target)
            raw.symlink_to(target.name)
            report = validate_live_probe(path, self.catalog, now=self.now)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertIn("must not contain symlinks", report["errors"][0])


if __name__ == "__main__":
    unittest.main()
