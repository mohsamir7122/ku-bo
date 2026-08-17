from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .disclosure_data_domains import (
    validate_historical_disclosure_record,
    validate_historical_event_market_window,
    validate_public_opinion_archive,
)
from .disclosure_reaction_common import (
    DisclosureReactionError,
    PRODUCT_ID,
    aware,
    exact_fields,
    mapping,
    number,
    text,
)

_PACKET_FIELDS = {
    "schema_version", "packet_id", "product_id", "timezone", "created_at",
    "policy", "historical_disclosure", "historical_market_window",
    "public_opinion_archive",
}
_POLICY_FIELDS = {
    "immediate_post_sessions", "movement_threshold_pct",
    "numeric_output_rule", "causality_rule", "current_market_rule",
    "latest_financial_rule",
}


def validate_disclosure_reaction_packet(raw: Mapping[str, Any]) -> dict[str, Any]:
    packet = mapping(raw, "packet")
    exact_fields(packet, _PACKET_FIELDS, "packet")
    if packet["schema_version"] != "1.0":
        raise DisclosureReactionError("packet.schema_version must equal 1.0")
    if packet["product_id"] != PRODUCT_ID:
        raise DisclosureReactionError(f"packet.product_id must equal {PRODUCT_ID}")
    if packet["timezone"] != "Asia/Kuwait":
        raise DisclosureReactionError("packet.timezone must equal Asia/Kuwait")
    created_at = aware(packet["created_at"], "packet.created_at")
    policy = mapping(packet["policy"], "packet.policy")
    exact_fields(policy, _POLICY_FIELDS, "packet.policy")
    if policy["immediate_post_sessions"] != 2:
        raise DisclosureReactionError("packet.policy.immediate_post_sessions must equal 2")
    threshold = number(policy["movement_threshold_pct"], "packet.policy.movement_threshold_pct", minimum=0.01, maximum=25)
    expected = {
        "numeric_output_rule": "QUALITATIVE_ONLY",
        "causality_rule": "ASSOCIATION_NOT_CAUSATION",
        "current_market_rule": "EXCLUDED_FROM_HISTORICAL_REACTION",
        "latest_financial_rule": "EXCLUDED_FROM_HISTORICAL_REACTION",
    }
    for field, value in expected.items():
        if policy[field] != value:
            raise DisclosureReactionError(f"packet.policy.{field} must equal {value}")
    disclosure = validate_historical_disclosure_record(packet["historical_disclosure"])
    window = validate_historical_event_market_window(packet["historical_market_window"])
    opinion = validate_public_opinion_archive(packet["public_opinion_archive"])
    if {disclosure["security_code"], window["security_code"], opinion["security_code"]} != {"HUMANSOFT"}:
        raise DisclosureReactionError("data-domain security codes do not match")
    if disclosure["canonical_cluster_id"] != window["canonical_cluster_id"] or disclosure["canonical_cluster_id"] != opinion["canonical_cluster_id"]:
        raise DisclosureReactionError("canonical disclosure cluster mismatch")
    if disclosure["record_id"] != window["disclosure_record_id"]:
        raise DisclosureReactionError("historical market window points to another disclosure record")
    disclosure_available = aware(disclosure["available_at"], "historical_disclosure.available_at")
    pre = window["pre_sessions"]
    post = window["post_sessions"]
    if aware(pre[-1]["session_close_at"], "pre.session_close_at") >= disclosure_available:
        raise DisclosureReactionError("pre-disclosure window includes the disclosure or later data")
    if aware(post[0]["session_close_at"], "post.session_close_at") <= disclosure_available:
        raise DisclosureReactionError("post-disclosure window does not start after disclosure availability")
    if created_at < aware(window["frozen_at"], "historical_market_window.frozen_at"):
        raise DisclosureReactionError("packet created before historical market window was frozen")
    if created_at < aware(opinion["captured_through"], "public_opinion_archive.captured_through"):
        raise DisclosureReactionError("packet created before public opinion archive cutoff")
    return {
        **dict(packet),
        "packet_id": text(packet["packet_id"], "packet.packet_id", 128),
        "policy": {**dict(policy), "movement_threshold_pct": threshold},
        "historical_disclosure": disclosure,
        "historical_market_window": window,
        "public_opinion_archive": opinion,
    }


__all__ = ["validate_disclosure_reaction_packet"]
