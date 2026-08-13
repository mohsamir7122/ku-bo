from __future__ import annotations

import copy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import unittest

try:
    from jsonschema import Draft202012Validator, ValidationError
except ImportError:  # pragma: no cover - optional test dependency
    Draft202012Validator = None  # type: ignore[assignment,misc]

    class ValidationError(Exception):
        pass

from kubo.context_research import (
    DEFAULT_FACTOR_DEFINITIONS,
    DEFAULT_FACTOR_REGISTRY,
    build_factor_snapshot,
    context_event_from_dict,
    deduplicate_context_events,
    factor_registry_payload,
    security_exposure_from_dict,
    validate_factor_registry,
    validate_factor_snapshot,
    validate_security_exposures,
    window_tags_for,
)


ROOT = Path(__file__).resolve().parents[1]
HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64
HASH_D = "d" * 64
MANIFEST_HASHES = frozenset({HASH_A, HASH_B, HASH_C, HASH_D})
DECISION = "2026-08-13T12:00:00+03:00"


def schema_validator(name: str):
    if Draft202012Validator is None:
        raise unittest.SkipTest("jsonschema optional test dependency is unavailable")
    schema = json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)


def raw_event(
    event_id: str,
    *,
    available_at: str = "2026-08-13T09:00:00+03:00",
    scope: str = "SECURITY",
    scope_key: str = "101",
    source_id: str = "news-a",
    source_group_id: str = "publisher-a",
    source_class: str = "NEWS",
    origin_id: str = "origin-a",
    origin_hash: str = HASH_A,
    content_hash: str = HASH_B,
    evidence_hash: str = HASH_C,
    availability_hash: str = HASH_D,
    direction: str = "POSITIVE",
    relation_type: str = "STANDALONE",
    original_event_id: str | None = None,
    factual_status: str = "UNCONFIRMED",
    contradiction_status: str = "UNCONTESTED",
    correction_status: str = "CURRENT",
    capture_mode: str = "PROSPECTIVE",
    captured_at: str | None = None,
) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "event_id": event_id,
        "scope": scope,
        "scope_key": scope_key,
        "event_type": "CONTRACT_AWARD",
        "direction": direction,
        "materiality": 0.8,
        "confidence": 0.7,
        "novelty": 0.9,
        "event_at": available_at,
        "published_at": available_at,
        "first_available_at": available_at,
        "captured_at": captured_at or available_at,
        "decision_at": DECISION,
        "capture_mode": capture_mode,
        "source_id": source_id,
        "source_group_id": source_group_id,
        "source_class": source_class,
        "origin_id": origin_id,
        "origin_hash": origin_hash,
        "content_hash": content_hash,
        "evidence_hashes": [evidence_hash],
        "availability_evidence_hashes": [availability_hash],
        "relation_type": relation_type,
        "original_event_id": original_event_id,
        "factual_status": factual_status,
        "contradiction_status": contradiction_status,
        "correction_status": correction_status,
        "summary": "Synthetic contract event",
    }


def exposure_row(canonical_event_id: str, *, exposure_type: str = "DIRECT_NAMED") -> dict[str, object]:
    sector_code = "INDUSTRIALS" if exposure_type == "SECTOR_EXPOSURE" else None
    confirmation = {
        "INFERRED_EXPOSURE": "ANALYTICAL_INFERENCE",
        "UNRESOLVED": "UNRESOLVED",
    }.get(exposure_type, "NEWS_CORROBORATED")
    unresolved = exposure_type == "UNRESOLVED"
    return {
        "schema_version": "1.0",
        "exposure_id": "exp-" + "1" * 24,
        "canonical_event_id": canonical_event_id,
        "security_code": "101",
        "exposure_type": exposure_type,
        "sector_code": sector_code,
        "direction": "UNKNOWN" if unresolved else "POSITIVE",
        "confidence": 0.7,
        "materiality": 0.8,
        "available_at": "2026-08-13T09:05:00+03:00",
        "decision_at": DECISION,
        "confirmation_class": confirmation,
        "contradiction_status": "UNCONTESTED",
        "factor_eligible": not unresolved,
        "evidence_hashes": [HASH_C],
        "reason_codes": ["MAPPING_UNRESOLVED"] if unresolved else [],
    }


