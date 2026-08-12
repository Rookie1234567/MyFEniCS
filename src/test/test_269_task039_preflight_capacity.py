"""Pure Task39 A0 capacity calculator contracts; no formal record or solver."""

from pathlib import Path
from hashlib import sha256

import pytest

from src.io.input_loader import InputError
from src.io.input_validation import load_and_resolve
from src.io.resolved_config import canonical_json_bytes
from benchmarks.task039_preflight_capacity import build_task039_capacity_snapshot


ROOT = Path(__file__).resolve().parents[2]
TASK039 = ROOT / "input" / "official" / "task039"


def test_task039_capacity_snapshot_reuses_exact_inventory_and_historical_carriers():
    specification = load_and_resolve(TASK039 / "5nm_p6h10_full3d_direct_mpi8.dat")
    snapshot = build_task039_capacity_snapshot(
        specification,
        verified_clean_source_sha="a" * 40,
        capacity_snapshot={"classification": "not_run"},
        abi_snapshot={"classification": "not_run"},
    )

    inventory = snapshot["external_mode_inventory"]
    keys = [
        (key["side"], key["m"], key["n"], key["polarization"])
        for key in inventory["keys"]
    ]
    assert inventory["count"] == 604
    assert len(keys) == len(set(keys)) == len(inventory["modes"])
    assert {key[0] for key in keys} == {"bottom", "top"}
    assert any(key[1:3] == (0, 0) for key in keys)
    assert inventory["counts"]["per_side"] == {"bottom": 300, "top": 304}
    assert inventory["counts"]["unique_spatial_mn_per_side"] == {
        "bottom": 150,
        "top": 152,
    }
    assert inventory["counts"]["polarization_per_side"] == {
        "bottom": {"S": 150, "P": 150},
        "top": {"S": 152, "P": 152},
    }
    assert inventory["counts"]["propagating"] == 604
    assert inventory["counts"]["nonpropagating"] == 0
    assert inventory["counts"]["rayleigh_warning"] == 0
    assert (
        snapshot["external_mode_inventory_sha256"]
        == sha256(canonical_json_bytes(inventory)).hexdigest()
    )

    geometry = snapshot["inherited_geometry_topology"]
    assert geometry["classification"] == "inherited_measured"
    assert geometry["path"] == (
        "benchmarks/cases/095_high_order_local_hp_resource_envelope/records/"
        "global_hexa_p1_p6_h10_p6_assembly_time_condensed_independent_mpi8.json"
    )
    assert geometry["record_sha256"] == (
        "96ac3949efc236393d4c2dbc6e1fa334ad5ccb0e9796bdeba13fbe0515577dd8"
    )
    assert geometry["values"] == {
        "cells": 252,
        "full_fe_dofs": 173802,
        "active_trace_rows": 51192,
        "old_auxiliary_rows": 80,
        "old_total_rows": 51272,
        "old_matrix_nnz": 41989040.0,
    }
    hybrid = snapshot["inherited_hybrid_topology"]
    assert hybrid["classification"] == "inherited_measured"
    assert hybrid["path"] == (
        "benchmarks/artifacts/task037c/final_e87d096/r3_direct_phi_0_m120/"
        "run/solver_record.json"
    )
    assert hybrid["record_sha256"] == (
        "ab9d54e52410d0b59f2a75abd459f79da415237b6de84d63e14fea1e15204f44"
    )
    assert (
        hybrid["values"]["bottom"]
        == hybrid["values"]["top"]
        == {
            "full_fe_rows": 25986,
            "trace_rows_before_constraints": 9786,
            "active_trace_rows": 8424,
            "cell_interior_rows": 16200,
            "floquet_slave_rows": 1362,
            "old_external_auxiliary_rows": 40,
            "old_local_algebra_rows": 8464,
        }
    )
    assert snapshot["source_path"] == (
        "input/official/task039/5nm_p6h10_full3d_direct_mpi8.dat"
    )
    assert not snapshot["source_path"].startswith("/")


def test_task039_capacity_snapshot_derived_estimates_are_explicit():
    specification = load_and_resolve(TASK039 / "5nm_p6h10_full3d_direct_mpi8.dat")
    snapshot = build_task039_capacity_snapshot(specification)
    derived = snapshot["derived_estimates"]

    assert derived["full3d"]["classification"] == "derived_estimate"
    assert derived["full3d"]["rows"] == 51796
    assert derived["full3d"]["nnz"] == 42913900
    assert derived["full3d"]["formula"]["base_fe_nnz"] == 41847840
    assert derived["full3d"]["formula"]["per_auxiliary_channel_topology_nnz"] == 1765
    assert (
        derived["full3d"]["formula"]["per_auxiliary_channel_topology_classification"]
        == "derived_estimate"
    )
    assert (
        "095 carrier does not measure"
        in derived["full3d"]["formula"]["per_auxiliary_channel_topology_source"]
    )

    sides = derived["hybrid"]["sides"]
    assert sides["bottom"]["local_algebra_rows"] == 8724
    assert sides["top"]["local_algebra_rows"] == 8728
    assert sides["bottom"]["W_bytes_complex128"] == 40435200
    assert sides["top"]["W_bytes_complex128"] == 40974336
    assert sides["bottom"]["K_bytes_complex128"] == 1440000
    assert sides["top"]["K_bytes_complex128"] == 1478656
    assert derived["hybrid"]["total_W_bytes_complex128"] == 81409536
    assert derived["hybrid"]["total_K_bytes_complex128"] == 2918656
    assert derived["hybrid"]["classification"] == "derived_estimate"


def test_task039_capacity_calculator_rejects_ordinary_input():
    ordinary = load_and_resolve(ROOT / "input/templates/full3d_direct_example.dat")
    iterative = load_and_resolve(TASK039 / "5nm_p6h10_full3d_iterative_mpi8.dat")

    with pytest.raises(InputError, match="only task039_5nm"):
        build_task039_capacity_snapshot(ordinary)
    with pytest.raises(InputError, match="only task039_5nm_full3d_direct"):
        build_task039_capacity_snapshot(iterative)
