"""Pure contracts for the custom h3star owner-packet runtime."""

from __future__ import annotations

import ast
from types import SimpleNamespace
from pathlib import Path

import numpy as np
import pytest

from src.solvers import fullspace_lor_memory_hierarchy_runtime as s5_runtime
from src.solvers import fullspace_lor_nested_hmg_runtime as nested_runtime
from src.solvers.fullspace_lor_nested_hmg import (
    H1STAR_GLL_INDICES,
    H3STAR_GLL_INDICES,
    H6_GLL_INDICES,
)
from src.solvers.fullspace_lor_transfer import _gll_nodes
from src.test.test_312_task038_lor_hierarchy_capacity import (
    _FakeMatrix,
    _FakeS5Level,
    _fake_local_transfer,
)


def _fake_extension():
    foundation_matrix = _FakeMatrix("foundation-low")
    levels = {
        "h6": _FakeS5Level(6, 882, 2, foundation_matrix),
        "h3star": _FakeS5Level(3, 144, 2, _FakeMatrix("h3star")),
        "h1star": _FakeS5Level(1, 12, 2, _FakeMatrix("h1star")),
    }
    for key, count in (("h6", 6), ("h3star", 3), ("h1star", 1)):
        levels[key].level_key = key
        levels[key].subinterval_count = count
    local = SimpleNamespace(
        h6_to_h3star=_fake_local_transfer(6, 3),
        h3star_to_h1star=_fake_local_transfer(3, 1),
    )
    transfers = (
        s5_runtime._OwnerPacketTransfer(
            levels["h6"],
            levels["h3star"],
            local.h6_to_h3star,
            allowed_pairs=nested_runtime.NESTED_HMG_PAIRS,
            route_schema=nested_runtime.NESTED_HMG_RUNTIME_SCHEMA,
            pair_key=("h6", "h3star"),
        ),
        s5_runtime._OwnerPacketTransfer(
            levels["h3star"],
            levels["h1star"],
            local.h3star_to_h1star,
            allowed_pairs=nested_runtime.NESTED_HMG_PAIRS,
            route_schema=nested_runtime.NESTED_HMG_RUNTIME_SCHEMA,
            pair_key=("h3star", "h1star"),
        ),
    )
    foundation = SimpleNamespace(low_matrix=foundation_matrix)
    extension = nested_runtime.NestedHmgHierarchyExtension(
        foundation, levels["h6"], levels["h3star"], levels["h1star"], *transfers
    )
    return extension, foundation, levels


def test_custom_axes_are_exact_nested_subsets_not_standard_p3() -> None:
    p6 = np.asarray(_gll_nodes(6), dtype=np.float64)
    assert nested_runtime._nested_indices("h6") == H6_GLL_INDICES
    assert nested_runtime._nested_indices("h3star") == H3STAR_GLL_INDICES
    assert nested_runtime._nested_indices("h1star") == H1STAR_GLL_INDICES
    np.testing.assert_array_equal(
        nested_runtime._nested_axis(np.asarray([0.0, 1.0]), "h3star"),
        p6[list(H3STAR_GLL_INDICES)],
    )
    np.testing.assert_array_equal(
        nested_runtime._nested_axis(np.asarray([0.0, 1.0]), "h1star"),
        p6[list(H1STAR_GLL_INDICES)],
    )
    h3_metadata = nested_runtime._TopologyOnlyNestedTransfer("h3star")
    h1_metadata = nested_runtime._TopologyOnlyNestedTransfer("h1star")
    assert h3_metadata.subinterval_count == 3
    assert h3_metadata.edge_count == 144
    assert h1_metadata.subinterval_count == 1
    assert h1_metadata.edge_count == 12
    np.testing.assert_array_equal(h3_metadata.nodes, p6[list(H3STAR_GLL_INDICES)])
    np.testing.assert_array_equal(h1_metadata.nodes, p6[list(H1STAR_GLL_INDICES)])
    assert not np.array_equal(p6[list(H3STAR_GLL_INDICES)], _gll_nodes(3))
    axes = nested_runtime._nested_axes(
        (np.asarray([0.0, 1.0]),) * 3, "h3star"
    )
    assert all(np.array_equal(axis, axes[0]) for axis in axes)


def test_legacy_defaults_and_nested_bridge_shapes_are_separate() -> None:
    assert s5_runtime.S5_LEVELS == (6, 3, 1)
    assert s5_runtime.S5_PAIRS == ((6, 3), (3, 1))
    assert nested_runtime.NESTED_HMG_LEVELS == ("h6", "h3star", "h1star")
    assert nested_runtime.NESTED_HMG_PAIRS == (
        ("h6", "h3star"),
        ("h3star", "h1star"),
    )
    extension, _foundation, levels = _fake_extension()
    assert set(extension.levels) == {"h6", "h3star", "h1star"}
    assert extension.transfers[("h6", "h3star")].audit["local_map"]["edge_rows"] == 882
    assert extension.transfers[("h6", "h3star")].audit["local_map"]["edge_cols"] == 144
    assert extension.transfers[("h3star", "h1star")].audit["local_map"]["edge_rows"] == 144
    assert extension.transfers[("h3star", "h1star")].audit["local_map"]["edge_cols"] == 12
    assert extension.audit["h3star_standard_polynomial_space"] is False
    assert extension.audit["global_transfer_matrix"] is False
    assert extension.audit["numeric_allgather"] is False
    assert extension.audit["smoother_built"] is False
    assert extension.audit["ksp_created"] is False
    assert extension.pair_levels(("h6", "h3star"))[0] is levels["h6"]
    with pytest.raises(ValueError, match="unsupported nested HMG pair"):
        extension.pair_levels(("h6", "h1star"))
    extension.destroy()


