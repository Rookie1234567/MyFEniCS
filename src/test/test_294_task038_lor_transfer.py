"""Review V7 L1 local transfer and periodic canonical identity tests."""

from __future__ import annotations

import ast
import time
from types import SimpleNamespace

import numpy as np
import pytest
import ufl
from basix.ufl import element
from dolfinx import default_real_type, fem, mesh
from mpi4py import MPI
from petsc4py import PETSc

from src.common.config_3d import target_stage4_config
from src.constraints.floquet_3d import build_double_floquet_mpc
from src.geometry.mesh_builder_3d import (
    _mark_boundary_facets,
    _mark_cells,
    _stage4_axis_plan,
    _structured_hexa_mesh,
)
from src.solvers.fullspace_mpc_action import build_fullspace_mpc_form_action
from src.solvers.fullspace_lor_transfer import (
    LOR_BATCH_CELL_CAP,
    build_local_lor_transfer,
    build_reference_factor_lor_transfer,
)
from src.solvers.fullspace_lor_topology import (
    CanonicalLORSubedgeTopology,
    P6_H10_REFERENCE_CELL_COUNT,
    P6_H10_REFERENCE_CELL_EDGE_COUNT,
    P6_H10_REFERENCE_UNIQUE_EDGE_COUNT,
    _pack_canonical_edges,
    _phase_code,
    build_canonical_lor_subedge_topology,
)
from src.solvers.hcurl_canonical_vector_dolfinx import (
    extract_canonical_full_fe_dual_packets,
    extract_canonical_full_fe_packets,
)


def _periodic_context(comm, degree: int):
    cfg = target_stage4_config(degree=degree, h_nm=50.0)
    plan = _stage4_axis_plan(cfg, comm.size)
    msh = _structured_hexa_mesh(
        comm,
        plan.x_values,
        plan.y_values,
        plan.z_values,
        preserve_input_partition=cfg.stage4_preserve_structured_input_partition,
    )
    facet_tags, _boundary_facets = _mark_boundary_facets(msh, cfg)
    cell_tags = _mark_cells(msh, cfg)
    mesh_data = SimpleNamespace(
        mesh=msh,
        cell_tags=cell_tags,
        facet_tags=facet_tags,
    )
    V = fem.functionspace(
        msh,
        element(
            "N1curl",
            msh.basix_cell(),
            degree,
            dtype=default_real_type,
        ),
    )
    floquet = build_double_floquet_mpc(V, mesh_data, cfg)
    return cfg, mesh_data, V, floquet


def _source_field(V, floquet):
    field = fem.Function(V)
    field.interpolate(
        lambda x: np.vstack(
            (
                x[0] + 1j * (1.0 + x[1]),
                2.0 * x[1] + 1j * (2.0 + x[2]),
                -x[2] + 1j * (3.0 + x[0]),
            )
        )
    )
    floquet.mpc.homogenize(field)
    floquet.mpc.backsubstitution(field)
    field.x.scatter_forward()
    return field


def _positive_action(V, floquet):
    u = ufl.TrialFunction(V)
    v = ufl.TestFunction(V)
    form = (
        ufl.inner(ufl.curl(u), ufl.curl(v))
        + PETSc.ScalarType(2.5) * ufl.inner(u, v)
    ) * ufl.dx
    return build_fullspace_mpc_form_action(form, V, mpc=floquet.mpc)


def _packet_map(parts):
    merged = {}
    for packets in parts:
        for key, value in packets:
            if key in merged:
                raise AssertionError(f"duplicate canonical packet key {key!r}")
            merged[key] = complex(value)
    return merged


def _packet_relative(left, right):
    if set(left) != set(right):
        return np.inf
    lhs = np.asarray([left[key] for key in sorted(left, key=repr)])
    rhs = np.asarray([right[key] for key in sorted(right, key=repr)])
    return float(np.linalg.norm(lhs - rhs) / max(np.linalg.norm(rhs), np.finfo(float).tiny))


