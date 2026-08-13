from __future__ import annotations

import csv
import hashlib
import hmac
import json
from pathlib import Path
import tempfile
import unittest

from kubo.hashing import canonical_json_bytes
from kubo.official_eod_import import (
    OFFICIAL_DAILY_EOD_HEADERS,
    _import_official_daily_eod_unchecked,
    validate_official_eod_output,
)
from kubo.official_eod_workspace import prepare_official_eod_workspace
from kubo.runtime_trust import canonical_registry_bytes, verify_runtime_trust_registry
from tests.official_eod_fixture_helpers import (
    add_matching_market_totals,
    add_provider,
    build_eod_upstreams,
    complete_eod_rows,
)


def _licensed_registry():
    key = b"official-eod-runtime-trust-test-key-material"
    payload = {
        "schema_version": "1.0",
        "audience": "kubo-source-network",
        "registry_id": "external-eod-registry-1",
        "issued_at": "2026-08-09T00:00:00+03:00",
        "expires_at": "2026-08-10T00:00:00+03:00",
        "entries": [
            {
                "source_id": "licensed_vendor",
                "subject_id": "licensed-subject",
                "domains": ["vendor.example.com"],
                "security_codes": ["101", "108", "413", "605", "623"],
                "activation_id": None,
                "entitlement_id": "licensed-entitlement",
                "valid_from": "2026-08-09T00:00:00+03:00",
                "valid_until": "2026-08-10T00:00:00+03:00",
            }
        ],
        "authentication": {
            "algorithm": "HMAC-SHA256",
            "key_id": "external-eod-key-v1",
            "tag": "0" * 64,
        },
    }
    payload["authentication"]["tag"] = hmac.new(
        key,
        canonical_registry_bytes(payload),
        hashlib.sha256,
    ).hexdigest()
    registry = verify_runtime_trust_registry(
        payload,
        key=key,
        expected_key_id="external-eod-key-v1",
        decision_at="2026-08-09T18:00:00+03:00",
    )
    return registry, key, payload


