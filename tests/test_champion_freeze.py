from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - optional test dependency
    Draft202012Validator = None

from kubo.champion_freeze import ChampionFreezeError, validate_champion_freeze


ROOT = Path(__file__).resolve().parents[1]


def _valid_manifest() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "freeze_id": "freeze-2026-08-23-three-session",
        "status": "APPROVED_CHAMPION",
        "product_id": "three_session_rank",
        "horizon_sessions": 3,
        "model_version": "champion-v1",
        "policy_version": "policy-v1",
        "source_session_date": "2026-08-23",
        "effective_from_session_date": "2026-08-24",
        "approved_at": "2026-08-23T16:00:00+03:00",
        "artifacts": {
            "code_sha256": "1" * 64,
            "model_sha256": "2" * 64,
            "feature_policy_sha256": "3" * 64,
            "training_manifest_sha256": "4" * 64,
        },
        "approval": {
            "approved_by_role": "AUTHORIZED_REVIEWER",
            "decision_id": "KU-BO-FREEZE-001",
        },
        "outcomes": {
            "available_through": "2026-08-23T14:00:00+03:00",
            "same_session_outcomes_included": False,
        },
        "claim_boundaries": {
            "previous_approved_freeze_only": True,
            "same_day_challenger_used": False,
            "live_or_accuracy_claim_allowed": False,
            "buy_recommendation_claim_allowed": False,
            "automatic_promotion_allowed": False,
        },
    }


def _write(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


class ChampionFreezeTests(unittest.TestCase):
    def _validate(self, payload: object, *, decision_date: str = "2026-08-24"):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "freeze.json"
            _write(path, payload)
            return validate_champion_freeze(
                path,
                decision_session_date=decision_date,
            )

    def test_previous_approved_freeze_passes(self) -> None:
        report = self._validate(_valid_manifest())
        self.assertEqual(report["status"], "PASS_PREVIOUS_FREEZE_ONLY")
        self.assertEqual(report["decision_session_date"], "2026-08-24")
        self.assertFalse(report["same_day_challenger_used"])
        self.assertFalse(report["claim_boundaries"]["automatic_promotion_allowed"])

    def test_schema_accepts_valid_manifest(self) -> None:
        if Draft202012Validator is None:
            self.skipTest("jsonschema optional dependency unavailable")
        schema = json.loads(
            (ROOT / "schemas" / "champion-freeze-manifest.schema.json").read_text(
                encoding="utf-8"
            )
        )
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(
            schema,
            format_checker=Draft202012Validator.FORMAT_CHECKER,
        ).validate(_valid_manifest())

    def test_same_day_approval_is_rejected(self) -> None:
        payload = _valid_manifest()
        payload["approved_at"] = "2026-08-24T08:00:00+03:00"
        with self.assertRaisesRegex(ChampionFreezeError, "same-day approval"):
            self._validate(payload)

    def test_challenger_status_is_rejected(self) -> None:
        payload = _valid_manifest()
        payload["status"] = "CHALLENGER"
        with self.assertRaisesRegex(ChampionFreezeError, "APPROVED_CHAMPION"):
            self._validate(payload)

    def test_product_horizon_mismatch_is_rejected(self) -> None:
        payload = _valid_manifest()
        payload["horizon_sessions"] = 5
        with self.assertRaisesRegex(ChampionFreezeError, "horizon"):
            self._validate(payload)

    def test_same_session_outcomes_are_rejected(self) -> None:
        payload = _valid_manifest()
        payload["outcomes"]["same_session_outcomes_included"] = True
        with self.assertRaisesRegex(ChampionFreezeError, "same-session outcomes"):
            self._validate(payload)

    def test_future_outcome_cutoff_is_rejected(self) -> None:
        payload = _valid_manifest()
        payload["outcomes"]["available_through"] = "2026-08-24T10:00:00+03:00"
        with self.assertRaisesRegex(ChampionFreezeError, "outcome cutoff"):
            self._validate(payload)

    def test_weakened_claim_boundary_is_rejected(self) -> None:
        payload = _valid_manifest()
        payload["claim_boundaries"]["automatic_promotion_allowed"] = True
        with self.assertRaisesRegex(ChampionFreezeError, "claim boundaries"):
            self._validate(payload)

    def test_source_session_must_precede_effective_session(self) -> None:
        payload = _valid_manifest()
        payload["source_session_date"] = "2026-08-24"
        with self.assertRaisesRegex(ChampionFreezeError, "originate before"):
            self._validate(payload)

    def test_freeze_not_yet_effective_is_rejected(self) -> None:
        payload = _valid_manifest()
        payload["effective_from_session_date"] = "2026-08-25"
        with self.assertRaisesRegex(ChampionFreezeError, "effective by decision"):
            self._validate(payload)

    def test_datetime_decision_session_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "freeze.json"
            _write(path, _valid_manifest())
            with self.assertRaisesRegex(ChampionFreezeError, "date, not datetime"):
                validate_champion_freeze(
                    path,
                    decision_session_date=datetime.fromisoformat(
                        "2026-08-24T15:07:00+03:00"
                    ),
                )

    def test_invalid_sha_is_rejected(self) -> None:
        payload = deepcopy(_valid_manifest())
        payload["artifacts"]["model_sha256"] = "not-a-hash"
        with self.assertRaisesRegex(ChampionFreezeError, "SHA-256"):
            self._validate(payload)


if __name__ == "__main__":
    unittest.main()
