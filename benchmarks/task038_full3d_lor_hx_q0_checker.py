"""Read-only checker for the Review V10 Q0 exact-reference record."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np


SCHEMA = "task038.lor-native-complex-hx.q0-record.v1"
MODULE = "benchmarks.run_task038_full3d_lor_hx_q0"
CASE = "p3-mpi1"
SOURCE_NAME = "random"
VARIANT = "sequential-v1"
TRACE_NAMES = (
    "edge_jacobi_pre",
    "gradient",
    "pi_x",
    "pi_y",
    "pi_z",
    "edge_jacobi_post",
)
NODAL_TRACE_NAMES = ("gradient", "pi_x", "pi_y", "pi_z")
RESTART = 20
MAX_IT = 500
RESIDUAL_LIMIT = 1.0e-8
EXACT_LIMIT = 1.0e-12
REPEAT_LIMIT = 1.0e-13
INPUT_LIMIT = 1.0e-12

HIGH_ROLES = {
    "source_before",
    "source_after",
    "high_rhs",
    "high_rhs_repeat",
    "e_input_before",
    "e_input_after",
    "e_output",
    "e_repeat",
    "e_final_solution",
    "e_final_action",
    "e_final_true_residual",
    "n_input_before",
    "n_input_after",
    "n_output",
    "n_repeat",
    "n_final_solution",
    "n_final_action",
    "n_final_true_residual",
}
LOW_ROLES = {
    "e_low_solution",
    "e_low_input",
    "e_low_input_matrix",
    "e_low_solution_matrix",
    "n_low_input",
}
for _trace_name in TRACE_NAMES:
    LOW_ROLES.update(
        {
            f"n_{_trace_name}_result",
            f"n_{_trace_name}_remaining",
            f"n_{_trace_name}_edge_delta",
            f"n_{_trace_name}_edge_action",
        }
    )
for _trace_name in NODAL_TRACE_NAMES:
    LOW_ROLES.update(
        {
            f"n_{_trace_name}_rhs",
            f"n_{_trace_name}_nodal_delta",
            f"n_{_trace_name}_rhs_matrix",
            f"n_{_trace_name}_nodal_delta_matrix",
        }
    )
CONSTRAINT_ROLES = {
    "e_output_constraint",
    "e_repeat_constraint",
    "n_output_constraint",
    "n_repeat_constraint",
    "e_final_constraint",
    "n_final_constraint",
}
ALL_ROLES = HIGH_ROLES | LOW_ROLES | CONSTRAINT_ROLES


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(
            "utf-8"
        )
        + b"\n"
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _relative(left: np.ndarray, right: np.ndarray) -> float:
    left = np.asarray(left, dtype=np.complex128)
    right = np.asarray(right, dtype=np.complex128)
    return float(
        np.linalg.norm(left - right)
        / max(np.linalg.norm(right), np.finfo(float).tiny)
    )


def _norm_ratio(numerator: np.ndarray, denominator: np.ndarray) -> float:
    return float(
        np.linalg.norm(np.asarray(numerator, dtype=np.complex128))
        / max(
            np.linalg.norm(np.asarray(denominator, dtype=np.complex128)),
            np.finfo(float).tiny,
        )
    )


def _base_relative(
    actual: np.ndarray, expected: np.ndarray, base: np.ndarray
) -> float:
    return _norm_ratio(
        np.asarray(actual, dtype=np.complex128)
        - np.asarray(expected, dtype=np.complex128),
        base,
    )


def _is_sha(value: Any, length: int) -> bool:
    value = str(value)
    return len(value) == length and all(c in "0123456789abcdef" for c in value)


def _inside(root: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


def _load_array(
    raw_dir: Path, descriptor: Any, errors: list[str], label: str
) -> np.ndarray | None:
    if not isinstance(descriptor, dict):
        errors.append(f"{label}: descriptor is not an object")
        return None
    relative = descriptor.get("relative_path")
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        errors.append(f"{label}: invalid relative_path")
        return None
    path = (raw_dir / relative).resolve()
    if not _inside(raw_dir, path) or not path.is_file():
        errors.append(f"{label}: artifact is outside raw_dir or missing")
        return None
    expected_sha = descriptor.get("sha256")
    if not _is_sha(expected_sha, 64) or _sha256(path) != expected_sha:
        errors.append(f"{label}: SHA256 mismatch")
        return None
    try:
        array = np.load(path, allow_pickle=False)
    except Exception as exc:
        errors.append(f"{label}: cannot load array ({type(exc).__name__})")
        return None
    if str(array.dtype) != str(descriptor.get("dtype")):
        errors.append(f"{label}: dtype mismatch")
    if list(array.shape) != list(descriptor.get("shape", ())):
        errors.append(f"{label}: shape mismatch")
    if int(path.stat().st_size) != int(descriptor.get("bytes", -1)):
        errors.append(f"{label}: byte-size mismatch")
    return np.asarray(array)


def _load_role(
    raw_dir: Path,
    role: str,
    descriptor: Any,
    errors: list[str],
) -> tuple[np.ndarray, np.ndarray] | None:
    if not isinstance(descriptor, dict):
        errors.append(f"canonical artifact {role}: descriptor missing")
        return None
    keys = _load_array(raw_dir, descriptor.get("keys"), errors, f"{role}.keys")
    values = _load_array(raw_dir, descriptor.get("values"), errors, f"{role}.values")
    if keys is None or values is None:
        return None
    keys = np.asarray(keys)
    values = np.asarray(values, dtype=np.complex128)
    if keys.ndim != 1 or values.ndim != 1 or keys.size != values.size:
        errors.append(f"canonical artifact {role}: key/value shape mismatch")
        return None
    if len(set(str(value) for value in keys)) != keys.size:
        errors.append(f"canonical artifact {role}: duplicate key")
    if not np.all(np.isfinite(values)):
        errors.append(f"canonical artifact {role}: non-finite values")
    return keys.astype(str), values


def _expected_role_kind(role: str) -> str:
    if role in CONSTRAINT_ROLES:
        return "constraint"
    if role == "e_low_input_matrix":
        return "dual"
    if role == "e_low_solution_matrix":
        return "primal"
    if role in HIGH_ROLES:
        return "primal" if role in {"source_before", "source_after", "e_output", "e_repeat", "e_final_solution", "n_output", "n_repeat", "n_final_solution"} else "dual"
    if "rhs" in role or "nodal_delta" in role:
        return "node"
    if "remaining" in role or "edge_action" in role or role.endswith("_input"):
        return "dual"
    return "primal"


def _align(
    left: tuple[np.ndarray, np.ndarray] | None,
    right: tuple[np.ndarray, np.ndarray] | None,
    errors: list[str],
    label: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
    if left is None or right is None:
        return None
    left_keys, left_values = left
    right_keys, right_values = right
    left_map = {str(key): index for index, key in enumerate(left_keys)}
    right_map = {str(key): index for index, key in enumerate(right_keys)}
    if set(left_map) != set(right_map):
        errors.append(f"{label}: key sets differ")
        return None
    order = np.asarray([right_map[str(key)] for key in left_keys], dtype=np.int64)
    return left_values, right_values[order], left_keys


def _check_settings(record: dict[str, Any], errors: list[str]) -> None:
    settings = record.get("settings")
    if not isinstance(settings, dict):
        errors.append("settings: missing")
        return
    outer = settings.get("reference_outer")
    expected_outer = {
        "ksp_type": "gmres",
        "pc_side": "right",
        "norm_type": "unpreconditioned",
        "restart": RESTART,
        "max_it": MAX_IT,
        "residual_replacement": True,
        "zero_initial_guess": True,
        "residual_limit": RESIDUAL_LIMIT,
    }
    if outer != expected_outer:
        errors.append("settings.reference_outer: frozen contract mismatch")
    edge = settings.get("edge_direct")
    if not isinstance(edge, dict) or edge.get("ksp_type") != "preonly" or edge.get("pc_type") != "lu" or edge.get("factor_solver_type") != "mumps" or edge.get("factor_reused_per_reference") is not True:
        errors.append("settings.edge_direct: exact factor contract mismatch")
    nodal = settings.get("nodal_direct")
    if not isinstance(nodal, dict) or nodal.get("ksp_type") != "preonly" or nodal.get("pc_type") != "lu" or nodal.get("factor_solver_type") != "mumps" or nodal.get("factor_reused_for_four_components") is not True:
        errors.append("settings.nodal_direct: exact factor contract mismatch")
    for key, expected in (
        ("exact_edge_limit", EXACT_LIMIT),
        ("exact_nodal_limit", EXACT_LIMIT),
        ("input_limit", INPUT_LIMIT),
        ("repeat_limit", REPEAT_LIMIT),
    ):
        if settings.get(key) != expected:
            errors.append(f"settings.{key}: mismatch")


def _check_source_runtime(
    record: dict[str, Any], record_path: Path, expected_source_sha: str | None, errors: list[str]
) -> Path | None:
    if record.get("schema") != SCHEMA or record.get("stage") != "q0":
        errors.append("schema/stage: mismatch")
    if record.get("case") != CASE or record.get("degree") != 3 or record.get("h_nm") != 50.0 or record.get("mpi_size") != 1 or record.get("source_name") != SOURCE_NAME or record.get("variant") != VARIANT:
        errors.append("case/degree/mpi/source/variant: mismatch")
    raw_value = record.get("raw_dir")
    if not isinstance(raw_value, str):
        errors.append("raw_dir: missing")
        return None
    raw_dir = Path(raw_value).resolve()
    if not raw_dir.is_dir():
        errors.append("raw_dir: missing directory")
        return None
    source = record.get("source")
    if not isinstance(source, dict):
        errors.append("source: missing")
    else:
        expected = source.get("expected_sha")
        if not _is_sha(expected, 40) or (expected_source_sha is not None and expected != expected_source_sha):
            errors.append("source.expected_sha: invalid or unexpected")
        for key in ("commit_sha_start", "commit_sha_end"):
            if source.get(key) != expected:
                errors.append(f"source.{key}: does not match expected SHA")
        if source.get("branch") != "codex/20260820-task38-extra-full3d-iterative-0p7nm":
            errors.append("source.branch: mismatch")
        if source.get("clean_start") is not True or source.get("clean_end") is not True or source.get("tracked_status_start") != "" or source.get("tracked_status_end") != "":
            errors.append("source: clean start/end contract failed")
    source_facts = record.get("source_facts")
    expected_formula = "analytic deterministic pseudo-random edge field from fixed noninteger trigonometric frequencies and phases"
    if not isinstance(source_facts, dict) or source_facts.get("name") != SOURCE_NAME or source_facts.get("formula") != expected_formula or source_facts.get("phase_application") != "algebraic_slave_zero_action_internal_finalized_mpc_once":
        errors.append("source_facts: frozen random source contract failed")
    runtime = record.get("runtime")
    if not isinstance(runtime, dict):
        errors.append("runtime: missing")
    else:
        if runtime.get("qualified_activation") != "1" or runtime.get("mpi_size") != 1 or runtime.get("petsc_scalar_type") != "complex128" or runtime.get("petsc_int_type") != "int32":
            errors.append("runtime ABI/activation contract failed")
    command = record.get("command")
    if not isinstance(command, list) or len(command) < 2 or not isinstance(command[0], str) or not Path(command[0]).is_absolute() or command[1:3] != ["-m", MODULE]:
        errors.append("command: exact Q0 module provenance missing")
    else:
        pairs = dict(zip(command[3::2], command[4::2]))
        if pairs.get("--stage") != "q0" or pairs.get("--case") != CASE or pairs.get("--raw-dir") != str(raw_dir) or pairs.get("--record") != str(record_path.resolve()) or pairs.get("--expected-mpi-size") != "1":
            errors.append("command: required identity arguments mismatch")
        if expected_source_sha is not None and pairs.get("--expected-source-sha") != expected_source_sha:
            errors.append("command: expected source SHA mismatch")
    provenance = record.get("provenance")
    if not isinstance(provenance, dict):
        errors.append("provenance: missing")
    else:
        for key in ("input_identity_sha256", "operator_identity_sha256", "physical_model_sha256"):
            if not _is_sha(provenance.get(key), 64):
                errors.append(f"provenance.{key}: invalid SHA256")
    return raw_dir


def _check_fixture_audit(record: dict[str, Any], errors: list[str]) -> None:
    audit = record.get("fixture_audit")
    if not isinstance(audit, dict):
        errors.append("fixture_audit: missing")
        return
    required_false = ("high_order_global_aij", "global_transfer_matrix", "global_numeric_allgather")
    for key in required_false:
        if audit.get(key) is not False:
            errors.append(f"fixture_audit.{key}: forbidden value")
    for key, expected in (("variant", VARIANT), ("degree", 3), ("high_order_matrix_free", True), ("slave_master_complete", True), ("phase_application", "finalized_floquet_mpc_once"), ("raw_edge_orientation_consistent", True), ("raw_edge_orientation_owned_rows_closed", True)):
        if audit.get(key) != expected:
            errors.append(f"fixture_audit.{key}: mismatch")
    if int(audit.get("raw_edge_orientation_factor_count", 0)) <= 0:
        errors.append("fixture_audit: missing orientation inventory")
    hx = audit.get("hx_audit")
    if not isinstance(hx, dict):
        errors.append("fixture_audit.hx_audit: missing")
        return
    expected_hx = {
        "variant": VARIANT,
        "composition": "sequential",
        "original_residual_for_all_corrections": False,
        "edge_jacobi_correction_count": 2,
        "gradient_correction_count": 1,
        "vector_correction_order": "x_then_y_then_z",
        "nodal_correction_count": 4,
        "one_v_cycle_per_nodal_correction": True,
        "one_shared_scalar_hierarchy": True,
        "hierarchy_object_count": 1,
        "global_transfer_matrix": False,
        "global_numeric_allgather": False,
        "global_direct_coarse": False,
        "high_order_aij": False,
        "real_imag_split": False,
        "hypre_ams": False,
    }
    for key, expected in expected_hx.items():
        if hx.get(key) != expected:
            errors.append(f"fixture_audit.hx_audit.{key}: mismatch")


def _load_matrix(raw_dir: Path, descriptor: Any, errors: list[str], label: str) -> dict[str, Any] | None:
    if not isinstance(descriptor, dict):
        errors.append(f"matrix {label}: missing")
        return None
    try:
        rows = int(descriptor["rows"])
        cols = int(descriptor["cols"])
        nnz = int(descriptor["nnz"])
    except (KeyError, TypeError, ValueError):
        errors.append(f"matrix {label}: scalar facts missing")
        return None
    indptr = _load_array(raw_dir, descriptor.get("indptr"), errors, f"matrix.{label}.indptr")
    indices = _load_array(raw_dir, descriptor.get("indices"), errors, f"matrix.{label}.indices")
    values = _load_array(raw_dir, descriptor.get("values"), errors, f"matrix.{label}.values")
    row_keys = _load_array(raw_dir, descriptor.get("row_keys"), errors, f"matrix.{label}.row_keys")
    if any(value is None for value in (indptr, indices, values, row_keys)):
        return None
    assert indptr is not None and indices is not None and values is not None and row_keys is not None
    if rows < 0 or cols < 0 or nnz != values.size or indptr.size != rows + 1 or indices.size != values.size or row_keys.size != rows:
        errors.append(f"matrix {label}: CSR shape mismatch")
    if indices.size and (np.min(indices) < 0 or np.max(indices) >= cols):
        errors.append(f"matrix {label}: CSR index out of range")
    if not np.all(np.diff(indptr.astype(np.int64)) >= 0):
        errors.append(f"matrix {label}: CSR indptr is not monotone")
    if int(descriptor.get("numeric_bytes", -1)) != int(values.nbytes) or int(descriptor.get("index_bytes", -1)) != int(indptr.nbytes + indices.nbytes):
        errors.append(f"matrix {label}: retained byte facts mismatch")
    return {
        "rows": rows,
        "cols": cols,
        "indptr": indptr.astype(np.int64),
        "indices": indices.astype(np.int64),
        "values": values.astype(np.complex128),
        "row_keys": row_keys.astype(str),
    }


def _csr_apply(matrix: dict[str, Any], vector: np.ndarray) -> np.ndarray:
    result = np.zeros(int(matrix["rows"]), dtype=np.complex128)
    indptr = matrix["indptr"]
    for row in range(result.size):
        start, stop = int(indptr[row]), int(indptr[row + 1])
        result[row] = np.dot(matrix["values"][start:stop], vector[matrix["indices"][start:stop]])
    return result


def _check_outer(
    outer: Any, label: str, errors: list[str], diagnostics: list[str]
) -> tuple[dict[str, Any] | None, float | None]:
    if not isinstance(outer, dict):
        errors.append(f"{label}.outer: missing")
        return None, None
    cycles = outer.get("cycles")
    if not isinstance(cycles, list) or not cycles:
        errors.append(f"{label}.outer.cycles: missing")
        return None, None
    previous = 0
    for index, cycle in enumerate(cycles):
        if not isinstance(cycle, dict):
            errors.append(f"{label}.cycle[{index}]: not an object")
            continue
        start = cycle.get("start_iteration")
        end = cycle.get("end_iteration")
        if not isinstance(start, int) or start != previous or not isinstance(end, int) or not (0 < end - start <= RESTART):
            errors.append(f"{label}.cycle[{index}]: non-contiguous or oversized")
        previous = end if isinstance(end, int) else previous
        if cycle.get("ksp_destroyed") is not True:
            errors.append(f"{label}.cycle[{index}]: KSP not destroyed")
        explicit = cycle.get("explicit_true_residual")
        if not isinstance(explicit, (int, float)) or not np.isfinite(float(explicit)) or float(explicit) < 0.0:
            errors.append(f"{label}.cycle[{index}]: invalid explicit residual")
        resource = cycle.get("resource")
        tree = resource.get("process_tree") if isinstance(resource, dict) else None
        if not isinstance(tree, dict) or tree.get("all_status_readable") is not True or tree.get("swap_bytes") != 0:
            diagnostics.append(f"{label}.cycle[{index}]: process-tree resource sample was not clean")
    if outer.get("iterations") != previous:
        errors.append(f"{label}.outer: final iteration does not close cycle ledger")
    final_residual = outer.get("final_true_residual")
    boundary_residual = cycles[-1].get("explicit_true_residual")
    if not isinstance(final_residual, (int, float)) or not isinstance(boundary_residual, (int, float)) or not np.isfinite(float(final_residual)) or not np.isclose(float(final_residual), float(boundary_residual), rtol=1e-14, atol=1e-14):
        errors.append(f"{label}.outer: final residual does not close cycle ledger")
    for key in ("matvec_count", "pc_apply_count", "explicit_action_count", "ksp_destroy_count"):
        if not isinstance(outer.get(key), int) or outer[key] < 0:
            errors.append(f"{label}.outer.{key}: invalid count")
    if outer.get("explicit_action_count") != 1 + len(cycles) or outer.get("ksp_destroy_count") != len(cycles):
        errors.append(f"{label}.outer: action/KSP lifecycle count mismatch")
    return outer, float(outer.get("final_true_residual", np.nan))


def _check_csr_direct(
    matrix: dict[str, Any] | None,
    rhs: tuple[np.ndarray, np.ndarray] | None,
    solution: tuple[np.ndarray, np.ndarray] | None,
    label: str,
    errors: list[str],
    gates: list[str],
) -> float | None:
    aligned = _align(rhs, solution, errors, f"{label}: rhs/solution")
    if matrix is None or aligned is None:
        return None
    rhs_values, solution_values, rhs_keys = aligned
    matrix_keys = matrix["row_keys"].astype(str)
    if set(matrix_keys) != set(str(key) for key in rhs_keys) or matrix["rows"] != rhs_keys.size:
        errors.append(f"{label}: matrix and vector key sets differ")
        return None
    rhs_order = {str(key): index for index, key in enumerate(rhs_keys)}
    values = np.asarray([rhs_values[rhs_order[str(key)]] for key in matrix_keys], dtype=np.complex128)
    solution_order = {str(key): index for index, key in enumerate(rhs_keys)}
    solution_values = np.asarray([solution_values[solution_order[str(key)]] for key in matrix_keys], dtype=np.complex128)
    action = _csr_apply(matrix, solution_values)
    relative = _norm_ratio(rhs_values[np.asarray([rhs_order[str(key)] for key in matrix_keys])] - action, values)
    if not np.isfinite(relative) or relative > EXACT_LIMIT:
        gates.append(f"{label}: direct residual {relative} > {EXACT_LIMIT}")
    return relative


def check_record(record_path: Path, expected_source_sha: str | None = None) -> dict[str, Any]:
    record_path = Path(record_path).resolve()
    errors: list[str] = []
    gates: list[str] = []
    diagnostics: list[str] = []
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"passed": False, "contract_errors": [f"record JSON: {type(exc).__name__}"], "gate_failures": []}
    if not isinstance(record, dict):
        return {"passed": False, "contract_errors": ["record is not an object"], "gate_failures": []}
    raw_dir = _check_source_runtime(record, record_path, expected_source_sha, errors)
    _check_settings(record, errors)
    _check_fixture_audit(record, errors)
    production = record.get("production")
    if not isinstance(production, dict):
        errors.append("production: missing")
    else:
        audit = record.get("fixture_audit", {})
        hx_audit = audit.get("hx_audit", {}) if isinstance(audit, dict) else {}
        derived_forbidden = {
            "global_transfer_matrix": bool(audit.get("global_transfer_matrix", False) or hx_audit.get("global_transfer_matrix", False)),
            "global_numeric_allgather": bool(audit.get("global_numeric_allgather", False) or hx_audit.get("global_numeric_allgather", False)),
            "global_direct_coarse": bool(audit.get("global_direct_coarse", False) or hx_audit.get("global_direct_coarse", False)),
            "high_order_global_aij": bool(audit.get("high_order_global_aij", False) or hx_audit.get("high_order_global_aij", hx_audit.get("high_order_aij", False))),
        }
        for key in ("production_pc_direct_factor_applied", "ordinary_default_changed"):
            if production.get(key) is not False:
                errors.append(f"production.{key}: forbidden or missing")
        for key, expected in derived_forbidden.items():
            if production.get(key) is not expected:
                errors.append(f"production.{key}: does not match fixture/hx audit")
    artifacts = record.get("canonical_artifacts")
    loaded: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    if not isinstance(artifacts, dict):
        errors.append("canonical_artifacts: missing")
    elif raw_dir is not None:
        if set(artifacts) != ALL_ROLES:
            errors.append("canonical_artifacts: role set is incomplete or has extras")
        for role in sorted(artifacts):
            if artifacts[role].get("role") != _expected_role_kind(role):
                errors.append(f"canonical artifact {role}: semantic role mismatch")
            value = _load_role(raw_dir, role, artifacts[role], errors)
            if value is not None:
                loaded[role] = value
        component_hashes = record.get("component_hashes")
        if not isinstance(component_hashes, dict) or set(component_hashes) != set(artifacts):
            errors.append("component_hashes: role set mismatch")
        else:
            for role, descriptor in artifacts.items():
                keys_descriptor = descriptor.get("keys") if isinstance(descriptor, dict) else None
                values_descriptor = descriptor.get("values") if isinstance(descriptor, dict) else None
                actual = hashlib.sha256(_json_bytes({"keys_sha256": keys_descriptor.get("sha256") if isinstance(keys_descriptor, dict) else None, "values_sha256": values_descriptor.get("sha256") if isinstance(values_descriptor, dict) else None})).hexdigest()
                if component_hashes.get(role) != actual:
                    errors.append(f"component_hashes.{role}: mismatch")
    for left, right, limit, label in (
        ("source_before", "source_after", INPUT_LIMIT, "source input unchanged"),
        ("high_rhs", "high_rhs_repeat", REPEAT_LIMIT, "high RHS repeat"),
        ("e_input_before", "e_input_after", INPUT_LIMIT, "E input unchanged"),
        ("n_input_before", "n_input_after", INPUT_LIMIT, "N input unchanged"),
        ("e_output", "e_repeat", REPEAT_LIMIT, "E repeat"),
        ("n_output", "n_repeat", REPEAT_LIMIT, "N repeat"),
    ):
        aligned = _align(loaded.get(left), loaded.get(right), errors, label)
        if aligned is not None:
            relative = _relative(aligned[0], aligned[1])
            if not np.isfinite(relative) or relative > limit:
                gates.append(f"{label}: {relative} > {limit}")
    matrix_artifacts = record.get("matrix_artifacts")
    matrices: dict[str, dict[str, Any] | None] = {"edge": None, "node": None}
    if raw_dir is not None and isinstance(matrix_artifacts, dict):
        for name in matrices:
            matrices[name] = _load_matrix(raw_dir, matrix_artifacts.get(name), errors, name)
    else:
        errors.append("matrix_artifacts: missing")
    e_direct = _check_csr_direct(matrices["edge"], loaded.get("e_low_input_matrix"), loaded.get("e_low_solution_matrix"), "E exact edge", errors, gates)
    nodal_direct_relative: dict[str, float | None] = {}
    for name in NODAL_TRACE_NAMES:
        nodal_direct_relative[name] = _check_csr_direct(matrices["node"], loaded.get(f"n_{name}_rhs_matrix"), loaded.get(f"n_{name}_nodal_delta_matrix"), f"N exact nodal {name}", errors, gates)
    previous_result = None
    base_values = None
    if loaded.get("n_low_input") is not None:
        zero_keys, zero_values = loaded["n_low_input"]
        previous_result = (zero_keys, np.zeros_like(zero_values))
        base_values = zero_values
    previous_remaining = loaded.get("n_low_input")
    for name in TRACE_NAMES:
        result = loaded.get(f"n_{name}_result")
        remaining = loaded.get(f"n_{name}_remaining")
        delta = loaded.get(f"n_{name}_edge_delta")
        edge_action = loaded.get(f"n_{name}_edge_action")
        result_sum = _align(previous_result, delta, errors, f"N {name} result input")
        result_actual = _align(result, previous_result, errors, f"N {name} result keys")
        if result_sum is not None and result_actual is not None:
            expected_result = result_sum[0] + result_sum[1]
            result_values = result_actual[0]
            relative = _base_relative(result_values, expected_result, base_values)
            if not np.isfinite(relative) or relative > EXACT_LIMIT:
                gates.append(f"N {name} result composition: {relative} > {EXACT_LIMIT}")
        if name == "edge_jacobi_post":
            remaining_expected = previous_remaining
        else:
            remaining_pair = _align(previous_remaining, edge_action, errors, f"N {name} remaining input")
            remaining_expected = None if remaining_pair is None else (remaining_pair[2], remaining_pair[0] - remaining_pair[1])
        remaining_actual = _align(remaining, remaining_expected, errors, f"N {name} remaining identity")
        if remaining_actual is not None:
            relative = _base_relative(remaining_actual[0], remaining_actual[1], base_values)
            if not np.isfinite(relative) or relative > EXACT_LIMIT:
                gates.append(f"N {name} remaining update: {relative} > {EXACT_LIMIT}")
        previous_result = result
        previous_remaining = remaining
    route = record.get("route_audit")
    if not isinstance(route, dict) or route.get("high_to_lor_owner_route") is not True or route.get("lor_to_high_owner_route") is not True or route.get("owner_inventory_equal") is not True or route.get("orientation_consistent") is not True or route.get("phase_application") != "finalized_floquet_mpc_once" or route.get("slave_master_complete") is not True:
        errors.append("route_audit: owner/orientation/phase contract failed")
    else:
        if route.get("canonical_component_hashes") != record.get("component_hashes"):
            errors.append("route_audit: component hash inventory mismatch")
        low_names = ("e_low_input", "e_low_solution", "n_low_input")
        low_key_sets = [set(loaded[name][0].astype(str)) for name in low_names if name in loaded]
        low_values_finite = all(
            name in loaded and np.all(np.isfinite(loaded[name][1])) for name in low_names
        )
        owner_count = route.get("owner_count")
        derived_owner_route = (
            len(low_key_sets) == len(low_names)
            and bool(low_key_sets)
            and all(keys == low_key_sets[0] for keys in low_key_sets[1:])
            and isinstance(owner_count, int)
            and owner_count == len(low_key_sets[0])
            and low_values_finite
            and all(
                name in loaded and loaded[name][0].size > 0
                for name in ("high_rhs", "e_input_before", "n_input_before")
            )
        )
        if route.get("high_to_lor_owner_route") is not derived_owner_route or route.get("lor_to_high_owner_route") is not derived_owner_route or route.get("owner_inventory_equal") is not derived_owner_route:
            errors.append("route_audit: stored owner route does not match raw artifact inventory")
    reference_e = record.get("reference_e")
    reference_n = record.get("reference_n")
    e_outer, e_rho = _check_outer(reference_e.get("outer") if isinstance(reference_e, dict) else None, "reference_e", errors, diagnostics)
    n_outer, n_rho = _check_outer(reference_n.get("outer") if isinstance(reference_n, dict) else None, "reference_n", errors, diagnostics)
    for label, outer, final_action, final_residual in (
        ("E", e_outer, "e_final_action", "e_final_true_residual"),
        ("N", n_outer, "n_final_action", "n_final_true_residual"),
    ):
        if outer is None:
            continue
        aligned = _align(loaded.get("high_rhs"), loaded.get(final_action), errors, f"{label} final RHS/action")
        residual_aligned = _align(loaded.get("high_rhs"), loaded.get(final_residual), errors, f"{label} final RHS/residual")
        if aligned is not None and residual_aligned is not None:
            rhs_values, action_values, _ = aligned
            residual_values = residual_aligned[1]
            algebraic = rhs_values - action_values
            algebraic_relative = _norm_ratio(algebraic - residual_values, rhs_values)
            if not np.isfinite(algebraic_relative) or algebraic_relative > EXACT_LIMIT:
                gates.append(f"{label} final residual algebra: {algebraic_relative} > {EXACT_LIMIT}")
            rho = _norm_ratio(residual_values, rhs_values)
            if label == "E" and (not np.isfinite(rho) or rho > RESIDUAL_LIMIT):
                gates.append(f"E final true residual rho {rho} > {RESIDUAL_LIMIT}")
            if label == "N" and np.isfinite(rho):
                diagnostics.append(f"N final true residual diagnostic rho={rho}")
            if not np.isclose(rho, float(outer.get("final_true_residual", np.nan)), rtol=1.0e-12, atol=1.0e-14):
                errors.append(f"{label} outer final residual scalar disagrees with raw rho")
    for label, reference, expected_count, outer in (
        ("E", reference_e, 2 + int(e_outer.get("pc_apply_count", 0)) if e_outer else -1, e_outer),
        ("N", reference_n, 8 + 4 * int(n_outer.get("pc_apply_count", 0)) if n_outer else -1, n_outer),
    ):
        if not isinstance(reference, dict):
            errors.append(f"reference_{label.lower()}: missing")
            continue
        if not np.isfinite(float(reference.get("repeat_relative", np.nan))) or float(reference.get("repeat_relative", np.inf)) > REPEAT_LIMIT:
            gates.append(f"{label} stored repeat exceeds limit")
        if not np.isfinite(float(reference.get("input_unchanged_relative", np.nan))) or float(reference.get("input_unchanged_relative", np.inf)) > INPUT_LIMIT:
            gates.append(f"{label} stored input unchanged exceeds limit")
        if reference.get("finite") is not True:
            gates.append(f"{label} one-apply finite=false")
        if int(reference.get("direct_solve_count", -1)) != expected_count:
            errors.append(f"{label} direct factor solve count does not match current-input applications")
        constraint_value = reference.get("primal_constraint_absolute")
        if not isinstance(constraint_value, (int, float)) or not np.isfinite(float(constraint_value)) or float(constraint_value) > EXACT_LIMIT:
            gates.append(f"{label} stored primal constraint exceeds limit")
    if isinstance(reference_n, dict) and reference_n.get("component_trace_names") != list(TRACE_NAMES):
        errors.append("N component trace order is not frozen sequential-v1")
    if isinstance(reference_e, dict) and "component_trace_names" in reference_e:
        errors.append("E must not claim multiplicative component traces")
    rank_facts = record.get("rank_facts")
    if not isinstance(rank_facts, list) or len(rank_facts) != 1 or not isinstance(rank_facts[0], dict) or rank_facts[0].get("rank") != 0:
        errors.append("rank_facts: MPI1 rank fact missing")
    elif isinstance(reference_e, dict) and isinstance(reference_n, dict):
        rank = rank_facts[0]
        if rank.get("runtime") != record.get("runtime"):
            errors.append("rank_facts.runtime: does not match record runtime")
        for key, reference, label in (("e_repeat_relative", reference_e, "E"), ("n_repeat_relative", reference_n, "N")):
            if not np.isclose(float(rank.get(key, np.nan)), float(reference.get("repeat_relative", np.nan)), rtol=0.0, atol=0.0):
                errors.append(f"rank_facts.{key}: does not match reference facts")
        for key, reference, label in (("e_input_unchanged_relative", reference_e, "E"), ("n_input_unchanged_relative", reference_n, "N")):
            if not np.isclose(float(rank.get(key, np.nan)), float(reference.get("input_unchanged_relative", np.nan)), rtol=0.0, atol=0.0):
                errors.append(f"rank_facts.{key}: does not match reference facts")
        if int(rank.get("edge_direct_solve_count", -1)) != int(reference_e.get("direct_solve_count", -2)) or int(rank.get("nodal_direct_solve_count", -1)) != int(reference_n.get("direct_solve_count", -2)):
            errors.append("rank_facts: direct solve counts disagree")
    for role in ("e_output_constraint", "e_repeat_constraint", "n_output_constraint", "n_repeat_constraint", "e_final_constraint", "n_final_constraint"):
        packet = loaded.get(role)
        if packet is None:
            continue
        keys, values = packet
        constraint_rows = record.get("primal_constraint_rows")
        if not isinstance(constraint_rows, list) or any(not isinstance(row, int) for row in constraint_rows):
            errors.append("primal_constraint_rows: missing or invalid")
            constraint_rows = []
        expected_keys = {f"high-slave:{row}" for row in constraint_rows}
        if set(keys.astype(str)) != expected_keys:
            errors.append(f"{role}: slave row key set mismatch")
        maximum = float(np.max(np.abs(values))) if values.size else 0.0
        if not np.isfinite(maximum) or maximum > EXACT_LIMIT:
            gates.append(f"{role}: primal slave constraint {maximum} > {EXACT_LIMIT}")
    if e_direct is not None and isinstance(reference_e, dict):
        stored = reference_e.get("direct_edge", {}).get("relative_residual")
        if not np.isclose(float(stored), e_direct, rtol=1.0e-12, atol=1.0e-14):
            errors.append("E direct residual fact disagrees with CSR recomputation")
    if isinstance(reference_n, dict):
        direct_facts = {fact.get("name"): fact for fact in reference_n.get("nodal_direct", []) if isinstance(fact, dict)}
        if set(direct_facts) != set(NODAL_TRACE_NAMES):
            errors.append("N direct nodal fact names are incomplete")
        for name in NODAL_TRACE_NAMES:
            relative = nodal_direct_relative.get(name)
            if name in direct_facts and relative is not None and not np.isclose(float(direct_facts[name].get("relative_residual", np.nan)), relative, rtol=1.0e-12, atol=1.0e-14):
                errors.append(f"N direct residual fact {name} disagrees with CSR recomputation")
    passed = not errors and not gates
    return {
        "schema": SCHEMA,
        "record": str(record_path),
        "passed": passed,
        "contract_errors": errors,
        "gate_failures": gates,
        "diagnostics": diagnostics,
        "reference_e_final_rho": e_rho,
        "reference_n_final_rho": n_rho,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--expected-source-sha")
    args = parser.parse_args(argv)
    if args.record is None or args.output is None:
        parser.error("--record and --output are required")
    result = check_record(args.record, args.expected_source_sha)
    args.output.write_bytes(_json_bytes(result))
    print(json.dumps(result, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
