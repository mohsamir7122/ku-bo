from __future__ import annotations

from datetime import date
import unittest

from kubo.status_history import (
    StatusNotice,
    build_status_intervals,
    parse_status_notice,
)


class StatusHistoryEngineTests(unittest.TestCase):
    @staticmethod
    def _notice(
        *,
        notice_id: str,
        event_type: str,
        effective_date: str,
        raw: str = "b" * 64,
        text: str = "c" * 64,
    ) -> StatusNotice:
        return StatusNotice(
            notice_id=notice_id,
            security_code="108",
            ticker="KFH",
            event_type=event_type,
            effective_date=date.fromisoformat(effective_date),
            published_date=date.fromisoformat(effective_date),
            source_id="boursa_historical_disclosures",
            source_url=(
                "https://www.boursakuwait.com.kw/en/announcements/"
                "disclosures-and-announcements/historical-disclosures-and-announcements/"
            ),
            raw_sha256=raw,
            text_sha256=text,
            query_id="query-kfh",
            classification_phrase="suspended from trading",
        )

    def test_valid_suspend_resume_suspend_sequence_builds_contiguous_intervals(self) -> None:
        notices = [
            self._notice(
                notice_id="suspend-1",
                event_type="SUSPEND",
                effective_date="2026-02-01",
            ),
            self._notice(
                notice_id="resume-1",
                event_type="RESUME",
                effective_date="2026-03-01",
                raw="d" * 64,
                text="e" * 64,
            ),
            self._notice(
                notice_id="suspend-2",
                event_type="SUSPEND",
                effective_date="2026-06-01",
                raw="f" * 64,
                text="a" * 64,
            ),
        ]
        intervals, report = build_status_intervals(
            expected_identity={"108": "KFH"},
            opening_states={
                "108": {
                    "ticker": "KFH",
                    "status": "TRADING",
                    "raw_sha256": "1" * 64,
                }
            },
            current_states={"108": "SUSPENDED"},
            notices=notices,
            window_from=date(2026, 1, 1),
            window_to=date(2026, 8, 9),
        )
        self.assertEqual(report["status"], "PASS")
        self.assertTrue(report["status_history_ready"])
        self.assertEqual(
            [item.status for item in intervals],
            ["TRADING", "SUSPENDED", "TRADING", "SUSPENDED"],
        )
        self.assertEqual(intervals[0].effective_from.isoformat(), "2026-01-01")
        self.assertEqual(intervals[0].effective_to.isoformat(), "2026-01-31")
        self.assertEqual(intervals[-1].effective_from.isoformat(), "2026-06-01")
        self.assertEqual(intervals[-1].effective_to.isoformat(), "2026-08-09")
        self.assertEqual(intervals[-1].end_notice_id, "CURRENT_SNAPSHOT")

    def test_invalid_resume_from_trading_is_blocked(self) -> None:
        intervals, report = build_status_intervals(
            expected_identity={"108": "KFH"},
            opening_states={
                "108": {
                    "ticker": "KFH",
                    "status": "TRADING",
                    "raw_sha256": "1" * 64,
                }
            },
            current_states={"108": "TRADING"},
            notices=[
                self._notice(
                    notice_id="bad-resume",
                    event_type="RESUME",
                    effective_date="2026-02-01",
                )
            ],
            window_from=date(2026, 1, 1),
            window_to=date(2026, 8, 9),
        )
        self.assertEqual(report["status"], "BLOCKED")
        self.assertTrue(intervals)
        self.assertTrue(
            any("INVALID_STATUS_TRANSITION" in error for error in report["errors"])
        )

    def test_final_history_must_match_current_snapshot(self) -> None:
        _, report = build_status_intervals(
            expected_identity={"108": "KFH"},
            opening_states={
                "108": {
                    "ticker": "KFH",
                    "status": "TRADING",
                    "raw_sha256": "1" * 64,
                }
            },
            current_states={"108": "SUSPENDED"},
            notices=[],
            window_from=date(2026, 1, 1),
            window_to=date(2026, 8, 9),
        )
        self.assertEqual(report["status"], "BLOCKED")
        self.assertTrue(
            any("CURRENT_STATUS_RECONCILIATION" in error for error in report["errors"])
        )

    def test_same_day_multiple_transitions_are_rejected(self) -> None:
        _, report = build_status_intervals(
            expected_identity={"108": "KFH"},
            opening_states={
                "108": {
                    "ticker": "KFH",
                    "status": "TRADING",
                    "raw_sha256": "1" * 64,
                }
            },
            current_states={"108": "TRADING"},
            notices=[
                self._notice(
                    notice_id="suspend",
                    event_type="SUSPEND",
                    effective_date="2026-02-01",
                ),
                self._notice(
                    notice_id="resume",
                    event_type="RESUME",
                    effective_date="2026-02-01",
                    raw="d" * 64,
                    text="e" * 64,
                ),
            ],
            window_from=date(2026, 1, 1),
            window_to=date(2026, 8, 9),
        )
        self.assertEqual(report["status"], "BLOCKED")
        self.assertIn("MULTIPLE_STATUS_EVENTS_SAME_DATE:108", report["errors"])

    def test_notice_contract_is_identity_query_and_hash_bound(self) -> None:
        row = {
            "notice_id": "suspend-108-2026-06-01",
            "security_code": "108",
            "ticker": "KFH",
            "event_type": "SUSPEND",
            "effective_date": "2026-06-01",
            "published_date": "2026-06-01",
            "source_id": "boursa_historical_disclosures",
            "source_url": (
                "https://www.boursakuwait.com.kw/en/announcements/"
                "disclosures-and-announcements/historical-disclosures-and-announcements/"
            ),
            "raw_sha256": "b" * 64,
            "text_sha256": "c" * 64,
            "query_id": "query-kfh",
            "classification_phrase": "suspended from trading",
        }
        notice = parse_status_notice(
            row,
            expected_identity={"108": "KFH"},
            manifest_hashes=frozenset({"b" * 64, "c" * 64}),
            allowed_query_ids=frozenset({"query-kfh"}),
            window_from=date(2026, 1, 1),
            window_to=date(2026, 8, 9),
        )
        self.assertEqual(notice.event_type, "SUSPEND")
        changed = dict(row)
        changed["query_id"] = "unregistered"
        with self.assertRaisesRegex(ValueError, "query_id"):
            parse_status_notice(
                changed,
                expected_identity={"108": "KFH"},
                manifest_hashes=frozenset({"b" * 64, "c" * 64}),
                allowed_query_ids=frozenset({"query-kfh"}),
                window_from=date(2026, 1, 1),
                window_to=date(2026, 8, 9),
            )


if __name__ == "__main__":
    unittest.main()
