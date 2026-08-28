from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any, Mapping


CONTROL_STATE_FILE = "config/codex_control_state.json"
REQUIRED_FILES = (
    "AGENTS.md",
    "CODEX_START_HERE.md",
    CONTROL_STATE_FILE,
    "STATUS.md",
    "NEXT_ACTIONS.md",
    "PROGRESS.json",
    "docs/codex/PROJECT_RULES.md",
    "docs/codex/CURRENT_STATUS.md",
    "docs/codex/CURRENT_TASK.md",
    "docs/codex/ACCEPTANCE_GATES.md",
    "docs/codex/CONVERSATION_IMPORT_POLICY.md",
    "docs/codex/USER_DECISIONS.md",
    "docs/codex/HANDOFF_TEMPLATE.md",
    "docs/codex/PROMPT_TEMPLATES.md",
)
REQUIRED_METADATA = (
    "TASK_ID",
    "STATUS",
    "REPOSITORY",
    "CONTROL_STATE_FILE",
    "CONTROL_BASE_BRANCH",
    "CONTROL_BASE_SHA",
    "EXPECTED_NEW_BRANCH",
    "EXPECTED_PR_MODE",
    "MERGE_ALLOWED",
    "FORCE_PUSH_ALLOWED",
    "PERMANENT_DELETE_ALLOWED",
    "REAL_DATA_COMMIT_ALLOWED",
    "PRIVATE_CONVERSATION_COMMIT_ALLOWED",
    "MODEL_TRAINING_ALLOWED",
    "REAL_BACKTEST_ALLOWED",
    "AUTOMATIC_SCHEDULES_ALLOWED",
    "MANUAL_CANARY_ALLOWED",
    "FINANCIAL_EXECUTION_ALLOWED",
    "LIVE_OPERATIONAL_CLAIM_ALLOWED",
    "PREDICTIVE_CLAIM_ALLOWED",
)
MUST_BE_NO = (
    "MERGE_ALLOWED",
    "FORCE_PUSH_ALLOWED",
    "PERMANENT_DELETE_ALLOWED",
    "REAL_DATA_COMMIT_ALLOWED",
    "PRIVATE_CONVERSATION_COMMIT_ALLOWED",
    "MODEL_TRAINING_ALLOWED",
    "REAL_BACKTEST_ALLOWED",
    "AUTOMATIC_SCHEDULES_ALLOWED",
    "FINANCIAL_EXECUTION_ALLOWED",
    "LIVE_OPERATIONAL_CLAIM_ALLOWED",
    "PREDICTIVE_CLAIM_ALLOWED",
)
ALLOWED_TASK_STATUSES = frozenset(
    {"READY", "IN_PROGRESS", "BLOCKED", "COMPLETED", "SUPERSEDED"}
)
PRIVATE_GOOGLE_URL = re.compile(
    r"https://(?:drive|docs)\.google\.com/(?:drive/folders|document/d|spreadsheets/d|presentation/d)/[A-Za-z0-9_-]+",
    flags=re.IGNORECASE,
)
FULL_GIT_SHA = re.compile(r"[0-9a-f]{40}")
FORBIDDEN_REPOSITORY_PATH_PARTS = frozenset(
    {
        "raw_conversations",
        "private_conversations",
        "conversation_transcripts",
        "chat_exports",
        "chat_transcripts",
    }
)
TEXT_STATE_MIRRORS = (
    "CODEX_START_HERE.md",
    "STATUS.md",
    "NEXT_ACTIONS.md",
    "docs/codex/CURRENT_STATUS.md",
)
TASK_STATE_FIELDS = {
    "TASK_ID": "task_id",
    "STATUS": "status",
    "REPOSITORY": "repository",
    "CONTROL_BASE_BRANCH": "control_base_branch",
    "CONTROL_BASE_SHA": "control_base_sha",
    "EXPECTED_NEW_BRANCH": "work_branch",
    "EXPECTED_PR_MODE": "pr_mode",
}
PERMISSION_STATE_FIELDS = {
    "MERGE_ALLOWED": "merge_allowed",
    "FORCE_PUSH_ALLOWED": "force_push_allowed",
    "PERMANENT_DELETE_ALLOWED": "permanent_delete_allowed",
    "REAL_DATA_COMMIT_ALLOWED": "real_data_commit_allowed",
    "PRIVATE_CONVERSATION_COMMIT_ALLOWED": "private_conversation_commit_allowed",
    "MODEL_TRAINING_ALLOWED": "model_training_allowed",
    "REAL_BACKTEST_ALLOWED": "real_backtest_allowed",
    "AUTOMATIC_SCHEDULES_ALLOWED": "automatic_schedules_allowed",
    "MANUAL_CANARY_ALLOWED": "manual_canary_allowed",
    "FINANCIAL_EXECUTION_ALLOWED": "financial_execution_allowed",
}
CLAIM_STATE_FIELDS = {
    "LIVE_OPERATIONAL_CLAIM_ALLOWED": "live_operational_claim_allowed",
    "PREDICTIVE_CLAIM_ALLOWED": "predictive_claim_allowed",
}


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"cannot read UTF-8 text file: {path}") from exc


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            _read(path),
            object_pairs_hook=_reject_duplicate_pairs,
        )
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def _metadata(task_text: str) -> dict[str, str]:
    metadata: dict[str, str] = {}
    in_fence = False
    for line in task_text.splitlines():
        if line.strip() == "```text":
            in_fence = True
            continue
        if in_fence and line.strip() == "```":
            break
        if not in_fence:
            continue
        match = re.fullmatch(r"([A-Z][A-Z0-9_]*):\s*(.+)", line.strip())
        if match:
            key, value = match.groups()
            if key in metadata:
                raise ValueError(f"duplicate CURRENT_TASK metadata key: {key}")
            metadata[key] = value.strip()
    return metadata