def _lor_packet_map(parts):
    merged = {}
    for ids, values in parts:
        for edge_id, value in zip(ids, values, strict=True):
            edge_id = int(edge_id)
            if edge_id in merged:
                raise AssertionError(f"duplicate owner LOR edge {edge_id}")
            merged[edge_id] = complex(value)
    return merged


def _lor_packet_relative(left, right):
    if isinstance(left, dict):
        left_ids = np.asarray(sorted(left), dtype=np.uint32)
        left_values = np.asarray([left[int(key)] for key in left_ids], dtype=np.complex128)
    else:
        left_ids, left_values = left
    right_ids, right_values = right
    if not np.array_equal(left_ids, right_ids):
        return np.inf
    return float(
        np.linalg.norm(left_values - right_values)
        / max(np.linalg.norm(right_values), np.finfo(float).tiny)
    )


def _mesh_hlor_roundtrip(V, floquet, source_field, transfer):
    """Apply H->LOR->H on every real cell, including DOLFINx orientation."""

    topology = V.mesh.topology
    cell_count = int(topology.index_map(topology.dim).size_local)
    cell_info = np.asarray(topology.get_cell_permutation_info(), dtype=np.uint32)
    roundtrip = fem.Function(V)
    multiplicity = fem.Function(V)
    roundtrip.x.array[:] = 0.0
    multiplicity.x.array[:] = 0.0
    local_max = 0.0
    for cell in range(cell_count):
        local_dofs = np.asarray(V.dofmap.cell_dofs(cell), dtype=np.int32)
        raw = np.asarray(source_field.x.array[local_dofs], dtype=np.complex128)
        canonical = raw.copy()
        V.element.Tt_apply(canonical, np.asarray([cell_info[cell]], dtype=np.uint32), 1)
        restored = transfer.lor_to_high(transfer.high_to_lor(canonical))
        stored = restored.copy()
        V.element.T_apply(stored, np.asarray([cell_info[cell]], dtype=np.uint32), 1)
        local_max = max(
            local_max,
            float(np.linalg.norm(stored - raw) / max(np.linalg.norm(raw), np.finfo(float).tiny)),
        )
        roundtrip.x.array[local_dofs] += stored
        multiplicity.x.array[local_dofs] += 1.0
    roundtrip.x.petsc_vec.ghostUpdate(
        addv=PETSc.InsertMode.ADD_VALUES, mode=PETSc.ScatterMode.REVERSE
    )
    multiplicity.x.petsc_vec.ghostUpdate(
        addv=PETSc.InsertMode.ADD_VALUES, mode=PETSc.ScatterMode.REVERSE
    )
    owned = int(V.dofmap.index_map.size_local)
    if np.any(np.real(multiplicity.x.array[:owned]) <= 0.0):
        raise AssertionError("real-cell transfer did not cover owned rows")
    roundtrip.x.array[:owned] /= multiplicity.x.array[:owned]
    roundtrip.x.petsc_vec.ghostUpdate(
        addv=PETSc.InsertMode.INSERT_VALUES, mode=PETSc.ScatterMode.FORWARD
    )
    floquet.mpc.homogenize(roundtrip)
    floquet.mpc.backsubstitution(roundtrip)
    roundtrip.x.scatter_forward()
    local_max = V.mesh.comm.allreduce(local_max, op=MPI.MAX)
    del multiplicity
    return roundtrip, float(local_max)


