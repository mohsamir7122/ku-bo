from __future__ import annotations

from pathlib import Path
import tomllib
import unittest

from kubo import __version__
from kubo.cli_v3 import parser
from kubo.ingestion import DEFAULT_USER_AGENT


ROOT = Path(__file__).resolve().parents[1]


class ReleaseMetadataTests(unittest.TestCase):
    def test_package_runtime_and_actor_versions_match(self) -> None:
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
        self.assertEqual(metadata["version"], __version__)
        self.assertEqual(__version__, "0.1.0")
        self.assertIn(f"/{__version__}", DEFAULT_USER_AGENT)

        args = parser().parse_args(
            [
                "append-research-outcome",
                "--ledger-dir",
                "runtime/ledger",
                "--ledger-id",
                "test-ledger",
                "--outcome-id",
                "outcome-1",
                "--decision-id",
                "decision-1",
                "--observed-at",
                "2026-08-07T12:00:00+03:00",
                "--payload",
                "outcome.json",
                "--evidence-hash",
                "a" * 64,
            ]
        )
        self.assertEqual(args.actor, f"kubo-outcome-recorder/{__version__}")

    def test_proprietary_license_is_bound_to_package_metadata(self) -> None:
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
        self.assertEqual(metadata["license"], {"file": "LICENSE"})
        license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
        self.assertIn("Mohamed Samir Rashed Shaheen", license_text)
        self.assertIn("ALL RIGHTS RESERVED", license_text)


if __name__ == "__main__":
    unittest.main()
