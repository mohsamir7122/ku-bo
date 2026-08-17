from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from .disclosure_reaction_common import (
    DisclosureReactionError,
    IMMEDIATE_POST_SESSIONS,
    POST_SESSIONS,
    PRE_SESSIONS,
    PRODUCT_ID,
    _DISCLOSURE_FIELDS,
    _OPINION_FIELDS,
    _PACKET_FIELDS,
    _POLICY_FIELDS,
    _RECEIPT_FIELDS,
    _RELEVANCE,
    _SESSION_FIELDS,
    _SOURCE_KINDS,
    _STANCES,
    _aware,
    _fields,
    _mapping,
    _number,
    _positive_int,
    _sha,
    _text,
    _url,
)

def _validate_policy(raw: Any) -> dict[str, Any]:
    policy = _mapping(raw, "policy")
    _fields(policy, _POLICY_FIELDS, "policy")
    expected_ints = {
        "pre_sessions": PRE_SESSIONS,
        "post_sessions": POST_SESSIONS,
        "immediate_post_sessions": IMMEDIATE_POST_SESSIONS,
    }
    for field, expected in expected_ints.items():
        if _positive_int(policy[field], f"policy.{field}") != expected:
            raise DisclosureReactionError(f"policy.{field} must equal {expected}")
    expected_text = {
        "price_basis": "TOTAL_RETURN_INDEX",
        "benchmark_rule": "MARKET_AND_SECTOR_EXCESS",
        "corporate_action_rule": "ADJUSTED_OR_EXPLICIT_NONE",
        "public_opinion_rule": "SOURCE_BACKED_INDEPENDENT_GROUPS",
        "numeric_output_rule": "QUALITATIVE_ONLY",
        "causality_rule": "ASSOCIATION_NOT_CAUSATION",
    }
    for field, expected in expected_text.items():
        if policy[field] != expected:
            raise DisclosureReactionError(f"policy.{field} must equal {expected}")
    return {
        **dict(policy),
        "movement_threshold_pct": _number(
            policy["movement_threshold_pct"],
            "policy.movement_threshold_pct",
            minimum=0.01,
            maximum=25.0,
        ),
    }


def _validate_disclosure(raw: Any) -> dict[str, Any]:
    disclosure = _mapping(raw, "disclosure")
    _fields(disclosure, _DISCLOSURE_FIELDS, "disclosure")
    published = _aware(disclosure["published_at"], "disclosure.published_at")
    available = _aware(disclosure["available_at"], "disclosure.available_at")
    if available < published:
        raise DisclosureReactionError(
            "disclosure.available_at precedes disclosure.published_at"
        )
    if disclosure["duplicate_of"] is not None:
        raise DisclosureReactionError(
            "only the canonical disclosure cluster may be analyzed"
        )
    security_code = _text(
        disclosure["security_code"], "disclosure.security_code", 64
    ).upper()
    if security_code != "HUMANSOFT":
        raise DisclosureReactionError("security_code must equal HUMANSOFT")
    return {
        "disclosure_id": _text(
            disclosure["disclosure_id"], "disclosure.disclosure_id", 128
        ),
        "security_code": security_code,
        "canonical_cluster_id": _text(
            disclosure["canonical_cluster_id"],
            "disclosure.canonical_cluster_id",
            128,
        ),
        "disclosure_type": _text(
            disclosure["disclosure_type"], "disclosure.disclosure_type", 128
        ),
        "headline": _text(disclosure["headline"], "disclosure.headline", 1000),
        "published_at": disclosure["published_at"],
        "available_at": disclosure["available_at"],
        "official_source_url": _url(
            disclosure["official_source_url"],
            "disclosure.official_source_url",
        ),
        "official_evidence_sha256": _sha(
            disclosure["official_evidence_sha256"],
            "disclosure.official_evidence_sha256",
        ),
        "duplicate_of": None,
    }


