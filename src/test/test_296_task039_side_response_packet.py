"""Focused V10-6 side-response packet and consumer lifecycle contracts."""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pytest
from mpi4py import MPI

import benchmarks.task039_v3_7_orchestration as orchestration
from src.solvers.hybrid_side_response_packet import (
    V10_SIDE_RESPONSE_PACKET_COLUMNS,
    V10_SIDE_RESPONSE_PACKET_FULL_COLUMNS,
    load_exact_side_response_packet,
    projected_response_payload_bytes,
    projected_response_wall_seconds,
    write_exact_side_response_packet,
)


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
    np.testing.assert_array_equal(exact.local_values, values)
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
