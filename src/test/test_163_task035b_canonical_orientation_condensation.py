from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

import basix
import numpy as np
import ufl
from basix.ufl import element
from dolfinx import default_real_type, fem, mesh
from mpi4py import MPI
from petsc4py import PETSc
from scipy.linalg import lu_solve

from src.adaptivity.hcurl_regionwise_p import (
    fixed_trace_hcurl_ufl_element,
)
from src.solvers.hcurl_assembly_time_condensation import (
    _qualified_trace_orientation_block,
    build_unconstrained_assembly_time_condensation,
    prepare_cell_interior_rhs_recovery,
    recover_owned_cell_interiors,
)


def _actual_orientation_problem(ufl_element):
    msh = mesh.create_unit_cube(
        MPI.COMM_SELF,
        2,
        2,
        2,
        cell_type=mesh.CellType.hexahedron,
    )
    owned_cells = int(
        msh.topology.index_map(msh.topology.dim).size_local
    )
    cell_tags = mesh.meshtags(
        msh,
        msh.topology.dim,
        np.arange(owned_cells, dtype=np.int32),
        np.ones(owned_cells, dtype=np.int32),
    )
    space = fem.functionspace(msh, ufl_element)
    trial = ufl.TrialFunction(space)
    test = ufl.TestFunction(space)
    dx = ufl.Measure("dx", domain=msh, subdomain_data=cell_tags)
    form = fem.form(
        (
            ufl.inner(ufl.curl(trial), ufl.curl(test))
            + PETSc.ScalarType(2.5 - 0.2j) * ufl.inner(trial, test)
        )
        * dx(1)
    )
    return msh, cell_tags, space, form


def _relative_array_error(candidate: np.ndarray, reference: np.ndarray) -> float:
    return float(
        np.linalg.norm(candidate - reference)
        / max(np.linalg.norm(reference), 1.0e-30)
    )


