from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

from .data_foundation_reconciliation import GATE_ORDER
from .foundation_io import (
    load_strict_json_object,
    positive_int,
    prepare_output_root,
    safe_regular_file,
)
from .hashing import canonical_json_bytes, hash_json, sha256_bytes
from .strict import parse_iso_date
from .vendor_symbol_mapping import (
    VendorSymbolMapping,
    _valid_isin,
    _vendor_mapping,
)


TRI_SECURITY_REGISTRY_SCHEMA_VERSION = "1.0"
TRI_SECURITY_WORKSPACE_SCHEMA_VERSION = "1.0"
TRI_SECURITY_MODE = "DATA_QUALIFICATION_ONLY"
TRI_SECURITY_SCOPE = "STAGED_TRI_SECURITY_DATA_QUALIFICATION"
TRI_SECURITY_BATCH_SIZE = 3
TRI_SECURITY_CLAIM_BOUNDARY = "CONFIGURATION_ONLY_NOT_MARKET_EVIDENCE"
TRI_SECURITY_ALLOWED_OUTPUT = "DATA_QUALIFICATION_REPORT_ONLY"
TRI_SECURITY_MAPPING_SCHEMA_VERSION = "1.0"

_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_REGISTRY_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_BATCH_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_SECURITY_CODE_RE = re.compile(r"^[0-9]{1,12}$")
_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9]{0,31}$")
_CASE_TAG_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")

_REQUIRED_EVIDENCE: dict[str, tuple[str, ...]] = {
    "POINT_IN_TIME_IDENTITY": (
        "effective-dated official security identity bytes and hashes",
    ),
    "TRADING_CALENDAR": (
        "official session calendar covering the declared test window",
    ),
    "SECURITY_STATUS_HISTORY": (
        "official suspension, resumption, listing, and delisting evidence",
    ),
    "PRICE_DENOMINATOR": (
        "one explicit security-session state for every eligible pair",
    ),
    "PRICE_EVIDENCE": (
        "hash-bound authorized price history and official EOD receipts",
    ),
    "PRICE_CORPORATE_ACTION_QA": (
        "official corporate-action schedule, factors, and return policy",
    ),
    "BENCHMARK_HISTORY": (
        "session-complete benchmark history with an explicit calculation basis",
    ),
    "BENCHMARK_EVIDENCE": (
        "authorized benchmark bytes, rights metadata, and capture receipts",
    ),
    "MARKET_TOTAL_RECONCILIATION": (
        "official market totals or an explicit source-unavailable receipt",
    ),
    "QUERY_AND_PAGINATION_COMPLETENESS": (
        "query, page, result-count, and zero-result receipts",
    ),
    "RUNTIME_SECRET_GUARD": (
        "runtime-only credentials and an independently authenticated trust registry",
    ),
    "CLAIM_BOUNDARIES": (
        "final independent gate report preserving all non-claims",
    ),
}


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    if any(character in value for character in ("\x00", "\r", "\n")):
        raise ValueError(f"{field} must be single-line text")
    normalized = value.strip()
    return normalized


@dataclass(frozen=True)
class TriSecurityCandidate:
    security_code: str
    ticker: str
    name_en: str
    name_ar: str
    isin: str
    sector: str
    identity_state: str
    case_tags: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "security_code": self.security_code,
            "ticker": self.ticker,
            "name_en": self.name_en,
            "name_ar": self.name_ar,
            "isin": self.isin,
            "sector": self.sector,
            "identity_state": self.identity_state,
            "case_tags": list(self.case_tags),
        }


@dataclass(frozen=True)
class TriSecurityBatch:
    batch_id: str
    sequence: int
    status: str
    purpose: str
    allowed_output: str
    securities: tuple[TriSecurityCandidate, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "sequence": self.sequence,
            "status": self.status,
            "purpose": self.purpose,
            "allowed_output": self.allowed_output,
            "securities": [security.to_dict() for security in self.securities],
        }


