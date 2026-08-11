from __future__ import annotations

import json
from types import SimpleNamespace

import numpy as np
import pytest

import benchmarks.run_task037_extra_h2b as runner
from src.solvers.hcurl_h2b_block_smoother import (
    discover_h2b_p0_touching_cells,
    factorize_h2b_p0_patch,
    group_h2b_p0_touching_cells_by_class,
    measure_h2b_p0_patch_direction,
    _p0_lu_reconstruction,
    select_h2b_p0_class,
    stream_h2b_p0_patch,
)
from src.solvers.hcurl_r2_constrained_local_block import H2AR2CellExpansion
from src.solvers.hcurl_r2_constrained_local_block import _pattern_payload, _pattern_sha256


def _class(class_id: int, cells: int, *, constrained: bool = False):
    return {
        "class_id": class_id,
        "cell_count": cells,
        "constraint_pattern_entry_count": 1 if constrained else 0,
        "constraint_pattern_kinds": ["edge:x"] if constrained else [],
        "class_key_sha256": f"{class_id + 1:064x}",
        "constraint_pattern_sha256": "a" * 64,
    }


def _identity_expansion(rows: tuple[int, ...]) -> H2AR2CellExpansion:
    offsets = np.arange(len(rows) + 1, dtype=np.int32)
    columns = np.arange(len(rows), dtype=np.int32)
    coefficients = np.ones(len(rows), dtype=np.complex128)
    identity = _pattern_payload(
        nloc=len(rows),
        independent_count=len(rows),
        offsets=offsets,
        column_indices=columns,
        coefficients=coefficients,
    )
    return H2AR2CellExpansion(
        offsets=offsets,
        column_indices=columns,
        coefficients=coefficients,
        independent_global_rows=np.asarray(rows, dtype=np.int64),
        pattern_identity=identity,
        pattern_sha256=_pattern_sha256(identity),
    )


def _constrained_expansion() -> H2AR2CellExpansion:
    offsets = np.asarray((0, 1, 3), dtype=np.int32)
    columns = np.asarray((0, 0, 1), dtype=np.int32)
    coefficients = np.asarray((1.0, 0.5, 1.0), dtype=np.complex128)
    identity = _pattern_payload(
        nloc=2,
        independent_count=2,
        offsets=offsets,
        column_indices=columns,
        coefficients=coefficients,
    )
    return H2AR2CellExpansion(
        offsets=offsets,
        column_indices=columns,
        coefficients=coefficients,
        independent_global_rows=np.asarray((11, 12), dtype=np.int64),
        pattern_identity=identity,
        pattern_sha256=_pattern_sha256(identity),
    )


def _shared_class_expansion(rows: tuple[int, ...]) -> H2AR2CellExpansion:
    offsets = np.asarray((0, 2, 4), dtype=np.int32)
    columns = np.asarray((0, 1, 1, 2), dtype=np.int32)
    coefficients = np.asarray(
        (1.0 + 0.0j, 0.4 + 0.2j, 1.0 + 0.0j, -0.3 + 0.15j),
        dtype=np.complex128,
    )
    identity = _pattern_payload(
        nloc=2,
        independent_count=3,
        offsets=offsets,
        column_indices=columns,
        coefficients=coefficients,
    )
    return H2AR2CellExpansion(
        offsets=offsets,
        column_indices=columns,
        coefficients=coefficients,
        independent_global_rows=np.asarray(rows, dtype=np.int64),
        pattern_identity=identity,
        pattern_sha256=_pattern_sha256(identity),
    )


def test_p0_selects_unique_largest_unconstrained_class_and_rejects_ties():
    selected = select_h2b_p0_class(
        [_class(0, 4), _class(3, 52), _class(2, 39, constrained=True)],
        task037_extra_h2b=True,
    )
    assert selected["class_id"] == 3
    assert selected["cell_count"] == 52
    with pytest.raises(ValueError, match="not unique"):
        select_h2b_p0_class(
            [_class(3, 52), _class(5, 52)], task037_extra_h2b=True
        )
    with pytest.raises(ValueError, match="no unconstrained"):
        select_h2b_p0_class(
            [_class(3, 52, constrained=True)], task037_extra_h2b=True
        )
    missing = _class(3, 52)
    del missing["constraint_pattern_sha256"]
    with pytest.raises(ValueError, match="missing"):
        select_h2b_p0_class([missing], task037_extra_h2b=True)


def test_p0_touching_cells_use_expanded_master_support_and_canonical_order():
    refs = tuple(
        SimpleNamespace(independent_global_rows=np.asarray(rows, dtype=np.int64))
        for rows in ((10, 99), (30, 40), (20, 30))
    )
    assert discover_h2b_p0_touching_cells(
        refs, np.asarray((10, 20, 30), dtype=np.int64), task037_extra_h2b=True
    ) == (0, 1, 2)
    with pytest.raises(ValueError, match="not covered"):
        discover_h2b_p0_touching_cells(
            refs, np.asarray((10, 20, 77), dtype=np.int64), task037_extra_h2b=True
        )


