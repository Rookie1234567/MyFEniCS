"""Pure/fake coverage for opt-in coupled p4 port refinement.

These tests use tiny PETSc vectors and a controlled dense factor double.  They
do not build a mesh, assemble an FE operator, or run a PDE solve.
"""

import ast
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from petsc4py import PETSc
from scipy.linalg import lu_factor

from src.runners.physical_retained_condensed_v20 import (
    RetainedCondensedRuntime,
    persist_p4_failure_packet,
)
from src.solvers.p4_cell_condensed_inverse import (
    CellPortTerms,
    P4CellCondensedInverse,
    P4RefinementLedger,
)

_V = 2.0 + 0.3j
_B = 3.0 - 0.2j
_D = 5.0 + 0.5j
_H = 7.0 - 0.1j
_G = 1.0 + 0.2j
_C0 = 0.1 - 0.03j
_A0 = 0.2 + 0.04j
_BLOCK = np.asarray([[_V, _B], [-_D, _H]], dtype=np.complex128)
_A4 = _V + _B * _D / _H


def _vec(size: int, values=None):
    result = PETSc.Vec().createMPI((size, size), comm=PETSc.COMM_SELF)
    result.set(PETSc.ScalarType(0.0))
    if values is not None:
        payload = np.ascontiguousarray(np.asarray(values, dtype=np.complex128))
        assert payload.shape == (size,)
        result.setValues(
            np.arange(size, dtype=PETSc.IntType),
            payload.astype(PETSc.ScalarType),
            addv=PETSc.InsertMode.INSERT_VALUES,
        )
    result.assemble()
    return result


class _DenseFactor:
    symbolic_calls = 1
    numeric_calls = 1

    def __init__(self, matrix, *, first_state=None, always_first_state=False):
        self.matrix = np.asarray(matrix, dtype=np.complex128)
        self.first_state = first_state
        self.always_first_state = bool(always_first_state)
        self.solve_calls = 0

    def solve_repeated(self, rhs, solution):
        values = np.asarray(rhs.getArray(readonly=True), dtype=np.complex128).copy()
        self.last_rhs = values.copy()
        self.solve_calls += 1
        if self.first_state is not None and (
            self.always_first_state or self.solve_calls == 1
        ):
            answer = np.asarray(self.first_state, dtype=np.complex128)
        else:
            answer = np.linalg.solve(self.matrix, values)
        solution.set(PETSc.ScalarType(0.0))
        solution.setValues(
            np.arange(answer.size, dtype=PETSc.IntType),
            answer.astype(PETSc.ScalarType),
            addv=PETSc.InsertMode.INSERT_VALUES,
        )
        solution.assemble()


def _inverse(matrix=_BLOCK, *, first_state=(_C0, _A0), always_first_state=False):
    matrix = np.asarray(matrix, dtype=np.complex128)
    active_rows = matrix.shape[0] - 1
    full_rows = active_rows
    factor = _DenseFactor(
        matrix,
        first_state=first_state,
        always_first_state=always_first_state,
    )
    active_original = np.arange(active_rows, dtype=PETSc.IntType)
    system = SimpleNamespace(
        full_rows=full_rows,
        appended_rows=1,
        active_rows=active_rows,
        owned_active_rows=active_rows,
        trace_constraints=SimpleNamespace(
            owned_active_original_dofs=active_original,
        ),
        cell_recovery_maps=(),
        create_augmented_vector=lambda: _vec(matrix.shape[0]),
    )
    inverse = object.__new__(P4CellCondensedInverse)
    inverse.coarse_degree = 4
    inverse.coarse_operator = "A4"
    inverse.condensed = system
    inverse.factor = factor
    inverse.port_terms = {}
    inverse.owns_condensed = False
    inverse.owns_factor = False
    inverse.retain_through_postprocess_v18 = False
    inverse.solve_count = 0
    inverse.destroyed = False
    inverse.last_port_solution = np.zeros(1, dtype=np.complex128)
    inverse.last_audit = {}
    inverse.matrix_identity = {"csr_sha256": "tiny-fake-matrix"}
    inverse._slave_original = np.empty(0, dtype=PETSc.IntType)
    inverse._xiB_by_cell = {}
    return inverse


def _a4_action(rhs):
    def apply(solution, _port_state):
        value = complex(solution.getArray(readonly=True)[0])
        output = _vec(1, [_A4 * value])
        return output

    return apply


