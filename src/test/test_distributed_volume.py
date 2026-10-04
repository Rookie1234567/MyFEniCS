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


def test_reused_direction_evidence_requires_explicit_source_and_full_coverage():
    from src.solvers.native_entity_qualification import require_direction_coverage

    proof = {
        "source": {"sha256": "bound-array", "path": "saved.npz"},
        "codes": [3, 7],
        "passed": True,
    }
    assert require_direction_coverage([7, 3], [proof])["passed"]
    with pytest.raises(ValueError, match="encountered"):
        require_direction_coverage([3, 8], [proof])
    with pytest.raises(ValueError, match="source"):
        require_direction_coverage([3], [dict(proof, source=None)])


def test_target_gate_cannot_promote_finite_action_or_payload_to_full_qualification():
    from src.solvers.distributed_volume_delivery import target_decision

    arguments = {
        "finite_passed": True,
        "neighbors": [],
        "backend_ready": True,
        "predicted_peak": 31 * 2**30,
        "exclusive_lock_verified": True,
    }
    assert target_decision(**arguments)["admitted"]
    for change, expected in [
        ({"finite_passed": False}, "FINITE_NUMERICAL_GATE_FAILED"),
        ({"neighbors": [{"pid": 42}]}, "OTHER_HEAVY_PRESENT"),
        ({"predicted_peak": None}, "CONSERVATIVE_TARGET_RSS_PREDICTION_UNKNOWN"),
        ({"backend_ready": False}, "TARGET_CANONICAL_VOLUME_BACKEND_NOT_IMPLEMENTED"),
    ]:
        result = target_decision(**(arguments | change))
        assert not result["admitted"] and expected in result["reasons"]


def test_checker_recomputes_oriented_class_and_rank_consumption():
    from collections import Counter

    from benchmarks.check_frozen_volume_dependencies import (
        literal_class_counts,
        require_declared_counts,
    )

    xyz = np.asarray(
        [[x, y, z] for z in (2.0, 3.0) for y in (1.0, 2.0) for x in (18.0, 19.0)]
    )
    a = {
        "coordinates": xyz,
        "cell_vertices": np.arange(8)[None, :],
        "cell_tags": np.array([3]),
        "cell_permutations": np.array([15]),
    }
    raw, oriented, _ = literal_class_counts(a, 1)
    row = {
        "tag": 3,
        "width_hex": [float(1).hex()] * 3,
        "count": 1,
        "rank_users": [0],
        "permutation": 15,
        "native_reference_vertex_order": list(range(8)),
    }
    require_declared_counts(
        oriented, [row], oriented=True, users={next(iter(oriented)): {0}}
    )
    with pytest.raises(ValueError, match="rank users"):
        require_declared_counts(
            oriented, [row], oriented=True, users={next(iter(oriented)): {1}}
        )
    with pytest.raises(ValueError, match="counts"):
        require_declared_counts(Counter(raw), [dict(row, count=2)])


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


def test_literal_native_CSR_shared_contributions_and_complex_MPC():
    from scipy.sparse import csr_matrix

    from src.solvers.native_witness_csr import assemble_witness_csr

    a = np.array([[2 + 0.7j, 0.3 - 1j], [0.9 + 0.2j, 3 - 0.4j]])
    b = np.array([[1 - 0.6j, 0.4 + 0.8j], [1.2 - 0.3j, 4 + 0.1j]])
    e = np.array([[1, 0, 0], [0.6 + 0.8j, 0, 0], [0, 0, 1]], complex)
    expected = np.zeros((3, 3), complex)
    expected[:2, :2] += a
    expected[1:, 1:] += b
    expected = e.conjugate().T @ expected @ e
    actual = assemble_witness_csr([a, b], [[0, 1], [1, 2]], csr_matrix(e), 3)
    assert np.allclose(actual.toarray(), expected)
    assert not np.allclose(expected, e.T @ e)


def test_p6_layer_orientation_against_native_Basix_both_axes():
    from src.solvers.distributed_entity_volume import cell_transform
    from src.solvers.distributed_volume_study import element
    from src.solvers.native_recovery_study import orient_basix_tensor

    e = element()
    rng = np.random.default_rng(424201)
    a = rng.normal(size=(882, 882)) + 1j * rng.normal(size=(882, 882))
    for info in (1 << 18, 3, 585):
        t = cell_transform(e, info)
        assert (
            np.linalg.norm(t @ a @ t.T - orient_basix_tensor(e, a, info))
            / np.linalg.norm(a)
            < 1e-12
        )


def test_actual_V42_one_run_schema_registration():
    from src.io.port_preparation import load_preparation
    from src.solvers.distributed_volume_scope import ROOT, STAGES

    for name in STAGES:
        r = load_preparation(
            ROOT / f"input/task042_neural_coarse_inverse/v42_{name.lower()}.dat"
        )
        assert r.derived["stage"] == name and r.derived["preparation_scope"] == "v42"
        assert r.derived["target_solve"] is False


def test_native_inverse_transpose_transfer_and_independent_dual():
    from src.solvers.distributed_entity_volume import cell_transform
    from src.solvers.distributed_saved_recovery import native_transfer
    from src.solvers.distributed_volume_study import element

    e = element()
    for old, new in ((0, 585), (3, 1 << 18), (585, 3)):
        m = native_transfer(e, old, new)
        t0, t1 = cell_transform(e, old), cell_transform(e, new)
        assert np.linalg.norm(t1.T @ m - t0.T) < 1e-10
        x = np.sin(np.arange(882)) + 1j * np.cos(np.arange(882) * 0.31)
        y = np.cos(np.arange(882) * 0.7) + 1j * np.sin(np.arange(882) * 0.23)
        assert abs(np.vdot(y, m @ x) - np.vdot(m.conjugate().T @ y, x)) < 1e-9


