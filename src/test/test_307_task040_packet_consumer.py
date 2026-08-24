"""Focused Task040 V2-B consumer route contracts."""

from __future__ import annotations

import time
from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest
from mpi4py import MPI

from benchmarks import check_task040_v2_consumer as consumer_checker
from benchmarks.task040_level_a import (
    TASK040_LEVEL_A_HARD_STOP_BYTES,
    TASK040_LEVEL_A_SOURCE_LABELS,
    TASK040_V2_INTERFACE_PACKET_CONSUMER_FLAG,
    TASK040_V2_INTERFACE_PACKET_CONSUMER_METHOD,
    TASK040_V2_INTERFACE_PACKET_CONSUMER_PROFILE_ID,
    TASK040_V2_INTERFACE_PACKET_CONSUMER_SCHEMA,
    TASK040_V2_INTERFACE_PACKET_MANIFEST_SHA256,
    _run_v2_packet_consumer,
    _v2_collective_stage_error,
    _v2_group_marker,
    _v2_packet_gamma_rows,
    _v2_packet_provenance,
    build_task040_level_a_plan,
)
from benchmarks.task040_level_a_watchdog import build_task040_level_a_watchdog_plan
from src.solvers.hybrid_interface_packet import (
    PacketGroup,
    canonical_key_json,
    redistribute_packet_group_rows,
)
from src.solvers.hybrid_interface_packet_dolfinx import (
    build_gamma_canonical_layout,
    make_gamma_entity_block,
    reconstruct_owner_local_basis,
)


def test_v2_group_markers_have_ordered_stage_fields() -> None:
    layout = SimpleNamespace(audit={"local_row_count": 2}, blocks=(object(), object()))
    events: list[tuple[str, dict[str, object]]] = []

    def callback(stage, detail):
        events.append((stage, dict(detail)))

    stages = (
        "packet_group_load_begin",
        "packet_group_load_ready",
        "packet_group_owner_redistribute_begin",
        "packet_group_owner_redistribute_ready",
        "packet_group_reconstruct_begin",
        "packet_group_reconstruct_ready",
        "packet_group_roundtrip_audit_begin",
        "packet_group_roundtrip_audit_ready",
        "packet_group_collective_remap_ready",
    )
    timed_ready_stages = {
        "packet_group_load_ready",
        "packet_group_owner_redistribute_ready",
        "packet_group_reconstruct_ready",
        "packet_group_roundtrip_audit_ready",
    }
    for stage in stages:
        _v2_group_marker(
            callback,
            stage,
            group=1,
            layout=layout,
            span_size=4,
            comm=MPI.COMM_WORLD,
            started=time.perf_counter() if stage in timed_ready_stages else None,
        )
    assert [stage for stage, _detail in events] == list(stages)
    for stage, detail in events:
        assert detail["group"] == 1
        assert detail["local_rows"] == 2
        assert detail["local_blocks"] == 2
        assert detail["span_size"] == 4
        if stage in timed_ready_stages:
            assert np.isfinite(detail["cross_rank_max_elapsed_seconds"])
            assert detail["cross_rank_max_elapsed_seconds"] >= 0.0
        else:
            assert "cross_rank_max_elapsed_seconds" not in detail


def test_v2_packet_reconstruct_mismatch_is_collective() -> None:
    comm = MPI.COMM_WORLD
    rows = (100 + 2 * comm.rank, 101 + 2 * comm.rank)
    block = make_gamma_entity_block(
        name=f"rank{comm.rank}",
        entity_dimension=1,
        physical_entity={"rank": comm.rank},
        raw_row_ids=rows,
        canonical_to_raw=np.eye(2, dtype=np.complex128),
        orientation_state="test",
    )
    layout = build_gamma_canonical_layout((block,), rows, plane_identity={"test": True})
    keys = list(layout.canonical_keys)
    if comm.rank == 0:
        keys[0] = '{"corrupt":true}'
    local_error = None
    try:
        reconstruct_owner_local_basis(
            layout,
            keys,
            np.ones((2, 1), dtype=np.complex128),
            np.ones((2, 1), dtype=np.complex128),
        )
    except Exception as exc:
        local_error = f"{type(exc).__name__}: {exc}"
    with pytest.raises(
        ValueError,
        match=r"packet_group_reconstruct.*first failing rank 0",
    ):
        _v2_collective_stage_error(
            comm,
            "packet_group_reconstruct",
            local_error,
        )


