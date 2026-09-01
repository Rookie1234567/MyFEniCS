"""Focused V9 physical-key bridge contracts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from mpi4py import MPI

from benchmarks.task040_level_a import build_task040_level_a_plan
from benchmarks.task040_level_a_watchdog import (
    build_task040_level_a_watchdog_plan,
)
from benchmarks.task040_v6_2_interface_schur import (
    V9_SOURCE_BRIDGE_ONLY_METHOD,
    V9_SOURCE_BRIDGE_ONLY_SCHEMA,
    V9_SOURCE_BRIDGE_ONLY_SOURCES,
)
from src.solvers.hybrid_source_canonical_bridge import (
    SOURCE_BRIDGE_PACKET_SCHEMA,
    SOURCE_BRIDGE_TOLERANCE,
    _canonical_residual_gates,
    _key_class_histogram,
    audit_packet_key_sets,
    packet_pair_digest,
    redistribute_owner_packets,
)


COMM = MPI.COMM_WORLD


def test_v9_fixed_residual_gate_names_and_threshold() -> None:
    names = (
        "owner_to_canonical_to_owner_relative",
        "canonical_value_relative",
        "repeated_reconstruction_relative",
        "static_condensed_active_rhs_repeat_relative",
        "current_canonical_repeat_relative",
        "source_norm_relative",
        "roundtrip_canonical_value_relative",
    )
    residuals = {name: 0.0 for name in names}
    assert all(_canonical_residual_gates(residuals).values())
    residuals[names[-1]] = SOURCE_BRIDGE_TOLERANCE * 2.0
    gates = _canonical_residual_gates(residuals)
    assert not gates[names[-1]]
    assert all(gates[name] for name in names[:-1])


def _token(
    dimension: int,
    orientation: dict[str, str],
    coefficient: tuple[float, float],
) -> str:
    return json.dumps(
        ["physical", dimension, "entity", "basis", orientation, "family", coefficient],
        separators=(",", ":"),
    )


def _pair_digest(pairs: list[tuple[str, complex]], label: str) -> str:
    payload = "\n".join(
        sorted(packet_pair_digest(key, value, label=label) for key, value in pairs)
    )
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def test_v9_physical_key_hash_audit_and_owner_routing() -> None:
    if COMM.size > 2:
        pytest.skip("V9-A focused contract is qualified for serial/MPI2")
    keys = (
        _token(1, {"state": "forward"}, (1.0, 0.0)),
        _token(2, {"state": "reverse"}, (0.0, 1.0)),
    )
    values = (1.0 + 2.0j, -3.0 + 0.5j)
    pairs = list(zip(keys, values, strict=True))
    assert _pair_digest(pairs, "external_dtn_coupling") == _pair_digest(
        list(reversed(pairs)), "external_dtn_coupling"
    )
    assert _pair_digest(pairs, "fixed_random_repeat_0") != _pair_digest(
        pairs, "external_dtn_coupling"
    )
    assert packet_pair_digest(keys[0], values[0], side="bottom") != packet_pair_digest(
        keys[0], values[0], side="top"
    )
    assert SOURCE_BRIDGE_PACKET_SCHEMA == (
        "task040.v9.source_canonical_bridge.packet.v1"
    )
    assert SOURCE_BRIDGE_TOLERANCE == 1.0e-12

    histogram = _key_class_histogram(keys)
    assert histogram["entity_dimension"] == {"1": 1, "2": 1}
    assert histogram["tangential_family"] == {
        "edge_tangential": 1,
        "face_tangential": 1,
    }
    assert histogram["orientation_state"] == {
        '{"state":"forward"}': 1,
        '{"state":"reverse"}': 1,
    }
    assert histogram["phase_class"]["unit"] == 1

    bad_missing = audit_packet_key_sets(keys, keys[:1])
    bad_extra = audit_packet_key_sets(keys[:1], keys)
    bad_duplicate = audit_packet_key_sets((keys[0], keys[0]), (keys[0],))
    assert not bad_missing["pass"] and bad_missing["extra_count"] == 1
    assert not bad_extra["pass"] and bad_extra["missing_count"] == 1
    assert not bad_duplicate["pass"]
    assert bad_duplicate["persisted_duplicate_count"] == 1

    if COMM.size == 2:
        owner_by_key = {keys[0]: 1, keys[1]: 0}
        packets = [(keys[COMM.rank], values[COMM.rank])]
        expected = {keys[1 - COMM.rank]: values[1 - COMM.rank]}
    else:
        owner_by_key = {key: 0 for key in keys}
        packets = pairs
        expected = dict(pairs)
    routed, routing = redistribute_owner_packets(packets, owner_by_key, comm=COMM)
    assert routed == expected
    assert routing["numeric_allgather"] is False
    assert routing["full_numeric_replica"] is False
    assert routing["collective_count"] == 1
    assert routing["max_sender_payload_bytes"] >= 16
    assert routing["max_receiver_payload_bytes"] >= 16


def test_v9_source_only_plan_and_worker_contract() -> None:
    if COMM.size > 2:
        pytest.skip("V9-A focused contract is qualified for serial/MPI2")
    run_directory = Path(f"/tmp/task040_v9_source_bridge_contract_{COMM.size}")
    kwargs = {
        "input_path": "/tmp/task040_v9_input.dat",
        "exact_spool_root": "/tmp/task040_v9_spool",
        "run_directory": run_directory,
        "source_sha": "a" * 40,
        "v9_source_bridge_only": True,
    }
    plan = build_task040_level_a_plan(**kwargs)
    assert plan["schema"] == V9_SOURCE_BRIDGE_ONLY_SCHEMA
    assert plan["method"] == V9_SOURCE_BRIDGE_ONLY_METHOD
    assert plan["source_order"] == list(V9_SOURCE_BRIDGE_ONLY_SOURCES)
    assert plan["marker_sequence"] == [
        "v9_source_bridge_preflight",
        "v9_source_bridge_system_ready",
        "v9_source_bridge_source_ready",
        "v9_source_bridge_packet_written",
        "v9_source_bridge_cleanup_complete",
    ]
    assert plan["fixed_configuration"]["numeric_allgather"] is False
    assert plan["fixed_configuration"]["full_numeric_replica"] is False
    with pytest.raises(ValueError):
        build_task040_level_a_plan(
            **kwargs, v8_adaptive_stage_bc_only=True
        )

    watchdog = build_task040_level_a_watchdog_plan(**kwargs)
    command = watchdog["worker_argv"]
    assert command[3]
    assert "--v9-source-bridge-only" in command
    assert "--watchdog-enabled" in command
    assert "--bottom-route-only" in command
    assert not any(argument.startswith(("--v7-", "--v8-")) for argument in command)
    assert watchdog["watchdog"]["hard_stop_bytes"] == 45 * 2**30
    assert watchdog["watchdog"]["swap_limit_bytes"] == 0
    assert watchdog["watchdog"]["timeout_seconds"] == 10800
    assert watchdog["watchdog"]["setup_target_seconds"] is None
    assert watchdog["watchdog"]["one_apply_target_seconds"] is None
    assert watchdog["watchdog"]["cleanup_stage"] == (
        "v9_source_bridge_cleanup_complete"
    )
