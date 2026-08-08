from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import Any

from .hashing import canonical_json_bytes, sha256_bytes
from .source_network import SourceNetworkCatalog, SourceNetworkRunValidator
from .source_parsers import (
    PARSER_SOURCE_IDS,
    investing_price_finding,
    parse_boursa_identity_html,
    parse_investing_history_html,
)
from .strict import https_url, parse_aware, parse_iso_date, require_sha256, resolved_regular_file, safe_relative_path


PARSER_PLAN_FIELDS = {
    "schema_version",
    "run_id",
    "product_id",
    "decision_at",
    "scope",
    "budget",
    "usage_wall_seconds",
    "bindings",
    "parser_tasks",
}
BINDING_FIELDS = {
    "security_code",
    "ticker",
    "isin",
    "valid_from",
    "valid_to",
    "official_artifact_sha256",
    "secondary_artifact_sha256",
}
TASK_FIELDS = {"parser_id", "artifact_sha256"}


def _load_object(path: Path, field: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{field} must be UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{field} must be a JSON object")
    return payload


def _ticker(value: Any) -> str:
    ticker = str(value or "").upper()
    if not 1 <= len(ticker) <= 32 or any(
        not (character.isalnum() or character in "._-") for character in ticker
    ):
        raise ValueError("ticker must contain 1..32 alphanumeric or ._- characters")
    return ticker


def _isin(value: Any) -> str:
    isin = str(value or "").upper()
    if len(isin) != 12 or not isin[:2].isalpha() or not isin[2:].isalnum() or not isin[-1].isdigit():
        raise ValueError("isin must be a 12-character ISIN")
    return isin


def _artifact_index(
    capture_root: Path,
    manifest: dict[str, Any],
    catalog: SourceNetworkCatalog,
    *,
    max_requests: int,
    max_raw_bytes: int,
) -> dict[tuple[str, str], dict[str, Any]]:
    if manifest.get("schema_version") != "3.0" or not isinstance(manifest.get("artifacts"), list):
        raise ValueError("capture manifest must use schema_version 3.0")
    if len(manifest["artifacts"]) > max_requests:
        raise ValueError("capture manifest exceeds parser-plan request budget")
    declared_total = 0
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for index, row in enumerate(manifest["artifacts"]):
        if not isinstance(row, dict):
            raise ValueError(f"manifest artifact {index} must be an object")
        source_id = str(row.get("source_id", ""))
        if source_id not in catalog.sources:
            raise ValueError(f"manifest artifact {index} references an unknown source")
        relative = safe_relative_path(row.get("path"), f"artifacts[{index}].path")
        if not relative.parts or relative.parts[0] != "raw":
            raise ValueError("parser artifacts must remain inside raw/")
        target = resolved_regular_file(
            capture_root, relative, f"manifest artifact {index} path"
        )
        digest = require_sha256(row.get("sha256"), f"artifacts[{index}].sha256")
        size = row.get("size_bytes")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise ValueError(f"manifest artifact {index} size is invalid")
        declared_total += size
        if declared_total > max_raw_bytes:
            raise ValueError("capture manifest exceeds parser-plan raw-byte budget")
        if target.stat().st_size != size:
            raise ValueError(f"manifest artifact {index} bytes do not match the manifest")
        content = target.read_bytes()
        if sha256_bytes(content) != digest:
            raise ValueError(f"manifest artifact {index} bytes do not match the manifest")
        source_url = https_url(row.get("source_url"), f"artifacts[{index}].source_url")
        observed_at = parse_aware(row.get("observed_at"), f"artifacts[{index}].observed_at")
        key = (source_id, digest)
        if key in result:
            raise ValueError("parser materialization requires unique source/hash artifacts")
        result[key] = {
            **row,
            "path_object": target,
            "source_url": source_url,
            "observed_datetime": observed_at,
            "content": content,
        }
    if not result:
        raise ValueError("capture manifest contains no artifacts")
    return result


def _validate_plan(plan: dict[str, Any], catalog: SourceNetworkCatalog) -> tuple[Any, list[dict[str, Any]], list[dict[str, str]]]:
    if set(plan) != PARSER_PLAN_FIELDS or plan.get("schema_version") != "1.0":
        raise ValueError("parser plan has unknown/missing fields or unsupported schema_version")
    run_id = str(plan.get("run_id", "")).strip()
    product_id = str(plan.get("product_id", "")).strip()
    if not run_id or product_id not in catalog.product_to_policy:
        raise ValueError("parser plan run_id/product_id is invalid")
    decision_at = parse_aware(plan.get("decision_at"), "decision_at")
    if str(plan.get("scope")) not in {"NAMED_SECURITIES", "CANDIDATE_SET"}:
        raise ValueError("parser materialization supports NAMED_SECURITIES or CANDIDATE_SET only")
    budget = plan.get("budget")
    if not isinstance(budget, dict) or set(budget) != {"max_requests", "max_raw_bytes", "max_wall_seconds"}:
        raise ValueError("parser plan budget is invalid")
    for key, value in budget.items():
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"budget.{key} must be a positive integer")
    wall_seconds = plan.get("usage_wall_seconds")
    if isinstance(wall_seconds, bool) or not isinstance(wall_seconds, int) or wall_seconds < 0:
        raise ValueError("usage_wall_seconds must be a non-negative integer")

    raw_bindings = plan.get("bindings")
    raw_tasks = plan.get("parser_tasks")
    if not isinstance(raw_bindings, list) or not raw_bindings:
        raise ValueError("parser plan bindings must be non-empty")
    if not isinstance(raw_tasks, list) or not raw_tasks:
        raise ValueError("parser plan parser_tasks must be non-empty")
    bindings: list[dict[str, Any]] = []
    seen_codes: set[str] = set()
    seen_isins: set[str] = set()
    seen_tickers: set[str] = set()
    for index, row in enumerate(raw_bindings):
        if not isinstance(row, dict) or set(row) != BINDING_FIELDS:
            raise ValueError(f"binding {index} has unknown or missing fields")
        code = str(row.get("security_code", ""))
        ticker = _ticker(row.get("ticker"))
        isin = _isin(row.get("isin"))
        valid_from = parse_iso_date(row.get("valid_from"), f"bindings[{index}].valid_from")
        valid_to_value = row.get("valid_to")
        valid_to = None if valid_to_value is None else parse_iso_date(valid_to_value, f"bindings[{index}].valid_to")
        if not code.isdigit() or code in seen_codes or ticker in seen_tickers or isin in seen_isins:
            raise ValueError("binding identities must be unique and security_code must be numeric")
        if valid_from > decision_at.date() or (valid_to is not None and (valid_to < valid_from or valid_to < decision_at.date())):
            raise ValueError("binding validity does not contain decision_at")
        seen_codes.add(code)
        seen_tickers.add(ticker)
        seen_isins.add(isin)
        bindings.append(
            {
                "security_code": code,
                "ticker": ticker,
                "isin": isin,
                "valid_from": valid_from.isoformat(),
                "valid_to": None if valid_to is None else valid_to.isoformat(),
                "official_artifact_sha256": require_sha256(
                    row.get("official_artifact_sha256"),
                    f"bindings[{index}].official_artifact_sha256",
                ),
                "secondary_artifact_sha256": require_sha256(
                    row.get("secondary_artifact_sha256"),
                    f"bindings[{index}].secondary_artifact_sha256",
                ),
            }
        )
    tasks: list[dict[str, str]] = []
    seen_tasks: set[tuple[str, str]] = set()
    for index, row in enumerate(raw_tasks):
        if not isinstance(row, dict) or set(row) != TASK_FIELDS:
            raise ValueError(f"parser task {index} has unknown or missing fields")
        parser_id = str(row.get("parser_id", ""))
        if parser_id not in PARSER_SOURCE_IDS:
            raise ValueError(f"parser task {index} references an unsupported parser")
        source_id = PARSER_SOURCE_IDS[parser_id]
        if parser_id not in catalog.capabilities[source_id].parser_ids:
            raise ValueError(f"parser task {index} is outside the capability matrix")
        digest = require_sha256(row.get("artifact_sha256"), f"parser_tasks[{index}].artifact_sha256")
        key = (parser_id, digest)
        if key in seen_tasks:
            raise ValueError("duplicate parser task")
        seen_tasks.add(key)
        tasks.append({"parser_id": parser_id, "source_id": source_id, "artifact_sha256": digest})
    if sum(task["parser_id"] == "boursa_identity_html_v1" for task in tasks) != 1:
        raise ValueError("exactly one Boursa identity parser task is required")
    return decision_at, bindings, tasks


