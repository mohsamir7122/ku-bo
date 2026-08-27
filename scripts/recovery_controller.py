#!/usr/bin/env python3
"""Fail-closed local and GitHub recovery controller for KU-BO.

The GitHub path uses only the official REST API. It never executes commands
from issue bodies, web pages, artifacts, or downloaded diagnostics. Artifacts
are untrusted ZIP containers and are reopened through the canonical incident
validator before any retry decision is made.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
from typing import Any, Mapping, Sequence
from urllib import error, request
from urllib.parse import urlencode, urlsplit
import zipfile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from kubo.foundation_io import load_strict_json_object, strict_json_object
from kubo.hashing import canonical_json_bytes
from kubo.recovery import (
    RecoveryError,
    build_incident,
    load_recovery_policy,
    mark_alert_sent,
    record_retry_attempt,
    recovery_decision,
    resolve_incident,
    sanitize_diagnostics,
    sanitize_text,
    validate_dispatch_inputs,
    validate_incident,
    validate_recovery_policy,
)
from kubo.strict import parse_aware


PIPELINE_WORKFLOW = "kuwait-market-pipeline.yml"
CONTROLLER_WORKFLOW = "recovery-controller.yml"
PIPELINE_WORKFLOW_NAME = "Kuwait Market Pipeline"
CI_WORKFLOW_NAME = "CI"
RECOVERY_EVENT = "market-recovery-request"
ALLOWED_DISPATCH_ACTORS = frozenset({"mohsamir7122", "github-actions[bot]"})
ALLOWED_SLOTS = frozenset(
    {
        "main_1500",
        "live_0400",
        "live_0700",
        "market_open_0900",
        "live_1100",
        "live_1200",
        "live_1300",
    }
)
MAX_EVENT_BYTES = 1024 * 1024
MAX_ARTIFACT_BYTES = 8 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 128
MAX_INCIDENTS_PER_PASS = 64
_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_INCIDENT_ID_RE = re.compile(r"^INC-[0-9A-F]{20}$")
_RETRIABLE_PIPELINE_CONCLUSIONS = frozenset(
    {"failure", "timed_out", "startup_failure", "stale"}
)


def _now(value: str | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RecoveryError("--now must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RecoveryError("--now must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _bool(value: Any, field: str) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value or "").strip().casefold()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no", ""}:
        return False
    raise RecoveryError(f"{field} must be true or false")


def _print(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2))


def _safe_write_json(path: Path, value: Any) -> None:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for component in absolute.parts[1:-1]:
        current /= component
        try:
            metadata = os.lstat(current)
        except FileNotFoundError:
            try:
                current.mkdir(mode=0o700)
            except OSError as exc:
                raise RecoveryError("cannot create output parent safely") from exc
            metadata = os.lstat(current)
        except OSError as exc:
            raise RecoveryError("output parent is unreadable") from exc
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise RecoveryError("output parent must contain only real directories")
    if absolute.is_symlink():
        raise RecoveryError("output must not be a symlink")
    content = canonical_json_bytes(value)
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_TRUNC
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(absolute, flags, 0o600)
    except OSError as exc:
        raise RecoveryError("cannot open output safely") from exc
    try:
        os.fchmod(descriptor, 0o600)
        offset = 0
        while offset < len(content):
            offset += os.write(descriptor, content[offset:])
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _active_runs(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    payload, _ = load_strict_json_object(path, field="active runs", max_bytes=1024 * 1024)
    if frozenset(payload) != {"runs"} or not isinstance(payload["runs"], list):
        raise RecoveryError("active-runs file must contain only a runs array")
    rows: list[dict[str, Any]] = []
    for row in payload["runs"]:
        if not isinstance(row, dict):
            raise RecoveryError("active-runs entries must be objects")
        rows.append(row)
    return rows


def _safe_event(path: Path) -> dict[str, Any]:
    try:
        payload, _ = load_strict_json_object(
            path, field="GitHub event", max_bytes=MAX_EVENT_BYTES
        )
    except ValueError as exc:
        raise RecoveryError(str(exc)) from exc
    return payload


def _slot(value: Any) -> str:
    slot = str(value or "main_1500")
    if slot not in ALLOWED_SLOTS:
        raise RecoveryError("slot_id is not allowlisted")
    return slot


def validate_github_event(
    *,
    event_name: str,
    event: Mapping[str, Any],
    actor: str,
    repository: str,
) -> dict[str, Any]:
    """Normalize only admitted pipeline events and reject unknown inputs."""

    if not _REPOSITORY_RE.fullmatch(repository):
        raise RecoveryError("repository must be owner/name")
    payload_repository = event.get("repository")
    if isinstance(payload_repository, Mapping):
        full_name = payload_repository.get("full_name")
        if full_name not in (None, repository):
            raise RecoveryError("event repository differs from GITHUB_REPOSITORY")

    if event_name == "schedule":
        schedule = str(event.get("schedule") or "")
        if not schedule:
            raise RecoveryError("scheduled event is missing its cron identity")
        return {
            "schema_version": "1.0",
            "event_name": "schedule",
            "action": "normal",
            "mode": "normal",
            "incident_id": None,
            "checkpoint": None,
            "slot_id": None,
            "event_schedule": schedule,
            "probe_only": False,
        }

    if event_name == "workflow_dispatch":
        raw_inputs = event.get("inputs") or {}
        if not isinstance(raw_inputs, Mapping):
            raise RecoveryError("workflow_dispatch inputs must be an object")
        allowed = {"mode", "incident_id", "checkpoint", "slot_id"}
        if set(raw_inputs) - allowed:
            raise RecoveryError("workflow_dispatch contains unknown inputs")
        normalized = validate_dispatch_inputs(
            mode=raw_inputs.get("mode", "normal"),
            incident_id=raw_inputs.get("incident_id"),
            checkpoint=raw_inputs.get("checkpoint"),
        )
        return {
            "schema_version": "1.0",
            "event_name": "workflow_dispatch",
            "action": normalized["mode"],
            **normalized,
            "slot_id": _slot(raw_inputs.get("slot_id")),
            "event_schedule": None,
            "probe_only": False,
        }

    if event_name == "repository_dispatch":
        if event.get("action") != RECOVERY_EVENT:
            raise RecoveryError("repository_dispatch type is not allowlisted")
        sender = event.get("sender")
        sender_login = sender.get("login") if isinstance(sender, Mapping) else None
        if actor not in ALLOWED_DISPATCH_ACTORS or sender_login not in ALLOWED_DISPATCH_ACTORS:
            raise RecoveryError("repository_dispatch actor is not allowlisted")
        client = event.get("client_payload")
        expected = {"action", "market", "incident_id", "checkpoint", "slot_id"}
        if not isinstance(client, Mapping) or set(client) != expected:
            raise RecoveryError("repository_dispatch client_payload fields are not exact")
        action = str(client["action"])
        if action not in {"retry", "resume", "probe"}:
            raise RecoveryError("repository_dispatch action is not allowlisted")
        if client["market"] != "KUWAIT":
            raise RecoveryError("repository_dispatch market must be KUWAIT")
        mode = "retry" if action in {"retry", "probe"} else "resume"
        normalized = validate_dispatch_inputs(
            mode=mode,
            incident_id=client["incident_id"],
            checkpoint=client["checkpoint"] if mode == "resume" else None,
        )
        if mode == "retry" and client["checkpoint"] not in (None, ""):
            raise RecoveryError("retry/probe dispatch cannot supply a checkpoint")
        return {
            "schema_version": "1.0",
            "event_name": "repository_dispatch",
            "action": action,
            **normalized,
            "slot_id": _slot(client["slot_id"]),
            "event_schedule": None,
            "probe_only": action == "probe",
        }

    raise RecoveryError("event_name is not admitted for the Kuwait pipeline")


def validate_controller_event(
    *,
    event_name: str,
    event: Mapping[str, Any],
    actor: str,
    repository: str,
) -> dict[str, Any]:
    """Bind controller inputs to one allowlisted GitHub event payload."""

    if not _REPOSITORY_RE.fullmatch(repository):
        raise RecoveryError("repository must be owner/name")
    payload_repository = event.get("repository")
    if isinstance(payload_repository, Mapping):
        full_name = payload_repository.get("full_name")
        if full_name not in (None, repository):
            raise RecoveryError("event repository differs from GITHUB_REPOSITORY")
    context = workflow_event_context(event_name, event)
    if event_name == "workflow_run":
        run = event["workflow_run"]
        head_repository = run.get("head_repository")
        if not isinstance(head_repository, Mapping) or head_repository.get(
            "full_name"
        ) != repository:
            raise RecoveryError("workflow_run head repository is not trusted")
        workflow_name = context["workflow_name"]
        trigger_event = str(run.get("event") or "")
        if workflow_name == CI_WORKFLOW_NAME:
            default_branch = (
                payload_repository.get("default_branch")
                if isinstance(payload_repository, Mapping)
                else None
            )
            if trigger_event != "push" or not default_branch or run.get(
                "head_branch"
            ) != default_branch:
                raise RecoveryError("CI recovery requires a default-branch push")
        elif trigger_event not in {
            "schedule",
            "workflow_dispatch",
            "repository_dispatch",
        }:
            raise RecoveryError("pipeline workflow_run trigger is not allowlisted")
    if event_name in {"workflow_run", "schedule"}:
        if event_name == "schedule" and not str(event.get("schedule") or ""):
            raise RecoveryError("watchdog schedule identity is missing")
        return {**context, "incident_id": None, "force_probe": False}
    if event_name == "workflow_dispatch":
        inputs = event.get("inputs") or {}
        if not isinstance(inputs, Mapping) or set(inputs) - {
            "incident_id",
            "force_probe",
        }:
            raise RecoveryError("controller workflow_dispatch inputs are invalid")
        incident_id = str(inputs.get("incident_id") or "") or None
        if incident_id is not None and not _INCIDENT_ID_RE.fullmatch(incident_id):
            raise RecoveryError("controller incident_id is invalid")
        return {
            **context,
            "incident_id": incident_id,
            "force_probe": _bool(inputs.get("force_probe", False), "force_probe"),
        }
    if event_name == "repository_dispatch":
        if event.get("action") != RECOVERY_EVENT:
            raise RecoveryError("controller repository_dispatch type is not allowlisted")
        sender = event.get("sender")
        sender_login = sender.get("login") if isinstance(sender, Mapping) else None
        if actor not in ALLOWED_DISPATCH_ACTORS or sender_login not in ALLOWED_DISPATCH_ACTORS:
            raise RecoveryError("controller repository_dispatch actor is not allowlisted")
        client = event.get("client_payload")
        expected = {"action", "market", "incident_id", "force_probe"}
        if not isinstance(client, Mapping) or set(client) != expected:
            raise RecoveryError("controller repository_dispatch payload is not exact")
        if client["market"] != "KUWAIT" or client["action"] not in {
            "retry",
            "resume",
            "probe",
        }:
            raise RecoveryError("controller repository_dispatch request is not allowlisted")
        incident_id = str(client["incident_id"] or "")
        if not _INCIDENT_ID_RE.fullmatch(incident_id):
            raise RecoveryError("controller repository_dispatch incident_id is invalid")
        force_probe = _bool(client["force_probe"], "force_probe")
        if client["action"] == "probe" and not force_probe:
            raise RecoveryError("probe action requires force_probe=true")
        return {
            **context,
            "incident_id": incident_id,
            "force_probe": force_probe,
        }
    raise RecoveryError("controller event is not allowlisted")


def _write_github_outputs(path: Path, payload: Mapping[str, Any]) -> None:
    allowed = (
        "action",
        "mode",
        "incident_id",
        "checkpoint",
        "slot_id",
        "event_schedule",
        "probe_only",
    )
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        for key in allowed:
            value = payload.get(key)
            if isinstance(value, bool):
                rendered = str(value).lower()
            else:
                rendered = "" if value is None else str(value)
            if "\n" in rendered or "\r" in rendered:
                raise RecoveryError("GitHub output contains a line break")
            handle.write(f"{key}={rendered}\n")


class _SafeRedirectHandler(request.HTTPRedirectHandler):
    max_redirections = 5
    max_repeats = 1

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is None:
            return None
        old_host = (urlsplit(req.full_url).hostname or "").casefold()
        new_host = (urlsplit(redirected.full_url).hostname or "").casefold()
        if old_host != new_host:
            redirected.remove_header("Authorization")
        return redirected


class GitHubApi:
    """Small official REST client with bounded responses and no body logging."""

    def __init__(self, repository: str, token: str, *, opener=None) -> None:
        if not _REPOSITORY_RE.fullmatch(repository):
            raise RecoveryError("repository must be owner/name")
        if not isinstance(token, str) or not token:
            raise RecoveryError("GITHUB_TOKEN is unavailable")
        self.repository = repository
        self._token = token
        self._opener = opener or request.build_opener(_SafeRedirectHandler())

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: Mapping[str, Any] | None = None,
        raw: bool = False,
        max_bytes: int = 4 * 1024 * 1024,
    ) -> Any:
        expected_prefix = f"/repos/{self.repository}/"
        route = path.split("?", 1)[0]
        if not path.startswith(expected_prefix) or ".." in PurePosixPath(route).parts:
            raise RecoveryError("GitHub API path escaped the repository")
        url = "https://api.github.com" + path
        body = canonical_json_bytes(payload) if payload is not None else None
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer " + self._token,
            "User-Agent": "KU-BO-Recovery-Controller/1",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        req = request.Request(url, data=body, headers=headers, method=method)
        try:
            response = self._opener.open(req, timeout=20)
            try:
                status = int(getattr(response, "status", response.getcode()))
                content = response.read(max_bytes + 1)
            finally:
                response.close()
        except error.HTTPError as exc:
            status = int(exc.code)
            exc.close()
            raise RecoveryError(f"GitHub API request failed with status {status}") from exc
        except (error.URLError, TimeoutError, OSError) as exc:
            raise RecoveryError("GitHub API transport failed") from exc
        if not 200 <= status < 300:
            raise RecoveryError(f"GitHub API request failed with status {status}")
        if len(content) > max_bytes:
            raise RecoveryError("GitHub API response exceeded the bounded size")
        if raw:
            return content
        if not content:
            return None
        try:
            return json.loads(content.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise RecoveryError("GitHub API returned invalid JSON") from exc

    def list_artifacts(self) -> list[dict[str, Any]]:
        payload = self._request(
            "GET", f"/repos/{self.repository}/actions/artifacts?per_page=100"
        )
        rows = payload.get("artifacts") if isinstance(payload, Mapping) else None
        if not isinstance(rows, list):
            raise RecoveryError("GitHub artifacts response is invalid")
        return [dict(row) for row in rows if isinstance(row, Mapping)]

    def download_artifact(self, artifact_id: int) -> bytes:
        if type(artifact_id) is not int or artifact_id <= 0:
            raise RecoveryError("artifact id is invalid")
        return self._request(
            "GET",
            f"/repos/{self.repository}/actions/artifacts/{artifact_id}/zip",
            raw=True,
            max_bytes=MAX_ARTIFACT_BYTES,
        )

    def active_pipeline_runs(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for status in ("queued", "in_progress"):
            query = urlencode({"status": status, "per_page": 100})
            payload = self._request(
                "GET",
                f"/repos/{self.repository}/actions/workflows/{PIPELINE_WORKFLOW}/runs?{query}",
            )
            runs = payload.get("workflow_runs") if isinstance(payload, Mapping) else None
            if not isinstance(runs, list):
                raise RecoveryError("GitHub workflow-runs response is invalid")
            rows.extend(
                {
                    "market": "KUWAIT",
                    "status": status,
                    "run_id": str(row.get("id")),
                }
                for row in runs
                if isinstance(row, Mapping)
            )
        return rows

    def dispatch_pipeline(self, *, ref: str, inputs: Mapping[str, str]) -> None:
        if not re.fullmatch(r"[A-Za-z0-9._/-]{1,200}", ref) or ".." in ref.split("/"):
            raise RecoveryError("dispatch ref is invalid")
        self._request(
            "POST",
            f"/repos/{self.repository}/actions/workflows/{PIPELINE_WORKFLOW}/dispatches",
            payload={"ref": ref, "inputs": dict(inputs)},
        )

    def rerun_failed_jobs(self, run_id: int) -> None:
        """Use GitHub's official failed-jobs rerun endpoint for one run."""

        if type(run_id) is not int or run_id <= 0:
            raise RecoveryError("workflow run id is invalid")
        self._request(
            "POST",
            f"/repos/{self.repository}/actions/runs/{run_id}/rerun-failed-jobs",
        )

    def compare_files(self, base_sha: str, head_sha: str) -> tuple[str, ...]:
        for value in (base_sha, head_sha):
            if not re.fullmatch(r"[0-9a-f]{40}", value):
                raise RecoveryError("compare SHA is invalid")
        payload = self._request(
            "GET", f"/repos/{self.repository}/compare/{base_sha}...{head_sha}"
        )
        files = payload.get("files") if isinstance(payload, Mapping) else None
        if not isinstance(files, list):
            raise RecoveryError("GitHub compare response is invalid")
        return tuple(
            str(row["filename"])
            for row in files
            if isinstance(row, Mapping) and isinstance(row.get("filename"), str)
        )

    def list_recovery_issues(self) -> list[dict[str, Any]]:
        query = urlencode(
            {"state": "all", "labels": "automation-blocked", "per_page": 100}
        )
        payload = self._request("GET", f"/repos/{self.repository}/issues?{query}")
        if not isinstance(payload, list):
            raise RecoveryError("GitHub issues response is invalid")
        return [
            dict(row)
            for row in payload
            if isinstance(row, Mapping) and "pull_request" not in row
        ]

    def create_issue(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        result = self._request(
            "POST", f"/repos/{self.repository}/issues", payload=payload
        )
        if not isinstance(result, Mapping):
            raise RecoveryError("GitHub issue creation response is invalid")
        return dict(result)

    def update_issue(self, number: int, payload: Mapping[str, Any]) -> dict[str, Any]:
        if type(number) is not int or number <= 0:
            raise RecoveryError("issue number is invalid")
        result = self._request(
            "PATCH", f"/repos/{self.repository}/issues/{number}", payload=payload
        )
        if not isinstance(result, Mapping):
            raise RecoveryError("GitHub issue update response is invalid")
        return dict(result)


def _safe_zip_rows(content: bytes) -> list[tuple[str, bytes]]:
    if not isinstance(content, bytes) or len(content) > MAX_ARTIFACT_BYTES:
        raise RecoveryError("recovery artifact is not bounded bytes")
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except (zipfile.BadZipFile, OSError) as exc:
        raise RecoveryError("recovery artifact is not a valid ZIP") from exc
    rows: list[tuple[str, bytes]] = []
    with archive:
        members = archive.infolist()
        if len(members) > MAX_ARCHIVE_MEMBERS:
            raise RecoveryError("recovery artifact contains too many members")
        total = 0
        for member in members:
            path = PurePosixPath(member.filename)
            mode = member.external_attr >> 16
            if (
                path.is_absolute()
                or ".." in path.parts
                or stat.S_ISLNK(mode)
                or member.is_dir()
            ):
                raise RecoveryError("recovery artifact contains an unsafe member")
            total += member.file_size
            if member.file_size > MAX_EVENT_BYTES or total > MAX_ARTIFACT_BYTES:
                raise RecoveryError("recovery artifact expands beyond the bounded size")
            rows.append((member.filename, archive.read(member)))
    return rows


def _artifact_records(
    content: bytes, *, project_root: Path
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    incidents: list[dict[str, Any]] = []
    successes: list[dict[str, Any]] = []
    for name, raw in _safe_zip_rows(content):
        basename = PurePosixPath(name).name
        if basename == "recovery-incident.json" or (
            basename.startswith("INC-") and basename.endswith(".json")
        ):
            try:
                payload = strict_json_object(raw, f"artifact {basename}")
                incidents.append(validate_incident(payload, project_root=project_root))
            except ValueError as exc:
                raise RecoveryError(str(exc)) from exc
        elif basename == "recovery-success.json":
            try:
                payload = strict_json_object(raw, "recovery success receipt")
            except ValueError as exc:
                raise RecoveryError(str(exc)) from exc
            expected = {
                "schema_version",
                "incident_id",
                "completed_at",
                "run_url",
                "code_sha",
            }
            if set(payload) != expected or payload["schema_version"] != "1.0":
                raise RecoveryError("recovery success receipt fields are invalid")
            if not _INCIDENT_ID_RE.fullmatch(str(payload["incident_id"])):
                raise RecoveryError("recovery success incident_id is invalid")
            parse_aware(payload["completed_at"], "recovery success completed_at")
            if not re.fullmatch(r"[0-9a-f]{40}", str(payload["code_sha"])):
                raise RecoveryError("recovery success code_sha is invalid")
            parsed_url = urlsplit(str(payload["run_url"]))
            if (
                parsed_url.scheme != "https"
                or parsed_url.hostname != "github.com"
                or "/actions/runs/" not in parsed_url.path
                or parsed_url.query
                or parsed_url.fragment
            ):
                raise RecoveryError("recovery success run_url is invalid")
            successes.append(payload)
    return incidents, successes


def discover_recovery_records(
    api: GitHubApi, *, project_root: Path
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    incidents: list[dict[str, Any]] = []
    successes: list[dict[str, Any]] = []
    artifacts = sorted(
        api.list_artifacts(), key=lambda row: str(row.get("created_at", "")), reverse=True
    )
    for artifact in artifacts[:MAX_INCIDENTS_PER_PASS]:
        name = str(artifact.get("name", ""))
        if not name.startswith(
            ("recovery-diagnostics-", "recovery-state-", "recovery-success-")
        ):
            continue
        if artifact.get("expired") is True:
            continue
        artifact_id = artifact.get("id")
        if type(artifact_id) is not int:
            raise RecoveryError("recovery artifact id is invalid")
        found_incidents, found_successes = _artifact_records(
            api.download_artifact(artifact_id), project_root=project_root
        )
        incidents.extend(found_incidents)
        successes.extend(found_successes)
    return incidents, successes


def _latest_incidents(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        item = dict(row)
        fingerprint = str(item["fingerprint"])
        previous = latest.get(fingerprint)
        item_order = (
            parse_aware(item["last_seen_at"], "last_seen_at"),
            int(item["attempt_count"]),
        )
        previous_order = (
            parse_aware(previous["last_seen_at"], "last_seen_at"),
            int(previous["attempt_count"]),
        ) if previous is not None else None
        if previous_order is None or item_order > previous_order:
            latest[fingerprint] = item
    return sorted(latest.values(), key=lambda item: str(item["incident_id"]))


def _change_is_relevant(component: str, files: Sequence[str]) -> bool:
    normalized = component.casefold().replace("-", "_")
    tokens = {
        token for token in re.split(r"[^a-z0-9]+", normalized) if len(token) >= 4
    }
    recovery_roots = {
        "src/kubo/recovery.py",
        "scripts/recovery_controller.py",
        ".github/workflows/kuwait-market-pipeline.yml",
        ".github/workflows/recovery-controller.yml",
    }
    for filename in files:
        folded = filename.casefold()
        if filename in recovery_roots or any(token in folded for token in tokens):
            return True
    return False


def _issue_marker(fingerprint: str) -> str:
    return f"<!-- kubo-recovery-fingerprint:{fingerprint} -->"


def _issue_body(incident: Mapping[str, Any], decision: Mapping[str, Any]) -> str:
    summary = sanitize_text(incident["sanitized_summary"], max_length=1000)
    action = incident.get("required_user_action") or (
        "Review the blocker and provide the required permission, secret, or validated fix."
    )
    action = sanitize_text(action, max_length=1000)
    run_url = incident.get("run_url") or "Not available"
    tried = ", ".join(str(item) for item in incident["fallbacks_tried"]) or "None recorded"
    resume = (
        "gh workflow run recovery-controller.yml --ref main "
        f"-f incident_id=\"{incident['incident_id']}\" -f force_probe=true"
    )
    return "\n".join(
        (
            _issue_marker(str(incident["fingerprint"])),
            "KU-BO stopped publication and emitted NO-TRADE.",
            "",
            f"- Incident: `{incident['incident_id']}`",
            f"- Stage: `{incident['stage']}`",
            f"- Error class: `{incident['error_class']}`",
            f"- Controller action: `{decision['action']}`",
            f"- Run URL: {run_url}",
            f"- Sanitized reason: {summary}",
            f"- Fallbacks tried: {tried}",
            f"- Required action: {action}",
            f"- Resume command: `{resume}`",
            "",
            "No raw logs, response bodies, credentials, or signed URLs are included.",
        )
    )


def _find_issue(
    issues: Sequence[Mapping[str, Any]], fingerprint: str
) -> Mapping[str, Any] | None:
    marker = _issue_marker(fingerprint)
    for issue in issues:
        if marker in str(issue.get("body", "")):
            return issue
    return None


def _upsert_alert(
    api: GitHubApi,
    *,
    incident: Mapping[str, Any],
    decision: Mapping[str, Any],
    now: datetime,
    policy: Mapping[str, Any],
) -> bool:
    existing = _find_issue(api.list_recovery_issues(), str(incident["fingerprint"]))
    if existing is not None:
        updated_at = parse_aware(existing["updated_at"], "issue.updated_at")
        suppression = timedelta(
            hours=policy["alerts"]["duplicate_suppression_hours"]
        )
        if now < updated_at.astimezone(timezone.utc) + suppression:
            return False
    payload: dict[str, Any] = {
        "title": policy["alerts"]["issue_title"],
        "body": _issue_body(incident, decision),
        "labels": list(policy["alerts"]["labels"]),
        "assignees": [policy["alerts"]["assignee"]],
        "state": "open",
    }
    if existing is None:
        try:
            api.create_issue(payload)
        except RecoveryError:
            payload.pop("assignees", None)
            api.create_issue(payload)
    else:
        api.update_issue(int(existing["number"]), payload)
    return True


def _close_alert(api: GitHubApi, fingerprint: str) -> bool:
    existing = _find_issue(api.list_recovery_issues(), fingerprint)
    if existing is None or existing.get("state") == "closed":
        return False
    api.update_issue(
        int(existing["number"]),
        {
            "state": "closed",
            "state_reason": "completed",
            "body": str(existing.get("body", ""))
            + "\n\nClosed automatically after a hash-bound successful recovery run.",
        },
    )
    return True


def run_github_controller(
    *,
    project_root: Path,
    api: GitHubApi,
    now: datetime,
    default_ref: str,
    current_code_sha: str,
    required_secrets_present: bool,
    incidents: Sequence[Mapping[str, Any]],
    successes: Sequence[Mapping[str, Any]] = (),
    incident_id: str | None = None,
    force_probe: bool = False,
    ci_passed: bool = False,
    smoke_passed: bool = False,
    changed_files: Sequence[str] = (),
    event_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Make one bounded controller pass; no sleeps and no recursive dispatch."""

    policy, _ = load_recovery_policy(project_root)
    if not re.fullmatch(r"[0-9a-f]{40}", current_code_sha):
        raise RecoveryError("current_code_sha must be a 40-character SHA")
    if incident_id is not None and not _INCIDENT_ID_RE.fullmatch(incident_id):
        raise RecoveryError("incident_id is invalid")
    context = dict(event_context or {"kind": "manual"})
    kind = str(context.get("kind") or "manual")
    workflow_name = context.get("workflow_name")
    workflow_conclusion = context.get("conclusion")
    workflow_run_id = context.get("run_id")
    workflow_run_attempt = context.get("run_attempt")
    active_runs = api.active_pipeline_runs()
    successful_ids = {str(row["incident_id"]): row for row in successes}
    outputs: list[dict[str, Any]] = []
    state_rows: list[dict[str, Any]] = []
    selected = _latest_incidents(incidents)
    if workflow_name == PIPELINE_WORKFLOW_NAME:
        selected = [
            row for row in selected if str(row["failed_run_id"]) == str(workflow_run_id)
        ]
    elif workflow_name == CI_WORKFLOW_NAME:
        selected = [row for row in selected if row["error_class"] == "deterministic_code"]
    if incident_id is not None:
        selected = [row for row in selected if row["incident_id"] == incident_id]
        if not selected:
            raise RecoveryError("requested incident was not found in validated artifacts")

    for incident in selected[:MAX_INCIDENTS_PER_PASS]:
        row = validate_incident(incident, policy=policy)
        if row["incident_id"] in successful_ids:
            resolved = resolve_incident(row, now=now, policy=policy)
            closed = _close_alert(api, str(row["fingerprint"]))
            state_rows.append(resolved)
            outputs.append(
                {
                    "incident_id": row["incident_id"],
                    "action": "RESOLVED_FROM_SUCCESS_RECEIPT",
                    "dispatched": False,
                    "alert_closed": closed,
                }
            )
            continue

        if workflow_name == PIPELINE_WORKFLOW_NAME and workflow_conclusion == "success":
            state_rows.append(row)
            outputs.append(
                {
                    "incident_id": row["incident_id"],
                    "fingerprint": row["fingerprint"],
                    "idempotency_key": row["idempotency_key"],
                    "action": "PIPELINE_SUCCESS_AWAITING_HASH_BOUND_RECEIPT",
                    "dispatched": False,
                    "alert_sent": False,
                    "publish_allowed": False,
                }
            )
            continue

        if workflow_name == PIPELINE_WORKFLOW_NAME:
            if workflow_conclusion not in _RETRIABLE_PIPELINE_CONCLUSIONS:
                state_rows.append(row)
                outputs.append(
                    {
                        "incident_id": row["incident_id"],
                        "fingerprint": row["fingerprint"],
                        "idempotency_key": row["idempotency_key"],
                        "action": "NO_RETRY_PIPELINE_CONCLUSION",
                        "dispatched": False,
                        "alert_sent": False,
                        "publish_allowed": False,
                    }
                )
                continue
            if type(workflow_run_attempt) is not int or workflow_run_attempt < 1:
                raise RecoveryError("pipeline workflow_run attempt is invalid")
            if row["retriable"]:
                target_attempts = min(
                    workflow_run_attempt - 1,
                    policy["retry"]["max_automatic_attempts"],
                )
                while row["attempt_count"] < target_attempts:
                    observed = max(
                        now,
                        parse_aware(
                            row["last_seen_at"], "last_seen_at"
                        ).astimezone(timezone.utc),
                    )
                    row = record_retry_attempt(row, now=observed, policy=policy)
                handled_attempts = min(
                    workflow_run_attempt,
                    policy["retry"]["max_automatic_attempts"],
                )
                if row["attempt_count"] >= handled_attempts:
                    decision = {
                        "action": (
                            "RETRY_EXHAUSTED"
                            if row["attempt_count"] >= row["max_attempts"]
                            else "SUPPRESS_DUPLICATE_WORKFLOW_EVENT"
                        ),
                        "dispatch_allowed": False,
                        "alert_due": row["attempt_count"] >= row["max_attempts"],
                        "publish_allowed": False,
                    }
                else:
                    decision = None
            else:
                decision = None
        else:
            decision = None

        component = str(row["fingerprint_basis"]["component"])
        if decision is None:
            decision = recovery_decision(
                row,
                now=now,
                policy=policy,
                active_runs=active_runs,
                required_secret_available=required_secrets_present,
                current_code_sha=current_code_sha,
                relevant_code_change=_change_is_relevant(component, changed_files),
                ci_passed=ci_passed,
                smoke_passed=smoke_passed,
            )
        if kind == "watchdog" and row["retriable"] and decision["dispatch_allowed"]:
            last_seen = parse_aware(row["last_seen_at"], "last_seen_at").astimezone(
                timezone.utc
            )
            grace = timedelta(
                seconds=policy["controller"]["missed_event_grace_seconds"]
            )
            if now < last_seen + grace:
                decision = {
                    **decision,
                    "action": "WATCHDOG_EVENT_NOT_MISSED",
                    "dispatch_allowed": False,
                }
        if (
            force_probe
            and row["error_class"] == "missing_secret"
            and not required_secrets_present
        ):
            decision = {
                **decision,
                "action": "HEALTH_PROBE_ONLY",
                "dispatch_allowed": False,
            }

        updated = dict(row)
        dispatched = False
        dispatch_method = "none"
        if decision["dispatch_allowed"]:
            if decision["action"] == "DISPATCH_RETRY":
                try:
                    failed_run_id = int(str(row["failed_run_id"]))
                except ValueError as exc:
                    raise RecoveryError("failed_run_id is not a GitHub workflow run id") from exc
                api.rerun_failed_jobs(failed_run_id)
                dispatch_method = "RERUN_FAILED_JOBS"
            else:
                inputs = {
                    "mode": "resume",
                    "incident_id": str(row["incident_id"]),
                    "checkpoint": str(row.get("checkpoint_id") or ""),
                    "slot_id": "main_1500",
                }
                api.dispatch_pipeline(ref=default_ref, inputs=inputs)
                dispatch_method = "WORKFLOW_DISPATCH_RESUME"
            dispatched = True
            if row["retriable"]:
                updated = record_retry_attempt(row, now=now, policy=policy)

        alert_needed = bool(decision.get("alert_due")) or (
            updated["status"] == "EXHAUSTED" and not dispatched
        )
        alerted = False
        if alert_needed:
            alerted = _upsert_alert(
                api,
                incident=updated,
                decision=decision,
                now=now,
                policy=policy,
            )
            if alerted:
                updated = mark_alert_sent(updated, now=now, policy=policy)
        state_rows.append(updated)
        outputs.append(
            {
                "incident_id": row["incident_id"],
                "fingerprint": row["fingerprint"],
                "idempotency_key": updated["idempotency_key"],
                "action": decision["action"],
                "dispatched": dispatched,
                "dispatch_method": dispatch_method,
                "alert_sent": alerted,
                "publish_allowed": False,
            }
        )

    return {
        "schema_version": "1.0",
        "status": "PASS_CONTROLLER_BOUNDED",
        "processed_at": now.astimezone(timezone.utc).isoformat(),
        "processed_incident_count": len(outputs),
        "active_run_count": len(active_runs),
        "trigger_kind": kind,
        "decisions": outputs,
        "incidents": state_rows,
        "direct_email_status": policy["alerts"]["direct_email_status"],
        "claim_boundaries": {
            "controller_may_modify_main": False,
            "controller_may_merge_pull_request": False,
            "controller_may_disable_safety_gate": False,
            "controller_may_submit_trade": False,
        },
    }


def workflow_event_context(event_name: str, event: Mapping[str, Any]) -> dict[str, Any]:
    if event_name == "schedule":
        return {"kind": "watchdog", "workflow_name": None}
    if event_name in {"workflow_dispatch", "repository_dispatch"}:
        return {"kind": "manual", "workflow_name": None}
    if event_name != "workflow_run":
        raise RecoveryError("controller event is not allowlisted")
    run = event.get("workflow_run")
    if not isinstance(run, Mapping) or run.get("name") not in {
        CI_WORKFLOW_NAME,
        PIPELINE_WORKFLOW_NAME,
    }:
        raise RecoveryError("workflow_run is not an allowlisted workflow")
    if event.get("action") != "completed":
        raise RecoveryError("workflow_run must be a completed event")
    run_id = run.get("id")
    run_attempt = run.get("run_attempt")
    if type(run_id) is not int or run_id <= 0:
        raise RecoveryError("workflow_run id is invalid")
    if type(run_attempt) is not int or not 1 <= run_attempt <= 100:
        raise RecoveryError("workflow_run attempt is invalid")
    head_sha = str(run.get("head_sha") or "")
    if not re.fullmatch(r"[0-9a-f]{40}", head_sha):
        raise RecoveryError("workflow_run head_sha is invalid")
    conclusion = str(run.get("conclusion") or "")
    if conclusion not in {
        "action_required",
        "cancelled",
        "failure",
        "neutral",
        "skipped",
        "stale",
        "startup_failure",
        "success",
        "timed_out",
    }:
        raise RecoveryError("workflow_run conclusion is invalid")
    return {
        "kind": "workflow_run",
        "workflow_name": run["name"],
        "conclusion": conclusion,
        "run_id": str(run_id),
        "run_attempt": run_attempt,
        "head_sha": head_sha,
        "ci_passed": run["name"] == CI_WORKFLOW_NAME and conclusion == "success",
        "smoke_passed": run["name"] == CI_WORKFLOW_NAME and conclusion == "success",
    }


def build_success_receipt(
    *, incident_id: Any, completed_at: datetime, run_url: Any, code_sha: Any
) -> dict[str, Any]:
    incident = str(incident_id or "")
    sha = str(code_sha or "")
    url = str(run_url or "")
    if not _INCIDENT_ID_RE.fullmatch(incident):
        raise RecoveryError("recovery success incident_id is invalid")
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise RecoveryError("recovery success code_sha is invalid")
    parsed_url = urlsplit(url)
    if (
        parsed_url.scheme != "https"
        or parsed_url.hostname != "github.com"
        or "/actions/runs/" not in parsed_url.path
        or parsed_url.query
        or parsed_url.fragment
    ):
        raise RecoveryError("recovery success run_url is invalid")
    return {
        "schema_version": "1.0",
        "incident_id": incident,
        "completed_at": completed_at.astimezone(timezone.utc).isoformat(),
        "run_url": url,
        "code_sha": sha,
    }


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(
        description="Validate incidents and make fail-closed KU-BO recovery decisions"
    )
    value.add_argument("--project-root", type=Path, default=Path.cwd())
    commands = value.add_subparsers(dest="command", required=True)

    commands.add_parser("validate-policy")

    validate = commands.add_parser("validate-incident")
    validate.add_argument("--incident", type=Path, required=True)

    create = commands.add_parser("create-incident")
    create.add_argument("--market", default="KUWAIT")
    create.add_argument("--stage", required=True)
    create.add_argument("--error-class", required=True)
    create.add_argument("--component", required=True)
    create.add_argument("--failure-code", required=True)
    create.add_argument("--code-sha", required=True)
    create.add_argument("--failed-run-id", required=True)
    create.add_argument("--summary", required=True)
    create.add_argument("--run-url")
    create.add_argument("--checkpoint-id")
    create.add_argument("--required-user-action")
    create.add_argument("--completed-run-attempt", type=int, default=1)
    create.add_argument("--now")
    create.add_argument("--output", type=Path)

    decide = commands.add_parser("decide")
    decide.add_argument("--incident", type=Path, required=True)
    decide.add_argument("--active-runs", type=Path)
    decide.add_argument(
        "--secret-state", choices=("unknown", "missing", "present"), default="unknown"
    )
    decide.add_argument("--current-code-sha")
    decide.add_argument("--relevant-code-change", action="store_true")
    decide.add_argument("--ci-passed", action="store_true")
    decide.add_argument("--smoke-passed", action="store_true")
    decide.add_argument("--now")

    dispatch = commands.add_parser("validate-dispatch")
    dispatch.add_argument("--mode", required=True)
    dispatch.add_argument("--incident-id")
    dispatch.add_argument("--checkpoint")

    event_command = commands.add_parser("validate-event")
    event_command.add_argument("--event-name", required=True)
    event_command.add_argument("--event-path", type=Path, required=True)
    event_command.add_argument("--actor", required=True)
    event_command.add_argument("--repository", required=True)
    event_command.add_argument("--output", type=Path)
    event_command.add_argument("--github-output", type=Path)

    redact = commands.add_parser("redact-diagnostics")
    redact.add_argument("--input", type=Path, required=True)
    redact.add_argument("--output", type=Path)

    success = commands.add_parser("create-success-receipt")
    success.add_argument("--incident-id", required=True)
    success.add_argument("--run-url", required=True)
    success.add_argument("--code-sha", required=True)
    success.add_argument("--completed-at")
    success.add_argument("--output", type=Path, required=True)

    github = commands.add_parser("github-control")
    github.add_argument("--repository", required=True)
    github.add_argument("--token-env", default="GITHUB_TOKEN")
    github.add_argument("--default-ref", default="main")
    github.add_argument("--current-code-sha", required=True)
    github.add_argument("--event-name", required=True)
    github.add_argument("--event-path", type=Path, required=True)
    github.add_argument("--actor", required=True)
    github.add_argument("--required-secrets-present", required=True)
    github.add_argument("--incident-id")
    github.add_argument("--force-probe", default="false")
    github.add_argument("--now")
    github.add_argument("--output", type=Path, required=True)
    github.add_argument("--state-output-root", type=Path, required=True)
    return value


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        root = args.project_root.resolve()
        if args.command == "validate-policy":
            result = validate_recovery_policy(root)
        elif args.command == "validate-incident":
            result = validate_incident(args.incident, project_root=root)
        elif args.command == "create-incident":
            if not 1 <= args.completed_run_attempt <= 3:
                raise RecoveryError("completed-run-attempt must be between 1 and 3")
            observed_at = _now(args.now)
            result = build_incident(
                root,
                market=args.market,
                stage=args.stage,
                error_class=args.error_class,
                component=args.component,
                failure_code=args.failure_code,
                code_sha=args.code_sha,
                failed_run_id=args.failed_run_id,
                summary=args.summary,
                now=observed_at,
                run_url=args.run_url,
                checkpoint_id=args.checkpoint_id,
                required_user_action=args.required_user_action,
            )
            for _ in range(args.completed_run_attempt - 1):
                if not result["retriable"]:
                    break
                result = record_retry_attempt(result, now=observed_at, policy=load_recovery_policy(root)[0])
            if args.output:
                _safe_write_json(args.output, result)
        elif args.command == "decide":
            policy, _ = load_recovery_policy(root)
            incident = validate_incident(args.incident, policy=policy)
            secret = (
                None if args.secret_state == "unknown" else args.secret_state == "present"
            )
            result = recovery_decision(
                incident,
                now=_now(args.now),
                policy=policy,
                active_runs=_active_runs(args.active_runs),
                required_secret_available=secret,
                current_code_sha=args.current_code_sha,
                relevant_code_change=args.relevant_code_change,
                ci_passed=args.ci_passed,
                smoke_passed=args.smoke_passed,
            )
        elif args.command == "validate-dispatch":
            result = validate_dispatch_inputs(
                mode=args.mode,
                incident_id=args.incident_id,
                checkpoint=args.checkpoint,
            )
        elif args.command == "validate-event":
            result = validate_github_event(
                event_name=args.event_name,
                event=_safe_event(args.event_path),
                actor=args.actor,
                repository=args.repository,
            )
            if args.output:
                _safe_write_json(args.output, result)
            if args.github_output:
                _write_github_outputs(args.github_output, result)
        elif args.command == "redact-diagnostics":
            payload, _ = load_strict_json_object(
                args.input, field="diagnostics", max_bytes=4 * 1024 * 1024
            )
            result = sanitize_diagnostics(payload)
            if args.output:
                _safe_write_json(args.output, result)
        elif args.command == "create-success-receipt":
            result = build_success_receipt(
                incident_id=args.incident_id,
                completed_at=_now(args.completed_at),
                run_url=args.run_url,
                code_sha=args.code_sha,
            )
            _safe_write_json(args.output, result)
        elif args.command == "github-control":
            api = GitHubApi(args.repository, os.environ.get(args.token_env, ""))
            event = _safe_event(args.event_path)
            event_context = validate_controller_event(
                event_name=args.event_name,
                event=event,
                actor=args.actor,
                repository=args.repository,
            )
            requested_incident_id = event_context.get("incident_id")
            requested_force_probe = bool(event_context.get("force_probe", False))
            if args.incident_id and args.incident_id != requested_incident_id:
                raise RecoveryError("incident_id differs from the signed event payload")
            if _bool(args.force_probe, "force_probe") != requested_force_probe:
                raise RecoveryError("force_probe differs from the signed event payload")
            ci_passed = bool(event_context.get("ci_passed", False))
            smoke_passed = bool(event_context.get("smoke_passed", False))
            current_sha = str(event_context.get("head_sha") or args.current_code_sha)
            incidents, successes = discover_recovery_records(api, project_root=root)
            changed_files: tuple[str, ...] = ()
            if ci_passed:
                bases = sorted(
                    {
                        str(row["code_sha"])
                        for row in incidents
                        if row["error_class"] == "deterministic_code"
                        and row["code_sha"] != current_sha
                    }
                )
                changed: set[str] = set()
                for base in bases[:MAX_INCIDENTS_PER_PASS]:
                    changed.update(api.compare_files(base, current_sha))
                changed_files = tuple(sorted(changed))
            result = run_github_controller(
                project_root=root,
                api=api,
                now=_now(args.now),
                default_ref=args.default_ref,
                current_code_sha=current_sha,
                required_secrets_present=_bool(
                    args.required_secrets_present, "required_secrets_present"
                ),
                incidents=incidents,
                successes=successes,
                incident_id=requested_incident_id,
                force_probe=requested_force_probe,
                ci_passed=ci_passed,
                smoke_passed=smoke_passed,
                changed_files=changed_files,
                event_context=event_context,
            )
            _safe_write_json(args.output, result)
            state_root = Path(args.state_output_root)
            for incident in result["incidents"]:
                _safe_write_json(
                    state_root / f"{incident['incident_id']}.json", incident
                )
        else:  # pragma: no cover - argparse enforces the subcommand
            raise RecoveryError("unsupported command")
        _print(result)
        return 0
    except (RecoveryError, ValueError, TypeError) as exc:
        print(f"RECOVERY_CONTROLLER_BLOCKED: {sanitize_text(exc)}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
