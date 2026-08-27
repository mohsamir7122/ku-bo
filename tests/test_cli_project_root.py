from __future__ import annotations

from contextlib import redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from kubo.cli_v3 import main


ROOT = Path(__file__).resolve().parents[1]


class CliProjectRootTests(unittest.TestCase):
    def test_installed_layout_without_checkout_fails_with_actionable_message(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            invalid_root = Path(temp) / "installed-wheel-layout"
            with patch("kubo.cli_v3._root", return_value=invalid_root):
                with self.assertRaises(SystemExit) as raised:
                    main(["validate-config"])
        message = str(raised.exception)
        self.assertIn("project root is invalid", message)
        self.assertIn("--project-root /path/to/ku-bo", message)

    def test_explicit_checkout_root_runs_from_cli_contract(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(["--project-root", str(ROOT), "validate-source-network"])
        self.assertEqual(code, 0)
        self.assertIn('"status": "PASS"', output.getvalue())

    def test_validate_config_includes_locked_scope_and_migrated_capabilities(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(["--project-root", str(ROOT), "validate-config"])

        rendered = output.getvalue()
        self.assertEqual(code, 0)
        self.assertIn('"market_scope": {', rendered)
        self.assertIn('"source_fallback_policy": {', rendered)
        self.assertIn('"predecessor_capability_parity": {', rendered)
        self.assertIn('"resolved_callable_count": 15', rendered)


if __name__ == "__main__":
    unittest.main()
