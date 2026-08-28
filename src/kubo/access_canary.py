"""Fail-closed audit for the bounded Kuwait public-access canary.

The canary is deliberately narrower than collection.  It reopens one canonical
source-access plan, one executor-produced access receipt, and the executor's
private report.  A pass proves only that one allowlisted public source returned
non-empty bytes whose digest can be reopened.  The public audit never contains
the raw bytes or private runtime paths, and it cannot create market evidence,
findings, candidates, forecasts, recommendations, or trades.
"""

from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit, urlunsplit

from .atomic_output import run_atomic_output
from .foundation_io import load_strict_json_object, safe_regular_file
from .hashing import canonical_json_bytes, hash_json, sha256_bytes
from .source_access_recipes import (
    PLAN_CLAIM_BOUNDARIES,
    PROBE_CLAIM_BOUNDARIES,
    SourceAccessRecipeCatalog,
    validate_access_probe_against_plan,
    validate_source_probe_plan,
)
from .source_network import SourceNetworkCatalog
from .strict import require_sha256, safe_relative_path
from .workflow_yaml import WorkflowYamlError, load_workflow_yaml


WORKFLOW_PATH = Path(".github/workflows/kuwait-access-canary.yml")
ALLOWED_SOURCE_IDS = (
    "kcc_maqasa_official",
    "boursa_reports_archive",
)
EXPECTED_BUDGET = {
    "max_attempts": 1,
    "timeout_seconds": 9,
    "max_bytes": 4 * 1024 * 1024,
}
CANARY_CLAIM_BOUNDARIES = {
    "access_only": True,
    "market_data_collected": False,
    "market_evidence_created": False,
    "parser_executed": False,
    "candidate_generation_invoked": False,
    "forecast_or_recommendation_created": False,
    "publication_attempted": False,
    "trade_allowed": False,
    "raw_bytes_uploaded": False,
}
_EXECUTOR_FALSE_CLAIMS = (
    "market_data_collected",
    "market_evidence_created",
    "parser_executed",
    "forecast_or_recommendation_created",
)
_FORBIDDEN_TRUE_CLAIMS = tuple(
    key for key, allowed in CANARY_CLAIM_BOUNDARIES.items() if allowed is False
)
AUTHORIZED_PR_HEAD_REF = "codex/ku-bo-readiness-live-canary-v1"
_PUBLIC_PLAN_NAME = "source-probe-plan.sanitized.json"
_PUBLIC_RECEIPT_NAME = "access-probe-receipt.sanitized.json"
_PUBLIC_AUDIT_NAME = "canary-audit.json"
_CHECKOUT_ACTION = "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"
_SETUP_PYTHON_ACTION = (
    "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97"
)
_UPLOAD_ACTION = (
    "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02"
)
_PY_YAML_INSTALL = (
    "python -m pip install --disable-pip-version-check PyYAML==6.0.3"
)
_ACCESS_RUN_SHA256 = {
    "Install pinned workflow-validator dependency": (
        "df846cc295169b3e22f1d661d35a2a580148bc9a1dc5c4748f38e310c96f4cb1"
    ),
    "Validate bounded access-only workflow contract": (
        "ee85d2396a077b37ed27364db673f42607c9f7867a91f2f93abd0017bbeeee25"
    ),
    "Build one bounded public access plan": (
        "5febe129389256750c05a2cff35676a6cc8af51058d9e0c5867d6c5e330fd8ee"
    ),
    "Execute one credential-free public access probe": (
        "efe0e633ad18d12ba09e744716f98754d9fd157244ba11ed395e86bd33e789d3"
    ),
    "Reopen bytes and create sanitized no-trade audit": (
        "32ae05fa8b5090eec5cb5430e1d789d83698a17dfdf13ecb3613ed2e2c159a30"
    ),
    "Write sanitized access-only summary": (
        "36d3f91390932f94587bbf7a1ed072fa24a05e29b3bdc6eba5873afdab99d5cf"
    ),
    "Preserve truthful canary result": (
        "7e01e0eae1a20a5ad211777b7bd53d0d6eac4eb37da79fa4af3e9506367d5af9"
    ),
}


