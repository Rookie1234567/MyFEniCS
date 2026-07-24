"""Opt-in port-plane scaling for the Task035b evanescent DtN buffer."""

from __future__ import annotations

import hashlib
import json

from basix.ufl import element
from dolfinx import default_real_type, fem
from mpi4py import MPI
import numpy as np
import pytest
from petsc4py import PETSc

from src.adaptivity.dtn_goal_adjoint import (
    DtnChannelGoal,
    build_dtn_channel_goal_gradient,
    dtn_channel_goal_value,
)
from src.adaptivity.target_fixed_trace_candidate import (
    _dtn_auxiliary_scaling_contract,
)
from src.common.config_3d import target_stage4_config
from src.common.modes_3d import outgoing_port_modes_3d
from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
from src.solvers.dtn_port_3d import (
    _ReusableSurfaceComponentAssembler,
    _global_auxiliary_values_from_solver_coordinates,
    _mode_assembly_projection_denominator,
    _mode_auxiliary_coordinate_scale,
    _mode_boundary_phase,
    _mode_projection_denominator,
    _mode_uses_boundary_referenced_auxiliary,
)


DEFAULT_MODE_SHA256 = (
    "f039dd14264f7bc2987e75e311ef338682388b1f17a4ea194702ff888f4c7a21"
)
BUFFER1_MODE_SHA256 = (
    "74f785341325c2f88a6512747bb4cf0d2cad1d8b8dc66fd0c7e2a63ee758f629"
)