def _validate_sessions(
    raw: Any,
    *,
    field: str,
    expected_count: int,
    disclosure_available: datetime,
    before: bool,
) -> list[dict[str, Any]]:
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise DisclosureReactionError(f"{field} must be an array")
    if len(raw) != expected_count:
        raise DisclosureReactionError(
            f"{field} must contain exactly {expected_count} sessions"
        )
    result: list[dict[str, Any]] = []
    dates: list[str] = []
    closes: list[datetime] = []
    for index, item in enumerate(raw):
        row = _mapping(item, f"{field}[{index}]")
        _fields(row, _SESSION_FIELDS, f"{field}[{index}]")
        trade_date = _text(row["trade_date"], f"{field}[{index}].trade_date", 10)
        try:
            parsed_date = datetime.strptime(trade_date, "%Y-%m-%d").date()
        except ValueError as exc:
            raise DisclosureReactionError(
                f"{field}[{index}].trade_date must be YYYY-MM-DD"
            ) from exc
        close = _aware(row["session_close_at"], f"{field}[{index}].session_close_at")
        observed = _aware(row["observed_at"], f"{field}[{index}].observed_at")
        if close.date() != parsed_date:
            raise DisclosureReactionError(f"{field}[{index}] date/close mismatch")
        if observed < close:
            raise DisclosureReactionError(f"{field}[{index}] observed before close")
        if before and close >= disclosure_available:
            raise DisclosureReactionError(f"{field}[{index}] is not pre-disclosure")
        if not before and close <= disclosure_available:
            raise DisclosureReactionError(f"{field}[{index}] is not post-disclosure")
        validated: dict[str, Any] = {
            "trade_date": trade_date,
            "session_close_at": row["session_close_at"],
            "observed_at": row["observed_at"],
            "stock_total_return_index": _number(
                row["stock_total_return_index"],
                f"{field}[{index}].stock_total_return_index",
                minimum=1e-12,
            ),
            "market_total_return_index": _number(
                row["market_total_return_index"],
                f"{field}[{index}].market_total_return_index",
                minimum=1e-12,
            ),
            "sector_total_return_index": _number(
                row["sector_total_return_index"],
                f"{field}[{index}].sector_total_return_index",
                minimum=1e-12,
            ),
        }
        for evidence_field in (
            "calendar_evidence_sha256",
            "price_evidence_sha256",
            "market_benchmark_evidence_sha256",
            "sector_benchmark_evidence_sha256",
            "corporate_action_evidence_sha256",
        ):
            validated[evidence_field] = _sha(
                row[evidence_field], f"{field}[{index}].{evidence_field}"
            )
        result.append(validated)
        dates.append(trade_date)
        closes.append(close)
    if dates != sorted(dates) or len(set(dates)) != len(dates):
        raise DisclosureReactionError(f"{field} must be unique and ascending")
    if closes != sorted(closes):
        raise DisclosureReactionError(f"{field} closes must be ascending")
    return result


def _validate_opinions(raw: Any, created_at: datetime) -> list[dict[str, Any]]:
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise DisclosureReactionError("public_opinion must be an array")
    seen_ids: set[str] = set()
    result: list[dict[str, Any]] = []
    for index, item in enumerate(raw):
        opinion = _mapping(item, f"public_opinion[{index}]")
        _fields(opinion, _OPINION_FIELDS, f"public_opinion[{index}]")
        opinion_id = _text(
            opinion["opinion_id"], f"public_opinion[{index}].opinion_id", 128
        )
        if opinion_id in seen_ids:
            raise DisclosureReactionError(f"duplicate opinion_id: {opinion_id}")
        seen_ids.add(opinion_id)
        published = _aware(
            opinion["published_at"], f"public_opinion[{index}].published_at"
        )
        if published > created_at:
            raise DisclosureReactionError(
                f"public_opinion[{index}] postdates packet.created_at"
            )
        source_kind = _text(
            opinion["source_kind"], f"public_opinion[{index}].source_kind", 64
        )
        stance = _text(opinion["stance"], f"public_opinion[{index}].stance", 64)
        relevance = _text(
            opinion["relevance"], f"public_opinion[{index}].relevance", 64
        )
        if source_kind not in _SOURCE_KINDS:
            raise DisclosureReactionError(f"unsupported source_kind: {source_kind}")
        if stance not in _STANCES:
            raise DisclosureReactionError(f"unsupported stance: {stance}")
        if relevance not in _RELEVANCE:
            raise DisclosureReactionError(f"unsupported relevance: {relevance}")
        result.append(
            {
                "opinion_id": opinion_id,
                "published_at": opinion["published_at"],
                "source_kind": source_kind,
                "source_group": _text(
                    opinion["source_group"],
                    f"public_opinion[{index}].source_group",
                    128,
                ),
                "source_url": _url(
                    opinion["source_url"], f"public_opinion[{index}].source_url"
                ),
                "stance": stance,
                "relevance": relevance,
                "evidence_sha256": _sha(
                    opinion["evidence_sha256"],
                    f"public_opinion[{index}].evidence_sha256",
                ),
            }
        )
    return result


