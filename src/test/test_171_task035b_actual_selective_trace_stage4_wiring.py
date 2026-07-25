"""Inactive-row-free Stage-4 wiring for an actual selective-p6 bridge."""

from __future__ import annotations

from dataclasses import replace
from inspect import signature
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest
from dolfinx import mesh
from dolfinx.la.petsc import create_vector
from mpi4py import MPI
from petsc4py import PETSc

from src.common.config_3d import (
    SimulationConfig3D,
    target_stage4_config,
)
from src.solvers.common_3d_case_flow import (
    _invoke_actual_selective_trace_expansion_factory,
    run_prepared_3d_case_flow,
)
from src.solvers.dtn_port_3d import (
    _assembly_time_full_operator_residual,
    _assembly_time_trace_constraint_kwargs,
    _assign_fe_solution_from_assembly_time_condensation,
    _build_assembly_time_condensation_with_request,
    solve_stage4_dtn_port_total_field,
)
from src.solvers.hcurl_affine_isotropic_tensor import (
    AffineIsotropicMaxwellTensorSpec,
)
from src.solvers.hcurl_assembly_time_condensation import (
    build_unconstrained_assembly_time_condensation,
    generalized_reduced_primal_residual,
    prepare_cell_interior_rhs_recovery,
    validate_primal_recovery_mpc_backsubstitution,
)
from src.solvers.solve_maxwell_3d_stage_4b_block_grating import (
    run_stage4b_block_grating_3d_case,
)


pytest_plugins = (
    "src.test.test_147_task035b_actual_selective_trace_expansion",
)


def _qualified_config() -> SimulationConfig3D:
    return replace(
        target_stage4_config(degree=6, h_nm=100.0),
        case_name="task035b_actual_selective_trace_stage4_wiring",
        nedelec_trace_degree=6,
        nedelec_interior_degree=6,
        matrix_diagnostics_assemble_only=False,
        matrix_diagnostics_factorization_only=False,
        stage4_cell_static_condensation=True,
        stage4_assembly_time_cell_static_condensation=True,
        stage4_floquet_slave_elimination=True,
        stage4_affine_isotropic_reference_tensor=True,
        stage4_regionwise_interior_p=False,
        unique_output=False,
    )


def _cell_tags(function_space):
    msh = function_space.mesh
    tdim = msh.topology.dim
    owned_cells = int(msh.topology.index_map(tdim).size_local)
    return mesh.meshtags(
        msh,
        tdim,
        np.arange(owned_cells, dtype=np.int32),
        np.ones(owned_cells, dtype=np.int32),
    )


def _tensor_spec() -> AffineIsotropicMaxwellTensorSpec:
    return AffineIsotropicMaxwellTensorSpec(
        curl_coefficient=1.2 - 0.04j,
        mass_coefficient_by_tag={1: -2.3 + 0.17j},
    )


def _canonical_request_audit() -> dict[str, object]:
    return {
        "schema_version": (
            "task035b.canonical-orientation-reuse-request.v1"
        ),
        "accepted": False,
    }


def _set_distributed_values(
    vector: PETSc.Vec,
    global_values: np.ndarray,
) -> None:
    start, end = map(int, vector.getOwnershipRange())
    vector.getArray()[:] = np.asarray(
        global_values[start:end],
        dtype=PETSc.ScalarType,
    )
    vector.assemble()


def _pull_back_full_trace_action(
    *,
    ordinary,
    bridge,
    storage_action: PETSc.Vec,
) -> np.ndarray:
    local = np.zeros(bridge.active_rows, dtype=np.complex128)
    row_start, row_end = map(int, storage_action.getOwnershipRange())
    local_values = np.asarray(
        storage_action.getArray(readonly=True),
        dtype=np.complex128,
    )
    for original in ordinary.trace_constraints.owned_active_original_dofs:
        storage_row = ordinary.trace_constraints.original_to_active[
            int(original)
        ]
        assert row_start <= storage_row < row_end
        value = local_values[storage_row - row_start]
        active_rows, coefficients = (
            bridge.caller_trace_expansion.expansion_by_original[
                int(original)
            ]
        )
        local[active_rows] += np.conj(coefficients) * value
    global_values = np.empty_like(local)
    ordinary.matrix.getComm().tompi4py().Allreduce(
        local,
        global_values,
        op=MPI.SUM,
    )
    return global_values


