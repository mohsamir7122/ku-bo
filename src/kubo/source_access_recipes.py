"""Fail-closed source-access recipes and capability-probe plans.

Recipes describe how an operator may test a registered source without claiming
that a connector, parser, market feed, or reusable dataset exists.  Probe plans
are metadata-only artifacts; the existing live-probe contract remains the
hash-bound receipt for any later operator-performed attempt.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

from .hashing import hash_json, sha256_file
from .source_network import SourceNetworkCatalog, validate_live_probe
from .strict import https_url, parse_aware


RECIPE_CAPABILITY_STATUS = "DEFINED_ONLY"
ROUTE_KINDS = frozenset(
    {
        "STABLE_PUBLIC_PAGE",
        "PUBLIC_DOWNLOAD_INDEX",
        "DYNAMIC_RENDERED_PAGE",
        "AUTHORIZED_USER_EXPORT",
        "AUTHORIZED_ACCOUNT_PAGE",
        "PUBLIC_ARCHIVE_INDEX",
        "LICENSED_OR_BROKER_EXPORT",
    }
)
CAPTURE_METHODS = frozenset(
    {"HTTP_GET", "BROWSER_RENDERED", "USER_EXPORT", "SEARCH_QUERY", "LICENSED_EXPORT"}
)
PURPOSE_CLASSES = frozenset(
    {"DISPLAY_OR_DISTRIBUTION", "NON_DISPLAY", "EXECUTION", "ROUTING_ONLY"}
)
COLLECTION_FREQUENCIES = frozenset({"ONE_OFF", "SYSTEMATIC"})
RIGHTS_STATUSES = frozenset(
    {"PUBLIC_ACCESS_ONLY", "AUTHORIZED", "LICENSED", "USER_SUPPLIED_AUTHORIZED_EXPORT"}
)
PROBE_STATES = frozenset(
    {"AVAILABLE", "PARTIAL", "BLOCKED", "ERROR", "AUTH_REQUIRED", "UNTESTED"}
)
ARTIFACT_POLICIES = frozenset({"REQUIRED_WHEN_READABLE"})
IMPORTER_IDS = frozenset({"INVESTING_USER_PRICE_EXPORT_V1"})
PROMOTION_CEILINGS = frozenset({"PRICE_IMPORT_READY_ONLY"})
MAX_PLAN_TASKS = 32
MAX_PLAN_TOTAL_BYTES = 128 * 1024 * 1024
MAX_PLAN_TOTAL_TIMEOUT_SECONDS = 300

_RECIPE_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{2,95}$")
_REASON_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,127}$")
_ACCESS_CAPTURE_COMPATIBILITY = {
    "PUBLIC_PAGE": frozenset({"HTTP_GET", "BROWSER_RENDERED"}),
    "PUBLIC_DOWNLOAD": frozenset({"HTTP_GET", "BROWSER_RENDERED"}),
    "AUTHORIZED_BROWSER": frozenset({"BROWSER_RENDERED"}),
    "AUTHORIZED_ACCOUNT": frozenset({"BROWSER_RENDERED", "USER_EXPORT"}),
    "USER_EXPORT": frozenset({"USER_EXPORT"}),
    "PUBLIC_INDEX": frozenset({"SEARCH_QUERY", "HTTP_GET"}),
    "SEARCH_INDEX_ONLY": frozenset({"SEARCH_QUERY"}),
    "LICENSED_VENDOR": frozenset({"LICENSED_EXPORT"}),
    "BROKER_AUTHENTICATED_EXPORT": frozenset({"LICENSED_EXPORT"}),
}
_ACCESS_RIGHTS_COMPATIBILITY = {
    "PUBLIC_PAGE": frozenset({"PUBLIC_ACCESS_ONLY"}),
    "PUBLIC_DOWNLOAD": frozenset({"PUBLIC_ACCESS_ONLY"}),
    "AUTHORIZED_BROWSER": frozenset({"AUTHORIZED"}),
    "AUTHORIZED_ACCOUNT": frozenset({"AUTHORIZED"}),
    "USER_EXPORT": frozenset({"USER_SUPPLIED_AUTHORIZED_EXPORT"}),
    "PUBLIC_INDEX": frozenset({"PUBLIC_ACCESS_ONLY"}),
    "SEARCH_INDEX_ONLY": frozenset({"PUBLIC_ACCESS_ONLY"}),
    "LICENSED_VENDOR": frozenset({"LICENSED"}),
    "BROKER_AUTHENTICATED_EXPORT": frozenset({"LICENSED"}),
}
_ROUTE_ACCESS_COMPATIBILITY = {
    "STABLE_PUBLIC_PAGE": frozenset(
        {("PUBLIC_PAGE", "HTTP_GET"), ("PUBLIC_PAGE", "BROWSER_RENDERED")}
    ),
    "PUBLIC_DOWNLOAD_INDEX": frozenset(
        {
            ("PUBLIC_DOWNLOAD", "HTTP_GET"),
            ("PUBLIC_DOWNLOAD", "BROWSER_RENDERED"),
        }
    ),
    "DYNAMIC_RENDERED_PAGE": frozenset(
        {
            ("PUBLIC_PAGE", "BROWSER_RENDERED"),
            ("AUTHORIZED_BROWSER", "BROWSER_RENDERED"),
            ("AUTHORIZED_ACCOUNT", "BROWSER_RENDERED"),
        }
    ),
    "AUTHORIZED_USER_EXPORT": frozenset({("USER_EXPORT", "USER_EXPORT")}),
    "AUTHORIZED_ACCOUNT_PAGE": frozenset(
        {
            ("AUTHORIZED_BROWSER", "BROWSER_RENDERED"),
            ("AUTHORIZED_ACCOUNT", "BROWSER_RENDERED"),
        }
    ),
    "PUBLIC_ARCHIVE_INDEX": frozenset(
        {
            ("PUBLIC_PAGE", "BROWSER_RENDERED"),
            ("PUBLIC_INDEX", "SEARCH_QUERY"),
            ("PUBLIC_DOWNLOAD", "HTTP_GET"),
        }
    ),
    "LICENSED_OR_BROKER_EXPORT": frozenset(
        {
            ("LICENSED_VENDOR", "LICENSED_EXPORT"),
            ("BROKER_AUTHENTICATED_EXPORT", "LICENSED_EXPORT"),
        }
    ),
}

RECIPE_CLAIM_BOUNDARIES = {
    "recipe_is_connector": False,
    "plan_executes_network_access": False,
    "access_probe_is_market_evidence": False,
    "access_probe_is_live_operational": False,
    "manual_export_is_official_eod": False,
    "manual_export_is_execution_tape": False,
    "price_import_ready_is_forecast_ready": False,
}

PLAN_CLAIM_BOUNDARIES = {
    "network_access_executed": False,
    "market_data_collected": False,
    "market_evidence_created": False,
    "live_operational_claim_allowed": False,
    "forecast_or_recommendation_allowed": False,
    "probe_may_bypass_access_controls": False,
}

PROBE_CLAIM_BOUNDARIES = {
    "plan_bound_access_only": True,
    "access_probe_is_market_evidence": False,
    "access_probe_is_historical_coverage": False,
    "access_probe_is_live_operational": False,
    "access_probe_is_forecast": False,
    "access_probe_authorizes_bypass": False,
}


def _reject_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-JSON numeric constant: {value}")


def _strict_json(path: Path) -> Mapping[str, Any]:
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_pairs,
            parse_constant=_reject_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError(f"cannot load strict JSON: {path}") from exc
    if not isinstance(payload, Mapping):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def _strict_object(value: Any, *, keys: frozenset[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    missing = sorted(keys - set(value))
    extra = sorted(set(value) - keys)
    if missing or extra:
        raise ValueError(f"{label} has missing={missing} extra={extra}")
    return value


def _positive_int(value: Any, field: str, *, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise ValueError(f"{field} must be an integer in 1..{maximum}")
    return value


@dataclass(frozen=True)
class ProbeBudget:
    max_attempts: int
    timeout_seconds: int
    max_bytes: int
    valid_for_hours: int


@dataclass(frozen=True)
class SourceAccessRecipe:
    recipe_id: str
    source_ids: tuple[str, ...]
    capability_status: str
    route_kind: str
    access_mode: str
    capture_method: str
    purpose_class: str
    collection_frequency: str
    rights_status: str
    allowed_states: tuple[str, ...]
    terminal_reason_codes: tuple[str, ...]
    artifact_policy: str
    notes: str


@dataclass(frozen=True)
class ManualImporter:
    importer_id: str
    source_id: str
    input_mode: str
    cli_command: str
    required_manifest: str
    promotion_ceiling: str
    claim_boundaries: dict[str, bool]


class SourceAccessRecipeCatalog:
    """Validate recipes against the source network and rights boundaries."""

    _ROOT_KEYS = frozenset(
        {
            "schema_version",
            "recipe_set_id",
            "capability_status",
            "defaults",
            "probe_reason_vocabulary",
            "recipes",
            "manual_importers",
            "claim_boundaries",
        }
    )
    _DEFAULT_KEYS = frozenset(
        {"max_attempts", "timeout_seconds", "max_bytes", "valid_for_hours"}
    )
    _RECIPE_KEYS = frozenset(
        {
            "recipe_id",
            "source_ids",
            "capability_status",
            "route_kind",
            "access_mode",
            "capture_method",
            "purpose_class",
            "collection_frequency",
            "rights_status",
            "allowed_states",
            "terminal_reason_codes",
            "artifact_policy",
            "notes",
        }
    )
    _IMPORTER_KEYS = frozenset(
        {
            "importer_id",
            "source_id",
            "input_mode",
            "cli_command",
            "required_manifest",
            "promotion_ceiling",
            "claim_boundaries",
        }
    )
    _IMPORTER_BOUNDARIES = {
        "official_identity_ready": False,
        "official_eod_ready": False,
        "execution_ready": False,
        "forecast_ready": False,
    }

    def __init__(self, path: Path, source_catalog: SourceNetworkCatalog):
        self.path = path
        self.registry_sha256 = sha256_file(path)
        payload = _strict_object(
            _strict_json(path), keys=self._ROOT_KEYS, label="source access recipe registry"
        )
        if payload["schema_version"] != "1.0":
            raise ValueError("source access recipes must use schema 1.0")
        self.recipe_set_id = str(payload["recipe_set_id"]).strip()
        if not _RECIPE_ID_RE.fullmatch(self.recipe_set_id):
            raise ValueError("recipe_set_id is invalid")
        if payload["capability_status"] != RECIPE_CAPABILITY_STATUS:
            raise ValueError("source access recipes must remain DEFINED_ONLY")
        if payload["claim_boundaries"] != RECIPE_CLAIM_BOUNDARIES:
            raise ValueError("source access recipe claim boundaries were weakened")
        self.budget = self._load_budget(payload["defaults"])
        self.reason_vocabulary = self._load_reason_vocabulary(
            payload["probe_reason_vocabulary"]
        )
        self.recipes, self.recipe_by_source = self._load_recipes(
            payload["recipes"], source_catalog
        )
        self.manual_importers = self._load_importers(
            payload["manual_importers"], source_catalog
        )

    def _load_budget(self, value: Any) -> ProbeBudget:
        row = _strict_object(value, keys=self._DEFAULT_KEYS, label="recipe defaults")
        return ProbeBudget(
            max_attempts=_positive_int(row["max_attempts"], "max_attempts", maximum=3),
            timeout_seconds=_positive_int(
                row["timeout_seconds"], "timeout_seconds", maximum=60
            ),
            max_bytes=_positive_int(row["max_bytes"], "max_bytes", maximum=16 * 1024 * 1024),
            valid_for_hours=_positive_int(
                row["valid_for_hours"], "valid_for_hours", maximum=24
            ),
        )

    @staticmethod
    def _load_reason_vocabulary(value: Any) -> frozenset[str]:
        if (
            not isinstance(value, list)
            or not value
            or len(value) != len(set(value))
            or any(not isinstance(item, str) or not _REASON_RE.fullmatch(item) for item in value)
        ):
            raise ValueError("probe_reason_vocabulary must contain unique stable codes")
        return frozenset(value)

    def _load_recipes(
        self, value: Any, source_catalog: SourceNetworkCatalog
    ) -> tuple[tuple[SourceAccessRecipe, ...], dict[str, SourceAccessRecipe]]:
        if not isinstance(value, list) or not value:
            raise ValueError("source access registry requires recipes")
        recipes: list[SourceAccessRecipe] = []
        by_source: dict[str, SourceAccessRecipe] = {}
        recipe_ids: set[str] = set()
        for index, raw in enumerate(value):
            row = _strict_object(raw, keys=self._RECIPE_KEYS, label=f"recipe[{index}]")
            recipe_id = str(row["recipe_id"])
            if not _RECIPE_ID_RE.fullmatch(recipe_id) or recipe_id in recipe_ids:
                raise ValueError("recipe_id must be unique and stable")
            recipe_ids.add(recipe_id)
            source_ids_value = row["source_ids"]
            if (
                not isinstance(source_ids_value, list)
                or not source_ids_value
                or len(source_ids_value) != len(set(source_ids_value))
                or any(not isinstance(item, str) for item in source_ids_value)
            ):
                raise ValueError(f"{recipe_id}.source_ids must be unique strings")
            source_ids = tuple(source_ids_value)
            unknown = sorted(set(source_ids) - set(source_catalog.sources))
            duplicate = sorted(set(source_ids).intersection(by_source))
            if unknown or duplicate:
                raise ValueError(
                    f"{recipe_id} has unknown={unknown} duplicate_recipe_sources={duplicate}"
                )
            if row["capability_status"] != RECIPE_CAPABILITY_STATUS:
                raise ValueError(f"{recipe_id} capability cannot exceed DEFINED_ONLY")
            route_kind = str(row["route_kind"])
            capture_method = str(row["capture_method"])
            purpose_class = str(row["purpose_class"])
            frequency = str(row["collection_frequency"])
            rights_status = str(row["rights_status"])
            artifact_policy = str(row["artifact_policy"])
            access_mode = str(row["access_mode"])
            if (
                route_kind not in ROUTE_KINDS
                or capture_method not in CAPTURE_METHODS
                or purpose_class not in PURPOSE_CLASSES
                or frequency not in COLLECTION_FREQUENCIES
                or rights_status not in RIGHTS_STATUSES
                or artifact_policy not in ARTIFACT_POLICIES
            ):
                raise ValueError(f"{recipe_id} has an invalid controlled value")
            compatible = _ACCESS_CAPTURE_COMPATIBILITY.get(access_mode, frozenset())
            if capture_method not in compatible:
                raise ValueError(f"{recipe_id} access_mode/capture_method is incompatible")
            if (access_mode, capture_method) not in _ROUTE_ACCESS_COMPATIBILITY[route_kind]:
                raise ValueError(f"{recipe_id} route/access/capture is incompatible")
            if rights_status not in _ACCESS_RIGHTS_COMPATIBILITY.get(
                access_mode, frozenset()
            ):
                raise ValueError(f"{recipe_id} access_mode/rights_status is incompatible")
            states_value = row["allowed_states"]
            reasons_value = row["terminal_reason_codes"]
            if (
                not isinstance(states_value, list)
                or not states_value
                or len(states_value) != len(set(states_value))
                or set(states_value) - PROBE_STATES
            ):
                raise ValueError(f"{recipe_id}.allowed_states is invalid")
            if (
                not isinstance(reasons_value, list)
                or not reasons_value
                or len(reasons_value) != len(set(reasons_value))
                or set(reasons_value) - self.reason_vocabulary
            ):
                raise ValueError(f"{recipe_id}.terminal_reason_codes is invalid")
            notes = str(row["notes"]).strip()
            if not notes or len(notes) > 2000:
                raise ValueError(f"{recipe_id}.notes is invalid")
            sources = tuple(source_catalog.sources[source_id] for source_id in source_ids)
            if any(access_mode not in source.access_modes for source in sources):
                raise ValueError(f"{recipe_id} access_mode is not registered for every source")
            if any(not source.start_urls for source in sources):
                raise ValueError(f"{recipe_id} requires a catalog start URL for every source")
            self._validate_rights(
                recipe_id=recipe_id,
                purpose_class=purpose_class,
                frequency=frequency,
                rights_status=rights_status,
                source_classes={source.source_class for source in sources},
                source_roles=set().union(*(set(source.roles) for source in sources)),
            )
            recipe = SourceAccessRecipe(
                recipe_id=recipe_id,
                source_ids=source_ids,
                capability_status=RECIPE_CAPABILITY_STATUS,
                route_kind=route_kind,
                access_mode=access_mode,
                capture_method=capture_method,
                purpose_class=purpose_class,
                collection_frequency=frequency,
                rights_status=rights_status,
                allowed_states=tuple(states_value),
                terminal_reason_codes=tuple(reasons_value),
                artifact_policy=artifact_policy,
                notes=notes,
            )
            recipes.append(recipe)
            for source_id in source_ids:
                by_source[source_id] = recipe
        return tuple(recipes), by_source

    @staticmethod
    def _validate_rights(
        *,
        recipe_id: str,
        purpose_class: str,
        frequency: str,
        rights_status: str,
        source_classes: set[str],
        source_roles: set[str],
    ) -> None:
        if frequency == "SYSTEMATIC" and rights_status == "PUBLIC_ACCESS_ONLY":
            raise ValueError(f"{recipe_id} systematic public access is fail-closed")
        if purpose_class in {"NON_DISPLAY", "EXECUTION"} and rights_status == "PUBLIC_ACCESS_ONLY":
            raise ValueError(f"{recipe_id} purpose requires authorization or a licence")
        if "COMMUNITY" in source_classes and purpose_class != "ROUTING_ONLY":
            raise ValueError(f"{recipe_id} community access must remain routing-only")
        if "LICENSED" in source_classes and rights_status != "LICENSED":
            raise ValueError(f"{recipe_id} licensed sources require LICENSED rights")
        if purpose_class == "EXECUTION" and "EXECUTION_TAPE" not in source_roles:
            raise ValueError(f"{recipe_id} execution purpose requires an execution-tape source")

    def _load_importers(
        self, value: Any, source_catalog: SourceNetworkCatalog
    ) -> tuple[ManualImporter, ...]:
        if not isinstance(value, list):
            raise ValueError("manual_importers must be a list")
        loaded: list[ManualImporter] = []
        seen: set[str] = set()
        for index, raw in enumerate(value):
            row = _strict_object(raw, keys=self._IMPORTER_KEYS, label=f"manual_importer[{index}]")
            importer_id = str(row["importer_id"])
            source_id = str(row["source_id"])
            if importer_id not in IMPORTER_IDS or importer_id in seen:
                raise ValueError("manual importer ID is unknown or duplicated")
            seen.add(importer_id)
            if source_id not in source_catalog.sources or source_id not in self.recipe_by_source:
                raise ValueError("manual importer source is not recipe-bound")
            input_mode = str(row["input_mode"])
            if input_mode != "USER_EXPORT" or input_mode not in source_catalog.sources[source_id].access_modes:
                raise ValueError("manual importer requires a registered USER_EXPORT source")
            if row["promotion_ceiling"] not in PROMOTION_CEILINGS:
                raise ValueError("manual importer promotion ceiling was weakened")
            if row["cli_command"] != "kubo-data-foundation import-user-price-exports":
                raise ValueError("manual importer CLI command is not the reviewed importer")
            if row["required_manifest"] != "price_collection_manifest.csv":
                raise ValueError("manual importer manifest contract is invalid")
            boundaries = row["claim_boundaries"]
            if boundaries != self._IMPORTER_BOUNDARIES:
                raise ValueError("manual importer claim boundaries were weakened")
            loaded.append(
                ManualImporter(
                    importer_id=importer_id,
                    source_id=source_id,
                    input_mode=input_mode,
                    cli_command=str(row["cli_command"]),
                    required_manifest=str(row["required_manifest"]),
                    promotion_ceiling=str(row["promotion_ceiling"]),
                    claim_boundaries=dict(boundaries),
                )
            )
        return tuple(loaded)

    def report(self, source_catalog: SourceNetworkCatalog) -> dict[str, Any]:
        covered = set(self.recipe_by_source)
        class_counts: dict[str, int] = {}
        for source_id in covered:
            source_class = source_catalog.sources[source_id].source_class
            class_counts[source_class] = class_counts.get(source_class, 0) + 1
        return {
            "status": "PASS_CONTRACT",
            "readiness_status": RECIPE_CAPABILITY_STATUS,
            "recipe_set_id": self.recipe_set_id,
            "recipe_set_sha256": self.registry_sha256,
            "recipe_count": len(self.recipes),
            "covered_source_count": len(covered),
            "catalog_source_count": len(source_catalog.sources),
            "uncovered_source_count": len(source_catalog.sources) - len(covered),
            "covered_source_classes": dict(sorted(class_counts.items())),
            "manual_importer_count": len(self.manual_importers),
            "manual_importers": [asdict(item) for item in self.manual_importers],
            "claim_boundaries": dict(RECIPE_CLAIM_BOUNDARIES),
        }


def _plan_without_id(plan: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(plan)
    result["plan_id"] = ""
    return result


def compile_source_probe_plan(
    recipes: SourceAccessRecipeCatalog,
    source_catalog: SourceNetworkCatalog,
    *,
    planned_at: datetime,
    source_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    if planned_at.tzinfo is None or planned_at.utcoffset() is None:
        raise ValueError("planned_at must be timezone-aware")
    requested = (
        sorted(recipes.recipe_by_source)
        if source_ids is None
        else sorted(str(source_id) for source_id in source_ids)
    )
    if not requested or len(requested) != len(set(requested)):
        raise ValueError("source probe plan requires unique recipe-bound sources")
    unknown = sorted(set(requested) - set(recipes.recipe_by_source))
    if unknown:
        raise ValueError("source probe plan references sources without recipes: " + ",".join(unknown))
    if len(requested) > MAX_PLAN_TASKS:
        raise ValueError(f"source probe plan exceeds {MAX_PLAN_TASKS} tasks")
    if len(requested) * recipes.budget.max_bytes > MAX_PLAN_TOTAL_BYTES:
        raise ValueError("source probe plan exceeds the 128 MiB aggregate byte budget")
    if (
        len(requested) * recipes.budget.timeout_seconds
        > MAX_PLAN_TOTAL_TIMEOUT_SECONDS
    ):
        raise ValueError("source probe plan exceeds the 300-second aggregate timeout budget")
    budget = {
        "max_attempts": recipes.budget.max_attempts,
        "timeout_seconds": recipes.budget.timeout_seconds,
        "max_bytes": recipes.budget.max_bytes,
    }
    tasks: list[dict[str, Any]] = []
    for source_id in requested:
        recipe = recipes.recipe_by_source[source_id]
        source = source_catalog.sources[source_id]
        tested_url = https_url(source.start_urls[0], f"{source_id}.tested_url")
        seed = f"{recipes.registry_sha256}:{recipe.recipe_id}:{source_id}:{planned_at.isoformat()}"
        task_id = "probe-task-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]
        tasks.append(
            {
                "task_id": task_id,
                "recipe_id": recipe.recipe_id,
                "source_id": source_id,
                "source_class": source.source_class,
                "tested_url": tested_url,
                "access_mode": recipe.access_mode,
                "capture_method": recipe.capture_method,
                "purpose_class": recipe.purpose_class,
                "collection_frequency": recipe.collection_frequency,
                "rights_status": recipe.rights_status,
                "allowed_states": list(recipe.allowed_states),
                "terminal_reason_codes": list(recipe.terminal_reason_codes),
                "artifact_policy": recipe.artifact_policy,
                "budget": dict(budget),
            }
        )
    plan: dict[str, Any] = {
        "schema_version": "1.0",
        "plan_id": "",
        "recipe_set_id": recipes.recipe_set_id,
        "recipe_set_sha256": recipes.registry_sha256,
        "planned_at": planned_at.isoformat(),
        "expires_at": (planned_at + timedelta(hours=recipes.budget.valid_for_hours)).isoformat(),
        "status": "PLANNED_NOT_EXECUTED",
        "purpose": "CAPABILITY_PROBE_ONLY",
        "tasks": tasks,
        "claim_boundaries": dict(PLAN_CLAIM_BOUNDARIES),
    }
    plan["plan_id"] = "source-probe-plan-" + hash_json(_plan_without_id(plan))[:24]
    return plan


def validate_source_probe_plan(
    path: Path,
    recipes: SourceAccessRecipeCatalog,
    source_catalog: SourceNetworkCatalog,
) -> dict[str, Any]:
    try:
        payload = _strict_object(
            _strict_json(path),
            keys=frozenset(
                {
                    "schema_version",
                    "plan_id",
                    "recipe_set_id",
                    "recipe_set_sha256",
                    "planned_at",
                    "expires_at",
                    "status",
                    "purpose",
                    "tasks",
                    "claim_boundaries",
                }
            ),
            label="source probe plan",
        )
        if payload["schema_version"] != "1.0":
            raise ValueError("source probe plan schema is unsupported")
        if payload["recipe_set_id"] != recipes.recipe_set_id:
            raise ValueError("source probe plan recipe_set_id is stale")
        if payload["recipe_set_sha256"] != recipes.registry_sha256:
            raise ValueError("source probe plan recipe-set hash is stale or forged")
        if payload["status"] != "PLANNED_NOT_EXECUTED" or payload["purpose"] != "CAPABILITY_PROBE_ONLY":
            raise ValueError("source probe plan claim state was weakened")
        if payload["claim_boundaries"] != PLAN_CLAIM_BOUNDARIES:
            raise ValueError("source probe plan claim boundaries were weakened")
        planned_at = parse_aware(payload["planned_at"], "planned_at")
        expires_at = parse_aware(payload["expires_at"], "expires_at")
        if expires_at != planned_at + timedelta(hours=recipes.budget.valid_for_hours):
            raise ValueError("source probe plan expiry does not match recipe policy")
        tasks = payload["tasks"]
        if not isinstance(tasks, list) or not tasks:
            raise ValueError("source probe plan requires tasks")
        source_ids: list[str] = []
        for task in tasks:
            if not isinstance(task, Mapping) or not isinstance(task.get("source_id"), str):
                raise ValueError("source probe plan task is invalid")
            source_ids.append(str(task["source_id"]))
        expected = compile_source_probe_plan(
            recipes,
            source_catalog,
            planned_at=planned_at,
            source_ids=source_ids,
        )
        if payload != expected:
            raise ValueError("source probe plan does not reproduce from the recipe registry")
        return {
            "status": "PASS_CONTRACT",
            "plan_id": payload["plan_id"],
            "plan_sha256": sha256_file(path),
            "planned_at": planned_at.isoformat(),
            "expires_at": expires_at.isoformat(),
            "task_count": len(tasks),
            "source_ids": source_ids,
            "errors": [],
            "claim_boundaries": dict(PLAN_CLAIM_BOUNDARIES),
        }
    except (OSError, TypeError, ValueError) as exc:
        return {
            "status": "BLOCKED",
            "errors": [f"INVALID_SOURCE_PROBE_PLAN:{exc}"],
            "claim_boundaries": dict(PLAN_CLAIM_BOUNDARIES),
        }


def validate_access_probe_against_plan(
    *,
    probe_path: Path,
    plan_path: Path,
    recipes: SourceAccessRecipeCatalog,
    source_catalog: SourceNetworkCatalog,
    now: datetime | None = None,
) -> dict[str, Any]:
    plan_report = validate_source_probe_plan(plan_path, recipes, source_catalog)
    if plan_report["status"] != "PASS_CONTRACT":
        return {
            "status": "BLOCKED",
            "plan": plan_report,
            "probe": None,
            "errors": list(plan_report["errors"]),
            "claim_boundaries": dict(PROBE_CLAIM_BOUNDARIES),
        }
    try:
        _strict_json(probe_path)
    except (OSError, TypeError, ValueError) as exc:
        return {
            "status": "BLOCKED",
            "plan": plan_report,
            "probe": None,
            "errors": [f"INVALID_STRICT_ACCESS_PROBE:{exc}"],
            "claim_boundaries": dict(PROBE_CLAIM_BOUNDARIES),
        }
    probe_report = validate_live_probe(probe_path, source_catalog, now=now)
    if probe_report.get("status") != "PASS":
        return {
            "status": "BLOCKED",
            "plan": plan_report,
            "probe": probe_report,
            "errors": list(probe_report.get("errors", [])),
            "claim_boundaries": dict(PROBE_CLAIM_BOUNDARIES),
        }
    errors: list[str] = []
    plan_payload = _strict_json(plan_path)
    tasks = {str(task["source_id"]): task for task in plan_payload["tasks"]}
    probe_rows = {str(row["source_id"]): row for row in probe_report["sources"]}
    if set(tasks) != set(probe_rows):
        errors.append("PROBE_SOURCE_SET_DOES_NOT_MATCH_PLAN")
    planned_at = parse_aware(plan_payload["planned_at"], "planned_at")
    plan_expires_at = parse_aware(plan_payload["expires_at"], "expires_at")
    observed_at = parse_aware(probe_report["observed_at"], "observed_at")
    probe_expires_at = parse_aware(probe_report["expires_at"], "probe.expires_at")
    if not planned_at <= observed_at <= plan_expires_at:
        errors.append("PROBE_OBSERVATION_OUTSIDE_PLAN_WINDOW")
    if probe_expires_at > plan_expires_at:
        errors.append("PROBE_EXPIRY_EXCEEDS_PLAN_WINDOW")
    for source_id in sorted(set(tasks).intersection(probe_rows)):
        task = tasks[source_id]
        row = probe_rows[source_id]
        if row["tested_url"] != task["tested_url"]:
            errors.append(f"PROBE_TESTED_URL_MISMATCH:{source_id}")
        if row["state"] not in task["allowed_states"]:
            errors.append(f"PROBE_STATE_NOT_ALLOWED:{source_id}")
        attempted_at = parse_aware(row["attempted_at"], "attempted_at")
        if not planned_at <= attempted_at <= plan_expires_at:
            errors.append(f"PROBE_ATTEMPT_OUTSIDE_PLAN_WINDOW:{source_id}")
        flags = set(row["data_quality_flags"])
        terminal_vocabulary = flags.intersection(recipes.reason_vocabulary)
        allowed_terminal = set(task["terminal_reason_codes"])
        if terminal_vocabulary - allowed_terminal:
            errors.append(f"PROBE_REASON_NOT_ALLOWED:{source_id}")
        if row["state"] in {"BLOCKED", "AUTH_REQUIRED", "ERROR"} and not (
            terminal_vocabulary & allowed_terminal
        ):
            errors.append(f"PROBE_TERMINAL_STATE_REQUIRES_REASON:{source_id}")
        if row["state"] == "AVAILABLE" and terminal_vocabulary:
            errors.append(f"AVAILABLE_PROBE_HAS_TERMINAL_REASON:{source_id}")
    return {
        "status": "PASS_ACCESS_ONLY" if not errors else "BLOCKED",
        "plan_id": plan_report["plan_id"],
        "plan_sha256": plan_report["plan_sha256"],
        "probe_id": probe_report["probe_id"],
        "probe_hash": probe_report["probe_hash"],
        "source_count": len(probe_rows),
        "sources": probe_report["sources"],
        "errors": errors,
        "claim_boundaries": dict(PROBE_CLAIM_BOUNDARIES),
    }


__all__ = [
    "MAX_PLAN_TASKS",
    "MAX_PLAN_TOTAL_BYTES",
    "MAX_PLAN_TOTAL_TIMEOUT_SECONDS",
    "PLAN_CLAIM_BOUNDARIES",
    "PROBE_CLAIM_BOUNDARIES",
    "RECIPE_CLAIM_BOUNDARIES",
    "SourceAccessRecipeCatalog",
    "compile_source_probe_plan",
    "validate_access_probe_against_plan",
    "validate_source_probe_plan",
]
