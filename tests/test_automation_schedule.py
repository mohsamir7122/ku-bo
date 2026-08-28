from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - optional test dependency
    Draft202012Validator = None

from kubo.automation_schedule import (
    AutomationScheduleError,
    EXPECTED_SLOTS,
    resolve_background_backfill_occurrence,
    resolve_automation_run,
    validate_automation_schedule,
)


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "kuwait_automation_schedule.json"
WORKFLOW = ROOT / ".github" / "workflows" / "kuwait-market-pipeline.yml"


def _payload() -> dict[str, object]:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def _write(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


class AutomationScheduleTests(unittest.TestCase):
    def _rejects_workflow(self, text: str, pattern: str | None = None) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "workflow.yml"
            path.write_text(text, encoding="utf-8")
            context = (
                self.assertRaisesRegex(AutomationScheduleError, pattern)
                if pattern is not None
                else self.assertRaises(AutomationScheduleError)
            )
            with context:
                validate_automation_schedule(ROOT, workflow_path=path)

    def test_repository_schedule_and_workflow_pass_locked_contract(self) -> None:
        report = validate_automation_schedule(ROOT)
        self.assertEqual(report["status"], "PASS_SCHEDULE_CONTRACT")
        self.assertEqual(report["slot_count"], 7)
        self.assertEqual(report["holiday_count"], 15)
        self.assertFalse(report["implementation_ready"])
        self.assertTrue(all(value is False for value in report["claim_boundaries"].values()))

    def test_schema_accepts_schedule(self) -> None:
        if Draft202012Validator is None:
            self.skipTest("jsonschema optional dependency unavailable")
        schema = json.loads(
            (ROOT / "schemas" / "kuwait-automation-schedule.schema.json").read_text(
                encoding="utf-8"
            )
        )
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(_payload())

    def test_contract_slots_have_exact_local_to_utc_mapping(self) -> None:
        self.assertEqual(
            [(row["local_time"], row["utc_time"]) for row in EXPECTED_SLOTS],
            [
                ("15:00", "12:00"),
                ("04:00", "01:00"),
                ("07:00", "04:00"),
                ("09:00", "06:00"),
                ("11:00", "08:00"),
                ("12:00", "09:00"),
                ("13:00", "10:00"),
            ],
        )

    def test_current_official_holiday_forces_maintenance_no_trade(self) -> None:
        report = resolve_automation_run(
            ROOT,
            actual_started_at=datetime.fromisoformat("2026-08-27T06:00:00+00:00"),
            slot_id="market_open_0900",
            mode="EXECUTE",
            activation_enabled=True,
            admission_ready=True,
            source_access_configured=True,
            drive_runtime_configured=True,
        )
        self.assertEqual(report["market_day_status"], "HOLIDAY")
        self.assertEqual(report["status"], "MAINTENANCE_ONLY_NO_TRADE")
        self.assertFalse(report["should_run_collection"])
        self.assertFalse(report["should_run_live_scoring"])

    def test_missing_calendar_coverage_also_forces_no_trade(self) -> None:
        report = resolve_automation_run(
            ROOT,
            actual_started_at="2027-01-03T06:00:00Z",
            slot_id="market_open_0900",
            mode="EXECUTE",
            activation_enabled=True,
            admission_ready=True,
            source_access_configured=True,
            drive_runtime_configured=True,
        )
        self.assertEqual(report["market_day_status"], "CALENDAR_COVERAGE_MISSING")
        self.assertEqual(report["status"], "MAINTENANCE_ONLY_NO_TRADE")

    def test_disabled_schedule_records_missing_controls_without_failure_claim(self) -> None:
        report = resolve_automation_run(
            ROOT,
            actual_started_at="2026-08-26T12:04:00Z",
            event_schedule="0 12 * * *",
            mode="EXECUTE",
        )
        self.assertEqual(report["market_day_status"], "TRADING_DAY")
        self.assertEqual(report["status"], "BLOCKED_DISABLED")
        self.assertEqual(len(report["missing_controls"]), 4)
        self.assertFalse(report["should_run_collection"])

    def test_enabled_schedule_fails_when_controls_are_missing(self) -> None:
        report = resolve_automation_run(
            ROOT,
            actual_started_at="2026-08-26T01:02:00Z",
            slot_id="live_0400",
            mode="EXECUTE",
            activation_enabled=True,
        )
        self.assertEqual(report["status"], "BLOCKED_MISSING_CONTROLS")
        self.assertNotIn("KUBO_KUWAIT_AUTOMATION_ENABLED", report["missing_controls"])
        self.assertIn("KUBO_DRIVE_RUNTIME_CONFIG", report["missing_controls"])

    def test_all_external_controls_cannot_bypass_implementation_gate(self) -> None:
        report = resolve_automation_run(
            ROOT,
            actual_started_at="2026-08-26T04:01:00Z",
            slot_id="live_0700",
            mode="EXECUTE",
            activation_enabled=True,
            admission_ready=True,
            source_access_configured=True,
            drive_runtime_configured=True,
        )
        self.assertEqual(report["status"], "BLOCKED_IMPLEMENTATION_GATE")
        self.assertEqual(report["missing_controls"], [])
        self.assertFalse(report["should_run_live_scoring"])

    def test_contract_check_never_executes_market_stages(self) -> None:
        report = resolve_automation_run(
            ROOT,
            actual_started_at="2026-08-26T12:01:00Z",
            slot_id="main_1500",
            mode="CONTRACT_CHECK",
        )
        self.assertEqual(report["status"], "PASS_CONTRACT_CHECK")
        self.assertFalse(report["should_run_collection"])
        self.assertFalse(report["should_run_validation"])
        self.assertFalse(report["claim_boundaries"]["contract_check_executes_market_stages"])

    def test_unknown_cron_and_ambiguous_selector_are_rejected(self) -> None:
        with self.assertRaisesRegex(AutomationScheduleError, "exactly one slot"):
            resolve_automation_run(
                ROOT,
                actual_started_at="2026-08-26T12:01:00Z",
                event_schedule="7 12 * * *",
            )
        with self.assertRaisesRegex(AutomationScheduleError, "exactly one of"):
            resolve_automation_run(
                ROOT,
                actual_started_at="2026-08-26T12:01:00Z",
                event_schedule="0 12 * * *",
                slot_id="main_1500",
            )

    def test_holiday_or_slot_tampering_is_rejected(self) -> None:
        payload = _payload()
        payload["official_basis"]["calendar"]["holidays"].pop()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "schedule.json"
            _write(path, payload)
            with self.assertRaisesRegex(AutomationScheduleError, "holiday dates"):
                validate_automation_schedule(ROOT, config_path=path)

        payload = _payload()
        payload["slots"][0]["utc_time"] = "11:00"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "schedule.json"
            _write(path, payload)
            with self.assertRaisesRegex(AutomationScheduleError, "slots"):
                validate_automation_schedule(ROOT, config_path=path)

    def test_workflow_has_no_legacy_schedule_overlap(self) -> None:
        paths = (
            ROOT / ".github" / "workflows" / "daily-shadow.yml",
            ROOT / ".github" / "workflows" / "kuwait-market-ai.yml",
        )
        for path in paths:
            with self.subTest(path=path):
                legacy = path.read_text(encoding="utf-8")
                self.assertNotIn("schedule:", legacy)
                self.assertIn("workflow_dispatch:", legacy)

    def test_legacy_contract_workflow_installs_yaml_parser_exactly(self) -> None:
        legacy = (
            ROOT / ".github" / "workflows" / "kuwait-market-ai.yml"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "python -m pip install --disable-pip-version-check -e . PyYAML==6.0.3",
            legacy,
        )

    def test_background_backfill_is_planned_but_not_activated(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertNotIn("cron:", workflow)
        self.assertIn("backfill_gate:", workflow)
        self.assertIn("if: ${{ false }}", workflow)
        self.assertIn("BLOCKED_CHECKPOINT_STORE", workflow)
        self.assertIn("schedule_active_claim=false", workflow)

    def test_background_occurrence_records_delay_without_punctuality_claim(self) -> None:
        report = resolve_background_backfill_occurrence(
            actual_started_at="2026-08-27T04:31:00Z",
            event_schedule="23 */2 * * *",
        )
        self.assertEqual(report["scheduled_at"], "2026-08-27T04:23:00Z")
        self.assertEqual(report["start_delay_seconds"], 480)
        self.assertFalse(report["scheduled_minute_is_guaranteed"])
        self.assertFalse(report["schedule_active_claim"])

        prior_day = resolve_background_backfill_occurrence(
            actual_started_at="2026-08-27T00:10:00Z",
            event_schedule="23 */2 * * *",
        )
        self.assertEqual(prior_day["scheduled_at"], "2026-08-26T22:23:00Z")

        with self.assertRaisesRegex(AutomationScheduleError, "not allowlisted"):
            resolve_background_backfill_occurrence(
                actual_started_at="2026-08-27T04:31:00Z",
                event_schedule="* * * * *",
            )

    def test_workflow_cron_drift_is_rejected(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8").replace(
            "  workflow_dispatch:\n",
            '  schedule:\n    - cron: "1 6 * * 0-4"\n  workflow_dispatch:\n',
            1,
        )
        self._rejects_workflow(text, "must not activate cron")

    def test_every_yaml_schedule_spelling_is_rejected(self) -> None:
        original = WORKFLOW.read_text(encoding="utf-8")
        trigger_spellings = (
            "  schedule:\n    - cron: '1 6 * * 0-4'\n",
            "  schedule :\n    - cron: 1 6 * * 0-4\n",
            '  "schedule": [{cron: "1 6 * * 0-4"}]\n',
            "  schedule: [{cron: '1 6 * * 0-4'}]\n",
        )
        for trigger in trigger_spellings:
            with self.subTest(trigger=trigger.strip()):
                text = original.replace("on:\n", f"on:\n{trigger}", 1)
                self._rejects_workflow(text, "must not activate cron")

    def test_inline_on_mapping_with_schedule_is_rejected(self) -> None:
        original = WORKFLOW.read_text(encoding="utf-8")
        before_on, after_on = original.split("on:\n", 1)
        _, after_triggers = after_on.split("\npermissions:\n", 1)
        inline = (
            f"{before_on}on: {{workflow_dispatch: {{}}, repository_dispatch: {{types: "
            "[market-recovery-request]}, schedule: [{cron: '1 6 * * 0-4'}]}\n\n"
            f"permissions:\n{after_triggers}"
        )
        self._rejects_workflow(inline, "must not activate cron")

    def test_duplicate_trigger_key_is_rejected_fail_closed(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8").replace(
            "  repository_dispatch:\n",
            "  workflow_dispatch: {}\n  repository_dispatch:\n",
            1,
        )
        self._rejects_workflow(text, "valid unique-key YAML")

    def test_unexpected_trigger_with_noncanonical_spacing_is_rejected(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8").replace(
            "  repository_dispatch:\n", "  push : {branches: [main]}\n  repository_dispatch:\n", 1
        )
        self._rejects_workflow(text, "workflow triggers")

    def test_validator_dependency_install_must_be_exact_and_pinned(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8").replace(
            "PyYAML==6.0.3", "PyYAML>=6", 1
        )
        self._rejects_workflow(text, "run bodies")

    def test_gate_run_body_mutation_is_rejected(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8").replace(
            "            validate-event \\\n",
            "            validate-policy \\\n",
            1,
        )
        self.assertNotEqual(text, WORKFLOW.read_text(encoding="utf-8"))
        self._rejects_workflow(text, "run bodies")

    def test_job_guard_mutation_is_rejected(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8").replace(
            "needs.gate.outputs.run_collection == 'true'",
            "needs.gate.outputs.run_collection != 'true'",
            1,
        )
        self._rejects_workflow(text, "skeleton")

    def test_arbitrary_sha_pinned_action_is_not_allowlisted(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8").replace(
            "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97",
            "attacker/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97",
            1,
        )
        self._rejects_workflow(text, "not allowlisted")


if __name__ == "__main__":
    unittest.main()
