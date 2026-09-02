"""Task41 MPI1 source-only canonical comparison.

The tool compares the current external source with persisted physical-key
packets.  It deliberately stops before a solve, factor, QEP, or preconditioner.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from src.io.input_validation import (
    TASK041_HARD_MEMORY_BYTES,
    TASK041_TIMEOUT_SECONDS,
    TASK041_WARNING_MEMORY_GIB,
    load_and_resolve,
    simulation_config_3d_from_normalized,
    task041_profile_errors,
)

TASK041_SOURCE_ONLY_SCHEMA = "task041.source_only.v1"
TASK041_SOURCE_ONLY_PROFILE = "task041.source_only.external.v1"
TASK041_EXPECTED_BRANCH = "codex/20260902-task41-mpi1-shortwave-hybrid-capacity"
TASK041_SOURCE_LABEL = "external_dtn_coupling"
TASK041_INPUT = "input/official/task041/5nm_p6h4_m480_mpi1.dat"
TASK041_SURFACE_QUADRATURE_DEGREE = 37
TASK041_MIN_MEMAVAILABLE_BYTES = 384 * 2**30
TASK041_TOLERANCE = 1.0e-12
TASK041_AUTHORITY_CHILD_SHA = (
    "f60389e2e4dd1541046812588a9a7e09251e2b46a14face00eb57c953be3b98b"
)
TASK041_AUTHORITY_PARENT_SHA = (
    "98610d2826342b963e0243ff57dd53753a82d0379021c89130069a9a0900ebd0"
)
TASK041_AUTHORITY_SOURCE_SHA = "17cf5ae28ccdcf7b0a28548ec1296b9956390509"
TASK041_AUTHORITY_INPUT_SHA = (
    "4e60924b5997e3ca99e324ea14779f9014efc6a1304a9aa11de9c808353f1811"
)
TASK041_AUTHORITY_PHYSICAL_SHA = (
    "8391d46139646440d869aa43abe6a68bc921fc1972a10030c64be81dffdd527c"
)
TASK041_AUTHORITY_RESOLVED_SHA = (
    "f965c38abea08bee0ff83a6603e336ca4823deb932af7064aed3c571f8f63883"
)
TASK041_AUTHORITY_KEY_SHA = (
    "2aca3dc2150fe20f6e7e3c05751cd81ee2c6a4878918e9eee092ff24d41cca76"
)
TASK041_AUTHORITY_PERSISTED_PAIR_SHA = (
    "e09d22f64263a8b4facf83b52f0dffb370d076847b44bceecf65b1c16ac7c237"
)
TASK041_PARENT_SCHEMA = "task040.v9.source_canonical_bridge.v1"
TASK041_CHILD_SCHEMA = "task040.v9.source_canonical_bridge.packet.v1"
SOURCE_SEMANTICS_UNCHANGED = "SOURCE_SEMANTICS_UNCHANGED"
REFERENCE_SOURCE_SEMANTICS_CHANGED = "REFERENCE_SOURCE_SEMANTICS_CHANGED"
IMPLEMENTATION_FAILURE = "IMPLEMENTATION_FAILURE"
RESOURCE_UNAVAILABLE = "RESOURCE_UNAVAILABLE"


class SourceOnlyIdentityError(RuntimeError):
    """A source, packet, or current-layout identity gate failed."""

    def __init__(self, failures: Sequence[str]):
        self.failures = tuple(str(failure) for failure in failures)
        super().__init__("; ".join(self.failures))


class SourceOnlyResourceStop(RuntimeError):
    """A Task41 resource boundary requires a controlled stop."""


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected JSON object: {path}")
    return value


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, np.generic):
        return _jsonable(value.item())
    if isinstance(value, Path):
        return str(value)
    return value


def _key_digest(keys: Sequence[str]) -> str:
    return _sha256_bytes("\n".join(sorted(str(key) for key in keys)).encode("utf-8"))


def _pair_digest(keys: Sequence[str], values: np.ndarray) -> str:
    if len(keys) != int(values.size):
        raise ValueError("canonical key/value lengths differ")
    from src.solvers.hybrid_source_canonical_bridge import packet_pair_digest

    digests = sorted(
        packet_pair_digest(
            str(key),
            complex(value),
            label=TASK041_SOURCE_LABEL,
            side="bottom",
        )
        for key, value in zip(keys, values, strict=True)
    )
    return _sha256_bytes("\n".join(digests).encode("ascii"))


def _relative(first: np.ndarray, second: np.ndarray) -> float:
    left = np.asarray(first, dtype=np.complex128)
    right = np.asarray(second, dtype=np.complex128)
    if left.shape != right.shape:
        return float("inf")
    denominator = max(float(np.linalg.norm(right)), 1.0e-300)
    return float(np.linalg.norm(left - right) / denominator)


def classify_reference_relative(relative: float) -> str:
    """Classify only the current-versus-persisted value comparison."""

    if np.isfinite(relative) and float(relative) <= TASK041_TOLERANCE:
        return SOURCE_SEMANTICS_UNCHANGED
    return REFERENCE_SOURCE_SEMANTICS_CHANGED


def classify_source_comparison(structural_gate_pass: bool, relative: float) -> str:
    if not structural_gate_pass:
        return IMPLEMENTATION_FAILURE
    return classify_reference_relative(relative)


def _path_inside(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise SourceOnlyIdentityError(
            (f"path escapes authority root: {relative}",)
        ) from exc
    return path


def load_verified_shards(
    shard_root: str | Path,
    shard_declarations: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Verify eight owner-local packet shards and merge their key/value bytes."""

    root = Path(shard_root).resolve()
    failures: list[str] = []
    if len(shard_declarations) != 8:
        failures.append("authority must declare exactly eight shards")
    ranks = [int(item.get("rank", -1)) for item in shard_declarations]
    if sorted(ranks) != list(range(8)):
        failures.append("authority shard ranks are not the unique range 0..7")
    records: list[dict[str, Any]] = []
    values_by_key: dict[str, complex] = {}
    all_keys: list[str] = []
    for declaration in sorted(
        shard_declarations, key=lambda item: int(item.get("rank", -1))
    ):
        rank = int(declaration.get("rank", -1))
        keys_relative = str(declaration.get("keys_path", ""))
        values_relative = str(declaration.get("values_path", ""))
        keys_path = _path_inside(root, keys_relative)
        values_path = _path_inside(root, values_relative)
        packet_relative = str(
            Path(keys_relative).with_name(
                Path(keys_relative).name.replace(
                    "canonical_keys.json", "canonical_packet.json"
                )
            )
        )
        packet_path = _path_inside(root, packet_relative)
        if not keys_path.is_file():
            failures.append(f"rank {rank} keys JSON is missing")
        if not values_path.is_file():
            failures.append(f"rank {rank} values NPY is missing")
        if not packet_path.is_file():
            failures.append(f"rank {rank} packet manifest is missing")
        if (
            not keys_path.is_file()
            or not values_path.is_file()
            or not packet_path.is_file()
        ):
            continue
        key_bytes_sha = _sha256_bytes(keys_path.read_bytes())
        value_bytes_sha = _sha256_bytes(values_path.read_bytes())
        packet_bytes_sha = _sha256_bytes(packet_path.read_bytes())
        if key_bytes_sha != declaration.get("key_sha256"):
            failures.append(f"rank {rank} keys JSON SHA mismatch")
        if value_bytes_sha != declaration.get("values_sha256"):
            failures.append(f"rank {rank} values NPY SHA mismatch")
        if packet_bytes_sha != declaration.get("shard_manifest_sha256"):
            failures.append(f"rank {rank} packet manifest SHA mismatch")
        packet = _read_json(packet_path)
        if packet.get("schema") != TASK041_CHILD_SCHEMA:
            failures.append(f"rank {rank} packet schema mismatch")
        if packet.get("label") != TASK041_SOURCE_LABEL:
            failures.append(f"rank {rank} packet label mismatch")
        if packet.get("side") != "bottom":
            failures.append(f"rank {rank} packet side mismatch")
        if packet.get("full_numeric_replica") is not False:
            failures.append(f"rank {rank} packet full_numeric_replica is not false")
        if packet.get("rank") != rank:
            failures.append(f"rank {rank} packet rank mismatch")
        if packet.get("keys_path") != keys_relative:
            failures.append(f"rank {rank} packet keys path mismatch")
        if packet.get("values_path") != values_relative:
            failures.append(f"rank {rank} packet values path mismatch")
        if declaration.get("schema") != TASK041_CHILD_SCHEMA:
            failures.append(f"rank {rank} shard schema mismatch")
        if declaration.get("label") != TASK041_SOURCE_LABEL:
            failures.append(f"rank {rank} shard label mismatch")
        if declaration.get("side") != "bottom":
            failures.append(f"rank {rank} shard side mismatch")
        if declaration.get("owner_local") is not True:
            failures.append(f"rank {rank} owner_local is not true")
        if declaration.get("numeric_allgather") is not False:
            failures.append(f"rank {rank} numeric_allgather is not false")
        if declaration.get("full_numeric_replica") is not False:
            failures.append(f"rank {rank} shard full_numeric_replica is not false")
        key_document = _read_json(keys_path)
        keys = key_document.get("keys")
        try:
            raw_values = np.load(values_path, allow_pickle=False)
        except (OSError, ValueError) as exc:
            failures.append(f"rank {rank} values NPY cannot be loaded: {exc}")
            continue
        if not isinstance(keys, list) or not all(isinstance(key, str) for key in keys):
            failures.append(f"rank {rank} keys JSON is not a string list")
            continue
        if raw_values.dtype != np.dtype(np.complex128):
            failures.append(f"rank {rank} values dtype is not complex128")
        if raw_values.ndim != 1:
            failures.append(f"rank {rank} values shape is not one-dimensional")
        if not np.isfinite(raw_values).all():
            failures.append(f"rank {rank} values contain non-finite entries")
        if len(keys) != int(raw_values.size):
            failures.append(f"rank {rank} key/value lengths differ")
        if len(keys) != int(declaration.get("key_count_local", -1)):
            failures.append(f"rank {rank} declared key count differs")
        values = np.asarray(raw_values, dtype=np.complex128)
        for key, value in zip(keys, values, strict=False):
            if key in values_by_key:
                failures.append(f"duplicate canonical key across shards: {key}")
            values_by_key[key] = complex(value)
            all_keys.append(key)
        records.append(
            {
                "rank": rank,
                "key_count": len(keys),
                "keys_file_sha256": key_bytes_sha,
                "values_file_sha256": value_bytes_sha,
                "packet_file_sha256": packet_bytes_sha,
                "owner_local": True,
                "numeric_allgather": False,
                "full_numeric_replica": False,
            }
        )
    actual_key_sha = _key_digest(all_keys)
    declared_key_shas = {
        str(item.get("global_key_set_sha256", "")) for item in shard_declarations
    }
    if len(declared_key_shas) != 1 or actual_key_sha not in declared_key_shas:
        failures.append("cross-shard global key SHA mismatch")
    if failures:
        raise SourceOnlyIdentityError(failures)
    ordered_keys = tuple(sorted(values_by_key))
    ordered_values = np.asarray(
        [values_by_key[key] for key in ordered_keys], dtype=np.complex128
    )
    return {
        "records": records,
        "keys": ordered_keys,
        "values": ordered_values,
        "values_by_key": values_by_key,
        "key_count": len(ordered_keys),
        "global_key_set_sha256": actual_key_sha,
        "persisted_value_pair_digest_sha256": _pair_digest(
            ordered_keys, ordered_values
        ),
    }


