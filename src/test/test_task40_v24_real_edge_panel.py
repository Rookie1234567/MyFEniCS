from __future__ import annotations

import json

import numpy as np
from scipy import sparse

from src.solvers.task40_v24_real_edge_panel import (
    _assemble_v17_edge_row_blocks,
    _array_sha256,
    _array_sha256,
    _local_trace_expansion,
    _relative_frobenius_error,
    project_edge_orbit_panel,
    write_panel_payload,
)


def test_edge_orbit_projection_uses_each_physical_transform_and_checks_offdiagonal() -> None:
    transforms = np.zeros((8, 6, 6), dtype=np.complex128)
    for orbit in range(8):
        permutation = np.roll(np.eye(6), orbit % 6, axis=1)
        signs = np.diag([(-1.0) ** ((orbit + row) % 2) for row in range(6)])
        transforms[orbit] = permutation @ signs
    native = np.zeros((48, 48), dtype=np.complex128)
    for orbit in range(8):
        rows = slice(6 * orbit, 6 * (orbit + 1))
        native[rows, rows] = (orbit + 1.0) * np.eye(6)
        if orbit < 7:
            next_rows = slice(6 * (orbit + 1), 6 * (orbit + 2))
            native[rows, next_rows] = 0.15 * np.eye(6)

    canonical, modal, dft = project_edge_orbit_panel(
        native, transforms, ky=0.37, period_y=2.4
    )
    entity_map = np.zeros((48, 48), dtype=np.complex128)
    for orbit, transform in enumerate(transforms):
        entity_map[6 * orbit : 6 * (orbit + 1), 6 * orbit : 6 * (orbit + 1)] = transform
    orbit_dft = np.kron(dft, np.eye(6))
    np.testing.assert_allclose(canonical, entity_map.conjugate().T @ native @ entity_map)
    np.testing.assert_allclose(modal, orbit_dft.conjugate().T @ canonical @ orbit_dft)
    off_diagonal_norm = np.sqrt(
        sum(
            np.linalg.norm(
                modal[6 * q : 6 * q + 6, 6 * r : 6 * r + 6]
            )
            ** 2
            for q in range(8)
            for r in range(8)
            if q != r
        )
    )
    assert off_diagonal_norm > 0.0


def test_local_trace_expansion_preserves_all_rows_and_applies_finalized_mpc_rows() -> None:
    trace_rows = np.arange(432, dtype=np.int64)
    mpc_rows = {
        10: (np.asarray([5000, 5001]), np.asarray([0.25 + 0.5j, 0.75 - 0.5j])),
        20: (np.asarray([5001]), np.asarray([1.0 + 0.0j])),
    }
    active_rows, expansion, slave_count = _local_trace_expansion(
        trace_rows, mpc_rows, index_dtype=np.dtype(np.int32)
    )
    assert expansion.shape == (432, 432)
    assert expansion.nnz == 433
    assert slave_count == 2
    assert np.all(np.diff(expansion.indptr) >= 1)
    assert 10 not in active_rows and 20 not in active_rows
    assert {5000, 5001}.issubset(set(active_rows.tolist()))
    np.testing.assert_allclose(expansion.getrow(10).data, [0.25 + 0.5j, 0.75 - 0.5j])
    np.testing.assert_allclose(expansion.getrow(20).data, [1.0 + 0.0j])


