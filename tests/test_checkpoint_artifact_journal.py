from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import tempfile
import unittest
from unittest import mock

from jsonschema import Draft202012Validator, FormatChecker
import yaml

import kubo.checkpoint_artifact_journal as journal
from kubo.atomic_output import AtomicOutputError
from kubo.checkpoint_artifact_journal import (
    ArtifactJournalCanaryError,
    CANARY_STATUS,
    COORDINATOR_STATUS,
    MANIFEST_PATH,
    WORKFLOW_NAME,
    artifact_journal_manifest_sha256,
    create_generation_one,
    create_generation_two,
    validate_artifact_journal_bundle,
    validate_artifact_journal_chain,
)
from kubo.hashing import canonical_json_bytes


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "mohsamir7122/ku-bo"
TASK_BRANCH = "codex/ku-bo-readiness-live-canary-v1"
WORKFLOW_REF = (
    f"{REPOSITORY}/.github/workflows/{WORKFLOW_NAME}@refs/heads/{TASK_BRANCH}"
)
WORKFLOW_SHA = "c" * 40
RUN_ID = "33140000000"
RUN_ATTEMPT = 1
HEAD_SHA = "a" * 40
FIRST_AT = "2026-08-28T03:00:00Z"
SECOND_AT = "2026-08-28T03:01:00Z"


def _create_pair(root: Path) -> tuple[Path, Path]:
    first = root / "generation-1"
    second = root / "generation-2"
    create_generation_one(
        first,
        repository=REPOSITORY,
        workflow=WORKFLOW_NAME,
        workflow_ref=WORKFLOW_REF,
        workflow_sha=WORKFLOW_SHA,
        run_id=RUN_ID,
        run_attempt=RUN_ATTEMPT,
        head_sha=HEAD_SHA,
        now=FIRST_AT,
    )
    create_generation_two(
        first,
        second,
        repository=REPOSITORY,
        workflow=WORKFLOW_NAME,
        workflow_ref=WORKFLOW_REF,
        workflow_sha=WORKFLOW_SHA,
        run_id=RUN_ID,
        run_attempt=RUN_ATTEMPT,
        head_sha=HEAD_SHA,
        now=SECOND_AT,
    )
    return first, second


def _manifest(root: Path) -> dict[str, object]:
    return json.loads((root / MANIFEST_PATH).read_text(encoding="utf-8"))


def _rewrite_manifest(root: Path, mutate: object) -> None:
    row = _manifest(root)
    mutate(row)
    row["manifest_sha256"] = artifact_journal_manifest_sha256(row)
    (root / MANIFEST_PATH).write_bytes(canonical_json_bytes(row) + b"\n")


