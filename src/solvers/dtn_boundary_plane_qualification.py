"""Bounded same-live-carrier boundary-plane component qualification.

This research oracle owns only independent literal forms and small vectors.
It never builds/replaces a primary carrier or qualifies a PDE solution.
Every numerical run needs external source/ABI/resource admission.
"""
from __future__ import annotations

from pathlib import Path
from collections.abc import Mapping
import hashlib
import json

import numpy as np

from .dtn_boundary_phase_gauge import (
    GLOBAL_Z, BOUNDARY_PLANE, _array_signature,
    solver_amplitudes_from_global, plane_port_rhs_from_global,
    global_port_rhs_from_plane, incident_projection_in_solver_coordinates,
    boundary_mode_power_from_solver, prepare_boundary_plane_outputs,
    compiled_surface_quadrature_identity,
)
from .fresh_c1_manifest_identity import (
    NATIVE_LINUX_PROFILE,
    literal532_manifest_sha256,
)


LIVE_COMPONENT_GATES = (
    "loaded_kernel_provenance_and_constant_restoration",
    "compiled_primary_literal_same_gauss",
    "all532_raw_coefficient_H_equivalence",
    "every_mode_full_DOF_rank_one_bound",
    "five_state_actual_action_recovery_output_components",
    "physical_FE_RHS_literal_oracle",
    "incident_and_nonzero_port_RHS_transforms",
    "unchanged_live_carrier_digest",
)


def _relative(left, right):
    difference = np.linalg.norm(left-right)
    scale = np.linalg.norm(left)+np.linalg.norm(right)
    return float(difference/scale) if scale else (0.0 if difference == 0 else float("inf"))



def _failure_diagnostic(value):
    """JSON-safe failed measurements, preserving explicit nonfinite markers.

    This applies only to controlled failure evidence. A marker is never a
    numerical value, a success classification or a substitute for a gate.
    Completed/current mode payloads remain bounded by the fixed532 contract.
    """
    if isinstance(value, np.generic):
        return _failure_diagnostic(value.item())
    if isinstance(value, float) and not np.isfinite(value):
        kind = "nan" if np.isnan(value) else ("positive_infinity" if value > 0 else "negative_infinity")
        return {"measurement_status": "NONFINITE", "kind": kind}
    if isinstance(value, complex) and not np.isfinite(value):
        return {"measurement_status": "NONFINITE_COMPLEX",
                "real": _failure_diagnostic(value.real), "imag": _failure_diagnostic(value.imag)}
    if isinstance(value, Mapping):
        return {str(key): _failure_diagnostic(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, np.ndarray)):
        return [_failure_diagnostic(item) for item in value]
    return value

def carrier_numeric_identity(carrier):
    """Ordered keys/H/full sparse rows+values; separate provenance identity."""
    from .fullspace_dtn_action import _canonical_json_bytes
    digest = hashlib.sha256()
    digest.update(_canonical_json_bytes({
        "schema": "task40extra.live-boundary-carrier-digest.v1",
        "global_rows": carrier.global_rows, "ownership_range": carrier.ownership_range,
        "mode_count": len(carrier.entries),
        "slave_rows": _array_signature(carrier.slave_rows),
    }))
    for index, entry in enumerate(carrier.entries):
        digest.update(_canonical_json_bytes({
            "index": index, "key": entry.mode_key, "H": entry.normalization_h,
            **{name: _array_signature(getattr(entry, name)) for name in (
                "coupling_rows", "coupling_values", "projection_rows", "projection_values")},
        }))
    return {
        "physical_generator_manifest_sha256": carrier.physical_generator_manifest_sha256,
        "assembly_mode_manifest_sha256": carrier.mode_manifest_sha256,
        "assembly_context_sha256": carrier.assembly_context_sha256,
        "carrier_numeric_sha256": digest.hexdigest(),
        "mode_count": len(carrier.entries),
        "ordered_mode_keys": tuple(entry.mode_key for entry in carrier.entries),
    }


def boundary_carrier_digest(carrier):
    return carrier_numeric_identity(carrier)["carrier_numeric_sha256"]



def _check_loaded_primary_provenance(primary_gauss):
    """Recheck exact module-bound source/binary artifacts; never substitute IDs."""
    for identity in primary_gauss.values():
        kernel = identity["loaded_kernel"]
        for path_key, hash_key in (("module_path", "binary_sha256"),
                                   ("module_bound_C_path", "module_bound_C_sha256")):
            digest = hashlib.sha256()
            with Path(kernel[path_key]).open("rb") as stream:
                for chunk in iter(lambda: stream.read(1 << 20), b""):
                    digest.update(chunk)
            assert digest.hexdigest() == kernel[hash_key], (path_key, "loaded provenance artifact changed")


