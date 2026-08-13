from __future__ import annotations

import copy
import hashlib
import hmac
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

try:
    from jsonschema import Draft202012Validator
except ModuleNotFoundError:  # Core-only local runs omit the optional test extra.
    Draft202012Validator = None  # type: ignore[assignment,misc]

from kubo.hashing import canonical_json_bytes, sha256_bytes
from kubo.tri_security_admission import (
    BOUNDARY_STAGE_MAP,
    RUN_AUTHORITY_ROOT,
    SEMANTIC_ADMISSION_ALGORITHM,
    SEMANTIC_ADMISSION_AUDIENCE,
    SEMANTIC_ADMISSION_CLAIM_BOUNDARY,
    SEMANTIC_ADMISSION_FILE,
    SEMANTIC_ADMISSION_SCHEMA_VERSION,
    STAGE_PREDECESSORS,
    BoundaryAdmissionError,
    VerifiedBoundaryAdmission,
)
from kubo.tri_security_lineage import (
    LINEAGE_CLAIM_BOUNDARY,
    LINEAGE_FILE,
    materialize_boundary_lineage,
    verify_boundary_lineage,
    verify_final_predecessor_lineages,
)


ROOT = Path(__file__).resolve().parents[1]
SEMANTIC_KEY = b"lineage-semantic-authority-key-32-bytes-v1"
SEMANTIC_KEY_ID = "lineage-semantic-key-v1"
RUN_ID = "lineage-run-v1"
BATCH_ID = "lineage-batch-v1"


def _signed(payload: dict[str, object]) -> tuple[dict[str, object], bytes]:
    payload["authentication"] = {
        "algorithm": SEMANTIC_ADMISSION_ALGORITHM,
        "key_id": SEMANTIC_KEY_ID,
        "tag": "0" * 64,
    }
    authentication = payload["authentication"]
    assert isinstance(authentication, dict)
    authenticated = canonical_json_bytes(
        {
            "document": {
                key: value
                for key, value in payload.items()
                if key != "authentication"
            },
            "algorithm": authentication["algorithm"],
            "key_id": authentication["key_id"],
        }
    )
    authentication["tag"] = hmac.new(
        SEMANTIC_KEY,
        authenticated,
        hashlib.sha256,
    ).hexdigest()
    return payload, canonical_json_bytes(payload)


def _rows(stage_id: str, *, run_id: str = RUN_ID) -> list[dict[str, str]]:
    result = []
    for index, predecessor in enumerate(STAGE_PREDECESSORS[stage_id]):
        digest = hashlib.sha256(f"{stage_id}:{predecessor}:{index}".encode()).hexdigest()
        result.append(
            {
                "stage_id": predecessor,
                "run_id": run_id,
                "admission_sha256": digest,
            }
        )
    return result


class TriSecurityLineageTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.root = Path(self._temporary.name)

    def token(
        self,
        boundary_id: str,
        *,
        predecessors: list[dict[str, str]] | None = None,
        run_id: str = RUN_ID,
        batch_id: str = BATCH_ID,
        admission_id: str | None = None,
    ) -> VerifiedBoundaryAdmission:
        stage_id = BOUNDARY_STAGE_MAP[boundary_id]
        predecessor_rows = predecessors if predecessors is not None else _rows(
            stage_id,
            run_id=run_id,
        )
        payload, admission_bytes = _signed(
            {
                "schema_version": SEMANTIC_ADMISSION_SCHEMA_VERSION,
                "audience": SEMANTIC_ADMISSION_AUDIENCE,
                "admission_id": admission_id or f"lineage-{boundary_id}",
                "issued_at": "2026-08-13T09:00:00+03:00",
                "boundary_id": boundary_id,
                "stage_id": stage_id,
                "v1_references": {},
                "run_binding": {"run_id": run_id, "batch_id": batch_id},
                "input_tree": {},
                "boundary_inputs": [],
                "operation_binding": {},
                "predecessor_bindings": predecessor_rows,
                "claims": {},
                "claim_boundary": SEMANTIC_ADMISSION_CLAIM_BOUNDARY,
            }
        )
        request = SimpleNamespace(
            semantic_key=SEMANTIC_KEY,
            semantic_key_id=SEMANTIC_KEY_ID,
        )
        return VerifiedBoundaryAdmission(
            request=request,  # type: ignore[arg-type]
            boundary_id=boundary_id,
            stage_id=stage_id,
            run_id=run_id,
            batch_id=batch_id,
            admission_sha256=sha256_bytes(admission_bytes),
            payload=payload,
            input_files={},
            _output_root=self.root / "unused-output",
            _input_tree_binding={},
            _boundary_input_binding=(),
            _operation_binding={},
            _admission_bytes=admission_bytes,
        )

    def publish(self, name: str, token: VerifiedBoundaryAdmission) -> Path:
        output = self.root / name
        (output / "reports").mkdir(parents=True)
        (output / SEMANTIC_ADMISSION_FILE).write_bytes(token._admission_bytes)
        materialize_boundary_lineage(token, output)
        return output

    def test_positive_lineage_is_signed_and_schema_valid_for_all_stages(self) -> None:
        validator = None
        if Draft202012Validator is not None:
            schema = json.loads(
                (ROOT / "schemas" / "tri-security-output-lineage.schema.json").read_text(
                    encoding="utf-8"
                )
            )
            validator = Draft202012Validator(schema)

        for boundary_id, stage_id in BOUNDARY_STAGE_MAP.items():
            with self.subTest(boundary_id=boundary_id):
                token = self.token(boundary_id)
                output = self.publish(boundary_id, token)
                verified = verify_boundary_lineage(
                    output,
                    semantic_key=SEMANTIC_KEY,
                    semantic_key_id=SEMANTIC_KEY_ID,
                )
                self.assertEqual(verified.boundary_id, boundary_id)
                self.assertEqual(verified.stage_id, stage_id)
                self.assertEqual(verified.admission_sha256, token.admission_sha256)
                self.assertEqual(
                    verified.payload["claim_boundary"],
                    LINEAGE_CLAIM_BOUNDARY,
                )
                self.assertEqual(
                    [row["stage_id"] for row in verified.predecessor_bindings],
                    list(STAGE_PREDECESSORS[stage_id]),
                )
                if validator is not None:
                    validator.validate(
                        json.loads((output / LINEAGE_FILE).read_text(encoding="utf-8"))
                    )

    def test_missing_tampered_and_wrong_key_lineage_fail_closed(self) -> None:
        token = self.token("import_official_foundation")

        missing = self.publish("missing", token)
        (missing / LINEAGE_FILE).unlink()
        with self.assertRaises(BoundaryAdmissionError) as raised:
            verify_boundary_lineage(
                missing,
                semantic_key=SEMANTIC_KEY,
                semantic_key_id=SEMANTIC_KEY_ID,
            )
        self.assertEqual(raised.exception.failure_code, "PREDECESSOR_BINDING_REQUIRED")

        tampered = self.publish("tampered", token)
        path = tampered / LINEAGE_FILE
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["batch_id"] = "different-batch"
        path.write_bytes(canonical_json_bytes(payload))
        with self.assertRaises(BoundaryAdmissionError) as raised:
            verify_boundary_lineage(
                tampered,
                semantic_key=SEMANTIC_KEY,
                semantic_key_id=SEMANTIC_KEY_ID,
            )
        self.assertEqual(
            raised.exception.failure_code,
            "STAGE_BINDING_AUTHENTICATION_FAILED",
        )

        wrong_key = self.publish("wrong-key", token)
        with self.assertRaises(BoundaryAdmissionError) as raised:
            verify_boundary_lineage(
                wrong_key,
                semantic_key=b"wrong-lineage-authority-key-32-bytes-v1",
                semantic_key_id=SEMANTIC_KEY_ID,
            )
        self.assertEqual(
            raised.exception.failure_code,
            "STAGE_BINDING_AUTHENTICATION_FAILED",
        )

    def test_final_verifier_rejects_valid_but_mixed_predecessor(self) -> None:
        boundaries_by_stage = {
            stage: boundary for boundary, stage in BOUNDARY_STAGE_MAP.items()
        }
        predecessor_stages = STAGE_PREDECESSORS[
            "FINAL_DATA_FOUNDATION_RECONCILIATION"
        ]
        roots: dict[str, Path] = {}
        predecessor_tokens: dict[str, VerifiedBoundaryAdmission] = {}
        for stage in predecessor_stages:
            token = self.token(boundaries_by_stage[stage])
            predecessor_tokens[stage] = token
            roots[stage] = self.publish(f"predecessor-{stage}", token)
        final_rows = [
            {
                "stage_id": stage,
                "run_id": RUN_ID,
                "admission_sha256": predecessor_tokens[stage].admission_sha256,
            }
            for stage in predecessor_stages
        ]
        final = self.token(
            "build_data_foundation_packet",
            predecessors=final_rows,
        )
        verified = verify_final_predecessor_lineages(
            final,
            predecessor_roots=roots,
        )
        self.assertEqual(
            tuple(item.stage_id for item in verified),
            predecessor_stages,
        )

        replacement = self.token(
            boundaries_by_stage["OFFICIAL_FOUNDATION"],
            admission_id="valid-but-different-official-foundation",
        )
        mixed_roots = dict(roots)
        mixed_roots["OFFICIAL_FOUNDATION"] = self.publish(
            "mixed-official-foundation",
            replacement,
        )
        with self.assertRaises(BoundaryAdmissionError) as raised:
            verify_final_predecessor_lineages(
                final,
                predecessor_roots=mixed_roots,
            )
        self.assertEqual(
            raised.exception.failure_code,
            "PREDECESSOR_BINDING_REPLAYED",
        )

    def test_sidecar_tamper_is_rejected_even_when_lineage_is_unchanged(self) -> None:
        token = self.token("import_official_foundation")
        output = self.publish("sidecar-tamper", token)
        sidecar_path = output / SEMANTIC_ADMISSION_FILE
        payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
        payload["admission_id"] = "tampered-admission"
        sidecar_path.write_bytes(canonical_json_bytes(payload))
        with self.assertRaises(BoundaryAdmissionError) as raised:
            verify_boundary_lineage(
                output,
                semantic_key=SEMANTIC_KEY,
                semantic_key_id=SEMANTIC_KEY_ID,
            )
        self.assertEqual(
            raised.exception.failure_code,
            "PREDECESSOR_BINDING_REPLAYED",
        )


if __name__ == "__main__":
    unittest.main()