def _closure(solution, port_state):
    c = complex(solution.getArray(readonly=True)[0])
    a = complex(np.asarray(port_state, dtype=np.complex128)[0])
    h_term = _H * a
    d_term = _D * c
    error = np.asarray([h_term - d_term], dtype=np.complex128)
    scale = abs(h_term) + abs(d_term)
    norm = float(np.linalg.norm(error))
    relative = 0.0 if scale == 0.0 and norm == 0.0 else norm / scale
    return {
        "status": "PASS" if relative <= 1.0e-10 else "P4_NUMERICAL_UNQUALIFIED",
        "finite": bool(np.isfinite(error).all()),
        "norm": norm,
        "scale": float(scale),
        "relative_residual": float(relative),
        "formula": "H*a-D*c",
        "_closure_vector": error,
    }


class _FakeModalAction:
    def __init__(self):
        self.carrier = SimpleNamespace(
            entries=(SimpleNamespace(normalization_h=_H),)
        )
        self.seen_amplitudes = None

    def apply_modal_rhs(self, mode_amplitudes, target):
        amplitudes = np.asarray(tuple(mode_amplitudes), dtype=np.complex128)
        self.seen_amplitudes = amplitudes.copy()
        target.getArray()[:] = _B * amplitudes[0]
        target.assemble()


def _runtime_with_fake_modal_action():
    action = _FakeModalAction()
    runtime = RetainedCondensedRuntime(
        levels={},
        fine={},
        p4={"dtn_action": action},
        p6_system=None,
        p6_action=None,
        p4_system=SimpleNamespace(full_rows=1),
        p4_terms={},
        mode_count=1,
        mode_sha256="tiny-fake-mode",
    )
    return runtime, action


def test_joint_rhs_matches_actual_uneliminated_block_residual_and_rejects_sign_errors():
    r_fe = _G - _A4 * _C0
    closure_error = _H * _A0 - _D * _C0
    actual_block_residual = np.asarray(
        [
            _G - _V * _C0 - _B * _A0,
            -(-_D * _C0 + _H * _A0),
        ],
        dtype=np.complex128,
    )
    # Independent augmented-block oracle: eliminate the port from the FE row
    # only to define r_FE, then restore the exact uneliminated residual.
    expected_block_residual = np.asarray(
        [r_fe - _B / _H * closure_error, -closure_error],
        dtype=np.complex128,
    )
    np.testing.assert_allclose(
        expected_block_residual,
        actual_block_residual,
        rtol=2.0e-15,
        atol=2.0e-15,
    )

    wrong_eliminated_sign = r_fe + _B / _H * closure_error
    omitted_coupling = r_fe
    wrong_port_sign = closure_error
    assert abs(wrong_eliminated_sign - actual_block_residual[0]) > 1.0e-3
    assert abs(omitted_coupling - actual_block_residual[0]) > 1.0e-3
    assert abs(wrong_port_sign - actual_block_residual[1]) > 1.0e-3


def test_joint_ledger_uses_real_inverse_and_runtime_bh_inverse_e_callback():
    rhs = _vec(1, [_G])
    inverse = _inverse()
    runtime, modal_action = _runtime_with_fake_modal_action()
    ledger = P4RefinementLedger(
        inverse,
        _a4_action(rhs),
        port_closure=_closure,
        joint_port_refinement=True,
        port_coupling_correction=runtime.apply_port_coupling_correction,
        max_refinements=2,
    )
    solution = ledger.solve(rhs)
    try:
        expected = np.linalg.solve(_BLOCK, np.asarray([_G, 0.0j]))
        np.testing.assert_allclose(
            solution.getArray(readonly=True), [expected[0]],
            rtol=2.0e-14,
            atol=2.0e-14,
        )
        np.testing.assert_allclose(
            ledger.total_port_solution, [expected[1]],
            rtol=2.0e-14,
            atol=2.0e-14,
        )
        assert ledger.last_audit["status"] == "P4_RETURN_PASS"
        assert ledger.last_audit["joint_port_refinement"] is True
        assert ledger.last_audit["refinement_count"] == 1
        assert inverse.factor.solve_calls == 2
        assert modal_action.seen_amplitudes is not None
        assert modal_action.seen_amplitudes.shape == (1,)
        assert len(ledger.last_audit["rows"]) == 2
        assert all(
            row["port_closure"]["status"] == "PASS"
            for row in ledger.last_audit["rows"][-1:]
        )
    finally:
        solution.destroy()
        rhs.destroy()


