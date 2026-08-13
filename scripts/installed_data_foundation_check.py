from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import stat
import subprocess
import sys
from typing import Any, Mapping, Sequence


RUN_ID = "installed-tri-security-check"
BATCH_ID = "tri-001-kfh-ship-aznoula"
DECISION_AT = "2026-08-13T10:00:00+03:00"
BOUND_AT = "2026-08-13T08:00:00+03:00"
SEMANTIC_ISSUED_AT = "2026-08-13T08:30:00+03:00"
OBSERVED_AT = "2026-08-13T09:30:00+03:00"
IMPORTED_AT = "2026-08-13T09:30:00+03:00"

BOUNDARY_STAGE = {
    "import_user_price_exports": "RESEARCH_PRICE_HISTORY",
    "import_official_foundation": "OFFICIAL_FOUNDATION",
    "import_status_corporate": "STATUS_CORPORATE",
    "import_ca_enrichment": "CA_ENRICHMENT",
    "import_status_history": "STATUS_HISTORY",
    "import_benchmark_history": "BENCHMARK_HISTORY",
    "import_official_eod": "OFFICIAL_EOD",
    "build_data_foundation_packet": "FINAL_DATA_FOUNDATION_RECONCILIATION",
}


def _run(arguments: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(arguments),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
    )


def _command(
    executable: str,
    project_root: Path,
    arguments: list[str],
    *,
    expected_exit: int,
) -> dict[str, Any]:
    completed = _run(
        [executable, "--project-root", str(project_root), *arguments]
    )
    if completed.returncode != expected_exit:
        raise RuntimeError(
            f"installed command {arguments[0]} returned {completed.returncode}, "
            f"expected {expected_exit}: {completed.stderr.strip()}"
        )
    try:
        report = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"installed command {arguments[0]} did not emit JSON: "
            f"{completed.stdout.strip()} {completed.stderr.strip()}"
        ) from exc
    if not isinstance(report, dict):
        raise RuntimeError("installed command report must be a JSON object")
    return report


def _rendered_command(
    executable: str,
    project_root: Path,
    arguments: list[str],
    *,
    expected_exit: int,
) -> str:
    completed = _run(
        [executable, "--project-root", str(project_root), *arguments]
    )
    if completed.returncode != expected_exit or not completed.stdout.strip():
        raise RuntimeError(
            f"installed render command returned {completed.returncode}, expected "
            f"{expected_exit}: {completed.stderr.strip()}"
        )
    return completed.stdout


def _expect(report: Mapping[str, Any], field: str, expected: object) -> None:
    actual = report.get(field)
    if actual != expected:
        raise RuntimeError(f"expected {field}={expected!r}, received {actual!r}")


def _expect_one_of(
    report: Mapping[str, Any],
    field: str,
    expected: set[str],
) -> None:
    actual = report.get(field)
    if actual not in expected:
        raise RuntimeError(
            f"expected {field} in {sorted(expected)!r}, received {actual!r}"
        )


def _clean_project_copy(source: Path, destination: Path) -> Path:
    completed = _run(
        [
            "git",
            "clone",
            "--quiet",
            "--no-hardlinks",
            "--no-local",
            str(source),
            str(destination),
        ]
    )
    if completed.returncode != 0:
        raise RuntimeError(f"clean project clone failed: {completed.stderr.strip()}")
    status_result = _run(
        ["git", "-C", str(destination), "status", "--porcelain=v1"]
    )
    if status_result.returncode != 0 or status_result.stdout:
        raise RuntimeError("installed check project clone is not a clean Git worktree")
    for path in destination.rglob("*"):
        if path.is_symlink():
            raise RuntimeError(
                f"installed check project clone contains a symlink: "
                f"{path.relative_to(destination)}"
            )
        metadata = os.lstat(path)
        if stat.S_ISREG(metadata.st_mode) and metadata.st_nlink != 1:
            raise RuntimeError(
                f"installed check project clone contains a hard-linked file: "
                f"{path.relative_to(destination)}"
            )
    return destination


def _manifest_workspace(root: Path) -> str:
    """Make the real prepared workspace itself the immutable v1 stage root."""

    from kubo.hashing import canonical_json_bytes, sha256_bytes

    manifest_path = root / "manifest.json"
    if manifest_path.exists() or manifest_path.is_symlink():
        raise RuntimeError(f"prepared workspace already has root manifest: {root}")
    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise RuntimeError(f"prepared workspace contains a symlink: {path}")
        if not path.is_file():
            continue
        content = path.read_bytes()
        rows.append(
            {
                "path": path.relative_to(root).as_posix(),
                "sha256": sha256_bytes(content),
                "size_bytes": len(content),
            }
        )
    if not rows:
        raise RuntimeError(f"prepared workspace contains no files: {root}")
    content = canonical_json_bytes(
        {"schema_version": "3.0", "artifacts": rows}
    )
    manifest_path.write_bytes(content)
    return sha256_bytes(content)


