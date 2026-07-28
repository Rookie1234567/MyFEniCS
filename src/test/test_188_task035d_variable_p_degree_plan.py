from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from dolfinx import mesh
from mpi4py import MPI

from src.adaptivity.variable_p_degree_plan import (
    build_variable_p_cell_degree_plan,
    cell_box_catalog,
    load_variable_p_cell_degree_plan,
    variable_p_cell_degree_plan_payload,
)
from src.adaptivity.variable_p_periodic_orbits import (
    build_variable_p_periodic_constraint_map,
)


class Task035dVariablePDegreePlanTests(unittest.TestCase):
    def test_geometry_plan_is_partition_independent_and_periodic(self) -> None:
        if MPI.COMM_WORLD.size not in {1, 2}:
            self.skipTest("Task035d B1 qualifies serial and MPI2")
        msh = mesh.create_unit_cube(
            MPI.COMM_WORLD,
            2,
            2,
            2,
            cell_type=mesh.CellType.hexahedron,
            ghost_mode=mesh.GhostMode.shared_facet,
        )
        boxes = cell_box_catalog(msh)
        cell_degrees = {
            box: 5 if box[2] < 0.5 else 6 for box in boxes
        }
        plan = build_variable_p_cell_degree_plan(
            msh,
            cell_degrees,
            previous_cell_degree_by_box={box: 6 for box in boxes},
        )
        self.assertTrue(plan.audit["pass"])
        self.assertEqual(
            plan.audit["schema_version"],
            "task035d.variable-p-cell-degree-plan.v1",
        )
        self.assertEqual(
            plan.audit["cell_degree_counts"],
            {"p4": 0, "p5": 4, "p6": 4},
        )
        self.assertEqual(
            plan.audit["maximum_adjacent_cell_degree_jump"],
            1,
        )
        self.assertTrue(
            plan.audit["transition_from_previous_checked"]
        )
        self.assertTrue(
            plan.audit["geometry_bound_not_global_entity_id_bound"]
        )
        self.assertLess(
            plan.entity_map.active_rows,
            plan.entity_map.uniform_p6_rows,
        )
        constraints = build_variable_p_periodic_constraint_map(
            plan.entity_map,
            axes=("x", "y"),
            phase_x=complex(0.9, 0.1),
            phase_y=complex(0.8, -0.2),
        )
        self.assertTrue(constraints.audit["pass"])
        identities = MPI.COMM_WORLD.allgather(
            (
                plan.audit["mesh_cell_box_catalog_sha256"],
                plan.audit["cell_degree_plan_sha256"],
                plan.entity_map.audit[
                    "canonical_degree_map_sha256"
                ],
                plan.entity_map.active_rows,
                constraints.independent_trace_rows,
            )
        )
        self.assertEqual(len(set(identities)), 1)

    def test_illegal_p_jump_and_two_level_transition_fail_closed(
        self,
    ) -> None:
        if MPI.COMM_WORLD.size != 1:
            self.skipTest("serial invalid-plan checks")
        msh = mesh.create_unit_cube(
            MPI.COMM_SELF,
            2,
            1,
            1,
            cell_type=mesh.CellType.hexahedron,
        )
        boxes = cell_box_catalog(msh)
        with self.assertRaisesRegex(
            ValueError,
            "only keep or lower one degree",
        ):
            build_variable_p_cell_degree_plan(
                msh,
                {box: 4 for box in boxes},
                previous_cell_degree_by_box={
                    box: 6 for box in boxes
                },
            )
        with self.assertRaisesRegex(
            ValueError,
            "differ by more than one p level",
        ):
            build_variable_p_cell_degree_plan(
                msh,
                {
                    boxes[0]: 4,
                    boxes[1]: 6,
                },
            )

    def test_payload_roundtrip_is_geometry_and_content_hash_bound(
        self,
    ) -> None:
        if MPI.COMM_WORLD.size != 1:
            self.skipTest("serial file roundtrip")
        msh = mesh.create_unit_cube(
            MPI.COMM_SELF,
            2,
            1,
            1,
            cell_type=mesh.CellType.hexahedron,
        )
        boxes = cell_box_catalog(msh)
        payload = variable_p_cell_degree_plan_payload(
            msh,
            {box: 5 for box in boxes},
            provenance={"selector": "unit-test"},
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "plan.json"
            path.write_text(
                json.dumps(payload, sort_keys=True),
                encoding="utf-8",
            )
            loaded = load_variable_p_cell_degree_plan(msh, path)
        self.assertEqual(
            loaded.audit["cell_degree_plan_sha256"],
            payload["cell_degree_plan_sha256"],
        )
        self.assertEqual(loaded.entity_map.active_rows, 1020)


if __name__ == "__main__":
    unittest.main()
