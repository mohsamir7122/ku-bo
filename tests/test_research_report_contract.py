from __future__ import annotations

import unittest

from kubo.research_ledger import validate_research_report

from tests.test_research_ledger import built_report


class ResearchReportLedgerBoundaryTests(unittest.TestCase):
    def test_request_is_reparsed_at_the_ledger_boundary(self) -> None:
        report = built_report()
        report["request"].update(
            {
                "scope": "CANDIDATE_SET",
                "claim_type": "SINGLE_SECURITY",
                "security_codes": ["101"],
            }
        )
        self.assertIn("REQUEST_CONTRACT_INVALID", validate_research_report(report))

    def test_full_market_boundary_is_bound_across_report_surfaces(self) -> None:
        report = built_report()
        report["full_market_claim_allowed"] = True
        errors = validate_research_report(report)
        self.assertIn("FULL_MARKET_BOUNDARY_BINDING_MISMATCH", errors)
        self.assertIn("FULL_MARKET_CLAIM_WITHOUT_EXACT_FULL_MARKET_PACKET", errors)

    def test_exact_full_market_ready_cannot_hide_a_role_boundary_failure(self) -> None:
        report = built_report()
        report["scope"] = "FULL_MARKET"
        report["exact_universe_reconciled"] = True
        report["full_market_claim_allowed"] = False
        report["claim_boundaries"]["full_market_claim_allowed"] = False
        self.assertIn(
            "EXACT_FULL_MARKET_READY_WITHOUT_CLAIM_BOUNDARY",
            validate_research_report(report),
        )

    def test_full_market_label_cannot_exist_when_boundary_is_false(self) -> None:
        report = built_report()
        report["candidates"][0]["scope_label"] = "FULL_MARKET_RESEARCH_RANK"
        self.assertIn(
            "FULL_MARKET_LABEL_WITHOUT_CLAIM_BOUNDARY",
            validate_research_report(report),
        )

    def test_consistent_full_market_report_is_accepted(self) -> None:
        report = built_report()
        report["scope"] = "FULL_MARKET"
        report["exact_universe_reconciled"] = True
        report["full_market_claim_allowed"] = True
        report["claim_boundaries"]["full_market_claim_allowed"] = True
        report["candidates"][0]["scope_label"] = "FULL_MARKET_RESEARCH_RANK"
        report["candidates"][0]["per_security_role_gaps"] = {}
        self.assertEqual(validate_research_report(report), [])

    def test_candidate_identity_rejects_noncanonical_code_and_ticker(self) -> None:
        for field, value in (
            ("security_code", "1" * 13),
            ("ticker", "AAA\nforged"),
            ("ticker", "A" * 33),
        ):
            with self.subTest(field=field, value=value):
                report = built_report()
                report["candidates"][0][field] = value
                self.assertTrue(
                    any(
                        error.startswith("CANDIDATE_IDENTITY_INVALID")
                        for error in validate_research_report(report)
                    )
                )


if __name__ == "__main__":
    unittest.main()
