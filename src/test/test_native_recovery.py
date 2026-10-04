"""Focused V40 persistence, independent carrier and physical-identity gates."""

import numpy as np
import pytest
from scipy.sparse import block_diag, csr_matrix

from benchmarks.check_native_recovery import audit_packets
from src.solvers.native_boundary_adapter import (
    CoupledNativeBoundaryAction,
    NativeBoundaryAdapter,
    boundary_identity,
)
from src.solvers.native_recovery_packets import PacketStore, sha


def test_real_basix_transform_preserves_complex_nonhermitian_tensor():
    import basix

    from src.solvers.native_recovery_study import orient_basix_tensor

    element = basix.create_element(
        basix.ElementFamily.N1E,
        basix.CellType.hexahedron,
        2,
        basix.LagrangeVariant.legendre,
    )
    rng = np.random.default_rng(4040)
    tensor = rng.normal(size=(element.dim, element.dim)) + 1j * rng.normal(
        size=(element.dim, element.dim)
    )
    original = tensor.copy()
    for code in (0, 1, 15, (1 << 24) - 1):
        transform = np.eye(element.dim)
        element.T_apply(transform.ravel(), element.dim, code)
        actual = orient_basix_tensor(element, tensor, code)
        assert np.allclose(actual, transform @ tensor @ transform.T, atol=1e-13)
        assert np.array_equal(tensor, original)
        assert actual.dtype == np.complex128


