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


def test_tensor_matches_independent_complete_facet_sum():
    import basix

    p = FacetPolynomial(element())
    l = BoundaryLayout(
        [0.0, 0.6, 1.5], [0.0, 0.8, 1.9], p, (np.exp(0.3j), np.exp(-0.2j))
    )
    action = DirectionalBoundaryAction(l, modes(), 30)
    rng = np.random.default_rng(423801)
    x = rng.normal(size=l.rows) + 1j * rng.normal(size=l.rows)
    y = rng.normal(size=l.rows) + 1j * rng.normal(size=l.rows)
    rule, w = basix.make_quadrature(basix.CellType.quadrilateral, 60)
    C = np.zeros((l.rows, len(modes())), complex)
    D = np.zeros((len(modes()), l.rows), complex)
    for m, r in enumerate(modes()):
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
                rows = l.maps[side][i, j]
                ph = l.weights[side][i, j]
                np.add.at(
                    C[:, m],
                    rows,
                    (integral @ (-np.asarray(r["traction_vector"][:2]))) * ph.conj(),
                )
                np.add.at(
                    D[m], rows, (integral @ np.asarray(r["e_vector"][:2])).conj() * ph
                )
    H = np.array([r["projection_denominator"] for r in modes()])
    A = C @ (D / H[:, None])
    np.testing.assert_allclose(action.recover(x), D @ x / H, rtol=1e-10, atol=1e-10)
    np.testing.assert_allclose(action.apply(x), A @ x, rtol=1e-10, atol=1e-10)
    np.testing.assert_allclose(
        action.apply(y, adjoint=True), A.conj().T @ y, rtol=1e-10, atol=1e-10
    )
    np.testing.assert_allclose(
        action.modal_rhs(np.ones(len(H))), C @ np.ones(len(H)), rtol=1e-10, atol=1e-10
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
