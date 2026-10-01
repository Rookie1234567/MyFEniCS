"""Small algebra/API negatives for the live-carrier research oracle.

Kernel fixtures here are explicit test doubles, not compiled FE evidence.
Actual kernel/pack/Gauss qualification is performed by the admitted all-mode
same-live-bundle case, independently of these small API tests.
"""
from types import SimpleNamespace
from pathlib import Path

import numpy as np
import pytest

from src.solvers.dtn_boundary_plane_qualification import carrier_numeric_identity, _failure_diagnostic
from src.solvers.dtn_boundary_phase_gauge import loaded_surface_kernel_identity


def _carrier():
    backing = np.arange(12, dtype=float).reshape(3, 4).astype(np.complex128)
    values = backing[:, 1]
    entry = SimpleNamespace(mode_key=(0, "top", 0, 0, "s"), normalization_h=2.0,
        coupling_rows=np.array([0, 2, 4], dtype=np.int32), coupling_values=values,
        projection_rows=np.array([0, 2, 4], dtype=np.int32), projection_values=values.conj())
    return SimpleNamespace(entries=[entry], global_rows=6, ownership_range=(0, 6),
        slave_rows=np.array([5], dtype=np.int32), mode_manifest_sha256="assembly",
        assembly_context_sha256="context", physical_generator_manifest_sha256="physical")


def test_live_carrier_digest_uses_full_noncontiguous_C_order_values():
    carrier = _carrier()
    original = carrier_numeric_identity(carrier)
    carrier.entries[0].coupling_values = carrier.entries[0].coupling_values.copy()
    assert carrier_numeric_identity(carrier) == original
    carrier.entries[0].coupling_values[1] += 1j
    assert carrier_numeric_identity(carrier)["carrier_numeric_sha256"] != original["carrier_numeric_sha256"]


@pytest.mark.parametrize("field", ["normalization_h", "mode_key", "projection_rows"])
def test_live_carrier_digest_rejects_H_key_or_row_mutation(field):
    carrier = _carrier()
    before = carrier_numeric_identity(carrier)
    entry = carrier.entries[0]
    setattr(entry, field, {"normalization_h": 3.0, "mode_key": (0, "top", 1, 0, "s"),
                         "projection_rows": np.array([0, 3, 4], dtype=np.int32)}[field])
    assert carrier_numeric_identity(carrier)["carrier_numeric_sha256"] != before["carrier_numeric_sha256"]


def test_live_numeric_digest_keeps_raw_context_separate():
    carrier = _carrier()
    before = carrier_numeric_identity(carrier)
    carrier.assembly_context_sha256 = "different-loaded-kernel"
    after = carrier_numeric_identity(carrier)
    assert before["carrier_numeric_sha256"] == after["carrier_numeric_sha256"]
    assert before != after


class _Constant:
    ufl_shape = ()
    def __init__(self, count, value):
        self._count = count
        self.value = np.asarray(value, dtype=np.complex128)
    def count(self):
        return self._count


def _kernel_fixture(tmp_path):
    constants = [_Constant(9, 1+2j), _Constant(10, 3+4j), _Constant(11, 5+6j)]
    binary = tmp_path/"fixture_kernel.so"
    binary.write_bytes(b"explicit fake binary for API test only")
    code = 'ufcx_integral fixture_integral = {0}; /* loaded-fixture-signature */'
    (tmp_path/"fixture_kernel.c").write_text(code)
    module = SimpleNamespace(__file__=str(binary), __name__="fixture_kernel",
                             ffi=SimpleNamespace(string=lambda value: value))
    ufcx = SimpleNamespace(num_constants=3, signature=b"loaded-fixture-signature",
        constant_name_map=[b"c0", b"c1", b"c2"], constant_ranks=[0, 0, 0],
        form_integral_offsets=[0, 0, 1, 1, 1, 1], form_integral_ids=[15],
        form_integrals=[SimpleNamespace(coordinate_element_hash=123, needs_facet_permutations=False)])
    compiled = SimpleNamespace(ufcx_form=ufcx, module=module)
    form = SimpleNamespace(constants=lambda: constants, signature=lambda: "UFL-fixture-signature")
    semantic = dict(zip(("alpha", "gamma", "kz"), constants, strict=True))
    return constants, form, compiled, code, semantic


def test_kernel_semantic_pack_probe_restores_exact_values(tmp_path, monkeypatch):
    from dolfinx import fem
    constants, form, compiled, code, semantic = _kernel_fixture(tmp_path)
    monkeypatch.setattr(fem, "pack_constants", lambda _: np.asarray([value.value.item() for value in constants]))
    before = [value.value.copy() for value in constants]
    identity = loaded_surface_kernel_identity(form, compiled, code, semantic)
    assert identity["restoration_exact"] and not identity["numerical_assembly_during_probe"]
    assert [row["packed_slot"] for row in identity["constant_roles"]] == [0, 1, 2]
    assert all(np.array_equal(value.value, old) for value, old in zip(constants, before, strict=True))


def test_kernel_bad_pack_mapping_stops_and_restores(tmp_path, monkeypatch):
    from dolfinx import fem
    constants, form, compiled, code, semantic = _kernel_fixture(tmp_path)
    before = [value.value.copy() for value in constants]
    def wrong_pack(_):
        packed = np.asarray([value.value.item() for value in constants])
        return packed[::-1] if packed[0] == 11+13j else packed
    monkeypatch.setattr(fem, "pack_constants", wrong_pack)
    with pytest.raises(ValueError, match="map"):
        loaded_surface_kernel_identity(form, compiled, code, semantic)
    assert all(np.array_equal(value.value, old) for value, old in zip(constants, before, strict=True))


def test_failed_mode_diagnostics_preserve_finite_values_and_mark_nonfinite():
    import json
    payload = _failure_diagnostic({"status": "FAILED_LIVE_COMPONENT_GATE", "full_case_pass": False,
        "completed_per_mode": [{"index": 0, "defect": 1e-14}],
        "current_mode_diagnostics": {"index": 1, "finite_error": 1e-11, "nonfinite_error": np.nan,
                                    "phase": complex(np.inf, -np.inf)}})
    encoded = json.dumps(payload, allow_nan=False)
    decoded = json.loads(encoded)
    assert decoded["completed_per_mode"] == [{"index": 0, "defect": 1e-14}]
    assert decoded["current_mode_diagnostics"]["finite_error"] == 1e-11
    assert decoded["current_mode_diagnostics"]["nonfinite_error"] == {"measurement_status": "NONFINITE", "kind": "nan"}
    assert decoded["current_mode_diagnostics"]["phase"]["measurement_status"] == "NONFINITE_COMPLEX"
    assert decoded["status"] == "FAILED_LIVE_COMPONENT_GATE" and decoded["full_case_pass"] is False
