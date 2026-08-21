"""Focused V10-6 side-response packet and consumer lifecycle contracts."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from mpi4py import MPI

import benchmarks.task039_v3_7_orchestration as orchestration
import benchmarks.task039_v3_7_watchdog as watchdog
from src.runners import task038_launcher as launcher
from src.solvers.hybrid_side_response_packet import (
    ExactSideResponsePacket,
    V10_SIDE_RESPONSE_PACKET_COLUMNS,
    V10_SIDE_RESPONSE_PACKET_FULL_COLUMNS,
    OwnerRowResponsePacketWriter,
    compress_owner_row_response_packet,
    load_full_side_response_packet,
    load_exact_side_response_packet,
    projected_response_payload_bytes,
    projected_response_wall_seconds,
    write_exact_side_response_packet,
    V10_SIDE_RESPONSE_PACKET_COMPRESSION_METHOD,
    V10_SIDE_RESPONSE_PACKET_COMPRESSION_SCHEMA,
    V10_SIDE_RESPONSE_PACKET_FULL_METHOD,
    V10_SIDE_RESPONSE_PACKET_FULL_SCHEMA,
)


def test_v10_full_and_compression_schema_method_contract_is_canonical() -> None:
    assert orchestration.V10_H4_SIDE_RESPONSE_PACKET_FULL_PRODUCER_SCHEMA == (
        V10_SIDE_RESPONSE_PACKET_FULL_SCHEMA
    )
    assert orchestration.V10_H4_SIDE_RESPONSE_PACKET_FULL_PRODUCER_METHOD == (
        V10_SIDE_RESPONSE_PACKET_FULL_METHOD
    )
    assert orchestration.V10_H4_SIDE_RESPONSE_PACKET_COMPRESSION_SCHEMA == (
        V10_SIDE_RESPONSE_PACKET_COMPRESSION_SCHEMA
    )
    assert orchestration.V10_H4_SIDE_RESPONSE_PACKET_COMPRESSION_METHOD == (
        V10_SIDE_RESPONSE_PACKET_COMPRESSION_METHOD
    )
    assert launcher.V10_H4_SIDE_RESPONSE_PACKET_FULL_PRODUCER_SCHEMA == (
        V10_SIDE_RESPONSE_PACKET_FULL_SCHEMA
    )
    assert launcher.V10_H4_SIDE_RESPONSE_PACKET_COMPRESSION_SCHEMA == (
        V10_SIDE_RESPONSE_PACKET_COMPRESSION_SCHEMA
    )
    assert launcher.V10_H4_SIDE_RESPONSE_PACKET_FULL_PRODUCER_METHOD == (
        V10_SIDE_RESPONSE_PACKET_FULL_METHOD
    )
    assert launcher.V10_H4_SIDE_RESPONSE_PACKET_COMPRESSION_METHOD == (
        V10_SIDE_RESPONSE_PACKET_COMPRESSION_METHOD
    )
    assert watchdog.V10_H4_SIDE_RESPONSE_PACKET_FULL_PRODUCER_SCHEMA == (
        V10_SIDE_RESPONSE_PACKET_FULL_SCHEMA
    )
    assert watchdog.V10_H4_SIDE_RESPONSE_PACKET_COMPRESSION_SCHEMA == (
        V10_SIDE_RESPONSE_PACKET_COMPRESSION_SCHEMA
    )
    assert watchdog.V10_H4_SIDE_RESPONSE_PACKET_FULL_PRODUCER_METHOD == (
        V10_SIDE_RESPONSE_PACKET_FULL_METHOD
    )
    assert watchdog.V10_H4_SIDE_RESPONSE_PACKET_COMPRESSION_METHOD == (
        V10_SIDE_RESPONSE_PACKET_COMPRESSION_METHOD
    )


def _write_tiny_full_recheck_fixture(tmp_path: Path) -> tuple[Path, Path]:
    raw_root = tmp_path / "raw"
    packet_root = tmp_path / "packet"
    numerical = raw_root / "numerical_output"
    numerical.mkdir(parents=True)
    packet_root.mkdir()
    source_sha = "a" * 40
    input_sha = "b" * 64
    physical_sha = "c" * 64
    for name, value in (
        ("source_sha.txt", source_sha),
        ("input_sha256.txt", input_sha),
        ("physical_model_sha256.txt", physical_sha),
    ):
        (raw_root / name).write_text(value + "\n", encoding="utf-8")
    records = [
        {
            "column_index": index,
            "label": f"modal_response_{index}",
            "finite": True,
            "true_residual_relative": 1.0e-10,
        }
        for index in range(960)
    ]
    records.append(
        {
            "column_index": 960,
            "label": "physical_side_rhs",
            "finite": True,
            "rhs_norm": 0.0,
            "output_norm": 0.0,
            "zero_map_pass": True,
        }
    )
    expected_holdout = orchestration.V10_SIDE_RESPONSE_PACKET_FULL_HOLDOUT_COLUMNS
    training = [index for index in range(960) if index not in expected_holdout]
    shards = []
    cursor = 0
    for rank in range(8):
        end = 132300 * (rank + 1) // 8
        filename = f"rank{rank:04d}_response.npy"
        path = packet_root / filename
        path.write_bytes(b"tiny-shard")
        shards.append(
            {
                "rank": rank,
                "path": filename,
                "ownership_range": [cursor, end],
                "shape": [end - cursor, 961],
                "dtype": "complex128",
                "file_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
        cursor = end
    manifest = {
        "schema": V10_SIDE_RESPONSE_PACKET_FULL_SCHEMA,
        "method": V10_SIDE_RESPONSE_PACKET_FULL_METHOD,
        "global_rows": 132300,
        "column_count": 961,
        "training_column_indices": training,
        "training_column_count": 950,
        "holdout_column_indices": list(expected_holdout),
        "holdout_column_count": 10,
        "zero_column_index": 960,
        "shards": shards,
        "provenance": {
            "source_sha": source_sha,
            "input_sha256": input_sha,
            "physical_model_sha256": physical_sha,
            "selected_mode_packet_manifest_sha256": (
                orchestration.V10_SIDE_RESPONSE_PACKET_FROZEN_HOLDOUT_MANIFEST_SHA256
            ),
            "exact_spool_manifest_sha256": (
                orchestration.V10_SIDE_RESPONSE_PACKET_FROZEN_HOLDOUT_MANIFEST_SHA256
            ),
            "factor_identity": {
                "side": "bottom",
                "action": "research_exact_side_lu",
                "factor_only_storage": True,
                "qualification_scope": (
                    "task039.v10.h4.side_response_packet.full_producer.v1"
                ),
                "profile_id": "task039.v10.h4.side_response_packet.full_producer.v1",
            },
        },
    }
    manifest_path = packet_root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    (numerical / "memory_stage_markers.raw.jsonl").write_text(
        json.dumps(
            {
                "stage": "v10_side_response_packet_full_producer_cleanup",
                "detail": {
                    "selected_mode_packet_released": True,
                    "factor_count_after_cleanup": 0,
                    "qep_count": 0,
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    diagnostic = {
        "schema": V10_SIDE_RESPONSE_PACKET_FULL_SCHEMA,
        "method": V10_SIDE_RESPONSE_PACKET_FULL_METHOD,
        "source_sha": source_sha,
        "input_sha256": input_sha,
        "physical_model_sha256": physical_sha,
        "column_records": records,
        "packet": {"manifest_sha256": manifest_sha},
        "holdout_provenance": {
            "producer_source_sha": orchestration.V9_FROZEN_HOLDOUT_PRODUCER_SHA,
            "catalog": {
                "catalog_sha256": orchestration.V9_FROZEN_HOLDOUT_CATALOG_SHA256
            },
            "manifest_sha256": (
                orchestration.V10_SIDE_RESPONSE_PACKET_FROZEN_HOLDOUT_MANIFEST_SHA256
            ),
        },
        "factor_inventory": {
            "exact_side_factor_count_ready": 1,
            "exact_side_factor_count_after_cleanup": 0,
            "global_direct_factor_count": 0,
            "nested_ksp_count": 0,
        },
        "lifecycle": {"producer_cleanup_completed": True},
        "projected_payload_bytes": 132300 * 961 * 16,
        "report_gate": {
            "measured_full_packet_setup_wall_seconds": 1.0,
            "measured_full_packet_solve_wall_seconds": 2.0,
            "measured_full_packet_total_wall_seconds": 3.0,
        },
    }
    diagnostic_path = numerical / "v3_v7_diagnostic.json"
    diagnostic_path.write_text(json.dumps(diagnostic), encoding="utf-8")
    (raw_root / "run_summary.json").write_text(
        json.dumps(
            {
                "status": "finished",
                "exit_status": 0,
                "resource_authority": {
                    "v10_h4_side_response_packet_full_producer_telemetry": {
                        "worker_record_status": "contract_mismatch",
                        "worker_record_contract_reason": "schema_mismatch",
                        "construction_interval_summary": {
                            "peak_process_tree_rss_bytes": 54497624064
                        },
                        "overall_peak_swap_bytes": 0,
                        "zero_swap_observed": True,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    return raw_root, packet_root


@pytest.mark.parametrize("mutation", ("pass", "schema", "producer", "shard", "release"))
def test_v10_full_recheck_tiny_fixture_and_negative_contracts(
    tmp_path: Path, monkeypatch, mutation: str
) -> None:
    raw_root, packet_root = _write_tiny_full_recheck_fixture(tmp_path)
    expected_source_sha = "a" * 40

    def fake_load(path, **_kwargs):
        rank = int(Path(path).name[4:8])
        start = 132300 * rank // 8
        end = 132300 * (rank + 1) // 8
        return SimpleNamespace(shape=(end - start, 961), dtype=np.dtype("complex128"))

    monkeypatch.setattr(orchestration.np, "load", fake_load)
    if mutation == "schema":
        path = raw_root / "numerical_output" / "v3_v7_diagnostic.json"
        diagnostic = json.loads(path.read_text(encoding="utf-8"))
        diagnostic["schema"] = "wrong.schema"
        path.write_text(json.dumps(diagnostic), encoding="utf-8")
    elif mutation == "producer":
        expected_source_sha = "d" * 40
    elif mutation == "shard":
        path = packet_root / "manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["shards"][0]["file_sha256"] = "0" * 64
        path.write_text(json.dumps(manifest), encoding="utf-8")
        diagnostic_path = raw_root / "numerical_output" / "v3_v7_diagnostic.json"
        diagnostic = json.loads(diagnostic_path.read_text(encoding="utf-8"))
        diagnostic["packet"]["manifest_sha256"] = hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        diagnostic_path.write_text(json.dumps(diagnostic), encoding="utf-8")
    elif mutation == "release":
        path = raw_root / "numerical_output" / "memory_stage_markers.raw.jsonl"
        marker = json.loads(path.read_text(encoding="utf-8"))
        marker["detail"]["selected_mode_packet_released"] = False
        path.write_text(json.dumps(marker) + "\n", encoding="utf-8")
    result = orchestration.recheck_v10_h4_full_side_response_packet(
        raw_root,
        packet_root,
        expected_producer_source_sha=expected_source_sha,
        checker_source_sha="e" * 40,
    )
    expected = (
        "FULL_SIDE_RESPONSE_PACKET_RECHECK_PASS"
        if mutation == "pass"
        else "FULL_SIDE_RESPONSE_PACKET_RECHECK_FAILED"
    )
    assert result["classification"] == expected
    if mutation == "schema":
        assert result["checks"]["schema_method"] is False
    elif mutation == "producer":
        assert result["checks"]["producer_source_sha"] is False
        assert result["checks"]["root_identity_files"] is False
    elif mutation == "shard":
        assert result["checks"]["shards_hash_shape_dtype"] is False
    elif mutation == "release":
        assert result["checks"]["packet_release"] is False


def test_v10_side_response_schedule_and_projection_contract() -> None:
    schedule = orchestration.v10_side_response_packet_pilot_schedule()
    assert len(schedule) == 16
    assert len({item["label"] for item in schedule}) == 16
    assert sum(item["kind"] == "selected_modal" for item in schedule) == 10
    assert sum(item["kind"] == "holdout" for item in schedule) == 3
    assert sum(item["kind"] == "deterministic_random" for item in schedule) == 2
    assert sum(item["kind"] == "physical_zero_replacement" for item in schedule) == 1
    selected = {
        int(item["column"]) for item in schedule if item["kind"] == "selected_modal"
    }
    assert [
        int(item["column"]) for item in schedule if item["kind"] == "selected_modal"
    ] == list(orchestration.V10_SIDE_RESPONSE_PACKET_FROZEN_SELECTED_COLUMNS)
    replacement = next(
        item for item in schedule if item["kind"] == "physical_zero_replacement"
    )
    assert 0 <= int(replacement["column"]) < 960
    assert int(replacement["column"]) not in selected
    assert projected_response_payload_bytes(
        11, V10_SIDE_RESPONSE_PACKET_FULL_COLUMNS
    ) == (11 * V10_SIDE_RESPONSE_PACKET_FULL_COLUMNS * 16)
    assert projected_response_wall_seconds(16.0) == pytest.approx(961.0)
    holdout = tuple(orchestration.V10_SIDE_RESPONSE_PACKET_FULL_HOLDOUT_COLUMNS)
    full_schedule = orchestration.v10_side_response_packet_full_schedule()
    assert tuple(item["column"] for item in full_schedule) == tuple(range(961))
    assert (
        tuple(item["column"] for item in full_schedule if item["column"] in holdout)
        == holdout
    )
    assert full_schedule[-1]["label"] == "physical_side_rhs"


def test_v10_side_response_requires_resolved_64_hex_provenance(tmp_path: Path) -> None:
    payload = {
        "provenance": {
            "input_sha256": "b" * 64,
            "physical_model_sha256": "c" * 64,
        }
    }
    assert orchestration._v10_side_response_resolved_provenance(payload) == (
        "b" * 64,
        "c" * 64,
    )
    with pytest.raises(ValueError, match="resolved provenance metadata"):
        orchestration._v10_side_response_resolved_provenance(
            {"input_sha256": "b" * 64, "physical_model_sha256": "c" * 64}
        )
    values = np.zeros((2, V10_SIDE_RESPONSE_PACKET_COLUMNS), dtype=np.complex128)
    records = [
        {"label": f"column_{index}", "kind": "tiny"}
        for index in range(V10_SIDE_RESPONSE_PACKET_COLUMNS)
    ]
    with pytest.raises(ValueError, match="64-hex input_sha256"):
        write_exact_side_response_packet(
            tmp_path / "rejected",
            values,
            global_rows=2,
            ownership_range=(0, 2),
            column_records=records,
            source_sha="a" * 40,
            input_sha256="not_available",
            physical_model_sha256="c" * 64,
            comm=MPI.COMM_SELF,
        )


def test_v10_side_response_packet_exact_and_cross_shard_remap(tmp_path: Path) -> None:
    comm = MPI.COMM_WORLD
    global_rows = 3 * comm.size
    first = 3 * comm.rank
    ownership = (first, first + 3)
    root = Path(comm.bcast(str(tmp_path / f"packet-{comm.size}"), root=0))
    if comm.rank == 0:
        shutil.rmtree(root, ignore_errors=True)
    comm.barrier()
    values = (
        np.arange(
            first * V10_SIDE_RESPONSE_PACKET_COLUMNS,
            (first + 3) * V10_SIDE_RESPONSE_PACKET_COLUMNS,
            dtype=np.float64,
        )
        .reshape((3, V10_SIDE_RESPONSE_PACKET_COLUMNS), order="C")
        .astype(np.complex128)
    )
    values = np.asfortranarray(values)
    expected_values = values.copy(order="F")
    records = [
        {"label": f"column_{index}", "kind": "tiny"}
        for index in range(V10_SIDE_RESPONSE_PACKET_COLUMNS)
    ]
    written = write_exact_side_response_packet(
        root,
        values,
        global_rows=global_rows,
        ownership_range=ownership,
        column_records=records,
        source_sha="a" * 40,
        input_sha256="b" * 64,
        physical_model_sha256="c" * 64,
        comm=comm,
    )
    assert values.flags.writeable is True
    values.fill(0.0)
    exact = load_exact_side_response_packet(
        written["manifest_path"],
        expected_manifest_sha256=written["manifest_sha256"],
        expected_provenance={
            "source_sha": "a" * 40,
            "input_sha256": "b" * 64,
            "physical_model_sha256": "c" * 64,
        },
        global_rows=global_rows,
        ownership_range=ownership,
        comm=comm,
    )
    np.testing.assert_array_equal(exact.local_values, expected_values)
    assert exact.local_values.flags.writeable is False
    assert exact.diagnostics["ownership_mode"] == "producer_owner_rows_mmap"
    assert exact.diagnostics["source_shard_hash_verified_local"] is True
    exact.destroy()
    assert exact.diagnostics["released"] is True

    remap = load_exact_side_response_packet(
        written["manifest_path"],
        expected_manifest_sha256=written["manifest_sha256"],
        expected_provenance={
            "source_sha": "a" * 40,
            "input_sha256": "b" * 64,
            "physical_model_sha256": "c" * 64,
        },
        global_rows=global_rows,
        ownership_range=(1, global_rows - 1),
        comm=comm,
    )
    assert remap.diagnostics["ownership_mode"] == "remapped_owner_rows"
    expected_global = (
        np.arange(global_rows * V10_SIDE_RESPONSE_PACKET_COLUMNS, dtype=np.float64)
        .reshape((global_rows, V10_SIDE_RESPONSE_PACKET_COLUMNS))
        .astype(np.complex128)
    )
    np.testing.assert_array_equal(remap.local_values, expected_global[1:-1])
    assert remap.local_values.flags.writeable is False
    assert remap.diagnostics["global_basis_materialized"] is False
    remap.destroy()
    comm.barrier()
    if comm.rank == 0:
        shutil.rmtree(root, ignore_errors=True)


def test_v10_side_response_consumer_marks_begin_and_returns_released_packet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakePacket:
        def __init__(self) -> None:
            self._released = False

        @property
        def diagnostics(self) -> dict[str, object]:
            return {
                "ownership_mode": "producer_owner_rows_mmap",
                "released": self._released,
                "consumer_factor_count": 0,
            }

        def destroy(self) -> None:
            self._released = True

    packet = FakePacket()
    markers: list[str] = []
    marker_details: dict[str, dict[str, object]] = {}

    def record_marker(marker: str, detail: dict[str, object]) -> None:
        markers.append(marker)
        marker_details[marker] = dict(detail)

    monkeypatch.setattr(
        orchestration,
        "assemble_hybrid_local_dtn_action_system",
        lambda *_args, **_kwargs: pytest.fail(
            "consumer must not assemble a side system"
        ),
    )
    monkeypatch.setattr(
        orchestration,
        "load_exact_side_response_packet",
        lambda *_args, **_kwargs: packet,
    )
    result = orchestration.run_v10_h4_side_response_packet_consumer(
        manifest_path="unused/manifest.json",
        manifest_sha256="d" * 64,
        source_sha="a" * 40,
        input_sha256="b" * 64,
        physical_model_sha256="c" * 64,
        global_rows=2,
        ownership_range=(0, 2),
        comm=MPI.COMM_SELF,
        marker_callback=record_marker,
    )
    assert markers == [
        "v10_side_response_packet_consumer_begin",
        "v10_side_response_packet_consumer_loaded",
        "v10_side_response_packet_consumer_released",
    ]
    assert marker_details[markers[-1]]["released"] is True
    assert result["packet"]["released"] is True
    assert result["factor_inventory"]["consumer_factor_count"] == 0
    assert result["selected_mode_packet_opened"] is False
    assert result["qep_count"] == 0
    assert result["sgs_executed"] is False


def test_v10_side_response_compression_uses_global_tsqr_projection() -> None:
    comm = MPI.COMM_WORLD
    local_rows = 4
    first = comm.rank * local_rows
    values = np.zeros(
        (local_rows, V10_SIDE_RESPONSE_PACKET_FULL_COLUMNS),
        dtype=np.complex128,
        order="F",
    )
    for local_index in range(local_rows):
        global_index = first + local_index
        values[local_index, :960] = (global_index + 1.0) + 1j * (global_index + 2.0)
    train = tuple(
        index
        for index in range(960)
        if index not in {0, 1, 240, 267, 479, 480, 481, 720, 746, 959}
    )
    holdout = tuple(index for index in (0, 1, 240, 267, 479, 480, 481, 720, 746, 959))
    packet = ExactSideResponsePacket(
        values,
        {
            "training_column_indices": list(train),
            "holdout_column_indices": list(holdout),
            "zero_column_index": 960,
        },
        Path("tiny-full-packet-manifest.json"),
        {"released": False},
    )
    result = compress_owner_row_response_packet(
        packet,
        training_column_indices=train,
        holdout_column_indices=holdout,
        zero_column_index=960,
        comm=comm,
    )
    assert result["zero_map_pass"] is True
    assert result["zero_output_norm"] <= 1.0e-13
    assert result["numerical_rank"] == 1
    assert result["gram_or_normal_equations_used"] is False
    assert result["one_tsqr_one_small_r_svd"] is True
    assert len(result["rank_reports"]) == 4
    assert all(report["effective_rank"] == 1 for report in result["rank_reports"])
    assert all(
        report["holdout_worst_projection_error"] is not None
        and report["holdout_worst_projection_error"] <= 1.0e-12
        for report in result["rank_reports"]
    )
    assert result["tsqr_reconstruction_error"] <= 1.0e-12
    assert all(
        report["training_optimal_frobenius_error"] <= 1.0e-12
        and report["q_orthogonality_error"] <= 1.0e-12
        for report in result["rank_reports"]
    )
    global_rows = local_rows * comm.size
    expected_tolerance = (
        np.finfo(float).eps
        * max(global_rows, len(train))
        * max(float(result["singular_values"][0]), 1.0)
    )
    assert result["svd_tolerance"] == pytest.approx(expected_tolerance)
    packet.destroy()


def test_v10_full_owner_row_writer_loader_round_trip(tmp_path: Path) -> None:
    comm = MPI.COMM_WORLD
    local_rows = 2
    global_rows = local_rows * comm.size
    first = local_rows * comm.rank
    root = Path(comm.bcast(str(tmp_path / f"full-packet-{comm.size}"), root=0))
    if comm.rank == 0:
        shutil.rmtree(root, ignore_errors=True)
    comm.barrier()
    holdout = tuple(orchestration.V10_SIDE_RESPONSE_PACKET_FULL_HOLDOUT_COLUMNS)
    train = tuple(index for index in range(960) if index not in holdout)
    records = [
        {
            "label": f"modal_{index}" if index < 960 else "physical_side_rhs",
            "kind": "selected_modal" if index < 960 else "physical_zero_validation",
        }
        for index in range(V10_SIDE_RESPONSE_PACKET_FULL_COLUMNS)
    ]
    factor_identity = {
        "side": "bottom",
        "action": "research_exact_side_lu",
        "factor_only_storage": True,
        "qualification_scope": "tiny_full_response",
        "profile_id": "tiny_full_response",
    }
    values = np.empty(
        (local_rows, V10_SIDE_RESPONSE_PACKET_FULL_COLUMNS),
        dtype=np.complex128,
        order="F",
    )
    for row in range(local_rows):
        global_row = first + row
        values[row, :] = (
            global_row
            + 1.0
            + 1j * (np.arange(V10_SIDE_RESPONSE_PACKET_FULL_COLUMNS) + 2.0)
        )
    values[:, 960] = 0.0
    expected = values.copy(order="F")
    writer = OwnerRowResponsePacketWriter(
        root,
        global_rows=global_rows,
        ownership_range=(first, first + local_rows),
        column_records=records,
        source_sha="a" * 40,
        input_sha256="b" * 64,
        physical_model_sha256="c" * 64,
        comm=comm,
        training_column_indices=train,
        holdout_column_indices=holdout,
        zero_column_index=960,
        identity={"factor_identity": factor_identity},
    )
    for column in range(V10_SIDE_RESPONSE_PACKET_FULL_COLUMNS):
        writer.write_column(column, values[:, column])
    written = writer.finalize()
    assert writer._closed is True
    assert writer._finalized is True
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["training_column_indices"]) == 950
    assert len(manifest["holdout_column_indices"]) == 10
    assert manifest["zero_column_index"] == 960
    assert set(manifest["training_column_indices"]) | set(
        manifest["holdout_column_indices"]
    ) == set(range(960))
    assert set(manifest["training_column_indices"]).isdisjoint(
        manifest["holdout_column_indices"]
    )
    assert manifest["coverage"]["exact"] is True
    assert manifest["provenance"]["factor_identity"] == factor_identity
    assert len(manifest["shards"]) == comm.size
    for shard in manifest["shards"]:
        assert shard["shape"][1] == V10_SIDE_RESPONSE_PACKET_FULL_COLUMNS
        assert shard["dtype"] == "complex128"
        assert len(shard["file_sha256"]) == 64
    packet = load_full_side_response_packet(
        written["manifest_path"],
        expected_manifest_sha256=written["manifest_sha256"],
        expected_provenance={
            "source_sha": "a" * 40,
            "input_sha256": "b" * 64,
            "physical_model_sha256": "c" * 64,
            "factor_identity": factor_identity,
        },
        global_rows=global_rows,
        ownership_range=(first, first + local_rows),
        comm=comm,
    )
    np.testing.assert_array_equal(packet.local_values, expected)
    assert packet.local_values.flags.writeable is False
    assert packet.manifest["provenance"]["source_sha"] == "a" * 40
    assert packet.manifest["provenance"]["input_sha256"] == "b" * 64
    assert packet.diagnostics["owner_row_coverage_exact"] is True
    assert packet.diagnostics["ownership_mode"] == "producer_owner_rows_mmap"
    packet.destroy()
    assert packet.diagnostics["released"] is True
    comm.barrier()
    if comm.rank == 0:
        shutil.rmtree(root, ignore_errors=True)
