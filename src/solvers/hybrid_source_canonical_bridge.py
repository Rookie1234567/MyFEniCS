"""Owner-independent source packets for the current H(curl) layout.

The V8 loader treated a persisted rank-local token order as a layout
identity.  This bridge keeps only the existing physical canonical token,
routes its complex value directly to the current token owner, and then uses
the reviewed canonical reconstruction routine.  Numeric values remain
sharded; only key and digest metadata are collected.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
from mpi4py import MPI

__all__ = (
    "SOURCE_BRIDGE_PACKET_SCHEMA",
    "SOURCE_BRIDGE_SOURCES",
    "SOURCE_BRIDGE_TOLERANCE",
    "SourceCanonicalIdentityError",
    "audit_packet_key_sets",
    "packet_pair_digest",
    "redistribute_owner_packets",
    "run_source_canonical_bridge",
)

SOURCE_BRIDGE_PACKET_SCHEMA = "task040.v9.source_canonical_bridge.packet.v1"
SOURCE_BRIDGE_TOLERANCE = 1.0e-12
SOURCE_BRIDGE_SOURCES = (
    "external_dtn_coupling",
    "fixed_random_repeat_0",
)


class SourceCanonicalIdentityError(ValueError):
    """A persisted/current physical-key identity cannot be established."""

    def __init__(self, message: str, audit: Mapping[str, Any] | None = None):
        super().__init__(message)
        self.audit = dict(audit or {})


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def packet_pair_digest(
    key: str,
    value: complex,
    *,
    label: str = "",
    side: str = "bottom",
) -> str:
    """Digest one physical key/value pair, independent of packet position."""

    if not isinstance(key, str) or not key:
        raise ValueError("canonical packet key must be a nonempty string")
    number = np.asarray(complex(value), dtype=np.complex128)
    if not np.isfinite(number):
        raise ValueError("canonical packet value must be finite")
    payload = json.dumps(
        {
            "schema": SOURCE_BRIDGE_PACKET_SCHEMA,
            "source_label": str(label),
            "active_side": str(side),
            "physical_token": key,
            "value": [float(number.real), float(number.imag)],
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _sha256(payload)


def audit_packet_key_sets(
    persisted_keys: Sequence[str], current_keys: Sequence[str]
) -> dict[str, Any]:
    """Compare key sets without depending on either sequence's order."""

    persisted = tuple(str(key) for key in persisted_keys)
    current = tuple(str(key) for key in current_keys)
    persisted_set = set(persisted)
    current_set = set(current)
    missing = current_set - persisted_set
    extra = persisted_set - current_set
    return {
        "persisted_count": len(persisted),
        "current_count": len(current),
        "persisted_duplicate_count": len(persisted) - len(persisted_set),
        "current_duplicate_count": len(current) - len(current_set),
        "missing_count": len(missing),
        "extra_count": len(extra),
        "missing_keys": sorted(missing)[:4],
        "extra_keys": sorted(extra)[:4],
        "pass": (
            len(persisted) == len(persisted_set)
            and len(current) == len(current_set)
            and not missing
            and not extra
        ),
    }


def _collective_error(
    comm: MPI.Intracomm, stage: str, local_error: str | None
) -> None:
    errors = comm.allgather(local_error)
    first = next(
        ((rank, error) for rank, error in enumerate(errors) if error is not None),
        None,
    )
    if first is not None:
        rank, error = first
        raise SourceCanonicalIdentityError(
            f"{stage} failed on rank {rank}: {error}"
        )


