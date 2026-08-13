from __future__ import annotations

import ast
import copy
import json
from pathlib import Path
import tempfile
from typing import Mapping
import unittest
from unittest.mock import patch

from kubo import ku_bo_011_adapter as adapter


ROOT = Path(__file__).resolve().parents[1]
CORPUS_PATH = ROOT / "tests" / "corpus" / "ku_bo_011_cases.jsonl"
BOUNDARIES = (
    "import_official_foundation",
    "import_user_price_exports",
    "import_status_corporate",
    "import_ca_enrichment",
    "import_status_history",
    "import_benchmark_history",
    "import_official_eod",
    "build_data_foundation_packet",
)
CHANNELS = (
    ("CLI_ARGUMENT", 0, "ENTRY_PRE_WRITE"),
    ("DIRECT_API_OBJECT", 1, "ENTRY_PRE_WRITE"),
    ("SERIALIZED_ARTIFACT", 2, "ARTIFACT_VALIDATION_PRE_WRITE"),
    ("FILESYSTEM_RACE", 3, "PRE_COMMIT_RECHECK"),
)


def _missing_receipt_materialization(
    input_channel: str,
    variant_index: int,
) -> dict[str, object]:
    ingress = {
        "CLI_ARGUMENT": "CLI_PARSER_TO_PUBLIC_BOUNDARY",
        "DIRECT_API_OBJECT": "DIRECT_PUBLIC_BOUNDARY",
        "SERIALIZED_ARTIFACT": "SERIALIZED_ADMISSION_TO_PUBLIC_BOUNDARY",
        "FILESYSTEM_RACE": "PUBLIC_BOUNDARY_PRE_COMMIT_HOOK",
    }[input_channel]
    timing = {
        "CLI_ARGUMENT": "BEFORE_CLI_PARSE_AND_PUBLIC_BOUNDARY",
        "DIRECT_API_OBJECT": "BEFORE_DIRECT_PUBLIC_BOUNDARY",
        "SERIALIZED_ARTIFACT": "BEFORE_SERIALIZED_ARTIFACT_ADMISSION",
        "FILESYSTEM_RACE": "PUBLIC_BOUNDARY_PRE_COMMIT_RECHECK",
    }[input_channel]
    request_surface = variant_index < 2
    return {
        "handler_id": "missing_run_receipt",
        "ingress": ingress,
        "artifact": (
            "BOUNDARY_ADMISSION_REQUEST" if request_surface else "RUN_RECEIPT_FILE"
        ),
        "field": "/receipt_path" if request_surface else "/",
        "action": "SET_REQUEST_PATH_NONE" if request_surface else "DELETE_FILE",
        "timing": timing,
        "resign_policy": "NOT_APPLICABLE",
        "value": None,
    }


def _missing_receipt_case(
    *,
    boundary_id: str,
    boundary_index: int,
    input_channel: str,
    variant_index: int,
) -> dict[str, object]:
    return {
        "case_id": f"adapter-{boundary_index:02d}-{variant_index}",
        "boundary": {"id": boundary_id},
        "mutation": {
            "id": "missing_run_receipt",
            "input_channel": input_channel,
            "variant_index": variant_index,
        },
        "materialization": _missing_receipt_materialization(
            input_channel,
            variant_index,
        ),
        "context": {
            "target_run_id": (
                f"ku-bo-011-adapter-{boundary_index:02d}-{variant_index}"
            ),
            "evaluation_time": "2026-08-13T10:00:00+03:00",
        },
    }


