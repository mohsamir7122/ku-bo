from __future__ import annotations

import csv
from io import StringIO
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from kubo.data_foundation_reconciliation import (
    GATE_ORDER,
    _build_data_foundation_packet_unchecked,
    print_data_foundation_gate_report,
    read_data_foundation_gate_report,
    render_data_foundation_gate_report,
    _repository_secret_scan,
)


ROOT = Path(__file__).resolve().parents[1]
AUTHORITATIVE_POLICY = ROOT / "config" / "pilot" / "outcome_session_policy.json"


def _canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_json(value))


def _write_csv(path: Path, headers: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(root: Path, *arguments: str) -> None:
    result = subprocess.run(
        ["git", "-C", str(root), *arguments],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"git fixture command failed with exit code {result.returncode}"
        )


def _guard_git_repository(parent: Path) -> Path:
    root = parent / "repository"
    root.mkdir()
    required = {
        "AGENTS.md": "# agents\n",
        "CODEX_START_HERE.md": "# start\n",
        "config/pilot/security_master_seed.json": "{}\n",
        "config/sources.json": '{"sources": []}\n',
        "docs/codex/CURRENT_TASK.md": "# task\n",
        "pyproject.toml": "[project]\nname='guard-fixture'\nversion='0'\n",
    }
    for relative, content in required.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "guard@example.test")
    _git(root, "config", "user.name", "Guard Fixture")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "required repository markers")
    return root


def _manifest(
    root: Path,
    component: str,
    *,
    classification: str = "PROVEN_REAL_EVIDENCE",
    rights_status: str = "RESEARCH_USE_AUTHORIZED",
    source_id: str = "ignored_as_proof",
    source_url: str = "https://example.test/evidence",
) -> str:
    content = (component + " preserved raw evidence\n").encode("utf-8")
    raw_path = root / "raw" / "evidence.bin"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()
    _write_json(
        root / "manifest.json",
        {
            "schema_version": "3.0",
            "artifacts": [
                {
                    "path": "raw/evidence.bin",
                    "sha256": digest,
                    "size_bytes": len(content),
                    "source_id": source_id,
                    "source_url": source_url,
                    "observed_at": "2026-08-09T09:00:00+03:00",
                    "capture_kind": (
                        "RECORDED_AUTHORIZED_FIXTURE"
                        if classification == "RECORDED_AUTHORIZED_FIXTURE"
                        else "USER_EXPORT"
                    ),
                    "artifact_role": "RAW_EVIDENCE",
                    "evidence_classification": classification,
                    "rights_status": rights_status,
                }
            ],
        },
    )
    return digest