def _yes_no(value: Any) -> str | None:
    if value is True:
        return "YES"
    if value is False:
        return "NO"
    return None


def _validate_control_state(
    state: Mapping[str, Any], errors: list[str]
) -> None:
    required = {
        "schema_version",
        "source_of_truth",
        "task_id",
        "status",
        "repository",
        "control_base_branch",
        "control_base_sha",
        "work_branch",
        "pr_mode",
        "permissions",
        "claim_boundaries",
    }
    missing = sorted(required - set(state))
    if missing:
        errors.append("CONTROL_STATE_FIELDS_MISSING:" + ",".join(missing))
    if state.get("schema_version") != "1.0":
        errors.append("CONTROL_STATE_SCHEMA_VERSION_INVALID")
    if state.get("source_of_truth") is not True:
        errors.append("CONTROL_STATE_MUST_BE_SOURCE_OF_TRUTH")
    if state.get("status") not in ALLOWED_TASK_STATUSES:
        errors.append("CONTROL_STATE_STATUS_INVALID")
    if state.get("repository") != "mohsamir7122/ku-bo":
        errors.append("CONTROL_STATE_REPOSITORY_MISMATCH")
    if state.get("control_base_branch") != "main":
        errors.append("CONTROL_STATE_BASE_BRANCH_MUST_BE_MAIN")
    base_sha = state.get("control_base_sha")
    if not isinstance(base_sha, str) or FULL_GIT_SHA.fullmatch(base_sha) is None:
        errors.append("CONTROL_STATE_BASE_SHA_INVALID")
    work_branch = state.get("work_branch")
    if not isinstance(work_branch, str) or not work_branch:
        errors.append("CONTROL_STATE_WORK_BRANCH_INVALID")
    if work_branch == state.get("control_base_branch"):
        errors.append("CONTROL_STATE_WORK_BRANCH_EQUALS_BASE")
    if state.get("pr_mode") != "DRAFT":
        errors.append("CONTROL_STATE_PR_MODE_MUST_BE_DRAFT")

    permissions = state.get("permissions")
    if not isinstance(permissions, dict):
        errors.append("CONTROL_STATE_PERMISSIONS_INVALID")
        permissions = {}
    for key in PERMISSION_STATE_FIELDS.values():
        if not isinstance(permissions.get(key), bool):
            errors.append(f"CONTROL_STATE_PERMISSION_NOT_BOOLEAN:{key}")
    for key in (
        "merge_allowed",
        "force_push_allowed",
        "permanent_delete_allowed",
        "real_data_commit_allowed",
        "private_conversation_commit_allowed",
        "model_training_allowed",
        "real_backtest_allowed",
        "automatic_schedules_allowed",
        "financial_execution_allowed",
    ):
        if permissions.get(key) is not False:
            errors.append(f"CONTROL_STATE_UNSAFE_PERMISSION:{key}")
    if permissions.get("manual_canary_allowed") is not True:
        errors.append("CONTROL_STATE_MANUAL_CANARY_NOT_ALLOWED")

    claims = state.get("claim_boundaries")
    if not isinstance(claims, dict):
        errors.append("CONTROL_STATE_CLAIMS_INVALID")
        claims = {}
    for key in CLAIM_STATE_FIELDS.values():
        if claims.get(key) is not False:
            errors.append(f"CONTROL_STATE_UNSAFE_CLAIM:{key}")


