"""Bounded, one-class-at-a-time V20 local and port component measurements."""

from __future__ import annotations

import gc
import hashlib
import json
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Mapping

import numpy as np


LOCAL_EQUATION_LIMIT = 1.0e-10
LOCAL_FORWARD_LIMIT = 1.0e-11
PORT_BATCH_MODES = 16
PORT_QUADRATURE_DEGREE = 60


def _array_owner(value: np.ndarray) -> np.ndarray:
    owner = np.asarray(value)
    while isinstance(owner.base, np.ndarray):
        owner = owner.base
    return owner


def _array_inventory(named_arrays: list[tuple[str, Any]]) -> dict[str, Any]:
    references = []
    unique: dict[int, dict[str, Any]] = {}
    alias_reference_bytes = 0
    for name, raw in named_arrays:
        if not isinstance(raw, np.ndarray):
            continue
        array = np.asarray(raw)
        owner = _array_owner(array)
        owner_id = id(owner)
        references.append({"name": name, "shape": list(array.shape), "bytes": int(array.nbytes)})
        if owner_id in unique:
            unique[owner_id]["alias_names"].append(name)
            alias_reference_bytes += int(array.nbytes)
        else:
            unique[owner_id] = {
                "owner_bytes": int(owner.nbytes),
                "owner_shape": list(owner.shape),
                "owner_dtype": str(owner.dtype),
                "names": [name],
                "alias_names": [],
            }
    return {
        "named_array_count": len(references),
        "named_array_payload_bytes_with_aliases": int(sum(row["bytes"] for row in references)),
        "unique_backing_count": len(unique),
        "unique_backing_bytes": int(sum(row["owner_bytes"] for row in unique.values())),
        "alias_reference_bytes": alias_reference_bytes,
        "named_arrays": references,
        "backings": list(unique.values()),
    }


def _array_sha256(value: np.ndarray) -> str:
    array = np.asarray(value)
    if not array.flags.c_contiguous:
        array = np.ascontiguousarray(array)
    digest = hashlib.sha256()
    digest.update(memoryview(array).cast("B"))
    return digest.hexdigest()


def _readback_component_packet(
    directory: Path, name: str, expected_array_hashes: Mapping[str, str]
) -> dict[str, Any]:
    from src.runners.physical_diagnosis_worker import _sha256_file

    stem = directory / name
    json_path = stem.with_suffix(".json")
    record = json.loads(json_path.read_text(encoding="utf-8"))
    manifest = record.get("arrays")
    descriptors = record.get("raw_arrays", {})
    if not isinstance(manifest, Mapping) or not isinstance(descriptors, Mapping):
        raise RuntimeError(f"V20 packet {name} omitted its NPZ array inventory")
    if set(descriptors) != set(expected_array_hashes):
        raise RuntimeError(f"V20 packet {name} scientific array descriptor inventory differs")
    array_key_to_name: dict[str, str] = {}
    for scientific_name in sorted(expected_array_hashes):
        descriptor = descriptors.get(scientific_name)
        array_key = descriptor.get("array_key") if isinstance(descriptor, Mapping) else None
        if not isinstance(array_key, str) or not array_key or array_key in array_key_to_name:
            raise RuntimeError(
                f"V20 packet {name} has a missing or repeated NPZ array key"
            )
        array_key_to_name[array_key] = scientific_name
    npz_path = Path(str(manifest.get("path", ""))).resolve()
    actual_sha256 = _sha256_file(npz_path)
    if actual_sha256 != manifest.get("sha256"):
        raise RuntimeError(f"V20 packet {name} failed its archive hash check")
    readback = {}
    with np.load(npz_path, allow_pickle=False) as archive:
        if (
            len(archive.files) != len(array_key_to_name)
            or set(archive.files) != set(array_key_to_name)
        ):
            raise RuntimeError(f"V20 packet {name} readback key inventory differs")
        for array_key in sorted(archive.files):
            scientific_name = array_key_to_name[array_key]
            array = archive[array_key]
            descriptor = descriptors[scientific_name]
            content_sha256 = _array_sha256(array)
            if (
                not isinstance(descriptor, Mapping)
                or descriptor.get("array_key") != array_key
                or descriptor.get("shape") != list(array.shape)
                or descriptor.get("dtype") != str(array.dtype)
                or content_sha256 != expected_array_hashes[scientific_name]
            ):
                raise RuntimeError(
                    f"V20 packet {name} failed readback for array {scientific_name}"
                )
            readback[scientific_name] = {
                "array_key": array_key,
                "shape": list(array.shape),
                "dtype": str(array.dtype),
                "sha256": content_sha256,
            }
            del array
    return {
        "json_path": str(json_path),
        "npz_path": str(npz_path),
        "npz_sha256": actual_sha256,
        "arrays": readback,
        "write_and_readback_hash_passed": True,
    }


