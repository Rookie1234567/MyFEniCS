"""Independent streaming checker for FC0 local-factor certificates."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np
from scipy.linalg import solve_triangular

SCHEMA = "task038.full3d.local-factor-certification-v2.worker.v1"
CERT_SCHEMA = "task038.local-factor-certification-v2"
EPS64 = float(np.finfo(np.float64).eps)
MAX_CLASSES = 32
MAX_LOCAL_ROWS = 882
FACTOR_BYTES_LIMIT = 6_230_448
TOTAL_FACTOR_BYTES_LIMIT = 199_374_336
ORDINARY_RESIDUAL_LIMIT = 1.0e-10
KAPPA_LIMIT = 1.0e8
HARD_BYTES = 2_000_000_000


def _gamma_n(rows: int) -> float:
    n = int(rows)
    if n < 1 or n > MAX_LOCAL_ROWS:
        raise ValueError("local row count is outside the frozen cap")
    return n * EPS64 / (1.0 - n * EPS64)


def _fixed_rhs(rows: int) -> np.ndarray:
    return np.arange(int(rows), dtype=np.float64) + (0.125 + 0.25j)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _relative(values: np.ndarray, reference: np.ndarray) -> float:
    return float(np.linalg.norm(np.asarray(values))) / max(
        float(np.linalg.norm(np.asarray(reference))), 1.0e-300
    )


def _gate_passes(value: float, limit: float) -> bool:
    return bool(np.isfinite(value) and float(value) <= float(limit))


def _packed_sha256(value: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(value).view(np.uint8).tobytes()).hexdigest()


def _is_digest(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )


def _independent_certificate(matrix: np.ndarray, rhs: np.ndarray) -> dict[str, Any]:
    array = np.ascontiguousarray(np.asarray(matrix, dtype=np.complex128))
    vector = np.ascontiguousarray(np.asarray(rhs, dtype=np.complex128))
    if array.ndim != 2 or array.shape[0] != array.shape[1]:
        raise ValueError("B0 is not square")
    rows = int(array.shape[0])
    if rows < 1 or rows > MAX_LOCAL_ROWS:
        raise ValueError("B0 row count is outside the frozen cap")
    if vector.shape != (rows,) or not np.array_equal(vector, _fixed_rhs(rows)):
        raise ValueError("fixed RHS identity failed")
    if not np.all(np.isfinite(array)) or not np.all(np.isfinite(vector)):
        raise ValueError("B0/RHS is non-finite")
    lower_raw = np.linalg.cholesky(array)
    indices = np.tril_indices(rows)
    packed = np.ascontiguousarray(lower_raw[indices], dtype=np.complex128)
    lower = np.zeros_like(lower_raw)
    lower[indices] = packed
    repacked = np.ascontiguousarray(lower[indices], dtype=np.complex128)
    first = solve_triangular(lower, vector, lower=True, check_finite=True)
    solution = solve_triangular(lower.conj().T, first, lower=False, check_finite=True)
    first_repeat = solve_triangular(lower, vector, lower=True, check_finite=True)
    repeated = solve_triangular(lower.conj().T, first_repeat, lower=False, check_finite=True)
    hermitian = 0.5 * (array + array.conj().T)
    eigenvalues = np.linalg.eigvalsh(hermitian)
    lambda_min = float(eigenvalues[0])
    lambda_max = float(eigenvalues[-1])
    kappa2 = float(lambda_max / lambda_min) if lambda_min > 0.0 else float("inf")
    gamma = _gamma_n(rows)
    thresholds = {
        "hermitian_defect": max(1.0e-13, 8.0 * gamma),
        "factorization_relative_error": max(1.0e-13, 16.0 * gamma),
        "normalized_backward_error": max(1.0e-14, 16.0 * gamma),
        "ordinary_relative_residual": ORDINARY_RESIDUAL_LIMIT,
        "kappa2": KAPPA_LIMIT,
        "factor_bytes": FACTOR_BYTES_LIMIT,
    }
    residual = array @ solution - vector
    matrix_norm = float(np.linalg.norm(array, ord=2))
    backward_denominator = matrix_norm * float(np.linalg.norm(solution)) + float(np.linalg.norm(vector))
    values = {
        "schema": CERT_SCHEMA,
        "rows": rows,
        "finite": True,
        "rhs_identity": True,
        "hermitian_defect": _relative(array - array.conj().T, array),
        "lambda_min": lambda_min,
        "lambda_max": lambda_max,
        "kappa2": kappa2,
        "factorization_relative_error": _relative(lower @ lower.conj().T - array, array),
        "packed_roundtrip_exact": bool(np.array_equal(packed, repacked)),
        "packed_roundtrip_relative": _relative(repacked - packed, packed),
        "packed_factor_sha256": _packed_sha256(packed),
        "repacked_factor_sha256": _packed_sha256(repacked),
        "packed_bytes": int(packed.nbytes),
        "triangular_repeat_exact": bool(np.array_equal(solution, repeated)),
        "triangular_repeat_relative": _relative(repeated - solution, solution),
        "ordinary_relative_residual": _relative(residual, vector),
        "normalized_backward_error": float(np.linalg.norm(residual)) / max(backward_denominator, 1.0e-300),
        "solution_finite": bool(np.all(np.isfinite(solution))),
        "matrix_norm_2": matrix_norm,
        "rhs_norm_2": float(np.linalg.norm(vector)),
        "thresholds": thresholds,
    }
    values["gates"] = {
        "finite": bool(values["finite"] and values["solution_finite"]),
        "rows": True,
        "hermitian": _gate_passes(values["hermitian_defect"], thresholds["hermitian_defect"]),
        "positive": lambda_min > 0.0,
        "kappa2": _gate_passes(kappa2, KAPPA_LIMIT),
        "factorization": _gate_passes(values["factorization_relative_error"], thresholds["factorization_relative_error"]),
        "packed_identity": bool(values["packed_roundtrip_exact"] and values["packed_factor_sha256"] == values["repacked_factor_sha256"]),
        "triangular_repeat": values["triangular_repeat_exact"],
        "backward": _gate_passes(values["normalized_backward_error"], thresholds["normalized_backward_error"]),
        "ordinary_residual": _gate_passes(values["ordinary_relative_residual"], ORDINARY_RESIDUAL_LIMIT),
        "factor_bytes": _gate_passes(values["packed_bytes"], FACTOR_BYTES_LIMIT),
    }
    values["gate_pass"] = bool(all(values["gates"].values()))
    return values


def _compare_recorded(recorded: Mapping[str, Any], actual: Mapping[str, Any], errors: list[str], label: str) -> None:
    for key in (
        "rows", "finite", "rhs_identity", "packed_roundtrip_exact",
        "packed_factor_sha256", "repacked_factor_sha256", "packed_bytes",
        "triangular_repeat_exact", "solution_finite", "gate_pass",
    ):
        if recorded.get(key) != actual.get(key):
            errors.append(f"{label}: recorded {key} does not close")
    for key in (
        "hermitian_defect", "lambda_min", "lambda_max", "kappa2",
        "factorization_relative_error", "packed_roundtrip_relative",
        "triangular_repeat_relative", "ordinary_relative_residual",
        "normalized_backward_error",
    ):
        if not np.isclose(recorded.get(key), actual.get(key), rtol=1.0e-14, atol=1.0e-300):
            errors.append(f"{label}: recorded {key} does not close")
    if recorded.get("gates") != actual.get("gates"):
        errors.append(f"{label}: recorded gates do not close")
    recorded_thresholds = recorded.get("thresholds")
    actual_thresholds = actual.get("thresholds")
    if not isinstance(recorded_thresholds, Mapping) or not isinstance(actual_thresholds, Mapping):
        errors.append(f"{label}: recorded thresholds are missing")
    elif set(recorded_thresholds) != set(actual_thresholds) or any(
        not np.isclose(recorded_thresholds[key], actual_thresholds[key], rtol=0.0, atol=0.0)
        for key in actual_thresholds
    ):
        errors.append(f"{label}: recorded thresholds do not close")


def _check_resource(record: Mapping[str, Any], errors: list[str]) -> None:
    contract = record.get("resource_contract")
    if not isinstance(contract, Mapping):
        errors.append("resource_contract is missing")
        return
    raw_path = Path(str(contract.get("raw_path", "")))
    compact_path = Path(str(contract.get("compact_path", "")))
    if not raw_path.is_file() or not compact_path.is_file():
        errors.append("watchdog raw/compact path is missing")
        return
    try:
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
        compact = json.loads(compact_path.read_text(encoding="utf-8"))
        samples = raw.get("samples", [])
        if not samples or any(
            not isinstance(row.get("authority"), Mapping)
            or row.get("authority_error")
            for row in samples
        ):
            errors.append("watchdog has no complete authority samples")
        if any(
            int(row["authority"].get("process_tree", {}).get("swap_bytes", -1)) != 0
            for row in samples
        ):
            errors.append("watchdog sample swap is nonzero")
        if raw.get("worker_returncode") != 0 or compact.get("worker_returncode") != 0:
            errors.append("worker did not return zero")
        if compact.get("process_tree_swap_gate") is not True:
            errors.append("watchdog swap gate failed")
        if int(compact.get("process_tree_peak_memory_authority_bytes", HARD_BYTES)) >= HARD_BYTES:
            errors.append("watchdog hard memory gate failed")
        if compact.get("stop_reason") != "natural_exit" or compact.get("natural_exit") is not True:
            errors.append("watchdog did not report natural rc0 completion")
        if compact.get("authority_complete") is not True:
            errors.append("watchdog authority samples are incomplete")
        if compact.get("raw_sha256") != _sha256(raw_path):
            errors.append("watchdog raw hash does not close")
        termination = compact.get("termination", {})
        if termination.get("method") != "already_exited" or compact.get("no_orphan_claim") is not True:
            errors.append("watchdog natural no-orphan contract failed")
    except (OSError, ValueError, TypeError, KeyError) as exc:
        errors.append(f"watchdog evidence is unreadable: {type(exc).__name__}: {exc}")


def check_record(record_path: Path, expected_source_sha: str | None = None) -> dict[str, Any]:
    errors: list[str] = []
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"passed": False, "errors": [f"record unreadable: {exc}"]}
    if not isinstance(record, Mapping):
        return {"passed": False, "errors": ["record is not an object"]}
    if record.get("schema") != SCHEMA:
        errors.append("worker schema is missing")
    if record.get("certification_schema") != CERT_SCHEMA:
        errors.append("certification-v2 schema is missing")
    if record.get("case") != "p6-h10-mpi1" or record.get("degree") != 6 or record.get("mesh_target_nm") != 10.0 or record.get("profile") != "full3d_scalable_v1":
        errors.append("frozen FC0 case identity failed")
    if record.get("mpi_size") != 1:
        errors.append("FC0 requires MPI1")
    source_identity = record.get("source_identity")
    runtime = record.get("runtime")
    if not isinstance(source_identity, Mapping) or not isinstance(runtime, Mapping):
        errors.append("source/runtime identity is missing")
    else:
        if expected_source_sha is not None and source_identity.get("source_git_sha") != expected_source_sha:
            errors.append("source Git SHA does not match expected clean SHA")
        if source_identity.get("expected_sha") != source_identity.get("source_git_sha"):
            errors.append("source expected/start SHA does not close")
        if source_identity.get("tracked_status") != "":
            errors.append("formal source is not clean")
        if runtime.get("source_identity") != source_identity:
            errors.append("runtime and top-level source identity differ")
        if runtime.get("qualified_activation") != "1" or runtime.get("mpi_size") != 1:
            errors.append("qualified runtime/MPI identity failed")
        if runtime.get("scalar_dtype") != "complex128" or runtime.get("int_dtype") != "int32":
            errors.append("qualified scalar/index ABI identity failed")
        executable = str(runtime.get("sys_executable", ""))
        if ".venv/" not in executable or "\\" in executable:
            errors.append("runtime executable is not the qualified Linux venv")
    input_identity = record.get("input")
    if not isinstance(input_identity, Mapping):
        errors.append("input identity is missing")
    else:
        input_path = Path(str(input_identity.get("path", "")))
        try:
            if not input_path.is_file() or _sha256(input_path) != input_identity.get("file_sha256"):
                errors.append("frozen input hash does not close")
        except OSError as exc:
            errors.append(f"frozen input is unreadable: {exc}")
    threshold_contract = record.get("threshold_contract")
    expected_contract = {
        "eps64": EPS64,
        "ordinary_relative_residual": ORDINARY_RESIDUAL_LIMIT,
        "kappa2": KAPPA_LIMIT,
        "factor_bytes": FACTOR_BYTES_LIMIT,
        "total_factor_bytes": TOTAL_FACTOR_BYTES_LIMIT,
    }
    if not isinstance(threshold_contract, Mapping) or set(threshold_contract) != set(expected_contract) or any(
        not np.isclose(threshold_contract[key], value, rtol=0.0, atol=0.0)
        for key, value in expected_contract.items()
    ):
        errors.append("frozen threshold contract does not close")
    order = record.get("class_order")
    if not isinstance(order, list) or not all(_is_digest(value) for value in order) or tuple(order) != tuple(sorted(set(order))) or len(order) > MAX_CLASSES:
        errors.append("class order/count is invalid")
        order = []
    elif not order:
        errors.append("FC0 has no exact classes")
    else:
        expected_order_sha = hashlib.sha256(json.dumps(order, separators=(",", ":")).encode("utf-8")).hexdigest()
        if record.get("class_order_sha256") != expected_order_sha:
            errors.append("class order hash failed")
    classes = record.get("classes")
    if not isinstance(classes, list) or len(classes) != len(order):
        errors.append("class record count does not close class order")
        classes = []
    seen: set[str] = set()
    actuals: list[Mapping[str, Any]] = []
    class_facts: list[dict[str, Any]] = []
    for item in classes:
        label = f"class[{item.get('slot', '?')}]" if isinstance(item, Mapping) else "class[?]"
        try:
            if not isinstance(item, Mapping):
                raise ValueError("class record is not an object")
            digest = str(item["digest"])
            slot = int(item["slot"])
            if digest in seen or slot != len(actuals) or digest != order[slot]:
                raise ValueError("class slot/order/duplicate failed")
            seen.add(digest)
            matrix_descriptor = item["matrix"]
            rhs_descriptor = item["rhs"]
            matrix_path = Path(str(matrix_descriptor["path"]))
            rhs_path = Path(str(rhs_descriptor["path"]))
            if _sha256(matrix_path) != matrix_descriptor["sha256"] or _sha256(rhs_path) != rhs_descriptor["sha256"]:
                raise ValueError("matrix/RHS hash failed")
            if matrix_descriptor.get("bytes") != matrix_path.stat().st_size or rhs_descriptor.get("bytes") != rhs_path.stat().st_size:
                raise ValueError("matrix/RHS byte descriptor failed")
            matrix = np.load(matrix_path, allow_pickle=False)
            rhs = np.load(rhs_path, allow_pickle=False)
            if matrix.dtype != np.dtype("complex128") or rhs.dtype != np.dtype("complex128"):
                raise ValueError("matrix/RHS dtype is not complex128")
            if matrix_descriptor.get("shape") != list(matrix.shape) or matrix_descriptor.get("dtype") != str(matrix.dtype):
                raise ValueError("matrix descriptor shape/dtype failed")
            if rhs_descriptor.get("shape") != list(rhs.shape) or rhs_descriptor.get("dtype") != str(rhs.dtype):
                raise ValueError("RHS descriptor shape/dtype failed")
            actual = _independent_certificate(matrix, rhs)
            representative = item.get("representative_cell")
            if (
                item.get("factor_owner_rank") != 0
                or item.get("representative_rank") != 0
                or not isinstance(representative, Mapping)
                or representative.get("row_count") != actual["rows"]
                or not _is_digest(representative.get("canonical_free_row_descriptor_sha256"))
                or not isinstance(representative.get("widths"), list)
                or "cell_key" not in representative
                or "tag" not in representative
            ):
                raise ValueError("representative canonical identity does not close")
            _compare_recorded(item.get("metrics", {}), actual, errors, label)
            if actual["gate_pass"] is not True:
                failed = tuple(
                    key for key, value in actual["gates"].items() if value is not True
                )
                errors.append(f"{label}: certification-v2 Gate failed: {failed}")
            actuals.append(actual)
            class_facts.append({
                "digest": digest,
                "slot": slot,
                "representative_rank": int(item["representative_rank"]),
                "factor_owner_rank": int(item["factor_owner_rank"]),
                "representative_identity": representative,
                "matrix": {
                    "path": str(matrix_path),
                    "sha256": matrix_descriptor["sha256"],
                    "bytes": int(matrix_descriptor["bytes"]),
                    "shape": list(matrix.shape),
                    "dtype": str(matrix.dtype),
                },
                "rhs": {
                    "path": str(rhs_path),
                    "sha256": rhs_descriptor["sha256"],
                    "bytes": int(rhs_descriptor["bytes"]),
                    "shape": list(rhs.shape),
                    "dtype": str(rhs.dtype),
                },
                "factor": {
                    "packed_sha256": actual["packed_factor_sha256"],
                    "repacked_sha256": actual["repacked_factor_sha256"],
                    "bytes": int(actual["packed_bytes"]),
                },
                "rows": int(actual["rows"]),
                "gates": dict(actual["gates"]),
                "thresholds": dict(actual["thresholds"]),
                "metrics": dict(actual),
            })
            del matrix, rhs, actual
        except (OSError, ValueError, TypeError, KeyError, np.linalg.LinAlgError) as exc:
            errors.append(f"{label}: fail-closed check error: {type(exc).__name__}: {exc}")
    summary = record.get("summary", {})
    if len(actuals) != len(order):
        errors.append("not all classes were independently recomputed")
    total = sum(int(value["packed_bytes"]) for value in actuals)
    if total > TOTAL_FACTOR_BYTES_LIMIT:
        errors.append("global factor-byte limit failed")
    if len(actuals) == len(order) and not all(value["gate_pass"] is True for value in actuals):
        errors.append("independent all-class certification Gate failed")
    repeated_order = record.get("class_order_repeat")
    if (
        not isinstance(repeated_order, list)
        or not all(_is_digest(value) for value in repeated_order)
        or tuple(repeated_order) != tuple(sorted(set(repeated_order)))
    ):
        errors.append("independent repeated class inventory is invalid")
        repeated_order = []
    repeat_sha = hashlib.sha256(json.dumps(repeated_order, separators=(",", ":")).encode("utf-8")).hexdigest()
    if (
        record.get("class_order_repeat_sha256") != repeat_sha
        or tuple(repeated_order) != tuple(order)
        or record.get("class_order_repeat_exact") is not True
    ):
        errors.append("class order repeat/hash identity failed")
    if (
        summary.get("class_count") != len(order)
        or summary.get("class_order") != order
        or summary.get("class_order_sha256") != record.get("class_order_sha256")
        or summary.get("class_order_repeat") != repeated_order
        or summary.get("class_order_repeat_sha256") != repeat_sha
        or summary.get("class_order_repeat_exact") is not True
        or summary.get("class_count_within_limit") != (len(order) <= MAX_CLASSES)
        or summary.get("class_order_sorted_unique") != (tuple(order) == tuple(sorted(set(order))))
        or summary.get("all_classes_processed") != (len(actuals) == len(order))
        or summary.get("processed_class_count") != len(actuals)
    ):
        errors.append("class summary inventory does not close")
    if summary.get("duplicate_class_count") != 0 or summary.get("missing_class_count") != 0:
        errors.append("class duplicate/missing closure failed")
    closure = summary.get("factor_owner_closure")
    if not isinstance(closure, Mapping) or closure.get("mpi_size") != 1 or closure.get("unique_factor_count") != len(order) or closure.get("duplicate_factor_count") != 0 or closure.get("owner_rank_set") != [0]:
        errors.append("factor owner closure failed")
    computed_all_pass = bool(actuals) and len(actuals) == len(order) and all(value["gate_pass"] is True for value in actuals)
    computed_global_bytes_pass = total <= TOTAL_FACTOR_BYTES_LIMIT
    if (
        summary.get("all_class_certificates_pass") is not computed_all_pass
        or summary.get("global_factor_count") != len(actuals)
        or summary.get("total_factor_bytes") != total
        or summary.get("total_factor_bytes_limit") != TOTAL_FACTOR_BYTES_LIMIT
        or summary.get("all_class_factor_bytes_within_global_limit") is not computed_global_bytes_pass
        or summary.get("overall_gate_pass") is not bool(
            len(order) <= MAX_CLASSES
            and tuple(order) == tuple(sorted(set(order)))
            and len(actuals) == len(order)
            and computed_all_pass
            and computed_global_bytes_pass
        )
    ):
        errors.append("worker summary all-class status does not close")
    if summary.get("dense_class_max_live") != 1 or summary.get("dense_workspace_released") is not True:
        errors.append("sequential dense lifecycle audit failed")
    lifecycle = record.get("lifecycle", {})
    if lifecycle.get("modes_built") is not False or lifecycle.get("regional_built") is not False or lifecycle.get("top_built") is not False or lifecycle.get("physical_action_built") is not False or lifecycle.get("rho_run") is not False:
        errors.append("FC0 forbidden stages were reported as run")
    forbidden = lifecycle.get("forbidden")
    if not isinstance(forbidden, Mapping) or any(forbidden.get(key) is not False for key in ("global_aij", "global_schur", "global_factor", "numeric_allgather")):
        errors.append("FC0 forbidden materialization audit is not explicitly false")
    _check_resource(record, errors)
    contract = record.get("resource_contract")
    if not isinstance(contract, Mapping) or contract.get("status") != "measured":
        errors.append("resource_contract is not externally measured")
    for fact in class_facts:
        fact["metrics"]["packed_identity_value"] = 0.0 if fact["metrics"]["packed_roundtrip_exact"] else 1.0
        fact["metrics"]["repeat_value"] = 0.0 if fact["metrics"]["triangular_repeat_exact"] else 1.0

    def worst(metric: str, limit: Any, *, reverse: bool) -> dict[str, Any] | None:
        if not class_facts:
            return None
        chosen = max(
            class_facts,
            key=lambda fact: float(fact["metrics"][metric]),
        ) if reverse else min(
            class_facts,
            key=lambda fact: float(fact["metrics"][metric]),
        )
        limit_value = limit(chosen) if callable(limit) else limit
        return {
            "digest": chosen["digest"],
            "slot": chosen["slot"],
            "rows": int(chosen["metrics"]["rows"]),
            "value": float(chosen["metrics"][metric]),
            "limit": float(limit_value),
        }

    worst_values = {
        "hermitian_defect": worst("hermitian_defect", lambda fact: fact["metrics"]["thresholds"]["hermitian_defect"], reverse=True),
        "lambda_min_spd_margin": worst("lambda_min", 0.0, reverse=False),
        "kappa2": worst("kappa2", KAPPA_LIMIT, reverse=True),
        "factorization_relative_error": worst("factorization_relative_error", lambda fact: fact["metrics"]["thresholds"]["factorization_relative_error"], reverse=True),
        "ordinary_relative_residual": worst("ordinary_relative_residual", ORDINARY_RESIDUAL_LIMIT, reverse=True),
        "normalized_backward_error": worst("normalized_backward_error", lambda fact: fact["metrics"]["thresholds"]["normalized_backward_error"], reverse=True),
        "factor_bytes": worst("packed_bytes", FACTOR_BYTES_LIMIT, reverse=True),
    }
    for key, metric, limit, reverse in (
        ("packing", "packed_identity_value", 0.0, True),
        ("repeat", "repeat_value", 0.0, True),
    ):
        worst_values[key] = worst(metric, limit, reverse=reverse)
    return {
        "schema": "task038.full3d.local-factor-certification-v2.check.v1",
        "certification_schema": CERT_SCHEMA,
        "record": str(record_path),
        "class_count": len(actuals),
        "all_classes_processed": len(actuals) == len(order),
        "all_class_certificates_pass": computed_all_pass,
        "all_class_factor_bytes_within_global_limit": computed_global_bytes_pass,
        "overall_gate_pass": bool(
            len(order) <= MAX_CLASSES
            and tuple(order) == tuple(sorted(set(order)))
            and len(actuals) == len(order)
            and computed_all_pass
            and computed_global_bytes_pass
        ),
        "class_order": list(order),
        "class_order_sha256": record.get("class_order_sha256"),
        "class_order_repeat": list(repeated_order),
        "class_order_repeat_sha256": record.get("class_order_repeat_sha256"),
        "class_order_repeat_exact": record.get("class_order_repeat_exact"),
        "missing_class_count": 0 if len(actuals) == len(order) else len(order) - len(actuals),
        "duplicate_class_count": len(order) - len(set(order)),
        "owner_closure": record.get("summary", {}).get("factor_owner_closure"),
        "total_factor_bytes": total,
        "total_factor_bytes_limit": TOTAL_FACTOR_BYTES_LIMIT,
        "threshold_contract": {
            "eps64": EPS64,
            "ordinary_relative_residual": ORDINARY_RESIDUAL_LIMIT,
            "kappa2": KAPPA_LIMIT,
            "factor_bytes": FACTOR_BYTES_LIMIT,
            "total_factor_bytes": TOTAL_FACTOR_BYTES_LIMIT,
        },
        "class_certificates": class_facts,
        "worst": worst_values,
        "passed": not errors,
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Independent FC0 checker")
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = check_record(args.record, args.expected_source_sha)
    if args.output is not None:
        if args.output.exists():
            raise FileExistsError(f"checker output already exists: {args.output}")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
