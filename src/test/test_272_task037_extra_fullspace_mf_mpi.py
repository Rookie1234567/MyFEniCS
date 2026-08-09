from __future__ import annotations

from dataclasses import replace
import shutil
import tempfile
from types import SimpleNamespace
from pathlib import Path

import dolfinx_mpc
import numpy as np
import pytest
import ufl
from basix.ufl import element
from dolfinx import default_real_type, fem, mesh
from dolfinx.la.petsc import create_vector
from mpi4py import MPI
from petsc4py import PETSc

from benchmarks.canonical_vector_artifacts import (
    canonical_shard_manifest,
    compare_canonical_manifests,
    write_canonical_manifest,
    write_canonical_packet_shard,
)
from src.common.config_3d import target_stage4_config
from src.constraints.floquet_3d import build_double_floquet_mpc
from src.constraints.floquet_3d_high_order import floquet_geometry_tolerance
from src.solvers.hcurl_canonical_vector_dolfinx import (
    iter_canonical_full_fe_dual_packets,
)
from src.solvers.fullspace_matrix_free_hcurl import (
    build_task037_extra_candidate_h_fullspace_action,
)


def _physical_cell_tags(mesh_3d, cfg) -> tuple[object, np.ndarray]:
    tdim = mesh_3d.topology.dim
    owned_cells = int(mesh_3d.topology.index_map(tdim).size_local)
    coordinates = np.asarray(mesh_3d.geometry.x, dtype=np.float64)
    x_mid = 0.5 * (float(cfg.x_min) + float(cfg.x_max))
    tags = np.empty(owned_cells, dtype=np.int32)
    for cell in range(owned_cells):
        points = np.asarray(mesh_3d.geometry.dofmap[cell], dtype=np.int32)
        center = np.mean(coordinates[points], axis=0)
        tags[cell] = 1 if float(center[0]) < x_mid else 2
    cell_tags = mesh.meshtags(
        mesh_3d,
        tdim,
        np.arange(owned_cells, dtype=np.int32),
        tags,
    )
    return cell_tags, tags


def _build_case(degree: int, comm):
    cfg = target_stage4_config(degree=degree, h_nm=1000.0)
    cfg = replace(cfg, incident_theta_deg=37.0, incident_phi_deg=23.0)
    points = (
        np.asarray(
            (cfg.x_min, cfg.y_min, cfg.domain_z_min), dtype=np.float64
        ),
        np.asarray(
            (cfg.x_max, cfg.y_max, cfg.domain_z_max), dtype=np.float64
        ),
    )
    mesh_3d = mesh.create_box(
        comm,
        points,
        (2, 2, 2),
        cell_type=mesh.CellType.hexahedron,
        ghost_mode=mesh.GhostMode.shared_facet,
    )
    fdim = mesh_3d.topology.dim - 1
    boundary_specs = (
        (cfg.tags.x_min, lambda x: np.isclose(x[0], cfg.x_min)),
        (cfg.tags.x_max, lambda x: np.isclose(x[0], cfg.x_max)),
        (cfg.tags.y_min, lambda x: np.isclose(x[1], cfg.y_min)),
        (cfg.tags.y_max, lambda x: np.isclose(x[1], cfg.y_max)),
    )
    facet_indices = []
    facet_values = []
    for tag, marker in boundary_specs:
        facets = mesh.locate_entities_boundary(mesh_3d, fdim, marker)
        facet_indices.append(facets)
        facet_values.append(np.full(len(facets), tag, dtype=np.int32))
    facet_index = np.concatenate(facet_indices).astype(np.int32)
    facet_value = np.concatenate(facet_values).astype(np.int32)
    order = np.argsort(facet_index)
    mesh_data = SimpleNamespace(
        mesh=mesh_3d,
        facet_tags=mesh.meshtags(
            mesh_3d, fdim, facet_index[order], facet_value[order]
        ),
    )
    cell_tags, tags = _physical_cell_tags(mesh_3d, cfg)
    function_space = fem.functionspace(
        mesh_3d,
        element(
            "N1curl",
            mesh_3d.basix_cell(),
            degree,
            dtype=default_real_type,
        ),
    )
    u = ufl.TrialFunction(function_space)
    v = ufl.TestFunction(function_space)
    dx = ufl.Measure("dx", domain=mesh_3d, subdomain_data=cell_tags)
    terms = []
    coefficients = {
        1: (PETSc.ScalarType(1.0 + 0.17j), PETSc.ScalarType(2.1 - 0.3j)),
        2: (PETSc.ScalarType(1.6 - 0.21j), PETSc.ScalarType(0.7 + 0.41j)),
    }
    for tag, (curl_coefficient, mass_coefficient) in coefficients.items():
        terms.append(
            (
                curl_coefficient * ufl.inner(ufl.curl(u), ufl.curl(v))
                + mass_coefficient * ufl.inner(u, v)
            )
            * dx(tag)
        )
    form = fem.form(sum(terms))
    floquet = build_double_floquet_mpc(function_space, mesh_data, cfg)
    return cfg, mesh_data, function_space, cell_tags, tags, floquet, form


