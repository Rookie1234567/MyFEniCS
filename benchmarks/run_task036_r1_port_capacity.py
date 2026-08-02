"""Task036 R1b-1a full-interface right/physical-adjoint mode pool.

This runner reuses the existing one-cell local factor setup.  A sparse
PEP/LINEAR solve with an internal two-sided EPS is the actual mode-pool path;
the paired EPS left vector supplies the physical-adjoint candidate from the
same eigenpair.  Batched Schur action and the reversed Hermitian polynomial
are used only for independent residual checks.  Six fixed phase targets plus
one fixed reciprocal source form a deterministic mode-pool audit; this is not
a B1 capacity or production propagation solver.
"""

from __future__ import annotations

import argparse
import hashlib
from itertools import combinations
import json
from pathlib import Path
import resource
import subprocess
import tempfile
import time
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc
from slepc4py import SLEPc

from benchmarks.run_task036_transfer_optimal_port_capacity import (
    _build_d1_local_factor_setup,
)
from src.solvers.one_cell_discrete_bloch import (
    bloch_polynomial_action,
    build_augmented_bloch_polynomial,
    build_reversed_hermitian_bloch_polynomial,
    endpoint_cauchy_balance,
)


ROOT = Path(__file__).resolve().parents[1]
MODE_POOL_TARGETS = (
    1.0 + 0.0j,
    1.0j,
    -1.0 + 0.0j,
    -1.0j,
    0.38268343236508984 + 0.9238795325112867j,
    0.38268343236508984 - 0.9238795325112867j,
)
MODE_POOL_SOURCE_SCHEDULE = (
    ("P", 0),
    ("P", 1),
    ("P", 2),
    ("P", 3),
    ("P", 4),
    ("P", 5),
    ("Prev", 2),
)
MODE_POOL_FAMILIES = ("P", "Prev", "Q", "Qrev")
MODE_POOL_NEV = 128
MODE_POOL_MAX_IT = 100
MODE_POOL_EIGEN_TOL = 1.0e-12
MODE_POOL_WALL_LIMIT_SECONDS = 6600.0
MODE_POOL_RSS_LIMIT_BYTES = 4 * 1024**3
MODE_POOL_SWAP_LIMIT_KIB = 0
MODE_POOL_BLOCK_TOL = 1.0e-6
MODE_POOL_RESIDUAL_TOL = 1.0e-7
MODE_POOL_PAIR_MATCH_TOL = 1.0e-10


def _git(*arguments: str) -> str:
    return subprocess.check_output(["git", *arguments], cwd=ROOT, text=True).strip()


def _complex_pair(value: complex) -> list[float]:
    number = complex(value)
    return [float(number.real), float(number.imag)]


def _groups(values: list[complex], *, reciprocal: bool) -> list[dict[str, Any]]:
    groups = []
    for left in range(len(values)):
        for right in range(left + 1, len(values)):
            metric = (
                abs(values[left] * values[right] - 1.0)
                if reciprocal
                else abs(values[left] - values[right])
            )
            scale = max(
                1.0,
                abs(values[left] * values[right]) if reciprocal else abs(values[left]),
                abs(values[right]),
            )
            if metric / scale <= 1.0e-6:
                groups.append(
                    {
                        "indices": [left, right],
                        "relative_error": float(metric / scale),
                    }
                )
    return groups


def _root_blocks(values: list[complex]) -> list[list[int]]:
    """Group near-degenerate roots without choosing a basis inside a block."""

    pending = set(range(len(values)))
    blocks: list[list[int]] = []
    while pending:
        seed = min(pending)
        block = {seed}
        changed = True
        while changed:
            changed = False
            for index in tuple(pending - block):
                if any(
                    abs(values[index] - values[member])
                    / max(1.0, abs(values[index]), abs(values[member]))
                    <= 1.0e-6
                    for member in block
                ):
                    block.add(index)
                    changed = True
        pending.difference_update(block)
        blocks.append(sorted(block))
    return blocks


def _block_right_reciprocal_error(
    right: list[complex],
    partner: list[complex],
) -> float:
    if len(right) != len(partner) or not right:
        return float("inf")
    if any(abs(value) <= 1.0e-30 for value in right):
        return float("inf")
    expected = [1.0 / value for value in right]

    def directed(source: list[complex], target: list[complex]) -> float:
        return max(
            min(
                abs(value - candidate) / max(1.0, abs(value), abs(candidate))
                for candidate in target
            )
            for value in source
        )

    return max(directed(expected, partner), directed(partner, expected))


def _block_adjoint_mapping_error(
    right: list[complex],
    adjoint: list[complex],
) -> float:
    if len(right) != len(adjoint) or not right:
        return float("inf")
    if any(abs(value) <= 1.0e-30 for value in right):
        return float("inf")
    expected = [1.0 / np.conj(value) for value in right]

    def directed(source: list[complex], target: list[complex]) -> float:
        return max(
            min(
                abs(value - candidate) / max(1.0, abs(value), abs(candidate))
                for candidate in target
            )
            for value in source
        )

    return max(directed(expected, adjoint), directed(adjoint, expected))


def _select_pairing_subblock(
    normalized: np.ndarray,
    right_indices: list[int],
    adjoint_indices: list[int],
) -> dict[str, Any]:
    """Select one deterministic, numerically strongest raw subblock."""

    matrix = np.asarray(normalized, dtype=np.complex128)
    if matrix.shape != (len(adjoint_indices), len(right_indices)):
        raise ValueError("Pairing matrix and block indices have incompatible shapes.")
    singular_values = np.linalg.svd(matrix, compute_uv=False)
    if not singular_values.size:
        rank = 0
    else:
        threshold = max(float(singular_values[0]), 1.0e-30) * 1.0e-10
        rank = int(np.count_nonzero(singular_values > threshold))
    candidates: list[dict[str, Any]] = []
    if rank:
        for right_positions in combinations(range(len(right_indices)), rank):
            for adjoint_positions in combinations(range(len(adjoint_indices)), rank):
                block = matrix[np.ix_(adjoint_positions, right_positions)]
                block_singular = np.linalg.svd(block, compute_uv=False)
                if not block_singular.size:
                    continue
                condition = float(
                    block_singular[0] / max(float(block_singular[-1]), 1.0e-30)
                )
                candidates.append(
                    {
                        "right_indices": [right_indices[i] for i in right_positions],
                        "adjoint_indices": [
                            adjoint_indices[i] for i in adjoint_positions
                        ],
                        "singular_values": block_singular.tolist(),
                        "minimum_singular_value": float(block_singular[-1]),
                        "condition": condition,
                    }
                )
    candidates.sort(
        key=lambda option: (
            -option["minimum_singular_value"],
            option["condition"],
            tuple(option["right_indices"]),
            tuple(option["adjoint_indices"]),
        )
    )
    return {
        "raw_right_block_size": len(right_indices),
        "raw_adjoint_block_size": len(adjoint_indices),
        "singular_values": singular_values.tolist(),
        "numerical_rank": rank,
        "pairing_rcond": 1.0e-10,
        "selected": candidates[0] if candidates else None,
    }


def _selected_pairing_gate(condition: float, green: dict[str, float]) -> bool:
    return condition <= 1.0e10 and all(
        green[key] <= 1.0e-10
        for key in (
            "green_pairing_relative",
            "primal_outward_balance_relative",
            "adjoint_outward_balance_relative",
        )
    )


def _closed_selected_component_indices(
    components: list[list[int]],
    qualified_blocks: dict[int, dict[str, Any]],
) -> list[int]:
    selected: list[int] = []
    for component in components:
        if not all(index in qualified_blocks for index in component):
            continue
        ranks = {int(qualified_blocks[index]["selected_rank"]) for index in component}
        if len(ranks) == 1:
            selected.extend(component)
    return sorted(selected)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--verified-clean-sha", required=True)
    return parser.parse_args()


