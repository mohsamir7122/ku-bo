from __future__ import annotations

from pathlib import Path
from typing import Any

from .capture_plan import MAX_CAPTURE_PLAN_TASKS
from .hashing import canonical_json_bytes
from .symbol_mapping import SymbolMappingCatalog


DEFAULT_LIVE_PILOT_CAPTURE_BYTES = 5 * 1024 * 1024
DEFAULT_LIVE_PILOT_TIMEOUT_SECONDS = 20.0
MAX_LIVE_PILOT_CAPTURE_TASKS = MAX_CAPTURE_PLAN_TASKS


def build_investing_seed_capture_plan(
    catalog: SymbolMappingCatalog,
    *,
    max_bytes: int = DEFAULT_LIVE_PILOT_CAPTURE_BYTES,
    timeout_seconds: float = DEFAULT_LIVE_PILOT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    candidates = catalog.capture_candidates()
    if len(candidates) > MAX_LIVE_PILOT_CAPTURE_TASKS:
        raise ValueError(
            "live-pilot capture plan exceeds the explicit limit of "
            f"{MAX_LIVE_PILOT_CAPTURE_TASKS} tasks; split it into batches"
        )
    tasks = []
    for mapping in candidates:
        tasks.append(
            {
                "connector": "public_http",
                "source_id": "investing_history",
                "source_url": mapping.investing_url,
                "roles_observed": ["MARKET_DISCOVERY", "PRICE_HISTORY"],
                "access_mode": "PUBLIC_PAGE",
                "capture_kind": "RAW_PAGE",
                "timeout_seconds": timeout_seconds,
                "max_bytes": max_bytes,
            }
        )
    if not tasks:
        raise ValueError("symbol mapping has no Investing capture candidates")
    return {
        "schema_version": "1.0",
        "tasks": tasks,
    }


def write_investing_seed_capture_plan(config_dir: Path, output_path: Path) -> dict[str, Any]:
    catalog = SymbolMappingCatalog(config_dir)
    candidates = catalog.capture_candidates()
    plan = build_investing_seed_capture_plan(catalog)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(canonical_json_bytes(plan))
    return {
        "status": "PASS",
        "output": str(output_path),
        "task_count": len(plan["tasks"]),
        "symbols": [mapping.boursa_symbol for mapping in candidates],
    }


__all__ = [
    "DEFAULT_LIVE_PILOT_CAPTURE_BYTES",
    "DEFAULT_LIVE_PILOT_TIMEOUT_SECONDS",
    "MAX_LIVE_PILOT_CAPTURE_TASKS",
    "build_investing_seed_capture_plan",
    "write_investing_seed_capture_plan",
]
