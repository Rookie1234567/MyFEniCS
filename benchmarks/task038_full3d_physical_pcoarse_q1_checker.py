"""Independently check V16 source-authority staging artifacts.

This checker reads only JSON, JSONL, and canonical packet bytes.  It has no
dependency on the runner or on the numerical stack, so a worker cannot make
its own status field authoritative.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any


BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"
PHASE = "source-authority"
WORKFLOW = "q1-physical-pcoarse-source-authority"
CHECKER_SCHEMA = "task038.v16.q1.source-authority.checker.v1"
PARENT_SCHEMA = "task038.v16.q1.source-authority.parent.v1"
WORKER_SCHEMA = "task038.v16.q1.source-authority.worker.v1"
PROCESS_SCHEMA = "task038.v16.q1.source-authority.process-sample.v1"
MARKER_SCHEMA = "task038.v16.q1.source-authority.marker.v1"
JIT_GROUPS = (
    "positive-p6",
    "positive-p3",
    "positive-p1",
    "dtn-surface",
    "incident-rhs",
    "physical-volume-curl",
    "physical-volume-mass",
)
MARKER_ORDER = (
    "paths_ready",
    "abi_ready",
    "old_authority_streamed",
    "h10_reconstructed",
    "h50_bridged",
    "h10_released",
    "r3_ready",
    "record_written",
)
INPUT_SHA256 = "819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41"
PHYSICAL_MODEL_SHA256 = "9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f"
MODE_MANIFEST_SHA256 = "dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2"
OLD_SOURCE_SHA = "2c8fca90c7300b85b30021081868b699c0b306d2"
OLD_MANIFEST_SHA256 = "0bf0588f888aba14177b19cf7f410d8dfb3edabcbd018a1c1b76f99df016c8fd"
OLD_SHARD_SHA256 = "a544b8a27d901bb4466f0e88e80c0ec64824caec295749d9c941f41015a23204"
OLD_MANIFEST = Path(
    "benchmarks/artifacts/task038_extra_full3d_iterative_t5_authority_v2/"
    "r3_2c8fca90/mpi1/raw/canonical/mapped_solution.manifest.json"
)
OLD_SHARD_FILENAME = "mapped_solution.rank0000.jsonl"
OLD_PACKET_COUNT = 173802
SHARD_SCHEMA = "task037.canonical-vector-shard.v1"
MANIFEST_SCHEMA = "task037.canonical-vector-manifest.v1"
KEY_DIGEST_ALGORITHM = "sha256(canonical-key-json-v1)"
RSS_HARD = 2_000_000_000
_MISSING = object()


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _reject_constant(token: str) -> Any:
    raise ValueError(f"non-finite JSON constant: {token}")


def _load_json(path: Path) -> Any:
    return json.loads(
        path.read_bytes().decode("utf-8"),
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_constant,
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_sha(value: Any, length: int = 64) -> bool:
    return isinstance(value, str) and len(value) == length and all(
        char in "0123456789abcdef" for char in value
    )


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _field(value: Any, key: str, label: str, errors: list[str]) -> Any:
    if not isinstance(value, dict):
        errors.append(f"{label}: expected object")
        return _MISSING
    if key not in value:
        errors.append(f"{label}.{key}: missing")
        return _MISSING
    return value[key]


def _sample_effectively_readable(sample: dict[str, Any]) -> bool:
    observed_code = sample.get("worker_exit_code_observed_after_sample")
    return sample.get("all_status_readable") is True or (
        sample.get("all_status_readable") is False
        and sample.get("process_tree_exit_race_observed") is True
        and _is_int(observed_code)
        and observed_code == 0
    )


def _expect(value: Any, key: str, expected: Any, label: str, errors: list[str]) -> Any:
    actual = _field(value, key, label, errors)
    if actual is not _MISSING and (type(actual) is not type(expected) or actual != expected):
        errors.append(f"{label}.{key}: expected {expected!r}, got {actual!r}")
    return actual


def _root_path(root: Path, relative: Any, label: str, errors: list[str]) -> Path | None:
    if not isinstance(relative, str) or Path(relative).is_absolute():
        errors.append(f"path:{label}: expected relative path")
        return None
    root = root.resolve()
    path = (root / relative).resolve()
    if path != root and root not in path.parents:
        errors.append(f"path:{label}: escapes artifact root")
        return None
    return path


def _check_source(
    source: Any, expected_source_sha: str, errors: list[str]
) -> dict[str, Any] | None:
    if not isinstance(source, dict):
        errors.append("source: expected object")
        return None
    expected = {
        "commit_sha": expected_source_sha,
        "branch": BRANCH,
        "upstream": f"origin/{BRANCH}",
        "upstream_sha": expected_source_sha,
        "ahead": 0,
        "behind": 0,
        "tracked_worktree_clean": True,
        "qualified_activation": "1",
        "input_sha256": INPUT_SHA256,
    }
    for key, item in expected.items():
        _expect(source, key, item, "source", errors)
    executable = _field(source, "python_executable", "source", errors)
    prefix = _field(source, "python_prefix", "source", errors)
    if executable is not _MISSING and not isinstance(executable, str):
        errors.append("source.python_executable: expected string")
    if prefix is not _MISSING and not isinstance(prefix, str):
        errors.append("source.python_prefix: expected string")
    return source


def _check_input_facts(value: Any, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append("input: expected object")
        return
    _expect(value, "template_sha256", INPUT_SHA256, "input", errors)
    _expect(value, "physical_model_sha256", PHYSICAL_MODEL_SHA256, "input", errors)


def _check_runtime(value: Any, expected_mpi_size: int, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append("runtime: expected object")
        return
    _expect(value, "mpi_size", expected_mpi_size, "runtime", errors)
    _expect(value, "petsc_scalar_type", "complex128", "runtime", errors)
    _expect(value, "petsc_int_type", "int32", "runtime", errors)
    threads = _field(value, "threads", "runtime", errors)
    if isinstance(threads, dict):
        for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
            _expect(threads, name, "1", f"runtime.threads", errors)
    modules = _field(value, "abi_modules", "runtime", errors)
    if isinstance(modules, dict):
        for name in ("mpi4py", "petsc4py", "slepc4py", "dolfinx", "basix"):
            module_path = _field(modules, name, "runtime.abi_modules", errors)
            if module_path is not _MISSING and not isinstance(module_path, str):
                errors.append(f"runtime.abi_modules.{name}: expected string")


def _check_process_result(
    value: Any, label: str, expected_stage: str, errors: list[str]
) -> None:
    if not isinstance(value, dict):
        errors.append(f"lifecycle:{label}: expected object")
        return
    _expect(value, "stage", expected_stage, label, errors)
    _expect(value, "returncode", 0, label, errors)
    stop_reason = _field(value, "stop_reason", label, errors)
    if stop_reason is not _MISSING and stop_reason is not None:
        prefix = (
            "resource"
            if stop_reason in {"process_tree_rss_watchdog", "process_tree_swap"}
            else "lifecycle"
        )
        errors.append(f"{prefix}:{label}: unexpected stop_reason {stop_reason!r}")
    _expect(value, "process_group_gone", True, label, errors)
    _expect(value, "lifecycle_failure", False, label, errors)
    _expect(value, "max_swap_bytes", 0, label, errors)
    _expect(value, "all_status_readable", True, label, errors)
    for key in ("sample_count", "peak_rss_bytes"):
        item = _field(value, key, label, errors)
        if item is not _MISSING and (not _is_int(item) or item < 0):
            errors.append(f"lifecycle:{label}.{key}: expected nonnegative integer")
    argv = _field(value, "argv", label, errors)
    if argv is not _MISSING and not isinstance(argv, list):
        errors.append(f"lifecycle:{label}.argv: expected list")
    _expect(value, "signals", [], label, errors)


def _load_process_samples(path: Path, errors: list[str]) -> list[dict[str, Any]]:
    if not path.is_file():
        errors.append(f"path:process_samples: missing {path}")
        return []
    samples: list[dict[str, Any]] = []
    try:
        with path.open("rb") as stream:
            for index, raw in enumerate(stream, 1):
                if not raw.strip():
                    errors.append(f"json:process_samples:{index}: blank line")
                    continue
                try:
                    item = json.loads(
                        raw.decode("utf-8"),
                        object_pairs_hook=_reject_duplicate_keys,
                        parse_constant=_reject_constant,
                    )
                except (UnicodeError, ValueError, json.JSONDecodeError) as exc:
                    errors.append(f"json:process_samples:{index}: {exc}")
                    continue
                if not isinstance(item, dict):
                    errors.append(f"json:process_samples:{index}: expected object")
                    continue
                samples.append(item)
    except OSError as exc:
        errors.append(f"path:process_samples: {exc}")
    return samples


def _check_process(
    path: Path, parent_process: Any, errors: list[str]
) -> list[dict[str, Any]]:
    samples = _load_process_samples(path, errors)
    peak = 0
    swap = 0
    readable = True
    for index, sample in enumerate(samples, 1):
        _expect(sample, "schema", PROCESS_SCHEMA, f"process[{index}]", errors)
        rss = _field(sample, "rss_bytes", f"process[{index}]", errors)
        sample_swap = _field(sample, "swap_bytes", f"process[{index}]", errors)
        status = _field(sample, "all_status_readable", f"process[{index}]", errors)
        compiler = _field(sample, "compiler_descendant_count", f"process[{index}]", errors)
        race = sample.get("process_tree_exit_race_observed", False)
        observed_code = sample.get("worker_exit_code_observed_after_sample", _MISSING)
        valid_race = (
            race is True
            and status is False
            and _is_int(observed_code)
            and observed_code == 0
            and rss is None
            and sample_swap is None
        )
        if race is not False and not isinstance(race, bool):
            errors.append(f"lifecycle:process[{index}].process_tree_exit_race_observed: invalid")
        if race is True:
            if not valid_race:
                errors.append(f"lifecycle:process[{index}]: invalid exit-race annotation")
        elif observed_code is not _MISSING:
            errors.append(f"lifecycle:process[{index}]: exit-race code without annotation")
        if valid_race:
            pass
        elif _is_int(rss) and rss >= 0:
            peak = max(peak, rss)
        else:
            errors.append(f"process[{index}].rss_bytes: invalid")
        if valid_race:
            pass
        elif _is_int(sample_swap) and sample_swap >= 0:
            swap = max(swap, sample_swap)
        else:
            errors.append(f"process[{index}].swap_bytes: invalid")
        if isinstance(status, bool):
            readable = readable and _sample_effectively_readable(sample)
        else:
            errors.append(f"process[{index}].all_status_readable: invalid")
        if not _is_int(compiler) or compiler < 0:
            errors.append(f"process[{index}].compiler_descendant_count: invalid")
    if not isinstance(parent_process, dict):
        errors.append("process: expected summary object")
    else:
        _expect(parent_process, "sample_count", len(samples), "process", errors)
        _expect(parent_process, "peak_rss_bytes", peak, "process", errors)
        _expect(parent_process, "max_swap_bytes", swap, "process", errors)
        _expect(parent_process, "all_status_readable", readable, "process", errors)
    if peak >= RSS_HARD:
        errors.append(f"resource:process RSS {peak} is at or above {RSS_HARD}")
    if swap != 0:
        errors.append(f"resource:process swap is {swap}")
    if not readable:
        errors.append("lifecycle:process status is unreadable")
    return samples


def _check_stage(
    result: Any, expected_stage: str, samples: list[dict[str, Any]], errors: list[str]
) -> None:
    label = f"child[{expected_stage}]"
    _check_process_result(result, label, expected_stage, errors)
    if not isinstance(result, dict):
        return
    rows = [sample for sample in samples if sample.get("stage") == expected_stage]
    non_exit = [sample for sample in rows if sample.get("exit_code") is None]
    exit_rows = [sample for sample in rows if sample.get("exit_code") is not None]
    sample_count = result.get("sample_count")
    if not _is_int(sample_count) or sample_count != len(non_exit):
        errors.append(
            f"lifecycle:{label}: sample_count does not equal non-exit samples"
        )
    if len(exit_rows) != 1:
        errors.append(f"lifecycle:{label}: expected exactly one exit sample")
    else:
        exit_sample = exit_rows[0]
        if exit_sample.get("exit_code") != 0:
            errors.append(f"lifecycle:{label}: exit sample is not successful")
        if exit_sample.get("compiler_descendant_count") != 0:
            errors.append(f"lifecycle:{label}: exit sample has compiler descendants")
    if not non_exit:
        errors.append(f"lifecycle:{label}: no non-exit process samples")
    else:
        rss_values = [
            sample["rss_bytes"]
            for sample in non_exit
            if _is_int(sample.get("rss_bytes")) and sample["rss_bytes"] >= 0
        ]
        swap_values = [
            sample["swap_bytes"]
            for sample in non_exit
            if _is_int(sample.get("swap_bytes")) and sample["swap_bytes"] >= 0
        ]
        if result.get("peak_rss_bytes") != max(rss_values, default=0):
            errors.append(f"lifecycle:{label}: reported peak does not match samples")
        if result.get("max_swap_bytes") != max(swap_values, default=0):
            errors.append(f"lifecycle:{label}: reported swap does not match samples")
        readable = all(_sample_effectively_readable(sample) for sample in non_exit)
        if result.get("all_status_readable") != readable:
            errors.append(f"lifecycle:{label}: reported readability does not match samples")


def _cache_snapshot(path: Path) -> dict[str, Any]:
    artifacts: list[dict[str, Any]] = []
    for base, _directories, files in __import__("os").walk(path, followlinks=False):
        for filename in files:
            item = Path(base) / filename
            if item.suffix not in {".c", ".o", ".so"} or not item.is_file():
                continue
            artifacts.append(
                {
                    "relative_path": item.relative_to(path).as_posix(),
                    "bytes": item.stat().st_size,
                    "sha256": _sha256(item),
                }
            )
    artifacts.sort(key=lambda item: item["relative_path"])
    manifest = {
        "cache_dir": str(path.resolve()),
        "artifacts": artifacts,
        "artifact_count": len(artifacts),
    }
    encoded = json.dumps(
        manifest, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return {
        "artifact_count": len(artifacts),
        "manifest_sha256": hashlib.sha256(encoded).hexdigest(),
    }


def _check_cache(root: Path, parent: Any, worker: Any, errors: list[str]) -> None:
    cache_info = _field(parent, "cache", "parent", errors)
    if not isinstance(cache_info, dict):
        return
    initial = _field(cache_info, "initial", "parent.cache", errors)
    before = _field(cache_info, "before_worker", "parent.cache", errors)
    after = _field(cache_info, "after_worker", "parent.cache", errors)
    for label, snapshot in (("initial", initial), ("before_worker", before), ("after_worker", after)):
        if not isinstance(snapshot, dict):
            errors.append(f"cache:{label}: expected snapshot")
            continue
        count = _field(snapshot, "artifact_count", f"cache.{label}", errors)
        digest = _field(snapshot, "manifest_sha256", f"cache.{label}", errors)
        if not _is_int(count) or count < 0:
            errors.append(f"cache:{label}: invalid artifact count")
        if not _is_sha(digest):
            errors.append(f"cache:{label}: invalid manifest SHA")
    if isinstance(initial, dict) and initial.get("artifact_count") != 0:
        errors.append("cache:initial cache is not empty")
    if isinstance(before, dict) and isinstance(after, dict) and before != after:
        errors.append("cache:before_worker and after_worker differ")
    cache_path = root / "jit_cache"
    if not cache_path.is_dir():
        errors.append(f"path:jit_cache: missing {cache_path}")
    elif isinstance(after, dict):
        try:
            if _cache_snapshot(cache_path) != after:
                errors.append("cache:after_worker does not match cache contents")
        except OSError as exc:
            errors.append(f"path:jit_cache: {exc}")
    worker_cache = _field(worker, "cache", "worker", errors)
    parent_binding = _field(cache_info, "worker_binding", "parent.cache", errors)
    expected_home = str(cache_path.resolve())
    for label, item in (("worker", worker_cache), ("parent", parent_binding)):
        if not isinstance(item, dict):
            errors.append(f"cache:{label} binding is not an object")
            continue
        _expect(item, "xdg_cache_home", expected_home, f"cache.{label}", errors)
        _expect(item, "binding", True, f"cache.{label}", errors)


def _check_markers(
    root: Path, parent: Any, expected_source_sha: str, expected_mpi_size: int, errors: list[str]
) -> None:
    marker_info = _field(parent, "markers", "parent", errors)
    if not isinstance(marker_info, dict):
        return
    manifest_relative = _field(marker_info, "manifest_relative_path", "parent.markers", errors)
    manifest_path = _root_path(root, manifest_relative, "marker_manifest", errors)
    if manifest_path is None:
        return
    if not manifest_path.is_file():
        errors.append(f"path:marker_manifest: missing {manifest_path}")
        return
    try:
        actual_manifest_sha = _sha256(manifest_path)
        marker_rows = _load_json(manifest_path)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"json:marker_manifest: {exc}")
        return
    _expect(marker_info, "manifest_sha256", actual_manifest_sha, "parent.markers", errors)
    _expect(marker_info, "names", list(MARKER_ORDER), "parent.markers", errors)
    if not isinstance(marker_rows, list):
        errors.append("marker:manifest is not a list")
        return
    marker_dir = root / "markers"
    expected_paths = [marker_dir / f"{index:03d}_{name}.json" for index, name in enumerate(MARKER_ORDER)]
    actual_paths = sorted(marker_dir.glob("*.json")) if marker_dir.is_dir() else []
    if actual_paths != expected_paths:
        errors.append("marker:marker files are not the exact eight ordered files")
    expected_rows = [{"name": name, "sha256": _sha256(path)} for name, path in zip(MARKER_ORDER, expected_paths) if path.is_file()]
    if marker_rows != expected_rows:
        errors.append("marker:manifest rows do not match marker file hashes")
    for index, (name, path) in enumerate(zip(MARKER_ORDER, expected_paths)):
        if not path.is_file():
            errors.append(f"path:marker:{name}: missing")
            continue
        try:
            payload = _load_json(path)
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"json:marker:{name}: {exc}")
            continue
        if not isinstance(payload, dict):
            errors.append(f"marker:{name}: expected object")
            continue
        _expect(payload, "schema", MARKER_SCHEMA, f"marker.{name}", errors)
        _expect(payload, "name", name, f"marker.{name}", errors)
        _expect(payload, "marker_index", index, f"marker.{name}", errors)
        timestamp = _field(payload, "timestamp_ns", f"marker.{name}", errors)
        if not _is_int(timestamp):
            errors.append(f"marker:{name}: invalid timestamp")
        facts = _field(payload, "facts", f"marker.{name}", errors)
        if isinstance(facts, dict):
            _expect(facts, "phase", PHASE, f"marker.{name}.facts", errors)
            _expect(facts, "workflow", WORKFLOW, f"marker.{name}.facts", errors)
            _expect(facts, "source_sha", expected_source_sha, f"marker.{name}.facts", errors)
            _expect(facts, "mpi_size", expected_mpi_size, f"marker.{name}.facts", errors)


def _check_old_authority(worker: Any, errors: list[str]) -> None:
    authority = _field(worker, "old_authority", "worker", errors)
    if not isinstance(authority, dict):
        return
    expected = {
        "source_sha": OLD_SOURCE_SHA,
        "manifest_relative_path": OLD_MANIFEST.as_posix(),
        "manifest_sha256": OLD_MANIFEST_SHA256,
        "shard_filename": OLD_SHARD_FILENAME,
        "shard_sha256": OLD_SHARD_SHA256,
        "packet_count": OLD_PACKET_COUNT,
    }
    for key, item in expected.items():
        _expect(authority, key, item, "worker.old_authority", errors)
    h10 = _field(authority, "h10", "worker.old_authority", errors)
    if not isinstance(h10, dict):
        return
    for key in ("selected_key_count", "extracted_key_count"):
        _expect(h10, key, OLD_PACKET_COUNT, "worker.old_authority.h10", errors)
    for key in ("selected_finite", "extracted_finite", "extraction_repeat_finite", "input_unchanged"):
        _expect(h10, key, True, "worker.old_authority.h10", errors)
    for key in ("input_before_digest", "input_after_digest", "extraction_digest", "extraction_repeat_digest"):
        item = _field(h10, key, "worker.old_authority.h10", errors)
        if item is not _MISSING and not _is_sha(item):
            errors.append(f"worker.old_authority.h10.{key}: invalid SHA")
    if h10.get("input_before_digest") != h10.get("input_after_digest"):
        errors.append("worker.old_authority.h10: selected input digest changed")
    if h10.get("extraction_digest") != h10.get("extraction_repeat_digest"):
        errors.append("worker.old_authority.h10: extraction repeat digest changed")
    for key in ("reconstruction_relative_l2", "extraction_repeat_relative_l2"):
        item = _field(h10, key, "worker.old_authority.h10", errors)
        if not _finite(item) or float(item) > 1.0e-12:
            errors.append(f"worker.old_authority.h10.{key}: exceeds 1e-12")
    _expect(h10, "source_role", "full_fe", "worker.old_authority.h10", errors)
    _expect(h10, "canonical_role", "full_fe", "worker.old_authority.h10", errors)


def _check_h50(worker: Any, errors: list[str]) -> None:
    bridge = _field(worker, "h50_bridge", "worker", errors)
    if not isinstance(bridge, dict):
        return
    _expect(bridge, "source_input_unchanged", True, "worker.h50_bridge", errors)
    before = _field(bridge, "source_before_sha256", "worker.h50_bridge", errors)
    after = _field(bridge, "source_after_sha256", "worker.h50_bridge", errors)
    if not _is_sha(before) or not _is_sha(after) or before != after:
        errors.append("worker.h50_bridge: source input digest does not close")
    audit = _field(bridge, "bridge_audit", "worker.h50_bridge", errors)
    if isinstance(audit, dict):
        _expect(audit, "schema", "task038.nonmatching_hcurl_primal_bridge.v1", "worker.h50_bridge.bridge_audit", errors)
        _expect(audit, "method", "dolfinx.create_interpolation_data+interpolate_nonmatching", "worker.h50_bridge.bridge_audit", errors)
        _expect(audit, "target_mpc_homogenize_count", 1, "worker.h50_bridge.bridge_audit", errors)
        _expect(audit, "target_mpc_backsubstitution_count", 1, "worker.h50_bridge.bridge_audit", errors)
        _expect(audit, "padding", 1.0e-10, "worker.h50_bridge.bridge_audit", errors)
        _expect(audit, "global_matrix", False, "worker.h50_bridge.bridge_audit", errors)
        _expect(audit, "numeric_allgather", False, "worker.h50_bridge.bridge_audit", errors)
    action = _field(bridge, "action_vector", "worker.h50_bridge", errors)
    if isinstance(action, dict):
        _expect(action, "role", "fullspace_slave_zero", "worker.h50_bridge.action_vector", errors)
        _expect(action, "finite", True, "worker.h50_bridge.action_vector", errors)
        norm = _field(action, "norm", "worker.h50_bridge.action_vector", errors)
        if not _finite(norm):
            errors.append("worker.h50_bridge.action_vector.norm: non-finite")
        slave = _field(action, "owned_slave_max", "worker.h50_bridge.action_vector", errors)
        if not _finite(slave) or float(slave) != 0.0:
            errors.append("worker.h50_bridge.action_vector.owned_slave_max: expected zero")
        digest = _field(action, "array_sha256", "worker.h50_bridge.action_vector", errors)
        if not _is_sha(digest):
            errors.append("worker.h50_bridge.action_vector.array_sha256: invalid SHA")
    canonical = _field(bridge, "canonical_field", "worker.h50_bridge", errors)
    if isinstance(canonical, dict):
        _expect(canonical, "canonical_role", "full_fe", "worker.h50_bridge.canonical_field", errors)
        _expect(canonical, "finite", True, "worker.h50_bridge.canonical_field", errors)
        norm = _field(canonical, "norm", "worker.h50_bridge.canonical_field", errors)
        if not _finite(norm):
            errors.append("worker.h50_bridge.canonical_field.norm: non-finite")
        packet_count = _field(canonical, "packet_count", "worker.h50_bridge.canonical_field", errors)
        if not _is_int(packet_count) or packet_count <= 0:
            errors.append("worker.h50_bridge.canonical_field.packet_count: expected positive integer")
        digest = _field(canonical, "array_sha256", "worker.h50_bridge.canonical_field", errors)
        if not _is_sha(digest):
            errors.append("worker.h50_bridge.canonical_field.array_sha256: invalid SHA")


def _canonical_key_bytes(key: Any) -> bytes:
    def valid(value: Any) -> bool:
        if isinstance(value, dict):
            return set(value) == {"tuple"} and isinstance(value["tuple"], list) and all(
                valid(item) for item in value["tuple"]
            )
        return value is None or isinstance(value, (bool, int, float, str))

    if not valid(key):
        raise ValueError("canonical key tuple encoding is invalid")
    return json.dumps(
        key, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _read_r3_shard(
    path: Path,
    metadata: Any,
    rank: int,
    global_keys: set[bytes],
    errors: list[str],
) -> dict[bytes, complex]:
    label = f"r3.shard[{rank}]"
    if not path.is_file():
        errors.append(f"path:{label}: missing {path}")
        return {}
    digest = hashlib.sha256()
    packets: dict[bytes, complex] = {}
    local_duplicate_count = 0
    finite = True
    count = 0
    try:
        with path.open("rb") as stream:
            for line_number, raw in enumerate(stream, 1):
                digest.update(raw)
                try:
                    packet = json.loads(
                        raw.decode("utf-8"),
                        object_pairs_hook=_reject_duplicate_keys,
                        parse_constant=_reject_constant,
                    )
                    if not isinstance(packet, dict):
                        raise ValueError("packet is not an object")
                    _schema = packet["schema_version"]
                    key = packet["key"]
                    key_digest = packet["key_sha256"]
                    value = packet["value"]
                    if _schema != SHARD_SCHEMA:
                        raise ValueError("unsupported packet schema")
                    key_bytes = _canonical_key_bytes(key)
                    expected_key_digest = hashlib.sha256(key_bytes).hexdigest()
                    if key_digest != expected_key_digest:
                        raise ValueError("key digest mismatch")
                    if not _is_sha(key_digest):
                        raise ValueError("invalid key digest")
                    if not isinstance(value, list) or len(value) != 2 or not all(
                        _finite(item) for item in value
                    ):
                        raise ValueError("invalid coefficient")
                    coefficient = complex(float(value[0]), float(value[1]))
                except (KeyError, TypeError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
                    errors.append(f"json:{label}:{line_number}: {exc}")
                    continue
                count += 1
                finite = finite and math.isfinite(coefficient.real) and math.isfinite(coefficient.imag)
                if key_bytes in packets or key_bytes in global_keys:
                    local_duplicate_count += 1
                    errors.append(f"shard:{label}: duplicate canonical key")
                else:
                    packets[key_bytes] = coefficient
                    global_keys.add(key_bytes)
    except OSError as exc:
        errors.append(f"path:{label}: {exc}")
        return packets
    if not isinstance(metadata, dict):
        errors.append(f"shard:{label}: metadata is not an object")
        return packets
    _expect(metadata, "rank", rank, label, errors)
    _expect(metadata, "schema_version", SHARD_SCHEMA, label, errors)
    _expect(metadata, "dtype", "complex128", label, errors)
    _expect(metadata, "key_digest_algorithm", KEY_DIGEST_ALGORITHM, label, errors)
    _expect(metadata, "packet_count", count, label, errors)
    _expect(metadata, "file_sha256", digest.hexdigest(), label, errors)
    _expect(metadata, "packet_finite", finite, label, errors)
    _expect(metadata, "local_duplicate_count", local_duplicate_count, label, errors)
    return packets


def _check_r3(
    root: Path, worker: Any, expected_mpi_size: int, errors: list[str]
) -> tuple[dict[bytes, complex], dict[str, Any]]:
    r3 = _field(worker, "r3", "worker", errors)
    if not isinstance(r3, dict):
        return {}, {}
    expected_facts = {
        "schema": "task038.r3-long-tail-derived.current-h50.v1",
        "name": "r3_long_tail_derived",
        "formula": "r50=b50-A6*x50; r3=P63^H*r50",
        "mapped_primal_authority_role": "full_fe",
        "mapped_primal_action_storage": "fullspace_slave_zero",
        "residual_role": "full_fe_dual",
        "probe_role": "full_fe_dual",
        "apply_count": 2,
        "input_unchanged": True,
        "finite": True,
    }
    for key, item in expected_facts.items():
        _expect(r3, key, item, "worker.r3", errors)
    repeat = _field(r3, "repeat_relative_l2", "worker.r3", errors)
    norm = _field(r3, "norm", "worker.r3", errors)
    slave = _field(r3, "owned_slave_max", "worker.r3", errors)
    if not _finite(repeat) or float(repeat) > 1.0e-12:
        errors.append("worker.r3.repeat_relative_l2: exceeds 1e-12")
    if not _finite(norm):
        errors.append("worker.r3.norm: non-finite")
    if not _finite(slave) or float(slave) != 0.0:
        errors.append("worker.r3.owned_slave_max: expected zero")
    for key in (
        "action_input_before_sha256",
        "action_input_after_first_sha256",
        "action_input_after_second_sha256",
    ):
        item = _field(r3, key, "worker.r3", errors)
        if not _is_sha(item):
            errors.append(f"worker.r3.{key}: invalid SHA")
    if not (
        r3.get("action_input_before_sha256")
        == r3.get("action_input_after_first_sha256")
        == r3.get("action_input_after_second_sha256")
    ):
        errors.append("worker.r3: action input digest changed")
    rhs_facts = _field(r3, "physical_rhs_facts", "worker.r3", errors)
    if not isinstance(rhs_facts, dict):
        errors.append("worker.r3.physical_rhs_facts: expected object")
    descriptor = _field(r3, "manifest", "worker.r3", errors)
    if not isinstance(descriptor, dict):
        return {}, {}
    manifest_relative = _field(descriptor, "manifest_relative_path", "worker.r3.manifest", errors)
    manifest_path = _root_path(root, manifest_relative, "r3_manifest", errors)
    if manifest_path is None or not manifest_path.is_file():
        errors.append("path:r3_manifest: missing")
        return {}, {}
    actual_manifest_sha = _sha256(manifest_path)
    _expect(descriptor, "manifest_sha256", actual_manifest_sha, "worker.r3.manifest", errors)
    _expect(descriptor, "role", "full_fe_dual", "worker.r3.manifest", errors)
    _expect(descriptor, "mpi_size", expected_mpi_size, "worker.r3.manifest", errors)
    try:
        manifest = _load_json(manifest_path)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"json:r3_manifest: {exc}")
        return {}, {}
    if not isinstance(manifest, dict):
        errors.append("r3: manifest is not an object")
        return {}, {}
    _expect(manifest, "schema_version", MANIFEST_SCHEMA, "r3.manifest", errors)
    _expect(manifest, "role", "full_fe_dual", "r3.manifest", errors)
    _expect(manifest, "mpi_size", expected_mpi_size, "r3.manifest", errors)
    _expect(manifest, "dtype", "complex128", "r3.manifest", errors)
    _expect(manifest, "key_digest_algorithm", KEY_DIGEST_ALGORITHM, "r3.manifest", errors)
    shards = _field(manifest, "per_rank_shards", "r3.manifest", errors)
    if not isinstance(shards, list):
        errors.append("r3: per_rank_shards is not a list")
        return {}, {}
    if len(shards) != expected_mpi_size:
        errors.append("r3: shard count does not match MPI size")
    global_keys: set[bytes] = set()
    packets: dict[bytes, complex] = {}
    shard_counts = []
    for rank, metadata in enumerate(shards):
        if not isinstance(metadata, dict):
            errors.append(f"schema:r3.shard[{rank}]: metadata is not an object")
            continue
        filename = _field(metadata, "filename", f"r3.shard[{rank}]", errors)
        if not isinstance(filename, str) or Path(filename).name != filename or Path(filename).is_absolute():
            errors.append(f"path:r3.shard[{rank}]: filename is not a basename")
            continue
        shard_path = (manifest_path.parent / filename).resolve()
        if root not in shard_path.parents:
            errors.append(f"path:r3.shard[{rank}]: escapes artifact root")
            continue
        shard_packets = _read_r3_shard(shard_path, metadata, rank, global_keys, errors)
        packets.update(shard_packets)
        count = metadata.get("packet_count")
        if _is_int(count):
            shard_counts.append(count)
    total = sum(shard_counts)
    _expect(manifest, "global_summed_packet_count", total, "r3.manifest", errors)
    _expect(manifest, "summed_local_duplicate_count", 0, "r3.manifest", errors)
    _expect(descriptor, "packet_count", total, "worker.r3.manifest", errors)
    audit = _field(manifest, "extractor_audit", "r3.manifest", errors)
    if isinstance(audit, dict):
        _expect(audit, "role", "full_fe_dual", "r3.manifest.extractor_audit", errors)
        _expect(audit, "source", "build_r3_long_tail_derived_probe", "r3.manifest.extractor_audit", errors)
        _expect(audit, "numeric_allgather", False, "r3.manifest.extractor_audit", errors)
        if not shards or not isinstance(shards[0], dict):
            errors.append("r3.manifest.extractor_audit.local_packet_count: rank0 metadata unavailable")
        else:
            _expect(audit, "local_packet_count", shards[0].get("packet_count"), "r3.manifest.extractor_audit", errors)
        _expect(audit, "global_packet_count", total, "r3.manifest.extractor_audit", errors)
        _expect(audit, "local_duplicate_count", 0, "r3.manifest.extractor_audit", errors)
        _expect(audit, "summed_local_duplicate_count", 0, "r3.manifest.extractor_audit", errors)
        _expect(audit, "slave_exclusion", True, "r3.manifest.extractor_audit", errors)
    return packets, {"packet_count": total, "key_count": len(packets), "manifest_sha256": actual_manifest_sha}


def _artifact_details(
    parent_record: str | Path, expected_source_sha: str, expected_mpi_size: int
) -> dict[str, Any]:
    errors: list[str] = []
    record_path = Path(parent_record).resolve()
    root = record_path.parent
    metrics: dict[str, Any] = {"mpi_size": expected_mpi_size}
    try:
        parent = _load_json(record_path)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        return {
            "result": _result([f"json:parent_record: {exc}"], metrics),
            "root": root,
            "parent": None,
            "worker": None,
            "packets": {},
        }
    if not isinstance(parent, dict):
        return {
            "result": _result(["schema:parent_record: expected object"], metrics),
            "root": root,
            "parent": None,
            "worker": None,
            "packets": {},
        }
    _expect(parent, "schema", PARENT_SCHEMA, "parent", errors)
    _expect(parent, "error", None, "parent", errors)
    source = _check_source(parent.get("source"), expected_source_sha, errors)
    paths = _field(parent, "paths", "parent", errors)
    path_values: dict[str, Path] = {}
    if isinstance(paths, dict):
        for key in ("jit_cache", "process_samples", "worker_record", "marker_manifest"):
            path = _root_path(root, paths.get(key), f"paths.{key}", errors)
            if path is not None:
                path_values[key] = path
        expected_paths = {
            "jit_cache": root / "jit_cache",
            "process_samples": root / "parent_process.jsonl",
            "worker_record": root / "raw" / "worker_record.json",
            "marker_manifest": root / "marker_manifest.json",
        }
        for key, expected in expected_paths.items():
            if key in path_values and path_values[key] != expected.resolve():
                errors.append(f"path:{key}: unexpected path")
    samples = _check_process(
        path_values.get("process_samples", root / "parent_process.jsonl"),
        parent.get("process"),
        errors,
    )
    metrics["process"] = parent.get("process")
    children = parent.get("children")
    if not isinstance(children, list) or len(children) != len(JIT_GROUPS):
        errors.append("lifecycle:parent.children: expected seven children")
        children = []
    for index, group in enumerate(JIT_GROUPS):
        result = children[index] if index < len(children) else None
        if isinstance(result, dict):
            _expect(result, "group", group, f"child[{index}]", errors)
        _check_stage(result, f"precompile:{group}", samples, errors)
    worker_result = parent.get("worker")
    _check_stage(worker_result, "worker", samples, errors)
    worker_record_path = path_values.get("worker_record", root / "raw" / "worker_record.json")
    worker = None
    if not worker_record_path.is_file():
        errors.append("path:worker_record: missing")
    else:
        try:
            worker = _load_json(worker_record_path)
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"json:worker_record: {exc}")
    if not isinstance(worker, dict):
        errors.append("schema:worker_record: expected object")
        worker = None
    else:
        _expect(worker, "schema", WORKER_SCHEMA, "worker", errors)
        _expect(worker, "raw_facts_only", True, "worker", errors)
        worker_source = _check_source(worker.get("source"), expected_source_sha, errors)
        if source is not None and worker_source is not None and worker_source != source:
            errors.append("source:parent and worker source facts differ")
        _check_runtime(worker.get("runtime"), expected_mpi_size, errors)
        _check_input_facts(worker.get("input"), errors)
        target_mode = worker.get("target_mode")
        if not isinstance(target_mode, dict):
            errors.append("worker.target_mode: expected object")
        else:
            _expect(target_mode, "mode_count", 80, "worker.target_mode", errors)
            _expect(target_mode, "mode_manifest_sha256", MODE_MANIFEST_SHA256, "worker.target_mode", errors)
        _check_old_authority(worker, errors)
        _check_h50(worker, errors)
    if isinstance(worker_result, dict) and worker is not None:
        _expect(worker_result, "record_present", True, "parent.worker", errors)
        record_sha = _field(worker_result, "record_sha256", "parent.worker", errors)
        if not _is_sha(record_sha) or record_sha != _sha256(worker_record_path):
            errors.append("path:parent.worker.record_sha256: does not match worker record")
        for key, filename in (("stdout_sha256", "worker.stdout.log"), ("stderr_sha256", "worker.stderr.log")):
            log_path = root / filename
            item = _field(worker_result, key, "parent.worker", errors)
            if not log_path.is_file():
                errors.append(f"path:{filename}: missing")
            elif not _is_sha(item) or item != _sha256(log_path):
                errors.append(f"path:parent.worker.{key}: does not match log")
    _check_cache(root, parent, worker or {}, errors)
    _check_markers(root, parent, expected_source_sha, expected_mpi_size, errors)
    packets, r3_metrics = _check_r3(root, worker or {}, expected_mpi_size, errors)
    metrics["r3"] = r3_metrics
    metrics["children"] = len(children)
    return {
        "result": _result(errors, metrics),
        "root": root,
        "parent": parent,
        "worker": worker,
        "packets": packets,
    }


def _classify(errors: list[str]) -> str:
    if not errors:
        return "SOURCE_AUTHORITY_PASS"
    normalized = [
        error[5:] if error.startswith(("mpi1:", "mpi2:")) else error
        for error in errors
    ]
    if any(error.startswith("resource:") for error in normalized):
        return "SOURCE_AUTHORITY_RESOURCE_GATE_FAIL"
    if any(
        error.startswith(
            (
                "schema:",
                "source:",
                "runtime:",
                "input:",
                "path:",
                "json:",
                "cache:",
                "marker:",
                "lifecycle:",
            )
        )
        for error in normalized
    ):
        return "INFRASTRUCTURE_FAILURE_RETRYABLE"
    return "SOURCE_AUTHORITY_GATE_FAIL"


def _result(errors: list[str], metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": CHECKER_SCHEMA,
        "passed": not errors,
        "classification": _classify(errors),
        "errors": errors,
        "metrics": metrics,
        "evidence_kind": {
            "process": "measured",
            "canonical": "measured",
            "hash": "derived",
            "cache": "derived",
            "mpi_relative": "derived",
        },
    }


def check_artifact(
    parent_record: str | Path, expected_source_sha: str, expected_mpi_size: int
) -> dict[str, Any]:
    """Check one source-authority parent record and its worker artifact."""

    if expected_mpi_size not in (1, 2):
        return _result(["schema:expected MPI size must be 1 or 2"], {})
    try:
        return _artifact_details(parent_record, expected_source_sha, expected_mpi_size)["result"]
    except Exception as exc:  # malformed evidence must never escape as a checker crash
        return _result([f"schema:checker boundary error: {exc}"], {})


def _check_pair(
    mpi1_parent_record: str | Path,
    mpi2_parent_record: str | Path,
    expected_source_sha: str,
) -> dict[str, Any]:
    """Check MPI1 and MPI2 artifacts, then compare their canonical R3 packets."""

    left = _artifact_details(mpi1_parent_record, expected_source_sha, 1)
    right = _artifact_details(mpi2_parent_record, expected_source_sha, 2)
    errors = [f"mpi1:{item}" for item in left["result"]["errors"]]
    errors.extend(f"mpi2:{item}" for item in right["result"]["errors"])
    pair_metrics: dict[str, Any] = {}
    if left["result"]["passed"] and right["result"]["passed"]:
        left_worker = left["worker"]
        right_worker = right["worker"]
        if not isinstance(left_worker, dict) or not isinstance(right_worker, dict):
            errors.append("schema:pair worker records are not objects")
        else:
            for key in ("source", "input", "target_mode"):
                if left_worker.get(key) != right_worker.get(key):
                    errors.append(f"mpi_identity:{key} differs")
            if left_worker.get("r3", {}).get("formula") != right_worker.get("r3", {}).get("formula"):
                errors.append("mpi_identity:r3 formula differs")
        left_packets = left["packets"]
        right_packets = right["packets"]
        if set(left_packets) != set(right_packets):
            errors.append("mpi_identity:r3 canonical key sets differ")
        else:
            numerator = math.fsum(
                abs(left_packets[key] - right_packets[key]) ** 2
                for key in left_packets
            )
            denominator = max(
                math.fsum(abs(value) ** 2 for value in right_packets.values()),
                1.0e-300,
            )
            relative = math.sqrt(numerator / denominator)
            pair_metrics = {"key_count": len(left_packets), "relative_l2": relative}
            if relative > 1.0e-10:
                errors.append(f"mpi_identity:r3 relative L2 {relative} exceeds 1e-10")
    metrics = {
        "mpi1": left["result"]["metrics"],
        "mpi2": right["result"]["metrics"],
        "r3_pair": pair_metrics,
    }
    result = _result(errors, metrics)
    if result["passed"]:
        result["classification"] = "SOURCE_AUTHORITY_MPI_PAIR_PASS"
    elif any(item.startswith("mpi_identity:") for item in errors):
        result["classification"] = "SOURCE_AUTHORITY_MPI_IDENTITY_FAIL"
    return result


def check_pair(
    mpi1_parent_record: str | Path,
    mpi2_parent_record: str | Path,
    expected_source_sha: str,
) -> dict[str, Any]:
    """Check a pair without allowing malformed evidence to escape the boundary."""

    try:
        return _check_pair(mpi1_parent_record, mpi2_parent_record, expected_source_sha)
    except Exception as exc:  # malformed evidence must never escape as a checker crash
        return _result([f"schema:checker boundary error: {exc}"], {})


def _write_output(path: Path, value: dict[str, Any]) -> None:
    if path.exists() or not path.parent.is_dir():
        raise FileExistsError(f"checker output must be a fresh file: {path}")
    encoded = (
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode("utf-8")
    with path.open("xb") as stream:
        stream.write(encoded)
        stream.flush()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mpi1-parent", required=True)
    parser.add_argument("--mpi2-parent")
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    if args.mpi2_parent:
        result = check_pair(args.mpi1_parent, args.mpi2_parent, args.expected_source_sha)
    else:
        result = check_artifact(args.mpi1_parent, args.expected_source_sha, 1)
    _write_output(Path(args.output), result)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