class _ForbiddenSecondMpc:
    def __init__(self, function_space) -> None:
        self.function_space = function_space
        self.homogenize_calls = 0
        self.backsubstitution_calls = 0

    def homogenize(self, _field) -> None:
        self.homogenize_calls += 1
        raise AssertionError("selective recovery must not homogenize twice")

    def backsubstitution(self, _field) -> None:
        self.backsubstitution_calls += 1
        raise AssertionError("selective recovery must not backsubstitute twice")


def test_opt_in_factory_defaults_and_stage4_forwarding_are_explicit() -> None:
    parameter_names = (
        (run_prepared_3d_case_flow, "actual_selective_trace_expansion_factory"),
        (
            run_stage4b_block_grating_3d_case,
            "actual_selective_trace_expansion_factory",
        ),
        (
            solve_stage4_dtn_port_total_field,
            "actual_selective_trace_expansion",
        ),
    )
    for function, parameter_name in parameter_names:
        assert signature(function).parameters[parameter_name].default is None
    assert not hasattr(
        SimulationConfig3D(),
        "actual_selective_trace_expansion_factory",
    )

    sentinel = object()
    received: dict[str, object] = {}

    def factory(**kwargs):
        received.update(kwargs)
        return sentinel

    function_space = object()
    mesh_data = object()
    config = _qualified_config()
    floquet_data = object()
    assert (
        _invoke_actual_selective_trace_expansion_factory(
            factory,
            function_space=function_space,
            mesh_data=mesh_data,
            config=config,
            floquet_data=floquet_data,  # type: ignore[arg-type]
        )
        is sentinel
    )
    assert received == {
        "function_space": function_space,
        "mesh_data": mesh_data,
        "config": config,
        "floquet_data": floquet_data,
    }

    with patch(
        "src.solvers.solve_maxwell_3d_stage_4b_block_grating."
        "run_prepared_3d_case_flow",
        return_value={"sentinel": True},
    ) as prepared:
        result = run_stage4b_block_grating_3d_case(
            config,
            Path("/tmp/task035b-selective-trace-forwarding"),
            actual_selective_trace_expansion_factory=factory,
        )
    assert result == {"sentinel": True}
    assert (
        prepared.call_args.kwargs[
            "actual_selective_trace_expansion_factory"
        ]
        is factory
    )


