"""Coverage negatives, real tensor workflow and V38 namespace isolation."""

import copy

import numpy as np
import pytest

from benchmarks.check_boundary_witness import require_complete_coverage
from src.solvers.directional_boundary import (
    BoundaryLayout,
    DirectionalBoundaryAction,
    FacetPolynomial,
)


def element():
    import basix.ufl

    return basix.ufl.element("N1curl", "hexahedron", 6).basix_element


def modes():
    rows = []
    for side in ("bottom", "top"):
        for j in range(3):
            rows.append(
                {
                    "side": side,
                    "k_vector": [0.2 + j * 0.13, -0.17 + j * 0.09, 0.31],
                    "reference_plane_nm": 0 if side == "bottom" else 2.0,
                    "e_vector": [1 + 0.2j, 0.3 - 0.1j, 0],
                    "traction_vector": [0.7 - 0.8j, -0.9 + 0.2j, 0],
                    "projection_denominator": 1.3 + j,
                }
            )
    return rows


@pytest.mark.parametrize("side_only", [None, "top", "bottom"])
def test_tensor_matches_independent_complete_facet_sum(side_only):
    import basix

    p = FacetPolynomial(element())
    l = BoundaryLayout(
        [0.0, 0.6, 1.5], [0.0, 0.8, 1.9], p, (np.exp(0.3j), np.exp(-0.2j))
    )
    rows = [r for r in modes() if side_only is None or r["side"] == side_only]
    action = DirectionalBoundaryAction(l, rows, 30)
    rng = np.random.default_rng(423801)
    x = rng.normal(size=l.rows) + 1j * rng.normal(size=l.rows)
    y = rng.normal(size=l.rows) + 1j * rng.normal(size=l.rows)
    rule, w = basix.make_quadrature(basix.CellType.quadrilateral, 60)
    C = np.zeros((l.rows, len(rows)), complex)
    D = np.zeros((len(rows), l.rows), complex)
    for m, r in enumerate(rows):
        side = r["side"]
        z = 0 if side == "bottom" else 1
        tab = p.element.tabulate(0, np.column_stack((rule, np.full(len(rule), z))))[0][
            :, p.active[side], :2
        ]
        for i in range(l.nx):
            for j in range(l.ny):
                dx = l.x[i + 1] - l.x[i]
                dy = l.y[j + 1] - l.y[j]
                pts = np.column_stack(
                    (
                        l.x[i] + dx * rule[:, 0],
                        l.y[j] + dy * rule[:, 1],
                        np.full(len(rule), r["reference_plane_nm"]),
                    )
                )
                integral = np.einsum(
                    "q,qjc->jc", w * np.exp(1j * (pts @ r["k_vector"])), tab
                ) * [dy, dx]
                row_ids = l.maps[side][i, j]
                ph = l.weights[side][i, j]
                np.add.at(
                    C[:, m],
                    row_ids,
                    (integral @ (-np.asarray(r["traction_vector"][:2]))) * ph.conj(),
                )
                np.add.at(
                    D[m],
                    row_ids,
                    (integral @ np.asarray(r["e_vector"][:2])).conj() * ph,
                )
    H = np.array([r["projection_denominator"] for r in rows])
    A = C @ (D / H[:, None])
    np.testing.assert_allclose(action.recover(x), D @ x / H, rtol=1e-10, atol=1e-10)
    np.testing.assert_allclose(action.apply(x), A @ x, rtol=1e-10, atol=1e-10)
    np.testing.assert_allclose(
        action.apply(y, adjoint=True), A.conj().T @ y, rtol=1e-10, atol=1e-10
    )
    np.testing.assert_allclose(
        action.modal_rhs(np.ones(len(H), dtype=np.complex128)),
        C @ np.ones(len(H)),
        rtol=1e-10,
        atol=1e-10,
    )
    assert 0 <= action.stats["project_seconds"] < 600
    assert action.cache_bytes < 64 * 2**20 and l.rows == 2 * 2 * 6**2 * 2 * 2


