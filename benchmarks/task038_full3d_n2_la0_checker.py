"""Independent, read-only checker for the LA0 failed-class artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping

import numpy as np


LA0_SCHEMA = "task038.full3d.local-spectral.la0-record.v1"
LA0_CASE = "p6-h10-mpi1"
LA0_DEGREE = 6
LA0_MESH_TARGET_NM = 10.0
LA0_SOLVE_LIMIT = 1.0e-11
LA0_MAX_ROWS = 882
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
LA0_MARKERS = (
    "preflight",
    "mesh_space_mpc",
    "subdomain_inventory",
    "local_factor_build",
    "linear_algebra_diagnostic",
    "failure",
)


def _error(errors: list[str], message: str) -> None:
    errors.append(message)


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _relative(value: np.ndarray, reference: np.ndarray) -> float:
    return float(np.linalg.norm(value)) / max(
        float(np.linalg.norm(reference)), 1.0e-300
    )


def _fixed_rhs(rows: int) -> np.ndarray:
    return np.arange(int(rows), dtype=np.float64) + (0.125 + 0.25j)


def _class_order_sha256(class_order: Any) -> str:
    payload = json.dumps(
        [str(value) for value in class_order],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _is_hex(value: Any, length: int) -> bool:
    return (
        isinstance(value, str)
        and len(value) == length
        and all(char in "0123456789abcdef" for char in value)
    )


def _check_old_v1_binding(record: Mapping[str, Any], errors: list[str]) -> None:
    binding = record.get("old_n2_v1_binding")
    if not isinstance(binding, Mapping):
        _error(errors, "old N2 v1 binding is missing")
        return
    expected = {
        "compact_record_relative_path": LA0_OLD_N2_V1_COMPACT_PATH,
        "compact_record_sha256": LA0_OLD_N2_V1_COMPACT_SHA256,
        "source_git_sha": LA0_OLD_N2_V1_SOURCE_SHA,
        "failure_stage": "local_factor_build",
        "fixed_rhs_solve_residual": LA0_OLD_N2_V1_RESIDUAL,
        "solve_gate": LA0_SOLVE_LIMIT,
        "first_failure_semantics": "first_registration_failure_in_global_sorted_class_slots",
    }
    for key, value in expected.items():
        if binding.get(key) != value:
            _error(errors, f"old N2 v1 binding field {key} is not frozen")
    old_path = Path(__file__).resolve().parents[1] / LA0_OLD_N2_V1_COMPACT_PATH
    if not old_path.is_file():
        _error(errors, "frozen old N2 v1 compact record is unavailable")
    elif _sha256(old_path) != LA0_OLD_N2_V1_COMPACT_SHA256:
        _error(errors, "frozen old N2 v1 compact record hash changed")


def _check_failed_class_identity(
    failed: Mapping[str, Any], rows: int, errors: list[str]
) -> None:
    digest = failed.get("digest")
    if not _is_hex(digest, 64):
        _error(errors, "captured failed class digest is not a lowercase SHA-256")
    slot = failed.get("slot")
    if not isinstance(slot, int) or isinstance(slot, bool) or slot < 0:
        _error(errors, "captured failed class slot is invalid")
        return
    if failed.get("representative_rank") != 0:
        _error(errors, "captured MPI1 representative rank is not zero")
    if failed.get("rows") != rows:
        _error(errors, "captured failed class rows do not close the matrix")
    cell = failed.get("representative_cell")
    if not isinstance(cell, Mapping):
        _error(errors, "representative cell canonical identity is missing")
    else:
        if "cell_key" not in cell:
            _error(errors, "representative cell key is missing")
        if not isinstance(cell.get("tag"), int) or isinstance(cell.get("tag"), bool):
            _error(errors, "representative cell tag is missing")
        widths = cell.get("widths")
        if (
            not isinstance(widths, list)
            or len(widths) != 3
            or not all(isinstance(value, (int, float)) and not isinstance(value, bool) and np.isfinite(value) for value in widths)
        ):
            _error(errors, "representative cell widths are invalid")
        if cell.get("row_count") != rows:
            _error(errors, "representative cell row count does not close the matrix")
        if not _is_hex(cell.get("canonical_free_row_descriptor_sha256"), 64):
            _error(errors, "representative cell canonical row identity is missing")
    if not isinstance(failed.get("registration_error"), str) or "fixed local factor solve residual" not in failed.get("registration_error", ""):
        _error(errors, "captured registration failure message is missing")
    if failed.get("reproduction_verified") is not True:
        _error(errors, "worker did not verify the captured old v1 reproduction")
    trace = failed.get("registration_trace")
    if not isinstance(trace, Mapping):
        _error(errors, "failed-class registration trace is missing")
        return
    class_order = trace.get("class_order")
    if (
        not isinstance(class_order, list)
        or not class_order
        or len(class_order) > 32
        or any(not _is_hex(value, 64) for value in class_order)
        or tuple(class_order) != tuple(sorted(set(class_order)))
    ):
        _error(errors, "global exact-class order is invalid")
        return
    if trace.get("class_order_sha256") != _class_order_sha256(class_order):
        _error(errors, "global exact-class order hash does not close")
    if trace.get("order_rule") != LA0_FAILURE_ORDER_RULE:
        _error(errors, "exact-class failure order rule is not frozen")
    if trace.get("first_failure") is not True:
        _error(errors, "capture is not marked as the first registration failure")
    if trace.get("failed_slot") != slot or slot >= len(class_order) or class_order[slot] != digest:
        _error(errors, "captured digest/slot is not the first failed class in order")
    if trace.get("successful_slots") != list(range(slot)):
        _error(errors, "registration trace does not close the successful class prefix")


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


def _la1_decision(metrics: Mapping[str, Any]) -> dict[str, str]:
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


def _la1_recompute(matrix: np.ndarray, rhs: np.ndarray) -> dict[str, Any]:
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
    result: dict[str, Any] = {
        "schema": LA1_SCHEMA,
        "norm_definition": "matrix spectral 2-norm; residual and RHS Euclidean 2-norm",
        "rows": int(matrix.shape[0]),
        "finite": bool(np.all(np.isfinite(matrix)) and np.all(np.isfinite(rhs))),
        "matrix_rhs_identity": bool(np.array_equal(rhs, _fixed_rhs(matrix.shape[0]))),
        "matrix_norm_2": matrix_norm,
        "rhs_norm_2": rhs_norm,
        "hermitian_defect": _relative(matrix - matrix.conj().T, matrix),
        "lambda_min": lambda_min,
        "lambda_max": lambda_max,
        "kappa2": kappa2,
        "factorization_residual": _relative(lower @ lower.conj().T - matrix, matrix),
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
            "derived_array_bytes": int(packed.nbytes + lower.nbytes + 6 * rhs.nbytes),
        },
        "scipy": _la1_scipy_identity(matrix),
    }
    result["decision"] = _la1_decision(result)
    return result


def _check_la1_recorded(
    recorded: Mapping[str, Any], actual: Mapping[str, Any], errors: list[str]
) -> None:
    if recorded.get("schema") != LA1_SCHEMA:
        _error(errors, "LA1 diagnostic schema is missing")
        return
    numeric_keys = (
        "rows", "matrix_norm_2", "rhs_norm_2", "hermitian_defect",
        "lambda_min", "lambda_max", "kappa2", "factorization_residual",
        "packed_roundtrip_relative",
    )
    for key in numeric_keys:
        left, right = recorded.get(key), actual.get(key)
        if isinstance(right, (int, float)) and not isinstance(right, bool):
            if not isinstance(left, (int, float)) or isinstance(left, bool) or not np.isclose(left, right, rtol=1e-14, atol=1e-300):
                _error(errors, f"LA1 recorded scalar {key} does not close independent recomputation")
        elif left != right:
            _error(errors, f"LA1 recorded field {key} does not close")
    if recorded.get("finite") is not actual.get("finite") or recorded.get("matrix_rhs_identity") is not actual.get("matrix_rhs_identity"):
        _error(errors, "LA1 finite or fixed RHS identity does not close")
    if recorded.get("factor_finite") is not actual.get("factor_finite"):
        _error(errors, "LA1 factor finite status does not close")
    if recorded.get("packed_roundtrip_exact") is not actual.get("packed_roundtrip_exact"):
        _error(errors, "LA1 packed roundtrip exact flag does not close")
    if recorded.get("norm_definition") != actual.get("norm_definition"):
        _error(errors, "LA1 norm definition does not close")
    for key in (
        "packed_factor_sha256",
        "reconstructed_factor_sha256",
        "raw_factor_sha256",
    ):
        if recorded.get(key) != actual.get(key):
            _error(errors, f"LA1 {key} does not close")
    if recorded.get("packed_reconstruction_hash_equal") is not actual.get(
        "packed_reconstruction_hash_equal"
    ):
        _error(errors, "LA1 packed roundtrip/hash identity does not close")
    for name, expected in actual["paths"].items():
        observed = recorded.get("paths", {}).get(name)
        if not isinstance(observed, Mapping):
            _error(errors, f"LA1 path {name} is missing")
            continue
        for key in ("relative_residual", "normalized_backward_error"):
            if not np.isclose(observed.get(key), expected[key], rtol=1e-14, atol=1e-300):
                _error(errors, f"LA1 {name} {key} does not close")
        if observed.get("finite") is not expected["finite"]:
            _error(errors, f"LA1 {name} finite flag does not close")
    observed_pairs = recorded.get("pairwise_solution_relative_differences")
    expected_pairs = actual.get("pairwise_solution_relative_differences", {})
    if not isinstance(observed_pairs, Mapping) or set(observed_pairs) != set(expected_pairs):
        _error(errors, "LA1 solution pairwise differences do not close")
    else:
        for key, value in expected_pairs.items():
            if not np.isclose(observed_pairs[key], value, rtol=1e-14, atol=1e-300):
                _error(errors, f"LA1 solution pair {key} does not close")
    observed_repeat = recorded.get("repeat")
    expected_repeat = actual.get("repeat", {})
    if not isinstance(observed_repeat, Mapping):
        _error(errors, "LA1 repeat determinism facts are missing")
    else:
        for key, value in expected_repeat.items():
            if isinstance(value, bool):
                if observed_repeat.get(key) is not value:
                    _error(errors, f"LA1 repeat flag {key} does not close")
            elif not np.isclose(observed_repeat.get(key), value, rtol=1e-14, atol=1e-300):
                _error(errors, f"LA1 repeat scalar {key} does not close")
    if recorded.get("temporary_bytes") != actual.get("temporary_bytes"):
        _error(errors, "LA1 temporary byte accounting does not close")
    if recorded.get("scipy") != actual.get("scipy"):
        _error(errors, "LA1 SciPy/BLAS/LAPACK identity does not close")
    if recorded.get("decision") != actual.get("decision"):
        _error(errors, "LA1 decision tree result does not close independent recomputation")


def _check_la1_watchdog(
    record_path: Path, record: Mapping[str, Any], errors: list[str]
) -> dict[str, Any] | None:
    contract = record.get("resource_contract")
    if not isinstance(contract, Mapping) or contract.get("status") != "measured":
        _error(errors, "LA0/LA1 resource contract is missing or not measured")
        return None
    raw_path = Path(str(contract.get("raw_path", "")))
    compact_path = Path(str(contract.get("compact_path", "")))
    if not raw_path.is_file() or not compact_path.is_file():
        _error(errors, "LA0/LA1 watchdog raw/compact artifact is missing")
        return None
    if contract.get("raw_sha256") != _sha256(raw_path):
        _error(errors, "LA0/LA1 watchdog raw hash does not close")
    if contract.get("compact_sha256") != _sha256(compact_path):
        _error(errors, "LA0/LA1 watchdog compact hash does not close")
    raw = _load(raw_path)
    compact = _load(compact_path)
    if raw.get("schema") != "task038.full3d.local-spectral.n2-watchdog-raw.v1":
        _error(errors, "LA0/LA1 watchdog raw schema mismatch")
    if compact.get("schema") != "task038.full3d.local-spectral.n2-watchdog-compact.v1":
        _error(errors, "LA0/LA1 watchdog compact schema mismatch")
    samples = raw.get("samples")
    if not isinstance(samples, list) or not samples:
        _error(errors, "LA0/LA1 watchdog has no samples")
        return compact
    valid = []
    peak = 0
    for index, sample in enumerate(samples):
        authority = sample.get("authority") if isinstance(sample, Mapping) else None
        tree = authority.get("process_tree") if isinstance(authority, Mapping) else None
        if not isinstance(authority, Mapping) or sample.get("authority_error") or not isinstance(tree, Mapping):
            _error(errors, f"LA0/LA1 watchdog sample {index} lacks readable authority")
            continue
        if int(tree.get("swap_bytes", -1)) != 0:
            _error(errors, f"LA0/LA1 watchdog sample {index} has nonzero swap")
        peak = max(peak, int(authority.get("memory_authority_bytes", -1)))
        valid.append(sample)
    if len(valid) != len(samples):
        _error(errors, "LA0/LA1 watchdog authority samples are incomplete")
    if peak >= 2_000_000_000:
        _error(errors, f"LA0/LA1 process-tree peak {peak} is not below 2000000000")
    if raw.get("worker_returncode") != 0 or raw.get("stop_reason") != "natural_exit":
        _error(errors, "LA0/LA1 watchdog did not record rc=0 natural completion")
    termination = raw.get("termination")
    if not isinstance(termination, Mapping) or termination.get("method") != "already_exited" or termination.get("process_group_exited") is not True:
        _error(errors, "LA0/LA1 watchdog termination/no-orphan proof is missing")
    if compact.get("raw_sha256") != _sha256(raw_path):
        _error(errors, "LA0/LA1 compact does not bind raw hash")
    if compact.get("process_tree_peak_memory_authority_bytes") != peak:
        _error(errors, "LA0/LA1 compact peak does not close raw samples")
    if compact.get("process_tree_swap_gate") is not True or compact.get("natural_exit") is not True or compact.get("no_orphan_claim") is not True:
        _error(errors, "LA0/LA1 compact resource/termination Gate is not true")
    command = " ".join(str(item) for item in compact.get("command", []))
    identity = record.get("source_identity", {})
    expected = identity.get("expected_sha") if isinstance(identity, Mapping) else None
    for token in (str(record_path.resolve()), str(record.get("case")), str(expected), "--stage la0", "--expected-mpi-size"):
        if token not in command:
            _error(errors, f"LA0/LA1 watchdog command is not bound to {token!r}")
    return {"peak": peak, "sample_count": len(samples), "swap": 0}


def _source_identity(
    record: Mapping[str, Any], expected_sha: str, errors: list[str]
) -> None:
    identity = record.get("source_identity")
    runtime = record.get("runtime")
    runtime_identity = runtime.get("source_identity") if isinstance(runtime, Mapping) else None
    for label, value in (("source identity", identity), ("runtime source identity", runtime_identity)):
        if not isinstance(value, Mapping):
            _error(errors, f"{label} is missing")
            continue
        if value.get("expected_sha") != expected_sha:
            _error(errors, f"{label} expected_sha is not bound to formal SHA")
        if value.get("source_git_sha") != expected_sha:
            _error(errors, f"{label} source_git_sha is not bound to formal SHA")
        if value.get("tracked_status") != "":
            _error(errors, f"{label} tracked_status is not clean")
    if isinstance(identity, Mapping) and isinstance(runtime_identity, Mapping):
        if dict(identity) != dict(runtime_identity):
            _error(errors, "top-level and runtime source identity differ")


def _read_array(
    descriptor: Mapping[str, Any],
    record_path: Path,
    errors: list[str],
) -> np.ndarray | None:
    path_value = descriptor.get("path")
    if not isinstance(path_value, str):
        _error(errors, "array path is missing")
        return None
    path = Path(path_value)
    if not path.is_absolute():
        path = record_path.parent / path
    try:
        if not path.is_file():
            raise FileNotFoundError(path)
        if descriptor.get("sha256") != _sha256(path):
            raise ValueError(f"array hash mismatch: {path}")
        if descriptor.get("bytes") != path.stat().st_size:
            raise ValueError(f"array byte count mismatch: {path}")
        array = np.load(path, allow_pickle=False)
    except (OSError, ValueError, EOFError) as exc:
        _error(errors, str(exc))
        return None
    if descriptor.get("dtype") != "complex128" or array.dtype != np.dtype(np.complex128):
        _error(errors, f"array dtype is not complex128: {path}")
    if descriptor.get("shape") != list(array.shape):
        _error(errors, f"array shape descriptor mismatch: {path}")
    if not np.all(np.isfinite(array)):
        _error(errors, f"array is not finite: {path}")
    return np.ascontiguousarray(array, dtype=np.complex128)


def _check_markers(record: Mapping[str, Any], errors: list[str]) -> None:
    markers = record.get("markers")
    ledger = markers.get("ledger") if isinstance(markers, Mapping) else None
    if not isinstance(ledger, list):
        _error(errors, "marker ledger is missing")
        return
    names = tuple(
        item.get("marker")
        for item in ledger
        if isinstance(item, Mapping)
    )
    if names != LA0_MARKERS:
        _error(errors, f"marker sequence {names!r} does not reproduce LA0")
    previous = -1
    for item in ledger:
        value = item.get("monotonic_ns") if isinstance(item, Mapping) else None
        if not isinstance(value, int) or value <= previous:
            _error(errors, "marker monotonic timestamps are not strictly increasing")
        previous = int(value) if isinstance(value, int) else previous


def check_record(
    record_path: Path,
    *,
    expected_sha: str,
    raw_dir: Path | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    try:
        record = _load(record_path)
    except (OSError, json.JSONDecodeError) as exc:
        return {"passed": False, "errors": [str(exc)], "record": str(record_path)}
    if not isinstance(record, Mapping):
        return {"passed": False, "errors": ["record must be an object"], "record": str(record_path)}
    if record.get("schema") != LA0_SCHEMA:
        _error(errors, "LA0 schema is missing")
    if record.get("stage") != "la0_single_failed_class":
        _error(errors, "LA0 stage is missing")
    if record.get("case") != LA0_CASE or record.get("mpi_size") != 1:
        _error(errors, "LA0 case or MPI size is not frozen")
    if record.get("degree") != LA0_DEGREE or record.get("mesh_target_nm") != LA0_MESH_TARGET_NM:
        _error(errors, "LA0 p6/h10 identity is not frozen")
    if record.get("old_n2_v1_classification") != "CONTROLLED_NEGATIVE_LOCAL_FACTOR_SOLVE_GATE":
        _error(errors, "old N2 v1 controlled-negative classification is missing")
    if record.get("classification") != "LA0_REPRODUCTION_PASS" or record.get("la0_reproduction") != "PASS":
        _error(errors, "LA0 reproduction did not complete successfully")
    _source_identity(record, expected_sha, errors)
    _check_old_v1_binding(record, errors)
    attempt = record.get("attempt")
    if not isinstance(attempt, Mapping) or attempt.get("kind") != "la0_la1_single_formal_attempt" or attempt.get("count") != 1 or attempt.get("single_attempt") is not True:
        _error(errors, "LA0/LA1 record is not bound to one formal attempt")
    _check_la1_watchdog(record_path, record, errors)
    _check_markers(record, errors)
    for key in ("no_production_change", "no_modes_or_coarse", "no_physical_action", "no_numeric_allgather"):
        if record.get(key) is not True:
            _error(errors, f"{key} audit is not true")
    diagnostic = record.get("fixed_diagnostic")
    if not isinstance(diagnostic, Mapping):
        _error(errors, "fixed diagnostic contract is missing")
    else:
        if diagnostic.get("solve_gate") != LA0_SOLVE_LIMIT:
            _error(errors, "fixed solve Gate changed")
        if diagnostic.get("source_independent") is not True:
            _error(errors, "diagnostic is not source-independent")
        if diagnostic.get("physical_rhs_accepted") is not False:
            _error(errors, "physical RHS was accepted")
        if diagnostic.get("residual_input_accepted") is not False:
            _error(errors, "residual input was accepted")
    failed = record.get("failed_class")
    artifacts = record.get("artifacts")
    if not isinstance(failed, Mapping) or not isinstance(artifacts, Mapping):
        _error(errors, "failed-class facts or artifacts are missing")
        return {"passed": False, "errors": errors, "record": str(record_path)}
    matrix_descriptor = artifacts.get("matrix")
    rhs_descriptor = artifacts.get("rhs")
    if not isinstance(matrix_descriptor, Mapping) or not isinstance(rhs_descriptor, Mapping):
        _error(errors, "matrix/RHS descriptors are missing")
        return {"passed": False, "errors": errors, "record": str(record_path)}
    matrix = _read_array(matrix_descriptor, record_path, errors)
    rhs = _read_array(rhs_descriptor, record_path, errors)
    if matrix is None or rhs is None:
        return {"passed": False, "errors": errors, "record": str(record_path)}
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1] or matrix.shape[0] > LA0_MAX_ROWS:
        _error(errors, "failed class matrix shape or row cap is invalid")
        return {"passed": False, "errors": errors, "record": str(record_path)}
    if rhs.shape != (matrix.shape[0],):
        _error(errors, "fixed RHS shape does not match matrix")
    expected_rhs = _fixed_rhs(matrix.shape[0])
    if not np.array_equal(rhs, expected_rhs):
        _error(errors, "fixed RHS does not match frozen arange definition")
    matrix_content_sha = hashlib.sha256(matrix.view(np.uint8)).hexdigest()
    rhs_content_sha = hashlib.sha256(rhs.view(np.uint8)).hexdigest()
    if failed.get("matrix_content_sha256") != matrix_content_sha:
        _error(errors, "matrix content hash does not close")
    if failed.get("rhs_content_sha256") != rhs_content_sha:
        _error(errors, "RHS content hash does not close")
    if failed.get("rows") != matrix.shape[0]:
        _error(errors, "failed class row count does not close matrix")
    _check_failed_class_identity(failed, int(matrix.shape[0]), errors)
    try:
        actual_la1 = _la1_recompute(matrix, rhs)
    except (np.linalg.LinAlgError, ValueError) as exc:
        _error(errors, f"independent LA1 recomputation failed: {exc}")
        return {"passed": False, "errors": errors, "record": str(record_path)}
    actual_residual = float(actual_la1["paths"]["S0"]["relative_residual"])
    recorded_la1 = record.get("la1")
    if not isinstance(recorded_la1, Mapping):
        _error(errors, "LA1 S0/S1/S2/S3 diagnostic is missing")
    else:
        _check_la1_recorded(recorded_la1, actual_la1, errors)
    recorded_residual = failed.get("original_s0_relative_residual")
    if not isinstance(recorded_residual, (int, float)) or isinstance(recorded_residual, bool):
        _error(errors, "recorded original residual is missing")
        recorded_residual = float("nan")
    agreement = abs(actual_residual - float(recorded_residual)) / max(
        abs(float(recorded_residual)), 1.0e-300
    )
    if not np.isfinite(agreement) or agreement > 1.0e-14:
        _error(errors, f"S0 residual reproduction relative agreement {agreement} exceeds 1e-14")
    frozen_agreement = abs(actual_residual - LA0_OLD_N2_V1_RESIDUAL) / max(
        abs(LA0_OLD_N2_V1_RESIDUAL), 1.0e-300
    )
    if not np.isfinite(frozen_agreement) or frozen_agreement > 1.0e-14:
        _error(errors, f"S0 residual vs frozen old N2 v1 value has relative agreement {frozen_agreement}, limit 1e-14")
    if not np.isfinite(actual_residual) or actual_residual <= LA0_SOLVE_LIMIT:
        _error(errors, f"reproduced S0 residual {actual_residual} does not reproduce the frozen failure")
    return {
        "passed": not errors,
        "errors": errors,
        "record": str(record_path),
        "facts": {
            "class_digest": failed.get("digest"),
            "rows": int(matrix.shape[0]),
            "s0_relative_residual": float(actual_residual),
            "s0_reproduction_relative_agreement": float(agreement),
            "s0_frozen_v1_relative_agreement": float(frozen_agreement),
            "matrix_sha256": matrix_descriptor.get("sha256"),
            "rhs_sha256": rhs_descriptor.get("sha256"),
            "la1_decision": actual_la1["decision"],
        },
        "la1": actual_la1,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check LA0 failed-class evidence")
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--raw-dir", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    result = check_record(
        args.record.resolve(),
        expected_sha=args.expected_source_sha,
        raw_dir=args.raw_dir.resolve() if args.raw_dir else None,
    )
    payload = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output:
        if args.output.exists():
            raise SystemExit(f"output already exists: {args.output}")
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
