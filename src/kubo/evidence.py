from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .catalog import Catalog
from .foundation_io import load_strict_json_object, safe_regular_file
from .strict import domain_matches, parse_aware, require_sha256, safe_relative_path


@dataclass(frozen=True)
class Artifact:
    path: str
    sha256: str
    size_bytes: int
    source_id: str
    source_url: str
    observed_at: str
    provider_as_of: str | None
    content_type: str


@dataclass(frozen=True)
class ManifestResult:
    status: str
    artifacts: tuple[Artifact, ...]
    errors: tuple[str, ...]

    @property
    def hashes(self) -> frozenset[str]:
        return frozenset(item.sha256 for item in self.artifacts)

    @property
    def by_hash(self) -> dict[str, tuple[Artifact, ...]]:
        grouped: dict[str, list[Artifact]] = {}
        for item in self.artifacts:
            grouped.setdefault(item.sha256, []).append(item)
        return {key: tuple(value) for key, value in grouped.items()}

    @property
    def hashes_by_source(self) -> dict[str, frozenset[str]]:
        """Return the exact raw hashes attributable to each manifest source.

        A global set of hashes is insufficient for capability validation: it
        would let an attestation name an official source while resolving its
        bytes from an unrelated secondary source.  Keep the legacy ``hashes``
        property for callers that only need existence checks, but expose this
        source-bound view for every trust decision.
        """

        grouped: dict[str, set[str]] = {}
        for item in self.artifacts:
            grouped.setdefault(item.source_id, set()).add(item.sha256)
        return {key: frozenset(value) for key, value in grouped.items()}


class EvidenceManifest:
    """Verify raw artifacts, metadata, source identity, and exact bytes."""

    def __init__(self, pack_root: Path, catalog: Catalog):
        self.pack_root = pack_root.resolve()
        self.catalog = catalog
        self.path = self.pack_root / "manifests" / "file_manifest.json"

    def validate(self, *, cutoff: Any | None = None) -> ManifestResult:
        if not self.path.is_file():
            return ManifestResult("BLOCKED", (), ("MISSING_FILE_MANIFEST",))
        errors: list[str] = []
        artifacts: list[Artifact] = []
        cutoff_at = parse_aware(cutoff, "cutoff") if cutoff is not None else None
        try:
            payload, _ = load_strict_json_object(
                self.path,
                field="evidence file manifest",
                max_bytes=16 * 1024 * 1024,
            )
        except ValueError as exc:
            return ManifestResult("BLOCKED", (), (f"INVALID_FILE_MANIFEST:{exc}",))
        if payload.get("schema_version") != "2.0":
            errors.append("UNSUPPORTED_MANIFEST_SCHEMA")
        rows = payload.get("artifacts")
        if not isinstance(rows, list) or not rows:
            errors.append("EMPTY_ARTIFACT_MANIFEST")
            rows = []
        seen_paths: set[str] = set()
        for index, row in enumerate(rows):
            prefix = f"artifact_{index}"
            if not isinstance(row, dict):
                errors.append(prefix + ":NOT_OBJECT")
                continue
            try:
                relative = safe_relative_path(row.get("path"), "path")
                if not relative.parts or relative.parts[0] != "raw":
                    raise ValueError("raw artifact path must start with raw/")
                relative_text = relative.as_posix()
                if relative_text in seen_paths:
                    raise ValueError("duplicate artifact path")
                seen_paths.add(relative_text)
                source_id = str(row.get("source_id", ""))
                if source_id not in self.catalog.sources:
                    raise ValueError(f"unknown source_id: {source_id}")
                source = self.catalog.sources[source_id]
                source_url = str(row.get("source_url", ""))
                if source.urls and not domain_matches(source_url, source.urls):
                    raise ValueError("source_url is outside the catalogued source domains")
                observed = parse_aware(row.get("observed_at"), "observed_at")
                provider_value = row.get("provider_as_of")
                provider = parse_aware(provider_value, "provider_as_of") if provider_value not in (None, "") else None
                if provider is not None and provider > observed:
                    raise ValueError("provider_as_of is after observed_at")
                if cutoff_at is not None and observed > cutoff_at:
                    raise ValueError("observed_at is after the collection cutoff")
                if cutoff_at is not None and provider is not None and provider > cutoff_at:
                    raise ValueError("provider_as_of is after the collection cutoff")
                digest = require_sha256(row.get("sha256"), "sha256")
                size = int(row.get("size_bytes"))
                if size < 0:
                    raise ValueError("size_bytes must be non-negative")
                content_type = str(row.get("content_type", ""))
                if not content_type:
                    raise ValueError("content_type is required")
                full_path = self.pack_root / relative
                content = safe_regular_file(
                    full_path,
                    field=f"evidence artifact {relative_text}",
                    max_bytes=512 * 1024 * 1024,
                )
                if len(content) != size:
                    raise ValueError("artifact size mismatch")
                if hashlib.sha256(content).hexdigest() != digest:
                    raise ValueError("artifact hash mismatch")
                artifacts.append(
                    Artifact(
                        path=relative_text,
                        sha256=digest,
                        size_bytes=size,
                        source_id=source_id,
                        source_url=source_url,
                        observed_at=observed.isoformat(),
                        provider_as_of=provider.isoformat() if provider else None,
                        content_type=content_type,
                    )
                )
            except (TypeError, ValueError) as exc:
                errors.append(f"{prefix}:{exc}")
        status = "PASS" if artifacts and not errors else "BLOCKED"
        return ManifestResult(status, tuple(artifacts), tuple(errors))


__all__ = ["Artifact", "EvidenceManifest", "ManifestResult"]
