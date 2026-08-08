from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from kubo.cli_v3 import main
from kubo.hashing import sha256_bytes
from kubo.pipeline import ResearchPipeline
from kubo.reporting import build_report
from kubo.request_contracts import AnalysisRequest
from kubo.research_ledger import ResearchDecisionLedger
from kubo.runtime_trust import canonical_registry_bytes, verify_runtime_trust_registry
from kubo.source_network import SourceNetworkCatalog, SourceNetworkRunValidator
from kubo.synthetic_network import build_synthetic_network_run


ROOT = Path(__file__).resolve().parents[1]
KEY = b"runtime-trust-integration-key-32bytes"
KEY_ID = "integration-key-v1"
DECISION_AT = "2026-08-07T01:00:00+03:00"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def read_findings(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def write_findings(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def runtime_registry_payload(
    *,
    security_codes: list[str] | None = None,
    valid_from: str = "2026-08-07T00:00:00+03:00",
) -> dict:
    payload = {
        "schema_version": "1.0",
        "audience": "kubo-source-network",
        "registry_id": "external-registry-1",
        "issued_at": "2026-08-07T00:00:00+03:00",
        "expires_at": "2026-08-08T00:00:00+03:00",
        "entries": [
            {
                "source_id": "x_public_community",
                "subject_id": "x-account-101",
                "domains": ["x.com"],
                "security_codes": security_codes or ["101"],
                "activation_id": "activation-x-101",
                "entitlement_id": None,
                "valid_from": valid_from,
                "valid_until": "2026-08-08T00:00:00+03:00",
            }
        ],
        "authentication": {
            "algorithm": "HMAC-SHA256",
            "key_id": KEY_ID,
            "tag": "0" * 64,
        },
    }
    payload["authentication"]["tag"] = hmac.new(
        KEY,
        canonical_registry_bytes(payload),
        hashlib.sha256,
    ).hexdigest()
    return payload


def verified_registry(**kwargs):
    return verify_runtime_trust_registry(
        runtime_registry_payload(**kwargs),
        key=KEY,
        expected_key_id=KEY_ID,
        decision_at=DECISION_AT,
    )


def runtime_sensitive_run(root: Path, *, authority_codes: list[str] | None = None) -> Path:
    run = build_synthetic_network_run(root)
    manifest_path = run / "manifest.json"
    manifest = read_json(manifest_path)
    official_hash = next(
        row["sha256"] for row in manifest["artifacts"] if row["source_id"] == "cma_ifsah"
    )
    artifact = next(
        row
        for row in manifest["artifacts"]
        if row["source_id"] == "telegram_kuwaitstockex"
    )
    artifact.update(
        {
            "source_id": "x_public_community",
            "source_url": "https://x.com/issuer101",
            "runtime_authority": {
                "registry_id": "external-registry-1",
                "verified_domain": "x.com",
                "subject_id": "x-account-101",
                "security_codes": authority_codes or ["101"],
                "evidence_sha256": official_hash,
                "verified_at": "2026-08-07T00:45:00+03:00",
            },
        }
    )
    write_json(manifest_path, manifest)

    observations_path = run / "source_observations.json"
    observations = read_json(observations_path)
    observation = next(
        row
        for row in observations["sources"]
        if row["source_id"] == "telegram_kuwaitstockex"
    )
    observation.update(
        {
            "source_id": "x_public_community",
            "enabled_for_run": True,
            "activation_id": "activation-x-101",
            "activation_evidence_sha256": artifact["sha256"],
        }
    )
    write_json(observations_path, observations)

    findings_path = run / "findings.jsonl"
    findings = read_findings(findings_path)
    finding = next(row for row in findings if row["source_id"] == "telegram_kuwaitstockex")
    finding.update(
        {
            "source_id": "x_public_community",
            "source_url": "https://x.com/issuer101",
            "timing_grade": "C",
        }
    )
    write_findings(findings_path, findings)
    return run


def self_attested_issuer_run(root: Path) -> Path:
    run = build_synthetic_network_run(root)
    manifest_path = run / "manifest.json"
    manifest = read_json(manifest_path)
    official_hash = next(
        row["sha256"] for row in manifest["artifacts"] if row["source_id"] == "cma_ifsah"
    )
    artifact = next(
        row
        for row in manifest["artifacts"]
        if row["source_id"] == "boursa_disclosure_archive"
    )
    artifact.update(
        {
            "source_id": "issuer_ir_verified",
            "source_url": "https://issuer.test/ir",
            "runtime_authority": {
                "registry_id": "packet-self-asserted-registry",
                "verified_domain": "issuer.test",
                "subject_id": "issuer-101",
                "security_codes": ["101"],
                "evidence_sha256": official_hash,
                "verified_at": "2026-08-07T00:45:00+03:00",
            },
        }
    )
    write_json(manifest_path, manifest)

    observations_path = run / "source_observations.json"
    observations = read_json(observations_path)
    observation = next(
        row
        for row in observations["sources"]
        if row["source_id"] == "boursa_disclosure_archive"
    )
    observation.update(
        {
            "source_id": "issuer_ir_verified",
            "enabled_for_run": True,
            "activation_id": "packet-self-asserted-activation",
            "activation_evidence_sha256": artifact["sha256"],
        }
    )
    write_json(observations_path, observations)

    findings_path = run / "findings.jsonl"
    findings = read_findings(findings_path)
    finding = next(
        row for row in findings if row["source_id"] == "boursa_disclosure_archive"
    )
    finding.update(
        {
            "source_id": "issuer_ir_verified",
            "source_url": "https://issuer.test/ir",
            "fact_type": "ISSUER_RELEASE",
        }
    )
    write_findings(findings_path, findings)
    return run


def self_attested_licensed_run(root: Path) -> Path:
    run = build_synthetic_network_run(root)
    manifest_path = run / "manifest.json"
    manifest = read_json(manifest_path)
    artifact = next(
        row
        for row in manifest["artifacts"]
        if row["source_id"] == "tradingview_screeners"
    )
    artifact.update(
        {
            "source_id": "ice_kuwait_archive",
            "source_url": "https://developer.ice.com/kuwait/export",
        }
    )
    receipt_bytes = b'{"fixture":"self-asserted entitlement receipt"}\n'
    receipt_path = run / "raw" / "ice_entitlement_receipt.json"
    receipt_path.write_bytes(receipt_bytes)
    receipt_hash = sha256_bytes(receipt_bytes)
    manifest["artifacts"].append(
        {
            "path": "raw/ice_entitlement_receipt.json",
            "sha256": receipt_hash,
            "size_bytes": len(receipt_bytes),
            "source_id": "ice_kuwait_archive",
            "source_url": "https://developer.ice.com/kuwait/entitlement",
            "observed_at": "2026-08-07T00:50:00+03:00",
            "capture_kind": "ACCESS_RECEIPT",
        }
    )
    write_json(manifest_path, manifest)
    contract_path = run / "research_run.json"
    contract = read_json(contract_path)
    contract["usage"]["raw_bytes"] += len(receipt_bytes)
    contract["usage"]["requests"] += 1
    write_json(contract_path, contract)

    observations_path = run / "source_observations.json"
    observations = read_json(observations_path)
    observation = next(
        row
        for row in observations["sources"]
        if row["source_id"] == "tradingview_screeners"
    )
    observation.update(
        {
            "source_id": "ice_kuwait_archive",
            "access_mode": "LICENSED_VENDOR",
            "raw_sha256s": [artifact["sha256"], receipt_hash],
            "enabled_for_run": True,
            "activation_id": "packet-self-asserted-ice-activation",
            "activation_evidence_sha256": artifact["sha256"],
            "entitlement_id": "packet-self-asserted-ice-entitlement",
            "entitlement_evidence_sha256": receipt_hash,
        }
    )
    write_json(observations_path, observations)

    findings_path = run / "findings.jsonl"
    findings = read_findings(findings_path)
    for finding in findings:
        if finding["source_id"] == "tradingview_screeners":
            finding.update(
                {
                    "source_id": "ice_kuwait_archive",
                    "source_url": "https://developer.ice.com/kuwait/export",
                    "fact_type": "LICENSED_HISTORY",
                }
            )
    write_findings(findings_path, findings)
    return run


class RuntimeTrustIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = SourceNetworkCatalog(ROOT / "config")
        self.pipeline = ResearchPipeline(ROOT)

    def test_sensitive_source_is_fail_closed_and_provenance_reaches_ledger(self):
        with tempfile.TemporaryDirectory() as directory:
            run = runtime_sensitive_run(Path(directory) / "run")
            missing = SourceNetworkRunValidator(
                run,
                self.catalog,
                "next_session_rank",
            ).validate()
            self.assertEqual(missing.status, "BLOCKED")
            self.assertTrue(
                any("external runtime trust registry" in item for item in missing.structural_errors),
                missing.structural_errors,
            )

            registry = verified_registry()
            validation = SourceNetworkRunValidator(
                run,
                self.catalog,
                "next_session_rank",
                runtime_trust_registry=registry,
            ).validate()
            self.assertEqual(validation.status, "PASS", validation.to_dict())
            self.assertTrue(validation.runtime_trust_required)
            self.assertEqual(validation.sensitive_source_ids, ("x_public_community",))
            self.assertEqual(validation.runtime_trust_registry_hash, registry.content_sha256)

            plan = self.pipeline.plan(
                "next_session_rank",
                network_run_root=run,
                runtime_trust_registry=registry,
            )
            self.assertEqual(plan["runtime_trust_registry_hash"], registry.content_sha256)
            request = AnalysisRequest.from_dict(
                {"request_id": "runtime-trust-decision", "product_id": "next_session_rank"}
            )
            report = build_report(plan, request)
            self.assertTrue(report["runtime_trust_required"])
            self.assertEqual(report["runtime_trust_registry_id"], registry.registry_id)
            self.assertEqual(report["runtime_trust_registry_hash"], registry.content_sha256)
            self.assertEqual(report["runtime_trust_key_id"], KEY_ID)

            ledger = ResearchDecisionLedger(
                Path(directory) / "decisions.jsonl",
                Path(directory) / "outcomes.jsonl",
                "runtime-trust-ledger",
            )
            event = ledger.record_report(
                report,
                actor_or_model_id="runtime-trust-integration",
                policy_hash="a" * 64,
                code_hash="b" * 64,
                configuration_hash="c" * 64,
                issued_at="2026-08-07T02:00:00+03:00",
                recorded_at="2026-08-07T02:01:00+03:00",
                test_mode=True,
            )
            self.assertEqual(event["runtime_trust_registry_hash"], registry.content_sha256)
            self.assertEqual(ledger.verify()["status"], "PASS")

    def test_self_attested_issuer_authority_is_rejected_without_external_registry(self):
        with tempfile.TemporaryDirectory() as directory:
            run = self_attested_issuer_run(Path(directory) / "run")
            result = SourceNetworkRunValidator(
                run,
                self.catalog,
                "next_session_rank",
            ).validate()
            self.assertEqual(result.status, "BLOCKED")
            self.assertTrue(
                any("external runtime trust registry" in item for item in result.structural_errors),
                result.structural_errors,
            )

    def test_self_attested_licensed_receipt_is_rejected_without_external_registry(self):
        with tempfile.TemporaryDirectory() as directory:
            run = self_attested_licensed_run(Path(directory) / "run")
            result = SourceNetworkRunValidator(
                run,
                self.catalog,
                "next_session_rank",
            ).validate()
            self.assertEqual(result.status, "BLOCKED")
            self.assertTrue(
                any("external runtime trust registry" in item for item in result.structural_errors),
                result.structural_errors,
            )

    def test_entry_that_starts_after_capture_cannot_authorize_old_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            run = runtime_sensitive_run(Path(directory) / "run")
            registry = verified_registry(valid_from="2026-08-07T00:55:00+03:00")
            result = SourceNetworkRunValidator(
                run,
                self.catalog,
                "next_session_rank",
                runtime_trust_registry=registry,
            ).validate()
            self.assertEqual(result.status, "BLOCKED")
            self.assertTrue(
                any(
                    "runtime authority is not uniquely authorized" in item
                    for item in result.structural_errors
                ),
                result.structural_errors,
            )

    def test_packet_security_binding_cannot_be_weaker_than_external_registry(self):
        with tempfile.TemporaryDirectory() as directory:
            run = runtime_sensitive_run(Path(directory) / "run", authority_codes=["102"])
            registry = verified_registry(security_codes=["101", "102"])
            result = SourceNetworkRunValidator(
                run,
                self.catalog,
                "next_session_rank",
                runtime_trust_registry=registry,
            ).validate()
            self.assertEqual(result.status, "BLOCKED")
            self.assertTrue(
                any(
                    "structured runtime domain/security authority" in item
                    for item in result.structural_errors
                ),
                result.structural_errors,
            )

    def test_cli_loads_registry_only_from_outside_packet_and_env_key(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            run = runtime_sensitive_run(workspace / "run")
            registry_path = workspace / "external-runtime-trust.json"
            write_json(registry_path, runtime_registry_payload())
            environment = {
                "KUBO_RUNTIME_TRUST_HMAC_KEY": "hex:" + KEY.hex(),
                "KUBO_RUNTIME_TRUST_HMAC_KEY_ID": KEY_ID,
            }
            with mock.patch.dict("os.environ", environment, clear=False):
                code = main(
                    [
                        "--project-root",
                        str(ROOT),
                        "validate-network-run",
                        "--run",
                        str(run),
                        "--product",
                        "next_session_rank",
                        "--runtime-trust-registry",
                        str(registry_path),
                    ]
                )
                self.assertEqual(code, 0)

                in_packet = run / "runtime-trust.json"
                write_json(in_packet, runtime_registry_payload())
                with self.assertRaisesRegex(ValueError, "outside the evidence packet"):
                    main(
                        [
                            "--project-root",
                            str(ROOT),
                            "validate-network-run",
                            "--run",
                            str(run),
                            "--product",
                            "next_session_rank",
                            "--runtime-trust-registry",
                            str(in_packet),
                        ]
                    )


if __name__ == "__main__":
    unittest.main()
