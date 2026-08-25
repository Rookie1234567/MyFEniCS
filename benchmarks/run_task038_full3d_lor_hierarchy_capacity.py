"""S5 p6/h10 hierarchy-capacity worker (the external watchdog is separate)."""
from __future__ import annotations
import argparse, gc, hashlib, json, os
from pathlib import Path
import sys, time
from typing import Any, Mapping
BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"
SCHEMA = "task038.full3d.lor-hierarchy-capacity.s5.v1"
MODULE = "benchmarks.run_task038_full3d_lor_hierarchy_capacity"
STAGE = "s5"
CASE = "p6-h10-mpi1"
DEGREE = 6
H_NM = 10.0
WAVELENGTH_NM = 13.5
LEVELS = (6, 3, 1)
PAIRS = ((6, 3), (3, 1))
MARKERS = (
    "paths_ready",
    "source_runtime_closed",
    "foundation_built",
    "reserve_built",
    "hierarchy_built_first",
    "probes_complete",
    "hierarchy_destroyed",
    "hierarchy_rebuilt",
    "retained_ready",
    "record_written",
)
RETAINED_DWELL_SECONDS = 2.0
CHEBYSHEV_DEGREE = 3
POWER_STEPS = 10
PRE_SWEEPS = 1
POST_SWEEPS = 1
RESERVE_BASIS = 21
RESERVE_AUXILIARY = 4
RESERVE_COUNT = RESERVE_BASIS + RESERVE_AUXILIARY
ALPHA = 0.37 + 0.19j
BETA = -0.23 + 0.41j
COARSE_PRIMAL_SOURCE = "owner_roundtrip_reduced_primal"
def _marker(marker_root: Path, name: str, source_sha: str, comm: Any, **facts: Any) -> int:
    if name not in MARKERS:
        raise ValueError(f"unknown S5 marker: {name}")
    wall_time_ns = comm.bcast(time.time_ns() if comm.rank == 0 else None, root=0)
    if comm.rank == 0:
        path = marker_root / "markers" / f"{name}.json"
        _write_json(path, {
            "schema": "task038.full3d.lor-hierarchy-capacity.marker.v1",
            "marker": name,
            "source_sha": source_sha,
            "wall_time_ns": int(wall_time_ns),
            "facts": facts,
        })
        with path.open("rb") as stream:
            os.fsync(stream.fileno())
    comm.barrier()
    return int(wall_time_ns)
def _vector_values(vector: Any):
    import numpy as np
    return np.asarray(vector.getArray(readonly=True), dtype=np.complex128).copy()
def _fill_deterministic(vector: Any, offset: float = 0.0) -> None:
    import numpy as np
    start, stop = vector.getOwnershipRange()
    indices = np.arange(start, stop, dtype=np.float64) + 1.0 + offset
    vector.array[:] = indices + 1j * (0.25 * indices + 0.5 * offset)
    vector.assemble()
def _relative(left, right) -> float:
    import numpy as np
    return float(np.linalg.norm(left - right) / max(float(np.linalg.norm(right)), 1.0e-300))
