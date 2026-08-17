from __future__ import annotations

import copy
import unittest

from kubo.disclosure_data_domains import (
    validate_historical_disclosure_record,
    validate_historical_event_market_window,
    validate_latest_financial_snapshot,
    validate_public_opinion_archive,
    validate_recent_daily_market_series,
)
from kubo.disclosure_reaction import DisclosureReactionError, analyze_disclosure_reaction
from kubo.disclosure_reaction_packet import validate_disclosure_reaction_packet
from disclosure_reaction_fixture import latest_financial_snapshot, packet, recent_daily_market


class DisclosureDataSeparationTests(unittest.TestCase):
    def test_all_historical_layers_validate_independently(self):
        value = packet()
        validate_historical_disclosure_record(value["historical_disclosure"])
        validate_historical_event_market_window(value["historical_market_window"])
        validate_public_opinion_archive(value["public_opinion_archive"])

    def test_recent_market_and_latest_financial_validate_independently(self):
        validate_recent_daily_market_series(recent_daily_market())
        validate_latest_financial_snapshot(latest_financial_snapshot())

    def test_historical_disclosure_rejects_market_fields(self):
        value = packet()["historical_disclosure"]
        value["latest_price"] = 1.0
        with self.assertRaisesRegex(DisclosureReactionError, "unknown=latest_price"):
            validate_historical_disclosure_record(value)

    def test_historical_disclosure_rejects_financial_fields(self):
        value = packet()["historical_disclosure"]
        value["revenue"] = 1.0
        with self.assertRaisesRegex(DisclosureReactionError, "unknown=revenue"):
            validate_historical_disclosure_record(value)

    def test_correction_is_append_only_separate_record(self):
        value = packet()["historical_disclosure"]
        value["record_id"] = "correction-1"
        value["record_type"] = "CORRECTION"
        value["corrects_record_id"] = "disclosure-2026-01"
        validated = validate_historical_disclosure_record(value)
        self.assertEqual(validated["record_type"], "CORRECTION")
        self.assertEqual(validated["corrects_record_id"], "disclosure-2026-01")
        self.assertEqual(validated["immutability"], "APPEND_ONLY")

    def test_historical_window_rejects_disclosure_text(self):
        value = packet()["historical_market_window"]
        value["headline"] = "not allowed"
        with self.assertRaisesRegex(DisclosureReactionError, "unknown=headline"):
            validate_historical_event_market_window(value)

    def test_historical_window_rejects_financial_metrics(self):
        value = packet()["historical_market_window"]
        value["net_income"] = 1.0
        with self.assertRaisesRegex(DisclosureReactionError, "unknown=net_income"):
            validate_historical_event_market_window(value)

    def test_recent_market_cannot_reference_disclosure(self):
        value = recent_daily_market()
        value["disclosure_id"] = "historical"
        with self.assertRaisesRegex(DisclosureReactionError, "unknown=disclosure_id"):
            validate_recent_daily_market_series(value)

    def test_recent_market_cannot_recompute_historical_reaction(self):
        value = recent_daily_market()
        value["historical_reaction_recompute_allowed"] = True
        with self.assertRaisesRegex(DisclosureReactionError, "cannot recompute"):
            validate_recent_daily_market_series(value)

    def test_latest_financial_cannot_contain_daily_price(self):
        value = latest_financial_snapshot()
        value["latest_price"] = 1.0
        with self.assertRaisesRegex(DisclosureReactionError, "unknown=latest_price"):
            validate_latest_financial_snapshot(value)

    def test_latest_financial_cannot_enter_historical_reaction(self):
        value = latest_financial_snapshot()
        value["historical_reaction_input_allowed"] = True
        with self.assertRaisesRegex(DisclosureReactionError, "cannot enter"):
            validate_latest_financial_snapshot(value)

    def test_reaction_packet_rejects_current_data_domains(self):
        value = packet()
        value["recent_daily_market"] = recent_daily_market()
        with self.assertRaisesRegex(DisclosureReactionError, "unknown=recent_daily_market"):
            validate_disclosure_reaction_packet(value)
        value = packet()
        value["latest_financial_snapshot"] = latest_financial_snapshot()
        with self.assertRaisesRegex(DisclosureReactionError, "unknown=latest_financial_snapshot"):
            validate_disclosure_reaction_packet(value)

    def test_recent_market_update_cannot_change_frozen_historical_result(self):
        historical = packet(pre_start=100, pre_end=100, immediate_end=103, post_end=106)
        before = analyze_disclosure_reaction(historical)
        current = recent_daily_market()
        current["records"][-1]["total_return_index"] = 999.0
        validate_recent_daily_market_series(current)
        after = analyze_disclosure_reaction(historical)
        self.assertEqual(before, after)
        self.assertFalse(after["data_separation"]["recent_daily_market_used"])
        self.assertFalse(after["data_separation"]["latest_financial_snapshot_used"])

    def test_cross_layer_ids_and_cutoffs_are_enforced(self):
        value = packet()
        value["historical_market_window"]["canonical_cluster_id"] = "other"
        with self.assertRaisesRegex(DisclosureReactionError, "cluster mismatch"):
            validate_disclosure_reaction_packet(value)
        value = packet()
        value["historical_market_window"]["disclosure_record_id"] = "other"
        with self.assertRaisesRegex(DisclosureReactionError, "another disclosure"):
            validate_disclosure_reaction_packet(value)


if __name__ == "__main__":
    unittest.main()