@dataclass(frozen=True)
class TriSecurityRegistry:
    registry_id: str
    as_of: str
    batches: tuple[TriSecurityBatch, ...]
    source_bytes: bytes

    @property
    def sha256(self) -> str:
        return sha256_bytes(self.source_bytes)

    @property
    def execution_order(self) -> tuple[str, ...]:
        return tuple(batch.batch_id for batch in self.batches)

    def batch(self, batch_id: str) -> TriSecurityBatch:
        matches = [batch for batch in self.batches if batch.batch_id == batch_id]
        if not matches:
            raise ValueError(f"unknown tri-security batch_id: {batch_id}")
        return matches[0]

    def predecessor(self, batch: TriSecurityBatch) -> str | None:
        if batch.sequence == 1:
            return None
        return self.batches[batch.sequence - 2].batch_id

    def report(self) -> dict[str, Any]:
        return {
            "schema_version": TRI_SECURITY_REGISTRY_SCHEMA_VERSION,
            "status": "PASS",
            "readiness_status": "CONFIG_VALID_EXTERNAL_EVIDENCE_REQUIRED",
            "mode": TRI_SECURITY_MODE,
            "registry_id": self.registry_id,
            "registry_sha256": self.sha256,
            "as_of": self.as_of,
            "batch_size": TRI_SECURITY_BATCH_SIZE,
            "batch_count": len(self.batches),
            "security_count": sum(len(batch.securities) for batch in self.batches),
            "execution_order": list(self.execution_order),
            "required_gates": list(GATE_ORDER),
            "batches": [
                {
                    "batch_id": batch.batch_id,
                    "sequence": batch.sequence,
                    "status": batch.status,
                    "tickers": [security.ticker for security in batch.securities],
                    "predecessor_batch_id": self.predecessor(batch),
                }
                for batch in self.batches
            ],
            "claim_boundaries": {
                "configuration_valid": True,
                "seed_identity_is_official_evidence": False,
                "market_data_collected": False,
                "batch_passed_data_qualification": False,
                "three_security_batch_validates_full_market": False,
                "backtest_ready": False,
                "forecast_generated": False,
                "probability_generated": False,
                "recommendation_generated": False,
            },
        }


@dataclass(frozen=True)
class TriSecurityVendorMappings:
    registry_id: str
    as_of: str
    mappings: tuple[VendorSymbolMapping, ...]
    source_bytes: bytes

    @property
    def sha256(self) -> str:
        return sha256_bytes(self.source_bytes)

    def for_batch(self, batch: TriSecurityBatch) -> tuple[VendorSymbolMapping, ...]:
        wanted = {security.ticker for security in batch.securities}
        selected = tuple(
            mapping for mapping in self.mappings if mapping.ticker in wanted
        )
        if {mapping.ticker for mapping in selected} != wanted:
            raise ValueError(f"tri-security vendor mappings are incomplete for {batch.batch_id}")
        return selected


def _candidate(row: Any, *, batch_index: int, security_index: int) -> TriSecurityCandidate:
    field = f"batches[{batch_index}].securities[{security_index}]"
    expected = {
        "security_code",
        "ticker",
        "name_en",
        "name_ar",
        "isin",
        "sector",
        "identity_state",
        "case_tags",
    }
    if not isinstance(row, dict) or set(row) != expected:
        raise ValueError(f"{field} has unknown or missing fields")
    security_code = _required_text(row["security_code"], f"{field}.security_code")
    ticker = _required_text(row["ticker"], f"{field}.ticker")
    isin = _required_text(row["isin"], f"{field}.isin")
    if not _SECURITY_CODE_RE.fullmatch(security_code):
        raise ValueError(f"{field}.security_code is invalid")
    if not _TICKER_RE.fullmatch(ticker):
        raise ValueError(f"{field}.ticker is invalid")
    if not _valid_isin(isin):
        raise ValueError(f"{field}.isin is invalid")
    if row["identity_state"] != "UNVERIFIED_SEED":
        raise ValueError(
            f"{field}.identity_state must remain UNVERIFIED_SEED until raw official evidence is imported"
        )
    raw_tags = row["case_tags"]
    if not isinstance(raw_tags, list) or not raw_tags:
        raise ValueError(f"{field}.case_tags must be a non-empty list")
    tags: list[str] = []
    for index, value in enumerate(raw_tags):
        tag = _required_text(value, f"{field}.case_tags[{index}]")
        if not _CASE_TAG_RE.fullmatch(tag):
            raise ValueError(f"{field}.case_tags[{index}] is invalid")
        tags.append(tag)
    if len(tags) != len(set(tags)):
        raise ValueError(f"{field}.case_tags contains duplicates")
    return TriSecurityCandidate(
        security_code=security_code,
        ticker=ticker,
        name_en=_required_text(row["name_en"], f"{field}.name_en"),
        name_ar=_required_text(row["name_ar"], f"{field}.name_ar"),
        isin=isin,
        sector=_required_text(row["sector"], f"{field}.sector"),
        identity_state="UNVERIFIED_SEED",
        case_tags=tuple(tags),
    )


