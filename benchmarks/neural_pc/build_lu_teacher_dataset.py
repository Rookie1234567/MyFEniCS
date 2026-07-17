from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import resource
import time
from typing import Any

import numpy as np

from benchmarks.neural_pc.data_contract import load_operator, save_operator
from src.solvers.local_slab_solver import LocalCsrOperator, ScipyCsrAction
from src.solvers.lu_teacher_local_solver import SparseLuTeacherLocalSolver


SCHEMA = "myfenics.lu_teacher_raw_local_inverse.dataset.v1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_int(path: str) -> int | None:
    try:
        return int(Path(path).read_text(encoding="utf-8").strip())
    except (FileNotFoundError, ValueError):
        return None


def _vmstat() -> dict[str, int | None]:
    values: dict[str, int] = {}
    try:
        for line in Path("/proc/vmstat").read_text(encoding="utf-8").splitlines():
            key, value = line.split()
            if key in {"pswpin", "pswpout"}:
                values[key] = int(value)
    except FileNotFoundError:
        pass
    return {"swap_in_pages": values.get("pswpin"), "swap_out_pages": values.get("pswpout")}


def _process_memory() -> dict[str, int | None]:
    values: dict[str, int] = {}
    try:
        for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
            key, raw = line.split(":", 1)
            if key in {"VmRSS", "VmHWM"}:
                values[key] = int(raw.split()[0]) * 1024
    except FileNotFoundError:
        pass
    return {
        "process_current_rss_bytes": values.get("VmRSS"),
        "process_peak_rss_bytes": values.get(
            "VmHWM", int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)
        ),
    }


def _load_raw_rhs(capture: Path) -> np.ndarray:
    files = sorted((capture / "real_krylov").glob("sample_*.npz"))
    if not files:
        raise FileNotFoundError(f"no raw local RHS samples under {capture}")
    rows = []
    for path in files:
        with np.load(path, allow_pickle=False) as payload:
            if set(payload.files) != {"rhs", "apply_index"}:
                raise ValueError(f"capture {path} is not raw-RHS-only")
            rows.append(np.asarray(payload["rhs"], dtype=np.complex128))
    return np.stack(rows)


