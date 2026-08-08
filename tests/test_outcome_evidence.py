from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

from kubo.outcome_evidence import (
    MAX_OUTCOME_EVIDENCE_ARTIFACTS,
    MAX_OUTCOME_EVIDENCE_BYTES,
    OUTCOME_UNITS,
    OutcomeEvidenceError,
    validate_outcome_evidence_packet,
    validate_outcome_payload,
)


ROOT = Path(__file__).resolve().parents[1]
DECISION_AT = "2026-08-07T10:00:00+03:00"
ARTIFACT_AT = "2026-08-07T11:00:00+03:00"
OBSERVED_AT = "2026-08-08T10:00:00+03:00"


def _artifact(path: str, content: bytes, *, observed_at: str = ARTIFACT_AT) -> dict[str, object]:
    return {
        "path": path,
        "sha256": hashlib.sha256(content).hexdigest(),
        "size_bytes": len(content),
        "source_id": "official_close",
        "source_url": "https://example.com/outcomes/101",
        "content_type": "application/json",
        "observed_at": observed_at,
    }


def _write_packet(
    root: Path,
    *,
    contents: tuple[tuple[str, bytes], ...] = (("raw/close.json", b'{"close": 123}'),),
) -> dict[str, object]:
    artifacts: list[dict[str, object]] = []
    for relative, content in contents:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        artifacts.append(_artifact(relative, content))
    manifest: dict[str, object] = {
        "schema_version": "1.0",
        "outcome_id": "outcome-1",
        "decision_id": "decision-1",
        "security_code": "101",
        "artifacts": artifacts,
    }
    (root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def _save_manifest(root: Path, manifest: dict[str, object]) -> None:
    (root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _validate(root: Path):
    return validate_outcome_evidence_packet(
        root,
        outcome_id="outcome-1",
        decision_id="decision-1",
        security_code="101",
        decision_at=DECISION_AT,
        observed_at=OBSERVED_AT,
    )


def _payload(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": "1.0",
        "security_code": "101",
        "metric_id": "session_return",
        "value": 0.025,
        "unit": "DECIMAL_RETURN",
        "measurement_start_at": "2026-08-07T10:00:00+03:00",
        "measurement_end_at": "2026-08-08T09:30:00+03:00",
        "method_id": "official_close_to_close_v1",
        "notes": "Official close-to-close measurement.",
    }
    value.update(overrides)
    return value


class OutcomeEvidencePacketTests(unittest.TestCase):
    def test_valid_packet_returns_stable_complete_hash_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            contents = (
                ("raw/close.json", b'{"close": 123}'),
                ("raw/benchmark.json", b'{"close": 456}'),
            )
            _write_packet(root, contents=contents)
            first = _validate(root)
            second = _validate(root)
            self.assertEqual(first, second)
            self.assertEqual(first.artifact_count, 2)
            self.assertEqual(first.total_bytes, sum(len(content) for _, content in contents))
            self.assertEqual(
                first.artifact_hashes,
                tuple(hashlib.sha256(content).hexdigest() for _, content in sorted(contents)),
            )
            self.assertRegex(first.packet_hash, r"^[0-9a-f]{64}$")
            self.assertIsInstance(first.to_dict()["artifact_hashes"], list)

    def test_packet_hash_commits_manifest_metadata_and_raw_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = _write_packet(root)
            original = _validate(root).packet_hash
            artifact = manifest["artifacts"][0]
            assert isinstance(artifact, dict)
            artifact["source_url"] = "https://example.com/outcomes/101?version=2"
            _save_manifest(root, manifest)
            changed_manifest = _validate(root).packet_hash
            self.assertNotEqual(original, changed_manifest)

            raw = root / "raw/close.json"
            raw.write_bytes(b'{"close": 124}')
            artifact["sha256"] = hashlib.sha256(raw.read_bytes()).hexdigest()
            artifact["size_bytes"] = raw.stat().st_size
            _save_manifest(root, manifest)
            changed_raw = _validate(root).packet_hash
            self.assertNotEqual(changed_manifest, changed_raw)

    def test_tampered_artifact_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_packet(root)
            (root / "raw/close.json").write_bytes(b'{"close": 999}')
            with self.assertRaisesRegex(OutcomeEvidenceError, "sha256 mismatch"):
                _validate(root)

    def test_actual_size_must_match_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = _write_packet(root)
            artifact = manifest["artifacts"][0]
            assert isinstance(artifact, dict)
            artifact["size_bytes"] = int(artifact["size_bytes"]) + 1
            _save_manifest(root, manifest)
            with self.assertRaisesRegex(OutcomeEvidenceError, "size mismatch"):
                _validate(root)

    def test_path_escape_absolute_and_noncanonical_paths_are_rejected(self) -> None:
        for path in ("../outside.json", "/tmp/outside.json", "raw/../outside.json", "raw//close.json"):
            with self.subTest(path=path), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                manifest = _write_packet(root)
                artifact = manifest["artifacts"][0]
                assert isinstance(artifact, dict)
                artifact["path"] = path
                _save_manifest(root, manifest)
                with self.assertRaisesRegex(OutcomeEvidenceError, "path|raw/"):
                    _validate(root)

    def test_symlink_artifact_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "raw"
            raw.mkdir()
            target = root / "outside.json"
            target.write_bytes(b'{"close": 123}')
            link = raw / "close.json"
            try:
                os.symlink(target, link)
            except (NotImplementedError, OSError) as exc:  # pragma: no cover - platform dependent.
                self.skipTest(f"symlink creation unavailable: {exc}")
            manifest = {
                "schema_version": "1.0",
                "outcome_id": "outcome-1",
                "decision_id": "decision-1",
                "security_code": "101",
                "artifacts": [_artifact("raw/close.json", target.read_bytes())],
            }
            _save_manifest(root, manifest)
            with self.assertRaisesRegex(OutcomeEvidenceError, "symlink"):
                _validate(root)

    def test_raw_inventory_must_match_manifest_exactly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_packet(root)
            (root / "raw/unreferenced.txt").write_text("extra", encoding="utf-8")
            with self.assertRaisesRegex(OutcomeEvidenceError, "unreferenced"):
                _validate(root)

    def test_artifact_time_must_be_inside_decision_outcome_window(self) -> None:
        for artifact_at in (
            "2026-08-07T09:59:59+03:00",
            "2026-08-08T10:00:01+03:00",
        ):
            with self.subTest(artifact_at=artifact_at), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                manifest = _write_packet(root)
                artifact = manifest["artifacts"][0]
                assert isinstance(artifact, dict)
                artifact["observed_at"] = artifact_at
                _save_manifest(root, manifest)
                with self.assertRaisesRegex(OutcomeEvidenceError, "decision_at <= artifact"):
                    _validate(root)

    def test_manifest_identity_must_match_envelope(self) -> None:
        for field, replacement, message in (
            ("outcome_id", "outcome-2", "outcome_id"),
            ("decision_id", "decision-2", "decision_id"),
            ("security_code", "102", "security_code"),
        ):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                manifest = _write_packet(root)
                manifest[field] = replacement
                _save_manifest(root, manifest)
                with self.assertRaisesRegex(OutcomeEvidenceError, message):
                    _validate(root)

    def test_strict_manifest_rejects_duplicate_unknown_and_nan(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_packet(root)
            original = (root / "manifest.json").read_text(encoding="utf-8")
            duplicate = original.replace(
                '"schema_version": "1.0",',
                '"schema_version": "1.0",\n  "schema_version": "1.0",',
                1,
            )
            (root / "manifest.json").write_text(duplicate, encoding="utf-8")
            with self.assertRaisesRegex(OutcomeEvidenceError, "duplicate object key"):
                _validate(root)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = _write_packet(root)
            manifest["unknown"] = "value"
            _save_manifest(root, manifest)
            with self.assertRaisesRegex(OutcomeEvidenceError, "unknown fields"):
                _validate(root)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = _write_packet(root)
            artifact = manifest["artifacts"][0]
            assert isinstance(artifact, dict)
            artifact["size_bytes"] = float("nan")
            (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(OutcomeEvidenceError, "non-JSON numeric"):
                _validate(root)

    def test_duplicate_artifact_path_and_hash_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = _write_packet(root)
            artifacts = manifest["artifacts"]
            assert isinstance(artifacts, list)
            artifacts.append(dict(artifacts[0]))
            _save_manifest(root, manifest)
            with self.assertRaisesRegex(OutcomeEvidenceError, "duplicate artifact path"):
                _validate(root)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            content = b"identical"
            manifest = _write_packet(
                root,
                contents=(("raw/one.txt", content), ("raw/two.txt", content)),
            )
            _save_manifest(root, manifest)
            with self.assertRaisesRegex(OutcomeEvidenceError, "duplicate artifact sha256"):
                _validate(root)

    def test_sha256_must_use_canonical_lowercase_text(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = _write_packet(root)
            artifact = manifest["artifacts"][0]
            assert isinstance(artifact, dict)
            artifact["sha256"] = str(artifact["sha256"]).upper()
            _save_manifest(root, manifest)
            with self.assertRaisesRegex(OutcomeEvidenceError, "canonical lowercase"):
                _validate(root)

    def test_artifact_count_and_declared_total_are_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = _write_packet(root)
            artifacts = manifest["artifacts"]
            assert isinstance(artifacts, list)
            manifest["artifacts"] = [dict(artifacts[0]) for _ in range(MAX_OUTCOME_EVIDENCE_ARTIFACTS + 1)]
            _save_manifest(root, manifest)
            with self.assertRaisesRegex(OutcomeEvidenceError, "1..32"):
                _validate(root)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = _write_packet(
                root,
                contents=(("raw/one.txt", b"one"), ("raw/two.txt", b"two")),
            )
            artifacts = manifest["artifacts"]
            assert isinstance(artifacts, list)
            artifacts[0]["size_bytes"] = MAX_OUTCOME_EVIDENCE_BYTES
            artifacts[1]["size_bytes"] = 1
            _save_manifest(root, manifest)
            with self.assertRaisesRegex(OutcomeEvidenceError, "declared bytes"):
                _validate(root)

    def test_unsafe_urls_and_noncanonical_content_type_are_rejected(self) -> None:
        cases = (
            ("source_url", "http://example.com/outcome", "HTTPS|https"),
            ("source_url", "https://user:password@example.com/outcome", "userinfo"),  # secret-guard: allow — rejection fixture
            ("source_url", "https://example.com/outcome?access_token=x", "credential"),  # secret-guard: allow — rejection fixture
            ("source_url", "https://example.com/outcome file", "whitespace"),
            ("source_url", "https://localhost/outcome", "public DNS"),
            ("content_type", "Application/JSON; charset=utf-8", "media type"),
        )
        for field, value, message in cases:
            with self.subTest(field=field, value=value), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                manifest = _write_packet(root)
                artifact = manifest["artifacts"][0]
                assert isinstance(artifact, dict)
                artifact[field] = value
                _save_manifest(root, manifest)
                with self.assertRaisesRegex(OutcomeEvidenceError, message):
                    _validate(root)


class OutcomePayloadTests(unittest.TestCase):
    def _validate(self, payload: dict[str, object]) -> dict[str, object]:
        return validate_outcome_payload(
            payload,
            expected_security_code="101",
            decision_at=DECISION_AT,
            observed_at=OBSERVED_AT,
        )

    def test_valid_payload_is_detached_and_all_units_are_supported(self) -> None:
        for unit in sorted(OUTCOME_UNITS):
            value: int | float = 2
            if unit == "BOOLEAN_FLAG":
                value = 1
            elif unit not in {"COUNT", "BOOLEAN_FLAG"}:
                value = 0.25
            with self.subTest(unit=unit):
                payload = _payload(unit=unit, value=value)
                result = self._validate(payload)
                self.assertEqual(result, payload)
                self.assertIsNot(result, payload)

    def test_security_code_uses_the_same_official_length_bound_as_requests(self) -> None:
        with self.assertRaisesRegex(OutcomeEvidenceError, "official numeric security code"):
            self._validate(_payload(security_code="1" * 13))

    def test_payload_requires_exact_fields_and_strict_json_numbers(self) -> None:
        unknown = _payload(extra="value")
        with self.assertRaisesRegex(OutcomeEvidenceError, "unknown fields"):
            self._validate(unknown)
        missing = _payload()
        missing.pop("method_id")
        with self.assertRaisesRegex(OutcomeEvidenceError, "missing fields"):
            self._validate(missing)
        for value in (float("nan"), float("inf"), True, "0.1"):
            with self.subTest(value=value), self.assertRaisesRegex(
                OutcomeEvidenceError, "strict JSON|finite JSON number"
            ):
                self._validate(_payload(value=value))
        with self.assertRaisesRegex(OutcomeEvidenceError, "finite JSON number"):
            self._validate(_payload(value=10**1000))

    def test_payload_security_identity_is_bound_to_decision(self) -> None:
        with self.assertRaisesRegex(OutcomeEvidenceError, "does not match"):
            self._validate(_payload(security_code="102"))

    def test_count_and_boolean_units_have_strict_numeric_rules(self) -> None:
        for unit, value, message in (
            ("COUNT", -1, "non-negative"),
            ("COUNT", 1.5, "integer"),
            ("BOOLEAN_FLAG", 2, "0 or 1"),
            ("BOOLEAN_FLAG", 1.0, "0 or 1"),
            ("BOOLEAN_FLAG", False, "finite JSON number"),
        ):
            with self.subTest(unit=unit, value=value), self.assertRaisesRegex(
                OutcomeEvidenceError, message
            ):
                self._validate(_payload(unit=unit, value=value))

    def test_measurement_window_is_forward_timed_and_bounded(self) -> None:
        cases = (
            {
                "measurement_start_at": "2026-08-07T09:59:59+03:00",
            },
            {
                "measurement_start_at": "2026-08-08T09:31:00+03:00",
                "measurement_end_at": "2026-08-08T09:30:00+03:00",
            },
            {
                "measurement_end_at": "2026-08-08T10:00:01+03:00",
            },
        )
        for values in cases:
            with self.subTest(values=values), self.assertRaisesRegex(
                OutcomeEvidenceError, "decision_at <= start"
            ):
                self._validate(_payload(**values))

    def test_payload_text_is_canonical_and_bounded(self) -> None:
        for field, value in (
            ("metric_id", "metric id"),
            ("method_id", "method\nheading"),
            ("notes", "line one\nline two"),
            ("notes", "x" * 2001),
            ("notes", "e\u0301"),
        ):
            with self.subTest(field=field), self.assertRaises(OutcomeEvidenceError):
                self._validate(_payload(**{field: value}))

    def test_unsupported_unit_is_rejected(self) -> None:
        with self.assertRaisesRegex(OutcomeEvidenceError, "unit is not supported"):
            self._validate(_payload(unit="PERCENT"))


class OutcomeEvidenceSchemaTests(unittest.TestCase):
    def test_manifest_schema_exposes_the_same_strict_surface(self) -> None:
        schema = json.loads(
            (ROOT / "schemas/outcome-evidence-manifest.schema.json").read_text(encoding="utf-8")
        )
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(schema["properties"]["schema_version"]["const"], "1.0")
        self.assertEqual(schema["properties"]["artifacts"]["maxItems"], 32)
        artifact = schema["$defs"]["artifact"]
        self.assertFalse(artifact["additionalProperties"])
        self.assertEqual(
            set(artifact["required"]),
            {
                "path",
                "sha256",
                "size_bytes",
                "source_id",
                "source_url",
                "content_type",
                "observed_at",
            },
        )


if __name__ == "__main__":
    unittest.main()
