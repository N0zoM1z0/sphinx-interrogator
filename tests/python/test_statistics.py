"""Tests for robust paired timing estimators."""

from sphinx_interrogator.statistics import median_of_means, paired_location


def test_median_of_means_resists_one_large_outlier() -> None:
    """A single extreme sample should not dominate grouped location estimation."""
    estimate = median_of_means([1.0, 1.0, 1.0, 1.0, 1000.0], groups=5)
    assert estimate == 1.0


def test_paired_location_preserves_direction() -> None:
    """Follow-up-minus-source estimates should retain the intended sign."""
    estimate = paired_location([10.0, 11.0, 9.0], [11.0, 12.0, 10.0])
    assert estimate.location == 1.0
    assert estimate.confidence == 1.0
