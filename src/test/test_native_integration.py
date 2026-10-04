"""V39 interface, evidence-link and affine-recovery regressions, no native mesh."""

import copy
from pathlib import Path

import numpy as np
import pytest
from scipy.sparse import csr_matrix

from benchmarks.check_boundary_structure import final_oracle_links
from benchmarks.check_native_integration import literal_layout_checks
from src.solvers.directional_boundary import (
    BoundaryLayout,
    DirectionalBoundaryAction,
    FacetPolynomial,
)
from src.solvers.native_boundary_adapter import (
    CoupledNativeBoundaryAction,
    NativeBoundaryAdapter,
    build_literal_adapter,
    literal_expansion,
)
from src.solvers.port_component_study import array_file
from src.test.test_boundary_structure import element, modes


def test_consumer_freezes_modes_coordinates_and_rejects_invalid_input():
    x = np.array([0.0, 0.7, 1.4])
    rows = modes()
    layout = BoundaryLayout(
        x, [0.0, 0.8, 1.6], FacetPolynomial(element()), (np.exp(0.2j), np.exp(-0.1j))
    )
    action = DirectionalBoundaryAction(layout, rows, 30)
    value = np.ones(layout.rows, np.complex128)
    before = action.apply(value)
    x[1] = 0.4
    rows[0]["e_vector"][0] = 2.0
    rows[0]["projection_denominator"] = 0.1
    assert np.array_equal(action.apply(value), before)
    with pytest.raises(ValueError, match="shape/complex128/finite"):
        action.apply(value.real)
    with pytest.raises(ValueError, match="shape/complex128/finite"):
        action.apply(value[:-1])
    bad = value.copy()
    bad[0] = np.nan
    with pytest.raises(ValueError, match="shape/complex128/finite"):
        action.apply(bad)
    rows = modes()
    rows[0]["projection_denominator"] = 0
    with pytest.raises(ValueError, match="positive H"):
        DirectionalBoundaryAction(layout, rows, 30)
    with pytest.raises(MemoryError, match="preallocation"):
        DirectionalBoundaryAction(layout, modes(), 30, cache_limit_bytes=1)
    with pytest.raises(ValueError):
        layout.x[1] = 0.3


def test_finite_surface_restriction_is_explicit_and_preserves_full_default():
    layout = BoundaryLayout(
        [0.0, 0.7, 1.4],
        [0.0, 0.8, 1.6],
        FacetPolynomial(element()),
        (np.exp(0.2j), np.exp(-0.1j)),
    )
    rows = modes()
    full = DirectionalBoundaryAction(layout, rows, 30)
    all_faces = [
        (s, i, j) for s in ("top", "bottom") for i in range(2) for j in range(2)
    ]
    complete = DirectionalBoundaryAction(layout, rows, 30, face_inventory=all_faces)
    pieces = [
        DirectionalBoundaryAction(layout, rows, 30, face_inventory=[face])
        for face in all_faces
    ]
    rng = np.random.default_rng(8)
    x = rng.normal(size=layout.rows) + 1j * rng.normal(size=layout.rows)
    alpha = rng.normal(size=len(rows)) + 1j * rng.normal(size=len(rows))
    assert np.allclose(full.recover(x), complete.recover(x), rtol=1e-12, atol=1e-12)
    assert np.allclose(
        full.recover(x), sum(p.recover(x) for p in pieces), rtol=1e-12, atol=1e-12
    )
    assert np.allclose(
        full.modal_rhs(alpha),
        sum(p.modal_rhs(alpha) for p in pieces),
        rtol=1e-12,
        atol=1e-12,
    )
    with pytest.raises(ValueError, match="facet inventory"):
        DirectionalBoundaryAction(
            layout, rows, 30, face_inventory=[("top", 0, 0), ("top", 0, 0)]
        )


@pytest.mark.parametrize("corruption", ["missing", "permuted", "mode", "value"])
def test_final_inventory_oracle_link_rejects_coverage_and_numerical_corruption(
    corruption,
):
    full = []
    for i, row in enumerate(modes()):
        full.append(dict(row, mode_index=i, m=i, n=0, polarization="s"))
    selected = copy.deepcopy([full[0], full[4]])
    data = {
        f"q{q}_{label}_amplitudes": np.arange(1, 7, dtype=np.complex128) * (1 + 0.3j)
        for q in (30, 60)
        for label in ("a", "b")
    }
    oracle = {
        label + "_amplitudes": data["q30_" + label + "_amplitudes"][[0, 4]].copy()
        for label in ("a", "b")
    }
    assert all(
        c["passed"] for c in final_oracle_links(data, oracle, full, selected, [0, 4])
    )
    indices = [0, 4]
    if corruption == "missing":
        indices = [0]
    if corruption == "permuted":
        indices = [4, 0]
    if corruption == "mode":
        selected[0]["m"] = 5
    if corruption == "value":
        data["q30_a_amplitudes"][4] += 1
    if corruption == "value":
        assert not all(
            c["passed"]
            for c in final_oracle_links(data, oracle, full, selected, indices)
        )
    else:
        with pytest.raises(ValueError):
            final_oracle_links(data, oracle, full, selected, indices)


