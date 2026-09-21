"""Focused Task041 H1c tests for the real physical-side operators."""

from __future__ import annotations

import json

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

from src.common.config_3d import (
    ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND,
    SimulationConfig3D,
)
from src.geometry.hybrid_local_mesh import build_hybrid_local_mesh
from src.solvers.dtn_port_3d import _augmented_vec_from_base
from src.solvers.hcurl_assembly_time_condensation import (
    recover_owned_cell_interiors,
)
from src.solvers.hybrid_local_dtn import assemble_hybrid_local_dtn_system
from src.solvers.hybrid_local_dtn_action import (
    assemble_hybrid_local_dtn_action_system,
)
from src.solvers.hybrid_local_dtn_woodbury import ResearchExactFactorInverse
from src.solvers.physical_balanced_physical_operator import (
    FullSpacePhysicalDtnActionSystem,
    P4CondensedExactFactor,
    P4ExactFactor,
    _assemble_augmented_matrix,
    _build_matching_p4_action,
    build_fullspace_physical_dtn_action,
    build_p4_condensed_exact_factor_from_action,
    build_p4_exact_factor,
)
from src.solvers.physical_balanced_same_mesh_transfer import (
    build_same_mesh_hcurl_owner_transfer,
)
from src.solvers.physical_balanced_side_inverse import (
    build_side_balanced_inverse,
)
from src.solvers.physical_balanced_trace_bridge import (
    extract_full_p6_to_active_trace,
    inject_active_residual_to_full_p6,
)

pytestmark = pytest.mark.skipif(
    MPI.COMM_WORLD.size not in (1, 2),
    reason="Task041 H1c focused physical tests are serial/MPI2 only",
)

# Review §6 accepts the p6 full/condensed reference and original physical
# residuals at 5e-9.  Mapping, p4, and global action checks retain 1e-10/1e-12.
_P6_TOLERANCE = 5.0e-9
_STRICT_TOLERANCE = 1.0e-10


def _fixture_config(degree: int, *, condensed: bool) -> SimulationConfig3D:
    return SimulationConfig3D(
        stage_case="stage4_block_grating",
        geometry_kind="rectangular_block_grating",
        lambda0=3.7,
        period_x=1.0,
        period_y=1.0,
        z_min=0.0,
        z_max=1.0,
        interface_z=0.5,
        n_substrate=1.4 + 0.02j,
        n_grating=1.7 + 0.01j,
        grating_width_x=1.0,
        grating_width_y=1.0,
        grating_height=0.5,
        incident_theta_deg=17.0,
        incident_phi_deg=23.0,
        polarization_kind="s",
        nedelec_degree=degree,
        mesh_cell_type="hexahedron",
        mesh_target_size=1.0,
        mesh_axis_cell_counts=(2, 2, 2),
        use_floquet_xy=True,
        floquet_constraint_mode=f"topological_trace_p{degree}",
        stage4_dtn_order_policy="manual",
        diffraction_zero_order_only=False,
        diffraction_order_max_m=1,
        diffraction_order_max_n=0,
        stage4_full3d_assembly_backend=(
            ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND
            if condensed
            else "standard_full"
        ),
    )


def _fill_algebraic(vector: PETSc.Vec, slaves: np.ndarray, seed: float) -> None:
    first, last = (int(value) for value in vector.getOwnershipRange())
    global_rows = np.arange(first, last, dtype=np.float64)
    vector.getArray()[:] = (
        seed
        + 0.01 * global_rows
        + 1.0
        + 1j * (0.2 * seed + 0.007 * global_rows + 0.3)
    ).astype(PETSc.ScalarType)
    local_slaves = np.asarray(slaves, dtype=np.int64)
    if len(local_slaves):
        vector.getArray()[local_slaves] = 0.0
    vector.assemble()


def _fill_active(vector: PETSc.Vec, seed: float) -> None:
    first, last = (int(value) for value in vector.getOwnershipRange())
    rows = np.arange(first, last, dtype=np.float64)
    vector.getArray()[:] = (
        seed + 0.013 * rows + 1j * (0.4 + 0.009 * rows)
    ).astype(PETSc.ScalarType)
    vector.assemble()


def _extract_fe_segment(augmented: PETSc.Vec, n_fe: int) -> PETSc.Vec:
    start, end = (int(value) for value in augmented.getOwnershipRange())
    local_fe = max(0, min(end, int(n_fe)) - start)
    result = PETSc.Vec().createMPI(
        (local_fe, int(n_fe)),
        comm=augmented.getComm(),
    )
    result_start, result_end = (int(value) for value in result.getOwnershipRange())
    if result_end > result_start:
        result.getArray()[:] = augmented.getValues(
            np.arange(result_start, result_end, dtype=PETSc.IntType)
        )
    result.assemble()
    return result


def _raw_residual_gate(
    residual: PETSc.Vec,
    rhs: PETSc.Vec,
    *,
    tolerance: float = _STRICT_TOLERANCE,
) -> dict[str, object]:
    comm = residual.getComm().tompi4py()
    finite_local = bool(
        np.isfinite(np.asarray(residual.getArray(readonly=True))).all()
    )
    finite = bool(comm.allreduce(finite_local, op=MPI.LAND))
    residual_norm = float(residual.norm())
    rhs_norm = float(rhs.norm())
    if rhs_norm == 0.0:
        relative = None
        passed = bool(finite and np.isfinite(residual_norm)
                      and residual_norm <= float(tolerance))
    else:
        relative = residual_norm / rhs_norm
        passed = bool(finite and np.isfinite(relative)
                      and relative <= float(tolerance))
    return {
        "tolerance": float(tolerance),
        "residual_norm": residual_norm,
        "rhs_norm": rhs_norm,
        "relative_residual": relative,
        "finite": finite and np.isfinite(residual_norm) and np.isfinite(rhs_norm),
        "passed": passed,
    }


def _raw_augmented_residual_metrics(
    matrix: PETSc.Mat,
    residual: PETSc.Vec,
    rhs: PETSc.Vec,
    solution: PETSc.Vec,
    fe_rows: int,
    *,
    tolerance: float,
) -> dict[str, object]:
    """Measure one oracle residual without making the oracle gate abort early."""

    comm = residual.getComm().tompi4py()
    start, end = (int(value) for value in residual.getOwnershipRange())
    values = np.asarray(residual.getArray(readonly=True), dtype=np.complex128)
    global_rows = np.arange(start, end, dtype=np.int64)
    fe_mask = global_rows < int(fe_rows)
    aux_mask = ~fe_mask
    local_fe_sq = float(np.vdot(values[fe_mask], values[fe_mask]).real)
    local_aux_sq = float(np.vdot(values[aux_mask], values[aux_mask]).real)
    fe_norm = float(np.sqrt(comm.allreduce(local_fe_sq, op=MPI.SUM)))
    aux_norm = float(np.sqrt(comm.allreduce(local_aux_sq, op=MPI.SUM)))
    residual_norm = float(residual.norm())
    rhs_norm = float(rhs.norm())
    solution_norm = float(solution.norm())
    matrix_norm = float(matrix.norm(PETSc.NormType.FROBENIUS))
    denominator = matrix_norm * solution_norm + rhs_norm
    if rhs_norm > 0.0:
        relative = residual_norm / rhs_norm
        gate_passed = bool(
            np.isfinite(relative) and relative <= float(tolerance)
        )
    else:
        relative = None
        gate_passed = bool(
            np.isfinite(residual_norm) and residual_norm <= float(tolerance)
        )
    backward_error = (
        residual_norm / denominator if denominator > 0.0 else residual_norm
    )
    return {
        "residual_norm": residual_norm,
        "relative_residual": relative,
        "fe_residual_norm": fe_norm,
        "aux_residual_norm": aux_norm,
        "rhs_norm": rhs_norm,
        "solution_norm": solution_norm,
        "matrix_frobenius_norm": matrix_norm,
        "consistent_norm_denominator": denominator,
        "consistent_backward_error": float(backward_error),
        "finite": bool(
            np.isfinite(values).all()
            and np.isfinite(
                [
                    residual_norm,
                    rhs_norm,
                    solution_norm,
                    matrix_norm,
                    denominator,
                    backward_error,
                ]
            ).all()
        ),
        "gate_passed": gate_passed,
    }


