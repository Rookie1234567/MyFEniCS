"""Task036 R1b-1a full-interface right/physical-adjoint mode pool.

This runner reuses the existing one-cell local factor setup.  The augmented
sparse polynomial is the actual solver path; batched Schur action is used only
to verify its eliminated residual.  It is a fixed target-one mode-pool audit,
not a B1 capacity or production propagation solver.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
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
MODE_POOL_TARGET = 1.0
MODE_POOL_NEV = 128
MODE_POOL_MAX_IT = 100
MODE_POOL_WALL_LIMIT_SECONDS = 600.0
MODE_POOL_RSS_LIMIT_BYTES = 4 * 1024**3
MODE_POOL_SWAP_LIMIT_KIB = 0


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
    dirty = _git(
        "status",
        "--short",
        "--untracked-files=all",
    )
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
    right_pep = None
    adjoint_pep = None
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

        def create_pep(operators: list[PETSc.Mat]) -> SLEPc.PEP:
            pep = SLEPc.PEP().create(comm=PETSc.COMM_WORLD)
            pep.setOperators(operators)
            pep.setProblemType(SLEPc.PEP.ProblemType.GENERAL)
            pep.setType(SLEPc.PEP.Type.TOAR)
            pep.setDimensions(nev=MODE_POOL_NEV)
            pep.setTarget(MODE_POOL_TARGET)
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

        def solver_record(pep: SLEPc.PEP) -> dict[str, Any]:
            spectral_transform = pep.getST()
            ksp = spectral_transform.getKSP()
            pc = ksp.getPC()
            return {
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
            operators: tuple[PETSc.Mat, PETSc.Mat, PETSc.Mat],
            *,
            physical_adjoint: bool,
        ) -> tuple[list[complex], list[np.ndarray], list[dict[str, Any]]]:
            converged = int(pep.getConverged())
            vector = operators[0].createVecRight()
            multipliers: list[complex] = []
            states: list[np.ndarray] = []
            candidates: list[dict[str, Any]] = []
            try:
                for index in range(converged):
                    multiplier = complex(pep.getEigenpair(index, vector))
                    state = np.asarray(
                        vector.array,
                        dtype=np.complex128,
                    ).copy()
                    terms = [sparse_apply(operator, state) for operator in operators]
                    full_residual = (
                        terms[0] + multiplier * terms[1] + multiplier**2 * terms[2]
                    )
                    full_scale = (
                        np.linalg.norm(terms[0])
                        + abs(multiplier) * np.linalg.norm(terms[1])
                        + abs(multiplier) ** 2 * np.linalg.norm(terms[2])
                    )
                    if physical_adjoint:
                        endpoint_columns = np.zeros(
                            (action.port_rows, 2),
                            dtype=np.complex128,
                        )
                        endpoint_columns[: action.left_rows, 0] = state[
                            : action.left_rows
                        ]
                        endpoint_columns[action.left_rows :, 1] = state[
                            : action.left_rows
                        ]
                        adjoint_action = action.apply_adjoint_columns(endpoint_columns)
                        schur_terms = [
                            adjoint_action[action.left_rows :, 0],
                            adjoint_action[: action.left_rows, 0]
                            + adjoint_action[action.left_rows :, 1],
                            adjoint_action[: action.left_rows, 1],
                        ]
                    else:
                        values = state[: action.left_rows].reshape(
                            action.left_rows,
                            1,
                        )
                        k0, k1, k2 = bloch_polynomial_action(
                            action,
                            values,
                        )
                        schur_terms = [
                            k0[:, 0],
                            k1[:, 0],
                            k2[:, 0],
                        ]
                    schur_residual = (
                        schur_terms[0]
                        + multiplier * schur_terms[1]
                        + multiplier**2 * schur_terms[2]
                    )
                    schur_scale = (
                        np.linalg.norm(schur_terms[0])
                        + abs(multiplier) * np.linalg.norm(schur_terms[1])
                        + abs(multiplier) ** 2 * np.linalg.norm(schur_terms[2])
                    )
                    multipliers.append(multiplier)
                    states.append(state)
                    candidates.append(
                        {
                            "nu" if physical_adjoint else "lambda": _complex_pair(
                                multiplier
                            ),
                            "full_augmented_relative_residual": float(
                                np.linalg.norm(full_residual) / max(full_scale, 1.0e-30)
                            ),
                            "schur_polynomial_relative_residual": float(
                                np.linalg.norm(schur_residual)
                                / max(schur_scale, 1.0e-30)
                            ),
                            "endpoint_vector_norm_fraction": float(
                                np.linalg.norm(state[: action.left_rows])
                                / max(np.linalg.norm(state), 1.0e-30)
                            ),
                            "slepc_relative_error": float(
                                pep.computeError(
                                    index,
                                    SLEPc.PEP.ErrorType.RELATIVE,
                                )
                            ),
                        }
                    )
            finally:
                vector.destroy()
            return multipliers, states, candidates

        right_pep = create_pep([augmented.K0, augmented.K1, augmented.K2])
        right_pep.solve()
        right_multipliers, right_states, right_candidates = collect_pool(
            right_pep,
            (augmented.K0, augmented.K1, augmented.K2),
            physical_adjoint=False,
        )
        right_solver = solver_record(right_pep)
        right_pep.destroy()
        right_pep = None

        reversed_polynomial = build_reversed_hermitian_bloch_polynomial(augmented)
        adjoint_pep = create_pep(
            [
                reversed_polynomial.K0,
                reversed_polynomial.K1,
                reversed_polynomial.K2,
            ]
        )
        adjoint_pep.solve()
        adjoint_multipliers, adjoint_states, adjoint_candidates = collect_pool(
            adjoint_pep,
            (
                reversed_polynomial.K0,
                reversed_polynomial.K1,
                reversed_polynomial.K2,
            ),
            physical_adjoint=True,
        )
        adjoint_solver = solver_record(adjoint_pep)
        adjoint_pep.destroy()
        adjoint_pep = None

        def residual_ok(candidate: dict[str, Any]) -> bool:
            return (
                max(
                    candidate["full_augmented_relative_residual"],
                    candidate["schur_polynomial_relative_residual"],
                )
                <= 1.0e-7
            )

        right_blocks = _root_blocks(right_multipliers)
        adjoint_blocks = _root_blocks(adjoint_multipliers)
        right_reciprocal: dict[int, dict[str, Any]] = {}
        for right_block_index, right_block in enumerate(right_blocks):
            candidates = list(range(len(right_blocks)))
            partner = min(
                candidates,
                key=lambda index: _block_right_reciprocal_error(
                    [right_multipliers[item] for item in right_block],
                    [right_multipliers[item] for item in right_blocks[index]],
                ),
                default=None,
            )
            error = (
                _block_right_reciprocal_error(
                    [right_multipliers[item] for item in right_block],
                    [right_multipliers[item] for item in right_blocks[partner]],
                )
                if partner is not None
                else float("inf")
            )
            right_reciprocal[right_block_index] = {
                "partner_block_index": partner,
                "relative_error": float(error),
                "equal_size": bool(
                    partner is not None
                    and len(right_block) == len(right_blocks[partner])
                ),
                "mutual_partner": False,
                "closed": False,
            }
        for right_block_index, mapping in right_reciprocal.items():
            partner = mapping["partner_block_index"]
            mapping["mutual_partner"] = bool(
                partner is not None
                and right_reciprocal[partner]["partner_block_index"]
                == right_block_index
            )
            mapping["closed"] = bool(
                mapping["equal_size"]
                and mapping["mutual_partner"]
                and mapping["relative_error"] <= 1.0e-6
                and (
                    partner is None
                    or right_reciprocal[partner]["relative_error"] <= 1.0e-6
                )
            )
        reciprocal_components: list[list[int]] = []
        seen_reciprocal: set[int] = set()
        for root in range(len(right_blocks)):
            if root in seen_reciprocal or not right_reciprocal[root]["closed"]:
                continue
            partner = right_reciprocal[root]["partner_block_index"]
            component = [root] if partner == root else sorted([root, partner])
            if all(right_reciprocal[node]["closed"] for node in component):
                reciprocal_components.append(component)
                seen_reciprocal.update(component)

        right_to_adjoint = {
            right_block_index: min(
                range(len(adjoint_blocks)),
                key=lambda index: _block_adjoint_mapping_error(
                    [right_multipliers[item] for item in right_block],
                    [adjoint_multipliers[item] for item in adjoint_blocks[index]],
                ),
                default=None,
            )
            for right_block_index, right_block in enumerate(right_blocks)
        }
        adjoint_to_right = {
            adjoint_block_index: min(
                range(len(right_blocks)),
                key=lambda index: _block_adjoint_mapping_error(
                    [right_multipliers[item] for item in right_blocks[index]],
                    [
                        adjoint_multipliers[item]
                        for item in adjoint_blocks[adjoint_block_index]
                    ],
                ),
                default=None,
            )
            for adjoint_block_index in range(len(adjoint_blocks))
        }
        accepted_adjoint_mapping = {
            right_block_index: adjoint_block_index
            for right_block_index, adjoint_block_index in right_to_adjoint.items()
            if adjoint_block_index is not None
            and len(right_blocks[right_block_index])
            == len(adjoint_blocks[adjoint_block_index])
            and adjoint_to_right[adjoint_block_index] == right_block_index
            and _block_adjoint_mapping_error(
                [right_multipliers[item] for item in right_blocks[right_block_index]],
                [
                    adjoint_multipliers[item]
                    for item in adjoint_blocks[adjoint_block_index]
                ],
            )
            <= 1.0e-6
        }
        unmatched_adjoint_blocks = sorted(
            set(range(len(adjoint_blocks))) - set(accepted_adjoint_mapping.values())
        )
        block_reports: list[dict[str, Any]] = []
        qualified_blocks: list[tuple[int, list[int], list[int]]] = []
        for right_block_index, right_block in enumerate(right_blocks):
            adjoint_block_index = right_to_adjoint[right_block_index]
            if adjoint_block_index is None:
                block_reports.append(
                    {
                        "right_block_index": int(right_block_index),
                        "right_indices": right_block,
                        "adjoint_block_index": None,
                        "adjoint_indices": [],
                        "adjoint_mapping_relative_error": None,
                        "right_block_size": len(right_block),
                        "adjoint_block_size": 0,
                        "right_reciprocal": right_reciprocal[right_block_index],
                        "mutual_block_match": False,
                        "mapping_status": "unmapped",
                        "mapped": False,
                        "qualified": False,
                    }
                )
                continue
            adjoint_block = adjoint_blocks[adjoint_block_index]
            mapping_error = _block_adjoint_mapping_error(
                [right_multipliers[item] for item in right_block],
                [adjoint_multipliers[item] for item in adjoint_block],
            )
            report: dict[str, Any] = {
                "right_block_index": int(right_block_index),
                "right_indices": right_block,
                "adjoint_block_index": int(adjoint_block_index),
                "adjoint_indices": adjoint_block,
                "adjoint_mapping_relative_error": (
                    float(mapping_error) if np.isfinite(mapping_error) else None
                ),
                "right_block_size": len(right_block),
                "adjoint_block_size": len(adjoint_block),
                "right_reciprocal": right_reciprocal[right_block_index],
                "mutual_block_match": right_block_index in accepted_adjoint_mapping,
                "mapping_status": (
                    "mutual"
                    if right_block_index in accepted_adjoint_mapping
                    else "non_mutual"
                ),
                "mapped": right_block_index in accepted_adjoint_mapping,
                "qualified": False,
            }
            if (
                not report["mapped"]
                or not all(residual_ok(right_candidates[item]) for item in right_block)
                or not all(
                    residual_ok(adjoint_candidates[item]) for item in adjoint_block
                )
            ):
                block_reports.append(report)
                continue

            right_states_block = np.column_stack(
                [right_states[item] for item in right_block]
            )
            adjoint_states_block = np.column_stack(
                [adjoint_states[item] for item in adjoint_block]
            )
            derivative_columns = np.column_stack(
                [
                    sparse_apply(augmented.K1, state)
                    + 2.0 * right_multipliers[item] * sparse_apply(augmented.K2, state)
                    for item, state in zip(
                        right_block,
                        right_states_block.T,
                        strict=True,
                    )
                ]
            )
            cauchy_matrix = adjoint_states_block.conj().T @ derivative_columns
            row_norms = np.linalg.norm(adjoint_states_block, axis=0)
            derivative_norms = np.linalg.norm(derivative_columns, axis=0)
            normalizer = row_norms[:, None] * derivative_norms[None, :]
            normalized_pairing = np.divide(
                cauchy_matrix,
                normalizer,
                out=np.zeros_like(cauchy_matrix),
                where=normalizer > 1.0e-30,
            )
            singular_values = np.linalg.svd(
                normalized_pairing,
                compute_uv=False,
            )
            pairing_rcond = 1.0e-10
            rank = int(
                np.count_nonzero(
                    singular_values
                    > max(float(singular_values[0]), 1.0e-30) * pairing_rcond
                )
            )
            condition = float(singular_values[0] / max(singular_values[-1], 1.0e-30))
            condition_limit = 1.0 / pairing_rcond
            block_green = endpoint_cauchy_balance(
                action,
                right_states_block,
                adjoint_states_block,
                multipliers=[right_multipliers[item] for item in right_block],
                adjoint_multipliers=[
                    adjoint_multipliers[item] for item in adjoint_block
                ],
            )
            report.update(
                {
                    "pairing_matrix": "w_i^H*(K1+2*lambda_j*K2)*x_j",
                    "pairing_row_norms": row_norms.tolist(),
                    "pairing_derivative_column_norms": derivative_norms.tolist(),
                    "pairing_rcond": pairing_rcond,
                    "pairing_condition_limit": condition_limit,
                    "cauchy_pairing_singular_values": singular_values.tolist(),
                    "cauchy_pairing_rank": rank,
                    "cauchy_pairing_condition": condition,
                    "green_cauchy": block_green,
                    "qualified": bool(
                        rank == len(right_block)
                        and condition <= condition_limit
                        and block_green["green_pairing_relative"] <= 1.0e-10
                        and block_green["primal_outward_balance_relative"] <= 1.0e-10
                        and block_green["adjoint_outward_balance_relative"] <= 1.0e-10
                    ),
                }
            )
            if report["qualified"]:
                qualified_blocks.append((right_block_index, right_block, adjoint_block))
            block_reports.append(report)

        qualified_by_index = {
            right_block_index for right_block_index, _, _ in qualified_blocks
        }
        effective_right_block_indices = {
            right_block_index
            for component in reciprocal_components
            if all(index in qualified_by_index for index in component)
            for right_block_index in component
        }
        effective_blocks = [
            (right_block_index, right_block, adjoint_block)
            for right_block_index, right_block, adjoint_block in qualified_blocks
            if right_block_index in effective_right_block_indices
        ]
        green_pairing: dict[str, Any] = {
            "columns": 0,
            "green_pairing_relative": None,
            "primal_outward_balance_relative": None,
            "adjoint_outward_balance_relative": None,
        }
        if effective_blocks:
            right_columns = np.column_stack(
                [
                    right_states[item]
                    for _, right_block, _ in effective_blocks
                    for item in right_block
                ]
            )
            adjoint_columns = np.column_stack(
                [
                    adjoint_states[item]
                    for _, _, adjoint_block in effective_blocks
                    for item in adjoint_block
                ]
            )
            green_pairing = endpoint_cauchy_balance(
                action,
                right_columns,
                adjoint_columns,
                multipliers=[
                    right_multipliers[item]
                    for _, right_block, _ in effective_blocks
                    for item in right_block
                ],
                adjoint_multipliers=[
                    adjoint_multipliers[item]
                    for _, _, adjoint_block in effective_blocks
                    for item in adjoint_block
                ],
            )
        effective_columns = sum(
            len(right_block) for _, right_block, _ in effective_blocks
        )
        elapsed = float(time.perf_counter() - started)
        ru_maxrss_kib = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        swap_kib = _current_swap_kib()
        diagnostic_within_nominal_limits = bool(
            elapsed <= MODE_POOL_WALL_LIMIT_SECONDS
            and ru_maxrss_kib * 1024 <= MODE_POOL_RSS_LIMIT_BYTES
            and swap_kib <= MODE_POOL_SWAP_LIMIT_KIB
        )
        contract_gate = bool(
            effective_columns >= 120
            and green_pairing["green_pairing_relative"] is not None
            and green_pairing["green_pairing_relative"] <= 1.0e-10
            and green_pairing["primal_outward_balance_relative"] <= 1.0e-10
            and green_pairing["adjoint_outward_balance_relative"] <= 1.0e-10
            and all(
                report["qualified"]
                for report in block_reports
                if report["right_block_index"] in effective_right_block_indices
            )
        )
        status = (
            "MODE_POOL_INCOMPLETE_AT_TARGET1"
            if effective_columns < 120
            else "mode-pool-qualified"
            if contract_gate
            else "MODE_POOL_CONTRACT_FAILED"
        )
        payload = {
            "schema_version": "task036.r1b-1a-physical-adjoint-mode-pool.v1",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "capacity_claim": "not_run",
            "source": {
                "sha": source_sha,
                "branch": _git("branch", "--show-current"),
                "petsc_int_type": str(np.dtype(PETSc.IntType)),
                "clean_src_benchmarks": not bool(dirty),
                "working_tree_status": dirty,
            },
            "solver": {
                "type": "SLEPc.PEP/TOAR with sparse augmented coefficients",
                "target": MODE_POOL_TARGET,
                "nev": MODE_POOL_NEV,
                "max_it": MODE_POOL_MAX_IT,
                "right": right_solver,
                "physical_adjoint": adjoint_solver,
            },
            "polynomial": {
                "equation": "S_RL + lambda*(S_RR + S_LL) + lambda^2*S_LR",
                "physical_adjoint_equation": ("K2^H + nu*K1^H + nu^2*K0^H"),
                "right_candidates": right_candidates,
                "physical_adjoint_candidates": adjoint_candidates,
                "right_root_blocks": right_blocks,
                "adjoint_root_blocks": adjoint_blocks,
                "right_reciprocal_block_mappings": right_reciprocal,
                "right_reciprocal_components": reciprocal_components,
                "effective_right_block_indices": sorted(effective_right_block_indices),
                "right_near_degenerate_groups": _groups(
                    right_multipliers,
                    reciprocal=False,
                ),
                "adjoint_near_degenerate_groups": _groups(
                    adjoint_multipliers,
                    reciprocal=False,
                ),
                "reciprocal_adjoint_block_mappings": block_reports,
                "unmatched_adjoint_block_indices": unmatched_adjoint_blocks,
                "reciprocal_closed_effective_columns": effective_columns,
                "mode_pool_green_cauchy": green_pairing,
            },
            "objects": {
                "state_rows": int(augmented.state_rows),
                "endpoint_rows": [int(action.left_rows), int(action.right_rows)],
                "interior_rows": int(action.interior_rows),
                "interior_matrix_nnz": int(action.interior_matrix_nnz),
                "right_sparse_polynomial_matrices": [
                    matrix_record(operator)
                    for operator in (augmented.K0, augmented.K1, augmented.K2)
                ],
                "physical_adjoint_sparse_polynomial_matrices": [
                    matrix_record(operator)
                    for operator in (
                        reversed_polynomial.K0,
                        reversed_polynomial.K1,
                        reversed_polynomial.K2,
                    )
                ],
                "resident_dense_interface_square_formed": bool(
                    augmented.dense_interface_square_formed
                ),
                "resident_full_interface_square_shape": None,
                "resident_transfer_matrix": False,
            },
            "timing_seconds": {
                "wall": elapsed,
                "wall_limit_seconds": MODE_POOL_WALL_LIMIT_SECONDS,
            },
            "resource": {
                "ru_maxrss_kib": ru_maxrss_kib,
                "rss_bytes": ru_maxrss_kib * 1024,
                "rss_limit_bytes": MODE_POOL_RSS_LIMIT_BYTES,
                "rss_scope": "MPI1 process lifetime peak",
                "swap_kib": swap_kib,
                "swap_limit_kib": MODE_POOL_SWAP_LIMIT_KIB,
                "swap_scope": "current MPI1 process VmSwap diagnostic",
                "diagnostic_within_nominal_limits": diagnostic_within_nominal_limits,
                "formal_gate": (
                    "external process-tree watchdog must provide wall, "
                    "simultaneous RSS peak, and swap=0"
                ),
            },
        }
        if comm.rank == 0:
            args.output.parent.mkdir(parents=True, exist_ok=True)
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
    finally:
        if adjoint_pep is not None:
            adjoint_pep.destroy()
        if right_pep is not None:
            right_pep.destroy()
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
