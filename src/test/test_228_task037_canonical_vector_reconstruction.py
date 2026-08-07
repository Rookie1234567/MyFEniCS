from __future__ import annotations

import pytest
from dolfinx import fem
from mpi4py import MPI

from src.common.analytic_fields_3d import electric_field_code_values
from src.constraints.floquet_3d import build_double_floquet_mpc
from src.solvers.hcurl_canonical_vector import compare_canonical_packets
from src.solvers.hcurl_canonical_vector_dolfinx import (
    compare_hcurl_fields,
    extract_canonical_full_fe_packets,
    reconstruct_canonical_full_fe_function,
)
from src.test.test_226_task037_canonical_vector_dolfinx import (
    _physical_field,
    _static_fixture,
)
from src.test.test_46_task033_high_order_floquet_topology import (
    _fixed_target_fixture,
)


def _fresh_field(function_space):
    field = fem.Function(function_space)
    field.interpolate(_physical_field)
    field.x.scatter_forward()
    return field


def test_serial_fresh_v_roundtrip_and_physical_norms():
    _mesh, source_space, source_condensed = _static_fixture(MPI.COMM_SELF)
    source = _fresh_field(source_space)
    packets, _audit = extract_canonical_full_fe_packets(
        source_space, source.x.petsc_vec, None
    )

    _fresh_mesh, fresh_space, fresh_condensed = _static_fixture(MPI.COMM_SELF)
    reference = _fresh_field(fresh_space)
    restored = reconstruct_canonical_full_fe_function(fresh_space, packets, None)
    restored_packets, _restored_audit = extract_canonical_full_fe_packets(
        fresh_space, restored.x.petsc_vec, None
    )
    coefficient_audit = compare_canonical_packets(packets, restored_packets)
    norms = compare_hcurl_fields(restored, reference)
    assert coefficient_audit["pass"], coefficient_audit
    assert norms["relative_l2"] <= 1.0e-12, norms
    assert norms["relative_curl_l2"] <= 1.0e-12, norms
    assert norms["relative_tangential_trace_mass"] <= 1.0e-12, norms
    assert norms["relative_hcurl"] <= 1.0e-12, norms
    assert norms["l2_reference_norm"] > 0.0
    assert norms["curl_reference_norm"] > 0.0
    assert norms["tangential_trace_mass_reference_norm"] > 0.0

    changed = list(packets)
    changed[0] = (changed[0][0], changed[0][1] + 0.25 + 0.1j)
    perturbed = reconstruct_canonical_full_fe_function(fresh_space, changed, None)
    perturb_norms = compare_hcurl_fields(perturbed, reference)
    assert perturb_norms["relative_l2"] > 1.0e-8
    assert perturb_norms["relative_hcurl"] > 1.0e-8
    with pytest.raises(ValueError, match="missing canonical"):
        reconstruct_canonical_full_fe_function(fresh_space, packets[:-1], None)
    with pytest.raises(ValueError, match="duplicate canonical"):
        reconstruct_canonical_full_fe_function(
            fresh_space, packets + (packets[0],), None
        )
    source_condensed.destroy()
    fresh_condensed.destroy()


def test_serial_floquet_fresh_v_roundtrip_with_phase_packets():
    cfg, source_mesh_data, source_space = _fixed_target_fixture(2, h_nm=50.0)
    source_space.mesh.topology.create_entity_permutations()
    cell_info = source_space.mesh.topology.get_cell_permutation_info()
    assert any(int(value) != 0 for value in cell_info)
    source = fem.Function(source_space)
    source.interpolate(lambda x: electric_field_code_values(cfg, x.T).T)
    source.x.scatter_forward()
    source_floquet = build_double_floquet_mpc(source_space, source_mesh_data, cfg)
    packets, _audit = extract_canonical_full_fe_packets(
        source_space, source.x.petsc_vec, source_floquet
    )
    phase_packets = [key for key, _value in packets if key[5] is not None]
    assert phase_packets
    assert {key[4][1] for key in phase_packets} >= {"x", "y", "corner"}
    assert any(key[6] != (1.0, 0.0) for key in phase_packets)

    _fresh_cfg, fresh_mesh_data, fresh_space = _fixed_target_fixture(2, h_nm=50.0)
    fresh_floquet = build_double_floquet_mpc(fresh_space, fresh_mesh_data, cfg)
    restored = reconstruct_canonical_full_fe_function(
        fresh_space, packets, fresh_floquet
    )
    reference = fem.Function(fresh_space)
    reference.interpolate(lambda x: electric_field_code_values(cfg, x.T).T)
    reference.x.scatter_forward()
    restored_packets, _restored_audit = extract_canonical_full_fe_packets(
        fresh_space, restored.x.petsc_vec, fresh_floquet
    )
    coefficient_audit = compare_canonical_packets(packets, restored_packets)
    norms = compare_hcurl_fields(restored, reference)
    assert coefficient_audit["pass"], coefficient_audit
    assert norms["relative_l2"] <= 1.0e-12, norms
    assert norms["relative_curl_l2"] <= 1.0e-12, norms
    assert norms["relative_tangential_trace_mass"] <= 1.0e-12, norms
    assert norms["relative_hcurl"] <= 1.0e-12, norms


@pytest.mark.skipif(MPI.COMM_WORLD.size != 2, reason="MPI2 fresh-V reconstruction")
def test_mpi2_global_packets_reconstruct_on_fresh_partition():
    comm = MPI.COMM_WORLD
    _mesh, source_space, source_condensed = _static_fixture(comm)
    source = _fresh_field(source_space)
    packets, _audit = extract_canonical_full_fe_packets(
        source_space, source.x.petsc_vec, None
    )
    gathered = comm.gather(packets, root=0)
    if comm.rank == 0:
        global_packets = tuple(packet for part in gathered for packet in part)
    else:
        global_packets = None
    global_packets = comm.bcast(global_packets, root=0)

    _fresh_mesh, fresh_space, fresh_condensed = _static_fixture(comm)
    reference = _fresh_field(fresh_space)
    restored = reconstruct_canonical_full_fe_function(fresh_space, global_packets, None)
    norms = compare_hcurl_fields(restored, reference)
    assert norms["relative_l2"] <= 1.0e-12, norms
    assert norms["relative_curl_l2"] <= 1.0e-12, norms
    assert norms["relative_tangential_trace_mass"] <= 1.0e-12, norms
    assert norms["relative_hcurl"] <= 1.0e-12, norms
    restored_packets, _restored_audit = extract_canonical_full_fe_packets(
        fresh_space, restored.x.petsc_vec, None
    )
    all_restored = comm.gather(restored_packets, root=0)
    if comm.rank == 0:
        merged = tuple(packet for part in all_restored for packet in part)
        audit = compare_canonical_packets(global_packets, merged)
        assert audit["pass"], audit
        assert audit["duplicate_left_count"] == 0
        assert audit["duplicate_right_count"] == 0
    comm.barrier()
    source_condensed.destroy()
    fresh_condensed.destroy()
