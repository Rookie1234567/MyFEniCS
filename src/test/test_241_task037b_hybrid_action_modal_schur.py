from __future__ import annotations

import hashlib
import inspect
import json
from types import SimpleNamespace

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

import src.solvers.hybrid_fem_modal_block_ldu as block_ldu
from src.solvers.hybrid_fem_modal_augmented_direct import (
    HybridAugmentedLayout,
    build_hybrid_augmented_direct_system,
    internal_modal_constraint_matrix,
)
from src.solvers.hybrid_fem_modal_block_ldu import (
    build_hybrid_action_modal_schur,
    create_action_block_ldu_preconditioner,
    create_research_exact_side_lu_block_ldu_preconditioner,
)
from src.solvers.hybrid_local_dtn_woodbury import ResearchExactSideLuAction


class _FixedAction:
    def __init__(self, operator: PETSc.Mat, inverse_diagonal: np.ndarray) -> None:
        self.operator = operator
        self.inverse_diagonal = np.asarray(inverse_diagonal, dtype=np.complex128)
        self.apply_count = 0
        self.destroyed = False

    @property
    def diagnostics(self) -> dict[str, object]:
        return {
            "operator_identity": "test_fixed_action",
            "direct_factor_count": 0,
            "ilu_factor_count": 1 if not self.destroyed else 0,
            "factor_count": 1 if not self.destroyed else 0,
            "apply_count": self.apply_count,
            "destroyed": self.destroyed,
        }

    def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        if self.destroyed:
            raise RuntimeError("The fixed action is destroyed.")
        source.copy(target)
        first, last = (int(value) for value in source.getOwnershipRange())
        target.getArray()[:] *= self.inverse_diagonal[first:last]
        self.apply_count += 1

    def destroy(self) -> None:
        self.destroyed = True


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
    comm = vector.getComm().tompi4py()
    packets = comm.allgather(
        (
            tuple(int(value) for value in vector.getOwnershipRange()),
            np.asarray(vector.getArray(readonly=True), dtype=np.complex128).copy(),
        )
    )
    result = np.empty(int(vector.getSize()), dtype=np.complex128)
    for (first, last), values in packets:
        result[first:last] = values
    return result


