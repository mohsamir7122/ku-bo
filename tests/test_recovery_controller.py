from __future__ import annotations

from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from kubo.recovery import build_incident, record_retry_attempt, load_recovery_policy
from scripts.recovery_controller import (
    CI_WORKFLOW_NAME,
    MISSED_EVENT_WATCHDOG_CRON,
    PIPELINE_WORKFLOW_NAME,
    RecoveryError,
    SCHEDULED_RECOVERY_CRON,
    _safe_write_json,
    _safe_zip_rows,
    run_github_controller,
    validate_controller_event,
    workflow_event_context,
)


ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)
CODE_SHA = "a" * 40


class FakeGitHubApi:
    def __init__(self) -> None:
        self.active_runs: list[dict[str, str]] = []
        self.rerun_ids: list[int] = []
        self.pipeline_dispatches: list[tuple[str, dict[str, str]]] = []
        self.issues: list[dict[str, object]] = []

    def active_pipeline_runs(self) -> list[dict[str, str]]:
        return list(self.active_runs)

    def rerun_failed_jobs(self, run_id: int) -> None:
        self.rerun_ids.append(run_id)

    def dispatch_pipeline(self, *, ref: str, inputs: dict[str, str]) -> None:
        self.pipeline_dispatches.append((ref, dict(inputs)))

    def list_recovery_issues(self) -> list[dict[str, object]]:
        return [dict(row) for row in self.issues]

    def create_issue(self, payload: dict[str, object]) -> dict[str, object]:
        row = {
            **payload,
            "number": len(self.issues) + 1,
            "updated_at": NOW.isoformat(),
        }
        self.issues.append(row)
        return dict(row)

    def update_issue(self, number: int, payload: dict[str, object]) -> dict[str, object]:
        for index, row in enumerate(self.issues):
            if row.get("number") == number:
                updated = {**row, **payload, "updated_at": NOW.isoformat()}
                self.issues[index] = updated
                return dict(updated)
        raise AssertionError("issue does not exist")


class RecoveryControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy, _ = load_recovery_policy(ROOT)

    def incident(
        self,
        error_class: str = "github_infrastructure",
        *,
        now: datetime = NOW,
        run_id: str = "42",
    ) -> dict[str, object]:
        return build_incident(
            ROOT,
            market="KUWAIT",
            stage="collection",
            error_class=error_class,
            component="kuwait_market_pipeline",
            failure_code="RUNNER_FAILURE",
            code_sha=CODE_SHA,
            failed_run_id=run_id,
            run_url=f"https://github.com/mohsamir7122/ku-bo/actions/runs/{run_id}",
            summary="sanitized runner failure",
            now=now,
        )

    def pipeline_context(
        self, *, attempt: int = 1, conclusion: str = "failure"
    ) -> dict[str, object]:
        return {
            "kind": "workflow_run",
            "workflow_name": PIPELINE_WORKFLOW_NAME,
            "conclusion": conclusion,
            "run_id": "42",
            "run_attempt": attempt,
            "head_sha": CODE_SHA,
        }

    def control(
        self,
        api: FakeGitHubApi,
        incident: dict[str, object],
        *,
        now: datetime = NOW,
        context: dict[str, object] | None = None,
        current_sha: str = CODE_SHA,
        changed_files: tuple[str, ...] = (),
        ci_passed: bool = False,
        smoke_passed: bool = False,
        secrets: bool = False,
    ) -> dict[str, object]:
        return run_github_controller(
            project_root=ROOT,
            api=api,
            now=now,
            default_ref="main",
            current_code_sha=current_sha,
            required_secrets_present=secrets,
            incidents=[incident],
            event_context=context or self.pipeline_context(),
            changed_files=changed_files,
            ci_passed=ci_passed,
            smoke_passed=smoke_passed,
        )

    def test_workflow_run_reruns_failed_jobs_immediately(self) -> None:
        api = FakeGitHubApi()
        result = self.control(api, self.incident())
        decision = result["decisions"][0]
        self.assertEqual(api.rerun_ids, [42])
        self.assertEqual(decision["action"], "DISPATCH_RETRY")
        self.assertEqual(decision["dispatch_method"], "RERUN_FAILED_JOBS")
        self.assertEqual(result["incidents"][0]["attempt_count"], 1)

    def test_duplicate_workflow_event_is_idempotently_suppressed(self) -> None:
        api = FakeGitHubApi()
        first = self.control(api, self.incident())
        api.rerun_ids.clear()
        duplicate = self.control(api, first["incidents"][0])
        self.assertEqual(api.rerun_ids, [])
        self.assertEqual(
            duplicate["decisions"][0]["action"],
            "SUPPRESS_DUPLICATE_WORKFLOW_EVENT",
        )

    def test_two_retry_cap_uses_trusted_workflow_run_attempt(self) -> None:
        api = FakeGitHubApi()
        first = self.control(api, self.incident())
        second = self.control(
            api,
            first["incidents"][0],
            now=NOW + timedelta(seconds=1),
            context=self.pipeline_context(attempt=2),
        )
        self.assertEqual(api.rerun_ids, [42, 42])
        self.assertEqual(second["incidents"][0]["attempt_count"], 2)
        self.assertEqual(second["incidents"][0]["status"], "EXHAUSTED")
        self.assertEqual(api.issues, [], "do not alert before the final retry finishes")

        third = self.control(
            api,
            second["incidents"][0],
            now=NOW + timedelta(seconds=2),
            context=self.pipeline_context(attempt=3),
        )
        self.assertEqual(api.rerun_ids, [42, 42])
        self.assertEqual(third["decisions"][0]["action"], "RETRY_EXHAUSTED")
        self.assertEqual(len(api.issues), 1)

    def test_watchdog_recovers_only_a_missed_event(self) -> None:
        incident = self.incident()
        fresh_api = FakeGitHubApi()
        fresh = self.control(
            fresh_api,
            incident,
            now=NOW + timedelta(seconds=299),
            context={"kind": "watchdog", "workflow_name": None},
        )
        self.assertEqual(fresh_api.rerun_ids, [])
        self.assertEqual(fresh["decisions"][0]["action"], "WATCHDOG_EVENT_NOT_MISSED")

        stale_api = FakeGitHubApi()
        stale = self.control(
            stale_api,
            incident,
            now=NOW + timedelta(seconds=300),
            context={"kind": "watchdog", "workflow_name": None},
        )
        self.assertEqual(stale_api.rerun_ids, [42])
        self.assertEqual(stale["decisions"][0]["action"], "DISPATCH_RETRY")

    def test_scheduled_recovery_is_bounded_and_does_not_wait_for_watchdog(self) -> None:
        context = workflow_event_context(
            "schedule",
            {"schedule": SCHEDULED_RECOVERY_CRON},
        )
        self.assertEqual(context["kind"], "scheduled_recovery")
        api = FakeGitHubApi()
        result = self.control(api, self.incident(), context=context)
        self.assertEqual(api.rerun_ids, [42])
        self.assertEqual(result["trigger_kind"], "scheduled_recovery")

    def test_schedule_identities_are_exactly_allowlisted(self) -> None:
        watchdog = workflow_event_context(
            "schedule",
            {"schedule": MISSED_EVENT_WATCHDOG_CRON},
        )
        self.assertEqual(watchdog["kind"], "watchdog")
        with self.assertRaisesRegex(RecoveryError, "not allowlisted"):
            workflow_event_context("schedule", {"schedule": "* * * * *"})

    def test_active_run_suppresses_retry(self) -> None:
        api = FakeGitHubApi()
        api.active_runs = [{"market": "KUWAIT", "status": "queued", "run_id": "42"}]
        result = self.control(api, self.incident())
        self.assertEqual(api.rerun_ids, [])
        self.assertEqual(result["decisions"][0]["action"], "SUPPRESS_ACTIVE_RUN")

    def test_missing_secret_is_probe_only_and_security_never_retries(self) -> None:
        missing_api = FakeGitHubApi()
        missing = self.control(missing_api, self.incident("missing_secret"))
        self.assertEqual(missing_api.rerun_ids, [])
        self.assertEqual(missing["decisions"][0]["action"], "HEALTH_PROBE_ONLY")

        security_api = FakeGitHubApi()
        security = self.control(security_api, self.incident("security"))
        self.assertEqual(security_api.rerun_ids, [])
        self.assertEqual(security["decisions"][0]["action"], "BLOCK_SECURITY")
        self.assertEqual(len(security_api.issues), 1)

    def test_validated_ci_fix_uses_resume_dispatch_not_failed_job_rerun(self) -> None:
        api = FakeGitHubApi()
        result = self.control(
            api,
            self.incident("deterministic_code"),
            context={
                "kind": "workflow_run",
                "workflow_name": CI_WORKFLOW_NAME,
                "conclusion": "success",
                "run_id": "84",
                "run_attempt": 1,
                "head_sha": "b" * 40,
            },
            current_sha="b" * 40,
            changed_files=("scripts/recovery_controller.py",),
            ci_passed=True,
            smoke_passed=True,
        )
        self.assertEqual(api.rerun_ids, [])
        self.assertEqual(len(api.pipeline_dispatches), 1)
        self.assertEqual(
            result["decisions"][0]["dispatch_method"],
            "WORKFLOW_DISPATCH_RESUME",
        )

    def test_workflow_event_context_rejects_unknown_or_incomplete_events(self) -> None:
        with self.assertRaises(RecoveryError):
            workflow_event_context(
                "workflow_run",
                {
                    "action": "completed",
                    "workflow_run": {
                        "name": "Untrusted",
                        "id": 1,
                        "run_attempt": 1,
                        "head_sha": CODE_SHA,
                        "conclusion": "failure",
                    },
                },
            )
        with self.assertRaises(RecoveryError):
            workflow_event_context(
                "workflow_run",
                {
                    "action": "requested",
                    "workflow_run": {
                        "name": PIPELINE_WORKFLOW_NAME,
                        "id": 1,
                        "run_attempt": 1,
                        "head_sha": CODE_SHA,
                        "conclusion": "failure",
                    },
                },
            )

    def test_repository_dispatch_is_exact_and_actor_allowlisted(self) -> None:
        valid = {
            "action": "market-recovery-request",
            "repository": {"full_name": "mohsamir7122/ku-bo"},
            "sender": {"login": "mohsamir7122"},
            "client_payload": {
                "action": "probe",
                "market": "KUWAIT",
                "incident_id": self.incident()["incident_id"],
                "force_probe": True,
            },
        }
        normalized = validate_controller_event(
            event_name="repository_dispatch",
            event=valid,
            actor="mohsamir7122",
            repository="mohsamir7122/ku-bo",
        )
        self.assertTrue(normalized["force_probe"])
        invalid = json.loads(json.dumps(valid))
        invalid["client_payload"]["unexpected"] = "bypass"
        with self.assertRaises(RecoveryError):
            validate_controller_event(
                event_name="repository_dispatch",
                event=invalid,
                actor="mohsamir7122",
                repository="mohsamir7122/ku-bo",
            )

    def test_workflow_run_from_untrusted_head_repository_is_rejected(self) -> None:
        event = {
            "action": "completed",
            "repository": {
                "full_name": "mohsamir7122/ku-bo",
                "default_branch": "main",
            },
            "workflow_run": {
                "name": PIPELINE_WORKFLOW_NAME,
                "id": 42,
                "run_attempt": 1,
                "head_sha": CODE_SHA,
                "head_branch": "main",
                "head_repository": {"full_name": "attacker/fork"},
                "event": "workflow_dispatch",
                "conclusion": "failure",
            },
        }
        with self.assertRaisesRegex(RecoveryError, "not trusted"):
            validate_controller_event(
                event_name="workflow_run",
                event=event,
                actor="github-actions[bot]",
                repository="mohsamir7122/ku-bo",
            )


class RecoveryControllerFilesystemTests(unittest.TestCase):
    def test_zip_path_traversal_is_rejected(self) -> None:
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("../recovery-incident.json", "{}")
        with self.assertRaises(RecoveryError):
            _safe_zip_rows(stream.getvalue())

    def test_zip_symlink_is_rejected(self) -> None:
        stream = io.BytesIO()
        info = zipfile.ZipInfo("recovery-incident.json")
        info.create_system = 3
        info.external_attr = 0o120777 << 16
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr(info, "target")
        with self.assertRaises(RecoveryError):
            _safe_zip_rows(stream.getvalue())

    def test_output_symlink_parent_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "target"
            target.mkdir()
            link = root / "link"
            try:
                link.symlink_to(target, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks are unavailable")
            with self.assertRaises(RecoveryError):
                _safe_write_json(link / "state.json", {"status": "blocked"})


if __name__ == "__main__":
    unittest.main()