def redistribute_owner_packets(
    packets: Sequence[tuple[str, complex]],
    owner_by_key: Mapping[str, int],
    *,
    comm: MPI.Intracomm = MPI.COMM_WORLD,
) -> tuple[dict[str, complex], dict[str, Any]]:
    """Send each persisted value once to its current physical-key owner."""

    outgoing: list[list[tuple[str, complex]]] = [[] for _ in range(comm.size)]
    local_error: str | None = None
    sender_bytes = 0
    try:
        for key, value in packets:
            key = str(key)
            destination = int(owner_by_key[key])
            if destination < 0 or destination >= comm.size:
                raise ValueError(f"owner rank is out of range for {key!r}")
            number = complex(value)
            if not np.isfinite(number):
                raise ValueError(f"nonfinite packet value for {key!r}")
            outgoing[destination].append((key, number))
            sender_bytes += len(key.encode("utf-8")) + np.dtype(np.complex128).itemsize
    except Exception as exc:
        local_error = f"{type(exc).__name__}: {exc}"
    _collective_error(comm, "owner packet routing preparation", local_error)
    received = comm.alltoall(outgoing)
    local_error = None
    merged: dict[str, complex] = {}
    receiver_bytes = 0
    try:
        for packet_list in received:
            for key, value in packet_list:
                key = str(key)
                if key in merged:
                    raise ValueError(f"duplicate routed canonical key {key!r}")
                merged[key] = complex(value)
                receiver_bytes += len(key.encode("utf-8")) + np.dtype(
                    np.complex128
                ).itemsize
    except Exception as exc:
        local_error = f"{type(exc).__name__}: {exc}"
    _collective_error(comm, "owner packet routing reception", local_error)
    return merged, {
        "numeric_allgather": False,
        "numeric_collective": "owner_to_owner_object_alltoall",
        "collective_count": 1,
        "max_sender_payload_bytes": int(
            comm.allreduce(sender_bytes, op=MPI.MAX)
        ),
        "max_receiver_payload_bytes": int(
            comm.allreduce(receiver_bytes, op=MPI.MAX)
        ),
        "max_single_packet_payload_bytes": int(
            max((len(str(key).encode("utf-8")) + 16 for key, _ in packets), default=0)
        ),
        "full_numeric_replica": False,
    }


