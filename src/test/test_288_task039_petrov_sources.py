from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from mpi4py import MPI

from src.coupling.hybrid_internal_modes import build_single_hybrid_interface_mode_owner
from src.solvers.hybrid_petrov_sources import (
    V6_PORT_MODAL_CHECKPOINTS,
    V6_PORT_MODAL_HOLDOUT_SPECS,
    _fill_partition_independent_random,
    build_v6_owner_row_basis_checkpoint,
    v6_port_modal_source_contract,
    v6_port_modal_training_schedule,
    v6_source_identity,
)
from src.solvers.hybrid_streamed_petrov import (
    V7_STREAMED_PETROV_BATCH_SIZE,
    V7_STREAMED_PETROV_CHECKPOINTS,
    V7_STREAMED_PETROV_HASH_LAYOUT,
    StreamedOwnerRowBasisBuilder,
    load_streamed_owner_row_basis_packet,
    run_streamed_owner_row_basis_producer,
    write_streamed_owner_row_basis_packet,
)


def test_v6_single_interface_rejects_degree_mismatch_before_build():
    system = SimpleNamespace(side="bottom", cfg=SimpleNamespace(nedelec_degree=2))
    spaces = SimpleNamespace(transverse_degree=3)
    with pytest.raises(ValueError, match="matching Nedelec"):
        build_single_hybrid_interface_mode_owner(system, spaces, None, None)


def test_v6_training_contract_is_factor_free_and_disjoint_from_holdout():
    contract = v6_port_modal_source_contract()
    training = contract["training"]
    holdout = contract["holdout"]
    assert len(training) == 512
    assert contract["checkpoints"] == list(V6_PORT_MODAL_CHECKPOINTS)
    assert all(item["factor_free"] and not item["holdout"] for item in training)
    assert all(item["holdout"] for item in holdout)
    assert {item["label"] for item in holdout} == {
        item["label"] for item in V6_PORT_MODAL_HOLDOUT_SPECS
    }
    assert contract["training_reads_holdout_files"] is False
    assert {
        (item["label"], item["seed"], item.get("resolved_column")) for item in holdout
    } == {
        (item["label"], item["seed"], item.get("resolved_column"))
        for item in V6_PORT_MODAL_HOLDOUT_SPECS
    }
    assert contract["external_count"] == 296
    assert all("right_family" in item and "left_family" in item for item in training)
    assert {item["right_family"] for item in training} >= {
        "positive_modal_traction",
        "negative_modal_traction",
        "external_c",
        "hcurl_near_null_gradient",
        "physical_rhs",
    }
    assert "fixed_random" not in {item["right_family"] for item in training}
    assert {item["left_family"] for item in training} == {
        "projection_dual",
        "positive_modal_dual",
        "negative_modal_dual",
        "external_dual",
    }
    assert len(contract["sha256"]) == 64


def test_v6_training_schedule_deterministic_and_column_bound():
    first = v6_port_modal_training_schedule(mode_count=480)
    second = v6_port_modal_training_schedule(mode_count=480)
    assert first == second
    assert all(
        0 <= item["right_selector"]["column"] < 480
        for item in first[1:]
        if "column" in item["right_selector"]
    )
    assert first[0]["right_selector"]["absent_if_zero"] is True
    assert first[0]["right_selector"]["fallback"]["selector"] == (
        "cross_section_discrete_gradient_potential"
    )
    assert first[0]["right_selector"]["fallback"]["potential_ordinal"] == 127
    hcurl_ordinals = [
        item["right_selector"]["potential_ordinal"]
        for item in first
        if item["right_family"] == "hcurl_near_null_gradient"
    ]
    assert hcurl_ordinals == list(range(127))
    assert 127 not in hcurl_ordinals
    assert all(
        "seed" not in item["right_selector"]
        for item in first
        if item["right_family"] == "hcurl_near_null_gradient"
    )
    assert all(
        item["right_selector"]["column"] < 296
        for item in first
        if item["right_family"] == "external_c"
    )
    for family, selector_key in (
        ("positive_modal_traction", "right_selector"),
        ("negative_modal_traction", "right_selector"),
        ("external_c", "right_selector"),
        ("positive_modal_dual", "left_selector"),
        ("negative_modal_dual", "left_selector"),
        ("external_dual", "left_selector"),
    ):
        columns = [
            item[selector_key]["column"]
            for item in first
            if item[
                "right_family" if selector_key == "right_selector" else "left_family"
            ]
            == family
        ]
        assert len(columns) == len(set(columns))
    assert all(
        "seed" in item["left_selector"]
        for item in first
        if item["left_family"] == "projection_dual"
    )