def _record_provenance(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    metadata = payload.get("metadata", {})
    return {
        "path": str(path),
        "sha256": _sha256(path),
        "commit_sha": metadata.get("commit_sha"),
        "branch": metadata.get("branch"),
        "git_dirty": metadata.get("git_dirty"),
        "tracked_source_dirty": metadata.get("tracked_source_dirty"),
        "case": payload.get("case"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture-a", required=True)
    parser.add_argument("--capture-b", required=True)
    parser.add_argument("--capture-c", required=True)
    parser.add_argument("--capture-a-record", required=True)
    parser.add_argument("--capture-b-record", required=True)
    parser.add_argument("--capture-c-record", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--ordering", default="COLAMD")
    args = parser.parse_args()

    captures = [Path(args.capture_a), Path(args.capture_b), Path(args.capture_c)]
    capture_records = [
        Path(args.capture_a_record),
        Path(args.capture_b_record),
        Path(args.capture_c_record),
    ]
    operators = [load_operator(path) for path in captures]
    if len({operator.fingerprint for operator in operators}) != 1:
        raise ValueError("capture A/B/C operator fingerprints differ")
    original = operators[0]
    sanitized_metadata = {
        key: value
        for key, value in original.metadata.items()
        if key not in {"local_solver_type", "factor_only_storage"}
    }
    sanitized_metadata.update(
        {
            "input_contract": "raw_local_residual_only",
            "teacher": "sparse_lu",
            "ilu_conditioning": False,
        }
    )
    operator = LocalCsrOperator(
        original.shape,
        original.indptr,
        original.indices,
        original.values,
        sanitized_metadata,
    )
    rhs_parts = [_load_raw_rhs(path) for path in captures]
    rhs = np.concatenate(rhs_parts)
    split = np.concatenate(
        [
            np.full(len(rhs_parts[0]), "train", dtype="U16"),
            np.full(len(rhs_parts[1]), "validation", dtype="U16"),
            np.full(len(rhs_parts[2]), "holdout", dtype="U16"),
        ]
    )
    capture_id = np.concatenate(
        [
            np.full(len(rhs_parts[0]), "A", dtype="U1"),
            np.full(len(rhs_parts[1]), "B", dtype="U1"),
            np.full(len(rhs_parts[2]), "C", dtype="U1"),
        ]
    )

    resource_before: dict[str, Any] = {
        **_process_memory(),
        "cgroup_current_bytes": _read_int("/sys/fs/cgroup/memory.current"),
        "cgroup_peak_bytes": _read_int("/sys/fs/cgroup/memory.peak"),
        **_vmstat(),
    }
    teacher = SparseLuTeacherLocalSolver(operator, ordering=args.ordering)
    resource_after_factor: dict[str, Any] = {
        **_process_memory(),
        "cgroup_current_bytes": _read_int("/sys/fs/cgroup/memory.current"),
        "cgroup_peak_bytes": _read_int("/sys/fs/cgroup/memory.peak"),
        **_vmstat(),
    }
    target, solve_elapsed = teacher.solve_many(rhs)
    action = ScipyCsrAction(operator)
    residual = rhs - action.action_many(target)
    rho = np.linalg.norm(residual, axis=1) / np.maximum(
        np.linalg.norm(rhs, axis=1), np.finfo(float).tiny
    )
    if not np.all(np.isfinite(target)):
        raise RuntimeError("teacher target contains NaN or Inf")
    if np.median(rho) > 1e-11 or np.quantile(rho, 0.95) > 1e-10 or np.max(rho) > 1e-9:
        raise RuntimeError("sparse-LU teacher residual Gate failed")

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    save_operator(output, operator)
    samples_path = output / "samples.npz"
    np.savez_compressed(
        samples_path,
        rhs=rhs,
        target=target,
        split=split,
        capture_id=capture_id,
    )
    teacher_diagnostics = dict(teacher.diagnostics)
    teacher.destroy()
    resource_after_destroy: dict[str, Any] = {
        **_process_memory(),
        "cgroup_current_bytes": _read_int("/sys/fs/cgroup/memory.current"),
        "cgroup_peak_bytes": _read_int("/sys/fs/cgroup/memory.peak"),
        **_vmstat(),
    }
    manifest = {
        "schema": SCHEMA,
        "operator_fingerprint": operator.fingerprint,
        "input_contract": "raw_local_residual_only",
        "label_contract": "sparse_lu_exact_local_solution",
        "ilu_output_present": False,
        "ilu_residual_present": False,
        "current_pc_output_present": False,
        "capture_roles": {"A": "train", "B": "validation", "C": "holdout"},
        "capture_source_records": {
            name: _record_provenance(path)
            for name, path in zip(("A", "B", "C"), capture_records, strict=True)
        },
        "split_counts": {
            name: int(np.count_nonzero(split == name))
            for name in ("train", "validation", "holdout")
        },
        "samples_sha256": _sha256(samples_path),
        "teacher": teacher_diagnostics,
        "teacher_rho": {
            "median": float(np.median(rho)),
            "p95": float(np.quantile(rho, 0.95)),
            "max": float(np.max(rho)),
        },
        "triangular_solve": {
            "mean_s": float(np.mean(solve_elapsed)),
            "p95_s": float(np.quantile(solve_elapsed, 0.95)),
            "max_s": float(np.max(solve_elapsed)),
        },
        "resource_before": resource_before,
        "resource_after_factor": resource_after_factor,
        "resource_after_destroy": resource_after_destroy,
        "factor_destroy_confirmed": bool(teacher.diagnostics["destroyed"]),
        "generated_unix_s": time.time(),
    }
    (output / "dataset.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
