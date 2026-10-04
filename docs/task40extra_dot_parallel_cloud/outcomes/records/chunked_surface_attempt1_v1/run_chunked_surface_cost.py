"""External selected-only chunked surface diagnostic, staged without execution.

The one degree-27 FFCx form is a mechanism witness, not target accuracy. The
original degree-160 rule runs only through the bounded native helper after the
full raw and masked vector witness passes. Frozen metadata/core/reference
bytes stay authoritative. Importing this file does not import any FE package.
"""
from __future__ import annotations

from collections.abc import Mapping
import hashlib
import importlib
import json
from pathlib import Path
import resource
import sys
import time

import numpy as np

SCHEMA = "task40extra.selected-chunked-surface-cost.v1"
CORE_SHA256 = "748e925d42b0da1e27240b10d47bf586173ced8ee44a93cd78ea4368a6dbae24"
REFERENCE_SHA256 = "cace8b9b472b9f8b7187f4cde1d028219041483a29cfc1981f9e6801c661737a"
MECHANISM_DEGREE = 27
PRIMARY_DEGREE = 160
VECTOR_RTOL = 1.0e-11
CHUNK_SIZE = 128


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _finite_array(value, *, shape=None, dtype=None, label="array"):
    value = np.asarray(value)
    _require((shape is None or value.shape == tuple(shape))
             and (dtype is None or value.dtype == np.dtype(dtype))
             and np.isfinite(value).all(), label + " shape/dtype/finite mismatch")
    return value


def vector_comparison(left, right, *, relative_limit=VECTOR_RTOL):
    """Full vector error bounded relative to BOTH norms; no denominator floor."""
    left, right = _finite_array(left), _finite_array(right)
    _require(left.ndim == 1 and left.shape == right.shape, "vector shape mismatch")
    _require(type(relative_limit) in (int, float) and np.isfinite(relative_limit)
             and relative_limit > 0, "invalid relative vector limit")
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            difference = np.abs(left - right)
            # Scale the norm computation itself, without altering its value or
            # introducing a tolerance floor for tiny representable vectors.
            def stable_norm(magnitudes):
                maximum = float(np.max(magnitudes, initial=0.0))
                return 0.0 if maximum == 0 else maximum*float(np.sqrt(np.sum((magnitudes/maximum)**2)))
            absolute = stable_norm(difference)
            left_scale, right_scale = stable_norm(np.abs(left)), stable_norm(np.abs(right))
            maximum = float(np.max(difference, initial=0.0))
            left_limit, right_limit = relative_limit*left_scale, relative_limit*right_scale
            left_relative = None if left_scale == 0 else absolute/left_scale
            right_relative = None if right_scale == 0 else absolute/right_scale
    except (FloatingPointError, OverflowError) as error:
        raise ValueError("vector difference or norms are unrepresentable") from error
    metrics = (absolute, left_scale, right_scale, maximum, left_limit, right_limit,
               *(v for v in (left_relative, right_relative) if v is not None))
    _require(all(np.isfinite(v) for v in metrics), "vector comparison produced nonfinite metric")
    left_pass = absolute == 0 if left_scale == 0 else absolute <= left_limit
    right_pass = absolute == 0 if right_scale == 0 else absolute <= right_limit
    return {"passed": bool(left_pass and right_pass), "left_scale_passed": bool(left_pass),
            "right_scale_passed": bool(right_pass), "absolute_error_l2": absolute,
            "maximum_absolute_error": maximum, "left_vector_norm": left_scale,
            "right_vector_norm": right_scale, "left_relative_error": left_relative,
            "right_relative_error": right_relative, "left_limit": left_limit,
            "right_limit": right_limit, "relative_limit": relative_limit,
            "exact_zero_rule": True, "no_denominator_floor": True,
            "scale_definition": "both corresponding complete native vector L2 norms"}


def materialize_mask(raw, rows, values):
    """Represent the actual supplied sparse entries in full native storage."""
    raw = _finite_array(raw, dtype=np.complex128, label="raw mask input")
    rows = np.asarray(rows)
    values = _finite_array(values, dtype=np.complex128, label="masked values")
    _require(raw.ndim == rows.ndim == values.ndim == 1 and rows.dtype.kind in "iu"
             and len(rows) == len(values) and np.all(rows >= 0) and np.all(rows < len(raw))
             and (len(rows) < 2 or np.all(rows[1:] > rows[:-1])), "invalid native masked rows")
    masked = np.zeros_like(raw)
    mask = np.zeros(len(raw), dtype=bool)
    masked[rows], mask[rows] = values, True
    return masked, mask