class OfficialEodPipelineTests(unittest.TestCase):
    def _prepared(self, root: Path) -> tuple[Path, Path, Path]:
        official, history = build_eod_upstreams(root)
        workspace = root / "eod-workspace"
        report = prepare_official_eod_workspace(
            official_foundation_root=official,
            status_history_root=history,
            output_root=workspace,
            run_id="official-eod-fixture",
            window_from="2026-08-08",
            window_to="2026-08-09",
            prepared_by="unit-test",
        )
        self.assertEqual(report["expected_pair_count"], 10)
        return official, history, workspace

    def _import(
        self,
        root: Path,
        official: Path,
        history: Path,
        workspace: Path,
    ) -> tuple[Path, dict]:
        output = root / "eod-output"
        report = _import_official_daily_eod_unchecked(
            workspace_root=workspace,
            official_foundation_root=official,
            status_history_root=history,
            output_root=output,
            run_id="official-eod-fixture",
            imported_at="2026-08-09T18:00:00+03:00",
        )
        return output, report

    def test_workspace_binds_upstreams_and_forbids_snapshot_backfill(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            official, history, workspace = self._prepared(root)
            manifest = json.loads(
                (workspace / "manifests" / "official_eod_manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(manifest["upstream"]["official_foundation"]["status"], "CURRENT_IDENTITY_AND_CALENDAR_READY")
            self.assertEqual(manifest["upstream"]["status_history"]["status"], "HISTORICAL_STATUS_INTERVALS_READY")
            self.assertRegex(
                manifest["upstream"]["official_foundation"]["security_master_sha256"],
                r"^[0-9a-f]{64}$",
            )
            with self.assertRaisesRegex(ValueError, "current snapshot must not backfill"):
                prepare_official_eod_workspace(
                    official_foundation_root=official,
                    status_history_root=history,
                    output_root=root / "invalid-backfill",
                    run_id="invalid-backfill",
                    window_from="2026-08-07",
                    window_to="2026-08-09",
                )
            with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
                prepare_official_eod_workspace(
                    official_foundation_root=official,
                    status_history_root=history,
                    output_root=workspace,
                    run_id="official-eod-fixture",
                    window_from="2026-08-08",
                    window_to="2026-08-09",
                )

    def test_complete_recorded_fixture_preserves_all_six_states_but_never_promotes_ready(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            official, history, workspace = self._prepared(root)
            add_provider(workspace)
            output, report = self._import(root, official, history, workspace)
            self.assertEqual(report["status"], "PARTIAL")
            self.assertEqual(report["denominator_status"], "PASS")
            self.assertEqual(report["query_and_pagination_status"], "PASS")
            self.assertEqual(report["evidence_classification"], "RECORDED_AUTHORIZED_FIXTURE")
            self.assertFalse(report["claim_boundaries"]["recorded_fixture_is_real_evidence"])
            with (output / "normalized" / "official_daily_eod.csv").open(
                "r", encoding="utf-8", newline=""
            ) as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(tuple(rows[0]), OFFICIAL_DAILY_EOD_HEADERS)
            self.assertEqual(len(rows), 10)
            self.assertEqual(
                {row["trading_state"] for row in rows},
                {
                    "TRADED",
                    "NO_TRADE",
                    "SUSPENDED",
                    "HALTED",
                    "TRADED_THEN_SUSPENDED",
                    "NOT_LISTED_OR_NOT_ELIGIBLE",
                },
            )
            nontraded = [
                row
                for row in rows
                if row["trading_state"]
                not in {"TRADED", "TRADED_THEN_SUSPENDED"}
            ]
            self.assertTrue(
                all(
                    not any(row[field] for field in ("open_fils", "high_fils", "low_fils", "close_fils"))
                    for row in nontraded
                )
            )
            validation = validate_official_eod_output(
                official_eod_root=output,
                official_foundation_root=official,
                status_history_root=history,
            )
            self.assertEqual(validation["validation_status"], "PASS")
            self.assertEqual(validation["status"], "PARTIAL")

    def test_optional_official_fields_remain_blank_and_are_not_derived(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            official, history, workspace = self._prepared(root)
            rows = complete_eod_rows()
            for row in rows:
                for field in (
                    "open_fils",
                    "high_fils",
                    "low_fils",
                    "close_fils",
                    "volume",
                    "value_traded_kwd",
                    "trade_count",
                    "reference_price_fils",
                ):
                    row[field] = ""
            add_provider(workspace, rows=rows, supplied_fields=["TRADING_STATE"])
            output, report = self._import(root, official, history, workspace)
            self.assertEqual(report["denominator_status"], "PASS")
            with (output / "normalized" / "official_daily_eod.csv").open(
                "r", encoding="utf-8", newline=""
            ) as handle:
                normalized = list(csv.DictReader(handle))
            self.assertTrue(all(row["available_official_fields"] == "TRADING_STATE" for row in normalized))
            self.assertTrue(all(row["trade_count"] == "" and row["value_traded_kwd"] == "" for row in normalized))

    def test_positive_activity_on_nontraded_row_blocks_and_quarantines(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            official, history, workspace = self._prepared(root)
            rows = complete_eod_rows()
            target = next(row for row in rows if row["trading_state"] == "NO_TRADE")
            target["volume"] = "1"
            add_provider(workspace, rows=rows)
            output, report = self._import(root, official, history, workspace)
            self.assertEqual(report["status"], "BLOCKED")
            self.assertTrue(any("must be blank or zero" in error for error in report["errors"]))
            self.assertTrue((output / "quarantine" / "provider_disagreements.csv").is_file())

    def test_provider_disagreement_and_price_basis_mixing_are_quarantined(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            official, history, workspace = self._prepared(root)
            add_provider(workspace, provider_id="raw-provider")
            add_provider(
                workspace,
                provider_id="adjusted-provider",
                price_basis="OFFICIALLY_ADJUSTED",
            )
            output, report = self._import(root, official, history, workspace)
            self.assertEqual(report["status"], "BLOCKED")
            self.assertEqual(report["quarantine_count"], 10)
            self.assertTrue(all("PROVIDER_DISAGREEMENT" in error for error in report["errors"]))
            self.assertTrue((output / "quarantine" / "provider_disagreements.csv").is_file())

    def test_missing_pair_and_partial_pagination_cannot_claim_complete_eod(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            official, history, workspace = self._prepared(root)
            add_provider(
                workspace,
                rows=complete_eod_rows()[:-1],
                availability_status="PARTIAL",
            )
            _, report = self._import(root, official, history, workspace)
            self.assertEqual(report["status"], "PARTIAL")
            self.assertEqual(report["denominator_status"], "PARTIAL")
            self.assertEqual(report["query_and_pagination_status"], "PARTIAL")
            self.assertEqual(report["missing_pair_count"], 1)

    def test_matching_same_scope_totals_pass_and_mismatch_blocks(self) -> None:
        for mismatch in (False, True):
            with self.subTest(mismatch=mismatch), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                official, history, workspace = self._prepared(root)
                add_provider(workspace)
                add_matching_market_totals(workspace, mismatch=mismatch)
                _, report = self._import(root, official, history, workspace)
                self.assertEqual(
                    report["market_totals_status"], "BLOCKED" if mismatch else "PASS"
                )
                self.assertEqual(report["status"], "BLOCKED" if mismatch else "PARTIAL")

    def test_licensed_feed_without_authenticated_runtime_trust_remains_dependent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            official, history, workspace = self._prepared(root)
            add_provider(
                workspace,
                source_class="LICENSED",
                evidence_classification="PROVEN_REAL_EVIDENCE",
                rights_status="RESEARCH_USE_AUTHORIZED",
            )
            _, report = self._import(root, official, history, workspace)
            self.assertEqual(report["status"], "PARTIAL")
            self.assertEqual(report["evidence_classification"], "LICENSED_FEED_DEPENDENT")
            self.assertEqual(report["price_evidence_status"], "PARTIAL")

    def test_self_attested_official_real_evidence_remains_live_dependent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            official, history, workspace = self._prepared(root)
            add_provider(
                workspace,
                source_class="OFFICIAL",
                evidence_classification="PROVEN_REAL_EVIDENCE",
                rights_status="RESEARCH_USE_AUTHORIZED",
            )
            _, report = self._import(root, official, history, workspace)
            self.assertEqual(report["status"], "PARTIAL")
            self.assertEqual(report["evidence_classification"], "LIVE_DEPENDENT")
            self.assertEqual(report["price_evidence_status"], "PARTIAL")
            self.assertIsNone(report["providers"][0]["runtime_trust"])

    def test_real_trading_state_only_is_partial_not_complete_eod(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            official, history, workspace = self._prepared(root)
            rows = complete_eod_rows()
            for row in rows:
                for field in (
                    "open_fils",
                    "high_fils",
                    "low_fils",
                    "close_fils",
                    "volume",
                    "value_traded_kwd",
                    "trade_count",
                    "reference_price_fils",
                ):
                    row[field] = ""
            add_provider(
                workspace,
                rows=rows,
                supplied_fields=["TRADING_STATE"],
                source_class="LICENSED",
                evidence_classification="PROVEN_REAL_EVIDENCE",
                rights_status="RESEARCH_USE_AUTHORIZED",
            )
            registry, _, _ = _licensed_registry()
            report = _import_official_daily_eod_unchecked(
                workspace_root=workspace,
                official_foundation_root=official,
                status_history_root=history,
                output_root=root / "state-only-output",
                run_id="official-eod-fixture",
                imported_at="2026-08-09T18:00:00+03:00",
                runtime_trust_registry=registry,
            )
            self.assertEqual(report["denominator_status"], "PASS")
            self.assertEqual(report["price_evidence_status"], "PARTIAL")
            self.assertEqual(report["status"], "PARTIAL")
            self.assertIn(
                "OFFICIAL_EOD_COMPLETE_FIELD_SET_UNAVAILABLE",
                report["warnings"],
            )

    def test_fixture_market_totals_cannot_promote_real_eod(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            official, history, workspace = self._prepared(root)
            add_provider(
                workspace,
                source_class="LICENSED",
                evidence_classification="PROVEN_REAL_EVIDENCE",
                rights_status="RESEARCH_USE_AUTHORIZED",
            )
            add_matching_market_totals(workspace)
            registry, _, _ = _licensed_registry()
            report = _import_official_daily_eod_unchecked(
                workspace_root=workspace,
                official_foundation_root=official,
                status_history_root=history,
                output_root=root / "mixed-evidence-output",
                run_id="official-eod-fixture",
                imported_at="2026-08-09T18:00:00+03:00",
                runtime_trust_registry=registry,
            )
            self.assertEqual(report["market_totals_status"], "PASS")
            self.assertEqual(
                report["evidence_classification"],
                "LICENSED_FEED_DEPENDENT",
            )
            self.assertEqual(report["status"], "PARTIAL")

    def test_entitlement_registry_does_not_prove_capture_bytes_or_copy_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            official, history, workspace = self._prepared(root)
            add_provider(
                workspace,
                source_class="LICENSED",
                evidence_classification="PROVEN_REAL_EVIDENCE",
                rights_status="RESEARCH_USE_AUTHORIZED",
            )
            registry, key, payload = _licensed_registry()
            output = root / "eod-output"
            report = _import_official_daily_eod_unchecked(
                workspace_root=workspace,
                official_foundation_root=official,
                status_history_root=history,
                output_root=output,
                run_id="official-eod-fixture",
                imported_at="2026-08-09T18:00:00+03:00",
                runtime_trust_registry=registry,
            )
            self.assertEqual(report["status"], "PARTIAL")
            self.assertEqual(report["price_evidence_status"], "PARTIAL")
            self.assertEqual(
                report["evidence_classification"],
                "LICENSED_FEED_DEPENDENT",
            )
            self.assertIn(
                "OFFICIAL_EOD_ARTIFACT_BOUND_CAPTURE_AUTHORITY_REQUIRED",
                report["warnings"],
            )
            trust = report["providers"][0]["runtime_trust"]
            self.assertEqual(
                set(trust),
                {"registry_id", "registry_sha256", "authenticated_key_id"},
            )
            self.assertEqual(trust["registry_id"], "external-eod-registry-1")
            self.assertEqual(trust["authenticated_key_id"], "external-eod-key-v1")
            serialized_output_json = "\n".join(
                path.read_text(encoding="utf-8")
                for path in (
                    output / "manifest.json",
                    output / "official_eod_manifest.json",
                    output / "reports" / "official_eod_import_report.json",
                )
            )
            self.assertNotIn(payload["authentication"]["tag"], serialized_output_json)
            self.assertNotIn(key.hex(), serialized_output_json)
            verified = validate_official_eod_output(
                official_eod_root=output,
                official_foundation_root=official,
                status_history_root=history,
                runtime_trust_registry=registry,
            )
            self.assertEqual(verified["validation_status"], "PASS")
            self.assertEqual(verified["status"], "PARTIAL")
            without_external_trust = validate_official_eod_output(
                official_eod_root=output,
                official_foundation_root=official,
                status_history_root=history,
            )
            self.assertEqual(without_external_trust["validation_status"], "BLOCKED")
            self.assertIn(
                "OFFICIAL_EOD_SAVED_REPORT_CONTRACT_OR_RECEIPT_MISMATCH",
                without_external_trust["errors"],
            )

    def test_observed_at_must_follow_every_official_session_close(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            official, history, workspace = self._prepared(root)
            add_provider(workspace)
            manifest_path = workspace / "manifests" / "official_eod_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["providers"][0]["observed_at"] = "2026-08-09T12:39:59+03:00"
            manifest_path.write_bytes(canonical_json_bytes(manifest))
            with self.assertRaisesRegex(ValueError, "precedes official session close"):
                _import_official_daily_eod_unchecked(
                    workspace_root=workspace,
                    official_foundation_root=official,
                    status_history_root=history,
                    output_root=root / "early-provider-output",
                    run_id="official-eod-fixture",
                    imported_at="2026-08-09T18:00:00+03:00",
                )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            official, history, workspace = self._prepared(root)
            add_provider(workspace)
            add_matching_market_totals(workspace)
            manifest_path = workspace / "manifests" / "official_eod_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["market_totals"]["observed_at"] = "2026-08-09T12:39:59+03:00"
            manifest_path.write_bytes(canonical_json_bytes(manifest))
            with self.assertRaisesRegex(ValueError, "precedes official session close"):
                _import_official_daily_eod_unchecked(
                    workspace_root=workspace,
                    official_foundation_root=official,
                    status_history_root=history,
                    output_root=root / "early-totals-output",
                    run_id="official-eod-fixture",
                    imported_at="2026-08-09T18:00:00+03:00",
                )

    def test_provider_and_totals_cannot_use_a_future_import_clock(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            official, history, workspace = self._prepared(root)
            add_provider(workspace)
            add_matching_market_totals(workspace)
            manifest_path = workspace / "manifests" / "official_eod_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["providers"][0]["observed_at"] = "2099-01-01T00:00:00+03:00"
            manifest["market_totals"]["observed_at"] = "2099-01-01T00:00:00+03:00"
            manifest_path.write_bytes(canonical_json_bytes(manifest))

            with self.assertRaisesRegex(ValueError, "imported_at must not be in the future"):
                _import_official_daily_eod_unchecked(
                    workspace_root=workspace,
                    official_foundation_root=official,
                    status_history_root=history,
                    output_root=root / "future-clock-output",
                    run_id="official-eod-fixture",
                    imported_at="2099-01-02T00:00:00+03:00",
                )
            self.assertFalse((root / "future-clock-output").exists())

    def test_hash_mismatch_and_stale_upstream_fail_before_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            official, history, workspace = self._prepared(root)
            add_provider(workspace)
            provider_path = workspace / "raw_exports" / "providers" / "fixture-provider.csv"
            provider_path.write_bytes(provider_path.read_bytes() + b"tamper")
            output = root / "hash-output"
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                _import_official_daily_eod_unchecked(
                    workspace_root=workspace,
                    official_foundation_root=official,
                    status_history_root=history,
                    output_root=output,
                    run_id="official-eod-fixture",
                    imported_at="2026-08-09T18:00:00+03:00",
                )
            self.assertFalse(output.exists())

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            official, history, workspace = self._prepared(root)
            add_provider(workspace)
            master = official / "normalized" / "security_master.csv"
            master.write_text(
                master.read_text(encoding="utf-8").replace("NBK fixture", "NBK fixture changed"),
                encoding="utf-8",
                newline="",
            )
            output = root / "stale-output"
            with self.assertRaisesRegex(ValueError, "stale or substituted upstream"):
                _import_official_daily_eod_unchecked(
                    workspace_root=workspace,
                    official_foundation_root=official,
                    status_history_root=history,
                    output_root=output,
                    run_id="official-eod-fixture",
                    imported_at="2026-08-09T18:00:00+03:00",
                )
            self.assertFalse(output.exists())

    def test_validator_rehashes_normalized_output_and_import_is_non_overwriting(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            official, history, workspace = self._prepared(root)
            add_provider(workspace)
            output, _ = self._import(root, official, history, workspace)
            with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
                _import_official_daily_eod_unchecked(
                    workspace_root=workspace,
                    official_foundation_root=official,
                    status_history_root=history,
                    output_root=output,
                    run_id="official-eod-fixture",
                    imported_at="2026-08-09T18:00:00+03:00",
                )
            normalized = output / "normalized" / "official_daily_eod.csv"
            normalized.write_text(
                normalized.read_text(encoding="utf-8").replace(
                    "100,110,90,105,10", "100,110,90,106,10", 1
                ),
                encoding="utf-8",
                newline="",
            )
            validation = validate_official_eod_output(
                official_eod_root=output,
                official_foundation_root=official,
                status_history_root=history,
            )
            self.assertEqual(validation["validation_status"], "BLOCKED")
            self.assertIn(
                "NORMALIZED_OFFICIAL_EOD_DIFFERS_FROM_RECOMPUTATION",
                validation["errors"],
            )

    def test_validator_rejects_unknown_report_fields_and_receipt_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            official, history, workspace = self._prepared(root)
            add_provider(workspace)
            output, _ = self._import(root, official, history, workspace)
            report_path = output / "reports" / "official_eod_import_report.json"
            saved = json.loads(report_path.read_text(encoding="utf-8"))
            saved["caller_ready"] = True
            saved["official_daily_eod"]["path"] = "normalized/alias.csv"
            report_path.write_bytes(canonical_json_bytes(saved))

            validation = validate_official_eod_output(
                official_eod_root=output,
                official_foundation_root=official,
                status_history_root=history,
            )
            self.assertEqual(validation["validation_status"], "BLOCKED")
            self.assertIn(
                "OFFICIAL_EOD_SAVED_REPORT_CONTRACT_OR_RECEIPT_MISMATCH",
                validation["errors"],
            )

    def test_manifest_rejects_derived_field_claim_and_wrong_market_scope(self) -> None:
        for mutation, message in (
            ("field_origin", "direct source fields"),
            ("capture_mode", "official source cannot claim licensed capture"),
            ("market_scope", "DECLARED_PILOT"),
        ):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                official, history, workspace = self._prepared(root)
                add_provider(workspace)
                if mutation == "market_scope":
                    add_matching_market_totals(workspace)
                manifest_path = workspace / "manifests" / "official_eod_manifest.json"
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                if mutation == "field_origin":
                    manifest["providers"][0]["field_origin"] = "DERIVED_FIELDS"
                elif mutation == "capture_mode":
                    manifest["providers"][0]["capture_mode"] = "LICENSED_VENDOR_EXPORT"
                else:
                    manifest["market_totals"]["scope"] = "FULL_MARKET"
                manifest_path.write_bytes(canonical_json_bytes(manifest))
                with self.assertRaisesRegex(ValueError, message):
                    self._import(root, official, history, workspace)


if __name__ == "__main__":
    unittest.main()
