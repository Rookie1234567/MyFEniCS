from __future__ import annotations

from dataclasses import replace
import hashlib
import json

import numpy as np
import pytest

from src.adaptivity.high_order_resource_audit import (
    partition_independent_linear_mesh_identity,
)
from src.common.config_3d import target_stage4_config
from src.constraints.high_order_floquet_trace import high_order_trace_layout
from src.geometry.mesh_builder_3d import (
    build_airbox_mesh_3d,
    stage4_axis_plan,
)
from src.geometry.research_axis_profiles import (
    TASK035B_H13_TOP_PHASE_REDISTRIBUTION_PROFILE,
    TASK035B_H13_TOP_PHASE_REDISTRIBUTION_Z_VALUES_NM,
    TASK035B_R5_SLAB_BISECT_PROFILE,
    TASK035B_R5_SLAB_BISECT_Z_VALUES_NM,
)
from src.geometry.tetra_mesh_audit import (
    canonical_owned_cell_ids,
    geometry_key_sha256,
)


def _axis_sha256(values: np.ndarray) -> str:
    encoded = json.dumps(
        [float(value) for value in values],
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _top_phase_config():
    return replace(
        target_stage4_config(degree=6, h_nm=13.0),
        mesh_axis_cell_counts=(6, 2, 12),
        mesh_axis_z_values=(
            TASK035B_H13_TOP_PHASE_REDISTRIBUTION_Z_VALUES_NM
        ),
        mesh_axis_z_profile=(
            TASK035B_H13_TOP_PHASE_REDISTRIBUTION_PROFILE
        ),
    )


def test_profile_moves_only_two_top_h13_planes() -> None:
    h13 = stage4_axis_plan(
        target_stage4_config(degree=6, h_nm=13.0),
        comm_size=8,
    )
    h14 = stage4_axis_plan(
        target_stage4_config(degree=6, h_nm=14.0),
        comm_size=8,
    )
    candidate = stage4_axis_plan(_top_phase_config(), comm_size=8)

    changed = np.flatnonzero(
        ~np.isclose(
            candidate.z_values,
            h13.z_values,
            rtol=0.0,
            atol=1.0e-13,
        )
    )
    assert changed.tolist() == [9, 10]
    np.testing.assert_allclose(
        candidate.z_values[:9],
        h13.z_values[:9],
        rtol=0.0,
        atol=0.0,
    )
    np.testing.assert_allclose(
        candidate.z_values[-4:],
        h14.z_values[-4:],
        rtol=0.0,
        atol=0.0,
    )
    assert candidate.z_values[[0, 1, -2, -1]].tolist() == [
        -10.0,
        0.0,
        120.0,
        130.0,
    ]
    assert candidate.mesh_cells_resolved == h13.mesh_cells_resolved == (
        6,
        2,
        12,
    )
    np.testing.assert_allclose(
        candidate.x_values,
        h13.x_values,
        rtol=0.0,
        atol=0.0,
    )
    np.testing.assert_allclose(
        candidate.y_values,
        h13.y_values,
        rtol=0.0,
        atol=0.0,
    )
    assert candidate.material_plane_alignment["all_aligned"] is True
    assert np.all(np.diff(candidate.z_values) > 0.0)
    assert candidate.axis_cell_stats["z"] == {
        "num_cells": 12,
        "min": 9.333333333333343,
        "max": 13.333333333333329,
        "median": 12.0,
    }
    assert _axis_sha256(candidate.z_values) == (
        "6f8892c60ecae93aa2b34dc4208de296c83a3cd39410e3e4e94872fc225b79b8"
    )


def test_profile_is_distinct_from_preserved_r5_negative() -> None:
    assert TASK035B_H13_TOP_PHASE_REDISTRIBUTION_PROFILE == (
        "h13_top2_phase_redistribution_v1"
    )
    assert TASK035B_R5_SLAB_BISECT_PROFILE == (
        "h14_max-R5_slab_bisect"
    )
    assert (
        TASK035B_H13_TOP_PHASE_REDISTRIBUTION_Z_VALUES_NM
        != TASK035B_R5_SLAB_BISECT_Z_VALUES_NM
    )
    assert TASK035B_R5_SLAB_BISECT_Z_VALUES_NM[:4] == (
        -10.0,
        0.0,
        6.666666666666667,
        13.333333333333334,
    )
    assert (
        TASK035B_H13_TOP_PHASE_REDISTRIBUTION_Z_VALUES_NM[:4]
        == (-10.0, 0.0, 12.0, 24.0)
    )


def test_profile_is_frozen_and_fails_closed() -> None:
    wrong_h = replace(
        _top_phase_config(),
        mesh_target_size=14.0,
    )
    with pytest.raises(ValueError, match="frozen explicit z authorities"):
        stage4_axis_plan(wrong_h, comm_size=8)

    mutated_z = list(
        TASK035B_H13_TOP_PHASE_REDISTRIBUTION_Z_VALUES_NM
    )
    mutated_z[9] += 0.25
    mutated = replace(
        _top_phase_config(),
        mesh_axis_z_values=tuple(mutated_z),
    )
    with pytest.raises(ValueError, match="frozen explicit z authorities"):
        stage4_axis_plan(mutated, comm_size=8)

    unknown = replace(
        _top_phase_config(),
        mesh_axis_z_profile="arbitrary_user_coordinates",
    )
    with pytest.raises(ValueError, match="unknown Task035b frozen"):
        stage4_axis_plan(unknown, comm_size=8)

    ordinary = target_stage4_config(degree=6, h_nm=13.0)
    assert ordinary.mesh_axis_cell_counts_requested is None
    assert ordinary.mesh_axis_z_values_requested is None
    assert ordinary.mesh_axis_z_profile is None
    assert _axis_sha256(
        stage4_axis_plan(ordinary, comm_size=8).z_values
    ) == "644e61a83908e2317dc1b8aef70ea2f1d8351a77a7cc685708be397c1aa9a3d8"


def test_fixed_trace_candidate_accepts_only_bounded_profile_context(
    monkeypatch,
    tmp_path,
) -> None:
    from src.adaptivity import target_fixed_trace_candidate as candidate

    class ReachedAuthorityGate(RuntimeError):
        pass

    def stop_at_authority_gate(_path):
        raise ReachedAuthorityGate

    monkeypatch.setattr(
        candidate,
        "_sha256",
        stop_at_authority_gate,
    )
    common = {
        "out_dir": tmp_path / "candidate",
        "control_record": tmp_path / "control.json",
        "control_sha256": "a" * 64,
        "significant_channel_reference_record": (
            tmp_path / "significant.json"
        ),
        "significant_channel_reference_sha256": "b" * 64,
        "directional_recovery": True,
        "directional_axis": "z",
    }
    with pytest.raises(ReachedAuthorityGate):
        candidate.run_target_fixed_trace_candidate(
            **common,
            h_nm=13.0,
            explicit_z_profile=(
                TASK035B_H13_TOP_PHASE_REDISTRIBUTION_PROFILE
            ),
            directional_parent_record=tmp_path / "h14.json",
            directional_parent_sha256="c" * 64,
        )
    with pytest.raises(ValueError, match="limited to the reviewed"):
        candidate.run_target_fixed_trace_candidate(
            **common,
            h_nm=14.0,
            explicit_z_profile=(
                TASK035B_H13_TOP_PHASE_REDISTRIBUTION_PROFILE
            ),
            directional_parent_record=tmp_path / "h14.json",
            directional_parent_sha256="c" * 64,
        )
    with pytest.raises(ValueError, match="limited to the reviewed"):
        candidate.run_target_fixed_trace_candidate(
            **common,
            h_nm=13.0,
            explicit_z_profile=(
                TASK035B_H13_TOP_PHASE_REDISTRIBUTION_PROFILE
            ),
        )
    with pytest.raises(ReachedAuthorityGate):
        candidate.run_target_fixed_trace_candidate(
            **common,
            h_nm=14.0,
            explicit_z_profile=TASK035B_R5_SLAB_BISECT_PROFILE,
        )


def test_profile_mesh_hash_topology_and_fixed_trace_dof_contract(
    tmp_path,
) -> None:
    mesh_data = build_airbox_mesh_3d(
        _top_phase_config(),
        tmp_path / "h13_top_phase_mesh",
    )
    identity = partition_independent_linear_mesh_identity(mesh_data)
    assert identity["global_cell_count"] == 144
    assert identity["mesh_cells_resolved"] == [6, 2, 12]
    assert identity["partition_independent_mesh_sha256"] == (
        "6d4bf800caedc07020e8d93e8fdb49cac4abd0e71a2cc29d1aea88f3a2927b08"
    )
    assert identity["cell_tag_sha256"] == (
        "46d288e1fae15f801988516b1579ecc14285f1472a9220f451cfa89efb6ef71e"
    )
    assert identity["facet_tag_sha256"] == (
        "442cd53e48103cfe55224a270b04c92cc61032ac128a5490d5349936d7d850d5"
    )

    msh = mesh_data.mesh
    for dimension in range(4):
        msh.topology.create_entities(dimension)
    entity_counts = {
        "vertices": int(msh.topology.index_map(0).size_global),
        "edges": int(msh.topology.index_map(1).size_global),
        "faces": int(msh.topology.index_map(2).size_global),
        "cells": int(msh.topology.index_map(3).size_global),
    }
    assert entity_counts == {
        "vertices": 273,
        "edges": 668,
        "faces": 540,
        "cells": 144,
    }
    p5 = high_order_trace_layout(5)
    p6 = high_order_trace_layout(6)
    fixed_trace_dofs = (
        entity_counts["edges"] * p5.edge_dofs
        + entity_counts["faces"] * p5.face_interior_dofs
        + entity_counts["cells"] * p6.cell_interior_dofs
    )
    assert fixed_trace_dofs == 89_740

    _ids, _rows, geometry_keys = canonical_owned_cell_ids(msh)
    assert geometry_key_sha256(geometry_keys) == (
        "4a1ce5adc3e30967b5f25e139fd884ae7a62eada8bb4908aa5c32c2195e0d914"
    )
