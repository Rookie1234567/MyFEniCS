from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

from benchmarks.run_task032_phase6_augmented import (
    _parse_args,
    _v2_not_run_validation_boundary,
)
from src.solvers.hybrid_fem_modal_augmented_direct import HybridAugmentedLayout
from src.solvers.hybrid_fem_modal_block_ldu import (
    action_block_screen_gate,
    create_action_block_ldu_preconditioner,
    screen_action_block_ldu,
)
from src.solvers.hybrid_fem_modal_iterative import (
    create_hybrid_assembled_block_action,
)


def _matrix_from_dense(
    row_template: PETSc.Vec,
    column_template: PETSc.Vec,
    dense: np.ndarray,
) -> PETSc.Mat:
    dense = np.asarray(dense, dtype=np.complex128)
    matrix = PETSc.Mat().createAIJ(
        size=(
            (row_template.getLocalSize(), dense.shape[0]),
            (column_template.getLocalSize(), dense.shape[1]),
        ),
        comm=row_template.getComm(),
    )
    first, last = (int(value) for value in row_template.getOwnershipRange())
    for row in range(first, last):
        for column, value in enumerate(dense[row]):
            if value != 0.0:
                matrix.setValue(row, column, PETSc.ScalarType(value))
    matrix.assemble()
    return matrix


class _DenseFixedAction:
    def __init__(self, operator: PETSc.Mat, inverse_diagonal: np.ndarray) -> None:
        self.operator = operator
        self.inverse_diagonal = np.asarray(inverse_diagonal, dtype=np.complex128)
        self.apply_count = 0
        self.destroyed = False

    @property
    def diagnostics(self) -> dict[str, object]:
        return {
            "operator_identity": "tiny_fixed_action",
            "direct_factor_count": 0,
            "ilu_factor_count": 1 if not self.destroyed else 0,
            "factor_count": 1 if not self.destroyed else 0,
            "apply_count": self.apply_count,
            "destroyed": self.destroyed,
        }

    def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        if self.destroyed:
            raise RuntimeError("The tiny action was destroyed.")
        source.copy(target)
        first, last = (int(value) for value in source.getOwnershipRange())
        target.getArray()[:] *= self.inverse_diagonal[first:last]
        self.apply_count += 1

    def destroy(self) -> None:
        self.destroyed = True


