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
from kubo.ingestion import (
    FileConnector as RealFileConnector,
    capture_sources as real_capture_sources,
)
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
    def test_plan_rejects_metadata_fields_the_executor_does_not_use(self) -> None:
        catalog = SourceNetworkCatalog(ROOT / "config")
        cases = (
            (
                "top-level-scope",
                {"schema_version": "1.0", "scope": "IGNORED", "tasks": [capture_task()]},
                "unknown capture-plan fields",
            ),
            (
                "symbol-binding",
                {
                    "schema_version": "1.0",
                    "tasks": [capture_task(symbol_binding={"security_code": "108"})],
                },
                "unknown fields: symbol_binding",
            ),
            (
                "unsupported-max-requests",
                {
                    "schema_version": "1.0",
                    "max_requests": 1,
                    "tasks": [capture_task()],
                },
                "does not accept max_requests budgets",
            ),
            (
                "unsupported-budget-object",
                {
                    "schema_version": "1.0",
                    "budget": {"max_requests": 1},
                    "tasks": [capture_task()],
                },
                "does not accept max_requests budgets",
            ),
        )
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            fixtures = workspace / "fixtures"
            fixtures.mkdir()
            (fixtures / "data").write_text("must not be read", encoding="utf-8")
            for name, payload, error in cases:
                with self.subTest(name=name):
                    plan = workspace / f"{name}.json"
                    plan.write_text(json.dumps(payload), encoding="utf-8")
                    output = workspace / f"output-{name}"
                    with self.assertRaisesRegex(ValueError, error):
                        execute_capture_plan(
                            plan_path=plan,
                            output_root=output,
                            fixture_root=fixtures,
                            catalog=catalog,
                        )
                    self.assertFalse(output.exists())

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
            self.assertFalse(
                report["claim_boundaries"]["capture_task_limit_is_network_request_budget"]
            )
            self.assertFalse(
                report["claim_boundaries"]["network_request_budget_enforced"]
            )
            self.assertEqual(
                report["capture_accounting"],
                {
                    "max_tasks": MAX_CAPTURE_PLAN_TASKS,
                    "planned_tasks": 1,
                    "capture_results": 1,
                    "public_http_tasks": 0,
                    "file_tasks": 1,
                },
            )
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(len(manifest["artifacts"]), 1)
            self.assertFalse((output / ".kubo-capture-plan-reservation").exists())

    def test_existing_empty_output_is_reserved_but_completed_output_cannot_be_reused(self) -> None:
        catalog = SourceNetworkCatalog(ROOT / "config")
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            fixtures = workspace / "fixtures"
            fixtures.mkdir()
            (fixtures / "data").write_text("first", encoding="utf-8")
            plan = workspace / "plan.json"
            plan.write_text(
                json.dumps({"schema_version": "1.0", "tasks": [capture_task()]}),
                encoding="utf-8",
            )
            output = workspace / "capture"
            output.mkdir()

            def connector_while_reserved(root: Path):
                self.assertEqual(
                    [path.name for path in output.iterdir()],
                    [".kubo-capture-plan-reservation"],
                )
                return RealFileConnector(root)

            with mock.patch(
                "kubo.capture_plan.FileConnector",
                side_effect=connector_while_reserved,
            ):
                report = execute_capture_plan(
                    plan_path=plan,
                    output_root=output,
                    fixture_root=fixtures,
                    catalog=catalog,
                )
            self.assertEqual(report["status"], "COMPLETE")
            before = {
                path.relative_to(output).as_posix(): path.read_bytes()
                for path in output.rglob("*")
                if path.is_file()
            }

            (fixtures / "data").write_text("second", encoding="utf-8")
            with (
                mock.patch("kubo.capture_plan.FileConnector") as file_connector,
                mock.patch("kubo.capture_plan.PublicHttpConnector") as http_connector,
                mock.patch("kubo.capture_plan.capture_sources") as capture,
                mock.patch("kubo.capture_plan.CapturePacketWriter") as writer,
            ):
                with self.assertRaisesRegex(ValueError, "output_root must be empty"):
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
            after = {
                path.relative_to(output).as_posix(): path.read_bytes()
                for path in output.rglob("*")
                if path.is_file()
            }
            self.assertEqual(after, before)

    def test_non_directory_and_symlink_output_roots_fail_closed(self) -> None:
        catalog = SourceNetworkCatalog(ROOT / "config")
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            fixtures = workspace / "fixtures"
            fixtures.mkdir()
            (fixtures / "data").write_text("must not be read", encoding="utf-8")
            plan = workspace / "plan.json"
            plan.write_text(
                json.dumps({"schema_version": "1.0", "tasks": [capture_task()]}),
                encoding="utf-8",
            )
            occupied_file = workspace / "occupied-file"
            occupied_file.write_text("sentinel", encoding="utf-8")
            target = workspace / "target"
            target.mkdir()
            symlink = workspace / "symlink"
            symlink.symlink_to(target, target_is_directory=True)

            for output in (occupied_file, symlink):
                with self.subTest(output=output.name):
                    with (
                        mock.patch("kubo.capture_plan.FileConnector") as file_connector,
                        mock.patch("kubo.capture_plan.PublicHttpConnector") as http_connector,
                        mock.patch("kubo.capture_plan.capture_sources") as capture,
                        mock.patch("kubo.capture_plan.CapturePacketWriter") as writer,
                    ):
                        with self.assertRaisesRegex(
                            ValueError,
                            "new or empty directory|parent contains a symlink",
                        ):
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

    def test_parent_symlink_is_rejected_before_connector_or_write(self) -> None:
        catalog = SourceNetworkCatalog(ROOT / "config")
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            fixtures = workspace / "fixtures"
            fixtures.mkdir()
            (fixtures / "data").write_text("must not be read", encoding="utf-8")
            plan = workspace / "plan.json"
            plan.write_text(
                json.dumps({"schema_version": "1.0", "tasks": [capture_task()]}),
                encoding="utf-8",
            )
            real_parent = workspace / "real-parent"
            real_parent.mkdir()
            link_parent = workspace / "link-parent"
            link_parent.symlink_to(real_parent, target_is_directory=True)

            with (
                mock.patch("kubo.capture_plan.FileConnector") as file_connector,
                mock.patch("kubo.capture_plan.PublicHttpConnector") as http_connector,
                mock.patch("kubo.capture_plan.capture_sources") as capture,
                mock.patch("kubo.capture_plan.CapturePacketWriter") as writer,
            ):
                with self.assertRaisesRegex(
                    ValueError,
                    "parent contains a symlink",
                ):
                    execute_capture_plan(
                        plan_path=plan,
                        output_root=link_parent / "run",
                        fixture_root=fixtures,
                        catalog=catalog,
                    )
            file_connector.assert_not_called()
            http_connector.assert_not_called()
            capture.assert_not_called()
            writer.assert_not_called()
            self.assertFalse((real_parent / "run").exists())

    def test_reserved_root_rename_and_replacement_fails_closed(self) -> None:
        catalog = SourceNetworkCatalog(ROOT / "config")
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            fixtures = workspace / "fixtures"
            fixtures.mkdir()
            (fixtures / "data").write_text("descriptor-bound", encoding="utf-8")
            plan = workspace / "plan.json"
            plan.write_text(
                json.dumps({"schema_version": "1.0", "tasks": [capture_task()]}),
                encoding="utf-8",
            )
            output = workspace / "capture"
            moved = workspace / "moved-capture"

            def rename_then_capture(tasks):
                output.rename(moved)
                output.mkdir()
                return real_capture_sources(tasks)

            with mock.patch(
                "kubo.capture_plan.capture_sources",
                side_effect=rename_then_capture,
            ):
                with self.assertRaisesRegex(
                    ValueError,
                    "output_root identity changed during capture",
                ):
                    execute_capture_plan(
                        plan_path=plan,
                        output_root=output,
                        fixture_root=fixtures,
                        catalog=catalog,
                    )

            self.assertFalse((output / "manifest.json").exists())
            self.assertFalse((output / "source_observations.json").exists())
            self.assertEqual(list(output.iterdir()), [])
            self.assertTrue((moved / "manifest.json").is_file())
            self.assertTrue((moved / "source_observations.json").is_file())

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