def _component_roots(
    root: Path,
    *,
    classification: str = "PROVEN_REAL_EVIDENCE",
    rights_status: str = "RESEARCH_USE_AUTHORIZED",
    source_id: str = "ignored_as_proof",
    source_url: str = "https://example.test/evidence",
) -> dict[str, Path]:
    official = root / "official"
    official_hash = _manifest(
        official,
        "official",
        classification=classification,
        rights_status=rights_status,
        source_id=source_id,
        source_url=source_url,
    )
    _write_json(
        official / "reports" / "official_foundation_import_report.json",
        {
            "status": "CURRENT_IDENTITY_AND_CALENDAR_READY",
            "identity_status": "PASS",
            "calendar_status": "PASS",
        },
    )
    _write_json(official / "reports" / "official_identity_report.json", {"status": "PASS"})
    _write_json(official / "reports" / "trading_calendar_report.json", {"status": "PASS"})
    _write_json(official / "official_foundation_manifest.json", {"schema_version": "1.0"})
    _write_csv(
        official / "normalized" / "security_master.csv",
        (
            "security_code",
            "ticker",
            "isin",
            "valid_from",
            "valid_to",
            "raw_sha256",
            "supporting_raw_sha256s",
            "identity_scope",
        ),
        [
            {
                "security_code": "101",
                "ticker": "TEST",
                "isin": "KW0000000001",
                "valid_from": "2026-01-01",
                "valid_to": "",
                "raw_sha256": official_hash,
                "supporting_raw_sha256s": "",
                "identity_scope": "POINT_IN_TIME_OFFICIAL",
            }
        ],
    )
    _write_csv(
        official / "normalized" / "trading_calendar.csv",
        ("trade_date", "is_trading_day", "raw_sha256", "supporting_raw_sha256s"),
        [
            {
                "trade_date": "2026-08-09",
                "is_trading_day": "true",
                "raw_sha256": official_hash,
                "supporting_raw_sha256s": "",
            }
        ],
    )

    status = root / "status"
    status_hash = _manifest(
        status,
        "status",
        classification=classification,
        rights_status=rights_status,
        source_id=source_id,
        source_url=source_url,
    )
    _write_json(
        status / "reports" / "status_history_import_report.json",
        {
            "status": "HISTORICAL_STATUS_INTERVALS_READY",
            "errors": [],
            "claim_boundaries": {"status_history_ready_for_declared_window": True},
        },
    )
    _write_json(status / "reports" / "status_history_validation_report.json", {"status": "PASS"})
    _write_json(status / "status_history_manifest.json", {"schema_version": "1.0"})
    _write_csv(
        status / "normalized" / "status_intervals.csv",
        (
            "security_code",
            "ticker",
            "status",
            "effective_from",
            "effective_to",
            "opening_evidence_sha256",
            "evidence_hashes",
        ),
        [
            {
                "security_code": "101",
                "ticker": "TEST",
                "status": "TRADING",
                "effective_from": "2026-01-01",
                "effective_to": "2026-12-31",
                "opening_evidence_sha256": status_hash,
                "evidence_hashes": status_hash,
            }
        ],
    )
    _write_csv(
        status / "normalized" / "opening_status_evidence.csv",
        ("security_code", "status", "effective_date", "raw_sha256"),
        [
            {
                "security_code": "101",
                "status": "TRADING",
                "effective_date": "2026-01-01",
                "raw_sha256": status_hash,
            }
        ],
    )
    _write_csv(
        status / "manifests" / "status_query_ledger.csv",
        (
            "query_id",
            "security_code",
            "pages_declared",
            "pages_received",
            "result_count_declared",
            "rows_normalized",
            "zero_result",
            "raw_sha256",
        ),
        [
            {
                "query_id": "status-101",
                "security_code": "101",
                "pages_declared": "1",
                "pages_received": "1",
                "result_count_declared": "0",
                "rows_normalized": "0",
                "zero_result": "true",
                "raw_sha256": status_hash,
            }
        ],
    )

    ca = root / "ca"
    ca_hash = _manifest(
        ca,
        "ca",
        classification=classification,
        rights_status=rights_status,
        source_id=source_id,
        source_url=source_url,
    )
    _write_json(
        ca / "reports" / "ca_enrichment_import_report.json",
        {"status": "CA_ENRICHMENT_READY", "errors": []},
    )
    _write_json(ca / "ca_enrichment_manifest.json", {"schema_version": "1.0"})
    factor_headers = (
        "action_id",
        "security_code",
        "action_type",
        "reference_price_factor",
        "historical_continuity_factor",
        "position_quantity_multiplier",
        "return_price_multiplier",
        "cash_distribution_per_pre_action_share_fils",
        "rights_cash_contribution_per_pre_action_share_fils",
        "return_engine_treatment",
        "return_engine_ready",
        "disclosure_raw_sha256",
        "disclosure_text_sha256",
        "price_reference_raw_sha256",
    )
    _write_csv(
        ca / "normalized" / "corporate_action_factor_ledger.csv",
        factor_headers,
        [
            {
                "action_id": "cash-1",
                "security_code": "101",
                "action_type": "CASH_DIVIDEND_NORMAL",
                "reference_price_factor": "0.95",
                "historical_continuity_factor": "0.95",
                "position_quantity_multiplier": "1",
                "return_price_multiplier": "1",
                "cash_distribution_per_pre_action_share_fils": "5",
                "rights_cash_contribution_per_pre_action_share_fils": "",
                "return_engine_treatment": "RAW_PRICE_PLUS_CASH_COMPONENT",
                "return_engine_ready": "true",
                "disclosure_raw_sha256": ca_hash,
                "disclosure_text_sha256": ca_hash,
                "price_reference_raw_sha256": ca_hash,
            }
        ],
    )
    _write_csv(
        ca / "normalized" / "corporate_action_return_policy_queue.csv",
        ("action_id", "action_type", "required_policy", "factor_status", "review_status"),
        [],
    )

    research = root / "research"
    research_hash = _manifest(
        research,
        "research",
        classification=classification,
        rights_status=rights_status,
        source_id=source_id,
        source_url=source_url,
    )
    collection_manifest = research / "price_collection_manifest.csv"
    _write_csv(collection_manifest, ("ticker", "row_count"), [{"ticker": "TEST", "row_count": "1"}])
    collection_hash = hashlib.sha256(collection_manifest.read_bytes()).hexdigest()
    _write_json(
        research / "reports" / "user_export_import_report.json",
        {
            "status": "RESEARCH_PRICE_HISTORY_READY",
            "price_history_status": "RESEARCH_PRICE_HISTORY_READY",
            "collection_manifest_sha256": collection_hash,
            "manifest_errors": [],
            "errors": [],
        },
    )
    _write_json(research / "reports" / "data_quality_report.json", {"status": "PASS"})
    _write_csv(
        research / "normalized" / "research_price_history.csv",
        (
            "trade_date",
            "security_code",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "raw_sha256",
            "capture_mode",
            "price_basis",
            "currency",
            "unit",
            "corporate_action_status",
        ),
        [
            {
                "trade_date": "2026-08-09",
                "security_code": "101",
                "open": "100",
                "high": "101",
                "low": "99",
                "close": "100",
                "volume": "1",
                "raw_sha256": research_hash,
                "capture_mode": (
                    "RECORDED_AUTHORIZED_FIXTURE"
                    if classification == "RECORDED_AUTHORIZED_FIXTURE"
                    else "USER_EXPORT"
                ),
                "price_basis": "RAW",
                "currency": "KWD",
                "unit": "fils",
                "corporate_action_status": "raw_unadjusted",
            }
        ],
    )

    benchmark = root / "benchmark"
    benchmark_hash = _manifest(
        benchmark,
        "benchmark",
        classification=classification,
        rights_status=rights_status,
        source_id=source_id,
        source_url=source_url,
    )
    _write_json(
        benchmark / "reports" / "benchmark_import_report.json",
        {
            "status": "READY",
            "query_and_pagination_status": "PASS",
            "errors": [],
            "benchmark_entries": [
                {
                    "benchmark_code": "BROAD_PRICE",
                    "availability_status": "AVAILABLE",
                    "validation_status": "PASS",
                    "missing_trading_dates": [],
                    "extra_trading_dates": [],
                }
            ],
        },
    )
    _write_json(benchmark / "benchmark_registry.json", {"schema_version": "1.0"})
    _write_json(
        benchmark / "benchmark_history_manifest.json",
        {
            "benchmarks": [
                {
                    "benchmark_code": "BROAD_PRICE",
                    "pages_declared": 1,
                    "pages_received": 1,
                    "result_count_declared": 1,
                    "row_count": 1,
                }
            ]
        },
    )
    _write_json(benchmark / "upstream_calendar_receipt.json", {"status": "PASS"})
    _write_csv(
        benchmark / "normalized" / "benchmark_history.csv",
        ("trade_date", "benchmark_code", "benchmark_type", "raw_sha256"),
        [
            {
                "trade_date": "2026-08-09",
                "benchmark_code": "BROAD_PRICE",
                "benchmark_type": "PRICE_INDEX",
                "raw_sha256": benchmark_hash,
            }
        ],
    )

    eod = root / "eod"
    eod_hash = _manifest(
        eod,
        "eod",
        classification=classification,
        rights_status=rights_status,
        source_id=source_id,
        source_url=source_url,
    )
    _write_json(
        eod / "reports" / "official_eod_import_report.json",
        {
            "status": "READY",
            "denominator_status": "PASS",
            "price_evidence_status": "PASS",
            "market_totals_status": "PASS",
            "query_and_pagination_status": "PASS",
            "expected_pair_count": 1,
            "normalized_row_count": 1,
            "missing_pair_count": 0,
            "quarantine_count": 0,
            "errors": [],
        },
    )
    _write_csv(
        eod / "normalized" / "official_daily_eod.csv",
        (
            "trade_date",
            "security_code",
            "ticker",
            "trading_state",
            "price_basis",
            "close_fils",
            "raw_sha256",
            "supporting_raw_sha256s",
        ),
        [
            {
                "trade_date": "2026-08-09",
                "security_code": "101",
                "ticker": "TEST",
                "trading_state": "TRADED",
                "price_basis": "RAW_UNADJUSTED",
                "close_fils": "100",
                "raw_sha256": eod_hash,
                "supporting_raw_sha256s": "",
            }
        ],
    )
    _write_csv(
        eod / "normalized" / "daily_market_totals.csv",
        ("trade_date", "total_value_kwd", "raw_sha256", "supporting_raw_sha256s"),
        [
            {
                "trade_date": "2026-08-09",
                "total_value_kwd": "100",
                "raw_sha256": eod_hash,
                "supporting_raw_sha256s": "",
            }
        ],
    )

    benchmark_receipt = {
        "official_foundation_report_sha256": _file_sha256(
            official / "reports" / "official_foundation_import_report.json"
        ),
        "trading_calendar_sha256": _file_sha256(
            official / "normalized" / "trading_calendar.csv"
        ),
        "evidence_manifest_sha256": _file_sha256(official / "manifest.json"),
    }
    _write_json(benchmark / "upstream_calendar_receipt.json", benchmark_receipt)
    benchmark_report_path = benchmark / "reports" / "benchmark_import_report.json"
    benchmark_report = json.loads(benchmark_report_path.read_text(encoding="utf-8"))
    benchmark_report.update(
        {
            "registry_sha256": _file_sha256(benchmark / "benchmark_registry.json"),
            "row_count": 1,
            "window_from": "2026-08-09",
            "window_to": "2026-08-09",
        }
    )
    _write_json(benchmark_report_path, benchmark_report)

    upstream = {
        "official_foundation": {
            "report_sha256": _file_sha256(
                official / "reports" / "official_foundation_import_report.json"
            ),
            "manifest_sha256": _file_sha256(official / "manifest.json"),
            "security_master_sha256": _file_sha256(
                official / "normalized" / "security_master.csv"
            ),
            "trading_calendar_sha256": _file_sha256(
                official / "normalized" / "trading_calendar.csv"
            ),
        },
        "status_history": {
            "report_sha256": _file_sha256(
                status / "reports" / "status_history_import_report.json"
            ),
            "manifest_sha256": _file_sha256(status / "manifest.json"),
            "status_intervals_sha256": _file_sha256(
                status / "normalized" / "status_intervals.csv"
            ),
            "status_query_ledger_sha256": _file_sha256(
                status / "manifests" / "status_query_ledger.csv"
            ),
        },
    }
    _write_json(
        eod / "official_eod_manifest.json",
        {
            "schema_version": "1.0",
            "window_from": "2026-08-09",
            "window_to": "2026-08-09",
            "upstream": upstream,
        },
    )
    eod_report_path = eod / "reports" / "official_eod_import_report.json"
    eod_report = json.loads(eod_report_path.read_text(encoding="utf-8"))
    eod_report.update(
        {
            "window_from": "2026-08-09",
            "window_to": "2026-08-09",
            "upstream": upstream,
            "official_eod_manifest_sha256": _file_sha256(
                eod / "official_eod_manifest.json"
            ),
            "official_daily_eod": {
                "path": "normalized/official_daily_eod.csv",
                "sha256": _file_sha256(
                    eod / "normalized" / "official_daily_eod.csv"
                ),
                "rows": 1,
            },
            "daily_market_totals": {
                "path": "normalized/daily_market_totals.csv",
                "sha256": _file_sha256(
                    eod / "normalized" / "daily_market_totals.csv"
                ),
                "rows": 1,
            },
        }
    )
    _write_json(eod_report_path, eod_report)

    return {
        "official_foundation_root": official,
        "status_history_root": status,
        "ca_enrichment_root": ca,
        "research_price_history_root": research,
        "benchmark_root": benchmark,
        "official_eod_root": eod,
    }


