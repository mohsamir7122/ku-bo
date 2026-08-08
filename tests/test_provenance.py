from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from kubo.hashing import sha256_bytes
from kubo.pipeline import ResearchPipeline
from kubo.provenance import evidence_packet_hash, runtime_package_hash, source_tree_hash
from kubo.synthetic_network import build_synthetic_network_run


class ProvenanceTests(unittest.TestCase):
    def test_runtime_package_hash_is_location_independent_and_content_sensitive(self) -> None:
        with tempfile.TemporaryDirectory() as first_temp, tempfile.TemporaryDirectory() as second_temp:
            first = Path(first_temp) / "kubo"
            second = Path(second_temp) / "kubo"
            first.mkdir()
            second.mkdir()
            for root in (first, second):
                (root / "__init__.py").write_text('VERSION = "1"\n', encoding="utf-8")
                (root / "engine.py").write_text("VALUE = 1\n", encoding="utf-8")
                (root / "__pycache__").mkdir()
                (root / "__pycache__" / "engine.pyc").write_bytes(b"ignored cache")
            self.assertEqual(runtime_package_hash(first), runtime_package_hash(second))
            (second / "engine.py").write_text("VALUE = 2\n", encoding="utf-8")
            self.assertNotEqual(runtime_package_hash(first), runtime_package_hash(second))

    def test_runtime_package_hash_cannot_fall_back_to_an_external_config_tree(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "config").mkdir()
            (root / "config" / "products.json").write_text("{}\n", encoding="utf-8")
            empty_package = root / "kubo"
            empty_package.mkdir()
            with self.assertRaisesRegex(ValueError, "no hashable files"):
                runtime_package_hash(empty_package)

        self.assertRegex(runtime_package_hash(), r"^[0-9a-f]{64}$")

    def test_source_tree_hash_is_order_independent_and_content_sensitive(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "src").mkdir()
            (root / "src" / "b.py").write_text("b = 2\n", encoding="utf-8")
            (root / "src" / "a.py").write_text("a = 1\n", encoding="utf-8")
            first = source_tree_hash(root, ("src",))
            second = source_tree_hash(root, ("src",))
            self.assertEqual(first, second)
            (root / "src" / "a.py").write_text("a = 3\n", encoding="utf-8")
            self.assertNotEqual(first, source_tree_hash(root, ("src",)))

    def test_default_hash_includes_policy_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "src").mkdir()
            (root / "src" / "engine.py").write_text("VALUE = 1\n", encoding="utf-8")
            (root / "config").mkdir()
            policy = root / "config" / "research_policies.json"
            policy.write_text('{"minimum_sources": 4}\n', encoding="utf-8")
            first = source_tree_hash(root)
            policy.write_text('{"minimum_sources": 1}\n', encoding="utf-8")
            self.assertNotEqual(first, source_tree_hash(root))

    def test_evidence_packet_hash_covers_raw_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in (
                "research_run.json",
                "universe.json",
                "source_observations.json",
                "findings.jsonl",
            ):
                (root / name).write_text("{}\n", encoding="utf-8")
            (root / "raw").mkdir()
            raw = root / "raw" / "source.bin"
            raw.write_bytes(b"first")
            manifest = {
                "artifacts": [
                    {
                        "path": "raw/source.bin",
                        "sha256": sha256_bytes(b"first"),
                    }
                ]
            }
            (root / "manifest.json").write_text(
                json.dumps(manifest) + "\n", encoding="utf-8"
            )
            first = evidence_packet_hash(root)
            raw.write_bytes(b"second")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                evidence_packet_hash(root)
            manifest["artifacts"][0]["sha256"] = sha256_bytes(b"second")
            (root / "manifest.json").write_text(
                json.dumps(manifest) + "\n", encoding="utf-8"
            )
            self.assertNotEqual(first, evidence_packet_hash(root))

    def test_unreferenced_raw_scratch_file_is_not_part_of_canonical_packet(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in (
                "research_run.json",
                "universe.json",
                "source_observations.json",
                "findings.jsonl",
            ):
                (root / name).write_text("{}\n", encoding="utf-8")
            (root / "raw").mkdir()
            raw = root / "raw" / "referenced.bin"
            raw.write_bytes(b"evidence")
            (root / "manifest.json").write_text(
                json.dumps(
                    {
                        "artifacts": [
                            {
                                "path": "raw/referenced.bin",
                                "sha256": sha256_bytes(b"evidence"),
                            }
                        ]
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            first = evidence_packet_hash(root)
            (root / "raw" / "scratch.tmp").write_bytes(b"not in manifest")
            self.assertEqual(first, evidence_packet_hash(root))

    def test_pipeline_blocks_when_packet_changes_after_validation(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp:
            run = build_synthetic_network_run(Path(temp) / "run")
            with mock.patch("kubo.pipeline.evidence_packet_hash", return_value="f" * 64):
                plan = ResearchPipeline(project_root).plan(
                    "next_session_rank",
                    network_run_root=run,
                )
        self.assertEqual(plan["status"], "SOURCE_NETWORK_BLOCKED")
        self.assertEqual(plan["ranked_candidates"], [])
        self.assertIn("EVIDENCE_PACKET_CHANGED_AFTER_VALIDATION", plan["reasons"])


if __name__ == "__main__":
    unittest.main()
