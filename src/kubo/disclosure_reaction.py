from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Mapping, Sequence
import json
from pathlib import Path
from typing import Any

from .disclosure_reaction_common import (
    DisclosureReactionError,
    IMMEDIATE_POST_SESSIONS,
    PRODUCT_ID,
    _aware,
    _digest,
)
from .disclosure_reaction_packet import validate_disclosure_reaction_packet

def _return_pct(start: float, end: float) -> float:
    return (end / start - 1.0) * 100.0


def _excess_move(start: Mapping[str, Any], end: Mapping[str, Any]) -> float:
    stock = _return_pct(
        float(start["stock_total_return_index"]),
        float(end["stock_total_return_index"]),
    )
    market = _return_pct(
        float(start["market_total_return_index"]),
        float(end["market_total_return_index"]),
    )
    sector = _return_pct(
        float(start["sector_total_return_index"]),
        float(end["sector_total_return_index"]),
    )
    return ((stock - market) + (stock - sector)) / 2.0


def _movement_label(value: float, threshold: float) -> str:
    if value >= threshold:
        return "RISING"
    if value <= -threshold:
        return "FALLING"
    return "NO_CLEAR_MOVE"


def _timing_conclusion(before: str, immediate: str, full_after: str) -> str:
    if before == "RISING" and full_after == "RISING":
        return "RISE_STARTED_BEFORE_AND_CONTINUED_AFTER"
    if before == "RISING":
        return "RISE_STARTED_BEFORE_DISCLOSURE"
    if immediate == "RISING" and full_after == "RISING":
        return "RISE_STARTED_IMMEDIATELY_AFTER_DISCLOSURE"
    if immediate == "RISING":
        return "SHORT_RISE_AFTER_DISCLOSURE_THEN_FADED"
    if full_after == "RISING":
        return "RISE_APPEARED_LATER_AFTER_DISCLOSURE"
    return "NO_CLEAR_RISE_AROUND_DISCLOSURE"


def _association(timing: str) -> str:
    if timing in {
        "RISE_STARTED_BEFORE_AND_CONTINUED_AFTER",
        "RISE_STARTED_BEFORE_DISCLOSURE",
    }:
        return "MOVE_PRECEDED_DISCLOSURE"
    if timing == "RISE_STARTED_IMMEDIATELY_AFTER_DISCLOSURE":
        return "POST_DISCLOSURE_RISE_ASSOCIATED"
    if timing == "SHORT_RISE_AFTER_DISCLOSURE_THEN_FADED":
        return "TEMPORARY_POST_DISCLOSURE_RISE_ASSOCIATED"
    if timing == "RISE_APPEARED_LATER_AFTER_DISCLOSURE":
        return "DELAYED_RISE_WEAKLY_ASSOCIATED"
    return "NO_CLEAR_RISE_ASSOCIATION"


def _opinion_label(rows: Sequence[Mapping[str, Any]]) -> str:
    if not rows:
        return "INSUFFICIENT_EVIDENCE"
    by_group: dict[str, set[str]] = {}
    for row in rows:
        by_group.setdefault(str(row["source_group"]), set()).add(str(row["stance"]))
    collapsed: list[str] = []
    for stances in by_group.values():
        collapsed.append(next(iter(stances)) if len(stances) == 1 else "MIXED")
    counts = Counter(collapsed)
    if counts["MIXED"] or (counts["POSITIVE"] and counts["NEGATIVE"]):
        return "MIXED"
    if counts["POSITIVE"]:
        return "POSITIVE"
    if counts["NEGATIVE"]:
        return "NEGATIVE"
    return "NEUTRAL"


def _arabic_price_summary(timing: str) -> str:
    summaries = {
        "RISE_STARTED_BEFORE_AND_CONTINUED_AFTER": (
            "كان السهم يرتفع قبل نشر الإفصاح واستمر الارتفاع بعده؛ لذلك لا يصح "
            "اعتبار الإفصاح نقطة بداية الحركة أو سببها الوحيد."
        ),
        "RISE_STARTED_BEFORE_DISCLOSURE": (
            "بدأ ارتفاع السهم قبل نشر الإفصاح، ولم يظهر استمرار واضح بعده؛ "
            "الحركة سبقت الخبر الرسمي."
        ),
        "RISE_STARTED_IMMEDIATELY_AFTER_DISCLOSURE": (
            "لم يظهر ارتفاع واضح قبل الإفصاح، وبدأ الارتفاع بعد نشره مباشرة؛ "
            "توجد علاقة زمنية بالخبر دون إثبات أن الخبر كان السبب الوحيد."
        ),
        "SHORT_RISE_AFTER_DISCLOSURE_THEN_FADED": (
            "ظهر ارتفاع قصير بعد نشر الإفصاح ثم تلاشى؛ كان التفاعل إيجابيًا مؤقتًا "
            "ولم يتحول إلى اتجاه صاعد مستمر."
        ),
        "RISE_APPEARED_LATER_AFTER_DISCLOSURE": (
            "ظهر الارتفاع بعد فترة من نشر الإفصاح، وليس فورًا؛ لذلك تكون صلة الحركة "
            "بالإفصاح أضعف وقد تكون عوامل أخرى شاركت فيها."
        ),
        "NO_CLEAR_RISE_AROUND_DISCLOSURE": (
            "لم يظهر ارتفاع واضح يمكن ربطه زمنيًا بالإفصاح، لا قبله ولا بعده."
        ),
    }
    return summaries[timing]


