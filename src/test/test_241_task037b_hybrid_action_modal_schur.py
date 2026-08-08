from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

from src.solvers.hybrid_fem_modal_augmented_direct import (
    HybridAugmentedLayout,
    internal_modal_constraint_matrix,
)
from src.solvers.hybrid_fem_modal_block_ldu import (
    HybridBlockLduDirectAction,
    create_action_block_ldu_preconditioner,
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


def _relative_array_error(actual: np.ndarray, expected: np.ndarray) -> float:
    return float(
        np.linalg.norm(np.asarray(actual) - np.asarray(expected))
        / max(float(np.linalg.norm(expected)), 1.0e-30)
    )


def _gather_vector(vector: PETSc.Vec) -> np.ndarray:
    local = np.asarray(vector.getArray(readonly=True), dtype=np.complex128).copy()
    return np.concatenate(vector.getComm().tompi4py().allgather(local))


class _DenseFactor:
    def __init__(self, inverse_diagonal: np.ndarray) -> None:
        self.inverse_diagonal = np.asarray(inverse_diagonal, dtype=np.complex128)
        self.destroyed = False
        self.solve_count = 0

    def solve(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        if self.destroyed:
            raise RuntimeError("The tiny direct factor was destroyed.")
        source.copy(target)
        first, last = (int(value) for value in source.getOwnershipRange())
        target.getArray()[:] *= self.inverse_diagonal[first:last]
        self.solve_count += 1

    def destroy(self) -> None:
        self.destroyed = True


class _DenseFixedAction:
    def __init__(
        self,
        operator: PETSc.Mat,
        inverse_diagonal: np.ndarray,
    ) -> None:
        self.operator = operator
        self.inverse_diagonal = np.asarray(inverse_diagonal, dtype=np.complex128)
        self.apply_count = 0
        self.destroyed = False

    @property
    def diagnostics(self) -> dict[str, object]:
        return {
            "operator_identity": "tiny_fixed_ilu_action",
            "direct_factor_count": 0,
            "ilu_factor_count": 1 if not self.destroyed else 0,
            "factor_count": 1 if not self.destroyed else 0,
            "apply_count": self.apply_count,
            "destroyed": self.destroyed,
        }

    def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        if self.destroyed:
            raise RuntimeError("The tiny fixed action was destroyed.")
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
    inverse_diagonal = 1.0 / diagonal
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
    zero = np.zeros((2, 2), dtype=np.complex128)
    block_bottom = SimpleNamespace(
        projection=matrices["bottom_projection"],
        positive_traction=matrices["bottom_positive"],
        negative_traction=matrices["bottom_negative"],
        positive_interior_correction=zero.copy(),
        negative_interior_correction=zero.copy(),
        modal_rhs_correction=np.zeros(2, dtype=np.complex128),
    )
    block_top = SimpleNamespace(
        projection=matrices["top_projection"],
        positive_traction=matrices["top_positive"],
        negative_traction=matrices["top_negative"],
        positive_interior_correction=zero.copy(),
        negative_interior_correction=zero.copy(),
        modal_rhs_correction=np.zeros(2, dtype=np.complex128),
    )
    propagation = SimpleNamespace(
        forward=SimpleNamespace(
            factors=(0.8 + 0.1j, 1.1 - 0.05j),
        ),
        backward=SimpleNamespace(
            factors=(0.7 - 0.1j, 0.9 + 0.04j),
        ),
    )
    coupling = SimpleNamespace(
        mode_count_per_direction=2,
        negative_trace_to_positive=np.eye(2, dtype=np.complex128),
        propagation=propagation,
        bottom=block_bottom,
        top=block_top,
    )
    bottom_b = bottom_a.createVecRight()
    top_b = top_a.createVecRight()
    bottom_b.set(0.0)
    top_b.set(0.0)
    bottom_system = SimpleNamespace(
        side="bottom",
        A=bottom_a,
        b=bottom_b,
        global_size=4,
        local_mesh=SimpleNamespace(mesh=SimpleNamespace(comm=comm)),
    )
    top_system = SimpleNamespace(
        side="top",
        A=top_a,
        b=top_b,
        global_size=4,
        local_mesh=SimpleNamespace(mesh=SimpleNamespace(comm=comm)),
    )
    layout = HybridAugmentedLayout.build(bottom_system, top_system, 4)
    return {
        "comm": comm,
        "coupling": coupling,
        "bottom": bottom_system,
        "top": top_system,
        "layout": layout,
        "diagonal": diagonal,
        "inverse_diagonal": inverse_diagonal,
        "dense_blocks": {
            "bottom_positive": bottom_positive,
            "bottom_negative": bottom_negative,
            "top_positive": top_positive,
            "top_negative": top_negative,
            "bottom_projection": bottom_projection,
            "top_projection": top_projection,
        },
    }


def _destroy_fixture(fixture: dict[str, object]) -> None:
    coupling = fixture["coupling"]
    coupling.bottom.projection.destroy()
    coupling.bottom.positive_traction.destroy()
    coupling.bottom.negative_traction.destroy()
    coupling.top.projection.destroy()
    coupling.top.positive_traction.destroy()
    coupling.top.negative_traction.destroy()
    fixture["bottom"].b.destroy()
    fixture["top"].b.destroy()
    fixture["bottom"].A.destroy()
    fixture["top"].A.destroy()


def _actions_for_profile(fixture: dict[str, object], profile: str):
    bottom_operator = fixture["bottom"].A
    top_operator = fixture["top"].A
    inverse_diagonal = fixture["inverse_diagonal"]
    bottom = _DenseFixedAction(bottom_operator, inverse_diagonal)
    top = _DenseFixedAction(top_operator, inverse_diagonal)
    if profile in {"B", "double"}:
        if profile == "B":
            top = HybridBlockLduDirectAction(
                top_operator,
                _DenseFactor(inverse_diagonal),
                {"factor_nnz": 4},
            )
    if profile == "T":
        bottom = HybridBlockLduDirectAction(
            bottom_operator,
            _DenseFactor(inverse_diagonal),
            {"factor_nnz": 4},
        )
    return bottom, top


def _expected_modal_matrix(fixture: dict[str, object]) -> np.ndarray:
    coupling = fixture["coupling"]
    blocks = fixture["dense_blocks"]
    inverse = np.diag(fixture["inverse_diagonal"])
    count = 2
    expected = internal_modal_constraint_matrix(coupling)
    bottom = np.zeros_like(expected)
    top = np.zeros_like(expected)
    for column in range(2 * count):
        modal = np.zeros(2 * count, dtype=np.complex128)
        modal[column] = 1.0
        bottom_traction = blocks["bottom_positive"] @ modal[:count]
        bottom_traction += blocks["bottom_negative"] @ (
            np.asarray(coupling.propagation.backward.factors) * modal[count:]
        )
        top_traction = blocks["top_positive"] @ (
            np.asarray(coupling.propagation.forward.factors) * modal[:count]
        )
        top_traction += blocks["top_negative"] @ modal[count:]
        bottom[:count, column] = blocks["bottom_projection"] @ (
            inverse @ bottom_traction
        )
        top[count:, column] = blocks["top_projection"] @ (inverse @ top_traction)
    return expected - bottom - top


def _destroy_actions(bottom, top) -> None:
    bottom.destroy()
    top.destroy()


def test_action_modal_schur_profiles_and_borrowed_lifecycle():
    if MPI.COMM_WORLD.size not in (1, 2, 4):
        pytest.skip("The focused V2 action test is defined for MPI1/2/4.")
    expected_side = {
        "B": ((0, 1), (1, 0)),
        "T": ((1, 0), (0, 1)),
        "double": ((0, 1), (0, 1)),
    }
    for profile in ("B", "T", "double"):
        fixture = _tiny_fixture()
        bottom, top = _actions_for_profile(fixture, profile)
        context = None
        try:
            expected = _expected_modal_matrix(fixture)
            context = create_action_block_ldu_preconditioner(
                fixture["layout"],
                fixture["bottom"],
                fixture["top"],
                fixture["coupling"],
                bottom,
                top,
            )
            modal_system = context.action_modal_schur_system
            diagnostics = modal_system.diagnostics
            assert _relative_array_error(modal_system.modal_schur, expected) <= 1e-13
            assert diagnostics["shape"] == [4, 4]
            assert diagnostics["rank"] == 4
            assert np.isfinite(diagnostics["condition"])
            assert diagnostics["condition"] <= 1e12
            assert diagnostics["finite"] is True
            assert diagnostics["matrix_repeat_error"] <= 1e-13
            assert diagnostics["lu_repeat_solve_error"] <= 1e-13
            assert diagnostics["build_apply_count"] == {"bottom": 8, "top": 8}
            inventory = context.inventory
            expected_bottom, expected_top = expected_side[profile]
            assert inventory["bottom_direct_factor_count"] == expected_bottom[0]
            assert inventory["bottom_ilu_factor_count"] == expected_bottom[1]
            assert inventory["top_direct_factor_count"] == expected_top[0]
            assert inventory["top_ilu_factor_count"] == expected_top[1]
            expected_direct = expected_bottom[0] + expected_top[0]
            expected_ilu = expected_bottom[1] + expected_top[1]
            assert inventory["direct_factor_count"] == expected_direct
            assert inventory["oracle_local_direct_factor_count"] == expected_direct
            assert inventory["borrowed_direct_factor_count"] == expected_direct
            assert inventory["borrowed_ilu_factor_count"] == expected_ilu
            assert inventory["borrowed_local_factor_count"] == 2
            assert inventory["pc_owned_local_factor_count"] == 0
            assert inventory["borrowed_side_actions"] is True
            assert context.direct_factor_count == expected_direct
        finally:
            if context is not None:
                context.destroy()
                assert context.inventory["modal_schur"]["destroyed"] is True
                assert context.factors_released is False
                assert context.modal_schur is None
                dead_source = fixture["layout"].create_vector()
                dead_target = fixture["layout"].create_vector()
                with pytest.raises(RuntimeError):
                    context.apply(None, dead_source, dead_target)
                dead_target.destroy()
                dead_source.destroy()
                with pytest.raises(RuntimeError):
                    modal_system.solve(np.ones(4, dtype=np.complex128))
            assert bottom.diagnostics["destroyed"] is False
            assert top.diagnostics["destroyed"] is False
            for action, system in ((bottom, fixture["bottom"]), (top, fixture["top"])):
                source = system.A.createVecRight()
                target = system.A.createVecLeft()
                source.set(1.0)
                try:
                    action.apply(source, target)
                    assert np.isfinite(target.norm())
                finally:
                    target.destroy()
                    source.destroy()
            _destroy_actions(bottom, top)
            _destroy_fixture(fixture)


def test_double_action_block_apply_matches_hand_formula():
    if MPI.COMM_WORLD.size not in (1, 2, 4):
        pytest.skip("The focused V2 action test is defined for MPI1/2/4.")
    fixture = _tiny_fixture()
    bottom, top = _actions_for_profile(fixture, "double")
    context = create_action_block_ldu_preconditioner(
        fixture["layout"],
        fixture["bottom"],
        fixture["top"],
        fixture["coupling"],
        bottom,
        top,
    )
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
    modal = np.asarray([0.3 + 0.1j, -0.2 + 0.4j, 0.5 - 0.2j, -0.1 + 0.3j])
    source = fixture["layout"].pack(source_bottom, source_top, modal)
    target = fixture["layout"].create_vector()
    try:
        context.apply(None, source, target)
        assert bottom.diagnostics["apply_count"] == 10
        assert top.diagnostics["apply_count"] == 10
        assert context.inventory["pc_apply_count"] == 1
        expected_matrix = _expected_modal_matrix(fixture)
        bottom_values = _gather_vector(source_bottom)
        top_values = _gather_vector(source_top)
        inverse = np.diag(fixture["inverse_diagonal"])
        blocks = fixture["dense_blocks"]
        modal_rhs = modal.copy()
        modal_rhs[:2] -= blocks["bottom_projection"] @ (inverse @ bottom_values)
        modal_rhs[2:] -= blocks["top_projection"] @ (inverse @ top_values)
        expected_modal = np.linalg.solve(expected_matrix, modal_rhs)
        bottom_traction = blocks["bottom_positive"] @ expected_modal[:2]
        bottom_traction += blocks["bottom_negative"] @ (
            np.asarray(fixture["coupling"].propagation.backward.factors)
            * expected_modal[2:]
        )
        top_traction = blocks["top_positive"] @ (
            np.asarray(fixture["coupling"].propagation.forward.factors)
            * expected_modal[:2]
        )
        top_traction += blocks["top_negative"] @ expected_modal[2:]
        expected_bottom = inverse @ (bottom_values - bottom_traction)
        expected_top = inverse @ (top_values - top_traction)
        actual_bottom, actual_top, actual_modal = fixture["layout"].split(
            target, fixture["bottom"].b, fixture["top"].b
        )
        try:
            assert (
                _relative_array_error(_gather_vector(actual_bottom), expected_bottom)
                <= 1e-13
            )
            assert (
                _relative_array_error(_gather_vector(actual_top), expected_top) <= 1e-13
            )
            assert _relative_array_error(actual_modal, expected_modal) <= 1e-13
        finally:
            actual_modal = None
            actual_top.destroy()
            actual_bottom.destroy()
    finally:
        target.destroy()
        source.destroy()
        source_top.destroy()
        source_bottom.destroy()
        context.destroy()
        assert bottom.diagnostics["destroyed"] is False
        assert top.diagnostics["destroyed"] is False
        _destroy_actions(bottom, top)
        _destroy_fixture(fixture)
