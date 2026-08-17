from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
import argparse
import json
from pathlib import Path
from typing import Any

from .disclosure_reaction_common import (
    DisclosureReactionError,
    IMMEDIATE_POST_SESSIONS,
    PRODUCT_ID,
    aware,
    digest,
)
from .disclosure_reaction_packet import validate_disclosure_reaction_packet


def _return_pct(start: float, end: float) -> float:
    return (end / start - 1.0) * 100.0


def _excess_move(start: Mapping[str, Any], end: Mapping[str, Any]) -> float:
    stock = _return_pct(float(start["stock_total_return_index"]), float(end["stock_total_return_index"]))
    market = _return_pct(float(start["market_total_return_index"]), float(end["market_total_return_index"]))
    sector = _return_pct(float(start["sector_total_return_index"]), float(end["sector_total_return_index"]))
    return ((stock - market) + (stock - sector)) / 2.0


def _movement_label(value: float, threshold: float) -> str:
    if value >= threshold:
        return "RISING"
    if value <= -threshold:
        return "FALLING"
    return "NO_CLEAR_MOVE"


def _timing_conclusion(before: str, immediate: str, after: str) -> str:
    if before == "RISING" and after == "RISING":
        return "RISE_STARTED_BEFORE_AND_CONTINUED_AFTER"
    if before == "RISING":
        return "RISE_STARTED_BEFORE_DISCLOSURE"
    if immediate == "RISING" and after == "RISING":
        return "RISE_STARTED_IMMEDIATELY_AFTER_DISCLOSURE"
    if immediate == "RISING":
        return "SHORT_RISE_AFTER_DISCLOSURE_THEN_FADED"
    if after == "RISING":
        return "RISE_APPEARED_LATER_AFTER_DISCLOSURE"
    return "NO_CLEAR_RISE_AROUND_DISCLOSURE"


def _association(timing: str) -> str:
    if timing in {"RISE_STARTED_BEFORE_AND_CONTINUED_AFTER", "RISE_STARTED_BEFORE_DISCLOSURE"}:
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
    collapsed = [next(iter(stances)) if len(stances) == 1 else "MIXED" for stances in by_group.values()]
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
        "RISE_STARTED_BEFORE_AND_CONTINUED_AFTER": "كان السهم يرتفع قبل نشر الإفصاح واستمر الارتفاع بعده؛ لذلك لا يصح اعتبار الإفصاح نقطة بداية الحركة أو سببها الوحيد.",
        "RISE_STARTED_BEFORE_DISCLOSURE": "بدأ ارتفاع السهم قبل نشر الإفصاح، ولم يظهر استمرار واضح بعده؛ الحركة سبقت الخبر الرسمي.",
        "RISE_STARTED_IMMEDIATELY_AFTER_DISCLOSURE": "لم يظهر ارتفاع واضح قبل الإفصاح، وبدأ الارتفاع مباشرة بعد نشره؛ توجد علاقة زمنية بالخبر دون إثبات أنه السبب الوحيد.",
        "SHORT_RISE_AFTER_DISCLOSURE_THEN_FADED": "ظهر ارتفاع قصير بعد نشر الإفصاح ثم تلاشى؛ كان التفاعل إيجابيًا مؤقتًا ولم يتحول إلى اتجاه صاعد مستمر.",
        "RISE_APPEARED_LATER_AFTER_DISCLOSURE": "ظهر الارتفاع بعد فترة من نشر الإفصاح وليس فورًا؛ لذلك تكون صلة الحركة بالإفصاح أضعف وقد تكون هناك عوامل أخرى مشتركة.",
        "NO_CLEAR_RISE_AROUND_DISCLOSURE": "لم يظهر ارتفاع واضح يمكن ربطه زمنيًا بالإفصاح، لا قبله ولا بعده.",
    }
    return summaries[timing]


def _arabic_opinion_summary(before: str, after: str, discussion_timing: str) -> str:
    labels = {
        "POSITIVE": "إيجابيًا", "NEGATIVE": "سلبيًا", "MIXED": "مختلطًا",
        "NEUTRAL": "محايدًا", "INSUFFICIENT_EVIDENCE": "غير كافٍ للحكم",
    }
    if discussion_timing == "PUBLIC_DISCUSSION_EXISTED_BEFORE_DISCLOSURE":
        opening = "وُجد نقاش عام موثق قبل نشر الإفصاح، وهذا يستحق المراجعة لكنه لا يثبت تسريبًا."
    elif discussion_timing == "PUBLIC_DISCUSSION_STARTED_AFTER_DISCLOSURE":
        opening = "بدأ النقاش العام الموثق بعد نشر الإفصاح."
    else:
        opening = "لم أجد نقاشًا عامًا موثقًا كافيًا حول الإفصاح."
    return f"{opening} كان اتجاه الرأي قبل الإفصاح {labels[before]}، وبعده {labels[after]}."


