"""Focused Task040 V2-A1 canonical packet contracts."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from mpi4py import MPI

from src.solvers.hybrid_interface_packet import (
    CanonicalBasis,
    CanonicalTraceBlock,
    PacketGroup,
    canonical_key_set_sha256,
    canonical_key_sha256,
    canonical_key_json,
    canonicalize_raw_basis,
    finalize_manifest,
    load_packet_shard,
    load_small_matrix,
    reconstruct_raw_basis,
    remap_group_rows,
    write_group_shard,
)


def _keys(prefix: str, count: int) -> tuple[str, ...]:
    return tuple(
        canonical_key_json(
            {"role": "active_trace", "plane": prefix, "entity": index, "basis": 0}
        )
        for index in range(count)
    )


def test_canonical_complex_block_round_trip_with_permutation_and_transform():
    canonical = tuple(
        {"role": "active_trace", "plane": "lower", "entity": index, "basis": 0}
        for index in range(3)
    )
    raw = (canonical[2], canonical[0], canonical[1])
    transform = np.asarray(
        [
            [1.0 + 0.2j, 0.3 - 0.1j, 0.0],
            [0.1 + 0.4j, 1.2 - 0.3j, 0.2j],
            [0.0, -0.2 + 0.1j, 0.8 + 0.2j],
        ],
        dtype=np.complex128,
    )
    block = CanonicalTraceBlock("lower", canonical, raw, transform)
    raw_u = np.asarray(
        [
            [1.0 + 0.4j, -0.2 + 0.1j],
            [0.3 - 0.7j, 0.9 + 0.2j],
            [1.2 + 0.1j, -0.4 - 0.3j],
        ],
        dtype=np.complex128,
    )
    raw_v = np.asarray(
        [
            [-0.4 + 0.2j, 0.8 - 0.1j],
            [0.7 + 0.3j, -0.1 + 0.6j],
            [0.2 - 0.5j, 0.4 + 0.9j],
        ],
        dtype=np.complex128,
    )
    basis = canonicalize_raw_basis([block], {"lower": raw_u}, {"lower": raw_v})
    assert basis.keys == tuple(canonical_key_json(key) for key in canonical)
    reconstructed_u, reconstructed_v = reconstruct_raw_basis([block], basis)
    assert np.allclose(reconstructed_u["lower"], raw_u, rtol=0.0, atol=1.0e-13)
    assert np.allclose(reconstructed_v["lower"], raw_v, rtol=0.0, atol=1.0e-13)
    assert not np.allclose(basis.U, raw_u)

    target_transform = np.asarray(
        [
            [0.9 - 0.1j, 0.2 + 0.3j, -0.1j],
            [0.0 + 0.2j, 1.1 + 0.1j, 0.25 - 0.2j],
            [0.3 - 0.1j, 0.0 + 0.15j, 0.8 + 0.25j],
        ],
        dtype=np.complex128,
    )
    target = CanonicalTraceBlock(
        "fresh_lower",
        canonical,
        (canonical[1], canonical[2], canonical[0]),
        target_transform,
    )
    target_raw_u, target_raw_v = reconstruct_raw_basis(
        [target], CanonicalBasis(basis.keys, basis.U, basis.V)
    )
    assert np.allclose(
        target_raw_u["fresh_lower"],
        np.linalg.solve(target_transform, basis.U),
        rtol=0.0,
        atol=1.0e-12,
    )
    assert np.allclose(
        target_raw_v["fresh_lower"],
        np.linalg.solve(target_transform, basis.V),
        rtol=0.0,
        atol=1.0e-12,
    )


def _shared_root(tmp_path: Path, comm: MPI.Intracomm) -> Path:
    root = Path(comm.bcast(str(tmp_path / "packet"), root=0))
    if comm.rank == 0:
        root.mkdir(parents=True, exist_ok=True)
    comm.barrier()
    return root


def _ownership_range(comm: MPI.Intracomm) -> tuple[int, int]:
    ranges_by_size = {
        1: ((0, 4),),
        2: ((0, 2), (2, 4)),
        4: ((0, 1), (1, 2), (2, 4), (4, 4)),
    }
    try:
        return ranges_by_size[comm.size][comm.rank]
    except KeyError as exc:
        raise RuntimeError("test304 supports only MPI sizes 1, 2, and 4") from exc


def _local_group_payloads(comm: MPI.Intracomm) -> tuple[PacketGroup, PacketGroup]:
    all_keys = _keys("gamma", 4)
    first, last = _ownership_range(comm)
    local_keys = tuple(all_keys[first:last])
    U = np.empty((len(local_keys), 2), dtype=np.complex128)
    V = np.empty_like(U)
    for index in range(len(local_keys)):
        U[index] = (1.0 + 0.2j * (first + index + 1), 0.1 - 0.1j * index)
        V[index] = (0.4 - 0.1j * index, 1.0 + 0.05j * (first + index + 1))
    return (
        PacketGroup("group0", local_keys, U, V),
        PacketGroup("group1", local_keys, U + 0.2j, V - 0.1j),
    )


def test_packet_rank_shards_finalize_load_and_canonical_remap(tmp_path: Path):
    comm = MPI.COMM_WORLD
    root = _shared_root(tmp_path, comm)
    groups = _local_group_payloads(comm)
    expected = {"group0": _keys("gamma", 4), "group1": _keys("gamma", 4)}
    descriptors = [
        write_group_shard(
            root,
            group,
            comm=comm,
            ownership_range=_ownership_range(comm),
        )
        for group in groups
    ]
    if comm.size == 1:
        with pytest.raises(FileNotFoundError, match="manifest"):
            load_packet_shard(root, groups=("group0",), comm=comm)
    else:
        with pytest.raises(ValueError, match="collective packet load failed"):
            load_packet_shard(root, groups=("group0",), comm=comm)
    manifest_result = finalize_manifest(
        root,
        descriptors,
        provenance={
            "source_sha": "a" * 64,
            "input_sha256": "b" * 64,
            "schema_owner": "task040",
        },
        group_names=("group0", "group1"),
        expected_group_counts={"group0": 4, "group1": 4},
        small_matrices={
            "G": np.asarray(
                [[1.0 + 0.2j, 0.1], [0.3j, 2.0 - 0.1j]], dtype=np.complex128
            ),
            "projected_scalar": np.eye(2, dtype=np.complex128),
        }
        if comm.rank == 0
        else None,
        diagnostics={"probe_count": 0, "basis_global_replicated": False},
        comm=comm,
    )
    assert manifest_result["packet_complete"] is True
    loaded = load_packet_shard(
        root,
        expected_provenance={
            "source_sha": "a" * 64,
            "input_sha256": "b" * 64,
            "schema_owner": "task040",
        },
        comm=comm,
    )
    assert loaded["numeric_allgather"] is False
    assert loaded["basis_global_replicated"] is False
    for group in groups:
        actual = loaded["groups"][group.name]
        assert actual.keys == group.keys
        assert np.allclose(actual.U, group.U)
        assert np.allclose(actual.V, group.V)
    if comm.rank == 0:
        manifest = json.loads((root / "manifest.json").read_text())
        assert manifest["packet_complete"] is True
        assert manifest["group_order"] == ["group0", "group1"]
        assert manifest["small_matrices"]["G"]["dtype"] == "complex128"
        assert "global_keys" not in manifest["groups"]["group0"]
        assert "owner_mapping" not in manifest["groups"]["group0"]
        assert (
            manifest["groups"]["group0"]["global_key_bijection"]
            == "requires_independent_checker"
        )
        assert manifest["groups"]["group0"]["global_count"] == 4
        for record in manifest["groups"]["group0"]["shards"]:
            assert "keys" not in record
            assert "key_order_sha256" in record
            assert "owner_key_set_sha256" in record
            assert record["key_order_sha256"] == canonical_key_sha256(
                _keys("gamma", 4)[
                    record["ownership_range"][0] : record["ownership_range"][1]
                ]
            )
            assert record["owner_key_set_sha256"] == canonical_key_set_sha256(
                _keys("gamma", 4)[
                    record["ownership_range"][0] : record["ownership_range"][1]
                ]
            )
        seen = []
        for record in manifest["groups"]["group0"]["shards"]:
            with np.load(root / record["path"], allow_pickle=False) as arrays:
                seen.extend(str(value) for value in arrays["keys"].tolist())
        assert len(seen) == 4 and len(set(seen)) == 4
        assert set(seen) == set(expected["group0"])
        assert np.allclose(
            load_small_matrix(root, "G"),
            np.asarray([[1.0 + 0.2j, 0.1], [0.3j, 2.0 - 0.1j]], dtype=np.complex128),
        )
    if comm.size >= 4:
        assert comm.allreduce(len(groups[0].keys) == 0, op=MPI.LOR)
    permutation = remap_group_rows(
        loaded["groups"]["group0"], tuple(reversed(loaded["groups"]["group0"].keys))
    )
    assert np.array_equal(permutation, np.arange(len(permutation) - 1, -1, -1))
    assert np.allclose(
        loaded["groups"]["group0"].U[permutation][::-1],
        loaded["groups"]["group0"].U,
    )


def test_packet_missing_manifest_and_tampered_shard_fail_closed(tmp_path: Path):
    comm = MPI.COMM_WORLD
    if comm.size != 1:
        pytest.skip("manifest tamper is a serial filesystem contract")
    root = tmp_path / "missing"
    with pytest.raises(FileNotFoundError, match="manifest"):
        load_packet_shard(root, comm=comm)

    group = PacketGroup(
        "group0",
        _keys("tamper", 2),
        np.eye(2, dtype=np.complex128),
        np.eye(2, dtype=np.complex128),
    )
    descriptor = write_group_shard(root, group, comm=comm, ownership_range=(0, 2))
    finalize_manifest(
        root,
        [descriptor],
        provenance={"source_sha": "c" * 64},
        group_names=("group0",),
        expected_group_counts={"group0": 2},
        comm=comm,
    )
    shard_path = root / descriptor["path"]
    shard_path.write_bytes(shard_path.read_bytes() + b"tamper")
    with pytest.raises(ValueError, match="hash mismatch"):
        load_packet_shard(root, comm=comm)


def test_packet_group_order_identity_fails_closed(tmp_path: Path):
    comm = MPI.COMM_WORLD
    if comm.size != 1:
        pytest.skip("group-order identity fixture is serial")
    root = tmp_path / "group-order"
    group = PacketGroup(
        "group0",
        _keys("group-order", 2),
        np.eye(2, dtype=np.complex128),
        np.eye(2, dtype=np.complex128),
    )
    descriptor = write_group_shard(root, group, comm=comm, ownership_range=(0, 2))
    finalize_manifest(
        root,
        [descriptor],
        provenance={"source_sha": "f" * 64},
        group_names=("group0",),
        expected_group_counts={"group0": 2},
        comm=comm,
    )
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["group_order"] = ["group0", "group0"]
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="group_order is invalid"):
        load_packet_shard(root, comm=comm)


def test_one_rank_write_validation_failure_is_collective(tmp_path: Path):
    comm = MPI.COMM_WORLD
    root = _shared_root(tmp_path / "validation", comm)
    group = _local_group_payloads(comm)[0]
    if comm.rank == 0:
        group = PacketGroup(
            group.name,
            group.keys,
            group.U.real,
            group.V,
        )
    with pytest.raises(ValueError, match="collective|group shard write failed"):
        write_group_shard(
            root,
            group,
            comm=comm,
            ownership_range=_ownership_range(comm),
        )


def test_one_rank_tampered_shard_load_failure_is_collective(tmp_path: Path):
    comm = MPI.COMM_WORLD
    root = _shared_root(tmp_path / "tamper", comm)
    group = _local_group_payloads(comm)[0]
    descriptor = write_group_shard(
        root,
        group,
        comm=comm,
        ownership_range=_ownership_range(comm),
    )
    finalize_manifest(
        root,
        [descriptor],
        provenance={"source_sha": "d" * 64},
        group_names=("group0",),
        expected_group_counts={"group0": 4},
        comm=comm,
    )
    if comm.rank == 0:
        shard_path = root / descriptor["path"]
        shard_path.write_bytes(shard_path.read_bytes() + b"tamper")
    comm.barrier()
    with pytest.raises(ValueError, match="collective packet load failed|hash mismatch"):
        load_packet_shard(root, comm=comm)


def test_canonical_key_rejects_double_encoded_or_nonobject_keys():
    semantic = {"plane": "lower", "entity": 0, "basis": 0}
    encoded = canonical_key_json(semantic)
    assert canonical_key_json(semantic) == encoded
    with pytest.raises(TypeError, match="top-level JSON objects"):
        canonical_key_json(encoded)
    with pytest.raises(ValueError, match="JSON-safe key"):
        remap_group_rows(
            PacketGroup(
                "group",
                (encoded,),
                np.ones((1, 1), dtype=np.complex128),
                np.ones((1, 1), dtype=np.complex128),
            ),
            (json.dumps(encoded),),
        )


def test_owner_mapping_identity_separates_order_and_owner_set(tmp_path: Path):
    comm = MPI.COMM_WORLD
    if comm.size != 1:
        pytest.skip("owner mapping identity fixture is serial")
    keys = _keys("identity", 3)
    reversed_keys = tuple(reversed(keys))
    U = np.asarray([[1.0 + 0.2j], [2.0 - 0.1j], [3.0 + 0.4j]], dtype=np.complex128)
    V = np.asarray([[0.5 - 0.2j], [0.7 + 0.1j], [0.9 - 0.3j]], dtype=np.complex128)
    root_a = tmp_path / "identity_a"
    root_b = tmp_path / "identity_b"
    descriptor_a = write_group_shard(
        root_a,
        PacketGroup("group0", keys, U, V),
        comm=comm,
        ownership_range=(0, 3),
    )
    descriptor_b = write_group_shard(
        root_b,
        PacketGroup("group0", reversed_keys, U[::-1], V[::-1]),
        comm=comm,
        ownership_range=(0, 3),
    )
    finalize_manifest(
        root_a,
        [descriptor_a],
        provenance={"source_sha": "e" * 64},
        group_names=("group0",),
        expected_group_counts={"group0": 3},
        comm=comm,
    )
    finalize_manifest(
        root_b,
        [descriptor_b],
        provenance={"source_sha": "e" * 64},
        group_names=("group0",),
        expected_group_counts={"group0": 3},
        comm=comm,
    )
    manifest_a = json.loads((root_a / "manifest.json").read_text())
    manifest_b = json.loads((root_b / "manifest.json").read_text())
    record_a = manifest_a["groups"]["group0"]["shards"][0]
    record_b = manifest_b["groups"]["group0"]["shards"][0]
    assert record_a["key_order_sha256"] != record_b["key_order_sha256"]
    assert record_a["owner_key_set_sha256"] == record_b["owner_key_set_sha256"]
    assert (
        manifest_a["groups"]["group0"]["row_key_to_owner_mapping_sha256"]
        == manifest_b["groups"]["group0"]["row_key_to_owner_mapping_sha256"]
    )