def test_p0_exact_class_stream_reuses_one_proxy_per_group_and_matches_reference():
    refs = tuple(
        SimpleNamespace(
            class_id=class_id,
            independent_global_rows=np.asarray(rows, dtype=np.int64),
        )
        for class_id, rows in (
            (4, (0, 1, 2)),
            (7, (6, 7)),
            (4, (3, 4, 5)),
            (7, (6, 7)),
        )
    )
    touching = (0, 1, 2, 3)
    groups = group_h2b_p0_touching_cells_by_class(
        refs, touching, task037_extra_h2b=True
    )
    assert groups == ((4, (0, 2)), (7, (1, 3)))
    class4_template = _shared_class_expansion((0, 1, 2))
    class7_template = _identity_expansion((0, 1))
    templates = {4: class4_template, 7: class7_template}
    blocks = {
        4: np.asarray(
            ((3.0 + 0.0j, 0.2 + 0.1j), (0.2 - 0.1j, 2.0 + 0.0j)),
            dtype=np.complex128,
            order="C",
        ),
        7: np.asarray(
            ((2.0 + 0.0j, 0.3 - 0.2j), (0.3 + 0.2j, 2.5 + 0.0j)),
            dtype=np.complex128,
            order="C",
        ),
    }

    def expansion_for(class_id, rows):
        template = templates[class_id]
        return H2AR2CellExpansion(
            offsets=template.offsets,
            column_indices=template.column_indices,
            coefficients=template.coefficients,
            independent_global_rows=np.asarray(rows, dtype=np.int64),
            pattern_identity=template.pattern_identity,
            pattern_sha256=template.pattern_sha256,
        )

    grouped_calls = []
    max_live = 0
    live = 0

    def grouped_stream():
        nonlocal live, max_live
        for class_id, ordinals in groups:
            grouped_calls.append((class_id, ordinals[0]))
            proxy = np.array(blocks[class_id], copy=True, order="C")
            live += 1
            max_live = max(max_live, live)
            for ordinal in ordinals:
                yield ordinal, proxy, expansion_for(
                    class_id, refs[ordinal].independent_global_rows
                )
            live -= 1

    reference_calls = []

    def reference_stream():
        for ordinal in touching:
            class_id = refs[ordinal].class_id
            reference_calls.append((class_id, ordinal))
            yield (
                ordinal,
                np.array(blocks[class_id], copy=True, order="C"),
                expansion_for(class_id, refs[ordinal].independent_global_rows),
            )

    patch_rows = np.arange(8, dtype=np.int64)
    grouped = stream_h2b_p0_patch(
        refs, patch_rows, grouped_stream(), task037_extra_h2b=True
    )
    reference = stream_h2b_p0_patch(
        refs, patch_rows, reference_stream(), task037_extra_h2b=True
    )
    relative = np.linalg.norm(
        grouped["matrix"] - reference["matrix"]
    ) / np.linalg.norm(reference["matrix"])
    assert relative <= 1.0e-14
    assert np.allclose(
        grouped["matrix"], grouped["matrix"].conj().T, rtol=0.0, atol=1.0e-14
    )
    assert grouped_calls == [(4, 0), (7, 1)]
    assert reference_calls == [(4, 0), (7, 1), (4, 2), (7, 3)]
    assert max_live == 1
    assert grouped["touching_cell_count"] == 4


def test_p0_streaming_matches_dense_column_reconstruction_and_keeps_patch_only():
    refs = (
        SimpleNamespace(independent_global_rows=np.asarray((10, 11), dtype=np.int64)),
        SimpleNamespace(independent_global_rows=np.asarray((11, 12), dtype=np.int64)),
    )
    expansion0 = _identity_expansion((10, 11))
    expansion1 = _constrained_expansion()
    block0 = np.asarray(
        ((4.0 + 0.0j, 1.0 + 0.2j), (1.0 - 0.2j, 3.0 + 0.0j)),
        dtype=np.complex128,
        order="C",
    )
    block1 = np.asarray(
        ((2.0 + 0.0j, 0.4 - 0.1j), (0.4 + 0.1j, 2.5 + 0.0j)),
        dtype=np.complex128,
        order="C",
    )
    stream = (
        (0, block0, expansion0),
        (1, block1, expansion1),
    )
    result = stream_h2b_p0_patch(
        refs, np.asarray((10, 11, 12), dtype=np.int64), (item for item in stream),
        task037_extra_h2b=True,
    )
    dense0 = expansion0.materialize_dense()
    dense1 = expansion1.materialize_dense()
    expected = np.zeros((3, 3), dtype=np.complex128)
    expected[:2, :2] += dense0.conj().T @ block0 @ dense0
    expected[1:, 1:] += dense1.conj().T @ block1 @ dense1
    assert np.allclose(result["matrix"], expected, rtol=1.0e-13, atol=1.0e-13)
    assert result["patch_row_count"] == 3
    assert result["patch_rows"] == (10, 11, 12)
    json.dumps(
        {key: value for key, value in result.items() if key != "matrix"},
        allow_nan=False,
    )
    assert result["touching_cell_ordinals"] == (0, 1)
    assert result["global_matrix_materialized"] is False
    assert result["per_cell_factor"] is False
    assert result["slab_factor"] is False