def _global_lor_edge_roundtrip(V, floquet, source_field, transfer):
    """Route real mesh H/LOR/H data through the production topology API."""

    comm = V.mesh.comm
    topology = build_canonical_lor_subedge_topology(V, floquet, transfer)
    local_dofs_by_cell = []
    local_max_error = 0.0
    cell_info = np.asarray(V.mesh.topology.get_cell_permutation_info(), dtype=np.uint32)
    batch_sizes = []

    def cell_chunks():
        nonlocal local_max_error
        batch_start = 0
        canonical_batch = []
        for cell in range(topology.cell_edge_ids.shape[0]):
            local_dofs = np.asarray(V.dofmap.cell_dofs(cell), dtype=np.int32)
            local_dofs_by_cell.append(local_dofs)
            raw = np.asarray(source_field.x.array[local_dofs], dtype=np.complex128).copy()
            canonical = raw.copy()
            V.element.Tt_apply(
                canonical, np.asarray([cell_info[cell]], dtype=np.uint32), 1
            )
            canonical_batch.append(canonical)
            if len(canonical_batch) == LOR_BATCH_CELL_CAP or cell + 1 == topology.cell_edge_ids.shape[0]:
                batch = np.asarray(canonical_batch, dtype=np.complex128)
                lor_batch = transfer.high_to_lor_many(batch)
                restored_batch = transfer.lor_to_high_many(lor_batch)
                errors = np.linalg.norm(restored_batch - batch, axis=1) / np.maximum(
                    np.linalg.norm(batch, axis=1), np.finfo(float).tiny
                )
                local_max_error = max(local_max_error, float(np.max(errors)))
                batch_sizes.append(len(canonical_batch))
                yield batch_start, lor_batch
                batch_start = cell + 1
                canonical_batch = []

    owner_ids, owner_values = topology.route_owner_cell_chunks(cell_chunks())
    unique_values = topology.pull_owner_unique_values(owner_ids, owner_values)

    roundtrip = fem.Function(V)
    multiplicity = fem.Function(V)
    roundtrip.x.array[:] = 0.0
    multiplicity.x.array[:] = 0.0
    for cell_start in range(0, len(local_dofs_by_cell), LOR_BATCH_CELL_CAP):
        cell_end = min(cell_start + LOR_BATCH_CELL_CAP, len(local_dofs_by_cell))
        pulled_lor = topology.cell_values_from_unique(
            unique_values, cell_start, cell_end
        )
        canonical_batch = transfer.lor_to_high_many(pulled_lor)
        for offset, cell in enumerate(range(cell_start, cell_end)):
            local_dofs = local_dofs_by_cell[cell]
            stored = canonical_batch[offset].copy()
            V.element.T_apply(stored, np.asarray([cell_info[cell]], dtype=np.uint32), 1)
            roundtrip.x.array[local_dofs] += stored
            multiplicity.x.array[local_dofs] += 1.0
    if len(local_dofs_by_cell) >= 2:
        assert max(batch_sizes) >= 2
    roundtrip.x.petsc_vec.ghostUpdate(
        addv=PETSc.InsertMode.ADD_VALUES, mode=PETSc.ScatterMode.REVERSE
    )
    multiplicity.x.petsc_vec.ghostUpdate(
        addv=PETSc.InsertMode.ADD_VALUES, mode=PETSc.ScatterMode.REVERSE
    )
    owned = int(V.dofmap.index_map.size_local)
    roundtrip.x.array[:owned] /= multiplicity.x.array[:owned]
    roundtrip.x.petsc_vec.ghostUpdate(
        addv=PETSc.InsertMode.INSERT_VALUES, mode=PETSc.ScatterMode.FORWARD
    )
    floquet.mpc.homogenize(roundtrip)
    floquet.mpc.backsubstitution(roundtrip)
    roundtrip.x.scatter_forward()
    local_max_error = comm.allreduce(local_max_error, op=MPI.MAX)
    del multiplicity
    return roundtrip, (owner_ids, owner_values), float(local_max_error), topology


def _canonical_transfer_authority(degree: int, transfer):
    serial = MPI.COMM_SELF
    _cfg, _mesh_data, V, floquet = _periodic_context(serial, degree)
    field = _source_field(V, floquet)
    roundtrip, lor_packets, local_error, _topology = _global_lor_edge_roundtrip(
        V, floquet, field, transfer
    )
    action = _positive_action(V, floquet)
    source = field.x.petsc_vec.copy()
    mapped = roundtrip.x.petsc_vec.copy()
    observed = action.apply(source).copy()
    mapped_action = action.apply(mapped).copy()
    source_packets, _ = extract_canonical_full_fe_packets(V, source, floquet)
    mapped_packets, _ = extract_canonical_full_fe_packets(V, mapped, floquet)
    action_packets, _ = extract_canonical_full_fe_dual_packets(
        V, floquet.mpc, observed
    )
    mapped_action_packets, _ = extract_canonical_full_fe_dual_packets(
        V, floquet.mpc, mapped_action
    )
    result = (
        _packet_map((source_packets,)),
        _packet_map((mapped_packets,)),
        _packet_map((action_packets,)),
        _packet_map((mapped_action_packets,)),
        lor_packets,
        local_error,
    )
    mapped_action.destroy()
    observed.destroy()
    mapped.destroy()
    source.destroy()
    action.destroy()
    return result


