import numpy as np
import pytest

from src.solvers.floquet_background_hcurl import (
    PeriodicBox3D,
    apply_periodic_background_inverse,
    apply_periodic_background_operator,
    bloch_fft_frequencies,
    estimate_periodic_fft_working_set_bytes,
    maxwell_fourier_symbol,
    maxwell_symbol_inverse,
    relative_l2_error,
    transverse_longitudinal_projectors,
)


def test_bloch_fft_frequencies_follow_numpy_order():
    values = bloch_fft_frequencies(4, 2.0, 0.3)
    expected = 0.3 + 2.0 * np.pi * np.fft.fftfreq(4, d=0.5)
    assert np.linalg.norm(values - expected) < 1.0e-14


def test_transverse_longitudinal_projectors():
    transverse, longitudinal = transverse_longitudinal_projectors((1.0, 2.0, -1.0))
    identity = np.eye(3)
    assert np.linalg.norm(transverse + longitudinal - identity) < 1.0e-14
    assert np.linalg.norm(transverse @ longitudinal) < 1.0e-14
    assert np.linalg.norm(transverse @ transverse - transverse) < 1.0e-14
    assert np.linalg.norm(longitudinal @ longitudinal - longitudinal) < 1.0e-14


def test_symbol_inverse_matches_dense_inverse():
    kwargs = {
        "mu_inv": 0.9 - 0.07j,
        "epsilon": 1.8 + 0.12j,
        "k0": 1.3,
        "shift": -0.4j,
    }
    wavevector = (0.7, -1.1, 0.5)
    symbol = maxwell_fourier_symbol(wavevector, **kwargs)
    inverse = maxwell_symbol_inverse(wavevector, **kwargs)
    assert np.linalg.norm(symbol @ inverse - np.eye(3)) < 1.0e-12
    assert np.linalg.norm(inverse - np.linalg.inv(symbol)) < 1.0e-12


def test_symbol_requires_shift_near_resonance():
    k0 = 2.0
    epsilon = 1.0
    wavevector = (k0, 0.0, 0.0)
    with pytest.raises(np.linalg.LinAlgError):
        maxwell_symbol_inverse(
            wavevector,
            mu_inv=1.0,
            epsilon=epsilon,
            k0=k0,
        )


def test_periodic_fft_operator_inverse_round_trip():
    rng = np.random.default_rng(11)
    field = rng.standard_normal((4, 3, 5, 3)) + 1j * rng.standard_normal((4, 3, 5, 3))
    kwargs = {
        "box": PeriodicBox3D((2.0, 3.0, 4.0)),
        "bloch": (0.17, -0.09, 0.13),
        "mu_inv": 1.1 - 0.03j,
        "epsilon": 1.7 + 0.08j,
        "k0": 0.9,
        "shift": -0.35j,
    }
    applied = apply_periodic_background_operator(field, **kwargs)
    recovered = apply_periodic_background_inverse(applied, **kwargs)
    assert relative_l2_error(recovered, field) < 2.0e-12


def test_fft_working_set_payload_estimate():
    expected = 5 * 7 * 9 * 3 * 6 * 16
    assert (
        estimate_periodic_fft_working_set_bytes(
            (5, 7, 9), live_complex_vectors=6
        )
        == expected
    )
