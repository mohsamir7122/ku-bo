from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

from .capabilities import CapabilityAttestation, CapabilityReport
from .catalog import Catalog
from .evidence import EvidenceManifest, ManifestResult
from .hashing import sha256_file
from .identity import IdentityRecord, StatusRecord, read_csv_rows, validate_security_master, validate_status_history
from .market import (
    CORPORATE_ACTION_COLUMNS,
    DISCLOSURE_COLUMNS,
    ValidationResult,
    validate_eod,
    validate_event_table,
    validate_market_totals,
    validate_query_ledger,
    validate_trading_calendar,
)
from .strict import parse_aware, parse_iso_date, require_sha256


@dataclass(frozen=True)
class CollectionContract:
    pack_id: str
    as_of: str
    window_from: date
    window_to: date
    timezone: str
    included_boards: tuple[str, ...]
    run_status: str


@dataclass(frozen=True)
class PackValidation:
    status: str
    passed_capabilities: frozenset[str]
    errors: tuple[str, ...]
    manifest: ManifestResult
    dataset_results: dict[str, ValidationResult]
    collection: CollectionContract | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "passed_capabilities": sorted(self.passed_capabilities),
            "errors": list(self.errors),
            "manifest": {
                "status": self.manifest.status,
                "artifacts": len(self.manifest.artifacts),
                "errors": list(self.manifest.errors),
            },
            "datasets": {key: asdict(value) for key, value in sorted(self.dataset_results.items())},
            "collection": None
            if self.collection is None
            else {
                **asdict(self.collection),
                "window_from": self.collection.window_from.isoformat(),
                "window_to": self.collection.window_to.isoformat(),
            },
        }


def _load_collection_contract(pack_root: Path) -> tuple[CollectionContract | None, list[str]]:
    path = pack_root / "manifests" / "collection_run.json"
    if not path.is_file():
        return None, ["MISSING_COLLECTION_RUN"]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, [f"INVALID_COLLECTION_RUN:{exc}"]
    errors: list[str] = []
    try:
        if payload.get("schema_version") != "2.0":
            raise ValueError("unsupported collection schema")
        pack_id = str(payload.get("pack_id", "")).strip()
        if not pack_id:
            raise ValueError("pack_id is required")
        as_of = parse_aware(payload.get("as_of"), "as_of")
        timezone = str(payload.get("timezone", ""))
        if timezone != "Asia/Kuwait":
            raise ValueError("timezone must be Asia/Kuwait")
        window_from = parse_iso_date(payload.get("window_from"), "window_from")
        window_to = parse_iso_date(payload.get("window_to"), "window_to")
        if window_from > window_to:
            raise ValueError("window_from is after window_to")
        if window_to > as_of.date():
            raise ValueError("window_to is after collection as_of")
        boards = tuple(str(item).lower() for item in payload.get("included_boards", []))
        if boards != ("cash",):
            raise ValueError("V2 validation requires included_boards=['cash']")
        run_status = str(payload.get("run_status", ""))
        if run_status not in {"QUALIFIED", "INCOMPLETE", "BLOCKED", "BUDGET_EXHAUSTED"}:
            raise ValueError("invalid run_status")
        budget = payload.get("budget")
        usage = payload.get("usage")
        if not isinstance(budget, dict) or not isinstance(usage, dict):
            raise ValueError("budget and usage are required")
        for field in ("max_requests", "max_raw_bytes", "max_wall_seconds", "max_zero_yield_attempts_per_family"):
            if int(budget.get(field, 0)) <= 0:
                raise ValueError(f"budget.{field} must be positive")
        for field in ("requests", "raw_bytes", "wall_seconds"):
            if int(usage.get(field, -1)) < 0:
                raise ValueError(f"usage.{field} must be non-negative")
        if int(usage["requests"]) > int(budget["max_requests"]) or int(usage["raw_bytes"]) > int(budget["max_raw_bytes"]) or int(usage["wall_seconds"]) > int(budget["max_wall_seconds"]):
            if run_status != "BUDGET_EXHAUSTED":
                raise ValueError("budget exceeded without BUDGET_EXHAUSTED status")
        return CollectionContract(pack_id, as_of.isoformat(), window_from, window_to, timezone, boards, run_status), []
    except (TypeError, ValueError) as exc:
        errors.append(str(exc))
    return None, errors


def _normalized_file(pack_root: Path, attestation: CapabilityAttestation) -> tuple[Path | None, list[str]]:
    errors: list[str] = []
    relative = Path(attestation.normalized_path)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts or relative.parts[0] != "normalized":
        return None, ["UNSAFE_NORMALIZED_PATH"]
    path = (pack_root / relative).resolve()
    if pack_root.resolve() not in path.parents or not path.is_file():
        return None, ["MISSING_NORMALIZED_FILE"]
    if sha256_file(path) != attestation.normalized_sha256:
        errors.append("NORMALIZED_HASH_MISMATCH")
    return path, errors


