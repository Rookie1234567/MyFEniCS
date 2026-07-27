from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from benchmarks.run_task033_full3d_watchdog import (
    _parse_args,
    _validate_task035d_case097_plan,
    _validate_task035d_nested_p_inputs,
    _worker_command,
)
from benchmarks.task035d_case097_gates import (
    TASK035D_CASE097_BACKEND,
    TASK035D_HP_FACTORIAL_BRIDGE_AUTHORITY_PATH,
    TASK035D_HP_FACTORIAL_BRIDGE_PLAN_NAME,
    TASK035D_HP_FACTORIAL_BRIDGE_PLAN_PATH,
    TASK035D_LOCAL_H_AUTHORITY_PATH,
    TASK035D_LOCAL_H_PLAN_NAME,
    TASK035D_LOCAL_H_PLAN_PATH,
)


ROOT = Path(__file__).resolve().parents[2]
RECORDS = (
    ROOT
    / "benchmarks"
    / "cases"
    / "097_goal_oriented_exact_sequence_hp_adaptivity"
    / "records"
)
SIGNIFICANT = (
    ROOT
    / "benchmarks"
    / "cases"
    / "095_high_order_local_hp_resource_envelope"
    / "records"
    / "significant_channel_reference_v1.json"
)
PAIR_AUTHORITY = (
    RECORDS / "h15_top_air_nested_p_pair_authority_v1.json"
)
SOURCE_SHA = "a" * 40


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _materialize_snapshot_shards(
    directory: Path,
    payload: dict,
) -> None:
    ownership_ranges = [[rank, rank + 1] for rank in range(8)]
    leaf_partitions = np.array_split(np.arange(134), 8)
    shards = []
    for rank, leaves_array in enumerate(leaf_partitions):
        leaves = list(map(int, leaves_array))
        path = directory / f"rank{rank:04d}.npz"
        zero = np.zeros(1, dtype=np.complex128)
        np.savez(
            path,
            schema_version=np.asarray(
                [
                    "task035d.variable-p-nested-coarse-shard.v1"
                ],
                dtype=np.str_,
            ),
            rank=np.asarray([rank], dtype=np.int64),
            mpi_size=np.asarray([8], dtype=np.int64),
            ownership_range=np.asarray(
                ownership_ranges[rank],
                dtype=np.int64,
            ),
            state_b_owned=zero,
            rhs_b_owned=zero,
            matrix_action_b_on_b_owned=zero,
            residual_b_owned=zero,
            canonical_leaves=np.asarray(leaves, dtype=np.int64),
        )
        shards.append(
            {
                "rank": rank,
                "path": path.name,
                "sha256": _sha256(path),
                "bytes": path.stat().st_size,
                "ownership_range": ownership_ranges[rank],
                "owned_value_count": 1,
                "canonical_leaves": leaves,
                "owned_cell_count": len(leaves),
            }
        )
    payload["shards"] = shards
    payload["vector_identity"]["global_size"] = 8
    payload["same_trace_identity"][
        "matrix_vector_ownership_ranges"
    ] = ownership_ranges


def _local_h_cli(
    *,
    candidate_id: str,
    plan: Path,
    authority: Path,
) -> list[str]:
    return [
        "--degree",
        "6",
        "--h-nm",
        "15",
        "--polarization-kind",
        "s",
        "--run-kind",
        "full-solve",
        "--mpi-size",
        "8",
        "--profile",
        "default",
        "--stage4-full3d-assembly-backend",
        TASK035D_CASE097_BACKEND,
        "--stage4-local-h-refinement-plan",
        str(plan),
        "--stage4-local-h-refinement-plan-sha256",
        _sha256(plan),
        "--task035d-case097-gate",
        "--task035d-candidate-id",
        candidate_id,
        "--task035d-plan-authority",
        str(authority),
        "--task035d-plan-authority-sha256",
        _sha256(authority),
        "--verified-clean-sha",
        SOURCE_SHA,
    ]