def test_v2_packet_owner_redistribution_changes_owners_and_order() -> None:
    comm = MPI.COMM_WORLD
    global_indices = tuple(range(8))
    keys = tuple(canonical_key_json({"row": index}) for index in global_indices)

    source_indices = tuple(
        index for index in global_indices if (index + 1) % comm.size == comm.rank
    )
    target_indices = [
        index for index in global_indices if index % comm.size == comm.rank
    ]
    if comm.size == 1 or comm.rank % 2:
        target_indices.reverse()

    def row(index: int, offset: float) -> list[complex]:
        return [
            complex(index + 1.0, offset + index),
            complex(10.0 + index, -offset - index),
        ]

    source = PacketGroup(
        "group0",
        tuple(keys[index] for index in source_indices),
        np.asarray([row(index, 0.25) for index in source_indices], dtype=np.complex128),
        np.asarray([row(index, 0.75) for index in source_indices], dtype=np.complex128),
    )
    target_keys = tuple(keys[index] for index in target_indices)
    redistributed, audit = redistribute_packet_group_rows(
        source,
        target_keys,
        comm=comm,
    )
    expected_u = np.asarray(
        [row(index, 0.25) for index in target_indices], dtype=np.complex128
    )
    expected_v = np.asarray(
        [row(index, 0.75) for index in target_indices], dtype=np.complex128
    )
    assert redistributed.keys == target_keys
    np.testing.assert_allclose(redistributed.U, expected_u)
    np.testing.assert_allclose(redistributed.V, expected_v)
    assert audit["source_global_row_count"] == 8
    assert audit["target_global_row_count"] == 8
    assert audit["source_target_key_bijection"] is True
    assert audit["canonical_key_metadata_allgather"] is True
    assert audit["numeric_allgather"] is False
    assert audit["basis_global_replicated"] is False


def test_v2_packet_owner_redistribution_rejects_global_target_duplicate() -> None:
    comm = MPI.COMM_WORLD
    keys = tuple(canonical_key_json({"row": index}) for index in range(8))
    source_indices = tuple(
        index for index in range(8) if (index + 1) % comm.size == comm.rank
    )
    target_indices = [index for index in range(8) if index % comm.size == comm.rank]
    if comm.rank == 0:
        target_indices[0] = 1
    source = PacketGroup(
        "group0",
        tuple(keys[index] for index in source_indices),
        np.ones((len(source_indices), 1), dtype=np.complex128),
        np.ones((len(source_indices), 1), dtype=np.complex128),
    )
    with pytest.raises(
        ValueError,
        match=r"collective packet owner redistribution metadata failed",
    ):
        redistribute_packet_group_rows(
            source,
            tuple(keys[index] for index in target_indices),
            comm=comm,
        )


def _consumer_checker_manifest() -> dict[str, object]:
    provenance = consumer_checker._expected_provenance()
    identity = {
        "input_sha256": provenance["input_sha256"],
        "physical_model_sha256": provenance["physical_model_sha256"],
        "selected_manifest_sha256": provenance["selected_manifest_sha256"],
        "spool_catalog_sha256": provenance["exact_spool_catalog_sha256"],
        "probe_manifest_sha256": provenance["probe_manifest_sha256"],
        "exact_output_identity_sha256": {
            label: f"{index + 1:064x}"
            for index, label in enumerate(TASK040_LEVEL_A_SOURCE_LABELS[1:])
        },
    }
    rows = (7560, 15120, 7560)
    spans = (296, 776, 480)
    diagnostic_groups = [
        {
            "group": index,
            "span_size": spans[index],
            "gamma_layout": {
                "global_row_count": rows[index],
                **({} if index == 1 else {"global_size": rows[index]}),
            },
        }
        for index in range(3)
    ]
    return {
        "schema": "task040.interface_schur_packet.v1",
        "packet_complete": True,
        "group_order": ["group0", "group1", "group2"],
        "rank_count": 8,
        "basis_global_replicated": False,
        "numeric_allgather": False,
        "fe_numeric_allgather": False,
        "provenance": provenance,
        "groups": {
            name: {"global_count": rows[index]}
            for index, name in enumerate(("group0", "group1", "group2"))
        },
        "diagnostics": {
            "groups": diagnostic_groups,
            "identity_observed": identity,
        },
    }


def _consumer_checkpoint(value: float) -> dict[str, object]:
    return {
        "finite": True,
        "reported_relative_residual": value,
        "true_residual_relative": value,
    }


