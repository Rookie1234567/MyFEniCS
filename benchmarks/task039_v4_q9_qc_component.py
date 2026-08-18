"""Research-only setup component for the fixed Task039 Q-C batching probe."""

from __future__ import annotations

import argparse
import gc
import hashlib
import inspect
import json
import sys
import time
from pathlib import Path
from typing import Any, Mapping

import numpy as np
from mpi4py import MPI
from scipy.optimize import linear_sum_assignment

from benchmarks.task039_v4_h4_hybrid_direct import (
    _validate_shared_h4_mode_identity,
    validate_v4_h4_specification,
)
from benchmarks.task039_v4_q9_qb_component import (
    _json_default,
    _sha256,
    _source_provenance,
)
from src.io.input_validation import (
    load_and_resolve,
    simulation_config_3d_from_normalized,
)
from src.modes.cross_section_spaces import (
    build_cross_section_spaces,
    build_matching_cross_section,
)
from src.modes.quadratic_beta_eigenproblem import (
    assemble_quadratic_beta_operators,
    solve_quadratic_beta_modes,
)

TOTAL_MODES = 8
BATCH_SIZE = 4
NUMERICAL_TOLERANCE = 1.0e-8


def _complex(value: Any) -> complex:
    pair = list(value)
    if len(pair) != 2:
        raise ValueError("authority complex value must be [real, imaginary]")
    return complex(float(pair[0]), float(pair[1]))


def _pair(value: complex) -> list[float]:
    return [float(value.real), float(value.imag)]


def fixed_target_plan(manifest: Mapping[str, Any]) -> dict[str, Any]:
    if manifest.get("mode_count") != 480 or manifest.get("rank_count") != 8:
        raise ValueError("Q-C requires the shared h4/M480/MPI8 packet authority")
    betas = [_complex(value) for value in manifest["selection"]["positive"]["beta"]]
    if len(betas) < TOTAL_MODES:
        raise ValueError("M480 authority has fewer than eight positive beta values")
    return {
        "one_shot": complex(np.mean(betas[0:8])),
        "batch1": complex(np.mean(betas[0:4])),
        "batch2": complex(np.mean(betas[4:8])),
        "authority_prefix": betas[0:8],
        "source": "manifest.selection.positive.beta fixed slices [0:8], [0:4], [4:8]",
    }


def match_beta_sets(
    reference: list[complex], observed: list[complex]
) -> dict[str, Any]:
    observed_duplicate_count = sum(
        any(
            other != index
            and abs(value - observed[other])
            / max(abs(value), abs(observed[other]), 1.0e-30)
            <= NUMERICAL_TOLERANCE
            for other in range(len(observed))
        )
        for index, value in enumerate(observed)
    )
    if len(reference) != len(observed):
        return {
            "status": "count_mismatch",
            "identity_pass": False,
            "one_to_one": False,
            "observed_duplicate_count": observed_duplicate_count,
            "missing_count": max(len(reference) - len(observed), 0),
            "extra_count": max(len(observed) - len(reference), 0),
            "max_relative_error": None,
            "relative_errors": [],
        }
    cost = np.asarray(
        [[abs(a - b) / max(abs(a), 1.0e-30) for b in observed] for a in reference],
        dtype=float,
    )
    rows, columns = linear_sum_assignment(cost)
    errors = cost[rows, columns]
    matched = int(np.count_nonzero(errors <= NUMERICAL_TOLERANCE))
    return {
        "status": "measured",
        "one_to_one": True,
        "identity_pass": matched == len(reference),
        "observed_duplicate_count": observed_duplicate_count,
        "missing_count": len(reference) - matched,
        "extra_count": len(observed) - matched,
        "max_relative_error": float(np.max(errors, initial=0.0)),
        "relative_errors": [float(value) for value in errors],
        "tolerance": NUMERICAL_TOLERANCE,
    }