def _tiny_fixture() -> dict[str, object]:
    comm = MPI.COMM_WORLD
    template = PETSc.Vec().createMPI((None, 4), comm=comm)
    modal_template = PETSc.Vec().createMPI(
        (2 if comm.rank == comm.size - 1 else 0, 2), comm=comm
    )
    diagonal = np.asarray(
        [2.0 + 0.1j, 2.4 - 0.2j, 2.8 + 0.15j, 3.1 - 0.05j],
        dtype=np.complex128,
    )
    inverse = 1.0 / diagonal
    bottom_a = _matrix_from_dense(template, template, np.diag(diagonal))
    top_a = _matrix_from_dense(template, template, np.diag(diagonal))
    blocks = {
        "bottom_positive": np.asarray(
            [[0.20, 0.01], [0.02, 0.25], [0.03, 0.00], [0.00, 0.04]],
            dtype=np.complex128,
        ),
        "bottom_negative": np.asarray(
            [[0.05, 0.00], [0.00, 0.06], [0.11, 0.01], [0.00, 0.09]],
            dtype=np.complex128,
        ),
        "top_positive": np.asarray(
            [[0.07, 0.00], [0.00, 0.08], [0.18, 0.02], [0.01, 0.21]],
            dtype=np.complex128,
        ),
        "top_negative": np.asarray(
            [[0.04, 0.01], [0.00, 0.03], [0.06, 0.00], [0.02, 0.10]],
            dtype=np.complex128,
        ),
        "bottom_projection": np.asarray(
            [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]],
            dtype=np.complex128,
        ),
        "top_projection": np.asarray(
            [[0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]],
            dtype=np.complex128,
        ),
    }
    matrices = {
        name: _matrix_from_dense(
            template if values.shape[0] == 4 else modal_template,
            modal_template if values.shape[1] == 2 else template,
            values,
        )
        for name, values in blocks.items()
    }
    template.destroy()
    modal_template.destroy()
    zero = np.zeros((2, 2), dtype=np.complex128)
    bottom_block = SimpleNamespace(
        projection=matrices["bottom_projection"],
        positive_traction=matrices["bottom_positive"],
        negative_traction=matrices["bottom_negative"],
        positive_interior_correction=zero.copy(),
        negative_interior_correction=zero.copy(),
        modal_rhs_correction=np.zeros(2, dtype=np.complex128),
    )
    top_block = SimpleNamespace(
        projection=matrices["top_projection"],
        positive_traction=matrices["top_positive"],
        negative_traction=matrices["top_negative"],
        positive_interior_correction=zero.copy(),
        negative_interior_correction=zero.copy(),
        modal_rhs_correction=np.zeros(2, dtype=np.complex128),
    )
    coupling = SimpleNamespace(
        mode_count_per_direction=2,
        internal_unknown_count=4,
        negative_trace_to_positive=np.eye(2, dtype=np.complex128),
        propagation=SimpleNamespace(
            forward=SimpleNamespace(factors=np.asarray([0.8 + 0.1j, 1.1 - 0.05j])),
            backward=SimpleNamespace(factors=np.asarray([0.7 - 0.1j, 0.9 + 0.04j])),
        ),
        bottom=bottom_block,
        top=top_block,
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
    )
    top = SimpleNamespace(
        side="top",
        A=top_a,
        b=top_b,
        global_size=4,
        local_mesh=SimpleNamespace(mesh=SimpleNamespace(comm=comm)),
    )
    layout = HybridAugmentedLayout.build(bottom, top, 4)
    return {
        "comm": comm,
        "coupling": coupling,
        "bottom": bottom,
        "top": top,
        "layout": layout,
        "diagonal": diagonal,
        "inverse": inverse,
        "blocks": blocks,
    }


def _actions(fixture: dict[str, object]) -> tuple[_FixedAction, _FixedAction]:
    inverse = fixture["inverse"]
    return (
        _FixedAction(fixture["bottom"].A, inverse),
        _FixedAction(fixture["top"].A, inverse),
    )


def _expected_modal_matrix(fixture: dict[str, object]) -> np.ndarray:
    coupling = fixture["coupling"]
    blocks = fixture["blocks"]
    inverse = np.diag(fixture["inverse"])
    expected = internal_modal_constraint_matrix(coupling)
    bottom = np.zeros_like(expected)
    top = np.zeros_like(expected)
    for column in range(4):
        modal = np.zeros(4, dtype=np.complex128)
        modal[column] = 1.0
        bottom_traction = blocks["bottom_positive"] @ modal[:2]
        bottom_traction += blocks["bottom_negative"] @ (
            coupling.propagation.backward.factors * modal[2:]
        )
        top_traction = blocks["top_positive"] @ (
            coupling.propagation.forward.factors * modal[:2]
        )
        top_traction += blocks["top_negative"] @ modal[2:]
        bottom[:2, column] = blocks["bottom_projection"] @ (inverse @ bottom_traction)
        top[2:, column] = blocks["top_projection"] @ (inverse @ top_traction)
    return expected - bottom - top


def _destroy_fixture(fixture: dict[str, object]) -> None:
    for block in (fixture["coupling"].bottom, fixture["coupling"].top):
        block.projection.destroy()
        block.positive_traction.destroy()
        block.negative_traction.destroy()
    fixture["bottom"].b.destroy()
    fixture["top"].b.destroy()
    fixture["bottom"].A.destroy()
    fixture["top"].A.destroy()


def _zero_research_components(fixture: dict[str, object], system) -> SimpleNamespace:
    row = system.A.createVecLeft()
    column = system.A.createVecRight()
    modal = fixture["coupling"].bottom.positive_traction.createVecRight()
    try:
        return SimpleNamespace(
            F=system.A,
            C=_matrix_from_dense(row, modal, np.zeros((4, 2), dtype=np.complex128)),
            D=_matrix_from_dense(modal, column, np.zeros((2, 4), dtype=np.complex128)),
            H=_matrix_from_dense(modal, modal, np.eye(2, dtype=np.complex128)),
        )
    finally:
        row.destroy()
        column.destroy()
        modal.destroy()


