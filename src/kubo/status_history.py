from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Iterable

from .strict import parse_iso_date, require_sha256


STATUS_VALUES = frozenset({"TRADING", "SUSPENDED", "DELISTED"})
STATUS_EVENT_TYPES = frozenset({"SUSPEND", "RESUME", "DELIST", "RELIST"})
_ALLOWED_TRANSITIONS = {
    ("TRADING", "SUSPEND"): "SUSPENDED",
    ("SUSPENDED", "RESUME"): "TRADING",
    ("TRADING", "DELIST"): "DELISTED",
    ("SUSPENDED", "DELIST"): "DELISTED",
    ("DELISTED", "RELIST"): "TRADING",
}


@dataclass(frozen=True)
class StatusNotice:
    notice_id: str
    security_code: str
    ticker: str
    event_type: str
    effective_date: date
    published_date: date
    source_id: str
    source_url: str
    raw_sha256: str
    text_sha256: str
    query_id: str
    classification_phrase: str


@dataclass(frozen=True)
class StatusInterval:
    security_code: str
    ticker: str
    status: str
    effective_from: date
    effective_to: date
    opening_evidence_sha256: str
    start_notice_id: str
    end_notice_id: str
    evidence_hashes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "security_code": self.security_code,
            "ticker": self.ticker,
            "status": self.status,
            "effective_from": self.effective_from.isoformat(),
            "effective_to": self.effective_to.isoformat(),
            "opening_evidence_sha256": self.opening_evidence_sha256,
            "start_notice_id": self.start_notice_id,
            "end_notice_id": self.end_notice_id,
            "evidence_hashes": "|".join(self.evidence_hashes),
        }


def parse_status_notice(
    row: dict[str, Any],
    *,
    expected_identity: dict[str, str],
    manifest_hashes: frozenset[str],
    allowed_query_ids: frozenset[str],
    window_from: date,
    window_to: date,
) -> StatusNotice:
    expected_fields = {
        "notice_id",
        "security_code",
        "ticker",
        "event_type",
        "effective_date",
        "published_date",
        "source_id",
        "source_url",
        "raw_sha256",
        "text_sha256",
        "query_id",
        "classification_phrase",
    }
    if not isinstance(row, dict) or set(row) != expected_fields:
        raise ValueError("status notice has unknown or missing fields")
    notice_id = str(row["notice_id"]).strip()
    code = str(row["security_code"]).strip()
    ticker = str(row["ticker"]).strip().upper()
    event_type = str(row["event_type"]).strip().upper()
    if not notice_id:
        raise ValueError("notice_id is required")
    if expected_identity.get(code) != ticker:
        raise ValueError("notice identity does not match the expected security")
    if event_type not in STATUS_EVENT_TYPES:
        raise ValueError("unsupported status event_type")
    effective_date = parse_iso_date(row["effective_date"], "effective_date")
    published_date = parse_iso_date(row["published_date"], "published_date")
    if not window_from <= effective_date <= window_to:
        raise ValueError("notice effective_date is outside the history window")
    if published_date > window_to:
        raise ValueError("notice published_date is after the history window")
    source_id = str(row["source_id"]).strip()
    source_url = str(row["source_url"]).strip()
    if source_id not in {"boursa_historical_disclosures", "cma_announcement"}:
        raise ValueError("unsupported status-notice source_id")
    if not source_url.startswith("https://"):
        raise ValueError("status notice source_url must be HTTPS")
    raw_sha256 = require_sha256(row["raw_sha256"], "raw_sha256")
    text_sha256 = require_sha256(row["text_sha256"], "text_sha256")
    if raw_sha256 not in manifest_hashes or text_sha256 not in manifest_hashes:
        raise ValueError("status notice evidence hash does not resolve")
    query_id = str(row["query_id"]).strip()
    if query_id not in allowed_query_ids:
        raise ValueError("status notice query_id is not registered")
    phrase = str(row["classification_phrase"]).strip()
    if not phrase:
        raise ValueError("classification_phrase is required")
    return StatusNotice(
        notice_id=notice_id,
        security_code=code,
        ticker=ticker,
        event_type=event_type,
        effective_date=effective_date,
        published_date=published_date,
        source_id=source_id,
        source_url=source_url,
        raw_sha256=raw_sha256,
        text_sha256=text_sha256,
        query_id=query_id,
        classification_phrase=phrase,
    )


