import math

import pytest

from qontinuum.assertions import (
    QuantumAssertionError,
    StatisticallyUnsoundError,
    assert_chi_squared,
    assert_distribution,
    assert_fidelity,
    assert_matches_baseline,
    assert_probability,
    stats,
)

BELL = {"00": 0.5, "11": 0.5}


class TestStats:
    def test_normalize_counts_strips_register_spaces(self):
        assert stats.normalize_counts({"00 1": 3, "001": 2}) == {"001": 5}

    def test_tvd_identical_is_zero(self):
        assert stats.tvd({"00": 500, "11": 500}, BELL) == pytest.approx(0.0)

    def test_tvd_disjoint_is_one(self):
        assert stats.tvd({"01": 100}, BELL) == pytest.approx(1.0)

    def test_tvd_known_value(self):
        # observed: 0.6/0.4 vs expected 0.5/0.5 -> TVD = 0.1
        assert stats.tvd({"00": 600, "11": 400}, BELL) == pytest.approx(0.1)

    def test_fidelity_identical_is_one(self):
        assert stats.hellinger_fidelity({"00": 500, "11": 500}, BELL) == pytest.approx(1.0)

    def test_fidelity_disjoint_is_zero(self):
        assert stats.hellinger_fidelity({"01": 100}, BELL) == pytest.approx(0.0)

    def test_sampling_floor_shrinks_with_shots(self):
        assert stats.sampling_floor(2, 10_000) < stats.sampling_floor(2, 100)

    def test_shots_for_threshold_inverts_floor(self):
        shots = stats.shots_for_threshold(2, 0.05)
        assert stats.sampling_floor(2, shots) <= 0.05
        assert stats.sampling_floor(2, shots - 200) > 0.05

    def test_validate_expected_rejects_bad_sum(self):
        with pytest.raises(ValueError, match="sum"):
            stats.validate_expected({"00": 0.5, "11": 0.4})

    def test_two_sample_same_distribution_high_pvalue(self):
        a = {"00": 5000, "11": 5000}
        b = {"00": 4980, "11": 5020}
        _, p = stats.two_sample_pvalue(a, b)
        assert p > 0.05

    def test_two_sample_different_distribution_low_pvalue(self):
        a = {"00": 5000, "11": 5000}
        b = {"00": 6000, "11": 4000}
        _, p = stats.two_sample_pvalue(a, b)
        assert p < 1e-6


class TestAssertDistribution:
    def test_passes_within_threshold(self):
        assert_distribution({"00": 2010, "11": 1990}, BELL, tvd_threshold=0.05)

    def test_fails_beyond_threshold(self):
        with pytest.raises(QuantumAssertionError, match="TVD"):
            assert_distribution({"00": 3000, "11": 1000}, BELL, tvd_threshold=0.05)

    def test_unsound_threshold_is_config_error_not_failure(self):
        # 100 shots cannot resolve a 0.01 TVD threshold.
        with pytest.raises(StatisticallyUnsoundError, match="shots"):
            assert_distribution({"00": 50, "11": 50}, BELL, tvd_threshold=0.01)

    def test_error_carries_statistic_and_threshold(self):
        with pytest.raises(QuantumAssertionError) as excinfo:
            assert_distribution({"00": 4000}, BELL, tvd_threshold=0.05)
        assert excinfo.value.statistic == pytest.approx(0.5)
        assert excinfo.value.threshold == 0.05

    def test_accepts_runresult_like_objects(self):
        class FakeResult:
            def __init__(self):
                self.counts = {"00": 2000, "11": 2000}

        assert_distribution(FakeResult(), BELL, tvd_threshold=0.05)


class TestAssertChiSquared:
    def test_passes_on_fair_sample(self):
        assert_chi_squared({"00": 5030, "11": 4970}, BELL, alpha=0.01)

    def test_fails_on_biased_sample(self):
        with pytest.raises(QuantumAssertionError, match="chi-squared"):
            assert_chi_squared({"00": 6000, "11": 4000}, BELL, alpha=0.01)

    def test_unexpected_outcome_fails_by_default(self):
        with pytest.raises(QuantumAssertionError):
            assert_chi_squared({"00": 500, "11": 480, "01": 20}, BELL, alpha=0.01)

    def test_unexpected_outcome_tolerated_when_configured(self):
        assert_chi_squared(
            {"00": 500, "11": 490, "01": 10}, BELL, alpha=0.01, unexpected_tolerance=0.05
        )


class TestAssertFidelity:
    def test_passes_high_fidelity(self):
        assert_fidelity({"00": 2020, "11": 1980}, BELL, min_fidelity=0.99)

    def test_fails_low_fidelity(self):
        with pytest.raises(QuantumAssertionError, match="fidelity"):
            assert_fidelity({"00": 3500, "11": 500}, BELL, min_fidelity=0.99)


class TestAssertProbability:
    def test_within_bounds(self):
        assert_probability({"00": 480, "11": 520}, "11", min_p=0.4, max_p=0.6)

    def test_outside_bounds(self):
        with pytest.raises(QuantumAssertionError, match="P\\(11\\)"):
            assert_probability({"00": 900, "11": 100}, "11", min_p=0.4, max_p=0.6)

    def test_missing_outcome_is_zero(self):
        assert_probability({"00": 100}, "11", max_p=0.0)


class TestAssertMatchesBaseline:
    def test_same_source_passes(self):
        assert_matches_baseline({"00": 2015, "11": 1985}, {"00": 1990, "11": 2010})

    def test_drift_fails(self):
        with pytest.raises(QuantumAssertionError, match="drifted"):
            assert_matches_baseline({"00": 3000, "11": 1000}, {"00": 2000, "11": 2000})

    def test_statistical_power_scales_with_shots(self):
        # A 2% bias is invisible at 200 shots but decisive at 200k shots.
        assert_matches_baseline({"00": 104, "11": 96}, {"00": 100, "11": 100})
        with pytest.raises(QuantumAssertionError):
            assert_matches_baseline(
                {"00": 104_000, "11": 96_000}, {"00": 100_000, "11": 100_000}
            )


def test_floor_math_is_self_consistent():
    # The floor promises: a perfect sampler stays under it with >= 99% probability.
    floor = stats.sampling_floor(2, 4000, confidence=0.99)
    assert 0 < floor < 0.05
    assert math.isfinite(floor)
