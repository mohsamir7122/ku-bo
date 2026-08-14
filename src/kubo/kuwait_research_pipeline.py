from __future__ import annotations

"""Fail-closed bridge from captured source bytes to auditable research inputs.

This module deliberately does not invent parsers, company mappings, factors, or
scores.  It verifies the source-search packet, accepts caller-supplied parsed
artifacts, and materializes one integrated bundle only when every layer binds
to the same decision cutoff, denominator, and evidence hashes.
"""

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any, Mapping

from .context_research import (
    DEFAULT_FACTOR_REGISTRY,
    build_factor_snapshot,
    context_event_from_dict,
    deduplicate_context_events,
    security_exposure_from_dict,
    validate_security_exposures,
)
from .atomic_output import run_atomic_output
from .foundation_io import safe_regular_file, strict_json_object
from .hashing import canonical_json_bytes, sha256_bytes
from .source_network import SourceNetworkCatalog
from .source_orchestrator import validate_source_search_run
from .strict import parse_aware, require_sha256


_SECURITY_CODE = __import__("re").compile(r"^[0-9]{1,12}$")
_MAX_INPUT_BYTES = 32 * 1024 * 1024

_CONTEXT_CLASSES_BY_CATALOG_CLASS = {
    "PRIMARY_OFFICIAL": frozenset({"OFFICIAL", "REGULATOR", "GOVERNMENT"}),
    "PRIMARY_ISSUER": frozenset({"ISSUER"}),
    "LICENSED": frozenset({"MARKET_DATA"}),
    "STRUCTURED_SECONDARY": frozenset({"MARKET_DATA"}),
    "EDITORIAL": frozenset({"NEWS"}),
    "COMMUNITY": frozenset({"COMMUNITY"}),
    "WEB_ARCHIVE": frozenset({"ARCHIVE"}),
    "SEARCH_ROUTER": frozenset({"SEARCH_ROUTING"}),
    "STORAGE": frozenset(),
}

_FACTOR_REQUIRED_ROLES = {
    "price_momentum_5d": frozenset({"PRICE_HISTORY", "EXECUTION_TAPE"}),
    "price_momentum_20d": frozenset({"PRICE_HISTORY", "EXECUTION_TAPE"}),
    "market_relative_strength_5d": frozenset({"PRICE_HISTORY", "EXECUTION_TAPE"}),
    "sector_relative_strength_5d": frozenset({"PRICE_HISTORY", "EXECUTION_TAPE"}),
    "liquidity_activity_20d": frozenset({"PRICE_HISTORY", "EXECUTION_TAPE"}),
    "realized_volatility_20d": frozenset({"PRICE_HISTORY", "EXECUTION_TAPE"}),
    "official_disclosure_30d": frozenset({"OFFICIAL_EVENT", "ISSUER_PRIMARY"}),
    "corporate_action_state": frozenset({"OFFICIAL_EVENT", "ISSUER_PRIMARY"}),
    "security_trading_status": frozenset({"IDENTITY_REFERENCE", "OFFICIAL_EVENT"}),
    "kuwait_context_regime_120d": frozenset({"NEWS_ARCHIVE", "OFFICIAL_EVENT", "MARKET_DISCOVERY"}),
    "market_regime_30d": frozenset({"PRICE_HISTORY", "MARKET_DISCOVERY"}),
    "sector_regime_30d": frozenset({"PRICE_HISTORY", "MARKET_DISCOVERY"}),
    "event_exposure_30d": frozenset({"OFFICIAL_EVENT", "ISSUER_PRIMARY", "NEWS_ARCHIVE"}),
    "fresh_catalyst_72h": frozenset({"OFFICIAL_EVENT", "ISSUER_PRIMARY", "NEWS_ARCHIVE"}),
    "community_sentiment_7d": frozenset({"COMMUNITY_SENTIMENT"}),
}


@dataclass(frozen=True, slots=True)
class ParsedResearchInputs:
    decision_id: str
    decision_at: str
    universe_as_of: str
    expected_security_codes: tuple[str, ...]
    manifest_hashes: frozenset[str]
    context_events: tuple[Mapping[str, Any], ...]
    security_exposures: tuple[Mapping[str, Any], ...]
    factor_inputs_by_security: Mapping[str, Mapping[str, Mapping[str, Any]]]
    dispositions_by_security: Mapping[str, Mapping[str, Any]]


def _load_strict(path: Path, field: str) -> dict[str, Any]:
    try:
        return strict_json_object(
            safe_regular_file(path, field=field, max_bytes=_MAX_INPUT_BYTES),
            field,
        )
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError(f"{field} is missing, unsafe, or invalid") from exc


