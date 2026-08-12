from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any


def _command(
    executable: str,
    project_root: Path,
    arguments: list[str],
    *,
    expected_exit: int,
) -> dict[str, Any]:
    completed = subprocess.run(
        [executable, "--project-root", str(project_root), *arguments],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if completed.returncode != expected_exit:
        raise RuntimeError(
            f"installed command {' '.join(arguments[:1])} returned "
            f"{completed.returncode}, expected {expected_exit}: {completed.stderr.strip()}"
        )
    try:
        report = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"installed command {' '.join(arguments[:1])} did not emit JSON"
        ) from exc
    if not isinstance(report, dict):
        raise RuntimeError("installed command report must be a JSON object")
    return report


def _expect(report: dict[str, Any], field: str, expected: object) -> None:
    actual = report.get(field)
    if actual != expected:
        raise RuntimeError(f"expected {field}={expected!r}, received {actual!r}")


def _rendered_command(
    executable: str,
    project_root: Path,
    arguments: list[str],
    *,
    expected_exit: int,
) -> str:
    completed = subprocess.run(
        [executable, "--project-root", str(project_root), *arguments],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if completed.returncode != expected_exit or not completed.stdout.strip():
        raise RuntimeError(
            f"installed render command returned {completed.returncode}, expected "
            f"{expected_exit}: {completed.stderr.strip()}"
        )
    return completed.stdout


def _manifest_sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Exercise installed KU-BO Data Foundation CLI handlers with fixtures"
    )
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    args = parser.parse_args(argv)

    project_root = args.project_root.resolve()
    work_root = args.work_root.resolve()
    if work_root.exists() and any(work_root.iterdir()):
        raise ValueError("installed CLI check requires an empty work root")
    work_root.mkdir(parents=True, exist_ok=True)
    installed_name = (
        "kubo-data-foundation.exe"
        if sys.platform == "win32"
        else "kubo-data-foundation"
    )
    # Entry-point scripts are siblings of the invoked virtual-environment
    # interpreter. Resolving the interpreter symlink would incorrectly jump
    # to the base interpreter and lose the installed wheel's scripts.
    sibling_executable = Path(sys.executable).parent / installed_name
    executable = (
        str(sibling_executable)
        if sibling_executable.is_file()
        else shutil.which("kubo-data-foundation")
    )
    if executable is None:
        raise RuntimeError("installed kubo-data-foundation executable was not found")

    # Fixture builders live in the checkout, while every subprocess below loads
    # kubo from the force-reinstalled wheel.
    sys.path.insert(0, str(project_root))
    import kubo

    installed_package = Path(kubo.__file__).resolve()
    if project_root == installed_package or project_root in installed_package.parents:
        raise RuntimeError("installed CLI check resolved kubo from the checkout")
    from kubo.benchmark_workspace import load_official_calendar_receipt
    from tests.benchmark_fixture_helpers import accept_fixture_manifest
    from tests.foundation_fixture_helpers import build_official_foundation_output
    from tests.official_eod_fixture_helpers import add_provider, build_eod_upstreams
    from tests.test_data_foundation_reconciliation import _component_roots
    from tests.test_status_history_import import StatusHistoryImportTests

    report = _command(
        executable,
        project_root,
        ["validate-tri-security-pilot"],
        expected_exit=0,
    )
    _expect(report, "status", "PASS")
    _expect(report, "batch_size", 3)
    _expect(report, "security_count", 9)

    tri_workspace = work_root / "tri-security-workspace"
    report = _command(
        executable,
        project_root,
        [
            "prepare-tri-security-batch",
            "--output-root",
            str(tri_workspace),
            "--batch-id",
            "tri-001-kfh-ship-aznoula",
            "--run-id",
            "installed-tri-security-check",
            "--window-from",
            "2026-08-02",
            "--window-to",
            "2026-08-12",
            "--prepared-by",
            "installed-wheel-check",
        ],
        expected_exit=0,
    )
    _expect(report, "status", "PASS")
    _expect(report, "batch_size", 3)
    scoped_report = _command(
        executable,
        project_root,
        [
            "--pilot-config-dir",
            str(tri_workspace / "scoped_config"),
            "--expected-pilot-config-manifest-sha256",
            report["scoped_config_manifest_sha256"],
            "validate-pilot-config",
        ],
        expected_exit=0,
    )
    _expect(scoped_report["identity_seed"], "security_count", 3)

    run_key = b"installed-run-receipt-key-material-32-bytes"
    stage_key = b"installed-stage-binding-key-material-32b"
    os.environ["KUBO_TRI_RUN_HMAC_KEY"] = "hex:" + run_key.hex()
    os.environ["KUBO_TRI_RUN_HMAC_KEY_ID"] = "installed-run-key-v1"
    os.environ["KUBO_TRI_STAGE_HMAC_KEY"] = "hex:" + stage_key.hex()
    os.environ["KUBO_TRI_STAGE_HMAC_KEY_ID"] = "installed-stage-key-v1"
    run_receipt_root = work_root / "tri-run-receipt"
    receipt_issue = _command(
        executable,
        project_root,
        [
            "issue-tri-security-run-receipt",
            "--workspace-root",
            str(tri_workspace),
            "--output-root",
            str(run_receipt_root),
            "--expected-batch-plan-sha256",
            report["batch_plan_sha256"],
            "--expected-scoped-config-manifest-sha256",
            report["scoped_config_manifest_sha256"],
            "--receipt-id",
            "installed-receipt-v1",
            "--issuer-id",
            "installed-wheel-check",
            "--issued-at",
            "2026-08-12T12:00:00+03:00",
            "--expires-at",
            "2026-08-14T12:00:00+03:00",
        ],
        expected_exit=0,
    )
    _expect(receipt_issue, "status", "PASS")
    receipt_path = run_receipt_root / "tri_security_run_receipt.json"
    receipt_verify = _command(
        executable,
        project_root,
        [
            "verify-tri-security-run-receipt",
            "--receipt-path",
            str(receipt_path),
            "--workspace-root",
            str(tri_workspace),
            "--expected-batch-plan-sha256",
            report["batch_plan_sha256"],
            "--expected-scoped-config-manifest-sha256",
            report["scoped_config_manifest_sha256"],
            "--decision-at",
            "2026-08-13T09:00:00+03:00",
            "--expected-run-id",
            "installed-tri-security-check",
            "--expected-batch-id",
            "tri-001-kfh-ship-aznoula",
        ],
        expected_exit=0,
    )
    _expect(receipt_verify, "status", "PASS")
    tri_price_workspace = work_root / "tri-price-workspace"
    report = _command(
        executable,
        project_root,
        [
            "--pilot-config-dir",
            str(tri_workspace / "scoped_config"),
            "--expected-pilot-config-manifest-sha256",
            report["scoped_config_manifest_sha256"],
            "prepare-price-collection",
            "--output-root",
            str(tri_price_workspace),
            "--downloaded-by",
            "installed-wheel-check",
        ],
        expected_exit=0,
    )
    _expect(report, "status", "PASS")
    _expect(report, "symbol_count", 3)

    status_fixture_root = work_root / "status-history-fixture"
    status_fixture_root.mkdir()
    status_upstream, status_workspace = StatusHistoryImportTests()._workspace(
        status_fixture_root
    )
    status_output = work_root / "status-history-output"
    report = _command(
        executable,
        project_root,
        [
            "import-status-history",
            "--status-corporate-root",
            str(status_upstream),
            "--workspace",
            str(status_workspace),
            "--output-root",
            str(status_output),
        ],
        expected_exit=0,
    )
    _expect(report, "status", "HISTORICAL_STATUS_INTERVALS_READY")
    _expect(report, "security_count", 5)
    _expect(report, "notice_count", 1)
    _expect(report, "interval_count", 6)
    synthetic_stage = work_root / "receipt-contract-stage"
    (synthetic_stage / "reports").mkdir(parents=True)
    synthetic_content = b'{"contract":"standalone-stage-integrity-only"}\n'
    synthetic_path = synthetic_stage / "reports" / "contract.json"
    synthetic_path.write_bytes(synthetic_content)
    import hashlib

    synthetic_manifest = {
        "schema_version": "3.0",
        "artifacts": [
            {
                "path": "reports/contract.json",
                "sha256": hashlib.sha256(synthetic_content).hexdigest(),
                "size_bytes": len(synthetic_content),
            }
        ],
    }
    (synthetic_stage / "manifest.json").write_bytes(
        (
            json.dumps(
                synthetic_manifest,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    )
    status_binding_root = work_root / "receipt-contract-binding"
    binding_issue = _command(
        executable,
        project_root,
        [
            "issue-tri-security-stage-binding",
            "--receipt-path",
            str(receipt_path),
            "--workspace-root",
            str(tri_workspace),
            "--stage-root",
            str(synthetic_stage),
            "--output-root",
            str(status_binding_root),
            "--expected-batch-plan-sha256",
            receipt_verify["batch_plan_sha256"],
            "--expected-scoped-config-manifest-sha256",
            receipt_verify["scoped_config_manifest_sha256"],
            "--expected-stage-manifest-sha256",
            _manifest_sha256(synthetic_stage / "manifest.json"),
            "--expected-run-id",
            "installed-tri-security-check",
            "--expected-batch-id",
            "tri-001-kfh-ship-aznoula",
            "--binding-id",
            "installed-status-binding-v1",
            "--stage-id",
            "OFFICIAL_FOUNDATION",
            "--bound-at",
            "2026-08-13T09:05:00+03:00",
        ],
        expected_exit=0,
    )
    _expect(binding_issue, "status", "PASS")
    binding_verify = _command(
        executable,
        project_root,
        [
            "verify-tri-security-stage-binding",
            "--binding-path",
            str(status_binding_root / "tri_security_stage_binding.json"),
            "--receipt-path",
            str(receipt_path),
            "--workspace-root",
            str(tri_workspace),
            "--stage-root",
            str(synthetic_stage),
            "--expected-batch-plan-sha256",
            receipt_verify["batch_plan_sha256"],
            "--expected-scoped-config-manifest-sha256",
            receipt_verify["scoped_config_manifest_sha256"],
            "--expected-stage-manifest-sha256",
            _manifest_sha256(synthetic_stage / "manifest.json"),
            "--decision-at",
            "2026-08-13T09:10:00+03:00",
            "--expected-stage-id",
            "OFFICIAL_FOUNDATION",
            "--expected-run-id",
            "installed-tri-security-check",
            "--expected-batch-id",
            "tri-001-kfh-ship-aznoula",
        ],
        expected_exit=0,
    )
    _expect(binding_verify, "status", "PASS")

    benchmark_fixture_root = work_root / "benchmark-fixture"
    benchmark_fixture_root.mkdir()
    official = build_official_foundation_output(benchmark_fixture_root)
    benchmark_workspace = work_root / "benchmark-workspace"
    report = _command(
        executable,
        project_root,
        [
            "prepare-benchmark-history",
            "--official-foundation-root",
            str(official),
            "--output-root",
            str(benchmark_workspace),
            "--run-id",
            "installed-benchmark-check",
            "--window-from",
            "2026-08-03",
            "--window-to",
            "2026-08-09",
            "--prepared-by",
            "installed-wheel-check",
        ],
        expected_exit=0,
    )
    _expect(report, "status", "PASS")
    receipt = load_official_calendar_receipt(official)
    trading_dates = tuple(
        day.isoformat()
        for day in sorted(receipt.trading_dates)
        if "2026-08-03" <= day.isoformat() <= "2026-08-09"
    )
    accept_fixture_manifest(benchmark_workspace, trading_dates)
    benchmark_output = work_root / "benchmark-output"
    report = _command(
        executable,
        project_root,
        [
            "import-benchmark-history",
            "--official-foundation-root",
            str(official),
            "--workspace",
            str(benchmark_workspace),
            "--output-root",
            str(benchmark_output),
            "--imported-at",
            "2026-08-10T10:00:00+03:00",
        ],
        expected_exit=1,
    )
    _expect(report, "status", "PARTIAL")
    _expect(report, "evidence_classification", "RECORDED_AUTHORIZED_FIXTURE")

    eod_fixture_root = work_root / "eod-fixture"
    eod_fixture_root.mkdir()
    eod_official, status_history = build_eod_upstreams(eod_fixture_root)
    eod_workspace = work_root / "eod-workspace"
    report = _command(
        executable,
        project_root,
        [
            "prepare-official-eod",
            "--official-foundation-root",
            str(eod_official),
            "--status-history-root",
            str(status_history),
            "--output-root",
            str(eod_workspace),
            "--run-id",
            "installed-eod-check",
            "--window-from",
            "2026-08-08",
            "--window-to",
            "2026-08-09",
            "--prepared-by",
            "installed-wheel-check",
        ],
        expected_exit=0,
    )
    _expect(report, "status", "PASS")
    add_provider(eod_workspace)
    eod_output = work_root / "eod-output"
    report = _command(
        executable,
        project_root,
        [
            "import-official-eod",
            "--workspace",
            str(eod_workspace),
            "--official-foundation-root",
            str(eod_official),
            "--status-history-root",
            str(status_history),
            "--output-root",
            str(eod_output),
            "--run-id",
            "installed-eod-check",
            "--imported-at",
            "2026-08-09T18:00:00+03:00",
        ],
        expected_exit=1,
    )
    _expect(report, "status", "PARTIAL")
    report = _command(
        executable,
        project_root,
        [
            "validate-official-eod",
            "--official-eod-root",
            str(eod_output),
            "--official-foundation-root",
            str(eod_official),
            "--status-history-root",
            str(status_history),
        ],
        expected_exit=1,
    )
    _expect(report, "validation_status", "PASS")

    component_root = work_root / "final-components"
    component_root.mkdir()
    roots = _component_roots(
        component_root,
        classification="RECORDED_AUTHORIZED_FIXTURE",
        rights_status="FIXTURE_ONLY",
    )
    packet_output = work_root / "final-packet"
    build_arguments = ["build-data-foundation-packet"]
    for option, key in (
        ("--official-foundation-root", "official_foundation_root"),
        ("--status-history-root", "status_history_root"),
        ("--ca-enrichment-root", "ca_enrichment_root"),
        ("--research-price-history-root", "research_price_history_root"),
        ("--benchmark-root", "benchmark_root"),
        ("--official-eod-root", "official_eod_root"),
    ):
        build_arguments.extend([option, str(roots[key])])
    build_arguments.extend(["--output-root", str(packet_output)])
    report = _command(
        executable,
        project_root,
        build_arguments,
        expected_exit=1,
    )
    if report.get("status") not in {"DATA_FOUNDATION_PARTIAL", "DATA_FOUNDATION_BLOCKED"}:
        raise RuntimeError("fixture final packet unexpectedly reached readiness")
    printed = _rendered_command(
        executable,
        project_root,
        [
            "print-data-foundation-gate-report",
            "--path",
            str(packet_output / "reports" / "data_foundation_gate_report.json"),
        ],
        expected_exit=1,
    )
    if not printed.startswith(f"{report['status']} | evidence="):
        raise RuntimeError("printed final gate report did not preserve the saved status")

    print(
        json.dumps(
            {
                "status": "PASS",
                "installed_handlers_exercised": [
                    "validate-tri-security-pilot",
                    "prepare-tri-security-batch",
                    "issue-tri-security-run-receipt",
                    "verify-tri-security-run-receipt",
                    "issue-tri-security-stage-binding",
                    "verify-tri-security-stage-binding",
                    "validate-pilot-config-scoped",
                    "prepare-price-collection-scoped",
                    "import-status-history",
                    "prepare-benchmark-history",
                    "import-benchmark-history",
                    "prepare-official-eod",
                    "import-official-eod",
                    "validate-official-eod",
                    "build-data-foundation-packet",
                    "print-data-foundation-gate-report",
                ],
                "installed_package": str(installed_package),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
