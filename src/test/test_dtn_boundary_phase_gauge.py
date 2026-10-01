"""Staged gauge tests, all NOT RUN. No global PDE factor is required.

The all-mode oracle uses separate literal UFL forms, full actual MPC, the
same Gauss rule, and all independent 3D FE coordinates. It does not assume
that fresh centered stored coefficients equal the clipped old carrier.
"""

import json
import os
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from src.solvers.dtn_boundary_phase_gauge import (
    GLOBAL_Z, BOUNDARY_PLANE, assembly_projection_denominator,
    global_amplitudes_from_solver, solver_amplitudes_from_global,
    plane_port_rhs_from_global, global_port_rhs_from_plane,
    incident_projection_in_solver_coordinates, outgoing_solver_amplitudes,
    boundary_mode_power_from_solver, phase_gauge_descriptor,
    prepare_boundary_plane_outputs, deep_frozen_identity,
    compiled_surface_quadrature_identity,
    analytic_lossless_evanescent_zero_power,
)


def _cfg():
    return SimpleNamespace(physical_z_min=-0.3, physical_z_max=1.0,
                           x_min=0.0, x_max=2.0, y_min=0.0, y_max=1.0,
                           n_air=1+0j, k0=1.0, mu_r=1+0j, kz=-0.5,
                           incident_amplitude=1+0j, polarization_vector=np.array([1, 0, 0]))


def _mode(side="top", kz=0.5, index=0):
    return SimpleNamespace(side=side, m=index, n=0, polarization="s",
                           k_vector=np.array([0, 0, kz], dtype=np.complex128),
                           e_vector=np.array([1, 0, 0], dtype=np.complex128),
                           electric_tangential_norm_sq=1.0)


def _relative(left, right):
    difference = np.linalg.norm(left - right)
    scale = np.linalg.norm(left) + np.linalg.norm(right)
    return float(difference / scale) if scale else (0.0 if difference == 0 else float("inf"))


