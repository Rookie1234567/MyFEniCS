"""Small algebra and storage tests for the explicit 0.7 nm Hp policy."""

from hashlib import sha256
from types import SimpleNamespace

import numpy as np
import pytest
from petsc4py import PETSc

from src.solvers.p6_cell_condensed_action import (
    P6CellCondensedAction,
    P6CellPortTerms,
    P6RetainedBALHBridge,
    _array_payload_sha256,
    _array_sha256,
    _merge_explicit_hlocal,
    _normalise_port_terms,
    _positive_hp_diagonal,
    _readonly,
    _typed_array_sha256,
    native_residual_from_augmented,
)
from src.test.test_task039extra_v20_noncommuting_contract import (
    _FakeCondensed,
    _matrix,
)


def _diagonal_action(diagonal):
    action = object.__new__(P6CellCondensedAction)
    action.condensed = SimpleNamespace(appended_rows=len(diagonal))
    action._H_p = None
    action._H_p_diagonal = _positive_hp_diagonal(diagonal, size=len(diagonal))
    action._hp_solve_count = 0
    return action


def test_streamed_hashes_match_both_legacy_encodings_including_empty_arrays():
    values = (
        np.empty((0, 0), dtype=np.complex128),
        np.empty((3, 0), dtype=np.complex128),
        np.arange(24, dtype=np.float64).reshape(4, 6).astype(np.complex128)[:, ::2],
    )
    for value in values:
        array = np.ascontiguousarray(value, dtype=np.complex128)
        expected_cache = sha256(
            repr((array.shape, str(array.dtype))).encode() + array.tobytes(order="C")
        ).hexdigest()
        expected_payload = sha256(array.tobytes(order="C")).hexdigest()
        assert _array_sha256(value) == expected_cache
        assert _array_payload_sha256(value) == expected_payload

    diagonal = np.arange(1, 5, dtype=np.float64)
    expected_typed = sha256(
        repr((diagonal.shape, str(diagonal.dtype))).encode()
        + diagonal.tobytes(order="C")
    ).hexdigest()
    assert _typed_array_sha256(diagonal) == expected_typed

    hp = np.array([[2.0, 0.0], [0.0, 3.0]], dtype=np.complex128)
    hhat = np.array([[2.1, 0.2j], [-0.1j, 3.2]], dtype=np.complex128)
    dense_action = object.__new__(P6CellCondensedAction)
    dense_action.condensed = SimpleNamespace(appended_rows=2)
    dense_action._H_p = hp
    dense_action._H_p_diagonal = None
    dense_action._Hhat = hhat
    dense_identity = dict(dense_action.port_block_identity)
    assert dense_identity["H_p_sha256"] == sha256(hp.tobytes(order="C")).hexdigest()
    assert dense_identity["Hhat_sha256"] == sha256(hhat.tobytes(order="C")).hexdigest()

    diagonal_action = object.__new__(P6CellCondensedAction)
    diagonal_action.condensed = SimpleNamespace(appended_rows=2)
    diagonal_action._H_p = None
    diagonal_action._H_p_diagonal = np.array([2.0, 3.0], dtype=np.float64)
    diagonal_action._Hhat = hhat
    diagonal_identity = dict(diagonal_action.port_block_identity)
    assert diagonal_identity["H_p_storage_policy"] == "carrier_diagonal_exact"
    assert diagonal_identity["H_p_sha256"] is None
    assert diagonal_identity["H_p_diagonal_sha256"] == sha256(
        diagonal_action._H_p_diagonal.tobytes(order="C")
    ).hexdigest()
    assert diagonal_identity["H_p_dense_materialized_for_identity"] is False
    assert diagonal_identity["Hhat_sha256"] == sha256(hhat.tobytes(order="C")).hexdigest()


def test_exact_carrier_diagonal_solve_apply_is_owned_readonly_and_matches_dense(monkeypatch):
    source = np.array([1.5, 2.25, 4.0], dtype=np.float64)
    diagonal = _positive_hp_diagonal(source, size=3)
    source[0] = 99.0
    assert diagonal[0] == 1.5
    assert not diagonal.flags.writeable

    hp = np.diag(diagonal.astype(np.complex128))
    rhs = np.array([2.0 + 0.5j, -1.0j, 3.0 - 2.0j])
    expected = np.linalg.solve(hp, rhs)
    action = _diagonal_action(diagonal)

    def dense_solve_forbidden(*_args, **_kwargs):
        raise AssertionError("exact diagonal Hp must not call a dense solver")

    monkeypatch.setattr(np.linalg, "solve", dense_solve_forbidden)
    np.testing.assert_array_equal(action.original_hp_solve(rhs), expected)
    np.testing.assert_array_equal(action._hp_apply(expected), rhs)
    assert action.hp_solve_count == 1


