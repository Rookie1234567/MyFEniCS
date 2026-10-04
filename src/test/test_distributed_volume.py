"""Live identity, inverse-dual, complete stage and true finite action regressions."""

from types import SimpleNamespace

import numpy as np
import pytest
from mpi4py import MPI

from src.solvers.distributed_entity_volume import (
    NativeDistributedAction,
    affine_internal_recover,
)
from src.solvers.native_entity_adapter import CompleteEntityAdapter
from src.solvers.native_entity_dependencies import digest, validate_envelope
from src.solvers.native_entity_qualification import complete_native_checks


def inventory():
    p = {"passed": True, "checks": [{"passed": True}]}
    r = {k: dict(p) for k in ("TOPOLOGY", "ORIENTATION", "ROUTING")}
    r["ROUTING"]["rows"] = 378432
    for n in (1, 2, 4):
        r[f"BRIDGE{n}"] = {"MPI_size": n, "fixtures": [dict(p)], "directions": dict(p)}
    r["ACTIONS"] = [
        {"kind": k, "passed": True}
        for k in ("adjoint", "amplitudes", "forward", "modal")
    ]
    return r


@pytest.mark.parametrize("missing", list(inventory()))
def test_missing_stage_never_qualifies(missing):
    r = inventory()
    assert complete_native_checks(r)
    del r[missing]
    assert not complete_native_checks(r)


def test_empty_rank_and_default_pass_rejected():
    r = inventory()
    r["BRIDGE2"]["fixtures"] = []
    assert not complete_native_checks(r)
    r = inventory()
    r["BRIDGE4"]["MPI_size"] = 1
    assert not complete_native_checks(r)
    r = inventory()
    r["ORIENTATION"] = {"status": "NOT_RUN"}
    assert not complete_native_checks(r)


def test_self_consistent_saved_identity_rejects_live_material_and_helper_changes():
    keys = (
        "physical",
        "material",
        "phase",
        "basis",
        "owner_protocol",
        "index_dtype",
        "scalar_dtype",
        "axes",
        "modes",
        "slave_semantics",
        "stage_dependencies",
        "tags",
        "q",
    )
    expected = {k: "old" for k in keys}
    expected["helpers"] = {"helper": "old"}
    row = dict(
        expected,
        schema="native-entity-consumption.v1",
        commit=True,
        identity_sha256=digest(expected),
        parents=[],
        class_bindings=[],
    )
    validate_envelope(row, expected)
    for key in ("material", "helpers"):
        live = dict(expected)
        live[key] = "changed live dependency"
        with pytest.raises(ValueError, match="consumption identity"):
            validate_envelope(row, live)


def test_inverse_dual_nonunitary_complex_is_not_primal_dual():
    a = object.__new__(CompleteEntityAdapter)
    a.permutations = np.zeros((1, 2), np.int8)
    a.phases = np.array([0.3 + 0.7j])
    p = np.array([[2, 0.4j], [0.3, 1]], np.complex128)
    a.transforms = {(0, 0): p}
    a.inverses = {(0, 0): np.linalg.inv(p)}
    u = np.array([[1 + 0.2j, -0.8 + 0.4j]])
    r = np.array([[-0.3 + 0.9j, 1.1 - 0.6j]])
    canonical = a.canonical_from_physical(u)
    dual = a.physical_dual_from_canonical(r)
    assert np.allclose(np.vdot(r, canonical), np.vdot(dual, u), rtol=1e-13)
    wrong = a.phases[0].conjugate() * (p.conjugate().T @ r[0])
    assert not np.allclose(dual[0], wrong)


def test_native_distributed_full_action_shared_cells_complex_MPC_and_adjoint():
    rng = np.random.default_rng(42)
    n = 7
    mats = [rng.normal(size=(4, 4)) + 1j * rng.normal(size=(4, 4)) for _ in range(2)]
    dofs = np.array([[0, 1, 2, 3], [2, 4, 5, 6]], np.int32)
    lit = {
        "actual_dof_global_ids": np.arange(n),
        "actual_dof_owners": np.zeros(n, np.int32),
        "cell_permutations": np.zeros(2, np.uint32),
        "cell_native_dofs": dofs,
        "slave_local_dofs": np.array([1]),
        "MPC_offsets": np.array([0, 0, 1, 1, 1, 1, 1, 1]),
        "MPC_masters": np.array([0]),
        "MPC_coefficients": np.array([0.7 + 0.2j]),
    }
    e = SimpleNamespace(dim=4, entity_dofs=[[], [], []], entity_transformations=dict)
    action = NativeDistributedAction(MPI.COMM_SELF, lit, mats, [0, 1], e, n, 2)
    expanded = np.eye(n, dtype=np.complex128)
    expanded[1] = 0
    expanded[1, 0] = 0.7 + 0.2j
    physical = np.zeros((n, n), np.complex128)
    for ids, mat in zip(dofs, mats, strict=True):
        physical[np.ix_(ids, ids)] += mat
    oracle = expanded.conjugate().T @ physical @ expanded
    x = rng.normal(size=n) + 1j * rng.normal(size=n)
    x[1] = 0
    y = rng.normal(size=n) + 1j * rng.normal(size=n)
    y[1] = 0
    assert np.allclose(action.apply_original(x), oracle @ x)
    assert np.allclose(action.apply_original_adjoint(y), oracle.conjugate().T @ y)
    assert not np.allclose(oracle.T @ y, oracle.conjugate().T @ y)
    assert np.allclose(action.apply_original(np.zeros(n, np.complex128)), 0)


def test_affine_recovery_difference_removes_nonzero_particular_solution():
    from scipy.linalg import lu_factor

    a = np.array([[2 + 0.3j, 0.4 - 1j], [0.9 + 0.2j, 3 - 0.4j]])
    lu, piv = lu_factor(a[1:, 1:])
    t = np.eye(2)
    f = np.array([0.6 + 0.9j])
    x = np.array([0.2 - 0.8j, 0j])
    y = np.array([1 + 0.4j, 0j])

    def recover(z):
        return affine_internal_recover(a, lu, piv, [0], [1], z.copy(), f, t)

    assert np.allclose(
        recover(x) - recover(y), recover(x - y) - recover(np.zeros(2, complex))
    )
    assert not np.allclose(recover(x) - recover(y), recover(x - y))
    assert np.allclose((a @ recover(x))[1:], f)
