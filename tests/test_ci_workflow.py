from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CiWorkflowTests(unittest.TestCase):
    def test_pull_request_checkout_is_exact_head_with_history(self) -> None:
        text = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn(
            "ref: ${{ github.event.pull_request.head.sha || github.sha }}",
            text,
        )
        self.assertIn("fetch-depth: 0", text)
        self.assertIn("persist-credentials: false", text)


if __name__ == "__main__":
    unittest.main()
