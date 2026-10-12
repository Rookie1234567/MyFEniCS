"""Atomic, identity-bound storage for completed port functionals.

The store contains completed modal surface functionals only.  It does not
store or restore a mesh, a finite-element context, a matrix, or a factor.
Each committed shard is one ordered mode so a durable prefix may end between
the s and p polarization entries.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import platform
import re
import shutil
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from itertools import pairwise
from pathlib import Path
from types import TracebackType
from typing import Any, Self
from uuid import uuid4
from zipfile import ZIP_STORED, BadZipFile, ZipFile

import numpy as np

STORE_SCHEMA = "task39extra.fullspace-dtn-functional-store.v1"
SHARD_SCHEMA = "task39extra.fullspace-dtn-functional-shard.v1"
SERIALIZATION_SCRATCH_BOUND_BYTES = 16 * 1024**2
_HASH_BLOCK_BYTES = 1024**2
_MAX_UFCX_FORM_SIGNATURE_BYTES = 4096
_MAX_MANIFEST_BYTES = 1024**2
N0_PARENT_COMPATIBILITY_SCHEMA = "task39extra.n0-parent-store-compatibility.v1"
N0_PARENT_MODE_COUNT = 32060
N0_PARENT_MODE_SHA256 = (
    "7f023c73d7b63379955642dd062e47ba7004f3cdf0accf42684286c4af71dbfb"
)
N0_PARENT_COMPATIBLE_IMPLEMENTATION_FILES = frozenset(
    {
        "src/io/input_validation.py",
        "src/io/native_capacity_profile.py",
        "src/runners/physical_intermediate.py",
        "src/runners/physical_retained_condensed_v20.py",
        "src/solvers/fullspace_dtn_action.py",
        "src/solvers/fullspace_dtn_functional_store.py",
        "src/solvers/fullspace_same_mesh_hcurl_pmg_physical.py",
    }
)
_SHARD_NAME = re.compile(r"^functional_(\d{8})$")
_TEMP_NAME = re.compile(r"^\.tmp_functional_\d{8}_[0-9a-f]{32}$")
_ARRAY_KEYS = (
    "coupling_rows",
    "coupling_values",
    "projection_rows",
    "projection_values",
    "normalization_h",
)
_UFCX_INTEGRAL_TYPE_BOUNDARIES = 6
_FFCX_FORM_MODULE_PREFIX = "libffcx_forms_"
_FFCX_FORM_MODULE_NAME = re.compile(
    rf"{re.escape(_FFCX_FORM_MODULE_PREFIX)}[0-9a-f]+$"
)
_REQUIRED_IDENTITY_KEYS = frozenset(
    {
        "schema",
        "source_sha256",
        "resolved_config_sha256",
        "implementation_file_sha256",
        "input_sha256",
        "physical_model_sha256",
        "backend",
        "degree",
        "mesh",
        "dof_mpc",
        "modes",
        "quadrature",
        "abi",
    }
)
P3_NUMERICAL_IDENTITY_SCHEMA = "task39extra.port-functional-numerical-identity.v1"
P6_NUMERICAL_IDENTITY_SCHEMA = (
    "task39extra.port-functional-numerical-identity.p6-paired.v2"
)
P6_SURFACE_PROVIDER_SCHEMA = "task39extra.p6-paired-surface-provider.v1"
P6_CONTEXT_PROVIDER_SCHEMA = (
    "task39extra.p6-paired-surface-context-numerical-provider.v1"
)
_REQUIRED_MODE_IDENTITY_KEYS = frozenset(
    {
        "schema",
        "mode_index",
        "side",
        "m",
        "n",
        "polarization",
        "alpha",
        "gamma",
        "beta",
        "k_vector",
        "e_vector",
        "h_vector",
        "refractive_index",
        "vertical_sign",
        "electric_tangential_norm_sq",
        "power_per_unit_amplitude",
        "propagating",
        "rayleigh_warning",
        "classification",
        "rayleigh_tolerance",
        "projection_denominator",
        "traction_vector",
    }
)


def _json_safe(value: Any) -> Any:
    if isinstance(value, np.generic):
        return _json_safe(value.item())
    if isinstance(value, complex):
        if not np.isfinite(value.real) or not np.isfinite(value.imag):
            raise ValueError(
                "functional-store identity contains non-finite complex data"
            )
        return {
            "real_hex": float(value.real).hex(),
            "imag_hex": float(value.imag).hex(),
        }
    if isinstance(value, float):
        if not np.isfinite(value):
            raise ValueError("functional-store identity contains non-finite float data")
        return {"float64_hex": value.hex()}
    if isinstance(value, bool) or value is None or isinstance(value, (int, str)):
        return value
    if isinstance(value, Mapping):
        return {
            str(key): _json_safe(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (tuple, list)):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.ndarray):
        return _json_safe(value.tolist())
    raise TypeError(
        f"unsupported functional-store identity value {type(value).__name__}"
    )


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        _json_safe(value),
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")


def _array_hash_update(digest: Any, name: str, array: Any) -> None:
    value = np.asarray(array)
    if not value.flags.c_contiguous:
        raise ValueError(f"identity array {name} is not C-contiguous")
    digest.update(name.encode("utf-8"))
    digest.update(b"\0")
    digest.update(value.dtype.str.encode("ascii"))
    digest.update(b"\0")
    digest.update(_canonical_json_bytes([int(item) for item in value.shape]))
    digest.update(b"\0")
    digest.update(memoryview(value).cast("B"))
    digest.update(b"\0")


def _validate_compiled_form_code_diagnostic(code: Any) -> None:
    """Accept cold-source and FFCx cache-hit code shapes without keying identity on them.

    FFCx returns ``(None, None)`` when a compiled module is loaded from cache.
    The loaded module and its signature/content below are the stable identity;
    generated source availability is diagnostic only.
    """

    if isinstance(code, str) and code:
        return
    if isinstance(code, (list, tuple)):
        if len(code) == 2 and code[0] is None and code[1] is None:
            return
        if code and all(isinstance(part, str) and part for part in code):
            return
    raise ValueError("functional-store compiled Form code diagnostic is malformed")


def _bounded_diagnostic_text(value: Any, limit: int = 512) -> str | None:
    if not isinstance(value, str):
        return None
    return value[:limit]


def _compiled_form_api_diagnostic(form: Any) -> dict[str, Any]:
    """Return a bounded, noncanonical description of the loaded Form API."""

    if form is None:
        return {
            "form_present": False,
            "code_type": "missing",
            "code_component_types": [],
            "module_name": None,
            "module_path": None,
            "signature_cffi_kind": "missing",
        }
    code = getattr(form, "code", None)
    if isinstance(code, (tuple, list)):
        code_type = type(code).__name__
        code_component_types = [type(item).__name__ for item in code[:4]]
        code_component_count = len(code)
    else:
        code_type = type(code).__name__ if hasattr(form, "code") else "missing"
        code_component_types = []
        code_component_count = None

    module = getattr(form, "module", None)
    module_name = _bounded_diagnostic_text(getattr(module, "__name__", None), 128)
    module_path = _bounded_diagnostic_text(getattr(module, "__file__", None))
    ufcx_form = getattr(form, "ufcx_form", None)
    signature = getattr(ufcx_form, "signature", None)
    if isinstance(signature, (str, bytes)):
        signature_kind = f"python:{type(signature).__name__}"
    else:
        ffi = getattr(module, "ffi", None)
        typeof = getattr(ffi, "typeof", None)
        if not callable(typeof):
            signature_kind = "module-ffi-unavailable"
        elif signature is None:
            signature_kind = "null-or-missing"
        else:
            try:
                signature_type = typeof(signature)
                item_type = getattr(signature_type, "item", None)
                signature_kind = ":".join(
                    str(value)
                    for value in (
                        getattr(signature_type, "kind", "unknown"),
                        getattr(signature_type, "cname", "unknown"),
                        getattr(item_type, "kind", "none"),
                        getattr(item_type, "cname", "none"),
                    )
                )
            except (TypeError, ValueError):
                signature_kind = "invalid-cffi-value"
    return {
        "form_present": True,
        "code_type": code_type,
        "code_component_types": code_component_types,
        "code_component_count": code_component_count,
        "module_name": module_name,
        "module_path": module_path,
        "signature_cffi_kind": signature_kind,
    }


def _normalize_ufcx_form_signature(form: Any, ufcx_form: Any) -> str:
    raw_signature = getattr(ufcx_form, "signature", None)
    if raw_signature is None:
        raise ValueError("functional-store UFCx Form signature is missing")
    if isinstance(raw_signature, str):
        try:
            signature_bytes = raw_signature.encode("utf-8", errors="strict")
        except UnicodeEncodeError as exc:
            raise ValueError(
                "functional-store UFCx Form signature is malformed"
            ) from exc
    elif isinstance(raw_signature, bytes):
        signature_bytes = raw_signature
    else:
        module = getattr(form, "module", None)
        ffi = getattr(module, "ffi", None)
        typeof = getattr(ffi, "typeof", None)
        string = getattr(ffi, "string", None)
        if not callable(typeof) or not callable(string) or not hasattr(ffi, "NULL"):
            raise ValueError(
                "functional-store UFCx Form signature requires the loaded module FFI"
            )
        try:
            if raw_signature == ffi.NULL:
                raise ValueError("functional-store UFCx Form signature is NULL")
        except TypeError:
            # Non-pointer CFFI values are rejected by the exact type check below.
            pass
        try:
            signature_type = typeof(raw_signature)
        except (TypeError, ValueError) as exc:
            raise TypeError(
                "functional-store UFCx Form signature is not CFFI char*"
            ) from exc
        item_type = getattr(signature_type, "item", None)
        if (
            getattr(signature_type, "kind", None) != "pointer"
            or getattr(item_type, "kind", None) != "primitive"
            or getattr(item_type, "cname", None) != "char"
        ):
            raise TypeError(
                "functional-store UFCx Form signature is not CFFI char*"
            )
        try:
            signature_bytes = string(
                raw_signature, _MAX_UFCX_FORM_SIGNATURE_BYTES + 1
            )
        except ValueError:
            raise
        except (TypeError, OverflowError) as exc:
            raise ValueError(
                "functional-store UFCx Form signature cannot be read through loaded FFI"
            ) from exc

    if not signature_bytes:
        raise ValueError("functional-store UFCx Form signature is empty")
    if len(signature_bytes) > _MAX_UFCX_FORM_SIGNATURE_BYTES:
        raise ValueError("functional-store UFCx Form signature exceeds size limit")
    if b"\0" in signature_bytes:
        raise ValueError("functional-store UFCx Form signature contains NUL")
    try:
        signature = signature_bytes.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError(
            "functional-store UFCx Form signature is not valid UTF-8"
        ) from exc
    if not signature:
        raise ValueError("functional-store UFCx Form signature is empty")
    return signature


def _loaded_ffcx_module_identity(
    form: Any, module_identity_cache: dict[tuple[Any, ...], dict[str, Any]]
) -> dict[str, Any]:
    """Bind the already-loaded FFCx module by signature and compiled bytes.

    This does not invoke JIT. The FFCx module name is derived from the UFL
    form and compiler-option signature, while the artifact digest binds the
    actual loaded module content on both cold and cache-hit paths. Absolute
    path and stat data are used only to verify one stable read and to reuse a
    digest within this identity construction; neither enters the identity.
    """

    module = getattr(form, "module", None)
    module_name = getattr(module, "__name__", None)
    module_file = getattr(module, "__file__", None)
    if (
        not isinstance(module_name, str)
        or _FFCX_FORM_MODULE_NAME.fullmatch(module_name) is None
        or not isinstance(module_file, str)
        or not module_file
    ):
        raise ValueError("functional-store loaded FFCx form module identity is missing")
    raw_path = Path(module_file)
    if not raw_path.is_absolute():
        raise ValueError("functional-store loaded FFCx module path is not absolute")
    try:
        path = raw_path.resolve(strict=True)
        before = path.stat()
    except (OSError, RuntimeError) as exc:
        raise ValueError("functional-store loaded FFCx module file is unavailable") from exc
    if not path.is_file() or before.st_size <= 0:
        raise ValueError("functional-store loaded FFCx module file is not a nonempty file")
    cache_key = (
        module_name,
        str(path),
        int(before.st_dev),
        int(before.st_ino),
        int(before.st_size),
        int(before.st_mtime_ns),
        int(before.st_ctime_ns),
    )
    cached = module_identity_cache.get(cache_key)
    if cached is not None:
        return dict(cached)
    digest, size, _elapsed = _sha256_file(path)
    try:
        after = path.stat()
    except OSError as exc:
        raise ValueError("functional-store loaded FFCx module changed while hashing") from exc
    if (
        size != before.st_size
        or after.st_dev != before.st_dev
        or after.st_ino != before.st_ino
        or after.st_size != before.st_size
        or after.st_mtime_ns != before.st_mtime_ns
        or after.st_ctime_ns != before.st_ctime_ns
    ):
        raise ValueError("functional-store loaded FFCx module changed while hashing")
    identity = {
        "compiled_module_signature": module_name,
        "compiled_module_file_sha256": digest,
    }
    module_identity_cache[cache_key] = identity
    return dict(identity)


def _compiled_surface_form_identity_impl(
    assembler: Any,
    *,
    side: str,
    component: int,
    module_identity_cache: dict[tuple[Any, ...], dict[str, Any]],
) -> dict[str, Any]:
    """Bind one compiled surface component through Dolfinx's public Form API.

    The qualified ``dolfinx.fem.Form`` exposes ``module``, ``code``,
    ``ufcx_form``, ``integral_types``, ``rank`` and ``dtype``; it does not
    expose UFL's ``integrals()`` method. The loaded FFCx module signature and
    artifact content bind the actual compiled kernel. ``code`` is validated
    only as cold-compile/cache-hit diagnostic metadata and is not hashed into
    the stable identity.
    """

    expected_side = str(side)
    expected_component = int(component)
    if expected_side not in {"bottom", "top"} or expected_component not in {0, 1}:
        raise ValueError("functional-store surface component key is invalid")
    if (
        int(getattr(assembler, "component", -1)) != expected_component
        or str(getattr(assembler, "side", expected_side)) != expected_side
    ):
        raise ValueError("functional-store assembler component identity differs")

    form = getattr(assembler, "form", None)
    if form is None:
        raise ValueError("functional-store compiled surface Form is missing")
    code = getattr(form, "code", None)
    _validate_compiled_form_code_diagnostic(code)
    module_identity = _loaded_ffcx_module_identity(form, module_identity_cache)

    integral_types = getattr(form, "integral_types", None)
    if integral_types is None:
        raise ValueError("functional-store compiled Form integral types are missing")
    try:
        integral_type_names = sorted(
            name
            for item in integral_types
            if isinstance((name := getattr(item, "name", None)), str) and name
        )
    except TypeError as exc:
        raise ValueError(
            "functional-store compiled Form integral types are malformed"
        ) from exc
    if not integral_type_names or "exterior_facet" not in integral_type_names:
        raise ValueError(
            "functional-store compiled Form lacks exterior-facet integral identity"
        )

    ufcx_form = getattr(form, "ufcx_form", None)
    if ufcx_form is None:
        raise ValueError("functional-store compiled Form UFCx metadata is missing")
    ufcx_signature = _normalize_ufcx_form_signature(form, ufcx_form)
    offsets_source = getattr(ufcx_form, "form_integral_offsets", None)
    integral_ids_source = getattr(ufcx_form, "form_integral_ids", None)
    if offsets_source is None or integral_ids_source is None:
        raise ValueError("functional-store UFCx integral identity is missing")
    try:
        offsets = [
            int(offsets_source[index])
            for index in range(_UFCX_INTEGRAL_TYPE_BOUNDARIES)
        ]
    except (IndexError, TypeError, ValueError, OverflowError) as exc:
        raise ValueError(
            "functional-store UFCx integral offsets are malformed"
        ) from exc
    if (
        offsets[0] != 0
        or any(right < left for left, right in pairwise(offsets))
        or offsets[2] <= offsets[1]
    ):
        raise ValueError(
            "functional-store UFCx offsets do not describe an exterior-facet form"
        )
    try:
        integral_ids = [int(integral_ids_source[index]) for index in range(offsets[-1])]
    except (IndexError, TypeError, ValueError, OverflowError) as exc:
        raise ValueError("functional-store UFCx integral ids are malformed") from exc

    try:
        rank = int(form.rank)
        dtype = np.dtype(form.dtype).str
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("functional-store compiled Form type identity is missing") from exc
    if rank != 1 or dtype != np.dtype(np.complex128).str:
        raise ValueError(
            "functional-store compiled surface Form must be complex128 rank one"
        )

    try:
        tag = int(assembler.tag)
    except (AttributeError, TypeError, ValueError, OverflowError) as exc:
        raise ValueError("functional-store surface tag identity is missing") from exc

    return {
        "side": expected_side,
        "component": expected_component,
        "tag": tag,
        "compiled_form_api": "dolfinx.fem.Form.module+ufcx_form.signature+integral_types+rank+dtype",
        **module_identity,
        "ufcx_form_signature": ufcx_signature,
        "integral_types": integral_type_names,
        "ufcx_integral_offsets": offsets,
        "ufcx_integral_ids": integral_ids,
        "rank": rank,
        "dtype": dtype,
    }


def _compiled_surface_form_identity(
    assembler: Any,
    *,
    side: str,
    component: int,
    module_identity_cache: dict[tuple[Any, ...], dict[str, Any]],
) -> dict[str, Any]:
    """Attach bounded loaded-Form diagnostics to identity failures."""

    try:
        return _compiled_surface_form_identity_impl(
            assembler,
            side=side,
            component=component,
            module_identity_cache=module_identity_cache,
        )
    except (TypeError, ValueError) as exc:
        form = getattr(assembler, "form", None)
        diagnostic = _compiled_form_api_diagnostic(form)
        details = json.dumps(
            diagnostic,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        raise type(exc)(f"{exc}; form_api_diagnostic={details}") from exc


def _surface_form_identities(
    surface_assemblers: Mapping[tuple[str, int], Any],
    compiled_surface_assemblers: Mapping[tuple[str, int], Any] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Return strict compiled identities for both components on both sides.

    A pointwise paired assembler has no compiled ``fem.Form`` of its own.  Its
    caller may therefore provide the same-space native FFCx assemblers whose
    compiled component forms are the independent surface-form witness.  The
    selected backend's numerical identity remains recorded from
    ``surface_assemblers`` separately.
    """

    expected = {
        (side, component)
        for side in ("bottom", "top")
        for component in (0, 1)
    }
    if set(surface_assemblers) != expected:
        raise ValueError("functional-store needs all four keyed surface assemblers")
    identity_assemblers = (
        surface_assemblers
        if compiled_surface_assemblers is None
        else compiled_surface_assemblers
    )
    if set(identity_assemblers) != expected:
        raise ValueError(
            "functional-store needs all four compiled component-form identities"
        )
    for key in expected:
        selected = surface_assemblers[key]
        compiled = identity_assemblers[key]
        if (
            compiled.function_space is not selected.function_space
            or compiled.mesh_data is not selected.mesh_data
            or int(compiled.component) != int(selected.component)
            or int(compiled.tag) != int(selected.tag)
            or str(getattr(compiled, "side", key[0])) != key[0]
        ):
            raise ValueError(
                "functional-store compiled Form witness is not the same keyed mesh/space/component"
            )
    module_identity_cache: dict[tuple[Any, ...], dict[str, Any]] = {}
    return {
        side: [
            _compiled_surface_form_identity(
                identity_assemblers[(side, component)],
                side=side,
                component=component,
                module_identity_cache=module_identity_cache,
            )
            for component in (0, 1)
        ]
        for side in ("bottom", "top")
    }


