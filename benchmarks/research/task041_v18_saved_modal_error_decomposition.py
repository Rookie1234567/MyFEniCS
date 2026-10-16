"""One-off, hash-bound V18 archive decomposition; no solver or MPI entrypoints.

The default command performs only small algebra fixtures.  Archive processing
requires the explicit --analyze flag and a new, nonexistent output path.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import resource
import sys
import time
import zipfile
from collections.abc import Iterable, Sequence
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any

import numpy as np

SCHEMA = "task041.v18.saved_modal_error_decomposition.v1"
RUNTIME_SOURCE_SHA = "c662a70b4af4d742f7a8305d0efd63342423c775"
INVOCATION_ID = "6344a904b8df435a88a7466dd739da76"
RUN_RELATIVE = Path(
    "results/task041_w0p7nm_balh_hybrid_iterative_p6h0p70_m400_mpi8_cell_condensed_pilot/"
    "task041_w0p7_p6_h0p70_m400_mpi8_cell_condensed_pilot__hybrid_iterative__mpi8__M400/"
    "20261015T143400.129213Z"
)
EVIDENCE_RELATIVE = Path(
    "consumer/numerical_output/v13_modal_row_evidence"
)
EXPECTED_SHA256 = {
    "run_manifest.json": "cad2cfdd14e37c0799a03d5d9172b7f581161d575dd7045566af14951afa12ca",
    "supervisor_summary.json": "237e4a6d983d8a2b113d30ec6a39dc453b7a80769594f0d21aab380a826b63e2",
    "index.json": "775c453b8c60699fd3f64ef4e4a3c1a1934c8616784d0777652adc3d9aaedfd9",
    "v15_s_b_ready.npz": "4a5f2e6d264b28e0d9b44af4306d6efafa897b5d154cb9f9fac6d02d7161def5",
    "v15_terminal_numeric_reject.npz": "e84fffe96bf19418714099d8f2496069c73c282ff452ec58c0854860deb40c54",
    "v15_terminal_rank_vectors_index.npz": "8739c76e681f900923b900c9df0ef75cf421d39cabb54650c4b9ad19b6a76d85",
    "selected_mode_manifest.json": "3755293a6055ee290300967f889126a3d04e3c140a973cdec521a09a4b55d5d6",
    "launch_manifest.json": "4d36167b092a8c47c9dfecc8a55e865a291eab070135016142f88f699c6d3283",
    "selected_mode_packet_manifest.json": "63b7635e99dd476a94c97a07aa469be8c5087ef55fadeb7e8f908b1ded0d84e2",
}
C_SHA256 = "b720ee6eab372f56e389241973e2573e0913f804fb90726f29c4543cc1fc1286"
S_B_SHA256 = "d4b25b721327c5b0f8261a15f96a61022507a5ae84ebe66c087cafd4832d3bfc"
LAYOUT_SHA256 = "db70fd5ee69f64337780912877872fc61ce3809f87e66fe3ccd4de8d9a39c5f8"
PACKET_MANIFEST_SHA256 = "63b7635e99dd476a94c97a07aa469be8c5087ef55fadeb7e8f908b1ded0d84e2"
TOLERANCE = Decimal("1e-10")
HP_PRECISION = 90
HP_CROSSCHECK_PRECISION = 120
HP_CROSSCHECK_LIMIT = Decimal("1e-30")
PROCESS_RSS_BUDGET_BYTES = 2 * 1024**3
HOST_PREFLIGHT_MARGIN_BYTES = 256 * 1024**2
DECIMAL_WORKSPACE_RESERVE_BYTES = 128 * 1024**2
THREAD_VARIABLES = (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "BLIS_NUM_THREADS",
)


class AnalysisError(RuntimeError):
    """A closed, actionable archive or fixture contract failure."""


DComplex = tuple[Decimal, Decimal]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AnalysisError(message)


def json_file(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"expected JSON object: {path}")
    return value


def _scalar_values_for_key(value: Any, key_names: set[str]) -> list[Any]:
    found: list[Any] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key in key_names and not isinstance(child, (dict, list)):
                found.append(child)
            found.extend(_scalar_values_for_key(child, key_names))
    elif isinstance(value, list):
        for child in value:
            found.extend(_scalar_values_for_key(child, key_names))
    return found


def _safe_repo_file(repo_root: Path, recorded_path: str) -> Path:
    candidate = Path(recorded_path)
    if not candidate.is_absolute():
        candidate = repo_root / candidate
    candidate = candidate.resolve()
    try:
        candidate.relative_to(repo_root.resolve())
    except ValueError as exc:
        raise AnalysisError(f"manifest path escapes repository: {recorded_path}") from exc
    require(candidate.is_file(), f"manifest-bound file is missing: {candidate}")
    return candidate


def _safe_evidence_file(evidence_dir: Path, recorded_path: str) -> Path:
    """Resolve a workflow-relative evidence path without guessing its root."""
    candidate = Path(recorded_path)
    if candidate.is_absolute():
        resolved = candidate.resolve()
        try:
            resolved.relative_to(evidence_dir.resolve())
        except ValueError as exc:
            raise AnalysisError(f"evidence path escapes evidence directory: {recorded_path}") from exc
    else:
        parts = candidate.parts
        prefix = ("numerical_output", "v13_modal_row_evidence")
        require(parts[:2] == prefix, f"unexpected workflow evidence path: {recorded_path}")
        require(".." not in parts, f"evidence path contains parent traversal: {recorded_path}")
        resolved = (evidence_dir / Path(*parts[2:])).resolve()
        try:
            resolved.relative_to(evidence_dir.resolve())
        except ValueError as exc:
            raise AnalysisError(f"evidence path escapes evidence directory: {recorded_path}") from exc
    require(resolved.is_file(), f"evidence file is missing: {resolved}")
    return resolved


def _verify_bound_file(
    repo_root: Path,
    binding: dict[str, Any],
    label: str,
) -> Path:
    path_value = binding.get("path")
    sha_value = binding.get("sha256")
    require(isinstance(path_value, str), f"{label}: missing path")
    require(isinstance(sha_value, str) and len(sha_value) == 64, f"{label}: bad SHA")
    path = _safe_repo_file(repo_root, path_value)
    actual = sha256_file(path)
    require(actual == sha_value, f"{label}: file SHA does not match run manifest")
    return path


def _archive_npz_members_size(path: Path) -> int:
    with zipfile.ZipFile(path) as archive:
        return sum(member.file_size for member in archive.infolist())


def _proc_status_bytes(field: str) -> int | None:
    status = Path("/proc/self/status")
    if not status.is_file():
        return None
    for line in status.read_text(encoding="ascii").splitlines():
        if line.startswith(field + ":"):
            pieces = line.split()
            if len(pieces) >= 3 and pieces[2] == "kB":
                return int(pieces[1]) * 1024
    return None


def _self_thread_count() -> int | None:
    task_dir = Path("/proc/self/task")
    if not task_dir.is_dir():
        return None
    return len(list(task_dir.iterdir()))


def _enforce_single_process_thread() -> None:
    count = _self_thread_count()
    require(count == 1, f"analysis requires one OS thread in its single process; observed {count}")


def _cgroup_v2_headroom() -> tuple[int | None, list[dict[str, int | str]]]:
    cgroup_file = Path("/proc/self/cgroup")
    mount = Path("/sys/fs/cgroup")
    if not cgroup_file.is_file() or not mount.is_dir():
        return None, []
    relative: str | None = None
    for line in cgroup_file.read_text(encoding="ascii").splitlines():
        if line.startswith("0::"):
            relative = line[3:].lstrip("/")
            break
    if relative is None:
        return None, []
    start = (mount / relative).resolve()
    try:
        start.relative_to(mount.resolve())
    except ValueError as exc:
        raise AnalysisError("cgroup path escapes cgroup v2 mount") from exc
    rows: list[dict[str, int | str]] = []
    finite_headrooms: list[int] = []
    current = start
    while True:
        max_path = current / "memory.max"
        current_path = current / "memory.current"
        if max_path.is_file() and current_path.is_file():
            max_text = max_path.read_text(encoding="ascii").strip()
            current_value = int(current_path.read_text(encoding="ascii").strip())
            if max_text == "max":
                rows.append({"path": str(current), "current_bytes": current_value, "limit": "max"})
            else:
                limit_value = int(max_text)
                headroom = limit_value - current_value
                rows.append(
                    {
                        "path": str(current),
                        "current_bytes": current_value,
                        "limit_bytes": limit_value,
                        "headroom_bytes": headroom,
                    }
                )
                finite_headrooms.append(headroom)
        if current == mount.resolve():
            break
        parent = current.parent
        if parent == current or mount.resolve() not in (parent, *parent.parents):
            break
        current = parent
    return (min(finite_headrooms) if finite_headrooms else None), rows


def _resource_preflight(repo_root: Path, index: dict[str, Any], run_root: Path) -> dict[str, Any]:
    _enforce_single_process_thread()
    available = None
    meminfo = Path("/proc/meminfo")
    if meminfo.is_file():
        for line in meminfo.read_text(encoding="ascii").splitlines():
            if line.startswith("MemAvailable:"):
                available = int(line.split()[1]) * 1024
                break
    require(available is not None, "kernel MemAvailable is unavailable")
    require(
        available >= PROCESS_RSS_BUDGET_BYTES + HOST_PREFLIGHT_MARGIN_BYTES,
        "host MemAvailable is below the analysis RSS budget plus margin",
    )
    cgroup_headroom, cgroups = _cgroup_v2_headroom()
    require(cgroups, "cgroup v2 memory authority is unavailable")
    require(
        cgroup_headroom is None or cgroup_headroom >= PROCESS_RSS_BUDGET_BYTES,
        "finite cgroup headroom is below the analysis RSS budget",
    )
    rss_now = _proc_status_bytes("VmRSS")
    require(rss_now is not None, "current process RSS cannot be measured")
    evidence_dir = run_root / EVIDENCE_RELATIVE
    compressed_inputs = sum(
        _archive_npz_members_size(evidence_dir / filename)
        for filename in (
            "v15_s_b_ready.npz",
            "v15_terminal_numeric_reject.npz",
            "v15_terminal_rank_vectors_index.npz",
        )
    )
    rank_bytes = sum(
        int(vector["nbytes"])
        for receipt in index["records"]["v15_terminal_rank_vectors_index"]["rank_receipts"]
        for vector in receipt["vectors"].values()
    )
    conservative_loaded_bytes = compressed_inputs + rank_bytes
    estimated_peak = (
        rss_now
        + conservative_loaded_bytes
        + HOST_PREFLIGHT_MARGIN_BYTES
        + DECIMAL_WORKSPACE_RESERVE_BYTES
    )
    require(
        estimated_peak <= PROCESS_RSS_BUDGET_BYTES,
        "conservative loaded-array estimate exceeds the 2 GiB process budget",
    )
    return {
        "host_memavailable_bytes": available,
        "current_process_rss_bytes": rss_now,
        "estimated_archive_uncompressed_bytes": compressed_inputs,
        "rank_vector_total_nbytes": rank_bytes,
        "conservative_process_peak_estimate_bytes": estimated_peak,
        "process_rss_budget_bytes": PROCESS_RSS_BUDGET_BYTES,
        "process_thread_count": _self_thread_count(),
        "host_margin_bytes": HOST_PREFLIGHT_MARGIN_BYTES,
        "decimal_workspace_reserve_bytes": DECIMAL_WORKSPACE_RESERVE_BYTES,
        "peak_rss_enforcement": "VmHWM checked after every analyzed row; no RLIMIT_AS is applied",
        "peak_rss_budget_is_kernel_hard_limit": False,
        "finite_cgroup_min_headroom_bytes": cgroup_headroom,
        "cgroup_observations": cgroups,
        "production_v16_resource_policy_applied": False,
    }


def _array_sha256(array: np.ndarray) -> str:
    contiguous = np.ascontiguousarray(array)
    return hashlib.sha256(contiguous.view(np.uint8)).hexdigest()


def _load_npz_checked(path: Path, expected_sha: str, expected_record: dict[str, Any]) -> dict[str, np.ndarray]:
    require(sha256_file(path) == expected_sha, f"archive SHA mismatch: {path.name}")
    with np.load(path, allow_pickle=False) as archive:
        arrays = {name: archive[name] for name in archive.files}
    shapes = expected_record.get("array_shapes", {})
    dtypes = expected_record.get("array_dtypes", {})
    require(set(arrays) == set(shapes), f"{path.name}: array keys differ from index")
    for name, array in arrays.items():
        require(list(array.shape) == shapes[name], f"{path.name}:{name} shape mismatch")
        if name in dtypes:
            require(str(array.dtype) == dtypes[name], f"{path.name}:{name} dtype mismatch")
    return arrays


def _is_complex_finite(array: np.ndarray) -> bool:
    return array.dtype.kind == "c" and bool(np.isfinite(array).all())


def _validate_log_arrays(arrays: dict[str, np.ndarray]) -> None:
    for log_name, linear_name, exact_name in (
        ("row_relative_log_error", "row_relative_error", "d"),
        (
            "decomposition_row_relative_log_error",
            "decomposition_row_relative_error",
            "decomposition_error",
        ),
    ):
        logs = arrays[log_name]
        linear = arrays[linear_name]
        exact = arrays[exact_name]
        require(logs.shape == linear.shape == exact.shape, f"{log_name}: paired shape mismatch")
        require(not np.isnan(logs).any() and not np.isposinf(logs).any(), f"{log_name}: NaN/+inf")
        negative_infinity = np.isneginf(logs)
        exact_zero = (exact.real == 0.0) & (exact.imag == 0.0)
        require(
            bool(np.all(~negative_infinity | ((linear == 0.0) & exact_zero))),
            f"{log_name}: -inf is not paired with exact-zero linear and complex values",
        )
        require(
            bool(np.all(~exact_zero | (np.isneginf(logs) & (linear == 0.0)))),
            f"{log_name}: exact-zero difference lacks its defined -inf/zero encoding",
        )
        require(np.isfinite(linear).all(), f"{linear_name}: nonfinite linear metric")
    for name, array in arrays.items():
        if name in ("row_relative_log_error", "decomposition_row_relative_log_error"):
            continue
        require(np.isfinite(array).all(), f"{name}: physical/linear array is nonfinite")


def _validate_layout(
    layout: dict[str, Any],
    source_vectors: Sequence[np.ndarray],
    target_vectors: Sequence[np.ndarray],
    *,
    expected_mpi_size: int | None = None,
    expected_modal_count: int | None = None,
) -> dict[str, Any]:
    required = {
        "global_size",
        "local_size_by_rank",
        "modal_global_indices",
        "combined_offsets",
        "modal_owner",
        "modal_count",
        "local_modal_range_by_rank",
    }
    require(required.issubset(layout), "layout is missing required rank-major fields")
    sizes = [int(value) for value in layout["local_size_by_rank"]]
    offsets = [int(value) for value in layout["combined_offsets"]]
    ranges = [[int(v) for v in pair] for pair in layout["local_modal_range_by_rank"]]
    mpi_size = len(sizes)
    require(mpi_size > 0, "rank-major layout has no ranks")
    if expected_mpi_size is not None:
        require(mpi_size == expected_mpi_size, f"expected {expected_mpi_size} ranks, got {mpi_size}")
    require(len(offsets) == len(ranges) == len(source_vectors) == len(target_vectors) == mpi_size, "rank layout length mismatch")
    expected_offset = 0
    for rank, (size, offset, local_range, source, target) in enumerate(
        zip(sizes, offsets, ranges, source_vectors, target_vectors, strict=True)
    ):
        require(offset == expected_offset, f"rank {rank}: noncontiguous combined offset")
        expected_offset += size
        require(source.shape == target.shape == (size,), f"rank {rank}: vector shape/layout mismatch")
        require(source.dtype == target.dtype == np.dtype("complex128"), f"rank {rank}: vector dtype mismatch")
        require(len(local_range) == 2 and 0 <= local_range[0] <= local_range[1] <= size, f"rank {rank}: invalid local modal range")
    require(expected_offset == int(layout["global_size"]), "combined offsets do not sum to global size")
    owner = int(layout["modal_owner"])
    modal_count = int(layout["modal_count"])
    require(0 <= owner < mpi_size and modal_count > 0, "modal owner/count mismatch")
    if expected_modal_count is not None:
        require(modal_count == expected_modal_count, f"expected {expected_modal_count} modal rows, got {modal_count}")
    owner_range = ranges[owner]
    require(owner_range[1] - owner_range[0] == modal_count, "owner local modal range length mismatch")
    for rank, local_range in enumerate(ranges):
        if rank != owner:
            require(local_range[0] == local_range[1], f"nonowner rank {rank} unexpectedly owns modal rows")
    global_indices = [int(value) for value in layout["modal_global_indices"]]
    require(len(global_indices) == modal_count and len(set(global_indices)) == modal_count, "modal global index length/uniqueness failure")
    expected_global = list(range(offsets[owner] + owner_range[0], offsets[owner] + owner_range[1]))
    require(global_indices == expected_global, "modal indices do not match owner range in rank-major layout")
    return {
        "mpi_size": mpi_size,
        "global_size": int(layout["global_size"]),
        "modal_count": modal_count,
        "modal_owner": owner,
        "combined_offsets": offsets,
        "local_size_by_rank": sizes,
        "owner_modal_local_range": owner_range,
        "modal_global_indices_sha256": hashlib.sha256(
            np.asarray(global_indices, dtype=np.int64).tobytes()
        ).hexdigest(),
        "layout_sha256": canonical_sha256(layout),
    }


def _same_complex_bytes(left: np.ndarray, right: np.ndarray) -> bool:
    return (
        left.dtype == right.dtype
        and left.shape == right.shape
        and np.ascontiguousarray(left).tobytes() == np.ascontiguousarray(right).tobytes()
    )


def _verify_modal_vector_bindings(
    layout: dict[str, Any],
    source_vectors: Sequence[np.ndarray],
    target_vectors: Sequence[np.ndarray],
    r_modal: np.ndarray,
    a_modal: np.ndarray,
    *,
    expected_mpi_size: int | None = None,
    expected_modal_count: int | None = None,
) -> dict[str, Any]:
    checked = _validate_layout(
        layout,
        source_vectors,
        target_vectors,
        expected_mpi_size=expected_mpi_size,
        expected_modal_count=expected_modal_count,
    )
    owner = checked["modal_owner"]
    start, end = checked["owner_modal_local_range"]
    source_modal = np.ascontiguousarray(source_vectors[owner][start:end])
    target_modal = np.ascontiguousarray(target_vectors[owner][start:end])
    require(_same_complex_bytes(source_modal, r_modal), "rank-owned source modal slice is not byte-identical to r_modal")
    require(_same_complex_bytes(target_modal, a_modal), "rank-owned target modal slice is not byte-identical to a")
    checked.update(
        {
            "source_modal_matches_r_modal_bytewise": True,
            "target_modal_matches_a_bytewise": True,
            "source_modal_sha256": hashlib.sha256(source_modal.view(np.uint8)).hexdigest(),
            "target_modal_sha256": hashlib.sha256(target_modal.view(np.uint8)).hexdigest(),
        }
    )
    return checked


def verify_inputs(repo_root: Path) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    run_root = repo_root / RUN_RELATIVE
    evidence_dir = run_root / EVIDENCE_RELATIVE
    require(run_root.is_dir() and evidence_dir.is_dir(), "bound M400 run/evidence directory is missing")
    for variable in THREAD_VARIABLES:
        require(os.environ.get(variable) == "1", f"{variable} must be explicitly set to 1")

    for filename, expected in (
        ("run_manifest.json", EXPECTED_SHA256["run_manifest.json"]),
        ("supervisor_summary.json", EXPECTED_SHA256["supervisor_summary.json"]),
        ("consumer/numerical_output/v13_modal_row_evidence/index.json", EXPECTED_SHA256["index.json"]),
    ):
        path = run_root / filename
        require(sha256_file(path) == expected, f"hash-bound input changed: {filename}")

    run_manifest = json_file(run_root / "run_manifest.json")
    supervisor_summary = json_file(run_root / "supervisor_summary.json")
    index = json_file(evidence_dir / "index.json")
    supervision = run_manifest.get("supervision_record", {})
    require(supervision.get("invocation_id") == INVOCATION_ID, "run manifest Invocation mismatch")
    require(supervision.get("source_sha") == RUNTIME_SOURCE_SHA, "run manifest runtime source mismatch")
    require(run_manifest.get("source_sha") == RUNTIME_SOURCE_SHA, "run manifest top-level source mismatch")
    require(supervisor_summary.get("supervision_record", {}).get("invocation_id") == INVOCATION_ID, "supervisor summary Invocation mismatch")
    require(supervisor_summary.get("supervision_record", {}).get("source_sha") == RUNTIME_SOURCE_SHA, "supervisor summary source mismatch")
    require(index.get("schema") == "task041.v13.modal_row_evidence_index.v1", "evidence index schema mismatch")
    require(index.get("source_sha") == RUNTIME_SOURCE_SHA, "evidence index source mismatch")
    identity = index.get("identity", {})
    require(identity.get("source_sha") == RUNTIME_SOURCE_SHA, "evidence identity source mismatch")
    require(identity.get("mpi_size") == 8 and identity.get("mode_count") == 400, "evidence identity is not this MPI8/M400 run")
    require(identity.get("run_id") == run_manifest.get("run_id"), "index/run manifest run_id mismatch")
    require(index.get("packet_manifest_sha256") == PACKET_MANIFEST_SHA256, "index packet manifest identity mismatch")
    require(index.get("packet_manifest_sha256") == run_manifest.get("packet_source_binding", {}).get("files", {}).get("selected_mode_packet_manifest", {}).get("sha256"), "run/index producer packet manifest mismatch")
    binding = index.get("consumer_binding", {})
    require(binding.get("pass") is True, "archived consumer binding is not passed")
    require(binding.get("consumer_identity", {}).get("source_sha") == RUNTIME_SOURCE_SHA, "consumer binding source mismatch")

    launch_binding = supervision
    launch_path_recorded = launch_binding.get("path")
    require(isinstance(launch_path_recorded, str), "run manifest has no launch manifest path")
    launch_manifest_path = _safe_repo_file(repo_root, launch_path_recorded)
    require(sha256_file(launch_manifest_path) == EXPECTED_SHA256["launch_manifest.json"], "launch manifest hash mismatch")
    require(launch_binding.get("sha256") == EXPECTED_SHA256["launch_manifest.json"], "run manifest launch hash mismatch")
    launch_manifest = json_file(launch_manifest_path)
    inv_values = _scalar_values_for_key(launch_manifest, {"invocation_id", "InvocationID", "invocation"})
    require(INVOCATION_ID in [str(value) for value in inv_values], "launch manifest does not bind the target Invocation")
    source_values = _scalar_values_for_key(launch_manifest, {"source_sha", "runtime_source_sha"})
    require(RUNTIME_SOURCE_SHA in [str(value) for value in source_values], "launch manifest does not bind runtime source")

    source_bindings = run_manifest.get("packet_source_binding", {}).get("files")
    require(isinstance(source_bindings, dict) and source_bindings, "run manifest producer file bindings are missing")
    for label, file_binding in source_bindings.items():
        _verify_bound_file(repo_root, file_binding, f"producer source {label}")
    packet_manifest_binding = source_bindings["selected_mode_packet_manifest"]
    packet_manifest_path = _safe_repo_file(repo_root, packet_manifest_binding["path"])
    require(sha256_file(packet_manifest_path) == PACKET_MANIFEST_SHA256, "selected mode packet manifest hash mismatch")

    records = index.get("records")
    require(isinstance(records, dict), "evidence index records missing")
    required_records = {
        "v15_s_b_ready",
        "v15_terminal_numeric_reject",
        "v15_terminal_rank_vectors_index",
    }
    require(required_records.issubset(records), "required P0 evidence slots are absent")
    ready_record = records["v15_s_b_ready"]
    terminal_record = records["v15_terminal_numeric_reject"]
    vectors_record = records["v15_terminal_rank_vectors_index"]
    require(ready_record.get("sha256") == EXPECTED_SHA256["v15_s_b_ready.npz"], "ready snapshot index SHA mismatch")
    require(terminal_record.get("sha256") == EXPECTED_SHA256["v15_terminal_numeric_reject.npz"], "terminal snapshot index SHA mismatch")
    require(vectors_record.get("sha256") == EXPECTED_SHA256["v15_terminal_rank_vectors_index.npz"], "vector index SHA mismatch")

    resource = _resource_preflight(repo_root, index, run_root)
    ready_path = _safe_evidence_file(evidence_dir, ready_record["path"])
    terminal_path = _safe_evidence_file(evidence_dir, terminal_record["path"])
    vectors_index_path = _safe_evidence_file(evidence_dir, vectors_record["path"])
    require(
        sha256_file(vectors_index_path) == EXPECTED_SHA256["v15_terminal_rank_vectors_index.npz"],
        "rank vector index NPZ file SHA mismatch",
    )
    ready_arrays = _load_npz_checked(ready_path, EXPECTED_SHA256["v15_s_b_ready.npz"], ready_record)
    terminal_arrays = _load_npz_checked(terminal_path, EXPECTED_SHA256["v15_terminal_numeric_reject.npz"], terminal_record)
    with np.load(vectors_index_path, allow_pickle=False) as archive:
        require(not archive.files, "rank vector index NPZ should contain metadata only")

    for required in (
        "C",
        "s_b",
    ):
        require(required in ready_arrays and _is_complex_finite(ready_arrays[required]), f"ready matrix {required} missing/nonfinite")
    require(ready_arrays["C"].shape == ready_arrays["s_b"].shape == (800, 800), "C/S_B matrix shape mismatch")
    require(_array_sha256(ready_arrays["C"]) == C_SHA256, "C array bytes do not match ready metadata hash")
    require(_array_sha256(ready_arrays["s_b"]) == S_B_SHA256, "S_B array bytes do not match ready metadata hash")

    terminal_required = {
        "a",
        "d",
        "decomposition_error",
        "decomposition_row_relative_error",
        "decomposition_row_relative_log_error",
        "g",
        "r_modal",
        "row_denominator_scaled",
        "row_relative_error",
        "row_relative_log_error",
        "row_scale",
        "t_bottom",
        "t_constraint",
        "t_top",
        "w_modal",
    }
    require(set(terminal_arrays) == terminal_required, "terminal array schema differs from the frozen expected keys")
    require(all(value.shape == (800,) for value in terminal_arrays.values()), "terminal array shape is not 800")
    require(all(value.dtype.kind in "fc" for value in terminal_arrays.values()), "terminal arrays have unexpected dtype")
    _validate_log_arrays(terminal_arrays)
    for name in ("a", "g", "r_modal", "d", "w_modal", "t_bottom", "t_top", "t_constraint", "decomposition_error"):
        require(terminal_arrays[name].dtype == np.dtype("complex128"), f"{name}: expected complex128")
    terminal_metadata = terminal_record.get("metadata", {})
    vector_metadata = vectors_record.get("metadata", {})
    row = terminal_metadata.get("record", {})
    capture = row.get("capture_identity", {})
    require(row.get("schema") == "task041.v15.original_modal_row.terms_backward.v1", "terminal row schema mismatch")
    require(row.get("contract_id") == row.get("schema"), "terminal row contract/schema mismatch")
    metrics = row.get("metrics")
    require(isinstance(metrics, dict), "terminal row metrics are missing")
    require(metrics.get("contract_id") == row.get("contract_id"), "terminal metrics contract mismatch")
    require(metrics.get("tolerance") == float(TOLERANCE), "terminal metrics tolerance differs from unchanged V15 gate")
    require(row.get("status") == "rejected", "terminal row status is not rejected")
    require(metrics.get("status") == "rejected" and metrics.get("valid") is True, "terminal row is not a valid, rejected modal-row record")
    row_eta_values = terminal_arrays["row_relative_error"]
    max_row = int(np.argmax(row_eta_values))
    require(float(metrics["eta_terms_inf"]) == float(np.max(row_eta_values)), "terminal metrics eta_inf differs from saved per-row eta array")
    require(metrics.get("max_row_index") == max_row, "terminal metrics max-row index differs from saved eta array")
    require(float(metrics.get("max_row_relative_error")) == float(row_eta_values[max_row]), "terminal metrics max-row eta differs from saved eta array")
    layout = capture.get("layout")
    require(isinstance(layout, dict), "terminal capture rank-major layout missing")
    require(row.get("attempt_index") == terminal_metadata.get("attempt_index") == 1, "terminal row attempt identity mismatch")
    require(vector_metadata.get("attempt_index") == 1, "rank-vector snapshot attempt identity mismatch")
    require(capture.get("attempt_index") == 1, "capture attempt identity mismatch")
    require(capture.get("layout_sha256") == LAYOUT_SHA256, "capture layout hash differs from approved layout")
    require(canonical_sha256(layout) == LAYOUT_SHA256, "capture layout contents do not match layout hash")
    require(row.get("same_attempt_owner_solve") is True, "owner solve is not bound to terminal attempt")
    require(row.get("owner_lu_solve_count_before") == 0 and row.get("owner_lu_solve_count_after") == 1, "owner solve count differs from terminal attempt")

    ready_metadata = ready_record.get("metadata", {}).get("metadata", {})
    ready_modal = ready_metadata.get("modal", {})
    ready_original = ready_metadata.get("original_A", {})
    require(ready_metadata.get("formula") == "S_B=C-LBG", "ready S_B formula mismatch")
    require(ready_modal.get("owner_rank") == layout.get("modal_owner") == 7, "S_B/terminal owner rank mismatch")
    require(ready_modal.get("internal_mode_count") == layout.get("modal_count") == 800, "S_B/terminal modal count mismatch")
    require(ready_modal.get("constraint_sha256") == C_SHA256, "C ready metadata identity mismatch")
    require(ready_modal.get("s_b_sha256") == S_B_SHA256, "S_B ready metadata identity mismatch")
    require(ready_original.get("handle") == capture.get("operator_handle"), "ready original-A Mat handle differs from terminal capture")
    owner_context = capture.get("operator_context_identity_by_rank", [None] * 8)[7]
    require(ready_original.get("context_identity") == owner_context, "ready/original-A owner context identity mismatch")
    require(ready_original.get("layout_sha256") == capture.get("layout_sha256"), "ready/original-A layout identity mismatch")

    receipts = vectors_record.get("rank_receipts")
    require(isinstance(receipts, list) and len(receipts) == 8, "expected exactly eight terminal rank receipts")
    capture_lists = (
        "pc_source_before_by_rank",
        "pc_source_after_by_rank",
        "pc_source_unchanged_by_rank",
        "pc_target_before_by_rank",
        "pc_target_after_by_rank",
        "pc_target_unchanged_by_original_A_by_rank",
        "pc_source_target_alias_by_rank",
        "operator_input_unchanged_by_rank",
        "operator_input_range_by_rank",
        "operator_input_handle_by_rank",
        "operator_input_sha256_before_by_rank",
        "operator_input_sha256_after_by_rank",
        "operator_output_range_by_rank",
        "operator_output_handle_by_rank",
        "matmult_call_id_by_rank",
        "operator_context_identity_by_rank",
        "pc_source_handle_by_rank",
        "pc_target_handle_by_rank",
    )
    for field in capture_lists:
        value = capture.get(field)
        require(isinstance(value, list) and len(value) == 8, f"capture {field} must bind all eight ranks")
    require(capture["output_matches_components"] is True, "capture does not bind output to archived components")
    require(capture["operator_input_output_alias"] is False, "original-A input/output alias is present")
    source_vectors: list[np.ndarray] = []
    target_vectors: list[np.ndarray] = []
    retained_rank_bytes = 0
    rank_offsets = layout["combined_offsets"]
    rank_sizes = layout["local_size_by_rank"]
    for expected_rank, receipt in enumerate(receipts):
        require(receipt.get("rank") == expected_rank and receipt.get("status") == "written", f"rank receipt {expected_rank} order/status mismatch")
        vectors = receipt.get("vectors", {})
        require(set(vectors) == {"source", "target"}, f"rank {expected_rank} source/target receipt missing")
        rank_size = int(rank_sizes[expected_rank])
        expected_range = [int(rank_offsets[expected_rank]), int(rank_offsets[expected_rank]) + rank_size]
        for kind, destination, before_key, after_key, unchanged_key in (
            ("source", source_vectors, "pc_source_before_by_rank", "pc_source_after_by_rank", "pc_source_unchanged_by_rank"),
            ("target", target_vectors, "pc_target_before_by_rank", "pc_target_after_by_rank", "pc_target_unchanged_by_original_A_by_rank"),
        ):
            vector = vectors[kind]
            file_path = _safe_evidence_file(evidence_dir, vector["path"])
            require(sha256_file(file_path) == vector["sha256"], f"rank {expected_rank} {kind} file SHA mismatch")
            loaded = np.load(file_path, allow_pickle=False)
            require(list(loaded.shape) == vector["shape"], f"rank {expected_rank} {kind} shape differs from receipt")
            require(str(loaded.dtype) == vector["dtype"] and loaded.nbytes == vector["nbytes"], f"rank {expected_rank} {kind} dtype/size differs from receipt")
            require(loaded.shape == (rank_size,), f"rank {expected_rank} {kind} payload differs from rank range")
            require(loaded.dtype == np.dtype("complex128"), f"rank {expected_rank} {kind} payload is not complex128")
            snapshot_before = capture[before_key][expected_rank]
            snapshot_after = capture[after_key][expected_rank]
            require(snapshot_before == snapshot_after, f"rank {expected_rank} {kind} changed between capture snapshots")
            require(capture[unchanged_key][expected_rank] is True, f"rank {expected_rank} {kind} unchanged flag is false")
            require(snapshot_after.get("dtype") == "complex128", f"rank {expected_rank} {kind} capture dtype mismatch")
            require(snapshot_after.get("global_size") == layout["global_size"], f"rank {expected_rank} {kind} capture global size mismatch")
            require(snapshot_after.get("local_size") == rank_size, f"rank {expected_rank} {kind} capture local size mismatch")
            require(snapshot_after.get("ownership_range") == expected_range, f"rank {expected_rank} {kind} capture ownership range mismatch")
            handle_key = "pc_source_handle_by_rank" if kind == "source" else "pc_target_handle_by_rank"
            require(snapshot_after.get("handle") == capture[handle_key][expected_rank], f"rank {expected_rank} {kind} capture handle mismatch")
            require(vector["shape"] == [rank_size], f"rank {expected_rank} {kind} receipt shape/range mismatch")
            require(vector["dtype"] == "complex128" and int(vector["nbytes"]) == rank_size * 16, f"rank {expected_rank} {kind} receipt dtype/bytes mismatch")
            require(_array_sha256(loaded) == snapshot_after.get("local_sha256"), f"rank {expected_rank} {kind} payload hash differs from capture")
            if kind == "source":
                require(capture["pc_source_target_alias_by_rank"][expected_rank] is False, f"rank {expected_rank} source/target alias flag is true")
            destination.append(loaded)
            retained_rank_bytes += int(loaded.nbytes)
    require(retained_rank_bytes <= 10 * 1024**2, "retaining real rank-local arrays exceeds the 10 MiB review allowance")
    require(capture["operator_input_unchanged_by_rank"] == [True] * 8, "original-A input was not unchanged on every rank")
    require(
        capture["operator_input_sha256_before_by_rank"] == capture["operator_input_sha256_after_by_rank"],
        "original-A input hash changed during capture",
    )
    require(
        capture["operator_input_handle_by_rank"] == capture["pc_target_handle_by_rank"],
        "captured target is not the original-A input handle",
    )
    require(
        capture["operator_input_sha256_after_by_rank"]
        == [entry["local_sha256"] for entry in capture["pc_target_after_by_rank"]],
        "captured target bytes do not match the original-A input hash",
    )
    require(len(set(capture["matmult_call_id_by_rank"])) == 1, "rank-local captures do not bind one MatMult call id")
    for expected_rank, (input_range, output_range) in enumerate(
        zip(capture["operator_input_range_by_rank"], capture["operator_output_range_by_rank"], strict=True)
    ):
        expected_range = [
            int(rank_offsets[expected_rank]),
            int(rank_offsets[expected_rank]) + int(rank_sizes[expected_rank]),
        ]
        require(input_range == expected_range, f"rank {expected_rank} original-A input range mismatch")
        require(output_range == expected_range, f"rank {expected_rank} original-A output range mismatch")
    vector_identity = _verify_modal_vector_bindings(
        layout,
        source_vectors,
        target_vectors,
        terminal_arrays["r_modal"],
        terminal_arrays["a"],
        expected_mpi_size=8,
        expected_modal_count=800,
    )
    owner_record = row.get("owner_lu_solve_record", {})
    require(owner_record.get("owner_rank") == 7, "owner LU record is not rank 7")
    require(owner_record.get("equation") == "S_B a - g", "owner LU equation identity mismatch")
    require(owner_record.get("status") == "passed" and owner_record.get("residual_passed") is True, "owner S_B solve audit is not passed")
    require(owner_record.get("input_unchanged") is True and owner_record.get("owner_lu_solve_count") == 1, "owner S_B solve identity/count mismatch")
    return {
        "repo_root": repo_root,
        "run_root": run_root,
        "evidence_dir": evidence_dir,
        "run_manifest": run_manifest,
        "supervisor_summary": supervisor_summary,
        "index": index,
        "ready_arrays": ready_arrays,
        "terminal_arrays": terminal_arrays,
        "terminal_row": row,
        "terminal_metrics": metrics,
        "layout": layout,
        "layout_check": vector_identity,
        "rank_vector_payload_bytes_retained": retained_rank_bytes,
        "owner_record": owner_record,
        "resource_preflight": resource,
        "input_sha256": {
            "run_manifest.json": EXPECTED_SHA256["run_manifest.json"],
            "supervisor_summary.json": EXPECTED_SHA256["supervisor_summary.json"],
            "evidence_index.json": EXPECTED_SHA256["index.json"],
            "s_b_ready.npz": EXPECTED_SHA256["v15_s_b_ready.npz"],
            "terminal_numeric_reject.npz": EXPECTED_SHA256["v15_terminal_numeric_reject.npz"],
            "rank_vector_index.npz": EXPECTED_SHA256["v15_terminal_rank_vectors_index.npz"],
            "packet_manifest.json": PACKET_MANIFEST_SHA256,
            "launch_manifest.json": EXPECTED_SHA256["launch_manifest.json"],
        },
        "constraint_identity_scope": "S_B/C snapshot C comes from system.modal_constraint; original A independently uses internal_modal_constraint_matrix. Same context/layout is recorded, but independent original-A C bytes/input correction are absent, so e_C remains constraint-action consistency difference rather than pure multiplication-rounding attribution",
    }


def _dc(value: Any) -> DComplex:
    if isinstance(value, (complex, np.complexfloating)):
        real = float(value.real)
        imag = float(value.imag)
    else:
        real = float(value)
        imag = 0.0
    require(math.isfinite(real) and math.isfinite(imag), "nonfinite input to Decimal conversion")
    return Decimal.from_float(real), Decimal.from_float(imag)


def _cadd(left: DComplex, right: DComplex) -> DComplex:
    return left[0] + right[0], left[1] + right[1]


def _csub(left: DComplex, right: DComplex) -> DComplex:
    return left[0] - right[0], left[1] - right[1]


def _cabs(value: DComplex) -> Decimal:
    return (value[0] * value[0] + value[1] * value[1]).sqrt()


def _dec_sum(values: Iterable[Decimal]) -> Decimal:
    result = Decimal(0)
    for value in values:
        result += value
    return result


def _ratio(numerator: Decimal, denominator: Decimal) -> tuple[Decimal | None, str]:
    if denominator == 0:
        if numerator == 0:
            return Decimal(0), "exact_zero_over_exact_zero"
        return None, "zero_scale_with_nonzero_difference"
    return numerator / denominator, "finite"


def _decimal_l2(values: Sequence[DComplex]) -> Decimal:
    squares = Decimal(0)
    for real, imag in values:
        squares += real * real + imag * imag
    return squares.sqrt()


def _decimal_dot_row(
    matrix: np.ndarray,
    row: int,
    vector: Sequence[DComplex],
    vector_abs: Sequence[Decimal],
) -> tuple[DComplex, Decimal, tuple[Decimal, Decimal], dict[str, Any]]:
    real = Decimal(0)
    imag = Decimal(0)
    absolute_complex_products = Decimal(0)
    real_component_product_scale = Decimal(0)
    imag_component_product_scale = Decimal(0)
    underflow_prone_products = 0
    overflow_prone_products = 0
    min_nonzero_product: Decimal | None = None
    max_product = Decimal(0)
    min_normal = Decimal.from_float(sys.float_info.min)
    max_finite = Decimal.from_float(sys.float_info.max)
    for column in range(matrix.shape[1]):
        mr, mi = _dc(matrix[row, column])
        vr, vi = vector[column]
        products = (mr * vr, mi * vi, mr * vi, mi * vr)
        for product in products:
            magnitude = abs(product)
            if magnitude == 0:
                continue
            min_nonzero_product = magnitude if min_nonzero_product is None else min(min_nonzero_product, magnitude)
            max_product = max(max_product, magnitude)
            if magnitude < min_normal:
                underflow_prone_products += 1
            if magnitude > max_finite:
                overflow_prone_products += 1
        real += mr * vr - mi * vi
        imag += mr * vi + mi * vr
        absolute_complex_products += _cabs((mr, mi)) * vector_abs[column]
        real_component_product_scale += abs(mr * vr) + abs(mi * vi)
        imag_component_product_scale += abs(mr * vi) + abs(mi * vr)
    return (
        (real, imag),
        absolute_complex_products,
        (real_component_product_scale, imag_component_product_scale),
        {
            "nonzero_products_below_min_normal_count": underflow_prone_products,
            "products_above_max_finite_count": overflow_prone_products,
            "minimum_nonzero_exact_product": _decimal_json(min_nonzero_product),
            "maximum_exact_product": str(max_product),
            "real_absolute_sum_exceeds_max_finite": real_component_product_scale > max_finite,
            "imag_absolute_sum_exceeds_max_finite": imag_component_product_scale > max_finite,
        },
    )


def _complex_json(value: DComplex) -> dict[str, str]:
    return {"real": str(value[0]), "imag": str(value[1])}


def _decimal_json(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def _row_decomposition(
    values: dict[str, DComplex],
    p_c: DComplex,
    p_s: DComplex,
    abs_c_a: Decimal,
    abs_s_a: Decimal,
    *,
    closure_limit: Decimal = HP_CROSSCHECK_LIMIT,
) -> dict[str, Any]:
    """Single source of the V18 five-term algebra for archive and fixtures."""
    d = values["d"]
    w = values["w_modal"]
    r = values["r_modal"]
    tb = values["t_bottom"]
    tt = values["t_top"]
    tc = values["t_constraint"]
    g = values["g"]
    t = _cadd(tb, tt)
    e_sub = _csub(d, _csub(w, r))
    e_sum = _csub(w, _cadd(t, tc))
    e_c = _csub(tc, p_c)
    e_s = _csub(p_s, g)
    e_k = _csub(_cadd(_csub(_cadd(t, p_c), p_s), g), r)
    total = _cadd(_cadd(_cadd(_cadd(e_sub, e_sum), e_c), e_s), e_k)
    closure = _csub(d, total)
    closure_scale = _dec_sum(
        (_cabs(d), _cabs(e_sub), _cabs(e_sum), _cabs(e_c), _cabs(e_s), _cabs(e_k))
    )
    closure_relative, closure_state = _ratio(_cabs(closure), closure_scale)
    if closure_relative is None:
        require(closure == (Decimal(0), Decimal(0)), "five-term closure has zero scale and nonzero error")
    else:
        require(closure_relative <= closure_limit, "five-term closure exceeds 1e-30 of uncancelled operation scale")

    v15_scale = _dec_sum((_cabs(tb), _cabs(tt), _cabs(tc), _cabs(r)))
    v15_eta, v15_state = _ratio(_cabs(d), v15_scale)
    c_cancel, c_cancel_state = _ratio(_cabs(p_c), abs_c_a)
    s_cancel, s_cancel_state = _ratio(_cabs(p_s), abs_s_a)
    s_berr_scale = abs_s_a + _cabs(g)
    s_berr, s_berr_state = _ratio(_cabs(e_s), s_berr_scale)
    operation_scales = {
        "e_sub": _dec_sum((_cabs(d), _cabs(w), _cabs(r))),
        "e_sum": _dec_sum((_cabs(w), _cabs(tb), _cabs(tt), _cabs(tc))),
        "e_C": _cabs(tc) + abs_c_a,
        "e_S": abs_s_a + _cabs(g),
        "e_K": _dec_sum((_cabs(tb), _cabs(tt), _cabs(p_c), _cabs(p_s), _cabs(g), _cabs(r))),
        "closure": closure_scale,
        "p_C": abs_c_a,
        "p_S": abs_s_a,
    }
    return {
        "t": t,
        "e_sub": e_sub,
        "e_sum": e_sum,
        "e_C": e_c,
        "e_S": e_s,
        "e_K": e_k,
        "closure": closure,
        "closure_scale": closure_scale,
        "closure_relative": closure_relative,
        "closure_state": closure_state,
        "v15_scale": v15_scale,
        "v15_eta": v15_eta,
        "v15_state": v15_state,
        "abs_C_abs_a": abs_c_a,
        "abs_S_abs_a": abs_s_a,
        "s_berr_scale": s_berr_scale,
        "schur_componentwise_berr": s_berr,
        "schur_berr_state": s_berr_state,
        "constraint_dot_cancellation_ratio": c_cancel,
        "constraint_dot_cancellation_state": c_cancel_state,
        "schur_dot_cancellation_ratio": s_cancel,
        "schur_dot_cancellation_state": s_cancel_state,
        "operation_scales": operation_scales,
    }


def decompose(
    arrays: dict[str, np.ndarray],
    C: np.ndarray,
    S: np.ndarray,
    *,
    precision: int = HP_PRECISION,
    peak_guard: bool = False,
) -> dict[str, Any]:
    n = int(arrays["d"].size)
    require(n == 800 and C.shape == S.shape == (n, n), "decomposition input shape mismatch")
    require(arrays["a"].shape == arrays["g"].shape == (n,), "a/g modal shape mismatch")
    require(all(value.shape == (n,) for value in arrays.values()), "row array shape mismatch")
    require(_is_complex_finite(C) and _is_complex_finite(S), "C/S contains nonfinite values")
    row_records: list[dict[str, Any]] = []
    with localcontext() as context:
        context.prec = precision
        vectors = {
            name: [_dc(value) for value in arrays[name]]
            for name in ("d", "w_modal", "r_modal", "t_bottom", "t_top", "t_constraint", "g", "a")
        }
        abs_vectors = {
            name: [_cabs(value) for value in vector]
            for name, vector in vectors.items()
        }
        CxS_values: dict[str, list[DComplex]] = {"p_C": [], "p_S": []}
        pC_abs_sums: list[Decimal] = []
        pS_abs_sums: list[Decimal] = []
        pC_component_scales: list[tuple[Decimal, Decimal]] = []
        pS_component_scales: list[tuple[Decimal, Decimal]] = []
        pC_product_risks: list[dict[str, Any]] = []
        pS_product_risks: list[dict[str, Any]] = []
        v15_denominators: list[Decimal] = []
        row_eta_hp: list[Decimal | None] = []
        eta2_terms = {
            name: _decimal_l2(vectors[name])
            for name in ("d", "t_bottom", "t_top", "t_constraint", "r_modal")
        }
        for row_index in range(n):
            pC, pC_abs, pC_scales, pC_risk = _decimal_dot_row(C, row_index, vectors["a"], abs_vectors["a"])
            pS, pS_abs, pS_scales, pS_risk = _decimal_dot_row(S, row_index, vectors["a"], abs_vectors["a"])
            CxS_values["p_C"].append(pC)
            CxS_values["p_S"].append(pS)
            pC_abs_sums.append(pC_abs)
            pS_abs_sums.append(pS_abs)
            pC_component_scales.append(pC_scales)
            pS_component_scales.append(pS_scales)
            pC_product_risks.append(pC_risk)
            pS_product_risks.append(pS_risk)

            values = {name: vector[row_index] for name, vector in vectors.items() if name != "a"}
            row_result = _row_decomposition(values, pC, pS, pC_abs, pS_abs)
            row_eta_hp.append(row_result["v15_eta"])
            v15_denominators.append(row_result["v15_scale"])
            orig_eta = float(arrays["row_relative_error"][row_index])
            require(math.isfinite(orig_eta) and orig_eta >= 0.0, f"row {row_index}: invalid stored V15 eta")
            budget_c = _complex_dot_roundoff_budget(
                C.shape[1], pC_scales, pC, pC_risk
            )
            budget_s = _complex_dot_roundoff_budget(
                S.shape[1], pS_scales, pS, pS_risk
            )
            e_c_bound_ratio, e_c_bound_state = _ratio(
                _cabs(row_result["e_C"]), Decimal(budget_c["complex_modulus_bound"])
            )
            e_s_bound_ratio, e_s_bound_state = _ratio(
                _cabs(row_result["e_S"]), Decimal(budget_s["complex_modulus_bound"])
            )
            archived = {
                name: _complex_json(_dc(arrays[name][row_index]))
                for name in (
                    "d",
                    "w_modal",
                    "r_modal",
                    "t_bottom",
                    "t_top",
                    "t_constraint",
                    "a",
                    "g",
                )
            }
            row_records.append(
                {
                    "row": row_index,
                    "v15_classification": "reject" if orig_eta > float(TOLERANCE) else "pass",
                    "v15_eta_binary64_recorded": orig_eta,
                    "v15_eta_90digit_from_saved_components": _decimal_json(row_result["v15_eta"]),
                    "v15_eta_state": row_result["v15_state"],
                    "d_abs_90": str(_cabs(values["d"])),
                    "v15_component_scale_s_90": str(row_result["v15_scale"]),
                    "row_relative_error_binary64": orig_eta,
                    "archived_binary64_components_exact_decimal": archived,
                    "complex_terms_90": {
                        name: _complex_json(row_result[name])
                        for name in ("e_sub", "e_sum", "e_C", "e_S", "e_K")
                    },
                    "complex_dot_products_90": {
                        "p_C": _complex_json(pC),
                        "p_S": _complex_json(pS),
                    },
                    "closure_error_90": _complex_json(row_result["closure"]),
                    "closure_scale_90": str(row_result["closure_scale"]),
                    "closure_relative_90": _decimal_json(row_result["closure_relative"]),
                    "closure_state": row_result["closure_state"],
                    "abs_C_times_abs_a_90": str(row_result["abs_C_abs_a"]),
                    "abs_S_times_abs_a_plus_abs_g_90": str(row_result["s_berr_scale"]),
                    "constraint_dot_cancellation_ratio_90": _decimal_json(row_result["constraint_dot_cancellation_ratio"]),
                    "constraint_dot_cancellation_state": row_result["constraint_dot_cancellation_state"],
                    "schur_dot_cancellation_ratio_90": _decimal_json(row_result["schur_dot_cancellation_ratio"]),
                    "schur_dot_cancellation_state": row_result["schur_dot_cancellation_state"],
                    "schur_componentwise_berr_90": _decimal_json(row_result["schur_componentwise_berr"]),
                    "schur_berr_state": row_result["schur_berr_state"],
                    "stored_decomposition_binary64": _complex_json(_dc(arrays["decomposition_error"][row_index])),
                    "complex128_dot_roundoff_reference": {"C_times_a": budget_c, "S_times_a": budget_s},
                    "e_C_abs_over_reference_dot_bound": _decimal_json(e_c_bound_ratio),
                    "e_C_bound_comparison_state": e_c_bound_state,
                    "e_S_abs_over_reference_dot_bound": _decimal_json(e_s_bound_ratio),
                    "e_S_bound_comparison_state": e_s_bound_state,
                    "roundoff_attribution_scope": "comparison only; C identity and S_B solve/capture construction errors are not included in a dot-rounding bound",
                }
            )
            if peak_guard:
                _enforce_peak_budget()

        d_norm = eta2_terms["d"]
        eta2_denominator = _dec_sum(
            eta2_terms[name]
            for name in ("t_bottom", "t_top", "t_constraint", "r_modal")
        )
        eta2, eta2_state = _ratio(d_norm, eta2_denominator)
        # NPZ eta logs are the authoritative original gate.  The Decimal table
        # independently reports the exact-from-binary64 component ratio.
        fails = [
            index
            for index, eta in enumerate(arrays["row_relative_error"])
            if float(eta) > float(TOLERANCE)
        ]
        owner_rhs_norm = _decimal_l2(vectors["g"])
        with localcontext() as context:
            context.prec = HP_PRECISION
            owner_residual = [
                _csub(CxS_values["p_S"][i], vectors["g"][i]) for i in range(n)
            ]
        owner_residual_norm = _decimal_l2(owner_residual)
    return {
        "precision": precision,
        "rows": row_records,
        "summary": {
            "row_count": n,
            "v15_tolerance": str(TOLERANCE),
            "stored_v15_reject_count": len(fails),
            "stored_v15_reject_rows": fails,
            "eta_terms_2_90": _decimal_json(eta2),
            "eta_terms_2_denominator_semantics": "||t_bottom||2 + ||t_top||2 + ||t_constraint||2 + ||r_modal||2",
            "eta_terms_2_state": eta2_state,
            "constraint_row_scale_semantics": "(|C||a|)_i using archived C and a",
            "schur_row_scale_semantics": "(|S_B||a|+|g|)_i using archived S_B, a and g",
            "owner_schur_norms_from_saved_arrays": {
                "g_norm_2": _decimal_json(owner_rhs_norm),
                "schur_residual_norm_2": _decimal_json(owner_residual_norm),
                "semantics": "||S_B a-g||2 / ||g||2; this is not componentwise BERR",
            },
        },
        "internal": {
            "p_C": CxS_values["p_C"],
            "p_S": CxS_values["p_S"],
            "p_C_abs_sums": pC_abs_sums,
            "p_S_abs_sums": pS_abs_sums,
            "v15_scales": v15_denominators,
            "v15_eta_hp": row_eta_hp,
        },
    }


def _complex_dot_roundoff_budget(
    n: int,
    component_scales: tuple[Decimal, Decimal],
    result: DComplex,
    product_risk: dict[str, Any],
) -> dict[str, Any]:
    """Conservative binary64 model for the two real sums in a complex dot."""
    with localcontext() as context:
        context.prec = HP_PRECISION
        u = Decimal(2) ** -53
        gamma_index = 2 * n + 2
        m_u = Decimal(gamma_index) * u
        require(m_u < 1, "gamma bound is undefined for this dot length")
        gamma = m_u / (Decimal(1) - m_u)
        real_scale, imag_scale = component_scales
        bound = gamma * (real_scale * real_scale + imag_scale * imag_scale).sqrt()
        max_finite = Decimal.from_float(sys.float_info.max)
        min_normal = Decimal.from_float(sys.float_info.min)
        output_subnormal_components = sum(
            1 for value in result if value != 0 and abs(value) < min_normal
        )
        risk_flags = []
        if product_risk["nonzero_products_below_min_normal_count"]:
            risk_flags.append("nonzero_product_below_min_normal")
        if product_risk["products_above_max_finite_count"]:
            risk_flags.append("product_may_overflow_binary64")
        if real_scale * (Decimal(1) + gamma) > max_finite or imag_scale * (Decimal(1) + gamma) > max_finite:
            risk_flags.append("uncancelled_component_sum_exceeds_max_finite")
        if output_subnormal_components:
            risk_flags.append("saved_dot_component_is_subnormal")
        reference_model_status = "no_known_saved-input_product_risk" if not risk_flags else "not_applicable_due_to_saved-input_range_risk"
        return {
            "model": "separate_real_imag_sums_of_2n_products",
            "n": n,
            "component_dtype": "float64",
            "complex_dtype": "complex128",
            "unit_roundoff": str(u),
            "gamma_index_2n_plus_2": gamma_index,
            "gamma_2n_plus_2": str(gamma),
            "real_un_cancelled_product_scale": str(real_scale),
            "imag_un_cancelled_product_scale": str(imag_scale),
            "complex_modulus_bound": str(bound),
            "bound_assumptions": "normal finite operations, no overflow/underflow/FTZ; generic reference sum model, not a claim about the archived BLAS or MPI reduction order",
            "error_bound_scope": "per real/imag sum, gamma_(2n+2) times its respective 2n-product absolute scale; complex modulus bound is gamma*sqrt(P_real^2+P_imag^2)",
            "actual_blas_or_mpi_reduction_order_persisted": False,
            "ftz_daz_runtime_state": "unknown_not_recorded",
            "intermediate_subnormal_state": "unknown_actual_partial_sum_order_not_recorded",
            "nonzero_products_below_min_normal_count": product_risk["nonzero_products_below_min_normal_count"],
            "products_above_max_finite_count": product_risk["products_above_max_finite_count"],
            "minimum_nonzero_exact_product": product_risk["minimum_nonzero_exact_product"],
            "maximum_exact_product": product_risk["maximum_exact_product"],
            "uncancelled_component_sum_exceeds_max_finite": bool(
                product_risk["real_absolute_sum_exceeds_max_finite"]
                or product_risk["imag_absolute_sum_exceeds_max_finite"]
            ),
            "saved_dot_subnormal_component_count": output_subnormal_components,
            "saved_input_range_status": reference_model_status,
            "actual_historical_kernel_bound_status": "unknown; archived BLAS/MPI order and FTZ/DAZ state are not recorded",
            "non_applicable_reason": None if not risk_flags else "saved input range shows underflow/overflow/subnormal risk; gamma model does not cover it",
        }


def _ratio_delta(left: Decimal, right: Decimal, scale: Decimal, label: str) -> Decimal:
    with localcontext() as context:
        context.prec = HP_CROSSCHECK_PRECISION
        delta = _cabs((left, right))
        value, _ = _ratio(delta, scale)
        require(value is not None, f"{label}: zero operation scale with nonzero precision difference")
        require(value <= HP_CROSSCHECK_LIMIT, f"{label}: 90/120-digit normalized difference exceeds 1e-30")
        return value


def _crosscheck_rows(
    arrays: dict[str, np.ndarray],
    C: np.ndarray,
    S: np.ndarray,
    rows_90: dict[str, Any],
    selected_rows: Sequence[int],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    with localcontext() as context:
        context.prec = HP_CROSSCHECK_PRECISION
        for row in selected_rows:
            low = rows_90["rows"][row]
            high_result = _analyze_selected_row(arrays, C, S, row, HP_CROSSCHECK_PRECISION)
            scales = high_result["operation_scales"]
            terms90 = low["complex_terms_90"]
            terms120 = high_result["complex_terms"]
            checks: dict[str, str] = {}
            for name in ("e_sub", "e_sum", "e_C", "e_S", "e_K"):
                left = Decimal(terms90[name]["real"])
                left_imag = Decimal(terms90[name]["imag"])
                right = Decimal(terms120[name]["real"])
                right_imag = Decimal(terms120[name]["imag"])
                checks[name] = str(
                    _ratio_delta(
                        left - right,
                        left_imag - right_imag,
                        scales[name],
                        f"row {row} {name}",
                    )
                )
            for name in ("p_C", "p_S"):
                low_value = low["complex_dot_products_90"][name]
                high_value = terms120[name]
                checks[name] = str(
                    _ratio_delta(
                        Decimal(low_value["real"]) - Decimal(high_value["real"]),
                        Decimal(low_value["imag"]) - Decimal(high_value["imag"]),
                        scales[name],
                        f"row {row} {name}",
                    )
                )
            low_closure = low["closure_error_90"]
            high_closure = terms120["closure"]
            checks["closure"] = str(
                _ratio_delta(
                    Decimal(low_closure["real"]) - Decimal(high_closure["real"]),
                    Decimal(low_closure["imag"]) - Decimal(high_closure["imag"]),
                    scales["closure"],
                    f"row {row} closure",
                )
            )
            result.append(
                {
                    "row": row,
                    "precision_low": HP_PRECISION,
                    "precision_high": HP_CROSSCHECK_PRECISION,
                    "normalized_complex_difference_by_quantity": checks,
                    "limit": str(HP_CROSSCHECK_LIMIT),
                    "pass": True,
                }
            )
    return result


def _analyze_selected_row(
    arrays: dict[str, np.ndarray], C: np.ndarray, S: np.ndarray, row: int, precision: int
) -> dict[str, Any]:
    with localcontext() as context:
        context.prec = precision
        values = {
            name: _dc(arrays[name][row])
            for name in ("d", "w_modal", "r_modal", "t_bottom", "t_top", "t_constraint", "g")
        }
        a = [_dc(value) for value in arrays["a"]]
        a_abs = [_cabs(value) for value in a]
        pC, absC, _, _ = _decimal_dot_row(C, row, a, a_abs)
        pS, absS, _, _ = _decimal_dot_row(S, row, a, a_abs)
        decomposed = _row_decomposition(values, pC, pS, absC, absS)
        return {
            "complex_terms": {
                name: _complex_json(decomposed[name])
                for name in ("e_sub", "e_sum", "e_C", "e_S", "e_K")
            } | {
                "p_C": _complex_json(pC),
                "p_S": _complex_json(pS),
                "closure": _complex_json(decomposed["closure"]),
            },
            "operation_scales": decomposed["operation_scales"],
        }


def _selected_representative_rows(analysis: dict[str, Any]) -> list[int]:
    rows = analysis["rows"]
    failing = [row["row"] for row in rows if row["v15_classification"] == "reject"]
    passing = [row["row"] for row in rows if row["v15_classification"] == "pass"]
    require(failing and passing, "representative row selection requires pass and reject rows")
    max_abs_d = max(
        failing,
        key=lambda index: (Decimal(rows[index]["d_abs_90"]), -index),
    )
    denominators = sorted(
        (
            Decimal(rows[index]["v15_component_scale_s_90"]),
            index,
        )
        for index in failing
    )
    median_denominator_row = denominators[(len(denominators) - 1) // 2][1]
    best_passing = min(
        passing,
        key=lambda index: (Decimal(rows[index]["v15_eta_90digit_from_saved_components"] or "0"), index),
    )
    selected: list[int] = []
    for row in (259, max_abs_d, median_denominator_row, best_passing):
        if row not in selected:
            selected.append(row)
    return selected


def _owner_norm_report(g: Sequence[DComplex], residual: Sequence[DComplex], owner_record: dict[str, Any]) -> dict[str, Any]:
    with localcontext() as context:
        context.prec = HP_PRECISION
        g_norm = _decimal_l2(g)
        residual_norm = _decimal_l2(residual)
        relative, state = _ratio(residual_norm, g_norm)
        recorded_rhs = Decimal.from_float(float(owner_record["rhs_norm"]))
        recorded_residual = Decimal.from_float(float(owner_record["residual_norm"]))
        recorded_relative = Decimal.from_float(float(owner_record["relative_backward_error"]))
        reconstructed, reconstructed_state = _ratio(recorded_residual, recorded_rhs)
        return {
            "g_norm_2_from_saved_g": str(g_norm),
            "schur_residual_norm_2_from_saved_S_a_g": str(residual_norm),
            "archived_owner_rhs_norm": str(recorded_rhs),
            "archived_owner_residual_norm": str(recorded_residual),
            "archived_owner_relative_backward_error": str(recorded_relative),
            "reconstructed_archived_relative": _decimal_json(reconstructed),
            "reconstructed_archived_relative_state": reconstructed_state,
            "saved_array_relative": _decimal_json(relative),
            "saved_array_relative_state": state,
            "denominator_semantics": "||g||2, not ||S_B||*||a||+||g|| and not componentwise BERR",
        }


def _run_archive_analysis(repo_root: Path, output_path: Path) -> dict[str, Any]:
    require(not output_path.exists(), f"refusing to overwrite existing analysis output: {output_path}")
    started = time.monotonic()
    archive = verify_inputs(repo_root)
    arrays = archive["terminal_arrays"]
    C = archive["ready_arrays"]["C"]
    S = archive["ready_arrays"]["s_b"]
    analysis = decompose(arrays, C, S, precision=HP_PRECISION, peak_guard=True)
    selected = _selected_representative_rows(analysis)
    crosschecks = _crosscheck_rows(arrays, C, S, analysis, selected)
    row_values = {name: [_dc(value) for value in arrays[name]] for name in ("g",)}
    with localcontext() as context:
        context.prec = HP_PRECISION
        owner_residual = [
            _csub(analysis["internal"]["p_S"][i], row_values["g"][i])
            for i in range(800)
        ]
    owner_report = _owner_norm_report(
        row_values["g"], owner_residual, archive["owner_record"]
    )
    owner_report["archived_recorded_rhs_norm"] = archive["owner_record"].get("rhs_norm")
    owner_report["archived_recorded_residual_norm"] = archive["owner_record"].get("residual_norm")
    analysis["summary"]["owner_schur_norms"] = owner_report
    analysis["representative_120_digit_crosschecks"] = crosschecks
    analysis["input_bindings"] = archive["input_sha256"]
    analysis["archive_identity"] = {
        "invocation_id": INVOCATION_ID,
        "runtime_source_sha": RUNTIME_SOURCE_SHA,
        "run_id": archive["index"]["identity"]["run_id"],
        "attempt_index": 1,
        "modal_count": 800,
        "modal_owner": 7,
        "layout": archive["layout_check"],
        "C_sha256": C_SHA256,
        "S_B_sha256": S_B_SHA256,
        "C_identity_limit": archive["constraint_identity_scope"],
        "rank_vector_mapping": {
            "persisted_roles": "rank-local PC source/target arrays, with handles/ranges/content hashes bound to capture_identity; source is the PC RHS, target carries z_b/z_t/a",
            "target_side_block_split": "target contains z_b/z_t/a; the per-rank bottom/top boundary is not persisted, so do not infer slices from merged local_size",
            "source_owner_modal_slice": "byte-identical to r_modal",
            "target_owner_modal_slice": "byte-identical to a",
            "retained_actual_rank_payload_bytes": archive["rank_vector_payload_bytes_retained"],
        },
    }
    analysis["terminal_row_record"] = {
        "schema": archive["terminal_row"]["schema"],
        "contract_id": archive["terminal_row"]["contract_id"],
        "status": archive["terminal_row"]["status"],
        "metrics": archive["terminal_metrics"],
        "outer_iteration": archive["terminal_row"].get("outer_iteration"),
    }
    analysis["resource"] = {
        **archive["resource_preflight"],
        "peak_rss_bytes": _peak_rss_bytes(),
        "process_peak_budget_bytes": PROCESS_RSS_BUDGET_BYTES,
    }
    analysis["classification"] = "offline_saved_binary64_error_decomposition_not_solver_pass"
    analysis["precision_contract"] = {
        "full_table_precision": HP_PRECISION,
        "representative_precision": HP_CROSSCHECK_PRECISION,
        "normalized_90_120_limit": str(HP_CROSSCHECK_LIMIT),
        "source_floats_converted_with": "Decimal.from_float",
        "zero_scale_rule": "only exact zero difference is accepted; no floor",
    }
    analysis["floating_point_reference_model"] = {
        "operation": "complex128 dot of archived complex128 operands, expanded into separate float64 real and imaginary sums",
        "n": 800,
        "products_per_real_or_imag_sum": 1600,
        "gamma_index": 1602,
        "unit_roundoff": str(Decimal(2) ** -53),
        "component_bound": "gamma_(2n+2) * sum of absolute values of the corresponding 2n real products",
        "complex_modulus_bound": "gamma_(2n+2) * sqrt(P_real^2 + P_imag^2)",
        "input_coefficient_generation_error_included": False,
        "actual_BLAS_or_MPI_reduction_order": "unknown_not_persisted",
        "FTZ_DAZ_state": "unknown_not_recorded",
        "subnormal_and_overflow_counts": "reported per row and separately from the normal-operation gamma model",
        "causal_claim": "none; this is a conservative reference summation model, not proof of archived kernel behavior",
    }
    analysis["runtime"] = {
        "parent_wall_seconds": time.monotonic() - started,
        "thread_environment": {name: os.environ.get(name) for name in THREAD_VARIABLES},
        "python": sys.executable,
        "analysis_script_sha256": sha256_file(Path(__file__).resolve()),
        "mpi_used": False,
        "FE_or_P4_or_QEP_or_solver_used": False,
    }
    internal = analysis.pop("internal")
    del internal
    _enforce_peak_budget()
    analysis["resource"]["peak_rss_bytes"] = _peak_rss_bytes()
    output_path = output_path.resolve()
    require(not output_path.exists(), f"refusing to overwrite existing output: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("x", encoding="utf-8") as stream:
        json.dump(analysis, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    return {
        "output": str(output_path),
        "output_sha256": sha256_file(output_path),
        "analysis_script_sha256": analysis["runtime"]["analysis_script_sha256"],
        "parent_wall_seconds": analysis["runtime"]["parent_wall_seconds"],
        "peak_rss_bytes": analysis["resource"]["peak_rss_bytes"],
        "row_count": analysis["summary"]["row_count"],
        "rejected_row_count": analysis["summary"]["stored_v15_reject_count"],
    }


def _peak_rss_bytes() -> int | None:
    value = _proc_status_bytes("VmHWM")
    if value is not None:
        return value
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(usage * 1024)


def _enforce_peak_budget() -> None:
    peak = _peak_rss_bytes()
    require(peak is not None, "process peak RSS cannot be measured")
    require(peak <= PROCESS_RSS_BUDGET_BYTES, "process VmHWM exceeded the 2 GiB analysis budget")


def _float_complex_dot(matrix_row: Sequence[complex], vector: Sequence[complex]) -> complex:
    result = 0.0 + 0.0j
    for left, right in zip(matrix_row, vector, strict=True):
        result += left * right
    return result


def _fixture_arrays(
    C: Sequence[Sequence[complex]],
    S: Sequence[Sequence[complex]],
    a: Sequence[complex],
    g: Sequence[complex],
    r: Sequence[complex],
    tb: Sequence[complex],
    tt: Sequence[complex],
    tc: Sequence[complex],
    w: Sequence[complex],
) -> tuple[dict[str, np.ndarray], np.ndarray, np.ndarray]:
    C_array = np.asarray(C, dtype=np.complex128)
    S_array = np.asarray(S, dtype=np.complex128)
    a_array = np.asarray(a, dtype=np.complex128)
    vectors = {
        "a": a_array,
        "g": np.asarray(g, dtype=np.complex128),
        "r_modal": np.asarray(r, dtype=np.complex128),
        "t_bottom": np.asarray(tb, dtype=np.complex128),
        "t_top": np.asarray(tt, dtype=np.complex128),
        "t_constraint": np.asarray(tc, dtype=np.complex128),
        "w_modal": np.asarray(w, dtype=np.complex128),
        "d": np.subtract(np.asarray(w, dtype=np.complex128), np.asarray(r, dtype=np.complex128)),
        "row_relative_error": np.zeros(len(r), dtype=np.float64),
        "row_relative_log_error": np.full(len(r), float("-inf"), dtype=np.float64),
        "row_scale": np.zeros(len(r), dtype=np.float64),
        "row_denominator_scaled": np.zeros(len(r), dtype=np.float64),
        "decomposition_error": np.zeros(len(r), dtype=np.complex128),
        "decomposition_row_relative_error": np.zeros(len(r), dtype=np.float64),
        "decomposition_row_relative_log_error": np.full(len(r), float("-inf"), dtype=np.float64),
    }
    for i in range(len(r)):
        denominator = sum(abs(value[i]) for value in (vectors["t_bottom"], vectors["t_top"], vectors["t_constraint"], vectors["r_modal"]))
        numerator = abs(vectors["d"][i])
        vectors["row_relative_error"][i] = 0.0 if denominator == 0.0 and numerator == 0.0 else (math.inf if denominator == 0.0 else numerator / denominator)
        if vectors["row_relative_error"][i] > 0.0 and math.isfinite(vectors["row_relative_error"][i]):
            vectors["row_relative_log_error"][i] = math.log(vectors["row_relative_error"][i])
        decomp = vectors["t_constraint"][i] + vectors["t_bottom"][i]
        decomp += vectors["t_top"][i]
        vectors["decomposition_error"][i] = vectors["w_modal"][i] - decomp
        decomp_denominator = denominator
        decomp_numerator = abs(vectors["decomposition_error"][i])
        vectors["decomposition_row_relative_error"][i] = 0.0 if decomp_denominator == 0.0 and decomp_numerator == 0.0 else (math.inf if decomp_denominator == 0.0 else decomp_numerator / decomp_denominator)
        if vectors["decomposition_row_relative_error"][i] > 0.0 and math.isfinite(vectors["decomposition_row_relative_error"][i]):
            vectors["decomposition_row_relative_log_error"][i] = math.log(vectors["decomposition_row_relative_error"][i])
    return vectors, C_array, S_array


def _small_decompose(
    arrays: dict[str, np.ndarray], C: np.ndarray, S: np.ndarray, precision: int = 90
) -> dict[str, Any]:
    # Fixture-only adapter accepts small vectors; the archive entrypoint enforces 800.
    n = int(arrays["d"].size)
    require(C.shape == S.shape == (n, n), "fixture C/S shape mismatch")
    with localcontext() as context:
        context.prec = precision
        a = [_dc(value) for value in arrays["a"]]
        a_abs = [_cabs(value) for value in a]
        records = []
        for i in range(n):
            values = {name: _dc(arrays[name][i]) for name in ("d", "w_modal", "r_modal", "t_bottom", "t_top", "t_constraint", "g")}
            pc, abs_c, _, _ = _decimal_dot_row(C, i, a, a_abs)
            ps, abs_s, _, _ = _decimal_dot_row(S, i, a, a_abs)
            row = _row_decomposition(values, pc, ps, abs_c, abs_s)
            records.append(
                {
                    **row,
                    "eta": row["v15_eta"],
                    "eta_state": row["v15_state"],
                    "p_C": pc,
                    "p_S": ps,
                    "abs_C_abs_a": abs_c,
                    "abs_S_abs_a": abs_s,
                }
            )
        return {"rows": records, "a": a, "g": [_dc(v) for v in arrays["g"]]}


def _small_layout_fixture() -> dict[str, Any]:
    return {
        "global_size": 4,
        "local_size_by_rank": [2, 2],
        "combined_offsets": [0, 2],
        "modal_owner": 1,
        "modal_count": 2,
        "modal_global_indices": [2, 3],
        "local_modal_range_by_rank": [[2, 2], [0, 2]],
    }


def _assert_rejected(callable_value: Any, label: str) -> None:
    try:
        callable_value()
    except (AnalysisError, ValueError):
        return
    raise AnalysisError(f"fixture negative was accepted: {label}")


def fixtures() -> dict[str, Any]:
    _enforce_single_process_thread()
    started = time.monotonic()
    results: list[dict[str, Any]] = []

    # 1. Large opposing components cancel exactly while the decomposition closes.
    arrays, C, S = _fixture_arrays(
        [[1.0]],
        [[2.0]],
        [1.0],
        [2.0],
        [1.0],
        [1.0e20],
        [-1.0e20],
        [1.0],
        [1.0],
    )
    exact = _small_decompose(arrays, C, S)["rows"][0]
    require(exact["closure"] == (Decimal(0), Decimal(0)), "exact-cancellation fixture did not close")
    require(exact["eta"] == 0 and exact["eta_state"] == "finite", "exact-cancellation fixture eta mismatch")
    zero_ok, zero_state = _ratio(Decimal(0), Decimal(0))
    require(zero_ok == 0 and zero_state == "exact_zero_over_exact_zero", "zero-scale exact-zero rule failed")
    zero_bad, zero_bad_state = _ratio(Decimal(1), Decimal(0))
    require(zero_bad is None and zero_bad_state == "zero_scale_with_nonzero_difference", "zero-scale nonzero error was not rejected")
    results.append({"case": "exact_opposing_component_cancellation_and_zero_scale_rule", "pass": True})

    # 2. Small absolute data can still have a genuine large relative discrepancy.
    eps = math.ldexp(1.0, -300)
    arrays, C, S = _fixture_arrays(
        [[1.0]],
        [[0.0]],
        [eps],
        [0.0],
        [0.0],
        [0.0],
        [0.0],
        [eps],
        [1.25 * eps],
    )
    small = _small_decompose(arrays, C, S)["rows"][0]
    require(small["eta"] is not None and small["eta"] > Decimal("1.2"), "small-data relative-error fixture failed to retain relative error")
    results.append({"case": "all_small_inputs_with_real_relative_error", "pass": True, "eta_90": str(small["eta"])})

    # 3. The dot product hides a small retained term behind cancellation.
    with localcontext() as context:
        context.prec = 90
        vector = [_dc(1.0), _dc(1.0), _dc(1.0)]
        row = np.asarray([float(2**60) + 0j, 1.0 + 0j, -float(2**60) + 0j], dtype=np.complex128)
        dot, abs_sum, component_scales, product_risk = _decimal_dot_row(
            row.reshape(1, 3), 0, vector, [_cabs(v) for v in vector]
        )
        cancellation, state = _ratio(_cabs(dot), abs_sum)
        expected_small_term = _dc(row[1])
        binary64_sequential = (
            float(row[0].real) + float(row[1].real)
        ) + float(row[2].real)
        require(binary64_sequential == 0.0, "binary64 cancellation fixture did not lose its middle term")
        require(dot == expected_small_term, "high-precision dot cancellation fixture lost the exact binary64 small term")
        require(cancellation is not None and cancellation < Decimal("1e-18"), "dot cancellation ratio fixture did not expose cancellation")
        bound = _complex_dot_roundoff_budget(3, component_scales, dot, product_risk)
        require(bound["gamma_index_2n_plus_2"] == 8, "complex gamma index is not 2n+2")
        synthetic_subnormal_risk = dict(product_risk)
        synthetic_subnormal_risk["nonzero_products_below_min_normal_count"] = 1
        not_applicable = _complex_dot_roundoff_budget(
            3, component_scales, dot, synthetic_subnormal_risk
        )
        require(
            not_applicable["saved_input_range_status"] == "not_applicable_due_to_saved-input_range_risk",
            "gamma model did not isolate underflow risk",
        )
    results.append({"case": "internal_dot_cancellation_and_complex_gamma_budget", "pass": True, "dot": _complex_json(dot), "cancellation_ratio": str(cancellation), "state": state, "gamma_index": bound["gamma_index_2n_plus_2"], "complex_modulus_bound": bound["complex_modulus_bound"], "underflow_risk_case": not_applicable["saved_input_range_status"]})

    # 4. One weak row with a wrong sign and a separately omitted component fail.
    tiny = math.ldexp(1.0, -100)
    arrays, C, S = _fixture_arrays(
        [[1.0, 0.0], [0.0, 1.0]],
        [[0.0, 0.0], [0.0, 0.0]],
        [1.0, tiny],
        [0.0, 0.0],
        [0.0, 0.0],
        [1.0, 0.0],
        [0.0, 0.0],
        [0.0, -tiny],
        [1.0, tiny],
    )
    weak = _small_decompose(arrays, C, S)["rows"][1]
    require(weak["eta"] is not None and weak["eta"] >= Decimal(1), "weak wrong-sign row did not reject by relative scale")
    require(_cabs(weak["e_sum"]) > 0 and _cabs(weak["e_C"]) > 0, "weak wrong-sign row did not localize component mismatch")
    arrays_omit = dict(arrays)
    arrays_omit["t_bottom"] = arrays["t_bottom"].copy()
    arrays_omit["t_bottom"][1] = 0.0
    arrays_omit["t_constraint"] = arrays["t_constraint"].copy()
    arrays_omit["t_constraint"][1] = 0.0
    omitted = _small_decompose(arrays_omit, C, S)["rows"][1]
    require(omitted["eta"] is None and omitted["eta_state"] == "zero_scale_with_nonzero_difference", "weak omitted-term row did not reject zero denominator")
    results.append({"case": "single_weak_row_wrong_sign_and_omission", "pass": True, "wrong_sign_eta_90": str(weak["eta"]), "omission_state": omitted["eta_state"]})

    # 5. Uniform and per-row non-real power-of-two rescaling preserve row ratios.
    C0 = np.asarray([[1.0 + 0.25j, 0.5 - 0.125j], [0.25 + 0.5j, 1.5 - 0.25j]], dtype=np.complex128)
    S0 = np.asarray([[0.75 - 0.125j, 0.25 + 0.5j], [0.5 + 0.25j, 0.625 - 0.125j]], dtype=np.complex128)
    a0 = np.asarray([1.0 + 0.5j, 0.5 - 0.25j], dtype=np.complex128)
    tb0 = np.asarray([0.25 + 0.125j, -0.5 + 0.25j], dtype=np.complex128)
    tt0 = np.asarray([-0.125 + 0.25j, 0.25 - 0.125j], dtype=np.complex128)
    tc0 = np.asarray([_float_complex_dot(C0[0], a0), _float_complex_dot(C0[1], a0)], dtype=np.complex128)
    r0 = np.asarray([0.125 - 0.25j, 0.0625 + 0.125j], dtype=np.complex128)
    w0 = np.asarray([(tb0[i] + tt0[i]) + tc0[i] for i in range(2)], dtype=np.complex128)
    g0 = np.asarray([_float_complex_dot(S0[0], a0), _float_complex_dot(S0[1], a0)], dtype=np.complex128)
    base, Cbase, Sbase = _fixture_arrays(C0, S0, a0, g0, r0, tb0, tt0, tc0, w0)
    base_result = _small_decompose(base, Cbase, Sbase)
    original_etas = [row["eta"] for row in base_result["rows"]]
    factors = [complex(0.0, math.ldexp(1.0, -20)), complex(0.0, -math.ldexp(1.0, 30))]
    def scaled_case(row_factors: Sequence[complex]) -> list[Decimal | None]:
        c_scaled = np.asarray(C0 * np.asarray(row_factors)[:, None], dtype=np.complex128)
        s_scaled = np.asarray(S0 * np.asarray(row_factors)[:, None], dtype=np.complex128)
        scaled = {
            name: value.copy()
            for name, value in base.items()
        }
        for key in ("g", "r_modal", "t_bottom", "t_top", "t_constraint", "w_modal", "d"):
            scaled[key] = np.asarray(base[key] * np.asarray(row_factors), dtype=np.complex128)
        return [row["eta"] for row in _small_decompose(scaled, c_scaled, s_scaled)["rows"]]
    uniform_etas = scaled_case([complex(0.0, math.ldexp(1.0, 18))] * 2)
    rowwise_etas = scaled_case(factors)
    for baseline, uniform_value, row_value in zip(original_etas, uniform_etas, rowwise_etas, strict=True):
        require(baseline is not None and uniform_value is not None and row_value is not None, "scale fixture has undefined ratio")
        require(abs(baseline - uniform_value) <= abs(baseline) * Decimal("1e-14"), "uniform complex scale changed row ratio")
        require(abs(baseline - row_value) <= abs(baseline) * Decimal("1e-14"), "rowwise complex scale changed row ratio")
    results.append({"case": "uniform_complex_and_per_row_complex_scaling", "pass": True, "uniform_phase": "i*2^18", "row_factors": ["i*2^-20", "-i*2^30"]})

    # 6. Layout and a/g bindings reject swaps; algebraic closure alone is not proof.
    layout = _small_layout_fixture()
    source = [
        np.asarray([0.0, 0.0], dtype=np.complex128),
        np.asarray([0.0 + 0j, 0.0 + 0j], dtype=np.complex128),
    ]
    target = [
        np.asarray([0.0, 0.0], dtype=np.complex128),
        np.asarray([2.0 + 1.0j, 5.0 - 1.0j], dtype=np.complex128),
    ]
    a_small = target[1].copy()
    r_small = np.asarray([3.0 + 4.0j, 6.0 + 8.0j], dtype=np.complex128)
    g_small = np.asarray([1.0 + 2.0j, 7.0 + 1.0j], dtype=np.complex128)
    source[1] = r_small.copy()
    valid_layout = _validate_layout(layout, source, target, expected_mpi_size=2, expected_modal_count=2)
    require(valid_layout["modal_owner"] == 1, "small owner layout not recognized")
    require(_same_complex_bytes(source[1], r_small) and _same_complex_bytes(target[1], a_small), "small vector binding fixture invalid")
    _assert_rejected(
        lambda: _verify_modal_vector_bindings(layout, source, target, r_small, g_small),
        "a/g swapped in target",
    )
    _assert_rejected(
        lambda: _verify_modal_vector_bindings(layout, source, target, g_small, a_small),
        "a/g swapped in source",
    )
    bad_layout = dict(layout)
    bad_layout["combined_offsets"] = [0, 1]
    _assert_rejected(lambda: _validate_layout(bad_layout, source, target), "wrong rank-major layout")
    S_small = np.asarray(
        [[2.0 + 1.0j, -1.0 + 0.5j], [0.5 - 1.0j, 1.5 + 0.25j]],
        dtype=np.complex128,
    )
    owner_norm = _owner_norm_report_fixture(S_small, a_small, g_small)
    with localcontext() as context:
        context.prec = HP_PRECISION
        require(Decimal(owner_norm["g_norm_2"]) == Decimal(55).sqrt(), "owner norm fixture denominator is not numeric ||g||2")
    require(owner_norm["relative"] != owner_norm["componentwise_berr"], "owner relative metric was confused with BERR")
    results.append({"case": "layout_and_a_g_binding_rejection_plus_owner_norm_semantics", "pass": True, "owner_norm": owner_norm})

    return {
        "schema": "task041.v18_modal_decomposition_fixture_result.v1",
        "classification": "analyzer_fixture_only_not_archive_P0_or_solver_evidence",
        "script_sha256": sha256_file(Path(__file__).resolve()),
        "precision": HP_PRECISION,
        "cases": results,
        "fixture_case_count": len(results),
        "fixture_wall_seconds": time.monotonic() - started,
        "peak_rss_bytes": _peak_rss_bytes(),
        "process_peak_budget_bytes": PROCESS_RSS_BUDGET_BYTES,
        "process_thread_count": _self_thread_count(),
        "thread_environment": {name: os.environ.get(name) for name in THREAD_VARIABLES},
    }


def _owner_norm_report_fixture(
    matrix: np.ndarray, solution: Sequence[complex], rhs: Sequence[complex]
) -> dict[str, str]:
    with localcontext() as context:
        context.prec = 90
        solution_decimal = [_dc(value) for value in solution]
        solution_abs = [_cabs(value) for value in solution_decimal]
        rhs_decimal = [_dc(value) for value in rhs]
        residual_decimal: list[DComplex] = []
        componentwise_berr_rows: list[Decimal | None] = []
        for row_index in range(matrix.shape[0]):
            action, abs_products, _, _ = _decimal_dot_row(
                matrix, row_index, solution_decimal, solution_abs
            )
            residual = _csub(action, rhs_decimal[row_index])
            residual_decimal.append(residual)
            row_scale = abs_products + _cabs(rhs_decimal[row_index])
            berr, _ = _ratio(_cabs(residual), row_scale)
            componentwise_berr_rows.append(berr)
        g_decimal = rhs_decimal
        g_norm = _decimal_l2(g_decimal)
        residual_norm = _decimal_l2(residual_decimal)
        relative, state = _ratio(residual_norm, g_norm)
        berr_values = [value for value in componentwise_berr_rows if value is not None]
        berr = max(berr_values) if berr_values else None
        return {
            "g_norm_2": str(g_norm),
            "residual_norm_2": str(residual_norm),
            "relative": str(relative),
            "relative_state": state,
            "componentwise_berr": str(berr),
            "denominator_semantics": "||g||2",
        }


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--self-test", action="store_true", help="run only the small algebra fixtures")
    mode.add_argument("--analyze", action="store_true", help="explicitly run the saved-archive P0 analysis")
    parser.add_argument("--repo-root", type=Path, default=_repo_root())
    parser.add_argument("--output", type=Path, help="new, nonexistent JSON output path; required by --analyze")
    args = parser.parse_args(argv)
    for variable in THREAD_VARIABLES:
        if os.environ.get(variable) != "1":
            parser.error(f"{variable} must be explicitly exported as 1 before starting Python")
    try:
        if args.self_test:
            result = fixtures()
            _enforce_peak_budget()
            _enforce_single_process_thread()
            result["peak_rss_bytes"] = _peak_rss_bytes()
            result["process_thread_count"] = _self_thread_count()
            print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))
            return 0
        if args.output is None:
            parser.error("--output is required with --analyze")
        output = args.output if args.output.is_absolute() else args.repo_root / args.output
        if output.exists():
            raise AnalysisError(f"refusing to overwrite existing output: {output}")
        result = _run_archive_analysis(args.repo_root, output)
        print(json.dumps({"schema": SCHEMA, "status": "written", **result}, sort_keys=True, indent=2))
        return 0
    except (AnalysisError, OSError, ValueError, zipfile.BadZipFile) as exc:
        print(json.dumps({"schema": SCHEMA, "status": "rejected", "error": f"{type(exc).__name__}: {exc}"}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