def _semantic_bytes(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
def _semantic_sha256(payload: Any) -> str:
    return hashlib.sha256(_semantic_bytes(payload)).hexdigest()
def _semantic_tree(value: Any) -> dict[str, Any]:
    import numpy as np
    if isinstance(value, Mapping):
        entries = []
        seen: set[str] = set()
        for key in sorted(value, key=str):
            text = str(key)
            if text in seen:
                raise ValueError("semantic mapping has duplicate string keys")
            seen.add(text)
            entries.append({"key": text, "child": _semantic_tree(value[key])})
        payload = {"kind": "mapping", "entries": entries}
    elif isinstance(value, (tuple, list)):
        payload = {"kind": "sequence", "children": [_semantic_tree(item) for item in value]}
    elif isinstance(value, (str, bool, int, float)) or value is None:
        payload = {"kind": "scalar", "type": type(value).__name__, "value": value}
    else:
        array = np.ascontiguousarray(np.asarray(value))
        if array.dtype.hasobject:
            raise TypeError("object dtype is forbidden in semantic evidence")
        payload = {
            "kind": "ndarray", "dtype": str(array.dtype),
            "shape": [int(item) for item in array.shape],
            "data_sha256": hashlib.sha256(array.view(np.uint8)).hexdigest(),
        }
    payload["sha256"] = _semantic_sha256(payload)
    return payload

def _array_descriptor(value: Any) -> dict[str, Any]:
    descriptor = _semantic_tree(value)
    if descriptor.get("kind") != "ndarray":
        raise TypeError("array descriptor requires an ndarray-like value")
    return descriptor

def _array_bundle(values: Any) -> dict[str, Any]:
    return _semantic_tree(tuple(values))

def _mapping_array_bundle(values: Mapping[str, Any]) -> dict[str, Any]:
    return _semantic_tree(values)

def _topology_compact_audit(topology: Any) -> dict[str, Any]:
    keys = ("owner_local_maps", "numeric_allgather", "global_transfer_matrix",
            "phase_application", "edge_orientation", "cell_permutation",
            "floquet_phase", "slave_master_complete", "local_unique_edge_count",
            "owned_unique_edge_count", "global_unique_edge_count")
    return {key: topology.audit[key] for key in keys}

def _level_record_facts(level: Any) -> dict[str, Any]:
    facts = dict(level.audit)
    facts["degree"] = int(level.degree)
    parent = _topology_compact_audit(level.parent_topology)
    raw = _topology_compact_audit(level.raw_topology)
    facts["parent_topology"] = parent
    facts["raw_topology"] = raw
    facts["topology_inventory_closed"] = bool(
        parent["global_unique_edge_count"] == facts["parent_global_unique_rows"]
        and raw["global_unique_edge_count"] == facts["raw_global_unique_rows"]
        and parent["global_unique_edge_count"] == raw["global_unique_edge_count"]
    )
    return facts

def _forbidden_facts(case: Any, extension: Any) -> tuple[dict[str, bool], dict[str, str]]:
    case_audit = case.audit
    extension_audit = extension.audit
    level_audits = [level.audit for level in extension.levels.values()]
    facts: dict[str, bool] = {}
    sources: dict[str, str] = {}
    extension_keys = (
        "global_transfer_matrix", "numeric_allgather", "p1_global_direct_factor",
        "p6_exact_factor", "hx_hierarchy_built", "pcgamg_hierarchy_built",
        "physical_solve", "recovery",
    )
    for key in extension_keys:
        value = extension_audit[key]
        if type(value) is not bool:
            raise TypeError(f"extension audit fact is not bool: {key}")
        facts[key] = value
        sources[key] = "extension.audit"
    high_order_values = [audit["global_high_order_aij"] for audit in level_audits]
    if any(type(value) is not bool for value in high_order_values):
        raise TypeError("level audit fact is not bool: global_high_order_aij")
    facts["global_high_order_aij"] = any(high_order_values)
    sources["global_high_order_aij"] = "extension.levels[*].audit"
    case_keys = (
        "global_dense_transfer", "global_numeric_allgather", "scalar_node_matrix_built",
        "global_direct_coarse_built", "recovery_field_arrays_built", "p6_exact_edge_factor_built",
        "hx_or_node_action_built", "production_local_spectral_built",
    )
    for key in case_keys:
        value = case_audit[key]
        if type(value) is not bool:
            raise TypeError(f"case audit fact is not bool: {key}")
        facts[key] = value
        sources[key] = "case.audit"
    return facts, sources

def _transfer_record_facts(transfer: Any) -> dict[str, Any]:
    facts = dict(transfer.audit)
    facts["local_transfer_arrays"] = {
        "edge_transfer": _array_descriptor(transfer.local_transfer.edge_transfer),
        "node_transfer": _array_descriptor(transfer.local_transfer.node_transfer),
    }
    return facts
def _action_probe(level: Any, arrays: dict[str, Any], prefix: str = "a") -> dict[str, Any]:
    import numpy as np
    matrix = level.matrix
    source = matrix.createVecRight()
    out1 = matrix.createVecLeft()
    out2 = matrix.createVecLeft()
    try:
        _fill_deterministic(source, float(level.degree) / 10.0)
        before = _vector_digest(source)
        matrix.mult(source, out1)
        matrix.mult(source, out2)
        after = _vector_digest(source)
        x, y1, y2 = _vector_values(source), _vector_values(out1), _vector_values(out2)
        name = f"{prefix}{level.degree}"
        arrays[f"{name}_input"] = x
        arrays[f"{name}_out1"] = y1
        arrays[f"{name}_out2"] = y2
        return {
            "diff_norm": float(np.linalg.norm(y2 - y1)),
            "ref_norm": float(np.linalg.norm(y1)),
            "finite": bool(np.all(np.isfinite(y1)) and np.all(np.isfinite(y2))),
            "input_before_digest": before,
            "input_after_digest": after,
            "input_unchanged": before == after,
        }
    finally:
        source.destroy()
        out1.destroy()
        out2.destroy()
def _transfer_probe(extension: Any, pair: tuple[int, int], arrays: dict[str, Any]) -> dict[str, Any]:
    import numpy as np
    fine = extension.levels[pair[0]]
    coarse = extension.levels[pair[1]]
    tag = f"{pair[0]}{pair[1]}"
    seed = coarse.matrix.createVecRight()
    seed2 = coarse.matrix.createVecRight()
    x = x2 = None
    combo = coarse.matrix.createVecRight()
    y = fine.matrix.createVecRight()
    ca = coarse.matrix.createVecLeft()
    fa = fine.matrix.createVecLeft()
    try:
        _fill_deterministic(seed, 0.1 + pair[1])
        _fill_deterministic(seed2, 0.7 + pair[0])
        x = coarse.owner_to_primal(coarse.primal_to_owner(seed))
        x2 = coarse.owner_to_primal(coarse.primal_to_owner(seed2))
        _fill_deterministic(y, 0.3 + pair[1])
        x_before, y_before = _vector_digest(x), _vector_digest(y)
        px1 = extension.apply_primal(pair, x)
        px_repeat = extension.apply_primal(pair, x)
        px2 = extension.apply_primal(pair, x2)
        combo.array[:] = ALPHA * x.array + BETA * x2.array
        combo.assemble()
        pcombo = extension.apply_primal(pair, combo)
        phy = extension.apply_adjoint(pair, y)
        coarse.matrix.mult(x, ca)
        fine.matrix.mult(px1, fa)
        x_values = _vector_values(x)
        x2_values = _vector_values(x2)
        y_values = _vector_values(y)
        px1_values = _vector_values(px1)
        px_repeat_values = _vector_values(px_repeat)
        px2_values = _vector_values(px2)
        pcombo_values = _vector_values(pcombo)
        phy_values = _vector_values(phy)
        coarse_action = _vector_values(ca)
        fine_action = _vector_values(fa)
        arrays.update({
            f"t{tag}_x": x_values, f"t{tag}_x2": x2_values,
            f"t{tag}_y": y_values, f"t{tag}_px1": px1_values,
            f"t{tag}_px_repeat": px_repeat_values, f"t{tag}_px2": px2_values,
            f"t{tag}_pcombo": pcombo_values,
            f"t{tag}_phy": phy_values, f"t{tag}_coarse_action": coarse_action,
            f"t{tag}_fine_action": fine_action,
        })
        lhs = np.vdot(px1_values, y_values)
        rhs = np.vdot(x_values, phy_values)
        ec = np.vdot(x_values, coarse_action)
        ef = np.vdot(px1_values, fine_action)
        return {
            "repeat_relative": _relative(px_repeat_values, px1_values),
            "linearity_relative": float(np.linalg.norm(
                pcombo_values - ALPHA * px1_values - BETA * px2_values
            ) / max(float(np.linalg.norm(pcombo_values)), 1.0e-300)),
            "adjoint_relative": float(abs(lhs - rhs) / max(abs(lhs), abs(rhs), 1.0e-300)),
            "energy_coarse": [float(ec.real), float(ec.imag)],
            "energy_fine": [float(ef.real), float(ef.imag)],
            "energy_relative": float(abs(ef - ec) / max(abs(ec), 1.0e-300)),
            "energy_imag_defect": float(max(abs(ec.imag), abs(ef.imag))),
            "coarse_primal_source": COARSE_PRIMAL_SOURCE,
            "finite": bool(all(np.all(np.isfinite(v)) for v in (
                x_values, x2_values, y_values, px1_values, px_repeat_values, px2_values,
                pcombo_values, phy_values, coarse_action, fine_action
            ))),
            "input_unchanged": x_before == _vector_digest(x) and y_before == _vector_digest(y),
            "x_before_digest": x_before,
            "x_after_digest": _vector_digest(x),
            "y_before_digest": y_before,
            "y_after_digest": _vector_digest(y),
        }
    finally:
        for name in ("seed", "seed2", "x", "x2", "combo", "y", "ca", "fa", "px1", "px_repeat", "px2", "pcombo", "phy"):
            value = locals().get(name)
            if value is not None:
                value.destroy()
def _smoother_probe(extension: Any, degree: int, arrays: dict[str, Any]) -> dict[str, Any]:
    import numpy as np
    matrix = extension.levels[degree].matrix
    rhs = matrix.createVecRight()
    out1 = matrix.createVecRight()
    out2 = matrix.createVecRight()
    try:
        _fill_deterministic(rhs, degree + 0.2)
        before = _vector_digest(rhs)
        facts = extension.apply_smoother(degree, rhs, out1)
        extension.apply_smoother(degree, rhs, out2)
        rhs_values = _vector_values(rhs)
        y1, y2 = _vector_values(out1), _vector_values(out2)
        arrays[f"s{degree}_rhs"] = rhs_values
        arrays[f"s{degree}_out1"] = y1
        arrays[f"s{degree}_out2"] = y2
        result = dict(facts)
        result.update({
            "repeat_relative": _relative(y2, y1),
            "finite": bool(np.all(np.isfinite(y1)) and np.all(np.isfinite(y2))),
            "input_before_digest": before,
            "input_after_digest": _vector_digest(rhs),
            "input_unchanged": before == _vector_digest(rhs),
        })
        return result
    finally:
        rhs.destroy()
        out1.destroy()
        out2.destroy()
def _probe_extension(extension: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    facts: dict[str, Any] = {"actions": {}, "transfers": {}, "smoothers": {}}
    arrays: dict[str, Any] = {}
    for degree in LEVELS:
        facts["actions"][str(degree)] = _action_probe(extension.levels[degree], arrays)
    for pair in PAIRS:
        facts["transfers"][f"{pair[0]}-{pair[1]}"] = _transfer_probe(extension, pair, arrays)
    for degree in (6, 3):
        facts["smoothers"][str(degree)] = _smoother_probe(extension, degree, arrays)
    return facts, arrays
def _fingerprint(extension: Any) -> tuple[str, dict[str, Any]]:
    from src.solvers.fullspace_lor_memory_first_foundation import _topology_retained_arrays
    def level_payload(level: Any) -> dict[str, Any]:
        audit = level.audit
        matrix = {key: audit["matrix"][key] for key in ("rows", "cols", "nnz", "index_bytes", "numeric_bytes", "type")}
        inventory_keys = ("parent_local_owned_rows", "parent_local_unique_rows", "parent_global_unique_rows",
                          "raw_local_owned_rows", "raw_local_unique_rows", "raw_global_unique_rows",
                          "parent_cell_count_local", "owner_route", "parent_matrix_built")
        return {
            "degree": int(level.degree), "matrix": matrix,
            "parent_inventory": {key: audit[key] for key in inventory_keys},
            "raw_inventory": {key: audit[key] for key in inventory_keys if key.startswith("raw_")},
            "parent_topology_arrays": _array_bundle(_topology_retained_arrays(level.parent_topology)),
            "raw_topology_arrays": _array_bundle(_topology_retained_arrays(level.raw_topology)),
            "raw_map_arrays": _mapping_array_bundle(level.raw_map),
            "raw_permutations": _array_descriptor(level.raw_permutations),
            "incidence_unique": _array_descriptor(level.incidence_unique),
            "parent_topology": _topology_compact_audit(level.parent_topology),
            "raw_topology": _topology_compact_audit(level.raw_topology),
        }
    def transfer_payload(transfer: Any) -> dict[str, Any]:
        audit = transfer.audit
        local = audit["local_map"]
        local_keys = ("edge_rows", "edge_cols", "edge_exact_nnz", "edge_numeric_bytes",
                      "node_rows", "node_cols", "node_exact_nnz", "node_numeric_bytes")
        local_audit = audit["local_transfer"]
        legality_keys = ("edge_line_integral_relative", "curl_flux_relative",
                         "gradient_commuting_relative", "node_transfer_relative",
                         "adjoint_work_relative", "linearity_relative", "repeat_relative",
                         "line_integral_histopolation", "simple_injection",
                         "structural_projection", "structural_forbidden_entry_count",
                         "structural_forbidden_nnz_after",
                         "structural_removed_nonzero_count",
                         "structural_removed_max_abs")
        return {"pair": [int(audit["pair"][0]), int(audit["pair"][1])],
                "local_map": {key: local[key] for key in local_keys},
                "edge_transfer": _array_descriptor(transfer.local_transfer.edge_transfer),
                "node_transfer": _array_descriptor(transfer.local_transfer.node_transfer),
                "local_legality": {key: local_audit[key] for key in legality_keys}}
    payload = {
        "levels": {str(d): level_payload(extension.levels[d]) for d in LEVELS},
        "transfers": {f"{a}-{b}": transfer_payload(extension.transfers[(a, b)]) for a, b in PAIRS},
        "smoothers": {
            str(d): {
                "degree": d,
                "fixed_degree": CHEBYSHEV_DEGREE,
                "power_steps": POWER_STEPS,
                "pre_sweeps": PRE_SWEEPS,
                "post_sweeps": POST_SWEEPS,
                "lambda_power10": float(extension.smoothers[d].lambda_power10),
                "lambda_hi": float(extension.smoothers[d].lambda_hi),
                "lambda_lo": float(extension.smoothers[d].lambda_lo),
            } for d in (6, 3)
        },
    }
    return _semantic_sha256(payload), payload
def _combined_ledger(case: Any, extension: Any, reserve: Mapping[str, Any], resource: Mapping[str, Any]) -> dict[str, Any]:
    foundation = case.retained_ledger(reserve, resource)
    lower = extension.retained_ledger(resource)
    known = dict(foundation["known_bytes"])
    known.update({f"extension_{key}": int(value) for key, value in lower["known_bytes"].items()})
    total = int(sum(value for value in known.values() if isinstance(value, int)))
    rss = int(resource.get("process_tree", {}).get("rss_bytes", -1))
    return {
        "scope": "foundation plus lower hierarchy; level6 matrix/topology counted only by foundation",
        "known_bytes": known,
        "known_total_bytes": total,
        "measured_process_tree_rss_bytes": rss,
        "unattributed_remainder_bytes": rss - total,
        "level6_foundation_ledger_included_once": True,
        "foundation": foundation,
        "extension": lower,
        "resource": dict(resource),
        "bounded_temporary_bytes": {
            "included_in_known_total": False,
            "transfer_batch_cell_cap": 32,
        },
    }
def run_worker(raw_dir: Path, record_path: Path, input_path: Path, expected_sha: str, expected_mpi: int) -> None:
    global _input_identity, _prepare_paths, _resource_sample, _runtime, _sha256, _source_identity, _vector_digest, _write_json
    from benchmarks.run_task038_full3d_lor_s2_memory_first import (
        _input_identity, _prepare_paths, _resource_sample, _runtime,
        _sha256, _source_identity, _vector_digest, _write_json,
    )
    from mpi4py import MPI
    import numpy as np
    from benchmarks.run_task038_full3d_r4 import _resolve_case
    from src.solvers.fullspace_lor_memory_first_foundation import (
        allocate_restart20_reserve, build_s2_foundation_case, destroy_restart20_reserve,
    )
    from src.solvers.fullspace_lor_memory_hierarchy_runtime import build_s5_hierarchy_extension
    comm = MPI.COMM_WORLD
    if comm.size != int(expected_mpi) or comm.size != 1:
        raise RuntimeError("S5 capacity case is fixed to MPI1")
    root = Path(__file__).resolve().parents[1]
    raw_dir = (raw_dir if raw_dir.is_absolute() else root / raw_dir).resolve()
    record_path = (record_path if record_path.is_absolute() else root / record_path).resolve()
    input_path = (input_path if input_path.is_absolute() else root / input_path).resolve()
    _prepare_paths(raw_dir, record_path, comm)
    _marker(raw_dir, "paths_ready", expected_sha, comm, raw_dir=str(raw_dir))
    runtime = _runtime(root, expected_sha, comm)
    _marker(raw_dir, "source_runtime_closed", expected_sha, comm, runtime=runtime)
    case = reserve = extension = None
    try:
        specification, cfg, resolved = _resolve_case(root, input_path, DEGREE, H_NM)
        input_identity = _input_identity(root, input_path, specification, resolved)
        case = build_s2_foundation_case(raw_dir, comm, cfg, resolved_config=resolved, resource_sample=_resource_sample)
        _marker(raw_dir, "foundation_built", expected_sha, comm, audit=case.audit)
        reserve = allocate_restart20_reserve(case.high_primal_source)
        _marker(raw_dir, "reserve_built", expected_sha, comm, reserve={k: v for k, v in reserve.items() if k != "vectors"})
        extension = build_s5_hierarchy_extension(case)
        _marker(raw_dir, "hierarchy_built_first", expected_sha, comm)
        first_facts, arrays = _probe_extension(extension)
        first_sha, fingerprint_payload = _fingerprint(extension)
        _marker(raw_dir, "probes_complete", expected_sha, comm, operation_count=len(arrays))
        first_probe = raw_dir / "probe_first.npz"
        np.savez(first_probe, **arrays)
        del arrays
        extension.destroy()
        extension = None
        gc.collect()
        _marker(raw_dir, "hierarchy_destroyed", expected_sha, comm)
        extension = build_s5_hierarchy_extension(case)
        _marker(raw_dir, "hierarchy_rebuilt", expected_sha, comm)
        rebuild_sha, rebuild_payload = _fingerprint(extension)
        rebuild_arrays: dict[str, Any] = {}
        rebuild_probe = _action_probe(extension.levels[6], rebuild_arrays, prefix="rebuild_a")
        rebuild_file = raw_dir / "probe_rebuild.npz"
        np.savez(rebuild_file, **rebuild_arrays)
        del rebuild_arrays
        raw_probe = raw_dir / "probe_facts.npz"
        with np.load(first_probe, allow_pickle=False) as first_data, np.load(rebuild_file, allow_pickle=False) as rebuild_data:
            combined = {key: first_data[key] for key in first_data.files}
            combined.update({key: rebuild_data[key] for key in rebuild_data.files})
            np.savez(raw_probe, **combined)
        del combined
        first_probe.unlink()
        rebuild_file.unlink()
        probe_sha = _sha256(raw_probe)
        retained_ready = _marker(raw_dir, "retained_ready", expected_sha, comm, retained_dwell_seconds=RETAINED_DWELL_SECONDS)
        time.sleep(RETAINED_DWELL_SECONDS)
        resource = _resource_sample()
        retained = _combined_ledger(case, extension, reserve, resource)
        levels = {str(d): _level_record_facts(extension.levels[d]) for d in LEVELS}
        transfers = {f"{a}-{b}": _transfer_record_facts(extension.transfers[(a, b)]) for a, b in PAIRS}
        smoothers = {str(d): {
            "degree": d,
            "fixed_degree": CHEBYSHEV_DEGREE, "power_steps": POWER_STEPS,
            "pre_sweeps": PRE_SWEEPS, "post_sweeps": POST_SWEEPS,
            "lambda_power10": float(extension.smoothers[d].lambda_power10),
            "lambda_hi": float(extension.smoothers[d].lambda_hi),
            "lambda_lo": float(extension.smoothers[d].lambda_lo),
            "power_matrix_mult_count": int(extension.smoothers[d].power_matrix_mult_count),
            "matrix_mult_count": int(extension.smoothers[d].matrix_mult_count),
        } for d in (6, 3)}
        level1_matrix = dict(extension.levels[1].audit["matrix"])
        end_source = _source_identity(root, expected_sha)
        command = [str(Path(sys.executable).absolute()), "-m", MODULE, "--stage", STAGE, "--case", CASE,
                   "--raw-dir", str(raw_dir), "--record", str(record_path),
                   "--expected-source-sha", expected_sha, "--expected-mpi-size", str(expected_mpi),
                   "--input", str(input_path)]
        probe_facts = {"first": first_facts, "rebuild": {"actions": {"6": rebuild_probe}}}
        forbidden, forbidden_sources = _forbidden_facts(case, extension)
        record = {
            "schema": SCHEMA, "stage": STAGE, "case": CASE, "degree": DEGREE,
            "h_nm": H_NM, "wavelength_nm": WAVELENGTH_NM, "mpi_size": int(comm.size),
            "raw_dir": str(raw_dir), "record_path": str(record_path),
            "command": command,
            "source": {"start": runtime["source"], "end": end_source}, "runtime": runtime,
            "input_identity": input_identity,
            "provenance": {"source_sha": expected_sha, "branch": BRANCH,
                "input_sha256": input_identity["raw_sha256"],
                "resolved_sha256": input_identity["resolved_sha256"],
                "physical_model_sha256": input_identity["physical_model_sha256"]},
            "reserve": {key: value for key, value in reserve.items() if key != "vectors"},
            "settings": {"levels": list(LEVELS), "pairs": [list(p) for p in PAIRS],
                "chebyshev_degree": CHEBYSHEV_DEGREE, "power_steps": POWER_STEPS,
                "pre_sweeps": PRE_SWEEPS, "post_sweeps": POST_SWEEPS,
                "reserve_basis": RESERVE_BASIS, "reserve_auxiliary": RESERVE_AUXILIARY,
                "reserve_count": RESERVE_COUNT, "retained_dwell_seconds": RETAINED_DWELL_SECONDS},
            "architecture": {"forbidden": forbidden, "forbidden_sources": forbidden_sources, "levels": levels,
                "transfers": transfers, "smoothers": smoothers,
                "foundation_audit": case.audit,
                "p1_coarse_budget": {"status": "derived_estimate_only", "solver_selected": False,
                    "direct_factor_built": False, "matrix_payload_bytes": int(level1_matrix["index_bytes"] + level1_matrix["numeric_bytes"]),
                    "fixed_work_vector_count": 8, "fixed_work_vector_bytes": int(8 * level1_matrix["rows"] * 16),
                    "petsc_overhead_bytes": int(level1_matrix["petsc_overhead_bytes"]),
                    "estimated_total_bytes": int(level1_matrix["index_bytes"] + level1_matrix["numeric_bytes"] + level1_matrix["petsc_overhead_bytes"] + 8 * level1_matrix["rows"] * 16)},},
            "probes": probe_facts,
            "raw_artifacts": {"probe_npz": {"relative_path": raw_probe.name, "sha256": probe_sha}},
            "fingerprint": {"first": {"payload": fingerprint_payload, "sha256": first_sha},
                "rebuild": {"payload": rebuild_payload, "sha256": rebuild_sha},
                "exact_identity": first_sha == rebuild_sha and fingerprint_payload == rebuild_payload},
            "markers": {"relative_dir": "markers", "names": list(MARKERS)},
            "retained_ready_wall_time_ns": retained_ready,
            "retained": retained,
        }
        if comm.rank == 0:
            _write_json(record_path, record)
            with record_path.open("rb") as stream:
                os.fsync(stream.fileno())
        comm.barrier()
        _marker(raw_dir, "record_written", expected_sha, comm, record_path=str(record_path))
    finally:
        if extension is not None:
            extension.destroy()
        if reserve is not None:
            destroy_restart20_reserve(reserve)
        if case is not None:
            case.destroy()
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=(STAGE,), required=True)
    parser.add_argument("--case", choices=(CASE,), required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--expected-mpi-size", type=int, required=True)
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args(argv)
    run_worker(args.raw_dir, args.record, args.input, args.expected_source_sha, args.expected_mpi_size)
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
