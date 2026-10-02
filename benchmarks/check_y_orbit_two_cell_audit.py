"""Independent saved-evidence checker for Q0--Q2, without solve or FFCx build.

Every four-q CSR entry and all twelve ordered off-diagonal blocks are checked.
Raw component receipts retain their narrower audit-only qualification.
"""
from __future__ import annotations

import argparse
import cmath
import json
import math
import os
from pathlib import Path
import sys
import traceback

from benchmarks.y_orbit_two_cell_authority import (
    AUTHORITY_RUN, PHYSICAL_MANIFEST, Q_ROWS, SavedFullP4Authority,
    bound_path, digest_json, file_sha, validate_supervision,
)


PASS = "QUOTIENT_OPERATOR_AUDIT_PASS"
SCHEMA = "task40extra.y-orbit-two-cell-operator-audit.v1"
RESERVE_BYTES = 128 * 1024**2
TREE_CAP_BYTES = 3 * 1024**3 // 2


def number(value):
    if isinstance(value, dict) and set(value) == {"real", "imag"}:
        result = complex(value["real"], value["imag"])
    elif isinstance(value, (list, tuple)) and len(value) == 2:
        result = complex(*value)
    else:
        result = complex(value)
    if not math.isfinite(result.real) or not math.isfinite(result.imag):
        raise ValueError("finite complex identity is required")
    return result


def expected_sector_keys(keys, indices):
    """Raw receipt keys have four fields; original indices are bound separately."""
    selected = [list(keys[i]) for i in indices]
    if any(len(key) != 4 for key in selected):
        raise ValueError("original side/m/n/polarization keys must contain four fields")
    return selected


def validate_local_row_partition(independent, trace, interior, slaves):
    """Exact native storage partition; interior cell iteration need not be sorted."""
    groups = (independent, trace, interior, slaves)
    if tuple(map(len, groups)) != (7936, 3616, 4320, 1004):
        raise ValueError("actual local independent/trace/interior/slave counts differ")
    if any(type(row) is not int or not 0 <= row < 8940 for group in groups for row in group):
        raise ValueError("native row maps require bounded literal integer storage indices")
    if any(len(set(group)) != len(group) for group in groups):
        raise ValueError("native row maps must cover every original row exactly once")
    if independent != sorted(independent) or trace != sorted(trace):
        raise ValueError("independent and active trace maps must retain increasing native order")
    if (set(trace) & set(interior) or set(trace) | set(interior) != set(independent)
            or set(independent) & set(slaves) or set(independent) | set(slaves) != set(range(8940))):
        raise ValueError("exact trace/interior/independent/slave partition failed")
    return True


def validate_bound_array_signature(actual, expected):
    if (set(actual) != {"shape", "dtype", "sha256"} or set(expected) != set(actual)
            or list(actual["shape"]) != list(expected["shape"])
            or actual["dtype"] != expected["dtype"] or actual["sha256"] != expected["sha256"]):
        raise ValueError("actual saved slave array differs from exact raw MPC signature")
    return True


def validate_raw_transport_ledger(rows):
    if len(rows) != 532 or [row.get("original_mode_index") for row in rows] != list(range(532)):
        raise ValueError("all532 original raw fold/lift rows in exact order are required")
    for row in rows:
        for side in ("C", "D"):
            for direction in ("fold", "lift"):
                error_name, scale_name = f"raw_{side}_{direction}_error_norm", f"raw_{side}_{direction}_operation_scale"
                if error_name not in row or scale_name not in row:
                    raise ValueError("both C/D raw fold and lift witnesses are required for every original mode")
                error, scale = row[error_name], row[scale_name]
                if (not math.isfinite(error) or not math.isfinite(scale) or error < 0 or scale <= 0
                        or error / scale > 1e-10):
                    raise ValueError("per-mode raw fold/lift finite positive-scale gate failed")
    return True


