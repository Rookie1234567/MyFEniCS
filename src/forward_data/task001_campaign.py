"""Formal Task001 Hybrid command construction and guarded execution."""

from __future__ import annotations

from dataclasses import asdict
import json
import os
from pathlib import Path
from typing import Any

from .provenance import canonical_hash, source_identity
from .resource_policy import task001_resource_limits
from .schema import Task001ForwardParameters
from .task001_config import task001_config_identity
from .watchdog import WatchdogResult, run_with_watchdog


def task001_hybrid_command(
    parameters: Task001ForwardParameters, *, root: Path, baseline_sha: str,
    output_record: Path, memory_stages: Path,
) -> list[str]:
    parameters.validate()
    fidelity = parameters.fidelity
    return [
        "mpiexec", "-n", str(parameters.mpi_ranks),
        str(root / ".venv" / "bin" / "python"), "-m",
        "benchmarks.run_task032_phase6_augmented",
        "--task001-surrogate-pilot-gate",
        "--task001-model-id", parameters.model_id,
        "--task001-height-nm", f"{parameters.height_nm:g}",
        "--task001-width-x-nm", f"{parameters.width_x_nm:g}",
        "--incident-theta-deg", f"{parameters.theta_deg:g}",
        "--incident-phi-deg", f"{parameters.phi_deg:g}",
        "--polarization-kind", parameters.incident_polarization.lower(),
        "--degree", str(fidelity["degree"]), "--h-nm", f"{fidelity['h_nm']:g}",
        "--modal-degree", str(fidelity["degree"]), "--modal-h-nm", f"{fidelity['h_nm']:g}",
        "--requested-modes", str(fidelity["modes"]),
        "--candidate-modes", str(2 * fidelity["modes"]),
        "--solver-path", "modal-schur-memory-minimal",
        "--stage4-full3d-assembly-backend", "assembly_time_static_condensed",
        "--internal-propagation-model", "full3d_uniform_cg",
        "--internal-traction-model", "scalar_cg_discrete_derivative",
        "--bottom-interface-nm", "10", "--top-interface-nm", "110",
        "--verified-clean-sha", baseline_sha,
        "--memory-stages", str(memory_stages), "--output", str(output_record),
    ]


def formal_preflight(root: Path, baseline_sha: str) -> dict[str, Any]:
    identity = source_identity(root)
    if identity["dirty"]:
        raise RuntimeError("Task001 formal PDE requires a clean source tree")
    if identity["source_sha"] != baseline_sha or len(baseline_sha) != 40:
        raise RuntimeError("Task001 formal PDE baseline SHA mismatch")
    resources = task001_resource_limits(root)
    if not resources["pass"]:
        raise RuntimeError(f"Task001 resource preflight failed: {resources['gates']}")
    return {"source": identity, "resources": resources}


def run_formal_task001_hybrid(
    parameters: Task001ForwardParameters, *, root: Path, baseline_sha: str,
    run_directory: Path, timeout_seconds: float,
) -> tuple[WatchdogResult, Path]:
    preflight = formal_preflight(root, baseline_sha)
    run_directory.mkdir(parents=True, exist_ok=False)
    output_record = run_directory / "solver_record.json"
    memory_stages = run_directory / "memory_stages.jsonl"
    command = task001_hybrid_command(
        parameters, root=root, baseline_sha=baseline_sha,
        output_record=output_record, memory_stages=memory_stages,
    )
    env = {
        **os.environ,
        "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1",
    }
    result = run_with_watchdog(
        command, cwd=root, env=env, output_dir=run_directory / "watchdog",
        timeout_seconds=timeout_seconds,
        memory_limit_bytes=preflight["resources"]["hard_ceiling_bytes"],
        stage_file=memory_stages,
    )
    execution = {
        "schema_version": "task001.execution.v1",
        "parameters": parameters.as_dict(),
        "parameter_hash": canonical_hash(parameters.as_dict()),
        "config_identity": task001_config_identity(parameters),
        "baseline_sha": baseline_sha,
        "preflight": preflight,
        "command": command,
        "watchdog": asdict(result),
        "solver_record_present": output_record.is_file(),
    }
    execution_path = run_directory / "execution.json"
    execution_path.write_text(json.dumps(execution, indent=2, ensure_ascii=False) + "\n")
    return result, execution_path