def test_p0_core_patch_json_roundtrip_is_json_safe():
    rows = tuple(range(882))
    result = stream_h2b_p0_patch(
        (SimpleNamespace(independent_global_rows=np.asarray(rows, dtype=np.int64)),),
        np.asarray(rows, dtype=np.int64),
        ((0, np.eye(882, dtype=np.complex128, order="C"), _identity_expansion(rows)),),
        task037_extra_h2b=True,
    )
    patch = json.loads(
        json.dumps(
            {key: value for key, value in result.items() if key != "matrix"},
            allow_nan=False,
        )
    )
    assert "matrix" not in patch
    assert patch["patch_rows"] == list(rows)
    assert patch["touching_cell_ordinals"] == [0]
    assert patch["touching_cell_count"] == 1
    assert patch["matrix_shape"] == [882, 882]
    assert patch["matrix_nbytes"] == 882 * 882 * 16


def test_p0_factor_and_patch_row_oracle_are_finite_deterministic_and_include_spill():
    patch = np.asarray(
        (
            (0.1 + 0.0j, 2.0 + 0.1j, 0.0 + 0.0j),
            (3.0 + 0.0j, 1.0 + 0.0j, 0.2 + 0.0j),
            (0.0 + 0.0j, 0.4 + 0.0j, 2.0 + 0.0j),
        ),
        dtype=np.complex128,
        order="C",
    )
    factor = factorize_h2b_p0_patch(patch, task037_extra_h2b=True)
    assert np.any(factor.pivots != np.arange(3, dtype=np.int32))
    assert factor.factorization_residual <= 1.0e-10
    assert factor.solve_residual <= 1.0e-10
    assert factor.finite is True
    assert factor.deterministic is True
    assert np.isfinite(factor.pivot_growth)
    assert 0.0 <= factor.reciprocal_condition_estimate <= 1.0
    assert factor.condition_estimate >= 1.0
    assert len(factor.solve_gains) == 2
    assert factor.factor_bytes == factor.values.nbytes + factor.pivots.nbytes
    assert not hasattr(factor, "matrix")

    full = np.zeros((4, 4), dtype=np.complex128)
    full[:3, :3] = patch
    full[3, 0] = 0.75 - 0.1j

    def action(source: np.ndarray, target: np.ndarray) -> None:
        target[:] = full @ source

    rhs = np.asarray((1.0 + 0.2j, -0.3 + 0.7j, 0.4 - 0.1j, 0.5 + 0.0j), dtype=np.complex128)
    rows = np.asarray((0, 1, 2), dtype=np.int64)
    first = measure_h2b_p0_patch_direction(
        rhs, patch, factor, rows, action, task037_extra_h2b=True
    )
    second = measure_h2b_p0_patch_direction(
        rhs, patch, factor, rows, action, task037_extra_h2b=True
    )
    assert first["exact_action_relative_error"] <= 1.0e-11
    assert first["off_patch_spill_norm"] > 0.0
    assert 0.0 <= first["rho_star"] <= first["rho_unit"] + 1.0e-12
    assert first["correction_sha256"] == second["correction_sha256"]
    assert first["action_sha256"] == second["action_sha256"]
    assert first["external_slave_mask"] is False
    assert first["rho_scope"] == "patch_rows_only"
    assert first["full_space_rho_scope"] == "diagnostic_only"
    assert np.isfinite(first["off_patch_spill_ratio"])


def test_p0_lu_reconstruction_reverses_multiple_pivot_swaps():
    from scipy.linalg import lu_factor

    matrix = np.asarray(
        (
            (1.0 + 0.2j, 1.0 - 0.1j, 0.0 + 0.3j),
            (4.0 - 0.2j, 1.0 + 0.4j, 1.0 - 0.1j),
            (2.0 + 0.1j, 3.0 - 0.3j, 1.0 + 0.2j),
        ),
        dtype=np.complex128,
        order="C",
    )
    lu, pivots = lu_factor(matrix)
    assert np.array_equal(pivots, np.asarray((1, 2, 2), dtype=np.int32))
    reconstructed = _p0_lu_reconstruction(lu, pivots)
    assert np.linalg.norm(reconstructed - matrix) / np.linalg.norm(matrix) <= 1.0e-12


def test_p0_element_solve_uses_row_complete_action_closure():
    patch = np.asarray(
        ((4.0 + 0.0j, 0.3 + 0.1j), (0.3 - 0.1j, 3.0 + 0.0j)),
        dtype=np.complex128,
        order="C",
    )
    element = np.array(patch, copy=True, order="C")
    element[0, 0] += 1.0
    element_factor = factorize_h2b_p0_patch(element, task037_extra_h2b=True)
    rhs = np.asarray((1.0 + 0.2j, -0.4 + 0.1j), dtype=np.complex128)
    rows = np.asarray((0, 1), dtype=np.int64)

    def action(source: np.ndarray, target: np.ndarray) -> None:
        target[:] = patch @ source

    result = measure_h2b_p0_patch_direction(
        rhs,
        element,
        element_factor,
        rows,
        action,
        closure_matrix=patch,
        task037_extra_h2b=True,
    )
    assert result["exact_action_relative_error"] <= 1.0e-11
    assert result["element_operator_mismatch_relative"] > 0.0


