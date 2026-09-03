"""Run one minimal J3 split physical form-precompile child.

The parent owns the artifact/cache directories.  This child only validates
the frozen input, compiles one requested group, and writes raw facts.
"""

from __future__ import annotations

import argparse
import copy
import gc
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any


BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"
MODULE = "benchmarks.run_task038_full3d_jit_precompile"
INPUT_SHA256 = "819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41"
PHYSICAL_MODEL_SHA256 = "9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f"
MODE_MANIFEST_SHA256 = "dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2"
RECORD_SCHEMA = "task038.full3d.jit-split.child-record.v1"
EXPECTED_PROFILE = {
    "model_id": "euv_grazing1_phi0",
    "run_id": "euv_grazing1_phi0_full3d_iterative_mpi1",
    "comparison_group": "euv_grazing1_phi0",
    "wavelength_nm": 13.5,
    "grazing_angle_deg": 1.0,
    "incident_theta_deg": 89.0,
    "incident_phi_deg": 0.0,
    "polarization": "s",
    "nedelec_degree": 6,
    "mesh_target_size_nm": 10.0,
    "mesh_cell_type": "hexahedron",
    "mesh_spacing_mode": "boundary_fitted",
    "boundary_model": "dtn_port",
    "dtn_order_policy": "auto_propagating",
    "dtn_assembly": "auxiliary",
}


def _write_record(path: Path, value: dict[str, Any]) -> None:
    with Path(path).open("xb") as stream:
        stream.write(
            json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
            + b"\n"
        )
        stream.flush()
        os.fsync(stream.fileno())


def _prepare_paths(cache_dir: Path, record_path: Path) -> tuple[Path, Path]:
    cache_dir = Path(cache_dir).resolve()
    record_path = Path(record_path).resolve()
    if not cache_dir.is_dir():
        raise FileNotFoundError(f"parent-created cache is missing: {cache_dir}")
    if record_path.exists():
        raise FileExistsError(f"child record already exists: {record_path}")
    if not record_path.parent.is_dir():
        raise FileNotFoundError(f"record parent is missing: {record_path.parent}")
    return cache_dir, record_path


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "--git-dir=.git-codex", "--work-tree=.", *args],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "git identity probe failed")
    return result.stdout.strip()


def _runtime_facts(root: Path, expected_sha: str, comm: Any, petsc: Any) -> dict[str, Any]:
    if len(expected_sha) != 40 or any(c not in "0123456789abcdef" for c in expected_sha):
        raise ValueError("source-sha must be a lowercase full Git SHA")
    actual_sha = _git(root, "rev-parse", "HEAD")
    branch = _git(root, "branch", "--show-current")
    status = _git(root, "status", "--porcelain", "--untracked-files=all")
    if actual_sha != expected_sha or branch != BRANCH or status:
        raise RuntimeError(
            f"source identity is not clean: sha={actual_sha}, branch={branch}, status={status!r}"
        )
    if os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION") != "1":
        raise RuntimeError("qualified activation is required")
    executable = Path(sys.executable)
    prefix = Path(sys.prefix)
    expected_prefix = root.absolute() / ".venv"
    if (
        executable != expected_prefix / "bin" / "python"
        or prefix != expected_prefix
        or not executable.is_file()
        or not prefix.is_dir()
    ):
        raise RuntimeError("child interpreter must be the current checkout lexical .venv")
    import numpy as np

    if np.dtype(petsc.ScalarType) != np.dtype(np.complex128):
        raise RuntimeError("PETSc scalar type must be complex128")
    if np.dtype(petsc.IntType) != np.dtype(np.int32):
        raise RuntimeError("PETSc integer type must be int32")
    threads = {
        name: os.environ.get(name, "1")
        for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")
    }
    if any(value != "1" for value in threads.values()):
        raise RuntimeError("all BLAS/OpenMP thread settings must be one")
    abi = {}
    for name in ("mpi4py", "petsc4py", "dolfinx", "basix"):
        module = importlib.import_module(name)
        abi[name] = str(Path(module.__file__).resolve())
    if int(comm.size) != 1:
        raise RuntimeError("J3 split child is MPI1-only")
    return {
        "source_sha": actual_sha,
        "branch": branch,
        "clean_source_tree": True,
        "qualified_activation": "1",
        "python_executable": str(executable),
        "python_prefix": str(prefix),
        "mpi_size": 1,
        "petsc_scalar_type": "complex128",
        "petsc_int_type": "int32",
        "threads": threads,
        "abi_modules": abi,
    }


