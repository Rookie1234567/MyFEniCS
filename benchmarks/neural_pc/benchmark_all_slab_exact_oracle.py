from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import resource
from typing import Any

import numpy as np

from benchmarks.neural_pc.data_contract import load_operator
from src.solvers.local_slab_solver import ScipyCsrAction
from src.solvers.lu_teacher_local_solver import SparseLuTeacherLocalSolver


SCHEMA = "myfenics.all_slab_exact_factor_census.v1"


def _process_rss_bytes() -> int:
    try:
        for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) * 1024
    except FileNotFoundError:
        pass
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)


def _mem_available_bytes() -> int | None:
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) * 1024
    except FileNotFoundError:
        pass
    return None


def _swap_pages() -> dict[str, int | None]:
    values: dict[str, int] = {}
    try:
        for line in Path("/proc/vmstat").read_text(encoding="utf-8").splitlines():
            key, value = line.split()
            if key in {"pswpin", "pswpout"}:
                values[key] = int(value)
    except FileNotFoundError:
        pass
    return {"swap_in_pages": values.get("pswpin"), "swap_out_pages": values.get("pswpout")}


def _discover_operators(capture_root: Path, expected_slabs: int) -> list[Path]:
    directories = sorted(
        path.parent for path in capture_root.glob("rank_*/slab_*/operator.json")
    )
    by_slab: dict[int, Path] = {}
    for directory in directories:
        slab = int(directory.name.removeprefix("slab_"))
        if slab in by_slab:
            raise ValueError(f"duplicate captured operator for slab {slab}")
        by_slab[slab] = directory
    expected = set(range(expected_slabs))
    if set(by_slab) != expected:
        raise ValueError(
            f"captured slab IDs {sorted(by_slab)} do not match {sorted(expected)}"
        )
    return [by_slab[slab] for slab in range(expected_slabs)]


def _baseline_factor_storage(record_path: Path | None) -> dict[int, int]:
    if record_path is None:
        return {}
    payload = json.loads(record_path.read_text(encoding="utf-8"))
    rows = payload.get("slab_diagnostics", {}).get("global_backend_diagnostics", [])
    return {
        int(row["subdomain"]): int(row.get("ilu_factor_storage_estimate", 0))
        for row in rows
    }


