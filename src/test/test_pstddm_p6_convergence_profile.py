from __future__ import annotations

import math

from src.common.runtime_resource_policy import disk_reserve_bytes, resource_policy
from src.runners.pstddm_p6_convergence import (
    DISK_RESERVE_BYTES,
    EXPECTED_MODE_COUNT,
    HOST_RESERVE_BYTES,
    TASK_CAP_BYTES,
    _assembly_future_bytes,
    _direct_gates,
    _mode_inventory,
    axis_values_for_h,
    build_p6_config,
    mesh_plan,
)
from src.solvers.pstddm_material import derive_si_optical_identity


def test_piecewise_h_axes_are_material_fitted_and_match_frozen_counts():
    coarse = mesh_plan(10.0)
    fine = mesh_plan(7.5)
    assert coarse["axis_cell_counts"] == [6, 6, 14]
    assert coarse["cells"] == 504
    assert fine["axis_cell_counts"] == [9, 7, 20]
    assert fine["cells"] == 1260
    assert {16.5, 33.5}.issubset(axis_values_for_h(10.0)["x"])
    assert {15.0, 35.0}.issubset(axis_values_for_h(7.5)["y"])
    for h in (10.0, 7.5):
        for values in axis_values_for_h(h).values():
            assert max(b - a for a, b in zip(values[:-1], values[1:], strict=True)) <= h + 1.0e-12


def test_p6_config_inherits_workstation_mode_padding_and_exact_physics():
    material = derive_si_optical_identity(13.5)
    case = {"case_id": "p6_h10_direct_13p5", "h_nm": 10.0, "wavelength_nm": 13.5}
    cfg = build_p6_config(case, material)
    modes = _mode_inventory(cfg)
    assert modes["count"] == EXPECTED_MODE_COUNT == 612
    assert cfg.period_x == cfg.period_y == 50.0
    assert cfg.grating_width_x == 17.0 and cfg.grating_width_y == 20.0
    assert cfg.grating_height == 120.0
    assert cfg.incident_theta_deg == 89.0 and cfg.incident_phi_deg == 90.0
    assert cfg.polarization_kind == "s"
    assert cfg.stage4_boundary_model == "dtn_port"
    assert cfg.stage4_dtn_order_policy == "manual"
    assert cfg.dtn_phase_gauge == "boundary_plane"
    assert cfg.stage4_dtn_quadrature_degree == 28
    assert cfg.require_full_explicit_residual is True
    assert cfg.stage4_preserve_exact_geometry is True
    assert cfg.stage4_assembly_time_cell_static_condensation is True
    assert cfg.petsc_extra_options["pc_factor_mat_solver_type"] == "mumps"
    assert cfg.mesh_axis_cell_counts == (6, 6, 14)


def test_direct_gate_uses_explicit_full_residual_and_independent_energy_closure():
    summary = {
        "actual_pc_factor_solver_type": "mumps",
        "ksp_converged": True,
        "cell_static_condensation": {
            "full_explicit_true_residual": {
                "original_full_augmented_residual": {"relative_residual": 2.0e-10, "passed": True}
            }
        },
        "R_total": 0.2,
        "T_total": 0.7,
        "A_volume_total": 0.1001,
        "energy_closure_error_port_volume": 1.0e-4,
    }
    gates = _direct_gates(summary)
    assert gates["numerical_pass"] is False
    assert gates["physical_pass"] is False
    summary["cell_static_condensation"]["full_explicit_true_residual"][
        "original_full_augmented_residual"
    ]["relative_residual"] = 5.0e-11
    summary["A_volume_total"] = 0.1000005
    summary["energy_closure_error_port_volume"] = 5.0e-7
    gates = _direct_gates(summary)
    assert gates["numerical_pass"] is True
    assert gates["physical_pass"] is True
    assert math.isclose(gates["computed_energy_closure"], 5.0e-7, abs_tol=1.0e-15)


def test_resource_profile_overrides_mumps_and_checkpoint_floors_without_changing_defaults():
    assert disk_reserve_bytes(2**31) == 2**31
    callback = lambda *_args, **_kwargs: None
    with resource_policy(callback, disk_reserve_bytes=DISK_RESERVE_BYTES):
        assert disk_reserve_bytes(2**31) == DISK_RESERVE_BYTES
    assert disk_reserve_bytes(2**31) == 2**31
    assert TASK_CAP_BYTES == 64 << 30
    assert HOST_RESERVE_BYTES == 400 << 30

    from src.solvers.bounded_mumps import incore_memory_budget

    info = {"16": 1, "26": 0}
    observation = {
        "effective_cap_bytes": 70 << 30,
        "live_tree_and_supervisor_bytes": 1 << 30,
        "system": {"available": 500 << 30},
        "margin_bytes": 512 << 20,
    }
    old = incore_memory_budget(info, 1, observation, available_floor_bytes=400 << 30)
    p6 = incore_memory_budget(
        info,
        1,
        observation,
        available_floor_bytes=HOST_RESERVE_BYTES,
        mumps_task_limit_bytes=TASK_CAP_BYTES,
        future_co_resident_reserve_bytes=4 << 30,
    )
    assert old["mumps_task_limit_bytes"] == 10_000_000_000
    assert p6["mumps_task_limit_bytes"] == TASK_CAP_BYTES
    assert p6["future_co_resident_reserve_bytes"] == 4 << 30
    assert p6["external_future_bytes"] == 24 + (256 << 20) + (4 << 30)
