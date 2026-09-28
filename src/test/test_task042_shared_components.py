"""Targeted fixed-PC and opt-in profile regression; no FE imports or JIT."""

import numpy as np
import pytest

from src.io import load_and_resolve
from src.solvers.learned_coarse_inverse import BoundedBlockPC


def test_nested_complex_metadata_keeps_both_channels(tmp_path):
    import json

    from src.runners.task042_shared import write_json

    path = tmp_path / "complex.json"
    write_json(path, {"scalar": 1.0 + 2.0j, "array": np.array([3.0 - 4.0j])})
    assert json.loads(path.read_text()) == {
        "scalar": {"real": 1.0, "imag": 2.0},
        "array": [{"real": 3.0, "imag": -4.0}],
    }


def test_complex_disjoint_patches_are_bounded_and_do_not_solve_global():
    a = np.array(
        [
            [3 + 1j, 1, 2, 0, 0, 0],
            [1j, 4, 0, 1, 0, 0],
            [0, 1, 5 - 1j, 1, 0, 0],
            [1, 0, 2j, 3, 1, 0],
            [0, 0, 0, 1, 4, 1],
            [0, 0, 1, 0, 1j, 6],
        ],
        dtype=np.complex128,
    )
    reads = []

    def reader(start, stop):
        reads.append((start, stop))
        return a[start:stop, start:stop]

    pc = BoundedBlockPC(6, reader, width=2)
    r = np.arange(6, dtype=float).astype(np.complex128) + 1j
    z = pc.apply_array(r)
    assert reads == [(0, 2), (2, 4), (4, 6)]
    for start, stop in reads:
        np.testing.assert_allclose(
            a[start:stop, start:stop] @ z[start:stop], r[start:stop], rtol=1e-14
        )
    assert np.linalg.norm(a @ z - r) > 1e-2
    assert len(pc.declarations) == 3 and all(
        d.scope == "patch" and d.rows == 2 for d in pc.declarations
    )


def test_no_one_block_global_factor_or_excessive_preallocation():
    with pytest.raises(ValueError, match="smaller"):
        BoundedBlockPC(6, lambda *_: None, width=6)
    with pytest.raises(ValueError, match="budget"):
        BoundedBlockPC(60000, lambda *_: None, width=6000)


def test_profiles_preserve_physical_identity_and_old_input():
    seed = load_and_resolve(
        "input/task39extra/original_13p5nm_p6h10_balanced_h6_p4_v5.dat"
    )
    b0 = load_and_resolve("input/task042_neural_coarse_inverse/f1_b0_shared.dat")
    ref = load_and_resolve(
        "input/task042_neural_coarse_inverse/f1_reference_shared.dat"
    )
    assert (
        b0.physical_model_sha256
        == ref.physical_model_sha256
        == seed.physical_model_sha256
    )
    assert (
        seed.execution["terminate_memory_gib"] == 12.0
        and seed.solver["preconditioner"] == "balanced_h6_p4_v5"
    )
    assert (
        b0.execution["terminate_memory_gib"] == 16.0 and b0.execution["mpi_size"] == 1
    )
