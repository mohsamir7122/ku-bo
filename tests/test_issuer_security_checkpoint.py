from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from kubo.issuer_sequential_collection import compile_issuer_sequential_collection_plan
from kubo.issuer_security_checkpoint import (
    EXTERNAL_EVIDENCE_STORE_TOCTOU_STATUS,
    IssuerSecurityCheckpointCasError,
    IssuerSecurityCheckpointError,
    IssuerSecurityCheckpointFencingError,
    IssuerSecurityCheckpointStore,
    checkpoint_cas,
    validate_issuer_security_checkpoint_policy,
)


ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc)
SEAL_KEY = b"synthetic-checkpoint-v2-test-key-material-32bytes"
SEAL_KEY_ID = "synthetic-checkpoint-v2-key"


def issuer_universe() -> dict[str, object]:
    return json.loads(
        (ROOT / "examples" / "synthetic_issuer_universe.json").read_text(encoding="utf-8")
    )


def two_security_universe() -> dict[str, object]:
    payload = issuer_universe()
    second = copy.deepcopy(payload["issuers"][0])  # type: ignore[index]
    second["issuer_id"] = "SYNTHETIC-ISSUER-2"
    second["official_registration_id"] = "SYNTHETIC-REGISTRATION-2"
    second["legal_name_ar"] = "شركة اصطناعية ثانية"
    second["legal_name_en"] = "Second Synthetic Company"
    second["security_identities"][0].update(  # type: ignore[index]
        {"security_code": "999002", "ticker": "SYN2", "isin": "KW0EQ9990028"}
    )
    payload["issuers"].append(second)  # type: ignore[union-attr]
    payload["expected_security_codes"].append("999002")  # type: ignore[union-attr]
    return payload


def compile_plan(directory: Path, universe: dict[str, object] | None = None) -> tuple[dict[str, object], dict[str, object]]:
    payload = issuer_universe() if universe is None else universe
    path = directory / "issuer-universe.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    plan = compile_issuer_sequential_collection_plan(
        ROOT,
        path,
        run_id="checkpoint-v2-synthetic-run",
        generated_at="2026-08-27T12:59:00+03:00",
    )
    return plan, payload


def create_store(
    directory: Path, *, now: datetime = NOW
) -> tuple[IssuerSecurityCheckpointStore, dict[str, object], Path]:
    plan, universe = compile_plan(directory)
    evidence = directory / "evidence"
    evidence.mkdir()
    store = IssuerSecurityCheckpointStore(
        directory / "checkpoints",
        project_root=ROOT,
        plan=plan,
        issuer_universe=universe,
    )
    checkpoint = store.create(owner_run_id="checkpoint-worker-1", now=now)
    return store, checkpoint, evidence


def write_manifest(
    evidence_root: Path,
    *,
    source_id: str,
    source_url: str,
    ordinal: int,
    observed_at: datetime,
) -> tuple[str, str]:
    packet = evidence_root / f"source-{ordinal:02d}"
    raw = packet / "raw"
    raw.mkdir(parents=True)
    content = f"synthetic raw receipt for {source_id}\n".encode()
    artifact = raw / "receipt.bin"
    artifact.write_bytes(content)
    manifest = {
        "schema_version": "3.0",
        "artifacts": [
            {
                "path": "raw/receipt.bin",
                "sha256": hashlib.sha256(content).hexdigest(),
                "size_bytes": len(content),
                "source_id": source_id,
                "source_url": source_url,
                "observed_at": observed_at.isoformat(),
                "capture_kind": "ACCESS_RECEIPT",
            }
        ],
    }
    manifest_path = packet / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    return manifest_path.relative_to(evidence_root).as_posix(), hashlib.sha256(
        manifest_path.read_bytes()
    ).hexdigest()


def result_for_source(
    source: dict[str, object],
    *,
    attempted_at: datetime,
    completed_at: datetime,
    manifest_sha256: str | None = None,
) -> dict[str, object]:
    source_id = str(source["source_id"])
    if manifest_sha256 is not None:
        status = "VERIFIED_ZERO"
        artifact_count = 1
    elif source_id == "issuer_ir_verified":
        status = "ISSUER_OFFICIAL_SITE_UNRESOLVED"
        artifact_count = 0
    elif source["requires_runtime_domain_registry"] or source["requires_entitlement"]:
        status = "ENTITLEMENT_REQUIRED"
        artifact_count = 0
    else:
        status = "BLOCKED_ACCESS"
        artifact_count = 0
    return {
        "terminal_status": status,
        "attempted_at": attempted_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "artifact_count": artifact_count,
        "observation_count": 0,
        "requested_domain": None,
        "activation_id": None,
        "entitlement_id": None,
        "artifact_manifest_sha256": manifest_sha256,
        "limitation": "Synthetic checkpoint-v2 contract fixture.",
    }


