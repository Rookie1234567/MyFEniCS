"""Opt-in p4-only research export using the existing physical kernels.

This module never builds a p6 space, creates a global factor, runs KSP, or
computes official powers. A degree-six UFL space is used only for FFCx's
symbolic quadrature analysis, preserving the parent coarse-form rule.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import sys
import time
from typing import Any, Callable


G0_INPUT_SHA256 = "6654ec211efbc6112f3ccba13ad67ff3a97cdbc471bdd48e39f891819f51a41e"
G0_MODE_SHA256 = "de0e4b79e8ec0741db4e4b08f2f2ce97e78026d18e1c6795da7d6ddd5f3d9ed8"
G0_HISTORICAL_MODE_SHA256 = "c3ff9c0cf35e2d183f44ed3fb7448d4aa586bb6fdf7f9dc9ba78dc25011c693a"
G0_MODE_REFERENCE_SHA256 = "8c061fa7e720e24f4377209454cb48c94d2e7a59fc04cad71a44d00ba7d6203d"
G0_ROWS = 29072
G0_NNZ = 10912592
G0_CELLS = 336
G0_MODES = 80


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def validate_named_input(path: Path) -> None:
    if file_sha256(path) != G0_INPUT_SHA256:
        raise ValueError("probe is restricted to the hash-bound G0 review-v1 input")


def validate_named_mode_inventory(rows: Any, digest: str, reference: Any) -> dict[str, Any]:
    """Freeze a new full identity; independently check prior M0 numerics.

    The unavailable raw manifest behind the historical PDE hash is not
    claimed identical. The declared 64-epsilon comparison is only a
    generator/reference roundoff gate, not a PDE or truncation tolerance.
    """
    if digest != G0_MODE_SHA256 or len(rows) != G0_MODES or reference["count"] != G0_MODES:
        raise ValueError("new full-manifest identity or exact real-mode count mismatch")
    fields = {"alpha": "alpha", "gamma": "gamma", "beta": "beta", "E": "e_vector",
              "H": "h_vector", "k": "k_vector", "tangent_norm_sq": "electric_tangential_norm_sq",
              "power": "power_per_unit_amplitude"}
    maxima = {field: 0.0 for field in fields}
    scaled_maxima = dict(maxima)

    def number(value):
        if isinstance(value, dict) and set(value) == {"real", "imag"}:
            value = complex(value["real"], value["imag"])
        elif isinstance(value, (list, tuple)):
            if len(value) != 2:
                raise ValueError("complex reference must contain exactly real/imag")
            value = complex(*value)
        else:
            value = complex(value)
        if not math.isfinite(value.real) or not math.isfinite(value.imag):
            raise ValueError("non-finite mode identity field")
        return value

    for index, (actual, expected) in enumerate(zip(rows, reference["rows"], strict=True)):
        if any(type(actual[name]) is not int for name in ("m", "n", "mode_index")):
            raise ValueError("mode indices must retain their exact integer type")
        key = [actual["side"], actual["m"], actual["n"], actual["polarization"]]
        if key != expected["key"] or actual["mode_index"] != index:
            raise ValueError("ordered real mode key/index differs from independent M0 reference")
        if any(actual[flag] != expected[flag] for flag in ("propagating", "rayleigh_warning")):
            raise ValueError("real mode classification flags differ from independent M0 reference")
        for field, actual_field in fields.items():
            a, b = actual[actual_field], expected[field]
            pairs = zip(a, b, strict=True) if field in ("E", "H", "k") else ((a, b),)
            for av, bv in pairs:
                av, bv = number(av), number(bv)
                delta = abs(av - bv)
                scaled = delta / max(1.0, abs(av), abs(bv))
                maxima[field] = max(maxima[field], delta)
                scaled_maxima[field] = max(scaled_maxima[field], scaled)
                if scaled > 64 * sys.float_info.epsilon:
                    raise ValueError(f"mode numeric reference mismatch: index={index}, field={field}")
    return {"schema": "real-p4-probe.independent-mode-gate.v1", "passed": True,
            "full_manifest_sha256": digest, "historical_PDE_manifest_sha256": G0_HISTORICAL_MODE_SHA256,
            "historical_hash_status": "unverified_raw_unavailable_difference_reason_unknown",
            "exact_ordered_key_index_and_flags": True, "reference_raw_audit_sha256": reference["raw_audit_sha256"],
            "numeric_scaled_limit": 64 * sys.float_info.epsilon, "max_absolute_deltas": maxima,
            "max_scaled_deltas": scaled_maxima, "historical_hash_identity_claimed": False}


def _symbolic_parent_quadrature(levels: Any, cfg: Any):
    """Same FFCx analysis as the parent, without a DOLFINx p6 allocation."""
    import numpy as np
    import ufl
    from basix.ufl import element
    from ffcx.analysis import analyze_ufl_objects
    from src.solvers.common_3d_forms import _build_physical_volume_terms

    symbolic_space = ufl.FunctionSpace(
        levels["mesh"].ufl_domain(), element("N1curl", levels["mesh"].basix_cell(), 6)
    )
    coefficient = ufl.Coefficient(symbolic_space)
    dx = ufl.Measure("dx", domain=levels["mesh"], subdomain_data=levels["mesh_data"].cell_tags)
    forms = _build_physical_volume_terms(
        cfg, ufl.TrialFunction(symbolic_space), ufl.TestFunction(symbolic_space), dx
    )
    metadata, records = [], []
    for component, form in zip(("curl", "material_mass"), forms, strict=True):
        analysis = analyze_ufl_objects([ufl.action(form, coefficient)], np.dtype(np.complex128))
        rules = set()
        for group in analysis.form_data[0].integral_data:
            for integral in group.integrals:
                rule = integral.metadata()
                if rule["quadrature_rule"] == "custom":
                    raise ValueError("custom parent quadrature is not supported by this export")
                pair = (int(rule["quadrature_degree"]), str(rule["quadrature_rule"]))
                rules.add(pair)
                records.append({"component": component, "subdomain_id": integral.subdomain_id(),
                                "quadrature_degree": pair[0], "quadrature_rule": pair[1]})
        if len(rules) != 1:
            raise ValueError("parent symbolic form has nonuniform material quadrature")
        degree, rule = rules.pop()
        metadata.append({"quadrature_degree": degree, "quadrature_rule": rule})
    return tuple(metadata), records


def assemble_export_named_g0(
    input_path: Path,
    output: Path,
    *,
    provenance: dict[str, Any],
    event: Callable[[str, dict[str, Any]], None],
    allocation_gate: Callable[[str, dict[str, Any]], None],
) -> dict[str, Any]:
    """Assemble/export one real G0 p4 system, with no global solve."""
    import numpy as np
    from dolfinx import fem
    from mpi4py import MPI
    from petsc4py import PETSc
    from src.io import load_and_resolve
    from src.io.input_validation import simulation_config_3d_from_normalized
    from src.solvers.fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
        build_physical_rhs, build_same_mesh_physical_action, destroy_same_mesh_physical_action,
    )
    from src.solvers.hcurl_assembly_time_condensation import build_unconstrained_assembly_time_condensation
    from src.solvers.p4_cell_condensed_inverse import (
        P4CellCondensedInverse, assemble_condensed_ports, petsc_csr_content_identity,
    )
    from src.solvers.condensed_fine_reference import native_map_arrays
    from src.solvers.fullspace_dtn_action import (
        _canonical_json_bytes, _jsonable, build_dynamic_mode_inventory,
        FULLSPACE_DTN_MANIFEST_SCHEMA, FULLSPACE_DTN_PROFILE,
    )

    validate_named_input(input_path)
    if MPI.COMM_WORLD.size != 1 or np.dtype(PETSc.ScalarType) != np.dtype(np.complex128):
        raise ValueError("named export requires MPI1 complex128 PETSc")
    specification = load_and_resolve(input_path)
    resolved = specification.as_jsonable()
    cfg = simulation_config_3d_from_normalized(resolved)
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "resolved_input.json", resolved)
    started = time.perf_counter()
    levels = action = condensed = inverse = rhs = reduced_rhs = None
    descriptors: dict[str, Any] = {}
    result = {"schema": "real-p4-probe.assembly-export.v1", "status": "STARTED",
              "purpose": "REAL_PHYSICAL_RHS_SCREEN", "official_result": False,
              "original_A4_residual": None, "original_A4_residual_status": "not_run_no_factor",
              "BAL_H_qualification": False, "global_factor_created": False,
              "full_p6_space_constructed": False, "source": provenance}

    def save_array(label: str, values: Any):
        array = np.asarray(values)
        if array.dtype.kind == "O":
            raise ValueError(f"object/pickle payload prohibited: {label}")
        if array.dtype.kind in "fc" and not np.isfinite(array).all():
            raise ValueError(f"non-finite export array: {label}")
        path = output / f"{label}.npy"
        np.save(path, array, allow_pickle=False)
        descriptor = {"path": path.name, "shape": list(array.shape), "dtype": str(array.dtype),
                      "array_bytes": int(array.nbytes), "file_bytes": path.stat().st_size,
                      "file_sha256": file_sha256(path)}
        descriptors[label] = descriptor
        return label

    try:
        mode_inventory = build_dynamic_mode_inventory(cfg)
        modes, mode_rows, mode_digest = mode_inventory
        reference_path = Path(__file__).resolve().parents[2] / "benchmarks/cases/task40extra_dot_parallel_cloud/real_p4_mode_reference.json"
        if file_sha256(reference_path) != G0_MODE_REFERENCE_SHA256:
            raise ValueError("independent frozen mode reference file content mismatch")
        mode_gate = validate_named_mode_inventory(mode_rows, mode_digest, json.loads(reference_path.read_text()))
        full_mode_payload = {"schema": FULLSPACE_DTN_MANIFEST_SCHEMA, "profile": FULLSPACE_DTN_PROFILE,
                             "mode_count": len(modes), "modes": mode_rows}
        encoded_modes = _canonical_json_bytes(full_mode_payload)
        if hashlib.sha256(encoded_modes).hexdigest() != mode_digest:
            raise ValueError("full mode manifest canonical serialization identity mismatch")
        (output / "ordered_modes_canonical.json").write_bytes(encoded_modes)
        result["mode_gate"] = mode_gate
        event("independent_real_mode_gate_passed", mode_gate)
        event("p4_mesh_mpc_started", {})
        levels = _build_same_mesh_levels(cfg, MPI.COMM_SELF, (4,), include_positive_coefficients=False)
        cells = int(levels["mesh"].topology.index_map(3).size_local)
        if cells != G0_CELLS or set(levels["spaces"]) != {4}:
            raise ValueError("named G0 mesh/degree inventory mismatch")
        event("p4_mesh_mpc_complete", {"cells": cells})
        quadrature, integral_records = _symbolic_parent_quadrature(levels, cfg)
        event("symbolic_parent_quadrature_complete", {"quadrature": quadrature, "records": integral_records,
                                                    "p6_analysis_only": True})
        action = build_same_mesh_physical_action(levels, cfg, 4, mode_inventory=mode_inventory,
                                                 volume_quadrature_metadata=quadrature)
        if len(action["modes"]) != G0_MODES or action["mode_sha256"] != G0_MODE_SHA256:
            raise ValueError("ordered real DtN mode inventory does not match named G0")
        rhs, rhs_facts = build_physical_rhs(action)
        if not np.isfinite(rhs.norm()) or rhs.norm() <= np.finfo(float).tiny:
            raise ValueError("real incident RHS is zero/non-finite")
        event("real_p4_physical_action_rhs_complete", {"rhs_norm": float(rhs.norm()), "rhs": rhs_facts,
                                                     "dtn_quadrature_degree": action["dtn_quadrature_degree"]})
        compiled = fem.form(action["volume_action"].bilinear_form)
        carrier = action["dtn_action"].carrier
        condensed = build_unconstrained_assembly_time_condensation(
            compiled, levels["spaces"][4], levels["mesh_data"].cell_tags,
            mpc=levels["floquets"][4].mpc, appended_global_rows=len(carrier.entries),
            appended_support_owned_cell_groups=(np.arange(cells, dtype=np.int32),),
            appended_support_group_by_row=tuple(0 for _ in carrier.entries),
            dense_appended_block=True, sum_duplicate_cell_integrals=True,
            strict_local_checks=True, defer_final_assembly=True,
            preserve_exact_geometry=True, allocation_gate=allocation_gate,
        )
        del compiled
        port_terms = assemble_condensed_ports(condensed, carrier)
        identity = petsc_csr_content_identity(condensed.matrix)
        event("real_p4_condensed_assembled", {"matrix": identity, "condensation": condensed.build_audit})
        if identity["shape"] != [G0_ROWS, G0_ROWS] or identity["nnz"] != G0_NNZ:
            raise ValueError("actual G0 p4 shape/NNZ differs from named expectation; stop before factor")
        # Reuse the production reduction/recovery owner with no factor attached.
        # Constructor freezes only small local XiB, and private RHS reduction
        # is the same operation apply() calls before its one global solve.
        inverse = P4CellCondensedInverse(condensed, None, port_terms=port_terms,
                                        owns_condensed=False, owns_factor=False)
        reduced_rhs = inverse._reduce_storage_rhs(rhs)
        save_array("physical_storage_rhs", rhs.array)
        save_array("condensed_augmented_rhs", reduced_rhs.array)
        indptr, indices, values = condensed.matrix.getValuesCSR()
        save_array("csr_indptr", indptr)
        save_array("csr_indices", indices)
        save_array("csr_data", values)
        event("real_p4_csr_rhs_exported", {"raw_array_bytes": sum(d["array_bytes"] for d in descriptors.values())})
        classes = {key: index for index, key in enumerate(condensed.interior_lu_by_class)}
        cache_manifest = []
        for key, class_index in classes.items():
            prefix = f"class_{class_index}"
            local = {"index": class_index, "key_repr": repr(key)}
            lu, pivots = condensed.interior_lu_by_class[key]
            local["lu"] = save_array(prefix + "_lu", lu)
            local["pivots"] = save_array(prefix + "_pivots", pivots)
            for name in ("interior_from_trace_by_class", "trace_from_interior_rhs_by_class",
                         "interior_rhs_projection_by_class", "interior_solution_embedding_by_class",
                         "interior_residual_projection_by_class"):
                local[name] = save_array(prefix + "_" + name, getattr(condensed, name)[key])
            cache_manifest.append(local)
        cell_manifest = []
        for index, cell in enumerate(condensed.cell_recovery_maps):
            packet = {"index": index, "class_index": classes[cell.class_key],
                      "interiors": save_array(f"cell_{index}_interiors", cell.interior_original_dofs),
                      "traces": save_array(f"cell_{index}_traces", cell.trace_original_dofs)}
            term = port_terms.get(index)
            if term is not None:
                packet["port_terms"] = {name: save_array(f"cell_{index}_port_{name}", getattr(term, name))
                                        for name in ("Bi", "Di", "port_indices")}
                packet["XiB"] = save_array(f"cell_{index}_XiB", inverse._xiB_by_cell[index])
            cell_manifest.append(packet)
        originals, offsets, ids, coefficients = [], [0], [], []
        for original, (target_ids, target_values) in sorted(condensed.trace_constraints.expansion_by_original.items()):
            originals.append(original)
            ids.extend(target_ids)
            coefficients.extend(target_values)
            offsets.append(len(ids))
        for label, value in (("trace_original", condensed.owned_trace_original_dofs),
                             ("active_original", condensed.trace_constraints.owned_active_original_dofs),
                             ("expansion_original", np.asarray(originals, dtype=np.int64)),
                             ("expansion_offsets", np.asarray(offsets, dtype=np.int64)),
                             ("expansion_ids", np.asarray(ids, dtype=np.int64)),
                             ("expansion_coefficients", np.asarray(coefficients, dtype=np.complex128)),
                             ("mesh_coordinates", levels["mesh"].geometry.x),
                             ("mesh_geometry_dofmap", levels["mesh"].geometry.dofmap),
                             ("p4_cell_dofmap", levels["spaces"][4].dofmap.list),
                             ("material_cells", levels["mesh_data"].cell_tags.indices),
                             ("material_values", levels["mesh_data"].cell_tags.values)):
            save_array(label, value)
        native_map = native_map_arrays(levels["spaces"][4], levels["floquets"][4])
        for label, value in native_map.items():
            if isinstance(value, np.ndarray):
                save_array("native_map_" + label, value)
        carrier_manifest = []
        for index, entry in enumerate(carrier.entries):
            packet = {"index": index, "normalization_h": {"real": float(entry.normalization_h.real),
                                                          "imag": float(entry.normalization_h.imag)}}
            for name in ("coupling_rows", "coupling_values", "projection_rows", "projection_values"):
                packet[name] = save_array(f"carrier_{index}_{name}", getattr(entry, name))
            carrier_manifest.append(packet)
        write_json(output / "ordered_modes.json", _jsonable(action["mode_rows"]))
        result.update(status="ASSEMBLY_EXPORT_COMPLETE", matrix=identity,
                      input_sha256=specification.input_sha256, physical_model_sha256=specification.physical_model_sha256,
                      ordered_mode_sha256=action["mode_sha256"], cells=cells, quadrature=quadrature,
                      quadrature_records=integral_records, dtn_quadrature_degree=action["dtn_quadrature_degree"],
                      condensation=condensed.build_audit, rhs=rhs_facts,
                      geometry_cache_policy="exact_mesh_widths_not_historical_p4_csr_byte_identity",
                      rhs_origin="true_p4_incident_Maxwell_RHS_not_saved_BAL_H_RHS",
                      arrays=descriptors, recovery_classes=cache_manifest, recovery_cells=cell_manifest,
                      carrier_entries=carrier_manifest, elapsed_seconds=time.perf_counter() - started,
                      original_A4_reconstruction="rebuild_p4_public_form_action_from_hash_bound_source_and_input",
                      original_A4_storage_rows=int(rhs.getSize()), active_trace_rows=condensed.active_rows)
        final_identity = petsc_csr_content_identity(condensed.matrix)
        if final_identity != identity:
            raise RuntimeError("matrix content changed during export")
        event("real_p4_export_complete", {"elapsed_seconds": result["elapsed_seconds"], "matrix": identity})
        return result
    except BaseException as exc:
        result.update(status="FAILED", error={"type": type(exc).__name__, "message": str(exc)}, arrays=descriptors,
                      elapsed_seconds=time.perf_counter() - started)
        raise
    finally:
        for vector in (reduced_rhs, rhs):
            if vector is not None:
                vector.destroy()
        if inverse is not None:
            inverse.destroy()
        if condensed is not None:
            condensed.destroy()
        if action is not None:
            destroy_same_mesh_physical_action(action)
        write_json(output / "export_manifest.json", result)