def _write_full_factor_contract(
    inputs: dict[str, Path],
    *,
    ex_date: str = "2026-08-09",
) -> None:
    factor_path = (
        inputs["ca_enrichment_root"]
        / "normalized"
        / "corporate_action_factor_ledger.csv"
    )
    rows = list(csv.DictReader(factor_path.read_text(encoding="utf-8").splitlines()))
    rows[0].update(
        {
            "ticker": "TEST",
            "isin": "KW0000000001",
            "ex_date": ex_date,
        }
    )
    _write_csv(factor_path, tuple(rows[0]), rows)


def _write_full_benchmark_contract(inputs: dict[str, Path]) -> None:
    benchmark_path = (
        inputs["benchmark_root"] / "normalized" / "benchmark_history.csv"
    )
    rows = list(
        csv.DictReader(benchmark_path.read_text(encoding="utf-8").splitlines())
    )
    rows[0]["calculation_basis"] = "TOTAL_RETURN_INDEX"
    _write_csv(benchmark_path, tuple(rows[0]), rows)


def _refresh_calendar_receipts(inputs: dict[str, Path]) -> None:
    official = inputs["official_foundation_root"]
    benchmark = inputs["benchmark_root"]
    eod = inputs["official_eod_root"]
    calendar_hash = _file_sha256(official / "normalized" / "trading_calendar.csv")

    benchmark_receipt_path = benchmark / "upstream_calendar_receipt.json"
    benchmark_receipt = json.loads(
        benchmark_receipt_path.read_text(encoding="utf-8")
    )
    benchmark_receipt["trading_calendar_sha256"] = calendar_hash
    _write_json(benchmark_receipt_path, benchmark_receipt)

    manifest_path = eod / "official_eod_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["upstream"]["official_foundation"][
        "trading_calendar_sha256"
    ] = calendar_hash
    _write_json(manifest_path, manifest)

    report_path = eod / "reports" / "official_eod_import_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["upstream"] = manifest["upstream"]
    report["official_eod_manifest_sha256"] = _file_sha256(manifest_path)
    _write_json(report_path, report)


def _refresh_eod_normalized_receipt(inputs: dict[str, Path]) -> None:
    eod = inputs["official_eod_root"]
    normalized_path = eod / "normalized" / "official_daily_eod.csv"
    report_path = eod / "reports" / "official_eod_import_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["official_daily_eod"]["sha256"] = _file_sha256(normalized_path)
    _write_json(report_path, report)


def _policy(path: Path, *, frozen: bool = True) -> Path:
    _write_json(
        path,
        {
            "schema_version": "1.0",
            "policy_id": "KU_BO_PILOT_OUTCOME_SESSION_POLICY",
            "status": "FROZEN" if frozen else "UNFROZEN",
            "timezone": "Asia/Kuwait",
            "horizon_basis": "OFFICIAL_TRADING_SESSIONS",
            "non_trading_day_rule": "ADVANCE_TO_NEXT_ELIGIBLE_OFFICIAL_SESSION",
            "suspended_or_halted_rule": (
                "ADVANCE_TO_NEXT_ELIGIBLE_OFFICIAL_SESSION" if frozen else "UNDECIDED"
            ),
            "corporate_action_rule": "RAW_PRICE_PLUS_SEPARATE_CASH_COMPONENT",
            "adjusted_price_double_count_guard": True,
            "rights_issue_policy": "BLOCK_UNTIL_EXERCISE_SALE_LAPSE_POLICY_FROZEN",
            "complex_action_policy": "BLOCK_UNTIL_RETURN_TREATMENT_FROZEN",
            "decision_id": "KU-BO-008-D01",
            "claim_boundary": (
                "OUTCOME_SESSION_POLICY_FROZEN"
                if frozen
                else "OUTCOME_SESSION_POLICY_NOT_FROZEN"
            ),
        },
    )
    return path


