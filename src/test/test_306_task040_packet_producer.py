"""Focused Task040 V2-A1 producer route and packet checker contracts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from mpi4py import MPI

from benchmarks import check_task040_v1_run_b as v1_checker
from benchmarks.check_task040_v2_packet import check_v2_packet
from benchmarks.task040_level_a import (
    TASK040_LEVEL_A_HARD_STOP_BYTES,
    _worker_current_resource,
)
from benchmarks.task040_level_a_watchdog import (
    TASK040_V2_INTERFACE_PACKET_PRODUCER_FLAG,
    build_task040_level_a_watchdog_plan,
)
from src.solvers.hybrid_interface_packet import (
    PacketGroup,
    canonical_key_json,
    finalize_manifest,
    write_group_shard,
)


PRODUCER_FLAG = TASK040_V2_INTERFACE_PACKET_PRODUCER_FLAG


def _partition(global_count: int, size: int, rank: int) -> tuple[int, int]:
    base, remainder = divmod(global_count, size)
    first = rank * base + min(rank, remainder)
    return first, first + base + int(rank < remainder)


def _keys(group: int, count: int) -> tuple[str, ...]:
    return tuple(
        canonical_key_json(
            {
                "role": "active_trace",
                "entity_dimension": 1,
                "physical_entity": {"group": group, "entity": index},
                "entity_local_basis_index": 0,
                "orientation_state": "canonical",
                "floquet_master": None,
                "floquet_coefficient": [1.0, 0.0],
            }
        )
        for index in range(count)
    )


def _pair(value: float) -> list[float]:
    return [float(value), 0.0]


def _contractions() -> dict[str, list[float]]:
    return {
        "source_h_source": _pair(1.0),
        "scalar_h_scalar": _pair(1.0),
        "exact_h_exact": _pair(1.0),
        "scalar_h_exact": _pair(0.5),
        "projected_h_projected": _pair(1.0),
        "projected_h_exact": _pair(0.5),
    }


def _physical_report(label: str, group: int) -> dict[str, object]:
    return {
        "label": label,
        "group": group,
        "kind": "physical",
        "exact_norm": 1.0,
        "scalar_norm": 1.0,
        "projected_norm": 1.0,
        "scalar_exact_relative": 1.0,
        "projected_exact_relative": 1.0,
        "contractions": _contractions(),
    }


def _interface_report(
    interface: str, kind: str, seed: int, group: int
) -> dict[str, object]:
    report: dict[str, object] = {
        "label": f"{interface}_{kind}_{seed}",
        "interface": 0 if interface == "lower" else 1,
        "group": group,
        "kind": kind,
        "seed": seed,
        "finite": True,
        "contractions": _contractions(),
    }
    if kind == "complement":
        report["YH_before_projection"] = [_pair(1.0), _pair(0.0)]
        report["YH_after_projection"] = [_pair(0.0), _pair(0.0)]
    return report


def _middle_identity() -> dict[str, dict[str, object]]:
    result = {}
    for interface, rows in (
        ("lower", (41, 7)),
        ("upper", (5, 91)),
    ):
        result[interface] = {
            "global_rows": list(rows),
            "size": len(rows),
            "sha256": hashlib.sha256(
                np.asarray(rows, dtype=np.int64).tobytes()
            ).hexdigest(),
        }
    return result


def _middle_report(interface: str, seed: int) -> dict[str, object]:
    identity = _middle_identity()[interface]
    kind = "modal_combination" if seed < 3000 else "complement"
    report: dict[str, object] = {
        "label": f"middle_{interface}_{kind}_{seed}",
        "interface": interface,
        "group": 1,
        "source_group": 1,
        "kind": kind,
        "seed": seed,
        "response": "middle_group1_schur",
        "direction": "apply_group",
        "source_norm": 1.0,
        "middle_norm": 1.0,
        "same_interface_norm": 0.8,
        "cross_interface_norm": 0.6,
        "total_norm": 1.0,
        "cross_to_total": 0.6,
        "finite": True,
        "partition_disjoint": True,
        "partition_complete": True,
        "contractions": {
            "source_h_source": _pair(1.0),
            "middle_h_middle": _pair(1.0),
            "source_h_middle": _pair(0.25),
        },
    }
    if kind == "complement":
        row_index = seed % int(identity["size"])
        report.update(
            {
                "selected_active_row": identity["global_rows"][row_index],
                "interface_row_index": row_index,
                "interface_size": identity["size"],
                "interface_rows_global_order_sha256": identity["sha256"],
            }
        )
    return report


def _frozen_identity() -> dict[str, object]:
    manifest = json.loads(v1_checker.PROBE_MANIFEST.read_text(encoding="utf-8"))
    identity = manifest["identity"]
    return {
        "probe_manifest_sha256": v1_checker.FROZEN_PROBE_MANIFEST_SHA256,
        "input_sha256": identity["input_sha256"],
        "physical_model_sha256": identity["physical_model_sha256"],
        "selected_manifest_sha256": identity["selected_manifest_sha256"],
        "selected_identity_sha256": identity["selected_identity_sha256"],
        "selected_selection_sha256": identity["selected_selection_sha256"],
        "selected_identity_physical_sha256": identity["physical_model_sha256"],
        "resolved_config_sha256": identity["exact_spool_resolved_config_sha256"],
        "spool_catalog_sha256": identity["exact_spool_catalog_sha256"],
        "upper_mode_key_sha256": (
            "089d6abfac9f482e7f6001988b9d1c12b1721c09a86749cdefcbfc4f22e82673"
        ),
        "upper_beta_sha256": (
            "aee266f602bf704ffbc3d7551be661b05e1663f84205012bfe26c8fd5983f6c9"
        ),
        "lower_mode_key_sha256": (
            "046afb0b3d3531f728dc958c1b0c8a321ffa51fb8a0e6ecf6834d462d5ab37e5"
        ),
        "lower_resolved_mode_metadata_sha256": (
            v1_checker.FROZEN_LOWER_RESOLVED_MODE_METADATA_SHA256
        ),
        "lower_legacy_beta_metadata_sha256": (
            "a58a3c6bc335bb5ae7f6b929a7abce4c193dedb27b115f17304091afb353318c"
        ),
        "exact_output_identity_sha256": dict(
            manifest["physical_probes"]["exact_output_identity_sha256"]
        ),
    }


def _diagnostics() -> dict[str, object]:
    manifest = json.loads(v1_checker.PROBE_MANIFEST.read_text(encoding="utf-8"))
    identity = _frozen_identity()
    labels = manifest["physical_probes"]["labels"]
    physical = [
        _physical_report(label, group) for label in labels for group in range(3)
    ]
    seeds = manifest["fixed_probe_seeds"]
    interface_reports = [
        _interface_report(interface_name, kind, seed, group)
        for interface_name, group, modal_seeds, complement_seeds in (
            (
                "lower",
                0,
                seeds["modal_combinations"]["lower"],
                seeds["complements"]["lower"],
            ),
            (
                "upper",
                2,
                seeds["modal_combinations"]["upper"],
                seeds["complements"]["upper"],
            ),
        )
        for kind, seeds in (
            ("modal_combination", modal_seeds),
            ("complement", complement_seeds),
        )
        for seed in seeds
    ]
    middle = [
        _middle_report(interface_name, seed)
        for interface_name, seeds in (
            (
                "lower",
                (*seeds["modal_combinations"]["lower"], *seeds["complements"]["lower"]),
            ),
            (
                "upper",
                (*seeds["modal_combinations"]["upper"], *seeds["complements"]["upper"]),
            ),
        )
        for seed in seeds
    ]
    middle_identity = _middle_identity()
    groups = []
    global_counts = (2, 4, 2)
    for group, span in enumerate((1, 1, 1)):
        interface_name = "lower" if group == 0 else "upper" if group == 2 else None
        gamma_layout = {
            "basis_global_replicated": False,
            "fe_numeric_allgather": False,
            "global_row_count": global_counts[group],
        }
        if interface_name is not None:
            gamma_layout.update(
                {
                    "global_size": middle_identity[interface_name]["size"],
                    "gamma_rows_global_order_sha256": middle_identity[interface_name][
                        "sha256"
                    ],
                }
            )
        groups.append({"group": group, "span_size": span, "gamma_layout": gamma_layout})
    return {
        "group_order": ["group0", "group1", "group2"],
        "basis_global_replicated": False,
        "fe_numeric_allgather": False,
        "probe_manifest_sha256": identity["probe_manifest_sha256"],
        "identity_observed": identity,
        "input_sha256": identity["input_sha256"],
        "physical_model_sha256": identity["physical_model_sha256"],
        "selected_manifest_sha256": identity["selected_manifest_sha256"],
        "exact_output_identity_sha256": identity["exact_output_identity_sha256"],
        "lower": {
            "mode_count": 296,
            "mode_key_sha256": identity["lower_mode_key_sha256"],
            "legacy_beta_metadata_sha256": identity[
                "lower_legacy_beta_metadata_sha256"
            ],
            "resolved_mode_metadata_sha256": identity[
                "lower_resolved_mode_metadata_sha256"
            ],
        },
        "upper": {
            "mode_count": 480,
            "mode_key_sha256": identity["upper_mode_key_sha256"],
            "beta_sha256": identity["upper_beta_sha256"],
            "branch_authority": "positive/forward",
            "qep_calls": 0,
        },
        "groups": groups,
        "physical_probe_reports": physical,
        "interface_probe_reports": interface_reports,
        "probes": physical + interface_reports,
        "incoming_neighbor_map": {
            "map": "block_diagonal_neighbor_transmission",
            "response": "apply_directed_neighbor",
            "probe_count": 8,
        },
        "middle_cross_interface_sampled_response": middle,
        "middle_cross_interface_identity": middle_identity,
        "projected_matrix_names": {
            f"group{group}": {
                "gram": f"gram_group{group}",
                "scalar": f"projected_scalar_group{group}",
                "exact": f"projected_exact_group{group}",
            }
            for group in range(3)
        },
        "factor_lifecycle": {
            "factor_count_ready": 3,
            "factor_count_after_cleanup": 0,
            "simultaneous_factor_count_max": 3,
            "exact_oracle_ready": {
                "factor_count_ready": 3,
                "dense_materialization": False,
            },
            "exact_oracle_after_cleanup": {"destroyed": True},
        },
    }


def _write_fixture(
    root: Path,
    comm: MPI.Intracomm,
    *,
    duplicate: bool = False,
    diagnostics: dict[str, object] | None = None,
) -> dict[str, str]:
    counts = (2, 4, 2)
    descriptors = []
    for group, count in enumerate(counts):
        first, last = _partition(count, comm.size, comm.rank)
        keys = list(_keys(group, count)[first:last])
        if duplicate and comm.rank > 0 and keys:
            keys[0] = _keys(group, count)[0]
        values_u = np.empty((len(keys), 1), dtype=np.complex128)
        values_v = np.empty_like(values_u)
        values_u[:, 0] = 1.0 + 0.1j * (comm.rank + 1)
        values_v[:, 0] = 0.5 - 0.2j * (comm.rank + 1)
        descriptors.append(
            write_group_shard(
                root,
                PacketGroup(f"group{group}", tuple(keys), values_u, values_v),
                comm=comm,
                ownership_range=(first, last),
            )
        )
    identity = _frozen_identity()
    provenance = {
        "schema": "task040.v2.interface_packet_producer.v1",
        "source_sha": "a" * 40,
        "input_sha256": identity["input_sha256"],
        "physical_model_sha256": identity["physical_model_sha256"],
        "selected_manifest_sha256": identity["selected_manifest_sha256"],
        "exact_spool_catalog_sha256": identity["spool_catalog_sha256"],
        "probe_manifest_sha256": identity["probe_manifest_sha256"],
        "qep_calls": 0,
        "pde_solve": "not_run",
        "v1_3_built": False,
    }
    matrices = {
        name: np.eye(1, dtype=np.complex128) * scale
        for group in range(3)
        for name, scale in (
            (f"gram_group{group}", 1.0),
            (f"projected_scalar_group{group}", 2.0),
            (f"projected_exact_group{group}", 3.0),
        )
    }
    finalize_manifest(
        root,
        descriptors,
        provenance=provenance,
        group_names=("group0", "group1", "group2"),
        expected_group_counts={
            f"group{group}": count for group, count in enumerate(counts)
        },
        small_matrices=matrices if comm.rank == 0 else None,
        diagnostics=_diagnostics() if diagnostics is None else diagnostics,
        comm=comm,
    )
    return provenance


def _shared_root(tmp_path: Path, comm: MPI.Intracomm, name: str) -> Path:
    root = Path(comm.bcast(str(tmp_path / name), root=0))
    if comm.rank == 0:
        root.mkdir(parents=True, exist_ok=True)
    comm.barrier()
    return root


def _write_watchdog_summary(packet_root: Path, provenance: dict[str, object]) -> Path:
    run_root = packet_root.parents[1]
    worker_root = run_root / "worker"
    worker_root.mkdir(parents=True, exist_ok=True)
    worker_summary = worker_root / "run_summary.json"
    worker_summary.write_text(
        json.dumps({"source_sha": provenance["source_sha"]}), encoding="utf-8"
    )
    worker_hash = hashlib.sha256(worker_summary.read_bytes()).hexdigest()
    summary = {
        "method": "task040_v2_interface_packet_producer",
        "source_sha": provenance["source_sha"],
        "hard_stop_bytes": 55 * 2**30,
        "termination_reason": "natural_exit",
        "return_code": 0,
        "run_summary_present": True,
        "run_summary_sha256": worker_hash,
        "preferred_memory_bytes": 45 * 2**30,
        "all_status_readable": True,
        "swap_authority_readable": True,
        "peak_rss_bytes": 44 * 2**30,
        "peak_swap_bytes": 0,
        "peak_dedicated_cgroup_swap_bytes": 0,
    }
    summary_path = run_root / "watchdog_summary.json"
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    return summary_path


@pytest.fixture(autouse=True)
def _small_v1_span(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(v1_checker, "EXPECTED_SPAN_SIZES", (1, 1, 1))


def test_task040_v2_producer_plan_is_opt_in_and_route_specific(tmp_path: Path):
    legacy = build_task040_level_a_watchdog_plan(
        input_path=tmp_path / "legacy_input.dat",
        exact_spool_root=tmp_path / "legacy_spool",
        run_directory=tmp_path / "legacy_run",
        source_sha="a" * 40,
    )
    producer = build_task040_level_a_watchdog_plan(
        input_path=tmp_path / "producer_input.dat",
        exact_spool_root=tmp_path / "producer_spool",
        run_directory=tmp_path / "producer_run",
        source_sha="b" * 40,
        packet_producer=True,
    )
    assert "preferred_memory_bytes" not in legacy
    assert "preferred_memory_bytes" not in legacy["watchdog"]
    assert legacy["absolute_terminate_memory_bytes"] == TASK040_LEVEL_A_HARD_STOP_BYTES
    assert producer["packet_producer"] is True
    assert producer["absolute_terminate_memory_bytes"] == 55 * 2**30
    assert producer["preferred_memory_bytes"] == 45 * 2**30
    assert producer["watchdog"]["absolute_terminate_memory_bytes"] == 55 * 2**30
    assert producer["watchdog"]["preferred_memory_bytes"] == 45 * 2**30
    assert producer["worker_run_directory"].endswith("producer_run/worker")
    assert producer["packet_root"].endswith("producer_run/worker/interface_packet")
    assert producer["worker_argv"].count(PRODUCER_FLAG) == 1
    assert producer["pde_solve"] == "not_run"
    assert producer["qep_calls"] == 0
    assert producer["v1_3_conditional"] is False
    assert {
        "v1_3_projected_transmission",
        "fgmres",
        "qep",
        "pde_solve",
    }.issubset(producer["forbidden"])
    with pytest.raises(ValueError, match="mutually exclusive"):
        build_task040_level_a_watchdog_plan(
            input_path=tmp_path / "bad_input.dat",
            exact_spool_root=tmp_path / "bad_spool",
            run_directory=tmp_path / "bad_run",
            source_sha="c" * 40,
            interface_schur=True,
            packet_producer=True,
        )


def test_task040_v2_packet_checker_recomputes_shards_and_reports(tmp_path: Path):
    comm = MPI.COMM_WORLD
    root = _shared_root(tmp_path, comm, "valid_run/worker/interface_packet")
    provenance = _write_fixture(root, comm)
    watchdog_summary = None
    if comm.rank == 0:
        watchdog_summary = _write_watchdog_summary(root, provenance)
    watchdog_summary = comm.bcast(watchdog_summary, root=0)
    result = None
    if comm.rank == 0:
        result = check_v2_packet(
            root,
            expected_provenance=provenance,
            expected_group_counts=(2, 4, 2),
            expected_rank_count=comm.size,
            expected_span_sizes=(1, 1, 1),
            watchdog_summary_path=watchdog_summary,
        )
    result = comm.bcast(result, root=0)
    assert result["packet_complete"] is True
    assert result["checks"]["probe_reports"] is True
    assert result["checks"]["factor_lifecycle"] is True
    assert result["watchdog"]["preferred_class"] == "preferred_le_45_gib"
    if comm.rank == 0:
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["group_order"] == ["group0", "group1", "group2"]
        assert manifest["groups"]["group1"]["global_count"] == 4
        assert "global_keys" not in manifest["groups"]["group1"]
        assert manifest["numeric_allgather"] is False

        lifecycle_tampered = json.loads(
            (root / "manifest.json").read_text(encoding="utf-8")
        )
        lifecycle_tampered["diagnostics"]["factor_lifecycle"]["exact_oracle_ready"][
            "dense_materialization"
        ] = True
        (root / "manifest.json").write_text(
            json.dumps(lifecycle_tampered), encoding="utf-8"
        )
        dense_tampered = check_v2_packet(
            root,
            expected_provenance=provenance,
            expected_group_counts=(2, 4, 2),
            expected_rank_count=comm.size,
            expected_span_sizes=(1, 1, 1),
            watchdog_summary_path=watchdog_summary,
        )
        assert dense_tampered["packet_complete"] is False
        assert dense_tampered["checks"]["factor_lifecycle"] is False
        lifecycle_tampered["diagnostics"]["factor_lifecycle"]["exact_oracle_ready"][
            "dense_materialization"
        ] = False
        (root / "manifest.json").write_text(
            json.dumps(lifecycle_tampered), encoding="utf-8"
        )

        watchdog = json.loads(Path(watchdog_summary).read_text(encoding="utf-8"))
        watchdog["preferred_memory_bytes"] = 44 * 2**30
        Path(watchdog_summary).write_text(json.dumps(watchdog), encoding="utf-8")
        preferred_tampered = check_v2_packet(
            root,
            expected_provenance=provenance,
            expected_group_counts=(2, 4, 2),
            expected_rank_count=comm.size,
            expected_span_sizes=(1, 1, 1),
            watchdog_summary_path=watchdog_summary,
        )
        assert preferred_tampered["packet_complete"] is False
        assert preferred_tampered["checks"]["watchdog"] is False
        watchdog["preferred_memory_bytes"] = 45 * 2**30
        watchdog["peak_rss_bytes"] = 55 * 2**30
        Path(watchdog_summary).write_text(json.dumps(watchdog), encoding="utf-8")
        hard_stop_tampered = check_v2_packet(
            root,
            expected_provenance=provenance,
            expected_group_counts=(2, 4, 2),
            expected_rank_count=comm.size,
            expected_span_sizes=(1, 1, 1),
            watchdog_summary_path=watchdog_summary,
        )
        assert hard_stop_tampered["packet_complete"] is False
        assert hard_stop_tampered["watchdog"]["preferred_class"] == (
            "hard_stop_or_invalid"
        )
        watchdog["peak_rss_bytes"] = 44 * 2**30
        watchdog["termination_reason"] = "absolute_memory_limit"
        Path(watchdog_summary).write_text(json.dumps(watchdog), encoding="utf-8")
        tampered = check_v2_packet(
            root,
            expected_provenance=provenance,
            expected_group_counts=(2, 4, 2),
            expected_rank_count=comm.size,
            expected_span_sizes=(1, 1, 1),
            watchdog_summary_path=watchdog_summary,
        )
        assert tampered["packet_complete"] is False
        assert tampered["checks"]["watchdog"] is False

        watchdog["termination_reason"] = "natural_exit"
        watchdog["source_sha"] = "c" * 40
        Path(watchdog_summary).write_text(json.dumps(watchdog), encoding="utf-8")
        source_tampered = check_v2_packet(
            root,
            expected_provenance=provenance,
            expected_group_counts=(2, 4, 2),
            expected_rank_count=comm.size,
            expected_span_sizes=(1, 1, 1),
            watchdog_summary_path=watchdog_summary,
        )
        assert source_tampered["packet_complete"] is False
        assert source_tampered["checks"]["watchdog"] is False


def test_task040_v2_checker_rejects_duplicate_and_missing_shard(tmp_path: Path):
    comm = MPI.COMM_WORLD
    duplicate_root = _shared_root(tmp_path, comm, "duplicate_packet")
    _write_fixture(duplicate_root, comm, duplicate=comm.size > 1)
    duplicate_error = None
    if comm.rank == 0 and comm.size > 1:
        try:
            check_v2_packet(
                duplicate_root,
                expected_group_counts=(2, 4, 2),
                expected_rank_count=comm.size,
                expected_span_sizes=(1, 1, 1),
            )
        except ValueError as exc:
            duplicate_error = str(exc)
    duplicate_error = comm.bcast(duplicate_error, root=0)
    if comm.size > 1:
        assert duplicate_error is not None
        assert "duplicate" in duplicate_error

    count_root = _shared_root(tmp_path, comm, "count_packet")
    _write_fixture(count_root, comm)
    count_error = None
    if comm.rank == 0:
        manifest = json.loads(
            (count_root / "manifest.json").read_text(encoding="utf-8")
        )
        manifest["diagnostics"]["groups"][0]["gamma_layout"]["global_row_count"] = 99
        (count_root / "manifest.json").write_text(
            json.dumps(manifest, sort_keys=True), encoding="utf-8"
        )
        try:
            check_v2_packet(
                count_root,
                expected_group_counts=(2, 4, 2),
                expected_rank_count=comm.size,
                expected_span_sizes=(1, 1, 1),
            )
        except ValueError as exc:
            count_error = str(exc)
    count_error = comm.bcast(count_error, root=0)
    assert count_error is not None

    range_root = _shared_root(tmp_path, comm, "range_packet")
    _write_fixture(range_root, comm)
    range_error = None
    if comm.rank == 0:
        manifest = json.loads(
            (range_root / "manifest.json").read_text(encoding="utf-8")
        )
        record = manifest["groups"]["group0"]["shards"][0]
        record["ownership_range"][0] += 1
        (range_root / "manifest.json").write_text(
            json.dumps(manifest, sort_keys=True), encoding="utf-8"
        )
        try:
            check_v2_packet(
                range_root,
                expected_group_counts=(2, 4, 2),
                expected_rank_count=comm.size,
                expected_span_sizes=(1, 1, 1),
            )
        except ValueError as exc:
            range_error = str(exc)
    range_error = comm.bcast(range_error, root=0)
    assert range_error is not None

    evidence_root = _shared_root(tmp_path, comm, "missing_evidence_packet")
    missing_evidence = _diagnostics()
    del missing_evidence["physical_probe_reports"]
    _write_fixture(evidence_root, comm, diagnostics=missing_evidence)
    evidence_error = None
    if comm.rank == 0:
        try:
            check_v2_packet(
                evidence_root,
                expected_group_counts=(2, 4, 2),
                expected_rank_count=comm.size,
                expected_span_sizes=(1, 1, 1),
            )
        except ValueError as exc:
            evidence_error = str(exc)
    evidence_error = comm.bcast(evidence_error, root=0)
    assert evidence_error is not None

    valid_root = _shared_root(tmp_path, comm, "missing_packet")
    _write_fixture(valid_root, comm)
    if comm.rank == 0:
        manifest = json.loads(
            (valid_root / "manifest.json").read_text(encoding="utf-8")
        )
        shard = manifest["groups"]["group0"]["shards"][0]
        (valid_root / shard["path"]).unlink()
    comm.barrier()
    missing_error = None
    if comm.rank == 0:
        try:
            check_v2_packet(
                valid_root,
                expected_group_counts=(2, 4, 2),
                expected_rank_count=comm.size,
                expected_span_sizes=(1, 1, 1),
            )
        except (FileNotFoundError, ValueError) as exc:
            missing_error = str(exc)
    missing_error = comm.bcast(missing_error, root=0)
    assert missing_error is not None


def test_task040_v2_checker_rejects_identity_seed_and_provenance_tamper(
    tmp_path: Path,
):
    comm = MPI.COMM_WORLD
    tamper_cases = (
        ("identity", "diagnostics.identity_observed.input_sha256"),
        ("seed", "diagnostics.probes.interface_seed"),
        ("provenance", "provenance.source_sha"),
    )
    for name, _description in tamper_cases:
        root = _shared_root(tmp_path, comm, f"tamper_{name}")
        provenance = _write_fixture(root, comm)
        error = None
        if comm.rank == 0:
            manifest_path = root / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if name == "identity":
                manifest["diagnostics"]["identity_observed"]["input_sha256"] = "0" * 64
            elif name == "seed":
                manifest["diagnostics"]["probes"][15]["seed"] += 1
            else:
                manifest["provenance"]["source_sha"] = "b" * 40
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            try:
                check_v2_packet(
                    root,
                    expected_provenance=provenance,
                    expected_group_counts=(2, 4, 2),
                    expected_rank_count=comm.size,
                    expected_span_sizes=(1, 1, 1),
                )
            except (FileNotFoundError, ValueError) as exc:
                error = str(exc)
        error = comm.bcast(error, root=0)
        assert error is not None


def test_task040_v2_checker_rejects_nonfinite_physical_contraction(tmp_path: Path):
    comm = MPI.COMM_WORLD
    root = _shared_root(tmp_path, comm, "nonfinite_physical")
    _write_fixture(root, comm)
    error = None
    if comm.rank == 0:
        manifest_path = root / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["diagnostics"]["physical_probe_reports"][0]["contractions"][
            "exact_h_exact"
        ] = [float("nan"), 0.0]
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        try:
            check_v2_packet(
                root,
                expected_group_counts=(2, 4, 2),
                expected_rank_count=comm.size,
                expected_span_sizes=(1, 1, 1),
            )
        except ValueError as exc:
            error = str(exc)
    error = comm.bcast(error, root=0)
    assert error is not None


def test_task040_v2_resource_authority_keeps_legacy_45_and_producer_55(
    monkeypatch: pytest.MonkeyPatch,
):
    from benchmarks import task040_level_a as worker

    cgroup_memory = 50 * 2**30
    monkeypatch.setattr(
        worker,
        "resource_authority_sample",
        lambda *_args, **_kwargs: {
            "process_tree": {
                "rss_bytes": 1024,
                "swap_bytes": 0,
                "all_status_readable": True,
            },
            "job_cgroup": {
                "dedicated_job_cgroup": True,
                "memory_current_bytes": cgroup_memory,
                "swap_current_bytes": 0,
            },
        },
    )
    legacy = _worker_current_resource(MPI.COMM_WORLD)
    producer = _worker_current_resource(MPI.COMM_WORLD, hard_limit_bytes=55 * 2**30)
    assert legacy["hard_limit_bytes"] == 45 * 2**30
    assert legacy["pass"] is False
    assert producer["hard_limit_bytes"] == 55 * 2**30
    assert producer["pass"] is True
