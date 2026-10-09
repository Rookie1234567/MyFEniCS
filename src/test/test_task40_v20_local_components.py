from __future__ import annotations

import json
import hashlib

import numpy as np
import pytest

from src.runners import physical_diagnosis_worker
from src.solvers.task40_v20_local_components import (
    _array_sha256,
    _save_component_packet,
    _validate_reused_local_prefix,
    verify_v20_saved_c00_packet,
    verify_v20_saved_local_component_packet,
)


def _sample_arrays():
    return {
        "matrix": np.arange(12, dtype=np.complex128).reshape(3, 4) * (1 + 2j),
        "rhs": np.asarray([2 + 3j, 5 - 7j], dtype=np.complex128),
    }


def test_v20_component_packet_round_trips_business_names_to_npz_keys(tmp_path):
    arrays = _sample_arrays()

    receipt = _save_component_packet(
        tmp_path,
        "roundtrip",
        {"purpose": "real save_packet readback fixture"},
        arrays,
    )

    record = json.loads((tmp_path / "roundtrip.json").read_text(encoding="utf-8"))
    descriptors = record["raw_arrays"]
    assert set(descriptors) == set(arrays)
    assert {item["array_key"] for item in descriptors.values()} == {
        "array_0",
        "array_1",
    }
    assert set(receipt["arrays"]) == set(arrays)
    assert receipt["write_and_readback_hash_passed"] is True
    with np.load(tmp_path / "roundtrip.npz", allow_pickle=False) as archive:
        assert set(archive.files) == {item["array_key"] for item in descriptors.values()}
        for name, expected in arrays.items():
            descriptor = descriptors[name]
            actual = archive[descriptor["array_key"]]
            assert actual.shape == expected.shape
            assert actual.dtype == expected.dtype
            assert _array_sha256(actual) == _array_sha256(expected)
            assert receipt["arrays"][name]["sha256"] == _array_sha256(expected)


@pytest.mark.parametrize("corruption", ["omitted", "duplicate"])
def test_v20_component_packet_rejects_incomplete_or_reused_array_keys(
    tmp_path, monkeypatch, corruption
):
    save_packet = physical_diagnosis_worker.save_packet

    def save_then_corrupt(directory, name, facts):
        save_packet(directory, name, facts)
        path = directory / f"{name}.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        if corruption == "omitted":
            record["raw_arrays"].pop("rhs")
        else:
            record["raw_arrays"]["rhs"]["array_key"] = record["raw_arrays"]["matrix"][
                "array_key"
            ]
        path.write_text(json.dumps(record), encoding="utf-8")

    monkeypatch.setattr(physical_diagnosis_worker, "save_packet", save_then_corrupt)
    with pytest.raises(RuntimeError, match="inventory|repeated"):
        _save_component_packet(
            tmp_path,
            "corrupt",
            {},
            _sample_arrays(),
        )


