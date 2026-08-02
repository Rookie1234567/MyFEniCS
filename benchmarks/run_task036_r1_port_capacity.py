"""Task036 R1b-1a full-interface right/physical-adjoint mode pool.

This runner reuses the existing one-cell local factor setup.  The augmented
sparse polynomial is the actual solver path; batched Schur action is used only
to verify its eliminated residual.  Four fixed reciprocal-variable polynomial
families and four fixed phase targets form a deterministic mode-pool audit;
this is not a B1 capacity or production propagation solver.
"""

from __future__ import annotations

import argparse
import hashlib
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
MODE_POOL_TARGETS = (1.0 + 0.0j, 1.0j, -1.0 + 0.0j, -1.0j)
MODE_POOL_FAMILIES = ("P", "Prev", "Q", "Qrev")
MODE_POOL_NEV = 128
MODE_POOL_MAX_IT = 100
MODE_POOL_WALL_LIMIT_SECONDS = 3600.0
MODE_POOL_RSS_LIMIT_BYTES = 4 * 1024**3
MODE_POOL_SWAP_LIMIT_KIB = 0
MODE_POOL_BLOCK_TOL = 1.0e-6
MODE_POOL_RESIDUAL_TOL = 1.0e-7


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


def _right_pool_gate(effective_columns: int) -> dict[str, Any]:
    passed = int(effective_columns) >= 120
    return {
        "passed": passed,
        "effective_columns": int(effective_columns),
        "minimum_columns": 120,
        "reason": (
            "right_pool_ready_for_Q_Qrev"
            if passed
            else "right_pool_effective_columns_below_120"
        ),
        "status_if_failed": "MODE_POOL_INCOMPLETE_AT_TARGET_SET",
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

        def create_pep(
            operators: tuple[PETSc.Mat, PETSc.Mat, PETSc.Mat],
            target: complex,
        ) -> SLEPc.PEP:
            pep = SLEPc.PEP().create(comm=PETSc.COMM_WORLD)
            pep.setOperators(list(operators))
            pep.setProblemType(SLEPc.PEP.ProblemType.GENERAL)
            pep.setType(SLEPc.PEP.Type.TOAR)
            pep.setDimensions(nev=MODE_POOL_NEV)
            pep.setTarget(target)
            pep.setWhichEigenpairs(SLEPc.PEP.Which.TARGET_MAGNITUDE)
            pep.setTolerances(tol=1.0e-8, max_it=MODE_POOL_MAX_IT)
            spectral_transform = pep.getST()
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
            spectral_transform = pep.getST()
            ksp = spectral_transform.getKSP()
            pc = ksp.getPC()
            return {
                "family": family,
                "target_index": int(target_index),
                "target": _complex_pair(target),
                "st_type": str(spectral_transform.getType()),
                "ksp_type": str(ksp.getType()),
                "pc_type": str(pc.getType()),
                "factor_solver_type": pc.getFactorSolverType(),
                "converged": int(pep.getConverged()),
                "iteration_number": int(pep.getIterationNumber()),
                "convergence_reason": int(pep.getConvergedReason()),
            }

        def collect_pool(
            pep: SLEPc.PEP,
            family: str,
            target_index: int,
            target: complex,
            canonical_operators: tuple[PETSc.Mat, PETSc.Mat, PETSc.Mat],
            *,
            physical_adjoint: bool,
        ) -> list[dict[str, Any]]:
            entries: list[dict[str, Any]] = []
            vector = canonical_operators[0].createVecRight()
            try:
                for index in range(int(pep.getConverged())):
                    source_multiplier = complex(pep.getEigenpair(index, vector))
                    state = np.asarray(
                        vector.array,
                        dtype=np.complex128,
                    ).copy()
                    variable, multiplier, state, mapping = _canonicalize_candidate(
                        family,
                        source_multiplier,
                        state,
                        endpoint_rows=action.left_rows,
                    )
                    terms = tuple(
                        sparse_apply(operator, state)
                        for operator in canonical_operators
                    )
                    full_residual = _polynomial_relative_residual(terms, multiplier)
                    electric = state[: action.left_rows].reshape(-1, 1)
                    if physical_adjoint:
                        columns = np.zeros(
                            (action.port_rows, 2),
                            dtype=np.complex128,
                        )
                        columns[: action.left_rows, 0] = electric[:, 0]
                        columns[action.left_rows :, 1] = electric[:, 0]
                        applied = action.apply_adjoint_columns(columns)
                        schur_terms = (
                            applied[action.left_rows :, 0],
                            applied[: action.left_rows, 0]
                            + applied[action.left_rows :, 1],
                            applied[: action.left_rows, 1],
                        )
                    else:
                        schur_terms = tuple(
                            column[:, 0]
                            for column in bloch_polynomial_action(action, electric)
                        )
                    schur_residual = _polynomial_relative_residual(
                        schur_terms, multiplier
                    )
                    record = {
                        "family": family,
                        "target_index": int(target_index),
                        "target": _complex_pair(target),
                        "variable": variable,
                        "source_multiplier": mapping["source_multiplier"],
                        "canonical_multiplier": mapping["canonical_multiplier"],
                        variable: mapping["canonical_multiplier"],
                        "canonical_mapping": mapping,
                        "full_augmented_relative_residual": full_residual,
                        "schur_polynomial_relative_residual": schur_residual,
                        "endpoint_vector_norm_fraction": float(
                            np.linalg.norm(electric)
                            / max(float(np.linalg.norm(state)), 1.0e-30)
                        ),
                        "slepc_relative_error": float(
                            pep.computeError(
                                index,
                                SLEPc.PEP.ErrorType.RELATIVE,
                            )
                        ),
                    }
                    entries.append(
                        {
                            "family": family,
                            "target_index": int(target_index),
                            "source_key": (family, int(target_index)),
                            "multiplier": multiplier,
                            "state": state,
                            "record": record,
                        }
                    )
            finally:
                vector.destroy()
            return entries

        def run_family(
            family: str,
            target_index: int,
            target: complex,
            source_operators: tuple[PETSc.Mat, PETSc.Mat, PETSc.Mat],
            canonical_operators: tuple[PETSc.Mat, PETSc.Mat, PETSc.Mat],
            *,
            physical_adjoint: bool,
        ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
            pep = create_pep(source_operators, target)
            try:
                pep.solve()
                solver = solver_record(pep, family, target_index, target)
                entries = collect_pool(
                    pep,
                    family,
                    target_index,
                    target,
                    canonical_operators,
                    physical_adjoint=physical_adjoint,
                )
                return solver, entries
            finally:
                pep.destroy()

        right_specs = {
            "P": (augmented.K0, augmented.K1, augmented.K2),
            "Prev": (augmented.K2, augmented.K1, augmented.K0),
        }
        right_runs: list[dict[str, Any]] = []
        right_raw: list[dict[str, Any]] = []
        right_stage_started = time.perf_counter()
        for family in ("P", "Prev"):
            for target_index, target in enumerate(MODE_POOL_TARGETS):
                solver, entries = run_family(
                    family,
                    target_index,
                    target,
                    right_specs[family],
                    (augmented.K0, augmented.K1, augmented.K2),
                    physical_adjoint=False,
                )
                right_runs.append(
                    {
                        "solver": solver,
                        "raw_candidate_count": len(entries),
                        "family": family,
                        "target_index": int(target_index),
                        "target": _complex_pair(target),
                    }
                )
                right_raw.extend(entries)
        right_stage_wall = float(time.perf_counter() - right_stage_started)
        right_entries, right_removed = _deduplicate_candidates(right_raw)
        right_blocks = _right_reciprocal_closure(
            [entry["multiplier"] for entry in right_entries],
            right_entries,
        )
        right_convergence_failures = [
            run for run in right_runs if run["solver"]["convergence_reason"] <= 0
        ]
        right_bounded = _bounded_right_components(right_blocks)
        right_gate = (
            {
                "passed": False,
                "effective_columns": right_bounded["bounded_effective_columns"],
                "raw_effective_columns": right_bounded["raw_effective_columns"],
                "bounded_effective_columns": right_bounded["bounded_effective_columns"],
                "minimum_columns": 120,
                "reason": "right_solver_failed",
                "status_if_failed": "MODE_POOL_SOLVER_FAILED",
            }
            if right_convergence_failures
            else _right_pool_gate(right_bounded["bounded_effective_columns"])
        )
        right_gate["raw_effective_columns"] = right_bounded["raw_effective_columns"]
        right_gate["bounded_effective_columns"] = right_bounded[
            "bounded_effective_columns"
        ]
        for run in right_runs:
            key = (run["family"], run["target_index"])
            selected = [entry for entry in right_entries if entry["source_key"] == key]
            run["retained_candidate_count"] = len(selected)
            run["residual_qualified_count"] = sum(
                _residual_ok(entry) for entry in selected
            )
            run["deduplicated_count"] = run["raw_candidate_count"] - len(selected)

        right_solver = {
            "status": "solver_failed" if right_convergence_failures else "completed",
            "run_count": len(right_runs),
            "runs": right_runs,
        }
        adjoint_runs: list[dict[str, Any]] = []
        adjoint_entries: list[dict[str, Any]] = []
        adjoint_removed = {family: 0 for family in MODE_POOL_FAMILIES}
        adjoint_blocks: list[list[int]] = []
        block_reports: list[dict[str, Any]] = []
        unmatched_adjoint_blocks: list[int] = []
        green_pairing: dict[str, Any] = {
            "columns": 0,
            "green_pairing_relative": None,
            "primal_outward_balance_relative": None,
            "adjoint_outward_balance_relative": None,
        }
        adjoint_stage_wall: float | None = None

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
                    "type": "SLEPc.PEP/TOAR with sparse augmented coefficients",
                    "target": 1.0,
                    "targets": [_complex_pair(target) for target in MODE_POOL_TARGETS],
                    "families": list(MODE_POOL_FAMILIES),
                    "nev": MODE_POOL_NEV,
                    "max_it": MODE_POOL_MAX_IT,
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
                    "right_stage": right_stage_wall,
                    "physical_adjoint_stage": adjoint_stage_elapsed,
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
                    "status": "not_run",
                    "reason": right_gate["reason"],
                    "runs": [],
                },
                adjoint_stage_elapsed=None,
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
                    "adjoint_stage": "not_run",
                },
            )
            return

        reversed_polynomial = build_reversed_hermitian_bloch_polynomial(augmented)
        adjoint_specs = {
            "Q": (
                reversed_polynomial.K0,
                reversed_polynomial.K1,
                reversed_polynomial.K2,
            ),
            "Qrev": (
                reversed_polynomial.K2,
                reversed_polynomial.K1,
                reversed_polynomial.K0,
            ),
        }
        adjoint_stage_started = time.perf_counter()
        for family in ("Q", "Qrev"):
            for target_index, target in enumerate(MODE_POOL_TARGETS):
                solver, entries = run_family(
                    family,
                    target_index,
                    target,
                    adjoint_specs[family],
                    (
                        reversed_polynomial.K0,
                        reversed_polynomial.K1,
                        reversed_polynomial.K2,
                    ),
                    physical_adjoint=True,
                )
                adjoint_runs.append(
                    {
                        "solver": solver,
                        "raw_candidate_count": len(entries),
                        "family": family,
                        "target_index": int(target_index),
                        "target": _complex_pair(target),
                    }
                )
                adjoint_entries.extend(entries)
        adjoint_stage_wall = float(time.perf_counter() - adjoint_stage_started)
        adjoint_entries, adjoint_removed = _deduplicate_candidates(adjoint_entries)
        adjoint_blocks = _root_blocks(
            [entry["multiplier"] for entry in adjoint_entries]
        )
        for run in adjoint_runs:
            key = (run["family"], run["target_index"])
            selected = [
                entry for entry in adjoint_entries if entry["source_key"] == key
            ]
            run["retained_candidate_count"] = len(selected)
            run["residual_qualified_count"] = sum(
                _residual_ok(entry) for entry in selected
            )
            run["deduplicated_count"] = run["raw_candidate_count"] - len(selected)
        adjoint_solver = {
            "status": "completed",
            "run_count": len(adjoint_runs),
            "runs": adjoint_runs,
        }
        adjoint_convergence_failures = [
            run for run in adjoint_runs if run["solver"]["convergence_reason"] <= 0
        ]
        if adjoint_convergence_failures:
            adjoint_solver["status"] = "solver_failed"
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
        qualified_blocks: list[tuple[int, list[int], list[int]]] = []
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
            if not report["mapped"] or not (
                all(_residual_ok(right_entries[item]) for item in right_block)
                and all(_residual_ok(adjoint_entries[item]) for item in adjoint_block)
            ):
                block_reports.append(report)
                continue
            right_states = np.column_stack(
                [right_entries[item]["state"] for item in right_block]
            )
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
            singular_values = np.linalg.svd(normalized, compute_uv=False)
            pairing_rcond = 1.0e-10
            rank = int(
                np.count_nonzero(
                    singular_values
                    > max(float(singular_values[0]), 1.0e-30) * pairing_rcond
                )
            )
            condition = float(
                singular_values[0] / max(float(singular_values[-1]), 1.0e-30)
            )
            green = endpoint_cauchy_balance(
                action,
                right_states,
                adjoint_states,
                multipliers=[right_entries[item]["multiplier"] for item in right_block],
                adjoint_multipliers=[
                    adjoint_entries[item]["multiplier"] for item in adjoint_block
                ],
            )
            report.update(
                {
                    "pairing_matrix": "w_i^H*(K1+2*lambda_j*K2)*x_j",
                    "pairing_row_norms": row_norms.tolist(),
                    "pairing_derivative_column_norms": derivative_norms.tolist(),
                    "pairing_rcond": pairing_rcond,
                    "pairing_condition_limit": 1.0e10,
                    "cauchy_pairing_singular_values": singular_values.tolist(),
                    "cauchy_pairing_rank": rank,
                    "cauchy_pairing_condition": condition,
                    "green_cauchy": green,
                    "qualified": bool(
                        rank == len(right_block)
                        and condition <= 1.0e10
                        and green["green_pairing_relative"] <= 1.0e-10
                        and green["primal_outward_balance_relative"] <= 1.0e-10
                        and green["adjoint_outward_balance_relative"] <= 1.0e-10
                    ),
                }
            )
            if report["qualified"]:
                qualified_blocks.append((right_index, right_block, adjoint_block))
            block_reports.append(report)

        qualified_indices = {item[0] for item in qualified_blocks}
        effective_indices = sorted(
            index
            for component in right_blocks["components"]
            if set(component).issubset(bounded_right_indices)
            and all(index in qualified_indices for index in component)
            for index in component
        )
        effective_blocks = [
            item for item in qualified_blocks if item[0] in effective_indices
        ]
        if effective_blocks:
            right_columns = np.column_stack(
                [
                    right_entries[item]["state"]
                    for _, block, _ in effective_blocks
                    for item in block
                ]
            )
            adjoint_columns = np.column_stack(
                [
                    adjoint_entries[item]["state"]
                    for _, _, block in effective_blocks
                    for item in block
                ]
            )
            green_pairing = endpoint_cauchy_balance(
                action,
                right_columns,
                adjoint_columns,
                multipliers=[
                    right_entries[item]["multiplier"]
                    for _, block, _ in effective_blocks
                    for item in block
                ],
                adjoint_multipliers=[
                    adjoint_entries[item]["multiplier"]
                    for _, _, block in effective_blocks
                    for item in block
                ],
            )
        effective_columns = sum(len(block) for _, block, _ in effective_blocks)
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
        for _, right_block, adjoint_block in effective_blocks:
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
