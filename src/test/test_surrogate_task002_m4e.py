from __future__ import annotations

import numpy as np
import pytest

from src.solvers.dtn_port_3d import (
    _outgoing_projection,
    _sampled_tangential_projection,
)


@pytest.mark.parametrize(
    "mode",
    [
        np.asarray([[-0.8, 0.6, 0.0], [-0.6j, -0.8j, 0.0]], dtype=complex),
        np.asarray([[0.04, 0.06, 0.997], [0.03j, -0.05j, 0.998]], dtype=complex),
        np.asarray([[0.04 + 0.01j, 0.06 - 0.02j, 0.997 - 0.003j]], dtype=complex),
    ],
    ids=("oblique_S", "oblique_P_nonzero_Ez", "lossy_bottom_P"),
)
def test_sampled_tangential_projection_recovers_complex_amplitude(mode: np.ndarray) -> None:
    amplitude = 0.37 - 0.21j
    electric = amplitude * mode
    electric[:, 2] += 123.0 - 77.0j
    assert _sampled_tangential_projection(electric, mode) == pytest.approx(
        amplitude, abs=2e-15,
    )


def test_top_incident_subtraction_and_bottom_identity() -> None:
    incident = 0.8 + 0.1j
    outgoing = -0.2 + 0.3j
    assert _outgoing_projection(incident + outgoing, incident, "top") == pytest.approx(outgoing)
    assert _outgoing_projection(outgoing, incident, "bottom") == pytest.approx(outgoing)
    with pytest.raises(ValueError, match="side"):
        _outgoing_projection(outgoing, incident, "left")
