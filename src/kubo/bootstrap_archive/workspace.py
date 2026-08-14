"""Atomic, self-verifying scaffold for the Kuwait bootstrap archive.

Version 1.0 creates control material and empty directories only.  It rejects
raw or normalized evidence until a later collection contract is implemented.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import os
from pathlib import Path
import re
import stat
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from ..atomic_output import run_atomic_output
from ..foundation_io import (
    require_real_directory,
    safe_regular_file,
    snapshot_regular_tree,
    strict_json_object,
)
from ..hashing import canonical_json_bytes, sha256_bytes
from ..historical_knowledge import (
    HistoricalKnowledgeCatalog,
    compile_research_plan,
    parse_as_of,
)
from ..source_network import SourceNetworkCatalog
from ..strict import parse_aware
from .bridge import load_historical_source_network_crosswalk
from .contract import load_bootstrap_archive_contract


ARCHIVE_STATUS = "BOOTSTRAP_ARCHIVE_SCAFFOLD_PREPARED"
READINESS_STATUS = "PLANNED_NOT_EXECUTED"
MANIFEST_STATUS = "SCAFFOLD_ONLY_NO_EVIDENCE"
MINIMUM_BOOTSTRAP_AS_OF = date(1980, 1, 1)

_ARCHIVE_ID_RE = re.compile(r"^bootstrap-[0-9a-f]{24}$")
_UTC_SECOND_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$"
)
_CONTROL_INPUTS: tuple[tuple[str, str, str], ...] = (
    ("config/bootstrap_archive.json", "control/bootstrap_archive.json", "ARCHIVE_CONTRACT"),
    ("config/historical_sources.json", "control/historical_sources.json", "HISTORICAL_SOURCE_REGISTRY"),
    ("config/historical_research_layers.json", "control/historical_research_layers.json", "HISTORICAL_LAYER_REGISTRY"),
    (
        "config/historical_source_network_crosswalk.json",
        "control/historical_source_network_crosswalk.json",
        "DECLARED_SOURCE_CROSSWALK",
    ),
    ("config/source_network.json", "control/source_network.json", "SOURCE_NETWORK_REGISTRY"),
    ("config/source_capabilities.json", "control/source_capabilities.json", "SOURCE_CAPABILITY_REGISTRY"),
    ("config/research_policies.json", "control/research_policies.json", "RESEARCH_POLICY_REGISTRY"),
)
_STAGE_FILE_NAMES = (
    "stages/01_bootstrap_archive.json",
    "stages/02_company_intelligence.json",
    "stages/03_source_waves.json",
    "stages/04_boursa_official_reconciliation.json",
)
_COLLECTION_CHECKLIST_BYTES = "\n".join(
    [
        "# Bootstrap Archive Collection Gate",
        "",
        "This workspace is an empty control scaffold, not a collected archive.",
        "",
        "- Do not place raw or normalized historical bytes here under contract 1.0.",
        "- Do not treat control files, queries, or the source crosswalk as evidence.",
        "- Collection remains blocked until runtime source bindings, rights, and a raw-object manifest contract are implemented and tested.",
        "- Company Intelligence remains blocked until a fresh official listed-universe identity anchor is admitted.",
        "- Source Waves remain blocked until Company Intelligence is validated.",
        "- Final Boursa Official Reconciliation remains the last stage.",
        "- No stage may emit a forecast, probability, recommendation, or execution instruction.",
        "",
    ]
).encode("utf-8")
_STATIC_FILE_PATHS = frozenset(
    {
        "bootstrap_archive.json",
        "control/bootstrap_archive_plan.json",
        "control/input_bindings.json",
        "historical/historical_research_plan.json",
        "manifests/bootstrap_archive_manifest.json",
        "reports/bootstrap_archive_workspace_report.json",
        "reports/COLLECTION_CHECKLIST.md",
        *(stored for _, stored, _ in _CONTROL_INPUTS),
        *_STAGE_FILE_NAMES,
    }
)


def _is_reparse_point(metadata: os.stat_result) -> bool:
    attributes = getattr(metadata, "st_file_attributes", 0)
    marker = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & marker)


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _validated_prepare_roots(
    *, project_root: Path, output_root: Path
) -> tuple[Path, Path]:
    project = require_real_directory(project_root, field="bootstrap project root")
    output = Path(os.path.abspath(output_root))
    if not output.name or output == output.parent:
        raise ValueError("bootstrap archive output must name a new directory")
    if _is_within(project, output):
        raise ValueError("bootstrap archive output cannot contain the project tree")
    if _is_within(output, project):
        runtime_root = project / "runtime"
        if output == runtime_root or not _is_within(output, runtime_root):
            raise ValueError(
                "bootstrap archive output inside the checkout must be below runtime/"
            )
    return project, output


def _strict_object(value: Any, *, keys: frozenset[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    missing = sorted(keys - set(value))
    extra = sorted(set(value) - keys)
    if missing or extra:
        raise ValueError(f"{label} has missing={missing} extra={extra}")
    return value


def _input_inventory(config_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source_path, stored_path, role in _CONTROL_INPUTS:
        relative_source = source_path.removeprefix("config/")
        content = safe_regular_file(
            config_root / relative_source,
            field=f"bootstrap input {source_path}",
        )
        strict_json_object(content, f"bootstrap input {source_path}")
        rows.append(
            {
                "source_path": source_path,
                "stored_path": stored_path,
                "role": role,
                "sha256": sha256_bytes(content),
                "size_bytes": len(content),
            }
        )
    return rows


def _build_bootstrap_archive_plan(
    *,
    config_root: Path,
    as_of: date,
    validation_date: date,
) -> dict[str, Any]:
    if as_of < MINIMUM_BOOTSTRAP_AS_OF:
        raise ValueError("bootstrap archive as_of cannot be before 1980-01-01")
    if as_of > validation_date:
        raise ValueError("bootstrap archive as_of cannot be in the future in Asia/Kuwait")
    config_root = require_real_directory(
        config_root,
        field="bootstrap archive configuration root",
    )
    historical_catalog = HistoricalKnowledgeCatalog(config_root)
    network_catalog = SourceNetworkCatalog(config_root)
    contract = load_bootstrap_archive_contract(config_root / "bootstrap_archive.json")
    crosswalk = load_historical_source_network_crosswalk(
        config_root / "historical_source_network_crosswalk.json"
    )
    contract.validate_against(historical_catalog)
    bridge_report = crosswalk.report(historical_catalog, network_catalog)
    historical_plan = compile_research_plan(
        historical_catalog,
        as_of=as_of,
        current_date=validation_date,
    )
    inputs = _input_inventory(config_root)
    plan: dict[str, Any] = {
        "schema_version": "1.0",
        "archive_id": "",
        "archive_kind": contract.archive_kind,
        "as_of": as_of.isoformat(),
        "status": "SCAFFOLD_PLANNED_NOT_EXECUTED",
        "decision_use": "CONTEXT_ONLY",
        "historical_research_plan_id": historical_plan["plan_id"],
        "archive_sections": [section.to_dict() for section in contract.sections],
        "stages": contract.stage_states(),
        "control_inputs": inputs,
        "source_bridge": bridge_report,
        "counts": {
            "historical_source_count": len(historical_catalog.sources),
            "historical_layer_count": len(historical_catalog.layers),
            "historical_task_count": len(historical_plan["tasks"]),
            "historical_evidence_artifact_count": 0,
            "company_count": 0,
            "event_count": 0,
        },
        "collection_gate": {
            "status": "BLOCKED",
            "reasons": [
                "SOURCE_RUNTIME_BINDINGS_NOT_VALIDATED",
                "SOURCE_RIGHTS_NOT_REVIEWED",
                "NO_ARCHIVE_COLLECTION_CONTRACT",
            ],
        },
        "company_intelligence_gate": {
            "status": "BLOCKED",
            "official_listed_universe_anchor_required": True,
            "final_boursa_reconciliation_remains_last_stage": True,
        },
        "claim_boundaries": {
            "historical_corpus_collected": False,
            "historical_completeness_claim_allowed": False,
            "company_intelligence_ready": False,
            "source_waves_ready": False,
            "boursa_reconciliation_ready": False,
            "live_operational": False,
            "forecast_allowed": False,
            "probability_allowed": False,
            "recommendation_allowed": False,
            "execution_allowed": False,
        },
    }
    canonical = canonical_json_bytes({**plan, "archive_id": ""})
    plan["archive_id"] = "bootstrap-" + hashlib.sha256(canonical).hexdigest()[:24]
    return plan


def build_bootstrap_archive_plan(*, config_root: Path, as_of: date) -> dict[str, Any]:
    """Build the stable scaffold plan using Kuwait's current calendar date."""

    return _build_bootstrap_archive_plan(
        config_root=config_root,
        as_of=as_of,
        validation_date=datetime.now(ZoneInfo("Asia/Kuwait")).date(),
    )


