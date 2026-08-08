from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
import unittest

from kubo.runtime_trust import (
    RuntimeTrustError,
    canonical_registry_bytes,
    verify_runtime_trust_registry,
)


ROOT = Path(__file__).resolve().parents[1]
KEY = b"runtime-trust-test-key-material-32bytes"
OTHER_KEY = b"runtime-trust-other-key-material-32byt"
DECISION_AT = "2026-08-07T12:00:00+03:00"


def registry_payload() -> dict:
    payload = {
        "schema_version": "1.0",
        "audience": "kubo-source-network",
        "registry_id": "registry-test-1",
        "issued_at": "2026-08-07T00:00:00+03:00",
        "expires_at": "2026-08-08T00:00:00+03:00",
        "entries": [
            {
                "source_id": "issuer_ir_verified",
                "subject_id": "issuer-101",
                "domains": ["issuer.test"],
                "security_codes": ["101"],
                "activation_id": "activation-101",
                "entitlement_id": None,
                "valid_from": "2026-08-07T00:00:00+03:00",
                "valid_until": "2026-08-08T00:00:00+03:00",
            },
            {
                "source_id": "ice_kuwait_archive",
                "subject_id": "ice-provider-account",
                "domains": ["developer.ice.test"],
                "security_codes": ["101", "202"],
                "activation_id": "activation-ice",
                "entitlement_id": "entitlement-ice",
                "valid_from": "2026-08-07T00:00:00+03:00",
                "valid_until": "2026-08-08T00:00:00+03:00",
            },
        ],
        "authentication": {
            "algorithm": "HMAC-SHA256",
            "key_id": "runtime-test-key",
            "tag": "0" * 64,
        },
    }
    return sign(payload)


def sign(payload: dict, key: bytes = KEY) -> dict:
    payload["authentication"]["tag"] = hmac.new(
        key,
        canonical_registry_bytes(payload),
        hashlib.sha256,
    ).hexdigest()
    return payload


def verify(payload: dict | str, *, key: bytes = KEY, key_id: str = "runtime-test-key"):
    return verify_runtime_trust_registry(
        payload,
        key=key,
        expected_key_id=key_id,
        decision_at=DECISION_AT,
    )