def complete_all_sources(
    store: IssuerSecurityCheckpointStore,
    checkpoint: dict[str, object],
    evidence: Path,
) -> dict[str, object]:
    row = checkpoint
    for ordinal, source in enumerate(store.security_plan["source_plan"], start=1):
        started = NOW + timedelta(seconds=ordinal * 10)
        row = store.start_next_source(now=started, **checkpoint_cas(row))
        manifest_path = None
        manifest_sha = None
        if ordinal == 1:
            source_spec = store.catalog.sources[str(source["source_id"])]
            manifest_path, manifest_sha = write_manifest(
                evidence,
                source_id=str(source["source_id"]),
                source_url=source_spec.start_urls[0],
                ordinal=ordinal,
                observed_at=started + timedelta(seconds=1),
            )
        raw_result = result_for_source(
            source,
            attempted_at=started + timedelta(seconds=1),
            completed_at=started + timedelta(seconds=2),
            manifest_sha256=manifest_sha,
        )
        row = store.complete_active_source(
            raw_result=raw_result,
            evidence_root=evidence,
            manifest_path=manifest_path,
            **checkpoint_cas(row),
        )
    return row


def schema_registry() -> tuple[dict[str, object], Registry]:
    schemas = {}
    resources = []
    for name in (
        "issuer-security-checkpoint-v2.schema.json",
        "issuer-security-reconciliation.schema.json",
        "issuer-security-terminal-seal.schema.json",
    ):
        schema = json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))
        schemas[name] = schema
        resources.append((schema["$id"], Resource.from_contents(schema)))
    return schemas, Registry().with_resources(resources)