def _final_admission_workspace(
    root: Path,
    boundary_inputs: Mapping[str, Path],
) -> tuple[Path, str]:
    """Persist hash receipts for the actual final inputs in its admission workspace."""

    from kubo.foundation_io import safe_regular_file, snapshot_regular_tree
    from kubo.hashing import canonical_json_bytes, hash_json, sha256_bytes

    root.mkdir(parents=True, exist_ok=False)
    receipts: list[dict[str, Any]] = []
    for role, raw_path in boundary_inputs.items():
        path = Path(raw_path)
        if path.is_dir() and not path.is_symlink():
            inventory = snapshot_regular_tree(
                path,
                field=f"installed final boundary input {role}",
            ).inventory()
            receipts.append(
                {
                    "role": role,
                    "kind": "REGULAR_TREE",
                    "inventory_sha256": hash_json(inventory),
                    "file_count": len(inventory),
                }
            )
        else:
            content = safe_regular_file(
                path,
                field=f"installed final boundary input {role}",
            )
            receipts.append(
                {
                    "role": role,
                    "kind": "REGULAR_FILE",
                    "inventory_sha256": sha256_bytes(content),
                    "file_count": 1,
                }
            )
    receipt_path = root / "boundary_input_receipts.json"
    receipt_content = canonical_json_bytes(
        {
            "schema_version": "1.0",
            "boundary_id": "build_data_foundation_packet",
            "inputs": receipts,
            "claim_boundary": "INPUT_BYTE_RECEIPTS_NOT_MARKET_EVIDENCE",
        }
    )
    receipt_path.write_bytes(receipt_content)
    manifest_content = canonical_json_bytes(
        {
            "schema_version": "3.0",
            "artifacts": [
                {
                    "path": receipt_path.name,
                    "sha256": sha256_bytes(receipt_content),
                    "size_bytes": len(receipt_content),
                }
            ],
        }
    )
    (root / "manifest.json").write_bytes(manifest_content)
    return root, sha256_bytes(manifest_content)


def _accept_official_workspace(workspace: Path) -> None:
    from tests.test_official_foundation_import import ARTIFACT_CONTENT

    manifest_path = workspace / "manifests" / "official_foundation_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["identity_snapshot_effective_date"] = "2026-08-09"
    raw = workspace / "raw_exports" / "boursa"
    for row in manifest["artifacts"]:
        content = ARTIFACT_CONTENT[row["artifact_id"]]
        (raw / row["file_name"]).write_bytes(content)
        row.update(
            {
                "file_sha256": hashlib.sha256(content).hexdigest(),
                "observed_at": "2026-08-09T09:00:00+03:00",
                "captured_by": "installed-wheel-check",
                "review_status": "ACCEPTED",
                "review_notes": "installed recorded contract fixture",
            }
        )
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


def _accept_status_workspace(workspace: Path) -> None:
    from tests.test_status_corporate_import import (
        DELISTED_HTML,
        EMPTY_CORPORATE_ACTIONS_HTML,
        EMPTY_SUSPENDED_HTML,
    )

    manifest_path = workspace / "manifests" / "status_corporate_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["status_snapshot_effective_date"] = "2026-08-09"
    manifest["corporate_action_query"].update(
        {
            "filter_applied": True,
            "pages_declared": 1,
            "pages_received": 1,
            "result_count_declared": 0,
            "review_status": "ACCEPTED",
            "review_notes": "installed rendered zero-result fixture",
        }
    )
    contents = {
        "suspended_companies": EMPTY_SUSPENDED_HTML,
        "delisted_companies": DELISTED_HTML,
        "corporate_actions": EMPTY_CORPORATE_ACTIONS_HTML,
    }
    raw = workspace / "raw_exports" / "boursa"
    for row in manifest["artifacts"]:
        content = contents[row["artifact_id"]]
        (raw / row["file_name"]).write_bytes(content)
        row.update(
            {
                "file_sha256": hashlib.sha256(content).hexdigest(),
                "observed_at": "2026-08-09T10:00:00+03:00",
                "captured_by": "installed-wheel-check",
                "review_status": "ACCEPTED",
                "review_notes": "installed rendered contract fixture",
            }
        )
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


