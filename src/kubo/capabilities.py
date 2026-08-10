from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .catalog import CAPABILITY_VOCABULARY, Catalog
from .evidence import ManifestResult
from .strict import parse_aware, require_sha256


EXECUTION_CAPABILITIES = frozenset({"intraday_bars", "opening_auction", "l1_quotes", "l2_order_book", "execution_fields"})
AUTHORIZED_ACCESS = frozenset({"LICENSED_VENDOR", "BROKER_AUTHENTICATED", "DIRECT_MARKET_FEED"})
CAPABILITY_ALLOWED_ROLES: dict[str, frozenset[str]] = {
    "security_master": frozenset({"OFFICIAL_TRUTH"}),
    "security_status_history": frozenset({"OFFICIAL_TRUTH"}),
    "trading_calendar": frozenset({"OFFICIAL_TRUTH"}),
    "daily_eod": frozenset({"OFFICIAL_TRUTH", "AUTHORIZED_TAPE"}),
    "daily_market_totals": frozenset({"OFFICIAL_TRUTH", "AUTHORIZED_TAPE"}),
    "benchmark_history": frozenset({"OFFICIAL_TRUTH", "AUTHORIZED_TAPE"}),
    "official_disclosures": frozenset({"OFFICIAL_TRUTH", "ISSUER_PRIMARY"}),
    "corporate_actions": frozenset({"OFFICIAL_TRUTH", "ISSUER_PRIMARY"}),
    "issuer_reports": frozenset({"ISSUER_PRIMARY"}),
    "news_context": frozenset({"DISCOVERY", "CROSS_CHECK", "CONTEXT"}),
    "social_evidence": frozenset({"SENTIMENT"}),
    "intraday_bars": frozenset({"AUTHORIZED_TAPE"}),
    "opening_auction": frozenset({"AUTHORIZED_TAPE"}),
    "l1_quotes": frozenset({"AUTHORIZED_TAPE"}),
    "l2_order_book": frozenset({"AUTHORIZED_TAPE"}),
    "execution_fields": frozenset({"AUTHORIZED_TAPE"}),
}


@dataclass(frozen=True)
class CapabilityAttestation:
    capability: str
    status: str
    source_ids: tuple[str, ...]
    evidence_hashes: tuple[str, ...]
    normalized_path: str
    normalized_sha256: str
    validator_id: str
    validator_version: str
    validated_at: str
    access_class: str
    coverage_numerator: int
    coverage_denominator: int
    limitations: tuple[str, ...]

    @property
    def coverage(self) -> float:
        return self.coverage_numerator / self.coverage_denominator if self.coverage_denominator else 0.0


@dataclass(frozen=True)
class CapabilityResult:
    status: str
    passed: frozenset[str]
    attestations: tuple[CapabilityAttestation, ...]
    errors: tuple[str, ...]


