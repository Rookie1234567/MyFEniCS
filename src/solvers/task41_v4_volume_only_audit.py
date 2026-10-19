"""Task41 V4's bounded, volume-only owner and raw-cell evidence extraction."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
import hashlib
from pathlib import Path
import shutil
from typing import Any

import numpy as np
from dolfinx import fem
from mpi4py import MPI
from scipy import sparse
import ufl

from .common_3d_forms import _build_physical_volume_terms
from .fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels
from .fullspace_same_mesh_hcurl_pmg_setup import SAME_MESH_JIT_OPTIONS
from .hcurl_assembly_time_condensation import (
    AssemblyTimeCondensedSystem,
    _cell_trace_expansion,
    build_unconstrained_assembly_time_condensation,
    iter_selected_volume_audit_cells,
    tabulate_volume_audit_cell,
)
from .p6_cell_condensed_action import P6CellCondensedAction

TASK41_V4_DONOR_MANIFEST_SHA256 = (
    "f55ac594382f40662954e19521ef9922d805abc64459cc7812877b12ec618465"
)
TASK41_V4_DONOR_NPY_BYTES = 9_379_882_344
TASK41_V4_EVIDENCE_CAP_BYTES = 16 * 1024**3
TASK41_V4_FREE_SPACE_FLOOR_BYTES = 2 * 1024**3
TASK41_V4_FULL_STORAGE_ROWS = 18_501_024
TASK41_V4_ACTIVE_TRACE_ROWS = 5_688_000
TASK41_V4_APPENDED_ROWS = 64_120
TASK41_V4_SELECTED_ACTIVE_ROW = 5_458_716
TASK41_V4_SELECTED_ORIGINAL_ROW = 17_692_332


def _class_key(value: Sequence[Any]) -> tuple[int, float, float, float, int]:
    if len(value) != 5:
        raise ValueError(f"Task41 V4 class key must have five fields: {value!r}")
    return (int(value[0]), float(value[1]), float(value[2]), float(value[3]), int(value[4]))


def _check_artifact_array(record: Mapping[str, Any], array: Any, label: str) -> np.ndarray:
    value = np.asarray(array)
    if list(value.shape) != list(record.get("shape", ())) or str(value.dtype) != str(
        record.get("dtype")
    ):
        raise ValueError(f"Task41 V4 donor array metadata differs for {label}")
    return value


def _csr_equal(left: sparse.csr_matrix, right: sparse.csr_matrix) -> bool:
    return (
        left.shape == right.shape
        and np.array_equal(left.indptr, right.indptr)
        and np.array_equal(left.indices, right.indices)
        and np.array_equal(left.data, right.data)
    )


def _vector_norm(value: np.ndarray) -> float:
    flat = np.asarray(value).reshape(-1)
    scale = 0.0
    squares = 1.0
    for start in range(0, flat.size, 262_144):
        chunk = np.asarray(flat[start : start + 262_144], dtype=np.complex128)
        if not np.isfinite(chunk).all():
            raise ValueError("Task41 V4 norm input contains non-finite values")
        magnitude = np.abs(chunk)
        if magnitude.size:
            chunk_scale = float(np.max(magnitude))
            if chunk_scale:
                local = float(np.linalg.norm(chunk / chunk_scale)) * chunk_scale
                if scale < local:
                    squares = 1.0 + squares * (scale / local) ** 2
                    scale = local
                elif local:
                    squares += (local / scale) ** 2
    return float(scale * np.sqrt(squares)) if scale else 0.0


def _difference_metrics(left: np.ndarray, right: np.ndarray) -> dict[str, Any]:
    a = np.asarray(left).reshape(-1)
    b = np.asarray(right).reshape(-1)
    if a.shape != b.shape:
        raise ValueError("Task41 V4 replay vectors have different lengths")
    scale = 0.0
    squares = 1.0
    max_abs = 0.0
    max_row: int | None = None
    for start in range(0, a.size, 262_144):
        left_chunk = np.asarray(a[start : start + 262_144], dtype=np.complex128)
        right_chunk = np.asarray(b[start : start + 262_144], dtype=np.complex128)
        if not np.isfinite(left_chunk).all() or not np.isfinite(right_chunk).all():
            raise ValueError("Task41 V4 difference input contains non-finite values")
        delta = left_chunk - right_chunk
        magnitude = np.abs(delta)
        if not magnitude.size:
            continue
        local_max_index = int(np.argmax(magnitude))
        local_max = float(magnitude[local_max_index])
        if local_max > max_abs:
            max_abs = local_max
            max_row = start + local_max_index
        local_norm = float(np.linalg.norm(delta))
        if scale < local_norm:
            squares = 1.0 + squares * (scale / local_norm) ** 2
            scale = local_norm
        elif local_norm:
            squares += (local_norm / scale) ** 2
    return {
        "absolute_l2": float(scale * np.sqrt(squares)) if scale else 0.0,
        "sum_squares": float(scale * scale * squares) if scale else 0.0,
        "max_abs": max_abs,
        "max_row": max_row,
    }


def _sum_metrics(left: np.ndarray, right: np.ndarray) -> dict[str, Any]:
    a = np.asarray(left).reshape(-1)
    b = np.asarray(right).reshape(-1)
    if a.shape != b.shape:
        raise ValueError("Task41 V4 identity vectors have different lengths")
    scale = 0.0
    squares = 1.0
    max_abs = 0.0
    max_row: int | None = None
    for start in range(0, a.size, 262_144):
        left_chunk = np.asarray(a[start : start + 262_144], dtype=np.complex128)
        right_chunk = np.asarray(b[start : start + 262_144], dtype=np.complex128)
        if not np.isfinite(left_chunk).all() or not np.isfinite(right_chunk).all():
            raise ValueError("Task41 V4 sum input contains non-finite values")
        total = left_chunk + right_chunk
        magnitude = np.abs(total)
        if not magnitude.size:
            continue
        local_max_index = int(np.argmax(magnitude))
        local_max = float(magnitude[local_max_index])
        if local_max > max_abs:
            max_abs = local_max
            max_row = start + local_max_index
        local_norm = float(np.linalg.norm(total))
        if scale < local_norm:
            squares = 1.0 + squares * (scale / local_norm) ** 2
            scale = local_norm
        elif local_norm:
            squares += (local_norm / scale) ** 2
    return {
        "absolute_l2": float(scale * np.sqrt(squares)) if scale else 0.0,
        "sum_squares": float(scale * scale * squares) if scale else 0.0,
        "max_abs": max_abs,
        "max_row": max_row,
    }


def _rhs_decomposition_metrics(
    total_rhs: np.ndarray,
    volume_rhs: np.ndarray,
    b_alpha_rows: np.ndarray,
    b_alpha_values: np.ndarray,
) -> dict[str, Any]:
    total = np.asarray(total_rhs).reshape(-1)
    volume = np.asarray(volume_rhs).reshape(-1)
    if total.shape != volume.shape:
        raise ValueError("Task41 V4 total and volume RHS have different lengths")
    scale = 0.0
    squares = 1.0
    max_abs = 0.0
    max_row: int | None = None
    for start in range(0, total.size, 262_144):
        stop = min(total.size, start + 262_144)
        delta = np.array(total[start:stop], dtype=np.complex128, copy=True)
        lo = int(np.searchsorted(b_alpha_rows, start))
        hi = int(np.searchsorted(b_alpha_rows, stop))
        if hi > lo:
            delta[b_alpha_rows[lo:hi] - start] -= b_alpha_values[lo:hi]
        delta -= np.asarray(volume[start:stop], dtype=np.complex128)
        if not np.isfinite(delta).all():
            raise ValueError("Task41 V4 RHS decomposition contains non-finite values")
        magnitude = np.abs(delta)
        if not magnitude.size:
            continue
        local_max_index = int(np.argmax(magnitude))
        local_max = float(magnitude[local_max_index])
        if local_max > max_abs:
            max_abs = local_max
            max_row = start + local_max_index
        local_norm = float(np.linalg.norm(delta))
        if scale < local_norm:
            squares = 1.0 + squares * (scale / local_norm) ** 2
            scale = local_norm
        elif local_norm:
            squares += (local_norm / scale) ** 2
    return {
        "absolute_l2": float(scale * np.sqrt(squares)) if scale else 0.0,
        "sum_squares": float(scale * scale * squares) if scale else 0.0,
        "max_abs": max_abs,
        "max_row": max_row,
    }


def _local_class_identity(
    key: tuple[Any, ...],
    raw: Mapping[str, Any],
    *,
    T: np.ndarray,
    R: np.ndarray,
    S: np.ndarray,
) -> dict[str, Any]:
    K = np.asarray(raw["K"], dtype=np.complex128)
    G = np.asarray(raw["G"], dtype=np.complex128)
    J = np.asarray(raw["J"], dtype=np.complex128)
    L = np.asarray(raw["L"], dtype=np.complex128)
    TG = T @ G
    TK = T @ K
    KR = K @ R
    residuals = {
        "S_minus_L_plus_TG": S - (L + TG),
        "TK_plus_J": TK + J,
        "KR_plus_G": KR + G,
    }
    scales = {
        "S_minus_L_plus_TG": max(_vector_norm(S), _vector_norm(L), _vector_norm(TG), np.finfo(float).tiny),
        "TK_plus_J": max(_vector_norm(TK), _vector_norm(J), np.finfo(float).tiny),
        "KR_plus_G": max(_vector_norm(KR), _vector_norm(G), np.finfo(float).tiny),
    }
    metrics = {
        name: {
            "absolute_frobenius": _vector_norm(value),
            "relative_to_local_terms": _vector_norm(value) / scales[name],
            "max_abs": float(np.max(np.abs(value))) if value.size else 0.0,
        }
        for name, value in residuals.items()
    }
    return {"class_key": list(key), "identities": metrics}


def build_task41_v4_volume_only_owner(
    cfg: Any,
    donor: Mapping[str, Any],
    output_directory: str | Path,
    *,
    allocation_gate: Callable[[str, Mapping[str, Any]], Any],
    progress_callback: Callable[[Mapping[str, Any]], Any],
    persist_array: Callable[[str, np.ndarray], Mapping[str, Any]],
) -> dict[str, Any]:
    """Build one fresh MPI1 volume owner and persist only selected local evidence.

    ``donor`` is a normalized read-only view of the existing recovery manifest:
    it has ``manifest``, ``manifest_sha256``, ``existing_evidence_bytes``, two
    ``columns`` (active/slave rows, known field, native RHS), three
    ``raw_classes`` (``class_key``, ``Vii``, ``Vit``), and six ``cell_maps``
    (rows, active IDs, permutation, and CSR expansion arrays).  It never copies
    those donor arrays.  On success the returned ``condensed`` owner remains
    alive for the caller's later full-domain identity audit and cleanup.
    """

    if not all(callable(item) for item in (allocation_gate, progress_callback, persist_array)):
        raise TypeError("Task41 V4 requires allocation, progress, and persistence callbacks")
    manifest = donor["manifest"]
    if donor.get("manifest_sha256") != TASK41_V4_DONOR_MANIFEST_SHA256:
        raise ValueError("Task41 V4 donor recovery-manifest identity differs")
    existing_bytes = int(donor.get("existing_evidence_bytes", -1))
    if existing_bytes != TASK41_V4_DONOR_NPY_BYTES:
        raise ValueError("Task41 V4 donor NPY byte count differs from the frozen 141-array set")
    if (
        int(manifest.get("full_storage_rows", -1)) != TASK41_V4_FULL_STORAGE_ROWS
        or int(manifest.get("active_trace_rows", -1)) != TASK41_V4_ACTIVE_TRACE_ROWS
        or int(manifest.get("port_rows", -1)) != TASK41_V4_APPENDED_ROWS
        or len(manifest.get("columns", ())) != 2
    ):
        raise ValueError("Task41 V4 donor manifest has an unexpected B0 layout")
    if (
        manifest.get("local_interior_Bi_Di_exact_zero") is not True
        or manifest.get("local_interior_Bi_Di_nonzero_entry_count") != 0
        or manifest.get("saved_surface_support_certificate_passed") is not True
    ):
        raise ValueError("Task41 V4 donor lacks the saved exact-zero Bi/Di support certificate")
    owner: AssemblyTimeCondensedSystem | None = None
    phase = "fresh_same_mesh_levels"

    def progress(stage: str, status: str, **facts: Any) -> None:
        progress_callback({"phase": stage, "status": status, **facts})

    try:
        progress(phase, "STARTED", degree=6, include_positive_coefficients=False)
        levels = _build_same_mesh_levels(
            cfg,
            MPI.COMM_SELF,
            (6,),
            include_positive_coefficients=False,
        )
        progress(phase, "COMPLETED", owned_cells=int(
            levels["mesh"].topology.index_map(3).size_local
        ))

        phase = "direct_volume_form_compile"
        progress(phase, "STARTED")
        space = levels["spaces"][6]
        mesh_data = levels["mesh_data"]
        trial = ufl.TrialFunction(space)
        test = ufl.TestFunction(space)
        dx = ufl.Measure("dx", domain=levels["mesh"], subdomain_data=mesh_data.cell_tags)
        curl_curl, material_mass = _build_physical_volume_terms(cfg, trial, test, dx)
        compiled_form = fem.form(
            curl_curl + material_mass,
            jit_options=dict(SAME_MESH_JIT_OPTIONS),
        )
        progress(phase, "COMPLETED", construction="curl_plus_mass_only")

        phase = "fresh_volume_owner"
        progress(
            phase,
            "STARTED",
            appended_rows=TASK41_V4_APPENDED_ROWS,
            matrix_materialized=False,
        )
        owner = build_unconstrained_assembly_time_condensation(
            compiled_form,
            space,
            mesh_data.cell_tags,
            mpc=levels["floquets"][6].mpc,
            appended_global_rows=TASK41_V4_APPENDED_ROWS,
            sum_duplicate_cell_integrals=True,
            strict_local_checks=True,
            materialize_global_matrix=False,
            retain_local_schur_for_matrix_free=True,
            share_identity_cache=True,
            preserve_exact_geometry=True,
            allocation_gate=allocation_gate,
        )
        progress(
            phase,
            "COMPLETED",
            active_rows=owner.active_rows,
            slave_rows=owner.trace_constraints.slave_rows,
            class_count=len(owner.interior_lu_by_class),
            retained_cache_bytes=owner.build_audit.get("retained_cache_bytes_local"),
        )

        phase = "donor_identity_validation"
        progress(phase, "STARTED", raw_classes=3, cell_maps=6)
        if (
            owner.full_rows != int(manifest["full_storage_rows"])
            or owner.active_rows != int(manifest["active_trace_rows"])
            or owner.appended_rows != int(manifest["port_rows"])
            or owner.trace_constraints.owned_active_range != (0, owner.active_rows)
        ):
            raise ValueError("fresh Task41 V4 owner layout differs from the saved donor")

        constraints = owner.trace_constraints
        fresh_active = np.asarray(constraints.owned_active_original_dofs)
        mpc = levels["floquets"][6].mpc
        mpc_index_map = space.dofmap.index_map
        local_slave_rows = np.asarray(mpc.slaves, dtype=np.int64).reshape(-1)
        owned_local_slaves = local_slave_rows[
            (local_slave_rows >= 0)
            & (local_slave_rows < int(mpc_index_map.size_local))
        ]
        if len(np.unique(owned_local_slaves)) != len(owned_local_slaves):
            raise ValueError("fresh finalized MPC contains duplicate owned slave rows")
        fresh_slave = np.asarray(
            mpc_index_map.local_to_global(owned_local_slaves.astype(np.int32, copy=False)),
            dtype=np.int64,
        ).reshape(-1)
        fresh_slave.sort()
        if len(fresh_slave) != constraints.slave_rows:
            raise ValueError("fresh finalized MPC slave rows do not match the condensed owner")
        columns = tuple(donor["columns"])
        if len(columns) != 2:
            raise ValueError("Task41 V4 donor must provide the two saved input columns")
        active_name = "active_original_rows"
        slave_name = "slave_rows"
        known_name = "known_field"
        rhs_name = "native_rhs"
        active_saved: np.ndarray | None = None
        slave_saved: np.ndarray | None = None
        for column_index, column in enumerate(columns):
            metadata = manifest["columns"][column_index]["artifacts"]
            active = _check_artifact_array(
                metadata[active_name], column[active_name], f"column {column_index} active rows"
            )
            slave = _check_artifact_array(
                metadata[slave_name], column[slave_name], f"column {column_index} slave rows"
            )
            known = _check_artifact_array(
                metadata[known_name], column[known_name], f"column {column_index} known field"
            )
            rhs = _check_artifact_array(
                metadata[rhs_name], column[rhs_name], f"column {column_index} native RHS"
            )
            if (
                not np.array_equal(active, fresh_active)
                or not np.array_equal(slave, fresh_slave)
                or known.shape != (owner.full_rows,)
                or rhs.shape != (owner.full_rows,)
                or known.dtype != np.dtype(np.complex128)
                or rhs.dtype != np.dtype(np.complex128)
                or np.any(known[slave] != 0.0)
                or np.any(rhs[slave] != 0.0)
            ):
                raise ValueError(f"fresh Task41 V4 numbering or donor vectors differ in column {column_index}")
            if column_index == 0:
                active_saved, slave_saved = active, slave
            elif not (
                np.array_equal(active, active_saved)
                and np.array_equal(slave, slave_saved)
            ):
                raise ValueError("saved Task41 V4 columns disagree on active/slave original rows")

        if (
            int(fresh_active[TASK41_V4_SELECTED_ACTIVE_ROW])
            != TASK41_V4_SELECTED_ORIGINAL_ROW
            or int(constraints.original_to_active[TASK41_V4_SELECTED_ORIGINAL_ROW])
            != TASK41_V4_SELECTED_ACTIVE_ROW
        ):
            raise ValueError("fresh active/storage row identity differs for the frozen target row")

        manifest_cells: dict[tuple[int, int], Mapping[str, Any]] = {}
        manifest_classes: dict[tuple[int, float, float, float, int], Mapping[str, Any]] = {}
        raw_groups = manifest.get("raw_cell_diagnostics", ())
        if len(raw_groups) != 2:
            raise ValueError("Task41 V4 donor does not contain two raw-cell groups")
        for column_index, group in enumerate(raw_groups):
            if (
                group.get("structure_identity_passed") is not True
                or group.get("raw_matrices_are_independently_retabulated") is not True
                or len(group.get("cells", ())) != 3
            ):
                raise ValueError(f"Task41 V4 donor raw group {column_index} is incomplete")
            for cell in group["cells"]:
                cell_index = int(cell["cell_index"])
                key = _class_key(cell["class_key"])
                manifest_cells[(column_index, cell_index)] = cell
                class_artifacts = cell["class_artifacts"]
                if key in manifest_classes:
                    existing = manifest_classes[key]
                    if any(
                        existing[name].get("path") != class_artifacts[name].get("path")
                        for name in ("Vii", "Vit")
                    ):
                        raise ValueError(f"saved matrices are not shared for class {key!r}")
                else:
                    manifest_classes[key] = class_artifacts

        raw_classes = tuple(donor["raw_classes"])
        raw_by_key = {_class_key(item["class_key"]): item for item in raw_classes}
        if len(raw_classes) != 3 or len(raw_by_key) != 3 or set(raw_by_key) != set(manifest_classes):
            raise ValueError("Task41 V4 donor raw class set differs from its six cell maps")
        cell_maps = {
            (int(item["column"]), int(item["cell_index"])): item
            for item in donor["cell_maps"]
        }
        if len(cell_maps) != 6 or set(cell_maps) != set(manifest_cells):
            raise ValueError("Task41 V4 donor must provide exactly the six manifested cell maps")

        owner_cells_by_class: dict[tuple[int, float, float, float, int], int] = {}
        for cell_index, cell in enumerate(owner.cell_recovery_maps):
            owner_cells_by_class.setdefault(_class_key(cell.class_key), cell_index)
        fresh_class_records: dict[tuple[int, float, float, float, int], Mapping[str, Any]] = {}
        dimension = int(space.element.space_dimension)
        raw_class_workspace_bytes = (
            4 * dimension * dimension * np.dtype(np.complex128).itemsize
        )

        def independently_tabulate(cell_index: int, class_key: tuple[Any, ...]):
            allocation_gate(
                "task41_v4_raw_class_retabulation",
                {
                    "additional_payload_bytes": 0,
                    "workspace_bytes": raw_class_workspace_bytes,
                    "cell_index": int(cell_index),
                    "class_key": class_key,
                    "workspace_model": "four complex128 local dimension-squared tensors",
                },
            )
            return tabulate_volume_audit_cell(
                compiled_form,
                space,
                mesh_data.cell_tags,
                owner,
                cell_index,
            )

        for key, saved_class in raw_by_key.items():
            if key not in owner_cells_by_class:
                raise ValueError(f"fresh owner is missing saved raw class {key!r}")
            saved_vii = _check_artifact_array(
                manifest_classes[key]["Vii"], saved_class["Vii"], f"saved Vii class {key!r}"
            )
            saved_vit = _check_artifact_array(
                manifest_classes[key]["Vit"], saved_class["Vit"], f"saved Vit class {key!r}"
            )
            fresh = independently_tabulate(owner_cells_by_class[key], key)
            if not (np.array_equal(saved_vii, fresh["K"]) and np.array_equal(saved_vit, fresh["G"])):
                raise ValueError(f"fresh independent K/G differ from saved class {key!r}")
            fresh_class_records[key] = fresh

        local_class_identities = []
        for key in sorted(fresh_class_records):
            local_class_identities.append(
                _local_class_identity(
                    key,
                    fresh_class_records[key],
                    T=owner.trace_from_interior_rhs_by_class[key],
                    R=owner.interior_from_trace_by_class[key],
                    S=owner.retained_local_schur_by_class[key],
                )
            )

        for identity, saved in cell_maps.items():
            column_index, cell_index = identity
            manifest_cell = manifest_cells[identity]
            key = _class_key(saved["class_key"])
            cell = owner.cell_recovery_maps[cell_index]
            if key != _class_key(manifest_cell["class_key"]) or key != _class_key(cell.class_key):
                raise ValueError(f"fresh Task41 V4 class identity differs for cell {identity}")
            arrays_meta = manifest_cell["artifacts"]
            for field, name in (
                ("interior_original_rows", "interior_original_rows"),
                ("trace_original_rows", "trace_original_rows"),
                ("active_ids", "active_ids"),
                ("cell_permutation_info", "cell_permutation_info"),
                ("trace_expansion_data", "trace_expansion_data"),
                ("trace_expansion_indices", "trace_expansion_indices"),
                ("trace_expansion_indptr", "trace_expansion_indptr"),
            ):
                _check_artifact_array(arrays_meta[name], saved[field], f"saved cell {identity} {field}")
            if (
                not np.array_equal(
                    saved["interior_original_rows"], cell.interior_original_dofs
                )
                or not np.array_equal(saved["trace_original_rows"], cell.trace_original_dofs)
                or int(np.asarray(saved["cell_permutation_info"]).reshape(-1)[0]) != key[-1]
            ):
                raise ValueError(f"fresh Task41 V4 original rows or direction differ for cell {identity}")
            active_ids, fresh_E, _identity = _cell_trace_expansion(
                cell.trace_original_dofs,
                constraints,
            )
            if not np.array_equal(saved["active_ids"], active_ids):
                raise ValueError(f"fresh Task41 V4 active IDs differ for cell {identity}")
            saved_E = sparse.csr_matrix(
                (
                    saved["trace_expansion_data"],
                    saved["trace_expansion_indices"],
                    saved["trace_expansion_indptr"],
                ),
                shape=(len(cell.trace_original_dofs), len(saved["active_ids"])),
            )
            if not _csr_equal(saved_E, fresh_E):
                raise ValueError(f"fresh Task41 V4 MPC expansion differs for cell {identity}")
        progress(phase, "COMPLETED", active_rows=len(fresh_active), slave_rows=len(fresh_slave))

        phase = "selected_active_row_incidence"
        progress(phase, "STARTED", active_row=TASK41_V4_SELECTED_ACTIVE_ROW)
        selected_cells = list(
            iter_selected_volume_audit_cells(owner, [TASK41_V4_SELECTED_ACTIVE_ROW])
        )
        if not selected_cells:
            raise ValueError("fresh owner has no cells incident to the selected active row")
        selected_classes = tuple(dict.fromkeys(record["class_key"] for record in selected_cells))
        progress(
            phase,
            "COMPLETED",
            incident_cells=len(selected_cells),
            incident_classes=len(selected_classes),
        )

        phase = "evidence_budget_preflight"
        arrays_by_class: dict[tuple[int, float, float, float, int], Mapping[str, Any]] = {}
        for class_key in selected_classes:
            record = fresh_class_records.get(class_key)
            if record is None:
                representative = next(
                    cell["cell_index"]
                    for cell in selected_cells
                    if cell["class_key"] == class_key
                )
                record = independently_tabulate(representative, class_key)
                fresh_class_records[class_key] = record
            arrays_by_class[class_key] = record

        class_cache_bytes = 0
        for class_key in selected_classes:
            lu, pivots = owner.interior_lu_by_class[class_key]
            class_cache_bytes += sum(
                value.nbytes
                for value in (
                    owner.trace_from_interior_rhs_by_class[class_key],
                    owner.interior_from_trace_by_class[class_key],
                    owner.retained_local_schur_by_class[class_key],
                    lu,
                    pivots,
                )
            )
        block_bytes = sum(
            record[name].nbytes
            for record in arrays_by_class.values()
            for name in ("K", "G", "J", "L")
        )
        map_arrays = [
            array
            for cell in selected_cells
            for array in (
                cell["interior_original_dofs"],
                cell["trace_original_dofs"],
                cell["active_ids"],
                cell["E"].data,
                cell["E"].indices,
                cell["E"].indptr,
            )
        ]
        map_bytes = sum(array.nbytes for array in map_arrays)
        array_count = 9 * len(selected_classes) + 6 * len(selected_cells)
        new_evidence_upper = (
            class_cache_bytes + block_bytes + map_bytes + array_count * 4096 + 1_048_576
        )
        cumulative_upper = existing_bytes + new_evidence_upper
        if cumulative_upper > TASK41_V4_EVIDENCE_CAP_BYTES:
            raise MemoryError(
                f"Task41 V4 evidence cap exceeded: {cumulative_upper} > "
                f"{TASK41_V4_EVIDENCE_CAP_BYTES} bytes"
            )
        output_path = Path(output_directory)
        disk_probe = output_path if output_path.exists() else output_path.parent
        while not disk_probe.exists() and disk_probe != disk_probe.parent:
            disk_probe = disk_probe.parent
        free_bytes = int(shutil.disk_usage(disk_probe).free)
        if free_bytes - new_evidence_upper < TASK41_V4_FREE_SPACE_FLOOR_BYTES:
            raise OSError("Task41 V4 volume evidence would breach the 2 GiB free-space floor")

        peak_workspace = class_cache_bytes + 3 * dimension * dimension * np.dtype(np.complex128).itemsize
        allocation_gate(
            "task41_v4_volume_only_evidence_preflight",
            {
                "additional_payload_bytes": 0,
                "workspace_bytes": peak_workspace,
                "incident_cells": len(selected_cells),
                "incident_classes": len(selected_classes),
                "existing_donor_bytes": existing_bytes,
                "new_evidence_bytes_upper": new_evidence_upper,
                "cumulative_evidence_bytes_upper": cumulative_upper,
                "evidence_cap_bytes": TASK41_V4_EVIDENCE_CAP_BYTES,
                "free_space_bytes": free_bytes,
                "free_space_floor_bytes": TASK41_V4_FREE_SPACE_FLOOR_BYTES,
                "donor_arrays_copied": False,
            },
        )
        progress(
            phase,
            "COMPLETED",
            existing_bytes=existing_bytes,
            new_bytes_upper=new_evidence_upper,
            cumulative_bytes_upper=cumulative_upper,
            free_bytes=free_bytes,
        )

        phase = "selected_volume_class_and_map_persist"
        progress(phase, "STARTED", classes=len(selected_classes), cells=len(selected_cells))

        def persist(name: str, array: np.ndarray) -> Mapping[str, Any]:
            return persist_array(name, np.asarray(array))

        class_records = []
        persisted_bytes = 0
        for class_key in selected_classes:
            class_digest = hashlib.sha256(repr(class_key).encode("ascii")).hexdigest()[:16]
            raw = arrays_by_class[class_key]
            lu, pivots = owner.interior_lu_by_class[class_key]
            payloads = {
                "K": raw["K"],
                "G": raw["G"],
                "J": raw["J"],
                "L": raw["L"],
                "T": owner.trace_from_interior_rhs_by_class[class_key],
                "R": owner.interior_from_trace_by_class[class_key],
                "S": owner.retained_local_schur_by_class[class_key],
                "LU_factor": lu,
                "LU_pivots": pivots,
            }
            artifacts = {}
            for name, array in payloads.items():
                artifact = persist(
                    f"task41_v4_volume_class_{class_digest}_{name}",
                    np.asarray(array),
                )
                artifacts[name] = dict(artifact)
                persisted_bytes += int(artifact.get("bytes", array.nbytes + 4096))
            class_records.append(
                {
                    "class_key": class_key,
                    "representative_cell": raw["cell_index"],
                    "hashes": dict(raw["hashes"]),
                    "artifacts": artifacts,
                }
            )

        cell_records = []
        for cell in selected_cells:
            cell_index = int(cell["cell_index"])
            payloads = {
                "interior_original_rows": cell["interior_original_dofs"],
                "trace_original_rows": cell["trace_original_dofs"],
                "active_ids": cell["active_ids"],
                "trace_expansion_data": cell["E"].data,
                "trace_expansion_indices": cell["E"].indices,
                "trace_expansion_indptr": cell["E"].indptr,
            }
            artifacts = {}
            for name, array in payloads.items():
                artifact = persist(
                    f"task41_v4_volume_cell_{cell_index:05d}_{name}",
                    np.asarray(array),
                )
                artifacts[name] = dict(artifact)
                persisted_bytes += int(artifact.get("bytes", array.nbytes + 4096))
            cell_records.append(
                {
                    "cell_index": cell_index,
                    "class_key": cell["class_key"],
                    "original_row_identity_passed": True,
                    "artifacts": artifacts,
                }
            )
        if existing_bytes + persisted_bytes > TASK41_V4_EVIDENCE_CAP_BYTES:
            raise MemoryError("Task41 V4 persisted evidence exceeded its cumulative 16 GiB cap")
        progress(
            phase,
            "COMPLETED",
            persisted_bytes=persisted_bytes,
            cumulative_bytes=existing_bytes + persisted_bytes,
            class_records=len(class_records),
            cell_records=len(cell_records),
        )
        return {
            "levels": levels,
            "compiled_form": compiled_form,
            "condensed": owner,
            "class_records": tuple(class_records),
            "cell_records": tuple(cell_records),
            "audit": {
                "donor_manifest_sha256": donor["manifest_sha256"],
                "fresh_active_rows_match": True,
                "fresh_slave_rows_match": True,
                "saved_raw_class_count_verified": len(raw_by_key),
                "saved_cell_map_count_verified": len(cell_maps),
                "selected_active_row": TASK41_V4_SELECTED_ACTIVE_ROW,
                "selected_original_row": TASK41_V4_SELECTED_ORIGINAL_ROW,
                "donor_arrays_copied": False,
                "matrix_materialized": False,
                "surface_or_carrier_constructed": False,
                "local_class_identities": local_class_identities,
                "evidence_bytes_existing": existing_bytes,
                "evidence_bytes_added": persisted_bytes,
                "evidence_bytes_cumulative": existing_bytes + persisted_bytes,
            },
        }
    except Exception as exc:
        progress(phase, "FAILED", error=f"{type(exc).__name__}: {exc}")
        if owner is not None:
            owner.destroy()
        raise


def audit_task41_v4_volume_identity(
    owner: AssemblyTimeCondensedSystem,
    donor: Mapping[str, Any],
    *,
    allocation_gate: Callable[[str, Mapping[str, Any]], Any],
    progress_callback: Callable[[Mapping[str, Any]], Any],
    persist_array: Callable[[str, np.ndarray], Mapping[str, Any]],
    output_directory: str | Path,
) -> dict[str, Any]:
    """Replay the trace-only production P6 action and RHS identities.

    ``donor`` is the checker's normalized view.  The 64,120 saved port rows are
    compared and carried through unchanged; the fresh action view has zero
    appended rows and borrows the same S/T/LU cache from ``owner``.
    """

    if not all(callable(item) for item in (allocation_gate, progress_callback, persist_array)):
        raise TypeError("Task41 V4 identity replay requires allocation, progress, and persistence callbacks")
    columns = tuple(donor["columns"])
    identity = donor["attribution"]
    joint = identity["joint"]
    saved_p6 = np.asarray(joint["p6_result"])
    saved_reduced = np.asarray(joint["reduced_rhs"])
    saved_port_rhs = np.asarray(joint["port_rhs"])
    active_rows = int(owner.active_rows)
    port_rows = int(owner.appended_rows)
    full_rows = int(owner.full_rows)
    if (
        len(columns) != 2
        or saved_p6.shape != (active_rows + port_rows, 2)
        or saved_reduced.shape != saved_p6.shape
        or saved_port_rhs.shape != (port_rows, 2)
        or any(value.dtype != np.dtype(np.complex128) for value in (saved_p6, saved_reduced, saved_port_rhs))
        or any(not np.isfinite(value).all() for value in (saved_p6, saved_reduced, saved_port_rhs))
    ):
        raise ValueError("Task41 V4 saved full-action arrays differ from the fresh owner layout")

    active_original = np.asarray(columns[0]["active_original_rows"])
    slave_rows = np.asarray(columns[0]["slave_rows"])
    if (
        active_original.shape != (active_rows,)
        or active_original.dtype.kind not in "iu"
        or slave_rows.dtype.kind not in "iu"
        or any(not np.array_equal(active_original, np.asarray(column["active_original_rows"])) for column in columns[1:])
        or any(not np.array_equal(slave_rows, np.asarray(column["slave_rows"])) for column in columns[1:])
    ):
        raise ValueError("Task41 V4 input columns disagree on active/slave storage rows")
    constraints = owner.trace_constraints
    if len(constraints.owned_active_original_dofs) != active_rows:
        raise ValueError("Task41 V4 active original-row map differs from the fresh owner")
    original_to_active = constraints.original_to_active
    if slave_rows.size > 1 and np.any(slave_rows[1:] < slave_rows[:-1]):
        raise ValueError("Task41 V4 saved slave rows are not sorted for safe identity checks")

    def any_nonzero_at_rows(values: np.ndarray, rows: np.ndarray) -> bool:
        for start in range(0, rows.size, 262_144):
            if np.any(np.asarray(values[rows[start : start + 262_144]]) != 0.0):
                return True
        return False

    expansion_by_original = constraints.expansion_by_original
    max_expansion_terms = max(
        (len(item[0]) for item in expansion_by_original.values()), default=1
    )
    index_size = np.asarray(owner.cell_recovery_maps[0].interior_original_dofs).dtype.itemsize
    local_interior_rows = sum(len(cell.interior_original_dofs) for cell in owner.cell_recovery_maps)
    local_trace_rows = sum(len(cell.trace_original_dofs) for cell in owner.cell_recovery_maps)
    cell_count = len(owner.cell_recovery_maps)
    expansion_nnz_upper = local_trace_rows * max_expansion_terms
    action_payload_upper = (
        index_size
        * (
            local_interior_rows
            + 2 * local_trace_rows
            + cell_count
            + 2 * expansion_nnz_upper
        )
        + np.dtype(np.complex128).itemsize * expansion_nnz_upper
        + 512 * cell_count
    )
    identity_array_bytes = 14 * active_rows * np.dtype(np.complex128).itemsize + 14 * 4096
    prior_new_bytes = int(donor.get("prior_new_evidence_bytes", 0))
    cumulative_evidence_upper = (
        int(donor["existing_evidence_bytes"]) + prior_new_bytes + identity_array_bytes
    )
    if cumulative_evidence_upper > TASK41_V4_EVIDENCE_CAP_BYTES:
        raise MemoryError("Task41 V4 identity evidence would exceed the cumulative 16 GiB cap")
    output_path = Path(output_directory)
    disk_probe = output_path if output_path.exists() else output_path.parent
    while not disk_probe.exists() and disk_probe != disk_probe.parent:
        disk_probe = disk_probe.parent
    free_bytes = int(shutil.disk_usage(disk_probe).free)
    if free_bytes - identity_array_bytes < TASK41_V4_FREE_SPACE_FLOOR_BYTES:
        raise OSError("Task41 V4 identity evidence would breach the 2 GiB free-space floor")
    vector_workspace = np.dtype(np.complex128).itemsize * (
        full_rows + 4 * (active_rows + 1)
    )
    allocation_gate(
        "task41_v4_production_volume_action_preflight",
        {
            "additional_payload_bytes": int(action_payload_upper),
            "workspace_bytes": int(vector_workspace),
            "cell_count": cell_count,
            "max_constraint_expansion_terms": max_expansion_terms,
            "active_rows": active_rows,
            "appended_rows_in_action_view": 0,
            "global_matrix_materialized": False,
            "dense_port_block_materialized": False,
            "new_identity_evidence_bytes_upper": identity_array_bytes,
            "cumulative_evidence_bytes_upper": cumulative_evidence_upper,
            "evidence_cap_bytes": TASK41_V4_EVIDENCE_CAP_BYTES,
            "free_space_bytes": free_bytes,
            "free_space_floor_bytes": TASK41_V4_FREE_SPACE_FLOOR_BYTES,
        },
    )
    progress_callback({"phase": "production_volume_action_view", "status": "STARTED"})
    # The shallow dataclass view keeps every numerical owner/cache shared while
    # making the production action trace-only.  Saved port rows stay external.
    volume_owner = replace(owner, appended_rows=0, owned_appended_rows=0)
    action = P6CellCondensedAction(
        volume_owner,
        H_p=np.zeros((0, 0), dtype=np.complex128),
    )
    column_metrics = []
    replay_artifacts: list[dict[str, Any]] = []
    persisted_bytes = 0

    def persist(name: str, values: np.ndarray) -> None:
        nonlocal persisted_bytes
        artifact = dict(persist_array(name, np.asarray(values)))
        artifact_bytes = int(artifact.get("bytes", np.asarray(values).nbytes + 4096))
        persisted_bytes += artifact_bytes
        if int(donor["existing_evidence_bytes"]) + prior_new_bytes + persisted_bytes > TASK41_V4_EVIDENCE_CAP_BYTES:
            raise MemoryError("Task41 V4 persisted identity evidence exceeded the cumulative 16 GiB cap")
        replay_artifacts.append({"name": name, **artifact})
    try:
        for column_index, column in enumerate(columns):
            progress_callback({"phase": "production_volume_column", "status": "STARTED", "column": column_index})
            known = np.asarray(column["known_field"])
            native_rhs = np.asarray(column["native_rhs"])
            volume_rhs = np.asarray(column["native_volume_rhs"])
            b_alpha_rows = np.asarray(column["b_alpha_rows"])
            b_alpha_values = np.asarray(column["b_alpha_values"])
            if (
                known.shape != (full_rows,)
                or native_rhs.shape != (full_rows,)
                or volume_rhs.shape != (full_rows,)
                or any(value.dtype != np.dtype(np.complex128) for value in (known, native_rhs, volume_rhs))
                or b_alpha_rows.ndim != 1
                or b_alpha_rows.dtype.kind not in "iu"
                or b_alpha_values.shape != b_alpha_rows.shape
                or b_alpha_values.dtype != np.dtype(np.complex128)
                or not np.isfinite(b_alpha_values).all()
                or (b_alpha_rows.size and (np.any(b_alpha_rows < 0) or np.any(b_alpha_rows >= full_rows)))
                or any_nonzero_at_rows(known, slave_rows)
                or any_nonzero_at_rows(native_rhs, slave_rows)
                or any_nonzero_at_rows(volume_rhs, slave_rows)
            ):
                raise ValueError(f"Task41 V4 column {column_index} has invalid vectors or slave-row support")
            slave_positions = np.searchsorted(slave_rows, b_alpha_rows)
            if slave_positions.size and len(slave_rows):
                valid_slave_positions = slave_positions < len(slave_rows)
                if np.any(
                    valid_slave_positions
                    & (slave_rows[np.minimum(slave_positions, len(slave_rows) - 1)] == b_alpha_rows)
                ):
                    raise ValueError("saved B-alpha has nonzero support on an MPC slave row")
            b_active_ids = np.empty(len(b_alpha_rows), dtype=np.int64)
            for index, original in enumerate(b_alpha_rows):
                active_id = original_to_active.get(int(original))
                if active_id is None:
                    raise ValueError("saved B-alpha row is not an independent active trace row")
                b_active_ids[index] = active_id

            source = np.zeros(active_rows, dtype=np.complex128)
            np.take(known, active_original, out=source)
            s_volume = action.apply(source)
            g_volume = action.reduce_rhs(volume_rhs, rhs_is_mpc_dual=True)
            if s_volume.shape != (active_rows,) or g_volume.shape != (active_rows,):
                raise ValueError("Task41 V4 production trace action/reducer returned an invalid shape")
            # Reuse g_volume storage for the pure-volume defect d_vol = S t - g_vol.
            g_volume *= -1.0
            g_volume += s_volume
            d_volume = g_volume

            s_full = s_volume
            np.add.at(s_full, b_active_ids, b_alpha_values)
            g_full = action.reduce_rhs(native_rhs, rhs_is_mpc_dual=True)
            if g_full.shape != (active_rows,):
                raise ValueError("Task41 V4 production full-RHS reducer returned an invalid trace shape")
            persist(f"task41_v4_s_full_trace_col{column_index}", s_full)
            persist(f"task41_v4_g_full_trace_col{column_index}", g_full)
            persist(f"task41_v4_d_volume_trace_col{column_index}", d_volume)
            rhs_decomposition_roundoff = _rhs_decomposition_metrics(
                native_rhs, volume_rhs, b_alpha_rows, b_alpha_values
            )
            saved_denom = max(
                _vector_norm(saved_p6[:, column_index]),
                _vector_norm(saved_reduced[:, column_index]),
                np.finfo(float).tiny,
            )
            saved_d = _difference_metrics(
                saved_p6[:, column_index], saved_reduced[:, column_index]
            )
            saved_d_trace = _difference_metrics(
                saved_p6[:active_rows, column_index], saved_reduced[:active_rows, column_index]
            )
            s_saved = _difference_metrics(
                s_full, saved_p6[:active_rows, column_index]
            )
            g_saved = _difference_metrics(
                g_full, saved_reduced[:active_rows, column_index]
            )
            old_port_action = saved_p6[active_rows:, column_index]
            old_port_reduced = saved_reduced[active_rows:, column_index]
            port_compare = {
                "p6_vs_reduced": _difference_metrics(old_port_action, old_port_reduced),
                "p6_vs_saved_port_rhs": _difference_metrics(old_port_action, saved_port_rhs[:, column_index]),
                "reduced_vs_saved_port_rhs": _difference_metrics(old_port_reduced, saved_port_rhs[:, column_index]),
            }
            s_full -= g_full
            d_full_trace = s_full
            replayed_full_norm = _vector_norm(d_full_trace)
            trace_old_norm = saved_d_trace["absolute_l2"]
            old_port_norm = port_compare["p6_vs_reduced"]["absolute_l2"]
            replayed_full_l2 = float(np.hypot(replayed_full_norm, old_port_norm))
            replayed_full_relative = replayed_full_l2 / saved_denom
            full_trace_gate = {
                "absolute_l2": replayed_full_norm,
                "same_original_denominator_relative": replayed_full_relative,
                "original_denominator": saved_denom,
                "max_abs": float(np.max(np.abs(d_full_trace))) if d_full_trace.size else 0.0,
                "max_row": int(np.argmax(np.abs(d_full_trace))) if d_full_trace.size else None,
                "full_saved_difference_absolute_l2": trace_old_norm,
                "saved_port_difference_absolute_l2": old_port_norm,
                "same_original_1e_11_gate_passed": replayed_full_relative <= 1.0e-11,
            }

            state_metrics = []
            for state in column["states"]:
                state_label = str(state["label"])
                state_storage = np.asarray(state["storage"])
                volume_residual = np.asarray(state["native_volume_residual"])
                volume_action = np.asarray(state["native_volume_action"])
                if (
                    state_storage.shape != (full_rows,)
                    or state_storage.dtype != np.dtype(np.complex128)
                    or any_nonzero_at_rows(state_storage, slave_rows)
                    or volume_residual.shape != (full_rows,)
                    or volume_action.shape != (full_rows,)
                    or volume_residual.dtype != np.dtype(np.complex128)
                    or volume_action.dtype != np.dtype(np.complex128)
                    or any_nonzero_at_rows(volume_residual, slave_rows)
                    or any_nonzero_at_rows(volume_action, slave_rows)
                ):
                    raise ValueError(f"Task41 V4 {state_label} residual/action layout differs")
                for start in range(0, active_rows, 262_144):
                    active_chunk = active_original[start : start + 262_144]
                    if not np.array_equal(
                        state_storage[active_chunk], known[active_chunk]
                    ):
                        raise ValueError(
                            f"Task41 V4 {state_label} state changed the saved active trace"
                        )
                residual_volume_reduced = action.reduce_rhs(
                    volume_residual, rhs_is_mpc_dual=True
                )
                persist(
                    f"task41_v4_reduce_r_volume_{state_label}_col{column_index}",
                    residual_volume_reduced,
                )
                volume_identity = _sum_metrics(d_volume, residual_volume_reduced)
                volume_identity["same_original_denominator_relative"] = (
                    volume_identity["absolute_l2"] / saved_denom
                )

                residual_full = np.empty(full_rows, dtype=np.complex128)
                for start in range(0, full_rows, 262_144):
                    stop = min(full_rows, start + 262_144)
                    residual_full[start:stop] = (
                        native_rhs[start:stop] - volume_action[start:stop]
                    )
                np.add.at(residual_full, b_alpha_rows, -b_alpha_values)
                full_residual_vs_volume_residual = _difference_metrics(
                    residual_full, volume_residual
                )
                residual_full_reduced = action.reduce_rhs(
                    residual_full, rhs_is_mpc_dual=True
                )
                persist(
                    f"task41_v4_reduce_r_full_{state_label}_col{column_index}",
                    residual_full_reduced,
                )
                full_identity = _sum_metrics(d_full_trace, residual_full_reduced)
                full_identity["same_original_denominator_relative"] = (
                    full_identity["absolute_l2"] / saved_denom
                )
                state_metrics.append(
                    {
                        "state": state_label,
                        "volume_identity_dvol_plus_reduce_rvol": volume_identity,
                        "full_identity_dfull_plus_reduce_rfull": full_identity,
                        "rhs_decomposition_roundoff_native_rhs_minus_action_minus_Balpha_vs_saved_volume_residual": {
                            **full_residual_vs_volume_residual,
                            "same_original_denominator_relative": full_residual_vs_volume_residual["absolute_l2"] / saved_denom,
                        },
                        "rhs_split_roundoff_native_rhs_minus_Balpha_minus_volume_rhs": {
                            **rhs_decomposition_roundoff,
                            "same_original_denominator_relative": rhs_decomposition_roundoff["absolute_l2"] / saved_denom,
                        },
                        "volume_residual_norm": _vector_norm(volume_residual),
                        "full_residual_norm": _vector_norm(residual_full),
                    }
                )
                del residual_volume_reduced, residual_full_reduced, residual_full

            column_metrics.append(
                {
                    "column": column_index,
                    "saved_original_denom": saved_denom,
                    "saved_full_d": saved_d,
                    "saved_trace_d": saved_d_trace,
                    "production_s_full_vs_saved_p6_trace": s_saved,
                    "production_g_full_vs_saved_reduced_rhs_trace": g_saved,
                    "saved_port_comparisons": port_compare,
                    "replayed_full_d_trace_and_original_gate": full_trace_gate,
                    "pure_volume_d_trace_norm": _vector_norm(d_volume),
                    "states": state_metrics,
                }
            )
            progress_callback(
                {"phase": "production_volume_column", "status": "COMPLETED", "column": column_index}
            )
        return {
            "schema": "task41.p0.v4.volume_only_attribution.v1",
            "completed": True,
            "production_action": "P6CellCondensedAction_active_only_shared_owner_caches",
            "rhs_reducer": "P6CellCondensedAction.reduce_rhs(rhs_is_mpc_dual=True)",
            "active_rows": active_rows,
            "saved_port_rows": port_rows,
            "saved_port_rows_reused": True,
            "global_volume_matrix_materialized": False,
            "dense_port_matrix_materialized": False,
            "carrier_or_surface_constructed": False,
            "local_class_identities": list(identity.get("local_class_identities", ())),
            "replay_artifacts": replay_artifacts,
            "new_identity_evidence_bytes": persisted_bytes,
            "cumulative_evidence_bytes": int(donor["existing_evidence_bytes"]) + prior_new_bytes + persisted_bytes,
            "columns": column_metrics,
        }
    finally:
        action.destroy()
