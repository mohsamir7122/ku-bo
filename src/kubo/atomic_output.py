from __future__ import annotations

from dataclasses import dataclass
import ctypes
import errno
import os
from pathlib import Path
import secrets
import shutil
import stat
import sys
from typing import Callable, TypeVar


OUTPUT_ROOT_ALREADY_EXISTS = "OUTPUT_ROOT_ALREADY_EXISTS"
OUTPUT_ROOT_CHANGED_DURING_COMMIT = "OUTPUT_ROOT_CHANGED_DURING_COMMIT"
PARTIAL_OUTPUT_FORBIDDEN = "PARTIAL_OUTPUT_FORBIDDEN"

_ERROR_CODES = frozenset(
    {
        OUTPUT_ROOT_ALREADY_EXISTS,
        OUTPUT_ROOT_CHANGED_DURING_COMMIT,
        PARTIAL_OUTPUT_FORBIDDEN,
    }
)
_AT_FDCWD = -100
_RENAME_NOREPLACE = 1
_RENAME_EXCL = 0x00000004

_T = TypeVar("_T")
ENTRY_PRE_WRITE = "ENTRY_PRE_WRITE"
ARTIFACT_VALIDATION_PRE_WRITE = "ARTIFACT_VALIDATION_PRE_WRITE"
PRE_COMMIT_RECHECK = "PRE_COMMIT_RECHECK"
_FAILURE_PHASES = frozenset(
    {ENTRY_PRE_WRITE, ARTIFACT_VALIDATION_PRE_WRITE, PRE_COMMIT_RECHECK}
)