def test_action_modal_schur_is_repeated_and_borrowed():
    fixture = _tiny_fixture()
    bottom, top = _actions(fixture)
    try:
        expected = _expected_modal_matrix(fixture)
        first = build_hybrid_action_modal_schur(fixture["coupling"], bottom, top)
        second = build_hybrid_action_modal_schur(fixture["coupling"], bottom, top)
        assert _relative_array_error(first.modal_schur, expected) <= 1.0e-13
        assert _relative_array_error(first.modal_schur, second.modal_schur) <= 1.0e-13
        assert first.diagnostics["rank"] == 4
        assert np.isfinite(first.diagnostics["condition"])
        assert first.diagnostics["normal_equations"] is False
        assert first.diagnostics["build_apply_count"] == {"bottom": 8, "top": 8}
        assert bottom.diagnostics["apply_count"] == 16
        assert top.diagnostics["apply_count"] == 16
        first.destroy()
        second.destroy()
        assert bottom.diagnostics["destroyed"] is False
        assert top.diagnostics["destroyed"] is False
    finally:
        bottom.destroy()
        top.destroy()
        _destroy_fixture(fixture)


def test_action_modal_schur_single_build_freezes_sampled_columns_and_hash():
    fixture = _tiny_fixture()
    bottom, top = _actions(fixture)
    contract = {
        "columns": [0, 1, 2, 3],
        "mode_count_per_direction": 2,
        "roles": {
            "0": ["head", "bottom_positive_unattenuated"],
            "1": ["interior", "bottom_positive_unattenuated"],
            "2": ["head", "top_negative_unattenuated"],
            "3": ["tail", "top_negative_unattenuated"],
        },
    }
    contract_sha = hashlib.sha256(
        json.dumps(contract, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    baseline = None
    modal = None
    try:
        rhs = np.asarray([0.5 - 0.2j, -0.3 + 0.4j, 0.7 + 0.1j, -0.2 - 0.6j])
        baseline = build_hybrid_action_modal_schur(fixture["coupling"], bottom, top)
        baseline_matrix = baseline.modal_schur.copy()
        baseline_solution = baseline.solve(rhs)
        baseline.destroy()
        baseline = None
        bottom.destroy()
        top.destroy()
        bottom, top = _actions(fixture)
        modal = build_hybrid_action_modal_schur(
            fixture["coupling"],
            bottom,
            top,
            sampled_columns=contract["columns"],
            sampled_column_roles=contract["roles"],
            sampled_column_contract_sha256=contract_sha,
        )
        expected = _expected_modal_matrix(fixture)
        assert _relative_array_error(modal.modal_schur, expected) <= 1.0e-13
        assert _relative_array_error(modal.modal_schur, baseline_matrix) <= 1.0e-13
        assert _relative_array_error(modal.solve(rhs), baseline_solution) <= 1.0e-13
        diagnostics = modal.diagnostics
        sampled = diagnostics["sampled_column_diagnostics"]
        assert sampled["single_build"] is True
        assert sampled["contract_sha256"] == contract_sha
        assert sampled["full_build_apply_count"] == {"bottom": 4, "top": 4}
        assert sampled["sample_build_apply_count"] == {"bottom": 4, "top": 4}
        assert diagnostics["build_apply_count"] == {"bottom": 8, "top": 8}
        assert diagnostics["repeat_diagnostics"]["matrix"]["mode"] == (
            "single_full_build_sampled_reconstruction"
        )
        assert diagnostics["matrix_repeat_error"] <= 1.0e-13
        assert diagnostics["repeat_diagnostics"]["matrix"][
            "max_column_relative_error"
        ] <= (1.0e-13)
        with pytest.raises(ValueError, match="contract hash"):
            build_hybrid_action_modal_schur(
                fixture["coupling"],
                bottom,
                top,
                sampled_columns=contract["columns"],
                sampled_column_roles=contract["roles"],
                sampled_column_contract_sha256="0" * 64,
            )
        extra_roles = dict(contract["roles"])
        extra_roles["99"] = ["unexpected"]
        with pytest.raises(ValueError, match="roles must cover"):
            build_hybrid_action_modal_schur(
                fixture["coupling"],
                bottom,
                top,
                sampled_columns=contract["columns"],
                sampled_column_roles=extra_roles,
                sampled_column_contract_sha256=contract_sha,
            )
    finally:
        if baseline is not None:
            baseline.destroy()
        if modal is not None:
            modal.destroy()
        bottom.destroy()
        top.destroy()
        _destroy_fixture(fixture)


def test_action_modal_schur_single_build_catches_sample_perturbation(monkeypatch):
    fixture = _tiny_fixture()
    bottom, top = _actions(fixture)
    columns = [0, 1, 2, 3]
    roles = {str(column): ["sample"] for column in columns}
    contract = {
        "columns": columns,
        "mode_count_per_direction": 2,
        "roles": roles,
    }
    contract_sha = hashlib.sha256(
        json.dumps(contract, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    original = block_ldu._build_action_modal_contribution
    calls = {"count": 0}

    def perturbed(side, coupling, action, modal_count, columns=None):
        value = original(side, coupling, action, modal_count, columns=columns)
        calls["count"] += 1
        if calls["count"] == 3:
            value = value.copy()
            value[0, 0] += 5.0e-11
        return value

    monkeypatch.setattr(block_ldu, "_build_action_modal_contribution", perturbed)
    try:
        with pytest.raises(ValueError, match="max_column=.*e-11"):
            build_hybrid_action_modal_schur(
                fixture["coupling"],
                bottom,
                top,
                sampled_columns=columns,
                sampled_column_roles=roles,
                sampled_column_contract_sha256=contract_sha,
            )
    finally:
        bottom.destroy()
        top.destroy()
        _destroy_fixture(fixture)


def test_research_matrix_repeat_tolerance_does_not_change_lu_gate(monkeypatch):
    parameter = inspect.signature(build_hybrid_action_modal_schur).parameters[
        "matrix_repeat_tolerance"
    ]
    assert parameter.default == 1.0e-13

    fixture = _tiny_fixture()
    bottom, top = _actions(fixture)
    modal = None
    try:
        baseline = build_hybrid_action_modal_schur(fixture["coupling"], bottom, top)
        baseline_norm = float(np.linalg.norm(baseline.modal_schur))
        baseline.destroy()
        original = block_ldu._build_action_modal_contribution
        calls = {"count": 0}

        def perturbed(side, coupling, action, modal_count):
            value = original(side, coupling, action, modal_count)
            calls["count"] += 1
            if calls["count"] == 3:
                value = value.copy()
                value[0, 0] += 5.0e-11 * baseline_norm
            return value

        monkeypatch.setattr(block_ldu, "_build_action_modal_contribution", perturbed)
        with pytest.raises(
            ValueError,
            match=r"actual=.*limit=1\.000000e-13.*reference_norm=.*max_abs=",
        ):
            build_hybrid_action_modal_schur(fixture["coupling"], bottom, top)

        calls["count"] = 0
        modal = build_hybrid_action_modal_schur(
            fixture["coupling"],
            bottom,
            top,
            matrix_repeat_tolerance=1.0e-10,
        )
        diagnostics = modal.diagnostics["repeat_diagnostics"]
        assert diagnostics["matrix"]["relative_error"] <= 1.0e-10
        assert diagnostics["matrix"]["limit"] == 1.0e-10
        assert diagnostics["lu_solve"]["limit"] == 1.0e-13
        modal.destroy()
        modal = None

        calls["count"] = 0

        def strongly_perturbed(side, coupling, action, modal_count):
            value = original(side, coupling, action, modal_count)
            calls["count"] += 1
            if calls["count"] == 3:
                value = value.copy()
                value[0, 0] += 2.0e-10 * baseline_norm
            return value

        monkeypatch.setattr(
            block_ldu, "_build_action_modal_contribution", strongly_perturbed
        )
        with pytest.raises(
            ValueError,
            match=r"actual=.*limit=1\.000000e-10.*reference_norm=.*max_abs=",
        ):
            build_hybrid_action_modal_schur(
                fixture["coupling"],
                bottom,
                top,
                matrix_repeat_tolerance=1.0e-10,
            )
    finally:
        if modal is not None:
            modal.destroy()
        bottom.destroy()
        top.destroy()
        _destroy_fixture(fixture)


def test_research_exact_side_action_nonzero_dtn_is_linear_and_finite():
    fixture = _tiny_fixture()
    system = fixture["bottom"]
    components = _zero_research_components(fixture, system)
    row = system.A.createVecLeft()
    column = system.A.createVecRight()
    modal = fixture["coupling"].bottom.positive_traction.createVecRight()
    action = None
    source = target = repeat = scaled_source = scaled_target = None
    try:
        components.C.destroy()
        components.D.destroy()
        components.H.destroy()
        components.C = _matrix_from_dense(
            row,
            modal,
            np.asarray(
                [[0.10, 0.02], [0.03, -0.04], [0.02, 0.01], [-0.01, 0.05]],
                dtype=np.complex128,
            ),
        )
        components.D = _matrix_from_dense(
            modal,
            column,
            np.asarray(
                [[0.04, 0.01, -0.02, 0.03], [0.02, -0.03, 0.01, 0.02]],
                dtype=np.complex128,
            ),
        )
        components.H = _matrix_from_dense(
            modal,
            modal,
            np.diag([2.0 + 0.1j, 2.4 - 0.2j]),
        )
        action = ResearchExactSideLuAction(
            system.A,
            components,
            factor_solver_type=None,
        )
        source = system.A.createVecRight()
        target = system.A.createVecLeft()
        repeat = system.A.createVecLeft()
        source.set(PETSc.ScalarType(0.75 - 0.2j))
        action.apply(source, target)
        action.apply(source, repeat)
        assert (
            _relative_array_error(_gather_vector(repeat), _gather_vector(target))
            <= 1.0e-10
        )
        scaled_source = source.duplicate()
        source.copy(scaled_source)
        scaled_source.scale(PETSc.ScalarType(2.0))
        scaled_target = system.A.createVecLeft()
        action.apply(scaled_source, scaled_target)
        assert (
            _relative_array_error(
                _gather_vector(scaled_target), 2.0 * _gather_vector(target)
            )
            <= 1.0e-10
        )
        diagnostics = action.diagnostics
        assert diagnostics["direct_factor_count"] == 1
        assert diagnostics["ilu_factor_count"] == 0
        assert diagnostics["global_hybrid_direct_factor_count"] == 0
        assert diagnostics["woodbury"]["n_aux"] == 2
        assert diagnostics["woodbury"]["arrays_finite"] is True
    finally:
        if action is not None:
            action.destroy()
        for vector in (scaled_target, scaled_source, repeat, target, source):
            if vector is not None:
                vector.destroy()
        row.destroy()
        column.destroy()
        modal.destroy()
        components.C.destroy()
        components.D.destroy()
        components.H.destroy()
        _destroy_fixture(fixture)


def test_action_block_apply_is_linear_and_owns_no_side_factor():
    fixture = _tiny_fixture()
    bottom, top = _actions(fixture)
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
    target_repeat = fixture["layout"].create_vector()
    source_y = source.duplicate()
    first, last = (int(value) for value in source_y.getOwnershipRange())
    source_y.getArray()[:] = np.asarray(
        [
            0.2 - 0.1j,
            1.1 + 0.3j,
            -0.7 + 0.5j,
            0.6 - 0.4j,
            0.9 + 0.2j,
            -1.0 + 0.1j,
            0.4 - 0.6j,
            0.8 + 0.7j,
            -0.3 + 0.2j,
            0.5 - 0.8j,
            1.2 + 0.1j,
            -0.9 - 0.3j,
        ][first:last],
        dtype=PETSc.ScalarType,
    )
    target_y = fixture["layout"].create_vector()
    combined = source.duplicate()
    combined_target = fixture["layout"].create_vector()
    linear_target = fixture["layout"].create_vector()
    workspace_ids = tuple(
        id(getattr(context, name))
        for name in (
            "_bottom_coupling",
            "_top_coupling",
            "_bottom_positive_source",
            "_top_positive_source",
        )
    )
    try:
        context.apply(None, source, target)
        context.apply(None, source, target_repeat)
        assert (
            _relative_array_error(_gather_vector(target_repeat), _gather_vector(target))
            <= 1.0e-13
        )
        context.apply(None, source_y, target_y)
        alpha, beta = 0.3, -0.7
        source.copy(combined)
        combined.scale(PETSc.ScalarType(alpha))
        combined.axpy(PETSc.ScalarType(beta), source_y)
        context.apply(None, combined, combined_target)
        target.copy(linear_target)
        linear_target.scale(PETSc.ScalarType(alpha))
        linear_target.axpy(PETSc.ScalarType(beta), target_y)
        assert (
            _relative_array_error(
                _gather_vector(combined_target), _gather_vector(linear_target)
            )
            <= 1.0e-13
        )
        assert (
            tuple(
                id(getattr(context, name))
                for name in (
                    "_bottom_coupling",
                    "_top_coupling",
                    "_bottom_positive_source",
                    "_top_positive_source",
                )
            )
            == workspace_ids
        )
        assert context.inventory["pc_owned_local_factor_count"] == 0
        assert context.inventory["direct_factor_count"] == 0
        assert context.inventory["pc_apply_count"] == 4
        assert bottom.diagnostics["apply_count"] == 16
        assert top.diagnostics["apply_count"] == 16
        expected_matrix = _expected_modal_matrix(fixture)
        bottom_values = _gather_vector(source_bottom)
        top_values = _gather_vector(source_top)
        modal_rhs = modal.copy()
        modal_rhs[:2] -= fixture["blocks"]["bottom_projection"] @ (
            np.diag(fixture["inverse"]) @ bottom_values
        )
        modal_rhs[2:] -= fixture["blocks"]["top_projection"] @ (
            np.diag(fixture["inverse"]) @ top_values
        )
        expected_modal = np.linalg.solve(expected_matrix, modal_rhs)
        bottom_traction = fixture["blocks"]["bottom_positive"] @ expected_modal[:2]
        bottom_traction += fixture["blocks"]["bottom_negative"] @ (
            fixture["coupling"].propagation.backward.factors * expected_modal[2:]
        )
        top_traction = fixture["blocks"]["top_positive"] @ (
            fixture["coupling"].propagation.forward.factors * expected_modal[:2]
        )
        top_traction += fixture["blocks"]["top_negative"] @ expected_modal[2:]
        expected_bottom = np.diag(fixture["inverse"]) @ (
            bottom_values - bottom_traction
        )
        expected_top = np.diag(fixture["inverse"]) @ (top_values - top_traction)
        actual_bottom, actual_top, actual_modal = fixture["layout"].split(
            target, fixture["bottom"].b, fixture["top"].b
        )
        try:
            assert (
                _relative_array_error(_gather_vector(actual_bottom), expected_bottom)
                <= 1.0e-13
            )
            assert (
                _relative_array_error(_gather_vector(actual_top), expected_top)
                <= 1.0e-13
            )
            assert _relative_array_error(actual_modal, expected_modal) <= 1.0e-13
        finally:
            actual_modal = None
            actual_top.destroy()
            actual_bottom.destroy()
        context.defer_action_modal_schur_release = True
        context.destroy(None)
        assert context.action_modal_schur_system.diagnostics["destroyed"] is False
        context.release_deferred_action_modal_schur()
        assert context.action_modal_schur_system.diagnostics["destroyed"] is True
        assert bottom.diagnostics["destroyed"] is False
        assert top.diagnostics["destroyed"] is False
    finally:
        target.destroy()
        source.destroy()
        source_top.destroy()
        source_bottom.destroy()
        linear_target.destroy()
        combined_target.destroy()
        combined.destroy()
        target_y.destroy()
        source_y.destroy()
        target_repeat.destroy()
        if not context._destroyed:
            context.destroy()
        bottom.destroy()
        top.destroy()
        _destroy_fixture(fixture)


@pytest.mark.parametrize("qualified", [False, True], ids=["historical", "qualified"])
def test_research_exact_side_factory_keeps_direct_and_ilu_inventories_separate(
    qualified,
):
    fixture = _tiny_fixture()
    components = []
    actions = []
    context = None
    source = target = direct = None
    try:
        for system in (fixture["bottom"], fixture["top"]):
            component = _zero_research_components(fixture, system)
            components.append(component)
            actions.append(
                ResearchExactSideLuAction(
                    system.A,
                    component,
                    factor_solver_type=None,
                    qualification_scope=(
                        "task039_v3_p6h5_m480_1deg_s" if qualified else None
                    ),
                    explicit_opt_in=qualified,
                )
            )
        with pytest.raises(ValueError, match="zero borrowed direct factors"):
            create_action_block_ldu_preconditioner(
                fixture["layout"],
                fixture["bottom"],
                fixture["top"],
                fixture["coupling"],
                actions[0],
                actions[1],
            )
        context = create_research_exact_side_lu_block_ldu_preconditioner(
            fixture["layout"],
            fixture["bottom"],
            fixture["top"],
            fixture["coupling"],
            actions[0],
            actions[1],
            qualification_scope=("task039_v3_p6h5_m480_1deg_s" if qualified else None),
            explicit_opt_in=qualified,
        )
        inventory = context.inventory
        if qualified:
            assert "research_only_exact_side_lu" not in inventory
            assert inventory["qualification_scope"] == ("task039_v3_p6h5_m480_1deg_s")
            assert inventory["explicit_opt_in"] is True
            assert inventory["case_qualification_opt_in"] is True
            assert inventory["local_direct_preonly_ksp_count"] == 2
            assert inventory["nested_iterative_ksp_count"] == 0
        else:
            assert inventory["research_only_exact_side_lu"] is True
            assert "case_qualification_opt_in" not in inventory
        assert inventory["bottom_direct_factor_count"] == 1
        assert inventory["top_direct_factor_count"] == 1
        assert inventory["borrowed_ilu_factor_count"] == 0
        assert inventory["global_hybrid_direct_factor_count"] == 0
        source = fixture["layout"].create_vector()
        target = fixture["layout"].create_vector()
        fixture["coupling"].internal_equation_count = 4
        values = np.asarray(
            np.random.default_rng(285).standard_normal(fixture["layout"].global_size)
            + 1j
            * np.random.default_rng(286).standard_normal(fixture["layout"].global_size),
            dtype=np.complex128,
        )
        first, last = (int(value) for value in source.getOwnershipRange())
        source.getArray()[:] = values[first:last]
        direct = build_hybrid_augmented_direct_system(
            fixture["bottom"], fixture["top"], fixture["coupling"]
        )
        rows = np.arange(direct.A.getSize()[0], dtype=PETSc.IntType)
        expected = np.linalg.solve(
            direct.A.getValues(rows, rows), _gather_vector(source)
        )
        context.apply(None, source, target)
        assert _relative_array_error(_gather_vector(target), expected) <= 1.0e-11
    finally:
        if direct is not None:
            direct.destroy()
        if target is not None:
            target.destroy()
        if source is not None:
            source.destroy()
        if context is not None:
            context.destroy()
        for action in actions:
            action.destroy()
        for component in components:
            component.C.destroy()
            component.D.destroy()
            component.H.destroy()
        _destroy_fixture(fixture)
