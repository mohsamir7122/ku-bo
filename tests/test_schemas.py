from __future__ import annotations

import copy
import json
from pathlib import Path
import re
import unittest

from jsonschema import Draft202012Validator, ValidationError
from referencing import Registry, Resource


ROOT = Path(__file__).resolve().parents[1]


def _load_schema(name: str) -> dict[str, object]:
    return json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))


def _schema_validator(name: str):
    schemas = [_load_schema(path.name) for path in (ROOT / "schemas").glob("*.schema.json")]
    registry = Registry().with_resources(
        [
            (schema["$id"], Resource.from_contents(schema))
            for schema in schemas
            if "$id" in schema
        ]
    )
    schema = _load_schema(name)
    return Draft202012Validator(
        schema,
        registry=registry,
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    )


def _official_upstream() -> dict[str, object]:
    digest = "0" * 64
    return {
        "official_foundation": {
            "status": "CURRENT_IDENTITY_AND_CALENDAR_READY",
            "run_id": "official-run",
            "report_sha256": digest,
            "manifest_sha256": digest,
            "security_master_sha256": digest,
            "trading_calendar_sha256": digest,
            "calendar_window_from": "2026-08-09",
            "calendar_window_to": "2026-08-09",
            "identity_snapshot_effective_date": "2026-08-09",
        },
        "status_history": {
            "status": "HISTORICAL_STATUS_INTERVALS_READY",
            "run_id": "status-run",
            "report_sha256": digest,
            "manifest_sha256": digest,
            "status_intervals_sha256": digest,
            "status_query_ledger_sha256": digest,
            "history_window_from": "2026-08-09",
            "history_window_to": "2026-08-09",
        },
    }


def _official_provider(
    *,
    evidence: str = "RECORDED_AUTHORIZED_FIXTURE",
    rights: str = "FIXTURE_ONLY",
) -> dict[str, object]:
    return {
        "provider_id": "fixture-provider",
        "source_id": "official-eod-fixture",
        "source_url": "https://example.test/eod.csv",
        "source_class": "OFFICIAL",
        "capture_mode": "RECORDED_AUTHORIZED_FIXTURE",
        "availability_status": "AVAILABLE",
        "artifact_path": "raw/providers/eod.csv",
        "artifact_sha256": "1" * 64,
        "observed_at": "2026-08-09T13:00:00+03:00",
        "supplied_fields": ["TRADING_STATE", "OHLC", "VOLUME"],
        "field_origin": "OFFICIAL_SOURCE_FIELDS",
        "price_basis": "RAW_UNADJUSTED",
        "evidence_classification": evidence,
        "rights_status": rights,
        "pages_declared": 1,
        "pages_received": 1,
        "result_count_declared": 1,
        "rows_normalized": 1,
        "zero_result": False,
        "complete": True,
        "runtime_trust": None,
    }


def _market_totals_unavailable() -> dict[str, object]:
    return {
        "provider_id": None,
        "source_id": None,
        "source_url": None,
        "source_class": "OFFICIAL",
        "capture_mode": "",
        "availability_status": "NOT_AVAILABLE_FROM_SOURCE",
        "scope": "DECLARED_PILOT",
        "board": "cash",
        "artifact_path": None,
        "artifact_sha256": None,
        "observed_at": None,
        "evidence_classification": "LIVE_DEPENDENT",
        "rights_status": "UNKNOWN",
        "pages_declared": None,
        "pages_received": None,
        "result_count_declared": None,
        "rows_normalized": None,
        "zero_result": False,
        "complete": False,
        "runtime_trust": None,
    }


