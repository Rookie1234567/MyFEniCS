"""Research-only canonical owner-row packets for Task040.

This module carries finalized owner-local interface data between two separate
MPI processes.  It deliberately does not build a factor, an interface oracle,
or a transmission action.  A canonical key is kept separate from the current
PETSc row number, and a small block transform is applied in both directions so
that a fresh consumer may use a different local row order or orientation.

The write path is intentionally two-stage: callers write one group shard at a
time and may release that group's temporary arrays immediately; rank zero
writes the small replicated matrices and the manifest only after every rank
has reported all group shards.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from mpi4py import MPI

PACKET_SCHEMA = "task040.interface_schur_packet.v1"

__all__ = (
    "PACKET_SCHEMA",
    "CanonicalTraceBlock",
    "CanonicalBasis",
    "PacketGroup",
    "canonical_key_json",
    "canonical_key_sha256",
    "canonical_key_set_sha256",
    "canonicalize_raw_basis",
    "reconstruct_raw_basis",
    "write_group_shard",
    "finalize_manifest",
    "load_packet_shard",
    "load_small_matrix",
    "remap_group_rows",
    "redistribute_packet_group_rows",
)


def _canonical_json(value: Any) -> str:
    """Encode metadata without silently stringifying unsupported values."""

    def convert(item: Any) -> Any:
        if isinstance(item, Mapping):
            return {str(key): convert(subvalue) for key, subvalue in item.items()}
        if isinstance(item, (list, tuple)):
            return [convert(subvalue) for subvalue in item]
        if isinstance(item, np.generic):
            return convert(item.item())
        if isinstance(item, np.ndarray):
            return convert(item.tolist())
        if isinstance(item, (str, int, float, bool)) or item is None:
            return item
        raise TypeError(f"packet metadata is not JSON-safe: {type(item)!r}")

    return json.dumps(
        convert(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def canonical_key_json(key: Any) -> str:
    """Return the stable JSON representation of one semantic Gamma key."""

    if not isinstance(key, Mapping):
        raise TypeError("canonical Gamma keys must be top-level JSON objects")
    return _canonical_json(key)


def _normalise_keys(keys: Any, *, label: str) -> tuple[str, ...]:
    try:
        result = tuple(
            canonical_key_json(json.loads(key))
            if isinstance(key, str)
            else canonical_key_json(key)
            for key in keys
        )
        if any(not isinstance(json.loads(key), dict) for key in result):
            raise ValueError("canonical Gamma keys must decode to JSON objects")
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} contains a non-JSON-safe key") from exc
    if len(set(result)) != len(result):
        raise ValueError(f"{label} contains duplicate canonical keys")
    return result


def canonical_key_sha256(keys: Any) -> str:
    encoded = _normalise_keys(keys, label="canonical keys")
    return hashlib.sha256("\n".join(encoded).encode("utf-8")).hexdigest()


def canonical_key_set_sha256(keys: Any) -> str:
    """Hash a canonical key set independently of its owner-local order."""

    encoded = sorted(_normalise_keys(keys, label="canonical key set"))
    return hashlib.sha256("\n".join(encoded).encode("utf-8")).hexdigest()


def _array_sha256(values: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(values).tobytes()).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_bytes(path: Path, payload: bytes) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _atomic_npy(path: Path, values: np.ndarray) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("wb") as stream:
        np.save(stream, values, allow_pickle=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


@dataclass(frozen=True)
class CanonicalTraceBlock:
    """A raw local block and its canonical, reversible row transform.

    ``raw_to_canonical`` maps coefficients in ``raw_keys`` order to
    ``canonical_keys`` order.  The matrix may include a permutation and a
    non-diagonal complex orientation/Floquet transform.
    """

    name: str
    canonical_keys: tuple[Any, ...]
    raw_keys: tuple[Any, ...]
    raw_to_canonical: np.ndarray


@dataclass(frozen=True)
class CanonicalBasis:
    keys: tuple[str, ...]
    U: np.ndarray
    V: np.ndarray


@dataclass(frozen=True)
class PacketGroup:
    """Owner-local canonical data for one packet group."""

    name: str
    keys: tuple[str, ...]
    U: np.ndarray
    V: np.ndarray


def _validated_block(
    block: CanonicalTraceBlock,
) -> tuple[str, tuple[str, ...], tuple[str, ...], np.ndarray]:
    canonical = _normalise_keys(
        block.canonical_keys, label=f"{block.name}.canonical_keys"
    )
    raw = _normalise_keys(block.raw_keys, label=f"{block.name}.raw_keys")
    if set(canonical) != set(raw):
        raise ValueError(f"{block.name} raw/canonical key sets differ")
    transform = np.asarray(block.raw_to_canonical, dtype=np.complex128)
    if transform.shape != (len(canonical), len(canonical)):
        raise ValueError(f"{block.name} transform shape does not match its keys")
    if not np.isfinite(transform).all():
        raise ValueError(f"{block.name} transform is nonfinite")
    if np.linalg.matrix_rank(transform) != transform.shape[0]:
        raise ValueError(f"{block.name} transform is singular")
    return str(block.name), canonical, raw, transform


def canonicalize_raw_basis(
    blocks: tuple[CanonicalTraceBlock, ...] | list[CanonicalTraceBlock],
    raw_U: dict[str, np.ndarray],
    raw_V: dict[str, np.ndarray],
) -> CanonicalBasis:
    """Transform raw owner-local blocks into one canonical U/V basis."""

    if not blocks:
        raise ValueError("at least one canonical trace block is required")
    canonical_keys: list[str] = []
    seen_keys: set[str] = set()
    validated: list[
        tuple[str, tuple[str, ...], np.ndarray, np.ndarray, np.ndarray]
    ] = []
    columns: int | None = None
    total_rows = 0
    for block in blocks:
        name, canonical, raw, transform = _validated_block(block)
        if name not in raw_U or name not in raw_V:
            raise ValueError(f"missing raw basis values for block {name}")
        values_u = np.asarray(raw_U[name], dtype=np.complex128)
        values_v = np.asarray(raw_V[name], dtype=np.complex128)
        expected_shape = (len(raw), None)
        if values_u.ndim != 2 or values_v.shape != values_u.shape:
            raise ValueError(f"{name} raw U/V shape mismatch")
        if values_u.shape[0] != expected_shape[0]:
            raise ValueError(f"{name} raw row count does not match keys")
        if columns is None:
            columns = int(values_u.shape[1])
        if values_u.shape[1] != columns:
            raise ValueError("canonical basis blocks have inconsistent column counts")
        if not np.isfinite(values_u).all() or not np.isfinite(values_v).all():
            raise ValueError(f"{name} raw U/V is nonfinite")
        if seen_keys.intersection(canonical):
            raise ValueError("canonical owner-local keys are duplicated across blocks")
        seen_keys.update(canonical)
        canonical_keys.extend(canonical)
        total_rows += len(canonical)
        validated.append((name, canonical, transform, values_u, values_v))
    if columns is None:
        raise ValueError("canonical basis has no columns")
    output_u = np.empty((total_rows, columns), dtype=np.complex128)
    output_v = np.empty_like(output_u)
    offset = 0
    for _name, canonical, transform, values_u, values_v in validated:
        end = offset + len(canonical)
        output_u[offset:end, :] = transform @ values_u
        output_v[offset:end, :] = transform @ values_v
        offset = end
    return CanonicalBasis(
        keys=tuple(canonical_keys),
        U=output_u,
        V=output_v,
    )


def reconstruct_raw_basis(
    blocks: tuple[CanonicalTraceBlock, ...] | list[CanonicalTraceBlock],
    basis: CanonicalBasis,
) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    """Reconstruct each raw U/V block exactly from canonical owner rows."""

    basis_keys = _normalise_keys(basis.keys, label="basis.keys")
    if basis.U.ndim != 2 or basis.V.shape != basis.U.shape:
        raise ValueError("canonical U/V shape mismatch")
    if len(basis_keys) != basis.U.shape[0]:
        raise ValueError("canonical key count does not match basis rows")
    positions = {key: index for index, key in enumerate(basis_keys)}
    raw_u: dict[str, np.ndarray] = {}
    raw_v: dict[str, np.ndarray] = {}
    consumed: set[str] = set()
    for block in blocks:
        name, canonical, raw, transform = _validated_block(block)
        if any(key not in positions for key in canonical):
            raise ValueError(f"canonical basis is missing rows for block {name}")
        if consumed.intersection(canonical):
            raise ValueError("canonical blocks overlap during reconstruction")
        consumed.update(canonical)
        canonical_u = basis.U[[positions[key] for key in canonical], :]
        canonical_v = basis.V[[positions[key] for key in canonical], :]
        raw_u[name] = np.linalg.solve(transform, canonical_u)
        raw_v[name] = np.linalg.solve(transform, canonical_v)
    if consumed != set(basis_keys):
        raise ValueError("canonical basis contains rows not covered by the blocks")
    return raw_u, raw_v


def _validated_group(
    group: PacketGroup,
) -> tuple[str, tuple[str, ...], np.ndarray, np.ndarray]:
    keys = _normalise_keys(group.keys, label=f"{group.name}.keys")
    if not group.name or "/" in group.name or "\\" in group.name:
        raise ValueError("packet group name must be a simple nonempty name")
    U = np.asarray(group.U)
    V = np.asarray(group.V)
    if U.dtype != np.dtype(np.complex128) or V.dtype != np.dtype(np.complex128):
        raise ValueError(f"{group.name} owner-local U/V must be complex128")
    if U.ndim != 2 or V.shape != U.shape or U.shape[0] != len(keys):
        raise ValueError(f"{group.name} owner-local U/V shape mismatch")
    if not np.isfinite(U).all() or not np.isfinite(V).all():
        raise ValueError(f"{group.name} owner-local U/V is nonfinite")
    return group.name, keys, U, V


def _group_descriptor(
    root: Path,
    group_name: str,
    keys: tuple[str, ...],
    U: np.ndarray,
    V: np.ndarray,
    ownership_range: tuple[int, int],
    rank: int,
) -> dict[str, Any]:
    shard_name = f"rank{rank:04d}_group_{group_name}.npz"
    shard_path = root / shard_name
    if shard_path.exists():
        raise FileExistsError(f"packet shard already exists: {shard_path}")
    first, last = (int(value) for value in ownership_range)
    if first < 0 or last < first or last - first != len(keys):
        raise ValueError(f"{group_name} ownership range does not match local rows")
    temporary = root / f".{shard_name}.tmp"
    with temporary.open("wb") as stream:
        np.savez(
            stream,
            keys=np.asarray(keys, dtype=str),
            U=U,
            V=V,
        )
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, shard_path)
    return {
        "rank": int(rank),
        "group": group_name,
        "path": shard_name,
        "sha256": _file_sha256(shard_path),
        "ownership_range": [first, last],
        "key_count": len(keys),
        "key_order_sha256": canonical_key_sha256(keys),
        "owner_key_set_sha256": canonical_key_set_sha256(keys),
        "u_shape": list(U.shape),
        "v_shape": list(V.shape),
        "dtype": "complex128",
        "u_sha256": _array_sha256(U),
        "v_sha256": _array_sha256(V),
    }


def write_group_shard(
    root: str | Path,
    group: PacketGroup,
    *,
    comm: MPI.Intracomm = MPI.COMM_WORLD,
    ownership_range: tuple[int, int],
) -> dict[str, Any]:
    """Write one rank/group shard without creating or updating a manifest."""

    root = Path(root)
    descriptor: dict[str, Any] | None = None
    local_error: str | None = None
    try:
        root.mkdir(parents=True, exist_ok=True)
        group_name, keys, U, V = _validated_group(group)
        descriptor = _group_descriptor(
            root, group_name, keys, U, V, ownership_range, int(comm.rank)
        )
    except Exception as exc:  # collective error propagation prevents rank hangs
        descriptor = None
        local_error = f"{type(exc).__name__}: {exc}"
    errors = comm.allgather(local_error)
    if any(error is not None for error in errors):
        raise ValueError(
            f"group shard write failed: {next(error for error in errors if error)}"
        )
    comm.barrier()
    if descriptor is None:
        raise RuntimeError("group shard descriptor was not produced")
    return descriptor


def _owner_mapping(
    descriptors: list[dict[str, Any]],
) -> tuple[str, int]:
    identities: list[dict[str, Any]] = []
    global_count = 0
    by_rank = sorted(descriptors, key=lambda item: int(item["rank"]))
    for descriptor in by_rank:
        first, last = (int(value) for value in descriptor["ownership_range"])
        count = int(descriptor["key_count"])
        if first < 0 or last < first or last - first != count:
            raise ValueError("packet shard ownership does not match key count")
        identities.append(
            {
                "rank": int(descriptor["rank"]),
                "ownership_range": [first, last],
                "key_count": count,
                "owner_key_set_sha256": descriptor["owner_key_set_sha256"],
            }
        )
        global_count += count
    mapping_sha = hashlib.sha256(
        _canonical_json(identities).encode("utf-8")
    ).hexdigest()
    return mapping_sha, global_count


def _matrix_descriptor(root: Path, name: str, values: np.ndarray) -> dict[str, Any]:
    matrix = np.asarray(values, dtype=np.complex128)
    if matrix.ndim != 2 or not np.isfinite(matrix).all():
        raise ValueError(
            f"small packet matrix {name} must be finite and two-dimensional"
        )
    filename = f"small_{name}.npy"
    path = root / filename
    if path.exists():
        raise FileExistsError(f"small packet matrix already exists: {path}")
    _atomic_npy(path, matrix)
    return {
        "path": filename,
        "shape": list(matrix.shape),
        "dtype": "complex128",
        "sha256": _file_sha256(path),
    }


def finalize_manifest(
    root: str | Path,
    local_descriptors: list[dict[str, Any]],
    *,
    provenance: dict[str, Any],
    group_names: tuple[str, ...] | list[str],
    expected_group_counts: dict[str, int] | None = None,
    small_matrices: dict[str, np.ndarray] | None = None,
    diagnostics: dict[str, Any] | None = None,
    comm: MPI.Intracomm = MPI.COMM_WORLD,
) -> dict[str, Any]:
    """Validate all metadata, then let rank zero write the final manifest."""

    root = Path(root)
    local_error: str | None = None
    try:
        if (root / "manifest.json").exists():
            raise FileExistsError("packet manifest already exists")
        provenance_json = _canonical_json(provenance)
        diagnostics_json = _canonical_json(diagnostics or {})
        local_descriptors = [dict(item) for item in local_descriptors]
        if any(
            int(item.get("rank", -1)) != int(comm.rank) for item in local_descriptors
        ):
            raise ValueError("local packet descriptor has the wrong rank")
        expected = tuple(str(name) for name in group_names)
        if len(set(expected)) != len(expected) or not expected:
            raise ValueError("packet group names must be unique and nonempty")
        if set(item["group"] for item in local_descriptors) != set(expected):
            raise ValueError(
                "each rank must report exactly one shard for every packet group"
            )
        if comm.rank != 0 and small_matrices is not None:
            raise ValueError("only rank zero may write replicated small matrices")
        if expected_group_counts is not None and set(expected_group_counts) != set(
            expected
        ):
            raise ValueError("expected group counts do not match group order")
    except Exception as exc:
        local_error = f"{type(exc).__name__}: {exc}"
    local_errors = comm.allgather(local_error)
    if any(error is not None for error in local_errors):
        raise ValueError(
            f"collective manifest preparation failed: {next(error for error in local_errors if error)}"
        )
    gathered = comm.allgather(
        {
            "rank": int(comm.rank),
            "provenance": provenance_json,
            "descriptors": local_descriptors,
        }
    )
    if len({item["provenance"] for item in gathered}) != 1:
        raise ValueError("packet provenance differs across ranks")
    all_descriptors = [
        item["descriptors"] for item in sorted(gathered, key=lambda item: item["rank"])
    ]
    group_records: dict[str, Any] | None = None
    local_error = None
    try:
        group_records = {}
        for group_name in expected:
            group_descriptors = [
                descriptor
                for rank_descriptors in all_descriptors
                for descriptor in rank_descriptors
                if descriptor["group"] == group_name
            ]
            mapping_sha, global_count = _owner_mapping(group_descriptors)
            if expected_group_counts is not None and global_count != int(
                expected_group_counts[group_name]
            ):
                raise ValueError(
                    f"{group_name} shard coverage count differs from authority"
                )
            if len(group_descriptors) != int(comm.size):
                raise ValueError(f"{group_name} does not have one descriptor per rank")
            ranges = [
                tuple(int(value) for value in descriptor["ownership_range"])
                for descriptor in group_descriptors
            ]
            if any(
                end - start != int(descriptor["key_count"])
                for descriptor, (start, end) in zip(group_descriptors, ranges)
            ):
                raise ValueError(
                    f"{group_name} ownership range does not match descriptor"
                )
            ordered_ranges = sorted(ranges)
            if ordered_ranges and ordered_ranges[0][0] != 0:
                raise ValueError(f"{group_name} ownership does not start at zero")
            if any(
                left[1] != right[0]
                for left, right in zip(ordered_ranges, ordered_ranges[1:])
            ):
                raise ValueError(f"{group_name} ownership ranges are not contiguous")
            group_records[group_name] = {
                "global_count": global_count,
                "row_key_to_owner_mapping_sha256": mapping_sha,
                "global_key_bijection": "requires_independent_checker",
                "shards": [
                    dict(descriptor)
                    for descriptor in sorted(
                        group_descriptors, key=lambda item: int(item["rank"])
                    )
                ],
            }
    except Exception as exc:
        local_error = f"{type(exc).__name__}: {exc}"
    local_errors = comm.allgather(local_error)
    if any(error is not None for error in local_errors):
        raise ValueError(
            f"collective manifest validation failed: {next(error for error in local_errors if error)}"
        )
    write_error: str | None = None
    if comm.rank == 0:
        try:
            small_records: dict[str, Any] = {}
            for name, values in (small_matrices or {}).items():
                if not name or "/" in name or "\\" in name:
                    raise ValueError("small matrix names must be simple")
                small_records[name] = _matrix_descriptor(root, name, values)
            manifest = {
                "schema": PACKET_SCHEMA,
                "packet_complete": True,
                "rank_count": int(comm.size),
                "group_order": list(expected),
                "provenance": json.loads(provenance_json),
                "groups": group_records,
                "small_matrices": small_records,
                "diagnostics": json.loads(diagnostics_json),
                "basis_global_replicated": False,
                "numeric_allgather": False,
                "fe_numeric_allgather": False,
            }
            _atomic_bytes(
                root / "manifest.json",
                (_canonical_json(manifest) + "\n").encode("utf-8"),
            )
        except Exception as exc:
            write_error = f"{type(exc).__name__}: {exc}"
    write_error = comm.bcast(write_error, root=0)
    if write_error is not None:
        raise ValueError(f"collective manifest write failed: {write_error}")
    comm.barrier()
    manifest_path = root / "manifest.json"
    return {
        "manifest": str(manifest_path),
        "manifest_sha256": _file_sha256(manifest_path),
        "packet_complete": True,
        "rank_count": int(comm.size),
    }


def _load_manifest(root: Path) -> tuple[dict[str, Any], str]:
    path = root / "manifest.json"
    if not path.is_file():
        raise FileNotFoundError(
            "interface packet manifest is missing; packet is incomplete"
        )
    payload = path.read_bytes()
    manifest = json.loads(payload)
    if (
        manifest.get("schema") != PACKET_SCHEMA
        or manifest.get("packet_complete") is not True
    ):
        raise ValueError(
            "interface packet manifest is incomplete or has the wrong schema"
        )
    return manifest, hashlib.sha256(payload).hexdigest()


def _load_group(root: Path, record: dict[str, Any], group_name: str) -> PacketGroup:
    path = root / record["path"]
    if _file_sha256(path) != record["sha256"]:
        raise ValueError(f"packet shard hash mismatch for {group_name}")
    with np.load(path, allow_pickle=False) as arrays:
        keys = tuple(str(value) for value in arrays["keys"].tolist())
        U = np.asarray(arrays["U"], dtype=np.complex128)
        V = np.asarray(arrays["V"], dtype=np.complex128)
    group_name, keys, U, V = _validated_group(PacketGroup(group_name, keys, U, V))
    if canonical_key_sha256(keys) != record["key_order_sha256"]:
        raise ValueError(f"packet shard key order hash mismatch for {group_name}")
    if canonical_key_set_sha256(keys) != record["owner_key_set_sha256"]:
        raise ValueError(f"packet shard key-set hash mismatch for {group_name}")
    first, last = (int(value) for value in record["ownership_range"])
    if last - first != len(keys):
        raise ValueError(f"packet shard ownership mismatch for {group_name}")
    if (
        list(U.shape) != list(record["u_shape"])
        or _array_sha256(U) != record["u_sha256"]
    ):
        raise ValueError(f"packet U payload mismatch for {group_name}")
    if (
        list(V.shape) != list(record["v_shape"])
        or _array_sha256(V) != record["v_sha256"]
    ):
        raise ValueError(f"packet V payload mismatch for {group_name}")
    return PacketGroup(group_name, keys, U, V)


def load_small_matrix(root: str | Path, name: str) -> np.ndarray:
    """Load and hash-check one rank-zero-written replicated complex matrix."""

    root = Path(root)
    manifest, _manifest_sha = _load_manifest(root)
    if name not in manifest.get("small_matrices", {}):
        raise KeyError(f"small packet matrix is not present: {name}")
    record = manifest["small_matrices"][name]
    path = root / record["path"]
    if _file_sha256(path) != record["sha256"]:
        raise ValueError(f"small packet matrix hash mismatch: {name}")
    with path.open("rb") as stream:
        values = np.load(stream, allow_pickle=False)
    matrix = np.asarray(values, dtype=np.complex128)
    if matrix.ndim != 2 or list(matrix.shape) != list(record["shape"]):
        raise ValueError(f"small packet matrix shape mismatch: {name}")
    if matrix.dtype != np.dtype(record["dtype"]):
        raise ValueError(f"small packet matrix dtype mismatch: {name}")
    return matrix


def load_packet_shard(
    root: str | Path,
    *,
    groups: list[str] | tuple[str, ...] | None = None,
    expected_provenance: dict[str, Any] | None = None,
    expected_manifest_sha256: str | None = None,
    comm: MPI.Intracomm = MPI.COMM_WORLD,
) -> dict[str, Any]:
    """Load only this rank's requested shards and verify their hashes."""

    root = Path(root)
    loaded: dict[str, PacketGroup] = {}
    local_exception: Exception | None = None
    local_error: str | None = None
    manifest: dict[str, Any] | None = None
    manifest_sha: str | None = None
    try:
        manifest, manifest_sha = _load_manifest(root)
        if (
            expected_manifest_sha256 is not None
            and manifest_sha != expected_manifest_sha256
        ):
            raise ValueError("interface packet manifest hash mismatch")
        if int(manifest["rank_count"]) != int(comm.size):
            raise ValueError("interface packet MPI rank-count mismatch")
        if "group_order" not in manifest:
            raise ValueError("interface packet manifest has no group_order")
        group_order = manifest["group_order"]
        manifest_groups = manifest["groups"]
        if (
            not isinstance(group_order, list)
            or not group_order
            or any(not isinstance(name, str) or not name for name in group_order)
            or len(set(group_order)) != len(group_order)
            or set(group_order) != set(manifest_groups)
        ):
            raise ValueError("interface packet group_order is invalid")
        if expected_provenance is not None and manifest["provenance"] != json.loads(
            _canonical_json(expected_provenance)
        ):
            raise ValueError("interface packet provenance mismatch")
        wanted = set(groups) if groups is not None else set(group_order)
        unknown = wanted - set(manifest_groups)
        if unknown:
            raise ValueError(f"unknown packet group(s): {sorted(unknown)}")
        for name in sorted(wanted):
            records = [
                item
                for item in manifest_groups[name]["shards"]
                if int(item["rank"]) == int(comm.rank)
            ]
            if len(records) != 1:
                raise ValueError(
                    f"packet does not have exactly one local shard for {name}"
                )
            loaded[name] = _load_group(root, records[0], name)
    except Exception as exc:
        local_exception = exc
        local_error = f"{type(exc).__name__}: {exc}"
    errors = comm.allgather(local_error)
    if any(error is not None for error in errors):
        if comm.size == 1 and local_exception is not None:
            raise local_exception
        raise ValueError(
            f"collective packet load failed: {next(error for error in errors if error)}"
        )
    assert manifest is not None and manifest_sha is not None
    return {
        "manifest": manifest,
        "manifest_sha256": manifest_sha,
        "groups": loaded,
        "basis_global_replicated": False,
        "numeric_allgather": False,
    }


