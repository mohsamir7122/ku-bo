from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any
import unicodedata


REQUEST_MODES = frozenset({"research_network", "validated_forecast"})
REQUEST_SCOPES = frozenset({"NAMED_SECURITIES", "CANDIDATE_SET", "FULL_MARKET"})
OUTPUT_FORMATS = frozenset({"json", "markdown"})
DETAIL_LEVELS = frozenset({"brief", "standard", "deep"})
LANGUAGES = frozenset({"ar", "en"})
CLAIM_TYPES = frozenset({"RESEARCH_RANK", "SINGLE_SECURITY", "COMPARISON", "EVIDENCE_AUDIT"})
FORBIDDEN_RESEARCH_FIELD_MARKERS = frozenset(
    {
        "probability",
        "probabilistic",
        "recommend",
        "entry",
        "exit",
        "guaranteedreturn",
        "targetprice",
        "stoploss",
        "buy",
        "sell",
        "احتمال",
        "توصية",
        "دخول",
        "خروج",
        "شراء",
        "بيع",
    }
)


def normalize_output_field(value: Any) -> str:
    raw = str(value or "").strip()
    raw = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", raw)
    normalized = unicodedata.normalize("NFKC", raw).casefold()
    return re.sub(r"[^\w\u0600-\u06ff]+", "_", normalized).strip("_")


def is_forbidden_research_output_field(value: Any) -> bool:
    normalized = normalize_output_field(value)
    collapsed = "".join(character for character in normalized if character.isalnum())
    return any(marker in collapsed for marker in FORBIDDEN_RESEARCH_FIELD_MARKERS)


def _nonempty_string(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} is required")
    return text


def _string_tuple(value: Any, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    result = tuple(str(item).strip() for item in value)
    if any(not item for item in result) or len(set(result)) != len(result):
        raise ValueError(f"{field} must contain unique non-empty strings")
    return result


@dataclass(frozen=True)
class AnalysisRequest:
    request_id: str
    product_id: str
    mode: str
    scope: str
    claim_type: str
    security_codes: tuple[str, ...]
    output_format: str
    detail_level: str
    language: str
    top_k: int
    requested_fields: tuple[str, ...]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AnalysisRequest":
        if not isinstance(payload, dict):
            raise ValueError("analysis request must be a JSON object")
        allowed = {
            "request_id",
            "product_id",
            "mode",
            "scope",
            "claim_type",
            "security_codes",
            "output_format",
            "detail_level",
            "language",
            "top_k",
            "requested_fields",
        }
        unknown = sorted(set(payload) - allowed)
        if unknown:
            raise ValueError("unknown request fields: " + ",".join(unknown))

        mode = str(payload.get("mode", "research_network"))
        scope = str(payload.get("scope", "CANDIDATE_SET"))
        claim_type = str(payload.get("claim_type", "RESEARCH_RANK"))
        output_format = str(payload.get("output_format", "json")).lower()
        detail_level = str(payload.get("detail_level", "standard")).lower()
        language = str(payload.get("language", "ar")).lower()
        for value, vocabulary, field in (
            (mode, REQUEST_MODES, "mode"),
            (scope, REQUEST_SCOPES, "scope"),
            (claim_type, CLAIM_TYPES, "claim_type"),
            (output_format, OUTPUT_FORMATS, "output_format"),
            (detail_level, DETAIL_LEVELS, "detail_level"),
            (language, LANGUAGES, "language"),
        ):
            if value not in vocabulary:
                raise ValueError(f"unsupported {field}: {value}")

        security_codes = _string_tuple(payload.get("security_codes"), "security_codes")
        if scope == "NAMED_SECURITIES" and not security_codes:
            raise ValueError("NAMED_SECURITIES requires security_codes")
        if claim_type == "SINGLE_SECURITY" and len(security_codes) != 1:
            raise ValueError("SINGLE_SECURITY requires exactly one security_code")
        if claim_type == "COMPARISON" and len(security_codes) < 2:
            raise ValueError("COMPARISON requires at least two security_codes")

        try:
            top_k = int(payload.get("top_k", 5))
        except (TypeError, ValueError) as exc:
            raise ValueError("top_k must be an integer") from exc
        if not 1 <= top_k <= 100:
            raise ValueError("top_k must be between 1 and 100")

        requested_fields = tuple(
            normalize_output_field(item)
            for item in _string_tuple(payload.get("requested_fields"), "requested_fields")
        )
        if len(requested_fields) != len(set(requested_fields)):
            raise ValueError("requested_fields must remain unique after normalization")
        if mode == "research_network" and any(
            is_forbidden_research_output_field(item) for item in requested_fields
        ):
            raise ValueError("research_network cannot request forecast, execution, or recommendation fields")

        return cls(
            request_id=_nonempty_string(payload.get("request_id"), "request_id"),
            product_id=_nonempty_string(payload.get("product_id"), "product_id"),
            mode=mode,
            scope=scope,
            claim_type=claim_type,
            security_codes=security_codes,
            output_format=output_format,
            detail_level=detail_level,
            language=language,
            top_k=top_k,
            requested_fields=requested_fields,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


__all__ = [
    "AnalysisRequest",
    "CLAIM_TYPES",
    "DETAIL_LEVELS",
    "LANGUAGES",
    "OUTPUT_FORMATS",
    "FORBIDDEN_RESEARCH_FIELD_MARKERS",
    "REQUEST_MODES",
    "REQUEST_SCOPES",
    "is_forbidden_research_output_field",
    "normalize_output_field",
]
