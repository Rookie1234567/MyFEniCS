from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile

import basix.ufl
from dolfinx import fem, mesh
from dolfinx.fem import petsc as fem_petsc
from mpi4py import MPI
import numpy as np
from petsc4py import PETSc
import pytest

from src.solvers.dtn_surface_vector_cache import (
    PersistentDtnSurfaceVectorCache,
    dtn_surface_vector_descriptor,
)


def _mesh_space_and_tags(
    comm: MPI.Intracomm,
    *,
    top_tag: int = 16,
):
    msh = mesh.create_unit_cube(
        comm,
        2,
        1,
        1,
        cell_type=mesh.CellType.hexahedron,
    )
    tdim = msh.topology.dim
    fdim = tdim - 1
    owned_cells = int(msh.topology.index_map(tdim).size_local)
    cell_indices = np.arange(owned_cells, dtype=np.int32)
    cell_tags = mesh.meshtags(
        msh,
        tdim,
        cell_indices,
        np.full(owned_cells, 1, dtype=np.int32),
    )
    bottom = mesh.locate_entities_boundary(
        msh,
        fdim,
        lambda x: np.isclose(x[2], 0.0),
    )
    top = mesh.locate_entities_boundary(
        msh,
        fdim,
        lambda x: np.isclose(x[2], 1.0),
    )
    facet_indices = np.concatenate((bottom, top)).astype(
        np.int32,
        copy=False,
    )
    facet_values = np.concatenate(
        (
            np.full(len(bottom), 15, dtype=np.int32),
            np.full(len(top), top_tag, dtype=np.int32),
        )
    )
    order = np.argsort(facet_indices)
    facet_tags = mesh.meshtags(
        msh,
        fdim,
        facet_indices[order],
        facet_values[order],
    )
    element = basix.ufl.element(
        "N1curl",
        msh.basix_cell(),
        2,
        dtype=np.float64,
    )
    V = fem.functionspace(msh, element)
    return (
        SimpleNamespace(
            mesh=msh,
            cell_tags=cell_tags,
            facet_tags=facet_tags,
        ),
        V,
    )


def _trace_constraints(V, *, coefficient: complex = 1.0):
    index_map = V.dofmap.index_map
    size = int(index_map.size_global * V.dofmap.index_map_bs)
    start, stop = map(int, index_map.local_range)
    expansion = {
        row: (
            np.asarray([row], dtype=PETSc.IntType),
            np.asarray([coefficient], dtype=np.complex128),
        )
        for row in range(size)
    }
    return SimpleNamespace(
        expansion_by_original=expansion,
        full_trace_rows=size,
        active_rows=size,
        slave_rows=0,
        active_coordinates_are_original_trace_dofs=True,
        owned_active_rows=np.arange(
            start,
            stop,
            dtype=PETSc.IntType,
        ),
        build_audit={
            "schema_version": "test.trace-constraint-map.v1",
            "inactive_modes_have_no_petsc_rows": True,
        },
    )


def _descriptors(*, alpha: complex = 0.25 + 0.0j):
    return tuple(
        dtn_surface_vector_descriptor(
            side="top",
            m=-4,
            n=0,
            alpha=alpha,
            gamma=0.0 + 0.0j,
            kz=0.5 + 0.1j,
            boundary_referenced=False,
            boundary_reference_z=None,
            boundary_tag=16,
            component=component,
        )
        for component in (0, 1)
    )


def _mode_inventory(*, alpha: complex = 0.25 + 0.0j):
    return [
        {
            "schema_version": "test.dtn-mode-identity.v1",
            "side": "top",
            "m": -4,
            "n": 0,
            "polarization": polarization,
            "alpha": alpha,
            "gamma": 0.0 + 0.0j,
            "k_vector": np.asarray(
                [alpha, 0.0 + 0.0j, 0.5 + 0.1j],
                dtype=np.complex128,
            ),
        }
        for polarization in ("s", "p")
    ]


def _reduced_operator_identity(
    *,
    content_sha256: str = "c" * 64,
):
    return {
        "schema_version": (
            "task035b.dtn-reduced-operator-identity.v1"
        ),
        "content_sha256": content_sha256,
        "cell_recovery_map_content_sha256": "d" * 64,
        "cell_recovery_map_count": 2,
        "class_array_count": 5,
        "dimensions": {
            "full_rows": 1,
            "trace_rows": 1,
            "active_rows": 1,
            "appended_rows": 0,
            "interior_rows": 0,
            "active_interior_rows": 0,
        },
        "material_and_tensor_content_bound": True,
        "aii_factor_and_primal_dual_projection_content_bound": True,
    }