def test_p0_opt_in_and_input_contracts_fail_closed():
    assert runner._parser().parse_args(
        ["p0-watchdog", "--run-dir", "/tmp/p0"]
    ).command == "p0-watchdog"
    assert runner._parser().parse_args(
        ["p0-check", "--run-dir", "/tmp/p0", "--output", "/tmp/p0.json"]
    ).command == "p0-check"
    with pytest.raises(ValueError, match="opt-in"):
        select_h2b_p0_class([_class(0, 1)], task037_extra_h2b=False)
    patch = np.eye(2, dtype=np.complex64)
    with pytest.raises(ValueError, match="complex128"):
        factorize_h2b_p0_patch(patch, task037_extra_h2b=True)


def _p0_direction(label: str, rho: float = 0.1) -> dict[str, object]:
    return {
        "schema": runner.H2B_P0_DIRECTION_SCHEMA,
        "patch_row_count": 882,
        "rhs_sha256": "9" * 64,
        "correction_sha256": "b" * 64,
        "repeat_correction_sha256": "b" * 64,
        "action_sha256": "c" * 64,
        "repeat_action_sha256": "c" * 64,
        "r_norm": 1.0,
        "q_norm": 1.0,
        "rho_unit": max(0.2, rho),
        "rho_star": rho,
        "eta": 0.5,
        "omega_real": 1.0,
        "omega_imag": 0.0,
        "omega_abs": 1.0,
        "exact_action_relative_error": 0.0,
        "off_patch_spill_norm": 0.0,
        "off_patch_spill_ratio": 0.0,
        "correction_norm": 1.0,
        "correction_amplification": 1.0,
        "element_operator_mismatch_relative": 0.0,
        "full_space_rho_star": rho,
        "full_space_rho_unit": 0.2,
        "full_space_eta": 0.5,
        "full_space_rho_scope": "diagnostic_only",
        "finite": True,
        "deterministic": True,
        "external_slave_mask": False,
        "rho_scope": "patch_rows_only",
    }


def _p0_source(label: str, rho: float = 0.1) -> dict[str, object]:
    return {
        "label": label,
        "definition": runner.H2B_SOURCE_DEFINITIONS[label],
        "definition_sha256": runner._source_definition_sha(label),
        "vector_sha256": "a" * 64,
        "full_space_norm": 2.0,
        "element_block": _p0_direction(label, rho),
        "row_complete_patch": _p0_direction(label, rho),
    }


