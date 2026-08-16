"""Thin, research-only Task39 V3-7 orchestration and explicit worker.

The numerical builders remain in ``src`` and the reviewed Task37b setup and
recovery remain the only production path.  This module only sequences the
identity audit, the side-action microbenchmark, and the exact-side oracle;
The parent entry point delegates process-tree sampling to Task38's launcher;
the ``--worker`` entry point performs one authenticated MPI8 diagnostic and
never creates a global direct factor.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from types import SimpleNamespace
from collections.abc import Callable, Mapping
from typing import Any

from mpi4py import MPI
import numpy as np
from petsc4py import PETSc

from benchmarks.run_task037b_hybrid_iterative import (
    build_frozen_m10_setup,
    collective_heap_cleanup,
    FrozenM10LinearSolve,
    recover_frozen_m10,
    release_frozen_m10_objects,
    run_frozen_m10_physics,
)
from benchmarks.task039_hybrid_direct_identity import (
    compare_v3_7_hybrid_candidate_to_direct,
    compare_v3_7_hybrid_candidate_to_full3d,
    load_task039_direct_solution_inventory,
)
from benchmarks.task039_v3_side_oracle import (
    audit_hybrid_operator_identity,
    build_research_independent_hybrid_reference,
    rebuild_hybrid_augmented_vector,
    run_exact_side_lu_oracle,
)
from src.common.config_3d import ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND
from src.io.input_validation import (
    load_and_resolve,
    simulation_config_3d_from_normalized,
    task039_dynamic_external_mode_inventory,
)
from src.io.execution_plan import ExecutionPlan
from src.runners.task039_hybrid_iterative import (
    make_task039_hybrid_iterative_profile,
)
from src.solvers.hybrid_fem_modal_augmented_direct import (
    HybridAugmentedLayout,
    internal_modal_rhs_correction,
)
from src.solvers.hybrid_fem_modal_iterative import (
    create_hybrid_assembled_block_action,
)
from src.solvers.hybrid_local_dtn_action import (
    create_hybrid_local_dtn_action_components,
)
from src.solvers.hybrid_local_dtn_woodbury import HybridLocalDtnWoodburyFixedAction
from src.solvers.hybrid_whole_endcap_fixed_smoother import (
    build_hybrid_whole_endcap_fixed_smoother_action,
)


V3_7_PROFILE_ID = "task039.v3_7.hybrid_iterative.p6-h5.v1"
V3_7_MAX_IT = 4000
V3_7_ORACLE_MAX_IT = 100
V3_7_RHS_TOLERANCE = 1.0e-10
V3_7_MATRIX_REPEAT_TOLERANCE = V3_7_RHS_TOLERANCE
V3_7_RESIDUAL_TOLERANCE = 5.0e-9
V3_7_WARNING_GIB = 170.0
V3_7_CRITICAL_GIB = 195.0
V3_7_ABSOLUTE_HARD_BYTES = 224_000_000_000
V3_7_POLL_SECONDS = 0.25
V3_7_DIRECT_RUN_ROOT = Path(
    "results/task039_5nm_v3_1deg_s5_hybrid_direct_m480/"
    "task039_v3_hybrid_direct_p6h5_m480_mpi8__hybrid_direct__mpi8__M480/"
    "20260815T111156.797076Z"
)
V3_7_DIRECT_PRODUCER_SHA = "5bfab734a9ca053b69fa1f3f20d907aacbf8b07f"
V3_7_FULL3D_RUN_ROOT = Path(
    "results/task039_5nm_v3_1deg_s5_full3d/"
    "task039_v3_3d_p6h5_full3d_direct_mpi8__full3d_direct__mpi8__Mna/"
    "20260815T055152.423656Z"
)
V3_7_WATCHDOG_AUTH_FLAG = "--launched-by-task038-watchdog"


def _keys(inventory: Mapping[str, Any]) -> set[tuple[str, int, int, str]]:
    result: set[tuple[str, int, int, str]] = set()
    for item in inventory.get("keys", ()):
        if isinstance(item, Mapping):
            result.add(
                (
                    str(item["side"]),
                    int(item["m"]),
                    int(item["n"]),
                    str(item["polarization"]),
                )
            )
    return result


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, complex):
        return [_json_safe(value.real), _json_safe(value.imag)]
    if isinstance(value, np.ndarray):
        return _json_safe(value.tolist())
    if isinstance(value, np.generic):
        return _json_safe(value.item())
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (bool, int, float, str)) or value is None:
        return value
    raise TypeError(f"unsupported V3-7 record value: {type(value).__name__}")


def v3_7_profile_from_resolved(
    resolved_payload: Mapping[str, Any],
) -> Any:
    """Derive the V3 profile from the official 1-degree resolved payload."""

    validate_v3_7_resolved_identity(resolved_payload)
    incidence = resolved_payload["incidence"]
    base = make_task039_hybrid_iterative_profile(480, 8, mesh_target_nm=5.0)
    return replace(
        base,
        profile_id=V3_7_PROFILE_ID,
        record_schema="task039.v3_7.hybrid-iterative-online.v1",
        qualification_schema="task039.v3_7.hybrid-iterative-qualification.v1",
        wavelength_nm=float(incidence["wavelength_nm"]),
        incident_grazing_deg=float(incidence["grazing_angle_deg"]),
        incident_phi_deg=float(incidence["azimuth_deg"]),
        polarization_kind=str(incidence["polarization"]).lower(),
        h_nm=5.0,
        modal_h_nm=5.0,
        requested_modes=480,
        candidate_modes=960,
        max_it=V3_7_MAX_IT,
        rtol=V3_7_RESIDUAL_TOLERANCE,
        assembly_backend=ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND,
        side_residual_correction_steps=2,
    )


def validate_v3_7_resolved_identity(payload: Mapping[str, Any]) -> None:
    """Reject a near-match before any setup or numerical object is created."""

    if payload.get("dimension") != 3:
        raise ValueError("V3-7 requires dimension=3")
    if payload.get("model_id") != "task039_5nm_v3_1deg_s5_hybrid_direct_m480":
        raise ValueError("V3-7 requires the official 1-degree h5 direct model_id")
    incidence = payload.get("incidence")
    discretization = payload.get("discretization")
    boundary = payload.get("boundary")
    method = payload.get("method")
    execution = payload.get("execution")
    if not all(
        isinstance(item, Mapping)
        for item in (incidence, discretization, boundary, method, execution)
    ):
        raise ValueError("V3-7 resolved identity sections are incomplete")
    expected = (
        (incidence["wavelength_nm"], 5.0),
        (incidence["grazing_angle_deg"], 1.0),
        (incidence["azimuth_deg"], 0.0),
        (incidence["polarization"], "s"),
        (discretization["nedelec_degree"], 6),
        (discretization["visualization_degree"], 6),
        (discretization["mesh_target_nm"], 5.0),
        (method["kind"], "hybrid_direct"),
        (method["requested_modes_per_direction"], 480),
        (method["propagation_model"], "full3d_uniform_cg"),
        (method["traction_model"], "full3d_one_cell_exact_schur"),
        (boundary["vertical_boundary"], "dtn_port"),
        (boundary["dtn_order_policy"], "auto_propagating"),
        (boundary["dtn_assembly"], "auxiliary"),
        (boundary["use_pml"], False),
        (execution["mpi_size"], 8),
    )
    if any(actual != value for actual, value in expected):
        raise ValueError("V3-7 official physical/discrete identity is not exact")


def v3_7_watchdog_policy(
    payload: Mapping[str, Any], *, poll_interval_seconds: float = V3_7_POLL_SECONDS
) -> dict[str, Any]:
    """Return the byte-authoritative policy; 195 GiB is telemetry only."""

    execution = payload.get("execution")
    if not isinstance(execution, Mapping):
        raise ValueError("V3-7 watchdog policy requires execution")
    if execution.get("warning_memory_gib") != V3_7_WARNING_GIB:
        raise ValueError("V3-7 warning threshold must be 170 GiB")
    if execution.get("terminate_memory_gib") != V3_7_CRITICAL_GIB:
        raise ValueError("V3-7 195 GiB field must remain the critical checkpoint")
    if execution.get("absolute_terminate_memory_bytes") != V3_7_ABSOLUTE_HARD_BYTES:
        raise ValueError("V3-7 absolute hard stop must be 224000000000 bytes")
    if execution.get("require_zero_swap") is not True:
        raise ValueError("V3-7 requires zero swap")
    if not np.isfinite(float(poll_interval_seconds)) or poll_interval_seconds > 0.25:
        raise ValueError("V3-7 watchdog polling must be <=0.25 seconds")
    return {
        "warning_memory_gib": V3_7_WARNING_GIB,
        "critical_memory_gib": V3_7_CRITICAL_GIB,
        "critical_action": "record_checkpoint_only",
        "absolute_terminate_memory_bytes": V3_7_ABSOLUTE_HARD_BYTES,
        "absolute_hard_stop_action": "terminate_complete_process_tree",
        "require_zero_swap": True,
        "poll_interval_seconds": float(poll_interval_seconds),
        "hard_stop_gib": V3_7_ABSOLUTE_HARD_BYTES / 2**30,
    }


def load_v3_7_official_payload(input_path: str | Path) -> dict[str, Any]:
    """Resolve the official dat without dispatching a worker."""

    specification = load_and_resolve(input_path)
    payload = specification.as_jsonable()
    validate_v3_7_resolved_identity(payload)
    return payload


def build_v3_7_execution_plan(
    input_path: str | Path,
    run_directory: str | Path,
    *,
    source_sha: str,
    python_executable: str | Path | None = None,
    mpiexec_command: str | None = None,
) -> dict[str, Any]:
    """Describe the opt-in worker command consumed by the existing watchdog."""

    payload = load_v3_7_official_payload(input_path)
    policy = v3_7_watchdog_policy(payload)
    executable = str(Path(os.path.abspath(python_executable or sys.executable)))
    mpiexec = mpiexec_command or shutil.which("mpiexec") or "mpiexec"
    argv = [
        str(mpiexec),
        "-n",
        "8",
        executable,
        "-m",
        "benchmarks.task039_v3_7_orchestration",
        "--worker",
        "--input",
        str(Path(input_path).resolve()),
        "--run-directory",
        str(Path(run_directory).resolve()),
        "--source-sha",
        source_sha,
        V3_7_WATCHDOG_AUTH_FLAG,
    ]
    return {
        "argv": argv,
        "shell": False,
        "launcher": "src.runners.task038_launcher",
        "watchdog": policy,
        "worker_contract": {
            "mpi_size": 8,
            "profile_id": V3_7_PROFILE_ID,
            "method": "hybrid_iterative_v3_7_diagnostic",
            "hard_stop_authority": "process_tree_rss_bytes",
            "critical_checkpoint_only": True,
            "swap_policy": "immediate_complete_process_tree_termination",
        },
    }


def v3_7_execution_dry_run(
    input_path: str | Path,
    run_directory: str | Path,
    *,
    source_sha: str,
    python_executable: str | Path | None = None,
) -> dict[str, Any]:
    """Return the non-mutating pre-heavy command and watchdog contract."""

    plan = build_v3_7_execution_plan(
        input_path,
        run_directory,
        source_sha=source_sha,
        python_executable=python_executable,
    )
    argv = plan["argv"]
    if argv[1:3] != ["-n", "8"] or plan["watchdog"]["critical_action"] != (
        "record_checkpoint_only"
    ):
        raise ValueError("V3-7 execution plan is not the fixed MPI8 watchdog contract")
    return plan


def launch_v3_7_with_task038_watchdog(
    input_path: str | Path,
    run_directory: str | Path,
    *,
    source_sha: str,
    python_executable: str | Path | None = None,
    mpiexec_command: str | None = None,
    popen_factory: Callable[..., Any] | None = None,
    sample_factory: Callable[[int], dict[str, Any]] | None = None,
    terminate_factory: Callable[[Any], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run the opt-in child through Task38's existing process-tree watchdog."""

    payload = load_v3_7_official_payload(input_path)
    if not V3_7_DIRECT_RUN_ROOT.is_dir():
        raise ValueError("V3-7 direct producer inventory is unavailable")
    if not callable(compare_v3_7_hybrid_candidate_to_direct):
        raise ValueError("V3-7 integrated checker entry point is unavailable")
    if len(source_sha) != 40 or any(
        character not in "0123456789abcdef" for character in source_sha.lower()
    ):
        raise ValueError("V3-7 source_sha must be a full hexadecimal commit SHA")
    load_v3_7_direct_inventory(payload, V3_7_DIRECT_RUN_ROOT)
    specification = load_and_resolve(input_path)
    plan_payload = build_v3_7_execution_plan(
        input_path,
        run_directory,
        source_sha=source_sha,
        python_executable=python_executable,
        mpiexec_command=mpiexec_command,
    )
    run_dir = Path(run_directory).resolve()
    if run_dir.exists():
        raise ValueError(f"V3-7 run directory already exists: {run_dir}")
    run_dir.mkdir(parents=True)
    from src.runners.task038_launcher import (
        _run_worker,
        _write_bootstrap,
    )
    from benchmarks.watchdog_process_control import terminate_process_tree
    from benchmarks.task034_wsl_resources import resource_authority_sample

    start_time = datetime.now(timezone.utc).isoformat()
    manifest, _ = _write_bootstrap(
        specification,
        run_dir,
        source_sha=source_sha,
        adapter_identity="task039.v3_7_orchestration",
        start_time=start_time,
    )
    executable = Path(os.path.abspath(python_executable or sys.executable))
    argv = tuple(plan_payload["argv"])
    plan = ExecutionPlan(
        argv=argv,
        shell=False,
        executable=executable,
        worker_module="benchmarks.task039_v3_7_orchestration",
        method="hybrid_iterative_v3_7_diagnostic",
        mpi_size=8,
        requested_modes=480,
        physical_model_sha256=specification.physical_model_sha256,
        input_sha256=specification.input_sha256,
        source_sha=source_sha,
        adapter_identity="task039.v3_7_orchestration",
        adapter_available=True,
        contract_probe=False,
        task039_trace_audit=False,
        expected_output_directory=run_dir,
        expected_resolved_config=run_dir / "resolved_config.json",
        expected_manifest=run_dir / "run_manifest.json",
    )
    result = _run_worker(
        plan,
        specification,
        run_dir,
        popen_factory=popen_factory or subprocess.Popen,
        sample_factory=sample_factory or resource_authority_sample,
        terminate_factory=terminate_factory or terminate_process_tree,
        monotonic=time.monotonic,
        sleep=time.sleep,
        poll_interval=V3_7_POLL_SECONDS,
    )
    manifest.update(
        {
            "end_time": datetime.now(timezone.utc).isoformat(),
            "exit_status": result["exit_status"],
            "result_classification": result["result_classification"],
            "status": "finished",
        }
    )
    summary = {
        "status": "finished",
        "run_id": manifest["run_id"],
        "output_directory": str(run_dir),
        "numerical_output_directory": str(run_dir / "numerical_output"),
        **result,
    }
    (run_dir / "run_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (run_dir / "run_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {"run_directory": str(run_dir), **result}


def _load_modal_amplitudes(inventory: Mapping[str, Any]) -> np.ndarray:
    artifact = inventory.get("payload", {}).get("artifact", {})
    path = Path(str(artifact.get("path", ""))).resolve()
    descriptor = inventory.get("payload", {}).get("arrays", {}).get("modal_amplitudes")
    if not path.is_file() or not isinstance(descriptor, Mapping):
        raise ValueError("direct modal amplitude artifact is not hash-bound")
    with np.load(path, allow_pickle=False) as archive:
        values = np.asarray(archive["modal_amplitudes"], dtype=np.complex128).copy()
    digest = hashlib.sha256(np.ascontiguousarray(values).tobytes()).hexdigest()
    if (
        descriptor.get("shape") != list(values.shape)
        or descriptor.get("dtype") != str(values.dtype)
        or descriptor.get("sha256") != digest
        or not np.isfinite(values).all()
    ):
        raise ValueError("direct modal amplitude identity is not exact")
    return values


def load_v3_7_direct_inventory(
    resolved_payload: Mapping[str, Any],
    direct_run_dir: str | Path,
    *,
    producer_source_sha: str = V3_7_DIRECT_PRODUCER_SHA,
) -> tuple[dict[str, Any], np.ndarray]:
    """Load the reviewed direct producer and verify its physical inventory."""

    physical_sha = resolved_payload.get("provenance", {}).get("physical_model_sha256")
    inventory = load_task039_direct_solution_inventory(
        direct_run_dir,
        expected_source_sha=producer_source_sha,
        expected_physical_model_sha256=physical_sha,
    )
    manifest_path = Path(str(direct_run_dir)).resolve() / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        manifest.get("model_id") != "task039_5nm_v3_1deg_s5_hybrid_direct_m480"
        or manifest.get("method") != "hybrid_direct"
        or manifest.get("mpi_size") != 8
    ):
        raise ValueError(
            "direct producer identity is not the fixed V3-7 h5/M480/MPI8 run"
        )
    expected = task039_dynamic_external_mode_inventory(resolved_payload)
    observed = manifest.get("external_mode_inventory")
    if not isinstance(observed, Mapping) or _keys(observed) != _keys(expected):
        raise ValueError("direct producer external mode keys do not match consumer")
    if int(inventory.get("verified_shard_count", 0)) != 32:
        raise ValueError("direct producer canonical inventory must verify 32 shards")
    modal = _load_modal_amplitudes(inventory)
    if modal.shape != (960,):
        raise ValueError("direct modal amplitude count must be 960")
    return {
        "producer_source_sha": producer_source_sha,
        "consumer_source_sha": None,
        "physical_model_sha256": physical_sha,
        "model_id": manifest["model_id"],
        "requested_modes": 480,
        "mpi_size": 8,
        "external_keys_exact": True,
        "verified_shard_count": int(inventory["verified_shard_count"]),
        "inventory": inventory,
    }, modal


