from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any


ACTION_TYPES = frozenset(
    {
        "CASH_DIVIDEND_NORMAL",
        "CASH_DIVIDEND_SPECIAL",
        "BONUS_SHARES",
        "STOCK_SPLIT",
        "REVERSE_SPLIT",
        "RIGHTS_ISSUE",
        "CAPITAL_REDUCTION",
        "MERGER",
        "PAR_VALUE_CHANGE",
        "OTHER",
    }
)
FORMULA_MODES = frozenset(
    {
        "OFFICIAL_FACTOR",
        "OFFICIAL_REFERENCE_PRICE",
        "REPRODUCIBLE_MECHANICAL",
        "NO_AUTOMATIC_FORMULA",
    }
)
FRACTIONAL_POLICIES = frozenset(
    {
        "NOT_APPLICABLE",
        "UNKNOWN",
        "ROUND_DOWN",
        "CASH_IN_LIEU",
        "EXACT_FRACTIONAL_ENTITLEMENT",
    }
)
_DECIMAL_QUANTUM = Decimal("0.000000000001")


@dataclass(frozen=True)
class AdjustmentResult:
    action_type: str
    formula_mode: str
    factor_status: str
    formula_id: str
    previous_close_fils: Decimal | None
    theoretical_ex_price_fils: Decimal | None
    reference_price_factor: Decimal | None
    historical_continuity_factor: Decimal | None
    position_quantity_multiplier: Decimal | None
    return_price_multiplier: Decimal | None
    cash_distribution_per_pre_action_share_fils: Decimal | None
    rights_cash_contribution_per_pre_action_share_fils: Decimal | None
    return_engine_treatment: str
    return_engine_ready: bool
    reference_price_use: str
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        def value(item: Decimal | None) -> str | None:
            return None if item is None else _canonical_decimal(item)

        return {
            "action_type": self.action_type,
            "formula_mode": self.formula_mode,
            "factor_status": self.factor_status,
            "formula_id": self.formula_id,
            "previous_close_fils": value(self.previous_close_fils),
            "theoretical_ex_price_fils": value(self.theoretical_ex_price_fils),
            "reference_price_factor": value(self.reference_price_factor),
            "historical_continuity_factor": value(
                self.historical_continuity_factor
            ),
            "position_quantity_multiplier": value(
                self.position_quantity_multiplier
            ),
            "return_price_multiplier": value(self.return_price_multiplier),
            "cash_distribution_per_pre_action_share_fils": value(
                self.cash_distribution_per_pre_action_share_fils
            ),
            "rights_cash_contribution_per_pre_action_share_fils": value(
                self.rights_cash_contribution_per_pre_action_share_fils
            ),
            "return_engine_treatment": self.return_engine_treatment,
            "return_engine_ready": self.return_engine_ready,
            "reference_price_use": self.reference_price_use,
            "limitations": list(self.limitations),
        }


def _decimal(
    value: Any,
    field: str,
    *,
    positive: bool = False,
    non_negative: bool = False,
) -> Decimal:
    if isinstance(value, bool) or value in (None, ""):
        raise ValueError(f"{field} must be a decimal number")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be a decimal number") from exc
    if not parsed.is_finite():
        raise ValueError(f"{field} must be finite")
    if positive and parsed <= 0:
        raise ValueError(f"{field} must be positive")
    if non_negative and parsed < 0:
        raise ValueError(f"{field} must be non-negative")
    return parsed


def _optional_decimal(
    value: Any,
    field: str,
    *,
    positive: bool = False,
    non_negative: bool = False,
) -> Decimal | None:
    if value in (None, ""):
        return None
    return _decimal(
        value,
        field,
        positive=positive,
        non_negative=non_negative,
    )


def _canonical_decimal(value: Decimal) -> str:
    normalized = value.quantize(_DECIMAL_QUANTUM, rounding=ROUND_HALF_UP)
    text = format(normalized, "f").rstrip("0").rstrip(".")
    return text or "0"


def _factor(ex_price: Decimal, previous_close: Decimal) -> Decimal:
    if ex_price <= 0 or previous_close <= 0:
        raise ValueError("reference prices must be positive")
    return ex_price / previous_close


