from __future__ import annotations

import base64
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from kubo.cli_v3 import ISSUER_CHECKPOINT_V2_HMAC_ENV, main, parser
from tests.test_issuer_checkpoint_v2 import SEAL_KEY, SEAL_KEY_ID, seal_full_fixture


ROOT = Path(__file__).resolve().parents[1]


class IssuerCheckpointV2CliTests(unittest.TestCase):
    def test_command_help_exposes_only_paths_and_key_identifier(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output), self.assertRaises(SystemExit) as caught:
            parser().parse_args(["validate-issuer-checkpoint-v2", "--help"])
        self.assertEqual(caught.exception.code, 0)
        rendered = output.getvalue()
        self.assertIn("--checkpoint-root", rendered)
        self.assertIn("--expected-key-id", rendered)
        self.assertNotIn("--key", rendered)
        self.assertNotIn("--secret", rendered)

    def test_missing_environment_key_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store, _plan, _report = seal_full_fixture(Path(temp))
            store.close()
            with patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(
                ValueError, ISSUER_CHECKPOINT_V2_HMAC_ENV
            ):
                main(
                    [
                        "--project-root",
                        str(ROOT),
                        "validate-issuer-checkpoint-v2",
                        "--checkpoint-root",
                        str(Path(temp) / "checkpoint"),
                        "--expected-key-id",
                        SEAL_KEY_ID,
                    ]
                )

    def test_authenticated_fixture_prints_sanitized_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store, _plan, _report = seal_full_fixture(Path(temp))
            store.close()
            output = io.StringIO()
            environment = {
                ISSUER_CHECKPOINT_V2_HMAC_ENV: "base64:"
                + base64.b64encode(SEAL_KEY).decode("ascii")
            }
            with patch.dict(os.environ, environment, clear=False), redirect_stdout(output):
                code = main(
                    [
                        "--project-root",
                        str(ROOT),
                        "validate-issuer-checkpoint-v2",
                        "--checkpoint-root",
                        str(Path(temp) / "checkpoint"),
                        "--expected-key-id",
                        SEAL_KEY_ID,
                    ]
                )

            self.assertEqual(code, 0)
            report = json.loads(output.getvalue())
            self.assertEqual(
                report["status"], "PASS_SYNTHETIC_ONE_SECURITY_TERMINAL_SEAL"
            )
            self.assertEqual(report["terminal_receipt_count"], 29)
            self.assertEqual(report["wave_count"], 7)
            self.assertEqual(report["authenticated_key_id"], SEAL_KEY_ID)
            self.assertNotIn("key", report)
            self.assertNotIn("secret", output.getvalue().lower())
            self.assertNotIn(SEAL_KEY.hex(), output.getvalue())


if __name__ == "__main__":
    unittest.main()