def _physical_source(function_space, mpc) -> PETSc.Vec:
    field = fem.Function(function_space)
    field.interpolate(
        lambda x: np.vstack(
            (
                1.0 + 0.2 * x[0] - 0.11 * x[2],
                -0.4 + 0.13 * x[1] + 0.07 * x[2],
                0.25 + 0.09 * x[0] - 0.17 * x[1],
            )
        ).astype(np.complex128)
    )
    field.x.scatter_forward()
    source = create_vector(
        [(mpc.function_space.dofmap.index_map, mpc.function_space.dofmap.index_map_bs)]
    )
    owned = int(mpc.function_space.dofmap.index_map.size_local)
    with source.localForm() as local:
        local.set(0.0)
        local.array_w[:owned] = field.x.array[:owned]
    source.ghostUpdate(
        addv=PETSc.InsertMode.INSERT_VALUES,
        mode=PETSc.ScatterMode.FORWARD,
    )
    mpc.backsubstitution(source)
    source.ghostUpdate(
        addv=PETSc.InsertMode.INSERT_VALUES,
        mode=PETSc.ScatterMode.FORWARD,
    )
    return source


def _write_dual_shard(function_space, mpc, vector, tolerance: float, path: Path):
    return write_canonical_packet_shard(
        path,
        iter_canonical_full_fe_dual_packets(
            function_space,
            mpc,
            vector,
            geometry_tolerance=tolerance,
        ),
    )