def _current_swap_kib() -> int:
    for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
        if line.startswith("VmSwap:"):
            return int(line.split()[1])
    return 0


def _canonicalize_candidate(
    family: str,
    source_multiplier: complex,
    state: np.ndarray,
    *,
    endpoint_rows: int,
) -> tuple[str, complex, np.ndarray, dict[str, Any]]:
    """Map a family root to canonical P or Q without changing its state."""

    source = complex(source_multiplier)
    if family in ("Prev", "Qrev") and abs(source) <= 1.0e-30:
        raise ValueError(f"{family} reciprocal multiplier is zero.")
    if family == "P":
        variable = "lambda"
        canonical = source
        rule = "identity-state P(lambda)"
    elif family == "Prev":
        variable = "lambda"
        canonical = 1.0 / source
        rule = "identity-state Prev(zeta)=zeta^2*P(1/zeta)"
    elif family == "Q":
        variable = "nu"
        canonical = source
        rule = "identity-state Q(nu)"
    elif family == "Qrev":
        variable = "nu"
        canonical = 1.0 / source
        rule = "identity-state Qrev(eta)=eta^2*Q(1/eta)"
    else:
        raise ValueError(f"Unknown Bloch polynomial family: {family}")
    values = np.asarray(state, dtype=np.complex128).copy()
    if values.ndim != 1 or values.shape[0] < endpoint_rows:
        raise ValueError("Bloch augmented state has an invalid shape.")
    return (
        variable,
        canonical,
        values,
        {
            "family": family,
            "source_multiplier": _complex_pair(source),
            "canonical_multiplier": _complex_pair(canonical),
            "state_map": "identity",
            "physical_endpoint_rule": (
                "e_R=lambda*e_L" if variable == "lambda" else "v_R=nu*v_L"
            ),
            "canonicalization_rule": rule,
        },
    )


def _residual_ok(candidate: dict[str, Any]) -> bool:
    values = candidate["record"]
    return (
        max(
            values["full_augmented_relative_residual"],
            values["schur_polynomial_relative_residual"],
        )
        <= MODE_POOL_RESIDUAL_TOL
    )


