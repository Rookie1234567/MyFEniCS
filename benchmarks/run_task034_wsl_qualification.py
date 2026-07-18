"""Structured native-WSL environment qualification for Task034."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib
import json
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
        matrix.assemblyBegin(); matrix.assemblyEnd()
        rhs.setValue(0, PETSc.ScalarType(4.0)); rhs.assemblyBegin(); rhs.assemblyEnd()
        ksp.setOperators(matrix)
        ksp.setType(PETSc.KSP.Type.PREONLY)
        ksp.getPC().setType(PETSc.PC.Type.LU)
        ksp.getPC().setFactorSolverType("mumps")
        ksp.setUp(); ksp.solve(rhs, solution)
        error = abs(complex(solution.getValue(0)) - 2.0)
        return {
            "pass": error <= 1.0e-13,
            "factor_solver_type": ksp.getPC().getFactorSolverType(),
            "solution_absolute_error": error,
        }
    except Exception as exc:
        return {"pass": False, "error": f"{type(exc).__name__}: {exc}"}
    finally:
        ksp.destroy(); solution.destroy(); rhs.destroy(); matrix.destroy()


def _rank_probe() -> int:
    imports, failures = _import_inventory()
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
    }
    print(json.dumps(payload, sort_keys=True), flush=True)
    return 0 if not failures else 2


def _mpi_probe(size: int) -> dict[str, Any]:
    completed = subprocess.run(
        ["mpiexec", "-n", str(size), sys.executable, "-m",
         "benchmarks.run_task034_wsl_qualification", "--rank-probe"],
        cwd=ROOT, text=True, capture_output=True, timeout=120, check=False,
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
    passed = bool(
        completed.returncode == 0 and len(rows) == size and not parse_failures
        and len(signatures) == 1 and no_windows_paths
        and {row.get("rank") for row in rows} == set(range(size))
    )
    return {
        "mpi_size": size, "pass": passed, "return_code": completed.returncode,
        "rank_records": rows, "non_json_stdout": parse_failures,
        "stderr": completed.stderr, "single_abi_signature": len(signatures) == 1,
        "no_windows_paths": no_windows_paths,
    }


def build_record() -> dict[str, Any]:
    audit = [_run_command(command) for command in AUDIT_COMMANDS]
    imports, import_failures = _import_inventory()
    pep = SLEPc.PEP().create(comm=PETSc.COMM_SELF)
    pep_created = bool(pep)
    pep.destroy()
    mpc_abi = _dolfinx_mpc_abi_probe()
    mumps = _mumps_probe()
    mpi = [_mpi_probe(size) for size in (1, 2, 4)]
    scalar_complex = np.dtype(PETSc.ScalarType) == np.dtype(np.complex128)
    head = _git("rev-parse", "HEAD")
    status = _git("status", "--short", "--untracked-files=all")
    checks = {
        "native_wsl_kernel": "microsoft" in platform.release().lower(),
        "docker_runtime_not_used": not Path("/.dockerenv").exists(),
        "all_required_imports": not import_failures,
        "petsc_scalar_complex128": scalar_complex,
        "petsc_int_width_recorded": np.dtype(PETSc.IntType).itemsize in (4, 8),
        "slepc_pep_created": pep_created,
        "dolfinx_mpc_complex_abi": mpc_abi.get("pass") is True,
        "mumps_selected_and_solved": mumps.get("pass") is True,
        "mpi1_mpi2_mpi4_pass": all(item["pass"] for item in mpi),
        "linux_paths_only": all(item["no_windows_paths"] for item in mpi),
        "single_mpi_abi_per_run": all(item["single_abi_signature"] for item in mpi),
        "tracked_activation_used": os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION") == "1",
        "source_clean_before_probe": status == "",
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "schema_version": "task034.wsl-environment-qualification.v1",
        "record_type": "native_wsl_environment_qualification",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "status": "environment_gate_pass" if not failures else "environment_gate_fail",
        "formal_pass": not failures,
        "source": {"head_sha": head, "status_before": status,
                   "cleanliness": "git status --short --untracked-files=all"},
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
        f"- HEAD\uff1a`{record['source']['head_sha']}`",
        f"- Python\uff1a`{runtime['python']}` / `{runtime['python_version'].split()[0]}`",
        f"- PETSc scalar\uff1a`{runtime['petsc_scalar_dtype']}`\uff1bInt\uff1a`{runtime['petsc_int_bits']} bit`",
        "- \u8fd0\u884c\u8eab\u4efd\uff1aWSL2 Ubuntu \u539f\u751f\uff1bDocker \u672a\u53c2\u4e0e\u3002", "",
        "## Gate", "", "| \u68c0\u67e5 | \u7ed3\u679c |", "|---|---|",
    ]
    lines.extend(
        f"| `{name}` | {'PASS' if passed else 'FAIL'} |"
        for name, passed in record["checks"].items()
    )
    lines.extend([
        "", "## MPI", "", "| ranks | \u7ed3\u679c | Python/ABI \u4e00\u81f4 |", "|---:|---|---|"
    ])
    lines.extend(
        f"| {item['mpi_size']} | {'PASS' if item['pass'] else 'FAIL'} | "
        f"{'\u662f' if item['single_abi_signature'] else '\u5426'} |"
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
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.rank_probe:
        return _rank_probe()
    record = build_record()
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