def _explicit_factor_solve(
    factor: ResearchExactFactorInverse,
    matrix: PETSc.Mat,
    rhs: PETSc.Vec,
    fe_rows: int,
    *,
    label: str,
    tolerance: float = _P6_TOLERANCE,
) -> tuple[PETSc.Vec, dict[str, object]]:
    solution = matrix.createVecRight()
    residual = rhs.duplicate()
    correction = None
    history: list[dict[str, object]] = []
    try:
        for iteration in range(3):
            if iteration == 0:
                factor.solve(rhs, solution)
            else:
                correction = matrix.createVecRight()
                try:
                    factor.solve(residual, correction)
                    solution.axpy(PETSc.ScalarType(-1.0), correction)
                finally:
                    correction.destroy()
                    correction = None
            matrix.mult(solution, residual)
            residual.axpy(PETSc.ScalarType(-1.0), rhs)
            metrics = _raw_augmented_residual_metrics(
                matrix,
                residual,
                rhs,
                solution,
                fe_rows,
                tolerance=tolerance,
            )
            metrics["iteration"] = int(iteration)
            history.append(metrics)
        final = history[-1]
        audit: dict[str, object] = {
            "label": label,
            "tolerance": float(tolerance),
            "raw_relative_residuals": tuple(
                item["relative_residual"] for item in history
            ),
            "history": tuple(history),
            "final_fe_residual_norm": final["fe_residual_norm"],
            "final_aux_residual_norm": final["aux_residual_norm"],
            "rhs_norm": final["rhs_norm"],
            "solution_norm": final["solution_norm"],
            "consistent_backward_error": final["consistent_backward_error"],
            "gate_passed": bool(final["finite"] and final["gate_passed"]),
        }
        if matrix.getComm().tompi4py().rank == 0:
            print(
                "H1c oracle "
                f"{label}: raw_relative={audit['raw_relative_residuals']}, "
                f"final_fe_abs={audit['final_fe_residual_norm']:.16e}, "
                f"final_aux_abs={audit['final_aux_residual_norm']:.16e}, "
                f"rhs_norm={audit['rhs_norm']:.16e}, "
                f"solution_norm={audit['solution_norm']:.16e}, "
                "Frobenius/2-norm backward_error="
                f"{audit['consistent_backward_error']:.16e}, "
                f"gate_tolerance={audit['tolerance']:.1e}, "
                f"gate={audit['gate_passed']}",
                flush=True,
            )
        return solution, audit
    except Exception:
        solution.destroy()
        raise
    finally:
        residual.destroy()
        if correction is not None:
            correction.destroy()


@pytest.fixture(scope="module")
def h1c_fixture():
    comm = MPI.COMM_WORLD
    cfg6 = _fixture_config(6, condensed=False)
    cfg_action = _fixture_config(6, condensed=True)
    meshes = {
        side: build_hybrid_local_mesh(
            cfg6,
            side,
            bottom_interface_z_nm=0.5,
            top_interface_z_nm=0.5,
            comm=comm,
        )
        for side in ("bottom", "top")
    }
    action_systems = {}
    p6: dict[str, FullSpacePhysicalDtnActionSystem] = {}
    p4: dict[str, P4ExactFactor] = {}
    full_oracle = {}
    condensed_oracle = {}
    full_factors = {}
    condensed_factors = {}
    owners = {}
    try:
        for side in ("bottom", "top"):
            action_systems[side] = assemble_hybrid_local_dtn_action_system(
                cfg_action,
                side,
                local_mesh_override=meshes[side],
                comm=comm,
            )
            p6[side] = build_fullspace_physical_dtn_action(
                action_systems[side]
            )
            p4[side] = build_p4_exact_factor(action_systems[side])
            full_oracle[side] = assemble_hybrid_local_dtn_system(
                cfg6,
                side,
                local_mesh_override=meshes[side],
                comm=comm,
            )
            condensed_oracle[side] = assemble_hybrid_local_dtn_system(
                cfg_action,
                side,
                local_mesh_override=meshes[side],
                comm=comm,
            )
            full_factors[side] = ResearchExactFactorInverse(
                full_oracle[side].A,
                factor_solver_type="mumps",
                factor_only_storage=True,
            )
            condensed_factors[side] = ResearchExactFactorInverse(
                condensed_oracle[side].A,
                factor_solver_type="mumps",
                factor_only_storage=True,
            )
            owners[side] = build_same_mesh_hcurl_owner_transfer(
                p6[side].V,
                p6[side].floquet_data,
                p4[side].physical_action.V,
                p4[side].physical_action.floquet_data,
            )
        yield {
            "cfg6": cfg6,
            "action_systems": action_systems,
            "p6": p6,
            "p4": p4,
            "condensed": action_systems,
            "full_oracle": full_oracle,
            "condensed_oracle": condensed_oracle,
            "full_factors": full_factors,
            "condensed_factors": condensed_factors,
            "owners": owners,
        }
    finally:
        for factor in full_factors.values():
            factor.destroy()
        for factor in condensed_factors.values():
            factor.destroy()
        for system in full_oracle.values():
            system.destroy()
        for system in condensed_oracle.values():
            system.destroy()
        for owner in owners.values():
            owner.destroy()
        for factor in p4.values():
            factor.destroy()
        for system in p6.values():
            system.destroy()
        for system in action_systems.values():
            system.destroy()