def _consumer_screen() -> dict[str, object]:
    labels = list(TASK040_LEVEL_A_SOURCE_LABELS[1:])
    phase1_values = {"0": 1.0, "4": 0.5, "8": 0.2, "16": 0.1}
    phase2_values = {**phase1_values, "32": 1.0e-4}

    def phase(values: dict[str, float], max_it: int) -> dict[str, object]:
        return {
            label: {
                "checkpoints": {
                    key: _consumer_checkpoint(value) for key, value in values.items()
                },
                "max_it": max_it,
                "restart": 32,
                "shared_ksp": True,
                "zero_initial_guess": True,
                "zero_initial_guess_count": 1,
                "pc_side": "right",
                "ksp_breakdown": False,
                "true_residual_matvec_count": len(values) - 1,
                "right_pc_apply_count": 4 if max_it == 16 else 5,
            }
            for label in labels
        }

    return {
        "schema": "task040.v1_1.right_fgmres_batch.v1",
        "labels": labels,
        "phase1": phase(phase1_values, 16),
        "phase2": phase(phase2_values, 32),
        "resource_at_phase_boundary": {
            "rss_bytes": 1,
            "swap_bytes": 0,
            "all_status_readable": True,
        },
        "conditional_32_authorized": True,
        "phase1_frozen_gate": False,
        "stop_on_frozen_gate": True,
        "ksp_setup_count": 1,
        "ksp_destroy_count": 1,
        "ksp_destroyed": True,
        "right_pc_apply_count": 45,
        "single_right_pc_setup": True,
        "zero_initial_guess_all_rhs": True,
    }