def build_status_intervals(
    *,
    expected_identity: dict[str, str],
    opening_states: dict[str, dict[str, Any]],
    current_states: dict[str, str],
    notices: Iterable[StatusNotice],
    window_from: date,
    window_to: date,
) -> tuple[list[StatusInterval], dict[str, Any]]:
    if window_from > window_to:
        raise ValueError("history window is reversed")
    errors: list[str] = []
    intervals: list[StatusInterval] = []
    notice_rows = list(notices)
    notice_ids = [item.notice_id for item in notice_rows]
    if len(notice_ids) != len(set(notice_ids)):
        errors.append("DUPLICATE_STATUS_NOTICE_ID")
    by_code: dict[str, list[StatusNotice]] = {}
    for notice in notice_rows:
        by_code.setdefault(notice.security_code, []).append(notice)

    for code, ticker in sorted(expected_identity.items()):
        opening = opening_states.get(code)
        if not isinstance(opening, dict):
            errors.append(f"MISSING_OPENING_STATE:{code}")
            continue
        opening_status = str(opening.get("status", "")).upper()
        if opening_status not in STATUS_VALUES:
            errors.append(f"INVALID_OPENING_STATE:{code}")
            continue
        if str(opening.get("ticker", "")).upper() != ticker:
            errors.append(f"OPENING_STATE_TICKER_MISMATCH:{code}")
            continue
        try:
            opening_hash = require_sha256(
                opening.get("raw_sha256"),
                "opening_state.raw_sha256",
            )
        except ValueError as exc:
            errors.append(f"OPENING_STATE_EVIDENCE:{code}:{exc}")
            continue
        events = sorted(
            by_code.get(code, []),
            key=lambda item: (item.effective_date, item.notice_id),
        )
        if len({item.effective_date for item in events}) != len(events):
            errors.append(f"MULTIPLE_STATUS_EVENTS_SAME_DATE:{code}")
            continue
        current_status = opening_status
        interval_start = window_from
        interval_start_notice = "OPENING_STATE"
        accumulated_hashes: list[str] = [opening_hash]
        for event in events:
            target = _ALLOWED_TRANSITIONS.get((current_status, event.event_type))
            if target is None:
                errors.append(
                    f"INVALID_STATUS_TRANSITION:{code}:{current_status}:{event.event_type}:{event.effective_date.isoformat()}"
                )
                continue
            previous_end = event.effective_date - timedelta(days=1)
            if previous_end >= interval_start:
                intervals.append(
                    StatusInterval(
                        security_code=code,
                        ticker=ticker,
                        status=current_status,
                        effective_from=interval_start,
                        effective_to=previous_end,
                        opening_evidence_sha256=opening_hash,
                        start_notice_id=interval_start_notice,
                        end_notice_id=event.notice_id,
                        evidence_hashes=tuple(dict.fromkeys(accumulated_hashes + [event.raw_sha256, event.text_sha256])),
                    )
                )
            current_status = target
            interval_start = event.effective_date
            interval_start_notice = event.notice_id
            accumulated_hashes.extend((event.raw_sha256, event.text_sha256))
        if interval_start <= window_to:
            intervals.append(
                StatusInterval(
                    security_code=code,
                    ticker=ticker,
                    status=current_status,
                    effective_from=interval_start,
                    effective_to=window_to,
                    opening_evidence_sha256=opening_hash,
                    start_notice_id=interval_start_notice,
                    end_notice_id="CURRENT_SNAPSHOT",
                    evidence_hashes=tuple(dict.fromkeys(accumulated_hashes)),
                )
            )
        expected_current = current_states.get(code)
        if expected_current not in {"TRADING", "SUSPENDED"}:
            errors.append(f"MISSING_CURRENT_STATUS:{code}")
        elif current_status != expected_current:
            errors.append(
                f"CURRENT_STATUS_RECONCILIATION:{code}:history={current_status}:snapshot={expected_current}"
            )

    expected_codes = set(expected_identity)
    notice_codes = set(by_code)
    extra_notice_codes = notice_codes - expected_codes
    if extra_notice_codes:
        errors.append(
            "STATUS_NOTICE_OUTSIDE_PILOT:" + ",".join(sorted(extra_notice_codes))
        )
    intervals.sort(key=lambda item: (int(item.security_code), item.effective_from))
    return intervals, {
        "status": "PASS" if intervals and not errors else "BLOCKED",
        "security_count": len(expected_identity),
        "notice_count": len(notice_rows),
        "interval_count": len(intervals),
        "window_from": window_from.isoformat(),
        "window_to": window_to.isoformat(),
        "errors": sorted(set(errors)),
        "history_scope": "DECLARED_WINDOW_ONLY",
        "status_history_ready": bool(intervals) and not errors,
    }


__all__ = [
    "STATUS_EVENT_TYPES",
    "STATUS_VALUES",
    "StatusInterval",
    "StatusNotice",
    "build_status_intervals",
    "parse_status_notice",
]
