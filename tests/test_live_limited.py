from __future__ import annotations

from contextlib import redirect_stdout
from datetime import datetime, timezone
from email.message import Message
from io import BytesIO, StringIO
import json
import os
from pathlib import Path
import signal
import stat
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib import request as urllib_request
from urllib.response import addinfourl

import kubo.live_limited as live_limited
from kubo.cli_v3 import main as cli_main
from kubo.ingestion import _AllowlistRedirectHandler
from kubo.live_limited import stage_limited_live_run
from kubo.source_network import SourceNetworkCatalog, SourceNetworkRunValidator, validate_live_probe


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "parser_contract"


def _plan(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "run_id": "staged-live-limited-test",
        "product_id": "next_session_rank",
        "scope": "NAMED_SECURITIES",
        "decision_delay_minutes": 0,
        "budget": {
            "max_requests": 2,
            "max_raw_bytes": 1000000,
            "max_wall_seconds": 60,
        },
        "binding": {
            "security_code": "101",
            "ticker": "AAA",
            "isin": "KW0EQ0000101",
            "valid_from": "2020-01-01",
            "valid_to": None,
        },
        "official_capture": {
            "connector": "file",
            "source_id": "boursa_current",
            "source_url": "https://www.boursakuwait.com.kw/en/",
            "roles_observed": ["IDENTITY_REFERENCE"],
            "access_mode": "USER_EXPORT",
            "capture_kind": "USER_EXPORT",
            "resource_path": "boursa_identity.html",
            "timeout_seconds": 5,
            "max_bytes": 500000,
        },
        "secondary_capture": {
            "connector": "file",
            "source_id": "investing_history",
            "source_url": "https://www.investing.com/equities/generated-test-historical-data",
            "roles_observed": ["MARKET_DISCOVERY", "PRICE_HISTORY"],
            "access_mode": "USER_EXPORT",
            "capture_kind": "USER_EXPORT",
            "resource_path": "investing_history.html",
            "timeout_seconds": 5,
            "max_bytes": 500000,
        },
    }
    payload.update(overrides)
    return payload


class LiveLimitedTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = SourceNetworkCatalog(ROOT / "config")

    def test_staged_limited_run_captures_probe_materializes_and_validates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            plan_path = workspace / "plan.json"
            plan_path.write_text(json.dumps(_plan()), encoding="utf-8")
            output_root = workspace / "run"
            report = stage_limited_live_run(
                plan_path=plan_path,
                output_root=output_root,
                fixture_root=FIXTURES,
                catalog=self.catalog,
            )
            self.assertEqual(report["status"], "PLUMBING_PASS")
            self.assertEqual(report["execution_mode"], "FIXTURE_PLUMBING")
            self.assertEqual(report["capture"]["status"], "COMPLETE")
            self.assertIsNone(report["access_probe"])
            self.assertEqual(
                report["fixture_receipt"]["status"], "PLUMBING_CAPTURED"
            )
            self.assertEqual(report["materialized"]["status"], "PASS")
            self.assertFalse(
                report["claim_boundaries"]["staged_run_upgrades_sources_to_live_operational"]
            )
            self.assertFalse((output_root / "access_probe.json").exists())
            fixture_receipt_path = output_root / "fixture_plumbing_receipt.json"
            self.assertTrue(fixture_receipt_path.is_file())
            fixture_receipt = json.loads(
                fixture_receipt_path.read_text(encoding="utf-8")
            )
            self.assertEqual(fixture_receipt["receipt_type"], "FIXTURE_PLUMBING")
            self.assertTrue(
                all(row["http_status"] is None for row in fixture_receipt["sources"])
            )
            self.assertFalse(
                fixture_receipt["claim_boundaries"][
                    "fixture_receipt_is_live_access_probe"
                ]
            )
            self.assertTrue((output_root / "parser_plan.json").is_file())
            self.assertTrue((output_root / "research_run.json").is_file())
            self.assertEqual(report["usage_http_requests"], 0)
            self.assertEqual(
                report["materialized"]["materialized_run"], str(output_root)
            )
            parser_plan = json.loads(
                (output_root / "parser_plan.json").read_text(encoding="utf-8")
            )
            research_run = json.loads(
                (output_root / "research_run.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                parser_plan["usage_wall_seconds"], report["usage_wall_seconds"]
            )
            self.assertEqual(
                research_run["usage"]["wall_seconds"],
                report["usage_wall_seconds"],
            )
            self.assertEqual(research_run["usage"]["requests"], 0)
            decision_at = datetime.fromisoformat(parser_plan["decision_at"])
            observed_at = max(
                datetime.fromisoformat(row["observed_at"])
                for row in fixture_receipt["sources"]
            )
            self.assertGreaterEqual(decision_at, observed_at)
            self.assertLessEqual(decision_at, datetime.now(timezone.utc))
            self.assertEqual(
                validate_live_probe(fixture_receipt_path, self.catalog)["status"],
                "BLOCKED",
            )
            validation = SourceNetworkRunValidator(
                output_root,
                self.catalog,
                "next_session_rank",
            ).validate()
            self.assertEqual(validation.status, "PARTIAL")
            self.assertFalse(
                any(
                    item.name.startswith(".kubo-stage-live-limited-")
                    for item in workspace.iterdir()
                )
            )

    def test_cli_stage_live_limited_runs_fixture_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            plan_path = workspace / "plan.json"
            plan_path.write_text(json.dumps(_plan()), encoding="utf-8")
            output = StringIO()
            with redirect_stdout(output):
                code = cli_main(
                    [
                        "--project-root",
                        str(ROOT),
                        "stage-live-limited",
                        "--plan",
                        str(plan_path),
                        "--fixture-root",
                        str(FIXTURES),
                        "--output-root",
                        str(workspace / "run"),
                    ]
                )
            report = json.loads(output.getvalue())
            self.assertEqual(code, 0)
            self.assertEqual(report["status"], "PLUMBING_PASS")

    def test_plan_loader_rejects_symlink_before_reading(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            target = workspace / "target.json"
            target.write_text(json.dumps(_plan()), encoding="utf-8")
            linked = workspace / "linked.json"
            linked.symlink_to(target)
            with patch("kubo.live_limited.os.read") as read:
                with self.assertRaisesRegex(ValueError, "non-symlink"):
                    live_limited._load_plan(linked)
            read.assert_not_called()

    def test_plan_loader_rejects_fifo_before_reading(self) -> None:
        if not hasattr(os, "mkfifo"):
            self.skipTest("FIFO creation is unavailable")
        with tempfile.TemporaryDirectory() as temporary:
            fifo = Path(temporary) / "plan.fifo"
            os.mkfifo(fifo)
            with patch("kubo.live_limited.os.read") as read:
                with self.assertRaisesRegex(ValueError, "regular non-symlink"):
                    live_limited._load_plan(fifo)
            read.assert_not_called()

    def test_plan_loader_rejects_oversized_file_before_reading(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            plan_path = Path(temporary) / "huge.json"
            plan_path.write_bytes(
                b"x" * (live_limited._MAX_STAGED_LIVE_PLAN_BYTES + 1)
            )
            with patch("kubo.live_limited.os.read") as read:
                with self.assertRaisesRegex(ValueError, "file-size limit"):
                    live_limited._load_plan(plan_path)
            read.assert_not_called()

    def test_non_empty_output_root_is_rejected_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            plan_path = workspace / "plan.json"
            plan_path.write_text(json.dumps(_plan()), encoding="utf-8")
            output_root = workspace / "run"
            output_root.mkdir()
            sentinel = output_root / "keep.txt"
            sentinel.write_text("untouched", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "output_root must not exist"):
                stage_limited_live_run(
                    plan_path=plan_path,
                    output_root=output_root,
                    fixture_root=FIXTURES,
                    catalog=self.catalog,
                )
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "untouched")
            self.assertEqual([item.name for item in output_root.iterdir()], ["keep.txt"])

    def test_existing_empty_output_root_is_rejected_for_atomic_publish(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            plan_path = workspace / "plan.json"
            plan_path.write_text(json.dumps(_plan()), encoding="utf-8")
            output_root = workspace / "run"
            output_root.mkdir()
            with self.assertRaisesRegex(ValueError, "output_root must not exist"):
                stage_limited_live_run(
                    plan_path=plan_path,
                    output_root=output_root,
                    fixture_root=FIXTURES,
                    catalog=self.catalog,
                )
            self.assertTrue(output_root.is_dir())
            self.assertEqual(list(output_root.iterdir()), [])

    def test_degraded_fixture_run_uses_fixture_receipt_not_live_probe(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            fixture_root = workspace / "fixtures"
            fixture_root.mkdir()
            (fixture_root / "boursa_identity.html").write_bytes(
                (FIXTURES / "boursa_identity.html").read_bytes()
            )
            plan_path = workspace / "plan.json"
            plan_path.write_text(json.dumps(_plan()), encoding="utf-8")
            output_root = workspace / "run"
            report = stage_limited_live_run(
                plan_path=plan_path,
                output_root=output_root,
                fixture_root=fixture_root,
                catalog=self.catalog,
            )
            self.assertEqual(report["status"], "CAPTURE_DEGRADED")
            self.assertIsNone(report["access_probe"])
            self.assertEqual(
                report["fixture_receipt"]["status"], "PLUMBING_DEGRADED"
            )
            self.assertFalse((output_root / "access_probe.json").exists())
            self.assertFalse((output_root / "parser_plan.json").exists())
            receipt = json.loads(
                (output_root / "fixture_plumbing_receipt.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertTrue(
                all(row["http_status"] is None for row in receipt["sources"])
            )

    def test_public_http_resource_path_is_optional_but_file_requires_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            public_plan = _plan()
            for slot in ("official_capture", "secondary_capture"):
                capture = dict(public_plan[slot])  # type: ignore[arg-type]
                capture.pop("resource_path")
                capture.update(
                    {
                        "connector": "public_http",
                        "access_mode": "PUBLIC_PAGE",
                        "capture_kind": "RAW_PAGE",
                    }
                )
                public_plan[slot] = capture
            public_plan["budget"] = {
                "max_requests": 4,
                "max_raw_bytes": 1000000,
                "max_wall_seconds": 60,
            }
            public_path = workspace / "public.json"
            public_path.write_text(json.dumps(public_plan), encoding="utf-8")
            occupied = workspace / "occupied"
            occupied.mkdir()
            (occupied / "sentinel").write_text("x", encoding="utf-8")
            # Reaching output preflight proves both public tasks validated
            # without a resource_path and avoids making a network request.
            with self.assertRaisesRegex(ValueError, "output_root must not exist"):
                stage_limited_live_run(
                    plan_path=public_path,
                    output_root=occupied,
                    catalog=self.catalog,
                )

            file_plan = _plan()
            official = dict(file_plan["official_capture"])  # type: ignore[arg-type]
            official.pop("resource_path")
            file_plan["official_capture"] = official
            file_path = workspace / "file.json"
            file_path.write_text(json.dumps(file_plan), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "file connector requires"):
                stage_limited_live_run(
                    plan_path=file_path,
                    output_root=workspace / "unused",
                    fixture_root=FIXTURES,
                    catalog=self.catalog,
                )

    def test_fractional_timeout_ceiling_cannot_evade_wall_budget(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            changed = _plan()
            changed["budget"] = {
                "max_requests": 2,
                "max_raw_bytes": 1000000,
                "max_wall_seconds": 10,
            }
            for slot in ("official_capture", "secondary_capture"):
                capture = dict(changed[slot])  # type: ignore[arg-type]
                capture["timeout_seconds"] = 5.1
                changed[slot] = capture
            path = workspace / "bad-budget.json"
            path.write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "timeout ceilings"):
                stage_limited_live_run(
                    plan_path=path,
                    output_root=workspace / "run",
                    fixture_root=FIXTURES,
                    catalog=self.catalog,
                )
            self.assertFalse((workspace / "run").exists())

    def test_public_budget_covers_robots_and_resources_before_network(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            changed = _plan()
            changed["budget"] = {
                "max_requests": 3,
                "max_raw_bytes": 1000000,
                "max_wall_seconds": 60,
            }
            for slot in ("official_capture", "secondary_capture"):
                capture = dict(changed[slot])  # type: ignore[arg-type]
                capture.update(
                    {
                        "connector": "public_http",
                        "access_mode": "PUBLIC_PAGE",
                        "capture_kind": "RAW_PAGE",
                        "resource_path": None,
                    }
                )
                changed[slot] = capture
            path = workspace / "insufficient-http-budget.json"
            path.write_text(json.dumps(changed), encoding="utf-8")
            with patch("kubo.live_limited._build_public_opener") as build_opener:
                with self.assertRaisesRegex(ValueError, "robots.txt and resource"):
                    stage_limited_live_run(
                        plan_path=path,
                        output_root=workspace / "run",
                        catalog=self.catalog,
                    )
            build_opener.assert_not_called()
            self.assertFalse((workspace / "run").exists())

    def test_opener_counts_robots_resource_and_recursive_redirects(self) -> None:
        class RedirectingHttpsHandler(urllib_request.BaseHandler):
            handler_order = 100

            def https_open(self, request):  # noqa: ANN001
                headers = Message()
                if request.host == "example.com":
                    headers["Location"] = (
                        "https://www.example.com" + request.selector
                    )
                    status = 302
                    body = b""
                else:
                    headers["Content-Type"] = "text/plain"
                    status = 200
                    body = b"ok"
                response = addinfourl(
                    BytesIO(body), headers, request.full_url, status
                )
                response.msg = "test status"
                return response

        budget = live_limited._HttpRequestBudget(
            max_requests=4,
            deadline=time.monotonic() + 10,
        )
        opener = urllib_request.build_opener(
            urllib_request.ProxyHandler({}),
            _AllowlistRedirectHandler(("example.com",)),
            RedirectingHttpsHandler(),
            live_limited._BudgetedHttpsRequestHandler(budget),
        )
        robots = opener.open("https://example.com/robots.txt", timeout=5)
        resource = opener.open("https://example.com/data", timeout=5)
        self.assertEqual(robots.geturl(), "https://www.example.com/robots.txt")
        self.assertEqual(resource.geturl(), "https://www.example.com/data")
        self.assertEqual(budget.requests, 4)

        with self.assertRaises(live_limited._CaptureBudgetExceeded) as raised:
            opener.open("https://example.com/final-redirect", timeout=5)
        self.assertEqual(raised.exception.reason_code, "REQUEST_BUDGET_EXCEEDED")
        self.assertEqual(budget.requests, 4)

    def test_hard_wall_interrupts_blocking_capture_work(self) -> None:
        started = time.monotonic()
        with self.assertRaises(live_limited._CaptureBudgetExceeded) as raised:
            with live_limited._hard_wall(started + 0.05):
                time.sleep(0.5)
        elapsed = time.monotonic() - started
        self.assertEqual(raised.exception.reason_code, "WALL_BUDGET_EXCEEDED")
        if (
            hasattr(signal, "SIGALRM")
            and threading.current_thread() is threading.main_thread()
        ):
            self.assertLess(elapsed, 0.3)

    def test_non_main_thread_rejects_before_output_setup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            plan_path = workspace / "plan.json"
            plan_path.write_text(json.dumps(_plan()), encoding="utf-8")
            errors: list[BaseException] = []

            def invoke() -> None:
                try:
                    stage_limited_live_run(
                        plan_path=plan_path,
                        output_root=workspace / "run",
                        fixture_root=FIXTURES,
                        catalog=self.catalog,
                    )
                except BaseException as exc:  # assertion captures fail-closed result
                    errors.append(exc)

            worker = threading.Thread(target=invoke)
            worker.start()
            worker.join(timeout=5)
            self.assertFalse(worker.is_alive())
            self.assertEqual(len(errors), 1)
            self.assertIsInstance(errors[0], ValueError)
            self.assertIn("main thread", str(errors[0]))
            self.assertFalse((workspace / "run").exists())
            self.assertFalse(
                any(
                    item.name.startswith(".kubo-stage-live-limited-")
                    for item in workspace.iterdir()
                )
            )

    def test_concurrent_thread_rejects_before_output_setup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            plan_path = workspace / "plan.json"
            plan_path.write_text(json.dumps(_plan()), encoding="utf-8")
            stop = threading.Event()
            worker = threading.Thread(target=stop.wait)
            worker.start()
            try:
                with self.assertRaisesRegex(ValueError, "single-threaded"):
                    stage_limited_live_run(
                        plan_path=plan_path,
                        output_root=workspace / "run",
                        fixture_root=FIXTURES,
                        catalog=self.catalog,
                    )
            finally:
                stop.set()
                worker.join(timeout=5)
            self.assertFalse(worker.is_alive())
            self.assertFalse((workspace / "run").exists())
            self.assertFalse(
                any(
                    item.name.startswith(".kubo-stage-live-limited-")
                    for item in workspace.iterdir()
                )
            )

    def test_existing_real_time_timer_is_not_replaced(self) -> None:
        if not hasattr(signal, "ITIMER_REAL"):
            self.skipTest("ITIMER_REAL is unavailable")
        if signal.getitimer(signal.ITIMER_REAL)[0] > 0:
            self.skipTest("test process already owns a real-time timer")
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            plan_path = workspace / "plan.json"
            plan_path.write_text(json.dumps(_plan()), encoding="utf-8")
            signal.setitimer(signal.ITIMER_REAL, 10)
            try:
                with self.assertRaisesRegex(ValueError, "existing real-time timer"):
                    stage_limited_live_run(
                        plan_path=plan_path,
                        output_root=workspace / "run",
                        fixture_root=FIXTURES,
                        catalog=self.catalog,
                    )
            finally:
                signal.setitimer(signal.ITIMER_REAL, 0)
            self.assertFalse((workspace / "run").exists())
            self.assertFalse(
                any(
                    item.name.startswith(".kubo-stage-live-limited-")
                    for item in workspace.iterdir()
                )
            )

    def test_decision_delay_zero_is_allowed_and_positive_delay_is_applied(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            changed = _plan(decision_delay_minutes=1)
            changed["budget"] = {
                "max_requests": 2,
                "max_raw_bytes": 1000000,
                "max_wall_seconds": 75,
            }
            path = workspace / "delayed.json"
            path.write_text(json.dumps(changed), encoding="utf-8")
            with patch("kubo.live_limited.time.sleep") as delay:
                report = stage_limited_live_run(
                    plan_path=path,
                    output_root=workspace / "run",
                    fixture_root=FIXTURES,
                    catalog=self.catalog,
                )
            self.assertEqual(report["status"], "PLUMBING_PASS")
            delay.assert_called_once_with(60)

    def test_slow_materializer_hits_full_wall_without_publishing_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            changed = _plan()
            changed["budget"] = {
                "max_requests": 2,
                "max_raw_bytes": 1000000,
                "max_wall_seconds": 1,
            }
            for slot in ("official_capture", "secondary_capture"):
                capture = dict(changed[slot])  # type: ignore[arg-type]
                capture["timeout_seconds"] = 0.1
                changed[slot] = capture
            path = workspace / "slow-materializer.json"
            path.write_text(json.dumps(changed), encoding="utf-8")

            def slow_materializer(**_kwargs):
                time.sleep(2)
                self.fail("the full-run wall failed to interrupt materialization")

            started = time.monotonic()
            with patch(
                "kubo.live_limited.materialize_parser_run",
                side_effect=slow_materializer,
            ):
                report = stage_limited_live_run(
                    plan_path=path,
                    output_root=workspace / "run",
                    fixture_root=FIXTURES,
                    catalog=self.catalog,
                )
            self.assertEqual(report["status"], "CAPTURE_DEGRADED")
            self.assertEqual(report["reason_code"], "WALL_BUDGET_EXCEEDED")
            self.assertLess(time.monotonic() - started, 1.8)
            self.assertFalse((workspace / "run").exists())
            self.assertFalse(
                any(
                    item.name.startswith(".kubo-stage-live-limited-")
                    for item in workspace.iterdir()
                )
            )

    def test_slow_second_validation_cannot_publish_or_underreport(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            changed = _plan()
            changed["budget"] = {
                "max_requests": 2,
                "max_raw_bytes": 1000000,
                "max_wall_seconds": 1,
            }
            for slot in ("official_capture", "secondary_capture"):
                capture = dict(changed[slot])  # type: ignore[arg-type]
                capture["timeout_seconds"] = 0.1
                changed[slot] = capture
            plan_path = workspace / "slow-validation.json"
            plan_path.write_text(json.dumps(changed), encoding="utf-8")
            original_validate = SourceNetworkRunValidator.validate
            calls = 0

            def delayed_second_validation(validator):
                nonlocal calls
                calls += 1
                if calls == 2:
                    time.sleep(2)
                return original_validate(validator)

            with patch.object(
                SourceNetworkRunValidator,
                "validate",
                new=delayed_second_validation,
            ):
                report = stage_limited_live_run(
                    plan_path=plan_path,
                    output_root=workspace / "run",
                    fixture_root=FIXTURES,
                    catalog=self.catalog,
                )
            self.assertEqual(calls, 2)
            self.assertEqual(report["status"], "CAPTURE_DEGRADED")
            self.assertEqual(report["reason_code"], "WALL_BUDGET_EXCEEDED")
            self.assertFalse((workspace / "run").exists())
            self.assertFalse(
                any(
                    item.name.startswith(".kubo-stage-live-limited-")
                    for item in workspace.iterdir()
                )
            )

    def test_abort_disarms_wall_before_slow_directory_clear(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            changed = _plan()
            changed["budget"] = {
                "max_requests": 2,
                "max_raw_bytes": 1000000,
                "max_wall_seconds": 1,
            }
            for slot in ("official_capture", "secondary_capture"):
                capture = dict(changed[slot])  # type: ignore[arg-type]
                capture["timeout_seconds"] = 0.1
                changed[slot] = capture
            plan_path = workspace / "slow-clear.json"
            plan_path.write_text(json.dumps(changed), encoding="utf-8")
            original_clear = live_limited._clear_directory_fd
            clear_saw_disarmed_timer = False
            clear_calls = 0

            def fail_before_deadline(**_kwargs):
                time.sleep(0.2)
                raise live_limited._CaptureBudgetExceeded(
                    "REQUEST_BUDGET_EXCEEDED"
                )

            def slow_clear(directory_fd):  # noqa: ANN001
                nonlocal clear_calls, clear_saw_disarmed_timer
                clear_calls += 1
                clear_saw_disarmed_timer = (
                    clear_saw_disarmed_timer
                    or signal.getitimer(signal.ITIMER_REAL)[0] == 0
                )
                if clear_calls == 1:
                    time.sleep(1.05)
                return original_clear(directory_fd)

            started = time.monotonic()
            with patch(
                "kubo.live_limited.materialize_parser_run",
                side_effect=fail_before_deadline,
            ), patch(
                "kubo.live_limited._clear_directory_fd",
                new=slow_clear,
            ):
                report = stage_limited_live_run(
                    plan_path=plan_path,
                    output_root=workspace / "run",
                    fixture_root=FIXTURES,
                    catalog=self.catalog,
                )
            self.assertTrue(clear_saw_disarmed_timer)
            self.assertGreater(time.monotonic() - started, 1.0)
            self.assertEqual(report["status"], "CAPTURE_DEGRADED")
            self.assertEqual(report["reason_code"], "REQUEST_BUDGET_EXCEEDED")
            self.assertEqual(report["usage_wall_seconds"], 1)
            self.assertFalse((workspace / "run").exists())
            self.assertFalse(
                any(
                    item.name.startswith(".kubo-stage-live-limited-")
                    for item in workspace.iterdir()
                )
            )

    def test_cutoff_disarms_wall_before_slow_lock_release(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            changed = _plan()
            changed["budget"] = {
                "max_requests": 2,
                "max_raw_bytes": 1000000,
                "max_wall_seconds": 1,
            }
            for slot in ("official_capture", "secondary_capture"):
                capture = dict(changed[slot])  # type: ignore[arg-type]
                capture["timeout_seconds"] = 0.1
                changed[slot] = capture
            plan_path = workspace / "slow-release.json"
            plan_path.write_text(json.dumps(changed), encoding="utf-8")
            output_root = workspace / "run"
            original_release = live_limited._OutputTransaction._release_lock
            release_saw_disarmed_timer = False

            def slow_release(transaction):  # noqa: ANN001
                nonlocal release_saw_disarmed_timer
                release_saw_disarmed_timer = (
                    signal.getitimer(signal.ITIMER_REAL)[0] == 0
                )
                time.sleep(1.05)
                return original_release(transaction)

            started = time.monotonic()
            with patch.object(
                live_limited._OutputTransaction,
                "_release_lock",
                new=slow_release,
            ):
                report = stage_limited_live_run(
                    plan_path=plan_path,
                    output_root=output_root,
                    fixture_root=FIXTURES,
                    catalog=self.catalog,
                )
            self.assertTrue(release_saw_disarmed_timer)
            self.assertGreater(time.monotonic() - started, 1.0)
            self.assertEqual(report["status"], "PLUMBING_PASS")
            self.assertEqual(report["usage_wall_seconds"], 1)
            self.assertTrue(output_root.is_dir())
            self.assertFalse(
                any(
                    item.name.startswith(".kubo-stage-live-limited-")
                    for item in workspace.iterdir()
                )
            )

    def test_wall_breach_after_atomic_publish_removes_published_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            changed = _plan()
            changed["budget"] = {
                "max_requests": 2,
                "max_raw_bytes": 1000000,
                "max_wall_seconds": 1,
            }
            for slot in ("official_capture", "secondary_capture"):
                capture = dict(changed[slot])  # type: ignore[arg-type]
                capture["timeout_seconds"] = 0.1
                changed[slot] = capture
            plan_path = workspace / "slow-publish.json"
            plan_path.write_text(json.dumps(changed), encoding="utf-8")
            output_root = workspace / "run"
            original_publish = live_limited._OutputTransaction.publish
            saw_atomic_output = False

            def publish_then_block(transaction):  # noqa: ANN001
                nonlocal saw_atomic_output
                original_publish(transaction)
                saw_atomic_output = output_root.is_dir()
                time.sleep(2)
                self.fail("the hard wall failed to interrupt post-rename work")

            started = time.monotonic()
            with patch.object(
                live_limited._OutputTransaction,
                "publish",
                new=publish_then_block,
            ):
                report = stage_limited_live_run(
                    plan_path=plan_path,
                    output_root=output_root,
                    fixture_root=FIXTURES,
                    catalog=self.catalog,
                )
            self.assertTrue(saw_atomic_output)
            self.assertLess(time.monotonic() - started, 1.8)
            self.assertEqual(report["status"], "CAPTURE_DEGRADED")
            self.assertEqual(report["reason_code"], "WALL_BUDGET_EXCEEDED")
            self.assertFalse(output_root.exists())
            self.assertFalse(
                any(
                    item.name.startswith(".kubo-stage-live-limited-")
                    for item in workspace.iterdir()
                )
            )

    def test_wall_breach_during_lock_identity_leaves_no_reservation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            changed = _plan()
            changed["budget"] = {
                "max_requests": 2,
                "max_raw_bytes": 1000000,
                "max_wall_seconds": 1,
            }
            for slot in ("official_capture", "secondary_capture"):
                capture = dict(changed[slot])  # type: ignore[arg-type]
                capture["timeout_seconds"] = 0.1
                changed[slot] = capture
            plan_path = workspace / "slow-lock-identity.json"
            plan_path.write_text(json.dumps(changed), encoding="utf-8")
            original_fstat = live_limited.os.fstat
            delayed = False

            def slow_lock_fstat(descriptor):  # noqa: ANN001
                nonlocal delayed
                try:
                    target = os.readlink(f"/proc/self/fd/{descriptor}")
                except OSError:
                    target = ""
                if not delayed and target.endswith(".lock"):
                    delayed = True
                    time.sleep(1.05)
                return original_fstat(descriptor)

            with patch("kubo.live_limited.os.fstat", new=slow_lock_fstat):
                report = stage_limited_live_run(
                    plan_path=plan_path,
                    output_root=workspace / "run",
                    fixture_root=FIXTURES,
                    catalog=self.catalog,
                )
            self.assertTrue(delayed)
            self.assertEqual(report["status"], "CAPTURE_DEGRADED")
            self.assertEqual(report["reason_code"], "WALL_BUDGET_EXCEEDED")
            self.assertFalse((workspace / "run").exists())
            self.assertFalse(
                any(
                    item.name.startswith(".kubo-stage-live-limited-")
                    for item in workspace.iterdir()
                )
            )

    def test_wall_breach_during_work_identity_leaves_no_staging(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            changed = _plan()
            changed["budget"] = {
                "max_requests": 2,
                "max_raw_bytes": 1000000,
                "max_wall_seconds": 1,
            }
            for slot in ("official_capture", "secondary_capture"):
                capture = dict(changed[slot])  # type: ignore[arg-type]
                capture["timeout_seconds"] = 0.1
                changed[slot] = capture
            plan_path = workspace / "slow-work-identity.json"
            plan_path.write_text(json.dumps(changed), encoding="utf-8")
            original_metadata = live_limited._entry_metadata
            delayed = False

            def slow_work_metadata(parent_fd, name):  # noqa: ANN001
                nonlocal delayed
                metadata = original_metadata(parent_fd, name)
                if (
                    not delayed
                    and name.startswith(".kubo-stage-live-limited-")
                    and not name.endswith(".lock")
                    and metadata is not None
                    and stat.S_ISDIR(metadata.st_mode)
                ):
                    delayed = True
                    time.sleep(1.05)
                return metadata

            with patch(
                "kubo.live_limited._entry_metadata",
                new=slow_work_metadata,
            ):
                report = stage_limited_live_run(
                    plan_path=plan_path,
                    output_root=workspace / "run",
                    fixture_root=FIXTURES,
                    catalog=self.catalog,
                )
            self.assertTrue(delayed)
            self.assertEqual(report["status"], "CAPTURE_DEGRADED")
            self.assertEqual(report["reason_code"], "WALL_BUDGET_EXCEEDED")
            self.assertFalse((workspace / "run").exists())
            self.assertFalse(
                any(
                    item.name.startswith(".kubo-stage-live-limited-")
                    for item in workspace.iterdir()
                )
            )

    def test_parent_swap_after_rename_aborts_old_parent_packet(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            parent = workspace / "parent"
            parent.mkdir()
            moved_parent = workspace / "moved-parent"
            output_root = parent / "run"
            plan_path = workspace / "plan.json"
            plan_path.write_text(json.dumps(_plan()), encoding="utf-8")
            original_revalidate = (
                live_limited._OutputTransaction._revalidate_parent_path
            )
            calls = 0

            def swap_on_post_rename(transaction):  # noqa: ANN001
                nonlocal calls
                calls += 1
                if calls == 2:
                    parent.rename(moved_parent)
                    parent.mkdir()
                return original_revalidate(transaction)

            with patch.object(
                live_limited._OutputTransaction,
                "_revalidate_parent_path",
                new=swap_on_post_rename,
            ):
                with self.assertRaisesRegex(ValueError, "parent changed"):
                    stage_limited_live_run(
                        plan_path=plan_path,
                        output_root=output_root,
                        fixture_root=FIXTURES,
                        catalog=self.catalog,
                    )
            self.assertEqual(calls, 2)
            self.assertEqual(list(parent.iterdir()), [])
            self.assertFalse((moved_parent / "run").exists())
            self.assertFalse(
                any(
                    item.name.startswith(".kubo-stage-live-limited-")
                    for item in moved_parent.iterdir()
                )
            )

    def test_parent_swap_between_publish_and_commit_aborts_packet(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            parent = workspace / "parent"
            parent.mkdir()
            moved_parent = workspace / "moved-parent"
            output_root = parent / "run"
            plan_path = workspace / "plan.json"
            plan_path.write_text(json.dumps(_plan()), encoding="utf-8")
            original_revalidate = (
                live_limited._OutputTransaction._revalidate_parent_path
            )
            calls = 0

            def swap_before_commit_revalidation(transaction):  # noqa: ANN001
                nonlocal calls
                calls += 1
                if calls == 3:
                    self.assertTrue(transaction.published)
                    self.assertFalse(transaction.committed)
                    parent.rename(moved_parent)
                    parent.mkdir()
                return original_revalidate(transaction)

            with patch.object(
                live_limited._OutputTransaction,
                "_revalidate_parent_path",
                new=swap_before_commit_revalidation,
            ):
                with self.assertRaisesRegex(ValueError, "parent changed"):
                    stage_limited_live_run(
                        plan_path=plan_path,
                        output_root=output_root,
                        fixture_root=FIXTURES,
                        catalog=self.catalog,
                    )
            self.assertEqual(calls, 3)
            self.assertEqual(list(parent.iterdir()), [])
            self.assertFalse((moved_parent / "run").exists())
            self.assertFalse(
                any(
                    item.name.startswith(".kubo-stage-live-limited-")
                    for item in moved_parent.iterdir()
                )
            )

    def test_output_parent_symlink_component_is_rejected_without_following(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            real_parent = workspace / "real-parent"
            real_parent.mkdir()
            link_parent = workspace / "link-parent"
            link_parent.symlink_to(real_parent, target_is_directory=True)
            plan_path = workspace / "plan.json"
            plan_path.write_text(json.dumps(_plan()), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "parent contains a symlink"):
                stage_limited_live_run(
                    plan_path=plan_path,
                    output_root=link_parent / "run",
                    fixture_root=FIXTURES,
                    catalog=self.catalog,
                )
            self.assertFalse((real_parent / "run").exists())

    def test_parent_swap_before_transaction_enter_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            original_parent = workspace / "parent"
            original_parent.mkdir()
            transaction = live_limited._OutputTransaction(original_parent / "run")

            moved_parent = workspace / "moved-parent"
            original_parent.rename(moved_parent)
            replacement = workspace / "replacement"
            replacement.mkdir()
            original_parent.symlink_to(replacement, target_is_directory=True)

            with self.assertRaisesRegex(ValueError, "symlink component"):
                with transaction:
                    self.fail("a swapped parent unexpectedly passed the secure walk")
            self.assertFalse((replacement / "run").exists())
            self.assertEqual(list(replacement.iterdir()), [])

    def test_output_transaction_is_exclusive_and_publishes_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            output_root = workspace / "run"
            with live_limited._OutputTransaction(output_root) as transaction:
                self.assertFalse(output_root.exists())
                (transaction.work_root / "complete.txt").write_text(
                    "complete", encoding="utf-8"
                )
                with self.assertRaisesRegex(ValueError, "reserved by another"):
                    with live_limited._OutputTransaction(output_root):
                        self.fail("a concurrent reservation unexpectedly succeeded")
                transaction.publish()
                transaction.commit()
            self.assertEqual(
                (output_root / "complete.txt").read_text(encoding="utf-8"),
                "complete",
            )

            target = workspace / "target"
            target.mkdir()
            symlink = workspace / "symlink-run"
            symlink.symlink_to(target, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "must not be a symlink"):
                with live_limited._OutputTransaction(symlink):
                    self.fail("a symlink output root unexpectedly succeeded")

    def test_official_slot_cannot_be_replaced_by_secondary_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            changed = _plan()
            official = dict(changed["official_capture"])  # type: ignore[arg-type]
            official["source_id"] = "investing_history"
            changed["official_capture"] = official
            path = workspace / "bad.json"
            path.write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "requires boursa_current"):
                stage_limited_live_run(
                    plan_path=path,
                    output_root=workspace / "run",
                    fixture_root=FIXTURES,
                    catalog=self.catalog,
                )

    def test_v1_rejects_full_market_claim(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            path = workspace / "bad.json"
            path.write_text(json.dumps(_plan(scope="FULL_MARKET")), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "NAMED_SECURITIES"):
                stage_limited_live_run(
                    plan_path=path,
                    output_root=workspace / "run",
                    fixture_root=FIXTURES,
                    catalog=self.catalog,
                )


if __name__ == "__main__":
    unittest.main()
