import numpy as np

from scripts.audit_device_bass_audio import amplitude, evidence


def test_fundamental_measurement_distinguishes_upper_octave_control():
    rate = 22050
    time = np.arange(rate) / rate
    frequency = 440 * 2 ** ((36 - 69) / 12)
    upper = .2 * np.sin(2 * np.pi * 2 * frequency * time)
    low = .02 * np.sin(2 * np.pi * frequency * time)
    absent = amplitude(upper, rate, 36, .5)
    present = amplitude(upper + low, rate, 36, .5)
    assert present > 100 * absent
    assert .019 < present < .021


def test_silence_and_start_boundary_do_not_confirm_attack():
    audio = np.zeros(22050)
    result = evidence(audio, 22050, {'pitch': 36, 'start_sec': .09})
    assert result['before_amplitude'] is None
    assert result['amplitude_ratio'] is None
    assert result['status'] == 'boundary_unavailable'
    assert result['independent_attack_confirmed'] is False


def test_sustained_low_note_never_claims_independent_restrike():
    time = np.arange(22050) / 22050
    audio = .02 * np.sin(2 * np.pi * 65.4064 * time)
    result = evidence(audio, 22050, {'pitch': 36, 'start_sec': .5})
    assert .99 < result['amplitude_ratio'] < 1.01
    assert result['independent_attack_confirmed'] is False
