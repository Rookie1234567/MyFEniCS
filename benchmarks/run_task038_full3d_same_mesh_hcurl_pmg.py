"""Thin p3/h50 same-mesh positive-candidate runner.

The numerical construction is in ``src.solvers.fullspace_same_mesh_hcurl_pmg_global``;
this file only fixes the small profile, connects the existing restart-20
driver, and serializes raw facts.  It is not a p6, physical, or formal Route-A
or Route-B runner.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
import hashlib
import json
import os
from pathlib import Path
import sys
import subprocess
from typing import Any, Callable

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from benchmarks.task034_wsl_resources import resource_authority_sample
from src.common.config_3d import target_stage4_config
from src.solvers.fullspace_memory_first_krylov import (
    run_restart20_cycles,
    write_solution_checkpoint,
)
from src.solvers.fullspace_same_mesh_hcurl_pmg_global import (
    audit_small_same_mesh_structure,
    build_small_same_mesh_positive_case,
    destroy_small_same_mesh_positive_case,
)


SMALL_RECORD_SCHEMA = "task038.full3d.same-mesh-hcurl-pmg.small-record.v1"
SMALL_STAGE = "c1-small"
SMALL_CASE_PREFIX = "p3-h50-mpi"
SMALL_SOURCE_NAMES = ("random", "gradient", "curl", "checkerboard")
SMALL_RESTART = 20
SMALL_MAX_IT = 10_000
SMALL_CHECKPOINT_INTERVAL = 500
SMALL_RESIDUAL_LIMIT = 1.0e-8
BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"
SMALL_MODULE = "benchmarks.run_task038_full3d_same_mesh_hcurl_pmg"


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        return _jsonable(value.tolist())
    if isinstance(value, (np.integer, np.floating, np.bool_)):
        return _jsonable(value.item())
    if isinstance(value, complex):
        return {"real": float(value.real), "imag": float(value.imag)}
    return value


def validate_small_profile(
    stage: str, case: str, source_name: str, mpi_size: int
) -> None:
    """Validate the one prospective profile without accepting a variant."""

    mpi_size = int(mpi_size)
    if stage != SMALL_STAGE:
        raise ValueError(f"small candidate stage must be {SMALL_STAGE!r}")
    if case != f"{SMALL_CASE_PREFIX}{mpi_size}":
        raise ValueError("small candidate case must be p3-h50-mpi1 or p3-h50-mpi2")
    if mpi_size not in (1, 2):
        raise ValueError("small candidate supports MPI1 or MPI2 only")
    if source_name not in SMALL_SOURCE_NAMES:
        raise ValueError(f"unknown frozen source {source_name!r}")


def _matrix_facts(matrix: Any) -> dict[str, object]:
    rows, columns = (int(value) for value in matrix.getSize())
    local_rows, local_columns = (int(value) for value in matrix.getLocalSize())
    comm = matrix.getComm().tompi4py()
    info = matrix.getInfo(PETSc.Mat.InfoType.LOCAL)
    local_nnz = int(info.get("nz_used", 0))
    global_nnz = int(comm.allreduce(local_nnz, op=MPI.SUM))
    diagonal = matrix.createVecRight()
    try:
        matrix.getDiagonal(diagonal)
        diagonal_values = np.asarray(diagonal.array, dtype=np.complex128)
        finite_local = bool(np.all(np.isfinite(diagonal_values)))
        positive_local = bool(
            finite_local
            and np.all(np.abs(diagonal_values.imag) <= 1.0e-12)
            and np.all(diagonal_values.real > 0.0)
        )
    finally:
        diagonal.destroy()
    return {
        "rows": rows,
        "cols": columns,
        "local_rows": local_rows,
        "local_cols": local_columns,
        "global_nnz": global_nnz,
        "finite_diagonal": bool(comm.allreduce(int(finite_local), op=MPI.MIN)),
        "positive_diagonal": bool(comm.allreduce(int(positive_local), op=MPI.MIN)),
    }


def _operator_identity_authority(
    pmg_audit: Mapping[str, Any],
    global_matrix_facts: Mapping[str, Any],
    global_coefficient_audit: Mapping[str, Any],
    global_owned_slave_count: int,
) -> dict[str, Any]:
    """Build the MPI-invariant operator identity from global facts only."""

    architecture = _jsonable(pmg_audit)
    local_count = architecture.pop("fine_owned_mpc_slave_count", None)
    if type(local_count) is not int or local_count < 0:
        raise ValueError("fine local owned-slave count is not a nonnegative integer")
    if type(global_owned_slave_count) is not int or global_owned_slave_count < 0:
        raise ValueError("fine global owned-slave count is not a nonnegative integer")
    architecture["fine_global_owned_mpc_slave_count"] = global_owned_slave_count
    return {
        "architecture": architecture,
        "matrix_facts": _jsonable(global_matrix_facts),
        "coefficient_audit": _jsonable(global_coefficient_audit),
        "matrix_free_action": "FullspaceMpcFormAction",
        "same_form": "curl_plus_mass",
    }


def _source_preflight(expected_source_sha: str) -> dict[str, str]:
    repo = Path(__file__).resolve().parents[1]
    git = ["git", "--git-dir=.git-codex", "--work-tree=."]
    actual_sha = subprocess.check_output(
        [*git, "rev-parse", "HEAD"], cwd=repo, text=True
    ).strip()
    actual_branch = subprocess.check_output(
        [*git, "branch", "--show-current"], cwd=repo, text=True
    ).strip()
    status = subprocess.check_output(
        [*git, "status", "--porcelain", "--untracked-files=all"],
        cwd=repo,
        text=True,
    )
    if actual_sha != expected_source_sha:
        raise RuntimeError(
            f"small candidate source SHA mismatch: {actual_sha} != {expected_source_sha}"
        )
    if actual_branch != BRANCH:
        raise RuntimeError(f"small candidate branch mismatch: {actual_branch!r}")
    if status:
        raise RuntimeError("small candidate requires a clean tracked source tree")
    return {"sha": actual_sha, "branch": actual_branch}


def _provenance_identities(
    case_bundle: Mapping[str, Any],
    *,
    source_name: str,
    source_sha: str,
    input_path: Path,
) -> dict[str, Any]:
    input_path = Path(input_path).resolve()
    input_sha = _sha256_file(input_path)
    source_facts = _jsonable(case_bundle["source_facts"])
    matrix_facts = {
        "fine": _matrix_facts(case_bundle["fine_matrix"]),
        "coarse": _matrix_facts(case_bundle["coarse_matrix"]),
    }
    global_matrix_facts = {
        name: {
            key: value
            for key, value in facts.items()
            if key not in {"local_rows", "local_cols"}
        }
        for name, facts in matrix_facts.items()
    }
    coefficient_audit = case_bundle["coefficient_audit"]
    global_coefficient_audit = {
        "cell_counts": _jsonable(coefficient_audit["cell_counts"]),
        "positive_coefficients": _jsonable(
            coefficient_audit["positive_coefficients"]
        ),
        "global_cell_count": int(sum(coefficient_audit["cell_counts"].values())),
    }
    authority = {
        "source_name": source_name,
        "source_sha": source_sha,
        "source_facts": source_facts,
        "input_path": str(input_path),
        "input_sha256": input_sha,
        "dtype": "complex128",
        "ownership": "PETSc owner-local",
    }
    comm = case_bundle["fine_matrix"].getComm().tompi4py()
    local_owned_slave_count = int(
        case_bundle["pmg"].audit["fine_owned_mpc_slave_count"]
    )
    global_owned_slave_count = int(
        comm.allreduce(local_owned_slave_count, op=MPI.SUM)
    )
    operator = _operator_identity_authority(
        case_bundle["pmg"].audit,
        global_matrix_facts,
        global_coefficient_audit,
        global_owned_slave_count,
    )
    physical = {
        "input_identity_sha256": _sha256_bytes(
            json.dumps(
                authority, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode("utf-8")
        ),
        "coefficient_audit": global_coefficient_audit,
    }
    return {
        "source_sha": source_sha,
        "input_path": str(input_path),
        "input_sha256": input_sha,
        "input_identity_authority": authority,
        "input_identity_sha256": _sha256_bytes(
            json.dumps(
                authority, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode("utf-8")
        ),
        "operator_identity_authority": operator,
        "operator_identity_sha256": _sha256_bytes(
            json.dumps(
                operator, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode("utf-8")
        ),
        "physical_model_sha256": _sha256_bytes(
            json.dumps(
                physical, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode("utf-8")
        ),
        "rank_facts": {
            "fine_owned_mpc_slave_count": local_owned_slave_count,
        },
    }


def _vector_relative(left: Any, right: Any) -> float:
    difference = left.copy()
    try:
        difference.axpy(-1.0, right)
        numerator = float(difference.norm())
        denominator = max(float(right.norm()), np.finfo(np.float64).tiny)
    finally:
        difference.destroy()
    return numerator / denominator


def qualify_one_vcycle(case_bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Record one bounded, independent PMG qualification before Krylov."""

    pmg = case_bundle["pmg"]
    base = case_bundle["rhs"].copy()
    second = case_bundle["rhs"].copy()
    diagonal = case_bundle["fine_matrix"].createVecRight()
    case_bundle["fine_matrix"].getDiagonal(diagonal)
    second.pointwiseMult(second, diagonal)
    diagonal.destroy()
    alpha = 0.37 - 0.19j
    beta = -0.23 + 0.41j
    combo = base.copy()
    combo.scale(alpha)
    combo.axpy(beta, second)
    base_before = np.asarray(base.array).copy()
    second_before = np.asarray(second.array).copy()
    combo_before = np.asarray(combo.array).copy()
    outputs: list[Any] = []
    apply_facts: list[Mapping[str, Any]] = []
    try:
        for vector in (base, second, base, combo):
            output = pmg.apply(vector)
            outputs.append(output)
            apply_facts.append(dict(pmg.last_apply_facts))
        expected = outputs[0].copy()
        expected.scale(alpha)
        expected.axpy(beta, outputs[1])
        comm = case_bundle["fine_matrix"].getComm().tompi4py()
        finite_local = all(
            bool(np.all(np.isfinite(np.asarray(output.array))))
            for output in outputs
        )
        input_local = bool(
            np.array_equal(np.asarray(base.array), base_before)
            and np.array_equal(np.asarray(second.array), second_before)
            and np.array_equal(np.asarray(combo.array), combo_before)
        )
        count_ok = all(
            facts.get("smoother_apply_count") == 2
            and facts.get("transfer_3_1_adjoint_count") == 1
            and facts.get("transfer_3_1_primal_count") == 1
            and facts.get("p1_solve_count") == 1
            for facts in apply_facts
        )
        p1_residuals = [
            float(facts.get("p1_relative_residual", np.inf))
            for facts in apply_facts
        ]
        slave_maxima = [
            float(facts.get("owned_slave_max", np.inf))
            for facts in apply_facts
        ]
        return {
            "probe_apply_count": 4,
            "finite": bool(comm.allreduce(int(finite_local), op=MPI.MIN)),
            "input_unchanged": bool(
                comm.allreduce(int(input_local), op=MPI.MIN)
            ),
            "repeat_relative": _vector_relative(outputs[0], outputs[2]),
            "linearity_relative": _vector_relative(outputs[3], expected),
            "each_apply_counts": count_ok,
            "smoother_apply_total": int(
                apply_facts[-1]["smoother_apply_total"]
            ),
            "transfer_3_1_adjoint_total": int(
                apply_facts[-1]["transfer_3_1_adjoint_total"]
            ),
            "transfer_3_1_primal_total": int(
                apply_facts[-1]["transfer_3_1_primal_total"]
            ),
            "p1_solve_total": int(apply_facts[-1]["p1_solve_total"]),
            "p1_relative_residual_max": max(p1_residuals),
            "owned_slave_max": max(slave_maxima),
            "alpha": {"real": alpha.real, "imag": alpha.imag},
            "beta": {"real": beta.real, "imag": beta.imag},
        }
    finally:
        expected = locals().get("expected")
        if expected is not None:
            expected.destroy()
        for output in outputs:
            output.destroy()
        base.destroy()
        second.destroy()
        combo.destroy()