def _p6_surface_provider_identity(
    surface_assemblers: Mapping[tuple[str, int], Any],
    *,
    compiled_surface_assemblers: Mapping[tuple[str, int], Any] | None,
    mpc: Any,
) -> dict[str, Any]:
    """Bind the actual live paired p6 context without constructing native Forms."""

    from .dtn_port_3d import _SurfaceLegendreMomentAssembler
    from .fullspace_surface_legendre import SURFACE_COMPONENT_PAIR_BACKEND

    expected = {
        (side, component)
        for side in ("bottom", "top")
        for component in (0, 1)
    }
    if compiled_surface_assemblers is not None:
        raise ValueError(
            "p6 functional identity rejects injected compiled surface Forms"
        )
    if set(surface_assemblers) != expected:
        raise ValueError("p6 functional identity requires all four paired assemblers")
    if any(not isinstance(value, _SurfaceLegendreMomentAssembler) for value in surface_assemblers.values()):
        raise TypeError("p6 functional identity requires the actual paired assemblers")
    contexts = {
        id(context): context
        for assembler in surface_assemblers.values()
        if (context := getattr(assembler, "context", None)) is not None
    }
    if len(contexts) != 1 or any(
        getattr(assembler, "context", None) is not next(iter(contexts.values()))
        for assembler in surface_assemblers.values()
    ):
        raise ValueError("p6 functional identity requires one shared live context")
    context = next(iter(contexts.values()))
    if (
        context is not next(iter(surface_assemblers.values())).context
        or context.mpc is not mpc
        or context.backend != SURFACE_COMPONENT_PAIR_BACKEND
        or int(context.degree) != 6
        or int(context.quadrature_degree) != 160
        or not context._geometry_cache_enabled
        or not context._prepare_trace_contraction
        or context._weighted_moment_contraction is None
    ):
        raise ValueError("p6 functional identity context route differs from the qualified provider")
    function_space = context.function_space
    mesh_data = context.mesh_data
    if mpc.function_space.mesh is not mesh_data.mesh:
        raise ValueError("p6 functional identity MPC and context use different meshes")
    assembler_descriptors: list[dict[str, Any]] = []
    for side, component in sorted(expected):
        assembler = surface_assemblers[(side, component)]
        if (
            assembler.context is not context
            or assembler.function_space is not function_space
            or assembler.mesh_data is not mesh_data
            or int(assembler.component) != component
            or str(assembler.side) != side
            or str(assembler.surface_backend) != SURFACE_COMPONENT_PAIR_BACKEND
        ):
            raise ValueError("p6 paired assembler is not bound to its live context key")
        assembler_descriptors.append(
            {"side": side, "component": component, "tag": int(assembler.tag)}
        )
    descriptor_factory = getattr(context, "functional_store_identity_descriptor", None)
    if not callable(descriptor_factory):
        raise TypeError("p6 context has no numerical functional-store identity provider")
    context_descriptor = descriptor_factory()
    _validate_p6_context_descriptor(context_descriptor)
    return {
        "schema": P6_SURFACE_PROVIDER_SCHEMA,
        "backend": SURFACE_COMPONENT_PAIR_BACKEND,
        "degree": 6,
        "assemblers": assembler_descriptors,
        "context": context_descriptor,
    }


def _require_sha256(value: Any, label: str) -> None:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError(f"functional-store {label} SHA is malformed")


def _validate_p6_context_descriptor(descriptor: Any) -> None:
    if not isinstance(descriptor, Mapping):
        raise TypeError("p6 context numerical descriptor must be a mapping")
    required = {
        "schema",
        "backend",
        "degree",
        "quadrature_degree",
        "weighted_moment_contraction",
        "prepared_trace_contraction",
        "element",
        "quadrature_and_basis_arrays",
        "coordinate_element",
        "trace_reference_tensors",
    }
    if required.difference(descriptor):
        raise ValueError("p6 context numerical descriptor is incomplete")
    from .fullspace_surface_legendre import (
        SURFACE_COMPONENT_PAIR_BACKEND,
        SURFACE_WEIGHTED_MOMENT_CONTRACTIONS,
    )

    if (
        descriptor["schema"] != P6_CONTEXT_PROVIDER_SCHEMA
        or descriptor["backend"] != SURFACE_COMPONENT_PAIR_BACKEND
        or int(descriptor["degree"]) != 6
        or int(descriptor["quadrature_degree"]) != 160
        or descriptor["weighted_moment_contraction"]
        not in SURFACE_WEIGHTED_MOMENT_CONTRACTIONS
    ):
        raise ValueError("p6 context numerical descriptor route differs")
    prepared = descriptor["prepared_trace_contraction"]
    if (
        not isinstance(prepared, Mapping)
        or prepared.get("enabled") is not True
        or prepared.get("expression") != "ikab,kab->i"
        or set(prepared.get("side_plans", {})) != {"bottom", "top"}
    ):
        raise ValueError("p6 prepared-trace identity is incomplete")
    expected_arrays = {
        "interval_points",
        "interval_weights",
        "quadrilateral_points",
        "quadrilateral_weights",
        "polynomial_values",
        "expanded_polynomial_x",
        "expanded_polynomial_y",
    }
    arrays = descriptor["quadrature_and_basis_arrays"]
    if not isinstance(arrays, Mapping) or expected_arrays.difference(arrays):
        raise ValueError("p6 quadrature/basis identity is incomplete")
    for name in expected_arrays:
        entry = arrays[name]
        if not isinstance(entry, Mapping):
            raise TypeError(f"p6 numerical array identity is not a mapping: {name}")
        _require_sha256(entry.get("sha256"), f"p6 {name}")
        if (
            not isinstance(entry.get("dtype"), str)
            or not isinstance(entry.get("shape"), list)
            or not entry["shape"]
            or any(int(value) <= 0 for value in entry["shape"])
            or int(entry.get("nbytes", -1)) <= 0
        ):
            raise ValueError(f"p6 numerical array descriptor is malformed: {name}")
    element = descriptor["element"]
    if not isinstance(element, Mapping) or not isinstance(
        element.get("coefficient_matrix"), Mapping
    ):
        raise TypeError("p6 Basix element identity is malformed")
    _require_sha256(
        element["coefficient_matrix"].get("sha256"), "p6 Basix coefficient matrix"
    )
    _require_sha256(
        element.get("endpoint_polynomial_table_sha256"),
        "p6 endpoint polynomial table",
    )
    coordinate = descriptor["coordinate_element"]
    if not isinstance(coordinate, Mapping) or set(
        coordinate.get("consumed_tables_by_side", {})
    ) != {"bottom", "top"}:
        raise ValueError("p6 consumed coordinate-table identity is incomplete")
    for side, value in coordinate["consumed_tables_by_side"].items():
        for field in ("values", "derivatives", "facet_jacobian"):
            entry = value.get(field)
            if not isinstance(entry, Mapping):
                raise TypeError(f"p6 coordinate {side} {field} identity is malformed")
            _require_sha256(entry.get("sha256"), f"p6 coordinate {side} {field}")
    traces = descriptor["trace_reference_tensors"]
    if not isinstance(traces, Mapping) or set(traces) != {"bottom", "top"}:
        raise ValueError("p6 reference-trace identity is incomplete")
    for side, entry in traces.items():
        if not isinstance(entry, Mapping):
            raise TypeError(f"p6 {side} reference-trace descriptor is not a mapping")
        _require_sha256(entry.get("sha256"), f"p6 {side} reference trace")
        plan = prepared["side_plans"].get(side)
        if not isinstance(plan, Mapping) or plan.get("trace_sha256") != entry["sha256"]:
            raise ValueError(f"p6 {side} prepared trace is detached from its table")