def factor_input(value: object, *, status: str = "OBSERVED", available_at: str = "2026-08-13T10:00:00+03:00") -> dict[str, object]:
    return {
        "status": status,
        "value": value,
        "available_at": available_at,
        "evidence_hashes": [HASH_A],
        "reason_codes": [],
    }


def required_factor_inputs() -> dict[str, dict[str, object]]:
    return {
        "price_momentum_5d": factor_input(0.0),
        "liquidity_activity_20d": factor_input(1.2),
        "security_trading_status": factor_input("TRADING"),
    }


class ContextWindowAndDedupTests(unittest.TestCase):
    def test_all_four_windows_are_inclusive_at_their_boundaries(self) -> None:
        decision = datetime.fromisoformat(DECISION)
        cases = (
            (timedelta(days=120), ("CONTEXT_120D",)),
            (timedelta(days=30), ("CONTEXT_120D", "ACTIVE_EVENT_30D")),
            (
                timedelta(days=7),
                ("CONTEXT_120D", "ACTIVE_EVENT_30D", "COMMUNITY_SENTIMENT_7D"),
            ),
            (
                timedelta(hours=72),
                (
                    "CONTEXT_120D",
                    "ACTIVE_EVENT_30D",
                    "COMMUNITY_SENTIMENT_7D",
                    "FRESH_CATALYST_72H",
                ),
            ),
        )
        for age, expected in cases:
            with self.subTest(age=age):
                self.assertEqual(
                    window_tags_for(first_available_at=decision - age, decision_at=decision),
                    expected,
                )

    def test_outside_120_days_and_future_availability_are_rejected(self) -> None:
        decision = datetime.fromisoformat(DECISION)
        with self.assertRaisesRegex(ValueError, "outside CONTEXT_120D"):
            window_tags_for(first_available_at=decision - timedelta(days=120, seconds=1), decision_at=decision)
        with self.assertRaisesRegex(ValueError, "after decision"):
            window_tags_for(first_available_at=decision + timedelta(microseconds=1), decision_at=decision)

    def test_scope_contract_and_unknown_fields_fail_closed(self) -> None:
        row = raw_event("e1", scope="KUWAIT_MACRO", scope_key="NOT_KUWAIT")
        with self.assertRaisesRegex(ValueError, "scope_key must be KUWAIT"):
            context_event_from_dict(row, manifest_hashes=MANIFEST_HASHES)
        row = raw_event("e2")
        row["unexpected"] = True
        with self.assertRaisesRegex(ValueError, "extra"):
            context_event_from_dict(row, manifest_hashes=MANIFEST_HASHES)

    def test_prospective_capture_after_cutoff_is_rejected(self) -> None:
        row = raw_event("e1", captured_at="2026-08-13T12:00:01+03:00")
        with self.assertRaisesRegex(ValueError, "captured after decision"):
            context_event_from_dict(row, manifest_hashes=MANIFEST_HASHES)

    def test_community_and_search_routing_cannot_claim_confirmation(self) -> None:
        community = raw_event("e1", source_class="COMMUNITY", factual_status="OFFICIAL_CONFIRMED")
        with self.assertRaisesRegex(ValueError, "cannot establish factual confirmation"):
            context_event_from_dict(community, manifest_hashes=MANIFEST_HASHES)
        search = raw_event("e2", source_class="SEARCH_ROUTING", factual_status="UNCONFIRMED")
        with self.assertRaisesRegex(ValueError, "must remain ROUTING_ONLY"):
            context_event_from_dict(search, manifest_hashes=MANIFEST_HASHES)

        news = raw_event("e3", source_class="NEWS", factual_status="OFFICIAL_CONFIRMED")
        with self.assertRaisesRegex(ValueError, "requires an official primary"):
            context_event_from_dict(news, manifest_hashes=MANIFEST_HASHES)

    def test_origin_and_content_dedup_are_transitive(self) -> None:
        first = context_event_from_dict(raw_event("e1"), manifest_hashes=MANIFEST_HASHES)
        same_origin = context_event_from_dict(
            raw_event(
                "e2",
                source_id="news-b",
                source_group_id="publisher-b",
                content_hash=HASH_D,
                evidence_hash=HASH_B,
                availability_hash=HASH_A,
            ),
            manifest_hashes=MANIFEST_HASHES,
        )
        same_content = context_event_from_dict(
            raw_event(
                "e3",
                source_id="news-c",
                source_group_id="publisher-c",
                origin_id="origin-c",
                origin_hash=HASH_D,
                content_hash=HASH_D,
                evidence_hash=HASH_A,
                availability_hash=HASH_B,
            ),
            manifest_hashes=MANIFEST_HASHES,
        )
        rows = deduplicate_context_events([first, same_origin, same_content])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["diffusion_count"], 3)
        self.assertEqual(rows[0]["independent_source_groups"], 3)
        schema_validator("context-event.schema.json").validate(rows[0])

    def test_canonical_id_is_stable_when_a_later_repost_arrives(self) -> None:
        original = context_event_from_dict(
            raw_event("e1", relation_type="ORIGINAL"), manifest_hashes=MANIFEST_HASHES
        )
        first_snapshot = deduplicate_context_events([original])
        repost = context_event_from_dict(
            raw_event(
                "e2",
                available_at="2026-08-13T10:00:00+03:00",
                source_id="news-b",
                source_group_id="publisher-b",
                origin_id="origin-b",
                origin_hash=HASH_D,
                content_hash=HASH_D,
                relation_type="REPUBLISHED",
                original_event_id="e1",
            ),
            manifest_hashes=MANIFEST_HASHES,
        )
        second_snapshot = deduplicate_context_events([original, repost])
        self.assertEqual(first_snapshot[0]["canonical_event_id"], second_snapshot[0]["canonical_event_id"])

    def test_correction_is_preserved_as_a_distinct_event(self) -> None:
        original = context_event_from_dict(
            raw_event("e1", relation_type="ORIGINAL"), manifest_hashes=MANIFEST_HASHES
        )
        correction = context_event_from_dict(
            raw_event(
                "e2",
                relation_type="CORRECTIVE",
                original_event_id="e1",
                correction_status="CORRECTED",
            ),
            manifest_hashes=MANIFEST_HASHES,
        )
        rows = deduplicate_context_events([original, correction])
        self.assertEqual(len(rows), 2)
        self.assertEqual({row["correction_status"] for row in rows}, {"CURRENT", "CORRECTED"})

    def test_same_content_with_conflicting_direction_is_rejected(self) -> None:
        first = context_event_from_dict(raw_event("e1"), manifest_hashes=MANIFEST_HASHES)
        conflict = context_event_from_dict(
            raw_event("e2", origin_id="other", origin_hash=HASH_D, direction="NEGATIVE"),
            manifest_hashes=MANIFEST_HASHES,
        )
        with self.assertRaisesRegex(ValueError, "conflicting event semantics"):
            deduplicate_context_events([first, conflict])


