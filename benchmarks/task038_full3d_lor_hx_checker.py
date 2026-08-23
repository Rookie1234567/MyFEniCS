"""Read-only checker for the thin L1 LOR/HX oracle records.

This checker deliberately does not import the runner, transfer solver, MPI,
PETSc, or DOLFINx.  It reassembles the bounded local identities from raw
arrays and, for the p2/p3 periodic cases, compares the measured owner-local
canonical packets across MPI1 and MPI2.  The p6 frozen case is a local
single-cell oracle and records the periodic packet stage as not applicable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any

import numpy as np
from scipy.linalg import eigvalsh


SCHEMA = "task038.lor-native-complex-hx.l1-record.v1"
CHECKER_SCHEMA = "task038.lor-native-complex-hx.l1-check.v1"
BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"
TRANSFER_LIMIT = 1.0e-12
REPEAT_LIMIT = 1.0e-13
SPECTRAL_LIMIT = 100.0
HERMITIAN_LIMIT = 1.0e-12
SHA40 = re.compile(r"^[0-9a-f]{40}$")
L2_SCHEMA = "task038.lor-native-complex-hx.l2-record.v1"
L2_CHECKER_SCHEMA = "task038.lor-native-complex-hx.l2-check.v1"
L2_CASE_ORDER = ("p2-mpi1", "p2-mpi2", "p3-mpi1", "p3-mpi2")
L2_SOURCE_NAMES = ("random", "gradient", "curl", "checkerboard")
L2_SOURCE_FORMULAS = {
    "random": (
        "analytic deterministic pseudo-random edge field from fixed "
        "noninteger trigonometric frequencies and phases"
    ),
    "gradient": "grad(sin(2*pi*sx)*sin(2*pi*sy)*sin(2*pi*sz))",
    "curl": "curl((0,0,sin(2*pi*sx)*sin(2*pi*sy)*sin(2*pi*sz)))",
    "checkerboard": (
        "R4 fixed 8-cycle field: "
        "(high_x*high_y*high_z, high_y*high_z, high_z*high_x)"
    ),
}
L2_PHASE_APPLICATION = "algebraic_slave_zero_action_internal_finalized_mpc_once"
L2_RHO_LIMITS = {
    "random": 0.45,
    "gradient": 0.25,
    "curl": 0.45,
    "checkerboard": 0.60,
}
L2_CG_KSP_TYPE = "cg"
L2_CG_RTOL = 1.0e-8
L2_CG_MAX_IT = 40
L2_REPEAT_LIMIT = 1.0e-13
L2_CANONICAL_LIMIT = 1.0e-12
L2_CG_TRUE_RESIDUAL_LIMIT = 1.0e-8
REQUIRED_ARRAYS = {
    "nodes",
    "high_to_lor",
    "lor_to_high",
    "high_matrix",
    "lor_matrix",
    "h1_transfer",
    "high_gradient_edge",
    "high_curl_face",
    "lor_gradient",
    "lor_curl_incidence",
    "probe",
    "local_probe_forward_1",
    "local_probe_forward_2",
    "local_probe_roundtrip",
    "reference_probe_forward_1",
    "reference_probe_forward_2",
    "reference_probe_inverse_1",
    "reference_probe_inverse_2",
}
REQUIRED_ARRAYS.update(
    {
        f"reference_group_{axis}"
        for axis in range(3)
    }
    | {
        f"reference_forward_tensor_{axis}"
        for axis in range(3)
    }
    | {
        f"reference_inverse_tensor_{axis}"
        for axis in range(3)
    }
)
CANONICAL_ARRAYS = {
    "canonical_source_keys",
    "canonical_source_values",
    "canonical_mapped_source_keys",
    "canonical_mapped_source_values",
    "canonical_action_keys",
    "canonical_action_values",
    "canonical_mapped_action_keys",
    "canonical_mapped_action_values",
    "canonical_repeat_keys",
    "canonical_repeat_values",
    "canonical_lor_keys",
    "canonical_lor_values",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _relative(left: np.ndarray, right: np.ndarray) -> float:
    left = np.asarray(left)
    right = np.asarray(right)
    return float(np.linalg.norm(left - right) / max(np.linalg.norm(right), 1.0e-300))


def _finite(array: np.ndarray) -> bool:
    array = np.asarray(array)
    if array.dtype.kind in "OUS":
        return True
    return bool(np.all(np.isfinite(array)))


def _artifact_path(raw_dir: Path, descriptor: dict[str, Any]) -> Path:
    path = (raw_dir / str(descriptor["relative_path"])).resolve()
    if raw_dir.resolve() not in path.parents:
        raise ValueError("artifact escapes raw directory")
    return path


def _read_artifacts(
    record: dict[str, Any], required_names: set[str] | None = None
) -> tuple[dict[str, np.ndarray], list[str]]:
    raw_dir = Path(str(record["raw_dir"])).resolve()
    descriptors = record.get("artifacts")
    if not isinstance(descriptors, list):
        return {}, ["artifacts list is missing"]
    by_name: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for descriptor in descriptors:
        if not isinstance(descriptor, dict) or not isinstance(descriptor.get("name"), str):
            errors.append("malformed artifact descriptor")
            continue
        name = descriptor["name"]
        if name in by_name:
            errors.append(f"duplicate artifact {name}")
        by_name[name] = descriptor
    required = set(REQUIRED_ARRAYS) if required_names is None else set(required_names)
    if required_names is None and int(record.get("degree", -1)) in {2, 3}:
        required.update(CANONICAL_ARRAYS)
    missing = required - set(by_name)
    errors.extend(f"missing artifact {name}" for name in sorted(missing))
    arrays: dict[str, np.ndarray] = {}
    for name, descriptor in by_name.items():
        try:
            path = _artifact_path(raw_dir, descriptor)
            if not path.is_file():
                raise ValueError("file is missing")
            if path.stat().st_size != int(descriptor["bytes"]):
                raise ValueError("byte count mismatch")
            if _sha256(path) != descriptor["sha256"]:
                raise ValueError("SHA256 mismatch")
            array = np.load(path, allow_pickle=False, mmap_mode="r")
            if str(array.dtype) != descriptor["dtype"]:
                raise ValueError("dtype mismatch")
            if list(array.shape) != list(descriptor["shape"]):
                raise ValueError("shape mismatch")
            if not _finite(array):
                raise ValueError("non-finite values")
            arrays[name] = np.asarray(array)
        except Exception as exc:
            errors.append(f"artifact {name}: {type(exc).__name__}: {exc}")
    return arrays, errors


def _identity_errors(record: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    expected_cases = {
        "p2-mpi1": (2, 1),
        "p2-mpi2": (2, 2),
        "p3-mpi1": (3, 1),
        "p3-mpi2": (3, 2),
        "p6-mpi1": (6, 1),
    }
    if record.get("schema") != SCHEMA or record.get("stage") != "l1":
        errors.append("record schema/stage mismatch")
    case = record.get("case")
    degree = record.get("degree")
    mpi_size = record.get("mpi_size")
    if not isinstance(case, str) or case not in expected_cases:
        errors.append("case identity is invalid")
    if case in expected_cases and (degree, mpi_size) != expected_cases[case]:
        errors.append("degree/MPI identity is invalid")
    source = record.get("source")
    if not isinstance(source, dict):
        errors.append("source identity is missing")
    else:
        expected = source.get("expected_sha")
        if not isinstance(expected, str) or not SHA40.fullmatch(expected):
            errors.append("expected source SHA is not lowercase 40-hex")
        if source.get("commit_sha_start") != expected or source.get("commit_sha_end") != expected:
            errors.append("source SHA is not closed at both boundaries")
        if source.get("branch") != BRANCH:
            errors.append("source branch mismatch")
        if source.get("clean_start") is not True or source.get("clean_end") is not True:
            errors.append("source was not clean at both boundaries")
    runtime = record.get("runtime")
    if not isinstance(runtime, dict):
        errors.append("runtime identity is missing")
    else:
        if runtime.get("qualified_activation") != "1":
            errors.append("qualified activation is not 1")
        if runtime.get("mpi_size") != mpi_size:
            errors.append("runtime MPI size mismatch")
        if runtime.get("petsc_scalar_type") != "complex128" or runtime.get("petsc_int_type") != "int32":
            errors.append("PETSc ABI identity mismatch")
        executable = str(runtime.get("sys_executable", ""))
        if "/.venv/" not in executable or "/mnt/c/" in executable:
            errors.append("runtime executable is not the qualified Linux .venv")
    rank_facts = record.get("rank_facts")
    if not isinstance(rank_facts, list) or len(rank_facts) != mpi_size:
        errors.append("rank_facts count does not equal record MPI size")
    else:
        rank_ids = [fact.get("rank") if isinstance(fact, dict) else None for fact in rank_facts]
        if any(not isinstance(rank, int) for rank in rank_ids) or sorted(rank_ids) != list(range(int(mpi_size))):
            errors.append("rank_facts rank IDs are not the complete MPI rank set")
        for fact in rank_facts:
            fact_runtime = fact.get("runtime") if isinstance(fact, dict) else None
            if not isinstance(fact_runtime, dict):
                errors.append("rank fact runtime identity is missing")
                continue
            if fact_runtime.get("qualified_activation") != "1":
                errors.append("rank fact qualified activation is not 1")
            if fact_runtime.get("mpi_size") != mpi_size:
                errors.append("rank fact MPI size mismatch")
            if fact_runtime.get("petsc_scalar_type") != "complex128" or fact_runtime.get("petsc_int_type") != "int32":
                errors.append("rank fact PETSc ABI identity mismatch")
            fact_executable = str(fact_runtime.get("sys_executable", ""))
            if "/.venv/" not in fact_executable or "/mnt/c/" in fact_executable:
                errors.append("rank fact executable is not the qualified Linux .venv")
    forbidden = record.get("forbidden")
    required_forbidden = (
        "global_numeric_allgather",
        "global_aij_in_production",
        "global_schur",
        "global_direct_coarse",
        "per_rank_full_basis_replication",
        "production_dense_transfer",
    )
    if not isinstance(forbidden, dict) or any(forbidden.get(key) is not False for key in required_forbidden):
        errors.append("forbidden production materialization audit is not explicitly false")
    production = record.get("production")
    required_production = {
        "global_transfer_matrix": False,
        "local_tensor_action": True,
        "owner_local_maps": True,
        "numeric_allgather": False,
    }
    if not isinstance(production, dict):
        errors.append("production contract is missing")
    else:
        for key, expected in required_production.items():
            if production.get(key) is not expected:
                errors.append(f"production {key} is not exactly {expected}")
        if production.get("retained_dense_transfer_bytes") != 0 or production.get("local_dense_oracle_only") is not True:
            errors.append("dense oracle/retained production boundary is not closed")
    if case in {"p2-mpi1", "p2-mpi2", "p3-mpi1", "p3-mpi2"}:
        canonical = record.get("canonical_mpi_identity")
        audit = canonical.get("audit") if isinstance(canonical, dict) else None
        topology = audit.get("topology_audit") if isinstance(audit, dict) else None
        required_topology = {
            "owner_local_maps": True,
            "global_transfer_matrix": False,
            "numeric_allgather": False,
            "phase_application": "once_in_canonical_owner_route",
            "edge_orientation": "dolfinx_cell_permutation_Tt_then_T",
            "cell_permutation": "Tt_before_high_to_lor_and_T_after_lor_to_high",
            "mpc_slave_master": "finalized_mpc_homogenize_backsubstitution",
            "floquet_phase": "complete_slave_edge_mapped_to_master_once",
            "slave_master_complete": True,
        }
        if not isinstance(topology, dict):
            errors.append("periodic topology audit is missing")
        else:
            for key, expected in required_topology.items():
                if topology.get(key) != expected:
                    errors.append(f"periodic topology {key} is not exactly {expected}")
    return errors


def _check_local_algebra(record: dict[str, Any], arrays: dict[str, np.ndarray]) -> dict[str, Any]:
    errors: list[str] = []
    degree = int(record["degree"])
    edge_count = 3 * degree * (degree + 1) ** 2
    forward = arrays["high_to_lor"]
    inverse = arrays["lor_to_high"]
    if forward.shape != (edge_count, edge_count) or inverse.shape != forward.shape:
        return {"errors": ["local transfer matrix shape is not the fixed bounded cell dimension"]}
    probe = np.arange(edge_count, dtype=np.float64) + 1j
    if not np.array_equal(arrays["probe"], probe):
        errors.append("deterministic probe mismatch")
    observed = forward @ probe
    if not np.array_equal(arrays["local_probe_forward_1"], observed) or not np.array_equal(
        arrays["local_probe_forward_2"], observed
    ):
        errors.append("local repeated action facts do not close")
    roundtrip = inverse @ observed
    forward_identity = _relative(roundtrip, probe)
    lor_identity = _relative(forward @ roundtrip, observed)
    if forward_identity > TRANSFER_LIMIT or lor_identity > TRANSFER_LIMIT:
        errors.append(f"local identity exceeds {TRANSFER_LIMIT}: {forward_identity}, {lor_identity}")
    if not np.array_equal(arrays["local_probe_roundtrip"], roundtrip):
        errors.append("local roundtrip artifact mismatch")
    high_matrix = arrays["high_matrix"]
    lor_matrix = arrays["lor_matrix"]
    high_hermitian = _relative(high_matrix, high_matrix.conj().T)
    lor_hermitian = _relative(lor_matrix, lor_matrix.conj().T)
    algebra_metrics = {
        "high_matrix_hermitian_relative": high_hermitian,
        "lor_matrix_hermitian_relative": lor_hermitian,
    }
    if (
        not _finite(high_matrix)
        or not _finite(lor_matrix)
        or not np.isfinite(high_hermitian)
        or not np.isfinite(lor_hermitian)
        or high_hermitian > HERMITIAN_LIMIT
        or lor_hermitian > HERMITIAN_LIMIT
    ):
        errors.append(
            "local Hermitian/SPD prerequisite fails: "
            f"high={high_hermitian}, lor={lor_hermitian}, limit={HERMITIAN_LIMIT}"
        )
        return {"errors": errors, **algebra_metrics}
    pulled_lor = forward.conj().T @ lor_matrix @ forward
    if not _finite(pulled_lor):
        errors.append("pulled local mass matrix is non-finite before eigvalsh")
        return {"errors": errors, **algebra_metrics}
    eigenvalues = eigvalsh(high_matrix, pulled_lor)
    if not np.all(np.isfinite(eigenvalues)) or eigenvalues[0] <= 0.0:
        errors.append("local generalized spectrum is not finite positive")
    condition = float(eigenvalues[-1] / eigenvalues[0])
    if condition > SPECTRAL_LIMIT:
        errors.append(f"spectral condition {condition} exceeds {SPECTRAL_LIMIT}")
    # The worker stores the already reconstructed high-space gradient.  The
    # independent checker must not apply the inverse transfer a second time.
    high_gradient = arrays["high_gradient_edge"]
    gradient = _relative(
        forward @ high_gradient, arrays["lor_gradient"] @ arrays["h1_transfer"]
    )
    curl_incidence = float(
        np.linalg.norm(arrays["lor_curl_incidence"] @ arrays["lor_gradient"])
        / max(np.linalg.norm(arrays["lor_gradient"]), 1.0)
    )
    curl_transferred = float(
        np.linalg.norm(arrays["lor_curl_incidence"] @ forward @ high_gradient)
        / max(np.linalg.norm(forward @ high_gradient), 1.0)
    )
    curl_face = _relative(
        arrays["lor_curl_incidence"] @ forward, arrays["high_curl_face"]
    )
    for name, value in {
        "gradient": gradient,
        "curl_incidence": curl_incidence,
        "curl_transferred_gradient": curl_transferred,
        "curl_face": curl_face,
    }.items():
        if value > TRANSFER_LIMIT:
            errors.append(f"{name} commuting error {value} exceeds {TRANSFER_LIMIT}")
    return {
        "errors": errors,
        "high_to_lor_identity_relative": forward_identity,
        "lor_to_high_identity_relative": lor_identity,
        **algebra_metrics,
        "spectral_lambda_min": float(eigenvalues[0]),
        "spectral_lambda_max": float(eigenvalues[-1]),
        "spectral_condition": condition,
        "de_rham_gradient_commuting_relative": gradient,
        "curl_incidence_relative": curl_incidence,
        "curl_transferred_gradient_relative": curl_transferred,
        "curl_face_commuting_relative": curl_face,
    }


def _canonical_series(
    arrays: dict[str, np.ndarray], key_name: str, value_name: str
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    errors: list[str] = []
    keys = np.asarray(arrays[key_name])
    values = np.asarray(arrays[value_name])
    if keys.ndim != 1 or keys.dtype.kind not in "SU":
        errors.append(f"{key_name} is not a one-dimensional string key sequence")
    if values.ndim != 1 or values.dtype != np.dtype(np.complex128):
        errors.append(f"{value_name} is not a complex128 vector")
    if keys.ndim == 1 and values.ndim == 1 and keys.size != values.size:
        errors.append(f"{key_name}/{value_name} length mismatch")
    if keys.ndim == 1:
        key_list = [str(key) for key in keys.tolist()]
        if key_list != sorted(key_list) or len(set(key_list)) != len(key_list):
            errors.append(f"{key_name} is not unique and sorted")
        if any(not SHA256_HEX.fullmatch(key) for key in key_list):
            errors.append(f"{key_name} contains a non-SHA256 key")
    if values.ndim == 1 and not _finite(values):
        errors.append(f"{value_name} contains non-finite values")
    return keys, values, errors


def _canonical_identity(record: dict[str, Any], arrays: dict[str, np.ndarray]) -> dict[str, Any]:
    errors: list[str] = []
    series_names = (
        ("source", "canonical_source_keys", "canonical_source_values"),
        ("mapped_source", "canonical_mapped_source_keys", "canonical_mapped_source_values"),
        ("action", "canonical_action_keys", "canonical_action_values"),
        ("mapped_action", "canonical_mapped_action_keys", "canonical_mapped_action_values"),
        ("repeat", "canonical_repeat_keys", "canonical_repeat_values"),
    )
    series: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for label, key_name, value_name in series_names:
        keys, values, local_errors = _canonical_series(arrays, key_name, value_name)
        errors.extend(local_errors)
        series[label] = (keys, values)
    lor_keys = np.asarray(arrays["canonical_lor_keys"])
    lor_values = np.asarray(arrays["canonical_lor_values"])
    if lor_keys.ndim != 1 or lor_keys.dtype != np.dtype(np.uint32):
        errors.append("canonical LOR keys are not a uint32 sequence")
    if lor_values.ndim != 1 or lor_values.dtype != np.dtype(np.complex128):
        errors.append("canonical LOR values are not a complex128 vector")
    if lor_keys.ndim == 1 and lor_values.ndim == 1 and lor_keys.size != lor_values.size:
        errors.append("canonical LOR key/value length mismatch")
    if lor_keys.ndim == 1 and (
        not np.array_equal(lor_keys, np.unique(lor_keys))
    ):
        errors.append("canonical LOR keys are not unique and sorted")
    if lor_values.ndim == 1 and not _finite(lor_values):
        errors.append("canonical LOR values are non-finite")
    source_keys = series["source"][0]
    metrics: dict[str, float] = {}
    if not np.array_equal(source_keys, series["mapped_source"][0]):
        errors.append("canonical source/mapped-source key sets differ")
    action_keys = series["action"][0]
    for label in ("mapped_action", "repeat"):
        if not np.array_equal(action_keys, series[label][0]):
            errors.append(f"canonical action key set differs for {label}")
    if not errors:
        source_values = series["source"][1]
        metrics["source_mapped_relative"] = _relative(
            series["mapped_source"][1], source_values
        )
        metrics["action_mapped_relative"] = _relative(
            series["mapped_action"][1], series["action"][1]
        )
        metrics["action_repeat_relative"] = _relative(
            series["repeat"][1], series["mapped_action"][1]
        )
        if metrics["source_mapped_relative"] > TRANSFER_LIMIT:
            errors.append("canonical source/mapped-source identity exceeds 1e-12")
        if metrics["action_mapped_relative"] > TRANSFER_LIMIT:
            errors.append("canonical action/mapped-action identity exceeds 1e-12")
        if metrics["action_repeat_relative"] > REPEAT_LIMIT:
            errors.append("canonical action repeat exceeds 1e-13")
    canonical = record.get("canonical_mpi_identity")
    if not isinstance(canonical, dict) or canonical.get("status") != "measured":
        errors.append("p2/p3 canonical owner-local identity is not measured")
    elif canonical.get("production_numeric_allgather") is not False:
        errors.append("production numeric_allgather is not explicitly false")
    return {
        "errors": errors,
        **metrics,
        "canonical_packet_count": int(source_keys.size) if source_keys.ndim == 1 else 0,
        "canonical_lor_count": int(lor_keys.size) if lor_keys.ndim == 1 else 0,
    }


SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")


def _packed_apply(
    vectors: np.ndarray, groups: list[np.ndarray], tensors: list[np.ndarray], degree: int, inverse: bool
) -> np.ndarray:
    batch = np.asarray(vectors, dtype=np.complex128)
    result = np.empty_like(batch)
    block_size = degree * (degree + 1) ** 2
    if inverse:
        for axis, (rows, tensor) in enumerate(zip(groups, tensors, strict=True)):
            block = batch[:, axis * block_size : (axis + 1) * block_size]
            result[:, rows] = np.einsum(
                "bijk,hijk->bh",
                block.reshape((batch.shape[0],) + tuple(tensor.shape[1:])),
                tensor,
                optimize=True,
            )
    else:
        for axis, (columns, tensor) in enumerate(zip(groups, tensors, strict=True)):
            result[:, axis * block_size : (axis + 1) * block_size] = np.einsum(
                "bh,hijk->bijk",
                batch[:, columns],
                tensor,
                optimize=True,
            ).reshape(batch.shape[0], block_size)
    return result


def _check_reference_factor(record: dict[str, Any], arrays: dict[str, np.ndarray]) -> dict[str, Any]:
    errors: list[str] = []
    degree = int(record["degree"])
    edge_count = 3 * degree * (degree + 1) ** 2
    block_size = degree * (degree + 1) ** 2
    groups = [arrays[f"reference_group_{axis}"] for axis in range(3)]
    forward_tensors = [arrays[f"reference_forward_tensor_{axis}"] for axis in range(3)]
    inverse_tensors = [arrays[f"reference_inverse_tensor_{axis}"] for axis in range(3)]
    forward = np.zeros((edge_count, edge_count), dtype=np.complex128)
    inverse = np.zeros_like(forward)
    for axis, (group, forward_tensor, inverse_tensor) in enumerate(
        zip(groups, forward_tensors, inverse_tensors, strict=True)
    ):
        shape = (degree, degree + 1, degree + 1) if axis == 0 else (
            (degree + 1, degree, degree + 1) if axis == 1 else (degree + 1, degree + 1, degree)
        )
        expected_shape = (block_size,) + shape
        if tuple(forward_tensor.shape) != expected_shape or tuple(inverse_tensor.shape) != expected_shape:
            errors.append(f"reference tensor shape mismatch on axis {axis}")
            continue
        if group.shape != (block_size,) or np.unique(group).size != block_size:
            errors.append(f"reference group mismatch on axis {axis}")
            continue
        row_start = axis * block_size
        row_end = (axis + 1) * block_size
        rows = np.arange(row_start, row_end, dtype=np.int64)
        forward[np.ix_(rows, group)] = forward_tensor.reshape(block_size, block_size).T
        inverse[np.ix_(group, rows)] = inverse_tensor.reshape(block_size, block_size)
    dense_forward = arrays["high_to_lor"]
    dense_inverse = arrays["lor_to_high"]
    packed_forward_relative = _relative(forward, dense_forward)
    packed_inverse_relative = _relative(inverse, dense_inverse)
    probe = arrays["probe"]
    batch = np.repeat(probe[None, :], 32, axis=0)
    packed_batch = _packed_apply(batch, groups, forward_tensors, degree, False)
    packed_inverse_batch = _packed_apply(packed_batch, groups, inverse_tensors, degree, True)
    expected_batch = np.repeat((dense_forward @ probe)[None, :], 32, axis=0)
    expected_inverse_batch = np.repeat((dense_inverse @ (dense_forward @ probe))[None, :], 32, axis=0)
    batch_forward_relative = _relative(packed_batch, expected_batch)
    batch_inverse_relative = _relative(packed_inverse_batch, expected_inverse_batch)
    repeat_forward = _relative(arrays["reference_probe_forward_1"], arrays["reference_probe_forward_2"])
    repeat_inverse = _relative(arrays["reference_probe_inverse_1"], arrays["reference_probe_inverse_2"])
    if max(packed_forward_relative, packed_inverse_relative, batch_forward_relative, batch_inverse_relative) > TRANSFER_LIMIT:
        errors.append("packed reference action exceeds 1e-12")
    if repeat_forward > REPEAT_LIMIT or repeat_inverse > REPEAT_LIMIT:
        errors.append("packed reference repeat exceeds 1e-13")
    numeric_bytes = int(sum(array.nbytes for array in (*forward_tensors, *inverse_tensors)))
    retained_dense = record.get("production", {}).get("retained_dense_transfer_bytes")
    if retained_dense != 0:
        errors.append("retained dense transfer is not zero")
    return {
        "errors": errors,
        "packed_forward_relative": packed_forward_relative,
        "packed_inverse_relative": packed_inverse_relative,
        "batch_forward_relative": batch_forward_relative,
        "batch_inverse_relative": batch_inverse_relative,
        "repeat_forward_relative": repeat_forward,
        "repeat_inverse_relative": repeat_inverse,
        "tensor_numeric_bytes_recomputed": numeric_bytes,
        "retained_dense_transfer_bytes": retained_dense,
    }


def check_record(record_path: Path) -> dict[str, Any]:
    try:
        raw_record_sha256 = _sha256(record_path)
    except Exception:
        raw_record_sha256 = None
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "record": str(record_path),
            "raw_record_sha256": raw_record_sha256,
            "source_sha": None,
            "passed": False,
            "errors": [f"record parse: {exc}"],
        }
    source = record.get("source")
    source_sha = source.get("expected_sha") if isinstance(source, dict) else None
    try:
        errors = _identity_errors(record)
    except Exception as exc:
        errors = [f"identity validation: {type(exc).__name__}: {exc}"]
    try:
        arrays, artifact_errors = _read_artifacts(record)
    except Exception as exc:
        arrays, artifact_errors = {}, [f"artifact validation: {type(exc).__name__}: {exc}"]
    errors.extend(artifact_errors)
    local = {"errors": ["local facts not checked because artifacts are incomplete"]}
    reference = {"errors": ["reference facts not checked because artifacts are incomplete"]}
    if not artifact_errors:
        try:
            local = _check_local_algebra(record, arrays)
            reference = _check_reference_factor(record, arrays)
            errors.extend(local["errors"])
            errors.extend(reference["errors"])
        except Exception as exc:
            errors.append(f"raw algebra validation: {type(exc).__name__}: {exc}")
    canonical = record.get("canonical_mpi_identity")
    canonical_result = {"errors": ["canonical facts not checked because artifacts are incomplete"]}
    degree = record.get("degree")
    if isinstance(degree, int) and degree in {2, 3}:
        if not artifact_errors:
            try:
                canonical_result = _canonical_identity(record, arrays)
                errors.extend(canonical_result["errors"])
            except Exception as exc:
                errors.append(
                    f"canonical packet validation: {type(exc).__name__}: {exc}"
                )
    elif record.get("case") == "p6-mpi1":
        if not isinstance(canonical, dict) or canonical.get("status") != "not_applicable_by_frozen_case":
            errors.append("p6-mpi1 canonical identity must be not_applicable_by_frozen_case")
    else:
        errors.append("canonical case boundary is invalid")
    return {
        "record": str(record_path),
        "raw_record_sha256": raw_record_sha256,
        "source_sha": source_sha,
        "case": record.get("case"),
        "degree": record.get("degree"),
        "mpi_size": record.get("mpi_size"),
        "passed": not errors,
        "errors": errors,
        "local": {key: value for key, value in local.items() if key != "errors"},
        "reference": {key: value for key, value in reference.items() if key != "errors"},
        "canonical": {
            key: value for key, value in canonical_result.items() if key != "errors"
        },
        "canonical_mpi_identity": canonical,
    }


def _compare_canonical_records(left_path: Path, right_path: Path) -> tuple[dict[str, float], list[str]]:
    left_record = json.loads(left_path.read_text(encoding="utf-8"))
    right_record = json.loads(right_path.read_text(encoding="utf-8"))
    left_arrays, left_errors = _read_artifacts(left_record, CANONICAL_ARRAYS)
    right_arrays, right_errors = _read_artifacts(right_record, CANONICAL_ARRAYS)
    errors = [f"left canonical artifacts: {error}" for error in left_errors]
    errors.extend(f"right canonical artifacts: {error}" for error in right_errors)
    metrics: dict[str, float] = {}
    pairs = (
        ("source", "canonical_source_keys", "canonical_source_values"),
        ("mapped_source", "canonical_mapped_source_keys", "canonical_mapped_source_values"),
        ("action", "canonical_action_keys", "canonical_action_values"),
        ("mapped_action", "canonical_mapped_action_keys", "canonical_mapped_action_values"),
        ("repeat", "canonical_repeat_keys", "canonical_repeat_values"),
    )
    for label, key_name, value_name in pairs:
        if left_errors or right_errors:
            continue
        left_keys, left_values, local_left_errors = _canonical_series(
            left_arrays, key_name, value_name
        )
        right_keys, right_values, local_right_errors = _canonical_series(
            right_arrays, key_name, value_name
        )
        errors.extend(f"left {label}: {error}" for error in local_left_errors)
        errors.extend(f"right {label}: {error}" for error in local_right_errors)
        if local_left_errors or local_right_errors:
            continue
        if not np.array_equal(left_keys, right_keys):
            errors.append(f"{label} canonical MPI key sets differ")
            continue
        value = _relative(left_values, right_values)
        metrics[f"{label}_mpi_relative"] = value
        limit = REPEAT_LIMIT if label == "repeat" else TRANSFER_LIMIT
        if value > limit:
            errors.append(f"{label} canonical MPI relative {value} exceeds {limit}")
    if not left_errors and not right_errors:
        left_keys = np.asarray(left_arrays["canonical_lor_keys"])
        right_keys = np.asarray(right_arrays["canonical_lor_keys"])
        left_values = np.asarray(left_arrays["canonical_lor_values"])
        right_values = np.asarray(right_arrays["canonical_lor_values"])
        if not np.array_equal(left_keys, right_keys):
            errors.append("owner-LOR canonical MPI key sets differ")
        else:
            value = _relative(left_values, right_values)
            metrics["lor_mpi_relative"] = value
            if value > TRANSFER_LIMIT:
                errors.append(f"owner-LOR canonical MPI relative {value} exceeds {TRANSFER_LIMIT}")
    return metrics, errors


def check_records(record_paths: list[Path]) -> dict[str, Any]:
    results = [check_record(path) for path in record_paths]
    errors = [error for result in results for error in result["errors"]]
    expected_cases = {
        "p2-mpi1",
        "p2-mpi2",
        "p3-mpi1",
        "p3-mpi2",
        "p6-mpi1",
    }
    case_paths: dict[str, Path] = {}
    duplicate_cases: set[str] = set()
    for result in results:
        case = result.get("case")
        if not isinstance(case, str):
            continue
        path = Path(str(result["record"]))
        if case in case_paths:
            duplicate_cases.add(case)
        case_paths[case] = path
    if duplicate_cases:
        errors.append(f"aggregate has duplicate cases: {sorted(duplicate_cases)}")
    missing_cases = expected_cases - set(case_paths)
    extra_cases = set(case_paths) - expected_cases
    if missing_cases:
        errors.append(f"aggregate missing cases: {sorted(missing_cases)}")
    if extra_cases:
        errors.append(f"aggregate has unexpected cases: {sorted(extra_cases)}")
    if len(record_paths) != len(expected_cases):
        errors.append("aggregate requires exactly five records")
    cross_mpi: dict[str, Any] = {}
    for degree in (2, 3):
        mpi1 = case_paths.get(f"p{degree}-mpi1")
        mpi2 = case_paths.get(f"p{degree}-mpi2")
        if mpi1 is None or mpi2 is None:
            cross_mpi[f"p{degree}"] = {"status": "not_run"}
            continue
        metrics, pair_errors = _compare_canonical_records(mpi1, mpi2)
        errors.extend(f"p{degree} MPI pair: {error}" for error in pair_errors)
        cross_mpi[f"p{degree}"] = {
            "status": "measured",
            "metrics": metrics,
            "relative_limit": TRANSFER_LIMIT,
            "repeat_limit": REPEAT_LIMIT,
        }
    by_degree: dict[int, list[dict[str, Any]]] = {}
    for result in results:
        if isinstance(result.get("degree"), int) and result.get("local"):
            by_degree.setdefault(int(result["degree"]), []).append(result)
    spectral_values = {
        degree: [
            item["local"].get("spectral_condition")
            for item in items
            if isinstance(item.get("local"), dict)
            and isinstance(item["local"].get("spectral_condition"), (int, float))
        ]
        for degree, items in by_degree.items()
    }
    if (
        expected_cases == set(case_paths)
        and all(spectral_values.get(degree) for degree in (2, 3, 6))
    ):
        p2 = max(spectral_values[2])
        p3 = max(spectral_values[3])
        p6 = max(spectral_values[6])
        if p6 > 2.0 * max(p2, p3):
            errors.append(f"p6 spectral condition {p6} exceeds cross-degree limit {2.0 * max(p2, p3)}")
        cross_degree = {"p2_max": p2, "p3_max": p3, "p6_max": p6, "limit": 2.0 * max(p2, p3)}
    else:
        cross_degree = {"status": "not_run", "required_degrees": [2, 3, 6]}
    return {
        "schema": CHECKER_SCHEMA,
        "records": results,
        "aggregate_complete": not missing_cases and not extra_cases and not duplicate_cases and len(record_paths) == 5,
        "cross_mpi": cross_mpi,
        "cross_degree_spectral": cross_degree,
        "passed": not errors and len(results) == len(expected_cases),
        "errors": errors,
        "qualification_boundary": "canonical owner-local MPI packet identity is mandatory; local oracle alone is not L1 PASS",
    }


def _l2_artifact_names(source_name: str) -> dict[str, str]:
    prefix = f"l2_{source_name}"
    return {
        "source_before": f"{prefix}_source_before",
        "source_after": f"{prefix}_source_after",
        "pc_output": f"{prefix}_pc_output",
        "pc_repeat": f"{prefix}_pc_repeat",
        "residual": f"{prefix}_residual",
        "applied_output": f"{prefix}_applied_output",
        "true_residual": f"{prefix}_true_residual",
        "cg_solution": f"{prefix}_cg_solution",
        "cg_action": f"{prefix}_cg_action",
        "cg_true_residual": f"{prefix}_cg_true_residual",
    }


def _l2_identity_errors(record: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    case = record.get("case")
    if record.get("schema") != L2_SCHEMA or record.get("stage") != "l2":
        errors.append("L2 record schema/stage mismatch")
    expected = {
        "p2-mpi1": (2, 1),
        "p2-mpi2": (2, 2),
        "p3-mpi1": (3, 1),
        "p3-mpi2": (3, 2),
    }
    if case not in expected:
        errors.append("L2 case identity is invalid")
    elif (record.get("degree"), record.get("mpi_size")) != expected[case]:
        errors.append("L2 degree/MPI identity is invalid")

    source = record.get("source")
    if not isinstance(source, dict):
        errors.append("L2 source identity is missing")
    else:
        expected_sha = source.get("expected_sha")
        if not isinstance(expected_sha, str) or not SHA40.fullmatch(expected_sha):
            errors.append("L2 expected source SHA is not lowercase 40-hex")
        if source.get("commit_sha_start") != expected_sha or source.get("commit_sha_end") != expected_sha:
            errors.append("L2 source SHA is not closed at both boundaries")
        if source.get("branch") != BRANCH:
            errors.append("L2 source branch mismatch")
        if source.get("clean_start") is not True or source.get("clean_end") is not True:
            errors.append("L2 source was not clean at both boundaries")

    runtime = record.get("runtime")
    if not isinstance(runtime, dict):
        errors.append("L2 runtime identity is missing")
    else:
        if runtime.get("qualified_activation") != "1":
            errors.append("L2 qualified activation is not 1")
        if runtime.get("mpi_size") != record.get("mpi_size"):
            errors.append("L2 runtime MPI size mismatch")
        if runtime.get("petsc_scalar_type") != "complex128" or runtime.get("petsc_int_type") != "int32":
            errors.append("L2 PETSc ABI identity mismatch")
        executable = str(runtime.get("sys_executable", ""))
        if "/.venv/" not in executable or "/mnt/c/" in executable:
            errors.append("L2 runtime executable is not qualified Linux .venv")

    rank_facts = record.get("rank_facts")
    mpi_size = record.get("mpi_size")
    if not isinstance(rank_facts, list) or not isinstance(mpi_size, int) or len(rank_facts) != mpi_size:
        errors.append("L2 rank_facts count does not equal MPI size")
    else:
        ranks = [fact.get("rank") if isinstance(fact, dict) else None for fact in rank_facts]
        if any(not isinstance(rank, int) or isinstance(rank, bool) for rank in ranks):
            errors.append("L2 rank_facts contain a non-integer rank ID")
        elif sorted(ranks) != list(range(mpi_size)):
            errors.append("L2 rank_facts are not the complete rank set")
        for fact in rank_facts:
            fact_runtime = fact.get("runtime") if isinstance(fact, dict) else None
            if not isinstance(fact_runtime, dict):
                errors.append("L2 rank runtime identity is missing")
                continue
            if fact_runtime.get("qualified_activation") != "1" or fact_runtime.get("mpi_size") != mpi_size:
                errors.append("L2 rank runtime activation/MPI identity mismatch")
            if fact_runtime.get("petsc_scalar_type") != "complex128" or fact_runtime.get("petsc_int_type") != "int32":
                errors.append("L2 rank PETSc ABI identity mismatch")
            executable = str(fact_runtime.get("sys_executable", ""))
            if "/.venv/" not in executable or "/mnt/c/" in executable:
                errors.append("L2 rank executable is not qualified Linux .venv")

    fixture = record.get("fixture_audit")
    if not isinstance(fixture, dict):
        errors.append("L2 fixture audit is missing")
    else:
        fixture_contract = {
            "high_order_matrix_free": True,
            "high_order_global_aij": False,
            "global_transfer_matrix": False,
            "global_numeric_allgather": False,
            "metadata_allgather": False,
            "phase_application": "finalized_floquet_mpc_once",
            "slave_master_complete": True,
        }
        for key, value in fixture_contract.items():
            if fixture.get(key) != value:
                errors.append(f"L2 fixture {key} is not exactly {value}")
        hx = fixture.get("hx_audit")
        if not isinstance(hx, dict):
            errors.append("L2 HX audit is missing")
        else:
            hx_contract = {
                "edge_jacobi_omega": 2.0 / 3.0,
                "edge_jacobi_pre": True,
                "edge_jacobi_post": True,
                "gradient_correction_count": 1,
                "vector_correction_order": "x_then_y_then_z",
                "nodal_correction_count": 4,
                "one_v_cycle_per_nodal_correction": True,
                "one_shared_scalar_hierarchy": True,
                "hierarchy_object_count": 1,
                "pc_type": "gamg",
                "pc_gamg_type": "agg",
                "maximum_levels": 8,
                "coarse_ksp_type": "preonly",
                "coarse_pc_type": "jacobi",
                "global_transfer_matrix": False,
                "global_numeric_allgather": False,
                "global_direct_coarse": False,
                "high_order_aij": False,
                "real_imag_split": False,
                "hypre_ams": False,
            }
            for key, value in hx_contract.items():
                if hx.get(key) != value:
                    errors.append(f"L2 HX {key} is not exactly {value}")
            observed_levels = hx.get("observed_levels")
            if not isinstance(observed_levels, int) or not 1 <= observed_levels <= 8:
                errors.append("L2 HX observed_levels is outside the fixed range")

    forbidden = record.get("forbidden")
    forbidden_keys = (
        "physical_action",
        "dynamic_dtn",
        "global_numeric_allgather",
        "high_order_global_aij",
        "global_transfer_matrix",
        "global_direct_coarse",
        "real_imag_split",
        "hypre_ams",
    )
    if not isinstance(forbidden, dict) or any(
        forbidden.get(key) is not False for key in forbidden_keys
    ):
        errors.append("L2 forbidden audit is not explicitly false")
    production = record.get("production")
    production_contract = {
        "positive_auxiliary_only": True,
        "high_order_matrix_free": True,
        "numeric_allgather": False,
        "global_high_order_aij": False,
        "global_transfer_matrix": False,
        "global_direct_coarse": False,
        "physical_action": False,
        "dynamic_dtn": False,
    }
    if not isinstance(production, dict):
        errors.append("L2 production audit is missing")
    else:
        for key, value in production_contract.items():
            if production.get(key) != value:
                errors.append(f"L2 production {key} is not exactly {value}")

    roles = record.get("canonical_roles")
    expected_roles = {
        "source_before": "full_fe_primal",
        "source_after": "full_fe_primal",
        "pc_output": "full_fe_primal",
        "pc_repeat": "full_fe_primal",
        "residual": "full_fe_dual",
        "applied_output": "full_fe_dual",
        "true_residual": "full_fe_dual",
        "cg_solution": "full_fe_primal",
        "cg_action": "full_fe_dual",
        "cg_true_residual": "full_fe_dual",
    }
    if roles != expected_roles:
        errors.append("L2 canonical role map is not exact")
    evidence = record.get("canonical_evidence")
    if not isinstance(evidence, dict) or evidence.get("root_gather_evidence_only") is not True or evidence.get("production_numeric_allgather") is not False:
        errors.append("L2 canonical evidence boundary is not explicit")

    if record.get("scope") != "l2_positive_auxiliary_one_apply_and_fixed_cg":
        errors.append("L2 scope is not the fixed positive auxiliary scope")
    if not isinstance(record.get("control_flow"), dict):
        errors.append("L2 control_flow facts are missing")
    sources = record.get("sources")
    if not isinstance(sources, list) or [item.get("name") if isinstance(item, dict) else None for item in sources] != list(L2_SOURCE_NAMES):
        errors.append("L2 source order is not the frozen four-source order")
    elif len(sources) == len(L2_SOURCE_NAMES):
        allowed_statuses = {
            "measured",
            "not_run_by_prior_contraction_gate",
        }
        for entry in sources:
            if not isinstance(entry, dict):
                errors.append("L2 source entry is not an object")
                continue
            name = entry.get("name")
            if entry.get("artifact_names") != _l2_artifact_names(name):
                errors.append(f"L2 {name}: artifact_names prefix is not exact")
            if entry.get("formula") != L2_SOURCE_FORMULAS.get(name):
                errors.append(f"L2 {name}: source formula is not the frozen helper formula")
            if entry.get("status") not in allowed_statuses:
                errors.append(f"L2 {name}: source status is not an allowed frozen status")
    return errors


def _l2_series(
    arrays: dict[str, np.ndarray], base: str
) -> tuple[np.ndarray | None, np.ndarray | None, list[str]]:
    errors: list[str] = []
    keys = arrays.get(f"{base}_keys")
    values = arrays.get(f"{base}_values")
    if keys is None or values is None:
        return None, None, [f"missing canonical series {base}"]
    keys = np.asarray(keys)
    values = np.asarray(values)
    if keys.dtype != np.dtype("<U64") or keys.ndim != 1:
        errors.append(f"{base} keys are not a <U64 vector")
    if values.dtype != np.dtype(np.complex128) or values.ndim != 1:
        errors.append(f"{base} values are not a complex128 vector")
    if keys.ndim == 1 and values.ndim == 1 and keys.size != values.size:
        errors.append(f"{base} key/value lengths differ")
    if keys.ndim == 1 and not np.array_equal(keys, np.unique(keys)):
        errors.append(f"{base} keys are not unique and sorted")
    if values.ndim == 1 and not _finite(values):
        errors.append(f"{base} values are non-finite")
    return keys, values, errors


def _l2_scalar_relative(observed: Any, expected: float) -> float:
    try:
        return float(abs(float(observed) - expected) / max(abs(expected), 1.0e-300))
    except (TypeError, ValueError):
        return float("inf")


def _l2_json_sequence(value: Any) -> Any:
    if value is None:
        return None
    array = np.asarray(value)
    if np.iscomplexobj(array):
        return [[float(item.real), float(item.imag)] for item in array.reshape(-1)]
    return array.tolist()


def _l2_source_check(
    entry: dict[str, Any], arrays: dict[str, np.ndarray]
) -> dict[str, Any]:
    errors: list[str] = []
    name = entry.get("name")
    if name not in L2_SOURCE_NAMES:
        return {
            "errors": [f"{name}: source name is not in the frozen source order"],
            "contract_errors": [f"{name}: source name is not in the frozen source order"],
            "gate_reason": None,
        }
    expected_names = _l2_artifact_names(name)
    if entry.get("artifact_names") != expected_names:
        errors.append(f"{name}: artifact_names prefix is not exact")
    if entry.get("formula") != L2_SOURCE_FORMULAS[name]:
        errors.append(f"{name}: source formula is not the frozen helper formula")
    if entry.get("status") != "measured":
        return {"errors": errors, "contract_errors": errors, "gate_reason": None}
    if entry.get("phase_application") != L2_PHASE_APPLICATION:
        errors.append(f"{name}: phase_application is not the finalized algebraic source contract")
    series: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for label in (
        "source_before",
        "source_after",
        "pc_output",
        "pc_repeat",
        "residual",
        "applied_output",
        "true_residual",
    ):
        keys, values, local_errors = _l2_series(arrays, expected_names[label])
        errors.extend(local_errors)
        if not local_errors:
            series[label] = (keys, values)
    if errors:
        return {"errors": errors, "contract_errors": errors, "gate_reason": None}

    primal_keys = series["source_before"][0]
    for label in ("source_after", "pc_output", "pc_repeat"):
        if not np.array_equal(primal_keys, series[label][0]):
            errors.append(f"{name}: primal canonical keys differ for {label}")
    dual_keys = series["residual"][0]
    for label in ("applied_output", "true_residual"):
        if not np.array_equal(dual_keys, series[label][0]):
            errors.append(f"{name}: dual canonical keys differ for {label}")
    if errors:
        return {"errors": errors, "contract_errors": errors, "gate_reason": None}

    source_before = series["source_before"][1]
    source_after = series["source_after"][1]
    pc_output = series["pc_output"][1]
    pc_repeat = series["pc_repeat"][1]
    residual = series["residual"][1]
    applied = series["applied_output"][1]
    stored_true = series["true_residual"][1]
    source_identity = _relative(source_after, source_before)
    repeat_relative = _relative(pc_repeat, pc_output)
    computed_true = residual - applied
    true_identity = _relative(stored_true, computed_true)
    rho = float(np.linalg.norm(computed_true) / max(np.linalg.norm(residual), 1.0e-300))
    if true_identity > L2_CANONICAL_LIMIT:
        errors.append(f"{name}: stored true residual differs from residual-applied")
    if entry.get("rho_limit") != L2_RHO_LIMITS.get(name):
        errors.append(f"{name}: rho limit is not the frozen source limit")
    if entry.get("repeat_limit") != L2_REPEAT_LIMIT:
        errors.append(f"{name}: repeat limit is not 1e-13")
    if _l2_scalar_relative(entry.get("rho"), rho) > L2_CANONICAL_LIMIT:
        errors.append(f"{name}: recorded rho does not match raw recomputation")
    if _l2_scalar_relative(entry.get("repeat_relative"), repeat_relative) > L2_CANONICAL_LIMIT:
        errors.append(f"{name}: recorded repeat does not match raw recomputation")
    before_after = entry.get("source_identity")
    if not isinstance(before_after, dict) or before_after.get("before") != expected_names["source_before"] or before_after.get("after") != expected_names["source_after"]:
        errors.append(f"{name}: source before/after identity artifacts are not bound")

    gate_reason = None
    if not all(_finite(series[label][1]) for label in series):
        gate_reason = "non_finite_source_or_one_apply"
    elif source_identity > L2_REPEAT_LIMIT:
        gate_reason = "source_input_changed"
    elif repeat_relative > L2_REPEAT_LIMIT:
        gate_reason = "repeat_relative_above_fixed_limit"
    elif rho > L2_RHO_LIMITS[name]:
        gate_reason = "rho_above_source_fixed_limit"
    if entry.get("input_unchanged") is not (gate_reason != "source_input_changed"):
        errors.append(f"{name}: recorded input_unchanged disagrees with raw identity")
    if entry.get("finite") is not all(_finite(series[label][1]) for label in series):
        errors.append(f"{name}: recorded finite fact disagrees with raw arrays")
    gate_failure = gate_reason is not None
    return {
        "errors": errors,
        "contract_errors": errors,
        "gate_reason": gate_reason,
        "rho_gate_failure": gate_reason == "rho_above_source_fixed_limit",
        "rho": rho,
        "repeat_relative": repeat_relative,
        "source_identity_relative": source_identity,
        "true_identity_relative": true_identity,
        "gate_failure": gate_failure,
        "residual_values": residual,
        "applied_values": applied,
        "source_keys": primal_keys,
        "dual_keys": dual_keys,
    }


def _l2_cg_check(
    entry: dict[str, Any], source_result: dict[str, Any], arrays: dict[str, np.ndarray]
) -> dict[str, Any]:
    errors: list[str] = []
    cg = entry.get("cg")
    if not isinstance(cg, dict):
        return {"errors": [f"{entry.get('name')}: CG facts are missing"], "gate_reason": None}
    if cg.get("status") != "measured":
        return {"errors": [], "gate_reason": None}
    name = entry.get("name")
    if name not in L2_SOURCE_NAMES:
        return {
            "errors": [f"{name}: CG source name is not in the frozen source order"],
            "gate_reason": None,
        }
    if (
        source_result.get("source_keys") is None
        or source_result.get("dual_keys") is None
        or source_result.get("residual_values") is None
    ):
        return {
            "errors": [f"{name}: CG cannot be checked because source facts are incomplete"],
            "gate_reason": None,
        }
    names = _l2_artifact_names(name)
    solution_keys, solution, solution_errors = _l2_series(arrays, names["cg_solution"])
    action_keys, action, action_errors = _l2_series(arrays, names["cg_action"])
    true_keys, stored_true, true_errors = _l2_series(arrays, names["cg_true_residual"])
    errors.extend(solution_errors + action_errors + true_errors)
    if errors:
        return {"errors": errors, "gate_reason": None}
    if not np.array_equal(solution_keys, source_result["source_keys"]):
        errors.append(f"{name}: CG solution keys differ from primal source keys")
    if not np.array_equal(action_keys, source_result["dual_keys"]) or not np.array_equal(true_keys, source_result["dual_keys"]):
        errors.append(f"{name}: CG dual keys differ from residual keys")
    computed_true = source_result["residual_values"] - action
    true_identity = _relative(stored_true, computed_true)
    true_relative = float(np.linalg.norm(computed_true) / max(np.linalg.norm(source_result["residual_values"]), 1.0e-300))
    reason = cg.get("reason")
    iterations = cg.get("iterations")
    if not isinstance(reason, int) or isinstance(reason, bool):
        errors.append(f"{name}: CG reason is not an integer")
    if not isinstance(iterations, int) or isinstance(iterations, bool):
        errors.append(f"{name}: CG iterations is not an integer")
    if true_identity > L2_CANONICAL_LIMIT:
        errors.append(f"{name}: CG stored true residual differs from rhs-action")
    if cg.get("true_residual_limit") != L2_CG_TRUE_RESIDUAL_LIMIT:
        errors.append(f"{name}: CG true-residual limit is not 1e-8")
    if cg.get("ksp_type") != L2_CG_KSP_TYPE:
        errors.append(f"{name}: CG ksp_type is not exactly cg")
    if cg.get("rtol") != L2_CG_RTOL:
        errors.append(f"{name}: CG rtol is not exactly 1e-8")
    if cg.get("max_it") != L2_CG_MAX_IT:
        errors.append(f"{name}: CG max_it is not exactly 40")
    if _l2_scalar_relative(cg.get("true_residual_relative"), true_relative) > L2_CANONICAL_LIMIT:
        errors.append(f"{name}: recorded CG true residual does not match raw recomputation")
    gate_reason = None
    if not all(_finite(value) for value in (solution, action, stored_true)):
        gate_reason = "cg_non_finite"
    elif not isinstance(reason, int) or isinstance(reason, bool) or reason <= 0:
        gate_reason = "cg_reason_not_converged"
    elif not isinstance(iterations, int) or isinstance(iterations, bool) or iterations > 40:
        gate_reason = "cg_iterations_above_40"
    elif true_relative > L2_CG_TRUE_RESIDUAL_LIMIT:
        gate_reason = "cg_true_residual_above_limit"
    return {
        "errors": errors,
        "gate_reason": gate_reason,
        "true_residual_relative": true_relative,
        "iterations": iterations,
        "reason": reason,
        "cg_solution_keys": solution_keys,
        "cg_solution_values": solution,
    }


def check_l2_record(record_path: Path) -> dict[str, Any]:
    try:
        raw_record_sha256 = _sha256(record_path)
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "record": str(record_path),
            "passed": False,
            "contract_errors": [f"L2 record parse: {type(exc).__name__}: {exc}"],
            "gate_failures": [],
            "errors": [f"L2 record parse: {type(exc).__name__}: {exc}"],
            "raw_record_sha256": locals().get("raw_record_sha256"),
            "case": None,
            "rho_gate_failure": False,
        }
    contract_errors = _l2_identity_errors(record)
    source_entries = record.get("sources")
    required: set[str] = set()
    if isinstance(source_entries, list):
        for entry in source_entries:
            if not isinstance(entry, dict) or entry.get("status") != "measured":
                continue
            names = _l2_artifact_names(str(entry.get("name")))
            required.update(
                f"{names[label]}_{suffix}"
                for label in (
                    "source_before",
                    "source_after",
                    "pc_output",
                    "pc_repeat",
                    "residual",
                    "applied_output",
                    "true_residual",
                )
                for suffix in ("keys", "values")
            )
            cg = entry.get("cg")
            if isinstance(cg, dict) and cg.get("status") == "measured":
                required.update(
                    f"{names[label]}_{suffix}"
                    for label in ("cg_solution", "cg_action", "cg_true_residual")
                    for suffix in ("keys", "values")
                )
    try:
        arrays, artifact_errors = _read_artifacts(record, required)
    except Exception as exc:
        arrays, artifact_errors = {}, [f"L2 artifact validation: {type(exc).__name__}: {exc}"]
    contract_errors.extend(artifact_errors)
    source_results: list[dict[str, Any]] = []
    gate_failures: list[str] = []
    first_source_gate: int | None = None
    rho_gate_failure = False
    if isinstance(source_entries, list) and len(source_entries) == len(L2_SOURCE_NAMES):
        for index, entry in enumerate(source_entries):
            if not isinstance(entry, dict):
                contract_errors.append(f"L2 source entry {index} is not an object")
                source_results.append({"gate_reason": None, "errors": []})
                continue
            if entry.get("status") == "measured" and not artifact_errors:
                result = _l2_source_check(entry, arrays)
            else:
                result = {
                    "errors": [] if entry.get("status") == "not_run_by_prior_contraction_gate" else [f"{entry.get('name')}: invalid source status"],
                    "gate_reason": None,
                }
            contract_errors.extend(result.get("contract_errors", result.get("errors", [])))
            source_results.append(result)
            if result.get("gate_reason") is not None and first_source_gate is None:
                first_source_gate = index
                gate_failures.append(
                    f"{entry.get('name')}: {result['gate_reason']} rho={result.get('rho')} limit={L2_RHO_LIMITS.get(entry.get('name'))}"
                )
                rho_gate_failure = bool(result.get("rho_gate_failure"))
            elif first_source_gate is not None and entry.get("status") == "measured":
                contract_errors.append(f"{entry.get('name')}: measured after prior source Gate failure")
        if first_source_gate is None:
            for index, entry in enumerate(source_entries):
                if isinstance(entry, dict) and entry.get("status") != "measured":
                    contract_errors.append(f"{entry.get('name')}: not_run without a prior recomputed source Gate failure")
        else:
            for index in range(first_source_gate):
                entry = source_entries[index]
                if not isinstance(entry, dict) or entry.get("status") != "measured":
                    contract_errors.append(f"L2 source index {index}: source was not measured before the first source Gate failure")
            for index in range(first_source_gate + 1, len(source_entries)):
                entry = source_entries[index]
                if not isinstance(entry, dict) or entry.get("status") != "not_run_by_prior_contraction_gate":
                    contract_errors.append(f"L2 source index {index}: later source was not marked not_run_by_prior_contraction_gate")

        if first_source_gate is not None:
            for entry in source_entries:
                if isinstance(entry, dict):
                    cg = entry.get("cg")
                    if isinstance(cg, dict) and cg.get("status") == "measured":
                        contract_errors.append(f"{entry.get('name')}: CG measured after source Gate failure")
        else:
            first_cg_gate: int | None = None
            for index, entry in enumerate(source_entries):
                if not isinstance(entry, dict) or entry.get("status") != "measured":
                    continue
                result = _l2_cg_check(entry, source_results[index], arrays) if not artifact_errors else {"errors": [], "gate_reason": None}
                contract_errors.extend(result.get("errors", []))
                source_results[index]["cg"] = result
                if result.get("gate_reason") is not None and first_cg_gate is None:
                    first_cg_gate = index
                    gate_failures.append(f"{entry.get('name')}: {result['gate_reason']}")
                elif first_cg_gate is not None:
                    if entry.get("cg", {}).get("status") != "not_run_by_prior_cg_gate":
                        contract_errors.append(f"{entry.get('name')}: CG was not stopped after prior CG Gate failure")
            if first_cg_gate is None:
                for entry in source_entries:
                    if isinstance(entry, dict) and entry.get("status") == "measured" and entry.get("cg", {}).get("status") != "measured":
                        contract_errors.append(f"{entry.get('name')}: measured source has no measured CG facts")
            else:
                for index in range(first_cg_gate):
                    entry = source_entries[index]
                    if not isinstance(entry, dict) or entry.get("status") != "measured":
                        continue
                    if entry.get("cg", {}).get("status") != "measured":
                        contract_errors.append(f"{entry.get('name')}: CG was not measured before the first CG Gate failure")
    source_metrics = [
        {
            "name": entry.get("name") if isinstance(entry, dict) else None,
            "gate_reason": result.get("gate_reason"),
            "rho": result.get("rho"),
            "rho_gate_failure": result.get("rho_gate_failure", False),
            "iterations": (result.get("cg") or {}).get("iterations"),
            "cg_solution_keys": _l2_json_sequence(
                (result.get("cg") or {}).get("cg_solution_keys")
            ),
            "cg_solution_values": _l2_json_sequence(
                (result.get("cg") or {}).get("cg_solution_values")
            ),
        }
        for entry, result in zip(source_entries or (), source_results, strict=False)
    ]
    return {
        "record": str(record_path),
        "raw_record_sha256": raw_record_sha256,
        "source_sha": record.get("source", {}).get("expected_sha") if isinstance(record.get("source"), dict) else None,
        "case": record.get("case"),
        "degree": record.get("degree"),
        "mpi_size": record.get("mpi_size"),
        "passed": not contract_errors and not gate_failures,
        "contract_errors": contract_errors,
        "gate_failures": gate_failures,
        "errors": contract_errors + gate_failures,
        "rho_gate_failure": rho_gate_failure,
        "source_metrics": source_metrics,
    }


def _l2_compare_pair(left: dict[str, Any], right: dict[str, Any]) -> tuple[dict[str, float], list[str]]:
    errors: list[str] = []
    metrics: dict[str, float] = {}
    left_record = json.loads(Path(left["record"]).read_text(encoding="utf-8"))
    right_record = json.loads(Path(right["record"]).read_text(encoding="utf-8"))
    required: set[str] = set()
    for entry in left_record.get("sources", []):
        if isinstance(entry, dict) and entry.get("status") == "measured":
            names = _l2_artifact_names(entry["name"])
            for label in ("residual", "applied_output", "cg_action", "cg_solution"):
                required.update({f"{names[label]}_keys", f"{names[label]}_values"})
    left_arrays, left_errors = _read_artifacts(left_record, required)
    right_arrays, right_errors = _read_artifacts(right_record, required)
    errors.extend(f"left canonical artifacts: {error}" for error in left_errors)
    errors.extend(f"right canonical artifacts: {error}" for error in right_errors)
    if errors:
        return metrics, errors
    for entry in left_record.get("sources", []):
        if not isinstance(entry, dict) or entry.get("status") != "measured":
            continue
        name = entry["name"]
        left_names = _l2_artifact_names(name)
        right_entry = next((item for item in right_record.get("sources", []) if item.get("name") == name), None)
        if not isinstance(right_entry, dict) or right_entry.get("status") != "measured":
            errors.append(f"{name}: MPI pair source is not measured on both ranks")
            continue
        right_names = _l2_artifact_names(name)
        for label in ("residual", "applied_output", "cg_action", "cg_solution"):
            left_keys, left_values, left_local_errors = _l2_series(left_arrays, left_names[label])
            right_keys, right_values, right_local_errors = _l2_series(right_arrays, right_names[label])
            errors.extend(f"{name} left {label}: {error}" for error in left_local_errors)
            errors.extend(f"{name} right {label}: {error}" for error in right_local_errors)
            if left_local_errors or right_local_errors:
                continue
            if not np.array_equal(left_keys, right_keys):
                errors.append(f"{name} {label} MPI key sets differ")
                continue
            relative = _relative(left_values, right_values)
            metrics[f"{name}_{label}_mpi_relative"] = relative
            if relative > L2_CANONICAL_LIMIT:
                errors.append(f"{name} {label} MPI relative {relative} exceeds {L2_CANONICAL_LIMIT}")
    return metrics, errors


def check_l2_records(record_paths: list[Path]) -> dict[str, Any]:
    results = [check_l2_record(path) for path in record_paths]
    contract_errors: list[str] = []
    gate_failures: list[str] = []
    for result in results:
        contract_errors.extend(f"{result.get('case')}: {error}" for error in result["contract_errors"])
        gate_failures.extend(f"{result.get('case')}: {error}" for error in result["gate_failures"])
    case_paths: dict[str, dict[str, Any]] = {}
    duplicate_cases: set[str] = set()
    for result in results:
        case = result.get("case")
        if not isinstance(case, str):
            continue
        if case in case_paths:
            duplicate_cases.add(case)
        case_paths[case] = result
    if duplicate_cases:
        contract_errors.append(f"L2 aggregate duplicate cases: {sorted(duplicate_cases)}")
    extra_cases = set(case_paths) - set(L2_CASE_ORDER)
    if extra_cases:
        contract_errors.append(f"L2 aggregate unexpected cases: {sorted(extra_cases)}")
    first = case_paths.get("p2-mpi1")
    hard_stop = bool(
        first is not None
        and first.get("gate_failures")
        and not first.get("contract_errors")
    )
    if hard_stop and any(case != "p2-mpi1" for case in case_paths):
        contract_errors.append("L2 hard-stop aggregate contains a later case after p2-mpi1 Gate failure")
    missing_cases = [case for case in L2_CASE_ORDER if case not in case_paths]
    if missing_cases and not hard_stop:
        contract_errors.append(f"L2 aggregate missing cases: {missing_cases}")
    if not hard_stop and len(record_paths) != len(L2_CASE_ORDER):
        contract_errors.append("L2 aggregate requires exactly four records")
    if len(record_paths) == len(L2_CASE_ORDER):
        observed_order = [result.get("case") for result in results]
        if observed_order != list(L2_CASE_ORDER):
            contract_errors.append("L2 aggregate case order is not the frozen order")

    cross_mpi: dict[str, Any] = {}
    if not hard_stop and not contract_errors and all(result.get("passed") for result in results):
        for degree in (2, 3):
            left = case_paths[f"p{degree}-mpi1"]
            right = case_paths[f"p{degree}-mpi2"]
            metrics, errors = _l2_compare_pair(left, right)
            cross_mpi[f"p{degree}"] = {"metrics": metrics, "errors": errors, "limit": L2_CANONICAL_LIMIT}
            gate_failures.extend(f"p{degree} MPI pair: {error}" for error in errors)
        for mpi in (1, 2):
            p2_metrics = {
                item["name"]: item
                for item in case_paths[f"p2-mpi{mpi}"]["source_metrics"]
                if item.get("name") in L2_SOURCE_NAMES
            }
            p3_metrics = {
                item["name"]: item
                for item in case_paths[f"p3-mpi{mpi}"]["source_metrics"]
                if item.get("name") in L2_SOURCE_NAMES
            }
            for name in L2_SOURCE_NAMES:
                p2_iterations = p2_metrics.get(name, {}).get("iterations")
                p3_iterations = p3_metrics.get(name, {}).get("iterations")
                if not isinstance(p2_iterations, int) or isinstance(p2_iterations, bool) or not isinstance(p3_iterations, int) or isinstance(p3_iterations, bool):
                    contract_errors.append(f"p2/p3-mpi{mpi} {name}: CG iterations are missing for p3<=p2+10")
                elif p3_iterations > p2_iterations + 10:
                    gate_failures.append(f"{name}: p3-mpi{mpi} iterations exceed p2-mpi{mpi}+10")
    return {
        "schema": L2_CHECKER_SCHEMA,
        "case_order": list(L2_CASE_ORDER),
        "records": results,
        "hard_stop": hard_stop,
        "later_cases": missing_cases if hard_stop else [],
        "later_cases_status": "not_run_by_gate" if hard_stop else None,
        "contract_errors": contract_errors,
        "gate_failures": gate_failures,
        "errors": contract_errors + gate_failures,
        "cross_mpi": cross_mpi,
        "passed": not contract_errors and not gate_failures and not hard_stop and len(results) == len(L2_CASE_ORDER),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("l1", "l2"), default="l1")
    parser.add_argument("--record", action="append", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.stage == "l2":
        result = check_l2_records([path.resolve() for path in args.record])
    else:
        result = check_records([path.resolve() for path in args.record])
    args.output.resolve().parent.mkdir(parents=True, exist_ok=True)
    args.output.resolve().write_bytes(
        (json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")
    )
    print(json.dumps({"output": str(args.output.resolve()), "passed": result["passed"], "errors": len(result["errors"])}, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
