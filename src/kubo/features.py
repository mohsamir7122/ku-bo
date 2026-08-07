from __future__ import annotations

from datetime import timedelta
from typing import Any, Iterable

from .events import FACT_ROLES, SOCIAL_ROLES, EventRecord, canonicalize_events
from .strict import finite_number, parse_aware, require_sha256


FORBIDDEN_FEATURE_TOKENS = ("future_", "forward_", "outcome", "target_hit", "realized_", "label_", "t_plus_")
CAPTURE_MODES = frozenset({"PROSPECTIVE", "HISTORICAL_POINT_IN_TIME"})
AVAILABILITY_GRADES = frozenset({"A", "B", "C"})


def _direction_value(value: str) -> float:
    text = value.upper()
    if text in {"POSITIVE", "UP", "BULLISH"}:
        return 1.0
    if text in {"NEGATIVE", "DOWN", "BEARISH"}:
        return -1.0
    return 0.0


def build_event_features(
    events: Iterable[EventRecord],
    *,
    decision_id: str,
    security_code: str,
    decision_at: str,
    capture_mode: str,
    coverage_evidence_hashes: Iterable[str] = (),
    parser_version: str = "events_v2",
) -> list[dict[str, Any]]:
    if capture_mode not in CAPTURE_MODES:
        raise ValueError("invalid capture_mode")
    cutoff = parse_aware(decision_at, "decision_at")
    available = [item for item in events if item.security_code == security_code and parse_aware(item.first_available_at, "first_available_at") <= cutoff]
    recent_30 = [item for item in available if parse_aware(item.first_available_at, "first_available_at") >= cutoff - timedelta(days=30)]
    recent_7 = [item for item in available if parse_aware(item.first_available_at, "first_available_at") >= cutoff - timedelta(days=7)]
    groups_30 = canonicalize_events(recent_30)
    groups_7 = canonicalize_events(recent_7)
    official = [item for item in groups_30 if set(item["source_roles"]) & FACT_ROLES]
    context = [item for item in groups_30 if not item["official_fact_seen"] and set(item["source_roles"]) & {"NEWS_CONTEXT", "FINANCIAL_CONTEXT"}]
    social = [item for item in groups_7 if set(item["source_roles"]) & SOCIAL_ROLES]
    coverage_hashes = {str(item).lower() for item in coverage_evidence_hashes}
    all_hashes = sorted(coverage_hashes | {digest for item in groups_30 for digest in item["evidence_hashes"]})
    observed = bool(groups_30 or coverage_hashes)
    values: dict[str, Any] = {
        "official_event_net_30d": sum(_direction_value(item["direction"]) * float(item["novelty"]) for item in official) if observed else None,
        "official_event_count_30d": len(official) if observed else None,
        "context_event_net_30d": sum(_direction_value(item["direction"]) * float(item["novelty"]) for item in context) if observed else None,
        "social_event_net_7d": sum(_direction_value(item["direction"]) * float(item["novelty"]) for item in social) if observed else None,
        "social_diffusion_7d": sum(int(item["diffusion_count"]) for item in social) if observed else None,
        "source_diversity_30d": len({source_id for item in groups_30 for source_id in item["source_ids"]}) if observed else None,
        "event_window_observed_30d": observed if observed else None,
    }
    timestamps = available or []
    source_event_at = min((item.event_at for item in timestamps), default=None)
    source_published_at = min((item.published_at for item in timestamps), default=None)
    latest_available = max((item.first_available_at for item in timestamps), default=decision_at if coverage_hashes else None)
    latest_fetched = max((item.captured_at for item in timestamps), default=decision_at if coverage_hashes else None)
    return [
        {
            "decision_id": decision_id,
            "decision_at": decision_at,
            "security_code": security_code,
            "feature_name": name,
            "feature_value": value,
            "source_event_at": source_event_at,
            "source_published_at": source_published_at,
            "available_at": latest_available,
            "fetched_at": latest_fetched,
            "capture_mode": capture_mode,
            "availability_evidence_grade": "B" if observed else None,
            "source_availability_state": "OBSERVED" if observed else "UNKNOWN_NOT_OBSERVED",
            "evidence_hashes": all_hashes,
            "parser_version": parser_version,
        }
        for name, value in values.items()
    ]


def validate_feature_snapshot(rows: Iterable[dict[str, Any]], *, manifest_hashes: frozenset[str]) -> dict[str, Any]:
    rows = list(rows)
    errors: list[str] = []
    keys: set[tuple[str, str, str]] = set()
    for index, row in enumerate(rows):
        prefix = f"feature_{index}"
        try:
            for field in ("decision_id", "decision_at", "security_code", "feature_name", "capture_mode", "source_availability_state", "parser_version"):
                if row.get(field) in (None, ""):
                    raise ValueError(f"{field} is required")
            key = (str(row["decision_id"]), str(row["security_code"]), str(row["feature_name"]))
            if key in keys:
                raise ValueError("duplicate feature key")
            keys.add(key)
            name = str(row["feature_name"]).lower()
            if any(token in name for token in FORBIDDEN_FEATURE_TOKENS):
                raise ValueError("label-like or future feature name")
            decision = parse_aware(row["decision_at"], "decision_at")
            mode = str(row["capture_mode"])
            if mode not in CAPTURE_MODES:
                raise ValueError("invalid capture_mode")
            state = str(row["source_availability_state"])
            if state not in {"OBSERVED", "UNKNOWN_NOT_OBSERVED"}:
                raise ValueError("invalid source availability state")
            hashes = row.get("evidence_hashes")
            if not isinstance(hashes, list):
                raise ValueError("evidence_hashes must be a list")
            normalized_hashes = [require_sha256(item, "evidence_hash") for item in hashes]
            if set(normalized_hashes) - manifest_hashes:
                raise ValueError("feature evidence hash does not resolve")
            available_value = row.get("available_at")
            fetched_value = row.get("fetched_at")
            if state == "OBSERVED":
                if not normalized_hashes or available_value in (None, "") or fetched_value in (None, ""):
                    raise ValueError("observed feature needs evidence and timestamps")
                grade = str(row.get("availability_evidence_grade", ""))
                if grade not in AVAILABILITY_GRADES:
                    raise ValueError("availability evidence grade is missing")
                available_at = parse_aware(available_value, "available_at")
                fetched_at = parse_aware(fetched_value, "fetched_at")
                if available_at > decision:
                    raise ValueError("look-ahead availability")
                if mode == "PROSPECTIVE" and fetched_at > decision:
                    raise ValueError("prospective feature fetched after decision")
                if row.get("source_published_at") not in (None, "") and parse_aware(row.get("source_published_at"), "source_published_at") > available_at:
                    raise ValueError("publication occurs after availability")
            else:
                if row.get("feature_value") not in (None, "") or normalized_hashes:
                    raise ValueError("unknown-not-observed cannot be encoded as zero/value/evidence")
            value = row.get("feature_value")
            if value not in (None, "") and type(value) is not bool:
                finite_number(value, "feature_value")
        except (TypeError, ValueError) as exc:
            errors.append(f"{prefix}:{exc}")
    return {"status": "PASS" if rows and not errors else "BLOCKED", "rows": len(rows), "errors": sorted(set(errors))}


__all__ = ["build_event_features", "validate_feature_snapshot"]