def test_task041_h1c_physical_galerkin_factor_and_alternation(h1c_fixture) -> None:
    data = h1c_fixture
    for side in ("bottom", "top"):
        p6 = data["p6"][side]
        p4 = data["p4"][side]
        owner = data["owners"][side]
        coarse_slaves = np.asarray(owner._coarse_slaves, dtype=np.int64)
        keys = {(int(mode.m), int(mode.n)) for mode in p6.modes}
        assert len(keys) >= 2
        assert any(m != 0 for m, _n in keys)
        q1 = p4.physical_action.action.context.input_vector.duplicate()
        q2 = q1.duplicate()
        p_q1 = None
        p_q2 = None
        p_q1_repeat = None
        fine_action = None
        coarse_from_adjoint = None
        coarse_action = None
        coarse_difference = None
        zero_q = None
        zero_rhs = None
        zero_solution = None
        try:
            _fill_algebraic(q1, coarse_slaves, 1.0)
            _fill_algebraic(q2, coarse_slaves, 4.0)
            q1_before = np.asarray(q1.getArray(readonly=True)).copy()
            p_q1 = owner.apply_primal(q1)
            p_q2 = owner.apply_primal(q2)
            p_q1_repeat = owner.apply_primal(q1)
            np.testing.assert_array_equal(q1.getArray(readonly=True), q1_before)
            np.testing.assert_allclose(
                p_q1.getArray(readonly=True),
                p_q1_repeat.getArray(readonly=True),
                atol=1.0e-12,
                rtol=1.0e-12,
            )
            assert not np.allclose(
                p_q1.getArray(readonly=True), p_q2.getArray(readonly=True)
            )

            fine_action = p_q1.duplicate()
            p6.action.mult(None, p_q1, fine_action)
            coarse_from_adjoint = owner.apply_adjoint(fine_action)
            coarse_action = p4.physical_action.matrix.createVecRight()
            p4.physical_action.matrix.mult(q1, coarse_action)
            coarse_difference = coarse_action.duplicate()
            coarse_action.copy(coarse_difference)
            coarse_difference.axpy(
                PETSc.ScalarType(-1.0),
                coarse_from_adjoint,
            )
            assert (
                coarse_difference.norm() / max(coarse_action.norm(), 1.0e-30)
                <= _STRICT_TOLERANCE
            )

            solution_snapshots = []
            for q in (q1, q2, q1):
                rhs = p4.create_rhs(q)
                solution = p4.matrix.createVecRight()
                try:
                    solve_audit = p4.solve_with_refinement(rhs, solution)
                    assert np.isfinite(solve_audit["relative_residual"])
                    assert solve_audit["relative_residual"] <= _STRICT_TOLERANCE
                    assert solve_audit["backsolve_count"] <= 3
                    assert solve_audit["refinement_count"] <= 2
                    assert solve_audit["same_factor_refinement"] == (
                        solve_audit["backsolve_count"] > 1
                    )
                    snapshot = np.asarray(
                        solution.getArray(readonly=True),
                        dtype=np.complex128,
                    ).copy()
                    if len(solution_snapshots) == 2:
                        np.testing.assert_allclose(
                            snapshot,
                            solution_snapshots[0],
                            atol=_STRICT_TOLERANCE,
                            rtol=_STRICT_TOLERANCE,
                        )
                    solution_snapshots.append(snapshot)
                finally:
                    solution.destroy()
                    rhs.destroy()

            zero_q = q1.duplicate()
            zero_q.set(0.0)
            zero_before = np.asarray(zero_q.getArray(readonly=True)).copy()
            zero_rhs = p4.create_rhs(zero_q)
            zero_solution = p4.matrix.createVecRight()
            zero_audit = p4.solve_with_refinement(zero_rhs, zero_solution)
            assert zero_audit["rhs_norm"] == 0.0
            assert zero_audit["residual_norm"] <= _STRICT_TOLERANCE
            assert zero_audit["relative_residual"] <= _STRICT_TOLERANCE
            np.testing.assert_array_equal(
                zero_q.getArray(readonly=True),
                zero_before,
            )
        finally:
            for vector in (p_q1, p_q2, p_q1_repeat):
                if vector is not None:
                    vector.destroy()
            if fine_action is not None:
                fine_action.destroy()
            if coarse_from_adjoint is not None:
                coarse_from_adjoint.destroy()
            if coarse_action is not None:
                coarse_action.destroy()
            if coarse_difference is not None:
                coarse_difference.destroy()
            if zero_q is not None:
                zero_q.destroy()
            if zero_rhs is not None:
                zero_rhs.destroy()
            if zero_solution is not None:
                zero_solution.destroy()
            q1.destroy()
            q2.destroy()

        diagnostics = p4.diagnostics
        assert diagnostics["factor_creation_count"] == 1
        assert diagnostics["research_factor"]["direct_factor_count"] == 1
        assert diagnostics["research_factor"]["solve_count"] >= 4


@pytest.fixture(scope="module")
def h1e_real_side_systems():
    """Build only the borrowed tiny-FE side systems for ownership coverage."""

    comm = MPI.COMM_WORLD
    cfg = _fixture_config(6, condensed=True)
    meshes = {}
    systems = {}
    try:
        for side in ("bottom", "top"):
            meshes[side] = build_hybrid_local_mesh(
                cfg,
                side,
                bottom_interface_z_nm=0.5,
                top_interface_z_nm=0.5,
                comm=comm,
            )
            systems[side] = assemble_hybrid_local_dtn_action_system(
                cfg,
                side,
                local_mesh_override=meshes[side],
                comm=comm,
            )
        yield systems
    finally:
        for system in systems.values():
            system.destroy()


