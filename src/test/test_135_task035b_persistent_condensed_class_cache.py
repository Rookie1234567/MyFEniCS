from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest

import numpy as np
import ufl
from basix.ufl import element
from mpi4py import MPI
from petsc4py import PETSc

from dolfinx import default_real_type, fem, mesh

from src.solvers import hcurl_assembly_time_condensation as assembly_time
from src.solvers.hcurl_assembly_time_condensation import (
    build_unconstrained_assembly_time_condensation,
    prepare_cell_interior_rhs_recovery,
    recover_owned_cell_interiors,
)


def _one_cell_problem():
    msh = mesh.create_unit_cube(
        MPI.COMM_SELF,
        1,
        1,
        1,
        cell_type=mesh.CellType.hexahedron,
    )
    cell_tags = mesh.meshtags(
        msh,
        msh.topology.dim,
        np.asarray([0], dtype=np.int32),
        np.asarray([1], dtype=np.int32),
    )
    V = fem.functionspace(
        msh,
        element(
            "N1curl",
            msh.basix_cell(),
            2,
            dtype=default_real_type,
        ),
    )
    u = ufl.TrialFunction(V)
    v = ufl.TestFunction(V)
    dx = ufl.Measure("dx", domain=msh, subdomain_data=cell_tags)
    compiled = fem.form(
        (
            ufl.inner(ufl.curl(u), ufl.curl(v))
            + PETSc.ScalarType(2.5 - 0.2j) * ufl.inner(u, v)
        )
        * dx(1)
    )
    return cell_tags, V, compiled


def _distributed_two_cell_problem(comm):
    msh = mesh.create_unit_cube(
        comm,
        2,
        1,
        1,
        cell_type=mesh.CellType.hexahedron,
    )
    owned_cells = msh.topology.index_map(msh.topology.dim).size_local
    cell_tags = mesh.meshtags(
        msh,
        msh.topology.dim,
        np.arange(owned_cells, dtype=np.int32),
        np.ones(owned_cells, dtype=np.int32),
    )
    V = fem.functionspace(
        msh,
        element(
            "N1curl",
            msh.basix_cell(),
            2,
            dtype=default_real_type,
        ),
    )
    u = ufl.TrialFunction(V)
    v = ufl.TestFunction(V)
    dx = ufl.Measure("dx", domain=msh, subdomain_data=cell_tags)
    compiled = fem.form(
        (
            ufl.inner(ufl.curl(u), ufl.curl(v))
            + PETSc.ScalarType(2.5 - 0.2j) * ufl.inner(u, v)
        )
        * dx(1)
    )
    return cell_tags, V, compiled


def _matrix_relative_difference(left, right) -> float:
    difference = left.copy()
    difference.axpy(
        PETSc.ScalarType(-1.0),
        right,
        structure=PETSc.Mat.Structure.SAME_NONZERO_PATTERN,
    )
    relative = difference.norm() / max(right.norm(), 1.0e-30)
    difference.destroy()
    return float(relative)


