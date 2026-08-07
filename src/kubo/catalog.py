from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .strict import https_url


CAPABILITY_VOCABULARY = frozenset(
    {
        "security_master",
        "security_status_history",
        "trading_calendar",
        "daily_eod",
        "daily_market_totals",
        "official_disclosures",
        "corporate_actions",
        "issuer_reports",
        "news_context",
        "social_evidence",
        "intraday_bars",
        "opening_auction",
        "l1_quotes",
        "l2_order_book",
        "execution_fields",
    }
)

SOURCE_ROLES = frozenset({"OFFICIAL_TRUTH", "AUTHORIZED_TAPE", "ISSUER_PRIMARY", "DISCOVERY", "CROSS_CHECK", "CONTEXT", "SENTIMENT", "STORAGE_ONLY"})
METHOD_STATES = frozenset({"FROZEN_BASELINE", "CANDIDATE", "UNVALIDATED_RESEARCH", "BLOCKED_CAPABILITY", "RETIRED"})


def _load(path: Path, key: str) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get(key)
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"{path.name} must contain a non-empty {key} list")
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError(f"{path.name} contains a non-object row")
    return rows


@dataclass(frozen=True)
class SourceSpec:
    source_id: str
    name: str
    role: str
    authority: str
    source_family: str
    urls: tuple[str, ...]
    access_modes: frozenset[str]
    capabilities: frozenset[str]
    delay_class: str
    market_evidence_allowed: bool
    notes: str

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> "SourceSpec":
        urls = tuple(str(item) for item in row.get("urls", []))
        for index, url in enumerate(urls):
            https_url(url, f"urls[{index}]")
        role = str(row["role"])
        if role not in SOURCE_ROLES:
            raise ValueError(f"unsupported source role: {role}")
        capabilities = frozenset(str(item) for item in row.get("capabilities", []))
        unknown = capabilities - CAPABILITY_VOCABULARY
        if unknown:
            raise ValueError(f"unknown source capabilities: {sorted(unknown)}")
        allowed = row.get("market_evidence_allowed")
        if type(allowed) is not bool:
            raise ValueError("market_evidence_allowed must be a JSON boolean")
        return cls(
            source_id=str(row["source_id"]),
            name=str(row["name"]),
            role=role,
            authority=str(row["authority"]),
            source_family=str(row["source_family"]),
            urls=urls,
            access_modes=frozenset(str(item) for item in row.get("access_modes", [])),
            capabilities=capabilities,
            delay_class=str(row["delay_class"]),
            market_evidence_allowed=allowed,
            notes=str(row.get("notes", "")),
        )


@dataclass(frozen=True)
class ProductSpec:
    product_id: str
    product_family: str
    horizon_sessions: int
    target_rule: str
    required_capabilities: frozenset[str]
    execution_grade_required: bool
    minimum_independent_dates: int
    benchmark_rule: str
    cost_policy: str
    allowed_output: str

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> "ProductSpec":
        capabilities = frozenset(str(item) for item in row.get("required_capabilities", []))
        unknown = capabilities - CAPABILITY_VOCABULARY
        if unknown:
            raise ValueError(f"unknown product capabilities: {sorted(unknown)}")
        execution = row.get("execution_grade_required")
        if type(execution) is not bool:
            raise ValueError("execution_grade_required must be a JSON boolean")
        product = cls(
            product_id=str(row["product_id"]),
            product_family=str(row["product_family"]),
            horizon_sessions=int(row["horizon_sessions"]),
            target_rule=str(row["target_rule"]),
            required_capabilities=capabilities,
            execution_grade_required=execution,
            minimum_independent_dates=int(row.get("minimum_independent_dates", 20)),
            benchmark_rule=str(row.get("benchmark_rule", "none")),
            cost_policy=str(row.get("cost_policy", "none")),
            allowed_output=str(row.get("allowed_output", "UNVALIDATED_RESEARCH_SCORE")),
        )
        if product.horizon_sessions <= 0 or product.minimum_independent_dates <= 0:
            raise ValueError(f"invalid product horizon/sample rule: {product.product_id}")
        if product.execution_grade_required and not {"intraday_bars", "l1_quotes", "execution_fields"}.issubset(product.required_capabilities):
            raise ValueError(f"execution product lacks required tape capabilities: {product.product_id}")
        if product.product_id == "opening_gap_or_limit" and "opening_auction" not in product.required_capabilities:
            raise ValueError("opening_gap_or_limit requires opening_auction")
        return product


@dataclass(frozen=True)
class MethodSpec:
    method_id: str
    family: str
    supports: frozenset[str]
    required_capabilities: frozenset[str]
    state: str
    validation_gates: frozenset[str]
    emits_probability: bool
    purpose: str

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> "MethodSpec":
        state = str(row["state"])
        if state not in METHOD_STATES:
            raise ValueError(f"unsupported method state: {state}")
        emits = row.get("emits_probability")
        if type(emits) is not bool:
            raise ValueError("emits_probability must be a JSON boolean")
        capabilities = frozenset(str(item) for item in row.get("required_capabilities", []))
        unknown = capabilities - CAPABILITY_VOCABULARY
        if unknown:
            raise ValueError(f"unknown method capabilities: {sorted(unknown)}")
        return cls(
            method_id=str(row["method_id"]),
            family=str(row["family"]),
            supports=frozenset(str(item) for item in row.get("supports", [])),
            required_capabilities=capabilities,
            state=state,
            validation_gates=frozenset(str(item) for item in row.get("validation_gates", [])),
            emits_probability=emits,
            purpose=str(row.get("purpose", "")),
        )


class Catalog:
    def __init__(self, config_dir: Path):
        source_rows = _load(config_dir / "sources.json", "sources")
        product_rows = _load(config_dir / "products.json", "products")
        method_rows = _load(config_dir / "methods.json", "methods")
        self.sources = self._unique((SourceSpec.from_dict(row) for row in source_rows), "source_id")
        self.products = self._unique((ProductSpec.from_dict(row) for row in product_rows), "product_id")
        self.methods = self._unique((MethodSpec.from_dict(row) for row in method_rows), "method_id")
        self._validate_cross_references()

    @staticmethod
    def _unique(rows: Any, field: str) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for row in rows:
            key = str(getattr(row, field))
            if not key or key in result:
                raise ValueError(f"duplicate or empty {field}: {key}")
            result[key] = row
        return result

    def _validate_cross_references(self) -> None:
        product_ids = set(self.products)
        if "project_google_drive" in self.sources:
            drive = self.sources["project_google_drive"]
            if drive.role != "STORAGE_ONLY" or drive.market_evidence_allowed:
                raise ValueError("project_google_drive must remain STORAGE_ONLY and ineligible as market evidence")
        for method in self.methods.values():
            unknown = set(method.supports) - product_ids
            if unknown:
                raise ValueError(f"{method.method_id} supports unknown products: {sorted(unknown)}")
            if method.emits_probability and "calibration" not in method.validation_gates:
                raise ValueError(f"{method.method_id} emits probability without calibration gate")

    def report(self) -> dict[str, Any]:
        return {
            "status": "PASS",
            "sources": len(self.sources),
            "products": len(self.products),
            "methods": len(self.methods),
            "capability_vocabulary": sorted(CAPABILITY_VOCABULARY),
        }


__all__ = ["CAPABILITY_VOCABULARY", "Catalog", "MethodSpec", "ProductSpec", "SourceSpec"]
