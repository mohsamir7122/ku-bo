from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable

from .strict import parse_aware


@dataclass(frozen=True)
class TemporalSample:
    sample_id: str
    feature_cutoff: datetime
    label_start: datetime
    label_end: datetime

    @classmethod
    def from_values(cls, sample_id: str, feature_cutoff: str, label_start: str, label_end: str) -> "TemporalSample":
        if not str(sample_id).strip():
            raise ValueError("sample_id is required")
        sample = cls(
            str(sample_id),
            parse_aware(feature_cutoff, "feature_cutoff"),
            parse_aware(label_start, "label_start"),
            parse_aware(label_end, "label_end"),
        )
        if sample.feature_cutoff > sample.label_start or sample.label_start > sample.label_end:
            raise ValueError("feature_cutoff <= label_start <= label_end is required")
        return sample

    @property
    def information_start(self) -> datetime:
        return self.feature_cutoff

    @property
    def information_end(self) -> datetime:
        return self.label_end


def _overlaps(left: TemporalSample, right: TemporalSample) -> bool:
    return left.information_start <= right.information_end and right.information_start <= left.information_end


def purge_and_embargo_training_samples(
    training: Iterable[TemporalSample],
    test: Iterable[TemporalSample],
    *,
    embargo: timedelta,
) -> tuple[tuple[TemporalSample, ...], tuple[str, ...]]:
    if embargo < timedelta(0):
        raise ValueError("embargo cannot be negative")
    training_rows = tuple(training)
    test_rows = tuple(test)
    if not test_rows:
        raise ValueError("test samples are required")
    if len({item.sample_id for item in (*training_rows, *test_rows)}) != len(training_rows) + len(test_rows):
        raise ValueError("sample_id must be unique across train and test")
    test_start = min(item.information_start for item in test_rows)
    test_end = max(item.information_end for item in test_rows)
    embargo_end = test_end + embargo
    kept: list[TemporalSample] = []
    removed: list[str] = []
    for sample in training_rows:
        overlap = any(_overlaps(sample, held_out) for held_out in test_rows)
        in_embargo = test_end < sample.information_start <= embargo_end
        # A causal walk-forward split may use only samples whose complete
        # information interval predates the first held-out feature cutoff.
        # Previously, a future sample beyond the embargo window could be kept,
        # which silently turned the split into a bidirectional/look-ahead split.
        not_strictly_prior = sample.information_end >= test_start
        if overlap or in_embargo or not_strictly_prior:
            removed.append(sample.sample_id)
        else:
            kept.append(sample)
    return tuple(kept), tuple(removed)


def assert_causal_split(training: Iterable[TemporalSample], test: Iterable[TemporalSample]) -> None:
    train_rows = tuple(training)
    test_rows = tuple(test)
    if not train_rows or not test_rows:
        raise ValueError("non-empty train and test samples are required")
    test_start = min(item.information_start for item in test_rows)
    leaking = sorted(item.sample_id for item in train_rows if item.information_end >= test_start)
    if leaking:
        raise ValueError("training label intervals overlap test boundary: " + ",".join(leaking))


__all__ = ["TemporalSample", "assert_causal_split", "purge_and_embargo_training_samples"]
