from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from kubo.access_canary import (
    ALLOWED_SOURCE_IDS,
    AUTHORIZED_PR_HEAD_REF,
    AccessCanaryError,
    validate_access_canary_workflow,
)


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "kuwait-access-canary.yml"


class AccessCanaryWorkflowTests(unittest.TestCase):
    def _rejects(self, text: str) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "canary.yml"
            path.write_text(text, encoding="utf-8")
            with self.assertRaises(AccessCanaryError):
                validate_access_canary_workflow(ROOT, workflow_path=path)

    def test_checked_in_workflow_has_only_manual_and_one_shot_pr_activation(self):
        report = validate_access_canary_workflow(ROOT)
        self.assertEqual(report["status"], "PASS_ACCESS_CANARY_WORKFLOW_CONTRACT")
        self.assertTrue(report["manual_dispatch"])
        self.assertTrue(report["manual_dispatch_branch_locked"])
        self.assertTrue(report["authorized_pr_opened_once"])
        self.assertEqual(report["authorized_pr_head_ref"], AUTHORIZED_PR_HEAD_REF)
        self.assertFalse(report["pr_update_actions_allowed"])
        self.assertEqual(report["allowed_source_ids"], list(ALLOWED_SOURCE_IDS))
        self.assertFalse(report["credentials_used"])
        self.assertFalse(report["free_url_input_allowed"])
        self.assertFalse(report["claim_boundaries"]["market_data_collected"])
        self.assertFalse(report["claim_boundaries"]["market_evidence_created"])
        self.assertFalse(
            report["claim_boundaries"]["candidate_generation_invoked"]
        )
        self.assertFalse(report["claim_boundaries"]["publication_attempted"])
        self.assertFalse(report["claim_boundaries"]["trade_allowed"])

        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertNotIn("${{ secrets.", text)
        self.assertNotIn("run-source-search", text)
        self.assertNotIn("build-kuwait-research-bundle", text)
        self.assertNotIn("run-live-dry-run", text)
        self.assertNotIn("submit-order", text)
        self.assertIn("path: runtime/public/", text)
        self.assertIn("branches: [main]", text)
        self.assertIn("types: [opened]", text)
        self.assertNotIn("synchronize", text)
        self.assertNotIn("reopened", text)
        self.assertIn(
            "github.event.pull_request.head.repo.full_name == github.repository",
            text,
        )
        self.assertIn(
            f"github.ref == 'refs/heads/{AUTHORIZED_PR_HEAD_REF}'",
            text,
        )
        self.assertIn("github.event.pull_request.draft == true", text)

    def test_scheduled_trigger_is_rejected(self):
        text = WORKFLOW.read_text(encoding="utf-8").replace(
            "on:\n", "on:\n  schedule:\n    - cron: '0 * * * *'\n", 1
        )
        self._rejects(text)

    def test_scheduled_trigger_with_noncanonical_spacing_is_rejected(self):
        text = WORKFLOW.read_text(encoding="utf-8").replace(
            "on:\n", "on:\n  schedule : [{cron: '0 * * * *'}]\n", 1
        )
        self._rejects(text)

    def test_repository_dispatch_with_noncanonical_spacing_is_rejected(self):
        text = WORKFLOW.read_text(encoding="utf-8").replace(
            "  pull_request:\n", "  repository_dispatch : {}\n  pull_request:\n", 1
        )
        self._rejects(text)

    def test_duplicate_trigger_key_is_rejected(self):
        text = WORKFLOW.read_text(encoding="utf-8").replace(
            "  pull_request:\n", "  workflow_dispatch: {}\n  pull_request:\n", 1
        )
        self._rejects(text)

    def test_synchronize_action_is_rejected(self):
        text = WORKFLOW.read_text(encoding="utf-8").replace(
            "types: [opened]", "types: [opened, synchronize]", 1
        )
        self._rejects(text)

    def test_reopened_action_is_rejected(self):
        text = WORKFLOW.read_text(encoding="utf-8").replace(
            "types: [opened]", "types: [opened, reopened]", 1
        )
        self._rejects(text)

    def test_wrong_pr_head_guard_is_rejected(self):
        text = WORKFLOW.read_text(encoding="utf-8").replace(
            AUTHORIZED_PR_HEAD_REF, "codex/another-branch"
        )
        self._rejects(text)

    def test_manual_dispatch_guard_must_pin_the_exact_branch(self):
        text = WORKFLOW.read_text(encoding="utf-8").replace(
            f"github.ref == 'refs/heads/{AUTHORIZED_PR_HEAD_REF}'",
            "github.ref != ''",
            1,
        )
        self._rejects(text)

    def test_non_draft_pr_guard_is_rejected(self):
        text = WORKFLOW.read_text(encoding="utf-8").replace(
            "github.event.pull_request.draft == true",
            "github.event.pull_request.draft == false",
            1,
        )
        self._rejects(text)

    def test_pr_source_must_remain_fixed_to_kcc(self):
        text = WORKFLOW.read_text(encoding="utf-8").replace(
            "'kcc_maqasa_official' || inputs.source_id",
            "'boursa_reports_archive' || inputs.source_id",
            1,
        )
        self._rejects(text)

    def test_pr_no_trade_confirmation_must_remain_fixed_true(self):
        text = WORKFLOW.read_text(encoding="utf-8").replace(
            "'true' || inputs.confirm_no_trade",
            "'false' || inputs.confirm_no_trade",
            1,
        )
        self._rejects(text)

    def test_free_url_input_is_rejected(self):
        text = WORKFLOW.read_text(encoding="utf-8").replace(
            "      confirm_no_trade:\n",
            "      url:\n        required: true\n        type: string\n"
            "      confirm_no_trade:\n",
            1,
        )
        self._rejects(text)

    def test_source_outside_exact_allowlist_is_rejected(self):
        text = WORKFLOW.read_text(encoding="utf-8").replace(
            "          - boursa_reports_archive",
            "          - boursa_current",
            1,
        )
        self._rejects(text)

    def test_private_artifact_upload_is_rejected(self):
        text = WORKFLOW.read_text(encoding="utf-8").replace(
            "path: runtime/public/", "path: runtime/private/", 1
        )
        self._rejects(text)

    def test_job_level_permission_is_rejected_even_when_read_only(self):
        text = WORKFLOW.read_text(encoding="utf-8").replace(
            "    runs-on: ubuntu-latest\n",
            "    permissions:\n      contents: read\n    runs-on: ubuntu-latest\n",
            1,
        )
        self._rejects(text)

    def test_second_artifact_upload_is_rejected(self):
        second_upload = """\
      - name: Upload a second artifact
        if: always()
        uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02
        with:
          name: extra
          path: runtime/public/
          if-no-files-found: error
          retention-days: 14
"""
        text = WORKFLOW.read_text(encoding="utf-8").replace(
            "      - name: Preserve truthful canary result\n",
            second_upload + "      - name: Preserve truthful canary result\n",
            1,
        )
        self._rejects(text)

    def test_unpinned_or_unexpected_action_is_rejected(self):
        text = WORKFLOW.read_text(encoding="utf-8").replace(
            "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97",
            "attacker/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97",
            1,
        )
        self._rejects(text)

    def test_validator_dependency_install_must_be_exact_and_pinned(self):
        text = WORKFLOW.read_text(encoding="utf-8").replace(
            "PyYAML==6.0.3", "PyYAML>=6", 1
        )
        self._rejects(text)

    def test_structurally_equivalent_permission_format_is_accepted(self):
        text = WORKFLOW.read_text(encoding="utf-8").replace(
            "permissions:\n  contents: read",
            "permissions : {contents: read}",
            1,
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "canary.yml"
            path.write_text(text, encoding="utf-8")
            report = validate_access_canary_workflow(ROOT, workflow_path=path)
        self.assertEqual(report["status"], "PASS_ACCESS_CANARY_WORKFLOW_CONTRACT")

    def test_market_pipeline_invocation_is_rejected(self):
        text = WORKFLOW.read_text(encoding="utf-8").replace(
            "echo \"PASS_ACCESS_ONLY_CANARY\"",
            "python -m kubo run-request --request unsafe.json\n"
            "          echo \"PASS_ACCESS_ONLY_CANARY\"",
            1,
        )
        self._rejects(text)

    def test_secret_reference_is_rejected(self):
        text = WORKFLOW.read_text(encoding="utf-8").replace(
            "      CANARY_SOURCE_ID: ${{ github.event_name == 'pull_request' && "
            "'kcc_maqasa_official' || inputs.source_id }}",
            "      CANARY_SOURCE_ID: ${{ secrets.SOURCE_URL }}",
            1,
        )
        self._rejects(text)

    def test_github_token_expression_inside_run_is_rejected(self):
        text = WORKFLOW.read_text(encoding="utf-8").replace(
            'echo "ACCESS_ONLY_CANARY"',
            'echo "${{ github.token }}"\n            echo "ACCESS_ONLY_CANARY"',
            1,
        )
        self._rejects(text)

    def test_final_truth_gate_cannot_be_replaced_with_unconditional_success(self):
        text = WORKFLOW.read_text(encoding="utf-8").replace(
            'if [[ "$AUDIT_OUTCOME" != "success" ]]; then',
            "if false; then",
            1,
        )
        self._rejects(text)

    def test_arbitrary_python_network_command_is_rejected(self):
        text = WORKFLOW.read_text(encoding="utf-8").replace(
            "          mkdir -p runtime/private\n",
            "          mkdir -p runtime/private\n"
            "          python -c \"import urllib.request; "
            "urllib.request.urlopen('https://attacker.invalid')\"\n",
            1,
        )
        self._rejects(text)


if __name__ == "__main__":
    unittest.main()
