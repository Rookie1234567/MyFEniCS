"""Independent NumPy checker for the V11 S1 bounded spectral audit."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

import numpy as np


SCHEMA = "task038.lor-global-spectral-audit.v2"
BATCH_SCHEMA = "task038.lor-global-spectral-audit.v2.batch"
STAGE = "s1"
H_NM = 50.0
CASE_DEGREES = {"p2-mpi1": 2, "p3-mpi1": 3}
EIGEN_RESIDUAL_LIMIT = 1.0e-10
HIGH_ACTION_LIMIT = 1.0e-11
WORK_LIMIT = 1.0e-12
RANK_TOLERANCE = "max(m,n)*eps*sigma_max"
EIGEN_DRIVER = "gvx"
EIGEN_METHOD = "complex128_lapack_generalized_hermitian"
EIGEN_LIBRARY = "scipy.linalg.eigh"
EIGEN_SELECTION = "subset_endpoint"
RANK_METHOD = "scipy.linalg.svdvals"
WATCHDOG_SCHEMA = "task038.lor-native-complex-hx.foundation-e-watchdog.v1"
WATCHDOG_POLL_SECONDS = 0.25
WATCHDOG_RSS_LIMIT = 2_000_000_000
BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"


def _relative(left: np.ndarray, right: np.ndarray, denominator: np.ndarray | None = None) -> float:
    left = np.asarray(left, dtype=np.complex128)
    right = np.asarray(right, dtype=np.complex128)
    base = right if denominator is None else np.asarray(denominator, dtype=np.complex128)
    return float(np.linalg.norm(left - right) / max(float(np.linalg.norm(base)), np.finfo(float).tiny))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_array(raw_dir: Path, descriptor: dict[str, Any], role: str, errors: list[str]) -> np.ndarray | None:
    required = {"relative_path", "sha256", "bytes", "dtype", "shape"}
    if not isinstance(descriptor, dict) or set(descriptor) != required:
        errors.append(f"{role}: invalid artifact descriptor")
        return None
    relative_path = Path(str(descriptor["relative_path"]))
    if relative_path.is_absolute() or ".." in relative_path.parts:
        errors.append(f"{role}: artifact escapes raw_dir")
        return None
    path = raw_dir / relative_path
    try:
        if not path.is_file():
            raise FileNotFoundError(path)
        if _sha256(path) != str(descriptor["sha256"]):
            raise ValueError("sha256 mismatch")
        if path.stat().st_size != int(descriptor["bytes"]):
            raise ValueError("byte count mismatch")
        values = np.load(path, allow_pickle=False)
        if str(values.dtype) != str(descriptor["dtype"]):
            raise ValueError(f"dtype {values.dtype} != {descriptor['dtype']}")
        if list(values.shape) != [int(item) for item in descriptor["shape"]]:
            raise ValueError("shape mismatch")
        if not np.all(np.isfinite(values)):
            raise ValueError("non-finite values")
        return np.asarray(values)
    except (OSError, ValueError, TypeError) as exc:
        errors.append(f"{role}: {exc}")
        return None


def _load_csr(raw_dir: Path, descriptor: dict[str, Any], role: str, errors: list[str]) -> dict[str, Any] | None:
    if not isinstance(descriptor, dict):
        errors.append(f"{role}: missing CSR descriptor")
        return None
    required = {"rows", "cols", "nnz", "index_bytes", "numeric_bytes", "indptr", "indices", "values"}
    if set(descriptor) != required:
        errors.append(f"{role}: CSR descriptor keys mismatch")
        return None
    indptr = _load_array(raw_dir, descriptor["indptr"], f"{role}.indptr", errors)
    indices = _load_array(raw_dir, descriptor["indices"], f"{role}.indices", errors)
    values = _load_array(raw_dir, descriptor["values"], f"{role}.values", errors)
    if indptr is None or indices is None or values is None:
        return None
    rows, cols, nnz = int(descriptor["rows"]), int(descriptor["cols"]), int(descriptor["nnz"])
    if indptr.dtype != np.int64 or indices.dtype != np.int64 or values.dtype != np.complex128:
        errors.append(f"{role}: CSR dtype contract mismatch")
    if indptr.shape != (rows + 1,) or indices.shape != (nnz,) or values.shape != (nnz,):
        errors.append(f"{role}: CSR shape contract mismatch")
    if indptr.size and (indptr[0] != 0 or indptr[-1] != nnz or np.any(np.diff(indptr) < 0)):
        errors.append(f"{role}: invalid CSR row pointer")
    if indices.size and (np.any(indices < 0) or np.any(indices >= cols)):
        errors.append(f"{role}: CSR column out of range")
    return {"rows": rows, "cols": cols, "nnz": nnz, "indptr": indptr, "indices": indices, "values": values}


def _csr_dense(matrix: dict[str, Any]) -> np.ndarray:
    dense = np.zeros((int(matrix["rows"]), int(matrix["cols"])), dtype=np.complex128)
    for row in range(int(matrix["rows"])):
        start, stop = int(matrix["indptr"][row]), int(matrix["indptr"][row + 1])
        dense[row, matrix["indices"][start:stop]] = matrix["values"][start:stop]
    return dense


def _csr_right_product(dense_left: np.ndarray, matrix: dict[str, Any]) -> np.ndarray:
    result = np.zeros((dense_left.shape[0], int(matrix["cols"])), dtype=np.complex128)
    for row in range(int(matrix["rows"])):
        start, stop = int(matrix["indptr"][row]), int(matrix["indptr"][row + 1])
        for position in range(start, stop):
            result[:, int(matrix["indices"][position])] += dense_left[:, row] * matrix["values"][position]
    return result


def _csr_adjoint_left_product(matrix: dict[str, Any], dense_right: np.ndarray) -> np.ndarray:
    result = np.zeros((int(matrix["cols"]), dense_right.shape[1]), dtype=np.complex128)
    for row in range(int(matrix["rows"])):
        start, stop = int(matrix["indptr"][row]), int(matrix["indptr"][row + 1])
        for position in range(start, stop):
            column = int(matrix["indices"][position])
            result[column] += np.conj(matrix["values"][position]) * dense_right[row]
    return result


def _check_layout(record: dict[str, Any], matrices: dict[str, dict[str, Any]], errors: list[str], gates: list[str]) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    layout = record.get("layout")
    if not isinstance(layout, dict) or set(layout) != {
        "low",
        "high",
        "tested_dimension",
        "numerical_rank",
        "rank_tau",
        "low_owner_authority",
        "high_owner_authority",
        "low_bijection",
        "high_active_slave_partition",
        "independent_dimension_closed",
    }:
        errors.append("layout: required keys missing")
        return {}, {}
    low_desc = layout.get("low")
    high_desc = layout.get("high")
    if not isinstance(low_desc, dict) or not isinstance(high_desc, dict):
        errors.append("layout: low/high descriptors missing")
        return {}, {}
    if record.get("layout", {}).get("low_owner_authority") != "lor_raw_topology.owned_edge_ids":
        errors.append("low owner inventory is not bound to the independent raw-topology authority")
    if record.get("layout", {}).get("high_owner_authority") != "lor_topology.owned_edge_ids":
        errors.append("high owner inventory authority is not closed")
    if record.get("layout", {}).get("low_bijection") is not True:
        gates.append("low owner bijection fact is not closed")
    if record.get("layout", {}).get("high_active_slave_partition") is not True:
        gates.append("high active/slave partition fact is not closed")
    if record.get("layout", {}).get("independent_dimension_closed") is not True:
        gates.append("independent dimensions are not closed")
    low: dict[str, np.ndarray] = {}
    high: dict[str, np.ndarray] = {}
    for name in (
        "low_active_raw_rows",
        "low_slave_raw_rows",
        "low_canonical_owner_ids",
        "low_topology_owner_ids",
        "low_phase_codes",
    ):
        value = _load_array(Path(record["raw_dir"]), low_desc.get(name), f"layout.{name}", errors)
        if value is not None:
            low[name] = value
    for name in (
        "high_active_raw_rows",
        "high_slave_raw_rows",
        "high_topology_owner_ids",
    ):
        value = _load_array(Path(record["raw_dir"]), high_desc.get(name), f"layout.{name}", errors)
        if value is not None:
            high[name] = value
    for name, data, dtype in (
        ("low_active_raw_rows", low, np.int64),
        ("low_slave_raw_rows", low, np.int64),
        ("low_canonical_owner_ids", low, np.int64),
        ("low_topology_owner_ids", low, np.int64),
        ("low_phase_codes", low, np.int8),
        ("high_active_raw_rows", high, np.int64),
        ("high_slave_raw_rows", high, np.int64),
        ("high_topology_owner_ids", high, np.int64),
    ):
        if name in data and data[name].dtype != dtype:
            errors.append(f"layout.{name} dtype mismatch")
    if "B_L_full" not in matrices or "B_H_full" not in matrices:
        return low, high
    for prefix, data, matrix_name in (("low", low, "B_L_full"), ("high", high, "B_H_full")):
        matrix = matrices[matrix_name]
        full = int(matrix["rows"])
        active = data.get(f"{prefix}_active_raw_rows")
        slave = data.get(f"{prefix}_slave_raw_rows")
        if active is None or slave is None:
            continue
        if np.unique(active).size != active.size or np.unique(slave).size != slave.size:
            errors.append(f"{prefix} layout rows are not unique")
        if np.any(active < 0) or np.any(active >= full) or np.any(slave < 0) or np.any(slave >= full):
            errors.append(f"{prefix} layout rows are out of range")
        if not np.array_equal(np.sort(np.concatenate((active, slave))), np.arange(full, dtype=np.int64)):
            errors.append(f"{prefix} active/slave rows do not partition full rows")
        if active.size != full - slave.size:
            errors.append(f"{prefix} active/slave count does not close full rows")
        owner_key = f"{prefix}_topology_owner_ids"
        owner_ids = data.get(owner_key)
        if owner_ids is not None:
            if owner_ids.dtype != np.int64:
                errors.append(f"{prefix} owner IDs must be int64")
            if np.unique(owner_ids).size != owner_ids.size or owner_ids.size != active.size:
                errors.append(f"{prefix} owner IDs are not a unique active-row inventory")
    if "low_canonical_owner_ids" in low and "low_topology_owner_ids" in low:
        if low["low_canonical_owner_ids"].dtype != np.int64:
            errors.append("low canonical owner IDs must be int64")
        if not np.array_equal(
            np.sort(low["low_canonical_owner_ids"]),
            np.sort(low["low_topology_owner_ids"]),
        ):
            errors.append("low canonical owner IDs do not close owner inventory")
        if low["low_canonical_owner_ids"].size != low["low_active_raw_rows"].size:
            errors.append("low canonical owner inventory count does not close")
    if "high_topology_owner_ids" in high and high["high_topology_owner_ids"].size != high.get(
        "high_active_raw_rows", np.empty(0)
    ).size:
        errors.append("high owner authority count does not close active rows")
    if int(layout.get("tested_dimension", -1)) != int(
        low.get("low_active_raw_rows", np.empty(0)).size
    ):
        errors.append("tested dimension does not match low independent rows")
    if "low_phase_codes" in low and np.any(low["low_phase_codes"] != 0):
        gates.append("active LOR phase code is nonzero")
    return low, high


def _check_settings(
    record: dict[str, Any],
    record_path: Path,
    raw_dir: Path,
    expected_source_sha: str,
    errors: list[str],
    gates: list[str],
    *,
    command_case: str | None = None,
    command_raw_dir: Path | None = None,
) -> None:
    if record.get("schema") != SCHEMA or record.get("stage") != STAGE:
        errors.append("schema/stage mismatch")
    case = record.get("case")
    if case not in CASE_DEGREES or int(record.get("degree", -1)) != CASE_DEGREES.get(case):
        errors.append("case/degree mismatch")
    if float(record.get("h_nm", -1.0)) != H_NM:
        errors.append("h_nm mismatch")
    if record.get("source_name") != "random" or int(record.get("mpi_size", -1)) != 1:
        errors.append("source/MPI identity mismatch")
    source = record.get("source")
    sha_pattern = re.compile(r"[0-9a-f]{40}")
    if not sha_pattern.fullmatch(str(expected_source_sha)):
        errors.append("expected source SHA is not a lowercase 40-hex Git SHA")
    if not isinstance(source, dict) or source.get("expected_sha") != expected_source_sha or source.get("commit_sha_start") != expected_source_sha or source.get("commit_sha_end") != expected_source_sha:
        errors.append("source SHA identity mismatch")
    if not isinstance(source, dict) or source.get("branch") != BRANCH:
        errors.append("source branch identity mismatch")
    if not isinstance(source, dict) or source.get("clean_start") is not True or source.get("clean_end") is not True:
        errors.append("source clean identity is not closed")
    runtime = record.get("runtime")
    if not isinstance(runtime, dict):
        errors.append("runtime facts missing")
    else:
        for key, expected in (("qualified_activation", "1"), ("petsc_scalar_type", "complex128"), ("petsc_int_type", "int32")):
            if runtime.get(key) != expected:
                errors.append(f"runtime.{key} mismatch")
        if int(runtime.get("mpi_size", -1)) != 1:
            errors.append("runtime MPI size mismatch")
        if runtime.get("threads") != {"OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1"}:
            errors.append("runtime thread identity mismatch")
    settings = record.get("settings")
    required = {
        "rank_tolerance": RANK_TOLERANCE,
        "eigen_method": EIGEN_METHOD,
        "eigen_library": EIGEN_LIBRARY,
        "eigen_driver": EIGEN_DRIVER,
        "eigen_selection": EIGEN_SELECTION,
        "rank_method": RANK_METHOD,
        "condition_policy": "report_only_no_cap",
    }
    if not isinstance(settings, dict):
        errors.append("settings missing")
    else:
        for key, expected in required.items():
            if settings.get(key) != expected:
                errors.append(f"settings.{key} mismatch")
        if float(settings.get("eigen_residual_limit", -1.0)) != EIGEN_RESIDUAL_LIMIT:
            errors.append("settings.eigen_residual_limit mismatch")
    command = record.get("command")
    if not isinstance(command, list) or not command or not isinstance(command[0], str) or not Path(command[0]).is_absolute():
        errors.append("command executable must be absolute")
    elif any(not isinstance(item, str) for item in command):
        errors.append("command argv must contain only strings")
    else:
        expected_options = {
            "--stage": STAGE,
            "--raw-dir": str((command_raw_dir or raw_dir).resolve()),
            "--record": str(record_path),
            "--expected-source-sha": expected_source_sha,
            "--expected-mpi-size": "1",
            "--source-name": "random",
        }
        if command_case is not None:
            expected_options["--case"] = command_case
        for option, expected in expected_options.items():
            positions = [index for index, token in enumerate(command) if token == option]
            if len(positions) != 1 or positions[0] + 1 >= len(command):
                errors.append(f"command missing unique {option}")
            elif command[positions[0] + 1] != expected:
                errors.append(f"command {option} binding mismatch")
        module_index = command.index("-m") if "-m" in command else -1
        if (
            module_index < 0
            or module_index + 1 >= len(command)
            or command[module_index + 1]
            != "benchmarks.run_task038_full3d_lor_spectral_audit_v2"
        ):
            errors.append("command module entrypoint mismatch")


def _check_production_audit(record: dict[str, Any], errors: list[str], gates: list[str]) -> None:
    fixture_audit = record.get("fixture_audit")
    fixture_hx_audit = record.get("fixture_hx_audit")
    forbidden = record.get("forbidden")
    audit_assembly = record.get("audit_assembly")
    if (
        not isinstance(fixture_audit, dict)
        or not isinstance(fixture_hx_audit, dict)
        or not isinstance(forbidden, dict)
        or not isinstance(audit_assembly, dict)
    ):
        errors.append("fixture/forbidden audit missing")
        return
    required_false = (
        "high_order_global_aij",
        "global_transfer_matrix",
        "global_numeric_allgather",
    )
    for key in required_false:
        if key not in fixture_audit:
            errors.append(f"fixture_audit.{key} missing")
        elif fixture_audit[key] is not False:
            gates.append(f"fixture audit {key} is not false")
    for key, expected in (
        ("phase_application", "finalized_floquet_mpc_once"),
        ("slave_master_complete", True),
        ("raw_edge_orientation_consistent", True),
        ("raw_edge_orientation_owned_rows_closed", True),
    ):
        if key not in fixture_audit:
            errors.append(f"fixture_audit.{key} missing")
        elif fixture_audit[key] != expected:
            gates.append(f"fixture audit {key} is not closed")
    counts = [
        fixture_audit.get("raw_edge_orientation_factor_count"),
        fixture_audit.get("raw_edge_orientation_plus_count"),
        fixture_audit.get("raw_edge_orientation_minus_count"),
    ]
    if not all(isinstance(value, int) and value >= 0 for value in counts):
        errors.append("fixture orientation inventory counts are missing or invalid")
    elif counts[1] + counts[2] != counts[0]:
        errors.append("fixture orientation inventory counts do not close")
    if fixture_hx_audit.get("constructed") is not False:
        gates.append("audit-only fixture constructed HX")
    if forbidden.get("native_hx_constructed") is not False or forbidden.get(
        "scalar_node_matrix_constructed"
    ) is not False:
        gates.append("production HX/node construction was not closed")
    for key, expected in (
        ("production_high_order_global_aij", fixture_audit.get("high_order_global_aij")),
        ("production_global_transfer_matrix", fixture_audit.get("global_transfer_matrix")),
        ("production_numeric_allgather", fixture_audit.get("global_numeric_allgather")),
    ):
        if forbidden.get(key) != expected:
            errors.append(f"forbidden.{key} is not bound to fixture audit")
    if (
        audit_assembly.get("high_order_global_aij") is not True
        or audit_assembly.get("sparse_independent_transfer") is not True
        or audit_assembly.get("temporary_dense_transfer_for_rank_svd") is not True
        or audit_assembly.get("production_global_dense_transfer") is not False
        or audit_assembly.get("numeric_allgather") is not False
    ):
        gates.append("audit assembly boundary is not closed")


def _check_markers(
    record: dict[str, Any],
    raw_dir: Path,
    errors: list[str],
) -> None:
    descriptor = record.get("markers")
    required = {"relative_path", "sha256", "bytes", "lines"}
    if not isinstance(descriptor, dict) or set(descriptor) != required:
        errors.append("markers descriptor is missing or malformed")
        return
    relative_path = Path(str(descriptor["relative_path"]))
    if relative_path.is_absolute() or ".." in relative_path.parts:
        errors.append("markers path escapes raw_dir")
        return
    path = raw_dir / relative_path
    try:
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != descriptor["sha256"]:
            errors.append("markers SHA mismatch")
        if len(data) != int(descriptor["bytes"]):
            errors.append("markers byte count mismatch")
        rows = [json.loads(line) for line in data.decode("utf-8").splitlines() if line]
        if len(rows) != int(descriptor["lines"]):
            errors.append("markers line count mismatch")
        names = [row.get("stage") for row in rows]
        if names[:7] != [
            "paths_ready",
            "source_runtime_closed",
            "fixture_built",
            "layout_closed",
            "matrices_built",
            "actions_checked",
            "rank_spd_checked",
        ]:
            errors.append("markers prefix is not ordered")
        if len(names) != 9 or names[7] not in {"endpoints_solved", "endpoints_not_run"} or names[8] != "record_written":
            errors.append("markers do not close the individual worker lifecycle")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        errors.append(f"markers unreadable: {exc}")


def _check_record_arrays(record: dict[str, Any], low: dict[str, np.ndarray], high: dict[str, np.ndarray], matrices: dict[str, dict[str, Any]], errors: list[str], gates: list[str]) -> dict[str, Any]:
    raw_dir = Path(record["raw_dir"])
    artifacts = record.get("artifacts")
    if not isinstance(artifacts, dict):
        errors.append("artifact payload missing")
        return {}
    payload: dict[str, Any] = {}
    for name, descriptor in artifacts.items():
        if name.startswith("work_") or name in {"singular_values"}:
            value = _load_array(raw_dir, descriptor, f"artifacts.{name}", errors)
            if value is not None:
                payload[name] = value
    for name in ("high_probes", "high_action_expected", "high_action_observed", "pull_expected", "pull_observed", "low_probes"):
        descriptors = artifacts.get(name)
        if not isinstance(descriptors, list) or not descriptors:
            errors.append(f"artifacts.{name} missing")
            continue
        values = []
        for index, descriptor in enumerate(descriptors):
            value = _load_array(raw_dir, descriptor, f"artifacts.{name}[{index}]", errors)
            if value is not None:
                values.append(np.asarray(value, dtype=np.complex128))
        if values:
            payload[name] = np.asarray(values, dtype=np.complex128)
    for prefix, expected in (("low", low.get("low_active_raw_rows")), ("high", high.get("high_active_raw_rows"))):
        if expected is not None and payload.get(f"{prefix}_probes") is not None:
            expected_size = (
                int(expected.size)
                if prefix == "low"
                else int(matrices["B_H_full"]["rows"])
            )
            if payload[f"{prefix}_probes"].shape[1] != expected_size:
                errors.append(f"{prefix} probe dimension mismatch")
    if (
        payload.get("high_probes") is not None
        and payload.get("high_action_expected") is not None
        and payload["high_probes"].shape != payload["high_action_expected"].shape
    ):
        errors.append("high action probe payload shape mismatch")
    if (
        payload.get("high_action_expected") is not None
        and payload.get("high_action_observed") is not None
        and payload["high_action_expected"].shape
        != payload["high_action_observed"].shape
    ):
        errors.append("high action observed payload shape mismatch")
    if (
        payload.get("pull_expected") is not None
        and payload.get("pull_observed") is not None
        and payload["pull_expected"].shape != payload["pull_observed"].shape
    ):
        errors.append("A_pull observed payload shape mismatch")
    if payload.get("pull_expected") is not None and payload["pull_expected"].shape[1] != int(
        low["low_active_raw_rows"].size
    ):
        errors.append("A_pull payload dimension mismatch")
    work_names = sorted(name for name in payload if name.startswith("work_") and name.endswith("_high_primal"))
    for name in work_names:
        index = name.split("_")[1]
        keys = [f"work_{index}_{suffix}" for suffix in ("high_primal", "high_dual", "owner_primal", "owner_dual")]
        if not all(key in payload for key in keys):
            errors.append(f"work payload {index} incomplete")
            continue
        expected_sizes = {
            "high_primal": int(matrices["B_H_full"]["rows"]),
            "high_dual": int(matrices["B_H_full"]["rows"]),
            "owner_primal": int(low["low_active_raw_rows"].size),
            "owner_dual": int(low["low_active_raw_rows"].size),
        }
        for key, size in expected_sizes.items():
            payload_key = f"work_{index}_{key}"
            if payload_key not in payload:
                continue
            if payload[payload_key].ndim != 1 or payload[payload_key].size != size:
                errors.append(f"work payload {index} {key} dimension mismatch")
        lhs = np.vdot(payload[keys[0]], payload[keys[1]])
        rhs = np.vdot(payload[keys[2]], payload[keys[3]])
        value = abs(lhs - rhs) / max(abs(rhs), np.finfo(float).tiny)
        if value > WORK_LIMIT:
            gates.append(f"work identity {index}={value:.17g}")
    return payload


def _check_spectrum(record: dict[str, Any], matrices: dict[str, dict[str, Any]], low: dict[str, np.ndarray], high: dict[str, np.ndarray], payload: dict[str, Any], errors: list[str], gates: list[str]) -> dict[str, Any]:
    metrics: dict[str, Any] = {"tested_dimension": None, "numerical_rank": None}
    if not all(name in matrices for name in ("B_L_full", "B_H_full", "B_L_ind", "B_H_ind", "L")):
        errors.append("required matrix artifacts missing")
        return metrics
    bl_full = _csr_dense(matrices["B_L_full"])
    bh_full = _csr_dense(matrices["B_H_full"])
    bl_ind_stored = _csr_dense(matrices["B_L_ind"])
    bh_ind_stored = _csr_dense(matrices["B_H_ind"])
    l_matrix = matrices["L"]
    low_active = low.get("low_active_raw_rows")
    high_active = high.get("high_active_raw_rows")
    if low_active is None or high_active is None:
        return metrics
    bl_ind = bl_full[np.ix_(low_active, low_active)]
    bh_ind = bh_full[np.ix_(high_active, high_active)]
    if not np.allclose(bl_ind, bl_ind_stored, rtol=0.0, atol=1.0e-13):
        errors.append("B_L independent submatrix does not match full CSR")
    if not np.allclose(bh_ind, bh_ind_stored, rtol=0.0, atol=1.0e-13):
        errors.append("B_H independent submatrix does not match full CSR")
    if (int(l_matrix["rows"]), int(l_matrix["cols"])) != (high_active.size, low_active.size):
        errors.append("L dimension does not close independent spaces")
        return metrics
    if not np.all(np.isfinite(l_matrix["values"])) or not np.all(np.isfinite(bl_ind)) or not np.all(np.isfinite(bh_ind)):
        gates.append("non-finite audit matrix")
        return metrics
    singular_values = payload.get("singular_values")
    if singular_values is None:
        errors.append("singular_values artifact missing")
        return metrics
    recomputed_singular = np.linalg.svd(_csr_dense(l_matrix), compute_uv=False)
    if not np.allclose(recomputed_singular, singular_values, rtol=1.0e-12, atol=1.0e-13):
        gates.append("transfer singular values mismatch")
    sigma_max = float(np.max(recomputed_singular)) if recomputed_singular.size else 0.0
    tau = max(int(l_matrix["rows"]), int(l_matrix["cols"])) * np.finfo(float).eps * sigma_max
    rank = int(np.count_nonzero(recomputed_singular > tau))
    metrics["tested_dimension"] = int(low_active.size)
    metrics["rank_tau"] = tau
    metrics["numerical_rank"] = rank
    if rank != int(low_active.size):
        gates.append(f"transfer numerical rank {rank} != {low_active.size}")
    for name, matrix in (("B_H", bh_ind), ("B_L", bl_ind)):
        defect = _relative(matrix, matrix.conj().T, denominator=matrix)
        metrics[f"{name}_hermitian_defect"] = defect
        if defect > WORK_LIMIT:
            gates.append(f"{name} Hermitian defect={defect:.17g}")
    high_times_transfer = _csr_right_product(bh_ind, l_matrix)
    pulled = _csr_adjoint_left_product(l_matrix, high_times_transfer)
    high_probes = payload.get("high_probes")
    high_expected = payload.get("high_action_expected")
    high_observed = payload.get("high_action_observed")
    if high_probes is None or high_expected is None or high_observed is None:
        errors.append("high action probe evidence is incomplete")
    elif not (high_probes.shape == high_expected.shape == high_observed.shape) or high_probes.shape[1] != bh_full.shape[0]:
        errors.append("high action probe dimensions do not match B_H_full")
    else:
        for index, (probe, stored_expected, observed) in enumerate(
            zip(high_probes, high_expected, high_observed, strict=True)
        ):
            expected = bh_full @ probe
            if _relative(stored_expected, expected, denominator=expected) > HIGH_ACTION_LIMIT:
                gates.append(f"stored high action expectation mismatch {index}")
            if _relative(observed, expected, denominator=expected) > HIGH_ACTION_LIMIT:
                gates.append(f"matrix-free high action mismatch {index}")
    low_probes = payload.get("low_probes")
    pull_expected = payload.get("pull_expected")
    pull_observed = payload.get("pull_observed")
    if low_probes is None or pull_expected is None or pull_observed is None:
        errors.append("A_pull probe evidence is incomplete")
    elif not (low_probes.shape == pull_expected.shape == pull_observed.shape) or low_probes.shape[1] != int(l_matrix["cols"]):
        errors.append("A_pull probe dimensions do not match L")
    else:
        for index, (probe, stored_expected, observed) in enumerate(
            zip(low_probes, pull_expected, pull_observed, strict=True)
        ):
            expected = pulled @ probe
            if _relative(stored_expected, expected, denominator=expected) > WORK_LIMIT:
                gates.append(f"stored A_pull expectation mismatch {index}")
            if _relative(observed, expected, denominator=expected) > WORK_LIMIT:
                gates.append(f"A_pull route mismatch {index}")
    defect = _relative(pulled, pulled.conj().T, denominator=pulled)
    metrics["A_pull_hermitian_defect"] = defect
    if defect > WORK_LIMIT:
        gates.append(f"A_pull Hermitian defect={defect:.17g}")
    stored_spd = record.get("facts", {}).get("spd")
    if not isinstance(stored_spd, dict):
        errors.append("facts.spd missing")
        return metrics
    recomputed_spd: dict[str, bool] = {}
    for name, matrix in (("B_L", bl_ind), ("A_pull", pulled)):
        try:
            np.linalg.cholesky(matrix)
        except np.linalg.LinAlgError:
            recomputed_spd[name] = False
        else:
            recomputed_spd[name] = True
        if stored_spd.get(name, {}).get("positive_definite") is not recomputed_spd[name]:
            errors.append(f"facts.spd.{name} does not match raw Cholesky result")
    metrics["spd"] = recomputed_spd
    if not all(recomputed_spd.values()):
        gates.append("SPD/Cholesky failure")
        return metrics
    if record.get("facts", {}).get("spectral_status") != "solved":
        errors.append("spectral endpoints are missing despite positive definite raw matrices")
        return metrics
    chol = np.linalg.cholesky(bl_ind)
    inverse_chol = np.linalg.inv(chol)
    generalized = inverse_chol @ pulled @ inverse_chol.conj().T
    eigenvalues, _vectors = np.linalg.eigh(generalized)
    smallest = float(eigenvalues[0])
    largest = float(eigenvalues[-1])
    del chol, inverse_chol
    condition = largest / smallest if np.isfinite(largest) and np.isfinite(smallest) and smallest != 0.0 else None
    metrics["lambda_min"] = smallest
    metrics["lambda_max"] = largest
    metrics["condition"] = condition
    positive_threshold = max(float(low_active.size) * np.finfo(float).eps * largest, 0.0) if np.isfinite(largest) else None
    metrics["lambda_min_positive_threshold"] = positive_threshold
    if (
        not np.isfinite(largest)
        or not np.isfinite(smallest)
        or positive_threshold is None
        or smallest <= positive_threshold
        or largest < smallest
        or condition is None
        or not np.isfinite(condition)
    ):
        gates.append("generalized spectrum is not finite positive ordered")
    for name in ("smallest", "largest"):
        descriptor = record.get("spectral", {}).get(name)
        if not isinstance(descriptor, dict):
            errors.append(f"spectral.{name} missing")
            continue
        q = _load_array(Path(record["raw_dir"]), descriptor.get("vector"), f"spectral.{name}.vector", errors)
        aq_saved = _load_array(Path(record["raw_dir"]), descriptor.get("Aq"), f"spectral.{name}.Aq", errors)
        bq_saved = _load_array(Path(record["raw_dir"]), descriptor.get("Bq"), f"spectral.{name}.Bq", errors)
        if q is None or aq_saved is None or bq_saved is None:
            continue
        aq = pulled @ q
        bq = bl_ind @ q
        lam = float(np.real(np.vdot(q, aq) / np.vdot(q, bq)))
        residual = float(np.linalg.norm(aq - lam * bq) / max(float(np.linalg.norm(aq)), abs(lam) * float(np.linalg.norm(bq)), np.finfo(float).tiny))
        metrics[f"{name}_residual_relative"] = residual
        metrics[f"{name}_eigenvalue_recomputed"] = lam
        expected_endpoint = smallest if name == "smallest" else largest
        stored_eigenvalue = float(descriptor.get("eigenvalue", math.nan))
        if not np.isfinite(stored_eigenvalue) or abs(stored_eigenvalue - lam) > 1.0e-10 * max(abs(lam), 1.0):
            gates.append(f"{name} stored eigenvalue mismatch")
        if abs(lam - expected_endpoint) > 1.0e-10 * max(abs(expected_endpoint), 1.0):
            gates.append(f"{name} vector is not the fixed endpoint")
        if _relative(aq_saved, aq, denominator=aq) > EIGEN_RESIDUAL_LIMIT or _relative(bq_saved, bq, denominator=bq) > EIGEN_RESIDUAL_LIMIT:
            gates.append(f"{name} action artifact mismatch")
        if residual > EIGEN_RESIDUAL_LIMIT:
            gates.append(f"{name} eigen residual={residual:.17g}")
        if not np.isfinite(lam) or lam <= 0.0:
            gates.append(f"{name} eigenvalue is not finite positive")
    return metrics


def _check_watchdog(
    record: dict[str, Any],
    record_path: Path,
    watchdog_path: Path,
    errors: list[str],
    gates: list[str],
) -> dict[str, Any]:
    compact_path = Path(watchdog_path).resolve()
    try:
        compact = json.loads(compact_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"watchdog compact: {exc}")
        return {}
    if compact.get("schema") != WATCHDOG_SCHEMA:
        errors.append("watchdog schema mismatch")
    if compact.get("source_sha") != record.get("source", {}).get("expected_sha"):
        errors.append("watchdog source SHA mismatch")
    if compact.get("worker_record") != str(record_path.resolve()):
        errors.append("watchdog worker_record binding mismatch")
    if compact.get("worker_raw_dir") != str(Path(record["raw_dir"]).resolve()):
        errors.append("watchdog worker_raw_dir binding mismatch")
    if compact.get("worker_command") != record.get("command"):
        errors.append("watchdog worker_command does not exactly match record command")
    raw_path = Path(str(compact.get("watchdog_raw", ""))).resolve()
    try:
        raw_bytes = raw_path.read_bytes()
        samples = [
            json.loads(line)
            for line in raw_bytes.decode("utf-8").splitlines()
            if line
        ]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
        errors.append(f"watchdog raw: {exc}")
        return compact
    if _sha256(raw_path) != compact.get("raw_sha256"):
        errors.append("watchdog raw SHA mismatch")
    if compact.get("sample_count") != len(samples):
        errors.append("watchdog sample_count does not match raw")
    raw_status = bool(samples) and all(
        sample.get("authority", {}).get("process_tree", {}).get("all_status_readable")
        is True
        for sample in samples
    )
    if compact.get("all_status_readable") is not raw_status:
        errors.append("watchdog all_status_readable does not match raw")
    if compact.get("watchdog_poll_seconds") != WATCHDOG_POLL_SECONDS:
        errors.append("watchdog poll interval is not 0.25 seconds")
    if compact.get("watchdog_rss_limit_bytes") != WATCHDOG_RSS_LIMIT:
        errors.append("watchdog RSS limit is not 2000000000 bytes")
    rss_values: list[int] = []
    swap_values: list[int] = []
    for sample in samples:
        authority = sample.get("authority", {})
        tree = authority.get("process_tree", {})
        if tree.get("all_status_readable") is not True or int(tree.get("swap_bytes", -1)) != 0:
            gates.append("watchdog process-tree status unreadable or swap nonzero")
        rss = int(tree.get("rss_bytes", -1))
        swap = int(tree.get("swap_bytes", -1))
        if rss < 0:
            errors.append("watchdog process-tree RSS missing")
        else:
            rss_values.append(rss)
        if swap < 0:
            errors.append("watchdog process-tree swap missing")
        else:
            swap_values.append(swap)
        cgroup = authority.get("job_cgroup", {})
        if cgroup.get("dedicated_job_cgroup") is True and int(
            cgroup.get("swap_current_bytes", -1)
        ) != 0:
            gates.append("watchdog dedicated cgroup swap nonzero")
    peak = max(rss_values, default=-1)
    max_swap = max(swap_values, default=-1)
    if compact.get("peak_process_tree_rss_bytes") != peak:
        errors.append("watchdog peak RSS does not match raw")
    if compact.get("max_process_tree_swap_bytes") != max_swap:
        errors.append("watchdog max swap does not match raw")
    if compact.get("no_orphan") is not True:
        errors.append("watchdog no_orphan is not explicitly true")
    if compact.get("returncode") != 0 or compact.get("natural_exit") is not True:
        gates.append("watchdog worker did not naturally close with rc0")
    if compact.get("stop_reason") != "natural_exit":
        gates.append(f"watchdog stop reason is {compact.get('stop_reason')!r}")
    if peak < 0 or peak >= WATCHDOG_RSS_LIMIT:
        gates.append(f"watchdog process-tree RSS {peak} is outside the fixed limit")
    return {
        "source_sha": compact.get("source_sha"),
        "watchdog_compact_path": str(compact_path),
        "watchdog_compact_sha256": _sha256(compact_path),
        "watchdog_raw_path": str(raw_path),
        "watchdog_raw_sha256": compact.get("raw_sha256"),
        "watchdog_rss_limit_bytes": compact.get("watchdog_rss_limit_bytes"),
        "worker_command": compact.get("worker_command"),
        "sample_count": compact.get("sample_count"),
        "peak_process_tree_rss_bytes": compact.get("peak_process_tree_rss_bytes"),
        "max_process_tree_swap_bytes": compact.get("max_process_tree_swap_bytes"),
        "natural_exit": compact.get("natural_exit"),
        "no_orphan": compact.get("no_orphan"),
        "stop_reason": compact.get("stop_reason"),
    }


def _check_loaded_record(
    record: dict[str, Any],
    record_path: Path,
    expected_source_sha: str,
    *,
    watchdog_path: Path | None,
    command_case: str | None = None,
    command_raw_dir: Path | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    gates: list[str] = []
    record_path = Path(record_path).resolve()
    raw_dir = Path(str(record.get("raw_dir", ""))).resolve()
    if not raw_dir.is_dir():
        errors.append("raw_dir is missing")
    if raw_dir == record_path.parent:
        errors.append("raw_dir and record parent must be distinct")
    if record.get("record_path") != str(record_path):
        errors.append("record_path identity does not match checker input")
    _check_settings(
        record,
        record_path,
        raw_dir,
        expected_source_sha,
        errors,
        gates,
        command_case=command_case or record.get("case"),
        command_raw_dir=command_raw_dir,
    )
    _check_production_audit(record, errors, gates)
    record["raw_dir"] = str(raw_dir)
    _check_markers(record, raw_dir, errors)
    watchdog_metrics = (
        _check_watchdog(record, record_path, watchdog_path, errors, gates)
        if watchdog_path is not None
        else {}
    )
    matrices: dict[str, dict[str, Any]] = {}
    for name, descriptor in (record.get("matrix_artifacts") or {}).items():
        matrix = _load_csr(raw_dir, descriptor, f"matrix_artifacts.{name}", errors)
        if matrix is not None:
            matrices[name] = matrix
    low, high = _check_layout(record, matrices, errors, gates)
    payload = _check_record_arrays(record, low, high, matrices, errors, gates)
    metrics = _check_spectrum(record, matrices, low, high, payload, errors, gates)
    return {
        "schema": SCHEMA,
        "passed": not errors and not gates,
        "contract_errors": errors,
        "gate_failures": gates,
        "metrics": metrics,
        "resource": watchdog_metrics,
    }


def check_record(
    record_path: Path,
    watchdog_path: Path,
    expected_source_sha: str,
) -> dict[str, Any]:
    record_path = Path(record_path).resolve()
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "passed": False,
            "contract_errors": [f"record: {exc}"],
            "gate_failures": [],
            "metrics": {},
            "resource": {},
        }
    if record.get("schema") != SCHEMA:
        return {
            "passed": False,
            "contract_errors": ["schema is not an individual S1 record"],
            "gate_failures": [],
            "metrics": {},
            "resource": {},
        }
    return _check_loaded_record(
        record,
        record_path,
        expected_source_sha,
        watchdog_path=Path(watchdog_path).resolve(),
    )


def check_batch(
    record_path: Path,
    watchdog_path: Path,
    expected_source_sha: str,
) -> dict[str, Any]:
    record_path = Path(record_path).resolve()
    errors: list[str] = []
    gates: list[str] = []
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"passed": False, "contract_errors": [f"record: {exc}"], "gate_failures": [], "cases": []}
    if record.get("schema") != BATCH_SCHEMA or record.get("stage") != STAGE or record.get("case") != "batch":
        errors.append("batch schema/stage/case mismatch")
    if record.get("record_path") != str(record_path):
        errors.append("batch record_path identity mismatch")
    batch_raw = Path(str(record.get("raw_dir", ""))).resolve()
    if not batch_raw.is_dir():
        errors.append("batch raw_dir is missing")
    if batch_raw == record_path.parent:
        errors.append("batch raw_dir and record parent must be distinct")
    marker = record.get("markers")
    if not isinstance(marker, dict) or set(marker) != {"relative_path", "sha256", "bytes", "lines"}:
        errors.append("batch marker descriptor is missing")
    else:
        marker_path = batch_raw / str(marker["relative_path"])
        try:
            marker_bytes = marker_path.read_bytes()
            marker_rows = [
                json.loads(line)
                for line in marker_bytes.decode("utf-8").splitlines()
                if line
            ]
            if hashlib.sha256(marker_bytes).hexdigest() != marker["sha256"]:
                errors.append("batch marker SHA mismatch")
            if len(marker_bytes) != int(marker["bytes"]) or len(marker_rows) != int(marker["lines"]):
                errors.append("batch marker size mismatch")
            if [row.get("stage") for row in marker_rows] != ["batch_record_written"]:
                errors.append("batch marker lifecycle is not closed")
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            errors.append(f"batch marker unreadable: {exc}")
    source = record.get("source")
    if (
        not isinstance(source, dict)
        or source.get("expected_sha") != expected_source_sha
        or source.get("commit_sha_start") != expected_source_sha
        or source.get("commit_sha_end") != expected_source_sha
        or source.get("clean_start") is not True
        or source.get("clean_end") is not True
    ):
        errors.append("batch source identity is not closed")
    if not isinstance(source, dict) or source.get("branch") != BRANCH:
        errors.append("batch source branch identity mismatch")
    runtime = record.get("runtime")
    if (
        not isinstance(runtime, dict)
        or runtime.get("qualified_activation") != "1"
        or runtime.get("petsc_scalar_type") != "complex128"
        or runtime.get("petsc_int_type") != "int32"
        or int(runtime.get("mpi_size", -1)) != 1
        or runtime.get("threads")
        != {"OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1"}
    ):
        errors.append("batch runtime identity is not closed")
    command = record.get("command")
    if not isinstance(command, list) or not command or not Path(str(command[0])).is_absolute():
        errors.append("batch command executable must be absolute")
    elif any(not isinstance(item, str) for item in command):
        errors.append("batch command argv is not string-valued")
    else:
        for option, expected in {
            "--stage": STAGE,
            "--case": "batch",
            "--source-name": "random",
            "--raw-dir": str(batch_raw),
            "--record": str(record_path),
            "--expected-source-sha": expected_source_sha,
            "--expected-mpi-size": "1",
        }.items():
            positions = [index for index, token in enumerate(command) if token == option]
            if len(positions) != 1 or positions[0] + 1 >= len(command):
                errors.append(f"batch command missing unique {option}")
            elif command[positions[0] + 1] != expected:
                errors.append(f"batch command {option} binding mismatch")
        module_index = command.index("-m") if "-m" in command else -1
        if (
            module_index < 0
            or module_index + 1 >= len(command)
            or command[module_index + 1]
            != "benchmarks.run_task038_full3d_lor_spectral_audit_v2"
        ):
            errors.append("batch command module entrypoint mismatch")
    if not isinstance(record.get("cases"), list):
        errors.append("batch cases are missing")
        return {"passed": False, "contract_errors": errors, "gate_failures": gates, "cases": []}
    if [item.get("case") for item in record["cases"]] != ["p2-mpi1", "p3-mpi1"][: len(record["cases"])]:
        errors.append("batch case order is not frozen")
    completed = [item.get("case") for item in record["cases"]]
    if record.get("completed_cases") != completed:
        errors.append("batch completed_cases does not match record cases")
    if any(item in completed for item in record.get("not_run_cases", [])):
        errors.append("batch not_run_cases overlaps completed cases")
    resource = _check_watchdog(record, record_path, Path(watchdog_path).resolve(), errors, gates)
    case_results: list[dict[str, Any]] = []
    for item in record["cases"]:
        case_raw = Path(str(item.get("raw_dir", ""))).resolve()
        if batch_raw not in case_raw.parents:
            errors.append(f"batch case raw_dir escapes campaign root: {case_raw}")
        case_results.append(
            _check_loaded_record(
                item,
                record_path,
                expected_source_sha,
                watchdog_path=None,
                command_case="batch",
                command_raw_dir=batch_raw,
            )
        )
    if len(record["cases"]) < 2 and not (
        case_results and case_results[0]["gate_failures"] and record.get("stop_reason")
    ):
        errors.append("batch stopped before both fixed cases without a prior-case Gate fact")
    for result in case_results:
        if result["contract_errors"]:
            errors.extend(f"{result['schema']}: {item}" for item in result["contract_errors"])
        if result["gate_failures"]:
            gates.extend(f"{result['schema']}: {item}" for item in result["gate_failures"])
    return {
        "schema": BATCH_SCHEMA,
        "passed": not errors and not gates,
        "contract_errors": errors,
        "gate_failures": gates,
        "resource": resource,
        "cases": case_results,
        "condition_growth": (
            case_results[-1]["metrics"].get("condition")
            / case_results[0]["metrics"].get("condition")
            if len(case_results) == 2
            and case_results[0]["metrics"].get("condition")
            and case_results[-1]["metrics"].get("condition")
            else None
        ),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--watchdog", required=True, type=Path)
    parser.add_argument("--expected-source-sha", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        schema = json.loads(args.record.read_text(encoding="utf-8")).get("schema")
    except (OSError, json.JSONDecodeError):
        schema = None
    result = (
        check_batch(args.record, args.watchdog, args.expected_source_sha)
        if schema == BATCH_SCHEMA
        else check_record(args.record, args.watchdog, args.expected_source_sha)
    )
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite checker output {args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