_NORMALIZED_CUTOFF_FIELDS = frozenset(
    {
        "as_of",
        "available_at",
        "fetched_at",
        "first_available_at",
        "generated_at",
        "normalized_at",
        "observed_at",
        "provider_as_of",
        "published_at",
        "source_published_at",
        "validated_at",
    }
)


def _normalized_cutoff_errors(path: Path, *, cutoff: str) -> list[str]:
    """Reject post-cutoff availability metadata in any normalized CSV.

    Business-effective dates such as a future dividend payment date are not
    availability timestamps and remain valid when announced before cutoff.
    The fields below describe observation, publication, fetching, or material-
    ization time and therefore must be point-in-time safe.
    """

    try:
        headers, rows = read_csv_rows(path)
    except (OSError, ValueError) as exc:
        return [f"NORMALIZED_CUTOFF_READ:{exc}"]
    fields = sorted(set(headers) & _NORMALIZED_CUTOFF_FIELDS)
    if not fields:
        return []
    cutoff_at = parse_aware(cutoff, "collection.as_of")
    errors: list[str] = []
    for index, row in enumerate(rows):
        for field in fields:
            value = row.get(field)
            if value in (None, ""):
                continue
            try:
                timestamp = parse_aware(value, field)
                if timestamp > cutoff_at:
                    raise ValueError(f"{field} is after collection as_of")
            except ValueError as exc:
                errors.append(f"normalized_row_{index}:{exc}")
    return errors


def _attestation_hashes(
    attestation: CapabilityAttestation,
    manifest: ManifestResult,
) -> frozenset[str]:
    """Resolve only hashes attributable to the attestation's sources."""

    declared = set(attestation.evidence_hashes)
    return frozenset(
        digest
        for source_id in attestation.source_ids
        for digest in manifest.hashes_by_source.get(source_id, frozenset())
        if digest in declared
    )


def _generic_normalized(path: Path, *, manifest_hashes: frozenset[str], capability: str) -> ValidationResult:
    errors: list[str] = []
    try:
        headers, rows = read_csv_rows(path)
    except (OSError, ValueError) as exc:
        return ValidationResult("BLOCKED", 0, (f"GENERIC_READ:{exc}",), {})
    if "raw_sha256" not in headers:
        errors.append("GENERIC_RAW_SHA256_HEADER")
    if not rows:
        errors.append("GENERIC_EMPTY")
    for index, row in enumerate(rows):
        try:
            digest = require_sha256(row.get("raw_sha256"), "raw_sha256")
            if digest not in manifest_hashes:
                raise ValueError("raw_sha256 does not resolve")
        except ValueError as exc:
            errors.append(f"generic_row_{index}:{exc}")
    return ValidationResult("PASS" if not errors else "BLOCKED", len(rows), tuple(errors), {"capability": capability})


