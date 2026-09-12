"""Small raw-writer fixtures for the Task041 BAL_H comparison contract."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

from benchmarks.canonical_vector_artifacts import (
    MANIFEST_SCHEMA,
    canonical_shard_manifest,
    write_canonical_manifest,
    write_canonical_packet_shard,
)
from benchmarks.run_task037b_hybrid_iterative import _write_frozen_m10_grid_payload
from benchmarks.task039_v3_7_orchestration import _write_v3_7_candidate_authority
from benchmarks.task041_balh_workflow import (
    build_task041_balh_packet_identity,
    task041_balh_time_stop_override_record,
)
from benchmarks.task041_exact_side_workflow import _inventory_from_payload
from benchmarks.task041_legacy_native_packet import (
    TASK039_V4_H4_EXTERNAL_SHA256,
    TASK039_V4_H4_IDENTITY_SCHEMA,
    TASK039_V4_H4_INPUT_SHA256,
    TASK039_V4_H4_MODE_COUNT,
    TASK039_V4_H4_MODEL_ID,
    TASK039_V4_H4_PHYSICAL_SHA256,
    TASK039_V4_H4_RUN_ID,
    TASK039_V4_H4_SOURCE_SHA,
    TASK041_LEGACY_NATIVE_PACKET_DESCRIPTOR_SCHEMA,
    TASK041_LEGACY_NATIVE_PACKET_ORIGIN,
    _physical_binding,
)
from benchmarks.task041_side_balh_comparison import (
    Task041ComparisonError,
    _compare_external,
    _compare_selected_fields,
    _own_gates,
    _pair_identity,
    _resources,
    _validate_legacy_consumer_binding,
    compare_task041_side_balh_pair,
    load_task041_side_balh_result,
)
from src.io.execution_plan import TASK041_PUBLIC_SUPERVISOR_ADAPTER
from src.io.input_validation import (
    load_and_resolve,
    task041_balh_phase_limits_for_model,
)
from src.io.resolved_config import resolved_config_sha256, write_resolved_config
from src.modes.selected_mode_packet import _json_bytes, write_selected_mode_packet
from src.runners.task038_launcher import _base_manifest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
EXACT_INPUT = (
    REPOSITORY_ROOT
    / "input/official/task041/side_balh/13p5nm_p6h10_m120_mpi8_exact.dat"
)
CANDIDATE_INPUT = (
    REPOSITORY_ROOT
    / "input/official/task041/side_balh/13p5nm_p6h10_m120_mpi8_balh.dat"
)
LEGACY_NATIVE_INPUT = (
    REPOSITORY_ROOT
    / "input/official/task041/side_balh/5nm_p6h4_m480_mpi8_exact.dat"
)
PUBLIC_SCOPE = "public_launcher_and_all_descendants"
POST_ROLE = "phase_end_public_root"


def _specification(path: Path):
    return load_and_resolve(path)


def _packet_fixture(tmp_path: Path, identity: dict[str, object]) -> tuple[Path, Path]:
    mode_count = int(identity["mode_count"])
    vectors: list[PETSc.Vec] = []
    bases: dict[str, SimpleNamespace] = {}
    for branch, sign in (("positive", 1), ("negative", -1)):
        modes = []
        for index in range(mode_count):
            right = PETSc.Vec().createMPI((1, 1), comm=PETSc.COMM_SELF)
            left = PETSc.Vec().createMPI((1, 1), comm=PETSc.COMM_SELF)
            right.getArray()[:] = np.asarray(
                [sign * (index + 1)], dtype=np.complex128
            )
            left.getArray()[:] = np.asarray(
                [sign * (index + 2)], dtype=np.complex128
            )
            vectors.extend((right, left))
            modes.append(
                SimpleNamespace(
                    beta=complex(sign * (index + 1), 0.25),
                    direction="down" if sign > 0 else "up",
                    kind="external",
                    passive_branch_valid=True,
                    right=SimpleNamespace(right_full=right),
                    left_full=left,
                )
            )
        bases[branch] = SimpleNamespace(
            modes=modes,
            groups=[SimpleNamespace(indices=tuple(range(mode_count)))],
        )
    metadata = {
        "trace_mapping": {},
        "canonical_mapping": {},
        "gram_authority": {"fixture": True},
        "qep_diagnostics": {"fixture": True},
        "selection_diagnostics": {"fixture": True},
    }
    packet_dir = tmp_path / "selected_packet"
    try:
        packet = write_selected_mode_packet(
            packet_dir,
            bases,
            identity=identity,
            metadata=metadata,
            scope=str(identity["scope"]),
            comm=MPI.COMM_SELF,
        )
    finally:
        for vector in vectors:
            vector.destroy()
    identity_path = packet_dir / "identity.json"
    identity_path.write_bytes(_json_bytes(identity) + b"\n")
    return Path(packet["manifest"]), identity_path


def _canonical_fixture(tmp_path: Path) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {
        side: {"roles": {}} for side in ("bottom", "top")
    }
    for side in ("bottom", "top"):
        for role in ("active_trace", "full_fe"):
            manifest_role = f"{side}_{role}"
            role_dir = tmp_path / "canonical" / manifest_role
            role_dir.mkdir(parents=True, exist_ok=True)
            shards = []
            for rank in range(8):
                shard_path = role_dir / f"rank{rank:04d}.jsonl"
                packets = (
                    [((manifest_role, 0), 1.0 + 0.0j)] if rank == 0 else []
                )
                metadata = write_canonical_packet_shard(
                    shard_path, packets, audit_packets=True
                )
                metadata["rank"] = rank
                shards.append(metadata)
            manifest = canonical_shard_manifest(
                role=manifest_role,
                mpi_size=8,
                shard_metadata=shards,
                extractor_audit={"fixture": True},
            )
            manifest_path = role_dir / "manifest.json"
            manifest_sha = write_canonical_manifest(manifest_path, manifest)
            result[side]["roles"][role] = {
                "schema_version": MANIFEST_SCHEMA,
                "manifest": str(manifest_path),
                "manifest_sha256": manifest_sha,
                "pass": True,
            }
    return result


def _external_orders(normalized: dict[str, object]) -> list[dict[str, object]]:
    keys, _count = _inventory_from_payload(normalized)
    return [
        {
            **dict(key),
            "power_ratio": 1.0e-3,
            "outgoing_amplitude": [1.0, 0.0],
        }
        for key in keys
    ]


def _phase_limits(model_id: str, phase: str) -> dict[str, object]:
    limits = dict(task041_balh_phase_limits_for_model(model_id, phase))
    limits.update(
        {
            "min_cgroup_ancestor_headroom_bytes": limits[
                "min_memavailable_bytes"
            ],
            "cumulative_compute_limit_seconds": 172800.0,
        }
    )
    return limits


def _sample(phase: str, elapsed: float, rss: int, *, post: bool) -> dict[str, object]:
    return {
        "phase": phase,
        "sample_elapsed_seconds": elapsed,
        "sample_role": POST_ROLE if post else "poll",
        "sample_root_scope": PUBLIC_SCOPE,
        "memory_authority_bytes": rss,
        "process_tree_rss_bytes": rss,
        "process_tree_rss_by_pid_bytes": {"1001": rss},
        "process_tree_swap_bytes": 0,
        "dedicated_cgroup_swap_bytes": 0,
        "swap_bytes": 0,
        "job_no_swap": True,
        "host_memavailable_bytes": 500 * 2**30,
        "cgroup_memory_current_bytes": None,
        "cgroup_memory_headroom_bytes": None,
        "cgroup_memory_limit_state": "max_or_unlimited",
        "cgroup_ancestor_memory_headroom_bytes": None,
        "cgroup_ancestor_hard_limit_state": "not_applicable_root",
        "cgroup_ancestor_memory": [],
        "global_swap_used_bytes": 0,
        "global_swap_used_bytes_delta": 0,
        "global_swap_readable": True,
        "global_pswpin_pages": 0,
        "global_pswpin_pages_delta": 0,
        "global_pswpout_pages": 0,
        "global_pswpout_pages_delta": 0,
        "pss_bytes": rss - 10,
        "uss_bytes": rss - 20,
    }


def _measured_phase(
    model_id: str, phase: str, wall: float, rss: int
) -> tuple[dict[str, object], list[dict[str, object]]]:
    samples = [_sample(phase, 0.0, rss, post=False), _sample(phase, wall, rss, post=True)]
    return (
        {
            "phase": phase,
            "reused": False,
            "returncode": 0,
            "termination_reason": None,
            "process_group_gone": True,
            "sample_root_scope": PUBLIC_SCOPE,
            "phase_wall_seconds": wall,
            "limits": _phase_limits(model_id, phase),
            "sampling": {"configured_poll_interval_seconds": 0.25},
            "phase_end_sample": samples[-1],
        },
        samples,
    )


def _write_run(
    root: Path,
    specification,
    method: str,
    consumer_identity: dict[str, object],
    producer_identity: dict[str, object],
    packet: tuple[Path, Path],
    canonical: dict[str, dict[str, object]],
    orders: list[dict[str, object]],
    producer_summary_sha: str | None,
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    consumer_root = root / "consumer"
    consumer_root.mkdir(parents=True, exist_ok=True)
    sample_path = root / "numerical_output" / "log" / "memory_stages.jsonl"
    sample_path.parent.mkdir(parents=True, exist_ok=True)
    write_resolved_config(specification, root / "resolved_config.json")
    (root / "input_original.dat").write_bytes(specification.raw_input_bytes)
    resolved_sha = resolved_config_sha256(specification)
    manifest = _base_manifest(
        specification,
        run_directory=root,
        source_sha=str(consumer_identity["source_sha"]),
        adapter_identity=TASK041_PUBLIC_SUPERVISOR_ADAPTER,
        start_time="fixture",
        resolved_sha=resolved_sha,
    )
    (root / "run_manifest.json").write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )

    normalized = specification.as_jsonable()
    keys, _count = _inventory_from_payload(normalized)
    grid_arrays = {
        "x_nm": np.arange(40, dtype=np.float64),
        "y_nm": np.arange(20, dtype=np.float64),
        "z_nm": np.asarray([10.0, 30.0, 60.0, 90.0, 110.0]),
        "E_V_per_m": np.ones((5, 20, 40, 3), dtype=np.complex128),
        "H_A_per_m": np.ones((5, 20, 40, 3), dtype=np.complex128),
        "modal_amplitudes": np.ones(
            2 * int(consumer_identity["mode_count"]), dtype=np.complex128
        ),
        "bottom_q": np.ones(
            sum(key["side"] == "bottom" for key in keys), dtype=np.complex128
        ),
        "top_q": np.ones(
            sum(key["side"] == "top" for key in keys), dtype=np.complex128
        ),
    }
    grid = _write_frozen_m10_grid_payload(
        root / "numerical_output",
        grid_arrays,
        MPI.COMM_SELF,
        modal_count=2 * int(consumer_identity["mode_count"]),
        bottom_mode_count=grid_arrays["bottom_q"].size,
        top_mode_count=grid_arrays["top_q"].size,
    )
    physics = SimpleNamespace(
        physics_pass=True,
        own_physics_pass=True,
        canonical_pass=True,
        own_grid=grid,
        external_orders=orders,
        interface_e_projection={"combined_relative_residual": 1.0e-10},
        energy={
            "R": 0.2,
            "T": 0.7,
            "A": 0.1,
            "A_volume": 0.1,
            "closure": 0.0,
        },
        traction={
            "bottom": {"relative_dual": 1.0e-10},
            "top": {"relative_dual": 1.0e-10},
        },
        interface_continuity={},
        order_audit={},
        canonical=canonical,
    )
    producer = {
        "consumer_model_id": consumer_identity["model_id"],
        "consumer_source_sha": consumer_identity["source_sha"],
        "physical_model_sha256": producer_identity["physical_sha256"],
        "mpi_size": 8,
        "requested_modes": consumer_identity["mode_count"],
        "qualification_scope": producer_identity["scope"],
        "qualification_method": (
            "task041_balh_side_inverse_response_fgmres32"
            if method == "candidate"
            else "task041_exact_side_full_formal"
        ),
        "canonical_authority": True,
    }
    authority_path = _write_v3_7_candidate_authority(
        root, physics, producer, MPI.COMM_SELF
    )
    packet_manifest, packet_identity = packet
    summary = {
        "schema": (
            "task041.side_balh.candidate_consumer.v1"
            if method == "candidate"
            else "task041.side_balh.exact_consumer.v1"
        ),
        "profile": (
            "task041.side_balh.candidate_consumer.v1"
            if method == "candidate"
            else "task041.side_balh.exact_consumer.v1"
        ),
        "consumer_route": (
            "task041_balh_candidate" if method == "candidate" else "task041_balh_exact"
        ),
        "qualification_status": (
            "research_only_approximate_candidate" if method == "candidate" else "exact_side"
        ),
        "source_sha": consumer_identity["source_sha"],
        "identity": consumer_identity,
        "producer_identity": producer_identity,
        "packet": {
            "manifest": str(packet_manifest),
            "manifest_sha256": hashlib.sha256(packet_manifest.read_bytes()).hexdigest(),
            "identity": str(packet_identity),
            "identity_sha256": hashlib.sha256(_json_bytes(producer_identity)).hexdigest(),
        },
        "authority_path": str(authority_path),
        "formal": {
            "solve": {
                "converged_reason": 1,
                "postsolve": {
                    "reported_relative_residual": 1.0e-10,
                    "global_true_relative_residual": 1.0e-10,
                    "bottom_true_relative_residual": 1.0e-10,
                    "top_true_relative_residual": 1.0e-10,
                    "modal_true_relative_residual": 1.0e-10,
                },
            },
            "recovery": {
                "reports": {
                    "bottom": {
                        "external_q": {"auxiliary_relative_residual": 1.0e-11}
                    },
                    "top": {
                        "external_q": {"auxiliary_relative_residual": 1.0e-11}
                    },
                }
            },
        },
    }
    (consumer_root / "consumer_summary.json").write_text(
        json.dumps(summary, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    phase_rows: list[dict[str, object]] = []
    if method == "exact":
        producer_phase, producer_rows = _measured_phase(
            str(consumer_identity["model_id"]), "producer", 2.0, 900
        )
        consumer_phase, consumer_rows = _measured_phase(
            str(consumer_identity["model_id"]), "consumer", 3.0, 500
        )
        phase_results = {"producer": producer_phase, "consumer": consumer_phase}
        phase_rows.extend(producer_rows)
        phase_rows.extend(consumer_rows)
        used_before, used_after = 10.0, 15.0
        supervisor_wall = 5.0
    else:
        producer_phase = {
            "phase": "producer",
            "reused": True,
            "resource_source": "inherited_exact_public_supervisor_summary",
            "supervisor_summary_sha256": producer_summary_sha,
            "peak_memory_authority_bytes": 900,
            "peak_process_tree_rss_bytes": 900,
            "peak_pss_bytes": 890,
            "peak_uss_bytes": 880,
            "peak_process_tree_swap_bytes": 0,
            "peak_dedicated_cgroup_swap_bytes": 0,
            "peak_swap_bytes": 0,
            "phase_wall_seconds": 2.0,
            "producer_resource_qualified": True,
        }
        consumer_phase, consumer_rows = _measured_phase(
            str(consumer_identity["model_id"]), "consumer", 1.0, 500
        )
        phase_results = {"producer": producer_phase, "consumer": consumer_phase}
        phase_rows.extend(consumer_rows)
        used_before, used_after = 15.0, 16.0
        supervisor_wall = 2.0
    sample_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in phase_rows),
        encoding="utf-8",
    )
    supervisor = {
        "phase_results": phase_results,
        "wall_seconds": supervisor_wall,
        "compute_wall_budget": {
            "used_before_seconds": used_before,
            "used_after_seconds": used_after,
            "remaining_seconds": 172800.0 - used_before,
            "remaining_after_seconds": 172800.0 - used_after,
            "limit_seconds": 172800.0,
            "used_before_status": "measured",
            "used_after_status": "measured",
            "current_invocation_status": "measured",
            "basis": "fixture measured public phase wall",
        },
    }
    (root / "supervisor_summary.json").write_text(
        json.dumps(supervisor, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )


@pytest.fixture
def comparison_pair(tmp_path: Path) -> dict[str, object]:
    exact_spec = _specification(EXACT_INPUT)
    candidate_spec = _specification(CANDIDATE_INPUT)
    producer_identity = build_task041_balh_packet_identity(
        exact_spec,
        exact_spec.as_jsonable(),
        "a" * 40,
        resolved_config_sha256(exact_spec),
    )
    exact_identity = build_task041_balh_packet_identity(
        exact_spec,
        exact_spec.as_jsonable(),
        "c" * 40,
        resolved_config_sha256(exact_spec),
    )
    candidate_identity = build_task041_balh_packet_identity(
        candidate_spec,
        candidate_spec.as_jsonable(),
        "b" * 40,
        resolved_config_sha256(candidate_spec),
    )
    packet = _packet_fixture(tmp_path, producer_identity)
    canonical = _canonical_fixture(tmp_path)
    exact_root = tmp_path / "exact"
    _write_run(
        exact_root,
        exact_spec,
        "exact",
        exact_identity,
        producer_identity,
        packet,
        canonical,
        _external_orders(exact_spec.as_jsonable()),
        None,
    )
    producer_summary_sha = hashlib.sha256(
        (exact_root / "supervisor_summary.json").read_bytes()
    ).hexdigest()
    candidate_root = tmp_path / "candidate"
    _write_run(
        candidate_root,
        candidate_spec,
        "candidate",
        candidate_identity,
        producer_identity,
        packet,
        canonical,
        _external_orders(candidate_spec.as_jsonable()),
        producer_summary_sha,
    )
    return {
        "exact": exact_root,
        "candidate": candidate_root,
        "producer_identity": producer_identity,
        "orders": _external_orders(exact_spec.as_jsonable()),
    }


def test_task041_comparison_real_writer_pair_and_workflow_peak(comparison_pair):
    result = compare_task041_side_balh_pair(
        comparison_pair["candidate"], comparison_pair["exact"]
    )
    assert result["pass"] is True
    assert result["candidate"]["load_pass"] is True
    assert result["exact"]["load_pass"] is True
    workflow = result["common_workflow"]
    assert workflow["workflow_peak"]["candidate"]["process_tree_rss_bytes"] == 900
    assert workflow["workflow_peak"]["exact"]["process_tree_rss_bytes"] == 900
    assert workflow["workflow_peak"]["savings"]["process_tree_rss_bytes"][
        "status"
    ] == "measured_difference"
    assert workflow["workflow_peak"]["savings"]["process_tree_rss_bytes"][
        "credible_saving"
    ] is None
    assert workflow["workflow_wall"]["candidate_supervisor_wall_seconds"] == 2.0
    assert workflow["workflow_wall"]["exact_supervisor_wall_seconds"] == 5.0
    assert workflow["workflow_wall"]["candidate_phase_sum_seconds"] == 1.0
    assert workflow["workflow_wall"]["exact_phase_sum_seconds"] == 5.0


def test_task041_time_override_is_worker_bound_and_keeps_resource_gates(tmp_path):
    model_id = "task041_5nm_balh_hybrid_iterative_p6h4_m480_mpi8"
    source_sha = "b" * 40
    run_id = "task041_5nm_p6h4_m480_mpi8_balh"
    limits = _phase_limits(model_id, "consumer")
    phase, samples = _measured_phase(
        model_id,
        "consumer",
        float(limits["timeout_seconds"]) + 1.0,
        500,
    )
    root = tmp_path / "time_override"
    consumer_root = root / "consumer"
    sample_path = root / "numerical_output" / "log" / "memory_stages.jsonl"
    consumer_root.mkdir(parents=True)
    sample_path.parent.mkdir(parents=True)
    sample_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in samples),
        encoding="utf-8",
    )
    override = task041_balh_time_stop_override_record(True) | {
        "model_id": model_id,
        "run_id": run_id,
        "source_sha": source_sha,
        "origin": "run_case_cli",
    }
    (root / "run_manifest.json").write_text(
        json.dumps(
            {"source_sha": source_sha, "time_stop_override": override},
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    supervisor = {
        "source_sha": source_sha,
        "identity": {"run_id": run_id},
        "time_stop_override": override,
        "phase_results": {
            "producer": {"reused": True, "phase_wall_seconds": 2.0},
            "consumer": phase,
        },
        "wall_seconds": float(limits["timeout_seconds"]) + 1.0,
        "compute_wall_budget": {
            "used_before_seconds": 130000.0,
            "used_after_seconds": 130000.0 + phase["phase_wall_seconds"],
            "remaining_seconds": 42800.0,
            "remaining_after_seconds": 0.0,
            "limit_seconds": 172800.0,
            "used_before_status": "measured",
            "used_after_status": "measured",
            "current_invocation_status": "measured",
            "basis": "fixture",
        },
    }
    (root / "supervisor_summary.json").write_text(
        json.dumps(supervisor, sort_keys=True) + "\n", encoding="utf-8"
    )
    worker_override = dict(override)
    worker_override["origin"] = "public_worker_cli"
    (consumer_root / "consumer_summary.json").write_text(
        json.dumps(
            {"source_sha": source_sha, "time_stop_override": worker_override},
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    resources = _resources(root, "candidate", model_id)
    assert resources["time_stop_override"]["status"] == "valid"
    assert resources["phases"]["consumer"]["phase_wall_pass"] is True
    assert resources["batch_compute_wall"]["pass"] is True
    assert resources["pass"] is True

    worker_summary_path = consumer_root / "consumer_summary.json"
    worker_summary_path.write_text(
        json.dumps({"source_sha": source_sha}, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    missing_worker = _resources(root, "candidate", model_id)
    assert missing_worker["time_stop_override"]["status"] == "invalid"
    assert missing_worker["phases"]["consumer"]["phase_wall_pass"] is False
    assert missing_worker["pass"] is False

    worker_summary_path.write_text(
        json.dumps(
            {"source_sha": source_sha, "time_stop_override": worker_override},
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    rows = [dict(row) for row in samples]
    rows[0]["memory_authority_bytes"] = limits["hard_memory_bytes"] + 1
    sample_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    memory_failure = _resources(root, "candidate", model_id)
    assert memory_failure["time_stop_override"]["status"] == "valid"
    assert memory_failure["phases"]["consumer"]["hard_cap_pass"] is False
    assert memory_failure["pass"] is False


def test_task041_unqualified_producer_does_not_enter_workflow_peak(comparison_pair):
    supervisor_path = comparison_pair["exact"] / "supervisor_summary.json"
    supervisor = json.loads(supervisor_path.read_text(encoding="utf-8"))
    producer_phase = supervisor["phase_results"]["producer"]
    producer_phase["reused"] = True
    producer_phase["worker_tree"] = {"peak_rss_bytes": 900}
    supervisor["compute_wall_budget"]["used_after_seconds"] = 13.0
    supervisor["compute_wall_budget"]["remaining_after_seconds"] = 172787.0
    supervisor_path.write_text(
        json.dumps(supervisor, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    result = compare_task041_side_balh_pair(
        comparison_pair["candidate"], comparison_pair["exact"]
    )
    assert result["consumer_resource_contract_pass"] is True
    assert result["resource_contract_pass"] is False
    assert result["pass"] is False
    workflow = result["common_workflow"]
    assert workflow["common_producer"]["qualified"] is False
    assert workflow["common_producer"]["peak"]["process_tree_rss_bytes"] is None
    assert workflow["common_producer"]["worker_tree"]["peak_rss_bytes"] == 900
    assert workflow["workflow_peak"]["common_producer_peak"][
        "process_tree_rss_bytes"
    ] is None


def test_task041_legacy_binding_recomputes_raw_resolved_contract(tmp_path: Path):
    specification = _specification(LEGACY_NATIVE_INPUT)
    public_root = tmp_path / "consumer"
    public_root.mkdir()
    public_resolved_path = public_root / "resolved_config.json"
    write_resolved_config(specification, public_resolved_path)
    public_resolved = json.loads(public_resolved_path.read_text(encoding="utf-8"))
    consumer_identity = build_task041_balh_packet_identity(
        specification,
        specification.as_jsonable(),
        "c" * 40,
        resolved_config_sha256(specification),
    )

    legacy_resolved = json.loads(json.dumps(public_resolved))
    legacy_resolved["materials"]["substrate_name"] = "legacy substrate"
    legacy_resolved["materials"]["grating_name"] = "legacy grating"
    legacy_resolved["provenance"]["input_sha256"] = TASK039_V4_H4_INPUT_SHA256
    legacy_resolved["provenance"]["physical_model_sha256"] = (
        TASK039_V4_H4_PHYSICAL_SHA256
    )
    producer_root = tmp_path / "producer"
    producer_root.mkdir()
    legacy_resolved_path = producer_root / "resolved_config.json"
    legacy_resolved_path.write_text(
        json.dumps(legacy_resolved, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    legacy_resolved_sha = hashlib.sha256(legacy_resolved_path.read_bytes()).hexdigest()
    producer_identity = {
        "schema": TASK039_V4_H4_IDENTITY_SCHEMA,
        "scope": "task039_v4_h4_m480",
        "source_sha": TASK039_V4_H4_SOURCE_SHA,
        "input_sha256": TASK039_V4_H4_INPUT_SHA256,
        "resolved_sha256": legacy_resolved_sha,
        "physical_sha256": TASK039_V4_H4_PHYSICAL_SHA256,
        "model_id": TASK039_V4_H4_MODEL_ID,
        "run_id": TASK039_V4_H4_RUN_ID,
        "mode_count": TASK039_V4_H4_MODE_COUNT,
        "mpi_size": 8,
        "external_keys": {
            "count": consumer_identity["external_keys"]["count"],
            "sha256": TASK039_V4_H4_EXTERNAL_SHA256,
        },
    }
    packet_root = tmp_path / "packet"
    packet_root.mkdir()
    manifest_path = packet_root / "manifest.json"
    manifest_path.write_text("{}\n", encoding="utf-8")
    identity_path = packet_root / "identity.json"
    identity_path.write_text(
        json.dumps(producer_identity, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    artifact_names = (
        "run_manifest",
        "run_summary",
        "numeric_summary",
        "resolved_config",
        "input",
        "source_record",
        "input_record",
        "physical_record",
        "process_samples",
    )
    artifact_hashes = {
        "packet_manifest": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "packet_identity": hashlib.sha256(identity_path.read_bytes()).hexdigest(),
        **{name: "0" * 64 for name in artifact_names},
    }
    artifact_hashes["resolved_config"] = legacy_resolved_sha
    descriptor_path = tmp_path / "legacy_descriptor.json"
    descriptor_path.write_text(
        json.dumps(
            {
                "schema": TASK041_LEGACY_NATIVE_PACKET_DESCRIPTOR_SCHEMA,
                "origin": TASK041_LEGACY_NATIVE_PACKET_ORIGIN,
                "packet_root": str(packet_root),
                "identity_path": str(identity_path),
                "producer_root": str(producer_root),
                "artifact_sha256": artifact_hashes,
            },
            sort_keys=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    physical = _physical_binding(legacy_resolved, public_resolved)
    binding = {
        "origin": TASK041_LEGACY_NATIVE_PACKET_ORIGIN,
        "pass": True,
        "producer_identity": producer_identity,
        "consumer_identity": consumer_identity,
        "physical_equivalence": physical,
        "external_keys": {
            "producer": producer_identity["external_keys"],
            "consumer": consumer_identity["external_keys"],
            "pass": True,
        },
        "descriptor": {
            "path": str(descriptor_path),
            "sha256": hashlib.sha256(descriptor_path.read_bytes()).hexdigest(),
        },
    }
    summary = {
        "packet_origin": TASK041_LEGACY_NATIVE_PACKET_ORIGIN,
        "consumer_binding": binding,
    }
    _validate_legacy_consumer_binding(
        summary, consumer_identity, producer_identity, public_root
    )

    legacy_resolved["materials"]["n_grating"][0] += 0.01
    legacy_resolved_path.write_text(
        json.dumps(legacy_resolved, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    legacy_resolved_sha = hashlib.sha256(legacy_resolved_path.read_bytes()).hexdigest()
    producer_identity["resolved_sha256"] = legacy_resolved_sha
    identity_path.write_text(
        json.dumps(producer_identity, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    artifact_hashes["packet_identity"] = hashlib.sha256(
        identity_path.read_bytes()
    ).hexdigest()
    artifact_hashes["resolved_config"] = legacy_resolved_sha
    descriptor_path.write_text(
        json.dumps(
            {
                "schema": TASK041_LEGACY_NATIVE_PACKET_DESCRIPTOR_SCHEMA,
                "origin": TASK041_LEGACY_NATIVE_PACKET_ORIGIN,
                "packet_root": str(packet_root),
                "identity_path": str(identity_path),
                "producer_root": str(producer_root),
                "artifact_sha256": artifact_hashes,
            },
            sort_keys=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    binding["producer_identity"] = producer_identity
    binding["descriptor"]["sha256"] = hashlib.sha256(
        descriptor_path.read_bytes()
    ).hexdigest()
    with pytest.raises(Task041ComparisonError, match="raw resolved contracts"):
        _validate_legacy_consumer_binding(
            summary, consumer_identity, producer_identity, public_root
        )


def _valid_gate_summary() -> dict[str, object]:
    return {
        "formal": {
            "solve": {
                "converged_reason": 1,
                "postsolve": {
                    name: 1.0e-10
                    for name in (
                        "reported_relative_residual",
                        "global_true_relative_residual",
                        "bottom_true_relative_residual",
                        "top_true_relative_residual",
                        "modal_true_relative_residual",
                    )
                },
            },
            "recovery": {
                "reports": {
                    side: {
                        "external_q": {"auxiliary_relative_residual": 1.0e-11}
                    }
                    for side in ("bottom", "top")
                }
            },
        }
    }


@pytest.mark.parametrize("closure", (2.0e-5, -2.0e-5))
def test_task041_own_gate_signed_closure_is_not_ignored(closure):
    authority = {
        "observables": {
            "R_total": 0.2,
            "T_total": 0.7,
            "A_balance": 0.1,
            "A_volume": 0.1 + closure,
        },
        "interface_projection": 1.0e-10,
        "traction": {
            "bottom": {"relative_residual": 1.0e-10},
            "top": {"relative_residual": 1.0e-10},
        },
    }
    authority["pass"] = True
    gates = _own_gates(_valid_gate_summary(), authority)
    assert authority["pass"] is True
    assert gates["closure"] == pytest.approx(closure)
    assert gates["energy_closure_status"] == "numeric_gate_fail"
    assert gates["pass"] is False
    assert gates["failure_classification"] == "numeric_gate_fail"


def test_task041_negative_writer_reports_relative_dual(tmp_path: Path):
    specification = _specification(EXACT_INPUT)
    normalized = specification.as_jsonable()
    producer_identity = build_task041_balh_packet_identity(
        specification,
        normalized,
        "a" * 40,
        resolved_config_sha256(specification),
    )
    orders = _external_orders(normalized)
    physics = SimpleNamespace(
        physics_pass=False,
        own_physics_pass=False,
        canonical_pass=False,
        own_grid=None,
        external_orders=orders,
        interface_e_projection={"combined_relative_residual": 1.0e-10},
        energy={"R": 0.2, "T": 0.7, "A": 0.1, "A_volume": 0.1, "closure": 0.0},
        traction={
            "bottom": {"relative_dual": 2.0e-5},
            "top": {"relative_dual": 1.0e-10},
        },
        interface_continuity={},
        order_audit={},
        canonical={},
    )
    producer = {
        "consumer_model_id": producer_identity["model_id"],
        "consumer_source_sha": producer_identity["source_sha"],
        "physical_model_sha256": producer_identity["physical_sha256"],
        "mpi_size": 8,
        "requested_modes": producer_identity["mode_count"],
        "qualification_scope": producer_identity["scope"],
        "qualification_method": "task041_exact_side_full_formal",
        "canonical_authority": True,
    }
    root = tmp_path / "negative"
    path = _write_v3_7_candidate_authority(root, physics, producer, MPI.COMM_SELF)
    authority = json.loads(path.read_text(encoding="utf-8"))
    gates = _own_gates(_valid_gate_summary(), authority)
    assert authority["status"] == "measured_candidate_physics_negative"
    assert authority["traction"]["bottom"]["relative_dual"] == 2.0e-5
    assert gates["traction_field"] == "relative_dual"
    assert gates["raw_traction"]["bottom"] == 2.0e-5
    assert gates["limits"]["traction"] == 1.0e-8
    assert gates["failure_classification"] == "numeric_gate_fail"


def test_task041_comparison_raw_residual_failure_is_numeric(comparison_pair):
    summary_path = comparison_pair["exact"] / "consumer" / "consumer_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["formal"]["solve"]["postsolve"]["global_true_relative_residual"] = 1.0e-5
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    result = compare_task041_side_balh_pair(
        comparison_pair["candidate"], comparison_pair["exact"]
    )
    assert result["numerical_pass"] is False
    assert result["exact"]["own_gates"]["raw_residuals"][
        "global_true_relative_residual"
    ] == 1.0e-5
    assert result["exact"]["own_gates"]["failure_classification"] == (
        "numeric_gate_fail"
    )


def test_task041_failed_solve_keeps_summary_gates_without_authority(tmp_path: Path):
    root = tmp_path / "missing_authority"
    consumer_root = root / "consumer"
    consumer_root.mkdir(parents=True)
    summary = _valid_gate_summary()
    summary.update(
        {
            "schema": "task041.side_balh.candidate_consumer.v1",
            "profile": "task041.side_balh.candidate_consumer.v1",
            "consumer_route": "task041_balh_candidate",
            "qualification_status": "research_only_approximate_candidate",
            "source_sha": "b" * 40,
        }
    )
    summary["formal"]["solve"]["postsolve"]["global_true_relative_residual"] = 1.0e-5
    summary_path = consumer_root / "consumer_summary.json"
    summary_path.write_text(json.dumps(summary) + "\n", encoding="utf-8")
    with pytest.raises(Task041ComparisonError) as caught:
        load_task041_side_balh_result(root, method="candidate")
    assert caught.value.context["own_gates"]["failure_classification"] == (
        "numeric_gate_fail"
    )
    assert caught.value.context["own_gates"]["raw_residuals"][
        "global_true_relative_residual"
    ] == 1.0e-5


@pytest.mark.parametrize("missing_field", ("grid_payload", "canonical"))
def test_task041_missing_official_artifact_keeps_own_gates(
    comparison_pair, missing_field
):
    summary_path = comparison_pair["candidate"] / "consumer" / "consumer_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    authority_path = Path(summary["authority_path"])
    authority = json.loads(authority_path.read_text(encoding="utf-8"))
    authority["observables"]["A_volume"] = 0.10002
    authority.pop(missing_field)
    authority_path.write_text(
        json.dumps(authority, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    with pytest.raises(Task041ComparisonError) as caught:
        load_task041_side_balh_result(comparison_pair["candidate"], method="candidate")
    own_gates = caught.value.context["own_gates"]
    assert own_gates["closure"] == pytest.approx(2.0e-5)
    assert own_gates["energy_closure_status"] == "numeric_gate_fail"
    assert own_gates["raw_traction"]["bottom"] == 1.0e-10
    assert own_gates["failure_classification"] == "numeric_gate_fail"


def test_task041_comparison_weak_and_significant_channels(comparison_pair):
    candidate = load_task041_side_balh_result(
        comparison_pair["candidate"], method="candidate"
    )
    exact = load_task041_side_balh_result(comparison_pair["exact"], method="exact")
    key = next(iter(candidate.external_rows))
    candidate.external_rows[key]["power_ratio"] = 1.0e-9
    exact.external_rows[key]["power_ratio"] = 1.0e-9
    weak = _compare_external(candidate, exact)
    weak_row = next(row for row in weak["rows"] if tuple(row["key"]) == key)
    assert weak_row["significant"] is False
    assert weak_row["pass"] is True
    candidate.external_rows[key]["power_ratio"] = 2.0e-8
    significant = _compare_external(candidate, exact)
    significant_row = next(
        row for row in significant["rows"] if tuple(row["key"]) == key
    )
    assert significant_row["significant"] is True
    assert significant_row["pass"] is False
    candidate.arrays["E_V_per_m"][:] = 0.0
    exact.arrays["E_V_per_m"][:] = 0.0
    candidate.arrays["H_A_per_m"][:] = 0.0
    exact.arrays["H_A_per_m"][:] = 0.0
    assert _compare_selected_fields(candidate, exact)["pass"] is True
    assert _pair_identity(candidate, exact)["pass"] is True
    candidate.identity["physical_sha256"] = "f" * 64
    assert _pair_identity(candidate, exact)["pass"] is False


def test_task041_comparison_reused_time_and_postphase_resource_failure(
    comparison_pair,
):
    candidate_sample_path = (
        comparison_pair["candidate"]
        / "numerical_output/log/memory_stages.jsonl"
    )
    rows = [json.loads(line) for line in candidate_sample_path.read_text().splitlines()]
    rows[-1]["memory_authority_bytes"] = 64 * 2**30 + 1
    candidate_sample_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    result = compare_task041_side_balh_pair(
        comparison_pair["candidate"], comparison_pair["exact"]
    )
    assert result["resource_contract_pass"] is False
    assert result["common_workflow"]["producer_binding"][
        "candidate_reuses_producer"
    ] is True
    assert result["common_workflow"]["workflow_wall"]["candidate_phase_sum_seconds"] == 1.0
