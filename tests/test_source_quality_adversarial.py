from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest

from kubo.source_quality import DIMENSION_IDS, SourceQualityError, assess_source_quality


ROOT = Path(__file__).resolve().parents[1]


def _scores(value: float = 1.0) -> dict[str, float]:
    return {dimension: value for dimension in DIMENSION_IDS}


class SourceQualityAdversarialTests(unittest.TestCase):
    def test_caller_cannot_promote_secondary_to_official(self) -> None:
        with self.assertRaisesRegex(SourceQualityError, "conflicts with trusted registry"):
            assess_source_quality(
                ROOT,
                source_id="mubasher_kuwait",
                source_role="OFFICIAL_TRUTH",
                requested_fact_role="OFFICIAL_FACT",
                dimension_scores=_scores(),
            )

    def test_unknown_or_excluded_source_cannot_be_assessed(self) -> None:
        for source_id in ("caller_invented_source", "web_search_router"):
            with self.subTest(source_id=source_id), self.assertRaisesRegex(
                SourceQualityError, "trusted source registry"
            ):
                assess_source_quality(
                    ROOT,
                    source_id=source_id,
                    requested_fact_role="RESEARCH_CONTEXT",
                    dimension_scores=_scores(),
                )

    def test_entitlement_source_is_never_access_authorized_by_quality_score(self) -> None:
        report = assess_source_quality(
            ROOT,
            source_id="authorized_broker_feed",
            requested_fact_role="PRICE_CONTEXT",
            dimension_scores=_scores(),
        )
        self.assertEqual(report["rights_status"], "ENTITLEMENT_REQUIRED")
        self.assertFalse(report["access_authorized"])
        self.assertFalse(report["automatic_promotion_allowed"])

    def test_tampered_trusted_role_mapping_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            shutil.copytree(ROOT / "config", project / "config")
            registry_path = project / "config" / "research_source_registry.json"
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            registry["class_role_map"]["STRUCTURED_SECONDARY"] = "OFFICIAL_PRIMARY"
            registry_path.write_text(json.dumps(registry), encoding="utf-8")
            with self.assertRaisesRegex(SourceQualityError, "trusted source registry"):
                assess_source_quality(
                    project,
                    source_id="mubasher_kuwait",
                    requested_fact_role="RESEARCH_CONTEXT",
                    dimension_scores=_scores(),
                )

    def test_malformed_source_catalog_failure_is_normalized(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            shutil.copytree(ROOT / "config", project / "config")
            catalog_path = project / "config" / "source_network.json"
            catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
            catalog["schema_version"] = "BROKEN"
            catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
            with self.assertRaisesRegex(SourceQualityError, "trusted source registry"):
                assess_source_quality(
                    project,
                    source_id="mubasher_kuwait",
                    requested_fact_role="RESEARCH_CONTEXT",
                    dimension_scores=_scores(),
                )

    def test_policy_file_path_resolves_only_from_canonical_config_location(self) -> None:
        report = assess_source_quality(
            ROOT / "config" / "source_quality_policy.json",
            source_id="boursa_current",
            requested_fact_role="OFFICIAL_FACT",
            dimension_scores=_scores(0.9),
        )
        self.assertTrue(report["source_role_resolved_from_registry"])

        with tempfile.TemporaryDirectory() as temporary:
            policy = Path(temporary) / "policy.json"
            policy.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(SourceQualityError, "requires a project root"):
                assess_source_quality(
                    policy,
                    source_id="boursa_current",
                    requested_fact_role="OFFICIAL_FACT",
                    dimension_scores=_scores(),
                )


if __name__ == "__main__":
    unittest.main()
