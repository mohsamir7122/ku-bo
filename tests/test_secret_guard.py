from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("kubo_secret_guard", ROOT / "scripts" / "secret_guard.py")
assert SPEC is not None and SPEC.loader is not None
SECRET_GUARD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SECRET_GUARD)


class SecretGuardTests(unittest.TestCase):
    def test_repository_has_no_unallowlisted_secret_pattern(self) -> None:
        self.assertEqual(SECRET_GUARD.scan(ROOT), [])

    def test_detects_likely_secret_without_printing_its_value(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            token = "ghp_" + ("A" * 36)
            environment_value = "not-a-real-secret-value"
            (root / "leak.env").write_text(
                "DATABASE_PASSWORD=" + environment_value + "\n",
                encoding="utf-8",
            )
            (root / "leak.txt").write_text("TOKEN=" + token + "\n", encoding="utf-8")
            findings = SECRET_GUARD.scan(root)
        self.assertEqual(
            {(line, rule) for _, line, rule in findings},
            {(1, "credential-environment-assignment"), (1, "github-token")},
        )
        self.assertNotIn(token, repr(findings))
        self.assertNotIn(environment_value, repr(findings))

    def test_explicit_inline_allow_marker_is_narrow(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            token = "ghp_" + ("B" * 36)
            (root / "fixture.txt").write_text(
                token + "  # secret-guard: allow\n",
                encoding="utf-8",
            )
            self.assertEqual(SECRET_GUARD.scan(root), [])

    def test_detects_project_specific_tokens_and_signed_urls(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "runtime.conf").write_text(
                "KUBO_BROKER_FEED_TOKEN=not-a-real-broker-token\n"
                "KUBO_META_COOKIE=not-a-real-cookie\n"
                "KUBO_RUNTIME_CREDENTIAL=not-a-real-credential\n"
                "SOURCE_URL=https://example.test/data?oauth_token=not-a-real-token\n",  # secret-guard: allow — detection fixture
                encoding="utf-8",
            )
            findings = SECRET_GUARD.scan(root)
        self.assertEqual(
            {(line, rule) for _, line, rule in findings},
            {
                (1, "credential-environment-assignment"),
                (2, "credential-environment-assignment"),
                (3, "credential-environment-assignment"),
                (4, "signed-or-tokenized-url"),
            },
        )

    def test_detects_unquoted_yaml_secret_and_binary_credential_container(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "credentials.yml").write_text(
                "broker_feed_token: not-a-real-token-value\n",  # secret-guard: allow — detection fixture
                encoding="utf-8",
            )
            (root / "client.p12").write_bytes(b"\x00not-a-real-credential-container")
            findings = SECRET_GUARD.scan(root)
        self.assertEqual(
            {(path.name, line, rule) for path, line, rule in findings},
            {
                ("credentials.yml", 1, "credential-unquoted-config-assignment"),
                ("client.p12", 0, "credential-file"),
            },
        )


if __name__ == "__main__":
    unittest.main()