def _load_source_authority_raw(
    authority_root: str | Path,
    authority_manifest_sha256: str,
) -> dict[str, Any]:
    """Verify the fixed V9 source bridge parent, child, and eight shards."""

    root = Path(authority_root).resolve()
    parent_path = root / "v9_source_bridge_manifest.json"
    child_path = (
        root
        / "source_bridge"
        / ("v9_external_dtn_coupling_source_bridge_manifest.json")
    )
    failures: list[str] = []
    if authority_manifest_sha256 != TASK041_AUTHORITY_PARENT_SHA:
        failures.append("authority manifest argument is not the frozen parent SHA")
    if not parent_path.is_file():
        raise SourceOnlyIdentityError(("authority parent manifest is missing",))
    parent_bytes_sha = _sha256_bytes(parent_path.read_bytes())
    if parent_bytes_sha != authority_manifest_sha256:
        failures.append("authority parent manifest bytes SHA mismatch")
    parent = _read_json(parent_path)
    if parent.get("schema") != TASK041_PARENT_SCHEMA:
        failures.append("authority parent schema mismatch")
    if parent.get("status") != "verified_source_canonical_bridge":
        failures.append("authority parent status mismatch")
    if parent.get("classification") != "V9_SOURCE_CANONICAL_BRIDGE_PASS":
        failures.append("authority parent classification mismatch")
    if parent.get("source_order") != [
        "external_dtn_coupling",
        "fixed_random_repeat_0",
    ]:
        failures.append("authority parent source_order mismatch")
    if parent.get("source_sha") != TASK041_AUTHORITY_SOURCE_SHA:
        failures.append("authority parent source SHA mismatch")
    if parent.get("full_numeric_replica") is not False:
        failures.append("authority parent full_numeric_replica is not false")
    provenance = parent.get("source_provenance", {})
    for field, expected in (
        ("input_sha256", TASK041_AUTHORITY_INPUT_SHA),
        ("physical_model_sha256", TASK041_AUTHORITY_PHYSICAL_SHA),
        ("resolved_config_sha256", TASK041_AUTHORITY_RESOLVED_SHA),
    ):
        if provenance.get(field) != expected:
            failures.append(f"authority parent {field} mismatch")
    external = parent.get("sources", {}).get(TASK041_SOURCE_LABEL, {})
    if external.get("manifest_sha256") != TASK041_AUTHORITY_CHILD_SHA:
        failures.append("authority parent external child SHA declaration mismatch")
    if not child_path.is_file():
        failures.append("authority external child manifest is missing")
        raise SourceOnlyIdentityError(failures)
    child_bytes_sha = _sha256_bytes(child_path.read_bytes())
    if child_bytes_sha != TASK041_AUTHORITY_CHILD_SHA:
        failures.append("authority external child manifest bytes SHA mismatch")
    child = _read_json(child_path)
    if child.get("schema") != TASK041_CHILD_SCHEMA:
        failures.append("authority child schema mismatch")
    if child.get("label") != TASK041_SOURCE_LABEL:
        failures.append("authority child label mismatch")
    if child.get("numeric_allgather") is not False:
        failures.append("authority child numeric_allgather is not false")
    if child.get("full_numeric_replica") is not False:
        failures.append("authority child full_numeric_replica is not false")
    shards = child.get("shards")
    if not isinstance(shards, list):
        failures.append("authority child shards is not a list")
        raise SourceOnlyIdentityError(failures)
    if child.get("side") not in (None, "bottom"):
        failures.append("authority child side mismatch")
    try:
        shard_data = load_verified_shards(root / "source_bridge", shards)
    except SourceOnlyIdentityError as exc:
        failures.extend(exc.failures)
        shard_data = None
    if shard_data is not None:
        if child.get("global_key_set_sha256") != shard_data["global_key_set_sha256"]:
            failures.append("authority child global key SHA mismatch")
        if external.get("global_key_set_sha256") != shard_data["global_key_set_sha256"]:
            failures.append("authority parent external global key SHA mismatch")
        if shard_data["global_key_set_sha256"] != TASK041_AUTHORITY_KEY_SHA:
            failures.append("authority global key SHA is not the frozen value")
        persisted_pair_sha = shard_data["persisted_value_pair_digest_sha256"]
        if persisted_pair_sha != TASK041_AUTHORITY_PERSISTED_PAIR_SHA:
            failures.append("authority persisted value-pair SHA mismatch")
        declared_pairs = {
            str(child.get("persisted_value_pair_digest_sha256", "")),
            *(
                str(item.get("persisted_value_pair_digest_sha256", ""))
                for item in shards
            ),
        }
        if declared_pairs != {TASK041_AUTHORITY_PERSISTED_PAIR_SHA}:
            failures.append("authority declared persisted pair SHA mismatch")
    orientation = external.get("orientation_phase_audit", {})
    if orientation.get("orientation_applied_once") is not True:
        failures.append("authority orientation was not applied exactly once")
    if orientation.get("phase_application_count") != 1:
        failures.append("authority phase application count is not one")
    matrix_inventory = external.get("matrix_factor_inventory", {})
    if any(
        int(matrix_inventory.get(name, 0)) != 0
        for name in ("C", "D", "H", "factor", "qep", "fgmres")
    ):
        failures.append("authority matrix/factor inventory is not zero")
    if external.get("numeric_allgather") is not False:
        failures.append("authority external numeric_allgather is not false")
    persisted_external = (
        child.get("persisted_identity", {})
        .get("semantic_descriptor", {})
        .get("external", {})
    )
    if not isinstance(persisted_external, Mapping):
        failures.append("authority persisted external semantic descriptor is missing")
        persisted_external = {}
    if "mode_key" not in persisted_external or "sign" not in persisted_external:
        failures.append("authority persisted external mode identity is incomplete")
    persisted_source_record = {
        "current_active_rhs_norm": external.get("current_active_rhs_norm"),
        "persisted_canonical_coefficient_norm": external.get(
            "persisted_canonical_coefficient_norm"
        ),
    }
    for field, value in persisted_source_record.items():
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            failures.append(f"authority source record {field} is not numeric")
            continue
        if not np.isfinite(numeric_value) or numeric_value <= 0.0:
            failures.append(
                f"authority source record {field} is not finite and positive"
            )
    if failures or shard_data is None:
        raise SourceOnlyIdentityError(failures or ("authority shard loading failed",))
    return {
        "root": str(root),
        "parent_manifest_sha256": parent_bytes_sha,
        "child_manifest_sha256": child_bytes_sha,
        "shards": shard_data["records"],
        "keys": shard_data["keys"],
        "values": shard_data["values"],
        "values_by_key": shard_data["values_by_key"],
        "global_key_set_sha256": shard_data["global_key_set_sha256"],
        "persisted_value_pair_digest_sha256": shard_data[
            "persisted_value_pair_digest_sha256"
        ],
        "orientation_phase_audit": _jsonable(orientation),
        "matrix_factor_inventory": _jsonable(matrix_inventory),
        "persisted_mode_key": _jsonable(persisted_external.get("mode_key")),
        "persisted_sign": persisted_external.get("sign"),
        "persisted_source_record": persisted_source_record,
        "identity": {
            "source_sha": TASK041_AUTHORITY_SOURCE_SHA,
            "input_sha256": TASK041_AUTHORITY_INPUT_SHA,
            "physical_model_sha256": TASK041_AUTHORITY_PHYSICAL_SHA,
            "resolved_config_sha256": TASK041_AUTHORITY_RESOLVED_SHA,
        },
    }


