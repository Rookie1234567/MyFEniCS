from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace

import numpy as np
import pytest
from scipy import sparse


def _array_record(value: np.ndarray, path: str = "fixture.npy") -> dict:
    return {"path": path, "shape": list(value.shape), "dtype": str(value.dtype)}


def _volume_only_config():
    return SimpleNamespace(
        tags=SimpleNamespace(air=1, substrate=2, grating=3),
        eps_r=1.0 + 0.0j,
        substrate_index=1.5 + 0.0j,
        grating_index=2.0 + 0.0j,
        mu_r=1.0 + 0.0j,
        k0=1.0 + 0.0j,
    )


def _fixture(tmp_path: Path, monkeypatch):
    from src.solvers import task41_v4_volume_only_audit as audit

    class IndexMap:
        size_local = 13

        @staticmethod
        def local_to_global(rows):
            return np.asarray(rows, dtype=np.int64)

    keys = (
        (1, 1.0, 1.0, 1.0, 0),
        (2, 1.0, 1.0, 1.0, 0),
        (3, 1.0, 1.0, 1.0, 0),
    )
    cell_keys = (keys[0], keys[1], keys[2], keys[0], keys[1], keys[2])
    cells = tuple(
        SimpleNamespace(
            interior_original_dofs=np.asarray([3 + index], dtype=np.int64),
            trace_original_dofs=np.asarray([10], dtype=np.int64),
            class_key=cell_keys[index],
        )
        for index in range(6)
    )
    active = np.asarray([10, 11], dtype=np.int64)
    slave = np.asarray([12], dtype=np.int64)
    known = np.zeros(13, dtype=np.complex128)
    rhs = np.zeros(13, dtype=np.complex128)
    vectors = {
        "active_original_rows": active,
        "slave_rows": slave,
        "known_field": known,
        "native_rhs": rhs,
    }
    column_metadata = {
        name: _array_record(value, f"column_{name}.npy")
        for name, value in vectors.items()
    }

    saved_raw = {
        key: {
            "Vii": np.asarray([[index + 2.0]], dtype=np.complex128),
            "Vit": np.asarray([[index + 4.0]], dtype=np.complex128),
        }
        for index, key in enumerate(keys)
    }
    class_metadata = {
        key: {
            name: _array_record(value, f"class_{index}_{name}.npy")
            for name, value in saved_raw[key].items()
        }
        for index, key in enumerate(keys)
    }

    cell_arrays = {}
    raw_groups = []
    cell_maps = []
    for column_index in range(2):
        group_cells = []
        for local_index in range(3):
            cell_index = column_index * 3 + local_index
            key = cell_keys[cell_index]
            arrays = {
                "interior_original_rows": np.asarray([3 + cell_index], dtype=np.int64),
                "trace_original_rows": np.asarray([10], dtype=np.int64),
                "active_ids": np.asarray([0], dtype=np.int64),
                "cell_permutation_info": np.asarray([key[-1]], dtype=np.uint32),
                "trace_expansion_data": np.asarray([1.0 + 0.0j], dtype=np.complex128),
                "trace_expansion_indices": np.asarray([0], dtype=np.int32),
                "trace_expansion_indptr": np.asarray([0, 1], dtype=np.int32),
            }
            cell_arrays[(column_index, cell_index)] = arrays
            artifacts = {
                name: _array_record(value, f"cell_{cell_index}_{name}.npy")
                for name, value in arrays.items()
            }
            group_cells.append(
                {
                    "cell_index": cell_index,
                    "class_key": list(key),
                    "class_artifacts": class_metadata[key],
                    "artifacts": artifacts,
                }
            )
            cell_maps.append(
                {
                    "column": column_index,
                    "cell_index": cell_index,
                    "class_key": key,
                    **arrays,
                }
            )
        raw_groups.append(
            {
                "structure_identity_passed": True,
                "raw_matrices_are_independently_retabulated": True,
                "cells": group_cells,
            }
        )

    manifest = {
        "full_storage_rows": 13,
        "active_trace_rows": 2,
        "port_rows": 2,
        "columns": [{"artifacts": column_metadata} for _ in range(2)],
        "raw_cell_diagnostics": raw_groups,
        "local_interior_Bi_Di_exact_zero": True,
        "local_interior_Bi_Di_nonzero_entry_count": 0,
        "saved_surface_support_certificate_passed": True,
    }
    donor = {
        "manifest": manifest,
        "manifest_sha256": "fixture-manifest-sha",
        "existing_evidence_bytes": 100,
        "columns": [dict(vectors), dict(vectors)],
        "raw_classes": [
            {"class_key": key, **saved_raw[key]} for key in keys
        ],
        "cell_maps": cell_maps,
    }

    class_caches = {
        key: np.asarray([[index + 1.0]], dtype=np.complex128)
        for index, key in enumerate(keys)
    }
    owner = SimpleNamespace(
        full_rows=13,
        active_rows=2,
        appended_rows=2,
        cell_recovery_maps=cells,
        interior_lu_by_class={
            key: (
                np.asarray([[index + 2.0]], dtype=np.complex128),
                np.asarray([0], dtype=np.int32),
            )
            for index, key in enumerate(keys)
        },
        trace_from_interior_rhs_by_class=class_caches,
        interior_from_trace_by_class=class_caches,
        retained_local_schur_by_class=class_caches,
        build_audit={},
        destroyed=False,
        destroy=lambda: setattr(owner, "destroyed", True),
    )
    constraints = SimpleNamespace(
        owned_active_original_dofs=active,
        owned_active_range=(0, 2),
        slave_rows=1,
        original_to_active={10: 0, 11: 1},
        # The production implementation must use finalized MPC slaves rather
        # than iterating this full trace expansion mapping.
        expansion_by_original={10: None, 11: None, 12: None},
    )
    owner.trace_constraints = constraints

    mpc = SimpleNamespace(slaves=np.asarray([12], dtype=np.int32))
    mesh = SimpleNamespace(
        topology=SimpleNamespace(
            index_map=lambda _dimension: SimpleNamespace(size_local=6)
        )
    )
    space = SimpleNamespace(
        dofmap=SimpleNamespace(index_map=IndexMap()),
        element=SimpleNamespace(space_dimension=2, basix_element="fixture-basix-element"),
        mesh=mesh,
    )
    levels = {
        "mesh": mesh,
        "mesh_data": SimpleNamespace(cell_tags=object()),
        "spaces": {6: space},
        "floquets": {6: SimpleNamespace(mpc=mpc)},
    }

    level_calls = []
    volume_calls = []
    owner_calls = []
    tabulation_order = []
    tabulated = []

    monkeypatch.setattr(audit, "_build_same_mesh_levels", lambda *a, **k: (level_calls.append((a, k)) or levels))
    monkeypatch.setattr(audit, "_build_physical_volume_terms", lambda *a: (volume_calls.append(a) or (2, 3)))
    monkeypatch.setattr(audit.fem, "form", lambda form, **_kwargs: ("compiled", form))
    monkeypatch.setattr(audit.ufl, "TrialFunction", lambda _space: "trial")
    monkeypatch.setattr(audit.ufl, "TestFunction", lambda _space: "test")
    monkeypatch.setattr(audit.ufl, "Measure", lambda *_args, **_kwargs: "dx")
    monkeypatch.setattr(
        audit,
        "build_unconstrained_assembly_time_condensation",
        lambda *args, **kwargs: (owner_calls.append((args, kwargs)) or owner),
    )
    monkeypatch.setattr(
        audit,
        "_cell_trace_expansion",
        lambda _rows, _constraints: (
            np.asarray([0], dtype=np.int64),
            sparse.eye(1, dtype=np.complex128, format="csr"),
            True,
        ),
    )

    def tabulate(_form, _space, _tags, _owner, cell_index, *, geometry_policy=None):
        tabulation_order.append("tabulate")
        key = cell_keys[cell_index]
        raw = saved_raw[key]
        result = {
            "cell_index": cell_index,
            "K": raw["Vii"],
            "G": raw["Vit"],
            "J": np.asarray([[index_for(key) + 6.0]], dtype=np.complex128),
            "L": np.asarray([[index_for(key) + 8.0]], dtype=np.complex128),
            "hashes": {"K": f"k-{key[0]}", "G": f"g-{key[0]}"},
        }
        tabulated.append(cell_index)
        return result

    def index_for(key):
        return keys.index(key)

    monkeypatch.setattr(audit, "tabulate_volume_audit_cell", tabulate)

    def selected_cells(_owner, _rows):
        return iter(
            [
                {
                    "cell_index": index,
                    "class_key": keys[0],
                    "interior_original_dofs": cells[index].interior_original_dofs,
                    "trace_original_dofs": cells[index].trace_original_dofs,
                    "active_ids": np.asarray([0], dtype=np.int64),
                    "E": sparse.eye(1, dtype=np.complex128, format="csr"),
                }
                for index in (0, 3)
            ]
        )

    monkeypatch.setattr(audit, "iter_selected_volume_audit_cells", selected_cells)

    def allocation_gate(label, facts):
        if label == "task41_v4_raw_class_retabulation":
            tabulation_order.append("gate")

    persisted = {}

    def persist_array(name, value):
        assert name not in persisted
        array = np.asarray(value)
        persisted[name] = array.copy()
        return {"path": f"{name}.npy", "bytes": array.nbytes + 100}

    monkeypatch.setattr(audit, "TASK41_V4_DONOR_MANIFEST_SHA256", "fixture-manifest-sha")
    monkeypatch.setattr(audit, "TASK41_V4_DONOR_NPY_BYTES", 100)
    monkeypatch.setattr(audit, "TASK41_V4_FULL_STORAGE_ROWS", 13)
    monkeypatch.setattr(audit, "TASK41_V4_ACTIVE_TRACE_ROWS", 2)
    monkeypatch.setattr(audit, "TASK41_V4_APPENDED_ROWS", 2)
    monkeypatch.setattr(audit, "TASK41_V4_SELECTED_ACTIVE_ROW", 0)
    monkeypatch.setattr(audit, "TASK41_V4_SELECTED_ORIGINAL_ROW", 10)
    monkeypatch.setattr(audit, "TASK41_V4_EVIDENCE_CAP_BYTES", 2_000_000)
    monkeypatch.setattr(audit, "TASK41_V4_FREE_SPACE_FLOOR_BYTES", 0)

    return SimpleNamespace(
        audit=audit,
        donor=donor,
        owner=owner,
        levels=levels,
        volume_calls=volume_calls,
        level_calls=level_calls,
        owner_calls=owner_calls,
        tabulation_order=tabulation_order,
        tabulated=tabulated,
        allocation_gate=allocation_gate,
        persisted=persisted,
        persist_array=persist_array,
        tmp_path=tmp_path,
    )


