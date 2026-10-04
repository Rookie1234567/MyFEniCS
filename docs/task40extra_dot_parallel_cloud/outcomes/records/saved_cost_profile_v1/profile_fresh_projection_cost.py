"""Single-recipe saved projection cost diagnostics; never all8/PDE replay.

Caller supplies the exact replay loader, resource gate and deterministic JSONL
sink after frozen source admission, with an independent <=60-second watchdog.
Profile empty and explicitly SYNTHETIC saved-q0-seeded accumulators separately.
The seeded value is saved complete q0 plus one contribution, not a recovered
intermediate state or physical operator qualification. Archived files are read
only. Profiler overhead is included in measured wall time and reported; selected
cheap cases may also run unprofiled with identical callbacks for bitwise proof.
"""
from __future__ import annotations

import cProfile
import pstats
from time import perf_counter

import numpy as np
from scipy import sparse

from src.solvers import fresh_projection_support_replay as replay

SCHEMA = "task40extra.saved-projection-single-recipe-cost.v1"
LABELS = ("volume/cell/0", "direct/C/port/2")


def _select(report, labels):
    replay._require(tuple(labels) in ((LABELS[0],), LABELS), "only first volume and optional first q0-compatible direct C permitted")
    matches = [s for s in report["local_compact_snapshots"] if s["twist"] == 0]
    replay._require(len(matches) == 1 and matches[0]["q_indices"] == [0, 2], "exact b0/q0 snapshot required")
    snapshot = matches[0]
    targets = [b for b in report["reformed_blocks"] if b["q"] == 0]
    replay._require(len(targets) == 1 and targets[0]["csr_prefix"] == "q_0_S"
                    and targets[0]["shape"] == [snapshot["qmaps"][0]["shape"][1]] * 2,
                    "saved q0 target shape/identity differs")
    recipes = []
    for label in labels:
        items = [r for r in snapshot["recipes"] if r["label"] == label]
        replay._require(len(items) == 1 and items[0]["kind"] == "dense", "exact single dense recipe required: " + label)
        recipes.append(items[0])
    return snapshot, targets[0], recipes


def _seed(accumulator, target):
    payload = sum(v.nbytes for v in (target.data, target.indices, target.indptr))
    # Admission counts coexistence with empty CSR and a possible constructor
    # copy. Copies are owned by the accumulator after assignment.
    accumulator._admit("synthetic_saved_q0_seed_copy", 2 * payload,
        synthetic_seed=True, before_seed_copy_and_constructor=True,
        saved_seed_CSR_payload_bytes=payload, constructor_copy_allowance_bytes=payload)
    data = np.array(target.data, copy=True, order="C")
    indices = np.array(target.indices, copy=True, order="C")
    indptr = np.array(target.indptr, copy=True, order="C")
    accumulator.result = sparse.csr_matrix((data, indices, indptr), shape=target.shape, copy=False)


def _category(filename, name, callback_keys):
    if name in ("_merge", "_merged_entries", "_shift_indptr"):
        return "scalar_merge_and_global_replacement"
    if name == "_gather_tile":
        return "qmap_gather"
    if name in ("_mark_stored_tiles", "_has_stored_column"):
        return "structural_support_discovery"
    if name in ("_numeric_sha", "csr_fingerprint", "_sha", "_sha_file") or "hashlib" in name or "HASH" in name:
        return "hashes"
    if "json" in filename or name in ("_json_bytes", "emit") or "write" in name or "flush" in name:
        return "JSON_and_file_sink"
    if (filename, name) in callback_keys["event"]:
        return "JSON_and_file_sink"
    if ((filename, name) in callback_keys["gate"] or any(token in name.lower()
            for token in ("allocation", "rss", "process_tree", "memory_envelope", "tree_sample", "process_iter"))
            or "psutil" in filename):
        return "allocations_and_process_sampling"
    if name == "_seed" or any(token in name for token in ("numpy.array", "numpy.empty", "numpy.zeros", "csr_matrix.__init__")):
        return "array_and_CSR_allocations"
    return "other"


def _code_key(function):
    code = getattr(function, "__code__", None)
    if code is None and hasattr(function, "__call__"):
        code = getattr(function.__call__, "__code__", None)
    return set() if code is None else {(code.co_filename, code.co_name)}