def _key_class_histogram(tokens: Sequence[str]) -> dict[str, dict[str, int]]:
    histogram = {
        "entity_dimension": {},
        "tangential_family": {},
        "orientation_state": {},
        "phase_class": {},
    }
    for token in tokens:
        try:
            decoded = json.loads(token)
            dimension = str(decoded[1])
            orientation = json.dumps(decoded[4], sort_keys=True, separators=(",", ":"))
            coefficient = tuple(float(value) for value in decoded[6])
        except (IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid physical canonical token: {token!r}") from exc
        family = {"1": "edge_tangential", "2": "face_tangential"}.get(
            dimension, "other"
        )
        phase = "unit" if coefficient == (1.0, 0.0) else json.dumps(coefficient)
        for name, value in (
            ("entity_dimension", dimension),
            ("tangential_family", family),
            ("orientation_state", orientation),
            ("phase_class", phase),
        ):
            histogram[name][value] = histogram[name].get(value, 0) + 1
    return histogram


def _merge_histograms(
    parts: Sequence[Mapping[str, Mapping[str, int]]]
) -> dict[str, dict[str, int]]:
    merged: dict[str, dict[str, int]] = {}
    for part in parts:
        for name, values in part.items():
            target = merged.setdefault(str(name), {})
            for value, count in values.items():
                target[str(value)] = target.get(str(value), 0) + int(count)
    return merged


def _global_pair_digest(
    comm: MPI.Intracomm,
    pairs: Sequence[tuple[str, complex]],
    *,
    label: str,
) -> str:
    local = sorted(
        packet_pair_digest(key, value, label=label) for key, value in pairs
    )
    gathered = comm.gather(local, root=0)
    if comm.rank == 0:
        all_digests = sorted(digest for part in gathered for digest in part)
        result = _sha256("\n".join(all_digests).encode("ascii"))
    else:
        result = None
    return str(comm.bcast(result, root=0))


def _global_key_digest(comm: MPI.Intracomm, keys: Sequence[str]) -> str:
    gathered = comm.gather(tuple(sorted(str(key) for key in keys)), root=0)
    if comm.rank == 0:
        result = _sha256(
            "\n".join(sorted(key for part in gathered for key in part)).encode(
                "utf-8"
            )
        )
    else:
        result = None
    return str(comm.bcast(result, root=0))


def _global_relative(
    comm: MPI.Intracomm, first: np.ndarray, second: np.ndarray
) -> float:
    first = np.asarray(first, dtype=np.complex128)
    second = np.asarray(second, dtype=np.complex128)
    if first.shape != second.shape:
        return float("inf")
    local_num = float(np.vdot(first - second, first - second).real)
    local_den = float(np.vdot(second, second).real)
    numerator = float(comm.allreduce(local_num, op=MPI.SUM)) ** 0.5
    denominator = float(comm.allreduce(local_den, op=MPI.SUM)) ** 0.5
    return numerator / max(denominator, 1.0e-300)


def _global_norm(comm: MPI.Intracomm, values: np.ndarray) -> float:
    local = float(np.vdot(values, values).real)
    return float(comm.allreduce(local, op=MPI.SUM)) ** 0.5


def _compact_identity(
    label: str,
    metadata: Mapping[str, Any],
    *,
    source_sha: str,
    input_sha256: str,
    physical_model_sha256: str,
    expected_provenance: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    from .hybrid_bare_f_authority import (
        _source_definition_sha256,
        _source_semantic_descriptor,
    )

    provenance = dict(expected_provenance or {})
    provenance.setdefault("input_sha256", str(input_sha256))
    provenance.setdefault("physical_model_sha256", str(physical_model_sha256))
    provenance.setdefault("source_sha", str(source_sha))
    semantic = _source_semantic_descriptor(
        label=label,
        metadata=metadata,
        provenance=provenance,
    )
    return {
        **semantic,
        "semantic_descriptor": semantic,
        "source_definition_sha256": _source_definition_sha256(
            label=label,
            metadata=metadata,
            provenance=provenance,
        ),
        "execution_source_sha": str(source_sha),
    }


def _semantic_without_execution_sha(value: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(value)
    result.pop("source_sha", None)
    return result


def _persisted_source_identity(
    descriptor: Mapping[str, Any],
    *,
    label: str,
    input_sha256: str,
    physical_model_sha256: str,
    expected_provenance: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Re-run V5's semantic descriptor/hash calculation for one shard."""

    from .hybrid_exact_qualification import validate_owner_vector_descriptor
    from .hybrid_bare_f_authority import (
        _source_definition_sha256,
        _source_semantic_descriptor,
    )

    expected = dict(expected_provenance or {})
    validated = validate_owner_vector_descriptor(
        descriptor,
        expected_label=label,
        expected_input_sha256=input_sha256,
        expected_physical_model_sha256=physical_model_sha256,
        expected_selected_manifest_sha256=expected.get("selected_manifest_sha256"),
        expected_resolved_config_sha256=expected.get("resolved_config_sha256"),
    )
    source_definition = descriptor.get("source_definition")
    provenance = descriptor.get("source_provenance")
    if not isinstance(source_definition, Mapping) or not isinstance(provenance, Mapping):
        raise ValueError("persisted source semantic descriptor/provenance is missing")
    semantic_provenance = source_definition.get("provenance")
    if not isinstance(semantic_provenance, Mapping):
        semantic_provenance = provenance
    semantic = _source_semantic_descriptor(
        label=label,
        metadata=source_definition,
        provenance=semantic_provenance,
    )
    stored_semantic = source_definition.get("source_definition_descriptor")
    if stored_semantic is not None and dict(stored_semantic) != semantic:
        raise ValueError("persisted source semantic descriptor changed")
    expected_hash = _source_definition_sha256(
        label=label,
        metadata=source_definition,
        provenance=semantic_provenance,
    )
    stored_hash = validated["source_definition_sha256"]
    if not isinstance(stored_hash, str) or stored_hash != expected_hash:
        raise ValueError("persisted source_definition_sha256 failed recomputation")
    if source_definition.get("source_definition_sha256") not in (None, stored_hash):
        raise ValueError("persisted nested source_definition_sha256 differs")
    for name, expected_value in expected.items():
        if expected_value is not None and semantic.get(name) != expected_value:
            raise ValueError(f"persisted {name} identity mismatch")
    return {
        "semantic_descriptor": semantic,
        "source_definition_sha256": stored_hash,
        "source_sha": semantic.get("source_sha"),
        "input_sha256": semantic.get("input_sha256"),
        "physical_model_sha256": semantic.get("physical_model_sha256"),
        "resolved_config_sha256": semantic.get("resolved_config_sha256"),
        "selected_manifest_sha256": semantic.get("selected_manifest_sha256"),
        "selected_identity_sha256": semantic.get("selected_identity_sha256"),
    }


def _read_persisted_shard(
    root: Path,
    rank: int,
    label: str,
    *,
    input_sha256: str,
    physical_model_sha256: str,
    expected_provenance: Mapping[str, Any] | None = None,
) -> tuple[list[tuple[str, complex]], dict[str, Any]]:
    try:
        root = root.resolve()
        descriptor_path = root / f"rank{rank:04d}" / f"bottom_{label}_rhs.json"
        descriptor_path.relative_to(root)
        descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
        if not isinstance(descriptor, Mapping):
            raise ValueError("persisted descriptor is not a mapping")
        if descriptor.get("metadata_path") != str(descriptor_path.relative_to(root)):
            raise ValueError("persisted descriptor path binding mismatch")
        layout_path = (root / str(descriptor["canonical_layout_path"])).resolve()
        layout_path.relative_to(root)
        layout = json.loads(layout_path.read_text(encoding="utf-8"))
        if (
            layout.get("schema")
            != "task040.v5.current_bare_f_authority_layout.v1"
            or layout.get("side") != "bottom"
            or int(layout.get("rank", -1)) != int(rank)
        ):
            raise ValueError("persisted canonical layout identity mismatch")
        keys = tuple(str(key) for key in layout["canonical_keys"])
        values_path = (root / str(descriptor["array_path"])).resolve()
        values_path.relative_to(root)
        values = np.load(values_path, mmap_mode="r", allow_pickle=False)
        if (
            values.ndim != 1
            or values.dtype != np.dtype(np.complex128)
            or values.size != len(keys)
        ):
            raise ValueError("persisted canonical shard shape/dtype mismatch")
        if not np.isfinite(np.asarray(values)).all():
            raise ValueError("persisted canonical shard is nonfinite")
        if _sha256(layout_path.read_bytes()) != descriptor.get(
            "canonical_layout_sha256"
        ):
            raise ValueError("persisted canonical layout bytes/hash mismatch")
        if _sha256(np.ascontiguousarray(values).tobytes()) != descriptor.get(
            "array_sha256"
        ):
            raise ValueError("persisted source array bytes/hash mismatch")
        identity = _persisted_source_identity(
            descriptor,
            label=label,
            input_sha256=input_sha256,
            physical_model_sha256=physical_model_sha256,
            expected_provenance=expected_provenance,
        )
        if descriptor.get("canonical_key_set_sha256") != layout.get(
            "canonical_key_set_sha256"
        ):
            raise ValueError("persisted canonical key-set hash mismatch")
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SourceCanonicalIdentityError(
            f"cannot read persisted {label} shard: {type(exc).__name__}: {exc}"
        ) from exc
    return [(key, complex(value)) for key, value in zip(keys, values, strict=True)], {
        "descriptor_path": str(descriptor_path),
        "descriptor_sha256": _sha256(descriptor_path.read_bytes()),
        "canonical_layout_sha256": descriptor.get("canonical_layout_sha256"),
        "canonical_key_set_sha256": descriptor.get("canonical_key_set_sha256"),
        "identity": identity,
        "persisted_key_count_local": len(keys),
    }


def _current_packets(
    system: Any, vector: Any
) -> tuple[dict[str, Any], dict[str, complex], dict[str, Any]]:
    from .hcurl_canonical_vector_dolfinx import (
        extract_canonical_active_trace_packets,
    )
    from .hybrid_bare_f_authority import _canonical_key_token

    packets, audit = extract_canonical_active_trace_packets(
        system.condensed, system.V, system.floquet_data, vector
    )
    raw_by_token: dict[str, Any] = {}
    values_by_token: dict[str, complex] = {}
    for raw_key, value in packets:
        token = _canonical_key_token(raw_key)
        if token in raw_by_token:
            raise ValueError(f"current canonical key is duplicated: {token}")
        raw_by_token[token] = raw_key
        values_by_token[token] = complex(value)
    return raw_by_token, values_by_token, dict(audit)


def _write_json(path: Path, payload: Mapping[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    encoded = json.dumps(payload, sort_keys=True, indent=2, allow_nan=False).encode(
        "utf-8"
    ) + b"\n"
    with temporary.open("wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    return _sha256(path.read_bytes())


def _write_array(path: Path, values: np.ndarray) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("wb") as stream:
        np.save(stream, np.asarray(values, dtype=np.complex128), allow_pickle=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    return _sha256(path.read_bytes())


def _write_current_packet(
    output_root: Path,
    rank: int,
    label: str,
    routed: Mapping[str, complex],
    *,
    source_identity: Mapping[str, Any],
    global_key_digest: str,
    current_pair_digest: str,
    persisted_pair_digest: str,
) -> dict[str, Any]:
    rank_root = output_root / f"rank{rank:04d}"
    ordered = tuple(sorted(routed))
    values = np.asarray([routed[key] for key in ordered], dtype=np.complex128)
    values_path = rank_root / f"v9_{label}_canonical_values.npy"
    keys_path = rank_root / f"v9_{label}_canonical_keys.json"
    values_sha = _write_array(values_path, values)
    keys_sha = _write_json(keys_path, {"keys": list(ordered)})
    shard = {
        "schema": SOURCE_BRIDGE_PACKET_SCHEMA,
        "side": "bottom",
        "label": label,
        "rank": rank,
        "owner_local": True,
        "keys_path": str(keys_path.relative_to(output_root)),
        "values_path": str(values_path.relative_to(output_root)),
        "key_count_local": len(ordered),
        "key_sha256": keys_sha,
        "values_sha256": values_sha,
        "global_key_set_sha256": global_key_digest,
        "persisted_value_pair_digest_sha256": persisted_pair_digest,
        "current_value_pair_digest_sha256": current_pair_digest,
        "source_identity": dict(source_identity),
        "numeric_allgather": False,
        "full_numeric_replica": False,
    }
    shard_path = rank_root / f"v9_{label}_canonical_packet.json"
    shard["shard_manifest_sha256"] = _write_json(shard_path, shard)
    return shard


def _source_bridge_one(
    system: Any,
    *,
    label: str,
    persisted_root: Path,
    output_root: Path,
    source_builder: Callable[[str], tuple[Any, Mapping[str, Any]]],
    source_sha: str,
    input_sha256: str,
    physical_model_sha256: str,
    expected_provenance: Mapping[str, Any] | None,
    event_callback: Callable[[str, Mapping[str, Any]], Any] | None,
) -> dict[str, Any]:
    comm = system.comm
    first_vector = second_vector = None
    first_array = second_array = None
    try:
        first_vector, first_metadata = source_builder(label)
        first_array = np.asarray(
            first_vector.getArray(readonly=True), dtype=np.complex128
        ).copy()
        first_raw, first_values, extraction_audit = _current_packets(
            system, first_vector
        )
        second_vector, second_metadata = source_builder(label)
        second_array = np.asarray(
            second_vector.getArray(readonly=True), dtype=np.complex128
        ).copy()
        second_raw, second_values, _second_audit = _current_packets(
            system, second_vector
        )
    finally:
        if first_vector is not None:
            first_vector.destroy()
        if second_vector is not None:
            second_vector.destroy()
    if first_array is None or second_array is None:
        raise RuntimeError(f"source {label} produced no current active vector")
    if set(first_raw) != set(second_raw):
        raise SourceCanonicalIdentityError(
            f"current source {label} changed its physical key set",
            {"current_repeat_key_sets_equal": False},
        )
    source_identity = _compact_identity(
        label,
        first_metadata,
        source_sha=source_sha,
        input_sha256=input_sha256,
        physical_model_sha256=physical_model_sha256,
        expected_provenance=expected_provenance,
    )
    second_identity = _compact_identity(
        label,
        second_metadata,
        source_sha=source_sha,
        input_sha256=input_sha256,
        physical_model_sha256=physical_model_sha256,
        expected_provenance=expected_provenance,
    )
    if source_identity != second_identity:
        raise SourceCanonicalIdentityError(
            f"current source {label} definition changed on repeat",
            {"source_repeat_identity_equal": False},
        )
    local_pairs: list[tuple[str, complex]] = []
    persisted_audit: dict[str, Any] = {}
    local_error: str | None = None
    try:
        local_pairs, persisted_audit = _read_persisted_shard(
            persisted_root,
            comm.rank,
            label,
            input_sha256=input_sha256,
            physical_model_sha256=physical_model_sha256,
            expected_provenance=expected_provenance,
        )
    except Exception as exc:
        local_error = f"{type(exc).__name__}: {exc}"
    _collective_error(comm, f"persisted {label} shard validation", local_error)
    local_current_tokens = tuple(first_values)
    persisted_parts = comm.allgather(tuple(sorted(key for key, _ in local_pairs)))
    current_parts = comm.allgather(tuple(sorted(local_current_tokens)))
    global_key_audit = audit_packet_key_sets(
        tuple(key for part in persisted_parts for key in part),
        tuple(key for part in current_parts for key in part),
    )
    declared_key_hashes = tuple(
        str(value)
        for value in comm.allgather(
            persisted_audit.get("canonical_key_set_sha256")
        )
    )
    persisted_key_digest = _global_key_digest(
        comm, tuple(key for key, _ in local_pairs)
    )
    current_key_digest = _global_key_digest(comm, local_current_tokens)
    key_hash_gate = bool(
        declared_key_hashes
        and all(value == persisted_key_digest for value in declared_key_hashes)
        and persisted_key_digest == current_key_digest
    )
    global_key_audit.update(
        {
            "persisted_actual_key_set_sha256": persisted_key_digest,
            "current_actual_key_set_sha256": current_key_digest,
            "declared_canonical_key_set_sha256": sorted(set(declared_key_hashes)),
            "canonical_key_set_hash_consistent": key_hash_gate,
        }
    )
    if not global_key_audit["pass"] or not key_hash_gate:
        raise SourceCanonicalIdentityError(
            f"source {label} persisted/current physical-key inventory is not bijective",
            {"key_audit": global_key_audit},
        )
    owner_by_key: dict[str, int] = {}
    owner_error = None
    for rank, part in enumerate(current_parts):
        for key in part:
            if key in owner_by_key:
                owner_error = f"current key has multiple owners: {key}"
            owner_by_key[key] = rank
    _collective_error(comm, "current physical-key owner inventory", owner_error)
    routed, routing_audit = redistribute_owner_packets(
        local_pairs, owner_by_key, comm=comm
    )
    local_key_audit = audit_packet_key_sets(tuple(routed), local_current_tokens)
    counts = {
        name: int(
            comm.allreduce(int(local_key_audit[name]), op=MPI.SUM)
        )
        for name in (
            "persisted_duplicate_count",
            "current_duplicate_count",
            "missing_count",
            "extra_count",
        )
    }
    key_gate = all(value == 0 for value in counts.values())
    if not key_gate:
        raise SourceCanonicalIdentityError(
            f"source {label} physical-key set is not bijective",
            {"key_audit": counts},
        )
    current_pairs = [(key, first_values[key]) for key in local_current_tokens]
    persisted_pairs = [(key, routed[key]) for key in local_current_tokens]
    persisted_pair_digest = _global_pair_digest(
        comm, persisted_pairs, label=label
    )
    current_pair_digest = _global_pair_digest(comm, current_pairs, label=label)
    key_digest = current_key_digest
    key_class_histogram = _merge_histograms(
        comm.allgather(_key_class_histogram(local_current_tokens))
    )
    canonical_value_relative = _global_relative(
        comm,
        np.asarray([routed[key] for key in local_current_tokens]),
        np.asarray([first_values[key] for key in local_current_tokens]),
    )
    static_rhs_repeat = _global_relative(comm, first_array, second_array)
    current_canonical_repeat = _global_relative(
        comm,
        np.asarray([first_values[key] for key in local_current_tokens]),
        np.asarray([second_values[key] for key in local_current_tokens]),
    )
    current_active_rhs_norm = _global_norm(comm, first_array)
    persisted_canonical_coefficient_norm = _global_norm(
        comm, np.asarray([routed[key] for key in local_current_tokens])
    )
    semantic_identity_match = _semantic_without_execution_sha(
        source_identity["semantic_descriptor"]
    ) == _semantic_without_execution_sha(
        persisted_audit["identity"]["semantic_descriptor"]
    )
    raw_to_token = {raw: token for token, raw in first_raw.items()}
    raw_values = {first_raw[key]: routed[key] for key in local_current_tokens}
    from .hcurl_canonical_vector_dolfinx import (
        extract_canonical_active_trace_packets,
        reconstruct_canonical_active_trace_vec,
    )

    reconstructed = None
    reconstruction_calls = 0
    try:
        reconstruction_calls += 1
        reconstructed = reconstruct_canonical_active_trace_vec(
            system.condensed, system.V, system.floquet_data, raw_values
        )
        reconstructed_array = np.asarray(
            reconstructed.getArray(readonly=True), dtype=np.complex128
        ).copy()
        owner_roundtrip_relative = _global_relative(
            comm, reconstructed_array, first_array
        )
        roundtrip_packets, _roundtrip_audit = extract_canonical_active_trace_packets(
            system.condensed, system.V, system.floquet_data, reconstructed
        )
        roundtrip_values = {
            raw_to_token[raw]: complex(value) for raw, value in roundtrip_packets
        }
        roundtrip_relative = _global_relative(
            comm,
            np.asarray([roundtrip_values[key] for key in local_current_tokens]),
            np.asarray([routed[key] for key in local_current_tokens]),
        )
        reconstructed_active_rhs_norm = _global_norm(comm, reconstructed_array)
        source_norm_relative = abs(
            reconstructed_active_rhs_norm - current_active_rhs_norm
        ) / max(
            current_active_rhs_norm, 1.0e-300
        )
    finally:
        if reconstructed is not None:
            reconstructed.destroy()
    residuals = {
        "owner_to_canonical_to_owner_relative": owner_roundtrip_relative,
        "canonical_value_relative": canonical_value_relative,
        "repeated_reconstruction_relative": _global_relative(
            comm, reconstructed_array, second_array
        ),
        "static_condensed_active_rhs_repeat_relative": static_rhs_repeat,
        "current_canonical_repeat_relative": current_canonical_repeat,
        "source_norm_relative": source_norm_relative,
        "roundtrip_canonical_value_relative": roundtrip_relative,
    }
    finite = all(
        np.isfinite(float(value))
        for value in (
            *residuals.values(),
            persisted_canonical_coefficient_norm,
            current_active_rhs_norm,
            reconstructed_active_rhs_norm,
        )
    )
    gate_residuals = (
        "owner_to_canonical_to_owner_relative",
        "canonical_value_relative",
        "repeated_reconstruction_relative",
        "static_condensed_active_rhs_repeat_relative",
        "current_canonical_repeat_relative",
        "source_norm_relative",
        "roundtrip_canonical_value_relative",
    )
    orientation_histogram = key_class_histogram["orientation_state"]
    phase_histogram = key_class_histogram["phase_class"]
    orientation_applied_once = bool(
        reconstruction_calls == 1
        and set(roundtrip_values) == set(local_current_tokens)
        and np.isfinite(roundtrip_relative)
    )
    phase_application_count = int(reconstruction_calls)
    gates = {
        "key_bijection": key_gate,
        "persisted_current_semantic_identity": semantic_identity_match,
        "canonical_key_set_hash_consistency": key_hash_gate,
        "phase_application_count": phase_application_count == 1,
        "orientation_applied_once": orientation_applied_once,
        "finite": finite,
        **{
            name: float(value) <= SOURCE_BRIDGE_TOLERANCE
            for name in gate_residuals
        },
    }
    if not all(bool(value) for value in gates.values()):
        raise SourceCanonicalIdentityError(
            f"source {label} canonical bridge accuracy gate failed",
            {"gates": gates, "residuals": residuals},
        )
    shard = _write_current_packet(
        output_root,
        comm.rank,
        label,
        routed,
        source_identity=source_identity,
        global_key_digest=key_digest,
        current_pair_digest=current_pair_digest,
        persisted_pair_digest=persisted_pair_digest,
    )
    shards = comm.gather(shard, root=0)
    manifest_sha = None
    if comm.rank == 0:
        manifest_sha = _write_json(
            output_root / f"v9_{label}_source_bridge_manifest.json",
            {
                "schema": SOURCE_BRIDGE_PACKET_SCHEMA,
                "side": "bottom",
                "label": label,
                "source_identity": source_identity,
                "persisted_identity": persisted_audit["identity"],
                "global_key_set_sha256": key_digest,
                "persisted_value_pair_digest_sha256": persisted_pair_digest,
                "current_value_pair_digest_sha256": current_pair_digest,
                "bitwise_pair_hash_equal": persisted_pair_digest == current_pair_digest,
                "shards": shards,
                "numeric_allgather": False,
                "full_numeric_replica": False,
                "metadata_collective": "key inventory and scalar digest only",
            },
        )
    manifest_sha = comm.bcast(manifest_sha, root=0)
    if event_callback is not None:
        event_callback(
            "source_ready",
            {
                "source": label,
                "source_identity": source_identity,
                "persisted_identity": persisted_audit["identity"],
                "key_count_global": int(
                    comm.allreduce(len(local_current_tokens), op=MPI.SUM)
                ),
                "phase_application_count": phase_application_count,
                "orientation_applied_once": orientation_applied_once,
                "orientation_state_histogram": orientation_histogram,
                "phase_class_histogram": phase_histogram,
                "residuals": residuals,
                "persisted_canonical_coefficient_norm": (
                    persisted_canonical_coefficient_norm
                ),
                "current_active_rhs_norm": current_active_rhs_norm,
                "reconstructed_active_rhs_norm": reconstructed_active_rhs_norm,
                "numeric_allgather": False,
            },
        )
        event_callback(
            "packet_written",
            {
                "source": label,
                "manifest_sha256": manifest_sha,
                "global_key_set_sha256": key_digest,
                "persisted_value_pair_digest_sha256": persisted_pair_digest,
                "current_value_pair_digest_sha256": current_pair_digest,
                "routing": routing_audit,
            },
        )
    return {
        "label": label,
        "status": "verified",
        "source_identity": source_identity,
        "persisted_identity": persisted_audit["identity"],
        "key_audit": {**global_key_audit, **counts},
        "key_class_histogram": key_class_histogram,
        "orientation_phase_audit": {
            "phase_application_count": phase_application_count,
            "orientation_applied_once": orientation_applied_once,
            "reconstruction_calls": reconstruction_calls,
            "orientation_state_histogram": orientation_histogram,
            "phase_class_histogram": phase_histogram,
            "roundtrip_key_set_equal": set(roundtrip_values)
            == set(local_current_tokens),
        },
        "residuals": residuals,
        "persisted_canonical_coefficient_norm": persisted_canonical_coefficient_norm,
        "current_active_rhs_norm": current_active_rhs_norm,
        "reconstructed_active_rhs_norm": reconstructed_active_rhs_norm,
        "gates": gates,
        "global_key_set_sha256": key_digest,
        "persisted_value_pair_digest_sha256": persisted_pair_digest,
        "current_value_pair_digest_sha256": current_pair_digest,
        "bitwise_pair_hash_equal": persisted_pair_digest == current_pair_digest,
        "source_build_count": 2,
        "static_condensed_active_rhs": True,
        "numeric_allgather": False,
        "full_numeric_replica": False,
        "routing": routing_audit,
        "manifest_sha256": manifest_sha,
        "extraction_audit": {
            "local": extraction_audit,
            "owner_inventory_allgather": True,
            "owner_inventory_numeric": False,
        },
        "matrix_factor_inventory": {
            "C": 0,
            "D": 0,
            "H": 0,
            "factor": 0,
            "qep": 0,
            "fgmres": 0,
        },
    }


def run_source_canonical_bridge(
    system: Any,
    *,
    persisted_root: str | Path,
    output_root: str | Path,
    source_builder: Callable[[str], tuple[Any, Mapping[str, Any]]],
    source_sha: str,
    input_sha256: str,
    physical_model_sha256: str,
    event_callback: Callable[[str, Mapping[str, Any]], Any] | None = None,
    sources: Sequence[str] = SOURCE_BRIDGE_SOURCES,
    source_provenance: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Verify and publish current-owner packets for the fixed two sources."""

    if tuple(sources) != SOURCE_BRIDGE_SOURCES:
        raise ValueError("V9 source bridge has a fixed two-source order")
    if system.comm.size != 8:
        raise ValueError("V9 source bridge formal route requires MPI size 8")
    persisted_root = Path(persisted_root).resolve()
    output_root = Path(output_root).resolve()
    if not persisted_root.is_dir():
        raise SourceCanonicalIdentityError(
            f"persisted source root does not exist: {persisted_root}"
        )
    if event_callback is not None:
        event_callback(
            "preflight",
            {
                "source_order": list(SOURCE_BRIDGE_SOURCES),
                "persisted_root": str(persisted_root),
                "numeric_allgather": False,
                "full_numeric_replica": False,
                "full_side_factor": 0,
                "group_factors": 0,
                "qep": 0,
                "fgmres": 0,
            },
        )
    records: dict[str, Any] = {}
    for label in SOURCE_BRIDGE_SOURCES:
        records[label] = _source_bridge_one(
            system,
            label=label,
            persisted_root=persisted_root,
            output_root=output_root,
            source_builder=source_builder,
            source_sha=source_sha,
            input_sha256=input_sha256,
            physical_model_sha256=physical_model_sha256,
            expected_provenance=source_provenance,
            event_callback=event_callback,
        )
    return {
        "schema": "task040.v9.source_canonical_bridge.v1",
        "status": "verified",
        "classification": "V9_SOURCE_CANONICAL_BRIDGE_PASS",
        "pass": True,
        "source_order": list(SOURCE_BRIDGE_SOURCES),
        "sources": records,
        "source_sha": source_sha,
        "input_sha256": input_sha256,
        "physical_model_sha256": physical_model_sha256,
        "source_provenance": dict(source_provenance or {}),
        "numeric_allgather": False,
        "full_numeric_replica": False,
        "full_side_factor_count": 0,
        "group_factor_count": 0,
        "qep_calls": 0,
        "fgmres_calls": 0,
        "outer_solver": "not_run",
        "metadata_collective": "current key inventory and scalar digest only",
    }