def _p0_checker_payload() -> dict[str, object]:
    rows = list(range(882))
    class_inventory = [
        {
            "class_id": 0,
            "cell_count": 252,
            "constraint_pattern_entry_count": 0,
            "constraint_pattern_kinds": [],
            "class_key_sha256": "d" * 64,
            "constraint_pattern_sha256": "e" * 64,
        }
    ]
    selection = select_h2b_p0_class(
        class_inventory, task037_extra_h2b=True
    )
    source = {
        "source_commit_full_sha": "f" * 40,
        "tracked_source_dirty": False,
        "source_worktree_dirty": False,
        "nonignored_untracked_paths": [],
    }
    authority = {"producer": "synthetic"}
    s0_authority = {
        "record_path": "/tmp/s0.json",
        "record_sha256": "1" * 64,
        "evidence_sha256": "2" * 64,
        "status": "pass",
        "pass": True,
        "route": "H2B-P",
        "s0_direction_gate_pass": False,
    }
    return {
        "scope": runner._p0_scope(),
        "identity": runner._fixed_identity(),
        "authority": authority,
        "authority_expected": authority,
        "worker_authority": authority,
        "s0_authority": s0_authority,
        "s0_authority_expected": s0_authority,
        "form": {"role": "b0"},
        "source_at_start": source,
        "source_at_end": source,
        "watchdog_source_at_start": source,
        "watchdog_source_at_end": source,
        "stage": {
            "return_code": 0,
            "termination": None,
            "processes_gone_before_p0": True,
        },
        "online": {
            "return_code": 0,
            "termination": None,
            "processes_gone_after_p0": True,
        },
        "stage_events": list(runner.H2B_STAGE_EVENTS),
        "online_events": list(runner.H2B_P0_EVENTS),
        "p6": {
            "global_cells": 252,
            "local_cells": 252,
            "local_nloc": 882,
            "global_rows": 173802,
            "constraint_count": 9210,
        },
        "class_inventory": class_inventory,
        "selection": selection,
        "central_cell_ordinal": 0,
        "patch_rows": rows,
        "cell_class_ids": [0] * 252,
        "cell_references": [
            {"class_id": 0, "independent_global_rows": rows}
            for _ in range(252)
        ],
        "touching_cell_ordinals": list(range(252)),
        "cache": {
            "action_cache_dir": "/tmp/p0/jit_cache",
            "action_cache_before": [],
            "action_cache_after": [],
            "action_cache_unchanged": True,
            "r1_proxy_cache_dir": "/tmp/r1-cache",
            "r1_proxy_cache_before": [],
            "r1_proxy_cache_after": [],
            "r1_proxy_cache_unchanged": True,
        },
        "r2_factor_payload_bytes": 201933812,
        "element_factor": {
            "matrix_sha256": "4" * 64,
            "factor_values_sha256": "5" * 64,
            "pivot_sha256": "6" * 64,
            "factor_bytes": 12450312,
            "factorization_residual": 1.0e-12,
            "solve_residual": 1.0e-12,
            "finite": True,
            "deterministic": True,
            "pivot_growth": 1.0,
            "reciprocal_condition_estimate": 0.5,
            "condition_estimate": 2.0,
            "pivot_growth_convention": "max_abs_U_over_max_abs_matrix",
            "solve_gains": [1.0, 2.0],
            "r2_store_binding": {
                "class_id": 0,
                "factor_id": 0,
                "class_key_sha256": "d" * 64,
                "constraint_pattern_sha256": "e" * 64,
                "expansion_pattern_sha256": "f" * 64,
                "matrix_sha256": "4" * 64,
                "factor_values_sha256": "5" * 64,
                "pivot_sha256": "6" * 64,
            },
        },
        "patch": {
            "patch_row_count": 882,
            "touching_cell_count": 252,
            "touching_cell_ordinals": list(range(252)),
            "touching_class_ids": [0],
            "touching_class_count": 1,
            "tensor_tabulation_cell_count": 1,
            "tensor_reuse_cell_count": 251,
            "max_live_dense_proxy_count": 1,
            "cell_dense_tensors_retained": False,
            "tensor_accumulation_order": "first_seen_class_then_ascending_cell_ordinal",
            "matrix_sha256": "1" * 64,
            "matrix_shape": [882, 882],
            "matrix_dtype": "complex128",
            "matrix_nbytes": 882 * 882 * 16,
            "global_matrix_materialized": False,
            "global_constraint_matrix_materialized": False,
            "per_cell_factor": False,
            "slab_factor": False,
            "schur_materialized": False,
        },
        "factor": {
            "matrix_sha256": "1" * 64,
            "factor_values_sha256": "2" * 64,
            "pivot_sha256": "3" * 64,
            "factor_bytes": 12450312,
            "factorization_residual": 1.0e-12,
            "solve_residual": 1.0e-12,
            "finite": True,
            "deterministic": True,
            "pivot_growth": 1.0,
            "reciprocal_condition_estimate": 0.5,
            "condition_estimate": 2.0,
            "pivot_growth_convention": "max_abs_U_over_max_abs_matrix",
            "solve_gains": [1.0, 2.0],
        },
        "sources": [_p0_source(label) for label in runner.H2B_SOURCE_LABELS],
        "resource": {
            "process_tree_peak_rss_bytes": 900_000_000,
            "process_tree_swap_bytes": 0,
        },
        "materialization_identity": {
            "global_matrix_materialized": False,
            "global_constraint_matrix_materialized": False,
            "per_cell_factor": False,
            "slab_factor": False,
            "schur_materialized": False,
        },
    }


def test_p0_checker_recomputes_selection_and_rejects_missing_payload_key():
    payload = _p0_checker_payload()
    checked = runner._p0_check_payload(payload)
    assert checked["pass"] is True
    assert checked["measurements"]["p6"]["constraint_count"] == 9210
    assert checked["measurements"]["patch"]["touching_class_count"] == 1
    assert checked["measurements"]["patch"]["tensor_reuse_cell_count"] == 251
    broken = {**payload}
    broken.pop("cell_class_ids")
    failed = runner._p0_check_payload(broken)
    assert failed["pass"] is False
    assert "cell_authority" in failed["problems"]
    short_ids = {
        **payload,
        "cell_class_ids": payload["cell_class_ids"][:-1],
    }
    failed_short = runner._p0_check_payload(short_ids)
    assert failed_short["pass"] is False
    assert "cell_authority" in failed_short["problems"]
    assert "patch" in failed_short["problems"]
    bool_ordinals = {
        **payload,
        "patch": {
            **payload["patch"],
            "touching_cell_ordinals": [True] + list(range(1, 252)),
        },
    }
    failed_bool_ordinal = runner._p0_check_payload(bool_ordinals)
    assert failed_bool_ordinal["pass"] is False
    assert "patch" in failed_bool_ordinal["problems"]
    over_limit = {**payload, "resource": {
        **payload["resource"],
        "process_tree_peak_rss_bytes": runner.H2B_P0_RSS_LIMIT_BYTES,
    }}
    failed_resource = runner._p0_check_payload(over_limit)
    assert failed_resource["pass"] is False
    assert "resource" in failed_resource["problems"]
    bad_swap = {**payload, "resource": {
        **payload["resource"],
        "process_tree_swap_bytes": 1,
    }}
    assert "resource" in runner._p0_check_payload(bad_swap)["problems"]
    bad_materialization = {
        **payload,
        "materialization_identity": {
            **payload["materialization_identity"],
            "slab_factor": True,
        },
    }
    assert "materialization" in runner._p0_check_payload(
        bad_materialization
    )["problems"]
    bad_reuse = {**payload, "patch": {
        **payload["patch"],
        "tensor_reuse_cell_count": 0,
    }}
    assert "patch" in runner._p0_check_payload(bad_reuse)["problems"]
    missing_reuse = {**payload, "patch": {
        key: value
        for key, value in payload["patch"].items()
        if key != "tensor_tabulation_cell_count"
    }}
    assert "patch" in runner._p0_check_payload(missing_reuse)["problems"]