def remap_group_rows(group: PacketGroup, target_keys: Any) -> np.ndarray:
    """Return an O(rows) permutation for canonical owner-row remapping."""

    name, source_keys, _source_u, _source_v = _validated_group(group)
    target = _normalise_keys(target_keys, label="target canonical keys")
    if set(source_keys) != set(target):
        raise ValueError(f"canonical remap coverage mismatch for {name}")
    positions = {key: index for index, key in enumerate(source_keys)}
    return np.asarray([positions[key] for key in target], dtype=np.int64)


def redistribute_packet_group_rows(
    source_group: PacketGroup,
    target_keys: Any,
    *,
    comm: MPI.Intracomm = MPI.COMM_WORLD,
) -> tuple[PacketGroup, dict[str, Any]]:
    """Redistribute canonical rows from producer owners to fresh owners.

    Canonical keys are replicated as metadata to establish the source and
    target owner directories.  Numeric U/V rows travel once through an
    object ``alltoall``; no numeric basis is gathered to a rank zero process.
    """

    source_keys: tuple[str, ...] = ()
    target: tuple[str, ...] = ()
    source_name = str(source_group.name)
    source_u = np.empty((0, 0), dtype=np.complex128)
    source_v = np.empty((0, 0), dtype=np.complex128)
    local_error: str | None = None
    try:
        source_name, source_keys, source_u, source_v = _validated_group(source_group)
        target = _normalise_keys(target_keys, label="target canonical keys")
    except Exception as exc:
        local_error = f"{type(exc).__name__}: {exc}"

    metadata = comm.allgather(
        {
            "rank": int(comm.rank),
            "error": local_error,
            "group": source_name,
            "source_keys": source_keys,
            "source_row_count": len(source_keys),
            "target_keys": target,
            "target_row_count": len(target),
            "span_size": int(source_u.shape[1]) if source_u.ndim == 2 else -1,
            "dtype": str(source_u.dtype),
        }
    )
    first_error = next(
        (
            (int(item["rank"]), str(item["error"]))
            for item in metadata
            if item["error"] is not None
        ),
        None,
    )
    if first_error is not None:
        rank, error = first_error
        raise ValueError(
            "collective packet owner redistribution metadata failed on first "
            f"failing rank {rank}: {error}"
        )

    source_owner: dict[str, int] = {}
    target_owner: dict[str, int] = {}
    validation_error: str | None = None
    try:
        groups = {str(item["group"]) for item in metadata}
        if groups != {source_name}:
            raise ValueError("source group names differ across ranks")
        spans = {int(item["span_size"]) for item in metadata}
        dtypes = {str(item["dtype"]) for item in metadata}
        if len(spans) != 1 or next(iter(spans), -1) < 0:
            raise ValueError("source packet span differs across ranks")
        if dtypes != {"complex128"}:
            raise ValueError("source packet U/V dtype is not complex128")
        for item in metadata:
            rank = int(item["rank"])
            for key in item["source_keys"]:
                if key in source_owner:
                    raise ValueError("source canonical keys are duplicated")
                source_owner[str(key)] = rank
            for key in item["target_keys"]:
                if key in target_owner:
                    raise ValueError("target canonical keys are duplicated")
                target_owner[str(key)] = rank
        if set(source_owner) != set(target_owner):
            raise ValueError("source and target canonical key sets differ")
    except Exception as exc:
        validation_error = f"{type(exc).__name__}: {exc}"
    if validation_error is not None:
        raise ValueError(
            "collective packet owner redistribution metadata failed: "
            f"{validation_error}"
        )

    span_size = next(iter({int(item["span_size"]) for item in metadata}))
    target_positions = {key: index for index, key in enumerate(target)}
    send_payload: list[tuple[str, tuple[str, ...], np.ndarray, np.ndarray]] = []
    rows_sent = 0
    for destination in range(comm.size):
        positions = [
            index
            for index, key in enumerate(source_keys)
            if target_owner[key] == destination
        ]
        keys = tuple(source_keys[index] for index in positions)
        rows_sent += len(keys)
        send_payload.append(
            (
                source_name,
                keys,
                source_u[positions, :],
                source_v[positions, :],
            )
        )
    received = comm.alltoall(send_payload)

    output_u = np.empty((len(target), span_size), dtype=np.complex128)
    output_v = np.empty_like(output_u)
    assigned = np.zeros(len(target), dtype=bool)
    post_error: str | None = None
    rows_received = 0
    try:
        for payload in received:
            if len(payload) != 4:
                raise ValueError("owner redistribution received malformed payload")
            name, keys, values_u, values_v = payload
            if name != source_name:
                raise ValueError("owner redistribution received the wrong group")
            values_u = np.asarray(values_u)
            values_v = np.asarray(values_v)
            if (
                values_u.dtype != np.dtype(np.complex128)
                or values_v.dtype != np.dtype(np.complex128)
                or values_u.ndim != 2
                or values_v.shape != values_u.shape
                or values_u.shape[1] != span_size
                or values_u.shape[0] != len(keys)
            ):
                raise ValueError("owner redistribution received a shape/dtype mismatch")
            if not np.isfinite(values_u).all() or not np.isfinite(values_v).all():
                raise ValueError("owner redistribution received nonfinite U/V")
            rows_received += len(keys)
            for offset, key in enumerate(keys):
                if key not in target_positions:
                    raise ValueError("owner redistribution received an unknown key")
                position = target_positions[key]
                if assigned[position]:
                    raise ValueError("owner redistribution received a duplicate key")
                output_u[position, :] = values_u[offset, :]
                output_v[position, :] = values_v[offset, :]
                assigned[position] = True
        if not bool(np.all(assigned)):
            raise ValueError("owner redistribution is missing target keys")
    except Exception as exc:
        post_error = f"{type(exc).__name__}: {exc}"
    post_errors = comm.allgather(post_error)
    first_post_error = next(
        ((rank, error) for rank, error in enumerate(post_errors) if error is not None),
        None,
    )
    if first_post_error is not None:
        rank, error = first_post_error
        raise ValueError(
            "collective packet owner redistribution payload failed on first "
            f"failing rank {rank}: {error}"
        )

    audit = {
        "source_local_row_count": len(source_keys),
        "target_local_row_count": len(target),
        "source_global_row_count": len(source_owner),
        "target_global_row_count": len(target_owner),
        "span_size": span_size,
        "rows_sent": rows_sent,
        "rows_received": rows_received,
        "source_rank_count": int(comm.size),
        "target_rank_count": int(comm.size),
        "source_target_key_bijection": True,
        "canonical_key_metadata_allgather": True,
        "numeric_allgather": False,
        "basis_global_replicated": False,
    }
    return PacketGroup(source_name, target, output_u, output_v), audit