def _vector(V, component: int) -> tuple[PETSc.Vec, np.ndarray]:
    vector = fem_petsc.create_vector(V)
    start, stop = map(int, vector.getOwnershipRange())
    rows = np.arange(start, stop, dtype=np.float64)
    expected = (
        rows
        + float(component + 1) / 7.0
        + 1j * (rows + float(component + 1) / 11.0)
    ).astype(np.complex128)
    vector.getArray()[:] = expected
    vector.ghostUpdate(
        addv=PETSc.InsertMode.INSERT_VALUES,
        mode=PETSc.ScatterMode.FORWARD,
    )
    return vector, expected


def _reduced_modal_bundle(trace_constraints):
    rows = np.asarray(
        trace_constraints.owned_active_rows,
        dtype=PETSc.IntType,
    )
    right = tuple(
        (
            rows.copy(),
            np.asarray(
                (component + 1) * 0.125 + 1j * (rows.astype(np.float64) + 0.25),
                dtype=np.complex128,
            ),
        )
        for component in range(2)
    )
    left = tuple(
        (
            rows.copy(),
            np.asarray(
                -(component + 1) * 0.375 + 1j * (rows.astype(np.float64) + 0.5),
                dtype=np.complex128,
            ),
        )
        for component in range(2)
    )
    bilinear = np.asarray(
        [
            [1.25 + 0.5j, -0.75 + 0.125j],
            [0.25 - 0.375j, 2.0 + 0.0j],
        ],
        dtype=np.complex128,
    )
    return right, left, bilinear


def _record_reduced_modal_bundle(
    cache: PersistentDtnSurfaceVectorCache,
    descriptors,
    trace_constraints,
) -> tuple[
    tuple[tuple[np.ndarray, np.ndarray], ...],
    tuple[tuple[np.ndarray, np.ndarray], ...],
    np.ndarray,
]:
    right, left, bilinear = _reduced_modal_bundle(trace_constraints)
    cache.record_reduced_modal_bundle(
        descriptors,
        right_entries=right,
        left_entries=left,
        interior_bilinear=bilinear,
    )
    return right, left, bilinear


@contextmanager
def _shared_temporary_directory(comm: MPI.Intracomm):
    holder = tempfile.TemporaryDirectory() if comm.rank == 0 else None
    path = Path(
        comm.bcast(
            None if holder is None else holder.name,
            root=0,
        )
    )
    try:
        yield path
    finally:
        comm.barrier()
        if holder is not None:
            holder.cleanup()


def _cache(
    *,
    V,
    mesh_data,
    trace_constraints,
    descriptors,
    directory: Path,
    mode: str,
    source_sha: str = "a" * 40,
    quadrature_degree: int = 12,
    mode_inventory=None,
    reduced_operator_identity=None,
) -> PersistentDtnSurfaceVectorCache:
    return PersistentDtnSurfaceVectorCache(
        function_space=V,
        mesh_data=mesh_data,
        trace_constraints=trace_constraints,
        reduced_operator_identity=(
            _reduced_operator_identity()
            if reduced_operator_identity is None
            else reduced_operator_identity
        ),
        descriptors=descriptors,
        mode_inventory=(
            _mode_inventory()
            if mode_inventory is None
            else mode_inventory
        ),
        quadrature_degree=quadrature_degree,
        directory=directory,
        source_sha=source_sha,
        mode=mode,
    )


