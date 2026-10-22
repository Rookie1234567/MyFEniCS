from __future__ import annotations

import unittest

from src.adaptivity.dyadic_hexa_refinement import build_root_dyadic_hexa_forest
from src.adaptivity.hcurl_broken_trace_graph import raise_cell_degrees_for_p_up


class Task43PUpDegreeClosureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.forest = build_root_dyadic_hexa_forest(
            [
                (0.0, 0.0, 0.0, 1.0, 1.0, 1.0),
                (1.0, 0.0, 0.0, 2.0, 1.0, 1.0),
                (2.0, 0.0, 0.0, 3.0, 1.0, 1.0),
            ],
            [1, 1, 1],
            periodic_axes=("x",),
        )
        self.boxes = tuple(cell.box for cell in self.forest.leaves)

    def test_closes_shared_and_periodic_p_jumps_minimally(self) -> None:
        parent = {
            self.boxes[0]: 4,
            self.boxes[1]: 3,
            self.boxes[2]: 3,
        }
        closed, audit = raise_cell_degrees_for_p_up(
            self.forest,
            parent,
            (self.boxes[0],),
        )
        self.assertEqual(
            tuple(closed[box] for box in self.boxes),
            (5, 4, 4),
        )
        self.assertEqual(audit["requested_raised_count"], 1)
        self.assertEqual(audit["forced_cell_count"], 2)
        self.assertEqual(audit["maximum_neighbor_p_jump_after_closure"], 1)

    def test_propagates_a_p_up_through_multiple_neighbor_layers(self) -> None:
        forest = build_root_dyadic_hexa_forest(
            [
                (0.0, 0.0, 0.0, 1.0, 1.0, 1.0),
                (1.0, 0.0, 0.0, 2.0, 1.0, 1.0),
                (2.0, 0.0, 0.0, 3.0, 1.0, 1.0),
            ],
            [1, 1, 1],
            periodic_axes=(),
        )
        boxes = tuple(cell.box for cell in forest.leaves)
        parent = dict(zip(boxes, (5, 4, 3), strict=True))
        closed, audit = raise_cell_degrees_for_p_up(
            forest,
            parent,
            (boxes[0],),
        )
        self.assertEqual(tuple(closed[box] for box in boxes), (6, 5, 4))
        self.assertEqual(audit["closure_iterations"], 2)
        self.assertEqual(audit["maximum_parent_neighbor_p_jump"], 1)

    def test_rejects_invalid_or_ambiguous_marks_and_invalid_parent(self) -> None:
        parent = {box: 3 for box in self.boxes}
        with self.assertRaisesRegex(ValueError, "must be unique"):
            raise_cell_degrees_for_p_up(
                self.forest,
                parent,
                (self.boxes[0], self.boxes[0]),
            )
        with self.assertRaisesRegex(ValueError, "absent forest leaves"):
            raise_cell_degrees_for_p_up(
                self.forest,
                parent,
                ((3.0, 0.0, 0.0, 4.0, 1.0, 1.0),),
            )
        invalid_parent = dict(zip(self.boxes, (5, 3, 3), strict=True))
        with self.assertRaisesRegex(ValueError, "parent already violates"):
            raise_cell_degrees_for_p_up(
                self.forest,
                invalid_parent,
                (self.boxes[0],),
            )

    def test_p6_marks_are_reported_as_saturated_not_noop_upgrades(self) -> None:
        parent = {box: 6 for box in self.boxes}
        closed, audit = raise_cell_degrees_for_p_up(
            self.forest,
            parent,
            (self.boxes[0],),
        )
        self.assertEqual(dict(closed), parent)
        self.assertEqual(audit["saturated_mark_count"], 1)
        self.assertEqual(audit["requested_raised_count"], 0)
        self.assertTrue(audit["all_marked_cells_saturated"])


if __name__ == "__main__":
    unittest.main()
