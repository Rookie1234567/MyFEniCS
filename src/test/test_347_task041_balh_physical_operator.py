"""Focused Task041 H1c tests for the real physical-side operators."""

from __future__ import annotations

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
    P4ExactFactor,
    build_fullspace_physical_dtn_action,
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