class _TinyOwnerVector:
    def __init__(self, first: int, last: int):
        self.first = first
        self.last = last
        self.values = np.zeros(last - first, dtype=np.complex128)

    def getOwnershipRange(self):
        return self.first, self.last

    def getArray(self):
        return self.values

    def assemble(self):
        return None


def test_v6_counter_random_is_partition_independent_and_high_rank():
    row_count = 96
    owned = np.array_split(np.arange(row_count), MPI.COMM_WORLD.size)[
        MPI.COMM_WORLD.rank
    ]
    local = _TinyOwnerVector(int(owned[0]), int(owned[-1] + 1))
    _fill_partition_independent_random(local, 6039071)
    chunks = MPI.COMM_WORLD.allgather(local.values)
    serial = _TinyOwnerVector(0, row_count)
    _fill_partition_independent_random(serial, 6039071)
    np.testing.assert_allclose(np.concatenate(chunks), serial.values)

    seeds = [6039071 + 101 * index for index in range(32)]
    matrix = np.empty((row_count, len(seeds)), dtype=np.complex128)
    for column, seed in enumerate(seeds):
        vector = _TinyOwnerVector(0, row_count)
        _fill_partition_independent_random(vector, seed)
        matrix[:, column] = vector.values
    assert np.linalg.matrix_rank(matrix, tol=1.0e-10) == len(seeds)


def test_v6_owner_row_qr_uses_complex_adjoint_and_fixed_prefix():
    if MPI.COMM_WORLD.size not in (1, 2, 4):
        pytest.skip("focused owner-row QR fixture supports MPI1/2/4")
    row_count = 96
    first, last = (
        np.array_split(np.arange(row_count), MPI.COMM_WORLD.size)[MPI.COMM_WORLD.rank][
            [0, -1]
        ]
        if MPI.COMM_WORLD.size > 1
        else (0, row_count - 1)
    )
    rng = np.random.default_rng(288)
    full_z = rng.standard_normal((row_count, 512)) + 1j * rng.standard_normal(
        (row_count, 512)
    )
    full_y = rng.standard_normal((row_count, 512)) + 1j * rng.standard_normal(
        (row_count, 512)
    )
    z = np.asarray(full_z[first : last + 1], dtype=np.complex128)
    y = np.asarray(full_y[first : last + 1], dtype=np.complex128)
    qz, qy, diagnostics = build_v6_owner_row_basis_checkpoint(z, y, 64)
    assert qz.shape == (last - first + 1, 64)
    assert qy.shape == (last - first + 1, 64)
    assert diagnostics["global_basis_materialized"] is False
    assert diagnostics["owner_row_local"] is True
    assert diagnostics["rank"] == 64
    assert diagnostics["z_orthogonality_error"] <= 1.0e-10
    assert diagnostics["y_orthogonality_error"] <= 1.0e-10
    assert diagnostics["z_reconstruction_relative_error"] <= 1.0e-12
    assert diagnostics["y_reconstruction_relative_error"] <= 1.0e-12
    assert np.isfinite(diagnostics["cross_yh_z_condition"])


