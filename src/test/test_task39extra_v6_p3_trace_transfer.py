"""Focused reference and saved-C2 checks for the opt-in V6 P3 trace map."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from hashlib import sha256
from itertools import product
from pathlib import Path

import basix
import numpy as np
import pytest

from src.io.native_capacity_profile import native_profile_facts
from src.solvers.fullspace_same_mesh_hcurl_pmg import (
    DEFAULT_TRACE_MAP_POLICY,
    V6_P3_CANONICAL_TRACE_MAP_POLICY,
    _canonical_p63_trace_rows,
    _canonical_quadrilateral_n1e_transfer,
    _dof_functional_interpolation,
    _dof_transform,
    _n1e,
    _n1e_quadrilateral,
    build_same_mesh_hcurl_transfer,
)

ROOT = Path(__file__).resolve().parents[2]
DIAGNOSTICS = ROOT / "tmp/p3_mid_order_0p7/diagnostics"
C2_NPZ = DIAGNOSTICS / "actual_p63_owner_row_repro_v3_c2_input.npz"
C2_NPZ_SHA256 = "207d8cf01d70fa62bd55ce0245ee43ada26996885bbf1c8cb871118dbfdfa113"
ROW_LIMIT = 1.0e-11


def _quad_d4_pullback_transform(element, linear: np.ndarray, offset: np.ndarray):
    points = np.asarray(element.points, dtype=np.float64)
    mapped_points = points @ linear.T + offset
    values = np.asarray(element.tabulate(0, mapped_points))[0]
    pulled = np.einsum("ab,njb->nja", linear.T, values, optimize=False)
    assert pulled.shape == values.shape
    value_size = int(np.prod(element.value_shape, dtype=np.int64))
    flattened = pulled.transpose(2, 0, 1).reshape(
        len(points) * value_size, int(element.dim)
    )
    return np.ascontiguousarray(element.interpolation_matrix @ flattened)


def _quad_d4_maps():
    maps = []
    identity = np.eye(2, dtype=np.int64)
    swap = np.array([[0, 1], [1, 0]], dtype=np.int64)
    center = np.array([0.5, 0.5], dtype=np.float64)
    for name, permutation in (("axis", identity), ("axis_swap", swap)):
        for sign_x, sign_y in product((-1, 1), repeat=2):
            linear = np.diag([sign_x, sign_y]) @ permutation
            offset = center - linear @ center
            maps.append((name, linear.astype(np.float64), offset))
    return maps


def _trace_rows(fine_element):
    edge_rows = {
        int(value)
        for entity in fine_element.entity_dofs[1]
        for value in entity
    }
    face_rows = {
        int(value)
        for entity in fine_element.entity_dofs[2]
        for value in entity
    }
    return edge_rows, face_rows, edge_rows | face_rows


def _batch8_replay(matrices, arrays):
    packet_count = int(np.asarray(arrays["p6_candidate_values_raw"]).size)
    result = np.empty(packet_count, dtype=np.complex128)
    source = np.asarray(arrays["p3_coarse_transfer_input"], dtype=np.complex128)
    offsets = np.asarray(arrays["cell_packet_offsets"], dtype=np.int64)
    orientation = np.asarray(arrays["cell_orientation_index"], dtype=np.int32)
    batch_size = min(8, len(orientation))
    width_fine, width_coarse = matrices[0].shape
    batch_input = np.empty((batch_size, width_coarse), dtype=np.complex128)
    batch_output = np.empty((batch_size, width_fine), dtype=np.complex128)
    local_ids = np.asarray(arrays["coarse_local_dof_indices"], dtype=np.int64)
    batch_counts = []
    for orientation_index, matrix in enumerate(matrices):
        cells = [
            int(value)
            for value in np.flatnonzero(orientation == orientation_index)
        ]
        batches = 0
        for start in range(0, len(cells), batch_size):
            selected = cells[start : start + batch_size]
            count = len(selected)
            for batch_row, cell in enumerate(selected):
                np.take(source, local_ids[cell], out=batch_input[batch_row])
            np.matmul(
                batch_input[:count],
                matrix.T,
                out=batch_output[:count],
            )
            for batch_row, cell in enumerate(selected):
                packet_start, packet_stop = offsets[cell]
                if int(packet_stop - packet_start) != width_fine:
                    raise AssertionError("saved cell packet has an unexpected width")
                result[int(packet_start) : int(packet_stop)] = batch_output[batch_row]
            batches += 1
        batch_counts.append({"orientation_index": orientation_index, "cells": len(cells), "batches": batches})
    return result, {"batch_size_limit": batch_size, "groups": batch_counts}


def _shared_owner_summary(values, arrays, trace_rows, edge_rows):
    candidate_global_rows = np.asarray(
        arrays["candidate_global_fine_rows"], dtype=np.int64
    )
    candidate_local_rows = np.asarray(
        arrays["candidate_local_fine_row"], dtype=np.int32
    )
    trace_candidates = np.flatnonzero(np.isin(candidate_local_rows, list(trace_rows)))
    grouped = {}
    for index in trace_candidates:
        grouped.setdefault(int(candidate_global_rows[index]), []).append(int(index))
    shared = {row: indices for row, indices in grouped.items() if len(indices) > 1}
    records = []
    for global_row, indices in shared.items():
        reference = values[indices[0]]
        defect = float(np.max(np.abs(values[indices] - reference)))
        local_row = int(candidate_local_rows[indices[0]])
        records.append(
            {
                "global_fine_row": global_row,
                "entity_class": "edge" if local_row in edge_rows else "face",
                "candidate_count": len(indices),
                "max_absolute_candidate_difference": defect,
            }
        )
    worst = max(records, key=lambda row: row["max_absolute_candidate_difference"])
    return {
        "candidate_count": len(trace_candidates),
        "shared_row_count": len(shared),
        "edge_shared_row_count": sum(row["entity_class"] == "edge" for row in records),
        "face_shared_row_count": sum(row["entity_class"] == "face" for row in records),
        "max_absolute_difference": worst["max_absolute_candidate_difference"],
        "worst": worst,
        "rows_over_original_absolute_gate": sum(
            row["max_absolute_candidate_difference"] > ROW_LIMIT for row in records
        ),
    }


def test_v6_p3_policy_is_explicit_and_keeps_other_maps_unchanged():
    p3_v6 = native_profile_facts("dual_condensed_balh_native_5nm_p3_v6")
    p2_v6 = native_profile_facts("dual_condensed_balh_native_2nm_p3_pilot16_v6")
    q4_v6 = native_profile_facts("dual_condensed_balh_native_5nm_v6")
    p3_v5 = native_profile_facts("dual_condensed_balh_native_13p5_q3_v5")
    assert p3_v6["component_options"]["same_mesh_trace_map_policy"] == V6_P3_CANONICAL_TRACE_MAP_POLICY
    assert p2_v6["component_options"]["same_mesh_trace_map_policy"] == V6_P3_CANONICAL_TRACE_MAP_POLICY
    assert "same_mesh_trace_map_policy" not in q4_v6["component_options"]
    assert "same_mesh_trace_map_policy" not in p3_v5.get("component_options", {})

    coarse3, fine6 = _n1e(3), _n1e(6)
    basix_p63 = np.asarray(
        basix.compute_interpolation_operator(coarse3, fine6), dtype=np.complex128
    )
    default_p63 = build_same_mesh_hcurl_transfer(6, 3)
    candidate_p63 = build_same_mesh_hcurl_transfer(
        6, 3, trace_map_policy=V6_P3_CANONICAL_TRACE_MAP_POLICY
    )
    assert default_p63.audit.get("trace_map_policy", DEFAULT_TRACE_MAP_POLICY) == DEFAULT_TRACE_MAP_POLICY
    assert np.array_equal(default_p63.matrix, basix_p63)
    assert candidate_p63.audit["trace_map_policy"] == V6_P3_CANONICAL_TRACE_MAP_POLICY
    assert candidate_p63.audit["trace_rows_replaced"] == 432
    assert candidate_p63.audit["interior_rows_retained_from_basix"] == 450
    assert candidate_p63.audit["interior_rows_bitwise_unchanged"] is True
    assert candidate_p63.audit["full_cell_basix_map_preserved"] is False
    assert len(candidate_p63.audit["canonical_reference_map_sha256"]) == 64
    assert candidate_p63.audit["absolute_owner_row_limit"] == ROW_LIMIT
    assert candidate_p63.audit["absolute_owner_row_limit_changed"] is False
    assert candidate_p63.audit["candidate_vs_unmodified_independent_max_abs"] <= ROW_LIMIT

    x = np.arange(default_p63.matrix.shape[1], dtype=np.float64) + 1j
    y = np.arange(default_p63.matrix.shape[0], dtype=np.float64) - 0.3j
    px = candidate_p63.apply(x)
    phy = candidate_p63.apply_adjoint(y)
    assert abs(np.vdot(px, y) - np.vdot(x, phy)) <= 1e-10 * max(
        np.linalg.norm(px) * np.linalg.norm(y), 1.0
    )

    baseline64 = np.asarray(
        basix.compute_interpolation_operator(_n1e(4), _n1e(6)),
        dtype=np.complex128,
    )
    default_p64 = build_same_mesh_hcurl_transfer(6, 4)
    assert np.array_equal(default_p64.matrix, baseline64)
    with pytest.raises(ValueError, match="restricted to the explicit P6-to-P3"):
        build_same_mesh_hcurl_transfer(
            6, 4, trace_map_policy=V6_P3_CANONICAL_TRACE_MAP_POLICY
        )


def test_canonical_trace_map_matches_independent_functionals_for_72_entity_states():
    coarse, fine = _n1e(3), _n1e(6)
    baseline = np.asarray(
        basix.compute_interpolation_operator(coarse, fine), dtype=np.complex128
    )
    candidate, facts = _canonical_p63_trace_rows(coarse, fine, baseline)
    independent = _dof_functional_interpolation(coarse, fine)
    edge_rows, _face_rows, _trace = _trace_rows(fine)
    assert facts["edge_trace_rows_replaced"] == 72
    assert facts["face_owned_trace_rows_replaced"] == 360
    assert facts["trace_rows_replaced"] == 432
    assert facts["interior_rows_retained_from_basix"] == 450

    checks = []
    for edge_id, rows in enumerate(fine.entity_dofs[1]):
        for reversed_edge in (False, True):
            cell_info = (1 << (18 + edge_id)) if reversed_edge else 0
            fine_transform = _dof_transform(fine, cell_info)
            coarse_transform = _dof_transform(coarse, cell_info)
            mapped = fine_transform @ candidate @ np.linalg.inv(coarse_transform)
            direct = fine_transform @ independent @ np.linalg.inv(coarse_transform)
            defect = float(np.max(np.abs(mapped[np.asarray(rows)] - direct[np.asarray(rows)])))
            assert defect <= ROW_LIMIT
            checks.append(defect)
    for face_id in range(6):
        rows = np.asarray(fine.entity_closure_dofs[2][face_id], dtype=np.int64)
        for d4_code in range(8):
            cell_info = int(d4_code << (3 * face_id))
            fine_transform = _dof_transform(fine, cell_info)
            coarse_transform = _dof_transform(coarse, cell_info)
            mapped = fine_transform @ candidate @ np.linalg.inv(coarse_transform)
            direct = fine_transform @ independent @ np.linalg.inv(coarse_transform)
            defect = float(np.max(np.abs(mapped[rows] - direct[rows])))
            assert defect <= ROW_LIMIT
            checks.append(defect)
    assert len(checks) == 72
    assert max(checks) <= 5.0e-15

    # A direction/sign error is deliberately constructed and must fail the
    # unchanged absolute comparison with the unmodified full-cell functionals.
    reversed_wrong = candidate.copy()
    first_edge_dof = int(fine.entity_dofs[1][0][0])
    reversed_wrong[first_edge_dof, :] *= -1.0
    assert np.max(np.abs(reversed_wrong - independent)) > ROW_LIMIT
    assert edge_rows


def test_canonical_quad_transfer_full_closure_d4_and_wrong_mapping_negative():
    coarse_quad = _n1e_quadrilateral(3)
    fine_quad = _n1e_quadrilateral(6)
    transfer = _canonical_quadrilateral_n1e_transfer(coarse_quad, fine_quad)
    independent = _dof_functional_interpolation(coarse_quad, fine_quad)
    assert np.max(np.abs(transfer - independent)) <= ROW_LIMIT

    maximum_candidate_covariance = 0.0
    maximum_independent_covariance = 0.0
    for _name, linear, offset in _quad_d4_maps():
        transform3 = _quad_d4_pullback_transform(coarse_quad, linear, offset)
        transform6 = _quad_d4_pullback_transform(fine_quad, linear, offset)
        candidate_defect = float(
            np.max(np.abs(transform6 @ transfer - transfer @ transform3))
        )
        independent_defect = float(
            np.max(np.abs(transform6 @ independent - independent @ transform3))
        )
        maximum_candidate_covariance = max(maximum_candidate_covariance, candidate_defect)
        maximum_independent_covariance = max(maximum_independent_covariance, independent_defect)
        assert candidate_defect <= ROW_LIMIT
        assert independent_defect <= ROW_LIMIT
    assert maximum_candidate_covariance <= 5.0e-15
    assert maximum_independent_covariance <= 5.1e-15

    bad = transfer.copy()
    edge_columns = [int(value) for value in coarse_quad.entity_dofs[1][0]]
    bad[:, [edge_columns[0], edge_columns[1]]] = bad[:, [edge_columns[1], edge_columns[0]]]
    direct_error = float(np.max(np.abs(bad - independent)))
    covariance_error = max(
        float(
            np.max(
                np.abs(
                    _quad_d4_pullback_transform(fine_quad, linear, offset) @ bad
                    - bad @ _quad_d4_pullback_transform(coarse_quad, linear, offset)
                )
            )
        )
        for _name, linear, offset in _quad_d4_maps()
    )
    assert direct_error > ROW_LIMIT
    assert covariance_error > ROW_LIMIT


def test_saved_c2_original_and_candidate_runtime_batch8_replay():
    started_utc = datetime.now(timezone.utc).isoformat()
    if not C2_NPZ.is_file():
        pytest.skip("saved C2 NPZ is ignored and is not present in this checkout")
    assert sha256(C2_NPZ.read_bytes()).hexdigest() == C2_NPZ_SHA256
    with np.load(C2_NPZ, allow_pickle=False) as archive:
        arrays = {key: archive[key] for key in archive.files if key != "metadata_json"}
        metadata = json.loads(str(archive["metadata_json"].item()))

    pairs = np.asarray(arrays["orientation_pairs"], dtype=np.int32)
    original_matrices = np.asarray(
        arrays["orientation_transfer_matrices"], dtype=np.complex128
    )
    assert pairs.shape == (5, 2)
    assert original_matrices.shape == (5, 882, 144)
    candidate_matrices = []
    orientation_audits = []
    for fine_info, coarse_info in pairs:
        transfer = build_same_mesh_hcurl_transfer(
            6,
            3,
            fine_cell_info=int(fine_info),
            coarse_cell_info=int(coarse_info),
            trace_map_policy=V6_P3_CANONICAL_TRACE_MAP_POLICY,
        )
        assert transfer.audit["trace_map_policy"] == V6_P3_CANONICAL_TRACE_MAP_POLICY
        assert transfer.audit["candidate_vs_unmodified_independent_max_abs"] <= ROW_LIMIT
        assert transfer.audit["gate_passed"] is True
        candidate_matrices.append(transfer.matrix)
        orientation_audits.append(
            {
                "fine_cell_info": int(fine_info),
                "coarse_cell_info": int(coarse_info),
                "candidate_matrix_sha256": transfer.audit["oriented_matrix_sha256"],
                "candidate_vs_independent_max_abs": transfer.audit[
                    "candidate_vs_unmodified_independent_max_abs"
                ],
                "edge_functional_relative": transfer.audit[
                    "edge_functional_relative"
                ],
                "gradient_commuting_relative": transfer.audit[
                    "gradient_commuting_relative"
                ],
                "curl_commuting_relative": transfer.audit[
                    "curl_commuting_relative"
                ],
                "adjoint_work_relative": transfer.audit["adjoint_work_relative"],
                "gate_passed": transfer.audit["gate_passed"],
            }
        )

    original_values, batch_facts = _batch8_replay(original_matrices, arrays)
    candidate_values, candidate_batch_facts = _batch8_replay(candidate_matrices, arrays)
    saved_values = np.asarray(arrays["p6_candidate_values_raw"], dtype=np.complex128)
    candidate_cells = np.asarray(arrays["candidate_cell_index"], dtype=np.int32)
    candidate_local_rows = np.asarray(arrays["candidate_local_fine_row"], dtype=np.int32)
    candidate_global_rows = np.asarray(arrays["candidate_global_fine_rows"], dtype=np.int64)
    fine = _n1e(6)
    edge_rows, _face_rows, trace_rows = _trace_rows(fine)
    selected = np.flatnonzero(np.isin(candidate_local_rows, list(trace_rows)))
    original_summary = _shared_owner_summary(
        original_values, arrays, trace_rows, edge_rows
    )
    candidate_summary = _shared_owner_summary(
        candidate_values, arrays, trace_rows, edge_rows
    )
    saved_replay_max = float(np.max(np.abs(original_values[selected] - saved_values[selected])))

    assert saved_replay_max <= 1.0e-14
    assert original_summary["shared_row_count"] == 2412
    assert original_summary["edge_shared_row_count"] == 432
    assert original_summary["face_shared_row_count"] == 1980
    assert original_summary["max_absolute_difference"] == pytest.approx(
        3.253907165344266e-11, rel=1.0e-10, abs=1.0e-18
    )
    assert original_summary["rows_over_original_absolute_gate"] > 0
    assert candidate_summary["shared_row_count"] == 2412
    assert candidate_summary["edge_shared_row_count"] == 432
    assert candidate_summary["face_shared_row_count"] == 1980
    assert candidate_summary["max_absolute_difference"] <= ROW_LIMIT
    assert candidate_summary["max_absolute_difference"] == pytest.approx(
        3.637978807091713e-12, rel=1.0e-10, abs=1.0e-14
    )
    assert candidate_summary["rows_over_original_absolute_gate"] == 0
    assert len(orientation_audits) == 5
    assert len(candidate_cells) == len(candidate_local_rows) == len(candidate_global_rows)

    record = {
        "schema": "task39extra.v6_p3_canonical_trace_transfer_saved_c2_test.v1",
        "classification": "FOCUSED_PRODUCTION_TRANSFER_TEST_NOT_FE_QUALIFICATION_OR_PDE",
        "started_utc": started_utc,
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "npz_path": str(C2_NPZ.relative_to(ROOT)),
        "npz_sha256": C2_NPZ_SHA256,
        "input_sha256": metadata.get("input_sha256"),
        "physical_sha256": metadata.get("physical_sha256"),
        "policy": V6_P3_CANONICAL_TRACE_MAP_POLICY,
        "unchanged_absolute_owner_row_limit": ROW_LIMIT,
        "script_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "transfer_module_sha256": sha256(
            (ROOT / "src/solvers/fullspace_same_mesh_hcurl_pmg.py").read_bytes()
        ).hexdigest(),
        "affinity_readback": sorted(os.sched_getaffinity(0)),
        "math_thread_environment": {
            name: os.environ.get(name)
            for name in (
                "OMP_NUM_THREADS",
                "OPENBLAS_NUM_THREADS",
                "MKL_NUM_THREADS",
                "BLIS_NUM_THREADS",
                "NUMEXPR_NUM_THREADS",
            )
        },
        "orientation_pairs": orientation_audits,
        "batch8": {"original": batch_facts, "candidate": candidate_batch_facts},
        "original_same_order_replay_vs_saved_trace_max_abs": saved_replay_max,
        "original_same_order_replay": original_summary,
        "candidate_same_order_replay": candidate_summary,
        "result": "PASS_FOCUSED_C2_REPLAY_ONLY",
    }
    outdir = ROOT / "tmp/p3_mid_order_0p7/diagnostics/production_trace_transfer_tests"
    outdir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    output = outdir / f"saved_c2_batch8_{stamp}.json"
    output.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    record_sha256 = sha256(output.read_bytes()).hexdigest()
    print(f"P3_C2_BATCH8_RECORD={output.relative_to(ROOT)} SHA256={record_sha256}")
