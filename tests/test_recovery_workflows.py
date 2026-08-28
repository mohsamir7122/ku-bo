from __future__ import annotations

from pathlib import Path
import re
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
PIPELINE = ROOT / ".github" / "workflows" / "kuwait-market-pipeline.yml"
CONTROLLER = ROOT / ".github" / "workflows" / "recovery-controller.yml"
LEGACY = ROOT / ".github" / "workflows" / "kuwait-market-ai.yml"
FULL_SHA_USE = re.compile(
    r"^\s*(?:-\s*)?uses:\s*[^\s@]+@[0-9a-f]{40}(?:\s+#.*)?$"
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _base_yaml(path: Path) -> dict[str, object]:
    value = yaml.load(_text(path), Loader=yaml.BaseLoader)
    if not isinstance(value, dict):
        raise AssertionError(f"{path} must contain a YAML mapping")
    return value


class RecoveryWorkflowTests(unittest.TestCase):
    def test_workflow_yaml_parses(self) -> None:
        for path in (PIPELINE, CONTROLLER, LEGACY):
            with self.subTest(path=path):
                self.assertIsNotNone(yaml.compose(_text(path)))

    def test_all_external_actions_are_pinned_to_full_commit_shas(self) -> None:
        for path in (PIPELINE, CONTROLLER, LEGACY):
            for line_number, line in enumerate(_text(path).splitlines(), start=1):
                if "uses:" not in line:
                    continue
                with self.subTest(path=path, line=line_number):
                    self.assertRegex(line, FULL_SHA_USE)

    def test_pipeline_permissions_and_unified_concurrency_are_read_only(self) -> None:
        workflow = _base_yaml(PIPELINE)
        self.assertEqual(workflow["permissions"], {"contents": "read"})
        self.assertEqual(
            workflow["concurrency"],
            {"group": "kubo-kuwait-market-ai", "cancel-in-progress": "false"},
        )
        text = _text(PIPELINE)
        self.assertNotIn("actions: write", text)
        self.assertNotIn("issues: write", text)
        self.assertIn("--completed-run-attempt", text)

    def test_controller_write_permissions_are_scoped_to_controller_job(self) -> None:
        workflow = _base_yaml(CONTROLLER)
        self.assertEqual(workflow["permissions"], {"contents": "read"})
        permissions = workflow["jobs"]["controller"]["permissions"]
        self.assertEqual(
            permissions,
            {"contents": "read", "actions": "write", "issues": "write"},
        )
        self.assertEqual(
            workflow["concurrency"],
            {"group": "kubo-kuwait-market-ai", "cancel-in-progress": "false"},
        )

    def test_controller_is_manual_or_main_workflow_event_only(self) -> None:
        workflow = _base_yaml(CONTROLLER)
        triggers = workflow["on"]
        self.assertEqual(
            triggers["workflow_run"]["workflows"],
            ["Kuwait Market Pipeline", "CI"],
        )
        self.assertEqual(triggers["workflow_run"]["types"], ["completed"])
        self.assertEqual(triggers["workflow_run"]["branches"], ["main"])
        self.assertNotIn("schedule", triggers)
        self.assertEqual(
            triggers["repository_dispatch"]["types"],
            ["market-recovery-request"],
        )
        text = _text(CONTROLLER)
        self.assertNotRegex(text, r"\bsleep\s+\d+")
        self.assertIn("github-control", text)
        self.assertIn("github.token", text)

    def test_pipeline_backfill_is_bounded_prioritized_and_dormant(self) -> None:
        workflow = _base_yaml(PIPELINE)
        triggers = workflow["on"]
        self.assertNotIn("schedule", triggers)
        backfill = workflow["jobs"]["backfill_gate"]
        self.assertEqual(backfill["timeout-minutes"], "5")
        self.assertEqual(backfill["if"], "${{ false }}")
        text = _text(PIPELINE)
        self.assertIn("priority=BACKFILL_90D:10", text)
        self.assertIn("--production", text)
        self.assertIn("BLOCKED_CHECKPOINT_STORE", text)
        self.assertIn("BLOCKED_UNWIRED_PRODUCTION_COORDINATOR", text)
        self.assertIn("Preserve backfill blocker exit code", text)
        self.assertNotRegex(text, r"\bsleep\s+\d+")

    def test_successful_failed_job_rerun_requires_hash_bound_incident_context(self) -> None:
        workflow = _base_yaml(PIPELINE)
        job = workflow["jobs"]["recovery_success"]
        self.assertEqual(job["permissions"], {"actions": "read", "contents": "read"})
        self.assertIn("github.run_attempt > 1", job["if"])
        text = _text(PIPELINE)
        self.assertIn("resolve-rerun-success-context", text)
        self.assertIn("steps.success_context.outputs.incident_id", text)
        self.assertIn("steps.success_context.outputs.incident_key", text)
        self.assertIn("recovery-success-context.json", text)

    def test_no_trade_marker_runs_for_success_failure_cancel_and_skip_outcomes(self) -> None:
        workflow = _base_yaml(PIPELINE)
        job = workflow["jobs"]["no_trade"]
        self.assertEqual(job["if"], "always()")
        self.assertEqual(len(job["steps"]), 1)
        step = job["steps"][0]
        self.assertNotIn("if", step)
        self.assertEqual(step["name"], "Enforce no-trade for every pipeline outcome")
        self.assertIn("NO-TRADE", step["run"])

    def test_legacy_sequential_workflow_is_manual_only(self) -> None:
        workflow = _base_yaml(LEGACY)
        self.assertEqual(set(workflow["on"]), {"workflow_dispatch"})


if __name__ == "__main__":
    unittest.main()