def fresh_c1_degree_profile(degree=6, runtime_profile=NATIVE_LINUX_PROFILE):
    """Derived same80 p4/p6 metadata; every inventory still needs a live gate."""
    if type(degree) is not int or degree not in (4, 6):
        raise ValueError("fresh C1 admits only integer degree 4 or 6")
    counts = {
        4: {"local_space_dimension": 300, "local_interior_rows": 108,
            "local_trace_rows": 192, "storage_rows": 17204,
            "independent_rows": 15872, "interior_rows": 8640,
            "independent_trace_rows": 7232, "native_slave_rows": 1332,
            "quadrature_degree": 23, "primary_facet_points": 144},
        6: {"local_space_dimension": 882, "local_interior_rows": 450,
            "local_trace_rows": 432, "storage_rows": 55950,
            "independent_rows": 52992, "interior_rows": 36000,
            "independent_trace_rows": 16992, "native_slave_rows": 2958,
            "quadrature_degree": 27, "primary_facet_points": 196},
    }[degree]
    profile = {"schema": "task40extra.fresh-C1-same80-degree-profile.v1",
            "degree": degree, "cell_count": 80, **counts,
            "expected_inventory_classification": "derived_not_measured",
            "nominal_gauss_points_require_actual_compiled_gate": True,
            "mode_count": 532, "manual_M": 9, "manual_N": 3,
            "physical_generator_manifest_sha256": literal532_manifest_sha256(runtime_profile),
            "action_recovery_limit": 1e-11, "original_residual_limit": 1e-10,
            "pure_algebra_limit": 1e-12,
            "p6_full_chain_qualified": False, "compact_p4_quotient_qualified": False}
    if runtime_profile != NATIVE_LINUX_PROFILE:
        profile["runtime_profile"] = runtime_profile
    return profile