def unchanged_mask_comparison(raw, rows, values):
    """Each role must independently reproduce the original 1e-30/1e-13 mask."""
    masked, mask = materialize_mask(raw, rows, values)
    with np.errstate(over="raise", invalid="raise"):
        magnitudes = np.abs(raw)
        cutoff = max(1.0e-30, 1.0e-13*float(np.max(magnitudes, initial=0.0)))
    _require(np.isfinite(cutoff) and np.isfinite(magnitudes).all(), "nonfinite original mask cutoff")
    expected_rows = np.flatnonzero(magnitudes > cutoff)
    row_pass = np.array_equal(rows, expected_rows)
    values_pass = np.array_equal(values, raw[np.asarray(rows)])
    return {"passed": bool(row_pass and values_pass), "rows_match_own_raw": bool(row_pass),
            "values_equal_own_raw": bool(values_pass), "cutoff": cutoff,
            "absolute_cutoff": 1.0e-30, "relative_cutoff": 1.0e-13,
            "raw_nonzero_entries": int(np.count_nonzero(raw)), "masked_entries": len(rows)}, masked, mask


def _raw_signature(value):
    value = np.ascontiguousarray(value)
    return {"shape": list(value.shape), "dtype": str(value.dtype),
            "sha256": hashlib.sha256(memoryview(value).cast("B")).hexdigest()}


def _native_payload_signature(value):
    value = np.ascontiguousarray(value)
    digest = hashlib.sha256()
    digest.update(str(value.dtype).encode())
    digest.update(str(value.shape).encode())
    digest.update(memoryview(value).cast("B"))
    return {"shape": list(value.shape), "dtype": str(value.dtype), "sha256": digest.hexdigest()}


def _actual_native_signatures(V, mpc):
    """Bind actual caller-native maps to the helper's recorded identities."""
    n = int(V.dofmap.index_map.size_local)
    numbers = np.asarray(V.dofmap.index_map.local_to_global(np.arange(n, dtype=np.int32)))
    _require(np.array_equal(numbers, np.arange(n, dtype=np.int64)), "actual native global numbering is not serial")
    dofs = hashlib.sha256()
    for cell in range(int(V.mesh.topology.index_map(3).size_local)):
        dofs.update(memoryview(np.ascontiguousarray(V.dofmap.cell_dofs(cell))).cast("B"))
    coefficients, offsets = mpc.coefficients()
    return {"native_layout": {"element_signature": V.element.signature,
        "global_numbering_sha256": _native_payload_signature(numbers)["sha256"],
        "cell_dof_order_sha256": dofs.hexdigest()},
        "MPC": {name: _native_payload_signature(array) for name, array in
            (("slaves", mpc.slaves), ("masters", mpc.masters.array),
             ("coefficients", coefficients), ("offsets", offsets))},
        "cell_permutations": _native_payload_signature(V.mesh.topology.get_cell_permutation_info())}


def mechanism_rule_comparison(compiled_identity, rule_points, rule_weights):
    """Compare the actual chunked rule to the verified small compiled rule."""
    points = _finite_array(rule_points, shape=(196, 2), dtype=np.float64, label="mechanism rule points")
    weights = _finite_array(rule_weights, shape=(196,), dtype=np.float64, label="mechanism rule weights")
    rules = compiled_identity.get("rules", ())
    _require(bool(rules), "missing mechanism compiled Gauss rules")
    signatures = {"points": _raw_signature(points), "weights": _raw_signature(weights)}
    matched = []
    for rule in rules:
        _require(rule.get("degree") == MECHANISM_DEGREE, "compiled rule role/degree mismatch")
        matched.append(all(dict(rule[name]) == signatures[name] for name in signatures))
    return {"passed": bool(all(matched)), "actual_nodes_per_facet": 196,
            "quadrature_degree": MECHANISM_DEGREE, "compiled_rules_matched": matched,
            "rule_signatures_raw_bytes": signatures, "role": "mechanism_only_not_target_accuracy"}


def _failure_jsonable(value):
    """Failure-only markers keep strict JSON writable without replacing data."""
    if isinstance(value, Mapping):
        return {str(k): _failure_jsonable(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_failure_jsonable(v) for v in value]
    if isinstance(value, np.ndarray):
        return _failure_jsonable(value.tolist())
    if isinstance(value, np.generic):
        return _failure_jsonable(value.item())
    if isinstance(value, complex):
        return {"real": _failure_jsonable(value.real), "imag": _failure_jsonable(value.imag)}
    if isinstance(value, float) and not np.isfinite(value):
        return {"failure_only_nonfinite_marker": repr(value), "numeric_substitution_permitted": False}
    return value


def _current_rss():
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1])*1024
    raise ValueError("current self RSS unavailable")


def _load_core(repo_root):
    root = Path(repo_root).resolve()
    sys.path.insert(0, str(root)) if str(root) not in sys.path else None
    core = importlib.import_module("src.solvers.target_auto_surface_cost")
    _require(Path(core.__file__).resolve() == root/"src/solvers/target_auto_surface_cost.py"
             and core.file_sha256(core.__file__) == CORE_SHA256, "frozen CORE source/path changed")
    return core


def _function_identity(function, core, *, expected_sha256=None):
    _require(callable(function) and hasattr(function, "__code__"), "explicit source-backed helper required")
    path = Path(function.__code__.co_filename).resolve()
    digest = core.file_sha256(path)
    _require(expected_sha256 is None or digest == expected_sha256, "pinned helper source changed")
    return {"path": str(path), "sha256": digest, "function": function.__name__}