def _mem_available_bytes() -> int:
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        key, _, value = line.partition(":")
        if key == "MemAvailable":
            return int(value.strip().split()[0]) * 1024
    raise RuntimeError("MemAvailable is unavailable")


def _resource_snapshot() -> dict[str, Any]:
    from benchmarks.task034_wsl_resources import resource_authority_sample

    sample = resource_authority_sample(os.getpid())
    process_tree = sample["process_tree"]
    cgroup = sample["job_cgroup"]
    cgroup_swap = cgroup.get("swap_current_bytes")
    swap_values = [int(process_tree["swap_bytes"])]
    if cgroup.get("dedicated_job_cgroup") and cgroup_swap is not None:
        swap_values.append(int(cgroup_swap))
    return {
        "scope": "worker_process_tree_not_final_capacity",
        "process_tree_rss_bytes": int(process_tree["rss_bytes"]),
        "process_tree_swap_bytes": int(process_tree["swap_bytes"]),
        "swap_used_bytes": max(swap_values),
        "all_status_readable": bool(process_tree["all_status_readable"]),
        "process_tree_pids": len(process_tree["pids"]),
        "memory_authority_bytes": int(sample["memory_authority_bytes"]),
        "mem_available_bytes": _mem_available_bytes(),
        "job_no_swap": bool(sample["job_no_swap"]),
        "dedicated_job_cgroup": bool(cgroup.get("dedicated_job_cgroup")),
    }


def _enforce_resource_boundary(
    snapshot: Mapping[str, Any],
    started: float,
    *,
    startup: bool = False,
) -> None:
    if not snapshot["all_status_readable"]:
        raise SourceOnlyResourceStop("process-tree resource status is unreadable")
    if int(snapshot["swap_used_bytes"]) != 0:
        raise SourceOnlyResourceStop("Task41 source-only swap boundary was crossed")
    if int(snapshot["process_tree_rss_bytes"]) >= TASK041_HARD_MEMORY_BYTES:
        raise SourceOnlyResourceStop("Task41 source-only hard RSS boundary was crossed")
    if (
        startup
        and int(snapshot["mem_available_bytes"]) < TASK041_MIN_MEMAVAILABLE_BYTES
    ):
        raise SourceOnlyResourceStop("Task41 startup MemAvailable floor was not met")
    if time.monotonic() - started > TASK041_TIMEOUT_SECONDS:
        raise SourceOnlyResourceStop("Task41 source-only timeout boundary was crossed")