def deterministic_global_index_vectors(
    layout: Any, *, seeds: tuple[int, ...] = (739, 743, 751)
) -> dict[str, PETSc.Vec]:
    """Create deterministic vectors from each rank's global ownership range."""

    vectors: dict[str, PETSc.Vec] = {}
    for seed in seeds:
        vector = layout.create_vector()
        first, last = (int(value) for value in vector.getOwnershipRange())
        index = np.arange(first, last, dtype=np.float64)
        vector.getArray()[:] = np.asarray(
            np.sin(index * 0.001 + seed) + 1j * np.cos(index * 0.0007 - seed),
            dtype=PETSc.ScalarType,
        )
        vector.assemble()
        vectors[f"global_index_seed_{seed}"] = vector
    return vectors


def _isolated_vector(layout: Any, block: str) -> PETSc.Vec:
    if block not in {"bottom", "top", "modal"}:
        raise ValueError("isolated block must be bottom, top, or modal")
    vector = layout.create_vector()
    values = np.arange(
        int(vector.getOwnershipRange()[0]),
        int(vector.getOwnershipRange()[1]),
        dtype=np.float64,
    )
    vector.getArray()[:] = 0.0
    target = getattr(layout, f"local_{block}_slice")
    vector.getArray()[target] = np.asarray(
        0.25 + np.sin(values[target] * 0.002), dtype=PETSc.ScalarType
    )
    vector.assemble()
    return vector