class AccessCanaryError(ValueError):
    """Raised when the canary contract or its sanitized outputs are unsafe."""


def _safe_public_url(value: Any, *, allowed_domains: tuple[str, ...]) -> str:
    """Return a query-free HTTPS URL limited to one catalog source."""

    try:
        parsed = urlsplit(str(value or ""))
        port = parsed.port
    except ValueError as exc:
        raise AccessCanaryError("CANARY_PUBLIC_URL_INVALID") from exc
    host = (parsed.hostname or "").casefold().rstrip(".")
    allowed = any(
        host == domain.casefold().rstrip(".")
        or host.endswith("." + domain.casefold().rstrip("."))
        for domain in allowed_domains
    )
    if (
        parsed.scheme.casefold() != "https"
        or not host
        or not allowed
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
    ):
        raise AccessCanaryError("CANARY_PUBLIC_URL_OUTSIDE_ALLOWLIST")
    netloc = host if port is None else f"{host}:{port}"
    return urlunsplit(("https", netloc, parsed.path or "/", "", ""))


def _load(path: Path, field: str) -> tuple[dict[str, Any], bytes]:
    try:
        return load_strict_json_object(path, field=field, max_bytes=8 * 1024 * 1024)
    except ValueError as exc:
        raise AccessCanaryError(f"INVALID_{field.upper().replace(' ', '_')}") from exc


def _write(path: Path, value: Mapping[str, Any]) -> bytes:
    content = canonical_json_bytes(value)
    path.write_bytes(content)
    return content


