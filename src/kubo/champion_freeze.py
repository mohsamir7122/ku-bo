"""Validate a previous-session Champion freeze before a daily research run."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from pathlib import Path
import re
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from .codex_live_bootstrap import EXPECTED_PRODUCTS
from .strict import parse_aware, parse_iso_date, require_sha256


KUWAIT_TZ = ZoneInfo("Asia/Kuwait")
FREEZE_CLAIM_BOUNDARIES = {
    "previous_approved_freeze_only": True,
    "same_day_challenger_used": False,
    "live_or_accuracy_claim_allowed": False,
    "buy_recommendation_claim_allowed": False,
    "automatic_promotion_allowed": False,
}
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,127}$")
_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_ROOT_KEYS = frozenset(
    {
        "schema_version",
        "freeze_id",
        "status",
        "product_id",
        "horizon_sessions",
        "model_version",
        "policy_version",
        "source_session_date",
        "effective_from_session_date",
        "approved_at",
        "artifacts",
        "approval",
        "outcomes",
        "claim_boundaries",
    }
)
_ARTIFACT_KEYS = frozenset(
    {
        "code_sha256",
        "model_sha256",
        "feature_policy_sha256",
        "training_manifest_sha256",
    }
)
_APPROVAL_KEYS = frozenset({"approved_by_role", "decision_id"})
_OUTCOME_KEYS = frozenset({"available_through", "same_session_outcomes_included"})


class ChampionFreezeError(ValueError):
    """Raised when a freeze could leak same-day or unapproved model state."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ChampionFreezeError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ChampionFreezeError(f"non-finite JSON value is forbidden: {value}")


def _load_strict(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ChampionFreezeError(f"cannot load strict freeze JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ChampionFreezeError("freeze manifest root must be an object")
    return payload


def _exact_object(value: Any, keys: frozenset[str], field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ChampionFreezeError(f"{field} must be an object")
    actual = frozenset(value)
    if actual != keys:
        raise ChampionFreezeError(
            f"{field} has missing={sorted(keys - actual)} unknown={sorted(actual - keys)}"
        )
    return value


def _parse_date(value: Any, field: str) -> date:
    try:
        return parse_iso_date(value, field)
    except ValueError as exc:
        raise ChampionFreezeError(str(exc)) from exc


def _parse_time(value: Any, field: str) -> datetime:
    try:
        return parse_aware(value, field)
    except ValueError as exc:
        raise ChampionFreezeError(str(exc)) from exc


def _require_identifier(value: Any, field: str, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or value != value.strip() or not pattern.fullmatch(value):
        raise ChampionFreezeError(f"{field} is not a canonical identifier")
    return value


def _manifest_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_champion_freeze(
    path: Path | str,
    *,
    decision_session_date: date | str,
) -> dict[str, Any]:
    """Require an approved freeze from an earlier Kuwait session."""

    manifest_path = Path(path)
    payload = _load_strict(manifest_path)
    _exact_object(payload, _ROOT_KEYS, "freeze")
    if payload["schema_version"] != "1.0":
        raise ChampionFreezeError("unsupported freeze schema")
    if payload["status"] != "APPROVED_CHAMPION":
        raise ChampionFreezeError("freeze status must be APPROVED_CHAMPION")
    freeze_id = _require_identifier(payload["freeze_id"], "freeze_id", _ID_RE)
    _require_identifier(payload["model_version"], "model_version", _VERSION_RE)
    _require_identifier(payload["policy_version"], "policy_version", _VERSION_RE)

    product_map = {row["product_id"]: row["horizon_sessions"] for row in EXPECTED_PRODUCTS}
    product_id = payload["product_id"]
    if product_id not in product_map:
        raise ChampionFreezeError("freeze product is outside the daily product contract")
    if isinstance(payload["horizon_sessions"], bool) or payload[
        "horizon_sessions"
    ] != product_map[product_id]:
        raise ChampionFreezeError("freeze horizon does not match product_id")

    artifacts = _exact_object(payload["artifacts"], _ARTIFACT_KEYS, "artifacts")
    for field, value in artifacts.items():
        try:
            require_sha256(value, f"artifacts.{field}")
        except ValueError as exc:
            raise ChampionFreezeError(str(exc)) from exc

    approval = _exact_object(payload["approval"], _APPROVAL_KEYS, "approval")
    if approval["approved_by_role"] != "AUTHORIZED_REVIEWER":
        raise ChampionFreezeError("freeze must be approved by an authorized reviewer")
    _require_identifier(approval["decision_id"], "approval.decision_id", _ID_RE)

    outcomes = _exact_object(payload["outcomes"], _OUTCOME_KEYS, "outcomes")
    if outcomes["same_session_outcomes_included"] is not False:
        raise ChampionFreezeError("same-session outcomes must not enter the freeze")

    if payload["claim_boundaries"] != FREEZE_CLAIM_BOUNDARIES:
        raise ChampionFreezeError("freeze claim boundaries were weakened")

    if isinstance(decision_session_date, datetime):
        raise ChampionFreezeError("decision_session_date must be a date, not datetime")
    decision_date = (
        decision_session_date
        if isinstance(decision_session_date, date)
        else _parse_date(decision_session_date, "decision_session_date")
    )
    source_date = _parse_date(payload["source_session_date"], "source_session_date")
    effective_date = _parse_date(
        payload["effective_from_session_date"], "effective_from_session_date"
    )
    approved_at = _parse_time(payload["approved_at"], "approved_at")
    outcome_cutoff = _parse_time(outcomes["available_through"], "outcomes.available_through")

    if not source_date < effective_date <= decision_date:
        raise ChampionFreezeError(
            "freeze must originate before its effective session and be effective by decision"
        )
    if approved_at.astimezone(KUWAIT_TZ).date() >= decision_date:
        raise ChampionFreezeError("same-day approval cannot power the daily output")
    if approved_at.astimezone(KUWAIT_TZ).date() > source_date:
        raise ChampionFreezeError("approval date cannot follow the source session date")
    if outcome_cutoff.astimezone(KUWAIT_TZ).date() > source_date:
        raise ChampionFreezeError("outcome cutoff cannot follow the source session date")
    if outcome_cutoff > approved_at:
        raise ChampionFreezeError("outcome cutoff cannot follow freeze approval")

    return {
        "schema_version": "1.0",
        "status": "PASS_PREVIOUS_FREEZE_ONLY",
        "freeze_id": freeze_id,
        "manifest_sha256": _manifest_sha256(manifest_path),
        "product_id": product_id,
        "horizon_sessions": product_map[product_id],
        "source_session_date": source_date.isoformat(),
        "effective_from_session_date": effective_date.isoformat(),
        "decision_session_date": decision_date.isoformat(),
        "same_day_challenger_used": False,
        "claim_boundaries": FREEZE_CLAIM_BOUNDARIES,
    }


__all__ = [
    "ChampionFreezeError",
    "FREEZE_CLAIM_BOUNDARIES",
    "validate_champion_freeze",
]