@pytest.mark.parametrize(
    ("pair", "coarse_size", "fine_size"),
    [
        (("h6", "h3star"), 288, 1764),
        (("h3star", "h1star"), 24, 288),
    ],
)
def test_nested_owner_bridge_primal_adjoint_into_and_destroy(
    pair, coarse_size, fine_size
) -> None:
    extension, foundation, levels = _fake_extension()
    source = np.arange(coarse_size, dtype=np.float64).astype(np.complex128) + 0.25j
    source_before = source.copy()
    primal = np.empty(fine_size, dtype=np.complex128)
    extension.apply_primal_into(pair, source, primal)
    fine_dual = np.arange(fine_size, dtype=np.float64).astype(np.complex128) - 0.5j
    fine_before = fine_dual.copy()
    coarse_dual = np.empty(coarse_size, dtype=np.complex128)
    extension.apply_adjoint_into(pair, fine_dual, coarse_dual)
    assert np.all(np.isfinite(primal)) and np.all(np.isfinite(coarse_dual))
    assert np.array_equal(source, source_before)
    assert np.array_equal(fine_dual, fine_before)
    repeat_primal = np.empty_like(primal)
    repeat_dual = np.empty_like(coarse_dual)
    extension.apply_primal_into(pair, source, repeat_primal)
    extension.apply_adjoint_into(pair, fine_dual, repeat_dual)
    np.testing.assert_array_equal(repeat_primal, primal)
    np.testing.assert_array_equal(repeat_dual, coarse_dual)
    assert abs(np.vdot(primal, fine_dual) - np.vdot(source, coarse_dual)) <= 1.0e-12
    with pytest.raises(ValueError, match="unsupported nested HMG pair"):
        extension.apply_primal_into(("h6", "h1star"), source, primal)
    extension.destroy()
    assert levels["h3star"].destroy_count == 1
    assert levels["h1star"].destroy_count == 1
    assert levels["h6"].destroy_count == 1
    assert foundation.low_matrix.destroy_count == 0
    extension.destroy()
    assert levels["h3star"].destroy_count == 1


def test_from_foundation_builder_calls_only_fixed_levels(monkeypatch) -> None:
    foundation_matrix = _FakeMatrix("foundation-low")
    foundation = SimpleNamespace(
        low_matrix=foundation_matrix,
        cfg=SimpleNamespace(nedelec_degree=6, mesh_target_size=10.0, lambda0=13.5),
    )
    calls = []
    levels = {
        "h6": _FakeS5Level(6, 882, 2, foundation_matrix),
        "h3star": _FakeS5Level(3, 144, 2, _FakeMatrix("h3star")),
        "h1star": _FakeS5Level(1, 12, 2, _FakeMatrix("h1star")),
    }
    for key, count in (("h6", 6), ("h3star", 3), ("h1star", 1)):
        levels[key].level_key = key
        levels[key].subinterval_count = count
    local = SimpleNamespace(
        h6_to_h3star=_fake_local_transfer(6, 3),
        h3star_to_h1star=_fake_local_transfer(3, 1),
    )
    monkeypatch.setattr(
        nested_runtime,
        "_stage4_parent_axes",
        lambda _foundation: calls.append("axes") or (),
    )
    monkeypatch.setattr(
        nested_runtime,
        "_build_level6_for_nested",
        lambda _foundation: calls.append("h6") or levels["h6"],
    )
    monkeypatch.setattr(
        nested_runtime,
        "_build_nested_level",
        lambda _foundation, key, _axes: calls.append(key) or levels[key],
    )
    monkeypatch.setattr(
        nested_runtime,
        "build_nested_lor_edge_hmg",
        lambda: calls.append("local") or local,
    )
    extension = nested_runtime.build_nested_hmg_extension_from_foundation(foundation)
    assert calls == ["axes", "h6", "h3star", "h1star", "local"]
    extension.destroy()
    assert levels["h3star"].destroy_count == 1
    assert levels["h1star"].destroy_count == 1
    assert foundation_matrix.destroy_count == 0


def test_nested_runtime_has_lazy_heavy_boundary() -> None:
    path = Path(__file__).parents[1] / "solvers" / "fullspace_lor_nested_hmg_runtime.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = [
        node.module
        for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.module
    ]
    assert not any(name in {"mpi4py", "petsc4py", "dolfinx"} for name in imports)
    assert "build_local_lor_transfer(3)" not in source
    assert "_refined_axis(" not in source
    assert "allgather(" not in source
    assert "build_nested_hmg_extension_from_foundation" in source
