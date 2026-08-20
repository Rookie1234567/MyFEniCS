"""T5.0 owner-local full-FE dual canonical packets."""

from __future__ import annotations

import hashlib
import inspect

import numpy as np
import pytest
from dolfinx import fem
from mpi4py import MPI

from benchmarks.canonical_vector_artifacts import (
    SHARD_SCHEMA,
    _key_from_jsonable,
    canonical_key_json_bytes,
)
from src.constraints.floquet_3d import build_double_floquet_mpc
from src.solvers.hcurl_canonical_vector import (
    canonical_key,
    compare_canonical_packets,
)
from src.solvers.hcurl_canonical_vector_dolfinx import (
    extract_canonical_full_fe_dual_packets,
    extract_canonical_full_fe_packets,
    reconstruct_canonical_full_fe_dual_vector,
)
import src.solvers.hcurl_canonical_vector_dolfinx as canonical_dolfinx
from src.test.test_46_task033_high_order_floquet_topology import (
    _fixed_target_fixture,
)


_EXPECTED_PACKET_IDENTITY = {
    2: (768, "b869e6b9e86b9dd403475405235279d67e8c7d4e6da445209d69aeda5bf6b863"),
    3: (2538, "b43707db8dc8e74d3c175ef7f69fdb7b845ee4f7a3d7deecf8d05833b0fc468f"),
}


def _packet_identity(packets) -> tuple[int, str]:
    ordered = sorted(packets, key=lambda item: repr(item[0]))
    payload = b"".join(
        canonical_key_json_bytes(key)
        + np.asarray(
            (complex(value).real, complex(value).imag), dtype="<f8"
        ).tobytes()
        for key, value in ordered
    )
    return len(ordered), hashlib.sha256(payload).hexdigest()


def _set_primal_vector(space, mpc, salt: float):
    field = fem.Function(space)

    def analytic_values(x):
        return np.vstack(
            (
                0.75
                + 0.17 * np.sin(0.013 * x[0] + salt)
                + 1j * (0.5 + 0.11 * np.cos(0.019 * x[1] - salt)),
                0.35
                + 0.13 * np.cos(0.017 * x[1] - salt)
                + 1j * (0.4 + 0.09 * np.sin(0.011 * x[2] + salt)),
                0.2
                + 0.19 * np.sin(0.015 * x[2] + salt)
                + 1j * (0.3 + 0.07 * np.cos(0.021 * x[0] - salt)),
            )
        )

    field.interpolate(analytic_values)
    field.x.scatter_forward()
    index_map = space.dofmap.index_map
    owned = int(index_map.size_local)
    values = field.x.array[:owned]
    is_slave = np.asarray(mpc.is_slave, dtype=bool)
    owned_slave = np.asarray(
        [
            int(local) < is_slave.size and bool(is_slave[int(local)])
            for local in range(owned)
        ],
        dtype=bool,
    )
    values[owned_slave] = 0.0
    field.x.scatter_forward()
    vector = field.x.petsc_vec.duplicate()
    field.x.petsc_vec.copy(vector)
    return vector


def _analytic_dual_packet_value(key, salt: float) -> complex:
    points = np.asarray(key[2], dtype=np.float64) * 1.0e-9
    center = np.mean(points, axis=0)
    span = np.ptp(points, axis=0)
    basis = float(key[3])
    return complex(
        0.6
        + 0.13 * np.sin(0.7 * center[0] + 0.3 * center[1] + salt + basis)
        + 0.05 * span[2],
        0.4
        + 0.11 * np.cos(0.5 * center[1] - 0.2 * center[2] - salt + basis)
        + 0.03 * span[0],
    )


def _fixed_dual_packets(space, mpc, salt: float):
    zero_field = fem.Function(space)
    zero = zero_field.x.petsc_vec.duplicate()
    zero_field.x.petsc_vec.copy(zero)
    try:
        zero_packets, _zero_audit = extract_canonical_full_fe_dual_packets(
            space, mpc, zero
        )
    finally:
        zero.destroy()
    return tuple(
        (key, _analytic_dual_packet_value(key, salt)) for key, _value in zero_packets
    )


def _relative_owned(left, right, comm: MPI.Comm) -> float:
    difference = np.asarray(
        left.getArray(readonly=True) - right.getArray(readonly=True),
        dtype=np.complex128,
    )
    reference = np.asarray(right.getArray(readonly=True), dtype=np.complex128)
    numerator = comm.allreduce(float(np.vdot(difference, difference).real), op=MPI.SUM)
    denominator = comm.allreduce(float(np.vdot(reference, reference).real), op=MPI.SUM)
    return float(np.sqrt(numerator) / max(np.sqrt(denominator), np.finfo(float).tiny))