def _save_arrays(core, root, prefix, arrays):
    """Persist unmodified actual arrays before shape, finite, or math gates."""
    artifacts = {}
    stem = prefix + "_" if prefix else ""
    for key, value in arrays.items():
        if isinstance(value, (tuple, list)):
            artifacts[key] = [core._save_array(root, f"{stem}{key}_{j}", np.asarray(a))
                              for j, a in enumerate(value)]
        else:
            artifacts[key] = core._save_array(root, f"{stem}{key}", np.asarray(value))
    return artifacts


def _destroy_owned_vector_after_copy(make_vector):
    """The public assembly APIs transfer one Vec to this caller."""
    vec = None
    try:
        vec = make_vector()
        raw = np.asarray(vec.getArray(readonly=True)).copy()
        ownership = tuple(vec.getOwnershipRange())
        return raw, ownership
    finally:
        if vec is not None:
            vec.destroy()


def _collect_ffcx(*, core, assembler, mpc, bundle, selected, n, g, width, root,
                  allocation_gate, event, record, checkpoint):
    components, raw_arrays = [], []
    for index in selected:
        mode = bundle.modes[index]
        allocation = core._admit("mechanism_FFCx_selected_component", {
            **core.component_allocation_facts(n, g, int(882), width),
            "retained_six_component_witness_arrays": len(selected)*n*96},
            allocation_gate=allocation_gate, event=event, original_mode_index=int(index),
            quadrature_degree=MECHANISM_DEGREE, role="mechanism_only", current_RSS_bytes=_current_rss())
        started = time.perf_counter()
        b_FE, fe_owned = _destroy_owned_vector_after_copy(lambda: assembler.assemble_unconstrained_vector(mode))
        artifacts = _save_arrays(core, root, f"mechanism_ffcx_mode_{index}", {"b_FE": b_FE})
        item = {"original_mode_index": int(index), "original_mode_key": core.mode_key(index, mode),
                "physical_row": core.jsonable(bundle.rows[index]), "role": "mechanism_only",
                "actual_near_cutoff": bool(mode.rayleigh_warning), "actual_abs_beta": float(abs(mode.beta)),
                "quadrature_degree": MECHANISM_DEGREE, "allocation": allocation,
                "FE_ownership": fe_owned, "artifacts": artifacts}
        components.append(item)
        record["mechanism_ffcx_components"] = components
        checkpoint()
        raw_MPC, mpc_owned = _destroy_owned_vector_after_copy(lambda: assembler.assemble_raw_mpc_vector(mode, mpc))
        artifacts.update(_save_arrays(core, root, f"mechanism_ffcx_mode_{index}", {"raw_MPC": raw_MPC}))
        item["MPC_ownership"] = mpc_owned
        checkpoint()
        rows, values = assembler.assemble_entries(mode, mpc)
        artifacts.update(_save_arrays(core, root, f"mechanism_ffcx_mode_{index}",
                                      {"masked_rows": rows, "masked_values": values}))
        item["wall_seconds"] = time.perf_counter()-started
        raw_arrays.append({"b_FE": b_FE, "raw_MPC": raw_MPC, "masked_rows": rows, "masked_values": values})
        checkpoint()
        event({"schema": SCHEMA, "stage": "mechanism_FFCx_actual_arrays_saved", "component": core.jsonable(item)})
    return raw_arrays


