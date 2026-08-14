from __future__ import annotations

from datetime import date, datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from kubo.atomic_output import AtomicOutputError, OUTPUT_ROOT_ALREADY_EXISTS
from kubo.bootstrap_archive.contract import load_bootstrap_archive_contract
from kubo.bootstrap_archive.workspace import (
    prepare_bootstrap_archive,
    verify_bootstrap_archive,
)
from kubo.hashing import canonical_json_bytes


ROOT = Path(__file__).resolve().parents[1]
AS_OF = date(2026, 8, 14)
PREPARED_AT = datetime(2026, 8, 14, 18, 30, tzinfo=timezone.utc)
EXTERNAL_TEMP_ROOT = (
    Path("/dev/shm") if Path("/dev/shm").is_dir() else Path(tempfile.gettempdir())
)


class BootstrapArchiveWorkspaceTests(unittest.TestCase):
    def _prepare(self, parent: Path, name: str = "bootstrap-archive") -> Path:
        output = parent / name
        report = prepare_bootstrap_archive(
            project_root=ROOT,
            output_root=output,
            as_of=AS_OF,
            prepared_at=PREPARED_AT,
        )
        self.assertEqual(report["status"], "PASS_SCAFFOLD_PREPARATION")
        self.assertEqual(
            report["pre_commit_validation"]["status"],
            "PASS_EMPTY_ARCHIVE_SCAFFOLD",
        )
        return output

    def test_prepare_and_verify_publish_only_an_empty_control_scaffold(self) -> None:
        with tempfile.TemporaryDirectory(dir=EXTERNAL_TEMP_ROOT) as directory:
            archive = self._prepare(Path(directory))
            verification = verify_bootstrap_archive(archive_root=archive)

            self.assertEqual(verification["status"], "PASS_EMPTY_ARCHIVE_SCAFFOLD")
            self.assertEqual(verification["readiness_status"], "PLANNED_NOT_EXECUTED")
            self.assertEqual(verification["historical_source_count"], 28)
            self.assertEqual(verification["historical_layer_count"], 6)
            self.assertEqual(verification["historical_task_count"], 756)
            self.assertEqual(verification["evidence_artifact_count"], 0)
            self.assertEqual(verification["company_count"], 0)
            self.assertEqual(verification["event_count"], 0)
            self.assertIs(verification["collection_allowed"], False)
            self.assertTrue(
                all(value is False for value in verification["claim_boundaries"].values())
            )

            contract = load_bootstrap_archive_contract(
                archive / "control" / "bootstrap_archive.json"
            )
            for relative in contract.directories:
                with self.subTest(directory=relative):
                    self.assertTrue((archive / relative).is_dir())

            descriptor_bytes = (archive / "bootstrap_archive.json").read_bytes()
            descriptor = json.loads(descriptor_bytes)
            self.assertEqual(descriptor_bytes, canonical_json_bytes(descriptor))
            self.assertEqual(descriptor["prepared_at"], "2026-08-14T18:30:00Z")

            manifest = json.loads(
                (archive / "manifests" / "bootstrap_archive_manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(manifest["status"], "SCAFFOLD_ONLY_NO_EVIDENCE")
            self.assertEqual(manifest["evidence_artifacts"], [])
            self.assertEqual(manifest["counts"]["evidence_artifact_count"], 0)
            self.assertTrue(
                all(
                    not row["path"].startswith(("raw/", "normalized/", "receipts/"))
                    for row in manifest["control_artifacts"]
                )
            )

    def test_prepare_is_no_overwrite_and_preserves_the_first_archive(self) -> None:
        with tempfile.TemporaryDirectory(dir=EXTERNAL_TEMP_ROOT) as directory:
            parent = Path(directory)
            archive = self._prepare(parent)
            descriptor_before = (archive / "bootstrap_archive.json").read_bytes()

            with self.assertRaises(AtomicOutputError) as captured:
                prepare_bootstrap_archive(
                    project_root=ROOT,
                    output_root=archive,
                    as_of=AS_OF,
                    prepared_at=PREPARED_AT,
                )

            self.assertEqual(captured.exception.code, OUTPUT_ROOT_ALREADY_EXISTS)
            self.assertEqual(
                (archive / "bootstrap_archive.json").read_bytes(),
                descriptor_before,
            )
            self.assertEqual(
                verify_bootstrap_archive(archive_root=archive)["status"],
                "PASS_EMPTY_ARCHIVE_SCAFFOLD",
            )
            self.assertEqual(
                [path for path in parent.iterdir() if path.name.startswith(".bootstrap-archive.staging-")],
                [],
            )

    def test_prepare_rejects_a_symlink_parent_without_writing_outside(self) -> None:
        with tempfile.TemporaryDirectory(dir=EXTERNAL_TEMP_ROOT) as directory:
            root = Path(directory)
            real_parent = root / "real-parent"
            real_parent.mkdir()
            linked_parent = root / "linked-parent"
            try:
                linked_parent.symlink_to(real_parent, target_is_directory=True)
            except (NotImplementedError, OSError) as exc:
                self.skipTest(f"symlink creation unavailable: {exc}")

            with self.assertRaises((ValueError, AtomicOutputError)) as captured:
                prepare_bootstrap_archive(
                    project_root=ROOT,
                    output_root=linked_parent / "archive",
                    as_of=AS_OF,
                    prepared_at=PREPARED_AT,
                )

            self.assertRegex(str(captured.exception), "symlink|reparse|real directory")
            self.assertEqual(list(real_parent.iterdir()), [])

    def test_prepare_rejects_an_in_checkout_target_outside_runtime(self) -> None:
        with tempfile.TemporaryDirectory(dir=EXTERNAL_TEMP_ROOT) as directory:
            project = Path(directory) / "checkout"
            project.mkdir()
            output = project / "archive-outside-runtime"
            with self.assertRaisesRegex(ValueError, "below runtime"):
                prepare_bootstrap_archive(
                    project_root=project,
                    output_root=output,
                    as_of=AS_OF,
                    prepared_at=PREPARED_AT,
                )
            self.assertFalse(output.exists())

    def test_verify_rejects_mutated_frozen_control_bytes(self) -> None:
        with tempfile.TemporaryDirectory(dir=EXTERNAL_TEMP_ROOT) as directory:
            archive = self._prepare(Path(directory))
            target = archive / "control" / "historical_sources.json"
            target.write_bytes(target.read_bytes() + b"\n")

            with self.assertRaisesRegex(
                ValueError,
                "canonical|changed|hash|strict JSON|does not bind",
            ):
                verify_bootstrap_archive(archive_root=archive)

    def test_verify_rejects_extra_raw_evidence_in_the_empty_scaffold(self) -> None:
        with tempfile.TemporaryDirectory(dir=EXTERNAL_TEMP_ROOT) as directory:
            archive = self._prepare(Path(directory))
            injected = archive / "raw" / "primary_official" / "injected.bin"
            injected.write_bytes(b"historical evidence is not admitted by contract 1.0")

            with self.assertRaisesRegex(ValueError, "inventory mismatch"):
                verify_bootstrap_archive(archive_root=archive)

    def test_verify_rejects_a_file_added_after_the_initial_snapshot(self) -> None:
        with tempfile.TemporaryDirectory(dir=EXTERNAL_TEMP_ROOT) as directory:
            archive = self._prepare(Path(directory))
            from kubo.bootstrap_archive import workspace as workspace_module

            original_snapshot = workspace_module.snapshot_regular_tree
            snapshot_calls = 0

            def snapshot_then_inject(*args: object, **kwargs: object):
                nonlocal snapshot_calls
                result = original_snapshot(*args, **kwargs)
                snapshot_calls += 1
                if snapshot_calls == 1:
                    (archive / "raw" / "primary_official" / "late.bin").write_bytes(
                        b"late evidence"
                    )
                return result

            with patch.object(
                workspace_module,
                "snapshot_regular_tree",
                side_effect=snapshot_then_inject,
            ):
                with self.assertRaisesRegex(ValueError, "changed during verification"):
                    verify_bootstrap_archive(archive_root=archive)

    def test_verify_rejects_existing_file_mutation_after_the_initial_snapshot(self) -> None:
        with tempfile.TemporaryDirectory(dir=EXTERNAL_TEMP_ROOT) as directory:
            archive = self._prepare(Path(directory))
            from kubo.bootstrap_archive import workspace as workspace_module

            original_snapshot = workspace_module.snapshot_regular_tree
            snapshot_calls = 0

            def snapshot_then_mutate(*args: object, **kwargs: object):
                nonlocal snapshot_calls
                result = original_snapshot(*args, **kwargs)
                snapshot_calls += 1
                if snapshot_calls == 1:
                    checklist = archive / "reports" / "COLLECTION_CHECKLIST.md"
                    checklist.write_bytes(checklist.read_bytes() + b"late mutation\n")
                return result

            with patch.object(
                workspace_module,
                "snapshot_regular_tree",
                side_effect=snapshot_then_mutate,
            ):
                with self.assertRaisesRegex(ValueError, "changed during verification"):
                    verify_bootstrap_archive(archive_root=archive)

    def test_verify_rejects_an_extra_empty_directory(self) -> None:
        with tempfile.TemporaryDirectory(dir=EXTERNAL_TEMP_ROOT) as directory:
            archive = self._prepare(Path(directory))
            (archive / "raw" / "primary_official" / "undeclared-empty").mkdir()

            with self.assertRaisesRegex(ValueError, "inventory|director"):
                verify_bootstrap_archive(archive_root=archive)

    def test_verify_rejects_symlinks_inside_the_archive(self) -> None:
        with tempfile.TemporaryDirectory(dir=EXTERNAL_TEMP_ROOT) as directory:
            parent = Path(directory)
            archive = self._prepare(parent)
            target = parent / "outside.bin"
            target.write_bytes(b"outside")
            link = archive / "raw" / "primary_archive" / "unsafe-link.bin"
            try:
                link.symlink_to(target)
            except (NotImplementedError, OSError) as exc:
                self.skipTest(f"symlink creation unavailable: {exc}")

            with self.assertRaisesRegex(ValueError, "symlink|reparse"):
                verify_bootstrap_archive(archive_root=archive)

    def test_verify_rejects_tampering_with_the_collection_checklist(self) -> None:
        with tempfile.TemporaryDirectory(dir=EXTERNAL_TEMP_ROOT) as directory:
            archive = self._prepare(Path(directory))
            checklist = archive / "reports" / "COLLECTION_CHECKLIST.md"
            checklist.write_text(
                "Collection and recommendations are now allowed.\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "checklist|inventory|changed|hash"):
                verify_bootstrap_archive(archive_root=archive)

    def test_naive_prepared_at_fails_before_any_output_is_published(self) -> None:
        with tempfile.TemporaryDirectory(dir=EXTERNAL_TEMP_ROOT) as directory:
            parent = Path(directory)
            output = parent / "archive"
            with self.assertRaisesRegex(ValueError, "timezone-aware"):
                prepare_bootstrap_archive(
                    project_root=ROOT,
                    output_root=output,
                    as_of=AS_OF,
                    prepared_at=datetime(2026, 8, 14, 18, 30),
                )
            self.assertFalse(output.exists())
            self.assertEqual(
                [path for path in parent.iterdir() if path.name.startswith(".archive.staging-")],
                [],
            )

    def test_future_as_of_fails_before_any_output_is_published(self) -> None:
        with tempfile.TemporaryDirectory(dir=EXTERNAL_TEMP_ROOT) as directory:
            parent = Path(directory)
            output = parent / "archive"
            with self.assertRaisesRegex(ValueError, "future in Asia/Kuwait"):
                prepare_bootstrap_archive(
                    project_root=ROOT,
                    output_root=output,
                    as_of=date(2026, 8, 15),
                    prepared_at=PREPARED_AT,
                )
            self.assertFalse(output.exists())
            self.assertEqual(
                [path for path in parent.iterdir() if path.name.startswith(".archive.staging-")],
                [],
            )

    def test_pre_1980_as_of_fails_before_any_output_is_published(self) -> None:
        with tempfile.TemporaryDirectory(dir=EXTERNAL_TEMP_ROOT) as directory:
            parent = Path(directory)
            output = parent / "archive"
            with self.assertRaisesRegex(ValueError, "before 1980-01-01"):
                prepare_bootstrap_archive(
                    project_root=ROOT,
                    output_root=output,
                    as_of=date(1979, 12, 31),
                    prepared_at=PREPARED_AT,
                )
            self.assertFalse(output.exists())
            self.assertEqual(
                [path for path in parent.iterdir() if path.name.startswith(".archive.staging-")],
                [],
            )

    def test_prepare_uses_the_wall_clock_kuwait_date_as_the_future_boundary(self) -> None:
        with tempfile.TemporaryDirectory(dir=EXTERNAL_TEMP_ROOT) as directory:
            from kubo.bootstrap_archive import workspace as workspace_module

            prepared_at = datetime(2026, 8, 14, 22, 0, tzinfo=timezone.utc)

            class FrozenDateTime(datetime):
                @classmethod
                def now(cls, tz: object | None = None):
                    if tz is None:
                        return prepared_at.replace(tzinfo=None)
                    return prepared_at.astimezone(tz)  # type: ignore[arg-type]

            archive = Path(directory) / "kuwait-next-day"
            with patch.object(workspace_module, "datetime", FrozenDateTime):
                prepare_bootstrap_archive(
                    project_root=ROOT,
                    output_root=archive,
                    as_of=date(2026, 8, 15),
                    prepared_at=prepared_at,
                )
                verification = verify_bootstrap_archive(archive_root=archive)
            self.assertEqual(verification["status"], "PASS_EMPTY_ARCHIVE_SCAFFOLD")
            descriptor = json.loads((archive / "bootstrap_archive.json").read_bytes())
            self.assertEqual(descriptor["as_of"], "2026-08-15")

    def test_future_prepared_at_fails_before_any_output_is_published(self) -> None:
        with tempfile.TemporaryDirectory(dir=EXTERNAL_TEMP_ROOT) as directory:
            output = Path(directory) / "future-archive"
            with self.assertRaisesRegex(ValueError, "prepared_at cannot be in the future"):
                prepare_bootstrap_archive(
                    project_root=ROOT,
                    output_root=output,
                    as_of=AS_OF,
                    prepared_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
                )
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