def _v6_actual_v4_postbuild_inputs(repo_root: Path):
    receipt_path = (
        repo_root
        / "docs/task41extra_phi90_p50x50_g17x20/outcomes/"
        / "b0_v4_volume_only_attribution_20261020.json"
    )
    donor_contract = {
        "source": {"sha": "afbe91e5947ed18fb74d7105097e129c1b8b4cc7"},
        "window": {
            "sha256": "68e6d8dfcccc9dee98bc161730957dc76f70a9e2dea2ee78455b66c9d8b37c38"
        },
    }
    return receipt_path, donor_contract


def _run_v6_postbuild_reserve(worker, receipt_path, donor_contract):
    return worker._v6_postbuild_reserve_evidence(
        receipt_path,
        donor_contract=donor_contract,
        donor_contract_sha256=(
            "9e312f86cdd6b15fff9015faf4fb7dce19043fa3798a3f35cf2e57f79149713c"
        ),
        donor_manifest_sha256=(
            "f55ac594382f40662954e19521ef9922d805abc64459cc7812877b12ec618465"
        ),
        current_execution_window_sha256=(
            "ea6b38c3bc791ace068c75188a562023cae197f7016f110b0b86970891c46c8d"
        ),
    )


def test_v6_postbuild_reserve_accepts_actual_v4_receipt_across_windows():
    from src.runners import task41_p0_v4_volume_only_audit as worker

    receipt_path, donor_contract = _v6_actual_v4_postbuild_inputs(
        Path(__file__).resolve().parents[2]
    )
    evidence = _run_v6_postbuild_reserve(worker, receipt_path, donor_contract)
    historical = evidence["historical_v4_evidence_identity"]
    assert historical["campaign_window_sha256"] == donor_contract["window"]["sha256"]
    assert evidence["current_execution_window_sha256"] == (
        "ea6b38c3bc791ace068c75188a562023cae197f7016f110b0b86970891c46c8d"
    )
    assert historical["campaign_window_sha256"] != evidence[
        "current_execution_window_sha256"
    ]
    assert historical["v4_volume_consumer_contract_sha256"] == (
        "9012ffc0e80fac30f2aa1307d266366e7607ebcd11b9e0e2278bb213514e4bcd"
    )
    assert evidence["measured_service_parent_seconds"] == pytest.approx(
        1638.8259056420065
    )


def test_v6_postbuild_reserve_rejects_tampered_actual_v4_window_identity(
    tmp_path, monkeypatch
):
    import hashlib
    import json

    from src.runners import task41_p0_v4_volume_only_audit as worker

    receipt_path, donor_contract = _v6_actual_v4_postbuild_inputs(
        Path(__file__).resolve().parents[2]
    )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["identity"]["campaign_window_sha256"] = "9" * 64
    tampered_path = tmp_path / "tampered_v4_receipt.json"
    tampered_path.write_text(json.dumps(receipt, sort_keys=True) + "\n", encoding="utf-8")
    monkeypatch.setattr(
        worker,
        "TASK41_P0_V4_VOLUME_ONLY_RECEIPT_SHA256",
        hashlib.sha256(tampered_path.read_bytes()).hexdigest(),
    )

    with pytest.raises(ValueError, match="identity.campaign_window_sha256"):
        _run_v6_postbuild_reserve(worker, tampered_path, donor_contract)


def test_v5_postbuild_reserve_reads_frozen_v4_checker_watchdog_elapsed_seconds():
    import json

    from src.runners.task41_p0_v4_volume_only_audit import (
        _v4_required_checker_watchdog_elapsed_seconds,
    )

    repo_root = Path(__file__).resolve().parents[2]
    receipt_path = (
        repo_root
        / "docs/task41extra_phi90_p50x50_g17x20/outcomes/"
        / "b0_v4_volume_only_attribution_20261020.json"
    )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert (
        receipt["identity"]["campaign_window_sha256"]
        == "68e6d8dfcccc9dee98bc161730957dc76f70a9e2dea2ee78455b66c9d8b37c38"
    )
    extraction = receipt["volume_only_extraction"]
    assert extraction["status"] == "COMPLETED"
    assert _v4_required_checker_watchdog_elapsed_seconds(extraction) == pytest.approx(
        59.97374047804624
    )


def test_v5_volume_worker_exposes_disk_usage_for_evidence_gates(tmp_path):
    from src.runners import task41_p0_v4_volume_only_audit as worker

    assert worker.shutil.disk_usage(tmp_path).free > 0


def test_volume_only_owner_avoids_surface_and_persists_each_class_once(tmp_path, monkeypatch):
    case = _fixture(tmp_path, monkeypatch)

    def forbidden_surface(*_args, **_kwargs):
        raise AssertionError("volume-only extraction must not construct a surface/carrier action")

    monkeypatch.setattr(case.audit, "build_same_mesh_physical_action", forbidden_surface, raising=False)
    progress = []
    result = case.audit.build_task41_v4_volume_only_owner(
        _volume_only_config(),
        case.donor,
        case.tmp_path,
        allocation_gate=case.allocation_gate,
        progress_callback=progress.append,
        persist_array=case.persist_array,
    )

    assert case.level_calls[0][1] == {
        "include_positive_coefficients": False,
    }
    assert case.level_calls[0][0][1:] == (case.audit.MPI.COMM_SELF, (6,))
    assert len(case.volume_calls) == 1
    assert case.owner_calls[0][1]["internal_rhs_strategy"] == "stored_T"
    assert result["condensed"] is case.owner
    assert case.owner.destroyed is False
    assert len(result["class_records"]) == 1
    assert len(result["cell_records"]) == 2
    class_payload_names = [name for name in case.persisted if "volume_class_" in name]
    assert len(class_payload_names) == 9
    assert len(set(class_payload_names)) == 9
    assert result["audit"]["matrix_materialized"] is False
    assert result["audit"]["surface_or_carrier_constructed"] is False
    assert all(event["status"] in {"STARTED", "COMPLETED"} for event in progress)
    assert case.tabulation_order == [
        "gate", "tabulate", "gate", "tabulate", "gate", "tabulate"
    ]


def test_v6_volume_owner_forwards_selected_evaluator_to_actual_builder(tmp_path, monkeypatch):
    from src.solvers import task41_actual_qmetric_blocked_gram as candidate_module

    case = _fixture(tmp_path, monkeypatch)
    source_path = tmp_path / "frozen-profile.c"
    source_path.write_text("fixture only", encoding="ascii")
    created = []
    volume_form = object()
    compiled_form = object()

    class FakeCandidate:
        identity = "task41extra_actual_qmetric_blocked_gram_ffcx_profile_v1"

        def __init__(self, *args, **kwargs):
            created.append((args, kwargs, self))

    monkeypatch.setattr(
        candidate_module,
        "Task41ActualQMetricBlockedGramCandidate",
        FakeCandidate,
        raising=False,
    )
    case.audit.build_task41_v4_volume_only_owner(
        _volume_only_config(),
        case.donor,
        case.tmp_path,
        allocation_gate=case.allocation_gate,
        progress_callback=lambda _event: None,
        persist_array=case.persist_array,
        geometry_policy="mesh_actual_exact",
        raw_tensor_evaluator_kind="actual_qmetric_blocked_gram",
        ffcx_c_source_path=source_path,
        internal_rhs_strategy="same_lu_rhs_solve",
        levels=case.levels,
        volume_form=volume_form,
        compiled_form=compiled_form,
    )
    forwarded = case.owner_calls[0][1]["raw_tensor_evaluator"]
    assert forwarded is created[0][2]
    assert created[0][0][1] is volume_form
    assert created[0][0][2] is compiled_form
    assert case.owner_calls[0][0][0] is compiled_form
    assert created[0][1]["c_source_path"] == source_path
    assert created[0][1]["scratch_directory"] == case.tmp_path
    assert case.owner_calls[0][1]["geometry_policy"] == "mesh_actual_exact"
    assert case.owner_calls[0][1]["internal_rhs_strategy"] == "same_lu_rhs_solve"
    assert case.level_calls == []
    assert case.volume_calls == []


def _v9_prefix_reuse_fixture():
    from src.solvers.task41_actual_qmetric_blocked_gram import (
        Task41ActualQMetricBlockedGramCandidate,
        V6_PREFIX_SAMPLE_CELL_INDICES,
    )

    evaluator = object.__new__(Task41ActualQMetricBlockedGramCandidate)
    evaluator.prefix_qualification_records = []
    evaluator.cache_identity = (
        "task41extra_actual_qmetric_blocked_gram_ffcx_profile_v1:"
        "abf508c661fd79892922d6a0a245fcbc50afeaf7df79f4f202345fe7b634c225"
    )
    cells = tuple(V6_PREFIX_SAMPLE_CELL_INDICES)
    coordinates = np.arange(24, dtype=np.float64).reshape(8, 3)
    raw_tensor = np.arange(64 * 64, dtype=np.float64).astype(np.complex128).reshape(64, 64)
    oriented_tensor = raw_tensor * np.complex128(1.0 + 0.25j)
    arrays = {
        "coordinates": coordinates,
        "raw_tensor": raw_tensor,
        "oriented_tensor": oriented_tensor,
    }
    records = {}
    for index, cell_index in enumerate(cells):
        saved_blocks = index < 2
        records[cell_index] = {
            "cell_index": int(cell_index),
            "status": "PASS",
            "admission_eligible": True,
            "source": (
                "V4_SAVED_ACTUAL_BLOCKS"
                if saved_blocks
                else "ORIGINAL_FFCX_KERNEL_ORACLE"
            ),
            "candidate_build_seconds": 0.25 + index,
            "geometry_witness": {
                "status": (
                    "NOT_REQUIRED_V4_SAVED_ACTUAL_BLOCKS"
                    if saved_blocks
                    else "BITWISE_EQUAL"
                ),
                "source_report_sha256": "c" * 64,
            },
            "reference_artifacts": {
                "raw_tensor": {"path": f"saved/{cell_index}.npy", "sha256": "d" * 64}
            },
        }
    return evaluator, cells, arrays, records


