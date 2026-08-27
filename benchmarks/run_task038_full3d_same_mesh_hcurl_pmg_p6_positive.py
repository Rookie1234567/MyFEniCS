"""Thin p6 same-mesh positive-lane worker.

The p6/p3/p1 construction and the fixed nested cycle live in ``src``.  This
module only owns the fresh artifact paths, the frozen source, the restart-20
driver, and raw-fact serialization.  It is intentionally MPI1-only and does
not create a p6 sparse matrix, a physical solve, or a second watchdog.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
import hashlib
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

import numpy as np


BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"
MODULE = "benchmarks.run_task038_full3d_same_mesh_hcurl_pmg_p6_positive"
STAGE = "c1-p6-positive"
CASE = "p6-h10-mpi1"
SOURCES = ("random", "gradient", "curl", "checkerboard")
RECORD_SCHEMA = "task038.full3d.same-mesh-hcurl-pmg.p6-positive-record.v2"
MARKER_SCHEMA = "task038.full3d.same-mesh-hcurl-pmg.p6-positive-marker.v2"
MARKERS = (
    "paths_ready",
    "bundle_built",
    "source_built",
    "solve_started",
    "solve_complete",
    "retained_ready",
    "retained_observed",
    "krylov_destroyed",
    "bundle_destroyed",
    "record_written",
)
LEVELS = (6, 3, 1)
PAIRS = ((6, 3), (3, 1))
RESTART = 20
CYCLE_MAX_IT = 20
MAX_IT = 10_000
CHECKPOINT_INTERVAL = 500
RESIDUAL_LIMIT = 1.0e-8
COLD_RSS_LIMIT = 2_000_000_000
RETAINED_WARNING = 1_800_000_000
RETAINED_DWELL_SECONDS = 2.0


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        return _jsonable(value.tolist())
    if isinstance(value, np.generic):
        return _jsonable(value.item())
    if isinstance(value, complex):
        return {"real": float(value.real), "imag": float(value.imag)}
    if isinstance(value, Path):
        return str(value)
    return value


def _strict_json_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            _jsonable(value),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    with path.open("xb") as stream:
        stream.write(_strict_json_bytes(value))
        stream.flush()
        os.fsync(stream.fileno())


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _stable_sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            _jsonable(value), sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    ).hexdigest()


def _array_sha(values: np.ndarray) -> str:
    array = np.ascontiguousarray(values, dtype=np.complex128)
    return hashlib.sha256(array.tobytes(order="C")).hexdigest()


def validate_profile(stage: str, case: str, source: str, mpi_size: int) -> None:
    if stage != STAGE or case != CASE or source not in SOURCES or int(mpi_size) != 1:
        raise ValueError("p6 positive lane is fixed to p6-h10-mpi1 and four sources")


def _prepare_paths(
    raw_dir: Path,
    jit_cache_dir: Path,
    checkpoint_root: Path,
    record_path: Path,
) -> None:
    raw_dir = Path(raw_dir).resolve()
    jit_cache_dir = Path(jit_cache_dir).resolve()
    checkpoint_root = Path(checkpoint_root).resolve()
    record_path = Path(record_path).resolve()
    root = raw_dir.parent
    if not raw_dir.is_absolute() or not checkpoint_root.is_absolute():
        raise ValueError("positive worker paths must be absolute")
    if jit_cache_dir != (root / "jit_cache").resolve():
        raise ValueError("jit-cache-dir must equal raw_dir.parent/jit_cache")
    if root.exists() and not root.is_dir():
        raise NotADirectoryError(f"positive artifact root is not a directory: {root}")
    worker_owned = (raw_dir, raw_dir / "markers", jit_cache_dir, checkpoint_root, record_path)
    if any(path.exists() for path in worker_owned):
        raise FileExistsError("a positive worker-owned path already exists")
    if checkpoint_root == raw_dir or raw_dir in checkpoint_root.parents:
        raise ValueError("checkpoint root must be separate from worker_raw")
    if record_path == raw_dir or record_path == checkpoint_root:
        raise ValueError("worker record must be a distinct file")
    if not root.exists():
        root.mkdir(parents=True, exist_ok=False)
    raw_dir.mkdir(exist_ok=False)
    (raw_dir / "markers").mkdir()
    jit_cache_dir.mkdir(exist_ok=False)
    checkpoint_root.mkdir(parents=True, exist_ok=False)
    if record_path.parent != root and not record_path.parent.is_dir():
        raise FileNotFoundError("record parent must already exist outside the artifact root")
    os.environ["XDG_CACHE_HOME"] = str(jit_cache_dir)


def _emit_marker(raw_dir: Path, name: str, source_sha: str, **facts: Any) -> None:
    if name not in MARKERS:
        raise ValueError(f"unknown positive marker: {name}")
    _write_json(
        Path(raw_dir) / "markers" / f"{name}.json",
        {
            "schema": MARKER_SCHEMA,
            "marker": name,
            "source_sha": source_sha,
            "wall_time_ns": time.time_ns(),
            "facts": facts,
        },
    )


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


def _source_facts(root: Path, expected_sha: str, comm: Any, petsc: Any) -> dict[str, Any]:
    if (
        type(expected_sha) is not str
        or len(expected_sha) != 40
        or any(char not in "0123456789abcdef" for char in expected_sha)
    ):
        raise ValueError("expected-source-sha must be a lowercase full Git SHA")
    actual_sha = _git(root, "rev-parse", "HEAD")
    branch = _git(root, "branch", "--show-current")
    status = _git(root, "status", "--porcelain", "--untracked-files=all")
    if actual_sha != expected_sha or branch != BRANCH or status:
        raise RuntimeError(
            f"source identity is not clean: sha={actual_sha}, branch={branch}, status={status!r}"
        )
    if os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION") != "1":
        raise RuntimeError("qualified activation is required")
    if not Path(sys.executable).resolve().is_file():
        raise RuntimeError("worker executable must resolve to a file")
    if np.dtype(petsc.ScalarType) != np.dtype(np.complex128):
        raise RuntimeError("PETSc scalar type must be complex128")
    if np.dtype(petsc.IntType) != np.dtype(np.int32):
        raise RuntimeError("PETSc integer type must be int32")
    thread_names = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")
    threads = {name: os.environ.get(name, "1") for name in thread_names}
    if any(value != "1" for value in threads.values()):
        raise RuntimeError("all BLAS/OpenMP thread settings must be one")
    abi: dict[str, str] = {}
    for name in ("mpi4py", "petsc4py", "dolfinx", "basix"):
        module = importlib.import_module(name)
        abi[name] = str(Path(module.__file__).resolve())
    if int(comm.size) != 1:
        raise RuntimeError("positive lane is MPI1-only")
    return {
        "source_sha": actual_sha,
        "branch": branch,
        "clean_source_tree": True,
        "qualified_activation": "1",
        "python_executable": str(Path(sys.executable).resolve()),
        "mpi_size": int(comm.size),
        "petsc_scalar_type": "complex128",
        "petsc_int_type": "int32",
        "threads": threads,
        "abi_modules": abi,
    }


def _command(args: argparse.Namespace) -> list[str]:
    return [
        str(Path(sys.executable).resolve()),
        "-m",
        MODULE,
        "--stage",
        str(args.stage),
        "--case",
        str(args.case),
        "--source",
        str(args.source),
        "--raw-dir",
        str(Path(args.raw_dir).resolve()),
        "--jit-cache-dir",
        str(Path(args.jit_cache_dir).resolve()),
        "--checkpoint-root",
        str(Path(args.checkpoint_root).resolve()),
        "--record",
        str(Path(args.record).resolve()),
        "--expected-source-sha",
        str(args.expected_source_sha),
        "--expected-mpi-size",
        "1",
        "--input",
        str(Path(args.input).resolve()),
    ]


def _vector_values(vector: Any) -> np.ndarray:
    return np.asarray(vector.getArray(readonly=True), dtype=np.complex128).copy()


def _vector_facts(values: np.ndarray, slave_indices: np.ndarray | None = None) -> dict[str, Any]:
    values = np.asarray(values, dtype=np.complex128)
    norm = float(np.linalg.norm(values))
    slave_max = 0.0
    if slave_indices is not None and slave_indices.size:
        slave_max = float(np.max(np.abs(values[slave_indices])))
    return {
        "shape": list(values.shape),
        "dtype": str(values.dtype),
        "finite": bool(np.all(np.isfinite(values))),
        "nonzero": bool(norm > 0.0),
        "norm": norm,
        "array_sha256": _array_sha(values),
        "owned_slave_max": slave_max,
    }


def _owned_slaves(bundle: Mapping[str, Any]) -> np.ndarray:
    mpc = bundle["floquets"][6].mpc
    index_map = mpc.function_space.dofmap.index_map
    owned = int(index_map.size_local) * int(mpc.function_space.dofmap.index_map_bs)
    slaves = np.asarray(mpc.slaves, dtype=np.int64)
    return np.asarray(slaves[(slaves >= 0) & (slaves < owned)], dtype=np.int32)


def _resource_sample() -> dict[str, Any]:
    from benchmarks.task034_wsl_resources import resource_authority_sample

    sample = dict(resource_authority_sample(os.getpid()))
    sample["scope"] = "rank-root-diagnostic"
    sample["process_tree_gate"] = False
    return sample


def _operator_authority(setup_audit: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "levels": list(LEVELS),
        "pairs": [list(pair) for pair in PAIRS],
        "profile": _jsonable(setup_audit["profile"]),
        "matrices": _jsonable(setup_audit["matrices"]),
        "p6_action": _jsonable(setup_audit["p6_action"]),
        "transfers": _jsonable(setup_audit["transfers"]),
        "architecture": _jsonable(setup_audit["architecture"]),
        "identity": "same_mesh_p6_matrix_free_fullspace_action",
    }


def _write_probe_npz(raw_dir: Path, arrays: Mapping[str, np.ndarray]) -> dict[str, Any]:
    path = Path(raw_dir) / "positive_probe.npz"
    if path.exists():
        raise FileExistsError(f"probe artifact already exists: {path}")
    np.savez_compressed(
        path,
        **{name: np.asarray(values, dtype=np.complex128) for name, values in arrays.items()},
    )
    return {
        "relative_path": path.name,
        "bytes": int(path.stat().st_size),
        "sha256": _sha256_file(path),
        "roles": list(arrays),
        "solution_only": False,
    }


def _record(
    *,
    raw_dir: Path,
    checkpoint_root: Path,
    record_path: Path,
    command: list[str],
    source: Mapping[str, Any],
    source_name: str,
    source_facts: Mapping[str, Any],
    setup_audit: Mapping[str, Any],
    provenance: Mapping[str, Any],
    identities: Mapping[str, Any],
    source_vector_facts: Mapping[str, Any],
    algebraic_input_facts: Mapping[str, Any],
    rhs_facts: Mapping[str, Any],
    rhs_repeat_facts: Mapping[str, Any],
    result: Mapping[str, Any],
    pc_apply_facts: list[Mapping[str, Any]],
    npz_facts: Mapping[str, Any],
    action_calls: int,
) -> dict[str, Any]:
    krylov = {
        key: _jsonable(value)
        for key, value in result.items()
        if key != "final_solution"
    }
    rhs_action_count = 2
    final_action_recheck_count = 1
    driver_explicit_action_count = int(result["explicit_action_count"])
    extra_action_count = rhs_action_count + final_action_recheck_count
    krylov["driver_explicit_action_count"] = driver_explicit_action_count
    krylov["rhs_action_count"] = rhs_action_count
    krylov["final_action_recheck_count"] = final_action_recheck_count
    krylov["extra_action_count"] = extra_action_count
    krylov["explicit_action_count_total"] = driver_explicit_action_count + extra_action_count
    krylov["action_calls_total"] = int(action_calls + rhs_action_count)
    krylov["pc_apply_facts"] = _jsonable(pc_apply_facts)
    return {
        "schema": RECORD_SCHEMA,
        "stage": STAGE,
        "case": CASE,
        "source_name": source_name,
        "mpi_size": 1,
        "branch": BRANCH,
        "command": list(command),
        "raw_dir": str(Path(raw_dir).resolve()),
        "record_path": str(Path(record_path).resolve()),
        "checkpoint_root": str(Path(checkpoint_root).resolve()),
        "provenance": _jsonable(dict(provenance)),
        "identities": _jsonable(dict(identities)),
        "architecture": {
            "levels": list(LEVELS),
            "pairs": [list(pair) for pair in PAIRS],
            "same_physical_mesh": True,
            "p6_matrix_free": True,
            "p3_sparse_allowed": True,
            "p1_sparse_allowed": True,
            "p6_global_aij": False,
            "high_order_global_aij": False,
            "global_dense_transfer": False,
            "global_transfer_matrix": False,
            "numeric_allgather": False,
            "p6_factor": False,
            "physical_solve": False,
            "dtn": False,
            "recovery": False,
            "outer_ksp_created": True,
            "source_is_pde_rhs": False,
            "setup_audit": _jsonable(setup_audit),
        },
        "source": {
            "facts": _jsonable(source_facts),
            "source_generation": "build_frozen_fullspace_primal_source",
            "role": "full_fe_primal_diagnostic_solution",
            "full_vector": _jsonable(source_vector_facts),
            "algebraic_input": _jsonable(algebraic_input_facts),
        },
        "rhs": {
            "facts": _jsonable(rhs_facts),
            "repeat": _jsonable(rhs_repeat_facts),
            "generation": "same_exact_p6_matrix_free_action",
        },
        "npz": _jsonable(npz_facts),
        "settings": {
            "ksp_type": "gmres",
            "pc_side": "right",
            "norm_type": "unpreconditioned",
            "restart": RESTART,
            "cycle_max_it": CYCLE_MAX_IT,
            "max_it": MAX_IT,
            "residual_replacement": True,
            "zero_initial_guess": True,
            "checkpoint_interval": CHECKPOINT_INTERVAL,
            "first_checkpoint_iteration": None,
            "residual_limit": RESIDUAL_LIMIT,
        },
        "krylov": krylov,
        "lifecycle": {
            "marker_relative_dir": "markers",
            "marker_names": list(MARKERS),
            "retained_dwell_seconds": RETAINED_DWELL_SECONDS,
            "release_order": ["source_rhs", "retained_window", "krylov_result", "bundle"],
            "external_process_tree_authority": True,
        },
        "raw_facts_only": True,
    }


def run_worker(args: argparse.Namespace) -> None:
    root = Path(__file__).resolve().parents[1]
    raw_dir = Path(args.raw_dir).resolve()
    jit_cache_dir = Path(args.jit_cache_dir).resolve()
    checkpoint_root = Path(args.checkpoint_root).resolve()
    record_path = Path(args.record).resolve()
    input_path = Path(args.input).resolve()
    if not input_path.is_file():
        raise FileNotFoundError(f"input template does not exist: {input_path}")
    command = _command(args)
    _prepare_paths(raw_dir, jit_cache_dir, checkpoint_root, record_path)
    _emit_marker(
        raw_dir,
        "paths_ready",
        args.expected_source_sha,
        worker_raw_dir=str(raw_dir),
        marker_dir=str(raw_dir / "markers"),
        jit_cache_dir=str(jit_cache_dir),
        checkpoint_root=str(checkpoint_root),
        record_path=str(record_path),
        isolated_jit_cache=True,
    )

    from mpi4py import MPI
    from petsc4py import PETSc
    from src.common.config_3d import target_stage4_config
    from src.solvers.fullspace_lor_native_hx_fixture import (
        build_frozen_fullspace_primal_source,
    )
    from src.solvers.fullspace_memory_first_krylov import (
        destroy_krylov_result,
        run_restart20_cycles,
        write_solution_checkpoint,
    )
    from src.solvers.fullspace_same_mesh_hcurl_pmg_global import (
        _algebraic_fine_function,
    )
    from src.solvers.fullspace_same_mesh_hcurl_pmg_setup import (
        audit_p6_same_mesh_setup,
        build_p6_same_mesh_setup,
        destroy_p6_same_mesh_setup_bundle,
    )

    comm = MPI.COMM_WORLD
    validate_profile(args.stage, args.case, args.source, comm.size)
    source = _source_facts(root, args.expected_source_sha, comm, PETSc)
    cfg = target_stage4_config(degree=6, h_nm=10.0)
    bundle: dict[str, Any] = {}
    result: dict[str, Any] | None = None
    source_vec: Any = None
    algebraic_function: Any = None
    algebraic_input: Any = None
    rhs: Any = None
    rhs_repeat: Any = None
    final_action: Any = None
    final_residual: Any = None
    setup_audit: dict[str, Any] | None = None
    npz_facts: dict[str, Any] | None = None
    record: dict[str, Any] | None = None
    try:
        bundle = build_p6_same_mesh_setup(cfg, comm)
        _emit_marker(raw_dir, "bundle_built", args.expected_source_sha)
        setup_audit = dict(audit_p6_same_mesh_setup(bundle))
        setup_audit["coefficient_audit"] = _jsonable(bundle["coefficient_audit"])
        fine_mpc = bundle["floquets"][6]
        slaves = _owned_slaves(bundle)
        source_vec, source_facts = build_frozen_fullspace_primal_source(
            bundle["spaces"][6], fine_mpc, cfg, args.source
        )
        source_before = _vector_values(source_vec)
        algebraic_function = _algebraic_fine_function(
            source_vec, fine_mpc.mpc.function_space, fine_mpc
        )
        algebraic_input = bundle["p6_shell"].matrix.createVecRight()
        algebraic_function.x.petsc_vec.copy(algebraic_input)
        algebraic_before = _vector_values(algebraic_input)
        p6_matrix = bundle["p6_shell"].matrix
        rhs = p6_matrix.createVecLeft()
        rhs_repeat = p6_matrix.createVecLeft()
        p6_matrix.mult(algebraic_input, rhs)
        p6_matrix.mult(algebraic_input, rhs_repeat)
        rhs_before = _vector_values(rhs)
        rhs_repeat_values = _vector_values(rhs_repeat)
        source_facts = dict(source_facts)
        source_facts.update(
            {
                "source_generation": "build_frozen_fullspace_primal_source",
                "source_role": "full_fe_primal_diagnostic_solution",
                "phase_application": source_facts.get("phase_application"),
            }
        )
        _emit_marker(
            raw_dir,
            "source_built",
            args.expected_source_sha,
            source_name=args.source,
            source_role="full_fe_primal_diagnostic_solution",
            source_generation="build_frozen_fullspace_primal_source",
        )
        source_authority = {
            "source_name": args.source,
            "source_facts": _jsonable(source_facts),
            "full_source_array_sha256": _array_sha(source_before),
            "algebraic_input_array_sha256": _array_sha(algebraic_before),
            "input_path": str(input_path),
            "input_sha256": _sha256_file(input_path),
        }
        operator_authority = _operator_authority(setup_audit)
        physical_authority = {
            "profile": {
                "wavelength_nm": 13.5,
                "mesh_target_size_nm": 10.0,
                "nedelec_degree": 6,
                "same_physical_mesh": True,
            },
            "input_sha256": _sha256_file(input_path),
            "coefficient_audit": _jsonable(bundle["coefficient_audit"]),
        }
        identities = {
            "input_identity_authority": source_authority,
            "input_identity_sha256": _stable_sha(source_authority),
            "operator_identity_authority": operator_authority,
            "operator_identity_sha256": _stable_sha(operator_authority),
            "physical_model_authority": physical_authority,
            "physical_model_sha256": _stable_sha(physical_authority),
        }
        _emit_marker(
            raw_dir,
            "solve_started",
            args.expected_source_sha,
            source=args.source,
            ksp_type="gmres",
            restart=RESTART,
            cycle_max_it=CYCLE_MAX_IT,
            max_it=MAX_IT,
            zero_initial_guess=True,
        )
        action_calls = 0
        pc_apply_facts: list[dict[str, Any]] = []

        def apply_action(vector: Any) -> Any:
            nonlocal action_calls
            target = p6_matrix.createVecLeft()
            p6_matrix.mult(vector, target)
            action_calls += 1
            return target

        def apply_preconditioner(vector: Any) -> Any:
            output = bundle["upper_cycle"].apply(vector)
            facts = dict(bundle["upper_cycle"].last_apply_facts)
            lower = dict(facts["lower_cycle_facts"])
            pc_apply_facts.append(
                {
                    "apply_index": len(pc_apply_facts),
                    "p6_smoother_apply_count": int(facts["p6_smoother_apply_count"]),
                    "p63_adjoint_count": int(facts["p63_adjoint_count"]),
                    "p63_primal_count": int(facts["p63_primal_count"]),
                    "lower_cycle_count": int(facts["lower_cycle_count"]),
                    "p1_solve_count": int(facts["p1_solve_count"]),
                    "p1_relative_residual": float(lower["p1_relative_residual"]),
                    "output_finite": bool(facts["output_finite"]),
                    "owned_slave_max": float(facts["owned_slave_max"]),
                }
            )
            return output

        def checkpoint_writer(iteration: int, solution: Any, residual: float) -> Mapping[str, Any]:
            checkpoint_dir = checkpoint_root / f"checkpoint-{int(iteration)}"
            start, stop = solution.getOwnershipRange()
            ownership = {
                "rank": int(comm.rank),
                "ownership_range": [int(start), int(stop)],
                "local_size": int(solution.getLocalSize()),
                "global_size": int(solution.getSize()),
            }
            return write_solution_checkpoint(
                checkpoint_dir,
                solution,
                iteration=int(iteration),
                explicit_true_residual=float(residual),
                input_identity_sha256=identities["input_identity_sha256"],
                operator_identity_sha256=identities["operator_identity_sha256"],
                physical_model_sha256=identities["physical_model_sha256"],
                source_sha=args.expected_source_sha,
                ownership=ownership,
                comm=comm,
            )

        result = run_restart20_cycles(
            rhs,
            apply_action,
            apply_preconditioner,
            max_it=MAX_IT,
            residual_limit=RESIDUAL_LIMIT,
            resource_sample=_resource_sample,
            start_iteration=0,
            checkpoint_writer=checkpoint_writer,
            first_checkpoint_iteration=None,
            checkpoint_interval=CHECKPOINT_INTERVAL,
            stop_on_true_residual=True,
        )
        final_solution = result["final_solution"]
        final_action = apply_action(final_solution)
        final_residual = rhs.copy()
        final_residual.axpy(PETSc.ScalarType(-1.0), final_action)
        source_after = _vector_values(source_vec)
        algebraic_after = _vector_values(algebraic_input)
        rhs_after = _vector_values(rhs)
        final_solution_values = _vector_values(final_solution)
        final_action_values = _vector_values(final_action)
        final_residual_values = _vector_values(final_residual)
        npz_facts = _write_probe_npz(
            raw_dir,
            {
                "source_before": source_before,
                "source_after": source_after,
                "input_before": algebraic_before,
                "input_after": algebraic_after,
                "rhs_before": rhs_before,
                "rhs_after": rhs_after,
                "rhs_repeat": rhs_repeat_values,
                "final_solution": final_solution_values,
                "final_action": final_action_values,
                "final_true_residual": final_residual_values,
            },
        )
        source_vector_facts = _vector_facts(source_before)
        source_vector_facts["after"] = _vector_facts(source_after)
        algebraic_input_facts = _vector_facts(algebraic_before, slaves)
        algebraic_input_facts["after"] = _vector_facts(algebraic_after, slaves)
        rhs_fact = _vector_facts(rhs_before, slaves)
        rhs_repeat_fact = _vector_facts(rhs_repeat_values, slaves)
        setup_audit["coefficient_audit"] = _jsonable(bundle["coefficient_audit"])
        provenance = dict(source)
        provenance.update(
            {
                "stage": STAGE,
                "case": CASE,
                "source_name": args.source,
                "input_path": str(input_path),
                "input_sha256": _sha256_file(input_path),
                "raw_dir": str(raw_dir),
                "checkpoint_root": str(checkpoint_root),
                "record_path": str(record_path),
                "jit_cache_dir": str(jit_cache_dir),
                "isolated_jit_cache": True,
                "command": list(command),
            }
        )
        record = _record(
            raw_dir=raw_dir,
            checkpoint_root=checkpoint_root,
            record_path=record_path,
            command=command,
            source=source,
            source_name=args.source,
            source_facts=source_facts,
            setup_audit=setup_audit,
            provenance=provenance,
            identities=identities,
            source_vector_facts=source_vector_facts,
            algebraic_input_facts=algebraic_input_facts,
            rhs_facts=rhs_fact,
            rhs_repeat_facts=rhs_repeat_fact,
            result=result,
            pc_apply_facts=pc_apply_facts,
            npz_facts=npz_facts,
            action_calls=action_calls,
        )
        record["source"]["owned_slave_indices"] = [int(value) for value in slaves]
        record["source"]["full_vector"]["array_sha256"] = _array_sha(source_before)
        record["krylov"]["final_output"] = _vector_facts(final_solution_values, slaves)
        record["krylov"]["final_action"] = _vector_facts(final_action_values, slaves)
        record["krylov"]["final_true_residual_facts"] = _vector_facts(
            final_residual_values, slaves
        )
        _emit_marker(
            raw_dir,
            "solve_complete",
            args.expected_source_sha,
            iterations=int(result["iterations"]),
            final_true_residual=float(result["final_true_residual"]),
            checkpoint_count=len(result["checkpoint_facts"]),
        )
        # Drop all NumPy snapshots before the retained-window measurement.
        del source_before, source_after, algebraic_before, algebraic_after
        del rhs_before, rhs_after, rhs_repeat_values
        del final_solution_values, final_action_values, final_residual_values
        # The retained window contains the setup bundle and the final Krylov Vec.
        for vector in (final_action, final_residual, rhs_repeat, rhs, algebraic_input, source_vec):
            if vector is not None:
                vector.destroy()
        final_action = None
        final_residual = None
        rhs_repeat = None
        rhs = None
        algebraic_input = None
        source_vec = None
        algebraic_function = None
        _emit_marker(
            raw_dir,
            "retained_ready",
            args.expected_source_sha,
            retained_dwell_seconds=RETAINED_DWELL_SECONDS,
            retained_authority="external_foundation_watchdog_process_tree",
            retained_warning_bytes=RETAINED_WARNING,
        )
        time.sleep(RETAINED_DWELL_SECONDS)
        _emit_marker(
            raw_dir,
            "retained_observed",
            args.expected_source_sha,
            retained_dwell_seconds=RETAINED_DWELL_SECONDS,
        )
        destroy_krylov_result(result)
        result = None
        _emit_marker(raw_dir, "krylov_destroyed", args.expected_source_sha)
        destroy_p6_same_mesh_setup_bundle(bundle)
        bundle = {}
        _emit_marker(raw_dir, "bundle_destroyed", args.expected_source_sha)
        assert record is not None
        _write_json(record_path, record)
        _emit_marker(
            raw_dir,
            "record_written",
            args.expected_source_sha,
            record_path=str(record_path),
            record_sha256=_sha256_file(record_path),
        )
    finally:
        if result is not None:
            destroy_krylov_result(result)
        for vector in (final_action, final_residual, rhs_repeat, rhs, algebraic_input, source_vec):
            if vector is not None:
                vector.destroy()
        if bundle:
            destroy_p6_same_mesh_setup_bundle(bundle)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=(STAGE,), required=True)
    parser.add_argument("--case", choices=(CASE,), required=True)
    parser.add_argument("--source", choices=SOURCES, required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--jit-cache-dir", type=Path, required=True)
    parser.add_argument("--checkpoint-root", type=Path, required=True)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--expected-mpi-size", type=int, required=True)
    parser.add_argument("--input", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.expected_mpi_size != 1:
        raise ValueError("positive worker expected MPI size is fixed to one")
    run_worker(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "BRANCH",
    "CASE",
    "CHECKPOINT_INTERVAL",
    "COLD_RSS_LIMIT",
    "CYCLE_MAX_IT",
    "LEVELS",
    "MARKERS",
    "MARKER_SCHEMA",
    "MAX_IT",
    "MODULE",
    "PAIRS",
    "RECORD_SCHEMA",
    "RESTART",
    "RESIDUAL_LIMIT",
    "RETAINED_WARNING",
    "SOURCES",
    "STAGE",
    "_emit_marker",
    "_prepare_paths",
    "build_parser",
    "main",
    "run_worker",
    "validate_profile",
]
