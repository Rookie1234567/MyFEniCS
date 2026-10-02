"""Fresh direct-profile primary/literal/raw component qualification before q factors.

The numerical entry point is externally admitted and limited to X/XZ/Y. It uses
existing full physical constructors, full finalized MPCs and raw observers.
There is no snapshot restoration, full-Ny reference matrix, factor or solve.
Importing this module uses only the standard library.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import hashlib
import json

SCHEMA = "task40extra.direct-fresh-carrier-qualification.v1"
PASS_STATUS = "PASS_DIRECT_FRESH_CARRIER_COMPONENTS_ONLY"
TOLERANCE = 1e-10
METRIC_TOLERANCE = 1e-12


def _sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _gate(callback, stage, *, payload=0, workspace=0, **facts):
    if not callable(callback):
        raise TypeError("a current whole-tree allocation callback is required")
    callback(stage, {"matrix_payload_bytes": int(payload), "workspace_bytes": int(workspace),
                     "factor_count": 0, "allocation_semantics": "additional_objects_not_current_resident_RSS",
                     **facts})


def _write(path, value):
    from .fullspace_dtn_action import _jsonable
    from .dtn_boundary_plane_qualification import _failure_diagnostic
    Path(path).write_text(json.dumps(_jsonable(_failure_diagnostic(value)), indent=2, allow_nan=False)+"\n")


def _reference(path, root):
    path = Path(path).resolve()
    return {"path": str(path.relative_to(root)), "file_sha256": _sha(path)}


@dataclass
class DirectCarrierQualification:
    """Fresh action owners and borrowed shared-bank maps; caller retains this object."""
    global_bundle: Any = None
    global_mode_inventory: Any = None
    global_entities: Any = None
    global_spool: Any = None
    local_bundles: list[Any] = field(default_factory=list)
    local_entities: list[Any] = field(default_factory=list)
    local_layouts: list[Any] = field(default_factory=list)
    transports: list[Any] = field(default_factory=list)
    local_spools: list[Any] = field(default_factory=list)
    qualification_receipt: Any = None

    def destroy(self):
        """Release action owners exactly once; the whole-run owner manages the bank."""
        from .fullspace_same_mesh_hcurl_pmg_physical import destroy_same_mesh_physical_action
        for bundle in reversed(self.local_bundles):
            destroy_same_mesh_physical_action(bundle)
        self.local_bundles.clear()
        if self.global_bundle is not None:
            destroy_same_mesh_physical_action(self.global_bundle)
            self.global_bundle = None
        self.local_layouts.clear()
        self.transports.clear()
        self.local_entities.clear()
        self.global_entities = None
        self.global_mode_inventory = None


def _export(name, array, *, root, save_array, allocation_gate, inventory):
    """Caller-created array, with an allocation admission before writer copies."""
    _gate(allocation_gate, "direct_export_"+name, payload=array.nbytes,
          workspace=array.nbytes+(1 << 20), bounded_named_export=True)
    descriptor = dict(save_array(name, array))
    required = {"path", "file_sha256", "shape", "dtype", "payload_bytes"}
    if required.difference(descriptor):
        raise ValueError("save_array requires exact path/hash/shape/dtype/payload descriptor")
    path = Path(descriptor["path"])
    path = path.resolve() if path.is_absolute() else (root/path).resolve()
    path.relative_to(root)
    if (not path.is_file() or _sha(path) != descriptor["file_sha256"]
            or tuple(descriptor["shape"]) != array.shape or descriptor["dtype"] != str(array.dtype)
            or descriptor["payload_bytes"] != array.nbytes):
        raise ValueError("named direct evidence is not bound to its exact exported array")
    descriptor["path"] = str(path.relative_to(root))
    descriptor["array_sha256"] = hashlib.sha256(array.tobytes(order="C")).hexdigest()
    inventory[name] = descriptor
    return descriptor


class DirectLiteralModeSpool:
    """Bounded exact-nonzero controls from already assembled current literals."""
    schema = "task40extra.direct-literal-current-mode-spool.v1"

    def __init__(self, directory, *, root, original_mode_indices, original_mode_keys,
                 ownership_rows, physical_manifest, context_sha, quotient_context,
                 save_array, allocation_gate):
        self.directory, self.root = Path(directory).resolve(), Path(root).resolve()
        self.directory.relative_to(self.root)
        self.manifest_path = self.directory/"literal_mode_manifest.json"
        if self.directory.exists():
            raise ValueError("literal controls require a fresh artifact directory")
        self.indices, self.keys = tuple(original_mode_indices), tuple(tuple(key) for key in original_mode_keys)
        if not self.indices or len(self.indices) != len(self.keys) or len(set(self.indices)) != len(self.indices):
            raise ValueError("exact original literal mode order is required")
        self.n, self.save_array, self.allocation_gate = int(ownership_rows), save_array, allocation_gate
        self.expected = {"physical_generator_manifest_sha256": physical_manifest, "assembly_context_sha256": context_sha,
                         "quotient_contract_sha256": None if quotient_context is None else quotient_context.sha256,
                         "quotient_twist_index": None if quotient_context is None else quotient_context.twist_index}
        self.branches = tuple(None for _ in self.indices) if quotient_context is None else quotient_context.local_branch_indices
        self.records, self.binding = [], None
        _gate(allocation_gate, "direct_literal_spool_initialize", workspace=1 << 20)
        self.directory.mkdir(parents=True, exist_ok=False)
        self._manifest()

    def _manifest(self):
        complete = len(self.records) == len(self.indices)
        _write(self.manifest_path, {"schema": self.schema,
            "status": "READY_LITERAL_CONTROLS_UNQUALIFIED" if complete else "PARTIAL_LITERAL_CONTROL_STREAM",
            "literal_controls_qualified": False, "PDE_solved": False, "factor_count": 0,
            "expected_mode_count": len(self.indices), "recorded_mode_count": len(self.records),
            "original_mode_indices": self.indices, "ownership_range": (0, self.n),
            "frozen_literal_binding": self.binding, "records": self.records,
            "lossless_rule": "every exact nonzero; no magnitude cutoff", "all_mode_dense_cache": False})

    def observe(self, packet):
        import numpy as np
        from .fullspace_dtn_action import _canonical_json_bytes
        index = len(self.records)
        if index >= len(self.indices):
            raise ValueError("literal controls exceed the exact complete mode inventory")
        if (packet.get("schema") != "task40extra.direct-literal-mode-observer.v1"
                or packet.get("local_mode_index") != index
                or type(packet.get("local_mode_index")) is not int
                or packet.get("original_mode_index") != self.indices[index]
                or type(packet.get("original_mode_index")) is not int
                or tuple(packet.get("original_mode_key", ())) != self.keys[index]
                or tuple(packet.get("ownership_range", ())) != (0, self.n)
                or packet.get("local_branch_index") != self.branches[index]
                or type(packet.get("local_branch_index")) is not type(self.branches[index])
                or any(packet.get(name) != value for name, value in self.expected.items())
                or packet.get("array_ownership") != "borrowed_readonly_during_synchronous_callback; copy_to_retain"):
            raise ValueError("literal control current-mode/context/original mapping changed")
        binding = {name: packet[name] for name in (*self.expected, "qualification_source_sha256",
                                                   "primary_compiled_gauss", "literal_compiled_gauss")}
        if self.binding is not None and _canonical_json_bytes(binding) != _canonical_json_bytes(self.binding):
            raise ValueError("literal control actual source/kernel/Gauss binding changed within stream")
        H = packet.get("literal_H")
        if not isinstance(H, float) or not np.isfinite(H) or H <= 0:
            raise ValueError("literal control requires the actual positive plane H")
        # This admission precedes exact support extraction and every numeric copy.
        upper = 2*self.n*(8+16)
        _gate(self.allocation_gate, "direct_literal_capture_mode_"+str(index), payload=upper,
              workspace=upper+(2 << 20), exact_nonzero_sparse_upper_bytes=upper)
        pairs, offsets, cursor = [], [], 0
        for name in ("C", "D"):
            vector = packet.get("literal_"+name)
            if (not isinstance(vector, np.ndarray) or vector.shape != (self.n,)
                    or vector.dtype != np.dtype(np.complex128) or vector.flags.writeable
                    or not np.isfinite(vector).all()):
                raise ValueError("literal control requires one complete finite borrowed complex128 vector")
            rows = np.flatnonzero(vector != 0)
            values = vector[rows]
            pairs.append((rows, values))
            offsets.append({"field": name, "offset": cursor, "length": len(rows)})
            cursor += len(rows)
        _gate(self.allocation_gate, "direct_literal_combine_mode_"+str(index), payload=cursor*24,
              workspace=cursor*24+(1 << 20), exact_pair_count=2)
        combined_rows = np.concatenate([pair[0] for pair in pairs], dtype=np.int64)
        combined_values = np.concatenate([pair[1] for pair in pairs], dtype=np.complex128)
        payload = {}
        prefix = "literal_"+self.directory.name+"_m"+str(index).zfill(4)
        for name, value in (("rows", combined_rows), ("values", combined_values)):
            _export(prefix+"_"+name, value, root=self.root, save_array=self.save_array,
                    allocation_gate=self.allocation_gate, inventory=payload)
        descriptor_path = self.directory/("mode_"+str(index).zfill(4)+".json")
        _write(descriptor_path, {"schema": self.schema,
            "local_mode_index": index, "original_mode_index": self.indices[index],
            "original_mode_key": self.keys[index], "local_branch_index": self.branches[index],
            "ownership_range": (0, self.n), "literal_H": H, **self.expected,
            "literal_payload": {"rows": payload[prefix+"_rows"], "values": payload[prefix+"_values"]},
            "offset_inventory": offsets, "literal_binding_sha256": hashlib.sha256(_canonical_json_bytes(binding)).hexdigest(),
            "exact_nonzero_policy": "no threshold; no stored carrier substitute"})
        self.binding = binding
        self.records.append({"local_mode_index": index, "original_mode_index": self.indices[index],
                             "literal_H": H, **_reference(descriptor_path, self.root)})
        self._manifest()

    def require_complete(self):
        if len(self.records) != len(self.indices):
            raise ValueError("complete original literal mode inventory was not emitted")
        return _reference(self.manifest_path, self.root)


def _export_inventory(bundle, entities, *, prefix, metadata, local, root, save_array,
                      allocation_gate, inventory):
    import numpy as np
    expected = metadata.local_independent_rows if local else metadata.independent_rows
    interior_count = metadata.local_interior_rows if local else metadata.interior_rows
    storage = metadata.local_storage_rows if local else metadata.storage_rows
    cells = metadata.local_cell_count if local else metadata.cell_count
    mpc = bundle["setup"]["floquets"][4].mpc
    mesh = bundle["setup"]["mesh"]
    if (entities.full_rows != storage or len(entities.independent) != expected
            or entities.dimension_counts.get(3) != interior_count
            or int(mesh.topology.index_map(mesh.topology.dim).size_local) != cells):
        raise ValueError("actual complete native inventory differs from direct admission metadata")
    _gate(allocation_gate, prefix+"_native_partition", payload=(storage+interior_count)*8,
          workspace=2 << 20, all_internal_channels_retained=True)
    independent = np.asarray(entities.independent)
    slaves = np.asarray(mpc.slaves)
    if (len(slaves) != storage-expected or not np.array_equal(
            independent, np.setdiff1d(np.arange(storage), slaves))):
        raise ValueError("complete independent/slave storage partition failed")
    interiors = np.sort(np.concatenate([independent[rows] for (orbit, base), (rows, matrix)
                                       in entities.records.items() if base[0] == 3]))
    if (len(interiors) != interior_count or len(np.unique(interiors)) != interior_count
            or not np.isin(interiors, independent).all()):
        raise ValueError("every actual complete cell-interior channel must survive")
    _gate(allocation_gate, prefix+"_normalization_export", payload=len(bundle["modes"])*8, workspace=1 << 20)
    h = np.asarray([entry.normalization_h for entry in bundle["dtn_action"].carrier.entries], dtype=np.float64)
    data = bundle["setup"]["mesh_data"]
    for suffix, array in (("independent_storage_rows", independent), ("slave_storage_rows", slaves),
                          ("interior_storage_rows", interiors), ("H", h),
                          ("geometry_x", mesh.geometry.x), ("cell_geometry_dofmap", mesh.geometry.dofmap),
                          ("cell_tag_indices", data.cell_tags.indices), ("cell_tag_values", data.cell_tags.values)):
        _export(prefix+"_"+suffix, array, root=root, save_array=save_array,
                allocation_gate=allocation_gate, inventory=inventory)
    return h


def _actual_cells(global_setup, local_setup, metadata, *, root, prefix, save_array,
                  allocation_gate, inventory):
    """Exhaustive actual vertices/material tags and translated whole-cell cover."""
    import numpy as np
    gm, lm = global_setup["mesh"], local_setup["mesh"]
    ga, la, gd, ld = gm.geometry.x, lm.geometry.x, gm.geometry.dofmap, lm.geometry.dofmap
    gdata, ldata = global_setup["mesh_data"], local_setup["mesh_data"]
    _gate(allocation_gate, prefix+"_actual_cell_cover", payload=metadata.cell_count*32,
          workspace=4 << 20, actual_cells_exhaustive=True)
    def tags(data, count):
        indices, values = np.asarray(data.cell_tags.indices), np.asarray(data.cell_tags.values)
        if (len(indices) != count or len(np.unique(indices)) != count
                or not np.array_equal(np.sort(indices), np.arange(count))):
            raise ValueError("actual cell tags must cover every original cell exactly once")
        result = np.empty(count, dtype=values.dtype)
        result[indices] = values
        return result
    gt, lt = tags(gdata, metadata.cell_count), tags(ldata, metadata.local_cell_count)
    centers = np.asarray([np.mean(ga[gd[cell]], axis=0) for cell in range(metadata.cell_count)])
    h = metadata.local_axes[1][-1]-metadata.local_axes[1][0]
    cover = np.empty((metadata.local_cell_count, metadata.replication_count), dtype=np.int64)
    maximum = 0.0
    for cell in range(metadata.local_cell_count):
        xyz = la[ld[cell]]
        for replica in range(metadata.replication_count):
            translated = xyz+np.asarray([0.0, replica*h, 0.0])
            matches = np.flatnonzero(np.max(np.abs(centers-np.mean(translated, axis=0)), axis=1) <= METRIC_TOLERANCE)
            if len(matches) != 1:
                raise ValueError("each actual translated cell needs one original full-period cell")
            original = int(matches[0])
            old = ga[gd[original]]
            old = old[np.lexsort((old[:, 2], old[:, 1], old[:, 0]))]
            translated = translated[np.lexsort((translated[:, 2], translated[:, 1], translated[:, 0]))]
            difference = float(np.max(np.abs(old-translated)))
            maximum = max(maximum, difference)
            if difference > METRIC_TOLERANCE or gt[original] != lt[cell]:
                raise ValueError("actual full/local material or metric identity failed")
            cover[cell, replica] = original
    if not np.array_equal(np.sort(cover.ravel()), np.arange(metadata.cell_count)):
        raise ValueError("full original cells must be covered exactly once")
    descriptor = _export(prefix+"_cell_cover_global_ids", cover, root=root, save_array=save_array,
                         allocation_gate=allocation_gate, inventory=inventory)
    return {"complete_actual_cell_count": metadata.cell_count, "local_actual_cell_count": metadata.local_cell_count,
            "replication_count": metadata.replication_count, "cover": descriptor,
            "maximum_actual_vertex_difference": maximum, "metric_tolerance": METRIC_TOLERANCE,
            "all_material_tags_equal": True, "cell_cover_exactly_once": True}


def _mask_packet(packet, entry, mode, cfg, n):
    """Both actual unchanged cutoffs, full raw coefficients and lost rank-one terms."""
    import numpy as np
    from .dtn_port_3d import _traction_vector
    from .y_orbit_quotient_raw_qualification import (
        _packet_components, _packet_vector, _dense_sparse, _mask, _mask_measurement,
        _rank_one_loss_bound, ABSOLUTE_SPARSE_FLOOR, RELATIVE_SPARSE_CUTOFF,
    )
    from .dtn_boundary_plane_qualification import _relative
    components = _packet_components(packet, n)
    raw = {name: _packet_vector(packet, "raw_"+name, n) for name in ("C", "D")}
    component_vectors, component_measurements = [], []
    for index, vector in enumerate(components):
        expected, threshold = _mask(vector)
        actual = _dense_sparse(packet["component_masked_entries"][index], n)
        diagnostic = packet["component_masks"][index]
        measurement = _mask_measurement(vector, actual, threshold)
        measurement["policy_defect"] = _relative(actual, expected)
        if (measurement["policy_defect"] > TOLERANCE or not np.array_equal(actual != 0, expected != 0)
                or diagnostic["threshold"] != threshold
                or diagnostic["absolute_sparse_floor"] != ABSOLUTE_SPARSE_FLOOR
                or diagnostic["relative_sparse_cutoff"] != RELATIVE_SPARSE_CUTOFF):
            raise ValueError("actual raw component cutoff policy changed")
        component_vectors.append(actual)
        component_measurements.append(measurement)
    traction = _traction_vector(mode, cfg)
    raw_expected = {"C": -traction[0]*components[0]-traction[1]*components[1],
                    "D": np.conjugate(mode.e_vector[0]*components[0]+mode.e_vector[1]*components[1])}
    raw_combination_defects = {name: _relative(raw[name], raw_expected[name]) for name in ("C", "D")}
    if not np.isfinite(tuple(raw_combination_defects.values())).all() or max(raw_combination_defects.values()) > TOLERANCE:
        raise ValueError("actual raw C/D must be the unchanged complete pre-mask component combinations")
    x, y = component_vectors
    combined_expected = {"C": -traction[0]*x-traction[1]*y,
                         "D": np.conjugate(mode.e_vector[0]*x+mode.e_vector[1]*y)}
    combined, stored, final_measurements = {}, {}, {}
    for index, name in enumerate(("C", "D")):
        combined[name] = _packet_vector(packet, "after_component_mask_"+name, n)
        stored[name] = _dense_sparse(packet["stored_"+name+"_sparse"], n)
        expected, threshold = _mask(combined_expected[name])
        diagnostic = packet["combination_masks"][index]["combination_stage"]
        measurement = _mask_measurement(combined[name], stored[name], threshold)
        measurement.update(combination_defect=_relative(combined[name], combined_expected[name]),
                           policy_defect=_relative(stored[name], expected))
        pair = (entry.coupling_rows, entry.coupling_values) if name == "C" else (entry.projection_rows, entry.projection_values)
        measurement["carrier_binding_defect"] = _relative(_dense_sparse(pair, n), stored[name])
        if (any(measurement[key] > TOLERANCE for key in ("combination_defect", "policy_defect", "carrier_binding_defect"))
                or not np.array_equal(stored[name] != 0, expected != 0) or diagnostic["threshold"] != threshold
                or diagnostic["absolute_sparse_floor"] != ABSOLUTE_SPARSE_FLOOR
                or diagnostic["relative_sparse_cutoff"] != RELATIVE_SPARSE_CUTOFF):
            raise ValueError("actual raw final cutoff or carrier binding changed")
        final_measurements[name] = measurement
    H = float(entry.normalization_h)
    raw_norm = float(np.linalg.norm(raw["C"])*np.linalg.norm(raw["D"])/H)
    losses = {"component_mask": _rank_one_loss_bound(combined["C"], combined["D"], raw["C"], raw["D"], H),
              "final_mask": _rank_one_loss_bound(stored["C"], stored["D"], combined["C"], combined["D"], H),
              "all_masks": _rank_one_loss_bound(stored["C"], stored["D"], raw["C"], raw["D"], H)}
    relative = {key: value/raw_norm if raw_norm else (0.0 if value == 0 else float("inf")) for key, value in losses.items()}
    if (not np.isfinite(tuple(relative.values())).all() or max(relative.values()) > TOLERANCE):
        raise ValueError("actual complete-DOF lost rank-one bound exceeds unchanged gate")
    return {"raw": raw, "after_component_mask": combined, "stored": stored}, {
        "components": component_measurements, "final": final_measurements,
        "raw_component_combination_defects": raw_combination_defects,
        "raw_rank_one_Frobenius_norm": raw_norm, "rank_one_loss_bounds": losses,
        "relative_rank_one_bounds": relative}


def _fold_modes(result, local_index, *, metadata, root, save_array, allocation_gate, event, arrays):
    """Complete original/local raw and stored C/D/H identity for every sector alias."""
    import numpy as np
    from .dtn_boundary_plane_qualification import _relative
    from .y_orbit_quotient_raw_qualification import _rank_one_loss_bound
    global_bundle = result.global_bundle
    local_bundle = result.local_bundles[local_index]
    transport = result.transports[local_index]
    context = local_bundle["quotient_context"]
    global_rows, local_rows = result.global_entities.independent, result.local_entities[local_index].independent
    gs = np.asarray(global_bundle["setup"]["floquets"][4].mpc.slaves)
    ls = np.asarray(local_bundle["setup"]["floquets"][4].mpc.slaves)
    prefix = "direct_twist_"+str(context.twist_index)
    ledger_path = root/(prefix+"_fold_ledger.jsonl")
    _gate(allocation_gate, prefix+"_lower_dual_rhs_states", payload=16*(metadata.independent_rows+metadata.local_independent_rows),
          workspace=4 << 20, no_factors=True)
    # A full vector identity above implies every load; this additional explicit
    # nonzero lower-port RHS uses the original raw D and measured H scaling.
    indices = np.arange(metadata.local_independent_rows)
    x = np.sin(indices+0.25)+1j*np.cos(indices+0.5)
    gx = transport.lift_primal(x)
    for suffix, array in (("lower_rhs_local_state", x), ("lower_rhs_global_state", gx)):
        _export(prefix+"_"+suffix, array, root=root, save_array=save_array,
                allocation_gate=allocation_gate, inventory=arrays)
    maximum = 0.0
    count, originals = 0, []
    stage_max = {stage: 0.0 for stage in ("raw", "after_component_mask", "stored")}
    for index, original in enumerate(context.original_mode_indices):
        _gate(allocation_gate, prefix+"_complete_mode_"+str(index),
              payload=24*(metadata.storage_rows+metadata.local_storage_rows)*16,
              workspace=4 << 20, all_mode_raw_fold=True, no_all_mode_dense_cache=True)
        gp, lp = result.global_spool.packet(original), result.local_spools[local_index].packet(index)
        ge = global_bundle["dtn_action"].carrier.entries[original]
        le = local_bundle["dtn_action"].carrier.entries[index]
        modes = global_bundle["modes"]
        global_vectors, global_masks = _mask_packet(gp, ge, modes[original], global_bundle["cfg"], metadata.storage_rows)
        local_vectors, local_masks = _mask_packet(lp, le, modes[original], local_bundle["cfg"], metadata.local_storage_rows)
        row = {"original_mode_index": original, "original_mode_key": context.original_mode_keys[index],
               "local_mode_index": index, "twist_index": context.twist_index,
               "local_branch_index": context.local_branch_indices[index],
               "global_cutoff_losses": global_masks, "local_cutoff_losses": local_masks, "stages": {}}
        defects = []
        for stage in ("raw", "after_component_mask", "stored"):
            measurements, lifted = {}, {}
            for name in ("C", "D"):
                gstorage, lstorage = global_vectors[stage][name], local_vectors[stage][name]
                if np.any(gstorage[gs] != 0) or np.any(lstorage[ls] != 0):
                    raise ValueError("complete MPC raw/stored slave rows must be exactly zero")
                g, local = gstorage[global_rows], lstorage[local_rows]
                fold = transport.fold_raw_coupling if name == "C" else transport.fold_raw_projection
                lift = transport.lift_raw_coupling if name == "C" else transport.lift_raw_projection
                folded, lifted[name] = fold(g), lift(local)
                measurements[name] = {"fold_relative_error": _relative(folded, local),
                                      "lift_relative_error": _relative(lifted[name], g),
                                      "fold_error_norm": float(np.linalg.norm(folded-local)),
                                      "fold_operation_scale": float(np.linalg.norm(folded)+np.linalg.norm(local)),
                                      "lift_error_norm": float(np.linalg.norm(lifted[name]-g)),
                                      "lift_operation_scale": float(np.linalg.norm(lifted[name])+np.linalg.norm(g))}
                defects.extend((measurements[name]["fold_relative_error"], measurements[name]["lift_relative_error"]))
            gC, gD = (global_vectors[stage][name][global_rows] for name in ("C", "D"))
            reference = float(np.linalg.norm(gC)*np.linalg.norm(gD)/ge.normalization_h)
            bound = _rank_one_loss_bound(lifted["C"], lifted["D"], gC, gD, ge.normalization_h)
            relative = bound/reference if reference else (0.0 if bound == 0 else float("inf"))
            measurements.update(lifted_rank_one_bound=bound, lifted_rank_one_relative_bound=relative)
            stage_max[stage] = max(stage_max[stage], relative)
            defects.append(relative)
            row["stages"][stage] = measurements
        K, H, h = metadata.replication_count, float(ge.normalization_h), float(le.normalization_h)
        row["H"] = {"global": H, "local": h, "replication_count": K, "sqrtK": float(np.sqrt(K)),
                    "global_over_K_relative_error": abs(H/K-h)/h,
                    "packet_global_H_relative_error": abs(float(gp["original_plane_H"])-H)/H,
                    "packet_local_H_relative_error": abs(float(lp["local_plane_H"])-h)/h,
                    "packet_original_H_relative_error": abs(float(lp["original_plane_H"])-H)/H}
        defects.extend(value for key, value in row["H"].items() if key.endswith("relative_error"))
        beta = complex(1+(original+1)/533, 0.25)
        gfull = complex(0.7, -0.13-(original+1)/533)
        lower_global = global_vectors["raw"]["D"][global_rows]@gx-H*beta/np.sqrt(K)+gfull
        lower_local = local_vectors["raw"]["D"][local_rows]@x-h*beta+gfull/np.sqrt(K)
        lower_defect = _relative(np.asarray(lower_global/np.sqrt(K)), np.asarray(lower_local))
        row["nonzero_lower_dual_rhs"] = {"beta_local": beta, "alpha_global": beta/np.sqrt(K),
                                         "g_global": gfull, "g_local": gfull/np.sqrt(K),
                                         "global_residual": lower_global, "local_residual": lower_local,
                                         "scaled_identity_relative_error": lower_defect}
        defects.append(lower_defect)
        passed = np.isfinite(defects).all() and max(defects) <= TOLERANCE
        row["status"] = "PASS_COMPLETE_MODE_FOLD_LIFT_CUTOFF" if passed else "FAILED_COMPLETE_MODE_FOLD_LIFT_CUTOFF"
        from .fullspace_dtn_action import _jsonable
        from .dtn_boundary_plane_qualification import _failure_diagnostic
        with ledger_path.open("a") as stream:
            stream.write(json.dumps(_jsonable(_failure_diagnostic(row)), separators=(",", ":"), allow_nan=False)+"\n")
        if not passed:
            event("direct_complete_mode_fold_failure", row)
            raise ValueError("complete alias/raw/stored C/D/H/lower-RHS fold/lift failed")
        count += 1
        originals.append(original)
        maximum = max(maximum, max(defects))
    if count != metadata.sector_port_counts[context.twist_index] or len(set(originals)) != count:
        raise ValueError("all physical aliases in the complete sector must be audited exactly once")
    return {"mode_count": count, "original_mode_indices": originals, "ledger": _reference(ledger_path, root),
            "maximum_complete_mode_relative_error": maximum, "rank_one_bounds_by_stage": stage_max,
            "tolerance": TOLERANCE, "raw_and_both_actual_cutoffs_audited": True,
            "complete_DOF_fold_and_lift": True, "single_D_conjugation": True,
            "nonzero_lower_dual_rhs_sqrtK_identity": True}


def _resource_authority(environment):
    """Receipt metadata only; the external supervisor owns the selected limit."""
    memory = environment.get("QUOTIENT_RESEARCH_MEMORY_GIB")
    if memory is None:
        requested = environment.get("QUOTIENT_RESEARCH_WALL_SECONDS")
        if requested is None:
            return "external min(fresh dynamic cap,1.5GiB)/600s/zeroSwap/MPI1/thread1 supervision"
        if requested != "1800" or not 0 < float(environment.get("QUOTIENT_PHASE_WALL_SECONDS", "nan")) <= 1800:
            raise ValueError("fresh X carrier resource metadata requires the exact supervised research budget")
        return "external min(fresh dynamic cap,1.5GiB)/1800s/zeroSwap/MPI1/thread1 supervision"
    contracts = {"X": (2, 1800), "XZ": (3, 4500), "Y": (3, 4500)}
    selected = environment.get("QUOTIENT_RESEARCH_MEMORY_PROFILE")
    if selected not in contracts:
        raise ValueError("fresh resource metadata admits only X2GiB/1800s, XZ3GiB/4500s or Y3GiB/4500s")
    memory_gib, wall_seconds = contracts[selected]
    cap_bytes = memory_gib*1024**3
    expected = {"QUOTIENT_RESEARCH_MEMORY_GIB": str(memory_gib), "QUOTIENT_RESEARCH_MEMORY_PROFILE": selected,
        "QUOTIENT_RESEARCH_MEMORY_STAGE": "solve", "QUOTIENT_RESEARCH_WALL_SECONDS": str(wall_seconds),
        "QUOTIENT_RESEARCH_TREE_CAP_BYTES": str(cap_bytes), "PHYSICAL_WATCHDOG_LAUNCH_CAP_BYTES": str(cap_bytes)}
    if (any(environment.get(name) != value for name, value in expected.items())
            or not 0 < float(environment.get("QUOTIENT_PHASE_WALL_SECONDS", "nan")) <= wall_seconds):
        raise ValueError("fresh resource text requires its exact bound profile/solve/wall supervisor request")
    receipt = json.loads(environment.get("QUOTIENT_RESEARCH_MEMORY_LAUNCH_ADMISSION", "null"))
    if (not isinstance(receipt, dict) or receipt.get("requested_memory_gib") != memory_gib
            or receipt.get("requested_tree_cap_bytes") != cap_bytes
            or receipt.get("required_cap_plus_evidence_reserve_bytes") != cap_bytes + 128*1024**2
            or receipt.get("launch_admission_passed") is not True):
        raise ValueError("fresh resource text requires the actual admitted launch packet")
    return f"external min(fresh dynamic cap,{memory_gib}GiB)/{wall_seconds}s/zeroSwap/MPI1/thread1 supervision"


def build_fresh_direct_carriers(cfg, *, direct_profile, run_directory, save_array,
                                allocation_gate, event=None, shared_template_bank,
                                entity_callback=None, layout_callback=None):
    """Externally supervised X/XZ/Y fresh full/all local setup and raw gates.

    The caller owns the admitted source/ABI/same80 storage bridge, resource
    watchdog, artifact writer and shared bank lifecycle. The returned actions
    remain live for condensed setup, original action/RHS/recovery and checker.
    Failure preserves honest component evidence then releases action owners.
    """
    from .y_orbit_direct_profile import DirectTwoCellProfile, validate_direct_physical_config
    if DirectTwoCellProfile(direct_profile) not in (DirectTwoCellProfile.X, DirectTwoCellProfile.XZ, DirectTwoCellProfile.Y):
        raise ValueError("fresh direct numerical helper admits only X/XZ/Y")
    metadata = validate_direct_physical_config(cfg, direct_profile)
    if not callable(save_array) or not callable(allocation_gate):
        raise TypeError("caller artifact writer and current-resident allocation gate are required")
    if event is None:
        event = lambda stage, facts: None
    elif not callable(event):
        raise TypeError("event must be a callable")
    for callback in (entity_callback, layout_callback):
        if callback is not None and not callable(callback):
            raise TypeError("entity/layout lifecycle callbacks must be callable or None")
    from .y_orbit_transform_bank import YOrbitTransformBank
    if not isinstance(shared_template_bank, YOrbitTransformBank):
        raise TypeError("one existing same80-qualified shared template bank is required")
    root = Path(run_directory).resolve()
    receipt_path = root/"direct_carrier_qualification.json"
    failure_path = root/"failed_direct_carrier_qualification.json"
    if any(path.exists() for path in (receipt_path, failure_path, root/"raw_global", root/"literal_global",
                                    root/"global_components",
                                    *(root/(stem+str(b)) for stem in ("raw_twist_", "literal_twist_")
                                      for b in range(metadata.replication_count)))):
        raise ValueError("fresh direct carriers require a new artifact directory")
    root.mkdir(parents=True, exist_ok=True)
    _gate(allocation_gate, "direct_"+metadata.name+"_pre_import_and_inventory", workspace=128 << 20,
          fresh_only=True, snapshots_reused=False, no_factors=True)
    import numpy as np
    from mpi4py import MPI
    from petsc4py import PETSc
    from .fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels
    from .fullspace_same_mesh_hcurl_pmg_physical import build_same_mesh_physical_action
    from .fullspace_dtn_action import build_dynamic_mode_inventory, build_ordered_mode_manifest
    from .dtn_boundary_plane_qualification import qualify_boundary_plane_bundle, carrier_numeric_identity
    from .y_orbit_quotient_raw_qualification import qualify_quotient_raw_bundle, _actual_discrete_binding
    from .y_orbit_raw_packet_spool import RawModeSpool
    from .y_orbit_quotient_context import build_two_cell_assembly_config, build_two_cell_quotient_context, PHYSICAL_GENERATOR_SHA256
    from .task40extra_y_orbit_reference import collect_y_orbit_entities, build_y_orbit_layout
    from .y_orbit_two_cell_transport import TwoCellNativeTransport
    if int(MPI.COMM_WORLD.size) != 1 or PETSc.ScalarType != np.complex128:
        raise ValueError("admitted MPI1/complex128 ABI required")
    result = DirectCarrierQualification()
    arrays, sector_receipts, raw_folds, cells, literal_manifests = {}, [], [], [], []
    base = {"schema": SCHEMA, "profile": metadata.identity(), "PDE_solved": False,
            "factor_count": 0, "official_results": False, "full_case_pass": False,
            "snapshots_reused": False, "fresh_primary_and_literal_forms": True,
            "full_Ny_reference_matrices_created": False,
            "qualification_source_sha256": _sha(__file__), "tolerance": TOLERANCE}
    gate = "fresh original physical inventory"
    try:
        inventory = build_dynamic_mode_inventory(cfg)
        result.global_mode_inventory = inventory
        modes, rows, manifest = inventory
        ordered_rows, encoded, actual_manifest = build_ordered_mode_manifest(modes, cfg)
        keys = tuple((index, mode.side, mode.m, mode.n, mode.polarization) for index, mode in enumerate(modes))
        if (manifest != actual_manifest or manifest != PHYSICAL_GENERATOR_SHA256
                or len(modes) != 532 or len(set(keys)) != 532
                or tuple(sum(int(mode.n) % metadata.ny == q for mode in modes) for q in range(metadata.ny)) != metadata.q_port_counts):
            raise ValueError("fresh unchanged global physical 532-mode inventory required")
        base["global_inventory"] = {"physical_generator_manifest_sha256": manifest,
                                    "ordered_mode_keys": keys, "q_port_counts": metadata.q_port_counts}
        def spool(name):
            return RawModeSpool(root/name, save_array=save_array, allocation_gate=allocation_gate,
                                root_directory=root, direct_profile=direct_profile)
        result.global_spool = spool("raw_global")
        gate = "fresh original mesh/MPC/volume/carrier"
        _gate(allocation_gate, "direct_global"+str(metadata.cell_count)+"_mesh_MPC_constructor", payload=16 << 20, workspace=128 << 20)
        setup = _build_same_mesh_levels(cfg, MPI.COMM_SELF, (4,), include_positive_coefficients=False)
        _gate(allocation_gate, "direct_global"+str(metadata.cell_count)+"_physical_volume_carrier_constructor", payload=64 << 20, workspace=256 << 20)
        result.global_bundle = build_same_mesh_physical_action(setup, cfg, 4, mode_inventory=inventory,
            dtn_phase_gauge="boundary_plane", verify_dtn_quadrature=True, raw_mode_observer=result.global_spool.observe,
            raw_observer_profile=metadata.name)
        global_identity = carrier_numeric_identity(result.global_bundle["dtn_action"].carrier)
        _actual_discrete_binding(result.global_bundle, result.global_bundle["dtn_action"].carrier)
        gate = "fresh global boundary-plane primary/literal component qualification"
        global_record = root/"global_components"/"live_component_receipt.json"
        global_literals = DirectLiteralModeSpool(root/"literal_global", root=root,
            original_mode_indices=range(532), original_mode_keys=[key[1:] for key in keys],
            ownership_rows=metadata.storage_rows, physical_manifest=manifest,
            context_sha=result.global_bundle["assembly_context_sha256"], quotient_context=None,
            save_array=save_array, allocation_gate=allocation_gate)
        _gate(allocation_gate, "direct_global"+str(metadata.cell_count)+"_live_boundary_literal_oracle", payload=16 << 20,
              workspace=128 << 20, original_Gauss23_144_required=True, no_factors=True)
        global_receipt = qualify_boundary_plane_bundle(result.global_bundle, record_path=global_record,
            expected_physical_manifest=manifest, expected_ordered_keys=keys, direct_profile=direct_profile,
            literal_mode_observer=global_literals.observe)
        literal_manifests.append(global_literals.require_complete())
        event("direct_fresh_global_component_complete", {"status": global_receipt["status"], **_reference(global_record, root)})
        axes = dict(zip(("x", "y", "z"), metadata.global_axes, strict=True))
        _gate(allocation_gate, "direct_global"+str(metadata.cell_count)+"_shared_complete_entities", payload=16 << 20,
              workspace=128 << 20, full_Ny_F_Q_created=False)
        result.global_entities = collect_y_orbit_entities(setup["spaces"][4], setup["floquets"][4], cfg, axes,
                                                         transform_bank=shared_template_bank)
        if entity_callback is not None:
            entity_callback("full", result.global_entities, setup, cfg, axes, result.global_bundle)
        _export_inventory(result.global_bundle, result.global_entities, prefix="direct_global", metadata=metadata,
                          local=False, root=root, save_array=save_array, allocation_gate=allocation_gate, inventory=arrays)
        local_cfg = build_two_cell_assembly_config(cfg, direct_profile=direct_profile)
        for b in range(metadata.replication_count):
            gate = "fresh local"+str(metadata.local_cell_count)+" twist "+str(b)
            context = build_two_cell_quotient_context(cfg, local_cfg, inventory, twist_index=b, direct_profile=direct_profile)
            local_spool = spool("raw_twist_"+str(b))
            result.local_spools.append(local_spool)
            _gate(allocation_gate, "direct_twist_"+str(b)+"_local"+str(metadata.local_cell_count)+"_MPC_constructor", payload=16 << 20, workspace=128 << 20,
                  explicit_x_y_corner_wrap=True)
            local_setup = _build_same_mesh_levels(local_cfg, MPI.COMM_SELF, (4,), include_positive_coefficients=False,
                                                 research_phase_override=context.phase_override)
            _gate(allocation_gate, "direct_twist_"+str(b)+"_physical_volume_carrier_constructor", payload=64 << 20,
                  workspace=256 << 20, no_local_incident_RHS=True)
            local = build_same_mesh_physical_action(local_setup, local_cfg, 4, mode_inventory=inventory,
                physical_cfg=cfg, quotient_context=context, dtn_phase_gauge="boundary_plane",
                verify_dtn_quadrature=True, raw_mode_observer=local_spool.observe, raw_observer_profile=metadata.name)
            result.local_bundles.append(local)
            prefix = "direct_twist_"+str(b)
            cells.append(_actual_cells(setup, local_setup, metadata, root=root, prefix=prefix,
                                      save_array=save_array, allocation_gate=allocation_gate, inventory=arrays))
            gate = "fresh literal local raw oracle twist "+str(b)
            record = root/("raw_twist_"+str(b))/"raw_port_receipt.json"
            local_literals = DirectLiteralModeSpool(root/("literal_twist_"+str(b)), root=root,
                original_mode_indices=context.original_mode_indices, original_mode_keys=context.original_mode_keys,
                ownership_rows=metadata.local_storage_rows, physical_manifest=manifest,
                context_sha=local["assembly_context_sha256"], quotient_context=context,
                save_array=save_array, allocation_gate=allocation_gate)
            _gate(allocation_gate, prefix+"_live_literal_raw_oracle", payload=16 << 20, workspace=128 << 20,
                  original_Gauss23_144_required=True, no_factors=True)
            receipt = qualify_quotient_raw_bundle(local, raw_mode_packets=local_spool.packets(), record_path=record,
                expected_physical_manifest=manifest, expected_global_ordered_keys=keys, direct_profile=direct_profile,
                literal_mode_observer=local_literals.observe)
            literal_manifests.append(local_literals.require_complete())
            sector_receipts.append({"twist_index": b, "status": receipt["status"], **_reference(record, root)})
            event("direct_fresh_local_raw_component_complete", sector_receipts[-1])
            local_axes = dict(zip(("x", "y", "z"), context.local_axes, strict=True))
            _gate(allocation_gate, prefix+"_shared_complete_entities", payload=16 << 20, workspace=128 << 20)
            entities = collect_y_orbit_entities(local_setup["spaces"][4], local_setup["floquets"][4], local_cfg,
                                               local_axes, transform_bank=shared_template_bank)
            result.local_entities.append(entities)
            if entity_callback is not None:
                entity_callback("twist_"+str(b), entities, local_setup, local_cfg, local_axes, local)
            _gate(allocation_gate, prefix+"_complete_local_R_F_Q_layout", payload=64 << 20, workspace=192 << 20,
                  full_Ny_reference_matrices_created=False)
            layout = build_y_orbit_layout(local_setup["spaces"][4], local_setup["floquets"][4], local_cfg, local_axes,
                wrap_phase_y=context.tau, cell_phase_y=context.eta, entities=entities, transform_bank=shared_template_bank)
            result.local_layouts.append(layout)
            if layout_callback is not None:
                layout_callback("twist_"+str(b), layout, entities)
            result.transports.append(TwoCellNativeTransport(result.global_entities, entities, twist_index=b, eta=context.eta,
                global_phase=cfg.floquet_phase_y, global_ky=cfg.ky, global_period_y=cfg.period_y, direct_profile=direct_profile))
            _export_inventory(local, entities, prefix=prefix, metadata=metadata, local=True, root=root,
                              save_array=save_array, allocation_gate=allocation_gate, inventory=arrays)
            _gate(allocation_gate, prefix+"_mode_mapping_export", payload=len(context.original_mode_indices)*16, workspace=1 << 20)
            for suffix, values in (("original_mode_indices", context.original_mode_indices), ("branch_indices", context.local_branch_indices)):
                _export(prefix+"_"+suffix, np.asarray(values, dtype=np.int64), root=root, save_array=save_array,
                        allocation_gate=allocation_gate, inventory=arrays)
            gate = "complete original/local532 raw/stored cutoff fold/lift twist "+str(b)
            raw_folds.append(_fold_modes(result, b, metadata=metadata, root=root, save_array=save_array,
                                         allocation_gate=allocation_gate, event=event, arrays=arrays))
        union = [i for receipt in raw_folds for i in receipt["original_mode_indices"]]
        if sorted(union) != list(range(532)) or len(set(union)) != 532:
            raise ValueError("twists must cover every original physical alias exactly once")
        if carrier_numeric_identity(result.global_bundle["dtn_action"].carrier) != global_identity:
            raise ValueError("fresh live global carrier mutated during qualification")
        from os import environ
        result.qualification_receipt = {**base, "status": PASS_STATUS,
            "global_component_receipt": _reference(global_record, root), "local_raw_receipts": sector_receipts,
            "literal_mode_manifests": literal_manifests,
            "raw_spool_manifests": [_reference(item.manifest_path, root) for item in (result.global_spool, *result.local_spools)],
            "cell_metric_material_cover": cells, "complete_mode_fold_lift": raw_folds,
            "original532_alias_union_exactly_once": True, "arrays": arrays,
            "global_carrier_identity_before": global_identity,
            "global_carrier_identity_after": carrier_numeric_identity(result.global_bundle["dtn_action"].carrier),
            "local_carrier_identities": [carrier_numeric_identity(bundle["dtn_action"].carrier) for bundle in result.local_bundles],
            "resource_authority": _resource_authority(environ),
            "deferred_gates": ["complete original contribution/operator audit", "all-q prefactor CSR and resources",
                               "q factors", "full original solve/recovery/residual/output qualification"]}
        _write(receipt_path, result.qualification_receipt)
        event("direct_fresh_carrier_qualification_complete", {"status": PASS_STATUS, **_reference(receipt_path, root)})
        return result
    except Exception as error:
        _write(failure_path, {**base, "status": "FAILED_DIRECT_FRESH_CARRIER_COMPONENTS", "gate": gate,
                             "exception_type": type(error).__name__, "exception": str(error),
                             "arrays": arrays, "local_raw_receipts": sector_receipts,
                             "completed_literal_mode_manifests": literal_manifests,
                             "completed_mode_fold_lift": raw_folds, "cell_metric_material_cover": cells})
        result.destroy()
        raise