def build_small_record(
    case_bundle: Mapping[str, Any],
    result: Mapping[str, Any],
    *,
    stage: str,
    case: str,
    source_name: str,
    mpi_size: int,
    command: list[str],
    provenance: Mapping[str, Any],
) -> dict[str, Any]:
    """Create a raw-facts record; no worker status or classification is written."""

    validate_small_profile(stage, case, source_name, mpi_size)
    if list(provenance.get("command", ())) != list(command):
        raise ValueError("small candidate provenance command is not exact")
    pmg = case_bundle["pmg"]
    architecture = dict(pmg.audit)
    architecture["fine_global_owned_mpc_slave_count"] = int(
        provenance["operator_identity_authority"]["architecture"][
            "fine_global_owned_mpc_slave_count"
        ]
    )
    record: dict[str, Any] = {
        "schema": SMALL_RECORD_SCHEMA,
        "stage": stage,
        "case": case,
        "source_name": source_name,
        "mpi_size": int(mpi_size),
        "branch": BRANCH,
        "command": list(command),
        "provenance": _jsonable(provenance),
        "settings": {
            "levels": [3, 1],
            "transfer_pair": [3, 1],
            "ksp_type": "gmres",
            "pc_side": "right",
            "restart": SMALL_RESTART,
            "max_it": SMALL_MAX_IT,
            "replacement_interval": SMALL_RESTART,
            "checkpoint_interval": SMALL_CHECKPOINT_INTERVAL,
            "residual_limit": SMALL_RESIDUAL_LIMIT,
            "zero_initial_guess": True,
        },
        "architecture": architecture,
        "matrices": {
            "fine": _matrix_facts(case_bundle["fine_matrix"]),
            "coarse": _matrix_facts(case_bundle["coarse_matrix"]),
            "same_physical_mesh": True,
        },
        "local_transfer": _jsonable(case_bundle["local_transfer"].audit),
        "material": _jsonable(case_bundle["coefficient_audit"]),
        "transfer": _jsonable(case_bundle["owner_transfer"].audit),
        "vcycle": {
            "audit": _jsonable(architecture),
            "last_apply": _jsonable(pmg.last_apply_facts),
        },
        "vcycle_qualification": _jsonable(
            case_bundle.get("vcycle_qualification", {})
        ),
        "structure": _jsonable(case_bundle.get("structure_audit", {})),
        "source": _jsonable(case_bundle["source_facts"]),
        "krylov": _jsonable(dict(result)),
    }
    record["krylov"].pop("final_solution", None)
    return record


