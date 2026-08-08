from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from urllib import error

from kubo.hashing import sha256_bytes
from kubo.ingestion import (
    DEFAULT_USER_AGENT,
    CapturePacketWriter,
    CaptureRequest,
    FileConnector,
    PublicHttpConnector,
    capture_sources,
)
from kubo.source_network import SourceNetworkCatalog, SourceNetworkRunValidator


FIXED_TIME = datetime.fromisoformat("2026-08-07T00:50:00+03:00")


def fixed_clock() -> datetime:
    return FIXED_TIME


def capture_request(**overrides) -> CaptureRequest:
    values = {
        "source_id": "fixture_source",
        "source_url": "https://example.com/public/data",
        "allowed_domains": ("example.com",),
        "roles_observed": ("NEWS_ARCHIVE",),
        "resource_path": "payload.json",
        "timeout_seconds": 7,
        "max_bytes": 1024,
    }
    values.update(overrides)
    return CaptureRequest(**values)


class FakeResponse:
    def __init__(
        self,
        body: bytes,
        url: str,
        *,
        status: int = 200,
        headers: dict[str, str] | None = None,
    ):
        self.body = body
        self.url = url
        self.status = status
        self.headers = headers or {}
        self.closed = False

    def read(self, limit: int = -1) -> bytes:
        if limit < 0:
            return self.body
        return self.body[:limit]

    def geturl(self) -> str:
        return self.url

    def getcode(self) -> int:
        return self.status

    def close(self) -> None:
        self.closed = True


class QueueOpener:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls: list[tuple[object, float]] = []

    def open(self, requested, timeout):
        self.calls.append((requested, timeout))
        if not self.responses:
            raise AssertionError("unexpected HTTP request")
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def robots_response(body: bytes = b"User-agent: *\nDisallow:\n") -> FakeResponse:
    return FakeResponse(body, "https://example.com/robots.txt", headers={"Content-Type": "text/plain"})


class CaptureContractTests(unittest.TestCase):
    def test_request_normalizes_domains_and_roles(self):
        item = capture_request(
            allowed_domains=("EXAMPLE.com.", "example.com"),
            roles_observed=("NEWS_ARCHIVE", "NEWS_ARCHIVE"),
        )
        self.assertEqual(item.allowed_domains, ("example.com",))
        self.assertEqual(item.roles_observed, ("NEWS_ARCHIVE",))

    def test_request_rejects_non_https_credentials_and_sensitive_query(self):
        invalid_urls = (
            "http://example.com/data",
            "https://user:pass@example.com/data",  # secret-guard: allow — deliberate rejection fixture
            "https://example.com/data#fragment",
            "https://example.com:8443/data",
            "https://example.com/data?access_token=secret",  # secret-guard: allow — rejection fixture
            "https://example.com/data?token=secret",  # secret-guard: allow — rejection fixture
            "https://example.com/data?AccessToken=secret",  # secret-guard: allow — rejection fixture
            "https://example.com/callback?code=oauth-code",  # secret-guard: allow — rejection fixture
            "https://example.com/data?X-Amz-Credential=AKIA/example",  # secret-guard: allow — fixture
            "https://example.com/data?X-Amz-Signature=deadbeef",  # secret-guard: allow — fixture
            "https://example.com/data?XAmzSignature=deadbeef",  # secret-guard: allow — fixture
        )
        for url in invalid_urls:
            with self.subTest(url=url), self.assertRaises(ValueError):
                capture_request(source_url=url)

    def test_request_rejects_domain_suffix_spoof(self):
        with self.assertRaisesRegex(ValueError, "outside"):
            capture_request(source_url="https://example.com.attacker.invalid/data")
        with self.assertRaisesRegex(ValueError, "IP literals"):
            capture_request(
                source_url="https://127.0.0.1/data",
                allowed_domains=("127.0.0.1",),
            )
        with self.assertRaisesRegex(ValueError, "local or internal"):
            capture_request(
                source_url="https://service.internal/data",
                allowed_domains=("service.internal",),
            )

    def test_request_rejects_unbounded_limits_and_header_injection(self):
        with self.assertRaises(ValueError):
            capture_request(max_bytes=0)
        with self.assertRaises(ValueError):
            capture_request(timeout_seconds=61)
        with self.assertRaises(ValueError):
            capture_request(user_agent="safe\r\nAuthorization: secret")

    def test_query_values_are_hashed_before_provenance_is_persisted(self):
        opaque_value = "private-value-that-must-not-be-recorded"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "payload.json").write_bytes(b"public body")
            result = FileConnector(root, clock=fixed_clock).capture(
                capture_request(source_url=f"https://example.com/data?symbol={opaque_value}")
            )
            run = root / "run"
            CapturePacketWriter(run).write((result,))
            persisted = (run / "manifest.json").read_text(encoding="utf-8")
        self.assertNotIn(opaque_value, result.source_url)
        self.assertNotIn(opaque_value, result.final_url)
        self.assertNotIn(opaque_value, persisted)
        self.assertIn("__kubo_query_sha256", result.final_url)


