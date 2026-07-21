"""Structured native-WSL environment qualification for Task034."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc
from slepc4py import SLEPc

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_IMPORTS = (
    "mpi4py", "petsc4py", "slepc4py", "dolfinx", "dolfinx_mpc",
    "basix", "ufl", "gmsh", "numpy", "scipy",
)
DEFAULT_MPI_SIZES = (1, 2, 4)
AUDIT_COMMANDS = (
    ("uname", "-a"),
    ("cat", "/etc/os-release"),
    ("python", "--version"),
    ("which", "python"),
    ("which", "mpiexec"),
    ("mpiexec", "--version"),
    ("lscpu",),
    ("numactl", "--hardware"),
    ("free", "-h"),
    ("cat", "/proc/meminfo"),
    ("cat", "/proc/swaps"),
    ("bash", "-lc", "ulimit -a"),
    ("df", "-hT"),
    ("df", "-ih"),
    ("mount",),
)


def _git(*args: str) -> str | None:
    try:
        return subprocess.check_output(
            ["git", *args], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _run_command(command: tuple[str, ...]) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command, cwd=ROOT, text=True, capture_output=True, timeout=30, check=False
        )
        return {
            "command": list(command),
            "return_code": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "optional_missing": command[0] == "numactl" and completed.returncode != 0,
        }
    except FileNotFoundError as exc:
        return {
            "command": list(command), "return_code": 127, "stdout": "",
            "stderr": str(exc), "optional_missing": command[0] == "numactl",
        }


def _import_inventory() -> tuple[dict[str, Any], list[str]]:
    inventory: dict[str, Any] = {}
    failures: list[str] = []
    for name in REQUIRED_IMPORTS:
        try:
            module = importlib.import_module(name)
            inventory[name] = {
                "version": getattr(module, "__version__", "unknown"),
                "path": getattr(module, "__file__", None),
            }
        except Exception as exc:  # qualification must preserve exact import failures
            failures.append(name)
            inventory[name] = {"error": f"{type(exc).__name__}: {exc}"}
    return inventory, failures


def _dolfinx_mpc_abi_probe() -> dict[str, Any]:
    try:
        module = importlib.import_module("dolfinx_mpc")
        cpp = importlib.import_module("dolfinx_mpc.cpp")
        module_path = Path(module.__file__).resolve()
        extension_path = Path(cpp.__file__).resolve()
        completed = subprocess.run(
            ["ldd", str(extension_path)], text=True, capture_output=True,
            timeout=30, check=False,
        )
        linkage = completed.stdout
        prefix = (ROOT / ".venv" / "dolfinx_mpc-complex").resolve()
        checks = {
            "python_module_from_project_venv": module_path.is_relative_to(
                (ROOT / ".venv").resolve()
            ),
            "extension_from_project_venv": extension_path.is_relative_to(
                (ROOT / ".venv").resolve()
            ),
            "project_complex_mpc_library_loaded": str(prefix / "lib") in linkage,
            "dolfinx_complex_loaded": "libdolfinx_complex" in linkage,
            "petsc_complex_loaded": "libpetsc_complex" in linkage,
            "no_dolfinx_real_loaded": "libdolfinx_real" not in linkage,
            "no_petsc_real_loaded": "libpetsc_real" not in linkage,
            "ldd_succeeded": completed.returncode == 0,
        }
        return {
            "pass": all(checks.values()), "module_path": str(module_path),
            "extension_path": str(extension_path), "checks": checks,
            "ldd_stdout": linkage, "ldd_stderr": completed.stderr,
        }
    except Exception as exc:
        return {"pass": False, "error": f"{type(exc).__name__}: {exc}"}


def _mumps_probe() -> dict[str, Any]:
    matrix = PETSc.Mat().createAIJ([1, 1], comm=PETSc.COMM_SELF)
    rhs = PETSc.Vec().createSeq(1, comm=PETSc.COMM_SELF)
    solution = rhs.duplicate()
    ksp = PETSc.KSP().create(comm=PETSc.COMM_SELF)
    try:
        matrix.setValue(0, 0, PETSc.ScalarType(2.0))
        matrix.assemblyBegin()
        matrix.assemblyEnd()
        rhs.setValue(0, PETSc.ScalarType(4.0))
        rhs.assemblyBegin()
        rhs.assemblyEnd()
        ksp.setOperators(matrix)
        ksp.setType(PETSc.KSP.Type.PREONLY)
        ksp.getPC().setType(PETSc.PC.Type.LU)
        ksp.getPC().setFactorSolverType("mumps")
        ksp.setUp()
        ksp.solve(rhs, solution)
        error = abs(complex(solution.getValue(0)) - 2.0)
        return {
            "pass": error <= 1.0e-13,
            "factor_solver_type": ksp.getPC().getFactorSolverType(),
            "solution_absolute_error": error,
        }
    except Exception as exc:
        return {"pass": False, "error": f"{type(exc).__name__}: {exc}"}
    finally:
        ksp.destroy()
        solution.destroy()
        rhs.destroy()
        matrix.destroy()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _rank_library_identity() -> dict[str, Any]:
    module_names = (
        "mpi4py.MPI",
        "petsc4py.PETSc",
        "slepc4py.SLEPc",
        "dolfinx.cpp",
        "dolfinx_mpc.cpp",
    )
    libraries: dict[str, Any] = {}
    failures: list[str] = []
    relevant_tokens = (
        "libmpi",
        "libpetsc",
        "libslepc",
        "libdolfinx",
        "libdolfinx_mpc",
    )
    for name in module_names:
        try:
            module = importlib.import_module(name)
            path = Path(module.__file__).resolve()
            completed = subprocess.run(
                ["ldd", str(path)],
                text=True,
                capture_output=True,
                timeout=30,
                check=False,
            )
            linked = sorted(
                line.strip().rsplit(" (0x", 1)[0]
                for line in completed.stdout.splitlines()
                if any(token in line for token in relevant_tokens)
            )
            entry = {
                "path": str(path),
                "sha256": _file_sha256(path),
                "ldd_return_code": completed.returncode,
                "linked_relevant_libraries": linked,
            }
            libraries[name] = entry
            if (
                not str(path).startswith("/")
                or ":\\" in str(path)
                or completed.returncode != 0
                or not linked
            ):
                failures.append(name)
        except Exception as exc:
            failures.append(name)
            libraries[name] = {"error": f"{type(exc).__name__}: {exc}"}
    signature_payload = json.dumps(
        libraries,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return {
        "pass": not failures,
        "libraries": libraries,
        "signature_sha256": hashlib.sha256(signature_payload).hexdigest(),
        "failures": failures,
    }


def _distributed_diagonal_matrix(
    dimension: int,
    *,
    diagonal: Any,
) -> PETSc.Mat:
    matrix = PETSc.Mat().createAIJ(
        [dimension, dimension],
        nnz=1,
        comm=PETSc.COMM_WORLD,
    )
    first, last = matrix.getOwnershipRange()
    for row in range(first, last):
        value = diagonal(row)
        if value != 0:
            matrix.setValue(row, row, PETSc.ScalarType(value))
    matrix.assemblyBegin()
    matrix.assemblyEnd()
    return matrix


def _distributed_mumps_probe() -> dict[str, Any]:
    communicator = MPI.COMM_WORLD
    dimension = max(2 * communicator.size, 32)
    matrix = _distributed_diagonal_matrix(
        dimension,
        diagonal=lambda row: 2.0 + row / dimension,
    )
    rhs = matrix.createVecRight()
    solution = rhs.duplicate()
    ksp = PETSc.KSP().create(comm=PETSc.COMM_WORLD)
    try:
        first, last = rhs.getOwnershipRange()
        for row in range(first, last):
            rhs.setValue(
                row,
                PETSc.ScalarType(2.0 + row / dimension),
            )
        rhs.assemblyBegin()
        rhs.assemblyEnd()
        ksp.setOperators(matrix)
        ksp.setType(PETSc.KSP.Type.PREONLY)
        ksp.getPC().setType(PETSc.PC.Type.LU)
        ksp.getPC().setFactorSolverType("mumps")
        ksp.setUp()
        ksp.solve(rhs, solution)
        values = solution.getArray(readonly=True)
        local_error = (
            float(np.max(np.abs(values - 1.0))) if len(values) else 0.0
        )
        error = communicator.allreduce(local_error, op=MPI.MAX)
        solver_type = ksp.getPC().getFactorSolverType()
        result = {
            "pass": solver_type == "mumps" and error <= 1.0e-12,
            "dimension": dimension,
            "factor_solver_type": solver_type,
            "solution_absolute_error_max": error,
            "ksp_converged_reason": ksp.getConvergedReason(),
            "ksp_iterations": ksp.getIterationNumber(),
        }
    except Exception as exc:
        result = {
            "pass": False,
            "dimension": dimension,
            "error": f"{type(exc).__name__}: {exc}",
        }
    finally:
        ksp.destroy()
        solution.destroy()
        rhs.destroy()
        matrix.destroy()
    return result


def _distributed_pep_probe() -> dict[str, Any]:
    communicator = MPI.COMM_WORLD
    dimension = max(2 * communicator.size, 32)
    a0 = _distributed_diagonal_matrix(
        dimension,
        diagonal=lambda row: -float((1.0 + row / dimension) ** 2),
    )
    a1 = _distributed_diagonal_matrix(
        dimension,
        diagonal=lambda row: 0.0,
    )
    a2 = _distributed_diagonal_matrix(
        dimension,
        diagonal=lambda row: 1.0,
    )
    pep = SLEPc.PEP().create(comm=PETSc.COMM_WORLD)
    try:
        pep.setOperators([a0, a1, a2])
        pep.setProblemType(SLEPc.PEP.ProblemType.GENERAL)
        pep.setType(SLEPc.PEP.Type.TOAR)
        pep.setDimensions(nev=1)
        pep.setWhichEigenpairs(SLEPc.PEP.Which.SMALLEST_MAGNITUDE)
        pep.setTolerances(tol=1.0e-12, max_it=500)
        pep.solve()
        converged = pep.getConverged()
        eigenvalue = (
            complex(pep.getEigenpair(0))
            if converged
            else complex(math.nan)
        )
        relative_error = (
            float(pep.computeError(0, SLEPc.PEP.ErrorType.RELATIVE))
            if converged
            else math.inf
        )
        root_error = min(abs(eigenvalue - 1.0), abs(eigenvalue + 1.0))
        result = {
            "pass": (
                converged >= 1
                and root_error <= 1.0e-8
                and relative_error <= 1.0e-8
            ),
            "dimension": dimension,
            "pep_type": pep.getType(),
            "converged": converged,
            "eigenvalue": [eigenvalue.real, eigenvalue.imag],
            "expected_root_absolute_error": root_error,
            "relative_error": relative_error,
        }
    except Exception as exc:
        result = {
            "pass": False,
            "dimension": dimension,
            "error": f"{type(exc).__name__}: {exc}",
        }
    finally:
        pep.destroy()
        a2.destroy()
        a1.destroy()
        a0.destroy()
    return result


def _distributed_solver_microfixture() -> dict[str, Any]:
    mumps = _distributed_mumps_probe()
    pep = _distributed_pep_probe()
    return {
        "pass": mumps.get("pass") is True and pep.get("pass") is True,
        "mumps": mumps,
        "pep": pep,
    }


def _rank_probe(*, solver_microfixture: bool = False) -> int:
    imports, failures = _import_inventory()
    library_identity = _rank_library_identity()
    solver = (
        _distributed_solver_microfixture()
        if solver_microfixture
        else None
    )
    payload = {
        "rank": MPI.COMM_WORLD.rank,
        "size": MPI.COMM_WORLD.size,
        "hostname": platform.node(),
        "python_executable": sys.executable,
        "python_prefix": sys.prefix,
        "mpi_library": MPI.Get_library_version().strip(),
        "petsc_scalar_dtype": str(np.dtype(PETSc.ScalarType)),
        "petsc_int_bits": np.dtype(PETSc.IntType).itemsize * 8,
        "petsc_dir": os.environ.get("PETSC_DIR"),
        "slepc_dir": os.environ.get("SLEPC_DIR"),
        "imports": imports,
        "import_failures": failures,
        "rank_library_identity": library_identity,
        "solver_microfixture_required": solver_microfixture,
        "solver_microfixture": solver,
    }
    local_pass = (
        not failures
        and library_identity["pass"]
        and (solver is None or solver["pass"])
    )
    passed = MPI.COMM_WORLD.allreduce(local_pass, op=MPI.LAND)
    rows = MPI.COMM_WORLD.gather(payload, root=0)
    if MPI.COMM_WORLD.rank == 0:
        for row in rows:
            print(json.dumps(row, sort_keys=True), flush=True)
    return 0 if passed else 2


def _mpi_probe(
    size: int,
    *,
    solver_microfixture: bool = False,
) -> dict[str, Any]:
    command = [
        "mpiexec", "-n", str(size), sys.executable, "-m",
        "benchmarks.run_task034_wsl_qualification", "--rank-probe",
    ]
    if solver_microfixture:
        command.append("--solver-microfixture")
    completed = subprocess.run(
        command,
        cwd=ROOT, text=True, capture_output=True, timeout=300, check=False,
        env={**os.environ, "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
             "MKL_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1"},
    )
    rows = []
    parse_failures = []
    for line in completed.stdout.splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            parse_failures.append(line)
    signatures = {
        (row.get("python_executable"), row.get("mpi_library"),
         row.get("petsc_scalar_dtype"), row.get("petsc_int_bits"),
         row.get("petsc_dir"), row.get("slepc_dir"),
         row.get("rank_library_identity", {}).get("signature_sha256"),
         row.get("imports", {}).get("dolfinx_mpc", {}).get("path"))
        for row in rows
    }
    no_windows_paths = all(
        isinstance(row.get("python_executable"), str)
        and row["python_executable"].startswith("/")
        and not any(
            isinstance(item.get("path"), str) and ":\\" in item["path"]
            for item in row.get("imports", {}).values()
        )
        for row in rows
    )
    libraries_pass = all(
        row.get("rank_library_identity", {}).get("pass") is True
        for row in rows
    )
    solver_pass = all(
        row.get("solver_microfixture", {}).get("pass") is True
        for row in rows
    ) if solver_microfixture else True
    passed = bool(
        completed.returncode == 0 and len(rows) == size and not parse_failures
        and len(signatures) == 1 and no_windows_paths and libraries_pass
        and solver_pass
        and {row.get("rank") for row in rows} == set(range(size))
    )
    return {
        "mpi_size": size, "pass": passed, "return_code": completed.returncode,
        "rank_records": rows, "non_json_stdout": parse_failures,
        "stderr": completed.stderr, "single_abi_signature": len(signatures) == 1,
        "no_windows_paths": no_windows_paths,
        "rank_library_identity_pass": libraries_pass,
        "solver_microfixture_required": solver_microfixture,
        "solver_microfixture_pass": solver_pass,
    }


def _parse_required_probe_sizes(value: str) -> tuple[int, ...]:
    try:
        sizes = tuple(int(item) for item in value.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "MPI sizes must be comma-separated positive integers"
        ) from exc
    if not sizes or any(size <= 0 for size in sizes) or len(set(sizes)) != len(sizes):
        raise argparse.ArgumentTypeError(
            "MPI sizes must be unique positive integers"
        )
    return sizes


def _parse_optional_probe_sizes(value: str) -> tuple[int, ...]:
    return () if not value else _parse_required_probe_sizes(value)


def _validate_probe_sizes(
    mpi_sizes: tuple[int, ...],
    distributed_solver_sizes: tuple[int, ...],
    exploratory_mpi_sizes: tuple[int, ...],
) -> tuple[tuple[int, ...], tuple[int, ...], tuple[int, ...]]:
    if not set(DEFAULT_MPI_SIZES).issubset(mpi_sizes):
        raise ValueError("MPI1/MPI2/MPI4 baseline probes are required")
    if not set(distributed_solver_sizes).issubset(mpi_sizes):
        raise ValueError("distributed solver sizes must be requested MPI sizes")
    if not set(exploratory_mpi_sizes).issubset(mpi_sizes):
        raise ValueError("exploratory sizes must be requested MPI sizes")
    if len(set(mpi_sizes)) != len(mpi_sizes):
        raise ValueError("requested MPI sizes must be unique")
    return mpi_sizes, distributed_solver_sizes, exploratory_mpi_sizes


def _physical_core_inventory() -> dict[str, Any]:
    allowed = (
        set(os.sched_getaffinity(0))
        if hasattr(os, "sched_getaffinity")
        else set(range(os.cpu_count() or 0))
    )
    completed = subprocess.run(
        ["lscpu", "-p=CPU,CORE,SOCKET,ONLINE"],
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    cores: set[tuple[int, int]] = set()
    parse_failures: list[str] = []
    for line in completed.stdout.splitlines():
        if not line or line.startswith("#"):
            continue
        try:
            cpu, core, socket, online = line.split(",")
            if int(cpu) in allowed and online.strip().lower() in {"y", "yes"}:
                cores.add((int(socket), int(core)))
        except (ValueError, TypeError):
            parse_failures.append(line)
    return {
        "source": "lscpu -p=CPU,CORE,SOCKET,ONLINE intersect sched_getaffinity",
        "lscpu_return_code": completed.returncode,
        "allowed_logical_cpu_count": len(allowed),
        "available_physical_core_count": len(cores),
        "parse_failures": parse_failures,
        "pass": completed.returncode == 0 and bool(cores) and not parse_failures,
    }


def build_record(
    *,
    mpi_sizes: tuple[int, ...] = DEFAULT_MPI_SIZES,
    distributed_solver_sizes: tuple[int, ...] = (),
    exploratory_mpi_sizes: tuple[int, ...] = (),
) -> dict[str, Any]:
    mpi_sizes, distributed_solver_sizes, exploratory_mpi_sizes = (
        _validate_probe_sizes(
            mpi_sizes,
            distributed_solver_sizes,
            exploratory_mpi_sizes,
        )
    )
    head_before = _git("rev-parse", "HEAD")
    status_before = _git("status", "--short", "--untracked-files=all")
    audit = [_run_command(command) for command in AUDIT_COMMANDS]
    imports, import_failures = _import_inventory()
    pep = SLEPc.PEP().create(comm=PETSc.COMM_SELF)
    pep_created = bool(pep)
    pep.destroy()
    mpc_abi = _dolfinx_mpc_abi_probe()
    mumps = _mumps_probe()
    mpi = [
        _mpi_probe(
            size,
            solver_microfixture=size in distributed_solver_sizes,
        )
        for size in mpi_sizes
    ]
    scalar_complex = np.dtype(PETSc.ScalarType) == np.dtype(np.complex128)
    cores = _physical_core_inventory()
    head_after = _git("rev-parse", "HEAD")
    status_after = _git("status", "--short", "--untracked-files=all")
    by_size = {item["mpi_size"]: item for item in mpi}
    checks = {
        "native_wsl_kernel": "microsoft" in platform.release().lower(),
        "docker_runtime_not_used": not Path("/.dockerenv").exists(),
        "all_required_imports": not import_failures,
        "petsc_scalar_complex128": scalar_complex,
        "petsc_int_width_recorded": np.dtype(PETSc.IntType).itemsize in (4, 8),
        "slepc_pep_created": pep_created,
        "dolfinx_mpc_complex_abi": mpc_abi.get("pass") is True,
        "mumps_selected_and_solved": mumps.get("pass") is True,
        "mpi1_mpi2_mpi4_pass": all(
            by_size[size]["pass"] for size in DEFAULT_MPI_SIZES
        ),
        "all_requested_mpi_sizes_pass": all(item["pass"] for item in mpi),
        "all_rank_library_identities_pass": all(
            item["rank_library_identity_pass"] for item in mpi
        ),
        "requested_distributed_solver_microfixtures_pass": all(
            by_size[size]["solver_microfixture_pass"]
            for size in distributed_solver_sizes
        ),
        "mpi16_microfixture_pass_when_requested": (
            16 not in mpi_sizes
            or (
                16 in distributed_solver_sizes
                and by_size[16]["solver_microfixture_pass"]
            )
        ),
        "mpi32_labeled_exploratory_when_requested": (
            32 not in mpi_sizes or 32 in exploratory_mpi_sizes
        ),
        "physical_core_inventory_readable": cores["pass"],
        "requested_mpi_sizes_do_not_oversubscribe": (
            cores["pass"]
            and max(mpi_sizes) <= cores["available_physical_core_count"]
        ),
        "linux_paths_only": all(item["no_windows_paths"] for item in mpi),
        "single_mpi_abi_per_run": all(item["single_abi_signature"] for item in mpi),
        "tracked_activation_used": os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION") == "1",
        "source_clean_before_probe": status_before == "",
        "source_stable_during_probe": head_before == head_after,
        "source_clean_after_probe": status_after == "",
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "schema_version": "task034.wsl-environment-qualification.v2",
        "record_type": "native_wsl_environment_qualification",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "status": "environment_gate_pass" if not failures else "environment_gate_fail",
        "formal_pass": not failures,
        "source": {
            "head_before_sha": head_before,
            "head_after_sha": head_after,
            "status_before": status_before,
            "status_after": status_after,
            "cleanliness": "git status --short --untracked-files=all",
        },
        "probe_scope": {
            "requested_mpi_sizes": list(mpi_sizes),
            "formal_mpi_sizes": [
                size for size in mpi_sizes
                if size not in exploratory_mpi_sizes
            ],
            "exploratory_mpi_sizes": list(exploratory_mpi_sizes),
            "distributed_solver_microfixture_sizes": list(
                distributed_solver_sizes
            ),
            "threads_per_rank": 1,
        },
        "runtime": {"python": sys.executable, "python_version": sys.version,
                    "kernel": platform.release(), "platform": platform.platform(),
                    "petsc_scalar_dtype": str(np.dtype(PETSc.ScalarType)),
                    "petsc_int_bits": np.dtype(PETSc.IntType).itemsize * 8,
                    "petsc_version": PETSc.Sys.getVersionInfo(),
                    "slepc_pep_created": pep_created},
        "imports": imports,
        "import_failures": import_failures,
        "dolfinx_mpc_abi": mpc_abi,
        "mumps": mumps,
        "mpi_probes": mpi,
        "physical_core_inventory": cores,
        "audit_commands": audit,
        "checks": checks,
        "failures": failures,
        "identity": {"native_wsl": True, "docker_used": False,
                     "is_pde_run": False, "ordinary_default_changed": False},
    }


def render_markdown(record: dict[str, Any]) -> str:
    runtime = record["runtime"]
    lines = [
        "# Task034 WSL \u539f\u751f\u73af\u5883\u8d44\u683c\u5316", "",
        f"- \u72b6\u6001\uff1a`{record['status']}`",
        f"- HEAD\uff1a`{record['source']['head_before_sha']}`",
        f"- Python\uff1a`{runtime['python']}` / `{runtime['python_version'].split()[0]}`",
        f"- PETSc scalar\uff1a`{runtime['petsc_scalar_dtype']}`\uff1bInt\uff1a`{runtime['petsc_int_bits']} bit`",
        f"- \u53ef\u7528\u7269\u7406\u6838\uff1a`{record['physical_core_inventory']['available_physical_core_count']}`",
        "- \u8fd0\u884c\u8eab\u4efd\uff1aWSL2 Ubuntu \u539f\u751f\uff1bDocker \u672a\u53c2\u4e0e\u3002", "",
        "## Gate", "", "| \u68c0\u67e5 | \u7ed3\u679c |", "|---|---|",
    ]
    lines.extend(
        f"| `{name}` | {'PASS' if passed else 'FAIL'} |"
        for name, passed in record["checks"].items()
    )
    lines.extend([
        "", "## MPI", "",
        "| ranks | \u8303\u56f4 | \u7ed3\u679c | Python/ABI \u4e00\u81f4 | MUMPS/PEP microfixture |",
        "|---:|---|---|---|---|",
    ])
    exploratory = set(record["probe_scope"]["exploratory_mpi_sizes"])
    lines.extend(
        f"| {item['mpi_size']} | "
        f"{'exploratory' if item['mpi_size'] in exploratory else 'formal'} | "
        f"{'PASS' if item['pass'] else 'FAIL'} | "
        f"{'\u662f' if item['single_abi_signature'] else '\u5426'} | "
        f"{('PASS' if item['solver_microfixture_pass'] else 'FAIL') if item['solver_microfixture_required'] else 'N/A'} |"
        for item in record["mpi_probes"]
    )
    lines.extend([
        "", "## \u8bf4\u660e", "",
        "`numactl` \u7f3a\u5931\u5141\u8bb8\u4f5c\u4e3a\u53ef\u9009\u8bca\u65ad\u8d1f\u9879\uff1bNUMA \u4fe1\u606f\u4ecd\u7531 `lscpu` \u8bb0\u5f55\u3002",
        "\u73af\u5883 Gate \u53ea\u8bc1\u660e\u539f\u751f\u8f6f\u4ef6\u6808\u53ef\u7528\uff0c\u4e0d\u66ff\u4ee3 Phase A \u5206\u5c42\u56de\u5f52\u548c\u540e\u7eed PDE Gate\u3002", "",
    ])
    return "\n".join(lines)

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rank-probe", action="store_true")
    parser.add_argument("--solver-microfixture", action="store_true")
    parser.add_argument(
        "--mpi-sizes",
        type=_parse_required_probe_sizes,
        default=DEFAULT_MPI_SIZES,
    )
    parser.add_argument(
        "--distributed-solver-sizes",
        type=_parse_optional_probe_sizes,
        default=(),
    )
    parser.add_argument(
        "--exploratory-mpi-sizes",
        type=_parse_optional_probe_sizes,
        default=(),
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.rank_probe:
        return _rank_probe(solver_microfixture=args.solver_microfixture)
    record = build_record(
        mpi_sizes=args.mpi_sizes,
        distributed_solver_sizes=args.distributed_solver_sizes,
        exploratory_mpi_sizes=args.exploratory_mpi_sizes,
    )
    rendered = json.dumps(record, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    if args.markdown_output:
        args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_output.write_text(render_markdown(record), encoding="utf-8")
    print(json.dumps({"status": record["status"], "failures": record["failures"]}, ensure_ascii=False))
    return 0 if record["formal_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
