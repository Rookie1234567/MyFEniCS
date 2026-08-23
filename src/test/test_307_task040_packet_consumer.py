"""Focused Task040 V2-B consumer route contracts."""

from __future__ import annotations

from copy import deepcopy

import pytest

from benchmarks.task040_level_a import (
    TASK040_LEVEL_A_HARD_STOP_BYTES,
    TASK040_V2_INTERFACE_PACKET_CONSUMER_FLAG,
    TASK040_V2_INTERFACE_PACKET_CONSUMER_METHOD,
    TASK040_V2_INTERFACE_PACKET_CONSUMER_SCHEMA,
    TASK040_V2_INTERFACE_PACKET_MANIFEST_SHA256,
    _run_v2_packet_consumer,
    _v2_packet_gamma_rows,
    _v2_packet_provenance,
    build_task040_level_a_plan,
)
from benchmarks.task040_level_a_watchdog import build_task040_level_a_watchdog_plan


def _provenance() -> dict[str, object]:
    return {
        "schema": "task040.v2.interface_packet_producer.v1",
        "source_sha": "a" * 40,
        "input_sha256": "b" * 64,
        "physical_model_sha256": "c" * 64,
        "selected_manifest_sha256": (
            "2dddaf7a6f8f045adabd840970952517d76305c7c0e03c71258642d856c13067"
        ),
        "exact_spool_catalog_sha256": (
            "a2a7fb6fb01df4f795d31ff94f6ac6adf957ac4fe4a5c1a8d05176e3d64c0384"
        ),
        "probe_manifest_sha256": (
            "7a03b2cf80fe5081d1fe1248b9d4c79f3ef4e955a8014e905c2f2ca82797baad"
        ),
        "qep_calls": 0,
        "pde_solve": "not_run",
        "v1_3_built": False,
    }


def test_consumer_plan_is_explicit_and_separate_from_packet_input(tmp_path):
    legacy = build_task040_level_a_plan(
        input_path=tmp_path / "input",
        exact_spool_root=tmp_path / "spool",
        run_directory=tmp_path / "legacy",
        source_sha="1" * 40,
    )
    consumer = build_task040_level_a_plan(
        input_path=tmp_path / "input",
        exact_spool_root=tmp_path / "spool",
        run_directory=tmp_path / "consumer",
        source_sha="2" * 40,
        packet_consumer=True,
        interface_packet_root=tmp_path / "frozen_packet",
    )
    assert legacy["method"] != TASK040_V2_INTERFACE_PACKET_CONSUMER_METHOD
    assert consumer["schema"] == TASK040_V2_INTERFACE_PACKET_CONSUMER_SCHEMA
    assert consumer["packet_consumer"] is True
    assert consumer["oracle_only"] is True
    assert consumer["scalable_candidate"] is False
    assert (
        consumer["absolute_terminate_memory_bytes"] == TASK040_LEVEL_A_HARD_STOP_BYTES
    )
    assert consumer["interface_packet_root"] != consumer["run_directory"]
    assert (
        consumer["packet_manifest_sha256"]
        == TASK040_V2_INTERFACE_PACKET_MANIFEST_SHA256
    )
    assert {
        "outer_ksp",
        "recovery",
        "top",
        "full_hybrid",
        "response_packet",
        "exact_output_vector_load",
    }.issubset(consumer["forbidden"])
    with pytest.raises(ValueError, match="mutually exclusive"):
        build_task040_level_a_plan(
            input_path=tmp_path / "input2",
            exact_spool_root=tmp_path / "spool2",
            run_directory=tmp_path / "bad",
            source_sha="3" * 40,
            interface_schur=True,
            packet_consumer=True,
            interface_packet_root=tmp_path / "frozen_packet2",
        )


def test_consumer_watchdog_argv_uses_read_only_packet_root(tmp_path):
    plan = build_task040_level_a_watchdog_plan(
        input_path=tmp_path / "input",
        exact_spool_root=tmp_path / "spool",
        run_directory=tmp_path / "run",
        source_sha="4" * 40,
        packet_consumer=True,
        interface_packet_root=tmp_path / "frozen_packet",
    )
    command = plan["worker_argv"]
    assert command.count(TASK040_V2_INTERFACE_PACKET_CONSUMER_FLAG) == 1
    assert command[command.index("--interface-packet-root") + 1].endswith(
        "/frozen_packet"
    )
    assert plan["absolute_terminate_memory_bytes"] == TASK040_LEVEL_A_HARD_STOP_BYTES
    assert plan["watchdog"]["absolute_terminate_memory_bytes"] == (
        TASK040_LEVEL_A_HARD_STOP_BYTES
    )
    assert "preferred_memory_bytes" not in plan
    assert "preferred_memory_bytes" not in plan["watchdog"]
    assert command[command.index("--run-directory") + 1].endswith("/run/worker")
    assert not (tmp_path / "run").exists()


def test_consumer_gamma_rows_follow_interface_sets_and_group_order():
    supports = (
        {"active_support": [2, 5, 11]},
        {"active_support": [7, 9, 13]},
    )
    group_rows = (
        [5, 2],
        [9, 5, 2, 12],
        [7, 9, 13],
    )
    lower, middle, upper = _v2_packet_gamma_rows(supports, group_rows)
    assert lower.tolist() == [5, 2]
    assert middle.tolist() == [9, 5, 2]
    assert 7 not in middle
    assert 11 not in lower
    assert upper.tolist() == [7, 9, 13]


def test_consumer_provenance_is_frozen_and_route_does_not_use_exact_oracle():
    actual = _provenance()
    validated = _v2_packet_provenance(
        {"provenance": actual},
        input_sha256=actual["input_sha256"],
        physical_model_sha256=actual["physical_model_sha256"],
    )
    assert validated == actual
    tampered = deepcopy(actual)
    tampered["qep_calls"] = 1
    with pytest.raises(ValueError, match="provenance"):
        _v2_packet_provenance(
            {"provenance": tampered},
            input_sha256=actual["input_sha256"],
            physical_model_sha256=actual["physical_model_sha256"],
        )
    names = set(_run_v2_packet_consumer.__code__.co_names)
    assert "build_petsc_interface_schur_oracle" not in names
    assert "stream_task039_v4_selected_mode_columns" not in names
    assert "outgoing_port_modes_3d" not in names
