from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from kubo import foundation_io
from kubo.foundation_io import (
    TreeSnapshotChangedError,
    prepare_output_root,
    read_csv_bytes,
    safe_regular_file,
    snapshot_regular_tree,
    strict_json_object,
    write_csv,
)


class FoundationIoTests(unittest.TestCase):
    def test_strict_json_rejects_duplicate_keys_and_non_finite_values(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate key"):
            strict_json_object(b'{"status":"PASS","status":"BLOCKED"}', "report")
        with self.assertRaisesRegex(ValueError, "non-finite"):
            strict_json_object(b'{"value":NaN}', "report")

    def test_csv_reader_enforces_exact_canonical_headers(self) -> None:
        headers, rows = read_csv_bytes(
            b"security_code,trade_date\n101,2026-08-09\n",
            field="denominator",
            exact_headers=("security_code", "trade_date"),
        )
        self.assertEqual(headers, ("security_code", "trade_date"))
        self.assertEqual(rows[0]["security_code"], "101")
        with self.assertRaisesRegex(ValueError, "canonical contract"):
            read_csv_bytes(
                b"trade_date,security_code\n2026-08-09,101\n",
                field="denominator",
                exact_headers=("security_code", "trade_date"),
            )

    def test_writer_uses_lf_and_refuses_uncontracted_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rows.csv"
            write_csv(
                path,
                headers=("security_code", "trade_date"),
                rows=({"security_code": "101", "trade_date": "2026-08-09"},),
            )
            self.assertEqual(
                path.read_bytes(),
                b"security_code,trade_date\n101,2026-08-09\n",
            )
            with self.assertRaisesRegex(ValueError, "outside the canonical contract"):
                write_csv(
                    Path(directory) / "bad.csv",
                    headers=("security_code",),
                    rows=({"security_code": "101", "ticker": "NBK"},),
                )

    def test_output_root_is_non_overwriting(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "packet"
            self.assertEqual(prepare_output_root(root, label="packet"), root)
            (root / "receipt.json").write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "non-empty"):
                prepare_output_root(root, label="packet")

    def test_safe_reader_rejects_symlink_when_supported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "target.json"
            link = root / "link.json"
            target.write_bytes(b"{}")
            try:
                link.symlink_to(target)
            except (NotImplementedError, OSError) as exc:
                self.skipTest(f"symlink creation is unavailable: {exc}")
            with self.assertRaisesRegex(ValueError, "symlink"):
                safe_regular_file(link, field="manifest")

    def test_safe_reader_preserves_exact_crlf_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            expected = b'{"schema_version":"3.0"}\r\n'
            path.write_bytes(expected)
            self.assertEqual(
                safe_regular_file(path, field="manifest"),
                expected,
            )

    def test_safe_reader_allows_unrelated_sibling_creation_during_read(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory) / "authority"
            parent.mkdir()
            path = parent / "receipt.json"
            path.write_bytes(b'{"status":"PASS"}\n')
            sibling = parent / "unrelated-audit-note.txt"
            original_read = foundation_io.os.read
            sibling_created = False

            def create_sibling(descriptor: int, size: int) -> bytes:
                nonlocal sibling_created
                content = original_read(descriptor, size)
                if not sibling_created:
                    sibling.write_bytes(b"unrelated concurrent write\n")
                    sibling_created = True
                return content

            with patch("kubo.foundation_io.os.read", side_effect=create_sibling):
                content = safe_regular_file(path, field="receipt")

            self.assertEqual(content, b'{"status":"PASS"}\n')
            self.assertTrue(sibling.is_file())

    @unittest.skipIf(os.name == "nt", "Windows blocks replacement of an open file")
    def test_safe_reader_still_rejects_leaf_replacement_during_read(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory) / "authority"
            parent.mkdir()
            path = parent / "receipt.json"
            path.write_bytes(b'{"status":"PASS"}\n')
            original = parent / "original-receipt.json"
            original_read = foundation_io.os.read
            replaced = False

            def replace_leaf(descriptor: int, size: int) -> bytes:
                nonlocal replaced
                content = original_read(descriptor, size)
                if not replaced:
                    path.rename(original)
                    path.write_bytes(b'{"status":"FORGED"}\n')
                    replaced = True
                return content

            with patch("kubo.foundation_io.os.read", side_effect=replace_leaf):
                with self.assertRaisesRegex(ValueError, "changed while being read"):
                    safe_regular_file(path, field="receipt")

    @unittest.skipIf(
        os.name == "nt",
        "Windows blocks replacement of a directory containing an open file",
    )
    def test_safe_reader_still_rejects_ancestor_replacement_during_read(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ancestor = root / "authority"
            ancestor.mkdir()
            path = ancestor / "receipt.json"
            path.write_bytes(b'{"status":"PASS"}\n')
            moved = root / "moved-authority"
            original_read = foundation_io.os.read
            replaced = False

            def replace_ancestor(descriptor: int, size: int) -> bytes:
                nonlocal replaced
                content = original_read(descriptor, size)
                if not replaced:
                    ancestor.rename(moved)
                    try:
                        ancestor.symlink_to(moved, target_is_directory=True)
                    except (NotImplementedError, OSError) as exc:
                        self.skipTest(f"symlink creation is unavailable: {exc}")
                    replaced = True
                return content

            with patch("kubo.foundation_io.os.read", side_effect=replace_ancestor):
                with self.assertRaisesRegex(ValueError, "changed while being read"):
                    safe_regular_file(path, field="receipt")

    def test_tree_snapshot_bounds_empty_entries_and_depth(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("one", "two", "three"):
                (root / name).mkdir()
            with self.assertRaisesRegex(ValueError, "exceeds 2 entries"):
                snapshot_regular_tree(root, field="tree", max_entries=2)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nested = root
            for name in ("one", "two", "three"):
                nested /= name
                nested.mkdir()
            with self.assertRaisesRegex(ValueError, "maximum depth 2"):
                snapshot_regular_tree(root, field="tree", max_depth=2)

    def test_tree_snapshot_reports_tree_change_between_scans(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = root / "evidence.bin"
            evidence.write_bytes(b"before")
            original_scan = foundation_io._scan_regular_tree_once
            scan_count = 0

            def mutate_after_first_scan(*args, **kwargs):
                nonlocal scan_count
                result = original_scan(*args, **kwargs)
                scan_count += 1
                if scan_count == 1:
                    evidence.write_bytes(b"after")
                return result

            with patch(
                "kubo.foundation_io._scan_regular_tree_once",
                side_effect=mutate_after_first_scan,
            ):
                with self.assertRaisesRegex(
                    TreeSnapshotChangedError,
                    "changed while being snapshotted",
                ):
                    snapshot_regular_tree(root, field="tree")

    def test_tree_snapshot_reports_tree_disappearance_between_scans(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "tree"
            root.mkdir()
            original_scan = foundation_io._scan_regular_tree_once
            scan_count = 0

            def remove_after_first_scan(*args, **kwargs):
                nonlocal scan_count
                result = original_scan(*args, **kwargs)
                scan_count += 1
                if scan_count == 1:
                    root.rmdir()
                return result

            with patch(
                "kubo.foundation_io._scan_regular_tree_once",
                side_effect=remove_after_first_scan,
            ):
                with self.assertRaisesRegex(
                    TreeSnapshotChangedError,
                    "changed while being snapshotted",
                ):
                    snapshot_regular_tree(root, field="tree")


if __name__ == "__main__":
    unittest.main()
