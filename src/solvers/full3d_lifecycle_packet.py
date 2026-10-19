"""Versioned rank-sharded NumPy arrays for pre-recovery checkpointing."""

from __future__ import annotations

import hashlib
import json
import os
import zipfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

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


def verify_task42_recovery_archive(
    manifest_path: Path,
    *,
    expected_manifest_sha256: str,
    expected_identity: Mapping[str, Any] | Sequence[Mapping[str, Any]],
    allowed_source_sha: str | None = None,
    allowed_source_shas: Sequence[str] | None = None,
    expected_mpi_size: int,
) -> dict[str, Any]:
    """Verify the archived RUN envelope and every shard before recovery setup.

    The Task42 packet did not persist a trace-map hash. This function validates
    the identities it did persist and records that missing field explicitly;
    it never treats the archived residual scalar as a current residual check.
    """

    manifest_path = Path(manifest_path).resolve(strict=True)
    if (
        manifest_path.name != "manifest.json"
        or manifest_path.parent.name != "pre_recovery_packet"
        or manifest_path.parent.parent.name != "numerical_output"
    ):
        raise ValueError(
            "Task42 recovery packet must be under RUN/numerical_output/pre_recovery_packet"
        )
    packet_directory = manifest_path.parent
    run_root = manifest_path.parents[2]
    manifest_bytes = manifest_path.read_bytes()
    manifest_sha = _sha256(manifest_bytes)
    if manifest_sha != expected_manifest_sha256:
        raise ValueError("Task42 recovery packet manifest SHA mismatch")
    manifest = json.loads(manifest_bytes)
    if not isinstance(manifest, dict) or manifest.get("schema") != PACKET_SCHEMA:
        raise ValueError("Task42 recovery packet schema mismatch")
    identity = manifest.get("identity")
    if not isinstance(identity, Mapping):
        raise ValueError("Task42 recovery packet identity is missing")  # noqa: TRY004
    if _sha256(_json_bytes(identity)) != manifest.get("identity_sha256"):
        raise ValueError("Task42 recovery packet identity hash mismatch")
    expected_identities = (
        [expected_identity]
        if isinstance(expected_identity, Mapping)
        else list(expected_identity)
    )
    if not expected_identities or any(
        not isinstance(candidate, Mapping) for candidate in expected_identities
    ):
        raise ValueError("Task42 recovery expected identity candidates are invalid")
    if not any(_safe(candidate) == identity for candidate in expected_identities):
        raise ValueError("Task42 recovery packet resolved identity mismatch")
    allowed_sources = set(allowed_source_shas or ())
    if allowed_source_sha is not None:
        allowed_sources.add(allowed_source_sha)
    if not allowed_sources or any(
        not isinstance(value, str)
        or len(value) != 40
        or any(character not in "0123456789abcdef" for character in value)
        for value in allowed_sources
    ):
        raise ValueError("Task42 recovery allowed source SHA set is invalid")
    archive_source_sha = identity.get("source_sha")
    if archive_source_sha not in allowed_sources:
        raise ValueError("Task42 recovery packet source SHA is not qualified")
    if type(expected_mpi_size) is not int or expected_mpi_size <= 0:
        raise ValueError("Task42 recovery MPI size must be a positive integer")
    if manifest.get("rank_count") != expected_mpi_size:
        raise ValueError("Task42 recovery packet rank count mismatch")
    shards = manifest.get("shards")
    if not isinstance(shards, list) or len(shards) != expected_mpi_size:
        raise ValueError("Task42 recovery packet shard inventory is incomplete")
    if not _ownership_is_contiguous(shards, int(manifest.get("global_size", -1))):
        raise ValueError("Task42 recovery packet ownership is not contiguous")
    ranks = [row.get("rank") for row in shards if isinstance(row, Mapping)]
    if ranks != list(range(expected_mpi_size)):
        raise ValueError("Task42 recovery packet rank shards are not in rank order")
    shard_hashes: dict[str, str] = {}
    for shard in shards:
        relative = shard.get("path")
        if (
            not isinstance(relative, str)
            or not relative
            or Path(relative).name != relative
        ):
            raise ValueError("Task42 recovery shard path is not a packet-local filename")
        shard_path = packet_directory / relative
        if shard_path.resolve(strict=True).parent != packet_directory:
            raise ValueError("Task42 recovery shard escaped its packet directory")
        digest = _sha256(shard_path.read_bytes())
        if digest != shard.get("sha256"):
            raise ValueError(f"Task42 recovery shard SHA mismatch: {relative}")
        try:
            with np.load(shard_path, allow_pickle=False) as arrays:
                if set(arrays.files) != {"solution", "rhs"}:
                    raise ValueError(
                        f"Task42 recovery shard fields mismatch: {relative}"
                    )
                solution = arrays["solution"]
                rhs = arrays["rhs"]
                expected_size = int(shard["ownership_range"][1]) - int(
                    shard["ownership_range"][0]
                )
                if (
                    solution.ndim != 1
                    or rhs.ndim != 1
                    or solution.shape != rhs.shape
                    or solution.size != expected_size
                    or type(shard.get("size")) is not int
                    or shard["size"] != expected_size
                    or solution.dtype != np.dtype(np.complex128)
                    or rhs.dtype != np.dtype(np.complex128)
                    or not np.isfinite(solution).all()
                    or not np.isfinite(rhs).all()
                ):
                    raise ValueError(
                        f"Task42 recovery shard array schema mismatch: {relative}"
                    )
        except (OSError, KeyError, ValueError, zipfile.BadZipFile) as exc:
            if isinstance(exc, ValueError) and str(exc).startswith(
                "Task42 recovery shard"
            ):
                raise
            raise ValueError(
                f"Task42 recovery shard cannot be read: {relative}: {exc}"
            ) from exc
        shard_hashes[relative] = digest

    def read_run_file(name: str) -> bytes:
        try:
            return (run_root / name).read_bytes()
        except OSError as exc:
            raise ValueError(f"Task42 recovery RUN file {name} is unreadable: {exc}") from exc

    run_manifest_bytes = read_run_file("run_manifest.json")
    resolved_bytes = read_run_file("resolved_config.json")
    input_bytes = read_run_file("input_original.dat")
    input_sha_text = read_run_file("input_sha256.txt").decode("ascii").strip()
    physical_sha_text = read_run_file("physical_model_sha256.txt").decode("ascii").strip()
    source_sha_text = read_run_file("source_sha.txt").decode("ascii").strip()
    run_manifest = json.loads(run_manifest_bytes)
    resolved = json.loads(resolved_bytes)
    if not isinstance(run_manifest, dict) or not isinstance(resolved, dict):
        raise ValueError("Task42 recovery RUN metadata must be JSON objects")  # noqa: TRY004
    resolved_method = resolved.get("method")
    resolved_method_kind = (
        resolved_method.get("kind") if isinstance(resolved_method, Mapping) else None
    )
    input_sha = _sha256(input_bytes)
    resolved_sha = _sha256(resolved_bytes)
    if input_sha != identity.get("input_sha256") or input_sha_text != input_sha:
        raise ValueError("Task42 recovery original input SHA mismatch")
    if resolved_sha != identity.get("resolved_config_sha256"):
        raise ValueError("Task42 recovery resolved-config SHA mismatch")
    if physical_sha_text != identity.get("physical_model_sha256"):
        raise ValueError("Task42 recovery physical-model SHA mismatch")
    if source_sha_text != archive_source_sha:
        raise ValueError("Task42 recovery source_sha.txt mismatch")
    if (
        run_manifest.get("source_sha") != archive_source_sha
        or run_manifest.get("resolved_config_sha256") != resolved_sha
        or run_manifest.get("input_sha256") != input_sha
        or run_manifest.get("physical_model_sha256") != physical_sha_text
        or run_manifest.get("model_id") != identity.get("model_id")
        or run_manifest.get("run_id") != identity.get("run_id")
        or run_manifest.get("comparison_group") != identity.get("comparison_group")
        or run_manifest.get("method") != identity.get("method")
        or run_manifest.get("mpi_size") != expected_mpi_size
        or run_manifest.get("output_directory") != str(run_root)
        or run_manifest.get("numerical_output_directory")
        != str(run_root / "numerical_output")
    ):
        raise ValueError("Task42 recovery RUN manifest does not bind the packet identity")
    provenance = resolved.get("provenance")
    if not isinstance(provenance, Mapping) or (
        provenance.get("input_sha256") != input_sha
        or provenance.get("physical_model_sha256") != physical_sha_text
    ):
        raise ValueError("Task42 recovery resolved provenance mismatch")
    for key in (
        "model_id",
        "run_id",
        "comparison_group",
        "dimension",
        "geometry",
        "materials",
        "discretization",
    ):
        if resolved.get(key) != identity.get(key):
            raise ValueError(f"Task42 recovery resolved {key} mismatch")
    if resolved_method_kind != identity.get("method"):
        raise ValueError("Task42 recovery resolved method kind mismatch")
    resolved_incidence = resolved.get("incidence")
    resolved_execution = resolved.get("execution")
    if (
        not isinstance(resolved_incidence, Mapping)
        or not isinstance(resolved_execution, Mapping)
        or resolved_incidence.get("wavelength_nm") != identity.get("wavelength_nm")
        or resolved_incidence.get("grazing_angle_deg")
        != identity.get("grazing_angle_deg")
        or resolved_incidence.get("azimuth_deg") != identity.get("azimuth_deg")
        or resolved_incidence.get("polarization") != identity.get("polarization")
        or resolved_execution.get("mpi_size") != expected_mpi_size
    ):
        raise ValueError("Task42 recovery incidence or execution identity mismatch")
    metadata = manifest.get("metadata")
    if not isinstance(metadata, Mapping):
        raise ValueError("Task42 recovery packet metadata is missing")  # noqa: TRY004
    external_keys = metadata.get("external_keys")
    if not isinstance(external_keys, list) or not external_keys:
        raise ValueError("Task42 recovery packet external keys are missing")
    derived = resolved.get("derived")
    external_inventory = (
        derived.get("external_mode_inventory") if isinstance(derived, Mapping) else None
    )
    resolved_external_keys = (
        external_inventory.get("keys")
        if isinstance(external_inventory, Mapping)
        else None
    )
    if not isinstance(resolved_external_keys, list):
        raise ValueError(  # noqa: TRY004 - missing persisted inventory is an input-value refusal
            "Task42 resolved RUN external-key inventory is missing"
        )
    packet_key_ids = [_json_bytes(key) for key in external_keys]
    resolved_key_ids = [_json_bytes(key) for key in resolved_external_keys]
    if (
        len(set(packet_key_ids)) != len(packet_key_ids)
        or len(set(resolved_key_ids)) != len(resolved_key_ids)
        or set(packet_key_ids) != set(resolved_key_ids)
    ):
        raise ValueError(
            "Task42 packet external keys do not match the resolved RUN inventory"
        )
    if metadata.get("task42_direct_original_residual_pass") is not True:
        raise ValueError("Task42 archived packet did not record a passed original solve")
    return {
        "manifest": manifest,
        "manifest_sha256": manifest_sha,
        "identity": dict(identity),
        "run_root": str(run_root),
        "archive_source_sha": source_sha_text,
        "shard_sha256_by_path": shard_hashes,
        "historical_trace_map_sha256": "not_saved_in_original_packet",
        "historical_residual_used_as_recovery_gate": False,
    }