def _cold_then_warm_exact_roundtrip(comm: MPI.Intracomm) -> None:
    mesh_data, V = _mesh_space_and_tags(comm)
    descriptors = _descriptors()
    constraints = _trace_constraints(V)
    with _shared_temporary_directory(comm) as directory:
        cold = _cache(
            V=V,
            mesh_data=mesh_data,
            trace_constraints=constraints,
            descriptors=descriptors,
            directory=directory,
            mode="read_write",
        )
        assert cold.load() is False
        expected: list[np.ndarray] = []
        for component, descriptor in enumerate(descriptors):
            vector, owned = _vector(V, component)
            expected.append(owned)
            cold.record_vector(descriptor, vector)
            vector.destroy()
        expected_right, expected_left, expected_bilinear = _record_reduced_modal_bundle(
            cold,
            descriptors,
            constraints,
        )
        cold_audit = cold.finalize()
        assert cold_audit["hit_count_sum"] == 0
        assert cold_audit["write_count_sum"] == comm.size
        assert cold_audit["record_count_sum"] == 2 * comm.size
        assert cold_audit["reduced_bundle_record_count_sum"] == (comm.size)
        comm.barrier()

        warm = _cache(
            V=V,
            mesh_data=mesh_data,
            trace_constraints=constraints,
            descriptors=descriptors,
            directory=directory,
            mode="read_only",
        )
        assert warm.load() is True
        for descriptor, reference in zip(
            descriptors,
            expected,
            strict=True,
        ):
            restored = warm.restore_vector(descriptor)
            assert np.array_equal(
                restored.getArray(readonly=True),
                reference,
            )
            restored.destroy()
        restored_right, restored_left, restored_bilinear = (
            warm.restore_reduced_modal_bundle(descriptors)
        )
        for actual_entries, expected_entries in (
            (restored_right, expected_right),
            (restored_left, expected_left),
        ):
            for actual, reference in zip(
                actual_entries,
                expected_entries,
                strict=True,
            ):
                assert np.array_equal(actual[0], reference[0])
                assert np.array_equal(actual[1], reference[1])
        assert np.array_equal(
            restored_bilinear,
            expected_bilinear,
        )
        warm_audit = warm.finalize()
        assert warm_audit["hit_on_all_ranks"] is True
        assert warm_audit["hit_count_sum"] == comm.size
        assert warm_audit["restore_count_sum"] == 2 * comm.size
        assert warm_audit["reduced_bundle_restore_count_sum"] == (comm.size)
        assert warm_audit["material_and_tensor_identity_bound"] is True
        assert warm_audit["legacy_v1_payload_compatible"] is False
        assert warm_audit["trace_projection_recomputed_after_restore"] is False
        assert warm_audit["ordinary_default_changed"] is False
        comm.barrier()
        if comm.rank == 0:
            assert len(list(directory.glob("dtn_reduced_modal_*.npz"))) == comm.size
            assert len(list(directory.glob("dtn_reduced_modal_*.json"))) == comm.size


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 1,
    reason="serial persistent-cache roundtrip",
)
def test_serial_exact_roundtrip_and_manifest_last_cache() -> None:
    _cold_then_warm_exact_roundtrip(MPI.COMM_WORLD)


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 1,
    reason="serial duplicate-record fail-closed control",
)
def test_duplicate_surface_vector_record_is_rejected() -> None:
    comm = MPI.COMM_WORLD
    mesh_data, V = _mesh_space_and_tags(comm)
    descriptors = _descriptors()
    constraints = _trace_constraints(V)
    with _shared_temporary_directory(comm) as directory:
        cold = _cache(
            V=V,
            mesh_data=mesh_data,
            trace_constraints=constraints,
            descriptors=descriptors,
            directory=directory,
            mode="read_write",
        )
        assert cold.load() is False
        vector, _ = _vector(V, 0)
        cold.record_vector(descriptors[0], vector)
        with pytest.raises(
            RuntimeError,
            match="component was recorded twice",
        ):
            cold.record_vector(descriptors[0], vector)
        vector.destroy()


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 2,
    reason="MPI2 rank-partition-bound persistent-cache roundtrip",
)
def test_mpi2_exact_roundtrip_on_every_rank() -> None:
    _cold_then_warm_exact_roundtrip(MPI.COMM_WORLD)


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 2,
    reason="MPI2 single-rank artifact failure control",
)
def test_mpi2_single_rank_failure_forces_collective_rebuild() -> None:
    comm = MPI.COMM_WORLD
    mesh_data, V = _mesh_space_and_tags(comm)
    descriptors = _descriptors()
    constraints = _trace_constraints(V)

    def record_all(cache: PersistentDtnSurfaceVectorCache) -> None:
        for component, descriptor in enumerate(descriptors):
            vector, _ = _vector(V, component)
            cache.record_vector(descriptor, vector)
            vector.destroy()
        _record_reduced_modal_bundle(
            cache,
            descriptors,
            constraints,
        )

    with _shared_temporary_directory(comm) as directory:
        cold = _cache(
            V=V,
            mesh_data=mesh_data,
            trace_constraints=constraints,
            descriptors=descriptors,
            directory=directory,
            mode="read_write",
        )
        assert cold.load() is False
        record_all(cold)
        cold.finalize()
        comm.barrier()

        if comm.rank == 0:
            cold.payload_path.unlink()
        comm.barrier()
        deleted = _cache(
            V=V,
            mesh_data=mesh_data,
            trace_constraints=constraints,
            descriptors=descriptors,
            directory=directory,
            mode="read_write",
        )
        assert deleted.load() is False
        # Rank 1 had a valid local artifact, but it must discard that hit
        # and enter the same rebuild branch as rank 0.
        assert deleted.hit is False
        record_all(deleted)
        deleted_audit = deleted.finalize()
        assert deleted_audit["collective_all_or_nothing"] is True
        assert deleted_audit["hit_count_sum"] == 0
        assert deleted_audit["miss_count_sum"] == comm.size
        assert deleted_audit["local_artifact_hit_count_sum"] == 1
        assert deleted_audit["record_count_sum"] == 2 * comm.size
        assert deleted_audit["reduced_bundle_record_count_sum"] == comm.size
        assert deleted_audit["write_count_sum"] == comm.size
        assert (
            "artifact_or_manifest_missing"
            in deleted_audit["global_collective_miss_reasons"]
        )
        assert (
            "collective_peer_artifact_miss"
            in deleted_audit["miss_reasons_by_rank"]
        )
        comm.barrier()

        if comm.rank == 1:
            manifest = json.loads(
                deleted.manifest_path.read_text(encoding="utf-8")
            )
            manifest["content_sha256"] = "f" * 64
            deleted.manifest_path.write_text(
                json.dumps(
                    manifest,
                    ensure_ascii=True,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n",
                encoding="utf-8",
            )
        comm.barrier()
        corrupt = _cache(
            V=V,
            mesh_data=mesh_data,
            trace_constraints=constraints,
            descriptors=descriptors,
            directory=directory,
            mode="read_write",
        )
        assert corrupt.load() is False
        assert corrupt.hit is False
        record_all(corrupt)
        corrupt_audit = corrupt.finalize()
        assert corrupt_audit["local_artifact_hit_count_sum"] == 1
        assert corrupt_audit["hit_count_sum"] == 0
        assert corrupt_audit["write_count_sum"] == comm.size
        assert (
            "payload_checksum_mismatch"
            in corrupt_audit["global_collective_miss_reasons"]
        )
        comm.barrier()

        repaired = _cache(
            V=V,
            mesh_data=mesh_data,
            trace_constraints=constraints,
            descriptors=descriptors,
            directory=directory,
            mode="read_only",
        )
        assert repaired.load() is True
        for component, descriptor in enumerate(descriptors):
            restored = repaired.restore_vector(descriptor)
            expected_vector, expected = _vector(V, component)
            assert np.array_equal(
                restored.getArray(readonly=True),
                expected,
            )
            restored.destroy()
            expected_vector.destroy()
        repaired.restore_reduced_modal_bundle(descriptors)
        repaired_audit = repaired.finalize()
        assert repaired_audit["hit_on_all_ranks"] is True
        assert repaired_audit[
            "local_artifact_hit_on_all_ranks"
        ] is True


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 2,
    reason="MPI2 small DtN cold/warm integration check",
)
def test_mpi2_small_dtn_cold_warm_numerical_equivalence() -> None:
    from dataclasses import replace

    from src.common.config_3d import target_stage4_config
    from src.solvers.solve_maxwell_3d_stage_4b_block_grating import (
        run_stage4b_block_grating_3d_case,
    )

    comm = MPI.COMM_WORLD
    with _shared_temporary_directory(comm) as directory:
        cache_directory = directory / "cache"
        base = replace(
            target_stage4_config(degree=2, h_nm=100.0),
            case_name="task035b_dtn_surface_cache_cold_mpi2",
            matrix_diagnostics_assemble_only=False,
            matrix_diagnostics_factorization_only=False,
            stage4_cell_static_condensation=True,
            stage4_assembly_time_cell_static_condensation=True,
            stage4_floquet_slave_elimination=True,
            stage4_affine_isotropic_reference_tensor=True,
            stage4_condensed_cache_directory=str(cache_directory),
            stage4_condensed_cache_source_sha="a" * 40,
            stage4_condensed_cache_mode="read_write",
            stage4_condensed_persistent_dtn_surface_cache=True,
            direct_release_base_after_augmentation=True,
            direct_release_solver_before_postprocess=True,
            unique_output=False,
        )
        cold = run_stage4b_block_grating_3d_case(
            base,
            directory / "cold_run",
        )
        warm = run_stage4b_block_grating_3d_case(
            replace(
                base,
                case_name="task035b_dtn_surface_cache_warm_mpi2",
                stage4_condensed_cache_mode="read_only",
            ),
            directory / "warm_run",
        )

        cold_cache = cold[
            "stage4_dtn_surface_vector_persistent_cache"
        ]
        warm_cache = warm[
            "stage4_dtn_surface_vector_persistent_cache"
        ]
        assert cold_cache["write_count_sum"] == comm.size
        assert cold_cache["record_count_sum"] == (
            comm.size * cold_cache["descriptor_count_per_rank"]
        )
        assert cold_cache["reduced_bundle_record_count_sum"] == (
            comm.size * cold_cache["surface_order_count_per_rank"]
        )
        assert cold["stage4_dtn_component_vector_assemblies"] > 0
        assert warm_cache["hit_on_all_ranks"] is True
        assert warm_cache["hit_count_sum"] == comm.size
        assert warm["stage4_dtn_component_vector_assemblies"] == 0
        assert (
            warm["stage4_dtn_persistent_reduced_modal_bundle_restores"]
            == warm_cache["surface_order_count_per_rank"]
        )
        assert warm_cache["reduced_bundle_restore_count_sum"] == (
            comm.size * warm_cache["surface_order_count_per_rank"]
        )
        assert (
            warm_cache["restore_count_sum"]
            + warm_cache["unrestored_full_vector_array_count_sum"]
            == comm.size * warm_cache["descriptor_count_per_rank"]
        )
        assert warm_cache["trace_projection_recomputed_after_restore"] is False
        assert warm_cache["cell_interior_bilinear_recomputed_after_restore"] is False
        assert (
            cold["matrix_stats"]["matrix_rows"] == warm["matrix_stats"]["matrix_rows"]
        )
        assert (
            cold["matrix_stats"]["matrix_nnz_used"]
            == warm["matrix_stats"]["matrix_nnz_used"]
        )
        assert cold["linear_system_relative_residual"] <= 1.0e-9
        assert warm["linear_system_relative_residual"] <= 1.0e-9
        for observable in ("R00_total", "R_total", "T_total"):
            assert np.isclose(
                cold[observable],
                warm[observable],
                rtol=1.0e-13,
                atol=1.0e-13,
        )


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 2,
    reason="MPI2 collective reduced-bundle validation control",
)
def test_mpi2_single_rank_record_validation_fails_collectively() -> None:
    comm = MPI.COMM_WORLD
    mesh_data, V = _mesh_space_and_tags(comm)
    descriptors = _descriptors()
    constraints = _trace_constraints(V)
    with _shared_temporary_directory(comm) as directory:
        cold = _cache(
            V=V,
            mesh_data=mesh_data,
            trace_constraints=constraints,
            descriptors=descriptors,
            directory=directory,
            mode="read_write",
        )
        assert cold.load() is False
        right, left, bilinear = _reduced_modal_bundle(constraints)
        if comm.rank == 0:
            invalid_rows = np.asarray(
                [cold._active_ownership_range[1]],
                dtype=PETSc.IntType,
            )
            right = (
                (
                    invalid_rows,
                    np.ones(1, dtype=np.complex128),
                ),
                right[1],
            )
        with pytest.raises(
            RuntimeError,
            match=(
                "collective DtN reduced-modal bundle validation failed: "
                "rank 0"
            ),
        ):
            cold.record_reduced_modal_bundle(
                descriptors,
                right_entries=right,
                left_entries=left,
                interior_bilinear=bilinear,
            )
        assert not cold._recorded


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 1,
    reason="serial identity invalidation controls",
)
def test_identity_changes_and_corruption_fail_closed_to_miss() -> None:
    comm = MPI.COMM_WORLD
    mesh_data, V = _mesh_space_and_tags(comm)
    descriptors = _descriptors()
    constraints = _trace_constraints(V)
    with _shared_temporary_directory(comm) as directory:
        cold = _cache(
            V=V,
            mesh_data=mesh_data,
            trace_constraints=constraints,
            descriptors=descriptors,
            directory=directory,
            mode="read_write",
        )
        assert cold.load() is False
        for component, descriptor in enumerate(descriptors):
            vector, _ = _vector(V, component)
            cold.record_vector(descriptor, vector)
            vector.destroy()
        _record_reduced_modal_bundle(
            cold,
            descriptors,
            constraints,
        )
        cold.finalize()

        controls = (
            {
                "quadrature_degree": 13,
            },
            {
                "source_sha": "b" * 40,
            },
            {
                "descriptors": _descriptors(alpha=0.3 + 0.0j),
                "mode_inventory": _mode_inventory(
                    alpha=0.3 + 0.0j
                ),
            },
            {
                "trace_constraints": _trace_constraints(
                    V,
                    coefficient=0.5 + 0.25j,
                ),
            },
            {
                "reduced_operator_identity": (
                    _reduced_operator_identity(
                        content_sha256="e" * 64,
                    )
                ),
            },
        )
        for overrides in controls:
            candidate = _cache(
                V=V,
                mesh_data=mesh_data,
                trace_constraints=overrides.get(
                    "trace_constraints",
                    constraints,
                ),
                descriptors=overrides.get(
                    "descriptors",
                    descriptors,
                ),
                directory=directory,
                mode="read_only",
                source_sha=overrides.get("source_sha", "a" * 40),
                quadrature_degree=overrides.get(
                    "quadrature_degree",
                    12,
                ),
                mode_inventory=overrides.get("mode_inventory"),
                reduced_operator_identity=overrides.get(
                    "reduced_operator_identity",
                ),
            )
            assert candidate.load() is False
            audit = candidate.finalize()
            assert audit["hit_count_sum"] == 0
            assert audit["miss_count_sum"] == 1

        changed_mesh_data = SimpleNamespace(
            mesh=mesh_data.mesh,
            cell_tags=mesh_data.cell_tags,
            facet_tags=mesh.meshtags(
                mesh_data.mesh,
                mesh_data.mesh.topology.dim - 1,
                np.asarray(
                    mesh_data.facet_tags.indices,
                    dtype=np.int32,
                ),
                np.asarray(
                    mesh_data.facet_tags.values,
                    dtype=np.int32,
                )
                + 100,
            ),
        )
        changed_boundary = _cache(
            V=V,
            mesh_data=changed_mesh_data,
            trace_constraints=constraints,
            descriptors=descriptors,
            directory=directory,
            mode="read_only",
        )
        assert changed_boundary.load() is False
        assert changed_boundary.finalize()["hit_count_sum"] == 0

        manifest_path = cold.manifest_path
        manifest = json.loads(
            manifest_path.read_text(encoding="utf-8")
        )
        manifest["content_sha256"] = "0" * 64
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
        corrupt = _cache(
            V=V,
            mesh_data=mesh_data,
            trace_constraints=constraints,
            descriptors=descriptors,
            directory=directory,
            mode="read_only",
        )
        assert corrupt.load() is False
        corrupt_audit = corrupt.finalize()
        assert corrupt_audit["miss_reasons_by_rank"] == [
            "payload_checksum_mismatch"
        ]
        assert (
            corrupt_audit[
                "identity_or_payload_mismatch_is_fail_closed"
            ]
            is True
        )


