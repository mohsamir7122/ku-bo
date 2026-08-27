from __future__ import annotations

from contextlib import redirect_stderr
import io
from pathlib import Path
import tomllib
import unittest

from kubo import __version__
from kubo.cli_v3 import parser
from kubo.ingestion import DEFAULT_USER_AGENT


ROOT = Path(__file__).resolve().parents[1]


class ReleaseMetadataTests(unittest.TestCase):
    def test_hash_bound_text_formats_are_forced_to_lf(self) -> None:
        attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
        for extension in ("csv", "html", "json", "jsonl"):
            with self.subTest(extension=extension):
                self.assertIn(f"*.{extension} text eol=lf", attributes)

    def test_package_runtime_and_actor_versions_match(self) -> None:
        project_file = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        metadata = project_file["project"]
        self.assertEqual(project_file["build-system"]["requires"], ["setuptools==83.0.0"])
        self.assertEqual(metadata["version"], __version__)
        self.assertEqual(__version__, "0.1.0")
        self.assertEqual(metadata["dependencies"], ["tzdata==2026.3"])
        self.assertEqual(
            project_file["project"]["optional-dependencies"]["test"],
            ["jsonschema==4.25.1", "PyYAML==6.0.3"],
        )
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
                "--evidence-pack",
                "outcome-evidence/outcome-1",
            ]
        )
        self.assertEqual(args.actor, f"kubo-outcome-recorder/{__version__}")
        self.assertEqual(args.evidence_pack, Path("outcome-evidence/outcome-1"))

        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            parser().parse_args(
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
        self.assertEqual(caught.exception.code, 2)

    def test_proprietary_license_is_bound_to_package_metadata(self) -> None:
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
        self.assertEqual(metadata["license"], {"file": "LICENSE"})
        self.assertEqual(metadata["readme"]["file"], "README.md")
        self.assertEqual(metadata["authors"], [{"name": "Mohamed Samir Rashed Shaheen"}])
        self.assertEqual(
            metadata["urls"]["Repository"],
            "https://github.com/mohsamir7122/ku-bo",
        )
        license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
        self.assertIn("Mohamed Samir Rashed Shaheen", license_text)
        self.assertIn("ALL RIGHTS RESERVED", license_text)


if __name__ == "__main__":
    unittest.main()
