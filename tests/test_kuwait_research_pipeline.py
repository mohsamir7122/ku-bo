from __future__ import annotations

from contextlib import redirect_stdout
from datetime import datetime
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover
    Draft202012Validator = None  # type: ignore[assignment,misc]

from kubo.context_research import context_event_from_dict, deduplicate_context_events
from kubo.cli_v3 import main
from kubo.hashing import sha256_bytes
from kubo.ingestion import CaptureResult
from kubo.kuwait_research_pipeline import (
    build_integrated_research_bundle,
    load_parsed_research_inputs,
)
from kubo.source_network import SourceNetworkCatalog
from kubo.source_orchestrator import SourceSearchOrchestrator


ROOT = Path(__file__).resolve().parents[1]
DECISION = datetime.fromisoformat("2026-08-13T12:00:00+03:00")


class _QualifiedConnector:
    def capture(self, request):
        content = json.dumps(
            {"event": "fixture-contract", "source_id": request.source_id},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return CaptureResult(
            source_id=request.source_id,
            source_url=request.source_url,
            final_url=request.source_url,
            access_mode=request.access_mode,
            capture_kind=request.capture_kind,
            roles_observed=request.roles_observed,
            attempted_at=DECISION,
            observed_at=DECISION,
            state="AVAILABLE",
            query_status="QUALIFIED",
            qualified_items=1,
            zero_result=False,
            content=content,
            content_type="application/json",
            http_status=200,
            error_code="",
            data_quality_flags=(),
            limitations=("GENERATED_CONTRACT_FIXTURE",),
        )


class _RawPendingParserConnector(_QualifiedConnector):
    def capture(self, request):
        result = super().capture(request)
        return CaptureResult(
            source_id=result.source_id,
            source_url=result.source_url,
            final_url=result.final_url,
            access_mode=result.access_mode,
            capture_kind=result.capture_kind,
            roles_observed=result.roles_observed,
            attempted_at=result.attempted_at,
            observed_at=result.observed_at,
            state="AVAILABLE",
            query_status="DATA_QUALITY_REJECTED",
            qualified_items=0,
            zero_result=False,
            content=result.content,
            content_type=result.content_type,
            http_status=result.http_status,
            error_code="RAW_CAPTURE_PENDING_PARSER_VALIDATION",
            data_quality_flags=(),
            limitations=("RAW_CAPTURE_PENDING_PARSER_VALIDATION",),
        )


def _raw_event(digest: str) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "event_id": "event-1",
        "scope": "SECURITY",
        "scope_key": "101",
        "event_type": "CONTRACT_AWARD",
        "direction": "POSITIVE",
        "materiality": 0.8,
        "confidence": 0.7,
        "novelty": 0.9,
        "event_at": "2026-08-13T09:00:00+03:00",
        "published_at": "2026-08-13T09:00:00+03:00",
        "first_available_at": "2026-08-13T09:00:00+03:00",
        "captured_at": "2026-08-13T12:00:00+03:00",
        "decision_at": DECISION.isoformat(),
        "capture_mode": "RECORDED_FIXTURE",
        "source_id": "boursa_current",
        "source_group_id": "boursa_kuwait",
        "source_class": "OFFICIAL",
        "origin_id": "origin-1",
        "origin_hash": digest,
        "content_hash": digest,
        "evidence_hashes": [digest],
        "availability_evidence_hashes": [digest],
        "relation_type": "STANDALONE",
        "original_event_id": None,
        "factual_status": "OFFICIAL_CONFIRMED",
        "contradiction_status": "UNCONTESTED",
        "correction_status": "CURRENT",
        "summary": "Generated integration-contract event",
    }