def _batch(row: Any, *, batch_index: int) -> TriSecurityBatch:
    field = f"batches[{batch_index}]"
    expected = {
        "batch_id",
        "sequence",
        "status",
        "purpose",
        "allowed_output",
        "securities",
    }
    if not isinstance(row, dict) or set(row) != expected:
        raise ValueError(f"{field} has unknown or missing fields")
    batch_id = _required_text(row["batch_id"], f"{field}.batch_id")
    if not _BATCH_ID_RE.fullmatch(batch_id):
        raise ValueError(f"{field}.batch_id is invalid")
    if isinstance(row["sequence"], bool) or not isinstance(row["sequence"], int):
        raise ValueError(f"{field}.sequence must be a positive integer")
    sequence = positive_int(row["sequence"], f"{field}.sequence")
    if row["status"] != "CONFIGURED_FOR_WORKSPACE_PREPARATION":
        raise ValueError(f"{field}.status is invalid")
    if row["allowed_output"] != TRI_SECURITY_ALLOWED_OUTPUT:
        raise ValueError(f"{field}.allowed_output is invalid")
    raw_securities = row["securities"]
    if not isinstance(raw_securities, list) or len(raw_securities) != TRI_SECURITY_BATCH_SIZE:
        raise ValueError(
            f"{field}.securities must contain exactly {TRI_SECURITY_BATCH_SIZE} rows"
        )
    return TriSecurityBatch(
        batch_id=batch_id,
        sequence=sequence,
        status="CONFIGURED_FOR_WORKSPACE_PREPARATION",
        purpose=_required_text(row["purpose"], f"{field}.purpose"),
        allowed_output=TRI_SECURITY_ALLOWED_OUTPUT,
        securities=tuple(
            _candidate(
                candidate,
                batch_index=batch_index,
                security_index=security_index,
            )
            for security_index, candidate in enumerate(raw_securities)
        ),
    )


def load_tri_security_registry(config_dir: Path) -> TriSecurityRegistry:
    path = Path(config_dir) / "pilot" / "tri_security_batches.json"
    payload, content = load_strict_json_object(
        path,
        field="tri-security pilot registry",
    )
    expected = {
        "schema_version",
        "registry_id",
        "as_of",
        "scope",
        "batch_size",
        "execution_order",
        "claim_boundary",
        "required_gates",
        "batches",
    }
    if set(payload) != expected:
        raise ValueError("tri-security pilot registry has unknown or missing fields")
    if payload["schema_version"] != TRI_SECURITY_REGISTRY_SCHEMA_VERSION:
        raise ValueError("tri-security pilot registry has unsupported schema_version")
    registry_id = _required_text(payload["registry_id"], "registry_id")
    if not _REGISTRY_ID_RE.fullmatch(registry_id):
        raise ValueError("registry_id is invalid")
    as_of = parse_iso_date(payload["as_of"], "as_of").isoformat()
    if payload["scope"] != TRI_SECURITY_SCOPE:
        raise ValueError("tri-security pilot registry has invalid scope")
    if payload["batch_size"] != TRI_SECURITY_BATCH_SIZE:
        raise ValueError("tri-security pilot batch_size must be exactly 3")
    if payload["claim_boundary"] != TRI_SECURITY_CLAIM_BOUNDARY:
        raise ValueError("tri-security pilot claim_boundary is invalid")
    if payload["required_gates"] != list(GATE_ORDER):
        raise ValueError("tri-security pilot required_gates must match the final gate order")
    raw_batches = payload["batches"]
    if not isinstance(raw_batches, list) or not raw_batches:
        raise ValueError("tri-security pilot batches must be a non-empty list")
    batches = tuple(
        _batch(row, batch_index=index) for index, row in enumerate(raw_batches)
    )
    expected_sequences = list(range(1, len(batches) + 1))
    if [batch.sequence for batch in batches] != expected_sequences:
        raise ValueError("tri-security pilot batch sequences must be contiguous and ordered")
    batch_ids = [batch.batch_id for batch in batches]
    if len(batch_ids) != len(set(batch_ids)):
        raise ValueError("tri-security pilot contains duplicate batch_id values")
    if payload["execution_order"] != batch_ids:
        raise ValueError("tri-security pilot execution_order does not match batch sequence")

    securities = [security for batch in batches for security in batch.securities]
    for field, values in (
        ("security_code", [security.security_code for security in securities]),
        ("ticker", [security.ticker for security in securities]),
        ("isin", [security.isin for security in securities]),
    ):
        if len(values) != len(set(values)):
            raise ValueError(f"tri-security pilot contains duplicate {field} values")
    return TriSecurityRegistry(
        registry_id=registry_id,
        as_of=as_of,
        batches=batches,
        source_bytes=content,
    )