def _tiny_fixture() -> dict[str, object]:
    comm = MPI.COMM_WORLD
    active_template = PETSc.Vec().createMPI((None, 4), comm=comm)
    modal_template = PETSc.Vec().createMPI(
        (2 if comm.rank == comm.size - 1 else 0, 2), comm=comm
    )
    diagonal = np.asarray(
        [2.0 + 0.1j, 2.4 - 0.2j, 2.8 + 0.15j, 3.1 - 0.05j],
        dtype=np.complex128,
    )
    inverse = 1.0 / diagonal
    bottom_a = _matrix_from_dense(active_template, active_template, np.diag(diagonal))
    top_a = _matrix_from_dense(active_template, active_template, np.diag(diagonal))
    bottom_positive = np.asarray(
        [[0.20, 0.01], [0.02, 0.25], [0.03, 0.00], [0.00, 0.04]],
        dtype=np.complex128,
    )
    bottom_negative = np.asarray(
        [[0.05, 0.00], [0.00, 0.06], [0.11, 0.01], [0.00, 0.09]],
        dtype=np.complex128,
    )
    top_positive = np.asarray(
        [[0.07, 0.00], [0.00, 0.08], [0.18, 0.02], [0.01, 0.21]],
        dtype=np.complex128,
    )
    top_negative = np.asarray(
        [[0.04, 0.01], [0.00, 0.03], [0.06, 0.00], [0.02, 0.10]],
        dtype=np.complex128,
    )
    bottom_projection = np.asarray(
        [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]],
        dtype=np.complex128,
    )
    top_projection = np.asarray(
        [[0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]],
        dtype=np.complex128,
    )
    matrices = {
        "bottom_positive": _matrix_from_dense(
            active_template, modal_template, bottom_positive
        ),
        "bottom_negative": _matrix_from_dense(
            active_template, modal_template, bottom_negative
        ),
        "top_positive": _matrix_from_dense(
            active_template, modal_template, top_positive
        ),
        "top_negative": _matrix_from_dense(
            active_template, modal_template, top_negative
        ),
        "bottom_projection": _matrix_from_dense(
            modal_template, active_template, bottom_projection
        ),
        "top_projection": _matrix_from_dense(
            modal_template, active_template, top_projection
        ),
    }
    active_template.destroy()
    modal_template.destroy()
    block_bottom = SimpleNamespace(
        projection=matrices["bottom_projection"],
        positive_traction=matrices["bottom_positive"],
        negative_traction=matrices["bottom_negative"],
        positive_interior_correction=np.zeros((2, 2), dtype=np.complex128),
        negative_interior_correction=np.zeros((2, 2), dtype=np.complex128),
        modal_rhs_correction=np.zeros(2, dtype=np.complex128),
    )
    block_top = SimpleNamespace(
        projection=matrices["top_projection"],
        positive_traction=matrices["top_positive"],
        negative_traction=matrices["top_negative"],
        positive_interior_correction=np.zeros((2, 2), dtype=np.complex128),
        negative_interior_correction=np.zeros((2, 2), dtype=np.complex128),
        modal_rhs_correction=np.zeros(2, dtype=np.complex128),
    )
    propagation = SimpleNamespace(
        forward=SimpleNamespace(factors=(0.8 + 0.1j, 1.1 - 0.05j)),
        backward=SimpleNamespace(factors=(0.7 - 0.1j, 0.9 + 0.04j)),
    )
    coupling = SimpleNamespace(
        mode_count_per_direction=2,
        internal_unknown_count=4,
        negative_trace_to_positive=np.eye(2, dtype=np.complex128),
        propagation=propagation,
        bottom=block_bottom,
        top=block_top,
    )
    bottom_b = bottom_a.createVecRight()
    top_b = top_a.createVecRight()
    bottom_b.set(0.0)
    top_b.set(0.0)
    bottom = SimpleNamespace(
        side="bottom",
        A=bottom_a,
        b=bottom_b,
        global_size=4,
        local_mesh=SimpleNamespace(mesh=SimpleNamespace(comm=comm)),
        inventory={"global_A_materialized": False},
    )
    top = SimpleNamespace(
        side="top",
        A=top_a,
        b=top_b,
        global_size=4,
        local_mesh=SimpleNamespace(mesh=SimpleNamespace(comm=comm)),
        inventory={"global_A_materialized": False},
    )
    layout = HybridAugmentedLayout.build(bottom, top, 4)
    return {
        "coupling": coupling,
        "bottom": bottom,
        "top": top,
        "layout": layout,
        "inverse": inverse,
    }


def _destroy_fixture(fixture: dict[str, object]) -> None:
    coupling = fixture["coupling"]
    for matrix in (
        coupling.bottom.projection,
        coupling.bottom.positive_traction,
        coupling.bottom.negative_traction,
        coupling.top.projection,
        coupling.top.positive_traction,
        coupling.top.negative_traction,
    ):
        matrix.destroy()
    fixture["bottom"].b.destroy()
    fixture["top"].b.destroy()
    fixture["bottom"].A.destroy()
    fixture["top"].A.destroy()


def _history(iterations: tuple[int, ...], residuals: tuple[float, ...]):
    return [
        {
            "iteration": iteration,
            "reported_relative_residual": residual,
            "global_true_relative_residual": residual,
            "bottom_true_relative_residual": residual,
            "top_true_relative_residual": residual,
            "modal_true_relative_residual": residual,
            "elapsed_seconds": float(iteration),
        }
        for iteration, residual in zip(iterations, residuals)
    ]


