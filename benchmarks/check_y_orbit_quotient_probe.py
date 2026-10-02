"""Independent saved-evidence checker for staged quotient prefactor/solve runs.

Restoration authority is validated by the sole snapshot reader. This checker
never assembles ports, volume tensors, a global FE square matrix, or a factor.
It recomputes CSR comparisons, factor tests, original residual packets, MPC
recovery, and every original mode's output and operation scale from saved data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from numbers import Integral
import os
from pathlib import Path
import re
import sys
import time
import traceback

SCHEMA = "task40extra.y-orbit-two-cell-quotient-probe.v1"
CHECKER_SCHEMA = "task40extra.y-orbit-two-cell-quotient-checker.v1"
PASSES = {"prefactor": "QUOTIENT_PREFACTOR_COMPARE_PASS",
          "solve": "QUOTIENT_FULL3D_INVERSE_PROBE_PASS"}
SOURCES = ("generic", "interior_only", "physical", "notch_supported")
Q_ROWS = (1884, 1960, 1960, 1960)
TREE_CAP_BYTES = 3 * 1024**3 // 2
RESERVE_BYTES = 128 * 1024**2
FACTOR_ALLOWANCE_BYTES = 512 * 1024**2
INPUT_SHA = "6654ec211efbc6112f3ccba13ad67ff3a97cdbc471bdd48e39f891819f51a41e"
PHYSICAL_MANIFEST = "4ace13f47bc6edf8a08e1a1df24309f6326294b6bf9d5ca4ada07208bd50c951"
AUDIT_RUN = "y_orbit_two_cell_p4_phi5_audit_attempt1"

SOLVE_WORKER_HEAD = "5e0364cd2eebfffb63a5f3ee8bda8e21083b2495"
CHECKER_SORT_ALLOWED_PATHS = frozenset({"benchmarks/check_y_orbit_quotient_probe.py",
    "src/test/test_y_orbit_quotient_checker_sort_metadata.py"})
HISTORICAL_FULL_Q_HEAD = "ad356715da86ab34fa6b10838cccc8629b3f6e8b"
HISTORICAL_FULL_Q_FILES = {
    "data": "b00c007208e34fb6a933b514f5470445ce6f1c05241f7737b1b4518fe7faee31",
    "indices": "aaffda99f55cbe067dde40e45feee79342bf0f1a7020a72d25f29dd76b407712",
    "indptr": "767e1b2e7addc19dcdf6a8d737af5bcc3010803ab8e1dd4b15f5f8c6bcb9cedb",
}



def file_sha(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            result.update(block)
    return result.hexdigest()


def digest_json(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def finite_gate(value, limit, name):
    if (isinstance(value, bool) or not isinstance(value, (float, int))
            or not math.isfinite(value) or not 0 <= value <= limit):
        raise ValueError("finite nonnegative measured gate failed: " + name)
    return True


def per_mode_operation_error(errors, scales):
    """Every one of532 uses its own scale, including exact zero operations."""
    if len(errors) != 532 or len(scales) != 532:
        raise ValueError("complete all532 per-mode error/scale inventory required")
    worst = 0.0
    for error, scale in zip(errors, scales, strict=True):
        error, scale = float(error), float(scale)
        if not math.isfinite(error) or not math.isfinite(scale) or min(error, scale) < 0:
            raise ValueError("finite nonnegative per-mode errors/scales required")
        if scale == 0:
            if error != 0:
                raise ValueError("nonzero mode error cannot use a zero operation scale")
            continue
        worst = max(worst, error / scale)
    return worst


def validate_scope(report, stage):
    if (stage not in PASSES or report.get("schema") != SCHEMA or report.get("stage") != stage
            or report.get("status") != PASSES[stage] or report.get("degree") != 4
            or report.get("physical_mode_count") != 532 or report.get("official_results") is not False
            or report.get("source_clean_unchanged") is not True
            or report.get("prefactor_only") is not (stage == "prefactor")
            or report.get("PDE_solved") is not (stage == "solve")
            or report.get("factor_count") != (0 if stage == "prefactor" else 4)
            or report.get("input_sha256") != INPUT_SHA
            or report.get("physical_generator_manifest_sha256") != PHYSICAL_MANIFEST):
        raise ValueError("complete stage/degree/all532/source/input/scope identity required")
    flags = report.get("scope_flags", {})
    if flags.get("full_layout_entity_stream") is not True or any(flags.get(key) is not False for key in
            ("candidate_full_Ny_CSR_created", "candidate_full_F_created", "candidate_full_Q_created",
             "candidate_global_FE_square_matrix_created", "raw_port_reassembled",
             "raw_literal_qualification_rerun", "performance_or_target_capacity_claim")):
        raise ValueError("entity-stream/restoration/no-full-map/no-new-raw bounded scope failed")
    if stage == "prefactor":
        if any(report.get(key) for key in ("regular_sources", "notched_sources", "sampled_right_PC_defect")):
            raise ValueError("prefactor cannot carry solved-source qualification")
        if report.get("factor", {}).get("input_blocks") or report.get("factor", {}).get("tests"):
            raise ValueError("prefactor cannot dispatch q factor or tests")
    else:
        if any(set(report.get(key, {})) != set(SOURCES) for key in
               ("regular_sources", "notched_sources", "sampled_right_PC_defect")):
            raise ValueError("all four regular/notched/PC source records are required")
        if report.get("PC_defect_is_norm_bound") is not False:
            raise ValueError("sampled right-PC defect is not an operator norm bound")
        for name in SOURCES:
            finite_gate(report["sampled_right_PC_defect"][name], float("inf"), "sampled_PC_" + name)
        if report.get("changed_cells") is None or len(report["changed_cells"]) != 2 or len(set(report["changed_cells"])) != 2:
            raise ValueError("exact two-cell genuine nonseparable notch is required")
        coupling = report.get("sampled_notch_off_q_delta_relative")
        if not isinstance(coupling, (float, int)) or not math.isfinite(coupling) or coupling < 1e-8:
            raise ValueError("actual notch off-q coupling gate failed")
    return True


def bind_checker_source(worker_source, checker_source):
    """Only this pinned worker's reviewed checker and its new test may differ."""
    if (worker_source.get("dirty") or checker_source.get("dirty")
            or worker_source.get("branch") != checker_source.get("branch")
            or not re.fullmatch(r"[0-9a-f]{40}", worker_source.get("head", ""))
            or not re.fullmatch(r"[0-9a-f]{40}", checker_source.get("head", ""))
            or not worker_source.get("files_sha256") or not checker_source.get("files_sha256")):
        raise ValueError("clean worker/checker source identities and complete inventories required")
    old, new = worker_source["files_sha256"], checker_source["files_sha256"]
    if any(not re.fullmatch(r"[0-9a-f]{64}", value) for value in list(old.values()) + list(new.values())):
        raise ValueError("every worker/checker dependency requires a literal SHA256")
    changed = sorted(path for path in set(old) | set(new) if old.get(path) != new.get(path))
    if worker_source["head"] == checker_source["head"]:
        if worker_source != checker_source:
            raise ValueError("same-head checker must keep exact complete worker source identity")
    elif (worker_source["head"] != SOLVE_WORKER_HEAD or not set(changed).issubset(CHECKER_SORT_ALLOWED_PATHS)
            or "benchmarks/check_y_orbit_quotient_probe.py" not in changed
            or "benchmarks/check_y_orbit_quotient_probe.py" not in old
            or not CHECKER_SORT_ALLOWED_PATHS.issubset(new)):
        raise ValueError("cross-head recheck permits only the pinned solve worker's checker/test correction")
    return {"worker_head": worker_source["head"], "checker_head": checker_source["head"],
            "same_head_exact_source_identity": worker_source == checker_source,
            "allowed_checker_test_paths": sorted(CHECKER_SORT_ALLOWED_PATHS),
            "changed_paths": changed, "all_other_numerical_config_input_dependencies_equal": True,
            "worker_dependency_manifest_sha256": digest_json(old), "checker_dependency_manifest_sha256": digest_json(new),
            "changed_dependencies": [{"path": path, "worker_sha256": old.get(path), "checker_sha256": new.get(path)}
                                     for path in changed]}


def admit_checker_output(worker_source, checker_source, *, worker_directory, output_directory,
                         explicit_checker_directory, prior_checker_output, direct_profile=None):
    """Reject unsafe output paths before the failure logger can write anything."""
    if direct_profile is None:
        binding = bind_checker_source(worker_source, checker_source)
    elif direct_profile in ("X", "XZ", "Y"):
        from benchmarks.check_y_orbit_direct_probe import bind_direct_checker_source
        binding = bind_direct_checker_source(worker_source, checker_source, direct_profile=direct_profile)
    else:
        raise ValueError("only explicit reviewed direct X/XZ/Y saved-worker checker profiles are admitted")
    same_directory = Path(worker_directory).resolve() == Path(output_directory).resolve()
    if (type(explicit_checker_directory) is not bool or type(prior_checker_output) is not bool
            or prior_checker_output or (explicit_checker_directory and same_directory)
            or (worker_source != checker_source and (not explicit_checker_directory or same_directory))):
        raise ValueError("saved-worker recheck requires a fresh separate checker directory; prior evidence remains immutable")
    return binding


def csr_row_sort_permutation(indices, indptr, shape, *, historical_only):
    """Exact per-row entry permutation, never aggregation or coefficient edits.

    Pure sequence policy also powers tiny stdlib negative tests. The numerical
    caller must pre-admit its lists and copy/sort workspace before this call.
    """
    if type(historical_only) is not bool:
        raise ValueError("historical-only row sorting requires a literal explicit scope")
    if (len(shape) != 2 or any(not isinstance(value, Integral) or isinstance(value, bool) or value < 0 for value in shape)
            or len(indptr) != shape[0] + 1
            or any(not isinstance(value, Integral) or isinstance(value, bool) for value in indptr)
            or indptr[0] != 0 or indptr[-1] != len(indices)
            or any(value < 0 or value > len(indices) for value in indptr)
            or any(a > b for a, b in zip(indptr[:-1], indptr[1:]))
            or any(not isinstance(value, Integral) or isinstance(value, bool) or not 0 <= value < shape[1]
                   for value in indices)):
        raise ValueError("malformed CSR rows/columns/pointers cannot be normalized")
    permutation, unsorted_rows, maximum_row_entries = [], 0, 0
    for row in range(shape[0]):
        start, stop = int(indptr[row]), int(indptr[row + 1])
        ordered = sorted(range(start, stop), key=indices.__getitem__)
        if any(indices[a] == indices[b] for a, b in zip(ordered[:-1], ordered[1:])):
            raise ValueError("duplicate CSR columns are forbidden; no duplicate summation")
        unsorted = any(indices[a] > indices[b] for a, b in zip(range(start, stop - 1), range(start + 1, stop)))
        if unsorted and not historical_only:
            raise ValueError("candidate CSR must remain strictly sorted canonical storage")
        unsorted_rows += int(unsorted)
        maximum_row_entries = max(maximum_row_entries, stop - start)
        permutation.extend(ordered)
    return permutation, {"unsorted_rows": unsorted_rows, "maximum_row_entries": maximum_row_entries,
                         "duplicate_entries": 0, "per_row_entry_counts_preserved": True}


def validate_pinned_full_q_asset(*, prefix, old, csc, head, shape, descriptors):
    if (prefix != "full_Q" or old is not True or csc is not False or head != HISTORICAL_FULL_Q_HEAD
            or list(shape) != [15872, 15872] or set(descriptors) != set(HISTORICAL_FULL_Q_FILES)):
        raise ValueError("only the exact immutable ad356715 historical full_Q asset may be reordered")
    for part, expected in HISTORICAL_FULL_Q_FILES.items():
        descriptor = descriptors[part]
        expected_shape = [15873] if part == "indptr" else [107840]
        expected_dtype = "complex128" if part == "data" else "int32"
        expected_payload = {"data": 1725440, "indices": 431360, "indptr": 63492}[part]
        if (descriptor.get("file_sha256") != expected or descriptor.get("shape") != expected_shape
                or descriptor.get("dtype") != expected_dtype or descriptor.get("payload_bytes") != expected_payload):
            raise ValueError("historical full_Q raw descriptor identity differs")
    return True


def sort_pinned_historical_full_q(matrix, *, descriptors, allocation_gate, save_evidence, index_dtype):
    """Private, pre-admitted exact permutation of the one historical asset."""
    import numpy as np
    from scipy import sparse
    from src.solvers.y_orbit_sparse_reference import sparse_hash, csr_audit
    payload = int(matrix.data.nbytes + matrix.indices.nbytes + matrix.indptr.nbytes)
    nnz, rows = int(matrix.nnz), int(matrix.shape[0])
    if (matrix.shape != (15872, 15872) or nnz != 107840 or payload != 2220292
            or matrix.data.dtype != np.dtype("complex128")
            or matrix.indices.dtype != np.dtype("int32") or matrix.indptr.dtype != np.dtype("int32")
            or any(value.flags.writeable for value in (matrix.data, matrix.indices, matrix.indptr))):
        raise ValueError("pinned historical full_Q requires the original readonly complex128/int32 buffers")
    # Includes private CSR plus comparison copies, exact permutation, bounded
    # Python row-sort objects, action probes/results and serialization workspace.
    allocation_gate("checker_historical_full_Q_private_copy_sort", {
        "matrix_payload_bytes": 3 * payload + 2 * nnz * 8 + 12 * rows * 16,
        "workspace_bytes": 128 * nnz + (4 << 20), "historical_validation_asset_only": True,
        "raw_buffers_preserved": True, "duplicate_summation_permitted": False})
    raw_before = sparse_hash(matrix)
    positions, facts = csr_row_sort_permutation(matrix.indices, matrix.indptr, matrix.shape, historical_only=True)
    if facts["unsorted_rows"] != 15872:
        raise ValueError("pinned historical full_Q raw storage order differs")
    permutation = np.asarray(positions, dtype=np.int64); del positions
    data, indices, indptr = matrix.data[permutation], matrix.indices[permutation], matrix.indptr.copy()
    normalized = sparse.csr_matrix((data, indices, indptr), shape=matrix.shape, copy=False)
    csr_audit(normalized, petsc_index_dtype=index_dtype)
    exact_columns = bool(np.array_equal(normalized.indices, matrix.indices[permutation]))
    exact_values = bool(np.array_equal(normalized.data.view(np.uint8), matrix.data[permutation].view(np.uint8)))
    exact_pointers = bool(np.array_equal(normalized.indptr, matrix.indptr))
    if not (exact_columns and exact_values and exact_pointers) or normalized.nnz != matrix.nnz:
        raise ValueError("historical CSR row sorting changed a column, coefficient byte or entry count")
    probes = []
    j = np.arange(matrix.shape[1], dtype=np.float64)
    for label, vector in (("a", np.cos(.173 * j) + 1j * np.sin(.291 * j)),
                          ("b", np.sin(.237 * j) + 1j * np.cos(.419 * j))):
        original, sorted_action = matrix @ vector, normalized @ vector
        relative = float(np.linalg.norm(original - sorted_action) / max(np.linalg.norm(original), np.finfo(float).tiny))
        finite_gate(relative, 1e-12, "historical_full_Q_action_equivalence_" + label)
        artifacts = {key: save_evidence("historical_full_Q_" + label + "_" + key, values)
                     for key, values in (("probe", vector), ("raw_action", original), ("sorted_action", sorted_action))}
        probes.append({"label": label, "relative_action_difference": relative, "limit": 1e-12,
                       "passed": bool(relative <= 1e-12), "artifacts": artifacts})
    raw_after = sparse_hash(matrix)
    if raw_after != raw_before or any(value.flags.writeable for value in (matrix.data, matrix.indices, matrix.indptr)):
        raise ValueError("historical raw CSR buffers were modified by sorting")
    receipt = {"schema": "task40extra.historical-full-Q-private-sort.v1", "asset": "full_Q",
        "authority_head": HISTORICAL_FULL_Q_HEAD, "raw_descriptors": descriptors,
        "shape": list(matrix.shape), "stored_entries": nnz, "raw_payload_bytes": payload,
        "raw_CSR_sha256_before": raw_before, "raw_CSR_sha256_after": raw_after,
        "sorted_CSR_sha256": sparse_hash(normalized), "raw_buffers_preserved": True,
        "private_sorted_copy": True, "duplicate_summation_performed": False,
        "exact_per_row_column_permutation": exact_columns, "exact_coefficient_byte_permutation": exact_values,
        "unchanged_row_partition_indptr": exact_pointers, **facts,
        "sorted_to_raw_entry_positions": save_evidence("historical_full_Q_sorted_to_raw_entry_positions", permutation),
        "row_partition": "immutable raw full_Q_indptr; each sorted entry maps to exactly one original entry in that row",
        "action_equivalence": probes, "qualification": "historical validation map storage-order correction only"}
    for value in (normalized.data, normalized.indices, normalized.indptr):
        value.flags.writeable = False
    return normalized, receipt


