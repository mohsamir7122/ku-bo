from __future__ import annotations

import copy
from dataclasses import replace
from datetime import datetime
import hashlib
import hmac
import json
from pathlib import Path
import tempfile
import unittest

try:
    from jsonschema import Draft202012Validator, FormatChecker
except ImportError:  # pragma: no cover - optional test dependency
    Draft202012Validator = None
    FormatChecker = None

from kubo.authenticated_runtime_storage import (
    RuntimeStorageAuthorityError,
    STORAGE_ALLOWED_SUBPATHS,
    STORAGE_AUTHORITY_ALGORITHM,
    STORAGE_AUTHORITY_AUDIENCE,
    STORAGE_AUTHORITY_SCHEMA_VERSION,
    STORAGE_LOGICAL_ROOT,
    STORAGE_MARKET,
    STORAGE_OPERATIONS,
    STORAGE_STORE_KIND,
    load_runtime_storage_authority,
    require_storage_grant,
)


ROOT = Path(__file__).resolve().parents[1]
KEY = b"synthetic-storage-authority-key-material-32-bytes"
KEY_ID = "synthetic-storage-key-v1"
DECISION_AT = "2026-08-27T13:00:00+03:00"


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def authority_payload() -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": STORAGE_AUTHORITY_SCHEMA_VERSION,
        "audience": STORAGE_AUTHORITY_AUDIENCE,
        "grant_id": "synthetic-one-security-grant",
        "subject_id": "KU_BO",
        "logical_root": STORAGE_LOGICAL_ROOT,
        "allowed_subpaths": list(STORAGE_ALLOWED_SUBPATHS),
        "store_kind": STORAGE_STORE_KIND,
        "market": STORAGE_MARKET,
        "security_codes": ["999001"],
        "operations": list(STORAGE_OPERATIONS),
        "issued_at": "2026-08-27T09:00:00+03:00",
        "expires_at": "2026-08-28T09:00:00+03:00",
        "authentication": {
            "algorithm": STORAGE_AUTHORITY_ALGORITHM,
            "key_id": KEY_ID,
            "tag": "",
        },
    }
    return sign(payload)


def sign(payload: dict[str, object], key: bytes = KEY) -> dict[str, object]:
    result = copy.deepcopy(payload)
    authentication = result["authentication"]
    assert isinstance(authentication, dict)
    authentication["tag"] = ""
    unsigned = copy.deepcopy(result)
    unsigned_authentication = unsigned["authentication"]
    assert isinstance(unsigned_authentication, dict)
    unsigned_authentication.pop("tag")
    authentication["tag"] = hmac.new(
        key, canonical_bytes(unsigned), hashlib.sha256
    ).hexdigest()
    return result


def write_payload(directory: Path, payload: dict[str, object]) -> Path:
    target = directory / "storage-authority.json"
    target.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    return target