def test_complex_augmented_nonzero_rhs_and_outgoing_coordinate_contract():
    cfg = _cfg()
    modes = [_mode(kz=0.3+2j), _mode(kz=-0.4+0.7j, index=1), _mode("bottom", -0.6-3j, 2)]
    scales = np.array([np.exp(1j*m.k_vector[2]*(cfg.physical_z_max if m.side == "top" else cfg.physical_z_min))
                       for m in modes])
    rng = np.random.default_rng(4053201)
    C = rng.normal(size=(4, 3)) + 1j*rng.normal(size=(4, 3))
    D = rng.normal(size=(3, 4)) + 1j*rng.normal(size=(3, 4))
    V = rng.normal(size=(4, 4)) + 1j*rng.normal(size=(4, 4))
    H = np.array([1.1, 2.3+0.4j, 4.6-0.2j])  # General algebra supplement.
    global_aug = np.block([[V, C*scales], [-scales.conj()[:, None]*D, np.diag(abs(scales)**2*H)]])
    plane_aug = np.block([[V, C], [-D, np.diag(H)]])
    x = rng.normal(size=(4, 5)) + 1j*rng.normal(size=(4, 5))
    a = rng.normal(size=(3, 5)) + 1j*rng.normal(size=(3, 5))
    b = solver_amplitudes_from_global(a, modes, cfg, BOUNDARY_PLANE)
    rhs_global = global_aug @ np.vstack([x, a])
    rhs_plane = np.vstack([rhs_global[:4], plane_port_rhs_from_global(rhs_global[4:], modes, cfg, BOUNDARY_PLANE)])
    np.testing.assert_allclose(plane_aug @ np.vstack([x, b]), rhs_plane, rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(global_amplitudes_from_solver(b, modes, cfg, BOUNDARY_PLANE), a,
                               rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(global_port_rhs_from_plane(rhs_plane[4:], modes, cfg, BOUNDARY_PLANE),
                               rhs_global[4:], rtol=1e-12, atol=1e-12)
    incident_global = 0.1*a
    incident_plane = solver_amplitudes_from_global(incident_global, modes, cfg, BOUNDARY_PLANE)
    np.testing.assert_allclose(
        global_amplitudes_from_solver(outgoing_solver_amplitudes(b, incident_plane, modes), modes, cfg, BOUNDARY_PLANE),
        outgoing_solver_amplitudes(a, incident_global, modes), rtol=1e-12, atol=1e-12,
    )
    np.testing.assert_array_equal(global_amplitudes_from_solver(a, modes, cfg, GLOBAL_Z), a)


def test_direct_plane_incident_and_power_equal_representable_global_contract():
    cfg, mode = _cfg(), _mode()
    incident_global = incident_projection_in_solver_coordinates(mode, cfg, GLOBAL_Z)
    incident_plane = incident_projection_in_solver_coordinates(mode, cfg, BOUNDARY_PLANE)
    scale = np.exp(1j*mode.k_vector[2]*cfg.physical_z_max)
    assert incident_plane == pytest.approx(scale*incident_global, rel=1e-12, abs=1e-12)
    a = 0.7-0.2j
    assert boundary_mode_power_from_solver(mode, cfg, a, GLOBAL_Z) == pytest.approx(
        boundary_mode_power_from_solver(mode, cfg, scale*a, BOUNDARY_PLANE), rel=1e-12, abs=1e-12,
    )


def test_direct_plane_H_and_power_do_not_require_representable_global_scale():
    cfg, mode = _cfg(), _mode(kz=1+1000j)
    assert assembly_projection_denominator(mode, cfg, BOUNDARY_PLANE) == 2.0
    assert boundary_mode_power_from_solver(mode, cfg, 1+0.2j, BOUNDARY_PLANE) > 0
    assert phase_gauge_descriptor(mode, cfg, BOUNDARY_PLANE)["log_abs_physical_boundary_phase"] == -1000
    with pytest.raises(FloatingPointError, match="unrepresentable"):
        global_amplitudes_from_solver([1], [mode], cfg, BOUNDARY_PLANE)
    plane = prepare_boundary_plane_outputs([1+0.2j], [0], [mode], cfg, include_global=False)
    assert plane["status"] == "plane_only_diagnostics" and plane["direct_plane_outgoing_power_diagnostic"][0] > 0
    stopped = prepare_boundary_plane_outputs([1+0.2j], [0], [mode], cfg)
    assert stopped["status"] == "controlled_stop_global_output_unrepresentable"
    assert stopped["global_output_failure"]["mode_index"] == 0
    assert stopped["plane_total_auxiliary"][0] == 1+0.2j
    assert stopped["direct_plane_outgoing_power_diagnostic"][0] > 0


def test_identity_is_recursively_frozen_and_power_underflow_rejected():
    original = {"phase_gauge": {"gauge": "boundary_plane"}, "context": {"mask": [1e-30, 1e-13]}}
    identity = deep_frozen_identity(original)
    original["phase_gauge"]["gauge"] = "wrong"
    assert identity["phase_gauge"]["gauge"] == "boundary_plane"
    with pytest.raises(TypeError):
        identity["phase_gauge"]["gauge"] = "wrong"
    cfg, mode = _cfg(), _mode(kz=1)
    with pytest.raises(FloatingPointError, match="unrepresentable"):
        boundary_mode_power_from_solver(mode, cfg, 1e-300, BOUNDARY_PLANE)


def test_conversion_rejects_overflow_nonzero_underflow_and_bad_shapes():
    cfg, mode = _cfg(), _mode(kz=1+450j)
    with pytest.raises(FloatingPointError, match="loses"):
        solver_amplitudes_from_global([1e-200], [mode], cfg, BOUNDARY_PLANE)
    with pytest.raises(FloatingPointError, match="overflows"):
        global_amplitudes_from_solver([1e200], [mode], cfg, BOUNDARY_PLANE)
    with pytest.raises(ValueError, match="shape"):
        plane_port_rhs_from_global(np.ones((1, 2, 3)), [mode], cfg, BOUNDARY_PLANE)
    with pytest.raises(ValueError, match="nonfinite"):
        global_amplitudes_from_solver([np.nan], [mode], cfg, BOUNDARY_PLANE)
    # Global total/incident can each be representable while their legacy
    # subtraction overflows. Plane diagnostics must survive that boundary.
    mode = _mode(kz=1+700j)
    stopped = prepare_boundary_plane_outputs([1e4], [-1e4], [mode], cfg)
    assert stopped["status"] == "controlled_stop_global_output_inconsistent"
    assert stopped["plane_outgoing_auxiliary"][0] == 2e4
    assert stopped["global_output_failure"]["mode_index"] == 0


def test_analytic_lossless_evanescent_signed_power_certificate():
    cfg = _cfg()
    mode = _mode(kz=1j*np.sqrt(3))
    mode.k_vector = np.array([2, 0, 1j*np.sqrt(3)], dtype=np.complex128)
    mode.e_vector = np.array([-1j*np.sqrt(3)/2, 0, 1], dtype=np.complex128)
    mode.refractive_index = 1+0j
    field = (0.6807367412098271+0.5502606205082826j)*mode.e_vector
    proof = analytic_lossless_evanescent_zero_power(mode, cfg, field)
    assert proof["proved"]
    assert abs(proof["raw_signed_power"]) <= proof["machine_epsilon_power_bound"]
    mode.e_vector = np.array([1, 0, 1], dtype=np.complex128)
    assert not analytic_lossless_evanescent_zero_power(mode, cfg, mode.e_vector)["proved"]


@pytest.mark.parametrize("kz,index", [(1+0j, 1+0j), (1+0.1j, 1+0.1j)])
def test_positive_power_propagating_or_lossy_underflow_is_not_exempt(kz, index):
    cfg, mode = _cfg(), _mode(kz=kz)
    mode.refractive_index = index
    assert not analytic_lossless_evanescent_zero_power(mode, cfg, mode.e_vector)["proved"]
    with pytest.raises(FloatingPointError, match="unrepresentable"):
        boundary_mode_power_from_solver(mode, cfg, 1e-300, BOUNDARY_PLANE)


@pytest.mark.skipif(os.environ.get("TASK40EXTRA_ALLOW_GAUGE_MPC_ORACLE") != "1",
                    reason="requires separate exact source/command/ABI/resource admission")
def test_actual_532_mode_same_gauss_full_mpc_coefficients_and_FE_action():
    from mpi4py import MPI
    from petsc4py import PETSc
    import ufl
    from dolfinx import fem
    from src.solvers.task40extra_y_orbit_reference import pilot_config
    from src.solvers.fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
        build_same_mesh_physical_action, build_physical_rhs, destroy_same_mesh_physical_action,
    )
    from src.solvers.fullspace_same_mesh_hcurl_pmg_setup import SAME_MESH_JIT_OPTIONS
    from src.solvers.dtn_port_3d import (
        _with_quadrature_degree, _assemble_mpc_form_vector, _set_scalar_constant,
        _traction_vector, _mode_projection_denominator,
    )
    assert MPI.COMM_WORLD.size == 1
    input_path = "input/task40extra_0p7nm_engineering/nonseparable_g0_p6_q4_review_v1.dat"
    cfg, axes, input_hash = pilot_config(input_path, azimuth_deg=5.0)
    levels = _build_same_mesh_levels(cfg, MPI.COMM_SELF, (2,), include_positive_coefficients=False)
    old = new = None
    raw_forms = {}
    try:
        old = build_same_mesh_physical_action(levels, cfg, 2, verify_dtn_quadrature=True)
        new = build_same_mesh_physical_action(levels, cfg, 2, dtn_phase_gauge=BOUNDARY_PLANE)
        from src.solvers.dtn_boundary_plane_qualification import qualify_boundary_plane_bundle
        record_path = Path(os.environ["TASK40EXTRA_GAUGE_ORACLE_RECORD"])
        packet = qualify_boundary_plane_bundle(
            new, record_path=record_path,
            expected_physical_manifest=old["mode_sha256"],
            expected_ordered_keys=tuple(entry.mode_key for entry in old["dtn_action"].carrier.entries),
            optional_legacy_bundle=old,
        )
        assert packet["status"] == "PASS_COMPONENT_ONLY"
        assert packet["PDE_solved"] is False and packet["official_results"] is False
    finally:
        raw_forms.clear()
        if new is not None:
            destroy_same_mesh_physical_action(new)
        if old is not None:
            destroy_same_mesh_physical_action(old)
        levels.clear()