class TestTask035bCanonicalOrientationCondensation(unittest.TestCase):
    def _assert_actual_operator_equivalence(self, ufl_element) -> None:
        _msh, cell_tags, space, form = _actual_orientation_problem(
            ufl_element
        )
        reference = build_unconstrained_assembly_time_condensation(
            form,
            space,
            cell_tags,
        )
        candidate = build_unconstrained_assembly_time_condensation(
            form,
            space,
            cell_tags,
            canonical_orientation_class_reuse=True,
        )
        difference = candidate.matrix.copy()
        difference.axpy(
            PETSc.ScalarType(-1.0),
            reference.matrix,
            structure=PETSc.Mat.Structure.SAME_NONZERO_PATTERN,
        )
        self.assertLess(
            difference.norm() / max(reference.matrix.norm(), 1.0e-30),
            2.0e-12,
        )
        self.assertEqual(
            set(candidate.interior_from_trace_by_class),
            set(reference.interior_from_trace_by_class),
        )
        rng = np.random.default_rng(2026072501)
        for class_key in reference.interior_from_trace_by_class:
            self.assertLess(
                _relative_array_error(
                    candidate.interior_from_trace_by_class[class_key],
                    reference.interior_from_trace_by_class[class_key],
                ),
                1.0e-11,
            )
            self.assertLess(
                _relative_array_error(
                    candidate.dual_interior_from_trace_by_class[class_key],
                    reference.dual_interior_from_trace_by_class[class_key],
                ),
                1.0e-11,
            )
            reference_lu = reference.interior_lu_by_class[class_key]
            candidate_lu = candidate.interior_lu_by_class[class_key]
            rhs = (
                rng.standard_normal(reference_lu[0].shape[0])
                + 1j * rng.standard_normal(reference_lu[0].shape[0])
            )
            np.testing.assert_allclose(
                lu_solve(candidate_lu, rhs),
                lu_solve(reference_lu, rhs),
                rtol=0.0,
                atol=0.0,
            )
            np.testing.assert_array_equal(
                candidate.interior_rhs_projection_by_class[class_key],
                reference.interior_rhs_projection_by_class[class_key],
            )
            np.testing.assert_array_equal(
                candidate.interior_solution_embedding_by_class[class_key],
                reference.interior_solution_embedding_by_class[class_key],
            )

        active_trace = (
            rng.standard_normal(candidate.active_rows)
            + 1j * rng.standard_normal(candidate.active_rows)
        )
        full_rhs = PETSc.Vec().createSeq(
            candidate.full_rows,
            comm=PETSc.COMM_SELF,
        )
        full_rhs.getArray()[:] = (
            rng.standard_normal(candidate.full_rows)
            + 1j * rng.standard_normal(candidate.full_rows)
        )
        full_rhs.assemble()
        reference_recovery = recover_owned_cell_interiors(
            reference,
            active_trace,
            full_rhs=full_rhs,
        )
        candidate_recovery = recover_owned_cell_interiors(
            candidate,
            active_trace,
            full_rhs=full_rhs,
        )
        for (reference_rows, reference_values), (
            candidate_rows,
            candidate_values,
        ) in zip(reference_recovery, candidate_recovery, strict=True):
            np.testing.assert_array_equal(candidate_rows, reference_rows)
            self.assertLess(
                _relative_array_error(
                    candidate_values,
                    reference_values,
                ),
                3.0e-11,
            )

        reference_lifecycle = prepare_cell_interior_rhs_recovery(
            reference,
            full_rhs,
            release_nonprimal_caches=False,
        )
        candidate_lifecycle = prepare_cell_interior_rhs_recovery(
            candidate,
            full_rhs,
            release_nonprimal_caches=False,
        )
        self.assertEqual(
            reference_lifecycle["owned_cell_count_global"],
            candidate_lifecycle["owned_cell_count_global"],
        )
        for reference_values, candidate_values in zip(
            reference.prepared_interior_rhs_by_cell or (),
            candidate.prepared_interior_rhs_by_cell or (),
            strict=True,
        ):
            np.testing.assert_allclose(
                candidate_values,
                reference_values,
                rtol=2.0e-13,
                atol=2.0e-12,
            )

        ordinary_audit = reference.build_audit[
            "canonical_orientation_class_reuse"
        ]
        self.assertFalse(ordinary_audit["enabled"])
        audit = candidate.build_audit[
            "canonical_orientation_class_reuse"
        ]
        self.assertTrue(audit["enabled"])
        self.assertFalse(audit["ordinary_default_changed"])
        self.assertTrue(
            audit[
                "trace_interior_block_diagonal_proven_for_every_used_"
                "permutation"
            ]
        )
        self.assertGreaterEqual(
            audit["aii_factorizations_avoided_sum"],
            1,
        )
        self.assertEqual(
            len(
                {
                    id(factor[0])
                    for factor in candidate.interior_lu_by_class.values()
                }
            ),
            audit["canonical_class_construction_count_sum"],
        )

        full_rhs.destroy()
        difference.destroy()
        candidate.destroy()
        reference.destroy()

    def test_actual_degree2_operator_and_rhs_recovery_are_equivalent(
        self,
    ) -> None:
        self._assert_actual_operator_equivalence(
            element(
                "N1curl",
                basix.CellType.hexahedron,
                2,
                dtype=default_real_type,
            )
        )

    def test_actual_p5trace_p6interior_orientation_split(
        self,
    ) -> None:
        msh = mesh.create_unit_cube(
            MPI.COMM_SELF,
            2,
            2,
            2,
            cell_type=mesh.CellType.hexahedron,
        )
        space = fem.functionspace(
            msh,
            fixed_trace_hcurl_ufl_element(5, 6),
        )
        basix_element = space.element.basix_element
        interior = np.asarray(
            basix_element.entity_dofs[msh.topology.dim][0],
            dtype=np.int32,
        )
        trace = np.setdiff1d(
            np.arange(space.element.space_dimension, dtype=np.int32),
            interior,
            assume_unique=True,
        )
        msh.topology.create_entity_permutations()
        permutations = np.unique(
            msh.topology.get_cell_permutation_info()
        )
        self.assertGreaterEqual(len(permutations), 5)
        for permutation in permutations:
            transform, audit = _qualified_trace_orientation_block(
                space.element,
                trace_positions=trace,
                interior_positions=interior,
                cell_info=int(permutation),
            )
            self.assertTrue(audit["block_diagonal_trace_interior_proven"])
            self.assertEqual(audit["interior_identity_max_abs"], 0.0)
            self.assertEqual(audit["trace_from_interior_max_abs"], 0.0)
            self.assertEqual(audit["interior_from_trace_max_abs"], 0.0)
            self.assertEqual(transform.shape, (300, 300))

    def test_warm_persistent_hits_still_qualify_every_used_permutation(
        self,
    ) -> None:
        _msh, cell_tags, space, form = _actual_orientation_problem(
            element(
                "N1curl",
                basix.CellType.hexahedron,
                2,
                dtype=default_real_type,
            )
        )
        with tempfile.TemporaryDirectory() as temporary:
            cache_directory = Path(temporary)
            cold = build_unconstrained_assembly_time_condensation(
                form,
                space,
                cell_tags,
                persistent_cache_directory=cache_directory,
                persistent_cache_source_sha="1" * 40,
                persistent_cache_mode="read_write",
                canonical_orientation_class_reuse=True,
            )
            warm = build_unconstrained_assembly_time_condensation(
                form,
                space,
                cell_tags,
                persistent_cache_directory=cache_directory,
                persistent_cache_source_sha="1" * 40,
                persistent_cache_mode="read_only",
                canonical_orientation_class_reuse=True,
            )
            persistent = warm.build_audit[
                "persistent_condensed_class_cache"
            ]
            self.assertEqual(
                persistent["hit_count_sum"],
                warm.build_audit["oriented_schur_class_count_sum"],
            )
            self.assertEqual(persistent["construction_count_sum"], 0)
            audit = warm.build_audit[
                "canonical_orientation_class_reuse"
            ]
            self.assertEqual(
                audit["used_cell_permutations"],
                audit["qualified_cell_permutations"],
            )
            self.assertTrue(audit["used_set_equals_qualified_set"])
            self.assertEqual(
                audit["canonical_class_construction_count_sum"],
                0,
            )
            self.assertEqual(audit["oriented_class_derived_count_sum"], 0)
            self.assertEqual(audit["aii_factorizations_avoided_sum"], 0)
            self.assertEqual(
                len(
                    {
                        id(factor[0])
                        for factor in warm.interior_lu_by_class.values()
                    }
                ),
                1,
            )
            self.assertEqual(
                audit["persistent_lu_alias_restore_count_sum"],
                persistent["hit_count_sum"] - 1,
            )
            warm.destroy()
            cold.destroy()

    @unittest.skipUnless(
        os.environ.get(
            "MYFENICS_TASK035B_CANONICAL_ORIENTATION_P5P6_TEST"
        )
        == "1",
        "set the explicit high-order canonical-orientation test opt-in",
    )
    def test_actual_p5trace_p6interior_operator_equivalence(self) -> None:
        self._assert_actual_operator_equivalence(
            fixed_trace_hcurl_ufl_element(5, 6)
        )


if __name__ == "__main__":
    unittest.main()