def test_cache_source_sha_and_descriptor_contract_fail_closed() -> None:
    if MPI.COMM_WORLD.size != 1:
        pytest.skip("serial constructor validation")
    mesh_data, V = _mesh_space_and_tags(MPI.COMM_WORLD)
    constraints = _trace_constraints(V)
    with tempfile.TemporaryDirectory() as directory:
        with pytest.raises(ValueError, match="full source Git SHA"):
            _cache(
                V=V,
                mesh_data=mesh_data,
                trace_constraints=constraints,
                descriptors=_descriptors(),
                directory=Path(directory),
                mode="read_only",
                source_sha="short",
            )
        with pytest.raises(
            ValueError,
            match="descriptors must be unique",
        ):
            descriptor = _descriptors()[0]
            _cache(
                V=V,
                mesh_data=mesh_data,
                trace_constraints=constraints,
                descriptors=(descriptor, descriptor),
                directory=Path(directory),
                mode="read_only",
            )
        with pytest.raises(
            ValueError,
            match="qualified material/tensor-bound",
        ):
            _cache(
                V=V,
                mesh_data=mesh_data,
                trace_constraints=constraints,
                descriptors=_descriptors(),
                directory=Path(directory),
                mode="read_only",
                reduced_operator_identity={
                    "schema_version": (
                        "task035b.dtn-reduced-operator-identity.v1"
                    ),
                    "content_sha256": "not-a-sha",
                    "material_and_tensor_content_bound": True,
                },
            )
