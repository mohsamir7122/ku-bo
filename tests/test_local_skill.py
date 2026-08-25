from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / ".agents" / "skills" / "operate-ku-bo-research" / "SKILL.md"


class LocalSkillTests(unittest.TestCase):
    def test_skill_has_valid_minimal_frontmatter(self) -> None:
        content = SKILL.read_text(encoding="utf-8")
        self.assertTrue(content.startswith("---\n"))
        _, frontmatter, body = content.split("---", 2)
        fields: dict[str, str] = {}
        for line in frontmatter.strip().splitlines():
            key, separator, value = line.partition(":")
            self.assertTrue(separator)
            self.assertNotIn(key, fields)
            fields[key] = value.strip()

        self.assertEqual(set(fields), {"name", "description"})
        self.assertRegex(fields["name"], r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
        self.assertLessEqual(len(fields["name"]), 64)
        self.assertTrue(fields["description"])
        self.assertLessEqual(len(fields["description"]), 1024)
        self.assertNotIn("[TODO:", body)

    def test_skill_routes_only_to_canonical_guarded_workflows(self) -> None:
        content = SKILL.read_text(encoding="utf-8")

        for required in (
            "validate-config",
            "validate-source-fallback-policy",
            "plan-source-fallback",
            "validate-portfolio-state",
            "validate-factor9-admission",
            "validate-ku-bo-live-program",
            "run-live-dry-run",
            "evaluate-forty-session-replay",
            "validate-predecessor-capability-parity",
            "PRIVATE_PREDECESSOR_SOURCE",
        ):
            with self.subTest(required=required):
                self.assertIn(required, content)
        self.assertNotIn("github.com/", content.casefold())
        self.assertIsNone(re.search(r"\b[0-9a-f]{40}\b", content, re.IGNORECASE))


if __name__ == "__main__":
    unittest.main()