def _atomic_write(path: Path, content: bytes) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def materialize_parser_run(
    *,
    capture_root: Path,
    parser_plan_path: Path,
    catalog: SourceNetworkCatalog,
) -> dict[str, Any]:
    """Turn bounded captured bytes into a validator-ready research run.

    This command is intentionally narrow: it reconciles official Boursa
    code/ISIN rows with Investing ticker/ISIN rows, then creates only a
    secondary price-history finding. It never classifies news, creates an
    official catalyst, or upgrades the source to live-operational status.
    """

    capture_root = Path(capture_root).resolve()
    if not capture_root.is_dir() or capture_root == Path(capture_root.anchor):
        raise ValueError("capture_root must be an existing non-root directory")
    generated_paths = [
        capture_root / "research_run.json",
        capture_root / "universe.json",
        capture_root / "findings.jsonl",
    ]
    if any(path.exists() for path in generated_paths):
        raise ValueError("capture_root already contains materialized research files")
    manifest = _load_object(capture_root / "manifest.json", "capture manifest")
    observations_payload = _load_object(
        capture_root / "source_observations.json", "capture observations"
    )
    if observations_payload.get("schema_version") != "3.0" or not isinstance(
        observations_payload.get("sources"), list
    ):
        raise ValueError("capture observations must use schema_version 3.0")
    try:
        plan_bytes = parser_plan_path.read_bytes()
        plan = json.loads(plan_bytes.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("parser plan must be UTF-8 JSON") from exc
    if not isinstance(plan, dict):
        raise ValueError("parser plan must be a JSON object")
    decision_at, bindings, tasks = _validate_plan(plan, catalog)
    artifacts = _artifact_index(
        capture_root,
        manifest,
        catalog,
        max_requests=plan["budget"]["max_requests"],
        max_raw_bytes=plan["budget"]["max_raw_bytes"],
    )
    if any(item["observed_datetime"] > decision_at for item in artifacts.values()):
        raise ValueError("capture artifact was observed after decision_at")
    plan_hash = sha256_bytes(plan_bytes)

    identities_by_artifact: dict[str, dict[str, Any]] = {}
    instruments_by_artifact: dict[str, Any] = {}
    parser_rows_by_source: dict[str, int] = {}
    parser_ids_by_source: dict[str, set[str]] = {}
    for task in tasks:
        key = (task["source_id"], task["artifact_sha256"])
        artifact = artifacts.get(key)
        if artifact is None:
            raise ValueError("parser task artifact is unresolved for the required source")
        content = artifact["content"]
        parser_ids_by_source.setdefault(task["source_id"], set()).add(task["parser_id"])
        if task["parser_id"] == "boursa_identity_html_v1":
            rows = parse_boursa_identity_html(content)
            identities_by_artifact[task["artifact_sha256"]] = {
                row.security_code: row for row in rows
            }
            parser_rows_by_source[task["source_id"]] = len(rows)
        elif task["parser_id"] == "investing_history_html_v1":
            instrument = parse_investing_history_html(content)
            instruments_by_artifact[task["artifact_sha256"]] = instrument
            parser_rows_by_source[task["source_id"]] = (
                parser_rows_by_source.get(task["source_id"], 0) + len(instrument.rows)
            )

    official_hashes = {binding["official_artifact_sha256"] for binding in bindings}
    if len(official_hashes) != 1 or not official_hashes <= set(identities_by_artifact):
        raise ValueError("all bindings must resolve through one parsed official membership artifact")
    official_hash = next(iter(official_hashes))
    official_artifact = artifacts.get(("boursa_current", official_hash))
    if official_artifact is None:
        raise ValueError("official membership artifact is unresolved")
    official_identities = identities_by_artifact[official_hash]

    findings: list[dict[str, Any]] = []
    securities: list[dict[str, Any]] = []
    for binding in bindings:
        official = official_identities.get(binding["security_code"])
        instrument = instruments_by_artifact.get(binding["secondary_artifact_sha256"])
        if official is None or official.isin != binding["isin"]:
            raise ValueError("official security-code/ISIN binding does not match captured Boursa bytes")
        if instrument is None or instrument.isin != binding["isin"] or instrument.ticker != binding["ticker"]:
            raise ValueError("secondary ticker/ISIN binding does not match captured Investing bytes")
        secondary_artifact = artifacts.get(
            ("investing_history", binding["secondary_artifact_sha256"])
        )
        if secondary_artifact is None:
            raise ValueError("secondary binding artifact is unresolved")
        capture_kind = str(secondary_artifact.get("capture_kind", ""))
        capture_mode = "USER_EXPORT" if capture_kind == "USER_EXPORT" else "PROSPECTIVE"
        findings.append(
            investing_price_finding(
                instrument,
                security_code=binding["security_code"],
                source_url=secondary_artifact["source_url"],
                raw_sha256=binding["secondary_artifact_sha256"],
                observed_at=secondary_artifact["observed_datetime"],
                capture_mode=capture_mode,
            )
        )
        securities.append(
            {
                "security_code": binding["security_code"],
                "ticker": binding["ticker"],
                "valid_from": binding["valid_from"],
                "valid_to": binding["valid_to"],
            }
        )

    observation_by_source: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(observations_payload["sources"]):
        if not isinstance(row, dict):
            raise ValueError(f"capture observation {index} must be an object")
        source_id = str(row.get("source_id", ""))
        if source_id in observation_by_source:
            raise ValueError("capture observations contain duplicate sources")
        observation_by_source[source_id] = dict(row)
    for source_id, qualified_items in parser_rows_by_source.items():
        observation = observation_by_source.get(source_id)
        if observation is None:
            raise ValueError("parsed source has no capture observation")
        matching_hashes = sorted(
            digest for artifact_source, digest in artifacts if artifact_source == source_id
        )
        roles = (
            ["IDENTITY_REFERENCE"]
            if source_id == "boursa_current"
            else ["MARKET_DISCOVERY", "PRICE_HISTORY"]
        )
        observation.update(
            {
                "state": "AVAILABLE",
                "query_status": "QUALIFIED",
                "roles_observed": roles,
                "qualified_items": qualified_items,
                "zero_result": False,
                "raw_sha256s": matching_hashes,
                "data_quality_flags": [],
                "limitations": sorted(
                    {
                        f"PARSER_ID:{parser_id}"
                        for parser_id in parser_ids_by_source[source_id]
                    }
                    | {
                        f"PARSER_PLAN_SHA256:{plan_hash}",
                        "PARSER_OUTPUT_REQUIRES_NETWORK_VALIDATION",
                    }
                ),
                "entitlement_id": "",
            }
        )

    codes = sorted((binding["security_code"] for binding in bindings), key=int)
    raw_bytes = sum(int(row["size_bytes"]) for row in manifest["artifacts"])
    requests = len(manifest["artifacts"])
    budget = plan["budget"]
    if requests > budget["max_requests"] or raw_bytes > budget["max_raw_bytes"] or plan["usage_wall_seconds"] > budget["max_wall_seconds"]:
        raise ValueError("materialized run exceeds parser-plan budget")
    research_run = {
        "schema_version": "3.0",
        "run_id": plan["run_id"],
        "product_id": plan["product_id"],
        "decision_at": decision_at.isoformat(),
        "timezone": "Asia/Kuwait",
        "scope": plan["scope"],
        "expected_universe_count": len(codes),
        "covered_universe_count": len(codes),
        "budget": budget,
        "usage": {
            "requests": requests,
            "raw_bytes": raw_bytes,
            "wall_seconds": plan["usage_wall_seconds"],
        },
    }
    universe = {
        "schema_version": "3.0",
        "membership_basis": "POINT_IN_TIME_OFFICIAL",
        "reconciliation_status": "EXACT",
        "expected_security_codes": codes,
        "covered_security_codes": codes,
        "membership_source_id": "boursa_current",
        "membership_raw_sha256": official_hash,
        "membership_as_of": official_artifact["observed_datetime"].isoformat(),
        "securities": sorted(securities, key=lambda item: int(item["security_code"])),
    }
    observations = {
        "schema_version": "3.0",
        "sources": [observation_by_source[key] for key in sorted(observation_by_source)],
    }
    findings_bytes = b"".join(canonical_json_bytes(row) for row in sorted(findings, key=lambda item: item["finding_id"]))
    original_observations = (capture_root / "source_observations.json").read_bytes()
    written: list[Path] = []
    try:
        for path, content in (
            (capture_root / "research_run.json", canonical_json_bytes(research_run)),
            (capture_root / "universe.json", canonical_json_bytes(universe)),
            (capture_root / "findings.jsonl", findings_bytes),
            (capture_root / "source_observations.json", canonical_json_bytes(observations)),
        ):
            _atomic_write(path, content)
            written.append(path)
        validation = SourceNetworkRunValidator(
            capture_root,
            catalog,
            str(plan["product_id"]),
        ).validate()
        if validation.status == "BLOCKED":
            raise ValueError(
                "materialized run failed network validation: "
                + ";".join(validation.structural_errors)
            )
    except Exception:
        _atomic_write(capture_root / "source_observations.json", original_observations)
        for path in written:
            if path.name != "source_observations.json" and path.exists():
                path.unlink()
        raise
    return {
        "status": "PASS",
        "materialized_run": str(capture_root),
        "parser_plan_sha256": plan_hash,
        "parser_ids": sorted({task["parser_id"] for task in tasks}),
        "finding_count": len(findings),
        "network_validation": validation.to_dict(),
        "claim_boundaries": {
            "parser_output_is_live_operational": False,
            "secondary_price_is_execution_price": False,
            "news_or_catalyst_inference_performed": False,
            "network_validation_still_required": True,
        },
    }


__all__ = ["materialize_parser_run"]
