"""Pure/fake checks for prepared trace plans and atomic DtN shards."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import copy
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import cffi
import numpy as np
import pytest

import src.solvers.fullspace_dtn_functional_store as functional_store_module
from src.io.native_capacity_profile import (
    V6_0P7_P3_HP_OPTIN_PROFILES,
    V6_NATIVE_PROFILES,
    native_profile_facts,
)
from src.solvers.dtn_port_3d import (
    _SurfaceLegendreMomentAssembler,
    _SurfaceLegendreMomentContext,
)
from src.solvers.fullspace_dtn_action import (
    FULLSPACE_DTN_MANIFEST_SCHEMA,
    FULLSPACE_DTN_PROFILE,
    _dtn_component_phase_key,
    _remaining_dtn_component_phase_uses,
)
from src.solvers.fullspace_dtn_action import (
    _canonical_json_bytes as _mode_json_bytes,
)
from src.solvers.fullspace_dtn_functional_store import (
    P3_NUMERICAL_IDENTITY_SCHEMA,
    P6_CONTEXT_PROVIDER_SCHEMA,
    P6_NUMERICAL_IDENTITY_SCHEMA,
    P6_SURFACE_PROVIDER_SCHEMA,
    PortFunctionalShardStore,
    _surface_form_identities,
    build_surface_functional_numerical_identity,
    _validate_p6_context_descriptor,
)
from src.solvers.fullspace_surface_legendre import (
    SURFACE_COMPONENT_PAIR_BACKEND,
    SURFACE_WEIGHTED_MOMENT_CONTRACTION,
    PreparedFaceTraceContraction,
    assemble_face_from_weighted_moments,
    validate_prepared_trace_contraction,
)

SOURCE_SHA = "a" * 40
INPUT_SHA = "b" * 64
PHYSICAL_SHA = "c" * 64


def _fake_ffcx_module(path: Path, *, name="libffcx_forms_0123456789abcdef"):
    module = ModuleType(name)
    module.__file__ = str(path)
    return module


def _fake_compiled_form(
    side: str,
    component: int,
    tag: int,
    *,
    module,
    code=None,
    ufcx_signature=None,
):
    return SimpleNamespace(
        module=module,
        code=(
            f"compiled q160 exterior facet {side} component {component} tag {tag}"
            if code is None
            else code
        ),
        ufcx_form=SimpleNamespace(
            signature=(
                f"ufcx-{side}-{component}-{tag}"
                if ufcx_signature is None
                else ufcx_signature
            ),
            form_integral_offsets=[0, 0, 1, 1, 1, 1],
            form_integral_ids=[tag],
        ),
        integral_types=(SimpleNamespace(name="exterior_facet"),),
        rank=1,
        dtype=np.dtype(np.complex128),
    )


def _fake_cffi_signature_form(
    prior_assembler,
    signature_bytes: bytes | None,
    *,
    code=None,
    signature_ctype="char",
):
    ffi = cffi.FFI()
    ffi.cdef(
        "struct char_signature_holder { const char *signature; };"
        "struct uchar_signature_holder { const unsigned char *signature; };"
    )
    module = prior_assembler.form.module
    module.ffi = ffi
    if signature_ctype == "char":
        owner = ffi.new("struct char_signature_holder *")
        storage = None if signature_bytes is None else ffi.new("char[]", signature_bytes)
        owner.signature = ffi.NULL if storage is None else storage
    elif signature_ctype == "unsigned char":
        owner = ffi.new("struct uchar_signature_holder *")
        storage = (
            None
            if signature_bytes is None
            else ffi.new("unsigned char[]", signature_bytes)
        )
        owner.signature = ffi.NULL if storage is None else storage
    else:
        raise AssertionError(f"unexpected CFFI fixture type {signature_ctype}")
    form = _fake_compiled_form(
        prior_assembler.side,
        prior_assembler.component,
        prior_assembler.tag,
        module=module,
        code=prior_assembler.form.code if code is None else code,
        ufcx_signature=owner.signature,
    )
    form._signature_keepalive = (owner, storage)
    return form


def _fake_surface_assembler(space, mesh_data, side, component, tag, form):
    return SimpleNamespace(
        function_space=space,
        mesh_data=mesh_data,
        side=side,
        component=component,
        tag=tag,
        form=form,
    )


def _fake_surface_form_maps(
    tmp_path,
    *,
    selected_has_forms=True,
    module=None,
    module_bytes=b"fake loaded FFCx extension module",
):
    module_path = tmp_path / "cache" / "libffcx_forms_0123456789abcdef.so"
    module_path.parent.mkdir(parents=True, exist_ok=True)
    if not module_path.exists():
        module_path.write_bytes(module_bytes)
    if module is None:
        module = _fake_ffcx_module(module_path)
    space = object()
    mesh_data = object()
    selected = {}
    compiled = {}
    for side, tag in (("bottom", 17), ("top", 29)):
        for component in (0, 1):
            form = (
                _fake_compiled_form(
                    side, component, tag, module=module
                )
                if selected_has_forms
                else None
            )
            selected[(side, component)] = _fake_surface_assembler(
                space, mesh_data, side, component, tag, form
            )
            compiled[(side, component)] = _fake_surface_assembler(
                space,
                mesh_data,
                side,
                component,
                tag,
                _fake_compiled_form(side, component, tag, module=module),
            )
    return selected, compiled


def test_functional_store_binds_both_components_from_public_compiled_form_api(
    tmp_path,
):
    selected, compiled = _fake_surface_form_maps(
        tmp_path, selected_has_forms=False
    )
    identities = _surface_form_identities(selected, compiled)
    assert [item["component"] for item in identities["bottom"]] == [0, 1]
    assert [item["component"] for item in identities["top"]] == [0, 1]
    assert all(
        item["compiled_module_signature"] == "libffcx_forms_0123456789abcdef"
        and len(item["compiled_module_file_sha256"]) == 64
        and item["ufcx_form_signature"].startswith("ufcx-")
        for side_items in identities.values()
        for item in side_items
    )
    assert all(
        item["compiled_form_api"]
        == "dolfinx.fem.Form.module+ufcx_form.signature+integral_types+rank+dtype"
        and item["integral_types"] == ["exterior_facet"]
        for side_items in identities.values()
        for item in side_items
    )
    assert all(
        "code" not in item
        and not any("path" in key or "mtime" in key or "inode" in key for key in item)
        for side_items in identities.values()
        for item in side_items
    )
    assert all(not hasattr(assembler.form, "integrals") for assembler in compiled.values())


def test_functional_store_cold_and_ffcx_cache_hit_forms_share_identity(tmp_path):
    module_dir = tmp_path / "cache-a"
    module_dir.mkdir()
    module_path = module_dir / "libffcx_forms_0123456789abcdef.so"
    module_path.write_bytes(b"same loaded extension bytes")
    module = _fake_ffcx_module(module_path)
    selected, cold = _fake_surface_form_maps(
        tmp_path / "cold", selected_has_forms=False, module=module
    )
    cold_identity = _surface_form_identities(selected, cold)

    hot = dict(cold)
    for key, prior in cold.items():
        hot[key] = _fake_surface_assembler(
            prior.function_space,
            prior.mesh_data,
            prior.side,
            prior.component,
            prior.tag,
            _fake_compiled_form(
                prior.side,
                prior.component,
                prior.tag,
                module=module,
                code=(None, None),
            ),
        )
    assert _surface_form_identities(selected, hot) == cold_identity

    byte_signatures = dict(cold)
    for key, prior in cold.items():
        byte_signatures[key] = _fake_surface_assembler(
            prior.function_space,
            prior.mesh_data,
            prior.side,
            prior.component,
            prior.tag,
            _fake_compiled_form(
                prior.side,
                prior.component,
                prior.tag,
                module=module,
                code=(None, None),
                ufcx_signature=prior.form.ufcx_form.signature.encode("utf-8"),
            ),
        )
    assert _surface_form_identities(selected, byte_signatures) == cold_identity

    source_changed = dict(cold)
    prior = source_changed[("bottom", 1)]
    source_changed[("bottom", 1)] = _fake_surface_assembler(
        prior.function_space,
        prior.mesh_data,
        prior.side,
        prior.component,
        prior.tag,
        _fake_compiled_form(
            prior.side,
            prior.component,
            prior.tag,
            module=module,
            code="different diagnostic-only generated source",
        ),
    )
    assert _surface_form_identities(selected, source_changed) == cold_identity


def test_functional_store_reads_real_cffi_char_pointer_and_preserves_cold_cache_identity(
    tmp_path,
):
    selected, compiled = _fake_surface_form_maps(
        tmp_path, selected_has_forms=False
    )
    key = ("bottom", 0)
    prior = compiled[key]
    expected_signature = prior.form.ufcx_form.signature
    cold_form = _fake_cffi_signature_form(
        prior, expected_signature.encode("utf-8")
    )
    assert cffi.FFI().typeof(cold_form.ufcx_form.signature).kind == "pointer"
    assert cffi.FFI().typeof(cold_form.ufcx_form.signature).item.cname == "char"
    cold_forms = dict(compiled)
    cold_forms[key] = _fake_surface_assembler(
        prior.function_space,
        prior.mesh_data,
        prior.side,
        prior.component,
        prior.tag,
        cold_form,
    )
    cold_identity = _surface_form_identities(selected, cold_forms)

    hot_form = _fake_compiled_form(
        prior.side,
        prior.component,
        prior.tag,
        module=cold_form.module,
        code=(None, None),
        ufcx_signature=cold_form.ufcx_form.signature,
    )
    hot_form._signature_keepalive = cold_form._signature_keepalive
    hot_forms = dict(compiled)
    hot_forms[key] = _fake_surface_assembler(
        prior.function_space,
        prior.mesh_data,
        prior.side,
        prior.component,
        prior.tag,
        hot_form,
    )
    assert _surface_form_identities(selected, hot_forms) == cold_identity

    python_signature_forms = dict(compiled)
    python_signature_forms[key] = _fake_surface_assembler(
        prior.function_space,
        prior.mesh_data,
        prior.side,
        prior.component,
        prior.tag,
        _fake_compiled_form(
            prior.side,
            prior.component,
            prior.tag,
            module=cold_form.module,
            code=(None, None),
            ufcx_signature=expected_signature,
        ),
    )
    assert _surface_form_identities(
        selected, python_signature_forms
    ) == cold_identity


@pytest.mark.parametrize(
    ("signature_bytes", "signature_ctype", "message"),
    [
        (None, "char", "UFCx Form signature is NULL"),
        (b"valid-but-wrong-pointer-type", "unsigned char", r"not CFFI char\*"),
        (
            b"x" * (functional_store_module._MAX_UFCX_FORM_SIGNATURE_BYTES + 1),
            "char",
            "signature exceeds size limit",
        ),
        (b"invalid-utf8-\xff", "char", "not valid UTF-8"),
    ],
)
def test_functional_store_rejects_bad_cffi_signatures_with_bounded_form_diagnostic(
    tmp_path, signature_bytes, signature_ctype, message
):
    selected, compiled = _fake_surface_form_maps(
        tmp_path, selected_has_forms=False
    )
    key = ("top", 1)
    prior = compiled[key]
    invalid_form = _fake_cffi_signature_form(
        prior,
        signature_bytes,
        code=(None, None),
        signature_ctype=signature_ctype,
    )
    invalid_forms = dict(compiled)
    invalid_forms[key] = _fake_surface_assembler(
        prior.function_space,
        prior.mesh_data,
        prior.side,
        prior.component,
        prior.tag,
        invalid_form,
    )
    with pytest.raises((TypeError, ValueError), match=message) as caught:
        _surface_form_identities(selected, invalid_forms)

    error_text = str(caught.value)
    marker = "; form_api_diagnostic="
    assert marker in error_text
    diagnostic = json.loads(error_text.split(marker, 1)[1])
    assert diagnostic["code_type"] == "tuple"
    assert diagnostic["code_component_types"] == ["NoneType", "NoneType"]
    assert diagnostic["module_name"] == "libffcx_forms_0123456789abcdef"
    assert diagnostic["module_path"] == str(Path(prior.form.module.__file__))
    assert diagnostic["signature_cffi_kind"].startswith("pointer:")
    assert "compiled q160 exterior facet" not in error_text


def test_functional_store_module_and_ufcx_signatures_are_canonical(tmp_path):
    first_dir = tmp_path / "cache-a"
    second_dir = tmp_path / "cache-b"
    first_dir.mkdir()
    second_dir.mkdir()
    first_path = first_dir / "libffcx_forms_0123456789abcdef.so"
    second_path = second_dir / first_path.name
    first_path.write_bytes(b"same extension bytes")
    second_path.write_bytes(b"same extension bytes")
    first_module = _fake_ffcx_module(first_path)
    second_module = _fake_ffcx_module(second_path)
    selected, first = _fake_surface_form_maps(
        tmp_path / "maps-a", selected_has_forms=False, module=first_module
    )
    selected_second, second = _fake_surface_form_maps(
        tmp_path / "maps-b", selected_has_forms=False, module=second_module
    )
    assert _surface_form_identities(selected, first) == _surface_form_identities(
        selected_second, second
    )

    changed_bytes_path = tmp_path / "changed" / first_path.name
    changed_bytes_path.parent.mkdir()
    changed_bytes_path.write_bytes(b"different extension bytes")
    changed_bytes_module = _fake_ffcx_module(changed_bytes_path)
    selected_changed_bytes, changed_bytes = _fake_surface_form_maps(
        tmp_path / "maps-c", selected_has_forms=False, module=changed_bytes_module
    )
    assert _surface_form_identities(
        selected_changed_bytes, changed_bytes
    ) != _surface_form_identities(selected, first)

    changed_module_name = _fake_ffcx_module(
        first_path, name="libffcx_forms_fedcba9876543210"
    )
    changed_name_forms = dict(first)
    prior = changed_name_forms[("bottom", 0)]
    changed_name_forms[("bottom", 0)] = _fake_surface_assembler(
        prior.function_space,
        prior.mesh_data,
        prior.side,
        prior.component,
        prior.tag,
        _fake_compiled_form(
            prior.side,
            prior.component,
            prior.tag,
            module=changed_module_name,
        ),
    )
    assert _surface_form_identities(
        selected, changed_name_forms
    ) != _surface_form_identities(selected, first)

    changed_signature = dict(first)
    prior = changed_signature[("top", 0)]
    changed_signature[("top", 0)] = _fake_surface_assembler(
        prior.function_space,
        prior.mesh_data,
        prior.side,
        prior.component,
        prior.tag,
        _fake_compiled_form(
            prior.side,
            prior.component,
            prior.tag,
            module=first_module,
            ufcx_signature="a different specific UFCx form signature",
        ),
    )
    assert _surface_form_identities(selected, changed_signature) != _surface_form_identities(
        selected, first
    )


def test_functional_store_rejects_missing_or_malformed_compiled_form_identity(
    tmp_path,
    monkeypatch,
):
    selected, compiled = _fake_surface_form_maps(
        tmp_path, selected_has_forms=False
    )

    def replace_form(key, form):
        result = dict(compiled)
        prior = result[key]
        result[key] = _fake_surface_assembler(
            prior.function_space,
            prior.mesh_data,
            prior.side,
            prior.component,
            prior.tag,
            form,
        )
        return result

    prior = compiled[("top", 0)]
    with pytest.raises(ValueError, match="loaded FFCx form module identity is missing"):
        _surface_form_identities(
            selected,
            replace_form(
                ("top", 0),
                SimpleNamespace(
                    code=(None, None),
                    module=None,
                    ufcx_form=prior.form.ufcx_form,
                    integral_types=prior.form.integral_types,
                    rank=1,
                    dtype=np.dtype(np.complex128),
                ),
            ),
        )

    bad_module = _fake_ffcx_module(
        Path(prior.form.module.__file__), name="not_ffcx_forms"
    )
    with pytest.raises(ValueError, match="loaded FFCx form module identity is missing"):
        _surface_form_identities(
            selected,
            replace_form(
                ("top", 0),
                _fake_compiled_form("top", 0, prior.tag, module=bad_module),
            ),
        )

    relative_module = _fake_ffcx_module(
        Path("relative/libffcx_forms_0123456789abcdef.so")
    )
    with pytest.raises(ValueError, match="module path is not absolute"):
        _surface_form_identities(
            selected,
            replace_form(
                ("top", 0),
                _fake_compiled_form("top", 0, prior.tag, module=relative_module),
            ),
        )

    missing_file_module = _fake_ffcx_module(
        tmp_path / "missing" / "libffcx_forms_0123456789abcdef.so"
    )
    with pytest.raises(ValueError, match="module file is unavailable"):
        _surface_form_identities(
            selected,
            replace_form(
                ("top", 0),
                _fake_compiled_form("top", 0, prior.tag, module=missing_file_module),
            ),
        )

    empty_file = tmp_path / "empty" / "libffcx_forms_0123456789abcdef.so"
    empty_file.parent.mkdir()
    empty_file.touch()
    empty_module = _fake_ffcx_module(empty_file)
    with pytest.raises(ValueError, match="module file is not a nonempty file"):
        _surface_form_identities(
            selected,
            replace_form(
                ("top", 0),
                _fake_compiled_form("top", 0, prior.tag, module=empty_module),
            ),
        )

    with pytest.raises(ValueError, match="compiled Form code diagnostic is malformed"):
        _surface_form_identities(
            selected,
            replace_form(
                ("top", 0),
                _fake_compiled_form(
                    "top", 0, prior.tag, module=prior.form.module, code=(None, "bad")
                ),
            ),
        )

    bad_signature_form = _fake_compiled_form(
        "top", 0, prior.tag, module=prior.form.module, ufcx_signature=None
    )
    del bad_signature_form.ufcx_form.signature
    with pytest.raises(ValueError, match="UFCx Form signature is missing"):
        _surface_form_identities(
            selected, replace_form(("top", 0), bad_signature_form)
        )

    original_hash_file = functional_store_module._sha256_file

    def replace_module_during_hash(path):
        result = original_hash_file(path)
        path.write_bytes(b"changed during identity hashing")
        return result

    monkeypatch.setattr(
        functional_store_module, "_sha256_file", replace_module_during_hash
    )
    with pytest.raises(ValueError, match="module changed while hashing"):
        _surface_form_identities(selected, compiled)

    with pytest.raises(ValueError, match="needs all four compiled"):
        _surface_form_identities(
            selected,
            {key: value for key, value in compiled.items() if key != ("bottom", 0)},
        )


def test_functional_store_reopen_rejects_changed_compiled_component_form(tmp_path):
    modes = _mode_identities()
    selected, compiled = _fake_surface_form_maps(tmp_path, selected_has_forms=False)
    identity = _numerical_identity(modes)
    identity["quadrature"]["surface_forms"] = _surface_form_identities(
        selected, compiled
    )
    root = tmp_path / "compiled-form-identity-store"
    original = _store(root, modes, identity=identity)
    _write_first(original, modes)
    original.close()

    warm_compiled = dict(compiled)
    for key, prior in compiled.items():
        warm_compiled[key] = _fake_surface_assembler(
            prior.function_space,
            prior.mesh_data,
            prior.side,
            prior.component,
            prior.tag,
            _fake_compiled_form(
                prior.side,
                prior.component,
                prior.tag,
                module=prior.form.module,
                code=(None, None),
            ),
        )
    warm_identity = _numerical_identity(modes)
    warm_identity["quadrature"]["surface_forms"] = _surface_form_identities(
        selected, warm_compiled
    )
    reopened_warm = _store(root, modes, identity=warm_identity)
    reopened_warm.close()

    changed_compiled = dict(compiled)
    prior = changed_compiled[("top", 1)]
    changed_compiled[("top", 1)] = _fake_surface_assembler(
        prior.function_space,
        prior.mesh_data,
        prior.side,
        prior.component,
        prior.tag,
        _fake_compiled_form(
            prior.side,
            prior.component,
            prior.tag,
            module=prior.form.module,
            ufcx_signature="changed compiled component after store write",
        ),
    )
    changed_identity = _numerical_identity(modes)
    changed_identity["quadrature"]["surface_forms"] = _surface_form_identities(
        selected, changed_compiled
    )
    with pytest.raises(ValueError, match="numerical identity mismatch"):
        _store(root, modes, identity=changed_identity)


def test_prepared_worker_fair_order_uses_component_maps_and_fresh_contexts_once():
    worker_path = (
        Path(__file__).resolve().parents[2]
        / "tmp/p3_main_review/p3_h0p7_prepared_trace_functional_store_72cell_worker_v2.py"
    )
    spec = importlib.util.spec_from_file_location(
        "p3_prepared_trace_functional_store_worker_v2_fake", worker_path
    )
    assert spec is not None and spec.loader is not None
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)

    keys = {("bottom", 0), ("bottom", 1), ("top", 0), ("top", 1)}
    native6 = {key: object() for key in keys}
    native3 = {key: object() for key in keys}
    candidate6 = {key: object() for key in keys}
    candidate3 = {key: object() for key in keys}
    unprepared_map = {key: object() for key in keys}
    prepared_map = {key: object() for key in keys}
    unprepared_context = SimpleNamespace(
        _geometry_cache=None,
        _geometry_cache_last_facts=None,
        _geometry_cache_enabled=True,
        _prepared_trace_contractions={},
        _prepared_trace_release_count=0,
    )
    prepared_context = SimpleNamespace(
        _geometry_cache=None,
        _geometry_cache_last_facts=None,
        _geometry_cache_enabled=True,
        _prepared_trace_contractions={"bottom": object(), "top": object()},
        _prepared_trace_release_count=0,
    )
    fair_order = (
        (6, "native"),
        (6, "cached_weighted_moment_unprepared"),
        (6, "cached_weighted_moment_prepared"),
        (3, "candidate"),
        (3, "native"),
    )
    expected = (
        (native6, None, False),
        (unprepared_map, unprepared_context, True),
        (prepared_map, prepared_context, True),
        (candidate3, None, False),
        (native3, None, False),
    )
    claimed = set()
    selected_context_ids = []
    for (degree, path), expected_route in zip(fair_order, expected, strict=True):
        actual = worker._select_fair_route(
            degree,
            path,
            native_assemblers={6: native6, 3: native3},
            weighted_moment_unprepared_assemblers=unprepared_map,
            timed_prepared_assemblers=prepared_map,
            candidate_assemblers={6: candidate6, 3: candidate3},
            timed_unprepared_context=unprepared_context,
            timed_prepared_context=prepared_context,
        )
        assert actual == expected_route
        context_id = worker._claim_fresh_timed_context(path, actual[1], claimed)
        if actual[2]:
            selected_context_ids.append(context_id)
            actual[1]._geometry_cache_last_facts = {
                "release_count": 1,
                "payload_after_release_bytes": 0,
            }
            actual[1]._geometry_cache = None
    assert len(selected_context_ids) == 2
    assert selected_context_ids[0] != selected_context_ids[1]
    selected_again = worker._select_fair_route(
        6,
        "cached_weighted_moment_unprepared",
        native_assemblers={6: native6, 3: native3},
        weighted_moment_unprepared_assemblers=unprepared_map,
        timed_prepared_assemblers=prepared_map,
        candidate_assemblers={6: candidate6, 3: candidate3},
        timed_unprepared_context=unprepared_context,
        timed_prepared_context=prepared_context,
    )
    with pytest.raises(ValueError, match="already consumed"):
        worker._claim_fresh_timed_context(
            "cached_weighted_moment_unprepared", selected_again[1], claimed
        )


def test_restored_carrier_comparator_checks_entries_and_final_carrier_bitwise():
    worker_path = (
        Path(__file__).resolve().parents[2]
        / "tmp/p3_main_review/p3_h0p7_prepared_trace_functional_store_72cell_worker_v2.py"
    )
    spec = importlib.util.spec_from_file_location(
        "p3_prepared_trace_functional_store_worker_v2_carrier_fake", worker_path
    )
    assert spec is not None and spec.loader is not None
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)

    def carrier(changed=False):
        value = 1.25 + (1.0e-12 if changed else 0.0) + 2.5j
        entry = SimpleNamespace(
            mode_key=(0, "bottom", -71, 35, "s"),
            mode_identity={"mode_index": 0, "mode": "test"},
            normalization_h=1.25,
            coupling_rows=np.asarray([100, 104], dtype=np.int64),
            coupling_values=np.asarray([value, 0.5 - 0.75j], dtype=np.complex128),
            projection_rows=np.asarray([101], dtype=np.int64),
            projection_values=np.asarray([0.25 + 0.5j], dtype=np.complex128),
        )
        return SimpleNamespace(
            entries=(entry,),
            _global_rows=120,
            _owned_start=100,
            _owned_end=120,
            _batch_size=8,
            _mode_manifest=b"ordered-mode-manifest",
            _mode_manifest_sha256="a" * 64,
            _slave_rows=np.asarray([105], dtype=np.int64),
            _retained_numeric_bytes=121,
        )

    assert worker._carrier_arrays_are_bitwise_equal(
        carrier(), carrier()
    )["exact"]
    mismatch = worker._carrier_arrays_are_bitwise_equal(carrier(), carrier(changed=True))
    assert not mismatch["exact"]
    assert not mismatch["entry_results"][0]["arrays"]["coupling_values"]


def _mode_identity(index: int, polarization: str) -> dict:
    return {
        "schema": "fullspace-dtn.mode.v1",
        "mode_index": index,
        "side": "bottom",
        "m": -71,
        "n": 35,
        "polarization": polarization,
        "alpha": 0.125 + 0.0j,
        "gamma": -0.25 + 0.0j,
        "beta": 2.5 + 0.0j,
        "k_vector": (0.125 + 0.0j, -0.25 + 0.0j, 2.5 + 0.0j),
        "e_vector": (1.0 + 0.0j, 0.0 + 0.0j, 0.0 + 0.0j),
        "h_vector": (0.0 + 0.0j, 1.0 + 0.0j, 0.0 + 0.0j),
        "refractive_index": 1.0 + 0.0j,
        "vertical_sign": -1,
        "electric_tangential_norm_sq": 1.0,
        "power_per_unit_amplitude": 1.0,
        "propagating": True,
        "rayleigh_warning": False,
        "classification": "propagating",
        "rayleigh_tolerance": 1.0e-10,
        "projection_denominator": 1.25,
        "traction_vector": (1.0 + 0.0j, -0.5 + 0.0j),
    }


def _mode_identities(count: int = 2) -> tuple[dict, ...]:
    return tuple(_mode_identity(i, "s" if i % 2 == 0 else "p") for i in range(count))


def _mode_sha(modes: tuple[dict, ...]) -> str:
    payload = {
        "schema": FULLSPACE_DTN_MANIFEST_SCHEMA,
        "profile": FULLSPACE_DTN_PROFILE,
        "mode_count": len(modes),
        "modes": list(modes),
    }
    return hashlib.sha256(_mode_json_bytes(payload)).hexdigest()


def _p6_context_identity_fixture() -> dict:
    def array(tag: str, shape=(1,)):
        return {
            "dtype": "<f8",
            "shape": list(shape),
            "nbytes": int(np.prod(shape)) * 8,
            "sha256": tag * 64,
        }

    traces = {side: array("3", (8, 3, 7, 7)) for side in ("bottom", "top")}
    return {
        "schema": P6_CONTEXT_PROVIDER_SCHEMA,
        "backend": SURFACE_COMPONENT_PAIR_BACKEND,
        "degree": 6,
        "quadrature_degree": 160,
        "weighted_moment_contraction": SURFACE_WEIGHTED_MOMENT_CONTRACTION,
        "prepared_trace_contraction": {
            "enabled": True,
            "expression": "ikab,kab->i",
            "side_plans": {
                side: {
                    "expression": "ikab,kab->i",
                    "einsum_path": ["einsum_path", [0, 1]],
                    "trace_sha256": traces[side]["sha256"],
                }
                for side in ("bottom", "top")
            },
        },
        "element": {
            "basix_hash": 123,
            "family": "N1E",
            "degree": 6,
            "cell_type": "hexahedron",
            "value_size": 3,
            "map_type": "covariantPiola",
            "polyset_type": "standard",
            "lagrange_variant": "legendre",
            "coefficient_matrix": {
                "dtype": "<f8",
                "shape": [8, 1029],
                "sha256": "4" * 64,
            },
            "endpoint_polynomial_table_sha256": "5" * 64,
        },
        "quadrature_and_basis_arrays": {
            name: array(str(index + 1), shape)
            for index, (name, shape) in enumerate(
                (
                    ("interval_points", (81,)),
                    ("interval_weights", (81,)),
                    ("quadrilateral_points", (6561, 2)),
                    ("quadrilateral_weights", (6561,)),
                    ("polynomial_values", (81, 7)),
                    ("expanded_polynomial_x", (6561, 7)),
                    ("expanded_polynomial_y", (6561, 7)),
                )
            )
        },
        "coordinate_element": {
            "basix_element_hash": 8,
            "coordinate_map_hash": 8,
            "ffcx_table_options": {
                "table_rtol": 1.0e-6,
                "table_atol": 1.0e-9,
                "formatter_identity": {"module_sha256": "6" * 64},
            },
            "consumed_tables_by_side": {
                side: {
                    "values": array("7", (6561, 8)),
                    "derivatives": array("8", (6561, 8, 3)),
                    "facet_jacobian": array("9", (3, 2)),
                    "local_facet": local_facet,
                }
                for side, local_facet in (("bottom", 0), ("top", 1))
            },
        },
        "trace_reference_tensors": traces,
    }


def test_six_lane_context_route_is_accepted_and_separates_store_identity():
    from src.solvers.fullspace_surface_legendre import (
        SURFACE_WEIGHTED_MOMENT_CONTRACTION_SIX_LANE,
    )

    baseline = _p6_context_identity_fixture()
    _validate_p6_context_descriptor(baseline)
    candidate = copy.deepcopy(baseline)
    candidate["weighted_moment_contraction"] = (
        SURFACE_WEIGHTED_MOMENT_CONTRACTION_SIX_LANE
    )
    _validate_p6_context_descriptor(candidate)
    assert functional_store_module._canonical_json_bytes(baseline) != (
        functional_store_module._canonical_json_bytes(candidate)
    )
    unsupported = copy.deepcopy(candidate)
    unsupported["weighted_moment_contraction"] = "unknown-route"
    with pytest.raises(ValueError, match="route differs"):
        _validate_p6_context_descriptor(unsupported)


def _p6_surface_provider_fixture() -> dict:
    return {
        "schema": P6_SURFACE_PROVIDER_SCHEMA,
        "backend": SURFACE_COMPONENT_PAIR_BACKEND,
        "degree": 6,
        "assemblers": [
            {"side": side, "component": component, "tag": tag}
            for side, tag in (("bottom", 17), ("top", 29))
            for component in (0, 1)
        ],
        "context": _p6_context_identity_fixture(),
    }


def _numerical_identity(modes: tuple[dict, ...], **changes) -> dict:
    degree = int(changes.pop("degree", 6))
    backend = changes.pop(
        "backend", SURFACE_COMPONENT_PAIR_BACKEND if degree == 6 else "native_ffcx"
    )
    value = {
        "schema": (
            P6_NUMERICAL_IDENTITY_SCHEMA
            if degree == 6
            else P3_NUMERICAL_IDENTITY_SCHEMA
        ),
        "source_sha256": SOURCE_SHA,
        "resolved_config_sha256": "2" * 64,
        "implementation_file_sha256": {"fixture.py": "d" * 64},
        "input_sha256": INPUT_SHA,
        "physical_model_sha256": PHYSICAL_SHA,
        "backend": backend,
        "degree": degree,
        "mesh": {"raw_coordinate_and_dofmap_sha256": "e" * 64},
        "dof_mpc": {"boundary_dofs_mpc_sha256": "f" * 64},
        "modes": {"count": len(modes), "ordered_manifest_sha256": _mode_sha(modes)},
        "quadrature": (
            {"degree": 160, "p6_surface_provider": _p6_surface_provider_fixture()}
            if degree == 6
            else {
                "degree": 160,
                "surface_forms": {
                    side: [{"side": side, "component": component} for component in (0, 1)]
                    for side in ("bottom", "top")
                },
            }
        ),
        "abi": {"scalar": "<c16", "index": "<i8", "mpi_size": 1},
    }
    value.update(changes)
    return value


def _readonly(values, dtype=None):
    array = np.ascontiguousarray(values, dtype=dtype)
    array.flags.writeable = False
    return array


def _fake_live_p6_context():
    from src.solvers.fullspace_surface_legendre import (
        SURFACE_COMPONENT_PAIR_BACKEND,
        SURFACE_WEIGHTED_MOMENT_CONTRACTION,
    )

    context = object.__new__(_SurfaceLegendreMomentContext)
    context.backend = SURFACE_COMPONENT_PAIR_BACKEND
    context.degree = 6
    context.quadrature_degree = 160
    context._geometry_cache_enabled = True
    context._weighted_moment_contraction = SURFACE_WEIGHTED_MOMENT_CONTRACTION
    context._prepare_trace_contraction = True
    context.interval_points = _readonly(np.linspace(0.0, 1.0, 81), np.float64)
    context.interval_weights = _readonly(np.full(81, 1.0 / 81.0), np.float64)
    context.quadrilateral_points = _readonly(np.zeros((6561, 2)), np.float64)
    context.quadrilateral_weights = _readonly(np.full(6561, 1.0 / 6561.0), np.float64)
    context.polynomial_values = _readonly(np.zeros((81, 7)), np.float64)
    context._polynomial_x = _readonly(np.zeros((6561, 7)), np.float64)
    context._polynomial_y = _readonly(np.zeros((6561, 7)), np.float64)
    context._geometry_face_tables = {}
    context._geometry_face_local_facets = {"bottom": 0, "top": 1}
    context._facet_jacobians_by_side = {}
    context._trace_tables = {}
    context._prepared_trace_contractions = {}
    context._coordinate_element_identity = {
        "basix_element_hash": 8,
        "coordinate_map_hash": 8,
        "basix_element_degree": 1,
        "basix_element_dimension": 8,
        "basix_element_value_size": 1,
        "coordinate_ufl_reference_value_shape": [3],
        "coordinate_ufl_block_size": 3,
        "element_source": "live fake UFL coordinate element",
    }
    context._ffcx_coordinate_table_options = {
        "table_rtol": 1.0e-6,
        "table_atol": 1.0e-9,
        "clamp_function": "ffcx.ir.elementtables.clamp_table_small_numbers",
        "clamp_targets_in_order": [-1.0, 0.0, 1.0],
        "float_roundtrip": "ffcx.codegeneration.C.c_implementation.CFormatter(np.float64)._format_number",
        "formatter_identity": {
            "class": "ffcx.codegeneration.C.c_implementation.CFormatter",
            "method": "_format_number",
            "scalar_dtype": "<f8",
            "module_path": "/diagnostic/path.py",
            "module_sha256": "6" * 64,
        },
    }
    for side in ("bottom", "top"):
        context._geometry_face_tables[side] = (
            _readonly(np.zeros((6561, 8)), np.float64),
            _readonly(np.zeros((6561, 8, 3)), np.float64),
        )
        context._facet_jacobians_by_side[side] = _readonly(
            np.asarray([[0.0, 1.0], [0.0, 1.0], [1.0, 0.0]]), np.float64
        )
        trace = _readonly(np.zeros((8, 3, 7, 7)), np.float64)
        context._trace_tables[(side, 0)] = trace
        context._trace_tables[(side, 1)] = trace
        context._prepared_trace_contractions[side] = SimpleNamespace(
            trace_tensor=trace,
            einsum_path=("einsum_path", (0, 1)),
        )

    class FakeElement:
        family = "N1E"
        degree = 6
        cell_type = "hexahedron"
        value_size = 3
        map_type = "covariantPiola"
        polyset_type = "standard"
        lagrange_variant = SimpleNamespace(name="legendre")

        @staticmethod
        def hash():
            return 123

    context._initialize_functional_store_identity(
        element=FakeElement(),
        coefficient_matrix_shape=(8, 1029),
        coefficient_matrix_dtype=np.dtype(np.float64).str,
        coefficient_matrix_sha256="4" * 64,
        endpoint_polynomial_table_sha256="5" * 64,
    )
    return context


class _FakeLinks:
    def __init__(self, rows):
        self.rows = rows

    def links(self, index):
        return self.rows[int(index)]


class _FakeTopology:
    dim = 3

    def __init__(self, index_map):
        self._index_map = index_map
        self._connectivity = {
            (2, 3): _FakeLinks({0: np.asarray([0]), 1: np.asarray([0])}),
            (3, 2): _FakeLinks({0: np.asarray([0, 1])}),
        }

    @staticmethod
    def cell_name():
        return "hexahedron"

    def index_map(self, _dimension):
        return SimpleNamespace(size_global=1)

    def create_connectivity(self, *_args):
        return None

    def connectivity(self, first, second):
        return self._connectivity[(first, second)]

    @staticmethod
    def get_cell_permutation_info():
        return np.asarray([0], dtype=np.uint32)


def _fake_p6_surface_bundle():
    context = _fake_live_p6_context()
    index_map = SimpleNamespace(
        local_range=(0, 8),
        size_local=8,
        size_global=8,
        num_ghosts=0,
        ghosts=np.empty(0, dtype=np.int64),
        owners=np.empty(0, dtype=np.int32),
    )
    mesh = SimpleNamespace(
        comm=SimpleNamespace(size=1),
        geometry=SimpleNamespace(
            x=np.ascontiguousarray(
                [[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0],
                 [0, 0, 1], [1, 0, 1], [0, 1, 1], [1, 1, 1]],
                dtype=np.float64,
            ),
            dofmap=np.ascontiguousarray([np.arange(8, dtype=np.int32)]),
        ),
    )
    mesh.topology = _FakeTopology(index_map)
    dofmap = SimpleNamespace(
        index_map=index_map,
        index_map_bs=1,
        cell_dofs=lambda _cell: np.arange(8, dtype=np.int32),
    )

    class FakeElement:
        basix_element = SimpleNamespace(
            family="N1E",
            degree=6,
            cell_type="hexahedron",
            value_size=3,
            map_type="covariantPiola",
            polyset_type="standard",
            hash=lambda: 123,
        )

    function_space = SimpleNamespace(mesh=mesh, dofmap=dofmap, element=FakeElement())
    mesh_data = SimpleNamespace(
        mesh=mesh,
        facet_tags=SimpleNamespace(
            find=lambda tag: np.asarray([0 if int(tag) == 17 else 1], dtype=np.int32)
        ),
    )
    mpc = SimpleNamespace(
        function_space=function_space,
        coefficients=lambda: (
            np.empty(0, dtype=np.complex128),
            np.zeros(9, dtype=np.int64),
        ),
        is_slave=np.zeros(8, dtype=np.int8),
        cell_to_slaves=_FakeLinks({0: np.empty(0, dtype=np.int64)}),
        masters=_FakeLinks({}),
    )
    context.function_space = function_space
    context.mesh_data = mesh_data
    context.mpc = mpc
    assemblers = {}
    for side, tag in (("bottom", 17), ("top", 29)):
        for component in (0, 1):
            assembler = object.__new__(_SurfaceLegendreMomentAssembler)
            assembler.context = context
            assembler.function_space = function_space
            assembler.mesh_data = mesh_data
            assembler.comm = mesh.comm
            assembler.side = side
            assembler.tag = tag
            assembler.component = component
            assembler.surface_backend = context.backend
            assemblers[(side, component)] = assembler
    return context, assemblers, mpc


def _open_surface_store(root, modes, assemblers, mpc):
    return PortFunctionalShardStore.for_surface(
        root,
        source_sha256=SOURCE_SHA,
        resolved_config_sha256="2" * 64,
        input_sha256=INPUT_SHA,
        physical_model_sha256=PHYSICAL_SHA,
        degree=6,
        backend=SURFACE_COMPONENT_PAIR_BACKEND,
        quadrature_degree=160,
        mode_identities=modes,
        mode_manifest_sha256=_mode_sha(modes),
        surface_assemblers=assemblers,
        mpc=mpc,
        ownership_range=(0, 8),
        slave_rows=np.empty(0, dtype=np.int64),
        row_dtype=np.dtype(np.int64),
        producer_provenance={"run_id": "fake", "pid": 999},
        max_shard_working_bytes=32 * 1024**2,
        max_total_disk_bytes=64 * 1024**2,
        disk_reserve_bytes=0,
    )


def test_p6_real_store_open_uses_live_context_and_reopens_without_native_forms(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        functional_store_module,
        "_live_abi_identity",
        lambda _mesh: {
            "python": "3.12",
            "numpy": "2.0",
            "petsc_scalar_dtype": "<c16",
            "petsc_index_dtype": "<i8",
            "mpi_size": 1,
        },
    )
    monkeypatch.setattr(
        functional_store_module,
        "_surface_form_identities",
        lambda *_args, **_kwargs: pytest.fail("p6 store-open attempted native Form identity"),
    )
    modes = _mode_identities()
    _context, assemblers, mpc = _fake_p6_surface_bundle()
    root = tmp_path / "live-p6-store"
    store = _open_surface_store(root, modes, assemblers, mpc)
    numerical = json.loads((root / "identity.json").read_text())["numerical_identity"]
    assert numerical["schema"] == P6_NUMERICAL_IDENTITY_SCHEMA
    assert "p6_surface_provider" in numerical["quadrature"]
    assert "surface_forms" not in numerical["quadrature"]
    assert (root / "writer.lock").is_file()
    first_identity = store.identity_sha256
    store.close()
    assert (root / "writer.lock").is_file()

    _second_context, second_assemblers, second_mpc = _fake_p6_surface_bundle()
    reopened = _open_surface_store(root, modes, second_assemblers, second_mpc)
    assert reopened.identity_sha256 == first_identity
    reopened.close()
    assert (root / "writer.lock").is_file()


def test_p6_context_snapshot_excludes_paths_and_rejects_replaced_or_writable_arrays():
    context = _fake_live_p6_context()
    descriptor = context.functional_store_identity_descriptor()
    assert descriptor["schema"] == P6_CONTEXT_PROVIDER_SCHEMA
    assert "/diagnostic/path.py" not in json.dumps(descriptor)
    original = context.polynomial_values
    context.polynomial_values = _readonly(original.copy(), np.float64)
    with pytest.raises(ValueError, match="immutable context lineage changed"):
        context.functional_store_identity_descriptor()
    context.polynomial_values = original
    original.flags.writeable = True
    with pytest.raises(ValueError, match="immutable context lineage changed"):
        context.functional_store_identity_descriptor()
    original.flags.writeable = False


def test_p6_old_form_identity_and_injected_form_arguments_are_rejected(tmp_path):
    modes = _mode_identities()
    old_p6 = _numerical_identity(modes)
    old_p6["schema"] = P3_NUMERICAL_IDENTITY_SCHEMA
    with pytest.raises(ValueError, match="schema does not match"):
        _store(tmp_path / "old-p6-schema", modes, identity=old_p6)
    with pytest.raises(ValueError, match="rejects injected compiled surface Forms"):
        build_surface_functional_numerical_identity(
            source_sha256=SOURCE_SHA,
            resolved_config_sha256="2" * 64,
            input_sha256=INPUT_SHA,
            physical_model_sha256=PHYSICAL_SHA,
            degree=6,
            backend=SURFACE_COMPONENT_PAIR_BACKEND,
            quadrature_degree=160,
            mode_count=1,
            mode_manifest_sha256="3" * 64,
            surface_assemblers={},
            compiled_surface_assemblers={},
            mpc=None,
        )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda identity: identity["quadrature"]["p6_surface_provider"]["context"]["coordinate_element"]["consumed_tables_by_side"]["bottom"]["values"].__setitem__("sha256", "9" * 64),
        lambda identity: identity["quadrature"]["p6_surface_provider"]["context"]["quadrature_and_basis_arrays"]["quadrilateral_weights"].__setitem__("sha256", "9" * 64),
        lambda identity: identity["quadrature"]["p6_surface_provider"]["context"]["element"]["coefficient_matrix"].__setitem__("sha256", "9" * 64),
        lambda identity: identity["dof_mpc"].__setitem__("boundary_cell_dofs_and_mpc_sha256", "9" * 64),
        lambda identity: identity["abi"].__setitem__("petsc_index_dtype", "<i4"),
        lambda identity: identity["modes"].__setitem__("ordered_manifest_sha256", "9" * 64),
    ],
)
def test_p6_reopen_rejects_numerical_context_tampering(tmp_path, monkeypatch, mutate):
    import copy

    monkeypatch.setattr(
        functional_store_module,
        "_live_abi_identity",
        lambda _mesh: {"petsc_scalar_dtype": "<c16", "petsc_index_dtype": "<i8", "mpi_size": 1},
    )
    modes = _mode_identities()
    _context, assemblers, mpc = _fake_p6_surface_bundle()
    root = tmp_path / "p6-tamper"
    store = _open_surface_store(root, modes, assemblers, mpc)
    expected_identity_sha = store.identity_sha256
    store.close()
    identity = json.loads((root / "identity.json").read_text())["numerical_identity"]
    assert hashlib.sha256(functional_store_module._canonical_json_bytes(identity)).hexdigest() == expected_identity_sha
    changed = copy.deepcopy(identity)
    mutate(changed)
    with pytest.raises(
        ValueError, match="numerical identity mismatch|ordered mode manifest hash differs"
    ):
        _store(root, modes, identity=changed)


class _PrefixStopSentinel(Exception):
    pass


def test_typed_progress_sentinel_occurs_after_third_durable_commit(tmp_path, monkeypatch):
    import src.solvers.fullspace_dtn_action as action_module

    events = []

    class FakeStore:
        def restore_prefix(self):
            return []

        def commit(self, _entry, *, mode_index):
            events.append(("commit", int(mode_index)))

        def close(self):
            events.append(("close", None))

    def fake_for_surface(cls, *_args, **_kwargs):
        return FakeStore()

    monkeypatch.setattr(
        PortFunctionalShardStore, "for_surface", classmethod(fake_for_surface)
    )
    monkeypatch.setattr(
        action_module,
        "build_ordered_mode_manifest",
        lambda modes, _cfg: (
            tuple({"mode_index": index} for index, _mode in enumerate(modes)),
            b"fake ordered manifest",
            "7" * 64,
        ),
    )
    monkeypatch.setattr(
        "src.solvers.dtn_port_3d._combine_owned_entries",
        lambda _components, _weights, *, comm: (
            np.asarray([0], dtype=np.int64),
            np.asarray([1.0 + 0.0j], dtype=np.complex128),
        ),
    )
    monkeypatch.setattr(
        "src.solvers.dtn_port_3d._mode_projection_denominator",
        lambda _mode, _cfg: 1.0,
    )
    monkeypatch.setattr(
        "src.solvers.dtn_port_3d._traction_vector",
        lambda _mode, _cfg: (1.0 + 0.0j, 0.0 + 0.0j),
    )

    index_map = SimpleNamespace(
        local_range=(0, 1),
        size_local=1,
        size_global=1,
        local_to_global=lambda rows: np.asarray(rows, dtype=np.int64),
    )
    mesh = SimpleNamespace(comm=SimpleNamespace(size=1))
    mpc = SimpleNamespace(
        function_space=SimpleNamespace(
            mesh=mesh,
            dofmap=SimpleNamespace(index_map=index_map, index_map_bs=1),
        ),
        slaves=np.empty(0, dtype=np.int64),
    )
    modes = tuple(
        SimpleNamespace(
            side="bottom",
            m=1,
            n=0,
            polarization="s",
            alpha=0.25 + 0.0j,
            gamma=0.0j,
            k_vector=(0.0j, 0.0j, 1.0 + 0.0j),
            e_vector=(1.0 + 0.0j, 0.0 + 0.0j),
        )
        for _ in range(3)
    )

    class FakeAssembler:
        def assemble_entries(self, _mode, _mpc):
            return np.asarray([0], dtype=np.int64), np.asarray([1.0 + 0.0j])

    assemblers = {
        (side, component): FakeAssembler()
        for side in ("bottom", "top")
        for component in (0, 1)
    }
    store_config = {
        "root": str(tmp_path / "sentinel-store"),
        "source_sha256": SOURCE_SHA,
        "resolved_config_sha256": "2" * 64,
        "input_sha256": INPUT_SHA,
        "physical_model_sha256": PHYSICAL_SHA,
        "max_shard_working_bytes": 32 * 1024**2,
        "max_total_disk_bytes": 64 * 1024**2,
        "disk_reserve_bytes": 0,
    }

    def callback(name, facts):
        if name == "surface_carrier_mode_progress":
            completed = int(facts["completed_modes"])
            events.append(("callback", completed))
            if completed == 3:
                raise _PrefixStopSentinel

    with pytest.raises(_PrefixStopSentinel):
        action_module.build_fullspace_dtn_carrier_from_surface(
            modes,
            assemblers,
            mpc,
            SimpleNamespace(),
            degree=3,
            quadrature_degree=160,
            progress_interval=1,
            functional_store_config=store_config,
            stage_callback=callback,
        )
    assert events[:6] == [
        ("commit", 0),
        ("callback", 1),
        ("commit", 1),
        ("callback", 2),
        ("commit", 2),
        ("callback", 3),
    ]
    assert events[-1] == ("close", None)


def _store(
    root: Path,
    modes: tuple[dict, ...] | None = None,
    *,
    identity: dict | None = None,
    provenance: dict | None = None,
    max_shard_working_bytes: int = 32 * 1024**2,
    max_total_disk_bytes: int = 64 * 1024**2,
    fault=None,
) -> PortFunctionalShardStore:
    modes = _mode_identities() if modes is None else modes
    return PortFunctionalShardStore(
        root,
        _numerical_identity(modes) if identity is None else identity,
        modes,
        ownership_range=(100, 120),
        slave_rows=np.asarray([105], dtype=np.int64),
        row_dtype=np.int64,
        producer_provenance=(
            {"run_id": "producer", "output_directory": "/producer"}
            if provenance is None
            else provenance
        ),
        max_shard_working_bytes=max_shard_working_bytes,
        max_total_disk_bytes=max_total_disk_bytes,
        disk_reserve_bytes=0,
        _test_fault_hook=fault,
    )


def _functional(index: int, modes: tuple[dict, ...] | None = None, **changes):
    modes = _mode_identities() if modes is None else modes
    mode = modes[index]
    value = {
        "mode_key": (
            int(mode["mode_index"]),
            str(mode["side"]),
            int(mode["m"]),
            int(mode["n"]),
            str(mode["polarization"]),
        ),
        "mode_identity": mode,
        "coupling_rows": np.asarray([100, 103], dtype=np.int64),
        "coupling_values": np.asarray(
            [1.25 + 2.5j, -3.0e-28 + 1.0e-29j], dtype=np.complex128
        ),
        "projection_rows": np.asarray([101, 109], dtype=np.int64),
        "projection_values": np.asarray(
            [0.5 - 0.75j, 4.0e-20 + 3.0e-20j], dtype=np.complex128
        ),
        "normalization_h": 1.25,
    }
    value.update(changes)
    return SimpleNamespace(**value)


def _write_first(
    store: PortFunctionalShardStore, modes: tuple[dict, ...] | None = None
):
    modes = _mode_identities() if modes is None else modes
    return store.commit(_functional(0, modes), mode_index=0)


def test_prepared_trace_plan_is_bitwise_identical_and_borrows_immutable_trace():
    rng = np.random.default_rng(911)
    trace = np.ascontiguousarray(rng.normal(size=(37, 3, 7, 7)), dtype=np.float64)
    trace[0, 0, 0, 0] = 1.0e-29
    trace[3, 1, 6, 6] = -2.0e-27
    trace.flags.writeable = False
    moments = np.ascontiguousarray(
        rng.normal(size=(3, 7, 7)) + 1j * rng.normal(size=(3, 7, 7)),
        dtype=np.complex128,
    )
    prepared = PreparedFaceTraceContraction.prepare(trace)
    expected = assemble_face_from_weighted_moments(trace, moments)
    actual = prepared.apply(moments)
    assert prepared.trace_tensor is trace
    assert np.array_equal(actual, expected)


@pytest.mark.parametrize(
    "kwargs",
    [
        {
            "backend": SURFACE_COMPONENT_PAIR_BACKEND,
            "degree": 3,
            "quadrature_degree": 160,
            "reuse_geometry_cache": True,
            "weighted_moment_contraction": SURFACE_WEIGHTED_MOMENT_CONTRACTION,
        },
        {
            "backend": SURFACE_COMPONENT_PAIR_BACKEND,
            "degree": 6,
            "quadrature_degree": 160,
            "reuse_geometry_cache": False,
            "weighted_moment_contraction": SURFACE_WEIGHTED_MOMENT_CONTRACTION,
        },
        {
            "backend": "native_ffcx",
            "degree": 6,
            "quadrature_degree": 160,
            "reuse_geometry_cache": True,
            "weighted_moment_contraction": SURFACE_WEIGHTED_MOMENT_CONTRACTION,
        },
        {
            "backend": SURFACE_COMPONENT_PAIR_BACKEND,
            "degree": 6,
            "quadrature_degree": 159,
            "reuse_geometry_cache": True,
            "weighted_moment_contraction": SURFACE_WEIGHTED_MOMENT_CONTRACTION,
        },
    ],
)
def test_prepared_trace_optin_rejects_other_routes(kwargs):
    with pytest.raises(ValueError):
        validate_prepared_trace_contraction(True, **kwargs)


def test_prepared_trace_plan_rejects_mutable_nonfinite_and_bad_variable_data():
    with pytest.raises(ValueError, match="immutable"):
        PreparedFaceTraceContraction.prepare(np.zeros((3, 3, 7, 7), dtype=np.float64))
    nonfinite = np.zeros((3, 3, 7, 7), dtype=np.float64)
    nonfinite[0, 0, 0, 0] = np.nan
    nonfinite.flags.writeable = False
    with pytest.raises(ValueError, match="non-finite"):
        PreparedFaceTraceContraction.prepare(nonfinite)
    trace = np.zeros((3, 3, 7, 7), dtype=np.float64)
    trace.flags.writeable = False
    prepared = PreparedFaceTraceContraction.prepare(trace)
    with pytest.raises(ValueError, match="shape"):
        prepared.apply(np.zeros((3, 7, 6), dtype=np.complex128))
    bad_moments = np.zeros((3, 7, 7), dtype=np.complex128)
    bad_moments[1, 0, 0] = np.inf
    with pytest.raises(ValueError, match="non-finite"):
        prepared.apply(bad_moments)


def test_only_explicit_h0p7_profile_enables_prepared_trace_route():
    from src.solvers.fullspace_surface_legendre import (
        SURFACE_WEIGHTED_MOMENT_CONTRACTION,
    )

    assert V6_0P7_P3_HP_OPTIN_PROFILES
    for profile in V6_0P7_P3_HP_OPTIN_PROFILES:
        options = native_profile_facts(profile)["component_options"]
        assert options["dtn_surface_prepare_trace_contraction"] is True
        assert options["dtn_surface_weighted_moment_contraction"] == (
            SURFACE_WEIGHTED_MOMENT_CONTRACTION
        )
    for profile in V6_NATIVE_PROFILES - V6_0P7_P3_HP_OPTIN_PROFILES:
        assert (
            "dtn_surface_prepare_trace_contraction"
            not in native_profile_facts(profile)["component_options"]
        )


def test_prefix_phase_use_counts_resume_between_s_and_p():
    modes = [
        SimpleNamespace(
            side="bottom",
            m=1,
            n=2,
            alpha=1 + 0j,
            gamma=2 + 0j,
            k_vector=(0j, 0j, 3 + 0j),
            polarization="s",
        ),
        SimpleNamespace(
            side="bottom",
            m=1,
            n=2,
            alpha=1 + 0j,
            gamma=2 + 0j,
            k_vector=(0j, 0j, 3 + 0j),
            polarization="p",
        ),
        SimpleNamespace(
            side="top",
            m=1,
            n=2,
            alpha=1 + 0j,
            gamma=2 + 0j,
            k_vector=(0j, 0j, 4 + 0j),
            polarization="s",
        ),
    ]
    remaining = _remaining_dtn_component_phase_uses(modes, 1)
    assert remaining == {
        ("bottom", 1, 2, 1 + 0j, 2 + 0j, 3 + 0j): 1,
        ("top", 1, 2, 1 + 0j, 2 + 0j, 4 + 0j): 1,
    }
    assert _remaining_dtn_component_phase_uses(modes, len(modes)) == {}
    with pytest.raises(ValueError):
        _remaining_dtn_component_phase_uses(modes, len(modes) + 1)


_FROZEN_P6_PHASE_MANIFEST_SHA = "2216fcd0fae1cb89003fa5da7a96f6cdcce805334a128480476e1b93c79c43b2"
_FROZEN_P6_PHASE_ROWS = (
    (10, "top", -142, 0, "s", -8.869634347212868, 0.0, 1.377601444289294, 0.0),
    (24177, "bottom", -71, 35, "p", 0.05248878898214571, 8.79645943005142, -1.780234909194495, -0.00019572724132429315),
    (8146, "top", -71, 35, "s", 0.05248878898214571, 8.79645943005142, 1.785425891785154, 0.0),
    (16041, "bottom", -142, 0, "p", -8.869634347212868, 0.0, -1.3708670549917559, -0.00025417524362925),
    (11, "top", -142, 0, "p", -8.869634347212868, 0.0, 1.377601444289294, 0.0),
    (24176, "bottom", -71, 35, "s", 0.05248878898214571, 8.79645943005142, -1.780234909194495, -0.00019572724132429315),
    (8147, "top", -71, 35, "p", 0.05248878898214571, 8.79645943005142, 1.785425891785154, 0.0),
    (16040, "bottom", -142, 0, "s", -8.869634347212868, 0.0, -1.3708670549917559, -0.00025417524362925),
)


def _frozen_p6_phase_modes():
    return tuple(
        SimpleNamespace(
            mode_index=index,
            side=side,
            m=m,
            n=n,
            polarization=polarization,
            alpha=complex(alpha, 0.0),
            gamma=complex(gamma, 0.0),
            k_vector=(0.0j, 0.0j, complex(kz_real, kz_imag)),
        )
        for (
            index,
            side,
            m,
            n,
            polarization,
            alpha,
            gamma,
            kz_real,
            kz_imag,
        ) in _FROZEN_P6_PHASE_ROWS
    )


def test_frozen_eight_mode_manifest_phase_keys_drive_assembly_counts():
    assert _FROZEN_P6_PHASE_MANIFEST_SHA == "2216fcd0fae1cb89003fa5da7a96f6cdcce805334a128480476e1b93c79c43b2"
    modes = _frozen_p6_phase_modes()
    assert len(modes) == 8
    keys = tuple(_dtn_component_phase_key(mode) for mode in modes)
    control = _remaining_dtn_component_phase_uses(modes, 0)
    prefix = _remaining_dtn_component_phase_uses(modes, 0) - _remaining_dtn_component_phase_uses(modes, 3)
    suffix = _remaining_dtn_component_phase_uses(modes, 3)
    assert (len(control), sum(control.values()), 2 * len(control)) == (4, 8, 8)
    assert (len(prefix), sum(prefix.values()), 2 * len(prefix)) == (3, 3, 6)
    assert (len(suffix), sum(suffix.values()), 2 * len(suffix)) == (4, 5, 8)
    assert (3, 5, len(modes)) == (3, 5, 8)
    first_suffix_pair_modes = []
    seen = set()
    for index, key in enumerate(keys[3:], start=3):
        if key not in seen:
            first_suffix_pair_modes.append(index)
            seen.add(key)
    assert first_suffix_pair_modes == [3, 4, 5, 6]


def test_store_commits_exact_arrays_and_accepts_new_consumer_path(tmp_path):
    modes = _mode_identities()
    root = tmp_path / "store-p6"
    first = _store(
        root,
        modes,
        provenance={"run_id": "producer", "output_directory": "/attempt/producer"},
    )
    _write_first(first, modes)
    first.close()

    resumed = _store(
        root,
        modes,
        provenance={"run_id": "consumer", "output_directory": "/attempt/consumer"},
    )
    restored = resumed.restore_prefix()
    assert len(restored) == 1
    original = _functional(0, modes)
    for key in (
        "coupling_rows",
        "coupling_values",
        "projection_rows",
        "projection_values",
    ):
        assert np.array_equal(restored[0][key], getattr(original, key))
        assert (
            restored[0][key].tobytes(order="C")
            == getattr(original, key).tobytes(order="C")
        )
        assert not restored[0][key].flags.writeable
    assert restored[0]["normalization_h"].hex() == original.normalization_h.hex()
    resumed.commit(_functional(1, modes), mode_index=1)
    resumed.close()
    manifests = [
        json.loads((root / f"functional_{index:08d}" / "manifest.json").read_text())
        for index in range(2)
    ]
    assert manifests[0]["producer_provenance"]["run_id"] == "producer"
    assert manifests[1]["producer_provenance"]["run_id"] == "consumer"
    assert manifests[0]["mode_identity"]["polarization"] == "s"
    assert manifests[1]["mode_identity"]["polarization"] == "p"


def test_uninterrupted_and_prefix_resumed_functionals_are_bitwise_equal(tmp_path):
    modes = _mode_identities(4)
    uninterrupted_root = tmp_path / "uninterrupted"
    uninterrupted = _store(uninterrupted_root, modes)
    for index in range(len(modes)):
        uninterrupted.commit(_functional(index, modes), mode_index=index)
    uninterrupted_values = uninterrupted.restore_prefix()
    uninterrupted.close()

    resumed_root = tmp_path / "resumed"
    producer = _store(
        resumed_root,
        modes,
        provenance={"run_id": "producer", "output_directory": "/producer"},
    )
    for index in range(2):
        producer.commit(_functional(index, modes), mode_index=index)
    producer.close()
    consumer = _store(
        resumed_root,
        modes,
        provenance={"run_id": "consumer", "output_directory": "/consumer"},
    )
    prefix = consumer.restore_prefix()
    for index in range(len(prefix), len(modes)):
        consumer.commit(_functional(index, modes), mode_index=index)
    resumed_values = consumer.restore_prefix()
    consumer.close()

    assert len(uninterrupted_values) == len(resumed_values) == len(modes)
    for uninterrupted_item, resumed_item in zip(
        uninterrupted_values, resumed_values, strict=True
    ):
        assert uninterrupted_item["mode_key"] == resumed_item["mode_key"]
        assert uninterrupted_item["normalization_h"].hex() == resumed_item[
            "normalization_h"
        ].hex()
        for name in (
            "coupling_rows",
            "coupling_values",
            "projection_rows",
            "projection_values",
        ):
            assert (
                uninterrupted_item[name].tobytes(order="C")
                == resumed_item[name].tobytes(order="C")
            )


@pytest.mark.parametrize(
    "identity_key",
    [
        "source_sha256",
        "resolved_config_sha256",
        "input_sha256",
        "physical_model_sha256",
    ],
)
def test_store_rejects_numerical_identity_mismatch(tmp_path, identity_key):
    modes = _mode_identities()
    root = tmp_path / "identity-store"
    store = _store(root, modes)
    _write_first(store, modes)
    store.close()
    changed = _numerical_identity(modes)
    changed[identity_key] = "9" * (40 if identity_key == "source_sha256" else 64)
    with pytest.raises(ValueError, match="identity mismatch"):
        _store(root, modes, identity=changed)


def test_store_rejects_ordered_mode_manifest_mismatch(tmp_path):
    modes = _mode_identities()
    root = tmp_path / "mode-identity"
    store = _store(root, modes)
    _write_first(store, modes)
    store.close()
    changed_modes = list(_mode_identities())
    changed_modes[1] = dict(changed_modes[1], alpha=0.12500000000000003 + 0.0j)
    changed_modes = tuple(changed_modes)
    changed_identity = _numerical_identity(changed_modes)
    with pytest.raises(ValueError, match="identity mismatch"):
        _store(root, changed_modes, identity=changed_identity)


def test_store_rejects_wrong_degree_backend_or_quadrature(tmp_path):
    modes = _mode_identities()
    wrong_backend = _numerical_identity(modes)
    wrong_backend["backend"] = "native_ffcx"
    with pytest.raises(ValueError, match="degree-specific route"):
        _store(tmp_path / "wrong-backend", modes, identity=wrong_backend)

    wrong_quadrature = _numerical_identity(modes)
    wrong_quadrature["quadrature"]["degree"] = 159
    with pytest.raises(ValueError, match="q160"):
        _store(tmp_path / "wrong-quadrature", modes, identity=wrong_quadrature)


@pytest.mark.parametrize(
    "changes,match",
    [
        ({"coupling_rows": np.asarray([103, 100], dtype=np.int64)}, "ordered, unique"),
        ({"coupling_rows": np.asarray([100, 100], dtype=np.int64)}, "ordered, unique"),
        (
            {
                "coupling_rows": np.asarray([105], dtype=np.int64),
                "coupling_values": np.asarray([1 + 0j], dtype=np.complex128),
            },
            "slave",
        ),
        (
            {
                "coupling_rows": np.asarray([99], dtype=np.int64),
                "coupling_values": np.asarray([1 + 0j], dtype=np.complex128),
            },
            "owned",
        ),
        (
            {"coupling_values": np.asarray([np.nan + 0j, 1 + 0j], dtype=np.complex128)},
            "non-finite",
        ),
        ({"normalization_h": 1.2500000000000002}, "differs from mode identity"),
        ({"normalization_h": 0.0}, "invalid or differs"),
        ({"mode_key": (1, "bottom", -71, 35, "s")}, "key/index identity differs"),
        ({"mode_identity": dict(_mode_identity(1, "s"))}, "key/index identity differs"),
    ],
)
def test_store_rejects_invalid_functional_rows_values_and_h(tmp_path, changes, match):
    modes = _mode_identities()
    store = _store(tmp_path / "invalid-store", modes)
    with pytest.raises(ValueError, match=match):
        store.commit(_functional(0, modes, **changes), mode_index=0)
    store.close()
    assert not (tmp_path / "invalid-store" / "functional_00000000").exists()


def test_store_rejects_wrong_sparse_dtype_and_unmatched_lengths(tmp_path):
    modes = _mode_identities()
    store = _store(tmp_path / "invalid-layout", modes)
    wrong_dtype = _functional(
        0,
        modes,
        coupling_rows=np.asarray([100, 103], dtype=np.int32),
    )
    with pytest.raises(ValueError, match="invalid dtype/layout"):
        store.commit(wrong_dtype, mode_index=0)
    wrong_length = _functional(
        0,
        modes,
        coupling_values=np.asarray([1 + 0j], dtype=np.complex128),
    )
    with pytest.raises(ValueError, match="invalid dtype/layout"):
        store.commit(wrong_length, mode_index=0)
    store.close()


def test_pre_rename_interruption_is_ignored_and_can_resume_same_prefix(tmp_path):
    modes = _mode_identities()

    def fail_before(point):
        if point == "before_rename":
            raise RuntimeError("simulated pre-rename interruption")

    root = tmp_path / "pre-rename"
    store = _store(root, modes, fault=fail_before)
    with pytest.raises(RuntimeError, match="pre-rename"):
        _write_first(store, modes)
    store.close()
    assert not (root / "functional_00000000").exists()
    assert any(path.name.startswith(".tmp_functional_") for path in root.iterdir())
    resumed = _store(root, modes)
    assert resumed.committed_count == 0
    _write_first(resumed, modes)
    assert len(resumed.restore_prefix()) == 1
    resumed.close()


def test_store_rejects_more_than_one_unfinished_shard(tmp_path):
    modes = _mode_identities()
    root = tmp_path / "multiple-unfinished"
    store = _store(root, modes)
    store.close()
    for suffix in ("a" * 32, "b" * 32):
        (root / f".tmp_functional_00000000_{suffix}").mkdir()
    with pytest.raises(ValueError, match="multiple incomplete temporary shards"):
        _store(root, modes)


def test_post_rename_interruption_is_visible_to_fresh_process(tmp_path):
    modes = _mode_identities()

    def fail_after(point):
        if point == "after_commit":
            raise RuntimeError("simulated post-rename interruption")

    root = tmp_path / "post-rename"
    store = _store(root, modes, fault=fail_after)
    with pytest.raises(RuntimeError, match="post-rename"):
        _write_first(store, modes)
    store.close()

    script = """
