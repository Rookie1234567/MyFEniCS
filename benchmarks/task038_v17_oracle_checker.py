"""Independent raw checker for the V17 Oracle A/B diagnostics.

Only JSON, NumPy arrays, hashes, and scalar process facts are inspected here;
the runner and every numerical solver stay outside this module.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np


BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"
SOURCE_SHA = "be67787d1237e8676b33f91f28c7b0ffcb3fe06a"
INPUT_SHA256 = "819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41"
PHYSICAL_MODEL_SHA256 = (
    "9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f"
)
MODE_MANIFEST_SHA256 = (
    "dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2"
)
CHECKPOINT_MANIFEST_SHA256 = (
    "7f7d6fd29e6a3d6130de439fa510a19c6830061f59090cfd9f6ee4c51d8eb139"
)
CHECKPOINT_SOLUTION_SHA256 = (
    "00f55e5256e673687942f79d98398d0fd2524d6d956c3b7ef5264615ab2c659b"
)
CHECKPOINT_SOURCE_SHA = "ee5920b9fa977a39fea7bc09cfbe155303acdb2d"
CHECKPOINT_INPUT_IDENTITY_SHA256 = (
    "754dbf810cc38b32804bced03b8d4b8f702d5943671724e7529f47cadefe8b1f"
)
CHECKPOINT_OPERATOR_IDENTITY_SHA256 = (
    "bbe5737b41b56c9dddb0c0ae3e0dd0384197dc22dd2faf41a2c57cc781f0a6f3"
)
CHECKPOINT_EXPLICIT_RESIDUAL = 0.4837947981092168
A_RESIDUAL_LIMIT = 1.0e-10
A_RHO3_LIMIT = 1.0e-6
A_RHO_REF_LIMIT = 0.70
B_STEPS = 500
B_INTERVAL = 20
B_DISK_FREE_BYTES = 10_000_000_000
B_HARD_BYTES = 2_000_000_000
B_START_ITERATION = 1_000
A_HARD_BYTES = 12_000_000_000
A3_SCHEMA = "task038.v17.oracle-a3.v2"
A_TRANSFER_CONSTRAINT_LIMIT = 1.0e-11
B_ORTHOGONALITY_LIMIT = 1.0e-8
B_EXPLICIT_ARNOLDI_LIMIT = 1.0e-8
A_MARKER_ORDER = (
    "paths_ready",
    "abi_ready",
    "A1_complete",
    "A2_complete",
    "A3_complete",
    "record_written",
    "release_complete",
)
A_BLOCKED_MARKER_ORDER = (
    "paths_ready",
    "abi_ready",
    "A1_complete",
    "A2_complete",
    "record_written",
    "release_complete",
)
A_NUMERIC_STOP_MARKER_ORDER = {
    "A1": ("paths_ready", "abi_ready"),
    "A2": ("paths_ready", "abi_ready", "A1_complete"),
}
CANONICAL_SHARD_SCHEMA = "task037.canonical-vector-shard.v1"
CANONICAL_MANIFEST_SCHEMA = "task037.canonical-vector-manifest.v1"
CANONICAL_KEY_ALGORITHM = "sha256(canonical-key-json-v1)"
B_MARKER_ORDER = (
    "paths_ready",
    "abi_ready",
    "reference_complete",
    "unrestarted_complete",
    "record_written",
    "release_complete",
)


def _reject_constant(value: str) -> Any:
    raise ValueError(f"non-finite JSON constant: {value}")


def _strict_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_json(path: Path) -> Any:
    return json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_strict_pairs,
        parse_constant=_reject_constant,
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_range(path: Path, offset: int, size: int) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        stream.seek(offset)
        remaining = size
        while remaining:
            block = stream.read(min(1 << 20, remaining))
            if not block:
                raise OSError("short basis column")
            digest.update(block)
            remaining -= len(block)
    return digest.hexdigest()


def _is_int(value: Any) -> bool:
    return type(value) is int


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(float(value))


def _error(errors: list[str], message: str) -> None:
    errors.append(message)


def _gate(gate_failures: list[str] | None, errors: list[str], message: str) -> None:
    if gate_failures is None:
        _error(errors, message)
    else:
        gate_failures.append(message)


def _source(record: Any, expected_source_sha: str, errors: list[str], label: str) -> None:
    if not isinstance(record, dict):
        _error(errors, f"infrastructure:{label} is not an object")
        return
    if record.get("commit_sha") != expected_source_sha:
        _error(errors, f"source:{label}.commit_sha mismatch")
    if record.get("branch") != BRANCH:
        _error(errors, f"source:{label}.branch mismatch")
    if record.get("upstream_sha") != expected_source_sha or record.get("upstream") != f"origin/{BRANCH}":
        _error(errors, f"source:{label}.upstream mismatch")
    if record.get("ahead") != 0 or record.get("behind") != 0 or record.get("tracked_worktree_clean") is not True:
        _error(errors, f"source:{label}.checkout is not clean 0/0")
    if record.get("qualified_activation") != "1":
        _error(errors, f"runtime:{label}.qualified activation mismatch")
    if record.get("input_sha256") != INPUT_SHA256:
        _error(errors, f"input:{label}.input identity mismatch")
    if record.get("physical_model_sha256") != PHYSICAL_MODEL_SHA256:
        _error(errors, f"provenance:{label}.physical model identity mismatch")
    if record.get("mode_manifest_sha256") != MODE_MANIFEST_SHA256:
        _error(errors, f"provenance:{label}.mode manifest identity mismatch")


def _check_source_bundle(worker: dict[str, Any], expected_source_sha: str, errors: list[str]) -> None:
    _source(worker.get("source"), expected_source_sha, errors, "worker.source")
    input_facts = worker.get("input")
    if isinstance(input_facts, dict):
        if input_facts.get("template_sha256") != INPUT_SHA256:
            _error(errors, "input:worker template SHA mismatch")
        if input_facts.get("physical_model_sha256") != PHYSICAL_MODEL_SHA256:
            _error(errors, "provenance:worker physical model identity mismatch")
        if input_facts.get("mode_manifest_sha256") != MODE_MANIFEST_SHA256:
            _error(errors, "provenance:worker mode manifest identity mismatch")
    else:
        _error(errors, "input:worker input facts missing")


def _check_process_result(
    result: Any,
    errors: list[str],
    label: str,
    *,
    allow_numeric_stop: bool = False,
) -> None:
    if not isinstance(result, dict):
        _error(errors, f"lifecycle:{label} result is not an object")
        return
    returncode = result.get("returncode")
    if allow_numeric_stop:
        if not _is_int(returncode) or returncode == 0:
            _error(errors, f"lifecycle:{label}.numeric stop returncode is invalid")
    elif returncode != 0:
        _error(errors, f"lifecycle:{label}.returncode is not zero")
    if result.get("stop_reason") is not None:
        _error(errors, f"lifecycle:{label}.stop_reason is not empty")
    if result.get("process_group_gone") is not True or result.get("lifecycle_failure") is not False:
        _error(errors, f"lifecycle:{label}.process group did not close")
    if result.get("signals") != []:
        _error(errors, f"lifecycle:{label}.signals is not empty")
    if result.get("max_swap_bytes") != 0:
        _error(errors, f"resource:{label}.swap is nonzero")
    if result.get("all_status_readable") is not True:
        _error(errors, f"lifecycle:{label}.status was unreadable")


def _effective_sample(sample: dict[str, Any]) -> bool:
    return (
        sample.get("all_status_readable") is True
        or (
            sample.get("all_status_readable") is False
            and sample.get("process_tree_exit_race_observed") is True
            and _is_int(sample.get("worker_exit_code_observed_after_sample"))
            and sample.get("worker_exit_code_observed_after_sample") == 0
            and sample.get("rss_bytes") is None
            and sample.get("swap_bytes") is None
        )
    )


def _read_process_timeline(root: Path, parent: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    relative = parent.get("paths", {}).get("process_samples")
    path = (root / str(relative)).resolve()
    if root.resolve() not in path.parents or not path.is_file():
        _error(errors, "lifecycle:parent process timeline is missing")
        return {"sample_count": 0, "peak_rss_bytes": 0, "max_swap_bytes": 0, "all_status_readable": False}
    count = 0
    peak = 0
    swap = 0
    readable = True
    try:
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                if not line.strip():
                    continue
                sample = _load_json_from_text(line)
                count += 1
                if not isinstance(sample, dict):
                    _error(errors, "lifecycle:process sample is not an object")
                    continue
                rss = sample.get("rss_bytes")
                swap_value = sample.get("swap_bytes")
                if rss is None or swap_value is None:
                    if not _effective_sample(sample):
                        _error(errors, f"lifecycle:process sample {count} has unreadable null resource")
                else:
                    if not _is_int(rss) or rss < 0 or not _is_int(swap_value) or swap_value < 0:
                        _error(errors, f"resource:process sample {count} has invalid RSS/swap")
                    else:
                        peak = max(peak, rss)
                        swap = max(swap, swap_value)
                readable = readable and _effective_sample(sample)
                descendant = sample.get("compiler_descendant_count")
                if not _is_int(descendant) or descendant < 0:
                    _error(errors, f"lifecycle:process sample {count} compiler count invalid")
    except (OSError, ValueError, TypeError) as exc:
        _error(errors, f"infrastructure:process timeline cannot be independently read: {exc}")
    expected = parent.get("process")
    if isinstance(expected, dict):
        if expected.get("sample_count") != count:
            _error(errors, "lifecycle:parent sample_count does not close")
        if expected.get("peak_rss_bytes") != peak:
            _error(errors, "resource:parent peak RSS does not close")
        if expected.get("max_swap_bytes") != swap:
            _error(errors, "resource:parent max swap does not close")
        if expected.get("all_status_readable") != readable:
            _error(errors, "lifecycle:parent readability does not close")
    else:
        _error(errors, "lifecycle:parent process summary missing")
    return {"sample_count": count, "peak_rss_bytes": peak, "max_swap_bytes": swap, "all_status_readable": readable}


def _load_json_from_text(text: str) -> Any:
    return json.loads(text, object_pairs_hook=_strict_pairs, parse_constant=_reject_constant)


def _canonical_key(value: Any) -> Any:
    if isinstance(value, dict):
        if set(value) != {"tuple"} or not isinstance(value["tuple"], list):
            raise ValueError("canonical key tuple encoding is invalid")
        return tuple(_canonical_key(item) for item in value["tuple"])
    if value is None or type(value) in {bool, int, str}:
        return value
    if type(value) is float and math.isfinite(value):
        return value
    raise ValueError("canonical key value is invalid")


def _canonical_key_bytes(key: tuple[Any, ...]) -> bytes:
    def encode(value: Any) -> Any:
        if isinstance(value, tuple):
            return {"tuple": [encode(item) for item in value]}
        if value is None or type(value) in {bool, int, str}:
            return value
        if type(value) is float and math.isfinite(value):
            return value
        raise ValueError("canonical key value is invalid")

    return json.dumps(
        encode(key), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _canonical_key_inventory_hash(keys: list[tuple[Any, ...]]) -> str:
    digest = hashlib.sha256()
    for key_bytes in sorted(_canonical_key_bytes(key) for key in keys):
        digest.update(key_bytes)
        digest.update(b"\n")
    return digest.hexdigest()


def _read_canonical(
    root: Path, descriptor: Any, errors: list[str], label: str
) -> dict[str, Any] | None:
    if not isinstance(descriptor, dict):
        _error(errors, f"schema:{label} canonical descriptor missing")
        return None
    relative = descriptor.get("manifest_relative_path")
    if not isinstance(relative, str):
        _error(errors, f"schema:{label} canonical manifest path missing")
        return None
    manifest_path = (root / relative).resolve()
    if root.resolve() not in manifest_path.parents or not manifest_path.is_file():
        _error(errors, f"provenance:{label} canonical manifest missing")
        return None
    try:
        if _sha256(manifest_path) != descriptor.get("manifest_sha256"):
            _error(errors, f"provenance:{label} canonical manifest SHA mismatch")
        manifest = _load_json(manifest_path)
    except (OSError, ValueError, TypeError) as exc:
        _error(errors, f"infrastructure:{label} canonical manifest unreadable: {exc}")
        return None
    if manifest.get("schema_version") != CANONICAL_MANIFEST_SCHEMA:
        _error(errors, f"schema:{label} canonical manifest schema mismatch")
    role = descriptor.get("role")
    if role not in {"full_fe", "full_fe_dual"} or manifest.get("role") != role:
        _error(errors, f"schema:{label} canonical role mismatch")
    if descriptor.get("dtype") not in {None, "complex128"} or manifest.get("dtype") != "complex128":
        _error(errors, f"schema:{label} canonical dtype mismatch")
    if manifest.get("key_digest_algorithm") != CANONICAL_KEY_ALGORITHM:
        _error(errors, f"schema:{label} canonical key algorithm mismatch")
    audit = manifest.get("extractor_audit")
    if not isinstance(audit, dict) or audit.get("numeric_allgather") is not False:
        _error(errors, f"provenance:{label} canonical numeric allgather is not false")
    shard_rows = manifest.get("per_rank_shards")
    mpi_size = manifest.get("mpi_size")
    if not _is_int(mpi_size) or mpi_size < 1 or not isinstance(shard_rows, list):
        _error(errors, f"schema:{label} canonical shard metadata is invalid")
        return None
    if descriptor.get("mpi_size") not in {None, mpi_size}:
        _error(errors, f"schema:{label} canonical MPI size mismatch")
    if len(shard_rows) != mpi_size:
        _error(errors, f"schema:{label} canonical shard count mismatch")
    keys: dict[tuple[Any, ...], complex] = {}
    total = 0
    duplicate_total = 0
    rank_hashes: list[dict[str, Any]] = []
    for shard in shard_rows:
        if not isinstance(shard, dict):
            _error(errors, f"schema:{label} shard metadata is not an object")
            continue
        rank = shard.get("rank")
        filename = shard.get("filename")
        if not _is_int(rank) or rank < 0 or rank >= mpi_size or not isinstance(filename, str):
            _error(errors, f"schema:{label} shard rank/path is invalid")
            continue
        shard_path = (manifest_path.parent / filename).resolve()
        if manifest_path.parent.resolve() not in shard_path.parents or not shard_path.is_file():
            _error(errors, f"provenance:{label}.rank{rank} shard missing")
            continue
        try:
            digest = hashlib.sha256()
            local_keys: list[tuple[Any, ...]] = []
            local_duplicate = 0
            finite = True
            with shard_path.open("rb") as stream:
                for raw_line in stream:
                    digest.update(raw_line)
                    item = _load_json_from_text(raw_line.decode("utf-8"))
                    if not isinstance(item, dict) or item.get("schema_version") != CANONICAL_SHARD_SCHEMA:
                        raise ValueError("canonical shard schema is unsupported")
                    key = _canonical_key(item.get("key"))
                    if not isinstance(key, tuple):
                        raise ValueError("canonical packet key is not a tuple")
                    key_bytes = _canonical_key_bytes(key)
                    if item.get("key_sha256") != hashlib.sha256(key_bytes).hexdigest():
                        raise ValueError("canonical key digest does not match key")
                    value = item.get("value")
                    if not isinstance(value, list) or len(value) != 2 or not all(
                        _finite(component) for component in value
                    ):
                        raise ValueError("canonical coefficient is not finite complex128")
                    coefficient = complex(float(value[0]), float(value[1]))
                    if key in keys:
                        local_duplicate += 1
                    else:
                        keys[key] = coefficient
                    local_keys.append(key)
                    finite = finite and math.isfinite(coefficient.real) and math.isfinite(coefficient.imag)
            actual_sha = digest.hexdigest()
            if actual_sha != shard.get("file_sha256"):
                _error(errors, f"provenance:{label}.rank{rank} shard SHA mismatch")
            if shard.get("packet_count") != len(local_keys):
                _error(errors, f"schema:{label}.rank{rank} packet count mismatch")
            if shard.get("key_inventory_sha256") != _canonical_key_inventory_hash(local_keys):
                _error(errors, f"provenance:{label}.rank{rank} key inventory mismatch")
            if shard.get("dtype") != "complex128" or shard.get("schema_version") != CANONICAL_SHARD_SCHEMA:
                _error(errors, f"schema:{label}.rank{rank} shard descriptor mismatch")
            if shard.get("local_duplicate_count") != local_duplicate or local_duplicate:
                _error(errors, f"schema:{label}.rank{rank} duplicate packet")
            if shard.get("packet_finite") is not True or not finite:
                _error(errors, f"numerical:{label}.rank{rank} packet is not finite")
            total += len(local_keys)
            duplicate_total += local_duplicate
            rank_hashes.append({"rank": rank, "key_inventory_sha256": _canonical_key_inventory_hash(local_keys)})
        except (OSError, UnicodeError, ValueError, TypeError) as exc:
            _error(errors, f"infrastructure:{label}.rank{rank} shard unreadable: {exc}")
    ranks = [item["rank"] for item in rank_hashes]
    if sorted(ranks) != list(range(mpi_size)):
        _error(errors, f"schema:{label} canonical ranks are not exact")
    expected_manifest_hash = hashlib.sha256(
        json.dumps(rank_hashes, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if manifest.get("key_inventory_sha256") != expected_manifest_hash:
        _error(errors, f"provenance:{label} global key inventory mismatch")
    if manifest.get("global_summed_packet_count") != total or manifest.get("summed_local_duplicate_count") != duplicate_total:
        _error(errors, f"schema:{label} global packet counts do not close")
    if descriptor.get("packet_count") != total or descriptor.get("key_inventory_sha256") != expected_manifest_hash:
        _error(errors, f"schema:{label} descriptor counts do not close")
    return {
        "role": role,
        "keys": keys,
        "key_inventory_sha256": expected_manifest_hash,
        "packet_count": total,
        "manifest": manifest,
    }


def _canonical_pair(
    root: Path,
    left: Any,
    right: Any,
    errors: list[str],
    label: str,
    *,
    values: bool = False,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    left_data = _read_canonical(root, left, errors, f"{label}.left")
    right_data = _read_canonical(root, right, errors, f"{label}.right")
    if left_data is not None and right_data is not None:
        if left_data["role"] != right_data["role"]:
            _error(errors, f"schema:{label} canonical roles differ")
        if left_data["key_inventory_sha256"] != right_data["key_inventory_sha256"] or set(left_data["keys"]) != set(right_data["keys"]):
            _error(errors, f"provenance:{label} canonical key inventory differs")
        if values and left_data["keys"] != right_data["keys"]:
            _error(errors, f"numerical:{label} canonical values differ")
    return left_data, right_data


def _cache_snapshot(path: Path, errors: list[str]) -> dict[str, Any]:
    artifacts = []
    if not path.is_dir():
        _error(errors, "cache:jit_cache is missing")
        return {"artifact_count": 0, "manifest_sha256": None}
    for base, _dirs, files in __import__("os").walk(path, followlinks=False):
        for name in files:
            file_path = Path(base) / name
            if file_path.suffix not in {".c", ".o", ".so"} or not file_path.is_file():
                continue
            artifacts.append({"relative_path": file_path.relative_to(path).as_posix(), "bytes": file_path.stat().st_size, "sha256": _sha256(file_path)})
    artifacts.sort(key=lambda item: item["relative_path"])
    manifest = {"cache_dir": str(path), "artifacts": artifacts, "artifact_count": len(artifacts)}
    encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return {"artifact_count": len(artifacts), "manifest_sha256": hashlib.sha256(encoded).hexdigest()}


def _check_markers(
    root: Path,
    parent: dict[str, Any],
    phase: str,
    errors: list[str],
    *,
    blocked: bool = False,
    numeric_stop_stage: str | None = None,
) -> None:
    order = (
        A_BLOCKED_MARKER_ORDER
        if phase == "oracle-a" and blocked
        else A_NUMERIC_STOP_MARKER_ORDER[numeric_stop_stage]
        if phase == "oracle-a" and numeric_stop_stage in A_NUMERIC_STOP_MARKER_ORDER
        else A_MARKER_ORDER
        if phase == "oracle-a"
        else B_MARKER_ORDER
    )
    full_order = A_MARKER_ORDER if phase == "oracle-a" else order
    marker_info = parent.get("markers")
    if not isinstance(marker_info, dict):
        _error(errors, "lifecycle:marker manifest fact missing")
        return
    path = (root / str(marker_info.get("relative_path"))).resolve()
    if root.resolve() not in path.parents or not path.is_file():
        _error(errors, "lifecycle:marker manifest path invalid")
        return
    if _sha256(path) != marker_info.get("sha256"):
        _error(errors, "provenance:marker manifest SHA mismatch")
    try:
        rows = _load_json(path)
        names = [row.get("name") for row in rows] if isinstance(rows, list) else []
        if names != list(order) or marker_info.get("names") != list(order):
            _error(errors, "lifecycle:marker order is incomplete")
        marker_dir = root / "markers"
        expected_files = set()
        for name in names:
            marker_path = marker_dir / f"{full_order.index(name):03d}_{name}.json"
            expected_files.add(marker_path.name)
            if not marker_path.is_file():
                _error(errors, f"lifecycle:marker file missing: {name}")
            else:
                try:
                    marker = _load_json(marker_path)
                    if not isinstance(marker, dict) or marker.get("name") != name:
                        _error(errors, f"schema:marker payload mismatch: {name}")
                except (OSError, ValueError, TypeError) as exc:
                    _error(errors, f"infrastructure:marker unreadable: {name}: {exc}")
        if marker_dir.is_dir():
            actual_files = {path.name for path in marker_dir.glob("*.json")}
            if actual_files != expected_files:
                _error(errors, "lifecycle:marker set contains unexpected files")
    except (ValueError, OSError, TypeError) as exc:
        _error(errors, f"infrastructure:marker manifest cannot be read: {exc}")


def _check_common(parent: dict[str, Any], parent_path: Path, expected_source_sha: str, errors: list[str]) -> dict[str, Any]:
    root = parent_path.parent
    if parent.get("schema") != "task038.v17.oracle.parent.v1":
        _error(errors, "schema:parent schema mismatch")
    _source(parent.get("source"), expected_source_sha, errors, "parent.source")
    phase = parent.get("phase")
    if phase not in {"oracle-a", "oracle-b"}:
        _error(errors, "schema:parent phase is invalid")
    contract = parent.get("resource_contract")
    if not isinstance(contract, dict):
        _error(errors, "resource:parent resource contract missing")
        contract = {}
    expected_hard = A_HARD_BYTES if phase == "oracle-a" else B_HARD_BYTES
    expected_warning = 10_000_000_000 if phase == "oracle-a" else 1_800_000_000
    if (
        contract.get("warning_bytes") != expected_warning
        or contract.get("rss_watchdog_bytes") != expected_hard
        or contract.get("hard_gate_bytes") != expected_hard
        or contract.get("swap_gate_bytes") != 0
    ):
        _error(errors, "resource:parent threshold contract mismatch")
    process = _read_process_timeline(root, parent, errors)
    if process["max_swap_bytes"] != 0:
        _error(errors, "resource:parent process swap Gate failed")
    if process["peak_rss_bytes"] >= expected_hard:
        _error(errors, "resource:parent process RSS Gate failed")
    blocked = phase == "oracle-a" and parent.get("a2_resource_blocked") is True
    numeric_stop_stage = parent.get("numeric_stop_stage")
    if phase != "oracle-a" and numeric_stop_stage is not None:
        _error(errors, "schema:numeric stop is only valid for Oracle A")
    if numeric_stop_stage not in {None, "A1", "A2"}:
        _error(errors, "schema:Oracle A numeric stop stage is invalid")
    if blocked and numeric_stop_stage is not None:
        _error(errors, "schema:resource block and numeric stop are exclusive")
    children = parent.get("children")
    if phase == "oracle-a":
        if children != []:
            _error(errors, "schema:Oracle A must not have JIT children")
        if parent.get("jit_groups") != []:
            _error(errors, "schema:Oracle A JIT group list is not empty")
    elif not isinstance(children, list) or len(children) != len(JIT_GROUPS):
        _error(errors, "schema:seven cold JIT children are not present")
    else:
        if parent.get("jit_groups") != list(JIT_GROUPS):
            _error(errors, "schema:Oracle B JIT group list mismatch")
        for index, child in enumerate(children):
            _check_process_result(child, errors, f"child[{index}]")
            if child.get("rss_watchdog_bytes") != expected_hard:
                _error(errors, f"resource:child[{index}] watchdog provenance mismatch")
            if child.get("group") != JIT_GROUPS[index]:
                _error(errors, f"lifecycle:child[{index}] stage order mismatch")
            relative = child.get("record")
            child_path = (root / str(relative)).resolve()
            if root.resolve() not in child_path.parents or not child_path.is_file():
                _error(errors, f"provenance:child[{index}] record missing")
            elif child.get("record_sha256") != _sha256(child_path):
                _error(errors, f"provenance:child[{index}] record SHA mismatch")
    expected_stages = (
        ("A1", "A2") if blocked else ("A1",) if numeric_stop_stage == "A1"
        else ("A1", "A2") if numeric_stop_stage == "A2" else ("A1", "A2", "A3")
        if phase == "oracle-a"
        else ("B",)
    )
    stage_results = parent.get("stages")
    stage_names = (
        [item.get("stage") if isinstance(item, dict) else None for item in stage_results]
        if isinstance(stage_results, list)
        else []
    )
    if stage_names != list(expected_stages):
        _error(errors, "lifecycle:oracle stage order mismatch")
        stage_results = []
    numeric_stop_error = (
        phase == "oracle-a"
        and numeric_stop_stage in {"A1", "A2"}
        and parent.get("error") == f"{numeric_stop_stage} numerical gate stop"
    )
    if parent.get("error") is not None and not numeric_stop_error:
        _error(errors, "lifecycle:parent error is not empty")
    if phase == "oracle-a":
        expected_classification = (
            "ORACLE_A_NUMERICAL_GATE_STOP"
            if numeric_stop_stage is not None
            else "A_ORACLE_BLOCKED_BY_RESOURCE_PREFLIGHT"
            if blocked
            else "RAW_COMPLETE_PENDING_CHECKER"
        )
        if parent.get("classification") != expected_classification:
            _error(errors, "schema:Oracle A parent classification mismatch")
    raw_dir = root / "raw"
    stage_records: dict[str, Any] = {}
    for item in stage_results:
        if not isinstance(item, dict):
            _error(errors, "schema:stage descriptor is not an object")
            continue
        stage = item.get("stage")
        _check_process_result(
            item,
            errors,
            f"stage:{stage}",
            allow_numeric_stop=(numeric_stop_stage == stage),
        )
        if item.get("rss_watchdog_bytes") != expected_hard:
            _error(errors, f"resource:stage:{stage} watchdog provenance mismatch")
        relative = item.get("record")
        if not isinstance(relative, str):
            _error(errors, f"schema:stage:{stage} record path is missing")
            continue
        stage_path = (root / relative).resolve()
        if root.resolve() not in stage_path.parents or not stage_path.is_file():
            _error(errors, f"provenance:stage record missing: {relative}")
            continue
        if _sha256(stage_path) != item.get("sha256"):
            _error(errors, f"provenance:stage record SHA mismatch: {relative}")
        try:
            stage_records[str(stage)] = _load_json(stage_path)
        except (OSError, ValueError, TypeError) as exc:
            _error(errors, f"infrastructure:stage record unreadable: {relative}: {exc}")
    cache = parent.get("cache")
    if not isinstance(cache, dict):
        _error(errors, "cache:parent cache facts missing")
    elif phase == "oracle-a":
        initial = cache.get("initial")
        snapshots = cache.get("stage_snapshots")
        empty_manifest = {
            "cache_dir": str(root / "jit_cache"),
            "artifacts": [],
            "artifact_count": 0,
        }
        empty_snapshot = {
            "artifact_count": 0,
            "manifest_sha256": hashlib.sha256(
                json.dumps(
                    empty_manifest, sort_keys=True, separators=(",", ":")
                ).encode()
            ).hexdigest(),
        }
        if initial != empty_snapshot:
            _error(errors, "cache:initial cache is not empty")
        if not isinstance(snapshots, list) or [
            item.get("stage") if isinstance(item, dict) else None for item in snapshots
        ] != list(expected_stages):
            _error(errors, "cache:Oracle A stage snapshot order mismatch")
        actual = _cache_snapshot(root / "jit_cache", errors)
        if not isinstance(snapshots, list) or not snapshots or not isinstance(snapshots[-1], dict) or snapshots[-1].get("snapshot") != actual:
            _error(errors, "cache:Oracle A final snapshot does not match current cache")
    elif cache.get("initial", {}).get("artifact_count") != 0:
        _error(errors, "cache:initial cache is not empty")
    elif cache.get("before_worker") != cache.get("after_worker"):
        _error(errors, "cache:worker changed the cold cache")
    else:
        actual = _cache_snapshot(root / "jit_cache", errors)
        if cache.get("after_worker") != actual:
            _error(errors, "cache:after_worker does not match current cache")
    _check_markers(
        root,
        parent,
        phase,
        errors,
        blocked=blocked,
        numeric_stop_stage=numeric_stop_stage,
    )
    worker = stage_records.get(str(expected_stages[0])) if expected_stages else None
    return {
        "root": root,
        "phase": phase,
        "blocked": blocked,
        "numeric_stop_stage": numeric_stop_stage,
        "contract": contract,
        "stage_results": stage_results,
        "stage_records": stage_records,
        "worker": worker,
        "raw_dir": raw_dir,
        "process": process,
    }


JIT_GROUPS = (
    "positive-p6",
    "positive-p3",
    "positive-p1",
    "dtn-surface",
    "incident-rhs",
    "physical-volume-curl",
    "physical-volume-mass",
)


def _check_vector(raw_dir: Path, descriptor: Any, errors: list[str], label: str) -> np.ndarray | None:
    if not isinstance(descriptor, dict):
        _error(errors, f"schema:{label} descriptor missing")
        return None
    relative = descriptor.get("relative_path")
    if not isinstance(relative, str):
        _error(errors, f"schema:{label} path is missing")
        return None
    path = (raw_dir.parent / relative).resolve()
    if raw_dir.parent.resolve() not in path.parents or not path.is_file():
        _error(errors, f"provenance:{label} file missing")
        return None
    if descriptor.get("bytes") != path.stat().st_size or descriptor.get("sha256") != _sha256(path):
        _error(errors, f"provenance:{label} file descriptor mismatch")
    try:
        values = np.asarray(np.load(path, allow_pickle=False))
    except (OSError, ValueError) as exc:
        _error(errors, f"infrastructure:{label} array cannot be read: {exc}")
        return None
    if descriptor.get("dtype") != "complex128" or values.dtype != np.dtype(np.complex128) or values.ndim != 1 or not np.all(np.isfinite(values)):
        _error(errors, f"numerical:{label} is not finite complex128")
        return None
    if descriptor.get("finite") is not True:
        _error(errors, f"numerical:{label} finite fact is not true")
    if "array_sha256" in descriptor:
        array_sha256 = hashlib.sha256(
            memoryview(np.ascontiguousarray(values)).cast("B")
        ).hexdigest()
        if descriptor.get("array_sha256") != array_sha256:
            _error(errors, f"provenance:{label} array SHA does not close")
    if list(values.shape) != descriptor.get("shape"):
        _error(errors, f"schema:{label} shape mismatch")
    stored_norm = descriptor.get("norm")
    if not _finite(stored_norm) or not math.isclose(float(stored_norm), float(np.linalg.norm(values)), rel_tol=1e-12, abs_tol=1e-12):
        _error(errors, f"numerical:{label} norm does not close")
    return values


def _check_owned_facts(
    facts: Any,
    errors: list[str],
    label: str,
    *,
    allow_nonzero: bool = False,
) -> None:
    if not isinstance(facts, dict):
        _error(errors, f"schema:{label} vector facts are missing")
        return
    if facts.get("finite") is not True or not _finite(facts.get("norm")):
        _error(errors, f"numerical:{label} finite facts are invalid")
    if not _finite(facts.get("owned_slave_max")) or float(facts["owned_slave_max"]) < 0.0:
        _error(errors, f"schema:{label} owned slave maximum is invalid")
    elif not allow_nonzero and float(facts["owned_slave_max"]) != 0.0:
        _error(errors, f"numerical:{label} owned slave maximum is not zero")
    if not _is_int(facts.get("owned_slave_count")) or facts["owned_slave_count"] < 0:
        _error(errors, f"schema:{label} owned slave count is invalid")
    elif not allow_nonzero and facts["owned_slave_count"] != 0:
        _error(errors, f"numerical:{label} owned slave count is not zero")


def _check_canonical_vector(
    root: Path, descriptor: Any, errors: list[str], label: str
) -> dict[str, Any] | None:
    value = _read_canonical(root, descriptor, errors, label)
    if value is not None and value["packet_count"] <= 0:
        _error(errors, f"schema:{label} canonical packet count is not positive")
    return value


def _check_input_unchanged(facts: Any, errors: list[str], label: str) -> None:
    if not isinstance(facts, dict) or facts.get("unchanged") is not True:
        _error(errors, f"input:{label} unchanged fact is not true")
        return
    for before, after in (
        ("checkpoint_solution_before_sha256", "checkpoint_solution_after_sha256"),
        ("rhs_before_sha256", "rhs_after_sha256"),
    ):
        if before in facts or after in facts:
            if not isinstance(facts.get(before), str) or facts.get(before) != facts.get(after):
                _error(errors, f"input:{label} {before} does not close")


def _check_architecture(architecture: Any, errors: list[str], label: str) -> None:
    if not isinstance(architecture, dict):
        _error(errors, f"architecture:{label} audit missing")
        return
    for key in ("global_physical_aij", "global_schur", "dense_dtn", "factor", "numeric_allgather"):
        if architecture.get(key) is not False:
            _error(errors, f"architecture:{label}.{key} is not false")
    if architecture.get("phase_once") is not True:
        _error(errors, f"architecture:{label}.phase_once is not true")


def _check_transfer_audit(architecture: Any, errors: list[str], label: str) -> None:
    if not isinstance(architecture, dict):
        return
    audit = architecture.get("p63_owner_transfer")
    if not isinstance(audit, dict):
        _error(errors, f"architecture:{label}.p63 owner-transfer audit missing")
        return
    for key in ("global_transfer_matrix", "numeric_allgather", "static_condensation"):
        if audit.get(key) is not False:
            _error(errors, f"architecture:{label}.p63.{key} is not false")
    if audit.get("owner_local") is not True or audit.get("coarse_dual_reduction") != "C^H_once":
        _error(errors, f"architecture:{label}.p63 owner-local audit mismatch")


def _check_a(context: dict[str, Any], expected_source_sha: str, errors: list[str]) -> dict[str, Any]:
    records = context.get("stage_records", {})
    blocked = context.get("blocked") is True
    numeric_stop_stage = context.get("numeric_stop_stage")
    expected_stages = (
        ("A1", "A2")
        if blocked
        else ("A1",)
        if numeric_stop_stage == "A1"
        else ("A1", "A2")
        if numeric_stop_stage == "A2"
        else ("A1", "A2", "A3")
    )
    if not all(isinstance(records.get(stage), dict) for stage in expected_stages):
        _error(errors, "schema:Oracle A raw stage record is missing")
        return {
            "resource_blocked": blocked,
            "numeric_stop_stage": numeric_stop_stage,
            "gate_failures": [],
        }
    if (
        not blocked
        and numeric_stop_stage is None
        and (context["raw_dir"] / "A3_record.json").is_file() is False
    ):
        _error(errors, "schema:A3 raw record missing")
    a1 = records["A1"]
    a2 = records.get("A2")
    a3 = records.get("A3")
    _check_source_bundle(a1, expected_source_sha, errors)
    gate_failures: list[str] = []
    for label, record in (("A1", a1), ("A2", a2), ("A3", a3)):
        if not isinstance(record, dict):
            continue
        _source(record.get("source"), expected_source_sha, errors, f"{label}.source")
        input_facts = record.get("input")
        if not isinstance(input_facts, dict):
            _error(errors, f"input:{label} input facts missing")
        else:
            if input_facts.get("template_sha256") != INPUT_SHA256:
                _error(errors, f"input:{label} input identity mismatch")
            if input_facts.get("physical_model_sha256") != PHYSICAL_MODEL_SHA256:
                _error(errors, f"provenance:{label} physical model identity mismatch")
            if input_facts.get("mode_manifest_sha256") != MODE_MANIFEST_SHA256:
                _error(errors, f"provenance:{label} mode manifest identity mismatch")
        if label in {"A1", "A3"}:
            _check_architecture(record.get("architecture"), errors, label)
            _check_transfer_audit(record.get("architecture"), errors, label)
    checkpoint = a1.get("checkpoint")
    checkpoint_expected = {
        "iteration": 1000,
        "input_identity_sha256": CHECKPOINT_INPUT_IDENTITY_SHA256,
        "operator_identity_sha256": CHECKPOINT_OPERATOR_IDENTITY_SHA256,
        "physical_model_sha256": PHYSICAL_MODEL_SHA256,
        "source_sha": CHECKPOINT_SOURCE_SHA,
        "mpi_size": 1,
        "manifest_sha256": CHECKPOINT_MANIFEST_SHA256,
        "solution_sha256": CHECKPOINT_SOLUTION_SHA256,
    }
    if not isinstance(checkpoint, dict):
        _error(errors, "provenance:A1 checkpoint facts missing")
    else:
        for key, expected in checkpoint_expected.items():
            if checkpoint.get(key) != expected:
                _error(errors, f"provenance:A1 checkpoint {key} mismatch")
    reproduction = a1.get("checkpoint_reproduction")
    if not isinstance(reproduction, dict):
        _error(errors, "schema:A1 checkpoint reproduction facts missing")
    else:
        actual = reproduction.get("actual")
        expected = reproduction.get("expected")
        absolute = reproduction.get("absolute_difference")
        relative = reproduction.get("relative_difference")
        relative_limit = reproduction.get("relative_limit")
        if expected != CHECKPOINT_EXPLICIT_RESIDUAL:
            _error(errors, "numerical:A1 checkpoint expected is not frozen")
        if type(relative_limit) is not float or relative_limit != 1.0e-8:
            _error(errors, "numerical:A1 checkpoint relative limit is not frozen")
        if not all(_finite(item) for item in (actual, expected, absolute, relative)):
            _error(errors, "numerical:A1 checkpoint reproduction is not finite")
        else:
            recomputed_absolute = abs(float(actual) - float(expected))
            recomputed_relative = recomputed_absolute / max(abs(float(expected)), np.finfo(float).tiny)
            if not math.isclose(float(absolute), recomputed_absolute, rel_tol=1e-12, abs_tol=1e-12) or not math.isclose(float(relative), recomputed_relative, rel_tol=1e-12, abs_tol=1e-12):
                _error(errors, "numerical:A1 checkpoint reproduction does not close")
            if (
                _finite(relative_limit)
                and float(relative) > float(relative_limit)
            ):
                gate_failures.append("checkpoint_reproduction")
    _check_input_unchanged(a1.get("input_unchanged"), errors, "A1")
    a1_vectors = a1.get("vectors")
    if not isinstance(a1_vectors, dict):
        _error(errors, "schema:A1 vector facts missing")
        return {
            "resource_blocked": blocked,
            "numeric_stop_stage": numeric_stop_stage,
            "gate_failures": gate_failures,
        }
    vector_values: dict[str, np.ndarray | None] = {}
    canonical: dict[str, dict[str, Any] | None] = {}
    for label, descriptor in (("A1.r6", a1_vectors.get("r6")), ("A1.r3", a1_vectors.get("r3"))):
        _check_owned_facts(descriptor, errors, label)
        vector_values[label] = _check_vector(context["raw_dir"], descriptor, errors, label)
        canonical[label] = _check_canonical_vector(
            context["root"], descriptor.get("canonical") if isinstance(descriptor, dict) else None, errors, f"{label}.canonical"
        )
    if a1.get("operation_counts") != {"p6_action": 1, "p63_adjoint": 1, "p63_primal": 0}:
        _error(errors, "lifecycle:A1 operation counts mismatch")
    _check_owned_facts(a1.get("rhs"), errors, "A1.rhs")
    if numeric_stop_stage == "A1":
        declared = a1.get("gate_failures")
        if (
            a1.get("stage_outcome") != "numerical_gate_failed"
            or not isinstance(declared, list)
            or not declared
            or any(item != "checkpoint_reproduction" for item in declared)
            or "checkpoint_reproduction" not in gate_failures
        ):
            _error(errors, "numerical:A1 stop does not match checkpoint Gate")
        return {
            "resource_blocked": False,
            "numeric_stop_stage": "A1",
            "gate_failures": gate_failures,
            "rho_ref": math.inf,
            "rho3": math.inf,
            "thresholds": {
                "rho_ref": A_RHO_REF_LIMIT,
                "rho3": A_RHO3_LIMIT,
                "p3_residual": A_RESIDUAL_LIMIT,
            },
        }
    if blocked:
        direct = a2.get("direct_solve")
        preflight = direct.get("resource_preflight_facts") if isinstance(direct, dict) else None
        predicted = a2.get("predicted_peak_bytes") if isinstance(a2, dict) else None
        if (
            not isinstance(direct, dict)
            or direct.get("resource_preflight") != "blocked"
            or direct.get("analysis_only") is not True
            or direct.get("numeric_factor_called") is not False
            or direct.get("solve_called") is not False
            or direct.get("symbolic_calls") != 1
            or not isinstance(direct.get("raw_info"), dict)
            or not isinstance(direct.get("raw_info", {}).get("infog"), dict)
            or not _is_int(predicted)
            or predicted < A_HARD_BYTES
            or not isinstance(preflight, dict)
            or preflight.get("predicted_peak_bytes") != predicted
            or preflight.get("hard_limit_bytes") != A_HARD_BYTES
            or preflight.get("formula")
            != "post_analysis_process_tree_rss_bytes + max(INFOG(16), 0) * 1000000"
            or not _is_int(preflight.get("post_analysis_process_tree_rss_bytes"))
            or preflight.get("post_analysis_process_tree_rss_bytes") < 0
            or not _is_int(preflight.get("infog16"))
            or predicted
            != preflight.get("post_analysis_process_tree_rss_bytes")
            + max(preflight.get("infog16"), 0) * 1_000_000
        ):
            _error(errors, "resource:A2 blocked lifecycle is not closed")
        return {
            "resource_blocked": True,
            "numeric_stop_stage": None,
            "gate_failures": gate_failures,
            "thresholds": {"rho_ref": A_RHO_REF_LIMIT, "rho3": A_RHO3_LIMIT},
        }
    architecture = a2.get("architecture")
    if not isinstance(architecture, dict) or architecture.get("global_physical_aij") is not True or architecture.get("production_global_aij") is not False or architecture.get("numeric_allgather") is not False or architecture.get("factor_destroyed_before_a3") is not True:
        _error(errors, "architecture:A2 diagnostic lifecycle mismatch")
    direct = a2.get("direct_solve")
    if not isinstance(direct, dict) or direct.get("resource_preflight") != "passed" or direct.get("analysis_only") is not False or direct.get("numeric_factor_called") is not True or direct.get("solve_called") is not True or direct.get("symbolic_calls") != 1 or direct.get("numeric_calls") != 1 or direct.get("solve_calls") != 1:
        _error(errors, "resource:Oracle A MUMPS analysis/numeric lifecycle is not closed")
    rhs_facts = a2.get("rhs")
    rhs_unchanged = (
        isinstance(rhs_facts, dict) and rhs_facts.get("unchanged") is True
    )
    if not isinstance(rhs_facts, dict) or (
        not rhs_unchanged and numeric_stop_stage != "A2"
    ):
        _error(errors, "input:A2 rhs unchanged fact is not true")
    else:
        before = rhs_facts.get("before")
        after = rhs_facts.get("after")
        _check_owned_facts(
            before, errors, "A2.rhs.before", allow_nonzero=numeric_stop_stage == "A2"
        )
        _check_owned_facts(
            after, errors, "A2.rhs.after", allow_nonzero=numeric_stop_stage == "A2"
        )
        if not isinstance(before, dict) or not isinstance(after, dict) or before.get("array_sha256") != after.get("array_sha256"):
            if numeric_stop_stage != "A2":
                _error(errors, "input:A2 rhs before/after hash mismatch")
    a2_vectors = a2.get("vectors")
    if not isinstance(a2_vectors, dict):
        _error(errors, "schema:A2 vector facts missing")
        return {
            "resource_blocked": False,
            "numeric_stop_stage": numeric_stop_stage,
            "gate_failures": gate_failures,
        }
    for label, descriptor in (("A2.rhs", a2_vectors.get("rhs")), ("A2.action", a2_vectors.get("action")), ("A2.residual", a2_vectors.get("residual")), ("A2.e3", a2_vectors.get("e3"))):
        _check_owned_facts(
            descriptor,
            errors,
            label,
            allow_nonzero=numeric_stop_stage == "A2",
        )
        vector_values[label] = _check_vector(context["raw_dir"], descriptor, errors, label)
    canonical["A2.e3"] = _check_canonical_vector(
        context["root"], a2_vectors.get("e3", {}).get("canonical") if isinstance(a2_vectors.get("e3"), dict) else None, errors, "A2.e3.canonical"
    )
    rhs = vector_values["A2.rhs"]
    action = vector_values["A2.action"]
    residual = vector_values["A2.residual"]
    if rhs is not None and action is not None and residual is not None:
        expected_residual = rhs - action
        residual_difference = residual - expected_residual
        residual_relative = float(np.linalg.norm(residual_difference)) / max(
            float(np.linalg.norm(residual)),
            float(np.linalg.norm(expected_residual)),
            np.finfo(float).tiny,
        )
        if residual_relative > 1.0e-12:
            _error(errors, "numerical:A2 residual rhs-action does not close")
        ratio = float(np.linalg.norm(residual)) / max(float(np.linalg.norm(rhs)), np.finfo(float).tiny)
        if not _finite(a2.get("explicit_true_residual")) or not math.isclose(float(a2["explicit_true_residual"]), ratio, rel_tol=1e-12, abs_tol=1e-12):
            _error(errors, "numerical:A2 explicit residual does not close")
        if ratio > A_RESIDUAL_LIMIT:
            gate_failures.append("p3_explicit_residual")
    if a2.get("finite") is not True and numeric_stop_stage != "A2":
        _error(errors, "numerical:A2 finite fact is not true")
    if numeric_stop_stage == "A2":
        declared = a2.get("gate_failures")
        allowed = {"p3_explicit_residual", "finite", "input", "slave"}
        actual_failures = set(gate_failures)
        if a2.get("finite") is not True:
            actual_failures.add("finite")
        if not rhs_unchanged:
            actual_failures.add("input")
        slave_failed = any(
            isinstance(descriptor, dict)
            and (
                float(descriptor.get("owned_slave_max", 0.0)) != 0.0
                or descriptor.get("owned_slave_count") != 0
            )
            for descriptor in a2_vectors.values()
        )
        if slave_failed:
            actual_failures.add("slave")
        if (
            not isinstance(declared, list)
            or not declared
            or len(declared) != len(set(declared))
            or not set(declared).issubset(allowed)
            or set(declared) != actual_failures
        ):
            _error(errors, "numerical:A2 stop does not match direct Gate facts")
        return {
            "resource_blocked": False,
            "numeric_stop_stage": "A2",
            "gate_failures": sorted(actual_failures),
            "p3_residual": a2.get("explicit_true_residual"),
            "rho_ref": math.inf,
            "rho3": math.inf,
            "thresholds": {
                "rho_ref": A_RHO_REF_LIMIT,
                "rho3": A_RHO3_LIMIT,
                "p3_residual": A_RESIDUAL_LIMIT,
            },
        }
    a3_vectors = a3.get("vectors") if isinstance(a3, dict) else None
    if not isinstance(a3_vectors, dict):
        _error(errors, "schema:A3 vector facts missing")
        return {"resource_blocked": False, "gate_failures": gate_failures}
    if a3.get("schema") != A3_SCHEMA:
        _error(errors, "schema:A3 schema version mismatch")
    for label, descriptor in (
        ("A3.e3_loaded", a3_vectors.get("e3_loaded")),
        ("A3.e6_full", a3_vectors.get("e6_full")),
        ("A3.e6_algebraic", a3_vectors.get("e6_algebraic")),
        ("A3.action", a3_vectors.get("action")),
        ("A3.r6_new", a3_vectors.get("r6_new")),
        ("A3.r3_new", a3_vectors.get("r3_new")),
    ):
        _check_owned_facts(
            descriptor,
            errors,
            label,
            allow_nonzero=label == "A3.e6_full",
        )
        vector_values[label] = _check_vector(context["raw_dir"], descriptor, errors, label)
        if label != "A3.e6_algebraic":
            canonical[label] = _check_canonical_vector(
                context["root"],
                descriptor.get("canonical") if isinstance(descriptor, dict) else None,
                errors,
                f"{label}.canonical",
            )
    e6_full = a3_vectors.get("e6_full")
    if isinstance(e6_full, dict):
        transfer_facts = e6_full.get("transfer_last_apply_facts")
        transfer_residual = e6_full.get("fine_mpc_constraint_residual")
        if (
            not isinstance(transfer_facts, dict)
            or transfer_facts.get("operation") != "primal"
            or transfer_facts.get("finite") is not True
            or transfer_facts.get("input_unchanged") is not True
            or not _finite(transfer_residual)
            or float(transfer_residual) < 0.0
            or float(transfer_residual) > A_TRANSFER_CONSTRAINT_LIMIT
            or transfer_facts.get("fine_mpc_constraint_residual") != transfer_residual
        ):
            _error(errors, "numerical:A3 e6_full constraint/transfer facts do not close")
    e6_algebraic = a3_vectors.get("e6_algebraic")
    action_descriptor = a3_vectors.get("action")
    if (
        not isinstance(action_descriptor, dict)
        or not isinstance(e6_algebraic, dict)
        or action_descriptor.get("input_array_sha256")
        != e6_algebraic.get("array_sha256")
    ):
        _error(errors, "provenance:A3 action input is not e6_algebraic")
    e3_loaded = a3_vectors.get("e3_loaded")
    e3_source = a2_vectors.get("e3")
    if isinstance(e3_loaded, dict) and isinstance(e3_source, dict):
        for key in ("relative_path", "sha256", "bytes", "dtype", "shape"):
            if e3_loaded.get(key) != e3_source.get(key):
                _error(errors, f"provenance:A3 e3_loaded {key} is not A2.e3")
        if (
            e3_loaded.get("source_array_sha256") != e3_source.get("array_sha256")
            or e3_loaded.get("loaded_array_sha256") != e3_source.get("array_sha256")
            or e3_loaded.get("loaded_unchanged") is not True
        ):
            _error(errors, "provenance:A3 e3_loaded array SHA does not close")
    loaded_inputs = a3.get("loaded_inputs")
    if not isinstance(loaded_inputs, dict):
        _error(errors, "input:A3 loaded input facts missing")
    else:
        for label in ("r6", "e3"):
            item = loaded_inputs.get(label)
            before = item.get("before") if isinstance(item, dict) else None
            after = item.get("after") if isinstance(item, dict) else None
            _check_owned_facts(before, errors, f"A3.{label}.before")
            _check_owned_facts(after, errors, f"A3.{label}.after")
            if not isinstance(item, dict) or item.get("unchanged") is not True or not isinstance(before, dict) or not isinstance(after, dict) or before.get("array_sha256") != after.get("array_sha256"):
                _error(errors, f"input:A3 {label} was changed")
    if all(vector_values.get(label) is not None for label in ("A1.r6", "A1.r3", "A3.action", "A3.r6_new", "A3.r3_new")):
        r6 = vector_values["A1.r6"]
        action = vector_values["A3.action"]
        r6_new = vector_values["A3.r6_new"]
        r3 = vector_values["A1.r3"]
        r3_new = vector_values["A3.r3_new"]
        expected_r6_new = r6 - action
        r6_difference = r6_new - expected_r6_new
        r6_relative = float(np.linalg.norm(r6_difference)) / max(
            float(np.linalg.norm(r6_new)),
            float(np.linalg.norm(expected_r6_new)),
            np.finfo(float).tiny,
        )
        if r6_relative > 1.0e-12:
            _error(errors, "numerical:A3 r6_new does not equal r6-action")
        rho_ref = float(np.linalg.norm(r6_new)) / max(float(np.linalg.norm(r6)), np.finfo(float).tiny)
        rho3 = float(np.linalg.norm(r3_new)) / max(float(np.linalg.norm(r3)), np.finfo(float).tiny)
    else:
        rho_ref = rho3 = math.inf
    if not _finite(a3.get("rho_ref")) or not math.isclose(float(a3["rho_ref"]), rho_ref, rel_tol=1e-12, abs_tol=1e-12):
        _error(errors, "numerical:stored rho_ref does not close")
    elif rho_ref > A_RHO_REF_LIMIT:
        gate_failures.append("rho_ref")
    if not _finite(a3.get("rho3")) or not math.isclose(float(a3["rho3"]), rho3, rel_tol=1e-12, abs_tol=1e-12):
        _error(errors, "numerical:stored rho3 does not close")
    elif rho3 > A_RHO3_LIMIT:
        gate_failures.append("rho3")
    counts = a3.get("operation_counts")
    if not isinstance(counts, dict) or counts.get("p6_action") != 1 or counts.get("p63_primal") != 1 or counts.get("p63_adjoint") != 1:
        _error(errors, "lifecycle:Oracle A operation counts mismatch")
    _canonical_pair(context["root"], a2_vectors.get("e3", {}).get("canonical") if isinstance(a2_vectors.get("e3"), dict) else None, a3_vectors.get("e3_loaded", {}).get("canonical") if isinstance(a3_vectors.get("e3_loaded"), dict) else None, errors, "A2.e3-A3.e3_loaded", values=True)
    for label, left, right in (
        ("p6 dual A1.r6-A3.action", a1_vectors.get("r6"), a3_vectors.get("action")),
        ("p6 dual A1.r6-A3.r6_new", a1_vectors.get("r6"), a3_vectors.get("r6_new")),
        ("p3 dual A1.r3-A3.r3_new", a1_vectors.get("r3"), a3_vectors.get("r3_new")),
    ):
        _canonical_pair(context["root"], left.get("canonical") if isinstance(left, dict) else None, right.get("canonical") if isinstance(right, dict) else None, errors, label)
    return {
        "resource_blocked": False,
        "numeric_stop_stage": None,
        "gate_failures": gate_failures,
        "rho_ref": rho_ref,
        "rho3": rho3,
        "p3_residual": a2.get("explicit_true_residual"),
        "thresholds": {"rho_ref": A_RHO_REF_LIMIT, "rho3": A_RHO3_LIMIT, "p3_residual": A_RESIDUAL_LIMIT},
    }


def _check_history(
    history: Any,
    errors: list[str],
    label: str,
    gate_failures: list[str] | None = None,
    *,
    require_arnoldi_closure: bool = False,
) -> dict[str, Any]:
    expected = list(range(B_INTERVAL, B_STEPS + 1, B_INTERVAL))
    if not isinstance(history, list) or [row.get("iteration") for row in history if isinstance(row, dict)] != expected:
        _error(errors, f"schema:{label} must have exact 20-step history")
        return {"final": math.inf, "count": 0}
    for row in history:
        if (
            not isinstance(row, dict)
            or not _finite(row.get("true_residual_norm"))
            or not _finite(row.get("true_relative_residual"))
        ):
            _error(errors, f"schema:{label} contains invalid history values")
            continue
        if row.get("finite") is not True:
            _gate(gate_failures, errors, f"numerical:{label}.finite")
        if require_arnoldi_closure:
            closure = row.get("explicit_vs_arnoldi_relative")
            if not _finite(closure):
                _error(errors, f"schema:{label} explicit-vs-Arnoldi closure is missing")
            elif float(closure) > B_EXPLICIT_ARNOLDI_LIMIT:
                _gate(gate_failures, errors, f"numerical:{label}.explicit_vs_arnoldi")
    final = float(history[-1]["true_relative_residual"])
    return {"final": final, "count": len(history)}


def _check_residual_packets(
    facts: dict[str, Any],
    raw_dir: Path,
    history: Any,
    errors: list[str],
    label: str,
) -> None:
    packets = facts.get("residual_packets")
    if not isinstance(history, list) or not isinstance(packets, list) or len(packets) != len(history):
        _error(errors, f"schema:{label} residual packet count mismatch")
        return
    rhs_digest = None
    expected_iterations = range(B_INTERVAL, B_STEPS + 1, B_INTERVAL)
    for expected_iteration, packet, history_row in zip(
        expected_iterations, packets, history, strict=True
    ):
        if not isinstance(packet, dict) or packet.get("iteration") != expected_iteration:
            _error(errors, f"schema:{label} residual packet iteration mismatch")
            continue
        rhs = _check_vector(raw_dir, packet.get("rhs"), errors, f"{label}.rhs")
        ax = _check_vector(raw_dir, packet.get("ax"), errors, f"{label}.ax")
        if rhs is None or ax is None:
            continue
        digest = packet["rhs"].get("sha256") if isinstance(packet.get("rhs"), dict) else None
        if rhs_digest is None:
            rhs_digest = digest
        elif digest != rhs_digest:
            _error(errors, f"numerical:{label} rhs changed across checkpoints")
        residual = rhs - ax
        rhs_norm = max(float(np.linalg.norm(rhs)), np.finfo(float).tiny)
        true_norm = float(np.linalg.norm(residual))
        true_relative = true_norm / rhs_norm
        if not isinstance(history_row, dict):
            _error(errors, f"schema:{label} history row is not an object")
            continue
        if not _finite(history_row.get("true_residual_norm")) or not math.isclose(
            float(history_row["true_residual_norm"]), true_norm, rel_tol=1e-12, abs_tol=1e-12
        ):
            _error(errors, f"numerical:{label} raw residual norm does not close")
        if not math.isclose(
            float(history_row.get("true_relative_residual", math.inf)),
            true_relative,
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
            _error(errors, f"numerical:{label} raw residual relative does not close")


def _check_basis(
    context: dict[str, Any],
    facts: dict[str, Any],
    errors: list[str],
    gate_failures: list[str] | None = None,
) -> None:
    audit = facts.get("audit")
    if not isinstance(audit, dict):
        _error(errors, "schema:unrestarted disk audit missing")
        return
    if audit.get("bounded_full_vector_buffer_count") != 8 or audit.get("bounded_full_vector_buffer_gate") is not True:
        _error(errors, "resource:full-vector buffer bound is not eight")
    lifecycle = audit.get("buffer_lifecycle")
    if not isinstance(lifecycle, dict) or not lifecycle:
        _error(errors, "resource:full-vector lifecycle facts are missing")
    else:
        counts = []
        for phase, item in lifecycle.items():
            if not isinstance(item, dict) or item.get("count") != 8 or not isinstance(item.get("names"), list):
                _error(errors, f"resource:full-vector {phase} window is not eight")
            else:
                counts.append(item["count"])
        if counts and max(counts) > 8:
            _error(errors, "resource:full-vector lifecycle exceeded eight")
    if audit.get("orthogonalization_passes") != 2 or audit.get("scratch_manifest") != "basis_manifest.json":
        _error(errors, "numerical:unrestarted MGS/checkpoint contract mismatch")
    if audit.get("input_unchanged") is not True:
        _gate(gate_failures, errors, "numerical:unrestarted.input_unchanged")
    if audit.get("final_solution_finite") is not True:
        _gate(gate_failures, errors, "numerical:unrestarted.final_solution_finite")
    if audit.get("orthogonality_limit") != B_ORTHOGONALITY_LIMIT:
        _error(errors, "schema:unrestarted orthogonality limit is not frozen")
    if audit.get("explicit_arnoldi_limit") != B_EXPLICIT_ARNOLDI_LIMIT:
        _error(errors, "schema:unrestarted explicit-Arnoldi limit is not frozen")
    orthogonality = audit.get("orthogonality_max_abs")
    if not _finite(orthogonality):
        _error(errors, "schema:unrestarted orthogonality fact is invalid")
    elif float(orthogonality) > B_ORTHOGONALITY_LIMIT:
        _gate(gate_failures, errors, "numerical:unrestarted.orthogonality")
    if "hessenberg_finite" not in audit:
        _error(errors, "schema:unrestarted Hessenberg finite fact is missing")
    elif audit.get("hessenberg_finite") is not True:
        _gate(gate_failures, errors, "numerical:unrestarted.hessenberg_finite")
    root = context["raw_dir"] / "unrestarted" / "basis"
    manifest_path = root / "basis_manifest.json"
    if not manifest_path.is_file():
        _error(errors, "provenance:unrestarted basis manifest missing")
        return
    try:
        manifest = _load_json(manifest_path)
    except (ValueError, OSError) as exc:
        _error(errors, f"infrastructure:basis manifest cannot be read: {exc}")
        return
    if not isinstance(manifest, dict):
        _error(errors, "schema:basis manifest is not an object")
        return
    if audit.get("scratch_manifest_sha256") != _sha256(manifest_path):
        _error(errors, "provenance:basis manifest SHA mismatch")
    if manifest.get("mmap") is not False or manifest.get("basis_in_memory") is not False:
        _error(errors, "resource:basis is not demonstrably disk-backed")
    h_descriptor = manifest.get("H")
    if not isinstance(h_descriptor, dict):
        _error(errors, "provenance:H disk descriptor missing")
    else:
        h_relative = h_descriptor.get("path")
        h_path = (root / h_relative).resolve() if isinstance(h_relative, str) else None
        if h_path is None or root.resolve() not in h_path.parents or not h_path.is_file():
            _error(errors, "provenance:H path is missing or escapes basis root")
        else:
            if (
                h_descriptor.get("bytes") != h_path.stat().st_size
                or h_descriptor.get("sha256") != _sha256(h_path)
            ):
                _error(errors, "provenance:H SHA/size mismatch")
            try:
                h_values = np.asarray(np.load(h_path, allow_pickle=False))
            except (OSError, ValueError, TypeError) as exc:
                _error(errors, f"infrastructure:H array cannot be read: {exc}")
            else:
                if h_descriptor.get("dtype") != "complex128" or h_values.dtype != np.dtype(np.complex128) or h_values.ndim != 2:
                    _error(errors, "schema:H dtype or rank mismatch")
                elif not np.all(np.isfinite(h_values)):
                    _gate(gate_failures, errors, "numerical:unrestarted.hessenberg_finite")
        h_shape = facts.get("hessenberg_shape")
        if (
            not isinstance(h_shape, list)
            or len(h_shape) != 2
            or not all(_is_int(item) and item >= 0 for item in h_shape)
            or h_descriptor.get("rows") != h_shape[0]
            or h_descriptor.get("columns") != h_shape[1]
        ):
            _error(errors, "schema:H shape mismatch")
        record_h = facts.get("hessenberg")
        expected_record_path = (
            Path("raw") / "unrestarted" / "basis" / h_relative
            if isinstance(h_relative, str)
            else None
        )
        if (
            not isinstance(record_h, dict)
            or expected_record_path is None
            or record_h.get("relative_path") != expected_record_path.as_posix()
            or record_h.get("bytes") != h_descriptor.get("bytes")
            or record_h.get("sha256") != h_descriptor.get("sha256")
            or record_h.get("dtype") != "complex128"
            or record_h.get("shape") != [h_descriptor.get("rows"), h_descriptor.get("columns")]
        ):
            _error(errors, "provenance:H raw descriptor does not match basis manifest")
    for name, capacity in (("V", B_STEPS + 1), ("Z", B_STEPS)):
        descriptor = manifest.get(name)
        if (
            not isinstance(descriptor, dict)
            or descriptor.get("capacity") != capacity
            or descriptor.get("mmap") is not False
            or descriptor.get("dtype") != "complex128"
        ):
            _error(errors, f"schema:{name} disk descriptor mismatch")
            continue
        relative = descriptor.get("path")
        path = (root / relative).resolve() if isinstance(relative, str) else None
        if path is None or root.resolve() not in path.parents or not path.is_file():
            _error(errors, f"provenance:{name} path escapes raw root")
            continue
        if descriptor.get("written_count") != capacity:
            _error(errors, f"schema:{name} did not write its full fixed capacity")
        records = descriptor.get("records")
        if not isinstance(records, list) or len(records) != capacity:
            _error(errors, f"provenance:{name} column manifest is incomplete")
        else:
            rows = descriptor.get("rows")
            expected_bytes = rows * 16 if _is_int(rows) and rows >= 0 else -1
            for index, record in enumerate(records):
                if (
                    not isinstance(record, dict)
                    or expected_bytes < 0
                    or record.get("column") != index
                    or record.get("offset") != index * expected_bytes
                    or record.get("bytes") != expected_bytes
                ):
                    _error(errors, f"provenance:{name} column descriptor mismatch")
                    break
                if _sha256_range(path, record["offset"], expected_bytes) != record.get("sha256"):
                    _error(errors, f"provenance:{name} column SHA mismatch")
                    break
        expected_sync = list(range(B_INTERVAL, B_STEPS + 1, B_INTERVAL))
        if descriptor.get("sync_cadence") != B_INTERVAL or descriptor.get("sync_columns") != expected_sync:
            _error(errors, f"lifecycle:{name} fsync cadence mismatch")
        if path.stat().st_size != descriptor.get("allocated_bytes"):
            _error(errors, f"provenance:{name} allocated file mismatch")
    expected_sync = [
        {"iteration": iteration, "V": iteration, "Z": iteration}
        for iteration in range(B_INTERVAL, B_STEPS + 1, B_INTERVAL)
    ]
    if audit.get("sync_cadence") != B_INTERVAL or audit.get("sync_columns") != expected_sync:
        _error(errors, "lifecycle:unrestarted sync cadence is not exactly 20 through 500")


def _check_b(context: dict[str, Any], expected_source_sha: str, errors: list[str]) -> dict[str, Any]:
    worker = context.get("worker")
    if not isinstance(worker, dict):
        _error(errors, "schema:Oracle B worker record missing")
        return {}
    gate_failures: list[str] = []
    _check_source_bundle(worker, expected_source_sha, errors)
    disk_preflight = worker.get("disk_preflight")
    if (
        not isinstance(disk_preflight, dict)
        or disk_preflight.get("required_free_bytes") != B_DISK_FREE_BYTES
        or not _is_int(disk_preflight.get("free_bytes"))
        or disk_preflight.get("free_bytes") < B_DISK_FREE_BYTES
    ):
        _error(errors, "resource:Oracle B free-disk preflight failed")
    checkpoint = worker.get("checkpoint")
    checkpoint_expected = {
        "iteration": 1000,
        "explicit_true_residual": CHECKPOINT_EXPLICIT_RESIDUAL,
        "input_identity_sha256": CHECKPOINT_INPUT_IDENTITY_SHA256,
        "operator_identity_sha256": CHECKPOINT_OPERATOR_IDENTITY_SHA256,
        "physical_model_sha256": PHYSICAL_MODEL_SHA256,
        "source_sha": CHECKPOINT_SOURCE_SHA,
        "mpi_size": 1,
        "manifest_sha256": CHECKPOINT_MANIFEST_SHA256,
        "solution_sha256": CHECKPOINT_SOLUTION_SHA256,
    }
    if not isinstance(checkpoint, dict):
        _error(errors, "provenance:Oracle B checkpoint facts missing")
    else:
        for key, expected in checkpoint_expected.items():
            if checkpoint.get(key) != expected:
                _error(errors, f"provenance:Oracle B checkpoint {key} mismatch")
    _check_architecture(worker.get("architecture"), errors, "B")
    same_start = worker.get("same_start")
    if not isinstance(same_start, dict):
        _error(errors, "input:Oracle B same-start authority is missing")
        same_start = {}
    same_rhs = same_start.get("rhs")
    same_initial = same_start.get("initial_solution")
    if (
        not isinstance(same_rhs, dict)
        or not isinstance(same_rhs.get("sha256"), str)
        or not isinstance(same_rhs.get("descriptor"), dict)
        or same_rhs.get("finite") is not True
    ):
        _error(errors, "input:Oracle B same-start RHS fact is invalid")
    if (
        not isinstance(same_initial, dict)
        or not isinstance(same_initial.get("sha256"), str)
        or not isinstance(same_initial.get("descriptor"), dict)
        or same_initial.get("finite") is not True
    ):
        _error(errors, "input:Oracle B same-start initial solution fact is invalid")
    reference = worker.get("reference")
    unrestarted = worker.get("unrestarted")
    if not isinstance(reference, dict):
        _error(errors, "schema:Oracle B reference facts missing")
        reference = {}
    if not isinstance(unrestarted, dict):
        _error(errors, "schema:Oracle B unrestarted facts missing")
        unrestarted = {}
    reference_result = _check_history(
        reference.get("history"), errors, "reference", gate_failures
    )
    unrestarted_result = _check_history(
        unrestarted.get("history"),
        errors,
        "unrestarted",
        gate_failures,
        require_arnoldi_closure=True,
    )
    reference_history = reference.get("history")
    unrestarted_history = unrestarted.get("history")
    expected_history = list(range(B_INTERVAL, B_STEPS + 1, B_INTERVAL))
    if isinstance(reference_history, list) and isinstance(unrestarted_history, list):
        if [row.get("iteration") for row in reference_history if isinstance(row, dict)] != expected_history:
            _error(errors, "schema:reference history boundary mismatch")
        if [row.get("iteration") for row in unrestarted_history if isinstance(row, dict)] != expected_history:
            _error(errors, "schema:unrestarted history boundary mismatch")
    _check_residual_packets(
        reference,
        context["raw_dir"],
        reference_history,
        errors,
        "reference",
    )
    _check_residual_packets(
        unrestarted,
        context["raw_dir"],
        unrestarted_history,
        errors,
        "unrestarted",
    )
    if reference.get("algorithm") != "right_gmres_restart20":
        _error(errors, "schema:reference algorithm mismatch")
    if unrestarted.get("algorithm") != "right_fgmres_unrestarted_disk_backed":
        _error(errors, "schema:unrestarted algorithm mismatch")
    if reference.get("iterations") != B_STEPS or unrestarted.get("iterations") != B_STEPS:
        _error(errors, "lifecycle:both Oracle B methods must run exactly 500 steps")
    if reference.get("explicit_action_count") != 26:
        _error(errors, "lifecycle:reference explicit action count does not close")
    if reference.get("residual_packet_action_count") != 25 or reference.get("observer_action_count") != 25:
        _error(errors, "lifecycle:reference observer action count does not close")
    if reference.get("ksp_destroy_count") != 25:
        _error(errors, "lifecycle:reference KSP destroy count does not close")
    if unrestarted.get("residual_packet_action_count") != 25:
        _error(errors, "lifecycle:unrestarted raw action count does not close")
    disk_audit = unrestarted.get("audit")
    if not isinstance(disk_audit, dict):
        _error(errors, "schema:unrestarted disk audit missing")
        disk_audit = {}
    if disk_audit.get("algorithm") != "right_flexible_gmres_unrestarted":
        _error(errors, "schema:unrestarted disk audit algorithm mismatch")
    if disk_audit.get("max_steps") != B_STEPS or disk_audit.get("checkpoint_interval") != B_INTERVAL:
        _error(errors, "schema:unrestarted fixed step contract mismatch")
    if disk_audit.get("iterations") != B_STEPS:
        _error(errors, "lifecycle:unrestarted iteration count does not close")
    if disk_audit.get("action_count") != 526 or unrestarted.get("action_count") != 526:
        _error(errors, "lifecycle:unrestarted action count does not close")
    if disk_audit.get("pc_count") != B_STEPS or unrestarted.get("pc_count") != B_STEPS:
        _error(errors, "lifecycle:unrestarted PC count does not close")
    if disk_audit.get("explicit_action_count") != 25:
        _error(errors, "lifecycle:unrestarted explicit action count does not close")
    if disk_audit.get("checkpoint_iterations") != expected_history:
        _error(errors, "lifecycle:unrestarted checkpoint iterations do not close")
    if unrestarted.get("explicit_action_count") != 25:
        _error(errors, "lifecycle:unrestarted explicit action facts do not close")
    if not _is_int(reference.get("matvec_count")) or reference.get("matvec_count") < 0:
        _error(errors, "lifecycle:reference matvec count is invalid")
    reference_cycle_count = B_STEPS // B_INTERVAL
    expected_reference_matvec = B_STEPS + reference_cycle_count
    expected_reference_pc = B_STEPS + reference_cycle_count
    if reference.get("matvec_count") != expected_reference_matvec:
        _error(errors, "lifecycle:reference matvec count does not close")
    if reference.get("pc_apply_count") != expected_reference_pc:
        _error(errors, "lifecycle:reference PC count does not close")
    cycles = reference.get("cycles")
    if not isinstance(cycles, list) or len(cycles) != reference_cycle_count:
        _error(errors, "lifecycle:reference must have exactly 25 cycles")
        cycles = []
    cycle_matvec = 0
    cycle_pc = 0
    for index, cycle in enumerate(cycles):
        start = B_START_ITERATION + index * B_INTERVAL
        if (
            not isinstance(cycle, dict)
            or cycle.get("cycle_index") != start // B_INTERVAL
            or cycle.get("start_iteration") != start
            or cycle.get("end_iteration") != start + B_INTERVAL
            or cycle.get("iterations") != B_INTERVAL
            or not _is_int(cycle.get("matvec_count"))
            or cycle.get("matvec_count") != cycle.get("iterations") + 1
            or cycle.get("pc_apply_count") != cycle.get("iterations") + 1
            or cycle.get("ksp_destroyed") is not True
        ):
            _error(errors, f"lifecycle:reference cycle {index} boundary/count mismatch")
            continue
        cycle_matvec += cycle["matvec_count"]
        cycle_pc += cycle["pc_apply_count"]
    if cycle_matvec != expected_reference_matvec or cycle_pc != expected_reference_pc:
        _error(errors, "lifecycle:reference cycle count ledger does not close")
    if reference.get("matvec_count") != cycle_matvec or reference.get("pc_apply_count") != cycle_pc:
        _error(errors, "lifecycle:reference total count ledger does not close")
    reference_settings = reference.get("settings")
    if (
        not isinstance(reference_settings, dict)
        or reference_settings.get("ksp_type") != "gmres"
        or reference_settings.get("pc_side") != "right"
        or reference_settings.get("norm_type") != "unpreconditioned"
        or reference_settings.get("restart") != 20
        or reference_settings.get("cycle_max_it") != 20
        or reference_settings.get("max_it") != 1500
        or reference_settings.get("start_iteration") != 1000
        or reference_settings.get("residual_limit") != 0.0
        or reference_settings.get("residual_replacement") is not True
        or reference_settings.get("initial_guess_nonzero") is not True
        or reference_settings.get("first_checkpoint_iteration") is not None
        or reference_settings.get("checkpoint_interval") != B_INTERVAL
    ):
        _error(errors, "schema:reference GMRES(20) settings mismatch")
    unrestarted_settings = unrestarted.get("settings")
    if (
        not isinstance(unrestarted_settings, dict)
        or unrestarted_settings.get("ksp_type") != "fgmres"
        or unrestarted_settings.get("pc_side") != "right"
        or unrestarted_settings.get("norm_type") != "unpreconditioned"
        or unrestarted_settings.get("restart") is not None
        or unrestarted_settings.get("max_steps") != B_STEPS
        or unrestarted_settings.get("checkpoint_interval") != B_INTERVAL
        or unrestarted_settings.get("initial_guess_nonzero") is not True
        or unrestarted_settings.get("residual_replacement") is not False
    ):
        _error(errors, "schema:unrestarted right-FGMRES settings mismatch")
    if (
        not _finite(reference.get("final_true_residual"))
        or not math.isclose(
            float(reference.get("final_true_residual")),
            reference_result["final"],
            rel_tol=1e-12,
            abs_tol=1e-12,
        )
    ):
        _error(errors, "numerical:reference final residual does not close")
    if (
        not _finite(unrestarted.get("final_true_residual"))
        or not math.isclose(
            float(unrestarted.get("final_true_residual")),
            unrestarted_result["final"],
            rel_tol=1e-12,
            abs_tol=1e-12,
        )
    ):
        _error(errors, "numerical:unrestarted final residual does not close")

    for label, facts in (("reference", reference), ("unrestarted", unrestarted)):
        if facts.get("finite") is not True:
            _gate(gate_failures, errors, f"numerical:{label}.finite")
    audit_input = disk_audit.get("input_unchanged")
    if audit_input is not True:
        _gate(gate_failures, errors, "input:unrestarted.input_unchanged")
    disk_finite = disk_audit.get("final_solution_finite")
    if disk_finite is not True:
        _gate(gate_failures, errors, "numerical:unrestarted.final_solution_finite")

    reference_initial = reference.get("initial_true_residual")
    unrestarted_initial = unrestarted.get("initial_true_residual")
    if (
        not _finite(reference_initial)
        or not _finite(unrestarted_initial)
        or not math.isclose(float(reference_initial), float(unrestarted_initial), rel_tol=1e-12, abs_tol=1e-12)
    ):
        _error(errors, "numerical:same-start initial true residual does not close")

    if isinstance(same_rhs, dict) and isinstance(same_initial, dict):
        same_rhs_sha = same_rhs.get("sha256")
        same_initial_sha = same_initial.get("sha256")
        same_rhs_values = _check_vector(
            context["raw_dir"], same_rhs.get("descriptor"), errors, "same-start.rhs"
        )
        same_initial_values = _check_vector(
            context["raw_dir"],
            same_initial.get("descriptor"),
            errors,
            "same-start.initial_solution",
        )
        if same_rhs_values is not None and (
            same_rhs.get("sha256")
            != hashlib.sha256(
                memoryview(np.ascontiguousarray(same_rhs_values)).cast("B")
            ).hexdigest()
        ):
            _error(errors, "provenance:same-start RHS array SHA does not close")
        if same_initial_values is not None and (
            same_initial.get("sha256")
            != hashlib.sha256(
                memoryview(np.ascontiguousarray(same_initial_values)).cast("B")
            ).hexdigest()
        ):
            _error(errors, "provenance:same-start initial array SHA does not close")
        for label, facts in (("reference", reference), ("unrestarted", unrestarted)):
            nested = same_start.get(label)
            if not isinstance(nested, dict):
                _error(errors, f"input:same-start {label} facts are missing")
                continue
            for prefix, expected_sha in (("rhs", same_rhs_sha), ("initial_solution", same_initial_sha)):
                before = nested.get(f"{prefix}_before_sha256")
                after = nested.get(f"{prefix}_after_sha256")
                if before != expected_sha or after != expected_sha:
                    _error(errors, f"input:same-start {label} {prefix} hash does not close")
            if nested.get("input_unchanged") is not True:
                _gate(gate_failures, errors, f"input:{label}.input_unchanged")
            if nested.get("finite") is not True:
                _gate(gate_failures, errors, f"numerical:{label}.finite")
            if not _finite(nested.get("initial_true_residual")) or not math.isclose(
                float(nested["initial_true_residual"]),
                float(reference_initial),
                rel_tol=1e-12,
                abs_tol=1e-12,
            ):
                _error(errors, f"numerical:same-start {label} initial residual mismatch")
    else:
        same_rhs_sha = same_initial_sha = None

    _check_basis(context, unrestarted, errors, gate_failures)
    ratio = unrestarted_result["final"] / max(reference_result["final"], np.finfo(float).tiny)
    if not _finite(ratio):
        _error(errors, "numerical:Oracle B mechanism ratio is not finite")
    classification = (
        "UNRESTARTED_KRYLOV_STRONG_SIGNAL"
        if ratio <= 0.1
        else "UNRESTARTED_KRYLOV_WEAK_SIGNAL"
        if ratio <= 0.5
        else "UNRESTARTED_KRYLOV_NO_SIGNAL"
    )
    trend = {}
    if isinstance(unrestarted_history, list) and len(unrestarted_history) == 25:
        row_300 = unrestarted_history[14]
        row_500 = unrestarted_history[24]
        start_200 = float(row_300["true_relative_residual"])
        end_200 = float(row_500["true_relative_residual"])
        trend = {
            "r300": start_200,
            "r500": end_200,
            "last_200_ratio": end_200 / max(start_200, np.finfo(float).tiny),
            "last_200_descent": end_200 < start_200,
            "definition": "unrestarted true relative residual r500 / r300",
        }
    return {
        "reference_final": reference_result["final"],
        "unrestarted_final": unrestarted_result["final"],
        "relative_ratio": ratio,
        "classification": classification,
        "gate_failures": gate_failures,
        "trend": trend,
    }


def _classification(phase: str, errors: list[str], metrics: dict[str, Any]) -> str:
    if any(error.startswith("resource:") for error in errors):
        return "ORACLE_A_RESOURCE_GATE_FAIL" if phase == "oracle-a" else "ORACLE_B_RESOURCE_GATE_FAIL"
    if any(error.startswith("numerical:") for error in errors):
        return "ORACLE_A_NUMERICAL_GATE_FAIL" if phase == "oracle-a" else "ORACLE_B_NUMERICAL_GATE_FAIL"
    if any(
        error.startswith(("infrastructure:", "schema:", "provenance:", "lifecycle:", "input:"))
        for error in errors
    ):
        return "INFRASTRUCTURE_FAILURE_RETRYABLE"
    if phase == "oracle-a":
        if metrics.get("resource_blocked") is True:
            return "A_ORACLE_BLOCKED_BY_RESOURCE_PREFLIGHT"
        gate_failures = set(metrics.get("gate_failures", ()))
        if metrics.get("numeric_stop_stage") in {"A1", "A2"} or gate_failures.intersection(
            {"checkpoint_reproduction", "p3_explicit_residual", "rho3", "finite", "input", "slave"}
        ):
            return "ORACLE_A_NUMERICAL_GATE_FAIL"
        rho_ref = metrics.get("rho_ref", math.inf)
        rho3 = metrics.get("rho3", math.inf)
        if rho_ref <= A_RHO_REF_LIMIT and rho3 <= A_RHO3_LIMIT:
            return "EXACT_P3_COARSE_SPAN_PASS"
        if A_RHO_REF_LIMIT < rho_ref < 0.90 and metrics.get(
            "p3_residual", math.inf
        ) <= A_RESIDUAL_LIMIT:
            return "EXACT_P3_COARSE_SPAN_WEAK_SIGNAL"
        return "EXACT_P3_COARSE_SPAN_FAIL"
    if metrics.get("gate_failures"):
        return "ORACLE_B_NUMERICAL_GATE_FAIL"
    return metrics.get("classification", "ORACLE_B_NUMERICAL_GATE_FAIL")


def check_artifact(record_path: str | Path, expected_source_sha: str = SOURCE_SHA) -> dict[str, Any]:
    errors: list[str] = []
    record_path = Path(record_path).resolve()
    try:
        parent = _load_json(record_path)
        if not isinstance(parent, dict):
            raise ValueError("parent record is not an object")
        context = _check_common(parent, record_path, expected_source_sha, errors)
        metrics = _check_a(context, expected_source_sha, errors) if context.get("phase") == "oracle-a" else _check_b(context, expected_source_sha, errors)
        classification = _classification(str(context.get("phase")), errors, metrics)
    except Exception as exc:
        errors.append(f"infrastructure:raw checker boundary failed: {exc}")
        classification = "INFRASTRUCTURE_FAILURE_RETRYABLE"
        metrics = {}
    return {
        "schema": "task038.v17.oracle.checker.v1",
        "status": "PASS" if not errors else "FAIL",
        "evidence_valid": not errors,
        "classification": classification,
        "errors": errors,
        "evidence_kind": {"process": "measured", "vectors": "measured", "hashes": "derived", "relative": "derived"},
        "metrics": metrics,
        "record": str(record_path),
    }


def _write_output(path: Path, value: dict[str, Any]) -> None:
    encoded = (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()
    with path.open("xb") as stream:
        stream.write(encoded)
        stream.flush()
        import os

        os.fsync(stream.fileno())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", required=True)
    parser.add_argument("--expected-source-sha", default=SOURCE_SHA)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    result = check_artifact(args.record, args.expected_source_sha)
    _write_output(Path(args.output), result)
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