class SecurityExposureTests(unittest.TestCase):
    def setUp(self) -> None:
        event = context_event_from_dict(raw_event("e1"), manifest_hashes=MANIFEST_HASHES)
        self.context_rows = deduplicate_context_events([event])
        self.event_id = self.context_rows[0]["canonical_event_id"]

    def test_all_five_exposure_types_have_strict_contracts(self) -> None:
        validator = schema_validator("security-exposure.schema.json")
        for index, exposure_type in enumerate(
            ("DIRECT_NAMED", "CONTRACT_COUNTERPARTY", "SECTOR_EXPOSURE", "INFERRED_EXPOSURE", "UNRESOLVED"),
            start=1,
        ):
            with self.subTest(exposure_type=exposure_type):
                payload = exposure_row(self.event_id, exposure_type=exposure_type)
                payload["exposure_id"] = "exp-" + str(index) * 24
                exposure = security_exposure_from_dict(payload, manifest_hashes=MANIFEST_HASHES)
                validator.validate(exposure.to_dict())

    def test_exposure_lookahead_and_unresolved_relabel_are_rejected(self) -> None:
        payload = exposure_row(self.event_id)
        payload["available_at"] = "2026-08-13T12:00:01+03:00"
        with self.assertRaisesRegex(ValueError, "after decision"):
            security_exposure_from_dict(payload, manifest_hashes=MANIFEST_HASHES)
        payload = exposure_row(self.event_id, exposure_type="UNRESOLVED")
        payload["factor_eligible"] = True
        with self.assertRaisesRegex(ValueError, "must remain non-factor-eligible"):
            security_exposure_from_dict(payload, manifest_hashes=MANIFEST_HASHES)

    def test_inferred_exposure_cannot_be_relabeled_as_official(self) -> None:
        payload = exposure_row(self.event_id, exposure_type="INFERRED_EXPOSURE")
        payload["confirmation_class"] = "OFFICIAL_EVIDENCE"
        with self.assertRaisesRegex(ValueError, "must remain ANALYTICAL_INFERENCE"):
            security_exposure_from_dict(payload, manifest_hashes=MANIFEST_HASHES)

    def test_exposure_must_resolve_event_and_denominator(self) -> None:
        exposure = security_exposure_from_dict(exposure_row(self.event_id), manifest_hashes=MANIFEST_HASHES)
        self.assertEqual(
            validate_security_exposures(
                [exposure], context_events=self.context_rows, expected_security_codes=["101"]
            )["status"],
            "PASS",
        )
        report = validate_security_exposures(
            [exposure], context_events=self.context_rows, expected_security_codes=["999"]
        )
        self.assertEqual(report["status"], "BLOCKED")
        self.assertTrue(any("outside frozen denominator" in item for item in report["errors"]))

    def test_exposure_evidence_and_decision_must_bind_to_event(self) -> None:
        payload = exposure_row(self.event_id)
        payload["evidence_hashes"] = [HASH_A]
        exposure = security_exposure_from_dict(payload, manifest_hashes=MANIFEST_HASHES)
        report = validate_security_exposures(
            [exposure], context_events=self.context_rows, expected_security_codes=["101"]
        )
        self.assertEqual(report["status"], "BLOCKED")
        self.assertTrue(any("does not bind" in item for item in report["errors"]))

        payload = exposure_row(self.event_id)
        payload["decision_at"] = "2026-08-13T11:59:59+03:00"
        exposure = security_exposure_from_dict(payload, manifest_hashes=MANIFEST_HASHES)
        report = validate_security_exposures(
            [exposure], context_events=self.context_rows, expected_security_codes=["101"]
        )
        self.assertEqual(report["status"], "BLOCKED")
        self.assertTrue(any("cutoff does not match" in item for item in report["errors"]))

    def test_routing_only_event_cannot_create_factor_eligible_exposure(self) -> None:
        routing_event = context_event_from_dict(
            raw_event(
                "routing",
                source_class="SEARCH_ROUTING",
                factual_status="ROUTING_ONLY",
                origin_hash=HASH_D,
            ),
            manifest_hashes=MANIFEST_HASHES,
        )
        context_rows = deduplicate_context_events([routing_event])
        payload = exposure_row(context_rows[0]["canonical_event_id"])
        exposure = security_exposure_from_dict(payload, manifest_hashes=MANIFEST_HASHES)
        report = validate_security_exposures(
            [exposure], context_events=context_rows, expected_security_codes=["101"]
        )
        self.assertEqual(report["status"], "BLOCKED")
        self.assertTrue(any("routing-only" in item for item in report["errors"]))

    def test_superseded_event_cannot_create_factor_eligible_exposure(self) -> None:
        superseded_event = context_event_from_dict(
            raw_event("superseded", correction_status="SUPERSEDED"),
            manifest_hashes=MANIFEST_HASHES,
        )
        context_rows = deduplicate_context_events([superseded_event])
        exposure = security_exposure_from_dict(
            exposure_row(context_rows[0]["canonical_event_id"]),
            manifest_hashes=MANIFEST_HASHES,
        )
        report = validate_security_exposures(
            [exposure], context_events=context_rows, expected_security_codes=["101"]
        )
        self.assertEqual(report["status"], "BLOCKED")
        self.assertTrue(any("superseded" in item for item in report["errors"]))

    def test_current_corrective_event_remains_factor_eligible(self) -> None:
        corrected_event = context_event_from_dict(
            raw_event("corrected", correction_status="CORRECTED"),
            manifest_hashes=MANIFEST_HASHES,
        )
        context_rows = deduplicate_context_events([corrected_event])
        exposure = security_exposure_from_dict(
            exposure_row(context_rows[0]["canonical_event_id"]),
            manifest_hashes=MANIFEST_HASHES,
        )
        report = validate_security_exposures(
            [exposure], context_events=context_rows, expected_security_codes=["101"]
        )
        self.assertEqual(report["status"], "PASS", report)