def validate_candidate_inventory(report, authority_report):
    """Pure metadata validation used by narrow negative tests."""
    if (report.get("schema") != SCHEMA or report.get("status") != PASS
            or report.get("degree") != 4 or report.get("factor_count") != 0
            or report.get("audit_only") is not True or report.get("PDE_solved") is not False
            or report.get("official_results") is not False
            or report.get("source_clean_unchanged") is not True
            or report.get("physical_generator_manifest_sha256") != PHYSICAL_MANIFEST
            or report.get("global_mode_keys") != authority_report["mode_keys"]):
        raise ValueError("candidate bounded audit/source/degree/global532 identity failed")
    twists = report.get("twists", [])
    if len(twists) != 2 or [t.get("b") for t in twists] != [0, 1]:
        raise ValueError("both explicit ordered twists are required")
    union = []
    q_inventory = []
    all_keys = authority_report["mode_keys"]
    phase = number(authority_report["layout"]["phase_y"])
    for twist in twists:
        b = twist["b"]
        indices = [i for i, key in enumerate(all_keys) if int(key[2]) % 2 == b]
        if twist.get("sector_original_indices") != indices or len(indices) != (228, 304)[b]:
            raise ValueError("literal original sector indices must partition all532 once")
        union.extend(indices)
        theta, eta, tau = (number(twist[k]) for k in ("theta", "eta", "tau"))
        if (abs(eta - cmath.exp(1j * theta)) > 1e-14
                or abs(tau - eta**2) > 1e-14 or abs(eta**4 - phase) > 1e-13):
            raise ValueError("theta-derived explicit eta/tau/full-wrap identity failed")
        if abs(theta.imag) > 1e-14:
            raise ValueError("this fixed real-ky fixture requires real theta")
        branches = twist.get("branches", [])
        if len(branches) != 2 or [v.get("local_branch") for v in branches] != [0, 1]:
            raise ValueError("both literal local branches are required at each twist")
        for branch in branches:
            q = b + 2 * branch["local_branch"]
            expected_indices = [i for i in indices if ((int(all_keys[i][2]) - b) // 2) % 2
                                == branch["local_branch"]]
            if (branch.get("q") != q or branch.get("shape") != [Q_ROWS[q], Q_ROWS[q]]
                    or branch.get("csr_prefix") != f"q_{q}_S"
                    or branch.get("original_mode_indices") != expected_indices
                    or len(expected_indices) != (76, 152, 152, 152)[q]):
                raise ValueError("q/branch/original alias dimensions differ")
            q_inventory.append(q)
    if sorted(union) != list(range(532)) or sorted(q_inventory) != list(range(4)):
        raise ValueError("complete exact once-only all4q/all532 coverage required")
    theta0, theta1 = number(twists[0]["theta"]), number(twists[1]["theta"])
    if abs((theta1 - theta0) - math.pi / 2) > 1e-14:
        raise ValueError("explicit branch phase cannot be reconstructed from a principal square root")
    pairs = report.get("cross_branch_blocks", [])
    expected = {(p, q) for p in range(4) for q in range(4) if p != q}
    if len(pairs) != 12 or {(v.get("p"), v.get("q")) for v in pairs} != expected:
        raise ValueError("all12 ordered off-diagonal branch pairs are required")
    for block in pairs:
        p, q = block["p"], block["q"]
        scope = "local_twist" if p % 2 == q % 2 else "full_original_action"
        if block.get("shape") != [Q_ROWS[p], Q_ROWS[q]] or block.get("scope") != scope:
            raise ValueError("cross-branch complete dimensions/validation scope differs")
    required = {f"q_{q}_S_{part}" for q in range(4) for part in ("data", "indices", "indptr")}
    required |= {f"q_{q}_map_{field}" for q in range(4)
                 for field in ("column_error_norms", "reference_column_norms")}
    required |= {f"folded_masked_port_{side}_{part}" for side in ("C", "D")
                 for part in ("data", "indices", "indptr")}
    for block in pairs:
        required |= {block["csr_prefix"] + "_" + part for part in ("data", "indices", "indptr")}
    required |= {twist["local_original_H_artifact"] for twist in twists}
    for twist in twists:
        b, mode_count = twist["b"], len(twist["sector_original_indices"])
        action = twist.get("original_action_witness", {})
        recovery = twist.get("complete_interior_port_recovery_witness", {})
        if (action.get("twist") != b or action.get("local_FE_rows") != 7936
                or action.get("all_local_interior_rows") != 4320 or action.get("global_FE_rows") != 15872
                or action.get("q_factors_used") is not False
                or action.get("volume_and_DtN_original_action") is not True
                or not math.isfinite(action.get("relative_original_FE_action_defect", math.nan))
                or not 0 <= action["relative_original_FE_action_defect"] <= 1e-10):
            raise ValueError("actual full-original-action witness is required at both twists")
        if (recovery.get("twist") != b or recovery.get("all_interior_rows") != 4320
                or recovery.get("arbitrary_interior_rhs_nonzero_count") != 4320
                or recovery.get("strict_slave_zero") is not True or recovery.get("global_and_q_factors") != 0
                or recovery.get("inherited_cell_interior_LU_used") is not True
                or not math.isfinite(recovery.get("port_rhs_norm", math.nan)) or recovery["port_rhs_norm"] <= 0
                or any(not math.isfinite(recovery.get(k, math.nan)) or not 0 <= recovery[k] <= 1e-10
                       for k in ("reduced_original_augmented_action_defect", "full_original_storage_recovery_defect"))):
            raise ValueError("complete original arbitrary interior/port recovery witness is required")
        shapes = {f"twist_{b}_original_action_{name}": [size] for name, size in
                  (("local", 7936), ("folded", 7936), ("local_state", 7936), ("global_state", 15872))}
        shapes.update({f"twist_{b}_complete_recovery_{name}": [size] for name, size in
                       (("state", 8940), ("alpha", mode_count), ("FE_rhs", 8940), ("port_rhs", mode_count),
                        ("reduced_rhs", 3616 + mode_count), ("reduced_action", 3616 + mode_count), ("recovered", 8940))})
        shapes.update({f"twist_{b}_{name}": [size] for name, size in
                       (("independent_storage_rows", 7936), ("trace_original_rows", 3616),
                        ("interior_original_rows", 4320), ("slave_storage_rows", 1004))})
        required.update(shapes)
        if any(report.get("artifacts", {}).get(name, {}).get("shape") != shape for name, shape in shapes.items()):
            raise ValueError("complete actual action/recovery/native-row saved-array shape inventory required")
    if not required.issubset(report.get("artifacts", {})):
        raise ValueError("candidate complete q/map/cross-branch/H/folded-port array inventory missing")
    validate_raw_transport_ledger(report.get("raw_fold_per_mode", []))
    return True


def validate_raw_port_receipt(receipt, twist, *, report_source, keys):
    """Bind the actual staged oracle contract, never promote its qualification."""
    b, indices = twist["b"], twist["sector_original_indices"]
    expected_keys = expected_sector_keys(keys, indices)
    if (receipt.get("schema") != "task40extra.y-orbit-quotient-raw-port-audit.v1"
            or receipt.get("status") != "PASS_QUOTIENT_RAW_PORT_AUDIT_ONLY"
            or receipt.get("raw_port_audit_pass") is not True
            or any(receipt.get(k) is not False for k in ("full_component_qualified", "full_case_pass",
                   "PDE_solved", "official_results", "physical_rhs_qualified", "physical_output_qualified"))
            or receipt.get("factor_count") != 0 or receipt.get("seed") != 4053202
            or receipt.get("tolerance") != 1e-10 or receipt.get("degree") != 4
            or receipt.get("local_space_dimension") != 300 or receipt.get("quadrature_degree") != 23
            or receipt.get("primary_facet_points") != 144 or receipt.get("global_mode_count") != 532
            or receipt.get("mode_count") != len(indices) or receipt.get("quotient_twist_index") != b
            or receipt.get("original_mode_indices") != indices
            or receipt.get("original_mode_keys") != expected_keys
            or receipt.get("physical_generator_manifest_sha256") != PHYSICAL_MANIFEST
            or receipt.get("carrier_identity_before") != receipt.get("carrier_identity_after")
            or receipt.get("qualification_source_sha256") != report_source["files_sha256"].get(
                "src/solvers/y_orbit_quotient_raw_qualification.py")):
        raise ValueError("fresh same-live sector raw audit identity/qualification differs")
    context = receipt["raw_discrete_context"]
    identity = receipt["carrier_identity_before"]
    if (digest_json(context) != receipt.get("assembly_context_sha256")
            or identity.get("assembly_context_sha256") != receipt["assembly_context_sha256"]
            or receipt["primary_compiled_gauss"] != context["gauss"]["compiled_forms_verified"]
            or context.get("element_degree") != 4 or context["gauss"]["degree"] != 23
            or receipt["actual_discrete_binding"].get("actual_local_cells") != 40
            or receipt["actual_discrete_binding"].get("actual_local_storage_rows") != 8940
            or receipt["actual_discrete_binding"].get("actual_finalized_slave_rows") != 1004):
        raise ValueError("same-live actual local p4/mesh/MPC/context binding failed")
    contract = context["y_orbit_quotient"]["contract"]
    if (digest_json(contract) != receipt["quotient_contract_sha256"]
            or context["y_orbit_quotient"]["contract_sha256"] != receipt["quotient_contract_sha256"]
            or any(abs(number(contract[k]) - number(twist[k])) > 1e-14 for k in ("theta", "eta", "tau"))):
        raise ValueError("raw receipt detached from the actual explicit twist")
    for proof in receipt["actual_source_binding"].values():
        path = Path(proof["path"])
        relative = "src/" + "/".join(path.parts[-2:])
        if report_source["files_sha256"].get(relative) != proof["sha256"]:
            raise ValueError("raw receipt source detached from worker freeze")
    if (set(receipt["actual_source_binding"]) != set(context["source_sha256"])
            or any(receipt["actual_source_binding"][name]["sha256"] != digest
                   for name, digest in context["source_sha256"].items())):
        raise ValueError("actual raw source proof is incomplete or detached from context")
    primary = receipt["primary_compiled_gauss"]
    oracle = receipt["independent_oracle_compiled_gauss"]
    expected_oracle = {f"{g}/{side}/{component}" for g in ("global_z", "boundary_plane")
                       for side in ("top", "bottom") for component in (0, 1)}
    if set(primary) != {"top/0", "top/1", "bottom/0", "bottom/1"} or set(oracle) != expected_oracle:
        raise ValueError("four primary/eight independent literal kernels required")
    for name, proof in primary.items():
        rules = proof["rules"]
        kernel = proof["loaded_kernel"]
        if (len(rules) != 1 or rules[0]["degree"] != 23
                or rules[0]["points"]["shape"] != [144, 2] or rules[0]["weights"]["shape"] != [144]
                or kernel.get("restoration_exact") is not True
                or kernel.get("numerical_assembly_during_probe") is not False
                or kernel.get("num_constants") != 3
                or [v["role"] for v in kernel["constant_roles"]] != ["alpha", "gamma", "kz"]
                or any(oracle[g + "/" + name]["rules"] != rules for g in ("global_z", "boundary_plane"))):
            raise ValueError("exact same-Gauss/kernel constant restoration failed")
    rows = receipt.get("per_mode", [])
    if (len(rows) != len(indices) or [r.get("local_mode_index") for r in rows] != list(range(len(indices)))
            or [r.get("original_mode_index") for r in rows] != indices
            or [r.get("original_mode_key") for r in rows] != expected_keys):
        raise ValueError("complete literal per-sector per-mode raw ledger required")
    for row in rows:
        if (row.get("status") != "PASS_LOCAL_MODE_RAW_MASK_PORT_AUDIT" or row.get("packet_metadata_errors")
                or row.get("stored_C_entries", 0) <= 0 or row.get("stored_D_entries", 0) <= 0
                or row.get("local_branch_index") != ((int(keys[row["original_mode_index"]][2]) - b) // 2) % 2):
            raise ValueError("raw mode/branch/actual contribution identity failed")
        expected_raw = {"component_x", "component_y", "primary_literal_C", "primary_literal_D",
                        "gauge_C", "gauge_D", "gauge_H", "local_H", "original_H", "area_H_scaling", "stored_H"}
        expected_bounds = {"component_mask", "final_mask", "all_masks", "literal_vs_primary_raw"}
        if (set(row["raw_literal_errors"]) != expected_raw
                or set(row["relative_rank_one_bounds"]) != expected_bounds
                or set(row["actual_recovery_operation_scaled_defects"]) != {"stored", "plane_raw"}
                or len(row["component_mask_measurements"]) != 2
                or set(row["final_mask_measurements"]) != {"C", "D"}):
            raise ValueError("complete raw/mask/rank-one/five-state scalar inventory required")
        values = list(row["raw_literal_errors"].values()) + list(row["relative_rank_one_bounds"].values())
        for group in row["actual_recovery_operation_scaled_defects"].values():
            if len(group) != 5:
                raise ValueError("five-state actual per-mode raw/stored recovery required")
            values.extend(group)
        if any(not math.isfinite(v) or not 0 <= v <= 1e-10 for v in values):
            raise ValueError("raw/literal/mask/rank-one/recovery scalar gate failed")
        if any(row["raw_literal_errors"][k] > 1e-14 for k in ("stored_H", "area_H_scaling")):
            raise ValueError("original H area/normalization gate failed")
        for measurement in [*row["component_mask_measurements"], *row["final_mask_measurements"].values()]:
            if (measurement.get("absolute_sparse_floor") != 1e-30
                    or measurement.get("relative_sparse_cutoff") != 1e-13
                    or measurement.get("introduced_support") != 0
                    or measurement.get("lost_support") != len(measurement.get("lost_rows", []))
                    or measurement.get("raw_nonzero_support") != measurement.get("retained_support", -1)
                       + measurement.get("lost_support", -1)
                    or not math.isfinite(measurement.get("threshold", math.nan))
                    or measurement["threshold"] < 1e-30
                    or not math.isfinite(measurement.get("unchanged_policy_defect", math.nan))
                    or not 0 <= measurement["unchanged_policy_defect"] <= 1e-10):
                raise ValueError("both original component/final mask policies and support losses required")
        for measurement in row["final_mask_measurements"].values():
            if any(not math.isfinite(measurement[k]) or not 0 <= measurement[k] <= 1e-10
                   for k in ("combination_defect", "carrier_binding_defect")):
                raise ValueError("actual final combination/carrier binding failed")
    states = receipt.get("five_state_actual_action_recovery", [])
    if len(states) != 5 or [s.get("state_column") for s in states] != list(range(5)):
        raise ValueError("five actual current carrier action/recovery states required")
    values = list(receipt["raw_vs_stored_five_state_action_defects"].values())
    values += [v for state in states for key, v in state.items() if key != "state_column"]
    if any(not math.isfinite(v) or not 0 <= v <= 1e-10 for v in values):
        raise ValueError("same-live actual raw/stored action/recovery gate failed")
    return True


def check(directory, *, checker_source, checker_environment, allocation_gate):
    import numpy as np
    from scipy import sparse
    from src.solvers.y_orbit_sparse_reference import csr_audit, integer_admission
    from src.solvers.dtn_boundary_phase_gauge import _array_signature
    directory = Path(directory).resolve()
    artifact_root = Path(__file__).resolve().parents[1] / "benchmarks/artifacts/task40extra_dot_parallel_cloud"
    if not directory.is_relative_to(artifact_root.resolve()):
        raise ValueError("audit checker evidence must remain in the own ignored artifact subtree")
    report_path, provenance_path = directory / "audit_report.json", directory / "provenance.json"
    report, provenance = json.loads(report_path.read_text()), json.loads(provenance_path.read_text())
    if (report.get("source") != checker_source or provenance.get("source") != checker_source
            or report.get("environment") != checker_environment or provenance.get("environment") != checker_environment):
        raise ValueError("independent checker requires exact current source and same ABI")
    if file_sha(directory / "abi_manifest.json") != checker_environment["qualification_manifest_sha256"]:
        raise ValueError("current audit ABI file/hash mismatch")
    watched = report["supervisor_receipt"]
    summary_path = bound_path(directory, watched["path"])
    if file_sha(summary_path) != watched["sha256"]:
        raise ValueError("worker supervised receipt hash mismatch")
    validate_supervision(json.loads(summary_path.read_text()), checker_source)
    authority = SavedFullP4Authority(artifact_root / AUTHORITY_RUN, new_source=checker_source,
                                    new_environment=checker_environment, allocation_gate=allocation_gate)
    if report.get("authority") != authority.receipt or provenance.get("saved_full_p4_authority") != authority.receipt:
        raise ValueError("explicit immutable old to new dependency bridge differs")
    validate_candidate_inventory(report, authority.report)
    descriptors, checks = report["artifacts"], []

    def load(name):
        descriptor = descriptors[name]
        path = bound_path(directory, descriptor["path"])
        if file_sha(path) != descriptor["file_sha256"]:
            raise ValueError("candidate saved artifact hash differs: " + name)
        allocation_gate("checker_mmap_" + name, {"matrix_payload_bytes": int(descriptor["payload_bytes"]),
                                                "workspace_bytes": 1 << 20})
        value = np.load(path, allow_pickle=False, mmap_mode="r")
        if (list(value.shape) != descriptor["shape"] or str(value.dtype) != descriptor["dtype"]
                or value.nbytes != descriptor["payload_bytes"] or value.dtype.hasobject
                or descriptor.get("nonfinite_entries") != 0):
            raise ValueError("candidate finite shape/dtype/payload descriptor differs: " + name)
        if value.dtype.kind in "fc":
            flat = value.ravel(order="K")
            for start in range(0, flat.size, 65536):
                if not np.isfinite(flat[start:start + 65536]).all():
                    raise ValueError("nonfinite candidate artifact: " + name)
        return value

    def csr(prefix, shape, *, csc=False):
        values, indices, indptr = (load(prefix + "_" + k) for k in ("data", "indices", "indptr"))
        integer_admission(shape, len(values), index_dtype=indices.dtype, indptr_dtype=indptr.dtype)
        integer_admission(shape, len(values), index_dtype=checker_environment["petsc_int_type"])
        integer_admission(shape, len(values), index_dtype="int32")
        pointer_size, index_bound = (shape[1] + 1, shape[0]) if csc else (shape[0] + 1, shape[1])
        if (values.ndim != 1 or indices.shape != values.shape or indptr.shape != (pointer_size,)
                or values.dtype != np.dtype("complex128") or indptr[0] != 0 or indptr[-1] != len(values)
                or np.any(indptr < 0) or np.any(indptr > len(values)) or np.any(np.diff(indptr) < 0)
                or np.any(indices < 0) or np.any(indices >= index_bound)):
            raise ValueError("raw CSR/CSC buffer dimensions/ranges must pass before any SciPy narrowing")
        if csc:
            matrix = sparse.csc_matrix((values, indices, indptr), shape=shape, copy=False)
            payload = matrix.data.nbytes + matrix.indices.nbytes + matrix.indptr.nbytes
            allocation_gate("checker_CSC_to_CSR_" + prefix, {"matrix_payload_bytes": payload,
                                                           "workspace_bytes": payload})
            matrix = matrix.tocsr()
        else:
            matrix = sparse.csr_matrix((values, indices, indptr), shape=shape, copy=False)
        csr_audit(matrix, petsc_index_dtype=checker_environment["petsc_int_type"])
        return matrix

    def add(name, measured, limit, **facts):
        checks.append({"name": name, "measured": float(measured), "limit": float(limit),
                       "passed": bool(np.isfinite(measured) and 0 <= measured <= limit), **facts})

    def norm(matrix):
        return float(np.linalg.norm(matrix.data))

    def absolute_max(matrix):
        return float(np.max(np.abs(matrix.data))) if matrix.nnz else 0.0

    def compare(left, right, name, limit):
        if left.shape != right.shape:
            raise ValueError("complete compared sparse shapes differ")
        payload = (left.nnz + right.nnz) * 24 + (left.shape[0] + 1) * 8
        allocation_gate("checker_full_entry_difference_" + name,
                        {"matrix_payload_bytes": payload, "workspace_bytes": payload})
        difference = left - right
        nscale, mscale = norm(right), absolute_max(right)
        add(name + "_Frobenius", norm(difference) / max(nscale, np.finfo(float).tiny), limit,
            absolute_difference_norm=norm(difference), reference_norm=nscale, all_entries_checked=True)
        add(name + "_maximum_entry", absolute_max(difference) / max(mscale, np.finfo(float).tiny), limit,
            absolute_maximum_difference=absolute_max(difference), reference_maximum=mscale,
            all_entries_checked=True)

    def bind_metric(name, actual, declared):
        if not math.isfinite(declared) or declared < 0:
            raise ValueError("finite nonnegative saved witness metric required")
        scale = max(abs(actual), abs(declared), np.finfo(float).tiny)
        add(name + "_reported_metric_binding", abs(actual - declared) / scale, 1e-12,
            recomputed=actual, declared=declared)

    for name in descriptors:
        values = load(name)
        del values
    diagonal_norms, diagonal_maxima = {}, {}
    for q in range(4):
        candidate = csr(f"q_{q}_S", (Q_ROWS[q], Q_ROWS[q]))
        old = authority.q_block(q)
        compare(candidate, old, f"q_{q}_complete_CSR", 1e-11)
        diagonal_norms[q], diagonal_maxima[q] = norm(candidate), absolute_max(candidate)
        errors, scales = load(f"q_{q}_map_column_error_norms"), load(f"q_{q}_map_reference_column_norms")
        if errors.shape != (3968,) or scales.shape != errors.shape or np.any(errors < 0) or np.any(scales <= 0):
            raise ValueError("all3968 native FE map columns and their operation scales required at every q")
        add(f"q_{q}_all_FE_map_column_bridge", float(np.max(errors / scales)), 1e-12,
            compared_native_FE_columns=3968, columns_are_complete=True)
        del candidate, old, errors, scales
    for entry in report["cross_branch_blocks"]:
        p, q = entry["p"], entry["q"]
        matrix = csr(entry["csr_prefix"], entry["shape"])
        weak_norm = min(diagonal_norms[p], diagonal_norms[q])
        weak_max = min(diagonal_maxima[p], diagonal_maxima[q])
        add(f"cross_{p}_{q}_Frobenius", norm(matrix) / max(weak_norm, np.finfo(float).tiny), 1e-11,
            absolute_norm=norm(matrix), weaker_diagonal_norm=weak_norm, scope=entry["scope"])
        add(f"cross_{p}_{q}_maximum_entry", absolute_max(matrix) / max(weak_max, np.finfo(float).tiny), 1e-11,
            absolute_maximum=absolute_max(matrix), weaker_diagonal_maximum=weak_max, scope=entry["scope"])
        del matrix
    old_c = sparse.csc_matrix((authority.load("original_port_C_data"), authority.load("original_port_C_indices"),
                               authority.load("original_port_C_indptr")), shape=(17204, 532), copy=False)
    old_d = sparse.csr_matrix((authority.load("original_port_D_data"), authority.load("original_port_D_indices"),
                               authority.load("original_port_D_indptr")), shape=(532, 17204), copy=False)
    candidate_c_csr = csr("folded_masked_port_C", (17204, 532), csc=True)
    c_payload = candidate_c_csr.data.nbytes + candidate_c_csr.indices.nbytes + candidate_c_csr.indptr.nbytes
    allocation_gate("checker_folded_C_CSR_to_CSC", {"matrix_payload_bytes": c_payload,
                                                  "workspace_bytes": c_payload})
    candidate_c = candidate_c_csr.tocsc()
    del candidate_c_csr
    candidate_d = csr("folded_masked_port_D", (532, 17204))
    original_h = authority.load("port_original_H")
    # Per-mode scales prevent a strong mode from concealing a weak-mode error.
    for index in range(532):
        entries = int(candidate_c.indptr[index + 1] - candidate_c.indptr[index])
        entries += int(old_c.indptr[index + 1] - old_c.indptr[index])
        entries += int(candidate_d.indptr[index + 1] - candidate_d.indptr[index])
        entries += int(old_d.indptr[index + 1] - old_d.indptr[index])
        allocation_gate("checker_mode_functional_packet_" + str(index),
                        {"matrix_payload_bytes": entries * 24 + 4 * 17205 * 8,
                         "workspace_bytes": 1 << 20})
        C, C0 = candidate_c[:, index].tocsr(), old_c[:, index].tocsr()
        D, D0 = candidate_d[index:index + 1], old_d[index:index + 1]
        compare(C, C0, f"mode_{index}_masked_C", 1e-10)
        compare(D, D0, f"mode_{index}_masked_D", 1e-10)
        H = float(original_h[index])
        reference = norm(C0) * norm(D0) / H
        bound = (norm(C - C0) * norm(D) + norm(C0) * norm(D - D0)) / H
        add(f"mode_{index}_masked_rank_one", bound / max(reference, np.finfo(float).tiny), 1e-10)
    for twist in report["twists"]:
        b, indices = twist["b"], twist["sector_original_indices"]
        local_H = load(twist["local_original_H_artifact"])
        old_H = original_h[indices]
        if local_H.shape != (len(indices),) or np.any(local_H <= 0):
            raise ValueError("actual local original positive H array required")
        add(f"twist_{b}_original_H_area_scaling", float(np.max(np.abs(2 * local_H - old_H) / old_H)), 1e-14)
        descriptor = twist["raw_port_receipt"]
        path = bound_path(directory, descriptor["path"])
        if file_sha(path) != descriptor["sha256"]:
            raise ValueError("same-live raw audit receipt file binding differs")
        receipt = json.loads(path.read_text())
        validate_raw_port_receipt(receipt, twist, report_source=checker_source, keys=report["global_mode_keys"])
        allocation_gate(f"checker_twist_{b}_complete_witness_packet",
                        {"matrix_payload_bytes": 3 << 20, "workspace_bytes": 4 << 20})
        row_arrays = {name: load(f"twist_{b}_{name}") for name in
                      ("independent_storage_rows", "trace_original_rows", "interior_original_rows", "slave_storage_rows")}
        if any(values.ndim != 1 or values.dtype.kind not in "iu" for values in row_arrays.values()):
            raise ValueError("actual saved native row maps must be one-dimensional integer arrays")
        independent = row_arrays["independent_storage_rows"]
        trace = row_arrays["trace_original_rows"]
        interior = row_arrays["interior_original_rows"]
        slaves = row_arrays["slave_storage_rows"]
        validate_local_row_partition(*(row_arrays[name].tolist() for name in
                                      ("independent_storage_rows", "trace_original_rows", "interior_original_rows", "slave_storage_rows")))
        validate_bound_array_signature(_array_signature(slaves), receipt["raw_discrete_context"]["MPC"]["slaves"])
        action_arrays = {name: load(f"twist_{b}_original_action_{name}")
                         for name in ("local", "folded", "local_state", "global_state")}
        recovery_arrays = {name: load(f"twist_{b}_complete_recovery_{name}") for name in
                           ("state", "alpha", "FE_rhs", "port_rhs", "reduced_rhs", "reduced_action", "recovered")}
        if any(values.dtype != np.dtype("complex128") for values in
               (*action_arrays.values(), *recovery_arrays.values())):
            raise ValueError("actual action/recovery witnesses require the qualified complex128 buffers")
        folded_norm = float(np.linalg.norm(action_arrays["folded"]))
        if folded_norm <= 0:
            raise ValueError("original full-action witness cannot have a vacuous zero reference")
        action_defect = float(np.linalg.norm(action_arrays["local"] - action_arrays["folded"]) / folded_norm)
        add(f"twist_{b}_actual_original_FE_action", action_defect, 1e-10, complete_local_FE_rows=7936)
        bind_metric(f"twist_{b}_actual_original_FE_action", action_defect,
                    twist["original_action_witness"]["relative_original_FE_action_defect"])
        independent_positions = np.searchsorted(independent, interior)
        if (np.any(independent[independent_positions] != interior)
                or np.count_nonzero(action_arrays["local_state"][independent_positions]) != 4320
                or np.linalg.norm(action_arrays["global_state"]) <= 0):
            raise ValueError("actual original-action input must excite every local interior and a nonzero full state")
        state, recovered, FE_rhs = (recovery_arrays[name] for name in ("state", "recovered", "FE_rhs"))
        if any(np.any(values[slaves] != 0) for values in (state, recovered, FE_rhs)):
            raise ValueError("original state, recovered storage and MPC-dual FE RHS require strict slave zeros")
        interior_nonzeros = int(np.count_nonzero(FE_rhs[interior]))
        if interior_nonzeros != 4320:
            raise ValueError("every one of the4320 original interior rows needs a nonzero manufactured RHS")
        port_norm = float(np.linalg.norm(recovery_arrays["port_rhs"]))
        reduced_norm = float(np.linalg.norm(recovery_arrays["reduced_rhs"]))
        state_norm = float(np.linalg.norm(state))
        if min(port_norm, reduced_norm, state_norm) <= 0:
            raise ValueError("complete recovery witness requires nonzero port/reduced RHS and original state")
        reduced_defect = float(np.linalg.norm(recovery_arrays["reduced_action"] - recovery_arrays["reduced_rhs"]) / reduced_norm)
        recovery_defect = float(np.linalg.norm(recovered - state) / state_norm)
        recovery_fact = twist["complete_interior_port_recovery_witness"]
        add(f"twist_{b}_complete_reduced_original_action", reduced_defect, 1e-10,
            complete_trace_rows=3616, complete_port_rows=len(indices), inherited_cell_interior_LU_used=True)
        add(f"twist_{b}_complete_original_storage_recovery", recovery_defect, 1e-10,
            complete_storage_rows=8940, complete_interior_rhs_nonzeros=interior_nonzeros, strict_slave_zero=True)
        bind_metric(f"twist_{b}_complete_reduced_original_action", reduced_defect,
                    recovery_fact["reduced_original_augmented_action_defect"])
        bind_metric(f"twist_{b}_complete_original_storage_recovery", recovery_defect,
                    recovery_fact["full_original_storage_recovery_defect"])
        bind_metric(f"twist_{b}_complete_recovery_port_rhs_norm", port_norm, recovery_fact["port_rhs_norm"])
        if recovery_fact["arbitrary_interior_rhs_nonzero_count"] != interior_nonzeros:
            raise ValueError("saved manufactured interior RHS support count differs")
        ledger = receipt["completed_per_mode_ledger"]
        ledger_path = bound_path(directory, ledger["path"])
        if file_sha(ledger_path) != ledger["sha256"] or ledger["mode_count"] != len(indices):
            raise ValueError("raw per-mode append-only mask ledger hash/count differs")
        add(f"twist_{b}_same_live_raw_port_receipt", 0, 0, compared_original_modes=len(indices),
            qualification="raw-port audit only; physical RHS/output gates deferred")
    raw = report["raw_fold_per_mode"]
    validate_raw_transport_ledger(raw)
    for row in raw:
        for name in ("C", "D"):
            for direction in ("fold", "lift"):
                error, scale = row[f"raw_{name}_{direction}_error_norm"], row[f"raw_{name}_{direction}_operation_scale"]
                add(f"mode_{row['original_mode_index']}_raw_{name}_{direction}", error / scale, 1e-10)
    structural = report["structural_audit"]
    required_true = ("complete_trace_interior_closure", "all_independent_rows_once", "slave_storage_zero",
                     "actual_cell_material_tags_equal", "actual_cell_metric_equal", "full_original_axes_retained",
                     "original_mode_objects_retained", "full_original_cutoffs_unchanged",
                     "local_maps_built_independently", "old_full_maps_validation_only")
    if any(structural.get(k) is not True for k in required_true):
        raise ValueError("required full inventory/material/metric/map/setup structural audit failed")
    if any(structural.get(k) is not False for k in
           ("candidate_full_Ny_CSR_created", "candidate_full_F_created", "candidate_full_Q_created")):
        raise ValueError("candidate setup must not materialize full Ny operators or maps")
    return {"schema": "task40extra.y-orbit-two-cell-independent-checker.v1", "gate_pass": all(v["passed"] for v in checks),
            "evidence_valid": True, "checks": checks, "report_sha256": file_sha(report_path),
            "provenance_sha256": file_sha(provenance_path), "artifact_manifest_sha256": digest_json(descriptors),
            "source": checker_source, "checker_source": checker_source, "environment": checker_environment,
            "command": sys.argv,
            "authority": authority.receipt, "degree": 4, "factor_count": 0, "all_four_q": True,
            "all_532_original_keys": True, "both_branches_each_twist": True,
            "PDE_solved": False, "official_results": False, "physical_rhs_qualified": False,
            "physical_output_qualified": False, "qualification": "Q0-Q2 operator audit only"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--run-directory", type=Path, required=True)
    args = parser.parse_args(argv)
    from benchmarks.run_real_p4_probe import source_facts, environment_facts
    from benchmarks.task038_full3d_jit_staging import process_tree_snapshot, append_jsonl
    from benchmarks.subreaper_watchdog import memory_envelope, runtime_tree_cap
    from src.solvers.real_p4_probe import write_json
    directory = args.run_directory.resolve()
    parent = int(os.environ.get("PHYSICAL_WATCHDOG_PARENT_PID", "0"))
    cap = int(os.environ.get("PHYSICAL_WATCHDOG_LAUNCH_CAP_BYTES", "0"))
    if not args.worker or parent != os.getppid() or parent <= 0 or not 0 < cap <= TREE_CAP_BYTES:
        raise RuntimeError("checker must be the audit CLI's supervised child")
    source = environment = None

    def global_swap():
        values = {}
        for line in Path("/proc/vmstat").read_text().splitlines():
            key, value = line.split()
            if key in ("pswpin", "pswpout"):
                values[key] = int(value)
        if set(values) != {"pswpin", "pswpout"}:
            raise RuntimeError("checker requires readable global swap counters")
        return values

    swap_baseline = None

    def allocation_gate(name, facts):
        sample = process_tree_snapshot(parent, name, None, pss_sampling_policy="disabled_by_profile")
        if (sample.get("all_status_readable") is not True or sample.get("identity_complete") is not True
                or sample.get("swap_bytes") != 0 or global_swap() != swap_baseline):
            raise RuntimeError("checker requires readable whole-tree identity and zero swap")
        payload, workspace = int(facts.get("matrix_payload_bytes", 0)), int(facts.get("workspace_bytes", 0))
        if min(payload, workspace) < 0:
            raise ValueError("negative checker allocation estimate")
        projected = int(sample["rss_bytes"]) + payload + workspace + RESERVE_BYTES
        envelope = memory_envelope()
        effective_cap = runtime_tree_cap(cap, int(sample["rss_bytes"]), envelope,
                                         explicit_tree_cap_bytes=TREE_CAP_BYTES)
        append_jsonl(directory / "checker_events.jsonl", {"event": "allocation_admission", "boundary": name,
                     "current_tree_rss_bytes": sample["rss_bytes"], "requested_payload_bytes": payload,
                     "workspace_bytes": workspace, "evidence_reserve_bytes": RESERVE_BYTES,
                     "projected_tree_bytes": projected, "launch_cap_bytes": cap,
                     "effective_cap_bytes": effective_cap, "fresh_memory_envelope": envelope,
                     "admitted": projected < effective_cap,
                     "global_swap_counters": swap_baseline})
        write_json(directory / "checker_phase.json", {"phase": name, "factor_count": 0})
        if projected >= effective_cap:
            raise MemoryError("checker fresh measured whole-tree headroom is insufficient")
    try:
        source, environment = source_facts(args.expected_head), environment_facts()
        swap_baseline = global_swap()
        result = check(directory, checker_source=source, checker_environment=environment,
                       allocation_gate=allocation_gate)
        if source_facts(args.expected_head) != source:
            raise RuntimeError("source changed during independent checker")
    except Exception as exc:
        result = {"gate_pass": False, "evidence_valid": False, "error_type": type(exc).__name__,
                  "reason": str(exc), "source": source, "environment": environment,
                  "degree": 4, "factor_count": 0, "qualification": "failed Q0-Q2 audit only"}
        (directory / "checker_traceback.txt").write_text(traceback.format_exc())
    write_json(directory / "independent_checker.json", result)
    return 0 if result["gate_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
