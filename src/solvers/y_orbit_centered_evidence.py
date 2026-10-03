"""Opt-in centered p2 evidence glue; reuse the qualified port/MPC formulas.

Physical generator, numerical assembly and solver coordinates have separate
identities. No quotient assembly, cutoff change or production default lives here.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np

SOURCES = ("generic", "interior_only", "physical", "notch_supported")
CENTERED_SCOPE = "fresh boundary-plane FE operator; original cutoffs and all physical contributions audited"
COMPONENT_HEAD = "a0546264ae1bcc51e2aeedcac33585f4ffc04025"
COMPONENT_SOURCE_FILES = {
    "src/solvers/dtn_boundary_phase_gauge.py": "bb0259b2b2da5656aef22d85f9fb2226118b95396276f1032d1ebfb6067bd984",
    "src/solvers/dtn_port_3d.py": "565a58133d2f86dda985ba2931536e7d63fc3c01b4616d2b4a00d4275767b0a5",
    "src/solvers/fullspace_dtn_action.py": "777d7ea10d598a7f5abba652b0de896f7040782fe7e421522c8b0e41d3f73c55",
    "src/solvers/fullspace_same_mesh_hcurl_pmg_physical.py": "2000062b8b2e09c12166d9b5f7dde97623d188a96895e96a182cf585ee4afc62",
    "src/common/modes_3d.py": "5731dc67d292b2eef854f6afdfa2a951fd5a109150cfa17f35f45c7c41cda2dd",
    "src/common/config_3d.py": "612e615f4aa5ae0411556523b9061ee47a755b8110a7c097d28b8d6f698bfc1b",
}
COMPONENT_IDENTITY = {
    "physical_generator_manifest_sha256": "4ace13f47bc6edf8a08e1a1df24309f6326294b6bf9d5ca4ada07208bd50c951",
    "assembly_mode_manifest_sha256": "6f3985dee573ca05793f81b6dc601971130201f1752af0ec6d61938dde37a820",
    "assembly_context_sha256": "2ae0fe4a4d314f706429454738439abbfca57fa1492e5a592c1205f203630714",
}
COMPONENT_RECEIPT_DIRECTORY = "docs/task40extra_dot_parallel_cloud/outcomes/records/boundary_component_v7"
COMPONENT_RECEIPT_FILES = {
    "component_qualification_a054626.json": "3fcc77a0310d5c1ecc146a80f09b72042aa7f721fa3657c1f90061f5c90e06c3",
    "source_receipt_a054626.json": "1e1bcccc52a3d7e2cb5fdee71dd8405930f3c20f2cb95eed7411d1fe53ac9a10",
    "all532_compact_ledger.json": "a100167655a1433b4a019b265a8743655144c33a3c550b3fc7cb6259a2465fef",
}


def digest_json(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def require_centered_dense_inventory(report):
    required = {"A0_original", "A_notch_original", "independent_storage_rows", "actual_interior_positions"}
    required |= {"full_mpc_"+name for name in ("slaves","masters","coefficients","offsets")}
    for name in SOURCES:
        required |= {name+"_rhs", "A0_direct_"+name, "A0_modal_"+name,
                     "notch_direct_"+name, "notch_iterative_"+name}
        for prefix in ("direct_regular_", "regular_", "direct_notch_", "notch_"):
            required |= {prefix+name+"_"+suffix for suffix in (
                "rhs_storage","solution_storage","original_action","volume_action","coupling_action",
                "auxiliary_ports","projection","normalization_h","recovered_field",
                "plane_total_auxiliary","plane_outgoing_auxiliary","plane_incident_projections",
                "direct_plane_outgoing_power_diagnostic","plane_electric","plane_magnetic",
                "mode_local_amplitude_scale","plane_electric_scale","plane_magnetic_scale","mode_power_operation_scale")}
    if (report.get("source_names") != list(SOURCES) or set(report.get("regular_sources",{})) != set(SOURCES)
            or set(report.get("notched_sources",{})) != set(SOURCES)
            or not required.issubset(report.get("artifacts",{}))):
        raise ValueError("complete required centered dense load/field/mode artifact inventory missing")
    return sorted(required)


def verify_component_sources(root, *, require_current_bytes=True):
    root = Path(root)
    for name, expected in COMPONENT_SOURCE_FILES.items():
        if require_current_bytes and hashlib.sha256((root / name).read_bytes()).hexdigest() != expected:
            raise RuntimeError("centered component numerical dependency changed: " + name)
    receipts = {}
    for name, expected in COMPONENT_RECEIPT_FILES.items():
        path = root/COMPONENT_RECEIPT_DIRECTORY/name
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise RuntimeError("actual centered component receipt hash changed: "+name)
        receipts[name] = json.loads(path.read_text())
    if receipts:
        qualification, source, ledger = (receipts[name] for name in (
            "component_qualification_a054626.json","source_receipt_a054626.json","all532_compact_ledger.json"))
        if (qualification.get("full_case_pass") is not True or qualification.get("PDE_solved") is not False
                or qualification["source_head"] != COMPONENT_HEAD or qualification["identity"] != COMPONENT_IDENTITY
                or source["head"] != COMPONENT_HEAD or source.get("clean") is not True
                or any(source["source_files"].get(k) != v for k,v in COMPONENT_SOURCE_FILES.items())
                or ledger["source_head"] != COMPONENT_HEAD or len(ledger["per_mode"]) != 532
                or ledger["original_oracle_sha256"] != "e6277e0d22eaec9cd0e4bbc40d7c44011bba3961aa3b08a081e4e398ca8e9c0b"
                or qualification["source_receipt_sha256"] != COMPONENT_RECEIPT_FILES["source_receipt_a054626.json"]
                or any(row["new_C_entries"] <= 0 or row["new_D_entries"] <= 0
                       or row["new_stored_relative_operator_bound"] > 1e-10 for row in ledger["per_mode"])):
            raise RuntimeError("actual all-mode component/source/cutoff qualification is incomplete")
    return {"component_head": COMPONENT_HEAD, "exact_unchanged_files": COMPONENT_SOURCE_FILES if require_current_bytes else {},
            "historical_source_files": COMPONENT_SOURCE_FILES,
            "current_byte_identity_required": require_current_bytes,
            "fresh_live_requalification_required": not require_current_bytes,
            "canonical_receipt_directory": COMPONENT_RECEIPT_DIRECTORY,
            "canonical_receipt_hashes": COMPONENT_RECEIPT_FILES,
            "context_rechecked_live": require_current_bytes, "PDE_qualified_by_component": False}


def require_output_packet(packet, *, label, event):
    """Preserve the guarded result before rejecting any required output stop."""
    passed = (packet.get("status") == "representable_global_output"
              and packet.get("global_output_component_consistency_checked") is True
              and packet.get("finite_plane_mode_count") == 532)
    event("required_centered_output_gate", {"label":label,"passed":passed,"packet":packet})
    if not passed:
        raise ValueError("required centered output contract stopped: "+json.dumps(packet,sort_keys=True,allow_nan=False))


def bind_native_packet(field, rhs, solution, load, independent):
    if (not np.array_equal(np.asarray(field)[independent],solution)
            or not np.array_equal(np.asarray(rhs)[independent],load)):
        raise ValueError("native solution/RHS packet is detached from actual solver vectors")
    return True


def centered_identity(bundle, *, event=None):
    from .fullspace_dtn_action import _jsonable
    carrier = bundle["dtn_action"].carrier
    actual = {key: str(bundle[key]) for key in COMPONENT_IDENTITY}
    # Diagnostic only. The acceptance expression below is unchanged. Keep
    # every actual source/config/compiled-Gauss/MPC identity before that gate.
    checks = {key: actual[key] == expected for key,expected in COMPONENT_IDENTITY.items()}
    checks.update({
        "bundle_dtn_phase_gauge": bundle.get("dtn_phase_gauge") == "boundary_plane",
        "bundle_physical_generator_mode_sha": bundle["mode_sha256"] == actual["physical_generator_manifest_sha256"],
        "carrier_assembly_manifest": carrier.mode_manifest_sha256 == actual["assembly_mode_manifest_sha256"],
        "carrier_assembly_context": carrier.assembly_context_sha256 == actual["assembly_context_sha256"],
        "all_C_D_nonempty": not any(len(e.coupling_rows)==0 or len(e.projection_rows)==0 for e in carrier.entries),
        "carrier_mode_count": len(carrier.entries) == 532,
    })
    diagnostic = {"expected_identity": COMPONENT_IDENTITY,"actual_identity":actual,
        "mismatch_keys": [key for key,passed in checks.items() if not passed],
        "all_acceptance_checks": checks,"expected_source_sha256": {Path(k).name:v for k,v in COMPONENT_SOURCE_FILES.items()},
        "actual_discrete_context": _jsonable(carrier.assembly_context),
        "actual_config": _jsonable(bundle["cfg"].as_jsonable()),
        "actual_carrier_mode_manifest_sha256": carrier.mode_manifest_sha256,
        "actual_carrier_context_sha256": carrier.assembly_context_sha256,
        "mode_count": len(carrier.entries),
        "empty_C": sum(len(e.coupling_rows)==0 for e in carrier.entries),
        "empty_D": sum(len(e.projection_rows)==0 for e in carrier.entries),
        "diagnostic_only_acceptance_unchanged": True}
    if event is not None:
        event("component_identity_before_assert",diagnostic)
    if (bundle.get("dtn_phase_gauge") != "boundary_plane" or actual != COMPONENT_IDENTITY
            or bundle["mode_sha256"] != actual["physical_generator_manifest_sha256"]
            or carrier.mode_manifest_sha256 != actual["assembly_mode_manifest_sha256"]
            or carrier.assembly_context_sha256 != actual["assembly_context_sha256"]
            or any(len(e.coupling_rows) == 0 or len(e.projection_rows) == 0 for e in carrier.entries)
            or len(carrier.entries) != 532):
        raise RuntimeError("centered fixture/source/Gauss/MPC or nonempty full port identity changed")
    return {**actual, "dtn_phase_gauge": "boundary_plane", "empty_C": 0, "empty_D": 0,
            "actual_context": _jsonable(carrier.assembly_context),
            "actual_mode_keys": [list(e.mode_key) for e in carrier.entries],
            "all_532_contributions_nonempty": True, "cutoffs_unchanged": True}


def fixture_interior_positions(space, layout, *, direct_profile=None, fresh_fixture_c1=False):
    local = np.asarray(space.element.basix_element.entity_dofs[3][0], dtype=np.int64)
    rows = np.unique(np.concatenate([np.asarray(space.dofmap.cell_dofs(c))[local]
            for c in range(int(space.mesh.topology.index_map(3).size_local))]))
    positions = np.flatnonzero(np.isin(layout.independent, rows))
    degree = int(space.element.basix_element.degree)
    expected = {2:480,4:8640}.get(degree)
    if type(fresh_fixture_c1) is not bool:
        raise TypeError('fresh C1 opt-in must be an explicit bool')
    if fresh_fixture_c1:
        if (direct_profile is not None or degree != 6 or len(local) != 450
                or int(space.element.space_dimension) != 882
                or int(space.mesh.topology.index_map(3).size_local) != 80
                or layout.full_rows != 55950 or len(layout.independent) != 52992
                or len(np.unique(layout.independent)) != 52992):
            raise ValueError('fresh C1 p6 requires its complete actual same80 native interior inventory')
        expected = 36000
    if direct_profile is not None:
        from .y_orbit_direct_profile import direct_profile_metadata
        profile=direct_profile_metadata(direct_profile)
        if profile.name not in ('X','XZ','Y') or degree!=4 or layout.full_rows!=profile.storage_rows:
            raise ValueError('only the admitted directX/XZ/Y full original interior inventory is enabled')
        expected=profile.interior_rows
    if expected is None or len(positions) != expected or len(rows) != expected:
        raise ValueError("centered profile must retain every actual p2/p4 interior row")
    return positions


def interior_only_rhs(space, layout, *, direct_profile=None):
    positions = fixture_interior_positions(space, layout, direct_profile=direct_profile)
    rhs = np.zeros(len(layout.independent), dtype=np.complex128)
    j = np.arange(len(positions))
    rhs[positions] = np.cos(.29*j) + 1j*np.sin(.43*j)
    rhs /= np.linalg.norm(rhs)
    if np.any(rhs[positions] == 0):
        raise ValueError("every actual interior row must have a nonzero load")
    return rhs


def save_mpc_inventory(bundle, layout, save):
    from .y_orbit_condensed_adapter import _mpc_expansion_width
    mpc = bundle["setup"]["floquets"][int(bundle["degree"])].mpc
    _mpc_expansion_width(mpc, layout.full_rows)
    coefficients, offsets = mpc.coefficients()
    for name, value in (("slaves", mpc.slaves), ("masters", mpc.masters.array),
                        ("coefficients", coefficients), ("offsets", offsets)):
        save("full_mpc_" + name, value)


def save_centered_port_inventory(bundle, layout, save, *, allocation_gate):
    """Export actual original C/D functionals and mode vectors for the p4 checker.

    Column C and row D naturally use CSC/CSR. No global FE square matrix is
    formed, and every retained functional is exported before temporary release.
    """
    from petsc4py import PETSc
    from .y_orbit_sparse_reference import integer_admission
    entries = bundle["dtn_action"].carrier.entries
    carrier = bundle["dtn_action"].carrier
    ports = len(entries)
    for kind, row_name, value_name in (("C", "coupling_rows", "coupling_values"),
                                        ("D", "projection_rows", "projection_values")):
        count = sum(len(getattr(e, row_name)) for e in entries)
        integer_admission((layout.full_rows, ports), count, index_dtype=PETSc.IntType)
        row_dtype = np.asarray(getattr(entries[0],row_name)).dtype
        if any(np.asarray(getattr(e,row_name)).dtype != row_dtype for e in entries):
            raise ValueError("original carrier row widths differ across modes")
        integer_admission((layout.full_rows,ports),count,index_dtype=row_dtype)
        size = count*(16+row_dtype.itemsize)+(ports+1)*np.dtype(PETSc.IntType).itemsize
        allocation_gate("original_"+kind+"_checker_export",{
            "matrix_payload_bytes": size, "workspace_bytes": size,
            "complete_original_functionals": True, "no_global_FE_square_matrix": True})
        for e in entries:
            rows = np.asarray(getattr(e, row_name))
            if (rows.dtype.kind not in "iu" or not len(rows) or rows.min()<0
                    or rows.max()>=layout.full_rows):
                raise ValueError("every original centered port must have valid native support")
        save("original_port_"+kind+"_indices", np.concatenate(
             [getattr(e,row_name) for e in entries]))
        save("original_port_"+kind+"_data", np.concatenate([getattr(e,value_name) for e in entries]))
        save("original_port_"+kind+"_indptr",np.asarray(
             [0]+list(np.cumsum([len(getattr(e,row_name)) for e in entries],dtype=np.int64)),dtype=PETSc.IntType))
    cfg = bundle["cfg"]
    save("original_mode_e_vectors",np.asarray([m.e_vector for m in bundle["modes"]],dtype=complex))
    save("original_mode_k_vectors",np.asarray([m.k_vector for m in bundle["modes"]],dtype=complex))
    save("original_mode_outward_signs",np.asarray([1 if m.side=="top" else -1 for m in bundle["modes"]]))
    save("original_mode_magnetic_denominator",np.asarray(cfg.k0*complex(cfg.mu_r)))
    save("original_mode_boundary_area",np.asarray((cfg.x_max-cfg.x_min)*(cfg.y_max-cfg.y_min)))
    save("original_mode_incident_projections",np.asarray(bundle["incident_projections"]))
    save("original_carrier_global_rows",np.asarray(carrier.global_rows))
    save("original_carrier_ownership_range",np.asarray(carrier.ownership_range))
    save("original_carrier_slave_rows",carrier.slave_rows)


def recovered_field_and_modes(bundle, layout, solution, *, physical, label, save):
    from dolfinx import fem
    from .dtn_boundary_phase_gauge import prepare_boundary_plane_outputs
    from .fullspace_dtn_action import _jsonable
    degree = int(bundle["degree"])
    floquet = bundle["setup"]["floquets"][degree]
    space = bundle["setup"]["spaces"][degree]
    field = fem.Function(space, name="centered_full3D_total")
    field.x.array[:] = 0
    field.x.array[layout.independent] = solution
    field.x.scatter_forward()
    # Auxiliary recovery consumes original zero-slave coordinates.
    alpha = bundle["dtn_action"].recover_auxiliary(field.x.petsc_vec).copy()
    carrier = bundle["dtn_action"].carrier
    projection_scale = np.asarray([np.linalg.norm(e.projection_values)/e.normalization_h
                                   for e in carrier.entries]) * np.linalg.norm(solution)
    incident = np.asarray(bundle["incident_projections"] if physical else np.zeros(len(alpha)))
    output = prepare_boundary_plane_outputs(alpha, incident, bundle["modes"], bundle["cfg"])
    floquet.mpc.homogenize(field); field.x.scatter_forward()
    floquet.mpc.backsubstitution(field); field.x.scatter_forward()
    save(label + "_recovered_field", field.x.array.copy())
    save(label + "_mode_local_amplitude_scale", projection_scale)
    for key in ("plane_total_auxiliary", "plane_incident_projections", "plane_outgoing_auxiliary",
                "direct_plane_outgoing_power_diagnostic", "global_total_auxiliary", "global_incident_projections"):
        if key in output:
            save(label + "_" + key, output.pop(key))
    outgoing = alpha - incident
    evectors = np.asarray([m.e_vector for m in bundle["modes"]], dtype=complex)
    kvectors = np.asarray([m.k_vector for m in bundle["modes"]], dtype=complex)
    electric = outgoing[:, None]*evectors
    magnetic = np.cross(kvectors, electric)/(bundle["cfg"].k0*complex(bundle["cfg"].mu_r))
    save(label + "_plane_electric", electric); save(label + "_plane_magnetic", magnetic)
    save(label + "_plane_electric_scale", projection_scale*np.linalg.norm(evectors, axis=1))
    save(label + "_plane_magnetic_scale", projection_scale*np.linalg.norm(
         np.cross(kvectors, evectors)/(bundle["cfg"].k0*complex(bundle["cfg"].mu_r)), axis=1))
    save(label + "_mode_power_operation_scale", .5*(bundle["cfg"].x_max-bundle["cfg"].x_min)*
         (bundle["cfg"].y_max-bundle["cfg"].y_min)*(projection_scale+np.abs(incident))**2*
         np.linalg.norm(evectors, axis=1)*np.linalg.norm(
         np.cross(kvectors, evectors)/(bundle["cfg"].k0*complex(bundle["cfg"].mu_r)), axis=1))
    return _jsonable({**output, "finite_plane_mode_count": len(alpha), "actual_degree": degree,
                      "full_physical_field_recovered": True, "official_results": False})


def original_packet(bundle, layout, rhs, solution, *, label, save, alpha=None):
    from .y_orbit_condensed_adapter import audit_original_solution
    view = SimpleNamespace(action_bundle=bundle, system=SimpleNamespace(full_rows=layout.full_rows),
             floquet=bundle["setup"]["floquets"][int(bundle["degree"])],
             carrier=bundle["dtn_action"].carrier, apply_storage=bundle["physical_action"].apply)
    packet = audit_original_solution(view, layout, rhs, solution,
                                    auxiliary_ports=alpha, return_vectors=True)
    for name, values in packet.pop("vectors").items():
        save(label + "_" + name, values)
    packet["solution_primal_q_norms"] = layout.modal_norms(solution, dual=False)
    return packet


def compare_mode_evidence(candidate_load, authority_load, label):
    """Every mode uses its own coefficient/operation scale, including cancellation.

    No maximum amplitude across modes, invented absolute floor or zero filling.
    Nonzero error at a zero local operation scale is an explicit failure.
    """
    checks = {}
    for name, scale_name in (("plane_total_auxiliary", "mode_local_amplitude_scale"),
        ("plane_outgoing_auxiliary", "mode_local_amplitude_scale"),
        ("plane_electric", "plane_electric_scale"), ("plane_magnetic", "plane_magnetic_scale"),
        ("direct_plane_outgoing_power_diagnostic", "mode_power_operation_scale")):
        actual, expected = candidate_load(label+"_"+name), authority_load(label+"_"+name)
        scales = candidate_load(label+"_"+scale_name) + authority_load(label+"_"+scale_name)
        if actual.shape != expected.shape or len(actual) != 532 or scales.shape != (532,):
            raise ValueError("complete centered per-mode output inventory differs")
        error = np.abs(actual-expected) if actual.ndim == 1 else np.linalg.norm(actual-expected, axis=1)
        if not np.isfinite(error).all() or not np.isfinite(scales).all() or np.any(scales < 0):
            raise ValueError("invalid finite-plane per-mode output diagnostic")
        ratios = np.divide(error, scales, out=np.zeros_like(error, dtype=float), where=scales != 0)
        if np.any((scales == 0) & (error != 0)):
            raise ValueError("nonzero output error has zero local operation scale")
        worst = int(np.argmax(ratios))
        checks[name] = {"relative_local_operation_error_max": float(ratios[worst]),
                       "worst_mode_index": worst, "limit": 1e-10,
                       "passed": bool(ratios[worst] <= 1e-10), "compared_modes": 532}
    return checks
