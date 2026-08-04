import json
import shutil
import tempfile
from pathlib import Path

import pytest
from dolfinx import fem
from mpi4py import MPI
from petsc4py import PETSc

from benchmarks.canonical_vector_artifacts import (
    canonical_shard_manifest,
    compare_canonical_manifests,
    compare_canonical_shard_sets,
    read_canonical_manifest,
    read_canonical_packet_shard,
    read_canonical_packet_shards,
    write_canonical_manifest,
    write_canonical_packet_shard,
)
from src.solvers.hcurl_canonical_vector import (
    canonical_key,
    canonical_packet,
    compare_canonical_packets,
)
from src.solvers.hcurl_canonical_vector_dolfinx import (
    extract_canonical_active_trace_packets,
    extract_canonical_full_fe_packets,
)
from src.test.test_226_task037_canonical_vector_dolfinx import (
    _active_from_field,
    _physical_field,
    _static_fixture,
)


def _packets():
    edge = canonical_key(
        role="active_trace",
        entity_dimension=1,
        physical_entity=((0, 0, 0), (1, 0, 0)),
        entity_local_basis_index=2,
        orientation_state=("edge", "canonical"),
        floquet_master=None,
    )
    face = canonical_key(
        role="full_fe",
        entity_dimension=2,
        physical_entity=((0, 0, 0), (0, 1, 0), (1, 0, 0), (1, 1, 0)),
        entity_local_basis_index=3,
        orientation_state=("face", "canonical"),
        floquet_master=((0, 0, 0), (0, 1, 0), (1, 0, 0), (1, 1, 0)),
        floquet_coefficient=0.5 + 0.25j,
    )
    return (
        canonical_packet(edge, 1.25 - 0.5j),
        canonical_packet(face, -0.75 + 0.125j),
    )


def test_key_roundtrip_is_reversible_and_queryable(tmp_path: Path):
    packets = _packets()
    metadata = write_canonical_packet_shard(tmp_path / "rank0.jsonl", packets)
    restored = read_canonical_packet_shard(
        tmp_path / "rank0.jsonl", metadata["file_sha256"]
    )
    assert restored == packets
    key = restored[1][0]
    assert key[0] == "full_fe"
    assert key[1] == 2
    assert key[2] == packets[1][0][2]
    assert key[3] == 3
    assert key[4] == ("face", "canonical")
    assert key[5] == packets[1][0][5]