def validate_metadata_bindings(report, provenance, manifest, *, checker_source, checker_environment, stage):
    validate_scope(report, stage)
    if (report.get("source") != checker_source or provenance.get("source") != checker_source
            or report.get("environment") != checker_environment or provenance.get("environment") != checker_environment
            or checker_source.get("dirty") or not re.fullmatch(r"[0-9a-f]{40}", checker_source.get("head", ""))
            or not checker_source.get("files_sha256") or provenance.get("schema") != SCHEMA
            or provenance.get("stage") != stage or provenance.get("degree") != 4
            or provenance.get("input_sha256") != INPUT_SHA
            or report.get("artifacts") != manifest or not manifest):
        raise ValueError("fresh report/provenance/manifest/source/ABI identity differs")
    resource = provenance.get("resource_contract", {})
    expected = {"stage": stage, "wall_seconds": 600, "swap_bytes": 0, "mpi": 1,
                "math_threads": 1, "evidence_reserve_bytes": RESERVE_BYTES,
                "factor_workspace_allowance_bytes": 0 if stage == "prefactor" else FACTOR_ALLOWANCE_BYTES,
                "factor_fill_and_temporary_workspace_unknown": True,
                "factor_L_U_statistics_copies_permitted": False,
                "performance_or_target_capacity_claim": False}
    if (any(resource.get(key) != value for key, value in expected.items())
            or type(resource.get("tree_cap_bytes")) is not int
            or not 0 < resource["tree_cap_bytes"] <= TREE_CAP_BYTES):
        raise ValueError("bounded whole-tree/time/swap/factor resource contract differs")
    if checker_environment.get("petsc_scalar_type") != "complex128":
        raise ValueError("qualified complex128 ABI is required")
    return True


def validate_recovery_identity_bindings(bindings, historical_condensations):
    if (len(bindings) != 2 or [item.get("twist") for item in bindings] != [0, 1]
            or len(historical_condensations) != 2):
        raise ValueError("both ordered complete pre-factor volume/recovery identity bridges required")
    rows = {"independent_storage_rows", "trace_original_rows", "interior_original_rows", "slave_storage_rows"}
    for binding, historical in zip(bindings, historical_condensations, strict=True):
        old_tensors = historical["action_only_complete_tensor_identities"]
        tensors = binding.get("raw_oriented_tensor_inventory", {})
        if (set(binding.get("native_row_inventory_equal", {})) != rows
                or any(value is not True for value in binding["native_row_inventory_equal"].values())
                or binding.get("raw_oriented_tensor_exact_equal") is not True
                or binding.get("tensor_count") != 20 or len(tensors) != 20 or tensors != old_tensors
                or binding.get("cache_recipe_equal") is not True
                or binding.get("new_volume_identity_claimed_equal_to_old_JIT") is not False):
            raise ValueError("all native rows and complete20 raw/oriented tensors must match before factors")
        for tensor in tensors.values():
            if (tensor.get("shape") != [300, 300] or tensor.get("dtype") != "complex128"
                    or any(not re.fullmatch(r"[0-9a-f]{64}", tensor.get(key, ""))
                           for key in ("raw_sha256", "oriented_sha256"))):
                raise ValueError("complete raw/oriented300x300 tensor hash identity required")
        old, new = binding.get("historical_cache_recipe", {}), binding.get("new_cache_recipe", {})
        if old != historical["operator_cache_identity"] or set(new) != set(old):
            raise ValueError("historical cache recipe must bind immutable Q0-Q2 metadata")
        if any(new[key] != old[key] for key in old if key != "policy_signatures"):
            raise ValueError("volume/recovery cache key dependencies or scope changed")
        previous, current = old.get("policy_signatures", {}), new.get("policy_signatures", {})
        signatures = binding.get("compiler_signatures", {})
        if not previous or set(previous) != set(current) or set(signatures) != set(previous):
            raise ValueError("both old/new primary compiler signature inventories required")
        for name, policy in current.items():
            before = previous[name]
            if set(policy) != set(before) or any(policy[key] != before[key] for key in policy if key != "ufcx_form_signature"):
                raise ValueError("volume/recovery cache policy changed beyond separately bound compiler signature")
            pair = signatures[name]
            if (set(pair) != {"historical", "new"} or pair["historical"] != before.get("ufcx_form_signature")
                    or pair["new"] != policy.get("ufcx_form_signature")
                    or any(not isinstance(value, str) or not 0 < len(value) <= 1024 for value in pair.values())):
                raise ValueError("new primary volume signature and historical raw-JIT signature must remain distinct receipts")
    return True


def validate_factor_event_contract(events, stage):
    """Bind all4 comparisons before factors, fresh RSS and remaining allowance."""
    compared, admitted, retained, recovery, created, hashes = set(), [], [], [], [], {}
    for event in events:
        name = event.get("event")
        if name == "complete_recovery_identity_before_factor":
            twist = event.get("twist")
            if type(twist) is not int or twist != len(recovery) or admitted:
                raise ValueError("both local recovery identity bridges must precede factors")
            recovery.append(twist)
        if name == "rebuilt_q_block_compared_before_any_factor":
            q = event.get("q")
            if type(q) is not int or q not in range(4) or q in compared or admitted:
                raise ValueError("all four once-only q comparisons must precede every factor")
            finite_gate(event.get("relative_frobenius_difference"), 1e-11, "event_q_norm")
            finite_gate(event.get("relative_max_difference"), 1e-11, "event_q_max")
            if not re.fullmatch(r"[0-9a-f]{64}", event.get("CSR_sha256", "")):
                raise ValueError("pre-factor q comparison event requires its input CSR hash")
            compared.add(q); hashes[q] = event["CSR_sha256"]
        if name == "allocation_admission" and event.get("boundary", "").startswith("quotient_factor_q_"):
            if stage != "solve" or compared != set(range(4)) or recovery != [0, 1]:
                raise ValueError("q factor admission is forbidden until all four comparisons pass")
            q, facts = len(admitted), event.get("facts", {})
            expected_allowance = (4 - q) * 128 * 1024**2
            if (q not in range(4) or event["boundary"] != f"quotient_factor_q_{q}"
                    or facts.get("retained_factor_count") != q or len(retained) != q
                    or facts.get("factor_workspace_allowance_bytes") != expected_allowance
                    or facts.get("LU_fill_and_workspace_unknown") is not True
                    or event.get("remaining_factor_allowance_bytes") != expected_allowance
                    or event.get("admitted") is not True):
                raise ValueError("actual retained-factor count/unknown-fill/remaining allowance failed")
            current, payload, workspace, reserve = (event.get(key) for key in
                ("current_tree_rss_bytes", "additional_payload_bytes", "declared_workspace_bytes", "evidence_reserve_bytes"))
            if (any(type(value) is not int or value < 0 for value in (current, payload, workspace, reserve))
                    or current <= 0 or reserve < RESERVE_BYTES
                    or event.get("projected_tree_bytes") != current + payload + workspace + expected_allowance + reserve
                    or not event["projected_tree_bytes"] < event.get("effective_tree_cap_bytes", 0) <= TREE_CAP_BYTES):
                raise ValueError("factor admission must use current measured RSS plus every additional byte")
            admitted.append(q)
        if name == "all_branch_factor_created":
            q = event.get("q")
            if (stage != "solve" or type(q) is not int or q != len(created)
                    or admitted != list(range(q + 1)) or event.get("factor_count") != q + 1
                    or event.get("retained_factor_count") != q + 1
                    or event.get("input_CSR_sha256") != hashes.get(q)):
                raise ValueError("created factor must immediately bind its admitted freshly compared CSR")
            created.append(q)
        if name == "all_branch_factor_retained":
            q = event.get("q")
            if (stage != "solve" or q != len(retained) or admitted != list(range(q + 1))
                    or event.get("retained_factor_count") != q + 1 or created != list(range(q + 1))):
                raise ValueError("all four factor-retention receipts must follow their own admissions")
            retained.append(q)
        if stage == "prefactor" and name in ("all_branch_factor_test", "original_augmented_manufactured_control"):
            raise ValueError("prefactor contains factor or solve dispatch")
    if recovery != [0, 1] or compared != set(range(4)) or (stage == "solve" and (admitted != list(range(4)) or created != list(range(4)) or retained != list(range(4)))):
        raise ValueError("complete four-comparison/all-factor event inventory is required")
    return True


def validate_historical_file_metadata(verification, *, context_sha, expected_gauss=None):
    keys = {"top/0", "top/1", "bottom/0", "bottom/1"}
    if (verification.get("schema") != "task40extra.historical-primary-surface-file-verification.v1"
            or verification.get("status") != "VERIFIED_HISTORICAL_FILES_ONLY"
            or verification.get("verified_primary_gauss_records") != 4
            or verification.get("verified_file_references") != 8
            or verification.get("assembly_context_sha256") != context_sha
            or verification.get("read_chunk_upper_bytes") != 1 << 20
            or verification.get("historical_kernel_provenance_retained") is not True
            or any(verification.get(key) is not False for key in
                   ("modules_loaded", "new_JIT_performed", "new_volume_kernel_qualified"))
            or set(verification.get("records", {})) != keys):
        raise ValueError("complete historical-file-only kernel provenance receipt required")
    if expected_gauss is not None and set(expected_gauss) != keys:
        raise ValueError("immutable primary Gauss context must contain all four records")
    for name, record in verification["records"].items():
        if set(record) != {"binary", "generated_C"}:
            raise ValueError("both binary and generated C provenance files required")
        for role, path_key, hash_key in (("binary", "module_path", "binary_sha256"),
                                       ("generated_C", "module_bound_C_path", "module_bound_C_sha256")):
            proof = record[role]
            if (not isinstance(proof.get("recorded_path"), str) or not Path(proof["recorded_path"]).is_absolute()
                    or proof.get("resolved_path") != str(Path(proof["recorded_path"]).resolve())
                    or not re.fullmatch(r"[0-9a-f]{64}", proof.get("expected_sha256", ""))
                    or proof.get("verified_sha256") != proof["expected_sha256"]
                    or type(proof.get("verified_bytes")) is not int or proof["verified_bytes"] <= 0):
                raise ValueError("complete historical file path/hash/bytes proof required")
            if expected_gauss is not None:
                kernel = expected_gauss[name]["loaded_kernel"]
                if (kernel.get("schema") != "task40extra.loaded-surface-kernel.v1"
                        or proof["recorded_path"] != kernel[path_key] or proof["expected_sha256"] != kernel[hash_key]):
                    raise ValueError("historical file proof detached from exact immutable loaded-kernel context")
    return True