class FactorRegistryAndSnapshotTests(unittest.TestCase):
    def test_default_registry_is_versioned_hash_bound_and_not_predictive(self) -> None:
        report = validate_factor_registry(DEFAULT_FACTOR_REGISTRY)
        self.assertEqual(report["status"], "PASS", report)
        self.assertGreaterEqual(report["definition_count"], 12)
        self.assertFalse(DEFAULT_FACTOR_REGISTRY["claim_boundaries"]["score_is_probability"])
        tampered = copy.deepcopy(DEFAULT_FACTOR_REGISTRY)
        tampered["definitions"][0]["family"] = "TAMPERED"
        report = validate_factor_registry(tampered)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertIn("hash mismatch", report["errors"][0])

        status_definition = next(
            row
            for row in DEFAULT_FACTOR_REGISTRY["definitions"]
            if row["factor_id"] == "security_trading_status"
        )
        self.assertEqual(status_definition["lookback_window"], "CURRENT_STATUS_24H")
        self.assertIsNone(status_definition["window_days"])
        self.assertEqual(status_definition["window_hours"], 24)

    def test_registry_rejects_a_duration_that_disagrees_with_its_named_window(self) -> None:
        definitions = list(DEFAULT_FACTOR_DEFINITIONS)
        definitions[0] = replace(definitions[0], window_days=8)
        report = validate_factor_registry(factor_registry_payload(definitions))
        self.assertEqual(report["status"], "BLOCKED")
        self.assertTrue(any("duration" in item for item in report["errors"]))

    def test_registry_rejects_duplicate_factor_ids(self) -> None:
        registry = factor_registry_payload()
        registry["definitions"].append(copy.deepcopy(registry["definitions"][0]))
        registry_without_hash = dict(registry)
        registry_without_hash.pop("registry_sha256")
        # A stale hash is enough to block; duplicate IDs are also checked before the hash.
        report = validate_factor_registry(registry)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertIn("duplicated", report["errors"][0])

    def test_missing_inputs_emit_one_abstained_row_per_denominator_security(self) -> None:
        snapshot = build_factor_snapshot(
            decision_id="decision-1",
            decision_at=DECISION,
            universe_as_of="2026-08-13T08:00:00+03:00",
            expected_security_codes=["102", "101"],
            factor_inputs_by_security={},
            dispositions_by_security=None,
            manifest_hashes=MANIFEST_HASHES,
        )
        self.assertEqual(snapshot["expected_security_codes"], ["101", "102"])
        self.assertEqual([row["security_code"] for row in snapshot["rows"]], ["101", "102"])
        self.assertTrue(all(row["disposition"] == "ABSTAINED" for row in snapshot["rows"]))
        for row in snapshot["rows"]:
            self.assertTrue(all(item["value"] is None for item in row["factors"]))
            self.assertTrue(all(item["status"] == "MISSING" for item in row["factors"]))
        schema_validator("factor-snapshot.schema.json").validate(snapshot)

    def test_observed_zero_is_allowed_only_with_evidence(self) -> None:
        snapshot = build_factor_snapshot(
            decision_id="decision-zero",
            decision_at=DECISION,
            universe_as_of="2026-08-13T08:00:00+03:00",
            expected_security_codes=["101"],
            factor_inputs_by_security={"101": required_factor_inputs()},
            dispositions_by_security={
                "101": {
                    "disposition": "SELECTED",
                    "first_failed_stage": None,
                    "reason_codes": [],
                    "score": 0.0,
                    "score_kind": "UNVALIDATED_RESEARCH_SCORE",
                }
            },
            manifest_hashes=MANIFEST_HASHES,
        )
        price = next(item for item in snapshot["rows"][0]["factors"] if item["factor_id"] == "price_momentum_5d")
        self.assertEqual(price["value"], 0.0)
        self.assertEqual(price["status"], "OBSERVED")
        self.assertEqual(price["evidence_hashes"], [HASH_A])
        self.assertIsNone(snapshot["rows"][0]["probability"])

    def test_missing_factor_cannot_smuggle_a_zero_or_evidence(self) -> None:
        inputs = required_factor_inputs()
        inputs["price_momentum_5d"] = {
            "status": "MISSING",
            "value": 0,
            "available_at": None,
            "evidence_hashes": [],
            "reason_codes": ["NOT_AVAILABLE"],
        }
        with self.assertRaisesRegex(ValueError, "MISSING must remain null"):
            build_factor_snapshot(
                decision_id="decision-2",
                decision_at=DECISION,
                universe_as_of="2026-08-13T08:00:00+03:00",
                expected_security_codes=["101"],
                factor_inputs_by_security={"101": inputs},
                dispositions_by_security=None,
                manifest_hashes=MANIFEST_HASHES,
            )

    def test_observed_factor_requires_resolved_evidence_and_no_lookahead(self) -> None:
        inputs = required_factor_inputs()
        inputs["price_momentum_5d"]["evidence_hashes"] = []
        with self.assertRaisesRegex(ValueError, "at least 1"):
            build_factor_snapshot(
                decision_id="decision-3",
                decision_at=DECISION,
                universe_as_of="2026-08-13T08:00:00+03:00",
                expected_security_codes=["101"],
                factor_inputs_by_security={"101": inputs},
                dispositions_by_security=None,
                manifest_hashes=MANIFEST_HASHES,
            )
        inputs = required_factor_inputs()
        inputs["price_momentum_5d"]["available_at"] = "2026-08-13T12:00:01+03:00"
        with self.assertRaisesRegex(ValueError, "look-ahead"):
            build_factor_snapshot(
                decision_id="decision-4",
                decision_at=DECISION,
                universe_as_of="2026-08-13T08:00:00+03:00",
                expected_security_codes=["101"],
                factor_inputs_by_security={"101": inputs},
                dispositions_by_security=None,
                manifest_hashes=MANIFEST_HASHES,
            )

    def test_observed_factor_must_be_fresh_inside_its_registry_window(self) -> None:
        decision = datetime.fromisoformat(DECISION)
        inputs = required_factor_inputs()
        inputs["price_momentum_5d"]["available_at"] = (
            decision - timedelta(days=7, seconds=1)
        ).isoformat()
        with self.assertRaisesRegex(ValueError, "outside its registry window"):
            build_factor_snapshot(
                decision_id="decision-stale-price",
                decision_at=DECISION,
                universe_as_of="2026-08-13T08:00:00+03:00",
                expected_security_codes=["101"],
                factor_inputs_by_security={"101": inputs},
                dispositions_by_security=None,
                manifest_hashes=MANIFEST_HASHES,
            )

        inputs = required_factor_inputs()
        inputs["security_trading_status"]["available_at"] = (
            decision - timedelta(hours=24, seconds=1)
        ).isoformat()
        with self.assertRaisesRegex(ValueError, "outside its registry window"):
            build_factor_snapshot(
                decision_id="decision-stale-status",
                decision_at=DECISION,
                universe_as_of="2026-08-13T08:00:00+03:00",
                expected_security_codes=["101"],
                factor_inputs_by_security={"101": inputs},
                dispositions_by_security=None,
                manifest_hashes=MANIFEST_HASHES,
            )

    def test_not_applicable_requires_coverage_evidence(self) -> None:
        inputs = required_factor_inputs()
        inputs["corporate_action_state"] = {
            "status": "NOT_APPLICABLE",
            "value": None,
            "available_at": None,
            "evidence_hashes": [],
            "reason_codes": ["NO_ACTION_IN_WINDOW"],
        }
        with self.assertRaises(ValueError):
            build_factor_snapshot(
                decision_id="decision-5",
                decision_at=DECISION,
                universe_as_of="2026-08-13T08:00:00+03:00",
                expected_security_codes=["101"],
                factor_inputs_by_security={"101": inputs},
                dispositions_by_security=None,
                manifest_hashes=MANIFEST_HASHES,
            )

    def test_enum_factor_is_registry_checked(self) -> None:
        inputs = required_factor_inputs()
        inputs["security_trading_status"] = factor_input("MAGIC_STATUS")
        with self.assertRaisesRegex(ValueError, "invalid enum"):
            build_factor_snapshot(
                decision_id="decision-6",
                decision_at=DECISION,
                universe_as_of="2026-08-13T08:00:00+03:00",
                expected_security_codes=["101"],
                factor_inputs_by_security={"101": inputs},
                dispositions_by_security=None,
                manifest_hashes=MANIFEST_HASHES,
            )

    def test_selected_disposition_is_blocked_when_required_factor_is_missing(self) -> None:
        inputs = required_factor_inputs()
        inputs.pop("liquidity_activity_20d")
        with self.assertRaisesRegex(ValueError, "SELECTED requires"):
            build_factor_snapshot(
                decision_id="decision-7",
                decision_at=DECISION,
                universe_as_of="2026-08-13T08:00:00+03:00",
                expected_security_codes=["101"],
                factor_inputs_by_security={"101": inputs},
                dispositions_by_security={
                    "101": {
                        "disposition": "SELECTED",
                        "first_failed_stage": None,
                        "reason_codes": [],
                        "score": 0.2,
                        "score_kind": "UNVALIDATED_RESEARCH_SCORE",
                    }
                },
                manifest_hashes=MANIFEST_HASHES,
            )

    def test_suspended_security_cannot_be_selected(self) -> None:
        inputs = required_factor_inputs()
        inputs["security_trading_status"] = factor_input("SUSPENDED")
        with self.assertRaisesRegex(ValueError, "SELECTED requires"):
            build_factor_snapshot(
                decision_id="decision-suspended",
                decision_at=DECISION,
                universe_as_of="2026-08-13T08:00:00+03:00",
                expected_security_codes=["101"],
                factor_inputs_by_security={"101": inputs},
                dispositions_by_security={
                    "101": {
                        "disposition": "SELECTED",
                        "first_failed_stage": None,
                        "reason_codes": [],
                        "score": 0.2,
                        "score_kind": "UNVALIDATED_RESEARCH_SCORE",
                    }
                },
                manifest_hashes=MANIFEST_HASHES,
            )

        snapshot = build_factor_snapshot(
            decision_id="decision-suspended-default",
            decision_at=DECISION,
            universe_as_of="2026-08-13T08:00:00+03:00",
            expected_security_codes=["101"],
            factor_inputs_by_security={"101": inputs},
            dispositions_by_security=None,
            manifest_hashes=MANIFEST_HASHES,
        )
        self.assertEqual(snapshot["rows"][0]["disposition"], "REJECTED")
        self.assertEqual(snapshot["rows"][0]["first_failed_stage"], "SECURITY_STATUS")

    def test_unknown_factor_or_security_cannot_escape_denominator_contract(self) -> None:
        with self.assertRaisesRegex(ValueError, "outside frozen denominator"):
            build_factor_snapshot(
                decision_id="decision-8",
                decision_at=DECISION,
                universe_as_of="2026-08-13T08:00:00+03:00",
                expected_security_codes=["101"],
                factor_inputs_by_security={"999": {}},
                dispositions_by_security=None,
                manifest_hashes=MANIFEST_HASHES,
            )
        with self.assertRaisesRegex(ValueError, "unknown factor"):
            build_factor_snapshot(
                decision_id="decision-9",
                decision_at=DECISION,
                universe_as_of="2026-08-13T08:00:00+03:00",
                expected_security_codes=["101"],
                factor_inputs_by_security={"101": {"unknown_factor": factor_input(1)}},
                dispositions_by_security=None,
                manifest_hashes=MANIFEST_HASHES,
            )

    def test_runtime_validator_rejects_forged_denominator_and_missing_zero(self) -> None:
        snapshot = build_factor_snapshot(
            decision_id="decision-10",
            decision_at=DECISION,
            universe_as_of="2026-08-13T08:00:00+03:00",
            expected_security_codes=["101", "102"],
            factor_inputs_by_security={},
            dispositions_by_security=None,
            manifest_hashes=MANIFEST_HASHES,
        )
        forged = copy.deepcopy(snapshot)
        forged["denominator_reconciliation"]["expected_count"] = 1
        report = validate_factor_snapshot(
            forged, registry=DEFAULT_FACTOR_REGISTRY, manifest_hashes=MANIFEST_HASHES
        )
        self.assertEqual(report["status"], "BLOCKED")
        self.assertTrue(any("denominator reconciliation" in item for item in report["errors"]))

        forged = copy.deepcopy(snapshot)
        forged["rows"][0]["factors"][0]["value"] = 0
        report = validate_factor_snapshot(
            forged, registry=DEFAULT_FACTOR_REGISTRY, manifest_hashes=MANIFEST_HASHES
        )
        self.assertEqual(report["status"], "BLOCKED")
        self.assertTrue(any("MISSING factor" in item for item in report["errors"]))

    def test_snapshot_hash_binds_factors_evidence_disposition_and_score(self) -> None:
        snapshot = build_factor_snapshot(
            decision_id="decision-hash-binding",
            decision_at=DECISION,
            universe_as_of="2026-08-13T08:00:00+03:00",
            expected_security_codes=["101"],
            factor_inputs_by_security={"101": required_factor_inputs()},
            dispositions_by_security={
                "101": {
                    "disposition": "SELECTED",
                    "first_failed_stage": None,
                    "reason_codes": [],
                    "score": 0.2,
                    "score_kind": "UNVALIDATED_RESEARCH_SCORE",
                }
            },
            manifest_hashes=MANIFEST_HASHES,
        )
        self.assertEqual(snapshot["snapshot_id"], "factor-snapshot-" + snapshot["factor_snapshot_sha256"][:24])

        factor_value = copy.deepcopy(snapshot)
        factor_value["rows"][0]["factors"][0]["value"] = 0.25

        factor_evidence = copy.deepcopy(snapshot)
        factor_evidence["rows"][0]["factors"][0]["evidence_hashes"] = [HASH_B]

        disposition = copy.deepcopy(snapshot)
        disposition["rows"][0].update(
            {
                "disposition": "REJECTED",
                "first_failed_stage": "RANKING",
                "reason_codes": ["RANKING_GATE"],
            }
        )

        score = copy.deepcopy(snapshot)
        score["rows"][0]["score"] = 0.4

        snapshot_id = copy.deepcopy(snapshot)
        snapshot_id["snapshot_id"] = "factor-snapshot-" + "f" * 24

        for label, forged in (
            ("factor value", factor_value),
            ("factor evidence", factor_evidence),
            ("disposition", disposition),
            ("score", score),
        ):
            with self.subTest(label=label):
                report = validate_factor_snapshot(
                    forged, registry=DEFAULT_FACTOR_REGISTRY, manifest_hashes=MANIFEST_HASHES
                )
                self.assertEqual(report["status"], "BLOCKED")
                self.assertTrue(any("content hash mismatch" in item for item in report["errors"]), report)

        report = validate_factor_snapshot(
            snapshot_id, registry=DEFAULT_FACTOR_REGISTRY, manifest_hashes=MANIFEST_HASHES
        )
        self.assertEqual(report["status"], "BLOCKED")
        self.assertTrue(any("snapshot_id mismatch" in item for item in report["errors"]), report)

    def test_runtime_validator_rejects_stale_factor_even_if_shape_is_valid(self) -> None:
        snapshot = build_factor_snapshot(
            decision_id="decision-stale-tamper",
            decision_at=DECISION,
            universe_as_of="2026-08-13T08:00:00+03:00",
            expected_security_codes=["101"],
            factor_inputs_by_security={"101": required_factor_inputs()},
            dispositions_by_security=None,
            manifest_hashes=MANIFEST_HASHES,
        )
        forged = copy.deepcopy(snapshot)
        factor = next(
            row for row in forged["rows"][0]["factors"] if row["factor_id"] == "security_trading_status"
        )
        factor["available_at"] = (datetime.fromisoformat(DECISION) - timedelta(hours=25)).isoformat()
        report = validate_factor_snapshot(
            forged, registry=DEFAULT_FACTOR_REGISTRY, manifest_hashes=MANIFEST_HASHES
        )
        self.assertEqual(report["status"], "BLOCKED")
        self.assertTrue(any("outside its registry window" in item for item in report["errors"]), report)

    def test_schemas_reject_uncontracted_fields(self) -> None:
        snapshot = build_factor_snapshot(
            decision_id="decision-11",
            decision_at=DECISION,
            universe_as_of="2026-08-13T08:00:00+03:00",
            expected_security_codes=["101"],
            factor_inputs_by_security={},
            dispositions_by_security=None,
            manifest_hashes=MANIFEST_HASHES,
        )
        validator = schema_validator("factor-snapshot.schema.json")
        validator.validate(snapshot)
        forged = copy.deepcopy(snapshot)
        forged["accuracy"] = 100
        with self.assertRaises(ValidationError):
            validator.validate(forged)


if __name__ == "__main__":
    unittest.main()