class IssuerSecurityCheckpointTests(unittest.TestCase):
    def test_policy_and_initial_checkpoint_schema_are_locked_synthetic_only(self) -> None:
        report = validate_issuer_security_checkpoint_policy(ROOT)
        self.assertEqual(report["status"], "PASS_SYNTHETIC_CHECKPOINT_V2_POLICY")
        self.assertFalse(report["production_authorized"])
        self.assertFalse(report["second_security_allowed"])
        with tempfile.TemporaryDirectory() as directory:
            _, checkpoint, _ = create_store(Path(directory))
        schemas, registry = schema_registry()
        Draft202012Validator.check_schema(
            schemas["issuer-security-checkpoint-v2.schema.json"]
        )
        Draft202012Validator(
            schemas["issuer-security-checkpoint-v2.schema.json"],
            registry=registry,
            format_checker=FormatChecker(),
        ).validate(checkpoint)
        self.assertEqual(len(checkpoint["source_slots"]), 29)
        self.assertEqual(
            sorted({item["wave_ordinal"] for item in checkpoint["source_slots"]}),
            list(range(1, 8)),
        )

    def test_exactly_one_plan_security_and_no_second_security_are_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan, universe = compile_plan(root, two_security_universe())
            with self.assertRaisesRegex(IssuerSecurityCheckpointError, "exactly one"):
                IssuerSecurityCheckpointStore(
                    root / "checkpoints",
                    project_root=ROOT,
                    plan=plan,
                    issuer_universe=universe,
                )

    def test_append_only_preempt_resume_and_stale_writer_rejection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store, checkpoint, _ = create_store(Path(directory))
            running = store.start_next_source(
                now=NOW + timedelta(seconds=1), **checkpoint_cas(checkpoint)
            )
            old_cas = checkpoint_cas(running)
            preempted = store.preempt(
                now=NOW + timedelta(seconds=2), **old_cas
            )
            resumed = store.resume(
                new_owner_run_id="checkpoint-worker-2",
                now=NOW + timedelta(seconds=3),
                **checkpoint_cas(preempted),
            )
            self.assertEqual(resumed["generation"], 2)
            self.assertEqual(resumed["revision"], 4)
            self.assertEqual(resumed["source_slots"][0]["attempt_count"], 1)
            with self.assertRaises(IssuerSecurityCheckpointCasError):
                store.start_next_source(now=NOW + timedelta(seconds=4), **old_cas)
            stale_fence = checkpoint_cas(resumed)
            stale_fence["fencing_token"] = "f" * 64
            with self.assertRaises(IssuerSecurityCheckpointFencingError):
                store.start_next_source(now=NOW + timedelta(seconds=4), **stale_fence)
            files = sorted((Path(directory) / "checkpoints").glob("*.revision-*.json"))
            self.assertEqual(len(files), 4)

    def test_reconciliation_waits_for_29_and_terminal_bundle_reopens_raw_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store, checkpoint, evidence = create_store(Path(directory))
            with self.assertRaisesRegex(IssuerSecurityCheckpointError, "all 29"):
                store.reconcile(
                    evidence_root=evidence,
                    now=NOW + timedelta(seconds=1),
                    **checkpoint_cas(checkpoint),
                )
            terminal = complete_all_sources(store, checkpoint, evidence)
            self.assertEqual(
                [slot["status"] for slot in terminal["source_slots"]],
                ["TERMINAL"] * 29,
            )
            reconciled = store.reconcile(
                evidence_root=evidence,
                now=NOW + timedelta(seconds=400),
                **checkpoint_cas(terminal),
            )
            sealed = store.seal(
                evidence_root=evidence,
                seal_key=SEAL_KEY,
                seal_key_id=SEAL_KEY_ID,
                now=NOW + timedelta(seconds=401),
                **checkpoint_cas(reconciled),
            )
            report = store.verify_bundle(
                evidence_root=evidence,
                seal_key=SEAL_KEY,
                expected_seal_key_id=SEAL_KEY_ID,
            )
            self.assertEqual(report["status"], "PASS_SYNTHETIC_ONE_SECURITY_CHECKPOINT_BUNDLE")
            self.assertEqual(report["terminal_source_count"], 29)
            self.assertFalse(report["production_authorized"])
            self.assertFalse(report["second_security_authorized"])
            self.assertTrue(EXTERNAL_EVIDENCE_STORE_TOCTOU_STATUS.startswith("BLOCKED_"))
            schemas, registry = schema_registry()
            Draft202012Validator(
                schemas["issuer-security-reconciliation.schema.json"],
                format_checker=FormatChecker(),
            ).validate(sealed["reconciliation"])
            Draft202012Validator(
                schemas["issuer-security-terminal-seal.schema.json"],
                format_checker=FormatChecker(),
            ).validate(sealed["terminal_seal"])
            Draft202012Validator(
                schemas["issuer-security-checkpoint-v2.schema.json"],
                registry=registry,
                format_checker=FormatChecker(),
            ).validate(sealed)

    def test_checkpoint_timestamps_preserve_microseconds_consistently(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            created_at = NOW.replace(microsecond=123456)
            store, checkpoint, _ = create_store(Path(directory), now=created_at)
            self.assertEqual(checkpoint["created_at"], "2026-08-27T10:00:00.123456Z")
            self.assertEqual(checkpoint["updated_at"], checkpoint["created_at"])
            started_at = created_at + timedelta(seconds=1, microseconds=530865)
            running = store.start_next_source(
                now=started_at, **checkpoint_cas(checkpoint)
            )
            self.assertEqual(running["updated_at"], "2026-08-27T10:00:01.654321Z")
            self.assertEqual(
                running["source_slots"][0]["started_at"], running["updated_at"]
            )

    def test_create_is_exclusive_and_terminal_sources_are_immutable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store, checkpoint, evidence = create_store(Path(directory))
            with self.assertRaises(IssuerSecurityCheckpointCasError):
                store.create(owner_run_id="checkpoint-worker-1", now=NOW)
            terminal = complete_all_sources(store, checkpoint, evidence)
            first_receipt = copy.deepcopy(terminal["source_slots"][0]["source_receipt"])
            reconciled = store.reconcile(
                evidence_root=evidence,
                now=NOW + timedelta(seconds=400),
                **checkpoint_cas(terminal),
            )
            sealed = store.seal(
                evidence_root=evidence,
                seal_key=SEAL_KEY,
                seal_key_id=SEAL_KEY_ID,
                now=NOW + timedelta(seconds=401),
                **checkpoint_cas(reconciled),
            )
            self.assertEqual(sealed["source_slots"][0]["source_receipt"], first_receipt)
            with self.assertRaisesRegex(IssuerSecurityCheckpointError, "immutable"):
                store.preempt(
                    now=NOW + timedelta(seconds=402), **checkpoint_cas(sealed)
                )


if __name__ == "__main__":
    unittest.main()