class CapabilityReport:
    """Validate capability attestations against real raw evidence.

    This does not validate normalized table semantics. `PackValidator` performs
    that independent pass before a capability becomes product-eligible.
    """

    def __init__(
        self,
        pack_root: Path,
        catalog: Catalog,
        manifest: ManifestResult,
        *,
        cutoff: Any | None = None,
    ):
        self.pack_root = pack_root.resolve()
        self.catalog = catalog
        self.manifest = manifest
        self.cutoff = parse_aware(cutoff, "cutoff") if cutoff is not None else None
        self.path = self.pack_root / "manifests" / "capability_report.json"

    def validate(self) -> CapabilityResult:
        if self.manifest.status != "PASS":
            return CapabilityResult("BLOCKED", frozenset(), (), ("RAW_MANIFEST_NOT_VALID",))
        if not self.path.is_file():
            return CapabilityResult("BLOCKED", frozenset(), (), ("MISSING_CAPABILITY_REPORT",))
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return CapabilityResult("BLOCKED", frozenset(), (), (f"INVALID_CAPABILITY_REPORT:{exc}",))
        errors: list[str] = []
        parsed_rows: list[CapabilityAttestation] = []
        if payload.get("schema_version") != "2.0":
            errors.append("UNSUPPORTED_CAPABILITY_SCHEMA")
        report_as_of = None
        try:
            report_as_of = parse_aware(payload.get("as_of"), "as_of")
            if self.cutoff is not None and report_as_of > self.cutoff:
                raise ValueError("capability report as_of is after the collection cutoff")
        except ValueError as exc:
            errors.append(str(exc))
        rows = payload.get("attestations")
        if not isinstance(rows, list) or not rows:
            errors.append("EMPTY_CAPABILITY_ATTESTATIONS")
            rows = []
        seen: set[str] = set()
        manifest_hashes = self.manifest.hashes
        hashes_by_source = self.manifest.hashes_by_source
        for index, row in enumerate(rows):
            prefix = f"attestation_{index}"
            if not isinstance(row, dict):
                errors.append(prefix + ":NOT_OBJECT")
                continue
            try:
                capability = str(row.get("capability", ""))
                if capability not in CAPABILITY_VOCABULARY:
                    raise ValueError(f"unknown capability: {capability}")
                if capability in seen:
                    raise ValueError("duplicate capability attestation")
                seen.add(capability)
                status = str(row.get("status", ""))
                if status not in {"PASS", "FAIL", "NOT_AVAILABLE", "NOT_APPLICABLE"}:
                    raise ValueError("invalid attestation status")
                source_ids = tuple(str(item) for item in row.get("source_ids", []))
                if status == "PASS" and not source_ids:
                    raise ValueError("PASS requires source_ids")
                if len(source_ids) != len(set(source_ids)):
                    raise ValueError("source_ids must be unique")
                for source_id in source_ids:
                    if source_id not in self.catalog.sources:
                        raise ValueError(f"unknown source_id: {source_id}")
                    source = self.catalog.sources[source_id]
                    if not source.market_evidence_allowed:
                        raise ValueError(f"source is ineligible as market evidence: {source_id}")
                    if capability not in source.capabilities:
                        raise ValueError(f"source {source_id} does not declare {capability}")
                    if source.role not in CAPABILITY_ALLOWED_ROLES[capability]:
                        raise ValueError(f"source role {source.role} cannot establish {capability}")
                evidence_hashes = tuple(require_sha256(item, "evidence_hash") for item in row.get("evidence_hashes", []))
                if status == "PASS" and not evidence_hashes:
                    raise ValueError("PASS requires resolved raw evidence")
                missing_hashes = sorted(set(evidence_hashes) - manifest_hashes)
                if missing_hashes:
                    raise ValueError("evidence hash does not resolve in the raw manifest")
                if status == "PASS":
                    declared_sources = set(source_ids)
                    unbound_hashes = sorted(
                        digest
                        for digest in set(evidence_hashes)
                        if not any(
                            digest in hashes_by_source.get(source_id, frozenset())
                            for source_id in declared_sources
                        )
                    )
                    if unbound_hashes:
                        raise ValueError(
                            "evidence hash is not bound to a declared source: "
                            + ",".join(unbound_hashes)
                        )
                    unsupported_sources = sorted(
                        source_id
                        for source_id in declared_sources
                        if not any(
                            digest in hashes_by_source.get(source_id, frozenset())
                            for digest in evidence_hashes
                        )
                    )
                    if unsupported_sources:
                        raise ValueError(
                            "declared source has no capability evidence: "
                            + ",".join(unsupported_sources)
                        )
                normalized_path = str(row.get("normalized_path", ""))
                if status == "PASS" and not normalized_path.startswith("normalized/"):
                    raise ValueError("PASS requires a normalized/ artifact path")
                normalized_sha256 = require_sha256(row.get("normalized_sha256"), "normalized_sha256") if status == "PASS" else str(row.get("normalized_sha256", ""))
                validator_id = str(row.get("validator_id", ""))
                validator_version = str(row.get("validator_version", ""))
                if status == "PASS" and (not validator_id.startswith("kubo.") or not validator_version):
                    raise ValueError("PASS requires a versioned KU-BO validator")
                validated = parse_aware(row.get("validated_at"), "validated_at")
                if report_as_of is not None and validated < report_as_of:
                    raise ValueError("validated_at precedes capability report as_of")
                if self.cutoff is not None and validated > self.cutoff:
                    raise ValueError("validated_at is after the collection cutoff")
                access_class = str(row.get("access_class", "UNKNOWN")).upper()
                if status == "PASS" and capability in EXECUTION_CAPABILITIES and access_class not in AUTHORIZED_ACCESS:
                    raise ValueError("execution capability requires authorized access class")
                numerator = int(row.get("coverage_numerator", 0))
                denominator = int(row.get("coverage_denominator", 0))
                if numerator < 0 or denominator < 0 or numerator > denominator:
                    raise ValueError("invalid coverage counts")
                if status == "PASS" and (denominator == 0 or numerator != denominator):
                    raise ValueError("PASS requires a reconciled coverage denominator")
                parsed_rows.append(
                    CapabilityAttestation(
                        capability=capability,
                        status=status,
                        source_ids=source_ids,
                        evidence_hashes=evidence_hashes,
                        normalized_path=normalized_path,
                        normalized_sha256=normalized_sha256,
                        validator_id=validator_id,
                        validator_version=validator_version,
                        validated_at=validated.isoformat(),
                        access_class=access_class,
                        coverage_numerator=numerator,
                        coverage_denominator=denominator,
                        limitations=tuple(str(item) for item in row.get("limitations", [])),
                    )
                )
            except (TypeError, ValueError) as exc:
                errors.append(f"{prefix}:{exc}")
        passed = frozenset(item.capability for item in parsed_rows if item.status == "PASS")
        return CapabilityResult("PASS" if not errors else "BLOCKED", passed if not errors else frozenset(), tuple(parsed_rows), tuple(errors))


__all__ = [
    "AUTHORIZED_ACCESS",
    "CapabilityAttestation",
    "CapabilityReport",
    "CapabilityResult",
    "EXECUTION_CAPABILITIES",
]
