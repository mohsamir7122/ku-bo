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
CANONICAL_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
SECURITY_CODE_PATTERN = re.compile(r"^[0-9]{1,12}$")
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
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty JSON string")
    return value


def _canonical_identifier(value: Any, field: str) -> str:
    text = _nonempty_string(value, field)
    if not CANONICAL_IDENTIFIER_PATTERN.fullmatch(text):
        raise ValueError(
            f"{field} must be a canonical ASCII identifier (1..128 safe characters)"
        )
    return text


def _string_tuple(
    value: Any, field: str, *, canonical_whitespace: bool = False
) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    if any(not isinstance(item, str) for item in value):
        raise ValueError(f"{field} must contain JSON strings")
    if canonical_whitespace and any(item != item.strip() for item in value):
        raise ValueError(f"{field} must not contain surrounding whitespace")
    result = tuple(item if canonical_whitespace else item.strip() for item in value)
    if any(not item for item in result) or len(set(result)) != len(result):
        raise ValueError(f"{field} must contain unique non-empty strings")
    return result


def _enum_string(payload: dict[str, Any], field: str, default: str) -> str:
    value = payload.get(field, default)
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a JSON string")
    return value


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

        mode = _enum_string(payload, "mode", "research_network")
        scope = _enum_string(payload, "scope", "CANDIDATE_SET")
        claim_type = _enum_string(payload, "claim_type", "RESEARCH_RANK")
        output_format = _enum_string(payload, "output_format", "json")
        detail_level = _enum_string(payload, "detail_level", "standard")
        language = _enum_string(payload, "language", "ar")
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

        security_codes = _string_tuple(
            payload.get("security_codes"),
            "security_codes",
            canonical_whitespace=True,
        )
        if any(not SECURITY_CODE_PATTERN.fullmatch(code) for code in security_codes):
            raise ValueError("security_codes must contain 1..12 digit official numeric codes")
        if scope == "NAMED_SECURITIES" and not security_codes:
            raise ValueError("NAMED_SECURITIES requires security_codes")
        if claim_type == "SINGLE_SECURITY":
            if scope != "NAMED_SECURITIES":
                raise ValueError("SINGLE_SECURITY requires scope NAMED_SECURITIES")
            if len(security_codes) != 1:
                raise ValueError("SINGLE_SECURITY requires exactly one security_code")
        if claim_type == "COMPARISON":
            if scope != "NAMED_SECURITIES":
                raise ValueError("COMPARISON requires scope NAMED_SECURITIES")
            if len(security_codes) < 2:
                raise ValueError("COMPARISON requires at least two security_codes")
        if claim_type == "RESEARCH_RANK":
            if scope not in {"CANDIDATE_SET", "FULL_MARKET"}:
                raise ValueError("RESEARCH_RANK requires scope CANDIDATE_SET or FULL_MARKET")
            if security_codes:
                raise ValueError("RESEARCH_RANK does not accept security_codes")

        top_k = payload.get("top_k", 5)
        if type(top_k) is not int:
            raise ValueError("top_k must be a JSON integer")
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
            request_id=_canonical_identifier(payload.get("request_id"), "request_id"),
            product_id=_canonical_identifier(payload.get("product_id"), "product_id"),
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
        payload = asdict(self)
        payload["security_codes"] = list(self.security_codes)
        payload["requested_fields"] = list(self.requested_fields)
        return payload


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