def validate_restoration_metadata(restoration, *, authority_receipt, source, environment,
                                  sector_identities, global_keys):
    if len(global_keys) != 532 or len({tuple(key) for key in global_keys}) != 532:
        raise ValueError("all532 exact ordered original physical keys required")
    if len(restoration) != 3 or [v.get("quotient_twist_index") for v in restoration] != [None, 0, 1]:
        raise ValueError("exact ordered global/both-local restoration receipts required")
    for receipt, twist, count, cells, rows, slaves in zip(restoration, (None, 0, 1), (532, 228, 304),
            (80, 40, 40), (17204, 8940, 8940), (1332, 1004, 1004), strict=True):
        identity = receipt.get("restored_public_carrier_identity", {})
        binding = receipt.get("actual_discrete_binding", {})
        if (receipt.get("schema") != "task40extra.qualified-quotient-snapshot-restoration.v1"
                or receipt.get("status") != "RESTORED_EXACT_SNAPSHOT_NEW_VOLUME_UNQUALIFIED"
                or receipt.get("authority") != authority_receipt
                or receipt.get("new_volume_source") != source or receipt.get("new_volume_environment") != environment
                or receipt.get("stored_D_second_conjugation") is not False
                or receipt.get("packet_mmaps_released") is not True
                or receipt.get("factor_count") != 0 or receipt.get("PDE_solved") is not False
                or receipt.get("expected_snapshot_identity") != identity or identity.get("mode_count") != count
                or identity.get("physical_generator_manifest_sha256") != PHYSICAL_MANIFEST
                or binding.get("actual_cells") != cells or binding.get("actual_storage_rows") != rows
                or binding.get("actual_finalized_slave_rows") != slaves
                or binding.get("ABI_equal") is not True or binding.get("config_equal") is not True
                or not binding.get("actual_source_sha256") or not receipt.get("new_volume_audit")
                or not re.fullmatch(r"[0-9a-f]{64}", binding.get("cell_dofmap_sha256", ""))):
            raise ValueError("restoration/public-constructor/new-volume/source/discrete binding failed")
        validate_historical_file_metadata(receipt.get("historical_primary_surface_file_verification", {}),
                                          context_sha=identity["assembly_context_sha256"])
        for name, digest in binding["actual_source_sha256"].items():
            if digest not in [value for path, value in source["files_sha256"].items() if Path(path).name == name]:
                raise ValueError("restored actual-source binding detached from new frozen inventory")
        for key in ("assembly_mode_manifest_sha256", "assembly_context_sha256", "carrier_numeric_sha256"):
            if not re.fullmatch(r"[0-9a-f]{64}", identity.get(key, "")):
                raise ValueError("complete restoration context/manifest/numeric digest required")
        if receipt.get("historical_raw_JIT_context_sha256") != identity["assembly_context_sha256"]:
            raise ValueError("historical surface context detached from restored coefficients")
        if twist is None:
            if (identity["assembly_context_sha256"] != "40bef5d252789a12236b19feeb5f417e053c76cbab4cab3a2252138f45b894f5"
                    or identity["carrier_numeric_sha256"] != "199d3bb28c624672d5d263877fa00c53909a1976fd69ae3e63a77bec11910cfd"
                    or identity.get("ordered_mode_keys") != [[index, *key] for index, key in enumerate(global_keys)]
                    or receipt.get("local_raw_receipt_sha256") is not None):
                raise ValueError("current35 global context and exact old numeric controls differ")
        elif identity != sector_identities[str(twist)]:
            raise ValueError("restored local manifest/numeric identity differs from raw qualification")
    return True


def expected_array_shapes(report, stage):
    """Complete non-vacuous inventory; shape declarations never grant a pass."""
    blocks = report.get("reformed_blocks", [])
    if len(blocks) != 4 or [block.get("q") for block in blocks] != list(range(4)):
        raise ValueError("all four ordered reformed q blocks are required")
    expected = {}
    for q, block in enumerate(blocks):
        nnz = block.get("nnz")
        if (block.get("shape") != [Q_ROWS[q], Q_ROWS[q]] or block.get("csr_prefix") != f"q_{q}_S"
                or type(nnz) is not int or not 0 < nnz <= 500000
                or not re.fullmatch(r"[0-9a-f]{64}", block.get("CSR_sha256", ""))):
            raise ValueError("literal q CSR index/shape/hash inventory differs")
        for metric in ("relative_frobenius_difference", "relative_max_difference"):
            finite_gate(block.get(metric), 1e-11, f"q_{q}_" + metric)
        expected[f"q_{q}_S_data"] = [nnz]
        expected[f"q_{q}_S_indices"] = [nnz]
        expected[f"q_{q}_S_indptr"] = [Q_ROWS[q] + 1]
    expected.update({"independent_storage_rows": [15872], "actual_interior_positions": [8640],
        "full_mpc_slaves": [1332], "full_mpc_offsets": [17205],
        "port_original_H": [532], "port_q_labels": [532], "port_factor_coordinate_scale": [532],
        "original_mode_e_vectors": [532, 3], "original_mode_k_vectors": [532, 3],
        "original_mode_outward_signs": [532], "original_mode_magnetic_denominator": [],
        "original_mode_boundary_area": [], "original_mode_incident_projections": [532],
        "original_carrier_global_rows": [], "original_carrier_ownership_range": [2],
        "original_carrier_slave_rows": [1332], "original_port_C_indptr": [533],
        "original_port_D_indptr": [533]})
    for b, modes in enumerate((228, 304)):
        expected.update({f"twist_{b}_{name}": [size] for name, size in
            (("independent_storage_rows", 7936), ("trace_original_rows", 3616),
             ("interior_original_rows", 4320), ("slave_storage_rows", 1004), ("original_H", modes))})
    if stage == "solve":
        factor = report.get("factor", {})
        factor_blocks, tests = factor.get("input_blocks", []), factor.get("tests", [])
        if (len(factor_blocks) != 4 or [v.get("q") for v in factor_blocks] != list(range(4))
                or len(tests) != 4 or [v.get("q") for v in tests] != list(range(4))
                or factor.get("all_reformed_blocks_compared_before_factor") is not True
                or factor.get("all_four_retained_simultaneously") is not True):
            raise ValueError("all four fresh compared factor inputs and measured tests are required")
        for q, test in enumerate(tests):
            finite_gate(test.get("true_block_residual"), 1e-10, f"factor_{q}_true_residual")
            finite_gate(test.get("repeated_difference"), 1e-11, f"factor_{q}_repeat")
            finite_gate(test.get("linearity_difference"), 1e-11, f"factor_{q}_linearity")
        for q, block in enumerate(factor_blocks):
            if block.get("shape") != blocks[q]["shape"] or block.get("CSR_sha256") != blocks[q]["CSR_sha256"]:
                raise ValueError("factor input detached from its fresh compared CSR")
            for name in ("rhs_a", "rhs_b", "solution_a", "solution_b", "solution_a_repeat", "solution_sum"):
                expected[f"q_{q}_{name}"] = [Q_ROWS[q]]
        for q in range(4):
            label = f"aug_q_{q}"
            expected.update({label + "_" + key: [15872] for key in
                             ("FE_rhs", "effective_rhs", "solution")})
            expected.update({label + "_" + key: [532] for key in
                             ("port_rhs", "port_operation_scale", "auxiliary_ports", "projection",
                              "normalization_h", "augmented_port_residual")})
            expected.update({label + "_" + key: [17204] for key in
                             ("rhs_storage", "solution_storage", "original_action", "volume_action",
                              "coupling_action", "native_residual", "augmented_FE_residual")})
        for name in SOURCES:
            expected[name + "_rhs"] = [15872]
            for prefix in ("regular", "notch"):
                label = prefix + "_" + name
                expected[label + "_solution"] = [15872]
                expected.update({label + "_" + key: [17204] for key in
                    ("rhs_storage", "solution_storage", "original_action", "volume_action", "coupling_action",
                     "native_residual", "augmented_FE_residual", "recovered_field")})
                expected.update({label + "_" + key: [532] for key in
                    ("auxiliary_ports", "projection", "normalization_h", "augmented_port_residual",
                     "plane_total_auxiliary", "plane_incident_projections", "plane_outgoing_auxiliary",
                     "direct_plane_outgoing_power_diagnostic", "global_total_auxiliary", "global_incident_projections",
                     "mode_local_amplitude_scale", "plane_electric_scale", "plane_magnetic_scale", "mode_power_operation_scale")})
                expected[label + "_plane_electric"] = [532, 3]
                expected[label + "_plane_magnetic"] = [532, 3]
    return expected


def validate_array_inventory(report, stage):
    expected = expected_array_shapes(report, stage)
    artifacts = report.get("artifacts", {})
    required_unsized = {"full_mpc_masters", "full_mpc_coefficients", "original_port_C_data",
                        "original_port_C_indices", "original_port_D_data", "original_port_D_indices"}
    if not set(expected).union(required_unsized).issubset(artifacts):
        raise ValueError("complete expected source/output/factor/native inventory is missing")
    for name, shape in expected.items():
        if artifacts[name].get("shape") != shape:
            raise ValueError("complete array shape differs: " + name)
    for name, descriptor in artifacts.items():
        if (not re.fullmatch(r"[A-Za-z0-9_]+", name)
                or descriptor.get("nonfinite_entries") != 0 or descriptor.get("raw_failure_diagnostic_only") is not False
                or not re.fullmatch(r"[0-9a-f]{64}", descriptor.get("file_sha256", ""))):
            raise ValueError("nonfinite or unbound diagnostic cannot qualify a pass: " + name)
    forbidden = {f"{prefix}_{part}" for prefix in ("full_Q", "full_F", "reference_S")
                 for part in ("data", "indices", "indptr")}
    if set(artifacts) & forbidden:
        raise ValueError("candidate fullNy map/matrix artifacts are forbidden")
    return True