@pytest.mark.parametrize("fault", ["q", "action", "duplicate", "identity"])
def test_complete_checker_rejects_missing_inventory(fault):
    plan = {
        "patches": [{"name": "a", "cells": [1]}, {"name": "b", "cells": [2]}],
        "quadrature_degrees": [15, 30, 60],
    }
    result = {
        "patches": [
            {
                "description": p,
                "q_records": [{"q": q} for q in (15, 30, 60)],
                "component": {"witness": {}},
            }
            for p in copy.deepcopy(plan["patches"])
        ]
    }
    require_complete_coverage(plan, result)
    if fault == "q":
        result["patches"][0]["q_records"].pop()
    if fault == "action":
        result["patches"][0]["component"].clear()
    if fault == "duplicate":
        result["patches"][1] = copy.deepcopy(result["patches"][0])
    if fault == "identity":
        result["patches"][0]["description"]["cells"] = [7]
    with pytest.raises(ValueError):
        require_complete_coverage(plan, result)


def test_shared_plans_are_not_copied_per_mode():
    import hashlib

    from src.solvers.bounded_port_provider import json_bytes
    from src.test.test_boundary_witness import TileSource, action

    s = TileSource()
    s.shared_tile_plans = {"surface": ("face-a", "face-b")}
    h = hashlib.sha256(json_bytes(s.shared_tile_plans)).hexdigest()
    for r in s.rows:
        del r["tile_ids"]
        r.update(tile_plan_key="surface", tile_plan_sha256=h)
    a = action(s)
    assert len({id(p) for p in a.plans}) == 1
    assert not a.apply(np.zeros(9, complex)).any()


def test_v38_dispatch_and_closed_windows_not_read():
    from pathlib import Path

    from src.io.port_preparation import load_preparation

    for f in Path("input/task042_neural_coarse_inverse").glob("v38_*.dat"):
        s = load_preparation(f)
        assert (
            s.derived["preparation_scope"] == "v38"
            and s.derived["target_solve"] is False
        )


def test_jit_archive_v38_exact_readback_and_scope():
    import gzip
    import tempfile
    from pathlib import Path

    from benchmarks.archive_jit_cache import archive

    root = Path("tmp/task042/v38")
    with tempfile.TemporaryDirectory(dir=root) as path:
        cache = Path(path) / "cache"
        cache.mkdir()
        (cache / "a.c").write_bytes(b"generated q30" * 100)
        (cache / "a.so").write_bytes(b"loaded so")
        result = archive(
            cache,
            Path(path) / "jit_archive_initial",
            namespace="v38",
            suffixes=(".c", ".o"),
        )
        assert result["members"][0]["lossless_readback"]
        assert (
            gzip.decompress(Path(result["members"][0]["archive"]).read_bytes())
            == b"generated q30" * 100
        )
        assert (cache / "a.so").exists() and not (cache / "a.c").exists()
        from benchmarks.archive_jit_cache import restore_cached_sources

        restore_cached_sources(cache, Path(path))
        assert (cache / "a.c").read_bytes() == b"generated q30" * 100
        second = archive(
            cache,
            Path(path) / "jit_archive_second",
            namespace="v38",
            suffixes=(".c", ".o"),
            reuse_root=Path(path),
        )
        assert second["members"][0]["archive"] == result["members"][0]["archive"]
        assert second["members"][0]["reused_immutable_archive"]
        with pytest.raises(ValueError, match="scope"):
            archive(cache, Path(path) / "bad", namespace="v39")


def test_lossless_alias_receipt_and_negative_cycle(tmp_path):
    from benchmarks.check_boundary_witness import read_arrays
    from src.solvers.port_component_study import array_file

    a = np.array([1 + 2j, 3 - 0.1j], np.complex128)
    receipt = array_file(
        tmp_path / "encoded.npz", compressed=True, deduplicate=True, a=a, b=a.copy()
    )
    assert receipt["aliases"] == {"b": "a"}
    np.testing.assert_array_equal(read_arrays(receipt)["b"], a)
    bad = copy.deepcopy(receipt)
    bad["aliases"] = {"a": "b", "b": "a"}
    with pytest.raises(ValueError, match="alias inventory"):
        read_arrays(bad)