def test_p0_other_source_gate_is_strictly_zero_point_ninety_five():
    payload = _p0_checker_payload()
    boundary = _p0_source("gradient-dominated", 0.95)
    payload["sources"] = [
        boundary if item["label"] == "gradient-dominated" else item
        for item in payload["sources"]
    ]
    assert runner._p0_check_payload(payload)["pass"] is True
    failed = _p0_source("gradient-dominated", 0.950000000001)
    payload["sources"] = [
        failed if item["label"] == "gradient-dominated" else item
        for item in payload["sources"]
    ]
    result = runner._p0_check_payload(payload)
    assert result["pass"] is False
    assert "sources" in result["problems"]


def test_p0_s0_authority_reads_frozen_canonical():
    authority = runner._p0_s0_authority()
    assert authority["record_sha256"] == runner.H2B_S0_RECORD_SHA256
    assert authority["route"] == "H2B-P"
    assert authority["s0_direction_gate_pass"] is False


def test_p0_direction_allows_signed_omega_but_requires_nonnegative_norms():
    record = _p0_direction("gradient-dominated")
    record["omega_real"] = -0.4
    record["omega_imag"] = -0.2
    assert runner._p0_direction_valid(
        "gradient-dominated", record, rho_limit=0.95
    )
    record["correction_norm"] = -1.0
    assert not runner._p0_direction_valid(
        "gradient-dominated", record, rho_limit=0.95
    )


