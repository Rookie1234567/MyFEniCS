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


def _write_packet_with_collective_writer_errors(
    directory: Path,
    solution: np.ndarray,
    rhs: np.ndarray,
    *,
    identity: Mapping[str, Any],
    metadata: Mapping[str, Any],
    ownership_range: tuple[int, int] | np.ndarray,
    comm: MPI.Intracomm,
    allow_nonfinite_diagnostic: bool,
) -> dict[str, Any]:
    """Task42-safe path: synchronize local filesystem errors before collectives."""

    shard_name = f"rank{comm.rank:04d}.npz"
    shard_path = directory / shard_name
    manifest_path = directory / "manifest.json"
    local_error = None
    local_finite = False
    shard = None
    identity_value = None
    identity_sha = None
    try:
        directory.mkdir(parents=True, exist_ok=True)
        if shard_path.exists() or manifest_path.exists():
            raise FileExistsError("Task42 pre-recovery packet path already exists")
        solution = np.asarray(solution, dtype=np.complex128)
        rhs = np.asarray(rhs, dtype=np.complex128)
        if solution.ndim != 1 or rhs.shape != solution.shape:
            raise ValueError("pre-recovery packet arrays must be matching 1-D vectors")
        local_finite = bool(np.isfinite(solution).all() and np.isfinite(rhs).all())
        if not local_finite and not allow_nonfinite_diagnostic:
            raise ValueError("pre-recovery packet arrays must be finite")
        ownership = tuple(int(value) for value in np.asarray(ownership_range).tolist())
        if len(ownership) != 2 or ownership[1] - ownership[0] != solution.size:
            raise ValueError("pre-recovery ownership range does not match local arrays")
        identity_value = _safe(identity)
        identity_sha = _sha256(_json_bytes(identity_value))
        _json_bytes(metadata)
        temporary = shard_path.with_name(f".{shard_name}.tmp")
        with temporary.open("xb") as stream:
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
    except BaseException as exc:  # noqa: BLE001 - local shard I/O is gathered at the next safe point
        local_error = f"{type(exc).__name__}: {exc}"
    preflight_rows = comm.allgather(
        {
            "rank": int(comm.rank),
            "error": local_error,
            "shard": shard,
            "identity_sha256": identity_sha,
            "local_finite": local_finite,
        }
    )
    errors = [
        f"rank_{row['rank']}_packet_preflight_failed:{row['error']}"
        for row in preflight_rows
        if row.get("error") is not None
    ]
    if errors:
        return {
            "pass": False,
            "schema": PACKET_SCHEMA,
            "manifest": str(manifest_path),
            "manifest_sha256": None,
            "identity_sha256": None,
            "errors": errors,
        }
    shards = [row["shard"] for row in preflight_rows]
    identity_hashes = [row["identity_sha256"] for row in preflight_rows]
    if len(set(identity_hashes)) != 1:
        return {
            "pass": False,
            "schema": PACKET_SCHEMA,
            "manifest": str(manifest_path),
            "manifest_sha256": None,
            "identity_sha256": None,
            "errors": ["pre-recovery identity hash differs across ranks"],
        }
    ownership_pass = _ownership_is_contiguous(shards)
    global_finite = bool(comm.allreduce(local_finite, op=MPI.LAND))
    manifest_error = None
    manifest_sha = None
    if comm.rank == 0:
        try:
            manifest = {
                "schema": PACKET_SCHEMA,
                "identity": identity_value,
                "identity_sha256": identity_hashes[0],
                "rank_count": int(comm.size),
                "global_size": int(
                    max(item["ownership_range"][1] for item in shards)
                ),
                "shards": sorted(shards, key=lambda item: item["rank"]),
                "metadata": _safe(metadata),
                "diagnostic_nonfinite": bool(
                    allow_nonfinite_diagnostic and not global_finite
                ),
            }
            manifest_sha = _atomic(manifest_path, _json_bytes(manifest) + b"\n")
        except BaseException as exc:  # noqa: BLE001 - local rank-0 manifest I/O is broadcast below
            manifest_error = f"{type(exc).__name__}: {exc}"
    manifest_status = comm.bcast(
        {"error": manifest_error, "sha256": manifest_sha} if comm.rank == 0 else None,
        root=0,
    )
    if not isinstance(manifest_status, dict) or manifest_status.get("error"):
        return {
            "pass": False,
            "schema": PACKET_SCHEMA,
            "manifest": str(manifest_path),
            "manifest_sha256": None,
            "identity_sha256": identity_hashes[0],
            "errors": [
                "pre-recovery manifest write failed: "
                + str(None if not isinstance(manifest_status, dict) else manifest_status.get("error"))
            ],
        }
    comm.barrier()
    try:
        manifest_bytes = manifest_path.read_bytes()
        local_manifest_sha = _sha256(manifest_bytes)
        read_error = None
    except BaseException as exc:  # noqa: BLE001 - local manifest read is gathered at the next safe point
        local_manifest_sha = None
        read_error = f"{type(exc).__name__}: {exc}"
    readbacks = comm.allgather(
        {"rank": int(comm.rank), "sha256": local_manifest_sha, "error": read_error}
    )
    read_errors = [
        f"rank_{row['rank']}_manifest_read_failed:{row['error']}"
        for row in readbacks
        if row.get("error") is not None
    ]
    digests = {row.get("sha256") for row in readbacks}
    if len(digests) != 1:
        read_errors.append("pre-recovery manifest bytes differ across ranks")
    return {
        "pass": bool(
            not read_errors
            and ownership_pass
            and all(bool(row["local_finite"]) for row in preflight_rows)
        ),
        "schema": PACKET_SCHEMA,
        "manifest": str(manifest_path),
        "manifest_sha256": next(iter(digests)) if len(digests) == 1 else None,
        "identity_sha256": identity_hashes[0],
        "errors": read_errors,
    }