def _reference_use(action_type: str) -> str:
    if action_type == "CASH_DIVIDEND_NORMAL":
        return "DISPLAY_AND_TOTAL_RETURN_INDEX_ONLY"
    if action_type == "CASH_DIVIDEND_SPECIAL":
        return "TRADING_REFERENCE_AND_INDEX"
    return "CORPORATE_ACTION_REFERENCE"


def calculate_adjustment(terms: dict[str, Any]) -> AdjustmentResult:
    if not isinstance(terms, dict):
        raise ValueError("corporate-action terms must be an object")
    expected_fields = {
        "action_type",
        "formula_mode",
        "previous_close_fils",
        "cash_per_share_fils",
        "new_shares_per_old_share",
        "rights_new_shares_per_old_share",
        "subscription_price_fils",
        "official_reference_price_fils",
        "official_factor",
        "official_position_quantity_multiplier",
        "fractional_entitlement_policy",
        "formula_notes",
    }
    if set(terms) != expected_fields:
        raise ValueError("corporate-action terms have unknown or missing fields")
    action_type = str(terms["action_type"])
    formula_mode = str(terms["formula_mode"])
    fractional_policy = str(terms["fractional_entitlement_policy"])
    if action_type not in ACTION_TYPES:
        raise ValueError(f"unsupported action_type: {action_type}")
    if formula_mode not in FORMULA_MODES:
        raise ValueError(f"unsupported formula_mode: {formula_mode}")
    if fractional_policy not in FRACTIONAL_POLICIES:
        raise ValueError(
            f"unsupported fractional_entitlement_policy: {fractional_policy}"
        )

    previous_close = _optional_decimal(
        terms["previous_close_fils"],
        "previous_close_fils",
        positive=True,
    )
    cash = _optional_decimal(
        terms["cash_per_share_fils"],
        "cash_per_share_fils",
        non_negative=True,
    )
    new_shares = _optional_decimal(
        terms["new_shares_per_old_share"],
        "new_shares_per_old_share",
        positive=True,
    )
    rights_ratio = _optional_decimal(
        terms["rights_new_shares_per_old_share"],
        "rights_new_shares_per_old_share",
        positive=True,
    )
    subscription_price = _optional_decimal(
        terms["subscription_price_fils"],
        "subscription_price_fils",
        non_negative=True,
    )
    official_reference = _optional_decimal(
        terms["official_reference_price_fils"],
        "official_reference_price_fils",
        positive=True,
    )
    official_factor = _optional_decimal(
        terms["official_factor"],
        "official_factor",
        positive=True,
    )
    official_quantity = _optional_decimal(
        terms["official_position_quantity_multiplier"],
        "official_position_quantity_multiplier",
        positive=True,
    )

    if formula_mode == "NO_AUTOMATIC_FORMULA":
        if any(
            value is not None
            for value in (
                official_reference,
                official_factor,
                official_quantity,
            )
        ):
            raise ValueError(
                "NO_AUTOMATIC_FORMULA cannot carry official calculated values"
            )
        return AdjustmentResult(
            action_type=action_type,
            formula_mode=formula_mode,
            factor_status="pending",
            formula_id="pending_official_terms_v1",
            previous_close_fils=previous_close,
            theoretical_ex_price_fils=None,
            reference_price_factor=None,
            historical_continuity_factor=None,
            position_quantity_multiplier=None,
            return_price_multiplier=None,
            cash_distribution_per_pre_action_share_fils=cash,
            rights_cash_contribution_per_pre_action_share_fils=None,
            return_engine_treatment="BLOCKED_PENDING_OFFICIAL_TERMS",
            return_engine_ready=False,
            reference_price_use="UNRESOLVED",
            limitations=(
                "ACTION_TYPE_OR_FACTOR_REQUIRES_OFFICIAL_DISCLOSURE",
            ),
        )

    if formula_mode == "OFFICIAL_FACTOR":
        if official_factor is None:
            raise ValueError("OFFICIAL_FACTOR requires official_factor")
        theoretical = (
            None
            if previous_close is None
            else previous_close * official_factor
        )
        quantity = official_quantity
        return_ready = action_type in {
            "CASH_DIVIDEND_NORMAL",
            "CASH_DIVIDEND_SPECIAL",
            "BONUS_SHARES",
            "STOCK_SPLIT",
            "REVERSE_SPLIT",
        } and (
            action_type.startswith("CASH_DIVIDEND")
            or quantity is not None
        )
        if action_type.startswith("CASH_DIVIDEND"):
            return_multiplier = Decimal(1)
            treatment = "RAW_PRICE_PLUS_CASH_COMPONENT"
            return_ready = return_ready and cash is not None
        elif return_ready:
            return_multiplier = quantity
            treatment = "RAW_PRICE_TIMES_QUANTITY_MULTIPLIER"
        else:
            return_multiplier = None
            treatment = "BLOCKED_ACTION_SPECIFIC_RETURN_POLICY"
        limitations = () if return_ready else (
            "OFFICIAL_FACTOR_DOES_NOT_COMPLETE_RETURN_ENGINE_POLICY",
        )
        return AdjustmentResult(
            action_type=action_type,
            formula_mode=formula_mode,
            factor_status="official",
            formula_id="official_factor_v1",
            previous_close_fils=previous_close,
            theoretical_ex_price_fils=theoretical,
            reference_price_factor=official_factor,
            historical_continuity_factor=official_factor,
            position_quantity_multiplier=quantity,
            return_price_multiplier=return_multiplier,
            cash_distribution_per_pre_action_share_fils=cash,
            rights_cash_contribution_per_pre_action_share_fils=None,
            return_engine_treatment=treatment,
            return_engine_ready=return_ready,
            reference_price_use=_reference_use(action_type),
            limitations=limitations,
        )

    if formula_mode == "OFFICIAL_REFERENCE_PRICE":
        if previous_close is None or official_reference is None:
            raise ValueError(
                "OFFICIAL_REFERENCE_PRICE requires previous_close_fils and official_reference_price_fils"
            )
        reference_factor = _factor(official_reference, previous_close)
        quantity = official_quantity
        if action_type.startswith("CASH_DIVIDEND"):
            return_ready = cash is not None
            return_multiplier = Decimal(1) if return_ready else None
            treatment = (
                "RAW_PRICE_PLUS_CASH_COMPONENT"
                if return_ready
                else "BLOCKED_MISSING_CASH_COMPONENT"
            )
        elif action_type in {"BONUS_SHARES", "STOCK_SPLIT", "REVERSE_SPLIT"}:
            return_ready = quantity is not None
            return_multiplier = quantity
            treatment = (
                "RAW_PRICE_TIMES_QUANTITY_MULTIPLIER"
                if return_ready
                else "BLOCKED_MISSING_QUANTITY_MULTIPLIER"
            )
        else:
            return_ready = False
            return_multiplier = None
            treatment = "BLOCKED_ACTION_SPECIFIC_RETURN_POLICY"
        return AdjustmentResult(
            action_type=action_type,
            formula_mode=formula_mode,
            factor_status="official",
            formula_id="official_reference_price_v1",
            previous_close_fils=previous_close,
            theoretical_ex_price_fils=official_reference,
            reference_price_factor=reference_factor,
            historical_continuity_factor=reference_factor,
            position_quantity_multiplier=quantity,
            return_price_multiplier=return_multiplier,
            cash_distribution_per_pre_action_share_fils=cash,
            rights_cash_contribution_per_pre_action_share_fils=None,
            return_engine_treatment=treatment,
            return_engine_ready=return_ready,
            reference_price_use=_reference_use(action_type),
            limitations=(
                ()
                if return_ready
                else ("REFERENCE_PRICE_ALONE_DOES_NOT_COMPLETE_RETURN_POLICY",)
            ),
        )

    if previous_close is None:
        raise ValueError(
            "REPRODUCIBLE_MECHANICAL requires previous_close_fils"
        )

    if action_type in {"CASH_DIVIDEND_NORMAL", "CASH_DIVIDEND_SPECIAL"}:
        if cash is None or cash <= 0 or cash >= previous_close:
            raise ValueError(
                "cash dividend requires 0 < cash_per_share_fils < previous_close_fils"
            )
        theoretical = previous_close - cash
        reference_factor = _factor(theoretical, previous_close)
        return AdjustmentResult(
            action_type=action_type,
            formula_mode=formula_mode,
            factor_status="reproducible",
            formula_id="boursa_dividend_adjusted_price_8_14_v1",
            previous_close_fils=previous_close,
            theoretical_ex_price_fils=theoretical,
            reference_price_factor=reference_factor,
            historical_continuity_factor=reference_factor,
            position_quantity_multiplier=Decimal(1),
            return_price_multiplier=Decimal(1),
            cash_distribution_per_pre_action_share_fils=cash,
            rights_cash_contribution_per_pre_action_share_fils=None,
            return_engine_treatment="RAW_PRICE_PLUS_CASH_COMPONENT",
            return_engine_ready=True,
            reference_price_use=_reference_use(action_type),
            limitations=(
                "NORMAL_CASH_ADJUSTED_PRICE_IS_NOT_TRADING_REFERENCE_PRICE",
            )
            if action_type == "CASH_DIVIDEND_NORMAL"
            else (),
        )

    if action_type == "BONUS_SHARES":
        if new_shares is None:
            raise ValueError(
                "BONUS_SHARES requires new_shares_per_old_share"
            )
        quantity = Decimal(1) + new_shares
        theoretical = previous_close / quantity
        reference_factor = _factor(theoretical, previous_close)
        return_ready = fractional_policy in {
            "NOT_APPLICABLE",
            "EXACT_FRACTIONAL_ENTITLEMENT",
        }
        return AdjustmentResult(
            action_type=action_type,
            formula_mode=formula_mode,
            factor_status="reproducible",
            formula_id="mechanical_bonus_share_factor_v1",
            previous_close_fils=previous_close,
            theoretical_ex_price_fils=theoretical,
            reference_price_factor=reference_factor,
            historical_continuity_factor=reference_factor,
            position_quantity_multiplier=quantity,
            return_price_multiplier=quantity if return_ready else None,
            cash_distribution_per_pre_action_share_fils=None,
            rights_cash_contribution_per_pre_action_share_fils=None,
            return_engine_treatment=(
                "RAW_PRICE_TIMES_QUANTITY_MULTIPLIER"
                if return_ready
                else "BLOCKED_FRACTIONAL_ENTITLEMENT_POLICY"
            ),
            return_engine_ready=return_ready,
            reference_price_use=_reference_use(action_type),
            limitations=(
                ()
                if return_ready
                else ("FRACTIONAL_ENTITLEMENT_POLICY_REQUIRED",)
            ),
        )

    if action_type in {"STOCK_SPLIT", "REVERSE_SPLIT"}:
        if new_shares is None:
            raise ValueError(
                f"{action_type} requires new_shares_per_old_share"
            )
        quantity = new_shares
        if action_type == "STOCK_SPLIT" and quantity <= 1:
            raise ValueError("STOCK_SPLIT requires a quantity multiplier > 1")
        if action_type == "REVERSE_SPLIT" and quantity >= 1:
            raise ValueError("REVERSE_SPLIT requires a quantity multiplier < 1")
        theoretical = previous_close / quantity
        reference_factor = _factor(theoretical, previous_close)
        return_ready = fractional_policy in {
            "NOT_APPLICABLE",
            "EXACT_FRACTIONAL_ENTITLEMENT",
        }
        return AdjustmentResult(
            action_type=action_type,
            formula_mode=formula_mode,
            factor_status="reproducible",
            formula_id="mechanical_share_count_conversion_v1",
            previous_close_fils=previous_close,
            theoretical_ex_price_fils=theoretical,
            reference_price_factor=reference_factor,
            historical_continuity_factor=reference_factor,
            position_quantity_multiplier=quantity,
            return_price_multiplier=quantity if return_ready else None,
            cash_distribution_per_pre_action_share_fils=None,
            rights_cash_contribution_per_pre_action_share_fils=None,
            return_engine_treatment=(
                "RAW_PRICE_TIMES_QUANTITY_MULTIPLIER"
                if return_ready
                else "BLOCKED_FRACTIONAL_ENTITLEMENT_POLICY"
            ),
            return_engine_ready=return_ready,
            reference_price_use=_reference_use(action_type),
            limitations=(
                ()
                if return_ready
                else ("FRACTIONAL_ENTITLEMENT_POLICY_REQUIRED",)
            ),
        )

    if action_type == "RIGHTS_ISSUE":
        if rights_ratio is None or subscription_price is None:
            raise ValueError(
                "RIGHTS_ISSUE requires rights_new_shares_per_old_share and subscription_price_fils"
            )
        quantity = Decimal(1) + rights_ratio
        theoretical = (
            previous_close + rights_ratio * subscription_price
        ) / quantity
        if theoretical <= 0:
            raise ValueError("rights issue theoretical ex-price must be positive")
        reference_factor = _factor(theoretical, previous_close)
        contribution = rights_ratio * subscription_price
        return AdjustmentResult(
            action_type=action_type,
            formula_mode=formula_mode,
            factor_status="reproducible",
            formula_id="mechanical_terp_v1",
            previous_close_fils=previous_close,
            theoretical_ex_price_fils=theoretical,
            reference_price_factor=reference_factor,
            historical_continuity_factor=reference_factor,
            position_quantity_multiplier=quantity,
            return_price_multiplier=None,
            cash_distribution_per_pre_action_share_fils=None,
            rights_cash_contribution_per_pre_action_share_fils=contribution,
            return_engine_treatment="BLOCKED_RIGHTS_EXERCISE_OR_SALE_POLICY",
            return_engine_ready=False,
            reference_price_use=_reference_use(action_type),
            limitations=(
                "RIGHTS_REQUIRE_EXERCISE_SALE_OR_LAPSE_POLICY",
                "TERP_IS_MECHANICAL_NOT_AN_EXECUTION_RECEIPT",
            ),
        )

    raise ValueError(
        f"REPRODUCIBLE_MECHANICAL is not permitted for {action_type}; use official evidence or NO_AUTOMATIC_FORMULA"
    )


