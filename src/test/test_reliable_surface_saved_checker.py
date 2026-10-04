import numpy as np
from scipy import sparse
from src.solvers.fixed_phase_reliable_ports import save_surface_evidence
from benchmarks.reliable_port_checker import surface_array_checks


def test_surface_checker_from_original_arrays_and_damage(tmp_path):
    B = sparse.csr_matrix(
        np.array(
            [[1 + 2j, 0.1 + 0.2j], [0.5 + 0.3j, 2 - 0.1j], [0.2 - 0.1j, 0.3 + 0.4j]]
        )
    )
    D = B.conj().T
    H = np.array([1.0, 2.0])
    path = tmp_path / "surface.npz"
    save_surface_evidence(
        path, dict(analytic=(B, D, H), oracle1=(B, D, H), oracle2=(B, D, H))
    )
    x = surface_array_checks(path)
    assert all(r["maximum"] == 0 for v in x.values() for r in v.values())
    save_surface_evidence(
        path, dict(analytic=(B, D * 1.1, H), oracle1=(B, D, H), oracle2=(B, D, H))
    )
    x = surface_array_checks(path)
    assert x["physical"]["D"]["maximum"] > 0.09