def _git(
    root: Path, *args: str
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    environment["GIT_NO_LAZY_FETCH"] = "1"
    return subprocess.run(
        ["git", *args],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )


def _github_event() -> dict[str, Any] | None:
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        return None
    try:
        value = _load_json(Path(event_path))
    except (ValueError, OSError):
        return None
    return value


def _github_environment_matches_root(root: Path) -> bool:
    """Use GitHub event context only for the checkout that owns it.

    The unit suite builds independent Git repositories under temporary roots.
    Ambient ``GITHUB_*`` values from the outer Actions checkout must not be
    treated as authority for those repositories.
    """

    workspace = os.environ.get("GITHUB_WORKSPACE", "").strip()
    if not workspace:
        return False
    try:
        return Path(workspace).resolve() == root.resolve()
    except OSError:
        return False


def _validate_git_state(
    root: Path,
    state: Mapping[str, Any],
    errors: list[str],
    warnings: list[str],
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "checked": True,
        "actual_branch": None,
        "observed_work_branch": None,
        "actual_head_sha": None,
        "control_base_ref_sha": None,
        "control_base_refs": {},
        "base_is_ancestor_of_head": None,
        "worktree_dirty": None,
    }
    inside = _git(root, "rev-parse", "--is-inside-work-tree")
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        errors.append("GIT_NOT_A_WORKTREE")
        return report

    head_result = _git(root, "rev-parse", "HEAD")
    if (
        head_result.returncode != 0
        or FULL_GIT_SHA.fullmatch(head_result.stdout.strip()) is None
    ):
        errors.append("GIT_HEAD_UNRESOLVED")
        return report
    actual_head = head_result.stdout.strip()
    report["actual_head_sha"] = actual_head

    branch_result = _git(root, "symbolic-ref", "--quiet", "--short", "HEAD")
    actual_branch = branch_result.stdout.strip() if branch_result.returncode == 0 else None
    report["actual_branch"] = actual_branch

    use_github_environment = _github_environment_matches_root(root)
    github_head_ref = (
        os.environ.get("GITHUB_HEAD_REF", "").strip()
        if use_github_environment
        else ""
    )
    github_ref = (
        os.environ.get("GITHUB_REF", "").strip()
        if use_github_environment
        else ""
    )
    event = _github_event() if use_github_environment else None
    pull_request = event.get("pull_request") if isinstance(event, dict) else None
    event_head_sha: str | None = None
    if isinstance(pull_request, dict):
        event_head = pull_request.get("head")
        if isinstance(event_head, dict):
            candidate = event_head.get("sha")
            if isinstance(candidate, str) and FULL_GIT_SHA.fullmatch(candidate):
                event_head_sha = candidate
    github_push_branch = (
        github_ref.removeprefix("refs/heads/")
        if github_ref.startswith("refs/heads/")
        else ""
    )
    observed_branch = github_head_ref or github_push_branch or actual_branch
    report["observed_work_branch"] = observed_branch
    expected_branch = state.get("work_branch")
    if observed_branch != expected_branch:
        errors.append(
            f"GIT_WORK_BRANCH_MISMATCH:{observed_branch or 'DETACHED'}:{expected_branch}"
        )

    github_sha = (
        os.environ.get("GITHUB_SHA", "").strip()
        if use_github_environment
        else ""
    )
    expected_checkout_sha = event_head_sha or github_sha
    if expected_checkout_sha and expected_checkout_sha != actual_head:
        errors.append(
            f"GIT_HEAD_ENV_MISMATCH:{actual_head}:{expected_checkout_sha}"
        )

    base_branch = str(state.get("control_base_branch", ""))
    base_sha = str(state.get("control_base_sha", ""))
    base_ref_sha: str | None = None
    base_refs: dict[str, str] = {}
    for label, ref in (
        (f"origin/{base_branch}", f"refs/remotes/origin/{base_branch}"),
        (base_branch, f"refs/heads/{base_branch}"),
    ):
        result = _git(root, "rev-parse", "--verify", ref)
        candidate = result.stdout.strip()
        if result.returncode == 0 and FULL_GIT_SHA.fullmatch(candidate):
            base_refs[label] = candidate
            if base_ref_sha is None:
                base_ref_sha = candidate
            if candidate != base_sha:
                errors.append(
                    f"GIT_BASE_REF_MOVED:{label}:{candidate}:{base_sha}"
                )

    if isinstance(pull_request, dict):
        base = pull_request.get("base")
        head = pull_request.get("head")
        if isinstance(base, dict):
            event_base_ref = base.get("ref")
            event_base_sha = base.get("sha")
            if event_base_ref != base_branch:
                errors.append(
                    f"GIT_EVENT_BASE_BRANCH_MISMATCH:{event_base_ref}:{base_branch}"
                )
            if event_base_sha != base_sha:
                errors.append(
                    f"GIT_EVENT_BASE_SHA_MISMATCH:{event_base_sha}:{base_sha}"
                )
            if isinstance(event_base_sha, str):
                base_ref_sha = event_base_sha
        if isinstance(head, dict):
            event_head_ref = head.get("ref")
            event_head_sha_value = head.get("sha")
            if event_head_ref != expected_branch:
                errors.append(
                    f"GIT_EVENT_HEAD_BRANCH_MISMATCH:{event_head_ref}:{expected_branch}"
                )
            if not isinstance(event_head_sha_value, str) or FULL_GIT_SHA.fullmatch(
                event_head_sha_value
            ) is None:
                errors.append("GIT_EVENT_HEAD_SHA_INVALID")

    report["control_base_ref_sha"] = base_ref_sha
    report["control_base_refs"] = base_refs
    if base_ref_sha is None:
        warnings.append("GIT_BASE_REF_UNAVAILABLE_SHALLOW_CHECKOUT")
    elif base_ref_sha != base_sha and not base_refs:
        errors.append(f"GIT_BASE_REF_MOVED:{base_branch}:{base_ref_sha}:{base_sha}")

    effective_head = event_head_sha or actual_head
    base_object = _git(root, "cat-file", "-e", f"{base_sha}^{{commit}}")
    head_object = _git(root, "cat-file", "-e", f"{effective_head}^{{commit}}")
    if base_object.returncode != 0 or head_object.returncode != 0:
        warnings.append("GIT_ANCESTRY_UNAVAILABLE_SHALLOW_CHECKOUT")
    else:
        ancestor = _git(root, "merge-base", "--is-ancestor", base_sha, effective_head)
        report["base_is_ancestor_of_head"] = ancestor.returncode == 0
        if ancestor.returncode != 0:
            errors.append(f"GIT_BASE_NOT_ANCESTOR_OF_HEAD:{base_sha}:{effective_head}")

    status = _git(root, "status", "--porcelain")
    if status.returncode == 0:
        report["worktree_dirty"] = bool(status.stdout)
        if status.stdout:
            warnings.append("GIT_WORKTREE_DIRTY")
    else:
        warnings.append("GIT_WORKTREE_STATUS_UNAVAILABLE")
    return report


def validate(root: Path, *, check_git: bool = True) -> dict[str, Any]:
    root = root.resolve()
    errors: list[str] = []
    warnings: list[str] = []

    for relative in REQUIRED_FILES:
        path = root / relative
        if not path.is_file() or path.is_symlink():
            errors.append(f"MISSING_OR_UNSAFE_REQUIRED_FILE:{relative}")

    state: dict[str, Any] = {}
    state_path = root / CONTROL_STATE_FILE
    if state_path.is_file() and not state_path.is_symlink():
        try:
            state = _load_json(state_path)
        except ValueError as exc:
            errors.append(f"CONTROL_STATE_READ:{exc}")
    _validate_control_state(state, errors)

    task_path = root / "docs/codex/CURRENT_TASK.md"
    metadata: dict[str, str] = {}
    task_text = ""
    if task_path.is_file() and not task_path.is_symlink():
        try:
            task_text = _read(task_path)
            metadata = _metadata(task_text)
        except ValueError as exc:
            errors.append(f"CURRENT_TASK_READ:{exc}")
        missing_metadata = sorted(set(REQUIRED_METADATA) - set(metadata))
        if missing_metadata:
            errors.append("CURRENT_TASK_METADATA_MISSING:" + ",".join(missing_metadata))
        if metadata.get("STATUS") not in ALLOWED_TASK_STATUSES:
            errors.append("CURRENT_TASK_STATUS_INVALID")
        if metadata.get("REPOSITORY") != "mohsamir7122/ku-bo":
            errors.append("CURRENT_TASK_REPOSITORY_MISMATCH")
        if metadata.get("CONTROL_STATE_FILE") != CONTROL_STATE_FILE:
            errors.append("CURRENT_TASK_CONTROL_STATE_FILE_MISMATCH")
        if metadata.get("EXPECTED_PR_MODE") != "DRAFT":
            errors.append("CURRENT_TASK_PR_MODE_MUST_BE_DRAFT")
        for key in MUST_BE_NO:
            if metadata.get(key) != "NO":
                errors.append(f"CURRENT_TASK_UNSAFE_PERMISSION:{key}")
        if metadata.get("MANUAL_CANARY_ALLOWED") != "YES":
            errors.append("CURRENT_TASK_MANUAL_CANARY_MUST_BE_YES")
        for marker in (
            "docs/codex/HANDOFF_TEMPLATE.md",
            "docs/codex/USER_DECISIONS.md",
            "Do not merge",
            "REAL_BACKTEST_ALLOWED: NO",
        ):
            if marker not in task_text:
                errors.append(f"CURRENT_TASK_REQUIRED_MARKER_MISSING:{marker}")

    for metadata_key, state_key in TASK_STATE_FIELDS.items():
        if metadata.get(metadata_key) != state.get(state_key):
            errors.append(f"CONTROL_STATE_TASK_MISMATCH:{metadata_key}")
    permissions = state.get("permissions") if isinstance(state.get("permissions"), dict) else {}
    for metadata_key, state_key in PERMISSION_STATE_FIELDS.items():
        if metadata.get(metadata_key) != _yes_no(permissions.get(state_key)):
            errors.append(f"CONTROL_STATE_TASK_MISMATCH:{metadata_key}")
    claims = state.get("claim_boundaries") if isinstance(state.get("claim_boundaries"), dict) else {}
    for metadata_key, state_key in CLAIM_STATE_FIELDS.items():
        if metadata.get(metadata_key) != _yes_no(claims.get(state_key)):
            errors.append(f"CONTROL_STATE_TASK_MISMATCH:{metadata_key}")

    mirror_markers = (
        CONTROL_STATE_FILE,
        str(state.get("task_id", "")),
        str(state.get("control_base_sha", "")),
        str(state.get("work_branch", "")),
    )
    for relative in TEXT_STATE_MIRRORS:
        path = root / relative
        if not path.is_file() or path.is_symlink():
            continue
        text = _read(path)
        for marker in mirror_markers:
            if not marker or marker not in text:
                errors.append(f"CONTROL_STATE_TEXT_MIRROR_MISMATCH:{relative}:{marker}")

    progress_path = root / "PROGRESS.json"
    if progress_path.is_file() and not progress_path.is_symlink():
        try:
            progress = _load_json(progress_path)
        except ValueError as exc:
            errors.append(f"PROGRESS_READ:{exc}")
            progress = {}
        if progress.get("canonical_control_state") != CONTROL_STATE_FILE:
            errors.append("PROGRESS_CONTROL_STATE_FILE_MISMATCH")
        active = progress.get("active_control")
        if not isinstance(active, dict):
            errors.append("PROGRESS_ACTIVE_CONTROL_INVALID")
            active = {}
        progress_fields = {
            "task_id": state.get("task_id"),
            "status": state.get("status"),
            "control_base_branch": state.get("control_base_branch"),
            "control_base_sha": state.get("control_base_sha"),
            "work_branch": state.get("work_branch"),
            "pr_mode": state.get("pr_mode"),
            "automatic_schedules_allowed": permissions.get("automatic_schedules_allowed"),
            "manual_canary_allowed": permissions.get("manual_canary_allowed"),
            "live_operational_claim_allowed": claims.get("live_operational_claim_allowed"),
            "predictive_claim_allowed": claims.get("predictive_claim_allowed"),
        }
        for key, expected in progress_fields.items():
            if active.get(key) != expected:
                errors.append(f"PROGRESS_ACTIVE_CONTROL_MISMATCH:{key}")

    checked_text_files = 0
    for relative in ("CODEX_START_HERE.md", "AGENTS.md", "docs/codex"):
        path = root / relative
        candidates = (
            [path]
            if path.is_file()
            else sorted(path.rglob("*.md"))
            if path.is_dir()
            else []
        )
        for candidate in candidates:
            if candidate.is_symlink() or not candidate.is_file():
                errors.append(
                    "CODEX_CONTROL_UNSAFE_FILE:"
                    + candidate.relative_to(root).as_posix()
                )
                continue
            checked_text_files += 1
            text = _read(candidate)
            if PRIVATE_GOOGLE_URL.search(text):
                errors.append(
                    "PRIVATE_GOOGLE_URL_COMMITTED:"
                    + candidate.relative_to(root).as_posix()
                )

    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            continue
        lowered_parts = {part.casefold() for part in path.relative_to(root).parts}
        if lowered_parts & FORBIDDEN_REPOSITORY_PATH_PARTS:
            errors.append(
                "RAW_CONVERSATION_PATH_FORBIDDEN:"
                + path.relative_to(root).as_posix()
            )

    handoff_dir = root / "docs/codex/handoffs"
    if not handoff_dir.exists():
        warnings.append("HANDOFF_DIRECTORY_WILL_BE_CREATED_BY_FIRST_TASK")

    git_state: dict[str, Any] = {"checked": False}
    if check_git:
        git_state = _validate_git_state(root, state, errors, warnings)

    return {
        "schema_version": "2.0",
        "status": "PASS" if not errors else "FAIL",
        "control_state_file": CONTROL_STATE_FILE,
        "task_id": state.get("task_id"),
        "task_status": state.get("status"),
        "expected_branch": state.get("work_branch"),
        "control_base_branch": state.get("control_base_branch"),
        "control_base_sha": state.get("control_base_sha"),
        "git_state": git_state,
        "checked_required_files": len(REQUIRED_FILES),
        "checked_control_text_files": checked_text_files,
        "errors": sorted(set(errors)),
        "warnings": sorted(set(warnings)),
        "claim_boundaries": {
            "control_check_authorizes_merge": False,
            "control_check_authorizes_deletion": False,
            "control_check_proves_market_data": False,
            "control_check_proves_backtest_readiness": False,
            "control_check_proves_live_operation": False,
            "control_check_proves_predictive_skill": False,
        },
    }


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(
        description="Validate KU-BO canonical control, mirrors, and live Git state"
    )
    value.add_argument("--root", type=Path, default=Path.cwd())
    return value


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    report = validate(args.root)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
