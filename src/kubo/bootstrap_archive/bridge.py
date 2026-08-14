"""Declared-only bridge between historical semantics and runtime source IDs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from ..foundation_io import load_strict_json_object
from ..historical_knowledge import HistoricalKnowledgeCatalog
from ..source_network import SourceNetworkCatalog


BRIDGE_STATUSES = frozenset(
    {"DECLARED_MAPPING_ONLY", "PARTIAL_DECLARED_MAPPING", "UNMAPPED_DEFINED_ONLY"}
)
EXPECTED_BRIDGE_STATUS_COUNTS = {
    "DECLARED_MAPPING_ONLY": 10,
    "PARTIAL_DECLARED_MAPPING": 11,
    "UNMAPPED_DEFINED_ONLY": 7,
}
EXPECTED_MAPPED_HISTORICAL_SOURCE_COUNT = 21


def _strict_object(value: Any, *, keys: frozenset[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    missing = sorted(keys - set(value))
    extra = sorted(set(value) - keys)
    if missing or extra:
        raise ValueError(f"{label} has missing={missing} extra={extra}")
    return value


@dataclass(frozen=True)
class HistoricalSourceBridge:
    historical_source_id: str
    network_source_ids: tuple[str, ...]
    bridge_status: str
    semantic_limit: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "historical_source_id": self.historical_source_id,
            "network_source_ids": list(self.network_source_ids),
            "bridge_status": self.bridge_status,
            "collection_allowed": False,
            "semantic_limit": self.semantic_limit,
        }


@dataclass(frozen=True)
class HistoricalSourceNetworkCrosswalk:
    source_path: Path
    source_bytes: bytes
    bindings: tuple[HistoricalSourceBridge, ...]

    def validate_against(
        self,
        historical_catalog: HistoricalKnowledgeCatalog,
        network_catalog: SourceNetworkCatalog,
    ) -> None:
        historical_ids = {item.source_id for item in historical_catalog.sources}
        binding_ids = {item.historical_source_id for item in self.bindings}
        if binding_ids != historical_ids or len(binding_ids) != len(self.bindings):
            raise ValueError("historical source crosswalk must cover every source exactly")
        network_ids = set(network_catalog.sources)
        for binding in self.bindings:
            if set(binding.network_source_ids) - network_ids:
                raise ValueError("historical source crosswalk references an unknown network source")
            if binding.bridge_status == "UNMAPPED_DEFINED_ONLY" and binding.network_source_ids:
                raise ValueError("an unmapped historical source cannot name network sources")
            if binding.bridge_status != "UNMAPPED_DEFINED_ONLY" and not binding.network_source_ids:
                raise ValueError("a declared historical mapping requires network sources")

    def report(
        self,
        historical_catalog: HistoricalKnowledgeCatalog,
        network_catalog: SourceNetworkCatalog,
    ) -> dict[str, Any]:
        self.validate_against(historical_catalog, network_catalog)
        counts = {status: 0 for status in sorted(BRIDGE_STATUSES)}
        for binding in self.bindings:
            counts[binding.bridge_status] += 1
        mapped_count = sum(bool(item.network_source_ids) for item in self.bindings)
        if (
            counts != EXPECTED_BRIDGE_STATUS_COUNTS
            or mapped_count != EXPECTED_MAPPED_HISTORICAL_SOURCE_COUNT
        ):
            raise ValueError(
                "historical source crosswalk must preserve the frozen schema 1.0 mapping profile"
            )
        return {
            "status": "PASS_CONTRACT",
            "readiness_status": "DEFINED_ONLY",
            "historical_source_count": len(self.bindings),
            "bridge_status_counts": counts,
            "mapped_historical_source_count": mapped_count,
            "collection_allowed": False,
            "live_operational": False,
        }


_ROOT_KEYS = frozenset({"schema_version", "capability_claim", "bindings", "claim_boundaries"})
_BINDING_KEYS = frozenset(
    {"historical_source_id", "network_source_ids", "bridge_status", "collection_allowed", "semantic_limit"}
)
_CLAIM_KEYS = frozenset(
    {
        "crosswalk_is_connector_implementation",
        "crosswalk_is_parser_validation",
        "crosswalk_is_live_operational",
        "collection_allowed",
    }
)


def load_historical_source_network_crosswalk(
    path: Path,
) -> HistoricalSourceNetworkCrosswalk:
    payload, source_bytes = load_strict_json_object(
        path,
        field="historical source network crosswalk",
    )
    root = _strict_object(payload, keys=_ROOT_KEYS, label="historical source network crosswalk")
    if root["schema_version"] != "1.0" or root["capability_claim"] != "DEFINED_ONLY":
        raise ValueError("historical source network crosswalk must remain DEFINED_ONLY schema 1.0")
    boundaries = _strict_object(
        root["claim_boundaries"],
        keys=_CLAIM_KEYS,
        label="historical source crosswalk claim boundaries",
    )
    if any(value is not False for value in boundaries.values()):
        raise ValueError("historical source crosswalk claims must remain false")
    rows = root["bindings"]
    if not isinstance(rows, list) or not rows:
        raise ValueError("historical source network crosswalk requires bindings")
    bindings: list[HistoricalSourceBridge] = []
    seen: set[str] = set()
    for index, value in enumerate(rows):
        row = _strict_object(value, keys=_BINDING_KEYS, label=f"source bridge[{index}]")
        historical_source_id = row["historical_source_id"]
        network_source_ids = row["network_source_ids"]
        bridge_status = row["bridge_status"]
        if not isinstance(historical_source_id, str) or not historical_source_id or historical_source_id in seen:
            raise ValueError("historical source bridge IDs must be unique non-empty strings")
        seen.add(historical_source_id)
        if (
            not isinstance(network_source_ids, list)
            or len(network_source_ids) > 3
            or any(not isinstance(item, str) or not item for item in network_source_ids)
            or len(network_source_ids) != len(set(network_source_ids))
        ):
            raise ValueError("network source bridge IDs must contain at most three unique strings")
        if bridge_status not in BRIDGE_STATUSES:
            raise ValueError("historical source bridge status is invalid")
        if row["collection_allowed"] is not False:
            raise ValueError("declared historical source bridges cannot authorize collection")
        semantic_limit = row["semantic_limit"]
        if (
            not isinstance(semantic_limit, str)
            or not semantic_limit
            or len(semantic_limit) > 2048
            or "\n" in semantic_limit
            or "\r" in semantic_limit
            or semantic_limit != semantic_limit.strip()
        ):
            raise ValueError(
                "historical source bridge requires a trimmed semantic limit of at most 2048 characters"
            )
        bindings.append(
            HistoricalSourceBridge(
                historical_source_id=historical_source_id,
                network_source_ids=tuple(network_source_ids),
                bridge_status=bridge_status,
                semantic_limit=semantic_limit,
            )
        )
    return HistoricalSourceNetworkCrosswalk(
        source_path=Path(path),
        source_bytes=source_bytes,
        bindings=tuple(bindings),
    )


__all__ = [
    "BRIDGE_STATUSES",
    "EXPECTED_BRIDGE_STATUS_COUNTS",
    "EXPECTED_MAPPED_HISTORICAL_SOURCE_COUNT",
    "HistoricalSourceBridge",
    "HistoricalSourceNetworkCrosswalk",
    "load_historical_source_network_crosswalk",
]