def _write_new(path: Path, content: bytes) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    return {
        "path": path.as_posix(),
        "sha256": sha256_bytes(content),
        "size_bytes": len(content),
    }


def _relative_artifact(root: Path, path: Path, content: bytes) -> dict[str, Any]:
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": sha256_bytes(content),
        "size_bytes": len(content),
    }


def _stage_documents(plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    stages = plan["stages"]
    if not isinstance(stages, list):
        raise ValueError("bootstrap archive plan stages are invalid")
    for row in stages:
        if not isinstance(row, Mapping):
            raise ValueError("bootstrap archive plan stage is invalid")
        result.append(
            {
                "schema_version": "1.0",
                "archive_id": plan["archive_id"],
                "stage_id": row["stage_id"],
                "order": row["order"],
                "depends_on": row["depends_on"],
                "status": row["status"],
                "evidence_artifact_count": 0,
                "execution_allowed": False,
            }
        )
    return result


def _manifest_id(payload: Mapping[str, Any]) -> str:
    return "bootstrap-manifest-" + sha256_bytes(
        canonical_json_bytes({**payload, "manifest_id": ""})
    )[:24]


def _prepared_at(value: datetime | None) -> str:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("prepared_at must be timezone-aware")
    return current.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def prepare_bootstrap_archive(
    *,
    project_root: Path,
    output_root: Path,
    as_of: date,
    prepared_at: datetime | None = None,
) -> dict[str, Any]:
    """Atomically publish one empty, immutable bootstrap archive scaffold."""

    wall_clock_now = datetime.now(timezone.utc)
    effective_prepared_at = prepared_at or wall_clock_now
    if effective_prepared_at.tzinfo is None or effective_prepared_at.utcoffset() is None:
        raise ValueError("prepared_at must be timezone-aware")
    if effective_prepared_at.astimezone(timezone.utc) > wall_clock_now:
        raise ValueError("prepared_at cannot be in the future")
    if as_of > effective_prepared_at.astimezone(ZoneInfo("Asia/Kuwait")).date():
        raise ValueError("bootstrap archive as_of cannot be in the future in Asia/Kuwait")

    project_root, output_root = _validated_prepare_roots(
        project_root=project_root,
        output_root=output_root,
    )
    config_root = require_real_directory(
        project_root / "config",
        field="bootstrap archive configuration root",
    )
    validation_date = effective_prepared_at.astimezone(ZoneInfo("Asia/Kuwait")).date()
    plan = _build_bootstrap_archive_plan(
        config_root=config_root,
        as_of=as_of,
        validation_date=validation_date,
    )
    historical_catalog = HistoricalKnowledgeCatalog(config_root)
    historical_plan = compile_research_plan(
        historical_catalog,
        as_of=as_of,
        current_date=validation_date,
    )
    contract = load_bootstrap_archive_contract(config_root / "bootstrap_archive.json")
    timestamp = _prepared_at(effective_prepared_at)
    verification_holder: dict[str, Any] = {}

    def worker(staging: Path) -> dict[str, Any]:
        for relative in contract.directories:
            (staging / relative).mkdir(parents=True, exist_ok=False)

        control_artifacts: list[dict[str, Any]] = []
        expected_inputs = plan["control_inputs"]
        if not isinstance(expected_inputs, list):
            raise ValueError("bootstrap archive plan control inputs are invalid")
        for row in expected_inputs:
            if not isinstance(row, Mapping):
                raise ValueError("bootstrap archive plan control input is invalid")
            source_relative = str(row["source_path"]).removeprefix("config/")
            content = safe_regular_file(
                config_root / source_relative,
                field=f"bootstrap archive frozen input {row['source_path']}",
            )
            if sha256_bytes(content) != row["sha256"] or len(content) != row["size_bytes"]:
                raise ValueError("bootstrap archive input changed during preparation")
            target = staging / str(row["stored_path"])
            _write_new(target, content)
            control_artifacts.append(_relative_artifact(staging, target, content))

        input_bindings = {
            "schema_version": "1.0",
            "archive_id": plan["archive_id"],
            "status": "FROZEN_CONTROL_INPUTS",
            "inputs": expected_inputs,
            "claim_boundaries": {
                "control_input_is_historical_evidence": False,
                "declared_crosswalk_is_runtime_validation": False,
            },
        }
        input_bytes = canonical_json_bytes(input_bindings)
        input_path = staging / "control" / "input_bindings.json"
        _write_new(input_path, input_bytes)
        control_artifacts.append(_relative_artifact(staging, input_path, input_bytes))

        plan_bytes = canonical_json_bytes(plan)
        plan_path = staging / "control" / "bootstrap_archive_plan.json"
        _write_new(plan_path, plan_bytes)
        control_artifacts.append(_relative_artifact(staging, plan_path, plan_bytes))

        historical_plan_bytes = canonical_json_bytes(historical_plan)
        historical_plan_path = staging / "historical" / "historical_research_plan.json"
        _write_new(historical_plan_path, historical_plan_bytes)
        control_artifacts.append(
            _relative_artifact(staging, historical_plan_path, historical_plan_bytes)
        )

        stage_documents = _stage_documents(plan)
        for relative, document in zip(_STAGE_FILE_NAMES, stage_documents, strict=True):
            content = canonical_json_bytes(document)
            target = staging / relative
            _write_new(target, content)
            control_artifacts.append(_relative_artifact(staging, target, content))

        checklist_path = staging / "reports" / "COLLECTION_CHECKLIST.md"
        _write_new(checklist_path, _COLLECTION_CHECKLIST_BYTES)
        control_artifacts.append(
            _relative_artifact(staging, checklist_path, _COLLECTION_CHECKLIST_BYTES)
        )

        control_artifacts.sort(key=lambda item: item["path"])
        manifest: dict[str, Any] = {
            "schema_version": "1.0",
            "manifest_id": "",
            "archive_id": plan["archive_id"],
            "status": MANIFEST_STATUS,
            "control_artifacts": control_artifacts,
            "evidence_artifacts": [],
            "counts": {
                "control_artifact_count": len(control_artifacts),
                "evidence_artifact_count": 0,
            },
            "claim_boundaries": {
                "control_artifact_is_historical_evidence": False,
                "empty_manifest_proves_historical_absence": False,
                "archive_collection_allowed": False,
            },
        }
        manifest["manifest_id"] = _manifest_id(manifest)
        manifest_bytes = canonical_json_bytes(manifest)
        manifest_path = staging / "manifests" / "bootstrap_archive_manifest.json"
        _write_new(manifest_path, manifest_bytes)

        descriptor = {
            "schema_version": "1.0",
            "archive_id": plan["archive_id"],
            "archive_kind": plan["archive_kind"],
            "as_of": plan["as_of"],
            "prepared_at": timestamp,
            "status": ARCHIVE_STATUS,
            "readiness_status": READINESS_STATUS,
            "decision_use": "CONTEXT_ONLY",
            "bootstrap_archive_plan_sha256": sha256_bytes(plan_bytes),
            "historical_research_plan_id": historical_plan["plan_id"],
            "historical_research_plan_sha256": sha256_bytes(historical_plan_bytes),
            "manifest_id": manifest["manifest_id"],
            "manifest_sha256": sha256_bytes(manifest_bytes),
            "stages": plan["stages"],
            "counts": plan["counts"],
            "collection_gate": plan["collection_gate"],
            "company_intelligence_gate": plan["company_intelligence_gate"],
            "claim_boundaries": plan["claim_boundaries"],
        }
        descriptor_bytes = canonical_json_bytes(descriptor)
        descriptor_path = staging / "bootstrap_archive.json"
        _write_new(descriptor_path, descriptor_bytes)

        report = {
            "schema_version": "1.0",
            "status": "PASS_SCAFFOLD_PREPARATION",
            "archive_id": plan["archive_id"],
            "archive_status": ARCHIVE_STATUS,
            "readiness_status": READINESS_STATUS,
            "archive_descriptor_sha256": sha256_bytes(descriptor_bytes),
            "bootstrap_archive_plan_sha256": sha256_bytes(plan_bytes),
            "manifest_sha256": sha256_bytes(manifest_bytes),
            "historical_research_plan_sha256": sha256_bytes(historical_plan_bytes),
            "historical_task_count": len(historical_plan["tasks"]),
            "evidence_artifact_count": 0,
            "company_count": 0,
            "event_count": 0,
            "claim_boundaries": plan["claim_boundaries"],
        }
        report_bytes = canonical_json_bytes(report)
        _write_new(
            staging / "reports" / "bootstrap_archive_workspace_report.json",
            report_bytes,
        )
        return report

    def validate_staging(staging: Path) -> None:
        verification_holder.update(verify_bootstrap_archive(archive_root=staging))

    report = run_atomic_output(output_root, worker, before_commit=validate_staging)
    return {**report, "pre_commit_validation": verification_holder}


def _parse_file(files: Mapping[str, Any], path: str, label: str) -> dict[str, Any]:
    try:
        content = files[path].content
    except KeyError as exc:
        raise ValueError(f"bootstrap archive lacks {path}") from exc
    payload = strict_json_object(content, label)
    if content != canonical_json_bytes(payload):
        raise ValueError(f"{label} must use canonical JSON encoding")
    return payload


def _directory_inventory(root: Path) -> frozenset[str]:
    """Return every real directory below root without following links."""

    directories: set[str] = set()
    entry_count = 0

    def visit(current: Path, relative_parts: tuple[str, ...], depth: int) -> None:
        nonlocal entry_count
        if depth > 8:
            raise ValueError("bootstrap archive directory inventory is too deep")
        try:
            with os.scandir(current) as iterator:
                entries = sorted(iterator, key=lambda item: item.name)
        except OSError as exc:
            raise ValueError("bootstrap archive directory cannot be enumerated") from exc
        for entry in entries:
            entry_count += 1
            if entry_count > 256:
                raise ValueError("bootstrap archive directory inventory is too large")
            try:
                metadata = entry.stat(follow_symlinks=False)
            except OSError as exc:
                raise ValueError("bootstrap archive directory changed during enumeration") from exc
            if (
                stat.S_ISLNK(metadata.st_mode)
                or _is_reparse_point(metadata)
            ):
                raise ValueError(
                    "bootstrap archive must not contain symlinks or reparse points"
                )
            relative = (*relative_parts, entry.name)
            if stat.S_ISDIR(metadata.st_mode):
                directories.add("/".join(relative))
                visit(Path(entry.path), relative, depth + 1)
            elif not stat.S_ISREG(metadata.st_mode):
                raise ValueError("bootstrap archive must contain only files and directories")

    visit(root, (), 0)
    return frozenset(directories)


def _expected_directory_inventory(relative_directories: tuple[str, ...]) -> frozenset[str]:
    expected: set[str] = set()
    for relative in relative_directories:
        parts = Path(relative).parts
        expected.update(Path(*parts[:index]).as_posix() for index in range(1, len(parts) + 1))
    return frozenset(expected)


def verify_bootstrap_archive(*, archive_root: Path) -> dict[str, Any]:
    """Reopen and verify the complete empty scaffold from its frozen bytes."""

    root = require_real_directory(archive_root, field="bootstrap archive root")
    directories_before = _directory_inventory(root)
    snapshot = snapshot_regular_tree(
        root,
        field="bootstrap archive scaffold",
        max_files=64,
        max_entries=256,
        max_depth=8,
        max_file_bytes=16 * 1024 * 1024,
        max_total_bytes=64 * 1024 * 1024,
    )
    directories_after = _directory_inventory(root)
    if directories_before != directories_after:
        raise ValueError("bootstrap archive directories changed during verification")
    files = snapshot.by_path()
    actual_paths = frozenset(files)
    if actual_paths != _STATIC_FILE_PATHS:
        missing = sorted(_STATIC_FILE_PATHS - actual_paths)
        extra = sorted(actual_paths - _STATIC_FILE_PATHS)
        raise ValueError(f"bootstrap archive inventory mismatch: missing={missing} extra={extra}")

    control_root = root / "control"
    historical_catalog = HistoricalKnowledgeCatalog(control_root)
    network_catalog = SourceNetworkCatalog(control_root)
    contract = load_bootstrap_archive_contract(control_root / "bootstrap_archive.json")
    crosswalk = load_historical_source_network_crosswalk(
        control_root / "historical_source_network_crosswalk.json"
    )
    contract.validate_against(historical_catalog)
    crosswalk.validate_against(historical_catalog, network_catalog)
    expected_directories = _expected_directory_inventory(contract.directories)
    if directories_after != expected_directories:
        missing = sorted(expected_directories - directories_after)
        extra = sorted(directories_after - expected_directories)
        raise ValueError(
            f"bootstrap archive directory inventory mismatch: missing={missing} extra={extra}"
        )
    for relative in contract.directories:
        require_real_directory(root / relative, field=f"bootstrap archive directory {relative}")

    descriptor = _parse_file(files, "bootstrap_archive.json", "bootstrap archive descriptor")
    descriptor = dict(
        _strict_object(
            descriptor,
            keys=frozenset(
                {
                    "schema_version",
                    "archive_id",
                    "archive_kind",
                    "as_of",
                    "prepared_at",
                    "status",
                    "readiness_status",
                    "decision_use",
                    "bootstrap_archive_plan_sha256",
                    "historical_research_plan_id",
                    "historical_research_plan_sha256",
                    "manifest_id",
                    "manifest_sha256",
                    "stages",
                    "counts",
                    "collection_gate",
                    "company_intelligence_gate",
                    "claim_boundaries",
                }
            ),
            label="bootstrap archive descriptor",
        )
    )
    if descriptor["schema_version"] != "1.0" or descriptor["status"] != ARCHIVE_STATUS:
        raise ValueError("bootstrap archive descriptor status is invalid")
    if descriptor["archive_kind"] != contract.archive_kind:
        raise ValueError("bootstrap archive descriptor kind is invalid")
    if descriptor["readiness_status"] != READINESS_STATUS or descriptor["decision_use"] != "CONTEXT_ONLY":
        raise ValueError("bootstrap archive descriptor overstates readiness")
    archive_id = descriptor["archive_id"]
    if not isinstance(archive_id, str) or not _ARCHIVE_ID_RE.fullmatch(archive_id):
        raise ValueError("bootstrap archive ID is invalid")
    if not isinstance(descriptor["as_of"], str):
        raise ValueError("bootstrap archive as_of must be an ISO date string")
    as_of = parse_as_of(descriptor["as_of"])
    prepared_at = descriptor["prepared_at"]
    if not isinstance(prepared_at, str) or not _UTC_SECOND_RE.fullmatch(prepared_at):
        raise ValueError("bootstrap archive prepared_at must be canonical UTC seconds")
    prepared = parse_aware(prepared_at, "prepared_at")
    if _prepared_at(prepared) != prepared_at:
        raise ValueError("bootstrap archive prepared_at must be canonical UTC seconds")
    verification_now = datetime.now(timezone.utc)
    if prepared > verification_now:
        raise ValueError("bootstrap archive prepared_at cannot be in the future")
    if as_of > prepared.astimezone(ZoneInfo("Asia/Kuwait")).date():
        raise ValueError("bootstrap archive as_of cannot be after prepared_at in Asia/Kuwait")

    validation_date = verification_now.astimezone(ZoneInfo("Asia/Kuwait")).date()
    expected_plan = _build_bootstrap_archive_plan(
        config_root=control_root,
        as_of=as_of,
        validation_date=validation_date,
    )
    if expected_plan["archive_id"] != archive_id:
        raise ValueError("bootstrap archive ID does not bind the frozen plan")
    if descriptor["stages"] != expected_plan["stages"]:
        raise ValueError("bootstrap archive stage states changed")
    if descriptor["counts"] != expected_plan["counts"]:
        raise ValueError("bootstrap archive counts changed")
    if descriptor["collection_gate"] != expected_plan["collection_gate"]:
        raise ValueError("bootstrap archive collection gate changed")
    if descriptor["company_intelligence_gate"] != expected_plan["company_intelligence_gate"]:
        raise ValueError("bootstrap archive company-intelligence gate changed")
    if descriptor["claim_boundaries"] != expected_plan["claim_boundaries"]:
        raise ValueError("bootstrap archive claim boundaries changed")

    bootstrap_plan_bytes = files["control/bootstrap_archive_plan.json"].content
    if bootstrap_plan_bytes != canonical_json_bytes(expected_plan):
        raise ValueError("bootstrap archive plan is not canonical or changed")
    if descriptor["bootstrap_archive_plan_sha256"] != sha256_bytes(bootstrap_plan_bytes):
        raise ValueError("bootstrap archive plan hash mismatch")

    historical_plan_bytes = files["historical/historical_research_plan.json"].content
    expected_historical_plan = compile_research_plan(
        historical_catalog,
        as_of=as_of,
        current_date=validation_date,
    )
    if historical_plan_bytes != canonical_json_bytes(expected_historical_plan):
        raise ValueError("bootstrap historical research plan is not canonical or changed")
    if descriptor["historical_research_plan_id"] != expected_historical_plan["plan_id"]:
        raise ValueError("bootstrap descriptor references the wrong historical plan")
    if descriptor["historical_research_plan_sha256"] != sha256_bytes(historical_plan_bytes):
        raise ValueError("bootstrap historical plan hash mismatch")

    input_bindings = _parse_file(files, "control/input_bindings.json", "bootstrap input bindings")
    if input_bindings != {
        "schema_version": "1.0",
        "archive_id": archive_id,
        "status": "FROZEN_CONTROL_INPUTS",
        "inputs": expected_plan["control_inputs"],
        "claim_boundaries": {
            "control_input_is_historical_evidence": False,
            "declared_crosswalk_is_runtime_validation": False,
        },
    }:
        raise ValueError("bootstrap input bindings changed")

    for expected_row in expected_plan["control_inputs"]:
        stored_path = str(expected_row["stored_path"])
        item = files.get(stored_path)
        if item is None or item.sha256 != expected_row["sha256"] or item.size_bytes != expected_row["size_bytes"]:
            raise ValueError("bootstrap frozen control input hash mismatch")

    if files["reports/COLLECTION_CHECKLIST.md"].content != _COLLECTION_CHECKLIST_BYTES:
        raise ValueError("bootstrap archive collection checklist changed")

    expected_stage_documents = _stage_documents(expected_plan)
    for relative, expected_document in zip(
        _STAGE_FILE_NAMES, expected_stage_documents, strict=True
    ):
        if _parse_file(files, relative, f"bootstrap stage {relative}") != expected_document:
            raise ValueError("bootstrap stage document changed")

    manifest = _parse_file(
        files,
        "manifests/bootstrap_archive_manifest.json",
        "bootstrap archive manifest",
    )
    manifest = dict(
        _strict_object(
            manifest,
            keys=frozenset(
                {
                    "schema_version",
                    "manifest_id",
                    "archive_id",
                    "status",
                    "control_artifacts",
                    "evidence_artifacts",
                    "counts",
                    "claim_boundaries",
                }
            ),
            label="bootstrap archive manifest",
        )
    )
    if (
        manifest["schema_version"] != "1.0"
        or manifest["archive_id"] != archive_id
        or manifest["status"] != MANIFEST_STATUS
        or manifest["evidence_artifacts"] != []
        or manifest["claim_boundaries"]
        != {
            "control_artifact_is_historical_evidence": False,
            "empty_manifest_proves_historical_absence": False,
            "archive_collection_allowed": False,
        }
    ):
        raise ValueError("bootstrap archive manifest overstates evidence or collection")
    if manifest["manifest_id"] != _manifest_id(manifest):
        raise ValueError("bootstrap archive manifest ID mismatch")
    manifest_bytes = files["manifests/bootstrap_archive_manifest.json"].content
    if descriptor["manifest_id"] != manifest["manifest_id"]:
        raise ValueError("bootstrap archive descriptor references the wrong manifest")
    if descriptor["manifest_sha256"] != sha256_bytes(manifest_bytes):
        raise ValueError("bootstrap archive manifest hash mismatch")

    declared_control = manifest["control_artifacts"]
    if not isinstance(declared_control, list):
        raise ValueError("bootstrap archive control artifact inventory is invalid")
    control_paths = {
        *(stored for _, stored, _ in _CONTROL_INPUTS),
        "control/bootstrap_archive_plan.json",
        "control/input_bindings.json",
        "historical/historical_research_plan.json",
        "reports/COLLECTION_CHECKLIST.md",
        *_STAGE_FILE_NAMES,
    }
    expected_control = [
        {
            "path": path,
            "sha256": files[path].sha256,
            "size_bytes": files[path].size_bytes,
        }
        for path in sorted(control_paths)
    ]
    if declared_control != expected_control:
        raise ValueError("bootstrap archive control artifact inventory changed")
    if manifest["counts"] != {
        "control_artifact_count": len(expected_control),
        "evidence_artifact_count": 0,
    }:
        raise ValueError("bootstrap archive manifest counts changed")

    report = _parse_file(
        files,
        "reports/bootstrap_archive_workspace_report.json",
        "bootstrap archive workspace report",
    )
    report = dict(
        _strict_object(
            report,
            keys=frozenset(
                {
                    "schema_version",
                    "status",
                    "archive_id",
                    "archive_status",
                    "readiness_status",
                    "archive_descriptor_sha256",
                    "bootstrap_archive_plan_sha256",
                    "manifest_sha256",
                    "historical_research_plan_sha256",
                    "historical_task_count",
                    "evidence_artifact_count",
                    "company_count",
                    "event_count",
                    "claim_boundaries",
                }
            ),
            label="bootstrap archive workspace report",
        )
    )
    if (
        report["schema_version"] != "1.0"
        or report["status"] != "PASS_SCAFFOLD_PREPARATION"
        or report["archive_id"] != archive_id
        or report["archive_status"] != ARCHIVE_STATUS
        or report["readiness_status"] != READINESS_STATUS
        or report["archive_descriptor_sha256"] != files["bootstrap_archive.json"].sha256
        or report["bootstrap_archive_plan_sha256"] != sha256_bytes(bootstrap_plan_bytes)
        or report["manifest_sha256"] != files["manifests/bootstrap_archive_manifest.json"].sha256
        or report["historical_research_plan_sha256"] != sha256_bytes(historical_plan_bytes)
        or report["historical_task_count"] != len(expected_historical_plan["tasks"])
        or report["evidence_artifact_count"] != 0
        or report["company_count"] != 0
        or report["event_count"] != 0
        or report["claim_boundaries"] != expected_plan["claim_boundaries"]
    ):
        raise ValueError("bootstrap archive workspace report changed or overstates readiness")

    final_snapshot = snapshot_regular_tree(
        root,
        field="bootstrap archive scaffold final recheck",
        max_files=64,
        max_entries=256,
        max_depth=8,
        max_file_bytes=16 * 1024 * 1024,
        max_total_bytes=64 * 1024 * 1024,
    )
    if final_snapshot.inventory() != snapshot.inventory():
        raise ValueError("bootstrap archive files changed during verification")
    if _directory_inventory(root) != expected_directories:
        raise ValueError("bootstrap archive directories changed during verification")

    return {
        "status": "PASS_EMPTY_ARCHIVE_SCAFFOLD",
        "archive_id": archive_id,
        "archive_status": ARCHIVE_STATUS,
        "readiness_status": READINESS_STATUS,
        "historical_source_count": len(historical_catalog.sources),
        "historical_layer_count": len(historical_catalog.layers),
        "historical_task_count": len(expected_historical_plan["tasks"]),
        "evidence_artifact_count": 0,
        "company_count": 0,
        "event_count": 0,
        "collection_allowed": False,
        "claim_boundaries": expected_plan["claim_boundaries"],
    }


__all__ = [
    "ARCHIVE_STATUS",
    "MANIFEST_STATUS",
    "MINIMUM_BOOTSTRAP_AS_OF",
    "READINESS_STATUS",
    "build_bootstrap_archive_plan",
    "prepare_bootstrap_archive",
    "verify_bootstrap_archive",
]
