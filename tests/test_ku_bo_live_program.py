from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover
    Draft202012Validator = None

from kubo.ku_bo_live_program import LiveProgramError, validate_ku_bo_live_program


ROOT = Path(__file__).resolve().parents[1]


class LiveProgramTests(unittest.TestCase):
    def setUp(self) -> None:
        self.program = json.loads(
            (ROOT / "config/ku_bo_live_program.json").read_text(encoding="utf-8")
        )
        self.task = json.loads(
            (ROOT / "config/ku_bo_018_event_admission_task.json").read_text(encoding="utf-8")
        )
        self.products = json.loads((ROOT / "config/products.json").read_text(encoding="utf-8"))

    def _root(self, program=None, task=None, products=None):
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        (root / "config").mkdir()
        for name, payload in (
            ("ku_bo_live_program.json", program or self.program),
            ("ku_bo_018_event_admission_task.json", task or self.task),
            ("products.json", products or self.products),
        ):
            (root / "config" / name).write_text(json.dumps(payload), encoding="utf-8")
        return temporary, root

    def test_program_passes_and_stays_disabled(self) -> None:
        report = validate_ku_bo_live_program(ROOT)
        self.assertEqual(report["status"], "PASS_DISABLED_PROGRAM_CONTRACT")
        self.assertFalse(report["claim_boundaries"]["schedule_enabled"])
        self.assertEqual(report["task_018_status"], "PROPOSED_NOT_STARTED")

    def test_schemas_accept_configs(self) -> None:
        if Draft202012Validator is None:
            self.skipTest("jsonschema unavailable")
        pairs = (
            ("ku-bo-live-program.schema.json", self.program),
            ("ku-bo-018-task.schema.json", self.task),
        )
        for schema_name, payload in pairs:
            schema = json.loads((ROOT / "schemas" / schema_name).read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)
            self.assertEqual(list(Draft202012Validator(schema).iter_errors(payload)), [])

    def test_schedule_enablement_rejected(self) -> None:
        payload = deepcopy(self.program)
        payload["claim_boundaries"]["schedule_enabled"] = True
        temporary, root = self._root(program=payload)
        with temporary, self.assertRaises(LiveProgramError):
            validate_ku_bo_live_program(root)

    def test_research_cycle_change_rejected(self) -> None:
        payload = deepcopy(self.program)
        payload["research_cycles"][0]["start_local"] = "08:01"
        temporary, root = self._root(program=payload)
        with temporary, self.assertRaises(LiveProgramError):
            validate_ku_bo_live_program(root)

    def test_shadow_activation_rejected(self) -> None:
        payload = deepcopy(self.program)
        payload["existing_shadow_contract"]["status"] = "ENABLED"
        temporary, root = self._root(program=payload)
        with temporary, self.assertRaises(LiveProgramError):
            validate_ku_bo_live_program(root)

    def test_product_horizon_mismatch_rejected(self) -> None:
        payload = deepcopy(self.program)
        payload["products"][0]["horizon_sessions"] = 5
        temporary, root = self._root(program=payload)
        with temporary, self.assertRaises(LiveProgramError):
            validate_ku_bo_live_program(root)

    def test_catalog_horizon_mismatch_rejected(self) -> None:
        products = deepcopy(self.products)
        target = next(row for row in products["products"] if row["product_id"] == "three_session_rank")
        target["horizon_sessions"] = 4
        temporary, root = self._root(products=products)
        with temporary, self.assertRaises(LiveProgramError):
            validate_ku_bo_live_program(root)

    def test_training_in_task_018_rejected(self) -> None:
        task = deepcopy(self.task)
        task["training"]["allowed_in_task"] = True
        temporary, root = self._root(task=task)
        with temporary, self.assertRaises(LiveProgramError):
            validate_ku_bo_live_program(root)

    def test_locked_test_overlap_rejected(self) -> None:
        task = deepcopy(self.task)
        task["development_set"]["locked_test_overlap_allowed"] = True
        temporary, root = self._root(task=task)
        with temporary, self.assertRaises(LiveProgramError):
            validate_ku_bo_live_program(root)

    def test_gate_removal_rejected(self) -> None:
        payload = deepcopy(self.program)
        payload["required_gates"].pop()
        temporary, root = self._root(program=payload)
        with temporary, self.assertRaises(LiveProgramError):
            validate_ku_bo_live_program(root)

    def test_task_mission_artifacts_and_claim_keys_are_locked(self) -> None:
        task = deepcopy(self.task)
        task["mission"] = "MODEL_TRAINING"
        temporary, root = self._root(task=task)
        with temporary, self.assertRaises(LiveProgramError):
            validate_ku_bo_live_program(root)

        task = deepcopy(self.task)
        task["required_artifacts"].pop()
        temporary, root = self._root(task=task)
        with temporary, self.assertRaises(LiveProgramError):
            validate_ku_bo_live_program(root)

        task = deepcopy(self.task)
        task["claim_boundaries"] = []
        temporary, root = self._root(task=task)
        with temporary, self.assertRaises(LiveProgramError):
            validate_ku_bo_live_program(root)


if __name__ == "__main__":
    unittest.main()
