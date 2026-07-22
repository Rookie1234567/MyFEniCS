from __future__ import annotations

import math
import unittest

import numpy as np
from basix.ufl import element
from mpi4py import MPI

from dolfinx import default_real_type, fem, mesh

from src.adaptivity.global_two_level_r5 import (
    _global_dorfler_mark,
    localize_global_two_level_correction,
)


def _analytic(x: np.ndarray) -> np.ndarray:
    values = np.empty((3, x.shape[1]), dtype=np.complex128)
    values[0] = np.sin(math.pi * x[1]) * np.exp(0.2j * x[2])
    values[1] = np.cos(math.pi * x[2]) * np.exp(-0.1j * x[0])
    values[2] = 0.25 * np.sin(2.0 * math.pi * x[0])
    return values


class Task035ActualGlobalR5Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        coarse_mesh = mesh.create_box(
            MPI.COMM_WORLD,
            [np.zeros(3), np.ones(3)],
            [2, 2, 2],
            cell_type=mesh.CellType.hexahedron,
        )
        enriched_mesh = mesh.create_box(
            MPI.COMM_WORLD,
            [np.zeros(3), np.ones(3)],
            [2, 2, 2],
            cell_type=mesh.CellType.hexahedron,
        )
        coarse_space = fem.functionspace(
            coarse_mesh,
            element("N1curl", coarse_mesh.basix_cell(), 1, dtype=default_real_type),
        )
        enriched_space = fem.functionspace(
            enriched_mesh,
            element("N1curl", enriched_mesh.basix_cell(), 2, dtype=default_real_type),
        )
        coarse = fem.Function(coarse_space)
        enriched = fem.Function(enriched_space)
        coarse.interpolate(_analytic)
        enriched.interpolate(_analytic)
        coarse.x.scatter_forward()
        enriched.x.scatter_forward()
        cls.record = localize_global_two_level_correction(
            coarse,
            enriched,
            theta=0.5,
        )

    def test_actual_cell_energy_is_finite_nonnegative_and_closed(self) -> None:
        self.assertTrue(self.record["formal_hierarchical_fe_r5"])
        self.assertTrue(self.record["finite_cell_contributions"])
        self.assertTrue(self.record["nonnegative_cell_contributions"])
        self.assertGreater(self.record["correction_energy_norm"], 0.0)
        self.assertLess(
            self.record["correction_energy"]["relative_closure_error"],
            1.0e-11,
        )

    def test_owned_cell_accounting_and_dorfler_marking(self) -> None:
        self.assertTrue(self.record["distributed_ownership_unique"])
        self.assertEqual(self.record["owned_cell_contribution_count"], 8)
        marking = self.record["marking"]
        self.assertGreater(marking["count"], 0)
        self.assertGreaterEqual(marking["captured_fraction"], 0.5)
        self.assertEqual(len(marking["global_cell_ids_sha256"]), 64)
        self.assertEqual(
            marking["count"], len(self.record["marked_global_cell_ids"])
        )

    def test_dorfler_cutoff_ties_are_expanded_deterministically(self) -> None:
        if MPI.COMM_WORLD.rank == 0:
            cell_ids = np.asarray([10, 11, 12], dtype=np.int64)
            contributions = np.asarray(
                [0.5, 0.25 + 5.0e-13, 0.25 - 5.0e-13],
                dtype=np.float64,
            )
        else:
            cell_ids = np.asarray([], dtype=np.int64)
            contributions = np.asarray([], dtype=np.float64)
        marked, report = _global_dorfler_mark(
            MPI.COMM_WORLD,
            cell_ids,
            contributions,
            theta=0.75,
        )
        self.assertEqual(marked.tolist(), [10, 11, 12])
        self.assertEqual(report["minimal_count_before_tie_expansion"], 2)
        self.assertEqual(report["cutoff_tie_expansion_count"], 1)
        self.assertEqual(
            report["tie_policy"],
            "include_all_cutoff_contributions_within_relative_1e-10",
        )


if __name__ == "__main__":
    unittest.main()