def test_p0_raw_checker_integration_uses_structured_worker_payload(tmp_path, monkeypatch):
    import hashlib

    run_dir = tmp_path / "p0"
    cache_dir = run_dir / "jit_cache"
    cache_dir.mkdir(parents=True)
    module = "libffcx_forms_synthetic"
    cache_files = []
    for suffix in (".c", ".o", ".so", ".c.cached"):
        path = cache_dir / f"{module}{suffix}"
        path.write_bytes(b"p0")
        cache_files.append(
            {
                "path": path.name,
                "bytes": path.stat().st_size,
                "mtime_ns": path.stat().st_mtime_ns,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    form_base = {
        "role": "b0",
        "ufl_signature": "u",
        "ufcx_signature": "u",
        "module_name": module,
        "ffcx_signature_stem": "synthetic",
        "jit_options": {
            "cache_dir": str(cache_dir.resolve()),
            "cffi_extra_compile_args": ["-O0", "-g0"],
        },
        "form_compiler_options": {"scalar_type": "complex128"},
        "proxy_identity": {"operator": "B0"},
        "element_signature": ["synthetic"],
        "cache_files": cache_files,
    }
    stage_form = {**form_base, "code_state": "cold_decl_impl_generated"}
    online_form = {**form_base, "code_state": "hit_no_new_decl_impl"}
    source = {
        "source_commit_full_sha": "f" * 40,
        "tracked_source_dirty": False,
        "source_worktree_dirty": False,
        "cleanliness_semantics": "all tracked changes plus every nonignored untracked path",
        "nonignored_untracked_paths": [],
        "worktree_status_porcelain": [],
        "git_error": None,
    }
    runtime = {
        "qualified_activation": "1",
        "sys_executable": "/repo/.venv/bin/python",
        "petsc_scalar_type": "complex128",
        "petsc_int_type": "int32",
        "threads": {
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
        },
    }
    payload = _p0_checker_payload()
    values = np.eye(2, dtype=np.complex128)
    pivots = np.asarray((0, 1), dtype=np.int32)
    array_sha = lambda value: hashlib.sha256(
        memoryview(np.ascontiguousarray(value)).cast("B")
    ).hexdigest()
    payload["element_factor"]["factor_values_sha256"] = array_sha(values)
    payload["element_factor"]["pivot_sha256"] = array_sha(pivots)
    payload["element_factor"]["r2_store_binding"]["factor_values_sha256"] = array_sha(values)
    payload["element_factor"]["r2_store_binding"]["pivot_sha256"] = array_sha(pivots)
    authority = {
        "r0": {"class_inventory": payload["class_inventory"]},
        "producer_authority": payload["authority"],
        "factor_manifest_sha256": "a" * 64,
    }
    s0_authority = payload["s0_authority"]
    fake_class = SimpleNamespace(
        class_id=0,
        class_key_sha256="d" * 64,
        constraint_pattern_sha256="e" * 64,
        expansion_pattern_sha256="f" * 64,
        factor_id=0,
    )
    fake_factor = SimpleNamespace(
        factor_id=0,
        numeric_matrix_sha256="4" * 64,
        values=values,
        pivots=pivots,
    )
    fake_store = SimpleNamespace(
        cells=[
            SimpleNamespace(
                class_id=0,
                independent_global_rows=np.arange(882, dtype=np.int64),
            )
            for _ in range(252)
        ],
        classes=[fake_class],
        factors=[fake_factor],
    )
    fake_h2a = SimpleNamespace(
        load_h2a_r2_factor_store=lambda *args, **kwargs: fake_store
    )
    monkeypatch.setattr(runner, "_authority", lambda: authority)
    monkeypatch.setattr(runner, "_p0_s0_authority", lambda: s0_authority)
    monkeypatch.setattr(runner, "_lazy_h2a", lambda: fake_h2a)
    monkeypatch.setattr(runner, "_light_source", lambda: source)
    stage = {
        "schema": runner.H2B_WORKER_SCHEMA,
        "phase": "stage",
        "status": "measurement_complete",
        "scope": runner._fixed_scope(),
        "identity": runner._fixed_identity(),
        "phase_identity": runner._phase_identity(
            jit_api=True, compile_called=True, compiler_probe=True
        ),
        "source_at_start": source,
        "source_at_end": source,
        "runtime_identity": runtime,
        "form": stage_form,
        "measurement": {},
        "error": None,
    }
    online_measurement = {
        **payload,
        "authority": authority["producer_authority"],
        "s0_authority": s0_authority,
    }
    online = {
        "schema": runner.H2B_P0_WORKER_SCHEMA,
        "phase": "p0",
        "status": "measurement_complete",
        "scope": runner._p0_scope(),
        "identity": runner._fixed_identity(),
        "phase_identity": runner._p0_phase_identity(),
        "source_at_start": source,
        "source_at_end": source,
        "runtime_identity": runtime,
        "form": online_form,
        "measurement": online_measurement,
        "error": None,
    }
    for phase, events in (("stage", runner.H2B_STAGE_EVENTS), ("p0", runner.H2B_P0_EVENTS)):
        path = run_dir / f"{phase}_progress.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "".join(
                json.dumps(
                    {"schema": runner.H2B_PROGRESS_SCHEMA, "phase": phase, "event": event}
                )
                + "\n"
                for event in events
            ),
            encoding="utf-8",
        )
        timeline = run_dir / f"{phase}_timeline.jsonl"
        timeline.write_text(
            json.dumps(
                {
                    "schema": runner.H2B_PROGRESS_SCHEMA,
                    "phase": phase,
                    "sample_kind": "worker",
                    "root_pid": 11,
                    "pids": [11],
                    "process_count": 1,
                    "rss_bytes": 100,
                    "swap_bytes": 0,
                    "all_status_readable": True,
                    "compiler_descendant_pids": [],
                }
            )
            + "\n",
            encoding="utf-8",
        )
    for name in runner.H2B_P0_ARTIFACT_NAMES:
        path = run_dir / name
        if not path.exists():
            path.write_bytes(b"artifact")
    runner._write_json(run_dir / "stage_summary.json", runner._attach_evidence(stage))
    runner._write_json(run_dir / "p0_summary.json", runner._attach_evidence(online))
    watchdog = {
        "schema": runner.H2B_P0_WATCHDOG_SCHEMA,
        "status": "pass",
        "scope": runner._p0_scope(),
        "identity": runner._fixed_identity(),
        "run_dir": str(run_dir.resolve()),
        "source_at_start": source,
        "source_at_end": source,
        "stage": {
            "return_code": 0,
            "termination": None,
            "processes_gone_before_p0": True,
        },
        "p0": {
            "return_code": 0,
            "termination": None,
            "processes_gone_after_p0": True,
        },
    }
    watchdog["raw_artifacts"] = {
        name: runner._artifact(run_dir, name)
        for name in runner.H2B_P0_ARTIFACT_NAMES
    }
    runner._write_json(
        run_dir / "p0_watchdog_summary.json", runner._attach_evidence(watchdog)
    )
    result = runner._p0_check_raw(run_dir)
    assert result["pass"] is True, result["problems"]
    assert result["checks"]["r2_store_cells"] is True
    assert result["checks"]["watchdog_status"] is True
    assert result["checks"]["watchdog_evidence"] is True
    watchdog["run_dir"] = str(run_dir / "wrong")
    runner._write_json(
        run_dir / "p0_watchdog_summary.json", runner._attach_evidence(watchdog)
    )
    broken = runner._p0_check_raw(run_dir)
    assert broken["checks"]["watchdog_evidence"] is False


