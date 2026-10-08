"""K-normalized port algebra for Task40 two-cell p6 sectors."""

from types import SimpleNamespace

import numpy as np
import pytest

from src.runners.task40_v10_worker import (
    _task40_reference_replication_count,
    _task40_sector_port_vectors,
)


@pytest.mark.parametrize("replication_count", (2, 4))
def test_sector_port_vectors_preserve_complex_augmented_port_equation(
    replication_count,
):
    profile = SimpleNamespace(replication_count=replication_count)
    sectors = tuple(
        {"transport": SimpleNamespace(K=replication_count)}
        for _ in range(replication_count)
    )
    reference = {"profile": profile, "sectors": sectors}
    assert _task40_reference_replication_count(reference) == replication_count

    h = np.asarray([1.7, 2.3, 4.1, 5.9], dtype=np.float64)
    recovered = np.asarray(
        [0.2 + 0.4j, -0.3 + 0.1j, 0.7 - 0.8j, -0.5 - 0.2j],
        dtype=np.complex128,
    )
    port_rhs = np.asarray(
        [0.8 - 0.6j, -0.4 + 0.9j, 0.3 + 0.2j, 0.6 - 0.7j],
        dtype=np.complex128,
    )
    alpha = recovered + port_rhs / h
    mode_indices = np.asarray([1, 3], dtype=np.int64)

    local = _task40_sector_port_vectors(
        mode_indices,
        replication_count=replication_count,
        global_h=h,
        global_port_rhs=port_rhs,
        global_alpha=alpha,
    )
    root_k = np.sqrt(float(replication_count))
    np.testing.assert_allclose(local["local_h"], h[mode_indices] / replication_count)
    np.testing.assert_allclose(local["local_port_rhs"], port_rhs[mode_indices] / root_k)
    np.testing.assert_allclose(local["local_alpha"], alpha[mode_indices] * root_k)

    local_recovered = recovered[mode_indices] * root_k
    local_port_residual = (
        local["local_port_rhs"]
        + local["local_h"] * local_recovered
        - local["local_h"] * local["local_alpha"]
    )
    np.testing.assert_allclose(local_port_residual, 0.0, atol=1e-14)


def test_reference_replication_count_rejects_transport_mismatch():
    reference = {
        "profile": SimpleNamespace(replication_count=4),
        "sectors": ({"transport": SimpleNamespace(K=2)},),
    }
    with pytest.raises(ValueError, match="profile K differs"):
        _task40_reference_replication_count(reference)