@pytest.mark.parametrize(
    "diagonal",
    [
        np.array([1.0, 0.0]),
        np.array([1.0, -1.0]),
        np.array([1.0, np.nan]),
        np.array([1.0, np.inf]),
        np.array([1.0 + 1.0e-300j, 2.0 + 0.0j]),
    ],
)
def test_exact_carrier_diagonal_rejects_zero_nonpositive_or_nonfinite(diagonal):
    with pytest.raises(ValueError):
        _positive_hp_diagonal(diagonal, size=2)


@pytest.mark.parametrize(
    "hp",
    [
        np.array([[2.0, 1.0e-18j], [0.2 + 0.1j, 3.0]], dtype=np.complex128),
        np.array([[2.0, 0.4j], [-0.3 + 0.2j, 1.5]], dtype=np.complex128),
    ],
)
def test_any_nonzero_offdiagonal_uses_exact_generic_dense_fallback(monkeypatch, hp):
    rhs = np.array([0.5 + 1.0j, -2.0 + 0.25j])
    expected = np.linalg.solve(hp, rhs)
    action = object.__new__(P6CellCondensedAction)
    action.condensed = SimpleNamespace(appended_rows=2)
    action._H_p = hp.copy()
    action._H_p_diagonal = None
    action._hp_solve_count = 0
    calls = []
    original_solve = np.linalg.solve

    def observed_solve(matrix, values):
        calls.append(matrix)
        return original_solve(matrix, values)

    monkeypatch.setattr(np.linalg, "solve", observed_solve)
    np.testing.assert_allclose(action.original_hp_solve(rhs), expected, rtol=0.0, atol=0.0)
    assert calls == [action._H_p]
    assert action._H_p_diagonal is None


def test_omitted_hlocal_is_structural_zero_and_explicit_h_is_preserved():
    term = P6CellPortTerms(
        Bi=np.array([[0.2 + 0.1j, 0.0], [0.0, -0.3j]]),
        Di=np.array([[0.1, 0.2j], [-0.15j, 0.4]]),
        port_indices=np.array([0, 2]),
    )
    omitted = _normalise_port_terms(
        term,
        ni=2,
        nt=3,
        appended_rows=4,
        name="test",
        omit_structural_zero_hlocal=True,
    )
    assert omitted[0].shape == (2, 2) and np.any(omitted[0])
    assert omitted[2].shape == (2, 2) and np.any(omitted[2])
    assert omitted[-1] is None

    materialized = _normalise_port_terms(
        term,
        ni=2,
        nt=3,
        appended_rows=4,
        name="test",
        omit_structural_zero_hlocal=False,
    )[-1]
    assert materialized.shape == (2, 2)
    assert materialized.nbytes == 2 * 2 * np.dtype(np.complex128).itemsize
    assert np.count_nonzero(materialized) == 0
    readonly = _readonly(materialized)
    assert not readonly.flags.writeable

    explicit_h = np.array([[0.2 + 0.3j, 0.0], [-0.1j, 0.4]], dtype=np.complex128)
    explicit = _normalise_port_terms(
        P6CellPortTerms(term.Bi, term.Di, term.port_indices, H=explicit_h),
        ni=2,
        nt=3,
        appended_rows=4,
        name="test",
        omit_structural_zero_hlocal=True,
    )[-1]
    np.testing.assert_array_equal(explicit, explicit_h)

    omitted_cell = SimpleNamespace(
        ports=np.array([0, 2]), Hlocal=materialized, Hlocal_is_omitted=True
    )
    _merge_explicit_hlocal(None, omitted_cell)
    with pytest.raises(RuntimeError, match="explicit Hlocal"):
        _merge_explicit_hlocal(
            None,
            SimpleNamespace(
                ports=np.array([0, 2]),
                Hlocal=explicit,
                Hlocal_is_omitted=False,
            ),
        )
    hp = np.diag(np.array([1.0, 2.0, 3.0], dtype=np.complex128))
    _merge_explicit_hlocal(
        hp,
        SimpleNamespace(
            ports=np.array([0, 2]), Hlocal=explicit, Hlocal_is_omitted=False
        ),
    )
    np.testing.assert_array_equal(
        hp[np.ix_([0, 2], [0, 2])],
        np.array([[1.2 + 0.3j, 0.0], [-0.1j, 3.4]], dtype=np.complex128),
    )


