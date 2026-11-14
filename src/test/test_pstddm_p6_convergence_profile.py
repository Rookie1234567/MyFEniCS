from __future__ import annotations

import math
import os
from pathlib import Path
import sys
import tempfile
import tomllib
from unittest.mock import patch

from src.common.runtime_resource_policy import disk_reserve_bytes, resource_policy, factor_checkpoint_enabled
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


def test_retry_keeps_original_math_and_separate_case_identity():
    from src.runners.pstddm_p6_convergence import _validate_case
    root=Path(__file__).resolve().parents[2]/'input/pstddm_p6_convergence_workstation'
    old=tomllib.loads((root/'13p5_h10_direct.dat').read_text())
    new=tomllib.loads((root/'13p5_h10_direct_retry1.dat').read_text())
    assert {k:v for k,v in old.items() if k!='case_id'} == {k:v for k,v in new.items() if k!='case_id'}
    assert _validate_case(new)['case_id'] != _validate_case(old)['case_id']
    for bad in ('p6_h10_direct_13p5_retry0','p6_h7p5_direct_13p5_retry1','../retry1'):
        try: _validate_case({**new,'case_id':bad})
        except ValueError: pass
        else: raise AssertionError('invalid retry identity accepted')


def test_explicit_compiler_context_and_prefix_do_not_mutate_sysconfig():
    import sysconfig
    from src.common.runtime_resource_policy import mumps_compiler_command
    from src.runners.pstddm_p6_convergence import qualified_mumps_compiler_command
    before=sysconfig.get_config_var('CC')
    with tempfile.TemporaryDirectory() as temporary:
        prefix=Path(temporary)
        compiler=prefix/'bin/x86_64-conda-linux-gnu-cc'
        compiler.parent.mkdir(); compiler.write_text('#!/bin/sh\n');compiler.chmod(0o700)
        (prefix/'x86_64-conda-linux-gnu/sysroot').mkdir(parents=True)
        with patch.object(sys,'prefix',str(prefix)),patch.dict(os.environ,{'_MYFENICS_CLOUD_QUALIFIED_ACTIVATION':'1'}):
            command=qualified_mumps_compiler_command()
        assert mumps_compiler_command() is None
        with resource_policy(lambda *_a,**_k: None,mumps_compiler_command=command):
            assert mumps_compiler_command()==command
        assert mumps_compiler_command() is None
        assert sysconfig.get_config_var('CC')==before


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
    assert cfg.write_visualization_files is False


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
    assert factor_checkpoint_enabled() is True
    with resource_policy(callback, disk_reserve_bytes=DISK_RESERVE_BYTES, factor_checkpoint=False):
        assert disk_reserve_bytes(2**31) == DISK_RESERVE_BYTES
        assert factor_checkpoint_enabled() is False
    assert factor_checkpoint_enabled() is True
    assert disk_reserve_bytes(2**31) == 2**31
    assert TASK_CAP_BYTES == 64 << 30
    assert HOST_RESERVE_BYTES == 400 << 30
    from benchmarks.pstddm_partition_pilot.supervise import _workstation_disk_floor
    assert DISK_RESERVE_BYTES == _workstation_disk_floor('workstation-p6') == 380_000_000_000
    assert _workstation_disk_floor('workstation') == 400_000_000_000

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