def test_v17_consumer_builds_complete_row_and_edge_self_csr_with_relative_oracles() -> None:
    from petsc4py import PETSc

    rng = np.random.default_rng(4017)
    row_count = 4
    column_count = 13
    edge_positions = np.asarray([9, 1, 7, 3], dtype=np.int64)
    native = rng.standard_normal((row_count, column_count)) + 1j * rng.standard_normal(
        (row_count, column_count)
    )
    dft = np.exp(
        2j * np.pi * np.arange(row_count)[:, None] * np.arange(row_count)[None, :]
        / row_count
    ) / np.sqrt(row_count)
    gate_events: list[str] = []

    def allocation_gate(label, facts):
        gate_events.append(str(label))
        assert int(facts.get("staging_live_bytes_upper", 0)) >= 0

    def resource_admission(label, additional_bytes):
        assert additional_bytes > 0
        return {"status": "ADMITTED", "stage": label, "bytes": additional_bytes}

    blocks, facts = _assemble_v17_edge_row_blocks(
        native,
        edge_column_positions=edge_positions,
        row_basis=dft,
        index_dtype=np.dtype(PETSc.IntType),
        allocation_gate=allocation_gate,
        resource_admission=resource_admission,
    )
    expected_row = dft.conjugate().T @ native
    expected_edge = expected_row[:, edge_positions] @ dft
    actual_row = blocks[(0, 1)].toarray()
    actual_edge = blocks[(0, 0)].toarray()
    row_error = _relative_frobenius_error(actual_row, expected_row)[0]
    edge_error = _relative_frobenius_error(actual_edge, expected_edge)[0]
    assert row_error <= 1e-11
    assert edge_error <= 1e-11
    assert facts["q_row_native_column_block_shape"] == [row_count, column_count]
    assert facts["q_edge_self_block_shape"] == [row_count, row_count]
    assert facts["q_row_relative_frobenius_error"] <= 1e-11
    assert facts["q_edge_self_relative_frobenius_error"] <= 1e-11
    assert facts["relative_error_limit"] == 1e-11
    assert facts["full_q_column_projection"] is False
    assert gate_events


def test_panel_writer_persists_every_array_and_local_witness(tmp_path) -> None:
    native = np.arange(12, dtype=np.float64).reshape(3, 4).astype(np.complex128)
    witness = np.asarray([1.0 + 2.0j, 3.0 - 1.0j])
    payload = {"native_panel": native, "local_witness_000_b_i": witness}
    hashes = {
        "local_equation_witness_payloads_sha256": {
            "local_witness_000_b_i": _array_sha256(witness)
        }
    }
    panel = {"payload": payload, "payload_hashes": hashes}
    written = write_panel_payload(tmp_path, panel)
    assert written["payload_file"] == "v24_real_edge_volume_panel.npz"
    assert written["payload_sha256"] == written["payload_hashes"]["payload_file_sha256"]
    with np.load(tmp_path / written["payload_file"], allow_pickle=False) as archive:
        np.testing.assert_array_equal(archive["native_panel"], native)
        np.testing.assert_array_equal(archive["local_witness_000_b_i"], witness)