def synthetic_packets(tmp_path):
    """Two non-Hermitian classes, nonmutual 40 ports and affine internal RHS."""
    from mpi4py import MPI

    from src.solvers.hcurl_assembly_time_condensation import (
        AssemblyTimeCondensedSystem,
        CellRecoveryMap,
        TraceConstraintMap,
    )
    from src.solvers.native_recovery_packets import save_system

    rng = np.random.default_rng(4019)
    n, nm = 1765, 40
    s = PacketStore(tmp_path, {"fixture": "synthetic-no-native-qualification"})
    ip, tp = np.arange(450), np.arange(450, 882)
    local = []
    names = []
    caches = {
        k: {} for k in ("recovery", "lu", "rhs_trace", "schur", "identity", "original")
    }
    for ci in range(2):
        a = np.diag(np.full(882, 2 + (ci + 1) * 0.2j))
        a[0, 450], a[450, 0] = 0.1 + 0.04j, -0.08 + 0.07j
        vii = a[np.ix_(ip, ip)]
        rec = -a[np.ix_(ip, tp)] / np.diag(vii)[:, None]
        rhs_trace = -a[np.ix_(tp, ip)] / np.diag(vii)[None, :]
        values = {
            "original": a,
            "raw_tensor": a,
            "recovery": rec,
            "rhs_trace": rhs_trace,
            "lu": vii.copy(),
            "pivots": ip.astype(np.int32),
            "schur": a[np.ix_(tp, tp)] + a[np.ix_(tp, ip)] @ rec,
            "identity": np.eye(450),
            "interior_positions": ip,
            "trace_positions": tp,
        }
        name = f"class_{ci}"
        s.save(name, values, {"synthetic": True})
        names.append(name)
        for k, cache in caches.items():
            cache[("test", ci)] = (
                (values["lu"], values["pivots"]) if k == "lu" else values[k]
            )
        local.append(a)
    interior = np.r_[ip, ip + 882]
    active = np.r_[tp, tp + 882]
    offsets = np.arange(n + 1)
    masters = np.arange(n)
    masters[-1] = int(active[0])
    dual = np.ones(n, complex)
    dual[-1] = np.exp(-0.2j)
    lit = {
        "cell_dofs": np.array([np.arange(882), np.arange(882) + 882]),
        "master_offsets": offsets,
        "master_rows": masters,
        "master_dual_coefficients": dual,
        "slaves": np.array([n - 1]),
        "interiors": interior,
        "cell_tags": np.array([1, 2]),
    }
    expansion = {
        int(r): (np.array([i]), np.array([1 + 0j])) for i, r in enumerate(active)
    }
    constraint = TraceConstraintMap(
        active,
        {int(r): i for i, r in enumerate(active)},
        expansion,
        len(active),
        len(active),
        1,
        {},
    )
    system = AssemblyTimeCondensedSystem(
        None,
        active,
        dict(constraint.original_to_active),
        constraint,
        tuple(
            CellRecoveryMap(ip + i * 882, tp + i * 882, ("test", i)) for i in range(2)
        ),
        caches["recovery"],
        caches["lu"],
        caches["identity"],
        caches["identity"],
        caches["rhs_trace"],
        caches["identity"],
        n,
        len(active),
        len(active),
        nm,
        len(interior),
        len(interior),
        {},
        MPI.COMM_SELF,
        len(active),
        nm,
        caches["schur"],
        caches["original"],
    )
    save_system(s, system, names)
    s.save("geometry", lit, {"n": n, "ports": nm, "synthetic": True})
    V = block_diag(
        [csr_matrix(a) for a in local] + [csr_matrix((1, 1), dtype=complex)],
        format="csr",
    )
    s.save(
        "oracle",
        {
            "data": V.data,
            "indices": V.indices,
            "indptr": V.indptr,
            "shape": np.array(V.shape),
        },
        {},
    )
    quad = {}
    for ci in range(2):
        for q in ("q15", "q17", "native"):
            quad[f"tag{ci + 1}_{q}"] = local[ci]
        quad[f"tag{ci + 1}_cell"] = np.array([ci, ci])
    s.save("quadrature", quad, {"tags": [1, 2]})
    C, D = np.zeros((n, nm), complex), np.zeros((nm, n), complex)
    C[active] = rng.normal(size=(len(active), nm)) + 1j * rng.normal(
        size=(len(active), nm)
    )
    D[:, active] = rng.normal(size=(nm, len(active))) + 1j * rng.normal(
        size=(nm, len(active))
    )
    values = {"C_native": C, "C_adapter": C, "D_native": D, "D_adapter": D}
    for label in ("a", "b", "zero", "scale"):
        x = (
            np.zeros(n, complex)
            if label == "zero"
            else rng.normal(size=n) + 1j * rng.normal(size=n)
        )
        if label == "scale":
            x = (0.37 - 0.91j) * values["a_x"]
        x[-1] = 0
        values.update(
            {
                label + "_x": x,
                label + "_volume": V @ x,
                label + "_adjoint_volume": V.conj().T @ x,
                label + "_action": V @ x + C @ (D @ x),
                label + "_adjoint": V.conj().T @ x + D.conj().T @ (C.conj().T @ x),
            }
        )
    f = rng.normal(size=n) + 1j * rng.normal(size=n)
    f[-1] = 0
    g = rng.normal(size=nm) + 1j * rng.normal(size=nm)
    z = rng.normal(size=len(active) + nm) + 1j * rng.normal(size=len(active) + nm)
    z2 = rng.normal(size=len(z)) + 1j * rng.normal(size=len(z))

    def recover(zz):
        u = np.zeros(n, complex)
        u[active] = zz[: len(active)]
        for i in range(2):
            ii, tt = ip + i * 882, tp + i * 882
            u[ii] = (
                f[ii] / np.diag(local[i])[ip] + caches["recovery"][("test", i)] @ u[tt]
            )
        return u

    u, u2, u0, ud = recover(z), recover(z2), recover(np.zeros_like(z)), recover(z - z2)
    expanded = u.copy()
    expanded[-1] = np.exp(0.2j) * u[active[0]]
    red = f.copy()
    sv = np.zeros(n, complex)
    for i in range(2):
        ii, tt = ip + i * 882, tp + i * 882
        red[tt] += caches["rhs_trace"][("test", i)] @ f[ii]
        sv[tt] += caches["schur"][("test", i)] @ u[tt]
    sa = np.r_[(sv + C @ z[len(active) :])[active], z[len(active) :] - D @ u]
    rr = np.r_[red[active], g]
    inj = np.zeros(n, complex)
    inj[active] = (rr - sa)[: len(active)]
    values.update(
        f=f,
        g=g,
        z=z,
        z2=z2,
        alpha=z[len(active) :],
        u=u,
        u2=u2,
        u_zero=u0,
        u_difference=ud,
        expanded=expanded,
        reduced_rhs=rr,
        schur_action=sa,
        reduced_injection=inj,
        rFE=f - V @ u - C @ z[len(active) :],
        rport=g + D @ u - z[len(active) :],
        rnative=f - C @ g - V @ u - C @ (D @ u),
        native_coupled_u=V @ u + C @ (D @ u),
    )
    s.save("recovery", values, {})
    return s


