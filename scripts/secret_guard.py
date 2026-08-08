from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys


ALLOW_MARKER = "secret-guard: allow"
IGNORED_DIRECTORIES = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".nox",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "env",
        "htmlcov",
        "runtime",
        "venv",
    }
)
SENSITIVE_FILE_SUFFIXES = frozenset({".jks", ".key", ".keystore", ".p12", ".pfx"})

SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "private-key",
        re.compile(r"-----BEGIN (?:DSA |EC |OPENSSH |PGP |RSA )?PRIVATE KEY-----"),
    ),
    (
        "github-token",
        re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
    ),
    ("gitlab-token", re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}\b")),
    ("aws-access-key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("google-oauth-secret", re.compile(r"\bGOCSPX-[0-9A-Za-z_-]{20,}\b")),
    ("openai-api-key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b")),
    ("slack-token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("stripe-live-key", re.compile(r"\b(?:rk|sk)_live_[A-Za-z0-9]{16,}\b")),
    ("sendgrid-key", re.compile(r"\bSG\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}\b")),
    ("huggingface-token", re.compile(r"\bhf_[A-Za-z0-9]{20,}\b")),
    ("npm-token", re.compile(r"\bnpm_[A-Za-z0-9]{20,}\b")),
    ("telegram-bot-token", re.compile(r"\b[0-9]{8,12}:[A-Za-z0-9_-]{30,}\b")),
    (
        "jwt",
        re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    ),
    (
        "credential-url",
        re.compile(r"(?:https?|mongodb(?:\+srv)?|mysql|postgres(?:ql)?|redis)://[^\s/@:]+:[^\s/@]+@"),
    ),
    (
        "signed-or-tokenized-url",
        re.compile(
            r"(?i)[?&](?:access_token|signature|token|x-amz-(?:credential|signature)|"
            r"x-goog-(?:credential|signature)|oauth_token|code|jwt)=[^&\s]+"
        ),
    ),
    (
        "credential-assignment",
        re.compile(
            r"(?i)[\"']?[A-Za-z0-9_-]*(?:access[_-]?token|api[_-]?key|auth[_-]?token|"
            r"bearer[_-]?token|client[_-]?secret|hmac[_-]?key|password|passwd|"
            r"private[_-]?key|secret|session(?:id)?|signature|token|cookie|credential)[\"']?\s*[:=]\s*"
            r"[\"'][A-Za-z0-9_./+=:@-]{8,}[\"']"
        ),
    ),
    (
        "credential-unquoted-config-assignment",
        re.compile(
            r"(?i)^\s*[A-Za-z0-9_.-]*(?:access[_-]?token|api[_-]?key|auth[_-]?token|"
            r"bearer[_-]?token|client[_-]?secret|hmac[_-]?key|password|passwd|"
            r"private[_-]?key|secret|session(?:id)?|signature|token|cookie|credential)"
            r"\s*:\s*[A-Za-z0-9_./+=:@-]{8,}\s*(?:#.*)?$"
        ),
    ),
    (
        "credential-environment-assignment",
        re.compile(
            r"^\s*[A-Z0-9_]*(?:ACCESS_TOKEN|API_KEY|AUTH_TOKEN|BEARER_TOKEN|"
            r"CLIENT_SECRET|HMAC_KEY|PASSWORD|PASSWD|PRIVATE_KEY|SECRET|SESSIONID|"
            r"SIGNATURE|TOKEN|COOKIE|CREDENTIAL)\s*=\s*[^\s#]{8,}\s*$"
        ),
    ),
)


def scan(root: Path) -> list[tuple[Path, int, str]]:
    root = root.resolve()
    findings: list[tuple[Path, int, str]] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        if any(part in IGNORED_DIRECTORIES for part in path.relative_to(root).parts):
            continue
        try:
            payload = path.read_bytes()
        except OSError:
            continue
        if path.suffix.casefold() in SENSITIVE_FILE_SUFFIXES:
            findings.append((path.relative_to(root), 0, "credential-file"))
            continue
        if b"\x00" in payload[:8192]:
            continue
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            if ALLOW_MARKER in line:
                continue
            for rule, pattern in SECRET_PATTERNS:
                if pattern.search(line):
                    findings.append((path.relative_to(root), line_number, rule))
    return findings


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description="Fail when repository text contains likely committed secrets")
    value.add_argument("--root", type=Path, default=Path.cwd())
    return value


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    findings = scan(args.root)
    if not findings:
        print("Secret guard: PASS")
        return 0
    for path, line_number, rule in findings:
        print(f"{path}:{line_number}: potential secret ({rule})", file=sys.stderr)
    print(f"Secret guard: FAIL ({len(findings)} finding(s))", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