def lifecycle_source_contract() -> dict[str, Any]:
    lines, start = inspect.getsourcelines(solve_quadratic_beta_modes)
    source = "".join(lines)
    counts = {
        "pep_create": source.count("SLEPc.PEP().create(comm=comm)"),
        "sinvert": source.count("SLEPc.ST.Type.SINVERT"),
        "ksp_preonly": source.count("PETSc.KSP.Type.PREONLY"),
        "pc_lu": source.count("PETSc.PC.Type.LU"),
        "mumps": source.count('setFactorSolverType("mumps")'),
        "pep_destroy": source.count("pep.destroy()"),
    }
    verified = all(value == 1 for value in counts.values())
    return {
        "source": "src/modes/quadratic_beta_eigenproblem.py::solve_quadratic_beta_modes",
        "source_start_line": start,
        "source_end_line": start + len(lines) - 1,
        "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
        "object_counts": counts,
        "verified": verified,
        "factor_reuse": False,
        "reason": "solve API has no PEP/ST/KSP/PC/factor handle parameter or return",
    }


def solve_call(
    operators: Any, target: complex, requested: int, comm: Any
) -> dict[str, Any]:
    started = time.perf_counter()
    modes, report = solve_quadratic_beta_modes(
        operators,
        target=target,
        requested_modes=requested,
        tolerance=1.0e-10,
        max_iterations=500,
    )
    try:
        snapshot = {
            "target": _pair(target),
            "requested_modes": int(report.requested_modes),
            "converged_modes": int(report.converged_modes),
            "iteration_count": int(report.iteration_count),
            "convergence_reason": int(report.convergence_reason),
            "returned_modes": len(modes),
            "betas": [_pair(mode.beta) for mode in modes],
            "polynomial_relative_residuals": [
                float(mode.polynomial_relative_residual) for mode in modes
            ],
            "slepc_relative_errors": [
                float(mode.slepc_relative_error) for mode in modes
            ],
        }
    finally:
        for mode in modes:
            mode.destroy()
        snapshot["wall_seconds"] = float(
            comm.allreduce(time.perf_counter() - started, op=MPI.MAX)
        )
    return snapshot


