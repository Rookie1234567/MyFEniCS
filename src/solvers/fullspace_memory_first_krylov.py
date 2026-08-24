"""Reusable fixed-memory residual-authority and checkpoint primitives.

The memory-first lane keeps the frozen multiplicative-v1 HX operator outside this
module.  It supplies only the fixed restart-20 right-GMRES lifecycle, a small
cycle ledger, a residual-based pair bound, and solution-only checkpoints.  No
Krylov basis, action vector, or residual vector is retained by a completed
cycle.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
import hashlib
import json
from pathlib import Path
import time
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc


CHECKPOINT_SCHEMA = "fixed-memory-krylov.solution-checkpoint.v1"
GMRES_RESTART = 20
CYCLE_MAX_IT = 20
CHECKPOINT_INTERVAL = 200
MANDATORY_FIRST_CHECKPOINT = 20
SMALL_PAIR_MARGIN = 1.0e-11
PHYSICAL_PAIR_MARGIN = 1.0e-9
DIVERGED_ITS = -3


def _mpi_comm(comm: Any) -> MPI.Comm:
    """Return an mpi4py communicator for PETSc or mpi4py inputs."""

    converter = getattr(comm, "tompi4py", None)
    return converter() if converter is not None else comm


def residual_pair_bound(
    rho_one: float,
    rho_two: float,
    rhs_identity: float,
    *,
    physical: bool,
) -> float:
    """Return the V9 residual-based MPI action bound.

    The three measured inputs are deliberately required arguments.  A missing
    or non-finite measurement is a contract error, not a zero default.
    """

    values = (float(rho_one), float(rho_two), float(rhs_identity))
    if not all(np.isfinite(value) and value >= 0.0 for value in values):
        raise ValueError("pair-bound measurements must be finite and non-negative")
    margin = PHYSICAL_PAIR_MARGIN if physical else SMALL_PAIR_MARGIN
    return float(sum(values) + margin)


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
        .encode("utf-8")
        + b"\n"
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _vector_descriptor(path: Path, values: np.ndarray) -> dict[str, Any]:
    return {
        "relative_path": path.name,
        "bytes": int(path.stat().st_size),
        "sha256": _sha256(path),
        "dtype": str(values.dtype),
        "shape": list(values.shape),
    }


def _source_sha(value: str) -> str:
    value = str(value)
    if len(value) != 40 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError("source_sha must be a 40-character lowercase Git SHA")
    return value


def _identity_sha(value: str, name: str) -> str:
    value = str(value)
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{name} must be a 64-character lowercase SHA256")
    return value


def _ownership_fact(solution: PETSc.Vec, comm: MPI.Comm, ownership: Mapping[str, Any]) -> dict[str, Any]:
    required = {"rank", "ownership_range", "local_size", "global_size"}
    if set(ownership) != required:
        raise ValueError("ownership identity must contain exactly the required fields")
    rank = int(comm.Get_rank())
    local_size = int(solution.getLocalSize())
    global_size = int(solution.getSize())
    start, stop = solution.getOwnershipRange()
    expected = {
        "rank": rank,
        "ownership_range": [int(start), int(stop)],
        "local_size": local_size,
        "global_size": global_size,
    }
    if {str(key): ownership[key] for key in ownership} != expected:
        raise ValueError("ownership identity does not match the PETSc vector")
    return expected


def write_solution_checkpoint(
    checkpoint_dir: Path,
    solution: PETSc.Vec,
    *,
    iteration: int,
    explicit_true_residual: float,
    input_identity_sha256: str,
    operator_identity_sha256: str,
    physical_model_sha256: str,
    source_sha: str,
    ownership: Mapping[str, Any],
    comm: MPI.Comm,
) -> dict[str, Any]:
    """Write one fresh owned solution shard and a small metadata manifest.

    The roundtrip reference stays in the caller's memory; the checkpoint itself
    contains exactly one owned solution shard per rank.  All collectives in
    this writer are metadata-only; no numeric vector is gathered to root.
    """

    checkpoint_dir = Path(checkpoint_dir)
    comm = _mpi_comm(comm)
    input_identity_sha256 = _identity_sha(input_identity_sha256, "input_identity_sha256")
    operator_identity_sha256 = _identity_sha(operator_identity_sha256, "operator_identity_sha256")
    physical_model_sha256 = _identity_sha(physical_model_sha256, "physical_model_sha256")
    source_sha = _source_sha(source_sha)
    if int(iteration) < 0:
        raise ValueError("checkpoint iteration must be non-negative")
    explicit_true_residual = float(explicit_true_residual)
    if not np.isfinite(explicit_true_residual) or explicit_true_residual < 0.0:
        raise ValueError("checkpoint explicit_true_residual must be finite and non-negative")
    ownership_fact = _ownership_fact(solution, comm, ownership)

    exists = comm.allreduce(int(checkpoint_dir.exists()), op=MPI.MAX)
    if exists:
        raise FileExistsError(f"checkpoint directory already exists: {checkpoint_dir}")
    creation_error: str | None = None
    if comm.Get_rank() == 0:
        try:
            checkpoint_dir.mkdir(parents=False, exist_ok=False)
        except Exception as exc:
            creation_error = f"{type(exc).__name__}: {exc}"
    creation_error = comm.bcast(creation_error, root=0)
    if creation_error is not None:
        raise RuntimeError(f"checkpoint creation failed: {creation_error}")
    comm.Barrier()

    rank = int(comm.Get_rank())
    shard_error: str | None = None
    rank_fact: dict[str, Any] | None = None
    try:
        solution_values = np.asarray(
            solution.getArray(readonly=True), dtype=np.complex128
        ).copy()
        solution_path = checkpoint_dir / f"solution_rank{rank}.npy"
        np.save(solution_path, solution_values, allow_pickle=False)
        rank_fact = {
            "rank": rank,
            "ownership": ownership_fact,
            "solution": _vector_descriptor(solution_path, solution_values),
        }
    except Exception as exc:
        shard_error = f"{type(exc).__name__}: {exc}"
    shard_errors = comm.allgather(shard_error)
    if any(error is not None for error in shard_errors):
        raise RuntimeError(f"checkpoint shard write failed: {shard_errors}")
    assert rank_fact is not None
    rank_facts = comm.allgather(rank_fact)
    manifest_error: str | None = None
    manifest_path = checkpoint_dir / "manifest.json"
    if rank == 0:
        try:
            ordered_facts = sorted(rank_facts, key=lambda fact: int(fact["rank"]))
            manifest = {
                "schema": CHECKPOINT_SCHEMA,
                "iteration": int(iteration),
                "explicit_true_residual": explicit_true_residual,
                "input_identity_sha256": str(input_identity_sha256),
                "operator_identity_sha256": str(operator_identity_sha256),
                "physical_model_sha256": str(physical_model_sha256),
                "source_sha": source_sha,
                "mpi_size": int(comm.Get_size()),
                "solution_only": True,
                "numeric_allgather": False,
                "vector_roles": ["solution"],
                "forbidden_vector_roles": ["action", "residual", "krylov_basis"],
                "ranks": ordered_facts,
            }
            manifest_path.write_bytes(_json_bytes(manifest))
        except Exception as exc:
            manifest_error = f"{type(exc).__name__}: {exc}"
    manifest_error = comm.bcast(manifest_error, root=0)
    if manifest_error is not None:
        raise RuntimeError(f"checkpoint manifest failed: {manifest_error}")
    comm.Barrier()
    manifest_sha256 = _sha256(manifest_path)
    return {
        "schema": CHECKPOINT_SCHEMA,
        "manifest_path": str(manifest_path.resolve()),
        "manifest_sha256": manifest_sha256,
        "iteration": int(iteration),
        "explicit_true_residual": explicit_true_residual,
        "mpi_size": int(comm.Get_size()),
        "rank": rank,
        "ownership": ownership_fact,
        "vector_roles": ["solution"],
        "forbidden_vector_roles": ["action", "residual", "krylov_basis"],
        "numeric_allgather": False,
        "rank_facts": rank_facts,
    }


def _checkpoint_path(root: Path, relative_path: str) -> Path:
    path = (root / relative_path).resolve()
    if root.resolve() not in path.parents:
        raise ValueError("checkpoint artifact escapes its directory")
    return path


def read_solution_checkpoint(
    checkpoint_dir: Path,
    solution: PETSc.Vec,
    *,
    expected: Mapping[str, Any],
    ownership: Mapping[str, Any],
    comm: MPI.Comm,
) -> dict[str, Any]:
    """Validate and restore one rank's solution shard, fail-closed."""

    checkpoint_dir = Path(checkpoint_dir).resolve()
    comm = _mpi_comm(comm)
    manifest_path = checkpoint_dir / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"missing checkpoint manifest: {manifest_path}")
    actual_manifest_sha = _sha256(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    required_expected = {
        "iteration",
        "explicit_true_residual",
        "input_identity_sha256",
        "operator_identity_sha256",
        "physical_model_sha256",
        "source_sha",
        "mpi_size",
        "manifest_sha256",
    }
    if set(expected) != required_expected:
        raise ValueError("checkpoint expected identity is incomplete")
    _source_sha(str(expected["source_sha"]))
    for key in (
        "input_identity_sha256",
        "operator_identity_sha256",
        "physical_model_sha256",
    ):
        _identity_sha(str(expected[key]), key)
    for key in required_expected - {"explicit_true_residual"}:
        if key == "manifest_sha256":
            if str(expected[key]) != actual_manifest_sha:
                raise ValueError("checkpoint manifest SHA256 mismatch")
            continue
        if key not in manifest or manifest[key] != expected[key]:
            raise ValueError(f"checkpoint provenance mismatch for {key}")
    if manifest["schema"] != CHECKPOINT_SCHEMA:
        raise ValueError("checkpoint schema mismatch")
    if manifest["solution_only"] is not True:
        raise ValueError("checkpoint is not solution-only")
    if manifest["numeric_allgather"] is not False:
        raise ValueError("checkpoint numeric allgather contract failed")
    if "explicit_true_residual" not in manifest:
        raise ValueError("checkpoint explicit_true_residual is missing")
    explicit_true_residual = manifest["explicit_true_residual"]
    if (
        not isinstance(explicit_true_residual, (int, float))
        or not np.isfinite(float(explicit_true_residual))
        or float(explicit_true_residual) < 0.0
    ):
        raise ValueError("checkpoint explicit_true_residual is invalid")
    if not np.isclose(
        float(explicit_true_residual),
        float(expected["explicit_true_residual"]),
        rtol=1.0e-14,
        atol=1.0e-15,
    ):
        raise ValueError("checkpoint explicit_true_residual mismatch")
    if manifest["vector_roles"] != ["solution"]:
        raise ValueError("checkpoint contains an unexpected vector role")
    if set(manifest["forbidden_vector_roles"]) != {"action", "residual", "krylov_basis"}:
        raise ValueError("checkpoint forbidden-vector contract failed")
    if int(manifest["mpi_size"]) != int(comm.Get_size()):
        raise ValueError("checkpoint MPI size mismatch")

    rank = int(comm.Get_rank())
    ranks = manifest["ranks"]
    if not isinstance(ranks, list) or len(ranks) != int(comm.Get_size()):
        raise ValueError("checkpoint rank metadata is incomplete")
    rank_ids = [int(item["rank"]) for item in ranks]
    if sorted(rank_ids) != list(range(int(comm.Get_size()))):
        raise ValueError("checkpoint rank metadata is not a complete permutation")
    fact = next(item for item in ranks if int(item["rank"]) == rank)
    if fact["ownership"] != _ownership_fact(solution, comm, ownership):
        raise ValueError("checkpoint ownership mismatch")

    descriptor = fact["solution"]
    shard_path = _checkpoint_path(checkpoint_dir, str(descriptor["relative_path"]))
    if not shard_path.is_file():
        raise FileNotFoundError(f"missing checkpoint shard: {shard_path}")
    if int(descriptor["bytes"]) != shard_path.stat().st_size:
        raise ValueError("checkpoint shard byte count mismatch")
    if _sha256(shard_path) != str(descriptor["sha256"]):
        raise ValueError("checkpoint shard SHA256 mismatch")
    values = np.asarray(np.load(shard_path, allow_pickle=False))
    if str(values.dtype) != str(descriptor["dtype"]):
        raise ValueError("checkpoint shard dtype mismatch")
    if list(values.shape) != list(descriptor["shape"]):
        raise ValueError("checkpoint shard shape mismatch")
    if values.ndim != 1 or values.size != solution.getLocalSize():
        raise ValueError("checkpoint shard local size mismatch")
    if not np.all(np.isfinite(values)):
        raise ValueError("checkpoint shard contains non-finite values")
    solution.array[:] = values
    return {
        "manifest_sha256": _sha256(manifest_path),
        "iteration": int(manifest["iteration"]),
        "explicit_true_residual": float(explicit_true_residual),
        "rank": rank,
        "restored_shard_sha256": str(descriptor["sha256"]),
    }


class _ActionContext:
    def __init__(self, apply_action: Callable[[PETSc.Vec], PETSc.Vec]) -> None:
        self.apply_action = apply_action
        self.matvec_count = 0

    def mult(self, _matrix: PETSc.Mat, source: PETSc.Vec, target: PETSc.Vec) -> None:
        action = self.apply_action(source)
        try:
            action.copy(target)
        finally:
            action.destroy()
        self.matvec_count += 1


class _PCContext:
    def __init__(self, apply_preconditioner: Callable[[PETSc.Vec], PETSc.Vec]) -> None:
        self.apply_preconditioner = apply_preconditioner
        self.apply_count = 0

    def apply(self, _pc: PETSc.PC, source: PETSc.Vec, target: PETSc.Vec) -> None:
        correction = self.apply_preconditioner(source)
        try:
            correction.copy(target)
        finally:
            correction.destroy()
        self.apply_count += 1


def run_restart20_cycles(
    rhs: PETSc.Vec,
    apply_action: Callable[[PETSc.Vec], PETSc.Vec],
    apply_preconditioner: Callable[[PETSc.Vec], PETSc.Vec],
    *,
    max_it: int,
    residual_limit: float,
    resource_sample: Callable[[], Mapping[str, Any]],
    initial_solution: PETSc.Vec | None = None,
    start_iteration: int | None = None,
    checkpoint_writer: Callable[[int, PETSc.Vec, float], Mapping[str, Any]] | None = None,
    first_checkpoint_iteration: int | None = MANDATORY_FIRST_CHECKPOINT,
    checkpoint_interval: int = CHECKPOINT_INTERVAL,
    cycle_observer: Callable[[int, PETSc.Vec, Mapping[str, Any]], None] | None = None,
    stop_on_true_residual: bool = True,
) -> dict[str, Any]:
    """Run fixed restart-20 right-GMRES cycles with explicit replacement.

    ``max_it`` is a caller-authorized fixed cap and must be a positive
    multiple of 20.  The only convergence decision is the explicit residual
    computed after a cycle; PETSc's reported norm is retained as a fact.
    """

    max_it = int(max_it)
    if start_iteration is None:
        raise ValueError("start_iteration must be explicit, including for zero initial guess")
    start_iteration = int(start_iteration)
    residual_limit = float(residual_limit)
    if (
        max_it <= 0
        or max_it % GMRES_RESTART != 0
        or start_iteration < 0
        or start_iteration % GMRES_RESTART != 0
        or start_iteration > max_it
    ):
        raise ValueError("max_it must be a positive multiple of restart=20")
    checkpoint_interval = int(checkpoint_interval)
    if checkpoint_interval <= 0 or checkpoint_interval % GMRES_RESTART != 0:
        raise ValueError("checkpoint_interval must be a positive multiple of restart=20")
    if first_checkpoint_iteration is not None:
        first_checkpoint_iteration = int(first_checkpoint_iteration)
        if (
            first_checkpoint_iteration <= 0
            or first_checkpoint_iteration % GMRES_RESTART != 0
            or first_checkpoint_iteration > max_it
        ):
            raise ValueError(
                "first_checkpoint_iteration must be a positive restart boundary or None"
            )
    if not np.isfinite(residual_limit) or residual_limit < 0.0:
        raise ValueError("residual limit must be finite and non-negative")

    comm = _mpi_comm(rhs.getComm())
    sizes = (rhs.getLocalSize(), rhs.getSize())
    action_context = _ActionContext(apply_action)
    operator = PETSc.Mat().createPython(
        (sizes, sizes), context=action_context, comm=comm
    )
    operator.setUp()
    pc_context = _PCContext(apply_preconditioner)
    solution = operator.createVecRight()
    if initial_solution is None:
        if start_iteration != 0:
            operator.destroy()
            raise ValueError("zero initial guess must start at iteration zero")
        solution.set(0.0 + 0.0j)
        resumed = False
    else:
        if (
            initial_solution.getSize() != solution.getSize()
            or initial_solution.getLocalSize() != solution.getLocalSize()
            or initial_solution.getOwnershipRange() != solution.getOwnershipRange()
            or MPI.Comm.Compare(
                _mpi_comm(initial_solution.getComm()), _mpi_comm(solution.getComm())
            )
            not in (MPI.IDENT, MPI.CONGRUENT)
        ):
            operator.destroy()
            raise ValueError("initial solution has incompatible local ownership or communicator")
        initial_solution.copy(solution)
        resumed = True

    rhs_norm = max(float(rhs.norm()), np.finfo(float).tiny)
    exact_action_count = 1
    initial_action = apply_action(solution)
    initial_true = rhs.copy()
    initial_true.axpy(PETSc.ScalarType(-1.0), initial_action)
    initial_true_relative = float(initial_true.norm()) / rhs_norm
    initial_action.destroy()
    initial_true.destroy()
    cycles: list[dict[str, Any]] = []
    checkpoint_facts: list[dict[str, Any]] = []
    ksp_destroy_count = 0
    cumulative_iteration = start_iteration
    started = time.perf_counter()
    active_ksp: PETSc.KSP | None = None

    try:
        while cumulative_iteration < max_it:
            cycle_index = cumulative_iteration // GMRES_RESTART
            cycle_start = cumulative_iteration
            matvec_start = action_context.matvec_count
            pc_start = pc_context.apply_count
            active_ksp = PETSc.KSP().create(comm)
            active_ksp.setOperators(operator)
            active_ksp.setType("gmres")
            active_ksp.setGMRESRestart(GMRES_RESTART)
            active_ksp.setPCSide(PETSc.PC.Side.RIGHT)
            active_ksp.setNormType(PETSc.KSP.NormType.UNPRECONDITIONED)
            active_ksp.setInitialGuessNonzero(resumed or cycle_index > 0)
            active_ksp.setTolerances(
                rtol=0.0, atol=0.0, max_it=CYCLE_MAX_IT
            )
            pc = active_ksp.getPC()
            pc.setType(PETSc.PC.Type.PYTHON)
            pc.setPythonContext(pc_context)
            active_ksp.setUp()
            cycle_started = time.perf_counter()
            active_ksp.solve(rhs, solution)
            local_iterations = int(active_ksp.getIterationNumber())
            reason = int(active_ksp.getConvergedReason())
            reported_final = float(active_ksp.getResidualNorm())
            active_ksp.destroy()
            active_ksp = None
            ksp_destroy_count += 1

            action = apply_action(solution)
            exact_action_count += 1
            true_residual = rhs.copy()
            true_residual.axpy(PETSc.ScalarType(-1.0), action)
            explicit_relative = float(true_residual.norm()) / rhs_norm
            action.destroy()
            true_residual.destroy()
            cumulative_iteration = cycle_start + local_iterations

            checkpoint_info = None
            checkpoint_due = cumulative_iteration % checkpoint_interval == 0
            if first_checkpoint_iteration is not None:
                checkpoint_due = checkpoint_due or (
                    cumulative_iteration == first_checkpoint_iteration
                )
            if checkpoint_writer is not None and checkpoint_due:
                checkpoint_info = dict(
                    checkpoint_writer(cumulative_iteration, solution, explicit_relative)
                )
                checkpoint_facts.append(checkpoint_info)

            resource = dict(resource_sample())
            cycle = {
                "cycle_index": int(cycle_index),
                "start_iteration": int(cycle_start),
                "end_iteration": int(cumulative_iteration),
                "iterations": int(local_iterations),
                "reason": int(reason),
                "initial_guess_nonzero": bool(resumed or cycle_index > 0),
                "reported_final_residual": reported_final,
                "explicit_true_residual": float(explicit_relative),
                "matvec_count": int(action_context.matvec_count - matvec_start),
                "pc_apply_count": int(pc_context.apply_count - pc_start),
                "wall_seconds": float(time.perf_counter() - cycle_started),
                "resource": resource,
                "ksp_destroyed": True,
            }
            if checkpoint_info is not None:
                cycle["checkpoint"] = checkpoint_info
            cycles.append(cycle)
            if cycle_observer is not None:
                cycle_observer(cumulative_iteration, solution, cycle)

            if stop_on_true_residual and explicit_relative <= residual_limit:
                break
            if cumulative_iteration >= max_it:
                break
            if reason < 0 and reason != DIVERGED_ITS:
                break
            if local_iterations == 0:
                break
            resumed = True

        final_solution = solution.copy()
        return {
            "settings": {
                "ksp_type": "gmres",
                "pc_side": "right",
                "norm_type": "unpreconditioned",
                "restart": GMRES_RESTART,
                "cycle_max_it": CYCLE_MAX_IT,
                "max_it": max_it,
                "start_iteration": start_iteration,
                "residual_limit": residual_limit,
                "residual_replacement": True,
                "initial_guess_nonzero": bool(initial_solution is not None),
                "first_checkpoint_iteration": first_checkpoint_iteration,
                "checkpoint_interval": checkpoint_interval,
            },
            "initial_true_residual": float(initial_true_relative),
            "cycles": cycles,
            "checkpoint_facts": checkpoint_facts,
            "iterations": int(cumulative_iteration),
            "reason": int(cycles[-1]["reason"]) if cycles else 0,
            "final_true_residual": float(
                cycles[-1]["explicit_true_residual"] if cycles else initial_true_relative
            ),
            "matvec_count": int(action_context.matvec_count),
            "pc_apply_count": int(pc_context.apply_count),
            "explicit_action_count": int(exact_action_count),
            "ksp_destroy_count": int(ksp_destroy_count),
            "elapsed_seconds": float(time.perf_counter() - started),
            "final_solution": final_solution,
        }
    finally:
        if active_ksp is not None:
            active_ksp.destroy()
        solution.destroy()
        operator.destroy()


def destroy_krylov_result(result: dict[str, Any]) -> None:
    """Destroy only the final solution owned by a Krylov result."""

    solution = result.pop("final_solution", None)
    if solution is not None:
        solution.destroy()


__all__ = [
    "CHECKPOINT_INTERVAL",
    "CHECKPOINT_SCHEMA",
    "CYCLE_MAX_IT",
    "GMRES_RESTART",
    "PHYSICAL_PAIR_MARGIN",
    "MANDATORY_FIRST_CHECKPOINT",
    "SMALL_PAIR_MARGIN",
    "destroy_krylov_result",
    "read_solution_checkpoint",
    "residual_pair_bound",
    "run_restart20_cycles",
    "write_solution_checkpoint",
]
