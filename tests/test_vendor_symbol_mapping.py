from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest

from kubo.vendor_symbol_mapping import (
    PilotIdentitySeedCatalog,
    VendorSymbolMappingCatalog,
)


ROOT = Path(__file__).resolve().parents[1]


class VendorSymbolMappingTests(unittest.TestCase):
    def test_pilot_catalogs_are_separated_and_seed_is_not_official(self) -> None:
        identities = PilotIdentitySeedCatalog(ROOT / "config")
        mappings = VendorSymbolMappingCatalog(ROOT / "config", identities)
        self.assertEqual(identities.report()["security_count"], 5)
        self.assertFalse(identities.official_identity_ready)
        self.assertEqual(mappings.report()["mapping_count"], 5)
        self.assertEqual(
            {item.ticker for item in mappings.capture_candidates("investing")},
            {"NBK", "KFH", "MABANEE", "ZAIN", "HUMANSOFT"},
        )
        self.assertFalse(mappings.report()["official_identity_ready"])

    def test_vendor_mapping_cannot_conflict_with_identity_seed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config"
            shutil.copytree(ROOT / "config" / "pilot", config / "pilot")
            path = config / "pilot" / "vendor_symbol_mappings.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["mappings"][0]["security_code"] = "999"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "conflicts with the separated identity seed"):
                VendorSymbolMappingCatalog(config)

    def test_unverified_seed_cannot_carry_self_asserted_official_proof(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config"
            shutil.copytree(ROOT / "config" / "pilot", config / "pilot")
            path = config / "pilot" / "security_master_seed.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["securities"][0]["official_artifact_sha256"] = "a" * 64
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "cannot carry official proof"):
                PilotIdentitySeedCatalog(config)

    def test_verified_identity_requires_hash_and_effective_date(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config"
            shutil.copytree(ROOT / "config" / "pilot", config / "pilot")
            path = config / "pilot" / "security_master_seed.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["securities"][0]["identity_state"] = "VERIFIED_OFFICIAL"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "official_artifact_sha256"):
                PilotIdentitySeedCatalog(config)


if __name__ == "__main__":
    unittest.main()