import sys
import numpy as np
from src.test.test_task39extra_functional_store import _store, _mode_identities
root = __import__('pathlib').Path(sys.argv[1])
modes = _mode_identities()
store = _store(root, modes)
items = store.restore_prefix()
assert store.committed_count == 1 and len(items) == 1
assert np.array_equal(items[0]['coupling_values'], np.asarray([1.25+2.5j, -3e-28+1e-29j], dtype=np.complex128))
store.close()
"""
    child = subprocess.run(
        [sys.executable, "-c", script, str(root)],
        cwd=Path(__file__).resolve().parents[2],
        text=True,
        capture_output=True,
        check=False,
    )
    assert child.returncode == 0, child.stdout + child.stderr


def test_store_rejects_corrupt_payload_and_prefix_gap(tmp_path):
    modes = _mode_identities()
    root = tmp_path / "corrupt-payload"
    store = _store(root, modes)
    _write_first(store, modes)
    store.close()
    payload = root / "functional_00000000" / "payload.npz"
    raw = bytearray(payload.read_bytes())
    raw[-1] ^= 0x01
    payload.write_bytes(raw)
    corrupt = _store(root, modes)
    with pytest.raises(ValueError, match="checksum"):
        corrupt.restore_prefix()
    corrupt.close()

    gap_root = tmp_path / "gap"
    gap = _store(gap_root, modes)
    _write_first(gap, modes)
    gap.commit(_functional(1, modes), mode_index=1)
    gap.close()
    shutil.rmtree(gap_root / "functional_00000000")
    with pytest.raises(ValueError, match="gap or duplicate"):
        _store(gap_root, modes)


def test_store_rejects_missing_payload_and_malformed_manifest(tmp_path):
    modes = _mode_identities()
    missing_root = tmp_path / "missing-payload"
    store = _store(missing_root, modes)
    _write_first(store, modes)
    store.close()
    (missing_root / "functional_00000000" / "payload.npz").unlink()
    with pytest.raises(ValueError, match="incomplete"):
        _store(missing_root, modes)

    malformed_root = tmp_path / "bad-manifest"
    store = _store(malformed_root, modes)
    _write_first(store, modes)
    store.close()
    (malformed_root / "functional_00000000" / "manifest.json").write_text("{")
    with pytest.raises(ValueError, match="manifest is malformed"):
        _store(malformed_root, modes)


def test_store_rejects_header_dtype_before_numpy_allocation(tmp_path, monkeypatch):
    modes = _mode_identities()
    root = tmp_path / "header-dtype"
    store = _store(root, modes)
    _write_first(store, modes)
    store.close()
    manifest_path = root / "functional_00000000" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["arrays"]["coupling_values"]["dtype"] = np.dtype(np.float64).str
    manifest["arrays"]["coupling_values"]["nbytes"] -= 16
    manifest["uncompressed_payload_bytes"] -= 16
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    )
    malformed = _store(root, modes)

    def allocation_forbidden(*_args, **_kwargs):
        raise AssertionError("NPZ allocation started before header validation")

    monkeypatch.setattr(np, "load", allocation_forbidden)
    with pytest.raises(ValueError, match="dtype differs before allocation"):
        malformed.restore_prefix()
    malformed.close()


def test_store_rejects_duplicate_content_at_a_later_mode_index(tmp_path):
    modes = _mode_identities()
    root = tmp_path / "duplicate"
    store = _store(root, modes)
    _write_first(store, modes)
    store.close()
    shutil.copytree(root / "functional_00000000", root / "functional_00000001")
    duplicate = _store(root, modes)
    with pytest.raises(ValueError, match="identity mismatch"):
        duplicate.restore_prefix()
    duplicate.close()


def test_store_preflights_work_and_disk_budgets_before_creating_shard(tmp_path):
    modes = _mode_identities()
    root = tmp_path / "budget"
    too_small_work = _store(
        root,
        modes,
        max_shard_working_bytes=16 * 1024**2 + 1,
    )
    with pytest.raises(MemoryError, match="working cap"):
        _write_first(too_small_work, modes)
    assert not (root / "functional_00000000").exists()
    too_small_work.close()

    disk_root = tmp_path / "disk-budget"
    too_small_disk = _store(
        disk_root,
        modes,
        max_total_disk_bytes=4096,
    )
    with pytest.raises(OSError, match="disk budget"):
        _write_first(too_small_disk, modes)
    assert not (disk_root / "functional_00000000").exists()
    too_small_disk.close()


def test_store_enforces_single_writer_and_separate_degree_roots(tmp_path):
    modes = _mode_identities()
    p6_root = tmp_path / "functional-store" / "p6"
    p3_root = tmp_path / "functional-store" / "p3"
    p6 = _store(p6_root, modes)
    with pytest.raises(BlockingIOError):
        _store(p6_root, modes)
    p3_identity = _numerical_identity(modes, degree=3, backend="native_ffcx")
    p3 = _store(p3_root, modes, identity=p3_identity)
    assert p6.identity_sha256 != p3.identity_sha256
    p3.close()
    p6.close()
