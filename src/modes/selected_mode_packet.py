"""Generic hash-bound, rank-sharded selected-mode packet v1.

The packet stores only mode-major selected right/left arrays and authority
metadata. The writer streams existing selected vectors into four independent
``.npy`` files; the loader returns read-only mmap arrays and never imports a
solver or QEP implementation.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Mapping

import numpy as np
from mpi4py import MPI


MODE_PACKET_SCHEMA = "myfenics.modes.selected_mode_packet.v1"
BRANCH_NAMES = ("positive", "negative")
_IDENTITY_KEYS = (
    "source_sha",
    "input_sha256",
    "resolved_sha256",
    "physical_sha256",
    "mesh",
    "mode_count",
    "external_keys",
)
_METADATA_KEYS = (
    "trace_mapping",
    "canonical_mapping",
    "gram_authority",
    "qep_diagnostics",
    "selection_diagnostics",
)


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.ndarray):
        if np.iscomplexobj(value):
            return [[float(item.real), float(item.imag)] for item in value.flat]
        return [_json_safe(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        return _json_safe(value.item())
    if isinstance(value, complex):
        return [float(value.real), float(value.imag)]
    return value


def _json_bytes(value: Any) -> bytes:
    return json.dumps(_json_safe(value), sort_keys=True, separators=(",", ":")).encode()


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_bytes(path: Path, payload: bytes) -> str:
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    return _sha256(payload)


def _finite_in_chunks(array: np.ndarray, *, elements_per_chunk: int = 65536) -> bool:
    flat = array.reshape(-1)
    for start in range(0, flat.size, elements_per_chunk):
        stop = min(start + elements_per_chunk, flat.size)
        if not bool(np.isfinite(flat[start:stop]).all()):
            return False
    return True


def _ownership_is_contiguous(
    shards: list[Mapping[str, Any]], global_size: int | None = None
) -> bool:
    expected = 0
    for shard in sorted(
        shards, key=lambda item: (item["ownership_range"][0], item["rank"])
    ):
        start, end = (int(value) for value in shard["ownership_range"])
        rows = int(shard["rows"])
        if start != expected or end < start or end - start != rows:
            return False
        expected = end
    return global_size is None or expected == int(global_size)


def _validate_identity(identity: Mapping[str, Any]) -> tuple[dict[str, Any], int]:
    value = _json_safe(identity)
    missing = [key for key in _IDENTITY_KEYS if key not in value]
    if missing:
        raise ValueError(f"selected-mode packet identity missing: {missing}")
    mode_count = int(value["mode_count"])
    if mode_count <= 0:
        raise ValueError("selected-mode packet requires a positive mode count")
    return value, mode_count


def _validate_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    value = _json_safe(metadata)
    missing = [key for key in _METADATA_KEYS if key not in value]
    if missing:
        raise ValueError(f"selected-mode packet metadata missing: {missing}")
    return value


def _complex_beta(value: Any, mode_count: int) -> np.ndarray:
    pairs = np.asarray(value, dtype=float)
    if pairs.shape != (mode_count, 2):
        raise ValueError("selected-mode beta metadata has the wrong mode count")
    return np.asarray(pairs[:, 0] + 1j * pairs[:, 1], dtype=np.complex128)


def _basis_branch_descriptor(
    basis: Any,
    *,
    branch: str,
    sign: int,
    mode_count: int,
) -> tuple[dict[str, Any], list[Any], list[Any], tuple[int, int]]:
    modes = list(basis.modes)
    if len(modes) != mode_count:
        raise ValueError("selected-mode basis mode count differs from identity")
    right_vectors = [mode.right.right_full for mode in modes]
    left_vectors = [mode.left_full for mode in modes]
    ownership = tuple(int(value) for value in right_vectors[0].getOwnershipRange())
    if ownership[1] <= ownership[0]:
        raise ValueError("selected-mode basis ownership is empty")
    for right_vector, left_vector in zip(right_vectors, left_vectors):
        if tuple(int(value) for value in right_vector.getOwnershipRange()) != ownership:
            raise ValueError("selected-mode right ownership differs across modes")
        if tuple(int(value) for value in left_vector.getOwnershipRange()) != ownership:
            raise ValueError("selected-mode left ownership differs from right")
    directions = {str(mode.direction) for mode in modes}
    if len(directions) != 1:
        raise ValueError("selected-mode branch direction differs across modes")
    group_ids = [None] * mode_count
    for group_id, group in enumerate(basis.groups):
        for index in group.indices:
            group_ids[int(index)] = int(group_id)
    if any(group_id is None for group_id in group_ids):
        raise ValueError("selected-mode basis has an ungrouped selected mode")
    betas = np.asarray([mode.beta for mode in modes], dtype=np.complex128)
    if not np.isfinite(betas).all():
        raise ValueError("selected-mode basis beta values must be finite")
    descriptor = {
        "branch": branch,
        "direction": directions.pop(),
        "sign": int(sign),
        "beta": _json_safe(betas),
        "mode_keys": [
            {"kind": mode.kind, "direction": mode.direction} for mode in modes
        ],
        "groups": group_ids,
        "passive_branch_valid": [bool(mode.passive_branch_valid) for mode in modes],
    }
    return descriptor, right_vectors, left_vectors, ownership


def _finalize_packet_write(
    directory: Path,
    *,
    started: float,
    scope: str,
    identity_value: Mapping[str, Any],
    identity_sha: str,
    selection: Mapping[str, Any],
    selection_sha: str,
    metadata_value: Mapping[str, Any],
    metadata_sha: str,
    mode_count: int,
    rows: int,
    ownership: tuple[int, int],
    shard_files: Mapping[str, Mapping[str, Any]],
    comm: MPI.Intracomm,
) -> dict[str, Any]:
    shards = comm.allgather(
        {
            "rank": int(comm.rank),
            "rows": int(rows),
            "ownership_range": list(ownership),
            "files": dict(shard_files),
        }
    )
    if not _ownership_is_contiguous(shards):
        raise ValueError("selected-mode ownership ranges are not contiguous")
    global_size = int(max(item["ownership_range"][1] for item in shards))
    manifest_path = directory / "manifest.json"
    if comm.rank == 0:
        manifest = {
            "schema": MODE_PACKET_SCHEMA,
            "scope": scope,
            "identity": identity_value,
            "identity_sha256": identity_sha,
            "selection": selection,
            "selection_sha256": selection_sha,
            "metadata": metadata_value,
            "metadata_sha256": metadata_sha,
            "mode_count": mode_count,
            "rank_count": int(comm.size),
            "global_size": global_size,
            "shards": sorted(shards, key=lambda item: item["rank"]),
            "qep_workspace_persisted": False,
            "consumer_qep_required": False,
        }
        _atomic_bytes(manifest_path, _json_bytes(manifest) + b"\n")
    comm.barrier()
    elapsed = float(comm.allreduce(time.perf_counter() - started, op=MPI.MAX))
    manifest_sha = _sha256_file(manifest_path)
    return {
        "pass": True,
        "schema": MODE_PACKET_SCHEMA,
        "scope": scope,
        "manifest": str(manifest_path),
        "manifest_sha256": manifest_sha,
        "identity_sha256": identity_sha,
        "selection_sha256": selection_sha,
        "global_size": global_size,
        "ownership_range": ownership,
        "write_seconds_max_rank": elapsed,
        "consumer_qep_required": False,
    }


def write_selected_mode_packet(
    directory: Path,
    bases: Mapping[str, Any],
    *,
    identity: Mapping[str, Any],
    metadata: Mapping[str, Any],
    scope: str | None = None,
    comm: MPI.Intracomm = MPI.COMM_WORLD,
) -> dict[str, Any]:
    """Stream two selected bases to four independent mode-major ``.npy`` files."""

    if not isinstance(scope, str) or not scope:
        raise ValueError("selected-mode packet requires an explicit scope")
    started = time.perf_counter()
    identity_value, mode_count = _validate_identity(identity)
    metadata_value = _validate_metadata(metadata)
    normalized = {
        branch: _basis_branch_descriptor(
            bases[branch], branch=branch, sign=sign, mode_count=mode_count
        )
        for branch, sign in (("positive", 1), ("negative", -1))
    }
    ownership = normalized["positive"][3]
    rows = ownership[1] - ownership[0]
    if normalized["negative"][3] != ownership:
        raise ValueError("selected-mode basis branch ownership differs")
    selection = {name: item[0] for name, item in normalized.items()}
    identity_sha = _sha256(_json_bytes(identity_value))
    selection_sha = _sha256(_json_bytes(selection))
    metadata_sha = _sha256(_json_bytes(metadata_value))
    if len(set(comm.allgather(identity_sha))) != 1:
        raise ValueError("selected-mode identity hash differs across ranks")
    if len(set(comm.allgather(selection_sha))) != 1:
        raise ValueError("selected-mode selection hash differs across ranks")
    if len(set(comm.allgather(metadata_sha))) != 1:
        raise ValueError("selected-mode metadata hash differs across ranks")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    shard_files: dict[str, dict[str, Any]] = {}
    for branch_name, array_name, vectors in (
        ("positive", "right", normalized["positive"][1]),
        ("positive", "left", normalized["positive"][2]),
        ("negative", "right", normalized["negative"][1]),
        ("negative", "left", normalized["negative"][2]),
    ):
        file_key = f"{branch_name}_{array_name}"
        file_path = directory / f"rank{comm.rank:04d}_{file_key}.npy"
        mapped = np.lib.format.open_memmap(
            file_path, mode="w+", dtype=np.complex128, shape=(mode_count, rows)
        )
        try:
            for index, vector in enumerate(vectors):
                values = np.asarray(vector.getArray(readonly=True), dtype=np.complex128)
                if values.shape != (rows,) or not _finite_in_chunks(values):
                    raise ValueError(
                        "selected-mode basis vector shape or finite check failed"
                    )
                mapped[index, :] = values
            mapped.flush()
        finally:
            del mapped
        descriptor_fd = os.open(file_path, os.O_RDONLY)
        try:
            os.fsync(descriptor_fd)
        finally:
            os.close(descriptor_fd)
        shard_files[file_key] = {
            "path": file_path.name,
            "sha256": _sha256_file(file_path),
            "shape": [mode_count, rows],
            "dtype": "complex128",
            "layout": "mode_major",
        }
    return _finalize_packet_write(
        directory,
        started=started,
        scope=scope,
        identity_value=identity_value,
        identity_sha=identity_sha,
        selection=selection,
        selection_sha=selection_sha,
        metadata_value=metadata_value,
        metadata_sha=metadata_sha,
        mode_count=mode_count,
        rows=rows,
        ownership=ownership,
        shard_files=shard_files,
        comm=comm,
    )


def load_selected_mode_packet(
    manifest_path: Path,
    *,
    identity: Mapping[str, Any] | None = None,
    expected_manifest_sha256: str | None = None,
    scope: str | None = None,
    comm: MPI.Intracomm = MPI.COMM_WORLD,
) -> dict[str, Any]:
    """Verify and load mode-major arrays as read-only mmap-backed arrays."""

    if not isinstance(scope, str) or not scope:
        raise ValueError("selected-mode consumer requires an explicit scope")
    started = time.perf_counter()
    manifest_path = Path(manifest_path)
    manifest_bytes = manifest_path.read_bytes()
    manifest_sha = _sha256(manifest_bytes)
    if (
        expected_manifest_sha256 is not None
        and manifest_sha != expected_manifest_sha256
    ):
        raise ValueError("selected-mode manifest hash mismatch before read")
    manifest = json.loads(manifest_bytes)
    if manifest["schema"] != MODE_PACKET_SCHEMA or manifest["scope"] != scope:
        raise ValueError("unsupported selected-mode packet schema or scope")
    mode_count = int(manifest["mode_count"])
    if mode_count <= 0 or int(manifest["rank_count"]) != int(comm.size):
        raise ValueError("selected-mode packet mode/rank count mismatch")
    for field in ("identity", "selection", "metadata"):
        if _sha256(_json_bytes(manifest[field])) != manifest[f"{field}_sha256"]:
            raise ValueError(f"selected-mode {field} hash mismatch")
    manifest_identity, identity_mode_count = _validate_identity(manifest["identity"])
    if identity_mode_count != mode_count or manifest_identity != manifest["identity"]:
        raise ValueError("selected-mode identity/mode count mismatch")
    if identity is not None and _validate_identity(identity) != (
        manifest["identity"],
        mode_count,
    ):
        raise ValueError("selected-mode identity mismatch")
    selection = manifest["selection"]
    if set(selection) != set(BRANCH_NAMES):
        raise ValueError("selected-mode selection branch set mismatch")
    for branch_name, descriptor in selection.items():
        if descriptor.get("branch") != branch_name:
            raise ValueError("selected-mode mapping key and branch descriptor disagree")
        if len(descriptor["passive_branch_valid"]) != mode_count:
            raise ValueError("selected-mode passive-branch metadata mismatch")
    shards = manifest["shards"]
    if not _ownership_is_contiguous(shards, int(manifest["global_size"])):
        raise ValueError("selected-mode ownership ranges are not contiguous")
    shard = next(item for item in shards if int(item["rank"]) == int(comm.rank))
    expected_files = {
        "positive_right",
        "positive_left",
        "negative_right",
        "negative_left",
    }
    if set(shard["files"]) != expected_files:
        raise ValueError("selected-mode shard file set mismatch")
    loaded: dict[str, np.ndarray] = {}
    rows = int(shard["rows"])
    for file_key, file_info in shard["files"].items():
        if file_info["layout"] != "mode_major":
            raise ValueError("selected-mode shard layout mismatch")
        file_path = manifest_path.parent / file_info["path"]
        if _sha256_file(file_path) != file_info["sha256"]:
            raise ValueError("selected-mode shard hash mismatch")
        if file_info["dtype"] != "complex128":
            raise ValueError("selected-mode shard dtype mismatch")
        array = np.load(file_path, mmap_mode="r", allow_pickle=False)
        if list(array.shape) != [mode_count, rows] or list(array.shape) != list(
            file_info["shape"]
        ):
            raise ValueError("selected-mode shard shape mismatch")
        if not _finite_in_chunks(array):
            raise ValueError("selected-mode shard finite-value check failed")
        loaded[file_key] = array
    if _sha256_file(manifest_path) != manifest_sha:
        raise ValueError("selected-mode manifest changed during read")
    elapsed = float(comm.allreduce(time.perf_counter() - started, op=MPI.MAX))
    return {
        "schema": manifest["schema"],
        "scope": manifest["scope"],
        "identity": manifest["identity"],
        "identity_sha256": manifest["identity_sha256"],
        "selection": {
            name: {
                **descriptor,
                "beta": _complex_beta(descriptor["beta"], mode_count),
            }
            for name, descriptor in selection.items()
        },
        "metadata": manifest["metadata"],
        "mode_count": mode_count,
        "global_size": int(manifest["global_size"]),
        "ownership_range": tuple(int(value) for value in shard["ownership_range"]),
        "positive": {
            "right_full": loaded["positive_right"],
            "left_full": loaded["positive_left"],
        },
        "negative": {
            "right_full": loaded["negative_right"],
            "left_full": loaded["negative_left"],
        },
        "manifest_sha256": manifest_sha,
        "read_seconds_max_rank": elapsed,
        "consumer_qep_required": bool(manifest["consumer_qep_required"]),
    }
