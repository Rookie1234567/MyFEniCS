"""Run-local immutable storage for the existing complete Y-orbit transforms.

This module has no FE imports and supplies no orientation mathematics. The
caller supplies the existing physical/Basix builder for each actual state.
All channels remain; matrices and lazy inverses have immutable byte backing.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from importlib import metadata
import json
import marshal
import sys
import weakref

import numpy as np


SCHEMA = "task40extra.y-orbit-shared-transform-bank.v1"
COEFFICIENT_SCHEMA = "canonical_to_native.basix_coefficient_v1.Tt_apply_v1"


def _digest(array):
    array = np.asarray(array)
    return sha256(array.tobytes(order="C")).hexdigest()


def _signature(value):
    if isinstance(value, np.ndarray):
        return {"dtype": value.dtype.str, "shape": list(value.shape),
                "sha256": _digest(value)}
    if isinstance(value, (tuple, list)):
        return [_signature(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _signature(item) for key, item in sorted(value.items())}
    if isinstance(value, (str, bool, int, float)) or value is None:
        return value
    if isinstance(value, np.generic):
        return _signature(value.item())
    if hasattr(value, "name"):
        return {"type": type(value).__module__ + "." + type(value).__qualname__,
                "name": str(value.name)}
    raise ValueError(f"unsupported actual-basis identity value: {type(value)}")


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def actual_space_identity(space, degree):
    """Fingerprint actual coefficients, layouts, Tt_apply wrapper and ABI.

    Mesh IDs and material data are intentionally absent: distinct full/local
    spaces can share only when their actual coefficient/layout identity agrees.
    Missing coefficient assets or a mismatched degree fail closed.
    """
    element = space.element
    basix = element.basix_element
    if int(basix.degree) != int(degree) or int(basix.dim) != int(element.space_dimension):
        raise ValueError("actual element degree/dimension disagrees with transform request")
    names = ("family", "cell_type", "degree", "dim", "value_shape", "map_type",
             "sobolev_space", "discontinuous", "lagrange_variant", "dpc_variant",
             "dof_ordering", "interpolation_nderivs", "entity_dofs", "entity_closure_dofs",
             "dof_transformations_are_identity", "dof_transformations_are_permutations",
             "wcoeffs", "coefficient_matrix", "dual_matrix", "interpolation_matrix", "x", "M")
    assets = {name: _signature(getattr(basix, name)) for name in names if hasattr(basix, name)}
    if not any(name in assets for name in ("wcoeffs", "coefficient_matrix", "dual_matrix")):
        raise ValueError("actual Basix coefficient fingerprint is unavailable")
    if "hexahedron" not in str(basix.cell_type).lower():
        raise ValueError("shared Y-orbit transforms require the actual hexahedral basis")
    if str(getattr(basix.family, "name", basix.family)).lower() not in ("n1curl", "n1e"):
        raise ValueError("shared Y-orbit transforms require actual N1curl")
    assets["entity_transformations"] = _signature(basix.entity_transformations())
    dof_layout = space.dofmap.dof_layout
    actual_positions = [[list(map(int, dof_layout.entity_dofs(dim, local)))
                         for local in range(len(basix.entity_dofs[dim]))]
                        for dim in range(4)]
    if actual_positions != _signature(basix.entity_dofs):
        raise ValueError("actual space entity channels disagree with Basix entity_dofs")
    apply_method = getattr(type(element), "Tt_apply", None)
    if apply_method is None:
        raise ValueError("actual Tt_apply semantics are unavailable")
    method_code = getattr(apply_method, "__code__", None)
    runtime = {}
    for name in ("numpy", "basix", "dolfinx", "petsc4py.PETSc"):
        module = sys.modules.get(name)
        if module is not None:
            runtime[name] = {"version": str(getattr(module, "__version__", "not_exposed")),
                             "file": str(getattr(module, "__file__", "not_exposed"))}
            if name == "petsc4py.PETSc":
                runtime[name].update(scalar_dtype=np.dtype(module.ScalarType).str,
                                     int_dtype=np.dtype(module.IntType).str)
    packages = {}
    for name in ("numpy", "fenics-basix", "fenics-dolfinx", "fenics-ufl", "petsc4py"):
        try:
            packages[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            packages[name] = "not_exposed"
    return {"coefficient_schema": COEFFICIENT_SCHEMA, "basix": assets,
            "actual_entity_positions": actual_positions,
            "element_signature": str(getattr(element, "signature", "not_exposed")),
            "element_type": type(element).__module__ + "." + type(element).__qualname__,
            "space_type": type(space).__module__ + "." + type(space).__qualname__,
            "index_map_bs": int(space.dofmap.index_map_bs),
            "Tt_apply": {"module": str(getattr(apply_method, "__module__", "not_exposed")),
                         "qualname": str(getattr(apply_method, "__qualname__", "not_exposed")),
                         "bytecode_sha256": (sha256(marshal.dumps(method_code)).hexdigest()
                                             if method_code is not None else None)},
            "runtime": runtime, "packages": packages, "byteorder": sys.byteorder,
            "pointer_bytes": np.dtype(np.intp).itemsize,
            "matrix_dtype": np.dtype(np.complex128).str}


@dataclass(frozen=True)
class TransformKey:
    basis: str
    dimension: int
    shape: tuple
    channels: tuple
    state: tuple
    semantics: tuple
    dtype: str = np.dtype(np.complex128).str


@dataclass
class _Template:
    key: TransformKey
    matrix: np.ndarray
    matrix_sha256: str
    inverse: np.ndarray | None = None
    inverse_sha256: str | None = None


def _immutable(array, shape):
    array = np.asarray(array)
    if array.shape != shape or array.dtype != np.dtype(np.complex128) or not np.isfinite(array).all():
        raise ValueError("complete finite complex128 transform with exact channel shape required")
    # A write-disabled owning ndarray can be made writable again. Immutable
    # bytes backing also rejects setflags(write=True), including through bases.
    result = np.frombuffer(array.tobytes(order="C"), dtype=np.complex128).reshape(shape)
    if result.flags.writeable:
        raise ValueError("shared transform unexpectedly permits mutation")
    return result


class RunLocalTransformBank:
    """One run's owner; full/local/entities/layouts borrow this same object."""

    def __init__(self, *, mapping_limit=1e-12):
        if not np.isfinite(mapping_limit) or mapping_limit <= 0:
            raise ValueError("positive finite original mapping limit required")
        self.mapping_limit = float(mapping_limit)
        self._bases = {}
        self._face_states = {}
        self._templates = {}
        self._content_templates = {}
        self._state_keys = {}
        self._array_keys = {}
        self._sealed = False
        self._closed = False
        self._inventory = BackingOwnerInventory()

    def bind_basis(self, descriptor):
        self._require_open()
        serialized = _json(_signature(descriptor))
        token = sha256(serialized.encode("utf-8")).hexdigest()
        if token in self._bases and self._bases[token] != serialized:
            raise ValueError("actual basis fingerprint collision")
        if token not in self._bases:
            if self._sealed:
                raise ValueError("unseen actual basis in sealed run-local bank")
            self._bases[token] = serialized
            self._face_states[token] = frozenset(
                (tuple(permutation), int(info)) for permutation, info in
                descriptor.get("actual_D4_states", ()))
        return token

    def bind_space(self, space, degree):
        self._require_open()
        if int(degree) != 4:
            raise ValueError("this storage-only opt-in is restricted to the same80 p4 qualification")
        from src.constraints.high_order_floquet_trace import quadrilateral_d4_vertex_permutations

        descriptor = actual_space_identity(space, degree)
        descriptor["actual_D4_states"] = sorted(quadrilateral_d4_vertex_permutations().items())
        return self.bind_basis(descriptor)

    def matrix(self, key, builder):
        self._require_open()
        if key in self._templates:
            return self._checked(self._templates[key], inverse=False)
        self._validate_key(key)
        if self._sealed:
            raise ValueError("unseen actual orientation in sealed run-local bank")
        candidate = np.asarray(builder())
        if (candidate.shape != key.shape or candidate.dtype != np.dtype(np.complex128)
                or not np.isfinite(candidate).all()):
            raise ValueError("complete finite complex128 transform with exact channel shape required")
        matrix_hash = _digest(candidate)
        content_key = (key.basis, key.dimension, key.shape, key.channels,
                       key.semantics, key.dtype, matrix_hash)
        template = self._content_templates.get(content_key)
        if template is not None:
            if candidate.tobytes(order="C") != template.matrix.tobytes(order="C"):
                raise ValueError("complete transform content hash collision")
            self._checked(template, inverse=False)
        else:
            matrix = _immutable(candidate, key.shape)
            template = _Template(key, matrix, matrix_hash)
            self._content_templates[content_key] = template
            self._array_keys[id(matrix)] = key
        self._templates[key] = template
        self._state_keys[key] = key
        return template.matrix

    def _validate_key(self, key):
        if not isinstance(key, TransformKey) or key.basis not in self._bases:
            raise ValueError("unknown actual-space transform key")
        if (key.dimension not in (1, 2, 3) or len(key.shape) != 2
                or key.shape != (len(key.channels), len(key.channels))
                or len(key.channels) != len(set(key.channels)) or not key.channels
                or key.dtype != np.dtype(np.complex128).str or not key.semantics):
            raise ValueError("unknown transform shape, complete channel inventory or semantics")
        if key.dimension == 1 and key.state not in (("edge_reversal", False), ("edge_reversal", True)):
            raise ValueError("unknown actual edge reversal")
        if key.dimension == 2:
            if (len(key.state) != 3 or key.state[0] != "face_D4"
                    or len(key.state[1]) != 4 or sorted(key.state[1]) != [0, 1, 2, 3]
                    or not isinstance(key.state[2], int) or not 0 <= key.state[2] < 8
                    or (key.state[1], key.state[2]) not in self._face_states[key.basis]):
                raise ValueError("unknown actual D4 face state")
        if key.dimension == 3:
            if (len(key.state) != 2 or key.state[0] != "cell_info"
                    or not isinstance(key.state[1], int) or not 0 <= key.state[1] < 2**30):
                raise ValueError("unknown actual hexahedral cell_info")

    def _checked(self, template, *, inverse):
        array = template.inverse if inverse else template.matrix
        if (array is None or array.flags.writeable or array.shape != template.key.shape
                or array.dtype.str != template.key.dtype or not array.flags.c_contiguous
                or not isinstance(_backing(array)[0], bytes)):
            raise ValueError("borrowed shared transform backing is mutable or missing")
        return array

    def key_for(self, matrix):
        self._require_open()
        key = self._array_keys.get(id(matrix))
        if key is None or self._templates[key].matrix is not matrix:
            raise ValueError("matrix is not an exact borrowed run-local template")
        self._checked(self._templates[key], inverse=False)
        return key

    def validate_borrow(self, key, matrix):
        self._require_open()
        template = self._templates.get(key)
        if template is None or template.matrix is not matrix:
            raise ValueError("actual state key does not reference its exact borrowed template")
        self._checked(template, inverse=False)
        return self._state_keys[key]

    def template_id_for(self, matrix):
        template = self._templates[self.key_for(matrix)]
        for index, current in enumerate(self._content_templates.values(), 1):
            if current is template:
                return f"template-{index:04d}"
        raise ValueError("borrowed matrix has no run-local content template")

    def inverse(self, matrix):
        template = self._templates[self.key_for(matrix)]
        if template.inverse is None:
            inverse = np.linalg.inv(template.matrix)
            size = template.matrix.shape[0]
            defect = np.linalg.norm(inverse @ template.matrix - np.eye(size)) / np.sqrt(size)
            if not np.isfinite(defect) or defect > self.mapping_limit:
                raise ValueError("original entity moment inverse failed")
            template.inverse = _immutable(inverse, template.key.shape)
            template.inverse_sha256 = _digest(template.inverse)
        return self._checked(template, inverse=True)

    def seal(self):
        """Reject unseen bases/states after all actual full/local collections."""
        self._require_open()
        self._sealed = True

    def _require_open(self):
        if self._closed:
            raise ValueError("run-local transform bank is closed")

    def close(self):
        """Whole-run exit only, after callers discard all entity/layout borrowers.

        This releases this owner's references; it makes no RSS/allocator claim.
        Diagnostic receipt remains available to record the caller's cleanup.
        """
        self._require_open()
        for cache in (self._bases, self._face_states, self._templates,
                      self._content_templates, self._state_keys, self._array_keys):
            cache.clear()
        self._closed = True

    def named_arrays(self):
        result = {}
        for index, template in enumerate(self._content_templates.values(), 1):
            result[f"bank.template.{index:04d}.matrix"] = self._checked(template, inverse=False)
            if template.inverse is not None:
                result[f"bank.template.{index:04d}.inverse"] = self._checked(template, inverse=True)
        return result

    def receipt(self, named_arrays=None, *, stage):
        arrays = self.named_arrays()
        for name, array in (named_arrays or {}).items():
            if name in arrays:
                raise ValueError("duplicate named numerical borrower")
            arrays[name] = array
        result = self._inventory.receipt(arrays, stage=stage)
        templates = []
        for index, template in enumerate(self._content_templates.values(), 1):
            if _digest(template.matrix) != template.matrix_sha256:
                raise ValueError("shared matrix content hash changed")
            if template.inverse is not None and _digest(template.inverse) != template.inverse_sha256:
                raise ValueError("shared inverse content hash changed")
            templates.append({"template_id": f"template-{index:04d}",
                              "keys": [_signature(key.__dict__) for key, value in self._templates.items()
                                       if value is template],
                              "matrix_sha256": template.matrix_sha256,
                              "inverse_sha256": template.inverse_sha256})
        result.update(schema=SCHEMA, basis_count=len(self._bases),
                      basis_fingerprints=[{"basis_id": token, "descriptor": json.loads(serialized)}
                                          for token, serialized in self._bases.items()],
                      actual_state_count=len(self._templates),
                      matrix_template_count=len(self._content_templates),
                      lazy_inverse_count=sum(t.inverse is not None for t in self._content_templates.values()),
                      sealed=self._sealed, closed=self._closed, templates=templates)
        return result