def _validate_chunked_result(result, *, selected, n, degree, source, core, native_signatures=None):
    facts, arrays = result["record"], result["arrays"]
    _require(facts.get("quadrature_degree") == degree and facts.get("native_rows") == n
             and facts.get("selected_original_mode_indices") == list(selected)
             and facts.get("default_gauss_points_weights_byte_equal") is True,
             "chunked degree/native/selected/rule identity mismatch")
    _require(facts.get("source", {}).get("path") == source["path"]
             and facts.get("source", {}).get("sha256") == source["sha256"], "chunked source identity changed")
    _require(facts.get("owned_buffer_limit_bytes") == 128 << 20
             and facts.get("mesh_space_form_JIT_factor_PDE_creation_calls") == 0,
             "chunked resource or constructor scope differs")
    for key in ("b_FE", "raw_MPC"):
        _finite_array(arrays[key], shape=(len(selected), n), dtype=np.complex128, label=key)
    _finite_array(arrays["masked_full"], shape=(len(selected), n), dtype=np.complex128, label="helper masked full")
    _finite_array(arrays["masks"], shape=(len(selected), n), dtype=bool, label="helper masks")
    _require(len(arrays["masked_rows"]) == len(arrays["masked_values"]) == len(selected),
             "chunked sparse selected count mismatch")
    nodes = ((degree+2)//2)**2
    _finite_array(arrays["rule_points"], shape=(nodes, 2), dtype=np.float64, label="chunked rule points")
    _finite_array(arrays["rule_weights"], shape=(nodes,), dtype=np.float64, label="chunked rule weights")
    _require(facts.get("actual_nodes_per_facet") == nodes, "chunked actual quadrature node count differs")
    # Hashes bind the same literal geometry/native map for both helper roles.
    for key in ("native_layout", "MPC", "cell_permutations", "facets"):
        _require(key in facts, "missing chunked native/MPC/geometry identity: " + key)
    if native_signatures is not None:
        for key, wanted in native_signatures.items():
            _require(core.canonical(facts[key]) == core.canonical(wanted),
                     "chunked recorded identity differs from actual caller native maps: " + key)
    return arrays


def _mask_arrays(arrays, *, selected, n):
    masked = np.empty((len(selected), n), dtype=np.complex128)
    mask = np.empty((len(selected), n), dtype=bool)
    metrics = []
    for j in range(len(selected)):
        metric, masked[j], mask[j] = unchanged_mask_comparison(
            arrays["raw_MPC"][j], arrays["masked_rows"][j], arrays["masked_values"][j])
        metric["recorded_full_matches_own_sparse"] = bool(np.array_equal(arrays["masked_full"][j], masked[j]))
        metric["recorded_mask_matches_own_sparse"] = bool(np.array_equal(arrays["masks"][j], mask[j]))
        metric["passed"] = bool(metric["passed"] and metric["recorded_full_matches_own_sparse"]
                                and metric["recorded_mask_matches_own_sparse"])
        metrics.append({"original_mode_index": int(selected[j]), **metric})
    return metrics, masked, mask


def _payload_bytes(value):
    if isinstance(value, Mapping):
        if "path" in value and "bytes" in value and "sha256" in value:
            return int(value["bytes"])
        return sum(_payload_bytes(v) for v in value.values())
    if isinstance(value, (tuple, list)):
        return sum(_payload_bytes(v) for v in value)
    return 0


def _array_payload_nbytes(value):
    """Sum actual named retained ndarray payload, including sparse tuples."""
    if isinstance(value, np.ndarray):
        return int(value.nbytes)
    if isinstance(value, Mapping):
        return sum(_array_payload_nbytes(v) for v in value.values())
    if isinstance(value, (tuple, list)):
        return sum(_array_payload_nbytes(v) for v in value)
    return 0


def _admit_result_persistence(core, arrays, *, allocation_gate, event, role):
    payload = _array_payload_nbytes(arrays)
    return core._admit(role + "_actual_array_persistence", {
        "actual_helper_result_retained_payload": payload,
        "numpy_file_IO_workspace_conservative": 2*payload + (4 << 20)},
        allocation_gate=allocation_gate, event=event, current_RSS_bytes=_current_rss(),
        actual_retained_payload_bytes=payload, complete_unmodified_arrays_saved_before_math_gates=True)


def _admit_mask_comparison(core, *, n, selected_count, allocation_gate, event, role):
    return core._admit(role + "_full_masks_and_vector_comparison", {
        "full_mask_and_masked_retained_arrays": selected_count*n*(16+1),
        "one_component_full_masks_magnitudes_and_norm_workspace": n*(16*6+8*8+4*4),
        "row_difference_and_file_output_workspace": n*4*4 + (4 << 20)},
        allocation_gate=allocation_gate, event=event, current_RSS_bytes=_current_rss(),
        actual_native_rows=n, actual_selected_modes=selected_count)


def run_chunked_surface_stage(*, repo_root, metadata_dir, metadata_seal, output_dir, cache_dir,
                             allocation_gate, event, chunked_helper, reference_helper):
    """Run only under the parent's reviewed, active whole-process 3 GiB gate."""
    core = _load_core(repo_root)
    stage, root = "metadata_seal", None
    started_total = time.perf_counter()
    record = {"schema": SCHEMA, "status": "PARTIAL_NOT_RUN",
              "scope": "original AUTO inventory; selected top/x raw and masked vectors only",
              "carrier_constructed": False, "dense_H_constructed": False,
              "volume_form_calls": 0, "factor_calls": 0, "PDE_calls": 0,
              "qualified_full_C_D_or_allmode_or_outputs": False,
              "whole_process_3gib_watchdog_required": True,
              "roles": {"mechanism": {"degree": 27, "FFCx_form_count": 1, "nodes_per_facet": 196,
                                       "target_accuracy_qualification": False},
                        "primary": {"degree": 160, "FFCx_form_count": 0, "native_chunked": True},
                        "reference": {"degrees": [168, 176], "public_Function_eval": True}},
              "FFCx_basis_table_clamping_caveat": "unthresholded native basis may fail the full-vector witness; no compiler clamp emulation",
              "mechanism_ffcx_components": [], "mechanism_comparisons": []}
    def checkpoint():
        if root is not None:
            core._write_bytes(root/"partial_surface_record.json", core.canonical(record))
    def terminal(status):
        record.update({"status": status, "scope_is_partial": True,
                       "actual_total_wall_seconds": time.perf_counter()-started_total,
                       "actual_artifact_payload_bytes": _payload_bytes(record),
                       "current_self_RSS_bytes": _current_rss(),
                       "self_historical_RSS_high_water_bytes": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)*1024,
                       "self_RSS_is_not_simultaneous_process_tree_peak": True})
        checkpoint()
        artifact = core._write_bytes(root/"surface_record.json", core.canonical(record))
        event({"schema": SCHEMA, "stage": "surface_terminal_saved", "status": status, "artifact": artifact})
        return {"record": core.jsonable(record), "surface_record": artifact}
    try:
        packet = core.validate_metadata_seal(metadata_dir=metadata_dir, seal=metadata_seal)
        identities = {"runner": {"path": str(Path(__file__).resolve()), "sha256": core.file_sha256(__file__)},
                      "core": {"path": str(Path(core.__file__).resolve()), "sha256": CORE_SHA256},
                      "chunked_helper": _function_identity(chunked_helper, core),
                      "reference_helper": _function_identity(reference_helper, core, expected_sha256=REFERENCE_SHA256)}
        core._admit("chunked_surface_journal_and_helper_identity", {"journal_source_hash_workspace": 4 << 20},
                    allocation_gate=allocation_gate, event=event)
        root = Path(output_dir).resolve()
        root.mkdir(parents=True, exist_ok=False)
        record.update({"metadata_seal": dict(metadata_seal), "actual_source_identities": identities})
        record.update({"actual_chunked_source_path": identities["chunked_helper"]["path"],
                       "actual_chunked_source_sha256": identities["chunked_helper"]["sha256"],
                       "actual_runner_source_path": identities["runner"]["path"],
                       "actual_runner_source_sha256": identities["runner"]["sha256"]})
        checkpoint()
        event({"schema": SCHEMA, "stage": "metadata_Library_seal_verified", "seal": dict(metadata_seal)})
        stage = "fresh_inventory_binding"
        bundle = core._fresh_inventory(repo_root=repo_root, allocation_gate=allocation_gate, event=event)
        _require(bundle.physical_manifest_sha256 == packet["original_physical_manifest_sha256"]
                 and bundle.ordered_keys_sha256 == packet["ordered_keys_sha256"]
                 and bundle.config_sha256 == packet["config_sha256"]
                 and core.canonical(bundle.cfg.as_jsonable()) == core.canonical(packet["cfg_as_jsonable"])
                 and bundle.manifest_bytes == (Path(metadata_dir)/"original_physical_manifest.json").read_bytes()
                 and bundle.ordered_keys_bytes == (Path(metadata_dir)/"original_ordered_keys.json").read_bytes()
                 and bundle.sources == packet["sources"]
                 and bundle.quadrature_degree == packet["quadrature_degree_from_complete_inventory"],
                 "fresh complete original target inventory differs from sealed metadata")
        selected, reasons = core.select_top_modes(bundle.modes)
        _require(list(selected) == packet["selected_original_mode_indices"]
                 and len(selected) == 6 and bundle.quadrature_degree == PRIMARY_DEGREE,
                 "sealed six selected modes or original degree160 differs")
        modes = tuple(bundle.modes[i] for i in selected)
        record.update({"physical_manifest_sha256": bundle.physical_manifest_sha256,
                       "ordered_keys_sha256": bundle.ordered_keys_sha256, "config_sha256": bundle.config_sha256,
                       "cfg_as_jsonable": bundle.cfg.as_jsonable(), "sources": bundle.sources,
                       "selected_original_mode_indices": selected, "selection_reasons": reasons,
                       "actual_reference_source_path": identities["reference_helper"]["path"],
                       "actual_reference_source_sha256": REFERENCE_SHA256, **bundle.summary})
        checkpoint()
        stage = "fixture"
        V, mesh_data, floquet = core._bare_fixture(bundle.cfg, allocation_gate=allocation_gate, event=event)
        mpc = floquet.mpc
        n, g = int(V.dofmap.index_map.size_local), int(V.dofmap.index_map.num_ghosts)
        _require(n > 0 and g == 0 and int(V.dofmap.index_map_bs) == 1
                 and int(V.dofmap.index_map.size_global) == n, "actual native fixture ownership differs")
        _, offsets = mpc.coefficients()
        width = max(1, int(np.max(np.diff(np.asarray(offsets)), initial=0)))
        record.update({"fixture_complete": True, "actual_native_storage_rows": n,
                       "actual_ghost_rows": g, "actual_MPC_max_expansion_width": width})
        checkpoint()
        cache = Path(cache_dir).resolve()
        cache.mkdir(parents=True, exist_ok=False)
        _require(not any(cache.iterdir()), "mechanism JIT cache must be fresh and empty")
        stage = "mechanism_compile"
        core._admit("single_small_mechanism_top_x_form_compile", {
            "bounded_small_FFCx_compiler_workspace": 384 << 20,
            "Gauss_loaded_kernel_Constant_pack_and_native_identity_workspace": 128 << 20},
            allocation_gate=allocation_gate, event=event, quadrature_degree=MECHANISM_DEGREE,
            nodes_per_facet=196, current_RSS_bytes=_current_rss(), cache_dir=str(cache),
            compiler_options=["-O2"], mechanism_form_count=1, target_FFCx_form_count=0,
            role="mechanism_only_not_target_accuracy")
        from src.solvers.dtn_port_3d import _ReusableSurfaceComponentAssembler
        from src.solvers.dtn_boundary_phase_gauge import build_gauge_assembly_context
        compile_started = time.perf_counter()
        assembler = _ReusableSurfaceComponentAssembler(
            V, mesh_data, bundle.cfg.tags.z_max, 0, quadrature_degree=MECHANISM_DEGREE,
            jit_options={"cache_dir": str(cache), "cffi_extra_compile_args": ["-O2"]},
            boundary_reference_z=130.0, verify_compiled_gauss=True)
        record["mechanism_compile_wall_seconds"] = time.perf_counter()-compile_started
        compiled = core.jsonable(assembler.compiled_gauss_identity)
        record["mechanism_compiled_gauss_loaded_binary_Constant_pack"] = compiled
        checkpoint()
        stage = "mechanism_compiled_file_persistence"
        kernel = compiled["loaded_kernel"]
        c_path, binary_path = Path(kernel["module_bound_C_path"]), Path(kernel["module_path"])
        core._admit("mechanism_generated_C_and_loaded_binary_output", {"streamed_copy_workspace": 2 << 20},
                    allocation_gate=allocation_gate, event=event,
                    output_bytes=c_path.stat().st_size+binary_path.stat().st_size)
        compiled_root = root/"compiled_mechanism"
        compiled_root.mkdir()
        record["mechanism_compiled_artifacts"] = {
            "generated_C": core._copy_pinned_file(c_path, compiled_root/c_path.name, kernel["module_bound_C_sha256"]),
            "loaded_binary": core._copy_pinned_file(binary_path, compiled_root/binary_path.name, kernel["binary_sha256"])}
        checkpoint()
        stage = "native_identity"
        core._admit("exact_native_mesh_element_MPC_identity", {"native_identity_workspace": 128 << 20},
                    allocation_gate=allocation_gate, event=event, native_storage_rows=n, mpc_max_expansion_width=width)
        record["native_discrete_identity"] = core.jsonable(build_gauge_assembly_context(
            V, mesh_data, mpc, bundle.cfg, MECHANISM_DEGREE, {("top", 0): assembler}))
        native_signatures = _actual_native_signatures(V, mpc)
        record["actual_native_helper_binding"] = native_signatures
        checkpoint()
        stage = "mechanism_FFCx_fullraw"
        ffcx = _collect_ffcx(core=core, assembler=assembler, mpc=mpc, bundle=bundle, selected=selected,
                             n=n, g=g, width=width, root=root, allocation_gate=allocation_gate,
                             event=event, record=record, checkpoint=checkpoint)
        stage = "mechanism_chunked_fullraw"
        mechanism_root = root/"mechanism_chunked"
        mechanism_root.mkdir()
        mechanism = chunked_helper(V=V, mesh_data=mesh_data, mpc=mpc, cfg=bundle.cfg,
                                   selected_modes=modes, selected_indices=selected,
                                   quadrature_degree=MECHANISM_DEGREE, allocation_gate=allocation_gate,
                                   event=event, output_dir=mechanism_root, chunk_size=CHUNK_SIZE)
        record["mechanism_chunked_record"] = core.jsonable(mechanism["record"])
        _admit_result_persistence(core, mechanism["arrays"], allocation_gate=allocation_gate, event=event, role="mechanism")
        record["mechanism_chunked_artifacts"] = _save_arrays(core, root, "mechanism_chunked", mechanism["arrays"])
        checkpoint()
        stage = "mechanism_gate"
        ma = _validate_chunked_result(mechanism, selected=selected, n=n, degree=MECHANISM_DEGREE,
                                      source=identities["chunked_helper"], core=core, native_signatures=native_signatures)
        _admit_mask_comparison(core, n=n, selected_count=len(selected), allocation_gate=allocation_gate,
                               event=event, role="mechanism")
        mask_metrics, m_masked, m_mask = _mask_arrays(ma, selected=selected, n=n)
        record["mechanism_chunked_artifacts"].update(_save_arrays(
            core, root, "mechanism_chunked", {"recomputed_masked_full": m_masked, "mask": m_mask}))
        record["mechanism_rule_comparison"] = mechanism_rule_comparison(compiled, ma["rule_points"], ma["rule_weights"])
        comparisons = []
        for j, index in enumerate(selected):
            actual = ffcx[j]
            for name in ("b_FE", "raw_MPC"):
                _finite_array(actual[name], shape=(n,), dtype=np.complex128, label="FFCx " + name)
            witness = record["mechanism_ffcx_components"][j]
            _require(tuple(witness["FE_ownership"]) == tuple(witness["MPC_ownership"]) == (0, n),
                     "FFCx Vec actual ownership differs")
            own_mask, f_masked, f_mask = unchanged_mask_comparison(actual["raw_MPC"], actual["masked_rows"], actual["masked_values"])
            witness["artifacts"].update(_save_arrays(core, root, f"mechanism_ffcx_mode_{index}",
                                                     {"masked_full": f_masked, "mask": f_mask}))
            row_difference = {"only_FFCx_rows": np.flatnonzero(f_mask & ~m_mask[j]).astype(np.int32),
                              "only_chunked_rows": np.flatnonzero(m_mask[j] & ~f_mask).astype(np.int32)}
            item = {"original_mode_index": int(index), "FFCx_own_mask": own_mask,
                    "chunked_own_mask": mask_metrics[j],
                    "b_FE_fullraw": vector_comparison(actual["b_FE"], ma["b_FE"][j]),
                    "raw_MPC_fullraw": vector_comparison(actual["raw_MPC"], ma["raw_MPC"][j]),
                    "masked_fullvector": vector_comparison(f_masked, m_masked[j]),
                    "row_difference_counts": {name: len(value) for name, value in row_difference.items()},
                    "row_difference_artifacts": _save_arrays(core, root, f"mechanism_mode_{index}", row_difference)}
            item["passed"] = all(item[key]["passed"] for key in
                                 ("FFCx_own_mask", "chunked_own_mask", "b_FE_fullraw", "raw_MPC_fullraw", "masked_fullvector"))
            comparisons.append(item)
            record["mechanism_comparisons"] = comparisons
            checkpoint()
        mechanism_pass = record["mechanism_rule_comparison"]["passed"] and all(c["passed"] for c in comparisons)
        record["mechanism_gate_passed"] = bool(mechanism_pass)
        record["mechanism_passed"] = bool(mechanism_pass)
        record["retained_array_payload_peak_bytes"] = int(_array_payload_nbytes(ffcx)
            + _array_payload_nbytes(ma) + m_masked.nbytes + m_mask.nbytes + f_masked.nbytes + f_mask.nbytes
            + _array_payload_nbytes(row_difference))
        record["retained_array_payload_peak_definition"] = "maximum observed stage snapshot of actual named retained ndarray payload; native transient workspace excluded"
        checkpoint()
        event({"schema": SCHEMA, "stage": "mechanism_fullvector_gate_complete", "passed": bool(mechanism_pass)})
        if not mechanism_pass:
            return terminal("CHUNKED_MECHANISM_GATE_FAILED")
        # Release every small witness vector before the primary assembly.
        del ffcx, mechanism, ma, m_masked, m_mask, f_masked, f_mask, actual, row_difference
        stage = "target_chunked_primary"
        target_root = root/"target_chunked"
        target_root.mkdir()
        primary_started = time.perf_counter()
        primary = chunked_helper(V=V, mesh_data=mesh_data, mpc=mpc, cfg=bundle.cfg,
                                 selected_modes=modes, selected_indices=selected,
                                 quadrature_degree=bundle.quadrature_degree, allocation_gate=allocation_gate,
                                 event=event, output_dir=target_root, chunk_size=CHUNK_SIZE)
        record["target_chunked_wall_seconds"] = time.perf_counter()-primary_started
        record["target_chunked_record"] = core.jsonable(primary["record"])
        _admit_result_persistence(core, primary["arrays"], allocation_gate=allocation_gate, event=event, role="primary")
        record["target_chunked_artifacts"] = _save_arrays(core, root, "target_chunked", primary["arrays"])
        checkpoint()
        pa = _validate_chunked_result(primary, selected=selected, n=n, degree=bundle.quadrature_degree,
                                      source=identities["chunked_helper"], core=core, native_signatures=native_signatures)
        for key in ("native_layout", "MPC", "cell_permutations", "facets"):
            _require(core.canonical(record["mechanism_chunked_record"][key]) == core.canonical(primary["record"][key]),
                     "target versus mechanism native/MPC/geometry identity changed: " + key)
        _admit_mask_comparison(core, n=n, selected_count=len(selected), allocation_gate=allocation_gate,
                               event=event, role="primary")
        target_masks, masked, mask = _mask_arrays(pa, selected=selected, n=n)
        record["target_own_mask_comparisons"] = target_masks
        record["target_chunked_artifacts"].update(_save_arrays(core, root, "target_chunked", {"recomputed_masked_full": masked, "mask": mask}))
        checkpoint()
        _require(all(m["passed"] for m in target_masks), "target helper mask differs from its own raw unchanged cutoff")
        stage = "native_states"
        states, fields = core._native_states(V, mpc, allocation_gate=allocation_gate, event=event)
        record["state_identity"] = {"seed": 61811, "labels": ["complex_random", "row_trigonometric", "row_modular"],
                                    "independent_slaves_zero": True, "native_fields_backsubstituted": True}
        record["state_artifacts"] = _save_arrays(core, root, "native", {
            "independent_states": states, "expanded_fields": tuple(np.asarray(f.x.array) for f in fields)})
        checkpoint()
        core._admit("selected_three_state_contraction_outputs", {
            "contractions_and_scale_retained_arrays": len(selected)*3*16*8,
            "native_sized_vdot_abs_and_product_workspace": n*(16*4+8*4)},
            allocation_gate=allocation_gate, event=event, current_RSS_bytes=_current_rss(), actual_native_rows=n)
        raw_contractions = np.empty((len(selected), 3), dtype=np.complex128)
        masked_contractions = np.empty_like(raw_contractions)
        scales = np.empty((len(selected), 3), dtype=np.float64)
        # Compute actual diagnostic values, including unrepresentable results,
        # then preserve the arrays before the finite gate rejects them.
        with np.errstate(over="ignore", invalid="ignore"):
            for j in range(len(selected)):
                for k in range(3):
                    raw_contractions[j, k] = np.vdot(states[:, k], pa["raw_MPC"][j])
                    masked_contractions[j, k] = np.vdot(states[:, k], masked[j])
                    scales[j, k] = np.sum(np.abs(states[:, k])*np.abs(pa["raw_MPC"][j]))
            cutoff_loss = raw_contractions-masked_contractions
        contractions = {"primary_raw_contractions": raw_contractions,
                        "primary_masked_contractions": masked_contractions,
                        "primary_operation_scales": scales,
                        "primary_cutoff_contraction_loss": cutoff_loss}
        record["contraction_artifacts"] = _save_arrays(core, root, "", contractions)
        retained_now = int(_array_payload_nbytes(pa) + masked.nbytes + mask.nbytes + states.nbytes
            + sum(f.x.array.nbytes for f in fields) + _array_payload_nbytes(contractions))
        record["retained_array_payload_peak_bytes"] = max(record["retained_array_payload_peak_bytes"], retained_now)
        checkpoint()
        for name, array in contractions.items():
            _finite_array(array, shape=(len(selected), 3), label=name)
        record["selected_components"] = [{"original_mode_index": int(index),
            "original_mode_key": core.mode_key(index, modes[j]), "physical_row": core.jsonable(bundle.rows[index]),
            "actual_near_cutoff": bool(modes[j].rayleigh_warning), "actual_abs_beta": float(abs(modes[j].beta)),
            "raw_contractions": raw_contractions[j], "masked_contractions": masked_contractions[j],
            "cutoff_contraction_loss": contractions["primary_cutoff_contraction_loss"][j],
            "primary_operation_scales": scales[j], "own_mask": target_masks[j]} for j, index in enumerate(selected)]
        checkpoint()
        stage = "independent_reference"
        reference = reference_helper(V=V, mesh_data=mesh_data, mpc=mpc, cfg=bundle.cfg,
                                     selected_modes=modes, selected_indices=selected,
                                     native_fields=fields, independent_states=states,
                                     quadrature_degree=bundle.quadrature_degree,
                                     allocation_gate=allocation_gate, event=event, output_dir=root)
        record["independent_reference"] = core.jsonable(reference["record"])
        _admit_result_persistence(core, reference["arrays"], allocation_gate=allocation_gate, event=event, role="reference")
        record["contraction_artifacts"].update(_save_arrays(core, root, "", reference["arrays"]))
        record["retained_array_payload_peak_bytes"] = max(record["retained_array_payload_peak_bytes"],
                                                         retained_now + _array_payload_nbytes(reference["arrays"]))
        checkpoint()
        ref = _finite_array(reference["arrays"]["contractions_degree_plus16"], shape=raw_contractions.shape,
                            dtype=np.complex128, label="public eval reference")
        integral_scales = _finite_array(reference["arrays"]["operation_scales_degree_plus16"], shape=ref.shape,
                                        dtype=np.float64, label="independent integral operation scales")
        _require(np.all(integral_scales >= 0), "negative independent integral scale")
        facts = reference["record"]
        _require(facts.get("primary_degree") == 160 and facts.get("reference_increments") == [8, 16]
                 and facts.get("selected_indices") == list(selected)
                 and [r["degree"] for r in facts.get("rules", ())] == [168, 176], "independent reference role identity differs")
        record["raw_vs_public_eval_reference"] = core.reference_action_gate(raw_contractions, ref, integral_scales)
        plus8 = _finite_array(reference["arrays"]["contractions_degree_plus8"], shape=ref.shape, dtype=np.complex128,
                              label="degree168 public eval reference")
        plus8_scales = _finite_array(reference["arrays"]["operation_scales_degree_plus8"], shape=ref.shape,
                                     dtype=np.float64, label="degree168 integral operation scales")
        _require(np.all(plus8_scales >= 0), "negative degree168 independent integral scale")
        convergence = core.reference_action_gate(plus8, ref, integral_scales)
        record["reference_convergence_recomputed"] = convergence
        passed = (record["raw_vs_public_eval_reference"]["passed"] and convergence["passed"]
                  and facts.get("reference_convergence_pass") is True)
        return terminal("CHUNKED_SELECTED_TOP_X_COMPLETE" if passed else "CHUNKED_SELECTED_TOP_X_REFERENCE_FAILED")
    except BaseException as error:
        record.update({"status": "PARTIAL_FAILED_OR_CONTROLLED_STOP", "stopped_stage": stage,
                       "error_type": type(error).__name__, "error": str(error),
                       "actual_total_wall_seconds": time.perf_counter()-started_total})
        failed = _failure_jsonable(record)
        if root is not None:
            core._write_bytes(root/"partial_surface_record.json", core.canonical(failed))
        event({"schema": SCHEMA, "stage": "surface_partial_or_failed", **failed})
        raise
