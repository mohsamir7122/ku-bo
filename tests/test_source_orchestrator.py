from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from zoneinfo import ZoneInfo

from kubo.ingestion import CaptureRequest, CaptureResult
from kubo.hashing import canonical_json_bytes, hash_json, sha256_bytes
from kubo.source_network import SourceNetworkCatalog
from kubo.source_orchestrator import (
    AppendOnlyAttemptLedger,
    SourceSearchOrchestrator,
    load_orchestrator_policy,
    registrable_domain,
    validate_source_search_run,
)


ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 8, 13, 10, 0, tzinfo=timezone.utc)
DECISION = NOW + timedelta(hours=1)
KUWAIT = ZoneInfo("Asia/Kuwait")


def result(request: CaptureRequest, kind: str, *, final_url: str | None = None) -> CaptureResult:
    common = {
        "source_id": request.source_id,
        "source_url": request.source_url,
        "final_url": final_url or request.source_url,
        "access_mode": request.access_mode,
        "capture_kind": request.capture_kind,
        "roles_observed": request.roles_observed,
        "attempted_at": NOW,
        "content_type": "application/json",
        "http_status": 200,
        "limitations": (),
    }
    if kind == "qualified":
        return CaptureResult(
            **common,
            observed_at=NOW,
            state="AVAILABLE",
            query_status="QUALIFIED",
            qualified_items=1,
            zero_result=False,
            content=b'{"items":[1]}',
            error_code="",
            data_quality_flags=(),
        )
    if kind in {"zero", "zero_unproved", "zero_duplicate_proof"}:
        zero_content = (
            b'{"items":[],"route":"duplicate"}'
            if kind == "zero_duplicate_proof"
            else b'{"items":[]}'
            if kind == "zero_unproved"
            else b'{"items":[],"effective_route":'
            + json.dumps(request.source_url).encode("utf-8")
            + b"}"
        )
        return CaptureResult(
            **common,
            observed_at=NOW,
            state="AVAILABLE",
            query_status="ZERO_RESULT",
            qualified_items=0,
            zero_result=True,
            content=zero_content,
            error_code="",
            data_quality_flags=(),
            material_query_route_proof_sha256=(
                None
                if kind == "zero_unproved"
                else sha256_bytes(zero_content)
            ),
        )
    if kind == "empty":
        return CaptureResult(
            **common,
            observed_at=NOW,
            state="PARTIAL",
            query_status="DATA_QUALITY_REJECTED",
            qualified_items=0,
            zero_result=False,
            content=b"",
            error_code="",
            data_quality_flags=("EMPTY_RESPONSE_BODY",),
        )
    if kind == "raw":
        return CaptureResult(
            **common,
            observed_at=NOW,
            state="AVAILABLE",
            query_status="DATA_QUALITY_REJECTED",
            qualified_items=0,
            zero_result=False,
            content=b"<html>raw</html>",
            error_code="",
            data_quality_flags=("RAW_CAPTURE_PENDING_PARSER_VALIDATION",),
        )
    failure = {
        **common,
        "observed_at": None,
        "qualified_items": 0,
        "zero_result": False,
        "content": None,
        "content_type": "",
        "data_quality_flags": (),
    }
    if kind == "blocked":
        return CaptureResult(
            **{**failure, "http_status": 403},
            state="BLOCKED",
            query_status="BLOCKED",
            error_code="HTTP_FORBIDDEN",
        )
    if kind == "auth":
        return CaptureResult(
            **{**failure, "http_status": 401},
            state="AUTH_REQUIRED",
            query_status="AUTH_REQUIRED",
            error_code="HTTP_AUTH_REQUIRED",
        )
    if kind == "timeout":
        return CaptureResult(
            **{**failure, "http_status": None},
            state="ERROR",
            query_status="ERROR",
            error_code="HTTP_TIMEOUT",
        )
    if kind in {"dns", "robots_unavailable"}:
        return CaptureResult(
            **{**failure, "http_status": None},
            state="ERROR",
            query_status="ERROR",
            error_code=(
                "HTTP_DNS_ERROR" if kind == "dns" else "ROBOTS_POLICY_UNAVAILABLE"
            ),
        )
    if kind == "rate":
        return CaptureResult(
            **{**failure, "http_status": 429},
            state="BLOCKED",
            query_status="BLOCKED",
            error_code="HTTP_RATE_LIMITED",
        )
    if kind == "rate_retry_after":
        return CaptureResult(
            **{**failure, "http_status": 429},
            state="BLOCKED",
            query_status="BLOCKED",
            error_code="HTTP_RATE_LIMITED",
            retry_after_seconds=7.0,
        )
    if kind == "notfound":
        return CaptureResult(
            **{**failure, "http_status": 404},
            state="PARTIAL",
            query_status="DATA_QUALITY_REJECTED",
            error_code="HTTP_RESOURCE_NOT_FOUND",
        )
    raise AssertionError(kind)