def validate_fresh_c1_bundle_profile(bundle):
    """Fail closed on the actual MPI1 same80 FE/MPC/carrier/compiled profile.

    This is metadata admission only. It neither assembles a form nor grants a
    numerical PASS; the unchanged literal532 oracle must subsequently finish.
    """
    profile = fresh_c1_degree_profile(
        bundle["degree"], bundle.get("runtime_profile", NATIVE_LINUX_PROFILE)
    )
    degree = profile["degree"]
    cfg, levels = bundle["cfg"], bundle["setup"]
    if set(levels["spaces"]) != {degree} or set(levels["floquets"]) != {degree}:
        raise ValueError("fresh C1 requires exactly one requested FE/MPC degree")
    space, floquet = levels["spaces"][degree], levels["floquets"][degree]
    mpc, mesh = floquet.mpc, levels["mesh_data"].mesh
    element = space.element.basix_element
    scale = 7.0 / 135.0
    axes = {"x": tuple(v*scale for v in (0, 16.5, 25, 33.5, 50)),
            "y": tuple(v*scale for v in (0, 6.25, 12.5, 18.75, 25)),
            "z": tuple(v*scale for v in (-10, 0, 40, 80, 120, 130))}
    if (int(mesh.comm.size) != 1 or space.mesh is not mesh
            or int(mesh.topology.dim) != 3 or cfg.mesh_cell_type != "hexahedron"
            or tuple(cfg.mesh_axis_cell_counts) != (4, 4, 5)
            or any(tuple(getattr(cfg, "mesh_axis_"+axis+"_values")) != values
                   for axis, values in axes.items())
            or cfg.lambda0 != 0.7 or cfg.incident_phi_deg != 5.0
            or cfg.nedelec_degree != degree or cfg.visualization_degree != degree
            or cfg.nedelec_trace_degree is not None or cfg.nedelec_interior_degree is not None):
        raise ValueError("fresh C1 actual mesh/config/degree differs from the same80 fixture")
    if any(not np.array_equal(np.unique(mesh.geometry.x[:, column]), np.asarray(axes[axis]))
           for column, axis in enumerate(("x", "y", "z"))):
        raise ValueError("fresh C1 actual mesh coordinates differ from the frozen axes")
    index_map = space.dofmap.index_map
    cell_map = mesh.topology.index_map(3)
    local_interior = np.asarray(element.entity_dofs[3][0], dtype=np.int64)
    if (int(element.degree) != degree
            or int(space.element.space_dimension) != profile["local_space_dimension"]
            or int(mpc.function_space.element.basix_element.degree) != degree
            or int(mpc.function_space.element.space_dimension) != profile["local_space_dimension"]
            or int(space.dofmap.index_map_bs) != 1
            or int(cell_map.size_local) != profile["cell_count"]
            or int(cell_map.size_global) != profile["cell_count"]
            or int(index_map.size_local) != profile["storage_rows"]
            or int(index_map.size_global) != profile["storage_rows"]
            or int(index_map.num_ghosts) != 0
            or int(mpc.function_space.dofmap.index_map.size_global) != profile["storage_rows"]
            or len(local_interior) != profile["local_interior_rows"]
            or len(np.unique(local_interior)) != len(local_interior)
            or np.any(local_interior < 0) or np.any(local_interior >= profile["local_space_dimension"])):
        raise ValueError("fresh C1 actual complete local/global FE inventory differs")
    cell_rows = [np.asarray(space.dofmap.cell_dofs(cell)) for cell in range(profile["cell_count"])]
    if any(row.shape != (profile["local_space_dimension"],)
           or len(np.unique(row)) != len(row) for row in cell_rows):
        raise ValueError("fresh C1 lost a complete actual cell element")
    all_rows = np.unique(np.concatenate(cell_rows))
    interior_rows = np.unique(np.concatenate([row[local_interior] for row in cell_rows]))
    slaves, masters = np.asarray(mpc.slaves), np.asarray(mpc.masters.array)
    coefficients, offsets = (np.asarray(value) for value in mpc.coefficients())
    if (slaves.dtype != np.dtype("int32") or masters.dtype != np.dtype("int32")
            or offsets.dtype != np.dtype("int32") or coefficients.dtype != np.dtype("complex128")
            or slaves.ndim != 1 or masters.ndim != 1 or coefficients.ndim != 1 or offsets.ndim != 1
            or len(slaves) != profile["native_slave_rows"] or len(np.unique(slaves)) != len(slaves)
            or np.any(slaves < 0) or np.any(slaves >= profile["storage_rows"])
            or len(masters) != len(coefficients) or not np.isfinite(coefficients).all()
            or np.any(masters < 0) or np.any(masters >= profile["storage_rows"])
            or len(offsets) < profile["storage_rows"]+1 or offsets[0] != 0
            or offsets[-1] != len(coefficients) or np.any(np.diff(offsets) < 0)
            or any(offsets[int(row)+1] == offsets[int(row)] for row in slaves)):
        raise ValueError("fresh C1 actual finalized native MPC inventory is invalid")
    independent = np.setdiff1d(all_rows, slaves)
    if (not np.array_equal(all_rows, np.arange(profile["storage_rows"]))
            or len(interior_rows) != profile["interior_rows"]
            or np.isin(interior_rows, slaves).any()
            or len(independent) != profile["independent_rows"]
            or len(independent)-len(interior_rows) != profile["independent_trace_rows"]
            or profile["local_space_dimension"]-len(local_interior) != profile["local_trace_rows"]):
        raise ValueError("fresh C1 actual complete interior/native trace partition differs")
    carrier = bundle["dtn_action"].carrier
    context = carrier.assembly_context
    native = {name: _array_signature(value) for name, value in (
        ("slaves", slaves), ("masters", masters), ("coefficients", coefficients), ("offsets", offsets))}
    if native != context["MPC"] or not np.array_equal(carrier.slave_rows, slaves):
        raise ValueError("fresh C1 actual native MPC is detached from the live carrier context")
    abi = context["ABI"]
    if (not str(abi["dolfinx"]).startswith("0.10.") or abi["dolfinx_mpc"] != "0.10.5"
            or tuple(abi["PETSc"]) != (3, 25, 6)
            or abi["scalar"] != "complex128" or abi["integer"] != "int32"):
        raise ValueError("fresh C1 actual carrier ABI differs from the admitted recovered runtime")
    semantic = tuple((j, mode.side, mode.m, mode.n, mode.polarization)
                     for j, mode in enumerate(bundle["modes"]))
    if (bundle["dtn_phase_gauge"] != BOUNDARY_PLANE or cfg.stage4_dtn_order_policy != "manual"
            or cfg.diffraction_order_max_m != 9 or cfg.diffraction_order_max_n != 3
            or cfg.diffraction_zero_order_only is not False
            or len(semantic) != 532 or len(set(semantic)) != 532
            or tuple(entry.mode_key for entry in carrier.entries) != semantic
            or carrier.global_rows != profile["storage_rows"]
            or carrier.ownership_range != (0, profile["storage_rows"])
            or bundle["mode_sha256"] != profile["physical_generator_manifest_sha256"]
            or carrier.physical_generator_manifest_sha256 != profile["physical_generator_manifest_sha256"]
            or any(not len(entry.coupling_rows) or not len(entry.projection_rows) for entry in carrier.entries)):
        raise ValueError("fresh C1 actual complete manual532 physical inventory differs")
    qdegree, points = profile["quadrature_degree"], profile["primary_facet_points"]
    primary = bundle["compiled_surface_gauss_identity"]
    if (context["element_degree"] != degree or bundle["dtn_quadrature_degree"] != qdegree
            or context["gauss"]["degree"] != qdegree
            or primary != context["gauss"]["compiled_forms_verified"]
            or set(primary) != {"top/0", "top/1", "bottom/0", "bottom/1"}):
        raise ValueError("fresh C1 actual degree/primary compiled Gauss context differs")
    for record in primary.values():
        rules = record["rules"]
        if len(rules) != 1:
            raise ValueError("fresh C1 requires one actual compiled facet rule per primary form")
        rule = rules[0]
        if (rule["degree"] != qdegree or rule["facet_cell"] != "quadrilateral"
                or rule["integral_type"] != "exterior_facet"
                or tuple(rule["points"]["shape"]) != (points, 2)
                or tuple(rule["weights"]["shape"]) != (points,)
                or rule["points"]["dtype"] != "float64" or rule["weights"]["dtype"] != "float64"):
            raise ValueError("fresh C1 nominal Gauss count differs from the actual compiled nodes/weights")
    counts = {"cell_count": int(cell_map.size_local),
              "local_space_dimension": int(space.element.space_dimension),
              "local_interior_rows": len(local_interior),
              "local_trace_rows": int(space.element.space_dimension)-len(local_interior),
              "storage_rows": int(index_map.size_global), "independent_rows": len(independent),
              "interior_rows": len(interior_rows),
              "independent_trace_rows": len(independent)-len(interior_rows),
              "native_slave_rows": len(slaves)}
    return {"degree": degree, "element_degree": int(element.degree),
            "local_space_dimension": int(space.element.space_dimension),
            "quadrature_degree": qdegree, "primary_facet_points": points,
            "fresh_fixture_c1": True, "fresh_c1_profile": profile,
            "fresh_c1_actual_inventory": {"classification": "actual_runtime_gated",
                **counts, "native_MPC": native, "actual_primary_compiled_gauss_verified": True}}


