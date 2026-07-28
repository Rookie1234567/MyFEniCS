from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from dolfinx import mesh
from mpi4py import MPI
import pytest

from src.adaptivity.variable_p_degree_plan import (
    BIDIRECTIONAL_ONE_STEP_TRANSITION_POLICY,
    build_variable_p_cell_degree_plan,
    cell_box_catalog,
    load_variable_p_cell_degree_plan,
    variable_p_cell_degree_plan_payload,
)
from src.adaptivity.variable_p_periodic_orbits import (
    build_variable_p_periodic_constraint_map,
)


class Task035eBidirectionalPTransitionTests(unittest.TestCase):
    def setUp(self) -> None:
        if MPI.COMM_WORLD.size != 1:
            self.skipTest("Task035e p-transition contract is a serial test")
        self.mesh = mesh.create_unit_cube(
            MPI.COMM_SELF,
            2,
            1,
            1,
            cell_type=mesh.CellType.hexahedron,
        )
        self.boxes = cell_box_catalog(self.mesh)
        self.previous = {
            self.boxes[0]: 4,
            self.boxes[1]: 5,
        }
        self.current = {
            self.boxes[0]: 5,
            self.boxes[1]: 6,
        }

    def test_legacy_default_still_rejects_p_up(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "only keep or lower one degree",
        ):
            build_variable_p_cell_degree_plan(
                self.mesh,
                self.current,
                previous_cell_degree_by_box=self.previous,
            )

    def test_opt_in_accepts_p4_to_p5_and_p5_to_p6(self) -> None:
        plan = build_variable_p_cell_degree_plan(
            self.mesh,
            self.current,
            previous_cell_degree_by_box=self.previous,
            transition_policy=(
                BIDIRECTIONAL_ONE_STEP_TRANSITION_POLICY
            ),
        )
        self.assertTrue(plan.audit["pass"])
        self.assertEqual(
            plan.audit["transition_policy"],
            BIDIRECTIONAL_ONE_STEP_TRANSITION_POLICY,
        )
        self.assertEqual(
            plan.audit["schema_version"],
            "task035e.variable-p-cell-degree-plan.v2",
        )
        self.assertEqual(
            plan.audit["maximum_adjacent_cell_degree_jump"],
            1,
        )
        self.assertIsNotNone(
            plan.audit["previous_cell_degree_plan_sha256"]
        )

        payload = variable_p_cell_degree_plan_payload(
            self.mesh,
            self.current,
            previous_cell_degree_by_box=self.previous,
            transition_policy=(
                BIDIRECTIONAL_ONE_STEP_TRANSITION_POLICY
            ),
            provenance={"selector": "task035e-unit-test"},
        )
        self.assertEqual(
            payload["schema_version"],
            "task035e.variable-p-cell-degree-plan.v2",
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "plan.json"
            path.write_text(
                json.dumps(payload, sort_keys=True),
                encoding="utf-8",
            )
            loaded = load_variable_p_cell_degree_plan(
                self.mesh,
                path,
            )
        self.assertEqual(
            loaded.audit["transition_context_sha256"],
            payload["transition_context_sha256"],
        )
        self.assertEqual(
            payload["closure_audit"]["schema_version"],
            "task035e.variable-p-cell-degree-plan.v2",
        )

    def test_x_periodic_incident_min_closes_before_entity_map(self) -> None:
        current = {
            self.boxes[0]: 4,
            self.boxes[1]: 5,
        }
        previous = {box: 4 for box in self.boxes}
        plan = build_variable_p_cell_degree_plan(
            self.mesh,
            current,
            previous_cell_degree_by_box=previous,
            transition_policy=(
                BIDIRECTIONAL_ONE_STEP_TRANSITION_POLICY
            ),
        )
        closure = plan.audit["periodic_entity_degree_closure"]

        self.assertTrue(closure["pass"])
        self.assertEqual(
            closure["maximum_periodic_cell_degree_jump"],
            1,
        )
        self.assertGreater(closure["lowered_entity_count"], 0)
        self.assertGreater(closure["relation_count"], 0)
        self.assertTrue(closure["periodic_relation_degrees_closed"])
        constraints = build_variable_p_periodic_constraint_map(
            plan.entity_map,
            axes=("x", "y"),
            phase_x=complex(0.9, 0.1),
            phase_y=complex(0.8, -0.2),
        )
        self.assertTrue(constraints.audit["pass"])

    def test_periodic_cell_jump_is_checked_before_trace_lowering(self) -> None:
        three = mesh.create_unit_cube(
            MPI.COMM_SELF,
            3,
            1,
            1,
            cell_type=mesh.CellType.hexahedron,
        )
        boxes = cell_box_catalog(three)
        current = {
            box: degree
            for box, degree in zip(boxes, (4, 5, 6), strict=True)
        }
        previous = {
            box: degree
            for box, degree in zip(boxes, (4, 4, 5), strict=True)
        }
        with self.assertRaisesRegex(
            ValueError,
            "periodic cells differ by more than one p level",
        ):
            build_variable_p_cell_degree_plan(
                three,
                current,
                previous_cell_degree_by_box=previous,
                transition_policy=(
                    BIDIRECTIONAL_ONE_STEP_TRANSITION_POLICY
                ),
            )

    def test_opt_in_rejects_two_level_jump_and_other_geometry(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "may only change one degree",
        ):
            build_variable_p_cell_degree_plan(
                self.mesh,
                {
                    self.boxes[0]: 6,
                    self.boxes[1]: 6,
                },
                previous_cell_degree_by_box=self.previous,
                transition_policy=(
                    BIDIRECTIONAL_ONE_STEP_TRANSITION_POLICY
                ),
            )
        with self.assertRaisesRegex(
            ValueError,
            "another geometry",
        ):
            build_variable_p_cell_degree_plan(
                self.mesh,
                self.current,
                previous_cell_degree_by_box={
                    self.boxes[0]: 4,
                },
                transition_policy=(
                    BIDIRECTIONAL_ONE_STEP_TRANSITION_POLICY
                ),
            )

    def test_v2_loader_rejects_geometry_drift_and_hash_tampering(
        self,
    ) -> None:
        payload = variable_p_cell_degree_plan_payload(
            self.mesh,
            self.current,
            previous_cell_degree_by_box=self.previous,
            transition_policy=(
                BIDIRECTIONAL_ONE_STEP_TRANSITION_POLICY
            ),
            provenance={"selector": "task035e-unit-test"},
        )
        drifted_mesh = mesh.create_unit_cube(
            MPI.COMM_SELF,
            3,
            1,
            1,
            cell_type=mesh.CellType.hexahedron,
        )
        tampered = copy.deepcopy(payload)
        tampered["previous_cells"][0]["degree"] = 5
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            path = directory_path / "plan.json"
            path.write_text(
                json.dumps(payload, sort_keys=True),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                ValueError,
                "geometry SHA differs",
            ):
                load_variable_p_cell_degree_plan(
                    drifted_mesh,
                    path,
                )
            path.write_text(
                json.dumps(tampered, sort_keys=True),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                ValueError,
                "previous degree-plan content SHA is invalid",
            ):
                load_variable_p_cell_degree_plan(
                    self.mesh,
                    path,
                )


def test_periodic_entity_degree_closure_is_mpi8_identical() -> None:
    if MPI.COMM_WORLD.size != 8:
        pytest.skip("Task035e periodic closure MPI qualification uses MPI8")
    msh = mesh.create_unit_cube(
        MPI.COMM_WORLD,
        8,
        1,
        1,
        cell_type=mesh.CellType.hexahedron,
        ghost_mode=mesh.GhostMode.shared_facet,
    )
    boxes = cell_box_catalog(msh)
    current = {
        box: (4 if index == 0 else 5)
        for index, box in enumerate(boxes)
    }
    previous = {box: 4 for box in boxes}
    plan = build_variable_p_cell_degree_plan(
        msh,
        current,
        previous_cell_degree_by_box=previous,
        transition_policy=BIDIRECTIONAL_ONE_STEP_TRANSITION_POLICY,
    )
    constraints = build_variable_p_periodic_constraint_map(
        plan.entity_map,
        axes=("x", "y"),
        phase_x=complex(0.9, 0.1),
        phase_y=complex(0.8, -0.2),
    )
    closure = plan.audit["periodic_entity_degree_closure"]
    identity = (
        closure["relation_sha256"],
        closure["orbit_sha256"],
        closure["raw_entity_degree_sha256"],
        closure["closed_entity_degree_sha256"],
        closure["degree_change_sha256"],
        closure["periodic_cell_pair_sha256"],
        plan.entity_map.audit["canonical_degree_map_sha256"],
        constraints.audit["relation_count"],
        constraints.audit["component_count"],
        constraints.audit["independent_periodic_trace_rows"],
        constraints.audit["maximum_orbit_size"],
    )

    assert closure["maximum_periodic_cell_degree_jump"] == 1
    assert closure["lowered_entity_count"] > 0
    assert constraints.audit["pass"] is True
    assert len(set(MPI.COMM_WORLD.allgather(identity))) == 1


if __name__ == "__main__":
    unittest.main()