def test_legacy_default_needs_no_closure_vector_and_keeps_scalar_early_gate():
    rhs = _vec(1, [_G])
    inverse = _inverse()
    correction_calls = []

    def scalar_only_closure(_solution, _port_state):
        return {
            "status": "PASS",
            "finite": True,
            "relative_residual": 0.0,
        }

    ledger = P4RefinementLedger(
        inverse,
        _a4_action(rhs),
        port_closure=scalar_only_closure,
        port_coupling_correction=lambda *args: correction_calls.append(args),
        max_refinements=2,
    )
    solution = ledger.solve(rhs)
    try:
        assert ledger.joint_port_refinement is False
        assert ledger.last_audit["status"] == "P4_RETURN_PASS"
        assert ledger.last_audit["refinement_count"] == 1
        assert inverse.factor.solve_calls == 2
        assert correction_calls == []
        assert "joint_port_refinement" not in ledger.last_audit
    finally:
        solution.destroy()
        rhs.destroy()


@pytest.mark.parametrize("facts", [{"status": "PASS"}, {"status": "PASS", "finite": False}])
def test_legacy_default_preserves_finite_port_closure_gate(facts):
    rhs = _vec(1, [_G])
    inverse = _inverse()
    ledger = P4RefinementLedger(
        inverse,
        _a4_action(rhs),
        port_closure=lambda _solution, _port_state: {
            "relative_residual": 0.0,
            **facts,
        },
        max_refinements=2,
    )
    try:
        with pytest.raises(FloatingPointError, match="port closure"):
            ledger.solve(rhs)
        assert inverse.factor.solve_calls == 1
        assert ledger.last_audit["rows"][0]["port_closure"]["status"] == (
            "P4_NUMERICAL_UNQUALIFIED"
        )
    finally:
        rhs.destroy()


def test_joint_mode_requires_vector_and_bounded_refinements():
    inverse = _inverse()
    with pytest.raises(ValueError, match="B H\\^-1 e"):
        P4RefinementLedger(
            inverse,
            lambda _solution, _ports: _vec(1, [0]),
            port_closure=_closure,
            joint_port_refinement=True,
        )
    with pytest.raises(ValueError, match="max_refinements"):
        P4RefinementLedger(
            inverse,
            lambda _solution, _ports: _vec(1, [0]),
            port_closure=_closure,
            joint_port_refinement=True,
            port_coupling_correction=lambda _error, _target: None,
            max_refinements=3,
        )


def test_joint_mode_missing_closure_vector_fails_before_correction():
    rhs = _vec(1, [_G])
    inverse = _inverse()
    ledger = P4RefinementLedger(
        inverse,
        _a4_action(rhs),
        port_closure=lambda _solution, _ports: {
            "status": "P4_NUMERICAL_UNQUALIFIED",
            "finite": True,
            "relative_residual": 1.0,
        },
        joint_port_refinement=True,
        port_coupling_correction=lambda _error, _target: None,
        max_refinements=2,
    )
    try:
        with pytest.raises(FloatingPointError, match="closure"):
            ledger.solve(rhs)
        assert inverse.factor.solve_calls == 1
        assert ledger.last_audit["rows"][0]["port_closure"][
            "closure_vector_available"
        ] is False
    finally:
        rhs.destroy()


def test_joint_mode_never_exceeds_two_factor_refinements():
    rhs = _vec(1, [_G])
    inverse = _inverse(always_first_state=True)
    runtime, _modal_action = _runtime_with_fake_modal_action()
    ledger = P4RefinementLedger(
        inverse,
        _a4_action(rhs),
        port_closure=_closure,
        joint_port_refinement=True,
        port_coupling_correction=runtime.apply_port_coupling_correction,
        max_refinements=2,
    )
    try:
        with pytest.raises(RuntimeError, match="qualified limit"):
            ledger.solve(rhs)
        assert inverse.factor.solve_calls == 3
        assert [row["refinement"] for row in ledger.last_audit["rows"]] == [0, 1, 2]
    finally:
        rhs.destroy()