def qualify_fresh_c1_p6_boundary_plane_bundle(
    bundle, *, record_path, expected_physical_manifest, expected_ordered_keys,
    seed=4053202, tolerance=1e-10,
):
    """Run the complete same-live literal532 qualification for the fresh p6 fixture.

    This is the original W0 numerical oracle narrowed to its explicit p6/same80
    route.  It compiles independent literal global-z and boundary-plane forms,
    reassembles every mode through the actual finalized MPC, checks the actual
    carrier coefficients and rank-one operators, then compares five complete
    storage states, recovered amplitudes, output conversion, and the physical
    incident RHS.  It does not solve a PDE or create a dense FE matrix/factor.
    """
    from mpi4py import MPI
    from petsc4py import PETSc
    from dolfinx import fem
    import ufl
    from .dtn_port_3d import (
        _with_quadrature_degree, _assemble_mpc_form_vector, _set_scalar_constant,
        _traction_vector, _mode_projection_denominator,
    )
    from .fullspace_same_mesh_hcurl_pmg_physical import build_physical_rhs
    from .fullspace_same_mesh_hcurl_pmg_setup import SAME_MESH_JIT_OPTIONS
    from .fullspace_dtn_action import _jsonable, _canonical_json_bytes

    if __debug__ is False:
        raise RuntimeError("component assertion gates require nonoptimized Python")
    if seed != 4053202 or tolerance != 1e-10:
        raise ValueError("fresh C1 fixes the original literal532 seed and 1e-10 gate")
    carrier = bundle["dtn_action"].carrier
    identity_before = carrier_numeric_identity(carrier)
    before_digest = identity_before["carrier_numeric_sha256"]
    record_path = Path(record_path)
    sidecars = tuple(record_path.with_name(name) for name in (
        "partial_components.json", "failed_output_packet.json", "failed_live_component.json"))
    if record_path.exists() or any(path.exists() for path in sidecars):
        raise FileExistsError("same-live qualification evidence already exists; require a fresh run directory")
    record_path.parent.mkdir(parents=True, exist_ok=True)
    raw_forms, ledger, oracle_gauss = {}, [], {}
    current_mode_diagnostics = None
    gate = "live input/identity"

    def write_packet(path, packet):
        path.write_text(json.dumps(_jsonable(packet), indent=2, allow_nan=False) + "\n")

    base_identity = {
        "schema": "task40extra.same-live-boundary-component.v1",
        "PDE_solved": False, "official_results": False,
        "physical_generator_manifest_sha256": carrier.physical_generator_manifest_sha256,
        "assembly_mode_manifest_sha256": carrier.mode_manifest_sha256,
        "assembly_context_sha256": carrier.assembly_context_sha256,
        "carrier_digest_before": before_digest, "identity": identity_before,
        "raw_discrete_context": carrier.assembly_context,
        "qualification_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "seed": seed, "tolerance": tolerance,
    }
    try:
        assert MPI.COMM_WORLD.size == 1
        cfg, levels = bundle["cfg"], bundle["setup"]
        assert bundle["dtn_phase_gauge"] == BOUNDARY_PLANE
        profile = validate_fresh_c1_bundle_profile(bundle)
        if profile["degree"] != 6:
            raise ValueError("literal532 fresh C1 oracle is fixed to degree six")
        degree = profile["degree"]
        base_identity.update(profile)
        modes = tuple(bundle["modes"])
        assert len(modes) == len(carrier.entries) == 532
        if (expected_physical_manifest != profile["physical_generator_manifest_sha256"]
                or bundle["mode_sha256"] != expected_physical_manifest
                or carrier.physical_generator_manifest_sha256 != expected_physical_manifest):
            raise ValueError("same-live expected literal532 manifest differs from the qualified runtime profile")
        expected_keys = tuple(tuple(key) for key in expected_ordered_keys)
        actual_keys = tuple(entry.mode_key for entry in carrier.entries)
        semantic_keys = tuple((index, mode.side, mode.m, mode.n, mode.polarization)
                              for index, mode in enumerate(modes))
        assert actual_keys == expected_keys == semantic_keys and len(set(actual_keys)) == 532
        assert all(len(entry.coupling_rows) and len(entry.projection_rows) for entry in carrier.entries)
        assert cfg.stage4_dtn_order_policy == "manual"
        assert cfg.diffraction_order_max_m == 9 and cfg.diffraction_order_max_n == 3
        assert bundle["assembly_context_sha256"] == carrier.assembly_context_sha256
        assert bundle["assembly_mode_manifest_sha256"] == carrier.mode_manifest_sha256
        assert carrier.assembly_context_sha256 == hashlib.sha256(
            _canonical_json_bytes(carrier.assembly_context)).hexdigest()
        assert carrier.construction_numeric_inventory[
            "unique_named_numpy_backing_bytes_before_staging_release"] <= 512 << 20
        V = levels["spaces"][degree]
        mpc = levels["floquets"][degree].mpc
        mesh_data = levels["mesh_data"]
        n = int(V.dofmap.index_map.size_global)
        qdegree = int(bundle["dtn_quadrature_degree"])
        assert carrier.ownership_range == (0, n)
        assert carrier.assembly_context["gauss"]["degree"] == qdegree
        primary_gauss = bundle["compiled_surface_gauss_identity"]
        assert primary_gauss == carrier.assembly_context["gauss"]["compiled_forms_verified"]
        _check_loaded_primary_provenance(primary_gauss)
        for identity in primary_gauss.values():
            kernel = identity["loaded_kernel"]
            assert kernel["restoration_exact"] and kernel["numerical_assembly_during_probe"] is False
            assert kernel["num_constants"] == 3
            assert tuple(item["role"] for item in kernel["constant_roles"]) == ("alpha", "gamma", "kz")

        rng = np.random.default_rng(seed)
        states = rng.normal(size=(n, 5)) + 1j * rng.normal(size=(n, 5))
        states[np.asarray(mpc.slaves, dtype=np.int64)] = 0
        assert states.nbytes <= 512 << 20
        labels = ("global_raw", "plane_raw", "new_stored")
        accumulated = {name: np.zeros_like(states) for name in labels}
        expected_recovery = {name: np.zeros((532, 5), dtype=np.complex128)
                             for name in ("new_stored", "plane_raw")}
        recovery_scales = {name: np.zeros(532) for name in expected_recovery}
        raw_incident_rhs = np.zeros(n, dtype=np.complex128)
        vector_cache = component_key = None
        gate = "independent literal Gauss"
        for gauge in (GLOBAL_Z, BOUNDARY_PLANE):
            for side in ("top", "bottom"):
                for component in (0, 1):
                    alpha = fem.Constant(mesh_data.mesh, PETSc.ScalarType(0))
                    gamma = fem.Constant(mesh_data.mesh, PETSc.ScalarType(0))
                    kz = fem.Constant(mesh_data.mesh, PETSc.ScalarType(0))
                    x = ufl.SpatialCoordinate(mesh_data.mesh)
                    z = (x[2] if gauge == GLOBAL_Z else
                         x[2] - PETSc.ScalarType(
                             cfg.physical_z_max if side == "top" else cfg.physical_z_min))
                    phase = ufl.exp(PETSc.ScalarType(1j) * (alpha*x[0] + gamma*x[1] + kz*z))
                    vector = [PETSc.ScalarType(0)] * 3
                    vector[component] = phase
                    tag = cfg.tags.z_max if side == "top" else cfg.tags.z_min
                    form = ufl.inner(ufl.as_vector(vector), ufl.TestFunction(V)) * ufl.Measure(
                        "ds", domain=mesh_data.mesh, subdomain_data=mesh_data.facet_tags)(tag)
                    compiled = fem.form(_with_quadrature_degree(form, qdegree),
                                        jit_options=SAME_MESH_JIT_OPTIONS)
                    oracle_identity = compiled_surface_quadrature_identity(
                        _with_quadrature_degree(form, qdegree), compiled,
                        semantic_constants={"alpha": alpha, "gamma": gamma, "kz": kz})
                    if oracle_identity["rules"] != primary_gauss[f"{side}/{component}"]["rules"]:
                        raise AssertionError("independent literal Gauss nodes/weights differ from primary")
                    oracle_gauss[f"{gauge}/{side}/{component}"] = oracle_identity
                    raw_forms[(gauge, side, component)] = (alpha, gamma, kz, compiled)

        def dense_entry(entry, side):
            result = np.zeros(n, dtype=np.complex128)
            rows = entry.coupling_rows if side == "C" else entry.projection_rows
            values = entry.coupling_values if side == "C" else entry.projection_values
            result[rows] = values
            return result

        def loss_bound(C, D, Cref, Dref, H):
            return float((np.linalg.norm(C-Cref)*np.linalg.norm(D)
                          + np.linalg.norm(Cref)*np.linalg.norm(D-Dref))/H)

        for index, (mode, new_entry) in enumerate(zip(modes, carrier.entries, strict=True)):
            gate = f"literal532 coefficient/action/port-equation index={index}"
            current_mode_diagnostics = {"index": index, "key": new_entry.mode_key,
                                        "status": "INCOMPLETE_UNQUALIFIED_MODE", "measurements": {}}
            key = (mode.side, mode.m, mode.n, complex(mode.k_vector[2]))
            if key != component_key:
                vector_cache = {}
                for gauge in (GLOBAL_Z, BOUNDARY_PLANE):
                    components = []
                    for component in (0, 1):
                        alpha, gamma, kz, form = raw_forms[(gauge, mode.side, component)]
                        for constant, value in ((alpha, mode.alpha), (gamma, mode.gamma),
                                                (kz, mode.k_vector[2])):
                            _set_scalar_constant(constant, value)
                        raw = _assemble_mpc_form_vector(form, mpc)
                        try:
                            if tuple(raw.getOwnershipRange()) != (0, n):
                                raise ValueError("literal MPC vector ownership differs from the full same80 space")
                            components.append(np.asarray(raw.getArray(readonly=True),
                                                         dtype=np.complex128).copy())
                        finally:
                            raw.destroy()
                    vector_cache[gauge] = components
                component_key = key
            gx, gy = vector_cache[GLOBAL_Z]
            px, py = vector_cache[BOUNDARY_PLANE]
            traction = _traction_vector(mode, cfg)
            Cg, Cp = -traction[0]*gx - traction[1]*gy, -traction[0]*px - traction[1]*py
            Dg = np.conjugate(mode.e_vector[0]*gx + mode.e_vector[1]*gy)
            Dp = np.conjugate(mode.e_vector[0]*px + mode.e_vector[1]*py)
            z = cfg.physical_z_max if mode.side == "top" else cfg.physical_z_min
            scale = complex(np.exp(1j*mode.k_vector[2]*z))
            current_mode_diagnostics["measurements"]["global_boundary_phase"] = scale
            assert np.isfinite(scale) and scale != 0
            H = (cfg.x_max-cfg.x_min) * (cfg.y_max-cfg.y_min) * mode.electric_tangential_norm_sq
            Cgn, Dgn = Cg/scale, Dg/np.conjugate(scale)
            Hg = _mode_projection_denominator(mode, cfg)
            errors = {"raw_C_equivalence": _relative(Cgn, Cp),
                      "raw_D_equivalence": _relative(Dgn, Dp),
                      "raw_H_equivalence": abs(Hg/(abs(scale)**2)-H)/H}
            current_mode_diagnostics["measurements"].update({"raw_equivalence": errors.copy(),
                "Hglobal": Hg, "Hplane": H, "stored_Hplane": new_entry.normalization_h,
                "raw_C_norm": float(np.linalg.norm(Cp)), "raw_D_norm": float(np.linalg.norm(Dp))})
            assert all(value <= tolerance for value in errors.values()), (index, errors)
            assert abs(new_entry.normalization_h-H) <= 1e-14*H
            C_new, D_new = dense_entry(new_entry, "C"), dense_entry(new_entry, "D")
            expected_recovery["new_stored"][index] = D_new @ states / H
            expected_recovery["plane_raw"][index] = Dp @ states / H
            recovery_scales["new_stored"][index] = np.linalg.norm(D_new)/H
            recovery_scales["plane_raw"][index] = np.linalg.norm(Dp)/H
            actions = {}
            for label, C, D in (("global_raw", Cgn, Dgn), ("plane_raw", Cp, Dp),
                                ("new_stored", C_new, D_new)):
                actions[label] = C[:, None] * (D @ states)[None, :] / H
                accumulated[label] += actions[label]
            action_error = _relative(actions["global_raw"], actions["plane_raw"])
            errors["per_mode_raw_action_equivalence"] = action_error
            current_mode_diagnostics["measurements"]["per_mode_raw_action_equivalence"] = action_error
            assert action_error <= tolerance
            reference_norm = float(np.linalg.norm(Cp)*np.linalg.norm(Dp)/H)
            bound = loss_bound(C_new, D_new, Cp, Dp, H)
            relative_bound = bound/reference_norm if reference_norm else (0.0 if bound == 0 else float("inf"))
            current_mode_diagnostics["measurements"].update({
                "raw_rank_one_Frobenius_norm": reference_norm,
                "new_stored_loss_bound": bound,
                "new_stored_relative_operator_bound": relative_bound})
            assert relative_bound <= tolerance, (index, "all-DOF rank-one operator bound", relative_bound)

            # Independently record the exact existing component/combined cutoffs.
            cutoffs = {}
            for label, components in (("global", (gx, gy)), ("plane", (px, py))):
                retained = []
                component_counts = []
                for component_values in components:
                    cutoff = max(1e-30, 1e-13*float(np.max(np.abs(component_values))))
                    keep = np.abs(component_values) > cutoff
                    retained.append(np.where(keep, component_values, 0))
                    component_counts.append({"raw_nonzero": int(np.count_nonzero(component_values)),
                                             "retained": int(np.count_nonzero(keep)),
                                             "cutoff": cutoff})
                Ccombined = -traction[0]*retained[0] - traction[1]*retained[1]
                Dcombined = np.conjugate(mode.e_vector[0]*retained[0] + mode.e_vector[1]*retained[1])
                cutoffs[label] = {"components": component_counts,
                    "combined_C_cutoff": max(1e-30, 1e-13*float(np.max(np.abs(Ccombined)))),
                    "combined_D_cutoff": max(1e-30, 1e-13*float(np.max(np.abs(Dcombined))))}
            b = rng.normal(size=5) + 1j*rng.normal(size=5)
            rp_plane = H*b - Dp@states
            rp_global = Hg*(b/scale) - Dg@states
            port_error = _relative(rp_global/np.conjugate(scale), rp_plane)
            current_mode_diagnostics["measurements"]["raw_nonzero_port_equation_defect"] = port_error
            assert port_error <= tolerance
            incident_global = incident_projection_in_solver_coordinates(mode, cfg, GLOBAL_Z)
            incident_plane = incident_projection_in_solver_coordinates(mode, cfg, BOUNDARY_PLANE)
            raw_incident_rhs += Cp*incident_plane
            total_plane = (Dp@states[:, 0])/H
            out_plane = total_plane-incident_plane if mode.side == "top" else total_plane
            out_global = (total_plane/scale)-incident_global if mode.side == "top" else total_plane/scale
            plane_power = boundary_mode_power_from_solver(mode, cfg, out_plane, BOUNDARY_PLANE)
            global_power = boundary_mode_power_from_solver(mode, cfg, out_global, GLOBAL_Z)
            electric = out_plane*np.asarray(mode.e_vector)
            magnetic = np.cross(mode.k_vector, electric)/(cfg.k0*complex(cfg.mu_r))
            power_scale = 0.5*(cfg.x_max-cfg.x_min)*(cfg.y_max-cfg.y_min)*np.linalg.norm(electric)*np.linalg.norm(magnetic)
            power_error = (abs(plane_power-global_power)/power_scale if power_scale
                           else (0.0 if plane_power == global_power else float("inf")))
            current_mode_diagnostics["measurements"].update({"plane_outgoing_power": plane_power,
                "global_outgoing_power": global_power, "power_operation_scaled_defect": power_error})
            assert power_error <= tolerance
            ledger.append({"index": index, "key": list(new_entry.mode_key),
                "log_abs_s": float(np.log(abs(scale))), "Hglobal": float(Hg), "Hplane": float(H),
                "raw_C_norm": float(np.linalg.norm(Cp)), "raw_D_norm": float(np.linalg.norm(Dp)),
                "raw_rank_one_Frobenius_norm": reference_norm,
                "new_C_entries": len(new_entry.coupling_rows), "new_D_entries": len(new_entry.projection_rows),
                "new_stored_loss_bound": bound, "new_stored_relative_operator_bound": relative_bound,
                "both_sparsification_stages": cutoffs, "plane_outgoing_power": plane_power,
                "global_outgoing_power": global_power, "power_operation_scaled_defect": float(power_error),
                "raw_nonzero_port_equation_defect": float(port_error),
                "global_component_cutoffs": [max(1e-30, 1e-13*float(np.max(np.abs(v)))) for v in (gx, gy)],
                "plane_component_cutoffs": [max(1e-30, 1e-13*float(np.max(np.abs(v)))) for v in (px, py)],
                "equivalence": errors})
            current_mode_diagnostics = None
        assert len(ledger) == 532
        assert _relative(accumulated["global_raw"], accumulated["plane_raw"]) <= tolerance
        assert _relative(accumulated["new_stored"], accumulated["plane_raw"]) <= tolerance

        outputs = []
        gate = "actual carrier action/recovery/output components"
        for column in range(5):
            source = PETSc.Vec().createSeq(n, comm=PETSc.COMM_SELF)
            target = source.duplicate()
            try:
                source.array[:] = states[:, column]
                source.assemble()
                bundle["dtn_action"].apply(source, target)
                assert _relative(target.array, accumulated["new_stored"][:, column]) <= tolerance
                recovered = bundle["dtn_action"].recover_auxiliary(source)
                assert _relative(recovered, expected_recovery["new_stored"][:, column]) <= tolerance
                assert _relative(recovered, expected_recovery["plane_raw"][:, column]) <= tolerance
                for index, observed in enumerate(recovered):
                    for label in ("new_stored", "plane_raw"):
                        error = abs(observed-expected_recovery[label][index, column])
                        scale_value = recovery_scales[label][index]*np.linalg.norm(states[:, column])
                        defect = float(error/scale_value) if scale_value else (0.0 if observed == expected_recovery[label][index, column] else float("inf"))
                        if label == "new_stored":
                            ledger[index].setdefault("production_recovery_operation_scaled_defects", []).append(defect)
                        else:
                            ledger[index].setdefault("raw_recovery_operation_scaled_defects", []).append(defect)
                        assert defect <= tolerance, (index, label, "per-entry stored recovery")
                output = prepare_boundary_plane_outputs(recovered, bundle["incident_projections"], modes, cfg)
                if output["status"] != "representable_global_output":
                    write_packet(record_path.with_name("failed_output_packet.json"), {
                        "status": "FAILED_OUTPUT_COMPONENT_GATE", "full_case_pass": False,
                        "arbitrary_state_column": column, "packet": output, "PDE_solved": False})
                assert output["status"] == "representable_global_output"
                assert output["global_output_component_consistency_checked"]
                assert output["official_results"] is False
                outputs.append({"arbitrary_state_column": column, "mode_count": len(modes),
                    "status": output["status"], "global_output_component_consistency_checked": True,
                    "official_results": False,
                    "global_output_component_checks": output["global_output_component_checks"],
                    "analytic_zero_power_checks": output.get("analytic_zero_power_checks", [])})
            finally:
                target.destroy()
                source.destroy()

        gate = "physical FE RHS independent literal oracle"
        k_inc = np.asarray(cfg.wavevector, dtype=np.complex128)
        e_inc = complex(cfg.incident_amplitude)*np.asarray(cfg.polarization_vector, dtype=np.complex128)
        incident_traction = np.cross(1j*np.cross(k_inc, e_inc), np.asarray([0., 0., 1.]))
        x = ufl.SpatialCoordinate(mesh_data.mesh)
        incident_phase = ufl.exp(PETSc.ScalarType(1j)*(PETSc.ScalarType(k_inc[0])*x[0]
            + PETSc.ScalarType(k_inc[1])*x[1] + PETSc.ScalarType(k_inc[2])*x[2]))
        literal_incident = ufl.inner(ufl.as_vector(tuple(PETSc.ScalarType(value)*incident_phase
            for value in incident_traction)), ufl.TestFunction(V))*ufl.Measure(
                "ds", domain=mesh_data.mesh, subdomain_data=mesh_data.facet_tags)(cfg.tags.z_max)
        compiled_incident = fem.form(_with_quadrature_degree(literal_incident, qdegree),
                                     jit_options=SAME_MESH_JIT_OPTIONS)
        incident_gauss = compiled_surface_quadrature_identity(
            _with_quadrature_degree(literal_incident, qdegree), compiled_incident)
        assert incident_gauss["rules"] == primary_gauss["top/0"]["rules"]
        raw_rhs = _assemble_mpc_form_vector(compiled_incident, mpc)
        physical_rhs = None
        try:
            expected_rhs = np.asarray(raw_rhs.getArray(readonly=True), dtype=np.complex128) + raw_incident_rhs
            physical_rhs, _rhs_facts = build_physical_rhs(bundle)
            rhs_defect = _relative(physical_rhs.array, expected_rhs)
            assert rhs_defect <= tolerance
        finally:
            if physical_rhs is not None:
                physical_rhs.destroy()
            raw_rhs.destroy()

        gate = "incident and arbitrary nonzero port RHS transforms"
        incident_global = np.asarray([incident_projection_in_solver_coordinates(mode, cfg, GLOBAL_Z)
                                      for mode in modes])
        incident_roundtrip = solver_amplitudes_from_global(incident_global, modes, cfg, BOUNDARY_PLANE)
        incident_reference = np.asarray(bundle["incident_projections"])
        np.testing.assert_allclose(incident_roundtrip, incident_reference, rtol=tolerance, atol=1e-12)
        incident_transform_gate_ratio = float(np.max(
            np.abs(incident_roundtrip-incident_reference)
            / (tolerance*np.abs(incident_reference)+1e-12)))
        port_rhs_global = rng.normal(size=(532, 5)) + 1j*rng.normal(size=(532, 5))
        port_rhs_plane = plane_port_rhs_from_global(port_rhs_global, modes, cfg, BOUNDARY_PLANE)
        port_rhs_roundtrip = global_port_rhs_from_plane(port_rhs_plane, modes, cfg, BOUNDARY_PLANE)
        np.testing.assert_allclose(port_rhs_roundtrip, port_rhs_global, rtol=tolerance, atol=1e-12)
        port_rhs_transform_gate_ratio = float(np.max(
            np.abs(port_rhs_roundtrip-port_rhs_global)
            / (tolerance*np.abs(port_rhs_global)+1e-12)))
        assert len(outputs) == 5
        assert all(len(item["raw_recovery_operation_scaled_defects"]) == 5
                   and len(item["production_recovery_operation_scaled_defects"]) == 5
                   for item in ledger)

        gate = "final unchanged live carrier digest"
        assert bundle["dtn_action"].carrier is carrier
        assert primary_gauss == carrier.assembly_context["gauss"]["compiled_forms_verified"]
        _check_loaded_primary_provenance(primary_gauss)
        after_identity = carrier_numeric_identity(carrier)
        after_digest = boundary_carrier_digest(carrier)
        assert after_identity == identity_before and after_digest == before_digest
        packet = {**base_identity, "status": "PASS_COMPONENT_ONLY", "full_case_pass": True,
            "scope": "same-live532 all-DOF coefficient/action/recovery/RHS/output components; no PDE/factor/official result",
            "degree": degree, "azimuth_deg": cfg.incident_phi_deg, "mode_count": 532,
            "carrier_digest_after": after_digest,
            "construction_numeric_inventory": dict(carrier.construction_numeric_inventory),
            "primary_compiled_gauss": primary_gauss,
            "independent_oracle_compiled_gauss": oracle_gauss,
            "incident_literal_gauss": incident_gauss, "quadrature_degree": qdegree,
            "raw_vs_centered_action_defect": _relative(accumulated["global_raw"], accumulated["plane_raw"]),
            "new_stored_vs_raw_action_defect": _relative(accumulated["new_stored"], accumulated["plane_raw"]),
            "physical_FE_RHS_literal_raw_defect": rhs_defect,
            "incident_transform_gate_ratio": incident_transform_gate_ratio,
            "nonzero_port_rhs_transform_gate_ratio": port_rhs_transform_gate_ratio,
            "per_mode": ledger, "output_component_gates": outputs,
            "completed_gates": list(LIVE_COMPONENT_GATES),
            "resource_authority": "external whole-tree/ABI/source supervision required; receipt alone is not admission"}
        write_packet(record_path, packet)
        return packet
    except Exception as error:
        write_packet(record_path.with_name("failed_live_component.json"), _failure_diagnostic({
            **base_identity, "status": "FAILED_LIVE_COMPONENT_GATE", "full_case_pass": False,
            "gate": gate, "exception_type": type(error).__name__, "exception": str(error),
            "carrier_digest_at_failure": boundary_carrier_digest(carrier),
            "completed_mode_count": len(ledger), "completed_per_mode": ledger,
            "current_mode_diagnostics": current_mode_diagnostics,
            "completed_literal_compiled_gauss": oracle_gauss,
            "evidence_classification": "partial failed evidence; no full component qualification"}))
        raise
    finally:
        raw_forms.clear()
        if (bundle["dtn_action"].carrier is not carrier
                or carrier_numeric_identity(carrier) != identity_before):
            raise RuntimeError("supplied live carrier replaced or mutated during component qualification")
