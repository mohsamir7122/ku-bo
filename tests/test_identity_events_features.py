from __future__ import annotations

from datetime import date
from pathlib import Path
import tempfile
import unittest

from kubo.events import EventRecord, canonicalize_events
from kubo.features import build_event_features, validate_feature_snapshot
from kubo.identity import IdentityRecord, IdentityResolver


HASH_A = "a" * 64
HASH_B = "b" * 64


def event(event_id: str, source_id: str, role: str, available: str, *, original: str | None = None, security_code: str = "101") -> EventRecord:
    return EventRecord(
        event_id=event_id,
        security_code=security_code,
        source_id=source_id,
        source_role=role,
        event_type="CONTRACT",
        direction="POSITIVE",
        novelty=0.8,
        event_at=available,
        published_at=available,
        first_available_at=available,
        captured_at="2026-08-06T12:00:00+03:00",
        content_hash=HASH_A,
        evidence_hash=HASH_A if source_id == "official" else HASH_B,
        relation_type="REPUBLISHED" if original else "STANDALONE",
        original_event_id=original,
        raw_text="synthetic",
    )


class IdentityEventFeatureTests(unittest.TestCase):
    def test_ticker_only_resolution_is_rejected(self):
        record = IdentityRecord("101", "ABC", "KW0000000001", "أ", "A", "cash", "MAIN", "KWD", date(2020, 1, 1), None, "TRADING", HASH_A)
        resolver = IdentityResolver([record])
        with self.assertRaises(ValueError):
            resolver.resolve(as_of=date(2026, 8, 6), board="cash", ticker="ABC")

    def test_effective_dated_rename(self):
        records = [
            IdentityRecord("101", "OLD", "KW0000000001", "قديم", "Old", "cash", "MAIN", "KWD", date(2020, 1, 1), date(2025, 12, 31), "LISTED", HASH_A),
            IdentityRecord("101", "NEW", "KW0000000001", "جديد", "New", "cash", "MAIN", "KWD", date(2026, 1, 1), None, "TRADING", HASH_A),
        ]
        resolver = IdentityResolver(records)
        self.assertEqual(resolver.resolve(as_of=date(2026, 8, 6), board="cash", security_code="101").ticker, "NEW")

    def test_repost_is_one_event_and_source_diversity_uses_sources(self):
        parent = event("e1", "official", "OFFICIAL_FILING", "2026-08-05T08:00:00+03:00")
        repost = event("e2", "telegram-channel", "TELEGRAM", "2026-08-05T08:10:00+03:00", original="e1")
        groups = canonicalize_events([parent, repost])
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["diffusion_count"], 2)
        self.assertEqual(groups[0]["source_diversity"], 2)
        self.assertEqual(groups[0]["evidence_hashes"], [HASH_A, HASH_B])

    def test_cross_security_relation_is_rejected(self):
        parent = event("e1", "official", "OFFICIAL_FILING", "2026-08-05T08:00:00+03:00")
        wrong = event("e2", "social", "SOCIAL", "2026-08-05T08:10:00+03:00", original="e1", security_code="102")
        with self.assertRaises(ValueError):
            canonicalize_events([parent, wrong])

    def test_missing_window_is_unknown_not_zero(self):
        rows = build_event_features([], decision_id="d1", security_code="101", decision_at="2026-08-06T12:00:00+03:00", capture_mode="HISTORICAL_POINT_IN_TIME")
        self.assertTrue(all(row["feature_value"] is None for row in rows))
        self.assertTrue(all(row["source_availability_state"] == "UNKNOWN_NOT_OBSERVED" for row in rows))
        report = validate_feature_snapshot(rows, manifest_hashes=frozenset())
        self.assertEqual(report["status"], "PASS", report)

    def test_coverage_evidence_allows_observed_zero(self):
        rows = build_event_features([], decision_id="d1", security_code="101", decision_at="2026-08-06T12:00:00+03:00", capture_mode="PROSPECTIVE", coverage_evidence_hashes=[HASH_A])
        count = next(row for row in rows if row["feature_name"] == "official_event_count_30d")
        self.assertEqual(count["feature_value"], 0)
        report = validate_feature_snapshot(rows, manifest_hashes=frozenset({HASH_A}))
        self.assertEqual(report["status"], "PASS", report)

    def test_prospective_late_fetch_is_rejected(self):
        row = {
            "decision_id": "d1",
            "decision_at": "2026-08-06T12:00:00+03:00",
            "security_code": "101",
            "feature_name": "official_event_count_30d",
            "feature_value": 1,
            "source_event_at": "2026-08-06T10:00:00+03:00",
            "source_published_at": "2026-08-06T10:00:00+03:00",
            "available_at": "2026-08-06T10:00:00+03:00",
            "fetched_at": "2026-08-07T10:00:00+03:00",
            "capture_mode": "PROSPECTIVE",
            "availability_evidence_grade": "A",
            "source_availability_state": "OBSERVED",
            "evidence_hashes": [HASH_A],
            "parser_version": "v2",
        }
        report = validate_feature_snapshot([row], manifest_hashes=frozenset({HASH_A}))
        self.assertEqual(report["status"], "BLOCKED")
        self.assertTrue(any("fetched after" in item for item in report["errors"]))

    def test_future_label_feature_name_is_rejected(self):
        row = {
            "decision_id": "d1", "decision_at": "2026-08-06T12:00:00+03:00", "security_code": "101",
            "feature_name": "future_return_1d", "feature_value": None, "capture_mode": "HISTORICAL_POINT_IN_TIME",
            "source_availability_state": "UNKNOWN_NOT_OBSERVED", "evidence_hashes": [], "parser_version": "v2",
        }
        report = validate_feature_snapshot([row], manifest_hashes=frozenset())
        self.assertEqual(report["status"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