class TestTask035bPersistentCondensedClassCache(unittest.TestCase):
    def test_identity_binds_operator_tensor_orientation_policy_and_rank(
        self,
    ) -> None:
        common = {
            "source_sha": "a" * 40,
            "operator_identity": {
                "raw_tensor_backend": "unit-test",
                "form_signature": "operator-a",
            },
            "raw_key": (1, 0.5, 1.0, 1.5),
            "raw_tensor_content_sha256": (
                assembly_time._raw_tensor_content_sha256(
                    np.eye(4, dtype=np.complex128)
                )
            ),
            "cell_permutation": 3,
            "interior_policy": "high",
            "storage_element_hash": 101,
            "policy_element_hash": 101,
            "trace_positions": np.asarray([0, 1], dtype=np.int32),
            "high_interior_positions": np.asarray(
                [2, 3],
                dtype=np.int32,
            ),
            "active_trace_positions": np.asarray(
                [0, 1],
                dtype=np.int32,
            ),
            "active_interior_positions": np.asarray(
                [2, 3],
                dtype=np.int32,
            ),
            "low_to_reduced_content_sha256": None,
            "mpi_size": 4,
            "mpi_rank": 2,
        }
        baseline, payload = (
            assembly_time._persistent_condensed_class_identity(
                **common
            )
        )
        repeated, repeated_payload = (
            assembly_time._persistent_condensed_class_identity(
                **common
            )
        )
        self.assertEqual(baseline, repeated)
        self.assertEqual(payload, repeated_payload)
        self.assertEqual(
            payload["mpi_partition"],
            {"size": 4, "rank": 2},
        )

        variants = [
            {**common, "source_sha": "b" * 40},
            {
                **common,
                "operator_identity": {
                    "raw_tensor_backend": "unit-test",
                    "form_signature": "operator-b",
                },
            },
            {
                **common,
                "raw_tensor_content_sha256": (
                    assembly_time._raw_tensor_content_sha256(
                        2.0 * np.eye(4, dtype=np.complex128)
                    )
                ),
            },
            {**common, "cell_permutation": 4},
            {
                **common,
                "interior_policy": "low",
                "policy_element_hash": 99,
                "low_to_reduced_content_sha256": (
                    assembly_time._numeric_array_content_sha256(
                        np.eye(4, dtype=np.float64),
                        namespace=b"task035b.low-to-reduced.v1",
                    )
                ),
            },
            {**common, "storage_element_hash": 102},
            {**common, "mpi_rank": 1},
            {**common, "mpi_size": 8},
        ]
        for variant in variants:
            digest, _variant_payload = (
                assembly_time._persistent_condensed_class_identity(
                    **variant
                )
            )
            self.assertNotEqual(baseline, digest)

    def test_warm_hit_skips_dense_stages_and_supports_rhs_lifecycle(
        self,
    ) -> None:
        cell_tags, V, compiled = _one_cell_problem()
        with tempfile.TemporaryDirectory() as tmp:
            cache_directory = Path(tmp) / "condensed_cache"
            cold = build_unconstrained_assembly_time_condensation(
                compiled,
                V,
                cell_tags,
                persistent_cache_directory=cache_directory,
                persistent_cache_source_sha="a" * 40,
                persistent_cache_mode="read_write",
            )
            cold_audit = cold.build_audit[
                "persistent_condensed_class_cache"
            ]
            self.assertEqual(cold_audit["hit_count_sum"], 0)
            self.assertEqual(cold_audit["miss_count_sum"], 1)
            self.assertEqual(cold_audit["construction_count_sum"], 1)
            self.assertEqual(cold_audit["write_count_sum"], 1)
            self.assertEqual(cold_audit["read_attempt_count_sum"], 1)
            self.assertGreater(cold_audit["write_bytes_sum"], 0)
            self.assertTrue(
                cold_audit[
                    "compatible_with_prepared_rhs_recovery_lifecycle"
                ]
            )

            warm = build_unconstrained_assembly_time_condensation(
                compiled,
                V,
                cell_tags,
                persistent_cache_directory=cache_directory,
                persistent_cache_source_sha="a" * 40,
                persistent_cache_mode="read_only",
            )
            warm_audit = warm.build_audit[
                "persistent_condensed_class_cache"
            ]
            self.assertEqual(warm_audit["hit_count_sum"], 1)
            self.assertEqual(warm_audit["miss_count_sum"], 0)
            self.assertEqual(warm_audit["construction_count_sum"], 0)
            self.assertEqual(warm_audit["write_count_sum"], 0)
            self.assertEqual(warm_audit["read_attempt_count_sum"], 1)
            self.assertGreater(warm_audit["read_bytes_sum"], 0)
            self.assertEqual(warm.build_audit["orientation_seconds_max"], 0.0)
            self.assertEqual(warm.build_audit["aii_factor_seconds_max"], 0.0)
            self.assertEqual(warm.build_audit["aii_solve_seconds_max"], 0.0)
            self.assertEqual(
                warm.build_audit["schur_product_seconds_max"],
                0.0,
            )
            self.assertLess(
                _matrix_relative_difference(warm.matrix, cold.matrix),
                1.0e-14,
            )
            self.assertEqual(
                set(warm.interior_from_trace_by_class),
                set(cold.interior_from_trace_by_class),
            )
            for class_key in cold.interior_from_trace_by_class:
                np.testing.assert_allclose(
                    warm.interior_from_trace_by_class[class_key],
                    cold.interior_from_trace_by_class[class_key],
                    rtol=0.0,
                    atol=0.0,
                )
                np.testing.assert_allclose(
                    warm.interior_lu_by_class[class_key][0],
                    cold.interior_lu_by_class[class_key][0],
                    rtol=0.0,
                    atol=0.0,
                )
                np.testing.assert_array_equal(
                    warm.interior_lu_by_class[class_key][1],
                    cold.interior_lu_by_class[class_key][1],
                )

            full_rhs = PETSc.Vec().createSeq(
                warm.full_rows,
                comm=PETSc.COMM_SELF,
            )
            rng = np.random.default_rng(20260725)
            full_rhs.getArray()[:] = (
                rng.standard_normal(warm.full_rows)
                + 1j * rng.standard_normal(warm.full_rows)
            )
            full_rhs.assemble()
            active = np.zeros(warm.active_rows, dtype=np.complex128)
            before = recover_owned_cell_interiors(
                warm,
                active,
                full_rhs=full_rhs,
            )
            lifecycle = prepare_cell_interior_rhs_recovery(
                warm,
                full_rhs,
                release_nonprimal_caches=True,
            )
            after = recover_owned_cell_interiors(
                warm,
                active,
                full_rhs=full_rhs,
            )
            self.assertEqual(
                lifecycle["status"],
                "particular_cell_interior_rhs_prepared",
            )
            self.assertEqual(warm.interior_lu_by_class, {})
            for (before_rows, before_values), (
                after_rows,
                after_values,
            ) in zip(before, after, strict=True):
                np.testing.assert_array_equal(before_rows, after_rows)
                np.testing.assert_allclose(
                    before_values,
                    after_values,
                    rtol=2.0e-14,
                    atol=2.0e-14,
                )

            payloads = sorted(
                cache_directory.glob("condensed_class_*.npz")
            )
            manifests = sorted(
                cache_directory.glob("condensed_class_*.json")
            )
            self.assertEqual(len(payloads), 1)
            self.assertEqual(len(manifests), 1)
            with np.load(payloads[0], allow_pickle=False) as archive:
                tampered = {
                    name: np.asarray(archive[name]).copy()
                    for name in archive.files
                }
            tampered["schur"][0, 0] += 1.0
            with payloads[0].open("wb") as stream:
                np.savez(stream, **tampered)

            recomputed = build_unconstrained_assembly_time_condensation(
                compiled,
                V,
                cell_tags,
                persistent_cache_directory=cache_directory,
                persistent_cache_source_sha="a" * 40,
                persistent_cache_mode="read_only",
            )
            recomputed_audit = recomputed.build_audit[
                "persistent_condensed_class_cache"
            ]
            self.assertEqual(recomputed_audit["hit_count_sum"], 0)
            self.assertEqual(recomputed_audit["miss_count_sum"], 1)
            self.assertEqual(
                recomputed_audit["construction_count_sum"],
                1,
            )
            self.assertIn(
                next(iter(recomputed_audit["miss_reasons"])),
                {"payload_size_mismatch", "payload_checksum_mismatch"},
            )
            self.assertLess(
                _matrix_relative_difference(
                    recomputed.matrix,
                    cold.matrix,
                ),
                1.0e-14,
            )

            invalidated = build_unconstrained_assembly_time_condensation(
                compiled,
                V,
                cell_tags,
                persistent_cache_directory=cache_directory,
                persistent_cache_source_sha="b" * 40,
                persistent_cache_mode="read_only",
            )
            invalidated_audit = invalidated.build_audit[
                "persistent_condensed_class_cache"
            ]
            self.assertEqual(invalidated_audit["hit_count_sum"], 0)
            self.assertEqual(invalidated_audit["miss_count_sum"], 1)
            self.assertEqual(
                invalidated_audit["construction_count_sum"],
                1,
            )

            invalidated.destroy()
            recomputed.destroy()
            full_rhs.destroy()
            warm.destroy()
            cold.destroy()

    @unittest.skipUnless(
        MPI.COMM_WORLD.size == 2,
        "MPI2 rank-bound persistent cache check",
    )
    def test_mpi2_shared_directory_uses_disjoint_rank_artifacts(
        self,
    ) -> None:
        comm = MPI.COMM_WORLD
        temporary = (
            tempfile.mkdtemp(prefix="task035b-condensed-cache-")
            if comm.rank == 0
            else None
        )
        cache_directory = Path(comm.bcast(temporary, root=0))
        cell_tags, V, compiled = _distributed_two_cell_problem(comm)
        try:
            cold = build_unconstrained_assembly_time_condensation(
                compiled,
                V,
                cell_tags,
                persistent_cache_directory=cache_directory,
                persistent_cache_source_sha="c" * 40,
                persistent_cache_mode="read_write",
            )
            cold_audit = cold.build_audit[
                "persistent_condensed_class_cache"
            ]
            self.assertEqual(cold_audit["hit_count_sum"], 0)
            self.assertEqual(cold_audit["miss_count_sum"], 2)
            self.assertEqual(cold_audit["write_count_sum"], 2)
            self.assertEqual(cold_audit["read_attempt_count_sum"], 2)
            comm.Barrier()
            if comm.rank == 0:
                manifests = sorted(
                    cache_directory.glob("condensed_class_*.json")
                )
                self.assertEqual(len(manifests), 2)
                partitions = set()
                for manifest_path in manifests:
                    with manifest_path.open(
                        "r",
                        encoding="utf-8",
                    ) as stream:
                        manifest = json.load(stream)
                    partitions.add(
                        (
                            manifest["identity"]["mpi_partition"]["size"],
                            manifest["identity"]["mpi_partition"]["rank"],
                        )
                    )
                self.assertEqual(partitions, {(2, 0), (2, 1)})

            warm = build_unconstrained_assembly_time_condensation(
                compiled,
                V,
                cell_tags,
                persistent_cache_directory=cache_directory,
                persistent_cache_source_sha="c" * 40,
                persistent_cache_mode="read_only",
            )
            warm_audit = warm.build_audit[
                "persistent_condensed_class_cache"
            ]
            self.assertEqual(warm_audit["hit_count_sum"], 2)
            self.assertEqual(warm_audit["miss_count_sum"], 0)
            self.assertEqual(warm_audit["construction_count_sum"], 0)
            self.assertEqual(warm_audit["read_attempt_count_sum"], 2)
            self.assertEqual(warm.build_audit["orientation_seconds_max"], 0.0)
            self.assertEqual(warm.build_audit["aii_factor_seconds_max"], 0.0)
            self.assertEqual(warm.build_audit["aii_solve_seconds_max"], 0.0)
            self.assertEqual(
                warm.build_audit["schur_product_seconds_max"],
                0.0,
            )
            self.assertLess(
                _matrix_relative_difference(warm.matrix, cold.matrix),
                1.0e-14,
            )
            warm.destroy()
            cold.destroy()
        finally:
            comm.Barrier()
            if comm.rank == 0:
                shutil.rmtree(cache_directory)
            comm.Barrier()


if __name__ == "__main__":
    unittest.main()