def _workflow_mapping(value: Any, *, error: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AccessCanaryError(error)
    return value


def _workflow_exact_keys(
    value: Any,
    expected: set[str] | frozenset[str],
    *,
    error: str,
) -> Mapping[str, Any]:
    mapping = _workflow_mapping(value, error=error)
    if set(mapping) != set(expected):
        raise AccessCanaryError(error)
    return mapping


def validate_access_canary_workflow(
    project_root: Path | str,
    *,
    workflow_path: Path | str | None = None,
) -> dict[str, Any]:
    """Validate that canary activation remains bounded and no-trade.

    Besides manual dispatch, exactly one PR event shape is admitted: ``opened``
    against ``main`` from the named same-repository canary branch.  Updates and
    reopened PRs cannot trigger it.
    """

    root = Path(project_root).resolve()
    path = (
        Path(workflow_path).resolve()
        if workflow_path is not None
        else root / WORKFLOW_PATH
    )
    try:
        content = safe_regular_file(
            path,
            field="Kuwait access canary workflow",
            max_bytes=256 * 1024,
        )
        text = content.decode("utf-8")
    except (UnicodeError, ValueError) as exc:
        raise AccessCanaryError("CANARY_WORKFLOW_UNREADABLE") from exc
    if "\t" in text:
        raise AccessCanaryError("CANARY_WORKFLOW_TABS_FORBIDDEN")
    try:
        workflow = load_workflow_yaml(content, field="Kuwait access canary workflow")
    except WorkflowYamlError as exc:
        raise AccessCanaryError("CANARY_WORKFLOW_INVALID_YAML") from exc

    _workflow_exact_keys(
        workflow,
        {"name", "on", "permissions", "concurrency", "jobs"},
        error="CANARY_WORKFLOW_TOP_LEVEL_NOT_EXACT",
    )
    if workflow["name"] != "Kuwait Public Access Canary":
        raise AccessCanaryError("CANARY_WORKFLOW_NAME_CHANGED")

    expected_triggers = {
        "workflow_dispatch": {
            "inputs": {
                "source_id": {
                    "description": "Fixed public source to probe once",
                    "required": "true",
                    "default": "kcc_maqasa_official",
                    "type": "choice",
                    "options": list(ALLOWED_SOURCE_IDS),
                },
                "confirm_no_trade": {
                    "description": (
                        "Confirm access-only execution with no market evidence or trade"
                    ),
                    "required": "true",
                    "default": "true",
                    "type": "boolean",
                },
            }
        },
        "pull_request": {"branches": ["main"], "types": ["opened"]},
    }
    if workflow["on"] != expected_triggers:
        raise AccessCanaryError("CANARY_WORKFLOW_TRIGGER_SCOPE_UNSAFE")

    if workflow["permissions"] != {"contents": "read"}:
        raise AccessCanaryError("CANARY_WORKFLOW_PERMISSIONS_NOT_READ_ONLY")
    if workflow["concurrency"] != {
        "group": "kubo-kuwait-public-access-canary",
        "cancel-in-progress": "false",
    }:
        raise AccessCanaryError("CANARY_WORKFLOW_CONCURRENCY_CHANGED")

    jobs = _workflow_exact_keys(
        workflow["jobs"],
        {"access_canary"},
        error="CANARY_WORKFLOW_JOBS_NOT_EXACT",
    )
    job = _workflow_exact_keys(
        jobs["access_canary"],
        {"if", "runs-on", "timeout-minutes", "env", "steps"},
        error="CANARY_WORKFLOW_JOB_SHAPE_NOT_EXACT",
    )
    if job["runs-on"] != "ubuntu-latest" or job["timeout-minutes"] != "5":
        raise AccessCanaryError("CANARY_WORKFLOW_JOB_BOUNDS_CHANGED")

    expected_guard = " ".join(
        (
            "(github.event_name == 'workflow_dispatch' &&",
            f"github.ref == 'refs/heads/{AUTHORIZED_PR_HEAD_REF}') ||",
            "(github.event_name == 'pull_request' &&",
            "github.event.action == 'opened' &&",
            "github.event.pull_request.base.ref == 'main' &&",
            f"github.event.pull_request.head.ref == '{AUTHORIZED_PR_HEAD_REF}' &&",
            "github.event.pull_request.head.repo.full_name == github.repository &&",
            "github.event.pull_request.draft == true)",
        )
    )
    if job["if"] != expected_guard:
        raise AccessCanaryError("CANARY_WORKFLOW_PR_JOB_GUARD_WEAKENED")

    expected_job_env = {
        "CANARY_SOURCE_ID": (
            "${{ github.event_name == 'pull_request' && "
            "'kcc_maqasa_official' || inputs.source_id }}"
        ),
        "CANARY_CONFIRM_NO_TRADE": (
            "${{ github.event_name == 'pull_request' && "
            "'true' || inputs.confirm_no_trade }}"
        ),
    }
    if job["env"] != expected_job_env:
        raise AccessCanaryError("CANARY_WORKFLOW_PR_INPUTS_NOT_FIXED")

    steps = job["steps"]
    if not isinstance(steps, list) or len(steps) != 10:
        raise AccessCanaryError("CANARY_WORKFLOW_STEPS_NOT_EXACT")
    if not all(isinstance(step, Mapping) for step in steps):
        raise AccessCanaryError("CANARY_WORKFLOW_STEPS_NOT_EXACT")

    checkout = _workflow_exact_keys(
        steps[0], {"uses", "with"}, error="CANARY_WORKFLOW_CHECKOUT_NOT_EXACT"
    )
    if checkout != {
        "uses": _CHECKOUT_ACTION,
        "with": {
            "persist-credentials": "false",
            "ref": (
                "${{ github.event_name == 'pull_request' && "
                "github.event.pull_request.head.sha || github.sha }}"
            ),
        },
    }:
        raise AccessCanaryError("CANARY_WORKFLOW_CREDENTIAL_FREE_CONTRACT_BROKEN")

    setup_python = _workflow_exact_keys(
        steps[1], {"uses", "with"}, error="CANARY_WORKFLOW_PYTHON_NOT_EXACT"
    )
    if setup_python != {
        "uses": _SETUP_PYTHON_ACTION,
        "with": {"python-version": "3.12", "cache": "pip"},
    }:
        raise AccessCanaryError("CANARY_WORKFLOW_PYTHON_NOT_EXACT")

    dependency_install = _workflow_exact_keys(
        steps[2], {"name", "run"}, error="CANARY_WORKFLOW_DEPENDENCY_NOT_PINNED"
    )
    if dependency_install != {
        "name": "Install pinned workflow-validator dependency",
        "run": _PY_YAML_INSTALL,
    }:
        raise AccessCanaryError("CANARY_WORKFLOW_DEPENDENCY_NOT_PINNED")

    expected_step_shapes = (
        (
            "Validate bounded access-only workflow contract",
            {"name", "run"},
        ),
        (
            "Build one bounded public access plan",
            {"name", "id", "continue-on-error", "run"},
        ),
        (
            "Execute one credential-free public access probe",
            {"name", "id", "if", "continue-on-error", "run"},
        ),
        (
            "Reopen bytes and create sanitized no-trade audit",
            {"name", "id", "if", "continue-on-error", "run"},
        ),
        ("Write sanitized access-only summary", {"name", "if", "run"}),
    )
    for step, (name, keys) in zip(steps[3:8], expected_step_shapes, strict=True):
        exact_step = _workflow_exact_keys(
            step, keys, error="CANARY_WORKFLOW_STEPS_NOT_EXACT"
        )
        if exact_step["name"] != name:
            raise AccessCanaryError("CANARY_WORKFLOW_STEPS_NOT_EXACT")
    if (
        steps[4].get("id") != "plan"
        or steps[4].get("continue-on-error") != "true"
        or steps[5].get("id") != "probe"
        or steps[5].get("if") != "${{ steps.plan.outcome == 'success' }}"
        or steps[5].get("continue-on-error") != "true"
        or steps[6].get("id") != "audit"
        or steps[6].get("if") != "always()"
        or steps[6].get("continue-on-error") != "true"
        or steps[7].get("if") != "always()"
    ):
        raise AccessCanaryError("CANARY_WORKFLOW_STEPS_NOT_EXACT")

    upload = _workflow_exact_keys(
        steps[8],
        {"name", "if", "uses", "with"},
        error="CANARY_WORKFLOW_SANITIZED_UPLOAD_MISSING",
    )
    if upload != {
        "name": "Upload sanitized plan receipt and audit only",
        "if": "always()",
        "uses": _UPLOAD_ACTION,
        "with": {
            "name": (
                "kuwait-access-canary-${{ env.CANARY_SOURCE_ID }}-"
                "${{ github.run_id }}-${{ github.run_attempt }}"
            ),
            "path": "runtime/public/",
            "if-no-files-found": "error",
            "retention-days": "14",
        },
    }:
        raise AccessCanaryError("CANARY_WORKFLOW_UPLOAD_SCOPE_UNSAFE")

    final_step = _workflow_exact_keys(
        steps[9],
        {"name", "if", "env", "run"},
        error="CANARY_WORKFLOW_STEPS_NOT_EXACT",
    )
    if (
        final_step["name"] != "Preserve truthful canary result"
        or final_step["if"] != "always()"
        or final_step["env"]
        != {"AUDIT_OUTCOME": "${{ steps.audit.outcome }}"}
    ):
        raise AccessCanaryError("CANARY_WORKFLOW_STEPS_NOT_EXACT")

    external_actions = [step.get("uses") for step in steps if "uses" in step]
    if external_actions != [_CHECKOUT_ACTION, _SETUP_PYTHON_ACTION, _UPLOAD_ACTION]:
        raise AccessCanaryError("CANARY_WORKFLOW_EXTERNAL_ACTIONS_NOT_EXACT")
    run_hashes: dict[str, str] = {}
    for step in steps:
        if "run" not in step:
            continue
        name = step.get("name")
        run = step.get("run")
        if not isinstance(name, str) or not isinstance(run, str) or name in run_hashes:
            raise AccessCanaryError("CANARY_WORKFLOW_RUN_STEPS_NOT_EXACT")
        run_hashes[name] = sha256_bytes(run.encode("utf-8"))
    if run_hashes != _ACCESS_RUN_SHA256:
        raise AccessCanaryError("CANARY_WORKFLOW_RUN_STEPS_NOT_EXACT")
    return {
        "schema_version": "1.0",
        "status": "PASS_ACCESS_CANARY_WORKFLOW_CONTRACT",
        "workflow_sha256": sha256_bytes(content),
        "manual_dispatch": True,
        "authorized_pr_opened_once": True,
        "authorized_pr_head_ref": AUTHORIZED_PR_HEAD_REF,
        "manual_dispatch_branch_locked": True,
        "pr_update_actions_allowed": False,
        "allowed_source_ids": list(ALLOWED_SOURCE_IDS),
        "credentials_used": False,
        "free_url_input_allowed": False,
        "claim_boundaries": dict(CANARY_CLAIM_BOUNDARIES),
    }


def _sanitize_plan(
    plan: Mapping[str, Any],
    *,
    source: Any,
) -> dict[str, Any]:
    tasks = plan.get("tasks")
    if not isinstance(tasks, list) or len(tasks) != 1 or not isinstance(tasks[0], Mapping):
        raise AccessCanaryError("CANARY_PLAN_REQUIRES_EXACTLY_ONE_TASK")
    task = tasks[0]
    if task.get("source_id") != source.source_id:
        raise AccessCanaryError("CANARY_PLAN_SOURCE_MISMATCH")
    if (
        task.get("capture_method") != "HTTP_GET"
        or task.get("rights_status") != "PUBLIC_ACCESS_ONLY"
        or task.get("collection_frequency") != "ONE_OFF"
        or task.get("budget") != EXPECTED_BUDGET
    ):
        raise AccessCanaryError("CANARY_PLAN_BOUNDS_CHANGED")
    if plan.get("claim_boundaries") != PLAN_CLAIM_BOUNDARIES:
        raise AccessCanaryError("CANARY_PLAN_CLAIM_BOUNDARIES_CHANGED")
    return {
        "schema_version": "1.0",
        "plan_id": plan["plan_id"],
        "recipe_set_id": plan["recipe_set_id"],
        "recipe_set_sha256": plan["recipe_set_sha256"],
        "planned_at": plan["planned_at"],
        "expires_at": plan["expires_at"],
        "status": plan["status"],
        "purpose": plan["purpose"],
        "task": {
            "task_id": task["task_id"],
            "recipe_id": task["recipe_id"],
            "source_id": task["source_id"],
            "source_class": task["source_class"],
            "tested_url": _safe_public_url(
                task["tested_url"], allowed_domains=source.domains
            ),
            "access_mode": task["access_mode"],
            "capture_method": task["capture_method"],
            "collection_frequency": task["collection_frequency"],
            "rights_status": task["rights_status"],
            "artifact_policy": task["artifact_policy"],
            "budget": dict(EXPECTED_BUDGET),
        },
        "claim_boundaries": dict(PLAN_CLAIM_BOUNDARIES),
    }


def _sanitize_receipt(
    probe: Mapping[str, Any],
    *,
    source: Any,
) -> tuple[dict[str, Any], Mapping[str, Any]]:
    rows = probe.get("sources")
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], Mapping):
        raise AccessCanaryError("CANARY_RECEIPT_REQUIRES_EXACTLY_ONE_SOURCE")
    row = rows[0]
    if row.get("source_id") != source.source_id:
        raise AccessCanaryError("CANARY_RECEIPT_SOURCE_MISMATCH")
    sanitized_artifact = None
    artifact = row.get("artifact")
    if isinstance(artifact, Mapping):
        sanitized_artifact = {
            "sha256": artifact.get("sha256"),
            "size_bytes": artifact.get("size_bytes"),
            "content_type": artifact.get("content_type"),
            "capture_kind": artifact.get("capture_kind"),
        }
    return (
        {
            "schema_version": probe["schema_version"],
            "probe_id": probe["probe_id"],
            "probe_version": probe["probe_version"],
            "observed_at": probe["observed_at"],
            "expires_at": probe["expires_at"],
            "source": {
                "source_id": row["source_id"],
                "state": row["state"],
                "tested_url": _safe_public_url(
                    row["tested_url"], allowed_domains=source.domains
                ),
                "final_url": (
                    None
                    if row.get("final_url") in (None, "")
                    else _safe_public_url(
                        row["final_url"], allowed_domains=source.domains
                    )
                ),
                "attempted_at": row["attempted_at"],
                "http_status": row["http_status"],
                "data_quality_flags": list(row["data_quality_flags"]),
                "artifact": sanitized_artifact,
            },
            "claim_boundaries": dict(PROBE_CLAIM_BOUNDARIES),
        },
        row,
    )