def _official_validation_report() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "validation_status": "PASS",
        "status": "PARTIAL",
        "denominator_status": "PASS",
        "price_evidence_status": "PASS",
        "market_totals_status": "NOT_AVAILABLE_FROM_SOURCE",
        "query_and_pagination_status": "PASS",
        "expected_pair_count": 1,
        "normalized_row_count": 1,
        "missing_pair_count": 0,
        "evidence_classification": "RECORDED_AUTHORIZED_FIXTURE",
        "rights_status": "FIXTURE_ONLY",
        "upstream": _official_upstream(),
        "providers": [_official_provider()],
        "market_totals_receipt": _market_totals_unavailable(),
        "security_codes": ["101"],
        "official_session_count": 1,
        "quarantine_count": 0,
        "errors": [],
        "warnings": [],
        "claim_boundaries": {
            "saved_report_was_trusted_without_recomputation": False,
            "raw_artifacts_rehashed": True,
            "normalized_outputs_recomputed": True,
            "upstream_receipts_rehashed": True,
            "data_foundation_ready": False,
            "backtest_ready": False,
        },
    }


def _official_import_report() -> dict[str, object]:
    report = _official_validation_report()
    report.pop("validation_status")
    report.update(
        {
            "run_id": "eod-run",
            "imported_at": "2026-08-10T10:00:00+03:00",
            "output_root": "eod-output",
            "window_from": "2026-08-09",
            "window_to": "2026-08-09",
            "official_daily_eod": {
                "path": "normalized/official_daily_eod.csv",
                "sha256": "2" * 64,
                "rows": 1,
            },
            "daily_market_totals": None,
            "quarantine": None,
            "official_eod_manifest_sha256": "3" * 64,
        }
    )
    report["claim_boundaries"] = {
        "recorded_fixture_is_real_evidence": False,
        "synthetic_fixture_promotes_readiness": False,
        "research_price_history_is_official_eod": False,
        "current_snapshot_backfills_history": False,
        "official_complete_eod_ready": False,
        "data_foundation_ready": False,
        "backtest_ready": False,
        "forecast_generated": False,
        "recommendation_generated": False,
    }
    return report


def _promote_official_eod_ready(report: dict[str, object]) -> dict[str, object]:
    promoted = copy.deepcopy(report)
    promoted["status"] = "OFFICIAL_COMPLETE_EOD_READY"
    promoted["denominator_status"] = "PASS"
    promoted["price_evidence_status"] = "PASS"
    promoted["market_totals_status"] = "NOT_AVAILABLE_FROM_SOURCE"
    promoted["query_and_pagination_status"] = "PASS"
    promoted["missing_pair_count"] = 0
    promoted["quarantine_count"] = 0
    promoted["evidence_classification"] = "PROVEN_REAL_EVIDENCE"
    promoted["rights_status"] = "RESEARCH_USE_AUTHORIZED"
    promoted["errors"] = []
    provider = promoted["providers"][0]
    provider["capture_mode"] = "PUBLIC_OFFICIAL_DOWNLOAD"
    provider["evidence_classification"] = "PROVEN_REAL_EVIDENCE"
    provider["rights_status"] = "RESEARCH_USE_AUTHORIZED"
    provider["availability_status"] = "AVAILABLE"
    provider["complete"] = True
    promoted["claim_boundaries"][
        "artifact_bound_capture_authority_verified"
    ] = True
    if "official_complete_eod_ready" in promoted["claim_boundaries"]:
        promoted["claim_boundaries"]["official_complete_eod_ready"] = True
    return promoted


GATE_NAMES = (
    "POINT_IN_TIME_IDENTITY",
    "TRADING_CALENDAR",
    "SECURITY_STATUS_HISTORY",
    "PRICE_DENOMINATOR",
    "PRICE_EVIDENCE",
    "PRICE_CORPORATE_ACTION_QA",
    "BENCHMARK_HISTORY",
    "BENCHMARK_EVIDENCE",
    "MARKET_TOTAL_RECONCILIATION",
    "QUERY_AND_PAGINATION_COMPLETENESS",
    "RUNTIME_SECRET_GUARD",
    "CLAIM_BOUNDARIES",
)