def _v2_parser_args(profile: str = "bottom-approx", max_it: int = 20) -> list[str]:
    return [
        "--task037b-v2-gate",
        "--task037b-v2-profile",
        profile,
        "--task037b-v2-max-it",
        str(max_it),
        "--degree",
        "6",
        "--h-nm",
        "10",
        "--modal-degree",
        "6",
        "--modal-h-nm",
        "10",
        "--requested-modes",
        "120",
        "--candidate-modes",
        "240",
        "--solver-path",
        "block-ldu-action-screen",
        "--stage4-full3d-assembly-backend",
        "assembly_time_static_condensed",
        "--bottom-interface-nm",
        "10",
        "--top-interface-nm",
        "110",
        "--incident-grazing-deg",
        "10",
        "--polarization-kind",
        "s",
        "--internal-propagation-model",
        "full3d_uniform_cg",
        "--internal-traction-model",
        "scalar_cg_discrete_derivative",
        "--full3d-reference",
        "/tmp/v2-full3d-reference.json",
        "--full3d-reference-sha256",
        "0" * 64,
        "--task035c-p6-preflight-authority",
        "/tmp/v2-preflight-authority.json",
        "--task035c-p6-preflight-sha256",
        "1" * 64,
        "--verified-clean-sha",
        "2" * 40,
        "--host-environment-id",
        "WSL2-Ubuntu-24.04",
    ]


def test_v2_parser_opt_in_scope_and_defaults():
    ordinary = _parse_args([])
    assert ordinary.solver_path == "augmented"
    assert ordinary.task037b_v2_gate is False
    assert ordinary.task037b_v2_profile is None
    assert ordinary.task037b_v2_max_it is None
    for profile, max_it in (
        ("bottom-approx", 20),
        ("top-approx", 20),
        ("double", 20),
        ("double", 100),
        ("double", 200),
    ):
        parsed = _parse_args(_v2_parser_args(profile, max_it))
        assert parsed.task037b_v2_gate is True
        assert parsed.task037b_v2_profile == profile
        assert parsed.task037b_v2_max_it == max_it
        assert parsed.solver_path == "block-ldu-action-screen"

    with pytest.raises(SystemExit):
        _parse_args(["--solver-path", "block-ldu-action-screen"])
    with pytest.raises(SystemExit):
        _parse_args(["--task037b-v2-profile", "bottom-approx"])
    with pytest.raises(SystemExit):
        _parse_args(["--task037b-v2-gate", "--solver-path", "block-ldu-action-screen"])
    profile_only = _v2_parser_args("bottom-approx", 20)
    max_index = profile_only.index("--task037b-v2-max-it")
    del profile_only[max_index : max_index + 2]
    with pytest.raises(SystemExit):
        _parse_args(profile_only)
    max_only = _v2_parser_args("bottom-approx", 20)
    profile_index = max_only.index("--task037b-v2-profile")
    del max_only[profile_index : profile_index + 2]
    with pytest.raises(SystemExit):
        _parse_args(max_only)
    with pytest.raises(SystemExit):
        _parse_args(_v2_parser_args("bottom-approx", 100))
    with pytest.raises(SystemExit):
        drifted = _v2_parser_args("bottom-approx", 20)
        drifted[drifted.index("--h-nm") + 1] = "9"
        _parse_args(drifted)
    with pytest.raises(SystemExit):
        _parse_args(_v2_parser_args("double", 20) + ["--task037b-v1-gate"])


def test_v2_validation_boundary_is_not_official():
    validation = _v2_not_run_validation_boundary()
    assert validation["official_record"] is False
    for key in (
        "R",
        "T",
        "A",
        "A_volume",
        "orders",
        "field",
        "12_plus_12",
        "Full3D",
    ):
        assert validation[key] == "not_run"