def test_v7_streamed_owner_row_prefixes_and_hash_bound_packet(tmp_path):
    if MPI.COMM_WORLD.size not in (1, 2, 4):
        pytest.skip("focused streamed owner-row fixture supports MPI1/2/4")
    comm = MPI.COMM_WORLD
    global_rows = 640
    partitions = np.array_split(np.arange(global_rows), comm.size)
    owned = partitions[comm.rank]
    first, last = int(owned[0]), int(owned[-1] + 1)
    rng = np.random.default_rng(392)
    full_right = rng.standard_normal((global_rows, 512)) + 1j * rng.standard_normal(
        (global_rows, 512)
    )
    full_left = rng.standard_normal((global_rows, 512)) + 1j * rng.standard_normal(
        (global_rows, 512)
    )
    builder = StreamedOwnerRowBasisBuilder(
        last - first,
        global_rows=global_rows,
        ownership_range=(first, last),
        comm=comm,
    )
    for index in range(64):
        builder.append(
            full_right[first:last, index],
            full_left[first:last, index],
            source_identity={"index": index, "family": "tiny"},
        )
    z64, y64, diagnostics64 = builder.checkpoint(64)
    assert diagnostics64["source_columns_retained"] is False
    assert diagnostics64["batch_size"] == V7_STREAMED_PETROV_BATCH_SIZE
    assert diagnostics64["rank"] == 64
    assert diagnostics64["basis_finite"] is True
    assert np.isfinite(diagnostics64["cross_yh_z_condition"])
    for index in range(64, 128):
        builder.append(
            full_right[first:last, index],
            full_left[first:last, index],
            source_identity={"index": index, "family": "tiny"},
        )
    z128, y128, diagnostics128 = builder.checkpoint(128)
    assert set(V7_STREAMED_PETROV_CHECKPOINTS) == {64, 128, 256, 512}
    np.testing.assert_allclose(z128[:, :64], z64, rtol=0.0, atol=1.0e-12)
    np.testing.assert_allclose(y128[:, :64], y64, rtol=0.0, atol=1.0e-12)
    assert diagnostics128["source_columns_retained"] is False
    assert diagnostics128["right_source_bytes"] == 128 * (last - first) * 16
    assert diagnostics64["z_orthogonality_error"] <= 1.0e-10
    assert diagnostics64["y_orthogonality_error"] <= 1.0e-10
    assert diagnostics128["z_orthogonality_error"] <= 1.0e-10
    assert diagnostics128["y_orthogonality_error"] <= 1.0e-10
    for index in range(128, 512):
        builder.append(
            full_right[first:last, index],
            full_left[first:last, index],
            source_identity={"index": index, "family": "tiny"},
        )
        if index + 1 in (256, 512):
            builder.checkpoint(index + 1)
    z512, y512, prefix_records = builder.final_basis()
    assert len(prefix_records) == 4
    assert [item["checkpoint"] for item in prefix_records] == [64, 128, 256, 512]
    assert prefix_records[2]["z_orthogonality_error"] <= 1.0e-10
    assert prefix_records[2]["y_orthogonality_error"] <= 1.0e-10
    assert prefix_records[3]["z_orthogonality_error"] <= 1.0e-10
    assert prefix_records[3]["y_orthogonality_error"] <= 1.0e-10
    assert builder.capacity_bytes["z"] == (last - first) * 512 * 16

    directory = Path(comm.bcast(str(tmp_path / "streamed_basis"), root=0))
    provenance = {
        "packet_manifest_sha256": "p" * 64,
        "source_mesh_sha256": "m" * 64,
        "training_holdout_disjoint": True,
    }
    packet = write_streamed_owner_row_basis_packet(
        directory,
        z512,
        y512,
        prefix_records=prefix_records,
        global_rows=global_rows,
        ownership_range=(first, last),
        schedule_sha256="s" * 64,
        provenance=provenance,
        comm=comm,
    )
    assert packet["checkpoint"] == 512
    assert packet["hash_layout"] == V7_STREAMED_PETROV_HASH_LAYOUT
    loaded = load_streamed_owner_row_basis_packet(
        directory / "manifest.json",
        expected_manifest_sha256=packet["manifest_sha256"],
        expected_schedule_sha256="s" * 64,
        expected_provenance=provenance,
        ownership_range=(first, last),
        comm=comm,
    )
    assert loaded.diagnostics["mmap_retained"] is True
    assert loaded.diagnostics["hash_layout"] == V7_STREAMED_PETROV_HASH_LAYOUT
    assert isinstance(loaded.z, np.memmap)
    assert isinstance(loaded.y, np.memmap)
    loaded_z, loaded_y, prefix64 = loaded.prefix(64)
    assert prefix64["hash_layout"] == V7_STREAMED_PETROV_HASH_LAYOUT
    np.testing.assert_allclose(loaded_z, z64, rtol=0.0, atol=1.0e-12)
    np.testing.assert_allclose(loaded_y, y64, rtol=0.0, atol=1.0e-12)
    loaded_z, loaded_y, _ = loaded.prefix(128)
    np.testing.assert_allclose(loaded_z, z128, rtol=0.0, atol=1.0e-12)
    np.testing.assert_allclose(loaded_y, y128, rtol=0.0, atol=1.0e-12)
    loaded.prefix(256)
    loaded.prefix(512)
    assert loaded.diagnostics["owned_basis_copy_count"] == 0
    assert loaded.diagnostics["mmap_mapping_count"] == 2
    loaded.destroy()
    assert loaded.z is None and loaded.y is None
    assert loaded.diagnostics == {"mmap_retained": False, "mmap_released": True}
    builder.destroy()
    with pytest.raises(RuntimeError, match="destroyed"):
        builder.checkpoint(128)


