from __future__ import annotations

from datetime import timedelta
import unittest

from kubo.temporal_validation import TemporalSample, assert_causal_split, purge_and_embargo_training_samples


def sample(sample_id: str, feature: str, start: str, end: str) -> TemporalSample:
    return TemporalSample.from_values(sample_id, feature, start, end)


class TemporalValidationTests(unittest.TestCase):
    def test_invalid_feature_label_order_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "feature_cutoff"):
            sample("bad", "2026-01-03T00:00:00+03:00", "2026-01-02T00:00:00+03:00", "2026-01-04T00:00:00+03:00")

    def test_overlapping_training_label_is_purged(self) -> None:
        training = [
            sample("old-safe", "2026-01-01T00:00:00+03:00", "2026-01-02T00:00:00+03:00", "2026-01-03T00:00:00+03:00"),
            sample("leaks", "2026-01-02T00:00:00+03:00", "2026-01-03T00:00:00+03:00", "2026-01-08T00:00:00+03:00"),
        ]
        test = [sample("test", "2026-01-07T00:00:00+03:00", "2026-01-08T00:00:00+03:00", "2026-01-09T00:00:00+03:00")]
        kept, removed = purge_and_embargo_training_samples(training, test, embargo=timedelta(days=1))
        self.assertEqual([item.sample_id for item in kept], ["old-safe"])
        self.assertEqual(removed, ("leaks",))

    def test_embargo_removes_immediately_following_sample(self) -> None:
        test = [sample("test", "2026-01-07T00:00:00+03:00", "2026-01-08T00:00:00+03:00", "2026-01-09T00:00:00+03:00")]
        after = sample("after", "2026-01-10T00:00:00+03:00", "2026-01-10T00:00:00+03:00", "2026-01-11T00:00:00+03:00")
        kept, removed = purge_and_embargo_training_samples([after], test, embargo=timedelta(days=2))
        self.assertEqual(kept, ())
        self.assertEqual(removed, ("after",))

    def test_future_training_beyond_embargo_is_still_removed(self) -> None:
        test = [sample("test", "2026-01-07T00:00:00+03:00", "2026-01-08T00:00:00+03:00", "2026-01-09T00:00:00+03:00")]
        future = sample("future", "2026-02-01T00:00:00+03:00", "2026-02-02T00:00:00+03:00", "2026-02-03T00:00:00+03:00")
        kept, removed = purge_and_embargo_training_samples([future], test, embargo=timedelta(days=2))
        self.assertEqual(kept, ())
        self.assertEqual(removed, ("future",))

    def test_causal_split_rejects_label_overlap(self) -> None:
        train = [sample("train", "2026-01-01T00:00:00+03:00", "2026-01-02T00:00:00+03:00", "2026-01-08T00:00:00+03:00")]
        test = [sample("test", "2026-01-07T00:00:00+03:00", "2026-01-08T00:00:00+03:00", "2026-01-09T00:00:00+03:00")]
        with self.assertRaisesRegex(ValueError, "overlap"):
            assert_causal_split(train, test)


if __name__ == "__main__":
    unittest.main()
