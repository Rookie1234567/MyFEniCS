"""Thin LA0 diagnostic worker for the one failed N2 exact class.

The worker reuses the frozen N2 case/builder and captures only the matrix
present immediately before the original class registration fails.  It never
changes the production factor solve and never builds modes, regional coarse
objects, a physical action, or a source/residual.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping

import numpy as np


LA0_SCHEMA = "task038.full3d.local-spectral.la0-record.v1"
LA0_STAGE = "la0_single_failed_class"
LA0_CASE = "p6-h10-mpi1"
LA0_DEGREE = 6
LA0_MESH_TARGET_NM = 10.0
LA0_SOLVE_LIMIT = 1.0e-11
LA0_RHS_OFFSET = 0.125 + 0.25j
LA0_OLD_N2_V1_RESIDUAL = 1.0426245523812324e-11
LA0_OLD_N2_V1_COMPACT_PATH = (
    "docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/"
    "n2_local_spectral_setup_mpi1_v1.json"
)
LA0_OLD_N2_V1_COMPACT_SHA256 = (
    "d02f416956a560c0837d067636d8f62d253c9d04da4e6bbe3b6194dd10098d40"
)
LA0_OLD_N2_V1_SOURCE_SHA = "907fe8fb204cffa34a921c6d0cab7ff4dd4831b8"
LA0_FAILURE_ORDER_RULE = "global_sorted_exact_class_digests"
LA1_SCHEMA = "task038.full3d.local-spectral.la1-diagnostic.v1"
LA1_BACKWARD_ERROR_LIMIT = LA0_SOLVE_LIMIT
LA1_LARGE_KAPPA_LIMIT = 1.0 / LA0_SOLVE_LIMIT


def failed_class_selection_key(class_digest: str, slot: int) -> tuple[int, str]:
    """Return the frozen class-slot order used by the N2 builder."""

    return int(slot), str(class_digest)


def fixed_rhs(rows: int) -> np.ndarray:
    """Return the frozen diagnostic RHS, independent of physical sources."""

    count = int(rows)
    if count < 1:
        raise ValueError("fixed RHS requires positive row count")
    return np.arange(count, dtype=np.float64) + LA0_RHS_OFFSET


def class_order_sha256(class_order: Any) -> str:
    """Hash the bounded global exact-class order without numeric payload."""

    payload = json.dumps(
        [str(value) for value in class_order],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _stable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _stable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_stable(item) for item in value]
    if isinstance(value, np.ndarray):
        return [_stable(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        return _stable(value.item())
    if isinstance(value, complex):
        return [float(value.real), float(value.imag)]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def representative_identity(metadata: Mapping[str, Any]) -> dict[str, Any]:
    """Keep only bounded, canonical representative-cell identity facts."""

    descriptors = tuple(metadata.get("canonical_free_row_descriptors", ()))
    descriptor_bytes = json.dumps(
        _stable(descriptors),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "cell_key": _stable(metadata.get("cell_key")),
        "tag": int(metadata.get("tag")),
        "widths": [float(value) for value in metadata.get("widths", ())],
        "row_count": int(len(metadata.get("free_rows", ()))),
        "canonical_free_row_descriptor_sha256": hashlib.sha256(
            descriptor_bytes
        ).hexdigest(),
    }


def top_level_source_identity(
    runtime: Mapping[str, Any], expected_sha: str
) -> dict[str, Any]:
    """Copy the validated runtime identity into every future record type."""

    identity = runtime.get("source_identity")
    if not isinstance(identity, Mapping):
        return {
            "expected_sha": expected_sha,
            "source_git_sha": None,
            "tracked_status": "not_measured",
        }
    return {
        "expected_sha": str(identity.get("expected_sha", expected_sha)),
        "source_git_sha": identity.get("source_git_sha"),
        "tracked_status": identity.get("tracked_status"),
    }


def _relative(value: np.ndarray, reference: np.ndarray) -> float:
    denominator = max(float(np.linalg.norm(reference)), 1.0e-300)
    return float(np.linalg.norm(value)) / denominator


def _s0_residual(matrix: np.ndarray, rhs: np.ndarray) -> float:
    raw_lower = np.linalg.cholesky(matrix)
    indices = np.tril_indices(matrix.shape[0])
    packed = np.ascontiguousarray(raw_lower[indices], dtype=np.complex128)
    lower = np.zeros_like(raw_lower)
    lower[indices] = packed
    first = np.linalg.solve(lower, rhs)
    solution = np.linalg.solve(lower.conj().T, first)
    return _relative(matrix @ solution - rhs, rhs)


def _la1_scipy_identity(matrix: np.ndarray) -> dict[str, str]:
    import scipy
    from scipy import linalg

    blas = linalg.get_blas_funcs(("gemm",), arrays=(matrix,))[0]
    lapack = linalg.get_lapack_funcs(("trtrs",), arrays=(matrix,))[0]
    return {
        "scipy_version": str(scipy.__version__),
        "scipy_path": str(scipy.__file__),
        "solve_triangular": "scipy.linalg.solve_triangular",
        "solve_triangular_module": str(linalg.solve_triangular.__module__),
        "blas_name": str(getattr(blas, "__name__", type(blas).__name__)),
        "blas_module": str(getattr(blas, "__module__", type(blas).__module__)),
        "lapack_name": str(getattr(lapack, "__name__", type(lapack).__name__)),
        "lapack_module": str(getattr(lapack, "__module__", type(lapack).__module__)),
    }


def _la1_pack(
    matrix: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, float, bool, str]:
    raw_lower = np.linalg.cholesky(matrix)
    indices = np.tril_indices(matrix.shape[0])
    packed = np.ascontiguousarray(raw_lower[indices], dtype=np.complex128)
    lower = np.zeros_like(raw_lower)
    lower[indices] = packed
    roundtrip = _relative(lower - raw_lower, raw_lower)
    exact = bool(np.array_equal(lower, raw_lower))
    raw_factor_sha256 = hashlib.sha256(raw_lower.view(np.uint8)).hexdigest()
    del raw_lower
    return packed, lower, roundtrip, exact, raw_factor_sha256


def _la1_s0(lower: np.ndarray, rhs: np.ndarray) -> np.ndarray:
    first = np.linalg.solve(lower, rhs)
    return np.linalg.solve(lower.conj().T, first)


def _la1_s1(lower: np.ndarray, rhs: np.ndarray) -> np.ndarray:
    from scipy.linalg import solve_triangular

    first = solve_triangular(lower, rhs, lower=True, check_finite=True)
    return solve_triangular(lower.conj().T, first, lower=False, check_finite=True)


def _la1_s2(matrix: np.ndarray, rhs: np.ndarray) -> np.ndarray:
    return np.linalg.solve(matrix, rhs)


def _la1_s3(lower: np.ndarray, matrix: np.ndarray, rhs: np.ndarray) -> np.ndarray:
    from scipy.linalg import solve_triangular

    solution = _la1_s1(lower, rhs)
    residual = rhs - matrix @ solution
    first = solve_triangular(lower, residual, lower=True, check_finite=True)
    correction = solve_triangular(
        lower.conj().T, first, lower=False, check_finite=True
    )
    return solution + correction


def _la1_backward_error(
    matrix_norm: float, matrix: np.ndarray, solution: np.ndarray, rhs: np.ndarray
) -> float:
    residual = matrix @ solution - rhs
    denominator = matrix_norm * float(np.linalg.norm(solution)) + float(np.linalg.norm(rhs))
    return float(np.linalg.norm(residual)) / max(denominator, 1.0e-300)


def _la1_pairwise(solutions: Mapping[str, np.ndarray]) -> dict[str, float]:
    names = ("S0", "S1", "S2", "S3")
    return {
        f"{left}|{right}": _relative(solutions[left] - solutions[right], solutions[right])
        for index, left in enumerate(names)
        for right in names[index + 1 :]
    }


def _la1_decision(metrics: Mapping[str, Any]) -> dict[str, Any]:
    paths = metrics["paths"]
    matrix_ok = bool(
        metrics["finite"]
        and metrics["factor_finite"]
        and metrics["matrix_rhs_identity"]
        and all(path["finite"] for path in metrics["paths"].values())
        and metrics["hermitian_defect"] <= LA0_SOLVE_LIMIT
        and metrics["lambda_min"] > 0.0
        and metrics["factorization_residual"] <= LA0_SOLVE_LIMIT
    )
    if not matrix_ok:
        return {"path": "A", "classification": "LOCAL_AUXILIARY_ASSEMBLY_IDENTITY_DEFECT"}
    if (
        paths["S1"]["relative_residual"] <= LA0_SOLVE_LIMIT
        and paths["S1"]["relative_residual"] < paths["S0"]["relative_residual"]
        and metrics["repeat"]["S0_exact"]
        and metrics["repeat"]["S1_exact"]
    ):
        return {"path": "T", "classification": "PATH_T_DEDICATED_TRIANGULAR_PASS"}
    packing_defect = bool(
        metrics["packed_roundtrip_relative"] > 64.0 * np.finfo(np.float64).eps
        or not metrics["packed_roundtrip_exact"]
        or not metrics["packed_reconstruction_hash_equal"]
    )
    if paths["S1"]["relative_residual"] > LA0_SOLVE_LIMIT and packing_defect:
        return {"path": "P", "classification": "PACKED_UNPACKED_FACTOR_DEFECT"}
    if (
        paths["S1"]["relative_residual"] > LA0_SOLVE_LIMIT
        and paths["S3"]["relative_residual"] <= LA0_SOLVE_LIMIT
        and paths["S2"]["finite"]
        and paths["S2"]["normalized_backward_error"] <= LA1_BACKWARD_ERROR_LIMIT
        and metrics["repeat"]["S3_exact"]
    ):
        return {"path": "R", "classification": "PATH_R_ONE_REFINEMENT_PASS"}
    backward_max = max(path["normalized_backward_error"] for path in paths.values())
    if (
        paths["S1"]["relative_residual"] > LA0_SOLVE_LIMIT
        and paths["S2"]["relative_residual"] > LA0_SOLVE_LIMIT
        and paths["S3"]["relative_residual"] > LA0_SOLVE_LIMIT
        and backward_max <= LA1_BACKWARD_ERROR_LIMIT
        and metrics["kappa2"] >= LA1_LARGE_KAPPA_LIMIT
    ):
        return {
            "path": "C",
            "classification": "CONDITION_LIMITED_LOCAL_FACTOR_CERTIFICATION",
        }
    return {"path": "close", "classification": "CLOSED_BY_LOCAL_FACTOR_CERTIFICATION"}


def _la1_diagnostics(matrix: np.ndarray, rhs: np.ndarray) -> dict[str, Any]:
    matrix = np.ascontiguousarray(np.asarray(matrix, dtype=np.complex128))
    rhs = np.ascontiguousarray(np.asarray(rhs, dtype=np.complex128))
    packed, lower, packed_roundtrip, packed_exact, raw_factor_sha256 = _la1_pack(matrix)
    matrix_norm = float(np.linalg.norm(matrix, ord=2))
    rhs_norm = float(np.linalg.norm(rhs))
    hermitian = 0.5 * (matrix + matrix.conj().T)
    eigenvalues = np.linalg.eigvalsh(hermitian)
    lambda_min = float(eigenvalues[0])
    lambda_max = float(eigenvalues[-1])
    kappa2 = float(lambda_max / lambda_min) if lambda_min > 0.0 else float("inf")
    solutions = {
        "S0": _la1_s0(lower, rhs),
        "S1": _la1_s1(lower, rhs),
        "S2": _la1_s2(matrix, rhs),
        "S3": _la1_s3(lower, matrix, rhs),
    }
    repeated = {
        "S0": _la1_s0(lower, rhs),
        "S1": _la1_s1(lower, rhs),
        "S2": _la1_s2(matrix, rhs),
        "S3": _la1_s3(lower, matrix, rhs),
    }
    paths = {
        name: {
            "relative_residual": _relative(matrix @ value - rhs, rhs),
            "normalized_backward_error": _la1_backward_error(
                matrix_norm, matrix, value, rhs
            ),
            "finite": bool(np.all(np.isfinite(value))),
        }
        for name, value in solutions.items()
    }
    factorization_residual = _relative(
        lower @ lower.conj().T - matrix, matrix
    )
    result: dict[str, Any] = {
        "schema": LA1_SCHEMA,
        "norm_definition": "matrix spectral 2-norm; residual and RHS Euclidean 2-norm",
        "rows": int(matrix.shape[0]),
        "finite": bool(np.all(np.isfinite(matrix)) and np.all(np.isfinite(rhs))),
        "matrix_rhs_identity": bool(np.array_equal(rhs, fixed_rhs(matrix.shape[0]))),
        "matrix_norm_2": matrix_norm,
        "rhs_norm_2": rhs_norm,
        "hermitian_defect": _relative(matrix - matrix.conj().T, matrix),
        "lambda_min": lambda_min,
        "lambda_max": lambda_max,
        "kappa2": kappa2,
        "factorization_residual": factorization_residual,
        "factor_finite": bool(
            np.all(np.isfinite(packed)) and np.all(np.isfinite(lower))
        ),
        "packed_roundtrip_relative": packed_roundtrip,
        "packed_roundtrip_exact": packed_exact,
        "packed_factor_sha256": hashlib.sha256(packed.view(np.uint8)).hexdigest(),
        "reconstructed_factor_sha256": hashlib.sha256(lower.view(np.uint8)).hexdigest(),
        "raw_factor_sha256": raw_factor_sha256,
        "packed_reconstruction_hash_equal": bool(
            raw_factor_sha256 == hashlib.sha256(lower.view(np.uint8)).hexdigest()
        ),
        "paths": paths,
        "pairwise_solution_relative_differences": _la1_pairwise(solutions),
        "repeat": {
            "S0_exact": bool(np.array_equal(solutions["S0"], repeated["S0"])),
            "S1_exact": bool(np.array_equal(solutions["S1"], repeated["S1"])),
            "S2_exact": bool(np.array_equal(solutions["S2"], repeated["S2"])),
            "S3_exact": bool(np.array_equal(solutions["S3"], repeated["S3"])),
            "S0_relative": _relative(repeated["S0"] - solutions["S0"], solutions["S0"]),
            "S1_relative": _relative(repeated["S1"] - solutions["S1"], solutions["S1"]),
            "S2_relative": _relative(repeated["S2"] - solutions["S2"], solutions["S2"]),
            "S3_relative": _relative(repeated["S3"] - solutions["S3"], solutions["S3"]),
        },
        "temporary_bytes": {
            "provenance": "derived_explicit_numpy_array_nbytes; library workspace unmeasured",
            "packed_factor_bytes": int(packed.nbytes),
            "reconstructed_factor_bytes": int(lower.nbytes),
            "solution_vectors_bytes": int(4 * solutions["S0"].nbytes),
            "one_refinement_work_vectors_bytes": int(2 * rhs.nbytes),
            "derived_array_bytes": int(
                packed.nbytes + lower.nbytes + 6 * rhs.nbytes
            ),
        },
        "scipy": _la1_scipy_identity(matrix),
    }
    result["decision"] = _la1_decision(result)
    return result


def _capture_reproduces_v1(capture: Mapping[str, Any]) -> bool:
    """Accept rc=0 only after the original class identity and residual close."""

    matrix = np.asarray(capture.get("matrix"), dtype=np.complex128)
    if (
        matrix.ndim != 2
        or matrix.shape[0] != matrix.shape[1]
        or matrix.shape[0] < 1
        or matrix.shape[0] > 882
        or not np.all(np.isfinite(matrix))
    ):
        return False
    if "fixed local factor solve residual" not in str(capture.get("registration_error", "")):
        return False
    digest = str(capture.get("class_digest", ""))
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        return False
    cell = capture.get("representative_cell")
    if (
        not isinstance(cell, Mapping)
        or "cell_key" not in cell
        or not isinstance(cell.get("tag"), int)
        or isinstance(cell.get("tag"), bool)
        or cell.get("row_count") != matrix.shape[0]
        or not isinstance(cell.get("widths"), list)
        or len(cell["widths"]) != 3
        or not all(
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and np.isfinite(value)
            for value in cell["widths"]
        )
        or len(str(cell.get("canonical_free_row_descriptor_sha256", ""))) != 64
        or any(
            char not in "0123456789abcdef"
            for char in str(cell.get("canonical_free_row_descriptor_sha256", ""))
        )
    ):
        return False
    trace = capture.get("registration_trace")
    slot = capture.get("slot")
    if (
        capture.get("representative_rank") != 0
        or not isinstance(slot, int)
        or slot < 0
        or not isinstance(trace, Mapping)
        or trace.get("first_failure") is not True
        or trace.get("order_rule") != LA0_FAILURE_ORDER_RULE
    ):
        return False
    class_order = trace.get("class_order")
    if (
        not isinstance(class_order, (list, tuple))
        or not class_order
        or any(
            not isinstance(value, str)
            or len(value) != 64
            or any(char not in "0123456789abcdef" for char in value)
            for value in class_order
        )
        or tuple(class_order) != tuple(sorted(set(class_order)))
        or slot >= len(class_order)
        or class_order[slot] != digest
        or trace.get("failed_slot") != slot
        or list(trace.get("successful_slots", ())) != list(range(slot))
        or trace.get("class_order_sha256") != class_order_sha256(class_order)
    ):
        return False
    residual = _s0_residual(matrix, fixed_rhs(matrix.shape[0]))
    agreement = abs(residual - LA0_OLD_N2_V1_RESIDUAL) / LA0_OLD_N2_V1_RESIDUAL
    return bool(np.isfinite(residual) and residual > LA0_SOLVE_LIMIT and agreement <= 1.0e-14)


def _array_descriptor(path: Path, array: np.ndarray) -> dict[str, Any]:
    values = np.ascontiguousarray(np.asarray(array, dtype=np.complex128))
    np.save(path, values, allow_pickle=False)
    return {
        "path": str(path),
        "sha256": sha256_path(path),
        "bytes": int(path.stat().st_size),
        "shape": list(values.shape),
        "dtype": "complex128",
        "finite": bool(np.all(np.isfinite(values))),
    }


def _record(
    args: argparse.Namespace,
    runtime: Mapping[str, Any],
    capture: Mapping[str, Any] | None,
    failure: BaseException | None,
    comm: Any,
) -> dict[str, Any]:
    reproduction_verified = bool(
        capture is not None and capture.get("reproduction_verified") is True
    )
    record: dict[str, Any] = {
        "schema": LA0_SCHEMA,
        "stage": LA0_STAGE,
        "case": args.case,
        "degree": LA0_DEGREE,
        "mesh_target_nm": LA0_MESH_TARGET_NM,
        "mpi_size": int(comm.size),
        "attempt": {
            "kind": "la0_la1_single_formal_attempt",
            "count": 1,
            "single_attempt": True,
        },
        "classification": (
            "LA0_REPRODUCTION_PASS"
            if reproduction_verified
            else "LA0_FAILED_TO_REPRODUCE_V1_CLASS"
        ),
        "old_n2_v1_classification": "CONTROLLED_NEGATIVE_LOCAL_FACTOR_SOLVE_GATE",
        "la0_reproduction": "PASS" if reproduction_verified else "FAIL",
        "source_identity": top_level_source_identity(
            runtime, args.expected_sha
        ),
        "runtime": _stable(runtime),
        "fixed_diagnostic": {
            "rhs_definition": "arange(n_rows)+(0.125+0.25j)",
            "rhs_offset": [0.125, 0.25],
            "solve_gate": LA0_SOLVE_LIMIT,
            "source_independent": True,
            "physical_rhs_accepted": False,
            "residual_input_accepted": False,
        },
        "markers": {
            "planned": [
                "preflight",
                "mesh_space_mpc",
                "subdomain_inventory",
                "local_factor_build",
                "linear_algebra_diagnostic",
                "failure",
            ],
            "ledger": [],
        },
        "no_production_change": True,
        "no_modes_or_coarse": True,
        "no_physical_action": True,
        "no_numeric_allgather": True,
    }
    if failure is not None:
        record["failure"] = {
            "exception_type": type(failure).__name__,
            "message": str(failure),
        }
    if capture is not None:
        matrix = np.asarray(capture["matrix"], dtype=np.complex128)
        rhs = fixed_rhs(matrix.shape[0])
        s0_residual = _s0_residual(matrix, rhs)
        record["la1"] = _la1_diagnostics(matrix, rhs)
        record["failed_class"] = {
            "digest": str(capture["class_digest"]),
            "slot": int(capture["slot"]),
            "representative_rank": capture["representative_rank"],
            "representative_cell": _stable(capture["representative_cell"]),
            "registration_error": str(capture.get("registration_error", "")),
            "registration_trace": _stable(capture.get("registration_trace", {})),
            "rows": int(matrix.shape[0]),
            "matrix_content_sha256": hashlib.sha256(
                np.ascontiguousarray(matrix).view(np.uint8)
            ).hexdigest(),
            "rhs_content_sha256": hashlib.sha256(
                np.ascontiguousarray(rhs).view(np.uint8)
            ).hexdigest(),
            "original_s0_relative_residual": float(s0_residual),
            "frozen_v1_s0_relative_agreement": abs(
                s0_residual - LA0_OLD_N2_V1_RESIDUAL
            )
            / LA0_OLD_N2_V1_RESIDUAL,
            "reproduction_verified": bool(
                capture.get("reproduction_verified", False)
            ),
            "finite": bool(np.all(np.isfinite(matrix)) and np.all(np.isfinite(rhs))),
        }
        record["artifacts"] = {
            "matrix": _array_descriptor(args.raw_dir / "failed_B.npy", matrix),
            "rhs": _array_descriptor(args.raw_dir / "failed_rhs.npy", rhs),
        }
    record["markers"]["ledger"] = _marker_ledger(args.marker_dir)
    record["old_n2_v1_binding"] = {
        "compact_record_relative_path": LA0_OLD_N2_V1_COMPACT_PATH,
        "compact_record_sha256": LA0_OLD_N2_V1_COMPACT_SHA256,
        "source_git_sha": LA0_OLD_N2_V1_SOURCE_SHA,
        "failure_stage": "local_factor_build",
        "fixed_rhs_solve_residual": LA0_OLD_N2_V1_RESIDUAL,
        "solve_gate": LA0_SOLVE_LIMIT,
        "first_failure_semantics": (
            "first_registration_failure_in_global_sorted_class_slots"
        ),
    }
    return record


def _marker_ledger(marker_dir: Path) -> list[dict[str, Any]]:
    names = (
        "preflight",
        "mesh_space_mpc",
        "subdomain_inventory",
        "local_factor_build",
        "linear_algebra_diagnostic",
        "failure",
    )
    return [
        json.loads((marker_dir / f"{name}.json").read_text(encoding="utf-8"))
        for name in names
        if (marker_dir / f"{name}.json").is_file()
    ]


def _write_record(path: Path, record: Mapping[str, Any]) -> None:
    if path.exists():
        raise FileExistsError(f"LA0 record already exists: {path}")
    path.write_text(
        json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _parse_worker(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="LA0 failed-class extraction")
    parser.add_argument("--stage", choices=("la0",), required=True)
    parser.add_argument("--case", choices=(LA0_CASE,), required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--marker-dir", type=Path, required=True)
    parser.add_argument("--expected-source-sha", dest="expected_sha", required=True)
    parser.add_argument("--expected-mpi-size", type=int, required=True)
    args = parser.parse_args(argv)
    if args.expected_mpi_size != 1:
        parser.error("LA0 is frozen to MPI1")
    return args


def _run_worker(args: argparse.Namespace) -> int:
    from mpi4py import MPI
    from benchmarks import run_task038_full3d_n2 as n2
    from src.solvers.fullspace_local_spectral import ExactClassOwnerPlan
    from src.solvers.fullspace_local_spectral_dolfinx import (
        build_real_local_spectral_patches,
    )

    comm = MPI.COMM_WORLD
    if comm.size != 1:
        raise RuntimeError("LA0 requires MPI1")
    root = Path.cwd().resolve()
    args.raw_dir = args.raw_dir.resolve()
    args.record = args.record.resolve()
    args.marker_dir = args.marker_dir.resolve()
    n2._prepare_paths(args.raw_dir, args.record, args.marker_dir, comm)
    runtime: dict[str, Any] = {}
    state: dict[str, Any] = {
        "current": None,
        "failed": None,
        "successful_slots": [],
    }
    original_register = ExactClassOwnerPlan.register_class_representative
    try:
        n2._write_marker(args.marker_dir, "preflight", args.expected_sha, comm, stage="LA0")
        runtime = n2._runtime_preflight(root, args.expected_sha, 1, comm.size)
        n2._write_marker(args.marker_dir, "mesh_space_mpc", args.expected_sha, comm, degree=LA0_DEGREE, mesh_target_nm=LA0_MESH_TARGET_NM)
        case = n2._build_case(root, args, comm)
        n2._write_marker(args.marker_dir, "subdomain_inventory", args.expected_sha, comm, diagnostic_only=True)

        def hook(**payload: Any) -> None:
            matrix = payload.get("matrix")
            if matrix is None:
                return
            state["current"] = {
                "class_digest": str(payload["class_digest"]),
                "slot": int(payload["slot"]),
                "representative_rank": payload.get("representative_rank"),
                "representative_cell": representative_identity(payload["metadata"]),
                "matrix": np.asarray(matrix, dtype=np.complex128),
            }

        def wrapped_register(self: Any, class_digest: str, matrix: Any, *, slot: int) -> Any:
            try:
                result = original_register(self, class_digest, matrix, slot=slot)
            except Exception as exc:
                current = state.get("current")
                if current is not None and current["class_digest"] == str(class_digest):
                    state["failed"] = dict(current)
                    state["failed"]["registration_error"] = str(exc)
                    state["failed"]["registration_trace"] = {
                        "class_order": tuple(self.class_digests),
                        "class_order_sha256": class_order_sha256(self.class_digests),
                        "successful_slots": tuple(state["successful_slots"]),
                        "failed_slot": int(slot),
                        "first_failure": True,
                        "order_rule": LA0_FAILURE_ORDER_RULE,
                    }
                raise
            state["successful_slots"].append(int(slot))
            return result

        ExactClassOwnerPlan.register_class_representative = wrapped_register
        n2._write_marker(args.marker_dir, "local_factor_build", args.expected_sha, comm, diagnostic_hook="fail_before_register")
        try:
            build_real_local_spectral_patches(
                case["space"],
                case["mesh_data"],
                case["floquet_data"],
                case["cfg"],
                reuse_class_templates=True,
                diagnostic_hook=hook,
            )
        except Exception as exc:
            failure = exc
        else:
            failure = RuntimeError("LA0 did not reproduce a failed exact class")
        capture = state.get("failed")
        if capture is not None:
            capture["reproduction_verified"] = _capture_reproduces_v1(capture)
        if capture is None:
            failure = RuntimeError(
                f"LA0 failed to capture the class before registration: {failure}"
            )
        n2._write_marker(
            args.marker_dir,
            "linear_algebra_diagnostic",
            args.expected_sha,
            comm,
            paths=("S0", "S1", "S2", "S3"),
            exact_refinement_steps=1,
            captured_failed_class=capture is not None,
        )
        record = _record(args, runtime, capture, failure, comm)
        n2._write_marker(
            args.marker_dir,
            "failure",
            args.expected_sha,
            comm,
            exception_type=type(failure).__name__,
            message=str(failure),
            captured_failed_class=capture is not None,
        )
        record["markers"]["ledger"] = _marker_ledger(args.marker_dir)
        _write_record(args.record, record)
        return 0 if capture is not None and capture["reproduction_verified"] else 1
    except Exception as exc:
        if not args.record.exists():
            try:
                n2._write_marker(args.marker_dir, "failure", args.expected_sha, comm, exception_type=type(exc).__name__, message=str(exc))
            finally:
                _write_record(args.record, _record(args, runtime, state.get("failed"), exc, comm))
        return 1
    finally:
        ExactClassOwnerPlan.register_class_representative = original_register


def main(argv: list[str] | None = None) -> int:
    selected = list(sys.argv[1:] if argv is None else argv)
    if "--watchdog" in selected:
        from benchmarks import run_task038_full3d_n2 as n2

        return n2._watchdog_main([item for item in selected if item != "--watchdog"])
    return _run_worker(_parse_worker(selected))


if __name__ == "__main__":
    raise SystemExit(main())