def _stats(profiler, allocation_gate, event):
    callback_keys = {"gate": _code_key(allocation_gate), "event": _code_key(event)}
    rows, groups = [], {}
    for (filename, line, name), (primitive, total, self_time, cumulative, callers) in pstats.Stats(profiler).stats.items():
        category = _category(filename, name, callback_keys)
        groups[category] = groups.get(category, 0.0) + self_time
        rows.append({"file": filename, "line": line, "function": name, "category": category,
                     "primitive_calls": primitive, "total_calls": total,
                     "self_seconds": self_time, "cumulative_seconds": cumulative,
                     "nested_seconds": max(0.0, cumulative - self_time)})
    rows.sort(key=lambda r:r["self_seconds"], reverse=True)
    return {"function_rows": rows, "exclusive_category_seconds": groups,
            "top_self_functions": rows[:20],
            "top_cumulative_functions": sorted(rows, key=lambda r:r["cumulative_seconds"], reverse=True)[:20],
            "time_semantics": "self excludes callees; cumulative includes callees; nested=cumulative-self; cumulative/nested rows overlap and must not be summed",
            "exclusive_categories_sum_seconds": sum(groups.values())}


def _case(descriptors, snapshot, target_record, recipe, seeded, accumulator_class, load_array,
          allocation_gate, event, max_owned_bytes, tile_width, index_dtype, profiler):
    costs = {"CSR_replacement_events": 0, "sum_next_CSR_payload_bytes": 0,
             "sum_constructor_copy_allowance_bytes": 0}
    def observed_gate(label, facts):
        allocation_gate(label, facts)
        if "next_CSR_payload_bytes" in facts:
            costs["CSR_replacement_events"] += 1
            costs["sum_next_CSR_payload_bytes"] += facts["next_CSR_payload_bytes"]
            costs["sum_constructor_copy_allowance_bytes"] += facts["CSR_constructor_copy_allowance_bytes"]
    events = replay._Events(observed_gate, event, "new")
    read = replay._Read(descriptors, load_array, events)
    events.gate("single_recipe_profile_state", {"matrix_payload_bytes": 0, "workspace_bytes": 16 << 20,
                "profiler_enabled": profiler is not None, "profiler_storage_outside_named_array_budget": True,
                "Python_native_profiler_workspace_unknown_independent_watchdog_required": True})
    started = perf_counter()
    if profiler is not None:
        profiler.enable()
    try:
        load_started = perf_counter()
        qmap = read.csr(snapshot["qmaps"][0])
        rows, cols, values = replay._recipe(read, recipe, qmap.shape[0])
        target = replay._target(read, 0, 0, {0: target_record["shape"]}) if seeded else None
        load_seconds = perf_counter() - load_started
        accumulator = accumulator_class((qmap.shape[1], qmap.shape[1]), max_owned_bytes=max_owned_bytes,
            tile_width=tile_width, index_dtype=index_dtype, gate=events.accumulator_gate)
        seed_started = perf_counter()
        seed_fingerprint = replay.csr_fingerprint(target) if target is not None else None
        if seeded:
            replay._require(seed_fingerprint["CSR_sha256"] == target_record["CSR_sha256"]
                            and seed_fingerprint["nnz"] == target_record["nnz"], "saved q0 seed detached from measured full CSR")
            _seed(accumulator, target)
        seed_copy_seconds = perf_counter() - seed_started
        add_started = perf_counter()
        accumulator.add(qmap, qmap, rows, cols, values, recipe["label"])
        add_seconds = perf_counter() - add_started
        finish_started = perf_counter()
        matrix = accumulator.finish()
        fingerprint = replay.csr_fingerprint(matrix)
        finish_hash_seconds = perf_counter() - finish_started
        return {"label": recipe["label"], "twist": 0, "p": 0, "q": 0,
                "case": "synthetic_saved_q0_plus_one_recipe" if seeded else "single_saved_recipe_empty_CSR",
                "synthetic_seed": seeded, "seed": seed_fingerprint, "result": fingerprint,
                "wall_seconds": perf_counter() - started, "load_seconds": load_seconds,
                "seed_copy_and_seed_hash_seconds": seed_copy_seconds, "add_seconds": add_seconds,
                "finish_and_result_hash_seconds": finish_hash_seconds,
                "event_count": events.event_count, "log_bytes": events.log_bytes, "array_reads": events.read_count,
                "peak_projection_owned_upper_bytes": accumulator.peak_owned_upper_bytes,
                "tiles_projected": accumulator.tiles_projected,
                "tiles_skipped_structural": accumulator.tiles_skipped_structural,
                "support_discoveries": accumulator.support_discoveries,
                "profile_enabled": profiler is not None, "archived_arrays_readonly": True,
                "archive_write_calls": 0, "declared_replacement_costs": costs,
                "replacement_byte_sums_are_declared_traffic_not_measured_memory_writes": True}
    finally:
        if profiler is not None:
            profiler.disable()