def run_component(args: argparse.Namespace) -> dict[str, Any] | None:
    comm = MPI.COMM_WORLD
    if comm.size != 8:
        raise RuntimeError(f"Q-C requires MPI8, got {comm.size}")
    provenance = _source_provenance(comm, args.audit_source_sha)
    input_path = Path(args.input).resolve()
    manifest_path = Path(args.packet_manifest).resolve()
    identity_path = Path(args.identity_json).resolve()
    specification = load_and_resolve(input_path)
    payload = specification.as_jsonable()
    validate_v4_h4_specification(specification)
    identity = json.loads(identity_path.read_text())
    _validate_shared_h4_mode_identity(identity, payload)
    manifest_sha = _sha256(manifest_path)
    if manifest_sha != args.expected_manifest_sha:
        raise RuntimeError("Q-C manifest SHA mismatch")
    manifest = json.loads(manifest_path.read_text())
    targets = fixed_target_plan(manifest)
    lifecycle = lifecycle_source_contract()
    if not lifecycle["verified"]:
        raise RuntimeError("Q-C lifecycle source contract failed")
    cfg = simulation_config_3d_from_normalized(payload)
    cross_section = build_matching_cross_section(cfg, "stage4_xy", comm=comm)
    spaces = build_cross_section_spaces(cross_section, transverse_degree=6)
    operators = None
    try:
        operators = assemble_quadratic_beta_operators(cfg, cross_section, spaces)
        one_shot = solve_call(operators, targets["one_shot"], TOTAL_MODES, comm)
        batch1 = solve_call(operators, targets["batch1"], BATCH_SIZE, comm)
        batch2 = solve_call(operators, targets["batch2"], BATCH_SIZE, comm)
        batch = {
            "calls": [batch1, batch2],
            "betas": batch1["betas"] + batch2["betas"],
            "solver_call_count": 2,
            "wall_seconds": batch1["wall_seconds"] + batch2["wall_seconds"],
        }
        authority = targets["authority_prefix"]
        one_betas = [_complex(value) for value in one_shot["betas"]]
        batch_betas = [_complex(value) for value in batch["betas"]]
        comparisons = {
            "one_shot_vs_batch": match_beta_sets(one_betas, batch_betas),
            "one_shot_vs_authority": match_beta_sets(authority, one_betas),
            "batch_vs_authority": match_beta_sets(authority, batch_betas),
        }
        batch["max_polynomial_relative_residual"] = max(
            value
            for call in batch["calls"]
            for value in call["polynomial_relative_residuals"]
        )
        one_shot["max_polynomial_relative_residual"] = max(
            one_shot["polynomial_relative_residuals"]
        )
        wall_increase = (
            batch["wall_seconds"] / max(one_shot["wall_seconds"], 1.0e-30) - 1.0
        )
        identity_pass = all(value["identity_pass"] for value in comparisons.values())
        result = {
            "schema": "task039.v4-9-q-c-component.v1",
            "status": "NOT_ESTABLISHED",
            "execution_status": "completed",
            "provenance": {**provenance, "argv": list(sys.argv)},
            "inputs": {
                "input": {
                    "path": str(input_path),
                    "sha256": specification.input_sha256,
                },
                "manifest": {"path": str(manifest_path), "sha256": manifest_sha},
                "identity": {
                    "path": str(identity_path),
                    "file_sha256": _sha256(identity_path),
                },
            },
            "fixed_targets": {
                "source": targets["source"],
                "one_shot": _pair(targets["one_shot"]),
                "batch1": _pair(targets["batch1"]),
                "batch2": _pair(targets["batch2"]),
                "nev": {"one_shot": 8, "each_batch": 4},
            },
            "solver_lifecycle": {
                **lifecycle,
                "operator_assembly_count": 1,
                "one_shot_call_count": 1,
                "two_batch_call_count": 2,
                "one_shot_factor_lifecycle_count": 1,
                "two_batch_factor_lifecycle_count": 2,
            },
            "one_shot": one_shot,
            "two_batch": batch,
            "comparisons": comparisons,
            "gates": {
                "numerical_equivalent": {
                    "pass": identity_pass,
                    "tolerance": NUMERICAL_TOLERANCE,
                },
                "one_shot_polynomial_residual_pass": one_shot[
                    "max_polynomial_relative_residual"
                ]
                <= 1.0e-10,
                "two_batch_polynomial_residual_pass": batch[
                    "max_polynomial_relative_residual"
                ]
                <= 1.0e-10,
                "wall_increase": {
                    "pass": wall_increase <= 0.20,
                    "value": wall_increase,
                    "limit": 0.20,
                },
                "peak_rss_reduction": {
                    "status": "NOT_ESTABLISHED",
                    "pass": None,
                    "value": None,
                    "limit": 0.30,
                    "reason": "process-tree RSS was not measured",
                },
                "overall": {"status": "NOT_ESTABLISHED", "pass": False},
            },
            "resources": {
                "process_tree_peak_rss_mib": {
                    "status": "not_measured",
                    "value": None,
                },
                "swap": {"status": "not_measured", "value": None},
            },
        }
    finally:
        if operators is not None:
            operators.destroy()
        del operators, spaces, cross_section
        gc.collect()
    comm.barrier()
    if comm.rank == 0:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(result, default=_json_default, indent=2, sort_keys=True) + "\n"
        )
        return result
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("input", "packet_manifest", "identity_json", "output"):
        parser.add_argument(f"--{name.replace('_', '-')}", type=Path, required=True)
    parser.add_argument("--expected-manifest-sha", required=True)
    parser.add_argument("--audit-source-sha", required=True)
    run_component(parser.parse_args())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
