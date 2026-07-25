from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

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
    trim_warm_persistent_condensed_cache_heap,
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
    def test_policy_bound_projection_alias_restore(self) -> None:
        identity = np.eye(3, dtype=np.float64)

        def high_arrays() -> dict[str, np.ndarray]:
            return {
                "rhs_projection": identity.copy(),
                "solution_embedding": identity.copy(),
                "residual_projection": identity.copy(),
            }

        first, reason, bytes_elided = (
            assembly_time._restore_condensed_projection_aliases(
                high_arrays(),
                interior_policy="high",
                high_interior_identity=identity,
            )
        )
        second, second_reason, second_bytes_elided = (
            assembly_time._restore_condensed_projection_aliases(
                high_arrays(),
                interior_policy="high",
                high_interior_identity=identity,
            )
        )
        self.assertIsNone(reason)
        self.assertIsNone(second_reason)
        self.assertEqual(bytes_elided, 3 * identity.nbytes)
        self.assertEqual(second_bytes_elided, bytes_elided)
        assert first is not None
        assert second is not None
        for restored in (first, second):
            self.assertIs(restored["rhs_projection"], identity)
            self.assertIs(restored["solution_embedding"], identity)
            self.assertIs(restored["residual_projection"], identity)

        invalid_high = high_arrays()
        invalid_high["rhs_projection"][0, 0] = 2.0
        restored, reason, bytes_elided = (
            assembly_time._restore_condensed_projection_aliases(
                invalid_high,
                interior_policy="high",
                high_interior_identity=identity,
            )
        )
        self.assertIsNone(restored)
        self.assertEqual(
            reason,
            "rhs_projection_high_identity_alias_mismatch",
        )
        self.assertEqual(bytes_elided, 0)

        solution = np.arange(8, dtype=np.float64).reshape((4, 2))
        low_arrays = {
            "rhs_projection": solution.T.copy(),
            "solution_embedding": solution.copy(),
            "residual_projection": solution.T.copy(),
        }
        restored, reason, bytes_elided = (
            assembly_time._restore_condensed_projection_aliases(
                low_arrays,
                interior_policy="low",
                high_interior_identity=identity,
            )
        )
        self.assertIsNone(reason)
        assert restored is not None
        self.assertEqual(
            bytes_elided,
            2 * solution.T.nbytes,
        )
        self.assertIs(
            restored["rhs_projection"],
            restored["residual_projection"],
        )
        self.assertTrue(
            np.shares_memory(
                restored["rhs_projection"],
                restored["solution_embedding"],
            )
        )
        np.testing.assert_array_equal(
            restored["rhs_projection"],
            restored["solution_embedding"].T,
        )

        invalid_low = {
            "rhs_projection": solution.T.copy(),
            "solution_embedding": solution.copy(),
            "residual_projection": solution.T.copy(),
        }
        invalid_low["residual_projection"][0, 0] += 1.0
        restored, reason, bytes_elided = (
            assembly_time._restore_condensed_projection_aliases(
                invalid_low,
                interior_policy="low",
                high_interior_identity=identity,
            )
        )
        self.assertIsNone(restored)
        self.assertEqual(
            reason,
            "residual_projection_low_transpose_alias_mismatch",
        )
        self.assertEqual(bytes_elided, 0)

    def test_identity_binds_content_but_not_mpi_partition(
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
            payload["schema_version"],
            "task035b.persistent-condensed-class-identity.v2",
        )
        self.assertNotIn("mpi_partition", payload)

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
        ]
        for variant in variants:
            digest, _variant_payload = (
                assembly_time._persistent_condensed_class_identity(
                    **variant
                )
            )
            self.assertNotEqual(baseline, digest)

        for mpi_size, mpi_rank in ((1, 0), (2, 1), (8, 0), (8, 7)):
            digest, variant_payload = (
                assembly_time._persistent_condensed_class_identity(
                    **{
                        **common,
                        "mpi_size": mpi_size,
                        "mpi_rank": mpi_rank,
                    }
                )
            )
            self.assertEqual(baseline, digest)
            self.assertEqual(payload, variant_payload)

        with self.assertRaisesRegex(ValueError, "MPI size"):
            assembly_time._persistent_condensed_class_identity(
                **{**common, "mpi_size": 0, "mpi_rank": 0}
            )
        with self.assertRaisesRegex(ValueError, "MPI rank"):
            assembly_time._persistent_condensed_class_identity(
                **{**common, "mpi_size": 2, "mpi_rank": 2}
            )

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
            self.assertEqual(
                warm_audit["projection_alias_restore_count_sum"],
                warm_audit["hit_count_sum"],
            )
            self.assertGreater(
                warm_audit[
                    "projection_alias_retained_bytes_elided_sum"
                ],
                0,
            )
            class_key = next(
                iter(warm.interior_rhs_projection_by_class)
            )
            self.assertIs(
                warm.interior_rhs_projection_by_class[class_key],
                warm.interior_solution_embedding_by_class[class_key],
            )
            self.assertIs(
                warm.interior_rhs_projection_by_class[class_key],
                warm.interior_residual_projection_by_class[class_key],
            )
            self.assertEqual(
                warm.build_audit["native_object_ledger"][
                    "retained_rank_sum_total_bytes"
                ],
                cold.build_audit["native_object_ledger"][
                    "retained_rank_sum_total_bytes"
                ],
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
            trim_result = {
                "implementation": "glibc_malloc_trim",
                "supported": True,
                "succeeded": True,
                "return_code": 1,
                "rss_before_mb": 100.0,
                "rss_after_mb": 90.0,
                "rss_released_mb": 10.0,
                "reason": None,
            }
            with mock.patch(
                "src.solvers.common_3d_utils._trim_process_heap",
                return_value=trim_result,
            ) as trim:
                trim_audit = trim_warm_persistent_condensed_cache_heap(
                    warm
                )
            trim.assert_called_once_with()
            self.assertTrue(trim_audit["eligible"])
            self.assertTrue(trim_audit["called"])
            self.assertTrue(trim_audit["supported_on_all_ranks"])
            self.assertTrue(trim_audit["succeeded_on_all_ranks"])
            self.assertEqual(trim_audit["return_codes_by_rank"], [1])
            self.assertEqual(trim_audit["sum_rss_released_mb"], 10.0)
            self.assertFalse(trim_audit["ordinary_default_changed"])
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

    def test_high_alias_corruption_is_a_fail_closed_cache_miss(
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
                persistent_cache_source_sha="d" * 40,
                persistent_cache_mode="read_write",
            )
            payload = next(cache_directory.glob("condensed_class_*.npz"))
            manifest_path = payload.with_suffix(".json")
            with np.load(payload, allow_pickle=False) as archive:
                arrays = {
                    name: np.asarray(archive[name]).copy()
                    for name in archive.files
                }
            arrays["rhs_projection"][0, 0] += 1.0
            with payload.open("wb") as stream:
                np.savez(stream, **arrays)
            manifest = json.loads(
                manifest_path.read_text(encoding="utf-8")
            )
            manifest["payload_size_bytes"] = int(payload.stat().st_size)
            manifest["content_sha256"] = (
                assembly_time._condensed_class_content_sha256(arrays)
            )
            manifest_path.write_text(
                json.dumps(
                    manifest,
                    ensure_ascii=True,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n",
                encoding="utf-8",
            )

            recomputed = build_unconstrained_assembly_time_condensation(
                compiled,
                V,
                cell_tags,
                persistent_cache_directory=cache_directory,
                persistent_cache_source_sha="d" * 40,
                persistent_cache_mode="read_only",
            )
            audit = recomputed.build_audit[
                "persistent_condensed_class_cache"
            ]
            self.assertEqual(audit["hit_count_sum"], 0)
            self.assertEqual(audit["miss_count_sum"], 1)
            self.assertEqual(audit["construction_count_sum"], 1)
            self.assertEqual(
                audit["miss_reasons"],
                {"rhs_projection_high_identity_alias_mismatch": 1},
            )
            self.assertEqual(
                audit["projection_alias_restore_count_sum"],
                0,
            )
            self.assertLess(
                _matrix_relative_difference(
                    recomputed.matrix,
                    cold.matrix,
                ),
                1.0e-14,
            )
            recomputed.destroy()
            cold.destroy()

    def test_heap_trim_is_inert_for_ordinary_cache_off_path(
        self,
    ) -> None:
        cell_tags, V, compiled = _one_cell_problem()
        ordinary = build_unconstrained_assembly_time_condensation(
            compiled,
            V,
            cell_tags,
        )
        with mock.patch(
            "src.solvers.common_3d_utils._trim_process_heap",
        ) as trim:
            audit = trim_warm_persistent_condensed_cache_heap(ordinary)
        trim.assert_not_called()
        self.assertFalse(audit["eligible"])
        self.assertFalse(audit["called"])
        self.assertEqual(audit["reason"], "cache_disabled")
        self.assertFalse(audit["ordinary_default_changed"])
        ordinary.destroy()

    @unittest.skipUnless(
        MPI.COMM_WORLD.size == 2,
        "MPI2 shared content-addressed persistent cache check",
    )
    def test_mpi2_identical_writers_publish_one_valid_artifact(
        self,
    ) -> None:
        comm = MPI.COMM_WORLD
        temporary = (
            tempfile.mkdtemp(prefix="task035b-condensed-cache-writers-")
            if comm.rank == 0
            else None
        )
        cache_directory = Path(comm.bcast(temporary, root=0))
        identity_sha256, identity = (
            assembly_time._persistent_condensed_class_identity(
                source_sha="e" * 40,
                operator_identity={
                    "raw_tensor_backend": "unit-test",
                    "form_signature": "shared-writer",
                },
                raw_key=(1, 1.0, 1.0, 1.0),
                raw_tensor_content_sha256=(
                    assembly_time._raw_tensor_content_sha256(
                        np.eye(2, dtype=np.complex128)
                    )
                ),
                cell_permutation=0,
                interior_policy="high",
                storage_element_hash=101,
                policy_element_hash=101,
                trace_positions=np.asarray([0], dtype=np.int32),
                high_interior_positions=np.asarray([1], dtype=np.int32),
                active_trace_positions=np.asarray([0], dtype=np.int32),
                active_interior_positions=np.asarray(
                    [1],
                    dtype=np.int32,
                ),
                low_to_reduced_content_sha256=None,
                mpi_size=comm.size,
                mpi_rank=comm.rank,
            )
        )
        expected_shapes = (
            assembly_time._condensed_class_expected_shapes(
                high_interior_dimension=1,
                trace_dimension=1,
                active_interior_dimension=1,
            )
        )
        arrays = {
            "schur": np.asarray([[2.0 + 0.5j]], dtype=np.complex128),
            "interior_from_trace": np.asarray(
                [[-0.25 + 0.1j]],
                dtype=np.complex128,
            ),
            "lu_values": np.asarray(
                [[3.0 - 0.2j]],
                dtype=np.complex128,
            ),
            "lu_pivots": np.asarray([0], dtype=np.int32),
            "rhs_projection": np.asarray([[1.0]], dtype=np.float64),
            "solution_embedding": np.asarray([[1.0]], dtype=np.float64),
            "dual_interior_from_trace": np.asarray(
                [[-0.2 - 0.05j]],
                dtype=np.complex128,
            ),
            "residual_projection": np.asarray(
                [[1.0]],
                dtype=np.float64,
            ),
        }
        payload = cache_directory / (
            f"condensed_class_{identity_sha256}.npz"
        )
        manifest = payload.with_suffix(".json")
        try:
            comm.Barrier()
            assembly_time._write_persistent_condensed_class(
                payload,
                arrays,
                manifest_path=manifest,
                identity_sha256=identity_sha256,
                identity_payload=identity,
                expected_shapes=expected_shapes,
                rank=comm.rank,
            )
            comm.Barrier()
            loaded, reason = (
                assembly_time._load_persistent_condensed_class(
                    payload,
                    manifest_path=manifest,
                    expected_identity_sha256=identity_sha256,
                    expected_identity_payload=identity,
                    expected_shapes=expected_shapes,
                )
            )
            self.assertIsNone(reason)
            assert loaded is not None
            for name, expected in arrays.items():
                np.testing.assert_array_equal(loaded[name], expected)
            temporary_files = (
                sorted(path.name for path in cache_directory.glob(".*.tmp"))
                if comm.rank == 0
                else None
            )
            temporary_files = comm.bcast(temporary_files, root=0)
            self.assertEqual(temporary_files, [])
        finally:
            comm.Barrier()
            if comm.rank == 0:
                shutil.rmtree(cache_directory)
            comm.Barrier()

    @unittest.skipUnless(
        MPI.COMM_WORLD.size == 2,
        "MPI2 rank-independent persistent cache check",
    )
    def test_mpi2_shared_directory_reuses_oriented_class_artifacts(
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
            self.assertEqual(
                cold_audit["hit_count_sum"]
                + cold_audit["miss_count_sum"],
                2,
            )
            self.assertGreaterEqual(cold_audit["miss_count_sum"], 1)
            self.assertEqual(
                cold_audit["write_count_sum"],
                cold_audit["miss_count_sum"],
            )
            self.assertEqual(
                cold_audit["construction_count_sum"],
                cold_audit["miss_count_sum"],
            )
            self.assertEqual(cold_audit["read_attempt_count_sum"], 2)
            self.assertFalse(
                cold_audit["identity_is_rank_partition_bound"]
            )
            self.assertTrue(cold_audit["cross_mpi_identity_eligible"])
            self.assertTrue(cold_audit["cross_mpi_partition_reuse"])
            self.assertFalse(
                cold_audit["concurrent_independent_job_locking"]
            )
            self.assertTrue(
                cold_audit[
                    "identity_or_payload_mismatch_is_fail_closed"
                ]
            )
            comm.Barrier()
            manifest_identities = (
                [
                    json.loads(path.read_text(encoding="utf-8"))
                    for path in sorted(
                        cache_directory.glob("condensed_class_*.json")
                    )
                ]
                if comm.rank == 0
                else None
            )
            manifest_identities = comm.bcast(
                manifest_identities,
                root=0,
            )
            self.assertEqual(len(manifest_identities), 2)
            for manifest in manifest_identities:
                self.assertEqual(
                    manifest["schema_version"],
                    "task035b.condensed-class-cache-manifest.v2",
                )
                self.assertEqual(
                    manifest["identity"]["schema_version"],
                    "task035b.persistent-condensed-class-identity.v2",
                )
                self.assertNotIn(
                    "mpi_partition",
                    manifest["identity"],
                )

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
            self.assertEqual(
                warm_audit["projection_alias_restore_count_sum"],
                warm_audit["hit_count_sum"],
            )
            self.assertGreater(
                warm_audit[
                    "projection_alias_retained_bytes_elided_sum"
                ],
                0,
            )
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