@pytest.mark.parametrize("degree", [2, 3, 6])
def test_l1_single_cell_transfer_derham_and_spectral_gate(degree: int) -> None:
    transfer = build_local_lor_transfer(degree)
    audit = transfer.audit
    assert audit["high_edge_dofs"] == audit["lor_edge_dofs"]
    assert audit["high_to_lor_identity_relative"] <= 1.0e-12
    assert audit["lor_to_high_identity_relative"] <= 1.0e-12
    assert audit["repeat_exact"] is True
    assert audit["de_rham_gradient_commuting_relative"] <= 1.0e-12
    assert audit["curl_incidence_relative"] <= 1.0e-12
    assert audit["curl_face_commuting_relative"] <= 1.0e-12
    assert audit["spectral_condition"] <= 100.0
    assert np.all(np.isfinite(transfer.high_curl_face))
    assert audit["global_transfer_matrix"] is False
    assert audit["numeric_allgather"] is False
    assert audit["oracle_local_dense"] is True
    assert audit["production_local_tensor_action"] is False
    assert audit["owner_local_maps"] is False


def test_l1_spectral_condition_cross_degree_gate() -> None:
    audits = {degree: build_local_lor_transfer(degree).audit for degree in (2, 3, 6)}
    assert audits[6]["spectral_condition"] <= 2.0 * max(
        audits[2]["spectral_condition"], audits[3]["spectral_condition"]
    )