class RuntimeTrustTests(unittest.TestCase):
    def test_valid_registry_authorizes_exact_runtime_bindings(self):
        registry = verify(registry_payload())
        self.assertEqual(registry.registry_id, "registry-test-1")
        self.assertEqual(registry.authenticated_key_id, "runtime-test-key")
        self.assertRegex(registry.content_sha256, r"^[0-9a-f]{64}$")
        registry.require_authority(
            source_id="issuer_ir_verified",
            subject_id="issuer-101",
            domain="news.issuer.test",
            security_code="101",
            decision_at=DECISION_AT,
        )
        registry.require_activation(
            source_id="issuer_ir_verified",
            activation_id="activation-101",
            security_code="101",
            decision_at=DECISION_AT,
        )
        registry.require_entitlement(
            source_id="ice_kuwait_archive",
            entitlement_id="entitlement-ice",
            security_code="202",
            decision_at=DECISION_AT,
        )

    def test_wrong_key_fails_authentication(self):
        with self.assertRaisesRegex(RuntimeTrustError, "authentication failed"):
            verify(registry_payload(), key=OTHER_KEY)

    def test_wrong_or_missing_expected_key_id_fails_closed(self):
        with self.assertRaisesRegex(RuntimeTrustError, "key_id mismatch"):
            verify(registry_payload(), key_id="unexpected-key")
        with self.assertRaisesRegex(RuntimeTrustError, "expected_key_id"):
            verify(registry_payload(), key_id="")

        payload = registry_payload()
        payload["authentication"]["key_id"] = "renamed-key"
        with self.assertRaisesRegex(RuntimeTrustError, "authentication failed"):
            verify(payload, key_id="renamed-key")

    def test_wrong_audience_is_rejected_even_with_a_valid_tag(self):
        payload = registry_payload()
        payload["audience"] = "another-service"
        sign(payload)
        with self.assertRaisesRegex(RuntimeTrustError, "audience mismatch"):
            verify(payload)

    def test_expired_registry_is_rejected(self):
        payload = registry_payload()
        payload["issued_at"] = "2026-08-05T00:00:00+03:00"
        payload["expires_at"] = "2026-08-06T00:00:00+03:00"
        for entry in payload["entries"]:
            entry["valid_from"] = "2026-08-05T00:00:00+03:00"
            entry["valid_until"] = "2026-08-06T00:00:00+03:00"
        sign(payload)
        with self.assertRaisesRegex(RuntimeTrustError, "not valid at decision_at"):
            verify(payload)

    def test_duplicate_json_keys_and_entries_are_rejected(self):
        document = json.dumps(registry_payload()).replace(
            '"schema_version": "1.0"',
            '"schema_version": "1.0", "schema_version": "1.0"',
            1,
        )
        with self.assertRaisesRegex(RuntimeTrustError, "duplicate JSON key"):
            verify_runtime_trust_registry(
                document,
                key=KEY,
                expected_key_id="runtime-test-key",
                decision_at=DECISION_AT,
            )

        payload = registry_payload()
        payload["entries"].append(dict(payload["entries"][0]))
        sign(payload)
        with self.assertRaisesRegex(RuntimeTrustError, "duplicate runtime trust entry"):
            verify(payload)

    def test_authenticated_content_tampering_is_rejected(self):
        payload = registry_payload()
        payload["entries"][0]["security_codes"] = ["999"]
        with self.assertRaisesRegex(RuntimeTrustError, "authentication failed"):
            verify(payload)

    def test_authorization_requires_exact_subject_source_ids_and_security(self):
        registry = verify(registry_payload())
        cases = (
            lambda: registry.require_authority(
                source_id="issuer_ir_verified",
                subject_id="other-issuer",
                domain="issuer.test",
                security_code="101",
                decision_at=DECISION_AT,
            ),
            lambda: registry.require_authority(
                source_id="issuer_ir_verified",
                subject_id="issuer-101",
                domain="issuer.test.evil.test",
                security_code="101",
                decision_at=DECISION_AT,
            ),
            lambda: registry.require_activation(
                source_id="issuer_ir_verified",
                activation_id="activation-101",
                security_code="202",
                decision_at=DECISION_AT,
            ),
            lambda: registry.require_entitlement(
                source_id="ice_kuwait_archive",
                entitlement_id="entitlement-ice",
                security_code="999",
                decision_at=DECISION_AT,
            ),
        )
        for call in cases:
            with self.subTest(call=call), self.assertRaises(RuntimeTrustError):
                call()

    def test_unknown_keys_unsafe_domains_and_short_keys_are_rejected(self):
        payload = registry_payload()
        payload["self_asserted"] = True
        sign(payload)
        with self.assertRaisesRegex(RuntimeTrustError, "unknown keys"):
            verify(payload)

        payload = registry_payload()
        payload["entries"][0]["domains"] = ["https://issuer.test/path"]
        sign(payload)
        with self.assertRaisesRegex(RuntimeTrustError, "hostname only"):
            verify(payload)

        payload = registry_payload()
        payload["entries"][0]["domains"] = ["issuer.internal"]
        sign(payload)
        with self.assertRaisesRegex(RuntimeTrustError, "non-public domain suffix"):
            verify(payload)

        payload = registry_payload()
        payload[1] = "non-string-key"
        with self.assertRaisesRegex(RuntimeTrustError, "keys must be strings"):
            verify(payload)

        with self.assertRaisesRegex(RuntimeTrustError, "at least 32 bytes"):
            verify(registry_payload(), key=b"short")

    def test_schema_is_parseable_and_matches_the_runtime_contract(self):
        schema = json.loads(
            (ROOT / "schemas" / "runtime-trust-registry.schema.json").read_text(encoding="utf-8")
        )
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(schema["properties"]["audience"]["const"], "kubo-source-network")
        self.assertEqual(
            schema["$defs"]["authentication"]["properties"]["algorithm"]["const"],
            "HMAC-SHA256",
        )


if __name__ == "__main__":
    unittest.main()