def test_real_saved_packet_checker_and_nonzero_affine_workflow(tmp_path):
    s = synthetic_packets(tmp_path)
    assert audit_packets(s)["passed"]
    from src.solvers.native_boundary_adapter import independent_trace_port_terms
    from src.solvers.native_recovery_packets import load_system
    from src.solvers.p6_cell_condensed_action import P6CellCondensedAction

    system, _ = load_system(s)
    d = s.read("recovery")[1]
    action = P6CellCondensedAction(
        system,
        H_p=np.eye(40, dtype=complex),
        direct_trace_terms=independent_trace_port_terms(
            system, d["C_native"], d["D_native"]
        ),
    )
    assert np.allclose(
        action.recover_storage(d["z"], full_rhs=d["f"]), d["u"], rtol=1e-12, atol=1e-12
    )
    assert np.allclose(
        action.reduce_rhs(d["f"], port_rhs=d["g"], rhs_is_mpc_dual=True),
        d["reduced_rhs"],
        rtol=1e-12,
        atol=1e-12,
    )
    assert (
        sha(s.root / "class_0.json")
        == s.read("system")[0]["metadata"]["classes"][0]["sha256"]
    )


def test_saved_checker_rejects_wrong_same_shape_physical_contract(tmp_path):
    from src.solvers.bounded_port_provider import content_hash

    s = synthetic_packets(tmp_path)
    _row, lit = s.read("geometry")
    expected = {
        "physical": "frozen",
        "basis": "p6",
        "dependencies": s.dependencies,
        "native": content_hash({k: v for k, v in lit.items() if k != "cell_tags"}),
    }
    s.expected_contract = expected
    original = s.read

    def replaced(name):
        result, arrays = original(name)
        if name == "geometry":
            result["metadata"]["contract"] = dict(
                expected, physical="wrong-material-phase"
            )
        return result, arrays

    s.read = replaced
    with pytest.raises(ValueError, match="consumer contract mismatch"):
        audit_packets(s)


def test_native_worker_budget_debits_live_stage_without_ready_reentry(
    monkeypatch, tmp_path
):
    import time

    from src.solvers.native_recovery_scope import RecoveryWindow

    w = RecoveryWindow(tmp_path, label="fixture")
    monkeypatch.setattr(w, "guard_worker_parent", lambda: None)
    monkeypatch.setattr(w, "snapshot", lambda: {"heavy_remaining_seconds": 10000})
    monkeypatch.setattr(
        w,
        "ledger",
        lambda: {
            "active": {
                "role": "BUILD",
                "before_clock": {"observed_monotonic": time.monotonic() - 10},
            },
            "runs": [{"role": "PREFLIGHT", "elapsed_seconds": 20}],
        },
    )
    assert 2369 < w.native_remaining_inside_worker() <= 2370


@pytest.mark.parametrize(
    "corruption", ["q17", "internal_rhs", "port_rhs", "recovery", "slave", "class"]
)
def test_independent_checker_rejects_corrupted_science(tmp_path, corruption):
    s = synthetic_packets(tmp_path)
    original = s.read

    def broken(name):
        row, a = original(name)
        if name == "quadrature" and corruption == "q17":
            del a["tag1_q17"]
        if name == "recovery":
            if corruption == "internal_rhs":
                a["f"][:450] = 0
                a["f"][882:1332] = 0
            if corruption == "port_rhs":
                a["g"][:] = 0
            if corruption == "recovery":
                a["u"][0] += 0.01
            if corruption == "slave":
                a["u"][-1] = 1e-30
        if name == "system" and corruption == "class":
            a["cell_class"][0] = 1
        return row, a

    s.read = broken
    try:
        result = audit_packets(s)
    except (ValueError, KeyError):
        return
    assert not result["passed"]


def test_atomic_commit_and_dependency_hash_failures(tmp_path):
    s = PacketStore(tmp_path, {"source": "frozen"})
    s.save("first", {"a": np.array([1 + 2j])}, {})
    (tmp_path / "second.npz").write_bytes(b"half write")
    assert not s.has("second") and s.has("first")
    with pytest.raises(FileExistsError):
        s.save("first", {}, {})
    s.dependencies = {"source": "wrong"}
    with pytest.raises(ValueError, match="dependency"):
        s.read("first")
    s.dependencies = {"source": "frozen"}
    (tmp_path / "first.npz").write_bytes(b"bad hash")
    with pytest.raises(ValueError):
        s.read("first")


