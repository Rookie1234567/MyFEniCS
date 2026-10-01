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


def qualify_boundary_plane_bundle(bundle, *, record_path,
                                   expected_physical_manifest, expected_ordered_keys,
                                   seed=4053202, tolerance=1e-10,
                                   optional_legacy_bundle=None):
    """Qualify exactly this supplied live p2/MPI1/532-mode carrier before factors.

    ``expected_ordered_keys`` uses complete carrier keys
    ``(index, side, m, n, polarization)``. The fixed physical contract is
    required independently of the mutable process-specific loaded-C identity.
    Each rebuilt dense/sparse carrier needs its own receipt; pairing receipts
    additionally requires fixed-contract equality and full-column controls.
    ``optional_legacy_bundle`` preserves historical test comparisons only.
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
    if tolerance != 1e-10 or seed != 4053202:
        raise ValueError("this admitted p2 component contract fixes tolerance/seed")
    new, old = bundle, optional_legacy_bundle
    carrier = new["dtn_action"].carrier
    identity_before = carrier_numeric_identity(carrier)
    before_digest = identity_before["carrier_numeric_sha256"]
    record_path = Path(record_path)
    if any(path.exists() for path in (record_path, record_path.with_name("partial_components.json"),
            record_path.with_name("failed_output_packet.json"), record_path.with_name("failed_live_component.json"))):
        raise ValueError("component evidence already exists; use a fresh artifact directory")
    record_path.parent.mkdir(parents=True, exist_ok=True)
    raw_forms = {}
    ledger, oracle_gauss = [], {}
    current_mode_diagnostics = None
    gate = "live input/identity"
    def write_packet(path, packet):
        path.write_text(json.dumps(_jsonable(packet), indent=2, allow_nan=False)+"\n")
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
        cfg, levels = new["cfg"], new["setup"]
        assert new["dtn_phase_gauge"] == BOUNDARY_PLANE
        assert int(new["degree"]) == 2
        modes = tuple(new["modes"])
        assert len(modes) == len(carrier.entries) == 532
        assert new["mode_sha256"] == expected_physical_manifest == carrier.physical_generator_manifest_sha256
        expected_keys = tuple(tuple(key) for key in expected_ordered_keys)
        actual_keys = tuple(entry.mode_key for entry in carrier.entries)
        semantic_keys = tuple((index, mode.side, mode.m, mode.n, mode.polarization)
                              for index, mode in enumerate(modes))
        assert actual_keys == expected_keys == semantic_keys
        assert len(set(actual_keys)) == 532
        assert all(len(entry.coupling_rows) and len(entry.projection_rows) for entry in carrier.entries)
        assert cfg.stage4_dtn_order_policy == "manual"
        assert cfg.diffraction_order_max_m == 9 and cfg.diffraction_order_max_n == 3
        assert new["assembly_context_sha256"] == carrier.assembly_context_sha256
        assert new["assembly_mode_manifest_sha256"] == carrier.mode_manifest_sha256
        assert carrier.assembly_context_sha256 == hashlib.sha256(_canonical_json_bytes(carrier.assembly_context)).hexdigest()
        assert carrier.construction_numeric_inventory["unique_named_numpy_backing_bytes_before_staging_release"] <= 512 << 20
        new_carrier = carrier
        old_carrier = old["dtn_action"].carrier if old is not None else None
        if old is not None:
            assert old["mode_sha256"] == new["mode_sha256"]
            assert tuple(entry.mode_key for entry in old_carrier.entries) == actual_keys
            assert old["dtn_quadrature_degree"] == new["dtn_quadrature_degree"]
        V, mpc, mesh_data = levels["spaces"][2], levels["floquets"][2].mpc, levels["mesh_data"]
        n = int(V.dofmap.index_map.size_global)
        qdegree = int(new["dtn_quadrature_degree"])
        assert carrier.ownership_range == (0, n)
        assert carrier.assembly_context["gauss"]["degree"] == qdegree
        primary_gauss = new["compiled_surface_gauss_identity"]
        assert primary_gauss == carrier.assembly_context["gauss"]["compiled_forms_verified"]
        _check_loaded_primary_provenance(primary_gauss)
        for identity in primary_gauss.values():
            assert identity["loaded_kernel"]["restoration_exact"]
            assert identity["loaded_kernel"]["numerical_assembly_during_probe"] is False
            assert identity["loaded_kernel"]["num_constants"] == 3
            assert tuple(item["role"] for item in identity["loaded_kernel"]["constant_roles"]) == ("alpha", "gamma", "kz")
        rng = np.random.default_rng(seed)
        states = rng.normal(size=(n, 5))+1j*rng.normal(size=(n, 5))
        states[np.asarray(mpc.slaves, dtype=np.int64)] = 0
        assert states.nbytes <= 512 << 20
        labels = ("global_raw", "plane_raw", "new_stored")+( ("old_stored",) if old is not None else ())
        accumulated = {name: np.zeros_like(states) for name in labels}
        recovery_labels = ("new_stored", "plane_raw")+( ("old_stored",) if old is not None else ())
        expected_recovery = {name: np.zeros((532, 5), dtype=np.complex128) for name in recovery_labels}
        recovery_coefficient_scales = {name: np.zeros(532) for name in recovery_labels}
        raw_incident_rhs = np.zeros(n, dtype=np.complex128)
        vector_cache = component_key = None
        gate = "compiled literal Gauss"
        # Independent literal UFL forms, same integral Gauss metadata and full
        # actual MPC. No primary surface/coefficient builder is called here.
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
                    assert oracle_identity["rules"] == primary_identity["rules"]
                    oracle_gauss[f"{gauge}/{side}/{component}"] = oracle_identity
                    raw_forms[(gauge, side, component)] = (alpha, gamma, kz, compiled)

        def dense_entry(entry, side):
            result = np.zeros(n, dtype=np.complex128)
            rows = entry.coupling_rows if side == "C" else entry.projection_rows
            values = entry.coupling_values if side == "C" else entry.projection_values
            result[rows] = values
            return result

        def loss_bound(C, D, Cref, Dref, H):
            # Stable full-DOF rank-one norm bound, without N×N matrices or
            # subtracting two nearly equal squared Frobenius expressions.
            return float((np.linalg.norm(C-Cref)*np.linalg.norm(D)
                         + np.linalg.norm(Cref)*np.linalg.norm(D-Dref))/H)

        for index, (mode, new_entry) in enumerate(zip(modes, new_carrier.entries, strict=True)):
            gate = f"all-mode coefficients/action/port equation index={index}"
            current_mode_diagnostics = {"index": index, "key": new_entry.mode_key,
                                        "status": "INCOMPLETE_UNQUALIFIED_MODE", "measurements": {}}
            old_entry = old_carrier.entries[index] if old_carrier is not None else None
            key = (mode.side, mode.m, mode.n, complex(mode.k_vector[2]))
            if key != component_key:
                vector_cache = {}
                for gauge in (GLOBAL_Z, BOUNDARY_PLANE):
                    components = []
                    for component in (0, 1):
                        alpha, gamma, kz, form = raw_forms[(gauge, mode.side, component)]
                        for constant, value in ((alpha, mode.alpha), (gamma, mode.gamma), (kz, mode.k_vector[2])):
                            _set_scalar_constant(constant, value)
                        raw = _assemble_mpc_form_vector(form, mpc)
                        try:
                            owned = raw.getOwnershipRange()
                            assert owned == (0, n)
                            components.append(np.asarray(raw.getArray(readonly=True), dtype=np.complex128).copy())
                        finally:
                            raw.destroy()
                    vector_cache[gauge] = components
                component_key = key
            gx, gy = vector_cache[GLOBAL_Z]
            px, py = vector_cache[BOUNDARY_PLANE]
            t = _traction_vector(mode, cfg)
            Cg, Cp = -t[0]*gx-t[1]*gy, -t[0]*px-t[1]*py
            Dg = np.conjugate(mode.e_vector[0]*gx+mode.e_vector[1]*gy)
            Dp = np.conjugate(mode.e_vector[0]*px+mode.e_vector[1]*py)
            z = cfg.physical_z_max if mode.side == "top" else cfg.physical_z_min
            s = complex(np.exp(1j*mode.k_vector[2]*z))
            current_mode_diagnostics["measurements"]["global_boundary_phase"] = s
            assert np.isfinite(s) and s != 0  # Honest bounded pilot representability gate.
            H = (cfg.x_max-cfg.x_min)*(cfg.y_max-cfg.y_min)*mode.electric_tangential_norm_sq
            Cgn, Dgn = Cg/s, Dg/np.conjugate(s)
            Hg = _mode_projection_denominator(mode, cfg)
            errors = {"raw_C_equivalence": _relative(Cgn, Cp), "raw_D_equivalence": _relative(Dgn, Dp),
                      "raw_H_equivalence": abs(Hg/(abs(s)**2)-H)/H}
            current_mode_diagnostics["measurements"].update({"raw_equivalence": errors.copy(),
                "Hglobal": Hg, "Hplane": H, "stored_Hplane": new_entry.normalization_h,
                "raw_C_norm": float(np.linalg.norm(Cp)), "raw_D_norm": float(np.linalg.norm(Dp))})
            assert all(value <= 1e-10 for value in errors.values()), (index, errors)
            assert abs(new_entry.normalization_h-H) <= 1e-14*H
            if old_entry is not None:
                C_old, D_old = dense_entry(old_entry, "C")/s, dense_entry(old_entry, "D")/np.conjugate(s)
            C_new, D_new = dense_entry(new_entry, "C"), dense_entry(new_entry, "D")
            if old_entry is not None:
                expected_recovery["old_stored"][index] = (D_old@states/H)/s
            expected_recovery["new_stored"][index] = D_new@states/H
            expected_recovery["plane_raw"][index] = Dp@states/H
            if old_entry is not None:
                recovery_coefficient_scales["old_stored"][index] = np.linalg.norm(D_old)/(H*abs(s))
            recovery_coefficient_scales["new_stored"][index] = np.linalg.norm(D_new)/H
            recovery_coefficient_scales["plane_raw"][index] = np.linalg.norm(Dp)/H
            actions = {}
            coefficient_sets = [("global_raw", Cgn, Dgn), ("plane_raw", Cp, Dp), ("new_stored", C_new, D_new)]
            if old_entry is not None:
                coefficient_sets.append(("old_stored", C_old, D_old))
            for name, C, D in coefficient_sets:
                actions[name] = C[:, None]*(D@states)[None, :]/H
                accumulated[name] += actions[name]
            errors["per_mode_raw_action_equivalence"] = _relative(actions["global_raw"], actions["plane_raw"])
            current_mode_diagnostics["measurements"]["per_mode_raw_action_equivalence"] = errors["per_mode_raw_action_equivalence"]
            assert errors["per_mode_raw_action_equivalence"] <= 1e-10
            reference_norm = float(np.linalg.norm(Cp)*np.linalg.norm(Dp)/H)
            new_loss = loss_bound(C_new, D_new, Cp, Dp, H)
            normalized_loss = new_loss/reference_norm if reference_norm else (0 if new_loss == 0 else float("inf"))
            current_mode_diagnostics["measurements"].update({"raw_rank_one_Frobenius_norm": reference_norm,
                "new_stored_loss_bound": new_loss, "new_stored_relative_operator_bound": normalized_loss})
            assert normalized_loss <= 1e-10, (index, "all-DOF coefficient certificate", normalized_loss)
            # Audit each unchanged sparsification stage independently. This is
            # an oracle policy application, not a production cutoff override.
            cutoffs = {}
            for label, components in (("global", (gx, gy)), ("plane", (px, py))):
                filtered = []
                component_counts = []
                for component in components:
                    cutoff = max(1e-30, 1e-13*float(np.max(np.abs(component))))
                    mask = np.abs(component) > cutoff
                    filtered.append(np.where(mask, component, 0))
                    component_counts.append({"raw_nonzero": int(np.count_nonzero(component)),
                                             "retained": int(np.count_nonzero(mask)), "cutoff": cutoff})
                Ccombined = -t[0]*filtered[0]-t[1]*filtered[1]
                Dcombined = np.conjugate(mode.e_vector[0]*filtered[0]+mode.e_vector[1]*filtered[1])
                cutoffs[label] = {"components": component_counts,
                                  "combined_C_cutoff": max(1e-30, 1e-13*float(np.max(np.abs(Ccombined)))),
                                  "combined_D_cutoff": max(1e-30, 1e-13*float(np.max(np.abs(Dcombined))))}
            # Full raw augmented port equation with an independent b and
            # nonzero rp: row scaling must use conjugate(s), not s.
            b = rng.normal(size=5) + 1j*rng.normal(size=5)
            rp_plane = H*b-Dp@states
            rp_global = Hg*(b/s)-Dg@states
            port_equation_defect = _relative(rp_global/np.conjugate(s), rp_plane)
            current_mode_diagnostics["measurements"]["raw_nonzero_port_equation_defect"] = port_equation_defect
            assert port_equation_defect <= 1e-10
            incident_g = incident_projection_in_solver_coordinates(mode, cfg, GLOBAL_Z)
            incident_p = incident_projection_in_solver_coordinates(mode, cfg, BOUNDARY_PLANE)
            raw_incident_rhs += Cp*incident_p
            total_p = (Dp@states[:, 0])/H
            outgoing_p = total_p-incident_p if mode.side == "top" else total_p
            outgoing_g = (total_p/s)-incident_g if mode.side == "top" else total_p/s
            plane_power = boundary_mode_power_from_solver(mode, cfg, outgoing_p, BOUNDARY_PLANE)
            global_power = boundary_mode_power_from_solver(mode, cfg, outgoing_g, GLOBAL_Z)
            Eplane = outgoing_p*np.asarray(mode.e_vector)
            Hplane = np.cross(mode.k_vector, Eplane)/(cfg.k0*complex(cfg.mu_r))
            power_scale = 0.5*(cfg.x_max-cfg.x_min)*(cfg.y_max-cfg.y_min)*np.linalg.norm(Eplane)*np.linalg.norm(Hplane)
            power_error = abs(plane_power-global_power)/power_scale if power_scale else (0 if plane_power == global_power else float("inf"))
            current_mode_diagnostics["measurements"].update({"plane_outgoing_power": plane_power,
                "global_outgoing_power": global_power, "power_operation_scaled_defect": power_error})
            assert power_error <= 1e-10
            ledger.append({
                "index": index, "key": list(new_entry.mode_key),
                "log_abs_s": float(np.log(abs(s))), "Hglobal": float(Hg), "Hplane": float(H),
                "raw_C_norm": float(np.linalg.norm(Cp)), "raw_D_norm": float(np.linalg.norm(Dp)),
                "raw_rank_one_Frobenius_norm": reference_norm,
                "old_C_entries": (len(old_entry.coupling_rows) if old_entry is not None else None), "old_D_entries": (len(old_entry.projection_rows) if old_entry is not None else None),
                "new_C_entries": len(new_entry.coupling_rows), "new_D_entries": len(new_entry.projection_rows),
                "old_stored_loss_bound": loss_bound(C_old, D_old, Cp, Dp, H) if old_entry is not None else None,
                "new_stored_loss_bound": new_loss, "new_stored_relative_operator_bound": normalized_loss,
                "both_sparsification_stages": cutoffs,
                "plane_outgoing_power": plane_power, "global_outgoing_power": global_power,
                "power_operation_scaled_defect": float(power_error),
                "global_component_cutoffs": [max(1e-30, 1e-13*float(np.max(np.abs(v)))) for v in (gx, gy)],
                "plane_component_cutoffs": [max(1e-30, 1e-13*float(np.max(np.abs(v)))) for v in (px, py)],
                "equivalence": errors,
                "old_empty_does_not_prove_physical_zero": (not len(old_entry.coupling_rows) or not len(old_entry.projection_rows)) if old_entry is not None else None,
            })
            current_mode_diagnostics = None
        assert len(ledger) == 532
        assert _relative(accumulated["global_raw"], accumulated["plane_raw"]) <= 1e-10
        assert _relative(accumulated["new_stored"], accumulated["plane_raw"]) <= 1e-10
        if record_path is not None:
            from src.solvers.fullspace_dtn_action import _jsonable
            partial = {"status": "PARTIAL_COMPONENT_EVIDENCE", "full_case_pass": False,
                       "completed": ["532 raw coefficient/H equivalence", "per-mode all-DOF rank-one bounds",
                                     "five arbitrary-state accumulated action probes", "compiled primary/oracle Gauss binding"],
                       "pending": ["production recovery", "output component", "physical RHS", "nonzero port RHS"],
                       "physical_generator_manifest_sha256": new["mode_sha256"],
                       "assembly_mode_manifest_sha256": new_carrier.mode_manifest_sha256,
                       "assembly_context_sha256": new_carrier.assembly_context_sha256,
                       "primary_compiled_gauss": new["compiled_surface_gauss_identity"],
                       "oracle_compiled_gauss": oracle_gauss, "per_mode": ledger,
                       "probe_scope": "not a certified relative norm of the summed operator", "PDE_solved": False}
            record_path.with_name("partial_components.json").write_text(json.dumps(_jsonable({**base_identity, **partial}), indent=2, allow_nan=False)+"\n")
        output_component_gates = []
        # Verify actual primary actions against the independent accumulated
        # all-mode oracle, including arbitrary full FE states/interior DOFs.
        qualified_bundles = [(new, "new_stored")]+([(old, "old_stored")] if old is not None else [])
        for active_bundle, label in qualified_bundles:
            gate = "production action/recovery/output "+label
            for column in range(states.shape[1]):
                source = PETSc.Vec().createSeq(n, comm=PETSc.COMM_SELF)
                target = source.duplicate()
                try:
                    source.array[:] = states[:, column]; source.assemble()
                    active_bundle["dtn_action"].apply(source, target)
                    assert _relative(target.array, accumulated[label][:, column]) <= 1e-10
                    recovered = active_bundle["dtn_action"].recover_auxiliary(source)
                    assert _relative(recovered, expected_recovery[label][:, column]) <= 1e-10
                    for index, observed in enumerate(recovered):
                        expected = expected_recovery[label][index, column]
                        scale = recovery_coefficient_scales[label][index]*np.linalg.norm(states[:, column])
                        defect = float(abs(observed-expected)/scale) if scale else (0.0 if observed == expected else float("inf"))
                        ledger[index].setdefault("production_recovery_operation_scaled_defects", {}).setdefault(label, []).append(defect)
                        assert defect <= tolerance, (label, index, "per-entry stored recovery")
                    if label == "new_stored":
                        assert _relative(recovered, expected_recovery["plane_raw"][:, column]) <= 1e-10
                        for index, observed in enumerate(recovered):
                            expected = expected_recovery["plane_raw"][index, column]
                            scale = recovery_coefficient_scales["plane_raw"][index]*np.linalg.norm(states[:, column])
                            defect = float(abs(observed-expected)/scale) if scale else (0.0 if observed == expected else float("inf"))
                            ledger[index].setdefault("raw_recovery_operation_scaled_defects", []).append(defect)
                            assert defect <= tolerance, (index, "per-entry raw recovery")
                        # Lower-level consistency only: arbitrary test fields
                        # have no PDE residual/official power qualification.
                        output = prepare_boundary_plane_outputs(
                            recovered, new["incident_projections"], modes, cfg)
                        if output["status"] != "representable_global_output":
                            from src.solvers.fullspace_dtn_action import _jsonable
                            failure = {"status": "FAILED_OUTPUT_COMPONENT_GATE", "full_case_pass": False,
                                       "arbitrary_state_column": column, "packet": output, "PDE_solved": False}
                            record_path.with_name("failed_output_packet.json").write_text(
                                json.dumps(_jsonable(_failure_diagnostic(failure)), indent=2, allow_nan=False)+"\n")
                        assert output["status"] == "representable_global_output", output.get("global_output_failure")
                        assert output["global_output_component_consistency_checked"]
                        assert output["official_results"] is False
                        output_component_gates.append({"arbitrary_state_column": column, "mode_count": len(modes),
                            "status": output["status"], "global_output_component_consistency_checked": True,
                            "official_results": False, "analytic_zero_power_checks": output.get("analytic_zero_power_checks", [])})
                finally:
                    target.destroy(); source.destroy()
        gate = "physical FE RHS independent literal oracle"
        k_inc = np.asarray(cfg.wavevector, dtype=np.complex128)
        e_inc = complex(cfg.incident_amplitude)*np.asarray(cfg.polarization_vector, dtype=np.complex128)
        traction_inc = np.cross(1j*np.cross(k_inc, e_inc), np.asarray([0., 0., 1.]))
        x = ufl.SpatialCoordinate(mesh_data.mesh)
        phase_inc = ufl.exp(PETSc.ScalarType(1j)*(PETSc.ScalarType(k_inc[0])*x[0]
                             +PETSc.ScalarType(k_inc[1])*x[1]+PETSc.ScalarType(k_inc[2])*x[2]))
        literal_incident = ufl.inner(ufl.as_vector(tuple(PETSc.ScalarType(value)*phase_inc
                                    for value in traction_inc)), ufl.TestFunction(V))*ufl.Measure(
                                    "ds", domain=mesh_data.mesh, subdomain_data=mesh_data.facet_tags)(cfg.tags.z_max)
        compiled_incident = fem.form(_with_quadrature_degree(literal_incident, qdegree),
                                     jit_options=SAME_MESH_JIT_OPTIONS)
        incident_gauss = compiled_surface_quadrature_identity(
            _with_quadrature_degree(literal_incident, qdegree), compiled_incident)
        assert incident_gauss["rules"] == primary_gauss["top/0"]["rules"]
        raw_base = _assemble_mpc_form_vector(compiled_incident, mpc)
        new_rhs = old_rhs = None
        try:
            expected_rhs = np.asarray(raw_base.getArray(readonly=True), dtype=np.complex128)+raw_incident_rhs
            new_rhs, _ = build_physical_rhs(new)
            rhs_defect = _relative(new_rhs.array, expected_rhs)
            assert rhs_defect <= tolerance
            if old is not None:
                old_rhs, _ = build_physical_rhs(old)
                assert _relative(old_rhs.array, new_rhs.array) <= tolerance
        finally:
            if old_rhs is not None:
                old_rhs.destroy()
            if new_rhs is not None:
                new_rhs.destroy()
            raw_base.destroy()
        gate = "incident and arbitrary nonzero port RHS transforms"
        incident_global = np.asarray([incident_projection_in_solver_coordinates(mode, cfg, GLOBAL_Z) for mode in modes])
        incident_plane = np.asarray(new["incident_projections"])
        np.testing.assert_allclose(solver_amplitudes_from_global(incident_global, modes, cfg, BOUNDARY_PLANE),
                                   incident_plane, rtol=tolerance, atol=1e-12)
        port_rhs_global = rng.normal(size=(532, 5))+1j*rng.normal(size=(532, 5))
        port_rhs_plane = plane_port_rhs_from_global(port_rhs_global, modes, cfg, BOUNDARY_PLANE)
        np.testing.assert_allclose(global_port_rhs_from_plane(port_rhs_plane, modes, cfg, BOUNDARY_PLANE),
                                   port_rhs_global, rtol=tolerance, atol=1e-12)
        assert len(output_component_gates) == 5
        assert all(len(entry["raw_recovery_operation_scaled_defects"]) == 5
                   and len(entry["production_recovery_operation_scaled_defects"]["new_stored"]) == 5 for entry in ledger)
        gate = "final unchanged live carrier digest"
        assert new["dtn_action"].carrier is carrier
        assert primary_gauss == carrier.assembly_context["gauss"]["compiled_forms_verified"]
        _check_loaded_primary_provenance(primary_gauss)
        after_digest = boundary_carrier_digest(carrier)
        assert carrier_numeric_identity(carrier) == identity_before
        assert after_digest == before_digest
        packet = {**base_identity,
            "status": "PASS_COMPONENT_ONLY", "full_case_pass": True,
            "scope": "same-live532 all-DOF coefficient/action/recovery/RHS/output components; no PDE/factor/official result",
            "degree": 2, "azimuth_deg": cfg.incident_phi_deg, "mode_count": 532,
            "carrier_digest_after": after_digest,
            "construction_numeric_inventory": dict(carrier.construction_numeric_inventory),
            "primary_compiled_gauss": primary_gauss, "independent_oracle_compiled_gauss": oracle_gauss,
            "incident_literal_gauss": incident_gauss,
            "quadrature_degree": qdegree,
            "raw_vs_centered_action_defect": _relative(accumulated["global_raw"], accumulated["plane_raw"]),
            "new_stored_vs_raw_action_defect": _relative(accumulated["new_stored"], accumulated["plane_raw"]),
            "old_vs_new_stored_action_change": _relative(accumulated["old_stored"], accumulated["new_stored"]) if old is not None else None,
            "physical_FE_RHS_literal_raw_defect": rhs_defect, "per_mode": ledger,
            "output_component_gates": output_component_gates,
            "completed_gates": list(LIVE_COMPONENT_GATES),
            "resource_authority": "external whole-tree/ABI/source supervision required; receipt alone is not admission",
        }
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
            "evidence_classification": "partial failed evidence; no full component qualification",
        }))
        raise
    finally:
        raw_forms.clear()
        if new["dtn_action"].carrier is not carrier or carrier_numeric_identity(carrier) != identity_before:
            raise RuntimeError("supplied live carrier replaced or mutated during component qualification")
