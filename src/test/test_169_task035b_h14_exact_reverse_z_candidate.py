"""Bounded contracts for the Review-V2 A2 h14 exact-reverse point."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from benchmarks.run_task035_actual_r5 import (
    _fixed_trace_resource_preflight,
    _parse_args,
    _worker,
)
from src.adaptivity.high_order_resource_audit import (
    partition_independent_linear_mesh_identity,
)
from src.adaptivity.target_fixed_trace_candidate import (
    _load_directional_parent,
    _load_h13_top_phase_negative,
)
from src.common.config_3d import target_stage4_config
from src.constraints.high_order_floquet_trace import high_order_trace_layout
from src.geometry.mesh_builder_3d import (
    build_airbox_mesh_3d,
    stage4_axis_plan,
)
from src.geometry.research_axis_profiles import (
    TASK035B_H13_TOP_PHASE_REDISTRIBUTION_PROFILE,
    TASK035B_H14_EXACT_REVERSE_TOP2_PROFILE,
    TASK035B_H14_EXACT_REVERSE_TOP2_Z_VALUES_NM,
)


ROOT = Path(__file__).resolve().parents[2]
RECORDS = (
    ROOT
    / "benchmarks"
    / "cases"
    / "095_high_order_local_hp_resource_envelope"
    / "records"
)
H14_PARENT = RECORDS / "fixed_p5trace_p6interior_h14_directional_z_mpi8.json"
H14_PARENT_SHA = (
    "e93f50155b3c8517292794cb9735730ebf738410aecafe00f43f7959c150a127"
)
H13_NEGATIVE = (
    RECORDS
    / "fixed_p5trace_p6interior_h13_top2_phase_redistribution_mpi8_v1.json"
)
H13_NEGATIVE_SHA = (
    "ff12b909aa1c75dcf15246ba48a8169bf9653d13ddf36709c46367217d799b4b"
)
SIGNIFICANT_SHA = (
    "83b7bcfeb510b849aea391d86f306072ead0232781598ea1232617e2535293e3"
)
_SHA = "a" * 64


def _config():
    return replace(
        target_stage4_config(degree=6, h_nm=14.0),
        mesh_axis_cell_counts=(6, 2, 11),
        mesh_axis_z_values=TASK035B_H14_EXACT_REVERSE_TOP2_Z_VALUES_NM,
        mesh_axis_z_profile=TASK035B_H14_EXACT_REVERSE_TOP2_PROFILE,
    )


def _args(*, parent: bool = True, negative: bool = True):
    values = [
        "--coarse-degree",
        "5",
        "--enriched-degree",
        "6",
        "--h-nm",
        "14",
        "--mesh-cell-type",
        "hexahedron",
        "--mpi-size",
        "8",
        "--fixed-trace-control-record",
        "control.json",
        "--fixed-trace-control-sha256",
        _SHA,
        "--fixed-trace-significant-channel-reference-record",
        "significant.json",
        "--fixed-trace-significant-channel-reference-sha256",
        _SHA,
        "--fixed-trace-degree",
        "5",
        "--fixed-interior-degree",
        "6",
        "--fixed-trace-directional-recovery",
        "--fixed-trace-directional-axis",
        "z",
        "--fixed-trace-explicit-z-profile",
        TASK035B_H14_EXACT_REVERSE_TOP2_PROFILE,
    ]
    if parent:
        values.extend(
            [
                "--fixed-trace-directional-parent-record",
                "h14.json",
                "--fixed-trace-directional-parent-sha256",
                _SHA,
            ]
        )
    if negative:
        values.extend(
            [
                "--fixed-trace-reverse-evidence-record",
                "h13-negative.json",
                "--fixed-trace-reverse-evidence-sha256",
                _SHA,
            ]
        )
    return _parse_args(values)


def test_profile_is_the_single_exact_reverse_on_unchanged_h14_topology(
    tmp_path: Path,
) -> None:
    h14 = stage4_axis_plan(
        target_stage4_config(degree=6, h_nm=14.0),
        comm_size=8,
    )
    candidate = stage4_axis_plan(_config(), comm_size=8)
    changed = np.flatnonzero(
        ~np.isclose(candidate.z_values, h14.z_values, rtol=0.0, atol=1e-13)
    )

    assert changed.tolist() == [8, 9]
    assert h14.z_values[8:10].tolist() == [
        93.33333333333334,
        106.66666666666667,
    ]
    assert candidate.z_values[8:10].tolist() == [96.0, 108.0]
    assert np.diff(candidate.z_values)[7:10].tolist() == [16.0, 12.0, 12.0]
    assert candidate.z_values[[0, 1, -2, -1]].tolist() == [
        -10.0,
        0.0,
        120.0,
        130.0,
    ]
    assert candidate.mesh_cells_resolved == h14.mesh_cells_resolved == (
        6,
        2,
        11,
    )
    assert candidate.material_plane_alignment["all_aligned"] is True
    axis_sha = hashlib.sha256(
        json.dumps(
            candidate.z_values.tolist(), separators=(",", ":")
        ).encode()
    ).hexdigest()
    assert axis_sha == (
        "62fa925a820639e4864c6512420acf12b768627fb0f125bc381fbdefde6bbd1d"
    )

    mesh_data = build_airbox_mesh_3d(_config(), tmp_path / "mesh")
    identity = partition_independent_linear_mesh_identity(mesh_data)
    assert identity["global_cell_count"] == 132
    assert identity["partition_independent_mesh_sha256"] == (
        "42b36eb298ec3bb2fcdf227b9ef09edfac999d03133c42985dc69ba6724effaa"
    )
    assert identity["cell_tag_sha256"] == (
        "7fc553a5b926cb83b7c675d3faeb262a54b638247814ef826937b9380772a61a"
    )
    assert identity["facet_tag_sha256"] == (
        "c99bc14ee9c94622bf37c3361f049b8c05f95a6f81e9744d5d7476b6cf3cdca4"
    )
    msh = mesh_data.mesh
    for dimension in range(4):
        msh.topology.create_entities(dimension)
    edges = int(msh.topology.index_map(1).size_global)
    faces = int(msh.topology.index_map(2).size_global)
    cells = int(msh.topology.index_map(3).size_global)
    p5 = high_order_trace_layout(5)
    p6 = high_order_trace_layout(6)
    assert (
        edges * p5.edge_dofs
        + faces * p5.face_interior_dofs
        + cells * p6.cell_interior_dofs
        == 82_315
    )


def test_preflight_binds_both_authorities_and_never_claims_success() -> None:
    args = _args()
    preflight = _fixed_trace_resource_preflight(args)
    contract = preflight["bounded_discriminator_contract"]
    prediction = contract["prior_prediction"]

    assert preflight["pass"] is True
    assert args.mpi_size == 8
    assert args.fixed_trace_directional_parent_record == Path("h14.json")
    assert args.fixed_trace_reverse_evidence_record == Path(
        "h13-negative.json"
    )
    assert preflight["predicted_resources"]["num_mesh_cells"] == 132
    assert preflight["predicted_resources"]["candidate_dofs"] == 82_315
    assert preflight["axis_plan"]["h14_changed_z_indices"] == [8, 9]
    assert contract["unchanged_h14_topology_control_required"] is True
    assert contract["h13_top2_controlled_negative_required"] is True
    assert contract["required_mpi_size"] == 8
    assert contract["swap_allowed"] is False
    assert contract["additional_plane_or_scan_authorized"] is False
    assert prediction["significant_power_pass_count"] == 9
    assert prediction["significant_complex_amplitude_pass_count"] == 11
    assert prediction["formal_success_claimed"] is False
    assert prediction["formal_gate_still_requires_measured_12_plus_12"] is True


@pytest.mark.parametrize(
    ("parent", "negative"),
    ((False, True), (True, False), (False, False)),
)
def test_missing_either_sha_bound_authority_fails_closed(
    parent: bool,
    negative: bool,
) -> None:
    with pytest.raises(SystemExit):
        _args(parent=parent, negative=negative)


def test_single_plane_mutation_and_other_profile_reuse_fail_closed() -> None:
    z_values = list(TASK035B_H14_EXACT_REVERSE_TOP2_Z_VALUES_NM)
    z_values[9] = 106.66666666666667
    with pytest.raises(ValueError, match="frozen explicit z authorities"):
        stage4_axis_plan(
            replace(_config(), mesh_axis_z_values=tuple(z_values)),
            comm_size=8,
        )

    values = [
        argument
        for argument in _worker_args()
        if argument != TASK035B_H14_EXACT_REVERSE_TOP2_PROFILE
    ]
    profile_index = values.index("--fixed-trace-explicit-z-profile") + 1
    values.insert(
        profile_index,
        TASK035B_H13_TOP_PHASE_REDISTRIBUTION_PROFILE,
    )
    with pytest.raises(SystemExit):
        _parse_args(values)


def _worker_args() -> list[str]:
    args = _args()
    values = [
        "--coarse-degree",
        "5",
        "--enriched-degree",
        "6",
        "--h-nm",
        "14",
        "--mesh-cell-type",
        "hexahedron",
        "--mpi-size",
        "8",
        "--fixed-trace-control-record",
        str(args.fixed_trace_control_record),
        "--fixed-trace-control-sha256",
        _SHA,
        "--fixed-trace-significant-channel-reference-record",
        str(args.fixed_trace_significant_channel_reference_record),
        "--fixed-trace-significant-channel-reference-sha256",
        _SHA,
        "--fixed-trace-degree",
        "5",
        "--fixed-interior-degree",
        "6",
        "--fixed-trace-directional-recovery",
        "--fixed-trace-directional-axis",
        "z",
        "--fixed-trace-explicit-z-profile",
        TASK035B_H14_EXACT_REVERSE_TOP2_PROFILE,
        "--fixed-trace-directional-parent-record",
        str(args.fixed_trace_directional_parent_record),
        "--fixed-trace-directional-parent-sha256",
        _SHA,
        "--fixed-trace-reverse-evidence-record",
        str(args.fixed_trace_reverse_evidence_record),
        "--fixed-trace-reverse-evidence-sha256",
        _SHA,
    ]
    return values


def test_worker_forwards_both_sha_bound_authorities_without_pde(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from src.adaptivity import target_fixed_trace_candidate as candidate

    captured = {}

    def fake_run(out_dir, **kwargs):
        captured["out_dir"] = out_dir
        captured.update(kwargs)
        return {"status": "contract_only_no_pde"}

    monkeypatch.setattr(
        candidate, "run_target_fixed_trace_candidate", fake_run
    )
    args = _parse_args(
        [
            *_worker_args(),
            "--worker",
            "--run-dir",
            str(tmp_path),
        ]
    )
    assert _worker(args) == 0
    assert captured["out_dir"] == tmp_path
    assert captured["directional_parent_record"] == Path("h14.json")
    assert captured["directional_parent_sha256"] == _SHA
    assert captured["reverse_evidence_record"] == Path(
        "h13-negative.json"
    )
    assert captured["reverse_evidence_sha256"] == _SHA
    assert captured["explicit_z_profile"] == (
        TASK035B_H14_EXACT_REVERSE_TOP2_PROFILE
    )


def test_real_parent_and_negative_authorities_are_qualified_and_hash_bound(
) -> None:
    parent = _load_directional_parent(
        H14_PARENT,
        H14_PARENT_SHA,
        significant_reference_sha256=SIGNIFICANT_SHA,
    )
    negative = _load_h13_top_phase_negative(
        H13_NEGATIVE,
        H13_NEGATIVE_SHA,
        significant_reference_sha256=SIGNIFICANT_SHA,
    )

    assert parent["candidate"]["num_nedelec_dofs"] == 82_315
    assert negative["candidate"]["num_nedelec_dofs"] == 89_740
    assert negative["status"] == "actual_fixed_trace_controlled_negative"
    assert negative["diffraction_channel_comparison"][
        "significant_power_pass_count"
    ] == 8
    assert negative["diffraction_channel_comparison"][
        "significant_complex_amplitude_pass_count"
    ] == 8