def _arabic_opinion_summary(before: str, after: str, discussion_timing: str) -> str:
    labels = {
        "POSITIVE": "إيجابيًا",
        "NEGATIVE": "سلبيًا",
        "MIXED": "مختلطًا",
        "NEUTRAL": "محايدًا",
        "INSUFFICIENT_EVIDENCE": "غير كافٍ للحكم",
    }
    if discussion_timing == "PUBLIC_DISCUSSION_EXISTED_BEFORE_DISCLOSURE":
        opening = "وُجد نقاش عام موثق قبل نشر الإفصاح."
    elif discussion_timing == "PUBLIC_DISCUSSION_STARTED_AFTER_DISCLOSURE":
        opening = "بدأ النقاش العام الموثق بعد نشر الإفصاح."
    else:
        opening = "لم أجد نقاشًا عامًا موثقًا كافيًا حول الإفصاح."
    return (
        f"{opening} كان اتجاه الرأي قبل الإفصاح {labels[before]}، "
        f"وبعده {labels[after]}."
    )


def analyze_disclosure_reaction(packet: Mapping[str, Any]) -> dict[str, Any]:
    """Return qualitative disclosure/public-opinion timing only; no price numbers."""

    try:
        input_sha256 = _digest(packet)
        validated = validate_disclosure_reaction_packet(packet)
    except (DisclosureReactionError, TypeError, ValueError) as exc:
        return {
            "schema_version": "1.0",
            "product_id": PRODUCT_ID,
            "status": "STOP_INSUFFICIENT_EVIDENCE",
            "input_sha256": None,
            "packet_id": None,
            "disclosure_id": None,
            "disclosure_headline": None,
            "official_source_url": None,
            "price_behavior": None,
            "public_opinion": None,
            "narrative_ar": None,
            "numbers_exposed": False,
            "causality_claim_allowed": False,
            "errors": [f"DISCLOSURE_REACTION_PACKET_INVALID:{exc}"],
            "warnings": [],
        }

    pre = validated["pre_sessions"]
    post = validated["post_sessions"]
    threshold = float(validated["policy"]["movement_threshold_pct"])
    before_value = _excess_move(pre[0], pre[-1])
    immediate_value = _excess_move(pre[-1], post[IMMEDIATE_POST_SESSIONS - 1])
    after_value = _excess_move(pre[-1], post[-1])
    before = _movement_label(before_value, threshold)
    immediate = _movement_label(immediate_value, threshold)
    after = _movement_label(after_value, threshold)
    timing = _timing_conclusion(before, immediate, after)

    disclosure_available = _aware(
        validated["disclosure"]["available_at"], "disclosure.available_at"
    )
    before_opinion = [
        row
        for row in validated["public_opinion"]
        if _aware(row["published_at"], "opinion.published_at") < disclosure_available
    ]
    after_opinion = [
        row
        for row in validated["public_opinion"]
        if _aware(row["published_at"], "opinion.published_at") >= disclosure_available
    ]
    before_stance = _opinion_label(before_opinion)
    after_stance = _opinion_label(after_opinion)
    if before_opinion:
        discussion_timing = "PUBLIC_DISCUSSION_EXISTED_BEFORE_DISCLOSURE"
    elif after_opinion:
        discussion_timing = "PUBLIC_DISCUSSION_STARTED_AFTER_DISCLOSURE"
    else:
        discussion_timing = "NO_VERIFIED_PUBLIC_DISCUSSION"
    channels = sorted(
        {str(row["source_kind"]) for row in validated["public_opinion"]}
    )
    price_summary = _arabic_price_summary(timing)
    opinion_summary = _arabic_opinion_summary(
        before_stance, after_stance, discussion_timing
    )
    warnings = [
        "PRICE_MOVEMENT_IS_ASSOCIATION_NOT_CAUSATION",
        "PUBLIC_OPINION_IS_SOURCE_BACKED_COMMENTARY_NOT_A_COMPANY_FACT",
    ]
    if before_opinion:
        warnings.append(
            "PRE_DISCLOSURE_PUBLIC_DISCUSSION_REQUIRES_REVIEW_BUT_DOES_NOT_PROVE_LEAKAGE"
        )
    return {
        "schema_version": "1.0",
        "product_id": PRODUCT_ID,
        "status": "QUALITATIVE_REACTION_READY",
        "input_sha256": input_sha256,
        "packet_id": validated["packet_id"],
        "disclosure_id": validated["disclosure"]["disclosure_id"],
        "disclosure_headline": validated["disclosure"]["headline"],
        "official_source_url": validated["disclosure"]["official_source_url"],
        "price_behavior": {
            "before_disclosure": before,
            "immediately_after_disclosure": immediate,
            "after_disclosure_window": after,
            "timing_conclusion": timing,
            "disclosure_association": _association(timing),
        },
        "public_opinion": {
            "before_disclosure": before_stance,
            "after_disclosure": after_stance,
            "discussion_timing": discussion_timing,
            "source_channels": channels,
        },
        "narrative_ar": f"{price_summary} {opinion_summary}",
        "numbers_exposed": False,
        "causality_claim_allowed": False,
        "errors": [],
        "warnings": sorted(warnings),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Classify a HUMANSOFT official disclosure by qualitative price timing "
            "and source-backed public opinion without exposing market numbers."
        )
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        packet = json.loads(args.input.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DisclosureReactionError(f"cannot read input packet: {exc}") from exc
    result = analyze_disclosure_reaction(packet)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0 if result["status"] == "QUALITATIVE_REACTION_READY" else 2


__all__ = [
    "DisclosureReactionError",
    "PRODUCT_ID",
    "analyze_disclosure_reaction",
    "validate_disclosure_reaction_packet",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