@pytest.mark.parametrize("degree", [2, 3])
def test_fullspace_mpc_action_and_dual_packets_are_partition_invariant(degree: int):
    comm = MPI.COMM_WORLD
    if comm.size not in (1, 2):
        pytest.skip("test272 is qualified only for COMM_WORLD size 1 or 2")
    (
        cfg,
        mesh_data,
        function_space,
        cell_tags,
        tags,
        floquet,
        form,
    ) = _build_case(degree, comm)
    assembled = dolfinx_mpc.assemble_matrix(
        form, floquet.mpc, diagval=PETSc.ScalarType(1.0)
    )
    assembled.assemble()
    action = build_task037_extra_candidate_h_fullspace_action(
        form,
        function_space,
        cell_tags,
        mpc=floquet.mpc,
        task037_extra_candidate_h=True,
        geometry_tolerance=floquet_geometry_tolerance(cfg),
    )
    source = _physical_source(function_space, floquet.mpc)
    expected = assembled.createVecLeft()
    observed = assembled.createVecLeft()
    repeated = assembled.createVecLeft()
    difference = assembled.createVecLeft()
    serial_assembled = None
    serial_action = None
    serial_source = None
    serial_observed = None
    packet_root = None
    try:
        assembled.mult(source, expected)
        action.matrix.mult(source, observed)
        action.matrix.mult(source, repeated)
        observed.copy(result=difference)
        difference.axpy(PETSc.ScalarType(-1.0), expected)
        relative_error = difference.norm() / max(expected.norm(), 1.0e-30)
        assert relative_error <= 1.0e-11
        assert np.array_equal(
            observed.getArray(readonly=True), repeated.getArray(readonly=True)
        )
        assert np.all(np.isfinite(observed.getArray(readonly=True)))
        owned_size = int(function_space.dofmap.index_map.size_local)
        slave_indices = np.asarray(floquet.mpc.slaves, dtype=np.int32)
        owned_slaves = slave_indices[slave_indices < owned_size]
        np.testing.assert_array_equal(
            observed.getArray(readonly=True)[owned_slaves],
            source.getArray(readonly=True)[owned_slaves],
        )

        topology = floquet.phase_independent_topology
        assert topology is not None
        assert {block.kind for block in topology.blocks} >= {"x", "y", "corner"}
        assert {block.entity_kind for block in topology.blocks} >= {"edge", "face"}
        assert floquet.num_edge_constraints > 0
        assert floquet.num_face_constraints > 0
        assert abs(complex(floquet.phase_x) - 1.0) > 1.0e-12
        assert abs(complex(floquet.phase_y) - 1.0) > 1.0e-12
        cell_infos = np.asarray(
            mesh_data.mesh.topology.get_cell_permutation_info(), dtype=np.uint32
        )
        local_any_nonzero = bool(
            np.any(cell_infos[: mesh_data.mesh.topology.index_map(3).size_local] != 0)
        )
        assert comm.allreduce(local_any_nonzero, op=MPI.LOR)
        global_tags = set().union(*comm.allgather(set(int(tag) for tag in tags)))
        assert global_tags == {1, 2}
        assert action.audit["mpc_enabled"] is True
        assert action.audit["mpc_metadata_cached"] is True
        assert action.audit["mpc_per_apply_collective"] is False
        assert action.audit["global_constraint_matrix_materialized"] is False

        tolerance = floquet_geometry_tolerance(cfg)
        if comm.rank == 0:
            packet_root = Path(
                tempfile.mkdtemp(prefix=f"task037_h1_2_dual_p{degree}_")
            )
        packet_root = Path(
            comm.bcast(None if packet_root is None else str(packet_root), root=0)
        )
        world_shard = packet_root / f"world_rank{comm.rank}.jsonl"
        world_metadata = _write_dual_shard(
            function_space, floquet.mpc, observed, tolerance, world_shard
        )
        gathered_metadata = comm.gather(world_metadata, root=0)
        comparison = None
        if comm.rank == 0:
            world_manifest_path = packet_root / "world_manifest.json"
            world_manifest = canonical_shard_manifest(
                role="full_fe_dual",
                mpi_size=comm.size,
                shard_metadata=gathered_metadata,
                extractor_audit={"source": "candidate_action_observed"},
            )
            world_manifest_sha256 = write_canonical_manifest(
                world_manifest_path, world_manifest
            )
            if comm.size == 1:
                serial_manifest_path = world_manifest_path
                serial_manifest_sha256 = world_manifest_sha256
            else:
                (
                    serial_cfg,
                    _serial_mesh_data,
                    serial_space,
                    serial_tags,
                    _serial_tags,
                    serial_floquet,
                    serial_form,
                ) = _build_case(degree, MPI.COMM_SELF)
                serial_assembled = dolfinx_mpc.assemble_matrix(
                    serial_form,
                    serial_floquet.mpc,
                    diagval=PETSc.ScalarType(1.0),
                )
                serial_assembled.assemble()
                serial_action = build_task037_extra_candidate_h_fullspace_action(
                    serial_form,
                    serial_space,
                    serial_tags,
                    mpc=serial_floquet.mpc,
                    task037_extra_candidate_h=True,
                    geometry_tolerance=floquet_geometry_tolerance(serial_cfg),
                )
                serial_source = _physical_source(serial_space, serial_floquet.mpc)
                serial_observed = serial_assembled.createVecLeft()
                serial_action.matrix.mult(serial_source, serial_observed)
                serial_shard = packet_root / "serial_rank0.jsonl"
                serial_metadata = _write_dual_shard(
                    serial_space,
                    serial_floquet.mpc,
                    serial_observed,
                    floquet_geometry_tolerance(serial_cfg),
                    serial_shard,
                )
                serial_manifest_path = packet_root / "serial_manifest.json"
                serial_manifest = canonical_shard_manifest(
                    role="full_fe_dual",
                    mpi_size=1,
                    shard_metadata=(serial_metadata,),
                    extractor_audit={"source": "serial_reference_action"},
                )
                serial_manifest_sha256 = write_canonical_manifest(
                    serial_manifest_path, serial_manifest
                )
            comparison = compare_canonical_manifests(
                world_manifest_path,
                serial_manifest_path,
                left_sha256=world_manifest_sha256,
                right_sha256=serial_manifest_sha256,
                relative_tolerance=1.0e-11,
            )
        comparison = comm.bcast(comparison, root=0)
        assert comparison["pass"] is True
        assert comparison["duplicate_left_count"] == 0
        assert comparison["duplicate_right_count"] == 0
        assert comparison["missing_key_count"] == 0
        assert comparison["extra_key_count"] == 0
        expected_reduced_dual_rows = (
            int(action.audit["global_rows"]) - int(floquet.num_constraints)
        )
        assert comparison["left_shape"][0] == expected_reduced_dual_rows
        assert comparison["right_shape"][0] == expected_reduced_dual_rows
        packet_error = comparison["relative_coefficient_l2"]
        global_permutation_values = sorted(
            {
                int(value)
                for packet in comm.allgather(
                    [
                        int(value)
                        for value in cell_infos[
                            : int(
                                mesh_data.mesh.topology.index_map(3).size_local
                            )
                        ]
                    ]
                )
                for value in packet
            }
        )
        if comm.rank == 0:
            print(
                {
                    "degree": degree,
                    "assembled_vs_mf_relative_error": relative_error,
                    "finite": True,
                    "repeated_bitwise_equal": True,
                    "world_dual_packet_relative_error": packet_error,
                    "world_dual_packet_count": comparison["left_shape"][0],
                    "serial_dual_packet_count": comparison["right_shape"][0],
                    "missing": comparison["missing_key_count"],
                    "extra": comparison["extra_key_count"],
                    "duplicate": comparison["duplicate_left_count"],
                    "phase_x": complex(floquet.phase_x),
                    "phase_y": complex(floquet.phase_y),
                    "global_material_tags": sorted(global_tags),
                    "global_permutation_unique_values": global_permutation_values,
                    "edge_constraints": int(floquet.num_edge_constraints),
                    "face_constraints": int(floquet.num_face_constraints),
                    "global_constraints": int(floquet.num_constraints),
                    "local_constraints": len(floquet.mpc.slaves),
                    "owned_constraints": int(floquet.mpc.num_local_slaves),
                    "audit": {
                        key: action.audit[key]
                        for key in (
                            "global_rows",
                            "local_owned_rows",
                            "local_cell_count",
                            "cell_dof_count",
                            "mpc_local_slave_count",
                            "mpc_owned_slave_count",
                            "mpc_constraint_nnz",
                            "global_matrix_materialized",
                            "retained_cell_dense_matrix_count",
                            "cell_tensor_scratch_count",
                            "cell_tensor_scratch_reused",
                            "global_constraint_matrix_materialized",
                        )
                    },
                }
            )
    finally:
        if comm.rank == 0 and packet_root is not None:
            shutil.rmtree(packet_root, ignore_errors=True)
        if serial_observed is not None:
            serial_observed.destroy()
        if serial_source is not None:
            serial_source.destroy()
        if serial_action is not None:
            serial_action.destroy()
        if serial_assembled is not None:
            serial_assembled.destroy()
        difference.destroy()
        repeated.destroy()
        observed.destroy()
        expected.destroy()
        source.destroy()
        action.destroy()
        assembled.destroy()
