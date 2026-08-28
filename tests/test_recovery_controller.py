from __future__ import annotations

from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from kubo.recovery import build_incident, record_retry_attempt, load_recovery_policy
from scripts.recovery_controller import (
    CI_WORKFLOW_NAME,
    CONTROLLER_WORKFLOW_PATH,
    MISSED_EVENT_WATCHDOG_CRON,
    PIPELINE_WORKFLOW_PATH,
    PIPELINE_WORKFLOW_NAME,
    RecoveryError,
    SCHEDULED_RECOVERY_CRON,
    _artifact_records,
    _safe_write_json,
    _safe_zip_rows,
    _trusted_artifact_origin,
    _validate_success_receipt,
    build_success_receipt,
    discover_recovery_records,
    main as recovery_main,
    resolve_rerun_success_context,
    run_github_controller,
    validate_controller_event,
    validate_github_event,
    workflow_event_context,
)


ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)
CODE_SHA = "a" * 40


class FakeGitHubApi:
    def __init__(self) -> None:
        self.repository = "mohsamir7122/ku-bo"
        self.active_runs: list[dict[str, str]] = []
        self.rerun_ids: list[int] = []
        self.pipeline_dispatches: list[tuple[str, dict[str, str]]] = []
        self.issues: list[dict[str, object]] = []
        self.workflow_runs: dict[int, dict[str, object]] = {}
        self.artifacts: list[dict[str, object]] = []
        self.artifact_bytes: dict[int, bytes] = {}

    def active_pipeline_runs(self) -> list[dict[str, str]]:
        return list(self.active_runs)

    def workflow_run(self, run_id: int) -> dict[str, object]:
        return dict(self.workflow_runs[run_id])

    def list_artifacts(self) -> list[dict[str, object]]:
        return [dict(row) for row in self.artifacts]

    def download_artifact(self, artifact_id: int) -> bytes:
        return self.artifact_bytes[artifact_id]

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
        successes: tuple[dict[str, object], ...] = (),
    ) -> dict[str, object]:
        return run_github_controller(
            project_root=ROOT,
            api=api,
            now=now,
            default_ref="main",
            current_code_sha=current_sha,
            required_secrets_present=secrets,
            incidents=[incident],
            successes=successes,
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

    def test_one_failed_run_cannot_dispatch_multiple_retries(self) -> None:
        api = FakeGitHubApi()
        first = self.incident()
        second = build_incident(
            ROOT,
            market="KUWAIT",
            stage="validation",
            error_class="github_infrastructure",
            component="second_retriable_component",
            failure_code="SECOND_RUNNER_FAILURE",
            code_sha=CODE_SHA,
            failed_run_id="42",
            run_url="https://github.com/mohsamir7122/ku-bo/actions/runs/42",
            summary="second sanitized runner failure",
            now=NOW,
        )
        with self.assertRaisesRegex(RecoveryError, "ambiguous retriable incidents"):
            run_github_controller(
                project_root=ROOT,
                api=api,
                now=NOW,
                default_ref="main",
                current_code_sha=CODE_SHA,
                required_secrets_present=False,
                incidents=[first, second],
                event_context=self.pipeline_context(),
            )
        self.assertEqual(api.rerun_ids, [])
        self.assertEqual(api.pipeline_dispatches, [])

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

    def test_failed_job_rerun_success_resolves_from_persisted_incident_key(self) -> None:
        api = FakeGitHubApi()
        first = self.control(api, self.incident())
        retry_state = first["incidents"][0]
        context = resolve_rerun_success_context(
            [retry_state],
            project_root=ROOT,
            run_id="42",
            run_attempt=2,
            code_sha=CODE_SHA,
        )
        self.assertEqual(context["incident_id"], retry_state["incident_id"])
        self.assertEqual(context["incident_key"], retry_state["idempotency_key"])
        self.assertEqual(context["attempt_count"], 1)

        receipt = build_success_receipt(
            incident_id=context["incident_id"],
            incident_key=context["incident_key"],
            completed_at=NOW + timedelta(seconds=1),
            repository=api.repository,
            workflow_path=PIPELINE_WORKFLOW_PATH,
            run_id="42",
            run_attempt=2,
            run_url=f"https://github.com/{api.repository}/actions/runs/42",
            code_sha=CODE_SHA,
        )
        resolved = self.control(
            api,
            retry_state,
            now=NOW + timedelta(seconds=1),
            context=self.pipeline_context(attempt=2, conclusion="success"),
            successes=(receipt,),
        )
        self.assertEqual(
            resolved["decisions"][0]["action"],
            "RESOLVED_FROM_SUCCESS_RECEIPT",
        )
        self.assertEqual(resolved["incidents"][0]["status"], "RESOLVED")

    def test_rerun_success_context_rejects_ambiguous_or_unadvanced_state(self) -> None:
        initial = self.incident()
        with self.assertRaisesRegex(RecoveryError, "exactly one trusted"):
            resolve_rerun_success_context(
                [initial],
                project_root=ROOT,
                run_id="42",
                run_attempt=2,
                code_sha=CODE_SHA,
            )
        policy = load_recovery_policy(ROOT)[0]
        advanced = record_retry_attempt(initial, now=NOW, policy=policy)
        second = build_incident(
            ROOT,
            market="KUWAIT",
            stage="collection",
            error_class="transient_network",
            component="alternate_component",
            failure_code="NETWORK_TIMEOUT",
            code_sha=CODE_SHA,
            failed_run_id="42",
            summary="alternate transient",
            now=NOW,
        )
        second = record_retry_attempt(second, now=NOW, policy=policy)
        with self.assertRaisesRegex(RecoveryError, "exactly one trusted"):
            resolve_rerun_success_context(
                [advanced, second],
                project_root=ROOT,
                run_id="42",
                run_attempt=2,
                code_sha=CODE_SHA,
            )

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

    def test_non_default_ci_event_is_ignored_without_becoming_a_failure(self) -> None:
        event = {
            "action": "completed",
            "repository": {
                "full_name": "mohsamir7122/ku-bo",
                "default_branch": "main",
            },
            "workflow_run": {
                "name": CI_WORKFLOW_NAME,
                "id": 42,
                "run_attempt": 1,
                "head_sha": CODE_SHA,
                "head_branch": "feature/test",
                "head_repository": {"full_name": "mohsamir7122/ku-bo"},
                "event": "pull_request",
                "conclusion": "success",
            },
        }
        normalized = validate_controller_event(
            event_name="workflow_run",
            event=event,
            actor="github-actions[bot]",
            repository="mohsamir7122/ku-bo",
        )
        self.assertEqual(normalized["kind"], "ignored_ci")
        self.assertEqual(normalized["skip_reason"], "NON_DEFAULT_OR_NON_PUSH_CI")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            event_path = root / "event.json"
            output_path = root / "report.json"
            event_path.write_text(json.dumps(event), encoding="utf-8")
            with redirect_stdout(io.StringIO()):
                code = recovery_main(
                    [
                        "--project-root",
                        str(ROOT),
                        "github-control",
                        "--repository",
                        "mohsamir7122/ku-bo",
                        "--default-ref",
                        "main",
                        "--current-code-sha",
                        CODE_SHA,
                        "--event-name",
                        "workflow_run",
                        "--event-path",
                        str(event_path),
                        "--actor",
                        "github-actions[bot]",
                        "--required-secrets-present",
                        "false",
                        "--output",
                        str(output_path),
                        "--state-output-root",
                        str(root / "state"),
                    ]
                )
            report = json.loads(output_path.read_text(encoding="utf-8"))
        self.assertEqual(code, 0)
        self.assertEqual(report["status"], "SKIP_NON_DEFAULT_CI")

    def test_recovery_dispatch_requires_exact_incident_key(self) -> None:
        incident = self.incident()
        valid = {
            "inputs": {
                "mode": "resume",
                "incident_id": incident["incident_id"],
                "incident_key": incident["idempotency_key"],
                "checkpoint": "checkpoint-1",
                "slot_id": "main_1500",
            }
        }
        normalized = validate_github_event(
            event_name="workflow_dispatch",
            event=valid,
            actor="mohsamir7122",
            repository="mohsamir7122/ku-bo",
        )
        self.assertEqual(normalized["incident_key"], incident["idempotency_key"])
        invalid = json.loads(json.dumps(valid))
        invalid["inputs"]["incident_key"] = ""
        with self.assertRaisesRegex(RecoveryError, "require a valid incident_key"):
            validate_github_event(
                event_name="workflow_dispatch",
                event=invalid,
                actor="mohsamir7122",
                repository="mohsamir7122/ku-bo",
            )

    def test_success_resolution_requires_current_incident_state_key_and_time(self) -> None:
        incident = self.incident("permission_required")
        api = FakeGitHubApi()
        exact = build_success_receipt(
            incident_id=incident["incident_id"],
            incident_key=incident["idempotency_key"],
            completed_at=NOW,
            repository=api.repository,
            workflow_path=PIPELINE_WORKFLOW_PATH,
            run_id="84",
            run_attempt=1,
            run_url=f"https://github.com/{api.repository}/actions/runs/84",
            code_sha="b" * 40,
        )
        resolved = self.control(api, incident, context={"kind": "manual", "workflow_name": None}, successes=(exact,))
        self.assertEqual(resolved["decisions"][0]["action"], "RESOLVED_FROM_SUCCESS_RECEIPT")

        stale = {**exact, "completed_at": (NOW - timedelta(seconds=1)).isoformat()}
        not_resolved = self.control(
            FakeGitHubApi(),
            incident,
            context={"kind": "manual", "workflow_name": None},
            successes=(stale,),
        )
        self.assertEqual(not_resolved["decisions"][0]["action"], "NO_RETRY_BLOCKED")

        wrong_key = {**exact, "incident_idempotency_key": "f" * 64}
        not_resolved = self.control(
            FakeGitHubApi(),
            incident,
            context={"kind": "manual", "workflow_name": None},
            successes=(wrong_key,),
        )
        self.assertEqual(not_resolved["decisions"][0]["action"], "NO_RETRY_BLOCKED")

    def test_newest_success_receipt_wins_independent_of_input_order(self) -> None:
        incident = self.incident("permission_required")
        api = FakeGitHubApi()

        def receipt(completed_at: datetime, run_id: str) -> dict[str, object]:
            return build_success_receipt(
                incident_id=incident["incident_id"],
                incident_key=incident["idempotency_key"],
                completed_at=completed_at,
                repository=api.repository,
                workflow_path=PIPELINE_WORKFLOW_PATH,
                run_id=run_id,
                run_attempt=1,
                run_url=f"https://github.com/{api.repository}/actions/runs/{run_id}",
                code_sha=CODE_SHA,
            )

        older = receipt(NOW - timedelta(seconds=1), "83")
        newer = receipt(NOW + timedelta(seconds=1), "84")
        for successes in ((newer, older), (older, newer)):
            with self.subTest(order=[row["run_id"] for row in successes]):
                result = self.control(
                    FakeGitHubApi(),
                    incident,
                    now=NOW + timedelta(seconds=2),
                    context={"kind": "manual", "workflow_name": None},
                    successes=successes,
                )
                self.assertEqual(
                    result["decisions"][0]["action"],
                    "RESOLVED_FROM_SUCCESS_RECEIPT",
                )

    def test_artifact_origin_binds_workflow_repository_branch_run_and_sha(self) -> None:
        api = FakeGitHubApi()
        api.workflow_runs[84] = {
            "id": 84,
            "run_attempt": 2,
            "status": "completed",
            "conclusion": "success",
            "path": f"{PIPELINE_WORKFLOW_PATH}@refs/heads/main",
            "head_branch": "main",
            "head_sha": "b" * 40,
            "repository": {"id": 1, "full_name": api.repository},
            "head_repository": {"id": 1, "full_name": api.repository},
            "html_url": f"https://github.com/{api.repository}/actions/runs/84",
            "run_started_at": "2026-08-28T11:59:00Z",
            "updated_at": "2026-08-28T12:01:00Z",
        }
        artifact = {
            "id": 7,
            "name": "recovery-success-84-2",
            "expired": False,
            "digest": "sha256:" + "c" * 64,
            "workflow_run": {
                "id": 84,
                "repository_id": 1,
                "head_repository_id": 1,
                "head_branch": "main",
                "head_sha": "b" * 40,
            },
        }
        origin = _trusted_artifact_origin(api, artifact, default_ref="main")
        self.assertIsNotNone(origin)
        self.assertEqual(origin["workflow_path"], PIPELINE_WORKFLOW_PATH)

        api.workflow_runs[84]["head_branch"] = "feature/forged"
        self.assertIsNone(_trusted_artifact_origin(api, artifact, default_ref="main"))

    def test_success_receipt_rejects_repository_or_run_origin_mismatch(self) -> None:
        origin = {
            "repository": "mohsamir7122/ku-bo",
            "workflow_path": PIPELINE_WORKFLOW_PATH,
            "run_id": 84,
            "run_attempt": 1,
            "run_url": "https://github.com/mohsamir7122/ku-bo/actions/runs/84",
            "head_sha": "b" * 40,
            "run_started_at": "2026-08-27T11:59:00Z",
            "completed_at": "2026-08-27T12:01:00Z",
        }
        receipt = build_success_receipt(
            incident_id=self.incident()["incident_id"],
            incident_key=self.incident()["idempotency_key"],
            completed_at=NOW,
            repository=origin["repository"],
            workflow_path=PIPELINE_WORKFLOW_PATH,
            run_id="84",
            run_attempt=1,
            run_url=origin["run_url"],
            code_sha=origin["head_sha"],
        )
        self.assertEqual(_validate_success_receipt(receipt, origin=origin), receipt)
        with self.assertRaisesRegex(RecoveryError, "repository differs"):
            _validate_success_receipt(
                {**receipt, "repository": "attacker/other"}, origin=origin
            )

    def test_success_member_must_use_exact_archive_path(self) -> None:
        origin = {
            "kind": "recovery-success",
            "repository": "mohsamir7122/ku-bo",
            "workflow_path": PIPELINE_WORKFLOW_PATH,
            "run_id": 84,
            "run_attempt": 1,
            "run_url": "https://github.com/mohsamir7122/ku-bo/actions/runs/84",
            "head_sha": "b" * 40,
            "run_started_at": "2026-08-27T11:59:00Z",
            "completed_at": "2026-08-27T12:01:00Z",
        }
        receipt = build_success_receipt(
            incident_id=self.incident()["incident_id"],
            incident_key=self.incident()["idempotency_key"],
            completed_at=NOW,
            repository=origin["repository"],
            workflow_path=PIPELINE_WORKFLOW_PATH,
            run_id="84",
            run_attempt=1,
            run_url=origin["run_url"],
            code_sha=origin["head_sha"],
        )
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("nested/recovery-success.json", json.dumps(receipt))
        incidents, successes = _artifact_records(
            stream.getvalue(), project_root=ROOT, origin=origin
        )
        self.assertEqual(incidents, [])
        self.assertEqual(successes, [])

    def test_discovery_reopens_only_digest_and_run_bound_records(self) -> None:
        api = FakeGitHubApi()
        incident = build_incident(
            ROOT,
            market="KUWAIT",
            stage="gate",
            error_class="permission_required",
            component="durable_checkpoint_store",
            failure_code="BLOCKED_CHECKPOINT_STORE",
            code_sha="b" * 40,
            failed_run_id="84",
            run_url=f"https://github.com/{api.repository}/actions/runs/84",
            summary="blocked checkpoint store",
            now=NOW,
        )
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("recovery-incident.json", json.dumps(incident))
        content = stream.getvalue()
        api.artifact_bytes[7] = content
        api.artifacts.append(
            {
                "id": 7,
                "name": "recovery-diagnostics-gate-84-1",
                "expired": False,
                "created_at": NOW.isoformat(),
                "digest": "sha256:" + hashlib.sha256(content).hexdigest(),
                "workflow_run": {
                    "id": 84,
                    "repository_id": 1,
                    "head_repository_id": 1,
                    "head_branch": "main",
                    "head_sha": "b" * 40,
                },
            }
        )
        api.workflow_runs[84] = {
            "id": 84,
            "run_attempt": 1,
            "status": "completed",
            "conclusion": "failure",
            "path": PIPELINE_WORKFLOW_PATH,
            "head_branch": "main",
            "head_sha": "b" * 40,
            "repository": {"id": 1, "full_name": api.repository},
            "head_repository": {"id": 1, "full_name": api.repository},
            "html_url": f"https://github.com/{api.repository}/actions/runs/84",
            "run_started_at": "2026-08-27T11:59:00Z",
            "updated_at": "2026-08-27T12:01:00Z",
        }
        incidents, successes = discover_recovery_records(api, project_root=ROOT)
        self.assertEqual(incidents, [incident])
        self.assertEqual(successes, [])

        api.artifacts[0]["digest"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(RecoveryError, "digest differs"):
            discover_recovery_records(api, project_root=ROOT)

    def test_pipeline_diagnostic_binds_stage_run_and_attempt_to_artifact(self) -> None:
        base = {
            "market": "KUWAIT",
            "error_class": "permission_required",
            "component": "diagnostic_origin_test",
            "failure_code": "BLOCKED_DIAGNOSTIC_ORIGIN",
            "code_sha": "b" * 40,
            "summary": "diagnostic origin binding test",
            "now": NOW,
        }
        origin = {
            "kind": "recovery-diagnostics-gate",
            "run_id": 84,
            "run_attempt": 1,
            "head_sha": "b" * 40,
            "run_url": "https://github.com/mohsamir7122/ku-bo/actions/runs/84",
        }

        def archive(incident: dict[str, object]) -> bytes:
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, "w") as bundle:
                bundle.writestr("recovery-incident.json", json.dumps(incident))
            return stream.getvalue()

        exact = build_incident(
            ROOT,
            stage="gate",
            failed_run_id="84",
            run_url=origin["run_url"],
            **base,
        )
        incidents, _successes = _artifact_records(
            archive(exact), project_root=ROOT, origin=origin
        )
        self.assertEqual(incidents, [exact])

        wrong_stage = build_incident(
            ROOT,
            stage="collection",
            failed_run_id="84",
            run_url=origin["run_url"],
            **base,
        )
        with self.assertRaisesRegex(RecoveryError, "stage"):
            _artifact_records(archive(wrong_stage), project_root=ROOT, origin=origin)

        wrong_run = build_incident(
            ROOT,
            stage="gate",
            failed_run_id="85",
            run_url="https://github.com/mohsamir7122/ku-bo/actions/runs/85",
            **base,
        )
        with self.assertRaisesRegex(RecoveryError, "failed_run_id"):
            _artifact_records(archive(wrong_run), project_root=ROOT, origin=origin)

        wrong_attempt_origin = {**origin, "run_attempt": 2}
        with self.assertRaisesRegex(RecoveryError, "attempt_count"):
            _artifact_records(
                archive(exact), project_root=ROOT, origin=wrong_attempt_origin
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