class AtomicOutputError(RuntimeError):
    """A fail-closed atomic-output error with a stable machine-readable code."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        phase: str = ENTRY_PRE_WRITE,
    ) -> None:
        if code not in _ERROR_CODES:
            raise ValueError(f"unsupported atomic-output error code: {code}")
        if phase not in _FAILURE_PHASES:
            raise ValueError(f"unsupported atomic-output failure phase: {phase}")
        self.code = code
        self.failure_code = code
        self.phase = phase
        self.failure_phase = phase
        self.message = message
        super().__init__(f"{code}:{phase}:{message}")

    def to_dict(self) -> dict[str, str]:
        return {
            "error": "ATOMIC_OUTPUT_ERROR",
            "code": self.code,
            "phase": self.phase,
            "message": self.message,
        }


def _is_reparse_point(metadata: os.stat_result) -> bool:
    attributes = getattr(metadata, "st_file_attributes", 0)
    marker = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & marker)


def _directory_identity(metadata: os.stat_result) -> tuple[int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
    )


@dataclass(frozen=True)
class _ParentGuard:
    path: Path
    snapshots: tuple[tuple[Path, tuple[int, int, int]], ...]
    descriptor: int | None


@dataclass(frozen=True)
class _StagingGuard:
    path: Path
    name: str
    identity: tuple[int, int, int]


def _path_chain(path: Path) -> tuple[Path, ...]:
    anchor = Path(path.anchor)
    if not path.anchor:
        raise AtomicOutputError(
            PARTIAL_OUTPUT_FORBIDDEN,
            "atomic output parent must be absolute",
        )
    rows = [anchor]
    current = anchor
    for component in path.parts[1:]:
        current /= component
        rows.append(current)
    return tuple(rows)


def _snapshot_real_parent(path: Path) -> tuple[tuple[Path, tuple[int, int, int]], ...]:
    rows: list[tuple[Path, tuple[int, int, int]]] = []
    for component in _path_chain(path):
        try:
            metadata = os.lstat(component)
        except OSError as exc:
            raise AtomicOutputError(
                PARTIAL_OUTPUT_FORBIDDEN,
                "atomic output parent must already exist",
            ) from exc
        if (
            stat.S_ISLNK(metadata.st_mode)
            or _is_reparse_point(metadata)
            or not stat.S_ISDIR(metadata.st_mode)
        ):
            raise AtomicOutputError(
                PARTIAL_OUTPUT_FORBIDDEN,
                "atomic output parent must be a real directory without symlink components",
            )
        rows.append((component, _directory_identity(metadata)))
    return tuple(rows)


def _open_parent(path: Path) -> _ParentGuard:
    snapshots = _snapshot_real_parent(path)
    descriptor: int | None = None
    flags = (
        os.O_RDONLY
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(path, flags)
    except OSError:
        # Windows does not provide a portable Python directory descriptor.
        # The path snapshots still provide the fail-closed fallback guard.
        if os.name != "nt":
            raise AtomicOutputError(
                PARTIAL_OUTPUT_FORBIDDEN,
                "atomic output parent cannot be opened safely",
            )
    if descriptor is not None:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(opened.st_mode)
            or _directory_identity(opened) != snapshots[-1][1]
        ):
            os.close(descriptor)
            raise AtomicOutputError(
                OUTPUT_ROOT_CHANGED_DURING_COMMIT,
                "atomic output parent changed while it was opened",
            )
    return _ParentGuard(path=path, snapshots=snapshots, descriptor=descriptor)


def _recheck_parent(guard: _ParentGuard) -> None:
    for path, expected in guard.snapshots:
        try:
            metadata = os.lstat(path)
        except OSError as exc:
            raise AtomicOutputError(
                OUTPUT_ROOT_CHANGED_DURING_COMMIT,
                "atomic output parent changed before commit",
                phase=PRE_COMMIT_RECHECK,
            ) from exc
        if (
            stat.S_ISLNK(metadata.st_mode)
            or _is_reparse_point(metadata)
            or not stat.S_ISDIR(metadata.st_mode)
            or _directory_identity(metadata) != expected
        ):
            raise AtomicOutputError(
                OUTPUT_ROOT_CHANGED_DURING_COMMIT,
                "atomic output parent changed before commit",
                phase=PRE_COMMIT_RECHECK,
            )
    if guard.descriptor is not None:
        try:
            opened = os.fstat(guard.descriptor)
        except OSError as exc:
            raise AtomicOutputError(
                OUTPUT_ROOT_CHANGED_DURING_COMMIT,
                "atomic output parent handle changed before commit",
                phase=PRE_COMMIT_RECHECK,
            ) from exc
        if _directory_identity(opened) != guard.snapshots[-1][1]:
            raise AtomicOutputError(
                OUTPUT_ROOT_CHANGED_DURING_COMMIT,
                "atomic output parent handle changed before commit",
                phase=PRE_COMMIT_RECHECK,
            )


def _entry_metadata(
    guard: _ParentGuard,
    name: str,
) -> os.stat_result | None:
    try:
        if guard.descriptor is not None and os.stat in os.supports_dir_fd:
            return os.stat(name, dir_fd=guard.descriptor, follow_symlinks=False)
        return os.lstat(guard.path / name)
    except FileNotFoundError:
        return None
    except OSError as exc:
        if exc.errno == errno.ENOENT:
            return None
        raise


def _require_target_absent(
    guard: _ParentGuard,
    target_name: str,
    *,
    initial: bool,
    phase: str,
) -> None:
    try:
        present = _entry_metadata(guard, target_name) is not None
    except OSError as exc:
        code = (
            OUTPUT_ROOT_ALREADY_EXISTS
            if initial
            else OUTPUT_ROOT_CHANGED_DURING_COMMIT
        )
        raise AtomicOutputError(
            code,
            "atomic output target cannot be inspected safely",
            phase=phase,
        ) from exc
    if present:
        code = (
            OUTPUT_ROOT_ALREADY_EXISTS
            if initial
            else OUTPUT_ROOT_CHANGED_DURING_COMMIT
        )
        message = (
            "atomic output target must be absent"
            if initial
            else "atomic output target appeared before commit"
        )
        raise AtomicOutputError(code, message, phase=phase)


def _staging_prefix(target_name: str) -> str:
    fragment = "".join(
        character if character.isalnum() or character in {"-", "_"} else "_"
        for character in target_name
    )[:48]
    return f".{fragment or 'output'}.staging-"


def _create_staging(guard: _ParentGuard, target_name: str) -> _StagingGuard:
    prefix = _staging_prefix(target_name)
    for _ in range(128):
        name = prefix + secrets.token_hex(12)
        try:
            if guard.descriptor is not None and os.mkdir in os.supports_dir_fd:
                os.mkdir(name, mode=0o700, dir_fd=guard.descriptor)
            else:
                os.mkdir(guard.path / name, mode=0o700)
        except FileExistsError:
            continue
        except OSError as exc:
            raise AtomicOutputError(
                PARTIAL_OUTPUT_FORBIDDEN,
                "hidden atomic staging directory could not be created",
            ) from exc
        metadata = _entry_metadata(guard, name)
        if metadata is None or not stat.S_ISDIR(metadata.st_mode):
            raise AtomicOutputError(
                PARTIAL_OUTPUT_FORBIDDEN,
                "hidden atomic staging directory is not a real directory",
            )
        return _StagingGuard(
            path=guard.path / name,
            name=name,
            identity=_directory_identity(metadata),
        )
    raise AtomicOutputError(
        PARTIAL_OUTPUT_FORBIDDEN,
        "a unique hidden atomic staging directory could not be allocated",
    )


def _require_staging_unchanged(
    parent: _ParentGuard,
    staging: _StagingGuard,
) -> None:
    try:
        metadata = _entry_metadata(parent, staging.name)
    except OSError as exc:
        raise AtomicOutputError(
            PARTIAL_OUTPUT_FORBIDDEN,
            "atomic staging directory cannot be inspected before commit",
            phase=PRE_COMMIT_RECHECK,
        ) from exc
    if (
        metadata is None
        or not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or _is_reparse_point(metadata)
        or _directory_identity(metadata) != staging.identity
    ):
        raise AtomicOutputError(
            PARTIAL_OUTPUT_FORBIDDEN,
            "atomic staging directory was removed or replaced",
            phase=PRE_COMMIT_RECHECK,
        )


def _linux_rename_noreplace(
    source_name: str,
    target_name: str,
    parent_descriptor: int,
) -> None:
    library = ctypes.CDLL(None, use_errno=True)
    function = getattr(library, "renameat2", None)
    if function is None:
        raise OSError(errno.ENOTSUP, "renameat2 is unavailable")
    function.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    function.restype = ctypes.c_int
    ctypes.set_errno(0)
    result = function(
        parent_descriptor,
        os.fsencode(source_name),
        parent_descriptor,
        os.fsencode(target_name),
        _RENAME_NOREPLACE,
    )
    if result != 0:
        error = ctypes.get_errno() or errno.EIO
        raise OSError(error, os.strerror(error), target_name)


def _renameatx_noreplace(
    source_name: str,
    target_name: str,
    parent_descriptor: int,
) -> None:
    library = ctypes.CDLL(None, use_errno=True)
    function = getattr(library, "renameatx_np", None)
    if function is None:
        raise OSError(errno.ENOTSUP, "renameatx_np is unavailable")
    function.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    function.restype = ctypes.c_int
    ctypes.set_errno(0)
    result = function(
        parent_descriptor,
        os.fsencode(source_name),
        parent_descriptor,
        os.fsencode(target_name),
        _RENAME_EXCL,
    )
    if result != 0:
        error = ctypes.get_errno() or errno.EIO
        raise OSError(error, os.strerror(error), target_name)


def _rename_noreplace(
    parent: _ParentGuard,
    staging: _StagingGuard,
    target_name: str,
) -> None:
    try:
        if sys.platform.startswith("linux") and parent.descriptor is not None:
            _linux_rename_noreplace(
                staging.name,
                target_name,
                parent.descriptor,
            )
        elif (
            sys.platform == "darwin"
            and parent.descriptor is not None
        ):
            _renameatx_noreplace(
                staging.name,
                target_name,
                parent.descriptor,
            )
        elif os.name == "nt":
            # os.rename never replaces an existing destination on Windows.
            os.rename(staging.path, parent.path / target_name)
        else:
            raise OSError(
                errno.ENOTSUP,
                "no safe no-overwrite directory rename primitive is available",
            )
    except OSError as exc:
        raise AtomicOutputError(
            OUTPUT_ROOT_CHANGED_DURING_COMMIT,
            "atomic no-overwrite commit failed",
            phase=PRE_COMMIT_RECHECK,
        ) from exc


def _cleanup_staging(
    parent: _ParentGuard,
    staging: _StagingGuard,
) -> None:
    try:
        metadata = _entry_metadata(parent, staging.name)
    except OSError as exc:
        raise AtomicOutputError(
            PARTIAL_OUTPUT_FORBIDDEN,
            "atomic staging cleanup could not inspect the staging entry",
        ) from exc
    if metadata is None:
        return
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or _is_reparse_point(metadata)
        or _directory_identity(metadata) != staging.identity
    ):
        raise AtomicOutputError(
            PARTIAL_OUTPUT_FORBIDDEN,
            "refusing to delete a replaced atomic staging entry",
        )
    try:
        if (
            parent.descriptor is not None
            and getattr(shutil.rmtree, "avoids_symlink_attacks", False)
        ):
            shutil.rmtree(staging.name, dir_fd=parent.descriptor)
        else:
            _recheck_parent(parent)
            shutil.rmtree(staging.path)
    except OSError as exc:
        raise AtomicOutputError(
            PARTIAL_OUTPUT_FORBIDDEN,
            "atomic staging directory could not be cleaned",
        ) from exc


def run_atomic_output(
    target: str | os.PathLike[str],
    worker: Callable[[Path], _T],
    before_commit: Callable[[Path], None] | None = None,
    *,
    failure_phase: str = ENTRY_PRE_WRITE,
) -> _T:
    """Publish a newly created output directory through a no-overwrite rename.

    ``worker`` receives a hidden sibling staging directory and must put every
    prospective output byte below it. ``before_commit`` is an optional test and
    integration hook that runs after the worker and immediately before the
    final identity/absence checks. The target is never removed or overwritten.
    """

    if failure_phase not in _FAILURE_PHASES:
        raise ValueError(f"unsupported atomic-output failure phase: {failure_phase}")
    output = Path(os.path.abspath(Path(target)))
    if not output.name or output == output.parent:
        raise AtomicOutputError(
            PARTIAL_OUTPUT_FORBIDDEN,
            "atomic output target must name one child of an existing parent",
        )
    parent = _open_parent(output.parent)
    staging: _StagingGuard | None = None
    committed = False
    try:
        _require_target_absent(
            parent,
            output.name,
            initial=True,
            phase=failure_phase,
        )
        staging = _create_staging(parent, output.name)
        _recheck_parent(parent)
        _require_target_absent(
            parent,
            output.name,
            initial=False,
            phase=PRE_COMMIT_RECHECK,
        )
        try:
            result = worker(staging.path)
        except AtomicOutputError:
            raise
        except Exception as exc:
            raise AtomicOutputError(
                PARTIAL_OUTPUT_FORBIDDEN,
                "atomic output worker failed; staged output was rejected",
                phase=failure_phase,
            ) from exc

        if before_commit is not None:
            try:
                before_commit(staging.path)
            except AtomicOutputError:
                raise
            except Exception as exc:
                failure_code = getattr(exc, "failure_code", None)
                failure_phase = getattr(exc, "failure_phase", None)
                if (
                    isinstance(failure_code, str)
                    and failure_code
                    and isinstance(failure_phase, str)
                    and failure_phase
                ):
                    # Admission rejections already carry the exact stable
                    # contract identity required by the caller. Preserve it
                    # while the outer guard still removes every staged byte.
                    raise
                raise AtomicOutputError(
                    PARTIAL_OUTPUT_FORBIDDEN,
                    "atomic output pre-commit callback failed; staged output was rejected",
                    phase=PRE_COMMIT_RECHECK,
                ) from exc

        _recheck_parent(parent)
        _require_staging_unchanged(parent, staging)
        _require_target_absent(
            parent,
            output.name,
            initial=False,
            phase=PRE_COMMIT_RECHECK,
        )
        _rename_noreplace(parent, staging, output.name)
        committed = True
        return result
    except BaseException as exc:
        if staging is not None and not committed:
            try:
                _cleanup_staging(parent, staging)
            except AtomicOutputError as cleanup_error:
                raise cleanup_error from exc
        raise
    finally:
        if parent.descriptor is not None:
            os.close(parent.descriptor)


__all__ = [
    "AtomicOutputError",
    "ARTIFACT_VALIDATION_PRE_WRITE",
    "ENTRY_PRE_WRITE",
    "OUTPUT_ROOT_ALREADY_EXISTS",
    "OUTPUT_ROOT_CHANGED_DURING_COMMIT",
    "PARTIAL_OUTPUT_FORBIDDEN",
    "PRE_COMMIT_RECHECK",
    "run_atomic_output",
]