def load_tri_security_vendor_mappings(
    config_dir: Path,
    registry: TriSecurityRegistry,
) -> TriSecurityVendorMappings:
    path = Path(config_dir) / "pilot" / "tri_security_vendor_mappings.json"
    payload, content = load_strict_json_object(
        path,
        field="tri-security vendor mappings",
    )
    expected = {
        "schema_version",
        "registry_id",
        "as_of",
        "scope",
        "claim_boundary",
        "mappings",
    }
    if set(payload) != expected:
        raise ValueError("tri-security vendor mappings have unknown or missing fields")
    if payload["schema_version"] != TRI_SECURITY_MAPPING_SCHEMA_VERSION:
        raise ValueError("tri-security vendor mappings have unsupported schema_version")
    if payload["registry_id"] != registry.registry_id:
        raise ValueError("tri-security vendor mappings registry_id mismatch")
    as_of = parse_iso_date(payload["as_of"], "tri-security mappings as_of").isoformat()
    if as_of != registry.as_of:
        raise ValueError("tri-security vendor mappings as_of mismatch")
    if payload["scope"] != "TRI_SECURITY_PILOT_VENDOR_MAPPINGS":
        raise ValueError("tri-security vendor mappings have invalid scope")
    if payload["claim_boundary"] != "VENDOR_MAPPING_IS_NOT_OFFICIAL_SECURITY_IDENTITY":
        raise ValueError("tri-security vendor mapping claim boundary cannot be weakened")
    raw_rows = payload["mappings"]
    if not isinstance(raw_rows, list) or not raw_rows:
        raise ValueError("tri-security vendor mappings must be a non-empty list")
    identities = {
        security.ticker: security
        for batch in registry.batches
        for security in batch.securities
    }
    mappings = tuple(
        _vendor_mapping(row, index, identities)  # type: ignore[arg-type]
        for index, row in enumerate(raw_rows)
    )
    inactive = sorted(
        mapping.ticker for mapping in mappings if mapping.mapping_state == "RETIRED"
    )
    if inactive:
        raise ValueError(
            "tri-security vendor mappings contain inactive configured securities: "
            + ",".join(inactive)
        )
    expected_tickers = set(identities)
    actual_tickers = {mapping.ticker for mapping in mappings}
    if actual_tickers != expected_tickers or len(mappings) != len(expected_tickers):
        raise ValueError(
            "tri-security vendor mappings must contain exactly one row per security"
        )
    urls = [mapping.provider_url for mapping in mappings]
    symbols = [(mapping.provider, mapping.provider_symbol) for mapping in mappings]
    if len(urls) != len(set(urls)) or len(symbols) != len(set(symbols)):
        raise ValueError("tri-security vendor mappings contain duplicate provider routes")
    return TriSecurityVendorMappings(
        registry_id=registry.registry_id,
        as_of=as_of,
        mappings=mappings,
        source_bytes=content,
    )


