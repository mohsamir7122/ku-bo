"""Strict configuration contract for the isolated bootstrap archive.

The contract defines storage and stage boundaries only.  It does not activate
historical sources, authorize collection, or promote the archive into a factor,
forecast, recommendation, or Boursa Kuwait reconciliation result.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Mapping

from ..foundation_io import load_strict_json_object
from ..historical_knowledge import HistoricalKnowledgeCatalog, LAYER_IDS
from ..strict import safe_relative_path


ARCHIVE_KIND = "KUWAIT_HISTORICAL_BOOTSTRAP"
EXPECTED_HISTORICAL_SOURCE_COUNT = 28
ARCHIVE_SECTION_IDS = (
    "KUWAIT_GENERAL_HISTORY",
    "COMMERCIAL_ECONOMIC_HISTORY",
    "COMPANY_HISTORY",
    "LEGAL_REGULATORY_HISTORY",
    "COMMUNITY_ARCHIVAL_CONTEXT",
)
ARCHIVE_SECTION_LAYER_IDS = (
    ("KUWAIT_YEARBOOK_1500_PRESENT",),
    (
        "COMMERCIAL_CRISIS_CHRONOLOGY_1927_PRESENT",
        "RECENT_ECONOMIC_EVENTS_ROLLING_5Y",
    ),
    ("COMPANY_LIFECYCLE_1970_PRESENT",),
    ("COMPANY_CASES_ROLLING_20Y",),
    ("COMPANY_MEDIA_HISTORY_1980_PRESENT",),
)
STAGE_IDS = (
    "BOOTSTRAP_ARCHIVE",
    "COMPANY_INTELLIGENCE",
    "SOURCE_WAVES",
    "BOURSA_OFFICIAL_RECONCILIATION",
)
STAGE_INITIAL_STATUSES = (
    "EMPTY_ARCHIVE_PREPARED_COLLECTION_BLOCKED",
    "BLOCKED_PENDING_BOOTSTRAP_VALIDATION_AND_OFFICIAL_UNIVERSE",
    "BLOCKED_PENDING_COMPANY_INTELLIGENCE",
    "BLOCKED_PENDING_SOURCE_WAVES",
)
ARCHIVE_DIRECTORIES = (
    "control",
    "historical",
    "manifests",
    "stages",
    "raw/primary_official",
    "raw/primary_archive",
    "raw/intergovernmental",
    "raw/editorial",
    "raw/community",
    "raw/routing_only",
    "normalized/events",
    "normalized/economic",
    "normalized/companies",
    "normalized/legal_regulatory",
    "receipts/capture",
    "receipts/search",
    "receipts/rights",
    "indexes/year",
    "indexes/company",
    "quarantine",
    "reports",
)

_SAFE_COMPONENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{index}" for index in range(1, 10)}
    | {f"LPT{index}" for index in range(1, 10)}
)


def _strict_object(
    value: Any,
    *,
    keys: frozenset[str],
    label: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    missing = sorted(keys - set(value))
    extra = sorted(set(value) - keys)
    if missing or extra:
        raise ValueError(f"{label} has missing={missing} extra={extra}")
    return value


def _canonical_relative_directory(value: Any, *, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or "\\" in value
    ):
        raise ValueError(f"{field} must be a canonical relative directory")
    relative = safe_relative_path(value, field)
    if (
        relative.as_posix() != value
        or any(
            part in {"", ".", ".."}
            or not _SAFE_COMPONENT_RE.fullmatch(part)
            or part.split(".", 1)[0].upper() in _WINDOWS_RESERVED_NAMES
            for part in relative.parts
        )
    ):
        raise ValueError(f"{field} must be a canonical relative directory")
    return value


@dataclass(frozen=True)
class ArchiveSection:
    section_id: str
    layer_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"section_id": self.section_id, "layer_ids": list(self.layer_ids)}


@dataclass(frozen=True)
class ArchiveStage:
    stage_id: str
    order: int
    depends_on: tuple[str, ...]
    initial_status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage_id": self.stage_id,
            "order": self.order,
            "depends_on": list(self.depends_on),
            "status": self.initial_status,
        }


@dataclass(frozen=True)
class BootstrapArchiveContract:
    source_path: Path
    source_bytes: bytes
    archive_kind: str
    sections: tuple[ArchiveSection, ...]
    stages: tuple[ArchiveStage, ...]
    directories: tuple[str, ...]
    storage_policy: Mapping[str, Any]
    claim_boundaries: Mapping[str, bool]

    def validate_against(self, catalog: HistoricalKnowledgeCatalog) -> None:
        configured_layer_rows = [
            layer_id for section in self.sections for layer_id in section.layer_ids
        ]
        configured_layers = set(configured_layer_rows)
        catalog_layers = {layer.layer_id for layer in catalog.layers}
        if (
            configured_layers != catalog_layers
            or configured_layers != set(LAYER_IDS)
            or len(configured_layer_rows) != len(configured_layers)
        ):
            raise ValueError(
                "bootstrap archive sections must partition every historical layer exactly once"
            )
        if len(catalog.sources) != EXPECTED_HISTORICAL_SOURCE_COUNT:
            raise ValueError(
                "bootstrap archive schema 1.0 requires exactly 28 historical sources"
            )

    def stage_states(self) -> list[dict[str, Any]]:
        return [stage.to_dict() for stage in self.stages]

    def report(self, catalog: HistoricalKnowledgeCatalog) -> dict[str, Any]:
        self.validate_against(catalog)
        return {
            "status": "PASS_CONTRACT",
            "archive_kind": self.archive_kind,
            "archive_section_count": len(self.sections),
            "stage_count": len(self.stages),
            "directory_count": len(self.directories),
            "historical_source_count": len(catalog.sources),
            "historical_layer_count": len(catalog.layers),
            "source_runtime_binding_status": "ALL_UNBOUND",
            "claim_boundaries": dict(self.claim_boundaries),
        }


_ROOT_KEYS = frozenset(
    {
        "schema_version",
        "archive_kind",
        "decision_use",
        "source_crosswalk",
        "storage_policy",
        "archive_sections",
        "stages",
        "directories",
        "claim_boundaries",
    }
)
_STORAGE_KEYS = frozenset(
    {
        "corpus_location",
        "raw_content_committed_to_git",
        "no_overwrite",
        "atomic_publication_required",
        "source_runtime_binding_required_before_collection",
    }
)
_SECTION_KEYS = frozenset({"section_id", "layer_ids"})
_STAGE_KEYS = frozenset({"stage_id", "order", "depends_on", "initial_status"})
_CLAIM_KEYS = frozenset(
    {
        "historical_corpus_collected",
        "historical_completeness_claim_allowed",
        "company_intelligence_ready",
        "source_waves_ready",
        "boursa_reconciliation_ready",
        "direct_trading_decision_allowed",
    }
)


def load_bootstrap_archive_contract(path: Path) -> BootstrapArchiveContract:
    payload, source_bytes = load_strict_json_object(
        path,
        field="bootstrap archive contract",
    )
    root = _strict_object(payload, keys=_ROOT_KEYS, label="bootstrap archive contract")
    if root["schema_version"] != "1.0":
        raise ValueError("bootstrap archive contract must be schema 1.0")
    if root["archive_kind"] != ARCHIVE_KIND or root["decision_use"] != "CONTEXT_ONLY":
        raise ValueError("bootstrap archive must remain isolated CONTEXT_ONLY history")
    if root["source_crosswalk"] != "historical_source_network_crosswalk.json":
        raise ValueError("bootstrap archive must use the declared historical source crosswalk")

    storage = _strict_object(
        root["storage_policy"],
        keys=_STORAGE_KEYS,
        label="bootstrap archive storage policy",
    )
    expected_storage = {
        "corpus_location": "RUNTIME_UNTRACKED_ONLY",
        "raw_content_committed_to_git": False,
        "no_overwrite": True,
        "atomic_publication_required": True,
        "source_runtime_binding_required_before_collection": True,
    }
    if dict(storage) != expected_storage:
        raise ValueError("bootstrap archive storage policy cannot weaken isolation")

    section_rows = root["archive_sections"]
    if not isinstance(section_rows, list):
        raise ValueError("bootstrap archive sections must be an array")
    sections: list[ArchiveSection] = []
    for index, value in enumerate(section_rows):
        row = _strict_object(value, keys=_SECTION_KEYS, label=f"archive section[{index}]")
        layer_ids = row["layer_ids"]
        if (
            not isinstance(layer_ids, list)
            or not layer_ids
            or any(not isinstance(item, str) or not item for item in layer_ids)
            or len(layer_ids) != len(set(layer_ids))
        ):
            raise ValueError("archive section layer_ids must be unique non-empty strings")
        sections.append(
            ArchiveSection(
                section_id=str(row["section_id"]),
                layer_ids=tuple(layer_ids),
            )
        )
    if tuple(section.section_id for section in sections) != ARCHIVE_SECTION_IDS:
        raise ValueError("bootstrap archive section order or membership is invalid")
    if tuple(section.layer_ids for section in sections) != ARCHIVE_SECTION_LAYER_IDS:
        raise ValueError("bootstrap archive schema 1.0 section-layer mapping is invalid")

    stage_rows = root["stages"]
    if not isinstance(stage_rows, list):
        raise ValueError("bootstrap archive stages must be an array")
    stages: list[ArchiveStage] = []
    for index, value in enumerate(stage_rows):
        row = _strict_object(value, keys=_STAGE_KEYS, label=f"archive stage[{index}]")
        depends_on = row["depends_on"]
        if (
            isinstance(row["order"], bool)
            or not isinstance(row["order"], int)
            or not isinstance(depends_on, list)
            or any(not isinstance(item, str) for item in depends_on)
            or len(depends_on) != len(set(depends_on))
        ):
            raise ValueError("bootstrap archive stage order or dependencies are invalid")
        stages.append(
            ArchiveStage(
                stage_id=str(row["stage_id"]),
                order=row["order"],
                depends_on=tuple(depends_on),
                initial_status=str(row["initial_status"]),
            )
        )
    if tuple(stage.stage_id for stage in stages) != STAGE_IDS:
        raise ValueError("bootstrap archive stage order or membership is invalid")
    if tuple(stage.order for stage in stages) != tuple(range(1, len(STAGE_IDS) + 1)):
        raise ValueError("bootstrap archive stages must be consecutively ordered")
    if tuple(stage.initial_status for stage in stages) != STAGE_INITIAL_STATUSES:
        raise ValueError("bootstrap archive stage statuses cannot claim readiness")
    expected_dependencies = ((), (STAGE_IDS[0],), (STAGE_IDS[1],), (STAGE_IDS[2],))
    if tuple(stage.depends_on for stage in stages) != expected_dependencies:
        raise ValueError("bootstrap archive stage dependencies are invalid")

    directories = root["directories"]
    if (
        not isinstance(directories, list)
        or not directories
        or any(not isinstance(item, str) for item in directories)
        or len(directories) != len(set(directories))
    ):
        raise ValueError("bootstrap archive directories must be unique strings")
    normalized_directories = tuple(
        _canonical_relative_directory(
            item,
            field=f"bootstrap archive directories[{index}]",
        )
        for index, item in enumerate(directories)
    )
    if normalized_directories != ARCHIVE_DIRECTORIES:
        raise ValueError(
            "bootstrap archive directories must match the frozen scaffold layout"
        )

    boundaries = _strict_object(
        root["claim_boundaries"],
        keys=_CLAIM_KEYS,
        label="bootstrap archive claim boundaries",
    )
    if any(value is not False for value in boundaries.values()):
        raise ValueError("bootstrap archive readiness and decision claims must remain false")

    return BootstrapArchiveContract(
        source_path=Path(path),
        source_bytes=source_bytes,
        archive_kind=ARCHIVE_KIND,
        sections=tuple(sections),
        stages=tuple(stages),
        directories=normalized_directories,
        storage_policy=dict(storage),
        claim_boundaries={key: False for key in sorted(_CLAIM_KEYS)},
    )


__all__ = [
    "ARCHIVE_KIND",
    "EXPECTED_HISTORICAL_SOURCE_COUNT",
    "ARCHIVE_DIRECTORIES",
    "ARCHIVE_SECTION_IDS",
    "ARCHIVE_SECTION_LAYER_IDS",
    "STAGE_IDS",
    "STAGE_INITIAL_STATUSES",
    "ArchiveSection",
    "ArchiveStage",
    "BootstrapArchiveContract",
    "load_bootstrap_archive_contract",
]