class PackValidator:
    def __init__(self, pack_root: Path, catalog: Catalog):
        self.pack_root = pack_root.resolve()
        self.catalog = catalog

    def validate(self) -> PackValidation:
        collection, collection_errors = _load_collection_contract(self.pack_root)
        cutoff = collection.as_of if collection is not None else None
        manifest = EvidenceManifest(self.pack_root, self.catalog).validate(cutoff=cutoff)
        capability_result = CapabilityReport(
            self.pack_root,
            self.catalog,
            manifest,
            cutoff=cutoff,
        ).validate()
        errors: list[str] = list(collection_errors) + list(capability_result.errors)
        results: dict[str, ValidationResult] = {}
        if manifest.status != "PASS" or collection is None or capability_result.status != "PASS":
            errors.extend(manifest.errors)
            return PackValidation("BLOCKED", frozenset(), tuple(sorted(set(errors))), manifest, results, collection)

        attestations = {item.capability: item for item in capability_result.attestations if item.status == "PASS"}
        paths: dict[str, Path] = {}
        for capability, attestation in attestations.items():
            path, path_errors = _normalized_file(self.pack_root, attestation)
            if path is not None and not path_errors and collection is not None:
                path_errors.extend(_normalized_cutoff_errors(path, cutoff=collection.as_of))
            if path_errors:
                results[capability] = ValidationResult("BLOCKED", 0, tuple(path_errors), {})
            elif path is not None:
                paths[capability] = path

        identities: list[IdentityRecord] = []
        statuses: list[StatusRecord] = []
        calendar: dict[date, dict[str, Any]] = {}
        eod_rows: list[dict[str, Any]] = []
        query_rows: list[dict[str, Any]] = []
        query_result: ValidationResult | None = None
        capability_hashes = {
            capability: _attestation_hashes(attestation, manifest)
            for capability, attestation in attestations.items()
        }

        if "security_master" in paths:
            identities, dataset_errors = validate_security_master(
                paths["security_master"],
                manifest_hashes=capability_hashes["security_master"],
            )
            results["security_master"] = ValidationResult("PASS" if not dataset_errors else "BLOCKED", len(identities), tuple(dataset_errors), {"unique_codes": len({item.security_code for item in identities})})
        if "security_status_history" in paths:
            known = frozenset(item.security_code for item in identities)
            if not known:
                results["security_status_history"] = ValidationResult("BLOCKED", 0, ("SECURITY_MASTER_REQUIRED",), {})
            else:
                statuses, dataset_errors = validate_status_history(
                    paths["security_status_history"],
                    manifest_hashes=capability_hashes["security_status_history"],
                    known_codes=known,
                )
                results["security_status_history"] = ValidationResult("PASS" if not dataset_errors else "BLOCKED", len(statuses), tuple(dataset_errors), {})
        if "trading_calendar" in paths:
            calendar, results["trading_calendar"] = validate_trading_calendar(
                paths["trading_calendar"],
                manifest_hashes=capability_hashes["trading_calendar"],
                window_from=collection.window_from,
                window_to=collection.window_to,
            )

        query_path = self.pack_root / "manifests" / "query_ledger.csv"
        if query_path.is_file():
            query_capabilities = {
                "disclosures": "official_disclosures",
                "corporate_actions": "corporate_actions",
            }
            query_hashes = frozenset(
                digest
                for capability in query_capabilities.values()
                for digest in capability_hashes.get(capability, frozenset())
            )
            query_rows, query_result = validate_query_ledger(
                query_path,
                manifest_hashes=query_hashes,
                window_from=collection.window_from,
                window_to=collection.window_to,
            )
            query_binding_errors: list[str] = []
            for index, row in enumerate(query_rows):
                capability = query_capabilities.get(str(row.get("dataset", "")))
                digest = str(row.get("raw_sha256", ""))
                if capability is None or digest not in capability_hashes.get(capability, frozenset()):
                    query_binding_errors.append(
                        f"query_row_{index}:raw_sha256 is not bound to its dataset capability"
                    )
            if query_binding_errors:
                query_result = ValidationResult(
                    "BLOCKED",
                    query_result.rows,
                    tuple(sorted(set([*query_result.errors, *query_binding_errors]))),
                    query_result.details,
                )
            results["query_ledger"] = query_result
        elif {"official_disclosures", "corporate_actions"} & set(paths):
            results["query_ledger"] = ValidationResult("BLOCKED", 0, ("MISSING_QUERY_LEDGER",), {})

        if "daily_eod" in paths:
            if not identities or not statuses or not calendar:
                results["daily_eod"] = ValidationResult("BLOCKED", 0, ("MASTER_STATUS_CALENDAR_REQUIRED",), {})
            else:
                eod_rows, results["daily_eod"] = validate_eod(
                    paths["daily_eod"],
                    manifest_hashes=capability_hashes["daily_eod"],
                    calendar=calendar,
                    identities=identities,
                    statuses=statuses,
                )
        if "daily_market_totals" in paths:
            if not eod_rows:
                results["daily_market_totals"] = ValidationResult("BLOCKED", 0, ("VALID_EOD_REQUIRED",), {})
            else:
                results["daily_market_totals"] = validate_market_totals(
                    paths["daily_market_totals"],
                    manifest_hashes=capability_hashes["daily_market_totals"],
                    eod_rows=eod_rows,
                )
        if "official_disclosures" in paths:
            results["official_disclosures"] = validate_event_table(
                paths["official_disclosures"],
                dataset="disclosures",
                manifest_hashes=capability_hashes["official_disclosures"],
                query_rows=query_rows,
                required_columns=DISCLOSURE_COLUMNS,
            )
        if "corporate_actions" in paths:
            results["corporate_actions"] = validate_event_table(
                paths["corporate_actions"],
                dataset="corporate_actions",
                manifest_hashes=capability_hashes["corporate_actions"],
                query_rows=query_rows,
                required_columns=CORPORATE_ACTION_COLUMNS,
            )

        handled = {"security_master", "security_status_history", "trading_calendar", "daily_eod", "daily_market_totals", "official_disclosures", "corporate_actions"}
        for capability, path in paths.items():
            if capability not in handled:
                results[capability] = _generic_normalized(
                    path,
                    manifest_hashes=capability_hashes[capability],
                    capability=capability,
                )

        passed = {capability for capability in attestations if capability in results and results[capability].status == "PASS"}
        if "query_ledger" in results and results["query_ledger"].status != "PASS":
            passed -= {"official_disclosures", "corporate_actions"}
        for capability in attestations:
            if capability not in results:
                errors.append(f"NO_VALIDATOR_RESULT:{capability}")
            elif results[capability].status != "PASS":
                errors.extend(f"{capability}:{item}" for item in results[capability].errors)
        if capability_result.passed - set(attestations):
            errors.append("CAPABILITY_ATTESTATION_INTERNAL_MISMATCH")
        status = "PASS" if not errors and passed == set(attestations) else "BLOCKED"
        return PackValidation(status, frozenset(passed) if status == "PASS" else frozenset(), tuple(sorted(set(errors))), manifest, results, collection)


__all__ = ["CollectionContract", "PackValidation", "PackValidator"]