def test_p0_controlled_timeout_preserves_only_measured_failure_evidence(
    tmp_path, monkeypatch
):
    run_dir = tmp_path / "p0"
    run_dir.mkdir()
    source = {
        "source_commit_full_sha": "a" * 40,
        "tracked_source_dirty": False,
        "source_worktree_dirty": False,
        "cleanliness_semantics": "all tracked changes plus every nonignored untracked path",
        "nonignored_untracked_paths": [],
        "worktree_status_porcelain": [],
        "git_error": None,
    }
    runtime = {
        "qualified_activation": "1",
        "sys_executable": "/repo/.venv/bin/python",
        "petsc_scalar_type": "complex128",
        "petsc_int_type": "int32",
        "threads": {
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
        },
    }

    def write_progress(phase, events):
        (run_dir / f"{phase}_progress.jsonl").write_text(
            "".join(
                json.dumps(
                    {
                        "schema": runner.H2B_PROGRESS_SCHEMA,
                        "phase": phase,
                        "event": event,
                    }
                )
                + "\n"
                for event in events
            ),
            encoding="utf-8",
        )

    def write_timeline(phase, rss):
        (run_dir / f"{phase}_timeline.jsonl").write_text(
            json.dumps(
                {
                    "schema": runner.H2B_PROGRESS_SCHEMA,
                    "phase": phase,
                    "sample_kind": "worker",
                    "root_pid": 11 if phase == "stage" else 12,
                    "pids": [11 if phase == "stage" else 12],
                    "process_count": 1,
                    "rss_bytes": rss,
                    "swap_bytes": 0,
                    "all_status_readable": True,
                    "compiler_descendant_pids": [],
                }
            )
            + "\n",
            encoding="utf-8",
        )

    for name in runner.H2B_P0_ARTIFACT_NAMES:
        if name != "p0_summary.json":
            (run_dir / name).write_bytes(b"artifact")
    write_progress("stage", runner.H2B_STAGE_EVENTS)
    write_progress("p0", runner.H2B_P0_EVENTS[:17])
    write_timeline("stage", 200)
    write_timeline("p0", 100)
    stage = {
        "schema": runner.H2B_WORKER_SCHEMA,
        "phase": "stage",
        "status": "measurement_complete",
        "scope": runner._fixed_scope(),
        "identity": runner._fixed_identity(),
        "source_at_start": source,
        "source_at_end": source,
        "runtime_identity": runtime,
        "error": None,
        "elapsed_wall_seconds": 25.0,
    }
    runner._write_json(run_dir / "stage_summary.json", runner._attach_evidence(stage))
    watchdog = {
        "schema": runner.H2B_P0_WATCHDOG_SCHEMA,
        "status": "gate_failed",
        "run_dir": str(run_dir.resolve()),
        "scope": runner._p0_scope(),
        "identity": runner._fixed_identity(),
        "source_at_start": source,
        "source_at_end": source,
        "error": None,
        "stage": {
            "command": ["python", "jit-worker", "--run-dir", str(run_dir)],
            "return_code": 0,
            "termination": None,
            "processes_gone_before_p0": True,
            "processes_gone_before_p0_drain": {"gone": True},
            "elapsed_wall_seconds": 26.0,
            "peak_rss_bytes": 200,
            "swap_bytes": 0,
        },
        "p0": {
            "command": ["python", "p0-worker", "--run-dir", str(run_dir)],
            "return_code": -15,
            "processes_gone_after_p0": True,
            "processes_gone_after_p0_drain": {"gone": True},
            "elapsed_wall_seconds": 3600.09,
            "peak_rss_bytes": 100,
            "swap_bytes": 0,
            "termination": {
                "reason": "timeout",
                "termination": {
                    "sigkill_required": False,
                    "worker_exited": True,
                },
            },
        },
    }
    watchdog["raw_artifacts"] = {
        name: runner._artifact(run_dir, name)
        for name in runner.H2B_P0_ARTIFACT_NAMES
    }
    runner._write_json(
        run_dir / "p0_watchdog_summary.json", runner._attach_evidence(watchdog)
    )
    checker_source = dict(source)
    checker_source["source_commit_full_sha"] = "b" * 40
    monkeypatch.setattr(runner, "_light_source", lambda: checker_source)

    result = runner._controlled_p0_failure(
        run_dir, FileNotFoundError(run_dir / "p0_summary.json")
    )
    assert result["status"] == "gate_failed"
    assert result["pass"] is False
    assert result["measurements"] is None
    assert "p0_execution_timeout" in result["problems"]
    assert "p0_measurements_not_produced" in result["problems"]
    assert result["failure_measurements"]["p0"]["return_code"] == -15
    assert result["failure_measurements"]["p0"]["process_tree_peak_rss_bytes"] == 100
    assert "factor" not in result["failure_measurements"]
    assert result["failure_measurements"]["run_source_at_start"][
        "source_commit_full_sha"
    ] == "a" * 40
    assert result["failure_measurements"]["checker_source"][
        "source_commit_full_sha"
    ] == "b" * 40
    assert (
        result["failure_measurements"]["run_source_at_start"]["source_commit_full_sha"]
        != result["failure_measurements"]["checker_source"]["source_commit_full_sha"]
    )
    assert result["raw_artifacts"]["p0_summary.json"] == {
        "path": "p0_summary.json",
        "present": False,
    }

    invalid = dict(watchdog)
    invalid["evidence_sha256"] = "0" * 64
    runner._write_json(run_dir / "p0_watchdog_summary.json", invalid)
    assert runner._controlled_p0_failure(run_dir, ValueError("bad evidence")) is None
    output = tmp_path / "generic.json"
    assert runner._run_p0_check(run_dir, output) == 1
    generic = json.loads(output.read_text(encoding="utf-8"))
    assert generic["problems"]
    assert all(problem.startswith("raw_unreadable:") for problem in generic["problems"])

    runner._write_json(
        run_dir / "p0_watchdog_summary.json", runner._attach_evidence(watchdog)
    )
    (run_dir / "p0_summary.json").write_text("{}", encoding="utf-8")
    assert runner._controlled_p0_failure(run_dir, FileNotFoundError("p0")) is None