def _parsed_payload(digest: str) -> dict[str, object]:
    event = _raw_event(digest)
    canonical = deduplicate_context_events(
        [context_event_from_dict(event, manifest_hashes=frozenset({digest}))]
    )[0]
    factor = lambda value: {  # noqa: E731
        "status": "OBSERVED",
        "value": value,
        "available_at": "2026-08-13T10:00:00+03:00",
        "evidence_hashes": [digest],
        "reason_codes": [],
    }
    return {
        "schema_version": "1.0",
        "decision_id": "decision-integration-1",
        "decision_at": DECISION.isoformat(),
        "universe_as_of": "2026-08-13T08:00:00+03:00",
        "expected_security_codes": ["101"],
        "manifest_hashes": [digest],
        "context_events": [event],
        "security_exposures": [
            {
                "schema_version": "1.0",
                "exposure_id": "exp-" + "1" * 24,
                "canonical_event_id": canonical["canonical_event_id"],
                "security_code": "101",
                "exposure_type": "DIRECT_NAMED",
                "sector_code": None,
                "direction": "POSITIVE",
                "confidence": 0.7,
                "materiality": 0.8,
                "available_at": "2026-08-13T09:00:00+03:00",
                "decision_at": DECISION.isoformat(),
                "confirmation_class": "OFFICIAL_EVIDENCE",
                "contradiction_status": "UNCONTESTED",
                "factor_eligible": True,
                "evidence_hashes": [digest],
                "reason_codes": [],
            }
        ],
        "factor_inputs_by_security": {
            "101": {
                "price_momentum_5d": factor(0.2),
                "liquidity_activity_20d": factor(1.1),
                "security_trading_status": factor("TRADING"),
            }
        },
        "dispositions_by_security": {
            "101": {
                "disposition": "SELECTED",
                "first_failed_stage": None,
                "reason_codes": [],
                "score": 0.4,
                "score_kind": "UNVALIDATED_RESEARCH_SCORE",
            }
        },
        "claim_boundaries": {
            "parser_output_is_raw_capture": False,
            "score_is_probability": False,
            "recommendation_allowed": False,
        },
    }


class KuwaitResearchPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = SourceNetworkCatalog(ROOT / "config")

    def _source_run(
        self,
        root: Path,
        *,
        connector=None,
        source_ids: list[str] | None = None,
    ) -> tuple[Path, dict[str, str]]:
        source_root = root / "source-run"
        source_root.mkdir()
        run = SourceSearchOrchestrator(
            catalog=SourceNetworkCatalog(ROOT / "config"),
            strategy_path=ROOT / "config" / "source_query_strategies.json",
            connector=connector or _QualifiedConnector(),
            clock=lambda: DECISION,
            sleeper=lambda _seconds: None,
        ).run(
            run_id="integration-source-run",
            decision_at=DECISION,
            attempt_log_path=source_root / "source_attempts.jsonl",
            source_ids=source_ids or ["boursa_current"],
        )
        (source_root / "source_search_run.json").write_bytes(
            (json.dumps(run.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
        )
        digests = {
            source_id: sha256_bytes(next((source_root / "raw" / source_id).iterdir()).read_bytes())
            for source_id in (source_ids or ["boursa_current"])
        }
        return source_root, digests

    def _integrable_source_run(self, root: Path, *, connector=None) -> tuple[Path, dict[str, str]]:
        return self._source_run(
            root,
            connector=connector,
            source_ids=["boursa_current", "investing_history"],
        )

    @staticmethod
    def _integrable_payload(digests: dict[str, str]) -> dict[str, object]:
        payload = _parsed_payload(digests["boursa_current"])
        payload["manifest_hashes"].append(digests["investing_history"])
        for factor_id in ("price_momentum_5d", "liquidity_activity_20d"):
            payload["factor_inputs_by_security"]["101"][factor_id]["evidence_hashes"] = [
                digests["investing_history"]
            ]
        return payload

    def test_bridge_verifies_source_bytes_and_materializes_all_layers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_root, digests = self._integrable_source_run(root)
            payload = self._integrable_payload(digests)
            inputs = root / "parsed.json"
            inputs.write_text(json.dumps(payload), encoding="utf-8")
            output = root / "integrated"
            report = build_integrated_research_bundle(
                source_search_root=source_root,
                parsed_inputs_path=inputs,
                output_root=output,
                source_catalog=self.catalog,
                schema_root=ROOT / "schemas",
            )
            self.assertEqual(report["status"], "CONTRACT_INTEGRATED")
            self.assertEqual(report["verified_raw_artifact_count"], 2)
            self.assertTrue((output / "context_events.json").is_file())
            self.assertTrue((output / "security_exposures.json").is_file())
            snapshot = json.loads((output / "factor_snapshot.json").read_text())
            self.assertIsNone(snapshot["rows"][0]["probability"])
            self.assertFalse(report["claim_boundaries"]["forecast_generated"])

    def test_unverified_hash_fails_before_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_root, digests = self._integrable_source_run(root)
            payload = self._integrable_payload(digests)
            payload["manifest_hashes"] = ["f" * 64]
            inputs = root / "parsed.json"
            inputs.write_text(json.dumps(payload), encoding="utf-8")
            output = root / "integrated"
            with self.assertRaisesRegex(ValueError, "outside the verified"):
                build_integrated_research_bundle(
                    source_search_root=source_root,
                    parsed_inputs_path=inputs,
                    output_root=output,
                    source_catalog=self.catalog,
                    schema_root=ROOT / "schemas",
                )
            self.assertFalse(output.exists())

    def test_verified_raw_pending_parser_can_continue_with_visible_limitations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_root, digests = self._integrable_source_run(
                root,
                connector=_RawPendingParserConnector(),
            )
            payload = self._integrable_payload(digests)
            inputs = root / "parsed.json"
            inputs.write_text(json.dumps(payload), encoding="utf-8")
            report = build_integrated_research_bundle(
                source_search_root=source_root,
                parsed_inputs_path=inputs,
                output_root=root / "integrated",
                source_catalog=self.catalog,
                schema_root=ROOT / "schemas",
            )
        self.assertEqual(
            report["status"],
            "CONTRACT_INTEGRATED_WITH_SOURCE_LIMITATIONS",
        )
        self.assertEqual(report["source_search_status"], "DEGRADED")
        self.assertFalse(report["claim_boundaries"]["contract_integration_is_live_operational"])

    def test_input_contract_rejects_weakened_claims(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "parsed.json"
            payload = _parsed_payload("a" * 64)
            payload["claim_boundaries"]["recommendation_allowed"] = True
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "claim boundaries"):
                load_parsed_research_inputs(path)

    def test_cli_dispatches_the_verified_integration_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "integrated"
            with patch(
                "kubo.cli_v3.build_integrated_research_bundle",
                return_value={"status": "CONTRACT_INTEGRATED"},
            ) as builder:
                with redirect_stdout(io.StringIO()):
                    code = main(
                        [
                            "--project-root",
                            str(ROOT),
                            "build-kuwait-research-bundle",
                            "--source-search-root",
                            str(root / "source"),
                            "--parsed-inputs",
                            str(root / "parsed.json"),
                            "--output-root",
                            str(output),
                        ]
                    )
        self.assertEqual(code, 0)
        builder.assert_called_once_with(
            source_search_root=root / "source",
            parsed_inputs_path=root / "parsed.json",
            output_root=output,
            source_catalog=unittest.mock.ANY,
            schema_root=ROOT / "schemas",
        )

    def test_bridge_rejects_context_and_exposure_cutoff_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_root, digests = self._integrable_source_run(root)
            for field in ("context_events", "security_exposures"):
                payload = self._integrable_payload(digests)
                payload[field][0]["decision_at"] = "2026-08-14T12:00:00+03:00"
                inputs = root / f"parsed-{field}.json"
                inputs.write_text(json.dumps(payload), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "different decision cutoffs"):
                    build_integrated_research_bundle(
                        source_search_root=source_root,
                        parsed_inputs_path=inputs,
                        output_root=root / f"integrated-{field}",
                        source_catalog=self.catalog,
                        schema_root=ROOT / "schemas",
                    )

    def test_bridge_rejects_forged_source_group_class_and_evidence_owner(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_root, digests = self._integrable_source_run(root)
            mutations = (
                ("source_group_id", "forged-independent-publisher", "source_group_id"),
                ("source_class", "COMMUNITY", "source_class"),
                ("source_id", "kuna", "source_id"),
            )
            for field, value, error in mutations:
                payload = self._integrable_payload(digests)
                payload["context_events"][0][field] = value
                inputs = root / f"parsed-{field}.json"
                inputs.write_text(json.dumps(payload), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, error):
                    build_integrated_research_bundle(
                        source_search_root=source_root,
                        parsed_inputs_path=inputs,
                        output_root=root / f"integrated-{field}",
                        source_catalog=self.catalog,
                        schema_root=ROOT / "schemas",
                    )

            second_root = root / "two-source"
            second_root.mkdir()
            source_root, digests = self._source_run(
                second_root,
                source_ids=["boursa_current", "kuna"],
            )
            kuna_digest = digests["kuna"]
            payload = _parsed_payload(kuna_digest)
            inputs = root / "parsed-wrong-owner.json"
            inputs.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "not owned"):
                build_integrated_research_bundle(
                    source_search_root=source_root,
                    parsed_inputs_path=inputs,
                    output_root=root / "integrated-wrong-owner",
                    source_catalog=self.catalog,
                    schema_root=ROOT / "schemas",
                )

            boursa_digest = digests["boursa_current"]
            payload = _parsed_payload(boursa_digest)
            payload["manifest_hashes"].append(kuna_digest)
            payload["context_events"][0]["content_hash"] = kuna_digest
            inputs = root / "parsed-wrong-content-owner.json"
            inputs.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "not owned"):
                build_integrated_research_bundle(
                    source_search_root=source_root,
                    parsed_inputs_path=inputs,
                    output_root=root / "integrated-wrong-content-owner",
                    source_catalog=self.catalog,
                    schema_root=ROOT / "schemas",
                )

    def test_community_capture_cannot_supply_price_liquidity_or_status_factors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_root = root / "source-run"
            source_root.mkdir()
            run = SourceSearchOrchestrator(
                catalog=self.catalog,
                strategy_path=ROOT / "config" / "source_query_strategies.json",
                connector=_QualifiedConnector(),
                clock=lambda: DECISION,
                sleeper=lambda _seconds: None,
            ).run(
                run_id="community-only-run",
                decision_at=DECISION,
                attempt_log_path=source_root / "source_attempts.jsonl",
                source_ids=["telegram_boursakw"],
            )
            (source_root / "source_search_run.json").write_bytes(
                (json.dumps(run.to_dict(), sort_keys=True, separators=(",", ":")) + "\n").encode()
            )
            raw_file = next((source_root / "raw" / "telegram_boursakw").iterdir())
            digest = sha256_bytes(raw_file.read_bytes())
            payload = _parsed_payload(digest)
            payload["context_events"] = []
            payload["security_exposures"] = []
            inputs = root / "parsed.json"
            inputs.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "eligible role"):
                build_integrated_research_bundle(
                    source_search_root=source_root,
                    parsed_inputs_path=inputs,
                    output_root=root / "integrated",
                    source_catalog=self.catalog,
                    schema_root=ROOT / "schemas",
                )

    @unittest.skipIf(Draft202012Validator is None, "jsonschema is optional")
    def test_parsed_input_schema_accepts_the_runtime_fixture(self) -> None:
        schema = json.loads((ROOT / "schemas/parsed-research-inputs.schema.json").read_text())
        Draft202012Validator.check_schema(schema)
        # security-exposure is a relative reference; the global schema-registry
        # suite performs the cross-file validation.
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")


if __name__ == "__main__":
    unittest.main()