def _array_descriptor(array: np.ndarray) -> dict[str, Any]:
    return {
        "dtype": array.dtype.str,
        "shape": [int(item) for item in array.shape],
        "nbytes": int(array.nbytes),
    }


def _mode_key_from_identity(identity: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        int(identity["mode_index"]),
        str(identity["side"]),
        int(identity["m"]),
        int(identity["n"]),
        str(identity["polarization"]),
    )


def _expected_float(value: Any) -> float:
    if isinstance(value, Mapping) and set(value) == {"float64_hex"}:
        return float.fromhex(str(value["float64_hex"]))
    return float(value)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _mkdir_durable(path: Path) -> None:
    """Create missing store path components and persist each parent entry."""

    missing: list[Path] = []
    current = path
    while not current.exists():
        if current.is_symlink():
            raise ValueError("functional-store path may not traverse a symlink")
        missing.append(current)
        parent = current.parent
        if parent == current:
            raise ValueError("functional-store path has no existing ancestor")
        current = parent
    if current.is_symlink() or not current.is_dir():
        raise ValueError("functional-store path ancestor is not a real directory")
    for directory in reversed(missing):
        try:
            directory.mkdir()
        except FileExistsError:
            if directory.is_symlink() or not directory.is_dir():
                raise ValueError("functional-store path raced with a non-directory")
        _fsync_directory(directory.parent)


def _path_has_symlink_component(path: Path) -> bool:
    if not path.is_absolute():
        return True
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _sha256_file(path: Path) -> tuple[str, int, float]:
    started = time.perf_counter()
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while block := stream.read(_HASH_BLOCK_BYTES):
            digest.update(block)
            size += len(block)
    return digest.hexdigest(), size, time.perf_counter() - started