def _consumer_run_fixture() -> tuple[
    dict[str, object], dict[str, object], dict[str, object]
]:
    manifest = _consumer_checker_manifest()
    labels = list(TASK040_LEVEL_A_SOURCE_LABELS)
    reports = [
        {
            "label": label,
            "source_norm": 0.0 if index == 0 else 1.0,
            "output_norm": 0.0 if index == 0 else 1.0,
            "true_residual_norm": 0.0 if index == 0 else 0.5,
            "true_residual_relative": None if index == 0 else 0.5,
            "repeat_error": 0.0,
            "finite": True,
            "physical_zero": index == 0,
        }
        for index, label in enumerate(labels)
    ]
    factor_inventory = {
        "observed": True,
        "factor_count_ready": 3,
        "cross_section_factor_count_ready": 3,
        "exact_interface_oracle_factor_count": 0,
        "full_side_exact_factor_count": 0,
        "global_direct_factor_count": 0,
        "nested_ksp_count": 0,
        "oracle_only": True,
        "scalable_candidate": False,
    }
    one_apply = {
        "reports": reports,
        "action_identity": {
            "carrier": "petsc_vecscatter",
            "global_numpy_copy": False,
            "subdomain_vectors_global_numpy_copy": False,
            "restriction_prolongation_pass": True,
            "bare_operator_unchanged": True,
        },
        "gate": {
            "finite_pass": False,
            "zero_map_pass": False,
            "action_identity_pass": False,
            "repeat_pass": False,
            "linearity_pass": False,
            "factor_inventory_pass": False,
            "linearity_relative_error": 0.0,
            "pass": False,
        },
        "factor_inventory": factor_inventory,
        "formal_source_apply_count": 6,
        "repeat_audit_apply_count": 6,
        "linearity_audit_apply_count": 1,
        "action_apply_count_delta": 13,
    }
    lifecycle = {
        "factor_count_ready": 3,
        "factor_count_after_cleanup": 0,
        "projected_inverse_count_after_cleanup": 0,
        "simultaneous_factor_count_max": 3,
        "action_destroyed": True,
        "factor_destroyed": True,
        "worker_cleanup": {
            "factor_owner": {
                "ready": {"factor_count_ready": 3, "auxiliary_owner_count": 3},
                "after": {
                    "factor_count_after_cleanup": 0,
                    "auxiliary_owner_count": 0,
                    "destroyed": True,
                },
            }
        },
    }
    groups = [
        {
            "group": index,
            "global_row_count": rows,
            "span_size": span,
            "pass": False,
            "local": {
                "U_relative_error": 0.0,
                "V_relative_error": 0.0,
                "max_relative_error": 0.0,
                "pass": False,
            },
            "collective_max_relative_error": 0.0,
        }
        for index, (rows, span) in enumerate(
            zip((7560, 15120, 7560), (296, 776, 480), strict=True)
        )
    ]
    provenance = manifest["provenance"]
    raw = {
        "packet_consumer": True,
        "producer_source_sha": consumer_checker.EXPECTED_PRODUCER_SOURCE_SHA,
        "packet_manifest_sha256": TASK040_V2_INTERFACE_PACKET_MANIFEST_SHA256,
        "packet_provenance": provenance,
        "basis_global_replicated": False,
        "fe_numeric_allgather": False,
        "groups": groups,
        "remap_pass": False,
        "factor_inventory": factor_inventory,
        "projected_diagnostics": {
            "projected_factor_count_ready": 3,
            "scalar_base_factor_count": 3,
            "projected_inverse_factor_count": 3,
            "basis_global_replicated": False,
            "fe_numeric_allgather": False,
            "exact_interface_oracle_factor_count": 0,
            "full_side_exact_factor_count": 0,
            "global_direct_factor_count": 0,
            "nested_ksp_count": 0,
            "oracle_only": True,
            "scalable_candidate": False,
        },
        "one_apply": one_apply,
        "fgmres_screen": _consumer_screen(),
        "first_preferred_checkpoint": 32,
        "action_destroyed": True,
        "factor_destroyed": True,
        "lifecycle": lifecycle,
        "source_loading": {
            "labels": labels,
            "rhs_vectors_loaded": 6,
            "exact_output_vectors_loaded": 0,
            "exact_output_metadata_hash_validation_only": True,
        },
        "forbidden_routes": [
            "qep",
            "exact_interface_oracle",
            "outer_ksp",
            "recovery",
            "top",
            "full_hybrid",
            "response_packet",
            "exact_output_vector_load",
        ],
    }
    source_sha = "d" * 40
    run = {
        "schema": "task040.v2.interface_packet_consumer.v1",
        "method": "task040_v2_interface_packet_consumer",
        "profile": TASK040_V2_INTERFACE_PACKET_CONSUMER_PROFILE_ID,
        "source_sha": source_sha,
        "input_sha256": provenance["input_sha256"],
        "physical_model_sha256": provenance["physical_model_sha256"],
        "selected_manifest_sha256": provenance["selected_manifest_sha256"],
        "exact_spool_catalog_sha256": provenance["exact_spool_catalog_sha256"],
        "packet_manifest_sha256": TASK040_V2_INTERFACE_PACKET_MANIFEST_SHA256,
        "packet_producer_source_sha": consumer_checker.EXPECTED_PRODUCER_SOURCE_SHA,
        "rhs_vectors_loaded": 6,
        "exact_output_vectors_loaded": 0,
        "qep_calls": 0,
        "pde_solve": "not_run",
        "interface_packet_raw": raw,
    }
    watchdog = {
        "method": "task040_v2_interface_packet_consumer",
        "source_sha": source_sha,
        "hard_stop_bytes": consumer_checker.RESOURCE_LIMIT_BYTES,
        "termination_reason": "natural_exit",
        "return_code": 0,
        "run_summary_present": True,
        "run_summary_sha256": "f" * 64,
        "all_status_readable": True,
        "swap_authority_readable": True,
        "peak_swap_bytes": 0,
        "peak_dedicated_cgroup_swap_bytes": 0,
        "peak_rss_bytes": 1,
        "sample_count": 1,
    }
    return run, watchdog, manifest


def _consumer_timeline_row(
    *, readable: bool, stage: str, stage_status: str = "running"
) -> dict[str, object]:
    return {
        "stage": stage,
        "stage_status": stage_status,
        "rss_bytes": 1,
        "swap_bytes": 0,
        "resource_authority": {
            "process_tree": {
                "pids": [1],
                "all_status_readable": readable,
                "swap_bytes": 0,
            },
            "job_cgroup": {
                "dedicated_job_cgroup": False,
                "swap_current_bytes": 0,
            },
        },
    }


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