def test_actual_inverse_reduces_nonzero_port_rhs_and_rejects_bad_rhs():
    factor = _DenseFactor(np.asarray([[_H]], dtype=np.complex128))
    active_original = np.empty(0, dtype=PETSc.IntType)
    system = SimpleNamespace(
        full_rows=1,
        appended_rows=1,
        active_rows=0,
        owned_active_rows=0,
        trace_constraints=SimpleNamespace(
            owned_active_original_dofs=active_original,
        ),
        cell_recovery_maps=(),
        create_augmented_vector=lambda: _vec(1),
    )
    inverse = object.__new__(P4CellCondensedInverse)
    inverse.coarse_degree = 4
    inverse.coarse_operator = "A4"
    inverse.condensed = system
    inverse.factor = factor
    inverse.port_terms = {}
    inverse.owns_condensed = False
    inverse.owns_factor = False
    inverse.retain_through_postprocess_v18 = False
    inverse.solve_count = 0
    inverse.destroyed = False
    inverse.last_port_solution = np.zeros(1, dtype=np.complex128)
    inverse.last_audit = {}
    inverse.matrix_identity = {"csr_sha256": "tiny-port-only"}
    inverse._slave_original = np.empty(0, dtype=PETSc.IntType)
    inverse._xiB_by_cell = {}
    rhs = _vec(1, [0.0])
    try:
        result = inverse.apply(rhs, port_rhs=np.asarray([2.0 + 0j]))
        try:
            assert factor.solve_calls == 1
            assert inverse.last_port_solution[0] == pytest.approx(2.0 / _H)
            assert inverse.last_audit["status"] == "SOLVE_COMPLETED"
        finally:
            result.destroy()
        with pytest.raises(FloatingPointError, match="non-finite"):
            inverse.apply(rhs, port_rhs=np.asarray([np.nan + 0j]))
        assert factor.solve_calls == 1
    finally:
        rhs.destroy()


def test_actual_reduce_and_apply_match_uncondensed_complex_three_block_solve():
    # Original unknown order is [one trace, one interior, one port].  The
    # production inverse receives its exact 2x2 Schur block plus the local
    # interior recovery metadata, so this covers both RHS reductions:
    # g_t - V_ti V_ii^-1 g_i and g_p + D_i V_ii^-1 g_i.
    v_tt = 4.0 + 0.2j
    v_ti = 1.0 - 0.3j
    v_it = 0.7 + 0.1j
    v_ii = 3.0 + 0.4j
    b_t = 0.4 + 0.6j
    b_i = 2.0 + 0.5j
    d_t = 0.8 - 0.1j
    d_i = 1.5 - 0.2j
    h = 5.0 + 0.2j
    g_t = 0.9 - 0.2j
    g_i = -0.3 + 0.8j
    g_p = 0.6 + 0.7j

    original = np.asarray(
        [
            [v_tt, v_ti, b_t],
            [v_it, v_ii, b_i],
            [-d_t, -d_i, h],
        ],
        dtype=np.complex128,
    )
    original_rhs = np.asarray([g_t, g_i, g_p], dtype=np.complex128)
    expected = np.linalg.solve(original, original_rhs)

    inverse_ii = 1.0 / v_ii
    schur = np.asarray(
        [
            [
                v_tt - v_ti * inverse_ii * v_it,
                b_t - v_ti * inverse_ii * b_i,
            ],
            [
                -(d_t - d_i * inverse_ii * v_it),
                h + d_i * inverse_ii * b_i,
            ],
        ],
        dtype=np.complex128,
    )
    system = SimpleNamespace(
        full_rows=2,
        appended_rows=1,
        active_rows=1,
        owned_active_rows=1,
        trace_constraints=SimpleNamespace(
            owned_active_original_dofs=np.asarray([0], dtype=PETSc.IntType),
            expansion_by_original={
                0: (
                    np.asarray([0], dtype=PETSc.IntType),
                    np.asarray([1.0 + 0j], dtype=np.complex128),
                )
            },
        ),
        cell_recovery_maps=(
            SimpleNamespace(
                interior_original_dofs=np.asarray([1], dtype=PETSc.IntType),
                trace_original_dofs=np.asarray([0], dtype=PETSc.IntType),
                class_key=("tiny-complex-cell",),
            ),
        ),
        interior_lu_by_class={
            ("tiny-complex-cell",): lu_factor(np.asarray([[v_ii]]))
        },
        trace_from_interior_rhs_by_class={
            ("tiny-complex-cell",): np.asarray([[-v_ti / v_ii]])
        },
        interior_from_trace_by_class={
            ("tiny-complex-cell",): np.asarray([[-v_it / v_ii]])
        },
        create_augmented_vector=lambda: _vec(2),
    )
    factor = _DenseFactor(schur)
    inverse = object.__new__(P4CellCondensedInverse)
    inverse.coarse_degree = 4
    inverse.coarse_operator = "A4"
    inverse.condensed = system
    inverse.factor = factor
    inverse.port_terms = {
        0: CellPortTerms(
            Bi=np.asarray([[b_i]], dtype=np.complex128),
            Di=np.asarray([[d_i]], dtype=np.complex128),
            port_indices=np.asarray([0], dtype=PETSc.IntType),
        )
    }
    inverse.owns_condensed = False
    inverse.owns_factor = False
    inverse.retain_through_postprocess_v18 = False
    inverse.solve_count = 0
    inverse.destroyed = False
    inverse.last_port_solution = np.zeros(1, dtype=np.complex128)
    inverse.last_audit = {}
    inverse.matrix_identity = {"csr_sha256": "tiny-3x3-schur"}
    inverse._slave_original = np.empty(0, dtype=PETSc.IntType)
    inverse._xiB_by_cell = {0: np.asarray([[b_i / v_ii]])}

    rhs = _vec(2, [g_t, g_i])
    try:
        result = inverse.apply(rhs, port_rhs=np.asarray([g_p]))
        try:
            expected_reduced_rhs = np.asarray(
                [g_t - v_ti * inverse_ii * g_i, g_p + d_i * inverse_ii * g_i],
                dtype=np.complex128,
            )
            np.testing.assert_allclose(
                factor.last_rhs, expected_reduced_rhs, rtol=2e-15, atol=2e-15
            )
            assert factor.last_rhs[1] != pytest.approx(g_p)
            actual = np.asarray(
                [
                    result.getArray(readonly=True)[0],
                    result.getArray(readonly=True)[1],
                    inverse.last_port_solution[0],
                ],
                dtype=np.complex128,
            )
            np.testing.assert_allclose(actual, expected, rtol=2e-14, atol=2e-14)
            assert inverse.last_audit["status"] == "SOLVE_COMPLETED"
        finally:
            result.destroy()
    finally:
        rhs.destroy()


