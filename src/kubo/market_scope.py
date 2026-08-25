"""Locked single-market boundary for KU-BO."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping

from .foundation_io import load_strict_json_object


MARKET_SCOPE_PATH = Path("config/market_scope.json")
EXPECTED_ROOT = {
    "schema_version": "1.0",
    "scope_id": "ku-bo-kuwait-only-v1",
    "status": "LOCKED_SINGLE_MARKET",
    "jurisdiction_code": "KW",
    "market_name": "BOURSA_KUWAIT",
    "currency": "KWD",
    "timezone": "Asia/Kuwait",
    "identity_key": "security_code",
}
EXPECTED_POLICY = {
    "single_market_only": True,
    "additional_market_adapters_allowed": False,
    "runtime_market_override_allowed": False,
    "cross_market_training_allowed": False,
    "cross_market_evaluation_allowed": False,
}
EXPECTED_CLAIM_BOUNDARIES = {
    "external_research_transfers_market_validity": False,
    "generic_adapter_proves_market_support": False,
    "scope_change_requires_new_version_and_user_approval": True,
}
ROOT_KEYS = frozenset({*EXPECTED_ROOT, "policy", "claim_boundaries"})


class MarketScopeError(ValueError):
    """Raised when repository configuration escapes the locked market scope."""


def _load_object(path: Path, field: str) -> tuple[dict[str, Any], bytes]:
    try:
        return load_strict_json_object(
            path,
            field=field,
            max_bytes=1024 * 1024,
        )
    except ValueError as exc:
        raise MarketScopeError(f"cannot load strict {field} JSON: {path}") from exc


def _exact_mapping(value: Any, expected: Mapping[str, Any], field: str) -> None:
    if not isinstance(value, Mapping) or dict(value) != dict(expected):
        raise MarketScopeError(f"{field} changed outside the locked scope")


def validate_market_scope(project_root_or_path: Path | str) -> dict[str, Any]:
    """Validate the locked scope and its product-catalog binding."""

    value = Path(project_root_or_path)
    project_root = value if value.is_dir() else value.parent.parent
    path = project_root / MARKET_SCOPE_PATH if value.is_dir() else value
    payload, scope_content = _load_object(path, "market scope")
    if frozenset(payload) != ROOT_KEYS:
        raise MarketScopeError("market scope root fields changed")
    _exact_mapping({key: payload[key] for key in EXPECTED_ROOT}, EXPECTED_ROOT, "market identity")
    _exact_mapping(payload["policy"], EXPECTED_POLICY, "market policy")
    _exact_mapping(
        payload["claim_boundaries"],
        EXPECTED_CLAIM_BOUNDARIES,
        "market claim boundaries",
    )

    products_path = project_root / "config" / "products.json"
    products, _ = _load_object(products_path, "product catalog")
    if products.get("timezone") != EXPECTED_ROOT["timezone"]:
        raise MarketScopeError("product catalog timezone escapes the locked market scope")
    rows = products.get("products")
    if not isinstance(rows, list) or not rows:
        raise MarketScopeError("product catalog must contain a non-empty products array")
    product_ids: list[str] = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise MarketScopeError(f"products[{index}] must be an object")
        product_id = row.get("product_id")
        if not isinstance(product_id, str) or not product_id or product_id in product_ids:
            raise MarketScopeError("product IDs must be unique non-empty strings")
        product_ids.append(product_id)

    return {
        "schema_version": "1.0",
        "status": "PASS_KUWAIT_ONLY_MARKET_SCOPE",
        "scope_id": payload["scope_id"],
        "jurisdiction_code": payload["jurisdiction_code"],
        "market_name": payload["market_name"],
        "currency": payload["currency"],
        "timezone": payload["timezone"],
        "product_count": len(product_ids),
        "market_scope_sha256": hashlib.sha256(scope_content).hexdigest(),
        "foreign_market_adapters_allowed": False,
    }


__all__ = ["MarketScopeError", "validate_market_scope"]