def test_task041_h1e_real_fe_side_inverse_is_sequential_and_owned(
    h1e_real_side_systems,
) -> None:
    """Check real tiny-FE ownership without constructing the old oracle factors."""

    baseline: dict[str, dict[str, object]] = {}
    live_inverse_count = 0
    try:
        # Capture both borrowed operators before either adapter is constructed.
        for side_index, side in enumerate(("bottom", "top")):
            operator = h1e_real_side_systems[side].A
            original_b = h1e_real_side_systems[side].b
            source = operator.createVecRight()
            rhs = operator.createVecLeft()
            _fill_active(source, 1.0 + float(side_index))
            operator.mult(source, rhs)
            assert source.norm() > 0.0
            assert rhs.norm() > 0.0
            baseline[side] = {
                "operator": operator,
                "b": original_b,
                "source": source,
                "rhs": rhs,
                "b_values": np.asarray(
                    original_b.getArray(readonly=True)
                ).copy(),
                "source_values": np.asarray(
                    source.getArray(readonly=True)
                ).copy(),
                "rhs_values": np.asarray(rhs.getArray(readonly=True)).copy(),
            }

        def assert_borrowed_objects_unchanged() -> None:
            for record in baseline.values():
                operator = record["operator"]
                original_b = record["b"]
                source = record["source"]
                rhs = record["rhs"]
                probe = operator.createVecLeft()
                try:
                    operator.mult(source, probe)
                    np.testing.assert_array_equal(
                        original_b.getArray(readonly=True), record["b_values"]
                    )
                    np.testing.assert_array_equal(
                        source.getArray(readonly=True), record["source_values"]
                    )
                    np.testing.assert_array_equal(
                        rhs.getArray(readonly=True), record["rhs_values"]
                    )
                    np.testing.assert_allclose(
                        probe.getArray(readonly=True), record["rhs_values"],
                        atol=1.0e-12,
                        rtol=1.0e-12,
                    )
                finally:
                    probe.destroy()

        assert_borrowed_objects_unchanged()

        for side in ("bottom", "top"):
            side_system = h1e_real_side_systems[side]
            operator = baseline[side]["operator"]
            rhs = baseline[side]["rhs"]
            zero_rhs = operator.createVecRight()
            zero_output = operator.createVecLeft()
            nonzero_output = operator.createVecLeft()
            inverse = None
            events = []

            def record_lifecycle(event, detail, event_log=events):
                event_log.append((event, dict(detail)))

            try:
                zero_rhs.set(0.0)
                zero_rhs.assemble()
                inverse = build_side_balanced_inverse(
                    side_system,
                    lifecycle_callback=record_lifecycle,
                )
                # This counter is test bookkeeping only; diagnostics are the
                # ownership authority below.
                live_inverse_count += 1
                assert live_inverse_count == 1
                diagnostics = inverse.diagnostics
                assert diagnostics["p4_factor_live"] == 1
                assert diagnostics["nested_iterative_ksp_count"] == 1
                assert diagnostics["p4_factor_created_count"] == 1
                assert diagnostics["nested_ksp_created_count"] == 1

                inverse.apply(zero_rhs, zero_output)
                assert inverse.diagnostics["last_apply"]["status"] == (
                    "ZERO_RHS_EXACT"
                )
                assert zero_output.norm() == 0.0

                inverse.apply(rhs, nonzero_output)
                nonzero_audit = inverse.diagnostics["last_apply"]
                assert nonzero_audit["status"] == "KSP_CONVERGED"
                assert nonzero_audit["reason"] > 0
                assert nonzero_audit["explicit_true_target_reached"] is True
                assert np.isfinite(nonzero_audit["residual_norm"])
                assert np.isfinite(nonzero_audit["relative_residual"])
                assert nonzero_audit["relative_residual"] <= 1.0e-2
                event_names = [event for event, _detail in events]
                for expected in (
                    "full_action_begin",
                    "full_action_ready",
                    "p4_form_assembly_begin",
                    "p4_factor_ready",
                    "transfer_ready",
                    "h6_diagonal_ready",
                    "h6_window_ready",
                    "h6_runtime_ready",
                    "adapter_ksp_ready",
                ):
                    assert expected in event_names
                assert all(
                    detail["scope"] == "side_local"
                    for _event, detail in events
                )
            finally:
                if inverse is not None:
                    inverse.destroy()
                    live_inverse_count -= 1
                    assert live_inverse_count == 0
                    released = inverse.diagnostics
                    assert released["destroyed"] is True
                    assert released["p4_factor_live"] == 0
                    assert released["nested_iterative_ksp_count"] == 0
                    assert released["p4_factor_destroy_count"] == 1
                    assert released["nested_ksp_destroy_count"] == 1
                zero_output.destroy()
                nonzero_output.destroy()
                zero_rhs.destroy()

            # This is deliberately before the top adapter is built, so a
            # bottom cleanup that damages the borrowed top system is visible.
            if side == "bottom":
                assert_borrowed_objects_unchanged()

        assert_borrowed_objects_unchanged()
    finally:
        for record in baseline.values():
            record["rhs"].destroy()
            record["source"].destroy()


@pytest.fixture(scope="module")
def h1e_one_side_real_system():
    """Build one borrowed side so the p4 layout is reused exactly once."""

    comm = MPI.COMM_WORLD
    cfg = _fixture_config(6, condensed=True)
    mesh = build_hybrid_local_mesh(
        cfg,
        "bottom",
        bottom_interface_z_nm=0.5,
        top_interface_z_nm=0.5,
        comm=comm,
    )
    system = assemble_hybrid_local_dtn_action_system(
        cfg,
        "bottom",
        local_mesh_override=mesh,
        comm=comm,
    )
    try:
        yield system
    finally:
        system.destroy()