def test_literal_mapping_audit_recomputes_periodic_and_orientation(tmp_path):
    e = element()
    layout = BoundaryLayout(
        [0.0, 1.0, 2.0],
        [0.0, 1.0, 2.0],
        FacetPolynomial(e),
        (np.exp(0.2j), np.exp(-0.3j)),
    )
    active = layout.polynomial.active["bottom"]
    compact = layout.maps["bottom"][0, 0]
    literal = {
        "cell_dofs": np.arange(882)[None, :],
        "coordinates": np.array(
            [[x, y, z] for z in (0.0, 1.0) for y in (0.0, 1.0) for x in (0.0, 1.0)]
        ),
        "geometry_dofmap": np.arange(8)[None, :],
        "permutations": np.array([0], np.uint32),
        "master_offsets": np.arange(883),
        "master_rows": np.arange(882),
        "master_dual_coefficients": np.ones(882, np.complex128),
    }
    conversion = {
        "native_rows": active.copy(),
        "compact_rows": np.sort(compact),
        "primal_map": np.zeros((len(active), len(active)), np.complex128),
    }
    conversion["primal_map"][
        np.arange(len(active)), np.searchsorted(conversion["compact_rows"], compact)
    ] = layout.weights["bottom"][0, 0]
    desc = {
        "name": "synthetic",
        "cells": [
            {
                "side": "bottom",
                "indices": [0, 0, 0],
                "bounds_nm": [[0.0, 1.0], [0.0, 1.0], [0.0, 1.0]],
            }
        ],
    }
    patch = {
        "description": desc,
        "storage_rows": 882,
        "literal": array_file(tmp_path / "literal.npz", **literal),
    }
    receipt = array_file(tmp_path / "old_conversion.npz", **conversion)
    assert all(c["passed"] for c in literal_layout_checks(e, layout, patch, receipt))
    for kind in ("coefficient", "orientation"):
        bad = {k: v.copy() for k, v in literal.items()}
        if kind == "coefficient":
            bad["master_dual_coefficients"][active[0]] = 1.1 + 0.2j
        else:
            bad["permutations"][0] = 1
        patch["literal"] = array_file(tmp_path / (kind + ".npz"), **bad)
        assert not all(
            c["passed"] for c in literal_layout_checks(e, layout, patch, receipt)
        )
    adapter, ownership = build_literal_adapter(
        e, literal, desc, layout, 882, np.array([], np.int64)
    )
    assert ownership["largest_entity_transform"] == 60
    assert ownership["small_linear_solves"] == 0
    rng = np.random.default_rng(5)
    a = rng.normal(size=882) + 1j * rng.normal(size=882)
    t = adapter.extract(a)
    assert np.allclose(t[compact] * layout.weights["bottom"][0, 0], a[active])


def test_sparse_native_primal_dual_and_storage_copy(tmp_path):
    E = csr_matrix(
        np.array([[1 + 0.3j, 0, 2 - 0.2j, 0], [0, 0.5 - 0.7j, 1, 0]], np.complex128)
    )
    adapter = NativeBoundaryAdapter(E, [1, 3], 4, 5, [3], identity="fixed")
    x = np.array([0.2 + 1j, 3 - 0.1j, 1 - 0.9j, 0], np.complex128)
    y = np.array([1, 2 + 0.3j, -0.1j, 2 - 1j, 3], np.complex128)
    assert np.allclose(np.vdot(y, adapter.extract(x)), np.vdot(adapter.scatter(y), x))
    assert adapter.scatter(y)[3] == 0
    bad = x.copy()
    bad[3] = 1
    with pytest.raises(ValueError, match="slave zero"):
        adapter.extract(bad)
    restored = NativeBoundaryAdapter.from_arrays(adapter.arrays(), identity="fixed")
    assert np.array_equal(restored.extract(x), adapter.extract(x))


def test_literal_identity_without_saved_mpc_and_nontrivial_coefficients():
    assert np.array_equal(literal_expansion({}, 3).toarray(), np.eye(3))
    lit = {
        "master_offsets": np.array([0, 1, 2, 3]),
        "master_rows": np.array([0, 0, 2]),
        "master_dual_coefficients": np.array([1, np.exp(-0.4j), 1], np.complex128),
    }
    assert literal_expansion(lit, 3)[1, 0] == np.exp(0.4j)
    lit["master_offsets"][-1] = 4
    with pytest.raises(ValueError, match="inventory"):
        literal_expansion(lit, 3)