def _coarse_cli() -> list[str]:
    return [
        *_local_h_cli(
            candidate_id=TASK035D_HP_FACTORIAL_BRIDGE_PLAN_NAME,
            plan=ROOT / TASK035D_HP_FACTORIAL_BRIDGE_PLAN_PATH,
            authority=ROOT / TASK035D_HP_FACTORIAL_BRIDGE_AUTHORITY_PATH,
        ),
        "--task035d-nested-p-dwr-phase",
        "coarse-snapshot",
        "--task035d-significant-channel-authority",
        str(SIGNIFICANT),
        "--task035d-significant-channel-authority-sha256",
        _sha256(SIGNIFICANT),
        "--task035d-nested-p-pair-authority",
        str(PAIR_AUTHORITY),
        "--task035d-nested-p-pair-authority-sha256",
        _sha256(PAIR_AUTHORITY),
    ]


def _enriched_cli(
    manifest: Path,
) -> list[str]:
    return [
        *_local_h_cli(
            candidate_id=TASK035D_LOCAL_H_PLAN_NAME,
            plan=ROOT / TASK035D_LOCAL_H_PLAN_PATH,
            authority=ROOT / TASK035D_LOCAL_H_AUTHORITY_PATH,
        ),
        "--task035d-nested-p-dwr-phase",
        "enriched-evaluate",
        "--task035d-significant-channel-authority",
        str(SIGNIFICANT),
        "--task035d-significant-channel-authority-sha256",
        _sha256(SIGNIFICANT),
        "--task035d-nested-p-pair-authority",
        str(PAIR_AUTHORITY),
        "--task035d-nested-p-pair-authority-sha256",
        _sha256(PAIR_AUTHORITY),
        "--task035d-coarse-snapshot-manifest",
        str(manifest),
        "--task035d-coarse-snapshot-manifest-sha256",
        _sha256(manifest),
    ]


def test_coarse_phase_is_candidate_locked_and_propagated() -> None:
    args = _parse_args(_coarse_cli())
    assert _validate_task035d_case097_plan(args)["pass"] is True
    gate = _validate_task035d_nested_p_inputs(args)
    assert gate["pass"] is True
    assert gate["phase"] == "coarse-snapshot"
    assert gate["nested_p_pair_authority"]["checks"]["active_plan"] is True
    command = _worker_command(args, Path("/tmp/task035d-nested-coarse"))
    assert command[
        command.index("--task035d-nested-p-dwr-phase") + 1
    ] == "coarse-snapshot"
    assert (
        "--task035d-coarse-snapshot-manifest" not in command
    )
    assert command[
        command.index("--task035d-nested-p-pair-authority") + 1
    ] == str(PAIR_AUTHORITY.resolve())

    wrong = _coarse_cli()
    wrong[
        wrong.index("--task035d-candidate-id") + 1
    ] = TASK035D_LOCAL_H_PLAN_NAME
    with pytest.raises(SystemExit):
        _parse_args(wrong)

    wrong_pair_sha = _coarse_cli()
    wrong_pair_sha[
        wrong_pair_sha.index(
            "--task035d-nested-p-pair-authority-sha256"
        )
        + 1
    ] = "0" * 64
    drifted = _parse_args(wrong_pair_sha)
    assert _validate_task035d_case097_plan(drifted)["pass"] is True
    with pytest.raises(SystemExit, match="pair_authority_sha256"):
        _validate_task035d_nested_p_inputs(drifted)