def test_task041_h1e_condensed_p4_matches_full_gp_response(
    h1e_one_side_real_system,
) -> None:
    """Compare one physical layout through full and condensed p4 factors."""

    comm = MPI.COMM_WORLD
    side_system = h1e_one_side_real_system
    physical = None
    full_matrix = None
    full_factor = None
    condensed: P4CondensedExactFactor | None = None
    fe_rhs = None
    augmented_rhs = None
    full_solution = None
    full_residual = None
    full_reference = None
    condensed_solution = None
    condensed_augmented = None
    condensed_residual = None
    rhs_b = None
    solution_b = None
    solution_a_repeat = None
    near_rhs = None
    near_solution = None
    zero_rhs = None
    zero_solution = None
    combo_rhs = None
    combo_solution = None
    expected_combo = None
    comparison = None
    repeat = None
    linearity = None
    oracle_rhs = None
    try:
        physical = _build_matching_p4_action(side_system)
        full_matrix = _assemble_augmented_matrix(physical)
        full_factor = ResearchExactFactorInverse(
            full_matrix,
            factor_solver_type="mumps",
            factor_only_storage=True,
        )
        fe_rhs = physical.action.context.input_vector.duplicate()
        fe_rhs.set(PETSc.ScalarType(0.0))
        _fill_algebraic(
            fe_rhs,
            physical.action.context.owned_slaves,
            1.7,
        )
        fe_before = np.asarray(fe_rhs.getArray(readonly=True)).copy()
        port_rhs = np.asarray(
            [
                (0.25 + 0.13j) * (index + 1)
                for index in range(len(physical.action.modes))
            ],
            dtype=np.complex128,
        )
        augmented_rhs = _augmented_vec_from_base(
            fe_rhs,
            len(port_rhs),
            comm,
        )
        if comm.rank == comm.size - 1:
            start, end = map(int, augmented_rhs.getOwnershipRange())
            port_start = physical.full_rows
            local_ports = np.arange(
                port_start,
                port_start + len(port_rhs),
                dtype=PETSc.IntType,
            )
            assert start <= port_start and end >= port_start + len(port_rhs)
            augmented_rhs.setValues(
                local_ports,
                port_rhs,
                addv=PETSc.InsertMode.ADD_VALUES,
            )
        augmented_rhs.assemble()
        full_solution = full_matrix.createVecRight()
        full_factor.solve(augmented_rhs, full_solution)
        full_residual = augmented_rhs.duplicate()
        full_matrix.mult(full_solution, full_residual)
        full_residual.axpy(PETSc.ScalarType(-1.0), augmented_rhs)
        full_relative = full_residual.norm() / augmented_rhs.norm()
        assert np.isfinite(full_relative)
        assert full_relative <= _STRICT_TOLERANCE
        full_reference = _extract_fe_segment(full_solution, physical.full_rows)
        if comm.rank == comm.size - 1:
            start, end = map(int, full_solution.getOwnershipRange())
            offset = physical.full_rows - start
            assert 0 <= offset <= end - start
            port_reference = np.asarray(
                full_solution.getArray(readonly=True)[
                    offset : offset + len(port_rhs)
                ],
                dtype=np.complex128,
            ).copy()
            assert len(port_reference) == len(port_rhs)
        else:
            port_reference = None
        port_reference = np.asarray(
            comm.bcast(port_reference, root=comm.size - 1),
            dtype=np.complex128,
        )
        full_factor.destroy()
        full_factor = None
        augmented_rhs.destroy()
        augmented_rhs = None
        full_solution.destroy()
        full_solution = None

        condensed = build_p4_condensed_exact_factor_from_action(
            physical,
            owns_physical_action=False,
        )
        same_physical_v_mpc_local = (
            condensed.physical_action is physical
            and condensed.physical_action.V is physical.V
            and condensed.physical_action.floquet_data.mpc
            is physical.floquet_data.mpc
        )
        same_physical_v_mpc = bool(
            all(comm.allgather(same_physical_v_mpc_local))
        )
        assert same_physical_v_mpc
        condensed_solution, port_solution = condensed.solve(
            fe_rhs,
            port_rhs=port_rhs,
        )
        comparison = condensed_solution.duplicate()
        condensed_solution.copy(comparison)
        comparison.axpy(PETSc.ScalarType(-1.0), full_reference)
        comparison_relative = comparison.norm() / full_reference.norm()
        assert np.isfinite(comparison_relative)
        assert comparison_relative <= 1.0e-11
        port_difference = np.linalg.norm(port_solution - port_reference)
        port_relative = port_difference / np.linalg.norm(port_reference)
        assert np.isfinite(port_relative)
        assert port_relative <= 1.0e-11
        condensed_augmented = _augmented_vec_from_base(
            condensed_solution,
            len(port_solution),
            comm,
        )
        if comm.rank == comm.size - 1:
            start, end = map(int, condensed_augmented.getOwnershipRange())
            offset = physical.full_rows - start
            condensed_augmented.setValues(
                np.arange(
                    physical.full_rows,
                    physical.full_rows + len(port_solution),
                    dtype=PETSc.IntType,
                ),
                port_solution,
                addv=PETSc.InsertMode.ADD_VALUES,
            )
            assert offset >= 0 and end >= physical.full_rows + len(port_solution)
        condensed_augmented.assemble()
        condensed_residual = condensed_augmented.duplicate()
        full_matrix.mult(condensed_augmented, condensed_residual)
        oracle_rhs = _augmented_vec_from_base(fe_rhs, len(port_rhs), comm)
        if comm.rank == comm.size - 1:
            oracle_rhs.setValues(
                np.arange(
                    physical.full_rows,
                    physical.full_rows + len(port_rhs),
                    dtype=PETSc.IntType,
                ),
                port_rhs,
                addv=PETSc.InsertMode.ADD_VALUES,
            )
        oracle_rhs.assemble()
        condensed_residual.axpy(PETSc.ScalarType(-1.0), oracle_rhs)
        condensed_residual_norm = condensed_residual.norm()
        oracle_rhs_norm = float(oracle_rhs.norm())
        condensed_residual_relative = condensed_residual_norm / oracle_rhs_norm
        assert condensed_residual_relative <= 1.0e-11
        audit = dict(condensed.diagnostics["last_solve"])
        assert audit["status"] == "passed"
        assert audit["relative_residual"] <= _STRICT_TOLERANCE
        assert audit["physical_relative_residual"] <= _STRICT_TOLERANCE
        assert audit["backsolve_count"] <= 3
        assert audit["refinement_count"] <= 2
        case_audits = {"normal": audit}
        np.testing.assert_array_equal(
            fe_rhs.getArray(readonly=True),
            fe_before,
        )

        zero_rhs = fe_rhs.duplicate()
        zero_rhs.set(PETSc.ScalarType(0.0))
        zero_rhs.assemble()
        zero_count_before = condensed.inverse.solve_count
        zero_solution, zero_ports = condensed.solve(
            zero_rhs,
            port_rhs=np.zeros_like(port_rhs),
        )
        zero_count_after = condensed.inverse.solve_count
        assert zero_solution.norm() == 0.0
        assert np.array_equal(zero_ports, np.zeros_like(port_rhs))
        assert zero_count_after == zero_count_before
        zero_audit = dict(condensed.diagnostics["last_solve"])
        assert zero_audit["physical_relative_residual"] == 0.0
        case_audits["zero"] = zero_audit

        near_rhs = fe_rhs.duplicate()
        fe_rhs.copy(near_rhs)
        near_rhs.scale(PETSc.ScalarType(1.0e-14))
        near_rhs.assemble()
        near_solution, near_ports = condensed.solve(
            near_rhs,
            port_rhs=port_rhs * 1.0e-14,
        )
        near_rhs_norm = float(near_rhs.norm())
        assert near_solution.norm() > 0.0
        near_audit = dict(condensed.diagnostics["last_solve"])
        assert near_audit["status"] == "passed"
        assert near_audit["backsolve_count"] <= 3
        assert near_audit["refinement_count"] <= 2
        assert np.linalg.norm(near_ports) > 0.0
        case_audits["nearzero"] = near_audit

        rhs_b = fe_rhs.duplicate()
        _fill_algebraic(
            rhs_b,
            physical.action.context.owned_slaves,
            2.3,
        )
        gp_b = port_rhs * (-0.17 + 0.21j)
        solution_b, ports_b = condensed.solve(rhs_b, port_rhs=gp_b)
        b_audit = dict(condensed.diagnostics["last_solve"])
        assert b_audit["backsolve_count"] <= 3
        assert b_audit["refinement_count"] <= 2
        case_audits["B"] = b_audit
        solution_a_repeat, ports_a_repeat = condensed.solve(
            fe_rhs,
            port_rhs=port_rhs,
        )
        repeat_audit = dict(condensed.diagnostics["last_solve"])
        assert repeat_audit["backsolve_count"] <= 3
        assert repeat_audit["refinement_count"] <= 2
        case_audits["A_repeat"] = repeat_audit
        repeat = solution_a_repeat.duplicate()
        solution_a_repeat.copy(repeat)
        repeat.axpy(PETSc.ScalarType(-1.0), condensed_solution)
        repeat_norm = float(repeat.norm())
        condensed_solution_norm = float(condensed_solution.norm())
        repeat_relative = repeat_norm / condensed_solution_norm
        assert repeat_relative <= 1.0e-11
        assert (
            np.linalg.norm(ports_a_repeat - port_solution)
            / np.linalg.norm(port_solution)
            <= 1.0e-11
        )

        alpha = 0.37 + 0.19j
        beta = -0.23 + 0.11j
        combo_rhs = fe_rhs.duplicate()
        fe_rhs.copy(combo_rhs)
        combo_rhs.scale(PETSc.ScalarType(alpha))
        combo_rhs.axpy(PETSc.ScalarType(beta), rhs_b)
        combo_rhs.assemble()
        combo_solution, combo_ports = condensed.solve(
            combo_rhs,
            port_rhs=alpha * port_rhs + beta * gp_b,
        )
        linearity_audit = dict(condensed.diagnostics["last_solve"])
        assert linearity_audit["backsolve_count"] <= 3
        assert linearity_audit["refinement_count"] <= 2
        case_audits["alpha_A_plus_beta_B"] = linearity_audit
        expected_combo = condensed_solution.duplicate()
        condensed_solution.copy(expected_combo)
        expected_combo.scale(PETSc.ScalarType(alpha))
        expected_combo.axpy(PETSc.ScalarType(beta), solution_b)
        linearity = combo_solution.duplicate()
        combo_solution.copy(linearity)
        linearity.axpy(PETSc.ScalarType(-1.0), expected_combo)
        linearity_norm = float(linearity.norm())
        expected_combo_norm = float(expected_combo.norm())
        linearity_relative = linearity_norm / expected_combo_norm
        assert linearity_relative <= 1.0e-11
        expected_ports = alpha * port_solution + beta * ports_b
        assert (
            linearity_relative
            <= 1.0e-11
        )
        port_linearity_relative = (
            np.linalg.norm(combo_ports - expected_ports)
            / np.linalg.norm(expected_ports)
        )
        assert port_linearity_relative <= 1.0e-11
        assert condensed.inverse.solve_count >= 5
        if comm.rank == 0:
            print(
                json.dumps(
                    {
                        "schema": "task041.h1e.p4_condensed_real_fixture.v1",
                        "mpi_size": comm.size,
                        "full_rows": physical.full_rows,
                        "active_trace_rows": condensed.condensed.active_rows,
                        "interior_rows": condensed.condensed.interior_rows,
                        "port_rows": condensed.condensed.appended_rows,
                        "same_physical_v_mpc": same_physical_v_mpc,
                        "factor_order": "old_full_released_before_new_condensed",
                        "fe_response_relative": float(comparison_relative),
                        "port_response_relative": float(port_relative),
                        "independent_full_residual_relative": float(full_relative),
                        "independent_condensed_residual_relative": float(
                            condensed_residual_relative
                        ),
                        "native_a4_relative": float(
                            audit["physical_relative_residual"]
                        ),
                        "native_a4_tolerance": 1.0e-10,
                        "repeat_relative": float(repeat_relative),
                        "complex_linearity_relative": float(linearity_relative),
                        "complex_port_linearity_relative": float(
                            port_linearity_relative
                        ),
                        "nearzero_rhs_norm": near_rhs_norm,
                        "zero_factor_solve_delta": int(
                            zero_count_after - zero_count_before
                        ),
                        "case_audits": {
                            name: {
                                "status": str(case["status"]),
                                "rhs_norm": float(case["physical_rhs_norm"]),
                                "physical_relative": float(
                                    case["physical_relative_residual"]
                                ),
                                "augmented_relative": float(
                                    case["relative_residual"]
                                ),
                                "backsolve_count": int(case["backsolve_count"]),
                                "refinement_count": int(case["refinement_count"]),
                            }
                            for name, case in case_audits.items()
                        },
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
    finally:
        if condensed is not None:
            condensed.destroy()
        if physical is not None:
            physical.destroy()
        if full_factor is not None:
            full_factor.destroy()
        if full_matrix is not None:
            full_matrix.destroy()
        if full_reference is not None:
            full_reference.destroy()
        if condensed_solution is not None:
            condensed_solution.destroy()
        if full_residual is not None:
            full_residual.destroy()
        if full_solution is not None:
            full_solution.destroy()
        if augmented_rhs is not None:
            augmented_rhs.destroy()
        if fe_rhs is not None:
            fe_rhs.destroy()
        for vector in (
            condensed_augmented,
            condensed_residual,
            rhs_b,
            solution_b,
            solution_a_repeat,
            near_rhs,
            near_solution,
            zero_rhs,
            zero_solution,
            combo_rhs,
            combo_solution,
            expected_combo,
            comparison,
            repeat,
            linearity,
            oracle_rhs,
        ):
            if vector is not None:
                vector.destroy()


def test_task041_h1e_side_inverse_old_new_q_pc_same_side(
    h1e_one_side_real_system,
) -> None:
    """Compare full and cell-condensed BAL_H Q/PC on one borrowed p6 side."""

    side_system = h1e_one_side_real_system
    operator = side_system.A
    source = operator.createVecRight()
    full_source = None
    old_inverse = None
    new_inverse = None
    old_q = None
    old_pc = None
    new_q = None
    new_pc = None
    side_a_before = operator.createVecLeft()
    side_b_before = np.asarray(
        side_system.b.getArray(readonly=True),
        dtype=np.complex128,
    ).copy()
    active_before = None
    full_before = None
    old_p4_audit = None
    old_pc_p4_audit = None
    new_p4_audit = None
    new_pc_p4_audit = None

    def relative_difference(left: PETSc.Vec, right: PETSc.Vec) -> float:
        difference = left.duplicate()
        try:
            left.copy(difference)
            difference.axpy(PETSc.ScalarType(-1.0), right)
            denominator = float(right.norm())
            numerator = float(difference.norm())
            return numerator / denominator if denominator else numerator
        finally:
            difference.destroy()

    def assert_borrowed_side_unchanged() -> None:
        np.testing.assert_array_equal(
            source.getArray(readonly=True),
            active_before,
        )
        np.testing.assert_array_equal(
            full_source.getArray(readonly=True),
            full_before,
        )
        np.testing.assert_array_equal(
            side_system.b.getArray(readonly=True),
            side_b_before,
        )
        side_a_probe = operator.createVecLeft()
        try:
            operator.mult(source, side_a_probe)
            np.testing.assert_array_equal(
                side_a_probe.getArray(readonly=True),
                side_a_before.getArray(readonly=True),
            )
        finally:
            side_a_probe.destroy()

    def p4_audit_values(adapter) -> dict[str, float]:
        last_solve = adapter.diagnostics["p4_factor"]["last_solve"]
        a4_relative = float(last_solve["physical_relative_residual"])
        backsolves = int(last_solve["backsolve_count"])
        assert np.isfinite(a4_relative)
        assert a4_relative <= 1.0e-10
        assert 1 <= backsolves <= 3
        return {
            "a4_relative": a4_relative,
            "backsolve_count": float(backsolves),
        }

    try:
        _fill_active(source, 1.25)
        active_before = np.asarray(
            source.getArray(readonly=True),
            dtype=np.complex128,
        ).copy()
        operator.mult(source, side_a_before)
        old_inverse = build_side_balanced_inverse(
            side_system,
            detailed_timing=True,
        )
        assert old_inverse._side_system is side_system
        full_source = old_inverse._full_action.matrix.createVecRight()
        assert full_source.getSize() == old_inverse._full_action.matrix.getSize()[1]
        inject_active_residual_to_full_p6(
            side_system.static_condensation.condensed,
            source,
            full_source,
        )
        full_before = np.asarray(
            full_source.getArray(readonly=True),
            dtype=np.complex128,
        ).copy()
        old_q = old_inverse._apply_q_callback(full_source)
        old_p4_audit = p4_audit_values(old_inverse)
        old_pc = operator.createVecLeft()
        old_inverse._apply_balanced_pc(source, old_pc)
        old_pc_p4_audit = p4_audit_values(old_inverse)
        assert_borrowed_side_unchanged()
        old_inverse.destroy()
        released = old_inverse.diagnostics
        assert released["destroyed"] is True
        assert released["p4_factor_live"] == 0
        assert released["nested_iterative_ksp_count"] == 0
        assert_borrowed_side_unchanged()
        old_inverse = None

        new_inverse = build_side_balanced_inverse(
            side_system,
            detailed_timing=True,
            p4_inverse_backend="cell_condensed",
        )
        assert new_inverse._side_system is side_system
        assert new_inverse.diagnostics["p4_inverse_backend"] == (
            "cell_condensed"
        )
        new_full_matrix = new_inverse._full_action.matrix
        assert new_full_matrix.getSize()[1] == full_source.getSize()
        assert tuple(new_full_matrix.getOwnershipRange()) == tuple(
            full_source.getOwnershipRange()
        )
        new_q = new_inverse._apply_q_callback(full_source)
        new_p4_audit = p4_audit_values(new_inverse)
        new_pc = operator.createVecLeft()
        new_inverse._apply_balanced_pc(source, new_pc)
        new_pc_p4_audit = p4_audit_values(new_inverse)
        assert_borrowed_side_unchanged()
        new_inverse.destroy()
        released = new_inverse.diagnostics
        assert released["destroyed"] is True
        assert released["p4_factor_live"] == 0
        assert released["nested_iterative_ksp_count"] == 0
        assert_borrowed_side_unchanged()
        new_inverse = None

        q_difference = relative_difference(new_q, old_q)
        pc_difference = relative_difference(new_pc, old_pc)
        assert np.isfinite(q_difference)
        assert np.isfinite(pc_difference)
        assert q_difference <= 1.0e-11
        assert pc_difference <= 1.0e-8
        if MPI.COMM_WORLD.rank == 0:
            print(
                json.dumps(
                    {
                        "schema": "task041.h1e.side_inverse_backend_compare.v1",
                        "mpi_size": MPI.COMM_WORLD.size,
                        "same_p6_side": True,
                        "old_backend": "full",
                        "new_backend": "cell_condensed",
                        "q_relative": float(q_difference),
                        "pc_relative": float(pc_difference),
                        "old_p4_a4_relative": old_p4_audit["a4_relative"],
                        "old_p4_backsolve_count": int(
                            old_p4_audit["backsolve_count"]
                        ),
                        "old_pc_p4_a4_relative": old_pc_p4_audit["a4_relative"],
                        "old_pc_p4_backsolve_count": int(
                            old_pc_p4_audit["backsolve_count"]
                        ),
                        "new_p4_a4_relative": new_p4_audit["a4_relative"],
                        "new_p4_backsolve_count": int(
                            new_p4_audit["backsolve_count"]
                        ),
                        "new_pc_p4_a4_relative": new_pc_p4_audit["a4_relative"],
                        "new_pc_p4_backsolve_count": int(
                            new_pc_p4_audit["backsolve_count"]
                        ),
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
    finally:
        for vector in (new_q, new_pc, old_q, old_pc, source):
            if vector is not None:
                vector.destroy()
        if full_source is not None:
            full_source.destroy()
        side_a_before.destroy()
        if new_inverse is not None:
            new_inverse.destroy()
        if old_inverse is not None:
            old_inverse.destroy()


def test_task041_h1c_j_jh_inverse_and_nonzero_particular(h1c_fixture) -> None:
    data = h1c_fixture
    oracle_audits: list[dict[str, object]] = []
    side_audits: list[dict[str, object]] = []
    for side in ("bottom", "top"):
        p6 = data["p6"][side]
        original = data["condensed"][side]
        condensed = original.static_condensation.condensed
        full_oracle = data["full_oracle"][side]
        condensed_oracle = data["condensed_oracle"][side]
        full_factor = data["full_factors"][side]
        condensed_factor = data["condensed_factors"][side]
        active_rhs = condensed.create_active_vector()
        full_rhs = p6.action.context.input_vector.duplicate()
        source = None
        active_from_full = None
        probe = None
        j_probe = None
        full_aug_rhs = None
        full_aug_solution = None
        full_solution = None
        full_residual = None
        condensed_aug_rhs = None
        condensed_aug_solution = None
        active_solution = None
        condensed_residual = None
        difference = None
        projected = None
        particular_rhs = None
        reconstructed = None
        particular_output = None
        try:
            _fill_active(active_rhs, 2.0)
            assert active_rhs.norm() > 0.0
            source = active_rhs.duplicate()
            active_rhs.copy(source)
            active_before = np.asarray(source.getArray(readonly=True)).copy()
            inject_active_residual_to_full_p6(condensed, active_rhs, full_rhs)
            active_from_full = extract_full_p6_to_active_trace(condensed, full_rhs)
            np.testing.assert_array_equal(
                active_rhs.getArray(readonly=True),
                active_before,
            )
            np.testing.assert_allclose(
                active_from_full.getArray(readonly=True),
                active_rhs.getArray(readonly=True),
                atol=0.0,
                rtol=0.0,
            )

            probe = p6.action.context.input_vector.duplicate()
            _fill_algebraic(probe, p6.action.context.owned_slaves, 3.0)
            j_probe = extract_full_p6_to_active_trace(condensed, probe)
            lhs = j_probe.dot(active_rhs)
            rhs_dot = probe.dot(full_rhs)
            assert (
                abs(lhs - rhs_dot) / max(abs(lhs), abs(rhs_dot), 1.0e-30)
                <= _STRICT_TOLERANCE
            )

            full_aug_rhs = _augmented_vec_from_base(
                full_rhs,
                len(full_oracle.external_modes),
                condensed.comm,
            )
            full_aug_rhs.assemble()
            full_aug_solution, full_oracle_audit = _explicit_factor_solve(
                full_factor,
                full_oracle.A,
                full_aug_rhs,
                full_oracle.n_fe,
                label=f"{side}.full_augmented",
            )
            oracle_audits.append(full_oracle_audit)
            full_solution = _extract_fe_segment(full_aug_solution, full_oracle.n_fe)
            full_residual = p6.matrix.createVecLeft()
            p6.matrix.mult(full_solution, full_residual)
            full_residual.axpy(PETSc.ScalarType(-1.0), full_rhs)
            full_physical_gate = _raw_residual_gate(
                full_residual,
                full_rhs,
                tolerance=_P6_TOLERANCE,
            )
            full_physical_relative = full_physical_gate["relative_residual"]
            projected = extract_full_p6_to_active_trace(condensed, full_solution)

            condensed_aug_rhs = _augmented_vec_from_base(
                active_rhs,
                len(condensed_oracle.external_modes),
                condensed.comm,
            )
            condensed_aug_rhs.assemble()
            condensed_aug_solution, condensed_oracle_audit = _explicit_factor_solve(
                condensed_factor,
                condensed_oracle.A,
                condensed_aug_rhs,
                condensed_oracle.n_fe,
                label=f"{side}.condensed_augmented",
            )
            oracle_audits.append(condensed_oracle_audit)
            active_solution = _extract_fe_segment(
                condensed_aug_solution,
                condensed_oracle.n_fe,
            )
            condensed_residual = original.A.createVecLeft()
            original.A.mult(active_solution, condensed_residual)
            condensed_residual.axpy(PETSc.ScalarType(-1.0), active_rhs)
            condensed_physical_gate = _raw_residual_gate(
                condensed_residual,
                active_rhs,
                tolerance=_P6_TOLERANCE,
            )
            condensed_physical_relative = condensed_physical_gate["relative_residual"]
            difference = projected.duplicate()
            projected.copy(difference)
            difference.axpy(PETSc.ScalarType(-1.0), active_solution)
            bridge_norm = float(difference.norm())
            bridge_solution_norm = float(active_solution.norm())
            bridge_relative = bridge_norm / max(bridge_solution_norm, 1.0e-30)
            bridge_finite = bool(
                np.isfinite(bridge_norm) and np.isfinite(bridge_solution_norm)
                and np.isfinite(bridge_relative)
            )
            bridge_passed = bool(
                bridge_finite and bridge_relative <= _STRICT_TOLERANCE
            )
            if MPI.COMM_WORLD.rank == 0:
                print(
                "H1c bridge pre-particular "
                f"{side}: full_relative={full_physical_relative}, "
                f"condensed_relative={condensed_physical_relative}, "
                f"bridge_relative={bridge_relative:.16e}, "
                f"full_gate={_P6_TOLERANCE:.1e}, "
                f"condensed_gate={_P6_TOLERANCE:.1e}, "
                f"bridge_gate={_STRICT_TOLERANCE:.1e}",
                    flush=True,
                )

            particular_rhs = full_rhs.duplicate()
            particular_rhs.set(0.0)
            first, _last = (int(value) for value in particular_rhs.getOwnershipRange())
            local = particular_rhs.getArray()
            for cell in condensed.cell_recovery_maps:
                rows = np.asarray(cell.interior_original_dofs, dtype=np.int64)
                if len(rows):
                    local[rows - first] = 1.0 + 0.25j
            particular_rhs.assemble()
            recovered = recover_owned_cell_interiors(
                condensed,
                np.zeros(condensed.active_rows, dtype=np.complex128),
                full_rhs=particular_rhs,
            )
            reconstructed = full_rhs.duplicate()
            reconstructed.set(0.0)
            for rows, values in recovered:
                petsc_rows = np.asarray(rows, dtype=PETSc.IntType)
                reconstructed.setValues(
                    petsc_rows,
                    np.asarray(values, dtype=PETSc.ScalarType),
                    addv=PETSc.InsertMode.INSERT_VALUES,
                )
            reconstructed.assemble()
            particular_output = p6.matrix.createVecLeft()
            p6.matrix.mult(reconstructed, particular_output)
            local_sq = 0.0
            for cell in condensed.cell_recovery_maps:
                rows = np.asarray(cell.interior_original_dofs, dtype=np.int64)
                if len(rows):
                    petsc_rows = np.asarray(rows, dtype=PETSc.IntType)
                    error = np.asarray(
                        particular_output.getValues(petsc_rows)
                        - particular_rhs.getValues(petsc_rows),
                        dtype=np.complex128,
                    )
                    local_sq += float(np.vdot(error, error).real)
            residual_norm = float(
                np.sqrt(condensed.comm.allreduce(local_sq, op=MPI.SUM))
            )
            rhs_norm = float(particular_rhs.norm())
            particular_relative = (
                residual_norm / rhs_norm if rhs_norm > 0.0 else None
            )
            particular_finite = bool(
                np.isfinite(residual_norm) and np.isfinite(rhs_norm)
                and (particular_relative is None or np.isfinite(particular_relative))
            )
            particular_passed = bool(
                particular_finite and rhs_norm > 0.0
                and particular_relative <= _STRICT_TOLERANCE
            )
            np.testing.assert_array_equal(
                active_rhs.getArray(readonly=True),
                active_before,
            )
            side_audits.append(
                {
                    "side": side,
                    "full_physical_relative": full_physical_relative,
                    "full_physical_tolerance": full_physical_gate["tolerance"],
                    "full_physical_finite": full_physical_gate["finite"],
                    "full_physical_passed": full_physical_gate["passed"],
                    "condensed_physical_relative": condensed_physical_relative,
                    "condensed_physical_tolerance": condensed_physical_gate[
                        "tolerance"
                    ],
                    "condensed_physical_finite": condensed_physical_gate["finite"],
                    "condensed_physical_passed": condensed_physical_gate["passed"],
                    "bridge_solution_relative": float(bridge_relative),
                    "bridge_solution_tolerance": _STRICT_TOLERANCE,
                    "bridge_solution_finite": bridge_finite,
                    "bridge_solution_passed": bridge_passed,
                    "particular_interior_relative": particular_relative,
                    "particular_interior_tolerance": _STRICT_TOLERANCE,
                    "particular_interior_finite": particular_finite,
                    "particular_interior_passed": particular_passed,
                    "particular_rhs_norm": rhs_norm,
                }
            )
        finally:
            if active_from_full is not None:
                active_from_full.destroy()
            if source is not None:
                source.destroy()
            if probe is not None:
                probe.destroy()
            if j_probe is not None:
                j_probe.destroy()
            if full_aug_rhs is not None:
                full_aug_rhs.destroy()
            if full_aug_solution is not None:
                full_aug_solution.destroy()
            if active_solution is not None:
                active_solution.destroy()
            if full_solution is not None:
                full_solution.destroy()
            if full_residual is not None:
                full_residual.destroy()
            if condensed_aug_rhs is not None:
                condensed_aug_rhs.destroy()
            if condensed_aug_solution is not None:
                condensed_aug_solution.destroy()
            if condensed_residual is not None:
                condensed_residual.destroy()
            if difference is not None:
                difference.destroy()
            if projected is not None:
                projected.destroy()
            if particular_rhs is not None:
                particular_rhs.destroy()
            if reconstructed is not None:
                reconstructed.destroy()
            if particular_output is not None:
                particular_output.destroy()
            active_rhs.destroy()
            full_rhs.destroy()

    if MPI.COMM_WORLD.rank == 0:
        for audit in side_audits:
            print(
                "H1c physical "
                f"{audit['side']}: full_relative={audit['full_physical_relative']}, "
                f"full_gate={audit['full_physical_tolerance']:.1e}, "
                f"full_finite={audit['full_physical_finite']}, "
                f"full_pass={audit['full_physical_passed']}, "
                f"condensed_relative={audit['condensed_physical_relative']}, "
                f"condensed_gate={audit['condensed_physical_tolerance']:.1e}, "
                f"condensed_finite={audit['condensed_physical_finite']}, "
                f"condensed_pass={audit['condensed_physical_passed']}, "
                f"bridge_relative={audit['bridge_solution_relative']:.16e}, "
                f"bridge_gate={audit['bridge_solution_tolerance']:.1e}, "
                f"bridge_finite={audit['bridge_solution_finite']}, "
                f"bridge_pass={audit['bridge_solution_passed']}, "
                f"particular_relative={audit['particular_interior_relative']}, "
                f"particular_gate={audit['particular_interior_tolerance']:.1e}, "
                f"particular_finite={audit['particular_interior_finite']}, "
                f"particular_pass={audit['particular_interior_passed']}, "
                f"particular_rhs_norm={audit['particular_rhs_norm']:.16e}",
                flush=True,
            )
    failed_gates = [
        f"{audit['label']}.{audit['tolerance']:.1e}"
        for audit in oracle_audits
        if not bool(audit["gate_passed"])
    ]
    for audit in side_audits:
            for name in (
            "full_physical",
            "condensed_physical",
            "bridge_solution",
            "particular_interior",
            ):
                if not bool(audit[f"{name}_finite"]):
                    failed_gates.append(f"{audit['side']}.{name}.finite")
                if not bool(audit[f"{name}_passed"]):
                    tolerance = audit[f"{name}_tolerance"]
                    failed_gates.append(
                        f"{audit['side']}.{name}.{float(tolerance):.1e}"
                    )
    assert not failed_gates, (
        "H1c residual/bridge gate failed: " + ", ".join(failed_gates)
    )
