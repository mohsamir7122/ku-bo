from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import shutil
import socket
import tempfile
import unittest
from unittest.mock import patch

from kubo.bootstrap_archive.bridge import (
    BRIDGE_STATUSES,
    load_historical_source_network_crosswalk,
)
from kubo.bootstrap_archive.contract import (
    ARCHIVE_SECTION_IDS,
    STAGE_IDS,
    STAGE_INITIAL_STATUSES,
    load_bootstrap_archive_contract,
)
from kubo.bootstrap_archive.workspace import build_bootstrap_archive_plan
from kubo.historical_knowledge import HistoricalKnowledgeCatalog
from kubo.source_network import SourceNetworkCatalog


ROOT = Path(__file__).resolve().parents[1]
AS_OF = date(2026, 8, 14)


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


class BootstrapArchiveContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.historical_catalog = HistoricalKnowledgeCatalog(ROOT / "config")
        self.network_catalog = SourceNetworkCatalog(ROOT / "config")

    def test_contract_freezes_sections_stage_order_dependencies_and_nonclaims(self) -> None:
        contract = load_bootstrap_archive_contract(
            ROOT / "config" / "bootstrap_archive.json"
        )
        contract.validate_against(self.historical_catalog)

        self.assertEqual(
            tuple(section.section_id for section in contract.sections),
            ARCHIVE_SECTION_IDS,
        )
        layer_memberships = [
            layer_id for section in contract.sections for layer_id in section.layer_ids
        ]
        self.assertEqual(len(layer_memberships), len(set(layer_memberships)))
        self.assertEqual(set(layer_memberships), {layer.layer_id for layer in self.historical_catalog.layers})
        self.assertEqual(
            tuple(stage.stage_id for stage in contract.stages),
            STAGE_IDS,
        )
        self.assertEqual(
            tuple(stage.order for stage in contract.stages),
            (1, 2, 3, 4),
        )
        self.assertEqual(
            tuple(stage.depends_on for stage in contract.stages),
            ((), ("BOOTSTRAP_ARCHIVE",), ("COMPANY_INTELLIGENCE",), ("SOURCE_WAVES",)),
        )
        self.assertEqual(
            tuple(stage.initial_status for stage in contract.stages),
            STAGE_INITIAL_STATUSES,
        )
        self.assertTrue(contract.claim_boundaries)
        self.assertTrue(all(value is False for value in contract.claim_boundaries.values()))
        self.assertEqual(contract.storage_policy["corpus_location"], "RUNTIME_UNTRACKED_ONLY")
        self.assertIs(contract.storage_policy["raw_content_committed_to_git"], False)
        self.assertIs(contract.storage_policy["no_overwrite"], True)
        self.assertIs(contract.storage_policy["atomic_publication_required"], True)

    def test_crosswalk_covers_every_historical_source_and_never_authorizes_collection(self) -> None:
        crosswalk = load_historical_source_network_crosswalk(
            ROOT / "config" / "historical_source_network_crosswalk.json"
        )
        crosswalk.validate_against(self.historical_catalog, self.network_catalog)
        report = crosswalk.report(self.historical_catalog, self.network_catalog)

        self.assertEqual(len(crosswalk.bindings), 28)
        self.assertEqual(
            {binding.historical_source_id for binding in crosswalk.bindings},
            {source.source_id for source in self.historical_catalog.sources},
        )
        self.assertEqual(report["historical_source_count"], 28)
        self.assertEqual(report["mapped_historical_source_count"], 21)
        self.assertEqual(
            report["bridge_status_counts"],
            {
                "DECLARED_MAPPING_ONLY": 10,
                "PARTIAL_DECLARED_MAPPING": 11,
                "UNMAPPED_DEFINED_ONLY": 7,
            },
        )
        self.assertEqual(set(report["bridge_status_counts"]), BRIDGE_STATUSES)
        self.assertIs(report["collection_allowed"], False)
        self.assertIs(report["live_operational"], False)
        self.assertTrue(
            all(binding.to_dict()["collection_allowed"] is False for binding in crosswalk.bindings)
        )

    def test_crosswalk_rejects_missing_unknown_and_collection_enabled_bindings(self) -> None:
        original = json.loads(
            (ROOT / "config" / "historical_source_network_crosswalk.json").read_text(
                encoding="utf-8"
            )
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            missing = json.loads(json.dumps(original))
            missing["bindings"].pop()
            missing_path = root / "missing.json"
            _write_json(missing_path, missing)
            with self.assertRaisesRegex(ValueError, "cover every source exactly"):
                load_historical_source_network_crosswalk(missing_path).validate_against(
                    self.historical_catalog,
                    self.network_catalog,
                )

            unknown = json.loads(json.dumps(original))
            unknown["bindings"][0]["network_source_ids"] = ["unknown_network_source"]
            unknown["bindings"][0]["bridge_status"] = "DECLARED_MAPPING_ONLY"
            unknown_path = root / "unknown.json"
            _write_json(unknown_path, unknown)
            with self.assertRaisesRegex(ValueError, "unknown network source"):
                load_historical_source_network_crosswalk(unknown_path).validate_against(
                    self.historical_catalog,
                    self.network_catalog,
                )

            enabled = json.loads(json.dumps(original))
            enabled["bindings"][0]["collection_allowed"] = True
            enabled_path = root / "enabled.json"
            _write_json(enabled_path, enabled)
            with self.assertRaisesRegex(ValueError, "cannot authorize collection"):
                load_historical_source_network_crosswalk(enabled_path)

            oversized = json.loads(json.dumps(original))
            oversized["bindings"][0]["semantic_limit"] = "x" * 2049
            oversized_path = root / "oversized.json"
            _write_json(oversized_path, oversized)
            with self.assertRaisesRegex(ValueError, "at most 2048"):
                load_historical_source_network_crosswalk(oversized_path)

            too_many_network_ids = json.loads(json.dumps(original))
            too_many_network_ids["bindings"][0]["network_source_ids"] = [
                "boursa_current",
                "boursa_reports_archive",
                "boursa_disclosure_archive",
                "cma_ifsah",
            ]
            too_many_path = root / "too-many-network-ids.json"
            _write_json(too_many_path, too_many_network_ids)
            with self.assertRaisesRegex(ValueError, "at most three"):
                load_historical_source_network_crosswalk(too_many_path)

            profile_drift = json.loads(json.dumps(original))
            profile_drift["bindings"][3]["bridge_status"] = "PARTIAL_DECLARED_MAPPING"
            profile_drift_path = root / "profile-drift.json"
            _write_json(profile_drift_path, profile_drift)
            with self.assertRaisesRegex(ValueError, "frozen schema 1.0 mapping profile"):
                load_historical_source_network_crosswalk(profile_drift_path).report(
                    self.historical_catalog,
                    self.network_catalog,
                )

            multiline = json.loads(json.dumps(original))
            multiline["bindings"][0]["semantic_limit"] = "line one\nline two"
            multiline_path = root / "multiline.json"
            _write_json(multiline_path, multiline)
            with self.assertRaisesRegex(ValueError, "trimmed semantic limit"):
                load_historical_source_network_crosswalk(multiline_path)

    def test_contract_rejects_stage_reordering_and_readiness_claims(self) -> None:
        original = json.loads(
            (ROOT / "config" / "bootstrap_archive.json").read_text(encoding="utf-8")
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            reordered = json.loads(json.dumps(original))
            reordered["stages"][1]["order"] = 3
            reordered_path = root / "reordered.json"
            _write_json(reordered_path, reordered)
            with self.assertRaisesRegex(ValueError, "consecutively ordered"):
                load_bootstrap_archive_contract(reordered_path)

            ready = json.loads(json.dumps(original))
            ready["claim_boundaries"]["company_intelligence_ready"] = True
            ready_path = root / "ready.json"
            _write_json(ready_path, ready)
            with self.assertRaisesRegex(ValueError, "claims must remain false"):
                load_bootstrap_archive_contract(ready_path)

    def test_contract_rejects_duplicate_layer_membership(self) -> None:
        original = json.loads(
            (ROOT / "config" / "bootstrap_archive.json").read_text(encoding="utf-8")
        )
        original["archive_sections"][2]["layer_ids"].append(
            "COMPANY_MEDIA_HISTORY_1980_PRESENT"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate-layer.json"
            _write_json(path, original)
            with self.assertRaisesRegex(ValueError, "section-layer mapping"):
                load_bootstrap_archive_contract(path)

    def test_contract_rejects_swapped_section_semantics(self) -> None:
        original = json.loads(
            (ROOT / "config" / "bootstrap_archive.json").read_text(encoding="utf-8")
        )
        original["archive_sections"][0]["layer_ids"], original["archive_sections"][3][
            "layer_ids"
        ] = (
            original["archive_sections"][3]["layer_ids"],
            original["archive_sections"][0]["layer_ids"],
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "swapped-sections.json"
            _write_json(path, original)
            with self.assertRaisesRegex(ValueError, "section-layer mapping"):
                load_bootstrap_archive_contract(path)


class BootstrapArchivePlanTests(unittest.TestCase):
    def test_plan_is_deterministic_offline_and_content_addressed(self) -> None:
        with patch.object(
            socket,
            "create_connection",
            side_effect=AssertionError("bootstrap planning must not access the network"),
        ):
            first = build_bootstrap_archive_plan(config_root=ROOT / "config", as_of=AS_OF)
            second = build_bootstrap_archive_plan(config_root=ROOT / "config", as_of=AS_OF)

        self.assertEqual(first, second)
        self.assertRegex(first["archive_id"], r"^bootstrap-[0-9a-f]{24}$")
        self.assertEqual(first["status"], "SCAFFOLD_PLANNED_NOT_EXECUTED")
        self.assertEqual(first["decision_use"], "CONTEXT_ONLY")
        self.assertEqual(
            first["counts"],
            {
                "historical_source_count": 28,
                "historical_layer_count": 6,
                "historical_task_count": 756,
                "historical_evidence_artifact_count": 0,
                "company_count": 0,
                "event_count": 0,
            },
        )
        self.assertEqual(first["collection_gate"]["status"], "BLOCKED")
        self.assertEqual(first["company_intelligence_gate"]["status"], "BLOCKED")
        self.assertTrue(all(value is False for value in first["claim_boundaries"].values()))
        self.assertTrue(
            all(row["status"] == expected for row, expected in zip(first["stages"], STAGE_INITIAL_STATUSES, strict=True))
        )

    def test_archive_id_changes_when_a_frozen_control_input_changes(self) -> None:
        baseline = build_bootstrap_archive_plan(config_root=ROOT / "config", as_of=AS_OF)
        with tempfile.TemporaryDirectory() as directory:
            config_root = Path(directory) / "config"
            shutil.copytree(ROOT / "config", config_root)
            crosswalk_path = config_root / "historical_source_network_crosswalk.json"
            payload = json.loads(crosswalk_path.read_text(encoding="utf-8"))
            payload["bindings"][0]["semantic_limit"] += " Frozen-input mutation."
            _write_json(crosswalk_path, payload)

            changed = build_bootstrap_archive_plan(config_root=config_root, as_of=AS_OF)

        self.assertNotEqual(changed["archive_id"], baseline["archive_id"])
        baseline_hashes = {row["role"]: row["sha256"] for row in baseline["control_inputs"]}
        changed_hashes = {row["role"]: row["sha256"] for row in changed["control_inputs"]}
        self.assertNotEqual(
            changed_hashes["DECLARED_SOURCE_CROSSWALK"],
            baseline_hashes["DECLARED_SOURCE_CROSSWALK"],
        )


if __name__ == "__main__":
    unittest.main()