def _data_foundation_gate_report() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "status": "DATA_FOUNDATION_READY_FOR_BASELINE_BACKTEST",
        "evidence_classification": "PROVEN_REAL_EVIDENCE",
        "rights_compatible": True,
        "gates": [
            {
                "gate": name,
                "critical": True,
                "status": "PASS",
                "evidence_classification": "PROVEN_REAL_EVIDENCE",
                "rights_compatible": True,
                "errors": [],
                "hashes": [],
                "details": {
                    "components": [],
                    "checks": {"contract": "PASS"},
                    "metrics": {},
                    "concepts": [],
                },
            }
            for name in GATE_NAMES
        ],
        "claim_boundaries": [],
    }


COMPONENT_NAMES = (
    "OFFICIAL_FOUNDATION",
    "STATUS_HISTORY",
    "CA_ENRICHMENT",
    "RESEARCH_PRICE_HISTORY",
    "BENCHMARK",
    "OFFICIAL_EOD",
)


def _data_foundation_packet() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "status": "DATA_FOUNDATION_READY_FOR_BASELINE_BACKTEST",
        "evidence_classification": "PROVEN_REAL_EVIDENCE",
        "rights_compatible": True,
        "outcome_session_policy_status": "FROZEN",
        "components": [
            {
                "component": name,
                "evidence_classification": "PROVEN_REAL_EVIDENCE",
                "rights_compatible": True,
                "rights_statuses": ["RESEARCH_USE_AUTHORIZED"],
                "structural_errors": [],
                "limitations": [],
                "file_hashes": [],
            }
            for name in COMPONENT_NAMES
        ],
        "claim_boundaries": [],
    }


def _benchmark_report() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "status": "BENCHMARK_HISTORY_READY",
        "contract_status": "PASS",
        "run_id": "benchmark-run",
        "imported_at": "2026-08-10T10:00:00+03:00",
        "output_root": "benchmark-output",
        "window_from": "2026-08-09",
        "window_to": "2026-08-09",
        "registry_id": "benchmark-registry",
        "registry_sha256": "4" * 64,
        "registry_date_basis": "KU_BO_REGISTRY_OBSERVATION_NOT_PROVIDER_LAUNCH_OR_SERIES_INCEPTION",
        "upstream_calendar_receipt": "upstream_calendar_receipt.json",
        "normalized_benchmark_history": "normalized/benchmark_history.csv",
        "evidence_manifest": "manifest.json",
        "benchmark_count": 1,
        "available_benchmark_count": 1,
        "row_count": 1,
        "query_and_pagination_status": "PASS",
        "evidence_classification": "PROVEN_REAL_EVIDENCE",
        "benchmark_entries": [
            {
                "benchmark_code": "KU_BO_BROAD_PRICE",
                "availability_status": "AVAILABLE",
                "validation_status": "PASS",
                "row_count": 1,
                "expected_trading_dates": 1,
                "missing_trading_dates": [],
                "extra_trading_dates": [],
                "pages_declared": 1,
                "pages_received": 1,
                "result_count_declared": 1,
                "evidence_classification": "PROVEN_REAL_EVIDENCE",
                "rights_status": "RESEARCH_USE_AUTHORIZED",
                "errors": [],
            }
        ],
        "comparisons": {
            "series": [
                {
                    "benchmark_code": "KU_BO_BROAD_PRICE",
                    "role_key": "BROAD_MARKET:PRICE_INDEX:DAILY_CLOSE",
                    "market_scope": "BROAD_MARKET",
                    "sector": "",
                    "calculation_basis": "PRICE_INDEX",
                    "frequency": "DAILY_CLOSE",
                    "contract_comparison_possible": True,
                    "real_evidence_comparison_possible": True,
                    "evidence_classification": "PROVEN_REAL_EVIDENCE",
                    "no_substitution_used": True,
                }
            ],
            "product_rules": [
                {
                    "benchmark_rule": "point_in_time_market",
                    "comparison_kind": "DAILY_PRICE_RETURN_COMPARISON",
                    "required_roles": ["BROAD_MARKET:PRICE_INDEX:DAILY_CLOSE"],
                    "contract_comparison_possible": True,
                    "real_evidence_comparison_possible": True,
                    "status": "READY",
                }
            ],
        },
        "errors": [],
        "remaining_gates": ["FINAL_DATA_FOUNDATION_RECONCILIATION"],
        "claim_boundaries": {
            "benchmark_history_ready_for_declared_window": True,
            "price_index_used_as_total_return_index": False,
            "broad_market_used_as_sector_benchmark": False,
            "fallback_benchmark_substitution_used": False,
            "forward_fill_used": False,
            "synthetic_benchmark_rows_created": False,
            "internal_code_is_official_provider_code": False,
            "registry_effective_from_is_series_inception": False,
            "licensed_manifest_claim_is_external_authenticated_trust": False,
            "artifact_bound_capture_authority_verified": True,
            "recorded_fixture_is_real_evidence": False,
            "synthetic_fixture_is_real_evidence": False,
            "data_foundation_ready": False,
            "backtest_ready": False,
            "forecast_generated": False,
            "recommendation_generated": False,
        },
    }