def formula_self_check() -> dict[str, Any]:
    examples = {
        "cash": calculate_adjustment(
            {
                "action_type": "CASH_DIVIDEND_NORMAL",
                "formula_mode": "REPRODUCIBLE_MECHANICAL",
                "previous_close_fils": "100",
                "cash_per_share_fils": "5",
                "new_shares_per_old_share": "",
                "rights_new_shares_per_old_share": "",
                "subscription_price_fils": "",
                "official_reference_price_fils": "",
                "official_factor": "",
                "official_position_quantity_multiplier": "",
                "fractional_entitlement_policy": "NOT_APPLICABLE",
                "formula_notes": "self-check",
            }
        ).to_dict(),
        "bonus": calculate_adjustment(
            {
                "action_type": "BONUS_SHARES",
                "formula_mode": "REPRODUCIBLE_MECHANICAL",
                "previous_close_fils": "100",
                "cash_per_share_fils": "",
                "new_shares_per_old_share": "0.25",
                "rights_new_shares_per_old_share": "",
                "subscription_price_fils": "",
                "official_reference_price_fils": "",
                "official_factor": "",
                "official_position_quantity_multiplier": "",
                "fractional_entitlement_policy": "EXACT_FRACTIONAL_ENTITLEMENT",
                "formula_notes": "self-check",
            }
        ).to_dict(),
        "rights": calculate_adjustment(
            {
                "action_type": "RIGHTS_ISSUE",
                "formula_mode": "REPRODUCIBLE_MECHANICAL",
                "previous_close_fils": "100",
                "cash_per_share_fils": "",
                "new_shares_per_old_share": "",
                "rights_new_shares_per_old_share": "0.5",
                "subscription_price_fils": "60",
                "official_reference_price_fils": "",
                "official_factor": "",
                "official_position_quantity_multiplier": "",
                "fractional_entitlement_policy": "UNKNOWN",
                "formula_notes": "self-check",
            }
        ).to_dict(),
    }
    passed = (
        examples["cash"]["theoretical_ex_price_fils"] == "95"
        and examples["bonus"]["position_quantity_multiplier"] == "1.25"
        and examples["rights"]["theoretical_ex_price_fils"]
        == "86.666666666667"
        and examples["rights"]["return_engine_ready"] is False
    )
    return {
        "status": "PASS" if passed else "FAIL",
        "examples": examples,
        "claim_boundaries": {
            "mechanical_factor_is_official_factor": False,
            "reference_price_factor_is_return_engine_multiplier": False,
            "rights_terp_is_execution_receipt": False,
        },
    }


__all__ = [
    "ACTION_TYPES",
    "FORMULA_MODES",
    "FRACTIONAL_POLICIES",
    "AdjustmentResult",
    "calculate_adjustment",
    "formula_self_check",
]
