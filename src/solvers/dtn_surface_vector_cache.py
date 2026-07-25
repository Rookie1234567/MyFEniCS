"""Fail-closed persistent cache for assembled DtN surface vectors.

The Stage-4 auxiliary DtN operator repeatedly assembles the same two
unconstrained tangential component vectors for every polarization of a
Floquet order.  In the Task035b assembly-time-condensed path those vectors
are independent of the cell Schur construction and can be reused across
identical offline/online runs.

This cache is deliberately opt-in and rank-partition-bound.  It stores only
owned entries of the original unconstrained FE vectors, publishes a manifest
after the payload, verifies a logical content checksum, and treats every
identity or payload discrepancy as a cache miss.  The ordinary DtN path does
not instantiate this class.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import sys
from time import perf_counter
from typing import Any, Mapping, Sequence
from uuid import uuid4
from zipfile import BadZipFile

import basix
import dolfinx
from dolfinx.fem import petsc as fem_petsc
from mpi4py import MPI, __version__ as mpi4py_version
import numpy as np
from petsc4py import PETSc, __version__ as petsc4py_version


_CACHE_SCHEMA = "task035b.dtn-surface-vector-persistent-cache.v1"
_MANIFEST_SCHEMA = "task035b.dtn-surface-vector-cache-manifest.v1"
_SOURCE_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_VALID_MODES = {"read_only", "read_write", "refresh"}


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def _canonical_value(value: Any) -> Any:
    """Return a JSON-safe identity value without lossy complex conversion."""

    if isinstance(value, (complex, np.complexfloating)):
        number = complex(value)
        return {
            "complex128_real_hex": float(number.real).hex(),
            "complex128_imag_hex": float(number.imag).hex(),
        }
    if isinstance(value, (float, np.floating)):
        return {"float64_hex": float(value).hex()}
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, str) or value is None:
        return value
    if isinstance(value, np.ndarray):
        return [_canonical_value(item) for item in value.tolist()]
    if isinstance(value, Mapping):
        return {
            str(key): _canonical_value(item)
            for key, item in sorted(
                value.items(),
                key=lambda pair: str(pair[0]),
            )
        }
    if isinstance(value, (tuple, list)):
        return [_canonical_value(item) for item in value]
    raise TypeError(
        "DtN surface-vector cache identity contains unsupported value "
        f"{type(value).__name__}"
    )


def _array_content_sha256(
    array: Any,
    *,
    namespace: bytes,
) -> str:
    canonical = np.ascontiguousarray(np.asarray(array))
    digest = hashlib.sha256()
    digest.update(namespace)
    digest.update(b"\0")
    digest.update(canonical.dtype.str.encode("ascii"))
    digest.update(b"\0")
    digest.update(
        _canonical_json(list(canonical.shape)).encode("ascii")
    )
    digest.update(b"\0")
    digest.update(canonical.tobytes(order="C"))
    return digest.hexdigest()


def _tag_identity(tags: Any, *, namespace: bytes) -> dict[str, Any]:
    if tags is None:
        return {"present": False}
    indices = np.asarray(tags.indices)
    values = np.asarray(tags.values)
    return {
        "present": True,
        "indices_sha256": _array_content_sha256(
            indices,
            namespace=namespace + b".indices",
        ),
        "values_sha256": _array_content_sha256(
            values,
            namespace=namespace + b".values",
        ),
        "indices_count": int(indices.size),
        "values_count": int(values.size),
    }


def _index_map_identity(index_map: Any) -> dict[str, Any]:
    return {
        "local_range": [int(value) for value in index_map.local_range],
        "size_local": int(index_map.size_local),
        "size_global": int(index_map.size_global),
        "num_ghosts": int(index_map.num_ghosts),
        "ghosts_sha256": _array_content_sha256(
            np.asarray(index_map.ghosts, dtype=np.int64),
            namespace=b"task035b.dtn-cache.index-map-ghosts.v1",
        ),
        "owners_sha256": _array_content_sha256(
            np.asarray(index_map.owners, dtype=np.int32),
            namespace=b"task035b.dtn-cache.index-map-owners.v1",
        ),
    }


def _trace_projection_identity(trace_constraints: Any) -> dict[str, Any]:
    """Hash the exact full-trace to active-coordinate expansion."""

    digest = hashlib.sha256()
    digest.update(b"task035b.dtn-cache.trace-projection.v1\0")
    expansion = trace_constraints.expansion_by_original
    for original in sorted(expansion):
        active_ids, coefficients = expansion[original]
        digest.update(
            np.asarray([int(original)], dtype="<i8").tobytes()
        )
        digest.update(
            np.ascontiguousarray(
                np.asarray(active_ids, dtype="<i8")
            ).tobytes()
        )
        digest.update(b"\0")
        digest.update(
            np.ascontiguousarray(
                np.asarray(coefficients, dtype="<c16")
            ).tobytes()
        )
        digest.update(b"\0")
    owned_active_rows = getattr(
        trace_constraints,
        "owned_active_rows",
        None,
    )
    if owned_active_rows is None:
        owned_active_rows = np.empty(0, dtype=np.int64)
    return {
        "schema_version": "task035b.dtn-trace-projection-identity.v1",
        "full_trace_rows": int(trace_constraints.full_trace_rows),
        "active_rows": int(trace_constraints.active_rows),
        "slave_rows": int(trace_constraints.slave_rows),
        "active_coordinates_are_original_trace_dofs": bool(
            trace_constraints.active_coordinates_are_original_trace_dofs
        ),
        "owned_active_rows_sha256": _array_content_sha256(
            np.asarray(owned_active_rows, dtype=np.int64),
            namespace=b"task035b.dtn-cache.owned-active-rows.v1",
        ),
        "expansion_row_count": int(len(expansion)),
        "expansion_sha256": digest.hexdigest(),
        "build_audit_sha256": hashlib.sha256(
            _canonical_json(
                _canonical_value(trace_constraints.build_audit)
            ).encode("ascii")
        ).hexdigest(),
    }


def _mesh_and_space_identity(
    function_space: Any,
    mesh_data: Any,
) -> dict[str, Any]:
    mesh = mesh_data.mesh
    topology = mesh.topology
    topology_index_map = topology.index_map(topology.dim)
    geometry_dofmap = np.asarray(mesh.geometry.dofmap)
    space_dofmap = np.asarray(function_space.dofmap.list)
    element = function_space.element.basix_element
    return {
        "mesh": {
            "topological_dimension": int(topology.dim),
            "geometric_dimension": int(mesh.geometry.dim),
            "cell_type": str(mesh.basix_cell()),
            "topology_index_map": _index_map_identity(
                topology_index_map
            ),
            "geometry_x_sha256": _array_content_sha256(
                np.asarray(mesh.geometry.x),
                namespace=b"task035b.dtn-cache.geometry-x.v1",
            ),
            "geometry_dofmap_sha256": _array_content_sha256(
                geometry_dofmap,
                namespace=b"task035b.dtn-cache.geometry-dofmap.v1",
            ),
            "cell_tags": _tag_identity(
                getattr(mesh_data, "cell_tags", None),
                namespace=b"task035b.dtn-cache.cell-tags.v1",
            ),
            "boundary_facet_tags": _tag_identity(
                getattr(mesh_data, "facet_tags", None),
                namespace=b"task035b.dtn-cache.facet-tags.v1",
            ),
        },
        "function_space": {
            "element_hash": int(element.hash()),
            "element_family": str(element.family),
            "element_cell_type": str(element.cell_type),
            "element_degree": int(element.degree),
            "element_map_type": str(element.map_type),
            "element_value_shape": list(element.value_shape),
            "dofmap_sha256": _array_content_sha256(
                space_dofmap,
                namespace=b"task035b.dtn-cache.function-dofmap.v1",
            ),
            "dofmap_block_size": int(function_space.dofmap.bs),
            "index_map_block_size": int(
                function_space.dofmap.index_map_bs
            ),
            "index_map": _index_map_identity(
                function_space.dofmap.index_map
            ),
        },
    }


def dtn_surface_vector_descriptor(
    *,
    side: str,
    m: int,
    n: int,
    alpha: complex,
    gamma: complex,
    kz: complex,
    boundary_referenced: bool,
    boundary_reference_z: float | None,
    boundary_tag: int,
    component: int,
) -> dict[str, Any]:
    """Build one typed identity for an x/y surface-vector component."""

    if side not in {"top", "bottom"}:
        raise ValueError("DtN surface-vector side must be top or bottom")
    if component not in {0, 1}:
        raise ValueError("DtN surface-vector component must be 0 or 1")
    if boundary_referenced != (boundary_reference_z is not None):
        raise ValueError(
            "boundary-reference flag and coordinate must agree"
        )
    return {
        "schema_version": "task035b.dtn-surface-vector-descriptor.v1",
        "side": side,
        "m": int(m),
        "n": int(n),
        "alpha": complex(alpha),
        "gamma": complex(gamma),
        "kz": complex(kz),
        "boundary_referenced": bool(boundary_referenced),
        "boundary_reference_z": boundary_reference_z,
        "boundary_tag": int(boundary_tag),
        "component": int(component),
        "phase_convention": (
            "exp(i*alpha*x+i*gamma*y+i*kz*(z-z_port))"
            if boundary_referenced
            else "exp(i*alpha*x+i*gamma*y+i*kz*z)"
        ),
    }


def _bundle_content_sha256(
    arrays: Mapping[str, np.ndarray],
) -> str:
    digest = hashlib.sha256()
    digest.update(b"task035b.dtn-surface-vector-content.v1\0")
    for name in sorted(arrays):
        canonical = np.ascontiguousarray(arrays[name])
        digest.update(name.encode("ascii"))
        digest.update(b"\0")
        digest.update(
            _array_content_sha256(
                canonical,
                namespace=b"task035b.dtn-surface-vector-array.v1",
            ).encode("ascii")
        )
        digest.update(b"\0")
    return digest.hexdigest()


class PersistentDtnSurfaceVectorCache:
    """One rank-local, content-addressed bundle of DtN component vectors."""

    def __init__(
        self,
        *,
        function_space: Any,
        mesh_data: Any,
        trace_constraints: Any,
        descriptors: Sequence[Mapping[str, Any]],
        mode_inventory: Sequence[Mapping[str, Any]],
        quadrature_degree: int,
        directory: Path,
        source_sha: str,
        mode: str,
    ) -> None:
        self.function_space = function_space
        self.comm = mesh_data.mesh.comm
        self.mode = str(mode).lower()
        if self.mode not in _VALID_MODES:
            raise ValueError(
                "DtN surface-vector cache mode must be read_only, "
                "read_write, or refresh"
            )
        self.source_sha = str(source_sha).lower()
        if _SOURCE_SHA_PATTERN.fullmatch(self.source_sha) is None:
            raise ValueError(
                "DtN surface-vector cache requires a full source Git SHA"
            )
        self.directory = Path(directory).resolve()
        if self.mode in {"read_write", "refresh"}:
            if self.comm.rank == 0:
                self.directory.mkdir(parents=True, exist_ok=True)
            self.comm.barrier()

        identity_started = perf_counter()
        self.descriptors = tuple(
            _canonical_value(dict(descriptor))
            for descriptor in descriptors
        )
        descriptor_json = tuple(
            _canonical_json(descriptor)
            for descriptor in self.descriptors
        )
        if len(set(descriptor_json)) != len(descriptor_json):
            raise ValueError(
                "DtN surface-vector cache descriptors must be unique"
            )
        self._descriptor_to_index = {
            descriptor: index
            for index, descriptor in enumerate(descriptor_json)
        }
        self._array_names = tuple(
            f"vector_{index:04d}"
            for index in range(len(self.descriptors))
        )
        vector_probe = fem_petsc.create_vector(function_space)
        try:
            self._owned_size = int(vector_probe.getLocalSize())
            self._global_size = int(vector_probe.getSize())
            self._ownership_range = [
                int(value)
                for value in vector_probe.getOwnershipRange()
            ]
        finally:
            vector_probe.destroy()

        self.identity = {
            "schema_version": (
                "task035b.dtn-surface-vector-cache-identity.v1"
            ),
            "source_commit_sha": self.source_sha,
            "mpi_size": int(self.comm.size),
            "mpi_rank": int(self.comm.rank),
            "quadrature_degree": int(quadrature_degree),
            "mode_inventory": [
                _canonical_value(dict(item))
                for item in mode_inventory
            ],
            "surface_vector_descriptors": list(self.descriptors),
            "mesh_and_function_space": _mesh_and_space_identity(
                function_space,
                mesh_data,
            ),
            "trace_projection": _trace_projection_identity(
                trace_constraints
            ),
            "vector_layout": {
                "global_size": self._global_size,
                "local_owned_size": self._owned_size,
                "ownership_range": self._ownership_range,
            },
            "abi": {
                "python_version": sys.version,
                "numpy_version": np.__version__,
                "dolfinx_version": dolfinx.__version__,
                "basix_version": basix.__version__,
                "petsc4py_version": petsc4py_version,
                "mpi4py_version": mpi4py_version,
                "petsc_version": list(PETSc.Sys.getVersion()),
                "mpi_library_version": MPI.Get_library_version(),
                "petsc_scalar_dtype": np.dtype(PETSc.ScalarType).str,
                "petsc_int_dtype": np.dtype(PETSc.IntType).str,
            },
        }
        identity_json = _canonical_json(self.identity)
        self.identity_sha256 = hashlib.sha256(
            identity_json.encode("ascii")
        ).hexdigest()
        self.payload_path = self.directory / (
            f"dtn_surface_vectors_{self.identity_sha256}.npz"
        )
        self.manifest_path = self.payload_path.with_suffix(".json")
        self.identity_seconds_local = (
            perf_counter() - identity_started
        )

        self._loaded: dict[int, np.ndarray] | None = None
        self._recorded: dict[int, np.ndarray] = {}
        self._load_attempted = False
        self._hit = False
        self._miss_reason: str | None = None
        self._local_artifact_hit = False
        self._local_miss_reason: str | None = None
        self._load_outcomes_by_rank: list[dict[str, Any]] = []
        self._read_seconds_local = 0.0
        self._write_seconds_local = 0.0
        self._read_bytes_local = 0
        self._write_bytes_local = 0
        self._restores = 0
        self._records = 0
        self._writes = 0
        self._finalized = False

    @property
    def hit(self) -> bool:
        return self._hit

    def _descriptor_index(
        self,
        descriptor: Mapping[str, Any],
    ) -> int:
        key = _canonical_json(_canonical_value(dict(descriptor)))
        try:
            return self._descriptor_to_index[key]
        except KeyError as error:
            raise KeyError(
                "DtN surface-vector descriptor is outside the cache identity"
            ) from error

    def load(self) -> bool:
        """Collectively load a bundle or make every rank rebuild.

        A rank-local hit is not sufficient: the solver must either restore
        vectors on every rank or assemble them on every rank.  This
        all-or-nothing decision prevents a missing/corrupt artifact on one
        rank from sending the distributed modal loop down different code
        paths.
        """

        if self._load_attempted:
            return self._hit
        self._load_attempted = True
        loaded: dict[int, np.ndarray] | None = None
        local_reason: str | None = None
        if self.mode == "refresh":
            local_reason = "refresh_mode_forces_rebuild"
        else:
            started = perf_counter()
            try:
                for path in (
                    self.payload_path,
                    self.manifest_path,
                ):
                    try:
                        self._read_bytes_local += int(
                            path.stat().st_size
                        )
                    except OSError:
                        pass
                try:
                    loaded, local_reason = self._load_bundle()
                except Exception as error:
                    loaded = None
                    local_reason = (
                        "unexpected_cache_read_error:"
                        f"{type(error).__name__}"
                    )
            finally:
                self._read_seconds_local += (
                    perf_counter() - started
                )
        self._local_artifact_hit = loaded is not None
        self._local_miss_reason = local_reason
        self._load_outcomes_by_rank = self.comm.allgather(
            {
                "rank": int(self.comm.rank),
                "local_artifact_hit": self._local_artifact_hit,
                "local_miss_reason": local_reason,
            }
        )
        collective_hit = all(
            outcome["local_artifact_hit"]
            for outcome in self._load_outcomes_by_rank
        )
        if not collective_hit:
            # A rank that read a valid bundle must release it as well.  The
            # distributed solver will now follow the same assembly branch on
            # every rank.
            loaded = None
            self._loaded = None
            self._miss_reason = (
                local_reason
                if local_reason is not None
                else "collective_peer_artifact_miss"
            )
            return False
        if loaded is None:
            raise RuntimeError(
                "collective DtN cache hit lacks a rank-local payload"
            )
        self._loaded = loaded
        self._hit = True
        return True

    def _load_bundle(
        self,
    ) -> tuple[dict[int, np.ndarray] | None, str | None]:
        if (
            not self.payload_path.is_file()
            or not self.manifest_path.is_file()
        ):
            return None, "artifact_or_manifest_missing"
        try:
            with self.manifest_path.open(
                "r",
                encoding="utf-8",
            ) as stream:
                manifest = json.load(stream)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None, "manifest_unreadable"
        if not isinstance(manifest, dict):
            return None, "manifest_not_an_object"
        if manifest.get("schema_version") != _MANIFEST_SCHEMA:
            return None, "manifest_schema_mismatch"
        if manifest.get("identity_sha256") != self.identity_sha256:
            return None, "identity_sha256_mismatch"
        if _canonical_json(manifest.get("identity")) != _canonical_json(
            self.identity
        ):
            return None, "identity_payload_mismatch"
        if manifest.get("payload_filename") != self.payload_path.name:
            return None, "payload_filename_mismatch"
        try:
            payload_size = int(self.payload_path.stat().st_size)
        except OSError:
            return None, "payload_stat_failed"
        if manifest.get("payload_size_bytes") != payload_size:
            return None, "payload_size_mismatch"
        try:
            with np.load(
                self.payload_path,
                allow_pickle=False,
            ) as archive:
                if tuple(sorted(archive.files)) != tuple(
                    sorted(self._array_names)
                ):
                    return None, "payload_member_inventory_mismatch"
                arrays = {
                    name: np.asarray(archive[name]).copy()
                    for name in self._array_names
                }
        except (OSError, ValueError, KeyError, EOFError, BadZipFile):
            return None, "payload_unreadable"
        expected_metadata = {
            name: {
                "shape": [self._owned_size],
                "dtype": np.dtype(np.complex128).str,
            }
            for name in self._array_names
        }
        actual_metadata = {
            name: {
                "shape": list(array.shape),
                "dtype": array.dtype.str,
            }
            for name, array in arrays.items()
        }
        if (
            manifest.get("arrays") != expected_metadata
            or actual_metadata != expected_metadata
        ):
            return None, "array_metadata_mismatch"
        if manifest.get("content_sha256") != _bundle_content_sha256(
            arrays
        ):
            return None, "payload_checksum_mismatch"
        return {
            index: np.ascontiguousarray(
                arrays[name],
                dtype=np.complex128,
            )
            for index, name in enumerate(self._array_names)
        }, None

    def restore_vector(
        self,
        descriptor: Mapping[str, Any],
    ) -> PETSc.Vec:
        if not self._hit or self._loaded is None:
            raise RuntimeError(
                "DtN surface-vector cache restore requires a validated hit"
            )
        index = self._descriptor_index(descriptor)
        try:
            values = self._loaded.pop(index)
        except KeyError as error:
            raise RuntimeError(
                "DtN surface-vector cache component was restored twice "
                "or is missing"
            ) from error
        vector = fem_petsc.create_vector(self.function_space)
        owned = vector.getArray()
        if owned.shape != (self._owned_size,):
            vector.destroy()
            raise RuntimeError(
                "restored DtN vector ownership differs from cache identity"
            )
        owned[:] = values
        vector.ghostUpdate(
            addv=PETSc.InsertMode.INSERT_VALUES,
            mode=PETSc.ScatterMode.FORWARD,
        )
        self._restores += 1
        return vector

    def record_vector(
        self,
        descriptor: Mapping[str, Any],
        vector: PETSc.Vec,
    ) -> None:
        if self._hit:
            raise RuntimeError(
                "DtN surface-vector cache may not record after a hit"
            )
        index = self._descriptor_index(descriptor)
        if index in self._recorded:
            raise RuntimeError(
                "DtN surface-vector cache component was recorded twice"
            )
        if int(vector.getSize()) != self._global_size or [
            int(value) for value in vector.getOwnershipRange()
        ] != self._ownership_range:
            raise ValueError(
                "DtN surface vector layout differs from cache identity"
            )
        owned = np.asarray(
            vector.getArray(readonly=True),
            dtype=np.complex128,
        )
        if owned.shape != (self._owned_size,):
            raise ValueError(
                "DtN surface vector local size differs from cache identity"
            )
        self._recorded[index] = np.ascontiguousarray(owned).copy()
        self._records += 1

    def _write_bundle(self) -> None:
        if len(self._recorded) != len(self.descriptors):
            missing = sorted(set(range(len(self.descriptors))) - set(
                self._recorded
            ))
            raise RuntimeError(
                "DtN surface-vector cache cannot publish an incomplete "
                f"bundle; missing descriptor indices {missing[:8]}"
            )
        arrays = {
            name: self._recorded[index]
            for index, name in enumerate(self._array_names)
        }
        suffix = (
            f"rank{self.comm.rank}.pid{os.getpid()}."
            f"{uuid4().hex}.tmp"
        )
        temporary_payload = self.payload_path.with_name(
            f".{self.payload_path.name}.{suffix}"
        )
        temporary_manifest = self.manifest_path.with_name(
            f".{self.manifest_path.name}.{suffix}"
        )
        try:
            with temporary_payload.open("wb") as stream:
                np.savez(stream, **arrays)
                stream.flush()
                os.fsync(stream.fileno())
            manifest = {
                "schema_version": _MANIFEST_SCHEMA,
                "identity_sha256": self.identity_sha256,
                "identity": self.identity,
                "payload_filename": self.payload_path.name,
                "payload_size_bytes": int(
                    temporary_payload.stat().st_size
                ),
                "arrays": {
                    name: {
                        "shape": list(array.shape),
                        "dtype": array.dtype.str,
                    }
                    for name, array in arrays.items()
                },
                "content_sha256": _bundle_content_sha256(arrays),
                "pickle_used": False,
            }
            with temporary_manifest.open(
                "w",
                encoding="utf-8",
            ) as stream:
                json.dump(
                    manifest,
                    stream,
                    ensure_ascii=True,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_payload, self.payload_path)
            os.replace(temporary_manifest, self.manifest_path)
        finally:
            for temporary in (
                temporary_payload,
                temporary_manifest,
            ):
                try:
                    temporary.unlink()
                except FileNotFoundError:
                    pass

    def finalize(self) -> dict[str, Any]:
        """Publish a complete miss bundle when permitted and return audit."""

        if self._finalized:
            raise RuntimeError(
                "DtN surface-vector cache was finalized twice"
            )
        self._finalized = True
        if not self._load_attempted:
            raise RuntimeError(
                "DtN surface-vector cache must attempt load before finalize"
            )
        local_error: str | None = None
        if (
            not self._hit
            and self.mode in {"read_write", "refresh"}
        ):
            started = perf_counter()
            try:
                self._write_bundle()
                self._writes = 1
                self._write_bytes_local = int(
                    self.payload_path.stat().st_size
                    + self.manifest_path.stat().st_size
                )
            except Exception as error:
                local_error = f"{type(error).__name__}: {error}"
            finally:
                self._write_seconds_local += (
                    perf_counter() - started
                )
        errors = self.comm.allgather(local_error)
        if any(error is not None for error in errors):
            raise RuntimeError(
                "persistent DtN surface-vector cache publication failed: "
                + "; ".join(
                    f"rank {rank}: {error}"
                    for rank, error in enumerate(errors)
                    if error is not None
                )
            )

        remaining_loaded = (
            0 if self._loaded is None else len(self._loaded)
        )
        if self._hit and remaining_loaded:
            raise RuntimeError(
                "validated DtN cache hit did not consume every component "
                f"vector; {remaining_loaded} remain"
            )
        self._loaded = None
        self._recorded.clear()

        hit_count = int(self.comm.allreduce(
            int(self._hit),
            op=MPI.SUM,
        ))
        miss_count = int(self.comm.size - hit_count)
        restore_count = int(self.comm.allreduce(
            self._restores,
            op=MPI.SUM,
        ))
        record_count = int(self.comm.allreduce(
            self._records,
            op=MPI.SUM,
        ))
        write_count = int(self.comm.allreduce(
            self._writes,
            op=MPI.SUM,
        ))
        read_seconds = float(self.comm.allreduce(
            self._read_seconds_local,
            op=MPI.MAX,
        ))
        write_seconds = float(self.comm.allreduce(
            self._write_seconds_local,
            op=MPI.MAX,
        ))
        identity_seconds = float(self.comm.allreduce(
            self.identity_seconds_local,
            op=MPI.MAX,
        ))
        read_bytes = int(self.comm.allreduce(
            self._read_bytes_local,
            op=MPI.SUM,
        ))
        write_bytes = int(self.comm.allreduce(
            self._write_bytes_local,
            op=MPI.SUM,
        ))
        miss_reasons = self.comm.allgather(self._miss_reason)
        local_artifact_hit_count = int(self.comm.allreduce(
            int(self._local_artifact_hit),
            op=MPI.SUM,
        ))
        local_miss_reasons = [
            outcome["local_miss_reason"]
            for outcome in self._load_outcomes_by_rank
        ]
        global_miss_reasons = sorted(
            {
                reason
                for reason in local_miss_reasons
                if reason is not None
            }
        )
        return {
            "schema_version": _CACHE_SCHEMA,
            "enabled": True,
            "mode": self.mode,
            "source_commit_sha": self.source_sha,
            "directory": str(self.directory),
            "identity_sha256_by_rank": self.comm.allgather(
                self.identity_sha256
            ),
            "identity_binds": [
                "source_commit_sha",
                "mesh_geometry_and_boundary_facet_tags",
                "function_space_element_and_dofmap",
                "full_selected_mode_inventory",
                "surface_phase_and_component_descriptors",
                "surface_quadrature_degree",
                "full_trace_to_active_projection",
                "mpi_rank_partition_and_vector_ownership",
                "python_numpy_dolfinx_basix_petsc_mpi_abi",
            ],
            "identity_is_rank_partition_bound": True,
            "cross_mpi_partition_reuse": False,
            "hit_count_sum": hit_count,
            "miss_count_sum": miss_count,
            "hit_on_all_ranks": hit_count == self.comm.size,
            "collective_all_or_nothing": True,
            "local_artifact_hit_count_sum": (
                local_artifact_hit_count
            ),
            "local_artifact_hit_on_all_ranks": (
                local_artifact_hit_count == self.comm.size
            ),
            "local_load_outcomes_by_rank": (
                self._load_outcomes_by_rank
            ),
            "local_miss_reasons_by_rank": local_miss_reasons,
            "global_collective_miss_reasons": global_miss_reasons,
            "restore_count_sum": restore_count,
            "record_count_sum": record_count,
            "write_count_sum": write_count,
            "descriptor_count_per_rank": len(self.descriptors),
            "read_seconds_max": read_seconds,
            "identity_and_key_seconds_max": identity_seconds,
            "write_seconds_max": write_seconds,
            "read_bytes_sum": read_bytes,
            "write_bytes_sum": write_bytes,
            "miss_reasons_by_rank": miss_reasons,
            "stages_skipped_on_hit": [
                "surface_form_construction_and_JIT",
                "surface_vector_assembly",
            ],
            "trace_projection_recomputed_after_restore": True,
            "payload_arrays_released_before_mumps_symbolic": True,
            "manifest_published_after_payload": True,
            "content_checksum_verified": True,
            "pickle_used": False,
            "identity_or_payload_mismatch_is_fail_closed": True,
            "inactive_modes_stored": False,
            "ordinary_default_changed": False,
        }


def disabled_dtn_surface_vector_cache_audit() -> dict[str, Any]:
    """Return an explicit audit when the ordinary cache-off path is used."""

    return {
        "schema_version": _CACHE_SCHEMA,
        "enabled": False,
        "mode": "off",
        "source_commit_sha": None,
        "directory": None,
        "hit_count_sum": 0,
        "miss_count_sum": 0,
        "hit_on_all_ranks": False,
        "restore_count_sum": 0,
        "record_count_sum": 0,
        "write_count_sum": 0,
        "read_seconds_max": 0.0,
        "identity_and_key_seconds_max": 0.0,
        "write_seconds_max": 0.0,
        "read_bytes_sum": 0,
        "write_bytes_sum": 0,
        "inactive_modes_stored": False,
        "ordinary_default_changed": False,
    }


__all__ = [
    "PersistentDtnSurfaceVectorCache",
    "disabled_dtn_surface_vector_cache_audit",
    "dtn_surface_vector_descriptor",
]