def test_bridge_and_original_port_residual_use_original_hp_not_hhat(monkeypatch):
    hp_value = 2.5
    hp = np.array([[hp_value]], dtype=np.complex128)
    action = _diagonal_action(np.array([hp_value]))
    action.condensed = SimpleNamespace(
        active_rows=1,
        appended_rows=1,
        full_rows=2,
        comm=SimpleNamespace(Get_size=lambda: 1),
        trace_constraints=SimpleNamespace(
            owned_active_original_dofs=np.array([0], dtype=np.int64)
        ),
    )
    B = np.array([0.4 + 0.1j, -0.2 + 0.3j], dtype=np.complex128)
    D = np.array([-0.3 + 0.05j, 0.15 + 0.2j], dtype=np.complex128)
    K = np.array([[0.7 + 0.1j, 0.2], [-0.1j, 0.5 - 0.2j]], dtype=np.complex128)
    action.inject_trace_port = lambda value: np.array([value[0], 0.0j])
    action.apply_B_full = lambda alpha: B * alpha[0]
    action.apply_D_full = lambda field: np.array([D @ field])

    rhs = np.array([0.3 - 0.1j, 0.8 + 0.2j])
    full_rhs = np.array([rhs[0], 0.0j])
    hp_inverse_port_rhs = np.linalg.solve(hp, rhs[1:])
    z = K @ (full_rhs - B * hp_inverse_port_rhs[0])
    alpha = np.linalg.solve(hp, rhs[1:] + np.array([D @ z]))
    expected_bridge = np.r_[z[0], alpha[0]]

    def dense_solve_forbidden(*_args, **_kwargs):
        raise AssertionError("the diagonal bridge must use exact scalar division")

    monkeypatch.setattr(np.linalg, "solve", dense_solve_forbidden)
    bridge = P6RetainedBALHBridge(action, lambda values: K @ values)
    actual_bridge = bridge.apply(rhs)
    np.testing.assert_allclose(actual_bridge, expected_bridge, rtol=0.0, atol=1.0e-15)
    port_equation = rhs[1:] + action.apply_D_full(z) - hp @ actual_bridge[1:]
    assert np.linalg.norm(port_equation) <= 1.0e-15

    fe_residual = np.array([0.2 + 0.1j, -0.4 + 0.05j])
    port_residual = np.array([-0.3 + 0.2j])
    expected_native = fe_residual - B * (port_residual[0] / hp_value)
    actual_native = native_residual_from_augmented(action, fe_residual, port_residual)
    np.testing.assert_allclose(actual_native, expected_native, rtol=0.0, atol=1.0e-15)


def test_full_mode_diagonal_metadata_stays_linear_storage():
    diagonal = _positive_hp_diagonal(np.ones(32060, dtype=np.float64), size=32060)
    assert diagonal.shape == (32060,)
    assert diagonal.nbytes == 32060 * np.dtype(np.float64).itemsize
    assert not diagonal.flags.writeable


