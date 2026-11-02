"""Opt-in exact carrier checkpoints with live numerical identity.

This new namespace includes q and sparse-cutoff identity explicitly. It does
not relax or import the legacy q160 provider's qualification checks.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

import numpy as np

from .parallel_tensor_cache import atomic_json, digest


class CarrierCheckpoint:
    def __init__(
        self,
        root,
        context,
        *,
        disk_reserve_bytes=10737418240,
        max_shard_bytes=1073741824,
    ):
        self.disk_reserve_bytes = int(disk_reserve_bytes)
        self.max_shard_bytes = int(max_shard_bytes)
        if self.disk_reserve_bytes < 0 or self.max_shard_bytes <= 0:
            raise ValueError("invalid checkpoint disk budget")
        required = {
            "numerical_source_sha256",
            "mesh_sha256",
            "space_sha256",
            "mpc_sha256",
            "boundary_sha256",
            "material_incidence_sha256",
            "mode_manifest_sha256",
            "surface_quadrature_degree",
            "quadrature_rule",
            "sparse_cutoff_policy",
            "sparse_cutoff_relative_tolerance",
            "global_rows",
            "scalar_dtype",
            "row_dtype",
        }
        if required - context.keys():
            raise ValueError("carrier numerical identity is incomplete")
        for name in required:
            if name.endswith("sha256"):
                value = context[name]
                if (
                    not isinstance(value, str)
                    or len(value) != 64
                    or any(c not in "0123456789abcdef" for c in value)
                ):
                    raise ValueError("invalid carrier identity hash")
        if context["scalar_dtype"] != "complex128" or context["row_dtype"] != "int64":
            raise ValueError("unsupported carrier precision/index type")
        if (
            int(context["global_rows"]) <= 0
            or int(context["surface_quadrature_degree"]) <= 0
        ):
            raise ValueError("invalid carrier rows/quadrature")
        tolerance = float(context["sparse_cutoff_relative_tolerance"])
        if not 0 < tolerance < 1:
            raise ValueError("invalid sparse cutoff tolerance")
        self.context = json.loads(json.dumps(context, allow_nan=False, sort_keys=True))
        self.context_sha = hashlib.sha256(
            json.dumps(self.context, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        self.root = Path(root) / "carrier-checkpoint-v2" / self.context_sha
        self.root.mkdir(parents=True, exist_ok=True)

    def _identity(self, index, mode):
        if int(index) < 0 or set(mode) != {"side", "m", "n", "polarization"}:
            raise ValueError("invalid mode identity")
        if mode["side"] not in {"top", "bottom"} or mode["polarization"] not in {
            "s",
            "p",
        }:
            raise ValueError("invalid mode side/polarization")
        return {
            "context_sha256": self.context_sha,
            "mode_index": int(index),
            "mode": mode,
        }

    def _validate(self, arrays, normalization_h):
        if not np.isfinite(normalization_h) or normalization_h <= 0:
            raise ValueError("normalization H must be positive and finite")
        expected = {
            "coupling_rows",
            "coupling_values",
            "projection_rows",
            "projection_values",
        }
        if set(arrays) != expected:
            raise ValueError("carrier arrays incomplete")
        for prefix in ("coupling", "projection"):
            rows, values = arrays[prefix + "_rows"], arrays[prefix + "_values"]
            if rows.dtype != np.dtype("int64") or values.dtype != np.dtype(
                "complex128"
            ):
                raise ValueError("carrier dtype changed")
            if (
                rows.ndim != 1
                or values.shape != rows.shape
                or not np.isfinite(values).all()
            ):
                raise ValueError("carrier shape/finite check failed")
            if rows.size and (
                rows.min() < 0 or rows.max() >= int(self.context["global_rows"])
            ):
                raise ValueError("carrier row outside bound space")
            if np.unique(rows).size != rows.size:
                raise ValueError("duplicate carrier rows")

    def load(self, index, mode):
        expected = self._identity(index, mode)
        folder = self.root / str(index)
        marker = folder / "complete.json"
        if not marker.exists():
            return None
        metadata = json.loads(marker.read_text())
        if metadata["identity"] != expected:
            raise ValueError("mode identity mismatch")
        payload = folder / "arrays.npz"
        if digest(payload) != metadata["payload_sha256"]:
            raise ValueError("carrier shard hash mismatch")
        with np.load(payload, allow_pickle=False) as packed:
            arrays = {name: packed[name] for name in packed.files}
        self._validate(arrays, metadata["normalization_h"])
        for array in arrays.values():
            array.flags.writeable = False
        return {"arrays": arrays, "normalization_h": metadata["normalization_h"]}

    def commit(self, index, mode, arrays, normalization_h):
        expected = self._identity(index, mode)
        self._validate(arrays, normalization_h)
        payload_bytes = sum(array.nbytes for array in arrays.values())
        if (
            payload_bytes > self.max_shard_bytes
            or shutil.disk_usage(self.root).free
            < self.disk_reserve_bytes + payload_bytes + 65536
        ):
            raise RuntimeError("carrier checkpoint disk budget exceeded")
        folder = self.root / str(index)
        folder.mkdir(parents=True, exist_ok=True)
        with (folder / "writer.lock").open("a") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            existing = self.load(index, mode)
            if existing is not None:
                if existing["normalization_h"] != normalization_h or any(
                    existing["arrays"][name].tobytes() != array.tobytes()
                    for name, array in arrays.items()
                ):
                    raise ValueError("refusing conflicting carrier shard overwrite")
                return
            fd, temporary = tempfile.mkstemp(prefix=".pending-", dir=folder)
            try:
                with os.fdopen(fd, "wb") as stream:
                    np.savez(stream, **arrays)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, folder / "arrays.npz")
                atomic_json(
                    folder / "complete.json",
                    {
                        "identity": expected,
                        "normalization_h": float(normalization_h),
                        "payload_sha256": digest(folder / "arrays.npz"),
                    },
                )
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)

    def restore_prefix(self, modes):
        result = []
        for index, mode in enumerate(modes):
            entry = self.load(index, mode)
            if entry is None:
                break
            result.append(entry)
        return result


def live_context(
    mpc,
    cfg,
    assemblers,
    *,
    mode_manifest_sha256,
    degree,
    quadrature_degree,
    cutoff_policy,
    cutoff_relative_tolerance,
    numerical_source_sha256,
):
    """Derive checkpoint identity from the live MPI1 storage, not caller claims."""
    if mpc.function_space.mesh.comm.size != 1:
        raise ValueError("carrier checkpoints currently require MPI1")
    V = mpc.function_space
    msh = V.mesh

    def arrays_hash(*arrays):
        h = hashlib.sha256()
        for array in arrays:
            a = np.ascontiguousarray(array)
            h.update(str(a.shape).encode())
            h.update(a.dtype.str.encode())
            h.update(memoryview(a).cast("B"))
        return h.hexdigest()

    coeff, offsets = mpc.coefficients()
    masters = mpc.masters
    if hasattr(masters, "array"):
        master_array = masters.array
    else:
        master_array = np.concatenate(
            [np.asarray(masters.links(int(s))) for s in mpc.slaves]
        )
    boundary = []
    for key, assembler in sorted(assemblers.items()):
        tags = assembler.mesh_data.facet_tags
        boundary.extend(
            (
                np.asarray(tags.indices),
                np.asarray(tags.values),
                np.asarray([assembler.tag, assembler.component]),
            )
        )
    # Cache reuse is also bound to the actual loaded numerical extension binaries.
    import basix
    import dolfinx
    import dolfinx_mpc
    import ffcx
    from petsc4py import PETSc

    extensions = (basix._basixcpp, dolfinx.cpp, dolfinx_mpc.cpp, PETSc)
    abi = {module.__name__: digest(module.__file__) for module in extensions}
    abi["ffcx_version"] = ffcx.__version__
    abi["numpy_version"] = np.__version__
    cfg_bytes = json.dumps(cfg.as_jsonable(), sort_keys=True, allow_nan=False).encode()
    return {
        "numerical_source_sha256": numerical_source_sha256,
        "runtime_abi": abi,
        "mesh_sha256": arrays_hash(msh.geometry.x, msh.geometry.dofmap),
        "space_sha256": arrays_hash(
            V.dofmap.list,
            np.asarray([degree, V.element.basix_element.hash()], dtype=np.uint64),
        ),
        "mpc_sha256": arrays_hash(mpc.slaves, master_array, coeff, offsets),
        "boundary_sha256": arrays_hash(*boundary),
        "material_incidence_sha256": hashlib.sha256(cfg_bytes).hexdigest(),
        "mode_manifest_sha256": mode_manifest_sha256,
        "surface_quadrature_degree": int(quadrature_degree),
        "quadrature_rule": "default",
        "sparse_cutoff_policy": cutoff_policy,
        "sparse_cutoff_relative_tolerance": float(cutoff_relative_tolerance),
        "global_rows": int(V.dofmap.index_map.size_global),
        "scalar_dtype": "complex128",
        "row_dtype": "int64",
    }
