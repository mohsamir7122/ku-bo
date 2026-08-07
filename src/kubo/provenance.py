from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .hashing import canonical_json_bytes, sha256_bytes, sha256_file
from .strict import require_sha256, safe_relative_path


DEFAULT_PROVENANCE_ROOTS = (
    "src",
    "scripts",
    "schemas",
    "config",
    "research",
    "AGENTS.md",
    "pyproject.toml",
)


def runtime_package_hash(package_root: Path | None = None) -> str:
    """Hash the exact installed ``kubo`` package used by this process.

    ``--project-root`` selects external policy and configuration files.  It is
    deliberately not a code-provenance authority: an installed wheel may be
    executed against a checkout that contains no ``src/`` tree at all.  The
    decision ledger therefore binds code to this importable package directory
    and records configuration under a separate digest.
    """

    unresolved = Path(package_root) if package_root is not None else Path(__file__).parent
    try:
        root = unresolved.resolve(strict=True)
    except OSError as exc:
        raise ValueError("runtime package root does not exist") from exc
    if not root.is_dir():
        raise ValueError("runtime package root must be a directory")

    entries: list[dict[str, str]] = []
    for path in sorted(root.rglob("*")):
        if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
            continue
        if path.is_symlink():
            raise ValueError("runtime package must not contain symlinked files")
        if not path.is_file():
            continue
        entries.append(
            {
                "path": path.relative_to(root).as_posix(),
                "sha256": sha256_file(path),
            }
        )
    if not entries:
        raise ValueError("runtime package contains no hashable files")
    return sha256_bytes(canonical_json_bytes(entries))


def source_tree_hash(
    project_root: Path,
    roots: Iterable[str] = DEFAULT_PROVENANCE_ROOTS,
) -> str:
    """Hash executable code and every policy/configuration surface it relies on.

    A research decision is not reproducible when only Python source is frozen:
    changing a source role, a quorum, a product contract, or a methodology
    registry can change the result without changing code.  Files and directories
    are therefore accepted in one deterministic provenance tree.
    """

    project_root = Path(project_root).resolve()
    entries: list[dict[str, str]] = []
    for root_name in roots:
        root = (project_root / root_name).resolve()
        if root != project_root and project_root not in root.parents:
            continue
        if root.is_file():
            paths = (root,)
        elif root.is_dir():
            paths = tuple(sorted(root.rglob("*")))
        else:
            continue
        for path in paths:
            if not path.is_file() or "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
                continue
            entries.append(
                {
                    "path": path.relative_to(project_root).as_posix(),
                    "sha256": sha256_file(path),
                }
            )
    if not entries:
        raise ValueError("no source files resolved for code hash")
    return sha256_bytes(canonical_json_bytes(entries))


def evidence_packet_hash(run_root: Path) -> str:
    """Hash the canonical files and every manifest-referenced raw artifact.

    The manifest is the packet's raw-file inventory.  Unreferenced scratch files
    do not change packet identity, while a missing, escaped, or hash-mismatched
    referenced artifact makes the packet ineligible for provenance binding.
    """

    run_root = Path(run_root).resolve()
    required = (
        "research_run.json",
        "universe.json",
        "manifest.json",
        "source_observations.json",
        "findings.jsonl",
    )
    paths: list[Path] = []
    for name in required:
        path = (run_root / name).resolve()
        if run_root not in path.parents or not path.is_file():
            raise ValueError(f"evidence packet is missing {name}")
        paths.append(path)

    try:
        manifest = json.loads((run_root / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("evidence packet manifest is not valid JSON") from exc
    if not isinstance(manifest, dict) or not isinstance(manifest.get("artifacts"), list):
        raise ValueError("evidence packet manifest artifacts must be a list")
    if not manifest["artifacts"]:
        raise ValueError("evidence packet manifest artifacts must be non-empty")

    referenced: set[str] = set()
    for index, row in enumerate(manifest["artifacts"]):
        if not isinstance(row, dict):
            raise ValueError(f"manifest artifact {index} is not an object")
        relative = safe_relative_path(row.get("path"), f"artifacts[{index}].path")
        if not relative.parts or relative.parts[0] != "raw":
            raise ValueError(f"manifest artifact {index} is outside raw/")
        relative_text = relative.as_posix()
        if relative_text in referenced:
            raise ValueError(f"manifest artifact path is duplicated: {relative_text}")
        referenced.add(relative_text)
        artifact = (run_root / relative).resolve()
        if run_root not in artifact.parents or not artifact.is_file():
            raise ValueError(f"manifest artifact is missing: {relative_text}")
        declared = require_sha256(row.get("sha256"), f"artifacts[{index}].sha256")
        if sha256_file(artifact) != declared:
            raise ValueError(f"manifest artifact hash mismatch: {relative_text}")
        paths.append(artifact)

    entries = [
        {
            "path": path.relative_to(run_root).as_posix(),
            "sha256": sha256_file(path),
        }
        for path in sorted(paths)
    ]
    return sha256_bytes(canonical_json_bytes(entries))


__all__ = [
    "DEFAULT_PROVENANCE_ROOTS",
    "evidence_packet_hash",
    "runtime_package_hash",
    "source_tree_hash",
]