def _assert_dual_roundtrip(space, mpc, source):
    comm = space.mesh.comm
    packets, audit = extract_canonical_full_fe_dual_packets(space, mpc, source)
    repeated, repeated_audit = extract_canonical_full_fe_dual_packets(
        space, mpc, source
    )
    assert packets == repeated
    assert audit["role"] == "full_fe_dual"
    assert audit["local_packet_count"] > 0
    assert audit["local_duplicate_count"] == 0
    assert audit["summed_local_duplicate_count"] == 0
    assert audit["slave_exclusion"] is True
    assert audit["numeric_allgather"] is False
    assert repeated_audit["local_duplicate_count"] == 0
    assert all(np.isfinite(complex(value)) for _key, value in packets)

    restored = reconstruct_canonical_full_fe_dual_vector(space, mpc, packets)
    restored_packets, restored_audit = extract_canonical_full_fe_dual_packets(
        space, mpc, restored
    )
    comparison = compare_canonical_packets(
        packets, restored_packets, relative_tolerance=1.0e-12
    )
    assert comparison["pass"], comparison
    assert _relative_owned(restored, source, comm) <= 1.0e-12
    is_slave = np.asarray(mpc.is_slave, dtype=bool)
    owned = int(space.dofmap.index_map.size_local)
    restored_values = np.asarray(restored.getArray(readonly=True))
    if is_slave.size:
        assert np.max(np.abs(restored_values[: min(owned, is_slave.size)][is_slave[:owned]])) == 0.0
    assert restored_audit["numeric_allgather"] is False
    return packets, restored


def _assert_primal_dual_pairing(space, mpc, primal, dual, floquet_data):
    primal_packets, _primal_audit = extract_canonical_full_fe_packets(
        space, primal, floquet_data
    )
    dual_packets, _dual_audit = extract_canonical_full_fe_dual_packets(
        space, mpc, dual
    )
    primal_by_key = dict(primal_packets)
    dual_values = []
    primal_values = []
    for dual_key, dual_value in dual_packets:
        assert dual_key[0] == "full_fe_dual"
        primal_key = ("full_fe",) + dual_key[1:]
        assert primal_key in primal_by_key
        primal_values.append(primal_by_key[primal_key])
        dual_values.append(dual_value)
    canonical_pairing = np.vdot(
        np.asarray(primal_values, dtype=np.complex128),
        np.asarray(dual_values, dtype=np.complex128),
    )
    local_pairing = np.vdot(
        np.asarray(primal.getArray(readonly=True), dtype=np.complex128),
        np.asarray(dual.getArray(readonly=True), dtype=np.complex128),
    )
    observed = complex(space.mesh.comm.allreduce(local_pairing, op=MPI.SUM))
    expected = complex(space.mesh.comm.allreduce(canonical_pairing, op=MPI.SUM))
    return abs(observed - expected) / max(abs(observed), 1.0)


def test_full_fe_dual_legacy_role_and_key_contract() -> None:
    legacy_shard = {
        "schema_version": SHARD_SCHEMA,
        "key": {
            "tuple": [
                "full_fe_dual",
                1,
                {
                    "tuple": [
                        {"tuple": [0, 0, -714285714]},
                        {"tuple": [589285714, 0, -714285714]},
                    ]
                },
                0,
                {
                    "tuple": [
                        "canonical_edge",
                        "lexicographic_xyz",
                        "basix_coefficient_v1",
                    ]
                },
                None,
                {"tuple": [1.0, 0.0]},
            ]
        },
        "key_sha256": "ac80cc69d4ec4b5d660769182d2a882324e639466173828c8162cf7e9fd1c44f",
        "value": [0.0, 0.0],
    }
    decoded = _key_from_jsonable(legacy_shard["key"])
    current = canonical_key(
        role="full_fe_dual",
        entity_dimension=1,
        physical_entity=((0, 0, -714285714), (589285714, 0, -714285714)),
        entity_local_basis_index=0,
        orientation_state=(
            "canonical_edge",
            "lexicographic_xyz",
            "basix_coefficient_v1",
        ),
    )
    encoded = canonical_key_json_bytes(current)
    assert decoded == current
    assert hashlib.sha256(encoded).hexdigest() == legacy_shard["key_sha256"]
    assert "allgather" not in inspect.getsource(
        canonical_dolfinx.iter_canonical_full_fe_dual_packets
    )
    assert "allgather" not in inspect.getsource(
        canonical_dolfinx.reconstruct_canonical_full_fe_dual_vector
    )