def test_complex_nonhermitian_augmented_identity_nonzero_port():
    rng = np.random.default_rng(6)
    n = 5
    nm = 40
    V = rng.normal(size=(n, n)) + 1j * rng.normal(size=(n, n))
    C = rng.normal(size=(n, nm)) + 1j * rng.normal(size=(n, nm))
    D = rng.normal(size=(nm, n)) + 1j * rng.normal(size=(nm, n))

    class Boundary:
        layout = type("Layout", (), {"rows": n})()
        modes = tuple(range(nm))

        def apply(self, x, adjoint=False):
            return D.conjugate().T @ (C.conjugate().T @ x) if adjoint else C @ (D @ x)

        def recover(self, x):
            return D @ x

        def modal_rhs(self, x):
            return C @ x

    adapter = NativeBoundaryAdapter(
        csr_matrix(np.eye(n, dtype=np.complex128)),
        np.arange(n),
        n,
        n,
        [],
        identity="nonHermitian",
    )
    wrapper = CoupledNativeBoundaryAction(
        adapter,
        Boundary(),
        lambda x, adjoint=False: V.conjugate().T @ x if adjoint else V @ x,
    )
    x = rng.normal(size=n) + 1j * rng.normal(size=n)
    f = rng.normal(size=n) + 1j * rng.normal(size=n)
    alpha = rng.normal(size=nm) + 1j * rng.normal(size=nm)
    g = rng.normal(size=nm) + 1j * rng.normal(size=nm)
    fe, port = wrapper.augmented(x, alpha)
    assert np.allclose(f - C @ g - wrapper.apply(x), (f - fe) - C @ (g - port))
    assert np.allclose(wrapper.apply(x, adjoint=True), (V + C @ D).conjugate().T @ x)
    assert np.array_equal(wrapper.hp_apply(g), g)
    assert wrapper.original_hp_kind.startswith("IMPLICIT_IDENTITY")


def test_affine_recovery_error_removes_internal_particular_nonzero_ports():
    from src.solvers.p6_cell_condensed_action import condense_physical_cell_blocks

    rng = np.random.default_rng(7)
    nt, ni, nm = 3, 2, 40
    V = (
        rng.normal(size=(nt + ni, nt + ni))
        + 1j * rng.normal(size=(nt + ni, nt + ni))
        + 4 * np.eye(nt + ni)
    )
    B = rng.normal(size=(nt + ni, nm)) + 1j * rng.normal(size=(nt + ni, nm))
    D = rng.normal(size=(nm, nt + ni)) + 1j * rng.normal(size=(nm, nt + ni))
    model = condense_physical_cell_blocks(
        Vii=V[nt:, nt:],
        Vit=V[nt:, :nt],
        Vti=V[:nt, nt:],
        Vtt=V[:nt, :nt],
        Bi=B[nt:],
        Bt=B[:nt],
        Di=D[:, nt:],
        Dt=D[:, :nt],
        H=np.eye(nm, dtype=np.complex128),
    )
    fi = rng.normal(size=ni) + 1j * rng.normal(size=ni)
    a = rng.normal(size=nt + nm) + 1j * rng.normal(size=nt + nm)
    b = rng.normal(size=nt + nm) + 1j * rng.normal(size=nt + nm)

    def recover(z):
        return model.solve_interior(fi - V[nt:, :nt] @ z[:nt] - B[nt:] @ z[nt:])

    assert np.allclose(
        recover(a) - recover(b), recover(a - b) - recover(np.zeros_like(a))
    )
    assert not np.allclose(recover(a) - recover(b), recover(a - b))
    assert np.allclose(
        V[nt:, nt:] @ recover(a) + V[nt:, :nt] @ a[:nt] + B[nt:] @ a[nt:], fi
    )


@pytest.mark.parametrize(
    "name",
    ["evidence", "native_adapter", "coupled_recovery", "integration_check", "consumer"],
)
def test_actual_one_run_dat_registry_does_not_reopen_old_window(name):
    from src.io.port_preparation import load_native_integration
    from src.solvers.native_integration_scope import ROOT

    spec = load_native_integration(
        ROOT / "input/task042_neural_coarse_inverse" / ("v39_" + name + ".dat")
    )
    assert spec.derived["preparation_scope"] == "v39"
    assert spec.derived["target_solve"] is False
    assert spec.execution["mpi_size"] == 1


def test_new_window_deadline_and_closed_parent_isolation(tmp_path):
    import json
    import time
    from datetime import datetime, timezone

    from src.solvers.native_integration_scope import IntegrationWindow

    folder = tmp_path / "v39"
    folder.mkdir()
    boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    start = {
        "start_utc": datetime.now(timezone.utc).isoformat(),
        "start_monotonic": time.monotonic() - 3,
        "boot_id": boot,
        "total_limit_seconds": 86400,
        "heavy_limit_seconds": 82800,
    }
    (folder / "window.json").write_text(json.dumps(start))
    win = IntegrationWindow(
        folder,
        label="V39",
        total=7200,
        component=5400,
        auxiliary=600,
        probe=60,
        reserve=180,
        bootstrap=3,
    )
    assert 1190 < win.remaining("COUPLED") <= 1200
    book = win.ledger()
    book["closed"] = True
    win.LEDGER_PATH.write_text(json.dumps(book))
    with pytest.raises(RuntimeError, match="closed"):
        win.remaining("ADAPTER")
