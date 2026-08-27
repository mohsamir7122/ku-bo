from __future__ import annotations

import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import kubo.backfill_90d as backfill_module
from kubo.atomic_output import AtomicOutputError
from kubo.backfill_90d import (
    RightsAwareBackfillError,
    build_rights_aware_bundle,
    validate_rights_aware_bundle,
)
from kubo.hashing import canonical_json_bytes, sha256_bytes

from tests.backfill_90d_helpers import (
    CODE_SHA,
    FINISHED_AT,
    ROOT,
    build_fixture_bundle,
    make_receipt,
    read_json,
    read_jsonl,
)


def _digest_without(value: dict[str, object], field: str) -> str:
    material = {key: item for key, item in value.items() if key != field}
    return hashlib.sha256(canonical_json_bytes(material)).hexdigest()


def _rewrite_manifest_inventory(bundle: Path) -> None:
    manifest_path = bundle / "run-manifest.json"
    manifest = read_json(manifest_path)
    inventory: list[dict[str, object]] = []
    for path in sorted(item for item in bundle.rglob("*") if item.is_file() and not item.is_symlink()):
        relative = path.relative_to(bundle).as_posix()
        if relative == "run-manifest.json":
            continue
        content = path.read_bytes()
        if relative.endswith(".jsonl"):
            record_count = len(content.splitlines()) if content else 0
        elif relative.endswith(".json"):
            record_count = 1
        else:
            record_count = 0
        inventory.append(
            {
                "path": relative,
                "sha256": sha256_bytes(content),
                "size_bytes": len(content),
                "record_count": record_count,
            }
        )
    manifest["files"] = inventory
    manifest["manifest_digest"] = _digest_without(manifest, "manifest_digest")
    manifest_path.write_bytes(canonical_json_bytes(manifest))