def test_enriched_phase_validates_hash_bound_coarse_manifest(
    tmp_path,
) -> None:
    manifest = tmp_path / "manifest.json"
    payload = {
        "schema_version": (
            "task035d.variable-p-nested-coarse-snapshot.v1"
        ),
        "pass": True,
        "role": "coarse_B",
        "candidate": {
            "candidate_id": TASK035D_HP_FACTORIAL_BRIDGE_PLAN_NAME,
            "source_sha": SOURCE_SHA,
            "plan_file_sha256": _sha256(
                ROOT / TASK035D_HP_FACTORIAL_BRIDGE_PLAN_PATH
            ),
            "cell_interior_degree_counts": {"5": 32, "6": 102},
            "actual_full3d_equivalent_active_fe_dofs": 76_205,
        },
        "same_trace_identity": {
            "mpi_size": 8,
            "independent_trace_rows": 18_390,
            "auxiliary_rows": 80,
            "matrix_rows": 18_470,
        },
        "significant_channel_authority": {
            "sha256": _sha256(SIGNIFICANT),
        },
        "vector_identity": {"relative_residual": 1.0e-12},
        "full_active_residual": {
            "linear_system_relative_residual": 2.0e-12
        },
        "primal_residual_gate": {
            "pass": True,
            "checks": {
                "finite": True,
                "nonnegative": True,
                "reduced_trace_dtn_relative_residual_le_1e-9": True,
                "full_explicit_true_relative_residual_le_1e-9": True,
            },
        },
        "port_operator_audit": {
            "pass": True,
            "checks": {
                "trace_functionals_present": True,
                "trace_only_gate": True,
                "removed_interior_is_qualified_roundoff": True,
                "no_auxiliary_interior_columns": True,
                "external_operator_content_hash": True,
                "external_rhs_content_hash": True,
                "zero_volume_base_rhs": True,
            },
            "removed_active_interior_over_threshold_max": 0.5,
            "external_operator_content_sha256": "a" * 64,
            "external_rhs_content_sha256": "b" * 64,
        },
    }
    _materialize_snapshot_shards(tmp_path, payload)
    manifest.write_text(
        json.dumps(payload, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    args = _parse_args(_enriched_cli(manifest))
    assert _validate_task035d_case097_plan(args)["pass"] is True
    gate = _validate_task035d_nested_p_inputs(args)
    assert gate["pass"] is True
    assert gate["phase"] == "enriched-evaluate"
    assert gate["coarse_snapshot"]["checks"]["trace_rows"] is True
    assert gate["nested_p_pair_authority"]["checks"][
        "active_launch_authority"
    ] is True
    command = _worker_command(args, Path("/tmp/task035d-nested-enriched"))
    assert command[
        command.index("--task035d-coarse-snapshot-manifest") + 1
    ] == str(manifest.resolve())

    (tmp_path / "rank0007.npz").unlink()
    missing_shard = _parse_args(_enriched_cli(manifest))
    assert _validate_task035d_case097_plan(missing_shard)["pass"] is True
    with pytest.raises(
        SystemExit,
        match="coarse_snapshot_all_shards_preflight",
    ):
        _validate_task035d_nested_p_inputs(missing_shard)
    _materialize_snapshot_shards(tmp_path, payload)
    manifest.write_text(
        json.dumps(payload, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    payload["primal_residual_gate"]["pass"] = False
    manifest.write_text(
        json.dumps(payload, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    failed_residual = _parse_args(_enriched_cli(manifest))
    assert (
        _validate_task035d_case097_plan(failed_residual)["pass"]
        is True
    )
    with pytest.raises(
        SystemExit,
        match="coarse_snapshot_primal_residual_gate",
    ):
        _validate_task035d_nested_p_inputs(failed_residual)

    payload["primal_residual_gate"]["pass"] = True
    payload["same_trace_identity"]["auxiliary_rows"] = 79
    manifest.write_text(
        json.dumps(payload, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    drifted = _parse_args(_enriched_cli(manifest))
    assert _validate_task035d_case097_plan(drifted)["pass"] is True
    with pytest.raises(SystemExit, match="coarse_snapshot_auxiliary_rows"):
        _validate_task035d_nested_p_inputs(drifted)