class DataFoundationReconciliationTests(unittest.TestCase):
    def _build(
        self,
        root: Path,
        *,
        classification: str = "RECORDED_AUTHORIZED_FIXTURE",
        rights_status: str = "FIXTURE_ONLY",
        source_id: str = "ignored_as_proof",
        source_url: str = "https://example.test/evidence",
    ) -> tuple[dict[str, object], Path, dict[str, Path]]:
        inputs = _component_roots(
            root / "inputs",
            classification=classification,
            rights_status=rights_status,
            source_id=source_id,
            source_url=source_url,
        )
        output = root / "output"
        report = _build_data_foundation_packet_unchecked(
            **inputs,
            project_root=ROOT,
            output_root=output,
            outcome_session_policy_path=AUTHORITATIVE_POLICY,
        )
        return report, output, inputs

    def test_self_attested_real_packet_is_blocked_without_source_authority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report, output, _ = self._build(
                Path(directory),
                classification="PROVEN_REAL_EVIDENCE",
                rights_status="RESEARCH_USE_AUTHORIZED",
            )
            self.assertEqual(
                report["status"],
                "DATA_FOUNDATION_BLOCKED",
            )
            self.assertEqual(
                tuple(gate["gate"] for gate in report["gates"]),
                GATE_ORDER,
            )
            self.assertTrue(any(gate["status"] == "BLOCKED" for gate in report["gates"]))
            self.assertTrue(
                any(
                    "UNREGISTERED_REAL_SOURCE" in error
                    for gate in report["gates"]
                    for error in gate["errors"]
                )
            )
            self.assertTrue(
                any(
                    "ARTIFACT_BOUND_CAPTURE_AUTHORITY_REQUIRED" in error
                    for gate in report["gates"]
                    for error in gate["errors"]
                )
            )
            loaded = read_data_foundation_gate_report(
                output / "reports" / "data_foundation_gate_report.json"
            )
            self.assertEqual(loaded, report)
            packet_text = (output / "data_foundation_packet.json").read_text(encoding="utf-8")
            self.assertNotIn(directory, packet_text)
            self.assertNotIn("observed_at", packet_text)

    def test_allowlisted_official_labels_cannot_promote_self_authored_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report, _, _ = self._build(
                Path(directory),
                classification="PROVEN_REAL_EVIDENCE",
                rights_status="RESEARCH_USE_AUTHORIZED",
                source_id="boursa_kuwait",
                source_url="https://www.boursakuwait.com.kw/markets/official-export",
            )
            errors = [
                error
                for gate in report["gates"]
                for error in gate["errors"]
            ]
            self.assertEqual(report["status"], "DATA_FOUNDATION_BLOCKED")
            self.assertTrue(
                any(
                    "ARTIFACT_BOUND_CAPTURE_AUTHORITY_REQUIRED" in error
                    for error in errors
                )
            )
            self.assertFalse(
                any("UNREGISTERED_REAL_SOURCE" in error for error in errors)
            )
            self.assertFalse(
                any("REAL_PROVENANCE_INVALID" in error for error in errors)
            )

    def test_fixture_packet_stays_partial_and_never_promotes_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report, _, _ = self._build(
                Path(directory),
                classification="RECORDED_AUTHORIZED_FIXTURE",
                rights_status="FIXTURE_ONLY",
            )
            self.assertEqual(report["status"], "DATA_FOUNDATION_PARTIAL")
            self.assertEqual(
                report["evidence_classification"],
                "RECORDED_AUTHORIZED_FIXTURE",
            )
            self.assertFalse(any(gate["status"] == "BLOCKED" for gate in report["gates"]))
            ca_gate = next(
                gate
                for gate in report["gates"]
                if gate["gate"] == "PRICE_CORPORATE_ACTION_QA"
            )
            self.assertEqual(
                ca_gate["details"]["checks"]["status_session_integration"],
                "PARTIAL",
            )
            self.assertEqual(
                ca_gate["details"]["metrics"][
                    "ca_rows_unverifiable_without_invention"
                ],
                1,
            )
            secret_gate = next(
                gate for gate in report["gates"] if gate["gate"] == "RUNTIME_SECRET_GUARD"
            )
            self.assertEqual(secret_gate["status"], "PASS")
            self.assertRegex(
                secret_gate["details"]["metrics"]["repository_head_sha"],
                r"^[0-9a-f]{40,64}$",
            )

    def test_synthetic_packet_stays_partial(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report, _, _ = self._build(
                Path(directory),
                classification="SYNTHETIC_ONLY",
                rights_status="SYNTHETIC_ONLY",
            )
            self.assertEqual(report["status"], "DATA_FOUNDATION_PARTIAL")
            self.assertEqual(report["evidence_classification"], "SYNTHETIC_ONLY")
            self.assertFalse(any(gate["status"] == "BLOCKED" for gate in report["gates"]))

    def test_unfrozen_policy_is_explicit_claim_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report, _, _ = self._build(Path(directory))
            self.assertEqual(report["status"], "DATA_FOUNDATION_PARTIAL")
            self.assertIn(
                "OUTCOME_SESSION_POLICY_NOT_FROZEN",
                report["claim_boundaries"],
            )
            claim_gate = report["gates"][-1]
            self.assertEqual(claim_gate["status"], "PARTIAL")
            self.assertIn("OUTCOME_SESSION_POLICY_NOT_FROZEN", claim_gate["errors"])

    def test_upstream_hash_mismatch_is_structural_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = _component_roots(
                root / "inputs",
                classification="RECORDED_AUTHORIZED_FIXTURE",
                rights_status="FIXTURE_ONLY",
            )
            raw = inputs["benchmark_root"] / "raw" / "evidence.bin"
            raw.write_bytes(b"tampered after manifest\n")
            report = _build_data_foundation_packet_unchecked(
                **inputs,
                project_root=ROOT,
                output_root=root / "output",
                outcome_session_policy_path=AUTHORITATIVE_POLICY,
            )
            self.assertEqual(report["status"], "DATA_FOUNDATION_BLOCKED")
            benchmark_gate = next(
                gate for gate in report["gates"] if gate["gate"] == "BENCHMARK_EVIDENCE"
            )
            self.assertEqual(benchmark_gate["status"], "BLOCKED")
            self.assertTrue(any("sha256" in error for error in benchmark_gate["errors"]))

    def test_stale_upstream_receipt_is_structural_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = _component_roots(root / "inputs")
            calendar = (
                inputs["official_foundation_root"]
                / "normalized"
                / "trading_calendar.csv"
            )
            calendar.write_bytes(calendar.read_bytes() + b"\n")
            report = _build_data_foundation_packet_unchecked(
                **inputs,
                project_root=ROOT,
                output_root=root / "output",
                outcome_session_policy_path=AUTHORITATIVE_POLICY,
            )
            self.assertEqual(report["status"], "DATA_FOUNDATION_BLOCKED")
            errors = [error for gate in report["gates"] for error in gate["errors"]]
            self.assertTrue(any("STALE_OR_SUBSTITUTED" in error for error in errors))

    def test_legacy_manifest_metadata_is_partial_not_inferred_real(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = _component_roots(
                root / "inputs",
                classification="RECORDED_AUTHORIZED_FIXTURE",
                rights_status="FIXTURE_ONLY",
            )
            manifest_path = inputs["ca_enrichment_root"] / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            for artifact in manifest["artifacts"]:
                artifact.pop("evidence_classification")
                artifact.pop("rights_status")
            _write_json(manifest_path, manifest)
            report = _build_data_foundation_packet_unchecked(
                **inputs,
                project_root=ROOT,
                output_root=root / "output",
                outcome_session_policy_path=AUTHORITATIVE_POLICY,
            )
            self.assertEqual(report["status"], "DATA_FOUNDATION_PARTIAL")
            ca_gate = next(
                gate
                for gate in report["gates"]
                if gate["gate"] == "PRICE_CORPORATE_ACTION_QA"
            )
            self.assertEqual(ca_gate["status"], "PARTIAL")
            self.assertTrue(
                any("HASH_BOUND_EVIDENCE_CLASSIFICATION_MISSING" in value for value in ca_gate["errors"])
            )

    def test_unknown_policy_field_is_structural_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = _component_roots(root / "inputs")
            policy_path = _policy(root / "policy.json")
            policy = json.loads(policy_path.read_text(encoding="utf-8"))
            policy["caller_ready"] = True
            project_root = root / "project"
            authoritative = (
                project_root / "config" / "pilot" / "outcome_session_policy.json"
            )
            _write_json(authoritative, policy)
            report = _build_data_foundation_packet_unchecked(
                **inputs,
                project_root=project_root,
                output_root=root / "output",
                outcome_session_policy_path=authoritative,
            )
            self.assertEqual(report["status"], "DATA_FOUNDATION_BLOCKED")
            self.assertIn(
                "OUTCOME_SESSION_POLICY_UNKNOWN_OR_MISSING_FIELDS",
                report["gates"][-1]["errors"],
            )

    def test_policy_decision_identity_and_unfrozen_contract_cannot_be_forged(self) -> None:
        for field, value in (
            ("decision_id", "unrecorded-decision"),
            ("corporate_action_rule", "UNDECIDED"),
        ):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                inputs = _component_roots(root / "inputs")
                policy_path = _policy(root / "policy.json", frozen=False)
                policy = json.loads(policy_path.read_text(encoding="utf-8"))
                policy[field] = value
                project_root = root / "project"
                authoritative = (
                    project_root / "config" / "pilot" / "outcome_session_policy.json"
                )
                _write_json(authoritative, policy)
                report = _build_data_foundation_packet_unchecked(
                    **inputs,
                    project_root=project_root,
                    output_root=root / "output",
                    outcome_session_policy_path=authoritative,
                )
                self.assertEqual(report["status"], "DATA_FOUNDATION_BLOCKED")
                self.assertTrue(
                    any(
                        "OUTCOME_SESSION_POLICY_CONTRACT_FIELDS_INVALID" in error
                        for error in report["gates"][-1]["errors"]
                    )
                )

    def test_external_frozen_policy_cannot_override_authoritative_open_decision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = _component_roots(root / "inputs")
            external = _policy(root / "external-frozen-policy.json", frozen=True)
            report = _build_data_foundation_packet_unchecked(
                **inputs,
                project_root=ROOT,
                output_root=root / "output",
                outcome_session_policy_path=external,
            )
            self.assertEqual(report["status"], "DATA_FOUNDATION_BLOCKED")
            self.assertIn(
                "OUTCOME_SESSION_POLICY_NOT_AUTHORITATIVE",
                report["gates"][-1]["errors"],
            )

    def test_global_option_one_frozen_policy_fails_while_decision_is_open(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = _component_roots(root / "inputs")
            project_root = root / "project"
            authoritative = _policy(
                project_root / "config" / "pilot" / "outcome_session_policy.json",
                frozen=True,
            )
            policy = json.loads(authoritative.read_text(encoding="utf-8"))
            policy["suspended_or_halted_rule"] = "UNDECIDED"
            policy["claim_boundary"] = "OUTCOME_SESSION_POLICY_NOT_FROZEN"
            _write_json(authoritative, policy)
            report = _build_data_foundation_packet_unchecked(
                **inputs,
                project_root=project_root,
                output_root=root / "output",
                outcome_session_policy_path=authoritative,
            )
            self.assertEqual(report["status"], "DATA_FOUNDATION_BLOCKED")
            self.assertIn(
                "OUTCOME_SESSION_USER_DECISION_NOT_APPROVED:KU-BO-008-D01",
                report["gates"][-1]["errors"],
            )

    def test_uncommitted_worktree_frozen_policy_cannot_promote(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = _component_roots(root / "inputs")
            project_root = root / "project"
            authoritative = _policy(
                project_root / "config" / "pilot" / "outcome_session_policy.json",
                frozen=True,
            )
            report = _build_data_foundation_packet_unchecked(
                **inputs,
                project_root=project_root,
                output_root=root / "output",
                outcome_session_policy_path=authoritative,
            )
            self.assertEqual(report["status"], "DATA_FOUNDATION_BLOCKED")
            self.assertIn(
                "OUTCOME_SESSION_USER_DECISION_NOT_APPROVED:KU-BO-008-D01",
                report["gates"][-1]["errors"],
            )

    def test_committed_global_option_one_cannot_approve_open_d01(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = _component_roots(root / "inputs")
            project_root = _guard_git_repository(root)
            authoritative = _policy(
                project_root / "config" / "pilot" / "outcome_session_policy.json",
                frozen=True,
            )
            _git(project_root, "add", "config/pilot/outcome_session_policy.json")
            _git(project_root, "commit", "-q", "-m", "attempt global option one")
            report = _build_data_foundation_packet_unchecked(
                **inputs,
                project_root=project_root,
                output_root=root / "output",
                outcome_session_policy_path=authoritative,
            )
            self.assertEqual(report["status"], "DATA_FOUNDATION_BLOCKED")
            self.assertIn(
                "OUTCOME_SESSION_USER_DECISION_NOT_APPROVED:KU-BO-008-D01",
                report["gates"][-1]["errors"],
            )

    def test_rights_issue_and_adjusted_price_risks_are_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = _component_roots(root / "inputs")
            ca_path = (
                inputs["ca_enrichment_root"]
                / "normalized"
                / "corporate_action_factor_ledger.csv"
            )
            rows = list(csv.DictReader(ca_path.read_text(encoding="utf-8").splitlines()))
            rows[0].update(
                {
                    "action_id": "rights-1",
                    "action_type": "RIGHTS_ISSUE",
                    "return_price_multiplier": "",
                    "cash_distribution_per_pre_action_share_fils": "",
                    "rights_cash_contribution_per_pre_action_share_fils": "30",
                    "return_engine_treatment": "BLOCKED_RIGHTS_EXERCISE_OR_SALE_POLICY",
                    "return_engine_ready": "false",
                }
            )
            _write_csv(ca_path, tuple(rows[0]), rows)
            policy_path = (
                inputs["ca_enrichment_root"]
                / "normalized"
                / "corporate_action_return_policy_queue.csv"
            )
            _write_csv(
                policy_path,
                ("action_id", "action_type", "required_policy", "factor_status", "review_status"),
                [
                    {
                        "action_id": "rights-1",
                        "action_type": "RIGHTS_ISSUE",
                        "required_policy": "EXERCISE_SALE_LAPSE",
                        "factor_status": "reproducible",
                        "review_status": "PENDING",
                    }
                ],
            )
            eod_path = inputs["official_eod_root"] / "normalized" / "official_daily_eod.csv"
            eod_rows = list(csv.DictReader(eod_path.read_text(encoding="utf-8").splitlines()))
            eod_rows[0]["price_basis"] = "OFFICIALLY_ADJUSTED"
            _write_csv(eod_path, tuple(eod_rows[0]), eod_rows)
            report = _build_data_foundation_packet_unchecked(
                **inputs,
                project_root=ROOT,
                output_root=root / "output",
                outcome_session_policy_path=AUTHORITATIVE_POLICY,
            )
            gate = next(
                item for item in report["gates"] if item["gate"] == "PRICE_CORPORATE_ACTION_QA"
            )
            self.assertEqual(gate["status"], "BLOCKED")
            self.assertIn("ADJUSTED_PRICE_DOUBLE_COUNT_RISK", gate["errors"])
            self.assertIn("RIGHTS_OR_COMPLEX_RETURN_POLICY_PENDING", gate["errors"])
            self.assertIn("CASH_COMPONENT", gate["details"]["concepts"])

    def test_ca_factor_unknown_security_code_blocks_all_identity_status_joins(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = _component_roots(
                root / "inputs",
                classification="RECORDED_AUTHORIZED_FIXTURE",
                rights_status="FIXTURE_ONLY",
            )
            factor_path = (
                inputs["ca_enrichment_root"]
                / "normalized"
                / "corporate_action_factor_ledger.csv"
            )
            rows = list(
                csv.DictReader(factor_path.read_text(encoding="utf-8").splitlines())
            )
            rows[0]["security_code"] = "999"
            _write_csv(factor_path, tuple(rows[0]), rows)

            report = _build_data_foundation_packet_unchecked(
                **inputs,
                project_root=ROOT,
                output_root=root / "output",
                outcome_session_policy_path=AUTHORITATIVE_POLICY,
            )
            gate = next(
                item
                for item in report["gates"]
                if item["gate"] == "PRICE_CORPORATE_ACTION_QA"
            )
            self.assertEqual(report["status"], "DATA_FOUNDATION_BLOCKED")
            self.assertEqual(gate["status"], "BLOCKED")
            self.assertIn(
                "CA_FACTOR_ROW_0_OFFICIAL_IDENTITY_SECURITY_CODE_UNKNOWN",
                gate["errors"],
            )
            self.assertIn(
                "CA_FACTOR_ROW_0_STATUS_SECURITY_CODE_UNKNOWN",
                gate["errors"],
            )
            self.assertEqual(
                gate["details"]["checks"]["status_session_integration"],
                "BLOCKED",
            )

    def test_full_ca_action_contract_joins_identity_calendar_status_and_eod(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = _component_roots(
                root / "inputs",
                classification="RECORDED_AUTHORIZED_FIXTURE",
                rights_status="FIXTURE_ONLY",
            )
            _write_full_factor_contract(inputs)
            _write_full_benchmark_contract(inputs)
            report = _build_data_foundation_packet_unchecked(
                **inputs,
                project_root=ROOT,
                output_root=root / "output",
                outcome_session_policy_path=AUTHORITATIVE_POLICY,
            )
            gate = next(
                item
                for item in report["gates"]
                if item["gate"] == "PRICE_CORPORATE_ACTION_QA"
            )
            self.assertEqual(report["status"], "DATA_FOUNDATION_PARTIAL")
            self.assertEqual(gate["status"], "PARTIAL")
            self.assertEqual(gate["errors"], [])
            for check in (
                "affected_eod_coverage",
                "benchmark_basis_comparison",
                "benchmark_treatment_separation",
                "corporate_action_identity_join",
                "official_action_calendar_join",
                "policy_factor_action_link",
                "status_session_integration",
            ):
                self.assertEqual(gate["details"]["checks"][check], "PASS")
            self.assertEqual(
                gate["details"]["metrics"]["ca_factor_rows_joined"], 1
            )
            self.assertEqual(
                gate["details"]["metrics"]["affected_eod_rows_joined"], 1
            )

    def test_ca_action_outside_eod_window_does_not_require_an_eod_row(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = _component_roots(
                root / "inputs",
                classification="RECORDED_AUTHORIZED_FIXTURE",
                rights_status="FIXTURE_ONLY",
            )
            calendar_path = (
                inputs["official_foundation_root"]
                / "normalized"
                / "trading_calendar.csv"
            )
            calendar_rows = list(
                csv.DictReader(calendar_path.read_text(encoding="utf-8").splitlines())
            )
            outside_row = dict(calendar_rows[0])
            outside_row["trade_date"] = "2026-08-10"
            calendar_rows.append(outside_row)
            _write_csv(calendar_path, tuple(calendar_rows[0]), calendar_rows)
            _refresh_calendar_receipts(inputs)
            _write_full_factor_contract(inputs, ex_date="2026-08-10")
            _write_full_benchmark_contract(inputs)

            report = _build_data_foundation_packet_unchecked(
                **inputs,
                project_root=ROOT,
                output_root=root / "output",
                outcome_session_policy_path=AUTHORITATIVE_POLICY,
            )
            gate = next(
                item
                for item in report["gates"]
                if item["gate"] == "PRICE_CORPORATE_ACTION_QA"
            )
            self.assertNotEqual(gate["status"], "BLOCKED")
            self.assertEqual(
                gate["details"]["checks"]["affected_eod_coverage"], "PASS"
            )
            self.assertEqual(
                gate["details"]["metrics"]["out_of_window_action_rows"], 1
            )
            self.assertEqual(
                gate["details"]["metrics"]["affected_eod_rows_joined"], 0
            )

    def test_ca_action_eod_state_must_match_effective_status_interval(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = _component_roots(
                root / "inputs",
                classification="RECORDED_AUTHORIZED_FIXTURE",
                rights_status="FIXTURE_ONLY",
            )
            _write_full_factor_contract(inputs)
            _write_full_benchmark_contract(inputs)
            eod_path = (
                inputs["official_eod_root"]
                / "normalized"
                / "official_daily_eod.csv"
            )
            eod_rows = list(
                csv.DictReader(eod_path.read_text(encoding="utf-8").splitlines())
            )
            eod_rows[0]["trading_state"] = "SUSPENDED"
            _write_csv(eod_path, tuple(eod_rows[0]), eod_rows)
            _refresh_eod_normalized_receipt(inputs)

            report = _build_data_foundation_packet_unchecked(
                **inputs,
                project_root=ROOT,
                output_root=root / "output",
                outcome_session_policy_path=AUTHORITATIVE_POLICY,
            )
            gate = next(
                item
                for item in report["gates"]
                if item["gate"] == "PRICE_CORPORATE_ACTION_QA"
            )
            self.assertEqual(gate["status"], "BLOCKED")
            self.assertIn(
                "CA_FACTOR_ROW_0_EOD_STATUS_SESSION_CONFLICT", gate["errors"]
            )
            self.assertEqual(
                gate["details"]["checks"]["status_session_integration"],
                "BLOCKED",
            )

    def test_ca_treatment_must_not_be_applied_to_benchmark_series(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = _component_roots(
                root / "inputs",
                classification="RECORDED_AUTHORIZED_FIXTURE",
                rights_status="FIXTURE_ONLY",
            )
            _write_full_factor_contract(inputs)
            _write_full_benchmark_contract(inputs)
            benchmark_path = (
                inputs["benchmark_root"]
                / "normalized"
                / "benchmark_history.csv"
            )
            rows = list(
                csv.DictReader(
                    benchmark_path.read_text(encoding="utf-8").splitlines()
                )
            )
            rows[0]["corporate_action_multiplier"] = "0.95"
            _write_csv(benchmark_path, tuple(rows[0]), rows)

            report = _build_data_foundation_packet_unchecked(
                **inputs,
                project_root=ROOT,
                output_root=root / "output",
                outcome_session_policy_path=AUTHORITATIVE_POLICY,
            )
            gate = next(
                item
                for item in report["gates"]
                if item["gate"] == "PRICE_CORPORATE_ACTION_QA"
            )
            self.assertEqual(gate["status"], "BLOCKED")
            self.assertIn(
                "BENCHMARK_ROW_0_CORPORATE_ACTION_TREATMENT_FORBIDDEN",
                gate["errors"],
            )
            self.assertEqual(
                gate["details"]["checks"]["benchmark_treatment_separation"],
                "BLOCKED",
            )

    def test_ca_factor_ticker_and_isin_must_match_effective_official_identity(self) -> None:
        for field, value, expected_error in (
            (
                "ticker",
                "WRONG",
                "CA_FACTOR_ROW_0_OFFICIAL_IDENTITY_TICKER_MISMATCH",
            ),
            (
                "isin",
                "KW9999999999",
                "CA_FACTOR_ROW_0_OFFICIAL_IDENTITY_ISIN_MISMATCH",
            ),
        ):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                inputs = _component_roots(
                    root / "inputs",
                    classification="RECORDED_AUTHORIZED_FIXTURE",
                    rights_status="FIXTURE_ONLY",
                )
                _write_full_factor_contract(inputs)
                _write_full_benchmark_contract(inputs)
                factor_path = (
                    inputs["ca_enrichment_root"]
                    / "normalized"
                    / "corporate_action_factor_ledger.csv"
                )
                rows = list(
                    csv.DictReader(
                        factor_path.read_text(encoding="utf-8").splitlines()
                    )
                )
                rows[0][field] = value
                _write_csv(factor_path, tuple(rows[0]), rows)

                report = _build_data_foundation_packet_unchecked(
                    **inputs,
                    project_root=ROOT,
                    output_root=root / "output",
                    outcome_session_policy_path=AUTHORITATIVE_POLICY,
                )
                gate = next(
                    item
                    for item in report["gates"]
                    if item["gate"] == "PRICE_CORPORATE_ACTION_QA"
                )
                self.assertEqual(gate["status"], "BLOCKED")
                self.assertIn(expected_error, gate["errors"])

    def test_ca_policy_row_must_link_to_the_same_factor_identity_and_date(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = _component_roots(
                root / "inputs",
                classification="RECORDED_AUTHORIZED_FIXTURE",
                rights_status="FIXTURE_ONLY",
            )
            _write_full_factor_contract(inputs)
            _write_full_benchmark_contract(inputs)
            policy_path = (
                inputs["ca_enrichment_root"]
                / "normalized"
                / "corporate_action_return_policy_queue.csv"
            )
            _write_csv(
                policy_path,
                (
                    "action_id",
                    "security_code",
                    "ticker",
                    "action_type",
                    "ex_date",
                    "return_engine_treatment",
                    "required_policy",
                    "factor_status",
                    "review_status",
                ),
                [
                    {
                        "action_id": "cash-1",
                        "security_code": "999",
                        "ticker": "TEST",
                        "action_type": "CASH_DIVIDEND_NORMAL",
                        "ex_date": "2026-08-09",
                        "return_engine_treatment": "BLOCKED_POLICY_REVIEW",
                        "required_policy": "ACTION_SPECIFIC_RETURN_POLICY",
                        "factor_status": "official",
                        "review_status": "PENDING",
                    }
                ],
            )
            report = _build_data_foundation_packet_unchecked(
                **inputs,
                project_root=ROOT,
                output_root=root / "output",
                outcome_session_policy_path=AUTHORITATIVE_POLICY,
            )
            gate = next(
                item
                for item in report["gates"]
                if item["gate"] == "PRICE_CORPORATE_ACTION_QA"
            )
            self.assertEqual(gate["status"], "BLOCKED")
            self.assertIn(
                "CA_POLICY_ROW_0_FACTOR_SECURITY_CODE_MISMATCH", gate["errors"]
            )
            self.assertEqual(
                gate["details"]["checks"]["policy_factor_action_link"],
                "BLOCKED",
            )

    def test_print_helper_reports_gate_errors_without_input_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report, output, _ = self._build(Path(directory))
            stream = StringIO()
            loaded = print_data_foundation_gate_report(
                output / "reports" / "data_foundation_gate_report.json",
                stream=stream,
            )
            self.assertEqual(loaded, report)
            self.assertIn("CLAIM_BOUNDARIES: PARTIAL", stream.getvalue())
            self.assertNotIn(directory, stream.getvalue())

    def test_gate_report_validator_rejects_shape_and_status_forgery(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report, _, _ = self._build(Path(directory))
            missing_contract = json.loads(json.dumps(report))
            missing_contract["gates"][0].pop("critical")
            with self.assertRaisesRegex(ValueError, "gate fields"):
                render_data_foundation_gate_report(missing_contract)

            forged_ready = json.loads(json.dumps(report))
            forged_ready["status"] = "DATA_FOUNDATION_READY_FOR_BASELINE_BACKTEST"
            forged_ready["evidence_classification"] = "PROVEN_REAL_EVIDENCE"
            forged_ready["rights_compatible"] = True
            with self.assertRaisesRegex(ValueError, "READY report invariants"):
                render_data_foundation_gate_report(forged_ready)

    def test_report_reader_rehashes_report_and_packet_from_final_manifest(self) -> None:
        for relative in (
            "reports/data_foundation_gate_report.json",
            "data_foundation_packet.json",
        ):
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as directory:
                _, output, _ = self._build(Path(directory))
                target = output / relative
                target.write_bytes(target.read_bytes() + b" ")
                with self.assertRaisesRegex(ValueError, "hash or size mismatch"):
                    read_data_foundation_gate_report(
                        output / "reports" / "data_foundation_gate_report.json"
                    )

    def test_report_reader_rejects_rehashed_but_malformed_gate_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _, output, _ = self._build(Path(directory))
            report_path = output / "reports" / "data_foundation_gate_report.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["gates"][0].pop("critical")
            report_bytes = _canonical_json(report)
            report_path.write_bytes(report_bytes)
            manifest_path = output / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            receipt = next(
                item
                for item in manifest["artifacts"]
                if item["path"] == "reports/data_foundation_gate_report.json"
            )
            receipt["sha256"] = hashlib.sha256(report_bytes).hexdigest()
            receipt["size_bytes"] = len(report_bytes)
            _write_json(manifest_path, manifest)
            with self.assertRaisesRegex(ValueError, "gate fields"):
                read_data_foundation_gate_report(report_path)

    def test_read_and_print_reject_self_hashed_forged_ready_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _, output, _ = self._build(Path(directory))
            report_path = output / "reports" / "data_foundation_gate_report.json"
            packet_path = output / "data_foundation_packet.json"
            manifest_path = output / "manifest.json"

            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["status"] = "DATA_FOUNDATION_READY_FOR_BASELINE_BACKTEST"
            report["evidence_classification"] = "PROVEN_REAL_EVIDENCE"
            report["rights_compatible"] = True
            for gate in report["gates"]:
                gate["status"] = "PASS"
                gate["evidence_classification"] = "PROVEN_REAL_EVIDENCE"
                gate["rights_compatible"] = True
                gate["errors"] = []
                gate["details"]["checks"] = {
                    key: "PASS" for key in gate["details"]["checks"]
                }
            report_bytes = _canonical_json(report)
            report_path.write_bytes(report_bytes)

            packet = json.loads(packet_path.read_text(encoding="utf-8"))
            packet["status"] = "DATA_FOUNDATION_READY_FOR_BASELINE_BACKTEST"
            packet["evidence_classification"] = "PROVEN_REAL_EVIDENCE"
            packet["rights_compatible"] = True
            packet["outcome_session_policy_status"] = "FROZEN"
            for component in packet["components"]:
                component["evidence_classification"] = "PROVEN_REAL_EVIDENCE"
                component["rights_compatible"] = True
                component["rights_statuses"] = ["RESEARCH_USE_AUTHORIZED"]
                component["structural_errors"] = []
                component["limitations"] = []
            packet_bytes = _canonical_json(packet)
            packet_path.write_bytes(packet_bytes)

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            forged = {
                "data_foundation_packet.json": packet_bytes,
                "reports/data_foundation_gate_report.json": report_bytes,
            }
            for receipt in manifest["artifacts"]:
                content = forged[receipt["path"]]
                receipt["sha256"] = hashlib.sha256(content).hexdigest()
                receipt["size_bytes"] = len(content)
                receipt["evidence_classification"] = "PROVEN_REAL_EVIDENCE"
            _write_json(manifest_path, manifest)

            with self.assertRaisesRegex(
                ValueError,
                "READY_FINAL_AUTHORITY_RECEIPT_REQUIRED",
            ):
                read_data_foundation_gate_report(report_path)
            with self.assertRaisesRegex(
                ValueError,
                "READY_FINAL_AUTHORITY_RECEIPT_REQUIRED",
            ):
                print_data_foundation_gate_report(report_path, stream=StringIO())

    def test_secret_guard_rejects_curated_non_repository_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = _component_roots(root / "inputs")
            project_root = root / "project"
            project_root.mkdir()
            (project_root / "README.md").write_text("curated subset\n", encoding="utf-8")
            report = _build_data_foundation_packet_unchecked(
                **inputs,
                project_root=project_root,
                output_root=root / "output",
                outcome_session_policy_path=_policy(root / "policy.json"),
            )
            secret_gate = next(
                gate for gate in report["gates"] if gate["gate"] == "RUNTIME_SECRET_GUARD"
            )
            self.assertEqual(secret_gate["status"], "BLOCKED")
            self.assertEqual(secret_gate["details"]["metrics"]["finding_count"], 1)
            self.assertTrue(
                any(
                    "PROJECT_ROOT_NOT_KU_BO_GIT_REPOSITORY" in error
                    for error in secret_gate["errors"]
                )
            )

    def test_secret_guard_blocks_any_tracked_runtime_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = _guard_git_repository(Path(directory))
            runtime_path = root / "runtime" / "private.env"
            runtime_path.parent.mkdir()
            runtime_path.write_text("fixture-only-placeholder\n", encoding="utf-8")
            _git(root, "add", "-f", "runtime/private.env")
            _git(root, "commit", "-q", "-m", "tracked runtime fixture")

            status, errors, _, _ = _repository_secret_scan(root)
            self.assertEqual(status, "BLOCKED")
            self.assertTrue(
                any("TRACKED_RUNTIME_PATH_FORBIDDEN" in error for error in errors)
            )

    def test_secret_guard_scans_head_blob_when_dirty_worktree_is_sanitized(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = _guard_git_repository(Path(directory))
            secret_value = "acceptance-repro-credential-" + "A" * 32
            tracked = root / "tracked.env"
            tracked.write_text(
                f"BROKER_API_KEY={secret_value}\n",
                encoding="utf-8",
            )
            _git(root, "add", "tracked.env")
            _git(root, "commit", "-q", "-m", "adversarial committed blob")
            tracked.write_text("SAFE_VALUE=sanitized\n", encoding="utf-8")

            status, errors, scanned, head_sha = _repository_secret_scan(root)

            self.assertEqual(status, "BLOCKED")
            self.assertGreater(scanned, 0)
            self.assertRegex(head_sha, r"^[0-9a-f]{40,64}$")
            self.assertTrue(
                any(
                    error
                    == "HEAD:tracked.env:1:CREDENTIAL_ENVIRONMENT_ASSIGNMENT"
                    for error in errors
                )
            )
            self.assertNotIn(secret_value, "\n".join(errors))

    def test_secret_guard_scans_staged_blob_when_dirty_worktree_is_sanitized(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = _guard_git_repository(Path(directory))
            secret_value = "queued-credential-" + "B" * 32
            tracked = root / "queued.env"
            tracked.write_text(
                f"BROKER_API_KEY={secret_value}\n",
                encoding="utf-8",
            )
            _git(root, "add", "queued.env")
            tracked.write_text("SAFE_VALUE=sanitized\n", encoding="utf-8")

            status, errors, scanned, head_sha = _repository_secret_scan(root)

            self.assertEqual(status, "BLOCKED")
            self.assertGreater(scanned, 0)
            self.assertRegex(head_sha, r"^[0-9a-f]{40,64}$")
            self.assertTrue(
                any(
                    error
                    == "INDEX:queued.env:1:CREDENTIAL_ENVIRONMENT_ASSIGNMENT"
                    for error in errors
                )
            )
            self.assertNotIn(secret_value, "\n".join(errors))

    def test_canonical_outputs_are_location_independent_and_timestamp_free(self) -> None:
        with tempfile.TemporaryDirectory() as left_directory, tempfile.TemporaryDirectory() as right_directory:
            _, left_output, _ = self._build(Path(left_directory))
            _, right_output, _ = self._build(Path(right_directory))
            for relative in (
                "data_foundation_packet.json",
                "reports/data_foundation_gate_report.json",
                "manifest.json",
            ):
                left = (left_output / relative).read_bytes()
                right = (right_output / relative).read_bytes()
                self.assertEqual(left, right)
                self.assertNotIn(b"observed_at", left)
                self.assertNotIn(b"imported_at", left)


if __name__ == "__main__":
    unittest.main()