def write_packet(
    directory: Path,
    solution: np.ndarray,
    rhs: np.ndarray,
    *,
    identity: Mapping[str, Any],
    metadata: Mapping[str, Any],
    ownership_range: tuple[int, int] | np.ndarray,
    comm: MPI.Intracomm = MPI.COMM_WORLD,
    allow_nonfinite_diagnostic: bool = False,
    collective_writer_errors: bool = False,
) -> dict[str, Any]:
    """Write one local ``npz`` shard and a rank-zero manifest.

    Non-finite arrays remain rejected by default.  The explicit diagnostic
    opt-in preserves a failed solve's owner shard for post-mortem inspection;
    such a packet is never reported as a qualified recovery packet.
    """

    if type(collective_writer_errors) is not bool:
        raise TypeError("collective_writer_errors must be an exact bool")
    directory = Path(directory)
    if collective_writer_errors:
        return _write_packet_with_collective_writer_errors(
            directory,
            solution,
            rhs,
            identity=identity,
            metadata=metadata,
            ownership_range=ownership_range,
            comm=comm,
            allow_nonfinite_diagnostic=allow_nonfinite_diagnostic,
        )
    directory.mkdir(parents=True, exist_ok=True)
    solution = np.asarray(solution, dtype=np.complex128)
    rhs = np.asarray(rhs, dtype=np.complex128)
    if solution.ndim != 1 or rhs.shape != solution.shape:
        raise ValueError("pre-recovery packet arrays must be matching 1-D vectors")
    local_finite = bool(np.isfinite(solution).all() and np.isfinite(rhs).all())
    if not local_finite and not allow_nonfinite_diagnostic:
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
    global_finite = bool(comm.allreduce(local_finite, op=MPI.LAND))
    identity_value = _safe(identity)
    identity_sha = _sha256(_json_bytes(identity_value))
    identity_hashes = comm.allgather(identity_sha)
    if len(set(identity_hashes)) != 1:
        raise ValueError("pre-recovery identity hash differs across ranks")
    manifest_path = directory / "manifest.json"
    local_pass = bool(local_finite and ownership_pass)
    if comm.rank == 0:
        manifest = {
            "schema": PACKET_SCHEMA,
            "identity": identity_value,
            "identity_sha256": identity_sha,
            "rank_count": int(comm.size),
            "global_size": int(max(item["ownership_range"][1] for item in shards)),
            "shards": sorted(shards, key=lambda item: item["rank"]),
            "metadata": _safe(metadata),
            "diagnostic_nonfinite": bool(allow_nonfinite_diagnostic and not global_finite),
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
