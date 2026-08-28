"""Bounded, data-only YAML loading for GitHub workflow contracts."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class WorkflowYamlError(ValueError):
    """Raised when a workflow is not bounded, unique-key, data-only YAML."""


def load_workflow_yaml(
    content: bytes,
    *,
    field: str,
    max_nodes: int = 20_000,
    max_depth: int = 64,
) -> dict[str, Any]:
    """Load a workflow with string-preserving scalars and unique mapping keys.

    PyYAML is intentionally a test/workflow-validator dependency rather than a
    runtime engine dependency. Callers fail closed when it is unavailable.
    ``BaseLoader`` keeps YAML 1.1 words such as ``on`` and ``false`` as strings,
    which is required when validating GitHub's workflow syntax.
    """

    if not isinstance(content, bytes):
        raise WorkflowYamlError(f"{field} must be bytes")
    try:
        text = content.decode("utf-8")
    except UnicodeError as exc:
        raise WorkflowYamlError(f"{field} must be UTF-8 YAML") from exc
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - exercised in lean runtimes.
        raise WorkflowYamlError(
            f"{field} requires the pinned PyYAML workflow-validator dependency"
        ) from exc

    class UniqueKeyBaseLoader(yaml.BaseLoader):
        pass

    def construct_unique_mapping(loader: Any, node: Any, deep: bool = False) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node, deep=deep)
            if not isinstance(key, str) or not key:
                raise WorkflowYamlError(f"{field} mapping keys must be non-empty strings")
            if key in result:
                raise WorkflowYamlError(f"{field} contains duplicate key: {key}")
            result[key] = loader.construct_object(value_node, deep=deep)
        return result

    UniqueKeyBaseLoader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
        construct_unique_mapping,
    )
    try:
        for event in yaml.parse(text, Loader=UniqueKeyBaseLoader):
            if (
                isinstance(event, yaml.events.AliasEvent)
                or getattr(event, "anchor", None) is not None
                or getattr(event, "tag", None) is not None
                or bool(getattr(event, "tags", None))
            ):
                raise WorkflowYamlError(
                    f"{field} YAML aliases are not admitted; anchors and explicit tags are forbidden"
                )
        payload = yaml.load(text, Loader=UniqueKeyBaseLoader)
    except WorkflowYamlError:
        raise
    except (RecursionError, yaml.YAMLError) as exc:
        raise WorkflowYamlError(f"{field} must be valid bounded YAML") from exc
    if not isinstance(payload, Mapping):
        raise WorkflowYamlError(f"{field} must contain a YAML mapping")

    seen: set[int] = set()
    node_count = 0

    def validate_node(value: Any, depth: int) -> None:
        nonlocal node_count
        node_count += 1
        if node_count > max_nodes or depth > max_depth:
            raise WorkflowYamlError(f"{field} exceeds the structural budget")
        if isinstance(value, Mapping):
            identity = id(value)
            if identity in seen:
                raise WorkflowYamlError(f"{field} YAML aliases are not admitted")
            seen.add(identity)
            for key, item in value.items():
                if not isinstance(key, str) or not key:
                    raise WorkflowYamlError(
                        f"{field} mapping keys must be non-empty strings"
                    )
                validate_node(item, depth + 1)
            return
        if isinstance(value, list):
            identity = id(value)
            if identity in seen:
                raise WorkflowYamlError(f"{field} YAML aliases are not admitted")
            seen.add(identity)
            for item in value:
                validate_node(item, depth + 1)
            return
        if value is not None and not isinstance(value, str):
            raise WorkflowYamlError(f"{field} contains a non-data YAML value")

    validate_node(payload, 0)
    return dict(payload)


__all__ = ["WorkflowYamlError", "load_workflow_yaml"]