def _security_codes(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError("expected_security_codes must be a non-empty list")
    rows = tuple(str(item).strip() for item in value)
    if any(not _SECURITY_CODE.fullmatch(item) for item in rows) or len(rows) != len(set(rows)):
        raise ValueError("expected_security_codes are invalid or duplicated")
    canonical = tuple(sorted(rows, key=lambda item: (int(item), item)))
    if rows != canonical:
        raise ValueError("expected_security_codes must use canonical order")
    return rows


def load_parsed_research_inputs(path: Path) -> ParsedResearchInputs:
    row = _load_strict(Path(path), "parsed research inputs")
    expected_keys = {
        "schema_version",
        "decision_id",
        "decision_at",
        "universe_as_of",
        "expected_security_codes",
        "manifest_hashes",
        "context_events",
        "security_exposures",
        "factor_inputs_by_security",
        "dispositions_by_security",
        "claim_boundaries",
    }
    if set(row) != expected_keys or row.get("schema_version") != "1.0":
        raise ValueError("parsed research inputs have unknown/missing fields or version")
    claims = row["claim_boundaries"]
    if claims != {
        "parser_output_is_raw_capture": False,
        "score_is_probability": False,
        "recommendation_allowed": False,
    }:
        raise ValueError("parsed research input claim boundaries were weakened")
    decision_id = str(row["decision_id"] or "").strip()
    if not decision_id:
        raise ValueError("decision_id is required")
    decision_at = parse_aware(row["decision_at"], "decision_at").isoformat()
    universe_as_of = parse_aware(row["universe_as_of"], "universe_as_of").isoformat()
    codes = _security_codes(row["expected_security_codes"])
    hashes = row["manifest_hashes"]
    if not isinstance(hashes, list) or not hashes:
        raise ValueError("manifest_hashes must be a non-empty list")
    manifest_hashes = frozenset(require_sha256(item, "manifest_hash") for item in hashes)
    if len(manifest_hashes) != len(hashes):
        raise ValueError("manifest_hashes must be unique")
    events = row["context_events"]
    exposures = row["security_exposures"]
    factors = row["factor_inputs_by_security"]
    dispositions = row["dispositions_by_security"]
    if not isinstance(events, list) or not isinstance(exposures, list):
        raise ValueError("context_events and security_exposures must be lists")
    if not isinstance(factors, dict) or not isinstance(dispositions, dict):
        raise ValueError("factor and disposition inputs must be objects")
    return ParsedResearchInputs(
        decision_id=decision_id,
        decision_at=decision_at,
        universe_as_of=universe_as_of,
        expected_security_codes=codes,
        manifest_hashes=manifest_hashes,
        context_events=tuple(events),
        security_exposures=tuple(exposures),
        factor_inputs_by_security=factors,
        dispositions_by_security=dispositions,
    )


def build_integrated_research_bundle(
    *,
    source_search_root: Path,
    parsed_inputs_path: Path,
    output_root: Path,
    source_catalog: SourceNetworkCatalog,
    schema_root: Path | None = None,
) -> dict[str, Any]:
    """Verify capture bytes and materialize context/exposure/factor artifacts.

    The parser payload must reference only hashes that exist in the verified
    source-search artifacts.  Missing parsing or factor inputs remain explicit;
    this bridge never derives analytical values from raw bytes itself.
    """

    source = validate_source_search_run(Path(source_search_root), schema_root=schema_root)
    parsed = load_parsed_research_inputs(Path(parsed_inputs_path))
    report = source.report
    source_status = report.get("status")
    if source_status not in {"COMPLETE", "DEGRADED"}:
        raise ValueError("source search run has no integrable capture state")
    if report.get("decision_at") != parsed.decision_at:
        raise ValueError("source search and parsed inputs use different decision cutoffs")
    verified_hashes = frozenset(digest for _, digest in source.artifact_hashes)
    if not verified_hashes:
        raise ValueError("source search run contains no verified raw artifacts to parse")
    if not parsed.manifest_hashes <= verified_hashes:
        raise ValueError("parsed inputs reference bytes outside the verified source-search run")

    report_source_ids = {str(item["source_id"]) for item in report["sources"]}
    unknown_report_sources = sorted(report_source_ids - set(source_catalog.sources))
    if unknown_report_sources:
        raise ValueError(
            "source search run references sources outside the verified catalog: "
            + ",".join(unknown_report_sources)
        )
    artifact_sources: dict[str, set[str]] = {}
    for row in source.attempt_rows:
        digest = row.get("content_sha256")
        source_id = row.get("source_id")
        if row.get("artifact_path") is not None and isinstance(digest, str):
            artifact_sources.setdefault(digest, set()).add(str(source_id))

    for index, row in enumerate(parsed.context_events):
        if not isinstance(row, Mapping):
            raise ValueError(f"context event {index} must be an object")
        if parse_aware(row.get("decision_at"), f"context_events[{index}].decision_at").isoformat() != parsed.decision_at:
            raise ValueError("context event and source search use different decision cutoffs")
        source_id = str(row.get("source_id") or "")
        if source_id not in report_source_ids or source_id not in source_catalog.sources:
            raise ValueError("context event source_id is outside the verified source-search run")
        catalog_source = source_catalog.sources[source_id]
        if row.get("source_group_id") != catalog_source.independence_group:
            raise ValueError("context event source_group_id does not match the verified source catalog")
        allowed_classes = _CONTEXT_CLASSES_BY_CATALOG_CLASS[catalog_source.source_class]
        if row.get("source_class") not in allowed_classes:
            raise ValueError("context event source_class exceeds the verified source catalog class")
        owned_hashes = {
            str(value)
            for field in ("evidence_hashes", "availability_evidence_hashes")
            for value in (row.get(field) if isinstance(row.get(field), list) else ())
        }
        owned_hashes.update(
            str(row[field])
            for field in ("origin_hash", "content_hash")
            if isinstance(row.get(field), str)
        )
        if not owned_hashes or any(source_id not in artifact_sources.get(digest, set()) for digest in owned_hashes):
            raise ValueError("context event evidence is not owned by its verified source_id")

    for security_code, factor_rows in parsed.factor_inputs_by_security.items():
        if not isinstance(factor_rows, Mapping):
            raise ValueError(f"factor inputs for {security_code} must be an object")
        for factor_id, factor_row in factor_rows.items():
            if not isinstance(factor_row, Mapping):
                raise ValueError(f"factor input {factor_id} must be an object")
            evidence = factor_row.get("evidence_hashes")
            if not isinstance(evidence, list):
                raise ValueError(f"factor input {factor_id} evidence_hashes must be a list")
            required_roles = _FACTOR_REQUIRED_ROLES.get(str(factor_id))
            if required_roles is None:
                raise ValueError(f"factor input has no source-role policy: {factor_id}")
            for digest in evidence:
                owners = artifact_sources.get(str(digest), set())
                eligible = {
                    source_id
                    for source_id in owners
                    if source_id in report_source_ids
                    and source_id in source_catalog.sources
                    and source_catalog.sources[source_id].roles & required_roles
                }
                if not eligible:
                    raise ValueError(
                        f"factor input {factor_id} is not supported by a verified source with an eligible role"
                    )

    events = tuple(
        context_event_from_dict(row, manifest_hashes=parsed.manifest_hashes)
        for row in parsed.context_events
    )
    canonical_events = deduplicate_context_events(events)
    exposures = tuple(
        security_exposure_from_dict(row, manifest_hashes=parsed.manifest_hashes)
        for row in parsed.security_exposures
    )
    if any(item.decision_at != parsed.decision_at for item in exposures):
        raise ValueError("security exposure and source search use different decision cutoffs")
    exposure_report = validate_security_exposures(
        exposures,
        context_events=canonical_events,
        expected_security_codes=parsed.expected_security_codes,
    )
    if exposure_report["status"] != "PASS":
        raise ValueError("security exposure integration failed: " + "; ".join(exposure_report["errors"]))
    snapshot = build_factor_snapshot(
        decision_id=parsed.decision_id,
        decision_at=parsed.decision_at,
        universe_as_of=parsed.universe_as_of,
        expected_security_codes=parsed.expected_security_codes,
        factor_inputs_by_security=parsed.factor_inputs_by_security,
        dispositions_by_security=parsed.dispositions_by_security,
        manifest_hashes=parsed.manifest_hashes,
        registry=DEFAULT_FACTOR_REGISTRY,
    )
    artifacts = {
        "context_events.json": canonical_events,
        "security_exposures.json": [item.to_dict() for item in exposures],
        "factor_snapshot.json": snapshot,
    }
    def worker(output: Path) -> dict[str, Any]:
        written: dict[str, dict[str, Any]] = {}
        for name, payload in artifacts.items():
            content = canonical_json_bytes(payload)
            target = output / name
            with target.open("xb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            written[name] = {"sha256": sha256_bytes(content), "bytes": len(content)}
        bundle = {
            "schema_version": "1.0",
            "status": (
                "CONTRACT_INTEGRATED"
                if source_status == "COMPLETE"
                else "CONTRACT_INTEGRATED_WITH_SOURCE_LIMITATIONS"
            ),
            "decision_id": parsed.decision_id,
            "decision_at": parsed.decision_at,
            "source_search_run_sha256": sha256_bytes(canonical_json_bytes(report)),
            "source_attempt_log_sha256": report["attempt_ledger"]["sha256"],
            "verified_raw_artifact_count": len(source.artifact_hashes),
            "source_search_status": source_status,
            "source_search_limitations": list(report.get("limitations", [])),
            "expected_security_count": len(parsed.expected_security_codes),
            "artifacts": written,
            "claim_boundaries": {
                "raw_capture_is_parsed_finding": False,
                "contract_integration_is_live_operational": False,
                "score_is_probability": False,
                "forecast_generated": False,
                "recommendation_generated": False,
            },
        }
        content = canonical_json_bytes(bundle)
        with (output / "integrated_research_bundle.json").open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        return bundle

    return run_atomic_output(Path(output_root), worker)


__all__ = [
    "ParsedResearchInputs",
    "build_integrated_research_bundle",
    "load_parsed_research_inputs",
]