def test_v7_streamed_producer_writes_one_nested_packet_and_releases_context(tmp_path):
    if MPI.COMM_WORLD.size not in (1, 2, 4):
        pytest.skip("focused streamed producer fixture supports MPI1/2/4")
    comm = MPI.COMM_WORLD
    global_rows = 640
    owned = np.array_split(np.arange(global_rows), comm.size)[comm.rank]
    first, last = int(owned[0]), int(owned[-1] + 1)

    class _Context:
        def __init__(self):
            self.release_count = 0
            self._released = False

        @property
        def diagnostics(self):
            return {
                "released": self._released,
                "mmap_mapping_count": 0 if self._released else 4,
            }

        def release(self):
            self.release_count += 1
            self._released = True

    context = _Context()
    schedule = [{"index": index, "holdout": False} for index in range(512)]

    def source_builder(item, _context):
        index = int(item["index"])
        right = np.zeros(last - first, dtype=np.complex128)
        left = np.zeros(last - first, dtype=np.complex128)
        if first <= index < last:
            right[index - first] = 1.0 + 0.0j
            left[index - first] = 1.0 + 0.0j
        return right, left, {"family": "tiny", "index": index}

    oracle = {
        branch: {
            "relative_error": 0.0,
            "finite": True,
            "tolerance": 1.0e-12,
            "equivalent": True,
        }
        for branch in ("positive", "negative")
    }
    output_directory = Path(comm.bcast(str(tmp_path / "producer_one_packet"), root=0))
    result = run_streamed_owner_row_basis_producer(
        context,
        schedule,
        source_builder,
        output_directory=output_directory,
        global_rows=global_rows,
        ownership_range=(first, last),
        schedule_sha256="t" * 64,
        provenance={
            "training_holdout_disjoint": True,
            "left_dual_oracle": oracle,
            "source_schedule_identity": "v7_tiny_streamed_equivalent",
        },
        comm=comm,
    )
    assert context.release_count == 1
    assert result["packet_context_before_release"]["mmap_mapping_count"] == 4
    assert result["packet_context_after_release"] == {
        "released": True,
        "mmap_mapping_count": 0,
    }
    assert result["checkpoint"] == 512
    assert result["prefix_checkpoints"] == [64, 128, 256, 512]
    assert result["writer_retained_basis_copy"] is False
    assert result["producer_diagnostics"]["checkpoint"] == 512
    assert all(len(shard["prefixes"]) == 4 for shard in result["rank_hashes"])
    assert (output_directory / "manifest.json").is_file()