@pytest.mark.skipif(MPI.COMM_WORLD.size != 1, reason="serial dual canonical lane")
@pytest.mark.parametrize("degree", [2, 3])
def test_serial_full_fe_dual_roundtrip_and_primal_pairing(degree: int) -> None:
    cfg, mesh_data, raw_space = _fixed_target_fixture(degree, h_nm=50.0)
    floquet_data = build_double_floquet_mpc(raw_space, mesh_data, cfg)
    space = floquet_data.mpc.function_space
    dual_packets = _fixed_dual_packets(space, floquet_data.mpc, 0.5)
    dual = reconstruct_canonical_full_fe_dual_vector(
        space, floquet_data.mpc, dual_packets
    )
    primal = _set_primal_vector(space, floquet_data.mpc, 1.5)
    restored = None
    try:
        assert _packet_identity(dual_packets) == _EXPECTED_PACKET_IDENTITY[degree]
        packets, restored = _assert_dual_roundtrip(space, floquet_data.mpc, dual)
        assert packets
        source_comparison = compare_canonical_packets(
            dual_packets, packets, relative_tolerance=1.0e-12
        )
        assert source_comparison["pass"], source_comparison
        assert _assert_primal_dual_pairing(
            space, floquet_data.mpc, primal, dual, floquet_data
        ) <= 1.0e-12
        topology = space.mesh.topology
        topology.create_entity_permutations()
        cell_info = np.asarray(topology.get_cell_permutation_info(), dtype=np.uint32)
        nonzero = next((int(value) for value in cell_info if int(value) != 0), None)
        if nonzero is not None:
            values = np.random.default_rng(274 + degree).standard_normal(
                space.element.space_dimension
            ) + 1j * np.random.default_rng(275 + degree).standard_normal(
                space.element.space_dimension
            )
            stored = values.copy()
            space.element.T_apply(stored, np.asarray([nonzero], dtype=np.uint32), 1)
            space.element.Tt_apply(stored, np.asarray([nonzero], dtype=np.uint32), 1)
            assert np.linalg.norm(stored - values) / np.linalg.norm(values) <= 1.0e-12
    finally:
        if restored is not None:
            restored.destroy()
        primal.destroy()
        dual.destroy()


@pytest.mark.skipif(MPI.COMM_WORLD.size != 2, reason="MPI2 dual canonical lane")
@pytest.mark.parametrize("degree", [2, 3])
def test_mpi2_full_fe_dual_owner_local_identity(degree: int) -> None:
    comm = MPI.COMM_WORLD
    cfg, mesh_data, raw_space = _fixed_target_fixture(degree, h_nm=50.0)
    floquet_data = build_double_floquet_mpc(raw_space, mesh_data, cfg)
    space = floquet_data.mpc.function_space
    restored = None
    try:
        source_packets = _fixed_dual_packets(space, floquet_data.mpc, 0.5)
        restored = reconstruct_canonical_full_fe_dual_vector(
            space, floquet_data.mpc, source_packets
        )
        _local_packets, audit = extract_canonical_full_fe_dual_packets(
            space, floquet_data.mpc, restored
        )
        assert audit["numeric_allgather"] is False
        assert audit["global_packet_count"] == _EXPECTED_PACKET_IDENTITY[degree][0]
        roundtrip_packets, _roundtrip_audit = extract_canonical_full_fe_dual_packets(
            space, floquet_data.mpc, restored
        )
        local_comparison = compare_canonical_packets(
            source_packets, roundtrip_packets, relative_tolerance=1.0e-12
        )
        assert local_comparison["pass"], local_comparison
        gathered = comm.gather(source_packets, root=0)
        gathered_roundtrip = comm.gather(roundtrip_packets, root=0)
        if comm.rank == 0:
            merged = tuple(packet for part in gathered for packet in part)
            merged_roundtrip = tuple(
                packet for part in gathered_roundtrip for packet in part
            )
            identity = _packet_identity(merged)
            roundtrip_identity = _packet_identity(merged_roundtrip)
            roundtrip_comparison = compare_canonical_packets(
                merged, merged_roundtrip, relative_tolerance=1.0e-12
            )
            result = (identity, roundtrip_identity, roundtrip_comparison)
        else:
            result = None
        identity, roundtrip_identity, roundtrip_comparison = comm.bcast(
            result, root=0
        )
        assert identity == _EXPECTED_PACKET_IDENTITY[degree]
        assert roundtrip_identity[0] == _EXPECTED_PACKET_IDENTITY[degree][0]
        assert roundtrip_comparison["pass"], roundtrip_comparison
    finally:
        if restored is not None:
            restored.destroy()
        comm.barrier()