def _reopen_artifact(
    probe_path: Path,
    row: Mapping[str, Any],
    *,
    max_bytes: int,
) -> dict[str, Any]:
    artifact = row.get("artifact")
    if not isinstance(artifact, Mapping):
        raise AccessCanaryError("CANARY_AVAILABLE_SOURCE_REQUIRES_ARTIFACT")
    try:
        relative = safe_relative_path(artifact.get("path"), "canary artifact path")
        digest = require_sha256(artifact.get("sha256"), "canary artifact sha256")
        content = safe_regular_file(
            Path(os.path.abspath(probe_path.parent)) / relative,
            field="canary raw access artifact",
            max_bytes=max_bytes,
        )
    except ValueError as exc:
        raise AccessCanaryError("CANARY_RAW_ARTIFACT_REOPEN_FAILED") from exc
    if not content:
        raise AccessCanaryError("CANARY_RAW_ARTIFACT_EMPTY")
    if digest != sha256_bytes(content) or artifact.get("size_bytes") != len(content):
        raise AccessCanaryError("CANARY_RAW_ARTIFACT_HASH_OR_SIZE_MISMATCH")
    return {
        "sha256": digest,
        "size_bytes": len(content),
        "content_type": str(artifact.get("content_type") or ""),
        "capture_kind": str(artifact.get("capture_kind") or ""),
        "reopened": True,
    }