def _v9_register_fixture_prefix_cell(
    evaluator,
    cell_index,
    arrays,
    record,
    *,
    actual_arrays=None,
    events=None,
):
    from src.runners.task40_v10_worker import _task41_v9_register_saved_prefix_record

    if events is None:
        events = []

    return _task41_v9_register_saved_prefix_record(
        cell_index=cell_index,
        actual_coordinates=(actual_arrays or arrays)["coordinates"],
        actual_raw_tensor=(actual_arrays or arrays)["raw_tensor"],
        actual_oriented_tensor=(actual_arrays or arrays)["oriented_tensor"],
        saved_coordinates=arrays["coordinates"],
        saved_raw_tensor=arrays["raw_tensor"],
        saved_oriented_tensor=arrays["oriented_tensor"],
        saved_record=record,
        saved_report_sha256="a" * 64,
        saved_index_sha256="b" * 64,
        saved_evaluator_identity=evaluator.identity,
        saved_evaluator_cache_identity=evaluator.cache_identity,
        evaluator=evaluator,
        persist_event=(events.append if events is not None else None),
    )


def test_v9_saved_v6_prefix_reuse_registers_eight_keys_into_real_evaluator_audit():
    evaluator, cells, arrays, records = _v9_prefix_reuse_fixture()
    events = []
    results = {}
    for cell_index in cells:
        result = _v9_register_fixture_prefix_cell(
            evaluator,
            cell_index,
            arrays,
            records[cell_index],
            events=events,
        )
        assert result["status"] == "PASS"
        results[cell_index] = result

    audit = evaluator.prefix_qualification_audit()
    assert audit["status"] == "PREFIX_QUALIFIED"
    assert audit["required_sample_cell_indices"] == list(cells)
    assert audit["sample_count"] == 8
    assert audit["required_sample_count"] == 8
    assert audit["geometry_witness_count"] == 6
    assert audit["full_admission_eligible"] is True
    assert len(events) == 16
    audited_by_cell = {record["cell_index"]: record for record in audit["records"]}
    assert set(audited_by_cell) == set(cells)
    for cell_index in cells:
        original = records[cell_index]
        inherited = audited_by_cell[cell_index]
        assert inherited["status"] == "PASS"
        assert inherited["source"] == original["source"]
        assert inherited["geometry_witness"] == original["geometry_witness"]
        assert inherited["reference_artifacts"] == original["reference_artifacts"]
        assert inherited["candidate_build_seconds"] == original["candidate_build_seconds"]
        assert inherited["qualification_origin"]["v6_record_sha256"] == results[
            cell_index
        ]["saved_v6_record_sha256"]
        assert results[cell_index]["evaluator_audit"]["sample_count"] == (
            list(cells).index(cell_index) + 1
        )
    assert records[cells[0]]["source"] == "V4_SAVED_ACTUAL_BLOCKS"


def test_v9_saved_v6_prefix_reuse_missing_key_stays_ineligible():
    evaluator, cells, arrays, records = _v9_prefix_reuse_fixture()
    for cell_index in cells[:-1]:
        result = _v9_register_fixture_prefix_cell(
            evaluator, cell_index, arrays, records[cell_index]
        )
        assert result["status"] == "PASS"
    audit = evaluator.prefix_qualification_audit()
    assert audit["status"] == "PREFIX_QUALIFICATION_INCOMPLETE_OR_FAILED"
    assert audit["sample_count"] == 7
    assert audit["full_admission_eligible"] is False


@pytest.mark.parametrize("failure", ["array_mismatch", "wrong_source"])
def test_v9_saved_v6_prefix_reuse_failure_never_registers_pass(failure):
    evaluator, cells, arrays, records = _v9_prefix_reuse_fixture()
    cell_index = cells[0]
    actual_arrays = dict(arrays)
    if failure == "array_mismatch":
        actual_arrays["raw_tensor"] = arrays["raw_tensor"].copy()
        actual_arrays["raw_tensor"][0, 0] += 1.0
    elif failure == "wrong_source":
        records[cell_index] = dict(
            records[cell_index], source="UNVERIFIED_SOURCE", geometry_witness=None
        )
    events = []
    result = _v9_register_fixture_prefix_cell(
        evaluator,
        cell_index,
        arrays,
        records[cell_index],
        actual_arrays=actual_arrays,
        events=events,
    )
    assert result["status"] == "FAIL"
    assert result["event_stage"] == "COMPARE_FAILED"
    assert evaluator.prefix_qualification_records == []
    assert evaluator.prefix_qualification_audit()["full_admission_eligible"] is False
    assert events[0]["status"] == "FAIL"
    if failure == "array_mismatch":
        assert result["validation"]["arrays_match"] is False
    if failure == "wrong_source":
        assert result["validation"]["source_and_witness_match"] is False


def test_volume_only_owner_rejects_unknown_internal_rhs_strategy_before_build(
    tmp_path, monkeypatch
):
    case = _fixture(tmp_path, monkeypatch)

    with pytest.raises(ValueError, match="unknown Task41 internal RHS strategy"):
        case.audit.build_task41_v4_volume_only_owner(
            _volume_only_config(),
            case.donor,
            case.tmp_path,
            allocation_gate=case.allocation_gate,
            progress_callback=lambda _event: None,
            persist_array=case.persist_array,
            internal_rhs_strategy="unqualified",
        )

    assert case.level_calls == []
    assert case.owner_calls == []
    assert case.persisted == {}


def test_volume_only_owner_rejects_partial_reused_fe_setup_before_build(
    tmp_path, monkeypatch
):
    case = _fixture(tmp_path, monkeypatch)

    with pytest.raises(ValueError, match="requires both levels and volume_form"):
        case.audit.build_task41_v4_volume_only_owner(
            _volume_only_config(),
            case.donor,
            case.tmp_path,
            allocation_gate=case.allocation_gate,
            progress_callback=lambda _event: None,
            persist_array=case.persist_array,
            levels=case.levels,
        )

    assert case.level_calls == []
    assert case.owner_calls == []
    assert case.persisted == {}


def test_volume_only_owner_can_reuse_identity_evidence_without_duplicate_arrays(
    tmp_path, monkeypatch
):
    case = _fixture(tmp_path, monkeypatch)

    result = case.audit.build_task41_v4_volume_only_owner(
        _volume_only_config(),
        case.donor,
        case.tmp_path,
        allocation_gate=case.allocation_gate,
        progress_callback=lambda _event: None,
        persist_array=case.persist_array,
        persist_selected_evidence=False,
    )

    assert result["condensed"] is case.owner
    assert case.owner.destroyed is False
    assert result["class_records"]
    assert result["cell_records"]
    assert all(not item["artifacts"] for item in result["class_records"])
    assert all(not item["artifacts"] for item in result["cell_records"])
    assert result["audit"]["selected_evidence_persisted"] is False
    assert result["audit"]["evidence_bytes_added"] == 0
    assert case.persisted == {}


def test_volume_only_owner_rejects_fresh_numbering_mismatch_before_persist(tmp_path, monkeypatch):
    case = _fixture(tmp_path, monkeypatch)
    case.donor["columns"][0]["active_original_rows"] = np.asarray([9, 11], dtype=np.int64)
    progress = []

    with pytest.raises(ValueError, match="fresh Task41 V4 numbering or donor vectors differ"):
        case.audit.build_task41_v4_volume_only_owner(
            _volume_only_config(),
            case.donor,
            case.tmp_path,
            allocation_gate=case.allocation_gate,
            progress_callback=progress.append,
            persist_array=case.persist_array,
        )

    assert case.owner.destroyed is True
    assert case.persisted == {}
    assert case.tabulated == []
    assert progress[-1]["status"] == "FAILED"


def test_volume_identity_replays_production_volume_and_two_state_residuals(tmp_path, monkeypatch):
    from src.solvers import task41_v4_volume_only_audit as audit

    @dataclass
    class TinyOwner:
        full_rows: int
        active_rows: int
        appended_rows: int
        owned_appended_rows: int
        trace_constraints: object
        cell_recovery_maps: tuple[object, ...]
        build_audit: dict

    constraints = SimpleNamespace(
        owned_active_original_dofs=np.asarray([0], dtype=np.int64),
        original_to_active={0: 0},
        expansion_by_original={0: ([0], np.asarray([1.0 + 0.0j]))},
    )
    owner = TinyOwner(
        full_rows=2,
        active_rows=1,
        appended_rows=1,
        owned_appended_rows=1,
        trace_constraints=constraints,
        cell_recovery_maps=(
            SimpleNamespace(
                interior_original_dofs=np.asarray([1], dtype=np.int32),
                trace_original_dofs=np.asarray([0], dtype=np.int32),
            ),
        ),
        build_audit={},
    )
    action_construction = []

    class FakeP6Action:
        def __init__(self, condensed, *, H_p):
            action_construction.append((condensed, H_p.copy()))
            assert condensed.appended_rows == condensed.owned_appended_rows == 0
            assert H_p.shape == (0, 0)
            self.destroyed = False

        @staticmethod
        def apply(source):
            return np.asarray([2.5 * source[0]], dtype=np.complex128)

        @staticmethod
        def reduce_rhs(rhs, *, rhs_is_mpc_dual):
            assert rhs_is_mpc_dual is True
            return np.asarray([rhs[0] - 1.5 * rhs[1]], dtype=np.complex128)

        def destroy(self):
            self.destroyed = True

    monkeypatch.setattr(audit, "P6CellCondensedAction", FakeP6Action)
    active = np.asarray([0], dtype=np.int64)
    slaves = np.asarray([], dtype=np.int64)
    known = np.asarray([0.2, 0.3], dtype=np.complex128)
    native_rhs = np.asarray([0.75, 0.4], dtype=np.complex128)
    volume_rhs = np.asarray([0.7, 0.4], dtype=np.complex128)
    col = {
        "active_original_rows": active,
        "slave_rows": slaves,
        "known_field": known,
        "native_rhs": native_rhs,
        "native_volume_rhs": volume_rhs,
        "b_alpha_rows": np.asarray([0], dtype=np.int64),
        "b_alpha_values": np.asarray([0.05], dtype=np.complex128),
        "states": [
            {
                "label": "j0",
                "storage": np.asarray([0.2, 0.3], dtype=np.complex128),
                "native_volume_action": np.asarray([1.7, 0.8], dtype=np.complex128),
                "native_volume_residual": np.asarray([-1.0, -0.4], dtype=np.complex128),
            },
            {
                "label": "j3",
                "storage": np.asarray([0.2, 0.1], dtype=np.complex128),
                "native_volume_action": np.asarray([1.1, 0.4], dtype=np.complex128),
                "native_volume_residual": np.asarray([-0.4, 0.0], dtype=np.complex128),
            },
        ],
    }
    donor = {
        "existing_evidence_bytes": 100,
        "columns": [col, col],
        "attribution": {
            "joint": {
                "p6_result": np.asarray([[0.55, 0.55], [0.2, 0.2]], dtype=np.complex128),
                "reduced_rhs": np.asarray([[0.15, 0.15], [0.2, 0.2]], dtype=np.complex128),
                "port_rhs": np.asarray([[0.2, 0.2]], dtype=np.complex128),
            },
            "local_class_identities": [],
        },
    }
    saved = {}

    def persist(name, array):
        saved[name] = np.asarray(array).copy()
        return {"path": name + ".npy", "bytes": saved[name].nbytes + 4096}

    report = audit.audit_task41_v4_volume_identity(
        owner,
        donor,
        allocation_gate=lambda *_args: None,
        progress_callback=lambda *_args: None,
        persist_array=persist,
        output_directory=tmp_path,
    )

    assert report["completed"] is True
    assert report["global_volume_matrix_materialized"] is False
    assert report["dense_port_matrix_materialized"] is False
    assert len(action_construction) == 1
    assert len(saved) == 14
    for state in report["columns"][0]["states"]:
        assert state["volume_identity_dvol_plus_reduce_rvol"]["absolute_l2"] == pytest.approx(0.0)
        assert state["full_identity_dfull_plus_reduce_rfull"]["absolute_l2"] == pytest.approx(0.0)
        assert state["rhs_split_roundoff_native_rhs_minus_Balpha_minus_volume_rhs"]["absolute_l2"] == pytest.approx(0.0)
    assert report["columns"][0]["replayed_full_d_trace_and_original_gate"]["same_original_1e_11_gate_passed"] is False