def _scoped_configuration(
    *,
    root: Path,
    config_dir: Path,
    registry: TriSecurityRegistry,
    vendor_catalog: TriSecurityVendorMappings,
    batch: TriSecurityBatch,
) -> tuple[dict[str, Any], bytes]:
    scoped_root = root / "scoped_config"
    pilot_dir = scoped_root / "pilot"
    pilot_dir.mkdir(parents=True, exist_ok=False)
    seed_payload = {
        "schema_version": "1.0",
        "as_of": registry.as_of,
        "scope": f"TRI_SECURITY_BATCH:{batch.batch_id}",
        "claim_boundary": "SEED_IDENTITY_NOT_OFFICIAL_EVIDENCE",
        "securities": [
            {
                "security_code": security.security_code,
                "ticker": security.ticker,
                "name_en": security.name_en,
                "name_ar": security.name_ar,
                "isin": security.isin,
                "sector": security.sector,
                "identity_state": "UNVERIFIED_SEED",
                "official_artifact_sha256": None,
                "valid_from": None,
                "valid_to": None,
                "notes": (
                    f"Scoped candidate for {batch.batch_id}. This row is not official "
                    "identity evidence; import preserved official bytes before use."
                ),
            }
            for security in batch.securities
        ],
    }
    selected_mappings = vendor_catalog.for_batch(batch)
    mapping_payload = {
        "schema_version": "1.0",
        "as_of": vendor_catalog.as_of,
        "scope": f"TRI_SECURITY_BATCH:{batch.batch_id}",
        "claim_boundary": "VENDOR_MAPPING_IS_NOT_OFFICIAL_SECURITY_IDENTITY",
        "mappings": [
            {
                "security_code": mapping.security_code,
                "ticker": mapping.ticker,
                "isin": mapping.isin,
                "provider": mapping.provider,
                "provider_symbol": mapping.provider_symbol,
                "provider_url": mapping.provider_url,
                "mapping_state": mapping.mapping_state,
                "evidence_notes": mapping.evidence_notes,
            }
            for mapping in selected_mappings
        ],
    }
    files: dict[str, bytes] = {
        "pilot/security_master_seed.json": canonical_json_bytes(seed_payload),
        "pilot/vendor_symbol_mappings.json": canonical_json_bytes(mapping_payload),
        "pilot/tri_security_batches.json": registry.source_bytes,
        "pilot/tri_security_vendor_mappings.json": vendor_catalog.source_bytes,
    }
    for name in ("benchmark_registry.json", "outcome_session_policy.json"):
        files[f"pilot/{name}"] = safe_regular_file(
            Path(config_dir) / "pilot" / name,
            field=f"base pilot {name}",
        )
    manifest_rows: list[dict[str, str]] = []
    for relative, content in sorted(files.items()):
        destination = scoped_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        manifest_rows.append(
            {"path": relative, "sha256": sha256_bytes(content)}
        )
    manifest = {
        "schema_version": "1.0",
        "scope": "TRI_SECURITY_BATCH_SCOPED_CONFIGURATION",
        "batch_id": batch.batch_id,
        "batch_sha256": hash_json(batch.to_dict()),
        "security_count": TRI_SECURITY_BATCH_SIZE,
        "files": manifest_rows,
        "claim_boundary": TRI_SECURITY_CLAIM_BOUNDARY,
    }
    manifest_bytes = canonical_json_bytes(manifest)
    (scoped_root / "manifest.json").write_bytes(manifest_bytes)
    (scoped_root / "README.txt").write_text(
        "Pass this exact directory to kubo-data-foundation with "
        "--pilot-config-dir. It contains a three-security configuration "
        "denominator, not official identity or market evidence.\n",
        encoding="utf-8",
    )
    return manifest, manifest_bytes