def _save_component_packet(
    directory: Path, name: str, facts: Mapping[str, Any], arrays: Mapping[str, Any]
) -> dict[str, Any]:
    from src.runners.physical_diagnosis_worker import save_packet

    stem = directory / name
    if stem.with_suffix(".json").exists() or stem.with_suffix(".npz").exists():
        raise FileExistsError(f"V20 evidence packet already exists: {name}")
    array_hashes = {
        key: _array_sha256(np.asarray(value)) for key, value in arrays.items()
    }
    save_packet(directory, name, {"facts": dict(facts), "raw_arrays": dict(arrays)})
    return _readback_component_packet(directory, name, array_hashes)


def _local_class_measurement(
    item: Mapping[str, Any],
    cfg: Any,
    *,
    output_directory: Path,
    resource_sample: Callable[[], Mapping[str, Any]],
) -> tuple[dict[str, Any], Any]:
    from src.solvers.task40_w1_local_probe import _local_tensor, solve_local_rhs

    started = perf_counter()
    before = dict(resource_sample())
    bounds = tuple(
        (float(axis[0]), float(axis[1]))
        for axis in item["representative_bounds_nm"]
    )
    local = _local_tensor(6, bounds, cfg, int(item["material_tag"]))
    canonical_cell_info = np.asarray(local["cell_info"], dtype=np.uint32).reshape(-1)
    target_coordinates = item.get("target_representative_cell_coordinates_nm")
    target_permutation = item.get("target_representative_cell_permutation")
    if target_coordinates is None or target_permutation is None:
        geometry_match = None
        permutation_match = None
        orientation_scope = "FILLED_REFERENCE_ONLY_CLASS_NO_TARGET_REPRESENTATIVE"
    else:
        geometry_match = bool(
            np.allclose(
                np.asarray(target_coordinates, dtype=np.float64),
                np.asarray(local["coordinates"], dtype=np.float64),
                rtol=0,
                atol=2e-14,
            )
        )
        permutation_match = bool(
            int(target_permutation) == int(canonical_cell_info[0])
        )
        orientation_scope = (
            "REPRESENTATIVE_TARGET_COORDINATES_AND_PERMUTATION_MATCH"
            if geometry_match and permutation_match
            else "CANONICAL_LOCAL_TENSOR_ONLY_TARGET_DIRECTION_UNKNOWN"
        )
    basix_element = local["basix_element"]
    Vii = np.asarray(local["Vii"], dtype=np.complex128)
    Vit = np.asarray(local["Vit"], dtype=np.complex128)
    Vti = np.asarray(local["Vti"], dtype=np.complex128)
    Vtt = np.asarray(local["Vtt"], dtype=np.complex128)

    solved_vit, solve_vit_block = solve_local_rhs(Vii, local["factor"], Vit)
    schur = np.ascontiguousarray(Vtt - Vti @ solved_vit)
    rng = np.random.default_rng(4000 + int(item["representative_cell"]))
    xi = np.asarray(
        rng.standard_normal(local["local_interior_dimension"])
        + 1j * rng.standard_normal(local["local_interior_dimension"]),
        dtype=np.complex128,
    )
    xt = np.asarray(
        rng.standard_normal(local["local_trace_dimension"])
        + 1j * rng.standard_normal(local["local_trace_dimension"]),
        dtype=np.complex128,
    )
    interior_rhs = Vii @ xi + Vit @ xt
    recovered, solve_recovery = solve_local_rhs(
        Vii, local["factor"], interior_rhs - Vit @ xt, reference_solution=xi
    )
    vit_xt_rhs = Vit @ xt
    solved_vit_xt, solve_vit_xt = solve_local_rhs(
        Vii, local["factor"], vit_xt_rhs
    )
    schur_rhs = Vtt @ xt - Vti @ solved_vit_xt
    schur_error = float(
        np.linalg.norm(schur_rhs - schur @ xt)
        / max(float(np.linalg.norm(schur_rhs)), np.finfo(float).tiny)
    )
    recovery_residual = float(solve_recovery["final_relative_residual"])
    recovery_forward = float(solve_recovery["final_forward_relative"])
    recovery_rhs = interior_rhs - Vit @ xt
    solve_rows = {
        "Vii_inverse_Vit": solve_vit_block,
        "Vii_inverse_recovery_rhs": solve_recovery,
        "Vii_inverse_Vit_xt": solve_vit_xt,
    }
    solve_residuals_pass = all(
        np.isfinite(float(row["final_relative_residual"]))
        and float(row["final_relative_residual"]) <= LOCAL_EQUATION_LIMIT
        for row in solve_rows.values()
    )
    gate_rows = {
        "interior_factor_identity": bool(
            np.isfinite(local["interior_factor_identity_relative"])
            and float(local["interior_factor_identity_relative"]) <= LOCAL_EQUATION_LIMIT
        ),
        "same_factor_original_matrix_residuals": solve_residuals_pass,
        "manufactured_solution_forward_error": bool(
            np.isfinite(recovery_forward) and recovery_forward <= LOCAL_FORWARD_LIMIT
        ),
        "schur_action": bool(np.isfinite(schur_error) and schur_error <= LOCAL_EQUATION_LIMIT),
    }
    local_lu_factor_count = int(local.get("factor") is not None)
    if local_lu_factor_count != 1:
        raise RuntimeError("each measured V20 metric class must create exactly one local LU factor")
    factor_arrays = local["factor"] if isinstance(local["factor"], tuple) else (local["factor"],)
    named_arrays = [
        (name, local[name])
        for name in (
            "tensor", "Vii", "Vit", "Vti", "Vtt", "interior_positions",
            "trace_positions", "coordinates", "cell_info",
        )
    ]
    named_arrays.extend((f"lu_{index}", value) for index, value in enumerate(factor_arrays))
    named_arrays.extend(
        (
            ("solved_Vit", solved_vit),
            ("Schur", schur),
            ("manufactured_xi", xi),
            ("manufactured_xt", xt),
            ("recovered_xi", recovered),
        )
    )
    arrays = _array_inventory(named_arrays)
    row = {
        "class_id": item["class_id"],
        "material": item["material"],
        "material_tag": int(item["material_tag"]),
        "metric_identity": item["metric_identity"],
        "class_cell_count": int(item["cell_count"]),
        "target_cell_count": int(item["target_cell_count"]),
        "filled_reference_cell_count": int(item["filled_reference_cell_count"]),
        "models_present": list(item["models_present"]),
        "representative_cell": int(item["representative_cell"]),
        "representative_target_cell": item.get("target_representative_cell"),
        "representative_target_coordinates_nm": target_coordinates,
        "canonical_local_coordinates_nm": np.asarray(local["coordinates"]).tolist(),
        "target_cell_permutation": target_permutation,
        "canonical_local_cell_info": canonical_cell_info.astype(int).tolist(),
        "representative_geometry_match": geometry_match,
        "representative_cell_permutation_match": permutation_match,
        "directional_mpc_qualification_scope": orientation_scope,
        "bounds_nm": [list(axis) for axis in bounds],
        "epsilon_r": local["epsilon_r"],
        "full_local_rows": int(local["local_full_dimension"]),
        "interior_rows": int(local["local_interior_dimension"]),
        "trace_rows": int(local["local_trace_dimension"]),
        "interior_factor_identity_relative": float(local["interior_factor_identity_relative"]),
        "local_lu_factor_count": local_lu_factor_count,
        "same_factor_solve_facts": solve_rows,
        "recovery_original_matrix_residual_relative": recovery_residual,
        "recovery_forward_relative": recovery_forward,
        "schur_action_relative": schur_error,
        "gate_limits": {
            "original_local_equation": LOCAL_EQUATION_LIMIT,
            "manufactured_forward_error": LOCAL_FORWARD_LIMIT,
        },
        "gates": gate_rows,
        "passed": all(gate_rows.values()),
        "status": "PASS" if all(gate_rows.values()) else "FAILED_LOCAL_CLASS_GATE",
        "array_inventory": arrays,
        "resource_sample_before": before,
        "elapsed_seconds": perf_counter() - started,
    }
    row["raw_packet"] = _save_component_packet(
        output_directory,
        f"v20_local_{item['class_id']}",
        row,
        {
            "Vii": Vii,
            "Vit": Vit,
            "Vti": Vti,
            "Vtt": Vtt,
            "Schur": schur,
            "known_xi": xi,
            "known_xt": xt,
            "interior_rhs": recovery_rhs,
            "recovered_xi": recovered,
            "solved_Vit": solved_vit,
            "solved_Vit_xt": solved_vit_xt,
        },
    )
    # Retain one Basix element for the face map; release every tensor and LU now.
    del local, Vii, Vit, Vti, Vtt, solved_vit, schur, xi, xt, interior_rhs
    del recovered, vit_xt_rhs, solved_vit_xt, schur_rhs, recovery_rhs
    del named_arrays, factor_arrays
    gc.collect()
    row["resource_sample_after_release"] = dict(resource_sample())
    row["resource_sample_after_release"]["sample_scope"] = "after this class tensor/LU release"
    return row, basix_element