@pytest.mark.parametrize(
    ("candidate_identity", "artifact_prefix", "attribution_prefix", "expected_schema"),
    [
        (None, "task41_p0_v5_candidate", "task41_p0_v5_attribution", "task41.p0.v5.global_geometry_native_elimination_attribution.v1"),
        (
            "task41extra_actual_qmetric_blocked_gram_ffcx_profile_v1",
            "task41_p0_v6_qmetric_candidate",
            "task41_p0_v6_qmetric_candidate_attribution",
            "task41.p0.v6.global_geometry_native_elimination_attribution.v1",
        ),
    ],
)
def test_attribution_reconstructs_nonzero_complex_mpc_slave_trace(
    candidate_identity, artifact_prefix, attribution_prefix, expected_schema
):
    from src.solvers.task41_v4_volume_only_audit import (
        Task41V5VolumeAttributionAccumulator,
    )

    K = np.asarray([[2.0 + 0.3j]], dtype=np.complex128)
    G = np.asarray([[0.2 + 0.1j, -0.4 + 0.2j]], dtype=np.complex128)
    J = np.asarray([[0.3 - 0.1j], [0.2 + 0.25j]], dtype=np.complex128)
    L = np.asarray(
        [[1.0 + 0.1j, 0.15j], [0.2 + 0.1j, 0.7 - 0.05j]],
        dtype=np.complex128,
    )
    R = -np.linalg.solve(K, G)
    T_exact = -J @ np.linalg.inv(K)
    S_exact = L + J @ R
    T = T_exact + np.asarray([[0.025 + 0.015j], [-0.01 + 0.02j]])
    S = S_exact + np.asarray(
        [[0.04 - 0.02j, 0.015j], [-0.01 + 0.01j, 0.03 + 0.025j]]
    )
    phase = 0.6 + 0.8j
    expansion = sparse.csr_matrix(
        np.asarray([[1.0 + 0.0j], [phase]], dtype=np.complex128)
    )
    active_original = np.asarray([1], dtype=np.int64)
    active_ids = np.asarray([0], dtype=np.int64)
    interior_positions = np.asarray([0], dtype=np.int64)
    trace_positions = np.asarray([1, 2], dtype=np.int64)
    original_dofs = np.asarray([0, 1, 2], dtype=np.int64)
    u_i = 0.4 - 0.2j
    active_value = 0.7 + 0.1j
    physical_trace = expansion @ np.asarray([active_value])
    beta = 0.13 - 0.07j
    native_volume_rhs = np.asarray(
        [0.9 + 0.2j, 0.6 - 0.1j, 0.0j], dtype=np.complex128
    )
    native_rhs = native_volume_rhs.copy()
    native_rhs[1] += beta
    g_volume = (
        native_volume_rhs[1]
        + (expansion.conj().T @ (T @ native_volume_rhs[0:1])).reshape(-1)[0]
    )
    s_volume = (expansion.conj().T @ (S @ physical_trace)).reshape(-1)[0]
    d_volume = s_volume - g_volume
    # Build full P6 and reduced RHS from S t + B-alpha and the actual reducer.
    candidate_full_action = s_volume + beta
    candidate_full_reduced_rhs = g_volume + beta
    d_full = candidate_full_action - candidate_full_reduced_rhs
    assert np.linalg.norm(J + T @ K) > 1.0e-3
    assert np.linalg.norm(S - L - T @ G) > 1.0e-3
    states = [
        {
            "label": "j0",
            "storage": np.asarray([u_i, active_value, 0.0j], dtype=np.complex128),
            "native_volume_action": np.asarray(
                [0.8 - 0.1j, 0.3 + 0.05j, 0.0j], dtype=np.complex128
            ),
        },
        {
            "label": "j3",
            "storage": np.asarray([-0.2 + 0.45j, active_value, 0.0j], dtype=np.complex128),
            "native_volume_action": np.asarray(
                [0.42 + 0.17j, 0.21 - 0.11j, 0.0j], dtype=np.complex128
            ),
        },
    ]
    donor = {
        "columns": [
            {
                "active_original_rows": active_original,
                "native_rhs": native_rhs,
                "native_volume_rhs": native_volume_rhs,
                "b_alpha_rows": np.asarray([1], dtype=np.int64),
                "b_alpha_values": np.asarray([beta], dtype=np.complex128),
                "states": states,
            },
            {
                "active_original_rows": active_original,
                "native_rhs": native_rhs,
                "native_volume_rhs": native_volume_rhs,
                "b_alpha_rows": np.asarray([1], dtype=np.int64),
                "b_alpha_values": np.asarray([beta], dtype=np.complex128),
                "states": states,
            },
        ]
    }
    accumulator = Task41V5VolumeAttributionAccumulator(
        donor,
        artifact_prefix=artifact_prefix,
        attribution_prefix=attribution_prefix,
        candidate_identity=candidate_identity,
    )
    accumulator.observe(
        0,
        np.zeros((8, 3), dtype=np.float64),
        {"K": K, "G": G, "J": J, "L": L},
        {
            "original_dofs": original_dofs,
            "interior_positions": interior_positions,
            "trace_positions": trace_positions,
            "trace_expansion": expansion,
            "active_ids": active_ids,
            "R": R,
            "T": T,
            "S": S,
        },
    )
    accumulator.admit(active_rows=1)
    candidate_p6 = np.full((1, 2), candidate_full_action, dtype=np.complex128)
    candidate_reduced = np.full((1, 2), candidate_full_reduced_rhs, dtype=np.complex128)
    saved_artifacts = []

    def persist(name, values):
        saved_artifacts.append(name)
        return {"path": name + ".npy", "bytes": np.asarray(values).nbytes}

    report = accumulator.finalize(
        candidate_p6,
        candidate_reduced,
        active_rows=1,
        candidate_d_volume_columns=[
            np.asarray([d_volume], dtype=np.complex128),
            np.asarray([d_volume], dtype=np.complex128),
        ],
        persist_array=persist,
    )

    assert states[0]["storage"][2] == 0.0j
    assert physical_trace[1] == pytest.approx(phase * active_value)
    assert report["global_closure_status"] == "DIAGNOSTIC_ONLY"
    assert report["schema"] == expected_schema
    assert f"{attribution_prefix}_col0_j0_T_r_i" in saved_artifacts
    assert report["slave_trace_reconstruction"].startswith("local E times")
    for column in report["columns"]:
        for result in column["states"]:
            v7 = result["v7_formula_diagnostics"]
            assert result["closure_difference"]["absolute_l2"] == pytest.approx(abs(beta))
            assert v7["legacy_closure_minus_beta_active"]["absolute_l2"] < 1.0e-13
            assert v7["corrected_full_closure"]["absolute_l2"] < 1.0e-13
            assert v7["corrected_volume_closure"]["absolute_l2"] < 1.0e-13
            assert v7["epsilon_rhs_native_minus_volume_minus_Balpha"]["absolute_l2"] == pytest.approx(0.0)
            assert v7["d_hat_volume_minus_saved_d_volume"]["absolute_l2"] < 1.0e-13
            assert v7["d_hat_full_minus_candidate_d_full"]["absolute_l2"] < 1.0e-13
            assert result["closure_relative_to_accumulation_scale"] == pytest.approx(
                abs(beta) / result["accumulation_scale_l2_sum"]
            )