def test_consumer_gamma_rows_preserve_owner_local_global_contract():
    """Globally replicated support metadata is filtered to local owner rows."""
    comm = MPI.COMM_WORLD
    local_rows = [row for row in range(8) if row % comm.size == comm.rank]
    lower_local = [row for row in reversed(local_rows) if row < 4]
    middle_local = list(reversed(local_rows))
    upper_local = [row for row in reversed(local_rows) if row >= 4]
    supports = (
        {"active_support": list(range(4))},
        {"active_support": list(range(4, 8))},
    )

    lower, middle, upper = _v2_packet_gamma_rows(
        supports,
        (lower_local, middle_local, upper_local),
    )

    assert lower.tolist() == lower_local
    assert middle.tolist() == [row for row in middle_local if row < 8]
    assert upper.tolist() == upper_local
    for observed, expected in (
        (lower, range(4)),
        (middle, range(8)),
        (upper, range(4, 8)),
    ):
        gathered = [row for rows in comm.allgather(observed.tolist()) for row in rows]
        assert sorted(gathered) == list(expected)
        assert len(gathered) == len(set(gathered))


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


def test_v2_consumer_checker_recomputes_gate_and_classifies_tamper():
    run, watchdog, manifest = _consumer_run_fixture()
    result = consumer_checker.recompute_v2_consumer(
        run,
        watchdog,
        manifest,
        manifest_sha256=TASK040_V2_INTERFACE_PACKET_MANIFEST_SHA256,
        run_summary_sha256="f" * 64,
        expected_source_sha=run["source_sha"],
    )
    assert result["classification"] == "PROJECTED_EXACT_TRANSMISSION_PASS"
    assert result["gate_pass"] is True
    assert result["derived"]["first_preferred_checkpoint"] == 32
    assert result["checks"]["one_apply_implementation"] is True

    resource_run, resource_watchdog, resource_manifest = deepcopy(
        (run, watchdog, manifest)
    )
    resource_watchdog["peak_rss_bytes"] = consumer_checker.RESOURCE_LIMIT_BYTES
    resource_watchdog["sample_count"] = 0
    resource_result = consumer_checker.recompute_v2_consumer(
        resource_run,
        resource_watchdog,
        resource_manifest,
        manifest_sha256=TASK040_V2_INTERFACE_PACKET_MANIFEST_SHA256,
        run_summary_sha256="f" * 64,
        expected_source_sha=resource_run["source_sha"],
    )
    assert resource_result["classification"] == "PROJECTED_CONSUMER_RESOURCE_FAIL"

    remap_run, remap_watchdog, remap_manifest = deepcopy((run, watchdog, manifest))
    remap_run["interface_packet_raw"]["groups"][0]["local"]["U_relative_error"] = 1.0e-9
    remap_result = consumer_checker.recompute_v2_consumer(
        remap_run,
        remap_watchdog,
        remap_manifest,
        manifest_sha256=TASK040_V2_INTERFACE_PACKET_MANIFEST_SHA256,
        run_summary_sha256="f" * 64,
        expected_source_sha=remap_run["source_sha"],
    )
    assert remap_result["classification"] == "PACKET_COORDINATE_IDENTITY_FAIL"

    numeric_run, numeric_watchdog, numeric_manifest = deepcopy(
        (run, watchdog, manifest)
    )
    numeric_run["interface_packet_raw"]["fgmres_screen"]["phase2"][
        "modal_traction_positive"
    ]["checkpoints"]["32"]["true_residual_relative"] = 0.1
    numeric_run["interface_packet_raw"]["first_preferred_checkpoint"] = None
    numeric_result = consumer_checker.recompute_v2_consumer(
        numeric_run,
        numeric_watchdog,
        numeric_manifest,
        manifest_sha256=TASK040_V2_INTERFACE_PACKET_MANIFEST_SHA256,
        run_summary_sha256="f" * 64,
        expected_source_sha=numeric_run["source_sha"],
    )
    assert (
        numeric_result["classification"]
        == "THREE_GROUP_MODE_SUBSPACE_OR_SWEEP_INSUFFICIENT"
    )

    lifecycle_run, lifecycle_watchdog, lifecycle_manifest = deepcopy(
        (run, watchdog, manifest)
    )
    lifecycle_run["interface_packet_raw"]["lifecycle"]["worker_cleanup"][
        "factor_owner"
    ]["after"]["factor_count_after_cleanup"] = 1
    lifecycle_result = consumer_checker.recompute_v2_consumer(
        lifecycle_run,
        lifecycle_watchdog,
        lifecycle_manifest,
        manifest_sha256=TASK040_V2_INTERFACE_PACKET_MANIFEST_SHA256,
        run_summary_sha256="f" * 64,
        expected_source_sha=lifecycle_run["source_sha"],
    )
    assert lifecycle_result["classification"] == "IMPLEMENTATION_FAILURE"

    source_run, source_watchdog, source_manifest = deepcopy((run, watchdog, manifest))
    source_result = consumer_checker.recompute_v2_consumer(
        source_run,
        source_watchdog,
        source_manifest,
        manifest_sha256=TASK040_V2_INTERFACE_PACKET_MANIFEST_SHA256,
        run_summary_sha256="f" * 64,
        expected_source_sha="e" * 40,
    )
    assert source_result["classification"] == "PACKET_COORDINATE_IDENTITY_FAIL"