class ScriptedConnector:
    def __init__(self, scripts=None, *, default="qualified"):
        self.scripts = {key: deque(value) for key, value in (scripts or {}).items()}
        self.default = default
        self.calls: list[CaptureRequest] = []

    def capture(self, request: CaptureRequest) -> CaptureResult:
        self.calls.append(request)
        queue = self.scripts.get(request.source_id)
        action = queue.popleft() if queue else self.default
        if isinstance(action, BaseException):
            raise action
        if isinstance(action, tuple):
            return result(request, action[0], final_url=action[1])
        return result(request, action)


class FixedClock:
    def __call__(self) -> datetime:
        return NOW


class WallBudgetClock:
    def __init__(self):
        self.calls = 0

    def __call__(self) -> datetime:
        self.calls += 1
        return NOW if self.calls == 1 else NOW + timedelta(seconds=1801)


class SourceOrchestratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = SourceNetworkCatalog(ROOT / "config")
        self.strategy_path = ROOT / "config" / "source_query_strategies.json"

    def run_one(self, connector, directory: str, **kwargs):
        return SourceSearchOrchestrator(
            catalog=self.catalog,
            strategy_path=self.strategy_path,
            connector=connector,
            clock=FixedClock(),
            sleeper=kwargs.pop("sleeper", lambda _seconds: None),
        ).run(
            run_id=kwargs.pop("run_id", "orchestrator-test"),
            decision_at=DECISION,
            attempt_log_path=Path(directory) / "source_attempts.jsonl",
            source_ids=kwargs.pop("source_ids", ["boursa_current"]),
            **kwargs,
        )

    def test_policy_freezes_three_transient_attempts_and_four_empty_strategies(self) -> None:
        policy = load_orchestrator_policy(self.strategy_path)
        self.assertEqual(policy.context_days, 120)
        self.assertEqual(policy.max_transient_attempts, 3)
        self.assertEqual(len(policy.strategies), 4)
        self.assertEqual(len({item.query_params for item in policy.strategies}), 4)

    def test_decision_and_watermarks_are_normalized_to_asia_kuwait(self) -> None:
        prior = DECISION - timedelta(days=7)
        with tempfile.TemporaryDirectory() as directory:
            run = self.run_one(
                ScriptedConnector(default="raw"),
                directory,
                watermarks={"boursa_current": prior.isoformat()},
            )
        payload = run.to_dict()
        self.assertEqual(payload["timezone"], "Asia/Kuwait")
        self.assertEqual(payload["decision_at"], DECISION.astimezone(KUWAIT).isoformat())
        self.assertEqual(payload["watermarks"]["timezone"], "Asia/Kuwait")
        self.assertEqual(
            payload["watermarks"]["initial"]["boursa_current"],
            prior.astimezone(KUWAIT).isoformat(),
        )
        self.assertTrue(payload["window_from"].endswith("+03:00"))
        self.assertTrue(payload["window_to"].endswith("+03:00"))

    def test_naive_decision_and_watermark_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            orchestrator = SourceSearchOrchestrator(
                catalog=self.catalog,
                strategy_path=self.strategy_path,
                connector=ScriptedConnector(default="qualified"),
                clock=FixedClock(),
                sleeper=lambda _seconds: None,
            )
            with self.assertRaisesRegex(ValueError, "decision_at must be a timezone-aware"):
                orchestrator.run(
                    run_id="naive-decision",
                    decision_at=DECISION.replace(tzinfo=None),
                    attempt_log_path=Path(directory) / "decision.jsonl",
                    source_ids=["boursa_current"],
                )
            with self.assertRaisesRegex(ValueError, "watermark.*timezone-aware"):
                orchestrator.run(
                    run_id="naive-watermark",
                    decision_at=DECISION,
                    attempt_log_path=Path(directory) / "watermark.jsonl",
                    source_ids=["boursa_current"],
                    watermarks={
                        "boursa_current": (DECISION - timedelta(days=1)).replace(
                            tzinfo=None
                        )
                    },
                )

    def test_transient_is_retried_exactly_three_times_before_next_strategy(self) -> None:
        connector = ScriptedConnector(
            {"boursa_current": ["timeout", "timeout", "timeout", "qualified"]}
        )
        sleeps: list[float] = []
        with tempfile.TemporaryDirectory() as directory:
            run = self.run_one(connector, directory, sleeper=sleeps.append)
            rows = [json.loads(line) for line in (Path(directory) / "source_attempts.jsonl").read_text().splitlines()]
        self.assertEqual(len(rows), 4)
        self.assertEqual([row["attempt_ordinal"] for row in rows[:3]], [1, 2, 3])
        self.assertEqual([row["strategy_ordinal"] for row in rows], [1, 1, 1, 2])
        self.assertEqual(sleeps, [0.25, 1.0])
        self.assertEqual(run.sources[0].status, "QUALIFIED")

    def test_dns_and_transient_robots_failures_receive_three_bounded_attempts(self) -> None:
        for kind in ("dns", "robots_unavailable"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                connector = ScriptedConnector(
                    {"boursa_current": [kind, kind, "qualified"]}
                )
                run = self.run_one(
                    connector,
                    directory,
                    run_id=f"transient-{kind}",
                )
                self.assertEqual(len(connector.calls), 3)
                self.assertEqual(run.sources[0].status, "QUALIFIED")

    def test_four_distinct_evidence_backed_zero_strategies_advance_watermark(self) -> None:
        connector = ScriptedConnector(default="zero")
        with tempfile.TemporaryDirectory() as directory:
            run = self.run_one(connector, directory)
            rows = [json.loads(line) for line in (Path(directory) / "source_attempts.jsonl").read_text().splitlines()]
        self.assertEqual(len(rows), 4)
        self.assertEqual(len({row["strategy_id"] for row in rows}), 4)
        self.assertEqual(len({row["requested_url"] for row in rows}), 4)
        self.assertEqual(
            len({row["material_query_route_proof_sha256"] for row in rows}),
            4,
        )
        self.assertTrue(
            all(
                row["material_query_route_proof_sha256"]
                == row["content_sha256"]
                for row in rows
            )
        )
        self.assertEqual(run.sources[0].status, "ZERO_RESULT")
        self.assertEqual(
            dict(run.final_watermarks)["boursa_current"],
            DECISION.astimezone(KUWAIT).isoformat(),
        )
        self.assertFalse(run.to_dict()["claim_boundaries"]["zero_result_is_negative_market_evidence"])

    def test_generic_or_duplicate_zero_routes_do_not_advance_watermark(self) -> None:
        for kind, limitation in (
            ("zero_unproved", "ZERO_RESULT_MATERIAL_QUERY_ROUTE_PROOF_MISSING"),
            ("zero_duplicate_proof", "ZERO_RESULT_MATERIAL_QUERY_ROUTE_PROOF_DUPLICATE"),
        ):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                run = self.run_one(
                    ScriptedConnector(default=kind),
                    directory,
                    run_id=f"unproved-{kind}",
                )
            self.assertEqual(run.sources[0].status, "ERROR")
            self.assertNotIn("boursa_current", dict(run.final_watermarks))
            self.assertIn(limitation, run.sources[0].limitations)

    def test_empty_http_bodies_try_four_strategies_but_do_not_advance_watermark(self) -> None:
        connector = ScriptedConnector(default="empty")
        with tempfile.TemporaryDirectory() as directory:
            run = self.run_one(connector, directory)
        self.assertEqual(len(connector.calls), 4)
        self.assertEqual(run.sources[0].status, "ERROR")
        self.assertNotIn("boursa_current", dict(run.final_watermarks))

    def test_hard_blocks_are_never_retried(self) -> None:
        for kind, expected in (("blocked", "BLOCKED"), ("auth", "AUTH_REQUIRED")):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                connector = ScriptedConnector(default=kind)
                run = self.run_one(connector, directory, run_id=f"hard-{kind}")
                self.assertEqual(len(connector.calls), 1)
                self.assertEqual(run.sources[0].status, expected)
                row = json.loads((Path(directory) / "source_attempts.jsonl").read_text())
                self.assertEqual(row["retry_disposition"], "STOP_HARD_BLOCK")

    def test_rate_limit_exhaustion_stops_source_without_rotating_strategy(self) -> None:
        connector = ScriptedConnector(
            {"boursa_current": ["rate", "rate", "rate", "qualified"]}
        )
        with tempfile.TemporaryDirectory() as directory:
            run = self.run_one(connector, directory)
            rows = [json.loads(line) for line in (Path(directory) / "source_attempts.jsonl").read_text().splitlines()]
        self.assertEqual(len(rows), 3)
        self.assertEqual([row["attempt_ordinal"] for row in rows], [1, 2, 3])
        self.assertEqual({row["strategy_ordinal"] for row in rows}, {1})
        self.assertTrue(
            all("RATE_LIMIT_RETRY_AFTER_UNAVAILABLE" in row["limitations"] for row in rows)
        )
        self.assertEqual(rows[-1]["retry_disposition"], "STOP_RATE_LIMITED")
        self.assertEqual(run.sources[0].status, "BLOCKED")
        self.assertIn("RATE_LIMIT_RETRY_EXHAUSTED", run.sources[0].limitations)

    def test_rate_limit_honors_bounded_retry_after(self) -> None:
        connector = ScriptedConnector(
            {"boursa_current": ["rate_retry_after", "qualified"]}
        )
        sleeps: list[float] = []
        with tempfile.TemporaryDirectory() as directory:
            self.run_one(connector, directory, sleeper=sleeps.append)
            rows = [
                json.loads(line)
                for line in (Path(directory) / "source_attempts.jsonl")
                .read_text()
                .splitlines()
            ]
        self.assertEqual(sleeps, [7.0])
        self.assertEqual(rows[0]["retry_delay_seconds"], 7.0)
        self.assertEqual(rows[0]["retry_after_seconds"], 7.0)
        self.assertNotIn("RATE_LIMIT_RETRY_AFTER_UNAVAILABLE", rows[0]["limitations"])

    def test_retry_after_beyond_remaining_wall_budget_defers_without_sleep(self) -> None:
        connector = ScriptedConnector(default="rate_retry_after")
        sleeps: list[float] = []
        with tempfile.TemporaryDirectory() as directory:
            orchestrator = SourceSearchOrchestrator(
                catalog=self.catalog,
                strategy_path=self.strategy_path,
                connector=connector,
                clock=FixedClock(),
                sleeper=sleeps.append,
            )
            orchestrator.policy = replace(orchestrator.policy, max_wall_seconds=5)
            run = orchestrator.run(
                run_id="retry-after-budget",
                decision_at=DECISION,
                attempt_log_path=Path(directory) / "source_attempts.jsonl",
                source_ids=["boursa_current"],
            )
            row = json.loads(
                (Path(directory) / "source_attempts.jsonl").read_text()
            )
        self.assertEqual(len(connector.calls), 1)
        self.assertEqual(sleeps, [])
        self.assertEqual(row["retry_after_seconds"], 7.0)
        self.assertEqual(row["retry_delay_seconds"], 0.0)
        self.assertEqual(row["retry_disposition"], "STOP_RETRY_BUDGET")
        self.assertIn(
            "RETRY_DELAY_EXCEEDS_REMAINING_WALL_BUDGET",
            run.sources[0].limitations,
        )

    def test_404_and_empty_bodies_are_not_explicit_zero_results(self) -> None:
        for kind in ("notfound", "empty"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                connector = ScriptedConnector(default=kind)
                run = self.run_one(connector, directory, run_id=f"not-zero-{kind}")
                self.assertEqual(run.sources[0].status, "ERROR")
                self.assertNotIn("boursa_current", dict(run.final_watermarks))
                self.assertNotIn(
                    "FOUR_DISTINCT_ZERO_RESULT_STRATEGIES",
                    run.sources[0].limitations,
                )

    def test_connector_exception_is_isolated_and_other_source_completes(self) -> None:
        connector = ScriptedConnector(
            {"boursa_current": [RuntimeError("boom")] * 12, "reuters_middle_east": ["qualified"]}
        )
        with tempfile.TemporaryDirectory() as directory:
            run = self.run_one(
                connector,
                directory,
                source_ids=["boursa_current", "reuters_middle_east"],
            )
        statuses = {item.source_id: item.status for item in run.sources}
        self.assertEqual(statuses["boursa_current"], "ERROR")
        self.assertEqual(statuses["reuters_middle_east"], "QUALIFIED")
        self.assertEqual(run.status, "DEGRADED")

    def test_raw_capture_stops_for_parser_and_incremental_watermark_is_preserved(self) -> None:
        prior = DECISION - timedelta(days=7)
        connector = ScriptedConnector(default="raw")
        with tempfile.TemporaryDirectory() as directory:
            run = self.run_one(connector, directory, watermarks={"boursa_current": prior})
            row = json.loads((Path(directory) / "source_attempts.jsonl").read_text())
        prior_kuwait = prior.astimezone(KUWAIT).isoformat()
        self.assertEqual(row["window_from"], prior_kuwait)
        self.assertEqual(run.sources[0].watermark_before, prior_kuwait)
        self.assertEqual(dict(run.final_watermarks)["boursa_current"], prior_kuwait)
        self.assertEqual(run.sources[0].status, "CAPTURED_PENDING_PARSER")

    def test_capture_after_decision_remains_raw_pending_parser_point_in_time(self) -> None:
        class LateRawConnector:
            def capture(self, request: CaptureRequest) -> CaptureResult:
                captured_at = DECISION + timedelta(seconds=1)
                return replace(
                    result(request, "raw"),
                    attempted_at=captured_at,
                    observed_at=captured_at,
                )

        with tempfile.TemporaryDirectory() as directory:
            run = self.run_one(LateRawConnector(), directory)
            row = json.loads(
                (Path(directory) / "source_attempts.jsonl").read_text()
            )
        self.assertEqual(run.sources[0].status, "CAPTURED_PENDING_PARSER")
        self.assertEqual(row["retry_disposition"], "STOP_CAPTURE_PENDING_PARSER")
        self.assertIn(
            "CAPTURE_TIMESTAMP_REQUIRES_PARSER_POINT_IN_TIME_VALIDATION",
            row["limitations"],
        )
        self.assertIn(
            "PARSER_MUST_ENFORCE_POINT_IN_TIME_PUBLICATION_CUTOFF",
            run.limitations,
        )

    def test_attempt_ledger_is_exact_hash_chained_append_only_and_schema_valid(self) -> None:
        connector = ScriptedConnector(default="qualified")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source_attempts.jsonl"
            run = self.run_one(connector, directory)
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            schema = json.loads((ROOT / "schemas" / "source-attempt.schema.json").read_text())
            for row in rows:
                self.assertEqual(set(row), set(schema["required"]))
            self.assertEqual(rows[0]["previous_attempt_hash"], "0" * 64)
            self.assertEqual(run.first_attempt_hash, rows[0]["attempt_hash"])
            artifact = Path(directory) / rows[0]["artifact_path"]
            self.assertEqual(artifact.read_bytes(), b'{"items":[1]}')
            self.assertEqual(len(artifact.read_bytes()), rows[0]["content_bytes"])
            with self.assertRaisesRegex(ValueError, "never overwritten"):
                AppendOnlyAttemptLedger(path, "second-run")

    def test_persisted_source_search_validator_rehashes_ledger_and_raw(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = self.run_one(ScriptedConnector(default="qualified"), directory)
            (root / "source_search_run.json").write_bytes(
                canonical_json_bytes(run.to_dict())
            )
            validated = validate_source_search_run(
                root,
                schema_root=ROOT / "schemas",
            )
            self.assertEqual(validated.report, run.to_dict())
            self.assertEqual(len(validated.attempt_rows), 1)
            self.assertEqual(
                validated.artifact_hashes,
                ((validated.attempt_rows[0]["artifact_path"], validated.attempt_rows[0]["content_sha256"]),),
            )

    def test_persisted_source_search_validator_rejects_report_or_raw_tamper(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = self.run_one(ScriptedConnector(default="qualified"), directory)
            report_path = root / "source_search_run.json"
            report = run.to_dict()
            report_path.write_bytes(canonical_json_bytes(report))
            rows = validate_source_search_run(root, schema_root=ROOT / "schemas").attempt_rows
            artifact = root / rows[0]["artifact_path"]
            artifact.write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "artifact bytes mismatch"):
                validate_source_search_run(root, schema_root=ROOT / "schemas")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = self.run_one(ScriptedConnector(default="qualified"), directory)
            report = run.to_dict()
            report["attempt_ledger"]["network_attempt_count"] = 2
            (root / "source_search_run.json").write_bytes(canonical_json_bytes(report))
            with self.assertRaisesRegex(ValueError, "attempt counts do not reconcile"):
                validate_source_search_run(root, schema_root=ROOT / "schemas")

    def test_persisted_validator_rejects_self_rehashed_timestamp_forgery(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = self.run_one(
                ScriptedConnector(default="qualified"),
                directory,
                run_id="forged-timestamp",
            )
            ledger_path = root / "source_attempts.jsonl"
            row = json.loads(ledger_path.read_text())
            row["completed_at"] = "2030-01-01T00:00:00+03:00"
            unhashed = dict(row)
            unhashed.pop("attempt_hash")
            row["attempt_hash"] = hash_json(unhashed)
            ledger_path.write_bytes(canonical_json_bytes(row))
            report = run.to_dict()
            ledger_bytes = ledger_path.read_bytes()
            report["attempt_ledger"].update(
                {
                    "sha256": sha256_bytes(ledger_bytes),
                    "first_attempt_hash": row["attempt_hash"],
                    "last_attempt_hash": row["attempt_hash"],
                }
            )
            (root / "source_search_run.json").write_bytes(canonical_json_bytes(report))
            with self.assertRaisesRegex(ValueError, "wall budget|declared wall"):
                validate_source_search_run(root, schema_root=ROOT / "schemas")

    def test_persisted_validator_accepts_reconciled_terminal_states(self) -> None:
        for kind, expected in (
            ("qualified", "QUALIFIED"),
            ("zero", "ZERO_RESULT"),
            ("blocked", "BLOCKED"),
            ("raw", "CAPTURED_PENDING_PARSER"),
            ("rate", "BLOCKED"),
            ("timeout", "ERROR"),
        ):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                run = self.run_one(
                    ScriptedConnector(default=kind),
                    directory,
                    run_id=f"valid-{kind}",
                )
                (root / "source_search_run.json").write_bytes(
                    canonical_json_bytes(run.to_dict())
                )
                validated = validate_source_search_run(
                    root,
                    schema_root=ROOT / "schemas",
                )
            self.assertEqual(validated.report["sources"][0]["status"], expected)

    def test_persisted_validator_accepts_pre_attempt_wall_budget_stop(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = SourceSearchOrchestrator(
                catalog=self.catalog,
                strategy_path=self.strategy_path,
                connector=ScriptedConnector(default="qualified"),
                clock=WallBudgetClock(),
                sleeper=lambda _seconds: None,
            ).run(
                run_id="valid-wall-budget-stop",
                decision_at=DECISION,
                attempt_log_path=root / "source_attempts.jsonl",
                source_ids=["boursa_current"],
            )
            (root / "source_search_run.json").write_bytes(
                canonical_json_bytes(run.to_dict())
            )
            validated = validate_source_search_run(
                root,
                schema_root=ROOT / "schemas",
            )
        self.assertEqual(validated.report["status"], "FAILED")
        self.assertEqual(validated.report["attempt_ledger"]["row_count"], 0)

    def test_persisted_validator_rejects_forged_source_id_wave_and_status(self) -> None:
        for variant in ("source_id", "wave", "status"):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                run = self.run_one(
                    ScriptedConnector(default="qualified"),
                    directory,
                    run_id=f"forged-{variant}",
                )
                report = run.to_dict()
                source = report["sources"][0]
                official = report["waves"][0]
                structured = report["waves"][2]
                if variant == "source_id":
                    source["source_id"] = "forged_source"
                    official["source_ids"] = ["forged_source"]
                    report["watermarks"]["final"] = {
                        "forged_source": report["decision_at"]
                    }
                elif variant == "wave":
                    source["wave_id"] = structured["wave_id"]
                    official.update(
                        status="EMPTY",
                        source_ids=[],
                        attempt_count=0,
                    )
                    structured.update(
                        status="COMPLETE",
                        source_ids=[source["source_id"]],
                        attempt_count=1,
                    )
                else:
                    source["status"] = "BLOCKED"
                    official.update(
                        status="DEGRADED",
                        degraded_source_ids=[source["source_id"]],
                    )
                    report["status"] = "DEGRADED"
                (root / "source_search_run.json").write_bytes(
                    canonical_json_bytes(report)
                )
                with self.assertRaisesRegex(
                    ValueError,
                    "unreported source|wave does not match|final status contradicts",
                ):
                    validate_source_search_run(root, schema_root=ROOT / "schemas")

    def test_persisted_validator_rejects_per_source_and_wave_counter_swap(self) -> None:
        connector = ScriptedConnector(
            {
                "boursa_current": ["timeout", "qualified"],
                "reuters_middle_east": ["qualified"],
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = self.run_one(
                connector,
                directory,
                run_id="forged-counters",
                source_ids=["boursa_current", "reuters_middle_east"],
            )
            report = run.to_dict()
            sources = {row["source_id"]: row for row in report["sources"]}
            waves = {row["wave_id"]: row for row in report["waves"]}
            sources["boursa_current"]["attempt_count"] = 1
            sources["reuters_middle_east"]["attempt_count"] = 2
            waves["OFFICIAL_AND_REGULATORY"]["attempt_count"] = 1
            waves["STRUCTURED_AND_EDITORIAL"]["attempt_count"] = 2
            (root / "source_search_run.json").write_bytes(
                canonical_json_bytes(report)
            )
            with self.assertRaisesRegex(ValueError, "source report attempt_count"):
                validate_source_search_run(root, schema_root=ROOT / "schemas")

    def test_persisted_validator_rejects_self_rehashed_impossible_disposition(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = self.run_one(
                ScriptedConnector(default="qualified"),
                directory,
                run_id="forged-disposition",
            )
            report = run.to_dict()
            ledger_path = root / "source_attempts.jsonl"
            row = json.loads(ledger_path.read_text(encoding="utf-8"))
            row["retry_disposition"] = "STOP_HARD_BLOCK"
            unhashed = dict(row)
            unhashed.pop("attempt_hash")
            row["attempt_hash"] = hash_json(unhashed)
            ledger_bytes = canonical_json_bytes(row)
            ledger_path.write_bytes(ledger_bytes)
            report["attempt_ledger"].update(
                sha256=sha256_bytes(ledger_bytes),
                first_attempt_hash=row["attempt_hash"],
                last_attempt_hash=row["attempt_hash"],
            )
            (root / "source_search_run.json").write_bytes(
                canonical_json_bytes(report)
            )
            with self.assertRaisesRegex(ValueError, "STOP_HARD_BLOCK contradicts"):
                validate_source_search_run(root, schema_root=ROOT / "schemas")

    def test_ledger_or_attempt_owned_artifact_tamper_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source_attempts.jsonl"
            self.run_one(ScriptedConnector(default="qualified"), directory)
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            artifact = Path(directory) / rows[0]["artifact_path"]
            artifact.write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "artifact bytes mismatch"):
                AppendOnlyAttemptLedger.open_for_verify(path, "orchestrator-test").verify()

    def test_attempt_raw_directory_symlink_is_not_followed(self) -> None:
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            path = Path(directory) / "source_attempts.jsonl"
            ledger = AppendOnlyAttemptLedger(path, "symlink-test")
            try:
                (Path(directory) / "raw").symlink_to(outside, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("directory symlinks are unavailable")
            with self.assertRaisesRegex(ValueError, "symlink|non-directory"):
                ledger.persist_content(source_id="boursa_current", content=b"secret")
            self.assertEqual(list(Path(outside).iterdir()), [])

    def test_attempt_ledger_rejects_symlink_leaf_and_parent(self) -> None:
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            root = Path(directory)
            outside_root = Path(outside)
            real = outside_root / "real.jsonl"
            real.write_text("", encoding="utf-8")
            leaf = root / "leaf.jsonl"
            parent = root / "parent"
            try:
                leaf.symlink_to(real)
                parent.symlink_to(outside_root, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks are unavailable")
            with self.assertRaisesRegex(ValueError, "unreadable"):
                AppendOnlyAttemptLedger.open_for_verify(leaf, "symlink-leaf")
            with self.assertRaisesRegex(ValueError, "symlink"):
                AppendOnlyAttemptLedger(parent / "attempts.jsonl", "symlink-parent")

    def test_search_run_schema_and_no_live_claims(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run = self.run_one(ScriptedConnector(default="qualified"), directory)
        schema = json.loads((ROOT / "schemas" / "source-search-run.schema.json").read_text())
        payload = run.to_dict()
        self.assertEqual(set(payload), set(schema["required"]))
        self.assertTrue(all(value is False for value in payload["claim_boundaries"].values()))

    def test_default_plan_reserves_all_waves_within_fifty_domains(self) -> None:
        connector = ScriptedConnector(default="blocked")
        with tempfile.TemporaryDirectory() as directory:
            run = SourceSearchOrchestrator(
                catalog=self.catalog,
                strategy_path=self.strategy_path,
                connector=connector,
                clock=FixedClock(),
                sleeper=lambda _seconds: None,
            ).run(
                run_id="all-domain-routes",
                decision_at=DECISION,
                attempt_log_path=Path(directory) / "source_attempts.jsonl",
            )
        coverage = run.to_dict()["domain_coverage"]
        self.assertGreaterEqual(coverage["catalog_registrable_domain_count"], 50)
        self.assertEqual(coverage["attempted_registrable_domain_count"], 50)
        self.assertLess(coverage["attempted_registrable_domain_count"], len(connector.calls))
        self.assertIsNone(run.budget_stop_reason)
        self.assertEqual(coverage["selection_mode"], "DEFAULT_FAIR_NETWORK")
        self.assertTrue(coverage["global_target_applicable"])
        self.assertTrue(coverage["global_target_met"])
        community = next(
            wave
            for wave in run.waves
            if wave.wave_id == "COMMUNITY_ARCHIVE_AND_ROUTING"
        )
        self.assertGreaterEqual(community.attempt_count, 4)
        self.assertTrue(
            any(call.source_id.startswith("telegram_") for call in connector.calls)
        )

    def test_explicit_subset_reports_global_target_not_applicable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run = self.run_one(ScriptedConnector(default="qualified"), directory)
        coverage = run.to_dict()["domain_coverage"]
        self.assertEqual(run.status, "COMPLETE")
        self.assertEqual(coverage["selection_mode"], "EXPLICIT_SOURCE_SUBSET")
        self.assertFalse(coverage["global_target_applicable"])
        self.assertIsNone(coverage["global_target_met"])
        self.assertIn(
            "EXPLICIT_SOURCE_SUBSET_GLOBAL_DOMAIN_TARGET_NOT_APPLICABLE",
            run.limitations,
        )

    def test_request_budget_stops_before_connector_call_beyond_limit(self) -> None:
        connector = ScriptedConnector(default="timeout")
        with tempfile.TemporaryDirectory() as directory:
            orchestrator = SourceSearchOrchestrator(
                catalog=self.catalog,
                strategy_path=self.strategy_path,
                connector=connector,
                clock=FixedClock(),
                sleeper=lambda _seconds: None,
            )
            orchestrator.policy = replace(
                orchestrator.policy,
                max_requests=2,
                max_distinct_registrable_domains=50,
            )
            run = orchestrator.run(
                run_id="request-budget",
                decision_at=DECISION,
                attempt_log_path=Path(directory) / "source_attempts.jsonl",
                source_ids=["boursa_current"],
            )
        self.assertEqual(len(connector.calls), 2)
        self.assertEqual(run.attempt_count, 2)
        self.assertEqual(run.budget_stop_reason, "MAX_REQUESTS_EXHAUSTED")

    def test_wall_budget_stops_before_first_over_budget_connector_call(self) -> None:
        connector = ScriptedConnector(default="qualified")
        with tempfile.TemporaryDirectory() as directory:
            run = SourceSearchOrchestrator(
                catalog=self.catalog,
                strategy_path=self.strategy_path,
                connector=connector,
                clock=WallBudgetClock(),
                sleeper=lambda _seconds: None,
            ).run(
                run_id="wall-budget",
                decision_at=DECISION,
                attempt_log_path=Path(directory) / "source_attempts.jsonl",
                source_ids=["boursa_current"],
            )
        self.assertEqual(connector.calls, [])
        self.assertEqual(run.attempt_count, 0)
        self.assertEqual(run.attempted_registrable_domains, ())
        self.assertEqual(run.budget_stop_reason, "MAX_WALL_SECONDS_EXHAUSTED")

    def test_registrable_domains_do_not_count_subdomains_or_channels_as_sites(self) -> None:
        self.assertEqual(registrable_domain("docs.boursakuwait.com.kw"), "boursakuwait.com.kw")
        self.assertEqual(registrable_domain("https://t.me/s/channel"), "t.me")
        self.assertEqual(registrable_domain("sa.investing.com"), "investing.com")

    def test_foreign_redirect_is_rejected_without_persisting_foreign_content(self) -> None:
        connector = ScriptedConnector(default=("qualified", "https://evil.example/steal"))
        with tempfile.TemporaryDirectory() as directory:
            run = self.run_one(connector, directory)
            rows = [json.loads(line) for line in (Path(directory) / "source_attempts.jsonl").read_text().splitlines()]
        self.assertEqual(run.sources[0].status, "ERROR")
        self.assertTrue(all(row["content_sha256"] is None for row in rows))
        self.assertTrue(all(row["error_code"] == "CONNECTOR_INTERNAL_ERROR" for row in rows))

    def test_injected_connector_contract_mismatch_is_not_persisted(self) -> None:
        variants = {
            "access": lambda request: replace(
                result(request, "qualified"), access_mode="PUBLIC_DOWNLOAD"
            ),
            "capture": lambda request: replace(
                result(request, "qualified"), capture_kind="RAW_DOWNLOAD"
            ),
            "roles": lambda request: replace(
                result(request, "qualified"), roles_observed=("UNEXPECTED_ROLE",)
            ),
            "oversized": lambda request: replace(
                result(request, "qualified"), content=b"x" * (request.max_bytes + 1)
            ),
        }

        for name, factory in variants.items():
            class InvalidConnector:
                def capture(self, request: CaptureRequest) -> CaptureResult:
                    return factory(request)

            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                orchestrator = SourceSearchOrchestrator(
                    catalog=self.catalog,
                    strategy_path=self.strategy_path,
                    connector=InvalidConnector(),
                    clock=FixedClock(),
                    sleeper=lambda _seconds: None,
                )
                orchestrator.policy = replace(orchestrator.policy, max_requests=1)
                run = orchestrator.run(
                    run_id=f"invalid-{name}",
                    decision_at=DECISION,
                    attempt_log_path=Path(directory) / "source_attempts.jsonl",
                    source_ids=["boursa_current"],
                )
                row = json.loads(
                    (Path(directory) / "source_attempts.jsonl").read_text()
                )
                raw_root = Path(directory) / "raw"
                raw_files = list(raw_root.rglob("*.bin")) if raw_root.exists() else []
            self.assertEqual(run.status, "DEGRADED")
            self.assertEqual(row["error_code"], "CONNECTOR_INTERNAL_ERROR")
            self.assertIsNone(row["artifact_path"])
            self.assertEqual(raw_files, [])

    def test_sleeper_failure_stops_retry_but_not_sibling_source(self) -> None:
        connector = ScriptedConnector(
            {
                "boursa_current": ["timeout", "qualified"],
                "reuters_middle_east": ["qualified"],
            }
        )

        def broken_sleeper(_seconds: float) -> None:
            raise RuntimeError("chaos")

        with tempfile.TemporaryDirectory() as directory:
            run = self.run_one(
                connector,
                directory,
                sleeper=broken_sleeper,
                source_ids=["boursa_current", "reuters_middle_east"],
            )
            ledger_rows = [
                json.loads(line)
                for line in (Path(directory) / "source_attempts.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
        statuses = {item.source_id: item for item in run.sources}
        self.assertEqual(statuses["boursa_current"].status, "ERROR")
        self.assertIn(
            "SLEEPER_FAILURE_STOPPED_RETRY",
            statuses["boursa_current"].limitations,
        )
        self.assertEqual(statuses["reuters_middle_east"].status, "QUALIFIED")
        self.assertEqual(
            [call.source_id for call in connector.calls],
            ["boursa_current", "reuters_middle_east"],
        )
        self.assertEqual(run.attempt_count, 2)
        self.assertEqual(run.ledger_event_count, 3)
        self.assertEqual(
            [row["event_type"] for row in ledger_rows],
            ["CAPTURE_ATTEMPT", "RETRY_CONTROL_EVENT", "CAPTURE_ATTEMPT"],
        )
        terminal = ledger_rows[1]
        self.assertEqual(terminal["error_code"], "SLEEPER_FAILURE")
        self.assertEqual(terminal["retry_disposition"], "STOP_SLEEPER_FAILURE")
        self.assertEqual(terminal["previous_attempt_hash"], ledger_rows[0]["attempt_hash"])
        self.assertEqual(ledger_rows[2]["previous_attempt_hash"], terminal["attempt_hash"])
        self.assertIn("SLEEPER_FAILURE_STOPPED_RETRY", terminal["limitations"])


if __name__ == "__main__":
    unittest.main()
