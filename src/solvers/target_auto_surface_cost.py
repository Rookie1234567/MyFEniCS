"""Staged, explicitly gated original-target AUTO top/x component diagnostic.

Importing this module is NumPy/config only. Neither API is called at import.
The metadata API uses the production generator and physical manifest builder;
the surface API requires a verified Library metadata seal before any mesh.
There is no carrier, dense H, volume form, factor, PDE, or output qualification.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import time
from types import SimpleNamespace
from typing import Any

import numpy as np

SCHEMA = "task40extra.target-auto-surface-cost.v1"
SOURCE_BASE = "d6ae70a53ba9b0f2c8c25a5144f17e78f7579d44"
SI_TARGET = complex(0.99988517036884961, 4.3236152269189515e-06)
AXES = ((0.0, 16.5, 33.5, 50.0), (0.0, 12.5, 25.0), (-10.0, 0.0, 120.0, 130.0))
PARTIAL_SCOPE = "original AUTO inventory; selected top/x raw and masked component only"
SOURCE_FILES = (
    "src/common/config_3d.py", "src/common/modes_3d.py",
    "src/solvers/fullspace_dtn_action.py", "src/solvers/dtn_port_3d.py",
    "src/solvers/dtn_boundary_phase_gauge.py", "src/geometry/mesh_builder_3d.py",
    "src/constraints/floquet_3d.py", "src/constraints/floquet_3d_high_order.py",
    "src/constraints/high_order_floquet_trace.py",
)


def jsonable(value):
    if isinstance(value, Mapping):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    if isinstance(value, np.ndarray):
        return jsonable(value.tolist())
    if isinstance(value, np.generic):
        return jsonable(value.item())
    if isinstance(value, complex):
        return {"real": float(value.real), "imag": float(value.imag)}
    return value


def canonical(value):
    return json.dumps(jsonable(value), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def source_binding(repo_root):
    root = Path(repo_root).resolve()
    import src.common.config_3d as module
    if Path(module.__file__).resolve() != root / SOURCE_FILES[0]:
        raise ValueError("configuration import does not belong to selected repository")
    return {"reviewed_base_sha": SOURCE_BASE,
            "repo_root": str(root),
            "production_source_sha256": {name: file_sha256(root/name) for name in SOURCE_FILES},
            "staged_capsule_sha256": file_sha256(__file__)}


def target_config():
    """Explicit target; deliberately never call the 13.5 nm target factory."""
    from src.common.config_3d import SimulationConfig3D
    return SimulationConfig3D(
        case_name="original_target_AUTO_p6_18cell_compiler_fixture",
        stage_case="stage4_block_grating", geometry_kind="rectangular_block_grating",
        geometry_model_variant="original", geometry_identity="target50x25x140_regular",
        lambda0=0.7, n_air=complex(1.0), mu_r=complex(1.0),
        period_x=50.0, period_y=25.0, z_min=-10.0, z_max=130.0,
        air_height=130.0, substrate_thickness=10.0, interface_z=0.0,
        grating_width_x=17.0, grating_width_y=25.0, grating_height=120.0,
        n_substrate=SI_TARGET, n_grating=SI_TARGET,
        substrate_material_label="Si / silicon at lambda0.7nm (fixed target)",
        grating_material_label="Si / silicon at lambda0.7nm (fixed target)",
        cell_notch=None, air_void_box_nm=None, scattering_background="layered",
        use_floquet_xy=True, use_pml=False, pml_top_thickness=0.0, pml_bottom_thickness=0.0,
        incident_theta_deg=89.0, incident_phi_deg=0.0, polarization_kind="s",
        custom_polarization=None, incident_amplitude=complex(1.0),
        nedelec_degree=6, visualization_degree=6, mesh_target_size=140.0,
        mesh_cell_type="hexahedron", mesh_spacing_mode="boundary_fitted",
        mesh_axis_cell_counts=(3, 2, 3), mesh_axis_x_values=AXES[0],
        mesh_axis_y_values=AXES[1], mesh_axis_z_values=AXES[2],
        mesh_axis_z_profile="exact_planes_18cell_boundary_compiler_fixture",
        mesh_plan_id="exact_planes_18cell_boundary_compiler_fixture_not_accuracy_mesh",
        floquet_constraint_mode="auto", stage4_boundary_model="dtn_port",
        stage4_dtn_order_policy="auto_propagating", stage4_dtn_assembly="auxiliary",
        diffraction_zero_order_only=False, diffraction_order_max_m=None,
        diffraction_order_max_n=None, reporting_diffraction_order_max_m=None,
        reporting_diffraction_order_max_n=None,
    )


def _admit(label, buffers, *, allocation_gate, event, **facts):
    if not callable(allocation_gate) or not callable(event):
        raise TypeError("explicit allocation_gate and event callbacks are required")
    if any(isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in buffers.values()):
        raise ValueError("allocation bytes must be nonnegative integers")
    record = {"schema": SCHEMA, "stage": "allocation_before", "label": label,
              "predicted_buffer_bytes": dict(buffers), "predicted_total_bytes": sum(buffers.values()),
              "data_identity": "predicted; native workspace is a conservative allowance", **facts}
    event(record)
    result = allocation_gate(label, record)
    if result is False:
        event({"schema": SCHEMA, "stage": "allocation_denied", "label": label})
        raise MemoryError("allocation gate denied " + label)
    event({"schema": SCHEMA, "stage": "allocation_admitted", "label": label,
           "gate_result": jsonable(result)})
    return record


def mode_key(index, mode):
    # Exact indexed-key construction used by the existing carrier builder.
    return (int(index), str(mode.side), int(mode.m), int(mode.n), str(mode.polarization))


def select_top_modes(modes):
    """At most four actual diffraction tuples, both available polarizations."""
    groups = {}
    for index, mode in enumerate(modes):
        if mode.side == "top":
            groups.setdefault((int(mode.m), int(mode.n)), []).append(index)
    if not groups or (0, 0) not in groups:
        raise ValueError("complete original inventory lacks the incident top tuple")
    first = {key: modes[indices[0]] for key, indices in groups.items()}
    candidates = (
        ("incident00", (0, 0)),
        ("largest_abs_m", min(groups, key=lambda k: (-abs(k[0]), k))),
        ("largest_abs_n", min(groups, key=lambda k: (-abs(k[1]), k))),
        ("smallest_abs_beta", min(groups, key=lambda k: (abs(first[k].beta), k))),
    )
    reasons = {}
    for reason, key in candidates:
        reasons.setdefault(key, []).append(reason)
    indices = tuple(index for key in reasons for index in groups[key])
    if len(reasons) > 4 or len(indices) > 8 or any(len(groups[key]) > 2 for key in reasons):
        raise ValueError("selected component bound exceeded")
    return indices, tuple({"tuple": key, "reasons": labels,
                           "original_mode_indices": tuple(groups[key]),
                           "actual_near_cutoff": bool(first[key].rayleigh_warning),
                           "minimum_abs_beta_is_not_a_cutoff_assertion": True}
                          for key, labels in reasons.items())


def inventory_summary(cfg, modes):
    counts = Counter((str(m.side), "near-cutoff" if m.rayleigh_warning else
                     "propagating" if m.propagating else "evanescent") for m in modes)
    phase = {}
    for side in ("top", "bottom"):
        port_z = cfg.physical_z_max if side == "top" else cfg.physical_z_min
        logs = [-complex(m.k_vector[2]).imag*port_z for m in modes if m.side == side]
        arguments = [complex(m.k_vector[2]).real*port_z for m in modes if m.side == side]
        if logs:
            phase[side] = {"port_z_nm": float(port_z), "global_z_log_abs_min": min(logs),
                           "global_z_log_abs_max": max(logs), "global_z_argument_min": min(arguments),
                           "global_z_argument_max": max(arguments), "centered_boundary_log_abs": 0.0,
                           "bounds_computation_evaluated_exponentials": False}
    return {"fresh_mode_count": len(modes),
            "side_counts": {s: sum(m.side == s for m in modes) for s in ("top", "bottom")},
            "classification_counts": {s: {c: counts[(s, c)] for c in
                ("propagating", "evanescent", "near-cutoff")} for s in ("top", "bottom")},
            "max_abs_m": max(abs(int(m.m)) for m in modes),
            "max_abs_n": max(abs(int(m.n)) for m in modes),
            "max_order": max(max(abs(int(m.m)), abs(int(m.n))) for m in modes),
            "boundary_phase_bounds": phase}


@dataclass(frozen=True)
class InventoryBundle:
    cfg: Any
    modes: tuple
    rows: tuple
    manifest_bytes: bytes
    physical_manifest_sha256: str
    ordered_keys_bytes: bytes
    ordered_keys_sha256: str
    config_sha256: str
    quadrature_degree: int
    summary: dict
    sources: dict


def _original_inventory_key_first(mode_generator, manifest_builder, cfg, keys_sink):
    """Exact two original functions, with persistence before legacy scalar H.

    build_dynamic_mode_inventory is precisely these two function calls. The
    staged seam inserts key persistence between them without monkeypatching,
    changing original generation/selection or duplicating the physical schema.
    """
    modes = tuple(mode_generator(cfg))
    keys = canonical([mode_key(i, mode) for i, mode in enumerate(modes)])
    keys_sink(modes, keys)
    rows, encoded, digest = manifest_builder(modes, cfg)
    return modes, rows, encoded, digest, keys


def _fresh_inventory(*, repo_root, allocation_gate, event, ordered_keys_sink=None):
    cfg = target_config()
    nmax = max(abs(cfg.n_air), abs(cfg.substrate_index))
    mmax = int(np.floor((nmax*cfg.k0 + abs(cfg.kx))*cfg.period_x/(2*np.pi) + 1e-12))
    nmax_order = int(np.floor((nmax*cfg.k0 + abs(cfg.ky))*cfg.period_y/(2*np.pi) + 1e-12))
    upper = 4*(2*mmax+1)*(2*nmax_order+1)
    _admit("complete_original_AUTO_metadata", {
        "mode_objects_and_arrays": upper*4096, "physical_manifest_and_JSON_workspace": upper*12288,
        "ordered_keys_classification_and_Python_workspace": upper*2048,
        "native_import_workspace_allowance": 128 << 20}, allocation_gate=allocation_gate, event=event,
        upper_bound_rectangular_mode_count=upper, auto_enumeration_m_bound=mmax,
        auto_enumeration_n_bound=nmax_order, mesh_calls=0, form_calls=0, jit_calls=0,
        historical_count_asserted=False)
    event({"stage": "original_inventory_generation_started", "schema": SCHEMA})
    from src.common.modes_3d import outgoing_port_modes_3d
    from src.solvers.fullspace_dtn_action import build_ordered_mode_manifest
    from src.solvers.dtn_port_3d import _dtn_surface_quadrature_degree
    started = time.perf_counter()
    def save_keys_before_H(modes, keys):
        event({"schema": SCHEMA, "stage": "complete_original_keys_before_legacy_H",
               "fresh_mode_count": len(modes), "ordered_keys_sha256": sha256(keys),
               "exact_original_generator_and_manifest_functions": True})
        if ordered_keys_sink is not None:
            ordered_keys_sink(modes, keys, cfg)
    modes, rows, encoded, digest, keys = _original_inventory_key_first(
        outgoing_port_modes_3d, build_ordered_mode_manifest, cfg, save_keys_before_H)
    if sha256(encoded) != digest or len(modes) != len(rows):
        raise ValueError("original manifest bytes/hash/count disagree")
    if keys != canonical([mode_key(i, mode) for i, mode in enumerate(modes)]):
        raise ValueError("original generator mode keys changed across legacy manifest construction")
    qdegree = int(_dtn_surface_quadrature_degree(cfg, list(modes)))
    result = InventoryBundle(cfg, tuple(modes), tuple(rows), encoded, str(digest), keys, sha256(keys),
                             sha256(canonical(cfg.as_jsonable())), qdegree,
                             inventory_summary(cfg, modes), source_binding(repo_root))
    event({"schema": SCHEMA, "stage": "original_inventory_complete", **result.summary,
           "quadrature_degree_from_complete_inventory": qdegree, "wall_seconds": time.perf_counter()-started,
           "physical_generator_manifest_sha256": digest, "mesh_calls": 0, "form_calls": 0, "jit_calls": 0})
    return result


def _write_bytes(path, data):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(path)
    return {"path": str(path.resolve()), "bytes": len(data), "sha256": sha256(data)}


def build_metadata_packet(*, repo_root, output_dir, allocation_gate, event):
    """Original target AUTO metadata only. No mesh/space/form construction."""
    root = None
    partial = {"schema": SCHEMA, "status": "METADATA_NOT_COMPLETE", "surface_stage_started": False}
    try:
        _admit("metadata_journal_before_output_creation", {"journal_JSON_and_file_workspace": 4 << 20},
               allocation_gate=allocation_gate, event=event)
        root = Path(output_dir).resolve()
        root.mkdir(parents=True, exist_ok=False)
        partial.update({"cfg_as_jsonable": target_config().as_jsonable(), "sources": source_binding(repo_root)})
        _write_bytes(root/"partial_metadata_record.json", canonical(partial))
        def retain_keys(modes, keys, cfg):
            from src.solvers.dtn_port_3d import _dtn_surface_quadrature_degree
            partial.update({"status": "FULL_ORDERED_KEYS_SAVED_LEGACY_MANIFEST_PENDING",
                            "ordered_keys_artifact": _write_bytes(root/"original_ordered_keys.json", keys),
                            "quadrature_degree_from_complete_inventory": int(_dtn_surface_quadrature_degree(cfg, list(modes))),
                            **inventory_summary(cfg, modes)})
            _write_bytes(root/"partial_metadata_record.json", canonical(partial))
            event({"schema": SCHEMA, "stage": "complete_original_keys_saved_before_legacy_H", **partial})
        bundle = _fresh_inventory(repo_root=repo_root, allocation_gate=allocation_gate, event=event,
                                  ordered_keys_sink=retain_keys)
        selected, reasons = select_top_modes(bundle.modes)
        packet = {"schema": SCHEMA, "status": "METADATA_COMPLETE_SURFACE_NOT_RUN", "scope": PARTIAL_SCOPE,
                  "cfg_as_jsonable": bundle.cfg.as_jsonable(), "config_sha256": bundle.config_sha256,
                  "sources": bundle.sources, **bundle.summary,
                  "physical_generator_manifest_sha256": bundle.physical_manifest_sha256,
                  "original_physical_manifest_sha256": bundle.physical_manifest_sha256,
                  "ordered_keys_sha256": bundle.ordered_keys_sha256,
                  "quadrature_degree_from_complete_inventory": bundle.quadrature_degree,
                  "selected_original_mode_indices": selected, "selection_reasons": reasons,
                  "selected_original_keys": [mode_key(i, bundle.modes[i]) for i in selected],
                  "fixture": {"axis_planes_nm": AXES, "cell_counts": (3, 2, 3), "full3D_hex_cells": 18,
                              "purpose": "boundary/compiler fixture; not an accuracy mesh"},
                  "mesh_calls": 0, "form_calls": 0, "jit_calls": 0,
                  "dense_H_constructed": False, "carrier_constructed": False,
                  "original_manifest_scalar_denominators_use_original_global_phase_exponentials": True,
                  "not_qualified": ["full C/D", "allmode components", "carrier", "volume", "PDE", "outputs"]}
        buffers = {"manifest_output_bytes": len(bundle.manifest_bytes),
                   "keys_output_bytes": len(bundle.ordered_keys_bytes), "packet_JSON_workspace": 4 << 20}
        _admit("metadata_output_before_write", buffers, allocation_gate=allocation_gate, event=event)
        packet["artifacts"] = {
            "physical_manifest": _write_bytes(root/"original_physical_manifest.json", bundle.manifest_bytes),
            "ordered_keys": _write_bytes(root/"original_ordered_keys.json", bundle.ordered_keys_bytes)}
        artifact = _write_bytes(root/"metadata_packet.json", canonical(packet))
        event({"schema": SCHEMA, "stage": "metadata_packet_saved", "artifact": artifact,
               "requires_verified_Library_seal_before_surface": True})
        return {"bundle": bundle, "packet": jsonable(packet), "metadata_packet": artifact}
    except BaseException as error:
        partial.update({"status": "METADATA_PARTIAL_OR_FAILED", "error_type": type(error).__name__, "error": str(error)})
        event({"schema": SCHEMA, "stage": "metadata_partial_or_failed", "error_type": type(error).__name__,
               "error": str(error), "surface_stage_started": False})
        if root is not None:
            _write_bytes(root/"partial_metadata_record.json", canonical(partial))
        raise


def validate_metadata_seal(*, metadata_dir, seal):
    """Require parent-owned Library round-trip receipt, then verify local bytes."""
    if not isinstance(seal, Mapping) or seal.get("library_readback_verified") is not True:
        raise ValueError("metadata Library seal with verified readback is required")
    if not seal.get("library_file_id") or seal.get("library_version") is None:
        raise ValueError("metadata seal lacks exact Library identity/version")
    root = Path(metadata_dir).resolve()
    path = root/"metadata_packet.json"
    if file_sha256(path) != seal.get("metadata_packet_sha256"):
        raise ValueError("metadata packet differs from sealed bytes")
    packet = json.loads(path.read_text())
    if packet.get("status") != "METADATA_COMPLETE_SURFACE_NOT_RUN":
        raise ValueError("metadata packet is not a complete metadata-only packet")
    pairs = (("physical_manifest", "physical_manifest_sha256", "original_physical_manifest.json"),
             ("ordered_keys", "ordered_keys_sha256", "original_ordered_keys.json"))
    for artifact, key, basename in pairs:
        expected = packet["artifacts"][artifact]["sha256"]
        if expected != seal.get(key) or file_sha256(root/basename) != expected:
            raise ValueError("metadata artifact differs from sealed bytes: " + artifact)
    if packet["config_sha256"] != seal.get("config_sha256"):
        raise ValueError("metadata config differs from seal")
    if packet.get("cfg_as_jsonable") is not None and sha256(canonical(packet["cfg_as_jsonable"])) != packet["config_sha256"]:
        raise ValueError("saved full configuration does not reproduce its claimed hash")
    return packet


def component_allocation_facts(rows, ghosts, local_dimension, mpc_width):
    """Admit both live raw Vecs and every later masked/copy/output workspace."""
    n, g, d, w = map(int, (rows, ghosts, local_dimension, mpc_width))
    if n <= 0 or g < 0 or d <= 0 or w <= 0:
        raise ValueError("invalid actual native allocation dimensions")
    return {
        "raw_PETSc_Vecs_two_concurrent": 2*(n+g)*16,
        "raw_numpy_retained_copy": n*16,
        "sparse_rows_values_retained": n*(4+16),
        "mask_abs_max_cutoff_and_native_indices": n*(8+1+8+8+4),
        "component_cache": 0,
        "component_staging_buffers": n*16*2,
        "retained_previous_components": 0,
        "sort_workspace_conservative": n*(8+4+16),
        "output_numpy_and_serialization_workspace": n*(16+4+16),
        "native_assembly_MPC_workspace_allowance": 8*(n+g)*16 + 8*d*w*16,
        "Python_workspace_allowance": 32 << 20,
    }


def reference_action_gate(primary, reference, integral_operation_scales):
    """Independent integral scale alone; no coefficient scale or zero floor."""
    primary = np.asarray(primary, dtype=np.complex128)
    reference = np.asarray(reference, dtype=np.complex128)
    scales = np.asarray(integral_operation_scales, dtype=float)
    if (primary.shape != reference.shape or scales.shape != reference.shape
            or not np.isfinite(primary).all() or not np.isfinite(reference).all()
            or not np.isfinite(scales).all() or np.any(scales < 0)):
        raise ValueError("independent action arrays have inconsistent shape or finite scale")
    try:
        with np.errstate(over="raise", invalid="raise"):
            error = np.abs(primary-reference)
    except FloatingPointError as error:
        raise ValueError("independent action difference is unrepresentable") from error
    if not np.isfinite(error).all():
        raise ValueError("independent action difference is nonfinite")
    passed = np.where(scales == 0, error == 0, error <= 1e-10*scales)
    return {"passed": bool(np.all(passed)), "entry_passed": passed, "absolute_error": error,
            "operation_scale": scales, "operation_scale_definition": "sum(w*abs(phase)*abs(expanded_field_x))",
            "relative_limit": 1e-10, "exact_zero_rule": True}


def _bare_fixture(cfg, *, allocation_gate, event):
    _admit("exact_18cell_mesh_p6_space_MPC", {
        "mesh_space_MPC_and_native_constructor_workspace_allowance": 384 << 20},
        allocation_gate=allocation_gate, event=event, fixture_cells=18, degree=6,
        volume_form_calls=0, jit_calls=0,
        constructors="existing structured hexa, tags, N1curl space, explicit double Floquet MPC")
    from mpi4py import MPI
    from petsc4py import PETSc
    from basix.ufl import element
    from dolfinx import default_real_type, fem
    from src.constraints.floquet_3d import build_double_floquet_mpc
    from src.geometry.mesh_builder_3d import _stage4_axis_plan, _structured_hexa_mesh, _mark_boundary_facets, _mark_cells
    if MPI.COMM_WORLD.size != 1 or np.dtype(PETSc.ScalarType) != np.dtype(np.complex128):
        raise ValueError("surface component stage requires MPI1 complex128")
    plan = _stage4_axis_plan(cfg, 1)  # Original pure geometry/explicit-axis guards.
    if (plan.mesh_cells_resolved != (3, 2, 3) or not plan.material_plane_alignment["all_aligned"]
            or not all(np.array_equal(a, np.asarray(b)) for a, b in
                       zip((plan.x_values, plan.y_values, plan.z_values), AXES))):
        raise ValueError("production axis guards did not reproduce the exact compiler fixture")
    msh = _structured_hexa_mesh(MPI.COMM_SELF, plan.x_values, plan.y_values, plan.z_values,
                                preserve_input_partition=False)
    facet_tags, _ = _mark_boundary_facets(msh, cfg)
    mesh_data = SimpleNamespace(mesh=msh, facet_tags=facet_tags, cell_tags=_mark_cells(msh, cfg))
    V = fem.functionspace(msh, element("N1curl", msh.basix_cell(), 6, dtype=default_real_type))
    floquet = build_double_floquet_mpc(V, mesh_data, cfg)
    if msh.topology.index_map(3).size_local != 18 or V.element.space_dimension != 882:
        raise ValueError("actual fixture is not the exact 18-cell p6/882 full3D element")
    for axis, expected in enumerate(AXES):
        if not np.array_equal(np.unique(msh.geometry.x[:, axis]), np.asarray(expected)):
            raise ValueError("actual mesh axis differs from exact fixture")
    event({"schema": SCHEMA, "stage": "exact_fixture_complete", "cells": 18,
           "local_element_dimension": 882, "degree": 6, "volume_form_calls": 0, "jit_calls": 0})
    return V, mesh_data, floquet


def _native_states(V, mpc, *, allocation_gate, event):
    from dolfinx import fem
    n = int(V.dofmap.index_map.size_local)*int(V.dofmap.index_map_bs)
    g = int(V.dofmap.index_map.num_ghosts)*int(V.dofmap.index_map_bs)
    if g != 0 or int(V.dofmap.index_map_bs) != 1:
        raise ValueError("diagnostic requires serial scalar native storage without ghosts")
    _admit("three_MPC_consistent_native_states", {
        "independent_states": 3*n*16, "native_fields": 3*(n+g)*16,
        "state_construction_workspace": 4*n*16, "MPC_backsubstitution_allowance": 8*n*16},
        allocation_gate=allocation_gate, event=event, native_storage_rows=n, state_count=3)
    states = np.empty((n, 3), dtype=np.complex128)
    rng = np.random.default_rng(61811)
    states[:, 0] = rng.standard_normal(n)+1j*rng.standard_normal(n)
    rows = np.arange(n, dtype=np.float64)
    states[:, 1] = np.cos(rows*0.017)+1j*np.sin(rows*0.031)
    states[:, 2] = ((rows % 7)-3)+1j*((rows % 11)-5)
    slaves = np.asarray(mpc.slaves, dtype=np.int64)
    states[slaves] = 0
    fields = []
    for j in range(3):
        field = fem.Function(V, name=f"component_reference_native_state_{j}")
        field.x.array[:] = states[:, j]
        field.x.scatter_forward()
        mpc.homogenize(field)
        mpc.backsubstitution(field)
        field.x.scatter_forward()
        fields.append(field)
    return states, tuple(fields)


def _save_array(root, name, array):
    path = root/(name+".npy")
    np.save(path, array, allow_pickle=False)
    return {"path": str(path), "bytes": path.stat().st_size,
            "shape": list(array.shape), "dtype": str(array.dtype), "sha256": file_sha256(path)}


def _copy_pinned_file(source, destination, expected_sha256):
    """Stream already verified compiled bytes without a file-sized RAM copy."""
    source, destination = Path(source), Path(destination)
    temporary = destination.with_suffix(destination.suffix+".tmp")
    digest, count = hashlib.sha256(), 0
    with source.open("rb") as reader, temporary.open("wb") as writer:
        for block in iter(lambda: reader.read(1 << 20), b""):
            writer.write(block)
            digest.update(block)
            count += len(block)
    if digest.hexdigest() != expected_sha256:
        raise ValueError("compiled file bytes changed before evidence persistence")
    temporary.replace(destination)
    return {"path": str(destination), "source_path": str(source), "bytes": count,
            "sha256": digest.hexdigest()}


def run_surface_stage(*, repo_root, metadata_dir, metadata_seal, output_dir, cache_dir,
                      allocation_gate, event, reference_helper):
    """Bounded production form and selected modes; explicitly requires a seal."""
    stage = "metadata_seal"
    record = {"schema": SCHEMA, "scope": PARTIAL_SCOPE, "status": "PARTIAL_NOT_RUN",
              "carrier_constructed": False, "dense_H_constructed": False,
              "volume_form_calls": 0, "factor_calls": 0, "PDE_calls": 0,
              "qualified_full_C_D_or_allmode_or_outputs": False, "selected_components": []}
    root = None
    try:
        packet = validate_metadata_seal(metadata_dir=metadata_dir, seal=metadata_seal)
        if not callable(reference_helper):
            raise TypeError("independent higher-order public Function.eval reference helper is required")
        event({"schema": SCHEMA, "stage": "metadata_Library_seal_verified", "seal": dict(metadata_seal)})
        stage = "fresh_inventory_binding"
        bundle = _fresh_inventory(repo_root=repo_root, allocation_gate=allocation_gate, event=event)
        if (bundle.physical_manifest_sha256 != packet["original_physical_manifest_sha256"]
                or bundle.ordered_keys_sha256 != packet["ordered_keys_sha256"]
                or bundle.config_sha256 != packet["config_sha256"]
                or canonical(bundle.cfg.as_jsonable()) != canonical(packet["cfg_as_jsonable"])
                or bundle.manifest_bytes != (Path(metadata_dir)/"original_physical_manifest.json").read_bytes()
                or bundle.ordered_keys_bytes != (Path(metadata_dir)/"original_ordered_keys.json").read_bytes()
                or bundle.sources != packet["sources"]
                or bundle.quadrature_degree != packet["quadrature_degree_from_complete_inventory"]):
            raise ValueError("fresh original target inventory differs from sealed metadata")
        selected, reasons = select_top_modes(bundle.modes)
        if list(selected) != packet["selected_original_mode_indices"]:
            raise ValueError("fresh selected indices differ from sealed full inventory")
        reference_path = Path(reference_helper.__code__.co_filename).resolve()
        reference_sha = file_sha256(reference_path)
        _admit("surface_reference_source_identity_before_mesh", {"source_hash_workspace": 1 << 20},
               allocation_gate=allocation_gate, event=event, reference_source_path=str(reference_path),
               reference_source_sha256=reference_sha,
               phase_specific_reference_identity_must_match_outer_reviewed_source_receipt=True)
        record.update({"metadata_seal": dict(metadata_seal), "physical_manifest_sha256": bundle.physical_manifest_sha256,
                       "ordered_keys_sha256": bundle.ordered_keys_sha256, "config_sha256": bundle.config_sha256,
                       "actual_reference_source_path": str(reference_path),
                       "actual_reference_source_sha256": reference_sha,
                       "cfg_as_jsonable": bundle.cfg.as_jsonable(), "sources": bundle.sources,
                       "selected_original_mode_indices": selected, "selection_reasons": reasons, **bundle.summary})
        root = Path(output_dir).resolve()
        root.mkdir(parents=True, exist_ok=False)
        _write_bytes(root/"partial_surface_record.json", canonical(record))
        cache = Path(cache_dir).resolve()
        cache.mkdir(parents=True, exist_ok=False)
        if any(cache.iterdir()):
            raise ValueError("dedicated primary JIT cache must be empty")
        stage = "fixture"
        V, mesh_data, floquet = _bare_fixture(bundle.cfg, allocation_gate=allocation_gate, event=event)
        record["fixture_complete"] = True
        _write_bytes(root/"partial_surface_record.json", canonical(record))
        mpc = floquet.mpc
        n = int(V.dofmap.index_map.size_local)
        g = int(V.dofmap.index_map.num_ghosts)
        coeff, offsets = mpc.coefficients()
        width = max(1, int(np.max(np.diff(np.asarray(offsets)), initial=0)))
        stage = "primary_compile"
        _admit("single_production_top_x_form_compile", {
            "compiler_table_native_workspace_allowance_not_proven_bound": 1536 << 20,
            "Gauss_loaded_kernel_and_Constant_pack_identity_allowance": 128 << 20},
            allocation_gate=allocation_gate, event=event, quadrature_degree=bundle.quadrature_degree,
            cache_dir=str(cache), compiler_options=["-O2"], primary_form_count=1,
            unknown_large_FFCx_tables_may_controlled_stop=True)
        from src.solvers.dtn_port_3d import _ReusableSurfaceComponentAssembler
        from src.solvers.dtn_boundary_phase_gauge import build_gauge_assembly_context
        started = time.perf_counter()
        assembler = _ReusableSurfaceComponentAssembler(
            V, mesh_data, bundle.cfg.tags.z_max, 0, quadrature_degree=bundle.quadrature_degree,
            jit_options={"cache_dir": str(cache), "cffi_extra_compile_args": ["-O2"]},
            boundary_reference_z=float(bundle.cfg.physical_z_max), verify_compiled_gauss=True)
        record["primary_compile_wall_seconds"] = time.perf_counter()-started
        record["primary_compiled_gauss_loaded_binary_Constant_pack"] = jsonable(assembler.compiled_gauss_identity)
        _write_bytes(root/"partial_surface_record.json", canonical(record))
        event({"schema": SCHEMA, "stage": "single_primary_compile_complete",
               "wall_seconds": record["primary_compile_wall_seconds"], "primary_form_count": 1,
               "identity": record["primary_compiled_gauss_loaded_binary_Constant_pack"]})
        stage = "primary_compiled_file_persistence"
        kernel = record["primary_compiled_gauss_loaded_binary_Constant_pack"]["loaded_kernel"]
        c_path, binary_path = Path(kernel["module_bound_C_path"]), Path(kernel["module_path"])
        _admit("primary_generated_C_and_loaded_binary_output", {
            "streamed_copy_workspace": 1 << 20, "Python_native_file_IO_allowance": 1 << 20},
            allocation_gate=allocation_gate, event=event,
            output_bytes=c_path.stat().st_size+binary_path.stat().st_size,
            generated_C_bytes=c_path.stat().st_size, loaded_binary_bytes=binary_path.stat().st_size)
        compiled_root = root/"compiled_primary"
        compiled_root.mkdir()
        record["primary_compiled_artifacts"] = {
            "generated_C": _copy_pinned_file(c_path, compiled_root/c_path.name, kernel["module_bound_C_sha256"]),
            "loaded_binary": _copy_pinned_file(binary_path, compiled_root/binary_path.name, kernel["binary_sha256"])}
        _write_bytes(root/"partial_surface_record.json", canonical(record))
        stage = "native_identity"
        _admit("exact_native_mesh_element_MPC_identity", {
            "native_element_coefficients_and_identity_workspace": 128 << 20},
            allocation_gate=allocation_gate, event=event, native_storage_rows=n, mpc_max_expansion_width=width)
        record["native_discrete_identity"] = jsonable(build_gauge_assembly_context(
            V, mesh_data, mpc, bundle.cfg, bundle.quadrature_degree, {("top", 0): assembler}))
        _write_bytes(root/"partial_surface_record.json", canonical(record))
        stage = "native_states"
        states, fields = _native_states(V, mpc, allocation_gate=allocation_gate, event=event)
        record["state_identity"] = {"seed": 61811, "labels": ["complex_random", "row_trigonometric", "row_modular"],
                                    "independent_slaves_zero": True, "native_fields_backsubstituted": True}
        record["state_artifacts"] = {"independent_states": _save_array(root, "independent_states", states)}
        _admit("small_selected_contraction_outputs", {"three_contractions_and_scales": len(selected)*3*16*8},
               allocation_gate=allocation_gate, event=event)
        raw_contractions = np.empty((len(selected), 3), dtype=np.complex128)
        masked_contractions = np.empty_like(raw_contractions)
        primary_operation_scales = np.empty((len(selected), 3), dtype=float)
        for j, index in enumerate(selected):
            stage = f"selected_component_{index}"
            mode = bundle.modes[index]
            admitted = _admit(stage, component_allocation_facts(n, g, int(V.element.space_dimension), width),
                              allocation_gate=allocation_gate, event=event, original_mode_index=int(index),
                              original_mode_key=mode_key(index, mode), native_storage_rows=n,
                              ghost_rows=g, mpc_max_expansion_width=width, retained_components_live=0)
            vec = None
            started = time.perf_counter()
            try:
                vec = assembler.assemble_raw_mpc_vector(mode, mpc)
                if tuple(vec.getOwnershipRange()) != (0, n):
                    raise ValueError("raw Vec ownership differs from native serial storage")
                raw = np.asarray(vec.getArray(readonly=True), dtype=np.complex128).copy()
                rows, values = assembler.assemble_entries(mode, mpc)  # Existing cutoff, unchanged.
                if not np.isfinite(raw).all() or not np.isfinite(values).all():
                    raise FloatingPointError("selected component contains nonfinite coefficients")
                for k in range(3):
                    raw_contractions[j, k] = np.vdot(states[:, k], raw)
                    masked_contractions[j, k] = np.vdot(states[rows, k], values)
                    primary_operation_scales[j, k] = np.sum(np.abs(states[:, k])*np.abs(raw))
                cutoff = max(1e-30, 1e-13*float(np.max(np.abs(raw), initial=0.0)))
                removed = np.abs(raw) <= cutoff
                if (not np.array_equal(rows, np.flatnonzero(~removed))
                        or not np.array_equal(values, raw[rows])):
                    raise ValueError("existing masked vector differs from unchanged cutoff applied to repeated raw assembly")
                item = {"original_mode_index": int(index), "original_mode_key": mode_key(index, mode),
                        "physical_row": jsonable(bundle.rows[index]), "actual_near_cutoff": bool(mode.rayleigh_warning),
                        "actual_abs_beta": float(abs(mode.beta)), "allocation": admitted,
                        "raw_norm": float(np.linalg.norm(raw)), "masked_norm": float(np.linalg.norm(values)),
                        "cutoff": cutoff, "cutoff_removed_l2": float(np.linalg.norm(raw[removed])),
                        "cutoff_removed_max_abs": float(np.max(np.abs(raw[removed]), initial=0.0)),
                        "raw_nonzero_entries": int(np.count_nonzero(raw)), "masked_entries": len(rows),
                        "existing_mask_equals_raw_unchanged_cutoff": True,
                        "raw_contractions": raw_contractions[j], "masked_contractions": masked_contractions[j],
                        "cutoff_contraction_loss": raw_contractions[j]-masked_contractions[j],
                        "primary_operation_scales": primary_operation_scales[j],
                        "artifacts": {"raw": _save_array(root, f"mode_{index}_top_x_raw", raw),
                                      "masked_rows": _save_array(root, f"mode_{index}_top_x_masked_rows", rows),
                                      "masked_values": _save_array(root, f"mode_{index}_top_x_masked_values", values)},
                        "wall_seconds": time.perf_counter()-started}
                record["selected_components"].append(jsonable(item))
                event({"schema": SCHEMA, "stage": "selected_component_saved", **jsonable(item)})
                del raw, rows, values, removed
            finally:
                if vec is not None:
                    vec.destroy()
            _write_bytes(root/"partial_surface_record.json", canonical(record))
        stage = "independent_reference"
        reference = reference_helper(
            V=V, mesh_data=mesh_data, mpc=mpc, cfg=bundle.cfg,
            selected_modes=tuple(bundle.modes[i] for i in selected), selected_indices=selected,
            native_fields=fields, independent_states=states, quadrature_degree=bundle.quadrature_degree,
            allocation_gate=allocation_gate, event=event, output_dir=root)
        record["independent_reference"] = jsonable(reference["record"])
        arrays = reference["arrays"]
        ref = np.asarray(arrays["contractions_degree_plus16"], dtype=np.complex128)
        scales = np.asarray(arrays["operation_scales_degree_plus16"], dtype=float)
        if (ref.shape != raw_contractions.shape or scales.shape != ref.shape
                or not np.isfinite(ref).all() or not np.isfinite(scales).all() or np.any(scales < 0)):
            raise ValueError("independent reference shape/finite scale differs from selected/native states")
        # The declared integral scale alone governs acceptance. Coefficient-space
        # scale remains a diagnostic and cannot relax the independent action gate.
        record["raw_vs_public_eval_reference"] = reference_action_gate(raw_contractions, ref, scales)
        record["contraction_artifacts"] = {name: _save_array(root, name, value) for name, value in
            (("primary_raw_contractions", raw_contractions), ("primary_masked_contractions", masked_contractions),
             ("primary_operation_scales", primary_operation_scales), *arrays.items())}
        reference_converged = reference["record"].get("reference_convergence_pass") is True
        record["status"] = ("SELECTED_TOP_X_COMPONENT_COMPLETE" if
                            record["raw_vs_public_eval_reference"]["passed"] and reference_converged
                            else "SELECTED_TOP_X_REFERENCE_FAILED")
        record["scope_is_partial"] = True
        artifact = _write_bytes(root/"surface_record.json", canonical(record))
        event({"schema": SCHEMA, "stage": "surface_terminal_saved", "status": record["status"], "artifact": artifact})
        return {"record": jsonable(record), "surface_record": artifact}
    except BaseException as error:
        record.update({"status": "PARTIAL_FAILED_OR_CONTROLLED_STOP", "stopped_stage": stage,
                       "error_type": type(error).__name__, "error": str(error)})
        event({"schema": SCHEMA, "stage": "surface_partial_or_failed", **jsonable(record)})
        if root is not None:
            _write_bytes(root/"partial_surface_record.json", canonical(record))
        raise