def _write_marker(
    root: Path,
    started: float,
    stage: str,
    detail: Mapping[str, Any],
    *,
    source_build_count: int,
    enforce: bool = True,
) -> dict[str, Any]:
    try:
        resource = _resource_snapshot()
    except Exception as exc:
        if enforce:
            raise
        resource = {"sample_error": f"{type(exc).__name__}: {exc}"}
    if enforce:
        _enforce_resource_boundary(resource, started)
    record = {
        "schema": TASK041_SOURCE_ONLY_SCHEMA,
        "stage": stage,
        "wall_seconds": time.monotonic() - started,
        "resource": {
            **resource,
            "warning_memory_bytes": int(TASK041_WARNING_MEMORY_GIB * 2**30),
            "hard_memory_bytes": TASK041_HARD_MEMORY_BYTES,
            "timeout_seconds": TASK041_TIMEOUT_SECONDS,
            "swap_limit_bytes": 0,
        },
        "counts": {
            "source_build_count": int(source_build_count),
            "action_apply_count": 0,
            "matrix_apply_count": 0,
        },
        "detail": _jsonable(detail),
    }
    with (root / "markers.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, sort_keys=True, allow_nan=False) + "\n")
    return record


def _run_local_git(repo_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )
    if completed.returncode != 0:
        raise SourceOnlyIdentityError(
            (f"local git identity command failed: {' '.join(args)}",)
        )
    return completed.stdout.strip()


def _validate_repository_identity(repo_root: Path, source_sha: str) -> dict[str, Any]:
    head = _run_local_git(repo_root, "rev-parse", "HEAD")
    branch = _run_local_git(repo_root, "branch", "--show-current")
    status = _run_local_git(repo_root, "status", "--porcelain", "--untracked-files=all")
    identity = {
        "head": head,
        "source_sha": source_sha,
        "branch": branch,
        "worktree_clean": status == "",
        "status_scope": "git_porcelain_nonignored_untracked_all",
    }
    failures = []
    if head != source_sha:
        failures.append("HEAD does not equal supplied source_sha")
    if branch != TASK041_EXPECTED_BRANCH:
        failures.append("current branch is not the Task41 execution branch")
    if status:
        failures.append("nonignored worktree is not clean")
    if failures:
        raise SourceOnlyIdentityError(tuple(failures))
    return identity


def _canonical_descriptor_hashes(keys, beta_metadata):
    from src.solvers.hybrid_interface_basis import (
        canonical_external_mode_metadata_sha256,
        canonical_mode_keys_sha256,
    )

    return {
        "canonical_key_list_sha256": canonical_mode_keys_sha256(keys),
        "resolved_mode_metadata_sha256": canonical_external_mode_metadata_sha256(
            beta_metadata
        ),
    }


def _extract_current_bottom_inventory(external_mode_inventory):
    from collections.abc import Mapping

    if not isinstance(external_mode_inventory, Mapping):
        raise SourceOnlyIdentityError(("current external inventory is not a mapping",))
    keys = external_mode_inventory.get("keys")
    modes = external_mode_inventory.get("modes")
    count = external_mode_inventory.get("count")
    if not isinstance(keys, list) or not isinstance(modes, list):
        raise SourceOnlyIdentityError(("current inventory keys/modes are not lists",))
    if not isinstance(count, int) or len(keys) != count or len(modes) != count:
        raise SourceOnlyIdentityError(("current inventory count/list lengths differ",))
    bottom_keys = []
    bottom_modes = []
    try:
        for key, mode in zip(keys, modes, strict=True):
            if not isinstance(key, Mapping):
                raise SourceOnlyIdentityError(("inventory key is not a mapping",))
            if not isinstance(mode, Mapping):
                raise TypeError("current inventory mode is not a mapping")
            mode_key = {
                "side": mode["side"],
                "m": mode["m"],
                "n": mode["n"],
                "polarization": mode["polarization"],
            }
            if dict(key) != mode_key:
                raise ValueError("current inventory mode key differs")
            if mode["side"] == "bottom":
                bottom_keys.append(dict(key))
                bottom_modes.append(dict(mode))
    except (KeyError, TypeError, ValueError) as exc:
        raise SourceOnlyIdentityError(
            (f"current inventory key binding failed: {exc}",)
        ) from exc
    return bottom_keys, bottom_modes


def bind_current_external_mode_authority(
    authority, external_mode_inventory, resolved_sha
):
    """Bind current bottom modes to the verified persisted descriptor."""
    if not isinstance(authority, Mapping):
        raise SourceOnlyIdentityError(("loader authority is not a mapping",))
    if "frozen_descriptor" not in authority:
        raise SourceOnlyIdentityError(("loader authority lacks frozen_descriptor",))
    frozen = authority["frozen_descriptor"]
    if not isinstance(frozen, Mapping):
        raise SourceOnlyIdentityError(("frozen descriptor is not a mapping",))

    required = (
        "count",
        "canonical_keys",
        "beta_metadata",
        "canonical_key_list_sha256",
        "resolved_mode_metadata_sha256",
        "legacy_beta_metadata_sha256",
        "legacy_beta_metadata_sha256_expected",
        "index177_key",
        "resolved_config_sha256",
    )
    failures = [
        f"frozen external authority missing {field}"
        for field in required
        if field not in frozen
    ]
    if failures:
        raise SourceOnlyIdentityError(tuple(failures))

    sha_fields = (
        "canonical_key_list_sha256",
        "resolved_mode_metadata_sha256",
        "legacy_beta_metadata_sha256",
        "legacy_beta_metadata_sha256_expected",
        "resolved_config_sha256",
    )
    for field in sha_fields:
        value = frozen[field]
        if not isinstance(value, str) or len(value) != 64:
            failures.append(f"frozen {field} is not a 64-character hex string")
            continue
        try:
            int(value, 16)
        except ValueError:
            failures.append(f"frozen {field} is not hexadecimal")

    canonical_keys = frozen["canonical_keys"]
    beta_metadata = frozen["beta_metadata"]
    if not isinstance(canonical_keys, list):
        failures.append("frozen canonical_keys is not a list")
    if not isinstance(beta_metadata, list):
        failures.append("frozen beta_metadata is not a list")
    if frozen["count"] != 296:
        failures.append("frozen external authority count is not 296")
    if isinstance(canonical_keys, list) and len(canonical_keys) != frozen["count"]:
        failures.append("frozen canonical key count differs")
    if isinstance(beta_metadata, list) and len(beta_metadata) != frozen["count"]:
        failures.append("frozen beta metadata count differs")
    if (
        frozen["legacy_beta_metadata_sha256"]
        != frozen["legacy_beta_metadata_sha256_expected"]
    ):
        failures.append("frozen legacy beta hashes differ")
    if (
        not isinstance(canonical_keys, list)
        or len(canonical_keys) <= 177
        or frozen["index177_key"] != canonical_keys[177]
    ):
        failures.append("frozen index177_key is not bound to frozen canonical keys")
    if failures:
        raise SourceOnlyIdentityError(tuple(failures))

    try:
        current_keys, current_beta = _extract_current_bottom_inventory(
            external_mode_inventory
        )
    except SourceOnlyIdentityError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise SourceOnlyIdentityError(
            (f"current inventory is invalid: {exc}",)
        ) from exc

    failures = []
    if len(current_keys) != frozen["count"]:
        failures.append("current/frozen bottom count differs")
    if current_keys != canonical_keys:
        failures.append("current/frozen bottom canonical keys differ")
    if current_beta != beta_metadata:
        failures.append("current/frozen bottom beta metadata differs")
    if not isinstance(resolved_sha, str) or len(resolved_sha) != 64:
        failures.append("current resolved config SHA is not a 64-character hex string")
    else:
        try:
            int(resolved_sha, 16)
        except ValueError:
            failures.append("current resolved config SHA is not hexadecimal")
    if len(current_keys) <= 177:
        failures.append("current canonical keys do not contain index177")
    if failures:
        raise SourceOnlyIdentityError(tuple(failures))

    try:
        current_hashes = _canonical_descriptor_hashes(current_keys, current_beta)
    except (KeyError, TypeError, ValueError) as exc:
        raise SourceOnlyIdentityError(
            (f"current canonical authority hashing failed: {exc}",)
        ) from exc
    failures = []
    for field in ("canonical_key_list_sha256", "resolved_mode_metadata_sha256"):
        if current_hashes[field] != frozen[field]:
            failures.append(f"current/frozen {field} differs")
    if current_keys[177] != frozen["index177_key"]:
        failures.append("current index177_key differs from frozen authority")
    if failures:
        raise SourceOnlyIdentityError(tuple(failures))

    current = dict(frozen)
    current.update(
        {
            "canonical_keys": list(current_keys),
            "beta_metadata": list(current_beta),
            **current_hashes,
            "index177_key": current_keys[177],
            "resolved_config_sha256": resolved_sha,
        }
    )
    audit = {
        "frozen_count": frozen["count"],
        "current_count": len(current_keys),
        "frozen_index177_key": frozen["index177_key"],
        "frozen_canonical_key_list_sha256": frozen["canonical_key_list_sha256"],
        "current_canonical_key_list_sha256": current_hashes[
            "canonical_key_list_sha256"
        ],
        "frozen_resolved_mode_metadata_sha256": frozen["resolved_mode_metadata_sha256"],
        "current_resolved_mode_metadata_sha256": current_hashes[
            "resolved_mode_metadata_sha256"
        ],
        "frozen_legacy_beta_metadata_sha256": frozen["legacy_beta_metadata_sha256"],
        "frozen_legacy_beta_metadata_sha256_expected": frozen[
            "legacy_beta_metadata_sha256_expected"
        ],
        "frozen_resolved_config_sha256": frozen["resolved_config_sha256"],
        "current_resolved_config_sha256": resolved_sha,
        "nonphysical_config_identity_changed": (
            resolved_sha != frozen["resolved_config_sha256"]
        ),
        "physical_external_inventory_exact": True,
        "legacy_beta_metadata_policy": "frozen_opaque_not_recomputed",
        "frozen_manifest_beta_metadata_reproducible": False,
    }
    return current, audit


def _extract_frozen_external_mode_descriptor(parent):
    from collections.abc import Mapping

    try:
        identity_preflight = parent["identity_preflight"]
        if not isinstance(identity_preflight, Mapping):
            raise TypeError("identity_preflight is not a mapping")
        if identity_preflight.get("pass") is not True:
            raise ValueError("identity_preflight.pass is not true")
        descriptor = identity_preflight["external_mode_authority"]
        if not isinstance(descriptor, Mapping):
            raise TypeError("external_mode_authority is not a mapping")
        required = (
            "count",
            "canonical_keys",
            "beta_metadata",
            "canonical_key_list_sha256",
            "resolved_mode_metadata_sha256",
            "legacy_beta_metadata_sha256",
            "legacy_beta_metadata_sha256_expected",
            "index177_key",
            "resolved_config_sha256",
        )
        missing = tuple(field for field in required if field not in descriptor)
        if missing:
            raise KeyError(f"missing descriptor fields: {', '.join(missing)}")
        if descriptor["count"] != 296:
            raise ValueError("frozen external authority count is not 296")
    except (KeyError, TypeError, ValueError) as exc:
        raise SourceOnlyIdentityError((f"invalid external authority: {exc}",)) from exc
    try:
        return json.loads(json.dumps(descriptor, sort_keys=True))
    except (TypeError, ValueError) as exc:
        raise SourceOnlyIdentityError(
            (f"frozen descriptor is not JSONable: {exc}",)
        ) from exc


def load_source_authority(authority_root, authority_manifest_sha256):
    authority = _load_source_authority_raw(authority_root, authority_manifest_sha256)
    root = Path(authority_root).resolve()
    parent_path = root / "v9_source_bridge_manifest.json"
    try:
        parent_bytes = parent_path.read_bytes()
        if authority_manifest_sha256 != TASK041_AUTHORITY_PARENT_SHA:
            raise ValueError("unexpected Task41 authority parent SHA")
        if hashlib.sha256(parent_bytes).hexdigest() != TASK041_AUTHORITY_PARENT_SHA:
            raise ValueError("parent manifest SHA changed after shard validation")
        parent = json.loads(parent_bytes)
        descriptor = _extract_frozen_external_mode_descriptor(parent)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SourceOnlyIdentityError(
            (f"cannot load frozen descriptor: {exc}",)
        ) from exc
    result = dict(authority)
    result["frozen_descriptor"] = descriptor
    result["frozen_descriptor_record"] = {
        field: descriptor[field]
        for field in (
            "count",
            "canonical_key_list_sha256",
            "resolved_mode_metadata_sha256",
            "legacy_beta_metadata_sha256",
            "legacy_beta_metadata_sha256_expected",
            "index177_key",
            "resolved_config_sha256",
        )
    }
    return result


def _environment_snapshot() -> dict[str, Any]:
    executable_entry = Path(os.path.abspath(sys.executable))
    executable_target = executable_entry.resolve()
    prefix = Path(sys.prefix).resolve()
    repo_root = Path(__file__).resolve().parents[1]
    repo_venv = repo_root / ".venv"
    repo_venv_resolved = repo_venv.resolve()
    from basix import __file__ as basix_path
    from dolfinx import __file__ as dolfinx_path
    from mpi4py import __file__ as mpi4py_path
    from petsc4py import PETSc
    from petsc4py import __file__ as petsc4py_path
    from slepc4py import __file__ as slepc4py_path

    thread_names = (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    )
    threads = {name: os.environ.get(name) for name in thread_names}
    marker = os.environ.get("MYFENICS_NATIVE_COMPLEX_ENV")
    scalar = np.dtype(PETSc.ScalarType)
    snapshot = {
        "marker": marker,
        "python": str(executable_entry),
        "python_resolved_target": str(executable_target),
        "sys_prefix": str(prefix),
        "petsc_scalar_type": str(scalar),
        "petsc_int_type": str(np.dtype(PETSc.IntType)),
        "packages": {
            "mpi4py": str(mpi4py_path),
            "petsc4py": str(petsc4py_path),
            "slepc4py": str(slepc4py_path),
            "dolfinx": str(dolfinx_path),
            "basix": str(basix_path),
        },
        "threads": threads,
    }
    failures: list[str] = []
    if marker != "1":
        failures.append("MYFENICS_NATIVE_COMPLEX_ENV is not 1")
    if repo_venv not in executable_entry.parents:
        failures.append("Python invocation entry is outside the repository .venv")
    if prefix != repo_venv_resolved:
        failures.append("sys.prefix does not identify the repository .venv")
    if scalar != np.dtype(np.complex128):
        failures.append("PETSc.ScalarType is not complex128")
    if any(value != "1" for value in threads.values()):
        failures.append("native thread variables are not all 1")
    if failures:
        raise SourceOnlyIdentityError(failures)
    return snapshot


def _current_source_packets(
    system: Any, vector: Any
) -> tuple[tuple[str, ...], np.ndarray, dict[str, Any]]:
    from src.solvers.hybrid_bare_f_authority import canonical_packets_for_vector

    tokens, values, audit = canonical_packets_for_vector(system, vector)
    return tuple(tokens), np.asarray(values, dtype=np.complex128), dict(audit)


def _current_orientation_phase_histogram(
    tokens: Sequence[str],
) -> tuple[dict[str, int], dict[str, int], int]:
    orientation: dict[str, int] = {}
    phase: dict[str, int] = {}
    missing = 0
    for token in tokens:
        try:
            decoded = json.loads(token)
            orientation_state = json.dumps(
                decoded[4], sort_keys=True, separators=(",", ":")
            )
            coefficient = tuple(float(value) for value in decoded[6])
        except (IndexError, TypeError, ValueError):
            missing += 1
            continue
        phase_class = "unit" if coefficient == (1.0, 0.0) else json.dumps(coefficient)
        orientation_key = orientation_state
        phase_key = phase_class
        orientation[orientation_key] = orientation.get(orientation_key, 0) + 1
        phase[phase_key] = phase.get(phase_key, 0) + 1
    return orientation, phase, missing


def _validate_source_audit(audit: Mapping[str, Any]) -> list[str]:
    failures: list[str] = []
    if audit.get("source") != "current_external_minimal_surface_components":
        failures.append("current source metadata source mismatch")
    if audit.get("sign") != -1.0:
        failures.append("current source metadata sign mismatch")
    mode_key = audit.get("mode_key")
    if not isinstance(mode_key, Mapping):
        failures.append("current source mode_key is missing")
    elif mode_key.get("side") != "bottom":
        failures.append("current source mode_key side mismatch")
    if audit.get("mode_index") != 177:
        failures.append("current source mode_index is not 177")
    if audit.get("surface_quadrature_degree") != TASK041_SURFACE_QUADRATURE_DEGREE:
        failures.append("current source surface quadrature degree mismatch")
    if audit.get("full_C_materialized") is not False:
        failures.append("current source materialized full C")
    if audit.get("matrix_objects") != {"C": 0, "D": 0, "H": 0}:
        failures.append("current source C/D/H inventory is not zero")
    if audit.get("raw_global_row_remap") is not False:
        failures.append("current source raw-row remap is not false")
    return failures


def _validate_current_system(system: Any) -> dict[str, Any]:
    inventory = dict(system.construction_inventory)
    objects = dict(inventory.get("objects", {}))
    matrix_inventory = {
        "C": int(objects.get("C", 0)),
        "D": int(objects.get("D", 0)),
        "H": int(objects.get("H", 0)),
        "factor": int(inventory.get("factor_count", 0)),
        "qep": int(inventory.get("qep_calls", 0)),
        "fgmres": int(inventory.get("fgmres_calls", 0)),
        "action_apply": int(getattr(system.static_context, "apply_count", 0)),
        "global_F_materialized": bool(inventory.get("global_F_materialized")),
        "global_AIJ_materialized": False,
        "physical_dtn_operator_constructed": bool(
            inventory.get("physical_dtn_operator_constructed")
        ),
        "woodbury_inverse_constructed": bool(
            inventory.get("woodbury_inverse_constructed")
        ),
        "operator_identity": inventory.get("operator_identity"),
    }
    failures = []
    if system.condensed.matrix is not None:
        failures.append("condensed global matrix is materialized")
    if matrix_inventory["global_F_materialized"]:
        failures.append("global F is materialized")
    if any(
        matrix_inventory[name] != 0
        for name in ("C", "D", "H", "factor", "qep", "fgmres", "action_apply")
    ):
        failures.append("matrix/factor/QEP/FGMRES/action inventory is nonzero")
    if matrix_inventory["physical_dtn_operator_constructed"]:
        failures.append("physical DtN operator was constructed")
    if matrix_inventory["woodbury_inverse_constructed"]:
        failures.append("Woodbury inverse was constructed")
    if "python" not in str(system.F.getType()).lower():
        failures.append("current F is not a PETSc Python action")
    if failures:
        raise SourceOnlyIdentityError(failures)
    return matrix_inventory


def run_source_only(
    *,
    input_path: str | Path,
    authority_root: str | Path,
    authority_manifest_sha256: str,
    run_directory: str | Path,
    comm: Any,
    source_sha: str,
) -> dict[str, Any]:
    """Run the MPI1 source-only comparison and write a fresh summary."""

    if int(comm.size) != 1:
        raise SourceOnlyIdentityError(("Task41 source-only requires MPI1",))
    if (
        not isinstance(source_sha, str)
        or len(source_sha) != 40
        or source_sha.lower() != source_sha
        or any(char not in "0123456789abcdef" for char in source_sha)
    ):
        raise SourceOnlyIdentityError(
            ("source_sha must be a 40-character lowercase hex SHA",)
        )
    repository_identity = _validate_repository_identity(
        Path(__file__).resolve().parents[1], source_sha
    )
    root = Path(run_directory).resolve()
    if root.exists():
        raise FileExistsError(f"fresh Task41 run directory already exists: {root}")
    started = time.monotonic()
    result: dict[str, Any] = {
        "schema": TASK041_SOURCE_ONLY_SCHEMA,
        "profile": TASK041_SOURCE_ONLY_PROFILE,
        "method": "task041_source_only_external_dtn_coupling",
        "status": IMPLEMENTATION_FAILURE,
        "classification": IMPLEMENTATION_FAILURE,
        "source_label": TASK041_SOURCE_LABEL,
        "official_rta": {"status": "not_run"},
        "limits": {
            "warning_memory_bytes": int(TASK041_WARNING_MEMORY_GIB * 2**30),
            "hard_memory_bytes": TASK041_HARD_MEMORY_BYTES,
            "startup_min_memavailable_bytes": TASK041_MIN_MEMAVAILABLE_BYTES,
            "timeout_seconds": TASK041_TIMEOUT_SECONDS,
            "swap_limit_bytes": 0,
        },
        "matrix_inventory": {
            "C": 0,
            "D": 0,
            "H": 0,
            "factor": 0,
            "qep": 0,
            "fgmres": 0,
            "action_apply": 0,
            "global_F_materialized": False,
            "global_AIJ_materialized": False,
        },
        "source_build_count": 0,
        "lifecycle": {
            "source_vectors_destroyed": False,
            "system_created": False,
            "system_destroyed": False,
            "system_not_created_or_destroyed": True,
            "cleanup_complete": False,
        },
    }
    root.mkdir(parents=True)
    system = None
    rhs1 = None
    rhs2 = None
    cleanup_failures: list[str] = []
    try:
        startup = _resource_snapshot()
        _enforce_resource_boundary(startup, started, startup=True)
        _write_marker(
            root,
            started,
            "preflight_begin",
            {"mpi_size": int(comm.size), "source_sha": source_sha},
            source_build_count=0,
        )
        result["environment"] = _environment_snapshot()
        spec = load_and_resolve(input_path)
        from src.io.resolved_config import resolved_config_sha256

        resolved_sha = resolved_config_sha256(spec)
        normalized = spec.as_jsonable()
        profile_failures = [
            f"{path}: {message}" for path, message in task041_profile_errors(normalized)
        ]
        if profile_failures:
            raise SourceOnlyIdentityError(profile_failures)
        result["identity"] = {
            "current": {
                "git": repository_identity,
                "model_id": spec.identity["model_id"],
                "run_id": spec.identity["run_id"],
                "input_sha256": str(spec.input_sha256),
                "physical_model_sha256": str(spec.physical_model_sha256),
                "resolved_config_sha256": str(resolved_sha),
                "source_sha": source_sha,
                "source_file_sha256": _sha256_bytes(Path(__file__).read_bytes()),
            },
        }
        _write_marker(
            root,
            started,
            "input_validated",
            result["identity"],
            source_build_count=0,
        )
        authority = load_source_authority(authority_root, authority_manifest_sha256)
        result["identity"]["persisted_authority"] = authority["identity"]
        result["authority"] = {
            "parent_manifest_sha256": authority["parent_manifest_sha256"],
            "child_manifest_sha256": authority["child_manifest_sha256"],
            "shard_count": len(authority["shards"]),
            "key_count": len(authority["keys"]),
            "global_key_set_sha256": authority["global_key_set_sha256"],
            "persisted_value_pair_digest_sha256": authority[
                "persisted_value_pair_digest_sha256"
            ],
            "orientation_phase_audit": authority["orientation_phase_audit"],
            "persisted_mode_key": authority["persisted_mode_key"],
            "persisted_sign": authority["persisted_sign"],
            "persisted_source_record": authority["persisted_source_record"],
        }
        _write_marker(
            root,
            started,
            "authority_loaded",
            result["authority"],
            source_build_count=0,
        )
        _write_marker(
            root,
            started,
            "eight_shards_validated",
            {"shard_count": len(authority["shards"])},
            source_build_count=0,
        )
        cfg_input = dict(normalized)
        cfg_input.pop("derived", None)
        cfg_input.pop("provenance", None)
        cfg_input.pop("schema_version", None)
        cfg = simulation_config_3d_from_normalized(cfg_input)
        from src.solvers.hybrid_bare_f_authority import (
            assemble_current_bare_f_authority_system,
            build_current_bare_f_rhs,
            canonical_layout_tokens,
            canonical_to_current_roundtrip_relative,
        )

        current_resolved_sha = result["identity"]["current"]["resolved_config_sha256"]
        current_external_mode_authority, authority_binding_audit = (
            bind_current_external_mode_authority(
                authority,
                spec.as_jsonable()["derived"]["external_mode_inventory"],
                current_resolved_sha,
            )
        )
        result["authority"]["external_mode_binding"] = authority_binding_audit
        system = assemble_current_bare_f_authority_system(
            cfg,
            side="bottom",
            bottom_interface_z_nm=10.0,
            top_interface_z_nm=110.0,
            source_work_directory=root / "source_work",
            selected_mode_provider=None,
            external_mode_authority=current_external_mode_authority,
            external_mode_current_resolved_config_sha256=current_resolved_sha,
            action_only=True,
            comm=comm,
        )
        result["lifecycle"]["system_created"] = True
        result["lifecycle"]["system_not_created_or_destroyed"] = False
        result["matrix_inventory"] = _validate_current_system(system)
        _write_marker(
            root,
            started,
            "assembly_ready",
            result["matrix_inventory"],
            source_build_count=0,
        )
        rhs1, source_audit1 = build_current_bare_f_rhs(system, TASK041_SOURCE_LABEL)
        result["source_build_count"] = 1
        tokens1, values1, packet_audit1 = _current_source_packets(system, rhs1)
        rhs1_owner_values = np.array(
            rhs1.getArray(readonly=True), copy=True, dtype=np.complex128
        )
        roundtrip1 = canonical_to_current_roundtrip_relative(
            system, tokens1, values1, rhs1
        )
        layout_tokens, layout_sha, layout_audit = canonical_layout_tokens(system)
        rhs2, source_audit2 = build_current_bare_f_rhs(system, TASK041_SOURCE_LABEL)
        result["source_build_count"] = 2
        tokens2, values2, packet_audit2 = _current_source_packets(system, rhs2)
        rhs2_owner_values = np.array(
            rhs2.getArray(readonly=True), copy=True, dtype=np.complex128
        )
        roundtrip2 = canonical_to_current_roundtrip_relative(
            system, tokens2, values2, rhs2
        )
        source_checks = _validate_source_audit(source_audit1)
        source_checks.extend(_validate_source_audit(source_audit2))
        if source_audit1.get("mode_key") != source_audit2.get("mode_key"):
            source_checks.append("source mode key changed between independent builds")
        if source_audit1.get("sign") != source_audit2.get("sign"):
            source_checks.append("source sign changed between independent builds")
        if source_audit1.get("mode_key") != authority["persisted_mode_key"]:
            source_checks.append(
                "current source mode key differs from persisted authority"
            )
        if source_audit1.get("sign") != authority["persisted_sign"]:
            source_checks.append("current source sign differs from persisted authority")
        if tokens1 != tuple(layout_tokens) or tokens2 != tuple(layout_tokens):
            source_checks.append("source token order differs from current layout")
        if len(tokens1) != len(set(tokens1)) or len(tokens2) != len(set(tokens2)):
            source_checks.append("current source canonical keys are duplicated")
        orientation_hist1, phase_hist1, missing_hist1 = (
            _current_orientation_phase_histogram(tokens1)
        )
        orientation_hist2, phase_hist2, missing_hist2 = (
            _current_orientation_phase_histogram(tokens2)
        )
        if missing_hist1 or missing_hist2:
            source_checks.append(
                "current physical tokens lack orientation or phase fields"
            )
        current_orientation1_ok = bool(missing_hist1 == 0 and np.isfinite(roundtrip1))
        current_orientation2_ok = bool(missing_hist2 == 0 and np.isfinite(roundtrip2))
        if not current_orientation1_ok or not current_orientation2_ok:
            source_checks.append(
                "current orientation/phase application evidence failed"
            )
        from src.solvers.hybrid_source_canonical_bridge import audit_packet_key_sets

        key_audit = audit_packet_key_sets(authority["keys"], tokens1)
        repeat_key_audit = audit_packet_key_sets(tokens1, tokens2)
        if not key_audit["pass"] or not repeat_key_audit["pass"]:
            source_checks.append(
                "current/persisted canonical key sets are not bijective"
            )
        current_key_sha1 = _key_digest(tokens1)
        current_key_sha2 = _key_digest(tokens2)
        if not (
            current_key_sha1
            == current_key_sha2
            == str(layout_sha)
            == authority["global_key_set_sha256"]
        ):
            source_checks.append("current layout and frozen key SHAs are not identical")
        current1_by_key = dict(zip(tokens1, values1, strict=True))
        current2_by_key = dict(zip(tokens2, values2, strict=True))
        ordered_keys = tuple(sorted(authority["values_by_key"]))
        key_sets_equal = set(ordered_keys) == set(current1_by_key) and set(
            ordered_keys
        ) == set(current2_by_key)
        if key_sets_equal:
            current_values1 = np.asarray(
                [current1_by_key[key] for key in ordered_keys],
                dtype=np.complex128,
            )
            current_values2 = np.asarray(
                [current2_by_key[key] for key in ordered_keys],
                dtype=np.complex128,
            )
            persisted_values = np.asarray(
                [authority["values_by_key"][key] for key in ordered_keys],
                dtype=np.complex128,
            )
        else:
            current_values1 = np.asarray([], dtype=np.complex128)
            current_values2 = np.asarray([], dtype=np.complex128)
            persisted_values = np.asarray([], dtype=np.complex128)
        current_old_relative = (
            _relative(current_values1, persisted_values)
            if persisted_values.size
            else float("inf")
        )
        current_repeat_relative = _relative(current_values1, current_values2)
        owner_source_norm1 = float(rhs1.norm())
        owner_source_norm2 = float(rhs2.norm())
        canonical_norm1 = float(np.linalg.norm(values1))
        canonical_norm2 = float(np.linalg.norm(values2))
        persisted_norm = float(np.linalg.norm(authority["values"]))
        owner_source_norm_repeat_relative = _relative(
            np.asarray([owner_source_norm1]), np.asarray([owner_source_norm2])
        )
        if persisted_values.size and rhs1 is not None:
            persisted_owner_roundtrip = canonical_to_current_roundtrip_relative(
                system, ordered_keys, persisted_values, rhs1
            )
        else:
            persisted_owner_roundtrip = float("inf")
        final_matrix_inventory = _validate_current_system(system)
        source_build_counts = dict(
            system.construction_inventory.get("source_build_counts", {})
        )
        if int(source_build_counts.get(TASK041_SOURCE_LABEL, 0)) != 2:
            source_checks.append("external_dtn_coupling source build count is not two")
        if any(
            int(count) != 0
            for label, count in source_build_counts.items()
            if label != TASK041_SOURCE_LABEL
        ):
            source_checks.append("unexpected non-external source build count")
        relative_checks = {
            "current_vs_persisted_relative": current_old_relative,
            "current_repeat_relative": current_repeat_relative,
            "current_first_canonical_to_owner_roundtrip_relative": float(roundtrip1),
            "current_second_canonical_to_owner_roundtrip_relative": float(roundtrip2),
            "persisted_to_current_owner_roundtrip_relative": float(
                persisted_owner_roundtrip
            ),
            "owner_source_norm_repeat_relative": owner_source_norm_repeat_relative,
        }
        hard_relative_names = {
            "current_repeat_relative",
            "current_first_canonical_to_owner_roundtrip_relative",
            "current_second_canonical_to_owner_roundtrip_relative",
            "owner_source_norm_repeat_relative",
        }
        relative_gates = {
            name: bool(
                np.isfinite(relative_checks[name])
                and relative_checks[name] <= TASK041_TOLERANCE
            )
            for name in hard_relative_names
        }
        hard_gate_pass = bool(
            not source_checks
            and key_audit["pass"]
            and repeat_key_audit["pass"]
            and np.isfinite(values1).all()
            and np.isfinite(values2).all()
            and np.isfinite(rhs1_owner_values).all()
            and np.isfinite(rhs2_owner_values).all()
            and owner_source_norm1 > 0.0
            and owner_source_norm2 > 0.0
            and canonical_norm1 > 0.0
            and canonical_norm2 > 0.0
            and source_audit1.get("surface_quadrature_degree")
            == TASK041_SURFACE_QUADRATURE_DEGREE
            and source_audit2.get("surface_quadrature_degree")
            == TASK041_SURFACE_QUADRATURE_DEGREE
            and relative_gates["current_repeat_relative"]
            and relative_gates["current_first_canonical_to_owner_roundtrip_relative"]
            and relative_gates["current_second_canonical_to_owner_roundtrip_relative"]
            and relative_gates["owner_source_norm_repeat_relative"]
        )
        result["source"] = {
            "source_build_count": 2,
            "first_audit": _jsonable(source_audit1),
            "second_audit": _jsonable(source_audit2),
            "first_packet_audit": _jsonable(packet_audit1),
            "second_packet_audit": _jsonable(packet_audit2),
            "layout_audit": _jsonable(layout_audit),
            "layout_key_set_sha256": str(layout_sha),
            "current_key_set_sha256": current_key_sha1,
            "current_second_key_set_sha256": current_key_sha2,
            "frozen_authority_key_set_sha256": authority["global_key_set_sha256"],
            "current_first_value_pair_digest_sha256": _pair_digest(tokens1, values1),
            "current_second_value_pair_digest_sha256": _pair_digest(tokens2, values2),
            "persisted_value_pair_digest_sha256": authority[
                "persisted_value_pair_digest_sha256"
            ],
            "key_audit": _jsonable(key_audit),
            "repeat_key_audit": _jsonable(repeat_key_audit),
            "orientation_phase": {
                "current_first": {
                    "orientation_state_histogram": orientation_hist1,
                    "phase_class_histogram": phase_hist1,
                    "phase_once_evidence": {
                        "canonical_reconstruction_calls": 1,
                        "physical_token_phase_used": True,
                        "roundtrip_gate_used": True,
                        "semantics": (
                            "one canonical reconstruction call + physical token phase + "
                            "roundtrip gate; control-flow evidence, not a backend counter"
                        ),
                    },
                    "orientation_applied_once": current_orientation1_ok,
                },
                "current_second": {
                    "orientation_state_histogram": orientation_hist2,
                    "phase_class_histogram": phase_hist2,
                    "phase_once_evidence": {
                        "canonical_reconstruction_calls": 1,
                        "physical_token_phase_used": True,
                        "roundtrip_gate_used": True,
                        "semantics": (
                            "one canonical reconstruction call + physical token phase + "
                            "roundtrip gate; control-flow evidence, not a backend counter"
                        ),
                    },
                    "orientation_applied_once": current_orientation2_ok,
                },
                "persisted_authority": authority["orientation_phase_audit"],
            },
            "norms": {
                "current_owner_source_first": owner_source_norm1,
                "current_owner_source_second": owner_source_norm2,
                "current_canonical_coefficient_first": canonical_norm1,
                "current_canonical_coefficient_second": canonical_norm2,
                "persisted_canonical_coefficient": persisted_norm,
                "persisted_authority_source_record": authority[
                    "persisted_source_record"
                ],
            },
            "relative": _jsonable(relative_checks),
            "relative_gate_1e-12": _jsonable(relative_gates),
            "diagnostic_relative": {
                "current_vs_persisted_relative": current_old_relative,
                "persisted_to_current_owner_roundtrip_relative": (
                    persisted_owner_roundtrip
                ),
            },
            "hard_gate_pass": hard_gate_pass,
            "final_matrix_inventory": final_matrix_inventory,
            "source_build_counts": source_build_counts,
            "mode_key_and_sign_checked": True,
            "surface_quadrature_degree": TASK041_SURFACE_QUADRATURE_DEGREE,
        }
        _write_marker(
            root,
            started,
            "source_repeat_ready",
            {"source_build_count": 2, "repeat_relative": current_repeat_relative},
            source_build_count=2,
        )
        reference_classification = classify_source_comparison(
            hard_gate_pass, current_old_relative
        )
        result["source"]["reference_classification"] = reference_classification
        if not hard_gate_pass:
            result["status"] = IMPLEMENTATION_FAILURE
            result["classification"] = IMPLEMENTATION_FAILURE
            raise SourceOnlyIdentityError(
                tuple(source_checks) or ("source hard gate failed",)
            )
        result["status"] = reference_classification
        result["classification"] = reference_classification
        _write_marker(
            root,
            started,
            "canonical_compare",
            {
                "reference_classification": reference_classification,
                "current_vs_persisted_relative": current_old_relative,
                "hard_gate_pass": hard_gate_pass,
            },
            source_build_count=2,
        )
    except SourceOnlyResourceStop as exc:
        result["status"] = RESOURCE_UNAVAILABLE
        result["classification"] = RESOURCE_UNAVAILABLE
        result["error"] = {"type": type(exc).__name__, "message": str(exc)}
    except Exception as exc:  # noqa: BLE001 - preserve failure evidence
        result["status"] = IMPLEMENTATION_FAILURE
        result["classification"] = IMPLEMENTATION_FAILURE
        result["error"] = {
            "type": type(exc).__name__,
            "message": str(exc),
            "failures": _jsonable(getattr(exc, "failures", ())),
        }
    finally:
        for name, vector in (("rhs1", rhs1), ("rhs2", rhs2)):
            if vector is not None:
                try:
                    vector.destroy()
                except Exception as exc:  # noqa: BLE001 - continue vector cleanup
                    cleanup_failures.append(f"{name}: {type(exc).__name__}: {exc}")
        result["lifecycle"]["source_vectors_destroyed"] = not cleanup_failures
        if system is not None:
            try:
                system.destroy()
            except Exception as exc:  # noqa: BLE001 - preserve cleanup evidence
                cleanup_failures.append(f"system: {type(exc).__name__}: {exc}")
            result["lifecycle"]["system_destroyed"] = bool(
                getattr(system, "_destroyed", False)
            )
            result["lifecycle"]["system_not_created_or_destroyed"] = bool(
                result["lifecycle"]["system_destroyed"]
            )
        result["lifecycle"]["cleanup_complete"] = bool(
            result["lifecycle"]["source_vectors_destroyed"]
            and (
                result["lifecycle"]["system_destroyed"]
                if system is not None
                else result["lifecycle"]["system_not_created_or_destroyed"]
            )
        )
        if cleanup_failures:
            result["cleanup_failures"] = cleanup_failures
            result["status"] = IMPLEMENTATION_FAILURE
            result["classification"] = IMPLEMENTATION_FAILURE
        result["wall_seconds"] = time.monotonic() - started
        try:
            _write_marker(
                root,
                started,
                "cleanup_complete",
                {
                    "status": result["status"],
                    "classification": result["classification"],
                    "lifecycle": result["lifecycle"],
                },
                source_build_count=int(result["source_build_count"]),
                enforce=False,
            )
        finally:
            (root / "source_only_summary.json").write_text(
                json.dumps(_jsonable(result), sort_keys=True, indent=2, allow_nan=False)
                + "\n",
                encoding="utf-8",
            )
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--authority-root", required=True)
    parser.add_argument("--authority-manifest-sha256", required=True)
    parser.add_argument("--run-directory", required=True)
    parser.add_argument("--source-sha", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    from mpi4py import MPI

    result = run_source_only(
        input_path=args.input,
        authority_root=args.authority_root,
        authority_manifest_sha256=args.authority_manifest_sha256,
        run_directory=args.run_directory,
        source_sha=args.source_sha,
        comm=MPI.COMM_WORLD,
    )
    if MPI.COMM_WORLD.rank == 0:
        print(json.dumps(_jsonable(result), sort_keys=True))
    return (
        0
        if result["classification"]
        in {
            SOURCE_SEMANTICS_UNCHANGED,
            REFERENCE_SOURCE_SEMANTICS_CHANGED,
        }
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