def validate_disclosure_reaction_packet(packet: Mapping[str, Any]) -> dict[str, Any]:
    packet = _mapping(packet, "packet")
    _fields(packet, _PACKET_FIELDS, "packet")
    if packet["schema_version"] != "1.0":
        raise DisclosureReactionError("schema_version must equal 1.0")
    if packet["product_id"] != PRODUCT_ID:
        raise DisclosureReactionError(f"product_id must equal {PRODUCT_ID}")
    if packet["timezone"] != "Asia/Kuwait":
        raise DisclosureReactionError("timezone must equal Asia/Kuwait")
    created_at = _aware(packet["created_at"], "packet.created_at")
    policy = _validate_policy(packet["policy"])
    disclosure = _validate_disclosure(packet["disclosure"])
    available_at = _aware(disclosure["available_at"], "disclosure.available_at")
    pre = _validate_sessions(
        packet["pre_sessions"],
        field="pre_sessions",
        expected_count=PRE_SESSIONS,
        disclosure_available=available_at,
        before=True,
    )
    post = _validate_sessions(
        packet["post_sessions"],
        field="post_sessions",
        expected_count=POST_SESSIONS,
        disclosure_available=available_at,
        before=False,
    )
    latest_observation = max(
        _aware(row["observed_at"], "session.observed_at") for row in (*pre, *post)
    )
    if created_at < latest_observation:
        raise DisclosureReactionError(
            "packet.created_at precedes an included session observation"
        )
    opinions = _validate_opinions(packet["public_opinion"], created_at)
    receipts = _mapping(packet["evidence_receipts"], "evidence_receipts")
    _fields(receipts, _RECEIPT_FIELDS, "evidence_receipts")
    validated_receipts = {
        field: _sha(value, f"evidence_receipts.{field}")
        for field, value in receipts.items()
    }
    if (
        validated_receipts["official_disclosure_sha256"]
        != disclosure["official_evidence_sha256"]
    ):
        raise DisclosureReactionError(
            "official disclosure does not match evidence receipt"
        )
    session_receipts = {
        "calendar_evidence_sha256": "trading_calendar_sha256",
        "price_evidence_sha256": "price_history_sha256",
        "market_benchmark_evidence_sha256": "market_benchmark_sha256",
        "sector_benchmark_evidence_sha256": "sector_benchmark_sha256",
        "corporate_action_evidence_sha256": "corporate_actions_sha256",
    }
    for window_name, rows in (("pre_sessions", pre), ("post_sessions", post)):
        for index, row in enumerate(rows):
            for row_field, receipt_field in session_receipts.items():
                if row[row_field] != validated_receipts[receipt_field]:
                    raise DisclosureReactionError(
                        f"{window_name}[{index}].{row_field} does not match "
                        f"evidence_receipts.{receipt_field}"
                    )
    return {
        **dict(packet),
        "packet_id": _text(packet["packet_id"], "packet.packet_id", 128),
        "policy": policy,
        "disclosure": disclosure,
        "pre_sessions": pre,
        "post_sessions": post,
        "public_opinion": opinions,
        "evidence_receipts": validated_receipts,
    }



__all__ = ["validate_disclosure_reaction_packet"]
