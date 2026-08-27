from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest

from scripts.validate_private_predecessor_migration_control import (
    CONTROL,
    EXECPLAN,
    MANIFEST,
    ORIENTATION,
    PARITY,
    TASK,
    MigrationControlError,
    validate,
)


ROOT = Path(__file__).resolve().parents[1]


class PrivatePredecessorMigrationControlTests(unittest.TestCase):
    def test_locked_preparation_package_passes_without_completion_claim(self) -> None:
        report = validate(ROOT)
        self.assertEqual(report["status"], "PASS_PREPARATION_CONTROL")
        self.assertEqual(report["migration_id"], "KU-BO-MIG-001")
        self.assertEqual(report["opaque_seed_capability_count"], 14)
        self.assertFalse(report["migration_task_active"])
        self.assertFalse(report["private_source_repository_read_allowed"])
        self.assertTrue(
            report["migration_contract_private_source_repository_read_allowed"]
        )
        self.assertFalse(report["private_runtime_data_access_allowed"])
        self.assertFalse(report["completion_claim_allowed"])
        self.assertFalse(report["claim_boundaries"]["validator_proves_source_inventory"])
        self.assertFalse(report["claim_boundaries"]["validator_proves_migration_complete"])
        self.assertFalse(report["claim_boundaries"]["validator_authorizes_merge"])

    def test_reactivated_migration_requires_the_narrow_read_marker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._copy_control(root)
            task_path = root / TASK
            task_text = task_path.read_text(encoding="utf-8").replace(
                "TASK_ID: KU-BO-2026-08-27-DAY1",
                "TASK_ID: KU-BO-MIG-001",
                1,
            )
            task_path.write_text(task_text, encoding="utf-8")
            with self.assertRaisesRegex(
                MigrationControlError,
                "CURRENT_TASK.PRIVATE_SOURCE_REPOSITORY_READ_ALLOWED",
            ):
                validate(root)

            task_path.write_text(
                task_text.replace(
                    "PRIVATE_SOURCE_REPOSITORY_READ_ALLOWED: NO",
                    "PRIVATE_SOURCE_REPOSITORY_READ_ALLOWED: YES",
                    1,
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                MigrationControlError,
                "CURRENT_TASK.CONTROL_BASE_BRANCH",
            ):
                validate(root)

            migration_task_text = task_path.read_text(encoding="utf-8")
            replacements = {
                "CONTROL_BASE_BRANCH: main": (
                    "CONTROL_BASE_BRANCH: agent/ku-bo-016-codex-live-bootstrap"
                ),
                "CONTROL_BASE_SHA: 93e4cab09915a4a4b58455d3cc45eb48be4bd499": (
                    "CONTROL_BASE_SHA: 6e9ab870e727494d5eb9e1ec9fa98829d6391d68"
                ),
                "EXPECTED_NEW_BRANCH: codex/kuwait-market-ai-day1-v1": (
                    "EXPECTED_NEW_BRANCH: agent/private-predecessor-capability-migration-v1"
                ),
                "EXPECTED_PR_BASE: main": (
                    "EXPECTED_PR_BASE: agent/ku-bo-016-codex-live-bootstrap"
                ),
            }
            for current, expected in replacements.items():
                migration_task_text = migration_task_text.replace(current, expected, 1)
            task_path.write_text(migration_task_text, encoding="utf-8")
            report = validate(root)
            self.assertTrue(report["migration_task_active"])
            self.assertTrue(report["private_source_repository_read_allowed"])

    def test_permission_markers_in_prose_cannot_override_inactive_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._copy_control(root)
            task_path = root / TASK
            task_text = task_path.read_text(encoding="utf-8").replace(
                "PRIVATE_SOURCE_REPOSITORY_READ_ALLOWED: NO",
                "PRIVATE_SOURCE_REPOSITORY_READ_ALLOWED: YES",
                1,
            )
            task_path.write_text(
                task_text
                + "\nHistorical prose: PRIVATE_SOURCE_REPOSITORY_READ_ALLOWED: NO\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                MigrationControlError,
                "CURRENT_TASK.PRIVATE_SOURCE_REPOSITORY_READ_ALLOWED",
            ):
                validate(root)

    def test_permission_markers_in_prose_cannot_override_active_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._copy_control(root)
            task_path = root / TASK
            task_text = task_path.read_text(encoding="utf-8").replace(
                "TASK_ID: KU-BO-2026-08-27-DAY1",
                "TASK_ID: KU-BO-MIG-001",
                1,
            )
            task_path.write_text(
                task_text
                + "\nHistorical prose: PRIVATE_SOURCE_REPOSITORY_READ_ALLOWED: YES\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                MigrationControlError,
                "CURRENT_TASK.PRIVATE_SOURCE_REPOSITORY_READ_ALLOWED",
            ):
                validate(root)

    def test_duplicate_task_metadata_keys_are_rejected(self) -> None:
        for key_line in (
            "TASK_ID: KU-BO-2026-08-27-DAY1",
            "PRIVATE_SOURCE_REPOSITORY_READ_ALLOWED: NO",
        ):
            with self.subTest(key_line=key_line), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self._copy_control(root)
                task_path = root / TASK
                task_text = task_path.read_text(encoding="utf-8").replace(
                    key_line,
                    f"{key_line}\n{key_line}",
                    1,
                )
                task_path.write_text(task_text, encoding="utf-8")
                with self.assertRaisesRegex(MigrationControlError, "duplicate key"):
                    validate(root)

    def _copy_control(self, destination: Path) -> None:
        for relative in (CONTROL, MANIFEST, PARITY, ORIENTATION, TASK, EXECPLAN):
            source = ROOT / relative
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

    @staticmethod
    def _load(path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _write(path: Path, payload: dict) -> None:
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _mutate_and_validate(self, relative: Path, mutator) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._copy_control(root)
            path = root / relative
            payload = self._load(path)
            mutator(payload)
            self._write(path, payload)
            validate(root)

    def test_merge_permission_cannot_be_enabled(self) -> None:
        with self.assertRaisesRegex(MigrationControlError, "permissions"):
            self._mutate_and_validate(
                CONTROL,
                lambda payload: payload["permissions"].update(merge_allowed=True),
            )

    def test_source_repository_write_cannot_be_enabled(self) -> None:
        with self.assertRaisesRegex(MigrationControlError, "source.write_allowed"):
            self._mutate_and_validate(
                CONTROL,
                lambda payload: payload["source"].update(write_allowed=True),
            )

    def test_authorized_private_source_read_cannot_be_silently_removed(self) -> None:
        with self.assertRaisesRegex(MigrationControlError, "authorized_read_scope"):
            self._mutate_and_validate(
                CONTROL,
                lambda payload: payload["authorized_read_scope"].update(
                    private_source_repository_read_allowed=False
                ),
            )

    def test_private_runtime_data_access_cannot_be_enabled(self) -> None:
        with self.assertRaisesRegex(MigrationControlError, "authorized_read_scope"):
            self._mutate_and_validate(
                CONTROL,
                lambda payload: payload["authorized_read_scope"].update(
                    runtime_private_data_read_allowed=True
                ),
            )

    def test_private_repository_locator_field_is_rejected(self) -> None:
        with self.assertRaisesRegex(MigrationControlError, "locator-bearing"):
            self._mutate_and_validate(
                CONTROL,
                lambda payload: payload["source"].update(
                    repository="private-owner/private-repository"
                ),
            )

    def test_private_git_oid_in_public_manifest_is_rejected(self) -> None:
        with self.assertRaisesRegex(MigrationControlError, "private Git OIDs"):
            self._mutate_and_validate(
                MANIFEST,
                lambda payload: payload.update(private_commit_oid="a" * 40),
            )

    def test_private_url_in_orientation_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._copy_control(root)
            path = root / ORIENTATION
            path.write_text(
                path.read_text(encoding="utf-8")
                + "\nhttps://github.com/private-owner/private-repository\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(MigrationControlError, "private locator"):
                validate(root)

    def test_manifest_cannot_claim_completion(self) -> None:
        with self.assertRaisesRegex(MigrationControlError, "cannot claim completion"):
            self._mutate_and_validate(
                MANIFEST,
                lambda payload: payload.update(public_summary_status="COMPLETE"),
            )

    def test_manifest_completion_flag_cannot_be_enabled(self) -> None:
        with self.assertRaisesRegex(MigrationControlError, "completion_claim_allowed"):
            self._mutate_and_validate(
                MANIFEST,
                lambda payload: payload.update(completion_claim_allowed=True),
            )

    def test_parity_cannot_claim_completion(self) -> None:
        with self.assertRaisesRegex(MigrationControlError, "cannot claim completion"):
            self._mutate_and_validate(
                PARITY,
                lambda payload: payload.update(denominator_status="COMPLETE"),
            )

    def test_live_operational_status_is_rejected(self) -> None:
        with self.assertRaisesRegex(MigrationControlError, "unsafe runtime status"):
            self._mutate_and_validate(
                PARITY,
                lambda payload: payload["capabilities"][0].update(
                    runtime_capability_status="LIVE_OPERATIONAL"
                ),
            )

    def test_seed_capability_cannot_disappear(self) -> None:
        with self.assertRaisesRegex(MigrationControlError, "seed capabilities"):
            self._mutate_and_validate(
                PARITY,
                lambda payload: payload["capabilities"].pop(),
            )

    def test_source_path_cannot_be_added_to_capability_row(self) -> None:
        with self.assertRaisesRegex(MigrationControlError, "locator-bearing"):
            self._mutate_and_validate(
                PARITY,
                lambda payload: payload["capabilities"][0].update(
                    source_path="private/path/to/skill"
                ),
            )


if __name__ == "__main__":
    unittest.main()