def test_v20_saved_c00_reuse_replays_matrix_schur_and_full_recovery_equations(tmp_path):
    Vii = np.diag(np.asarray([2.0, 3.0], dtype=np.complex128))
    Vit = np.asarray([[1.0], [2.0]], dtype=np.complex128)
    Vti = np.asarray([[1.0, 2.0]], dtype=np.complex128)
    Vtt = np.asarray([[8.0]], dtype=np.complex128)
    xi = np.asarray([0.5, -0.25], dtype=np.complex128)
    xt = np.asarray([2.0], dtype=np.complex128)
    solved = np.linalg.solve(Vii, Vit)
    solved_xt = np.linalg.solve(Vii, Vit @ xt)
    full_rhs = Vii @ xi + Vit @ xt
    reduced_rhs = full_rhs - Vit @ xt
    arrays = {
        "Vii": Vii,
        "Vit": Vit,
        "Vti": Vti,
        "Vtt": Vtt,
        "Schur": Vtt - Vti @ solved,
        "known_xi": xi,
        "known_xt": xt,
        "interior_rhs": reduced_rhs,
        "recovered_xi": xi,
        "solved_Vit": solved,
        "solved_Vit_xt": solved_xt,
    }
    inventory = {
        "named_array_payload_bytes_with_aliases": 4096,
        "unique_backing_bytes": 3072,
    }
    facts = {
        "class_id": "c00",
        "status": "PASS",
        "passed": True,
        "gates": {"local_equation": True, "forward": True},
        "metric_identity": {"cell_permutation": 0},
        "material_tag": 1,
        "target_cell_count": 1,
        "filled_reference_cell_count": 1,
        "array_inventory": inventory,
    }
    packet = _save_component_packet(tmp_path, "v20_local_c00", facts, arrays)
    packet_json = tmp_path / "v20_local_c00.json"
    packet_npz = tmp_path / "v20_local_c00.npz"
    json_sha = hashlib.sha256(packet_json.read_bytes()).hexdigest()
    npz_sha = hashlib.sha256(packet_npz.read_bytes()).hexdigest()
    receipt = {
        "classification": "SUPPLEMENTAL_ARTIFACT_READBACK_ONLY",
        "json_sha256": json_sha,
        "archive_sha256": npz_sha,
        "current_source_head": "a" * 40,
        "run_directory": str(tmp_path.resolve()),
        "per_array_expected_hash_basis": (
            "loaded from preserved NPZ for key-mapping integrity replay; not an independent pre-save hash"
        ),
        "readback": packet,
    }
    receipt_path = tmp_path / "readback_receipt.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    receipt_sha = hashlib.sha256(receipt_path.read_bytes()).hexdigest()

    reused, validation = verify_v20_saved_c00_packet(
        tmp_path,
        receipt_path,
        expected_json_sha256=json_sha,
        expected_npz_sha256=npz_sha,
        expected_readback_receipt_sha256=receipt_sha,
    )

    assert reused["class_id"] == "c00"
    assert reused["raw_packet"]["write_and_readback_hash_passed"] is True
    assert validation["passed"] is True
    assert validation["independent_matrix_and_recovery_replay"][
        "recovery_full_original_equation_relative"
    ] < 1.0e-14
    assert validation["independent_matrix_and_recovery_replay"][
        "recovery_reduced_original_equation_relative"
    ] < 1.0e-14


def test_v20_saved_non_c00_packet_replays_original_equations_and_hashes(tmp_path):
    Vii = np.diag(np.asarray([2.0, 3.0], dtype=np.complex128))
    Vit = np.asarray([[1.0], [2.0]], dtype=np.complex128)
    Vti = np.asarray([[1.0, 2.0]], dtype=np.complex128)
    Vtt = np.asarray([[8.0]], dtype=np.complex128)
    xi = np.asarray([0.5, -0.25], dtype=np.complex128)
    xt = np.asarray([2.0], dtype=np.complex128)
    solved = np.linalg.solve(Vii, Vit)
    solved_xt = np.linalg.solve(Vii, Vit @ xt)
    reduced_rhs = Vii @ xi
    arrays = {
        "Vii": Vii,
        "Vit": Vit,
        "Vti": Vti,
        "Vtt": Vtt,
        "Schur": Vtt - Vti @ solved,
        "known_xi": xi,
        "known_xt": xt,
        "interior_rhs": reduced_rhs,
        "recovered_xi": xi,
        "solved_Vit": solved,
        "solved_Vit_xt": solved_xt,
    }
    facts = {
        "class_id": "c01",
        "status": "PASS",
        "passed": True,
        "gates": {"matrix_equations": True, "recovery": True},
        "interior_rows": 2,
        "trace_rows": 1,
        "interior_factor_identity_relative": 0.0,
    }
    packet = _save_component_packet(tmp_path, "v20_local_c01", facts, arrays)
    packet_json = tmp_path / "v20_local_c01.json"
    packet_npz = tmp_path / "v20_local_c01.npz"
    expected = dict(facts, raw_packet=packet)
    json_sha = hashlib.sha256(packet_json.read_bytes()).hexdigest()
    npz_sha = hashlib.sha256(packet_npz.read_bytes()).hexdigest()

    row, validation = verify_v20_saved_local_component_packet(
        tmp_path,
        expected,
        expected_json_sha256=json_sha,
        expected_npz_sha256=npz_sha,
    )

    replay = validation["independent_matrix_and_recovery_replay"]
    assert row["saved_packet_independent_readback"]["passed"] is True
    assert replay["recorded_reduced_rhs_relative"] < 1.0e-14
    assert replay["Vii_inverse_Vit_xt_original_equation_relative"] < 1.0e-14
    assert replay["recovery_full_original_equation_relative"] < 1.0e-14
    with pytest.raises(RuntimeError, match="NPZ hash differs"):
        verify_v20_saved_local_component_packet(
            tmp_path,
            expected,
            expected_json_sha256=json_sha,
            expected_npz_sha256="0" * 64,
        )


