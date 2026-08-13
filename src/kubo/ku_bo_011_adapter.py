from __future__ import annotations

from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import shutil
import threading
import tempfile
from types import MappingProxyType
from typing import Any, Callable, Iterator, Mapping
from unittest.mock import patch
from zoneinfo import ZoneInfo

from . import atomic_output
from . import benchmark_import
from . import ca_enrichment_import
from . import data_foundation_cli
from . import data_foundation_reconciliation
from . import foundation_io
from . import official_eod_import
from . import official_foundation_import
from . import status_corporate_import
from . import status_history_import
from . import tri_security_admission as admission
from . import user_price_export
from .hashing import canonical_json_bytes, sha256_bytes
from .tri_security_pilot import prepare_tri_security_batch_workspace
from .tri_security_receipts import (
    RUN_RECEIPT_FILE,
    STAGE_BINDING_FILE,
    issue_tri_security_run_receipt,
    issue_tri_security_stage_binding,
    verify_tri_security_run_receipt,
    verify_tri_security_stage_binding,
)


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_BATCH_ID = "tri-001-kfh-ship-aznoula"
_RUN_KEY_ID = "ku-bo-011-run-authority-v2"
_STAGE_KEY_ID = "ku-bo-011-stage-authority-v2"
_SEMANTIC_KEY_ID = "ku-bo-011-semantic-authority-v2"
_KUWAIT = ZoneInfo("Asia/Kuwait")
_CONFIG_ENV = "KUBO_KU_BO_011_CONFIG_DIR"


def _config_dir() -> Path:
    """Locate the explicit configuration fixture used by the test adapter."""

    candidates: list[Path] = []
    configured = os.environ.get(_CONFIG_ENV)
    if configured:
        candidates.append(Path(configured))
    candidates.extend((_PROJECT_ROOT / "config", Path.cwd() / "config"))
    required = (
        "tri_security_batches.json",
        "tri_security_vendor_mappings.json",
        "benchmark_registry.json",
        "outcome_session_policy.json",
    )
    for candidate in candidates:
        absolute = candidate.absolute()
        if all((absolute / "pilot" / name).is_file() for name in required):
            return absolute
    raise ProductionAdapterError(
        "KU-BO-011 adapter configuration is unavailable; set "
        f"{_CONFIG_ENV} to the repository config directory"
    )

_BOUNDARY_ORDER = (
    "import_official_foundation",
    "import_user_price_exports",
    "import_status_corporate",
    "import_ca_enrichment",
    "import_status_history",
    "import_benchmark_history",
    "import_official_eod",
    "build_data_foundation_packet",
)
_BOUNDARY_COMMANDS = MappingProxyType(
    {
        "import_user_price_exports": "import-user-price-exports",
        "import_official_foundation": "import-official-foundation",
        "import_status_corporate": "import-status-corporate",
        "import_ca_enrichment": "import-ca-enrichment",
        "import_status_history": "import-status-history",
        "import_benchmark_history": "import-benchmark-history",
        "import_official_eod": "import-official-eod",
        "build_data_foundation_packet": "build-data-foundation-packet",
    }
)
_BOUNDARY_BY_STAGE = MappingProxyType(
    {stage: boundary for boundary, stage in admission.BOUNDARY_STAGE_MAP.items()}
)
_BOUNDARY_MODULES = MappingProxyType(
    {
        "import_user_price_exports": user_price_export,
        "import_official_foundation": official_foundation_import,
        "import_status_corporate": status_corporate_import,
        "import_ca_enrichment": ca_enrichment_import,
        "import_status_history": status_history_import,
        "import_benchmark_history": benchmark_import,
        "import_official_eod": official_eod_import,
        "build_data_foundation_packet": data_foundation_reconciliation,
    }
)
_BOUNDARY_FUNCTION_NAMES = MappingProxyType(
    {
        "import_user_price_exports": "import_investing_user_exports",
        "import_official_foundation": "import_official_foundation",
        "import_status_corporate": "import_status_corporate",
        "import_ca_enrichment": "import_ca_enrichment",
        "import_status_history": "import_status_history",
        "import_benchmark_history": "import_benchmark_history",
        "import_official_eod": "import_official_daily_eod",
        "build_data_foundation_packet": "build_data_foundation_packet",
    }
)
_UNCHECKED_FUNCTION_NAMES = MappingProxyType(
    {
        "import_user_price_exports": "_import_investing_user_exports_unchecked",
        "import_official_foundation": "_import_official_foundation_unchecked",
        "import_status_corporate": "_import_status_corporate_unchecked",
        "import_ca_enrichment": "_import_ca_enrichment_unchecked",
        "import_status_history": "_import_status_history_unchecked",
        "import_benchmark_history": "_import_benchmark_history_unchecked",
        "import_official_eod": "_import_official_daily_eod_unchecked",
        "build_data_foundation_packet": "_build_data_foundation_packet_unchecked",
    }
)


class ProductionAdapterError(RuntimeError):
    """Raised when a corpus mutation does not produce a structured rejection."""


@dataclass(frozen=True, slots=True)
class _IssuedBoundary:
    boundary_id: str
    stage_id: str
    input_root: Path
    binding_path: Path
    admission_path: Path
    published_root: Path
    boundary_inputs: Mapping[str, Path]
    operation_binding: Mapping[str, Any]
    predecessor_paths: tuple[Path, ...]
    stage_manifest_sha256: str


@dataclass(slots=True)
class _MutationContext:
    case: Mapping[str, Any]
    case_root: Path
    input_root: Path
    protected_output_root: Path
    gate_output_root: Path
    boundary_id: str
    mutation_id: str
    variant_index: int
    input_channel: str
    materializer: "_BaselineMaterializer"
    issued: _IssuedBoundary
    request: admission.BoundaryAdmissionRequest
    operation_binding: Mapping[str, Any]
    active_token: admission.VerifiedBoundaryAdmission | None = None
    race_stop: threading.Event | None = None
    race_thread: threading.Thread | None = None
    deterministic_tree_race: bool = False
    atomic_staging: Path | None = None
    cli_run_key: bytes = b""
    cli_run_key_id: str = ""
    cli_stage_key: bytes = b""
    cli_stage_key_id: str = ""
    cli_semantic_key: bytes = b""
    cli_semantic_key_id: str = ""
    audit_events: list[dict[str, str]] = field(default_factory=list)


