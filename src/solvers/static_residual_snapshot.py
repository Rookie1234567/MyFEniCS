"""Small, opt-in carrier for Task037 active-row true residual snapshots."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, cast

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

RESIDUAL_SNAPSHOT_SCHEMA = "task037.extra.active-trace-residual-global-row.v1"
CANONICAL_ORDERING_RULE = (
    "ascending global active row ID; rank ownership is not part of identity"
)
RESIDUAL_SEMANTICS = (
    "condensed active-trace dual/load residual r=b-Ax; values use active-row "
    "global numbering; not a physical field coefficient"
)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha256(
    row_ids: np.ndarray,
    real: np.ndarray,
    imag: np.ndarray,
    *,
    global_active_row_count: int,
) -> str:
    header = json.dumps(
        {
            "schema_version": RESIDUAL_SNAPSHOT_SCHEMA,
            "global_active_row_count": int(global_active_row_count),
            "row_identity": "active_trace_residual_global_row",
            "value_dtype": "complex128",
            "canonical_ordering_rule": CANONICAL_ORDERING_RULE,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hashlib.sha256(header + b"\0")
    for array, dtype in (
        (row_ids, "<i8"),
        (real, "<f8"),
        (imag, "<f8"),
    ):
        digest.update(np.ascontiguousarray(array, dtype=dtype).tobytes(order="C"))
    return digest.hexdigest()


def _write_residual_owner_shard(
    path: Path,
    *,
    rank: int,
    global_start: int,
    global_end: int,
    row_ids: np.ndarray,
    values: np.ndarray,
) -> dict[str, Any]:
    """Copy and write one owner shard without retaining a PETSc Vec reference."""

    rows = np.asarray(row_ids, dtype="<i8").copy()
    complex_values = np.asarray(values, dtype=np.complex128).copy()
    start, end = int(global_start), int(global_end)
    if end < start or rows.size != end - start:
        raise ValueError("residual owner range and shard length do not agree")
    if not np.array_equal(rows, np.arange(start, end, dtype="<i8")):
        raise ValueError("residual owner shard is not in global row order")
    if complex_values.shape != rows.shape:
        raise ValueError("residual owner values are not aligned with global rows")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(
        path,
        row_ids=np.ascontiguousarray(rows, dtype="<i8"),
        real=np.ascontiguousarray(np.real(complex_values), dtype="<f8"),
        imag=np.ascontiguousarray(np.imag(complex_values), dtype="<f8"),
    )
    return {
        "rank": int(rank),
        "filename": path.name,
        "global_start": start,
        "global_end": end,
        "row_count": int(rows.size),
        "file_sha256": _file_sha256(path),
        "row_identity": "active_trace_residual_global_row",
        "value_dtype": "complex128",
        "storage": "npz(real=float64,imag=float64,row_ids=int64)",
    }


def _write_residual_manifest(
    path: Path,
    *,
    profile: str,
    source_sha: str,
    iteration: int,
    global_active_row_count: int,
    norm_2: float,
    true_relative_residual: float | None,
    reported_relative_residual: float | None,
    canonical_sha256: str,
    shard_metadata: Iterable[dict[str, Any]],
    mpi_size: int,
) -> dict[str, Any]:
    """Write the residual-specific manifest and validate only row identity."""

    shards = sorted(
        (dict(item) for item in shard_metadata),
        key=lambda item: (int(item["global_start"]), int(item["rank"])),
    )
    cursor = 0
    for shard in shards:
        start = int(shard["global_start"])
        end = int(shard["global_end"])
        if start != cursor or end < start or int(shard["row_count"]) != end - start:
            raise ValueError("residual shard ownership is not globally contiguous")
        cursor = end
    if cursor != int(global_active_row_count):
        raise ValueError("residual shard ownership does not cover active rows")
    manifest = {
        "schema_version": RESIDUAL_SNAPSHOT_SCHEMA,
        "profile": str(profile),
        "full_source_sha": str(source_sha),
        "iteration": int(iteration),
        "residual_semantics": RESIDUAL_SEMANTICS,
        "row_identity": "active_trace_residual_global_row",
        "global_active_row_count": int(global_active_row_count),
        "value_dtype": "complex128",
        "real_imag_dtype": "float64",
        "norm_2": float(norm_2),
        "true_relative_residual": (
            None if true_relative_residual is None else float(true_relative_residual)
        ),
        "reported_relative_residual": (
            None
            if reported_relative_residual is None
            else float(reported_relative_residual)
        ),
        "canonical_ordering_rule": CANONICAL_ORDERING_RULE,
        "rank_ownership_not_part_of_identity": True,
        "repartition_invariant_global_numbering": "not_claimed",
        "canonical_sha256": str(canonical_sha256),
        "mpi_size": int(mpi_size),
        "per_rank_shards": shards,
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2).encode(
            "utf-8"
        )
        + b"\n"
    )
    path.write_bytes(payload)
    return {
        "manifest_filename": path.name,
        "manifest_sha256": hashlib.sha256(payload).hexdigest(),
        "manifest": manifest,
    }


def write_residual_snapshot(
    directory: Path,
    residual: PETSc.Vec,
    *,
    iteration: int,
    profile: str,
    source_sha: str,
    true_relative_residual: float | None = None,
    reported_relative_residual: float | None = None,
    comm: MPI.Comm | None = None,
    prefix: str = "task037_g0_residual",
) -> dict[str, Any]:
    """Collectively copy a borrowed Vec, write owner shards, then root manifest."""

    mpi_comm = comm if comm is not None else residual.getComm().tompi4py()
    start, end = map(int, residual.getOwnershipRange())
    local_values = np.asarray(
        residual.getArray(readonly=True), dtype=np.complex128
    ).copy()
    row_ids = np.arange(start, end, dtype="<i8")
    directory = Path(directory)
    shard_path = directory / (
        f"{prefix}_iter{int(iteration):04d}_rank{mpi_comm.rank:04d}.npz"
    )
    local_metadata = _write_residual_owner_shard(
        shard_path,
        rank=mpi_comm.rank,
        global_start=start,
        global_end=end,
        row_ids=row_ids,
        values=local_values,
    )
    packet = (
        local_metadata,
        row_ids,
        np.asarray(np.real(local_values), dtype="<f8"),
        np.asarray(np.imag(local_values), dtype="<f8"),
    )
    packets = mpi_comm.gather(packet, root=0)
    local_norm_sq = float(
        np.sum(np.real(local_values) ** 2 + np.imag(local_values) ** 2)
    )
    norm_2 = float(np.sqrt(mpi_comm.allreduce(local_norm_sq, op=MPI.SUM)))
    result: dict[str, Any] | None = None
    if mpi_comm.rank == 0:
        ordered = sorted(packets, key=lambda item: (item[0]["global_start"], item[0]["rank"]))
        all_rows: list[np.ndarray] = []
        all_real: list[np.ndarray] = []
        all_imag: list[np.ndarray] = []
        for _metadata, rows, real, imag in ordered:
            all_rows.append(rows)
            all_real.append(real)
            all_imag.append(imag)
        global_rows = (
            np.concatenate(all_rows) if all_rows else np.empty(0, dtype="<i8")
        )
        global_real = (
            np.concatenate(all_real) if all_real else np.empty(0, dtype="<f8")
        )
        global_imag = (
            np.concatenate(all_imag) if all_imag else np.empty(0, dtype="<f8")
        )
        manifest_path = directory / (
            f"{prefix}_iter{int(iteration):04d}_manifest.json"
        )
        result = _write_residual_manifest(
            manifest_path,
            profile=profile,
            source_sha=source_sha,
            iteration=iteration,
            global_active_row_count=int(residual.getSize()),
            norm_2=norm_2,
            true_relative_residual=true_relative_residual,
            reported_relative_residual=reported_relative_residual,
            canonical_sha256=_canonical_sha256(
                global_rows,
                global_real,
                global_imag,
                global_active_row_count=int(residual.getSize()),
            ),
            shard_metadata=[item[0] for item in ordered],
            mpi_size=mpi_comm.size,
        )
    return cast(dict[str, Any], mpi_comm.bcast(result, root=0))


__all__ = (
    "CANONICAL_ORDERING_RULE",
    "RESIDUAL_SEMANTICS",
    "RESIDUAL_SNAPSHOT_SCHEMA",
    "write_residual_snapshot",
)