def analyze_disclosure_reaction(packet: Mapping[str, Any]) -> dict[str, Any]:
    try:
        input_sha256 = digest(packet)
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
            "data_separation": None,
            "narrative_ar": None,
            "numbers_exposed": False,
            "causality_claim_allowed": False,
            "errors": [f"DISCLOSURE_REACTION_PACKET_INVALID:{exc}"],
            "warnings": [],
        }

    disclosure = validated["historical_disclosure"]
    window = validated["historical_market_window"]
    opinion_archive = validated["public_opinion_archive"]
    pre = window["pre_sessions"]
    post = window["post_sessions"]
    threshold = float(validated["policy"]["movement_threshold_pct"])
    before = _movement_label(_excess_move(pre[0], pre[-1]), threshold)
    immediate = _movement_label(_excess_move(pre[-1], post[IMMEDIATE_POST_SESSIONS - 1]), threshold)
    after = _movement_label(_excess_move(pre[-1], post[-1]), threshold)
    timing = _timing_conclusion(before, immediate, after)

    disclosure_available = aware(disclosure["available_at"], "historical_disclosure.available_at")
    before_rows = [
        row for row in opinion_archive["items"]
        if row["relevance"] == "DIRECT_DISCLOSURE_REACTION"
        and aware(row["published_at"], "opinion.published_at") < disclosure_available
    ]
    after_rows = [
        row for row in opinion_archive["items"]
        if row["relevance"] == "DIRECT_DISCLOSURE_REACTION"
        and aware(row["published_at"], "opinion.published_at") >= disclosure_available
    ]
    before_stance = _opinion_label(before_rows)
    after_stance = _opinion_label(after_rows)
    if before_rows:
        discussion_timing = "PUBLIC_DISCUSSION_EXISTED_BEFORE_DISCLOSURE"
    elif after_rows:
        discussion_timing = "PUBLIC_DISCUSSION_STARTED_AFTER_DISCLOSURE"
    else:
        discussion_timing = "NO_VERIFIED_PUBLIC_DISCUSSION"
    channels = sorted({str(row["source_kind"]) for row in opinion_archive["items"]})
    warnings = [
        "PRICE_MOVEMENT_IS_ASSOCIATION_NOT_CAUSATION",
        "PUBLIC_OPINION_IS_SOURCE_BACKED_COMMENTARY_NOT_A_COMPANY_FACT",
    ]
    if before_rows:
        warnings.append("PRE_DISCLOSURE_PUBLIC_DISCUSSION_DOES_NOT_PROVE_LEAKAGE")
    price_summary = _arabic_price_summary(timing)
    opinion_summary = _arabic_opinion_summary(before_stance, after_stance, discussion_timing)
    return {
        "schema_version": "1.0",
        "product_id": PRODUCT_ID,
        "status": "QUALITATIVE_REACTION_READY",
        "input_sha256": input_sha256,
        "packet_id": validated["packet_id"],
        "disclosure_id": disclosure["record_id"],
        "disclosure_headline": disclosure["headline"],
        "official_source_url": disclosure["official_source_url"],
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
        "data_separation": {
            "historical_disclosure_domain": "HISTORICAL_DISCLOSURE_ARCHIVE",
            "historical_market_domain": "HISTORICAL_EVENT_MARKET_WINDOW",
            "public_opinion_domain": "HISTORICAL_PUBLIC_OPINION_ARCHIVE",
            "recent_daily_market_used": False,
            "latest_financial_snapshot_used": False,
        },
        "narrative_ar": f"{price_summary} {opinion_summary}",
        "numbers_exposed": False,
        "causality_claim_allowed": False,
        "errors": [],
        "warnings": sorted(warnings),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Classify HUMANSOFT disclosure timing and public reaction without exposing market numbers.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        packet = json.loads(args.input.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DisclosureReactionError(f"cannot read input packet: {exc}") from exc
    result = analyze_disclosure_reaction(packet)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return 0 if result["status"] == "QUALITATIVE_REACTION_READY" else 2


__all__ = ["DisclosureReactionError", "PRODUCT_ID", "analyze_disclosure_reaction", "main"]

if __name__ == "__main__":
    raise SystemExit(main())