def test_new_action_inventory_rejects_missing_q():
    from benchmarks.check_boundary_structure import require_action_inventory

    d = {
        f"q{q}_{label}_{kind}": np.zeros(
            2 if kind == "amplitudes" else 3, np.complex128
        )
        for q in (30, 60)
        for label in ("a", "b")
        for kind in ("amplitudes", "forward", "adjoint", "modal", "linear", "zero")
    }
    d.update(H_errors=np.zeros(2), unit_power_errors=np.zeros(2))
    inp = {
        "x": np.zeros(3, np.complex128),
        "y": np.zeros(3, np.complex128),
        "alpha": np.zeros(2, np.complex128),
    }
    require_action_inventory(d, inp, 3, 2)
    del d["q60_a_forward"]
    with pytest.raises(ValueError, match="inventory"):
        require_action_inventory(d, inp, 3, 2)


def test_active_worker_budget_counts_current_wall_and_rejects_other_actor(
    tmp_path, monkeypatch
):
    from src.solvers.boundary_structure_scope import StructureWindow

    w = StructureWindow(tmp_path, total=7200, component=5400, reserve=180)
    active = {
        "role": "COMPONENT",
        "folder": str(tmp_path / "worker"),
        "before_clock": {"observed_monotonic": 100.0},
    }
    monkeypatch.setenv("TASK042_V36_AUX_DIRECTORY", active["folder"])
    monkeypatch.setattr(
        w,
        "require_live",
        lambda: {"observed_monotonic": 120.0, "heavy_remaining_seconds": 8000.0},
    )
    monkeypatch.setattr(w, "charged_wall", lambda: 300.0)
    book = {
        "active": active,
        "closed": False,
        "runs": [{"role": "BRIDGE", "elapsed_seconds": 200.0}],
    }
    monkeypatch.setattr(w, "ledger", lambda: book)
    assert w.active_remaining("COMPONENT") == 5180.0
    monkeypatch.setenv("TASK042_V36_AUX_DIRECTORY", str(tmp_path / "other"))
    with pytest.raises(RuntimeError, match="identity"):
        w.active_remaining("COMPONENT")
    monkeypatch.setenv("TASK042_V36_AUX_DIRECTORY", active["folder"])
    book["closed"] = True
    with pytest.raises(RuntimeError, match="identity"):
        w.active_remaining("COMPONENT")


def test_modal_physics_is_recomputed_not_copied_from_saved_status():
    from benchmarks.check_boundary_structure import modal_physics

    rows = [
        {
            "side": side,
            "k_vector": [0, 0, k],
            "e_vector": [1, 0, 0],
            "reference_plane_nm": 0,
            "projection_denominator": 4,
            "power_at_reference_unit_amplitude": 2,
        }
        for side, k in (("top", 2), ("bottom", -2))
    ]
    h, p = modal_physics(rows, area=4, k0=2, mu_r=1)
    assert not h.any() and not p.any()
    rows[0]["projection_denominator"] = 4.1
    rows[1]["power_at_reference_unit_amplitude"] = 2.1
    h, p = modal_physics(rows, area=4, k0=2, mu_r=1)
    assert max(h) > 1e-10 and max(p) > 1e-10
    rows[0]["projection_denominator"] = 0
    with pytest.raises(ValueError, match="modal H"):
        modal_physics(rows, area=4, k0=2, mu_r=1)


def test_evaluate_freezes_counter_snapshot_before_next_input():
    from src.solvers.boundary_structure_study import evaluate

    p = FacetPolynomial(element())
    l = BoundaryLayout([0.0, 1.0], [0.0, 1.0], p, (1, 1))
    a = DirectionalBoundaryAction(l, modes(), 30)
    rng = np.random.default_rng(423801)
    x = rng.normal(size=l.rows) + 1j * rng.normal(size=l.rows)
    _, first = evaluate(a, x, x, np.ones(len(modes()), complex))
    snapshot = first["stats"].copy()
    evaluate(a, x, x, np.ones(len(modes()), complex))
    assert first["stats"] == snapshot
    assert a.stats["project_calls"] == 2 * snapshot["project_calls"]
    assert a.stats["scatter_calls"] == 2 * snapshot["scatter_calls"]
