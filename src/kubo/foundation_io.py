from __future__ import annotations

import csv
import io
import json
import os
import stat
from pathlib import Path
from typing import Any, Iterable, Mapping


DEFAULT_MAX_BYTES = 64 * 1024 * 1024


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
    current = Path(absolute.anchor)
    for component in absolute.parts[1:]:
        current /= component
        try:
            metadata = os.lstat(current)
        except OSError as exc:
            raise ValueError(f"{field} is missing or unreadable") from exc
        if stat.S_ISLNK(metadata.st_mode):
            raise ValueError(f"{field} must not contain symlinks")

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
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
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise ValueError(f"{field} changed while being read")
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
        if current.exists() and current.is_symlink():
            raise ValueError(f"{label} must not contain symlink components")
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
    current = Path(absolute.anchor)
    for component in absolute.parts[1:]:
        current /= component
        try:
            metadata = os.lstat(current)
        except OSError as exc:
            raise ValueError(f"{field} is missing or unreadable") from exc
        if stat.S_ISLNK(metadata.st_mode):
            raise ValueError(f"{field} must not contain symlinks")
    if not absolute.is_dir():
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
    "load_strict_json_object",
    "nonnegative_int",
    "positive_int",
    "prepare_output_root",
    "read_csv_bytes",
    "require_real_directory",
    "safe_regular_file",
    "strict_json_object",
    "write_csv",
]