def test_transpose_pointers_do_not_scale_with_native_size():
    n = 345771066
    a = NativeBoundaryAdapter(
        csr_matrix(
            (np.array([1 + 0.2j]), np.array([n - 1]), np.array([0, 1])), shape=(1, n)
        ),
        [0],
        n,
        1,
        [],
        identity="capacity-only",
    )
    assert a.EH.format == "csc" and len(a.EH.indptr) == 2
    assert a.EH.data.nbytes + a.EH.indices.nbytes + a.EH.indptr.nbytes < 100


def test_entity_builder_has_no_native_length_default_or_dense_row():
    from src.solvers.directional_boundary import BoundaryLayout, FacetPolynomial
    from src.solvers.native_boundary_adapter import build_literal_adapter
    from src.test.test_boundary_structure import element

    e = element()
    layout = BoundaryLayout(
        [0.0, 1.0, 2.0], [0.0, 1.0, 2.0], FacetPolynomial(e), (1, 1)
    )
    literal = {
        "cell_dofs": np.arange(882)[None, :],
        "coordinates": np.array(
            [[x, y, z] for z in (0.0, 1.0) for y in (0.0, 1.0) for x in (0.0, 1.0)]
        ),
        "geometry_dofmap": np.arange(8)[None, :],
        "permutations": np.array([0], np.uint32),
    }
    description = {
        "name": "synthetic-entity-capacity-only",
        "cells": [
            {
                "side": "bottom",
                "indices": [0, 0, 0],
                "bounds_nm": [[0.0, 1.0], [0.0, 1.0], [0.0, 1.0]],
            }
        ],
    }
    adapter, meta = build_literal_adapter(
        e, literal, description, layout, 345771066, np.array([], np.int64)
    )
    assert (
        adapter.E.shape[1] == 345771066
        and len(adapter.EH.indptr) == adapter.E.shape[0] + 1
    )
    assert meta["native_width_dense_intermediate"] is False
    assert (
        adapter.E.data.nbytes + adapter.E.indices.nbytes + adapter.E.indptr.nbytes
        < 2**20
    )


def test_consumer_same_shape_wrong_geometry_phase_material_and_source():
    from src.solvers.directional_boundary import (
        BoundaryLayout,
        DirectionalBoundaryAction,
        FacetPolynomial,
    )
    from src.test.test_boundary_structure import element, modes

    def boundary(phase=1):
        return DirectionalBoundaryAction(
            BoundaryLayout([0, 1], [0, 1], FacetPolynomial(element()), (phase, 1)),
            modes(),
            30,
        )

    b = boundary()
    identity = {
        "boundary": boundary_identity(b),
        "material": "Si-frozen",
        "source": "frozen",
        "native": "literal",
    }
    a = NativeBoundaryAdapter(
        csr_matrix(np.eye(b.layout.rows, dtype=complex)),
        np.arange(b.layout.rows),
        b.layout.rows,
        b.layout.rows,
        [],
        identity=identity,
    )

    class Volume:
        def __init__(self, i):
            self.identity = i

        def __call__(self, x, adjoint=False):
            return x.copy()

    CoupledNativeBoundaryAction(a, b, Volume(identity), contract=identity)
    for key in ("material", "source", "native"):
        bad = dict(identity)
        bad[key] = "wrong"
        with pytest.raises(ValueError, match="consumer identity"):
            CoupledNativeBoundaryAction(a, b, Volume(bad), contract=identity)
    with pytest.raises(ValueError, match="consumer identity"):
        CoupledNativeBoundaryAction(
            a, boundary(np.exp(0.2j)), Volume(identity), contract=identity
        )


@pytest.mark.parametrize(
    "stage", ["PREFLIGHT", "BUILD", "RECOVER", "CHECK", "DEPLOY", "CAPACITY"]
)
def test_actual_v40_dat_registered_with_isolated_scope(stage):
    from src.io.port_preparation import ROOT, load_preparation

    r = load_preparation(
        ROOT / f"input/task042_neural_coarse_inverse/v40_{stage.lower()}.dat"
    )
    assert r.derived["preparation_scope"] == "v40" and r.derived["stage"] == stage
    assert not r.derived["target_solve"] and r.execution["mpi_size"] == 1