@pytest.mark.parametrize(
    ("geometry_policy", "port_error", "candidate_identity", "artifact_prefix"),
    (
        ("canonical", 0.0, None, "task41_p0_v4_volume"),
        ("mesh_actual_exact", 0.0, None, "task41_p0_v5_candidate"),
        ("mesh_actual_exact", 1.0e-6, None, "task41_p0_v5_candidate"),
        (
            "mesh_actual_exact",
            0.0,
            "task41extra_actual_qmetric_blocked_gram_ffcx_profile_v1",
            "task41_p0_v6_qmetric_candidate",
        ),
    ),
)
def test_volume_identity_replays_real_p6_action_and_rhs_reducer(
    tmp_path, geometry_policy, port_error, candidate_identity, artifact_prefix
):
    from mpi4py import MPI
    from scipy.linalg import lu_factor

    from src.solvers.hcurl_assembly_time_condensation import (
        AssemblyTimeCondensedSystem,
        CellRecoveryMap,
    )
    from src.solvers.task41_v4_volume_only_audit import audit_task41_v4_volume_identity

    key = (0,)
    K = np.asarray([[2.0 + 0.0j]], dtype=np.complex128)
    Vit = np.asarray([[0.5 + 0.0j]], dtype=np.complex128)
    Vti = np.asarray([[0.25 + 0.0j]], dtype=np.complex128)
    L = np.asarray([[2.5 + 0.0j]], dtype=np.complex128)
    factor = lu_factor(K)
    recovery = -np.linalg.solve(K, Vit)
    trace_from_rhs = -Vti @ np.linalg.solve(K, np.eye(1, dtype=np.complex128))
    schur = L + Vti @ recovery
    active_rows = np.asarray([1], dtype=np.int32)
    constraints = SimpleNamespace(
        owned_active_original_dofs=active_rows,
        original_to_active={1: 0},
        expansion_by_original={
            1: (np.asarray([0], dtype=np.int32), np.asarray([1.0 + 0.0j]))
        },
    )
    owner = AssemblyTimeCondensedSystem(
        matrix=None,
        owned_trace_original_dofs=np.asarray([1], dtype=np.int32),
        original_to_trace={1: 0},
        trace_constraints=constraints,
        cell_recovery_maps=(
            CellRecoveryMap(
                interior_original_dofs=np.asarray([0], dtype=np.int32),
                trace_original_dofs=np.asarray([1], dtype=np.int32),
                class_key=key,
            ),
        ),
        interior_from_trace_by_class={key: recovery},
        interior_lu_by_class={key: factor},
        interior_rhs_projection_by_class={key: trace_from_rhs},
        interior_solution_embedding_by_class={key: recovery},
        trace_from_interior_rhs_by_class={key: trace_from_rhs},
        interior_residual_projection_by_class={key: trace_from_rhs},
        full_rows=2,
        trace_rows=1,
        active_rows=1,
        appended_rows=1,
        interior_rows=1,
        active_interior_rows=1,
        build_audit={
            "geometry_policy": geometry_policy,
            **(
                {
                    "raw_tensor_evaluator": {
                        "implementation": candidate_identity,
                        "cache_identity": "task41-v6-test-cache-identity",
                    }
                }
                if candidate_identity is not None
                else {}
            ),
        },
        comm=MPI.COMM_SELF,
        owned_active_rows=1,
        owned_appended_rows=1,
        retained_local_schur_by_class={key: schur},
    )

    def apply_native_volume(storage):
        interior, trace = storage
        return np.asarray(
            [K[0, 0] * interior + Vit[0, 0] * trace,
             Vti[0, 0] * interior + L[0, 0] * trace],
            dtype=np.complex128,
        )

    columns = []
    p6 = np.zeros((2, 2), dtype=np.complex128)
    reduced = np.zeros_like(p6)
    port_rhs = np.asarray([[0.23 + 0.09j, -0.11 + 0.04j]], dtype=np.complex128)
    for index, (trace, interior, refined, b_alpha) in enumerate(
        (
            (0.4 + 0.2j, 0.2 + 0.1j, -0.1 + 0.03j, 0.05 + 0.02j),
            (-0.25 + 0.15j, -0.1 + 0.05j, 0.07 - 0.02j, -0.03 + 0.04j),
        )
    ):
        known = np.asarray([0.0j, trace], dtype=np.complex128)
        j0_storage = np.asarray([interior, trace], dtype=np.complex128)
        j3_storage = np.asarray([refined, trace], dtype=np.complex128)
        j0_action = apply_native_volume(j0_storage)
        j3_action = apply_native_volume(j3_storage)
        # This interior-only perturbation is annihilated by the production
        # reducer, so the volume RHS has a nonzero raw residual but the same
        # condensed active RHS as S*t.
        volume_rhs = j0_action + np.asarray([0.125 + 0.0j, 0.015625 + 0.0j])
        native_rhs = volume_rhs.copy()
        native_rhs[1] += b_alpha
        p6[0, index] = (schur @ np.asarray([trace]))[0] + b_alpha
        p6[1, index] = port_rhs[0, index]
        reduced[0, index] = p6[0, index]
        reduced[1, index] = port_rhs[0, index]
        columns.append(
            {
                "active_original_rows": active_rows.copy(),
                "slave_rows": np.empty(0, dtype=np.int32),
                "known_field": known,
                "native_rhs": native_rhs,
                "native_volume_rhs": volume_rhs,
                "b_alpha_rows": np.asarray([1], dtype=np.int32),
                "b_alpha_values": np.asarray([b_alpha], dtype=np.complex128),
                "states": [
                    {
                        "label": "j0",
                        "storage": j0_storage,
                        "native_volume_action": j0_action,
                        "native_volume_residual": volume_rhs - j0_action,
                    },
                    {
                        "label": "j3",
                        "storage": j3_storage,
                        "native_volume_action": j3_action,
                        "native_volume_residual": volume_rhs - j3_action,
                    },
                ],
            }
        )
    saved_reduced = reduced.copy()
    if port_error:
        saved_reduced[1, 0] += port_error
    donor = {
        "existing_evidence_bytes": 0,
        "columns": columns,
        "attribution": {
            "joint": {"p6_result": p6, "reduced_rhs": saved_reduced, "port_rhs": port_rhs},
            "local_class_identities": [],
        },
    }
    persisted = {}

    def persist(name, values):
        persisted[name] = np.asarray(values).copy()
        return {"path": name + ".npy", "bytes": persisted[name].nbytes + 4096}

    report = audit_task41_v4_volume_identity(
        owner,
        donor,
        allocation_gate=lambda *_args: None,
        progress_callback=lambda *_args: None,
        persist_array=persist,
        output_directory=tmp_path,
        native_volume_apply=(
            apply_native_volume if geometry_policy == "mesh_actual_exact" else None
        ),
        artifact_prefix=artifact_prefix,
        candidate_identity=candidate_identity,
        candidate_cache_identity=(
            "task41-v6-test-cache-identity" if candidate_identity is not None else None
        ),
    )

    assert report["completed"] is True
    assert report["production_action"] == "P6CellCondensedAction_active_only_shared_owner_caches"
    assert report["saved_port_rows_reused"] is True
    assert report["candidate_evaluator_identity"] == candidate_identity
    assert report["candidate_evaluator_cache_identity"] == (
        "task41-v6-test-cache-identity" if candidate_identity is not None else None
    )
    if geometry_policy == "mesh_actual_exact":
        assert len(persisted) == 20
        assert report["candidate_recovery_gate"]["native_volume_action_count"] == 2
        assert report["candidate_recovery_gate"]["status"] == "ACTUAL_COORDINATES_INSUFFICIENT"
        assert set(
            name
            for name in persisted
            if "candidate_recovered_storage" in name
            or "candidate_native_volume_residual" in name
        ) == {
            f"{artifact_prefix}_recovered_storage_col0",
            f"{artifact_prefix}_recovered_storage_col1",
            f"{artifact_prefix}_native_volume_residual_col0",
            f"{artifact_prefix}_native_volume_residual_col1",
        }
        np.testing.assert_array_equal(
            persisted[f"{artifact_prefix}_full_p6"], p6
        )
        expected_reduced = saved_reduced.copy()
        np.testing.assert_allclose(
            persisted[f"{artifact_prefix}_full_reduced_rhs"],
            expected_reduced,
            rtol=0.0,
            atol=1.0e-15,
        )
        candidate_gate = report["candidate_full_action_gate"]
        assert candidate_gate["status"] == (
            "PASS" if port_error == 0.0 else "ACTUAL_COORDINATES_INSUFFICIENT"
        )
        assert [item["frozen_denominator"] for item in candidate_gate["columns"]] == [
            2225.481253487629,
            2225.4807123031883,
        ]
        assert all(
            item["dynamic_gate_passed"] and item["frozen_gate_passed"]
            for item in candidate_gate["columns"]
        ) is (port_error == 0.0)
    else:
        assert len(persisted) == 14
        assert report["candidate_full_action_gate"] is None
        assert report["candidate_recovery_gate"] is None
    for column_index, column in enumerate(report["columns"]):
        assert column["replayed_full_d_trace_and_original_gate"]["same_original_1e_11_gate_passed"] is (
            port_error == 0.0 or column_index == 1
        )
        for state in column["states"]:
            assert state["volume_identity_dvol_plus_reduce_rvol"]["absolute_l2"] < 1.0e-13
            assert state["full_identity_dfull_plus_reduce_rfull"]["absolute_l2"] < 1.0e-13
            assert state["rhs_split_roundoff_native_rhs_minus_Balpha_minus_volume_rhs"]["absolute_l2"] < 1.0e-13