def _accept_status_history_workspace(workspace: Path) -> None:
    source_url = (
        "https://www.boursakuwait.com.kw/en/announcements/"
        "disclosures-and-announcements/historical-disclosures-and-announcements/"
    )
    manifest_path = workspace / "manifests" / "status_history_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for query in manifest["queries"]:
        content = (
            f"Rendered complete historical query for {query['ticker']}; zero results."
        ).encode("utf-8")
        (workspace / "raw_exports" / "queries" / query["raw_file_name"]).write_bytes(
            content
        )
        query.update(
            {
                "raw_sha256": hashlib.sha256(content).hexdigest(),
                "pages_declared": 1,
                "pages_received": 1,
                "result_count_declared": 0,
                "rows_normalized": 0,
                "zero_result": True,
                "observed_at": "2026-08-09T12:00:00+03:00",
                "captured_by": "installed-wheel-check",
                "review_status": "ACCEPTED",
                "review_notes": "installed complete zero-result fixture",
            }
        )
    for opening in manifest["opening_states"]:
        phrase = f"Opening status for {opening['ticker']} was trading"
        content = phrase.encode("utf-8")
        path = workspace / "raw_exports" / "opening_states" / opening["raw_file_name"]
        path.write_bytes(content)
        opening.update(
            {
                "status": "TRADING",
                "source_id": "boursa_historical_disclosures",
                "source_url": source_url,
                "raw_sha256": hashlib.sha256(content).hexdigest(),
                "evidence_excerpt": phrase,
                "observed_at": "2026-08-09T12:05:00+03:00",
                "captured_by": "installed-wheel-check",
                "review_status": "ACCEPTED",
                "review_notes": "installed opening-state fixture",
            }
        )
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


def _admission_options(
    *,
    admission_path: Path,
    receipt_path: Path,
    binding_path: Path,
    tri_workspace: Path,
    input_root: Path,
    batch_plan_sha256: str,
    scoped_manifest_sha256: str,
    stage_manifest_sha256: str,
    predecessors: Sequence[Path],
) -> list[str]:
    arguments = [
        "--admission-path", str(admission_path),
        "--receipt-path", str(receipt_path),
        "--stage-binding-path", str(binding_path),
        "--workspace-root", str(tri_workspace),
        "--input-root", str(input_root),
        "--expected-batch-plan-sha256", batch_plan_sha256,
        "--expected-scoped-config-manifest-sha256", scoped_manifest_sha256,
        "--expected-stage-manifest-sha256", stage_manifest_sha256,
        "--decision-at", DECISION_AT,
        "--expected-run-id", RUN_ID,
        "--expected-batch-id", BATCH_ID,
    ]
    for path in predecessors:
        arguments.extend(["--predecessor-admission", str(path)])
    return arguments


_SEMANTIC_KEY = b""