def _profile(specification: Any, cfg: Any) -> dict[str, Any]:
    payload = specification.as_jsonable()
    incidence = payload["incidence"]
    internal = payload["derived"]["internal"]
    return {
        "model_id": str(specification.identity["model_id"]),
        "run_id": str(specification.identity["run_id"]),
        "comparison_group": str(specification.identity["comparison_group"]),
        "wavelength_nm": float(incidence["wavelength_nm"]),
        "grazing_angle_deg": float(incidence["grazing_angle_deg"]),
        "incident_theta_deg": float(internal["incident_theta_deg"]),
        "incident_phi_deg": float(internal["incident_phi_deg"]),
        "polarization": str(incidence["polarization"]),
        "nedelec_degree": int(cfg.nedelec_degree),
        "mesh_target_size_nm": float(cfg.mesh_target_size),
        "mesh_cell_type": str(cfg.mesh_cell_type),
        "mesh_spacing_mode": str(cfg.mesh_spacing_mode),
        "boundary_model": str(cfg.stage4_boundary_model),
        "dtn_order_policy": str(cfg.stage4_dtn_order_policy),
        "dtn_assembly": str(cfg.stage4_dtn_assembly),
    }


def _mode_identity(cfg: Any) -> tuple[int, str, int]:
    from src.solvers.dtn_port_3d import _dtn_surface_quadrature_degree
    from src.solvers.fullspace_dtn_action import build_dynamic_mode_inventory

    modes, _rows, mode_sha = build_dynamic_mode_inventory(cfg)
    return len(modes), str(mode_sha), int(_dtn_surface_quadrature_degree(cfg, list(modes)))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--group", required=True)
    parser.add_argument("--cache-dir", required=True)
    parser.add_argument("--record", required=True)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--input", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    cache_dir, record_path = _prepare_paths(args.cache_dir, args.record)
    os.environ["XDG_CACHE_HOME"] = str(cache_dir)

    from mpi4py import MPI
    from petsc4py import PETSc
    from src.io import load_and_resolve
    from src.io.input_validation import simulation_config_3d_from_normalized
    from src.solvers.fullspace_same_mesh_hcurl_pmg_jit import (
        JIT_GROUPS,
        Q1_INNER_JIT_GROUP,
        build_minimal_jit_group,
    )

    if args.group not in JIT_GROUPS and args.group != Q1_INNER_JIT_GROUP:
        raise ValueError(f"unsupported J3 split group: {args.group!r}")
    root = Path(__file__).resolve().parents[1]
    comm = MPI.COMM_WORLD
    runtime = _runtime_facts(root, args.expected_source_sha, comm, PETSc)
    input_path = Path(args.input).resolve()
    specification = load_and_resolve(input_path)
    cfg = simulation_config_3d_from_normalized(specification.as_jsonable())
    profile_cfg = cfg
    if args.group == Q1_INNER_JIT_GROUP:
        profile_cfg = copy.deepcopy(cfg)
        profile_cfg.nedelec_degree = 3
        profile_cfg.mesh_target_size = 50.0
    profile = _profile(specification, profile_cfg)
    expected_profile = EXPECTED_PROFILE
    if args.group == Q1_INNER_JIT_GROUP:
        expected_profile = {
            **EXPECTED_PROFILE,
            "nedelec_degree": 3,
            "mesh_target_size_nm": 50.0,
        }
    if (
        specification.input_sha256 != INPUT_SHA256
        or specification.physical_model_sha256 != PHYSICAL_MODEL_SHA256
        or profile != expected_profile
    ):
        raise RuntimeError("J3 split input is not the frozen exact profile")
    mode_count, mode_sha, qdegree = _mode_identity(profile_cfg)
    if mode_sha != MODE_MANIFEST_SHA256:
        raise RuntimeError("J3 split mode inventory is not the frozen manifest")
    facts = build_minimal_jit_group(cfg, comm, args.group)
    gc.collect()
    PETSc.garbage_cleanup(comm)
    gc.collect()
    command = [str(Path(sys.executable)), "-m", MODULE, *sys.argv[1:]]
    record = {
        "schema": RECORD_SCHEMA,
        "stage": "j3-split-precompile-child",
        "group": args.group,
        "source_sha": args.expected_source_sha,
        "branch": runtime["branch"],
        "command": command,
        "input": {
            "path": str(input_path),
            "input_sha256": specification.input_sha256,
            "physical_model_sha256": specification.physical_model_sha256,
            "mode_manifest_sha256": mode_sha,
            "profile": profile,
        },
        "cache": {"cache_dir": str(cache_dir), "jit_options": facts["jit_options"]},
        "facts": {
            "mode_count": mode_count,
            "mode_manifest_sha256": mode_sha,
            "dtn_quadrature_degree": qdegree,
            "group_facts": facts,
        },
        "architecture": {
            "matrix": False,
            "factor": False,
            "pc": False,
            "rhs_vector": False,
            "surface_carrier": False,
            "dtn_carrier": False,
            "solve": False,
            "recovery": False,
            "compile": True,
            "mesh": True,
            "jit": True,
            "pde": False,
            "compiler_descendant_authority": "parent_watchdog",
        },
        "runtime": runtime,
        "raw_facts_only": True,
    }
    _write_record(record_path, record)


if __name__ == "__main__":
    main()