def _task41_v9_compact_terminal_fixture(
    tmp_path,
    monkeypatch,
    *,
    action_passes: bool,
    missing_numerical_output: bool = False,
    service_repo_root=None,
):
    from src.runners import task41_p0_checker, task41_p0_contract
    from src.solvers import task41_v4_volume_only_audit as audit

    case = _fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(audit, "TASK41_V4_ACTIVE_TRACE_ROWS", 2)
    monkeypatch.setattr(audit, "TASK41_V4_APPENDED_ROWS", 2)
    monkeypatch.setattr(audit, "TASK41_V4_FULL_STORAGE_ROWS", 13)
    monkeypatch.setattr(
        audit,
        "TASK41_V9_COMPACT_EVIDENCE_RESERVE_BYTES",
        2 * (2 + 2) * 2 * 16 + 6 * 13 * 16 + 10 * 4096,
    )
    monkeypatch.setattr(audit, "TASK41_V5_FROZEN_DENOMINATORS", (11.0, 13.0))
    monkeypatch.setattr(audit.shutil, "disk_usage", lambda _path: SimpleNamespace(free=10**12))
    monkeypatch.setattr(
        audit,
        "replace",
        lambda owner, **changes: SimpleNamespace(**{**vars(owner), **changes}),
    )
    owner = case.owner
    owner.internal_rhs_strategy = "same_lu_rhs_solve"
    owner.build_audit = {"geometry_policy": "mesh_actual_exact"}
    owner.trace_constraints.owned_active_original_dofs = np.asarray([10, 11], dtype=np.int64)
    donor = case.donor
    donor["manifest_sha256"] = "fixture-manifest-sha256"
    donor["existing_evidence_bytes"] = 100
    donor["prior_new_evidence_bytes"] = 20
    zeros = np.zeros(13, dtype=np.complex128)
    for column_index, column in enumerate(donor["columns"]):
        known = zeros.copy()
        known[10] = 1.0 + column_index
        known[11] = 2.0 + 2.0 * column_index
        column.update(
            {
                "known_field": known,
                "native_rhs": zeros.copy(),
                "native_volume_rhs": zeros.copy(),
                "b_alpha_rows": np.empty(0, dtype=np.int64),
                "b_alpha_values": np.empty(0, dtype=np.complex128),
                "states": [{"native_volume_residual": zeros.copy()}],
            }
        )
    donor["attribution"] = {
        "joint": {
            "p6_result": np.zeros((4, 2), dtype=np.complex128),
            "reduced_rhs": np.zeros((4, 2), dtype=np.complex128),
            "port_rhs": np.zeros((2, 2), dtype=np.complex128),
        }
    }
    if service_repo_root is not None:
        from src.runners.task41_p0_contract import TASK41_B0_V9_VOLUME_DONOR_RUN_RELATIVE

        donor_run = Path(service_repo_root) / TASK41_B0_V9_VOLUME_DONOR_RUN_RELATIVE
        donor_run.mkdir(parents=True, exist_ok=True)
        donor_arrays = []
        for index in range(2):
            artifact_path = donor_run / f"fixture-donor-{index}.npy"
            artifact_path.write_bytes(f"fixture donor array {index}\n".encode())
            donor_arrays.append(
                {
                    "path": str(artifact_path.relative_to(donor_run)),
                    "bytes": artifact_path.stat().st_size,
                    "sha256": hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
                    "shape": [1],
                    "dtype": "complex128",
                }
            )
        donor_manifest_path = donor_run / "fixture_manifest.json"
        donor_manifest_path.write_text(
            json.dumps({"fixture_arrays": donor_arrays}, sort_keys=True), encoding="utf-8"
        )
        donor_manifest_record = {
            "path": str(donor_manifest_path.relative_to(donor_run)),
            "bytes": donor_manifest_path.stat().st_size,
            "sha256": hashlib.sha256(donor_manifest_path.read_bytes()).hexdigest(),
        }
        donor_summary_path = donor_run / "task40_v10_p6_candidate_summary.json"
        donor_summary_path.write_text(
            json.dumps({"b0_recovery_evidence": {"manifest": donor_manifest_record}}),
            encoding="utf-8",
        )
        donor["manifest_sha256"] = donor_manifest_record["sha256"]
        donor["existing_evidence_bytes"] = sum(item["bytes"] for item in donor_arrays)

    class FakeP6Action:
        def __init__(self, condensed, *, H_p):
            assert condensed.appended_rows == 0
            assert H_p.shape == (0, 0)

        @staticmethod
        def apply(_source):
            return np.zeros(2, dtype=np.complex128)

        @staticmethod
        def reduce_rhs(_rhs, *, rhs_is_mpc_dual):
            assert rhs_is_mpc_dual is True
            return np.zeros(2, dtype=np.complex128) if action_passes else np.ones(2, dtype=np.complex128)

        @staticmethod
        def recover_storage(active_rhs, *, full_rhs, expand_trace):
            assert expand_trace is False
            result = np.zeros_like(full_rhs)
            result[10:12] = active_rhs
            return result

        @staticmethod
        def refine_internal_storage_with_native_volume_residual(
            initial_storage,
            _full_rhs,
            _native_volume_apply,
            *,
            initial_volume_action,
            initial_residual,
            forward_reference,
            on_state,
            max_steps,
        ):
            assert max_steps == 3
            storage = np.array(initial_storage, copy=True)
            action = np.array(initial_volume_action, copy=True)
            residual = np.array(initial_residual, copy=True)
            assert np.array_equal(storage, forward_reference)
            on_state(
                0,
                storage,
                action,
                residual,
                {
                    "forward_relative_error": 0.0,
                    "native_volume_residual_norm": 0.0,
                    "native_volume_residual_relative": 0.0,
                    "native_internal_residual_relative": 0.0,
                },
            )
            return {
                "storage_solution": storage,
                "native_volume_action": action,
                "native_volume_residual": residual,
            }

        @staticmethod
        def destroy():
            return None

    monkeypatch.setattr(audit, "P6CellCondensedAction", FakeP6Action)
    if service_repo_root is None:
        run_root = tmp_path / "consumer-run"
    else:
        run_root = (
            Path(service_repo_root)
            / "results"
            / task41_p0_contract.TASK41_MODEL_ID
            / "task41extra_b0_p6_phi90_07nm_iterative__full3d_iterative__mpi1__Mna"
            / "20261022T052401.200732Z"
        )
    run_root.mkdir(parents=True, exist_ok=True)
    numerical_output = run_root / "numerical_output"
    evidence_directory = run_root if missing_numerical_output else numerical_output
    evidence_directory.mkdir(parents=True, exist_ok=True)

    def persist_array(name, values):
        array = np.asarray(values)
        path = evidence_directory / f"{name}.npy"
        np.save(path, array, allow_pickle=False)
        return {
            "path": str(path),
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "array_sha256": hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest(),
            "shape": list(array.shape),
            "dtype": str(array.dtype),
        }

    report = audit._task41_v9_compact_volume_identity(
        owner,
        donor,
        allocation_gate=lambda *_args: None,
        progress_callback=lambda _event: None,
        persist_array=persist_array,
        output_directory=evidence_directory,
        native_volume_apply=lambda values: np.zeros_like(values),
        artifact_prefix="fixture_v9",
        candidate_identity="task41extra_actual_qmetric_blocked_gram_ffcx_profile_v1",
        candidate_cache_identity="fixture-cache-identity",
        recovery_refinement_max_steps=3,
        reserved_followup_evidence_bytes=audit.TASK41_V9_COMPACT_EVIDENCE_RESERVE_BYTES,
    )
    identity_path = evidence_directory / "identity.json"
    identity_path.write_text(json.dumps(report, sort_keys=True, allow_nan=False), encoding="utf-8")
    live_check = task41_p0_checker.check_task41_b0_v9_compact_volume_audit(
        report,
        donor,
        output_directory=evidence_directory,
        native_volume_apply=lambda values: np.zeros_like(values),
        expected_candidate_identity="task41extra_actual_qmetric_blocked_gram_ffcx_profile_v1",
        expected_cache_identity="fixture-cache-identity",
    )
    checker_path = evidence_directory / "independent.json"
    checker_path.write_text(json.dumps(live_check, sort_keys=True, allow_nan=False), encoding="utf-8")

    fake_repo = Path(service_repo_root) if service_repo_root is not None else tmp_path / "fake-repo"
    fake_checker_path = fake_repo / "src/runners/task41_p0_checker.py"
    fake_checker_path.parent.mkdir(parents=True)
    fake_checker_path.write_text("# fixture repo root", encoding="ascii")
    source_path = fake_repo / "src/candidate_qmetric.c"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text("candidate source fixture", encoding="ascii")
    donor_relative = (
        Path("results/frozen-v4-donor")
        if service_repo_root is None
        else task41_p0_contract.TASK41_B0_V9_VOLUME_DONOR_RUN_RELATIVE
    )
    donor_run = fake_repo / donor_relative
    donor_run.mkdir(parents=True, exist_ok=True)
    donor_summary_path = donor_run / "task40_v10_p6_candidate_summary.json"
    if not donor_summary_path.is_file():
        donor_summary_path.write_text("frozen donor summary fixture", encoding="ascii")
    monkeypatch.setattr(task41_p0_checker, "__file__", str(fake_checker_path))
    monkeypatch.setattr(task41_p0_checker, "load_task41_v4_volume_only_donor", lambda **_kwargs: donor)
    monkeypatch.setattr(task41_p0_contract, "TASK41_B0_V9_VOLUME_DONOR_RUN_RELATIVE", donor_relative)

    def file_binding(path):
        return {
            "path": str(path),
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }

    summary = {
        "campaign_authority": {"internal_rhs_strategy": "same_lu_rhs_solve"},
        "b0_v9_volume_donor_binding": {
            "relative_path": donor_relative.as_posix(),
            "attempt_id": donor_relative.name,
            "summary_bytes": donor_summary_path.stat().st_size,
            "summary_sha256": hashlib.sha256(donor_summary_path.read_bytes()).hexdigest(),
            "manifest_sha256": donor["manifest_sha256"],
            "existing_evidence_bytes": donor["existing_evidence_bytes"],
            "prior_new_evidence_bytes": donor["prior_new_evidence_bytes"],
        },
        "b0_v9_saved_prefix_binding": {
            "c_source_path": str(source_path),
            "c_source_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
            "candidate_evaluator_identity": report["candidate_evaluator_identity"],
            "candidate_cache_identity": report["candidate_evaluator_cache_identity"],
            "owner_internal_rhs_strategy": "same_lu_rhs_solve",
            "owner_geometry_policy": "mesh_actual_exact",
            "appended_rows": 2,
            "loaded_v7_payloads": False,
        },
        "b0_v9_compact_volume_audit": {
            **file_binding(identity_path),
            "schema": report["schema"],
            "status": report["status"],
            "action_gate": report["candidate_full_action_gate"],
            "recovery_gate": report["candidate_recovery_gate"],
        },
        "b0_v9_independent_check": {
            **live_check,
            **file_binding(checker_path),
        },
    }
    return task41_p0_checker, summary, numerical_output, identity_path


@pytest.mark.parametrize("action_passes", (True, False))
def test_v9_compact_producer_live_checker_and_terminal_saved_replay(
    tmp_path, monkeypatch, action_passes
):
    checker, summary, numerical_output, _identity_path = _task41_v9_compact_terminal_fixture(
        tmp_path, monkeypatch, action_passes=action_passes
    )
    result = checker._task41_b0_recovery_evidence_checks(
        summary,
        numerical_output,
        {"numerical_strategy": {"internal_rhs_strategy": "same_lu_rhs_solve"}},
        contract_sha256="fixture-contract-sha256",
    )

    assert result["terminal_route"] == "task41_b0_v9_compact_volume_audit"
    assert result["audit_completed"] is True, result
    assert result["data_integrity"] is True
    assert result["support_certificate_rechecked"] is None
    assert result["qualification_passed"] is action_passes
    assert result["errors"] == []
    assert result["saved_only_compact_replay"]["native_action_receipts_reused"] == (
        2 if action_passes else 0
    )
    assert result["saved_only_compact_replay"]["independent_native_volume_action_calls"] == 0
    assert result["saved_only_compact_replay"]["checks"]["reported_frozen_denominators_match_contract"] is True