def _issue_and_run_boundary(
    *,
    executable: str,
    project_root: Path,
    work_root: Path,
    receipt_path: Path,
    tri_workspace: Path,
    batch_plan_sha256: str,
    scoped_manifest_sha256: str,
    boundary_id: str,
    input_root: Path,
    stage_manifest_sha256: str,
    boundary_inputs: Mapping[str, Path],
    predecessor_admissions: Sequence[Path],
    operation_arguments: Sequence[str],
    boundary_command: list[str],
    output_root: Path,
    expected_exit: int,
) -> tuple[dict[str, Any], Path]:
    stage_id = BOUNDARY_STAGE[boundary_id]
    authority_root = work_root / "boundary-authorities"
    authority_root.mkdir(exist_ok=True)
    binding_root = authority_root / f"{boundary_id}-stage-binding"
    binding_report = _command(
        executable,
        project_root,
        [
            "issue-tri-security-stage-binding",
            "--receipt-path", str(receipt_path),
            "--workspace-root", str(tri_workspace),
            "--stage-root", str(input_root),
            "--output-root", str(binding_root),
            "--expected-batch-plan-sha256", batch_plan_sha256,
            "--expected-scoped-config-manifest-sha256", scoped_manifest_sha256,
            "--expected-stage-manifest-sha256", stage_manifest_sha256,
            "--expected-run-id", RUN_ID,
            "--expected-batch-id", BATCH_ID,
            "--binding-id", f"installed-{boundary_id}-binding-v1",
            "--stage-id", stage_id,
            "--bound-at", BOUND_AT,
        ],
        expected_exit=0,
    )
    _expect(binding_report, "status", "PASS")
    binding_path = binding_root / "tri_security_stage_binding.json"

    semantic_root = authority_root / "semantic-admissions"
    semantic_root.mkdir(exist_ok=True)
    admission_path = semantic_root / f"{boundary_id}.json"
    semantic_arguments = [
        "issue-tri-security-semantic-admission",
        "--boundary-id", boundary_id,
        "--receipt-path", str(receipt_path),
        "--stage-binding-path", str(binding_path),
        "--workspace-root", str(tri_workspace),
        "--input-root", str(input_root),
        "--output-path", str(admission_path),
        "--expected-batch-plan-sha256", batch_plan_sha256,
        "--expected-scoped-config-manifest-sha256", scoped_manifest_sha256,
        "--expected-stage-manifest-sha256", stage_manifest_sha256,
        "--expected-run-id", RUN_ID,
        "--expected-batch-id", BATCH_ID,
        "--admission-id", f"installed-{boundary_id}-admission-v2",
        "--issued-at", SEMANTIC_ISSUED_AT,
        "--operation-decision-at", DECISION_AT,
        *operation_arguments,
    ]
    for role, path in boundary_inputs.items():
        semantic_arguments.extend(["--boundary-input", f"{role}={path}"])
    for path in predecessor_admissions:
        semantic_arguments.extend(["--predecessor-admission", str(path)])
    semantic_report = _command(
        executable,
        project_root,
        semantic_arguments,
        expected_exit=0,
    )
    _expect(semantic_report, "status", "PASS")

    report = _command(
        executable,
        project_root,
        [
            *boundary_command,
            *_admission_options(
                admission_path=admission_path,
                receipt_path=receipt_path,
                binding_path=binding_path,
                tri_workspace=tri_workspace,
                input_root=input_root,
                batch_plan_sha256=batch_plan_sha256,
                scoped_manifest_sha256=scoped_manifest_sha256,
                stage_manifest_sha256=stage_manifest_sha256,
                predecessors=predecessor_admissions,
            ),
        ],
        expected_exit=expected_exit,
    )
    sidecar = output_root / "tri_security_semantic_admission.json"
    lineage = output_root / "reports" / "tri_security_lineage.json"
    if not sidecar.is_file() or not lineage.is_file():
        raise RuntimeError(f"{boundary_id} did not publish semantic lineage")
    from kubo.tri_security_lineage import verify_boundary_lineage

    verified = verify_boundary_lineage(
        output_root,
        semantic_key=_SEMANTIC_KEY,
        semantic_key_id="installed-semantic-key-v1",
    )
    if verified.boundary_id != boundary_id or verified.stage_id != stage_id:
        raise RuntimeError(f"{boundary_id} published the wrong lineage identity")
    return report, sidecar


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Exercise the installed KU-BO wheel through the complete authenticated "
            "eight-boundary Data Foundation DAG"
        )
    )
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    args = parser.parse_args(argv)

    source_project = args.project_root.resolve()
    work_root = args.work_root.resolve()
    if work_root.exists() and any(work_root.iterdir()):
        raise ValueError("installed CLI check requires an empty work root")
    work_root.mkdir(parents=True, exist_ok=True)
    clean_project = _clean_project_copy(
        source_project,
        work_root / "clean-project",
    )

    installed_name = (
        "kubo-data-foundation.exe"
        if sys.platform == "win32"
        else "kubo-data-foundation"
    )
    sibling_executable = Path(sys.executable).parent / installed_name
    executable = (
        str(sibling_executable)
        if sibling_executable.is_file()
        else shutil.which("kubo-data-foundation")
    )
    if executable is None:
        raise RuntimeError("installed kubo-data-foundation executable was not found")

    # Fixture constants live in the checkout; kubo itself must resolve only
    # from the clean-installed wheel.
    sys.path.insert(0, str(source_project))
    import kubo

    installed_package = Path(kubo.__file__).resolve()
    if source_project == installed_package or source_project in installed_package.parents:
        raise RuntimeError("installed CLI check resolved kubo from the checkout")

    global _SEMANTIC_KEY
    run_key = secrets.token_bytes(32)
    stage_key = secrets.token_bytes(32)
    _SEMANTIC_KEY = secrets.token_bytes(32)
    os.environ.update(
        {
            "KUBO_TRI_RUN_HMAC_KEY": "hex:" + run_key.hex(),
            "KUBO_TRI_RUN_HMAC_KEY_ID": "installed-run-key-v1",
            "KUBO_TRI_STAGE_HMAC_KEY": "hex:" + stage_key.hex(),
            "KUBO_TRI_STAGE_HMAC_KEY_ID": "installed-stage-key-v1",
            "KUBO_TRI_SEMANTIC_HMAC_KEY": "hex:" + _SEMANTIC_KEY.hex(),
            "KUBO_TRI_SEMANTIC_HMAC_KEY_ID": "installed-semantic-key-v1",
        }
    )

    pilot_report = _command(
        executable,
        clean_project,
        ["validate-tri-security-pilot"],
        expected_exit=0,
    )
    _expect(pilot_report, "status", "PASS")

    tri_workspace = work_root / "tri-security-workspace"
    run = _command(
        executable,
        clean_project,
        [
            "prepare-tri-security-batch",
            "--output-root", str(tri_workspace),
            "--batch-id", BATCH_ID,
            "--run-id", RUN_ID,
            "--window-from", "2026-08-02",
            "--window-to", "2026-08-12",
            "--prepared-by", "installed-wheel-check",
        ],
        expected_exit=0,
    )
    _expect(run, "status", "PASS")
    batch_plan_sha256 = str(run["batch_plan_sha256"])
    scoped_manifest_sha256 = str(run["scoped_config_manifest_sha256"])

    receipt_root = work_root / "tri-run-receipt"
    receipt_issue = _command(
        executable,
        clean_project,
        [
            "issue-tri-security-run-receipt",
            "--workspace-root", str(tri_workspace),
            "--output-root", str(receipt_root),
            "--expected-batch-plan-sha256", batch_plan_sha256,
            "--expected-scoped-config-manifest-sha256", scoped_manifest_sha256,
            "--receipt-id", "installed-receipt-v1",
            "--issuer-id", "installed-wheel-check",
            "--issued-at", "2026-08-12T12:00:00+03:00",
            "--expires-at", "2026-08-14T12:00:00+03:00",
        ],
        expected_exit=0,
    )
    _expect(receipt_issue, "status", "PASS")
    receipt_path = receipt_root / "tri_security_run_receipt.json"

    config_dir = clean_project / "config"
    sidecars: dict[str, Path] = {}
    exercised: list[str] = []

    # Root boundary: official identity and calendar.
    official_workspace = work_root / "official-workspace"
    _command(
        executable,
        clean_project,
        [
            "prepare-official-foundation",
            "--output-root", str(official_workspace),
            "--run-id", RUN_ID,
            "--calendar-year", "2026",
            "--prepared-by", "installed-wheel-check",
        ],
        expected_exit=0,
    )
    _accept_official_workspace(official_workspace)
    official_manifest = _manifest_workspace(official_workspace)
    official_output = work_root / "official-output"
    report, sidecars["OFFICIAL_FOUNDATION"] = _issue_and_run_boundary(
        executable=executable,
        project_root=clean_project,
        work_root=work_root,
        receipt_path=receipt_path,
        tri_workspace=tri_workspace,
        batch_plan_sha256=batch_plan_sha256,
        scoped_manifest_sha256=scoped_manifest_sha256,
        boundary_id="import_official_foundation",
        input_root=official_workspace,
        stage_manifest_sha256=official_manifest,
        boundary_inputs={"config_dir": config_dir, "workspace": official_workspace},
        predecessor_admissions=(),
        operation_arguments=(),
        boundary_command=[
            "import-official-foundation",
            "--workspace", str(official_workspace),
            "--output-root", str(official_output),
        ],
        output_root=official_output,
        expected_exit=0,
    )
    _expect(report, "status", "CURRENT_IDENTITY_AND_CALENDAR_READY")
    exercised.append("import-official-foundation")

    # Root boundary: user-export research prices.
    price_workspace = work_root / "price-workspace"
    _command(
        executable,
        clean_project,
        [
            "prepare-price-collection",
            "--output-root", str(price_workspace),
            "--downloaded-by", "installed-wheel-check",
        ],
        expected_exit=0,
    )
    from tests.test_user_price_export import UserPriceExportTests

    UserPriceExportTests()._accept_exports(price_workspace)
    price_manifest = _manifest_workspace(price_workspace)
    price_input = price_workspace / "raw_exports" / "investing"
    price_output = work_root / "research-price-output"
    report, sidecars["RESEARCH_PRICE_HISTORY"] = _issue_and_run_boundary(
        executable=executable,
        project_root=clean_project,
        work_root=work_root,
        receipt_path=receipt_path,
        tri_workspace=tri_workspace,
        batch_plan_sha256=batch_plan_sha256,
        scoped_manifest_sha256=scoped_manifest_sha256,
        boundary_id="import_user_price_exports",
        input_root=price_workspace,
        stage_manifest_sha256=price_manifest,
        boundary_inputs={"config_dir": config_dir, "input_dir": price_input},
        predecessor_admissions=(),
        operation_arguments=("--operation-observed-at", OBSERVED_AT),
        boundary_command=[
            "import-user-price-exports",
            "--input-dir", str(price_input),
            "--output-root", str(price_output),
            "--observed-at", OBSERVED_AT,
        ],
        output_root=price_output,
        expected_exit=1,
    )
    _expect_one_of(report, "status", {"BLOCKED_OFFICIAL_IDENTITY", "PARTIAL"})
    exercised.append("import-user-price-exports")

    # Official foundation -> current status/corporate schedule.
    status_workspace = work_root / "status-corporate-workspace"
    _command(
        executable,
        clean_project,
        [
            "prepare-status-corporate",
            "--output-root", str(status_workspace),
            "--run-id", RUN_ID,
            "--action-window-from", "2026-01-01",
            "--action-window-to", "2026-12-31",
            "--prepared-by", "installed-wheel-check",
        ],
        expected_exit=0,
    )
    _accept_status_workspace(status_workspace)
    status_manifest = _manifest_workspace(status_workspace)
    status_output = work_root / "status-corporate-output"
    report, sidecars["STATUS_CORPORATE"] = _issue_and_run_boundary(
        executable=executable,
        project_root=clean_project,
        work_root=work_root,
        receipt_path=receipt_path,
        tri_workspace=tri_workspace,
        batch_plan_sha256=batch_plan_sha256,
        scoped_manifest_sha256=scoped_manifest_sha256,
        boundary_id="import_status_corporate",
        input_root=status_workspace,
        stage_manifest_sha256=status_manifest,
        boundary_inputs={
            "official_foundation_root": official_output,
            "workspace": status_workspace,
        },
        predecessor_admissions=(sidecars["OFFICIAL_FOUNDATION"],),
        operation_arguments=(),
        boundary_command=[
            "import-status-corporate",
            "--official-foundation-root", str(official_output),
            "--workspace", str(status_workspace),
            "--output-root", str(status_output),
        ],
        output_root=status_output,
        expected_exit=0,
    )
    _expect(report, "status", "CURRENT_STATUS_AND_CA_ZERO_RESULT_READY")
    exercised.append("import-status-corporate")

    # Status/corporate -> corporate-action enrichment (explicit zero result).
    ca_workspace = work_root / "ca-enrichment-workspace"
    _command(
        executable,
        clean_project,
        [
            "prepare-ca-enrichment",
            "--status-corporate-root", str(status_output),
            "--output-root", str(ca_workspace),
            "--run-id", RUN_ID,
            "--prepared-by", "installed-wheel-check",
        ],
        expected_exit=0,
    )
    ca_manifest = _manifest_workspace(ca_workspace)
    ca_output = work_root / "ca-enrichment-output"
    report, sidecars["CA_ENRICHMENT"] = _issue_and_run_boundary(
        executable=executable,
        project_root=clean_project,
        work_root=work_root,
        receipt_path=receipt_path,
        tri_workspace=tri_workspace,
        batch_plan_sha256=batch_plan_sha256,
        scoped_manifest_sha256=scoped_manifest_sha256,
        boundary_id="import_ca_enrichment",
        input_root=ca_workspace,
        stage_manifest_sha256=ca_manifest,
        boundary_inputs={
            "status_corporate_root": status_output,
            "workspace": ca_workspace,
        },
        predecessor_admissions=(sidecars["STATUS_CORPORATE"],),
        operation_arguments=(),
        boundary_command=[
            "import-ca-enrichment",
            "--status-corporate-root", str(status_output),
            "--workspace", str(ca_workspace),
            "--output-root", str(ca_output),
        ],
        output_root=ca_output,
        expected_exit=0,
    )
    _expect(report, "status", "CA_ENRICHMENT_ZERO_RESULT_READY")
    exercised.append("import-ca-enrichment")

    # Status/corporate -> complete historical zero-result queries.
    history_workspace = work_root / "status-history-workspace"
    _command(
        executable,
        clean_project,
        [
            "prepare-status-history",
            "--status-corporate-root", str(status_output),
            "--output-root", str(history_workspace),
            "--run-id", RUN_ID,
            "--history-window-from", "2026-01-01",
            "--history-window-to", "2026-08-09",
            "--prepared-by", "installed-wheel-check",
        ],
        expected_exit=0,
    )
    _accept_status_history_workspace(history_workspace)
    history_manifest = _manifest_workspace(history_workspace)
    history_output = work_root / "status-history-output"
    report, sidecars["STATUS_HISTORY"] = _issue_and_run_boundary(
        executable=executable,
        project_root=clean_project,
        work_root=work_root,
        receipt_path=receipt_path,
        tri_workspace=tri_workspace,
        batch_plan_sha256=batch_plan_sha256,
        scoped_manifest_sha256=scoped_manifest_sha256,
        boundary_id="import_status_history",
        input_root=history_workspace,
        stage_manifest_sha256=history_manifest,
        boundary_inputs={
            "status_corporate_root": status_output,
            "workspace": history_workspace,
        },
        predecessor_admissions=(sidecars["STATUS_CORPORATE"],),
        operation_arguments=(),
        boundary_command=[
            "import-status-history",
            "--status-corporate-root", str(status_output),
            "--workspace", str(history_workspace),
            "--output-root", str(history_output),
        ],
        output_root=history_output,
        expected_exit=0,
    )
    _expect(report, "status", "HISTORICAL_STATUS_INTERVALS_READY")
    exercised.append("import-status-history")

    # Official foundation -> benchmark history.
    benchmark_workspace = work_root / "benchmark-workspace"
    _command(
        executable,
        clean_project,
        [
            "prepare-benchmark-history",
            "--official-foundation-root", str(official_output),
            "--output-root", str(benchmark_workspace),
            "--run-id", RUN_ID,
            "--window-from", "2026-08-03",
            "--window-to", "2026-08-09",
            "--prepared-by", "installed-wheel-check",
        ],
        expected_exit=0,
    )
    from kubo.benchmark_workspace import load_official_calendar_receipt
    from tests.benchmark_fixture_helpers import accept_fixture_manifest

    calendar = load_official_calendar_receipt(official_output)
    trading_dates = tuple(
        day.isoformat()
        for day in sorted(calendar.trading_dates)
        if "2026-08-03" <= day.isoformat() <= "2026-08-09"
    )
    benchmark_payload = accept_fixture_manifest(benchmark_workspace, trading_dates)
    for row in benchmark_payload["artifacts"]:
        row["observed_at"] = "2026-08-13T09:00:00+03:00"
    (
        benchmark_workspace / "manifests" / "benchmark_history_manifest.json"
    ).write_text(
        json.dumps(benchmark_payload, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    benchmark_manifest = _manifest_workspace(benchmark_workspace)
    benchmark_output = work_root / "benchmark-output"
    report, sidecars["BENCHMARK_HISTORY"] = _issue_and_run_boundary(
        executable=executable,
        project_root=clean_project,
        work_root=work_root,
        receipt_path=receipt_path,
        tri_workspace=tri_workspace,
        batch_plan_sha256=batch_plan_sha256,
        scoped_manifest_sha256=scoped_manifest_sha256,
        boundary_id="import_benchmark_history",
        input_root=benchmark_workspace,
        stage_manifest_sha256=benchmark_manifest,
        boundary_inputs={
            "config_dir": config_dir,
            "official_foundation_root": official_output,
            "workspace": benchmark_workspace,
        },
        predecessor_admissions=(sidecars["OFFICIAL_FOUNDATION"],),
        operation_arguments=("--operation-imported-at", IMPORTED_AT),
        boundary_command=[
            "import-benchmark-history",
            "--official-foundation-root", str(official_output),
            "--workspace", str(benchmark_workspace),
            "--output-root", str(benchmark_output),
            "--imported-at", IMPORTED_AT,
        ],
        output_root=benchmark_output,
        expected_exit=1,
    )
    _expect(report, "status", "PARTIAL")
    exercised.append("import-benchmark-history")

    # Official foundation + status history -> official EOD.
    eod_workspace = work_root / "official-eod-workspace"
    _command(
        executable,
        clean_project,
        [
            "prepare-official-eod",
            "--official-foundation-root", str(official_output),
            "--status-history-root", str(history_output),
            "--output-root", str(eod_workspace),
            "--run-id", RUN_ID,
            "--window-from", "2026-08-09",
            "--window-to", "2026-08-09",
            "--prepared-by", "installed-wheel-check",
        ],
        expected_exit=0,
    )
    from tests.official_eod_fixture_helpers import SECURITIES, add_provider

    eod_rows = [
        {
            "trade_date": "2026-08-09",
            "security_code": code,
            "ticker": ticker,
            "trading_state": "TRADED",
            "open_fils": "100",
            "high_fils": "110",
            "low_fils": "90",
            "close_fils": "105",
            "volume": "10",
            "value_traded_kwd": "1.05",
            "trade_count": "1",
            "reference_price_fils": "100",
        }
        for code, ticker in SECURITIES.items()
    ]
    add_provider(eod_workspace, rows=eod_rows)
    eod_manifest = _manifest_workspace(eod_workspace)
    eod_output = work_root / "official-eod-output"
    report, sidecars["OFFICIAL_EOD"] = _issue_and_run_boundary(
        executable=executable,
        project_root=clean_project,
        work_root=work_root,
        receipt_path=receipt_path,
        tri_workspace=tri_workspace,
        batch_plan_sha256=batch_plan_sha256,
        scoped_manifest_sha256=scoped_manifest_sha256,
        boundary_id="import_official_eod",
        input_root=eod_workspace,
        stage_manifest_sha256=eod_manifest,
        boundary_inputs={
            "workspace_root": eod_workspace,
            "official_foundation_root": official_output,
            "status_history_root": history_output,
        },
        predecessor_admissions=(
            sidecars["OFFICIAL_FOUNDATION"],
            sidecars["STATUS_HISTORY"],
        ),
        operation_arguments=(
            "--operation-imported-at", IMPORTED_AT,
            "--operation-run-id", RUN_ID,
        ),
        boundary_command=[
            "import-official-eod",
            "--workspace", str(eod_workspace),
            "--official-foundation-root", str(official_output),
            "--status-history-root", str(history_output),
            "--output-root", str(eod_output),
            "--run-id", RUN_ID,
            "--imported-at", IMPORTED_AT,
        ],
        output_root=eod_output,
        expected_exit=1,
    )
    _expect_one_of(report, "status", {"PARTIAL", "BLOCKED"})
    exercised.append("import-official-eod")

    # Six authenticated predecessor lineages -> final reconciliation.
    policy_path = clean_project / "config" / "pilot" / "outcome_session_policy.json"
    final_inputs = {
        "official_foundation_root": official_output,
        "status_history_root": history_output,
        "ca_enrichment_root": ca_output,
        "research_price_history_root": price_output,
        "benchmark_root": benchmark_output,
        "official_eod_root": eod_output,
        "project_root": clean_project,
        "outcome_session_policy_path": policy_path,
    }
    final_workspace, final_manifest = _final_admission_workspace(
        work_root / "final-admission-workspace",
        final_inputs,
    )
    final_output = work_root / "final-data-foundation-output"
    final_predecessors = tuple(
        sidecars[stage]
        for stage in (
            "OFFICIAL_FOUNDATION",
            "STATUS_HISTORY",
            "CA_ENRICHMENT",
            "RESEARCH_PRICE_HISTORY",
            "BENCHMARK_HISTORY",
            "OFFICIAL_EOD",
        )
    )
    report, _ = _issue_and_run_boundary(
        executable=executable,
        project_root=clean_project,
        work_root=work_root,
        receipt_path=receipt_path,
        tri_workspace=tri_workspace,
        batch_plan_sha256=batch_plan_sha256,
        scoped_manifest_sha256=scoped_manifest_sha256,
        boundary_id="build_data_foundation_packet",
        input_root=final_workspace,
        stage_manifest_sha256=final_manifest,
        boundary_inputs=final_inputs,
        predecessor_admissions=final_predecessors,
        operation_arguments=(),
        boundary_command=[
            "build-data-foundation-packet",
            "--official-foundation-root", str(official_output),
            "--status-history-root", str(history_output),
            "--ca-enrichment-root", str(ca_output),
            "--research-price-history-root", str(price_output),
            "--benchmark-root", str(benchmark_output),
            "--official-eod-root", str(eod_output),
            "--outcome-session-policy", str(policy_path),
            "--output-root", str(final_output),
        ],
        output_root=final_output,
        expected_exit=1,
    )
    _expect_one_of(
        report,
        "status",
        {"DATA_FOUNDATION_PARTIAL", "DATA_FOUNDATION_BLOCKED"},
    )
    exercised.append("build-data-foundation-packet")
    printed = _rendered_command(
        executable,
        clean_project,
        [
            "print-data-foundation-gate-report",
            "--path",
            str(final_output / "reports" / "data_foundation_gate_report.json"),
        ],
        expected_exit=1,
    )
    if not printed.startswith(f"{report['status']} | evidence="):
        raise RuntimeError("printed final gate report did not preserve saved status")

    expected_commands = [
        "import-official-foundation",
        "import-user-price-exports",
        "import-status-corporate",
        "import-ca-enrichment",
        "import-status-history",
        "import-benchmark-history",
        "import-official-eod",
        "build-data-foundation-packet",
    ]
    if exercised != expected_commands:
        raise RuntimeError("installed boundary execution order drifted")
    print(
        json.dumps(
            {
                "status": "PASS",
                "authenticated_boundary_dag": exercised,
                "semantic_admission_count": len(sidecars) + 1,
                "lineage_count": len(sidecars) + 1,
                "clean_project_head": _run(
                    ["git", "-C", str(clean_project), "rev-parse", "HEAD"]
                ).stdout.strip(),
                "installed_package": str(installed_package),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
