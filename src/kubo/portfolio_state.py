"""Point-in-time portfolio and order validation with evidence-byte binding."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal, InvalidOperation
import hashlib
import os
from pathlib import Path
import re
from typing import Any, Mapping

from .foundation_io import load_strict_json_object, safe_regular_file
from .strict import parse_aware, require_sha256, safe_relative_path


SOURCE_TYPES = frozenset(
    {"BROKER_EXPORT", "USER_AUTHORIZED_EXPORT", "MANUAL_RECONCILIATION"}
)
COMPLETENESS = frozenset({"COMPLETE", "PARTIAL"})
ORDER_STATUSES = frozenset(
    {"OPEN", "PARTIALLY_FILLED", "FILLED", "CANCELLED", "REJECTED", "EXPIRED"}
)
ACTIVE_ORDER_STATUSES = frozenset({"OPEN", "PARTIALLY_FILLED"})
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SECURITY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")
_TOLERANCE = Decimal("0.001")
CLAIM_BOUNDARIES = {
    "broker_connected": False,
    "order_submitted": False,
    "portfolio_optimized": False,
    "recommendation_generated": False,
    "market_prices_verified": False,
    "structural_validation_is_execution_readiness": False,
}


class PortfolioStateError(ValueError):
    """Raised when a portfolio packet is stale, forged, or structurally invalid."""


def _exact(value: Any, keys: frozenset[str], field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or frozenset(value) != keys:
        raise PortfolioStateError(f"{field} has unknown or missing fields")
    return value


def _load(path: Path, field: str) -> tuple[dict[str, Any], bytes]:
    try:
        return load_strict_json_object(path, field=field, max_bytes=16 * 1024 * 1024)
    except ValueError as exc:
        raise PortfolioStateError(str(exc)) from exc


def _number(
    value: Any,
    field: str,
    *,
    minimum: Decimal | None = Decimal("0"),
) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PortfolioStateError(f"{field} must be a JSON number")
    try:
        parsed = Decimal(str(value))
    except InvalidOperation as exc:
        raise PortfolioStateError(f"{field} must be a finite JSON number") from exc
    if not parsed.is_finite():
        raise PortfolioStateError(f"{field} must be finite")
    if minimum is not None and parsed < minimum:
        raise PortfolioStateError(f"{field} must be >= {minimum}")
    return parsed


def _identity(value: Any, field: str, *, security: bool = False) -> str:
    pattern = _SECURITY_RE if security else _ID_RE
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise PortfolioStateError(f"{field} is invalid")
    return value


def _header(
    payload: Mapping[str, Any],
    *,
    field: str,
    decision_at: Any,
    max_age: timedelta,
) -> tuple[str, Any]:
    if payload.get("schema_version") != "1.0":
        raise PortfolioStateError(f"{field}.schema_version must be 1.0")
    portfolio_id = _identity(payload.get("portfolio_id"), f"{field}.portfolio_id")
    if payload.get("timezone") != "Asia/Kuwait" or payload.get("currency") != "KWD":
        raise PortfolioStateError(f"{field} escaped the Kuwait market identity")
    if payload.get("source_type") not in SOURCE_TYPES:
        raise PortfolioStateError(f"{field}.source_type is invalid")
    if payload.get("completeness") not in COMPLETENESS:
        raise PortfolioStateError(f"{field}.completeness is invalid")
    as_of = parse_aware(payload.get("as_of"), f"{field}.as_of")
    if as_of > decision_at:
        raise PortfolioStateError(f"{field}.as_of occurs after decision_at")
    if decision_at - as_of > max_age:
        raise PortfolioStateError(f"{field} is stale at decision_at")
    return portfolio_id, as_of


def _evidence(
    rows: Any,
    *,
    field: str,
    evidence_root: Path,
    decision_at: Any,
    max_age: timedelta,
    not_before: Any,
) -> list[dict[str, Any]]:
    if not isinstance(rows, list) or not rows or len(rows) > 64:
        raise PortfolioStateError(f"{field} must be a non-empty bounded array")
    result: list[dict[str, Any]] = []
    paths: set[str] = set()
    for index, raw in enumerate(rows):
        row = _exact(
            raw,
            frozenset({"path", "sha256", "captured_at", "source_id"}),
            f"{field}[{index}]",
        )
        relative = safe_relative_path(row.get("path"), f"{field}[{index}].path")
        normalized = relative.as_posix()
        if normalized in paths:
            raise PortfolioStateError(f"{field} contains a duplicate evidence path")
        paths.add(normalized)
        expected_hash = require_sha256(row.get("sha256"), f"{field}[{index}].sha256")
        captured_at = parse_aware(row.get("captured_at"), f"{field}[{index}].captured_at")
        if captured_at < not_before:
            raise PortfolioStateError(f"{field}[{index}] predates the declared as_of")
        if captured_at > decision_at:
            raise PortfolioStateError(f"{field}[{index}] was captured after decision_at")
        if decision_at - captured_at > max_age:
            raise PortfolioStateError(f"{field}[{index}] evidence is stale")
        source_id = _identity(row.get("source_id"), f"{field}[{index}].source_id")
        try:
            content = safe_regular_file(
                evidence_root / relative,
                field=f"{field}[{index}].path",
                max_bytes=64 * 1024 * 1024,
            )
        except ValueError as exc:
            raise PortfolioStateError(str(exc)) from exc
        actual_hash = hashlib.sha256(content).hexdigest()
        if actual_hash != expected_hash:
            raise PortfolioStateError(f"{field}[{index}] evidence hash mismatch")
        result.append(
            {
                "path": normalized,
                "sha256": actual_hash,
                "size_bytes": len(content),
                "captured_at": captured_at.isoformat(),
                "source_id": source_id,
            }
        )
    return result


def _positions(rows: Any) -> tuple[list[dict[str, Any]], Decimal]:
    if not isinstance(rows, list) or len(rows) > 10000:
        raise PortfolioStateError("positions must be a bounded array")
    result: list[dict[str, Any]] = []
    codes: set[str] = set()
    total = Decimal("0")
    keys = frozenset(
        {"security_code", "quantity", "available_quantity", "average_cost", "market_value"}
    )
    for index, raw in enumerate(rows):
        row = _exact(raw, keys, f"positions[{index}]")
        code = _identity(row.get("security_code"), f"positions[{index}].security_code", security=True)
        if code in codes:
            raise PortfolioStateError("positions contain duplicate security_code values")
        codes.add(code)
        quantity = _number(row.get("quantity"), f"positions[{index}].quantity")
        available = _number(
            row.get("available_quantity"), f"positions[{index}].available_quantity"
        )
        if available > quantity:
            raise PortfolioStateError("available position quantity exceeds total quantity")
        average_cost = _number(row.get("average_cost"), f"positions[{index}].average_cost")
        market_value = _number(row.get("market_value"), f"positions[{index}].market_value")
        total += market_value
        result.append(
            {
                "security_code": code,
                "quantity": quantity,
                "available_quantity": available,
                "average_cost": average_cost,
                "market_value": market_value,
            }
        )
    return result, total


def _orders(rows: Any, *, decision_at: Any) -> tuple[list[dict[str, Any]], int]:
    if not isinstance(rows, list) or len(rows) > 10000:
        raise PortfolioStateError("orders must be a bounded array")
    result: list[dict[str, Any]] = []
    order_ids: set[str] = set()
    active = 0
    keys = frozenset(
        {
            "order_id",
            "security_code",
            "side",
            "order_type",
            "quantity",
            "filled_quantity",
            "limit_price",
            "status",
            "submitted_at",
            "updated_at",
        }
    )
    for index, raw in enumerate(rows):
        row = _exact(raw, keys, f"orders[{index}]")
        order_id = _identity(row.get("order_id"), f"orders[{index}].order_id")
        if order_id in order_ids:
            raise PortfolioStateError("orders contain duplicate order_id values")
        order_ids.add(order_id)
        security_code = _identity(
            row.get("security_code"), f"orders[{index}].security_code", security=True
        )
        side = row.get("side")
        order_type = row.get("order_type")
        status = row.get("status")
        if side not in {"BUY", "SELL"} or order_type not in {"MARKET", "LIMIT"}:
            raise PortfolioStateError("order side or type is invalid")
        if status not in ORDER_STATUSES:
            raise PortfolioStateError("order status is invalid")
        quantity = _number(row.get("quantity"), f"orders[{index}].quantity")
        if quantity <= 0:
            raise PortfolioStateError("order quantity must be positive")
        filled = _number(row.get("filled_quantity"), f"orders[{index}].filled_quantity")
        if filled > quantity:
            raise PortfolioStateError("filled order quantity exceeds submitted quantity")
        limit_value = row.get("limit_price")
        if order_type == "MARKET":
            if limit_value is not None:
                raise PortfolioStateError("market order must not contain limit_price")
            limit_price = None
        else:
            limit_price = _number(limit_value, f"orders[{index}].limit_price")
            if limit_price <= 0:
                raise PortfolioStateError("limit order requires a positive limit_price")
        if status == "FILLED" and filled != quantity:
            raise PortfolioStateError("FILLED order must have full filled_quantity")
        if status == "OPEN" and filled != 0:
            raise PortfolioStateError("OPEN order cannot contain a filled quantity")
        if status == "PARTIALLY_FILLED" and not Decimal("0") < filled < quantity:
            raise PortfolioStateError("PARTIALLY_FILLED order has inconsistent quantities")
        submitted_at = parse_aware(row.get("submitted_at"), f"orders[{index}].submitted_at")
        updated_at = parse_aware(row.get("updated_at"), f"orders[{index}].updated_at")
        if submitted_at > updated_at or updated_at > decision_at:
            raise PortfolioStateError("order timestamps violate point-in-time ordering")
        if status in ACTIVE_ORDER_STATUSES:
            active += 1
        result.append(
            {
                "order_id": order_id,
                "security_code": security_code,
                "side": side,
                "order_type": order_type,
                "quantity": quantity,
                "filled_quantity": filled,
                "limit_price": limit_price,
                "status": status,
                "submitted_at": submitted_at,
                "updated_at": updated_at,
            }
        )
    return result, active


def validate_portfolio_state(
    snapshot_path: Path | str,
    orders_path: Path | str,
    *,
    evidence_root: Path | str,
    decision_at: Any,
    max_age_minutes: int = 30,
) -> dict[str, Any]:
    """Validate two private exports without connecting to a broker or placing orders."""

    if isinstance(max_age_minutes, bool) or not isinstance(max_age_minutes, int) or max_age_minutes <= 0:
        raise PortfolioStateError("max_age_minutes must be a positive integer")
    decision = parse_aware(decision_at, "decision_at")
    max_age = timedelta(minutes=max_age_minutes)
    evidence_candidate = Path(evidence_root)
    evidence_directory = Path(os.path.abspath(evidence_candidate))
    if not evidence_directory.is_dir() or evidence_directory.is_symlink():
        raise PortfolioStateError("evidence_root must be a regular local directory")
    snapshot, snapshot_content = _load(Path(snapshot_path), "portfolio snapshot")
    orders, orders_content = _load(Path(orders_path), "execution order ledger")
    _exact(
        snapshot,
        frozenset(
            {
                "schema_version",
                "portfolio_id",
                "as_of",
                "timezone",
                "currency",
                "source_type",
                "completeness",
                "evidence",
                "cash",
                "positions",
                "reconciliation",
            }
        ),
        "portfolio snapshot",
    )
    _exact(
        orders,
        frozenset(
            {
                "schema_version",
                "portfolio_id",
                "as_of",
                "timezone",
                "currency",
                "source_type",
                "completeness",
                "evidence",
                "orders",
            }
        ),
        "execution order ledger",
    )
    portfolio_id, snapshot_as_of = _header(
        snapshot, field="portfolio snapshot", decision_at=decision, max_age=max_age
    )
    orders_portfolio_id, orders_as_of = _header(
        orders, field="execution order ledger", decision_at=decision, max_age=max_age
    )
    if portfolio_id != orders_portfolio_id:
        raise PortfolioStateError("portfolio snapshot and order ledger IDs do not match")

    snapshot_evidence = _evidence(
        snapshot.get("evidence"),
        field="portfolio snapshot evidence",
        evidence_root=evidence_directory,
        decision_at=decision,
        max_age=max_age,
        not_before=snapshot_as_of,
    )
    order_evidence = _evidence(
        orders.get("evidence"),
        field="execution order evidence",
        evidence_root=evidence_directory,
        decision_at=decision,
        max_age=max_age,
        not_before=orders_as_of,
    )
    cash = _exact(
        snapshot.get("cash"),
        frozenset({"available", "settled", "reserved"}),
        "cash",
    )
    settled_cash = _number(cash.get("settled"), "cash.settled")
    _number(cash.get("available"), "cash.available")
    _number(cash.get("reserved"), "cash.reserved")
    positions, position_market_value = _positions(snapshot.get("positions"))
    order_rows, active_order_count = _orders(orders.get("orders"), decision_at=decision)

    reconciliation = _exact(
        snapshot.get("reconciliation"),
        frozenset({"broker_total_equity", "computed_total_equity", "difference", "status"}),
        "reconciliation",
    )
    broker_total = _number(reconciliation.get("broker_total_equity"), "reconciliation.broker_total_equity")
    computed_total = _number(
        reconciliation.get("computed_total_equity"),
        "reconciliation.computed_total_equity",
    )
    difference = _number(
        reconciliation.get("difference"),
        "reconciliation.difference",
        minimum=None,
    )
    expected_computed = settled_cash + position_market_value
    if abs(computed_total - expected_computed) > _TOLERANCE:
        raise PortfolioStateError("computed_total_equity does not reconcile to cash and positions")
    if abs((broker_total - computed_total) - difference) > _TOLERANCE:
        raise PortfolioStateError("reconciliation difference is arithmetically inconsistent")
    reconciliation_status = reconciliation.get("status")
    if reconciliation_status not in {"MATCHED", "UNRESOLVED"}:
        raise PortfolioStateError("reconciliation.status is invalid")
    if reconciliation_status == "MATCHED" and abs(difference) > _TOLERANCE:
        raise PortfolioStateError("MATCHED reconciliation exceeds the KWD tolerance")

    warnings: list[str] = []
    if snapshot.get("completeness") == "PARTIAL":
        warnings.append("PORTFOLIO_SNAPSHOT_PARTIAL")
    if orders.get("completeness") == "PARTIAL":
        warnings.append("ORDER_LEDGER_PARTIAL")
    if reconciliation_status == "UNRESOLVED":
        warnings.append("PORTFOLIO_RECONCILIATION_UNRESOLVED")
    if active_order_count and reconciliation_status == "UNRESOLVED":
        warnings.append("ACTIVE_ORDERS_WITH_UNRESOLVED_RECONCILIATION")
    if snapshot_as_of != orders_as_of:
        warnings.append("SNAPSHOT_AND_ORDER_LEDGER_AS_OF_DIFFER")
    status = (
        "PASS_STRUCTURAL_NON_ACTIONABLE"
        if not warnings
        else "PARTIAL_STRUCTURAL_NON_ACTIONABLE"
    )
    evidence_by_path: dict[tuple[str, str], dict[str, Any]] = {}
    for row in snapshot_evidence + order_evidence:
        evidence_by_path[(row["path"], row["sha256"])] = row
    return {
        "schema_version": "1.0",
        "status": status,
        "portfolio_id": portfolio_id,
        "decision_at": decision.isoformat(),
        "snapshot_as_of": snapshot_as_of.isoformat(),
        "orders_as_of": orders_as_of.isoformat(),
        "snapshot_sha256": hashlib.sha256(snapshot_content).hexdigest(),
        "orders_sha256": hashlib.sha256(orders_content).hexdigest(),
        "evidence_files": sorted(evidence_by_path.values(), key=lambda row: row["path"]),
        "position_count": len(positions),
        "order_count": len(order_rows),
        "active_order_count": active_order_count,
        "reconciliation_status": reconciliation_status,
        "warnings": warnings,
        "actionable": False,
        "claim_boundaries": CLAIM_BOUNDARIES,
    }


__all__ = ["PortfolioStateError", "validate_portfolio_state"]
