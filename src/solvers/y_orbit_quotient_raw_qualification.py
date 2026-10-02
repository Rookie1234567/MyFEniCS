"""Independent literal raw-port audit of a supplied p4 two-cell carrier.

This opt-in research audit consumes the primary observer's current-mode
packet stream. It owns eight literal forms and small FE vectors, never a
primary builder, physical-mode generator, factor, physical RHS, or PDE solve.
External admission is required before calling the numerical entry point.
"""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
import hashlib
import json

import numpy as np

from .dtn_boundary_phase_gauge import (
    GLOBAL_Z, BOUNDARY_PLANE, _array_signature,
    compiled_surface_quadrature_identity,
)
from .dtn_boundary_plane_qualification import (
    _relative, _failure_diagnostic, _qualification_degree_profile,
    _check_loaded_primary_provenance, carrier_numeric_identity,
)


RAW_PACKET_SCHEMA = "task40extra.dtn-raw-mode-observer.research.v1"
AUDIT_SCHEMA = "task40extra.y-orbit-quotient-raw-port-audit.v1"
PASS_STATUS = "PASS_QUOTIENT_RAW_PORT_AUDIT_ONLY"
SECTOR_COUNTS = (228, 304)
FIXED_TOLERANCE = 1e-10
FIXED_SEED = 4053202
ABSOLUTE_SPARSE_FLOOR = 1e-30
RELATIVE_SPARSE_CUTOFF = 1e-13
REQUIRED_PACKET_METADATA = (
    "schema", "local_mode_index", "original_mode_index", "original_mode_key",
    "original_mode_row", "physical_generator_manifest_sha256",
    "assembly_context_sha256", "assembly_context", "quotient_contract_sha256",
    "quotient_twist_index", "local_branch_index", "ownership_range",
    "component_masked_entries", "stored_C_sparse", "stored_D_sparse",
    "component_masks", "combination_masks", "local_plane_H", "original_plane_H",
    "single_D_conjugation", "raw_vectors_destroyed_before_callback", "array_ownership",
)
RAW_VECTOR_FIELDS = (
    "raw_C", "raw_D", "after_component_mask_C", "after_component_mask_D",
)
DEFERRED_GATES = (
    "union of two sectors and original 532-key coverage",
    "native primal/dual transport and raw full/local folding",
    "four complete-column masked/operator blocks and cross-branch leakage",
    "complete interior condensation qualification",
    "global dual-folded physical forcing and arbitrary full RHS",
    "factors, full original recovery, physical outputs, and outer replacement",
)


def _packet_metadata_errors(packet, *, local_index, original_index, original_key,
                            branch, twist, physical_manifest, context_sha,
                            contract_sha, ownership_range):
    """Pure metadata gate, also testable without importing project modules."""
    errors = ["missing " + name for name in REQUIRED_PACKET_METADATA if name not in packet]
    expected = {
        "schema": RAW_PACKET_SCHEMA, "local_mode_index": local_index,
        "original_mode_index": original_index, "original_mode_key": tuple(original_key),
        "local_branch_index": branch, "quotient_twist_index": twist,
        "physical_generator_manifest_sha256": physical_manifest,
        "assembly_context_sha256": context_sha, "quotient_contract_sha256": contract_sha,
        "ownership_range": tuple(ownership_range), "single_D_conjugation": True,
        "raw_vectors_destroyed_before_callback": True,
    }
    for name, value in expected.items():
        observed = packet.get(name)
        if name in ("original_mode_key", "ownership_range") and observed is not None:
            observed = tuple(observed)
        if observed != value or (isinstance(value, (bool, int)) and type(observed) is not type(value)):
            errors.append("mismatch " + name)
    return errors


def _dense_sparse(pair, n):
    """Lossless sparse packet input; integer checks precede every narrowing."""
    rows, values = map(np.asarray, pair)
    if (rows.ndim != 1 or values.shape != rows.shape or rows.dtype.kind not in "iu"
            or not np.isfinite(values).all()
            or np.any(rows < 0) or np.any(rows >= n)
            or (len(rows) > 1 and np.any(rows[1:] <= rows[:-1]))):
        raise ValueError("raw snapshot requires unique sorted in-range integer rows and finite values")
    result = np.zeros(n, dtype=np.complex128)
    result[rows.astype(np.int64, copy=False)] = values
    return result


def _packet_vector(packet, field, n):
    if field in packet:
        result = np.asarray(packet[field], dtype=np.complex128)
        if result.shape != (n,) or not np.isfinite(result).all():
            raise ValueError("incomplete or nonfinite observer vector: " + field)
        return result
    sparse = field + "_sparse"
    if sparse not in packet:
        raise ValueError("missing raw observer vector or lossless sparse snapshot: " + field)
    return _dense_sparse(packet[sparse], n)