def profile_saved_projection_cost(report, *, accumulator_class, load_array, allocation_gate,
                                event, source_metadata, labels=LABELS,
                                max_owned_bytes=128 << 20, tile_width=128,
                                index_dtype=np.int32, verify_if_wall_below_seconds=2.0):
    """At most four reset cases: first volume/q0-compatible direct C, empty/synthetic seed.

    Cheap verification repeats exactly one case, never preceding contributions.
    Caller enforces a <=60-second whole-process watchdog, including profiling,
    optional repeats, metadata conversion and output. cProfile itself slows
    Python loops; profiled times are diagnostics, not normal replay forecasts.
    """
    identity = replay._source_identity(accumulator_class, source_metadata)
    replay._require(0 < max_owned_bytes <= 128 << 20 and 0 <= verify_if_wall_below_seconds <= 2,
                    "profiler owned/verification bounds differ")
    snapshot, target, recipes = _select(report, labels)
    started = perf_counter()
    results = []
    for recipe in recipes:
        for seeded in (False, True):
            profiler = cProfile.Profile()
            measured = _case(report["artifacts"], snapshot, target, recipe, seeded, accumulator_class, load_array,
                allocation_gate, event, max_owned_bytes, tile_width, index_dtype, profiler)
            measured["profile"] = _stats(profiler, allocation_gate, event)
            measured["verification"] = {"status": "TIMING_DIAGNOSTIC_ONLY", "reason": "profiled case exceeds cheap-repeat threshold or remaining watchdog allowance"}
            if (measured["wall_seconds"] <= verify_if_wall_below_seconds
                    and perf_counter() - started + 2 * measured["wall_seconds"] + 5 < 60):
                unprofiled = _case(report["artifacts"], snapshot, target, recipe, seeded, accumulator_class, load_array,
                    allocation_gate, event, max_owned_bytes, tile_width, index_dtype, None)
                equal = measured["result"] == unprofiled["result"]
                measured["verification"] = {"status": "BITWISE_FINGERPRINT_PASS" if equal else "BITWISE_FINGERPRINT_FAILED",
                                            "bitwise_CSR_equal": equal, "unprofiled": unprofiled,
                                            "profiled_to_unprofiled_wall_ratio": measured["wall_seconds"] / unprofiled["wall_seconds"] if unprofiled["wall_seconds"] else None,
                                            "ratio_is_single_observation_not_calibrated_profiler_overhead": True}
            results.append(measured)
            summary = {k:measured[k] for k in ("label", "case", "wall_seconds", "add_seconds", "seed_copy_and_seed_hash_seconds")}
            summary["exclusive_category_seconds"] = measured["profile"]["exclusive_category_seconds"]
            summary["top_self_functions"] = measured["profile"]["top_self_functions"][:8]
            summary["verification_status"] = measured["verification"]["status"]
            replay._Events(allocation_gate, event, "new").emit("single_recipe_profile_case_complete", **summary)
    integrity_passed = not any(c["verification"]["status"] == "BITWISE_FINGERPRINT_FAILED" for c in results)
    return {"schema": SCHEMA, "status": "SINGLE_RECIPE_COST_DIAGNOSTICS_COMPLETE" if integrity_passed else "SINGLE_RECIPE_COST_INTEGRITY_FAILED",
            "integrity_passed": integrity_passed, "scope": replay.SCOPE,
            "source": identity, "source_metadata": source_metadata, "labels": list(labels), "cases": results,
            "selected_recipe_inventory_sha256": replay._sha(recipes), "wall_seconds": perf_counter() - started,
            "max_owned_bytes": max_owned_bytes, "tile_width": tile_width,
            "required_external_watchdog_seconds": 60, "required_external_tree_cap_bytes": 3 << 30,
            "profiler_overhead_included_in_wall_and_unquantified_without_repeat": True,
            "seeded_results_are_synthetic_cost_diagnostics_not_operator_qualification": True,
            "all8_replay_calls": 0, "old_baseline_calls": 0,
            "FE_calls": 0, "JIT_calls": 0, "new_factor_calls": 0, "PDE_calls": 0}