def test_l1_p6_reference_factor_action_has_bounded_retained_payload() -> None:
    dense = build_local_lor_transfer(6)
    probe = np.arange(dense.high_to_lor_matrix.shape[1], dtype=np.float64) + (
        0.125 + 0.25j
    )
    dense_lor = dense.high_to_lor(probe)
    dense_high = dense.lor_to_high(dense_lor)
    del dense

    reference = build_reference_factor_lor_transfer(6)
    factor_lor = reference.high_to_lor(probe)
    factor_high = reference.lor_to_high(factor_lor)
    batch_one_lor = reference.high_to_lor_many(probe[None, :])[0]
    batch_one_high = reference.lor_to_high_many(batch_one_lor[None, :])[0]
    batch_input = np.repeat(probe[None, :], LOR_BATCH_CELL_CAP, axis=0)
    dense_lor_batch = np.repeat(dense_lor[None, :], LOR_BATCH_CELL_CAP, axis=0)
    dense_high_batch = np.repeat(dense_high[None, :], LOR_BATCH_CELL_CAP, axis=0)
    forward_times = []
    inverse_times = []
    factor_lor_batch = None
    factor_high_batch = None
    for _ in range(3):
        started = time.perf_counter()
        factor_lor_batch = reference.high_to_lor_many(batch_input)
        forward_times.append(time.perf_counter() - started)
        started = time.perf_counter()
        factor_high_batch = reference.lor_to_high_many(factor_lor_batch)
        inverse_times.append(time.perf_counter() - started)
    assert factor_lor_batch is not None and factor_high_batch is not None
    audit = reference.audit
    forward_median = float(np.median(forward_times))
    inverse_median = float(np.median(inverse_times))
    projected_serial_wall = (54_432 // LOR_BATCH_CELL_CAP) * (
        forward_median + inverse_median
    )
    forward_relative = float(
        np.linalg.norm(factor_lor - dense_lor)
        / max(np.linalg.norm(dense_lor), np.finfo(float).tiny)
    )
    inverse_relative = float(
        np.linalg.norm(factor_high - dense_high)
        / max(np.linalg.norm(dense_high), np.finfo(float).tiny)
    )
    batch_forward_relative = float(
        np.linalg.norm(factor_lor_batch - dense_lor_batch)
        / max(np.linalg.norm(dense_lor_batch), np.finfo(float).tiny)
    )
    batch_inverse_relative = float(
        np.linalg.norm(factor_high_batch - dense_high_batch)
        / max(np.linalg.norm(dense_high_batch), np.finfo(float).tiny)
    )
    measured = {
        "build_wall_seconds": audit["reference_factor_build_wall_seconds"],
        "forward_tensor_shapes": audit["forward_tensor_shapes"],
        "inverse_tensor_shapes": audit["inverse_tensor_shapes"],
        "numeric_bytes": audit["reference_factor_numeric_bytes"],
        "index_metadata_bytes": audit["reference_factor_index_metadata_bytes"],
        "python_object_count": audit["reference_factor_python_object_count"],
        "approx_retained_bytes": audit["reference_factor_approx_retained_bytes"],
        "forward_warm_median_seconds": forward_median,
        "forward_warm_min_seconds": float(np.min(forward_times)),
        "inverse_warm_median_seconds": inverse_median,
        "inverse_warm_min_seconds": float(np.min(inverse_times)),
        "projected_54432_cell_serial_wall_seconds_derived": projected_serial_wall,
        "forward_relative": forward_relative,
        "inverse_relative": inverse_relative,
        "batch_forward_relative": batch_forward_relative,
        "batch_inverse_relative": batch_inverse_relative,
    }
    print(f"L1 p6 reference-factor metrics={measured}")
    assert audit["production_local_tensor_action"] is True
    assert audit["retained_dense_transfer_bytes"] == 0
    assert audit["dense_oracle_workspace_released"] is True
    assert audit["reference_factor_batch_cell_cap"] == LOR_BATCH_CELL_CAP
    assert forward_relative <= 1.0e-12
    assert inverse_relative <= 1.0e-12
    assert batch_forward_relative <= 1.0e-12
    assert batch_inverse_relative <= 1.0e-12
    assert np.linalg.norm(batch_one_lor - factor_lor) / max(
        np.linalg.norm(factor_lor), np.finfo(float).tiny
    ) <= 1.0e-13
    assert np.linalg.norm(batch_one_high - factor_high) / max(
        np.linalg.norm(factor_high), np.finfo(float).tiny
    ) <= 1.0e-13
    assert audit["reference_factor_repeat_relative"] <= 1.0e-13
    assert audit["reference_factor_repeat_exact"] is True
    assert audit["reference_factor_approx_retained_bytes"] < 310_000_000
    assert audit["reference_factor_python_object_count"] < 100


def test_l1_slave_edge_pack_maps_to_master_but_normal_edge_does_not() -> None:
    upper = np.asarray([3, 3, 3], dtype=np.int32)
    lower_start = np.asarray([[0, 1, 0], [0, 0, 0]], dtype=np.int32)
    lower_end = np.asarray([[0, 2, 0], [1, 0, 0]], dtype=np.int32)
    upper_start = np.asarray([[3, 1, 0], [2, 0, 0]], dtype=np.int32)
    upper_end = np.asarray([[3, 2, 0], [3, 0, 0]], dtype=np.int32)
    lower_ids, _, lower_codes = _pack_canonical_edges(
        lower_start, lower_end, upper
    )
    upper_ids, _, upper_codes = _pack_canonical_edges(
        upper_start, upper_end, upper
    )
    assert lower_ids[0] == upper_ids[0]
    assert lower_codes[0] == 0
    assert upper_codes[0] == 1
    assert lower_ids[1] != upper_ids[1]
    assert upper_codes[1] == 0
    assert _phase_code((True, False), (False, False)) == 0