def _validate_operator_selection_identity(selection: Any, mode_identity: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(selection, Mapping):
        raise TypeError("functional-store operator selection must be a mapping")
    value = _json_safe(dict(selection))
    required = {
        "schema",
        "policy",
        "parent_mode_count",
        "parent_mode_sha256",
        "active_mode_count",
        "active_mode_sha256",
        "expected_active_mode_sha256",
        "selected_parent_indices_sha256",
        "side_polarization_counts",
        "m_range_in_each_side_polarization",
        "quadrature_inventory",
        "operator_scope",
    }
    if set(value) != required:
        raise ValueError("functional-store N0 operator selection fields differ")
    expected_groups = {
        "bottom_p": 143,
        "bottom_s": 143,
        "top_p": 143,
        "top_s": 143,
    }
    if (
        value.get("schema") != "task39extra.dtn-mode-selection.v1"
        or value.get("policy") != "n_equals_zero_both_ports_both_polarizations"
        or value.get("parent_mode_count") != 32060
        or value.get("parent_mode_sha256")
        != "7f023c73d7b63379955642dd062e47ba7004f3cdf0accf42684286c4af71dbfb"
        or value.get("active_mode_count") != 572
        or int(mode_identity.get("count", -1)) != 572
        or value.get("active_mode_sha256")
        != "946e0d294b99cb7f44817c3649029942ac325f345eb1770caa566183d2b04f3b"
        or value.get("active_mode_sha256")
        != mode_identity.get("ordered_manifest_sha256")
        or value.get("expected_active_mode_sha256")
        != "946e0d294b99cb7f44817c3649029942ac325f345eb1770caa566183d2b04f3b"
        or value.get("side_polarization_counts") != expected_groups
        or value.get("m_range_in_each_side_polarization") != [-142, 0]
        or value.get("quadrature_inventory") != "full_parent_modes"
        or value.get("operator_scope") != "n0_filtered_dtn_not_full_dtn"
        or not re.fullmatch(
            r"[0-9a-f]{64}", str(value.get("selected_parent_indices_sha256", ""))
        )
        or not re.fullmatch(r"[0-9a-f]{64}", str(value.get("active_mode_sha256", "")))
    ):
        raise ValueError("functional-store N0 operator selection identity is malformed")
    return value


def _validate_n0_parent_compatibility_contract(
    compatibility: Any,
) -> dict[str, Any]:
    if not isinstance(compatibility, Mapping):
        raise TypeError("N0 parent-store compatibility must be a mapping")
    value = _json_safe(dict(compatibility))
    required = {
        "schema",
        "parent_source_sha256",
        "parent_resolved_config_sha256",
        "parent_input_sha256",
        "parent_physical_model_sha256",
        "parent_mode_count",
        "parent_mode_sha256",
        "allowed_implementation_file_changes",
        "stores",
    }
    if set(value) != required:
        raise ValueError("N0 parent-store compatibility fields differ")
    expected_hashes = (
        "parent_source_sha256",
        "parent_resolved_config_sha256",
        "parent_input_sha256",
        "parent_physical_model_sha256",
        "parent_mode_sha256",
    )
    if any(not re.fullmatch(r"[0-9a-f]{40,64}", str(value[key])) for key in expected_hashes):
        raise ValueError("N0 parent-store compatibility hash is malformed")
    if (
        value.get("schema") != N0_PARENT_COMPATIBILITY_SCHEMA
        or value.get("parent_source_sha256")
        != "2e72ce0df34a8781dca3d44d6fcaee2b7b6f3150"
        or value.get("parent_resolved_config_sha256")
        != "ca13bffb6636a8278c2aaca5ba00f849e806702c3e29eee892aa9637424d5179"
        or value.get("parent_input_sha256")
        != "3be4d0b12713f2cef4b7c90c97024b286d3ea8a7bd4d343b2178792f0121d480"
        or value.get("parent_physical_model_sha256")
        != "965c5ad2c25b817b01dbe5eaab1ee557a3d5c84ea4913b620466bb13f0795e4e"
        or value.get("parent_mode_count") != N0_PARENT_MODE_COUNT
        or value.get("parent_mode_sha256") != N0_PARENT_MODE_SHA256
        or value.get("allowed_implementation_file_changes")
        != sorted(N0_PARENT_COMPATIBLE_IMPLEMENTATION_FILES)
    ):
        raise ValueError("N0 parent-store compatibility is outside the reviewed mapping")
    stores = value.get("stores")
    if not isinstance(stores, Mapping) or set(stores) != {"3", "6"}:
        raise ValueError("N0 compatibility must bind both parent degree stores")
    for degree in ("3", "6"):
        entry = stores[degree]
        if not isinstance(entry, Mapping) or set(entry) != {
            "root",
            "numerical_identity_sha256",
        }:
            raise ValueError(f"N0 parent p{degree} store binding is malformed")
        root = Path(str(entry["root"]))
        if (
            not root.is_absolute()
            or _path_has_symlink_component(root)
            or not re.fullmatch(
                r"[0-9a-f]{64}", str(entry["numerical_identity_sha256"])
            )
        ):
            raise ValueError(f"N0 parent p{degree} store path/hash is invalid")
    return value


def _n0_remapped_mode_identity_matches(
    parent_mode_identity: Mapping[str, Any],
    active_mode_identity: Mapping[str, Any],
    active_index: int,
) -> bool:
    """Compare parent and active mode physics in the store's canonical form."""

    remapped = _json_safe(dict(parent_mode_identity))
    remapped["mode_index"] = int(active_index)
    return remapped == _json_safe(dict(active_mode_identity))


def _validate_identity(identity: Mapping[str, Any]) -> dict[str, Any]:
    missing = _REQUIRED_IDENTITY_KEYS.difference(identity)
    if missing:
        raise ValueError(
            "functional-store numerical identity lacks: " + ", ".join(sorted(missing))
        )
    source_sha = str(identity["source_sha256"])
    if not re.fullmatch(r"[0-9a-f]{40,64}", source_sha):
        raise ValueError("functional-store source SHA is malformed")
    implementation = identity["implementation_file_sha256"]
    if not isinstance(implementation, Mapping) or not implementation:
        raise ValueError("functional-store implementation identity is empty")
    for name, digest in implementation.items():
        relative_name = str(name)
        if (
            not relative_name
            or relative_name.startswith("/")
            or ".." in Path(relative_name).parts
            or not re.fullmatch(r"[0-9a-f]{64}", str(digest))
        ):
            raise ValueError(
                "functional-store implementation file identity is malformed"
            )
    degree = int(identity["degree"])
    if degree not in (3, 6):
        raise ValueError("functional-store supports only separate p3/p6 stores")
    from .fullspace_surface_legendre import SURFACE_COMPONENT_PAIR_BACKEND

    expected_backend = (
        SURFACE_COMPONENT_PAIR_BACKEND if degree == 6 else "native_ffcx"
    )
    if identity["backend"] != expected_backend:
        raise ValueError(
            "functional-store backend does not match the degree-specific route"
        )
    expected_identity_schema = (
        P6_NUMERICAL_IDENTITY_SCHEMA if degree == 6 else P3_NUMERICAL_IDENTITY_SCHEMA
    )
    if identity["schema"] != expected_identity_schema:
        raise ValueError(
            "functional-store numerical identity schema does not match its degree-specific provider"
        )
    for key in ("mesh", "dof_mpc", "modes", "quadrature", "abi"):
        if not isinstance(identity[key], Mapping):
            raise TypeError(f"functional-store {key} identity must be a mapping")
    if int(identity["quadrature"].get("degree", -1)) != 160:
        raise ValueError("functional-store route is qualified only for q160")
    if degree == 6:
        if "surface_forms" in identity["quadrature"]:
            raise ValueError("p6 provider identity may not contain native Form identities")
        _validate_p6_surface_provider_descriptor(
            identity["quadrature"].get("p6_surface_provider")
        )
    elif "p6_surface_provider" in identity["quadrature"]:
        raise ValueError("p3 native identity may not contain a p6 context provider")
    mode_sha = str(identity["modes"].get("ordered_manifest_sha256", ""))
    if int(identity["modes"].get("count", -1)) <= 0 or not re.fullmatch(
        r"[0-9a-f]{64}", mode_sha
    ):
        raise ValueError("functional-store ordered mode identity is malformed")
    normalized = _json_safe(dict(identity))
    if "operator_selection" in normalized:
        normalized["operator_selection"] = _validate_operator_selection_identity(
            normalized["operator_selection"], normalized["modes"]
        )
    return normalized


def _validate_p6_surface_provider_descriptor(provider: Any) -> None:
    from .fullspace_surface_legendre import SURFACE_COMPONENT_PAIR_BACKEND

    if not isinstance(provider, Mapping):
        raise TypeError("p6 surface provider identity must be a mapping")
    if (
        provider.get("schema") != P6_SURFACE_PROVIDER_SCHEMA
        or provider.get("backend") != SURFACE_COMPONENT_PAIR_BACKEND
        or int(provider.get("degree", -1)) != 6
    ):
        raise ValueError("p6 surface provider identity route differs")
    assemblers = provider.get("assemblers")
    expected = [
        {"side": side, "component": component}
        for side in ("bottom", "top")
        for component in (0, 1)
    ]
    if not isinstance(assemblers, list) or len(assemblers) != len(expected):
        raise ValueError("p6 surface provider must bind four assembler keys")
    for actual, key in zip(assemblers, expected, strict=True):
        if (
            not isinstance(actual, Mapping)
            or actual.get("side") != key["side"]
            or int(actual.get("component", -1)) != key["component"]
            or int(actual.get("tag", -1)) < 0
        ):
            raise ValueError("p6 surface provider assembler keys are malformed")
    _validate_p6_context_descriptor(provider.get("context"))


def _live_abi_identity(mesh: Any) -> dict[str, Any]:
    import basix
    import dolfinx
    import dolfinx_mpc
    from mpi4py import MPI
    from mpi4py import __version__ as mpi4py_version
    from petsc4py import PETSc
    from petsc4py import __version__ as petsc4py_version

    return {
        "python": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "byteorder": sys.byteorder,
        "numpy": np.__version__,
        "basix": str(getattr(basix, "__version__", "unknown")),
        "dolfinx": str(getattr(dolfinx, "__version__", "unknown")),
        "dolfinx_mpc": str(getattr(dolfinx_mpc, "__version__", "unknown")),
        "petsc4py": str(petsc4py_version),
        "petsc": str(PETSc.Sys.getVersion()),
        "petsc_scalar_dtype": np.dtype(PETSc.ScalarType).str,
        "petsc_index_dtype": np.dtype(PETSc.IntType).str,
        "mpi4py": str(mpi4py_version),
        "mpi_size": int(mesh.comm.size),
        "mpi_library": str(MPI.Get_library_version()).strip(),
    }


def _implementation_file_sha256() -> dict[str, str]:
    """Hash the small source files that define this carrier/store route."""

    root = Path(__file__).resolve().parents[2]
    relative_files = (
        "src/geometry/mesh_builder_3d.py",
        "src/io/input_validation.py",
        "src/io/resolved_config.py",
        "src/solvers/fullspace_dtn_action.py",
        "src/solvers/fullspace_dtn_functional_store.py",
        "src/solvers/fullspace_surface_legendre.py",
        "src/solvers/dtn_port_3d.py",
        "src/solvers/fullspace_same_mesh_hcurl_pmg_global.py",
        "src/solvers/fullspace_same_mesh_hcurl_pmg_setup.py",
        "src/solvers/fullspace_same_mesh_hcurl_pmg_physical.py",
        "src/runners/math_backend_identity.py",
        "src/runners/physical_retained_condensed_v20.py",
        "src/runners/physical_intermediate.py",
        "src/io/native_capacity_profile.py",
    )
    result: dict[str, str] = {}
    for relative in relative_files:
        path = root / relative
        if path.is_symlink() or not path.is_file():
            raise ValueError(
                f"functional-store implementation file is unavailable: {relative}"
            )
        result[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def build_surface_functional_numerical_identity(
    *,
    source_sha256: str,
    resolved_config_sha256: str,
    input_sha256: str,
    physical_model_sha256: str,
    degree: int,
    backend: str,
    quadrature_degree: int,
    mode_count: int,
    mode_manifest_sha256: str,
    surface_assemblers: Mapping[tuple[str, int], Any],
    mpc: Any,
    compiled_surface_assemblers: Mapping[tuple[str, int], Any] | None = None,
    operator_selection: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a strict live identity without retaining another mesh-sized copy."""

    degree = int(degree)
    if degree == 6 and compiled_surface_assemblers is not None:
        raise ValueError(
            "p6 functional identity rejects injected compiled surface Forms"
        )

    expected_form_keys = {
        (side, component) for side in ("bottom", "top") for component in (0, 1)
    }
    if mpc is None or set(surface_assemblers) != expected_form_keys:
        raise ValueError(
            "functional-store identity needs the four finalized port forms"
        )
    if int(mpc.function_space.mesh.comm.size) != 1:
        raise NotImplementedError("functional shards are qualified for MPI1 only")
    first = surface_assemblers[("bottom", 0)]
    function_space = first.function_space
    mesh_data = first.mesh_data
    mesh = mesh_data.mesh
    if mpc.function_space.mesh is not mesh or function_space.mesh is not mesh:
        raise ValueError("functional-store spaces do not share the finalized mesh")
    if any(
        assembler.function_space is not function_space
        or assembler.mesh_data is not mesh_data
        or int(assembler.component) != int(component)
        or str(getattr(assembler, "side", side)) != str(side)
        or int(assembler.tag) != int(surface_assemblers[(side, 0)].tag)
        for (side, component), assembler in surface_assemblers.items()
    ):
        raise ValueError("functional-store surface-form identity is inconsistent")

    source = str(source_sha256)
    if not re.fullmatch(r"[0-9a-f]{40,64}", source):
        raise ValueError("functional-store source SHA is malformed")
    resolved_sha = str(resolved_config_sha256)
    if not re.fullmatch(r"[0-9a-f]{64}", resolved_sha):
        raise ValueError("functional-store resolved-config SHA is malformed")
    input_sha = str(input_sha256)
    physical_sha = str(physical_model_sha256)
    if not re.fullmatch(r"[0-9a-f]{64}", input_sha):
        raise ValueError("functional-store input SHA is malformed")
    if not re.fullmatch(r"[0-9a-f]{64}", physical_sha):
        raise ValueError("functional-store physical-model SHA is malformed")
    mode_sha = str(mode_manifest_sha256)
    if not re.fullmatch(r"[0-9a-f]{64}", mode_sha) or int(mode_count) <= 0:
        raise ValueError("functional-store ordered mode identity is malformed")

    geometry_coordinates = np.asarray(mesh.geometry.x)
    geometry_dofmap = np.asarray(mesh.geometry.dofmap)
    mesh_digest = hashlib.sha256(b"task39extra.port-functional.mesh.v1\0")
    _array_hash_update(mesh_digest, "raw_geometry_coordinates", geometry_coordinates)
    _array_hash_update(mesh_digest, "geometry_dofmap", geometry_dofmap)
    mesh_identity = {
        "cell_name": str(mesh.topology.cell_name()),
        "topological_dimension": int(mesh.topology.dim),
        "global_cell_count": int(
            mesh.topology.index_map(mesh.topology.dim).size_global
        ),
        "raw_coordinate_shape": [int(item) for item in geometry_coordinates.shape],
        "raw_coordinate_dtype": geometry_coordinates.dtype.str,
        "geometry_dofmap_shape": [int(item) for item in geometry_dofmap.shape],
        "geometry_dofmap_dtype": geometry_dofmap.dtype.str,
        "raw_geometry_and_dofmap_sha256": mesh_digest.hexdigest(),
    }

    index_map = function_space.dofmap.index_map
    if int(function_space.dofmap.index_map_bs) != 1:
        raise NotImplementedError(
            "functional-store row identity requires block size one"
        )
    ghosts = np.asarray(index_map.ghosts)
    owners = np.asarray(index_map.owners)
    if not ghosts.flags.c_contiguous or not owners.flags.c_contiguous:
        raise ValueError("functional-store index-map arrays are not contiguous")
    dof_digest = hashlib.sha256(b"task39extra.port-functional.boundary-dofs-mpc.v1\0")
    tdim = int(mesh.topology.dim)
    fdim = tdim - 1
    mesh.topology.create_connectivity(fdim, tdim)
    mesh.topology.create_connectivity(tdim, fdim)
    facet_to_cell = mesh.topology.connectivity(fdim, tdim)
    cell_to_facet = mesh.topology.connectivity(tdim, fdim)
    cell_permutations = np.asarray(mesh.topology.get_cell_permutation_info())
    coefficients_source, offsets_source = mpc.coefficients()
    coefficients = np.asarray(coefficients_source)
    offsets = np.asarray(offsets_source)
    is_slave = np.asarray(mpc.is_slave)
    if (
        coefficients.ndim != 1
        or not np.issubdtype(coefficients.dtype, np.complexfloating)
        or offsets.ndim != 1
        or not np.issubdtype(offsets.dtype, np.integer)
        or is_slave.ndim != 1
        or not np.issubdtype(is_slave.dtype, np.integer)
    ):
        raise ValueError("functional-store MPC arrays have malformed dtypes or shapes")
    local_storage_size = int(index_map.size_local + index_map.num_ghosts)
    from .fullspace_surface_legendre import validate_boundary_mpc_row

    for side in ("bottom", "top"):
        primary = surface_assemblers[(side, 0)]
        companion = surface_assemblers[(side, 1)]
        if int(primary.tag) != int(companion.tag):
            raise ValueError("paired component assemblers use different side tags")
        facets = np.asarray(mesh_data.facet_tags.find(int(primary.tag)))
        if (
            facets.ndim != 1
            or not np.issubdtype(facets.dtype, np.integer)
            or np.unique(facets).size != facets.size
        ):
            raise ValueError("functional-store boundary facet inventory is malformed")
        dof_digest.update(side.encode("ascii") + b"\0")
        dof_digest.update(_canonical_json_bytes(int(primary.tag)))
        dof_digest.update(b"\0")
        _array_hash_update(dof_digest, f"{side}.facets", np.ascontiguousarray(facets))
        seen_cells: set[int] = set()
        for facet_value in facets:
            facet = int(facet_value)
            adjacent = np.asarray(facet_to_cell.links(facet))
            if adjacent.shape != (1,):
                raise NotImplementedError(
                    "functional store requires exterior port facets"
                )
            cell = int(adjacent[0])
            local_facets = np.asarray(cell_to_facet.links(cell))
            local_matches = np.flatnonzero(local_facets == facet)
            if local_matches.size != 1:
                raise ValueError("functional-store facet has no unique local cell face")
            cell_dofs = np.asarray(function_space.dofmap.cell_dofs(cell))
            if cell_dofs.ndim != 1 or not np.issubdtype(cell_dofs.dtype, np.integer):
                raise ValueError("functional-store cell DOF row is malformed")
            dof_digest.update(
                _canonical_json_bytes(
                    {
                        "facet": facet,
                        "cell": cell,
                        "local_facet": int(local_matches[0]),
                        "permutation": int(cell_permutations[cell]),
                    }
                )
            )
            _array_hash_update(dof_digest, "cell_dofs", np.ascontiguousarray(cell_dofs))
            global_dofs = np.empty(cell_dofs.size, dtype=np.int64)
            for offset, local_dof_value in enumerate(cell_dofs):
                local_dof = int(local_dof_value)
                if local_dof < 0 or local_dof >= local_storage_size:
                    raise ValueError(
                        "functional-store cell DOF is outside local storage"
                    )
                if local_dof < int(index_map.size_local):
                    global_dofs[offset] = int(index_map.local_range[0]) + local_dof
                else:
                    ghost_index = local_dof - int(index_map.size_local)
                    if ghost_index >= ghosts.size:
                        raise ValueError(
                            "functional-store ghost DOF has no global identity"
                        )
                    global_dofs[offset] = int(ghosts[ghost_index])
            _array_hash_update(dof_digest, "cell_global_dofs", global_dofs)
            if cell in seen_cells:
                continue
            seen_cells.add(cell)
            slave_rows = np.asarray(mpc.cell_to_slaves.links(cell))
            if slave_rows.ndim != 1 or not np.issubdtype(slave_rows.dtype, np.integer):
                raise ValueError("functional-store boundary slave row is malformed")
            _array_hash_update(
                dof_digest, "cell_slaves", np.ascontiguousarray(slave_rows)
            )
            for slave_value in slave_rows:
                slave = int(slave_value)
                masters_source = np.asarray(mpc.masters.links(slave))
                masters, coeffs = validate_boundary_mpc_row(
                    slave,
                    offsets,
                    coefficients,
                    is_slave,
                    masters_source,
                    local_storage_size,
                )
                dof_digest.update(_canonical_json_bytes(slave))
                _array_hash_update(dof_digest, "slave_masters", masters)
                _array_hash_update(dof_digest, "slave_coefficients", coeffs)

    basix_element = function_space.element.basix_element
    element_hash = getattr(basix_element, "hash", None)
    if not callable(element_hash):
        raise NotImplementedError("functional-store Basix element hash is unavailable")
    dof_mpc_identity = {
        "element": {
            "hash": int(element_hash()),
            "family": str(basix_element.family),
            "degree": int(basix_element.degree),
            "cell_type": str(basix_element.cell_type),
            "value_size": int(basix_element.value_size),
            "map_type": str(basix_element.map_type),
            "polyset_type": str(basix_element.polyset_type),
        },
        "ownership": {
            "local_range": [int(value) for value in index_map.local_range],
            "size_local": int(index_map.size_local),
            "size_global": int(index_map.size_global),
            "num_ghosts": int(index_map.num_ghosts),
        },
        "ghost_rows_sha256": hashlib.sha256(memoryview(ghosts).cast("B")).hexdigest(),
        "ghost_owners_sha256": hashlib.sha256(memoryview(owners).cast("B")).hexdigest(),
        "boundary_cell_dofs_and_mpc_sha256": dof_digest.hexdigest(),
    }

    if degree == 6:
        p6_provider = _p6_surface_provider_identity(
            surface_assemblers,
            compiled_surface_assemblers=compiled_surface_assemblers,
            mpc=mpc,
        )
        quadrature_identity: dict[str, Any] = {
            "degree": int(quadrature_degree),
            "p6_surface_provider": p6_provider,
        }
        identity_schema = P6_NUMERICAL_IDENTITY_SCHEMA
    else:
        component_form_identities = _surface_form_identities(
            surface_assemblers, compiled_surface_assemblers
        )
        assembler_identities: dict[str, Any] = {}
        for side in ("bottom", "top"):
            assembler = surface_assemblers[(side, 0)]
            context = getattr(assembler, "context", None)
            if context is not None:
                quadrature_metadata = {
                    "quadrature_array_hashes": dict(
                        context.facts["quadrature_array_hashes"]
                    ),
                    "ffcx_coordinate_options": dict(
                        getattr(context, "_ffcx_coordinate_table_options", {})
                    ),
                    "weighted_moment_contraction": getattr(
                        context, "_weighted_moment_contraction", None
                    ),
                }
            else:
                quadrature_metadata = {
                    "identity_source": "compiled_component_form_identity",
                    "compiled_form_components": [
                        int(item["component"])
                        for item in component_form_identities[side]
                    ],
                }
            assembler_identities[side] = {
                "tag": int(assembler.tag),
                "component_form_metadata": component_form_identities[side],
                "component_form_identity_role": (
                    "same-space native FFCx component-form witness; selected numerical backend identity is recorded independently"
                    if compiled_surface_assemblers is not None
                    and compiled_surface_assemblers is not surface_assemblers
                    else "selected assembler compiled FFCx component forms"
                ),
                "quadrature": quadrature_metadata,
            }
        quadrature_identity = {
            "degree": int(quadrature_degree),
            "surface_forms": assembler_identities,
        }
        identity_schema = P3_NUMERICAL_IDENTITY_SCHEMA

    identity = {
        "schema": identity_schema,
        "source_sha256": source,
        "resolved_config_sha256": resolved_sha,
        "implementation_file_sha256": _implementation_file_sha256(),
        "input_sha256": input_sha,
        "physical_model_sha256": physical_sha,
        "backend": str(backend),
        "degree": int(degree),
        "mesh": mesh_identity,
        "dof_mpc": dof_mpc_identity,
        "modes": {
            "count": int(mode_count),
            "ordered_manifest_sha256": mode_sha,
        },
        "quadrature": quadrature_identity,
        "abi": _live_abi_identity(mesh),
    }
    if operator_selection is not None:
        identity["operator_selection"] = _validate_operator_selection_identity(
            operator_selection, identity["modes"]
        )
    return _validate_identity(identity)


class PortFunctionalShardStore:
    """Single-writer append-only store of validated one-mode NPZ shards."""

    def __init__(
        self,
        root: str | Path,
        numerical_identity: Mapping[str, Any],
        expected_mode_identities: Sequence[Mapping[str, Any]],
        *,
        ownership_range: tuple[int, int],
        slave_rows: np.ndarray,
        row_dtype: Any,
        producer_provenance: Mapping[str, Any],
        max_shard_working_bytes: int,
        max_total_disk_bytes: int,
        disk_reserve_bytes: int,
        _test_fault_hook: Callable[[str], None] | None = None,
    ) -> None:
        identity = _validate_identity(numerical_identity)
        raw_mode_identities = tuple(dict(item) for item in expected_mode_identities)
        mode_identities = tuple(_json_safe(item) for item in raw_mode_identities)
        if not mode_identities:
            raise ValueError(
                "functional store requires a nonempty ordered mode manifest"
            )
        if int(identity["modes"]["count"]) != len(mode_identities):
            raise ValueError(
                "functional-store mode count differs from its numerical identity"
            )
        for index, item in enumerate(mode_identities):
            if (
                _REQUIRED_MODE_IDENTITY_KEYS.difference(item)
                or item.get("schema") != "fullspace-dtn.mode.v1"
                or int(item.get("mode_index", -1)) != index
                or item.get("side") not in {"bottom", "top"}
                or item.get("polarization") not in {"s", "p"}
            ):
                raise ValueError(
                    "functional-store expected mode manifest is not ordered"
                )
            _json_safe(item)
        from .fullspace_dtn_action import (
            FULLSPACE_DTN_MANIFEST_SCHEMA,
            FULLSPACE_DTN_PROFILE,
        )
        from .fullspace_dtn_action import (
            _canonical_json_bytes as _canonical_mode_json_bytes,
        )

        mode_manifest_payload = {
            "schema": FULLSPACE_DTN_MANIFEST_SCHEMA,
            "profile": FULLSPACE_DTN_PROFILE,
            "mode_count": len(raw_mode_identities),
            "modes": list(raw_mode_identities),
        }
        actual_mode_sha = hashlib.sha256(
            _canonical_mode_json_bytes(mode_manifest_payload)
        ).hexdigest()
        if actual_mode_sha != identity["modes"].get("ordered_manifest_sha256"):
            raise ValueError("functional-store ordered mode manifest hash differs")
        self.root = Path(root)
        if _path_has_symlink_component(self.root):
            raise ValueError("functional-store path may not contain symlink components")
        _mkdir_durable(self.root)
        self._identity = identity
        self._identity_bytes = _canonical_json_bytes(identity)
        self._identity_sha256 = hashlib.sha256(self._identity_bytes).hexdigest()
        self._mode_identities = mode_identities
        self._raw_mode_identities = raw_mode_identities
        self._ownership_range = (int(ownership_range[0]), int(ownership_range[1]))
        if (
            self._ownership_range[0] < 0
            or self._ownership_range[1] < self._ownership_range[0]
        ):
            raise ValueError("functional-store ownership range is invalid")
        self._row_dtype = np.dtype(row_dtype)
        if not np.issubdtype(self._row_dtype, np.integer):
            raise ValueError("functional-store row dtype must be integer")
        self._slave_rows = np.asarray(slave_rows)
        if (
            self._slave_rows.dtype != self._row_dtype
            or self._slave_rows.ndim != 1
            or not self._slave_rows.flags.c_contiguous
            or (
                self._slave_rows.size > 1
                and np.any(self._slave_rows[1:] <= self._slave_rows[:-1])
            )
        ):
            raise ValueError(
                "functional-store owned slave rows must be sorted unique integer rows"
            )
        if self._slave_rows.size and (
            int(self._slave_rows[0]) < self._ownership_range[0]
            or int(self._slave_rows[-1]) >= self._ownership_range[1]
        ):
            raise ValueError("functional-store slave rows are outside local ownership")
        self._producer_provenance = _json_safe(dict(producer_provenance))
        self._max_shard_working_bytes = int(max_shard_working_bytes)
        self._max_total_disk_bytes = int(max_total_disk_bytes)
        self._disk_reserve_bytes = int(disk_reserve_bytes)
        if (
            self._max_shard_working_bytes <= SERIALIZATION_SCRATCH_BOUND_BYTES
            or self._max_total_disk_bytes <= 0
            or self._disk_reserve_bytes < 0
        ):
            raise ValueError("functional-store storage budgets are invalid")
        self._test_fault_hook = _test_fault_hook
        self._parent_import_state: dict[str, Any] | None = None
        self._parent_import_facts: dict[str, Any] = {
            "configured": False,
            "status": "NOT_CONFIGURED",
            "attempted_count": 0,
            "imported_count": 0,
            "fallback_count": 0,
            "fallback_reasons": [],
            "omitted_fallback_reason_count": 0,
            "timing_seconds": {
                "parent_manifest_read_seconds": 0.0,
                "parent_payload_hash_seconds": 0.0,
                "parent_payload_read_seconds": 0.0,
                "parent_active_store_commit_seconds": 0.0,
                "parent_fallback_fe_assembly_seconds": 0.0,
            },
        }
        self._lock_stream = None
        self._next_index = 0
        self._committed_disk_bytes = 0
        self._incomplete_temporary_bytes = 0
        self.timing_seconds = {
            "restore_read_seconds": 0.0,
            "restore_hash_seconds": 0.0,
            "active_store_commit_seconds": 0.0,
            "payload_write_seconds": 0.0,
            "payload_hash_seconds": 0.0,
            "payload_fsync_seconds": 0.0,
            "manifest_fsync_seconds": 0.0,
            "directory_fsync_seconds": 0.0,
        }
        self._acquire_lock_and_bind()

    @classmethod
    def for_surface(
        cls,
        root: str | Path,
        *,
        source_sha256: str,
        resolved_config_sha256: str,
        input_sha256: str,
        physical_model_sha256: str,
        degree: int,
        backend: str,
        quadrature_degree: int,
        mode_identities: Sequence[Mapping[str, Any]],
        mode_manifest_sha256: str,
        surface_assemblers: Mapping[tuple[str, int], Any],
        mpc: Any,
        compiled_surface_assemblers: Mapping[tuple[str, int], Any] | None = None,
        operator_selection: Mapping[str, Any] | None = None,
        ownership_range: tuple[int, int],
        slave_rows: np.ndarray,
        row_dtype: Any,
        producer_provenance: Mapping[str, Any],
        max_shard_working_bytes: int,
        max_total_disk_bytes: int,
        disk_reserve_bytes: int,
    ) -> PortFunctionalShardStore:
        identity = build_surface_functional_numerical_identity(
            source_sha256=source_sha256,
            resolved_config_sha256=resolved_config_sha256,
            input_sha256=input_sha256,
            physical_model_sha256=physical_model_sha256,
            degree=degree,
            backend=backend,
            quadrature_degree=quadrature_degree,
            mode_count=len(mode_identities),
            mode_manifest_sha256=mode_manifest_sha256,
            surface_assemblers=surface_assemblers,
            mpc=mpc,
            compiled_surface_assemblers=compiled_surface_assemblers,
            operator_selection=operator_selection,
        )
        return cls(
            root,
            identity,
            mode_identities,
            ownership_range=ownership_range,
            slave_rows=slave_rows,
            row_dtype=row_dtype,
            producer_provenance=producer_provenance,
            max_shard_working_bytes=max_shard_working_bytes,
            max_total_disk_bytes=max_total_disk_bytes,
            disk_reserve_bytes=disk_reserve_bytes,
        )

    def _acquire_lock_and_bind(self) -> None:
        lock_path = self.root / "writer.lock"
        self._lock_stream = lock_path.open("a+b")
        try:
            fcntl.flock(self._lock_stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            identity_path = self.root / "identity.json"
            if identity_path.exists():
                if identity_path.stat().st_size > _MAX_MANIFEST_BYTES:
                    raise ValueError(
                        "functional-store identity manifest exceeds its size bound"
                    )
                if (
                    identity_path.is_symlink()
                    or identity_path.read_bytes()
                    != _canonical_json_bytes(
                        {
                            "schema": STORE_SCHEMA,
                            "numerical_identity": self._identity,
                            "numerical_identity_sha256": self._identity_sha256,
                            "mode_count": len(self._mode_identities),
                        }
                    )
                ):
                    raise ValueError("functional-store numerical identity mismatch")
            else:
                if any(
                    item.name != "writer.lock" and not _TEMP_NAME.fullmatch(item.name)
                    for item in self.root.iterdir()
                ):
                    raise ValueError(
                        "functional-store has data without an identity manifest"
                    )
                self._atomic_write_identity(identity_path)
            self._scan_committed_prefix()
            if (
                self._committed_disk_bytes + self._incomplete_temporary_bytes
                > self._max_total_disk_bytes
            ):
                raise OSError(
                    "existing functional shards exceed the configured disk budget"
                )
        except Exception:
            self.close()
            raise

    def _atomic_write_identity(self, target: Path) -> None:
        payload = _canonical_json_bytes(
            {
                "schema": STORE_SCHEMA,
                "numerical_identity": self._identity,
                "numerical_identity_sha256": self._identity_sha256,
                "mode_count": len(self._mode_identities),
            }
        )
        temporary = self.root / f".tmp_identity_{uuid4().hex}"
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.rename(temporary, target)
        _fsync_directory(self.root)

    def _scan_committed_prefix(self) -> None:
        identity_path = self.root / "identity.json"
        lock_path = self.root / "writer.lock"
        if not identity_path.is_file() or not lock_path.is_file():
            raise ValueError("functional-store root identity or writer lock is missing")
        if identity_path.stat().st_size > _MAX_MANIFEST_BYTES:
            raise ValueError(
                "functional-store identity manifest exceeds its size bound"
            )
        self._committed_disk_bytes = int(
            identity_path.stat().st_size + lock_path.stat().st_size
        )
        indices: list[int] = []
        temporary_directories: list[Path] = []
        for item in self.root.iterdir():
            if item.name in {"identity.json", "writer.lock"}:
                continue
            if _TEMP_NAME.fullmatch(item.name):
                temporary_directories.append(item)
                continue
            match = _SHARD_NAME.fullmatch(item.name)
            if not match or not item.is_dir() or item.is_symlink():
                raise ValueError(f"unexpected functional-store entry {item.name!r}")
            indices.append(int(match.group(1)))
        if len(temporary_directories) > 1:
            raise ValueError(
                "functional-store has multiple incomplete temporary shards"
            )
        if temporary_directories:
            temporary = temporary_directories[0]
            if temporary.is_symlink() or not temporary.is_dir():
                raise ValueError(
                    "functional-store incomplete temporary shard is not a directory"
                )
            temporary_bytes = 0
            for item in temporary.iterdir():
                if (
                    item.name not in {"payload.npz", "manifest.json"}
                    or item.is_symlink()
                    or not item.is_file()
                ):
                    raise ValueError(
                        "functional-store incomplete temporary shard is malformed"
                    )
                temporary_bytes += int(item.stat().st_size)
            if temporary_bytes > self._max_shard_working_bytes:
                raise ValueError(
                    "functional-store incomplete temporary shard exceeds its bound"
                )
            self._incomplete_temporary_bytes = temporary_bytes
        indices.sort()
        if indices != list(range(len(indices))):
            raise ValueError(
                "functional-store committed shards have a gap or duplicate"
            )
        if len(indices) > len(self._mode_identities):
            raise ValueError(
                "functional-store contains more shards than the mode manifest"
            )
        self._next_index = len(indices)
        for index in indices:
            directory, manifest_path, payload_path = self._shard_paths(index)
            if (
                directory.is_symlink()
                or manifest_path.is_symlink()
                or payload_path.is_symlink()
                or not manifest_path.is_file()
                or not payload_path.is_file()
            ):
                raise ValueError("functional-store committed shard is incomplete")
            try:
                if manifest_path.stat().st_size > _MAX_MANIFEST_BYTES:
                    raise ValueError(
                        "functional-store shard manifest exceeds its size bound"
                    )
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                declared_bytes = int(manifest["serialized_bytes"])
            except (
                OSError,
                json.JSONDecodeError,
                KeyError,
                TypeError,
                ValueError,
            ) as exc:
                raise ValueError(
                    "functional-store committed shard manifest is malformed"
                ) from exc
            if declared_bytes != int(payload_path.stat().st_size):
                raise ValueError(
                    "functional-store committed payload size differs from manifest"
                )
            self._committed_disk_bytes += declared_bytes + int(
                manifest_path.stat().st_size
            )

    @property
    def committed_count(self) -> int:
        return self._next_index

    @property
    def identity_sha256(self) -> str:
        return self._identity_sha256

    @property
    def serialized_bytes(self) -> int:
        return self._committed_disk_bytes

    @property
    def audit(self) -> dict[str, Any]:
        return {
            "schema": STORE_SCHEMA,
            "numerical_identity_sha256": self._identity_sha256,
            "degree": int(self._identity["degree"]),
            "committed_functional_count": self._next_index,
            "expected_mode_count": len(self._mode_identities),
            "serialized_bytes_including_manifests": self._committed_disk_bytes,
            "incomplete_temporary_bytes": self._incomplete_temporary_bytes,
            "max_shard_working_bytes": self._max_shard_working_bytes,
            "max_total_disk_bytes": self._max_total_disk_bytes,
            "disk_reserve_bytes": self._disk_reserve_bytes,
            "serialization_scratch_bound_bytes": SERIALIZATION_SCRATCH_BOUND_BYTES,
            "producer_provenance_is_not_numerical_identity": True,
            "timing_seconds": dict(self.timing_seconds),
            "parent_import": _json_safe(self._parent_import_facts),
        }

    def _shard_paths(self, index: int) -> tuple[Path, Path, Path]:
        directory = self.root / f"functional_{index:08d}"
        return directory, directory / "manifest.json", directory / "payload.npz"

    def _read_shard_manifest(self, index: int) -> dict[str, Any]:
        directory, manifest_path, payload_path = self._shard_paths(index)
        if (
            directory.is_symlink()
            or manifest_path.is_symlink()
            or payload_path.is_symlink()
        ):
            raise ValueError(
                "functional-store committed shard may not contain symlinks"
            )
        try:
            if manifest_path.stat().st_size > _MAX_MANIFEST_BYTES:
                raise ValueError(
                    "functional-store shard manifest exceeds its size bound"
                )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(
                f"functional-store shard {index} manifest is malformed"
            ) from exc
        expected_identity = self._mode_identities[index]
        if (
            manifest.get("schema") != SHARD_SCHEMA
            or int(manifest.get("mode_index", -1)) != index
            or manifest.get("numerical_identity_sha256") != self._identity_sha256
            or manifest.get("mode_identity") != expected_identity
            or manifest.get("mode_key")
            != _json_safe(_mode_key_from_identity(expected_identity))
            or manifest.get("payload_filename") != "payload.npz"
        ):
            raise ValueError(f"functional-store shard {index} identity mismatch")
        if not payload_path.is_file():
            raise ValueError(f"functional-store shard {index} payload is missing")
        expected_size = int(manifest.get("serialized_bytes", -1))
        if expected_size <= 0 or payload_path.stat().st_size != expected_size:
            raise ValueError(f"functional-store shard {index} serialized size mismatch")
        digest, size, elapsed = _sha256_file(payload_path)
        self.timing_seconds["restore_hash_seconds"] += elapsed
        if size != expected_size or digest != manifest.get("payload_sha256"):
            raise ValueError(
                f"functional-store shard {index} payload checksum mismatch"
            )
        if size > self._max_shard_working_bytes:
            raise ValueError(
                f"functional-store shard {index} exceeds the configured shard cap"
            )
        self._validate_npz_headers(payload_path, manifest)
        return manifest

    def _validate_npz_headers(self, path: Path, manifest: Mapping[str, Any]) -> None:
        try:
            descriptors = manifest["arrays"]
            if not isinstance(descriptors, Mapping) or set(descriptors) != set(
                _ARRAY_KEYS
            ):
                raise ValueError(
                    "functional-store array descriptors differ from schema"
                )
            descriptor_payload_bytes = 0
            for descriptor in descriptors.values():
                if not isinstance(descriptor, Mapping):
                    raise ValueError(  # noqa: TRY004 - malformed persisted value
                        "functional-store array descriptor is malformed"
                    )
                shape = descriptor.get("shape")
                if not isinstance(shape, list) or any(
                    not isinstance(item, int) or item < 0 for item in shape
                ):
                    raise ValueError("functional-store array shape is malformed")
                itemsize = np.dtype(descriptor["dtype"]).itemsize
                nbytes = math.prod(shape) * itemsize
                if nbytes != int(descriptor["nbytes"]):
                    raise ValueError(
                        "functional-store array descriptor byte count differs"
                    )
                descriptor_payload_bytes += nbytes
            if descriptor_payload_bytes != int(manifest["uncompressed_payload_bytes"]):
                raise ValueError("functional-store uncompressed payload size differs")
            if descriptor_payload_bytes + 16 * 1024 > int(
                manifest["uncompressed_npz_member_bytes_cap"]
            ):
                raise ValueError(
                    "functional-store declared NPZ header allowance is too small"
                )
            if descriptor_payload_bytes + SERIALIZATION_SCRATCH_BOUND_BYTES + len(
                _canonical_json_bytes(manifest)
            ) > int(manifest.get("max_shard_working_bytes", -1)):
                raise ValueError(
                    "functional-store shard cannot fit its declared working bound"
                )
            expected_dtypes = {
                "coupling_rows": self._row_dtype.str,
                "coupling_values": np.dtype(np.complex128).str,
                "projection_rows": self._row_dtype.str,
                "projection_values": np.dtype(np.complex128).str,
                "normalization_h": np.dtype(np.float64).str,
            }
            if any(
                descriptors[key]["dtype"] != dtype
                for key, dtype in expected_dtypes.items()
            ):
                raise ValueError(
                    "functional-store array dtype differs before allocation"
                )
            for key in (
                "coupling_rows",
                "coupling_values",
                "projection_rows",
                "projection_values",
            ):
                if len(descriptors[key]["shape"]) != 1:
                    raise ValueError(
                        "functional-store sparse arrays must be one-dimensional"
                    )
            if (
                descriptors["coupling_rows"]["shape"]
                != descriptors["coupling_values"]["shape"]
            ):
                raise ValueError("functional-store coupling row/value lengths differ")
            if (
                descriptors["projection_rows"]["shape"]
                != descriptors["projection_values"]["shape"]
            ):
                raise ValueError("functional-store projection row/value lengths differ")
            if descriptors["normalization_h"]["shape"] != [1]:
                raise ValueError("functional-store H array must contain one value")
            with ZipFile(path, "r") as archive:
                infos = archive.infolist()
                expected_names = {f"{key}.npy" for key in _ARRAY_KEYS}
                if {info.filename for info in infos} != expected_names or len(
                    infos
                ) != len(expected_names):
                    raise ValueError("functional-store NPZ members differ from schema")
                if any(info.compress_type != ZIP_STORED for info in infos):
                    raise ValueError("functional-store NPZ compression is unsupported")
                if sum(int(info.file_size) for info in infos) > int(
                    manifest["uncompressed_npz_member_bytes_cap"]
                ):
                    raise ValueError(
                        "functional-store NPZ expands beyond its declared payload"
                    )
                for info in infos:
                    key = info.filename[:-4]
                    with archive.open(info, "r") as stream:
                        version = np.lib.format.read_magic(stream)
                        if version == (1, 0):
                            shape, fortran_order, dtype = (
                                np.lib.format.read_array_header_1_0(stream)
                            )
                        elif version == (2, 0):
                            shape, fortran_order, dtype = (
                                np.lib.format.read_array_header_2_0(stream)
                            )
                        else:
                            raise ValueError(
                                "functional-store NPZ header version is unsupported"
                            )
                    descriptor = manifest["arrays"][key]
                    dtype = np.dtype(dtype)
                    shape = [int(item) for item in shape]
                    expected_nbytes = math.prod(shape) * dtype.itemsize
                    if (
                        dtype.hasobject
                        or dtype.str != descriptor["dtype"]
                        or dtype.str != expected_dtypes[key]
                        or shape != descriptor["shape"]
                        or expected_nbytes != int(descriptor["nbytes"])
                        or bool(fortran_order)
                    ):
                        raise ValueError(
                            f"functional-store array header mismatch for {key}"
                        )
        except (BadZipFile, OSError, KeyError, EOFError) as exc:
            raise ValueError("functional-store NPZ container is malformed") from exc

    def restore_prefix(self) -> list[dict[str, Any]]:
        restored: list[dict[str, Any]] = []
        for index in range(self._next_index):
            manifest = self._read_shard_manifest(index)
            _directory, _manifest_path, payload_path = self._shard_paths(index)
            started = time.perf_counter()
            try:
                with np.load(payload_path, allow_pickle=False) as archive:
                    arrays = {key: archive[key] for key in _ARRAY_KEYS}
            except (OSError, ValueError, BadZipFile) as exc:
                raise ValueError(
                    f"functional-store shard {index} payload cannot be read"
                ) from exc
            self.timing_seconds["restore_read_seconds"] += time.perf_counter() - started
            for key, array in arrays.items():
                descriptor = manifest["arrays"][key]
                if (
                    array.dtype.str != descriptor["dtype"]
                    or list(array.shape) != descriptor["shape"]
                    or int(array.nbytes) != int(descriptor["nbytes"])
                    or array.dtype.hasobject
                ):
                    raise ValueError(
                        f"functional-store shard {index} loaded array differs"
                    )
            functional = {
                "mode_key": tuple(
                    _mode_key_from_identity(self._mode_identities[index])
                ),
                "mode_identity": dict(self._raw_mode_identities[index]),
                "coupling_rows": arrays["coupling_rows"],
                "coupling_values": arrays["coupling_values"],
                "projection_rows": arrays["projection_rows"],
                "projection_values": arrays["projection_values"],
                "normalization_h": float(arrays["normalization_h"][0]),
            }
            self._validate_functional(functional, index)
            for array in arrays.values():
                array.flags.writeable = False
            restored.append(functional)
        return restored

    def _compatible_parent_identity(
        self, compatibility: Mapping[str, Any]
    ) -> tuple[Path, dict[str, Any], str]:
        compatibility = _validate_n0_parent_compatibility_contract(compatibility)
        if "operator_selection" not in self._identity:
            raise ValueError("parent-store import is restricted to explicit N0 identities")
        degree = str(int(self._identity["degree"]))
        binding = compatibility["stores"][degree]
        root = Path(binding["root"])
        if not root.is_dir() or root.is_symlink():
            raise ValueError("N0 parent functional-store root is unavailable")
        identity_path = root / "identity.json"
        if identity_path.is_symlink() or not identity_path.is_file():
            raise ValueError("N0 parent functional-store identity is unavailable")
        before = identity_path.stat()
        if before.st_size > _MAX_MANIFEST_BYTES:
            raise ValueError("N0 parent functional-store identity exceeds its bound")
        raw = identity_path.read_bytes()
        after = identity_path.stat()
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise ValueError("N0 parent identity changed while it was read")
        try:
            document = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("N0 parent functional-store identity is malformed") from exc
        if (
            not isinstance(document, Mapping)
            or set(document)
            != {
                "schema",
                "numerical_identity",
                "numerical_identity_sha256",
                "mode_count",
            }
            or raw != _canonical_json_bytes(document)
            or document.get("schema") != STORE_SCHEMA
        ):
            raise ValueError("N0 parent functional-store identity schema differs")
        parent_identity = _validate_identity(document["numerical_identity"])
        parent_identity_sha = hashlib.sha256(
            _canonical_json_bytes(parent_identity)
        ).hexdigest()
        if (
            parent_identity_sha != binding["numerical_identity_sha256"]
            or document.get("numerical_identity_sha256") != parent_identity_sha
            or int(document.get("mode_count", -1))
            != int(compatibility["parent_mode_count"])
        ):
            raise ValueError("N0 parent numerical identity hash/count differs")
        for field in (
            "source_sha256",
            "resolved_config_sha256",
            "input_sha256",
            "physical_model_sha256",
        ):
            if parent_identity.get(field) != compatibility[f"parent_{field}"]:
                raise ValueError(f"N0 parent {field} differs from the pinned mapping")
        for field in (
            "schema",
            "physical_model_sha256",
            "backend",
            "degree",
            "mesh",
            "dof_mpc",
            "quadrature",
            "abi",
        ):
            if parent_identity.get(field) != self._identity.get(field):
                raise ValueError(f"N0 parent and active {field} identities differ")
        parent_modes = parent_identity.get("modes", {})
        active_selection = self._identity["operator_selection"]
        if (
            int(parent_modes.get("count", -1))
            != int(compatibility["parent_mode_count"])
            or parent_modes.get("ordered_manifest_sha256")
            != compatibility["parent_mode_sha256"]
            or active_selection.get("parent_mode_count")
            != int(parent_modes.get("count", -1))
            or active_selection.get("parent_mode_sha256")
            != parent_modes.get("ordered_manifest_sha256")
        ):
            raise ValueError("N0 parent mode identity differs from the reviewed mapping")
        old_implementation = parent_identity["implementation_file_sha256"]
        active_implementation = self._identity["implementation_file_sha256"]
        if set(old_implementation) != set(active_implementation):
            raise ValueError("N0 parent implementation identity key set changed")
        changed_files = {
            name
            for name, old_digest in old_implementation.items()
            if active_implementation[name] != old_digest
        }
        if not changed_files.issubset(N0_PARENT_COMPATIBLE_IMPLEMENTATION_FILES):
            raise ValueError("N0 parent implementation changes exceed the allowlist")
        if not Path(root / "writer.lock").is_file():
            raise ValueError("N0 parent store writer-lock provenance is missing")
        return root, parent_identity, parent_identity_sha

    def _read_compatible_parent_functional(
        self,
        parent_root: Path,
        parent_identity_sha256: str,
        parent_index: int,
        parent_mode_identity: Mapping[str, Any],
        active_index: int | None,
    ) -> dict[str, Any] | None:
        directory = parent_root / f"functional_{int(parent_index):08d}"
        manifest_path = directory / "manifest.json"
        payload_path = directory / "payload.npz"
        if any(path.is_symlink() for path in (directory, manifest_path, payload_path)):
            raise ValueError("N0 parent functional shard may not contain symlinks")
        present = tuple(path.exists() for path in (directory, manifest_path, payload_path))
        if not any(present):
            return None
        if not all(present) or not directory.is_dir() or not manifest_path.is_file() or not payload_path.is_file():
            raise ValueError(f"N0 parent functional shard {parent_index} is incomplete")
        manifest_before = manifest_path.stat()
        if manifest_before.st_size > _MAX_MANIFEST_BYTES:
            raise ValueError("N0 parent shard manifest exceeds its bound")
        manifest_started = time.perf_counter()
        raw_manifest = manifest_path.read_bytes()
        manifest_after = manifest_path.stat()
        if (manifest_before.st_dev, manifest_before.st_ino, manifest_before.st_size, manifest_before.st_mtime_ns) != (
            manifest_after.st_dev,
            manifest_after.st_ino,
            manifest_after.st_size,
            manifest_after.st_mtime_ns,
        ):
            raise ValueError("N0 parent shard manifest changed while it was read")
        try:
            manifest = json.loads(raw_manifest.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("N0 parent shard manifest is malformed") from exc
        self._parent_import_facts["timing_seconds"][
            "parent_manifest_read_seconds"
        ] += time.perf_counter() - manifest_started
        parent_mode_identity = _json_safe(dict(parent_mode_identity))
        if (
            not isinstance(manifest, Mapping)
            or raw_manifest != _canonical_json_bytes(manifest)
            or manifest.get("schema") != SHARD_SCHEMA
            or int(manifest.get("mode_index", -1)) != int(parent_index)
            or manifest.get("numerical_identity_sha256") != parent_identity_sha256
            or manifest.get("mode_identity") != parent_mode_identity
            or manifest.get("mode_key")
            != _json_safe(_mode_key_from_identity(parent_mode_identity))
            or manifest.get("payload_filename") != "payload.npz"
        ):
            raise ValueError(f"N0 parent shard {parent_index} mode identity differs")
        payload_before = payload_path.stat()
        expected_size = int(manifest.get("serialized_bytes", -1))
        if expected_size <= 0 or payload_before.st_size != expected_size:
            raise ValueError("N0 parent payload size differs from its manifest")
        payload_sha, payload_size, hash_seconds = _sha256_file(payload_path)
        self._parent_import_facts["timing_seconds"][
            "parent_payload_hash_seconds"
        ] += float(hash_seconds)
        payload_after = payload_path.stat()
        if (payload_before.st_dev, payload_before.st_ino, payload_before.st_size, payload_before.st_mtime_ns) != (
            payload_after.st_dev,
            payload_after.st_ino,
            payload_after.st_size,
            payload_after.st_mtime_ns,
        ):
            raise ValueError("N0 parent payload changed while it was hashed")
        if (
            payload_size != expected_size
            or payload_sha != manifest.get("payload_sha256")
            or payload_size > self._max_shard_working_bytes
        ):
            raise ValueError("N0 parent payload hash or size differs")
        self._validate_npz_headers(payload_path, manifest)
        payload_read_started = time.perf_counter()
        try:
            with np.load(payload_path, allow_pickle=False) as archive:
                arrays = {key: archive[key] for key in _ARRAY_KEYS}
        except (OSError, ValueError, BadZipFile) as exc:
            raise ValueError("N0 parent payload cannot be decoded") from exc
        self._parent_import_facts["timing_seconds"][
            "parent_payload_read_seconds"
        ] += time.perf_counter() - payload_read_started
        for key, array in arrays.items():
            descriptor = manifest["arrays"][key]
            if (
                array.dtype.str != descriptor["dtype"]
                or list(array.shape) != descriptor["shape"]
                or int(array.nbytes) != int(descriptor["nbytes"])
                or array.dtype.hasobject
            ):
                raise ValueError(f"N0 parent payload array {key} differs")
        if active_index is None:
            functional_identity = dict(parent_mode_identity)
            functional_index = int(parent_index)
        else:
            active_identity = self._mode_identities[int(active_index)]
            if not _n0_remapped_mode_identity_matches(
                parent_mode_identity, active_identity, int(active_index)
            ):
                raise ValueError("N0 parent and active mode physics differ")
            functional_identity = self._raw_mode_identities[int(active_index)]
            functional_index = int(active_index)
        functional = {
            "mode_key": _mode_key_from_identity(functional_identity),
            "mode_identity": dict(functional_identity),
            "coupling_rows": arrays["coupling_rows"],
            "coupling_values": arrays["coupling_values"],
            "projection_rows": arrays["projection_rows"],
            "projection_values": arrays["projection_values"],
            "normalization_h": float(arrays["normalization_h"][0]),
        }
        self._validate_functional(
            functional,
            functional_index,
            expected_mode_identity=(
                parent_mode_identity if active_index is None else None
            ),
        )
        for array in arrays.values():
            array.flags.writeable = False
        return functional

    def prepare_compatible_parent_import(
        self,
        compatibility: Mapping[str, Any],
        parent_mode_identities: Sequence[Mapping[str, Any]],
        selected_parent_indices: Sequence[int],
    ) -> None:
        """Bind optional parent reuse after validating active N0 mode identity."""

        parent_rows = tuple(_json_safe(dict(row)) for row in parent_mode_identities)
        selected = tuple(int(index) for index in selected_parent_indices)
        if (
            len(parent_rows) != N0_PARENT_MODE_COUNT
            or len(selected) != len(self._mode_identities)
            or any(index < 0 or index >= len(parent_rows) for index in selected)
            or any(right <= left for left, right in pairwise(selected))
        ):
            raise ValueError("N0 parent import mode mapping is invalid")
        selection = self._identity.get("operator_selection")
        index_sha = hashlib.sha256(_canonical_json_bytes(list(selected))).hexdigest()
        if (
            selection is None
            or index_sha != selection.get("selected_parent_indices_sha256")
            or selection.get("parent_mode_sha256") != N0_PARENT_MODE_SHA256
            or len(selected) != len(self._mode_identities)
        ):
            raise ValueError("N0 parent import selection identity differs")
        if any(
            not _n0_remapped_mode_identity_matches(
                parent_rows[parent_index], self._raw_mode_identities[active_index], active_index
            )
            for active_index, parent_index in enumerate(selected)
        ):
            raise ValueError("N0 selected parent rows differ from active mode identity")

        self._parent_import_facts.update(
            configured=True,
            status="PARENT_CHECK_PENDING",
            selected_mode_count=len(selected),
        )
        try:
            parent_root, parent_identity, parent_identity_sha = (
                self._compatible_parent_identity(compatibility)
            )
            if (
                int(parent_identity["modes"]["count"]) != len(parent_rows)
                or parent_identity["modes"]["ordered_manifest_sha256"]
                != N0_PARENT_MODE_SHA256
            ):
                raise ValueError(
                    "N0 live parent mode rows differ from the pinned parent manifest"
                )
        except (OSError, ValueError, TypeError, KeyError) as exc:
            self._parent_import_facts["status"] = "PARENT_NOT_REUSABLE"
            self._record_parent_import_fallback(
                None, None, "parent_identity_incompatible", exc
            )
            self._parent_import_state = None
            return
        self._parent_import_state = {
            "root": parent_root,
            "identity_sha256": parent_identity_sha,
            "parent_rows": parent_rows,
            "selected_parent_indices": selected,
        }
        self._parent_import_facts["status"] = "PARENT_COMPATIBLE"

    def disable_parent_import(self, reason: str) -> None:
        """Record that optional parent reuse was intentionally unavailable."""

        self._parent_import_state = None
        self._parent_import_facts.update(
            configured=False,
            status="PARENT_REUSE_NOT_CONFIGURED",
            disabled_reason=str(reason)[:240],
        )

    def n0_parent_store_inventory_facts(self) -> dict[str, Any]:
        """Inspect only parent shard names; never read payloads or hashes."""

        state = self._parent_import_state
        if state is None:
            return {
                "status": "PARENT_NOT_REUSABLE",
                "expected_mode_count": N0_PARENT_MODE_COUNT,
                "committed_shard_count": None,
                "contiguous_prefix_count": None,
                "complete": False,
            }
        root = Path(state["root"])
        indices: set[int] = set()
        for entry in root.iterdir():
            match = _SHARD_NAME.fullmatch(entry.name)
            if match is None:
                continue
            if entry.is_symlink() or not entry.is_dir():
                return {
                    "status": "PARENT_SHARD_INVENTORY_INVALID",
                    "expected_mode_count": len(state["parent_rows"]),
                    "committed_shard_count": len(indices),
                    "contiguous_prefix_count": None,
                    "complete": False,
                    "reason": "shard_entry_is_not_a_regular_directory",
                }
            index = int(match.group(1))
            if index >= len(state["parent_rows"]):
                return {
                    "status": "PARENT_SHARD_INVENTORY_INVALID",
                    "expected_mode_count": len(state["parent_rows"]),
                    "committed_shard_count": len(indices) + 1,
                    "contiguous_prefix_count": None,
                    "complete": False,
                    "reason": "shard_index_exceeds_parent_inventory",
                }
            indices.add(index)
        prefix = 0
        while prefix in indices:
            prefix += 1
        expected = len(state["parent_rows"])
        complete = prefix == expected and len(indices) == expected
        facts = {
            "status": "PARENT_STORE_COMPLETE" if complete else "PARENT_STORE_INCOMPLETE",
            "expected_mode_count": expected,
            "committed_shard_count": len(indices),
            "contiguous_prefix_count": prefix,
            "first_missing_mode_index": None if complete else prefix,
            "complete": complete,
            "payloads_opened": 0,
            "payload_hashes_computed": 0,
        }
        self._parent_import_facts["endpoint_inventory"] = dict(facts)
        return facts

    def record_n0_parent_fallback_assembly_seconds(self, seconds: float) -> None:
        value = float(seconds)
        if not np.isfinite(value) or value < 0.0:
            raise ValueError("parent fallback FE assembly time must be finite and nonnegative")
        self._parent_import_facts["timing_seconds"][
            "parent_fallback_fe_assembly_seconds"
        ] += value

    def record_active_store_commit_seconds(self, seconds: float) -> None:
        value = float(seconds)
        if not np.isfinite(value) or value < 0.0:
            raise ValueError("active store commit time must be finite and nonnegative")
        self.timing_seconds["active_store_commit_seconds"] += value

    def read_n0_parent_functional_for_endpoint(
        self, parent_index: int
    ) -> dict[str, Any] | None:
        """Read and validate one full-parent shard for the one endpoint check."""

        state = self._parent_import_state
        if state is None:
            return None
        parent_index = int(parent_index)
        rows = state["parent_rows"]
        if parent_index < 0 or parent_index >= len(rows):
            raise IndexError("N0 endpoint parent index is outside the bound inventory")
        return self._read_compatible_parent_functional(
            state["root"],
            state["identity_sha256"],
            parent_index,
            rows[parent_index],
            None,
        )

    def _record_parent_import_fallback(
        self,
        active_index: int | None,
        parent_index: int | None,
        category: str,
        exc: BaseException | None = None,
    ) -> None:
        self._parent_import_facts["fallback_count"] += 1
        record = {
            "active_index": active_index,
            "parent_index": parent_index,
            "category": str(category),
        }
        if exc is not None:
            record["reason"] = f"{type(exc).__name__}: {exc}"[:240]
        reasons = self._parent_import_facts["fallback_reasons"]
        if len(reasons) < 16:
            reasons.append(record)
        else:
            self._parent_import_facts["omitted_fallback_reason_count"] += 1
        if self._parent_import_facts["status"] == "PARENT_COMPATIBLE":
            self._parent_import_facts["status"] = "PARTIAL_PARENT_REUSE"

    def try_import_compatible_parent_functional(
        self, active_index: int
    ) -> dict[str, Any] | None:
        """Read one optional parent shard; caller assembles when reuse is unavailable.

        New-store validation and commit failures are intentionally outside the
        parent-read fallback boundary and remain fatal.
        """

        active_index = int(active_index)
        if active_index != self._next_index:
            raise ValueError("N0 parent import must follow the active store index")
        self._parent_import_facts["attempted_count"] += 1
        state = self._parent_import_state
        if state is None:
            self._record_parent_import_fallback(
                active_index, None, "parent_reuse_unavailable"
            )
            return None
        selected = state["selected_parent_indices"]
        if active_index < 0 or active_index >= len(selected):
            raise ValueError("N0 active import index is outside the selected modes")
        parent_index = selected[active_index]
        try:
            functional = self._read_compatible_parent_functional(
                state["root"],
                state["identity_sha256"],
                parent_index,
                state["parent_rows"][parent_index],
                active_index,
            )
        except (OSError, ValueError, TypeError, KeyError, EOFError, BadZipFile) as exc:
            self._record_parent_import_fallback(
                active_index, parent_index, "selected_parent_payload_invalid", exc
            )
            return None
        if functional is None:
            self._record_parent_import_fallback(
                active_index, parent_index, "selected_parent_payload_missing"
            )
            return None
        # This writes only the new active store. A write/identity/disk failure
        # here must not be mistaken for an optional parent-cache miss.
        commit_started = time.perf_counter()
        self.commit(functional, mode_index=active_index)
        commit_elapsed = time.perf_counter() - commit_started
        self.record_active_store_commit_seconds(commit_elapsed)
        self._parent_import_facts["timing_seconds"][
            "parent_active_store_commit_seconds"
        ] += commit_elapsed
        self._parent_import_facts["imported_count"] += 1
        if self._parent_import_facts["fallback_count"]:
            self._parent_import_facts["status"] = "PARTIAL_PARENT_REUSE"
        else:
            self._parent_import_facts["status"] = "PARENT_REUSE_ACTIVE"
        return functional

    def _validate_functional(
        self,
        functional: Any,
        index: int,
        *,
        expected_mode_identity: Mapping[str, Any] | None = None,
    ) -> dict[str, np.ndarray]:
        def field(name: str) -> Any:
            if isinstance(functional, Mapping):
                try:
                    return functional[name]
                except KeyError as exc:
                    raise ValueError(
                        f"functional shard is missing field {name!r}"
                    ) from exc
            try:
                return getattr(functional, name)
            except AttributeError as exc:
                raise ValueError(f"functional shard is missing field {name!r}") from exc

        expected_identity = (
            self._mode_identities[index]
            if expected_mode_identity is None
            else _json_safe(dict(expected_mode_identity))
        )
        identity = _json_safe(dict(field("mode_identity")))
        key = tuple(field("mode_key"))
        if (
            identity != expected_identity
            or key != _mode_key_from_identity(expected_identity)
            or int(identity["mode_index"]) != index
        ):
            raise ValueError(
                "functional mode key/index identity differs from ordered manifest"
            )
        h = float(field("normalization_h"))
        expected_h = _expected_float(expected_identity["projection_denominator"])
        if not np.isfinite(h) or h <= 0.0 or h.hex() != expected_h.hex():
            raise ValueError("functional H is invalid or differs from mode identity")
        arrays = {key: np.asarray(field(key)) for key in _ARRAY_KEYS[:-1]}
        for prefix in ("coupling", "projection"):
            rows = arrays[f"{prefix}_rows"]
            values = arrays[f"{prefix}_values"]
            if (
                rows.ndim != 1
                or rows.dtype != self._row_dtype
                or not rows.flags.c_contiguous
                or values.ndim != 1
                or values.dtype != np.dtype(np.complex128)
                or not values.flags.c_contiguous
                or rows.shape != values.shape
            ):
                raise ValueError(
                    f"functional {prefix} sparse arrays have invalid dtype/layout"
                )
            if rows.size and (
                int(rows[0]) < self._ownership_range[0]
                or int(rows[-1]) >= self._ownership_range[1]
                or (rows.size > 1 and np.any(rows[1:] <= rows[:-1]))
            ):
                raise ValueError(
                    f"functional {prefix} rows must be owned, ordered, unique"
                )
            if (
                rows.size
                and self._slave_rows.size
                and np.intersect1d(rows, self._slave_rows, assume_unique=True).size
            ):
                raise ValueError(f"functional {prefix} rows intersect MPC slave rows")
            if not np.isfinite(values).all():
                raise ValueError(
                    f"functional {prefix} values contain non-finite entries"
                )
        return arrays

    def _preflight_write(
        self, arrays: Mapping[str, np.ndarray], manifest_size: int
    ) -> tuple[int, int]:
        array_bytes = sum(int(array.nbytes) for array in arrays.values())
        header_allowance = 16 * 1024
        disk_bound = array_bytes + header_allowance + int(manifest_size)
        working_bound = (
            array_bytes
            + SERIALIZATION_SCRATCH_BOUND_BYTES
            + int(manifest_size)
            + 64 * 1024
        )
        if working_bound > self._max_shard_working_bytes:
            raise MemoryError(
                "functional shard plus serialization scratch exceeds working cap"
            )
        if (
            self._committed_disk_bytes
            + self._incomplete_temporary_bytes
            + disk_bound
            > self._max_total_disk_bytes
        ):
            raise OSError("functional shards exceed the configured total disk budget")
        free_bytes = int(shutil.disk_usage(self.root).free)
        if free_bytes < disk_bound + self._disk_reserve_bytes:
            raise OSError("insufficient disk space for a complete functional shard")
        return disk_bound, working_bound

    def commit(self, functional: Any, *, mode_index: int) -> dict[str, Any]:
        index = int(mode_index)
        if index != self._next_index or index >= len(self._mode_identities):
            raise ValueError(
                "functional shards must commit as one contiguous mode prefix"
            )

        def field(name: str) -> Any:
            if isinstance(functional, Mapping):
                try:
                    return functional[name]
                except KeyError as exc:
                    raise ValueError(
                        f"functional shard is missing field {name!r}"
                    ) from exc
            try:
                return getattr(functional, name)
            except AttributeError as exc:
                raise ValueError(
                    f"functional shard is missing field {name!r}"
                ) from exc

        arrays = self._validate_functional(functional, index)
        npz_arrays = {
            **arrays,
            "normalization_h": np.asarray(
                [float(field("normalization_h"))], dtype=np.float64
            ),
        }
        descriptors = {
            key: _array_descriptor(value) for key, value in npz_arrays.items()
        }
        uncompressed_bytes = sum(int(value.nbytes) for value in npz_arrays.values())
        manifest = {
            "schema": SHARD_SCHEMA,
            "mode_index": index,
            "mode_key": _json_safe(tuple(field("mode_key"))),
            "mode_identity": _json_safe(dict(field("mode_identity"))),
            "numerical_identity_sha256": self._identity_sha256,
            "producer_provenance": self._producer_provenance,
            "payload_filename": "payload.npz",
            "arrays": descriptors,
            "max_shard_working_bytes": self._max_shard_working_bytes,
            "uncompressed_payload_bytes": int(uncompressed_bytes),
            "uncompressed_npz_member_bytes_cap": int(uncompressed_bytes + 16 * 1024),
        }
        manifest_bytes = _canonical_json_bytes(manifest)
        _disk_bound, _working_bound = self._preflight_write(
            npz_arrays, len(manifest_bytes)
        )
        temporary = self.root / f".tmp_functional_{index:08d}_{uuid4().hex}"
        final_dir, _manifest_path, _payload_path = self._shard_paths(index)
        if final_dir.exists():
            raise FileExistsError(
                "functional-store refuses to replace a committed shard"
            )
        temporary.mkdir()
        payload_path = temporary / "payload.npz"
        started = time.perf_counter()
        with payload_path.open("xb") as stream:
            np.savez(stream, **npz_arrays)
            stream.flush()
            fsync_started = time.perf_counter()
            os.fsync(stream.fileno())
            self.timing_seconds["payload_fsync_seconds"] += (
                time.perf_counter() - fsync_started
            )
        self.timing_seconds["payload_write_seconds"] += time.perf_counter() - started
        digest, serialized_bytes, hash_seconds = _sha256_file(payload_path)
        self.timing_seconds["payload_hash_seconds"] += hash_seconds
        manifest["payload_sha256"] = digest
        manifest["serialized_bytes"] = serialized_bytes
        manifest_bytes = _canonical_json_bytes(manifest)
        if (
            serialized_bytes + len(manifest_bytes) + SERIALIZATION_SCRATCH_BOUND_BYTES
            > self._max_shard_working_bytes
        ):
            raise MemoryError(
                "serialized functional shard exceeds the configured working cap"
            )
        if (
            self._committed_disk_bytes + serialized_bytes + len(manifest_bytes)
            > self._max_total_disk_bytes
        ):
            raise OSError("serialized functional shards exceed the total disk budget")
        with (temporary / "manifest.json").open("xb") as stream:
            stream.write(manifest_bytes)
            stream.flush()
            fsync_started = time.perf_counter()
            os.fsync(stream.fileno())
            self.timing_seconds["manifest_fsync_seconds"] += (
                time.perf_counter() - fsync_started
            )
        fsync_started = time.perf_counter()
        _fsync_directory(temporary)
        self.timing_seconds["directory_fsync_seconds"] += (
            time.perf_counter() - fsync_started
        )
        if self._test_fault_hook is not None:
            self._test_fault_hook("before_rename")
        os.rename(temporary, final_dir)
        fsync_started = time.perf_counter()
        _fsync_directory(self.root)
        self.timing_seconds["directory_fsync_seconds"] += (
            time.perf_counter() - fsync_started
        )
        # A successful directory rename followed by parent fsync is the commit
        # point. A crash before it leaves only an ignored .tmp shard.
        if self._test_fault_hook is not None:
            self._test_fault_hook("after_commit")
        self._next_index += 1
        self._committed_disk_bytes += serialized_bytes + len(manifest_bytes)
        return {
            "mode_index": index,
            "serialized_bytes": serialized_bytes,
            "payload_sha256": digest,
            "identity_sha256": self._identity_sha256,
        }

    def close(self) -> None:
        stream, self._lock_stream = self._lock_stream, None
        if stream is not None:
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
            finally:
                stream.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        self.close()


__all__ = (
    "SERIALIZATION_SCRATCH_BOUND_BYTES",
    "PortFunctionalShardStore",
    "build_surface_functional_numerical_identity",
)
