"""Read-only checker for the owner-space LOR spectral audit."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np


SCHEMA = "task038.lor-native-complex-hx.global-spectral-audit.v1"
STAGE = "global-spectral-audit"
CASE = "p3-mpi1"
DEGREE = 3
H_NM = 50.0
FULL_EDGE_ROWS = 3018
SLAVE_EDGE_ROWS = 480
INDEPENDENT_EDGE_ROWS = 2538
LINEARITY_ALPHA = 0.37 + 0.19j
LINEARITY_BETA = -0.23 + 0.41j
WORK_LIMIT = 1.0e-12
LINEARITY_LIMIT = 1.0e-12
REPEAT_LIMIT = 1.0e-13
EIGEN_RESIDUAL_LIMIT = 1.0e-10
SPECTRAL_CONDITION_LIMIT = 100.0
EPS_TOL = 1.0e-10
EPS_MAX_IT = 500
EPS_NEV = 1
EPS_NCV = 21
EPS_ST_TYPE = "shift"
EPS_SHIFT = 0.0
EPS_KSP_TYPE = "preonly"
EPS_PC_TYPE = "lu"
EPS_FACTOR_SOLVER = "mumps"
WATCHDOG_SCHEMA = "task038.lor-native-complex-hx.foundation-e-watchdog.v1"
WATCHDOG_POLL_SECONDS = 0.25
WATCHDOG_RSS_LIMIT = 500_000_000
BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _finite_sha(value: Any, length: int) -> bool:
    text = str(value)
    return len(text) == length and all(char in "0123456789abcdef" for char in text)


def _relative(left: np.ndarray, right: np.ndarray, denominator: np.ndarray | None = None) -> float:
    left = np.asarray(left, dtype=np.complex128)
    right = np.asarray(right, dtype=np.complex128)
    base = right if denominator is None else np.asarray(denominator, dtype=np.complex128)
    return float(np.linalg.norm(left - right) / max(np.linalg.norm(base), np.finfo(float).tiny))


def _scalar_relative(left: complex, right: complex) -> float:
    return float(abs(complex(left) - complex(right)) / max(abs(complex(right)), np.finfo(float).tiny))


def _inside(base: Path, path: Path) -> bool:
    try:
        path.relative_to(base)
    except ValueError:
        return False
    return True


def _load_array(raw_dir: Path, descriptor: Any, errors: list[str], label: str) -> np.ndarray | None:
    if not isinstance(descriptor, dict):
        errors.append(f"{label}: missing descriptor")
        return None
    relative = descriptor.get("relative_path")
    if not isinstance(relative, str) or Path(relative).is_absolute():
        errors.append(f"{label}: path is not a relative filename")
        return None
    path = (raw_dir / relative).resolve()
    if not _inside(raw_dir.resolve(), path) or not path.is_file():
        errors.append(f"{label}: artifact missing or outside raw_dir")
        return None
    try:
        if int(descriptor.get("bytes", -1)) != path.stat().st_size:
            errors.append(f"{label}: byte count mismatch")
        if str(descriptor.get("sha256")) != _sha256(path):
            errors.append(f"{label}: SHA256 mismatch")
        values = np.asarray(np.load(path, allow_pickle=False))
    except (OSError, ValueError) as exc:
        errors.append(f"{label}: unreadable: {exc}")
        return None
    if str(values.dtype) != str(descriptor.get("dtype")):
        errors.append(f"{label}: dtype mismatch")
    if list(values.shape) != list(descriptor.get("shape", [])):
        errors.append(f"{label}: shape mismatch")
    if values.dtype.kind not in "OUS" and not np.all(np.isfinite(values)):
        errors.append(f"{label}: non-finite values")
    return values


def _load_vector(
    raw_dir: Path,
    artifacts: dict[str, Any],
    name: str,
    errors: list[str],
    *,
    expected_coordinate: str,
    expected_dtype: str,
) -> np.ndarray | None:
    item = artifacts.get(name)
    if not isinstance(item, dict):
        errors.append(f"missing vector artifact {name}")
        return None
    values = _load_array(raw_dir, item.get("values"), errors, f"{name}.values")
    coordinate = item.get("coordinate")
    if coordinate != expected_coordinate:
        errors.append(f"{name}: coordinate role mismatch")
    if values is None:
        return None
    if str(values.dtype) != expected_dtype:
        errors.append(f"{name}: dtype role mismatch")
    return np.asarray(values, dtype=np.int64 if expected_dtype == "int64" else np.complex128)


def _load_layout(record: dict[str, Any], raw_dir: Path, errors: list[str]) -> dict[str, np.ndarray] | None:
    layout = record.get("layout")
    if not isinstance(layout, dict):
        errors.append("missing layout")
        return None
    if (layout.get("full_rows"), layout.get("slave_rows"), layout.get("owner_count")) != (
        FULL_EDGE_ROWS,
        SLAVE_EDGE_ROWS,
        INDEPENDENT_EDGE_ROWS,
    ):
        errors.append("full/slave/independent layout dimensions mismatch")
    active = _load_array(raw_dir, layout.get("active_raw_rows"), errors, "layout.active_raw_rows")
    slave = _load_array(raw_dir, layout.get("slave_raw_rows"), errors, "layout.slave_raw_rows")
    canonical = _load_array(raw_dir, layout.get("canonical_ids"), errors, "layout.canonical_ids")
    owners = _load_array(raw_dir, layout.get("owner_ids"), errors, "layout.owner_ids")
    phase_codes = _load_array(raw_dir, layout.get("phase_codes"), errors, "layout.phase_codes")
    if any(value is None for value in (active, slave, canonical, owners, phase_codes)):
        return None
    if any(np.asarray(value).dtype.kind not in "iu" for value in (active, slave, canonical, owners, phase_codes)):
        errors.append("layout row/phase inventories are not integer arrays")
    active = np.asarray(active, dtype=np.int64)
    slave = np.asarray(slave, dtype=np.int64)
    canonical = np.asarray(canonical, dtype=np.int64)
    owners = np.asarray(owners, dtype=np.int64)
    phase_codes = np.asarray(phase_codes)
    if active.size != INDEPENDENT_EDGE_ROWS or slave.size != SLAVE_EDGE_ROWS:
        errors.append("layout artifact sizes do not match frozen dimensions")
    if np.unique(active).size != active.size or np.any(active < 0) or np.any(active >= FULL_EDGE_ROWS):
        errors.append("active raw rows are not unique/in range")
    if np.unique(slave).size != slave.size or np.any(slave < 0) or np.any(slave >= FULL_EDGE_ROWS):
        errors.append("slave raw rows are not unique/in range")
    if set(active.tolist()) & set(slave.tolist()) or set(active.tolist()) | set(slave.tolist()) != set(range(FULL_EDGE_ROWS)):
        errors.append("active/slave raw row partition is not exact")
    if canonical.size != active.size or owners.size != active.size:
        errors.append("canonical/owner arrays do not match active rows")
    if np.unique(canonical).size != canonical.size or np.unique(owners).size != owners.size:
        errors.append("canonical or owner IDs are not unique")
    if set(canonical.tolist()) != set(owners.tolist()):
        errors.append("active raw rows and canonical owner IDs are not a bijection")
    if phase_codes.size != active.size or phase_codes.dtype.kind not in "iu" or np.any(phase_codes != 0):
        errors.append("active raw phase-code artifact is not a zero-valued int inventory")
    if layout.get("bijection") is not True:
        errors.append("worker did not report a closed owner bijection")
    return {
        "active": active,
        "slave": slave,
        "canonical": canonical,
        "owners": owners,
        "phase_codes": phase_codes,
    }


def _load_high_layout(
    record: dict[str, Any], raw_dir: Path, errors: list[str]
) -> dict[str, Any] | None:
    layout = record.get("high_layout")
    if not isinstance(layout, dict):
        errors.append("missing high_layout")
        return None
    if (
        layout.get("full_rows"),
        layout.get("slave_rows"),
        layout.get("independent_rows"),
    ) != (FULL_EDGE_ROWS, SLAVE_EDGE_ROWS, INDEPENDENT_EDGE_ROWS):
        errors.append("high full/slave/independent dimensions mismatch")
    slave = _load_array(raw_dir, layout.get("slave_raw_rows"), errors, "high_layout.slave_raw_rows")
    if slave is None:
        return None
    if np.asarray(slave).dtype.kind not in "iu":
        errors.append("high slave rows are not an integer array")
    slave = np.asarray(slave, dtype=np.int64)
    if (
        slave.size != SLAVE_EDGE_ROWS
        or np.unique(slave).size != slave.size
        or np.any(slave < 0)
        or np.any(slave >= FULL_EDGE_ROWS)
    ):
        errors.append("high slave rows are not unique/in range")
    active = np.asarray(
        [row for row in range(FULL_EDGE_ROWS) if row not in set(slave.tolist())],
        dtype=np.int64,
    )
    if active.size != INDEPENDENT_EDGE_ROWS:
        errors.append("high full/slave partition does not close")
    return {"full_rows": FULL_EDGE_ROWS, "slave": slave, "active": active}


def _load_csr(record: dict[str, Any], raw_dir: Path, errors: list[str]) -> dict[str, Any] | None:
    matrix = record.get("matrix_artifacts", {}).get("B_L_ind")
    if not isinstance(matrix, dict):
        errors.append("missing B_L_ind matrix artifact")
        return None
    if (matrix.get("rows"), matrix.get("cols")) != (INDEPENDENT_EDGE_ROWS, INDEPENDENT_EDGE_ROWS):
        errors.append("B_L_ind dimensions mismatch")
    if "aij" not in str(matrix.get("type", "")).lower():
        errors.append("B_L_ind is not a sparse AIJ matrix")
    indptr = _load_array(raw_dir, matrix.get("indptr"), errors, "B_L_ind.indptr")
    indices = _load_array(raw_dir, matrix.get("indices"), errors, "B_L_ind.indices")
    values = _load_array(raw_dir, matrix.get("values"), errors, "B_L_ind.values")
    row_keys = _load_array(raw_dir, matrix.get("row_keys"), errors, "B_L_ind.row_keys")
    if any(value is None for value in (indptr, indices, values, row_keys)):
        return None
    if np.asarray(indptr).dtype.kind not in "iu" or np.asarray(indices).dtype.kind not in "iu" or np.asarray(row_keys).dtype.kind not in "iu":
        errors.append("B_L_ind CSR indices/row keys are not integer arrays")
    if np.asarray(values).dtype != np.dtype(np.complex128):
        errors.append("B_L_ind CSR values are not complex128")
    indptr = np.asarray(indptr, dtype=np.int64)
    indices = np.asarray(indices, dtype=np.int64)
    values = np.asarray(values, dtype=np.complex128)
    row_keys = np.asarray(row_keys, dtype=np.int64)
    if indptr.size != INDEPENDENT_EDGE_ROWS + 1 or indptr[0] != 0 or indptr[-1] != values.size:
        errors.append("B_L_ind CSR pointer/nnz mismatch")
    if np.any(np.diff(indptr) < 0) or np.any(indices < 0) or np.any(indices >= INDEPENDENT_EDGE_ROWS):
        errors.append("B_L_ind CSR indices are invalid")
    if row_keys.size != INDEPENDENT_EDGE_ROWS:
        errors.append("B_L_ind row-key count mismatch")
    return {"indptr": indptr, "indices": indices, "values": values, "row_keys": row_keys}


def _csr_matvec(matrix: dict[str, Any], vector: np.ndarray) -> np.ndarray:
    result = np.zeros(matrix["indptr"].size - 1, dtype=np.complex128)
    for row in range(result.size):
        start, stop = int(matrix["indptr"][row]), int(matrix["indptr"][row + 1])
        result[row] = np.dot(matrix["values"][start:stop], vector[matrix["indices"][start:stop]])
    return result


def _check_settings(record: dict[str, Any], errors: list[str]) -> None:
    settings = record.get("settings")
    expected = {
        "owner_coordinate": "increasing_raw_active_edge_row",
        "full_edge_rows": FULL_EDGE_ROWS,
        "slave_edge_rows": SLAVE_EDGE_ROWS,
        "independent_edge_rows": INDEPENDENT_EDGE_ROWS,
        "linearity_alpha": [float(LINEARITY_ALPHA.real), float(LINEARITY_ALPHA.imag)],
        "linearity_beta": [float(LINEARITY_BETA.real), float(LINEARITY_BETA.imag)],
        "slepc_problem_type": "GHEP",
        "slepc_type": "KRYLOVSCHUR",
        "slepc_nev": EPS_NEV,
        "slepc_ncv": EPS_NCV,
        "slepc_tol": EPS_TOL,
        "slepc_max_it": EPS_MAX_IT,
        "slepc_st_type": EPS_ST_TYPE,
        "slepc_shift": EPS_SHIFT,
        "slepc_ksp_type": EPS_KSP_TYPE,
        "slepc_pc_type": EPS_PC_TYPE,
        "slepc_factor_solver": EPS_FACTOR_SOLVER,
        "spectral_condition_limit": SPECTRAL_CONDITION_LIMIT,
        "work_limit": WORK_LIMIT,
        "linearity_limit": LINEARITY_LIMIT,
        "repeat_limit": REPEAT_LIMIT,
        "eigen_residual_limit": EIGEN_RESIDUAL_LIMIT,
    }
    if not isinstance(settings, dict):
        errors.append("missing settings")
        return
    for key, value in expected.items():
        if settings.get(key) != value:
            errors.append(f"settings.{key} mismatch")


def _check_watchdog(
    record: dict[str, Any],
    record_path: Path,
    watchdog_path: Path,
    errors: list[str],
    gates: list[str],
) -> dict[str, Any]:
    if not watchdog_path.is_file():
        errors.append("missing external foundation watchdog compact")
        return {}
    try:
        compact = json.loads(watchdog_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"watchdog compact unreadable: {exc}")
        return {}
    if compact.get("schema") != WATCHDOG_SCHEMA:
        errors.append("watchdog schema mismatch")
    if compact.get("source_sha") != record.get("source", {}).get("expected_sha"):
        errors.append("watchdog source SHA binding mismatch")
    if compact.get("worker_record") != str(record_path.resolve()):
        errors.append("watchdog worker record binding mismatch")
    if compact.get("worker_raw_dir") != str(Path(str(record.get("raw_dir", ""))).resolve()):
        errors.append("watchdog worker raw_dir binding mismatch")
    if compact.get("worker_command") != record.get("command"):
        errors.append("watchdog worker command binding mismatch")
    raw_value = compact.get("watchdog_raw")
    raw_path = Path(str(raw_value)).resolve() if isinstance(raw_value, str) else None
    if raw_path is None or not raw_path.is_file():
        errors.append("watchdog raw ledger missing")
        return compact
    try:
        raw_bytes = raw_path.read_bytes()
        samples = [json.loads(line) for line in raw_bytes.decode().splitlines() if line]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
        errors.append(f"watchdog raw ledger unreadable: {exc}")
        return compact
    if compact.get("raw_sha256") != hashlib.sha256(raw_bytes).hexdigest():
        errors.append("watchdog raw SHA mismatch")
    if compact.get("sample_count") != len(samples) or len(samples) == 0:
        errors.append("watchdog sample_count does not match nonempty raw ledger")
    raw_status = bool(samples) and all(
        sample.get("authority", {}).get("process_tree", {}).get("all_status_readable") is True
        for sample in samples
    )
    if compact.get("all_status_readable") is not raw_status:
        errors.append("watchdog all_status_readable does not match raw ledger")
    if compact.get("watchdog_poll_seconds") != WATCHDOG_POLL_SECONDS:
        errors.append("watchdog poll interval mismatch")
    if compact.get("watchdog_rss_limit_bytes") != WATCHDOG_RSS_LIMIT:
        errors.append("watchdog RSS limit mismatch")
    rss_values: list[int] = []
    swap_values: list[int] = []
    for sample in samples:
        tree = sample.get("authority", {}).get("process_tree", {})
        if tree.get("all_status_readable") is not True or int(tree.get("swap_bytes", -1)) != 0:
            gates.append("watchdog process-tree status unreadable or swap nonzero")
        rss = int(tree.get("rss_bytes", -1))
        swap = int(tree.get("swap_bytes", -1))
        if rss < 0 or swap < 0:
            errors.append("watchdog process-tree RSS/swap sample is missing")
        else:
            rss_values.append(rss)
            swap_values.append(swap)
        cgroup = sample.get("authority", {}).get("job_cgroup", {})
        if cgroup.get("dedicated_job_cgroup") is True and int(cgroup.get("swap_current_bytes", -1)) != 0:
            gates.append("watchdog dedicated cgroup swap nonzero")
    peak = max(rss_values, default=-1)
    max_swap = max(swap_values, default=-1)
    if compact.get("peak_process_tree_rss_bytes") != peak:
        errors.append("watchdog peak RSS does not match raw ledger")
    if compact.get("max_process_tree_swap_bytes") != max_swap:
        errors.append("watchdog max swap does not match raw ledger")
    if compact.get("no_orphan") is not True:
        errors.append("watchdog no_orphan is not explicitly true")
    if compact.get("natural_exit") is not True or compact.get("returncode") != 0:
        gates.append("watchdog worker did not close with natural rc0")
    if compact.get("stop_reason") != "natural_exit":
        gates.append(f"watchdog stop reason is {compact.get('stop_reason')!r}")
    if peak < 0 or peak >= WATCHDOG_RSS_LIMIT:
        gates.append(f"watchdog process-tree peak RSS {peak} violates {WATCHDOG_RSS_LIMIT}")
    return compact


def _check_provenance(record: dict[str, Any], record_path: Path, expected_source_sha: str | None, errors: list[str]) -> Path | None:
    if record.get("schema") != SCHEMA or record.get("stage") != STAGE or record.get("case") != CASE:
        errors.append("schema/stage/case mismatch")
    if record.get("degree") != DEGREE or float(record.get("h_nm", np.nan)) != H_NM:
        errors.append("degree/h_nm mismatch")
    if record.get("source_name") != "random" or record.get("variant") != "sequential-v1" or record.get("mpi_size") != 1:
        errors.append("source/variant/MPI mismatch")
    if record.get("record_path") != str(record_path.resolve()):
        errors.append("record_path provenance mismatch")
    source = record.get("source")
    source_sha = source.get("expected_sha") if isinstance(source, dict) else None
    if not _finite_sha(source_sha, 40):
        errors.append("source SHA is not lowercase 40-hex")
    if expected_source_sha is not None and source_sha != expected_source_sha:
        errors.append("source SHA differs from checker argument")
    if not isinstance(source, dict) or source.get("branch") != BRANCH or source.get("clean_start") is not True or source.get("clean_end") is not True:
        errors.append("source branch/clean provenance mismatch")
    command = record.get("command")
    expected_tail = [
        "-m", "benchmarks.run_task038_full3d_lor_spectral_audit", "--stage", STAGE,
        "--case", CASE, "--raw-dir", str(Path(str(record.get("raw_dir", ""))).resolve()),
        "--record", str(record_path.resolve()), "--expected-source-sha", str(source_sha),
        "--expected-mpi-size", "1",
    ]
    if not isinstance(command, list) or len(command) != len(expected_tail) + 1 or command[1:] != expected_tail or not isinstance(command[0], str) or not Path(command[0]).is_absolute():
        errors.append("worker command is not the fixed ordered invocation")
    runtime = record.get("runtime")
    if not isinstance(runtime, dict):
        errors.append("runtime identity missing")
    else:
        for key, value in (("qualified_activation", "1"), ("mpi_size", 1), ("petsc_scalar_type", "complex128"), ("petsc_int_type", "int32")):
            if runtime.get(key) != value:
                errors.append(f"runtime.{key} mismatch")
        threads = runtime.get("threads")
        if not isinstance(threads, dict) or any(threads.get(key) != "1" for key in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS")):
            errors.append("thread contract mismatch")
    provenance = record.get("provenance")
    if not isinstance(provenance, dict):
        errors.append("provenance missing")
    else:
        for key in ("input_identity_sha256", "operator_identity_sha256", "physical_model_sha256"):
            if not _finite_sha(provenance.get(key), 64):
                errors.append(f"invalid {key}")
    raw_value = record.get("raw_dir")
    if not isinstance(raw_value, str):
        errors.append("raw_dir missing")
        return None
    raw_dir = Path(raw_value).resolve()
    if not raw_dir.is_dir() or raw_dir == record_path.parent.resolve():
        errors.append("raw_dir is missing or malformed")
        return None
    return raw_dir


def check_record(
    record_path: Path, watchdog_path: Path, expected_source_sha: str | None = None
) -> dict[str, Any]:
    record_path = Path(record_path).resolve()
    errors: list[str] = []
    gates: list[str] = []
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"passed": False, "contract_errors": [f"record unreadable: {exc}"], "gate_failures": []}
    raw_dir = _check_provenance(record, record_path, expected_source_sha, errors)
    _check_settings(record, errors)
    watchdog_compact = _check_watchdog(
        record, record_path, watchdog_path.resolve(), errors, gates
    )
    layout = _load_layout(record, raw_dir, errors) if raw_dir is not None else None
    matrix = _load_csr(record, raw_dir, errors) if raw_dir is not None else None
    high_layout = _load_high_layout(record, raw_dir, errors) if raw_dir is not None else None
    artifacts = record.get("artifacts")
    if not isinstance(artifacts, dict):
        errors.append("missing artifacts")
        artifacts = {}

    required = {
        "source_before", "source_after", "source_action", "source_action_repeat",
        "q1", "q1_after", "q2", "q2_after", "q_combined", "q_combined_after",
        "A_q1", "A_q1_repeat", "A_q2", "A_q_combined",
        "B_q1", "B_q2", "B_q_combined", "work_h1", "work_h2", "work_lq1", "work_lq2",
        "work_lstar_h1", "work_lstar_h2", "route_low_ids", "route_high_ids",
        "eigen_smallest_q", "eigen_smallest_Aq", "eigen_smallest_Bq",
        "eigen_largest_q", "eigen_largest_Aq", "eigen_largest_Bq",
    }
    if set(artifacts) != required:
        errors.append("artifact role set mismatch")
    high_names = {
        "source_before", "source_after", "source_action", "source_action_repeat",
        "work_h1", "work_h2", "work_lq1", "work_lq2",
    }
    route_names = {"route_low_ids", "route_high_ids"}
    loaded: dict[str, np.ndarray | None] = {}
    if raw_dir is not None:
        for name in required:
            if name in high_names:
                coordinate, dtype = "high_raw_owned", "complex128"
            elif name in route_names:
                coordinate, dtype = "canonical_owner_id", "int64"
            else:
                coordinate, dtype = "independent_raw_active_row", "complex128"
            loaded[name] = _load_vector(
                raw_dir,
                artifacts,
                name,
                errors,
                expected_coordinate=coordinate,
                expected_dtype=dtype,
            )
    if layout is not None and high_layout is not None and matrix is not None and all(loaded.get(name) is not None for name in required):
        q1 = loaded["q1"]
        q2 = loaded["q2"]
        q_combined = loaded["q_combined"]
        if any(np.asarray(loaded[name]).size != FULL_EDGE_ROWS for name in high_names):
            errors.append("high-space artifact has wrong full-row length")
        if any(np.asarray(loaded[name]).size != INDEPENDENT_EDGE_ROWS for name in required - high_names):
            errors.append("owner-space artifact has wrong independent-row length")
        if not np.array_equal(matrix["row_keys"], layout["active"]):
            errors.append("B_L_ind row keys do not equal active raw rows")
        bq1 = _csr_matvec(matrix, q1)
        bq2 = _csr_matvec(matrix, q2)
        bqc = _csr_matvec(matrix, q_combined)
        metrics = {
            "source_unchanged_relative": _relative(loaded["source_after"], loaded["source_before"]),
            "high_action_repeat_relative": _relative(loaded["source_action"], loaded["source_action_repeat"]),
            "q_combined_relative": _relative(
                q_combined,
                LINEARITY_ALPHA * q1 + LINEARITY_BETA * q2,
            ),
            "A_linearity_relative": _relative(
                loaded["A_q_combined"],
                LINEARITY_ALPHA * loaded["A_q1"]
                + LINEARITY_BETA * loaded["A_q2"],
            ),
            "A_repeat_relative": _relative(loaded["A_q1"], loaded["A_q1_repeat"]),
            "A_input_unchanged_relative": max(_relative(loaded["q1_after"], q1), _relative(loaded["q2_after"], q2), _relative(loaded["q_combined_after"], q_combined)),
            "B_q1_stored_relative": _relative(loaded["B_q1"], bq1),
            "B_q2_stored_relative": _relative(loaded["B_q2"], bq2),
            "B_q_combined_stored_relative": _relative(loaded["B_q_combined"], bqc),
            "work_q1_relative": _scalar_relative(np.vdot(loaded["work_lq1"], loaded["work_h1"]), np.vdot(q1, loaded["work_lstar_h1"])),
            "work_q2_relative": _scalar_relative(np.vdot(loaded["work_lq2"], loaded["work_h2"]), np.vdot(q2, loaded["work_lstar_h2"])),
            "A_hermitian_probe_relative": _scalar_relative(np.vdot(q1, loaded["A_q2"]), np.vdot(loaded["A_q1"], q2)),
            "B_hermitian_probe_relative": _scalar_relative(np.vdot(q1, bq2), np.vdot(bq1, q2)),
        }
        route = record.get("route_audit", {})
        if route.get("owner_count") != INDEPENDENT_EDGE_ROWS:
            errors.append("route_audit owner count mismatch")
        for name in ("route_low_ids", "route_high_ids"):
            if not np.array_equal(np.sort(loaded[name].real.astype(np.int64)), np.sort(layout["owners"])):
                errors.append(f"{name} owner inventory mismatch")
        for name in ("owner_inventory_equal", "high_to_lor_owner_route", "lor_to_high_owner_route", "owner_ids_unique", "canonical_owner_bijection", "orientation_consistent", "slave_master_complete"):
            if route.get(name) is not True:
                errors.append(f"route_audit.{name} is not true")
        if route.get("phase_application") != "finalized_floquet_mpc_once":
            errors.append("route phase application mismatch")
        if layout["phase_codes"].dtype.kind not in "iu" or np.any(layout["phase_codes"] != 0):
            errors.append("active phase codes are not a zero-valued integer inventory")
        fixture_audit = record.get("fixture_audit")
        if not isinstance(fixture_audit, dict):
            errors.append("fixture audit missing")
            fixture_audit = {}
        if fixture_audit.get("lor_full_edge_rows") != FULL_EDGE_ROWS or fixture_audit.get("lor_edge_slave_rows") != SLAVE_EDGE_ROWS:
            errors.append("fixture audit row dimensions mismatch")
        if fixture_audit.get("high_space_global_rows") != FULL_EDGE_ROWS:
            errors.append("fixture audit high-space row dimension mismatch")
        if (
            high_layout["full_rows"],
            high_layout["slave"].size,
            high_layout["active"].size,
        ) != (FULL_EDGE_ROWS, SLAVE_EDGE_ROWS, INDEPENDENT_EDGE_ROWS):
            errors.append("high-space row partition mismatch")
        if fixture_audit.get("slave_master_complete") is not True or fixture_audit.get("phase_application") != "finalized_floquet_mpc_once":
            errors.append("fixture MPC/phase audit mismatch")
        hx_audit = fixture_audit.get("hx_audit", {})
        if not isinstance(hx_audit, dict):
            errors.append("fixture hx audit missing")
            hx_audit = {}
        if any(fixture_audit.get(key) is not False for key in ("high_order_global_aij", "global_transfer_matrix", "global_numeric_allgather")):
            errors.append("fixture forbidden boundary is not false")
        if any(hx_audit.get(key) is not False for key in ("high_order_aij", "global_transfer_matrix")):
            errors.append("HX forbidden boundary is not false")
        production = record.get("production", {})
        derived_production = {
            "high_order_global_aij": bool(fixture_audit.get("high_order_global_aij") or hx_audit.get("high_order_aij")),
            "global_dense_transfer": bool(fixture_audit.get("global_transfer_matrix") or hx_audit.get("global_transfer_matrix")),
            "numeric_allgather": bool(fixture_audit.get("global_numeric_allgather")),
        }
        if any(production.get(key) is not False for key in derived_production):
            errors.append("production forbidden boundary is not false")
        if any(production.get(key) != value for key, value in derived_production.items()):
            errors.append("production forbidden boundary is not bound to fixture/HX audit")
        for name, value in metrics.items():
            if not np.isfinite(value):
                gates.append(f"{name} is non-finite")
        for name in ("source_unchanged_relative", "high_action_repeat_relative", "A_input_unchanged_relative"):
            if metrics[name] > WORK_LIMIT:
                gates.append(f"{name} > {WORK_LIMIT:g}")
        for name in ("q_combined_relative", "A_linearity_relative", "B_q1_stored_relative", "B_q2_stored_relative", "B_q_combined_stored_relative", "work_q1_relative", "work_q2_relative", "A_hermitian_probe_relative", "B_hermitian_probe_relative"):
            limit = LINEARITY_LIMIT if name == "A_linearity_relative" else WORK_LIMIT
            if metrics[name] > limit:
                gates.append(f"{name} exceeds fixed algebra limit")
        if metrics["A_repeat_relative"] > REPEAT_LIMIT:
            gates.append("A repeat exceeds fixed repeat limit")
        spectral = record.get("spectral", {})
        values = {}
        eigen_gate_ok = not errors and not gates
        for name in ("smallest", "largest"):
            item = spectral.get(name, {})
            q = loaded[f"eigen_{name}_q"]
            aq = loaded[f"eigen_{name}_Aq"]
            stored_bq = loaded[f"eigen_{name}_Bq"]
            recomputed_bq = _csr_matvec(matrix, q)
            if _relative(stored_bq, recomputed_bq) > WORK_LIMIT:
                errors.append(f"eigen_{name} B action does not match CSR")
            eigenvalue = float(item.get("eigenvalue", np.nan))
            residual = float(
                np.linalg.norm(aq - eigenvalue * recomputed_bq)
                / max(
                    np.linalg.norm(aq),
                    abs(eigenvalue) * np.linalg.norm(recomputed_bq),
                    np.finfo(float).tiny,
                )
            )
            q_norm = float(np.linalg.norm(q))
            quadratic = np.vdot(q, recomputed_bq)
            quadratic_imag_defect = float(
                abs(complex(quadratic).imag)
                / max(abs(complex(quadratic).real), np.finfo(float).tiny)
            )
            values[name] = {
                "eigenvalue": eigenvalue,
                "residual_relative": residual,
                "q_norm": q_norm,
                "quadratic_real": float(complex(quadratic).real),
                "quadratic_imag_defect": quadratic_imag_defect,
            }
            stored_residual = float(item.get("residual_relative", np.nan))
            imaginary_part = float(item.get("imaginary_part", np.nan))
            if not np.isfinite(stored_residual) or abs(stored_residual - residual) > 1.0e-14:
                errors.append(f"eigen_{name} stored residual does not match raw recomputation")
            if not np.isfinite(eigenvalue) or not np.isfinite(residual):
                gates.append(f"eigen_{name} is non-finite")
                eigen_gate_ok = False
            if not np.isfinite(imaginary_part) or abs(imaginary_part) > EIGEN_RESIDUAL_LIMIT:
                gates.append(f"eigen_{name} has a non-real eigenvalue")
                eigen_gate_ok = False
            if residual > EIGEN_RESIDUAL_LIMIT:
                gates.append(f"eigen_{name} residual exceeds {EIGEN_RESIDUAL_LIMIT:g}")
                eigen_gate_ok = False
            if q_norm <= 0.0 or not np.isfinite(q_norm):
                gates.append(f"eigen_{name} vector norm is not positive and finite")
                eigen_gate_ok = False
            if complex(quadratic).real <= 0.0 or not np.isfinite(complex(quadratic).real):
                gates.append(f"eigen_{name} q^H B q is not positive and finite")
                eigen_gate_ok = False
            if quadratic_imag_defect > EIGEN_RESIDUAL_LIMIT:
                gates.append(f"eigen_{name} q^H B q has an imaginary defect")
                eigen_gate_ok = False
            if int(item.get("reason", 0)) <= 0 or int(item.get("iterations", -1)) < 0:
                errors.append(f"eigen_{name} solver fact is invalid")
        smallest = values.get("smallest", {}).get("eigenvalue", np.nan)
        largest = values.get("largest", {}).get("eigenvalue", np.nan)
        condition = float(largest / smallest) if np.isfinite(smallest) and smallest != 0 else np.nan
        if not np.isfinite(smallest) or smallest <= 0:
            gates.append("lambda_min is not positive and finite")
            eigen_gate_ok = False
        if not np.isfinite(largest):
            gates.append("lambda_max is not finite")
            eigen_gate_ok = False
        if np.isfinite(smallest) and np.isfinite(largest) and largest < smallest:
            gates.append("lambda_max is smaller than lambda_min")
            eigen_gate_ok = False
        if not np.isfinite(condition) or condition > SPECTRAL_CONDITION_LIMIT:
            gates.append("global spectral condition exceeds the fixed limit")
            eigen_gate_ok = False
        if spectral.get("tested_dimension") != INDEPENDENT_EDGE_ROWS:
            errors.append("spectral tested_dimension is not the independent owner dimension")
            eigen_gate_ok = False
        numerical_rank = INDEPENDENT_EDGE_ROWS if eigen_gate_ok else None
        metrics.update({
            "lambda_min": float(smallest),
            "lambda_max": float(largest),
            "condition": condition,
            "tested_dimension": spectral.get("tested_dimension"),
            "numerical_rank": numerical_rank,
            "numerical_rank_status": "established" if numerical_rank is not None else "not_established",
            "eigenpairs": values,
        })
    else:
        metrics = {}
    resource_metrics = {
        key: watchdog_compact.get(key)
        for key in (
            "source_sha",
            "sample_count",
            "peak_process_tree_rss_bytes",
            "max_process_tree_swap_bytes",
            "natural_exit",
            "no_orphan",
            "stop_reason",
        )
    }
    return {
        "schema": "task038.lor-native-complex-hx.global-spectral-audit.check.v1",
        "record": str(record_path),
        "passed": not errors and not gates,
        "contract_errors": errors,
        "gate_failures": gates,
        "metrics": metrics,
        "resource_metrics": resource_metrics,
        "watchdog": watchdog_compact,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--watchdog", type=Path, required=True)
    parser.add_argument("--expected-source-sha")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    result = check_record(args.record, args.watchdog, args.expected_source_sha)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