@pytest.mark.parametrize(
    ("storage", "hlocal", "omit_hlocal"),
    [
        ("legacy_dense", None, False),
        ("exact_diagonal", None, True),
        ("exact_diagonal_materialized_zero", None, False),
        (
            "exact_diagonal_explicit_hlocal",
            np.array([[0.1 + 0.2j, -0.05j], [0.07, 0.3 - 0.1j]]),
            True,
        ),
    ],
)
def test_constructor_old_new_storage_matches_full_action_bridge_and_residual(
    storage, hlocal, omit_hlocal
):
    rng = np.random.default_rng(270705)
    block = {
        "Vii": _matrix(rng, 2, 2, 5.0),
        "Vit": _matrix(rng, 2, 2),
        "Vti": _matrix(rng, 2, 2),
        "Vtt": _matrix(rng, 2, 2, 3.0),
        "Bi": _matrix(rng, 2, 2),
        "Bt": _matrix(rng, 2, 2),
        "Di": _matrix(rng, 2, 2),
        "Dt": _matrix(rng, 2, 2),
    }
    hp_diagonal = np.array([4.0, 6.0], dtype=np.float64)
    hp_dense = np.diag(hp_diagonal.astype(np.complex128))
    port_h = None if hlocal is None else np.asarray(hlocal, dtype=np.complex128)
    condensed = _FakeCondensed((block,))
    terms = {
        0: P6CellPortTerms(
            block["Bi"],
            block["Di"],
            np.asarray([0, 1], dtype=PETSc.IntType),
            Bt=block["Bt"],
            Dt=block["Dt"],
            H=port_h,
        )
    }
    if storage == "legacy_dense":
        action = P6CellCondensedAction(
            condensed,
            H_p=hp_dense,
            port_terms=terms,
            omit_structural_zero_hlocal=omit_hlocal,
        )
    else:
        action = P6CellCondensedAction(
            condensed,
            H_p_diagonal=hp_diagonal,
            port_terms=terms,
            omit_structural_zero_hlocal=omit_hlocal,
        )

    expected_hp = hp_dense.copy()
    if port_h is not None:
        expected_hp += port_h
    inverse_vii = np.linalg.inv(block["Vii"])
    expected_hhat = expected_hp + block["Di"] @ inverse_vii @ block["Bi"]
    expected_reduced = np.block(
        [
            [
                block["Vtt"] - block["Vti"] @ inverse_vii @ block["Vit"],
                block["Bt"] - block["Vti"] @ inverse_vii @ block["Bi"],
            ],
            [
                -(block["Dt"] - block["Di"] @ inverse_vii @ block["Vit"]),
                expected_hhat,
            ],
        ]
    )
    assert not np.allclose(expected_hhat, expected_hp)
    np.testing.assert_allclose(action.H_p, expected_hp, rtol=2e-14, atol=2e-14)
    np.testing.assert_allclose(action.Hhat, expected_hhat, rtol=2e-14, atol=2e-14)
    source = _matrix(rng, 4, 1)[:, 0]
    np.testing.assert_allclose(action.apply(source), expected_reduced @ source, rtol=2e-13, atol=2e-13)

    # Exercise the actual bridge over this constructed action.  The callback
    # is a fixed non-Hermitian map so this checks both original-Hp solves and
    # the nonzero B/Di routes without creating a larger factor.
    bal = _matrix(rng, 4, 4, 5.0)
    bridge_rhs = _matrix(rng, 4, 1)[:, 0]
    full_b = np.vstack((block["Bi"], block["Bt"]))
    full_d = np.hstack((block["Di"], block["Dt"]))
    injected = np.zeros(4, dtype=np.complex128)
    injected[[2, 3]] = bridge_rhs[:2]
    first_alpha = np.linalg.solve(expected_hp, bridge_rhs[2:])
    full_z = bal @ (injected - full_b @ first_alpha)
    expected_alpha = np.linalg.solve(expected_hp, bridge_rhs[2:] + full_d @ full_z)
    expected_bridge = np.r_[full_z[[2, 3]], expected_alpha]
    bridge = P6RetainedBALHBridge(action, lambda values: bal @ values)
    actual_bridge = bridge.apply(bridge_rhs)
    np.testing.assert_allclose(actual_bridge, expected_bridge, rtol=3e-13, atol=3e-13)
    np.testing.assert_allclose(
        bridge_rhs[2:] + full_d @ full_z - expected_hp @ actual_bridge[2:],
        0.0,
        rtol=0.0,
        atol=3e-13,
    )

    field = _matrix(rng, 4, 1)[:, 0]
    alpha = _matrix(rng, 2, 1)[:, 0]
    fe_rhs = _matrix(rng, 4, 1)[:, 0]
    port_rhs = _matrix(rng, 2, 1)[:, 0]
    e_fe = fe_rhs - np.block(
        [[block["Vii"], block["Vit"]], [block["Vti"], block["Vtt"]]]
    ) @ field
    e_port = port_rhs + full_d @ field - expected_hp @ alpha
    expected_native = e_fe - full_b @ np.linalg.solve(expected_hp, e_port)
    np.testing.assert_allclose(
        native_residual_from_augmented(action, e_fe, e_port),
        expected_native,
        rtol=2e-13,
        atol=2e-13,
    )

    inventory = dict(action.buffer_inventory)
    assert inventory["Hlocal_structural_zero_omitted_cell_count"] == int(port_h is None)
    assert inventory["Hlocal_explicit_cell_count"] == int(port_h is not None)
    if storage == "exact_diagonal":
        assert action._H_p is None
        assert action._H_p_diagonal is not None
        assert action._cells[0].Hlocal is None
    elif storage == "exact_diagonal_materialized_zero":
        assert action._H_p is None
        assert inventory["Hlocal_zero_matrix_materialized_cell_count"] == 1
    elif storage == "exact_diagonal_explicit_hlocal":
        assert action._H_p is not None
        assert action._H_p_diagonal is None
        assert np.count_nonzero(action._cells[0].Hlocal)
    port_identity = dict(action.port_block_identity)
    cache_identity = dict(action.cache_identity)
    assert port_identity["Hhat_sha256"] == sha256(action.Hhat.tobytes(order="C")).hexdigest()
    if action._H_p is None:
        assert port_identity["H_p_sha256"] is None
        assert cache_identity["H_p_sha256"] is None
    else:
        assert port_identity["H_p_sha256"] == sha256(action._H_p.tobytes(order="C")).hexdigest()
        assert cache_identity["H_p_sha256"] == _array_sha256(action._H_p)
    action.destroy()