def test_l1_streaming_chunk_accepts_adjacent_shared_edge_once() -> None:
    schedule = {
        "send_order": np.asarray([0, 1, 2], dtype=np.int32),
        "send_counts": np.asarray([3], dtype=np.int32),
        "receive_ids": np.asarray([1, 2, 3], dtype=np.uint32),
        "receive_counts": np.asarray([3], dtype=np.int32),
    }
    topology = CanonicalLORSubedgeTopology(
        degree=1,
        edge_count=2,
        cell_edge_ids=np.asarray([[1, 2], [2, 3]], dtype=np.uint32),
        cell_orientation=np.ones((2, 2), dtype=np.int8),
        cell_phase_codes=np.zeros((2, 2), dtype=np.uint8),
        phase_values=np.asarray([1.0 + 0.0j]),
        unique_edge_ids=np.asarray([1, 2, 3], dtype=np.uint32),
        owned_edge_ids=np.asarray([1, 2, 3], dtype=np.uint32),
        owner_schedule=schedule,
        owner_received_sort_order=np.asarray([0, 1, 2], dtype=np.int32),
        owner_received_sorted_ids=np.asarray([1, 2, 3], dtype=np.uint32),
        owner_received_group_starts=np.asarray([0, 1, 2], dtype=np.int32),
        pull_schedule=schedule,
        pull_received_positions=np.asarray([0, 1, 2], dtype=np.int32),
        pull_send_positions=np.asarray([0, 1, 2], dtype=np.int32),
        comm=MPI.COMM_SELF,
        audit={"apply_chunk_cell_cap": LOR_BATCH_CELL_CAP},
    )
    owner_ids, owner_values = topology.route_owner_cell_chunks(
        [(0, np.asarray([[1.0, 2.0], [2.0, 3.0]], dtype=np.complex128))]
    )
    np.testing.assert_array_equal(owner_ids, np.asarray([1, 2, 3], dtype=np.uint32))
    np.testing.assert_array_equal(
        owner_values, np.asarray([1.0, 2.0, 3.0], dtype=np.complex128)
    )
    with pytest.raises(ValueError, match="shared local edge values disagree"):
        topology.route_owner_cell_chunks(
            [(0, np.asarray([[1.0, 2.0], [4.0, 3.0]], dtype=np.complex128))]
        )