def _packet_components(packet, n):
    if "raw_components" in packet:
        vectors = tuple(np.asarray(value, dtype=np.complex128) for value in packet["raw_components"])
    elif "raw_components_sparse" in packet:
        vectors = tuple(_dense_sparse(pair, n) for pair in packet["raw_components_sparse"])
    else:
        raise ValueError("actual pre-mask raw components are required; stored data cannot substitute")
    if len(vectors) != 2 or any(value.shape != (n,) or not np.isfinite(value).all() for value in vectors):
        raise ValueError("exactly two finite complete raw observer components are required")
    return vectors


def _mask(vector):
    threshold = max(ABSOLUTE_SPARSE_FLOOR,
                    RELATIVE_SPARSE_CUTOFF*float(np.max(np.abs(vector), initial=0.0)))
    return np.where(np.abs(vector) > threshold, vector, 0), threshold


def _mask_measurement(raw, masked, threshold):
    retained = np.flatnonzero(masked != 0)
    lost = np.flatnonzero((raw != 0) & (masked == 0))
    introduced = np.flatnonzero((raw == 0) & (masked != 0))
    return {
        "absolute_sparse_floor": ABSOLUTE_SPARSE_FLOOR,
        "relative_sparse_cutoff": RELATIVE_SPARSE_CUTOFF,
        "threshold": threshold, "raw_nonzero_support": int(np.count_nonzero(raw)),
        "retained_support": len(retained), "lost_support": len(lost),
        "introduced_support": len(introduced), "lost_rows": lost.tolist(),
        "retained_rows_signature": _array_signature(retained),
        "raw_norm": float(np.linalg.norm(raw)), "stored_norm": float(np.linalg.norm(masked)),
        "loss_norm": float(np.linalg.norm(raw-masked)),
    }


def _rank_one_loss_bound(C, D, Cref, Dref, H):
    """All-DOF operator/Frobenius upper bound, no dense FE operator."""
    return float((np.linalg.norm(C-Cref)*np.linalg.norm(D)
                  + np.linalg.norm(Cref)*np.linalg.norm(D-Dref))/H)