def test_v20_complete_local_prefix_uses_only_metadata_and_full_port_dimensions(
    tmp_path, monkeypatch
):
    from src.solvers import directional_boundary, task40_w1_local_probe
    from src.solvers import task40_v20_local_components as local_components

    axis_coordinates = tuple(np.asarray([0.0, 1.0]) for _ in range(3))
    axis_hashes = [
        hashlib.sha256(np.ascontiguousarray(axis).tobytes()).hexdigest()
        for axis in axis_coordinates
    ]
    geometry_classes = []
    completed_rows = []
    for index in range(60):
        class_id = f"c{index:02d}"
        metric = {"identity": index}
        geometry_classes.append(
            {
                "class_id": class_id,
                "metric_identity": metric,
                "material_tag": 1,
                "target_cell_count": 1,
                "filled_reference_cell_count": 1,
            }
        )
        completed_rows.append(
            {
                "class_id": class_id,
                "metric_identity": metric,
                "material_tag": 1,
                "target_cell_count": 1,
                "filled_reference_cell_count": 1,
                "status": "PASS",
                "passed": True,
                "gates": {"saved_local_component": True},
                "saved_packet_independent_readback": {"passed": True},
                "interior_rows": 450,
                "trace_rows": 432,
                "local_lu_factor_count": 1,
            }
        )
    mode_rows = tuple(
        {"mode_index": index, "alpha": 0.0, "gamma": 0.0, "m": 0, "n": 0}
        for index in range(32060)
    )
    boundary_rows = [
        {
            "side": side,
            "cell_id": index,
            "facet_id": index,
            "material_tag": 1,
            "cell_permutation": 0,
            "bounds_nm": ((0.0, 1.0), (0.0, 1.0), (float(index), float(index + 1))),
            "face_i": 0,
            "face_j": 0,
        }
        for index, side in enumerate(("bottom", "top"))
    ]
    geometry_facts = {
        "actual_axes": [1, 1, 1],
        "vertex_axis_coordinate_counts": [2, 2, 2],
        "axis_coordinate_sha256": axis_hashes,
        "periodic_face_inventory": {"boundary_face_cells": boundary_rows},
    }
    resolved = {
        "execution": {
            "task40_mode_manifest_sha256": "a" * 64,
            "task40_mode_key_sha256": "b" * 64,
        }
    }
    metadata_sentinel = object()
    metadata_calls = []
    measurement_calls = []
    port_calls = []

    def build_metadata():
        metadata_calls.append(True)
        return metadata_sentinel

    def forbidden_measurement(*_args, **_kwargs):
        measurement_calls.append(True)
        raise AssertionError("a complete prefix must not remeasure local FE classes")

    class StubFacetPolynomial:
        def __init__(self, element):
            assert element is metadata_sentinel

    class StubBoundaryLayout:
        rows = 9999

        def __init__(self, *_args):
            pass

    def stream_stub(**kwargs):
        assert len(kwargs["modes"]) == 32060
        assert kwargs["modes"][0] == mode_rows[0]
        assert kwargs["modes"][-1] == mode_rows[-1]
        assert kwargs["trace_values"].shape == (432,)
        assert kwargs["known_interior_solution"].shape == (450,)
        port_calls.append((kwargs["side"], len(kwargs["modes"])))
        return {
            "local_recovery_equation_relative": 0.0,
            "local_original_trace_equation_relative": 0.0,
            "local_reduced_trace_equation_relative": 0.0,
            "local_trace_elimination_identity_relative": 0.0,
            "local_port_equation_relative": 0.0,
            "local_reduced_port_equation_relative": 0.0,
            "local_port_elimination_identity_relative": 0.0,
            "known_interior_solution_relative": 0.0,
            "local_vii_factorization_count": 1,
            "small_key_native_carrier_witness": {
                "direct_trace_B_relative": 0.0,
                "direct_trace_D_relative": 0.0,
                "full_dof_direct_q30_B_relative": 0.0,
                "full_dof_direct_q30_D_relative": 0.0,
                "full_dof_direct_q30_gate_pass": True,
            },
            "arrays": {"stub": np.zeros(1, dtype=np.complex128)},
        }

    monkeypatch.setattr(local_components, "_build_p6_basix_element_metadata", build_metadata)
    monkeypatch.setattr(local_components, "_local_class_measurement", forbidden_measurement)
    monkeypatch.setattr(directional_boundary, "FacetPolynomial", StubFacetPolynomial)
    monkeypatch.setattr(directional_boundary, "BoundaryLayout", StubBoundaryLayout)
    monkeypatch.setattr(task40_w1_local_probe, "stream_boundary_correction", stream_stub)
    report = local_components.run_v20_local_port_components(
        resolved,
        tmp_path,
        axis_coordinates=axis_coordinates,
        cfg=type("Config", (), {"period_x": 1.0, "period_y": 1.0})(),
        geometry_facts=geometry_facts,
        classes=geometry_classes,
        mode_rows=mode_rows,
        resource_sample=lambda: {},
        completed_local_rows=completed_rows,
        reused_packet_validation={"passed": True},
    )

    assert metadata_calls == [True]
    assert measurement_calls == []
    assert port_calls == [("bottom", 32060), ("top", 32060)]
    assert report["reused_local_class_ids"] == [f"c{index:02d}" for index in range(60)]
    assert report["status"] == "PASS"
    assert report["global_p6_space_created"] is False
    assert report["global_MPC_created"] is False
    assert report["all_q_csr_created"] is False
    assert report["local_lu_factor_count"] == 60
    assert report["reused_local_class_lu_factor_count"] == 60
    assert report["reused_local_class_count"] == 60
    assert report["new_local_class_measurement_count"] == 0
    assert report["new_local_class_lu_factor_count"] == 0
    assert report["new_port_local_vii_factorization_count"] == 2
    assert report["new_port_factorization_observed_side_count"] == 2
    assert report["new_port_factorization_unknown_side_count"] == 0


def test_v20_reused_local_prefix_rejects_a_wrong_class_identity():
    classes = [
        {
            "class_id": "c00",
            "metric_identity": {"cell_permutation": 0},
            "material_tag": 1,
            "target_cell_count": 1,
            "filled_reference_cell_count": 1,
        }
    ]
    reused = {
        "class_id": "c01",
        "metric_identity": {"cell_permutation": 0},
        "material_tag": 1,
        "target_cell_count": 1,
        "filled_reference_cell_count": 1,
        "passed": True,
    }
    with pytest.raises(ValueError, match="geometry inventory"):
        _validate_reused_local_prefix(classes, [reused])