class FileConnectorTests(unittest.TestCase):
    def test_file_connector_reads_bounded_bytes_without_qualifying_them(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            content = b'{"fixture": true}\n'
            (root / "payload.json").write_bytes(content)
            result = FileConnector(root, clock=fixed_clock).capture(capture_request())
        self.assertTrue(result.captured)
        self.assertEqual(result.content, content)
        self.assertEqual(result.state, "AVAILABLE")
        self.assertEqual(result.query_status, "DATA_QUALITY_REJECTED")
        self.assertIn("RAW_CAPTURE_PENDING_PARSER_VALIDATION", result.data_quality_flags)
        self.assertEqual(result.qualified_items, 0)

    def test_file_connector_rejects_traversal_and_outside_symlink(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            root = Path(directory)
            outside_file = Path(outside) / "secret.txt"
            outside_file.write_text("secret", encoding="utf-8")
            (root / "escape.txt").symlink_to(outside_file)
            connector = FileConnector(root, clock=fixed_clock)
            traversal = connector.capture(capture_request(resource_path="../secret.txt"))
            escaped = connector.capture(capture_request(resource_path="escape.txt"))
        self.assertEqual(traversal.error_code, "LOCAL_PATH_OUTSIDE_FIXTURE_ROOT")
        self.assertEqual(escaped.error_code, "LOCAL_PATH_OUTSIDE_FIXTURE_ROOT")
        self.assertFalse(traversal.captured)
        self.assertFalse(escaped.captured)

    def test_file_connector_records_missing_and_oversized_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "large.bin").write_bytes(b"12345")
            connector = FileConnector(root, clock=fixed_clock)
            missing = connector.capture(capture_request(resource_path="missing.bin"))
            oversized = connector.capture(
                capture_request(resource_path="large.bin", max_bytes=4)
            )
        self.assertEqual(missing.state, "ERROR")
        self.assertEqual(missing.error_code, "LOCAL_RESOURCE_NOT_FOUND")
        self.assertEqual(oversized.state, "PARTIAL")
        self.assertEqual(oversized.error_code, "MAX_BYTES_EXCEEDED")

    def test_empty_file_is_preserved_but_marked_partial(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "payload.json").write_bytes(b"")
            result = FileConnector(root, clock=fixed_clock).capture(capture_request())
        self.assertEqual(result.content, b"")
        self.assertEqual(result.state, "PARTIAL")
        self.assertIn("EMPTY_RESPONSE_BODY", result.data_quality_flags)


class PublicHttpConnectorTests(unittest.TestCase):
    def test_dns_resolution_to_non_public_address_is_blocked_before_connect(self):
        def private_resolver(*_args, **_kwargs):
            return [
                (2, 1, 6, "", ("127.0.0.1", 443)),
                (2, 1, 6, "", ("10.0.0.7", 443)),
            ]

        result = PublicHttpConnector(clock=fixed_clock, resolver=private_resolver).capture(
            capture_request(resource_path=None)
        )
        self.assertEqual(result.state, "BLOCKED")
        self.assertEqual(result.error_code, "ROBOTS_NON_PUBLIC_NETWORK_TARGET")
        self.assertFalse(result.captured)

    def test_public_capture_checks_robots_and_sends_only_public_headers(self):
        body = b'{"market": "fixture"}'
        page = FakeResponse(
            body,
            "https://news.example.com/item",
            headers={"Content-Type": "application/json", "Content-Length": str(len(body))},
        )
        opener = QueueOpener(robots_response(), page)
        connector = PublicHttpConnector(clock=fixed_clock, opener=opener)
        result = connector.capture(
            capture_request(
                source_url="https://news.example.com/item",
                allowed_domains=("example.com",),
                resource_path=None,
            )
        )
        self.assertEqual(result.content, body)
        self.assertEqual(result.http_status, 200)
        self.assertEqual(len(opener.calls), 2)
        robots_call, page_call = opener.calls
        self.assertEqual(robots_call[0].full_url, "https://news.example.com/robots.txt")
        self.assertEqual(page_call[1], 7.0)
        headers = {key.casefold(): value for key, value in page_call[0].header_items()}
        self.assertEqual(headers["user-agent"], DEFAULT_USER_AGENT)
        self.assertNotIn("authorization", headers)
        self.assertNotIn("cookie", headers)

    def test_robots_disallow_blocks_without_requesting_page(self):
        opener = QueueOpener(robots_response(b"User-agent: *\nDisallow: /private\n"))
        result = PublicHttpConnector(clock=fixed_clock, opener=opener).capture(
            capture_request(source_url="https://example.com/private/data", resource_path=None)
        )
        self.assertEqual(result.state, "BLOCKED")
        self.assertEqual(result.error_code, "ROBOTS_DISALLOWED")
        self.assertEqual(len(opener.calls), 1)

    def test_missing_robots_is_not_treated_as_a_published_restriction(self):
        robots_404 = error.HTTPError(
            "https://example.com/robots.txt", 404, "Not Found", {}, io.BytesIO(b"")
        )
        opener = QueueOpener(
            robots_404,
            FakeResponse(b"ok", "https://example.com/data", headers={"Content-Type": "text/plain"}),
        )
        result = PublicHttpConnector(clock=fixed_clock, opener=opener).capture(
            capture_request(source_url="https://example.com/data", resource_path=None)
        )
        self.assertTrue(result.captured)

    def test_unavailable_robots_fails_closed(self):
        opener = QueueOpener(error.URLError("offline"))
        result = PublicHttpConnector(clock=fixed_clock, opener=opener).capture(
            capture_request(resource_path=None)
        )
        self.assertEqual(result.state, "BLOCKED")
        self.assertEqual(result.error_code, "ROBOTS_POLICY_UNAVAILABLE")
        self.assertEqual(len(opener.calls), 1)

    def test_http_auth_rate_limit_and_server_failures_are_explicit(self):
        cases = (
            (401, "AUTH_REQUIRED", "HTTP_AUTH_REQUIRED"),
            (403, "BLOCKED", "HTTP_FORBIDDEN"),
            (429, "BLOCKED", "HTTP_RATE_LIMITED"),
            (503, "ERROR", "HTTP_SERVER_ERROR"),
        )
        for status, state, code in cases:
            with self.subTest(status=status):
                http_error = error.HTTPError(
                    "https://example.com/public/data", status, "error", {}, io.BytesIO(b"")
                )
                opener = QueueOpener(robots_response(), http_error)
                result = PublicHttpConnector(clock=fixed_clock, opener=opener).capture(
                    capture_request(resource_path=None)
                )
                self.assertEqual(result.state, state)
                self.assertEqual(result.error_code, code)
                self.assertFalse(result.captured)

    def test_captcha_paywall_and_login_pages_are_not_saved(self):
        cases = (
            (b'<div class="g-recaptcha"></div>', "BLOCKED", "CAPTCHA_DETECTED"),
            (b'<div id="paywall">Subscribe to continue</div>', "AUTH_REQUIRED", "PAYWALL_DETECTED"),
            (b'<form><input type="password"></form>', "AUTH_REQUIRED", "AUTH_REQUIRED_PAGE"),
        )
        for body, state, code in cases:
            with self.subTest(code=code):
                opener = QueueOpener(
                    robots_response(),
                    FakeResponse(body, "https://example.com/public/data", headers={"Content-Type": "text/html"}),
                )
                result = PublicHttpConnector(clock=fixed_clock, opener=opener).capture(
                    capture_request(resource_path=None)
                )
                self.assertEqual(result.state, state)
                self.assertEqual(result.error_code, code)
                self.assertIsNone(result.content)

    def test_redirect_final_url_outside_allowlist_is_rejected(self):
        opener = QueueOpener(
            robots_response(),
            FakeResponse(b"stolen", "https://attacker.invalid/data", headers={"Content-Type": "text/plain"}),
        )
        result = PublicHttpConnector(clock=fixed_clock, opener=opener).capture(
            capture_request(resource_path=None)
        )
        self.assertEqual(result.state, "BLOCKED")
        self.assertEqual(result.error_code, "REDIRECT_OUTSIDE_ALLOWLIST")
        self.assertIsNone(result.content)

    def test_declared_and_streamed_size_limits_are_enforced(self):
        declared = QueueOpener(
            robots_response(),
            FakeResponse(
                b"ignored",
                "https://example.com/public/data",
                headers={"Content-Type": "text/plain", "Content-Length": "999"},
            ),
        )
        streamed = QueueOpener(
            robots_response(),
            FakeResponse(
                b"12345",
                "https://example.com/public/data",
                headers={"Content-Type": "text/plain"},
            ),
        )
        first = PublicHttpConnector(clock=fixed_clock, opener=declared).capture(
            capture_request(resource_path=None, max_bytes=4)
        )
        second = PublicHttpConnector(clock=fixed_clock, opener=streamed).capture(
            capture_request(resource_path=None, max_bytes=4)
        )
        self.assertEqual(first.error_code, "MAX_BYTES_EXCEEDED")
        self.assertEqual(second.error_code, "MAX_BYTES_EXCEEDED")
        self.assertIsNone(first.content)
        self.assertIsNone(second.content)

    def test_public_connector_refuses_authenticated_mode_before_network(self):
        opener = QueueOpener()
        result = PublicHttpConnector(clock=fixed_clock, opener=opener).capture(
            capture_request(
                access_mode="AUTHORIZED_BROWSER",
                resource_path=None,
            )
        )
        self.assertEqual(result.state, "AUTH_REQUIRED")
        self.assertEqual(result.error_code, "AUTHENTICATED_ACCESS_FORBIDDEN")
        self.assertEqual(opener.calls, [])


class BatchAndWriterTests(unittest.TestCase):
    def test_batch_isolates_connector_failure_per_source(self):
        class ExplodingConnector:
            def capture(self, _):
                raise RuntimeError("a secret must never be copied into output")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "payload.json").write_bytes(b"good")
            good = capture_request(source_id="good_source")
            bad = capture_request(source_id="bad_source", resource_path="unused")
            batch = capture_sources(
                [
                    (FileConnector(root, clock=fixed_clock), good),
                    (ExplodingConnector(), bad),
                ],
                clock=fixed_clock,
            )
        self.assertEqual(batch.status, "DEGRADED")
        self.assertEqual(len(batch.results), 2)
        failed = next(item for item in batch.results if item.source_id == "bad_source")
        self.assertEqual(failed.error_code, "CONNECTOR_INTERNAL_ERROR")
        self.assertNotIn("secret", repr(failed))
        self.assertEqual(dict(batch.source_states)["good_source"], "AVAILABLE")
        self.assertEqual(dict(batch.source_states)["bad_source"], "ERROR")

    def test_writer_creates_content_addressed_artifact_and_degraded_observation(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            fixture = workspace / "fixtures"
            run = workspace / "run"
            fixture.mkdir()
            content = b"fixture evidence"
            (fixture / "payload.json").write_bytes(content)
            connector = FileConnector(fixture, clock=fixed_clock)
            success = connector.capture(capture_request(source_id="good_source"))
            failure = connector.capture(
                capture_request(source_id="failed_source", resource_path="missing.json")
            )
            report = CapturePacketWriter(run).write((success, failure))
            manifest_bytes = (run / "manifest.json").read_bytes()
            observations_bytes = (run / "source_observations.json").read_bytes()
            manifest = json.loads(manifest_bytes)
            observations = json.loads(observations_bytes)

            second_report = CapturePacketWriter(run).write((success, failure))
            self.assertEqual((run / "manifest.json").read_bytes(), manifest_bytes)
            self.assertEqual((run / "source_observations.json").read_bytes(), observations_bytes)

            artifact = manifest["artifacts"][0]
            raw_path = run / artifact["path"]
            self.assertTrue(raw_path.is_file())
            self.assertEqual(raw_path.read_bytes(), content)
            self.assertEqual(artifact["sha256"], sha256_bytes(content))
            self.assertEqual(report.status, "DEGRADED")
            self.assertEqual(second_report.to_dict(), report.to_dict())
            self.assertEqual(report.artifact_count, 1)
            rows = {item["source_id"]: item for item in observations["sources"]}
            self.assertEqual(rows["failed_source"]["state"], "ERROR")
            self.assertEqual(rows["good_source"]["query_status"], "DATA_QUALITY_REJECTED")
            self.assertEqual(rows["good_source"]["qualified_items"], 0)
            self.assertIn("RAW_CAPTURE_PENDING_PARSER_VALIDATION", rows["good_source"]["data_quality_flags"])

    def test_writer_aggregates_multiple_urls_for_one_source_deterministically(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            fixture = workspace / "fixtures"
            fixture.mkdir()
            (fixture / "one.txt").write_bytes(b"one")
            (fixture / "two.txt").write_bytes(b"two")
            connector = FileConnector(fixture, clock=fixed_clock)
            first = connector.capture(
                capture_request(resource_path="one.txt", source_url="https://example.com/data?id=1")
            )
            second = connector.capture(
                capture_request(resource_path="two.txt", source_url="https://example.com/data?id=2")
            )
            report = CapturePacketWriter(workspace / "run").write((second, first))
            observations = json.loads((workspace / "run" / "source_observations.json").read_text())
        self.assertEqual(report.status, "COMPLETE")
        self.assertEqual(report.artifact_count, 2)
        self.assertEqual(report.source_count, 1)
        self.assertEqual(len(observations["sources"]), 1)
        self.assertEqual(len(observations["sources"][0]["raw_sha256s"]), 2)

    @unittest.skipUnless(hasattr(os, "O_NOFOLLOW"), "requires POSIX no-follow support")
    def test_writer_run_root_fd_stays_bound_after_path_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            fixture = workspace / "fixtures"
            run = workspace / "run"
            moved = workspace / "moved-run"
            fixture.mkdir()
            run.mkdir()
            (fixture / "payload.json").write_bytes(b"descriptor-bound evidence")
            result = FileConnector(fixture, clock=fixed_clock).capture(capture_request())
            flags = getattr(os, "O_PATH", os.O_RDONLY) | os.O_DIRECTORY | os.O_NOFOLLOW
            root_fd = os.open(run, flags)
            try:
                writer = CapturePacketWriter(run, run_root_fd=root_fd)
                os.close(root_fd)
                root_fd = -1
                with writer:
                    run.rename(moved)
                    run.mkdir()
                    report = writer.write((result,))
            finally:
                if root_fd >= 0:
                    os.close(root_fd)

            self.assertEqual(report.status, "COMPLETE")
            self.assertTrue((moved / "manifest.json").is_file())
            self.assertTrue((moved / "source_observations.json").is_file())
            self.assertFalse((run / "manifest.json").exists())
            self.assertEqual(list(run.iterdir()), [])

    @unittest.skipUnless(hasattr(os, "O_NOFOLLOW"), "requires POSIX no-follow support")
    def test_writer_rejects_filesystem_root_fd_regardless_of_diagnostic_path(self):
        with tempfile.TemporaryDirectory() as directory:
            diagnostic_path = Path(directory) / "diagnostic-non-root"
            flags = getattr(os, "O_PATH", os.O_RDONLY) | os.O_DIRECTORY | os.O_NOFOLLOW
            root_fd = os.open("/", flags)
            try:
                with self.assertRaisesRegex(ValueError, "filesystem root"):
                    CapturePacketWriter(
                        diagnostic_path,
                        run_root_fd=root_fd,
                    )
            finally:
                os.close(root_fd)
            self.assertFalse(diagnostic_path.exists())

    @unittest.skipUnless(hasattr(__import__("os"), "O_NOFOLLOW"), "requires POSIX no-follow support")
    def test_writer_rejects_precreated_symlink_parent_without_outside_write(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            workspace = Path(directory)
            fixture = workspace / "fixtures"
            run = workspace / "run"
            fixture.mkdir()
            run.mkdir()
            (run / "raw").mkdir()
            (run / "raw" / "fixture_source").symlink_to(Path(outside), target_is_directory=True)
            (fixture / "payload.json").write_bytes(b"must stay inside")
            result = FileConnector(fixture, clock=fixed_clock).capture(capture_request())
            with self.assertRaisesRegex(ValueError, "symlink|non-directory"):
                CapturePacketWriter(run).write((result,))
            self.assertEqual(list(Path(outside).iterdir()), [])

    def test_writer_output_remains_unqualified_without_identity_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            fixture = workspace / "fixtures"
            run = workspace / "run"
            config = workspace / "config"
            fixture.mkdir()
            config.mkdir()
            (fixture / "payload.json").write_bytes(b'{"fixture": "news"}\n')
            result = FileConnector(fixture, clock=fixed_clock).capture(
                capture_request(
                    source_id="kuna",
                    source_url="https://www.kuna.net.kw/",
                    allowed_domains=("kuna.net.kw", "www.kuna.net.kw"),
                    roles_observed=("NEWS_ARCHIVE",),
                )
            )
            CapturePacketWriter(run).write((result,))
            (run / "research_run.json").write_text(
                json.dumps(
                    {
                        "schema_version": "3.0",
                        "run_id": "ingestion-contract-test",
                        "product_id": "next_session_rank",
                        "decision_at": "2026-08-07T01:00:00+03:00",
                        "timezone": "Asia/Kuwait",
                        "scope": "CANDIDATE_SET",
                        "expected_universe_count": 1,
                        "covered_universe_count": 1,
                        "budget": {
                            "max_requests": 2,
                            "max_raw_bytes": 10000,
                            "max_wall_seconds": 60,
                        },
                        "usage": {"requests": 1, "raw_bytes": len(result.content or b""), "wall_seconds": 1},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (run / "findings.jsonl").write_text("", encoding="utf-8")
            (config / "source_network.json").write_text(
                json.dumps(
                    {
                        "schema_version": "3.0",
                        "role_vocabulary": [
                            "IDENTITY_REFERENCE",
                            "OFFICIAL_EVENT",
                            "ISSUER_PRIMARY",
                            "MARKET_DISCOVERY",
                            "PRICE_HISTORY",
                            "FUNDAMENTAL_ARCHIVE",
                            "NEWS_ARCHIVE",
                            "COMMUNITY_SENTIMENT",
                            "WEB_ARCHIVE",
                            "SEARCH_ROUTER",
                            "EXECUTION_TAPE",
                            "STORAGE_ONLY",
                        ],
                        "sources": [
                            {
                                "source_id": "kuna",
                                "name": "Fixture editorial source",
                                "source_class": "EDITORIAL",
                                "roles": ["NEWS_ARCHIVE"],
                                "domains": ["kuna.net.kw", "www.kuna.net.kw"],
                                "start_urls": ["https://www.kuna.net.kw/"],
                                "access_modes": ["PUBLIC_PAGE"],
                                "independence_group": "kuna",
                                "timing_grade_ceiling": "B",
                                "fact_eligibility": ["NEWS_CONTEXT"],
                                "enabled_by_default": True,
                            }
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (config / "research_policies.json").write_text(
                json.dumps(
                    {
                        "schema_version": "3.0",
                        "allowed_outputs": [
                            "CANDIDATE_RESEARCH_RANK",
                            "WATCH",
                            "ABSTAIN",
                            "EXECUTION_BLOCKED",
                        ],
                        "forbidden_outputs": [
                            "CALIBRATED_PROBABILITY",
                            "HIGH_BUY_OPPORTUNITY",
                            "GUARANTEED_RETURN",
                        ],
                        "profiles": [
                            {
                                "profile_id": "test_profile",
                                "products": ["next_session_rank"],
                                "required_role_quorum": {"NEWS_ARCHIVE": 1},
                                "confirmation_roles": ["OFFICIAL_EVENT", "ISSUER_PRIMARY"],
                                "minimum_independent_sources": 1,
                                "minimum_independent_community_sources": 0,
                                "max_source_age_hours": 24,
                                "signal_weights": {"CATALYST": 1.0},
                                "sentiment_contribution_cap": 0.0,
                                "candidate_minimum_coverage": 0.5,
                                "full_market_coverage_required": 1.0,
                                "allowed_output": "CANDIDATE_RESEARCH_RANK",
                                "probability_allowed": False,
                                "recommendation_allowed": False,
                            }
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (config / "source_capabilities.json").write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "default_capability": {
                            "status": "DEFINED_ONLY",
                            "capture": "CATALOG_ONLY",
                            "parser_ids": [],
                            "fixture_evidence": "NONE",
                            "live_operational": False,
                        },
                        "overrides": {},
                        "claim_boundaries": {
                            "catalog_entry_is_connector": False,
                            "capture_success_is_parser_success": False,
                            "contract_fixture_is_live_acceptance": False,
                            "parser_implemented_is_live_operational": False,
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            catalog = SourceNetworkCatalog(config)
            validation = SourceNetworkRunValidator(run, catalog, "next_session_rank").validate()
        self.assertEqual(validation.status, "BLOCKED", validation.to_dict())
        self.assertIn("MISSING_SECURITY_IDENTITY_RECEIPT", validation.structural_errors)
        self.assertEqual(len(validation.artifacts), 1)
        kuna_observation = next(
            item for item in validation.observations if item.source_id == "kuna"
        )
        self.assertFalse(kuna_observation.contributes)


if __name__ == "__main__":
    unittest.main()
