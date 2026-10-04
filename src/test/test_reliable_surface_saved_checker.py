import numpy as np
from scipy import sparse
from src.solvers.fixed_phase_reliable_ports import save_surface_evidence
from benchmarks.reliable_port_checker import (
    surface_array_checks,
    raw_surface_gate,
    physical_origin_sensitivity,
)


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
    assert all(v[k]["maximum"] == 0 for v in x.values() for k in ("B", "D", "H"))
    assert raw_surface_gate(x, 2)
    save_surface_evidence(
        path, dict(analytic=(B, D * 1.1, H), oracle1=(B, D, H), oracle2=(B, D, H))
    )
    x = surface_array_checks(path)
    assert x["physical"]["D"]["maximum"] > 0.09
    assert not raw_surface_gate(x, 2)


def test_old_operator_change_is_report_not_new_component_failure(tmp_path):
    B = sparse.csr_matrix(np.eye(2, dtype=complex))
    H = np.ones(2)
    path = tmp_path / "surface.npz"
    save_surface_evidence(
        path,
        dict(
            analytic=(B, B, H),
            oracle1=(B, B, H),
            oracle2=(B, B, H),
            old_q15=(B * 1.1, B, H),
        ),
    )
    raw = surface_array_checks(path)
    assert raw["old_q15_change"]["B"]["maximum"] > 0.09
    assert raw_surface_gate(raw, 2)
    assert not raw_surface_gate(raw, 3)
    raw["physical"]["D"]["relative"][0] = float("nan")
    assert not raw_surface_gate(raw, 2)


def projection_fixture():
    c = np.ones(2, complex)
    zero = np.zeros(2, complex)
    D = sparse.csr_matrix(np.array([[1, 0], [1, -1]], complex))
    coo = D.tocoo()
    H = np.array([1.0, 1e-12])
    a = dict(dp=coo.row, dr=coo.col, dv=coo.data, H=H, gp=zero)
    alpha = np.array([1, 0], complex)
    state = dict(
        c_scattered=c,
        background=zero,
        total_hi=c,
        total_lo=zero,
        alpha_scattered=alpha,
        background_alpha=zero,
        alpha_total_hi=alpha,
        alpha_total_lo=zero,
    )
    return a, state, D, H


def test_matrix_pair_pass_does_not_imply_actual_original_projection_pass(tmp_path):
    a, state, D, H = projection_fixture()
    other = D.toarray()
    other[1, 1] += 1e-15
    oracle = sparse.csr_matrix(other)
    path = tmp_path / "sensitivity.npz"
    save_surface_evidence(
        path,
        dict(analytic=(D.T, D, H), oracle1=(oracle.T, oracle, H), oracle2=(oracle.T, oracle, H)),
    )
    assert raw_surface_gate(surface_array_checks(path), 2)
    result = physical_origin_sensitivity(a, state, path)
    assert not result["all_physical_projections_within_1e_10"]
    assert result["rows"]["scattered"]["native_arithmetic_relative"] == 0
    assert result["rows"]["scattered"]["original_coordinates_relative"] > 9e-4
    assert result["rows"]["background"]["original_coordinates_relative"] == 0


def test_physical_origin_check_from_matching_frozen_oracle(tmp_path):
    a, state, D, H = projection_fixture()
    path = tmp_path / "matching.npz"
    save_surface_evidence(path, dict(analytic=(D.T, D, H), oracle1=(D.T, D, H), oracle2=(D.T, D, H)))
    result = physical_origin_sensitivity(a, state, path)
    assert result["all_physical_projections_within_1e_10"]
    assert all(r["all_modes"] == 2 for r in result["rows"].values())
    assert not result["strict_forward_solution_qualified"]