def test_partial_checker_recomputes_d_panel_and_local_witness(tmp_path) -> None:
    import hashlib

    from scripts import task40_v20_service_workflow as service

    output = tmp_path / "numerical"
    output.mkdir()
    native = np.eye(48, dtype=np.complex128)
    dft = np.exp(
        1j
        * np.arange(8)[:, None]
        * (0.31 + 2.0 * np.pi * np.arange(8))[None, :]
        / 8.0
    ) / np.sqrt(8.0)
    dft_edge = np.kron(dft, np.eye(6))
    entity_map = np.eye(48, dtype=np.complex128)
    canonical = native.copy()
    q_row = dft_edge.conjugate().T @ native
    edge_q = q_row @ dft_edge

    A_ii = np.eye(450, dtype=np.complex128)
    A_it = np.zeros((450, 432), dtype=np.complex128)
    A_ti = np.zeros((432, 450), dtype=np.complex128)
    schur = np.eye(432, dtype=np.complex128)
    A_tt = schur.copy()
    xi_true = np.linspace(0.2, 1.0, 450).astype(np.complex128)
    xt_true = np.linspace(0.3, 1.1, 432).astype(np.complex128)
    b_i, b_t = xi_true.copy(), A_tt @ xt_true
    witness_prefix = "local_witness_000"
    witness_arrays = {
        f"{witness_prefix}_A_ii": A_ii,
        f"{witness_prefix}_A_it": A_it,
        f"{witness_prefix}_A_ti": A_ti,
        f"{witness_prefix}_A_tt": A_tt,
        f"{witness_prefix}_schur": schur,
        f"{witness_prefix}_x_i_true": xi_true,
        f"{witness_prefix}_x_t_true": xt_true,
        f"{witness_prefix}_b_i": b_i,
        f"{witness_prefix}_b_t": b_t,
        f"{witness_prefix}_x_i_recovered_initial": xi_true,
        f"{witness_prefix}_solve_b_initial": b_i,
        f"{witness_prefix}_x_i_recovered": xi_true,
        f"{witness_prefix}_solve_b_selected": b_i,
        f"{witness_prefix}_rhs_condensed": b_t,
    }

    def resource_admission(label, size):
        return {"status": "ADMITTED", "stage": label, "bytes": size}

    row_blocks, v17_facts = _assemble_v17_edge_row_blocks(
        native,
        edge_column_positions=np.arange(48),
        row_basis=dft_edge,
        index_dtype=np.dtype(np.int32),
        allocation_gate=lambda _label, _facts: None,
        resource_admission=resource_admission,
    )
    cell_projection_records = []
    cell_projection_arrays = {}
    for orbit in range(8):
        prefix = f"cell_projection_{orbit:03d}"
        trace_rows = np.concatenate(
            (
                np.arange(orbit * 6, orbit * 6 + 6, dtype=np.int64),
                np.arange(
                    1000 + orbit * 500,
                    1000 + orbit * 500 + 426,
                    dtype=np.int64,
                ),
            )
        )
        active_rows = np.arange(48, dtype=np.int64)
        expansion_data = np.ones(432, dtype=np.complex128)
        selected_rows = np.arange(orbit * 6, orbit * 6 + 6, dtype=np.int32)
        other_rows = np.setdiff1d(np.arange(48, dtype=np.int32), selected_rows)
        expansion_indices = np.concatenate(
            (selected_rows, other_rows, np.repeat(other_rows[0], 384))
        )
        expansion_indptr = np.arange(433, dtype=np.int32)
        keys = {
            "trace_global_rows": f"{prefix}_trace_global_rows",
            "active_global_rows": f"{prefix}_active_global_rows",
            "expansion_data": f"{prefix}_expansion_data",
            "expansion_indices": f"{prefix}_expansion_indices",
            "expansion_indptr": f"{prefix}_expansion_indptr",
        }
        cell_projection_arrays.update(
            {
                keys["trace_global_rows"]: trace_rows,
                keys["active_global_rows"]: active_rows,
                keys["expansion_data"]: expansion_data,
                keys["expansion_indices"]: expansion_indices,
                keys["expansion_indptr"]: expansion_indptr,
            }
        )
        cell_projection_records.append(
            {
                "record_prefix": prefix,
                "cell_id": orbit,
                "orbit_index": orbit,
                "oriented_class_key": "test-class",
                "schur_payload_key": f"{witness_prefix}_schur",
                "trace_global_rows_payload_key": keys["trace_global_rows"],
                "active_global_rows_payload_key": keys["active_global_rows"],
                "expansion_data_payload_key": keys["expansion_data"],
                "expansion_indices_payload_key": keys["expansion_indices"],
                "expansion_indptr_payload_key": keys["expansion_indptr"],
                "expansion_shape": [432, 48],
                "expansion_nnz": 432,
                "selected_edge_global_rows": list(range(orbit * 6, orbit * 6 + 6)),
                "selected_edge_expansion_columns": list(range(orbit * 6, orbit * 6 + 6)),
                "panel_row_positions": list(range(orbit * 6, orbit * 6 + 6)),
                "panel_column_positions": list(range(48)),
            }
        )
    payload = {
        "native_panel": native,
        "canonical_row_panel": canonical,
        "q_row_panel": q_row,
        "edge_self_native_panel": native,
        "edge_self_canonical_panel": native,
        "edge_self_q_panel": edge_q,
        "edge_transforms": np.repeat(np.eye(6)[None, :, :], 8, axis=0),
        "entity_map": entity_map,
        "dft": dft,
        "dft_edge": dft_edge,
        "column_global_rows": np.arange(48, dtype=np.int64),
        "q_row_csr_data": row_blocks[(0, 1)].data,
        "q_row_csr_indices": row_blocks[(0, 1)].indices,
        "q_row_csr_indptr": row_blocks[(0, 1)].indptr,
        "q_edge_csr_data": row_blocks[(0, 0)].data,
        "q_edge_csr_indices": row_blocks[(0, 0)].indices,
        "q_edge_csr_indptr": row_blocks[(0, 0)].indptr,
        **cell_projection_arrays,
        **witness_arrays,
    }
    witness_audit = {
        "status": "PASS_LOCAL_EQUATION_CONDENSE_RECOVER_WITNESS",
        "payload_prefix": witness_prefix,
        "nonzero_interior_rhs_norm": float(np.linalg.norm(b_i)),
        "full_equation_residual_relative": 0.0,
        "recovered_interior_forward_relative": 0.0,
        "condensed_trace_residual_relative": 0.0,
        "initial_state_passed": True,
        "refinement_correction_count": 0,
        "refinement_history": [{"state": "initial"}],
        "same_lu_fresh_factorizations": 1,
        "same_lu_refinement_corrections": 0,
        "same_lu_max_refinement_corrections": 3,
    }
    payload_hashes = {
        "native_panel_sha256": _array_sha256(native),
        "canonical_row_panel_sha256": _array_sha256(canonical),
        "q_row_panel_sha256": _array_sha256(q_row),
        "edge_self_q_panel_sha256": _array_sha256(edge_q),
        "entity_map_sha256": _array_sha256(entity_map),
        "dft_sha256": _array_sha256(dft),
        "column_global_rows_sha256": _array_sha256(payload["column_global_rows"]),
        "local_equation_witness_payloads_sha256": {
            name: _array_sha256(array) for name, array in witness_arrays.items()
        },
        "cell_mpc_projection_payloads_sha256": {
            name: _array_sha256(array) for name, array in cell_projection_arrays.items()
        },
    }
    panel = {
        "schema": "task40extra.review_v24_real_edge_orbit_volume_panel.v1",
        "status": "PASS_V24_REAL_EDGE_ORBIT_Q_PANEL",
        "official_result": False,
        "full_q_matrix": False,
        "full_volume_action": False,
        "pde_solved": False,
        "payload_hashes": payload_hashes,
        "payload": payload,
        "selected_entity": {
            "global_edge_ids_by_orbit": list(range(8)),
            "global_rows_by_orbit": np.arange(48, dtype=np.int64).reshape(8, 6).tolist(),
        },
        "incident_cells": {
            "cell_count": 8,
            "cell_dofs_per_cell": 882,
            "interior_rows_per_cell": 450,
            "trace_rows_per_cell": 432,
            "complete_432_trace_rows_retained_before_projection": True,
            "complete_active_trace_columns_accumulated": True,
            "active_trace_column_count": 48,
            "all_incident_cells_included_exactly_once": True,
            "projected_cell_count_by_orbit": [1] * 8,
            "cells_by_orbit": {str(orbit): [orbit] for orbit in range(8)},
        },
        "cell_mpc_projection_records": cell_projection_records,
        "local_equation_condense_recover_witnesses": {"test-class": witness_audit},
        "local_lu": {
            "oriented_classes": {
                "test-class": {
                    "fresh_factorizations": 1,
                    "iterative_refinement_corrections": 0,
                    "maximum_iterative_refinement_corrections_allowed": 3,
                }
            },
            "maximum_fresh_factorizations_per_class": 1,
            "maximum_iterative_refinement_corrections_per_class": 0,
        },
        "q_projection": {"full_q_column_projection": "NOT_RUN_FOR_NON_EDGE_COLUMNS"},
        "v17_row_tile_csr": v17_facts,
    }
    panel = write_panel_payload(output, panel)
    panel["artifact_path"] = "v24_real_edge_volume_panel.json"
    panel_path = output / panel["artifact_path"]
    panel_path.write_text(json.dumps(panel, sort_keys=True), encoding="utf-8")
    npz_path = output / panel["payload_file"]
    partial = {
        "artifact_hashes": {
            panel_path.name: {"sha256": hashlib.sha256(panel_path.read_bytes()).hexdigest()},
            npz_path.name: {"sha256": panel["payload_sha256"]},
        }
    }
    (output / "v20_partial_result.json").write_text(
        json.dumps(partial), encoding="utf-8"
    )
    probe = {
        "v24_real_edge_volume_panel": panel,
        "q_coverage": {
            "built_q_count": 0,
            "full_q_matrix_coverage": "0/8",
            "volume_qualification": "PARTIAL_REAL_EDGE_ORBIT_Q_PANEL",
            "reason": "non-edge q-column projection not run",
        },
    }
    checks = service._v24_real_edge_panel_readback_checks(
        output_directory=output, probe=probe
    )
    assert not [name for name, passed in checks.items() if not passed], {
        name: passed for name, passed in checks.items() if not passed
    }