@pytest.mark.parametrize("action_passes", (True, False))
def test_v9_compact_terminal_replay_uses_run_root_without_numerical_output(
    tmp_path, monkeypatch, action_passes
):
    checker, summary, numerical_output, _identity_path = _task41_v9_compact_terminal_fixture(
        tmp_path,
        monkeypatch,
        action_passes=action_passes,
        missing_numerical_output=True,
    )
    assert not numerical_output.exists()

    result = checker._task41_b0_recovery_evidence_checks(
        summary,
        numerical_output,
        {"numerical_strategy": {"internal_rhs_strategy": "same_lu_rhs_solve"}},
        contract_sha256="fixture-contract-sha256",
        run_root=numerical_output.parent,
    )

    assert result["audit_completed"] is True, result
    assert result["data_integrity"] is True
    assert result["qualification_passed"] is action_passes
    assert result["official_result"] is False
    assert result["errors"] == []


@pytest.mark.parametrize("damage", ("array", "column", "source"))
def test_v9_compact_terminal_saved_replay_rejects_corrupt_bindings(
    tmp_path, monkeypatch, damage
):
    checker, summary, numerical_output, identity_path = _task41_v9_compact_terminal_fixture(
        tmp_path, monkeypatch, action_passes=True
    )
    report = json.loads(identity_path.read_text(encoding="utf-8"))
    if damage == "array":
        artifact_path = Path(report["candidate_full_action_gate"]["full_action_artifact"]["path"])
        with artifact_path.open("r+b") as stream:
            stream.seek(-1, os.SEEK_END)
            stream.write(b"x")
    elif damage == "column":
        report["candidate_recovery_gate"]["columns"][0]["column"] = 1
        identity_path.write_text(json.dumps(report, sort_keys=True, allow_nan=False), encoding="utf-8")
        identity_binding = summary["b0_v9_compact_volume_audit"]
        identity_binding.update(
            {
                "bytes": identity_path.stat().st_size,
                "sha256": hashlib.sha256(identity_path.read_bytes()).hexdigest(),
                "recovery_gate": report["candidate_recovery_gate"],
            }
        )
    else:
        source_path = Path(summary["b0_v9_saved_prefix_binding"]["c_source_path"])
        source_path.write_text("tampered source fixture", encoding="ascii")

    result = checker._task41_b0_recovery_evidence_checks(
        summary,
        numerical_output,
        {"numerical_strategy": {"internal_rhs_strategy": "same_lu_rhs_solve"}},
        contract_sha256="fixture-contract-sha256",
    )

    assert result["audit_completed"] is False
    assert result["data_integrity"] is False
    assert result["qualification_passed"] is False
    assert result["errors"]


def _v9_candidate_evaluator_report(source_path: Path, source_sha256: str) -> dict:
    return {
        "identity_audit": {
            "candidate_evaluator_audit": {
                "evaluator_source_path": "/fixture/repo/src/solvers/evaluator.py",
                "evaluator_source_sha256": "a" * 64,
                "geometry_helper": {
                    "source_path": str(source_path),
                    "source_sha256": source_sha256,
                    "helper_source_sha256": "b" * 64,
                },
            }
        }
    }


def _v9_sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_v9_frozen_c_source_binding_uses_saved_geometry_helper_schema(tmp_path):
    from src.runners.task40_v10_worker import _task41_v9_frozen_c_source_binding

    repo_root = tmp_path / "repo"
    c_source = repo_root / "benchmarks/jit/candidate.c"
    c_source.parent.mkdir(parents=True)
    c_source.write_text("frozen generated C source", encoding="ascii")
    expected_sha256 = _v9_sha256_file(c_source)
    report = _v9_candidate_evaluator_report(c_source, expected_sha256)

    actual_path, actual_sha256 = _task41_v9_frozen_c_source_binding(
        report,
        repo_root=repo_root,
        sha256_file=_v9_sha256_file,
    )

    assert actual_path == c_source.resolve(strict=True)
    assert actual_sha256 == expected_sha256


@pytest.mark.parametrize(
    ("damage", "message"),
    (
        ("missing_helper", "geometry-helper audit"),
        ("missing_path", "C source path"),
        ("empty_path", "C source path"),
        ("directory_path", "not a regular file"),
        ("outside_repo", "outside the canonical repository"),
        ("missing_hash", "C source SHA-256 is absent"),
        ("hash_mismatch", "C-source SHA-256 differs"),
    ),
)
def test_v9_frozen_c_source_binding_rejects_invalid_saved_identity(
    tmp_path, damage, message
):
    from src.runners.task40_v10_worker import _task41_v9_frozen_c_source_binding

    repo_root = tmp_path / "repo"
    c_source = repo_root / "benchmarks/jit/candidate.c"
    c_source.parent.mkdir(parents=True)
    c_source.write_text("frozen generated C source", encoding="ascii")
    report = _v9_candidate_evaluator_report(c_source, _v9_sha256_file(c_source))
    candidate = report["identity_audit"]["candidate_evaluator_audit"]
    geometry_helper = candidate["geometry_helper"]
    outside_source = tmp_path / "outside.c"
    outside_source.write_text("outside generated C source", encoding="ascii")
    if damage == "missing_helper":
        candidate.pop("geometry_helper")
    elif damage == "missing_path":
        geometry_helper.pop("source_path")
    elif damage == "empty_path":
        geometry_helper["source_path"] = ""
    elif damage == "directory_path":
        geometry_helper["source_path"] = str(repo_root)
    elif damage == "outside_repo":
        geometry_helper["source_path"] = str(outside_source)
    elif damage == "missing_hash":
        geometry_helper.pop("source_sha256")
    elif damage == "hash_mismatch":
        geometry_helper["source_sha256"] = "0" * 64

    hash_calls = []

    def record_hash_call(path):
        hash_calls.append(path)
        return _v9_sha256_file(path)

    with pytest.raises(ValueError, match=message):
        _task41_v9_frozen_c_source_binding(
            report,
            repo_root=repo_root,
            sha256_file=record_hash_call,
        )

    assert hash_calls == ([c_source.resolve(strict=True)] if damage == "hash_mismatch" else [])


def test_v9_pre_donor_owner_is_released_if_a_post_build_gate_raises():
    from src.runners import task40_v10_worker

    class CondensedOwner:
        def __init__(self):
            self.destroy_calls = 0

        def destroy(self):
            self.destroy_calls += 1

    owner = CondensedOwner()
    target_bundle = {
        "pre_donor_qualification": {"owner_result": {"condensed": owner}}
    }
    registered_owner = task40_v10_worker._task41_b0_v9_pre_donor_condensed(target_bundle)
    assert registered_owner is owner

    with pytest.raises(RuntimeError, match="post-build profile gate"):
        try:
            raise RuntimeError("post-build profile gate")
        finally:
            task40_v10_worker._task41_destroy_pending_condensed(registered_owner)

    assert owner.destroy_calls == 1


def test_v9_pending_owner_destroy_failure_is_recorded_for_cleanup():
    from src.runners import task40_v10_worker

    class FailingOwner:
        def destroy(self):
            raise RuntimeError("fixture destroy failure")

    summary = {}
    task40_v10_worker._task41_destroy_pending_condensed(
        FailingOwner(), summary=summary
    )

    assert summary == {
        "cleanup_errors": [
            {"type": "RuntimeError", "message": "fixture destroy failure"}
        ]
    }


@pytest.mark.parametrize("column_index", (0, 1))
def test_v6_saved_prefix_action_diagnostic_uses_main_lazy_import(column_index):
    import ast
    import inspect

    from src.runners import task41_p0_v4_volume_only_audit as runner

    main_tree = ast.parse(inspect.getsource(runner.main))
    denominator_imports = [
        node
        for node in ast.walk(main_tree)
        if isinstance(node, ast.ImportFrom)
        and node.module == "src.solvers.task41_v4_volume_only_audit"
        and any(
            alias.name == "TASK41_V5_FROZEN_DENOMINATORS"
            for alias in node.names
        )
    ]
    assert len(denominator_imports) == 1
    import_namespace = {}
    import_module = ast.Module(body=[denominator_imports[0]], type_ignores=[])
    exec(compile(import_module, "<task41-v6-main-lazy-import>", "exec"), import_namespace)
    frozen_denominators = import_namespace["TASK41_V5_FROZEN_DENOMINATORS"]

    reference = np.asarray([1.0 + 2.0j, 3.0 + 4.0j, 5.0 + 6.0j])
    candidate = reference.copy()
    candidate[1] += 2.0j
    candidate[2] -= 1.0 + 1.0j
    expansion = sparse.csc_matrix(
        np.asarray([[0.0, 1.0], [1.0, 0.0]], dtype=np.complex128)
    )

    diagnostic = runner._v6_saved_local_action_diagnostic(
        reference,
        candidate,
        frozen_denominators=frozen_denominators,
        column_index=column_index,
        trace_positions=np.asarray([1, 2], dtype=np.int64),
        active_ids=np.asarray([0, runner.TASK41_P0_V4_SELECTED_ACTIVE_ROW], dtype=np.int64),
        trace_expansion=expansion,
        selected_active_row=runner.TASK41_P0_V4_SELECTED_ACTIVE_ROW,
    )

    denominator = frozen_denominators[column_index]
    assert diagnostic["frozen_denominator"] == denominator
    assert diagnostic["full_local_action"]["status"] == "FAIL"
    assert diagnostic["full_local_action_scale_check"] == "diagnostic_only"
    assert diagnostic["full_local_action_difference_over_frozen_denominator"] == pytest.approx(
        np.linalg.norm(candidate - reference) / denominator
    )
    assert diagnostic["selected_row_reference"] == [3.0, 4.0]
    assert diagnostic["selected_row_candidate"] == [3.0, 6.0]
    assert diagnostic["selected_row_difference_over_frozen_denominator"] == pytest.approx(
        2.0 / denominator
    )
    assert diagnostic["selected_row_scale_check"] == "diagnostic_only"