def test_v2_consumer_checker_excludes_legacy_terminal_teardown() -> None:
    run, watchdog, manifest = _consumer_run_fixture()
    raw = run["interface_packet_raw"]
    screen = raw["fgmres_screen"]
    for item in screen["phase1"].values():
        for checkpoint in ("4", "8", "16"):
            item["checkpoints"][checkpoint]["true_residual_relative"] = 0.99
            item["checkpoints"][checkpoint]["reported_relative_residual"] = 0.99
    screen["phase2"] = {}
    screen["conditional_32_authorized"] = False
    raw["first_preferred_checkpoint"] = None
    watchdog["all_status_readable"] = False
    watchdog["swap_authority_readable"] = False
    watchdog["sample_count"] = 3
    watchdog["artifact_hashes"] = {"process_tree_samples.jsonl": "timeline-sha"}
    timeline = [
        _consumer_timeline_row(readable=True, stage="running"),
        _consumer_timeline_row(readable=True, stage="running"),
        _consumer_timeline_row(
            readable=False, stage="cleanup", stage_status="complete"
        ),
    ]
    result = consumer_checker.recompute_v2_consumer(
        run,
        watchdog,
        manifest,
        manifest_sha256=TASK040_V2_INTERFACE_PACKET_MANIFEST_SHA256,
        run_summary_sha256="f" * 64,
        expected_source_sha=run["source_sha"],
        timeline_rows=timeline,
        timeline_sha256="timeline-sha",
    )
    audit = result["legacy_lifecycle_audit"]
    assert result["checks"]["watchdog_raw"] is False
    assert result["checks"]["watchdog"] is True
    assert result["resource_pass"] is True
    assert result["classification"] == "THREE_GROUP_MODE_SUBSPACE_OR_SWEEP_INSUFFICIENT"
    assert audit["raw_summary_all_status_readable"] is False
    assert audit["raw_summary_swap_authority_readable"] is False
    assert audit["excluded_terminal_teardown_count"] == 1
    assert audit["authoritative_sample_count"] == 2
    assert audit["derived_all_status_readable"] is True
    assert audit["derived_swap_authority_readable"] is True
    assert audit["derived_peak_rss_bytes"] == 1
    assert audit["timeline_sha256"] == "timeline-sha"
    assert audit["timeline_hash_bound"] is True
    assert audit["count_binding_pass"] is True


@pytest.mark.parametrize("case", ("hash_mismatch", "nonterminal"))
def test_v2_consumer_checker_rejects_malformed_teardown_timeline(case: str) -> None:
    run, watchdog, manifest = _consumer_run_fixture()
    watchdog["all_status_readable"] = False
    watchdog["swap_authority_readable"] = False
    if case == "hash_mismatch":
        watchdog["artifact_hashes"] = {
            "process_tree_samples.jsonl": "different-timeline"
        }
        timeline = [
            _consumer_timeline_row(readable=True, stage="running"),
            _consumer_timeline_row(readable=True, stage="running"),
            _consumer_timeline_row(
                readable=False, stage="cleanup", stage_status="complete"
            ),
        ]
    elif case == "nonterminal":
        watchdog["artifact_hashes"] = {"process_tree_samples.jsonl": "bad-timeline"}
        timeline = [
            _consumer_timeline_row(readable=True, stage="running"),
            _consumer_timeline_row(readable=False, stage="running"),
        ]
    else:
        raise AssertionError(case)
    result = consumer_checker.recompute_v2_consumer(
        run,
        watchdog,
        manifest,
        manifest_sha256=TASK040_V2_INTERFACE_PACKET_MANIFEST_SHA256,
        run_summary_sha256="f" * 64,
        expected_source_sha=run["source_sha"],
        timeline_rows=timeline,
        timeline_sha256="bad-timeline",
    )
    assert result["checks"]["watchdog"] is False
    assert result["resource_pass"] is False
    assert result["legacy_lifecycle_audit"]["pass"] is False
    if case == "hash_mismatch":
        assert result["legacy_lifecycle_audit"]["timeline_hash_bound"] is False
