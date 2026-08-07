from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .catalog import Catalog
from .strict import parse_aware


ACCESS_STATES = frozenset({"UNTESTED", "AVAILABLE", "PARTIAL", "BLOCKED", "EMPTY", "ERROR", "PARSER_DRIFT", "AUTH_REQUIRED"})


@dataclass(frozen=True)
class SourceAccessResult:
    status: str
    states: dict[str, str]
    errors: tuple[str, ...]


def load_source_access(path: Path | None, catalog: Catalog) -> SourceAccessResult:
    default = {source_id: "UNTESTED" for source_id in catalog.sources}
    if path is None or not path.is_file():
        return SourceAccessResult("UNTESTED", default, ())
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return SourceAccessResult("BLOCKED", default, (f"INVALID_SOURCE_ACCESS_REPORT:{exc}",))
    errors: list[str] = []
    states = dict(default)
    try:
        parse_aware(payload.get("observed_at"), "observed_at")
    except ValueError as exc:
        errors.append(str(exc))
    rows = payload.get("sources")
    if not isinstance(rows, list):
        errors.append("sources must be a list")
        rows = []
    seen: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"source_{index}:NOT_OBJECT")
            continue
        source_id = str(row.get("source_id", ""))
        state = str(row.get("state", "")).upper()
        if source_id not in catalog.sources or source_id in seen:
            errors.append(f"source_{index}:UNKNOWN_OR_DUPLICATE")
            continue
        if state not in ACCESS_STATES:
            errors.append(f"source_{index}:INVALID_STATE")
            continue
        seen.add(source_id)
        states[source_id] = state
    return SourceAccessResult("PASS" if not errors else "BLOCKED", states, tuple(errors))


__all__ = ["ACCESS_STATES", "SourceAccessResult", "load_source_access"]
