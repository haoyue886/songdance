import pytest

from scripts.audit_quantization_grid_drift import measure


def test_frame_quantized_regular_pulses_expose_accumulating_median_bias():
    times = [round(i * 0.5 / 0.02322) * 0.02322 for i in range(60)]
    result = measure(times)
    assert abs(result["span_average_interval"] - 0.5) < 0.001
    assert abs(result["endpoint_difference_seconds"]) > 0.5
    assert result["suggested_automatic_change"] is False


def test_exact_constant_grid_has_no_drift():
    assert measure([i * 0.5 for i in range(60)])["endpoint_difference_seconds"] == 0


def test_variable_performance_is_not_automatically_retimed():
    result = measure([0, 0.4, 0.9, 1.5, 2.2, 3])
    assert result["suggested_automatic_change"] is False


def test_non_increasing_times_rejected():
    with pytest.raises(ValueError):
        measure([0, 1, 0.5])