def test_rhs_split_roundoff_uses_native_rhs_minus_balpha_minus_volume_order():
    from src.solvers.task41_v4_volume_only_audit import _rhs_decomposition_metrics

    total = np.asarray([1.0e16 + 0.0j], dtype=np.complex128)
    before = total.copy()
    metrics = _rhs_decomposition_metrics(
        total,
        np.asarray([1.0 + 0.0j], dtype=np.complex128),
        np.asarray([0], dtype=np.int64),
        np.asarray([1.0e16 + 0.0j], dtype=np.complex128),
    )

    assert metrics["absolute_l2"] == 1.0
    np.testing.assert_array_equal(total, before)


def test_user_service_wrapper_accepts_volume_only_audit_flag(tmp_path):
    root = Path(__file__).resolve().parents[2]
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    capture = tmp_path / "systemd-run-arguments"
    fake_python = fake_bin / "python3"
    fake_python.write_text(
        "#!/bin/bash\n"
        "set -euo pipefail\n"
        "printf '%s\\n' \"$FAKE_REPO_ROOT\" /fixture/runtime /fixture/abi.json "
        "/fixture/jit contract-sha /fixture/window.json window-sha "
        "1610612736 67108864 0 unused source-sha\n",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)
    fake_systemd_run = fake_bin / "systemd-run"
    fake_systemd_run.write_text(
        "#!/bin/bash\n"
        "set -euo pipefail\n"
        "printf '%s\\0' \"$@\" > \"$CAPTURE_PATH\"\n",
        encoding="utf-8",
    )
    fake_systemd_run.chmod(0o755)
    env = dict(os.environ)
    env.update(
        PATH=f"{fake_bin}:{env['PATH']}",
        FAKE_REPO_ROOT=str(root),
        CAPTURE_PATH=str(capture),
    )
    result = subprocess.run(
        [
            "bash",
            str(root / "scripts/run_case_in_user_service.sh"),
            str(tmp_path / "fixture.dat"),
            "--task41-p0-execution-contract",
            str(tmp_path / "contract.json"),
            "--task41-p0-saved-b0-volume-only-attribution",
            "--service-unit",
            "v4-wrapper-fixture.service",
        ],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    systemd_arguments = capture.read_bytes().decode("utf-8", errors="surrogateescape").split("\0")
    assert "--property=MemoryMax=1610612736" in systemd_arguments
    assert "--task41-p0-saved-b0-volume-only-attribution" in systemd_arguments


def test_volume_identity_metrics_reject_nonfinite_and_resource_gate_keeps_contract(tmp_path):
    from src.runners.task41_p0_v4_volume_only_audit import _checked_allocation_gate, _parse_args
    from src.solvers import task41_v4_volume_only_audit as audit

    with pytest.raises(ValueError, match="non-finite"):
        audit._difference_metrics(np.asarray([np.nan + 0.0j]), np.asarray([0.0j]))
    with pytest.raises(ValueError, match="non-finite"):
        audit._sum_metrics(np.asarray([np.inf + 0.0j]), np.asarray([0.0j]))

    args = _parse_args(
        [
            "--summary", str(tmp_path / "summary.json"),
            "--numerical-output", str(tmp_path / "numerical_output"),
            "--donor-contract", str(tmp_path / "donor.json"),
            "--donor-contract-sha256", "a" * 64,
            "--consumer-contract", str(tmp_path / "consumer.json"),
            "--consumer-contract-sha256", "b" * 64,
            "--output-dir", str(tmp_path / "output"),
        ]
    )
    assert args.output_dir == tmp_path / "output"

    calls = []
    progress = []
    snapshot = lambda: {"host_memory_available_bytes": 99}

    def admission(stage, amount, **kwargs):
        calls.append((stage, amount, kwargs))
        return {"host_gate_passed": True, "task_cgroup_gate_passed": True}

    _checked_allocation_gate(
        "phase",
        {"additional_payload_bytes": 5, "workspace_bytes": 7},
        resource_admission=admission,
        resource_snapshot=snapshot,
        resources={
            "task_memory_max_bytes": 1536 * 1024**3,
            "host_reserve_bytes": 64 * 1024**3,
            "task_cgroup_reserve_bytes": 0,
        },
        progress=progress.append,
    )
    assert calls[0][0:2] == ("task41_v4_phase", 12)
    assert calls[0][2] == {
        "resource_sample": snapshot,
        "require_task_cgroup": True,
        "explicit_process_tree_cap_bytes": 1536 * 1024**3,
        "host_reserve_bytes": 64 * 1024**3,
        "task_cgroup_reserve_bytes": 0,
    }
    assert progress[0]["status"] == "PASSED"


def test_compiled_kernel_identity_uses_bounded_real_ffcx_cell_metadata():
    import ufl
    from basix.ufl import element
    from dolfinx import default_real_type, fem, mesh
    from mpi4py import MPI

    from src.runners.task41_p0_v4_volume_only_audit import _compiled_kernel_identity
    from src.runners.task41_p0_contract import sha256_file

    msh = mesh.create_unit_cube(MPI.COMM_SELF, 1, 1, 1)
    space = fem.functionspace(
        msh,
        element("N1curl", msh.basix_cell(), 1, dtype=default_real_type),
    )
    trial = ufl.TrialFunction(space)
    test = ufl.TestFunction(space)
    dx = ufl.Measure("dx", domain=msh)
    curl_form = ufl.inner(ufl.curl(trial), ufl.curl(test)) * dx
    mass_form = ufl.inner(trial, test) * dx
    rank_two = fem.form(curl_form + mass_form)
    source = fem.Function(space)
    rank_one = fem.form(ufl.action(curl_form, source))

    rank_two_identity = _compiled_kernel_identity(
        rank_two, rank=2, label="test_combined", sha256_file=sha256_file
    )
    rank_one_identity = _compiled_kernel_identity(
        rank_one, rank=1, label="test_action", sha256_file=sha256_file
    )

    assert rank_two_identity["form_rank"] == 2
    assert rank_one_identity["form_rank"] == 1
    assert rank_two_identity["ffcx_form_signature"] != rank_one_identity["ffcx_form_signature"]
    for identity in (rank_two_identity, rank_one_identity):
        assert len(identity["cell_integral_offsets"]) == 2
        assert identity["cell_integral_offsets"][0] == 0
        assert identity["cell_integral_count"] > 0
        assert sum(identity["integral_kernel_counts"].values()) > 0


def test_geometry_pair_attribution_closes_selected_row_identity_algebraically():
    from src.solvers.task41_v4_volume_only_audit import (
        audit_task41_v4_geometry_pair_attribution,
    )

    cells = (26762, 26897)
    cell_pairs = {}
    saved_maps = {}
    saved_classes = {}
    for cell_index, interior_row in (
        (cells[0], 0),
        (cells[1], 2),
    ):
        cell_pairs[cell_index] = {
            "actual": {
                "K": np.asarray([[2.0]], dtype=np.complex128),
                "G": np.asarray([[3.0]], dtype=np.complex128),
                "J": np.asarray([[5.0]], dtype=np.complex128),
                "L": np.asarray([[7.0]], dtype=np.complex128),
            },
            "canonical": {
                "K": np.asarray([[1.0]], dtype=np.complex128),
                "G": np.asarray([[2.0]], dtype=np.complex128),
                "J": np.asarray([[4.0]], dtype=np.complex128),
                "L": np.asarray([[6.0]], dtype=np.complex128),
            },
        }
        saved_maps[cell_index] = {
            "interior_original_rows": np.asarray([interior_row], dtype=np.int64),
            "trace_original_rows": np.asarray([1 if interior_row == 0 else 3], dtype=np.int64),
            "active_ids": np.asarray([0], dtype=np.int64),
            "trace_expansion_data": np.asarray([1.0 + 0.0j], dtype=np.complex128),
            "trace_expansion_indices": np.asarray([0], dtype=np.int32),
            "trace_expansion_indptr": np.asarray([0, 1], dtype=np.int32),
        }
        saved_classes[cell_index] = {
            "S": np.asarray([[11.0]], dtype=np.complex128),
            "T": np.asarray([[13.0]], dtype=np.complex128),
        }

    field = np.asarray([17.0, 23.0, 19.0, 23.0], dtype=np.complex128)
    native = np.asarray([31.0, 41.0, 37.0, 0.0], dtype=np.complex128)
    columns = [
        {
            "active_original_rows": np.asarray([1], dtype=np.int64),
            "known_field": field.copy(),
            "states": [
                {"storage": field.copy(), "native_volume_action": native.copy()},
                {"storage": field.copy(), "native_volume_action": native.copy()},
            ],
        }
        for _ in range(2)
    ]
    zero = np.zeros(1, dtype=np.complex128)
    saved_reduce = {(column, state): zero.copy() for column in range(2) for state in ("j0", "j3")}
    result = audit_task41_v4_geometry_pair_attribution(
        cell_pairs=cell_pairs,
        saved_maps=saved_maps,
        columns=columns,
        saved_classes=saved_classes,
        saved_d_volume=[np.asarray([-419.0 + 0.0j]), np.asarray([-419.0 + 0.0j])],
        saved_reduce_r_volume=saved_reduce,
        original_denominators=[100.0, 100.0],
        target_active_row=0,
        target_original_row=1,
    )

    actual_j0 = result["attribution"][1]["paths"]["actual"]
    canonical_j0 = result["attribution"][1]["paths"]["canonical"]
    assert actual_j0["native_comparison"]["delta_t"] == [461.0, 0.0]
    assert canonical_j0["native_comparison"]["delta_t"] == [379.0, 0.0]
    assert actual_j0["native_comparison"]["selected_row_identity_residual_abs"] == 0.0
    assert canonical_j0["native_comparison"]["selected_row_identity_residual_abs"] == 0.0
    assert actual_j0["selected_cells"][0]["delta_i"]["max_abs"] == 72.0
    assert canonical_j0["selected_cells"][0]["delta_i"]["max_abs"] == 32.0
    assert actual_j0["selected_cells"][0]["actual_minus_canonical_target_trace_action"] == [40.0, 0.0]
    assert result["attribution"][1]["paths"]["actual"]["native_comparison"]["global_column_gate_claim"] is False