def _port_gate(result: Mapping[str, Any]) -> dict[str, Any]:
    equation_keys = (
        "local_recovery_equation_relative",
        "local_original_trace_equation_relative",
        "local_reduced_trace_equation_relative",
        "local_trace_elimination_identity_relative",
        "local_port_equation_relative",
        "local_reduced_port_equation_relative",
        "local_port_elimination_identity_relative",
    )
    equation = {
        key: bool(np.isfinite(float(result.get(key, np.inf))) and float(result[key]) <= LOCAL_EQUATION_LIMIT)
        for key in equation_keys
    }
    forward = bool(
        np.isfinite(float(result.get("known_interior_solution_relative", np.inf)))
        and float(result["known_interior_solution_relative"]) <= LOCAL_FORWARD_LIMIT
    )
    direct = result.get("small_key_native_carrier_witness", {})
    direct_gate = bool(
        isinstance(direct, Mapping)
        and np.isfinite(float(direct.get("direct_trace_B_relative", np.inf)))
        and np.isfinite(float(direct.get("direct_trace_D_relative", np.inf)))
        and float(direct["direct_trace_B_relative"]) <= 1.0e-14
        and float(direct["direct_trace_D_relative"]) <= 1.0e-14
        and np.isfinite(float(direct.get("full_dof_direct_B_relative", np.inf)))
        and np.isfinite(float(direct.get("full_dof_direct_D_relative", np.inf)))
        and float(direct["full_dof_direct_B_relative"]) <= LOCAL_EQUATION_LIMIT
        and float(direct["full_dof_direct_D_relative"]) <= LOCAL_EQUATION_LIMIT
    )
    return {
        **equation,
        "manufactured_solution_forward_error": forward,
        "independent_direct_native_carrier": direct_gate,
        "passed": all(equation.values()) and forward and direct_gate,
    }


