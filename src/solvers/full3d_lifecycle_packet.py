"""Versioned rank-sharded NumPy arrays for pre-recovery checkpointing."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

import numpy as np
from mpi4py import MPI


PACKET_SCHEMA = "myfenics.full3d.pre_recovery_packet.v1"


def _safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(item) for item in value]
    if isinstance(value, np.ndarray):
        return _safe(value.tolist())
    if isinstance(value, np.generic):
        return _safe(value.item())
    if isinstance(value, complex):
        return [float(value.real), float(value.imag)]
    return value


def _json_bytes(value: Any) -> bytes:
    return json.dumps(_safe(value), sort_keys=True, separators=(",", ":")).encode()


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _ownership_is_contiguous(
    shards: list[Mapping[str, Any]], global_size: int | None = None
) -> bool:
    expected = 0
    for shard in sorted(
        shards, key=lambda item: (item["ownership_range"][0], item["rank"])
    ):
        start, end = (int(value) for value in shard["ownership_range"])
        if start != expected or end < start or end - start != int(shard["size"]):
            return False
        expected = end
    contiguous_size = sum(int(shard["size"]) for shard in shards)
    return expected == contiguous_size and (
        global_size is None or expected == int(global_size)
    )


def _atomic(path: Path, payload: bytes) -> str:
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    return _sha256(payload)


def write_packet(
    directory: Path,
    solution: np.ndarray,
    rhs: np.ndarray,
    *,
    identity: Mapping[str, Any],
    metadata: Mapping[str, Any],
    ownership_range: tuple[int, int] | np.ndarray,
    comm: MPI.Intracomm = MPI.COMM_WORLD,
) -> dict[str, Any]:
    """Write one local ``npz`` shard and a rank-zero manifest."""

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    solution = np.asarray(solution, dtype=np.complex128)
    rhs = np.asarray(rhs, dtype=np.complex128)
    if solution.ndim != 1 or rhs.shape != solution.shape:
        raise ValueError("pre-recovery packet arrays must be matching 1-D vectors")
    if not np.isfinite(solution).all() or not np.isfinite(rhs).all():
        raise ValueError("pre-recovery packet arrays must be finite")
    ownership = tuple(int(value) for value in np.asarray(ownership_range).tolist())
    if len(ownership) != 2 or ownership[1] - ownership[0] != solution.size:
        raise ValueError("pre-recovery ownership range does not match local arrays")
    shard_name = f"rank{comm.rank:04d}.npz"
    shard_path = directory / shard_name
    temporary = shard_path.with_name(f".{shard_name}.tmp")
    with temporary.open("wb") as stream:
        np.savez(stream, solution=solution, rhs=rhs)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, shard_path)
    shard_payload = shard_path.read_bytes()
    shard = {
        "rank": int(comm.rank),
        "path": shard_name,
        "sha256": _sha256(shard_payload),
        "size": int(solution.size),
        "ownership_range": list(ownership),
    }
    shards = comm.allgather(shard)
    ownership_pass = _ownership_is_contiguous(shards)
    identity_value = _safe(identity)
    identity_sha = _sha256(_json_bytes(identity_value))
    identity_hashes = comm.allgather(identity_sha)
    if len(set(identity_hashes)) != 1:
        raise ValueError("pre-recovery identity hash differs across ranks")
    manifest_path = directory / "manifest.json"
    local_pass = bool(
        np.isfinite(solution).all() and np.isfinite(rhs).all() and ownership_pass
    )
    if comm.rank == 0:
        manifest = {
            "schema": PACKET_SCHEMA,
            "identity": identity_value,
            "identity_sha256": identity_sha,
            "rank_count": int(comm.size),
            "global_size": int(max(item["ownership_range"][1] for item in shards)),
            "shards": sorted(shards, key=lambda item: item["rank"]),
            "metadata": _safe(metadata),
        }
        _atomic(manifest_path, _json_bytes(manifest) + b"\n")
    comm.barrier()
    return {
        "pass": bool(comm.allreduce(local_pass, op=MPI.LAND)),
        "schema": PACKET_SCHEMA,
        "manifest": str(manifest_path),
        "manifest_sha256": _sha256(manifest_path.read_bytes()),
        "identity_sha256": identity_sha,
    }


def load_packet(
    manifest_path: Path,
    *,
    identity: Mapping[str, Any] | None = None,
    expected_manifest_sha256: str | None = None,
    comm: MPI.Intracomm = MPI.COMM_WORLD,
) -> dict[str, Any]:
    """Verify and load the caller rank's arrays without solver dependencies."""

    manifest_path = Path(manifest_path)
    manifest_bytes_before = manifest_path.read_bytes()
    manifest_sha_before = _sha256(manifest_bytes_before)
    if (
        expected_manifest_sha256 is not None
        and manifest_sha_before != expected_manifest_sha256
    ):
        raise ValueError("pre-recovery manifest hash mismatch before read")
    manifest = json.loads(manifest_bytes_before)
    if manifest["schema"] != PACKET_SCHEMA:
        raise ValueError("unsupported pre-recovery packet schema")
    if _sha256(_json_bytes(manifest["identity"])) != manifest["identity_sha256"]:
        raise ValueError("pre-recovery identity hash mismatch")
    if identity is not None and _safe(identity) != manifest["identity"]:
        raise ValueError("pre-recovery identity mismatch")
    if int(manifest["rank_count"]) != int(comm.size):
        raise ValueError("pre-recovery packet rank-count mismatch")
    if not _ownership_is_contiguous(manifest["shards"], int(manifest["global_size"])):
        raise ValueError("pre-recovery ownership ranges are not contiguous")
    shard = next(item for item in manifest["shards"] if item["rank"] == comm.rank)
    shard_path = manifest_path.parent / shard["path"]
    payload = shard_path.read_bytes()
    if _sha256(payload) != shard["sha256"]:
        raise ValueError("pre-recovery shard hash mismatch")
    with np.load(shard_path, allow_pickle=False) as arrays:
        solution = np.asarray(arrays["solution"], dtype=np.complex128).copy()
        rhs = np.asarray(arrays["rhs"], dtype=np.complex128).copy()
    if solution.ndim != 1 or rhs.shape != solution.shape:
        raise ValueError("pre-recovery packet shape mismatch")
    ownership_range = tuple(int(value) for value in shard["ownership_range"])
    if (
        len(ownership_range) != 2
        or ownership_range[1] - ownership_range[0] != solution.size
    ):
        raise ValueError("pre-recovery ownership range mismatch")
    manifest_sha_after = _sha256(manifest_path.read_bytes())
    if manifest_sha_after != manifest_sha_before:
        raise ValueError("pre-recovery manifest changed during read")
    return {
        "schema": manifest["schema"],
        "identity": manifest["identity"],
        "identity_sha256": manifest["identity_sha256"],
        "metadata": manifest["metadata"],
        "global_size": int(manifest["global_size"]),
        "solution": solution,
        "rhs": rhs,
        "ownership_range": ownership_range,
        "manifest_sha256": manifest_sha_after,
    }