@pytest.mark.skipif(
    MPI.COMM_WORLD.size not in {1, 2},
    reason="focused serial/MPI2 selective trace identity",
)
def test_actual_selective_bridge_reaches_core_without_inactive_rows(
    actual_selective_expansion_fixture,
) -> None:
    fixture = actual_selective_expansion_fixture
    comm = MPI.COMM_WORLD
    function_space = fixture.storage_space
    bridge = fixture.bridge
    tags = _cell_tags(function_space)
    config = _qualified_config()
    legacy_mpc = object()
    floquet_data = SimpleNamespace(mpc=legacy_mpc)

    ordinary_kwargs, ordinary_audit = (
        _assembly_time_trace_constraint_kwargs(
            function_space=function_space,
            mesh_data=SimpleNamespace(mesh=fixture.mesh),
            cfg=config,
            floquet_data=floquet_data,
            actual_selective_trace_expansion=None,
        )
    )
    assert ordinary_kwargs == {"mpc": legacy_mpc}
    assert ordinary_audit is None

    selective_kwargs, request_audit = (
        _assembly_time_trace_constraint_kwargs(
            function_space=function_space,
            mesh_data=SimpleNamespace(mesh=fixture.mesh),
            cfg=config,
            floquet_data=floquet_data,
            actual_selective_trace_expansion=bridge,
        )
    )
    assert set(selective_kwargs) == {"caller_trace_expansion"}
    assert "mpc" not in selective_kwargs
    assert request_audit is not None
    assert request_audit["pass"] is True
    assert request_audit["legacy_mpc_passed_to_condensation"] is False
    assert request_audit["inactive_missing_p6_rows_allocated"] == 0

    ordinary = build_unconstrained_assembly_time_condensation(
        None,
        function_space,
        tags,
        affine_isotropic_tensor_spec=_tensor_spec(),
    )
    selected = _build_assembly_time_condensation_with_request(
        None,
        function_space,
        tags,
        canonical_orientation_request_audit=_canonical_request_audit(),
        affine_isotropic_tensor_spec=_tensor_spec(),
        **selective_kwargs,
    )
    q_vector = None
    selected_action = None
    storage_vector = None
    storage_action = None
    selected_rhs = None
    full_rhs = None
    embedded = None
    try:
        assert ordinary.matrix.getSize() == (
            bridge.full_p6_storage_trace_rows,
            bridge.full_p6_storage_trace_rows,
        )
        assert selected.matrix.getSize() == (
            bridge.active_rows,
            bridge.active_rows,
        )
        assert bridge.active_rows < bridge.full_p6_storage_trace_rows
        assert bridge.audit["inactive_missing_orbit_count"] > 0
        assert (
            selected.build_audit[
                "inactive_trace_modes_receive_petsc_rows"
            ]
            is False
        )
        assert (
            selected.trace_constraints.build_audit[
                "complete_storage_trace_pullback"
            ]
            is True
        )
        assert (
            selected.trace_constraints.build_audit[
                "post_recovery_mpc_backsubstitution_forbidden"
            ]
            is True
        )

        q = np.asarray(
            [
                (0.3 + 0.004 * (index + 1))
                * np.exp(1j * 0.017 * (index + 1))
                for index in range(bridge.active_rows)
            ],
            dtype=np.complex128,
        )
        q_vector = selected.matrix.createVecRight()
        _set_distributed_values(q_vector, q)
        selected_action = selected.matrix.createVecLeft()
        selected.matrix.mult(q_vector, selected_action)

        storage_values = np.zeros(
            bridge.full_p6_storage_trace_rows,
            dtype=np.complex128,
        )
        for original, storage_row in ordinary.trace_constraints.original_to_active.items():
            active_rows, coefficients = (
                bridge.caller_trace_expansion.expansion_by_original[
                    int(original)
                ]
            )
            storage_values[int(storage_row)] = coefficients @ q[active_rows]
        storage_vector = ordinary.matrix.createVecRight()
        _set_distributed_values(storage_vector, storage_values)
        storage_action = ordinary.matrix.createVecLeft()
        ordinary.matrix.mult(storage_vector, storage_action)
        expected_action = _pull_back_full_trace_action(
            ordinary=ordinary,
            bridge=bridge,
            storage_action=storage_action,
        )
        selected_start, selected_end = map(
            int,
            selected_action.getOwnershipRange(),
        )
        np.testing.assert_allclose(
            selected_action.getArray(readonly=True),
            expected_action[selected_start:selected_end],
            rtol=3.0e-11,
            atol=3.0e-10,
        )

        selected_rhs = selected_action.copy()
        reduced_residual = generalized_reduced_primal_residual(
            selected,
            selected_rhs,
            q_vector,
        )
        assert reduced_residual["caller_owned_active_rows_used"] is True
        assert reduced_residual["fresh_explicit_petsc_matmult"] is True
        assert reduced_residual["linear_system_residual_norm"] <= 2.0e-10

        recovery_policy = validate_primal_recovery_mpc_backsubstitution(
            selected,
            requested=False,
        )
        assert recovery_policy["mpc_backsubstitution_permitted"] is False
        with pytest.raises(
            RuntimeError,
            match="duplicate MPC backsubstitution is forbidden",
        ):
            validate_primal_recovery_mpc_backsubstitution(
                selected,
                requested=True,
            )

        index_map = function_space.dofmap.index_map
        block_size = function_space.dofmap.index_map_bs
        full_rhs = create_vector([(index_map, block_size)])
        full_rhs.set(PETSc.ScalarType(0.0))
        full_rhs.assemble()
        prepare_cell_interior_rhs_recovery(
            selected,
            full_rhs,
            release_nonprimal_caches=False,
        )
        forbidden_mpc = _ForbiddenSecondMpc(function_space)
        recovered_field, embedded, recovery_audit = (
            _assign_fe_solution_from_assembly_time_condensation(
                q_vector,
                selected,
                SimpleNamespace(mpc=forbidden_mpc),
                full_rhs,
            )
        )
        assert recovery_audit["generalized_caller_trace_expansion"] is True
        assert (
            recovery_audit["post_recovery_mpc_backsubstitution_applied"]
            is False
        )
        assert forbidden_mpc.homogenize_calls == 0
        assert forbidden_mpc.backsubstitution_calls == 0

        full_residual = _assembly_time_full_operator_residual(
            None,
            SimpleNamespace(mpc=forbidden_mpc),
            embedded,
            selected.matrix,
            selected_rhs,
            q_vector,
            selected,
            full_rhs,
            function_space=function_space,
            affine_isotropic_tensor_spec=_tensor_spec(),
            recovered_field=recovered_field,
        )
        assert (
            full_residual["full_global_matrix_allocated_for_residual"]
            is False
        )
        assert (
            full_residual["full_trace_matrix_allocated_for_residual"]
            is False
        )
        assert full_residual["reduced_trace_dtn_residual_norm"] <= 2.0e-10
        assert (
            full_residual["eliminated_cell_interior_residual_norm"]
            <= 2.0e-8
        )
        assert np.isfinite(full_residual["linear_system_residual_norm"])
        assert len(
            set(
                comm.allgather(
                    request_audit["selection_sha256"],
                )
            )
        ) == 1
    finally:
        if embedded is not None:
            embedded.destroy()
        if full_rhs is not None:
            full_rhs.destroy()
        if selected_rhs is not None:
            selected_rhs.destroy()
        if storage_action is not None:
            storage_action.destroy()
        if storage_vector is not None:
            storage_vector.destroy()
        if selected_action is not None:
            selected_action.destroy()
        if q_vector is not None:
            q_vector.destroy()
        selected.destroy()
        ordinary.destroy()


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 1,
    reason="serial fail-closed identity mutations",
)
def test_selective_request_rejects_wrong_storage_and_stale_hash(
    actual_selective_expansion_fixture,
) -> None:
    fixture = actual_selective_expansion_fixture
    config = _qualified_config()
    floquet_data = SimpleNamespace(mpc=object())
    with pytest.raises(
        ValueError,
        match="qualified standard covariant-Piola p6",
    ):
        _assembly_time_trace_constraint_kwargs(
            function_space=fixture.fixed_space,
            mesh_data=SimpleNamespace(mesh=fixture.mesh),
            cfg=config,
            floquet_data=floquet_data,
            actual_selective_trace_expansion=fixture.bridge,
        )

    stale_audit = dict(fixture.bridge.audit)
    stale_audit["selection_sha256"] = "0" * 64
    stale = replace(fixture.bridge, audit=stale_audit)
    with pytest.raises(
        ValueError,
        match="caller qualification is incomplete or stale",
    ):
        _assembly_time_trace_constraint_kwargs(
            function_space=fixture.storage_space,
            mesh_data=SimpleNamespace(mesh=fixture.mesh),
            cfg=config,
            floquet_data=floquet_data,
            actual_selective_trace_expansion=stale,
        )
