from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any


REQUIRED_FILES = (
    "AGENTS.md",
    "CODEX_START_HERE.md",
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
    "CONTROL_BASE_BRANCH",
    "EXPECTED_NEW_BRANCH",
    "EXPECTED_PR_MODE",
    "MERGE_ALLOWED",
    "FORCE_PUSH_ALLOWED",
    "PERMANENT_DELETE_ALLOWED",
    "REAL_DATA_COMMIT_ALLOWED",
    "PRIVATE_CONVERSATION_COMMIT_ALLOWED",
    "MODEL_TRAINING_ALLOWED",
    "REAL_BACKTEST_ALLOWED",
)
MUST_BE_NO = (
    "MERGE_ALLOWED",
    "FORCE_PUSH_ALLOWED",
    "PERMANENT_DELETE_ALLOWED",
    "REAL_DATA_COMMIT_ALLOWED",
    "PRIVATE_CONVERSATION_COMMIT_ALLOWED",
    "MODEL_TRAINING_ALLOWED",
    "REAL_BACKTEST_ALLOWED",
)
ALLOWED_TASK_STATUSES = frozenset(
    {"READY", "IN_PROGRESS", "BLOCKED", "COMPLETED", "SUPERSEDED"}
)
PRIVATE_GOOGLE_URL = re.compile(
    r"https://(?:drive|docs)\.google\.com/(?:drive/folders|document/d|spreadsheets/d|presentation/d)/[A-Za-z0-9_-]+",
    flags=re.IGNORECASE,
)
FORBIDDEN_REPOSITORY_PATH_PARTS = frozenset(
    {
        "raw_conversations",
        "private_conversations",
        "conversation_transcripts",
        "chat_exports",
        "chat_transcripts",
    }
)


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"cannot read UTF-8 text file: {path}") from exc


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


def validate(root: Path) -> dict[str, Any]:
    root = root.resolve()
    errors: list[str] = []
    warnings: list[str] = []

    for relative in REQUIRED_FILES:
        path = root / relative
        if not path.is_file() or path.is_symlink():
            errors.append(f"MISSING_OR_UNSAFE_REQUIRED_FILE:{relative}")

    task_path = root / "docs/codex/CURRENT_TASK.md"
    metadata: dict[str, str] = {}
    if task_path.is_file() and not task_path.is_symlink():
        try:
            task_text = _read(task_path)
            metadata = _metadata(task_text)
        except ValueError as exc:
            errors.append(f"CURRENT_TASK_READ:{exc}")
            task_text = ""
        missing_metadata = sorted(set(REQUIRED_METADATA) - set(metadata))
        if missing_metadata:
            errors.append("CURRENT_TASK_METADATA_MISSING:" + ",".join(missing_metadata))
        if metadata.get("STATUS") not in ALLOWED_TASK_STATUSES:
            errors.append("CURRENT_TASK_STATUS_INVALID")
        if metadata.get("REPOSITORY") != "mohsamir7122/ku-bo":
            errors.append("CURRENT_TASK_REPOSITORY_MISMATCH")
        if metadata.get("EXPECTED_PR_MODE") != "DRAFT":
            errors.append("CURRENT_TASK_PR_MODE_MUST_BE_DRAFT")
        for key in MUST_BE_NO:
            if metadata.get(key) != "NO":
                errors.append(f"CURRENT_TASK_UNSAFE_PERMISSION:{key}")
        for marker in (
            "docs/codex/HANDOFF_TEMPLATE.md",
            "docs/codex/USER_DECISIONS.md",
            "Do not merge",
            "REAL_BACKTEST_ALLOWED: NO",
        ):
            if marker not in task_text:
                errors.append(f"CURRENT_TASK_REQUIRED_MARKER_MISSING:{marker}")

    checked_text_files = 0
    for relative in (
        "CODEX_START_HERE.md",
        "AGENTS.md",
        "docs/codex",
    ):
        path = root / relative
        candidates = [path] if path.is_file() else sorted(path.rglob("*.md")) if path.is_dir() else []
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

    return {
        "schema_version": "1.0",
        "status": "PASS" if not errors else "FAIL",
        "task_id": metadata.get("TASK_ID"),
        "task_status": metadata.get("STATUS"),
        "expected_branch": metadata.get("EXPECTED_NEW_BRANCH"),
        "checked_required_files": len(REQUIRED_FILES),
        "checked_control_text_files": checked_text_files,
        "errors": sorted(set(errors)),
        "warnings": sorted(set(warnings)),
        "claim_boundaries": {
            "control_check_authorizes_merge": False,
            "control_check_authorizes_deletion": False,
            "control_check_proves_market_data": False,
            "control_check_proves_backtest_readiness": False,
        },
    }


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(
        description="Validate KU-BO repository-native Codex control files"
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
