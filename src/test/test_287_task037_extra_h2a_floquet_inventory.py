from __future__ import annotations

from dataclasses import replace

import numpy as np
from mpi4py import MPI

from src.solvers.hcurl_exact_class_block_cache import (
    make_task037_extra_h2a_class_key,
    make_task037_extra_h2a_constraint_pattern,
)
from src.test.test_272_task037_extra_fullspace_mf_mpi import _build_case


def _key(pattern, *, orientation=(0,)):
    return make_task037_extra_h2a_class_key(
        cell_widths=(1.0, 1.0, 1.0),
        material_tag=1,
        material_identity=("epsilon_raw", 2.0, "epsilon_abs", 2.0),
        orientation=orientation,
        constraint_pattern=pattern,
        canonical_local_basis_signature=(
            "N1curl",
            2,
            "canonical-basix-local-order-v1",
        ),
        proxy_identity=("B0", "k0=2", "unit-mass-abs-once"),
    )


def test_h2a_pattern_uses_real_floquet_blocks_and_canonical_ordinals():
    _cfg, _mesh_data, function_space, _cell_tags, _tags, floquet, _form = _build_case(
        2, MPI.COMM_SELF
    )
    try:
        blocks = tuple(floquet.phase_independent_topology.blocks)
        block = next(
            candidate
            for candidate in blocks
            if candidate.slave_local_dofs
            and candidate.entity_kind in {"edge", "face"}
        )
        owned_cells = int(function_space.mesh.topology.index_map(3).size_local)
        cell_id = next(
            cell
            for cell in range(owned_cells)
            if all(
                int(row) in set(
                    int(value)
                    for value in function_space.dofmap.cell_dofs(cell)
                )
                for row in block.slave_local_dofs
            )
        )
        local_rows = tuple(
            int(value) for value in function_space.dofmap.cell_dofs(cell_id)
        )
        pattern = make_task037_extra_h2a_constraint_pattern(
            (block,),
            cell_local_dofs=local_rows,
            phase_x=floquet.phase_x,
            phase_y=floquet.phase_y,
            phase_corner=floquet.phase_corner,
        )
        assert pattern
        topology_fields = tuple(field[0] for field in pattern[0]["topology"])
        assert topology_fields == (
            "entity_kind",
            "direction",
            "vertex_permutation",
            "cell_type",
        )
        serialized = repr(pattern)
        assert all(
            forbidden not in serialized
            for forbidden in (
                "global row",
                "global_row",
                "entity_id",
                "owner",
                "geometry_key",
            )
        )
        assert all(
            all(isinstance(column, int) for column, _value in entry["columns"])
            for entry in pattern
        )
        assert all(
            entry["local_slave"] < len(local_rows) for entry in pattern
        )
        expected_ordinals = {
            int(row): ordinal for ordinal, row in enumerate(local_rows)
        }
        assert all(
            entry["local_slave"]
            == expected_ordinals[int(block.slave_local_dofs[index])]
            for index, entry in enumerate(pattern)
            if index < len(block.slave_local_dofs)
        )
        shifted_rows = tuple(row + 10000 for row in local_rows)
        assert _key(pattern) == _key(
            make_task037_extra_h2a_constraint_pattern(
                (
                    replace(
                        block,
                        slave_local_dofs=tuple(
                            row + 10000 for row in block.slave_local_dofs
                        ),
                    ),
                ),
                cell_local_dofs=shifted_rows,
                phase_x=floquet.phase_x,
                phase_y=floquet.phase_y,
                phase_corner=floquet.phase_corner,
            )
        )
        phase_values = {
            "x": complex(floquet.phase_x),
            "y": complex(floquet.phase_y),
            "corner": complex(floquet.phase_corner),
        }
        phase_values[str(block.kind)] *= np.exp(0.2j)
        phase_changed = make_task037_extra_h2a_constraint_pattern(
            (block,),
            cell_local_dofs=local_rows,
            phase_x=phase_values["x"],
            phase_y=phase_values["y"],
            phase_corner=phase_values["corner"],
        )
        assert _key(phase_changed) != _key(pattern)
        other_direction = {"x": "y", "y": "x", "corner": "x"}[str(block.kind)]
        direction_pair_key = list(block.periodic_pair_key)
        direction_pair_key[1] = {"x": 1, "y": 2, "corner": 3}[other_direction]
        direction_pattern = make_task037_extra_h2a_constraint_pattern(
            (
                replace(
                    block,
                    kind=other_direction,
                    periodic_pair_key=tuple(direction_pair_key),
                ),
            ),
            cell_local_dofs=local_rows,
            phase_x=floquet.phase_x,
            phase_y=floquet.phase_y,
            phase_corner=floquet.phase_corner,
        )
        assert _key(direction_pattern) != _key(pattern)
        permutation_changed = tuple(reversed(tuple(block.entity_vertex_permutation)))
        if permutation_changed == tuple(block.entity_vertex_permutation):
            permutation_changed = tuple(
                (int(value) + 1) % max(2, len(permutation_changed))
                for value in permutation_changed
            )
        permutation_pattern = make_task037_extra_h2a_constraint_pattern(
            (
                replace(
                    block,
                    entity_vertex_permutation=permutation_changed,
                ),
            ),
            cell_local_dofs=local_rows,
            phase_x=floquet.phase_x,
            phase_y=floquet.phase_y,
            phase_corner=floquet.phase_corner,
        )
        assert _key(permutation_pattern) != _key(pattern)
        transform_changed = np.array(block.coefficient_transform, copy=True)
        transform_changed[0, 0] += 0.125
        transform_pattern = make_task037_extra_h2a_constraint_pattern(
            (
                replace(
                    block,
                    coefficient_transform=transform_changed,
                ),
            ),
            cell_local_dofs=local_rows,
            phase_x=floquet.phase_x,
            phase_y=floquet.phase_y,
            phase_corner=floquet.phase_corner,
        )
        assert _key(transform_pattern) != _key(pattern)
        assert _key(()) != _key(pattern)
    finally:
        del floquet


def test_h2a_unconstrained_pattern_is_structured_empty_tuple():
    assert make_task037_extra_h2a_constraint_pattern(
        (),
        cell_local_dofs=(0, 1, 2),
        phase_x=1.0 + 0.0j,
        phase_y=1.0 + 0.0j,
    ) == ()
