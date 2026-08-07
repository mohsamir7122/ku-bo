from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SchemaTests(unittest.TestCase):
    def test_all_schemas_are_json_schema_2020_12(self) -> None:
        paths = sorted((ROOT / "schemas").glob("*.schema.json"))
        self.assertGreaterEqual(len(paths), 2)
        for path in paths:
            with self.subTest(path=path.name):
                value = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(value["$schema"], "https://json-schema.org/draft/2020-12/schema")
                self.assertEqual(value["type"], "object")
                self.assertFalse(value["additionalProperties"])

    def test_analysis_request_schema_matches_runtime_vocabularies(self) -> None:
        from kubo.request_contracts import (
            CLAIM_TYPES,
            DETAIL_LEVELS,
            LANGUAGES,
            OUTPUT_FORMATS,
            REQUEST_MODES,
            REQUEST_SCOPES,
        )

        value = json.loads((ROOT / "schemas" / "analysis-request.schema.json").read_text(encoding="utf-8"))
        properties = value["properties"]
        self.assertEqual(set(properties["mode"]["enum"]), set(REQUEST_MODES))
        self.assertEqual(set(properties["scope"]["enum"]), set(REQUEST_SCOPES))
        self.assertEqual(set(properties["claim_type"]["enum"]), set(CLAIM_TYPES))
        self.assertEqual(set(properties["output_format"]["enum"]), set(OUTPUT_FORMATS))
        self.assertEqual(set(properties["detail_level"]["enum"]), set(DETAIL_LEVELS))
        self.assertEqual(set(properties["language"]["enum"]), set(LANGUAGES))


if __name__ == "__main__":
    unittest.main()