def run_v20_local_port_components(
    resolved: Mapping[str, Any],
    output_directory: str | Path,
    *,
    mesh_data: Any,
    cfg: Any,
    geometry_facts: Mapping[str, Any],
    classes: list[dict[str, Any]],
    mode_rows: tuple[Mapping[str, Any], ...],
    resource_sample: Callable[[], Mapping[str, Any]],
) -> dict[str, Any]:
    from src.solvers.directional_boundary import BoundaryLayout, FacetPolynomial
    from src.solvers.task40_w1_local_probe import stream_boundary_correction

    output_directory = Path(output_directory)
    started = perf_counter()
    local_rows = []
    basix_element = None
    max_class_payload = 0
    max_class_backing = 0
    for item in classes:
        row, current_basix = _local_class_measurement(
            item,
            cfg,
            output_directory=output_directory,
            resource_sample=resource_sample,
        )
        local_rows.append(row)
        basix_element = basix_element or current_basix
        max_class_payload = max(
            max_class_payload, int(row["array_inventory"]["named_array_payload_bytes_with_aliases"])
        )
        max_class_backing = max(max_class_backing, int(row["array_inventory"]["unique_backing_bytes"]))
    if basix_element is None:
        raise RuntimeError("V20 geometry has no exact local metric classes")

    axis_coordinates = [
        np.unique(np.asarray(mesh_data.mesh.geometry.x[:, axis], dtype=np.float64))
        for axis in range(3)
    ]
    mode0 = mode_rows[0]
    from src.solvers.task40_v20_mode_inventory import _complex

    incident_alpha = _complex(mode0["alpha"], "alpha") - 2.0 * np.pi * int(mode0["m"]) / float(cfg.period_x)
    incident_gamma = _complex(mode0["gamma"], "gamma") - 2.0 * np.pi * int(mode0["n"]) / float(cfg.period_y)
    phases = (
        np.exp(1j * incident_alpha * float(cfg.period_x)),
        np.exp(1j * incident_gamma * float(cfg.period_y)),
    )
    layout = BoundaryLayout(
        axis_coordinates[0], axis_coordinates[1], FacetPolynomial(basix_element), phases
    )
    boundary_witnesses = []
    for boundary in geometry_facts["periodic_face_inventory"]["boundary_face_cells"]:
        side = str(boundary["side"])
        nmode = len(mode_rows)
        mode_alpha = np.asarray(
            [np.exp(1j * (index % 997) / 37.0) / np.sqrt(index + 1.0) for index in range(nmode)],
            dtype=np.complex128,
        )
        local_layout_rows = int(layout.rows)
        rng = np.random.default_rng(4100 + int(boundary["cell_id"]))
        trace_values = np.asarray(
            rng.standard_normal(local_layout_rows) + 1j * rng.standard_normal(local_layout_rows),
            dtype=np.complex128,
        )
        known_interior = np.asarray(
            rng.standard_normal(450) + 1j * rng.standard_normal(450), dtype=np.complex128
        )
        sample_before = dict(resource_sample())
        witness_started = perf_counter()
        try:
            result = stream_boundary_correction(
                modes=list(mode_rows),
                side=side,
                degree=6,
                bounds=tuple(tuple(map(float, axis)) for axis in boundary["bounds_nm"]),
                config=cfg,
                material_tag=int(boundary["material_tag"]),
                mode_alpha=mode_alpha,
                trace_values=trace_values,
                known_interior_solution=known_interior,
                boundary_layout=layout,
                face_i=int(boundary["face_i"]),
                face_j=int(boundary["face_j"]),
                boundary_quadrature_degree=PORT_QUADRATURE_DEGREE,
                batch_modes=PORT_BATCH_MODES,
            )
            arrays = result.pop("arrays", {})
            array_inventory = _array_inventory(list(arrays.items()))
            # Replace the legacy q30 label with the exact rule actually used.
            direct = result.get("small_key_native_carrier_witness", {})
            direct["full_dof_direct_quadrature_degree"] = PORT_QUADRATURE_DEGREE
            direct["full_dof_direct_B_relative"] = direct.pop("full_dof_direct_q30_B_relative", None)
            direct["full_dof_direct_D_relative"] = direct.pop("full_dof_direct_q30_D_relative", None)
            direct["full_dof_direct_gate_pass"] = direct.pop("full_dof_direct_q30_gate_pass", None)
            for obsolete in tuple(direct):
                if "q30" in obsolete:
                    direct.pop(obsolete, None)
            gate = _port_gate(result)
            result.pop("arrays", None)
            result.update(
                actual_boundary_facet=int(boundary["facet_id"]),
                actual_boundary_cell=int(boundary["cell_id"]),
                actual_material_tag=int(boundary["material_tag"]),
                actual_boundary_cell_permutation=int(boundary["cell_permutation"]),
                actual_boundary_bounds_nm=boundary["bounds_nm"],
                target_mode_manifest_sha256=resolved["execution"][
                    "task40_mode_manifest_sha256"
                ],
                target_ordered_mode_key_sha256=resolved["execution"][
                    "task40_mode_key_sha256"
                ],
                target_mode_count_full_ordered=len(mode_rows),
                target_mode_batch_count=(len(mode_rows) + PORT_BATCH_MODES - 1)
                // PORT_BATCH_MODES,
                mode_vector_scope=(
                    "actual ordered target mode rows are traversed in bounded batches; "
                    "trace and amplitude test vectors are deterministic synthetic witnesses"
                ),
                face_indices=[int(boundary["face_i"]), int(boundary["face_j"])],
                phase_x={"real": float(phases[0].real), "imag": float(phases[0].imag)},
                phase_y={"real": float(phases[1].real), "imag": float(phases[1].imag)},
                array_inventory=array_inventory,
                gates=gate,
                gate_limits={
                    "original_local_equation": LOCAL_EQUATION_LIMIT,
                    "manufactured_forward_error": LOCAL_FORWARD_LIMIT,
                    "direct_trace_carrier": 1.0e-14,
                },
                status="PASS" if gate["passed"] else "FAILED_LOCAL_PORT_GATE",
                resource_sample_before=sample_before,
                elapsed_seconds=perf_counter() - witness_started,
            )
            result["raw_packet"] = _save_component_packet(
                output_directory, f"v20_port_{side}", result, arrays
            )
            del arrays, mode_alpha, trace_values, known_interior
            gc.collect()
            result["resource_sample_after_release"] = dict(resource_sample())
            result["resource_sample_after_release"]["sample_scope"] = "after this side's mode batches and vectors were released"
            boundary_witnesses.append(result)
        except Exception as error:
            boundary_witnesses.append(
                {
                    "side": side,
                    "actual_boundary_facet": int(boundary["facet_id"]),
                    "actual_boundary_cell": int(boundary["cell_id"]),
                    "actual_material_tag": int(boundary["material_tag"]),
                    "actual_boundary_cell_permutation": int(
                        boundary["cell_permutation"]
                    ),
                    "actual_boundary_bounds_nm": boundary["bounds_nm"],
                    "target_mode_manifest_sha256": resolved["execution"][
                        "task40_mode_manifest_sha256"
                    ],
                    "target_ordered_mode_key_sha256": resolved["execution"][
                        "task40_mode_key_sha256"
                    ],
                    "target_mode_count_full_ordered": len(mode_rows),
                    "mode_batch_size": PORT_BATCH_MODES,
                    "mode_vector_scope": (
                        "actual ordered target modes; synthetic test vectors; one representative face only"
                    ),
                    "boundary_quadrature_degree": PORT_QUADRATURE_DEGREE,
                    "batch_modes": PORT_BATCH_MODES,
                    "status": "FAILED_LOCAL_PORT_GATE",
                    "error": {"type": type(error).__name__, "message": str(error)},
                    "resource_sample_before": sample_before,
                    "resource_sample_after": dict(resource_sample()),
                    "elapsed_seconds": perf_counter() - witness_started,
                }
            )
            del mode_alpha, trace_values, known_interior
            gc.collect()

    passed = all(row["passed"] for row in local_rows) and all(
        row.get("status") == "PASS" for row in boundary_witnesses
    )
    report = {
        "schema": "task40extra.review_v20_original_local_port_components.v1",
        "status": "PASS" if passed else "PARTIAL_OR_FAILED",
        "mode_manifest_sha256": resolved["execution"]["task40_mode_manifest_sha256"],
        "ordered_mode_key_sha256": resolved["execution"]["task40_mode_key_sha256"],
        "mode_count_full_ordered": len(mode_rows),
        "mode_batch_size": PORT_BATCH_MODES,
        "boundary_quadrature_degree": PORT_QUADRATURE_DEGREE,
        "q0_predeclared_by_largest_port_count": 0,
        "q_port_counts": [4076, 4052, 4028, 3984, 3856, 3984, 4028, 4052],
        "phase_x": {"real": float(phases[0].real), "imag": float(phases[0].imag)},
        "phase_y": {"real": float(phases[1].real), "imag": float(phases[1].imag)},
        "local_cell_class_count": len(local_rows),
        "local_cell_classes": local_rows,
        "directional_mpc_qualification": {
            "status": "PARTIAL_CANONICAL_LOCAL_COMPONENTS",
            "representative_geometry_and_permutation_match_count": sum(
                row.get("representative_geometry_match") is True
                and row.get("representative_cell_permutation_match") is True
                for row in local_rows
            ),
            "class_count_without_matching_target_orientation": sum(
                row.get("representative_geometry_match") is not True
                or row.get("representative_cell_permutation_match") is not True
                for row in local_rows
            ),
            "meaning": (
                "local algebra is measured on canonical one-cell meshes with exact target bounds/material; "
                "a coordinate/permutation match covers only that representative class and does not qualify "
                "the full target directional map, MPC, or operator"
            ),
        },
        "maximum_single_class_named_array_payload_bytes_with_aliases": max_class_payload,
        "maximum_single_class_unique_backing_bytes": max_class_backing,
        "boundary_components": boundary_witnesses,
        "global_p6_space_created": False,
        "global_MPC_created": False,
        "global_C_D_created": False,
        "all_q_csr_created": False,
        "global_mumps_factor_created": False,
        "local_lu_factor_count": int(
            sum(int(row["local_lu_factor_count"]) for row in local_rows)
        ),
        "local_lu_factor_count_scope": "one local dense LU per measured exact metric class; no global MUMPS factor",
        "full_target_operator_qualified": False,
        "full_target_field_qualified": False,
        "elapsed_seconds": perf_counter() - started,
        "resource_sample_after": dict(resource_sample()),
        "scope": (
            "measured exact metric classes one at a time and bounded all-mode port actions; "
            "port samples use actual top/bottom representative face bounds and Floquet phases with the "
            "complete ordered mode table but synthetic test vectors; no target global FE/MPC/q CSR/factor/PDE claim"
        ),
    }
    return report


__all__ = ["run_v20_local_port_components"]
