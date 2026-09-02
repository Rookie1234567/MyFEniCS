"""Streaming, reversible owner-local storage for canonical vector packets."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable

from src.solvers.hcurl_canonical_vector import (
    CanonicalPacket,
    compare_canonical_packets,
)


SHARD_SCHEMA = "task037.canonical-vector-shard.v1"
MANIFEST_SCHEMA = "task037.canonical-vector-manifest.v1"
KEY_DIGEST_ALGORITHM = "sha256(canonical-key-json-v1)"


def _key_jsonable(value: Any) -> Any:
    if isinstance(value, tuple):
        return {"tuple": [_key_jsonable(item) for item in value]}
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise TypeError(f"unsupported canonical key value: {type(value).__name__}")


def _key_from_jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        if set(value) != {"tuple"} or not isinstance(value["tuple"], list):
            raise ValueError("canonical key tuple encoding is invalid")
        return tuple(_key_from_jsonable(item) for item in value["tuple"])
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise ValueError("canonical key JSON value is invalid")


def canonical_key_json_bytes(key: tuple[Any, ...]) -> bytes:
    return json.dumps(
        _key_jsonable(key),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _packet_line(
    key: tuple[Any, ...], value: complex, *, key_bytes: bytes | None = None
) -> bytes:
    if key_bytes is None:
        key_bytes = canonical_key_json_bytes(key)
    coefficient = complex(value)
    record = {
        "schema_version": SHARD_SCHEMA,
        "key": json.loads(key_bytes),
        "key_sha256": hashlib.sha256(key_bytes).hexdigest(),
        "value": [float(coefficient.real), float(coefficient.imag)],
    }
    return (
        json.dumps(
            record,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )


def _decode_canonical_packet_line(
    raw_line: bytes,
) -> tuple[CanonicalPacket, bytes]:
    record = json.loads(raw_line)
    if record["schema_version"] != SHARD_SCHEMA:
        raise ValueError("canonical shard schema is unsupported")
    key = _key_from_jsonable(record["key"])
    key_bytes = canonical_key_json_bytes(key)
    if record["key_sha256"] != hashlib.sha256(key_bytes).hexdigest():
        raise ValueError("canonical key digest does not match key payload")
    value = record["value"]
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError("canonical coefficient encoding is invalid")
    return (key, complex(float(value[0]), float(value[1]))), key_bytes


def write_canonical_packet_shard(
    path: Path,
    packets: Iterable[CanonicalPacket],
    *,
    audit_packets: bool = False,
) -> dict[str, Any]:
    digest = hashlib.sha256()
    count = 0
    packet_finite = True
    duplicate_count = 0
    seen_key_bytes: set[bytes] | None = set() if audit_packets else None
    with path.open("wb") as stream:
        for key, value in packets:
            key_bytes = canonical_key_json_bytes(key)
            if seen_key_bytes is not None:
                if key_bytes in seen_key_bytes:
                    duplicate_count += 1
                else:
                    seen_key_bytes.add(key_bytes)
                coefficient = complex(value)
                packet_finite = (
                    packet_finite
                    and math.isfinite(coefficient.real)
                    and math.isfinite(coefficient.imag)
                )
            line = _packet_line(key, value, key_bytes=key_bytes)
            stream.write(line)
            digest.update(line)
            count += 1
    metadata = {
        "filename": path.name,
        "packet_count": int(count),
        "file_sha256": digest.hexdigest(),
        "key_digest_algorithm": KEY_DIGEST_ALGORITHM,
        "dtype": "complex128",
        "schema_version": SHARD_SCHEMA,
    }
    if audit_packets:
        metadata.update(
            {
                "packet_finite": bool(packet_finite),
                "local_duplicate_count": int(duplicate_count),
            }
        )
    return metadata


def read_canonical_packet_shard(
    path: Path, expected_sha256: str | None = None
) -> tuple[CanonicalPacket, ...]:
    digest = hashlib.sha256()
    packets: list[CanonicalPacket] = []
    with path.open("rb") as stream:
        for raw_line in stream:
            digest.update(raw_line)
            packet, _key_bytes = _decode_canonical_packet_line(raw_line)
            packets.append(packet)
    actual_sha256 = digest.hexdigest()
    if expected_sha256 is not None and actual_sha256 != expected_sha256:
        raise ValueError("canonical shard file digest does not match manifest")
    return tuple(packets)


def read_selected_canonical_packet_shard(
    path: Path,
    wanted_keys: Iterable[tuple[Any, ...]],
    expected_sha256: str,
) -> tuple[tuple[CanonicalPacket, ...], dict[str, Any]]:
    wanted_by_bytes: dict[bytes, tuple[Any, ...]] = {}
    for key in wanted_keys:
        key_bytes = canonical_key_json_bytes(key)
        if key_bytes in wanted_by_bytes:
            raise ValueError("wanted canonical keys contain a duplicate")
        wanted_by_bytes[key_bytes] = key

    digest = hashlib.sha256()
    selected: list[CanonicalPacket] = []
    selected_key_bytes: set[bytes] = set()
    streamed_packet_count = 0
    all_finite = True
    with path.open("rb") as stream:
        for raw_line in stream:
            digest.update(raw_line)
            packet, key_bytes = _decode_canonical_packet_line(raw_line)
            streamed_packet_count += 1
            value = packet[1]
            all_finite = all_finite and math.isfinite(value.real) and math.isfinite(
                value.imag
            )
            if key_bytes not in wanted_by_bytes:
                continue
            if key_bytes in selected_key_bytes:
                raise ValueError("selected canonical key appears more than once")
            selected_key_bytes.add(key_bytes)
            selected.append(packet)

    actual_sha256 = digest.hexdigest()
    if actual_sha256 != expected_sha256:
        raise ValueError("canonical shard file digest does not match manifest")
    missing = set(wanted_by_bytes) - selected_key_bytes
    if missing:
        raise ValueError(f"missing selected canonical keys: {len(missing)}")
    return tuple(selected), {
        "streamed_packet_count": int(streamed_packet_count),
        "selected_packet_count": len(selected),
        "file_sha256": actual_sha256,
        "finite": bool(all_finite),
    }


def read_canonical_packet_shards(
    paths: Iterable[Path], expected_sha256: Iterable[str] | None = None
) -> tuple[CanonicalPacket, ...]:
    expected = None if expected_sha256 is None else tuple(expected_sha256)
    selected = tuple(paths)
    if expected is not None and len(expected) != len(selected):
        raise ValueError("canonical shard digest count does not match paths")
    packets: list[CanonicalPacket] = []
    for index, path in enumerate(selected):
        packets.extend(
            read_canonical_packet_shard(
                path, None if expected is None else expected[index]
            )
        )
    return tuple(packets)


def compare_canonical_shard_sets(
    left_paths: Iterable[Path],
    right_paths: Iterable[Path],
    *,
    left_sha256: Iterable[str] | None = None,
    right_sha256: Iterable[str] | None = None,
    relative_tolerance: float = 1.0e-5,
) -> dict[str, Any]:
    left = read_canonical_packet_shards(left_paths, left_sha256)
    right = read_canonical_packet_shards(right_paths, right_sha256)
    return compare_canonical_packets(
        left,
        right,
        relative_tolerance=relative_tolerance,
    )


def canonical_shard_manifest(
    *,
    role: str,
    mpi_size: int,
    shard_metadata: Iterable[dict[str, Any]],
    extractor_audit: dict[str, Any],
) -> dict[str, Any]:
    shards = tuple(shard_metadata)
    return {
        "schema_version": MANIFEST_SCHEMA,
        "role": role,
        "mpi_size": int(mpi_size),
        "dtype": "complex128",
        "key_digest_algorithm": KEY_DIGEST_ALGORITHM,
        "global_summed_packet_count": int(
            sum(int(item["packet_count"]) for item in shards)
        ),
        "summed_local_duplicate_count": int(
            sum(int(item.get("local_duplicate_count", 0)) for item in shards)
        ),
        "per_rank_shards": list(shards),
        "extractor_audit": extractor_audit,
    }


def write_canonical_manifest(path: Path, manifest: dict[str, Any]) -> str:
    payload = (
        json.dumps(
            manifest,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        ).encode("utf-8")
        + b"\n"
    )
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def read_canonical_manifest(
    path: Path, expected_sha256: str | None = None
) -> dict[str, Any]:
    manifest = read_canonical_manifest_metadata(path, expected_sha256)
    for shard in manifest["per_rank_shards"]:
        read_canonical_packet_shard(
            path.parent / shard["filename"], shard["file_sha256"]
        )
    return manifest


def read_canonical_manifest_metadata(
    path: Path, expected_sha256: str | None = None
) -> dict[str, Any]:
    payload = path.read_bytes()
    actual_sha256 = hashlib.sha256(payload).hexdigest()
    if expected_sha256 is not None and actual_sha256 != expected_sha256:
        raise ValueError("canonical manifest file digest does not match")
    manifest = json.loads(payload)
    if manifest["schema_version"] != MANIFEST_SCHEMA:
        raise ValueError("canonical manifest schema is unsupported")
    return manifest


def compare_canonical_manifests(
    left_path: Path,
    right_path: Path,
    *,
    left_sha256: str | None = None,
    right_sha256: str | None = None,
    relative_tolerance: float = 1.0e-5,
) -> dict[str, Any]:
    left_manifest = read_canonical_manifest(left_path, left_sha256)
    right_manifest = read_canonical_manifest(right_path, right_sha256)
    left_shards = tuple(
        left_path.parent / item["filename"] for item in left_manifest["per_rank_shards"]
    )
    right_shards = tuple(
        right_path.parent / item["filename"]
        for item in right_manifest["per_rank_shards"]
    )
    return compare_canonical_shard_sets(
        left_shards,
        right_shards,
        left_sha256=tuple(
            item["file_sha256"] for item in left_manifest["per_rank_shards"]
        ),
        right_sha256=tuple(
            item["file_sha256"] for item in right_manifest["per_rank_shards"]
        ),
        relative_tolerance=relative_tolerance,
    )


__all__ = [
    "KEY_DIGEST_ALGORITHM",
    "MANIFEST_SCHEMA",
    "SHARD_SCHEMA",
    "canonical_key_json_bytes",
    "canonical_shard_manifest",
    "compare_canonical_manifests",
    "compare_canonical_shard_sets",
    "read_canonical_packet_shard",
    "read_canonical_packet_shards",
    "read_canonical_manifest",
    "read_canonical_manifest_metadata",
    "read_selected_canonical_packet_shard",
    "write_canonical_manifest",
    "write_canonical_packet_shard",
]
