from __future__ import annotations

from contextlib import redirect_stdout
import copy
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from kubo.data_foundation_cli import main as data_foundation_main
from kubo.hashing import hash_json, sha256_file
from kubo.tri_security_pilot import (
    TRI_SECURITY_MODE,
    load_tri_security_registry,
    load_tri_security_vendor_mappings,
    prepare_tri_security_batch_workspace,
    verify_tri_security_scoped_config,
)
from kubo.vendor_symbol_mapping import PilotIdentitySeedCatalog, VendorSymbolMappingCatalog


ROOT = Path(__file__).resolve().parents[1]
FIRST_BATCH_ID = "tri-001-kfh-ship-aznoula"


def _schema_validator(name: str) -> Draft202012Validator:
    schemas = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (ROOT / "schemas").glob("*.schema.json")
    ]
    registry = Registry().with_resources(
        [
            (schema["$id"], Resource.from_contents(schema))
            for schema in schemas
            if "$id" in schema
        ]
    )
    schema = next(
        schema
        for schema in schemas
        if schema.get("$id", "").endswith(f"/{name}")
    )
    return Draft202012Validator(
        schema,
        registry=registry,
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    )


class TriSecurityPilotTests(unittest.TestCase):
    def _mutable_config(self, directory: str) -> tuple[Path, Path, dict[str, object]]:
        config = Path(directory) / "config"
        shutil.copytree(ROOT / "config" / "pilot", config / "pilot")
        path = config / "pilot" / "tri_security_batches.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        return config, path, payload

    def test_registry_has_three_ordered_batches_and_requested_first_batch(self) -> None:
        registry = load_tri_security_registry(ROOT / "config")
        report = registry.report()
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["batch_size"], 3)
        self.assertEqual(report["batch_count"], 3)
        self.assertEqual(report["security_count"], 9)
        first = registry.batch(FIRST_BATCH_ID)
        self.assertEqual(
            [(row.security_code, row.ticker, row.isin) for row in first.securities],
            [
                ("108", "KFH", "KW0EQ0100085"),
                ("506", "SHIP", "KW0EQ0500888"),
                ("826", "AZNOULA", "KW0EQ0504799"),
            ],
        )
        self.assertTrue(report["claim_boundaries"]["configuration_valid"])
        for claim, allowed in report["claim_boundaries"].items():
            if claim != "configuration_valid":
                self.assertFalse(allowed, claim)

    def test_committed_registry_matches_machine_readable_schema(self) -> None:
        payload = json.loads(
            (ROOT / "config" / "pilot" / "tri_security_batches.json").read_text(
                encoding="utf-8"
            )
        )
        _schema_validator("tri-security-pilot-registry.schema.json").validate(payload)
        mapping_payload = json.loads(
            (ROOT / "config" / "pilot" / "tri_security_vendor_mappings.json").read_text(
                encoding="utf-8"
            )
        )
        _schema_validator("tri-security-vendor-mappings.schema.json").validate(
            mapping_payload
        )
        registry = load_tri_security_registry(ROOT / "config")
        mappings = load_tri_security_vendor_mappings(ROOT / "config", registry)
        ship = next(mapping for mapping in mappings.mappings if mapping.ticker == "SHIP")
        self.assertEqual(ship.provider_symbol, "heavy-eng---ship")
        self.assertTrue(ship.provider_url.endswith("/heavy-eng---ship-historical-data"))

    def test_inactive_tri_security_vendor_mapping_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config, _, _ = self._mutable_config(directory)
            path = config / "pilot" / "tri_security_vendor_mappings.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["mappings"][0]["mapping_state"] = "RETIRED"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "inactive configured"):
                load_tri_security_vendor_mappings(
                    config,
                    load_tri_security_registry(config),
                )

    def test_every_batch_must_have_exactly_three_securities(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config, path, payload = self._mutable_config(directory)
            payload["batches"][0]["securities"].pop()
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "exactly 3"):
                load_tri_security_registry(config)

    def test_security_identity_must_be_unique_across_batches(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config, path, payload = self._mutable_config(directory)
            payload["batches"][1]["securities"][0] = copy.deepcopy(
                payload["batches"][0]["securities"][0]
            )
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate security_code"):
                load_tri_security_registry(config)

    def test_seed_cannot_self_promote_to_official_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config, path, payload = self._mutable_config(directory)
            payload["batches"][0]["securities"][0]["identity_state"] = (
                "VERIFIED_OFFICIAL"
            )
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "UNVERIFIED_SEED"):
                load_tri_security_registry(config)

    def test_execution_order_must_match_contiguous_sequence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config, path, payload = self._mutable_config(directory)
            payload["execution_order"] = list(reversed(payload["execution_order"]))
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "execution_order"):
                load_tri_security_registry(config)

    def test_strict_loader_rejects_duplicate_json_keys(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config, path, _ = self._mutable_config(directory)
            content = path.read_text(encoding="utf-8")
            path.write_text(
                content.replace(
                    '"schema_version": "1.0",',
                    '"schema_version": "1.0",\n  "schema_version": "1.0",',
                    1,
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "duplicate key"):
                load_tri_security_registry(config)

    def test_first_batch_workspace_is_portable_and_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "batch"
            report = prepare_tri_security_batch_workspace(
                config_dir=ROOT / "config",
                output_root=output,
                batch_id=FIRST_BATCH_ID,
                run_id="tri-run-001",
                window_from="2026-08-02",
                window_to="2026-08-12",
                prepared_by="unit-test",
            )
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(report["mode"], TRI_SECURITY_MODE)
            self.assertEqual(
                report["readiness_status"],
                "CONFIG_VALID_EXTERNAL_EVIDENCE_REQUIRED",
            )
            self.assertIsNone(report["predecessor_batch_id"])
            self.assertFalse(report["predecessor_qualification_required"])
            self.assertEqual(report["batch_size"], 3)
            self.assertEqual(len(set(report["gate_states"])), 1)
            self.assertEqual(report["gate_states"][0], "PENDING_EXTERNAL_EVIDENCE")
            self.assertTrue(all(not value for value in report["claim_boundaries"].values()))

            plan_path = output / report["batch_plan_path"]
            saved_report_path = output / "reports" / "tri_security_workspace_report.json"
            self.assertEqual(report["batch_plan_sha256"], sha256_file(plan_path))
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            saved_report = json.loads(saved_report_path.read_text(encoding="utf-8"))
            self.assertEqual(plan["batch_sha256"], hash_json(plan["batch"]))
            self.assertEqual(plan["qualification_window"]["window_from"], "2026-08-02")
            plan_validator = _schema_validator("tri-security-batch-plan.schema.json")
            plan_validator.validate(plan)
            forged_gates = copy.deepcopy(plan)
            forged_gates["gates"][11] = copy.deepcopy(forged_gates["gates"][0])
            with self.assertRaises(Exception):
                plan_validator.validate(forged_gates)
            forged_progression = copy.deepcopy(plan)
            forged_progression["execution"] = {
                "sequence": 3,
                "predecessor_batch_id": None,
                "predecessor_qualification_required": False,
            }
            with self.assertRaises(Exception):
                plan_validator.validate(forged_progression)
            _schema_validator("tri-security-workspace-report.schema.json").validate(
                saved_report
            )
            scoped_manifest = json.loads(
                (output / report["scoped_config_manifest_path"]).read_text(
                    encoding="utf-8"
                )
            )
            _schema_validator("tri-security-scoped-config-manifest.schema.json").validate(
                scoped_manifest
            )
            self.assertEqual(
                report["scoped_config_manifest_sha256"],
                sha256_file(output / report["scoped_config_manifest_path"]),
            )
            scoped_config = output / report["scoped_config_root"]
            scoped_verification = verify_tri_security_scoped_config(
                scoped_config,
                expected_manifest_sha256=report["scoped_config_manifest_sha256"],
            )
            self.assertEqual(scoped_verification["security_count"], 3)
            identities = PilotIdentitySeedCatalog(scoped_config)
            vendor_mappings = VendorSymbolMappingCatalog(scoped_config, identities)
            self.assertEqual(len(identities.identities), 3)
            self.assertEqual(
                {mapping.ticker for mapping in vendor_mappings.capture_candidates()},
                {"KFH", "SHIP", "AZNOULA"},
            )

            seed_path = scoped_config / "pilot" / "security_master_seed.json"
            seed_payload = json.loads(seed_path.read_text(encoding="utf-8"))
            seed_payload["securities"][0]["sector"] = "TAMPERED"
            seed_path.write_text(json.dumps(seed_payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                verify_tri_security_scoped_config(scoped_config)
            self.assertNotIn(str(output), json.dumps(saved_report, ensure_ascii=False))
            for security in report["securities"]:
                readme = (
                    output
                    / "evidence"
                    / f"{security['security_code']}-{security['ticker']}"
                    / "README.txt"
                )
                self.assertIn("UNVERIFIED_SEED", readme.read_text(encoding="utf-8"))

    def test_later_batch_is_locked_until_verified_progression_is_implemented(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "batch"
            with self.assertRaisesRegex(ValueError, "locked until"):
                prepare_tri_security_batch_workspace(
                    config_dir=ROOT / "config",
                    output_root=output,
                    batch_id="tri-002-nbk-mabanee-zain",
                    run_id="tri-run-002",
                    window_from="2026-08-02",
                    window_to="2026-08-12",
                )
            self.assertFalse(output.exists())

    def test_qualification_window_is_mandatory_and_bounded_by_as_of(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "exceeds the registry as_of"):
                prepare_tri_security_batch_workspace(
                    config_dir=ROOT / "config",
                    output_root=Path(directory) / "batch",
                    batch_id=FIRST_BATCH_ID,
                    run_id="tri-run-window",
                    window_from="2026-08-02",
                    window_to="2026-08-13",
                )

    def test_workspace_refuses_nonempty_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "batch"
            output.mkdir()
            (output / "preserve.txt").write_text("user data", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
                prepare_tri_security_batch_workspace(
                    config_dir=ROOT / "config",
                    output_root=output,
                    batch_id=FIRST_BATCH_ID,
                    run_id="tri-run-003",
                    window_from="2026-08-02",
                    window_to="2026-08-12",
                )
            self.assertEqual(
                (output / "preserve.txt").read_text(encoding="utf-8"),
                "user data",
            )

    @unittest.skipIf(os.name == "nt", "symlink privilege varies on Windows")
    def test_workspace_refuses_symlink_output_component(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            real = root / "real"
            real.mkdir()
            linked = root / "linked"
            linked.symlink_to(real, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symlink"):
                prepare_tri_security_batch_workspace(
                    config_dir=ROOT / "config",
                    output_root=linked / "batch",
                    batch_id=FIRST_BATCH_ID,
                    run_id="tri-run-004",
                    window_from="2026-08-02",
                    window_to="2026-08-12",
                )

    def test_cli_validates_and_prepares_first_batch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                validate_code = data_foundation_main(
                    [
                        "--project-root",
                        str(ROOT),
                        "validate-tri-security-pilot",
                    ]
                )
            self.assertEqual(validate_code, 0)
            self.assertEqual(json.loads(stdout.getvalue())["batch_count"], 3)

            stdout = io.StringIO()
            output = Path(directory) / "workspace"
            with redirect_stdout(stdout):
                prepare_code = data_foundation_main(
                    [
                        "--project-root",
                        str(ROOT),
                        "prepare-tri-security-batch",
                        "--output-root",
                        str(output),
                        "--batch-id",
                        FIRST_BATCH_ID,
                        "--run-id",
                        "cli-run-001",
                        "--window-from",
                        "2026-08-02",
                        "--window-to",
                        "2026-08-12",
                    ]
                )
            self.assertEqual(prepare_code, 0)
            cli_report = json.loads(stdout.getvalue())
            self.assertEqual(cli_report["batch_id"], FIRST_BATCH_ID)

            scoped_stdout = io.StringIO()
            with redirect_stdout(scoped_stdout):
                scoped_code = data_foundation_main(
                    [
                        "--project-root",
                        str(ROOT),
                        "--pilot-config-dir",
                        str(output / "scoped_config"),
                        "--expected-pilot-config-manifest-sha256",
                        cli_report["scoped_config_manifest_sha256"],
                        "validate-pilot-config",
                    ]
                )
            self.assertEqual(scoped_code, 0)
            self.assertEqual(
                json.loads(scoped_stdout.getvalue())["identity_seed"]["security_count"],
                3,
            )
            self.assertEqual(
                json.loads(scoped_stdout.getvalue())["scoped_configuration"]["status"],
                "PASS",
            )
            price_stdout = io.StringIO()
            with redirect_stdout(price_stdout):
                price_code = data_foundation_main(
                    [
                        "--project-root",
                        str(ROOT),
                        "--pilot-config-dir",
                        str(output / "scoped_config"),
                        "--expected-pilot-config-manifest-sha256",
                        cli_report["scoped_config_manifest_sha256"],
                        "prepare-price-collection",
                        "--output-root",
                        str(Path(directory) / "price-workspace"),
                        "--downloaded-by",
                        "unit-test",
                    ]
                )
            self.assertEqual(price_code, 0)
            price_report = json.loads(price_stdout.getvalue())
            self.assertEqual(price_report["status"], "PASS")
            self.assertEqual(price_report["symbol_count"], 3)
            with self.assertRaisesRegex(ValueError, "requires.*expected-pilot",):
                data_foundation_main(
                    [
                        "--project-root",
                        str(ROOT),
                        "--pilot-config-dir",
                        str(output / "scoped_config"),
                        "validate-pilot-config",
                    ]
                )

if __name__ == "__main__":
    unittest.main()
