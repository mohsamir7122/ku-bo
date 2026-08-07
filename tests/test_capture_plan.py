from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from kubo.capture_plan import (
    MAX_CAPTURE_PLAN_BYTES,
    MAX_CAPTURE_PLAN_TASKS,
    MAX_CAPTURE_PLAN_TIMEOUT_SECONDS,
    execute_capture_plan,
)
from kubo.cli_v3 import main
from kubo.source_network import SourceNetworkCatalog


ROOT = Path(__file__).resolve().parents[1]


def capture_task(**overrides) -> dict:
    task = {
        "connector": "file",
        "source_id": "kuna",
        "source_url": "https://www.kuna.net.kw/",
        "roles_observed": ["NEWS_ARCHIVE"],
        "access_mode": "PUBLIC_PAGE",
        "capture_kind": "RAW_PAGE",
        "resource_path": "data",
    }
    task.update(overrides)
    return task


class CapturePlanTests(unittest.TestCase):
    def test_fixture_capture_uses_source_contract_and_writes_raw_packet(self) -> None:
        catalog = SourceNetworkCatalog(ROOT / "config")
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            fixtures = workspace / "fixtures"
            fixtures.mkdir()
            (fixtures / "news.html").write_text("fixture", encoding="utf-8")
            plan = workspace / "plan.json"
            plan.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "tasks": [
                            {
                                "connector": "file",
                                "source_id": "kuna",
                                "source_url": "https://www.kuna.net.kw/",
                                "roles_observed": ["NEWS_ARCHIVE"],
                                "access_mode": "PUBLIC_PAGE",
                                "capture_kind": "RAW_PAGE",
                                "resource_path": "news.html",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            output = workspace / "capture"
            report = execute_capture_plan(
                plan_path=plan,
                output_root=output,
                fixture_root=fixtures,
                catalog=catalog,
            )
            self.assertEqual(report["status"], "COMPLETE")
            self.assertFalse(report["claim_boundaries"]["raw_capture_is_qualified_finding"])
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(len(manifest["artifacts"]), 1)

    def test_plan_cannot_enable_disabled_or_unregistered_source(self) -> None:
        catalog = SourceNetworkCatalog(ROOT / "config")
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            fixtures = workspace / "fixtures"
            fixtures.mkdir()
            (fixtures / "data").write_text("x", encoding="utf-8")
            for source_id in ("not_registered", "licensed_execution_feed"):
                with self.subTest(source_id=source_id):
                    plan = workspace / f"{source_id}.json"
                    plan.write_text(
                        json.dumps(
                            {
                                "schema_version": "1.0",
                                "tasks": [
                                    {
                                        "connector": "file",
                                        "source_id": source_id,
                                        "source_url": "https://example.com/",
                                        "roles_observed": ["EXECUTION_TAPE"],
                                        "resource_path": "data",
                                    }
                                ],
                            }
                        ),
                        encoding="utf-8",
                    )
                    with self.assertRaises(ValueError):
                        execute_capture_plan(
                            plan_path=plan,
                            output_root=workspace / "out",
                            fixture_root=fixtures,
                            catalog=catalog,
                        )

    def test_cli_capture_command(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "capture"
            code = main(
                [
                    "--project-root",
                    str(ROOT),
                    "capture",
                    "--plan",
                    str(ROOT / "examples" / "capture_plan.json"),
                    "--fixture-root",
                    str(ROOT / "examples" / "synthetic_source_network_run"),
                    "--output-root",
                    str(output),
                ]
            )
            self.assertEqual(code, 0)
            self.assertTrue((output / "manifest.json").is_file())

    def test_plan_wide_resource_limits_fail_before_connectors_or_writes(self) -> None:
        byte_tasks = [capture_task(max_bytes=50 * 1024 * 1024) for _ in range(3)]
        self.assertGreater(sum(task["max_bytes"] for task in byte_tasks), MAX_CAPTURE_PLAN_BYTES)
        timeout_tasks = [capture_task(timeout_seconds=60) for _ in range(6)]
        self.assertGreater(
            sum(task["timeout_seconds"] for task in timeout_tasks),
            MAX_CAPTURE_PLAN_TIMEOUT_SECONDS,
        )
        cases = (
            (
                "tasks",
                [capture_task() for _ in range(MAX_CAPTURE_PLAN_TASKS + 1)],
                "task limit",
            ),
            ("bytes", byte_tasks, "max_bytes total"),
            ("timeout", timeout_tasks, "timeout_seconds total"),
        )

        catalog = SourceNetworkCatalog(ROOT / "config")
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            fixtures = workspace / "fixtures"
            fixtures.mkdir()
            (fixtures / "data").write_text("must not be read", encoding="utf-8")
            for name, tasks, error in cases:
                with self.subTest(limit=name):
                    plan = workspace / f"{name}.json"
                    plan.write_text(
                        json.dumps({"schema_version": "1.0", "tasks": tasks}),
                        encoding="utf-8",
                    )
                    output = workspace / f"output-{name}"
                    with (
                        mock.patch("kubo.capture_plan.FileConnector") as file_connector,
                        mock.patch("kubo.capture_plan.PublicHttpConnector") as http_connector,
                        mock.patch("kubo.capture_plan.capture_sources") as capture,
                        mock.patch("kubo.capture_plan.CapturePacketWriter") as writer,
                    ):
                        with self.assertRaisesRegex(ValueError, error):
                            execute_capture_plan(
                                plan_path=plan,
                                output_root=output,
                                fixture_root=fixtures,
                                catalog=catalog,
                            )
                    file_connector.assert_not_called()
                    http_connector.assert_not_called()
                    capture.assert_not_called()
                    writer.assert_not_called()
                    self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