def _deduplicate_candidates(
    entries: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Keep independent vectors in each canonical multiplier block."""

    removed: dict[str, int] = {family: 0 for family in MODE_POOL_FAMILIES}
    if not entries:
        return [], removed
    values = [complex(entry["multiplier"]) for entry in entries]
    blocks = _root_blocks(values)
    kept_indices: list[int] = []
    for block in blocks:
        basis: list[np.ndarray] = []
        source_keys: set[tuple[str, int]] = set()
        for index in block:
            entry = entries[index]
            state = np.asarray(entry["state"], dtype=np.complex128)
            norm = float(np.linalg.norm(state))
            if norm <= 1.0e-30:
                raise ValueError("Cannot deduplicate a zero Bloch state.")
            normalized = state / norm
            same_source = entry["source_key"] in source_keys
            independent = True
            if basis:
                old_matrix = np.column_stack(basis)
                matrix = np.column_stack(basis + [normalized])
                old_singular = np.linalg.svd(old_matrix, compute_uv=False)
                singular_values = np.linalg.svd(matrix, compute_uv=False)
                tolerance = (
                    max(
                        float(singular_values[0]),
                        float(old_singular[0]) if old_singular.size else 0.0,
                        1.0e-30,
                    )
                    * 1.0e-10
                )
                old_rank = int(np.count_nonzero(old_singular > tolerance))
                new_rank = int(np.count_nonzero(singular_values > tolerance))
                independent = new_rank > old_rank
            if same_source or independent:
                kept_indices.append(index)
                source_keys.add(entry["source_key"])
                basis.append(normalized)
            else:
                removed[entry["family"]] += 1
    kept_indices.sort()
    return [entries[index] for index in kept_indices], removed


def _right_reciprocal_closure(
    multipliers: list[complex],
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    blocks = _root_blocks(multipliers)
    mappings: dict[int, dict[str, Any]] = {}
    for block_index, block in enumerate(blocks):
        partner = min(
            range(len(blocks)),
            key=lambda index: _block_right_reciprocal_error(
                [multipliers[item] for item in block],
                [multipliers[item] for item in blocks[index]],
            ),
            default=None,
        )
        error = (
            _block_right_reciprocal_error(
                [multipliers[item] for item in block],
                [multipliers[item] for item in blocks[partner]],
            )
            if partner is not None
            else float("inf")
        )
        finite_error = float(error) if np.isfinite(error) else None
        mappings[block_index] = {
            "partner_block_index": partner,
            "relative_error": finite_error,
            "equal_size": bool(
                partner is not None and len(block) == len(blocks[partner])
            ),
            "mutual_partner": False,
            "closed": False,
        }
    for block_index, mapping in mappings.items():
        partner = mapping["partner_block_index"]
        partner_mapping = mappings[partner] if partner is not None else None
        partner_error = partner_mapping["relative_error"] if partner_mapping else None
        mapping["mutual_partner"] = bool(
            partner_mapping is not None
            and partner_mapping["partner_block_index"] == block_index
        )
        mapping["closed"] = bool(
            mapping["equal_size"]
            and mapping["mutual_partner"]
            and mapping["relative_error"] is not None
            and mapping["relative_error"] <= MODE_POOL_BLOCK_TOL
            and partner_error is not None
            and partner_error <= MODE_POOL_BLOCK_TOL
        )
    components: list[list[int]] = []
    seen: set[int] = set()
    for root in range(len(blocks)):
        if root in seen or not mappings[root]["closed"]:
            continue
        partner = mappings[root]["partner_block_index"]
        component = [root] if partner == root else sorted([root, partner])
        components.append(component)
        seen.update(component)
    effective_indices = {
        index
        for component in components
        if all(
            all(_residual_ok(candidates[item]) for item in blocks[index])
            for index in component
        )
        for index in component
    }
    effective_columns = sum(len(blocks[index]) for index in effective_indices)
    return {
        "blocks": blocks,
        "mappings": mappings,
        "components": components,
        "effective_block_indices": sorted(effective_indices),
        "effective_columns": int(effective_columns),
        "near_degenerate_groups": _groups(multipliers, reciprocal=False),
    }


def _right_pool_gate(
    effective_columns: int,
    *,
    phase_bins: list[int] | None = None,
    full_residual_max: float | None = None,
    schur_residual_max: float | None = None,
    partial_runs: list[dict[str, Any]] | None = None,
    unusable_runs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    partial_runs = [] if partial_runs is None else partial_runs
    unusable_runs = [] if unusable_runs is None else unusable_runs
    if unusable_runs:
        reason = "right_solver_failed"
        passed = False
    elif int(effective_columns) < 120:
        reason = "right_pool_effective_columns_below_120"
        passed = False
    elif int(effective_columns) > 360:
        reason = "bounded_dimension_exceeded"
        passed = False
    elif phase_bins is None or full_residual_max is None or schur_residual_max is None:
        reason = "right_pool_gate_evidence_missing"
        passed = False
    elif phase_bins is not None and (
        len(phase_bins) != 8 or any(int(value) <= 0 for value in phase_bins)
    ):
        reason = "right_pool_phase_coverage_incomplete"
        passed = False
    elif full_residual_max is not None and full_residual_max > MODE_POOL_RESIDUAL_TOL:
        reason = "right_pool_full_residual_failed"
        passed = False
    elif schur_residual_max is not None and schur_residual_max > MODE_POOL_RESIDUAL_TOL:
        reason = "right_pool_schur_residual_failed"
        passed = False
    else:
        reason = "right_pool_ready_for_Q_Qrev"
        passed = True
    status_if_failed = (
        "MODE_POOL_SOLVER_FAILED"
        if unusable_runs
        else "MODE_POOL_INCOMPLETE_AT_TARGET_SET"
    )
    return {
        "passed": passed,
        "effective_columns": int(effective_columns),
        "minimum_columns": 120,
        "maximum_columns": 360,
        "reason": reason,
        "status_if_failed": status_if_failed,
        "effective_phase_bins_8": None if phase_bins is None else list(phase_bins),
        "full_residual_max": full_residual_max,
        "schur_residual_max": schur_residual_max,
        "partial_runs": partial_runs,
        "unusable_runs": unusable_runs,
    }


def _bounded_right_components(closure: dict[str, Any]) -> dict[str, Any]:
    raw_indices = set(closure["effective_block_indices"])
    selected: list[int] = []
    requested_columns = 0
    for component in closure["components"]:
        if not set(component).issubset(raw_indices):
            continue
        component_columns = sum(len(closure["blocks"][index]) for index in component)
        requested_columns += component_columns
        if (
            sum(len(closure["blocks"][index]) for index in selected) + component_columns
            > 360
        ):
            break
        selected.extend(component)
    selected = sorted(selected)
    return {
        "raw_effective_block_indices": sorted(raw_indices),
        "bounded_effective_block_indices": selected,
        "raw_effective_columns": int(closure["effective_columns"]),
        "bounded_effective_columns": int(
            sum(len(closure["blocks"][index]) for index in selected)
        ),
        "requested_columns": int(requested_columns),
    }


def _canonical_npz_arrays(
    entries: list[dict[str, Any]],
    blocks: list[list[int]],
    *,
    state_rows: int,
    prefix: str,
) -> dict[str, np.ndarray]:
    block_ids = np.full(len(entries), -1, dtype=np.int32)
    for block_index, block in enumerate(blocks):
        block_ids[np.asarray(block, dtype=np.int32)] = block_index
    states = (
        np.column_stack([entry["state"] for entry in entries])
        if entries
        else np.empty((state_rows, 0), dtype=np.complex128)
    )
    multipliers = np.asarray(
        [entry["multiplier"] for entry in entries], dtype=np.complex128
    )
    return {
        f"{prefix}_multipliers": multipliers,
        f"{prefix}_states": states,
        f"{prefix}_block_ids": block_ids,
        f"{prefix}_family": np.asarray(
            [entry["family"] for entry in entries], dtype="U8"
        ),
        f"{prefix}_target_index": np.asarray(
            [entry["target_index"] for entry in entries], dtype=np.int32
        ),
    }


def _phase_coverage(multipliers: list[complex]) -> dict[str, Any]:
    if not multipliers:
        return {"count": 0, "phase_bins_8": [0] * 8, "abs_min": None, "abs_max": None}
    values = np.asarray(multipliers, dtype=np.complex128)
    bins = np.histogram(
        np.mod(np.angle(values), 2.0 * np.pi),
        np.linspace(0.0, 2.0 * np.pi, 9),
    )[0]
    return {
        "count": int(len(values)),
        "phase_bins_8": [int(value) for value in bins],
        "abs_min": float(np.min(np.abs(values))),
        "abs_max": float(np.max(np.abs(values))),
    }


def _polynomial_relative_residual(
    terms: tuple[np.ndarray, np.ndarray, np.ndarray],
    multiplier: complex,
) -> float:
    residual = terms[0] + multiplier * terms[1] + multiplier**2 * terms[2]
    scale = (
        np.linalg.norm(terms[0])
        + abs(multiplier) * np.linalg.norm(terms[1])
        + abs(multiplier) ** 2 * np.linalg.norm(terms[2])
    )
    return float(np.linalg.norm(residual) / max(float(scale), 1.0e-30))


def main() -> None:
    args = _parse_args()
    comm = MPI.COMM_WORLD
    if comm.size != 1:
        raise SystemExit("R1b-1a mode pool is fixed to MPI1.")
    if np.dtype(PETSc.ScalarType) != np.dtype(np.complex128):
        raise SystemExit("R1b-1a mode pool requires PETSc complex128.")
    if np.dtype(PETSc.IntType) != np.dtype(np.int32):
        raise SystemExit("R1b-1a mode pool requires PETSc int32.")
    source_sha = _git("rev-parse", "HEAD")
    if source_sha != args.verified_clean_sha:
        raise SystemExit(f"Source SHA {source_sha} != {args.verified_clean_sha}.")
    dirty = _git("status", "--short", "--untracked-files=all")
    if dirty:
        raise SystemExit("R1b-1a requires a clean source worktree.")

    started = time.perf_counter()
    work_parent = args.work_dir.resolve()
    work_parent.mkdir(parents=True, exist_ok=True)
    work_dir = tempfile.TemporaryDirectory(
        prefix="task036-r1b-1a-",
        dir=work_parent,
    )
    setup: dict[str, Any] | None = None
    action = None
    augmented = None
    reversed_polynomial = None
    try:
        setup = _build_d1_local_factor_setup(
            work_dir,
            endpoint_comms=(MPI.COMM_NULL, MPI.COMM_NULL),
        )
        action = setup["cell_action"]
        if action.left_rows != 1200 or action.right_rows != 1200:
            raise RuntimeError(
                "Full-interface endpoint rows are not exactly 1200+1200."
            )
        augmented = build_augmented_bloch_polynomial(action)
        if augmented.state_rows != 3240:
            raise RuntimeError(
                f"Unexpected augmented state rows: {augmented.state_rows}."
            )
        reversed_polynomial = build_reversed_hermitian_bloch_polynomial(augmented)

        def create_pep(
            operators: tuple[PETSc.Mat, PETSc.Mat, PETSc.Mat],
            target: complex,
        ) -> SLEPc.PEP:
            pep = SLEPc.PEP().create(comm=PETSc.COMM_WORLD)
            pep.setOperators(list(operators))
            pep.setProblemType(SLEPc.PEP.ProblemType.GENERAL)
            pep.setType(SLEPc.PEP.Type.LINEAR)
            pep.setLinearExplicitMatrix(True)
            pep.setLinearLinearization(alpha=1.0, beta=0.0)
            pep.setDimensions(nev=MODE_POOL_NEV)
            pep.setTarget(target)
            pep.setWhichEigenpairs(SLEPc.PEP.Which.TARGET_MAGNITUDE)
            pep.setTolerances(tol=MODE_POOL_EIGEN_TOL, max_it=MODE_POOL_MAX_IT)
            eps = pep.getLinearEPS()
            eps.setType(SLEPc.EPS.Type.KRYLOVSCHUR)
            eps.setTwoSided(True)
            eps.setDimensions(nev=MODE_POOL_NEV)
            eps.setTarget(target)
            eps.setWhichEigenpairs(SLEPc.EPS.Which.TARGET_MAGNITUDE)
            eps.setTolerances(tol=MODE_POOL_EIGEN_TOL, max_it=MODE_POOL_MAX_IT)
            spectral_transform = eps.getST()
            spectral_transform.setType(SLEPc.ST.Type.SINVERT)
            ksp = spectral_transform.getKSP()
            ksp.setType(PETSc.KSP.Type.PREONLY)
            pc = ksp.getPC()
            pc.setType(PETSc.PC.Type.LU)
            pc.setFactorSolverType("mumps")
            return pep

        def sparse_apply(operator: PETSc.Mat, values: np.ndarray) -> np.ndarray:
            input_vector = operator.createVecRight()
            output_vector = operator.createVecLeft()
            try:
                input_vector.array[:] = values
                operator.mult(input_vector, output_vector)
                return np.asarray(output_vector.array, dtype=np.complex128).copy()
            finally:
                output_vector.destroy()
                input_vector.destroy()

        def matrix_record(operator: PETSc.Mat) -> dict[str, Any]:
            info = operator.getInfo(PETSc.Mat.InfoType.GLOBAL_SUM)
            return {
                "type": str(operator.getType()),
                "shape": [int(value) for value in operator.getSize()],
                "nnz": int(info.get("nz_used", 0.0)),
                "memory_bytes": int(info.get("memory", 0.0)),
            }

        def solver_record(
            pep: SLEPc.PEP,
            family: str,
            target_index: int,
            target: complex,
        ) -> dict[str, Any]:
            eps = pep.getLinearEPS()
            spectral_transform = eps.getST()
            ksp = spectral_transform.getKSP()
            pc = ksp.getPC()
            return {
                "family": family,
                "target_index": int(target_index),
                "target": _complex_pair(target),
                "pep_type": str(pep.getType()),
                "linear_explicit_matrix": bool(pep.getLinearExplicitMatrix()),
                "linear_alpha": 1.0,
                "linear_beta": 0.0,
                "eps_type": str(eps.getType()),
                "eps_two_sided": bool(eps.getTwoSided()),
                "st_type": str(spectral_transform.getType()),
                "ksp_type": str(ksp.getType()),
                "pc_type": str(pc.getType()),
                "factor_solver_type": pc.getFactorSolverType(),
                "converged": int(eps.getConverged()),
                "iteration_number": int(eps.getIterationNumber()),
                "convergence_reason": int(eps.getConvergedReason()),
            }

        def adjoint_schur_terms(electric: np.ndarray) -> tuple[np.ndarray, ...]:
            columns = np.zeros((action.port_rows, 2), dtype=np.complex128)
            columns[: action.left_rows, 0] = electric
            columns[action.left_rows :, 1] = electric
            applied = action.apply_adjoint_columns(columns)
            return (
                applied[action.left_rows :, 0],
                applied[: action.left_rows, 0] + applied[action.left_rows :, 1],
                applied[: action.left_rows, 1],
            )

        def collect_paired_pool(
            pep: SLEPc.PEP,
            eps: SLEPc.EPS,
            right_family: str,
            target_index: int,
            target: complex,
            right_operators: tuple[PETSc.Mat, PETSc.Mat, PETSc.Mat],
            canonical_right_operators: tuple[PETSc.Mat, PETSc.Mat, PETSc.Mat],
        ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
            right_entries: list[dict[str, Any]] = []
            adjoint_entries: list[dict[str, Any]] = []
            eps_converged = int(eps.getConverged())
            pep_converged = int(pep.getConverged())
            if pep_converged != eps_converged:
                raise RuntimeError(
                    "PEP and internal EPS converged counts do not match."
                )
            vector = right_operators[0].createVecRight()
            linear_left = PETSc.Vec().create(comm=PETSc.COMM_WORLD)
            linear_left.setSizes((2 * augmented.state_rows, 2 * augmented.state_rows))
            linear_left.setUp()
            left_family = "Qrev" if right_family == "P" else "Q"
            adjoint_operators = (
                reversed_polynomial.K0,
                reversed_polynomial.K1,
                reversed_polynomial.K2,
            )
            try:
                for index in range(pep_converged):
                    source_multiplier = complex(pep.getEigenpair(index, vector))
                    eps_multiplier = complex(eps.getEigenvalue(index))
                    paired_error = abs(source_multiplier - eps_multiplier) / max(
                        1.0,
                        abs(source_multiplier),
                        abs(eps_multiplier),
                    )
                    if paired_error > MODE_POOL_PAIR_MATCH_TOL:
                        raise RuntimeError(
                            "PEP/EPS eigenvalue ordering is not strictly paired."
                        )
                    right_state = np.asarray(
                        vector.getArray(readonly=True), dtype=np.complex128
                    ).copy()
                    variable, multiplier, right_state, mapping = (
                        _canonicalize_candidate(
                            right_family,
                            source_multiplier,
                            right_state,
                            endpoint_rows=action.left_rows,
                        )
                    )
                    right_terms = tuple(
                        sparse_apply(operator, right_state)
                        for operator in canonical_right_operators
                    )
                    right_electric = right_state[: action.left_rows]
                    right_record = {
                        "family": right_family,
                        "target_index": int(target_index),
                        "target": _complex_pair(target),
                        "variable": variable,
                        "source_multiplier": mapping["source_multiplier"],
                        "canonical_multiplier": mapping["canonical_multiplier"],
                        variable: mapping["canonical_multiplier"],
                        "canonical_mapping": mapping,
                        "full_augmented_relative_residual": _polynomial_relative_residual(
                            right_terms, multiplier
                        ),
                        "schur_polynomial_relative_residual": _polynomial_relative_residual(
                            tuple(
                                column[:, 0]
                                for column in bloch_polynomial_action(
                                    action, right_electric.reshape(-1, 1)
                                )
                            ),
                            multiplier,
                        ),
                        "endpoint_vector_norm_fraction": float(
                            np.linalg.norm(right_electric)
                            / max(float(np.linalg.norm(right_state)), 1.0e-30)
                        ),
                        "slepc_relative_error": float(
                            pep.computeError(
                                index,
                                SLEPc.PEP.ErrorType.RELATIVE,
                            )
                        ),
                        "eps_eigenvalue": _complex_pair(eps_multiplier),
                        "paired_eigenvalue_relative_error": float(paired_error),
                    }
                    right_entries.append(
                        {
                            "family": right_family,
                            "target_index": int(target_index),
                            "source_key": (right_family, int(target_index)),
                            "multiplier": multiplier,
                            "state": right_state,
                            "record": right_record,
                        }
                    )
                    eps.getLeftEigenvector(index, linear_left)
                    linear_state = np.asarray(
                        linear_left.getArray(readonly=True), dtype=np.complex128
                    )
                    if len(linear_state) != 2 * augmented.state_rows:
                        raise RuntimeError(
                            "Two-sided EPS left vector has unexpected size."
                        )
                    left_state = linear_state[augmented.state_rows :].copy()
                    left_source_multiplier = np.conj(source_multiplier)
                    if right_family == "P" and abs(left_source_multiplier) <= 1.0e-30:
                        continue
                    left_variable, left_multiplier, left_state, left_mapping = (
                        _canonicalize_candidate(
                            left_family,
                            left_source_multiplier,
                            left_state,
                            endpoint_rows=action.left_rows,
                        )
                    )
                    left_terms = tuple(
                        sparse_apply(operator, left_state)
                        for operator in adjoint_operators
                    )
                    left_electric = left_state[: action.left_rows]
                    left_record = {
                        "family": left_family,
                        "target_index": int(target_index),
                        "target": _complex_pair(target),
                        "variable": left_variable,
                        "source_multiplier": left_mapping["source_multiplier"],
                        "canonical_multiplier": left_mapping["canonical_multiplier"],
                        left_variable: left_mapping["canonical_multiplier"],
                        "canonical_mapping": left_mapping,
                        "full_augmented_relative_residual": _polynomial_relative_residual(
                            left_terms, left_multiplier
                        ),
                        "schur_polynomial_relative_residual": _polynomial_relative_residual(
                            adjoint_schur_terms(left_electric), left_multiplier
                        ),
                        "endpoint_vector_norm_fraction": float(
                            np.linalg.norm(left_electric)
                            / max(float(np.linalg.norm(left_state)), 1.0e-30)
                        ),
                        "paired_source_right_slepc_relative_error": float(
                            pep.computeError(
                                index,
                                SLEPc.PEP.ErrorType.RELATIVE,
                            )
                        ),
                        "eps_eigenvalue": _complex_pair(eps_multiplier),
                        "paired_eigenvalue_relative_error": float(paired_error),
                        "paired_right_family": right_family,
                    }
                    adjoint_entries.append(
                        {
                            "family": left_family,
                            "target_index": int(target_index),
                            "source_key": (left_family, int(target_index)),
                            "multiplier": left_multiplier,
                            "state": left_state,
                            "record": left_record,
                        }
                    )
            finally:
                linear_left.destroy()
                vector.destroy()
            return right_entries, adjoint_entries, eps_converged

        def run_paired_family(
            family: str,
            target_index: int,
            target: complex,
            source_operators: tuple[PETSc.Mat, PETSc.Mat, PETSc.Mat],
            canonical_right_operators: tuple[PETSc.Mat, PETSc.Mat, PETSc.Mat],
        ) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
            pep = create_pep(source_operators, target)
            try:
                pep.solve()
                solver = solver_record(pep, family, target_index, target)
                right_entries, adjoint_entries, _ = collect_paired_pool(
                    pep,
                    pep.getLinearEPS(),
                    family,
                    target_index,
                    target,
                    source_operators,
                    canonical_right_operators,
                )
                return solver, right_entries, adjoint_entries
            finally:
                pep.destroy()

        right_specs = {
            "P": (augmented.K0, augmented.K1, augmented.K2),
            "Prev": (augmented.K2, augmented.K1, augmented.K0),
        }
        right_runs: list[dict[str, Any]] = []
        right_raw: list[dict[str, Any]] = []
        adjoint_runs: list[dict[str, Any]] = []
        adjoint_raw: list[dict[str, Any]] = []
        paired_stage_started = time.perf_counter()
        for schedule_index, (family, target_index) in enumerate(
            MODE_POOL_SOURCE_SCHEDULE, start=1
        ):
            target = MODE_POOL_TARGETS[target_index]
            solver, right_entries, adjoint_entries = run_paired_family(
                family,
                target_index,
                target,
                right_specs[family],
                (augmented.K0, augmented.K1, augmented.K2),
            )
            right_runs.append(
                {
                    "solver": solver,
                    "raw_candidate_count": len(right_entries),
                    "family": family,
                    "target_index": int(target_index),
                    "target": _complex_pair(target),
                    "stage": "paired_two_sided",
                }
            )
            left_family = "Qrev" if family == "P" else "Q"
            adjoint_runs.append(
                {
                    "solver": solver.copy(),
                    "raw_candidate_count": len(adjoint_entries),
                    "family": left_family,
                    "target_index": int(target_index),
                    "target": _complex_pair(target),
                    "paired_source_family": family,
                    "solver_role": "paired_source_solver",
                    "paired_output_family": left_family,
                    "stage": "paired_two_sided",
                }
            )
            right_raw.extend(right_entries)
            adjoint_raw.extend(adjoint_entries)
            if comm.rank == 0:
                print(
                    f"mode-pool source {schedule_index}/7 family={family} "
                    f"target_index={target_index} raw_right={len(right_entries)} "
                    f"raw_adjoint={len(adjoint_entries)} "
                    f"paired_wall={time.perf_counter() - paired_stage_started:.3f}s",
                    flush=True,
                )
        paired_stage_wall = float(time.perf_counter() - paired_stage_started)
        right_qualified_raw = [entry for entry in right_raw if _residual_ok(entry)]
        adjoint_qualified_raw = [entry for entry in adjoint_raw if _residual_ok(entry)]
        right_entries, right_removed = _deduplicate_candidates(right_qualified_raw)
        right_blocks = _right_reciprocal_closure(
            [entry["multiplier"] for entry in right_entries],
            right_entries,
        )
        right_bounded = _bounded_right_components(right_blocks)
        for run in right_runs:
            key = (run["family"], run["target_index"])
            raw_selected = [entry for entry in right_raw if entry["source_key"] == key]
            qualified = [
                entry for entry in right_qualified_raw if entry["source_key"] == key
            ]
            selected = [entry for entry in right_entries if entry["source_key"] == key]
            run["raw_candidate_count"] = len(raw_selected)
            run["residual_rejected_count"] = len(raw_selected) - len(qualified)
            run["retained_candidate_count"] = len(selected)
            run["residual_qualified_count"] = len(qualified)
            run["deduplicated_count"] = len(qualified) - len(selected)
            reason = int(run["solver"]["convergence_reason"])
            if not qualified:
                run["solver"]["convergence_status"] = "failed_no_residual_qualified"
            elif reason <= 0:
                run["solver"]["convergence_status"] = "partial_convergence"
            else:
                run["solver"]["convergence_status"] = "converged"
            run["solver"]["usable"] = bool(qualified)

        right_partial_runs = [
            {
                "family": run["family"],
                "target_index": int(run["target_index"]),
                "convergence_reason": int(run["solver"]["convergence_reason"]),
                "residual_qualified_count": int(run["residual_qualified_count"]),
            }
            for run in right_runs
            if run["solver"]["convergence_reason"] <= 0
            and run["residual_qualified_count"] > 0
        ]
        right_unusable_runs = [
            {
                "family": run["family"],
                "target_index": int(run["target_index"]),
                "convergence_reason": int(run["solver"]["convergence_reason"]),
                "residual_qualified_count": int(run["residual_qualified_count"]),
            }
            for run in right_runs
            if run["residual_qualified_count"] == 0
        ]
        bounded_right_entries = [
            right_entries[item]
            for index in right_bounded["bounded_effective_block_indices"]
            for item in right_blocks["blocks"][index]
        ]
        bounded_phase = _phase_coverage(
            [entry["multiplier"] for entry in bounded_right_entries]
        )
        bounded_full_max = max(
            (
                entry["record"]["full_augmented_relative_residual"]
                for entry in bounded_right_entries
            ),
            default=None,
        )
        bounded_schur_max = max(
            (
                entry["record"]["schur_polynomial_relative_residual"]
                for entry in bounded_right_entries
            ),
            default=None,
        )
        right_gate = _right_pool_gate(
            right_bounded["bounded_effective_columns"],
            phase_bins=bounded_phase["phase_bins_8"],
            full_residual_max=bounded_full_max,
            schur_residual_max=bounded_schur_max,
            partial_runs=right_partial_runs,
            unusable_runs=right_unusable_runs,
        )
        right_gate["raw_effective_columns"] = right_bounded["raw_effective_columns"]
        right_gate["bounded_effective_columns"] = right_bounded[
            "bounded_effective_columns"
        ]
        right_gate["effective_phase_coverage"] = bounded_phase
        right_solver = {
            "status": (
                "solver_failed"
                if right_unusable_runs
                else "partial_convergence"
                if right_partial_runs
                else "completed"
            ),
            "run_count": len(right_runs),
            "partial_runs": right_partial_runs,
            "unusable_runs": right_unusable_runs,
            "runs": right_runs,
        }
        adjoint_entries, adjoint_removed = _deduplicate_candidates(
            adjoint_qualified_raw
        )
        for run in adjoint_runs:
            key = (run["family"], run["target_index"])
            raw_selected = [
                entry for entry in adjoint_raw if entry["source_key"] == key
            ]
            qualified = [
                entry for entry in adjoint_qualified_raw if entry["source_key"] == key
            ]
            selected = [
                entry for entry in adjoint_entries if entry["source_key"] == key
            ]
            run["raw_candidate_count"] = len(raw_selected)
            run["residual_rejected_count"] = len(raw_selected) - len(qualified)
            run["retained_candidate_count"] = len(selected)
            run["residual_qualified_count"] = len(qualified)
            run["deduplicated_count"] = len(qualified) - len(selected)
            reason = int(run["solver"]["convergence_reason"])
            if not qualified:
                run["solver"]["convergence_status"] = "failed_no_residual_qualified"
            elif reason <= 0:
                run["solver"]["convergence_status"] = "partial_convergence"
            else:
                run["solver"]["convergence_status"] = "converged"
            run["solver"]["usable"] = bool(qualified)
        adjoint_blocks: list[list[int]] = []
        block_reports: list[dict[str, Any]] = []
        unmatched_adjoint_blocks: list[int] = []
        green_pairing: dict[str, Any] = {
            "columns": 0,
            "green_pairing_relative": None,
            "primal_outward_balance_relative": None,
            "adjoint_outward_balance_relative": None,
        }
        adjoint_stage_wall: float | None = paired_stage_wall

        def emit(
            status: str,
            *,
            adjoint_solver: dict[str, Any],
            adjoint_stage_elapsed: float | None,
            right_entries_for_output: list[dict[str, Any]],
            right_blocks_for_output: list[list[int]],
            adjoint_entries_for_output: list[dict[str, Any]],
            effective_right_block_indices: list[int],
            effective_columns: int,
            reciprocal_adjoint: list[dict[str, Any]],
            adjoint_blocks_for_output: list[list[int]],
            unmatched_blocks: list[int],
            contract_gate: dict[str, Any],
        ) -> None:
            elapsed = float(time.perf_counter() - started)
            rss_kib = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
            swap_kib = _current_swap_kib()
            npz_path = args.output.with_suffix(".npz")
            arrays = _canonical_npz_arrays(
                right_entries_for_output,
                right_blocks_for_output,
                state_rows=augmented.state_rows,
                prefix="right",
            )
            arrays.update(
                _canonical_npz_arrays(
                    adjoint_entries_for_output,
                    adjoint_blocks_for_output,
                    state_rows=augmented.state_rows,
                    prefix="adjoint",
                )
            )
            payload = {
                "schema_version": ("task036.r1b-1a-physical-adjoint-mode-pool.v2"),
                "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "status": status,
                "capacity_claim": "not_run",
                "source": {
                    "sha": source_sha,
                    "branch": _git("branch", "--show-current"),
                    "petsc_scalar_type": str(np.dtype(PETSc.ScalarType)),
                    "petsc_int_type": str(np.dtype(PETSc.IntType)),
                    "clean_src_benchmarks": not bool(dirty),
                    "working_tree_status": dirty,
                },
                "solver": {
                    "type": (
                        "SLEPc.PEP/LINEAR + EPS/KRYLOVSCHUR two-sided "
                        "with sparse augmented coefficients"
                    ),
                    "target": 1.0,
                    "targets": [_complex_pair(target) for target in MODE_POOL_TARGETS],
                    "families": list(MODE_POOL_FAMILIES),
                    "nev": MODE_POOL_NEV,
                    "max_it": MODE_POOL_MAX_IT,
                    "paired_two_sided": True,
                    "independent_adjoint_solves": 0,
                    "right": right_solver,
                    "physical_adjoint": adjoint_solver,
                },
                "polynomial": {
                    "equation": "P(lambda)=K0+lambda*K1+lambda^2*K2",
                    "reciprocal_right_equation": ("Prev(zeta)=K2+zeta*K1+zeta^2*K0"),
                    "physical_adjoint_equation": ("Q(nu)=K2^H+nu*K1^H+nu^2*K0^H"),
                    "reversed_adjoint_equation": ("Qrev(eta)=K0^H+eta*K1^H+eta^2*K2^H"),
                    "family_target_runs": {
                        "right": right_runs,
                        "physical_adjoint": adjoint_runs,
                    },
                    "right_candidates": [entry["record"] for entry in right_entries],
                    "physical_adjoint_candidates": [
                        entry["record"] for entry in adjoint_entries
                    ],
                    "right_dedup_removed_by_family": right_removed,
                    "adjoint_dedup_removed_by_family": adjoint_removed,
                    "right_root_blocks": right_blocks["blocks"],
                    "adjoint_root_blocks": adjoint_blocks,
                    "right_reciprocal_block_mappings": right_blocks["mappings"],
                    "right_reciprocal_components": right_blocks["components"],
                    "right_near_degenerate_groups": right_blocks[
                        "near_degenerate_groups"
                    ],
                    "effective_right_block_indices": (effective_right_block_indices),
                    "reciprocal_closed_effective_columns": int(effective_columns),
                    "right_pool_gate": right_gate,
                    "right_bounded_component_selection": right_bounded,
                    "reciprocal_adjoint_block_mappings": reciprocal_adjoint,
                    "unmatched_adjoint_block_indices": unmatched_blocks,
                    "mode_pool_green_cauchy": green_pairing,
                    "contract_gate": contract_gate,
                    "phase_coverage": {
                        "right": _phase_coverage(
                            [entry["multiplier"] for entry in right_entries_for_output]
                        ),
                        "physical_adjoint": _phase_coverage(
                            [
                                entry["multiplier"]
                                for entry in adjoint_entries_for_output
                            ]
                        ),
                    },
                },
                "objects": {
                    "state_rows": int(augmented.state_rows),
                    "endpoint_rows": [
                        int(action.left_rows),
                        int(action.right_rows),
                    ],
                    "interior_rows": int(action.interior_rows),
                    "interior_matrix_nnz": int(action.interior_matrix_nnz),
                    "right_sparse_polynomial_matrices": [
                        matrix_record(operator)
                        for operator in (augmented.K0, augmented.K1, augmented.K2)
                    ],
                    "physical_adjoint_sparse_polynomial_matrices": (
                        [
                            matrix_record(operator)
                            for operator in (
                                reversed_polynomial.K0,
                                reversed_polynomial.K1,
                                reversed_polynomial.K2,
                            )
                        ]
                        if reversed_polynomial is not None
                        else []
                    ),
                    "resident_dense_interface_square_formed": bool(
                        augmented.dense_interface_square_formed
                    ),
                    "resident_full_interface_square_shape": None,
                    "resident_transfer_matrix": False,
                },
                "timing_seconds": {
                    "wall": elapsed,
                    "paired_two_sided_stage": paired_stage_wall,
                    "right_stage": paired_stage_wall,
                    "physical_adjoint_stage": paired_stage_wall,
                    "right_and_adjoint_share_stage": True,
                    "wall_limit_seconds": MODE_POOL_WALL_LIMIT_SECONDS,
                },
                "resource": {
                    "ru_maxrss_kib": rss_kib,
                    "rss_bytes": rss_kib * 1024,
                    "rss_limit_bytes": MODE_POOL_RSS_LIMIT_BYTES,
                    "rss_scope": "MPI1 process lifetime peak diagnostic",
                    "swap_kib": swap_kib,
                    "swap_limit_kib": MODE_POOL_SWAP_LIMIT_KIB,
                    "swap_scope": "current MPI1 process VmSwap diagnostic",
                    "diagnostic_within_nominal_limits": bool(
                        elapsed <= MODE_POOL_WALL_LIMIT_SECONDS
                        and rss_kib * 1024 <= MODE_POOL_RSS_LIMIT_BYTES
                        and swap_kib <= MODE_POOL_SWAP_LIMIT_KIB
                    ),
                    "formal_gate": (
                        "external process-tree watchdog must provide "
                        "simultaneous RSS, wall, and swap=0"
                    ),
                },
            }
            if comm.rank == 0:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                np.savez_compressed(npz_path, **arrays)
                with npz_path.open("rb") as stream:
                    npz_sha256 = hashlib.file_digest(stream, "sha256").hexdigest()
                payload["canonical_npz_manifest"] = {
                    "path": str(npz_path),
                    "sha256": npz_sha256,
                    "bytes": npz_path.stat().st_size,
                    "right_columns": int(arrays["right_states"].shape[1]),
                    "adjoint_columns": int(arrays["adjoint_states"].shape[1]),
                }
                elapsed = float(time.perf_counter() - started)
                rss_kib = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
                swap_kib = _current_swap_kib()
                payload["timing_seconds"]["wall"] = elapsed
                payload["resource"].update(
                    {
                        "ru_maxrss_kib": rss_kib,
                        "rss_bytes": rss_kib * 1024,
                        "swap_kib": swap_kib,
                        "diagnostic_within_nominal_limits": bool(
                            elapsed <= MODE_POOL_WALL_LIMIT_SECONDS
                            and rss_kib * 1024 <= MODE_POOL_RSS_LIMIT_BYTES
                            and swap_kib <= MODE_POOL_SWAP_LIMIT_KIB
                        ),
                    }
                )
                args.output.write_text(
                    json.dumps(
                        payload,
                        indent=2,
                        ensure_ascii=False,
                        allow_nan=False,
                    )
                    + "\n",
                    encoding="utf-8",
                )

        if not right_gate["passed"]:
            emit(
                right_gate["status_if_failed"],
                adjoint_solver={
                    "status": "paired_stage_not_qualified",
                    "reason": right_gate["reason"],
                    "run_count": len(adjoint_runs),
                    "stage": "paired_two_sided",
                    "runs": adjoint_runs,
                },
                adjoint_stage_elapsed=paired_stage_wall,
                right_entries_for_output=right_entries,
                right_blocks_for_output=right_blocks["blocks"],
                adjoint_entries_for_output=[],
                effective_right_block_indices=right_bounded[
                    "bounded_effective_block_indices"
                ],
                effective_columns=right_bounded["bounded_effective_columns"],
                reciprocal_adjoint=[],
                adjoint_blocks_for_output=[],
                unmatched_blocks=[],
                contract_gate={
                    "passed": False,
                    "reason": right_gate["reason"],
                    "adjoint_stage": "paired_stage_not_qualified",
                },
            )
            return

        adjoint_blocks = _root_blocks(
            [entry["multiplier"] for entry in adjoint_entries]
        )
        adjoint_partial_runs = [
            {
                "family": run["family"],
                "target_index": int(run["target_index"]),
                "convergence_reason": int(run["solver"]["convergence_reason"]),
                "residual_qualified_count": int(run["residual_qualified_count"]),
            }
            for run in adjoint_runs
            if run["solver"]["convergence_reason"] <= 0
            and run["residual_qualified_count"] > 0
        ]
        adjoint_unusable_runs = [
            {
                "family": run["family"],
                "target_index": int(run["target_index"]),
                "convergence_reason": int(run["solver"]["convergence_reason"]),
                "residual_qualified_count": int(run["residual_qualified_count"]),
            }
            for run in adjoint_runs
            if run["residual_qualified_count"] == 0
        ]
        adjoint_solver = {
            "status": (
                "solver_failed"
                if adjoint_unusable_runs
                else "partial_convergence"
                if adjoint_partial_runs
                else "completed"
            ),
            "run_count": len(adjoint_runs),
            "partial_runs": adjoint_partial_runs,
            "unusable_runs": adjoint_unusable_runs,
            "runs": adjoint_runs,
        }
        if adjoint_unusable_runs:
            failure_right_entries = [
                right_entries[item]
                for index in right_bounded["bounded_effective_block_indices"]
                for item in right_blocks["blocks"][index]
            ]
            failure_right_blocks: list[list[int]] = []
            for index in right_bounded["bounded_effective_block_indices"]:
                start = sum(len(block) for block in failure_right_blocks)
                failure_right_blocks.append(
                    list(
                        range(
                            start,
                            start + len(right_blocks["blocks"][index]),
                        )
                    )
                )
            emit(
                "MODE_POOL_SOLVER_FAILED",
                adjoint_solver=adjoint_solver,
                adjoint_stage_elapsed=adjoint_stage_wall,
                right_entries_for_output=failure_right_entries,
                right_blocks_for_output=failure_right_blocks,
                adjoint_entries_for_output=[],
                effective_right_block_indices=right_bounded[
                    "bounded_effective_block_indices"
                ],
                effective_columns=right_bounded["bounded_effective_columns"],
                reciprocal_adjoint=[],
                adjoint_blocks_for_output=[],
                unmatched_blocks=list(range(len(adjoint_blocks))),
                contract_gate={
                    "passed": False,
                    "reason": "adjoint_solver_failed",
                    "adjoint_stage": "solver_failed",
                },
            )
            return

        right_multipliers = [entry["multiplier"] for entry in right_entries]
        adjoint_multipliers = [entry["multiplier"] for entry in adjoint_entries]
        right_blocks_list = right_blocks["blocks"]
        right_to_adjoint = {}
        for right_index, block in enumerate(right_blocks_list):
            right_to_adjoint[right_index] = min(
                range(len(adjoint_blocks)),
                key=lambda candidate: _block_adjoint_mapping_error(
                    [right_multipliers[item] for item in block],
                    [adjoint_multipliers[item] for item in adjoint_blocks[candidate]],
                ),
                default=None,
            )
        adjoint_to_right = {}
        for adjoint_index, block in enumerate(adjoint_blocks):
            adjoint_to_right[adjoint_index] = min(
                range(len(right_blocks_list)),
                key=lambda candidate: _block_adjoint_mapping_error(
                    [right_multipliers[item] for item in right_blocks_list[candidate]],
                    [adjoint_multipliers[item] for item in block],
                ),
                default=None,
            )
        accepted_mapping = {
            right_index: adjoint_index
            for right_index, adjoint_index in right_to_adjoint.items()
            if adjoint_index is not None
            and adjoint_to_right.get(adjoint_index) == right_index
            and len(right_blocks_list[right_index])
            == len(adjoint_blocks[adjoint_index])
            and _block_adjoint_mapping_error(
                [right_multipliers[item] for item in right_blocks_list[right_index]],
                [adjoint_multipliers[item] for item in adjoint_blocks[adjoint_index]],
            )
            <= MODE_POOL_BLOCK_TOL
        }
        unmatched_adjoint_blocks = sorted(
            set(range(len(adjoint_blocks))) - set(accepted_mapping.values())
        )
        bounded_right_indices = set(right_bounded["bounded_effective_block_indices"])
        qualified_blocks: dict[int, dict[str, Any]] = {}
        for right_index, right_block in enumerate(right_blocks_list):
            if right_index not in bounded_right_indices:
                block_reports.append(
                    {
                        "right_block_index": right_index,
                        "right_indices": right_block,
                        "adjoint_block_index": None,
                        "adjoint_indices": [],
                        "mapping_status": "outside_bounded_effective_set",
                        "mapped": False,
                        "qualified": False,
                    }
                )
                continue
            adjoint_index = right_to_adjoint[right_index]
            if adjoint_index is None:
                block_reports.append(
                    {
                        "right_block_index": right_index,
                        "right_indices": right_block,
                        "adjoint_block_index": None,
                        "adjoint_indices": [],
                        "mapping_status": "unmapped",
                        "mapped": False,
                        "qualified": False,
                    }
                )
                continue
            adjoint_block = adjoint_blocks[adjoint_index]
            mapping_error = _block_adjoint_mapping_error(
                [right_multipliers[item] for item in right_block],
                [adjoint_multipliers[item] for item in adjoint_block],
            )
            report = {
                "right_block_index": right_index,
                "right_indices": right_block,
                "adjoint_block_index": adjoint_index,
                "adjoint_indices": adjoint_block,
                "mapping_relative_error": (
                    float(mapping_error) if np.isfinite(mapping_error) else None
                ),
                "right_block_size": len(right_block),
                "adjoint_block_size": len(adjoint_block),
                "mutual_block_match": right_index in accepted_mapping,
                "mapping_status": (
                    "mutual" if right_index in accepted_mapping else "unqualified"
                ),
                "mapped": right_index in accepted_mapping,
                "qualified": False,
            }
            if not report["mapped"]:
                block_reports.append(report)
                continue
            adjoint_states = np.column_stack(
                [adjoint_entries[item]["state"] for item in adjoint_block]
            )
            derivative = np.column_stack(
                [
                    sparse_apply(augmented.K1, right_entries[item]["state"])
                    + 2.0
                    * right_entries[item]["multiplier"]
                    * sparse_apply(augmented.K2, right_entries[item]["state"])
                    for item in right_block
                ]
            )
            pairing = adjoint_states.conj().T @ derivative
            row_norms = np.linalg.norm(adjoint_states, axis=0)
            derivative_norms = np.linalg.norm(derivative, axis=0)
            normalizer = row_norms[:, None] * derivative_norms[None, :]
            normalized = np.divide(
                pairing,
                normalizer,
                out=np.zeros_like(pairing),
                where=normalizer > 1.0e-30,
            )
            pairing_selection = _select_pairing_subblock(
                normalized,
                right_block,
                adjoint_block,
            )
            singular_values = np.asarray(
                pairing_selection["singular_values"], dtype=float
            )
            rank = int(pairing_selection["numerical_rank"])
            raw_condition = (
                float(singular_values[0] / max(float(singular_values[-1]), 1.0e-30))
                if singular_values.size
                else None
            )
            selected_option = pairing_selection["selected"]
            selected_green: dict[str, Any] | None = None
            accepted_option: dict[str, Any] | None = None
            if selected_option is not None:
                selected_right = selected_option["right_indices"]
                selected_adjoint = selected_option["adjoint_indices"]
                if all(
                    _residual_ok(right_entries[item]) for item in selected_right
                ) and all(
                    _residual_ok(adjoint_entries[item]) for item in selected_adjoint
                ):
                    selected_right_states = np.column_stack(
                        [right_entries[item]["state"] for item in selected_right]
                    )
                    selected_adjoint_states = np.column_stack(
                        [adjoint_entries[item]["state"] for item in selected_adjoint]
                    )
                    selected_green = endpoint_cauchy_balance(
                        action,
                        selected_right_states,
                        selected_adjoint_states,
                        multipliers=[
                            right_entries[item]["multiplier"] for item in selected_right
                        ],
                        adjoint_multipliers=[
                            adjoint_entries[item]["multiplier"]
                            for item in selected_adjoint
                        ],
                    )
                    if _selected_pairing_gate(
                        selected_option["condition"], selected_green
                    ):
                        accepted_option = selected_option
            selected_right = selected_option["right_indices"] if selected_option else []
            selected_adjoint = (
                selected_option["adjoint_indices"] if selected_option else []
            )
            report.update(
                {
                    "pairing_matrix": "w_i^H*(K1+2*lambda_j*K2)*x_j",
                    "pairing_row_norms": row_norms.tolist(),
                    "pairing_derivative_column_norms": derivative_norms.tolist(),
                    "pairing_rcond": pairing_selection["pairing_rcond"],
                    "pairing_condition_limit": 1.0e10,
                    "cauchy_pairing_singular_values": singular_values.tolist(),
                    "cauchy_pairing_rank": rank,
                    "cauchy_pairing_condition": raw_condition,
                    "selected_right_indices": selected_right,
                    "selected_adjoint_indices": selected_adjoint,
                    "selected_rank": (
                        len(selected_right) if selected_option is not None else None
                    ),
                    "selected_cauchy_pairing_singular_values": (
                        selected_option["singular_values"]
                        if selected_option is not None
                        else []
                    ),
                    "selected_pairing_condition": (
                        selected_option["condition"]
                        if selected_option is not None
                        else None
                    ),
                    "green_cauchy": selected_green,
                    "qualified": accepted_option is not None,
                }
            )
            if report["qualified"]:
                qualified_blocks[right_index] = {
                    "right_block_index": right_index,
                    "right_indices": selected_right,
                    "adjoint_indices": selected_adjoint,
                    "selected_rank": len(selected_right),
                }
            block_reports.append(report)

        effective_indices = _closed_selected_component_indices(
            [
                component
                for component in right_blocks["components"]
                if set(component).issubset(bounded_right_indices)
            ],
            qualified_blocks,
        )
        effective_blocks = [qualified_blocks[index] for index in effective_indices]
        if effective_blocks:
            right_columns = np.column_stack(
                [
                    right_entries[item]["state"]
                    for selected in effective_blocks
                    for item in selected["right_indices"]
                ]
            )
            adjoint_columns = np.column_stack(
                [
                    adjoint_entries[item]["state"]
                    for selected in effective_blocks
                    for item in selected["adjoint_indices"]
                ]
            )
            green_pairing = endpoint_cauchy_balance(
                action,
                right_columns,
                adjoint_columns,
                multipliers=[
                    right_entries[item]["multiplier"]
                    for selected in effective_blocks
                    for item in selected["right_indices"]
                ],
                adjoint_multipliers=[
                    adjoint_entries[item]["multiplier"]
                    for selected in effective_blocks
                    for item in selected["adjoint_indices"]
                ],
            )
        effective_columns = sum(
            len(selected["right_indices"]) for selected in effective_blocks
        )
        global_green_gate = bool(
            green_pairing["green_pairing_relative"] is not None
            and green_pairing["green_pairing_relative"] <= 1.0e-10
            and green_pairing["primal_outward_balance_relative"] is not None
            and green_pairing["primal_outward_balance_relative"] <= 1.0e-10
            and green_pairing["adjoint_outward_balance_relative"] is not None
            and green_pairing["adjoint_outward_balance_relative"] <= 1.0e-10
        )
        contract_columns_ready = bool(120 <= effective_columns <= 360)
        contract_gate = {
            "passed": bool(
                contract_columns_ready
                and global_green_gate
                and all(
                    report["qualified"]
                    for report in block_reports
                    if report["right_block_index"] in effective_indices
                )
            ),
            "minimum_columns": 120,
            "maximum_columns": 360,
            "effective_columns": effective_columns,
            "raw_effective_columns": right_bounded["raw_effective_columns"],
            "bounded_effective_columns": right_bounded["bounded_effective_columns"],
            "global_mode_pool_green_cauchy_passed": global_green_gate,
            "reason": (
                "mode_pool_qualified"
                if contract_columns_ready and global_green_gate
                else "right_or_adjoint_block_closure_below_120"
                if effective_columns < 120
                else "bounded_dimension_exceeded"
                if effective_columns > 360
                else "mode_pool_green_cauchy_failed"
            ),
        }
        status = (
            "mode-pool-qualified"
            if contract_gate["passed"]
            else (
                "MODE_POOL_INCOMPLETE_AT_TARGET_SET"
                if effective_columns < 120
                else "MODE_POOL_CONTRACT_FAILED"
            )
        )
        right_npz_entries: list[dict[str, Any]] = []
        adjoint_npz_entries: list[dict[str, Any]] = []
        right_npz_blocks: list[list[int]] = []
        adjoint_npz_blocks: list[list[int]] = []
        for selected in effective_blocks:
            right_block = selected["right_indices"]
            adjoint_block = selected["adjoint_indices"]
            right_start = len(right_npz_entries)
            adjoint_start = len(adjoint_npz_entries)
            right_npz_entries.extend(right_entries[item] for item in right_block)
            adjoint_npz_entries.extend(adjoint_entries[item] for item in adjoint_block)
            right_npz_blocks.append(list(range(right_start, len(right_npz_entries))))
            adjoint_npz_blocks.append(
                list(range(adjoint_start, len(adjoint_npz_entries)))
            )
        emit(
            status,
            adjoint_solver=adjoint_solver,
            adjoint_stage_elapsed=adjoint_stage_wall,
            right_entries_for_output=right_npz_entries,
            right_blocks_for_output=right_npz_blocks,
            adjoint_entries_for_output=adjoint_npz_entries,
            effective_right_block_indices=effective_indices,
            effective_columns=effective_columns,
            reciprocal_adjoint=block_reports,
            adjoint_blocks_for_output=adjoint_npz_blocks,
            unmatched_blocks=unmatched_adjoint_blocks,
            contract_gate=contract_gate,
        )
    finally:
        if reversed_polynomial is not None:
            reversed_polynomial.destroy()
        if augmented is not None:
            augmented.destroy()
        if action is not None:
            action.destroy()
        if setup is not None:
            setup["condensed"].destroy()
            mpc = setup["one_cell_floquet"].mpc
            if hasattr(mpc, "destroy"):
                mpc.destroy()
        work_dir.cleanup()


if __name__ == "__main__":
    main()