def test_deterministic_manifest_and_controlled_comparison_failures(tmp_path: Path):
    packets = _packets()
    left_path = tmp_path / "left.jsonl"
    right_path = tmp_path / "right.jsonl"
    left = write_canonical_packet_shard(left_path, packets)
    repeat = write_canonical_packet_shard(tmp_path / "repeat.jsonl", packets)
    assert repeat["file_sha256"] == left["file_sha256"]
    right = write_canonical_packet_shard(
        right_path, (packets[0], (packets[1][0], packets[1][1] + 0.01j))
    )
    assert left["file_sha256"] != right["file_sha256"]
    failed = compare_canonical_shard_sets(
        (left_path,),
        (right_path,),
        left_sha256=(left["file_sha256"],),
        right_sha256=(right["file_sha256"],),
    )
    assert not failed["pass"]
    assert failed["common_key_count"] == 2
    duplicate = write_canonical_packet_shard(
        tmp_path / "duplicate.jsonl", packets + packets[:1]
    )
    manifest = canonical_shard_manifest(
        role="active_trace",
        mpi_size=2,
        shard_metadata=[
            {**left, "rank": 0, "local_duplicate_count": 0},
            {**duplicate, "rank": 1, "local_duplicate_count": 1},
        ],
        extractor_audit={"trace_mass_norm": "not_qualified"},
    )
    manifest_sha = write_canonical_manifest(tmp_path / "manifest.json", manifest)
    assert len(manifest_sha) == 64
    restored_manifest = read_canonical_manifest(
        tmp_path / "manifest.json", manifest_sha
    )
    assert restored_manifest == manifest
    assert manifest["global_summed_packet_count"] == 5
    assert manifest["summed_local_duplicate_count"] == 1
    left_manifest = canonical_shard_manifest(
        role="active_trace",
        mpi_size=1,
        shard_metadata=[{**left, "rank": 0, "local_duplicate_count": 0}],
        extractor_audit={},
    )
    right_manifest = canonical_shard_manifest(
        role="active_trace",
        mpi_size=1,
        shard_metadata=[{**right, "rank": 0, "local_duplicate_count": 0}],
        extractor_audit={},
    )
    left_manifest_path = tmp_path / "left_manifest.json"
    right_manifest_path = tmp_path / "right_manifest.json"
    left_manifest_sha = write_canonical_manifest(left_manifest_path, left_manifest)
    right_manifest_sha = write_canonical_manifest(right_manifest_path, right_manifest)
    manifest_failed = compare_canonical_manifests(
        left_manifest_path,
        right_manifest_path,
        left_sha256=left_manifest_sha,
        right_sha256=right_manifest_sha,
    )
    assert not manifest_failed["pass"]
    assert manifest_failed["relative_coefficient_l2"] > 0.0
    with pytest.raises(ValueError):
        read_canonical_packet_shard(left_path, "0" * 64)
    with pytest.raises(ValueError):
        read_canonical_manifest(left_manifest_path, "0" * 64)
    tampered_manifest = json.loads(left_manifest_path.read_text())
    tampered_manifest["per_rank_shards"][0]["file_sha256"] = "0" * 64
    tampered_path = tmp_path / "tampered_manifest.json"
    tampered_path.write_text(json.dumps(tampered_manifest))
    with pytest.raises(ValueError):
        read_canonical_manifest(tampered_path)
    different_key = canonical_key(
        role="active_trace",
        entity_dimension=1,
        physical_entity=((9, 0, 0), (10, 0, 0)),
        entity_local_basis_index=2,
        orientation_state=("edge", "canonical"),
    )
    different_path = tmp_path / "different.jsonl"
    different = write_canonical_packet_shard(
        different_path, (packets[0], canonical_packet(different_key, 2.0))
    )
    different_manifest = canonical_shard_manifest(
        role="active_trace",
        mpi_size=1,
        shard_metadata=[{**different, "rank": 0, "local_duplicate_count": 0}],
        extractor_audit={},
    )
    different_manifest_path = tmp_path / "different_manifest.json"
    different_manifest_sha = write_canonical_manifest(
        different_manifest_path, different_manifest
    )
    key_failed = compare_canonical_manifests(
        left_manifest_path,
        different_manifest_path,
        left_sha256=left_manifest_sha,
        right_sha256=different_manifest_sha,
    )
    assert not key_failed["pass"]
    assert key_failed["missing_key_count"]
    assert key_failed["extra_key_count"]
    duplicate_manifest_path = tmp_path / "duplicate_manifest.json"
    duplicate_manifest_sha = write_canonical_manifest(duplicate_manifest_path, manifest)
    duplicate_failed = compare_canonical_manifests(
        duplicate_manifest_path,
        left_manifest_path,
        left_sha256=duplicate_manifest_sha,
        right_sha256=left_manifest_sha,
    )
    assert not duplicate_failed["pass"]
    assert duplicate_failed["duplicate_left_count"]


def test_serial_hexa_extraction_artifact_roundtrip(tmp_path: Path):
    _mesh, function_space, condensed = _static_fixture(MPI.COMM_SELF)
    field = fem.Function(function_space)
    field.interpolate(_physical_field)
    field.x.scatter_forward()
    active = _active_from_field(function_space, condensed, field)
    extracted = (
        extract_canonical_active_trace_packets(condensed, function_space, None, active),
        extract_canonical_full_fe_packets(function_space, field.x.petsc_vec, None),
    )
    results = {}
    for role, (packets, audit) in zip(("active_trace", "full_fe"), extracted):
        shard = write_canonical_packet_shard(tmp_path / f"{role}.jsonl", packets)
        manifest = canonical_shard_manifest(
            role=role,
            mpi_size=1,
            shard_metadata=[
                {
                    **shard,
                    "rank": 0,
                    "local_duplicate_count": audit["local_duplicate_count"],
                }
            ],
            extractor_audit={"by_rank": [audit]},
        )
        manifest_path = tmp_path / f"{role}.manifest.json"
        manifest_sha = write_canonical_manifest(manifest_path, manifest)
        restored_packets = read_canonical_packet_shard(
            tmp_path / f"{role}.jsonl", shard["file_sha256"]
        )
        assert restored_packets == packets
        results[role] = compare_canonical_manifests(
            manifest_path,
            manifest_path,
            left_sha256=manifest_sha,
            right_sha256=manifest_sha,
        )
    assert results["active_trace"]["pass"]
    assert results["full_fe"]["pass"]
    active.destroy()
    condensed.destroy()


