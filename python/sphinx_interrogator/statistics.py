"""Robust paired estimators for coarse and noisy relational observations."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from statistics import median


@dataclass(frozen=True, slots=True)
class PairedEstimate:
    """Robust estimate and conservative uncertainty summary for paired deltas."""

    location: float
    median_absolute_deviation: float
    confidence: float
    samples: int


def median_of_means(values: Sequence[float], groups: int) -> float:
    """Estimate a location by taking the median of approximately equal group means."""
    if not values:
        raise ValueError("median_of_means requires at least one value")
    if groups < 1 or groups > len(values):
        raise ValueError("groups must be between one and the sample count")
    buckets: list[list[float]] = [[] for _ in range(groups)]
    for index, value in enumerate(values):
        buckets[index % groups].append(value)
    means = [sum(bucket) / len(bucket) for bucket in buckets]
    return float(median(means))


def paired_location(
    source_samples: Sequence[float],
    follow_up_samples: Sequence[float],
    *,
    groups: int | None = None,
) -> PairedEstimate:
    """Estimate follow-up minus source using interleaved paired measurements."""
    if len(source_samples) != len(follow_up_samples):
        raise ValueError("paired sample sequences must have equal length")
    if not source_samples:
        raise ValueError("at least one pair is required")
    deltas = [right - left for left, right in zip(source_samples, follow_up_samples, strict=True)]
    group_count = groups if groups is not None else max(1, int(math.sqrt(len(deltas))))
    location = median_of_means(deltas, min(group_count, len(deltas)))
    absolute_deviations = [abs(value - location) for value in deltas]
    mad = float(median(absolute_deviations))
    if mad == 0.0:
        confidence = 1.0 if len(deltas) >= 3 else 0.75
    else:
        signal = abs(location) / (mad + 1e-12)
        confidence = min(0.999, 1.0 - math.exp(-signal * math.sqrt(len(deltas))))
    return PairedEstimate(
        location=location,
        median_absolute_deviation=mad,
        confidence=confidence,
        samples=len(deltas),
    )


def bucket_midpoint(cycle_bucket: int, bucket_width: int) -> float:
    """Map a public bucket to the midpoint of its represented cycle interval."""
    if cycle_bucket < 0 or bucket_width < 1:
        raise ValueError("invalid timing bucket")
    lower = cycle_bucket * bucket_width
    return lower + (bucket_width - 1) / 2.0