def _side_vector_identity(vector: PETSc.Vec, source: str) -> dict[str, Any]:
    values = np.ascontiguousarray(vector.getArray(readonly=True))
    comm = vector.getComm().tompi4py()
    ownership = [int(value) for value in vector.getOwnershipRange()]
    rank_records = comm.allgather(
        {
            "ownership_range": ownership,
            "local_sha256": hashlib.sha256(values.tobytes()).hexdigest(),
        }
    )
    global_sha = hashlib.sha256(
        json.dumps(rank_records, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "source": source,
        "global_size": int(vector.getSize()),
        "ownership_range": ownership,
        "dtype": str(values.dtype),
        "local_sha256": rank_records[comm.rank]["local_sha256"],
        "global_sha256": global_sha,
        "source_norm": float(vector.norm()),
    }


def _short_side_ksp_residual(
    system: Any, rhs: PETSc.Vec, *, max_it: int, source: str
) -> tuple[PETSc.Vec, dict[str, Any]]:
    """Create one explicit ``rhs - A * x`` residual for a side probe."""

    rhs_norm = float(rhs.norm())
    if not np.isfinite(rhs_norm) or rhs_norm <= 1.0e-30:
        raise ValueError("side-KSP probe RHS must be finite and nonzero")
    ksp = PETSc.KSP().create(system.A.getComm())
    solution = system.A.createVecRight()
    residual = system.A.createVecLeft()
    applied = system.A.createVecLeft()
    try:
        ksp.setOperators(system.A)
        ksp.setType("gmres")
        ksp.getPC().setType("none")
        ksp.setInitialGuessNonzero(False)
        ksp.setTolerances(rtol=1.0e-14, atol=0.0, max_it=max_it)
        ksp.solve(rhs, solution)
        iterations = int(ksp.getIterationNumber())
        reason = int(ksp.getConvergedReason())
        if iterations <= 0:
            raise RuntimeError("side GMRES produced no residual iteration")
        expected_nonconverged = int(PETSc.KSP.ConvergedReason.DIVERGED_MAX_IT)
        if reason == 0 or (reason < 0 and reason != expected_nonconverged):
            raise RuntimeError(
                f"side GMRES returned an unexpected failure reason: {reason}"
            )
        system.A.mult(solution, applied)
        rhs.copy(residual)
        residual.axpy(PETSc.ScalarType(-1.0), applied)
        solution_norm = float(solution.norm())
        residual_norm = float(residual.norm())
        if not np.isfinite(solution_norm) or not np.isfinite(residual_norm):
            raise RuntimeError("side GMRES produced a non-finite solution/residual")
        return residual, {
            "source": source,
            "max_it": int(max_it),
            "rhs_source": source,
            "rhs_norm": rhs_norm,
            "solution_norm": solution_norm,
            "explicit_residual_norm": residual_norm,
            "explicit_residual_relative": residual_norm / rhs_norm,
            "residual_source": "explicit_b_minus_Ax",
            "ksp_iterations": iterations,
            "ksp_reason": reason,
            "expected_nonconverged_reason": expected_nonconverged,
        }
    finally:
        applied.destroy()
        solution.destroy()
        ksp.destroy()


def _side_survey_vectors(
    system: Any,
    side: str,
    supplied: Mapping[str, PETSc.Vec] | None,
) -> tuple[dict[str, PETSc.Vec], list[PETSc.Vec], dict[str, Any]]:
    vectors: dict[str, PETSc.Vec] = {"physical_side_rhs": system.b.copy()}
    owned = [vectors["physical_side_rhs"]]
    metadata: dict[str, Any] = {}
    if supplied is not None:
        for label, vector in supplied.items():
            vectors[label] = vector.copy()
            owned.append(vectors[label])
    first, last = (int(value) for value in system.b.getOwnershipRange())
    index = np.arange(first, last, dtype=np.float64)
    for seed in (739, 743, 751, 757):
        vector = system.b.copy()
        vector.getArray()[:] = np.asarray(
            np.sin(index * 0.001 + seed) + 1j * np.cos(index * 0.0007 - seed),
            dtype=PETSc.ScalarType,
        )
        vector.assemble()
        label = f"global_index_seed_{seed}"
        vectors[label] = vector
        owned.append(vector)
    for max_it in (1, 3):
        label = f"early_krylov_residual_it{max_it}"
        probe = vectors["global_index_seed_739"]
        krylov, krylov_meta = _short_side_ksp_residual(
            system,
            probe,
            max_it=max_it,
            source=f"side_unpreconditioned_gmres_it{max_it}",
        )
        krylov_meta["probe_source"] = "global_index_seed_739"
        krylov_meta["probe_identity"] = _side_vector_identity(
            probe, "global_index_seed_739"
        )
        vectors[label] = krylov
        owned.append(krylov)
        metadata[label] = krylov_meta
    metadata["side"] = side
    return vectors, owned, metadata


def _side_correction_probe(
    system: Any,
    action: Any,
    pass_count: int,
    vectors: Mapping[str, PETSc.Vec],
    vector_metadata: Mapping[str, Any],
) -> dict[str, Any]:
    reports: dict[str, Any] = {}
    rho_values: list[float] = []
    for label, source in vectors.items():
        target = system.A.createVecLeft()
        residual = system.A.createVecLeft()
        try:
            action.apply(source, target)
            system.A.mult(target, residual)
            residual.axpy(PETSc.ScalarType(-1.0), source)
            source_norm = float(source.norm())
            residual_norm = float(residual.norm())
            finite = bool(np.isfinite(source_norm) and np.isfinite(residual_norm))
            if source_norm <= 1.0e-30 and finite:
                reports[label] = {
                    "rho": None,
                    "denominator": "max(norm(side_rhs_or_probe),1e-30)",
                    "finite": True,
                    "informative": False,
                    "status": "degenerate_uninformative",
                    "source_norm": source_norm,
                    "residual_norm": residual_norm,
                    "vector": _side_vector_identity(source, label),
                }
            else:
                rho = residual_norm / source_norm if finite else float("nan")
                if np.isfinite(rho):
                    rho_values.append(rho)
                reports[label] = {
                    "rho": float(rho) if np.isfinite(rho) else None,
                    "denominator": "max(norm(side_rhs_or_probe),1e-30)",
                    "finite": bool(np.isfinite(rho)),
                    "informative": bool(np.isfinite(rho)),
                    "status": "measured" if np.isfinite(rho) else "nonfinite",
                    "source_norm": source_norm,
                    "residual_norm": residual_norm,
                    "vector": _side_vector_identity(source, label),
                }
        finally:
            residual.destroy()
            target.destroy()
    complete = len(reports) == len(vectors) and all(
        item["finite"] for item in reports.values()
    )
    informative_labels = [
        label for label, item in reports.items() if item["informative"]
    ]
    excluded_labels = [
        label for label, item in reports.items() if not item["informative"]
    ]
    return {
        "pass": complete,
        "correction_passes": int(pass_count),
        "vectors": reports,
        "vector_inventory": {
            "count": len(reports),
            "sources": sorted(reports),
            "informative_labels": informative_labels,
            "excluded_labels": excluded_labels,
            "informative_count": len(informative_labels),
            "excluded_count": len(excluded_labels),
            "metadata": dict(vector_metadata),
        },
        "rho_summary": {
            "median": float(np.median(rho_values)) if rho_values else None,
            "worst": float(max(rho_values)) if rho_values else None,
            "candidate_A_pass": bool(
                rho_values
                and float(np.median(rho_values)) <= 0.2
                and float(max(rho_values)) <= 0.5
            ),
        },
    }


def run_task039_v3_7_side_correction_survey(
    setup: Any,
    *,
    side_vectors: Mapping[str, Mapping[str, PETSc.Vec]] | None = None,
    stage_callback: Callable[[str, Mapping[str, Any]], None] | None = None,
    marker_callback: Callable[[str, Mapping[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Survey 1/2/4/8 wrappers while retaining one pair at a time."""

    _emit_marker(
        marker_callback,
        "side_fixed_components_setup_begin",
    )
    components = {
        "bottom": create_hybrid_local_dtn_action_components(setup.bottom),
        "top": create_hybrid_local_dtn_action_components(setup.top),
    }
    fixed = {
        "bottom": build_hybrid_whole_endcap_fixed_smoother_action(setup.bottom),
        "top": build_hybrid_whole_endcap_fixed_smoother_action(setup.top),
    }
    _emit_marker(
        marker_callback,
        "side_fixed_components_setup_end",
    )

    try:
        survey_vectors: dict[str, dict[str, PETSc.Vec]] = {}
        owned_vectors: list[PETSc.Vec] = []
        vector_metadata: dict[str, dict[str, Any]] = {}
        for side, system in (("bottom", setup.bottom), ("top", setup.top)):
            supplied = side_vectors.get(side) if side_vectors is not None else None
            survey_vectors[side], owned, vector_metadata[side] = _side_survey_vectors(
                system, side, supplied
            )
            owned_vectors.extend(owned)
        reports: list[dict[str, Any]] = []
        for pass_count in (1, 2, 4, 8):
            _emit_marker(
                marker_callback,
                f"side_correction_{pass_count}_begin",
                correction_passes=pass_count,
            )
            actions = {
                "bottom": HybridLocalDtnWoodburyFixedAction(
                    fixed["bottom"],
                    components["bottom"],
                    residual_operator=(setup.bottom.A if pass_count > 1 else None),
                    residual_correction_steps=pass_count,
                ),
                "top": HybridLocalDtnWoodburyFixedAction(
                    fixed["top"],
                    components["top"],
                    residual_operator=(setup.top.A if pass_count > 1 else None),
                    residual_correction_steps=pass_count,
                ),
            }
            _emit_marker(
                marker_callback,
                f"side_correction_{pass_count}_ready",
                correction_passes=pass_count,
                wrappers_live=2,
            )
            try:
                side_reports = {
                    side: _side_correction_probe(
                        setup.bottom if side == "bottom" else setup.top,
                        action,
                        pass_count,
                        survey_vectors[side],
                        vector_metadata[side],
                    )
                    for side, action in actions.items()
                }
                reports.append(
                    {
                        "correction_passes": pass_count,
                        "bottom": side_reports["bottom"],
                        "top": side_reports["top"],
                        "pass": bool(
                            side_reports["bottom"]["pass"]
                            and side_reports["top"]["pass"]
                        ),
                        "wrappers_live": 2,
                    }
                )
            finally:
                actions["top"].destroy()
                actions["bottom"].destroy()
                _emit_marker(
                    marker_callback,
                    f"side_correction_{pass_count}_end",
                    correction_passes=pass_count,
                    wrappers_live=0,
                )
        return {
            "status": "measured",
            "pass": bool(all(item["pass"] for item in reports)),
            "pass_counts": [item["correction_passes"] for item in reports],
            "sequential": True,
            "max_live_wrapper_count": 2,
            "passes": reports,
        }
    finally:
        for vector in locals().get("owned_vectors", ()):
            vector.destroy()
        fixed["top"].destroy()
        fixed["bottom"].destroy()
        components["top"].destroy()
        components["bottom"].destroy()
        _emit_marker(
            marker_callback,
            "side_survey_cleanup_end",
        )


def run_v3_7_recovery_runner(
    setup: Any,
    layout: Any,
    snapshot: PETSc.Vec,
    run_directory: Path,
    producer: Mapping[str, Any],
) -> dict[str, Any]:
    """Run existing recovery/physics and the reviewed integrated checker."""

    bottom_solution, top_solution, modal_solution = layout.split(
        snapshot,
        setup.bottom.b,
        setup.top.b,
    )
    linear = FrozenM10LinearSolve(
        result=SimpleNamespace(destroy=lambda: None),
        layout=layout,
        bottom_solution=bottom_solution,
        top_solution=top_solution,
        modal_solution=modal_solution,
        linear_pass=True,
        inventory={"source": "v3_7_exact_side_oracle_snapshot"},
        timings={},
        release={"pass": True},
    )
    detail_callback = producer.get("_stage_callback")
    recovery_stage_callback = (
        None
        if detail_callback is None
        else lambda stage: _emit_marker(
            detail_callback, stage, source="recovery_physics"
        )
    )
    recovery = recover_frozen_m10(
        setup,
        linear,
        stage_callback=recovery_stage_callback,
    )
    try:
        physics = run_frozen_m10_physics(
            setup,
            recovery,
            run_directory,
            setup.bottom.local_mesh.mesh.comm,
            stage_callback=recovery_stage_callback,
        )
        _write_v3_7_candidate_authority(
            run_directory,
            physics,
            producer,
            setup.bottom.local_mesh.mesh.comm,
        )
        integrated_checker = check_v3_7_integrated_physics(
            run_directory,
            V3_7_DIRECT_RUN_ROOT,
            V3_7_FULL3D_RUN_ROOT,
        )
        return {
            "pass": bool(physics.physics_pass and integrated_checker["pass"]),
            "producer_source_sha": producer.get("producer_source_sha"),
            "recovery_pass": bool(recovery.recovery_pass),
            "physics_pass": bool(physics.physics_pass),
            "integrated_checker": integrated_checker,
        }
    finally:
        recovery.destroy()


def _write_v3_7_candidate_authority(
    run_directory: Path,
    physics: Any,
    producer: Mapping[str, Any],
    comm: MPI.Intracomm,
) -> Path:
    """Persist the small raw projection consumed by the independent checker."""

    if physics.own_grid is None:
        raise RuntimeError("V3-7 candidate physics did not produce its grid payload")
    orders = list(physics.external_orders)
    keys = [
        {
            "side": row["side"],
            "m": int(row["m"]),
            "n": int(row["n"]),
            "polarization": row["polarization"],
        }
        for row in orders
    ]
    projection = physics.interface_e_projection
    projection_value = float(projection["combined_relative_residual"])
    authority = {
        "schema": "task039.v3-7-hybrid-authority.v1",
        "status": "measured_candidate_physics",
        "model_id": "task039_5nm_v3_1deg_s5_hybrid_iterative_m480",
        "source_sha": producer.get("consumer_source_sha"),
        "physical_model_sha256": producer["physical_model_sha256"],
        "mpi_size": 8,
        "requested_modes": 480,
        "inventory_count": len(keys),
        "external_mode_inventory": {"keys": keys},
        "external_orders": orders,
        "observables": {
            "R_total": physics.energy["R"],
            "T_total": physics.energy["T"],
            "A_balance": physics.energy["A"],
            "A_volume": physics.energy["A_volume"],
        },
        "closure": physics.energy["closure"],
        "traction": {
            side: {"relative_residual": physics.traction[side]["relative_dual"]}
            for side in ("bottom", "top")
        },
        "interface_projection": projection_value,
        "grid_payload": dict(physics.own_grid),
    }
    path = run_directory / "numerical_output" / "v3_7_hybrid_authority.json"
    if comm.rank == 0:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        temporary.write_text(
            json.dumps(_json_safe(authority), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    comm.barrier()
    return path


def check_v3_7_integrated_physics(
    hybrid_run_directory: str | Path,
    direct_run_directory: str | Path,
    full3d_run_directory: str | Path | None = None,
) -> dict[str, Any]:
    """Check candidate physics against Hybrid-direct; Full3D is secondary."""

    candidate = Path(hybrid_run_directory)
    if not (candidate / "numerical_output" / "v3_7_hybrid_authority.json").is_file():
        return {
            "status": "not_available",
            "pass": False,
            "reason": "candidate authority record is not persisted",
        }
    direct = Path(direct_run_directory)
    if not direct.is_dir():
        return {
            "status": "not_available",
            "pass": False,
            "reason": "fixed Hybrid-direct authority is not available",
        }
    try:
        result = compare_v3_7_hybrid_candidate_to_direct(candidate, direct)
    except Exception as exc:
        return {
            "status": "checker_error",
            "pass": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
    secondary: dict[str, Any] | None = None
    if full3d_run_directory is not None:
        full3d = Path(full3d_run_directory)
        if full3d.is_dir():
            try:
                secondary = {
                    "status": "measured",
                    "gate": compare_v3_7_hybrid_candidate_to_full3d(candidate, full3d),
                }
            except Exception as exc:
                secondary = {
                    "status": "checker_error",
                    "pass": False,
                    "error": f"{type(exc).__name__}: {exc}",
                    "role": "secondary_only_not_hybrid_authority",
                }
    return {
        "status": "measured",
        "pass": bool(result.get("pass") is True),
        "classification": result.get("classification"),
        "authority": "fixed_1deg_hybrid_direct",
        "gate": result,
        "full3d_secondary": secondary,
    }


def _default_rhs(setup: Any, layout: Any) -> PETSc.Vec:
    return layout.pack(
        setup.bottom.b,
        setup.top.b,
        internal_modal_rhs_correction(setup.coupling),
    )


def _destroy(value: Any) -> None:
    if value is not None and hasattr(value, "destroy"):
        value.destroy()


def _v3_7_cleanup_callback(
    comm: MPI.Intracomm,
    callback: Callable[[], Mapping[str, Any]] | None,
) -> Callable[[], Mapping[str, Any]]:
    """Use the repository collective heap cleanup for the formal worker."""

    return callback if callback is not None else lambda: collective_heap_cleanup(comm)


def _emit_marker(
    callback: Callable[[str, Mapping[str, Any]], None] | None,
    marker: str,
    **detail: Any,
) -> None:
    if callback is not None:
        callback(marker, detail)


def _v3_7_object_ledger() -> dict[str, Any]:
    names = (
        "setup",
        "qep_matrices",
        "selected_basis",
        "one_cell_factor",
        "lift_columns",
        "apply_columns",
        "bottom_projection",
        "top_projection",
        "independent_reference",
        "side_base_ilu",
        "correction_wrappers",
        "exact_side_action",
        "exact_side_factors",
        "solution_snapshot",
        "recovery_physics",
    )
    return {
        "schema": "task039.v3-7-memory-object-ledger.v1",
        "status": "in_progress",
        "capacity_semantics": "known capacities only; unknown is not_available",
        "objects": {
            name: {
                "created": False,
                "completed": False,
                "destroyed": False,
                "status": "not_available",
                "capacity_bytes": "not_available",
                "classification": "lifecycle_marker",
            }
            for name in names
        },
        "events": [],
    }


def _write_v3_7_object_ledger(
    path: Path,
    ledger: Mapping[str, Any],
    comm: MPI.Intracomm,
    *,
    synchronize: bool = True,
) -> None:
    if comm.rank == 0:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        temporary.write_text(
            json.dumps(_json_safe(dict(ledger)), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    if synchronize:
        comm.barrier()


def _write_v3_7_identity_checkpoint(
    run_directory: Path,
    *,
    source_sha: str,
    producer: Mapping[str, Any],
    identity: Mapping[str, Any],
    comm: MPI.Intracomm,
) -> Path:
    """Persist the completed identity audit before the next stage can fail."""

    path = run_directory / "numerical_output" / "v3_7_identity_checkpoint.json"
    checkpoint = {
        "schema": "task039.v3-7-identity-checkpoint.v1",
        "source_sha": source_sha,
        "physical_identity": {
            "producer_source_sha": producer.get("producer_source_sha"),
            "physical_model_sha256": producer.get("physical_model_sha256"),
            "model_id": producer.get("model_id"),
            "requested_modes": producer.get("requested_modes"),
            "mpi_size": producer.get("mpi_size"),
            "external_keys_exact": producer.get("external_keys_exact"),
        },
        "pass": bool(identity.get("pass") is True),
        "relative_limit": V3_7_RHS_TOLERANCE,
        "vector_count": identity.get("vector_count"),
        "vectors": identity.get("vectors", {}),
        "rhs_equality": identity.get("rhs_equality", {}),
        "coupling_isolation": identity.get("coupling_isolation", {}),
        "direct_solution_residual": identity.get("direct_solution_residual"),
    }
    if comm.rank == 0:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        temporary.write_text(
            json.dumps(_json_safe(checkpoint), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    comm.barrier()
    return path


def _write_v3_7_side_survey_checkpoint(
    run_directory: Path,
    *,
    source_sha: str,
    producer: Mapping[str, Any],
    correction: Mapping[str, Any],
    comm: MPI.Intracomm,
) -> Path:
    """Persist the completed side survey before exact-oracle construction."""

    path = run_directory / "numerical_output" / "v3_7_side_survey_checkpoint.json"
    passes = []
    for item in correction.get("passes", ()):
        side_reports = {}
        for side in ("bottom", "top"):
            report = item.get(side, {})
            inventory = report.get("vector_inventory", {})
            summary = report.get("rho_summary", {})
            side_reports[side] = {
                "informative_labels": list(inventory.get("informative_labels", ())),
                "excluded_labels": list(inventory.get("excluded_labels", ())),
                "informative_count": inventory.get("informative_count"),
                "excluded_count": inventory.get("excluded_count"),
                "median": summary.get("median"),
                "worst": summary.get("worst"),
                "candidate_A_pass": summary.get("candidate_A_pass"),
            }
        passes.append(
            {
                "correction_passes": item.get("correction_passes"),
                "pass": item.get("pass"),
                **side_reports,
            }
        )
    checkpoint = {
        "schema": "task039.v3-7-side-survey-checkpoint.v1",
        "source_sha": source_sha,
        "physical_identity": {
            "producer_source_sha": producer.get("producer_source_sha"),
            "consumer_source_sha": producer.get("consumer_source_sha"),
            "physical_model_sha256": producer.get("physical_model_sha256"),
            "model_id": producer.get("model_id"),
            "requested_modes": producer.get("requested_modes"),
            "mpi_size": producer.get("mpi_size"),
            "external_keys_exact": producer.get("external_keys_exact"),
        },
        "survey_status": correction.get("status"),
        "survey_pass": correction.get("pass"),
        "passes": passes,
    }
    if comm.rank == 0:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        temporary.write_text(
            json.dumps(_json_safe(checkpoint), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    comm.barrier()
    return path


def _record_v3_7_marker(
    ledger: dict[str, Any], marker: str, detail: Mapping[str, Any]
) -> None:
    """Record only lifecycle facts represented by an actual marker."""

    ledger["events"].append(
        {
            "marker": marker,
            "detail_keys": sorted(str(key) for key in detail),
        }
    )
    objects = ledger["objects"]

    def mark(name: str, *, created=False, completed=False, destroyed=False) -> None:
        item = objects[name]
        if created:
            item["created"] = True
            item["status"] = "measured"
        if completed:
            item["completed"] = True
        if destroyed:
            item["destroyed"] = True

    if marker == "identity_reference_materialization_end":
        mark("independent_reference", created=True, completed=True)
    elif marker == "borrowed_reference_cleanup_end":
        mark("independent_reference", destroyed=True)
    elif marker == "side_fixed_components_setup_end":
        mark("side_base_ilu", created=True, completed=True)
    elif marker.startswith("side_correction_") and marker.endswith("_ready"):
        mark("correction_wrappers", created=True, completed=True)
    elif marker.startswith("side_correction_") and marker.endswith("_end"):
        mark("correction_wrappers", destroyed=True)
    elif marker == "side_survey_cleanup_end":
        if objects["side_base_ilu"]["created"]:
            mark("side_base_ilu", destroyed=True)
    elif marker == "exact_side_oracle_begin":
        mark("exact_side_action", created=True)
    elif marker == "exact_side_oracle_end":
        mark("exact_side_action", completed=True, destroyed=True)
    elif marker == "solution_snapshot_created":
        mark("solution_snapshot", created=True, completed=True)
    elif marker == "solution_snapshot_destroyed":
        mark("solution_snapshot", destroyed=True)
    elif marker == "recovery_physics_begin":
        mark("recovery_physics", created=True)
    elif marker == "recovery_physics_end":
        mark("recovery_physics", completed=True, destroyed=True)

    if marker in {"qep_matrices_ready", "qep_matrices_complete"}:
        mark("qep_matrices", created=True, completed=True)
    elif marker in {
        "modal_qep_temporaries_released",
        "selected_biorthogonal_bases_released",
        "final_cleanup",
    }:
        mark("qep_matrices", destroyed=True)
        if marker != "final_cleanup":
            mark("selected_basis", destroyed=True)
    if marker == "selected_biorthogonal_bases_ready":
        mark("selected_basis", created=True, completed=True)
    if marker == "one_cell_factor_ready":
        mark("one_cell_factor", created=True, completed=True)
    elif marker == "one_cell_factor_destroyed":
        mark("one_cell_factor", destroyed=True)
        for name in (
            "lift_columns",
            "apply_columns",
            "bottom_projection",
            "top_projection",
        ):
            if objects[name]["created"]:
                mark(name, destroyed=True)

    for token, name in (
        ("lift_columns", "lift_columns"),
        ("apply_columns", "apply_columns"),
        ("bottom_projection", "bottom_projection"),
        ("top_projection", "top_projection"),
    ):
        if token in marker:
            mark(name, created=True)
            if marker.endswith(("_end", "_complete", "_ready")):
                mark(name, completed=True)


def run_v3_7_stage_sequence(
    *,
    identity_stage: Callable[[], Mapping[str, Any]],
    correction_stage: Callable[[], Mapping[str, Any]],
    oracle_stage: Callable[
        [Callable[[Any, Mapping[str, Any]], None]], Mapping[str, Any]
    ],
    snapshotter: Callable[[Any], Any] | None = None,
    recovery_runner: Callable[[Any], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Enforce identity -> side survey -> oracle and handoff ordering."""

    identity = dict(identity_stage())
    if identity.get("pass") is not True:
        return {
            "status": "controlled_stop_identity_failure",
            "identity": identity,
            "correction": {"status": "not_run"},
            "oracle": {"status": "not_run"},
            "solution_handoff": "not_run",
        }
    correction = dict(correction_stage())
    if correction.get("pass", True) is not True:
        return {
            "status": "controlled_stop_side_correction_failure",
            "identity": identity,
            "correction": correction,
            "oracle": {"status": "not_run"},
            "solution_handoff": "not_run",
        }
    snapshot_holder: dict[str, Any] = {}

    def consume(solution: Any, report: Mapping[str, Any]) -> None:
        if snapshotter is None:
            snapshot_holder["snapshot"] = None
            return
        snapshot_holder["snapshot"] = snapshotter(solution)
        snapshot_holder["source"] = "oracle_result.solution_duplicate"
        snapshot_holder["oracle_pass"] = bool(report.get("pass"))

    oracle = dict(oracle_stage(consume))
    handoff = "not_run"
    recovery_result: Mapping[str, Any] | None = None
    if oracle.get("pass") is True and "snapshot" in snapshot_holder:
        if recovery_runner is not None:
            recovery_result = recovery_runner(snapshot_holder["snapshot"])
            if not isinstance(recovery_result, Mapping):
                handoff = "recovery_result_invalid"
            elif recovery_result.get("pass") is True:
                handoff = "recovery_after_oracle_cleanup"
            else:
                handoff = "recovery_or_physics_failed"
        else:
            handoff = "snapshot_created_no_recovery_requested"
    elif oracle.get("pass") is not True:
        handoff = "not_run_oracle_failed"
    status = "oracle_failed"
    if oracle.get("pass") is True:
        if recovery_runner is None:
            status = "recovery_callback_required"
        elif (
            isinstance(recovery_result, Mapping) and recovery_result.get("pass") is True
        ):
            status = "completed"
        else:
            status = "oracle_linear_pass_physics_fail"
    return {
        "status": status,
        "identity": identity,
        "correction": correction,
        "oracle": oracle,
        "recovery": recovery_result,
        "solution_handoff": handoff,
    }


def run_task039_v3_7_diagnostic(
    resolved_payload: Mapping[str, Any],
    run_directory: str | Path,
    *,
    source_sha: str,
    direct_run_dir: str | Path = V3_7_DIRECT_RUN_ROOT,
    comm: MPI.Intracomm = MPI.COMM_WORLD,
    setup_builder: Callable[..., Any] = build_frozen_m10_setup,
    inventory_loader: Callable[
        ..., tuple[dict[str, Any], np.ndarray]
    ] = load_v3_7_direct_inventory,
    reference_builder: Callable[..., Any] = build_research_independent_hybrid_reference,
    identity_runner: Callable[..., Mapping[str, Any]] = audit_hybrid_operator_identity,
    correction_runner: Callable[..., Mapping[str, Any]] | None = None,
    oracle_runner: Callable[..., Mapping[str, Any]] = run_exact_side_lu_oracle,
    stage_callback: Callable[[str, Mapping[str, Any]], None] | None = None,
    post_destroy_cleanup: Callable[[], Mapping[str, Any]] | None = None,
    recovery_runner: Callable[
        [Any, Any, Any, Path, Mapping[str, Any]], Mapping[str, Any]
    ]
    | None = None,
    record_path: str | Path | None = None,
) -> dict[str, Any]:
    """Prepare one V3-7 diagnostic campaign; never dispatches MPI itself."""

    setup = None
    reference_holder: dict[str, Any] = {}
    survey_side_vectors: dict[str, dict[str, PETSc.Vec]] = {}
    marker_path = (
        Path(run_directory).resolve()
        / "numerical_output"
        / "memory_stage_markers.raw.jsonl"
    )
    marker_started = time.perf_counter()
    marker_stream = None
    object_ledger_path = (
        Path(run_directory).resolve() / "numerical_output" / "memory_object_ledger.json"
    )
    object_ledger = _v3_7_object_ledger()
    normal_return = False
    exception_raised = False
    result: dict[str, Any] | None = None
    profile = None
    watchdog = None
    producer = None
    modal_amplitudes = None
    cfg = None
    modal_cfg = None
    side_checkpoint_path: Path | None = None
    if comm.rank == 0:
        marker_path.parent.mkdir(parents=True, exist_ok=True)
        marker_stream = marker_path.open("a", encoding="utf-8")
    _write_v3_7_object_ledger(object_ledger_path, object_ledger, comm)

    def marker_callback(marker: str, detail: Mapping[str, Any]) -> None:
        if comm.rank == 0:
            _record_v3_7_marker(object_ledger, marker, detail)
            _write_v3_7_object_ledger(
                object_ledger_path,
                object_ledger,
                comm,
                synchronize=False,
            )
        if marker_stream is None:
            return
        marker_stream.write(
            json.dumps(
                _json_safe(
                    {
                        "schema": "task039.v3-7-detail-marker.v1",
                        "stage": marker,
                        "marker": marker,
                        "elapsed_seconds": time.perf_counter() - marker_started,
                        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                        "worker_elapsed_seconds": time.perf_counter() - marker_started,
                        "elapsed_origin": "v3_7_worker_perf_counter_start",
                        "detail": {"v3_7_marker": marker, **dict(detail)},
                    }
                ),
                ensure_ascii=False,
            )
            + "\n"
        )
        marker_stream.flush()

    def combined_detail_callback(stage: str, detail: Mapping[str, Any]) -> None:
        if stage_callback is not None:
            stage_callback(stage, detail)
        marker_callback(stage, {"source": "setup_detail_callback", **dict(detail)})

    try:
        _emit_marker(marker_callback, "diagnostic_entry")
        profile = v3_7_profile_from_resolved(resolved_payload)
        _emit_marker(marker_callback, "profile_ready", profile_id=profile.profile_id)
        watchdog = v3_7_watchdog_policy(resolved_payload)
        _emit_marker(
            marker_callback,
            "watchdog_ready",
            absolute_terminate_memory_bytes=V3_7_ABSOLUTE_HARD_BYTES,
        )
        if recovery_runner is None:
            raise ValueError(
                "V3-7 requires an injected recovery_runner(setup, layout, snapshot, "
                "run_dir, producer)"
            )
        producer, modal_amplitudes = inventory_loader(
            resolved_payload,
            direct_run_dir,
        )
        producer["consumer_source_sha"] = source_sha
        _emit_marker(
            marker_callback,
            "inventory_ready",
            producer_source_sha=producer.get("producer_source_sha"),
        )
        cfg = simulation_config_3d_from_normalized(resolved_payload)
        modal_cfg = deepcopy(cfg)
        _emit_marker(marker_callback, "config_ready")
        producer["_stage_callback"] = marker_callback
        _emit_marker(marker_callback, "setup_begin")
        setup = setup_builder(
            comm,
            profile=profile,
            exact_one_cell_work_dir=(
                Path(run_directory).resolve() / "numerical_output" / "exact_one_cell"
            ),
            cfg_override=cfg,
            modal_cfg_override=modal_cfg,
            detail_stage_callback=combined_detail_callback,
            post_destroy_cleanup=_v3_7_cleanup_callback(comm, post_destroy_cleanup),
        )
        object_ledger["objects"]["setup"]["created"] = True
        object_ledger["objects"]["setup"]["status"] = "measured"
        layout = HybridAugmentedLayout.build(
            setup.bottom,
            setup.top,
            setup.coupling.internal_unknown_count,
        )
        rhs = _default_rhs(setup, layout)

        def identity_stage() -> Mapping[str, Any]:
            production_operator, production_context = (
                create_hybrid_assembled_block_action(
                    setup.bottom, setup.top, setup.coupling
                )
            )
            vectors: dict[str, PETSc.Vec] = {}
            isolated: dict[str, PETSc.Vec] = {}
            reference_rhs = None
            x_star = None
            try:
                reference = reference_holder.get("reference")
                if reference is None:
                    _emit_marker(
                        marker_callback,
                        "identity_reference_materialization_begin",
                    )
                    reference = reference_builder(
                        setup.bottom, setup.top, setup.coupling
                    )
                    reference_holder["reference"] = reference
                    _emit_marker(
                        marker_callback,
                        "identity_reference_materialization_end",
                    )
                reference_rhs = layout.pack(
                    reference.bottom.b,
                    reference.top.b,
                    internal_modal_rhs_correction(setup.coupling),
                )
                vectors.update(deterministic_global_index_vectors(layout))
                vectors["physical_rhs"] = rhs
                x_star = rebuild_hybrid_augmented_vector(
                    producer["inventory"],
                    setup.bottom,
                    setup.top,
                    layout,
                    modal_amplitudes,
                )[0]
                vectors["direct_solution_x_star"] = x_star
                direct_residual = production_operator.createVecLeft()
                production_operator.mult(x_star, direct_residual)
                direct_residual.scale(PETSc.ScalarType(-1.0))
                direct_residual.axpy(PETSc.ScalarType(1.0), rhs)
                vectors["direct_solution_derived_residual"] = direct_residual
                for side, system, block_slice in (
                    ("bottom", setup.bottom, layout.local_bottom_slice),
                    ("top", setup.top, layout.local_top_slice),
                ):
                    side_residual = system.A.createVecLeft()
                    side_values = side_residual.getArray()
                    global_values = direct_residual.getArray(readonly=True)[block_slice]
                    if side_values.size != global_values.size:
                        side_residual.destroy()
                        raise ValueError(
                            f"{side} direct residual ownership does not match layout"
                        )
                    side_values[:] = global_values
                    side_residual.assemble()
                    survey_side_vectors.setdefault(side, {})[
                        "direct_solution_side_residual"
                    ] = side_residual
                for block in ("bottom", "top", "modal"):
                    isolated[f"{block}_only"] = _isolated_vector(layout, block)
                result = dict(
                    identity_runner(
                        reference.operator,
                        production_operator,
                        layout,
                        vectors,
                        rhs_pairs={"physical_rhs": (rhs, reference_rhs)},
                        isolated_vectors=isolated,
                        relative_limit=V3_7_RHS_TOLERANCE,
                    )
                )
                result["direct_solution_residual"] = {
                    "relative_error": float(direct_residual.norm())
                    / max(float(rhs.norm()), 1.0e-30),
                    "denominator": "max(norm(physical_rhs),1e-30)",
                    "source": "canonical direct payload reconstructed on current layout",
                }
                identity_checkpoint = _write_v3_7_identity_checkpoint(
                    Path(run_directory).resolve(),
                    source_sha=source_sha,
                    producer=producer,
                    identity=result,
                    comm=comm,
                )
                _emit_marker(
                    marker_callback,
                    "identity_audit_complete",
                    path=str(
                        identity_checkpoint.relative_to(Path(run_directory).resolve())
                    ),
                    **{"pass": bool(result.get("pass") is True)},
                )
                return result
            finally:
                for vector in isolated.values():
                    _destroy(vector)
                for label, vector in vectors.items():
                    if vector is not rhs and vector is not x_star:
                        _destroy(vector)
                _destroy(x_star)
                _destroy(reference_rhs)
                production_context.destroy()
                production_operator.destroy()

        def correction_stage() -> Mapping[str, Any]:
            nonlocal side_checkpoint_path
            if correction_runner is not None:
                correction = correction_runner(setup, stage_callback=stage_callback)
            else:
                correction = run_task039_v3_7_side_correction_survey(
                    setup,
                    side_vectors=survey_side_vectors,
                    stage_callback=stage_callback,
                    marker_callback=marker_callback,
                )
            side_checkpoint_path = _write_v3_7_side_survey_checkpoint(
                Path(run_directory).resolve(),
                source_sha=source_sha,
                producer=producer,
                correction=correction,
                comm=comm,
            )
            return correction

        def oracle_stage(
            consumer: Callable[[Any, Mapping[str, Any]], None],
        ) -> Mapping[str, Any]:
            _emit_marker(
                marker_callback,
                "exact_side_oracle_begin",
            )
            report = dict(
                oracle_runner(
                    layout,
                    setup.bottom,
                    setup.top,
                    setup.coupling,
                    rhs,
                    reference=reference_holder["reference"],
                    max_it=V3_7_ORACLE_MAX_IT,
                    restart=90,
                    threshold=V3_7_RESIDUAL_TOLERANCE,
                    matrix_repeat_tolerance=V3_7_MATRIX_REPEAT_TOLERANCE,
                    solution_consumer=consumer,
                )
            )
            _emit_marker(
                marker_callback,
                "exact_side_oracle_end",
                numerical_pass=report.get("numerical_pass"),
                inventory_pass=report.get("inventory_pass"),
            )
            borrowed_reference = reference_holder.pop("reference")
            borrowed_reference.destroy()
            _emit_marker(
                marker_callback,
                "borrowed_reference_cleanup_end",
            )
            report["borrowed_reference_cleanup"] = {
                "destroyed_by_caller": True,
                "before_recovery_consumer": True,
            }
            return report

        snapshot: dict[str, Any] = {}

        def snapshotter(solution: Any) -> Any:
            duplicate = solution.duplicate()
            solution.copy(duplicate)
            snapshot["vector"] = duplicate
            _emit_marker(marker_callback, "solution_snapshot_created")
            return duplicate

        def recovery_consumer(snapshot: PETSc.Vec) -> Mapping[str, Any]:
            _emit_marker(marker_callback, "recovery_physics_begin")
            report = recovery_runner(
                setup,
                layout,
                snapshot,
                Path(run_directory).resolve(),
                producer,
            )
            _emit_marker(marker_callback, "recovery_physics_end")
            return report

        sequence = run_v3_7_stage_sequence(
            identity_stage=identity_stage,
            correction_stage=correction_stage,
            oracle_stage=oracle_stage,
            snapshotter=snapshotter,
            recovery_runner=recovery_consumer,
        )
        oracle_lifecycle = sequence.get("oracle", {}).get("lifecycle", {})
        oracle_inventory = sequence.get("oracle", {}).get("inventory", {})
        if oracle_lifecycle:
            action = object_ledger["objects"]["exact_side_action"]
            action.update(
                {
                    "created": True,
                    "completed": True,
                    "destroyed": bool(
                        oracle_lifecycle.get("bottom_action_destroyed")
                        and oracle_lifecycle.get("top_action_destroyed")
                    ),
                    "status": "measured",
                }
            )
            if (
                oracle_inventory.get("bottom_direct_factor_count") == 1
                and oracle_inventory.get("top_direct_factor_count") == 1
            ):
                object_ledger["objects"]["exact_side_factors"].update(
                    {
                        "created": True,
                        "completed": True,
                        "destroyed": bool(
                            oracle_lifecycle.get("bottom_action_destroyed")
                            and oracle_lifecycle.get("top_action_destroyed")
                        ),
                        "status": "measured",
                    }
                )
        if "vector" in snapshot:
            object_ledger["objects"]["solution_snapshot"]["created"] = True
        if "vector" in snapshot:
            _destroy(snapshot["vector"])
            object_ledger["objects"]["solution_snapshot"]["destroyed"] = True
            _emit_marker(marker_callback, "solution_snapshot_destroyed")
        result = {
            "schema": "task039.v3_7-thin-orchestration.v1",
            "status": sequence["status"],
            "source_identity": {
                "consumer_source_sha": source_sha,
                "producer_source_sha": producer["producer_source_sha"],
                "physical_model_sha256": producer["physical_model_sha256"],
                "model_id": producer["model_id"],
                "requested_modes": producer["requested_modes"],
                "mpi_size": producer["mpi_size"],
                "external_keys_exact": producer["external_keys_exact"],
            },
            "profile": {
                "profile_id": profile.profile_id,
                "incident_grazing_deg": profile.incident_grazing_deg,
                "incident_phi_deg": profile.incident_phi_deg,
                "h_nm": profile.h_nm,
                "requested_modes": profile.requested_modes,
                "candidate_modes": profile.candidate_modes,
                "max_it": profile.max_it,
                "oracle_max_it": V3_7_ORACLE_MAX_IT,
                "matrix_repeat_tolerance": V3_7_MATRIX_REPEAT_TOLERANCE,
            },
            "qep_basis_audit": getattr(setup, "qep_audit", {}),
            "watchdog": watchdog,
            "telemetry": {
                "process_tree_samples": {
                    "path": "numerical_output/process_tree_samples.jsonl",
                    "writer": "parent_task038_launcher",
                    "status": "expected_from_parent_launcher",
                },
                "memory_stages": {
                    "path": "numerical_output/memory_stages.jsonl",
                    "writer": "parent_task038_launcher_marker_alignment",
                    "status": "expected_from_parent_launcher",
                },
                "memory_stage_markers": {
                    "path": "numerical_output/memory_stage_markers.raw.jsonl",
                    "writer": "v3_7_worker",
                    "status": "measured_worker_marker_stream",
                },
                "memory_object_ledger": {
                    "path": "numerical_output/memory_object_ledger.json",
                    "schema": object_ledger["schema"],
                    "status": "finalized_in_worker_finalizer",
                },
                "side_survey_checkpoint": {
                    "path": (
                        str(
                            side_checkpoint_path.relative_to(
                                Path(run_directory).resolve()
                            )
                        )
                        if side_checkpoint_path is not None
                        else "not_available"
                    ),
                    "status": (
                        "written_before_oracle"
                        if side_checkpoint_path is not None
                        else "not_available"
                    ),
                },
                "stage_callback_connected": stage_callback is not None,
            },
            "sequence": sequence,
            "formal_run": {
                "status": sequence["status"],
                "classification": "measured_v3_7_diagnostic",
            },
            "run_directory": str(Path(run_directory).resolve()),
        }
        normal_return = sequence["status"] == "completed"
        return result
    finally:
        if marker_stream is not None:
            marker_stream.close()
        _destroy(rhs) if "rhs" in locals() else None
        for side_vectors in survey_side_vectors.values():
            for vector in side_vectors.values():
                vector.destroy()
        if reference_holder.get("reference") is not None:
            reference_holder["reference"].destroy()
            if object_ledger["objects"]["independent_reference"]["created"]:
                object_ledger["objects"]["independent_reference"]["destroyed"] = True
        try:
            if setup is not None:
                release_frozen_m10_objects(setup, None, comm)
                object_ledger["objects"]["setup"]["destroyed"] = True
                object_ledger["objects"]["setup"]["completed"] = True
        except Exception:
            exception_raised = True
            raise
        finally:
            if exception_raised:
                object_ledger["status"] = "exception"
            elif normal_return:
                object_ledger["status"] = "completed"
            elif result is not None:
                object_ledger["status"] = "controlled_stop"
            else:
                object_ledger["status"] = "exception"
            for item in object_ledger["objects"].values():
                if item["created"]:
                    item["status"] = "measured"
                elif item["status"] == "not_available":
                    item["status"] = "not_available"
            _write_v3_7_object_ledger(object_ledger_path, object_ledger, comm)
            if result is not None:
                ledger_digest = hashlib.sha256(
                    object_ledger_path.read_bytes()
                ).hexdigest()
                result["telemetry"]["memory_object_ledger"].update(
                    {
                        "status": object_ledger["status"],
                        "sha256": ledger_digest,
                    }
                )
                if record_path is not None and comm.rank == 0:
                    path = Path(record_path)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
                    temporary.write_text(
                        json.dumps(_json_safe(result), ensure_ascii=False, indent=2)
                        + "\n",
                        encoding="utf-8",
                    )
                    temporary.replace(path)
                if record_path is not None:
                    comm.barrier()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--launched-by-task038-watchdog", action="store_true")
    parser.add_argument("--input", required=True, dest="input_path")
    parser.add_argument("--run-directory", required=True)
    parser.add_argument("--source-sha", required=True)
    args = parser.parse_args(argv)
    if args.worker == args.dry_run:
        parser.error("choose exactly one of --worker or --dry-run")
    if args.dry_run:
        plan = v3_7_execution_dry_run(
            args.input_path,
            args.run_directory,
            source_sha=args.source_sha,
        )
        print(json.dumps(_json_safe(plan), ensure_ascii=False, sort_keys=True))
        return 0
    if not args.launched_by_task038_watchdog:
        print(
            "V3-7 worker requires --launched-by-task038-watchdog",
            file=sys.stderr,
        )
        return 2
    if MPI.COMM_WORLD.size != 8:
        print(
            f"V3-7 worker requires MPI8, got MPI{MPI.COMM_WORLD.size}",
            file=sys.stderr,
        )
        return 2
    try:
        payload = load_v3_7_official_payload(args.input_path)
        result = run_task039_v3_7_diagnostic(
            payload,
            args.run_directory,
            source_sha=args.source_sha,
            direct_run_dir=V3_7_DIRECT_RUN_ROOT,
            recovery_runner=run_v3_7_recovery_runner,
            record_path=(
                Path(args.run_directory).resolve()
                / "numerical_output"
                / "v3_v7_diagnostic.json"
            ),
        )
    except Exception as exc:
        print(
            f"V3-7 worker failed before completion: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 2
    print(json.dumps(_json_safe(result), ensure_ascii=False, sort_keys=True))
    return 0 if result.get("status") == "completed" else 3


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "V3_7_ABSOLUTE_HARD_BYTES",
    "V3_7_DIRECT_PRODUCER_SHA",
    "V3_7_DIRECT_RUN_ROOT",
    "V3_7_MAX_IT",
    "V3_7_MATRIX_REPEAT_TOLERANCE",
    "V3_7_PROFILE_ID",
    "build_v3_7_execution_plan",
    "check_v3_7_integrated_physics",
    "compare_v3_7_hybrid_candidate_to_direct",
    "deterministic_global_index_vectors",
    "load_v3_7_direct_inventory",
    "load_v3_7_official_payload",
    "run_task039_v3_7_side_correction_survey",
    "run_task039_v3_7_diagnostic",
    "run_v3_7_recovery_runner",
    "run_v3_7_stage_sequence",
    "v3_7_execution_dry_run",
    "launch_v3_7_with_task038_watchdog",
    "v3_7_profile_from_resolved",
    "v3_7_watchdog_policy",
    "validate_v3_7_resolved_identity",
]