# Compatibility spelling for the opt-in seam; neither name creates global state.
YOrbitTransformBank = RunLocalTransformBank


def _backing(array):
    """Return ultimate owner, last ndarray anchor, and the complete base chain."""
    current = array
    chain = []
    seen = set()
    anchor = array
    while True:
        if id(current) in seen:
            raise ValueError("cyclic numerical backing chain")
        seen.add(id(current))
        chain.append(type(current).__module__ + "." + type(current).__qualname__)
        if isinstance(current, np.ndarray):
            anchor = current
            if current.base is None:
                return current, anchor, chain
            current = current.base
        elif isinstance(current, memoryview):
            current = current.obj
        else:
            # Buffer protocol is required for an exact non-ndarray byte span.
            memoryview(current)
            return current, anchor, chain


class BackingOwnerInventory:
    """Stable run-local IDs without retaining temporary numerical owners.

    Addresses/object IDs are used only for this process's alias checks and are
    never written into receipts. Weak anchors prevent inventory-induced leaks.
    """

    def __init__(self):
        self._owners = {}
        self._next = 1

    def _owner_id(self, owner, anchor):
        identity = id(owner)
        previous = self._owners.get(identity)
        live = [] if previous is None else [ref for ref in previous[1] if ref() is not None]
        if previous is not None and any(_backing(ref())[0] is owner for ref in live):
            token = previous[0]
        else:
            token = f"owner-{self._next:06d}"
            self._next += 1
            live = []
        if not any(ref() is anchor for ref in live):
            live.append(weakref.ref(anchor))
        self._owners[identity] = (token, live)
        return token

    def receipt(self, named_arrays, *, stage):
        owners = {}
        owner_starts = {}
        view_hashes = {}
        views = []
        for name, array in sorted(named_arrays.items()):
            if not isinstance(name, str) or not isinstance(array, np.ndarray):
                raise ValueError("exact names and ndarray borrowers required")
            if array.dtype.hasobject:
                raise ValueError("object-array storage is not a numerical payload")
            owner, anchor, chain = _backing(array)
            token = self._owner_id(owner, anchor)
            if token not in owners:
                if isinstance(owner, np.ndarray):
                    if not (owner.flags.c_contiguous or owner.flags.f_contiguous):
                        raise ValueError("non-contiguous ndarray owner has no qualified allocation span")
                    allocation = int(owner.nbytes)
                    start = int(owner.__array_interface__["data"][0])
                    owner_dtype, owner_shape = owner.dtype.str, list(owner.shape)
                    owner_strides = list(owner.strides)
                    owner_hash = sha256(owner.tobytes(order="A")).hexdigest()
                else:
                    buffer = memoryview(owner)
                    if not buffer.c_contiguous:
                        raise ValueError("external backing has no qualified C-contiguous allocation span")
                    allocation = int(buffer.nbytes)
                    start = int(np.frombuffer(buffer, dtype=np.uint8).__array_interface__["data"][0])
                    owner_dtype, owner_shape, owner_strides = None, None, None
                    owner_hash = sha256(buffer).hexdigest()
                owner_starts[token] = start
                owners[token] = {"owner_id": token, "owner_type": chain[-1],
                                 "allocation_nbytes": allocation, "dtype": owner_dtype,
                                 "shape": owner_shape, "strides": owner_strides,
                                 "sha256": owner_hash, "borrowers": []}
            else:
                start = owner_starts[token]
                allocation = owners[token]["allocation_nbytes"]
            offset = int(array.__array_interface__["data"][0]) - start
            low = offset + sum(min(0, (size-1)*stride) for size, stride in zip(array.shape, array.strides))
            high = offset + sum(max(0, (size-1)*stride) for size, stride in zip(array.shape, array.strides)) + array.itemsize
            if array.size == 0:
                low = high = offset
            if low < 0 or high > allocation:
                raise ValueError("borrowed view exceeds its reported backing allocation")
            owners[token]["borrowers"].append(name)
            view_identity = (token, array.dtype.str, array.shape, array.strides, offset)
            if view_identity not in view_hashes:
                view_hashes[view_identity] = _digest(array)
            views.append({"name": name, "owner_id": token, "dtype": array.dtype.str,
                          "shape": list(array.shape), "strides": list(array.strides),
                          "view_nbytes": int(array.nbytes), "owndata": bool(array.flags.owndata),
                          "writeable": bool(array.flags.writeable), "base_chain": chain,
                          "byte_offset": offset, "backing_span": [low, high],
                          "sha256": view_hashes[view_identity]})
        # Discard dead weak entries; metadata must not grow with discarded panels.
        self._owners = {key: value for key, value in self._owners.items()
                        if any(ref() is not None for ref in value[1])}
        return {"stage": str(stage), "scope": "named numerical backing allocations; not RSS",
                "sum_view_nbytes_with_aliases": sum(view["view_nbytes"] for view in views),
                "unique_backing_owner_nbytes": sum(owner["allocation_nbytes"] for owner in owners.values()),
                "owner_count": len(owners), "owners": list(owners.values()), "views": views}
