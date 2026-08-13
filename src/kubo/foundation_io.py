from __future__ import annotations

import csv
from dataclasses import dataclass, field
import errno
import hashlib
import io
import json
import os
import stat
from pathlib import Path
from typing import Any, Iterable, Mapping


DEFAULT_MAX_BYTES = 64 * 1024 * 1024
DEFAULT_MAX_TREE_BYTES = 512 * 1024 * 1024
DEFAULT_MAX_TREE_FILES = 4096
DEFAULT_MAX_TREE_ENTRIES = 8192
DEFAULT_MAX_TREE_DEPTH = 64


class TreeSnapshotChangedError(ValueError):
    """The tree changed while a bounded snapshot was being constructed."""


def _is_reparse_point(metadata: os.stat_result) -> bool:
    attributes = getattr(metadata, "st_file_attributes", 0)
    marker = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & marker)


def _identity(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _same_open_path_identity(
    descriptor_metadata: os.stat_result,
    path_metadata: os.stat_result,
) -> bool:
    """Compare stable identity fields across Windows handle/path stat APIs."""

    return (
        descriptor_metadata.st_dev,
        descriptor_metadata.st_ino,
        descriptor_metadata.st_mode,
        descriptor_metadata.st_nlink,
        descriptor_metadata.st_size,
        descriptor_metadata.st_mtime_ns,
    ) == (
        path_metadata.st_dev,
        path_metadata.st_ino,
        path_metadata.st_mode,
        path_metadata.st_nlink,
        path_metadata.st_size,
        path_metadata.st_mtime_ns,
    )


def _safe_ancestor_snapshot(path: Path, *, field: str) -> tuple[tuple[Path, tuple[int, ...]], ...]:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    rows: list[tuple[Path, tuple[int, ...]]] = []
    for component in absolute.parts[1:]:
        current /= component
        try:
            metadata = os.lstat(current)
        except OSError as exc:
            raise ValueError(f"{field} is missing or unreadable") from exc
        if stat.S_ISLNK(metadata.st_mode) or _is_reparse_point(metadata):
            raise ValueError(f"{field} must not contain symlinks or reparse points")
        rows.append((current, _identity(metadata)))
    return tuple(rows)


def _recheck_ancestor_snapshot(
    snapshot: tuple[tuple[Path, tuple[int, ...]], ...],
    *,
    field: str,
) -> None:
    for index, (path, expected) in enumerate(snapshot):
        try:
            metadata = os.lstat(path)
        except OSError as exc:
            raise ValueError(f"{field} changed while being read") from exc
        current = _identity(metadata)
        directory = index < len(snapshot) - 1
        # Directory size/link-count can change when an unrelated sibling is
        # created elsewhere under the same ancestor.  Path safety depends on
        # the directory object (device, inode, and type), not those mutable
        # inventory counters.  The leaf file still receives the full identity
        # comparison below.
        unchanged = current[:3] == expected[:3] if directory else current == expected
        if stat.S_ISLNK(metadata.st_mode) or _is_reparse_point(metadata) or not unchanged:
            raise ValueError(f"{field} changed while being read")


def safe_regular_file(
    path: Path,
    *,
    field: str,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> bytes:
    """Read a bounded regular file without following a symlink component."""

    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    absolute = Path(os.path.abspath(path))
    ancestors = _safe_ancestor_snapshot(absolute, field=field)

    flags = (
        os.O_RDONLY
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(absolute, flags)
    except OSError as exc:
        raise ValueError(f"{field} cannot be opened safely") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError(f"{field} must be a regular file")
        if before.st_size > max_bytes:
            raise ValueError(f"{field} exceeds {max_bytes} bytes")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(1024 * 1024, max_bytes + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > max_bytes:
                raise ValueError(f"{field} exceeds {max_bytes} bytes")
        after = os.fstat(descriptor)
        if _identity(before) != _identity(after):
            raise ValueError(f"{field} changed while being read")
        try:
            current = os.lstat(absolute)
        except OSError as exc:
            raise ValueError(f"{field} changed while being read") from exc
        if not _same_open_path_identity(after, current):
            raise ValueError(f"{field} changed while being read")
        _recheck_ancestor_snapshot(ancestors, field=field)
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def strict_json_object(content: bytes, field: str) -> dict[str, Any]:
    """Decode a strict UTF-8 JSON object and reject duplicate/non-finite values."""

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"{field} contains duplicate key: {key}")
            result[key] = value
        return result

    try:
        payload = json.loads(
            content.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"{field} contains non-finite JSON: {value}")
            ),
        )
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError(f"{field} must be strict UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{field} must contain a JSON object")
    return payload


def load_strict_json_object(
    path: Path,
    *,
    field: str,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> tuple[dict[str, Any], bytes]:
    content = safe_regular_file(path, field=field, max_bytes=max_bytes)
    return strict_json_object(content, field), content


@dataclass(frozen=True)
class RegularFileSnapshot:
    path: str
    content: bytes = field(repr=False)
    sha256: str
    size_bytes: int

    def inventory_row(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
        }


@dataclass(frozen=True)
class RegularTreeSnapshot:
    root: Path
    files: tuple[RegularFileSnapshot, ...]

    def by_path(self) -> dict[str, RegularFileSnapshot]:
        return {item.path: item for item in self.files}

    def inventory(self) -> list[dict[str, Any]]:
        return [item.inventory_row() for item in self.files]


_WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{index}" for index in range(1, 10)}
    | {f"LPT{index}" for index in range(1, 10)}
)


def _safe_tree_name(value: str, *, field: str) -> str:
    if (
        not value
        or value in {".", ".."}
        or value != value.strip()
        or value.endswith((".", " "))
        or ":" in value
        or "\\" in value
        or "/" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ValueError(f"{field} contains an unsafe path component")
    if value.split(".", 1)[0].upper() in _WINDOWS_RESERVED_NAMES:
        raise ValueError(f"{field} contains a reserved path component")
    return value


def _scan_regular_tree_once(
    root: Path,
    *,
    field: str,
    max_files: int,
    max_entries: int,
    max_depth: int,
    max_file_bytes: int,
    max_total_bytes: int,
) -> tuple[RegularFileSnapshot, ...]:
    rows: list[RegularFileSnapshot] = []
    total_bytes = 0
    total_entries = 0

    def visit(
        directory: Path,
        relative_parts: tuple[str, ...],
        depth: int,
    ) -> None:
        nonlocal total_bytes, total_entries
        if depth > max_depth:
            raise ValueError(f"{field} exceeds maximum depth {max_depth}")
        try:
            with os.scandir(directory) as iterator:
                entries = []
                for entry in iterator:
                    total_entries += 1
                    if total_entries > max_entries:
                        raise ValueError(f"{field} exceeds {max_entries} entries")
                    entries.append(entry)
                entries.sort(key=lambda item: item.name)
        except OSError as exc:
            raise ValueError(f"{field} cannot be enumerated safely") from exc
        for entry in entries:
            name = _safe_tree_name(entry.name, field=field)
            relative = (*relative_parts, name)
            path_text = "/".join(relative)
            try:
                metadata = entry.stat(follow_symlinks=False)
            except OSError as exc:
                raise ValueError(f"{field} entry changed during enumeration") from exc
            if stat.S_ISLNK(metadata.st_mode) or _is_reparse_point(metadata):
                raise ValueError(f"{field} must not contain symlinks or reparse points")
            if stat.S_ISDIR(metadata.st_mode):
                visit(Path(entry.path), relative, depth + 1)
                continue
            if not stat.S_ISREG(metadata.st_mode):
                raise ValueError(f"{field} must contain only regular files and directories")
            try:
                path_metadata = os.lstat(entry.path)
            except OSError as exc:
                raise ValueError(f"{field} entry changed during enumeration") from exc
            if stat.S_ISLNK(path_metadata.st_mode) or _is_reparse_point(path_metadata):
                raise ValueError(f"{field} must not contain symlinks or reparse points")
            if path_metadata.st_nlink != 1:
                raise ValueError(f"{field} must not contain hard-linked files")
            if len(rows) >= max_files:
                raise ValueError(f"{field} exceeds {max_files} files")
            content = safe_regular_file(
                Path(entry.path),
                field=f"{field} file {path_text}",
                max_bytes=max_file_bytes,
            )
            total_bytes += len(content)
            if total_bytes > max_total_bytes:
                raise ValueError(f"{field} exceeds {max_total_bytes} bytes")
            rows.append(
                RegularFileSnapshot(
                    path=path_text,
                    content=content,
                    sha256=hashlib.sha256(content).hexdigest(),
                    size_bytes=len(content),
                )
            )

    visit(root, (), 0)
    return tuple(sorted(rows, key=lambda item: item.path))


def snapshot_regular_tree(
    root: Path,
    *,
    field: str,
    max_files: int = DEFAULT_MAX_TREE_FILES,
    max_entries: int = DEFAULT_MAX_TREE_ENTRIES,
    max_depth: int = DEFAULT_MAX_TREE_DEPTH,
    max_file_bytes: int = DEFAULT_MAX_BYTES,
    max_total_bytes: int = DEFAULT_MAX_TREE_BYTES,
) -> RegularTreeSnapshot:
    """Read a complete, bounded regular-file tree twice and reject drift.

    Returned bytes are the verified snapshot. Callers that need to consume a
    stage must use these bytes instead of reopening mutable paths.
    """

    if (
        max_files <= 0
        or max_entries <= 0
        or max_depth <= 0
        or max_file_bytes <= 0
        or max_total_bytes <= 0
    ):
        raise ValueError("tree snapshot limits must be positive")
    absolute = require_real_directory(root, field=field)
    before_root = _identity(os.lstat(absolute))
    def scan() -> tuple[RegularFileSnapshot, ...]:
        try:
            return _scan_regular_tree_once(
                absolute,
                field=field,
                max_files=max_files,
                max_entries=max_entries,
                max_depth=max_depth,
                max_file_bytes=max_file_bytes,
                max_total_bytes=max_total_bytes,
            )
        except ValueError as exc:
            message = str(exc).lower()
            cause = exc.__cause__
            raced_enumeration = (
                "cannot be enumerated safely" in message
                and isinstance(cause, OSError)
                and cause.errno in {errno.ENOENT, errno.ENOTDIR, errno.ESTALE}
            )
            if "changed while" in message or "changed during" in message or raced_enumeration:
                raise TreeSnapshotChangedError(
                    f"{field} changed while being snapshotted"
                ) from exc
            raise

    first = scan()
    second = scan()
    first_inventory = [item.inventory_row() for item in first]
    second_inventory = [item.inventory_row() for item in second]
    try:
        after_root = _identity(os.lstat(absolute))
    except OSError as exc:
        raise TreeSnapshotChangedError(
            f"{field} changed while being snapshotted"
        ) from exc
    if first_inventory != second_inventory:
        raise TreeSnapshotChangedError(f"{field} changed while being snapshotted")
    if before_root[:5] != after_root[:5]:
        raise TreeSnapshotChangedError(f"{field} changed while being snapshotted")
    return RegularTreeSnapshot(root=absolute, files=second)


def read_csv_bytes(
    content: bytes,
    *,
    field: str,
    exact_headers: Iterable[str] | None = None,
    required_headers: Iterable[str] = (),
) -> tuple[tuple[str, ...], list[dict[str, str]]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{field} must be UTF-8 CSV") from exc
    reader = csv.DictReader(io.StringIO(text, newline=""))
    headers = tuple(reader.fieldnames or ())
    if not headers:
        raise ValueError(f"{field} must contain a header row")
    if len(headers) != len(set(headers)):
        raise ValueError(f"{field} contains duplicate headers")
    if exact_headers is not None and headers != tuple(exact_headers):
        raise ValueError(f"{field} headers do not match the canonical contract")
    missing = sorted(set(required_headers) - set(headers))
    if missing:
        raise ValueError(f"{field} lacks required headers: {','.join(missing)}")
    rows: list[dict[str, str]] = []
    for index, row in enumerate(reader):
        if None in row:
            raise ValueError(f"{field} row {index} has extra columns")
        normalized = {key: str(value or "").strip() for key, value in row.items()}
        if not any(normalized.values()):
            raise ValueError(f"{field} row {index} is empty")
        rows.append(normalized)
    return headers, rows


def write_csv(
    path: Path,
    *,
    headers: Iterable[str],
    rows: Iterable[Mapping[str, Any]],
) -> None:
    canonical_headers = tuple(headers)
    if not canonical_headers or len(canonical_headers) != len(set(canonical_headers)):
        raise ValueError("CSV headers must be non-empty and unique")
    with path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=canonical_headers, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            unexpected = set(row) - set(canonical_headers)
            if unexpected:
                raise ValueError("CSV row contains fields outside the canonical contract")
            writer.writerow({key: row.get(key, "") for key in canonical_headers})


def prepare_output_root(path: Path, *, label: str) -> Path:
    """Create or accept one empty real directory without following symlinks."""

    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for component in absolute.parts[1:]:
        current /= component
        if current.exists():
            metadata = os.lstat(current)
            if stat.S_ISLNK(metadata.st_mode) or _is_reparse_point(metadata):
                raise ValueError(
                    f"{label} must not contain symlink or reparse components"
                )
    if absolute.exists() or absolute.is_symlink():
        if absolute.is_symlink() or not absolute.is_dir():
            raise ValueError(f"{label} must be a real directory")
        if any(absolute.iterdir()):
            raise ValueError(f"refusing to overwrite a non-empty {label}")
    else:
        absolute.mkdir(parents=True, exist_ok=False)
    return absolute


def require_real_directory(path: Path, *, field: str) -> Path:
    absolute = Path(os.path.abspath(path))
    _safe_ancestor_snapshot(absolute, field=field)
    if not stat.S_ISDIR(os.lstat(absolute).st_mode):
        raise ValueError(f"{field} must be a real directory")
    return absolute


def nonnegative_int(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a non-negative integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a non-negative integer") from exc
    if str(value).strip() != str(parsed) or parsed < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return parsed


def positive_int(value: Any, field: str) -> int:
    parsed = nonnegative_int(value, field)
    if parsed == 0:
        raise ValueError(f"{field} must be positive")
    return parsed


__all__ = [
    "DEFAULT_MAX_BYTES",
    "DEFAULT_MAX_TREE_BYTES",
    "DEFAULT_MAX_TREE_DEPTH",
    "DEFAULT_MAX_TREE_ENTRIES",
    "DEFAULT_MAX_TREE_FILES",
    "RegularFileSnapshot",
    "RegularTreeSnapshot",
    "load_strict_json_object",
    "nonnegative_int",
    "positive_int",
    "prepare_output_root",
    "read_csv_bytes",
    "require_real_directory",
    "safe_regular_file",
    "snapshot_regular_tree",
    "strict_json_object",
    "write_csv",
]
