from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace

import numpy as np
import pytest
from scipy import sparse


def _array_record(value: np.ndarray, path: str = "fixture.npy") -> dict:
    return {"path": path, "shape": list(value.shape), "dtype": str(value.dtype)}


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
        element=SimpleNamespace(space_dimension=2),
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

    def tabulate(_form, _space, _tags, _owner, cell_index):
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


def test_volume_only_owner_avoids_surface_and_persists_each_class_once(tmp_path, monkeypatch):
    case = _fixture(tmp_path, monkeypatch)

    def forbidden_surface(*_args, **_kwargs):
        raise AssertionError("volume-only extraction must not construct a surface/carrier action")

    monkeypatch.setattr(case.audit, "build_same_mesh_physical_action", forbidden_surface, raising=False)
    progress = []
    result = case.audit.build_task41_v4_volume_only_owner(
        object(),
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


def test_volume_only_owner_rejects_fresh_numbering_mismatch_before_persist(tmp_path, monkeypatch):
    case = _fixture(tmp_path, monkeypatch)
    case.donor["columns"][0]["active_original_rows"] = np.asarray([9, 11], dtype=np.int64)
    progress = []

    with pytest.raises(ValueError, match="fresh Task41 V4 numbering or donor vectors differ"):
        case.audit.build_task41_v4_volume_only_owner(
            object(),
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


def test_v5_attribution_reconstructs_nonzero_complex_mpc_slave_trace():
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
    T = -J @ np.linalg.inv(K)
    S = L + J @ R
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
    storage = np.asarray([u_i, active_value, 0.0j], dtype=np.complex128)
    native_action = np.asarray([0.8 - 0.1j, 0.3 + 0.05j, 0.0j], dtype=np.complex128)
    native_rhs = np.asarray([0.9 + 0.2j, 0.6 - 0.1j, 0.0j], dtype=np.complex128)
    native_i = native_action[0]
    r_i = native_rhs[0] - native_i
    delta_i = (K @ np.asarray([u_i]) + G @ physical_trace).reshape(-1) - native_i
    actual_trace = J @ np.asarray([u_i]) + L @ physical_trace
    delta_t = (expansion.conj().T @ actual_trace).reshape(-1) - native_action[1:2]
    E_T_u = J @ np.asarray([u_i]) + T @ (K @ np.asarray([u_i]))
    E_S_t = S @ physical_trace - L @ physical_trace - T @ (G @ physical_trace)
    attributed = T @ delta_i + E_S_t - E_T_u
    right = delta_t + expansion.conj().T @ attributed
    T_r_i = (expansion.conj().T @ (T @ np.asarray([r_i]))).reshape(-1)
    r_t = native_rhs[1:2] - native_action[1:2]
    d = (right - r_t - T_r_i).reshape(-1)[0]

    state = {
        "label": "j0",
        "storage": storage,
        "native_volume_action": native_action,
    }
    donor = {
        "columns": [
            {
                "active_original_rows": active_original,
                "native_rhs": native_rhs,
                "states": [state, {**state, "label": "j3"}],
            },
            {
                "active_original_rows": active_original,
                "native_rhs": native_rhs,
                "states": [state, {**state, "label": "j3"}],
            },
        ]
    }
    accumulator = Task41V5VolumeAttributionAccumulator(donor)
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
    candidate_p6 = np.full((1, 2), d, dtype=np.complex128)
    candidate_reduced = np.zeros_like(candidate_p6)
    report = accumulator.finalize(
        candidate_p6, candidate_reduced, active_rows=1
    )

    assert storage[2] == 0.0j
    assert physical_trace[1] == pytest.approx(phase * active_value)
    assert report["global_closure_status"] == "DIAGNOSTIC_ONLY"
    assert report["slave_trace_reconstruction"].startswith("local E times")
    for column in report["columns"]:
        for result in column["states"]:
            assert result["closure_difference"]["absolute_l2"] < 1.0e-13
            assert result["closure_relative_to_accumulation_scale"] < 1.0e-12


@pytest.mark.parametrize(
    ("geometry_policy", "port_error"),
    (("canonical", 0.0), ("mesh_actual_exact", 0.0), ("mesh_actual_exact", 1.0e-6)),
)
def test_volume_identity_replays_real_p6_action_and_rhs_reducer(
    tmp_path, geometry_policy, port_error
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
        build_audit={"geometry_policy": geometry_policy},
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
    )

    assert report["completed"] is True
    assert report["production_action"] == "P6CellCondensedAction_active_only_shared_owner_caches"
    assert report["saved_port_rows_reused"] is True
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
            "task41_p0_v5_candidate_recovered_storage_col0",
            "task41_p0_v5_candidate_recovered_storage_col1",
            "task41_p0_v5_candidate_native_volume_residual_col0",
            "task41_p0_v5_candidate_native_volume_residual_col1",
        }
        np.testing.assert_array_equal(
            persisted["task41_p0_v5_candidate_full_p6"], p6
        )
        expected_reduced = saved_reduced.copy()
        np.testing.assert_allclose(
            persisted["task41_p0_v5_candidate_full_reduced_rhs"],
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
