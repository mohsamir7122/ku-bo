from __future__ import annotations

import io
import json
import socket
import ssl
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from urllib import error

from kubo.hashing import sha256_bytes
from kubo.ingestion import (
    DEFAULT_USER_AGENT,
    CapturePacketWriter,
    CaptureRequest,
    FileConnector,
    PublicHttpConnector,
    RobotsAccessGrant,
    capture_sources,
)
import kubo.ingestion as ingestion
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


def robots_access_grant(source_id: str = "fixture_source") -> RobotsAccessGrant:
    return RobotsAccessGrant(
        source_id=source_id,
        registry_id="reviewed-robots-access-v1",
        registry_sha256="a" * 64,
        rights_status="PERMITTED",
        terms_status="REVIEWED_PERMITTED",
        public_access_status="CONFIRMED_PUBLIC",
        reviewed_at=FIXED_TIME - timedelta(days=1),
        expires_at=FIXED_TIME + timedelta(days=30),
    )


class CaptureContractTests(unittest.TestCase):
    def test_capture_writer_rejects_symlink_run_root(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            link = Path(directory) / "run"
            try:
                link.symlink_to(outside, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("directory symlinks are unavailable")
            with self.assertRaisesRegex(ValueError, "symlink"):
                CapturePacketWriter(link)
            self.assertEqual(list(Path(outside).iterdir()), [])

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
    def test_pinned_https_handler_uses_python_312_connection_signature(self):
        context = ssl.create_default_context()

        def resolver(*_args, **_kwargs):
            return [(2, 1, 6, "", ("93.184.216.34", 443))]

        handler = ingestion._PinnedHTTPSHandler(
            ("example.com",), resolver=resolver, context=context
        )
        observed = {}

        def do_open(factory, requested, **kwargs):
            observed["kwargs"] = kwargs
            connection = factory(
                "example.com",
                timeout=7,
                context=kwargs["context"],
            )
            self.assertIsInstance(connection, ingestion._PinnedHTTPSConnection)
            self.assertEqual(connection._pinned_addresses, ("93.184.216.34",))
            return "opened"

        handler.do_open = do_open
        requested = ingestion.request.Request("https://example.com/data")
        self.assertEqual(handler.https_open(requested), "opened")
        self.assertEqual(observed["kwargs"], {"context": context})
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)

    def test_dns_resolution_failure_is_transient_but_non_public_is_blocked(self):
        def failed_resolver(*_args, **_kwargs):
            raise socket.gaierror("temporary failure")

        result = PublicHttpConnector(clock=fixed_clock, resolver=failed_resolver).capture(
            capture_request(resource_path=None)
        )
        self.assertEqual(result.state, "ERROR")
        self.assertEqual(result.error_code, "ROBOTS_UNREACHABLE")

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

    def test_missing_robots_requires_trusted_rights_terms_and_public_access(self):
        robots_404 = error.HTTPError(
            "https://example.com/robots.txt", 404, "Not Found", {}, io.BytesIO(b"")
        )
        blocked = PublicHttpConnector(
            clock=fixed_clock,
            opener=QueueOpener(robots_404),
        ).capture(capture_request(source_url="https://example.com/data", resource_path=None))
        self.assertEqual(blocked.state, "BLOCKED")
        self.assertEqual(blocked.error_code, "ACCESS_REVIEW_REQUIRED")
        self.assertEqual(blocked.robots_policy_receipt.http_status, 404)
        self.assertFalse(
            blocked.robots_policy_receipt.to_dict()["access_receipt_proves_collection"]
        )

        granted_404 = error.HTTPError(
            "https://example.com/robots.txt", 404, "Not Found", {}, io.BytesIO(b"")
        )
        opener = QueueOpener(
            granted_404,
            FakeResponse(b"ok", "https://example.com/data", headers={"Content-Type": "text/plain"}),
        )
        result = PublicHttpConnector(
            clock=fixed_clock,
            opener=opener,
            robots_access_grants={"fixture_source": robots_access_grant()},
        ).capture(
            capture_request(source_url="https://example.com/data", resource_path=None)
        )
        self.assertTrue(result.captured)
        receipt = result.robots_policy_receipt.to_dict()
        self.assertEqual(receipt["decision"], "ROBOTS_NOT_PUBLISHED")
        self.assertEqual(receipt["access_registry_sha256"], "a" * 64)
        self.assertFalse(receipt["access_receipt_proves_collection"])

    def test_unavailable_robots_fails_closed(self):
        opener = QueueOpener(error.URLError("offline"))
        result = PublicHttpConnector(clock=fixed_clock, opener=opener).capture(
            capture_request(resource_path=None)
        )
        self.assertEqual(result.state, "ERROR")
        self.assertEqual(result.error_code, "ROBOTS_UNREACHABLE")
        self.assertEqual(result.robots_policy_receipt.decision, "ROBOTS_UNREACHABLE")
        self.assertEqual(len(opener.calls), 1)

    def test_transient_robots_failure_is_not_cached_across_retry(self):
        opener = QueueOpener(
            error.URLError("offline"),
            robots_response(),
            FakeResponse(
                b"ok",
                "https://example.com/public/data",
                headers={"Content-Type": "text/plain"},
            ),
        )
        connector = PublicHttpConnector(clock=fixed_clock, opener=opener)
        first = connector.capture(capture_request(resource_path=None))
        second = connector.capture(capture_request(resource_path=None))
        self.assertEqual(first.error_code, "ROBOTS_UNREACHABLE")
        self.assertTrue(second.captured)
        self.assertEqual(len(opener.calls), 3)

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

    def test_http_rate_limit_preserves_bounded_retry_after(self):
        http_error = error.HTTPError(
            "https://example.com/public/data",
            429,
            "rate limited",
            {"Retry-After": "17"},
            io.BytesIO(b""),
        )
        opener = QueueOpener(robots_response(), http_error)
        result = PublicHttpConnector(clock=fixed_clock, opener=opener).capture(
            capture_request(resource_path=None)
        )
        self.assertEqual(result.error_code, "HTTP_RATE_LIMITED")
        self.assertEqual(result.retry_after_seconds, 17.0)

    def test_http_rate_limit_preserves_long_retry_after_for_budget_defer(self):
        http_error = error.HTTPError(
            "https://example.com/public/data",
            429,
            "rate limited",
            {"Retry-After": "600"},
            io.BytesIO(b""),
        )
        opener = QueueOpener(robots_response(), http_error)
        result = PublicHttpConnector(clock=fixed_clock, opener=opener).capture(
            capture_request(resource_path=None)
        )
        self.assertEqual(result.retry_after_seconds, 600.0)

    def test_negative_retry_after_is_invalid_but_does_not_escape_capture(self):
        http_error = error.HTTPError(
            "https://example.com/public/data",
            429,
            "rate limited",
            {"Retry-After": "-1"},
            io.BytesIO(b""),
        )
        opener = QueueOpener(robots_response(), http_error)
        result = PublicHttpConnector(clock=fixed_clock, opener=opener).capture(
            capture_request(resource_path=None)
        )
        self.assertEqual(result.error_code, "HTTP_RATE_LIMITED")
        self.assertIsNone(result.retry_after_seconds)

    def test_http_error_preserves_validated_final_url(self):
        http_error = error.HTTPError(
            "https://example.com/redirected/rate",
            429,
            "rate limited",
            {"Retry-After": "5"},
            io.BytesIO(b""),
        )
        opener = QueueOpener(robots_response(), http_error)
        result = PublicHttpConnector(clock=fixed_clock, opener=opener).capture(
            capture_request(
                source_url="https://example.com/original",
                resource_path=None,
            )
        )
        self.assertEqual(result.final_url, "https://example.com/redirected/rate")
        self.assertEqual(result.retry_after_seconds, 5.0)

    def test_http_error_outside_allowlist_is_blocked(self):
        http_error = error.HTTPError(
            "https://evil.example/rate",
            429,
            "rate limited",
            {"Retry-After": "5"},
            io.BytesIO(b""),
        )
        opener = QueueOpener(robots_response(), http_error)
        result = PublicHttpConnector(clock=fixed_clock, opener=opener).capture(
            capture_request(resource_path=None)
        )
        self.assertEqual(result.error_code, "REDIRECT_OUTSIDE_ALLOWLIST")
        self.assertIsNone(result.retry_after_seconds)

    def test_robots_rate_limit_preserves_retry_after_without_page_request(self):
        robots_429 = error.HTTPError(
            "https://example.com/robots.txt",
            429,
            "rate limited",
            {"Retry-After": "19"},
            io.BytesIO(b""),
        )
        opener = QueueOpener(robots_429)
        result = PublicHttpConnector(clock=fixed_clock, opener=opener).capture(
            capture_request(resource_path=None)
        )
        self.assertEqual(result.error_code, "HTTP_RATE_LIMITED")
        self.assertEqual(result.retry_after_seconds, 19.0)
        self.assertIn("ROBOTS_ENDPOINT_RATE_LIMITED", result.limitations)
        self.assertEqual(result.robots_policy_receipt.decision, "RETRYABLE_RATE_LIMIT")
        self.assertEqual(result.robots_policy_receipt.http_status, 429)
        self.assertEqual(len(opener.calls), 1)

    def test_robots_auth_and_gone_statuses_require_access_review(self):
        for status in (401, 403, 410):
            with self.subTest(status=status):
                failure = error.HTTPError(
                    "https://example.com/robots.txt",
                    status,
                    "blocked",
                    {},
                    io.BytesIO(b""),
                )
                result = PublicHttpConnector(
                    clock=fixed_clock, opener=QueueOpener(failure)
                ).capture(capture_request(resource_path=None))
                self.assertEqual(result.state, "BLOCKED")
                self.assertEqual(result.error_code, "ACCESS_REVIEW_REQUIRED")
                self.assertEqual(result.robots_policy_receipt.http_status, status)
                self.assertFalse(result.captured)

    def test_robots_server_and_tls_failures_are_temporarily_unreachable(self):
        cases = (
            error.HTTPError(
                "https://example.com/robots.txt",
                503,
                "unavailable",
                {},
                io.BytesIO(b""),
            ),
            error.URLError(ssl.SSLError("certificate verify failed")),
        )
        for failure in cases:
            with self.subTest(failure=type(failure).__name__):
                result = PublicHttpConnector(
                    clock=fixed_clock, opener=QueueOpener(failure)
                ).capture(capture_request(resource_path=None))
                self.assertEqual(result.state, "ERROR")
                self.assertEqual(result.error_code, "ROBOTS_UNREACHABLE")
                receipt = result.robots_policy_receipt.to_dict()
                self.assertEqual(receipt["decision"], "ROBOTS_UNREACHABLE")
                self.assertIn("HEALTH_PROBE_REQUIRED", receipt["access_gates"])

    def test_robots_receipt_records_redirect_metadata_and_redacts_query(self):
        redirected = FakeResponse(
            b"User-agent: *\nDisallow:\n",
            "https://cdn.example.com/robots.txt",
            headers={"Content-Type": "text/plain"},
        )
        opener = QueueOpener(
            redirected,
            FakeResponse(b"ok", "https://example.com/public/data", headers={"Content-Type": "text/plain"}),
        )
        result = PublicHttpConnector(clock=fixed_clock, opener=opener).capture(
            capture_request(resource_path=None)
        )
        receipt = result.robots_policy_receipt.to_dict()
        self.assertEqual(receipt["http_status"], 200)
        self.assertEqual(
            receipt["redirect_chain"],
            ["https://example.com/robots.txt", "https://cdn.example.com/robots.txt"],
        )
        self.assertEqual(receipt["origin"], "https://example.com/")
        digest = receipt.pop("receipt_sha256")
        self.assertEqual(digest, sha256_bytes(ingestion.canonical_json_bytes(receipt)))

        signed_query_key = "X-Amz-" + "Signature"
        signed = FakeResponse(
            b"ignored",
            f"https://example.com/robots.txt?{signed_query_key}=never-store-this",
        )
        blocked = PublicHttpConnector(
            clock=fixed_clock, opener=QueueOpener(signed)
        ).capture(capture_request(resource_path=None))
        serialized = json.dumps(blocked.robots_policy_receipt.to_dict())
        self.assertEqual(blocked.error_code, "ROBOTS_REDIRECT_BLOCKED")
        self.assertNotIn("never-store-this", serialized)
        self.assertIn("__kubo_query_sha256", serialized)

    def test_robots_cache_is_dated_bounded_and_revalidated_after_expiry(self):
        current = [FIXED_TIME]

        def clock() -> datetime:
            return current[0]

        opener = QueueOpener(
            robots_response(),
            FakeResponse(b"first", "https://example.com/public/data", headers={"Content-Type": "text/plain"}),
            FakeResponse(b"cached", "https://example.com/public/data", headers={"Content-Type": "text/plain"}),
            FakeResponse(
                b"User-agent: *\nDisallow:\n",
                "https://example.com/robots.txt",
                headers={"Content-Type": "text/plain"},
            ),
            FakeResponse(b"second", "https://example.com/public/data", headers={"Content-Type": "text/plain"}),
        )
        connector = PublicHttpConnector(clock=clock, opener=opener)
        first = connector.capture(capture_request(resource_path=None))
        cached = connector.capture(capture_request(resource_path=None))
        self.assertFalse(first.robots_policy_receipt.cache_hit)
        self.assertTrue(cached.robots_policy_receipt.cache_hit)
        self.assertLessEqual(
            cached.robots_policy_receipt.cache_expires_at
            - cached.robots_policy_receipt.fetched_at,
            timedelta(hours=24),
        )
        self.assertEqual(len(opener.calls), 3)

        current[0] = FIXED_TIME + timedelta(hours=25)
        refreshed = connector.capture(capture_request(resource_path=None))
        self.assertFalse(refreshed.robots_policy_receipt.cache_hit)
        self.assertEqual(refreshed.content, b"second")
        self.assertEqual(len(opener.calls), 5)

    def test_redirect_handler_blocks_sixth_redirect_loop_and_unregistered_domain(self):
        handler = ingestion._AllowlistRedirectHandler(("example.com",))
        current = ingestion.request.Request("https://example.com/start")
        handler.reset_trace(current.full_url)
        for index in range(5):
            current = handler.redirect_request(
                current, None, 302, "redirect", {}, f"/step-{index}"
            )
        with self.assertRaisesRegex(ingestion._RedirectPolicyError, "REDIRECT_LIMIT_EXCEEDED"):
            handler.redirect_request(current, None, 302, "redirect", {}, "/step-6")

        loop_handler = ingestion._AllowlistRedirectHandler(("example.com",))
        original = ingestion.request.Request("https://example.com/start")
        redirected_request = loop_handler.redirect_request(
            original, None, 302, "redirect", {}, "/next"
        )
        with self.assertRaisesRegex(ingestion._RedirectPolicyError, "REDIRECT_LOOP"):
            loop_handler.redirect_request(
                redirected_request, None, 302, "redirect", {}, "/start"
            )

        with self.assertRaisesRegex(
            ingestion._RedirectPolicyError, "UNREGISTERED_REDIRECT_DOMAIN"
        ):
            handler.redirect_request(
                ingestion.request.Request("https://example.com/start"),
                None,
                302,
                "redirect",
                {},
                "https://attacker.invalid/robots.txt",
            )

    def test_writer_persists_robots_receipt_without_promoting_collection(self):
        opener = QueueOpener(
            robots_response(),
            FakeResponse(b"raw", "https://example.com/public/data", headers={"Content-Type": "text/plain"}),
        )
        result = PublicHttpConnector(clock=fixed_clock, opener=opener).capture(
            capture_request(resource_path=None)
        )
        with tempfile.TemporaryDirectory() as directory:
            CapturePacketWriter(Path(directory) / "run").write((result,))
            payload = json.loads(
                (Path(directory) / "run" / "robots-policy-receipts.json").read_text()
            )
        self.assertEqual(len(payload["receipts"]), 1)
        self.assertFalse(payload["claim_boundaries"]["access_receipt_proves_collection"])
        self.assertEqual(result.query_status, "DATA_QUALITY_REJECTED")

    def test_expired_or_miskeyed_access_grant_cannot_authorize_missing_robots(self):
        expired = RobotsAccessGrant(
            source_id="fixture_source",
            registry_id="reviewed-robots-access-v1",
            registry_sha256="b" * 64,
            rights_status="PERMITTED",
            terms_status="REVIEWED_PERMITTED",
            public_access_status="CONFIRMED_PUBLIC",
            reviewed_at=FIXED_TIME - timedelta(days=2),
            expires_at=FIXED_TIME - timedelta(days=1),
        )
        gone = error.HTTPError(
            "https://example.com/robots.txt", 410, "Gone", {}, io.BytesIO(b"")
        )
        result = PublicHttpConnector(
            clock=fixed_clock,
            opener=QueueOpener(gone),
            robots_access_grants={"fixture_source": expired},
        ).capture(capture_request(resource_path=None))
        self.assertEqual(result.error_code, "ACCESS_REVIEW_REQUIRED")
        self.assertEqual(result.robots_policy_receipt.access_gates, ("ACCESS_GRANT_EXPIRED",))

        with self.assertRaisesRegex(ValueError, "keyed"):
            PublicHttpConnector(
                robots_access_grants={"different_source": robots_access_grant()}
            )
        with self.assertRaisesRegex(ValueError, "no greater than 24"):
            PublicHttpConnector(robots_cache_ttl=timedelta(hours=24, seconds=1))
        with self.assertRaisesRegex(TypeError, "timedelta"):
            PublicHttpConnector(robots_cache_ttl="24 hours")

    def test_robots_receipt_rejects_unredacted_urls_and_expired_cache_claims(self):
        opener = QueueOpener(
            robots_response(),
            FakeResponse(b"raw", "https://example.com/public/data", headers={"Content-Type": "text/plain"}),
        )
        receipt = PublicHttpConnector(clock=fixed_clock, opener=opener).capture(
            capture_request(resource_path=None)
        ).robots_policy_receipt
        credential_part = "user" + ":" + "pass" + "word" + "@"
        sensitive_key = "to" + "ken"
        unsafe = (
            "https://"
            + credential_part
            + "example.com/robots.txt?"
            + sensitive_key
            + "=secret"
        )
        with self.assertRaisesRegex(ValueError, "unsafe|sanitized"):
            replace(
                receipt,
                final_url=unsafe,
                redirect_chain=(receipt.robots_url, unsafe),
            )
        with self.assertRaisesRegex(ValueError, "expired cache"):
            replace(
                receipt,
                cache_hit=True,
                evaluated_at=receipt.cache_expires_at,
            )
        with self.assertRaisesRegex(ValueError, "retry delay"):
            replace(receipt, retry_after_seconds=1.0)

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