class AuthenticatedRuntimeStorageTests(unittest.TestCase):
    def load(self, payload: dict[str, object] | None = None, **kwargs: object):
        with tempfile.TemporaryDirectory() as directory:
            path = write_payload(Path(directory), payload or authority_payload())
            return load_runtime_storage_authority(
                path,
                kwargs.get("key", KEY),  # type: ignore[arg-type]
                kwargs.get("expected_key_id", KEY_ID),  # type: ignore[arg-type]
                kwargs.get("decision_at", DECISION_AT),
            )

    def test_valid_authority_loads_and_grants_exact_operations(self) -> None:
        authority = self.load()
        self.assertEqual(authority.security_codes, frozenset({"999001"}))
        self.assertEqual(authority.allowed_subpaths, STORAGE_ALLOWED_SUBPATHS)
        self.assertRegex(authority.content_sha256, r"^[0-9a-f]{64}$")
        for operation in STORAGE_OPERATIONS:
            self.assertIs(
                require_storage_grant(
                    authority,
                    STORAGE_LOGICAL_ROOT,
                    "999001",
                    operation,
                    DECISION_AT,
                ),
                authority,
            )

    @unittest.skipUnless(Draft202012Validator is not None, "jsonschema unavailable")
    def test_generated_fixture_matches_public_schema(self) -> None:
        assert Draft202012Validator is not None
        schema = json.loads(
            (ROOT / "schemas" / "runtime-storage-authority.schema.json").read_text(
                encoding="utf-8"
            )
        )
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(
            schema, format_checker=FormatChecker()
        ).validate(authority_payload())

    def test_hmac_key_and_key_identity_are_external_roots_of_trust(self) -> None:
        with self.assertRaisesRegex(RuntimeStorageAuthorityError, "verification failed"):
            self.load(key=b"different-synthetic-storage-key-material-32bytes")
        with self.assertRaisesRegex(RuntimeStorageAuthorityError, "key_id mismatch"):
            self.load(expected_key_id="different-key")
        with self.assertRaisesRegex(RuntimeStorageAuthorityError, "at least 32 bytes"):
            self.load(key=b"short")
        with self.assertRaisesRegex(RuntimeStorageAuthorityError, "must be bytes"):
            self.load(key=True)
        with self.assertRaisesRegex(RuntimeStorageAuthorityError, "canonical identifier"):
            self.load(expected_key_id=True)

    def test_tampered_payload_cannot_reuse_a_valid_tag(self) -> None:
        payload = authority_payload()
        payload["subject_id"] = "TAMPERED"
        with self.assertRaisesRegex(RuntimeStorageAuthorityError, "verification failed"):
            self.load(payload)

    def test_root_and_subpaths_remain_locked_even_when_resigned(self) -> None:
        payload = authority_payload()
        payload["logical_root"] = "AI Rebuild/04_Curated_Core/OTHER"
        with self.assertRaisesRegex(RuntimeStorageAuthorityError, "logical root mismatch"):
            self.load(sign(payload))

        payload = authority_payload()
        payload["allowed_subpaths"] = ["00_Manifests/Other"]
        with self.assertRaisesRegex(RuntimeStorageAuthorityError, "subpaths differ"):
            self.load(sign(payload))

    def test_operations_must_be_the_exact_canonical_sequence(self) -> None:
        for operations in (
            list(reversed(STORAGE_OPERATIONS)),
            list(STORAGE_OPERATIONS[:-1]),
            [*STORAGE_OPERATIONS, "DELETE"],
        ):
            payload = authority_payload()
            payload["operations"] = operations
            with self.subTest(operations=operations):
                with self.assertRaisesRegex(RuntimeStorageAuthorityError, "operations differ"):
                    self.load(sign(payload))

    def test_authority_binds_exactly_one_numeric_security(self) -> None:
        for codes in ([], ["999001", "999002"], ["ABC"], [True]):
            payload = authority_payload()
            payload["security_codes"] = codes
            with self.subTest(codes=codes):
                with self.assertRaises(RuntimeStorageAuthorityError):
                    self.load(sign(payload))

    def test_audience_market_store_kind_and_algorithm_are_locked(self) -> None:
        cases = (
            ("audience", "other-audience", "audience mismatch"),
            ("market", "OTHER_MARKET", "market mismatch"),
            ("store_kind", "EPHEMERAL", "store kind mismatch"),
        )
        for field, value, message in cases:
            payload = authority_payload()
            payload[field] = value
            with self.subTest(field=field):
                with self.assertRaisesRegex(RuntimeStorageAuthorityError, message):
                    self.load(sign(payload))

        payload = authority_payload()
        authentication = payload["authentication"]
        assert isinstance(authentication, dict)
        authentication["algorithm"] = "NONE"
        with self.assertRaisesRegex(RuntimeStorageAuthorityError, "algorithm mismatch"):
            self.load(sign(payload))

    def test_validity_window_and_decision_time_fail_closed(self) -> None:
        with self.assertRaisesRegex(RuntimeStorageAuthorityError, "not valid"):
            self.load(decision_at="2026-08-29T09:00:00+03:00")
        with self.assertRaises(RuntimeStorageAuthorityError):
            self.load(decision_at=True)
        with self.assertRaises(RuntimeStorageAuthorityError):
            self.load(decision_at="2026-08-27T10:00:00")

        payload = authority_payload()
        payload["issued_at"] = True
        with self.assertRaises(RuntimeStorageAuthorityError):
            self.load(sign(payload))

        payload = authority_payload()
        payload["expires_at"] = payload["issued_at"]
        with self.assertRaisesRegex(RuntimeStorageAuthorityError, "validity window is empty"):
            self.load(sign(payload))

    def test_require_grant_rejects_mapping_root_code_operation_and_time_tamper(self) -> None:
        authority = self.load()
        cases = (
            ({}, STORAGE_LOGICAL_ROOT, "999001", "READ_REOPEN", DECISION_AT),
            (authority, "AI Rebuild/04_Curated_Core/OTHER", "999001", "READ_REOPEN", DECISION_AT),
            (authority, STORAGE_LOGICAL_ROOT, "999002", "READ_REOPEN", DECISION_AT),
            (authority, STORAGE_LOGICAL_ROOT, "999001", "DELETE", DECISION_AT),
            (authority, STORAGE_LOGICAL_ROOT, "999001", "READ_REOPEN", "2026-08-29T09:00:00+03:00"),
            (authority, STORAGE_LOGICAL_ROOT, "999001", "READ_REOPEN", True),
        )
        for args in cases:
            with self.subTest(args=args[1:]):
                with self.assertRaises(RuntimeStorageAuthorityError):
                    require_storage_grant(*args)  # type: ignore[arg-type]

    def test_require_grant_rejects_direct_construction_replace_and_copy(self) -> None:
        authority = self.load()
        authority_type = type(authority)
        direct = authority_type(
            **{
                name: getattr(authority, name)
                for name in authority_type.__dataclass_fields__
            }
        )
        candidates = (
            direct,
            replace(authority),
            copy.copy(authority),
            copy.deepcopy(authority),
        )
        for candidate in candidates:
            with self.subTest(candidate=type(candidate).__name__):
                with self.assertRaisesRegex(
                    RuntimeStorageAuthorityError,
                    "not admitted by the authenticated loader",
                ):
                    require_storage_grant(
                        candidate,
                        STORAGE_LOGICAL_ROOT,
                        "999001",
                        "READ_REOPEN",
                        DECISION_AT,
                    )

    def test_require_grant_rejects_object_setattr_field_and_shape_tampering(self) -> None:
        replacements = {
            "grant_id": "tampered-grant",
            "subject_id": "TAMPERED",
            "logical_root": "AI Rebuild/04_Curated_Core/OTHER",
            "allowed_subpaths": ("00_Manifests/Other",),
            "store_kind": "OTHER_STORE",
            "market": "OTHER_MARKET",
            "security_codes": frozenset({"999002"}),
            "operations": ("READ_REOPEN",),
            "issued_at": datetime.fromisoformat("2026-08-27T10:00:00+03:00"),
            "expires_at": datetime.fromisoformat("2026-08-27T12:00:00+03:00"),
            "authenticated_key_id": "tampered-key",
            "content_sha256": "0" * 64,
        }
        for field, value in replacements.items():
            with self.subTest(field=field):
                authority = self.load()
                object.__setattr__(authority, field, value)
                with self.assertRaisesRegex(RuntimeStorageAuthorityError, "was modified"):
                    require_storage_grant(
                        authority,
                        STORAGE_LOGICAL_ROOT,
                        "999001",
                        "READ_REOPEN",
                        DECISION_AT,
                    )

        authority = self.load()
        object.__setattr__(authority, "active_at", lambda _decision_at: True)
        with self.assertRaisesRegex(RuntimeStorageAuthorityError, "was modified"):
            require_storage_grant(
                authority,
                STORAGE_LOGICAL_ROOT,
                "999001",
                "READ_REOPEN",
                "2026-08-29T09:00:00+03:00",
            )

    def test_duplicate_or_unknown_json_keys_are_rejected(self) -> None:
        payload = authority_payload()
        payload["unexpected"] = "value"
        with self.assertRaisesRegex(RuntimeStorageAuthorityError, "unknown keys"):
            self.load(sign(payload))

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "storage-authority.json"
            path.write_text('{"schema_version":"a","schema_version":"b"}', encoding="utf-8")
            with self.assertRaisesRegex(RuntimeStorageAuthorityError, "duplicate key"):
                load_runtime_storage_authority(path, KEY, KEY_ID, DECISION_AT)


if __name__ == "__main__":
    unittest.main()
