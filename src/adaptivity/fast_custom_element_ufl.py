"""Opt-in, bytewise UFL identity for large custom Basix elements.

Basix 0.10 computes the UFL identity of a custom element by formatting every
floating-point coefficient as Python text.  That is deterministic, but it is
needlessly expensive for the fixed-p5-trace/p6-interior element used by
Task035b.  This module provides an explicitly opt-in wrapper whose identity is
instead a SHA256 digest of a canonical binary stream.

The ordinary Basix/DOLFINx path is deliberately untouched.  Callers must
explicitly invoke :func:`wrap_custom_element_fast`, and the wrapper refuses to
run if the audited private Basix UFL API or supported Basix version changes.
No pickle or executable deserialisation format is used.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from functools import lru_cache
import hashlib
import inspect
import json
from pathlib import Path
import struct
import sys
import time
from types import MappingProxyType
from typing import Any

import basix
import basix.ufl
import numpy as np


_SIGNATURE_SCHEMA = "myfenics.custom-basix-byte-signature.v1"
_WRAPPER_AUDIT_SCHEMA = "task035b.fast-custom-basix-ufl-wrapper.v1"
_SUPPORTED_BASIX_VERSIONS = ("0.10.0",)
_SUPPORTED_BASIX_UFL_SOURCE_SHA256 = {
    "0.10.0": (
        "63b96e54f21d5bff2601de0310beea4585cd4f8ca3dee855f10c7153ccaaf5f1"
    ),
}
_QUALIFIED_BASIX_UFL_MODULE_SHA256 = {
    "0.10.0": (
        "63b96e54f21d5bff2601de0310beea4585cd4f8ca3dee855f10c7153ccaaf5f1",
    ),
}

_PrivateBasixElement = getattr(basix.ufl, "_BasixElement", None)
_PrivateElementBase = getattr(basix.ufl, "_ElementBase", None)
_private_pullback = getattr(basix.ufl, "_ufl_pullback_from_enum", None)

if not isinstance(_PrivateBasixElement, type):
    raise RuntimeError("Basix UFL private _BasixElement is unavailable")
if not isinstance(_PrivateElementBase, type):
    raise RuntimeError("Basix UFL private _ElementBase is unavailable")
if not callable(_private_pullback):
    raise RuntimeError("Basix UFL private pullback adapter is unavailable")


@dataclass(frozen=True)
class BasixUFLPrivateAPIAudit:
    """Fail-closed compatibility record for the private constructor path."""

    schema_version: str
    status: str
    basix_version: str
    supported_basix_versions: tuple[str, ...]
    basix_ufl_module_path: str
    basix_ufl_module_sha256: str
    qualified_basix_ufl_module_sha256: tuple[str, ...]
    private_element_base_init_parameters: tuple[str, ...]
    private_basix_element_init_parameters: tuple[str, ...]
    private_pullback_parameters: tuple[str, ...]
    required_forwarded_attributes: tuple[str, ...]


def _parameter_names(callable_object: Any) -> tuple[str, ...]:
    return tuple(inspect.signature(callable_object).parameters)


@lru_cache(maxsize=1)
def basix_ufl_private_api_audit() -> BasixUFLPrivateAPIAudit:
    """Validate the exact private API assumptions used by the fast wrapper."""

    version = str(getattr(basix, "__version__", ""))
    if version not in _SUPPORTED_BASIX_VERSIONS:
        raise RuntimeError(
            "fast custom-element wrapper is not qualified for Basix "
            f"{version!r}; supported={_SUPPORTED_BASIX_VERSIONS}"
        )
    if getattr(basix.ufl, "_BasixElement", None) is not _PrivateBasixElement:
        raise RuntimeError("Basix UFL _BasixElement identity changed")
    if getattr(basix.ufl, "_ElementBase", None) is not _PrivateElementBase:
        raise RuntimeError("Basix UFL _ElementBase identity changed")
    if (
        getattr(basix.ufl, "_ufl_pullback_from_enum", None)
        is not _private_pullback
    ):
        raise RuntimeError("Basix UFL pullback adapter identity changed")
    if not issubclass(_PrivateBasixElement, _PrivateElementBase):
        raise RuntimeError("Basix UFL private wrapper inheritance changed")

    base_parameters = _parameter_names(_PrivateElementBase.__init__)
    wrapper_parameters = _parameter_names(_PrivateBasixElement.__init__)
    pullback_parameters = _parameter_names(_private_pullback)
    if base_parameters != (
        "self",
        "repr",
        "cellname",
        "reference_value_shape",
        "degree",
        "pullback",
    ):
        raise RuntimeError(
            "Basix UFL _ElementBase constructor contract changed: "
            f"{base_parameters}"
        )
    if wrapper_parameters != ("self", "element"):
        raise RuntimeError(
            "Basix UFL _BasixElement constructor contract changed: "
            f"{wrapper_parameters}"
        )
    if pullback_parameters != ("m",):
        raise RuntimeError(
            "Basix UFL pullback adapter contract changed: "
            f"{pullback_parameters}"
        )

    required_attributes = (
        "basix_element",
        "basix_hash",
        "tabulate",
        "entity_dofs",
        "entity_closure_dofs",
        "num_entity_dofs",
        "num_entity_closure_dofs",
        "map_type",
        "pullback",
        "get_component_element",
    )
    missing = tuple(
        name
        for name in required_attributes
        if not hasattr(_PrivateBasixElement, name)
    )
    if missing:
        raise RuntimeError(
            f"Basix UFL private wrapper lost required attributes: {missing}"
        )

    module_path = Path(str(getattr(basix.ufl, "__file__", ""))).resolve()
    if not module_path.is_file():
        raise RuntimeError("Basix UFL source path is not an auditable file")
    module_sha256 = hashlib.sha256(module_path.read_bytes()).hexdigest()
    expected_module_sha256 = _SUPPORTED_BASIX_UFL_SOURCE_SHA256.get(
        version
    )
    if module_sha256 != expected_module_sha256:
        raise RuntimeError(
            "fast custom-element wrapper has not qualified this Basix UFL "
            f"source: version={version}, sha256={module_sha256}, "
            f"expected={expected_module_sha256}"
        )
    qualified_module_hashes = _QUALIFIED_BASIX_UFL_MODULE_SHA256[version]
    if module_sha256 not in qualified_module_hashes:
        raise RuntimeError(
            "Basix UFL source changed without requalification: "
            f"observed={module_sha256}, qualified={qualified_module_hashes}"
        )
    return BasixUFLPrivateAPIAudit(
        schema_version="task035b.basix-ufl-private-api-audit.v1",
        status="qualified_fail_closed_private_api",
        basix_version=version,
        supported_basix_versions=_SUPPORTED_BASIX_VERSIONS,
        basix_ufl_module_path=str(module_path),
        basix_ufl_module_sha256=module_sha256,
        qualified_basix_ufl_module_sha256=qualified_module_hashes,
        private_element_base_init_parameters=base_parameters,
        private_basix_element_init_parameters=wrapper_parameters,
        private_pullback_parameters=pullback_parameters,
        required_forwarded_attributes=required_attributes,
    )


def _update_blob(
    digest: Any,
    label: str,
    payload: bytes | bytearray | memoryview,
) -> None:
    """Append one unambiguous, length-framed item to a digest."""

    label_bytes = label.encode("utf-8")
    payload_view = memoryview(payload).cast("B")
    digest.update(struct.pack("<Q", len(label_bytes)))
    digest.update(label_bytes)
    digest.update(struct.pack("<Q", len(payload_view)))
    digest.update(payload_view)


def _canonical_array(array: Any) -> tuple[str, tuple[int, ...], np.ndarray]:
    """Return a C-contiguous, little-endian numeric array."""

    values = np.asarray(array)
    if values.dtype.hasobject or values.dtype.fields is not None:
        raise TypeError("custom-element signatures reject object/record arrays")
    dtype = values.dtype
    if dtype.itemsize > 1 and dtype.byteorder != "|":
        dtype = dtype.newbyteorder("<")
    canonical = np.ascontiguousarray(values, dtype=dtype)
    return dtype.str, tuple(int(i) for i in canonical.shape), canonical


def _update_array(digest: Any, label: str, array: Any) -> None:
    dtype, shape, canonical = _canonical_array(array)
    _update_blob(digest, f"{label}.dtype", dtype.encode("ascii"))
    shape_bytes = struct.pack("<Q", len(shape)) + b"".join(
        struct.pack("<q", value) for value in shape
    )
    _update_blob(digest, f"{label}.shape", shape_bytes)
    payload = (
        b""
        if canonical.nbytes == 0
        else memoryview(canonical).cast("B")
    )
    _update_blob(digest, f"{label}.data", payload)


def _json_value(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {
            str(key): _json_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if hasattr(value, "name"):
        return str(value.name)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise TypeError(
        "custom-element metadata contains an unsupported value "
        f"{type(value).__qualname__}"
    )


def _element_metadata(element: Any) -> dict[str, Any]:
    """Collect non-array custom-element state that affects UFL identity."""

    return {
        "family": _json_value(element.family),
        "cell_type": _json_value(element.cell_type),
        "degree": int(element.degree),
        "value_shape": _json_value(element.value_shape),
        "map_type": _json_value(element.map_type),
        "sobolev_space": _json_value(element.sobolev_space),
        "discontinuous": bool(element.discontinuous),
        "embedded_subdegree": int(element.embedded_subdegree),
        "embedded_superdegree": int(element.embedded_superdegree),
        "interpolation_nderivs": int(element.interpolation_nderivs),
        "polyset_type": _json_value(element.polyset_type),
        "dtype": np.dtype(element.dtype).str,
        "dimension": int(element.dim),
        "dof_ordering": _json_value(element.dof_ordering),
        "lagrange_variant": _json_value(element.lagrange_variant),
        "dpc_variant": _json_value(element.dpc_variant),
        "has_tensor_product_factorisation": bool(
            element.has_tensor_product_factorisation
        ),
        "num_entity_dofs": _json_value(element.num_entity_dofs),
        "entity_dofs": _json_value(element.entity_dofs),
        "num_entity_closure_dofs": _json_value(
            element.num_entity_closure_dofs
        ),
        "entity_closure_dofs": _json_value(element.entity_closure_dofs),
    }


def _update_nested_arrays(
    digest: Any,
    label: str,
    nested_arrays: Any,
) -> None:
    dimensions = list(nested_arrays)
    _update_blob(
        digest,
        f"{label}.dimension_count",
        struct.pack("<Q", len(dimensions)),
    )
    for dimension, entities in enumerate(dimensions):
        entity_arrays = list(entities)
        _update_blob(
            digest,
            f"{label}.{dimension}.entity_count",
            struct.pack("<Q", len(entity_arrays)),
        )
        for entity, array in enumerate(entity_arrays):
            _update_array(digest, f"{label}.{dimension}.{entity}", array)


def _custom_element_sha256_unchecked(element: Any) -> str:
    """Hash a Basix-compatible custom-element data view."""

    if element.family != basix.ElementFamily.custom:
        raise ValueError("bytewise wrapper only accepts custom Basix elements")
    digest = hashlib.sha256()
    _update_blob(digest, "schema", _SIGNATURE_SCHEMA.encode("ascii"))
    metadata = json.dumps(
        _element_metadata(element),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")
    _update_blob(digest, "metadata", metadata)
    _update_array(digest, "wcoeffs", element.wcoeffs)
    _update_nested_arrays(digest, "x", element.x)
    _update_nested_arrays(digest, "M", element.M)

    transformations = element.entity_transformations()
    names = sorted(str(name) for name in transformations)
    _update_blob(
        digest,
        "entity_transformations.count",
        struct.pack("<Q", len(names)),
    )
    for index, name in enumerate(names):
        _update_blob(
            digest,
            f"entity_transformations.{index}.name",
            name.encode("utf-8"),
        )
        _update_array(
            digest,
            f"entity_transformations.{index}.matrix",
            transformations[name],
        )
    return digest.hexdigest()


def custom_element_sha256(
    element: basix.finite_element.FiniteElement,
) -> str:
    """Return the canonical SHA256 identity of one custom Basix element."""

    if not isinstance(element, basix.finite_element.FiniteElement):
        raise TypeError("element must be a Basix FiniteElement")
    return _custom_element_sha256_unchecked(element)


class FastCustomBasixElement(_PrivateBasixElement):
    """UFL wrapper with a namespaced binary identity.

    Fast wrappers compare equal only to other fast wrappers with the same
    canonical signature.  They intentionally do not compare equal to Basix's
    text-signature wrapper: making those objects equal while assigning
    different Python hashes would violate the Python/UFL hashing contract.
    Their underlying ``basix_element`` and ``basix_hash()`` remain identical.
    """

    def __init__(
        self,
        element: basix.finite_element.FiniteElement,
        signature: str,
        audit: MappingProxyType,
    ) -> None:
        representation = (
            "custom Basix element "
            f"({_SIGNATURE_SCHEMA}:sha256:{signature})"
        )
        _PrivateElementBase.__init__(
            self,
            representation,
            element.cell_type.name,
            tuple(element.value_shape),
            element.degree,
            _private_pullback(element.map_type),
        )
        self._element = element
        self._is_custom = True
        self._fast_custom_signature = signature
        self._fast_wrapper_audit = audit

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, FastCustomBasixElement)
            and self._fast_custom_signature
            == other._fast_custom_signature
            and self._element == other._element
        )

    def __hash__(self) -> int:
        return _PrivateElementBase.__hash__(self)

    @property
    def fast_custom_signature(self) -> str:
        """Canonical bytewise SHA256 identity."""

        return self._fast_custom_signature

    @property
    def fast_wrapper_audit(self) -> MappingProxyType:
        """Immutable construction and compatibility audit."""

        return self._fast_wrapper_audit


def wrap_custom_element_fast(
    element: basix.finite_element.FiniteElement,
) -> FastCustomBasixElement:
    """Wrap a custom element without Basix's per-scalar text formatting."""

    started = time.perf_counter()
    private_audit = basix_ufl_private_api_audit()
    if not isinstance(element, basix.finite_element.FiniteElement):
        raise TypeError("element must be a Basix FiniteElement")
    if element.family != basix.ElementFamily.custom:
        raise ValueError("fast wrapper only accepts custom Basix elements")
    signature_started = time.perf_counter()
    signature = custom_element_sha256(element)
    signature_seconds = time.perf_counter() - signature_started
    audit = MappingProxyType(
        {
            "schema_version": _WRAPPER_AUDIT_SCHEMA,
            "status": "opt_in_fast_custom_wrapper_built",
            "ordinary_default_changed": False,
            "signature_schema": _SIGNATURE_SCHEMA,
            "signature_algorithm": (
                "sha256_length_framed_metadata_and_little_endian_array_bytes"
            ),
            "serialization": "canonical_binary_no_pickle",
            "signature_sha256": signature,
            "signature_seconds": float(signature_seconds),
            "private_api_audit": asdict(private_audit),
            "python_version": sys.version.split()[0],
        }
    )
    wrapper = FastCustomBasixElement(element, signature, audit)
    # The immutable mapping deliberately excludes this final assignment time;
    # callers can time the whole function when comparing construction paths.
    if time.perf_counter() < started:
        raise RuntimeError("monotonic construction timer moved backwards")
    return wrapper


__all__ = [
    "BasixUFLPrivateAPIAudit",
    "FastCustomBasixElement",
    "basix_ufl_private_api_audit",
    "custom_element_sha256",
    "wrap_custom_element_fast",
]
