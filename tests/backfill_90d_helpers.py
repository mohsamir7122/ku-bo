from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any

from kubo.backfill_90d import build_rights_aware_bundle
from kubo.hashing import canonical_json_bytes
from kubo.ingestion import CaptureResult
from kubo.source_access_executor import execute_public_source_probe
from kubo.source_access_recipes import (
    SourceAccessRecipeCatalog,
    compile_source_probe_plan,
)
from kubo.source_network import SourceNetworkCatalog


ROOT = Path(__file__).resolve().parents[1]
PLANNED_AT = datetime.fromisoformat("2026-08-27T06:00:00+03:00")
RUN_AT = datetime.fromisoformat("2026-08-27T06:05:00+03:00")
FINISHED_AT = datetime.fromisoformat("2026-08-27T03:10:00+00:00")
CODE_SHA = "a" * 40


class FixtureConnector:
    def __init__(self, *, readable: bool = False) -> None:
        self.readable = readable
        self.calls: list[Any] = []

    def capture(self, request: Any) -> CaptureResult:
        self.calls.append(request)
        if self.readable:
            return CaptureResult(
                source_id=request.source_id,
                source_url=request.source_url,
                final_url=request.source_url,
                access_mode=request.access_mode,
                capture_kind=request.capture_kind,
                roles_observed=request.roles_observed,
                attempted_at=RUN_AT,
                observed_at=RUN_AT,
                state="AVAILABLE",
                query_status="DATA_QUALITY_REJECTED",
                qualified_items=0,
                zero_result=False,
                content=b"synthetic contract fixture; not market data",
                content_type="text/plain",
                http_status=200,
                error_code="",
                data_quality_flags=("RAW_CAPTURE_PENDING_PARSER_VALIDATION",),
                limitations=("SYNTHETIC_CONTRACT_ONLY",),
            )
        return CaptureResult(
            source_id=request.source_id,
            source_url=request.source_url,
            final_url=request.source_url,
            access_mode=request.access_mode,
            capture_kind=request.capture_kind,
            roles_observed=request.roles_observed,
            attempted_at=RUN_AT,
            observed_at=None,
            state="BLOCKED",
            query_status="BLOCKED",
            qualified_items=0,
            zero_result=False,
            content=None,
            content_type="",
            http_status=403,
            error_code="HTTP_FORBIDDEN",
            data_quality_flags=(),
            limitations=(),
        )


def make_receipt(
    directory: Path,
    *,
    source_id: str = "kcc_maqasa_official",
    readable: bool = False,
) -> tuple[Path, Path]:
    network = SourceNetworkCatalog(ROOT / "config")
    recipes = SourceAccessRecipeCatalog(
        ROOT / "config/source_access_recipes.json", network
    )
    plan_payload = compile_source_probe_plan(
        recipes,
        network,
        planned_at=PLANNED_AT,
        source_ids=[source_id],
    )
    plan_path = directory / f"{source_id}-plan.json"
    plan_path.write_bytes(canonical_json_bytes(plan_payload))
    output = directory / f"{source_id}-probe"
    connector = FixtureConnector(readable=readable)
    report = execute_public_source_probe(
        plan_path=plan_path,
        output_root=output,
        recipes=recipes,
        source_catalog=network,
        connector=connector,
        clock=lambda: RUN_AT,
    )
    if report["status"] != "PASS_ACCESS_ONLY" or len(connector.calls) != 1:
        raise AssertionError("synthetic source receipt fixture did not validate")
    return plan_path, output / "access-probe.json"


def build_fixture_bundle(
    directory: Path,
    *,
    receipt_bindings: list[tuple[Path, Path]] | None = None,
    output_name: str = "bundle",
) -> tuple[Path, dict[str, Any]]:
    bindings = (
        [make_receipt(directory)]
        if receipt_bindings is None
        else receipt_bindings
    )
    output = directory / output_name
    report = build_rights_aware_bundle(
        ROOT,
        output,
        run_id="fixture-run",
        code_sha=CODE_SHA,
        scheduled_at="2026-08-27T03:00:00Z",
        actual_started_at="2026-08-27T03:01:00Z",
        finished_at=FINISHED_AT,
        receipt_bindings=bindings,
    )
    return output, report


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AssertionError(f"{path} did not contain an object")
    return value


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.read_bytes():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
