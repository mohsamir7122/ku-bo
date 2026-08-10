from __future__ import annotations

import unittest

from kubo.ca_adjustments import calculate_adjustment, formula_self_check


class CorporateActionAdjustmentTests(unittest.TestCase):
    @staticmethod
    def _terms(**changes: str) -> dict[str, str]:
        values = {
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
            "formula_notes": "unit test",
        }
        values.update(changes)
        return values

    def test_cash_dividend_keeps_return_cash_separate(self) -> None:
        result = calculate_adjustment(self._terms())
        payload = result.to_dict()
        self.assertEqual(payload["theoretical_ex_price_fils"], "95")
        self.assertEqual(payload["reference_price_factor"], "0.95")
        self.assertEqual(payload["return_price_multiplier"], "1")
        self.assertEqual(
            payload["cash_distribution_per_pre_action_share_fils"],
            "5",
        )
        self.assertEqual(
            result.return_engine_treatment,
            "RAW_PRICE_PLUS_CASH_COMPONENT",
        )
        self.assertTrue(result.return_engine_ready)
        self.assertIn(
            "NORMAL_CASH_ADJUSTED_PRICE_IS_NOT_TRADING_REFERENCE_PRICE",
            result.limitations,
        )

    def test_bonus_and_split_use_quantity_multiplier(self) -> None:
        bonus = calculate_adjustment(
            self._terms(
                action_type="BONUS_SHARES",
                cash_per_share_fils="",
                new_shares_per_old_share="0.25",
                fractional_entitlement_policy="EXACT_FRACTIONAL_ENTITLEMENT",
            )
        ).to_dict()
        self.assertEqual(bonus["theoretical_ex_price_fils"], "80")
        self.assertEqual(bonus["historical_continuity_factor"], "0.8")
        self.assertEqual(bonus["position_quantity_multiplier"], "1.25")
        self.assertEqual(bonus["return_price_multiplier"], "1.25")

        split = calculate_adjustment(
            self._terms(
                action_type="STOCK_SPLIT",
                cash_per_share_fils="",
                new_shares_per_old_share="2",
                fractional_entitlement_policy="NOT_APPLICABLE",
            )
        ).to_dict()
        self.assertEqual(split["theoretical_ex_price_fils"], "50")
        self.assertEqual(split["position_quantity_multiplier"], "2")

    def test_rights_terp_is_not_return_engine_ready(self) -> None:
        result = calculate_adjustment(
            self._terms(
                action_type="RIGHTS_ISSUE",
                cash_per_share_fils="",
                rights_new_shares_per_old_share="0.5",
                subscription_price_fils="60",
                fractional_entitlement_policy="UNKNOWN",
            )
        )
        payload = result.to_dict()
        self.assertEqual(payload["theoretical_ex_price_fils"], "86.666666666667")
        self.assertEqual(
            payload["rights_cash_contribution_per_pre_action_share_fils"],
            "30",
        )
        self.assertFalse(result.return_engine_ready)
        self.assertEqual(
            result.return_engine_treatment,
            "BLOCKED_RIGHTS_EXERCISE_OR_SALE_POLICY",
        )

    def test_ambiguous_actions_cannot_use_mechanical_formula(self) -> None:
        with self.assertRaisesRegex(ValueError, "not permitted"):
            calculate_adjustment(
                self._terms(
                    action_type="CAPITAL_REDUCTION",
                    cash_per_share_fils="",
                )
            )

    def test_official_reference_price_requires_return_terms_separately(self) -> None:
        result = calculate_adjustment(
            self._terms(
                action_type="BONUS_SHARES",
                formula_mode="OFFICIAL_REFERENCE_PRICE",
                cash_per_share_fils="",
                official_reference_price_fils="80",
                official_position_quantity_multiplier="",
                fractional_entitlement_policy="UNKNOWN",
            )
        )
        self.assertEqual(result.factor_status, "official")
        self.assertEqual(result.to_dict()["reference_price_factor"], "0.8")
        self.assertFalse(result.return_engine_ready)

    def test_no_automatic_formula_remains_pending(self) -> None:
        result = calculate_adjustment(
            self._terms(
                action_type="MERGER",
                formula_mode="NO_AUTOMATIC_FORMULA",
                previous_close_fils="",
                cash_per_share_fils="",
                fractional_entitlement_policy="UNKNOWN",
            )
        )
        self.assertEqual(result.factor_status, "pending")
        self.assertFalse(result.return_engine_ready)
        self.assertIsNone(result.reference_price_factor)

    def test_formula_self_check(self) -> None:
        self.assertEqual(formula_self_check()["status"], "PASS")


if __name__ == "__main__":
    unittest.main()