def _prediction(
    rows: list[dict[str, Any]],
    *,
    available_memory_bytes: int | None,
    baseline_peak_total_bytes: int | None,
) -> dict[str, Any]:
    per_rank: dict[int, dict[str, int]] = {}
    for row in rows:
        owner = int(row["owner_rank"])
        packet = per_rank.setdefault(
            owner, {"exact_factor_bytes": 0, "removed_ilu_bytes": 0}
        )
        packet["exact_factor_bytes"] += int(row["factor_storage_bytes"])
        packet["removed_ilu_bytes"] += int(row["removed_ilu_storage_bytes"])
    for packet in per_rank.values():
        packet["net_factor_change_bytes"] = (
            packet["exact_factor_bytes"] - packet["removed_ilu_bytes"]
        )
    maximum_exact = max(
        (packet["exact_factor_bytes"] for packet in per_rank.values()), default=0
    )
    conservative_peak = (
        None
        if baseline_peak_total_bytes is None
        else int(baseline_peak_total_bytes + maximum_exact)
    )
    warning = (
        None if available_memory_bytes is None else int(0.40 * available_memory_bytes)
    )
    stop = (
        None if available_memory_bytes is None else int(0.50 * available_memory_bytes)
    )
    return {
        "per_rank": {str(key): value for key, value in sorted(per_rank.items())},
        "predicted_exact_factor_bytes_global": sum(
            int(row["factor_storage_bytes"]) for row in rows
        ),
        "predicted_maximum_exact_factor_bytes_per_rank": maximum_exact,
        "baseline_simultaneous_total_rss_upper_bytes": baseline_peak_total_bytes,
        "predicted_peak_worker_rss_conservative_upper_bytes": conservative_peak,
        "available_memory_bytes": available_memory_bytes,
        "warning_threshold_bytes": warning,
        "stop_threshold_bytes": stop,
        "safety_gate_passed": (
            conservative_peak is not None
            and stop is not None
            and conservative_peak < stop
        ),
        "prediction_semantics": (
            "The baseline simultaneous all-worker RSS is deliberately used as an "
            "upper bound for one worker, then the maximum owner exact-factor bytes "
            "are added. This is conservative rather than a measured worker peak."
        ),
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    capture_root = Path(args.capture_root)
    operator_paths = _discover_operators(capture_root, args.expected_slabs)
    baseline_storage = _baseline_factor_storage(
        None if args.baseline_record is None else Path(args.baseline_record)
    )
    baseline_peak_total_bytes = None
    if args.baseline_record is not None:
        baseline = json.loads(Path(args.baseline_record).read_text(encoding="utf-8"))
        peak_gib = baseline.get("peak_total_rss_including_rta_gb")
        if peak_gib is None:
            peak_gib = baseline.get("final_peak_total_gb")
        if peak_gib is not None:
            baseline_peak_total_bytes = int(float(peak_gib) * 1024**3)

    rows: list[dict[str, Any]] = []
    swap_before = _swap_pages()
    for slab, path in enumerate(operator_paths):
        operator = load_operator(path)
        owner_rank = int(operator.metadata.get("owner_rank", -1))
        rss_before = _process_rss_bytes()
        teacher = SparseLuTeacherLocalSolver(operator, ordering=args.ordering)
        rss_after_factor = _process_rss_bytes()
        rng = np.random.default_rng(args.seed + slab)
        rhs = rng.standard_normal(operator.shape[0]) + 1j * rng.standard_normal(
            operator.shape[0]
        )
        solution = np.empty(operator.shape[0], dtype=np.complex128)
        teacher.solve(rhs, solution)
        residual = rhs - ScipyCsrAction(operator).action(solution)
        rho = float(np.linalg.norm(residual) / np.linalg.norm(rhs))
        diagnostics = dict(teacher.diagnostics)
        teacher.destroy()
        destroyed = bool(teacher.diagnostics["destroyed"])
        try:
            teacher.solve(rhs, solution)
        except RuntimeError:
            destroy_rejects_apply = True
        else:
            destroy_rejects_apply = False
        rows.append(
            {
                "slab_id": slab,
                "owner_rank": owner_rank,
                "shape": list(operator.shape),
                "matrix_nnz": diagnostics["matrix_nnz"],
                "operator_fingerprint": operator.fingerprint,
                "factorization_s": diagnostics["factorization_s"],
                "l_nnz": diagnostics["l_nnz"],
                "u_nnz": diagnostics["u_nnz"],
                "factor_nnz": diagnostics["factor_nnz"],
                "fill_ratio": diagnostics["fill_ratio"],
                "factor_storage_bytes": diagnostics["factor_storage_bytes"],
                "removed_ilu_storage_bytes": baseline_storage.get(slab, 0),
                "rss_before_factor_bytes": rss_before,
                "rss_after_factor_bytes": rss_after_factor,
                "rss_factor_delta_bytes": max(rss_after_factor - rss_before, 0),
                "test_rhs_relative_residual": rho,
                "destroyed": destroyed,
                "destroy_rejects_apply": destroy_rejects_apply,
            }
        )
        if rho > args.residual_limit:
            raise RuntimeError(f"slab {slab} exact residual Gate failed: {rho}")
        if not destroyed or not destroy_rejects_apply:
            raise RuntimeError(f"slab {slab} factor destroy Gate failed")
    swap_after = _swap_pages()
    prediction = _prediction(
        rows,
        available_memory_bytes=_mem_available_bytes(),
        baseline_peak_total_bytes=baseline_peak_total_bytes,
    )
    swap_delta = {
        key.replace("_pages", "_delta_pages"): (
            None
            if swap_before[key] is None or swap_after[key] is None
            else int(swap_after[key] - swap_before[key])
        )
        for key in ("swap_in_pages", "swap_out_pages")
    }
    payload = {
        "schema": SCHEMA,
        "capture_root": str(capture_root),
        "expected_slabs": args.expected_slabs,
        "ordering": args.ordering,
        "residual_limit": args.residual_limit,
        "rows": rows,
        "prediction": prediction,
        "swap": {**swap_before, **swap_after, **swap_delta},
        "all_factors_finite": all(
            np.isfinite(row["factorization_s"]) and row["factor_nnz"] > 0
            for row in rows
        ),
        "all_residuals_pass": all(
            row["test_rhs_relative_residual"] <= args.residual_limit for row in rows
        ),
        "all_destroyed": all(
            row["destroyed"] and row["destroy_rejects_apply"] for row in rows
        ),
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    csv_path = output.with_suffix(".csv")
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps(payload, indent=2))
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sequential 16-slab sparse-LU census and memory predictor."
    )
    parser.add_argument("--capture-root", required=True)
    parser.add_argument("--baseline-record")
    parser.add_argument("--output", required=True)
    parser.add_argument("--expected-slabs", type=int, default=16)
    parser.add_argument("--ordering", default="COLAMD")
    parser.add_argument("--seed", type=int, default=20260717)
    parser.add_argument("--residual-limit", type=float, default=1.0e-11)
    args = parser.parse_args()
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
