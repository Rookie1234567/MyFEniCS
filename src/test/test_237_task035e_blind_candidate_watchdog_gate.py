from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from benchmarks.run_task033_full3d_watchdog import (
    GIB,
    TASK035E_BLIND_CANDIDATE_AUTHORITY_SCHEMA,
    TASK035E_BLIND_CANDIDATE_BACKEND,
    _apply_task035e_reference_dynamic_cap,
    _parse_args,
    _task035e_blind_candidate_authority,
    _task035e_blind_candidate_plan_gate,
    _task035e_blind_candidate_resource_policy,
    _task035e_blind_candidate_solver_gate,
    _task035e_blind_live_role_evidence_gate,
    _task035e_namespaced_json_sha256,
    _task035e_private_regular_input_path,
    _validate_task035e_blind_candidate_plan,
    _validate_task035e_transition_action_input,
    _worker_command,
    _worker_launch_contract,
)
from benchmarks.task035e_candidate_output import candidate_config_sha256
from src.adaptivity.blind_controller.contracts import (
    FORMAL_GOAL_IDS,
    FORMAL_GOAL_INVENTORY_SHA256,
)
from src.adaptivity.stage4_local_h import (
    stage4_multilevel_local_h_refinement_plan_payload,
)
from src.adaptivity.task035e_initial_space import (
    build_task035e_initial_space_plan,
)
from src.adaptivity.task035e_hp_transition import (
    build_initial_hp_transition_state,
    hp_transition_action_payload,
)
from src.adaptivity.task035e_plan_transition import (
    build_next_solver_plan,
    canonical_solver_content_sha256,
)
from src.common.config_3d import target_stage4_config