def validate_shared_storage_metadata(evidence, descriptors, *, direct_profile=None):
    """Nonvacuous complete same80 record, class, owner and lazy inventory."""
    directions = ("primal_to_canonical", "primal_from_canonical", "dual_to_canonical",
        "dual_from_canonical", "functional_to_canonical", "functional_from_canonical")
    if direct_profile is None:
        shared_schema="task40extra.same80-shared-transform-equivalence.v1"
        independent_counts=(15872,7936,7936);record_totals=(608,304,304);base_count=152;row_width=3968
        storage_counts=(17204,8940,8940);dimension_record_counts=({1:272,2:256,3:80},{1:136,2:128,3:40},{1:136,2:128,3:40})
    else:
        from benchmarks.check_y_orbit_direct_probe import reviewed_direct_profile_metadata
        metadata=reviewed_direct_profile_metadata(direct_profile)
        shared_schema="task40extra.direct-shared-transform-equivalence.v1"
        independent_counts=(metadata.independent_rows,)+(metadata.local_independent_rows,)*metadata.replication_count
        dimension_record_counts=tuple({1:metadata.nx*ny*(3*metadata.nz+2),2:metadata.nx*ny*(3*metadata.nz+1),
            3:metadata.nx*ny*metadata.nz} for ny in (metadata.ny,)+(metadata.local_y_cells,)*metadata.replication_count)
        record_totals=tuple(sum(counts.values()) for counts in dimension_record_counts)
        base_count=record_totals[0]//metadata.ny;row_width=metadata.rows_per_q
        storage_counts=(metadata.storage_rows,)+(metadata.local_storage_rows,)*metadata.replication_count
        if evidence.get("direct_profile")!=metadata.name:raise ValueError("actual direct profile missing from shared inventory")
    if (evidence.get("schema") != shared_schema
            or evidence.get("shared_transforms") is not True or evidence.get("same80_p4_only") is not (direct_profile is None)
            or evidence.get("complete_before_any_factor") is not True
            or evidence.get("local_layout_borrows_existing_entities") is not True
            or evidence.get("payload_is_RSS") is not False or evidence.get("target_savings_measured") is not False
            or evidence.get("mapping_limit") != 1e-12):
        raise ValueError("complete same80 storage-only equivalence required")
    role_names = ["full", "twist_0", "twist_1"] if direct_profile is None else [
        "full", *(f"twist_{b}" for b in range(metadata.replication_count))]
    role_ny = (4,2,2) if direct_profile is None else (metadata.ny,)+(metadata.local_y_cells,)*metadata.replication_count
    roles = evidence.get("roles", [])
    if [item.get("role") for item in roles] != role_names:
        raise ValueError("complete ordered full/all-reviewed-local roles required")
    for role, n, ny, total, expected_counts, storage_count in zip(roles,independent_counts,role_ny,record_totals,
            dimension_record_counts,storage_counts,strict=True):
        records=role.get("records",[])
        if (role.get("independent_rows")!=n or role.get("width")!=row_width or role.get("ny")!=ny
                or role.get("record_count")!=total or len(records)!=total or role.get("base_count")!=base_count
                or role.get("full_rows")!=storage_count
                or any(role.get(key) is not True for key in ("complete_native_independent_partition_equal",
                    "complete_orbit_base_slot_partition_equal","every_actual_record_matrix_inverse_compared",
                    "all_six_complete_operator_columns_compared","shared_bank_instance_equal"))
                or role.get("mutable_transform_borrow_detected") is not False or role.get("key_collision_detected") is not False
                or not role.get("references") or not role.get("record_rows_artifact")):
            raise ValueError("complete actual same80 record coverage required")
        counts={dimension:sum(item.get("dimension")==dimension for item in records) for dimension in (1,2,3)}
        if counts!=expected_counts or sum(item.get("size",0) for item in records)!=n:
            raise ValueError("complete edge/face/interior channel inventory differs")
        if {item.get("borrower_record_index") for item in records}!=set(range(1,total+1)):
            raise ValueError("exact insertion-order borrower inventory required")
        for item in records:
            if (type(item.get("orbit")) is not int or item["orbit"] not in range(ny)
                    or type(item.get("dimension")) is not int or item["dimension"] not in (1,2,3)
                    or item.get("size")!={1:4,2:24,3:108}[item["dimension"]]
                    or item.get("rows_count")!=item["size"] or item.get("template_id") not in role["references"]
                    or any(not isinstance(item.get(member+"_owner_id"),str) for member in ("rows","matrix","inverse"))):
                raise ValueError("complete per-record template/owner identity differs")
            for metric in ("matrix_difference","inverse_difference","inverse_composition","nonhermitian_pairing"):
                finite_gate(item.get(metric),1e-12,"shared_record_"+metric)
        if [item.get("direction") for item in role.get("directions",[])]!=list(directions):
            raise ValueError("all six ordered complete operators required")
        for item in role["directions"]:
            if (item.get("complete_columns")!=108 or item.get("panel_columns_max")!=32
                    or item.get("default_action_sha256")!=item.get("shared_action_sha256")
                    or any(not re.fullmatch(r"[0-9a-f]{64}",item.get(key,"")) for key in
                        ("input_sha256","default_action_sha256","shared_action_sha256"))):
                raise ValueError("complete six-direction exhaustive action evidence differs")
            finite_gate(item.get("relative_difference"),1e-12,"shared_direction")
    stages=evidence.get("owner_stages",[])
    names=[item.get("stage") for item in stages]
    required=["before_collect"]
    for role in role_names:
        required.extend([role+"_after_collect",role+("_unshared_overlap" if direct_profile is None else "_streamed_controls_begin"),role+"_after_first_inverse_request",
                         role+"_after_first_inverse_direction",role+"_after_all_six_directions"])
        if role!="full":required.append(role+"_layout_after_build")
    required.extend(["all_sectors_retained_before_factor","cleanup"])
    if len(names)!=len(set(names)) or any(name not in names for name in required):
        raise ValueError("complete collect/layout/lazy/retention/cleanup owner lifecycle required")
    if [names.index(name) for name in required]!=sorted(names.index(name) for name in required):
        raise ValueError("owner lifecycle chronology differs")
    if stages[0].get("matrix_template_count")!=0 or stages[0].get("lazy_inverse_count")!=0:
        raise ValueError("bank must start empty")
    sealed_seen=False;previous_inverse=0;previous_templates=0
    union_owner_artifacts={key:value for receipt in stages for key,value in receipt.get("owner_artifacts",{}).items()}
    if evidence.get("owner_artifacts")!=union_owner_artifacts:raise ValueError("complete global owner artifact inventory required")
    if stages[names.index("full_after_collect")].get("lazy_inverse_count")!=0 or stages[names.index("full_after_first_inverse_request")].get("lazy_inverse_count")!=1:
        raise ValueError("actual empty and first-class lazy inverse stages required")
    for stage in stages:
        owners,views=stage.get("owners",[]),stage.get("views",[])
        ids=[item.get("owner_id") for item in owners];view_names=[item.get("name") for item in views]
        if (len(ids)!=len(set(ids)) or len(view_names)!=len(set(view_names))
                or stage.get("allocation_boundary")!="shared_owner_receipt_"+stage["stage"]
                or stage.get("owner_count")!=len(owners) or stage.get("scope")!="named numerical backing allocations; not RSS"
                or stage.get("sum_view_nbytes_with_aliases")!=sum(item.get("view_nbytes",-1) for item in views)
                or stage.get("unique_backing_owner_nbytes")!=sum(item.get("allocation_nbytes",-1) for item in owners)):
            raise ValueError("exact distinct-owner versus alias accounting failed")
        templates=stage.get("templates",[])
        if (stage.get("matrix_template_count")!=len(templates)
                or stage.get("actual_state_count")!=sum(len(item.get("keys",[])) for item in templates)
                or stage.get("lazy_inverse_count")!=sum(item.get("inverse_sha256") is not None for item in templates)):
            raise ValueError("actual class/template/lazy inventory differs")
        if stage["stage"]=="cleanup":
            if (stage.get("closed") is not True or owners or views or templates
                    or stage.get("cleanup_live_declared_owner_anchors")!=0
                    or stage.get("cleanup_all_declared_borrowers_released") is not True):
                raise ValueError("cleanup requires actual declared borrower release, not empty labels")
            continue
        if stage["stage"]!="before_collect" and (not owners or not views or not templates):
            raise ValueError("nonempty actual owner/class inventory required")
        if stage.get("lazy_inverse_count",-1)<previous_inverse or stage.get("matrix_template_count",-1)<previous_templates:
            raise ValueError("run-local lazy templates cannot disappear before cleanup")
        if sealed_seen and not stage.get("sealed"):raise ValueError("sealed bank cannot reopen")
        sealed_seen=sealed_seen or stage.get("sealed") is True
        previous_inverse=stage["lazy_inverse_count"];previous_templates=stage["matrix_template_count"]
        named_views={item["name"]:item for item in views}
        actual_inverse_count=0
        for template in templates:
            prefix="bank.template."+template["template_id"].split("-")[1]
            matrix_view=named_views.get(prefix+".matrix")
            inverse_view=named_views.get(prefix+".inverse")
            if matrix_view is None or matrix_view.get("sha256")!=template.get("matrix_sha256"):
                raise ValueError("every stage matrix template needs its exact saved owner view")
            if template.get("inverse_sha256") is None:
                if inverse_view is not None:raise ValueError("lazy-empty template cannot have inverse storage")
            elif inverse_view is None or inverse_view.get("sha256")!=template["inverse_sha256"]:
                raise ValueError("every stage lazy inverse needs its exact saved owner view")
            else:actual_inverse_count+=1
        if actual_inverse_count!=stage["lazy_inverse_count"]:raise ValueError("actual saved lazy inverse count differs")
        owner_by_id={item["owner_id"]:item for item in owners}
        for owner in owners:
            borrowers=sorted(item["name"] for item in views if item.get("owner_id")==owner["owner_id"])
            artifact=stage.get("owner_artifacts",{}).get(owner["owner_id"],{})
            descriptor=descriptors.get(artifact.get("artifact"),{})
            if (not borrowers or sorted(owner.get("borrowers",[]))!=borrowers
                    or artifact.get("sha256")!=owner.get("sha256")
                    or artifact.get("allocation_nbytes")!=owner.get("allocation_nbytes")
                    or descriptor.get("dtype")!="uint8" or descriptor.get("shape")!=[owner["allocation_nbytes"]]
                    or descriptor.get("payload_bytes")!=owner["allocation_nbytes"]):
                raise ValueError("complete owner buffer artifacts and borrower edges required")
        for view in views:
            owner=owner_by_id.get(view.get("owner_id"))
            if owner is None or not view.get("base_chain") or len(view.get("shape",[]))!=len(view.get("strides",[])):
                raise ValueError("complete view to ultimate owner chain required")
            low,high=view.get("backing_span",[-1,-1])
            if not 0<=low<=high<=owner["allocation_nbytes"]:raise ValueError("view exceeds actual owner allocation")
            if (view["name"].startswith("bank.template.") or
                    view["name"].startswith(tuple(role+".record." for role in role_names)) and
                    view["name"].endswith((".matrix",".inverse"))):
                if view.get("writeable") is not False or owner.get("owner_type")!="builtins.bytes":
                    raise ValueError("shared borrowed transform must have immutable byte backing")
    retained=stages[names.index("all_sectors_retained_before_factor")]
    if (retained.get("sealed") is not True or retained.get("lazy_inverse_count")!=retained.get("matrix_template_count")
            or not retained.get("basis_fingerprints")):
        raise ValueError("all actual classes/inverses retained in the sealed pre-factor bank")
    final_templates={item["template_id"]:item for item in retained["templates"]}
    final_basis={item["basis_id"]:item["descriptor"] for item in retained["basis_fingerprints"]}
    def identity(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
    for receipt in stages:
        for template in receipt.get("templates",[]):
            final=final_templates.get(template["template_id"])
            if (final is None or template["matrix_sha256"]!=final["matrix_sha256"]
                    or template["inverse_sha256"] is not None and template["inverse_sha256"]!=final["inverse_sha256"]
                    or not {identity(key) for key in template["keys"]}.issubset({identity(key) for key in final["keys"]})):
                raise ValueError("earlier actual class/template state detached from complete retained proof")
        for descriptor in receipt.get("basis_fingerprints",[]):
            if final_basis.get(descriptor["basis_id"])!=descriptor["descriptor"]:
                raise ValueError("earlier actual basis descriptor changed")
    return True


def validate_shared_record_key(key,witness,*,dimension,size,basis_descriptor,actual_cell_info,expected_state):
    positions=basis_descriptor["actual_entity_positions"]
    if (set(key)!={"basis","dimension","shape","channels","state","semantics","dtype"}
            or type(dimension) is not int or dimension not in (1,2,3) or key.get("dimension")!=dimension
            or type(key.get("dimension")) is not int or key.get("shape")!=[size,size]
            or any(type(value) is not int for value in key["shape"])
            or key.get("dtype")!=basis_descriptor["matrix_dtype"]
            or witness.get("dimension")!=dimension or type(witness.get("dimension")) is not int
            or type(witness.get("cell_info")) is not int or witness["cell_info"]!=actual_cell_info):
        raise ValueError("complete actual record coefficient identity differs")
    if dimension in (1,2):
        local=witness.get("local_entity")
        if type(local) is not int or local not in range(len(positions[dimension])):raise ValueError("actual local subentity missing")
        expected_positions=positions[dimension][local];expected_channels=list(range(size))
        semantics=(["canonical_edge","lexicographic_xyz","basix_coefficient_v1"] if dimension==1 else
                   ["canonical_face","axis_aligned_reference_q1","basix_coefficient_v1"])
    else:
        if witness.get("local_entity") is not None:raise ValueError("cell interior subentity relabeled")
        expected_positions=positions[3][0];expected_channels=expected_positions
        semantics=["actual_element.Tt_apply","cell_dim_block_size","inverse_interior_block"]
    if (not isinstance(key.get("channels"),list) or any(type(value) is not int for value in key["channels"])
            or key["channels"]!=expected_channels or witness.get("positions")!=expected_positions
            or any(type(value) is not int for value in witness["positions"]) or key.get("semantics")!=semantics):
        raise ValueError("ordered actual channels or inherited coefficient semantics differ")
    state=key.get("state")
    if not isinstance(state,list) or state!=expected_state:raise ValueError("actual orientation state relabeled")
    if dimension==1:
        valid=len(state)==2 and state[0]=="edge_reversal" and type(state[1]) is bool
    elif dimension==2:
        valid=(len(state)==3 and state[0]=="face_D4" and isinstance(state[1],list) and len(state[1])==4
               and all(type(value) is int for value in state[1]) and sorted(state[1])==[0,1,2,3]
               and type(state[2]) is int and state[2] in range(8))
    else:
        valid=len(state)==2 and state[0]=="cell_info" and type(state[1]) is int and 0<=state[1]<2**30
    if not valid:raise ValueError("strict actual finite orientation class required")
    return True


def check_shared_storage_evidence(evidence, *, load, descriptors, allocation_gate, native_inventories, snapshot_contexts, direct_profile=None):
    """Independently rebuild logical views and all six complete record actions."""
    import numpy as np
    from src.solvers.hcurl_canonical_vector_dolfinx import _entity_canonical_order
    from src.constraints.high_order_floquet_trace import quadrilateral_face_info
    validate_shared_storage_metadata(evidence,descriptors,direct_profile=direct_profile)
    if direct_profile is not None:
        from benchmarks.check_y_orbit_direct_probe import reviewed_direct_profile_metadata
        metadata=reviewed_direct_profile_metadata(direct_profile)
    checks=[];owner_hashes={};view_hashes={};known_owner_facts={};raw_buffers={}
    unique_artifacts={item['artifact'] for stage in evidence['owner_stages'] for item in stage['owner_artifacts'].values()}
    allocation_gate('checker_shared_owner_payloads',{'matrix_payload_bytes':sum(descriptors[name]['payload_bytes'] for name in unique_artifacts),
                                                  'workspace_bytes':16<<20})
    def raw_load(name):
        if name not in raw_buffers:raw_buffers[name]=load(name)
        return raw_buffers[name]
    def add(name,measured,limit=1e-12):
        measured=float(measured)
        if not math.isfinite(measured) or measured>limit:raise ValueError("shared storage numerical proof failed: "+name)
        checks.append({"name":name,"measured":measured,"limit":float(limit),"passed":True})
    def raw_hash(value):return hashlib.sha256(value.tobytes(order="C")).hexdigest()
    for stage in evidence["owner_stages"]:
        allocations={item["owner_id"]:item for item in stage["owners"]}
        for owner in stage["owners"]:
            token=owner["owner_id"];facts={k:v for k,v in owner.items() if k!="borrowers"}
            if token in known_owner_facts and known_owner_facts[token]!=facts:raise ValueError("same owner ID changed allocation/content")
            known_owner_facts[token]=facts
            ref=stage["owner_artifacts"][token];raw=raw_load(ref["artifact"])
            if raw.dtype!=np.dtype(np.uint8) or raw.ndim!=1 or raw_hash(raw)!=owner["sha256"]:
                raise ValueError("actual saved backing byte hash differs")
            owner_hashes[token]=owner["sha256"]
            for view in (item for item in stage["views"] if item["owner_id"]==token):
                dtype=np.dtype(view["dtype"]);shape=tuple(view["shape"]);strides=tuple(view["strides"])
                if dtype.hasobject or any(type(size) is not int or size<0 for size in shape):raise ValueError("invalid numerical view shape/dtype")
                size=math.prod(shape);offset=view["byte_offset"]
                low=offset+sum(min(0,(count-1)*stride) for count,stride in zip(shape,strides)) if size else offset
                high=offset+sum(max(0,(count-1)*stride) for count,stride in zip(shape,strides))+dtype.itemsize if size else offset
                if [low,high]!=view["backing_span"] or size*dtype.itemsize!=view["view_nbytes"]:
                    raise ValueError("exact saved strided byte span differs")
                array=np.ndarray(shape=shape,dtype=dtype,buffer=raw,offset=offset,strides=strides)
                if array.dtype.kind in "fc" and not np.isfinite(array).all():
                    raise ValueError("nonfinite backing view cannot qualify shared storage")
                value_hash=raw_hash(array)
                if value_hash!=view["sha256"]:raise ValueError("saved alias logical numerical hash differs")
                view_hashes[(stage["stage"],view["name"])]=value_hash
            add(stage["stage"]+"_"+token+"_raw_owner_hash",0.,0.)
    retained=next(item for item in evidence["owner_stages"] if item["stage"]=="all_sectors_retained_before_factor")
    templates={item["template_id"]:item for item in retained["templates"]}
    basis={item["basis_id"]:item["descriptor"] for item in retained["basis_fingerprints"]}
    if len(basis)!=retained["basis_count"] or any(digest_json(desc)!=token for token,desc in basis.items()):
        raise ValueError("actual basis coefficient/ABI fingerprints differ")
    template_keys={digest_json(key) for item in templates.values() for key in item["keys"]};record_keys=set()
    views={item["name"]:item for item in retained["views"]}
    def borrowed(name, selected_stage=None):
        selected_stage=retained if selected_stage is None else selected_stage
        selected_views={item["name"]:item for item in selected_stage["views"]}
        view=selected_views[name];raw=raw_load(selected_stage["owner_artifacts"][view["owner_id"]]["artifact"])
        return np.ndarray(tuple(view["shape"]),dtype=np.dtype(view["dtype"]),buffer=raw,
                          offset=view["byte_offset"],strides=tuple(view["strides"]))
    directions=("primal_to_canonical","primal_from_canonical","dual_to_canonical","dual_from_canonical","functional_to_canonical","functional_from_canonical")
    for role in evidence["roles"]:
        name=role["role"];records=role["records"];n=role["independent_rows"]
        context=snapshot_contexts[name]
        actual_arrays={}
        for member,expected in (("cell_info",context["orientation"]),("geometry_x",context["mesh"]["geometry_x"])):
            reference=role.get("actual_arrays",{}).get(member,{})
            actual=load(reference["artifact"])
            signature={"shape":list(actual.shape),"dtype":str(actual.dtype),"sha256":raw_hash(actual)}
            if signature!=reference.get("signature") or signature!=expected:
                raise ValueError("complete actual orientation/geometry not bound to historical immutable topology")
            actual_arrays[member]=actual
        rows=load(role["record_rows_artifact"])
        native=load(native_inventories[name])
        default_stage=next(item for item in evidence["owner_stages"] if item["stage"]==name+"_after_all_six_directions")
        default_views={item["name"]:item for item in default_stage["views"]}
        default_native=borrowed("default_"+name+".independent",default_stage) if direct_profile is None else native
        if direct_profile is not None and role.get("original_control_scope")!="streamed actual original helpers; one state scratch; no unshared collector":
            raise ValueError("direct reviewed profiles require streamed original helper controls")
        saved_independent=borrowed(name+".independent")
        if not np.array_equal(native,saved_independent) or not np.array_equal(native,default_native) or native.shape!=(n,):raise ValueError("complete actual native inventory differs")
        if rows.dtype!=np.dtype(np.int64) or rows.shape!=(n,) or not np.array_equal(np.sort(rows),np.arange(n)):
            raise ValueError("every native independent channel must occur exactly once")
        canonical=[];operators={};bases={};offset_cursor=0;seen_record_keys=set()
        allocation_gate("checker_shared_complete_record_operators_"+name,{"matrix_payload_bytes":0,"workspace_bytes":8<<20})
        for item in records:
            key=item["actual_key"];record_keys.add(digest_json(key));template=templates[item["template_id"]]
            if key not in template["keys"] or key.get("basis") not in basis or key.get("dimension")!=item["dimension"]:
                raise ValueError("actual record state not represented by exact qualified template key")
            size=item["size"];start=item["orbit"]*role["width"]+item["first"]
            witness=item.get("actual_state_witness",{})
            dimension=item["dimension"];cell=witness.get("cell")
            if (witness.get("dimension")!=dimension or type(cell) is not int
                    or cell not in range(len(actual_arrays["cell_info"]))
                    or witness.get("cell_info")!=int(actual_arrays["cell_info"][cell])
                    or key.get("shape")!=[size,size] or key.get("dtype")!=np.dtype(np.complex128).str):
                raise ValueError("actual basis shape/dtype/cell orientation identity differs")
            coords=np.asarray(witness.get("native_coordinates"),dtype=float)
            if coords.shape!=({1:2,2:4,3:8}[dimension],3) or not np.isfinite(coords).all():
                raise ValueError("complete original native entity coordinates required")
            if any(not np.any(np.all(actual_arrays["geometry_x"]==point,axis=1)) for point in coords):
                raise ValueError("actual entity coordinates absent from immutable full geometry")
            descriptor=basis[key["basis"]]
            positions=descriptor["actual_entity_positions"]
            if dimension in (1,2):
                local_entity=witness.get("local_entity")
                if type(local_entity) is not int or local_entity not in range(len(positions[dimension])):
                    raise ValueError("actual local entity channel inventory required")
                expected_positions=positions[dimension][local_entity]
                _,permutation=_entity_canonical_order(coords,dimension,1e-9)
                permutation=list(map(int,permutation))
                expected_state=(["edge_reversal",permutation!=[0,1]] if dimension==1 else
                                ["face_D4",permutation,int(quadrilateral_face_info(tuple(permutation)))])
                expected_channels=list(range(size))
                expected_semantics=(["canonical_edge","lexicographic_xyz","basix_coefficient_v1"] if dimension==1 else
                                    ["canonical_face","axis_aligned_reference_q1","basix_coefficient_v1"])
            else:
                if witness.get("local_entity") is not None:raise ValueError("cell witness cannot relabel a subentity")
                expected_positions=positions[3][0]
                expected_state=["cell_info",int(actual_arrays["cell_info"][cell])]
                expected_channels=expected_positions
                expected_semantics=["actual_element.Tt_apply","cell_dim_block_size","inverse_interior_block"]
            validate_shared_record_key(key,witness,dimension=dimension,size=size,basis_descriptor=descriptor,
                actual_cell_info=int(actual_arrays["cell_info"][cell]),expected_state=expected_state)
            if item["rows_offset"]!=offset_cursor:raise ValueError("complete sequential record row offsets required")
            offset_cursor+=size
            record_id=(item["orbit"],digest_json(item["base"]))
            if record_id in seen_record_keys:raise ValueError("duplicate actual orbit/base record")
            seen_record_keys.add(record_id)
            canonical.extend(range(start,start+size));base=digest_json(item["base"])
            if base in bases and bases[base]!=(item["first"],size):raise ValueError("translated slot/base dimensions changed")
            bases[base]=(item["first"],size)
            prefix=name+".record."+format(item["borrower_record_index"],"06d")
            matrix=borrowed(prefix+".matrix");inverse=borrowed(prefix+".inverse")
            record_rows=borrowed(prefix+".rows")
            default_prefix="default_"+prefix
            default_rows=borrowed(default_prefix+".rows",default_stage) if direct_profile is None else record_rows
            if (views[prefix+".rows"]["owner_id"]!=item["rows_owner_id"]
                    or not np.array_equal(record_rows,rows[item["rows_offset"]:item["rows_offset"]+size])
                    or not np.array_equal(record_rows,default_rows)):
                raise ValueError("complete actual/default record row owner differs")
            for member,value in (("matrix",matrix),("inverse",inverse)):
                view=views[prefix+"."+member]
                bank_index=item["template_id"].split("-")[1]
                bank_view=views["bank.template."+bank_index+"."+member]
                if (view["owner_id"]!=item[member+"_owner_id"] or view["owner_id"]!=bank_view["owner_id"]
                        or view["byte_offset"]!=bank_view["byte_offset"] or view["strides"]!=bank_view["strides"]
                        or value.shape!=(size,size) or value.dtype!=np.dtype(np.complex128)
                        or raw_hash(value)!=item[member+"_sha256"] or raw_hash(value)!=template[member+"_sha256"]):
                    raise ValueError("complete per-entity immutable template/owner alias differs")
                reference=borrowed(default_prefix+"."+member,default_stage) if direct_profile is None else load(role["references"][item["template_id"]][member+"_artifact"])
                saved_reference=load(role["references"][item["template_id"]][member+"_artifact"])
                if (reference.tobytes(order="C")!=saved_reference.tobytes(order="C")
                        or raw_hash(reference)!=role["references"][item["template_id"]][member+"_sha256"]):
                    raise ValueError("per-template default control detached from complete per-record original owner")
                difference=float(np.linalg.norm(value-reference)/max(np.linalg.norm(reference),np.finfo(float).tiny))
                if value.tobytes(order="C")!=reference.tobytes(order="C"):raise ValueError("complete default record transform changed")
                add(name+"_record_"+str(item["borrower_record_index"])+"_"+member,difference)
            if direct_profile is not None:
                if dimension in (1,2):
                    from src.solvers.hcurl_canonical_vector_dolfinx import _physical_entity_transform
                    original_control,semantics=_physical_entity_transform(coords,dimension,4,1e-9)
                    if list(semantics)!=key["semantics"]:raise ValueError("original physical helper semantics changed")
                else:
                    full_t=load(role["references"][item["template_id"]]["full_Tt_artifact"])
                    if full_t.shape!=(300,300) or full_t.dtype!=np.dtype(float):raise ValueError("complete actual originalTt control required")
                    original_control=np.linalg.inv(full_t[np.ix_(expected_positions,expected_positions)]).astype(complex)
                if original_control.tobytes(order="C")!=matrix.tobytes(order="C"):
                    raise ValueError("every actual state differs from its original helper control")
                add(name+"_original_helper_state_control",0.,0.)
            composition=float(np.linalg.norm(inverse@matrix-np.eye(size))/np.sqrt(size));add(name+"_inverse_composition",composition)
            j=np.arange(size);x=np.cos(.31*j)+1j*np.sin(.47*j);d=np.sin(.29*j)+1j*np.cos(.41*j);f=np.cos(.23*j)+1j*np.sin(.37*j)
            scale=max(np.linalg.norm(d)*np.linalg.norm(x),np.linalg.norm(f)*np.linalg.norm(x),1.)
            pairing=float(max(abs(np.vdot(inverse.conj().T@d,matrix@x)-np.vdot(d,x)),abs(np.dot(inverse.T@f,matrix@x)-np.dot(f,x)))/scale)
            add(name+"_nonhermitian_pairing",pairing)
            operators[item["borrower_record_index"]]=(matrix,inverse)
        if len(bases)!=(152 if direct_profile is None else metadata.nx*(7*metadata.nz+3)) or sorted(canonical)!=list(range(n)):raise ValueError("all canonical/orbit/base/slot channels must occur exactly once")
        interior=sum(item["size"] for item in records if item["dimension"]==3)
        if interior!=((8640 if name=="full" else 4320) if direct_profile is None else (metadata.interior_rows if name=="full" else metadata.local_interior_rows)):raise ValueError("complete original cell interior channels differ")
        allocation_gate("checker_shared_six_direction_complete_panels_"+name,{"matrix_payload_bytes":2*n*32*16,"workspace_bytes":8<<20})
        for direction,recorded in zip(directions,role["directions"],strict=True):
            ih=hashlib.sha256();oh=hashlib.sha256()
            for first in range(0,108,32):
                count=min(32,108-first);source=np.zeros((n,count),complex);result=np.empty_like(source)
                for item in records:
                    size=item["size"];rr=rows[item["rows_offset"]:item["rows_offset"]+size]
                    cr=np.arange(item["orbit"]*role["width"]+item["first"],item["orbit"]*role["width"]+item["first"]+size)
                    source_rows=rr if direction.endswith("to_canonical") else cr
                    if first<size:source[source_rows[first:first+min(count,size-first)],np.arange(min(count,size-first))]=1
                for item in records:
                    rr=rows[item["rows_offset"]:item["rows_offset"]+item["size"]]
                    cr=np.arange(item["orbit"]*role["width"]+item["first"],item["orbit"]*role["width"]+item["first"]+item["size"])
                    matrix,inverse=operators[item["borrower_record_index"]]
                    if direction==directions[0]:result[cr]=inverse@source[rr]
                    elif direction==directions[1]:result[rr]=matrix@source[cr]
                    elif direction==directions[2]:result[cr]=matrix.conj().T@source[rr]
                    elif direction==directions[3]:result[rr]=inverse.conj().T@source[cr]
                    elif direction==directions[4]:result[cr]=matrix.T@source[rr]
                    else:result[rr]=inverse.T@source[cr]
                ih.update(source.tobytes(order="C"));oh.update(result.tobytes(order="C"))
            if ih.hexdigest()!=recorded["input_sha256"] or oh.hexdigest()!=recorded["shared_action_sha256"]:
                raise ValueError("all six complete operator/panel action hashes differ")
            add(name+"_"+direction+"_complete_columns",0.,0.)
    if template_keys!=record_keys:raise ValueError("every actual bank state must have complete default record proof")
    return checks


def check(directory, *, checker_source, checker_environment, stage, allocation_gate, checker_directory=None,
          research_wall_seconds=None, research_memory_gib=None):
    # The small provenance determines schema before any large report decode.
    provenance_path=Path(directory).resolve()/"provenance.json"
    allocation_gate("checker_profile_dispatch_metadata",{"matrix_payload_bytes":0,"workspace_bytes":8*provenance_path.stat().st_size+(1<<20)})
    dispatch_provenance=json.loads(provenance_path.read_text())
    if dispatch_provenance.get("direct_profile") is not None:
        if dispatch_provenance.get("direct_profile") not in ("X","XZ","Y"):raise ValueError("only reviewed direct X/XZ/Y checker profiles are admitted")
        from benchmarks.check_y_orbit_direct_probe import check_direct
        return check_direct(directory,checker_source=checker_source,checker_environment=checker_environment,
                            stage=stage,allocation_gate=allocation_gate,checker_directory=checker_directory,
                            research_wall_seconds=research_wall_seconds, research_memory_gib=research_memory_gib)
    if research_wall_seconds is not None:
        raise ValueError("research wall override requires saved reviewed direct evidence")
    if research_memory_gib is not None:
        raise ValueError("research memory override requires saved reviewed direct solve evidence")
    import numpy as np
    from scipy import sparse
    from benchmarks.y_orbit_two_cell_authority import (SavedFullP4Authority, AUTHORITY_RUN,
        bound_path, validate_supervision)
    from benchmarks.run_y_orbit_quotient_probe import plain_metadata
    from src.solvers.y_orbit_qualified_snapshot import SavedQuotientSnapshotAuthority
    from src.solvers.y_orbit_sparse_reference import csr_audit, integer_admission, sparse_hash
    from src.solvers.y_orbit_centered_evidence import compare_mode_evidence
    from src.solvers.dtn_boundary_phase_gauge import _array_signature
    from src.solvers.fullspace_dtn_action import _canonical_json_bytes, _jsonable
    from src.solvers.task40extra_y_orbit_reference import pilot_config
    from src.common.modes_3d import outgoing_port_modes_3d
    from src.solvers.dtn_boundary_phase_gauge import (solver_amplitudes_from_global,
        incident_projection_in_solver_coordinates, BOUNDARY_PLANE)
    from benchmarks.check_y_orbit_sparse_probe import _require_operation_scale_binding

    directory = Path(directory).resolve()
    artifact_root = Path(__file__).resolve().parents[1] / "benchmarks/artifacts/task40extra_dot_parallel_cloud"
    if not directory.is_relative_to(artifact_root.resolve()):
        raise ValueError("quotient evidence must stay inside the own ignored artifact subtree")
    report_path, provenance_path = directory / "probe_report.json", directory / "provenance.json"
    report, provenance = json.loads(report_path.read_text()), json.loads(provenance_path.read_text())
    worker_source = report["source"]
    source_binding = bind_checker_source(worker_source, checker_source)
    evidence_directory = directory if checker_directory is None else Path(checker_directory).resolve()
    if (not evidence_directory.is_relative_to(artifact_root.resolve())
            or (source_binding["changed_paths"] and evidence_directory == directory)):
        raise ValueError("cross-head recheck requires its own fresh ignored checker-attempt directory")
    manifest = json.loads((directory / "artifact_manifest.json").read_text())
    validate_metadata_bindings(report, provenance, manifest, checker_source=worker_source,
                              checker_environment=checker_environment, stage=stage)
    validate_array_inventory(report, stage)
    event_path = directory / "probe_events.jsonl"
    events = [json.loads(line) for line in event_path.read_text().splitlines() if line.strip()]
    validate_factor_event_contract(events, stage)
    compared_events = sorted(({key: value for key, value in item.items() if key not in ("event", "worker_elapsed_seconds")}
        for item in events if item.get("event") == "rebuilt_q_block_compared_before_any_factor"), key=lambda item: item["q"])
    if compared_events != report["reformed_blocks"]:
        raise ValueError("fresh q block report detached from the actual pre-factor comparison events")
    for key, filename in (("provenance_receipt", "provenance.json"),
                          ("artifact_manifest_receipt", "artifact_manifest.json")):
        receipt = report.get(key, {})
        if receipt.get("path") != filename or receipt.get("sha256") != file_sha(directory / filename):
            raise ValueError("fresh report file binding differs: " + key)
    if file_sha(directory / "abi_manifest.json") != checker_environment["qualification_manifest_sha256"]:
        raise ValueError("fresh numerical ABI file hash differs")
    watched = report["supervisor_receipt"]
    summary_path = bound_path(directory, watched["path"])
    if file_sha(summary_path) != watched["sha256"]:
        raise ValueError("worker supervision receipt hash differs")
    validate_supervision(json.loads(summary_path.read_text()), worker_source)
    storage_source_bridge = None
    if report.get("shared_transforms") is True:
        from benchmarks.y_orbit_shared_storage_bridge import load_storage_source_bridge
        storage_source_bridge = load_storage_source_bridge(artifact_root,new_source=report["source"],
            new_environment=checker_environment,allocation_gate=allocation_gate)
        if (report.get("same80_storage_source_bridge")!=storage_source_bridge["receipt"]
                or provenance.get("same80_storage_source_bridge")!=storage_source_bridge["receipt"]
                or provenance.get("shared_transforms") is not True
                or "--shared-transforms" not in provenance.get("command",[])):
            raise ValueError("shared live representation detached from actual source/ABI/explicit command")
        validate_shared_storage_metadata(report.get("shared_transform_equivalence",{}),manifest)
        complete_events=[item for item in events if item.get("event")=="shared_complete_equivalence_before_any_factor"]
        if len(complete_events)!=1:raise ValueError("exact complete shared equivalence event required")
        event_index=events.index(complete_events[0])
        factor_indices=[i for i,item in enumerate(events) if item.get("event")=="all_branch_factor_created" or
                        item.get("event")=="allocation_admission" and item.get("boundary","").startswith("quotient_factor_q_")]
        if any(i<=event_index for i in factor_indices):raise ValueError("shared proof must finish before any factor admission")
        proof=report["shared_transform_equivalence"]
        frozen_event={key:value for key,value in complete_events[0].items() if key not in ("event","worker_elapsed_seconds")}
        boundary=next(i for i,item in enumerate(proof["owner_stages"]) if item["stage"]=="all_sectors_retained_before_factor")
        expected_event={**proof,"owner_stages":proof["owner_stages"][:boundary+1],
            "owner_artifacts":{key:value for stage_receipt in proof["owner_stages"][:boundary+1]
                               for key,value in stage_receipt["owner_artifacts"].items()}}
        if frozen_event!=expected_event:raise ValueError("complete shared proof report detached from pre-factor event")
        role_events=[{key:value for key,value in item.items() if key not in ("event","worker_elapsed_seconds")}
                     for item in events if item.get("event")=="shared_complete_role_equivalence_before_factor"]
        if role_events!=proof["roles"]:raise ValueError("per-role complete equivalence events differ")
        if stage=="solve" and not any(item["stage"]=="apply_recovery_complete" for item in proof["owner_stages"]):
            raise ValueError("solve must record actual shared apply/recovery lifecycle")
        owner_events=[item for item in events if item.get("event")=="shared_transform_owner_stage"]
        if [item.get("stage") for item in owner_events]!=[item["stage"] for item in proof["owner_stages"]]:
            raise ValueError("all actual owner lifecycle events required")
        for item,stage_receipt in zip(owner_events,proof["owner_stages"],strict=True):
            if item.get("receipt_sha256")!=digest_json(stage_receipt):raise ValueError("owner stage event/report digest differs")
            allocations=[entry for entry in events if entry.get("event")=="allocation_admission"
                         and entry.get("boundary")==stage_receipt["allocation_boundary"]]
            if (len(allocations)!=1 or allocations[0].get("admitted") is not True
                    or not 0<allocations[0].get("current_tree_rss_bytes",0)<TREE_CAP_BYTES
                    or events.index(allocations[0])>=events.index(item)):
                raise ValueError("each named owner receipt requires its actual prior whole-tree RSS admission")
    elif report.get("shared_transforms") not in (None,False):
        raise ValueError("shared-transform selection must be literal boolean")
    authority = SavedQuotientSnapshotAuthority(artifact_root / AUDIT_RUN, new_source=worker_source,
        new_environment=checker_environment, allocation_gate=allocation_gate, storage_source_bridge=storage_source_bridge)
    authority_receipt = plain_metadata(authority.receipt)
    bindings = report.get("recovery_identity_bindings", [])
    validate_recovery_identity_bindings(bindings, [plain_metadata(authority.report["twists"][b]["condensation"]["condensation"])
                                                   for b in range(2)])
    event_bindings = [{key: value for key, value in item.items() if key not in ("event", "worker_elapsed_seconds")}
                      for item in events if item.get("event") == "complete_recovery_identity_before_factor"]
    if event_bindings != bindings:
        raise ValueError("report recovery bridges detached from the actual pre-factor event receipts")
    if (report.get("authority") != authority_receipt
            or provenance.get("saved_quotient_snapshot_authority") != authority_receipt):
        raise ValueError("immutable audit to new source/ABI bridge differs")
    full_authority = SavedFullP4Authority(artifact_root / AUTHORITY_RUN, new_source=worker_source,
        new_environment=checker_environment, allocation_gate=allocation_gate, storage_source_bridge=storage_source_bridge)
    if (report.get("saved_full_p4_authority") != full_authority.receipt
            or provenance.get("saved_full_p4_authority") != full_authority.receipt):
        raise ValueError("immutable full-period field/mode authority receipt differs")
    descriptors, checks, historical_normalizations = report["artifacts"], [], []

    def save_checker_evidence(name, values):
        if not re.fullmatch(r"[A-Za-z0-9_]+", name) or not isinstance(values, np.ndarray) or values.dtype.hasobject:
            raise ValueError("checker normalization evidence requires a bounded typed array")
        allocation_gate("checker_sort_evidence_" + name, {"matrix_payload_bytes": 0,
            "workspace_bytes": (1 << 20) + (0 if values.flags.c_contiguous else int(values.nbytes))})
        path = evidence_directory / (name + ".npy")
        with path.open("xb") as stream:
            np.save(stream, values, allow_pickle=False)
        return {"path": str(path.relative_to(evidence_directory)), "shape": list(values.shape),
                "dtype": str(values.dtype), "payload_bytes": int(values.nbytes), "file_sha256": file_sha(path)}

    def load(name):
        descriptor = descriptors[name]
        path = bound_path(directory, descriptor["path"])
        if file_sha(path) != descriptor["file_sha256"]:
            raise ValueError("candidate artifact content hash differs: " + name)
        allocation_gate("checker_mmap_" + name, {"matrix_payload_bytes": int(descriptor["payload_bytes"]),
                                                "workspace_bytes": 1 << 20})
        value = np.load(path, allow_pickle=False, mmap_mode="r")
        if (list(value.shape) != descriptor["shape"] or str(value.dtype) != descriptor["dtype"]
                or value.nbytes != descriptor["payload_bytes"] or value.dtype.hasobject or value.flags.writeable):
            raise ValueError("candidate array shape/dtype/payload/readonly binding differs: " + name)
        finite_count = value.size
        if value.dtype.kind in "fc":
            flat = value.ravel(order="K")
            finite_count = sum(int(np.count_nonzero(np.isfinite(flat[start:start + 65536])))
                for start in range(0, flat.size, 65536))
        if (finite_count != value.size or descriptor.get("finite_entries") != value.size
                or descriptor.get("nonfinite_entries") != 0):
            raise ValueError("nonfinite artifact cannot qualify a pass: " + name)
        return value

    def csr(prefix, shape, *, csc=False, old=False):
        loader = full_authority.load if old else load
        data, indices, indptr = (loader(prefix + "_" + name) for name in ("data", "indices", "indptr"))
        integer_admission(shape, len(data), index_dtype=indices.dtype, indptr_dtype=indptr.dtype)
        integer_admission(shape, len(data), index_dtype=checker_environment["petsc_int_type"])
        integer_admission(shape, len(data), index_dtype="int32")
        pointer_count, index_bound = (shape[1] + 1, shape[0]) if csc else (shape[0] + 1, shape[1])
        if (data.ndim != 1 or data.dtype != np.dtype("complex128") or indices.shape != data.shape
                or indices.dtype.kind not in "iu" or indptr.dtype.kind not in "iu"
                or indptr.shape != (pointer_count,) or indptr[0] != 0 or indptr[-1] != len(data)
                or np.any(indptr < 0) or np.any(indptr > len(data)) or np.any(np.diff(indptr) < 0)
                or np.any(indices < 0) or np.any(indices >= index_bound)):
            raise ValueError("CSR/CSC dimensions and integer ranges must pass before narrowing")
        constructor = sparse.csc_matrix if csc else sparse.csr_matrix
        matrix = constructor((data, indices, indptr), shape=shape, copy=False)
        if csc:
            payload = matrix.data.nbytes + matrix.indices.nbytes + matrix.indptr.nbytes
            allocation_gate("checker_CSC_to_CSR_" + prefix, {"matrix_payload_bytes": payload, "workspace_bytes": payload})
            matrix = matrix.tocsr()
        if old and prefix == "full_Q" and not csc:
            pinned_descriptors = {part: full_authority.report["artifacts"]["full_Q_" + part]
                                  for part in ("data", "indices", "indptr")}
            validate_pinned_full_q_asset(prefix=prefix, old=old, csc=csc,
                head=full_authority.report["source"]["head"], shape=shape, descriptors=pinned_descriptors)
            matrix, receipt = sort_pinned_historical_full_q(matrix, descriptors=pinned_descriptors,
                allocation_gate=allocation_gate, save_evidence=save_checker_evidence,
                index_dtype=checker_environment["petsc_int_type"])
            historical_normalizations.append(receipt)
        # Every candidate and every other historical CSR keeps the existing
        # strict canonical-format audit. No fallback and no duplicate summation.
        csr_audit(matrix, petsc_index_dtype=checker_environment["petsc_int_type"])
        return matrix

    def add(name, measured, limit, **facts):
        measured = float(measured)
        checks.append({"name": name, "measured": measured, "limit": float(limit),
                       "passed": bool(np.isfinite(measured) and 0 <= measured <= limit), **facts})

    def relative(error, scale):
        return float(np.linalg.norm(error) / max(np.linalg.norm(scale), np.finfo(float).tiny))

    def bind_metric(name, measured, recorded):
        finite_gate(recorded, float("inf"), name + "_record")
        add(name + "_record_binding", abs(measured - recorded) / max(abs(measured), abs(recorded), 1e-300), 1e-8)

    # Verify every descriptor, including arrays not later used in a gate.
    for name in descriptors:
        value = load(name)
        del value
    for q, facts in enumerate(report["reformed_blocks"]):
        candidate, reference = csr(f"q_{q}_S", (Q_ROWS[q], Q_ROWS[q])), authority.q_block(q)
        if sparse_hash(candidate) != facts["CSR_sha256"]:
            raise ValueError("fresh q block CSR hash differs")
        payload = (candidate.nnz + reference.nnz) * 24 + (Q_ROWS[q] + 1) * 8
        allocation_gate(f"checker_q_{q}_complete_difference", {"matrix_payload_bytes": payload, "workspace_bytes": payload})
        difference = candidate - reference
        norm = relative(difference.data, reference.data)
        peak = float(np.max(np.abs(difference.data))) if difference.nnz else 0.0
        peak /= max(float(np.max(np.abs(reference.data))), np.finfo(float).tiny)
        add(f"q_{q}_all_entries_norm", norm, 1e-11)
        add(f"q_{q}_all_entries_max", peak, 1e-11)
        bind_metric(f"q_{q}_norm", norm, facts["relative_frobenius_difference"])
        bind_metric(f"q_{q}_max", peak, facts["relative_max_difference"])
        if stage == "solve":
            a, b, xa, xb, repeat, summed = (load(f"q_{q}_" + key) for key in
                ("rhs_a", "rhs_b", "solution_a", "solution_b", "solution_a_repeat", "solution_sum"))
            if any(values.dtype != np.dtype("complex128") for values in (a, b, xa, xb, repeat, summed)):
                raise ValueError("raw factor vectors require complex128")
            if min(np.linalg.norm(a), np.linalg.norm(b), np.linalg.norm(xa), np.linalg.norm(xb)) <= 0:
                raise ValueError("factor controls cannot be vacuous zero vectors")
            residual = max(relative(candidate @ xa - a, a), relative(candidate @ xb - b, b))
            repeated, linearity = relative(repeat - xa, xa), relative(summed - xa - xb, summed)
            add(f"q_{q}_factor_original_true_residual", residual, 1e-10)
            add(f"q_{q}_factor_repeat", repeated, 1e-11)
            add(f"q_{q}_factor_linearity", linearity, 1e-11)
            test = report["factor"]["tests"][q]
            for key, value in (("true_block_residual", residual),
                               ("repeated_difference", repeated), ("linearity_difference", linearity)):
                bind_metric(f"q_{q}_" + key, value, test[key])
        del candidate, reference, difference

    # Native inventories and physical coefficients are new exports, compared
    # with immutable controls without exposing historical maps to candidate setup.
    independent, interior = load("independent_storage_rows"), load("actual_interior_positions")
    for name in ("independent_storage_rows", "actual_interior_positions", "full_mpc_slaves", "full_mpc_masters",
                 "full_mpc_coefficients", "full_mpc_offsets", "port_q_labels", "original_carrier_global_rows",
                 "original_carrier_ownership_range", "original_carrier_slave_rows", "original_mode_e_vectors",
                 "original_mode_k_vectors", "original_mode_outward_signs", "original_mode_magnetic_denominator",
                 "original_mode_boundary_area", "original_mode_incident_projections", "port_original_H"):
        if not np.array_equal(load(name), full_authority.load(name)):
            raise ValueError("exact rebuilt original inventory differs: " + name)
    for b in range(2):
        for name in ("independent_storage_rows", "trace_original_rows", "interior_original_rows", "slave_storage_rows", "original_H"):
            key = f"twist_{b}_" + name
            if not np.array_equal(load(key), authority.load(key)):
                raise ValueError("exact rebuilt local inventory differs: " + key)
    h = load("port_original_H")
    if np.any(h <= 0):
        raise ValueError("all original H must remain strictly positive")
    add("positive_H_coordinate_scale", relative(load("port_factor_coordinate_scale") - 1 / np.sqrt(h), 1 / np.sqrt(h)), 1e-12)
    original_c = csr("original_port_C", (17204, 532), csc=True)
    original_d = csr("original_port_D", (532, 17204))
    old_c = csr("original_port_C", (17204, 532), csc=True, old=True)
    old_d = csr("original_port_D", (532, 17204), old=True)
    for name, actual, expected in (("C", original_c, old_c), ("D", original_d, old_d)):
        add("restored_global_" + name + "_numeric", relative((actual - expected).data, expected.data), 1e-12)
    del old_c, old_d
    # Restoration receipt validation is delegated to the same authority contract;
    # no second C/D packet reader or runtime coefficient injection exists here.
    restoration = report.get("restoration", [])
    validate_restoration_metadata(restoration, authority_receipt=authority_receipt, source=worker_source,
        environment=checker_environment, sector_identities={str(b): plain_metadata(authority.receipts[str(b)]["carrier_identity_after"])
        for b in range(2)}, global_keys=full_authority.report["mode_keys"])
    # Bind exported final functionals back to the public carrier's complete
    # ordered numeric digest, so an aggregate norm cannot hide a weak mode.
    numeric = hashlib.sha256()
    numeric.update(_canonical_json_bytes({"schema": "task40extra.live-boundary-carrier-digest.v1",
        "global_rows": int(load("original_carrier_global_rows")),
        "ownership_range": tuple(int(v) for v in load("original_carrier_ownership_range")),
        "mode_count": 532, "slave_rows": _array_signature(load("original_carrier_slave_rows"))}))
    c_data, c_rows, c_ptr = (load("original_port_C_" + key) for key in ("data", "indices", "indptr"))
    d_data, d_rows, d_ptr = (load("original_port_D_" + key) for key in ("data", "indices", "indptr"))
    for index, key in enumerate(full_authority.report["mode_keys"]):
        c_start, c_end, d_start, d_end = int(c_ptr[index]), int(c_ptr[index + 1]), int(d_ptr[index]), int(d_ptr[index + 1])
        if c_end <= c_start or d_end <= d_start:
            raise ValueError("every original restored C/D functional must remain nonempty")
        numeric.update(_canonical_json_bytes({"index": index, "key": (index, *key), "H": float(h[index]),
            "coupling_rows": _array_signature(c_rows[c_start:c_end]),
            "coupling_values": _array_signature(c_data[c_start:c_end]),
            "projection_rows": _array_signature(d_rows[d_start:d_end]),
            "projection_values": _array_signature(d_data[d_start:d_end])}))
    if numeric.hexdigest() != restoration[0]["restored_public_carrier_identity"]["carrier_numeric_sha256"]:
        raise ValueError("saved original functionals detached from the exact restored public carrier digest")
    del c_data, c_rows, c_ptr, d_data, d_rows, d_ptr
    for index, twist in enumerate((None, 0, 1)):
        context = _jsonable(authority.snapshot_context(twist))
        verification = restoration[index]["historical_primary_surface_file_verification"]
        validate_historical_file_metadata(verification, context_sha=digest_json(context),
            expected_gauss=context["gauss"]["compiled_forms_verified"])
        for name, record in verification["records"].items():
            for role, proof in record.items():
                allocation_gate(f"checker_historical_file_{index}_{name}_{role}",
                                {"matrix_payload_bytes": 0, "workspace_bytes": 2 << 20})
                path = Path(proof["recorded_path"])
                before = path.stat()
                digest = file_sha(path)
                after = path.stat()
                if (digest != proof["expected_sha256"] or after.st_size != proof["verified_bytes"]
                        or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
                        != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)):
                    raise ValueError("historical primary kernel file changed since restoration")
    for b in range(2):
        if restoration[b + 1]["local_raw_receipt_sha256"] != authority.report["twists"][b]["raw_port_receipt"]["sha256"]:
            raise ValueError("restored sector historical raw receipt binding differs")

    if stage == "solve":
        full_f = csr("full_F", (15872, 15872), old=True)
        full_ri = csr("full_R_inverse", (15872, 15872), old=True)
        full_q = csr("full_Q", (15872, 15872), old=True)
        generic, interior_only = load("generic_rhs"), load("interior_only_rhs")
        if np.count_nonzero(generic[interior]) != 8640 or np.count_nonzero(interior_only[interior]) != 8640:
            raise ValueError("every original interior RHS entry must be excited")
        complement = np.ones(15872, bool); complement[interior] = False
        if np.any(interior_only[complement] != 0):
            raise ValueError("interior-only load has non-interior support")
        generic_q_norms = np.linalg.norm(np.asarray(full_q.conj().T @ generic).reshape(4, 3968), axis=1)
        if np.min(generic_q_norms) / np.linalg.norm(generic_q_norms) < 1e-3:
            raise ValueError("generic load must excite all four actual q sectors")
        e_vectors, k_vectors, outward = (load("original_mode_" + key) for key in
                                        ("e_vectors", "k_vectors", "outward_signs"))
        denominator, area = load("original_mode_magnetic_denominator"), load("original_mode_boundary_area")
        incident_physical = load("original_mode_incident_projections")
        if denominator == 0 or area <= 0:
            raise ValueError("physical output denominator/area must be nonzero positive")
        cfg, _, input_sha = pilot_config(Path(__file__).resolve().parents[1] /
            "input/task40extra_0p7nm_engineering/nonseparable_g0_p6_q4_review_v1.dat", azimuth_deg=5.)
        physical_modes = outgoing_port_modes_3d(cfg)
        if (input_sha != INPUT_SHA or len(physical_modes) != 532
                or not np.array_equal(e_vectors, np.asarray([mode.e_vector for mode in physical_modes]))
                or not np.array_equal(k_vectors, np.asarray([mode.k_vector for mode in physical_modes]))
                or not np.array_equal(outward, np.asarray([1 if mode.side == "top" else -1 for mode in physical_modes]))
                or not np.array_equal(incident_physical, np.asarray([incident_projection_in_solver_coordinates(
                    mode, cfg, BOUNDARY_PLANE) for mode in physical_modes]))
                or denominator != cfg.k0 * complex(cfg.mu_r)
                or area != (cfg.x_max - cfg.x_min) * (cfg.y_max - cfg.y_min)):
            raise ValueError("saved original532 physical mode/config/incident geometry is detached from its unchanged generator")
        coefficients, offsets = load("full_mpc_coefficients"), load("full_mpc_offsets")
        masters, slaves = load("full_mpc_masters"), load("full_mpc_slaves")
        if (np.any(np.diff(independent) <= 0) or np.any(np.diff(offsets) < 0)
                or offsets[0] != 0 or offsets[-1] != len(coefficients) or len(masters) != len(coefficients)
                or len(np.intersect1d(slaves, masters)) or not np.array_equal(
                    np.sort(slaves), np.setdiff1d(np.arange(17204), independent))
                or np.any(masters < 0) or np.any(masters >= 17204)):
            raise ValueError("complete actual finalized native MPC inventory differs")
        mode_checks = {}
        q_labels = load("port_q_labels")
        augmented = report.get("augmented_controls", [])
        if len(augmented) != 4 or [v.get("q") for v in augmented] != list(range(4)):
            raise ValueError("all four complete original augmented controls required")
        d_norms = np.sqrt(np.asarray(original_d.multiply(original_d.conj()).sum(axis=1)).real.ravel())
        for q, packet in enumerate(augmented):
            label = f"aug_q_{q}"
            f, g, effective, active = (load(label + "_" + key) for key in
                                       ("FE_rhs", "port_rhs", "effective_rhs", "solution"))
            field, action, volume, coupling = (load(label + "_" + key) for key in
                ("solution_storage", "original_action", "volume_action", "coupling_action"))
            alpha, projection, local_h = (load(label + "_" + key) for key in
                                         ("auxiliary_ports", "projection", "normalization_h"))
            if np.any(field[slaves] != 0) or not np.array_equal(field[independent], active) or not np.array_equal(local_h, h):
                raise ValueError("manufactured augmented field/storage/H binding differs")
            rhs_storage = load(label + "_rhs_storage")
            if not np.array_equal(rhs_storage[independent], f) or np.any(rhs_storage[slaves] != 0):
                raise ValueError("manufactured augmented FE RHS native storage differs")
            modal = np.asarray(full_q.conj().T @ f).reshape(4, 3968)
            if np.count_nonzero(modal[q]) != 3968 or np.count_nonzero(f[interior]) != 8640:
                raise ValueError("manufactured within-q load must excite every3968 FE channel including interiors")
            # Native rounding may leave off-q roundoff; judge against this q's own scale.
            other = np.delete(modal, q, axis=0)
            add(label + "_dual_single_q_identity", relative(other, modal[q]), 1e-11)
            if np.count_nonzero(g[q_labels == q]) != np.count_nonzero(q_labels == q) or np.any(g[q_labels != q] != 0):
                raise ValueError("manufactured original port RHS must excite every alias of exactly this q")
            expected_effective = f - np.asarray(original_c @ (g / h))[independent]
            add(label + "_effective_rhs_sign_binding", relative(effective - expected_effective, expected_effective), 1e-12)
            native = effective - action[independent]
            top = f - volume[independent] - coupling[independent]
            port = projection - h * alpha + g
            add(label + "_full_original_true_residual", relative(native, effective), 1e-10)
            add(label + "_augmented_FE_true_residual", relative(top, f), 1e-10)
            operation_scale = d_norms * np.linalg.norm(active) + np.abs(h * alpha) + np.abs(g)
            _require_operation_scale_binding(load(label + "_port_operation_scale"), operation_scale, label)
            errors = np.abs(port)
            if np.any((operation_scale == 0) & (errors != 0)):
                raise ValueError("manufactured port closure has nonzero error at zero operation scale")
            ratios = np.divide(errors, operation_scale, out=np.zeros_like(errors), where=operation_scale != 0)
            add(label + "_all532_augmented_port_closure", float(np.max(ratios)), 1e-10)
            add(label + "_D_full_field_projection", relative(original_d @ field - projection, projection), 1e-11)
            add(label + "_C_auxiliary_coupling", relative(original_c @ alpha - coupling, f), 1e-11)
            add(label + "_native_residual_saved", relative(native - load(label + "_native_residual")[independent], effective), 1e-12)
            add(label + "_augmented_FE_residual_saved", relative(top - load(label + "_augmented_FE_residual")[independent], f), 1e-12)
            add(label + "_augmented_port_residual_saved", relative(port - load(label + "_augmented_port_residual"), operation_scale), 1e-12)
            derived = top - np.asarray(original_c @ (port / h))[independent]
            add(label + "_original_augmented_residual_identity", np.linalg.norm(native - derived) /
                max(np.linalg.norm(effective) + np.linalg.norm(action[independent]), np.finfo(float).tiny), 1e-10)
        for name in SOURCES:
            if not np.array_equal(load(name + "_rhs"), full_authority.load(name + "_rhs")):
                raise ValueError("original fixed source changed: " + name)
            for prefix, source_key in (("regular", "regular_sources"), ("notch", "notched_sources")):
                label, packet = prefix + "_" + name, report[source_key][name]
                rhs, field, active = load(label + "_rhs_storage"), load(label + "_solution_storage"), load(label + "_solution")
                if (np.any(field[slaves] != 0) or np.any(rhs[slaves] != 0)
                        or not np.array_equal(field[independent], active)
                        or not np.array_equal(rhs[independent], load(name + "_rhs"))):
                    raise ValueError("full native packet is detached from its independent solve/source")
                action, volume, coupling = (load(label + "_" + key) for key in
                                           ("original_action", "volume_action", "coupling_action"))
                alpha, projection, local_h = (load(label + "_" + key) for key in
                                             ("auxiliary_ports", "projection", "normalization_h"))
                native, top, port = rhs - action, rhs - volume - coupling, projection - local_h * alpha
                add(label + "_original_A4_true_residual", relative(native, rhs), 1e-10)
                add(label + "_augmented_FE_true_residual", relative(top, rhs), 1e-10)
                add(label + "_augmented_port_closure", relative(port, projection), 1e-10)
                add(label + "_native_residual_saved", relative(native - load(label + "_native_residual"), rhs), 1e-12)
                add(label + "_augmented_FE_residual_saved", relative(top - load(label + "_augmented_FE_residual"), rhs), 1e-12)
                add(label + "_augmented_port_residual_saved", relative(port - load(label + "_augmented_port_residual"), projection), 1e-12)
                add(label + "_original_D_final_field_projection", relative(original_d @ field - projection, projection), 1e-11)
                add(label + "_original_C_alpha_coupling", relative(original_c @ alpha - coupling, rhs), 1e-11)
                if not np.array_equal(local_h, h):
                    raise ValueError("packet original H inventory differs")
                derived = top - original_c @ (port / h)
                identity = np.linalg.norm(native - derived) / max(np.linalg.norm(rhs) + np.linalg.norm(action), np.finfo(float).tiny)
                add(label + "_independent_augmented_residual_identity", identity, 1e-10)
                norms = np.linalg.norm(np.asarray(full_f.conj().T @ (full_ri @ active)).reshape(4, 3968), axis=1)
                add(label + "_primal_q_norm_record", relative(norms - packet["solution_primal_q_norms"], norms), 1e-12)
                add(label + "_saved_full_p4_solution_difference", relative(active - full_authority.load(label + "_solution"),
                                                                          full_authority.load(label + "_solution")), 1e-9)
                recovered = field.copy()
                for slave in slaves:
                    start, end = int(offsets[slave]), int(offsets[slave + 1])
                    if end <= start:
                        raise ValueError("actual MPC slave expansion cannot be empty")
                    recovered[slave] = np.dot(coefficients[start:end], field[masters[start:end]])
                add(label + "_actual_MPC_backsubstitution", relative(load(label + "_recovered_field") - recovered, recovered), 1e-12)
                add(label + "_saved_full_p4_recovered_field_difference", relative(load(label + "_recovered_field") -
                    full_authority.load(label + "_recovered_field"), full_authority.load(label + "_recovered_field")), 1e-9)
                total = np.asarray(original_d @ field) / h
                incident = incident_physical if name == "physical" else np.zeros(532, complex)
                outgoing = total.copy(); outgoing[outward == 1] -= incident[outward == 1]
                electric = outgoing[:, None] * e_vectors
                magnetic = np.cross(k_vectors, electric) / denominator
                power = np.maximum(.5 * np.real(np.cross(electric, np.conj(magnetic)))[:, 2] * outward, 0) * area
                scale = np.sqrt(np.asarray(original_d.multiply(original_d.conj()).sum(axis=1)).real.ravel()) / h * np.linalg.norm(active)
                unit_magnetic = np.cross(k_vectors, e_vectors) / denominator
                expected = {label + "_plane_total_auxiliary": total, label + "_plane_outgoing_auxiliary": outgoing,
                    label + "_plane_electric": electric, label + "_plane_magnetic": magnetic,
                    label + "_direct_plane_outgoing_power_diagnostic": power, label + "_mode_local_amplitude_scale": scale,
                    label + "_plane_electric_scale": scale * np.linalg.norm(e_vectors, axis=1),
                    label + "_plane_magnetic_scale": scale * np.linalg.norm(unit_magnetic, axis=1),
                    label + "_mode_power_operation_scale": .5 * area * (scale + np.abs(incident))**2 *
                        np.linalg.norm(e_vectors, axis=1) * np.linalg.norm(unit_magnetic, axis=1)}
                if not np.array_equal(load(label + "_plane_incident_projections"), incident):
                    raise ValueError("per-source original incident subtraction binding differs")
                for key in ("mode_local_amplitude_scale", "plane_electric_scale", "plane_magnetic_scale", "mode_power_operation_scale"):
                    _require_operation_scale_binding(load(label + "_" + key), expected[label + "_" + key], key)
                mode_checks[label] = {"independent_original_coefficients": compare_mode_evidence(load, expected.__getitem__, label),
                                     "immutable_full_p4_outputs": compare_mode_evidence(load, full_authority.load, label)}
                for comparison, metrics in mode_checks[label].items():
                    for key, metric in metrics.items():
                        add(label + "_" + comparison + "_" + key, metric["relative_local_operation_error_max"], 1e-10,
                            compared_modes=532, worst_mode_index=metric["worst_mode_index"])
                add(label + "_plane_auxiliary_vs_original_alpha_all532", per_mode_operation_error(
                    np.abs(load(label + "_plane_total_auxiliary") - alpha), scale), 1e-10, compared_modes=532)
                # Global values must survive the existing representability-safe
                # conversion and agree with both this field and immutable p4.
                # Compare in plane coordinates using each mode's original scale.
                old_scale = full_authority.load(label + "_mode_local_amplitude_scale")
                for global_key, expected_plane in (("global_total_auxiliary", total),
                                                    ("global_incident_projections", incident)):
                    converted = solver_amplitudes_from_global(load(label + "_" + global_key), physical_modes, cfg, BOUNDARY_PLANE)
                    old_converted = solver_amplitudes_from_global(full_authority.load(label + "_" + global_key),
                                                                  physical_modes, cfg, BOUNDARY_PLANE)
                    if global_key == "global_incident_projections":
                        operation = np.abs(incident)
                        old_operation = np.abs(full_authority.load(label + "_plane_incident_projections"))
                    else:
                        operation, old_operation = scale, old_scale
                    add(label + "_" + global_key + "_original_plane_binding", per_mode_operation_error(
                        np.abs(converted - expected_plane), operation), 1e-10, compared_modes=532)
                    add(label + "_" + global_key + "_immutable_p4_binding", per_mode_operation_error(
                        np.abs(converted - old_converted), operation + old_operation), 1e-10, compared_modes=532)
                output = packet.get("outputs", {})
                if (output.get("finite_plane_mode_count") != 532 or output.get("status") != "representable_global_output"
                        or output.get("global_output_component_consistency_checked") is not True
                        or output.get("full_physical_field_recovered") is not True or output.get("official_results") is not False):
                    raise ValueError("complete representable original532 output packet is required")
                if prefix == "notch":
                    if (packet.get("reason", 0) <= 0 or not 0 < packet.get("iterations", 0) <= 128
                            or packet.get("outer_operator") != "full_original_3D_FFCx_form_action_plus_all_DtN_modes"
                            or packet.get("right_pc") != "all_y_blocks_regular_geometry_reference_inverse"):
                        raise ValueError("original right-FGMRES positive convergence and bound are required")
                    history = packet.get("history", [])
                    if len(history) != packet["iterations"] + 1 or [v.get("iteration") for v in history] != list(range(len(history))):
                        raise ValueError("every original residual iteration is required")
                    for step in history:
                        finite_gate(step.get("full_original_true_residual"), float("inf"), label + "_history")
                    if name == "physical":
                        nonzero = float(np.linalg.norm(norms[1:]) / np.linalg.norm(norms))
                        if not math.isfinite(nonzero) or nonzero <= 1e-12:
                            raise ValueError("actual notch physical field must retain nonzero q modes")
                        bind_metric(label + "_nonzero_q", nonzero, packet["nonzero_q_primal_relative"])
    else:
        mode_checks = {}
    if stage=="solve" and len(checks)!=312:raise ValueError("complete original312 residual/output gates required")
    shared_checks=[]
    if report.get("shared_transforms") is True:
        shared_checks=check_shared_storage_evidence(report["shared_transform_equivalence"],load=load,
            descriptors=descriptors,allocation_gate=allocation_gate,
            native_inventories={"full":"independent_storage_rows","twist_0":"twist_0_independent_storage_rows",
                                "twist_1":"twist_1_independent_storage_rows"},
            snapshot_contexts={"full":plain_metadata(authority.snapshot_context(None)),
                "twist_0":plain_metadata(authority.snapshot_context(0)),"twist_1":plain_metadata(authority.snapshot_context(1))})
    return {"schema": CHECKER_SCHEMA, "gate_pass": bool(checks) and all(v["passed"] for v in checks)
            and (report.get("shared_transforms") is not True or bool(shared_checks) and all(v["passed"] for v in shared_checks)),
            "original_check_count":len(checks), "shared_storage_checks":shared_checks,
            "shared_storage_check_count":len(shared_checks), "shared_transforms":report.get("shared_transforms",False),
            "shared_owner_RSS_comparison":[{"stage":item["stage"],
                "sum_view_nbytes_with_aliases":item["sum_view_nbytes_with_aliases"],
                "unique_backing_owner_nbytes":item["unique_backing_owner_nbytes"],
                "allocation_entry_tree_RSS_bytes":next(entry["current_tree_rss_bytes"] for entry in events
                    if entry.get("event")=="allocation_admission" and entry.get("boundary")==item["allocation_boundary"]),
                "named_payload_is_RSS":False} for item in report.get("shared_transform_equivalence",{}).get("owner_stages",[])],
            "evidence_valid": True, "checks": checks, "report_sha256": file_sha(report_path),
            "provenance_sha256": file_sha(provenance_path), "artifact_manifest_sha256": digest_json(descriptors),
            "source": worker_source, "checker_source": checker_source, "checker_source_bridge": source_binding,
            "environment": checker_environment, "checker_attempt_directory": str(evidence_directory),
            "historical_validation_normalizations": historical_normalizations, "PDE_rerun": False,
            "command": sys.argv, "stage": stage, "authority": authority_receipt,
            "saved_full_p4_authority": full_authority.receipt, "degree": 4, "physical_mode_count": 532,
            "factor_count": 0 if stage == "prefactor" else 4, "PDE_solved": stage == "solve",
            "official_results": False, "mode_checks": mode_checks,
            "qualification": "prefactor restoration/volume/q-compare only" if stage == "prefactor"
                             else "scaled full3D quotient inverse and genuine-notch probe only"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--expected-head", "--expected-checker-head", dest="expected_head", required=True,
        help="actual clean checker HEAD; the saved worker source remains separately bound")
    parser.add_argument("--stage", choices=("prefactor", "solve"), required=True)
    parser.add_argument("--run-directory", type=Path, required=True)
    parser.add_argument("--checker-directory", type=Path,
        help="fresh ignored attempt directory for saved-worker rechecks; worker evidence remains readonly")
    parser.add_argument("--research-wall-seconds", type=int, choices=(1800,4500),
        help="explicit X/wall1800 or XZ/Y/wall4500 allowance; ordinary default is600 seconds")
    parser.add_argument("--research-memory-gib", type=int, choices=(2,3),
        help="explicit X/solve/wall1800/2GiB or XZ/Y/solve/wall4500/3GiB cap; ordinary default is1.5GiB")
    args = parser.parse_args(argv)
    started = time.monotonic()
    from benchmarks.run_real_p4_probe import source_facts, environment_facts
    from benchmarks.task038_full3d_jit_staging import process_tree_snapshot, append_jsonl
    from benchmarks.subreaper_watchdog import memory_envelope, runtime_tree_cap
    from src.solvers.real_p4_probe import write_json
    directory = args.run_directory.resolve()
    output_directory = directory if args.checker_directory is None else args.checker_directory.resolve()
    artifact_root = Path(__file__).resolve().parents[1] / "benchmarks/artifacts/task40extra_dot_parallel_cloud"
    if not output_directory.is_relative_to(artifact_root.resolve()):
        raise ValueError("checker attempt must stay inside the own ignored artifact subtree")
    if args.checker_directory is not None and (output_directory == directory or not output_directory.is_dir()
            or any((output_directory / name).exists() for name in
                   ("independent_checker.json", "checker_events.jsonl", "checker_phase.json", "checker_traceback.txt"))):
        raise ValueError("checker recheck requires a fresh supervisor-created attempt directory")
    parent = int(os.environ.get("PHYSICAL_WATCHDOG_PARENT_PID", "0"))
    cap = int(os.environ.get("PHYSICAL_WATCHDOG_LAUNCH_CAP_BYTES", "0"))
    from benchmarks.run_y_orbit_quotient_probe import research_wall_budget, research_phase_budget, research_memory_child_budget
    timing_provenance = json.loads((directory / "provenance.json").read_text())
    direct_profile = timing_provenance.get("direct_profile")
    tree_cap, memory_launch_admission = research_memory_child_budget(direct_profile, args.stage,
        args.research_wall_seconds, args.research_memory_gib, os.environ, cap)
    if (not args.worker or parent != os.getppid() or parent <= 0 or not 0 < cap <= tree_cap
            or os.environ.get("PHYSICAL_TIMEBASE_GUARD") != "1"):
        raise RuntimeError("checker requires the quotient CLI's strict supervised child contract")
    wall_seconds = research_wall_budget(direct_profile, args.research_wall_seconds)
    phase_seconds = research_phase_budget(direct_profile, args.research_wall_seconds, os.environ)
    # Actual clean source admission belongs outside the failure-writing try.
    # A stale expected HEAD or refused output path must not overwrite the
    # immutable worker's earlier checker report, traceback or phase records.
    source = source_facts(args.expected_head)
    worker_source = json.loads((directory / "probe_report.json").read_text())["source"]
    admit_checker_output(worker_source, source, worker_directory=directory, output_directory=output_directory,
        explicit_checker_directory=args.checker_directory is not None,
        direct_profile=direct_profile,
        prior_checker_output=any((output_directory / name).exists() for name in
            ("independent_checker.json", "checker_events.jsonl", "checker_phase.json", "checker_traceback.txt")))
    environment = swap_baseline = None

    def global_swap():
        values = {}
        for line in Path("/proc/vmstat").read_text().splitlines():
            key, value = line.split()
            if key in ("pswpin", "pswpout"):
                values[key] = int(value)
        if set(values) != {"pswpin", "pswpout"}:
            raise RuntimeError("checker requires readable global swap counters")
        return values

    def allocation_gate(name, facts):
        elapsed = time.monotonic() - started
        if args.research_wall_seconds is not None and elapsed >= phase_seconds:
            raise TimeoutError("direct checker remaining watchdog allowance expired before allocation")
        sample = process_tree_snapshot(parent, name, None, pss_sampling_policy="disabled_by_profile")
        if (sample.get("all_status_readable") is not True or sample.get("identity_complete") is not True
                or sample.get("swap_bytes") != 0 or global_swap() != swap_baseline):
            raise RuntimeError("checker requires fresh readable whole-tree identity and zero swap")
        payload, workspace = int(facts.get("matrix_payload_bytes", 0)), int(facts.get("workspace_bytes", 0))
        if min(payload, workspace) < 0:
            raise ValueError("negative checker allocation declaration")
        projected = int(sample["rss_bytes"]) + payload + workspace + RESERVE_BYTES
        envelope = memory_envelope()
        effective = runtime_tree_cap(cap, int(sample["rss_bytes"]), envelope, explicit_tree_cap_bytes=tree_cap)
        append_jsonl(output_directory / "checker_events.jsonl", {"event": "allocation_admission", "boundary": name,
            "current_tree_rss_bytes": sample["rss_bytes"], "requested_payload_bytes": payload,
            "workspace_bytes": workspace, "evidence_reserve_bytes": RESERVE_BYTES, "projected_tree_bytes": projected,
            "launch_cap_bytes": cap, "effective_cap_bytes": effective, "fresh_memory_envelope": envelope,
            "admitted": projected < effective, "global_swap_counters": swap_baseline,
            **({"research_wall_seconds": wall_seconds, "phase_wall_seconds": phase_seconds,
                "checker_elapsed_seconds": elapsed} if args.research_wall_seconds is not None else {}),
            **({"research_memory_gib": args.research_memory_gib, "requested_tree_cap_bytes": tree_cap}
               if args.research_memory_gib is not None else {})})
        write_json(output_directory / "checker_phase.json", {"phase": name, "factor_count": 0,
            **({"research_wall_seconds": wall_seconds, "phase_wall_seconds": phase_seconds,
                "checker_elapsed_seconds": elapsed} if args.research_wall_seconds is not None else {}),
            **({"research_memory_gib": args.research_memory_gib, "requested_tree_cap_bytes": tree_cap}
               if args.research_memory_gib is not None else {})})
        if projected >= effective:
            raise MemoryError("checker measured whole-tree allocation plus evidence reserve exceeds cap")
    try:
        if source_facts(args.expected_head) != source:
            raise RuntimeError("checker source changed after output admission")
        environment = environment_facts()
        swap_baseline = global_swap()
        result = check(directory, checker_source=source, checker_environment=environment,
                       stage=args.stage, allocation_gate=allocation_gate, checker_directory=output_directory,
                       research_wall_seconds=args.research_wall_seconds, research_memory_gib=args.research_memory_gib)
        if source_facts(args.expected_head) != source:
            raise RuntimeError("source changed during independent checker")
    except Exception as exc:
        result = {"schema": CHECKER_SCHEMA, "gate_pass": False, "evidence_valid": False,
                  "error_type": type(exc).__name__, "reason": str(exc), "source": source,
                  "environment": environment, "stage": args.stage, "degree": 4, "official_results": False}
        (output_directory / "checker_traceback.txt").write_text(traceback.format_exc())
    # Hash-bound provenance for this attempt never mutates the worker report.
    result["checker_attempt_provenance"] = {"checker_source": source, "environment": environment,
        "command": sys.argv, "worker_directory": str(directory), "output_directory": str(output_directory),
        "PDE_rerun": False,
        **({"research_wall_seconds": wall_seconds, "phase_wall_seconds": phase_seconds}
           if args.research_wall_seconds is not None else {}),
        **({"research_memory_gib": args.research_memory_gib, "requested_tree_cap_bytes": tree_cap,
            "research_memory_launch_admission": memory_launch_admission}
           if args.research_memory_gib is not None else {})}
    write_json(output_directory / "independent_checker.json", result)
    return 0 if result["gate_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
