from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from kubo.foundation_io import (
    prepare_output_root,
    read_csv_bytes,
    safe_regular_file,
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


if __name__ == "__main__":
    unittest.main()