SOURCE_SHA = "7" * 40


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _transition_fixture(
    h_nm: float,
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    cfg = target_stage4_config(degree=6, h_nm=h_nm)
    initial = build_task035e_initial_space_plan(
        cfg,
        path_id="A" if h_nm == 20.0 else "B",
        source_sha=SOURCE_SHA,
        comm_size=8,
    )
    state = build_initial_hp_transition_state(
        initial.forest,
        initial.cell_degree_by_key,
        source_sha=SOURCE_SHA,
        algorithm_sha256=initial.audit["algorithm_sha256"],
    )
    target = next(
        key
        for key, degree in state.cell_degree_by_key.items()
        if degree == 5
    )
    action = hp_transition_action_payload(
        state,
        action_id="fixture-p-up",
        kind="p-up",
        degree_deltas={target: 1},
    )
    transition = build_next_solver_plan(
        cfg,
        current_plan=initial.plan_payload(),
        state=state,
        action=action,
        comm_size=8,
    )
    return (
        initial.plan_payload(),
        dict(action),
        dict(transition.plan_payload),
    )


def _p_keep_transition_fixture(
    h_nm: float,
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    cfg = target_stage4_config(degree=6, h_nm=h_nm)
    initial = build_task035e_initial_space_plan(
        cfg,
        path_id="A" if h_nm == 20.0 else "B",
        source_sha=SOURCE_SHA,
        comm_size=8,
    )
    state = build_initial_hp_transition_state(
        initial.forest,
        initial.cell_degree_by_key,
        source_sha=SOURCE_SHA,
        algorithm_sha256=initial.audit["algorithm_sha256"],
    )
    action = hp_transition_action_payload(
        state,
        action_id="fixture-p-keep",
        kind="p-keep",
        degree_deltas={},
    )
    transition = build_next_solver_plan(
        cfg,
        current_plan=initial.plan_payload(),
        state=state,
        action=action,
        comm_size=8,
    )
    return (
        initial.plan_payload(),
        dict(action),
        dict(transition.plan_payload),
    )


def _plan_payload(h_nm: float) -> dict[str, object]:
    return _transition_fixture(h_nm)[2]


def _plan_file(tmp_path: Path, h_nm: float) -> tuple[Path, str]:
    path = tmp_path / f"path-h{h_nm:g}.json"
    path.write_text(
        json.dumps(_plan_payload(h_nm), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)
    return path, _sha(path)


def _initial_plan_file(
    tmp_path: Path,
    *,
    path_id: str,
    h_nm: float,
) -> tuple[Path, str]:
    plan = build_task035e_initial_space_plan(
        target_stage4_config(degree=6, h_nm=h_nm),
        path_id=path_id,
        source_sha=SOURCE_SHA,
        comm_size=8,
    )
    path = tmp_path / f"path-{path_id.lower()}-initial.json"
    path.write_text(
        json.dumps(plan.plan_payload(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)
    return path, _sha(path)


def _cli(path: Path, sha256: str, h_nm: str = "20") -> list[str]:
    return [
        "--degree",
        "6",
        "--h-nm",
        h_nm,
        "--polarization-kind",
        "s",
        "--run-kind",
        "full-solve",
        "--mpi-size",
        "8",
        "--profile",
        "default",
        "--stage4-full3d-assembly-backend",
        TASK035E_BLIND_CANDIDATE_BACKEND,
        "--stage4-local-h-refinement-plan",
        str(path),
        "--stage4-local-h-refinement-plan-sha256",
        sha256,
        "--task035e-blind-candidate-gate",
        "--task035e-blind-trial-id",
        "path-a-cycle-2",
        "--task035e-blind-cycle-index",
        "0",
        "--task035e-blind-output-role",
        "current",
        "--verified-clean-sha",
        SOURCE_SHA,
    ]


def _replace(cli: list[str], option: str, value: str) -> list[str]:
    result = list(cli)
    result[result.index(option) + 1] = value
    return result


def _snapshot_binding(
    plan: dict[str, object],
    *,
    cycle_index: int,
) -> dict[str, object]:
    return {
        "plan_payload": plan,
        "plan_identity": {
            "forest_leaf_catalog_sha256": plan["expected_forest"][
                "leaf_catalog_sha256"
            ],
            "cell_degree_plan_sha256": plan[
                "cell_interior_degree_plan_sha256"
            ],
        },
        "snapshot_cycle_index": cycle_index,
    }


def _write_private_json(path: Path, payload: object) -> tuple[Path, str]:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)
    return path, _sha(path)


def _rehash_action(action: dict[str, object]) -> dict[str, object]:
    identity = {
        "action_id": action.get("action_id"),
        "kind": action.get("kind"),
        "cycle_index": action.get("cycle_index"),
        "source_sha": action.get("source_sha"),
        "algorithm_sha256": action.get("algorithm_sha256"),
        "canonical_target_ids": action.get("canonical_target_ids"),
    }
    action["action_identity_sha256"] = hashlib.sha256(
        json.dumps(
            identity,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("ascii")
    ).hexdigest()
    unsigned = dict(action)
    unsigned.pop("action_sha256", None)
    action["action_sha256"] = hashlib.sha256(
        json.dumps(
            unsigned,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("ascii")
    ).hexdigest()
    return action


def test_h20_and_h15_are_open_only_under_the_blind_gate(
    tmp_path: Path,
) -> None:
    h20, h20_sha = _plan_file(tmp_path, 20.0)
    h15, h15_sha = _plan_file(tmp_path, 15.0)
    assert _parse_args(_cli(h20, h20_sha)).h_nm == 20.0
    assert _parse_args(_cli(h15, h15_sha, "15")).h_nm == 15.0

    with pytest.raises(SystemExit):
        _parse_args(["--degree", "6", "--h-nm", "20"])
    with pytest.raises(SystemExit):
        _parse_args(_replace(_cli(h20, h20_sha), "--mpi-size", "4"))
    with pytest.raises(SystemExit):
        _parse_args(
            [
                *_cli(h20, h20_sha),
                "--task035e-reference-certifier-gate",
            ]
        )


def test_plan_is_hash_bound_rebuilt_and_has_complete_p456_inventory(
    tmp_path: Path,
) -> None:
    current, action, target = _transition_fixture(20.0)
    path = tmp_path / "transition-plan.json"
    path.write_text(
        json.dumps(target, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    sha256 = _sha(path)
    gate = _task035e_blind_candidate_plan_gate(
        target,
        expected_file_sha256=sha256,
        observed_file_sha256=sha256,
        expected_h_nm=20.0,
        config=target_stage4_config(degree=6, h_nm=20.0),
        expected_source_sha=SOURCE_SHA,
        expected_cycle_index=1,
        expected_output_role="current",
        current_snapshot_binding={
            "plan_payload": current,
            "plan_identity": {
                "forest_leaf_catalog_sha256": current[
                    "expected_forest"
                ]["leaf_catalog_sha256"],
                "cell_degree_plan_sha256": current[
                    "cell_interior_degree_plan_sha256"
                ],
            },
            "snapshot_cycle_index": 0,
        },
        transition_action=action,
    )
    assert gate["pass"] is True, gate["failures"]
    assert gate["degree_counts"]["p4"] > 0
    assert gate["degree_counts"]["p5"] > 0
    assert gate["degree_counts"]["p6"] > 0

    tampered = json.loads(path.read_text(encoding="utf-8"))
    tampered["cell_interior_degrees"][0]["degree"] = 3
    failed = _task035e_blind_candidate_plan_gate(
        tampered,
        expected_file_sha256=sha256,
        observed_file_sha256=sha256,
        expected_h_nm=20.0,
        config=target_stage4_config(degree=6, h_nm=20.0),
        expected_source_sha=SOURCE_SHA,
        expected_cycle_index=1,
        expected_output_role="current",
        current_snapshot_binding={
            "plan_payload": current,
            "plan_identity": {
                "forest_leaf_catalog_sha256": current[
                    "expected_forest"
                ]["leaf_catalog_sha256"],
                "cell_degree_plan_sha256": current[
                    "cell_interior_degree_plan_sha256"
                ],
            },
            "snapshot_cycle_index": 0,
        },
        transition_action=action,
    )
    assert failed["pass"] is False
    assert "canonical_rebuild_exact" in failed["failures"]


def test_p_keep_current_repeat_is_action_and_plan_qualified(
    tmp_path: Path,
) -> None:
    current, action, target = _p_keep_transition_fixture(20.0)
    target_path, target_sha = _write_private_json(
        tmp_path / "p-keep-plan.json",
        target,
    )
    action_path, action_sha = _write_private_json(
        tmp_path / "p-keep-action.json",
        action,
    )
    args = _parse_args(_cli(target_path, target_sha))
    args.task035e_blind_cycle_index = 1
    args.task035e_transition_action = action_path
    args.task035e_transition_action_sha256 = action_sha
    binding = _snapshot_binding(current, cycle_index=0)

    validated_action, action_gate = (
        _validate_task035e_transition_action_input(
            args,
            current_snapshot_binding=binding,
            target_plan=target,
        )
    )
    assert validated_action["kind"] == "p-keep"
    assert action_gate["pass"] is True, action_gate["failures"]
    assert action_gate["checks"]["p_keep_current_role_only"] is True
    assert action_gate["checks"]["p_keep_empty_action"] is True
    assert (
        action_gate["checks"]["p_keep_execution_identities_unchanged"]
        is True
    )

    plan_gate = _task035e_blind_candidate_plan_gate(
        target,
        expected_file_sha256=target_sha,
        observed_file_sha256=target_sha,
        expected_h_nm=20.0,
        config=target_stage4_config(degree=6, h_nm=20.0),
        expected_source_sha=SOURCE_SHA,
        expected_cycle_index=1,
        expected_output_role="current",
        current_snapshot_binding=binding,
        transition_action=validated_action,
    )
    assert plan_gate["pass"] is True, plan_gate["failures"]
    assert (
        plan_gate["checks"]["p_keep_solver_content_unchanged"] is True
    )
    assert canonical_solver_content_sha256(
        target
    ) == canonical_solver_content_sha256(current)
    assert target != current


def test_p_keep_action_rejects_shadow_role_and_nonempty_targets(
    tmp_path: Path,
) -> None:
    current, action, target = _p_keep_transition_fixture(20.0)
    target_path, target_sha = _write_private_json(
        tmp_path / "p-keep-plan.json",
        target,
    )
    binding = _snapshot_binding(current, cycle_index=0)

    action_path, action_sha = _write_private_json(
        tmp_path / "p-keep-action.json",
        action,
    )
    shadow_args = _parse_args(_cli(target_path, target_sha))
    shadow_args.task035e_blind_output_role = "p-shadow"
    shadow_args.task035e_transition_action = action_path
    shadow_args.task035e_transition_action_sha256 = action_sha
    with pytest.raises(SystemExit, match="p_keep_current_role_only"):
        _validate_task035e_transition_action_input(
            shadow_args,
            current_snapshot_binding=binding,
            target_plan=target,
        )

    nonempty = json.loads(json.dumps(action))
    nonempty["canonical_target_ids"] = ["cell:r0:l1:i0:j0:k0"]
    nonempty["degree_deltas"] = [
        {
            "key": {"root": 0, "level": 1, "i": 0, "j": 0, "k": 0},
            "delta": 1,
        }
    ]
    _rehash_action(nonempty)
    nonempty_path, nonempty_sha = _write_private_json(
        tmp_path / "p-keep-nonempty-action.json",
        nonempty,
    )
    current_args = _parse_args(_cli(target_path, target_sha))
    current_args.task035e_blind_cycle_index = 1
    current_args.task035e_transition_action = nonempty_path
    current_args.task035e_transition_action_sha256 = nonempty_sha
    with pytest.raises(SystemExit, match="p_keep_empty_action"):
        _validate_task035e_transition_action_input(
            current_args,
            current_snapshot_binding=binding,
            target_plan=target,
        )


def test_p_keep_plan_rejects_solver_drift_and_stale_cycle() -> None:
    current, action, target = _p_keep_transition_fixture(20.0)
    binding = _snapshot_binding(current, cycle_index=0)
    drifted = json.loads(json.dumps(target))
    drifted["ordinary_default_changed"] = True
    provenance = drifted["provenance"]
    provenance["next_plan_canonical_solver_content_sha256"] = (
        canonical_solver_content_sha256(drifted)
    )
    unsigned_provenance = dict(provenance)
    unsigned_provenance.pop("transition_provenance_sha256")
    provenance["transition_provenance_sha256"] = hashlib.sha256(
        json.dumps(
            unsigned_provenance,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("ascii")
    ).hexdigest()
    drift_sha = hashlib.sha256(
        json.dumps(drifted, sort_keys=True).encode("utf-8")
    ).hexdigest()
    drift_gate = _task035e_blind_candidate_plan_gate(
        drifted,
        expected_file_sha256=drift_sha,
        observed_file_sha256=drift_sha,
        expected_h_nm=20.0,
        config=target_stage4_config(degree=6, h_nm=20.0),
        expected_source_sha=SOURCE_SHA,
        expected_cycle_index=1,
        expected_output_role="current",
        current_snapshot_binding=binding,
        transition_action=action,
    )
    assert drift_gate["pass"] is False
    assert (
        "p_keep_solver_content_unchanged" in drift_gate["failures"]
    )

    stale_gate = _task035e_blind_candidate_plan_gate(
        target,
        expected_file_sha256="a" * 64,
        observed_file_sha256="a" * 64,
        expected_h_nm=20.0,
        config=target_stage4_config(degree=6, h_nm=20.0),
        expected_source_sha=SOURCE_SHA,
        expected_cycle_index=2,
        expected_output_role="current",
        current_snapshot_binding=binding,
        transition_action=action,
    )
    assert stale_gate["pass"] is False
    assert "provenance_request_bound" in stale_gate["failures"]
    assert "transition_action_bound" in stale_gate["failures"]

    reused_old_plan_gate = _task035e_blind_candidate_plan_gate(
        current,
        expected_file_sha256="b" * 64,
        observed_file_sha256="b" * 64,
        expected_h_nm=20.0,
        config=target_stage4_config(degree=6, h_nm=20.0),
        expected_source_sha=SOURCE_SHA,
        expected_cycle_index=1,
        expected_output_role="current",
        current_snapshot_binding=binding,
        transition_action=action,
    )
    assert reused_old_plan_gate["pass"] is False
    assert "provenance_request_bound" in reused_old_plan_gate["failures"]


@pytest.mark.parametrize(
    ("path_id", "h_nm"),
    (("A", 20.0), ("B", 15.0)),
)
def test_cycle_zero_initial_p4_p5_level_one_plan_is_admitted(
    tmp_path: Path,
    path_id: str,
    h_nm: float,
) -> None:
    path, sha256 = _initial_plan_file(
        tmp_path,
        path_id=path_id,
        h_nm=h_nm,
    )
    args = _parse_args(_cli(path, sha256, f"{h_nm:g}"))
    args.task035e_blind_cycle_index = 0
    gate = _validate_task035e_blind_candidate_plan(args)

    assert gate is not None
    assert gate["pass"] is True, gate["failures"]
    assert gate["degree_counts"]["p4"] > 0
    assert gate["degree_counts"]["p5"] > 0
    assert gate["degree_counts"]["p6"] == 0
    assert gate["checks"]["valid_incremental_multilevel_mesh"] is True


def test_cycle_zero_rejects_rehashed_non_deterministic_p6_initial_map(
    tmp_path: Path,
) -> None:
    path, _sha256 = _initial_plan_file(
        tmp_path,
        path_id="A",
        h_nm=20.0,
    )
    original = json.loads(path.read_text(encoding="utf-8"))
    stages = tuple(
        tuple(
            (
                *tuple(float(value) for value in row["lower"]),
                *tuple(float(value) for value in row["upper"]),
            )
            for row in stage["marked_leaves"]
        )
        for stage in original["refinement_stages"]
    )
    overrides = {
        (
            *tuple(float(value) for value in row["lower"]),
            *tuple(float(value) for value in row["upper"]),
        ): int(row["degree"])
        for row in original["cell_interior_degrees"]
    }
    changed = next(box for box, degree in overrides.items() if degree == 4)
    overrides[changed] = 6
    tampered = stage4_multilevel_local_h_refinement_plan_payload(
        target_stage4_config(degree=6, h_nm=20.0),
        stages,
        comm_size=8,
        trace_degree=4,
        cell_interior_degree=6,
        provenance=original["provenance"],
        cell_interior_degree_overrides=overrides,
        variable_trace_from_cell_degrees=True,
    )
    path.write_text(
        json.dumps(tampered, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    args = _parse_args(_cli(path, _sha(path)))
    args.task035e_blind_cycle_index = 0
    with pytest.raises(SystemExit, match="deterministic_initial"):
        _validate_task035e_blind_candidate_plan(args)


def test_formal_inputs_require_private_regular_non_evaluator_paths(
    tmp_path: Path,
) -> None:
    plan, sha256 = _initial_plan_file(
        tmp_path,
        path_id="A",
        h_nm=20.0,
    )
    plan.chmod(0o644)
    with pytest.raises(SystemExit, match="mode 0600"):
        _validate_task035e_blind_candidate_plan(
            _parse_args(_cli(plan, sha256))
        )

    plan.chmod(0o600)
    protected = tmp_path / "Hidden_Auditor"
    protected.mkdir()
    copied = protected / "plan.json"
    copied.write_bytes(plan.read_bytes())
    copied.chmod(0o600)
    with pytest.raises(SystemExit, match="evaluator/reference"):
        _task035e_private_regular_input_path(
            copied,
            label="blind candidate plan",
        )

    sealed = tmp_path / "sealed-reference"
    sealed.mkdir()
    copied = sealed / "action.json"
    copied.write_bytes(plan.read_bytes())
    copied.chmod(0o600)
    with pytest.raises(SystemExit, match="evaluator/reference"):
        _task035e_private_regular_input_path(
            copied,
            label="transition action",
        )

    symlink = tmp_path / "plan-link.json"
    symlink.symlink_to(plan)
    with pytest.raises(SystemExit, match="non-symlink"):
        _task035e_private_regular_input_path(
            symlink,
            label="blind candidate plan",
        )


def test_cli_rejects_late_trial_and_terminal_shadow_cycle(
    tmp_path: Path,
) -> None:
    path, sha256 = _plan_file(tmp_path, 20.0)
    with pytest.raises(SystemExit):
        _parse_args(
            _replace(
                _cli(path, sha256),
                "--task035e-blind-trial-id",
                "invalid trial with spaces",
            )
        )
    shadow_cli = _replace(
        _cli(path, sha256),
        "--task035e-blind-output-role",
        "p-shadow",
    )
    shadow_cli = _replace(
        shadow_cli,
        "--task035e-blind-cycle-index",
        "5",
    )
    shadow_cli.extend(
        (
            "--task035e-current-snapshot-manifest",
            "/tmp/current-snapshot.json",
            "--task035e-current-snapshot-manifest-sha256",
            "9" * 64,
        )
    )
    with pytest.raises(SystemExit):
        _parse_args(shadow_cli)


def test_dynamic_cap_and_parent_worker_contract_are_bounded_by_11_gib(
    tmp_path: Path,
) -> None:
    path, sha256 = _plan_file(tmp_path, 20.0)
    args = _parse_args(_cli(path, sha256))
    snapshot = {
        "wsl_total_bytes": 100 * GIB,
        "host_available_bytes": 90 * GIB,
    }
    policy = _task035e_blind_candidate_resource_policy(snapshot)
    assert policy["effective_job_cap_bytes"] == 11 * GIB
    _apply_task035e_reference_dynamic_cap(args, snapshot)
    assert args.terminate_gib == 11.0
    args.run_dir = tmp_path / "run"

    command = _worker_command(args, args.run_dir)
    assert "--task035e-blind-candidate-gate" in command
    assert command[command.index("--terminate-gib") + 1] == "11.0"
    assert (
        command[
            command.index("--stage4-local-h-refinement-plan-sha256") + 1
        ]
        == sha256
    )
    contract = _worker_launch_contract(args)
    assert contract["task035e_blind_plan_sha256"] == sha256
    assert contract["task035e_dynamic_termination_bytes"] == 11 * GIB


def test_solver_gate_and_closed_candidate_authority() -> None:
    args = _parse_args(
        _cli(Path("/tmp/plan.json"), "8" * 64)
    )
    args.task035e_blind_cycle_index = 2
    args.terminate_gib = 11.0
    config = {"case_name": "blind", "mesh_target_size": 20.0}
    summary = {
        "config": config,
        "stage4_full3d_assembly_backend_actual": (
            TASK035E_BLIND_CANDIDATE_BACKEND
        ),
        "stage4_variable_p_active": True,
        "stage4_local_h_active": True,
        "stage4_assembly_time_cell_static_condensation": True,
        "petsc_direct_solver_profile": "default",
        "linear_solve_method": "direct_lu",
        "selected_parallel_lu_solver_type": "mumps",
        "actual_ksp_type": "preonly",
        "actual_pc_type": "lu",
        "actual_pc_factor_solver_type": "mumps",
        "linear_solve_petsc_options": {
            "ksp_type": "preonly",
            "pc_type": "lu",
            "pc_factor_mat_solver_type": "mumps",
        },
        "stage4_local_h_constraint_audit": {
            "schema_version": (
                "task035e.stage4-multilevel-local-hp-reduction-authority.v1"
            ),
            "status": "stage4_local_h_reduction_authority_pass",
            "pass": True,
            "variable_trace_from_cell_degrees": True,
            "mesh": {
                "schema_version": (
                    "task035e.stage4-multilevel-local-h-mesh.v1"
                ),
                "true_multilevel": True,
                "maximum_level": 2,
                "plan_file_sha256": "8" * 64,
            },
            "degree_plan": {
                "schema_version": (
                    "task035e.local-h-variable-exact-sequence-plan.v1"
                ),
                "cell_driven_variable_trace_component_complete": True,
                "cell_degree_counts": {"p4": 1, "p5": 2, "p6": 3},
            },
            "physical_trace": {
                "variable_trace_opt_in": True,
                "trace_degree_values": [4, 5, 6],
            },
            "trace_constraints": {
                "pass": True,
                "local_variable_trace_implemented": True,
                "selective_trace_action": (
                    "cell_driven_p4_p5_p6_exact_sequence_trace"
                ),
                "constraint_kinds": ["floquet", "hanging"],
            },
        },
    }
    gate = _task035e_blind_candidate_solver_gate(
        args,
        summary,
        plan_gate={"pass": True},
        live_resource_gate={
            "pass": True,
            "memory_cap_at_most_11_gib": True,
            "maximum_swap_authority_bytes": 0,
        },
    )
    assert gate["pass"] is True, gate["failures"]

    authority = _task035e_blind_candidate_authority(
        args,
        summary,
        source_sha=SOURCE_SHA,
        qualified=True,
    )
    assert authority == {
        "schema_version": TASK035E_BLIND_CANDIDATE_AUTHORITY_SCHEMA,
        "selected": True,
        "output_role": "blind_current_solve",
        "trial_id": "path-a-cycle-2",
        "cycle_index": 2,
        "source_sha": SOURCE_SHA,
        "config_sha256": candidate_config_sha256(config),
    }
    assert (
        _task035e_blind_candidate_authority(
            args,
            summary,
            source_sha=SOURCE_SHA,
            qualified=False,
        )
        is None
    )

    for cli_role, authority_role in (
        ("p-shadow", "blind_p_shadow_solve"),
        ("h-shadow", "blind_h_shadow_solve"),
    ):
        role_cli = _replace(
            _cli(Path("/tmp/plan.json"), "8" * 64),
            "--task035e-blind-output-role",
            cli_role,
        )
        role_cli.extend(
            (
                "--task035e-current-snapshot-manifest",
                "/tmp/current-snapshot.json",
                "--task035e-current-snapshot-manifest-sha256",
                "9" * 64,
                "--task035e-transition-action",
                "/tmp/action.json",
                "--task035e-transition-action-sha256",
                "a" * 64,
            )
        )
        role_args = _parse_args(
            role_cli
        )
        role_authority = _task035e_blind_candidate_authority(
            role_args,
            summary,
            source_sha=SOURCE_SHA,
            qualified=True,
        )
        assert role_authority is not None
        assert role_authority["output_role"] == authority_role


def test_solver_gate_accepts_executed_initial_p4_p5_state() -> None:
    args = _parse_args(_cli(Path("/tmp/plan.json"), "8" * 64))
    summary = {
        "stage4_full3d_assembly_backend_actual": (
            TASK035E_BLIND_CANDIDATE_BACKEND
        ),
        "stage4_variable_p_active": True,
        "stage4_local_h_active": True,
        "stage4_assembly_time_cell_static_condensation": True,
        "petsc_direct_solver_profile": "default",
        "linear_solve_method": "direct_lu",
        "selected_parallel_lu_solver_type": "mumps",
        "actual_ksp_type": "preonly",
        "actual_pc_type": "lu",
        "actual_pc_factor_solver_type": "mumps",
        "linear_solve_petsc_options": {
            "ksp_type": "preonly",
            "pc_type": "lu",
            "pc_factor_mat_solver_type": "mumps",
        },
        "stage4_local_h_constraint_audit": {
            "schema_version": (
                "task035e.stage4-multilevel-local-hp-reduction-authority.v1"
            ),
            "status": "stage4_local_h_reduction_authority_pass",
            "pass": True,
            "variable_trace_from_cell_degrees": True,
            "mesh": {
                "schema_version": (
                    "task035e.stage4-multilevel-local-h-mesh.v1"
                ),
                "true_multilevel": False,
                "maximum_level": 1,
                "plan_file_sha256": "8" * 64,
            },
            "degree_plan": {
                "schema_version": (
                    "task035e.local-h-variable-exact-sequence-plan.v1"
                ),
                "cell_driven_variable_trace_component_complete": True,
                "cell_degree_counts": {"p4": 5, "p5": 7, "p6": 0},
            },
            "physical_trace": {
                "variable_trace_opt_in": True,
                "trace_degree_values": [4, 5],
            },
            "trace_constraints": {
                "pass": True,
                "local_variable_trace_implemented": True,
                "selective_trace_action": (
                    "cell_driven_p4_p5_p6_exact_sequence_trace"
                ),
                "constraint_kinds": ["floquet", "hanging"],
            },
        },
    }
    gate = _task035e_blind_candidate_solver_gate(
        args,
        summary,
        plan_gate={"pass": True},
        live_resource_gate={
            "pass": True,
            "memory_cap_at_most_11_gib": True,
            "maximum_swap_authority_bytes": 0,
        },
    )
    assert gate["pass"] is True, gate["failures"]


def test_shadow_live_gate_accepts_sorted_json_goal_mapping(
    tmp_path: Path,
) -> None:
    signed = {
        goal_id: float(index + 1) * 1.0e-8
        for index, goal_id in enumerate(sorted(FORMAL_GOAL_IDS))
    }
    gradient_unsigned = {
        "schema_version": "task035e.formal-59-goal-live-gradients.v1",
        "status": "formal_59_goal_live_gradients_pass",
        "pass": True,
        "formal_goal_count": len(FORMAL_GOAL_IDS),
        "formal_goal_inventory_sha256": FORMAL_GOAL_INVENTORY_SHA256,
    }
    gradient = {
        **gradient_unsigned,
        "gradient_inventory_sha256": _task035e_namespaced_json_sha256(
            gradient_unsigned,
            namespace="task035e.formal-gradient-inventory.v1",
        ),
    }
    implementation_unsigned = {
        "schema_version": (
            "task035e.actual-dwr-implementation-identity.v1"
        ),
        "module_file_sha256": _sha(
            Path(__file__).resolve().parents[1]
            / "adaptivity"
            / "task035e_actual_dwr.py"
        ),
    }
    implementation_sha = _task035e_namespaced_json_sha256(
        implementation_unsigned,
        namespace="task035e.actual-dwr-implementation.v1",
    )
    goal_rows = []
    for goal_id in FORMAL_GOAL_IDS:
        goal_unsigned = {
            "goal_id": goal_id,
            "signed_eta_real_zH_r": signed[goal_id],
        }
        goal_rows.append(
            {
                **goal_unsigned,
                "goal_evidence_sha256": (
                    _task035e_namespaced_json_sha256(
                        goal_unsigned,
                        namespace="task035e.actual-dwr.per-goal.v1",
                    )
                ),
            }
        )
    actual_unsigned = {
        "schema_version": "task035e.actual-live-shadow-dwr.v1",
        "status": "actual_live_shadow_dwr_pass",
        "pass": True,
        "source_sha": SOURCE_SHA,
        "shadow_kind": "p-shadow",
        "shadow_plan_identity": {"file_sha256": "8" * 64},
        "layout_identity": {},
        "operator_identity": {},
        "enriched_current_residual": {
            "partition_bound_sha256": "2" * 64,
        },
        "goal_inventory": {
            "formal_goal_count": len(FORMAL_GOAL_IDS),
            "formal_goal_inventory_sha256": (
                FORMAL_GOAL_INVENTORY_SHA256
            ),
            "ordered_goal_ids": list(FORMAL_GOAL_IDS),
        },
        "goals": goal_rows,
        "implementation_identity": {
            **implementation_unsigned,
            "implementation_sha256": implementation_sha,
        },
        "aggregate_identities": {
            "implementation_sha256": implementation_sha,
            "primal_residual_sha256": "2" * 64,
            "adjoint_system_sha256": _task035e_namespaced_json_sha256(
                {
                    "shadow_plan_identity": {
                        "file_sha256": "8" * 64,
                    },
                    "layout_identity": {},
                    "operator_identity": {},
                },
                namespace="task035e.actual-dwr-adjoint-system.v1",
            ),
        },
    }
    actual = {
        **actual_unsigned,
        "report_sha256": _task035e_namespaced_json_sha256(
            actual_unsigned,
            namespace="task035e.actual-live-shadow-dwr-report.v1",
        ),
    }
    rank_rows = [
        {
            "rank": rank,
            "transfer": {"pass": True},
            "projection": {"pass": True},
            "primal_extraction": {"pass": True},
        }
        for rank in range(8)
    ]
    outer_unsigned = {
        "schema_version": "task035e.live-shadow-evaluation.v1",
        "status": "live_shadow_59_goal_actual_dwr_pass",
        "pass": True,
        "source_sha": SOURCE_SHA,
        "trial_id": "path-a-cycle-2",
        "cycle_index": 2,
        "shadow_kind": "p-shadow",
        "mpi_size": 8,
        "formal_mpi8_qualified": True,
        "current_snapshot": {
            "manifest_file_sha256": "9" * 64,
            "manifest_payload_sha256": "4" * 64,
            "current_plan_file_sha256": "5" * 64,
        },
        "shadow_plan_file_sha256": "8" * 64,
        "goal_gradient_inventory": gradient,
        "actual_dwr": actual,
        "signed_dwr_delta": signed,
        "formal_goal_count": len(FORMAL_GOAL_IDS),
        "formal_goal_inventory_sha256": FORMAL_GOAL_INVENTORY_SHA256,
        "rank_pipeline_audits": rank_rows,
        "rank_pipeline_catalog_sha256": (
            _task035e_namespaced_json_sha256(
                rank_rows,
                namespace="task035e.shadow-pipeline-rank-catalog.v1",
            )
        ),
        "capability_credit": {
            "current_primal_snapshot_complete": True,
            "current_to_shadow_injection_complete": True,
            "local_h_transfer_complete": False,
            "formal_59_goal_gradient_construction_complete": True,
            "actual_enriched_residual_complete": True,
            "actual_59_goal_adjoint_complete": True,
            "actual_signed_dwr_complete": True,
            "shadow_endpoint_effectivity_complete": False,
            "accuracy_credit": False,
        },
        "hidden_reference_consumed": False,
        "endpoint_delta_used_as_dwr": False,
        "ordinary_default_changed": False,
    }
    payload = {
        **outer_unsigned,
        "payload_sha256": _task035e_namespaced_json_sha256(
            outer_unsigned,
            namespace="task035e.live-shadow-evaluation-payload.v1",
        ),
    }
    evidence = tmp_path / "task035e_p_shadow_evaluation.json"
    evidence.write_text(
        json.dumps(payload, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    evidence.chmod(0o600)
    role_cli = _replace(
        _cli(Path("/tmp/plan.json"), "8" * 64),
        "--task035e-blind-output-role",
        "p-shadow",
    )
    role_cli = _replace(
        role_cli,
        "--task035e-blind-cycle-index",
        "2",
    )
    role_cli.extend(
        (
            "--task035e-current-snapshot-manifest",
            "/tmp/current-snapshot.json",
            "--task035e-current-snapshot-manifest-sha256",
            "9" * 64,
            "--task035e-transition-action",
            "/tmp/action.json",
            "--task035e-transition-action-sha256",
            "a" * 64,
        )
    )
    gate = _task035e_blind_live_role_evidence_gate(
        _parse_args(role_cli),
        evidence_path=evidence,
        payload=json.loads(evidence.read_text(encoding="utf-8")),
    )
    assert gate["pass"] is True, gate["failures"]

    malformed = json.loads(json.dumps(payload))
    malformed["rank_pipeline_audits"][0] = 1
    malformed_unsigned = dict(malformed)
    malformed_unsigned.pop("payload_sha256")
    malformed["payload_sha256"] = _task035e_namespaced_json_sha256(
        malformed_unsigned,
        namespace="task035e.live-shadow-evaluation-payload.v1",
    )
    malformed_gate = _task035e_blind_live_role_evidence_gate(
        _parse_args(role_cli),
        evidence_path=evidence,
        payload=malformed,
    )
    assert malformed_gate["pass"] is False
    assert "rank_pipeline_and_capability" in malformed_gate["failures"]
