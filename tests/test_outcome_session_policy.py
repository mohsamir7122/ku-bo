from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class OutcomeSessionPolicyTests(unittest.TestCase):
    def test_repository_policy_is_explicitly_unfrozen(self) -> None:
        policy = json.loads(
            (ROOT / "config" / "pilot" / "outcome_session_policy.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(policy["status"], "UNFROZEN")
        self.assertEqual(policy["horizon_basis"], "OFFICIAL_TRADING_SESSIONS")
        self.assertEqual(policy["suspended_or_halted_rule"], "UNDECIDED")
        self.assertEqual(policy["decision_id"], "KU-BO-008-D01")
        self.assertEqual(
            policy["claim_boundary"],
            "OUTCOME_SESSION_POLICY_NOT_FROZEN",
        )

    def test_unfrozen_policy_cannot_silently_use_civil_days(self) -> None:
        text = (
            ROOT / "config" / "pilot" / "outcome_session_policy.json"
        ).read_text(encoding="utf-8")
        self.assertNotIn("CIVIL_DAY", text)
        self.assertIn("OFFICIAL_TRADING_SESSIONS", text)

    def test_schema_freezes_the_unfrozen_claim_invariants(self) -> None:
        schema = json.loads(
            (ROOT / "schemas" / "outcome-session-policy.schema.json").read_text(
                encoding="utf-8"
            )
        )
        unfrozen = schema["properties"]
        self.assertEqual(unfrozen["status"]["const"], "UNFROZEN")
        self.assertEqual(
            unfrozen["suspended_or_halted_rule"]["const"],
            "UNDECIDED",
        )
        self.assertEqual(
            unfrozen["claim_boundary"]["const"],
            "OUTCOME_SESSION_POLICY_NOT_FROZEN",
        )

    def test_v1_schema_rejects_caller_committed_global_option_one(self) -> None:
        schema = json.loads(
            (ROOT / "schemas" / "outcome-session-policy.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(schema["properties"]["status"], {"const": "UNFROZEN"})
        self.assertNotIn("OUTCOME_SESSION_POLICY_FROZEN", json.dumps(schema))


if __name__ == "__main__":
    unittest.main()