class RightsAwareBackfillAdversarialTests(unittest.TestCase):
    def _assert_atomic_rejection(self, callback: object, output: Path) -> None:
        with self.assertRaises(AtomicOutputError):
            callback()  # type: ignore[operator]
        self.assertFalse(output.exists())

    def test_duplicate_source_receipts_are_rejected_without_partial_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            receipt = make_receipt(root)
            output = root / "duplicate"
            self._assert_atomic_rejection(
                lambda: build_rights_aware_bundle(
                    ROOT,
                    output,
                    run_id="duplicate-fixture",
                    code_sha=CODE_SHA,
                    scheduled_at="2026-08-27T03:00:00Z",
                    actual_started_at="2026-08-27T03:01:00Z",
                    finished_at=FINISHED_AT,
                    receipt_bindings=[receipt, receipt],
                ),
                output,
            )

    def test_probe_after_known_at_is_rejected_without_partial_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            receipt = make_receipt(root)
            output = root / "future"
            self._assert_atomic_rejection(
                lambda: build_rights_aware_bundle(
                    ROOT,
                    output,
                    run_id="future-fixture",
                    code_sha=CODE_SHA,
                    scheduled_at="2026-08-27T02:00:00Z",
                    actual_started_at="2026-08-27T02:01:00Z",
                    finished_at="2026-08-27T03:04:59Z",
                    receipt_bindings=[receipt],
                ),
                output,
            )

    def test_symlink_plan_is_rejected_without_partial_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan, probe = make_receipt(root)
            plan_link = root / "linked-plan.json"
            plan_link.symlink_to(plan)
            output = root / "symlink-plan"
            self._assert_atomic_rejection(
                lambda: build_rights_aware_bundle(
                    ROOT,
                    output,
                    run_id="symlink-fixture",
                    code_sha=CODE_SHA,
                    scheduled_at="2026-08-27T03:00:00Z",
                    actual_started_at="2026-08-27T03:01:00Z",
                    finished_at=FINISHED_AT,
                    receipt_bindings=[(plan_link, probe)],
                ),
                output,
            )

    def test_symlink_raw_artifact_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan, probe_path = make_receipt(root, readable=True)
            probe = read_json(probe_path)
            raw = probe_path.parent / probe["sources"][0]["artifact"]["path"]
            saved = root / "saved-artifact"
            saved.write_bytes(raw.read_bytes())
            raw.unlink()
            raw.symlink_to(saved)
            output = root / "artifact-symlink"
            self._assert_atomic_rejection(
                lambda: build_rights_aware_bundle(
                    ROOT,
                    output,
                    run_id="artifact-symlink-fixture",
                    code_sha=CODE_SHA,
                    scheduled_at="2026-08-27T03:00:00Z",
                    actual_started_at="2026-08-27T03:01:00Z",
                    finished_at=FINISHED_AT,
                    receipt_bindings=[(plan, probe_path)],
                ),
                output,
            )

    def test_receipt_change_during_canonical_validation_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan, probe = make_receipt(root)
            output = root / "receipt-race"
            canonical_validator = backfill_module.validate_access_probe_against_plan

            def mutate_after_validation(**kwargs: object) -> dict[str, object]:
                report = canonical_validator(**kwargs)  # type: ignore[arg-type]
                Path(kwargs["plan_path"]).write_bytes(plan.read_bytes() + b" ")
                return report

            with mock.patch.object(
                backfill_module,
                "validate_access_probe_against_plan",
                side_effect=mutate_after_validation,
            ):
                self._assert_atomic_rejection(
                    lambda: build_rights_aware_bundle(
                        ROOT,
                        output,
                        run_id="receipt-race-fixture",
                        code_sha=CODE_SHA,
                        scheduled_at="2026-08-27T03:00:00Z",
                        actual_started_at="2026-08-27T03:01:00Z",
                        finished_at=FINISHED_AT,
                        receipt_bindings=[(plan, probe)],
                    ),
                    output,
                )

    def test_existing_output_is_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            receipt = make_receipt(root)
            output = root / "existing"
            output.mkdir()
            marker = output / "preserve.txt"
            marker.write_text("preserve", encoding="utf-8")
            with self.assertRaises(AtomicOutputError):
                build_rights_aware_bundle(
                    ROOT,
                    output,
                    run_id="overwrite-fixture",
                    code_sha=CODE_SHA,
                    scheduled_at="2026-08-27T03:00:00Z",
                    actual_started_at="2026-08-27T03:01:00Z",
                    finished_at=FINISHED_AT,
                    receipt_bindings=[receipt],
                )
            self.assertEqual(marker.read_text(encoding="utf-8"), "preserve")

    def test_embedded_receipt_hash_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle, _ = build_fixture_bundle(Path(directory))
            attempt = read_jsonl(bundle / "source-attempts.jsonl")[0]
            probe = bundle / attempt["probe_path"]
            probe.write_bytes(probe.read_bytes() + b"\n")
            with self.assertRaises(RightsAwareBackfillError):
                validate_rights_aware_bundle(ROOT, bundle)

    def test_path_traversal_is_rejected_even_with_rehashed_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle, _ = build_fixture_bundle(Path(directory))
            rows = read_jsonl(bundle / "source-attempts.jsonl")
            rows[0]["plan_path"] = "../../outside.json"
            rows[0]["record_digest"] = _digest_without(rows[0], "record_digest")
            (bundle / "source-attempts.jsonl").write_bytes(
                canonical_json_bytes(rows[0])
            )
            _rewrite_manifest_inventory(bundle)
            with self.assertRaises((RightsAwareBackfillError, ValueError)):
                validate_rights_aware_bundle(ROOT, bundle)

    def test_untrusted_source_role_is_rejected_even_with_rehashed_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle, _ = build_fixture_bundle(Path(directory))
            rows = read_jsonl(bundle / "source-attempts.jsonl")
            rows[0]["source_role"] = "COMMUNITY_DISCOVERY"
            rows[0]["record_digest"] = _digest_without(rows[0], "record_digest")
            (bundle / "source-attempts.jsonl").write_bytes(
                canonical_json_bytes(rows[0])
            )
            _rewrite_manifest_inventory(bundle)
            with self.assertRaises(RightsAwareBackfillError):
                validate_rights_aware_bundle(ROOT, bundle)

    def test_training_injection_is_rejected_even_with_rehashed_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle, _ = build_fixture_bundle(Path(directory))
            injected = {"synthetic": True, "must_not_train": True}
            (bundle / "training-candidates.jsonl").write_bytes(
                canonical_json_bytes(injected)
            )
            _rewrite_manifest_inventory(bundle)
            with self.assertRaisesRegex(
                RightsAwareBackfillError,
                "cannot be populated",
            ):
                validate_rights_aware_bundle(ROOT, bundle)

    def test_bundle_symlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle, _ = build_fixture_bundle(root)
            attempt = read_jsonl(bundle / "source-attempts.jsonl")[0]
            plan = bundle / attempt["plan_path"]
            copy_path = root / "external-plan-copy.json"
            copy_path.write_bytes(plan.read_bytes())
            plan.unlink()
            os.symlink(copy_path, plan)
            with self.assertRaises(RightsAwareBackfillError):
                validate_rights_aware_bundle(ROOT, bundle)


if __name__ == "__main__":
    unittest.main()
