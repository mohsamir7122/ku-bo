from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from kubo.ca_enrichment_import import import_ca_enrichment
from kubo.ca_enrichment_workspace import prepare_ca_enrichment_workspace
from tests.foundation_fixture_helpers import build_status_corporate_output


DISCLOSURE_URL = (
    "https://www.boursakuwait.com.kw/en/announcements/"
    "disclosures-and-announcements/historical-disclosures-and-announcements/"
)
PRICE_URL = "https://reports.boursakuwait.com.kw/en/price-history"


class CorporateActionEnrichmentImportTests(unittest.TestCase):
    def _workspace(
        self,
        root: Path,
        *,
        accept_actions: bool = True,
        missing_phrase: bool = False,
        stale_schedule_hash: bool = False,
    ) -> tuple[Path, Path]:
        upstream = build_status_corporate_output(root)
        workspace = root / "ca-workspace"
        prepare_ca_enrichment_workspace(
            status_corporate_root=upstream,
            output_root=workspace,
            run_id="ca-enrichment-001",
            prepared_by="unit-test",
        )
        manifest_path = workspace / "manifests" / "ca_enrichment_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if stale_schedule_hash and manifest["actions"]:
            manifest["actions"][0]["schedule_row_sha256"] = "f" * 64

        for action in manifest["actions"]:
            action_id = action["action_id"]
            is_nbk = action["ticker"] == "NBK"
            phrase = (
                "cash dividend of 5 fils per share"
                if is_nbk
                else "rights issue of one new share for every two old shares at 60 fils"
            )
            raw_content = (
                f"Official disclosure {action_id}. {phrase}. "
                f"Ex date {action['ex_date']}."
            ).encode("utf-8")
            text_content = raw_content
            raw_path = (
                workspace
                / "raw_exports"
                / "disclosures"
                / action["disclosure"]["raw_file_name"]
            )
            text_path = (
                workspace
                / "text_exports"
                / "disclosures"
                / action["disclosure"]["text_file_name"]
            )
            raw_path.write_bytes(raw_content)
            text_path.write_bytes(text_content)
            action["disclosure"].update(
                {
                    "source_url": DISCLOSURE_URL,
                    "raw_sha256": hashlib.sha256(raw_content).hexdigest(),
                    "text_sha256": hashlib.sha256(text_content).hexdigest(),
                    "text_derivation": "OFFICIAL_HTML_VISIBLE_TEXT",
                    "published_at": "2026-02-20T10:00:00+03:00",
                    "captured_at": "2026-08-09T11:00:00+03:00",
                    "captured_by": "unit-test",
                    "evidence_phrases": [
                        "phrase not present" if missing_phrase and is_nbk else phrase
                    ],
                    "review_status": "ACCEPTED" if accept_actions else "PENDING",
                    "review_notes": "reviewed official fixture",
                }
            )

            previous_close = "100"
            price_excerpt = f"Previous closing price {previous_close} fils"
            price_content = price_excerpt.encode("utf-8")
            price_path = (
                workspace
                / "raw_exports"
                / "reference_prices"
                / action["price_reference"]["raw_file_name"]
            )
            price_path.write_bytes(price_content)
            action["price_reference"].update(
                {
                    "source_url": PRICE_URL,
                    "raw_sha256": hashlib.sha256(price_content).hexdigest(),
                    "trade_date": (
                        "2026-03-10" if is_nbk else "2026-08-10"
                    ),
                    "previous_close_fils": previous_close,
                    "evidence_excerpt": price_excerpt,
                    "captured_at": "2026-08-09T11:05:00+03:00",
                    "captured_by": "unit-test",
                    "review_status": "ACCEPTED",
                    "review_notes": "reviewed official price fixture",
                }
            )
            if is_nbk:
                action["terms"].update(
                    {
                        "action_type": "CASH_DIVIDEND_NORMAL",
                        "formula_mode": "REPRODUCIBLE_MECHANICAL",
                        "previous_close_fils": previous_close,
                        "cash_per_share_fils": "5",
                        "new_shares_per_old_share": "",
                        "rights_new_shares_per_old_share": "",
                        "subscription_price_fils": "",
                        "official_reference_price_fils": "",
                        "official_factor": "",
                        "official_position_quantity_multiplier": "",
                        "fractional_entitlement_policy": "NOT_APPLICABLE",
                        "formula_notes": "Boursa dividend-adjusted-price formula",
                    }
                )
            else:
                action["terms"].update(
                    {
                        "action_type": "RIGHTS_ISSUE",
                        "formula_mode": "REPRODUCIBLE_MECHANICAL",
                        "previous_close_fils": previous_close,
                        "cash_per_share_fils": "",
                        "new_shares_per_old_share": "",
                        "rights_new_shares_per_old_share": "0.5",
                        "subscription_price_fils": "60",
                        "official_reference_price_fils": "",
                        "official_factor": "",
                        "official_position_quantity_multiplier": "",
                        "fractional_entitlement_policy": "UNKNOWN",
                        "formula_notes": "mechanical TERP; return policy remains pending",
                    }
                )
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        return upstream, workspace

    def test_disclosures_produce_reference_factors_but_rights_policy_remains_pending(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            upstream, workspace = self._workspace(root)
            output = root / "ca-output"
            report = import_ca_enrichment(
                status_corporate_root=upstream,
                workspace=workspace,
                output_root=output,
            )
            self.assertEqual(
                report["status"],
                "CA_REFERENCE_FACTORS_READY_RETURN_POLICY_PENDING",
            )
            self.assertEqual(report["action_count"], 2)
            self.assertEqual(report["accepted_action_count"], 2)
            self.assertEqual(report["reference_factor_ready_count"], 2)
            self.assertEqual(report["return_engine_ready_count"], 1)
            self.assertFalse(report["claim_boundaries"]["backtest_ready"])
            self.assertFalse(
                report["claim_boundaries"][
                    "reference_price_factor_is_return_engine_multiplier"
                ]
            )

            import csv

            with (output / "normalized" / "corporate_action_factor_ledger.csv").open(
                "r", encoding="utf-8", newline=""
            ) as handle:
                rows = list(csv.DictReader(handle))
            by_ticker = {row["ticker"]: row for row in rows}
            self.assertEqual(by_ticker["NBK"]["theoretical_ex_price_fils"], "95")
            self.assertEqual(by_ticker["NBK"]["return_price_multiplier"], "1")
            self.assertEqual(
                by_ticker["NBK"]["cash_distribution_per_pre_action_share_fils"],
                "5",
            )
            self.assertEqual(
                by_ticker["KFH"]["return_engine_treatment"],
                "BLOCKED_RIGHTS_EXERCISE_OR_SALE_POLICY",
            )
            self.assertEqual(by_ticker["KFH"]["return_engine_ready"], "false")

            with (output / "normalized" / "corporate_action_return_policy_queue.csv").open(
                "r", encoding="utf-8", newline=""
            ) as handle:
                policy_rows = list(csv.DictReader(handle))
            self.assertEqual(len(policy_rows), 1)
            self.assertEqual(policy_rows[0]["ticker"], "KFH")

    def test_pending_disclosure_results_in_partial_not_synthetic_factor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            upstream, workspace = self._workspace(root, accept_actions=False)
            report = import_ca_enrichment(
                status_corporate_root=upstream,
                workspace=workspace,
                output_root=root / "ca-output",
            )
            self.assertEqual(report["status"], "PARTIAL")
            self.assertEqual(report["reference_factor_ready_count"], 0)
            self.assertEqual(len(report["pending_actions"]), 2)

    def test_missing_evidence_phrase_blocks_import(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            upstream, workspace = self._workspace(root, missing_phrase=True)
            report = import_ca_enrichment(
                status_corporate_root=upstream,
                workspace=workspace,
                output_root=root / "ca-output",
            )
            self.assertEqual(report["status"], "BLOCKED")
            self.assertTrue(
                any("evidence phrase is absent" in error for error in report["errors"])
            )

    def test_stale_schedule_hash_is_rejected_before_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            upstream, workspace = self._workspace(root, stale_schedule_hash=True)
            output = root / "ca-output"
            with self.assertRaisesRegex(ValueError, "stale schedule row hash"):
                import_ca_enrichment(
                    status_corporate_root=upstream,
                    workspace=workspace,
                    output_root=output,
                )
            self.assertFalse(output.exists())

    def test_zero_action_upstream_produces_explicit_zero_ready(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            upstream = build_status_corporate_output(root, zero_actions=True)
            workspace = root / "ca-workspace"
            prepare_ca_enrichment_workspace(
                status_corporate_root=upstream,
                output_root=workspace,
                run_id="ca-zero",
            )
            report = import_ca_enrichment(
                status_corporate_root=upstream,
                workspace=workspace,
                output_root=root / "ca-output",
            )
            self.assertEqual(report["status"], "CA_ENRICHMENT_ZERO_RESULT_READY")
            self.assertEqual(report["action_count"], 0)
            self.assertFalse(report["claim_boundaries"]["backtest_ready"])


if __name__ == "__main__":
    unittest.main()