class SchemaTests(unittest.TestCase):
    def test_all_schemas_are_json_schema_2020_12(self) -> None:
        paths = sorted((ROOT / "schemas").glob("*.schema.json"))
        self.assertGreaterEqual(len(paths), 2)
        for path in paths:
            with self.subTest(path=path.name):
                value = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(value["$schema"], "https://json-schema.org/draft/2020-12/schema")
                self.assertEqual(value["type"], "object")
                self.assertFalse(value["additionalProperties"])

    def test_analysis_request_schema_matches_runtime_vocabularies(self) -> None:
        from kubo.request_contracts import (
            CLAIM_TYPES,
            DETAIL_LEVELS,
            LANGUAGES,
            OUTPUT_FORMATS,
            REQUEST_MODES,
            REQUEST_SCOPES,
        )

        value = json.loads((ROOT / "schemas" / "analysis-request.schema.json").read_text(encoding="utf-8"))
        properties = value["properties"]
        self.assertEqual(set(properties["mode"]["enum"]), set(REQUEST_MODES))
        self.assertEqual(set(properties["scope"]["enum"]), set(REQUEST_SCOPES))
        self.assertEqual(set(properties["claim_type"]["enum"]), set(CLAIM_TYPES))
        self.assertEqual(set(properties["output_format"]["enum"]), set(OUTPUT_FORMATS))
        self.assertEqual(set(properties["detail_level"]["enum"]), set(DETAIL_LEVELS))
        self.assertEqual(set(properties["language"]["enum"]), set(LANGUAGES))

    def test_analysis_request_schema_exposes_runtime_scope_and_claim_guards(self) -> None:
        value = json.loads(
            (ROOT / "schemas" / "analysis-request.schema.json").read_text(
                encoding="utf-8"
            )
        )
        named_scope = next(
            clause
            for clause in value["allOf"]
            if clause.get("if", {}).get("properties", {}).get("scope", {}).get("const")
            == "NAMED_SECURITIES"
        )
        self.assertIn("security_codes", named_scope["then"]["required"])
        self.assertEqual(
            named_scope["then"]["properties"]["security_codes"]["minItems"],
            1,
        )

        research_fields = next(
            clause
            for clause in value["allOf"]
            if "requested_fields" in clause.get("then", {}).get("properties", {})
        )
        forbidden_pattern = research_fields["then"]["properties"]["requested_fields"][
            "items"
        ]["not"]["pattern"]
        for field in (
            "buy_recommendation",
            "Probability",
            "entryPrice",
            "سعر_الدخول",
        ):
            with self.subTest(field=field):
                self.assertIsNotNone(re.search(forbidden_pattern, field))
        for field in ("research_score", "evidence_coverage"):
            with self.subTest(field=field):
                self.assertIsNone(re.search(forbidden_pattern, field))
        self.assertIn("normalization", value["$comment"])

    def test_official_eod_schemas_close_nested_objects_and_negative_counts(self) -> None:
        report = json.loads(
            (ROOT / "schemas" / "official-eod-import-report.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(report["properties"]["upstream"]["$ref"], "#/$defs/upstream")
        self.assertFalse(report["$defs"]["upstream"]["additionalProperties"])
        self.assertFalse(report["$defs"]["providerReceipt"]["additionalProperties"])
        self.assertFalse(report["$defs"]["marketTotalsReceipt"]["additionalProperties"])
        self.assertEqual(
            report["$defs"]["nullableCount"]["oneOf"][1]["minimum"],
            0,
        )

        manifest = json.loads(
            (ROOT / "schemas" / "official-eod-manifest.schema.json").read_text(
                encoding="utf-8"
            )
        )
        integer_count = manifest["$defs"]["optionalCount"]["oneOf"][0]
        self.assertEqual(integer_count, {"type": "integer", "minimum": 0})
        for definition in ("provider", "marketTotals"):
            properties = manifest["$defs"][definition]["properties"]
            for field in (
                "pages_declared",
                "pages_received",
                "result_count_declared",
                "rows_normalized",
            ):
                self.assertEqual(properties[field]["$ref"], "#/$defs/optionalCount")

        evidence_manifest = json.loads(
            (
                ROOT
                / "schemas"
                / "official-eod-evidence-manifest.schema.json"
            ).read_text(encoding="utf-8")
        )
        self.assertFalse(evidence_manifest["additionalProperties"])
        self.assertFalse(
            evidence_manifest["$defs"]["artifact"]["additionalProperties"]
        )
        self.assertIn(
            "RAW_DOWNLOAD",
            evidence_manifest["$defs"]["artifact"]["properties"][
                "capture_kind"
            ]["enum"],
        )

        validation = json.loads(
            (
                ROOT
                / "schemas"
                / "official-eod-validation-report.schema.json"
            ).read_text(encoding="utf-8")
        )
        self.assertFalse(validation["additionalProperties"])
        self.assertFalse(
            validation["properties"]["claim_boundaries"]["additionalProperties"]
        )
        self.assertEqual(
            validation["properties"]["providers"]["items"]["$ref"],
            "#/$defs/providerReceipt",
        )
        self.assertEqual(
            validation["properties"]["upstream"]["$ref"],
            "#/$defs/upstream",
        )
        self.assertEqual(
            validation["properties"]["market_totals_receipt"]["$ref"],
            "#/$defs/marketTotalsReceipt",
        )
        for definition in (
            "sha256",
            "nullableSha256",
            "nullableCount",
            "classification",
            "rights",
            "runtimeTrust",
            "officialReceipt",
            "statusReceipt",
            "upstream",
            "providerReceipt",
            "marketTotalsReceipt",
            "captureEvidenceInvariants",
        ):
            with self.subTest(embedded_definition=definition):
                self.assertEqual(
                    validation["$defs"][definition],
                    report["$defs"][definition],
                )

        benchmark_evidence = json.loads(
            (
                ROOT / "schemas" / "benchmark-evidence-manifest.schema.json"
            ).read_text(encoding="utf-8")
        )
        self.assertFalse(benchmark_evidence["additionalProperties"])
        self.assertFalse(
            benchmark_evidence["$defs"]["artifact"]["additionalProperties"]
        )
        self.assertIn(
            "SYNTHETIC_GENERATED",
            benchmark_evidence["$defs"]["artifact"]["properties"][
                "capture_kind"
            ]["enum"],
        )

    def test_every_schema_is_valid_and_resolvable_with_local_registry(self) -> None:
        for path in sorted((ROOT / "schemas").glob("*.schema.json")):
            with self.subTest(path=path.name):
                schema = _load_schema(path.name)
                Draft202012Validator.check_schema(schema)
                _schema_validator(path.name)

        validation_schema = _load_schema(
            "official-eod-validation-report.schema.json"
        )
        refs = json.dumps(validation_schema, sort_keys=True)
        self.assertNotIn("official-eod-import-report.schema.json#", refs)
        validator = _schema_validator(
            "official-eod-validation-report.schema.json"
        )
        validator.validate(_official_validation_report())

        forged_nested_receipt = _official_validation_report()
        forged_nested_receipt["providers"][0]["uncontracted"] = True
        with self.assertRaises(ValidationError):
            validator.validate(forged_nested_receipt)

    def test_final_ready_and_pass_invariants_reject_forged_reports(self) -> None:
        gate_validator = _schema_validator(
            "data-foundation-gate-report.schema.json"
        )
        ready_gate_report = _data_foundation_gate_report()
        with self.assertRaises(ValidationError):
            gate_validator.validate(ready_gate_report)

        non_ready_gate_report = copy.deepcopy(ready_gate_report)
        non_ready_gate_report["status"] = "DATA_FOUNDATION_PARTIAL"
        non_ready_gate_report["evidence_classification"] = "PARTIAL"
        gate_validator.validate(non_ready_gate_report)

        forged = copy.deepcopy(non_ready_gate_report)
        forged["gates"][0]["status"] = "PARTIAL"
        gate_validator.validate(forged)

        forged = copy.deepcopy(non_ready_gate_report)
        forged["gates"][0]["evidence_classification"] = "SYNTHETIC_ONLY"
        with self.assertRaises(ValidationError):
            gate_validator.validate(forged)

        forged = copy.deepcopy(non_ready_gate_report)
        forged["gates"][0]["rights_compatible"] = False
        with self.assertRaises(ValidationError):
            gate_validator.validate(forged)

        forged = copy.deepcopy(non_ready_gate_report)
        forged["gates"][0]["details"]["checks"]["contract"] = "PARTIAL"
        with self.assertRaises(ValidationError):
            gate_validator.validate(forged)

        packet_validator = _schema_validator("data-foundation-packet.schema.json")
        ready_packet = _data_foundation_packet()
        with self.assertRaises(ValidationError):
            packet_validator.validate(ready_packet)

        non_ready_packet = copy.deepcopy(ready_packet)
        non_ready_packet["status"] = "DATA_FOUNDATION_PARTIAL"
        non_ready_packet["evidence_classification"] = "PARTIAL"
        non_ready_packet["outcome_session_policy_status"] = "UNFROZEN"
        packet_validator.validate(non_ready_packet)

        future_packet_schema = _load_schema("data-foundation-packet.schema.json")
        future_packet_schema.pop("not")
        future_packet_validator = Draft202012Validator(future_packet_schema)
        future_packet_validator.validate(ready_packet)
        for mutation in (
            "policy",
            "classification",
            "rights",
            "rights_status",
            "structural",
        ):
            with self.subTest(mutation=mutation):
                forged = copy.deepcopy(ready_packet)
                if mutation == "policy":
                    forged["outcome_session_policy_status"] = "UNFROZEN"
                elif mutation == "classification":
                    forged["components"][0]["evidence_classification"] = (
                        "LIVE_DEPENDENT"
                    )
                elif mutation == "rights":
                    forged["components"][0]["rights_compatible"] = False
                elif mutation == "rights_status":
                    forged["components"][0]["rights_statuses"] = ["FIXTURE_ONLY"]
                else:
                    forged["components"][0]["structural_errors"] = ["FORGED"]
                with self.assertRaises(ValidationError):
                    future_packet_validator.validate(forged)

    def test_benchmark_ready_and_evidence_relabel_invariants(self) -> None:
        report_validator = _schema_validator("benchmark-import-report.schema.json")
        report = _benchmark_report()
        with self.assertRaises(ValidationError):
            report_validator.validate(report)

        dependent = copy.deepcopy(report)
        dependent["status"] = "PARTIAL"
        dependent["evidence_classification"] = "LIVE_DEPENDENT"
        dependent["benchmark_entries"][0][
            "evidence_classification"
        ] = "LIVE_DEPENDENT"
        dependent["comparisons"]["series"][0][
            "real_evidence_comparison_possible"
        ] = False
        dependent["comparisons"]["series"][0][
            "evidence_classification"
        ] = "LIVE_DEPENDENT"
        dependent["comparisons"]["product_rules"][0][
            "real_evidence_comparison_possible"
        ] = False
        dependent["comparisons"]["product_rules"][0]["status"] = "CONTRACT_ONLY"
        dependent["claim_boundaries"][
            "benchmark_history_ready_for_declared_window"
        ] = False
        dependent["claim_boundaries"][
            "artifact_bound_capture_authority_verified"
        ] = False
        report_validator.validate(dependent)

        relabeled = copy.deepcopy(dependent)
        relabeled["status"] = "BENCHMARK_HISTORY_READY"
        relabeled["evidence_classification"] = "PROVEN_REAL_EVIDENCE"
        relabeled["benchmark_entries"][0][
            "evidence_classification"
        ] = "PROVEN_REAL_EVIDENCE"
        relabeled["comparisons"]["series"][0][
            "real_evidence_comparison_possible"
        ] = True
        relabeled["comparisons"]["series"][0][
            "evidence_classification"
        ] = "PROVEN_REAL_EVIDENCE"
        relabeled["comparisons"]["product_rules"][0][
            "real_evidence_comparison_possible"
        ] = True
        relabeled["comparisons"]["product_rules"][0]["status"] = "READY"
        relabeled["claim_boundaries"][
            "benchmark_history_ready_for_declared_window"
        ] = True
        with self.assertRaises(ValidationError):
            report_validator.validate(relabeled)

        history_validator = _schema_validator("benchmark-history.schema.json")
        history = {
            "schema_version": "1.0",
            "rows": [
                {
                    "trade_date": "2026-08-09",
                    "benchmark_code": "KU_BO_BROAD_PRICE",
                    "benchmark_name": "Broad price",
                    "market_scope": "BROAD_MARKET",
                    "sector": "",
                    "calculation_basis": "PRICE_INDEX",
                    "benchmark_value": "1000.0",
                    "currency": "KWD",
                    "unit": "INDEX_POINTS",
                    "provider": "Official provider",
                    "source_id": "official_source",
                    "source_url": "https://example.test/benchmark.csv",
                    "raw_sha256": "5" * 64,
                    "observed_at": "2026-08-09T13:00:00+03:00",
                    "capture_mode": "RECORDED_AUTHORIZED_FIXTURE",
                    "rights_status": "FIXTURE_ONLY",
                    "evidence_classification": "RECORDED_AUTHORIZED_FIXTURE",
                }
            ],
            "claim_boundaries": {
                "price_index_used_as_total_return_index": False,
                "broad_market_used_as_sector_benchmark": False,
                "fallback_benchmark_substitution_used": False,
                "forward_fill_used": False,
                "synthetic_benchmark_rows_created": False,
                "registry_effective_from_used_as_series_inception": False,
                "backtest_ready": False,
            },
        }
        history_validator.validate(history)
        forged = copy.deepcopy(history)
        forged["rows"][0]["evidence_classification"] = "PROVEN_REAL_EVIDENCE"
        with self.assertRaises(ValidationError):
            history_validator.validate(forged)

        evidence_validator = _schema_validator(
            "benchmark-evidence-manifest.schema.json"
        )
        evidence = {
            "schema_version": "3.0",
            "artifacts": [
                {
                    "path": "raw/broad.csv",
                    "sha256": "6" * 64,
                    "size_bytes": 10,
                    "source_id": "official_source",
                    "source_url": "https://example.test/benchmark.csv",
                    "observed_at": "2026-08-09T13:00:00+03:00",
                    "capture_kind": "SYNTHETIC_GENERATED",
                    "artifact_role": "BENCHMARK_HISTORY_EXPORT",
                    "benchmark_code": "KU_BO_BROAD_PRICE",
                    "availability_status": "AVAILABLE",
                    "rights_status": "FIXTURE_ONLY",
                    "evidence_classification": "SYNTHETIC_ONLY",
                }
            ],
        }
        evidence_validator.validate(evidence)
        forged = copy.deepcopy(evidence)
        forged["artifacts"][0]["evidence_classification"] = (
            "PROVEN_REAL_EVIDENCE"
        )
        forged["artifacts"][0]["rights_status"] = "RESEARCH_USE_AUTHORIZED"
        with self.assertRaises(ValidationError):
            evidence_validator.validate(forged)

        manifest_validator = _schema_validator(
            "benchmark-history-manifest.schema.json"
        )
        manifest = {
            "schema_version": "1.0",
            "run_id": "benchmark-run",
            "registry_id": "benchmark-registry",
            "registry_sha256": "7" * 64,
            "registry_date_basis": "KU_BO_REGISTRY_OBSERVATION_NOT_PROVIDER_LAUNCH_OR_SERIES_INCEPTION",
            "window_from": "2026-08-09",
            "window_to": "2026-08-09",
            "upstream": {
                "status": "CURRENT_IDENTITY_AND_CALENDAR_READY",
                "run_id": "official-run",
                "calendar_window_from": "2026-08-09",
                "calendar_window_to": "2026-08-09",
                "trading_date_count": 1,
                "official_foundation_report_sha256": "8" * 64,
                "trading_calendar_sha256": "9" * 64,
                "evidence_manifest_sha256": "a" * 64,
            },
            "artifacts": [
                {
                    "benchmark_code": "KU_BO_BROAD_PRICE",
                    "source_id": "official_source",
                    "source_url": "https://example.test/benchmark.csv",
                    "provider": "Official provider",
                    "file_name": "broad.csv",
                    "availability_status": "AVAILABLE",
                    "file_sha256": "b" * 64,
                    "observed_at": "2026-08-09T13:00:00+03:00",
                    "captured_by": "schema-test",
                    "capture_mode": "RECORDED_AUTHORIZED_FIXTURE",
                    "rights_status": "FIXTURE_ONLY",
                    "window_from": "2026-08-09",
                    "window_to": "2026-08-09",
                    "pages_declared": 1,
                    "pages_received": 1,
                    "result_count_declared": 1,
                    "row_count": 1,
                    "review_status": "ACCEPTED",
                    "review_notes": "fixture",
                    "unavailable_reason": "",
                }
            ],
        }
        manifest_validator.validate(manifest)
        forged = copy.deepcopy(manifest)
        forged["artifacts"][0]["rights_status"] = "RESEARCH_USE_AUTHORIZED"
        with self.assertRaises(ValidationError):
            manifest_validator.validate(forged)

    def test_official_eod_ready_invariants_and_validation_pass_semantics(self) -> None:
        import_validator = _schema_validator(
            "official-eod-import-report.schema.json"
        )
        partial_import = _official_import_report()
        import_validator.validate(partial_import)
        ready_import = _promote_official_eod_ready(partial_import)
        with self.assertRaises(ValidationError):
            import_validator.validate(ready_import)

        forged = copy.deepcopy(partial_import)
        forged["providers"][0]["capture_mode"] = "SYNTHETIC_GENERATED"
        with self.assertRaises(ValidationError):
            import_validator.validate(forged)

        forged = copy.deepcopy(partial_import)
        forged["claim_boundaries"]["official_complete_eod_ready"] = True
        forged["claim_boundaries"][
            "artifact_bound_capture_authority_verified"
        ] = True
        with self.assertRaises(ValidationError):
            import_validator.validate(forged)

        validation_validator = _schema_validator(
            "official-eod-validation-report.schema.json"
        )
        partial_validation = _official_validation_report()
        validation_validator.validate(partial_validation)
        ready_validation = _promote_official_eod_ready(partial_validation)
        with self.assertRaises(ValidationError):
            validation_validator.validate(ready_validation)

        forged = copy.deepcopy(partial_validation)
        forged["providers"][0]["capture_mode"] = "SYNTHETIC_GENERATED"
        with self.assertRaises(ValidationError):
            validation_validator.validate(forged)

        forged = copy.deepcopy(partial_validation)
        forged["errors"] = ["FORGED_PASS"]
        with self.assertRaises(ValidationError):
            validation_validator.validate(forged)


if __name__ == "__main__":
    unittest.main()