def test_v7_streamed_producer_rejects_legacy_non_equivalent_left_dual_identity():
    oracle = {
        branch: {
            "relative_error": 900.298368548294,
            "finite": True,
            "tolerance": 1.0e-12,
            "equivalent": False,
        }
        for branch in ("positive", "negative")
    }
    with pytest.raises(ValueError, match="distinct source schedule"):
        run_streamed_owner_row_basis_producer(
            SimpleNamespace(release=lambda: None),
            [{"holdout": False}] * 512,
            lambda _item, _context: (None, None, {}),
            output_directory=Path("/tmp/task039-v7-never-written"),
            global_rows=1,
            ownership_range=(0, 1),
            schedule_sha256="s" * 64,
            provenance={
                "training_holdout_disjoint": True,
                "left_dual_oracle": oracle,
                "source_schedule_identity": "v6_full_owner_p_h_e",
            },
            comm=MPI.COMM_WORLD,
        )


def test_v6_owner_row_qr_prefixes_are_nested():
    if MPI.COMM_WORLD.size not in (1, 2, 4):
        pytest.skip("focused owner-row QR fixture supports MPI1/2/4")
    row_count = 192
    owned = np.array_split(np.arange(row_count), MPI.COMM_WORLD.size)[
        MPI.COMM_WORLD.rank
    ]
    rng = np.random.default_rng(2881)
    full_z = rng.standard_normal((row_count, 512)) + 1j * rng.standard_normal(
        (row_count, 512)
    )
    full_y = rng.standard_normal((row_count, 512)) + 1j * rng.standard_normal(
        (row_count, 512)
    )
    z64, y64, _ = build_v6_owner_row_basis_checkpoint(full_z[owned], full_y[owned], 64)
    z128, y128, diagnostics = build_v6_owner_row_basis_checkpoint(
        full_z[owned], full_y[owned], 128
    )
    overlap_z = np.empty((64, 128), dtype=np.complex128)
    overlap_y = np.empty((64, 128), dtype=np.complex128)
    MPI.COMM_WORLD.Allreduce(z64.conj().T @ z128, overlap_z, op=MPI.SUM)
    MPI.COMM_WORLD.Allreduce(y64.conj().T @ y128, overlap_y, op=MPI.SUM)
    assert np.linalg.norm(overlap_z @ overlap_z.conj().T - np.eye(64)) <= 1.0e-10
    assert np.linalg.norm(overlap_y @ overlap_y.conj().T - np.eye(64)) <= 1.0e-10
    assert np.isfinite(diagnostics["cross_yh_z_condition"])


def test_v6_owner_row_qr_rank_failure_is_collective():
    row_count = 96
    owned = np.array_split(np.arange(row_count), MPI.COMM_WORLD.size)[
        MPI.COMM_WORLD.rank
    ]
    column = np.ones((owned.size, 64), dtype=np.complex128)
    with pytest.raises(ValueError, match="rank deficient"):
        build_v6_owner_row_basis_checkpoint(column, column, 64)


def test_v6_source_identity_reduces_only_hash_metadata():
    global_rows = 2 * MPI.COMM_WORLD.size
    owned = np.array_split(np.arange(global_rows), MPI.COMM_WORLD.size)[
        MPI.COMM_WORLD.rank
    ]
    values = np.asarray(owned + 1.0j * (owned + 1.0), dtype=np.complex128)
    identity = v6_source_identity(
        values,
        label="external_c",
        seed=6039071,
        global_rows=global_rows,
        ownership_range=(int(owned[0]), int(owned[-1] + 1)),
    )
    assert identity["dtype"] == "complex128"
    assert identity["global_rows"] == global_rows
    assert identity["ownership_range"] == [int(owned[0]), int(owned[-1] + 1)]
    assert identity["owner_hashes"][0]["sha256"]