def _parse_instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _canonical_document(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ProductionAdapterError(f"signed artifact is not an object: {path}")
    return value


def _write_document(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_bytes(canonical_json_bytes(payload))


def _authentication_bytes(payload: Mapping[str, Any]) -> bytes:
    authentication = payload["authentication"]
    return canonical_json_bytes(
        {
            "document": {
                key: value
                for key, value in payload.items()
                if key != "authentication"
            },
            "algorithm": authentication["algorithm"],
            "key_id": authentication["key_id"],
        }
    )


def _resign(path: Path, key: bytes) -> None:
    payload = _canonical_document(path)
    payload["authentication"]["tag"] = hmac.new(
        key,
        _authentication_bytes(payload),
        hashlib.sha256,
    ).hexdigest()
    _write_document(path, payload)


def _mutate_signed(
    path: Path,
    key: bytes,
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    payload = _canonical_document(path)
    mutate(payload)
    payload["authentication"]["tag"] = hmac.new(
        key,
        _authentication_bytes(payload),
        hashlib.sha256,
    ).hexdigest()
    _write_document(path, payload)


def _manifest(root: Path, marker: str) -> str:
    raw = root / "raw"
    nested = root / "nested"
    raw.mkdir(parents=True)
    nested.mkdir()
    evidence = raw / "evidence.bin"
    empty = raw / "empty.bin"
    deep = nested / "deep.bin"
    evidence.write_bytes(f"signed evidence for {marker}".encode("utf-8"))
    empty.write_bytes(b"")
    deep.write_bytes(f"nested {marker}".encode("utf-8"))
    rows = []
    for path in (evidence, empty, deep):
        content = path.read_bytes()
        rows.append(
            {
                "path": path.relative_to(root).as_posix(),
                "sha256": sha256_bytes(content),
                "size_bytes": len(content),
            }
        )
    content = canonical_json_bytes(
        {"schema_version": "3.0", "artifacts": rows}
    )
    (root / "manifest.json").write_bytes(content)
    return sha256_bytes(content)


class _BaselineMaterializer:
    """Build one real signed run and its complete semantic predecessor DAG."""

    def __init__(
        self,
        *,
        case_root: Path,
        target_input_root: Path,
        target_boundary_id: str,
        run_id: str,
        decision_at: str,
    ) -> None:
        self.case_root = Path(case_root)
        self.case_root.mkdir(parents=True, exist_ok=True)
        self.root = self.case_root / "production-fixture"
        self.root.mkdir()
        self.target_input_root = Path(target_input_root)
        self.target_boundary_id = target_boundary_id
        self.run_id = run_id
        self.decision = _parse_instant(decision_at)
        self.decision_at = self.decision.isoformat()
        self.run_key = secrets.token_bytes(32)
        self.stage_key = secrets.token_bytes(32)
        self.semantic_key = secrets.token_bytes(32)
        self.issued_at = (self.decision - timedelta(minutes=10)).isoformat()
        self.bound_at = (self.decision - timedelta(minutes=20)).isoformat()
        self.imported_at = (self.decision - timedelta(minutes=5)).isoformat()
        self.observed_at = self.decision.isoformat()
        self.workspace = self.root / "tri-workspace"
        self.receipt_root = self.root / "run-receipt"
        self.authority_root = self.root / "authorities"
        self.authority_root.mkdir()
        self.published_root = self.root / "published"
        self.published_root.mkdir()
        self.gate_root = self.root / "admission-gates"
        self.gate_root.mkdir()
        self.generic_root = self.root / "boundary-inputs"
        self.generic_root.mkdir()
        self.project_root = self.root / "project"
        policy_parent = self.project_root / "config" / "pilot"
        policy_parent.mkdir(parents=True)
        self.policy_path = policy_parent / "outcome_session_policy.json"
        self.policy_path.write_text(
            '{"policy":"ku-bo-011-signed-fixture"}\n',
            encoding="utf-8",
        )
        self._generic: dict[str, Path] = {}
        self.issued: dict[str, _IssuedBoundary] = {}
        self._prepare_run()
        required = self._required_boundaries(target_boundary_id)
        for boundary_id in _BOUNDARY_ORDER:
            if boundary_id in required:
                self._issue_boundary(boundary_id)

    @staticmethod
    def _required_boundaries(target_boundary_id: str) -> frozenset[str]:
        required: set[str] = set()

        def visit(boundary_id: str) -> None:
            if boundary_id in required:
                return
            required.add(boundary_id)
            stage_id = admission.BOUNDARY_STAGE_MAP[boundary_id]
            for predecessor in admission.STAGE_PREDECESSORS[stage_id]:
                if predecessor != admission.RUN_AUTHORITY_ROOT:
                    visit(_BOUNDARY_BY_STAGE[predecessor])

        visit(target_boundary_id)
        return frozenset(required)

    def _prepare_run(self) -> None:
        prepared = prepare_tri_security_batch_workspace(
            config_dir=_config_dir(),
            output_root=self.workspace,
            batch_id=_BATCH_ID,
            run_id=self.run_id,
            window_from="2026-08-01",
            window_to="2026-08-12",
            prepared_by="ku-bo-011-production-adapter",
        )
        self.plan_sha256 = str(prepared["batch_plan_sha256"])
        self.scoped_sha256 = str(prepared["scoped_config_manifest_sha256"])
        receipt_issued = (self.decision - timedelta(hours=1)).isoformat()
        receipt_expires = (self.decision + timedelta(hours=1)).isoformat()
        issue_tri_security_run_receipt(
            workspace_root=self.workspace,
            output_root=self.receipt_root,
            expected_batch_plan_sha256=self.plan_sha256,
            expected_scoped_config_manifest_sha256=self.scoped_sha256,
            receipt_id=f"receipt-{self.run_id}",
            issuer_id="ku-bo-011-production-run-authority",
            issued_at=receipt_issued,
            expires_at=receipt_expires,
            key=self.run_key,
            key_id=_RUN_KEY_ID,
        )
        self.receipt_path = self.receipt_root / RUN_RECEIPT_FILE
        self.receipt = verify_tri_security_run_receipt(
            receipt_path=self.receipt_path,
            workspace_root=self.workspace,
            expected_batch_plan_sha256=self.plan_sha256,
            expected_scoped_config_manifest_sha256=self.scoped_sha256,
            decision_at=self.decision_at,
            key=self.run_key,
            expected_key_id=_RUN_KEY_ID,
            expected_run_id=self.run_id,
            expected_batch_id=_BATCH_ID,
        )

    def _generic_directory(self, name: str) -> Path:
        path = self._generic.get(name)
        if path is None:
            path = self.generic_root / name
            path.mkdir()
            (path / "input.json").write_text(
                json.dumps({"role": name}, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            self._generic[name] = path
        return path

    def _operation(self, boundary_id: str) -> dict[str, Any]:
        values: dict[str, Any] = {
            "decision_at": self.decision_at,
        }
        if boundary_id == "import_user_price_exports":
            values["observed_at"] = self.observed_at
        elif boundary_id == "import_benchmark_history":
            values["imported_at"] = self.imported_at
        elif boundary_id == "import_official_eod":
            values.update(
                {
                    "imported_at": self.imported_at,
                    "run_id": self.run_id,
                    "runtime_trust_registry": None,
                }
            )
        return admission.build_boundary_operation_binding(boundary_id, **values)

    def _published(self, stage_id: str) -> Path:
        return self.issued[_BOUNDARY_BY_STAGE[stage_id]].published_root

    def _inputs(self, boundary_id: str) -> dict[str, Path]:
        if boundary_id == "import_user_price_exports":
            return {
                "config_dir": _config_dir(),
                "input_dir": self._generic_directory("user-input"),
            }
        if boundary_id == "import_official_foundation":
            return {
                "config_dir": _config_dir(),
                "workspace": self._generic_directory("official-workspace"),
            }
        if boundary_id == "import_status_corporate":
            return {
                "official_foundation_root": self._published("OFFICIAL_FOUNDATION"),
                "workspace": self._generic_directory("status-corporate-workspace"),
            }
        if boundary_id == "import_ca_enrichment":
            return {
                "status_corporate_root": self._published("STATUS_CORPORATE"),
                "workspace": self._generic_directory("ca-workspace"),
            }
        if boundary_id == "import_status_history":
            return {
                "status_corporate_root": self._published("STATUS_CORPORATE"),
                "workspace": self._generic_directory("status-history-workspace"),
            }
        if boundary_id == "import_benchmark_history":
            return {
                "config_dir": _config_dir(),
                "official_foundation_root": self._published("OFFICIAL_FOUNDATION"),
                "workspace": self._generic_directory("benchmark-workspace"),
            }
        if boundary_id == "import_official_eod":
            return {
                "workspace_root": self._generic_directory("eod-workspace"),
                "official_foundation_root": self._published("OFFICIAL_FOUNDATION"),
                "status_history_root": self._published("STATUS_HISTORY"),
            }
        if boundary_id == "build_data_foundation_packet":
            return {
                "official_foundation_root": self._published("OFFICIAL_FOUNDATION"),
                "status_history_root": self._published("STATUS_HISTORY"),
                "ca_enrichment_root": self._published("CA_ENRICHMENT"),
                "research_price_history_root": self._published("RESEARCH_PRICE_HISTORY"),
                "benchmark_root": self._published("BENCHMARK_HISTORY"),
                "official_eod_root": self._published("OFFICIAL_EOD"),
                "project_root": self.project_root,
                "outcome_session_policy_path": self.policy_path,
            }
        raise ProductionAdapterError(f"unsupported production boundary: {boundary_id}")

    def _predecessors(
        self,
        stage_id: str,
        boundary_inputs: Mapping[str, Path],
    ) -> tuple[Path, ...]:
        rows = admission.STAGE_PREDECESSORS[stage_id]
        if rows == (admission.RUN_AUTHORITY_ROOT,):
            return ()
        role_by_stage = {
            "OFFICIAL_FOUNDATION": "official_foundation_root",
            "STATUS_CORPORATE": "status_corporate_root",
            "STATUS_HISTORY": "status_history_root",
            "CA_ENRICHMENT": "ca_enrichment_root",
            "RESEARCH_PRICE_HISTORY": "research_price_history_root",
            "BENCHMARK_HISTORY": "benchmark_root",
            "OFFICIAL_EOD": "official_eod_root",
        }
        return tuple(
            Path(boundary_inputs[role_by_stage[stage]])
            / admission.SEMANTIC_ADMISSION_FILE
            for stage in rows
        )

    def _issue_boundary(self, boundary_id: str) -> None:
        stage_id = admission.BOUNDARY_STAGE_MAP[boundary_id]
        stage_root = (
            self.target_input_root
            if boundary_id == self.target_boundary_id
            else self.root / "stages" / boundary_id
        )
        if stage_root != self.target_input_root:
            stage_root.mkdir(parents=True)
        stage_manifest_sha256 = _manifest(stage_root, boundary_id)
        binding_root = self.authority_root / "bindings" / boundary_id
        binding_root.parent.mkdir(exist_ok=True)
        issue_tri_security_stage_binding(
            verified_receipt=self.receipt,
            workspace_root=self.workspace,
            stage_root=stage_root,
            output_root=binding_root,
            expected_stage_manifest_sha256=stage_manifest_sha256,
            binding_id=f"binding-{self.run_id}-{stage_id.lower()}",
            stage_id=stage_id,
            bound_at=self.bound_at,
            key=self.stage_key,
            key_id=_STAGE_KEY_ID,
        )
        binding_path = binding_root / STAGE_BINDING_FILE
        verified_stage = verify_tri_security_stage_binding(
            binding_path=binding_path,
            receipt_path=self.receipt_path,
            workspace_root=self.workspace,
            stage_root=stage_root,
            expected_batch_plan_sha256=self.plan_sha256,
            expected_scoped_config_manifest_sha256=self.scoped_sha256,
            expected_stage_manifest_sha256=stage_manifest_sha256,
            decision_at=self.decision_at,
            key=self.stage_key,
            expected_key_id=_STAGE_KEY_ID,
            receipt_key=self.run_key,
            expected_receipt_key_id=_RUN_KEY_ID,
            expected_stage_id=stage_id,
            expected_run_id=self.run_id,
            expected_batch_id=_BATCH_ID,
        )
        boundary_inputs = self._inputs(boundary_id)
        operation_binding = self._operation(boundary_id)
        predecessors = self._predecessors(stage_id, boundary_inputs)
        admission_parent = self.authority_root / "admissions"
        admission_parent.mkdir(exist_ok=True)
        admission_path = admission_parent / f"{boundary_id}.json"
        admission.issue_semantic_boundary_admission(
            output_path=admission_path,
            boundary_id=boundary_id,
            verified_receipt=self.receipt,
            v1_stage_report=verified_stage.report(),
            v1_stage_binding_sha256=verified_stage.report()["binding_sha256"],
            input_root=stage_root,
            boundary_inputs=boundary_inputs,
            operation_binding=operation_binding,
            predecessor_admission_paths=predecessors,
            admission_id=f"admission-{self.run_id}-{stage_id.lower()}",
            issued_at=self.issued_at,
            key=self.semantic_key,
            key_id=_SEMANTIC_KEY_ID,
        )
        published_root = self.published_root / stage_id.lower()
        issued = _IssuedBoundary(
            boundary_id=boundary_id,
            stage_id=stage_id,
            input_root=stage_root,
            binding_path=binding_path,
            admission_path=admission_path,
            published_root=published_root,
            boundary_inputs=MappingProxyType(dict(boundary_inputs)),
            operation_binding=MappingProxyType(dict(operation_binding)),
            predecessor_paths=predecessors,
            stage_manifest_sha256=stage_manifest_sha256,
        )
        self.issued[boundary_id] = issued
        token = admission.admit_boundary(
            self.request(boundary_id),
            boundary_id=boundary_id,
            output_root=self.gate_root / boundary_id,
            boundary_inputs=issued.boundary_inputs,
            operation_binding=issued.operation_binding,
        )
        published_root.mkdir()
        (published_root / "reports").mkdir()
        token.materialize_receipt(published_root)
        token.materialize_lineage(published_root)

    def request(self, boundary_id: str) -> admission.BoundaryAdmissionRequest:
        issued = self.issued[boundary_id]
        return admission.BoundaryAdmissionRequest(
            admission_path=issued.admission_path,
            receipt_path=self.receipt_path,
            stage_binding_path=issued.binding_path,
            workspace_root=self.workspace,
            input_root=issued.input_root,
            expected_batch_plan_sha256=self.plan_sha256,
            expected_scoped_config_manifest_sha256=self.scoped_sha256,
            expected_stage_manifest_sha256=issued.stage_manifest_sha256,
            decision_at=self.decision_at,
            expected_run_id=self.run_id,
            expected_batch_id=_BATCH_ID,
            run_key=self.run_key,
            run_key_id=_RUN_KEY_ID,
            v1_stage_key=self.stage_key,
            v1_stage_key_id=_STAGE_KEY_ID,
            semantic_key=self.semantic_key,
            semantic_key_id=_SEMANTIC_KEY_ID,
            boundary_inputs=issued.boundary_inputs,
            operation_binding=issued.operation_binding,
            predecessor_admission_paths=issued.predecessor_paths,
        )


def _semantic_change(
    context: _MutationContext,
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    _mutate_signed(
        context.request.admission_path,
        context.materializer.semantic_key,
        mutate,
    )


def _request_value(context: _MutationContext, field: str, value: Any) -> None:
    if context.active_token is not None:
        object.__setattr__(context.active_token.request, field, value)
    else:
        context.request = replace(context.request, **{field: value})


def _missing_run_receipt(context: _MutationContext) -> None:
    if context.input_channel in {"CLI_ARGUMENT", "DIRECT_API_OBJECT"}:
        _request_value(context, "receipt_path", None)
    else:
        assert context.request.receipt_path is not None
        context.request.receipt_path.unlink(missing_ok=True)


def _malformed_run_receipt(context: _MutationContext) -> None:
    context.request.receipt_path.write_bytes(b'{"truncated":')


def _forged_run_authentication_tag(context: _MutationContext) -> None:
    payload = _canonical_document(context.request.receipt_path)
    tag = payload["authentication"]["tag"]
    payload["authentication"]["tag"] = ("0" if tag[0] != "0" else "1") + tag[1:]
    _write_document(context.request.receipt_path, payload)


def _wrong_run_key_id(context: _MutationContext) -> None:
    payload = _canonical_document(context.request.receipt_path)
    payload["authentication"]["key_id"] = "unknown-ku-bo-011-run-key"
    _write_document(context.request.receipt_path, payload)


def _non_independent_authority(context: _MutationContext) -> None:
    context.cli_stage_key = context.cli_run_key
    _request_value(context, "v1_stage_key", context.request.run_key)


def _expired_run_receipt(context: _MutationContext) -> None:
    expires = (_parse_instant(context.request.decision_at) - timedelta(seconds=1)).isoformat()
    _mutate_signed(
        context.request.receipt_path,
        context.materializer.run_key,
        lambda payload: payload.__setitem__("expires_at", expires),
    )


def _future_run_receipt(context: _MutationContext) -> None:
    issued = _parse_instant(context.request.decision_at) + timedelta(seconds=1)

    def mutate(payload: dict[str, Any]) -> None:
        payload["issued_at"] = issued.isoformat()
        payload["expires_at"] = (issued + timedelta(hours=1)).isoformat()
        payload["run_date"] = issued.astimezone(_KUWAIT).date().isoformat()

    _mutate_signed(
        context.request.receipt_path,
        context.materializer.run_key,
        mutate,
    )


def _semantic_run_field(
    context: _MutationContext,
    field: str,
    value: Any,
) -> None:
    def mutate(payload: dict[str, Any]) -> None:
        payload["run_binding"][field] = value

    _semantic_change(context, mutate)


def _cross_run_receipt(context: _MutationContext) -> None:
    _semantic_run_field(context, "run_id", f"foreign-{context.materializer.run_id}")


def _wrong_receipt_audience(context: _MutationContext) -> None:
    _mutate_signed(
        context.request.receipt_path,
        context.materializer.run_key,
        lambda payload: payload.__setitem__("audience", "foreign-diagnostic-audience"),
    )


def _wrong_batch_binding(context: _MutationContext) -> None:
    _semantic_run_field(context, "batch_id", "tri-999-foreign-batch")


def _batch_plan_hash_mismatch(context: _MutationContext) -> None:
    _semantic_run_field(context, "batch_plan_sha256", "0" * 64)


def _qualification_window_mismatch(context: _MutationContext) -> None:
    _semantic_run_field(
        context,
        "qualification_window",
        {
            "window_from": "2026-08-02",
            "window_to": "2026-08-12",
            "timezone": "Asia/Kuwait",
        },
    )


def _cohort_mismatch(context: _MutationContext) -> None:
    _semantic_run_field(
        context,
        "cohort",
        {
            "security_count": 3,
            "cohort_sha256": "0" * 64,
            "securities": [],
        },
    )


def _scoped_manifest_hash_mismatch(context: _MutationContext) -> None:
    _semantic_run_field(context, "scoped_manifest_sha256", "0" * 64)


def _pending_gate_state_mismatch(context: _MutationContext) -> None:
    def mutate(payload: dict[str, Any]) -> None:
        gates = dict(payload["run_binding"]["pending_gate_state"])
        gates.pop(next(iter(gates)))
        payload["run_binding"]["pending_gate_state"] = gates

    _semantic_change(context, mutate)


def _missing_stage_binding(context: _MutationContext) -> None:
    if context.input_channel in {"CLI_ARGUMENT", "DIRECT_API_OBJECT"}:
        _request_value(context, "stage_binding_path", None)
    else:
        assert context.request.stage_binding_path is not None
        context.request.stage_binding_path.unlink(missing_ok=True)


def _malformed_stage_binding(context: _MutationContext) -> None:
    context.request.stage_binding_path.write_bytes(b'{"truncated":')


def _forged_stage_authentication_tag(context: _MutationContext) -> None:
    payload = _canonical_document(context.request.stage_binding_path)
    tag = payload["authentication"]["tag"]
    payload["authentication"]["tag"] = tag[:-1] + ("0" if tag[-1] != "0" else "1")
    _write_document(context.request.stage_binding_path, payload)


def _wrong_stage_key_id(context: _MutationContext) -> None:
    payload = _canonical_document(context.request.stage_binding_path)
    payload["authentication"]["key_id"] = "unknown-ku-bo-011-stage-key"
    _write_document(context.request.stage_binding_path, payload)


def _cross_run_stage_binding(context: _MutationContext) -> None:
    def mutate(payload: dict[str, Any]) -> None:
        payload["run_binding"]["run_id"] = f"foreign-{context.materializer.run_id}"

    _mutate_signed(
        context.request.stage_binding_path,
        context.materializer.stage_key,
        mutate,
    )


def _wrong_stage_id(context: _MutationContext) -> None:
    current = context.issued.stage_id
    other = "STATUS_CORPORATE" if current != "STATUS_CORPORATE" else "OFFICIAL_FOUNDATION"
    _mutate_signed(
        context.request.stage_binding_path,
        context.materializer.stage_key,
        lambda payload: payload.__setitem__("stage_id", other),
    )


def _stage_manifest_hash_mismatch(context: _MutationContext) -> None:
    _request_value(context, "expected_stage_manifest_sha256", "0" * 64)


def _stage_tree_addition(context: _MutationContext) -> None:
    addition = context.request.input_root / "raw" / "unbound.bin"
    addition.write_bytes(b"unbound stage-tree addition")


def _stage_tree_deletion(context: _MutationContext) -> None:
    (context.request.input_root / "raw" / "evidence.bin").unlink(missing_ok=True)


def _stage_tree_byte_drift(context: _MutationContext) -> None:
    (context.request.input_root / "raw" / "evidence.bin").write_bytes(
        b"mutated stage bytes"
    )


def _unsafe_stage_entry(context: _MutationContext) -> None:
    path = context.request.input_root / "raw" / "unsafe-link.bin"
    target = context.materializer.root / "outside-stage.bin"
    target.write_bytes(b"outside")
    try:
        path.symlink_to(target)
    except (NotImplementedError, OSError):
        fifo = context.request.input_root / "raw" / "unsafe-fifo"
        os.mkfifo(fifo)


def _stage_tree_toc_tou(context: _MutationContext) -> None:
    # The scan instrumentation below inserts a real file after the first
    # bounded tree pass.  This makes the TOCTOU deterministic while still
    # exercising the production double-snapshot detector.
    context.deterministic_tree_race = True


def _stage_root_overlap_or_alias(context: _MutationContext) -> None:
    overlap = context.request.input_root / "overlapping-output"
    if context.active_token is not None:
        object.__setattr__(context.active_token, "_output_root", overlap)
    else:
        context.gate_output_root = overlap


def _stage_artifact_inventory_mismatch(context: _MutationContext) -> None:
    def mutate(payload: dict[str, Any]) -> None:
        payload["stage_artifact"]["complete_file_count"] += 1

    _mutate_signed(
        context.request.stage_binding_path,
        context.materializer.stage_key,
        mutate,
    )


def _predecessor_binding_omission(context: _MutationContext) -> None:
    _semantic_change(
        context,
        lambda payload: payload.__setitem__("predecessor_bindings", []),
    )


def _predecessor_binding_replay(context: _MutationContext) -> None:
    def mutate(payload: dict[str, Any]) -> None:
        rows = payload["predecessor_bindings"]
        rows.append(dict(rows[0]))

    _semantic_change(context, mutate)


def _predecessor_binding_wrong_stage(context: _MutationContext) -> None:
    def mutate(payload: dict[str, Any]) -> None:
        payload["predecessor_bindings"][0]["stage_id"] = "WRONG_PREDECESSOR_STAGE"

    _semantic_change(context, mutate)


def _claim_value(context: _MutationContext, field: str, value: Any) -> None:
    def mutate(payload: dict[str, Any]) -> None:
        payload["claims"][field] = value

    _semantic_change(context, mutate)


def _five_security_denominator_promotion(context: _MutationContext) -> None:
    _claim_value(context, "denominator", "FIVE_SECURITY_COHORT")


def _full_market_claim_promotion(context: _MutationContext) -> None:
    _claim_value(context, "full_market", True)


def _benchmark_fallback_promotion(context: _MutationContext) -> None:
    _claim_value(context, "benchmark_fallback_allowed", True)


def _d01_policy_promotion(context: _MutationContext) -> None:
    _claim_value(context, "outcome_session_policy", "FROZEN_D01_APPROVED")


def _untrusted_legacy_claim_promotion(context: _MutationContext) -> None:
    _claim_value(context, "legacy_july", "TRUSTED_LEGACY_CLAIM")


def _output_root_preexists(context: _MutationContext) -> None:
    context.gate_output_root.mkdir()
    (context.gate_output_root / "racer.txt").write_text(
        "fixture-owned output racer\n",
        encoding="utf-8",
    )


def _partial_output_on_rejection(context: _MutationContext) -> None:
    del context


def _output_commit_toc_tou(context: _MutationContext) -> None:
    if context.variant_index == 2 and context.atomic_staging is not None:
        shutil.rmtree(context.atomic_staging)
        return
    _output_root_preexists(context)


_MUTATION_HANDLERS: Mapping[str, Callable[[_MutationContext], None]] = (
    MappingProxyType(
        {
            "missing_run_receipt": _missing_run_receipt,
            "malformed_run_receipt": _malformed_run_receipt,
            "forged_run_authentication_tag": _forged_run_authentication_tag,
            "wrong_run_key_id": _wrong_run_key_id,
            "non_independent_authority": _non_independent_authority,
            "expired_run_receipt": _expired_run_receipt,
            "future_run_receipt": _future_run_receipt,
            "cross_run_receipt": _cross_run_receipt,
            "wrong_receipt_audience": _wrong_receipt_audience,
            "wrong_batch_binding": _wrong_batch_binding,
            "batch_plan_hash_mismatch": _batch_plan_hash_mismatch,
            "qualification_window_mismatch": _qualification_window_mismatch,
            "cohort_mismatch": _cohort_mismatch,
            "scoped_manifest_hash_mismatch": _scoped_manifest_hash_mismatch,
            "pending_gate_state_mismatch": _pending_gate_state_mismatch,
            "missing_stage_binding": _missing_stage_binding,
            "malformed_stage_binding": _malformed_stage_binding,
            "forged_stage_authentication_tag": _forged_stage_authentication_tag,
            "wrong_stage_key_id": _wrong_stage_key_id,
            "cross_run_stage_binding": _cross_run_stage_binding,
            "wrong_stage_id": _wrong_stage_id,
            "stage_manifest_hash_mismatch": _stage_manifest_hash_mismatch,
            "stage_tree_addition": _stage_tree_addition,
            "stage_tree_deletion": _stage_tree_deletion,
            "stage_tree_byte_drift": _stage_tree_byte_drift,
            "unsafe_stage_entry": _unsafe_stage_entry,
            "stage_tree_toc_tou": _stage_tree_toc_tou,
            "stage_root_overlap_or_alias": _stage_root_overlap_or_alias,
            "stage_artifact_inventory_mismatch": _stage_artifact_inventory_mismatch,
            "predecessor_binding_omission": _predecessor_binding_omission,
            "predecessor_binding_replay": _predecessor_binding_replay,
            "predecessor_binding_wrong_stage": _predecessor_binding_wrong_stage,
            "five_security_denominator_promotion": _five_security_denominator_promotion,
            "full_market_claim_promotion": _full_market_claim_promotion,
            "benchmark_fallback_promotion": _benchmark_fallback_promotion,
            "d01_policy_promotion": _d01_policy_promotion,
            "untrusted_legacy_claim_promotion": _untrusted_legacy_claim_promotion,
            "output_root_preexists": _output_root_preexists,
            "partial_output_on_rejection": _partial_output_on_rejection,
            "output_commit_toc_tou": _output_commit_toc_tou,
        }
    )
)


_MATERIALIZATION_FIELDS = frozenset(
    {
        "handler_id",
        "ingress",
        "artifact",
        "field",
        "action",
        "timing",
        "resign_policy",
        "value",
    }
)
_MATERIALIZATION_INGRESS = MappingProxyType(
    {
        "CLI_ARGUMENT": "CLI_PARSER_TO_PUBLIC_BOUNDARY",
        "DIRECT_API_OBJECT": "DIRECT_PUBLIC_BOUNDARY",
        "SERIALIZED_ARTIFACT": "SERIALIZED_ADMISSION_TO_PUBLIC_BOUNDARY",
        "FILESYSTEM_RACE": "PUBLIC_BOUNDARY_PRE_COMMIT_HOOK",
    }
)
_MATERIALIZATION_TIMING = MappingProxyType(
    {
        "CLI_ARGUMENT": "BEFORE_CLI_PARSE_AND_PUBLIC_BOUNDARY",
        "DIRECT_API_OBJECT": "BEFORE_DIRECT_PUBLIC_BOUNDARY",
        "SERIALIZED_ARTIFACT": "BEFORE_SERIALIZED_ARTIFACT_ADMISSION",
        "FILESYSTEM_RACE": "PUBLIC_BOUNDARY_PRE_COMMIT_RECHECK",
    }
)
_MATERIALIZATION_VARIANT = MappingProxyType(
    {
        "CLI_ARGUMENT": 0,
        "DIRECT_API_OBJECT": 1,
        "SERIALIZED_ARTIFACT": 2,
        "FILESYSTEM_RACE": 3,
    }
)

# Adapter-owned executable descriptions only.  No rejection code, phase, or
# other corpus result oracle is present in this contract.
_MATERIALIZATION_BASE = MappingProxyType(
    {
        "missing_run_receipt": (
            "RUN_RECEIPT_FILE", "/", "DELETE_FILE", "NOT_APPLICABLE", None
        ),
        "malformed_run_receipt": (
            "RUN_RECEIPT_FILE",
            "/",
            "WRITE_TRUNCATED_JSON",
            "NOT_APPLICABLE",
            '{"truncated":',
        ),
        "forged_run_authentication_tag": (
            "RUN_RECEIPT_FILE",
            "/authentication/tag",
            "FLIP_FIRST_TAG_NIBBLE",
            "PRESERVE_STALE_AUTHENTICATION",
            "one changed hex nibble",
        ),
        "wrong_run_key_id": (
            "RUN_RECEIPT_FILE",
            "/authentication/key_id",
            "SET_UNKNOWN_KEY_ID",
            "PRESERVE_STALE_AUTHENTICATION",
            "unknown-ku-bo-011-run-key",
        ),
        "non_independent_authority": (
            "BOUNDARY_ADMISSION_REQUEST",
            "/v1_stage_key",
            "REUSE_RUN_SECRET_AS_STAGE_SECRET",
            "NOT_APPLICABLE",
            "request.run_key",
        ),
        "expired_run_receipt": (
            "RUN_RECEIPT_FILE",
            "/expires_at",
            "SET_EXPIRY_BEFORE_DECISION",
            "RESIGN_WITH_RUN_AUTHORITY",
            "decision_at minus 1 second",
        ),
        "future_run_receipt": (
            "RUN_RECEIPT_FILE",
            "/issued_at",
            "SET_ISSUANCE_AFTER_DECISION",
            "RESIGN_WITH_RUN_AUTHORITY",
            "issued_at=decision_at+1s; expires_at=issued_at+1h; recompute run_date",
        ),
        "cross_run_receipt": (
            "SEMANTIC_ADMISSION_FILE",
            "/run_binding/run_id",
            "SET_FOREIGN_RUN_ID",
            "RESIGN_WITH_SEMANTIC_AUTHORITY",
            "foreign-${target_run_id}",
        ),
        "wrong_receipt_audience": (
            "RUN_RECEIPT_FILE",
            "/audience",
            "SET_FOREIGN_AUDIENCE",
            "RESIGN_WITH_RUN_AUTHORITY",
            "foreign-diagnostic-audience",
        ),
        "wrong_batch_binding": (
            "SEMANTIC_ADMISSION_FILE",
            "/run_binding/batch_id",
            "SET_FOREIGN_BATCH_ID",
            "RESIGN_WITH_SEMANTIC_AUTHORITY",
            "tri-999-foreign-batch",
        ),
        "batch_plan_hash_mismatch": (
            "SEMANTIC_ADMISSION_FILE",
            "/run_binding/batch_plan_sha256",
            "SET_ZERO_SHA256",
            "RESIGN_WITH_SEMANTIC_AUTHORITY",
            "0 repeated 64 times",
        ),
        "qualification_window_mismatch": (
            "SEMANTIC_ADMISSION_FILE",
            "/run_binding/qualification_window",
            "REPLACE_QUALIFICATION_WINDOW",
            "RESIGN_WITH_SEMANTIC_AUTHORITY",
            "2026-08-02..2026-08-12 Asia/Kuwait",
        ),
        "cohort_mismatch": (
            "SEMANTIC_ADMISSION_FILE",
            "/run_binding/cohort",
            "REPLACE_WITH_EMPTY_ZERO_HASH_COHORT",
            "RESIGN_WITH_SEMANTIC_AUTHORITY",
            "security_count=3; zero cohort hash; empty securities",
        ),
        "scoped_manifest_hash_mismatch": (
            "SEMANTIC_ADMISSION_FILE",
            "/run_binding/scoped_manifest_sha256",
            "SET_ZERO_SHA256",
            "RESIGN_WITH_SEMANTIC_AUTHORITY",
            "0 repeated 64 times",
        ),
        "pending_gate_state_mismatch": (
            "SEMANTIC_ADMISSION_FILE",
            "/run_binding/pending_gate_state",
            "REMOVE_FIRST_GATE",
            "RESIGN_WITH_SEMANTIC_AUTHORITY",
            "remove first insertion-ordered gate",
        ),
        "missing_stage_binding": (
            "STAGE_BINDING_FILE", "/", "DELETE_FILE", "NOT_APPLICABLE", None
        ),
        "malformed_stage_binding": (
            "STAGE_BINDING_FILE",
            "/",
            "WRITE_TRUNCATED_JSON",
            "NOT_APPLICABLE",
            '{"truncated":',
        ),
        "forged_stage_authentication_tag": (
            "STAGE_BINDING_FILE",
            "/authentication/tag",
            "FLIP_LAST_TAG_NIBBLE",
            "PRESERVE_STALE_AUTHENTICATION",
            "one changed hex nibble",
        ),
        "wrong_stage_key_id": (
            "STAGE_BINDING_FILE",
            "/authentication/key_id",
            "SET_UNKNOWN_KEY_ID",
            "PRESERVE_STALE_AUTHENTICATION",
            "unknown-ku-bo-011-stage-key",
        ),
        "cross_run_stage_binding": (
            "STAGE_BINDING_FILE",
            "/run_binding/run_id",
            "SET_FOREIGN_RUN_ID",
            "RESIGN_WITH_STAGE_AUTHORITY",
            "foreign-${target_run_id}",
        ),
        "wrong_stage_id": (
            "STAGE_BINDING_FILE",
            "/stage_id",
            "SET_OTHER_STAGE_ID",
            "RESIGN_WITH_STAGE_AUTHORITY",
            (
                "STATUS_CORPORATE unless current is STATUS_CORPORATE, otherwise "
                "OFFICIAL_FOUNDATION"
            ),
        ),
        "stage_manifest_hash_mismatch": (
            "BOUNDARY_ADMISSION_REQUEST",
            "/expected_stage_manifest_sha256",
            "SET_ZERO_SHA256",
            "NOT_APPLICABLE",
            "0 repeated 64 times",
        ),
        "stage_tree_addition": (
            "STAGE_INPUT_TREE",
            "/raw/unbound.bin",
            "WRITE_UNBOUND_FILE",
            "NOT_APPLICABLE",
            "unbound stage-tree addition",
        ),
        "stage_tree_deletion": (
            "STAGE_INPUT_TREE",
            "/raw/evidence.bin",
            "DELETE_FILE",
            "NOT_APPLICABLE",
            None,
        ),
        "stage_tree_byte_drift": (
            "STAGE_INPUT_TREE",
            "/raw/evidence.bin",
            "OVERWRITE_FILE_BYTES",
            "NOT_APPLICABLE",
            "mutated stage bytes",
        ),
        "unsafe_stage_entry": (
            "STAGE_INPUT_TREE",
            "/raw/unsafe-link.bin",
            "CREATE_SYMLINK_WITH_FIFO_FALLBACK",
            "NOT_APPLICABLE",
            "outside-stage.bin; FIFO fallback raw/unsafe-fifo",
        ),
        "stage_tree_toc_tou": (
            "STAGE_INPUT_TREE",
            "/ku-bo-011-race-marker.bin",
            "INJECT_FILE_AFTER_FIRST_TREE_SCAN",
            "NOT_APPLICABLE",
            "inserted after first production tree scan",
        ),
        "stage_root_overlap_or_alias": (
            "VERIFIED_OUTPUT_BINDING",
            "/output_root",
            "SET_OUTPUT_ROOT_INSIDE_STAGE",
            "NOT_APPLICABLE",
            "input_root/overlapping-output",
        ),
        "stage_artifact_inventory_mismatch": (
            "STAGE_BINDING_FILE",
            "/stage_artifact/complete_file_count",
            "INCREMENT_INTEGER",
            "RESIGN_WITH_STAGE_AUTHORITY",
            "+1",
        ),
        "predecessor_binding_omission": (
            "SEMANTIC_ADMISSION_FILE",
            "/predecessor_bindings",
            "REPLACE_WITH_EMPTY_LIST",
            "RESIGN_WITH_SEMANTIC_AUTHORITY",
            "[]",
        ),
        "predecessor_binding_replay": (
            "SEMANTIC_ADMISSION_FILE",
            "/predecessor_bindings/-",
            "APPEND_COPY_OF_FIRST_ROW",
            "RESIGN_WITH_SEMANTIC_AUTHORITY",
            "copy predecessor_bindings[0]",
        ),
        "predecessor_binding_wrong_stage": (
            "SEMANTIC_ADMISSION_FILE",
            "/predecessor_bindings/0/stage_id",
            "SET_WRONG_PREDECESSOR_STAGE",
            "RESIGN_WITH_SEMANTIC_AUTHORITY",
            "WRONG_PREDECESSOR_STAGE",
        ),
        "five_security_denominator_promotion": (
            "SEMANTIC_ADMISSION_FILE",
            "/claims/denominator",
            "SET_CLAIM_VALUE",
            "RESIGN_WITH_SEMANTIC_AUTHORITY",
            "FIVE_SECURITY_COHORT",
        ),
        "full_market_claim_promotion": (
            "SEMANTIC_ADMISSION_FILE",
            "/claims/full_market",
            "SET_CLAIM_VALUE",
            "RESIGN_WITH_SEMANTIC_AUTHORITY",
            "true",
        ),
        "benchmark_fallback_promotion": (
            "SEMANTIC_ADMISSION_FILE",
            "/claims/benchmark_fallback_allowed",
            "SET_CLAIM_VALUE",
            "RESIGN_WITH_SEMANTIC_AUTHORITY",
            "true",
        ),
        "d01_policy_promotion": (
            "SEMANTIC_ADMISSION_FILE",
            "/claims/outcome_session_policy",
            "SET_CLAIM_VALUE",
            "RESIGN_WITH_SEMANTIC_AUTHORITY",
            "FROZEN_D01_APPROVED",
        ),
        "untrusted_legacy_claim_promotion": (
            "SEMANTIC_ADMISSION_FILE",
            "/claims/legacy_july",
            "SET_CLAIM_VALUE",
            "RESIGN_WITH_SEMANTIC_AUTHORITY",
            "TRUSTED_LEGACY_CLAIM",
        ),
        "output_root_preexists": (
            "ATOMIC_OUTPUT_TRANSACTION",
            "/output_root",
            "CREATE_OUTPUT_ROOT_WITH_RACER_FILE",
            "NOT_APPLICABLE",
            "racer.txt=fixture-owned output racer",
        ),
        "partial_output_on_rejection": (
            "ATOMIC_STAGING_DIRECTORY",
            "/partial.txt",
            "WRITE_STAGED_FILE_THEN_RAISE",
            "NOT_APPLICABLE",
            (
                "this partial candidate must never be published; then RuntimeError"
            ),
        ),
        "output_commit_toc_tou": (
            "ATOMIC_OUTPUT_TRANSACTION",
            "/output_root",
            "CREATE_OUTPUT_ROOT_WITH_RACER_FILE",
            "NOT_APPLICABLE",
            "racer.txt=fixture-owned output racer",
        ),
    }
)


def _materialization_contract(
    *,
    handler_id: str,
    input_channel: str,
    variant_index: int,
) -> dict[str, Any]:
    try:
        artifact, field, action, resign_policy, value = _MATERIALIZATION_BASE[
            handler_id
        ]
        ingress = _MATERIALIZATION_INGRESS[input_channel]
        timing = _MATERIALIZATION_TIMING[input_channel]
        channel_variant = _MATERIALIZATION_VARIANT[input_channel]
    except KeyError as exc:
        raise ProductionAdapterError(
            "materialization descriptor names an unsupported handler or channel"
        ) from exc
    if variant_index != channel_variant:
        raise ProductionAdapterError(
            "materialization variant differs from input channel"
        )

    if handler_id in {"missing_run_receipt", "missing_stage_binding"}:
        if variant_index < 2:
            artifact = "BOUNDARY_ADMISSION_REQUEST"
            field = (
                "/receipt_path"
                if handler_id == "missing_run_receipt"
                else "/stage_binding_path"
            )
            action = "SET_REQUEST_PATH_NONE"
        else:
            action = "DELETE_FILE"
    elif handler_id == "stage_tree_toc_tou":
        timing = "DURING_PRODUCTION_TREE_DOUBLE_SNAPSHOT"
    elif handler_id == "partial_output_on_rejection":
        timing = "INSIDE_ATOMIC_OUTPUT_WORKER_AFTER_ADMISSION"
    elif handler_id == "output_commit_toc_tou":
        timing = "PUBLIC_BOUNDARY_PRE_COMMIT_RECHECK"
        if variant_index == 2:
            artifact = "ATOMIC_STAGING_DIRECTORY"
            field = "/"
            action = "DELETE_STAGING_DIRECTORY"
            value = None

    return {
        "handler_id": handler_id,
        "ingress": ingress,
        "artifact": artifact,
        "field": field,
        "action": action,
        "timing": timing,
        "resign_policy": resign_policy,
        "value": value,
    }


def _validate_materialization_descriptor(
    descriptor: Any,
    *,
    handler_id: str,
    input_channel: str,
    variant_index: int,
) -> None:
    if not isinstance(descriptor, Mapping):
        raise ProductionAdapterError(
            "case lacks an executable materialization descriptor"
        )
    if set(descriptor) != _MATERIALIZATION_FIELDS:
        raise ProductionAdapterError(
            "materialization descriptor has unknown or missing fields"
        )
    contract = _materialization_contract(
        handler_id=handler_id,
        input_channel=input_channel,
        variant_index=variant_index,
    )
    for field in _MATERIALIZATION_FIELDS:
        supplied = descriptor[field]
        required = contract[field]
        if type(supplied) is not type(required) or supplied != required:
            raise ProductionAdapterError(
                f"materialization {field} differs from production handler contract"
            )


_AuditHook = Callable[[str, Mapping[str, str]], None]
_AUDIT_HOOK: _AuditHook | None = None


def _audit(event: str, context: _MutationContext, implementation: str) -> None:
    row = {
        "event": event,
        "boundary_id": context.boundary_id,
        "input_channel": context.input_channel,
        "implementation": implementation,
    }
    context.audit_events.append(row)
    hook = _AUDIT_HOOK
    if hook is not None:
        hook(event, MappingProxyType(dict(row)))


@contextmanager
def _cli_authorities(context: _MutationContext) -> Iterator[None]:
    values = {
        "KUBO_TRI_RUN_HMAC_KEY": f"hex:{context.cli_run_key.hex()}",
        "KUBO_TRI_RUN_HMAC_KEY_ID": context.cli_run_key_id,
        "KUBO_TRI_STAGE_HMAC_KEY": f"hex:{context.cli_stage_key.hex()}",
        "KUBO_TRI_STAGE_HMAC_KEY_ID": context.cli_stage_key_id,
        "KUBO_TRI_SEMANTIC_HMAC_KEY": f"hex:{context.cli_semantic_key.hex()}",
        "KUBO_TRI_SEMANTIC_HMAC_KEY_ID": context.cli_semantic_key_id,
    }
    previous = {name: os.environ.get(name) for name in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _cli_arguments(context: _MutationContext) -> list[str]:
    request = context.request
    inputs = request.boundary_inputs
    project_root = (
        inputs["project_root"]
        if context.boundary_id == "build_data_foundation_packet"
        else _config_dir().parent
    )
    arguments = [
        "--project-root",
        str(project_root),
        _BOUNDARY_COMMANDS[context.boundary_id],
    ]
    if context.boundary_id == "import_user_price_exports":
        arguments.extend(
            (
                "--input-dir",
                str(inputs["input_dir"]),
                "--output-root",
                str(context.gate_output_root),
                "--observed-at",
                str(context.operation_binding["arguments"]["observed_at"]),
            )
        )
    elif context.boundary_id == "import_official_foundation":
        arguments.extend(
            (
                "--workspace",
                str(inputs["workspace"]),
                "--output-root",
                str(context.gate_output_root),
            )
        )
    elif context.boundary_id in {
        "import_status_corporate",
        "import_ca_enrichment",
        "import_status_history",
    }:
        upstream_role = (
            "official_foundation_root"
            if context.boundary_id == "import_status_corporate"
            else "status_corporate_root"
        )
        arguments.extend(
            (
                f"--{upstream_role.replace('_', '-')}",
                str(inputs[upstream_role]),
                "--workspace",
                str(inputs["workspace"]),
                "--output-root",
                str(context.gate_output_root),
            )
        )
    elif context.boundary_id == "import_benchmark_history":
        arguments.extend(
            (
                "--official-foundation-root",
                str(inputs["official_foundation_root"]),
                "--workspace",
                str(inputs["workspace"]),
                "--output-root",
                str(context.gate_output_root),
                "--imported-at",
                str(context.operation_binding["arguments"]["imported_at"]),
            )
        )
    elif context.boundary_id == "import_official_eod":
        arguments.extend(
            (
                "--workspace",
                str(inputs["workspace_root"]),
                "--official-foundation-root",
                str(inputs["official_foundation_root"]),
                "--status-history-root",
                str(inputs["status_history_root"]),
                "--output-root",
                str(context.gate_output_root),
                "--run-id",
                str(context.operation_binding["arguments"]["run_id"]),
                "--imported-at",
                str(context.operation_binding["arguments"]["imported_at"]),
            )
        )
    elif context.boundary_id == "build_data_foundation_packet":
        for role in (
            "official_foundation_root",
            "status_history_root",
            "ca_enrichment_root",
            "research_price_history_root",
            "benchmark_root",
            "official_eod_root",
        ):
            arguments.extend(
                (f"--{role.replace('_', '-')}", str(inputs[role]))
            )
        arguments.extend(
            (
                "--output-root",
                str(context.gate_output_root),
                "--outcome-session-policy",
                str(inputs["outcome_session_policy_path"]),
            )
        )
    else:  # pragma: no cover - guarded by public input validation
        raise ProductionAdapterError(
            f"unsupported production boundary: {context.boundary_id}"
        )
    arguments.extend(("--admission-path", str(request.admission_path)))
    if request.receipt_path is not None:
        arguments.extend(("--receipt-path", str(request.receipt_path)))
    if request.stage_binding_path is not None:
        arguments.extend(("--stage-binding-path", str(request.stage_binding_path)))
    arguments.extend(
        (
            "--workspace-root",
            str(request.workspace_root),
            "--input-root",
            str(request.input_root),
            "--expected-batch-plan-sha256",
            request.expected_batch_plan_sha256,
            "--expected-scoped-config-manifest-sha256",
            request.expected_scoped_config_manifest_sha256,
            "--expected-stage-manifest-sha256",
            request.expected_stage_manifest_sha256,
            "--decision-at",
            request.decision_at,
            "--expected-run-id",
            request.expected_run_id,
            "--expected-batch-id",
            request.expected_batch_id,
        )
    )
    for path in request.predecessor_admission_paths:
        arguments.extend(("--predecessor-admission", str(path)))
    return arguments


def _cli_boundary_inputs(
    context: _MutationContext,
    args: Any,
) -> dict[str, Path]:
    boundary_id = context.boundary_id
    if boundary_id == "import_user_price_exports":
        return {"config_dir": args.project_root / "config", "input_dir": args.input_dir}
    if boundary_id == "import_official_foundation":
        return {"config_dir": args.project_root / "config", "workspace": args.workspace}
    if boundary_id == "import_status_corporate":
        return {
            "official_foundation_root": args.official_foundation_root,
            "workspace": args.workspace,
        }
    if boundary_id in {"import_ca_enrichment", "import_status_history"}:
        return {
            "status_corporate_root": args.status_corporate_root,
            "workspace": args.workspace,
        }
    if boundary_id == "import_benchmark_history":
        return {
            "config_dir": args.project_root / "config",
            "official_foundation_root": args.official_foundation_root,
            "workspace": args.workspace,
        }
    if boundary_id == "import_official_eod":
        return {
            "workspace_root": args.workspace,
            "official_foundation_root": args.official_foundation_root,
            "status_history_root": args.status_history_root,
        }
    if boundary_id == "build_data_foundation_packet":
        return {
            "official_foundation_root": args.official_foundation_root,
            "status_history_root": args.status_history_root,
            "ca_enrichment_root": args.ca_enrichment_root,
            "research_price_history_root": args.research_price_history_root,
            "benchmark_root": args.benchmark_root,
            "official_eod_root": args.official_eod_root,
            "project_root": args.project_root,
            "outcome_session_policy_path": args.outcome_session_policy,
        }
    raise ProductionAdapterError(f"unsupported production boundary: {boundary_id}")


def _public_boundary_arguments(context: _MutationContext) -> dict[str, Any]:
    """Build the exact keyword surface of the named production boundary."""

    inputs = context.request.boundary_inputs
    operation = context.operation_binding
    operation_arguments = operation["arguments"]
    common = {
        "output_root": context.gate_output_root,
        "admission_request": context.request,
    }
    if context.boundary_id == "import_user_price_exports":
        return {
            **common,
            "config_dir": inputs["config_dir"],
            "input_dir": inputs["input_dir"],
            "observed_at": operation_arguments["observed_at"],
            "decision_at": operation["decision_at"],
        }
    if context.boundary_id == "import_official_foundation":
        return {
            **common,
            "config_dir": inputs["config_dir"],
            "workspace": inputs["workspace"],
        }
    if context.boundary_id == "import_status_corporate":
        return {
            **common,
            "config_dir": _config_dir(),
            "official_foundation_root": inputs["official_foundation_root"],
            "workspace": inputs["workspace"],
        }
    if context.boundary_id == "import_ca_enrichment":
        return {
            **common,
            "status_corporate_root": inputs["status_corporate_root"],
            "workspace": inputs["workspace"],
        }
    if context.boundary_id == "import_status_history":
        return {
            **common,
            "status_corporate_root": inputs["status_corporate_root"],
            "workspace": inputs["workspace"],
        }
    if context.boundary_id == "import_benchmark_history":
        return {
            **common,
            "config_dir": inputs["config_dir"],
            "official_foundation_root": inputs["official_foundation_root"],
            "workspace": inputs["workspace"],
            "imported_at": operation_arguments["imported_at"],
        }
    if context.boundary_id == "import_official_eod":
        return {
            **common,
            "workspace_root": inputs["workspace_root"],
            "official_foundation_root": inputs["official_foundation_root"],
            "status_history_root": inputs["status_history_root"],
            "run_id": operation_arguments["run_id"],
            "imported_at": operation_arguments["imported_at"],
            "runtime_trust_registry": None,
        }
    if context.boundary_id == "build_data_foundation_packet":
        return {
            **common,
            "official_foundation_root": inputs["official_foundation_root"],
            "status_history_root": inputs["status_history_root"],
            "ca_enrichment_root": inputs["ca_enrichment_root"],
            "research_price_history_root": inputs["research_price_history_root"],
            "benchmark_root": inputs["benchmark_root"],
            "official_eod_root": inputs["official_eod_root"],
            "project_root": inputs["project_root"],
            "outcome_session_policy_path": inputs["outcome_session_policy_path"],
        }
    raise ProductionAdapterError(
        f"unsupported production boundary: {context.boundary_id}"
    )


def _invoke_public_boundary(
    context: _MutationContext,
    *,
    serialized: bool = False,
    before_commit_mutation: Callable[[_MutationContext], None] | None = None,
    partial_worker_failure: bool = False,
) -> Any:
    """Invoke the named importer while retaining its real gate/atomic flow.

    The adapter replaces only the domain-specific normalization body with a
    minimal candidate writer.  Admission, sidecar/lineage publication,
    pre-commit revalidation, staging cleanup, and the public boundary itself
    remain the production implementations under test.
    """

    module = _BOUNDARY_MODULES[context.boundary_id]
    public = getattr(module, _BOUNDARY_FUNCTION_NAMES[context.boundary_id])
    unchecked_name = _UNCHECKED_FUNCTION_NAMES[context.boundary_id]
    original_atomic = module.run_atomic_output
    original_admit = (
        admission.admit_serialized_boundary
        if serialized
        else admission.admit_boundary
    )
    original_scan = foundation_io._scan_regular_tree_once
    tree_race_injected = False

    def candidate_worker(**kwargs: Any) -> dict[str, Any]:
        staging = Path(kwargs["output_root"])
        (staging / "reports").mkdir(exist_ok=True)
        (staging / "adapter_candidate.txt").write_text(
            "candidate output guarded by the public KU-BO-011 boundary\n",
            encoding="utf-8",
        )
        if partial_worker_failure:
            _audit("mutation", context, "_partial_output_on_rejection")
            raise RuntimeError("fixture worker rejected its partial candidate")
        return {"status": "KU_BO_011_ADAPTER_CANDIDATE"}

    def instrumented_atomic(
        target: str | os.PathLike[str],
        worker: Callable[[Path], Any],
        before_commit: Callable[[Path], None] | None = None,
    ) -> Any:
        def instrumented_before_commit(staging: Path) -> None:
            context.atomic_staging = staging
            if before_commit_mutation is not None:
                _audit("mutation", context, before_commit_mutation.__name__)
                before_commit_mutation(context)
            if before_commit is not None:
                before_commit(staging)

        return original_atomic(
            target,
            worker,
            before_commit=instrumented_before_commit,
            failure_phase=_channel_phase(context),
        )

    def capturing_admit(*args: Any, **kwargs: Any) -> Any:
        token = original_admit(*args, **kwargs)
        context.active_token = token
        return token

    def instrumented_scan(*args: Any, **kwargs: Any) -> Any:
        nonlocal tree_race_injected
        snapshot = original_scan(*args, **kwargs)
        root = Path(args[0] if args else kwargs["root"])
        if (
            context.deterministic_tree_race
            and not tree_race_injected
            and root.absolute() == context.request.input_root.absolute()
        ):
            tree_race_injected = True
            (root / "ku-bo-011-race-marker.bin").write_bytes(
                b"inserted after the first production tree scan"
            )
        return snapshot

    admission_patch_target = (
        admission
        if context.boundary_id == "build_data_foundation_packet"
        else module
    )
    _audit(
        "public_boundary",
        context,
        f"{module.__name__}.{_BOUNDARY_FUNCTION_NAMES[context.boundary_id]}",
    )
    with ExitStack() as stack:
        stack.enter_context(
            patch.object(module, unchecked_name, side_effect=candidate_worker)
        )
        stack.enter_context(
            patch.object(
                module,
                "run_atomic_output",
                side_effect=instrumented_atomic,
            )
        )
        stack.enter_context(
            patch.object(
                admission_patch_target,
                "admit_boundary",
                side_effect=capturing_admit,
            )
        )
        stack.enter_context(
            patch.object(
                foundation_io,
                "_scan_regular_tree_once",
                side_effect=instrumented_scan,
            )
        )
        return public(**_public_boundary_arguments(context))


def _cli_gate(
    context: _MutationContext,
    *,
    before_commit_mutation: Callable[[_MutationContext], None] | None = None,
    partial_worker_failure: bool = False,
) -> Any:
    _audit("channel_gate", context, "data_foundation_cli.parser+public_boundary")
    with _cli_authorities(context):
        args = data_foundation_cli.parser().parse_args(_cli_arguments(context))
        run_key, run_key_id = data_foundation_cli._runtime_tri_run_hmac()
        stage_key, stage_key_id = data_foundation_cli._runtime_tri_stage_hmac()
        semantic_key, semantic_key_id = data_foundation_cli._runtime_tri_semantic_hmac()
    inputs = _cli_boundary_inputs(context, args)
    operation = data_foundation_cli._command_operation_binding(
        args,
        context.boundary_id,
    )
    request = admission.BoundaryAdmissionRequest(
        admission_path=args.admission_path,
        receipt_path=args.receipt_path,
        stage_binding_path=args.stage_binding_path,
        workspace_root=args.workspace_root,
        input_root=args.input_root,
        expected_batch_plan_sha256=args.expected_batch_plan_sha256,
        expected_scoped_config_manifest_sha256=(
            args.expected_scoped_config_manifest_sha256
        ),
        expected_stage_manifest_sha256=args.expected_stage_manifest_sha256,
        decision_at=args.decision_at,
        expected_run_id=args.expected_run_id,
        expected_batch_id=args.expected_batch_id,
        run_key=run_key,
        run_key_id=run_key_id,
        v1_stage_key=stage_key,
        v1_stage_key_id=stage_key_id,
        semantic_key=semantic_key,
        semantic_key_id=semantic_key_id,
        boundary_inputs=inputs,
        operation_binding=operation,
        predecessor_admission_paths=tuple(args.predecessor_admission_paths),
    )
    context.request = request
    context.operation_binding = operation
    return _invoke_public_boundary(
        context,
        before_commit_mutation=before_commit_mutation,
        partial_worker_failure=partial_worker_failure,
    )


def _direct_gate(
    context: _MutationContext,
    *,
    before_commit_mutation: Callable[[_MutationContext], None] | None = None,
    partial_worker_failure: bool = False,
) -> Any:
    _audit("channel_gate", context, "public_boundary+admit_boundary")
    return _invoke_public_boundary(
        context,
        before_commit_mutation=before_commit_mutation,
        partial_worker_failure=partial_worker_failure,
    )


def _serialized_gate(
    context: _MutationContext,
    *,
    before_commit_mutation: Callable[[_MutationContext], None] | None = None,
    partial_worker_failure: bool = False,
) -> Any:
    _audit("channel_gate", context, "public_boundary+admit_serialized_boundary")
    return _invoke_public_boundary(
        context,
        serialized=True,
        before_commit_mutation=before_commit_mutation,
        partial_worker_failure=partial_worker_failure,
    )


def _gate(
    context: _MutationContext,
    *,
    before_commit_mutation: Callable[[_MutationContext], None] | None = None,
    partial_worker_failure: bool = False,
) -> Any:
    if context.input_channel == "CLI_ARGUMENT":
        return _cli_gate(
            context,
            before_commit_mutation=before_commit_mutation,
            partial_worker_failure=partial_worker_failure,
        )
    if context.input_channel in {"DIRECT_API_OBJECT", "FILESYSTEM_RACE"}:
        return _direct_gate(
            context,
            before_commit_mutation=before_commit_mutation,
            partial_worker_failure=partial_worker_failure,
        )
    if context.input_channel == "SERIALIZED_ARTIFACT":
        return _serialized_gate(
            context,
            before_commit_mutation=before_commit_mutation,
            partial_worker_failure=partial_worker_failure,
        )
    raise ProductionAdapterError(
        f"unsupported production input channel: {context.input_channel}"
    )


def _channel_phase(context: _MutationContext) -> str:
    if context.input_channel == "SERIALIZED_ARTIFACT":
        return atomic_output.ARTIFACT_VALIDATION_PRE_WRITE
    if context.input_channel == "FILESYSTEM_RACE":
        return atomic_output.PRE_COMMIT_RECHECK
    return atomic_output.ENTRY_PRE_WRITE


def _materialize_candidate_output(
    context: _MutationContext,
    token: admission.VerifiedBoundaryAdmission,
    staging: Path,
) -> None:
    (staging / "reports").mkdir()
    (staging / "adapter_candidate.txt").write_text(
        "candidate output guarded by KU-BO-011 admission\n",
        encoding="utf-8",
    )
    token.materialize_receipt(staging)
    token.materialize_lineage(staging)


def _atomic_revalidation(
    context: _MutationContext,
    token: admission.VerifiedBoundaryAdmission,
    handler: Callable[[_MutationContext], None],
) -> None:
    _audit("atomic_output", context, "run_atomic_output")

    def worker(staging: Path) -> None:
        _materialize_candidate_output(context, token, staging)

    def before_commit(staging: Path) -> None:
        context.atomic_staging = staging
        _audit("mutation", context, handler.__name__)
        handler(context)
        token.revalidate_before_commit()

    atomic_output.run_atomic_output(
        context.gate_output_root,
        worker,
        before_commit,
        failure_phase=_channel_phase(context),
    )


def _partial_output_rejection(
    context: _MutationContext,
    token: admission.VerifiedBoundaryAdmission,
) -> None:
    del token
    _audit("atomic_output", context, "run_atomic_output")

    def worker(staging: Path) -> None:
        (staging / "partial.txt").write_text(
            "this partial candidate must never be published\n",
            encoding="utf-8",
        )
        raise RuntimeError("fixture worker rejected its partial output")

    atomic_output.run_atomic_output(
        context.gate_output_root,
        worker,
        failure_phase=_channel_phase(context),
    )


def _execute(context: _MutationContext) -> None:
    handler = _MUTATION_HANDLERS[context.mutation_id]
    if context.mutation_id == "output_root_preexists":
        if context.input_channel == "FILESYSTEM_RACE":
            _gate(context, before_commit_mutation=handler)
        else:
            _audit("mutation", context, handler.__name__)
            handler(context)
            _gate(context)
        return
    if context.mutation_id == "partial_output_on_rejection":
        _gate(context, partial_worker_failure=True)
        return
    if context.mutation_id == "output_commit_toc_tou":
        _gate(context, before_commit_mutation=handler)
        return
    if context.input_channel == "FILESYSTEM_RACE":
        _gate(context, before_commit_mutation=handler)
        return
    _audit("mutation", context, handler.__name__)
    handler(context)
    _gate(context)


def _stop_race(context: _MutationContext) -> None:
    if context.race_stop is not None:
        context.race_stop.set()
    if context.race_thread is not None:
        context.race_thread.join(timeout=5)
        if context.race_thread.is_alive():
            raise ProductionAdapterError("stage-tree race thread did not stop")


def _remove_entry(path: Path) -> None:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return
    if path.is_symlink() or not path.is_dir():
        path.unlink()
        return
    del metadata
    shutil.rmtree(path)


def _restore_case_surface(context: _MutationContext) -> None:
    _stop_race(context)
    for child in tuple(context.case_root.iterdir()):
        if child == context.input_root:
            for input_child in tuple(context.input_root.iterdir()):
                _remove_entry(input_child)
        else:
            _remove_entry(child)


def _output_writes(output_root: Path) -> list[str]:
    if not output_root.exists() and not output_root.is_symlink():
        return []
    if output_root.is_symlink() or output_root.is_file():
        return [output_root.name]
    return sorted(
        path.relative_to(output_root).as_posix()
        for path in output_root.rglob("*")
    )


def production_adapter(
    *,
    case: Mapping[str, Any],
    case_root: Path,
    input_root: Path,
    output_root: Path,
) -> Mapping[str, Any]:
    """Execute one supplied attack against the installed production gates."""

    boundary = case.get("boundary")
    mutation = case.get("mutation")
    context_row = case.get("context")
    if not isinstance(boundary, Mapping) or not isinstance(mutation, Mapping):
        raise ProductionAdapterError("case boundary and mutation must be objects")
    if not isinstance(context_row, Mapping):
        raise ProductionAdapterError("case context must be an object")
    case_id = case.get("case_id")
    boundary_id = boundary.get("id")
    mutation_id = mutation.get("id")
    input_channel = mutation.get("input_channel")
    variant_index = mutation.get("variant_index")
    if not isinstance(case_id, str) or not case_id:
        raise ProductionAdapterError("case_id must be a non-empty string")
    if boundary_id not in admission.BOUNDARY_STAGE_MAP:
        raise ProductionAdapterError(f"unsupported production boundary: {boundary_id!r}")
    if mutation_id not in _MUTATION_HANDLERS:
        raise ProductionAdapterError(f"unsupported production mutation: {mutation_id!r}")
    if input_channel not in {
        "CLI_ARGUMENT",
        "DIRECT_API_OBJECT",
        "SERIALIZED_ARTIFACT",
        "FILESYSTEM_RACE",
    }:
        raise ProductionAdapterError(f"unsupported input channel: {input_channel!r}")
    if isinstance(variant_index, bool) or not isinstance(variant_index, int):
        raise ProductionAdapterError("variant_index must be an integer")
    target_run_id = context_row.get("target_run_id")
    decision_at = context_row.get("evaluation_time")
    if not isinstance(target_run_id, str) or not isinstance(decision_at, str):
        raise ProductionAdapterError("case run id and evaluation time are required")

    _validate_materialization_descriptor(
        case.get("materialization"),
        handler_id=mutation_id,
        input_channel=input_channel,
        variant_index=variant_index,
    )

    protected_case_root = Path(case_root).absolute()
    protected_input = Path(input_root).absolute()
    protected_output = Path(output_root).absolute()
    if protected_input.parent != protected_case_root or protected_output.parent != protected_case_root:
        raise ProductionAdapterError("protected input and output must be direct case-root children")

    captured: Exception | None = None
    adapter_context: _MutationContext | None = None
    try:
        with tempfile.TemporaryDirectory(prefix="ku-bo-011-production-") as temp_name:
            materializer = _BaselineMaterializer(
                case_root=Path(temp_name),
                target_input_root=protected_input,
                target_boundary_id=boundary_id,
                run_id=target_run_id,
                decision_at=decision_at,
            )
            issued = materializer.issued[boundary_id]
            request = materializer.request(boundary_id)
            adapter_context = _MutationContext(
                case=case,
                case_root=protected_case_root,
                input_root=protected_input,
                protected_output_root=protected_output,
                gate_output_root=protected_output,
                boundary_id=boundary_id,
                mutation_id=mutation_id,
                variant_index=variant_index,
                input_channel=input_channel,
                materializer=materializer,
                issued=issued,
                request=request,
                operation_binding=request.operation_binding,
                cli_run_key=materializer.run_key,
                cli_run_key_id=_RUN_KEY_ID,
                cli_stage_key=materializer.stage_key,
                cli_stage_key_id=_STAGE_KEY_ID,
                cli_semantic_key=materializer.semantic_key,
                cli_semantic_key_id=_SEMANTIC_KEY_ID,
            )
            try:
                _execute(adapter_context)
            except Exception as exc:
                captured = exc
            else:
                raise ProductionAdapterError(
                    f"production accepted mutation {mutation_id!r} for {boundary_id!r}"
                )
    finally:
        if adapter_context is not None:
            _restore_case_surface(adapter_context)

    if captured is None:
        raise ProductionAdapterError("production rejection was not captured")
    failure_code = getattr(captured, "failure_code", None)
    failure_phase = getattr(captured, "failure_phase", None)
    if not isinstance(failure_code, str) or not isinstance(failure_phase, str):
        raise ProductionAdapterError(
            "production rejection lacks stable failure_code/failure_phase: "
            f"{type(captured).__name__}: {captured}"
        ) from captured
    writes = _output_writes(protected_output)
    events = tuple(dict(row) for row in adapter_context.audit_events)
    authority_digests = tuple(
        hashlib.sha256(key).hexdigest()
        for key in (
            adapter_context.materializer.run_key,
            adapter_context.materializer.stage_key,
            adapter_context.materializer.semantic_key,
        )
    )
    return {
        "case_id": case_id,
        "decision": "REJECT",
        "failure_code": failure_code,
        "failure_phase": failure_phase,
        "output_writes": writes,
        "dispatch_proof": {
            "schema_version": "ku-bo-011-dispatch-proof-v1",
            "boundary_id": boundary_id,
            "input_channel": input_channel,
            "mutation_id": mutation_id,
            "public_boundary": (
                f"{_BOUNDARY_MODULES[boundary_id].__name__}."
                f"{_BOUNDARY_FUNCTION_NAMES[boundary_id]}"
            ),
            "rejection_type": (
                f"{type(captured).__module__}.{type(captured).__qualname__}"
            ),
            "authority_key_sha256": authority_digests,
            "events": events,
            "events_sha256": sha256_bytes(canonical_json_bytes(events)),
        },
    }


run_production_case = production_adapter


__all__ = ["production_adapter", "run_production_case"]