def write_small_record(path: Path, record: Mapping[str, Any]) -> None:
    """Write one strict JSON raw-facts record without creating a second schema."""

    path = Path(path)
    if path.exists():
        raise FileExistsError(f"small candidate record already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        _jsonable(record),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    path.write_bytes(payload + b"\n")


def run_small_candidate(
    case_bundle: Mapping[str, Any],
    *,
    stage: str,
    case: str,
    source_name: str,
    mpi_size: int,
    resource_sample: Callable[[], Mapping[str, Any]],
    checkpoint_writer: Callable[[int, Any, float], Mapping[str, Any]],
    provenance: Mapping[str, Any],
    command: list[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run the fixed restart-20 driver with the rank-root resource diagnostic."""

    validate_small_profile(stage, case, source_name, mpi_size)
    if not callable(resource_sample):
        raise ValueError("a process-tree resource sampler is required")
    fine_matrix = case_bundle["fine_matrix"]
    pmg = case_bundle["pmg"]
    rhs = case_bundle["rhs"]

    def apply_action(vector: Any) -> Any:
        target = fine_matrix.createVecLeft()
        fine_matrix.mult(vector, target)
        return target

    result = run_restart20_cycles(
        rhs,
        apply_action,
        pmg.apply,
        max_it=SMALL_MAX_IT,
        residual_limit=SMALL_RESIDUAL_LIMIT,
        resource_sample=resource_sample,
        start_iteration=0,
        checkpoint_writer=checkpoint_writer,
        first_checkpoint_iteration=SMALL_CHECKPOINT_INTERVAL,
        checkpoint_interval=SMALL_CHECKPOINT_INTERVAL,
    )
    return result, build_small_record(
        case_bundle,
        result,
        stage=stage,
        case=case,
        source_name=source_name,
        mpi_size=mpi_size,
        command=command,
        provenance=provenance,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", default=SMALL_STAGE)
    parser.add_argument("--case", required=True)
    parser.add_argument("--source", choices=SMALL_SOURCE_NAMES, default="random")
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--checkpoint-root", type=Path, required=True)
    parser.add_argument("--record", type=Path, required=True)
    args = parser.parse_args(argv)
    mpi_size = int(MPI.COMM_WORLD.size)
    validate_small_profile(args.stage, args.case, args.source, mpi_size)
    if (
        len(args.expected_source_sha) != 40
        or any(character not in "0123456789abcdef" for character in args.expected_source_sha)
    ):
        raise ValueError("expected-source-sha must be a lowercase 40-character SHA")
    if not args.input.is_absolute() or not args.checkpoint_root.is_absolute() or not args.record.is_absolute():
        raise ValueError("small candidate input, checkpoint root, and record must be absolute")
    _source_preflight(args.expected_source_sha)
    if np.dtype(PETSc.ScalarType) != np.dtype(np.complex128):
        raise TypeError("small candidate requires complex128 PETSc")
    if np.dtype(PETSc.IntType) != np.dtype(np.int32):
        raise TypeError("small candidate requires int32 PETSc indices")
    input_path = args.input.resolve()
    if not input_path.is_file():
        raise FileNotFoundError(f"small candidate input does not exist: {input_path}")
    if os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION") != "1":
        raise RuntimeError("small candidate requires qualified activation")
    thread_facts = {
        name: os.environ.get(name, "1")
        for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")
    }
    if any(value != "1" for value in thread_facts.values()):
        raise RuntimeError("small candidate requires one thread in each BLAS setting")
    command = [sys.executable, "-m", SMALL_MODULE, *sys.argv[1:]]
    checkpoint_root = args.checkpoint_root.resolve()
    root_exists = bool(MPI.COMM_WORLD.allreduce(int(checkpoint_root.exists()), op=MPI.MAX))
    if root_exists:
        raise FileExistsError(f"small candidate checkpoint root already exists: {checkpoint_root}")
    checkpoint_error = None
    if MPI.COMM_WORLD.rank == 0:
        try:
            checkpoint_root.mkdir(parents=False, exist_ok=False)
        except Exception as exc:
            checkpoint_error = f"{type(exc).__name__}: {exc}"
    checkpoint_error = MPI.COMM_WORLD.bcast(checkpoint_error, root=0)
    if checkpoint_error is not None:
        raise RuntimeError(f"small candidate checkpoint root creation failed: {checkpoint_error}")
    MPI.COMM_WORLD.Barrier()
    cfg = target_stage4_config(degree=3, h_nm=50.0)
    bundle = build_small_same_mesh_positive_case(
        cfg, MPI.COMM_WORLD, source_name=args.source
    )
    result = None
    try:
        provenance = _provenance_identities(
            bundle,
            source_name=args.source,
            source_sha=args.expected_source_sha,
            input_path=input_path,
        )
        bundle["structure_audit"] = audit_small_same_mesh_structure(bundle)
        bundle["fine_action"].destroy()
        bundle.pop("fine_action")
        bundle["vcycle_qualification"] = qualify_one_vcycle(bundle)
        provenance.update(
            {
                "branch": BRANCH,
                "qualified_activation": "1",
                "python_executable": sys.executable,
                "mpi_size": mpi_size,
                "threads": thread_facts,
                "command": command,
            }
        )

        def checkpoint_writer(
            iteration: int, solution: Any, residual: float
        ) -> Mapping[str, Any]:
            checkpoint_dir = checkpoint_root / f"checkpoint-{int(iteration)}"
            start, stop = solution.getOwnershipRange()
            ownership = {
                "rank": int(MPI.COMM_WORLD.rank),
                "ownership_range": [int(start), int(stop)],
                "local_size": int(solution.getLocalSize()),
                "global_size": int(solution.getSize()),
            }
            return write_solution_checkpoint(
                checkpoint_dir,
                solution,
                iteration=int(iteration),
                explicit_true_residual=float(residual),
                input_identity_sha256=str(provenance["input_identity_sha256"]),
                operator_identity_sha256=str(provenance["operator_identity_sha256"]),
                physical_model_sha256=str(provenance["physical_model_sha256"]),
                source_sha=args.expected_source_sha,
                ownership=ownership,
                comm=MPI.COMM_WORLD,
            )

        result, record = run_small_candidate(
            bundle,
            stage=args.stage,
            case=args.case,
            source_name=args.source,
            mpi_size=mpi_size,
            resource_sample=lambda: {
                **dict(resource_authority_sample(os.getpid())),
                "scope": "rank-root-diagnostic",
                "process_tree_gate": False,
            },
            checkpoint_writer=checkpoint_writer,
            provenance=provenance,
            command=command,
        )
        MPI.COMM_WORLD.Barrier()
        if MPI.COMM_WORLD.rank == 0:
            write_small_record(args.record, record)
        if MPI.COMM_WORLD.rank == 0:
            print(json.dumps({"record": str(args.record.resolve())}, sort_keys=True), flush=True)
    finally:
        if result is not None:
            final_solution = result.pop("final_solution", None)
            if final_solution is not None:
                final_solution.destroy()
        destroy_small_same_mesh_positive_case(bundle)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "BRANCH",
    "SMALL_CASE_PREFIX",
    "SMALL_CHECKPOINT_INTERVAL",
    "SMALL_MAX_IT",
    "SMALL_RECORD_SCHEMA",
    "SMALL_RESIDUAL_LIMIT",
    "SMALL_RESTART",
    "SMALL_SOURCE_NAMES",
    "SMALL_STAGE",
    "build_small_record",
    "qualify_one_vcycle",
    "main",
    "run_small_candidate",
    "validate_small_profile",
    "write_small_record",
]
