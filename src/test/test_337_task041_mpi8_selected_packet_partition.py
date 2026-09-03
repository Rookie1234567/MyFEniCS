"""Focused opt-in partition/layout contracts for the Task41 MPI8 detour."""

import hashlib
import json
from types import SimpleNamespace

import numpy as np
import pytest
from mpi4py import MPI

from benchmarks.task039_v4_selected_mode_packet import (
    TASK041_CROSS_SECTION_PARTITION_FIELD,
    TASK041_CROSS_SECTION_PARTITION_POLICY,
    task041_cross_section_partition_enabled,
    validate_task041_cross_section_layout_identity,
)
from src.geometry.mesh_builder_3d import _rank_cell_ids
from src.modes.cross_section_spaces import (
    CrossSectionMesh,
    _structured_quad_mesh,
    build_cross_section_spaces,
    cross_section_layout_identity,
)


def _layout_identity(*, global_mixed_size: int = 12) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema": "task041.cross_section_layout_identity.v1",
        "partition_policy": TASK041_CROSS_SECTION_PARTITION_POLICY,
        "mpi_size": 1,
        "global_mixed_size": global_mixed_size,
        "rank_layout": [],
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()
    return {
        **payload,
        "canonical_json_sha256": hashlib.sha256(encoded).hexdigest(),
    }


def _task041_identity() -> dict[str, object]:
    return {
        TASK041_CROSS_SECTION_PARTITION_FIELD: TASK041_CROSS_SECTION_PARTITION_POLICY
    }


def test_partition_opt_in_is_strict_and_old_identity_is_ordinary() -> None:
    assert task041_cross_section_partition_enabled({}) is False
    assert task041_cross_section_partition_enabled({"mode_count": 480}) is False
    assert task041_cross_section_partition_enabled(_task041_identity()) is True
    with pytest.raises(ValueError, match="partition policy"):
        task041_cross_section_partition_enabled(
            {TASK041_CROSS_SECTION_PARTITION_FIELD: "graph_default"}
        )


def test_packet_layout_match_and_mismatch_fail_closed() -> None:
    identity = _task041_identity()
    layout = _layout_identity()
    metadata = {"cross_section_layout_identity": layout}
    assert (
        validate_task041_cross_section_layout_identity(identity, metadata, layout)
        == layout
    )

    mismatch = _layout_identity(global_mixed_size=13)
    with pytest.raises(ValueError, match="layout identity mismatch"):
        validate_task041_cross_section_layout_identity(identity, {
            "cross_section_layout_identity": mismatch
        }, layout)

    tampered = dict(layout)
    tampered["global_mixed_size"] = 13
    with pytest.raises(ValueError, match="layout SHA mismatch"):
        validate_task041_cross_section_layout_identity(
            identity, {"cross_section_layout_identity": tampered}, layout
        )


def test_ordinary_partition_path_selects_graph_partitioner(monkeypatch) -> None:
    calls: list[tuple[object, ...]] = []

    monkeypatch.setattr(
        "src.modes.cross_section_spaces.mesh.create_cell_partitioner",
        lambda *args: calls.append(args) or "graph-partitioner",
    )
    monkeypatch.setattr(
        "src.modes.cross_section_spaces.mesh.create_mesh",
        lambda *args, **kwargs: SimpleNamespace(),
    )
    _structured_quad_mesh(
        MPI.COMM_WORLD,
        np.array([0.0, 1.0]),
        np.array([0.0, 1.0]),
    )
    assert len(calls) == 1
    assert len(calls[0]) == 1


def test_input_partition_layout_identity_repeats_on_small_mesh() -> None:
    if MPI.COMM_WORLD.size not in (1, 2):
        pytest.skip("focused layout regression is serial/MPI2")
    x_values = np.array([0.0, 1.0, 2.0])
    y_values = np.array([0.0, 1.0, 2.0])
    layouts = []
    owned_ids = None
    for _ in range(2):
        msh = _structured_quad_mesh(
            MPI.COMM_WORLD,
            x_values,
            y_values,
            preserve_input_partition=True,
        )
        cross_section = CrossSectionMesh(
            mesh=msh,
            x_values=x_values,
            y_values=y_values,
            axis_plan=SimpleNamespace(),
            material_kind="air",
            epsilon_r=None,
        )
        spaces = build_cross_section_spaces(cross_section, transverse_degree=1)
        owned_cell_count = int(msh.topology.index_map(msh.topology.dim).size_local)
        cell_ids = []
        for cell in range(owned_cell_count):
            geometry_ids = np.asarray(msh.geometry.dofmap[cell], dtype=np.int64)
            center = np.mean(msh.geometry.x[geometry_ids], axis=0)
            cell_ids.append(2 * int(np.floor(center[1])) + int(np.floor(center[0])))
        expected_ids = list(
            _rank_cell_ids(
                4,
                MPI.COMM_WORLD.rank,
                MPI.COMM_WORLD.size,
            )
        )
        assert len(cell_ids) == len(expected_ids)
        assert sorted(cell_ids) == expected_ids
        if owned_ids is None:
            owned_ids = cell_ids
        else:
            assert cell_ids == owned_ids
        layouts.append(
            cross_section_layout_identity(
                cross_section,
                spaces,
                comm=MPI.COMM_WORLD,
                preserve_input_partition=True,
            )
        )
    assert layouts[0]["partition_policy"] == TASK041_CROSS_SECTION_PARTITION_POLICY
    assert layouts[0]["mpi_size"] == MPI.COMM_WORLD.size
    assert layouts[0]["rank_layout"] == layouts[1]["rank_layout"]
    assert (
        layouts[0]["canonical_json_sha256"]
        == layouts[1]["canonical_json_sha256"]
    )
    all_owned_ids = MPI.COMM_WORLD.allgather(owned_ids)
    assert all_owned_ids == [
        list(_rank_cell_ids(4, rank, MPI.COMM_WORLD.size))
        for rank in range(MPI.COMM_WORLD.size)
    ]
    for rank_layout in layouts[0]["rank_layout"]:
        expected_ids = list(
            _rank_cell_ids(4, rank_layout["rank"], MPI.COMM_WORLD.size)
        )
        assert rank_layout["input_cell_count"] == len(expected_ids)
        assert rank_layout["cells"]["index_map"]["size_local"] == len(expected_ids)
        cell_index_map = rank_layout["cells"]["index_map"]
        mixed_dofs = rank_layout["mixed_dofs"]
        hashes = (
            cell_index_map["local_to_global_sha256"],
            cell_index_map["ghost_owners_sha256"],
            rank_layout["cells"]["permutation"]["sha256"],
            rank_layout["cells"]["orientation"]["sha256"],
            rank_layout["cells"]["connectivity"]["sha256"],
            mixed_dofs["local_to_global_sha256"],
            mixed_dofs["ghost_owners_sha256"],
            rank_layout["transverse_to_mixed_sha256"],
            rank_layout["longitudinal_to_mixed_sha256"],
        )
        assert all(
            isinstance(value, str)
            and len(value) == 64
            and all(char in "0123456789abcdef" for char in value)
            for value in hashes
        )
