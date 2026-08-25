"""Thin Route-B setup/positive evidence worker for the R4.1 qualification.

The worker owns only raw facts and lifecycle markers.  The external foundation
watchdog owns process-tree resource sampling; the independent checker owns all
classification.  ``setup`` measures the fixed ten-apply reserve path, while
``positive`` uses the existing restart-20 residual-authority loop for one
frozen analytic source.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Mapping


BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"
MODULE = "benchmarks.run_task038_full3d_lor_nested_positive"
SCHEMA = "task038.full3d.lor-nested-positive.r4.v1"
MARKER_SCHEMA = "task038.full3d.lor-nested-positive.marker.v1"
CASE = "p6-h10-mpi1"
DEGREE = 6
H_NM = 10.0
WAVELENGTH_NM = 13.5
MPI_SIZE = 1
CHEBYSHEV_DEGREE = 3
POWER_STEPS = 10
RESTART = 20
MAX_IT = 10000
RESIDUAL_LIMIT = 1.0e-8
CHECKPOINT_INTERVAL = 500
RETAINED_DWELL_SECONDS = 2.0
SETUP_APPLY_COUNT = 10
SETUP_GROWTH_LIMIT_BYTES = 32_000_000
IMMUTABLE_OPERATOR_ACTION_KEYS = (
    "schema", "backend", "matrix_type", "operator", "mpc_enabled",
    "slave_row_identity", "global_rows", "local_owned_rows",
    "local_ghost_rows", "local_storage_entries",
    "constraint_row_metadata_entries", "constraint_count",
    "owned_constraint_count", "constraint_nnz", "constraint_nnz_closes",
    "form_rank", "coefficient_count", "phase_application", "orientation",
    "owner_local", "numeric_allgather", "replicated_global_numeric_vector",
    "global_matrix_materialized", "global_constraint_matrix_materialized",
    "global_condensed_schur_materialized", "cell_schur_matrix_materialized",
    "slab_matrix_materialized", "cell_schur_matrix_nnz", "slab_matrix_nnz",
    "factor_count", "ksp_created", "dtn_used", "ordinary_default_changed",
    "fresh_packed_arrays_released", "jit_options_explicit",
    "retained_numeric_payload_components",
    "retained_numeric_payload_local_bytes",
    "retained_numeric_payload_global_sum_bytes",
    "retained_numeric_payload_global_max_bytes",
    "retained_dense_cell_tensor_count",
    "dense_cell_tensor_materialized_per_apply",
)
STAGES = ("setup", "positive")
SOURCES = ("random", "gradient", "curl", "checkerboard")
MARKER_NAMES = {
    "setup": (
        "paths_ready", "source_runtime_closed", "foundation_built",
        "extension_built", "vcycle_built", "reserve_built",
        "pc_applies_complete", "retained_ready", "vcycle_destroyed",
        "reserve_destroyed", "foundation_destroyed", "record_written",
    ),
    "positive": (
        "paths_ready", "source_runtime_closed", "foundation_built",
        "extension_built", "vcycle_built", "positive_started",
        "checkpoints_complete", "retained_ready", "vcycle_destroyed",
        "foundation_destroyed", "record_written",
    ),
}


def _jsonable(value: Any) -> Any:
    """Convert the small scalar/sequence facts written by this worker."""

    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (str, bool, int, float)) or value is None:
        return value
    if isinstance(value, complex):
        return [float(value.real), float(value.imag)]
    return str(value)


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        _jsonable(value), sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8") + b"\n"


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _stable_sha(value: Any) -> str:
    return _sha256_bytes(_json_bytes(value).rstrip(b"\n"))


def _write_json(path: Path, value: Mapping[str, Any]) -> str:
    encoded = _json_bytes(value)
    path.write_bytes(encoded)
    return _sha256_file(path)


def canonical_worker_command(
    raw_dir: Path,
    record_path: Path,
    input_path: Path,
    source_sha: str,
    stage: str,
    source: str | None = None,
    *,
    executable: str | None = None,
) -> list[str]:
    """Return the exact direct-worker argv bound into a record/watchdog."""

    if stage not in STAGES:
        raise ValueError(f"unknown R4.1 stage {stage!r}")
    if stage == "positive" and source not in SOURCES:
        raise ValueError("positive stage requires one frozen source")
    if stage == "setup" and source is not None:
        raise ValueError("setup stage has no source argument")
    command = [
        str(Path(executable or sys.executable).absolute()), "-m", MODULE,
        "--stage", stage, "--case", CASE,
        "--raw-dir", str(Path(raw_dir).resolve()),
        "--record", str(Path(record_path).resolve()),
        "--expected-source-sha", str(source_sha),
        "--expected-mpi-size", str(MPI_SIZE),
        "--input", str(Path(input_path).resolve()),
    ]
    if stage == "positive":
        command.extend(("--source", str(source)))
    return command


def _resource_scalars(sample: Mapping[str, Any]) -> dict[str, Any]:
    tree = sample.get("process_tree", {})
    return {
        "rss_bytes": int(tree["rss_bytes"]),
        "swap_bytes": int(tree["swap_bytes"]),
        "all_status_readable": bool(tree["all_status_readable"]),
    }


def _array_descriptor(path: Path, values: Any) -> dict[str, Any]:
    import numpy as np

    values = np.ascontiguousarray(np.asarray(values))
    return {
        "relative_path": path.name,
        "bytes": int(values.nbytes),
        "sha256": hashlib.sha256(values.view(np.uint8)).hexdigest(),
        "dtype": str(values.dtype),
        "shape": list(values.shape),
    }


def _array_sha256(values: Any) -> str:
    import numpy as np

    values = np.ascontiguousarray(np.asarray(values))
    return hashlib.sha256(values.view(np.uint8)).hexdigest()


def _immutable_operator_action_audit(audit: Mapping[str, Any]) -> dict[str, Any]:
    missing = [key for key in IMMUTABLE_OPERATOR_ACTION_KEYS if key not in audit]
    if missing:
        raise RuntimeError(f"high positive immutable audit is missing {missing}")
    return {key: _jsonable(audit[key]) for key in IMMUTABLE_OPERATOR_ACTION_KEYS}


def _copy_borrowed_action(action: Any, source: Any) -> Any:
    """Copy an action-owned Vec without taking ownership of or destroying it."""

    return action.apply(source).copy()


def _marker(raw_dir: Path, name: str, source_sha: str, facts: Mapping[str, Any]) -> int:
    if name not in {item for names in MARKER_NAMES.values() for item in names}:
        raise ValueError(f"unknown R4.1 marker {name}")
    path = raw_dir / "markers" / f"{name}.json"
    if path.exists():
        raise FileExistsError(f"marker already exists: {path}")
    timestamp = time.time_ns()
    payload = {
        "schema": MARKER_SCHEMA,
        "marker": name,
        "source_sha": source_sha,
        "wall_time_ns": timestamp,
        "facts": dict(facts),
    }
    path.write_bytes(_json_bytes(payload))
    with path.open("rb") as stream:
        os.fsync(stream.fileno())
    return timestamp


def _prepare_worker_paths(raw_dir: Path, record_path: Path, comm: Any) -> None:
    """Use the already-qualified S2 fail-closed path creator."""

    from benchmarks.run_task038_full3d_lor_s2_memory_first import _prepare_paths

    _prepare_paths(raw_dir, record_path, comm)


def _vector_digest(vector: Any) -> str:
    import hashlib
    import numpy as np

    values = np.ascontiguousarray(
        np.asarray(vector.getArray(readonly=True), dtype=np.complex128)
    )
    return hashlib.sha256(values.view(np.uint8)).hexdigest()


def _vector_values(vector: Any) -> Any:
    import numpy as np

    return np.asarray(vector.getArray(readonly=True), dtype=np.complex128).copy()


def _relative(left: Any, right: Any) -> float:
    import numpy as np

    left = np.asarray(left, dtype=np.complex128)
    right = np.asarray(right, dtype=np.complex128)
    return float(np.linalg.norm(left - right) / max(np.linalg.norm(right), np.finfo(float).tiny))


def _noncollinear_relative(left: Any, right: Any) -> float:
    """Return the relative component of ``right`` orthogonal to ``left``."""

    import numpy as np

    left = np.asarray(left, dtype=np.complex128)
    right = np.asarray(right, dtype=np.complex128)
    denominator = np.vdot(left, left)
    if not np.isfinite(denominator) or abs(denominator) == 0.0:
        return 0.0
    orthogonal = right - left * (np.vdot(left, right) / denominator)
    return float(np.linalg.norm(orthogonal) / max(np.linalg.norm(right), np.finfo(float).tiny))


def _copy_scaled(template: Any, scale: complex) -> Any:
    result = template.duplicate()
    result.set(0.0 + 0.0j)
    result.axpy(scale, template)
    return result


def _p1_factor_facts(vcycle: Any) -> dict[str, Any]:
    matrix = vcycle.level1.matrix
    _indptr, _indices, values = matrix.getValuesCSR()
    facts: dict[str, Any] = {
        "backend": str(vcycle.level1_solver.audit.get("backend", "petsc-preonly-lu-mumps"))
        if hasattr(vcycle.level1_solver, "audit")
        else "petsc-preonly-lu-mumps",
        "factor_solver_type": "mumps",
        "matrix_rows": int(matrix.getSize()[0]),
        "matrix_cols": int(matrix.getSize()[1]),
        "matrix_nnz": int(len(values)),
        "setup_count": int(getattr(vcycle.level1_solver, "setup_count", 1)),
        "solve_count": int(vcycle.level1_solver.solve_count),
        "factor_matrix_nnz": None,
        "petsc_reported_factor_memory_local_bytes": None,
        "petsc_reported_factor_memory_global_bytes": None,
        "petsc_reported_factor_memory_bytes": None,
        "petsc_reported_factor_memory_available": False,
    }
    try:
        factor = vcycle.level1_solver.ksp.getPC().getFactorMatrix()
        if factor is not None:
            factor_info = dict(factor.getInfo())
            if "nz_used" in factor_info:
                facts["factor_matrix_nnz"] = int(factor_info["nz_used"])
            if "memory" in factor_info:
                memory = int(factor_info["memory"])
                facts["petsc_reported_factor_memory_bytes"] = memory
                facts["petsc_reported_factor_memory_local_bytes"] = memory
                facts["petsc_reported_factor_memory_global_bytes"] = memory
                facts["petsc_reported_factor_memory_available"] = memory > 0
    except (AttributeError, KeyError, TypeError, ValueError, RuntimeError):
        pass
    return facts


def _forbidden_architecture(case: Any, extension: Any, vcycle: Any) -> dict[str, bool]:
    sources = {
        "case": case.audit,
        "extension": dict(extension.audit),
        "vcycle": dict(vcycle.audit),
    }
    bindings = {
        "global_high_order_aij": ("vcycle", "global_high_order_aij"),
        "global_transfer_matrix": ("extension", "global_transfer_matrix"),
        "global_dense_transfer": ("case", "global_dense_transfer"),
        "numeric_allgather": ("extension", "numeric_allgather"),
        "global_numeric_allgather": ("case", "global_numeric_allgather"),
        "p6_exact_factor": ("extension", "p6_exact_factor"),
        "p6_exact_edge_factor_built": ("case", "p6_exact_edge_factor_built"),
        "level2_exact_factor": ("vcycle", "level2_exact_factor"),
        "global_direct_coarse": ("vcycle", "global_direct_coarse"),
        "hx_hierarchy_built": ("extension", "hx_hierarchy_built"),
        "pcgamg_hierarchy_built": ("extension", "pcgamg_hierarchy_built"),
        "scalar_node_matrix_built": ("case", "scalar_node_matrix_built"),
        "recovery_field_arrays_built": ("case", "recovery_field_arrays_built"),
        "hx_or_node_action_built": ("case", "hx_or_node_action_built"),
        "production_local_spectral_built": ("case", "production_local_spectral_built"),
        "physical_solve": ("extension", "physical_solve"),
        "recovery": ("extension", "recovery"),
        "retains_per_apply_history": ("vcycle", "retains_per_apply_history"),
    }
    result: dict[str, bool] = {}
    for name, (source_name, key) in bindings.items():
        source = sources[source_name]
        if key not in source:
            raise RuntimeError(f"architecture audit is missing {source_name}.{key}")
        value = source[key]
        if not isinstance(value, bool):
            raise RuntimeError(f"architecture audit {source_name}.{key} is not boolean")
        result[name] = value
    return result


def _architecture(case: Any, extension: Any, vcycle: Any) -> dict[str, Any]:
    return {
        "case_audit": case.audit,
        "high_coefficient_audit": _jsonable(case.high_coeff_audit),
        "extension_audit": dict(extension.audit),
        "vcycle_audit": dict(vcycle.audit),
        "forbidden": _forbidden_architecture(case, extension, vcycle),
        "current_anchor_p1_exact_oracle": True,
        "level1_factor": _p1_factor_facts(vcycle),
    }


def _apply_setup_probe(vcycle: Any, vector: Any, label: str, resource_sample: Any) -> tuple[dict[str, Any], Any]:
    import numpy as np

    before = _vector_digest(vector)
    output = vcycle.apply(vector)
    values = _vector_values(output)
    last_apply = dict(vcycle.last_apply_facts)
    slaves = np.asarray(vcycle.foundation.high_floquet.mpc.slaves, dtype=np.int64)
    owned_slaves = slaves[(slaves >= 0) & (slaves < int(output.getLocalSize()))]
    constraint_norm = float(np.max(np.abs(values[owned_slaves]), initial=0.0))
    constraint_relative = constraint_norm / max(float(np.linalg.norm(values)), np.finfo(float).tiny)
    facts = {
        "label": label,
        "input_before_digest": before,
        "input_after_digest": _vector_digest(vector),
        "input_unchanged": before == _vector_digest(vector),
        "output_digest": _vector_digest(output),
        "output_finite": bool(np.all(np.isfinite(values))),
        "output_norm": float(output.norm()),
        "primal_constraint_relative": constraint_relative,
        "legal_high_primal": bool(
            np.isfinite(constraint_relative) and constraint_relative <= 1.0e-12
        ),
        "p1_relative_residual": float(last_apply["p1_relative_residual"]),
        "p1_solve_count": int(last_apply["p1_solve_count"]),
        "transfer_counts": {
            key: int(value) for key, value in last_apply.items()
            if key.startswith("transfer_") and key.endswith("_total")
        },
        "resource": _resource_scalars(resource_sample()),
    }
    output.destroy()
    return facts, values


def _setup_stage(case: Any, vcycle: Any, raw_dir: Path, resource_sample: Any, reserve: Mapping[str, Any]) -> dict[str, Any]:
    x = _copy_scaled(case.high_primal_source, 1.0 + 0.0j)
    y = case.high_dual_source.duplicate()
    case.high_dual_source.copy(y)
    alpha = 0.75 - 0.25j
    beta = -0.5 + 0.5j
    combo = x.duplicate()
    combo.set(0.0 + 0.0j)
    combo.axpy(alpha, x)
    combo.axpy(beta, y)
    ax = _copy_scaled(x, alpha)
    by = _copy_scaled(y, beta)
    apply_facts: list[dict[str, Any]] = []
    kept: dict[str, Any] = {}
    try:
        for label, vector in (
            ("x", x), ("y", y), ("x_repeat", x), ("combo", combo),
            ("ax", ax), ("by", by), ("x_repeat_2", x), ("x_repeat_3", x),
            ("x_repeat_4", x), ("x_repeat_5", x),
        ):
            facts, values = _apply_setup_probe(vcycle, vector, label, resource_sample)
            apply_facts.append(facts)
            if label in {"x", "y", "x_repeat", "combo", "ax", "by"}:
                kept[label] = values
        linearity = _relative(
            kept["combo"], kept["ax"] + kept["by"]
        )
        repeat = _relative(kept["x_repeat"], kept["x"])
        independent = _noncollinear_relative(_vector_values(x), _vector_values(y))
        rss = [int(item["resource"]["rss_bytes"]) for item in apply_facts]
        swaps = [int(item["resource"]["swap_bytes"]) for item in apply_facts]
        p1_residuals = [float(item["p1_relative_residual"]) for item in apply_facts]
        p1_counts = [int(item["p1_solve_count"]) for item in apply_facts]
        facts = {
            "apply_count": len(apply_facts),
            "apply_facts": apply_facts,
            "linearity_relative": linearity,
            "repeat_relative": repeat,
            "alpha": [float(alpha.real), float(alpha.imag)],
            "beta": [float(beta.real), float(beta.imag)],
            "independent_input_relative": independent,
            "finite": bool(all(item["output_finite"] for item in apply_facts)),
            "input_unchanged": bool(all(item["input_unchanged"] for item in apply_facts)),
            "legal_high_primal": bool(all(item["legal_high_primal"] for item in apply_facts)),
            "rss_span_bytes": int(max(rss) - rss[0]) if rss else -1,
            "max_swap_bytes": int(max(swaps)) if swaps else -1,
            "max_p1_relative_residual": max(p1_residuals) if p1_residuals else -1.0,
            "p1_solve_count": p1_counts[-1] if p1_counts else -1,
            "outer_ksp_create_count": 0,
            "outer_ksp_destroy_count": 0,
            "growth_limit_bytes": SETUP_GROWTH_LIMIT_BYTES,
            "vcycle_apply_count": int(vcycle.apply_count),
            "transfer_counts": {
                key: int(value) for key, value in vcycle.last_apply_facts.items()
                if key.startswith("transfer_") and key.endswith("_total")
            },
            "reserve": {key: value for key, value in reserve.items() if key != "vectors"},
        }
        return facts
    finally:
        for vector in (x, y, combo, ax, by):
            vector.destroy()


def _route_b_retained_ledger(
    case: Any, extension: Any, vcycle: Any, reserve: Mapping[str, Any] | None,
    retained_sample: Mapping[str, Any], factor: Mapping[str, Any],
) -> dict[str, Any]:
    """Return the measured component ledger without counting level 6 twice."""

    from src.solvers.fullspace_lor_memory_first_foundation import (
        _retained_array_bytes, _topology_retained_arrays,
    )

    foundation = case.retained_ledger(
        {"local_numeric_bytes": 0}, {"process_tree": dict(retained_sample)}
    )
    route_known: dict[str, int] = {}
    seen: set[int] = set()
    for degree in (2, 1):
        level = extension.levels[degree]
        prefix = f"level{degree}_"
        for name, value in level.audit["retained_known_bytes"].items():
            route_known[prefix + name] = int(value)
        route_known[prefix + "raw_permutations_bytes"] = int(level.raw_permutations.nbytes)
        route_known[prefix + "incidence_unique_bytes"] = int(level.incidence_unique.nbytes)
        route_known[prefix + "parent_topology_retained_array_bytes"] = int(
            _retained_array_bytes(_topology_retained_arrays(level.parent_topology), seen)
        )
        route_known[prefix + "raw_topology_retained_array_bytes"] = int(
            _retained_array_bytes(_topology_retained_arrays(level.raw_topology), seen)
        )
    for pair, transfer in extension.transfers.items():
        local_map = transfer.audit["local_map"]
        prefix = f"transfer_{pair[0]}_{pair[1]}_"
        route_known[prefix + "edge_bytes"] = int(local_map["edge_numeric_bytes"])
        route_known[prefix + "node_bytes"] = int(local_map["node_numeric_bytes"])

    smoother_components: dict[str, Any] = {}
    smoother_names = (
        "_inv_sqrt", "_scaled_input", "_scaled_action", "_rhs_scaled",
        "_residual", "_direction", "_solution", "_action",
    )
    for degree, smoother in ((6, vcycle.smoother6), (2, vcycle.smoother2)):
        vectors = tuple(getattr(smoother, name, None) for name in smoother_names)
        if any(vector is None for vector in vectors):
            raise RuntimeError(f"level{degree} smoother work-vector inventory is incomplete")
        local_entries = [int(vector.getLocalSize()) for vector in vectors]
        bytes_value = int(sum(entries * 16 for entries in local_entries))
        route_known[f"level{degree}_smoother_work_vector_bytes"] = bytes_value
        smoother_components[f"level{degree}"] = {
            "vector_count": 8,
            "local_entries": local_entries,
            "complex128_bytes": bytes_value,
        }

    work_entries = [int(vector.getLocalSize()) for vector in vcycle.work_vectors]
    route_known["vcycle_work_vector_bytes"] = int(sum(entry * 16 for entry in work_entries))
    factor_memory = factor.get("petsc_reported_factor_memory_local_bytes")
    if isinstance(factor_memory, int) and factor_memory > 0:
        route_known["p1_factor_memory_bytes"] = int(factor_memory)
    reserve_bytes = int(reserve.get("local_numeric_bytes", 0)) if reserve else 0
    route_known["restart_reserve_numeric_bytes"] = reserve_bytes
    foundation_known = {
        name: int(value) for name, value in foundation["known_bytes"].items()
        if isinstance(value, int) and name != "restart_reserve_numeric_bytes"
    }
    known = {
        **{f"foundation_{name}": value for name, value in foundation_known.items()},
        **route_known,
    }
    known_total = int(sum(known.values()))
    rss = int(retained_sample["rss_bytes"])
    return {
        "scope": "foundation plus Route-B lower-level measured components; level6 foundation is not duplicated",
        "foundation": foundation,
        "route_b": {
            "known_bytes": route_known,
            "smoother_work_vectors": smoother_components,
            "vcycle_work_vectors": {
                "vector_count": len(work_entries),
                "local_entries": work_entries,
                "complex128_bytes": route_known["vcycle_work_vector_bytes"],
            },
            "p1_factor_memory_bytes": factor_memory,
            "restart_reserve_numeric_bytes": reserve_bytes,
        },
        "known_bytes": known,
        "known_total_bytes": known_total,
        "measured_process_tree_rss_bytes": rss,
        "unattributed_remainder_bytes": int(rss - known_total),
        "estimates_included": False,
    }


def _checkpoint_writer_factory(
    raw_dir: Path,
    source_sha: str,
    input_sha: str,
    operator_sha: str,
    physical_sha: str,
    comm: Any,
):
    from src.solvers.fullspace_memory_first_krylov import write_solution_checkpoint

    def writer(iteration: int, solution: Any, residual: float) -> Mapping[str, Any]:
        start, stop = solution.getOwnershipRange()
        ownership = {
            "rank": int(comm.rank),
            "ownership_range": [int(start), int(stop)],
            "local_size": int(solution.getLocalSize()),
            "global_size": int(solution.getSize()),
        }
        return write_solution_checkpoint(
            raw_dir / f"checkpoint-{int(iteration)}", solution,
            iteration=int(iteration), explicit_true_residual=float(residual),
            input_identity_sha256=input_sha, operator_identity_sha256=operator_sha,
            physical_model_sha256=physical_sha, source_sha=source_sha,
            ownership=ownership, comm=comm,
        )

    return writer


def _positive_stage(
    case: Any, vcycle: Any, raw_dir: Path, source_name: str, source_sha: str,
    operator_authority: Mapping[str, Any], operator_sha: str, resolved_sha: str,
    input_raw_sha: str, physical_sha: str, resource_sample: Any,
    comm: Any,
) -> dict[str, Any]:
    import numpy as np
    from src.solvers.fullspace_lor_native_hx_fixture import build_frozen_fullspace_primal_source
    from src.solvers.fullspace_memory_first_krylov import (
        destroy_krylov_result, run_restart20_cycles,
    )

    source, source_facts = build_frozen_fullspace_primal_source(
        case.high_space, case.high_floquet, case.cfg, source_name
    )
    try:
        source_before = _vector_values(source)
        source_before_finite = bool(np.all(np.isfinite(source_before)))
        source_before_nonzero = bool(np.linalg.norm(source_before) > 0.0)
        if not source_before_finite or not source_before_nonzero:
            raise RuntimeError("positive source is non-finite or zero before applying B_h")
        rhs = _copy_borrowed_action(case.high_positive, source)
        rhs_repeat = _copy_borrowed_action(case.high_positive, source)
        source_after = _vector_values(source)
        if not np.array_equal(source_before, source_after):
            raise RuntimeError("positive source changed during RHS construction")
        ownership_start, ownership_stop = source.getOwnershipRange()
        input_identity_authority = {
            "source_generation": dict(source_facts),
            "source_before": {
                "sha256": _array_sha256(source_before),
                "dtype": str(source_before.dtype),
                "shape": list(source_before.shape),
                "ownership_range": [int(ownership_start), int(ownership_stop)],
                "local_size": int(source.getLocalSize()),
                "global_size": int(source.getSize()),
                "finite": source_before_finite,
                "nonzero": source_before_nonzero,
            },
            "resolved_config_sha256": resolved_sha,
            "input_raw_sha256": input_raw_sha,
            "physical_model_sha256": physical_sha,
        }
        input_sha = _stable_sha(input_identity_authority)
        writer = _checkpoint_writer_factory(
            raw_dir, source_sha, input_sha, operator_sha, physical_sha, comm
        )

        def action(vector: Any) -> Any:
            return case.high_positive.apply(vector).copy()

        result = run_restart20_cycles(
            rhs, action, vcycle.apply, max_it=MAX_IT, residual_limit=RESIDUAL_LIMIT,
            resource_sample=resource_sample, initial_solution=None, start_iteration=0,
            checkpoint_writer=writer, first_checkpoint_iteration=None,
            checkpoint_interval=CHECKPOINT_INTERVAL, stop_on_true_residual=True,
        )
        final_solution = result["final_solution"]
        final_action = action(final_solution)
        final_residual = rhs.copy()
        final_residual.axpy(-1.0, final_action)
        values = {
            "source_before": source_before,
            "source_after": source_after,
            "rhs": _vector_values(rhs),
            "rhs_repeat": _vector_values(rhs_repeat),
            "final_solution": _vector_values(final_solution),
            "final_action": _vector_values(final_action),
            "final_true_residual": _vector_values(final_residual),
        }
        raw_path = raw_dir / "positive_rank0.npz"
        np.savez(raw_path, **values)
        final_relative = float(final_residual.norm()) / max(float(rhs.norm()), np.finfo(float).tiny)
        raw_facts = {
            "relative_path": raw_path.name,
            "sha256": _sha256_file(raw_path),
            "arrays": {name: _array_descriptor(raw_path, value) for name, value in values.items()},
            "rank": int(comm.rank),
            "ownership_range": [int(final_solution.getOwnershipRange()[0]), int(final_solution.getOwnershipRange()[1])],
            "local_size": int(final_solution.getLocalSize()),
            "global_size": int(final_solution.getSize()),
        }
        cycles = []
        for cycle in result["cycles"]:
            cycles.append({
                key: cycle[key] for key in (
                    "cycle_index", "start_iteration", "end_iteration", "iterations", "reason",
                    "initial_guess_nonzero",
                    "reported_final_residual", "explicit_true_residual", "matvec_count",
                    "pc_apply_count", "wall_seconds", "ksp_destroyed",
                )
            } | {"resource": _resource_scalars(cycle["resource"])})
        checkpoint_facts = [
            {key: item[key] for key in (
                "iteration", "manifest_path", "manifest_sha256", "rank", "mpi_size",
                "explicit_true_residual",
            )}
            for item in result["checkpoint_facts"]
        ]
        return {
            "source": source_facts,
            "operator_identity_sha256": operator_sha,
            "operator_identity_authority": dict(operator_authority),
            "physical_model_sha256": physical_sha,
            "input_identity_sha256": input_sha,
            "input_identity_authority": input_identity_authority,
            "source_finite": source_before_finite,
            "source_nonzero": source_before_nonzero,
            "source_before_finite": source_before_finite,
            "source_before_nonzero": source_before_nonzero,
            "source_unchanged": bool(np.array_equal(source_before, source_after)),
            "rhs_repeat_relative": float(
                np.linalg.norm(values["rhs_repeat"] - values["rhs"])
                / max(np.linalg.norm(values["rhs"]), np.finfo(float).tiny)
            ),
            "settings": dict(result["settings"]),
            "initial_true_residual": float(result["initial_true_residual"]),
            "cycles": cycles,
            "iterations": int(result["iterations"]),
            "reason": int(result["reason"]),
            "final_true_residual": final_relative,
            "matvec_count": int(result["matvec_count"]),
            "pc_apply_count": int(result["pc_apply_count"]),
            "explicit_action_count": int(result["explicit_action_count"]) + 3,
            "rhs_action_count": 1,
            "final_action_recheck_count": 1,
            "rhs_repeat_action_count": 1,
            "ksp_create_count": int(result["ksp_destroy_count"]),
            "ksp_destroy_count": int(result["ksp_destroy_count"]),
            "outer_ksp_create_count": int(result["ksp_destroy_count"]),
            "outer_ksp_destroy_count": int(result["ksp_destroy_count"]),
            "vcycle_apply_count": int(vcycle.apply_count),
            "p1_solve_count": int(vcycle.level1_solver.solve_count),
            "max_p1_relative_residual": float(vcycle.max_p1_relative_residual),
            "transfer_counts": {
                key: int(value) for key, value in vcycle.last_apply_facts.items()
                if key.startswith("transfer_") and key.endswith("_total")
            },
            "checkpoint_facts": checkpoint_facts,
            "raw": raw_facts,
            "milestones": {
                str(value): ("measured" if int(result["iterations"]) >= value else "not_reached")
                for value in (20, 100, 200, 500, 1000, 2000, 5000, 10000)
            },
        }
    finally:
        if "final_residual" in locals():
            final_residual.destroy()
        if "final_action" in locals():
            final_action.destroy()
        if "result" in locals():
            destroy_krylov_result(result)
        if "rhs" in locals():
            rhs.destroy()
        if "rhs_repeat" in locals():
            rhs_repeat.destroy()
        source.destroy()


def run_worker(
    raw_dir: Path, record_path: Path, input_path: Path, expected_sha: str,
    expected_mpi: int, stage: str, source_name: str | None = None,
) -> None:
    """Run one fixed p6/h10 MPI1 setup or positive evidence case."""

    from mpi4py import MPI
    from benchmarks.run_task038_full3d_lor_s2_memory_first import (
        _input_identity, _resource_sample, _runtime, _source_identity,
    )
    from benchmarks.run_task038_full3d_r4 import _resolve_case
    from src.solvers.fullspace_lor_memory_first_foundation import (
        allocate_restart20_reserve, build_s2_foundation_case,
    )
    from src.solvers.fullspace_lor_nested_interlevel_runtime import (
        build_route_b_nested_hierarchy_extension,
    )
    from src.solvers.fullspace_lor_nested_vcycle import RouteBNestedVcycle

    if stage not in STAGES or (stage == "positive" and source_name not in SOURCES):
        raise ValueError("R4.1 stage/source identity is invalid")
    if stage == "setup" and source_name is not None:
        raise ValueError("setup does not accept a source")
    comm = MPI.COMM_WORLD
    if int(expected_mpi) != MPI_SIZE or comm.size != MPI_SIZE:
        raise RuntimeError("R4.1 is fixed to p6/h10 MPI1")
    root = Path(__file__).resolve().parents[1]
    raw_dir = Path(raw_dir).resolve()
    record_path = Path(record_path).resolve()
    input_path = Path(input_path).resolve()
    _prepare_worker_paths(raw_dir, record_path, comm)
    marker_times: dict[str, int] = {}
    marker_times["paths_ready"] = _marker(raw_dir, "paths_ready", expected_sha, {"raw_dir": str(raw_dir)})
    runtime = _runtime(root, expected_sha, comm)
    marker_times["source_runtime_closed"] = _marker(raw_dir, "source_runtime_closed", expected_sha, {"runtime": runtime})
    case = None
    extension = None
    vcycle = None
    reserve_object = None
    normal_closeout = False
    try:
        specification, cfg, resolved = _resolve_case(root, input_path, DEGREE, H_NM)
        input_identity = _input_identity(root, input_path, specification, resolved)
        case = build_s2_foundation_case(
            raw_dir, comm, cfg, resolved_config=resolved, resource_sample=_resource_sample
        )
        marker_times["foundation_built"] = _marker(raw_dir, "foundation_built", expected_sha, {"audit": case.audit})
        hierarchy_setup_before = _resource_scalars(_resource_sample())
        extension = build_route_b_nested_hierarchy_extension(foundation=case)
        marker_times["extension_built"] = _marker(
            raw_dir, "extension_built", expected_sha, {"audit": dict(extension.audit)}
        )
        vcycle = RouteBNestedVcycle(case, extension)
        hierarchy_setup_after = _resource_scalars(_resource_sample())
        marker_times["vcycle_built"] = _marker(
            raw_dir, "vcycle_built", expected_sha, {"audit": dict(vcycle.audit)}
        )
        resolved_sha = str(input_identity["resolved_sha256"])
        physical_sha = str(input_identity["physical_model_sha256"])
        operator_authority = {
            "resolved_config_sha256": resolved_sha,
            "input_raw_sha256": input_identity["raw_sha256"],
            "physical_model_sha256": physical_sha,
            "high_coefficient_audit": _jsonable(case.high_coeff_audit),
            "high_positive_action_audit": _immutable_operator_action_audit(
                case.audit["high_positive_action"]
            ),
            "matrix_free_action_identity": "S2FoundationCase.high_positive.apply",
        }
        operator_sha = _stable_sha(operator_authority)
        if stage == "setup":
            reserve_object = allocate_restart20_reserve(case.high_primal_source)
            marker_times["reserve_built"] = _marker(raw_dir, "reserve_built", expected_sha, {"vector_count": 25})
            stage_facts = _setup_stage(case, vcycle, raw_dir, _resource_sample, reserve_object)
            input_identity_authority = {
                "stage": "setup", "resolved_config_sha256": resolved_sha,
                "input_raw_sha256": input_identity["raw_sha256"],
                "physical_model_sha256": physical_sha,
            }
            input_sha = _stable_sha(input_identity_authority)
            stage_facts.update({
                "input_identity_sha256": input_sha,
                "input_identity_authority": input_identity_authority,
                "operator_identity_sha256": operator_sha,
                "operator_identity_authority": operator_authority,
                "physical_model_sha256": physical_sha,
                "identity_authority": {
                    "resolved_config_sha256": resolved_sha,
                    "input_raw_sha256": input_identity["raw_sha256"],
                    "physical_model_sha256": physical_sha,
                },
            })
            marker_times["pc_applies_complete"] = _marker(raw_dir, "pc_applies_complete", expected_sha, {"apply_count": 10})
        else:
            marker_times["positive_started"] = _marker(raw_dir, "positive_started", expected_sha, {"source": source_name})
            stage_facts = _positive_stage(
                case, vcycle, raw_dir, str(source_name), expected_sha,
                operator_authority, operator_sha, resolved_sha,
                input_identity["raw_sha256"], physical_sha, _resource_sample, comm,
            )
            stage_facts["identity_authority"] = {
                "resolved_config_sha256": resolved_sha,
                "input_raw_sha256": input_identity["raw_sha256"],
                "physical_model_sha256": physical_sha,
            }
            marker_times["checkpoints_complete"] = _marker(raw_dir, "checkpoints_complete", expected_sha, {"count": len(stage_facts["checkpoint_facts"])})
        gc.collect()
        retained_ready_sample = _resource_scalars(_resource_sample())
        marker_times["retained_ready"] = _marker(
            raw_dir, "retained_ready", expected_sha,
            {"dwell_seconds": RETAINED_DWELL_SECONDS, "resource": retained_ready_sample},
        )
        time.sleep(RETAINED_DWELL_SECONDS)
        retained_observed_wall_time_ns = time.time_ns()
        retained_sample = _resource_scalars(_resource_sample())
        architecture = _architecture(case, extension, vcycle)
        reserve = stage_facts.get("reserve") if stage == "setup" else None
        factor = architecture["level1_factor"]
        retained_ledger = _route_b_retained_ledger(
            case, extension, vcycle, reserve_object, retained_sample, factor
        )
        resource = {
            "hierarchy_setup_before": hierarchy_setup_before,
            "hierarchy_setup_after": hierarchy_setup_after,
            "retained_ready": retained_ready_sample,
            "retained_observed": retained_sample,
            "retained_observed_wall_time_ns": retained_observed_wall_time_ns,
            "apply": stage_facts.get("apply_facts", []),
        }
        command = canonical_worker_command(raw_dir, record_path, input_path, expected_sha, stage, source_name)
        end_source = _source_identity(root, expected_sha)
        record_marker_names = list(MARKER_NAMES[stage])
        record = {
            "schema": SCHEMA, "stage": stage, "case": CASE, "degree": DEGREE,
            "h_nm": H_NM, "wavelength_nm": WAVELENGTH_NM, "mpi_size": MPI_SIZE,
            "raw_dir": str(raw_dir), "record_path": str(record_path), "command": command,
            "source": {"start": runtime["source"], "end": end_source}, "runtime": runtime,
            "input_identity": input_identity,
            "provenance": {
                "source_sha": expected_sha, "branch": BRANCH,
                "input_identity_sha256": stage_facts["input_identity_sha256"],
                "operator_identity_sha256": stage_facts["operator_identity_sha256"],
                "physical_model_sha256": stage_facts["physical_model_sha256"],
                "resolved_config_sha256": resolved_sha,
            },
            "settings": {
                "levels": [6, 2, 1], "pairs": [[6, 2], [2, 1]],
                "chebyshev_degree": CHEBYSHEV_DEGREE, "power_steps": POWER_STEPS,
                "pre_sweeps": 1, "post_sweeps": 1, "vcycle_count": 1,
                "restart": RESTART, "max_it": MAX_IT,
                "residual_replacement": True, "checkpoint_interval": CHECKPOINT_INTERVAL,
                "cold_rss_limit_bytes": 2_000_000_000,
                "retained_rss_limit_bytes": 1_800_000_000,
                "setup_growth_limit_bytes": SETUP_GROWTH_LIMIT_BYTES,
            },
            "architecture": architecture,
            "reserve": reserve,
            "stage_facts": stage_facts,
            "retained_ledger": retained_ledger,
            "resource": resource,
            "markers": {"relative_dir": "markers", "names": record_marker_names, "wall_time_ns": marker_times},
            "retained_ready_wall_time_ns": marker_times["retained_ready"],
            "retained_observed_wall_time_ns": retained_observed_wall_time_ns,
            "retained_dwell_seconds": RETAINED_DWELL_SECONDS,
            "resource_authority": "external_foundation_watchdog_process_tree",
            "lifecycle": {"destroy_order": [], "normal_closeout": False},
        }
        vcycle.destroy()
        vcycle = None
        marker_times["vcycle_destroyed"] = _marker(
            raw_dir, "vcycle_destroyed", expected_sha, {"destroy_order_index": 1}
        )
        extension = None
        if reserve_object is not None:
            from src.solvers.fullspace_lor_memory_first_foundation import destroy_restart20_reserve
            destroy_restart20_reserve(reserve_object)
            reserve_object = None
            marker_times["reserve_destroyed"] = _marker(
                raw_dir, "reserve_destroyed", expected_sha, {"destroy_order_index": 2}
            )
        case.destroy()
        case = None
        marker_times["foundation_destroyed"] = _marker(
            raw_dir, "foundation_destroyed", expected_sha,
            {"destroy_order_index": 3 if stage == "setup" else 2},
        )
        record["markers"]["wall_time_ns"] = dict(marker_times)
        record["lifecycle"] = {
            "destroy_order": (
                ["vcycle", "reserve", "foundation"]
                if stage == "setup" else ["vcycle", "foundation"]
            ),
            "normal_closeout": True,
            "vcycle_destroyed": True,
            "reserve_destroyed": stage == "setup",
            "foundation_destroyed": True,
        }
        _write_json(record_path, record)
        _marker(raw_dir, "record_written", expected_sha, {"record_path": str(record_path), "record_sha256": _sha256_file(record_path)})
        normal_closeout = True
    finally:
        if not normal_closeout and vcycle is not None:
            vcycle.destroy()
        elif not normal_closeout and extension is not None:
            extension.destroy()
        if not normal_closeout and reserve_object is not None:
            from src.solvers.fullspace_lor_memory_first_foundation import destroy_restart20_reserve
            destroy_restart20_reserve(reserve_object)
            reserve_object = None
        if not normal_closeout and case is not None:
            case.destroy()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=STAGES, required=True)
    parser.add_argument("--case", choices=(CASE,), required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--expected-mpi-size", type=int, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--source", choices=SOURCES)
    args = parser.parse_args(argv)
    run_worker(
        args.raw_dir, args.record, args.input, args.expected_source_sha,
        args.expected_mpi_size, args.stage, args.source,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