def _source_binding(context):
    """Recheck actual bound source files, not only claimed hash strings."""
    source_roots = (Path(__file__).parent, Path(__file__).parents[1]/"common",
                    Path(__file__).parents[1]/"constraints")
    checked = {}
    for name, expected in context["source_sha256"].items():
        if Path(name).name != name:
            raise ValueError("assembly source identity must contain filenames only")
        paths = [root/name for root in source_roots if (root/name).is_file()]
        if len(paths) != 1:
            raise ValueError("bound assembly source is missing or ambiguous: " + name)
        actual = hashlib.sha256(paths[0].read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError("actual bound assembly source changed: " + name)
        checked[name] = {"path": str(paths[0]), "sha256": actual}
    required = {"dtn_port_3d.py", "fullspace_dtn_action.py", "dtn_boundary_phase_gauge.py",
                "dtn_boundary_plane_qualification.py", "y_orbit_quotient_context.py",
                "floquet_3d.py", "floquet_3d_high_order.py", "high_order_floquet_trace.py"}
    if not required.issubset(checked):
        raise ValueError("quotient assembly source proof is incomplete")
    return checked


def _actual_discrete_binding(bundle, carrier):
    """Compare current finalized public MPC/mesh/basis arrays to bound identity."""
    from .fullspace_dtn_action import _canonical_json_bytes
    setup, context = bundle["setup"], carrier.assembly_context
    V, mpc, data = setup["spaces"][4], setup["floquets"][4].mpc, setup["mesh_data"]
    mesh = data.mesh
    coefficients, offsets = mpc.coefficients()
    for name, value in (("slaves", mpc.slaves), ("masters", mpc.masters.array),
                        ("coefficients", coefficients), ("offsets", offsets)):
        if _array_signature(value) != context["MPC"][name]:
            raise ValueError("actual finalized MPC binding changed: " + name)
    mesh.topology.create_entity_permutations()
    mesh.topology.create_connectivity(mesh.topology.dim-1, 0)
    facets = mesh.topology.connectivity(mesh.topology.dim-1, 0)
    for name, value in (("geometry_x", mesh.geometry.x), ("geometry_dofmap", mesh.geometry.dofmap),
                        ("facet_vertices", facets.array), ("facet_vertex_offsets", facets.offsets),
                        ("facet_indices", data.facet_tags.indices), ("facet_values", data.facet_tags.values),
                        ("cell_indices", data.cell_tags.indices), ("cell_values", data.cell_tags.values)):
        if _array_signature(value) != context["mesh"][name]:
            raise ValueError("actual local mesh/tag binding changed: " + name)
    if (_array_signature(mesh.topology.get_cell_permutation_info()) != context["orientation"]
            or _array_signature(V.element.basix_element.coefficient_matrix) != context["basix_coefficients"]):
        raise ValueError("actual p4 orientation/Basix binding changed")
    cell_count = int(mesh.topology.index_map(mesh.topology.dim).size_local)
    digest = hashlib.sha256()
    for cell in range(cell_count):
        digest.update(_canonical_json_bytes(_array_signature(np.asarray(V.dofmap.cell_dofs(cell)))))
    if digest.hexdigest() != context["cell_dofmap_sha256"]:
        raise ValueError("actual cell dofmap binding changed")
    return {"actual_local_cells": cell_count, "actual_local_storage_rows": int(V.dofmap.index_map.size_global),
            "actual_finalized_slave_rows": len(mpc.slaves), "cell_dofmap_sha256": digest.hexdigest()}


def qualify_quotient_raw_bundle(bundle, *, raw_mode_packets, record_path,
                                expected_physical_manifest, expected_global_ordered_keys,
                                seed=FIXED_SEED, tolerance=FIXED_TOLERANCE):
    """Audit one supplied live sector and current-mode raw packet stream.

    Packets are the existing observer v1 mappings. A caller may instead provide
    lossless sparse snapshots: raw_components_sparse contains two (rows,values)
    pairs and each RAW_VECTOR_FIELDS name may have a _sparse pair. Rows must be
    sorted unique original local-storage rows. Every true nonzero is retained,
    including values below either cutoff. Sparse capture is caller-owned and
    never inferred from a masked carrier. The iterator must yield exactly the
    sector's contiguous order once; the function retains no packet collection.

    PASS_QUOTIENT_RAW_PORT_AUDIT_ONLY is not full component/PDE/factor/official
    qualification. Physical n0 incidence is incompatible with the b1 local
    wrap. Q3-Q5 require global dual-folded physical forcing and full outputs.
    """
    from mpi4py import MPI
    from petsc4py import PETSc
    from dolfinx import fem
    import ufl
    from .dtn_port_3d import (
        _with_quadrature_degree, _assemble_mpc_form_vector, _set_scalar_constant,
        _traction_vector, _mode_projection_denominator,
    )
    from .fullspace_same_mesh_hcurl_pmg_setup import SAME_MESH_JIT_OPTIONS
    from .fullspace_dtn_action import _jsonable, _canonical_json_bytes
    from .y_orbit_quotient_context import YOrbitTwoCellQuotientContext, PHYSICAL_GENERATOR_SHA256
    if __debug__ is False:
        raise RuntimeError("raw audit gates require nonoptimized Python")
    if tolerance != FIXED_TOLERANCE or seed != FIXED_SEED:
        raise ValueError("admitted raw audit fixes tolerance 1e-10 and seed 4053202")
    carrier = bundle["dtn_action"].carrier
    identity_before = carrier_numeric_identity(carrier)
    record_path = Path(record_path)
    partial_path = record_path.with_name("partial_quotient_raw_ports.json")
    failure_path = record_path.with_name("failed_quotient_raw_ports.json")
    ledger_path = record_path.with_name("quotient_raw_mode_ledger.jsonl")
    if any(path.exists() for path in (record_path, partial_path, failure_path, ledger_path)):
        raise ValueError("raw audit evidence already exists; use a fresh artifact directory")
    record_path.parent.mkdir(parents=True, exist_ok=True)
    forms, oracle_gauss, ledger = {}, {}, []
    ledger_digest = hashlib.sha256()
    current, supplied, literal_current = None, None, None
    gate = "supplied live bundle/context"
    base = {"schema": AUDIT_SCHEMA, "full_component_qualified": False, "full_case_pass": False,
            "PDE_solved": False, "factor_count": 0, "official_results": False,
            "physical_rhs_qualified": False, "physical_output_qualified": False,
            "qualification_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "carrier_identity_before": identity_before, "seed": seed, "tolerance": tolerance,
            "deferred_gates": DEFERRED_GATES,
            "scope": "one exact live local sector, true raw/literal ports, unchanged masks, five FE action/recovery probes"}

    def write(path, value):
        path.write_text(json.dumps(_jsonable(_failure_diagnostic(value)), indent=2, allow_nan=False)+"\n")

    def preserve():
        write(partial_path, {**base, "status": "PARTIAL_QUOTIENT_RAW_PORT_AUDIT",
                            "gate": gate, "completed_mode_count": len(ledger),
                            "completed_per_mode_ledger": {"path": str(ledger_path),
                                "sha256": ledger_digest.hexdigest(), "mode_count": len(ledger)},
                            "current_mode": current,
                            "independent_oracle_compiled_gauss": oracle_gauss})

    def require(condition, label):
        # A rejecting gate writes every measurement before raising. Completed
        # modes are separately checkpointed once, without rewriting the full
        # ledger for every successful scalar recovery check.
        if not condition:
            preserve()
            raise AssertionError(label)

    try:
        require(int(MPI.COMM_WORLD.size) == 1, "MPI1 audit required")
        ctx = bundle.get("quotient_context")
        require(isinstance(ctx, YOrbitTwoCellQuotientContext), "explicit frozen quotient context required")
        cfg, physical_cfg, setup = bundle["cfg"], bundle["physical_cfg"], bundle["setup"]
        selected, rows, manifest = ctx.select_inventory(physical_cfg, cfg, bundle["global_mode_inventory"])
        modes = tuple(bundle["modes"])
        M = SECTOR_COUNTS[ctx.twist_index]
        require(len(modes) == len(carrier.entries) == M and all(a is b for a, b in zip(modes, selected, strict=True)),
                "exact original selected mode objects and sector count required")
        require(manifest == expected_physical_manifest == PHYSICAL_GENERATOR_SHA256
                == bundle["mode_sha256"] == carrier.physical_generator_manifest_sha256,
                "unchanged global physical generator identity required")
        global_keys = tuple(tuple(key) for key in expected_global_ordered_keys)
        full_modes = tuple(bundle["global_mode_inventory"][0])
        semantic_global = tuple((i, mode.side, mode.m, mode.n, mode.polarization) for i, mode in enumerate(full_modes))
        require(len(global_keys) == len(set(global_keys)) == 532 and global_keys == semantic_global,
                "independent original 532 ordered keys required")
        semantic_local = tuple((i, mode.side, mode.m, mode.n, mode.polarization) for i, mode in enumerate(modes))
        require(tuple(entry.mode_key for entry in carrier.entries) == semantic_local,
                "local carrier indices must remain contiguous")
        require(carrier.quotient_context is ctx and carrier.original_mode_indices == ctx.original_mode_indices
                and carrier.original_mode_keys == ctx.original_mode_keys
                and carrier.local_branch_indices == ctx.local_branch_indices,
                "exact carrier/quotient mapping identity required")
        require(bundle["dtn_phase_gauge"] == BOUNDARY_PLANE and bundle["incident_projections"] is None,
                "quotient raw audit requires centered ports and no local incident RHS")
        context = carrier.assembly_context
        require(bundle["assembly_context_sha256"] == carrier.assembly_context_sha256
                == hashlib.sha256(_canonical_json_bytes(context)).hexdigest()
                and bundle["assembly_mode_manifest_sha256"] == carrier.mode_manifest_sha256,
                "exact assembly numeric/context digest required")
        local_context = context["y_orbit_quotient"]
        require(local_context["contract_sha256"] == ctx.sha256
                and _canonical_json_bytes(local_context["contract"]) == _canonical_json_bytes(ctx.identity()),
                "exact explicit phase/sector contract required")
        profile = _qualification_degree_profile(bundle)
        require(profile["degree"] == 4 and profile["local_space_dimension"] == 300
                and profile["quadrature_degree"] == 23 and profile["primary_facet_points"] == 144,
                "actual degree4/local300/Gauss23/144 profile required")
        V, mpc, mesh_data = setup["spaces"][4], setup["floquets"][4].mpc, setup["mesh_data"]
        n, qdegree = int(V.dofmap.index_map.size_global), int(bundle["dtn_quadrature_degree"])
        discrete = _actual_discrete_binding(bundle, carrier)
        require(discrete["actual_local_cells"] == 40 and n == 8940
                and discrete["actual_finalized_slave_rows"] == 1004
                and carrier.ownership_range == (0, n), "actual bounded 40-cell local storage/MPC profile required")
        floquet = setup["floquets"][4]
        require((complex(floquet.phase_x), complex(floquet.phase_y)) == ctx.phase_override
                and complex(floquet.phase_corner) == ctx.phase_x*ctx.tau and ctx.tau == ctx.eta**2,
                "actual finalized explicit x/y/corner wrap required")
        source_proof = _source_binding(context)
        primary_gauss = bundle["compiled_surface_gauss_identity"]
        require(primary_gauss == context["gauss"]["compiled_forms_verified"], "actual primary Gauss context required")
        _check_loaded_primary_provenance(primary_gauss)
        for proof in primary_gauss.values():
            kernel = proof["loaded_kernel"]
            require(kernel["restoration_exact"] and kernel["numerical_assembly_during_probe"] is False
                    and kernel["num_constants"] == 3
                    and tuple(item["role"] for item in kernel["constant_roles"]) == ("alpha", "gamma", "kz"),
                    "actual loaded kernel/constant-role proof required")
        base.update({**profile, "actual_discrete_binding": discrete, "actual_source_binding": source_proof,
                     "physical_generator_manifest_sha256": manifest, "assembly_context_sha256": carrier.assembly_context_sha256,
                     "assembly_mode_manifest_sha256": carrier.mode_manifest_sha256,
                     "quotient_contract_sha256": ctx.sha256, "quotient_twist_index": ctx.twist_index,
                     "mode_count": M, "global_mode_count": 532,
                     "original_mode_indices": ctx.original_mode_indices, "original_mode_keys": ctx.original_mode_keys,
                     "primary_compiled_gauss": primary_gauss, "raw_discrete_context": context})
        rng = np.random.default_rng(seed)
        states = rng.normal(size=(n, 5))+1j*rng.normal(size=(n, 5))
        states[np.asarray(mpc.slaves, dtype=np.int64)] = 0
        labels = ("global_raw", "plane_raw", "observer_raw", "stored")
        accumulated = {label: np.zeros_like(states) for label in labels}
        expected_recovery = {label: np.zeros((M, 5), dtype=np.complex128) for label in ("plane_raw", "stored")}
        recovery_scale = {label: np.zeros(M) for label in expected_recovery}
        gate = "compiled independent literal same Gauss"
        # Literal forms are the existing eight parameterized forms verbatim;
        # physical alpha/gamma/kz remain from global modes, MPC is local actual.
        for gauge in (GLOBAL_Z, BOUNDARY_PLANE):
            for side in ("top", "bottom"):
                for component in (0, 1):
                    alpha = fem.Constant(mesh_data.mesh, PETSc.ScalarType(0))
                    gamma = fem.Constant(mesh_data.mesh, PETSc.ScalarType(0))
                    kz = fem.Constant(mesh_data.mesh, PETSc.ScalarType(0))
                    x = ufl.SpatialCoordinate(mesh_data.mesh)
                    z = x[2] if gauge == GLOBAL_Z else x[2]-PETSc.ScalarType(
                        cfg.physical_z_max if side == "top" else cfg.physical_z_min)
                    phase = ufl.exp(PETSc.ScalarType(1j)*(alpha*x[0]+gamma*x[1]+kz*z))
                    vector = [PETSc.ScalarType(0)]*3
                    vector[component] = phase
                    form = ufl.inner(ufl.as_vector(vector), ufl.TestFunction(V))*ufl.Measure(
                        "ds", domain=mesh_data.mesh, subdomain_data=mesh_data.facet_tags)(
                            cfg.tags.z_max if side == "top" else cfg.tags.z_min)
                    compiled = fem.form(_with_quadrature_degree(form, qdegree), jit_options=SAME_MESH_JIT_OPTIONS)
                    oracle_identity = compiled_surface_quadrature_identity(
                        _with_quadrature_degree(form, qdegree), compiled,
                        semantic_constants={"alpha": alpha, "gamma": gamma, "kz": kz})
                    primary_identity = primary_gauss[f"{side}/{component}"]
                    oracle_gauss[f"{gauge}/{side}/{component}"] = oracle_identity
                    require(oracle_identity["rules"] == primary_identity["rules"], "literal/primary Gauss mismatch")
                    forms[(gauge, side, component)] = (alpha, gamma, kz, compiled)
        _check_loaded_primary_provenance(oracle_gauss)
        stream = iter(raw_mode_packets)
        operator_bounds = {name: 0.0 for name in ("component_mask", "final_mask", "all_masks", "literal_vs_primary_raw")}
        rank_one_norm_sum = 0.0
        for index, (mode, entry) in enumerate(zip(modes, carrier.entries, strict=True)):
            gate = f"true raw/literal/mask audit local mode {index}"
            current = {"local_mode_index": index, "original_mode_index": ctx.original_mode_indices[index],
                       "original_mode_key": ctx.original_mode_keys[index], "status": "INCOMPLETE_UNQUALIFIED_MODE"}
            supplied = next(stream, None)
            require(supplied is not None, "missing current-mode raw observer packet")
            errors = _packet_metadata_errors(supplied, local_index=index, original_index=ctx.original_mode_indices[index],
                original_key=ctx.original_mode_keys[index], branch=ctx.local_branch_indices[index], twist=ctx.twist_index,
                physical_manifest=manifest, context_sha=carrier.assembly_context_sha256,
                contract_sha=ctx.sha256, ownership_range=(0, n))
            current["packet_metadata_errors"] = errors
            require(not errors, "raw packet metadata identity mismatch")
            require(_canonical_json_bytes(supplied["assembly_context"]) == _canonical_json_bytes(context)
                    and _canonical_json_bytes(supplied["original_mode_row"]) == _canonical_json_bytes(rows[index])
                    and _canonical_json_bytes(entry.mode_identity["original_mode_row"]) == _canonical_json_bytes(rows[index])
                    and entry.mode_identity["original_mode_index"] == ctx.original_mode_indices[index]
                    and entry.mode_identity["local_branch_index"] == ctx.local_branch_indices[index],
                    "raw packet must bind exact current context/original physical row")
            observed_components = _packet_components(supplied, n)
            observed = {field: _packet_vector(supplied, field, n) for field in RAW_VECTOR_FIELDS}
            stored = {side: _dense_sparse(supplied[f"stored_{side}_sparse"], n) for side in ("C", "D")}
            literal = literal_current = {}
            for gauge in (GLOBAL_Z, BOUNDARY_PLANE):
                components = []
                for component in (0, 1):
                    alpha, gamma, kz, form = forms[(gauge, mode.side, component)]
                    for constant, value in ((alpha, mode.alpha), (gamma, mode.gamma), (kz, mode.k_vector[2])):
                        _set_scalar_constant(constant, value)
                    raw = _assemble_mpc_form_vector(form, mpc)
                    try:
                        require(raw.getOwnershipRange() == (0, n), "literal MPC owned layout mismatch")
                        components.append(np.asarray(raw.getArray(readonly=True), dtype=np.complex128).copy())
                    finally:
                        raw.destroy()
                literal[gauge] = tuple(components)
            gx, gy = literal[GLOBAL_Z]
            px, py = literal[BOUNDARY_PLANE]
            traction = _traction_vector(mode, cfg)
            Cg, Cp = -traction[0]*gx-traction[1]*gy, -traction[0]*px-traction[1]*py
            Dg = np.conjugate(mode.e_vector[0]*gx+mode.e_vector[1]*gy)
            Dp = np.conjugate(mode.e_vector[0]*px+mode.e_vector[1]*py)
            z = cfg.physical_z_max if mode.side == "top" else cfg.physical_z_min
            phase = complex(np.exp(1j*mode.k_vector[2]*z))
            H = (cfg.x_max-cfg.x_min)*(cfg.y_max-cfg.y_min)*mode.electric_tangential_norm_sq
            original_H = (physical_cfg.x_max-physical_cfg.x_min)*(physical_cfg.y_max-physical_cfg.y_min)*mode.electric_tangential_norm_sq
            Hg = _mode_projection_denominator(mode, cfg)
            current.update({"plane_H": H, "original_plane_H": original_H, "global_gauge_H": Hg,
                            "global_boundary_phase": phase, "observer_component_masks": supplied["component_masks"],
                            "observer_combination_masks": supplied["combination_masks"]})
            require(np.isfinite((phase, H, original_H, Hg)).all() and phase != 0 and H > 0,
                    "raw phase/H representability gate failed")
            Cgn, Dgn = Cg/phase, Dg/np.conjugate(phase)
            raw_errors = {"component_x": _relative(observed_components[0], px),
                          "component_y": _relative(observed_components[1], py),
                          "primary_literal_C": _relative(observed["raw_C"], Cp),
                          "primary_literal_D": _relative(observed["raw_D"], Dp),
                          "gauge_C": _relative(Cgn, Cp), "gauge_D": _relative(Dgn, Dp),
                          "gauge_H": abs(Hg/(abs(phase)**2)-H)/H,
                          "local_H": abs(supplied["local_plane_H"]-H)/H,
                          "original_H": abs(supplied["original_plane_H"]-original_H)/original_H,
                          "area_H_scaling": abs(original_H/2-H)/H,
                          "stored_H": abs(entry.normalization_h-H)/H}
            current["raw_literal_errors"] = raw_errors
            # Measure true raw identities before either mask policy is applied.
            require(all(np.isfinite(value) and value <= tolerance for value in raw_errors.values()),
                    "true pre-mask primary/literal C/D/H mismatch")
            require(raw_errors["stored_H"] <= 1e-14 and raw_errors["area_H_scaling"] <= 1e-14,
                    "original unchanged positive-H normalization/area gate failed")
            after_components = tuple(_mask(component) for component in observed_components)
            component_measurements = []
            for component, (masked, threshold) in enumerate(after_components):
                actual_masked = _dense_sparse(supplied["component_masked_entries"][component], n)
                measurement = _mask_measurement(observed_components[component], actual_masked, threshold)
                measurement["unchanged_policy_defect"] = _relative(actual_masked, masked)
                component_measurements.append(measurement)
                current["component_mask_measurements"] = component_measurements
                diagnostic = supplied["component_masks"][component]
                require(measurement["unchanged_policy_defect"] <= tolerance
                        and np.array_equal(actual_masked != 0, masked != 0)
                        and diagnostic["threshold"] == threshold
                        and diagnostic["absolute_sparse_floor"] == ABSOLUTE_SPARSE_FLOOR
                        and diagnostic["relative_sparse_cutoff"] == RELATIVE_SPARSE_CUTOFF,
                        "component cutoff differs from unchanged actual raw policy")
            mx, my = (item[0] for item in after_components)
            Cm = -traction[0]*mx-traction[1]*my
            Dm = np.conjugate(mode.e_vector[0]*mx+mode.e_vector[1]*my)
            final_measurements = {}
            for side, combined, supplied_combined, values, sparse_rows, sparse_values in (
                ("C", Cm, observed["after_component_mask_C"], stored["C"], entry.coupling_rows, entry.coupling_values),
                ("D", Dm, observed["after_component_mask_D"], stored["D"], entry.projection_rows, entry.projection_values)):
                expected, threshold = _mask(combined)
                carrier_values = _dense_sparse((sparse_rows, sparse_values), n)
                measurement = _mask_measurement(supplied_combined, values, threshold)
                measurement.update({"combination_defect": _relative(supplied_combined, combined),
                                    "unchanged_policy_defect": _relative(values, expected),
                                    "carrier_binding_defect": _relative(carrier_values, values)})
                final_measurements[side] = measurement
                current["final_mask_measurements"] = final_measurements
                diagnostic = supplied["combination_masks"][0 if side == "C" else 1]["combination_stage"]
                require(all(measurement[key] <= tolerance for key in
                            ("combination_defect", "unchanged_policy_defect", "carrier_binding_defect"))
                        and np.array_equal(values != 0, expected != 0)
                        and diagnostic["threshold"] == threshold
                        and diagnostic["absolute_sparse_floor"] == ABSOLUTE_SPARSE_FLOOR
                        and diagnostic["relative_sparse_cutoff"] == RELATIVE_SPARSE_CUTOFF,
                        "final cutoff/stored carrier differs from unchanged actual raw policy")
            C, D = stored["C"], stored["D"]
            reference_norm = float(np.linalg.norm(Cp)*np.linalg.norm(Dp)/H)
            losses = {"component_mask": _rank_one_loss_bound(Cm, Dm, observed["raw_C"], observed["raw_D"], H),
                      "final_mask": _rank_one_loss_bound(C, D, Cm, Dm, H),
                      "all_masks": _rank_one_loss_bound(C, D, Cp, Dp, H),
                      "literal_vs_primary_raw": _rank_one_loss_bound(observed["raw_C"], observed["raw_D"], Cp, Dp, H)}
            relative_bounds = {name: value/reference_norm if reference_norm else (0.0 if value == 0 else float("inf"))
                               for name, value in losses.items()}
            current.update({"raw_rank_one_Frobenius_norm": reference_norm, "rank_one_loss_bounds": losses,
                            "relative_rank_one_bounds": relative_bounds})
            require(all(np.isfinite(value) and value <= tolerance for value in relative_bounds.values()),
                    "per-mode full-DOF mask/raw rank-one bound exceeds original 1e-10")
            for name, value in losses.items():
                operator_bounds[name] += value
            rank_one_norm_sum += reference_norm
            for label, left, right in (("global_raw", Cgn, Dgn), ("plane_raw", Cp, Dp),
                                        ("observer_raw", observed["raw_C"], observed["raw_D"]), ("stored", C, D)):
                accumulated[label] += left[:, None]*(right@states)[None, :]/H
            for label, functional in (("plane_raw", Dp), ("stored", D)):
                expected_recovery[label][index] = functional@states/H
                recovery_scale[label][index] = np.linalg.norm(functional)/H
            current.update({"local_branch_index": ctx.local_branch_indices[index],
                            "C_raw_norm": float(np.linalg.norm(Cp)), "D_raw_norm": float(np.linalg.norm(Dp)),
                            "stored_C_entries": len(entry.coupling_rows), "stored_D_entries": len(entry.projection_rows),
                            "status": "PASS_LOCAL_MODE_RAW_MASK_PORT_AUDIT"})
            encoded = (json.dumps(_jsonable(_failure_diagnostic(current)), separators=(",", ":"), allow_nan=False)+"\n").encode()
            with ledger_path.open("ab") as stream_file:
                stream_file.write(encoded)
            ledger_digest.update(encoded)
            ledger.append(current)
            current = None
            preserve()
            # No dense raw array or observer packet escapes this iteration.
            del supplied, observed_components, observed, stored, literal, gx, gy, px, py
            del Cg, Cp, Dg, Dp, Cgn, Dgn, after_components, mx, my, Cm, Dm, C, D
            del components, masked, actual_masked, expected, carrier_values, values
            del combined, supplied_combined, left, right, functional
            supplied = literal_current = None
        extra = next(stream, None)
        current = {"extra_packet_metadata": _failure_diagnostic(dict(extra))} if extra is not None else None
        require(extra is None, "extra or repeated raw packet after the complete sector")
        current = None
        action_errors = {label: _relative(accumulated[label], accumulated["plane_raw"])
                         for label in ("global_raw", "observer_raw", "stored")}
        base.update({"raw_vs_stored_five_state_action_defects": action_errors,
                     "cumulative_absolute_operator_bounds": operator_bounds,
                     "sum_of_raw_mode_rank_one_norms": rank_one_norm_sum,
                     "operator_bound_reference": "absolute triangle bound; no certified relative norm of summed operator"})
        require(all(value <= tolerance for value in action_errors.values()), "five-state raw/stored action audit failed")
        gate = "five-state actual current action/recovery"
        action_recovery = []
        for column in range(5):
            source = PETSc.Vec().createSeq(n, comm=PETSc.COMM_SELF)
            target = source.duplicate()
            try:
                source.array[:] = states[:, column]
                source.assemble()
                bundle["dtn_action"].apply(source, target)
                recovered = bundle["dtn_action"].recover_auxiliary(source)
                measurement = {"state_column": column, "actual_action_vs_stored": _relative(target.array, accumulated["stored"][:, column]),
                               "actual_action_vs_raw": _relative(target.array, accumulated["plane_raw"][:, column]),
                               "actual_recovery_vs_stored": _relative(recovered, expected_recovery["stored"][:, column]),
                               "actual_recovery_vs_raw": _relative(recovered, expected_recovery["plane_raw"][:, column])}
                action_recovery.append(measurement)
                base["five_state_actual_action_recovery"] = action_recovery
                require(all(value <= tolerance for key, value in measurement.items() if key != "state_column"),
                        "actual current action/recovery mismatch")
                for index, value in enumerate(recovered):
                    for label in ("stored", "plane_raw"):
                        scale = recovery_scale[label][index]*np.linalg.norm(states[:, column])
                        expected = expected_recovery[label][index, column]
                        defect = float(abs(value-expected)/scale) if scale else (0.0 if value == expected else float("inf"))
                        ledger[index].setdefault("actual_recovery_operation_scaled_defects", {}).setdefault(label, []).append(defect)
                        require(defect <= tolerance, "per-mode raw/stored actual recovery operation-scaled mismatch")
            finally:
                target.destroy()
                source.destroy()
        gate = "unchanged live object/numeric/context/source/kernel identity"
        require(bundle["dtn_action"].carrier is carrier and carrier_numeric_identity(carrier) == identity_before,
                "supplied exact live carrier replaced or mutated")
        require(carrier.quotient_context is ctx and carrier.original_mode_indices == ctx.original_mode_indices
                and carrier.original_mode_keys == ctx.original_mode_keys
                and carrier.local_branch_indices == ctx.local_branch_indices
                and hashlib.sha256(_canonical_json_bytes(carrier.assembly_context)).hexdigest()
                    == identity_before["assembly_context_sha256"],
                "exact quotient mapping/discrete context changed during audit")
        final_modes, final_rows, final_manifest = ctx.select_inventory(physical_cfg, cfg, bundle["global_mode_inventory"])
        require(all(a is b for a, b in zip(final_modes, modes, strict=True))
                and final_manifest == manifest and _canonical_json_bytes(final_rows) == _canonical_json_bytes(rows),
                "frozen original physical mode objects changed during audit")
        require(_actual_discrete_binding(bundle, carrier) == discrete and _source_binding(context) == source_proof,
                "actual discrete/source inputs changed during audit")
        _check_loaded_primary_provenance(primary_gauss)
        _check_loaded_primary_provenance(oracle_gauss)
        require(primary_gauss == carrier.assembly_context["gauss"]["compiled_forms_verified"], "primary Gauss context changed")
        result = {**base, "status": PASS_STATUS, "raw_port_audit_pass": True,
                  "carrier_identity_after": carrier_numeric_identity(carrier),
                  "completed_per_mode_ledger": {"path": str(ledger_path), "sha256": ledger_digest.hexdigest(), "mode_count": len(ledger)},
                  "independent_oracle_compiled_gauss": oracle_gauss, "per_mode": ledger,
                  "physical_rhs_source_required": "dual_transport_of_original_global_MPC_load",
                  "resource_authority": "external whole-tree/source/ABI supervision; receipt is not resource admission"}
        write(record_path, result)
        return result
    except Exception as error:
        failure = {**base, "status": "FAILED_QUOTIENT_RAW_PORT_AUDIT", "raw_port_audit_pass": False,
                   "gate": gate, "exception_type": type(error).__name__, "exception": str(error),
                   "completed_mode_count": len(ledger), "per_mode": ledger, "current_mode": current,
                   "independent_oracle_compiled_gauss": oracle_gauss,
                   "current_raw_packet": dict(supplied) if supplied is not None else None,
                   "current_literal_raw_components": literal_current,
                   "evidence_classification": "partial/negative audit-only evidence; no full qualification"}
        write(failure_path, failure)
        raise
    finally:
        forms.clear()
        if bundle["dtn_action"].carrier is not carrier or carrier_numeric_identity(carrier) != identity_before:
            raise RuntimeError("supplied live carrier replaced or mutated during raw-port audit")