def test_current_mpi_consumer_abi_and_live_producer_packet_identity():
    from src.solvers.distributed_recovery_study import producer_abi, producer_store
    from src.solvers.native_entity_study import environment
    from src.solvers.native_recovery_study import dependencies

    env = dict(environment(), MPI_size=4)
    assert producer_abi(env)["MPI_size"] == 1
    with pytest.raises(ValueError, match="live consumer ABI"):
        producer_abi(dict(env, scalar="float64"))
    # Real immutable geometry plus current physics; no saved self-identity.
    packet, _ = producer_store()
    assert packet.dependencies == dependencies()
    # Production V40 uses the exact literal trace carrier. Native form
    # quadrature is an independent oracle and may have roundoff interiors.
    _, saved = packet.read("recovery")
    _, numbering = packet.read("system")
    interiors = numbering["cell_interior"]
    assert np.all(saved["C_adapter"][interiors] == 0)
    assert np.all(saved["D_adapter"][:, interiors] == 0)
    assert (
        np.linalg.norm(saved["C_native"] - saved["C_adapter"])
        / np.linalg.norm(saved["C_native"])
        <= 1e-10
    )
    assert (
        np.linalg.norm(saved["D_native"] - saved["D_adapter"])
        / np.linalg.norm(saved["D_native"])
        <= 1e-10
    )


def test_saved_owner_consumer_nonhermitian_nonmutual_ports_and_affine_rhs():
    from scipy.linalg import lu_factor

    from src.solvers.distributed_saved_recovery import SavedRecoveryConsumer

    rng = np.random.default_rng(424209)
    raw = [
        rng.normal(size=(4, 4)) + 1j * rng.normal(size=(4, 4)) + 6 * np.eye(4)
        for _ in range(2)
    ]
    dofs = np.array([[0, 1, 2, 3], [0, 1, 4, 5]])
    lit = {
        "cell_dofs": dofs,
        "master_offsets": np.arange(7),
        "master_rows": np.array([0, 0, 2, 3, 4, 5]),
        "master_dual_coefficients": np.array([1, 0.7 - 0.2j, 1, 1, 1, 1]),
    }
    numbering = {
        "cell_class": np.arange(2),
        "cell_interior": dofs[:, 2:],
        "cell_trace": dofs[:, :2],
        "owned_active": np.array([0]),
    }
    classes = []
    for a in raw:
        lu, piv = lu_factor(a[2:, 2:])
        classes.append(
            {
                "raw_tensor": a,
                "original": a,
                "lu": lu,
                "pivots": piv,
                "recovery": np.linalg.solve(a[2:, 2:], -a[2:, :2]),
                "rhs_trace": -np.linalg.solve(a[2:, 2:].T, a[:2, 2:].T).T,
                "trace_positions": np.array([0, 1]),
                "interior_positions": np.array([2, 3]),
            }
        )
    t = np.array([[2.0, 0.3, 0, 0], [0, 1.0, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]])
    bridge = {
        "producer_cells": np.arange(2),
        "owned_cells": 2,
        "producer_owner": np.zeros(6, np.int32),
        "transfer": [np.linalg.inv(t.T)] * 2,
        "native_transforms": [t] * 2,
    }
    C = np.zeros((6, 12), complex)
    D = np.zeros((12, 6), complex)
    C[0] = rng.normal(size=12) + 1j * rng.normal(size=12)
    D[:, 0] = rng.normal(size=12) + 1j * rng.normal(size=12)
    actor = SavedRecoveryConsumer(MPI.COMM_SELF, lit, numbering, classes, bridge, C, D)
    G = np.eye(6, dtype=complex)
    G[1] = 0
    G[1, 0] = 0.7 + 0.2j
    V = np.zeros((6, 6), complex)
    for ids, a in zip(dofs, raw, strict=True):
        V[np.ix_(ids, ids)] += a
    V = G.conjugate().T @ V @ G
    x = rng.normal(size=6) + 1j * rng.normal(size=6)
    x[1] = 0
    assert np.allclose(actor.apply_original(x, coupled=True), V @ x + C @ (D @ x))
    assert np.allclose(
        actor.apply_original(x, coupled=True, adjoint=True),
        V.conjugate().T @ x + D.conjugate().T @ (C.conjugate().T @ x),
    )
    f = rng.normal(size=6) + 1j * rng.normal(size=6)
    f[1] = 0
    g = rng.normal(size=12) + 1j * rng.normal(size=12)
    z = rng.normal(size=13) + 1j * rng.normal(size=13)
    u, u0 = actor.recover(z, f), actor.recover(np.zeros_like(z), f)
    assert np.allclose((V @ u)[2:], f[2:])
    assert np.allclose(u - u0, actor.recover(z, np.zeros_like(f)))
    assert np.allclose(actor.reduced_rhs(f, g)[1:], g)
    rFE, rp = f - V @ u - C @ z[1:], g + D @ u - z[1:]
    assert np.allclose(rFE - C @ rp, f - C @ g - V @ u - C @ (D @ u))
    assert not np.allclose(D, C.conjugate().T)
