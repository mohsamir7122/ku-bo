from __future__ import annotations

import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from kubo.disclosure_reaction import analyze_disclosure_reaction
from disclosure_reaction_fixture import latest_financial_snapshot, packet, recent_daily_market

ROOT = Path(__file__).resolve().parents[1]


def validator(name: str):
    schemas = [json.loads(path.read_text(encoding="utf-8")) for path in (ROOT / "schemas").glob("*.schema.json")]
    registry = Registry().with_resources([(schema["$id"], Resource.from_contents(schema)) for schema in schemas])
    schema = next(schema for schema in schemas if schema["$id"].endswith(name))
    return Draft202012Validator(schema, registry=registry, format_checker=Draft202012Validator.FORMAT_CHECKER)


class DisclosureSchemaTests(unittest.TestCase):
    def test_all_new_schemas_are_valid_and_strict(self):
        for path in sorted((ROOT / "schemas").glob("*.schema.json")):
            schema = json.loads(path.read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)
            self.assertEqual(schema["type"], "object")
            self.assertFalse(schema["additionalProperties"])

    def test_packet_and_result_validate(self):
        value = packet()
        validator("disclosure-reaction-packet.schema.json").validate(value)
        validator("disclosure-reaction-result.schema.json").validate(analyze_disclosure_reaction(value))

    def test_current_domain_schemas_validate(self):
        validator("recent-daily-market-series.schema.json").validate(recent_daily_market())
        validator("latest-financial-snapshot.schema.json").validate(latest_financial_snapshot())


if __name__ == "__main__":
    unittest.main()
