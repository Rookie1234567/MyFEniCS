from __future__ import annotations

import importlib.util
import inspect
import json
from pathlib import Path
from types import MappingProxyType

import numpy as np
import pytest

SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "docs/task40para_phi90_mesh_modes_direct/scripts/d13_saved_field_port_action_only.py"
)
SPEC = importlib.util.spec_from_file_location("task40_d13_action_only", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _rows() -> list[dict[str, object]]:
    target = list(MODULE.TARGET_KEYS)
    rows = [
        {"mode_index": i, "side": side, "m": m, "n": n, "polarization": pol}
        for i, (side, m, n, pol) in enumerate(target)
    ]
    rows.extend(
        {"mode_index": i + len(rows), "side": "top", "m": 100 + i, "n": 100, "polarization": "s"}
        for i in range(606)
    )
    return rows


def _rows_at_frozen_indices() -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    indexed = {
        index: key for index, key in zip(MODULE.TARGET_PARENT_INDICES, MODULE.TARGET_KEYS, strict=True)
    }
    parents = [
        {"mode_index": i, "side": "top", "m": 1000 + i, "n": 1000, "polarization": "s"}
        for i in range(612)
    ]
    for index, (side, m, n, polarization) in indexed.items():
        parents[index] = {
            "mode_index": index, "side": side, "m": m, "n": n, "polarization": polarization
        }
    auxiliary = [
        {"auxiliary_index": i, "side": row["side"], "m": row["m"], "n": row["n"], "polarization": row["polarization"]}
        for i, row in enumerate(parents)
    ]
    return parents, auxiliary


def test_only_six_exact_saved_mode_keys_are_selected_in_parent_order():
    rows = _rows()
    rows[0]["mode_index"] = 19
    rows[1]["mode_index"] = 2
    selected = MODULE.select_target_rows(rows)
    assert len(selected) == 6
    assert [row["mode_index"] for row in selected] == sorted(row["mode_index"] for row in selected)
    assert {MODULE.mode_key(row) for row in selected} == set(MODULE.TARGET_KEYS)


def test_target_selection_rejects_missing_or_duplicate_mode():
    rows = _rows()
    rows.pop(0)
    rows.append({"mode_index": 999, "side": "top", "m": 99, "n": 99, "polarization": "s"})
    with pytest.raises(ValueError, match="lacks target keys"):
        MODULE.select_target_rows(rows)
    rows = _rows()
    rows[-1] = dict(rows[0])
    with pytest.raises(ValueError, match="duplicate saved target"):
        MODULE.select_target_rows(rows)


def test_exact_signed_parent_and_auxiliary_keys_bind_the_frozen_indices():
    parent_rows, auxiliary_rows = _rows_at_frozen_indices()
    pairs = MODULE.bind_exact_signed_mode_rows(parent_rows, auxiliary_rows)
    assert [int(parent["mode_index"]) for parent, _ in pairs] == [17, 152, 289, 323, 458, 595]
    assert [MODULE.mode_key(parent) for parent, _ in pairs] == list(MODULE.TARGET_KEYS)
    assert [int(aux["auxiliary_index"]) for _, aux in pairs] == [17, 152, 289, 323, 458, 595]


@pytest.mark.parametrize("damage", ["signed_key_swapped", "index_swapped", "unsigned_key"])
def test_exact_signed_pairing_rejects_pm4_mixing_and_index_drift(damage):
    parent_rows, auxiliary_rows = _rows_at_frozen_indices()
    if damage == "signed_key_swapped":
        auxiliary_rows[17]["m"] = 4
    elif damage == "index_swapped":
        auxiliary_rows[17]["auxiliary_index"] = 289
    else:
        auxiliary_rows[17].pop("m")
    with pytest.raises(ValueError, match="signed|index|duplicate"):
        MODULE.bind_exact_signed_mode_rows(parent_rows, auxiliary_rows)


def test_exact_signed_pairing_rejects_wrong_parent_index():
    parent_rows, auxiliary_rows = _rows_at_frozen_indices()
    parent_rows[17]["mode_index"] = 289
    with pytest.raises(ValueError, match="frozen parent index"):
        MODULE.bind_exact_signed_mode_rows(parent_rows, auxiliary_rows)


def test_failed_gate_projection_capture_keeps_no_carrier_status_and_scope():
    parent_rows, auxiliary_rows = _rows_at_frozen_indices()
    pairs = MODULE.bind_exact_signed_mode_rows(parent_rows, auxiliary_rows)
    assert len(pairs) == 6
    gate = MODULE.carrier_comparison_gate(
        data_finite=True,
        global_roundtrip_relative=1e-13,
        maximum_cell_roundtrip_relative=1e-13,
        shared_trace_relative=1e-13,
        maximum_facet_trace_relative=2e-4,
        mpc_backsubstitution_relative=1e-13,
    )
    calls = []
    result = MODULE.preserve_no_carrier_diagnostic(
        {"projection_comparisons": [], "assembled_carrier_mode_count": 0},
        gate,
        lambda: calls.append("six scalar mode projections") or {"status": "captured"},
    )
    assert calls == ["six scalar mode projections"]
    assert result["status"] == "NO_CARRIER_COMPARISON"
    assert result["qualification"] == "DIAGNOSTIC_ONLY_NOT_CARRIER_OR_FIELD_QUALIFICATION"
    assert result["assembled_carrier_mode_count"] == 0
    assert result["projection_comparisons"] == []
    assert result["diagnostic_only_signed_key_projection_capture"]["status"] == "captured"


def test_diagnostic_capture_never_builds_carrier_even_if_frozen_gate_passes():
    calls = []
    case = {"projection_comparisons": [], "assembled_carrier_mode_count": 0}
    gate = MODULE.carrier_comparison_gate(**_passing_compatibility_metrics())
    result = MODULE.preserve_no_carrier_diagnostic(
        case,
        gate,
        lambda: calls.append("diagnostic capture") or {"status": "captured"},
    )
    assert calls == ["diagnostic capture"]
    assert gate["passed"] is True
    assert result["status"] == "CARRIER_GATE_PASSED_BUT_CARRIER_NOT_BUILT_DIAGNOSTIC_ONLY"
    assert result["assembled_carrier_mode_count"] == 0
    assert result["projection_comparisons"] == []


def test_complex_pair_decoder_and_relative_compare_keep_complex_phase():
    assert MODULE.decode_complex([1.25, -2.5]) == complex(1.25, -2.5)
    assert MODULE.decode_complex({"real": 1.25, "imag": -2.5}) == complex(1.25, -2.5)
    assert MODULE.relative_difference(1.0 + 2.0j, 1.0 - 2.0j) > 0.0


def test_cell_local_point_match_tracks_permutation_and_rejects_nonbijection():
    xyz = np.asarray([[0.0, 0.0, 0.0], [0.0, 1.0, 0.0], [1.0, 0.0, 0.0]])
    permutation = np.asarray([2, 0, 1])
    mapping, error = MODULE.match_cell_points(xyz, xyz[permutation], 1.0e-12)
    assert mapping.tolist() == permutation.tolist()
    assert error == 0.0
    with pytest.raises(ValueError, match="not one-to-one"):
        MODULE.match_cell_points(xyz, np.asarray([[0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [1.0, 0.0, 0.0]]), 1.0e-12)
    with pytest.raises(ValueError, match="mismatch"):
        MODULE.match_cell_points(xyz, xyz + 1.0, 1.0e-12)


def test_zero_slave_storage_copies_and_changes_only_slave_entries():
    source = np.asarray([1 + 2j, 3 - 4j, 5 + 6j], dtype=np.complex128)
    result = MODULE.zero_slave_storage(source, [1])
    assert np.array_equal(source, np.asarray([1 + 2j, 3 - 4j, 5 + 6j]))
    assert np.array_equal(result, np.asarray([1 + 2j, 0j, 5 + 6j]))
    with pytest.raises(ValueError, match="outside"):
        MODULE.zero_slave_storage(source, [3])
    with pytest.raises(ValueError, match="unique"):
        MODULE.zero_slave_storage(source, [1, 1])


def test_contract_binds_exact_y2_y3_scope_and_six_modes(tmp_path: Path):
    mode_sha = "a" * 64
    case = {
        "case": "Y2-primary",
        "run_id": "task40_phi90_13p5_D13_Y2_p6_direct_v1",
        "run_directory_id": "20261016T112452.011352Z",
        "parent_mode_count": 612,
        "mode_sha256": mode_sha,
        "surface_quadrature_degree": 28,
        "selected_keys": [list(key) for key in MODULE.TARGET_KEYS],
        "selected_parent_indices": list(MODULE.TARGET_PARENT_INDICES),
        "diagnostic_only_signed_key_capture": True,
    }
    control = dict(
        case,
        case="Y3-control",
        run_id="task40_phi90_13p5_D13_Y3_p6_direct_v1",
        run_directory_id="20261016T122621.622353Z",
    )
    contract = {
        "schema": "task40.d13.signed-key-surface-capture-contract.v1",
        "scope": "Y2_Y3_six_signed_key_projection_diagnostic_no_carrier_no_solve",
        "diagnostic_only_no_carrier": True,
        "expected_parent_mode_sha256": mode_sha,
        "cases": [case, control],
    }
    path = tmp_path / "contract.json"
    path.write_text(json.dumps(contract))
    assert len(MODULE._load_contract(path)["cases"]) == 2

    contract["cases"] = [case, control, dict(control, case="Y4-control")]
    path.write_text(json.dumps(contract))
    with pytest.raises(ValueError, match="exactly the Y2 primary and Y3 same-key control"):
        MODULE._load_contract(path)

    contract["cases"] = [case, dict(control, selected_keys=[["top", 99, 0, "p"]])]
    path.write_text(json.dumps(contract))
    with pytest.raises(ValueError, match="six-key scope"):
        MODULE._load_contract(path)

    contract["cases"] = [case, control]
    contract["diagnostic_only_no_carrier"] = False
    path.write_text(json.dumps(contract))
    with pytest.raises(ValueError, match="forbid carrier construction"):
        MODULE._load_contract(path)


def test_jsonable_preserves_complex_mapping_and_numpy_values():
    value = MappingProxyType(
        {
            "array": np.asarray([1 + 2j, 3 - 4j], dtype=np.complex128),
            "scalar": np.float64(2.5),
            "pair": 5 - 6j,
        }
    )
    serialized = MODULE._jsonable(value)
    assert serialized == {
        "array": [{"real": 1.0, "imag": 2.0}, {"real": 3.0, "imag": -4.0}],
        "scalar": 2.5,
        "pair": {"real": 5.0, "imag": -6.0},
    }


def _passing_compatibility_metrics():
    return {
        "data_finite": True,
        "global_roundtrip_relative": 2.0e-13,
        "maximum_cell_roundtrip_relative": 8.0e-13,
        "shared_trace_relative": 3.0e-13,
        "maximum_facet_trace_relative": 9.0e-13,
        "mpc_backsubstitution_relative": 1.0e-13,
    }


@pytest.mark.parametrize(
    "override, failed_check",
    [
        ({"global_roundtrip_relative": 2.0e-10}, "global_DG6_roundtrip_relative"),
        ({"maximum_cell_roundtrip_relative": 2.0e-10}, "maximum_cell_DG6_roundtrip_relative"),
        ({"shared_trace_relative": 2.0e-10}, "global_unaveraged_shared_tangential_trace_relative"),
        ({"maximum_facet_trace_relative": 2.0e-10}, "maximum_facet_unaveraged_tangential_trace_relative"),
        ({"mpc_backsubstitution_relative": 2.0e-10}, "MPC_zero_slave_backsubstitution_relative"),
        ({"data_finite": False}, "input_or_reconstruction_nonfinite"),
        ({"global_roundtrip_relative": np.nan}, "global_DG6_roundtrip_relative"),
        ({"maximum_facet_trace_relative": np.inf}, "maximum_facet_unaveraged_tangential_trace_relative"),
    ],
)
def test_each_roundtrip_trace_or_mpc_failure_skips_carrier_builder(override, failed_check):
    metrics = _passing_compatibility_metrics() | override
    gate = MODULE.carrier_comparison_gate(**metrics)
    calls = []
    carrier = MODULE.build_carrier_if_compatible(gate, lambda: calls.append("carrier") or object())
    assert gate["passed"] is False
    assert failed_check in gate["failed_checks"]
    assert carrier is None
    assert calls == []


def test_carrier_builder_runs_only_after_all_compatibility_witnesses_pass():
    gate = MODULE.carrier_comparison_gate(**_passing_compatibility_metrics())
    calls = []
    token = object()
    assert gate["passed"] is True
    assert MODULE.build_carrier_if_compatible(gate, lambda: calls.append("carrier") or token) is token
    assert calls == ["carrier"]


def test_facet_metrics_keep_absolute_error_and_near_zero_scale_separate():
    facts = MODULE._facet_tangential_metrics(
        np.asarray([1.0e-20 + 0j]),
        np.asarray([0j]),
        np.asarray([0j]),
    )
    assert facts["finite"] is True
    assert facts["jump_l2"] == 1.0e-20
    assert facts["scale_l2"] == 0.0
    assert facts["relative_denominator"] == np.finfo(float).tiny
    assert facts["relative_l2"] > 1.0e-10
    nonfinite = MODULE._facet_tangential_metrics(
        np.asarray([np.inf + 0j]), np.asarray([1 + 0j]), np.asarray([1 + 0j])
    )
    assert nonfinite["finite"] is False
    assert nonfinite["jump_l2"] is None


def test_complex_vtu_reconstruction_rejects_real_dolfinx_scalar_type():
    assert MODULE._require_complex_scalar_type(np.complex128) is np.complex128
    with pytest.raises(TypeError, match="complex DOLFINx scalar"):
        MODULE._require_complex_scalar_type(np.float64)


def test_real_basix_dg6_metadata_dtype_is_separate_from_complex_function_dtype():
    import basix
    from basix.ufl import element
    from dolfinx import default_scalar_type, fem

    basis_dtype, function_dtype = MODULE._dg6_dtype_pair(np.dtype(np.float64), default_scalar_type)
    dg6 = element("DG", basix.CellType.hexahedron, 6, shape=(3,), dtype=basis_dtype)
    assert np.dtype(dg6.dtype) == np.dtype(np.float64)
    assert np.dtype(function_dtype) == np.dtype(np.complex128)
    assert "dtype" in inspect.signature(fem.Function).parameters


def test_dg6_wiring_uses_mesh_geometry_dtype_for_basix_and_complex_for_function():
    class FakeMesh:
        geometry = type("Geometry", (), {"x": np.empty((0, 3), dtype=np.float64)})()

        @staticmethod
        def basix_cell():
            return "hexahedron"

    class FakeField:
        def __init__(self, space, *, name, dtype):
            self.space = space
            self.name = name
            self.dtype = np.dtype(dtype)
            self.x = type("Vector", (), {"array": np.empty(2, dtype=dtype)})()

    class FakeFem:
        @staticmethod
        def functionspace(mesh, dg_element):
            return (mesh, dg_element)

        Function = FakeField

    element_calls = []

    def element_factory(family, cell, degree, *, shape, dtype):
        element_calls.append((family, cell, degree, shape, np.dtype(dtype)))
        return object()

    space, field, basis_dtype, function_dtype = MODULE._build_complex_dg6_field(
        FakeMesh(), FakeFem, element_factory, np.complex128
    )
    assert element_calls == [("DG", "hexahedron", 6, (3,), np.dtype(np.float64))]
    assert space[1] is not None
    assert basis_dtype == np.dtype(np.float64)
    assert function_dtype is np.complex128
    assert field.dtype == np.dtype(np.complex128)
    field.x.array[:] = 1.25 - 2.5j
    assert np.array_equal(field.x.array, np.asarray([1.25 - 2.5j] * 2, dtype=np.complex128))


def test_mode_selection_report_is_not_labeled_sparse_row_cutoff_evidence():
    facts = MODULE.mode_selection_scope_facts()
    assert facts["saved_parent_modes"] == 612
    assert facts["explicitly_assembled_target_modes"] == 6
    assert facts["other_parent_modes_not_evaluated_by_this_diagnostic"] == 606
    assert facts["sparse_row_cutoff_before_after_evidence"] == "NOT_MEASURED"
