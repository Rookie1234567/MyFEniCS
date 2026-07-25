"""Safe offline/online cache for fixed-trace custom Basix elements.

The fixed-p5-trace/p6-interior element is expensive to derive because every
new process otherwise rebuilds three high-order Basix elements, two
interpolation operators, and a dense QR factorisation.  This research-only
cache persists only the numeric inputs accepted by
``basix.create_custom_element``.  A warm process still constructs a fresh
Basix C++ object; it never unpickles or restores executable state.

Publication is manifest-last and SHA256 checked.  The cache identity binds the
full source SHA, degrees, Basix UFL source, Python/NumPy platform, and payload
schema.  MPI callers use an all-or-nothing collective decision so one rank
cannot silently take a different finite-element path.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import time
from typing import Any
from uuid import uuid4

import basix
import numpy as np

from .fast_custom_element_ufl import (
    basix_ufl_private_api_audit,
    custom_element_sha256,
)


_CACHE_SCHEMA = "task035b.fixed-trace-custom-element-cache.v1"
_IDENTITY_SCHEMA = "task035b.fixed-trace-custom-element-identity.v1"
_PAYLOAD_SCHEMA = "task035b.fixed-trace-custom-element-payload.v1"
_CACHE_MODES = frozenset({"read_only", "read_write"})


@dataclass(frozen=True)
class FixedTraceElementBuild:
    """One custom element plus its pre-construction numeric payload."""

    element: basix.finite_element.FiniteElement
    payload_metadata: dict[str, Any]
    payload_arrays: dict[str, np.ndarray]
    build_audit: dict[str, Any] | None = None


def _full_source_sha(value: str) -> str:
    sha = str(value).strip().lower()
    if len(sha) != 40 or any(char not in "0123456789abcdef" for char in sha):
        raise ValueError(
            "persistent fixed-trace element cache requires a full Git SHA"
        )
    return sha


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _identity(
    *,
    source_sha: str,
    trace_degree: int,
    interior_degree: int,
) -> dict[str, Any]:
    private_api = basix_ufl_private_api_audit()
    return {
        "schema_version": _IDENTITY_SCHEMA,
        "source_sha": _full_source_sha(source_sha),
        "trace_degree": int(trace_degree),
        "interior_degree": int(interior_degree),
        "cell_type": "hexahedron",
        "element_family": "N1curl",
        "payload_schema": _PAYLOAD_SCHEMA,
        "basix_version": str(basix.__version__),
        "basix_ufl_source_sha256": private_api.basix_ufl_module_sha256,
        "python_implementation": platform.python_implementation(),
        "python_major_minor": [int(sys.version_info.major), int(sys.version_info.minor)],
        "numpy_version": str(np.__version__),
        "machine": platform.machine(),
        "byteorder": sys.byteorder,
    }


def _identity_digest(identity: dict[str, Any]) -> str:
    encoded = json.dumps(
        identity,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def _enum_name(value: Any) -> str:
    name = getattr(value, "name", None)
    if not isinstance(name, str) or not name:
        raise TypeError(f"Basix enum value has no stable name: {value!r}")
    return name


def fixed_trace_element_build(
    element: basix.finite_element.FiniteElement,
    *,
    cell_type: Any,
    value_shape: tuple[int, ...],
    wcoeffs: np.ndarray,
    x: list[list[np.ndarray]],
    M: list[list[np.ndarray]],
    interpolation_nderivs: int,
    map_type: Any,
    sobolev_space: Any,
    discontinuous: bool,
    embedded_subdegree: int,
    embedded_superdegree: int,
    polyset_type: Any,
    build_audit: dict[str, Any] | None = None,
) -> FixedTraceElementBuild:
    """Capture the exact inputs used for the first custom-element build.

    Persisting ``element.wcoeffs`` would feed Basix's normalized output back
    into ``create_custom_element`` and introduce another round of floating
    point normalization.  The resulting tiny changes alter the Basix hash and
    invalidate downstream tensor/DtN caches.  The original constructor inputs
    reproduce the cold element bit-for-bit on the qualified ABI.
    """

    arrays: dict[str, np.ndarray] = {
        "wcoeffs": np.ascontiguousarray(wcoeffs),
    }
    x_counts: list[int] = []
    m_counts: list[int] = []
    for dimension, entities in enumerate(x):
        x_counts.append(len(entities))
        for entity, values in enumerate(entities):
            arrays[f"x_{dimension}_{entity}"] = np.ascontiguousarray(values)
    for dimension, entities in enumerate(M):
        m_counts.append(len(entities))
        for entity, values in enumerate(entities):
            arrays[f"M_{dimension}_{entity}"] = np.ascontiguousarray(values)
    metadata = {
        "schema_version": _PAYLOAD_SCHEMA,
        "cell_type": _enum_name(cell_type),
        "value_shape": [int(value) for value in value_shape],
        "interpolation_nderivs": int(interpolation_nderivs),
        "map_type": _enum_name(map_type),
        "sobolev_space": _enum_name(sobolev_space),
        "discontinuous": bool(discontinuous),
        "embedded_subdegree": int(embedded_subdegree),
        "embedded_superdegree": int(embedded_superdegree),
        "polyset_type": _enum_name(polyset_type),
        "x_entity_counts": x_counts,
        "M_entity_counts": m_counts,
        "array_names": sorted(arrays),
    }
    return FixedTraceElementBuild(
        element=element,
        payload_metadata=metadata,
        payload_arrays=arrays,
        build_audit=(
            None if build_audit is None else dict(build_audit)
        ),
    )


def _enum(enum_type: Any, name: Any) -> Any:
    if not isinstance(name, str) or not hasattr(enum_type, name):
        raise ValueError(
            f"cached Basix enum {getattr(enum_type, '__name__', enum_type)!r} "
            f"has invalid member {name!r}"
        )
    return getattr(enum_type, name)


def _nested_arrays(
    arrays: dict[str, np.ndarray],
    *,
    prefix: str,
    counts: Any,
) -> list[list[np.ndarray]]:
    if (
        not isinstance(counts, list)
        or any(not isinstance(count, int) or count < 0 for count in counts)
    ):
        raise ValueError(f"cached {prefix} entity counts are invalid")
    return [
        [
            np.ascontiguousarray(arrays[f"{prefix}_{dimension}_{entity}"])
            for entity in range(count)
        ]
        for dimension, count in enumerate(counts)
    ]


def _reconstruct(
    metadata: dict[str, Any],
    arrays: dict[str, np.ndarray],
) -> basix.finite_element.FiniteElement:
    if metadata.get("schema_version") != _PAYLOAD_SCHEMA:
        raise ValueError("fixed-trace element payload schema mismatch")
    expected_names = metadata.get("array_names")
    if (
        not isinstance(expected_names, list)
        or set(expected_names) != set(arrays)
        or any(not isinstance(name, str) for name in expected_names)
    ):
        raise ValueError("fixed-trace element array inventory mismatch")
    if "wcoeffs" not in arrays:
        raise ValueError("fixed-trace element payload lacks wcoeffs")
    value_shape = metadata.get("value_shape")
    if (
        not isinstance(value_shape, list)
        or any(not isinstance(value, int) or value < 0 for value in value_shape)
    ):
        raise ValueError("fixed-trace element value shape is invalid")
    return basix.create_custom_element(
        _enum(basix.CellType, metadata.get("cell_type")),
        tuple(value_shape),
        np.ascontiguousarray(arrays["wcoeffs"]),
        _nested_arrays(
            arrays,
            prefix="x",
            counts=metadata.get("x_entity_counts"),
        ),
        _nested_arrays(
            arrays,
            prefix="M",
            counts=metadata.get("M_entity_counts"),
        ),
        int(metadata["interpolation_nderivs"]),
        _enum(basix.MapType, metadata.get("map_type")),
        _enum(basix.SobolevSpace, metadata.get("sobolev_space")),
        bool(metadata["discontinuous"]),
        int(metadata["embedded_subdegree"]),
        int(metadata["embedded_superdegree"]),
        _enum(basix.PolysetType, metadata.get("polyset_type")),
    )


def _load_pair(
    manifest_path: Path,
    payload_path: Path,
    *,
    identity: dict[str, Any],
) -> tuple[basix.finite_element.FiniteElement, dict[str, Any]]:
    started = time.perf_counter()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("fixed-trace element manifest is not an object")
    if manifest.get("schema_version") != _CACHE_SCHEMA:
        raise ValueError("fixed-trace element cache schema mismatch")
    if manifest.get("identity") != identity:
        raise ValueError("fixed-trace element cache identity mismatch")
    expected_payload_sha = manifest.get("payload_sha256")
    if (
        not isinstance(expected_payload_sha, str)
        or len(expected_payload_sha) != 64
        or _sha256(payload_path) != expected_payload_sha
    ):
        raise ValueError("fixed-trace element payload checksum mismatch")
    metadata = manifest.get("payload_metadata")
    if not isinstance(metadata, dict):
        raise ValueError("fixed-trace element payload metadata is missing")
    with np.load(payload_path, allow_pickle=False) as archive:
        arrays = {
            str(name): np.asarray(archive[name]).copy()
            for name in archive.files
        }
    read_seconds = time.perf_counter() - started
    reconstruct_started = time.perf_counter()
    element = _reconstruct(metadata, arrays)
    reconstruct_seconds = time.perf_counter() - reconstruct_started
    signature_started = time.perf_counter()
    signature = custom_element_sha256(element)
    signature_seconds = time.perf_counter() - signature_started
    if signature != manifest.get("element_signature_sha256"):
        raise ValueError("fixed-trace element signature mismatch after restore")
    return element, {
        "read_seconds_local": float(read_seconds),
        "reconstruct_seconds_local": float(reconstruct_seconds),
        "signature_seconds_local": float(signature_seconds),
        "payload_sha256": expected_payload_sha,
        "element_signature_sha256": signature,
    }


def _publish_pair(
    manifest_path: Path,
    payload_path: Path,
    *,
    identity: dict[str, Any],
    build: FixedTraceElementBuild,
) -> dict[str, Any]:
    metadata = build.payload_metadata
    arrays = build.payload_arrays
    cache_directory = manifest_path.parent
    cache_directory.mkdir(parents=True, exist_ok=True)
    lock_path = cache_directory / f".{manifest_path.stem}.lock"
    lock_descriptor = os.open(
        lock_path,
        os.O_CREAT | os.O_EXCL | os.O_WRONLY,
        0o600,
    )
    token = uuid4().hex
    temporary_payload = cache_directory / f".{payload_path.name}.{token}.tmp"
    temporary_manifest = cache_directory / f".{manifest_path.name}.{token}.tmp"
    try:
        if manifest_path.exists() or payload_path.exists():
            raise FileExistsError(
                "fixed-trace element cache publication refuses to overwrite "
                "an existing artifact"
            )
        with temporary_payload.open("xb") as stream:
            np.savez(stream, **arrays)
            stream.flush()
            os.fsync(stream.fileno())
        payload_sha = _sha256(temporary_payload)
        manifest = {
            "schema_version": _CACHE_SCHEMA,
            "identity": identity,
            "payload_metadata": metadata,
            "payload_sha256": payload_sha,
            "element_signature_sha256": custom_element_sha256(build.element),
            "serialization": "json_plus_npz_allow_pickle_false",
            "publication": "atomic_payload_then_manifest",
        }
        encoded = (
            json.dumps(
                manifest,
                sort_keys=True,
                indent=2,
                ensure_ascii=True,
                allow_nan=False,
            )
            + "\n"
        )
        with temporary_manifest.open("x", encoding="utf-8") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_payload, payload_path)
        os.replace(temporary_manifest, manifest_path)
        directory_descriptor = os.open(cache_directory, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        temporary_payload.unlink(missing_ok=True)
        temporary_manifest.unlink(missing_ok=True)
        os.close(lock_descriptor)
        lock_path.unlink(missing_ok=True)
    return {
        "payload_sha256": payload_sha,
        "element_signature_sha256": manifest["element_signature_sha256"],
        "payload_array_count": len(arrays),
        "payload_bytes": int(payload_path.stat().st_size),
    }


def load_or_build_fixed_trace_element(
    *,
    trace_degree: int,
    interior_degree: int,
    cache_directory: str | Path,
    source_sha: str,
    cache_mode: str,
    comm: Any,
    builder: Callable[
        [int, int], FixedTraceElementBuild
    ],
) -> tuple[basix.finite_element.FiniteElement, dict[str, Any]]:
    """Collectively restore or build one fixed-trace custom element."""

    local_contract_error: str | None = None
    mode = str(cache_mode).lower()
    identity: dict[str, Any] = {}
    digest = ""
    directory = Path(cache_directory)
    manifest_path = directory / "invalid"
    payload_path = directory / "invalid"
    try:
        if mode not in _CACHE_MODES:
            raise ValueError(
                "fixed-trace element cache mode must be read_only or "
                "read_write"
            )
        trace_degree = int(trace_degree)
        interior_degree = int(interior_degree)
        if not 1 <= trace_degree < interior_degree <= 6:
            raise ValueError(
                "fixed-trace element cache requires "
                "1 <= trace degree < interior degree <= 6"
            )
        identity = _identity(
            source_sha=source_sha,
            trace_degree=trace_degree,
            interior_degree=interior_degree,
        )
        digest = _identity_digest(identity)
        directory = Path(cache_directory).resolve()
        manifest_path = directory / f"fixed_trace_element_{digest}.json"
        payload_path = directory / f"fixed_trace_element_{digest}.npz"
    except Exception as exc:
        local_contract_error = f"{type(exc).__name__}: {exc}"
    contract_errors = tuple(comm.allgather(local_contract_error))
    if any(error is not None for error in contract_errors):
        raise ValueError(
            "fixed-trace element cache contract failed collectively: "
            f"{contract_errors}"
        )
    contracts = tuple(
        comm.allgather(
            (
                mode,
                digest,
                str(directory),
                str(manifest_path),
                str(payload_path),
            )
        )
    )
    if len(set(contracts)) != 1:
        raise RuntimeError(
            "fixed-trace element cache identity/path differs across MPI ranks"
        )

    local_pair_error: str | None = None
    pair_state = (False, False)
    try:
        pair_state = (manifest_path.is_file(), payload_path.is_file())
    except Exception as exc:
        local_pair_error = f"{type(exc).__name__}: {exc}"
    pair_errors = tuple(comm.allgather(local_pair_error))
    if any(error is not None for error in pair_errors):
        raise RuntimeError(
            "fixed-trace element cache pair probe failed collectively: "
            f"{pair_errors}"
        )
    pair_states = tuple(comm.allgather(pair_state))
    if len(set(pair_states)) != 1:
        raise RuntimeError(
            "fixed-trace element cache visibility differs across MPI ranks"
        )
    if pair_state[0] != pair_state[1]:
        raise RuntimeError("fixed-trace element cache pair is incomplete")

    read_audit: dict[str, Any] = {}
    cache_hit = bool(pair_state[0])
    if cache_hit:
        local_error: str | None = None
        element: basix.finite_element.FiniteElement | None = None
        try:
            element, read_audit = _load_pair(
                manifest_path,
                payload_path,
                identity=identity,
            )
        except Exception as exc:  # collective fail-closed report below
            local_error = f"{type(exc).__name__}: {exc}"
        errors = tuple(comm.allgather(local_error))
        if any(error is not None for error in errors):
            raise RuntimeError(
                "fixed-trace element cache validation failed collectively: "
                f"{errors}"
            )
        if element is None:
            raise RuntimeError("fixed-trace element cache returned no element")
        restored_certificates = tuple(
            comm.allgather(
                (
                    custom_element_sha256(element),
                    int(element.hash()),
                    int(element.dim),
                )
            )
        )
        if len(set(restored_certificates)) != 1:
            raise RuntimeError(
                "restored fixed-trace element differs across MPI ranks"
            )
        status = "persistent_fixed_trace_element_cache_hit"
        build_seconds_local = 0.0
        write_seconds_local = 0.0
        publication: dict[str, Any] = {}
    else:
        if mode == "read_only":
            raise FileNotFoundError(
                "read-only fixed-trace element cache pair is missing"
            )
        build: FixedTraceElementBuild | None = None
        build_error: str | None = None
        element: basix.finite_element.FiniteElement | None = None
        signature = ""
        build_audit_local: dict[str, Any] | None = None
        build_started = time.perf_counter()
        try:
            build = builder(trace_degree, interior_degree)
            if not isinstance(build, FixedTraceElementBuild):
                raise TypeError(
                    "fixed-trace element cache builder must return "
                    "FixedTraceElementBuild"
                )
            element = build.element
            signature = custom_element_sha256(element)
            build_audit_local = build.build_audit
        except Exception as exc:
            build_error = f"{type(exc).__name__}: {exc}"
        build_seconds_local = time.perf_counter() - build_started
        build_errors = tuple(comm.allgather(build_error))
        if any(error is not None for error in build_errors):
            raise RuntimeError(
                "fixed-trace element construction failed collectively: "
                f"{build_errors}"
            )
        if build is None or element is None:
            raise RuntimeError("fixed-trace element builder returned no data")
        signatures = tuple(comm.allgather(signature))
        if len(set(signatures)) != 1:
            raise RuntimeError(
                "fixed-trace element construction differs across MPI ranks"
            )
        build_audits = tuple(comm.allgather(build_audit_local))
        if any(audit is None for audit in build_audits):
            if not all(audit is None for audit in build_audits):
                raise RuntimeError(
                    "fixed-trace element build audit presence differs "
                    "across MPI ranks"
                )
            cold_builder_profile = None
        else:
            typed_audits = tuple(
                dict(audit) for audit in build_audits if audit is not None
            )
            structural_audits = []
            timing_audits = []
            for audit in typed_audits:
                stage_seconds = audit.pop("stage_seconds", None)
                if not isinstance(stage_seconds, dict):
                    raise RuntimeError(
                        "fixed-trace element build audit lacks stage timings"
                    )
                structural_audits.append(audit)
                timing_audits.append(stage_seconds)
            encoded_structural = {
                json.dumps(
                    audit,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=True,
                    allow_nan=False,
                )
                for audit in structural_audits
            }
            if len(encoded_structural) != 1:
                raise RuntimeError(
                    "fixed-trace element build strategy differs across ranks"
                )
            timing_keys = tuple(sorted(timing_audits[0]))
            if any(tuple(sorted(timing)) != timing_keys for timing in timing_audits):
                raise RuntimeError(
                    "fixed-trace element build timing inventory differs "
                    "across ranks"
                )
            stage_seconds_max: dict[str, float] = {}
            for key in timing_keys:
                values = [float(timing[key]) for timing in timing_audits]
                if any(not np.isfinite(value) or value < 0.0 for value in values):
                    raise RuntimeError(
                        "fixed-trace element build timing is not finite and "
                        f"nonnegative: stage={key}, values={values}"
                    )
                stage_seconds_max[key] = max(values)
            cold_builder_profile = {
                **structural_audits[0],
                "stage_seconds_max": stage_seconds_max,
                "mpi_rank_count": int(comm.size),
                "aggregation": "per_stage_MPI_MAX",
            }
        write_seconds_local = 0.0
        publication = {}
        if mode == "read_write":
            publication_error: str | None = None
            if int(comm.rank) == 0:
                try:
                    write_started = time.perf_counter()
                    publication = _publish_pair(
                        manifest_path,
                        payload_path,
                        identity=identity,
                        build=build,
                    )
                    write_seconds_local = (
                        time.perf_counter() - write_started
                    )
                except Exception as exc:
                    publication_error = f"{type(exc).__name__}: {exc}"
            publication_error, publication = comm.bcast(
                (publication_error, publication),
                root=0,
            )
            if publication_error is not None:
                raise RuntimeError(
                    "fixed-trace element cache publication failed "
                    f"collectively: {publication_error}"
                )
            local_visibility = (
                manifest_path.is_file() and payload_path.is_file()
            )
            visibility = tuple(comm.allgather(local_visibility))
            if not all(visibility):
                raise RuntimeError(
                    "fixed-trace element cache publication is not visible "
                    f"on all MPI ranks: {visibility}"
                )
            status = "persistent_fixed_trace_element_cache_cold_write"
    if cache_hit:
        cold_builder_profile = None

    from mpi4py import MPI

    def max_value(value: float) -> float:
        return float(comm.allreduce(float(value), op=MPI.MAX))

    audit = {
        "schema_version": _CACHE_SCHEMA,
        "status": status,
        "mode": mode,
        "cache_hit_on_all_ranks": bool(cache_hit),
        "cache_miss_on_all_ranks": not bool(cache_hit),
        "identity": identity,
        "identity_sha256": digest,
        "manifest_path": str(manifest_path),
        "payload_path": str(payload_path),
        "read_seconds_max": max_value(read_audit.get("read_seconds_local", 0.0)),
        "reconstruct_seconds_max": max_value(
            read_audit.get("reconstruct_seconds_local", 0.0)
        ),
        "signature_seconds_max": max_value(
            read_audit.get("signature_seconds_local", 0.0)
        ),
        "build_seconds_max": max_value(build_seconds_local),
        "write_seconds_max": max_value(write_seconds_local),
        "payload_sha256": (
            read_audit.get("payload_sha256")
            or publication.get("payload_sha256")
        ),
        "element_signature_sha256": (
            read_audit.get("element_signature_sha256")
            or publication.get("element_signature_sha256")
            or custom_element_sha256(element)
        ),
        "payload_array_count": publication.get("payload_array_count"),
        "payload_bytes": publication.get("payload_bytes"),
        "cold_builder_profile": cold_builder_profile,
        "serialization": "json_plus_npz_allow_pickle_false",
        "ordinary_default_changed": False,
        "publication_lock": "exclusive_identity_lockfile",
        "publication_parent_directory_fsync": True,
    }
    return element, audit


__all__ = [
    "FixedTraceElementBuild",
    "fixed_trace_element_build",
    "load_or_build_fixed_trace_element",
]
