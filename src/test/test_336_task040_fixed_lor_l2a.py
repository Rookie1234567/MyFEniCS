"""Focused Task040 L2a cell-local p6/LOR trace bridge checks."""

from __future__ import annotations

import numpy as np
import pytest

from src.solvers.hcurl_fixed_lor_cell_bridge import (
    FixedP6LORCellBridge,
    build_fixed_p6_lor_cell_bridge,
)


@pytest.fixture(scope="module")
def bridge() -> FixedP6LORCellBridge:
    action = build_fixed_p6_lor_cell_bridge(
        (0.8, 1.1, 1.4),
        curl_coefficient=1.0 + 0.0j,
        mass_coefficient=2.5 - 0.2j,
        cell_info=134743045,
    )
    try:
        yield action
    finally:
        action.destroy()


def _probe(size: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.normal(size=size) + 1j * rng.normal(size=size)


def _relative(actual: np.ndarray, expected: np.ndarray) -> float:
    return float(
        np.linalg.norm(actual - expected)
        / max(float(np.linalg.norm(expected)), np.finfo(float).tiny)
    )


def test_l2a_partition_support_and_material_contract(
    bridge: FixedP6LORCellBridge,
) -> None:
    audit = bridge.audit
    assert audit["schema_version"] == "task040.fixed-lor.l2a.v1"
    assert audit["status"] == "fixed_p6_lor_cell_trace_bridge_qualified"
    assert audit["scope"] == "component_mechanism_only_not_5nm_signal"
    assert audit["pass"]
    assert audit["cell"] == {
        "widths": (0.8, 1.1, 1.4),
        "cell_info": 134743045,
        "material_class": "axis_aligned_affine_isotropic",
        "curl_coefficient": (1.0, 0.0),
        "mass_coefficient": (2.5, -0.2),
        "ordinary_defaults_unchanged": True,
        "physics_unchanged": True,
    }
    assert audit["partitions"]["p6_trace"] == 432
    assert audit["partitions"]["p6_interior"] == 450
    assert audit["partitions"]["p6_trace_unique"]
    assert audit["partitions"]["p6_interior_unique"]
    assert audit["partitions"]["p6_disjoint_complete"]
    assert audit["partitions"]["lor_boundary"] == 432
    assert audit["partitions"]["lor_interior"] == 450
    assert audit["partitions"]["lor_disjoint_complete"]
    assert audit["checks"]["cell_mapping"]
    assert audit["checks"]["reference_transfer"]
    assert audit["orientation"]["nonzero_cell_info"]
    assert audit["orientation"]["changed_entries_max"] > 0.0
    assert audit["orientation"]["trace_interior_mixing_max"] <= 2.0e-12
    assert audit["transfer"]["R1_shape"] == (882, 882)
    assert audit["transfer"]["trace_shape"] == (432, 432)
    assert audit["transfer"]["trace_rank"] == 432
    assert audit["transfer"]["boundary_p6_interior_max_abs"] <= 2.0e-12
    assert audit["operators"]["p6_raw_shape"] == (882, 882)
    assert audit["operators"]["lor_raw_shape"] == (882, 882)
    assert audit["operators"]["p6_trace_schur_shape"] == (432, 432)
    assert audit["operators"]["lor_trace_schur_shape"] == (432, 432)
    assert audit["operators"]["max_local_factor_rows"] == 450
    assert np.isfinite(
        audit["diagnostics"]["fine_vs_mapped_trace_relative"]
    )
    assert audit["forbidden_objects"] == {
        "global_F": False,
        "global_AIJ": False,
        "global_factor": False,
        "numeric_allgather": False,
        "full_basis_replication": False,
        "petsc": False,
        "mpi": False,
        "dolfinx": False,
    }
    assert audit["lifecycle"]["full_cell_transient_released_before_return"]
    assert audit["lifecycle"]["retained_trace_bridge_bytes"] > 0
    p = audit["partitions"]
    t = audit["transfer"]
    o = audit["orientation"]
    s = audit["solve_audit"]
    d = audit["diagnostics"]
    q = audit["operators"]
    l = audit["lifecycle"]
    p6_trace, p6_interior = p["p6_trace"], p["p6_interior"]
    lor_boundary, lor_interior = p["lor_boundary"], p["lor_interior"]
    cross = t["boundary_p6_interior_max_abs"]
    mixing = o["trace_interior_mixing_max"]
    tat = o["tensor_TAT_relative"]
    p6_solve = s["p6_interior_relative"]
    lor_solve = s["lor_interior_relative"]
    mapped_solve = s["mapped_trace_relative"]
    diagnostic = d["fine_vs_mapped_trace_relative"]
    factor_rows = q["max_local_factor_rows"]
    retained = l["retained_trace_bridge_bytes"]
    transient = l["selected_transient_array_bytes_not_peak"]
    wall = audit["wall_seconds"]
    print(
        "TASK040_L2A "
        f"p6_trace={p6_trace} p6_interior={p6_interior} "
        f"lor_boundary={lor_boundary} lor_interior={lor_interior} "
        f"cross_block_max_abs={cross:.6e} orientation_mixing_max={mixing:.6e} "
        f"TAT_relative={tat:.6e} "
        f"p6_interior_solve_relative={p6_solve:.6e} "
        f"lor_interior_solve_relative={lor_solve:.6e} "
        f"mapped_trace_solve_relative={mapped_solve:.6e} "
        f"fine_vs_mapped_diagnostic_relative={diagnostic:.6e} "
        f"max_local_factor_rows={factor_rows} retained_trace_bridge_bytes={retained} "
        f"selected_transient_array_bytes_not_peak={transient} "
        f"builder_wall_seconds={wall:.6f}"
    )


def test_l2a_independent_actions_solve_and_destroy(
    bridge: FixedP6LORCellBridge,
) -> None:
    x = _probe(432, 3361)
    y = _probe(432, 3362)
    assert bridge.fine_trace_operator is not None
    assert bridge.lor_trace_operator is not None
    assert bridge.trace_transfer is not None
    fine_expected = bridge.fine_trace_operator @ x
    mapped_expected = bridge.trace_transfer.conj().T @ (
        bridge.lor_trace_operator @ (bridge.trace_transfer @ x)
    )
    assert _relative(bridge.apply_fine_trace_schur(x), fine_expected) <= 1.0e-10
    assert _relative(bridge.apply_mapped_lor_trace(x), mapped_expected) <= 1.0e-10
    assert _relative(
        bridge.apply_fine_trace_schur(x), bridge.apply_fine_trace_schur(x)
    ) <= 1.0e-10
    assert _relative(
        bridge.apply_mapped_lor_trace(x), bridge.apply_mapped_lor_trace(x)
    ) <= 1.0e-10
    alpha, beta = 0.7 - 0.2j, -0.4 + 0.3j
    assert _relative(
        bridge.apply_fine_trace_schur(alpha * x + beta * y),
        alpha * bridge.apply_fine_trace_schur(x)
        + beta * bridge.apply_fine_trace_schur(y),
    ) <= 1.0e-10
    assert _relative(
        bridge.apply_mapped_lor_trace(alpha * x + beta * y),
        alpha * bridge.apply_mapped_lor_trace(x)
        + beta * bridge.apply_mapped_lor_trace(y),
    ) <= 1.0e-10
    rhs = mapped_expected
    expected_solution = np.linalg.solve(
        bridge.trace_transfer.conj().T
        @ bridge.lor_trace_operator
        @ bridge.trace_transfer,
        rhs,
    )
    solution = bridge.solve_mapped_lor_trace(rhs)
    assert _relative(solution, expected_solution) <= 1.0e-10
    assert _relative(bridge.apply_mapped_lor_trace(solution), rhs) <= 1.0e-10
    assert np.isfinite(
        [
            bridge.audit["solve_audit"]["p6_interior_relative"],
            bridge.audit["solve_audit"]["lor_interior_relative"],
            bridge.audit["solve_audit"]["mapped_trace_relative"],
        ]
    ).all()
    assert max(
        bridge.audit["solve_audit"]["p6_interior_relative"],
        bridge.audit["solve_audit"]["lor_interior_relative"],
        bridge.audit["solve_audit"]["mapped_trace_relative"],
    ) <= 1.0e-10
    bridge.destroy()
    assert bridge.destroyed
    with pytest.raises(RuntimeError, match="destroyed"):
        bridge.apply_mapped_lor_trace(x)