def test_action_block_screen_true_residual_and_lifecycle():
    if MPI.COMM_WORLD.size not in (1, 2):
        pytest.skip("The bounded screen fixture is defined for MPI1/2.")
    fixture = _tiny_fixture()
    bottom = _DenseFixedAction(fixture["bottom"].A, fixture["inverse"])
    top = _DenseFixedAction(fixture["top"].A, fixture["inverse"])
    modal = np.asarray([0.3 + 0.1j, -0.2 + 0.4j, 0.5 - 0.2j, -0.1 + 0.3j])
    source_bottom = fixture["bottom"].A.createVecRight()
    source_top = fixture["top"].A.createVecRight()
    source_bottom.set(0.0)
    source_top.set(0.0)
    first, last = (int(value) for value in source_bottom.getOwnershipRange())
    source_bottom.getArray()[:] = np.asarray(
        [1.0 + 0.1j, -0.5 + 0.2j, 0.8 - 0.3j, 0.2 + 0.4j][first:last],
        dtype=PETSc.ScalarType,
    )
    first, last = (int(value) for value in source_top.getOwnershipRange())
    source_top.getArray()[:] = np.asarray(
        [-0.4 + 0.2j, 0.7 - 0.1j, 1.2 + 0.3j, -0.3 - 0.2j][first:last],
        dtype=PETSc.ScalarType,
    )
    action_matrix = None
    action_context = None
    preconditioner = None
    rhs = None
    try:
        preconditioner = create_action_block_ldu_preconditioner(
            fixture["layout"],
            fixture["bottom"],
            fixture["top"],
            fixture["coupling"],
            bottom,
            top,
        )
        action_matrix, action_context = create_hybrid_assembled_block_action(
            fixture["bottom"], fixture["top"], fixture["coupling"]
        )
        rhs = fixture["layout"].pack(source_bottom, source_top, modal)
        build_bottom_apply_count = bottom.apply_count
        build_top_apply_count = top.apply_count
        result = screen_action_block_ldu(
            action_matrix,
            rhs,
            preconditioner,
            max_it=20,
        )
        preconditioner = None
        assert result.iterations <= 20
        assert result.history[0]["iteration"] == 0
        assert result.history[-1]["iteration"] == result.iterations
        assert result.final_true_relative_residual <= 1.0e-10
        assert (
            result.minimum_true_relative_residual <= result.final_true_relative_residual
        )
        assert all(
            np.isfinite(row["global_true_relative_residual"]) for row in result.history
        )
        assert all("bottom_action_apply_count" in row for row in result.history)
        assert all("top_action_apply_count" in row for row in result.history)
        pc_apply_count = result.inventory["pc_apply_count"]
        assert pc_apply_count > 0
        assert (
            result.inventory["bottom_action_apply_count"] - build_bottom_apply_count
            == 2 * pc_apply_count
        )
        assert (
            result.inventory["top_action_apply_count"] - build_top_apply_count
            == 2 * pc_apply_count
        )
        assert result.inventory["pc_apply_seconds"] >= 0.0
        assert result.inventory["modal_schur"]["modal_schur_bytes"] > 0
        assert bottom.destroyed is False
        assert top.destroyed is False
        assert action_context._destroyed is False
        gate = action_block_screen_gate(
            _history((0, 1), (1.0, 0.1)),
            profile="bottom-approx",
            max_it=20,
            converged_reason=1,
        )
        assert gate["pass"] is True
        gate = action_block_screen_gate(
            _history((0, 40), (1.0, 0.1)),
            profile="double",
            max_it=100,
            converged_reason=1,
        )
        assert gate["pass"] is True
        gate = action_block_screen_gate(
            _history((0, 40), (1.0, 0.04)),
            profile="double",
            max_it=200,
            converged_reason=1,
        )
        assert gate["pass"] is True
        assert gate["prediction_target"] == 1.0e-6
        assert gate["predicted_iterations"] is not None
        assert gate["predicted_iterations"] <= 3000
        assert (
            action_block_screen_gate(
                _history((0, 1), (1.0, 0.35)),
                profile="bottom-approx",
                max_it=20,
                converged_reason=1,
            )["pass"]
            is False
        )
        assert (
            action_block_screen_gate(
                _history((0, 1), (1.0, 0.1)),
                profile="bottom-approx",
                max_it=20,
                converged_reason=-3,
            )["pass"]
            is False
        )
        assert (
            action_block_screen_gate(
                _history((0, 1), (1.0, 0.1)),
                profile="bottom-approx",
                max_it=20,
                converged_reason=1,
            )["pass"]
            is True
        )
    finally:
        if preconditioner is not None:
            preconditioner.destroy()
        if rhs is not None:
            rhs.destroy()
        if action_matrix is not None:
            action_matrix.destroy()
        if action_context is not None:
            action_context.destroy()
        source_top.destroy()
        source_bottom.destroy()
        bottom.destroy()
        top.destroy()
        _destroy_fixture(fixture)
