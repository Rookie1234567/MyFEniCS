"""Supervised Task41 V4 volume-only extraction and RHS attribution worker."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from time import perf_counter
from typing import Any, Mapping

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TASK41_P0_V4_SOURCE_REPORT_SHA256 = (
    "09e96eb8c9d52b4cf0c29570fd8df3c1f820bc208104d91edd102978dfc9c4d5"
)
TASK41_P0_V4_SELECTED_ACTIVE_ROW = 5_458_716
TASK41_P0_V4_SELECTED_ORIGINAL_ROW = 17_692_332


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
    parser.add_argument("--source-report", type=Path)
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
    from src.runners.task40_v20_stage_runner import _resource_snapshot
    from src.io.input_validation import simulation_config_3d_from_normalized
    from src.runners.task41_p0_checker import load_task41_v4_volume_only_donor
    from src.runners.task41_p0_contract import require_task41_p0_contract, sha256_file
    from src.solvers.task40_v22_operator_probe import _resource_admission
    from src.solvers.task41_v4_volume_only_audit import (
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
        "geometry_pair" if args.geometry_pair_only else "volume_only"
    )
    output_directory.mkdir(parents=True, exist_ok=False)
    report_path = output_root / (
        "task41_p0_v4_geometry_pair_probe.json"
        if args.geometry_pair_only
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
    run_record: dict[str, Any] = {
        "schema": (
            "task41.p0.v4.geometry_pair_probe_receipt.v1"
            if args.geometry_pair_only
            else "task41.p0.v4.volume_only_attribution_receipt.v1"
        ),
        "status": "RUNNING",
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
        "phase_path": str(phase_path),
        "event_log_path": str(event_path),
        "preparation_elapsed_seconds": perf_counter() - started_perf,
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

    def allocation_gate(label: str, facts: Mapping[str, Any]) -> None:
        _checked_allocation_gate(
            label,
            facts,
            resource_admission=_resource_admission,
            resource_snapshot=_resource_snapshot,
            resources=consumer_contract["resources"],
            progress=progress,
        )

    owner_result = None
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
        owner_result = build_task41_v4_volume_only_owner(
            cfg,
            donor,
            output_directory,
            allocation_gate=allocation_gate,
            progress_callback=progress,
            persist_array=persist_volume_array,
        )
        donor["prior_new_evidence_bytes"] = int(owner_result["audit"]["evidence_bytes_added"])
        donor["attribution"]["local_class_identities"] = owner_result["audit"]["local_class_identities"]
        identity_report = audit_task41_v4_volume_identity(
            owner_result["condensed"],
            donor,
            allocation_gate=allocation_gate,
            progress_callback=progress,
            persist_array=persist_volume_array,
            output_directory=output_directory,
        )
        run_record.update(
            {
                "status": "COMPLETED",
                "completed_at_utc": datetime.now(timezone.utc).isoformat(),
                "elapsed_since_worker_start_seconds": perf_counter() - started_perf,
                "owner_audit": owner_result["audit"],
                "identity_audit": identity_report,
                "evidence_cap_bytes": 16 * 1024**3,
                "free_space_floor_bytes": 2 * 1024**3,
            }
        )
        _write_json_atomic(report_path, run_record)
        progress({"phase": "v4_volume_only_attribution", "status": "COMPLETED"})
        return 0
    except Exception as exc:
        failure_status = (
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
        if owner_result is not None:
            owner_result["condensed"].destroy()


if __name__ == "__main__":
    raise SystemExit(main())
