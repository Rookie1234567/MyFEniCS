"""Supervised Task41 V4 volume-only extraction and RHS attribution worker."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from time import perf_counter
import math
from typing import Any, Mapping

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TASK41_P0_V4_SOURCE_REPORT_SHA256 = (
    "09e96eb8c9d52b4cf0c29570fd8df3c1f820bc208104d91edd102978dfc9c4d5"
)
TASK41_P0_V5_GEOMETRY_REFERENCE_SHA256 = (
    "a47eb7a8795b5af542c23ae45915588d89c962d1af1bb8360b8a9d42f1e7c031"
)
TASK41_P0_V5_REFERENCE_CELLS = (26762, 26897)
TASK41_P0_V4_SELECTED_ACTIVE_ROW = 5_458_716
TASK41_P0_V4_SELECTED_ORIGINAL_ROW = 17_692_332
TASK41_P0_V5_POSTBUILD_SAFETY_FACTOR = 1.10
TASK41_P0_V5_PREFIX_MINIMUM_SECONDS = 600.0
TASK41_P0_V5_TERMINATION_RESERVE_SECONDS = 300.0


class _CandidateNotAdmitted(RuntimeError):
    """Exact-geometry candidate lacks fixed-window or resource headroom."""


def _v4_required_checker_watchdog_elapsed_seconds(
    v4_extraction: Mapping[str, Any],
) -> float:
    value = float(v4_extraction["required_checker_watchdog_elapsed_seconds"])
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError("V4 required-checker watchdog elapsed time is not finite and positive")
    return value


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _persist_array(
    directory: Path,
    name: str,
    value: np.ndarray,
    *,
    sha256_file: Any,
) -> dict[str, Any]:
    if not name or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for char in name):
        raise ValueError("Task41 V4 evidence array name is not a safe leaf")
    path = directory / f"{name}.npy"
    temporary = directory / f".{name}.npy.tmp"
    if path.exists() or temporary.exists():
        raise FileExistsError(f"Task41 V4 evidence output already exists: {path}")
    array = np.asarray(value)
    with temporary.open("xb") as stream:
        np.save(stream, array, allow_pickle=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    return {
        "path": str(path.resolve()),
        "sha256": sha256_file(path),
        "bytes": int(path.stat().st_size),
        "shape": list(array.shape),
        "dtype": str(array.dtype),
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--numerical-output", type=Path, required=True)
    parser.add_argument("--donor-contract", type=Path, required=True)
    parser.add_argument("--donor-contract-sha256", required=True)
    parser.add_argument("--consumer-contract", type=Path, required=True)
    parser.add_argument("--consumer-contract-sha256", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--geometry-pair-only", action="store_true")
    parser.add_argument(
        "--geometry-policy",
        choices=("canonical", "mesh_actual_exact"),
        default="canonical",
    )
    parser.add_argument("--source-report", type=Path)
    parser.add_argument("--geometry-reference-report", type=Path)
    return parser.parse_args(argv)


def _checked_allocation_gate(
    label: str,
    facts: Mapping[str, Any],
    *,
    resource_admission: Any,
    resource_snapshot: Any,
    resources: Mapping[str, Any],
    progress: Any,
) -> None:
    required = int(facts.get("additional_payload_bytes", 0)) + int(facts.get("workspace_bytes", 0))
    admission = resource_admission(
        f"task41_v4_{label}",
        required,
        resource_sample=resource_snapshot,
        require_task_cgroup=True,
        explicit_process_tree_cap_bytes=int(resources["task_memory_max_bytes"]),
        host_reserve_bytes=int(resources["host_reserve_bytes"]),
        task_cgroup_reserve_bytes=int(resources.get("task_cgroup_reserve_bytes", 0)),
    )
    progress(
        {
            "phase": "allocation_gate",
            "status": "PASSED",
            "label": label,
            "additional_upper_bytes": required,
            "resource_admission": admission,
        }
    )


def _compiled_kernel_identity(compiled_form: Any, *, rank: int, label: str, sha256_file: Any) -> dict[str, Any]:
    form = compiled_form.ufcx_form
    ffi = compiled_form.module.ffi
    signature = ffi.string(form.signature).decode("ascii")
    # The existing raw-cell core only indexes the cell-integral offset pair.
    # Read that same bounded pair; do not walk the opaque FFCx pointer table.
    offsets = [int(form.form_integral_offsets[index]) for index in range(2)]
    if offsets[0] != 0 or offsets[1] < offsets[0]:
        raise ValueError("FFCx cell-integral offsets are invalid")
    if offsets[1] > 128:
        raise ValueError("FFCx cell-integral count is outside the finite identity bound")
    kernel_counts: dict[int, int] = {}
    for position in range(offsets[0], offsets[1]):
        integral_id = int(form.form_integral_ids[position])
        kernel = form.form_integrals[position].tabulate_tensor_complex128
        if kernel == ffi.NULL:
            raise TypeError("compiled form does not expose a complex128 cell kernel")
        kernel_counts[integral_id] = kernel_counts.get(integral_id, 0) + 1
    module_path_value = getattr(compiled_form.module, "__file__", None)
    module_path = None
    module_sha256 = None
    if module_path_value:
        candidate = Path(module_path_value).resolve()
        if candidate.is_file():
            module_path = str(candidate)
            module_sha256 = sha256_file(candidate)
    return {
        "label": label,
        "form_rank": int(rank),
        "ffcx_form_signature": signature,
        "ffcx_module_path": module_path,
        "ffcx_module_sha256": module_sha256,
        "cell_integral_count": offsets[1] - offsets[0],
        "cell_integral_offsets": offsets,
        "integral_kernel_counts": {
            str(key): kernel_counts[key] for key in sorted(kernel_counts)
        },
        "num_coefficients": int(form.num_coefficients),
        "num_constants": int(form.num_constants),
        "dtype": str(np.dtype(compiled_form.dtype)),
    }


def _load_bound_report_array(
    source_root: Path,
    records: Mapping[str, Mapping[str, Any]],
    name: str,
    *,
    sha256_file: Any,
) -> np.ndarray:
    record = records.get(name)
    if not isinstance(record, Mapping):
        raise ValueError(f"Task41 V4 source report omits saved array {name}")
    raw_path = Path(str(record.get("path", "")))
    path = (raw_path if raw_path.is_absolute() else source_root / raw_path).resolve(strict=True)
    if not path.is_relative_to(source_root) or path.stat().st_size != int(record.get("bytes", -1)):
        raise ValueError(f"Task41 V4 source array path or size differs for {name}")
    if sha256_file(path) != record.get("sha256"):
        raise ValueError(f"Task41 V4 source array hash differs for {name}")
    value = np.load(path, allow_pickle=False)
    if list(value.shape) != list(record.get("shape", ())) or str(value.dtype) != str(record.get("dtype")):
        raise ValueError(f"Task41 V4 source array metadata differs for {name}")
    return np.asarray(value)


def _load_v5_geometry_reference(
    report_path: Path,
    *,
    donor_manifest_sha256: str,
    sha256_file: Any,
) -> dict[str, Any]:
    report_path = report_path.resolve(strict=True)
    source_root = report_path.parent.resolve(strict=True)
    if not source_root.is_relative_to((ROOT / "results").resolve()):
        raise ValueError("V5 geometry reference report must remain in the registered results tree")
    if sha256_file(report_path) != TASK41_P0_V5_GEOMETRY_REFERENCE_SHA256:
        raise ValueError("V5 geometry reference report SHA-256 differs from the frozen V4 evidence")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    probe = report.get("geometry_pair_probe")
    if (
        report.get("status") != "COMPLETED_GEOMETRY_PAIR_PROBE"
        or not isinstance(probe, Mapping)
        or probe.get("schema") != "task41.p0.v4.geometry_pair_probe.v1"
        or probe.get("source_report_sha256") != TASK41_P0_V4_SOURCE_REPORT_SHA256
        or probe.get("source_donor_manifest_sha256") != donor_manifest_sha256
        or [item.get("cell_index") for item in probe.get("selected_cells", [])]
        != list(TASK41_P0_V5_REFERENCE_CELLS)
    ):
        raise ValueError("V5 geometry reference is not the frozen two-cell V4 report")
    records_list = report.get("persisted_evidence_arrays")
    if not isinstance(records_list, list):
        raise ValueError("V5 geometry reference omits its hash-bound array inventory")
    records = {
        str(item["name"]): item
        for item in records_list
        if isinstance(item, Mapping) and isinstance(item.get("name"), str)
    }
    if len(records) != len(records_list):
        raise ValueError("V5 geometry reference has duplicate or malformed array identities")
    references: dict[int, dict[str, Any]] = {}
    for cell in probe["selected_cells"]:
        index = int(cell["cell_index"])
        prefix = f"cell{index}_actual_"
        geometry = _load_bound_report_array(
            source_root,
            records,
            f"cell{index}_actual_geometry_coordinates",
            sha256_file=sha256_file,
        )
        blocks = {
            name: _load_bound_report_array(
                source_root,
                records,
                prefix + name,
                sha256_file=sha256_file,
            )
            for name in ("K", "G", "J", "L")
        }
        block_meta = cell["block_artifacts"]["actual"]
        if any(
            not isinstance(block_meta.get(name), Mapping)
            or block_meta[name].get("sha256") != records[prefix + name].get("sha256")
            or block_meta[name].get("shape") != records[prefix + name].get("shape")
            or block_meta[name].get("dtype") != records[prefix + name].get("dtype")
            for name in ("K", "G", "J", "L")
        ):
            raise ValueError(f"V5 reference inventory disagrees with selected cell {index} block metadata")
        references[index] = {
            "coordinates": geometry,
            "blocks": blocks,
            "block_sha256": {
                name: str(records[prefix + name]["sha256"])
                for name in ("K", "G", "J", "L")
            },
            "coordinates_sha256": str(
                records[f"cell{index}_actual_geometry_coordinates"]["sha256"]
            ),
        }
    return {
        "path": str(report_path),
        "sha256": TASK41_P0_V5_GEOMETRY_REFERENCE_SHA256,
        "source_root": str(source_root),
        "cells": references,
    }


def _run_geometry_pair_probe(
    *,
    cfg: Any,
    donor: dict[str, Any],
    source_report_path: Path,
    consumer_contract: Mapping[str, Any],
    output_directory: Path,
    persist_array: Any,
    allocation_gate: Any,
    progress: Any,
    sha256_file: Any,
) -> dict[str, Any]:
    """Extract and attribute only the two frozen selected-row incident cells."""

    import ufl
    from basix.ufl import element
    from dolfinx import default_real_type, fem
    from mpi4py import MPI

    from src.geometry.mesh_builder_3d import _mark_cells, _stage4_axis_plan, _structured_hexa_mesh
    from src.solvers.common_3d_forms import _build_physical_volume_terms
    from src.solvers.fullspace_same_mesh_hcurl_pmg_setup import SAME_MESH_JIT_OPTIONS
    from src.solvers.hcurl_assembly_time_condensation import tabulate_volume_audit_cell_geometry_pair
    from src.solvers.task41_v4_volume_only_audit import audit_task41_v4_geometry_pair_attribution

    selected_cells = (26762, 26897)
    source_report_path = source_report_path.resolve(strict=True)
    source_root = source_report_path.parent.resolve(strict=True)
    expected_report_sha = TASK41_P0_V4_SOURCE_REPORT_SHA256
    if not source_root.is_relative_to((ROOT / "results").resolve()):
        raise ValueError("Task41 V4 source report must remain inside this repository's results tree")
    if sha256_file(source_report_path) != expected_report_sha:
        raise ValueError("Task41 V4 source report SHA-256 differs from the frozen Review V4 receipt")
    source_report = json.loads(source_report_path.read_text(encoding="utf-8"))
    if (
        source_report.get("status") != "COMPLETED"
        or source_report.get("donor_manifest_sha256") != donor.get("manifest_sha256")
        or source_report.get("consumer_source_sha") != "d883c1f3381b4f3d6100022097d615846564673c"
        or source_report.get("owner_audit", {}).get("selected_active_row")
        != TASK41_P0_V4_SELECTED_ACTIVE_ROW
        or source_report.get("owner_audit", {}).get("selected_original_row")
        != TASK41_P0_V4_SELECTED_ORIGINAL_ROW
    ):
        raise ValueError("Task41 V4 source receipt is not the frozen two-cell donor")
    records_list = source_report.get("persisted_evidence_arrays")
    if not isinstance(records_list, list):
        raise ValueError("Task41 V4 source receipt omits its hash-bound array inventory")
    records = {
        str(item["name"]): item for item in records_list
        if isinstance(item, Mapping) and isinstance(item.get("name"), str)
    }
    if len(records) != len(records_list):
        raise ValueError("Task41 V4 source receipt has duplicate or malformed array names")
    class_keys = {
        tuple(item["class_key"])
        for item in source_report.get("identity_audit", {}).get("local_class_identities", ())
        if isinstance(item, Mapping) and isinstance(item.get("class_key"), list)
    }

    allocation_gate(
        "geometry_pair_mesh_rebuild",
        {"additional_payload_bytes": 0, "workspace_bytes": 6 * 1024**3, "degree": 6},
    )
    prior_bytes = int(donor["existing_evidence_bytes"]) + int(source_report["persisted_evidence_bytes"])
    if prior_bytes >= 16 * 1024**3:
        raise MemoryError("Task41 V4 geometry-pair input is already at the unchanged 16 GiB cap")
    if not output_directory.is_dir():
        raise FileNotFoundError("Task41 V4 geometry-pair output directory was not prepared")
    import shutil

    free_bytes = int(shutil.disk_usage(output_directory).free)
    if free_bytes < 2 * 1024**3:
        raise OSError("Task41 V4 geometry-pair output is below the unchanged 2 GiB free-space floor")

    progress({"phase": "geometry_pair_mesh_space", "status": "STARTED", "degree": 6})
    plan = _stage4_axis_plan(cfg, MPI.COMM_SELF.size)
    mesh = _structured_hexa_mesh(
        MPI.COMM_SELF,
        plan.x_values,
        plan.y_values,
        plan.z_values,
        preserve_input_partition=cfg.stage4_preserve_structured_input_partition,
    )
    cell_tags = _mark_cells(mesh, cfg)
    space = fem.functionspace(mesh, element("N1curl", mesh.basix_cell(), 6, dtype=default_real_type))
    progress({
        "phase": "geometry_pair_mesh_space",
        "status": "COMPLETED",
        "owned_cells": int(mesh.topology.index_map(mesh.topology.dim).size_local),
        "global_dofs": int(space.dofmap.index_map.size_global),
    })

    trial, test = ufl.TrialFunction(space), ufl.TestFunction(space)
    dx = ufl.Measure("dx", domain=mesh, subdomain_data=cell_tags)
    curl_form, mass_form = _build_physical_volume_terms(cfg, trial, test, dx)
    jit_options = dict(SAME_MESH_JIT_OPTIONS)
    combined_form = fem.form(curl_form + mass_form, jit_options=jit_options)
    source_function = fem.Function(space)
    split_forms = (
        fem.form(ufl.action(curl_form, source_function), jit_options=jit_options),
        fem.form(ufl.action(mass_form, source_function), jit_options=jit_options),
    )
    kernel_identities = {
        "fresh_combined_volume": _compiled_kernel_identity(
            combined_form, rank=2, label="combined_curl_plus_mass", sha256_file=sha256_file
        ),
        "native_split_curl_action": _compiled_kernel_identity(
            split_forms[0], rank=1, label="split_curl_ufl_action", sha256_file=sha256_file
        ),
        "native_split_mass_action": _compiled_kernel_identity(
            split_forms[1], rank=1, label="split_mass_ufl_action", sha256_file=sha256_file
        ),
        "relationship": "Fresh blocks are combined rank-2 FFCx; saved native actions are split rank-1 FFCx. The signatures and arithmetic paths are kept distinct.",
    }

    dimension = int(space.element.space_dimension)
    interior_count = len(space.element.basix_element.entity_dofs[mesh.topology.dim][0])
    geometry_node_count = int(np.asarray(mesh.geometry.dofmap).shape[1])
    block_bytes = 2 * len(selected_cells) * dimension * dimension * np.dtype(np.complex128).itemsize
    geometry_and_dof_bytes = len(selected_cells) * (
        2 * geometry_node_count * 3 * np.dtype(np.float64).itemsize
        + geometry_node_count * np.dtype(np.int32).itemsize
        + dimension * np.dtype(np.int32).itemsize
        + dimension * np.dtype(np.int64).itemsize
    )
    selected_vector_bytes = (
        2 * 2 * 2 * len(selected_cells) * interior_count * np.dtype(np.complex128).itemsize
    )
    projected_evidence_bytes = int(
        block_bytes + geometry_and_dof_bytes + selected_vector_bytes + 1024**2
    )
    pair_workspace_bytes = int(
        2 * len(selected_cells) * 2 * dimension * dimension * np.dtype(np.complex128).itemsize
        + projected_evidence_bytes
        + 32 * 1024**2
    )
    if prior_bytes + projected_evidence_bytes > 16 * 1024**3:
        raise MemoryError("Task41 V4 geometry-pair evidence would exceed the unchanged 16 GiB cap")
    if free_bytes - projected_evidence_bytes < 2 * 1024**3:
        raise OSError(
            "Task41 V4 geometry-pair output would breach the unchanged 2 GiB free-space floor"
        )
    allocation_gate(
        "geometry_pair_blocks_and_selected_row_vectors",
        {
            "additional_payload_bytes": projected_evidence_bytes,
            "workspace_bytes": pair_workspace_bytes,
            "selected_cells": list(selected_cells),
            "coordinate_paths": 2,
            "block_artifacts_only": ["K", "G", "J", "L"],
        },
    )
    cell_pairs: dict[int, dict[str, Any]] = {}
    saved_maps: dict[int, dict[str, np.ndarray]] = {}
    saved_classes: dict[int, Mapping[str, np.ndarray] | None] = {}
    cell_records = []
    for cell_index in selected_cells:
        progress({"phase": "geometry_pair_cell", "status": "STARTED", "cell_index": cell_index})
        pair = tabulate_volume_audit_cell_geometry_pair(combined_form, space, cell_tags, cell_index)
        if pair["actual_geometry_coordinates"].shape != (8, 3):
            raise ValueError(f"selected cell {cell_index} does not have the expected eight actual geometry nodes")
        if tuple(pair["class_key"]) not in class_keys:
            raise ValueError(f"fresh cell class/permutation identity is absent from the frozen V4 receipt: {cell_index}")
        prefix = f"task41_v4_volume_cell_{cell_index}"
        cell_map = {
            name: _load_bound_report_array(source_root, records, f"{prefix}_{name}", sha256_file=sha256_file)
            for name in (
                "interior_original_rows", "trace_original_rows", "active_ids",
                "trace_expansion_data", "trace_expansion_indices", "trace_expansion_indptr",
            )
        }
        if not (
            np.array_equal(pair["interior_original_dofs"], cell_map["interior_original_rows"])
            and np.array_equal(pair["trace_original_dofs"], cell_map["trace_original_rows"])
        ):
            raise ValueError(f"fresh p6 cell dofmap differs from saved V4 rows for cell {cell_index}")
        if cell_map["active_ids"].size == 0 or np.any(cell_map["active_ids"] < 0):
            raise ValueError(f"saved V4 active map is invalid for cell {cell_index}")
        saved_maps[cell_index] = cell_map
        cell_pairs[cell_index] = pair

        class_ids = sorted({
            name[len("task41_v4_volume_class_"):-2]
            for name in records
            if name.startswith("task41_v4_volume_class_") and name.endswith("_K")
        })
        class_data = {}
        for class_id in class_ids:
            candidate = {
                name: _load_bound_report_array(
                    source_root, records, f"task41_v4_volume_class_{class_id}_{name}", sha256_file=sha256_file
                )
                for name in ("K", "G", "J", "L", "T", "S")
            }
            if all(np.array_equal(pair["canonical"][name], candidate[name]) for name in ("K", "G", "J", "L")):
                class_data[class_id] = candidate
        if len(class_data) > 1:
            raise ValueError(f"saved canonical class blocks are ambiguous for cell {cell_index}")
        saved_class_id, saved_class = next(iter(class_data.items())) if class_data else (None, None)
        saved_classes[cell_index] = saved_class

        artifacts = {}
        for name, value in (
            ("geometry_dofs", pair["geometry_dofs"]),
            ("actual_geometry_coordinates", pair["actual_geometry_coordinates"]),
            ("canonical_geometry_coordinates", pair["canonical_geometry_coordinates"]),
            ("local_dofs", pair["local_dofs"]),
            ("original_dofs", pair["original_dofs"]),
        ):
            artifacts[name] = persist_array(f"cell{cell_index}_{name}", value)
        block_artifacts = {
            path_name: {
                name: persist_array(f"cell{cell_index}_{path_name}_{name}", pair[path_name][name])
                for name in ("K", "G", "J", "L")
            }
            for path_name in ("actual", "canonical")
        }
        cell_records.append({
            "cell_index": cell_index,
            "cell_tag": int(pair["cell_tag"]),
            "class_key": [int(pair["class_key"][0]), *[float(v) for v in pair["class_key"][1:4]], int(pair["class_key"][4])],
            "cell_permutation": int(pair["cell_permutation"]),
            "dofmap_identity_passed": True,
            "saved_class_key_listed": True,
            "saved_canonical_class_id": saved_class_id,
            "saved_map_artifacts": {name: dict(records[f"{prefix}_{name}"]) for name in cell_map},
            "geometry_and_dof_artifacts": artifacts,
            "block_artifacts": block_artifacts,
            "integral_kernel_counts": pair["integral_kernel_counts"],
        })
        progress({"phase": "geometry_pair_cell", "status": "COMPLETED", "cell_index": cell_index})

    columns = donor["columns"]
    for column in columns:
        for name in list(column):
            if name not in {"active_original_rows", "known_field", "states"}:
                del column[name]
        for state in column["states"]:
            for name in list(state):
                if name not in {"storage", "native_volume_action"}:
                    del state[name]
    donor.pop("raw_classes", None)
    donor.pop("cell_maps", None)
    donor.pop("attribution", None)

    saved_d_volume = [
        _load_bound_report_array(source_root, records, f"task41_v4_d_volume_trace_col{col}", sha256_file=sha256_file)
        for col in range(2)
    ]
    saved_reduce = {
        (col, state): _load_bound_report_array(
            source_root, records, f"task41_v4_reduce_r_volume_{state}_col{col}", sha256_file=sha256_file
        )
        for col in range(2) for state in ("j0", "j3")
    }
    denominators = [float(item["saved_original_denom"]) for item in source_report["identity_audit"]["columns"]]
    attribution = audit_task41_v4_geometry_pair_attribution(
        cell_pairs=cell_pairs,
        saved_maps=saved_maps,
        columns=columns,
        saved_classes=saved_classes,
        saved_d_volume=saved_d_volume,
        saved_reduce_r_volume=saved_reduce,
        original_denominators=denominators,
        target_active_row=TASK41_P0_V4_SELECTED_ACTIVE_ROW,
        target_original_row=TASK41_P0_V4_SELECTED_ORIGINAL_ROW,
    )
    attribution_artifacts = {
        name: persist_array(name, values)
        for name, values in attribution.pop("delta_i_arrays").items()
    }
    return {
        "schema": "task41.p0.v4.geometry_pair_probe.v1",
        "source_report_path": str(source_report_path),
        "source_report_sha256": expected_report_sha,
        "consumer_source_sha": consumer_contract.get("source", {}).get("sha"),
        "source_donor_manifest_sha256": donor.get("manifest_sha256"),
        "prior_evidence_bytes": prior_bytes,
        "projected_new_evidence_bytes": projected_evidence_bytes,
        "unchanged_evidence_cap_bytes": 16 * 1024**3,
        "selected_active_row": TASK41_P0_V4_SELECTED_ACTIVE_ROW,
        "selected_original_row": TASK41_P0_V4_SELECTED_ORIGINAL_ROW,
        "selected_cells": cell_records,
        "ffcx_kernel_identities": kernel_identities,
        "attribution": attribution["attribution"],
        "delta_i_artifacts": attribution_artifacts,
        "scope_note": "Two-cell selected-row diagnostic only. Its global-denominator-scaled residual is not the whole-column 1e-11 gate. Actual-vs-canonical uses one combined rank-2 form; saved native actions use two separately compiled rank-1 forms.",
    }

def main(argv: list[str] | None = None) -> int:
    started_perf = perf_counter()
    started_at_utc = datetime.now(timezone.utc).isoformat()
    args = _parse_args(argv)
    if args.geometry_pair_only != (args.source_report is not None):
        raise ValueError("--geometry-pair-only and --source-report must be provided together")
    if args.geometry_pair_only and args.geometry_policy != "canonical":
        raise ValueError("the selected-cell geometry-pair diagnostic remains canonical-only")
    if args.geometry_policy == "mesh_actual_exact" and args.geometry_reference_report is None:
        raise ValueError("mesh_actual_exact requires the frozen two-cell V4 geometry reference report")
    if args.geometry_policy != "mesh_actual_exact" and args.geometry_reference_report is not None:
        raise ValueError("V4 canonical paths cannot consume the V5 exact-geometry reference")
    from src.runners.task40_v20_stage_runner import _resource_snapshot
    from src.io.input_validation import simulation_config_3d_from_normalized
    from src.runners.task41_p0_checker import load_task41_v4_volume_only_donor
    from src.runners.task41_p0_contract import require_task41_p0_contract, sha256_file
    from src.solvers.task40_v22_operator_probe import _resource_admission
    from src.solvers.task41_v4_volume_only_audit import (
        TASK41_V5_ATTRIBUTION_ACCUMULATOR_COUNT,
        Task41V5VolumeAttributionAccumulator,
        audit_task41_v4_volume_identity,
        build_task41_v4_volume_only_owner,
    )

    donor_contract, donor_digest = require_task41_p0_contract(
        args.donor_contract,
        expected_sha256=args.donor_contract_sha256,
        current_root=ROOT,
        check_current_source=False,
        require_clean_source=False,
    )
    consumer_contract, consumer_digest = require_task41_p0_contract(
        args.consumer_contract,
        expected_sha256=args.consumer_contract_sha256,
        current_root=ROOT,
        check_current_source=True,
        require_clean_source=True,
    )
    fixed_window = None
    initial_fixed_window_state = None
    postbuild_reserve_evidence: dict[str, Any] | None = None
    if args.geometry_policy == "mesh_actual_exact":
        from src.runners.task41_p0_contract import load_task41_p0_fixed_window
        from src.runners.task40_v10_campaign import read_campaign_state

        fixed_window = load_task41_p0_fixed_window(
            consumer_contract,
            current_root=ROOT,
        )
        initial_fixed_window_state = read_campaign_state(
            fixed_window,
            phase="numeric",
        )
        v4_receipt_path = (
            ROOT
            / "docs/task41extra_phi90_p50x50_g17x20/outcomes/"
            / "b0_v4_volume_only_attribution_20261020.json"
        )
        v4_receipt = json.loads(v4_receipt_path.read_text(encoding="utf-8"))
        v4_identity = v4_receipt.get("identity", {})
        v4_extraction = v4_receipt.get("volume_only_extraction", {})
        if (
            v4_identity.get("campaign_window_sha256") != fixed_window.sha256
            or v4_extraction.get("status") != "COMPLETED"
        ):
            raise ValueError("V5 post-build reserve lacks a completed V4 receipt on the same fixed window")
        postbuild_parent_seconds = float(v4_extraction["service_parent_seconds"])
        if not math.isfinite(postbuild_parent_seconds) or postbuild_parent_seconds <= 0.0:
            raise ValueError("V4 measured post-build service time is not finite and positive")
        postbuild_reserve_evidence = {
            "path": str(v4_receipt_path),
            "sha256": sha256_file(v4_receipt_path),
            "campaign_window_sha256": fixed_window.sha256,
            "measured_service_parent_seconds": postbuild_parent_seconds,
            "measured_worker_seconds": float(v4_extraction["worker_elapsed_seconds"]),
            "required_checker_watchdog_seconds": (
                _v4_required_checker_watchdog_elapsed_seconds(v4_extraction)
            ),
            "safety_factor": TASK41_P0_V5_POSTBUILD_SAFETY_FACTOR,
        }
    donor_case = donor_contract.get("case", {})
    consumer_case = consumer_contract.get("case", {})
    for key in (
        "model_id",
        "method",
        "mpi_size",
        "input_sha256",
        "physical_model_sha256",
        "resolved_config_sha256",
        "run_id",
    ):
        if donor_case.get(key) != consumer_case.get(key):
            raise ValueError(f"Task41 V4 donor/consumer case identity differs at {key}")
    if args.summary.resolve(strict=True).parent != args.numerical_output.resolve().parent:
        raise ValueError("Task41 V4 summary and numerical-output roots differ")
    run_root = args.summary.resolve(strict=True).parent
    config_path = run_root / "resolved_config.json"
    if sha256_file(config_path) != donor_case.get("resolved_config_sha256"):
        raise ValueError("Task41 V4 resolved configuration differs from its frozen producer contract")
    resolved = json.loads(config_path.read_text(encoding="utf-8"))
    cfg = simulation_config_3d_from_normalized(resolved)
    output_root = args.output_dir.resolve(strict=True)
    output_directory = output_root / (
        "geometry_pair"
        if args.geometry_pair_only
        else "mesh_actual_exact"
        if args.geometry_policy == "mesh_actual_exact"
        else "volume_only"
    )
    output_directory.mkdir(parents=True, exist_ok=False)
    report_path = output_root / (
        "task41_p0_v4_geometry_pair_probe.json"
        if args.geometry_pair_only
        else "task41_p0_v5_mesh_actual_exact_attribution.json"
        if args.geometry_policy == "mesh_actual_exact"
        else "task41_p0_v4_volume_only_attribution.json"
    )
    if report_path.exists():
        raise FileExistsError(f"Task41 V4 attribution report already exists: {report_path}")
    phase_path = output_root / "task41_p0_v4_volume_only_phase.json"
    event_path = output_root / "task41_p0_v4_volume_only_events.jsonl"
    donor = load_task41_v4_volume_only_donor(
        summary_path=args.summary,
        numerical_output=args.numerical_output,
    )
    geometry_reference = (
        _load_v5_geometry_reference(
            args.geometry_reference_report,
            donor_manifest_sha256=str(donor["manifest_sha256"]),
            sha256_file=sha256_file,
        )
        if args.geometry_policy == "mesh_actual_exact"
        else None
    )
    run_record: dict[str, Any] = {
            "schema": (
            "task41.p0.v4.geometry_pair_probe_receipt.v1"
            if args.geometry_pair_only
                else "task41.p0.v5.mesh_actual_exact_attribution_receipt.v1"
                if args.geometry_policy == "mesh_actual_exact"
                else "task41.p0.v4.volume_only_attribution_receipt.v1"
        ),
        "status": "RUNNING",
        "geometry_policy": args.geometry_policy,
        "started_at_utc": started_at_utc,
        "worker_started_perf_counter": started_perf,
        "donor_contract_path": str(args.donor_contract.resolve()),
        "donor_contract_sha256": donor_digest,
        "donor_source_sha": donor_contract.get("source", {}).get("sha"),
        "consumer_contract_path": str(args.consumer_contract.resolve()),
        "consumer_contract_sha256": consumer_digest,
        "consumer_source_sha": consumer_contract.get("source", {}).get("sha"),
        "resolved_config_sha256": donor_case.get("resolved_config_sha256"),
        "donor_manifest_sha256": donor.get("manifest_sha256"),
        "output_directory": str(output_root),
        "volume_evidence_directory": str(output_directory),
        "source_report_path": (
            str(args.source_report.resolve()) if args.source_report is not None else None
        ),
        "geometry_reference_report_path": (
            geometry_reference["path"] if geometry_reference is not None else None
        ),
        "geometry_reference_report_sha256": (
            geometry_reference["sha256"] if geometry_reference is not None else None
        ),
        "phase_path": str(phase_path),
        "event_log_path": str(event_path),
        "preparation_elapsed_seconds": perf_counter() - started_perf,
        "initial_fixed_window_state": initial_fixed_window_state,
        "postbuild_reserve_evidence": postbuild_reserve_evidence,
    }
    _write_json_atomic(report_path, run_record)
    phase_started: dict[tuple[str, Any], float] = {}

    def progress(event: Mapping[str, Any]) -> None:
        now = perf_counter()
        phase = str(event.get("phase", "unknown"))
        phase_key = (phase, event.get("column"))
        if event.get("status") == "STARTED" or phase_key not in phase_started:
            phase_started[phase_key] = now
        row = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "elapsed_since_worker_start_seconds": now - started_perf,
            "elapsed_in_phase_seconds": now - phase_started[phase_key],
            **dict(event),
        }
        with event_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        _write_json_atomic(phase_path, row)
        print(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False), flush=True)

    def persist_volume_array(name: str, array: np.ndarray) -> dict[str, Any]:
        array_bytes_upper = int(np.asarray(array).nbytes) + 4096
        cumulative_before = (
            int(donor.get("existing_evidence_bytes", 0))
            + int(run_record.get("candidate_admission_evidence_bytes", 0))
            + int(run_record.get("persisted_evidence_bytes", 0))
        )
        if cumulative_before + array_bytes_upper > 16 * 1024**3:
            raise MemoryError(
                "Task41 V5 evidence write would exceed the unchanged 16 GiB cap by "
                f"{cumulative_before + array_bytes_upper - 16 * 1024**3} bytes"
            )
        free_before = int(shutil.disk_usage(output_directory).free)
        if free_before - array_bytes_upper < 2 * 1024**3:
            raise OSError(
                "Task41 V5 evidence write would breach the 2 GiB free-space floor by "
                f"{2 * 1024**3 - (free_before - array_bytes_upper)} bytes"
            )
        artifact = _persist_array(
            output_directory, name, array, sha256_file=sha256_file
        )
        records = run_record.setdefault("persisted_evidence_arrays", [])
        records.append({"name": name, **artifact})
        run_record["persisted_evidence_bytes"] = sum(
            int(item["bytes"]) for item in records
        )
        _write_json_atomic(report_path, run_record)
        return artifact

    exact_attribution = (
        Task41V5VolumeAttributionAccumulator(donor)
        if args.geometry_policy == "mesh_actual_exact"
        else None
    )

    def allocation_gate(label: str, facts: Mapping[str, Any]) -> None:
        checked_facts = dict(facts)
        if args.geometry_policy == "mesh_actual_exact" and label in {
            "mesh_actual_exact_prefix_preflight",
            "mesh_actual_exact_full_admission",
        }:
            if label == "mesh_actual_exact_full_admission":
                active_rows = int(donor["manifest"]["active_trace_rows"])
                port_rows = int(donor["manifest"]["port_rows"])
                full_rows = int(donor["manifest"]["full_storage_rows"])
                candidate_rows = active_rows + port_rows
                candidate_array_bytes = (
                    2 * candidate_rows * 2 * np.dtype(np.complex128).itemsize
                )
                accumulator_bytes = (
                    TASK41_V5_ATTRIBUTION_ACCUMULATOR_COUNT
                    * active_rows
                    * np.dtype(np.complex128).itemsize
                )
                action_and_closure_workspace = (
                    np.dtype(np.complex128).itemsize
                    * (full_rows + 4 * (active_rows + 1))
                    + candidate_array_bytes
                    + 4 * active_rows * np.dtype(np.complex128).itemsize
                )
                expected_identity_evidence = (
                    26 * active_rows * np.dtype(np.complex128).itemsize
                    + 28 * 4096
                    + candidate_array_bytes
                    + 4 * full_rows * np.dtype(np.complex128).itemsize
                    + 4 * 4096
                )
                expected_evidence_total = (
                    int(donor.get("existing_evidence_bytes", 0))
                    + int(run_record.get("candidate_admission_evidence_bytes", 0))
                    + expected_identity_evidence
                )
                if expected_evidence_total > 16 * 1024**3:
                    raise _CandidateNotAdmitted(
                        "V5 selected output arrays exceed the unchanged 16 GiB evidence cap by "
                        f"{expected_evidence_total - 16 * 1024**3} bytes"
                    )
                checked_facts["additional_payload_bytes"] = int(
                    checked_facts.get("additional_payload_bytes", 0)
                ) + accumulator_bytes
                checked_facts["workspace_bytes"] = max(
                    int(checked_facts.get("workspace_bytes", 0)),
                    action_and_closure_workspace,
                )
                checked_facts["v5_postbuild_reserve"] = {
                    "candidate_rows_active_plus_port": candidate_rows,
                    "candidate_full_array_bytes": candidate_array_bytes,
                    "attribution_accumulator_bytes": accumulator_bytes,
                    "attribution_accumulators": TASK41_V5_ATTRIBUTION_ACCUMULATOR_COUNT,
                    "production_action_and_global_closure_workspace_bytes": action_and_closure_workspace,
                    "projected_identity_evidence_bytes": expected_identity_evidence,
                    "projected_evidence_total_bytes": expected_evidence_total,
                    "evidence_cap_bytes": 16 * 1024**3,
                    "free_space_floor_bytes": 2 * 1024**3,
                }
                verified = {
                    int(item["cell_index"]): item
                    for item in checked_facts.get("prefix_records", ())
                    if isinstance(item, Mapping)
                    and isinstance(item.get("reference_validation"), Mapping)
                }
                if set(verified) != set(TASK41_P0_V5_REFERENCE_CELLS) or any(
                    item["reference_validation"].get("coordinates_bitwise_equal") is not True
                    or item["reference_validation"].get("K_G_J_L_bitwise_equal") is not True
                    for item in verified.values()
                ):
                    raise ValueError(
                        "V5 exact prefix did not reproduce the frozen actual coordinates/K/G/J/L "
                        "for cells 26762 and 26897"
                    )
            key_inventory = checked_facts.pop("exact_key_inventory", None)
            artifact = None
            if key_inventory is not None:
                inventory_path = output_directory / "mesh_actual_exact_key_inventory.json"
                if inventory_path.exists():
                    raise FileExistsError(f"exact key inventory already exists: {inventory_path}")
                encoded = json.dumps(
                    {
                        "schema": "task41.p0.v5.mesh_actual_exact_key_inventory.v1",
                        "consumer_source_sha": consumer_contract.get("source", {}).get("sha"),
                        "campaign_window_sha256": fixed_window.sha256,
                        "form_identity": checked_facts.get("exact_form_identity"),
                        "geometry_material_identity_by_tag": checked_facts.get(
                            "geometry_material_identity_by_tag"
                        ),
                        "keys": key_inventory,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    indent=2,
                    allow_nan=False,
                ) + "\n"
                payload_size = len(encoded.encode("utf-8"))
                current_bytes = int(donor.get("existing_evidence_bytes", 0)) + int(
                    run_record.get("candidate_admission_evidence_bytes", 0)
                )
                free_bytes = int(shutil.disk_usage(output_directory).free)
                if current_bytes + payload_size > 16 * 1024**3:
                    raise _CandidateNotAdmitted(
                        f"exact key inventory would exceed the unchanged 16 GiB evidence cap by "
                        f"{current_bytes + payload_size - 16 * 1024**3} bytes"
                    )
                if free_bytes - payload_size < 2 * 1024**3:
                    raise _CandidateNotAdmitted(
                        f"exact key inventory would breach the 2 GiB free-space floor by "
                        f"{2 * 1024**3 - (free_bytes - payload_size)} bytes"
                    )
                _write_json_atomic(inventory_path, json.loads(encoded))
                artifact = {
                    "path": str(inventory_path.resolve()),
                    "sha256": sha256_file(inventory_path),
                    "bytes": int(inventory_path.stat().st_size),
                    "key_count": len(key_inventory),
                }
                run_record["candidate_key_inventory"] = artifact
                run_record["candidate_key_inventory_bytes"] = artifact["bytes"]
                run_record["candidate_admission_evidence_bytes"] = int(
                    run_record.get("candidate_admission_evidence_bytes", 0)
                ) + int(artifact["bytes"])
            if label == "mesh_actual_exact_full_admission":
                measurement_path = output_directory / "mesh_actual_exact_prefix_measurement.json"
                if measurement_path.exists():
                    raise FileExistsError(f"exact prefix measurement already exists: {measurement_path}")
                measurement_size_upper = len(
                    json.dumps(
                        {"schema": "task41.p0.v5.mesh_actual_exact_prefix_measurement.v1", "facts": checked_facts},
                        ensure_ascii=False,
                        sort_keys=True,
                        indent=2,
                        allow_nan=False,
                    ).encode("utf-8")
                ) + 512
                current_bytes = int(donor.get("existing_evidence_bytes", 0)) + int(
                    run_record.get("candidate_admission_evidence_bytes", 0)
                )
                free_bytes = int(shutil.disk_usage(output_directory).free)
                if current_bytes + measurement_size_upper > 16 * 1024**3:
                    raise _CandidateNotAdmitted(
                        f"prefix measurement would exceed the unchanged 16 GiB evidence cap by "
                        f"{current_bytes + measurement_size_upper - 16 * 1024**3} bytes"
                    )
                if free_bytes - measurement_size_upper < 2 * 1024**3:
                    raise _CandidateNotAdmitted(
                        f"prefix measurement would breach the 2 GiB free-space floor by "
                        f"{2 * 1024**3 - (free_bytes - measurement_size_upper)} bytes"
                    )
                measurement_payload = {
                    "schema": "task41.p0.v5.mesh_actual_exact_prefix_measurement.v1",
                    "campaign_window_sha256": fixed_window.sha256,
                    "facts": checked_facts,
                }
                _write_json_atomic(measurement_path, measurement_payload)
                run_record["candidate_prefix_measurement"] = {
                    "path": str(measurement_path.resolve()),
                    "sha256": sha256_file(measurement_path),
                    "bytes": int(measurement_path.stat().st_size),
                    "measured_misses": int(
                        checked_facts.get("measured_prefix_cache_misses", 0)
                    ),
                }
                run_record["candidate_prefix_measurement_bytes"] = int(
                    measurement_path.stat().st_size
                )
                run_record["candidate_admission_evidence_bytes"] = int(
                    run_record.get("candidate_admission_evidence_bytes", 0)
                ) + int(measurement_path.stat().st_size)
            gate_record = {
                "gate": label,
                "status": "INPUTS_RECORDED_BEFORE_ADMISSION",
                "key_inventory_artifact": artifact,
            }
            if label == "mesh_actual_exact_prefix_preflight":
                gate_record["facts"] = checked_facts
            else:
                gate_record["facts_artifact"] = run_record.get(
                    "candidate_prefix_measurement"
                )
                gate_record["facts_summary"] = {
                    "raw_key_count": checked_facts.get("raw_key_count"),
                    "oriented_key_count": checked_facts.get("oriented_key_count"),
                    "measured_prefix_cache_misses": checked_facts.get(
                        "measured_prefix_cache_misses"
                    ),
                    "projected_remaining_class_build_seconds_upper": checked_facts.get(
                        "projected_remaining_class_build_seconds_upper"
                    ),
                }
            run_record.setdefault("candidate_admission_gates", []).append(gate_record)
            _write_json_atomic(report_path, run_record)
            progress(
                {
                    "phase": "mesh_actual_exact_gate_evidence",
                    "status": "INPUTS_RECORDED_BEFORE_ADMISSION",
                    **gate_record,
                }
            )
        if args.geometry_policy == "mesh_actual_exact":
            assert fixed_window is not None
            from src.runners.task40_v10_campaign import read_campaign_state

            from src.runners.workflow_timebase import TimebaseInconsistency

            try:
                state = read_campaign_state(fixed_window, phase="numeric")
            except TimebaseInconsistency as exc:
                admission = {
                    "status": "CANDIDATE_NOT_ADMITTED",
                    "reason": f"fixed-window balance could not be verified: {type(exc).__name__}: {exc}",
                    "gate": label,
                    "facts": checked_facts,
                }
                run_record["candidate_admission"] = admission
                progress(
                    {
                        "phase": "mesh_actual_exact_candidate_admission",
                        "status": "CANDIDATE_NOT_ADMITTED",
                        **admission,
                    }
                )
                raise _CandidateNotAdmitted(admission["reason"]) from exc
            remaining = float(state["remaining_phase_seconds"])
            postbuild_reserve = math.ceil(
                float(postbuild_reserve_evidence["measured_service_parent_seconds"])
                * TASK41_P0_V5_POSTBUILD_SAFETY_FACTOR
            )
            if label == "mesh_actual_exact_prefix_preflight":
                estimated_required = (
                    TASK41_P0_V5_PREFIX_MINIMUM_SECONDS
                    + TASK41_P0_V5_TERMINATION_RESERVE_SECONDS
                )
            elif label == "mesh_actual_exact_full_admission":
                estimated_required = (
                    float(facts["projected_remaining_class_build_seconds_upper"])
                    + postbuild_reserve
                    + TASK41_P0_V5_TERMINATION_RESERVE_SECONDS
                )
            else:
                estimated_required = 0.0
            checked_facts["fixed_window_admission"] = {
                "campaign_window_sha256": fixed_window.sha256,
                "remaining_numeric_seconds": remaining,
                "estimated_required_seconds": estimated_required,
                "postbuild_two_column_action_write_checker_reserve_seconds": postbuild_reserve,
                "termination_reserve_seconds": (
                    TASK41_P0_V5_TERMINATION_RESERVE_SECONDS
                    if label == "mesh_actual_exact_full_admission"
                    else 0.0
                ),
                "source_of_postbuild_reserve": postbuild_reserve_evidence,
                "read_only_live_campaign_state": state,
            }
            if label in {"mesh_actual_exact_prefix_preflight", "mesh_actual_exact_full_admission"}:
                gate_rows = run_record.get("candidate_admission_gates", [])
                if gate_rows and gate_rows[-1].get("gate") == label:
                    gate_rows[-1]["fixed_window_admission"] = checked_facts[
                        "fixed_window_admission"
                    ]
                if label == "mesh_actual_exact_full_admission":
                    measurement_path = output_directory / "mesh_actual_exact_prefix_measurement.json"
                    _write_json_atomic(
                        measurement_path,
                        {
                            "schema": "task41.p0.v5.mesh_actual_exact_prefix_measurement.v1",
                            "campaign_window_sha256": fixed_window.sha256,
                            "facts": checked_facts,
                        },
                    )
                    run_record["candidate_prefix_measurement"].update(
                        {
                            "sha256": sha256_file(measurement_path),
                            "bytes": int(measurement_path.stat().st_size),
                        }
                    )
                    gate_rows[-1]["measurement_artifact"] = dict(
                        run_record["candidate_prefix_measurement"]
                    )
                _write_json_atomic(report_path, run_record)
                progress(
                    {
                        "phase": "mesh_actual_exact_gate_evidence",
                        "status": "LIVE_WINDOW_BALANCE_RECORDED",
                        "gate": label,
                        "fixed_window_admission": checked_facts["fixed_window_admission"],
                    }
                )
            if estimated_required > remaining:
                admission = {
                    "status": "CANDIDATE_NOT_ADMITTED",
                    "reason": "fixed-window numeric balance is below conservative remaining-work estimate",
                    "gate": label,
                    "facts": checked_facts,
                    "time_deficit_seconds": estimated_required - remaining,
                }
                run_record["candidate_admission"] = admission
                progress(
                    {
                        "phase": "mesh_actual_exact_candidate_admission",
                        "status": "CANDIDATE_NOT_ADMITTED",
                        **admission,
                    }
                )
                raise _CandidateNotAdmitted(
                    f"{label}: fixed-window deficit {estimated_required - remaining:.3f}s; "
                    f"N={facts.get('oriented_key_count')}, "
                    f"working_set={facts.get('projected_condensation_and_key_bytes_upper')} bytes"
                )
        from src.solvers.task40_v22_operator_probe import _ProbeResourceBlocked

        try:
            _checked_allocation_gate(
                label,
                checked_facts,
                resource_admission=_resource_admission,
                resource_snapshot=_resource_snapshot,
                resources=consumer_contract["resources"],
                progress=progress,
            )
        except _ProbeResourceBlocked as exc:
            if args.geometry_policy != "mesh_actual_exact" or label not in {
                "mesh_actual_exact_prefix_preflight",
                "mesh_actual_exact_full_admission",
            }:
                raise
            admission = {
                "status": "CANDIDATE_NOT_ADMITTED",
                "reason": f"resource admission rejected the exact candidate: {exc}",
                "gate": label,
                "facts": checked_facts,
                "resource_block": getattr(exc, "facts", None),
            }
            run_record["candidate_admission"] = admission
            progress(
                {
                    "phase": "mesh_actual_exact_candidate_admission",
                    "status": "CANDIDATE_NOT_ADMITTED",
                    **admission,
                }
            )
            raise _CandidateNotAdmitted(
                f"{label}: {type(exc).__name__}; N={facts.get('oriented_key_count')}, "
                f"projected_retained={facts.get('projected_retained_numeric_bytes_upper')} bytes"
            ) from exc
        if (
            args.geometry_policy == "mesh_actual_exact"
            and label == "mesh_actual_exact_full_admission"
        ):
            assert exact_attribution is not None
            exact_attribution.admit(int(donor["manifest"]["active_trace_rows"]))

    owner_result = None
    native_volume_action = None
    try:
        if args.geometry_pair_only:
            probe = _run_geometry_pair_probe(
                cfg=cfg,
                donor=donor,
                source_report_path=args.source_report,
                consumer_contract=consumer_contract,
                output_directory=output_directory,
                persist_array=persist_volume_array,
                allocation_gate=allocation_gate,
                progress=progress,
                sha256_file=sha256_file,
            )
            actual_cumulative_bytes = int(probe["prior_evidence_bytes"]) + int(
                run_record.get("persisted_evidence_bytes", 0)
            )
            if actual_cumulative_bytes > 16 * 1024**3:
                raise MemoryError("Task41 V4 geometry-pair output exceeded the unchanged 16 GiB cap")
            run_record.update(
                {
                    "status": "COMPLETED_GEOMETRY_PAIR_PROBE",
                    "completed_at_utc": datetime.now(timezone.utc).isoformat(),
                    "elapsed_since_worker_start_seconds": perf_counter() - started_perf,
                    "geometry_pair_probe": probe,
                    "evidence_cap_bytes": 16 * 1024**3,
                    "free_space_floor_bytes": 2 * 1024**3,
                }
            )
            _write_json_atomic(report_path, run_record)
            progress({"phase": "v4_geometry_pair_probe", "status": "COMPLETED"})
            return 0
        donor["prior_new_evidence_bytes"] = int(
            run_record.get("candidate_admission_evidence_bytes", 0)
        )

        def validate_exact_prefix_cell(
            cell_index: int,
            coordinates: np.ndarray,
            blocks: Mapping[str, np.ndarray],
        ) -> Mapping[str, Any]:
            if geometry_reference is None or cell_index not in geometry_reference["cells"]:
                return {}
            reference = geometry_reference["cells"][cell_index]
            coordinates_equal = np.array_equal(
                np.asarray(coordinates, dtype=np.float64), reference["coordinates"]
            )
            block_equal = all(
                np.array_equal(np.asarray(blocks[name]), reference["blocks"][name])
                for name in ("K", "G", "J", "L")
            )
            if not coordinates_equal or not block_equal:
                mismatches = [
                    name
                    for name in ("K", "G", "J", "L")
                    if not np.array_equal(np.asarray(blocks[name]), reference["blocks"][name])
                ]
                raise ValueError(
                    f"V5 exact prefix differs from frozen V4 actual evidence for cell {cell_index}: "
                    f"coordinates_equal={coordinates_equal}, block_mismatches={mismatches}"
                )
            return {
                "cell_index": int(cell_index),
                "reference_report_sha256": geometry_reference["sha256"],
                "coordinates_bitwise_equal": True,
                "coordinates_sha256": reference["coordinates_sha256"],
                "K_G_J_L_bitwise_equal": True,
                "block_sha256": dict(reference["block_sha256"]),
            }

        owner_result = build_task41_v4_volume_only_owner(
            cfg,
            donor,
            output_directory,
            allocation_gate=allocation_gate,
            progress_callback=progress,
            persist_array=persist_volume_array,
            geometry_policy=args.geometry_policy,
            required_prefix_cells=(
                TASK41_P0_V5_REFERENCE_CELLS
                if args.geometry_policy == "mesh_actual_exact"
                else ()
            ),
            prefix_cell_validator=(
                validate_exact_prefix_cell
                if args.geometry_policy == "mesh_actual_exact"
                else None
            ),
            exact_cell_observer=(
                exact_attribution.observe
                if exact_attribution is not None
                else None
            ),
        )
        donor["prior_new_evidence_bytes"] += int(
            owner_result["audit"]["evidence_bytes_added"]
        )
        donor["attribution"]["local_class_identities"] = owner_result["audit"]["local_class_identities"]
        native_volume_apply = None
        if args.geometry_policy == "mesh_actual_exact":
            from mpi4py import MPI
            from petsc4py import PETSc
            from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
                _build_split_volume_action,
            )
            from src.solvers.fullspace_same_mesh_hcurl_pmg_setup import (
                SAME_MESH_JIT_OPTIONS,
            )

            levels = owner_result["levels"]
            full_rows = int(owner_result["condensed"].full_rows)
            allocation_gate(
                "v5_candidate_recovery_native_action_preflight",
                {
                    "additional_payload_bytes": 0,
                    "workspace_bytes": 3 * full_rows * np.dtype(np.complex128).itemsize,
                    "native_volume_action_calls": 2,
                    "candidate_recovery_vectors": 2,
                    "port_or_surface_action": False,
                },
            )
            progress(
                {
                    "phase": "v5_candidate_recovery_native_action_build",
                    "status": "STARTED",
                    "action": "existing split volume-only form action",
                }
            )
            native_volume_action = _build_split_volume_action(
                levels["mesh_data"],
                cfg,
                levels["spaces"][6],
                levels["floquets"][6],
                jit_options=dict(SAME_MESH_JIT_OPTIONS),
            )
            native_apply_count = 0

            def native_volume_apply(values: np.ndarray) -> np.ndarray:
                nonlocal native_apply_count
                if native_apply_count >= 2:
                    raise RuntimeError("V5 recovery exceeded its two native volume-only action calls")
                source_values = np.asarray(values, dtype=np.complex128)
                if source_values.shape != (full_rows,) or not np.isfinite(source_values).all():
                    raise ValueError("V5 candidate recovery storage has an invalid full-space layout")
                source = PETSc.Vec().createWithArray(source_values, comm=MPI.COMM_SELF)
                try:
                    result = native_volume_action.apply(source)
                    # The split action owns and reuses its returned work Vec; copy
                    # the values and keep that Vec alive for the next column.
                    output = np.array(
                        result.getArray(readonly=True), dtype=np.complex128, copy=True
                    )
                finally:
                    source.destroy()
                native_apply_count += 1
                return output

            progress(
                {
                    "phase": "v5_candidate_recovery_native_action_build",
                    "status": "COMPLETED",
                }
            )
        identity_report = audit_task41_v4_volume_identity(
            owner_result["condensed"],
            donor,
            allocation_gate=allocation_gate,
            progress_callback=progress,
            persist_array=persist_volume_array,
            output_directory=output_directory,
            native_volume_apply=native_volume_apply,
        )
        if exact_attribution is not None:
            array_records = {
                str(item["name"]): item
                for item in run_record.get("persisted_evidence_arrays", ())
                if isinstance(item, Mapping) and item.get("name")
            }
            p6_record = array_records.get("task41_p0_v5_candidate_full_p6")
            reduced_record = array_records.get(
                "task41_p0_v5_candidate_full_reduced_rhs"
            )
            if p6_record is None or reduced_record is None:
                raise RuntimeError("V5 full-action arrays were not persisted before attribution")
            candidate_p6 = np.load(
                p6_record["path"], mmap_mode="r", allow_pickle=False
            )
            candidate_reduced = np.load(
                reduced_record["path"], mmap_mode="r", allow_pickle=False
            )
            identity_report["global_geometry_native_elimination_attribution"] = (
                exact_attribution.finalize(
                    candidate_p6,
                    candidate_reduced,
                    active_rows=owner_result["condensed"].active_rows,
                    persist_array=persist_volume_array,
                )
            )
            del candidate_p6, candidate_reduced
        candidate_gate = identity_report.get("candidate_full_action_gate")
        action_candidate_status = (
            str(candidate_gate.get("status"))
            if args.geometry_policy == "mesh_actual_exact" and candidate_gate is not None
            else None
        )
        recovery_gate = identity_report.get("candidate_recovery_gate")
        candidate_status = (
            "PASS"
            if args.geometry_policy == "mesh_actual_exact"
            and action_candidate_status == "PASS"
            and isinstance(recovery_gate, Mapping)
            and recovery_gate.get("status") == "PASS"
            else "ACTUAL_COORDINATES_INSUFFICIENT"
            if args.geometry_policy == "mesh_actual_exact"
            else None
        )
        if args.geometry_policy == "mesh_actual_exact" and candidate_status is None:
            raise RuntimeError("exact-geometry audit did not produce full-action and recovery gates")
        attribution_status = (
            identity_report.get("global_geometry_native_elimination_attribution", {}).get(
                "global_closure_status"
            )
            if args.geometry_policy == "mesh_actual_exact"
            else None
        )
        if args.geometry_policy == "mesh_actual_exact" and attribution_status is None:
            raise RuntimeError("exact-geometry audit did not produce the global attribution closure")
        if args.geometry_policy == "mesh_actual_exact":
            run_status = (
                "CANDIDATE_NUMERICAL_PASS_CHECKER_PENDING"
                if candidate_status == "PASS"
                else "ACTUAL_COORDINATES_INSUFFICIENT"
            )
            run_record["candidate_attribution_status"] = attribution_status
            run_record["independent_checker_status"] = "NOT_RUN"
            run_record["candidate_numeric_status"] = candidate_status
        else:
            run_status = "COMPLETED"
        run_record.update(
            {
                "status": run_status,
                "completed_at_utc": datetime.now(timezone.utc).isoformat(),
                "elapsed_since_worker_start_seconds": perf_counter() - started_perf,
                "owner_audit": owner_result["audit"],
                "identity_audit": identity_report,
                "evidence_cap_bytes": 16 * 1024**3,
                "free_space_floor_bytes": 2 * 1024**3,
            }
        )
        _write_json_atomic(report_path, run_record)
        progress(
            {
                "phase": (
                    "v5_mesh_actual_exact_full_action"
                    if args.geometry_policy == "mesh_actual_exact"
                    else "v4_volume_only_attribution"
                ),
                "status": (
                    "PASS_CHECKER_PENDING"
                    if candidate_status == "PASS"
                    else "ACTUAL_COORDINATES_INSUFFICIENT"
                    if candidate_status is not None
                    else "COMPLETED"
                ),
            }
        )
        # A complete exact-geometry report, including a numerical negative, is
        # worker-success evidence so the independent checker can run. The
        # service records scientific acceptance separately from audit completion.
        return 0
    except Exception as exc:
        if isinstance(exc, _CandidateNotAdmitted) and "candidate_admission" not in run_record:
            last_gate = (
                run_record.get("candidate_admission_gates", [])[-1]
                if run_record.get("candidate_admission_gates")
                else {}
            )
            run_record["candidate_admission"] = {
                "status": "CANDIDATE_NOT_ADMITTED",
                "reason": str(exc),
                "gate": last_gate.get("gate"),
                "gate_evidence": last_gate,
            }
        failure_status = (
            "CANDIDATE_NOT_ADMITTED"
            if isinstance(exc, _CandidateNotAdmitted)
            else
            "FAILED_GEOMETRY_PAIR_EVIDENCE_RETAINED"
            if args.geometry_pair_only
            else "FAILED_RAW_EVIDENCE_RETAINED"
        )
        run_record.update(
            {
                "status": failure_status,
                "failed_at_utc": datetime.now(timezone.utc).isoformat(),
                "elapsed_since_worker_start_seconds": perf_counter() - started_perf,
                "error": {"type": type(exc).__name__, "message": str(exc)},
            }
        )
        _write_json_atomic(report_path, run_record)
        progress(
            {
                "phase": (
                    "v4_geometry_pair_probe"
                    if args.geometry_pair_only
                    else "v4_volume_only_attribution"
                ),
                "status": "FAILED",
                "error": str(exc),
            }
        )
        return 3
    finally:
        if native_volume_action is not None:
            native_volume_action.destroy()
        if owner_result is not None:
            owner_result["condensed"].destroy()


if __name__ == "__main__":
    raise SystemExit(main())