def verify_tri_security_scoped_config(
    config_dir: Path,
    *,
    expected_manifest_sha256: str | None = None,
) -> dict[str, Any]:
    root = Path(config_dir)
    manifest, manifest_bytes = load_strict_json_object(
        root / "manifest.json",
        field="tri-security scoped configuration manifest",
    )
    expected_top = {
        "schema_version",
        "scope",
        "batch_id",
        "batch_sha256",
        "security_count",
        "files",
        "claim_boundary",
    }
    if set(manifest) != expected_top:
        raise ValueError("tri-security scoped configuration manifest has unknown or missing fields")
    if manifest["schema_version"] != "1.0":
        raise ValueError("unsupported tri-security scoped configuration schema_version")
    if manifest["scope"] != "TRI_SECURITY_BATCH_SCOPED_CONFIGURATION":
        raise ValueError("tri-security scoped configuration scope is invalid")
    if manifest["claim_boundary"] != TRI_SECURITY_CLAIM_BOUNDARY:
        raise ValueError("tri-security scoped configuration claim boundary is invalid")
    manifest_sha256 = sha256_bytes(manifest_bytes)
    if expected_manifest_sha256 is not None:
        if not re.fullmatch(r"[0-9a-f]{64}", expected_manifest_sha256):
            raise ValueError("expected scoped configuration manifest SHA-256 is invalid")
        if manifest_sha256 != expected_manifest_sha256:
            raise ValueError("tri-security scoped configuration manifest SHA-256 mismatch")
    raw_files = manifest["files"]
    if not isinstance(raw_files, list) or len(raw_files) != 6:
        raise ValueError("tri-security scoped configuration must bind exactly six files")
    expected_paths = {
        "pilot/benchmark_registry.json",
        "pilot/outcome_session_policy.json",
        "pilot/security_master_seed.json",
        "pilot/tri_security_batches.json",
        "pilot/tri_security_vendor_mappings.json",
        "pilot/vendor_symbol_mappings.json",
    }
    seen: set[str] = set()
    verified_files: list[dict[str, str]] = []
    for index, row in enumerate(raw_files):
        if not isinstance(row, dict) or set(row) != {"path", "sha256"}:
            raise ValueError(f"tri-security scoped configuration file {index} is invalid")
        relative = row["path"]
        digest = row["sha256"]
        if relative not in expected_paths or relative in seen:
            raise ValueError("tri-security scoped configuration contains an invalid or duplicate path")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("tri-security scoped configuration contains an invalid SHA-256")
        content = safe_regular_file(
            root / relative,
            field=f"tri-security scoped configuration {relative}",
        )
        if sha256_bytes(content) != digest:
            raise ValueError(f"tri-security scoped configuration hash mismatch: {relative}")
        seen.add(relative)
        verified_files.append({"path": relative, "sha256": digest})
    if seen != expected_paths:
        raise ValueError("tri-security scoped configuration file denominator mismatch")
    registry = load_tri_security_registry(root)
    vendor_catalog = load_tri_security_vendor_mappings(root, registry)
    batch_id = _required_text(manifest["batch_id"], "scoped configuration batch_id")
    batch = registry.batch(batch_id)
    if manifest["batch_sha256"] != hash_json(batch.to_dict()):
        raise ValueError("tri-security scoped configuration batch SHA-256 mismatch")
    if manifest["security_count"] != TRI_SECURITY_BATCH_SIZE:
        raise ValueError("tri-security scoped configuration security_count must be exactly 3")
    identities_payload, _ = load_strict_json_object(
        root / "pilot" / "security_master_seed.json",
        field="tri-security scoped identity seed",
    )
    scoped_codes = {
        str(row.get("security_code"))
        for row in identities_payload.get("securities", [])
        if isinstance(row, dict)
    }
    batch_codes = {security.security_code for security in batch.securities}
    if scoped_codes != batch_codes or len(scoped_codes) != TRI_SECURITY_BATCH_SIZE:
        raise ValueError("tri-security scoped identity denominator does not match the batch")
    vendor_catalog.for_batch(batch)
    return {
        "status": "PASS",
        "scope": "TRI_SECURITY_BATCH_SCOPED_CONFIGURATION",
        "batch_id": batch.batch_id,
        "security_count": TRI_SECURITY_BATCH_SIZE,
        "manifest_sha256": manifest_sha256,
        "verified_files": verified_files,
        "claim_boundaries": {
            "configuration_integrity_verified": True,
            "configuration_is_official_identity": False,
            "configuration_is_market_evidence": False,
            "backtest_ready": False,
        },
    }


