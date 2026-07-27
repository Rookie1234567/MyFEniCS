"""Thin subprocess adapter around the tracked authoritative runner."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any
import uuid

from .provenance import canonical_hash, file_hash, source_identity
from .schema import (
    ForwardParameters,
    OBSERVABLE_SCHEMA_VERSION,
    RunConfig,
)


ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class ForwardResult:
    status: str
    run_directory: Path
    observables: dict[str, Any]
    manifest_path: Path
    return_code: int


def _abi_identity(root: Path) -> dict[str, Any]:
    import numpy as np
    from petsc4py import PETSc
    import dolfinx
    import dolfinx_mpc

    python = Path(sys.executable).absolute()
    expected_venv = (root / ".venv").resolve()
    mpc_path = Path(dolfinx_mpc.__file__).resolve()
    path_parts = os.environ.get("PATH", "").split(":")
    checks = {
        "project_venv_python": (
            python.is_relative_to(expected_venv)
            and Path(sys.prefix).resolve() == expected_venv
        ),
        "complex128": np.dtype(PETSc.ScalarType) == np.dtype(np.complex128),
        "project_venv_mpc": mpc_path.is_relative_to(expected_venv),
        "linux_only_path": not any(item.startswith("/mnt/") for item in path_parts),
        "qualified_activation": os.environ.get(
            "_MYFENICS_SURROGATE_WSL_QUALIFIED_ACTIVATION"
        ) == "1",
    }
    if not all(checks.values()):
        raise RuntimeError(f"ABI preflight failed: {checks}")
    return {
        "checks": checks,
        "python": str(python),
        "petsc_scalar": str(np.dtype(PETSc.ScalarType)),
        "petsc_int_bits": np.dtype(PETSc.IntType).itemsize * 8,
        "dolfinx_version": dolfinx.__version__,
        "dolfinx_mpc_path": str(mpc_path),
    }


def _resource_identity(root: Path, model_id: str) -> dict[str, Any]:
    meminfo: dict[str, int] = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, value = line.split(":", 1)
        meminfo[key] = int(value.strip().split()[0]) * 1024
    disk = shutil.disk_usage(root)
    minimum_available = {
        "euv_2d_complex_absorption_v1": 2 * 1024**3,
        "euv_3d_target_grating_v1": 10 * 1024**3,
    }[model_id]
    available = meminfo["MemAvailable"]
    if available < minimum_available:
        raise RuntimeError(
            f"resource preflight failed: {available} bytes available; "
            f"{minimum_available} required for {model_id}"
        )
    if disk.free < 5 * 1024**3:
        raise RuntimeError("resource preflight failed: less than 5 GiB disk free")
    return {
        "mem_available_bytes": available,
        "swap_free_bytes": meminfo.get("SwapFree", 0),
        "disk_free_bytes": disk.free,
        "minimum_mem_available_bytes": minimum_available,
    }


def _swap_free_bytes() -> int:
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("SwapFree:"):
            return int(line.split()[1]) * 1024
    raise RuntimeError("SwapFree is not readable")


def _collect_named_values(value: Any, names: set[str], out: dict[str, Any]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in names and isinstance(item, (int, float)) and key not in out:
                out[key] = item
            _collect_named_values(item, names, out)
    elif isinstance(value, list):
        for item in value:
            _collect_named_values(item, names, out)


def _extract_observables(
    summaries: list[dict[str, Any]], model_id: str
) -> dict[str, Any]:
    if not summaries:
        return {}
    records = summaries[0]["record"]
    case = records[0] if isinstance(records, list) and records else records
    if not isinstance(case, dict):
        return {}
    if model_id == "euv_2d_complex_absorption_v1":
        official = (
            case.get("dtn_auxiliary_power_metrics")
            or case.get("dtn_port_power_metrics")
            or {}
        )
        return {
            key: value
            for key, value in {
                "R_total": official.get("R_total"),
                "T_total": official.get("T_total"),
                "A_balance": official.get("A_balance"),
                "A_volume": official.get("A_volume"),
                "true_residual": case.get("reduced_linear_residual"),
                "num_mesh_cells": case.get("num_mesh_cells"),
                "num_nedelec_dofs": case.get("num_nedelec_dofs"),
                "linear_matrix_rows": case.get("linear_matrix_rows"),
                "linear_matrix_nnz": case.get("linear_matrix_nnz"),
                "solver_elapsed_seconds": case.get("elapsed_seconds"),
            }.items()
            if value is not None
        }
    observables: dict[str, Any] = {}
    _collect_named_values(
        case,
        {
            "R_total", "T_total", "A_balance", "A_volume",
            "true_residual", "linear_true_residual", "relative_residual",
            "num_mesh_cells", "num_nedelec_dofs", "linear_matrix_rows",
            "linear_matrix_nnz", "elapsed_seconds",
        },
        observables,
    )
    return observables


class ForwardModel:
    def __init__(self, root: Path = ROOT) -> None:
        self.root = root.resolve()

    def evaluate(self, parameters: ForwardParameters, run: RunConfig) -> ForwardResult:
        parameters.validate()
        run.validate()
        source = source_identity(self.root)
        abi = _abi_identity(self.root)
        resources = _resource_identity(self.root, parameters.model_id)
        if run.formal and source["dirty"]:
            raise RuntimeError("formal forward samples require a clean source tree")
        if not run.output.resolve().is_relative_to(self.root):
            raise ValueError("Task000 output must remain below the repository root")
        run.output.mkdir(parents=True, exist_ok=True)
        run_dir = run.output / (
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "_" + uuid.uuid4().hex[:12]
        )
        run_dir.mkdir(parents=False, exist_ok=False)
        solver_dir = run_dir / "solver"
        command = [
            str(self.root / ".venv" / "bin" / "python"),
            str(self.root / "src" / "main.py"),
            "--preset", parameters.preset,
            "--results-root", str(solver_dir),
            "--no-unique-output",
        ]
        env = {
            **os.environ,
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
        }
        started_utc = datetime.now(timezone.utc).isoformat()
        swap_before = _swap_free_bytes()
        started = time.monotonic()
        if run.dry_run:
            completed = subprocess.CompletedProcess(command, 0, "dry-run\n", "")
        else:
            try:
                completed = subprocess.run(
                    command, cwd=self.root, env=env, text=True,
                    capture_output=True, timeout=run.timeout_seconds, check=False,
                )
            except subprocess.TimeoutExpired as exc:
                completed = subprocess.CompletedProcess(
                    command, 124, exc.stdout or "", exc.stderr or "timeout"
                )
        elapsed = time.monotonic() - started
        completed_utc = datetime.now(timezone.utc).isoformat()
        swap_after = _swap_free_bytes()
        import resource
        child_peak_rss_kib = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
        summaries: list[dict[str, Any]] = []
        if not run.dry_run:
            for path in sorted(solver_dir.rglob("*summary.json")):
                summaries.append({"path": str(path), "record": json.loads(path.read_text())})
        observables = _extract_observables(summaries, parameters.model_id)
        residual = observables.get(
            "true_residual",
            observables.get("linear_true_residual", observables.get("relative_residual")),
        )
        r_value = observables.get("R_total")
        t_value = observables.get("T_total")
        a_value = observables.get("A_balance")
        a_volume = observables.get("A_volume")
        physics_gate = {
            "residual_present_and_below_1e-8": (
                isinstance(residual, (int, float)) and residual <= 1.0e-8
            ),
            "rta_present_and_nonnegative": all(
                isinstance(value, (int, float)) and value >= -1.0e-8
                for value in (r_value, t_value, a_value)
            ),
            "rta_closure_within_1e-5": (
                all(isinstance(value, (int, float)) for value in (r_value, t_value, a_value))
                and abs(float(r_value) + float(t_value) + float(a_value) - 1.0) <= 1.0e-5
            ),
            "volume_absorption_matches_balance_within_1e-5": (
                not isinstance(a_volume, (int, float))
                or (
                    isinstance(a_value, (int, float))
                    and abs(float(a_volume) - float(a_value)) <= 1.0e-5
                )
            ),
        }
        gate_pass = all(physics_gate.values())
        status = "dry_run_pass"
        effective_return_code = completed.returncode
        if not run.dry_run:
            if completed.returncode != 0:
                status = "timeout" if completed.returncode == 124 else "solver_failed"
            elif not gate_pass:
                status = "physics_gate_failed"
                effective_return_code = 4
            else:
                status = "formal_sample_pass" if run.formal else "development_smoke_pass"
        raw = {
            "status": status,
            "parameters": parameters.as_dict(),
            "source": source,
            "abi": abi,
            "resource_preflight": resources,
            "formal": run.formal,
            "command": command,
            "return_code": completed.returncode,
            "effective_return_code": effective_return_code,
            "elapsed_seconds": elapsed,
            "started_utc": started_utc,
            "completed_utc": completed_utc,
            "resource_observation": {
                "scope": "single serial child process; ru_maxrss plus system SwapFree delta",
                "child_peak_rss_kib": child_peak_rss_kib,
                "swap_free_before_bytes": swap_before,
                "swap_free_after_bytes": swap_after,
                "swap_free_delta_bytes": swap_after - swap_before,
            },
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "summaries": summaries,
            "observables": observables,
            "physics_gate": physics_gate,
        }
        raw_path = run_dir / "raw_record.json"
        raw_path.write_text(json.dumps(raw, indent=2, ensure_ascii=False) + "\n")
        compact = {
            "status": status,
            "source_sha": source["source_sha"],
            "dirty": source["dirty"],
            "parameter_hash": canonical_hash(parameters.as_dict()),
            "observable_schema_version": OBSERVABLE_SCHEMA_VERSION,
            "observables": observables,
            "return_code": effective_return_code,
            "solver_return_code": completed.returncode,
            "physics_gate": physics_gate,
            "elapsed_seconds": elapsed,
        }
        compact_path = run_dir / "compact_record.json"
        compact_path.write_text(json.dumps(compact, indent=2, ensure_ascii=False) + "\n")
        manifest = {
            "schema_version": "task000.forward-manifest.v1",
            "parameter_schema_version": parameters.schema_version,
            "observable_schema_version": OBSERVABLE_SCHEMA_VERSION,
            "source": source,
            "abi": abi,
            "resource_preflight": resources,
            "artifact_hashes": {
                "raw_record.json": file_hash(raw_path),
                "compact_record.json": file_hash(compact_path),
                **{
                    str(Path(item["path"]).relative_to(run_dir)): file_hash(Path(item["path"]))
                    for item in summaries
                },
            },
        }
        manifest_path = run_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
        return ForwardResult(
            status=status, run_directory=run_dir, observables=observables,
            manifest_path=manifest_path, return_code=effective_return_code,
        )