def test_l1_packed_streaming_projection_budget_is_fixed() -> None:
    assert P6_H10_REFERENCE_CELL_COUNT == 54_432
    assert P6_H10_REFERENCE_CELL_EDGE_COUNT == 882
    assert P6_H10_REFERENCE_UNIQUE_EDGE_COUNT == 173_802
    assert P6_H10_REFERENCE_CELL_COUNT * P6_H10_REFERENCE_CELL_EDGE_COUNT * 6 == 288_054_144
    assert 2 * LOR_BATCH_CELL_CAP * P6_H10_REFERENCE_CELL_EDGE_COUNT * 16 + (
        LOR_BATCH_CELL_CAP * (P6_H10_REFERENCE_CELL_EDGE_COUNT // 3) * 16
    ) == 1_053_696


def test_l1_transfer_orientation_and_repeat_are_not_hidden_by_audit() -> None:
    transfer = build_local_lor_transfer(2)
    high = np.arange(transfer.high_to_lor_matrix.shape[1], dtype=np.float64)
    high = high + 1j * (high + 0.25)
    lor_a = transfer.high_to_lor(high)
    lor_b = transfer.high_to_lor(high)
    np.testing.assert_array_equal(lor_a, lor_b)
    high_roundtrip = transfer.lor_to_high(lor_a)
    assert np.linalg.norm(high_roundtrip - high) / np.linalg.norm(high) <= 1.0e-12
    assert transfer.audit["curl_face_commuting_relative"] <= 1.0e-12
    reference = build_reference_factor_lor_transfer(2)
    reference_lor = reference.high_to_lor(high)
    reference_high = reference.lor_to_high(reference_lor)
    reference_many = reference.high_to_lor_many(
        np.repeat(high[None, :], LOR_BATCH_CELL_CAP, axis=0)
    )
    reference_many_again = reference.high_to_lor_many(
        np.repeat(high[None, :], LOR_BATCH_CELL_CAP, axis=0)
    )
    reference_many_high = reference.lor_to_high_many(reference_many)
    dense_many = np.repeat(lor_a[None, :], LOR_BATCH_CELL_CAP, axis=0)
    assert np.linalg.norm(reference_lor - lor_a) / np.linalg.norm(lor_a) <= 1.0e-12
    assert np.linalg.norm(reference_high - high_roundtrip) / np.linalg.norm(high_roundtrip) <= 1.0e-12
    assert np.linalg.norm(reference_many - dense_many) / np.linalg.norm(dense_many) <= 1.0e-12
    assert np.linalg.norm(reference_many_high - np.repeat(high_roundtrip[None, :], LOR_BATCH_CELL_CAP, axis=0)) / np.linalg.norm(reference_many_high) <= 1.0e-12
    np.testing.assert_array_equal(reference_many, reference_many_again)
    assert reference.audit["reference_factor_batch_cell_cap"] == LOR_BATCH_CELL_CAP
    assert reference.audit["production_local_tensor_action"] is True
    assert reference.audit["retained_dense_transfer_bytes"] == 0
    assert not hasattr(reference, "high_to_lor_matrix")


@pytest.mark.parametrize("degree", [2, 3])
def test_l1_periodic_mpc_canonical_source_action_identity(degree: int) -> None:
    """Exercise real-cell H/LOR/H and compare canonical packets to MPI1 authority."""

    comm = MPI.COMM_WORLD
    _cfg, _mesh_data, V, floquet = _periodic_context(comm, degree)
    field = _source_field(V, floquet)
    transfer = build_reference_factor_lor_transfer(degree)
    roundtrip, lor_packets, local_transfer_error, lor_topology = _global_lor_edge_roundtrip(
        V, floquet, field, transfer
    )
    assert local_transfer_error <= 1.0e-12
    assert lor_topology.audit["owner_local_maps"] is True
    assert (
        lor_topology.audit["numeric_owner_route"]
        == "typed_uint32_complex128_alltoallv"
    )
    assert sum(lor_topology.audit["phase_code_counts"][1:]) > 0
    assert lor_topology.audit["single_endpoint_normal_edge_count"] > 0
    assert lor_topology.audit["production_apply_streaming"] is True
    assert lor_topology.audit["per_apply_full_cell_value_array"] is False
    assert lor_topology.audit["per_apply_global_sort"] is False
    assert lor_topology.audit["apply_chunk_cell_cap"] == LOR_BATCH_CELL_CAP
    assert lor_topology.audit["projected_p6_h10_packed_map_bytes"] == 288_054_144
    assert lor_topology.audit["projected_p6_h10_transfer_batch_scratch_bytes"] == 2 * LOR_BATCH_CELL_CAP * 882 * 16
    assert (
        lor_topology.audit["apply_scratch_upper_bound_bytes"]
        < lor_topology.audit["projected_p6_h10_packed_map_bytes"]
    )
    assert _phase_code((True, False), (False, False)) == 0
    assert _phase_code((True, False), (True, False)) == 1
    assert _phase_code((False, True), (False, True)) == 2
    assert _phase_code((True, True), (True, True)) == 3
    action = _positive_action(V, floquet)
    source = field.x.petsc_vec.copy()
    mapped_source = roundtrip.x.petsc_vec.copy()
    observed = action.apply(source).copy()
    mapped_observed = action.apply(mapped_source).copy()
    repeated = action.apply(mapped_source).copy()
    source_packets, source_audit = extract_canonical_full_fe_packets(
        V, source, floquet
    )
    mapped_source_packets, _mapped_source_audit = extract_canonical_full_fe_packets(
        V, mapped_source, floquet
    )
    action_packets, action_audit = extract_canonical_full_fe_dual_packets(
        V, floquet.mpc, observed
    )
    mapped_action_packets, _mapped_action_audit = extract_canonical_full_fe_dual_packets(
        V, floquet.mpc, mapped_observed
    )
    repeated_packets, _repeat_audit = extract_canonical_full_fe_dual_packets(
        V, floquet.mpc, repeated
    )
    gathered = comm.gather(
        (source_packets, mapped_source_packets, action_packets, mapped_action_packets, repeated_packets),
        root=0,
    )
    lor_gathered = comm.gather(lor_packets, root=0)
    passed = True
    measured = {}
    if comm.rank == 0:
        source_map = _packet_map(part[0] for part in gathered)
        mapped_source_map = _packet_map(part[1] for part in gathered)
        action_map = _packet_map(part[2] for part in gathered)
        mapped_action_map = _packet_map(part[3] for part in gathered)
        repeated_map = _packet_map(part[4] for part in gathered)
        lor_map = _lor_packet_map(lor_gathered)
        passed = bool(source_map and action_map)
        measured = {
            "source_roundtrip_relative": _packet_relative(source_map, mapped_source_map),
            "action_roundtrip_relative": _packet_relative(action_map, mapped_action_map),
            "action_repeat_relative": _packet_relative(action_map, repeated_map),
            "lor_packet_count": int(len(lor_map)),
        }
        passed = passed and measured["lor_packet_count"] > 0
        passed = passed and all(
            value <= 1.0e-12
            for key, value in measured.items()
            if key.endswith("relative")
        )
        if comm.size > 1:
            serial = _canonical_transfer_authority(degree, transfer)
            measured.update(
                {
                    "mpi1_source_relative": _packet_relative(source_map, serial[0]),
                    "mpi1_mapped_source_relative": _packet_relative(mapped_source_map, serial[1]),
                    "mpi1_action_relative": _packet_relative(action_map, serial[2]),
                    "mpi1_mapped_action_relative": _packet_relative(mapped_action_map, serial[3]),
                    "mpi1_lor_relative": _lor_packet_relative(lor_map, serial[4]),
                    "mpi1_transfer_relative": float(serial[5]),
                }
            )
            passed = passed and all(
                value <= 1.0e-12
                for key, value in measured.items()
                if key.endswith("relative")
            )
    passed = comm.bcast(passed, root=0)
    measured = comm.bcast(measured, root=0)
    try:
        if comm.rank == 0:
            print(f"L1 transfer degree={degree} mpi={comm.size} metrics={measured}")
        assert passed
        assert measured["source_roundtrip_relative"] <= 1.0e-12
        assert measured["action_roundtrip_relative"] <= 1.0e-12
        assert measured["action_repeat_relative"] <= 1.0e-13
        if comm.size > 1:
            assert measured["mpi1_source_relative"] <= 1.0e-12
            assert measured["mpi1_action_relative"] <= 1.0e-12
            assert measured["mpi1_mapped_action_relative"] <= 1.0e-12
            assert measured["mpi1_lor_relative"] <= 1.0e-12
        assert source_audit["role"] == "full_fe"
        assert action_audit["role"] == "full_fe_dual"
        assert source_audit["local_duplicate_count"] == 0
        assert action_audit["local_duplicate_count"] == 0
        assert action_audit["numeric_allgather"] is False
        assert action.audit["phase_application"] == "finalized_floquet_mpc_once"
        assert action.audit["global_matrix_materialized"] is False
        assert action.audit["numeric_allgather"] is False
    finally:
        mapped_observed.destroy()
        mapped_source.destroy()
        repeated.destroy()
        observed.destroy()
        source.destroy()
        action.destroy()
        del roundtrip, transfer


def test_l1_production_contract_does_not_claim_dense_oracle_as_tensor_action() -> None:
    source = ast.parse(
        __import__("inspect").getsource(
            __import__("src.solvers.fullspace_lor_transfer", fromlist=["*"])
        )
    )
    calls = [
        node.func.attr
        for node in ast.walk(source)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"allgather", "createAIJ", "assemble_matrix"}
    ]
    assert calls == []
    module = __import__("src.solvers.fullspace_lor_transfer", fromlist=["*"])
    audit = module.build_reference_factor_lor_transfer(2).audit
    assert audit["global_transfer_matrix"] is False
    assert audit["oracle_local_dense"] is False
    assert audit["production_reference_factors_only"] is True
    assert audit["production_local_tensor_action"] is True
    assert audit["retained_dense_transfer_bytes"] == 0