class ArtifactJournalCanaryTests(unittest.TestCase):
    def test_two_generation_cross_runner_contract_and_schema(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first, second = _create_pair(Path(directory))
            first_report = validate_artifact_journal_bundle(
                first,
                expected_repository=REPOSITORY,
                expected_workflow=WORKFLOW_NAME,
                expected_workflow_ref=WORKFLOW_REF,
                expected_workflow_sha=WORKFLOW_SHA,
                expected_run_id=RUN_ID,
                expected_run_attempt=RUN_ATTEMPT,
                expected_head_sha=HEAD_SHA,
            )
            second_report = validate_artifact_journal_bundle(second)
            chain = validate_artifact_journal_chain(
                first,
                second,
                expected_repository=REPOSITORY,
                expected_workflow=WORKFLOW_NAME,
                expected_workflow_ref=WORKFLOW_REF,
                expected_workflow_sha=WORKFLOW_SHA,
                expected_run_id=RUN_ID,
                expected_run_attempt=RUN_ATTEMPT,
                expected_head_sha=HEAD_SHA,
            )
            schema = json.loads(
                (ROOT / "schemas" / "checkpoint-artifact-journal-canary.schema.json")
                .read_text(encoding="utf-8")
            )
            Draft202012Validator.check_schema(schema)
            validator = Draft202012Validator(schema, format_checker=FormatChecker())
            validator.validate(_manifest(first))
            validator.validate(_manifest(second))

        self.assertEqual(first_report["status"], CANARY_STATUS)
        self.assertEqual(first_report["production_coordinator_status"], COORDINATOR_STATUS)
        self.assertEqual(first_report["generation"], 1)
        self.assertFalse(first_report["cas_rejection_verified"])
        self.assertFalse(first_report["fencing_rejection_verified"])
        self.assertEqual(second_report["generation"], 2)
        self.assertTrue(second_report["cas_rejection_verified"])
        self.assertTrue(second_report["fencing_rejection_verified"])
        self.assertEqual(chain["previous_generation"], 1)
        self.assertEqual(chain["current_generation"], 2)
        self.assertEqual(first_report["checkpoint_id"], second_report["checkpoint_id"])
        self.assertNotEqual(
            first_report["checkpoint_digest"], second_report["checkpoint_digest"]
        )
        self.assertFalse(
            chain["claim_boundaries"]["canary_resolves_blocked_checkpoint_store"]
        )

    def test_expected_workflow_context_rejects_independently_rehashed_tampering(self) -> None:
        cases = {
            "repository": "attacker/fork",
            "workflow": "other-workflow.yml",
            "workflow_ref": (
                f"{REPOSITORY}/.github/workflows/{WORKFLOW_NAME}@refs/pull/99/merge"
            ),
            "workflow_sha": "d" * 40,
            "run_id": "99999999999",
            "run_attempt": 2,
            "head_sha": "b" * 40,
        }
        for field, replacement in cases.items():
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                first = root / "generation-1"
                create_generation_one(
                    first,
                    repository=REPOSITORY,
                    workflow=WORKFLOW_NAME,
                    workflow_ref=WORKFLOW_REF,
                    workflow_sha=WORKFLOW_SHA,
                    run_id=RUN_ID,
                    run_attempt=RUN_ATTEMPT,
                    head_sha=HEAD_SHA,
                    now=FIRST_AT,
                )
                _rewrite_manifest(first, lambda row: row.__setitem__(field, replacement))
                with self.assertRaises(ArtifactJournalCanaryError):
                    validate_artifact_journal_bundle(
                        first,
                        expected_repository=REPOSITORY,
                        expected_workflow=WORKFLOW_NAME,
                        expected_workflow_ref=WORKFLOW_REF,
                        expected_workflow_sha=WORKFLOW_SHA,
                        expected_run_id=RUN_ID,
                        expected_run_attempt=RUN_ATTEMPT,
                        expected_head_sha=HEAD_SHA,
                    )

    def test_checkpoint_and_manifest_binding_tampering_fails_closed(self) -> None:
        mutations = (
            lambda row: row.__setitem__("generation", 2),
            lambda row: row.__setitem__("checkpoint_digest", "0" * 64),
            lambda row: row.__setitem__("checkpoint_sha256", "1" * 64),
            lambda row: row.__setitem__("checkpoint_id", "CP-" + "F" * 24),
            lambda row: row["claim_boundaries"].__setitem__(
                "canary_resolves_blocked_checkpoint_store", True
            ),
        )
        for index, mutation in enumerate(mutations):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as directory:
                first = Path(directory) / "generation-1"
                create_generation_one(
                    first,
                    repository=REPOSITORY,
                    workflow=WORKFLOW_NAME,
                    workflow_ref=WORKFLOW_REF,
                    workflow_sha=WORKFLOW_SHA,
                    run_id=RUN_ID,
                    run_attempt=RUN_ATTEMPT,
                    head_sha=HEAD_SHA,
                    now=FIRST_AT,
                )
                _rewrite_manifest(first, mutation)
                with self.assertRaises(ArtifactJournalCanaryError):
                    validate_artifact_journal_bundle(first)

    def test_unknown_duplicate_noncanonical_and_extra_files_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "generation-1"
            create_generation_one(
                first,
                repository=REPOSITORY,
                workflow=WORKFLOW_NAME,
                workflow_ref=WORKFLOW_REF,
                workflow_sha=WORKFLOW_SHA,
                run_id=RUN_ID,
                run_attempt=RUN_ATTEMPT,
                head_sha=HEAD_SHA,
                now=FIRST_AT,
            )
            row = _manifest(first)
            row["unknown"] = True
            (first / MANIFEST_PATH).write_bytes(canonical_json_bytes(row) + b"\n")
            with self.assertRaises(ArtifactJournalCanaryError):
                validate_artifact_journal_bundle(first)

        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "generation-1"
            create_generation_one(
                first,
                repository=REPOSITORY,
                workflow=WORKFLOW_NAME,
                workflow_ref=WORKFLOW_REF,
                workflow_sha=WORKFLOW_SHA,
                run_id=RUN_ID,
                run_attempt=RUN_ATTEMPT,
                head_sha=HEAD_SHA,
                now=FIRST_AT,
            )
            content = (first / MANIFEST_PATH).read_text(encoding="utf-8")
            duplicate = content.replace(
                '"schema_version":"1.0",',
                '"schema_version":"1.0","schema_version":"1.0",',
                1,
            )
            (first / MANIFEST_PATH).write_text(duplicate, encoding="utf-8")
            with self.assertRaisesRegex(ArtifactJournalCanaryError, "duplicate key"):
                validate_artifact_journal_bundle(first)

        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "generation-1"
            create_generation_one(
                first,
                repository=REPOSITORY,
                workflow=WORKFLOW_NAME,
                workflow_ref=WORKFLOW_REF,
                workflow_sha=WORKFLOW_SHA,
                run_id=RUN_ID,
                run_attempt=RUN_ATTEMPT,
                head_sha=HEAD_SHA,
                now=FIRST_AT,
            )
            row = _manifest(first)
            (first / MANIFEST_PATH).write_text(
                json.dumps(row, indent=2) + "\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(ArtifactJournalCanaryError, "not canonical"):
                validate_artifact_journal_bundle(first)

        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "generation-1"
            create_generation_one(
                first,
                repository=REPOSITORY,
                workflow=WORKFLOW_NAME,
                workflow_ref=WORKFLOW_REF,
                workflow_sha=WORKFLOW_SHA,
                run_id=RUN_ID,
                run_attempt=RUN_ATTEMPT,
                head_sha=HEAD_SHA,
                now=FIRST_AT,
            )
            (first / "unexpected.txt").write_text("not admitted", encoding="utf-8")
            with self.assertRaises(ArtifactJournalCanaryError):
                validate_artifact_journal_bundle(first)

    def test_checkpoint_mutation_and_symlink_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "generation-1"
            create_generation_one(
                first,
                repository=REPOSITORY,
                workflow=WORKFLOW_NAME,
                workflow_ref=WORKFLOW_REF,
                workflow_sha=WORKFLOW_SHA,
                run_id=RUN_ID,
                run_attempt=RUN_ATTEMPT,
                head_sha=HEAD_SHA,
                now=FIRST_AT,
            )
            checkpoint = next((first / "checkpoint-store").glob("*.checkpoint.json"))
            checkpoint.write_bytes(checkpoint.read_bytes() + b" ")
            _rewrite_manifest(
                first,
                lambda row: row.__setitem__(
                    "checkpoint_sha256",
                    __import__("hashlib").sha256(checkpoint.read_bytes()).hexdigest(),
                ),
            )
            with self.assertRaises(ArtifactJournalCanaryError):
                validate_artifact_journal_bundle(first)

        if hasattr(Path, "symlink_to"):
            with tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                first = base / "generation-1"
                create_generation_one(
                    first,
                    repository=REPOSITORY,
                    workflow=WORKFLOW_NAME,
                    workflow_ref=WORKFLOW_REF,
                    workflow_sha=WORKFLOW_SHA,
                    run_id=RUN_ID,
                    run_attempt=RUN_ATTEMPT,
                    head_sha=HEAD_SHA,
                    now=FIRST_AT,
                )
                target = base / "outside.json"
                target.write_text("{}", encoding="utf-8")
                (first / "linked.json").symlink_to(target)
                with self.assertRaises(ArtifactJournalCanaryError):
                    validate_artifact_journal_bundle(first)

    def test_generation_chain_rejects_fork_and_cross_context(self) -> None:
        for field, replacement in (
            ("previous_manifest_sha256", "f" * 64),
            ("repository", "other/project"),
        ):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                first, second = _create_pair(root)
                fork = root / "fork"
                shutil.copytree(second, fork)
                _rewrite_manifest(fork, lambda row: row.__setitem__(field, replacement))
                with self.assertRaises(ArtifactJournalCanaryError):
                    validate_artifact_journal_chain(first, fork)

    def test_manifest_context_cannot_be_rebound_away_from_checkpoint_owner(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first, second = _create_pair(Path(directory))
            for root in (first, second):
                _rewrite_manifest(
                    root,
                    lambda row: (
                        row.__setitem__("run_id", "99999999999"),
                        row.__setitem__("run_attempt", 2),
                    ),
                )
                with self.subTest(generation=_manifest(root)["generation"]):
                    with self.assertRaisesRegex(
                        ArtifactJournalCanaryError, "checkpoint owner differs"
                    ):
                        validate_artifact_journal_bundle(root)

    def test_invalid_staging_and_overlapping_roots_never_publish(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            rejected = base / "rejected-generation-1"
            original_manifest = journal._manifest

            def invalid_manifest(**kwargs: object) -> dict[str, object]:
                row = original_manifest(**kwargs)
                row["status"] = "FORGED_READY"
                row["manifest_sha256"] = artifact_journal_manifest_sha256(row)
                return row

            with mock.patch.object(journal, "_manifest", side_effect=invalid_manifest):
                with self.assertRaises(AtomicOutputError):
                    create_generation_one(
                        rejected,
                        repository=REPOSITORY,
                        workflow=WORKFLOW_NAME,
                        workflow_ref=WORKFLOW_REF,
                        workflow_sha=WORKFLOW_SHA,
                        run_id=RUN_ID,
                        run_attempt=RUN_ATTEMPT,
                        head_sha=HEAD_SHA,
                        now=FIRST_AT,
                    )
            self.assertFalse(rejected.exists())

            first = base / "generation-1"
            create_generation_one(
                first,
                repository=REPOSITORY,
                workflow=WORKFLOW_NAME,
                workflow_ref=WORKFLOW_REF,
                workflow_sha=WORKFLOW_SHA,
                run_id=RUN_ID,
                run_attempt=RUN_ATTEMPT,
                head_sha=HEAD_SHA,
                now=FIRST_AT,
            )
            nested = first / "nested-generation-2"
            with self.assertRaisesRegex(
                ArtifactJournalCanaryError, "roots must be disjoint"
            ):
                create_generation_two(
                    first,
                    nested,
                    repository=REPOSITORY,
                    workflow=WORKFLOW_NAME,
                    workflow_ref=WORKFLOW_REF,
                    workflow_sha=WORKFLOW_SHA,
                    run_id=RUN_ID,
                    run_attempt=RUN_ATTEMPT,
                    head_sha=HEAD_SHA,
                    now=SECOND_AT,
                )
            self.assertFalse(nested.exists())
            validate_artifact_journal_bundle(first)


class ArtifactJournalCanaryWorkflowTests(unittest.TestCase):
    def test_workflow_is_one_shot_two_runner_and_explicitly_nonproduction(self) -> None:
        path = (
            ROOT
            / ".github"
            / "workflows"
            / "checkpoint-artifact-journal-canary.yml"
        )
        text = path.read_text(encoding="utf-8")
        workflow = yaml.load(text, Loader=yaml.BaseLoader)
        self.assertEqual(set(workflow["on"]), {"workflow_dispatch", "pull_request"})
        self.assertEqual(
            workflow["on"]["pull_request"],
            {"branches": ["main"], "types": ["opened"]},
        )
        self.assertEqual(workflow["permissions"], {"contents": "read"})
        jobs = workflow["jobs"]
        self.assertEqual(set(jobs), {"generation_1_runner", "generation_2_runner"})
        self.assertEqual(jobs["generation_1_runner"]["runs-on"], "ubuntu-latest")
        self.assertEqual(jobs["generation_2_runner"]["runs-on"], "ubuntu-latest")
        self.assertEqual(
            jobs["generation_2_runner"]["needs"], "generation_1_runner"
        )
        self.assertNotIn("schedule:", text)
        self.assertNotIn("push:", text)
        self.assertEqual(text.count("CANARY_ONLY"), 2)
        self.assertGreaterEqual(text.count("NOT_PRODUCTION_COORDINATOR"), 2)
        self.assertIn("create-generation-1", text)
        self.assertIn("create-generation-2", text)
        self.assertIn("validate-chain", text)
        self.assertIn("actions/download-artifact@", text)
        self.assertEqual(text.count("actions/upload-artifact@"), 2)
        self.assertEqual(
            text.count(
                "HEAD_SHA: ${{ github.event.pull_request.head.sha || github.sha }}"
            ),
            2,
        )
        self.assertEqual(
            text.count(
                "ref: ${{ github.event.pull_request.head.sha || github.sha }}"
            ),
            2,
        )
        self.assertEqual(text.count("WORKFLOW_REF: ${{ github.workflow_ref }}"), 2)
        self.assertEqual(text.count("WORKFLOW_SHA: ${{ github.workflow_sha }}"), 2)
        self.assertEqual(text.count("--workflow-ref \"$WORKFLOW_REF\""), 4)
        self.assertEqual(text.count("--workflow-sha \"$WORKFLOW_SHA\""), 4)
        self.assertEqual(text.count("mkdir -p runtime"), 2)
        self.assertNotIn("HEAD_SHA: ${{ github.sha }}", text)
        self.assertNotIn("execution-priority-policy", text)
        self.assertNotIn("recovery-success", text)

    def test_job_guards_allow_only_the_exact_same_repository_task_branch(self) -> None:
        path = (
            ROOT
            / ".github"
            / "workflows"
            / "checkpoint-artifact-journal-canary.yml"
        )
        workflow = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
        expected_branch = "codex/ku-bo-readiness-live-canary-v1"
        expected_guard = """${{
  (github.event_name == 'workflow_dispatch' &&
    github.ref == 'refs/heads/{branch}') ||
  (github.event_name == 'pull_request' &&
    github.event.action == 'opened' &&
    github.base_ref == 'main' &&
    github.head_ref == '{branch}' &&
    github.event.pull_request.head.repo.full_name == github.repository)
}}""".replace("{branch}", expected_branch)
        guards = []
        for job_name in ("generation_1_runner", "generation_2_runner"):
            with self.subTest(job=job_name):
                guard = workflow["jobs"][job_name]["if"]
                self.assertEqual(guard, expected_guard)
                guards.append(guard)
        self.assertEqual(guards[0], guards[1])

    def test_every_external_action_is_pinned_to_a_full_sha(self) -> None:
        path = (
            ROOT
            / ".github"
            / "workflows"
            / "checkpoint-artifact-journal-canary.yml"
        )
        matcher = re.compile(
            r"^\s*(?:-\s*)?uses:\s*[^\s@]+@[0-9a-f]{40}(?:\s+#.*)?$"
        )
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if "uses:" in line:
                with self.subTest(line=line_number):
                    self.assertRegex(line, matcher)


if __name__ == "__main__":
    unittest.main()