def _mode_digest(modes) -> str:
    ordered = [
        (mode.side, mode.m, mode.n, mode.polarization)
        for mode in modes
    ]
    return hashlib.sha256(
        json.dumps(ordered, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def test_default_80_mode_path_keeps_global_z_coordinates_and_identity() -> None:
    config = target_stage4_config(degree=6, h_nm=15.0)
    modes = outgoing_port_modes_3d(config)

    assert config.stage4_dtn_evanescent_buffer == 0
    assert len(modes) == 80
    assert _mode_digest(modes) == DEFAULT_MODE_SHA256
    assert all(
        not _mode_uses_boundary_referenced_auxiliary(mode, config)
        for mode in modes
    )
    assert all(
        _mode_auxiliary_coordinate_scale(mode, config) == 1.0 + 0.0j
        for mode in modes
    )
    assert all(
        _mode_assembly_projection_denominator(mode, config)
        == _mode_projection_denominator(mode, config)
        for mode in modes
    )


def test_buffer1_boundary_coordinates_preserve_the_eliminated_dtn_operator() -> None:
    config = target_stage4_config(degree=6, h_nm=15.0)
    config.stage4_dtn_evanescent_buffer = 1
    modes = outgoing_port_modes_3d(config)

    assert len(modes) == 340
    assert _mode_digest(modes) == BUFFER1_MODE_SHA256
    scaled_modes = [
        mode
        for mode in modes
        if _mode_uses_boundary_referenced_auxiliary(mode, config)
    ]
    assert len(scaled_modes) == 260
    worst = min(
        scaled_modes,
        key=lambda mode: abs(_mode_boundary_phase(mode, config)),
    )
    scale = _mode_auxiliary_coordinate_scale(worst, config)
    denominator_global = _mode_projection_denominator(worst, config)
    denominator_boundary = _mode_assembly_projection_denominator(
        worst,
        config,
    )
    assert abs(scale) == pytest.approx(
        4.698738560873268e-84,
        rel=1.0e-12,
    )
    assert denominator_global == pytest.approx(
        abs(scale) ** 2 * denominator_boundary,
        rel=2.0e-15,
    )

    # The old global-z surface vectors equal ``s`` times their port-plane
    # counterparts.  Eliminating either auxiliary coordinate therefore
    # produces the same physical DtN Schur contribution.
    traction_boundary = 0.31 - 0.27j
    projection_boundary = -0.19 + 0.41j
    traction_global = scale * traction_boundary
    projection_global = scale * projection_boundary
    eliminated_global = (
        traction_global
        * np.conj(projection_global)
        / denominator_global
    )
    eliminated_boundary = (
        traction_boundary
        * np.conj(projection_boundary)
        / denominator_boundary
    )
    assert eliminated_global == pytest.approx(
        eliminated_boundary,
        rel=2.0e-15,
        abs=1.0e-18,
    )


def test_formal_port_scaling_contract_requires_actual_solver_provenance() -> None:
    assert _dtn_auxiliary_scaling_contract(
        {},
        evanescent_buffer=0,
    )["pass"] is True
    assert _dtn_auxiliary_scaling_contract(
        {},
        evanescent_buffer=1,
    )["pass"] is False

    summary = {
        "dtn_port_evanescent_mode_count": 260,
        "dtn_auxiliary_coordinate_scaling": {
            "status": "boundary_referenced_evanescent_buffer_active",
            "ordinary_default_changed": False,
            "solver_coordinate": (
                "a_solver=exp(i*kz*z_port)*a_global_z"
            ),
            "official_output_coordinate": "historical_global_z",
            "scaled_mode_count": 260,
            "minimum_abs_coordinate_scale": 4.698738560873268e-84,
            "minimum_assembly_projection_denominator": 32.1362606996094,
        },
    }
    passed = _dtn_auxiliary_scaling_contract(
        summary,
        evanescent_buffer=1,
    )
    assert passed["pass"] is True
    assert passed["status"] == "actual_boundary_referenced_scaling_pass"

    for key, value in (
        ("scaled_mode_count", 259),
        ("minimum_abs_coordinate_scale", float("nan")),
        ("minimum_assembly_projection_denominator", 0.0),
        ("ordinary_default_changed", True),
        ("solver_coordinate", "wrong"),
        ("official_output_coordinate", "wrong"),
        ("status", "wrong"),
    ):
        tampered = json.loads(json.dumps(summary))
        tampered["dtn_auxiliary_coordinate_scaling"][key] = value
        assert _dtn_auxiliary_scaling_contract(
            tampered,
            evanescent_buffer=1,
        )["pass"] is False


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 1,
    reason="tiny assembled operator-equivalence gate is serial",
)
def test_tiny_assembled_surface_vectors_preserve_schur_action(
    tmp_path,
) -> None:
    config = target_stage4_config(degree=2, h_nm=50.0)
    config.stage4_dtn_evanescent_buffer = 1
    mesh_data = build_airbox_mesh_3d(config, tmp_path / "mesh")
    space = fem.functionspace(
        mesh_data.mesh,
        element(
            "N1curl",
            mesh_data.mesh.basix_cell(),
            2,
            dtype=default_real_type,
        ),
    )
    modes = outgoing_port_modes_3d(config)
    mode = min(
        (
            candidate
            for candidate in modes
            if _mode_uses_boundary_referenced_auxiliary(
                candidate,
                config,
            )
        ),
        key=lambda candidate: abs(
            _mode_boundary_phase(candidate, config)
        ),
    )
    tag = (
        config.tags.z_max
        if mode.side == "top"
        else config.tags.z_min
    )
    boundary_z = (
        config.physical_z_max
        if mode.side == "top"
        else config.physical_z_min
    )
    global_vector = _ReusableSurfaceComponentAssembler(
        space,
        mesh_data,
        tag,
        0,
    ).assemble_unconstrained_vector(mode)
    boundary_vector = _ReusableSurfaceComponentAssembler(
        space,
        mesh_data,
        tag,
        0,
        boundary_reference_z=float(boundary_z),
    ).assemble_unconstrained_vector(mode)
    scale = _mode_auxiliary_coordinate_scale(mode, config)
    difference = global_vector.copy()
    state = global_vector.duplicate()
    global_action = global_vector.copy()
    boundary_action = boundary_vector.copy()
    try:
        difference.axpy(PETSc.ScalarType(-scale), boundary_vector)
        relative_vector_error = float(
            difference.norm() / max(global_vector.norm(), 1.0e-300)
        )
        assert relative_vector_error <= 5.0e-12

        owned = state.getOwnershipRange()
        state.setValues(
            np.arange(owned[0], owned[1], dtype=PETSc.IntType),
            np.asarray(
                [
                    complex(0.01 * (index + 1), -0.003 * (index + 2))
                    for index in range(owned[0], owned[1])
                ],
                dtype=np.complex128,
            ),
        )
        state.assemble()
        denominator_global = _mode_projection_denominator(
            mode,
            config,
        )
        denominator_boundary = (
            _mode_assembly_projection_denominator(mode, config)
        )
        global_action.scale(
            PETSc.ScalarType(
                global_vector.dot(state) / denominator_global
            )
        )
        boundary_action.scale(
            PETSc.ScalarType(
                boundary_vector.dot(state) / denominator_boundary
            )
        )
        global_action.axpy(
            PETSc.ScalarType(-1.0),
            boundary_action,
        )
        relative_schur_error = float(
            global_action.norm()
            / max(boundary_action.norm(), 1.0e-300)
        )
        assert relative_schur_error <= 1.0e-11
    finally:
        difference.destroy()
        state.destroy()
        global_action.destroy()
        boundary_action.destroy()
        global_vector.destroy()
        boundary_vector.destroy()


def test_solver_boundary_amplitudes_restore_historical_global_z_convention() -> None:
    config = target_stage4_config(degree=6, h_nm=15.0)
    config.stage4_dtn_evanescent_buffer = 1
    modes = outgoing_port_modes_3d(config)
    global_values = np.asarray(
        [
            complex(0.001 * (index + 1), -0.0007 * (index + 2))
            for index in range(len(modes))
        ],
        dtype=np.complex128,
    )
    scales = np.asarray(
        [_mode_auxiliary_coordinate_scale(mode, config) for mode in modes],
        dtype=np.complex128,
    )
    solver_values = scales * global_values
    restored = _global_auxiliary_values_from_solver_coordinates(
        modes,
        config,
        solver_values,
    )

    assert np.allclose(restored, global_values, rtol=2.0e-15, atol=0.0)
    assert np.allclose(
        restored * scales,
        solver_values,
        rtol=2.0e-15,
        atol=0.0,
    )


@pytest.mark.parametrize(
    "quantity",
    ("amplitude_real", "amplitude_imag", "power"),
)
def test_channel_adjoint_applies_auxiliary_coordinate_chain_rule(
    quantity: str,
) -> None:
    config = target_stage4_config(degree=6, h_nm=15.0)
    config.stage4_dtn_evanescent_buffer = 1
    modes = outgoing_port_modes_3d(config)
    mode_index = next(
        index
        for index, mode in enumerate(modes)
        if (
            mode.side == "bottom"
            and mode.power_per_unit_amplitude > 0.0
            and _mode_uses_boundary_referenced_auxiliary(mode, config)
        )
    )
    selected = modes[mode_index]
    scales = np.asarray(
        [_mode_auxiliary_coordinate_scale(mode, config) for mode in modes],
        dtype=np.complex128,
    )
    solver_values = np.full(len(modes), 0.002 - 0.001j)
    global_values = solver_values / scales
    n_fe = 2
    state_values = np.concatenate(
        (np.asarray((0.1 + 0.2j, -0.3j)), solver_values)
    )
    state = PETSc.Vec().createSeq(len(state_values))
    state.setValues(
        np.arange(len(state_values), dtype=PETSc.IntType),
        state_values,
    )
    state.assemble()
    context = {
        "num_fem_dofs_after_mpc": n_fe,
        "modes": modes,
        "auxiliary_values": global_values,
        "incident_projections": np.zeros(len(modes), dtype=np.complex128),
        "auxiliary_coordinate_scales": scales,
    }
    goal = DtnChannelGoal(
        selected.side,
        selected.m,
        selected.n,
        selected.polarization,
        quantity,
    )
    gradient, metadata = build_dtn_channel_goal_gradient(
        state,
        config,
        context,
        goal=goal,
    )
    direction_values = np.zeros_like(state_values)
    direction_values[n_fe + mode_index] = 0.37 - 0.21j
    direction = PETSc.Vec().createSeq(len(state_values))
    direction.setValues(
        np.arange(len(state_values), dtype=PETSc.IntType),
        direction_values,
    )
    direction.assemble()
    step = 1.0e-7
    solver_direction = direction_values[n_fe:]
    plus = dtn_channel_goal_value(
        config,
        modes,
        global_values + step * solver_direction / scales,
        context["incident_projections"],
        goal=goal,
    )
    minus = dtn_channel_goal_value(
        config,
        modes,
        global_values - step * solver_direction / scales,
        context["incident_projections"],
        goal=goal,
    )
    finite_difference = (plus - minus) / (2.0 * step)
    analytic = float(np.real(gradient.dot(direction)))

    assert finite_difference == pytest.approx(
        analytic,
        rel=2.0e-8,
        abs=2.0e-10,
    )
    if quantity in {"amplitude_real", "amplitude_imag"}:
        assert metadata["gradient_norm"] == pytest.approx(1.0)
    else:
        assert metadata["gradient_norm"] > 0.0
    direction.destroy()
    gradient.destroy()
    state.destroy()