@pytest.mark.skipif(MPI.COMM_WORLD.size != 2, reason="MPI2 artifact roundtrip")
def test_mpi2_owner_local_shards_roundtrip():
    comm = MPI.COMM_WORLD
    _mesh, function_space, condensed = _static_fixture(comm)
    field = fem.Function(function_space)
    field.interpolate(_physical_field)
    field.x.scatter_forward()
    active = _active_from_field(function_space, condensed, field)
    extracted = (
        extract_canonical_active_trace_packets(condensed, function_space, None, active),
        extract_canonical_full_fe_packets(function_space, field.x.petsc_vec, None),
    )
    reference = None
    if comm.rank == 0:
        _ref_mesh, ref_space, ref_condensed = _static_fixture(MPI.COMM_SELF)
        ref_field = fem.Function(ref_space)
        ref_field.interpolate(_physical_field)
        ref_field.x.scatter_forward()
        ref_active = _active_from_field(ref_space, ref_condensed, ref_field)
        reference = (
            extract_canonical_active_trace_packets(
                ref_condensed, ref_space, None, ref_active
            )[0],
            extract_canonical_full_fe_packets(ref_space, ref_field.x.petsc_vec, None)[
                0
            ],
        )
        ref_active.destroy()
        ref_condensed.destroy()
    root_path = tempfile.mkdtemp(prefix="task037-c1-mpi2-") if comm.rank == 0 else None
    root_path = Path(comm.bcast(root_path, root=0))
    for role, (packets, audit) in zip(("active_trace", "full_fe"), extracted):
        shard = write_canonical_packet_shard(
            root_path / f"{role}_rank{comm.rank}.jsonl", packets
        )
        shard.update(
            rank=comm.rank,
            local_duplicate_count=audit["local_duplicate_count"],
            extractor_audit=audit,
        )
        gathered = comm.gather(shard, root=0)
        if comm.rank == 0:
            manifest = canonical_shard_manifest(
                role=role,
                mpi_size=comm.size,
                shard_metadata=gathered,
                extractor_audit={
                    "by_rank": [item["extractor_audit"] for item in gathered]
                },
            )
            manifest_path = root_path / f"{role}.manifest.json"
            manifest_sha = write_canonical_manifest(manifest_path, manifest)
            restored_manifest = read_canonical_manifest(manifest_path, manifest_sha)
            restored_packets = read_canonical_packet_shards(
                tuple(
                    root_path / item["filename"]
                    for item in restored_manifest["per_rank_shards"]
                ),
                tuple(
                    item["file_sha256"] for item in restored_manifest["per_rank_shards"]
                ),
            )
            result = compare_canonical_packets(
                restored_packets,
                reference[0 if role == "active_trace" else 1],
            )
        else:
            result = None
        result = comm.bcast(result, root=0)
        assert result["pass"]
    comm.barrier()
    active.destroy()
    condensed.destroy()
    comm.barrier()
    if comm.rank == 0:
        shutil.rmtree(root_path)


@pytest.mark.skipif(MPI.COMM_WORLD.size != 2, reason="MPI2 subvector ownership")
def test_mpi2_active_prefix_zero_local_row():
    comm = MPI.COMM_WORLD
    vector = PETSc.Vec().createMPI((PETSc.DECIDE, 1), comm=PETSc.COMM_WORLD)
    start, end = map(int, vector.getOwnershipRange())
    active_rows = 1
    local_n = max(0, min(end, active_rows) - start)
    index_set = PETSc.IS().createStride(
        local_n,
        first=start,
        step=1,
        comm=vector.getComm(),
    )
    subvector = vector.getSubVector(index_set)
    zero_local_ranks = comm.allreduce(int(local_n == 0), op=MPI.SUM)
    assert zero_local_ranks == 1
    vector.restoreSubVector(index_set, subvector)
    index_set.destroy()
    vector.destroy()