def test_v24_d_selector_binds_prior_c_artifacts_and_operation(tmp_path) -> None:
    import hashlib

    from scripts import task40_v20_service_workflow as service

    repo = tmp_path / "repo"
    artifact_root = repo / service.V24_ARTIFACT_ROOT
    artifact_root.mkdir(parents=True)
    results = repo / "results" / "completed_c"
    results.mkdir(parents=True)
    input_path = repo / "input.dat"
    input_path.write_text("v24-d-input", encoding="utf-8")
    q0_path = artifact_root / "q0.json"
    q0_path.write_text(
        json.dumps(
            {
                "status": "PARTIAL_RECEIPT_CHECKED",
                "checker_passed": True,
                "official_result": False,
                "full_pass": False,
                "checks": {"prior_q0": True},
            }
        ),
        encoding="utf-8",
    )
    c_files = {}
    for name, content in (
        ("sample.json", b"completed C sample"),
        ("cache.npz", b"C cache bytes"),
        ("replay.npz", b"C replay bytes"),
    ):
        path = results / name
        path.write_bytes(content)
        c_files[name] = {
            "path": str(path.relative_to(repo)),
            "sha256": hashlib.sha256(content).hexdigest(),
        }
    selector = {
        "schema": "task40extra.review_v24_bounded_port_reuse_volume_selector.v1",
        "operation": "D_REAL_EDGE_PANEL",
        "campaign_window_sha256": service.TASK40_V24_CAMPAIGN_SHA256,
        "input_sha256": service._sha256_file(input_path),
        "q_only_scan_manifest_sha256": "scan-manifest",
        "q_only_checkpoint_metadata_sha256": "checkpoint-metadata",
        "q_only_checkpoint_payload_sha256": "checkpoint-payload",
        "mode_count": 32,
        "selection": "first valid actual mode for every side x global-q x s/polarization group",
        "max_cache_bytes": 536_870_912,
        "volume_trace_dimension": 432,
        "face_panel_rows": 60,
        "y_orbit_count": 8,
        "sum_duplicate_cell_integrals": True,
        "q0_partial_checker_path": str(q0_path.relative_to(repo)),
        "q0_partial_checker_sha256": service._sha256_file(q0_path),
        "c_sample_path": c_files["sample.json"]["path"],
        "c_sample_sha256": c_files["sample.json"]["sha256"],
        "c_cache_path": c_files["cache.npz"]["path"],
        "c_cache_sha256": c_files["cache.npz"]["sha256"],
        "c_replay_path": c_files["replay.npz"]["path"],
        "c_replay_sha256": c_files["replay.npz"]["sha256"],
        "c_source_sha": "a" * 40,
    }
    selector_path = artifact_root / "d_selector.json"
    selector_path.write_text(json.dumps(selector), encoding="utf-8")
    registration = {
        "version": "V24",
        "sha256": service.TASK40_V24_CAMPAIGN_SHA256,
    }
    binding = service._bind_v24_cd_selector(
        selector_path,
        input_path=input_path,
        campaign_registration=registration,
        profile=service.V24_TARGET_PROFILE,
        stop_stage="target_operator_probe",
        q_only_binding={
            "scan_manifest_sha256": "scan-manifest",
            "checkpoint_metadata_sha256": "checkpoint-metadata",
            "checkpoint_payload_sha256": "checkpoint-payload",
        },
        repo_root=repo,
    )
    assert binding["operation"] == "D_REAL_EDGE_PANEL"
    assert binding["c_sample_sha256"] == c_files["sample.json"]["sha256"]
    assert binding["c_source_sha"] == "a" * 40
