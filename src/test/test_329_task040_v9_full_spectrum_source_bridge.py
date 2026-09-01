"""Pure contracts for the V9 corrected full-spectrum source adapter."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from mpi4py import MPI

from benchmarks.task040_level_a import (
    V8_FULL_SPECTRUM_ONLY_FLAG,
    V9_SOURCE_PACKET_MANIFEST_SHA256_OPTION,
    V9_SOURCE_PACKET_ROOT_OPTION,
    build_task040_level_a_plan,
)
from benchmarks.task040_level_a_watchdog import (
    _v9_full_spectrum_active_stage_timeout,
    build_task040_level_a_watchdog_plan,
)
from src.solvers.hybrid_source_canonical_bridge import (
    SOURCE_BRIDGE_PACKET_SCHEMA,
    _v9_read_shard,
    audit_packet_key_sets,
    packet_pair_digest,
    redistribute_owner_packets,
)

_SHA = "17cf5ae28ccdcf7b0a28548ec1296b9956390509"
_PACKET_SHA = "98610d2826342b963e0243ff57dd53753a82d0379021c89130069a9a0900ebd0"


def _paths(tmp_path: Path) -> dict[str, str]:
    return {
        "input_path": str(tmp_path / "input.dat"),
        "exact_spool_root": str(tmp_path / "v5-authority"),
        "run_directory": str(tmp_path / "run"),
        "source_sha": _SHA,
    }


def test_v9_corrected_packet_plan_and_worker_argv(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    plan = build_task040_level_a_watchdog_plan(
        **paths,
        v8_full_spectrum_only=True,
        v9_source_packet_root=tmp_path / "v9-worker",
        v9_source_packet_manifest_sha256=_PACKET_SHA,
    )
    argv = plan["worker_argv"]
    assert V8_FULL_SPECTRUM_ONLY_FLAG in argv
    assert V9_SOURCE_PACKET_ROOT_OPTION in argv
    assert V9_SOURCE_PACKET_MANIFEST_SHA256_OPTION in argv
    assert "--v9-source-bridge-only" not in argv
    assert "--v8-adaptive-schwarz-only" not in argv
    assert "--v8-adaptive-stage-b1-only" not in argv
    assert plan["watchdog"]["hard_stop_bytes"] == 45 * 2**30
    assert plan["watchdog"]["swap_limit_bytes"] == 0
    assert plan["watchdog"]["timeout_seconds"] == 10800
    assert plan["watchdog"]["setup_target_seconds"] == 1800
    assert plan["watchdog"]["transform_target_seconds"] == 900
    assert plan["watchdog"]["one_apply_target_seconds"] == 1200
    assert plan["watchdog"]["minimum_mem_available_bytes"] == 96 * 2**30
    assert plan["watchdog"]["v9_corrected_source_packet"] is True
    assert plan["watchdog"]["v9_marker_stages"] == [
        "v9_full_spectrum_source_packet_validated",
        "v9_full_spectrum_external_owner_vector_ready",
        "v9_full_spectrum_random0_owner_vector_ready",
    ]


def test_v9_packet_arguments_are_a_full_route_pair(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    with pytest.raises(ValueError, match="together"):
        build_task040_level_a_plan(
            **paths,
            v8_full_spectrum_only=True,
            v9_source_packet_root=tmp_path / "packet",
        )
    with pytest.raises(ValueError, match="full-spectrum"):
        build_task040_level_a_plan(
            **paths,
            v9_source_packet_root=tmp_path / "packet",
            v9_source_packet_manifest_sha256=_PACKET_SHA,
        )
    ordinary = build_task040_level_a_plan(**paths)
    assert "v9_corrected_source_packet" not in ordinary


def test_v9_physical_packet_hash_and_key_contract() -> None:
    assert SOURCE_BRIDGE_PACKET_SCHEMA.endswith("packet.v1")
    assert packet_pair_digest(
        "physical-token", 1.0 + 2.0j, label="external_dtn_coupling"
    ) == packet_pair_digest(
        "physical-token", 1.0 + 2.0j, label="external_dtn_coupling"
    )
    assert packet_pair_digest(
        "physical-token", 1.0 + 2.0j, label="external_dtn_coupling"
    ) != packet_pair_digest(
        "physical-token", 1.0 + 2.0j, label="fixed_random_repeat_0"
    )
    audit = audit_packet_key_sets(
        ("k2", "k1", "k1"),
        ("k1", "k2"),
    )
    assert audit["persisted_duplicate_count"] == 1
    assert audit["missing_count"] == 0
    assert audit["extra_count"] == 0


def test_v9_corrected_stage_timeout_boundaries() -> None:
    assert not _v9_full_spectrum_active_stage_timeout(
        "v8_full_spectrum_external_r8", 1201.0, 1.0
    )["active"]
    group2 = _v9_full_spectrum_active_stage_timeout(
        "v8_full_spectrum_group2_factor_ready", 901.0, 1.0
    )
    assert group2["active"] and group2["limit_seconds"] == 900.0
    symbol = _v9_full_spectrum_active_stage_timeout(
        "v8_full_spectrum_symbol_ready", 1801.0, 1.0
    )
    assert symbol["active"] and symbol["limit_seconds"] == 1800.0
    one_apply = _v9_full_spectrum_active_stage_timeout(
        "v8_full_spectrum_external_one_apply_begin", 1201.0, 1.0
    )
    assert one_apply["active"] and one_apply["limit_seconds"] == 1200.0


def test_v9_owner_routing_uses_physical_key_not_shard_order() -> None:
    comm = MPI.COMM_WORLD
    if comm.size not in (1, 2):
        pytest.skip("V9 owner routing contract requires serial or MPI2")
    values = tuple(
        (f"physical-{index}", complex(index + 1, -(index + 2)))
        for index in range(4)
    )
    if comm.size == 1:
        local_packets = list(reversed(values))
        origin_by_key = {key: 0 for key, _ in values}
    else:
        local_packets = list(reversed(values[2 * comm.rank : 2 * comm.rank + 2]))
        origin_by_key = {key: index // 2 for index, (key, _) in enumerate(values)}
    current_owner = {
        key: (origin + 1) % comm.size for key, origin in origin_by_key.items()
    }
    routed, audit = redistribute_owner_packets(
        local_packets, current_owner, comm=comm
    )
    expected = {
        key: value
        for key, value in values
        if current_owner[key] == comm.rank
    }
    assert routed == expected
    assert len(routed) == len(set(routed))
    assert audit["numeric_allgather"] is False
    assert audit["full_numeric_replica"] is False
    assert audit["collective_count"] == 1


def test_v9_shard_load_checks_contract_and_value_bytes(tmp_path: Path) -> None:
    comm = MPI.COMM_WORLD
    if comm.size not in (1, 2):
        pytest.skip("V9 shard contract requires serial or MPI2")
    label = "external_dtn_coupling"
    rank = comm.rank
    packet_dir = tmp_path / "source_bridge"
    rank_dir = packet_dir / f"rank{rank:04d}"
    rank_dir.mkdir(parents=True)
    keys = (f"physical-{rank}-a", f"physical-{rank}-z")
    values = np.asarray((1.0 + rank * 1.0j, 2.0 - rank * 1.0j), dtype=np.complex128)
    keys_path = rank_dir / f"v9_{label}_canonical_keys.json"
    values_path = rank_dir / f"v9_{label}_canonical_values.npy"
    keys_path.write_text(
        json.dumps({"keys": list(keys)}, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    np.save(values_path, values, allow_pickle=False)
    shard = {
        "schema": SOURCE_BRIDGE_PACKET_SCHEMA,
        "side": "bottom",
        "label": label,
        "rank": rank,
        "owner_local": True,
        "keys_path": str(keys_path.relative_to(packet_dir)),
        "values_path": str(values_path.relative_to(packet_dir)),
        "key_count_local": len(keys),
        "key_sha256": hashlib.sha256(keys_path.read_bytes()).hexdigest(),
        "values_sha256": hashlib.sha256(values_path.read_bytes()).hexdigest(),
        "global_key_set_sha256": "key-set",
        "persisted_value_pair_digest_sha256": "persisted-values",
        "current_value_pair_digest_sha256": "current-values",
        "source_identity": {},
        "numeric_allgather": False,
        "full_numeric_replica": False,
    }
    unsigned = dict(shard)
    shard["shard_manifest_sha256"] = hashlib.sha256(
        (json.dumps(unsigned, sort_keys=True, indent=2) + "\n").encode()
    ).hexdigest()
    shard_path = rank_dir / f"v9_{label}_canonical_packet.json"
    shard_path.write_text(
        json.dumps(shard, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    packets, audit = _v9_read_shard(
        tmp_path, {"shards": [shard]}, label, rank
    )
    assert dict(packets) == dict(zip(keys, values, strict=True))
    assert audit["shard_manifest_sha256"] == shard["shard_manifest_sha256"]
    assert audit["key_count_local"] == len(keys)
    assert audit["owner_local"] is True
    assert audit["numeric_allgather"] is False
    assert audit["full_numeric_replica"] is False
    np.save(values_path, values + (1.0 + 0.0j), allow_pickle=False)
    with pytest.raises(ValueError, match="value bytes/hash"):
        _v9_read_shard(tmp_path, {"shards": [shard]}, label, rank)
