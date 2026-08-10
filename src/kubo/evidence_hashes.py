from __future__ import annotations

from typing import Any

from .strict import require_sha256


SUPPORTING_HASH_SEPARATOR = "|"


def parse_supporting_hashes(
    value: Any,
    *,
    field: str,
    manifest_hashes: frozenset[str],
) -> tuple[str, ...]:
    """Parse optional pipe-separated supporting evidence hashes.

    CSV contracts historically carried one ``raw_sha256``. Some normalized
    facts legitimately require more than one primary artifact, for example a
    current security identity reconciled from one official code/ISIN table and
    one official listed-company table. The primary hash remains in
    ``raw_sha256``; this field binds the additional source bytes without
    replacing or weakening the original contract.
    """

    if value in (None, ""):
        return ()
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a pipe-separated string")
    parts = value.split(SUPPORTING_HASH_SEPARATOR)
    if any(not part or part != part.strip() for part in parts):
        raise ValueError(f"{field} must contain canonical pipe-separated hashes")
    hashes = tuple(require_sha256(part, field) for part in parts)
    if len(hashes) != len(set(hashes)):
        raise ValueError(f"{field} contains duplicate hashes")
    unresolved = sorted(set(hashes) - manifest_hashes)
    if unresolved:
        raise ValueError(f"{field} contains an unresolved hash")
    return hashes


def format_supporting_hashes(hashes: tuple[str, ...] | list[str]) -> str:
    normalized = tuple(str(item) for item in hashes)
    if len(normalized) != len(set(normalized)):
        raise ValueError("supporting evidence hashes must be unique")
    for digest in normalized:
        require_sha256(digest, "supporting_raw_sha256s")
    return SUPPORTING_HASH_SEPARATOR.join(normalized)


__all__ = [
    "SUPPORTING_HASH_SEPARATOR",
    "format_supporting_hashes",
    "parse_supporting_hashes",
]