def run_access_canary_audit(
    *,
    project_root: Path | str,
    source_id: str,
    confirm_no_trade: bool,
    plan_path: Path | str,
    probe_path: Path | str,
    execution_report_path: Path | str,
    output_root: Path | str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Create sanitized public artifacts and fail closed on anything but AVAILABLE."""

    root = Path(project_root).resolve()
    plan_file = Path(plan_path).resolve()
    probe_file = Path(probe_path).resolve()
    execution_file = Path(execution_report_path).resolve()
    failures: list[str] = []
    sanitized_plan: dict[str, Any] | None = None
    sanitized_receipt: dict[str, Any] | None = None
    artifact_report: dict[str, Any] | None = None
    plan_report: Mapping[str, Any] | None = None
    receipt_report: Mapping[str, Any] | None = None
    workflow_report: Mapping[str, Any] | None = None
    receipt_content = b""
    source_state: str | None = None
    http_status: int | None = None

    if source_id not in ALLOWED_SOURCE_IDS:
        failures.append("SOURCE_ID_NOT_ALLOWLISTED")
    if not confirm_no_trade:
        failures.append("EXPLICIT_NO_TRADE_CONFIRMATION_REQUIRED")

    try:
        workflow_report = validate_access_canary_workflow(root)
    except AccessCanaryError:
        failures.append("WORKFLOW_CONTRACT_REJECTED")

    if source_id in ALLOWED_SOURCE_IDS:
        try:
            catalog = SourceNetworkCatalog(root / "config")
            recipes = SourceAccessRecipeCatalog(
                root / "config" / "source_access_recipes.json", catalog
            )
            source = catalog.sources[source_id]
            plan_report = validate_source_probe_plan(plan_file, recipes, catalog)
            if plan_report.get("status") != "PASS_CONTRACT":
                raise AccessCanaryError("CANARY_PLAN_VALIDATION_BLOCKED")
            if plan_report.get("source_ids") != [source_id]:
                raise AccessCanaryError("CANARY_PLAN_SOURCE_DENOMINATOR_CHANGED")
            plan, _plan_content = _load(plan_file, "canary source plan")
            sanitized_plan = _sanitize_plan(plan, source=source)

            receipt_report = validate_access_probe_against_plan(
                probe_path=probe_file,
                plan_path=plan_file,
                recipes=recipes,
                source_catalog=catalog,
                now=now,
            )
            if receipt_report.get("status") != "PASS_ACCESS_ONLY":
                raise AccessCanaryError("CANARY_RECEIPT_VALIDATION_BLOCKED")
            probe, receipt_content = _load(probe_file, "canary access receipt")
            sanitized_receipt, row = _sanitize_receipt(probe, source=source)
            source_state = str(row.get("state") or "")
            raw_status = row.get("http_status")
            http_status = raw_status if type(raw_status) is int else None
            if source_state != "AVAILABLE":
                failures.append(f"SOURCE_STATE_{source_state or 'UNKNOWN'}")
            else:
                artifact_report = _reopen_artifact(
                    probe_file,
                    row,
                    max_bytes=EXPECTED_BUDGET["max_bytes"],
                )

            execution, _execution_content = _load(
                execution_file, "canary execution report"
            )
            if (
                execution.get("status") != "PASS_ACCESS_ONLY"
                or execution.get("plan_id") != plan_report.get("plan_id")
                or execution.get("plan_sha256") != plan_report.get("plan_sha256")
                or execution.get("probe_id") != receipt_report.get("probe_id")
                or execution.get("probe_hash") != receipt_report.get("probe_hash")
                or execution.get("source_count") != 1
                or execution.get("network_access_attempted") is not True
                or execution.get("network_access_executed") is not True
                or any(execution.get(field) is not False for field in _EXECUTOR_FALSE_CLAIMS)
                or any(
                    execution.get(field, False) is not False
                    for field in _FORBIDDEN_TRUE_CLAIMS
                )
            ):
                failures.append("EXECUTOR_REPORT_CLAIM_BOUNDARY_REJECTED")
        except (AccessCanaryError, KeyError, OSError, TypeError, ValueError):
            failures.append("CANARY_INPUT_VALIDATION_FAILED")

    failures = sorted(set(failures))
    passed = not failures and artifact_report is not None and source_state == "AVAILABLE"
    status = "PASS_ACCESS_ONLY_CANARY" if passed else "BLOCKED_ACCESS_ONLY_CANARY"

    public_values: list[tuple[str, dict[str, Any]]] = []
    if sanitized_plan is not None:
        public_values.append((_PUBLIC_PLAN_NAME, sanitized_plan))
    if sanitized_receipt is not None:
        public_values.append((_PUBLIC_RECEIPT_NAME, sanitized_receipt))
    public_inventory = [
        {
            "path": name,
            "sha256": sha256_bytes(canonical_json_bytes(value)),
            "size_bytes": len(canonical_json_bytes(value)),
        }
        for name, value in public_values
    ]
    audit = {
        "schema_version": "1.0",
        "audit_id": "",
        "status": status,
        "source_id": source_id,
        "source_state": source_state,
        "http_status": http_status,
        "plan_id": None if plan_report is None else plan_report.get("plan_id"),
        "plan_sha256": None if plan_report is None else plan_report.get("plan_sha256"),
        "probe_id": None if receipt_report is None else receipt_report.get("probe_id"),
        "probe_sha256": sha256_bytes(receipt_content) if receipt_content else None,
        "workflow_sha256": (
            None if workflow_report is None else workflow_report.get("workflow_sha256")
        ),
        "artifact": artifact_report,
        "failure_codes": failures,
        "candidate_count": 0,
        "no_trade": True,
        "sanitized_artifacts": public_inventory,
        "claim_boundaries": dict(CANARY_CLAIM_BOUNDARIES),
    }
    audit["audit_id"] = "KAC-" + hash_json({**audit, "audit_id": ""})[:24].upper()

    def worker(staging: Path) -> None:
        for name, value in public_values:
            _write(staging / name, value)
        _write(staging / _PUBLIC_AUDIT_NAME, audit)

    run_atomic_output(output_root, worker)
    return audit


__all__ = [
    "ALLOWED_SOURCE_IDS",
    "AUTHORIZED_PR_HEAD_REF",
    "AccessCanaryError",
    "CANARY_CLAIM_BOUNDARIES",
    "EXPECTED_BUDGET",
    "WORKFLOW_PATH",
    "run_access_canary_audit",
    "validate_access_canary_workflow",
]