def _validate_prepared_by(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("prepared_by must be text")
    if any(character in value for character in ("\x00", "\r", "\n")):
        raise ValueError("prepared_by must be at most 128 single-line characters")
    normalized = value.strip()
    if len(normalized) > 128:
        raise ValueError("prepared_by must be at most 128 single-line characters")
    return normalized


def prepare_tri_security_batch_workspace(
    *,
    config_dir: Path,
    output_root: Path,
    batch_id: str,
    run_id: str,
    window_from: str,
    window_to: str,
    prepared_by: str = "",
) -> dict[str, Any]:
    if not _RUN_ID_RE.fullmatch(run_id):
        raise ValueError("run_id must be a canonical path-safe identifier")
    actor = _validate_prepared_by(prepared_by)
    registry = load_tri_security_registry(config_dir)
    vendor_catalog = load_tri_security_vendor_mappings(config_dir, registry)
    batch = registry.batch(batch_id)
    predecessor = registry.predecessor(batch)
    if predecessor is not None:
        raise ValueError(
            f"batch {batch.batch_id} is locked until an independently verified "
            f"qualification receipt for {predecessor} is supported"
        )
    start = parse_iso_date(window_from, "window_from")
    end = parse_iso_date(window_to, "window_to")
    if start > end:
        raise ValueError("tri-security qualification window is reversed")
    if start.year != end.year:
        raise ValueError("tri-security qualification window must remain within one calendar year")
    if end > parse_iso_date(registry.as_of, "registry as_of"):
        raise ValueError("tri-security qualification window exceeds the registry as_of date")
    root = prepare_output_root(output_root, label="tri-security batch workspace")
    plan_dir = root / "plan"
    evidence_dir = root / "evidence"
    report_dir = root / "reports"
    for directory in (plan_dir, evidence_dir, report_dir):
        directory.mkdir(parents=True, exist_ok=False)

    batch_payload = batch.to_dict()
    batch_sha256 = hash_json(batch_payload)
    scoped_manifest, scoped_manifest_bytes = _scoped_configuration(
        root=root,
        config_dir=config_dir,
        registry=registry,
        vendor_catalog=vendor_catalog,
        batch=batch,
    )
    plan = {
        "schema_version": TRI_SECURITY_WORKSPACE_SCHEMA_VERSION,
        "mode": TRI_SECURITY_MODE,
        "run_id": run_id,
        "prepared_by": actor,
        "registry": {
            "registry_id": registry.registry_id,
            "registry_sha256": registry.sha256,
            "as_of": registry.as_of,
        },
        "batch": batch_payload,
        "batch_sha256": batch_sha256,
        "qualification_window": {
            "window_from": start.isoformat(),
            "window_to": end.isoformat(),
            "timezone": "Asia/Kuwait",
            "date_basis": "DECLARED_DATA_QUALIFICATION_WINDOW",
        },
        "scoped_configuration": {
            "root": "scoped_config",
            "manifest_path": "scoped_config/manifest.json",
            "manifest_sha256": sha256_bytes(scoped_manifest_bytes),
            "security_count": scoped_manifest["security_count"],
        },
        "execution": {
            "sequence": batch.sequence,
            "predecessor_batch_id": predecessor,
            "predecessor_qualification_required": predecessor is not None,
        },
        "gates": [
            {
                "gate": gate,
                "status": "PENDING_EXTERNAL_EVIDENCE",
                "required_evidence": list(_REQUIRED_EVIDENCE[gate]),
            }
            for gate in GATE_ORDER
        ],
        "allowed_output": TRI_SECURITY_ALLOWED_OUTPUT,
        "claim_boundary": TRI_SECURITY_CLAIM_BOUNDARY,
    }
    plan_path = plan_dir / "tri_security_batch_plan.json"
    plan_bytes = canonical_json_bytes(plan)
    plan_path.write_bytes(plan_bytes)

    for security in batch.securities:
        security_dir = evidence_dir / f"{security.security_code}-{security.ticker}"
        security_dir.mkdir()
        (security_dir / "README.txt").write_text(
            "This directory is empty by design. Preserve authorized raw evidence "
            "outside Git, retain exact bytes, record SHA-256 and timestamps, and "
            "import it only through the existing KU-BO data-foundation contracts.\n"
            f"security_code={security.security_code}\n"
            f"ticker={security.ticker}\n"
            f"isin={security.isin}\n"
            "The configured identity is UNVERIFIED_SEED and is not official evidence.\n",
            encoding="utf-8",
        )

    checklist_path = report_dir / "tri_security_batch_checklist_ar.md"
    checklist_lines = [
        "# قائمة فحص دفعة الأسهم الثلاثية",
        "",
        f"- Batch: `{batch.batch_id}`",
        f"- Run: `{run_id}`",
        f"- Mode: `{TRI_SECURITY_MODE}`",
        f"- Window: `{start.isoformat()}` to `{end.isoformat()}` (Asia/Kuwait)",
        "- المخرج المسموح: تقرير تأهيل بيانات فقط.",
        "- ابدأ بإثبات الهوية الرسمية المؤرخة لكل Security Code وISIN.",
        "- لا تستخدم Ticker وحده للربط.",
        "- لا تملأ جلسة أو سعرًا أو Corporate Action مفقودة اصطناعيًا.",
        "- لا تبدأ الدفعة التالية قبل تقرير تأهيل مستقل للدفعة السابقة.",
        "- نجاح ثلاثة أسهم لا يثبت تغطية السوق أو صلاحية Backtest أو Forecast.",
        "",
        "## الأوراق المالية",
        "",
    ]
    for security in batch.securities:
        checklist_lines.append(
            f"- `{security.security_code}` / `{security.ticker}` / `{security.isin}` "
            f"— {security.name_ar}"
        )
    checklist_lines.append("")
    checklist_path.write_text("\n".join(checklist_lines), encoding="utf-8")

    readiness_status = (
        "CONFIG_VALID_EXTERNAL_EVIDENCE_REQUIRED"
        if predecessor is None
        else "CONFIG_VALID_PREDECESSOR_AND_EXTERNAL_EVIDENCE_REQUIRED"
    )
    report = {
        "schema_version": TRI_SECURITY_WORKSPACE_SCHEMA_VERSION,
        "status": "PASS",
        "readiness_status": readiness_status,
        "workspace_kind": "TRI_SECURITY_DATA_QUALIFICATION",
        "mode": TRI_SECURITY_MODE,
        "run_id": run_id,
        "batch_id": batch.batch_id,
        "batch_sequence": batch.sequence,
        "batch_size": len(batch.securities),
        "qualification_window": {
            "window_from": start.isoformat(),
            "window_to": end.isoformat(),
            "timezone": "Asia/Kuwait",
        },
        "securities": [
            {
                "security_code": security.security_code,
                "ticker": security.ticker,
                "isin": security.isin,
                "identity_state": security.identity_state,
            }
            for security in batch.securities
        ],
        "registry_id": registry.registry_id,
        "registry_sha256": registry.sha256,
        "batch_sha256": batch_sha256,
        "batch_plan_path": plan_path.relative_to(root).as_posix(),
        "batch_plan_sha256": sha256_bytes(plan_bytes),
        "scoped_config_root": "scoped_config",
        "scoped_config_manifest_path": "scoped_config/manifest.json",
        "scoped_config_manifest_sha256": sha256_bytes(scoped_manifest_bytes),
        "checklist_path": checklist_path.relative_to(root).as_posix(),
        "predecessor_batch_id": predecessor,
        "predecessor_qualification_required": predecessor is not None,
        "required_gates": list(GATE_ORDER),
        "gate_states": ["PENDING_EXTERNAL_EVIDENCE" for _ in GATE_ORDER],
        "remaining_external_blockers": [
            "OFFICIAL_EFFECTIVE_DATED_IDENTITY",
            "RIGHTS_COMPATIBLE_MARKET_EVIDENCE",
            "AUTHENTICATED_CAPTURE_RECEIPTS",
            "KU-BO-008-D01_OUTCOME_SESSION_POLICY",
            "INDEPENDENT_FINAL_GATE_REPORT",
        ],
        "claim_boundaries": {
            "workspace_contains_market_evidence": False,
            "seed_identity_is_official_evidence": False,
            "batch_passed_data_qualification": False,
            "three_security_batch_validates_full_market": False,
            "backtest_ready": False,
            "forecast_generated": False,
            "probability_generated": False,
            "recommendation_generated": False,
            "next_batch_authorized": False,
        },
    }
    report_path = report_dir / "tri_security_workspace_report.json"
    report_path.write_bytes(canonical_json_bytes(report))
    return report


__all__ = [
    "TRI_SECURITY_ALLOWED_OUTPUT",
    "TRI_SECURITY_BATCH_SIZE",
    "TRI_SECURITY_CLAIM_BOUNDARY",
    "TRI_SECURITY_MODE",
    "TRI_SECURITY_MAPPING_SCHEMA_VERSION",
    "TRI_SECURITY_REGISTRY_SCHEMA_VERSION",
    "TRI_SECURITY_SCOPE",
    "TriSecurityBatch",
    "TriSecurityCandidate",
    "TriSecurityRegistry",
    "TriSecurityVendorMappings",
    "load_tri_security_registry",
    "load_tri_security_vendor_mappings",
    "prepare_tri_security_batch_workspace",
    "verify_tri_security_scoped_config",
]