def test_destroyed_inverse_checks_state_before_condensed_layout():
    inverse = object.__new__(P4CellCondensedInverse)
    inverse.destroyed = True
    inverse.condensed = None
    with pytest.raises(RuntimeError, match="destroyed"):
        inverse.apply(_vec(1, [1.0]))


def test_failure_packet_persists_port_closure_residual_array(tmp_path):
    records = []
    closure = np.asarray([0.25 - 0.75j], dtype=np.complex128)
    packet = {
        "status": "P4_NUMERICAL_UNQUALIFIED",
        "matrix_identity": {"csr_sha256": "tiny"},
        "factor_counts": {"logical_apply_calls": 1},
        "rows": [],
        "g": np.asarray([1.0 + 0j]),
        "c": np.asarray([0.5 + 0j]),
        "r": np.asarray([0.1 + 0j]),
        "port_state": np.asarray([0.2 + 0j]),
        "port_closure_residual": closure,
    }
    record = persist_p4_failure_packet(
        packet,
        tmp_path,
        source_sha="a" * 40,
        input_sha256="b" * 64,
        physical_model_sha256="c" * 64,
        append=lambda _name, value: records.append(value),
    )
    assert records and record["array_artifact"]["arrays"][
        "port_closure_residual"
    ]["shape"] == [1]
    loaded = np.load(tmp_path / record["array_artifact"]["filename"], allow_pickle=False)
    try:
        np.testing.assert_array_equal(loaded["port_closure_residual"], closure)
    finally:
        loaded.close()


def test_joint_port_refinement_is_v7_bound_and_legacy_default_is_off():
    legacy_runtime = RetainedCondensedRuntime(
        levels={},
        fine={},
        p4={},
        p6_system=None,
        p6_action=None,
        p4_system=None,
        p4_terms={},
        mode_count=0,
        mode_sha256="empty-fake",
    )
    assert legacy_runtime.joint_port_refinement is False

    source_path = Path(__import__(
        "src.runners.physical_retained_condensed_v20", fromlist=["__file__"]
    ).__file__)
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    runtime_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        and node.name == "RetainedCondensedRuntime"
    )
    build_method = next(
        node
        for node in runtime_class.body
        if isinstance(node, ast.FunctionDef) and node.name == "build"
    )
    attach_method = next(
        node
        for node in runtime_class.body
        if isinstance(node, ast.FunctionDef) and node.name == "attach_p4_factor"
    )
    build_calls = [
        node
        for node in ast.walk(build_method)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "cls"
    ]
    assert any(
        any(
            keyword.arg == "joint_port_refinement"
            and ast.unparse(keyword.value) == "bool(is_v7)"
            for keyword in call.keywords
        )
        for call in build_calls
    )
    ledger_calls = [
        node
        for node in ast.walk(attach_method)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "P4RefinementLedger"
    ]
    assert len(ledger_calls) == 1
    keywords = {keyword.arg: keyword.value for keyword in ledger_calls[0].keywords}
    assert ast.unparse(keywords["joint_port_refinement"]) == (
        "bool(self.joint_port_refinement)"
    )
    assert ast.unparse(keywords["port_coupling_correction"]) == (
        "self.apply_port_coupling_correction if self.joint_port_refinement else None"
    )