class KUBO011ProductionAdapterTests(unittest.TestCase):
    def test_adapter_source_has_no_corpus_expected_or_mutator_oracle(self) -> None:
        source_path = Path(adapter.__file__).resolve()
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        imported_modules: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported_modules.add(node.module or "")

        prohibited_imports = {
            module
            for module in imported_modules
            if module == "tests"
            or module.startswith("tests.")
            or "ku_bo_011_mutators" in module
            or "ku_bo_011_harness" in module
        }
        self.assertEqual(prohibited_imports, set())
        self.assertNotIn(
            "MUTATIONS",
            {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)},
        )

        oracle_accesses: list[int] = []
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Subscript)
                and isinstance(node.slice, ast.Constant)
                and node.slice.value == "expected"
            ):
                oracle_accesses.append(node.lineno)
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "get"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == "expected"
            ):
                oracle_accesses.append(node.lineno)
        self.assertEqual(oracle_accesses, [])

    def test_all_boundaries_and_channels_reach_public_boundary_and_channel_gate(
        self,
    ) -> None:
        channel_implementation = {
            "CLI_ARGUMENT": "data_foundation_cli.parser+public_boundary",
            "DIRECT_API_OBJECT": "public_boundary+admit_boundary",
            "SERIALIZED_ARTIFACT": (
                "public_boundary+admit_serialized_boundary"
            ),
            "FILESYSTEM_RACE": "public_boundary+admit_boundary",
        }
        for boundary_index, boundary_id in enumerate(BOUNDARIES):
            for input_channel, variant_index, failure_phase in CHANNELS:
                with self.subTest(
                    boundary_id=boundary_id,
                    input_channel=input_channel,
                ):
                    events: list[tuple[str, dict[str, str]]] = []

                    def capture(
                        event: str,
                        details: Mapping[str, str],
                    ) -> None:
                        events.append((event, dict(details)))

                    with tempfile.TemporaryDirectory() as directory:
                        case_root = Path(directory) / "case"
                        case_root.mkdir()
                        input_root = case_root / "input"
                        input_root.mkdir()
                        output_root = case_root / "output"
                        case = _missing_receipt_case(
                            boundary_id=boundary_id,
                            boundary_index=boundary_index,
                            input_channel=input_channel,
                            variant_index=variant_index,
                        )
                        with patch.object(adapter, "_AUDIT_HOOK", capture):
                            result = adapter.production_adapter(
                                case=case,
                                case_root=case_root,
                                input_root=input_root,
                                output_root=output_root,
                            )

                    self.assertEqual(result["failure_code"], "RUN_RECEIPT_REQUIRED")
                    self.assertEqual(result["failure_phase"], failure_phase)
                    self.assertEqual(result["output_writes"], [])
                    channel_events = [
                        (index, details)
                        for index, (event, details) in enumerate(events)
                        if event == "channel_gate"
                    ]
                    boundary_events = [
                        (index, details)
                        for index, (event, details) in enumerate(events)
                        if event == "public_boundary"
                    ]
                    self.assertEqual(len(channel_events), 1, events)
                    self.assertEqual(len(boundary_events), 1, events)
                    channel_index, channel_details = channel_events[0]
                    boundary_event_index, boundary_details = boundary_events[0]
                    self.assertLess(channel_index, boundary_event_index)
                    self.assertEqual(channel_details["boundary_id"], boundary_id)
                    self.assertEqual(
                        channel_details["input_channel"],
                        input_channel,
                    )
                    self.assertEqual(
                        channel_details["implementation"],
                        channel_implementation[input_channel],
                    )
                    self.assertEqual(boundary_details["boundary_id"], boundary_id)
                    self.assertEqual(
                        boundary_details["input_channel"],
                        input_channel,
                    )
                    self.assertIn(
                        adapter._BOUNDARY_FUNCTION_NAMES[boundary_id],
                        boundary_details["implementation"],
                    )

    def test_all_1280_corpus_descriptors_match_adapter_contract(self) -> None:
        count = 0
        boundaries: set[str] = set()
        handlers: set[str] = set()
        channels: set[str] = set()
        with CORPUS_PATH.open("r", encoding="utf-8") as corpus:
            for line in corpus:
                case = json.loads(line)
                mutation = case["mutation"]
                adapter._validate_materialization_descriptor(
                    case["materialization"],
                    handler_id=mutation["id"],
                    input_channel=mutation["input_channel"],
                    variant_index=mutation["variant_index"],
                )
                count += 1
                boundaries.add(case["boundary"]["id"])
                handlers.add(mutation["id"])
                channels.add(mutation["input_channel"])

        self.assertEqual(count, 1_280)
        self.assertEqual(boundaries, set(BOUNDARIES))
        self.assertEqual(len(handlers), 40)
        self.assertEqual(channels, {channel for channel, _, _ in CHANNELS})

    def test_action_and_value_canaries_fail_before_materialization(self) -> None:
        case = _missing_receipt_case(
            boundary_id="import_official_foundation",
            boundary_index=0,
            input_channel="CLI_ARGUMENT",
            variant_index=0,
        )
        for field, replacement in (
            ("action", "DELETE_FILE"),
            ("value", "CLI_OPTION_ABSENT"),
        ):
            with self.subTest(field=field):
                tampered = copy.deepcopy(case)
                tampered["materialization"][field] = replacement  # type: ignore[index]
                with tempfile.TemporaryDirectory() as directory:
                    case_root = Path(directory) / "case"
                    case_root.mkdir()
                    input_root = case_root / "input"
                    input_root.mkdir()
                    with patch.object(
                        adapter,
                        "_BaselineMaterializer",
                        side_effect=AssertionError(
                            "descriptor validation must precede materialization"
                        ),
                    ) as materializer:
                        with self.assertRaisesRegex(
                            adapter.ProductionAdapterError,
                            f"materialization {field} differs",
                        ):
                            adapter.production_adapter(
                                case=tampered,
                                case_root=case_root,
                                input_root=input_root,
                                output_root=case_root / "output",
                            )
                    materializer.assert_not_called()

    def test_materializer_uses_three_independent_runtime_authorities(self) -> None:
        keys = (b"r" * 32, b"s" * 32, b"m" * 32)
        supplied_keys = iter(keys)
        original_token_bytes = adapter.secrets.token_bytes

        def deterministic_authorities(size: int) -> bytes:
            try:
                return next(supplied_keys)
            except StopIteration:
                return original_token_bytes(size)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_root = root / "input"
            input_root.mkdir()
            with patch.object(
                adapter.secrets,
                "token_bytes",
                side_effect=deterministic_authorities,
            ):
                materializer = adapter._BaselineMaterializer(
                    case_root=root / "materialized",
                    target_input_root=input_root,
                    target_boundary_id="import_official_foundation",
                    run_id="ku-bo-011-independent-authorities",
                    decision_at="2026-08-13T10:00:00+03:00",
                )
            request = materializer.request("import_official_foundation")

        self.assertEqual(
            (request.run_key, request.v1_stage_key, request.semantic_key),
            keys,
        )
        self.assertEqual(
            len({request.run_key, request.v1_stage_key, request.semantic_key}),
            3,
        )
        self.assertEqual(
            len(
                {
                    request.run_key_id,
                    request.v1_stage_key_id,
                    request.semantic_key_id,
                }
            ),
            3,
        )


if __name__ == "__main__":
    unittest.main()
