from __future__ import annotations

import builtins
from unittest import mock
import unittest

from kubo.workflow_yaml import WorkflowYamlError, load_workflow_yaml


class WorkflowYamlTests(unittest.TestCase):
    def test_base_loader_preserves_github_yaml_words_as_strings(self) -> None:
        payload = load_workflow_yaml(
            b"on:\n  workflow_dispatch:\n    required: true\n    default: false\n",
            field="workflow",
        )
        self.assertEqual(
            payload,
            {
                "on": {
                    "workflow_dispatch": {
                        "required": "true",
                        "default": "false",
                    }
                }
            },
        )

    def test_duplicate_keys_are_rejected(self) -> None:
        with self.assertRaisesRegex(WorkflowYamlError, "duplicate key: on"):
            load_workflow_yaml(
                b"on: {workflow_dispatch: {}}\non: {schedule: []}\n",
                field="workflow",
            )

    def test_aliases_are_rejected(self) -> None:
        with self.assertRaisesRegex(WorkflowYamlError, "aliases are not admitted"):
            load_workflow_yaml(
                b"one: &shared {contents: read}\ntwo: *shared\n",
                field="workflow",
            )

    def test_scalar_aliases_and_explicit_tags_are_rejected(self) -> None:
        for content in (
            b"name: &shared hello\ncopy: *shared\n",
            b"name: !custom hello\n",
            b"name: !!str hello\n",
        ):
            with self.subTest(content=content):
                with self.assertRaisesRegex(
                    WorkflowYamlError, "aliases are not admitted|explicit tags"
                ):
                    load_workflow_yaml(content, field="workflow")

    def test_missing_pyyaml_dependency_fails_closed(self) -> None:
        original_import = builtins.__import__

        def import_without_yaml(name, *args, **kwargs):
            if name == "yaml":
                raise ImportError("intentionally unavailable")
            return original_import(name, *args, **kwargs)

        with mock.patch("builtins.__import__", side_effect=import_without_yaml):
            with self.assertRaisesRegex(WorkflowYamlError, "pinned PyYAML"):
                load_workflow_yaml(b"on: {}\n", field="workflow")


if __name__ == "__main__":
    unittest.main()
