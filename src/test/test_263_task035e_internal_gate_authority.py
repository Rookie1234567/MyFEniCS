from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import stat
from typing import Any, Callable

import pytest

from benchmarks.task035e_candidate_output import (
    CandidateWatchdogInput,
    adapt_candidate_output,
    candidate_config_sha256,
    write_candidate_output,
)
from benchmarks.task035e_internal_gate_authority import (
    AUTHORITY_NAMESPACE,
    BoundJSONInput,
    DEFERRED_AUTHORITY_CLASSIFICATION,
    DEFERRED_AUTHORITY_STATUS,
    FINAL_AUTHORITY_CLASSIFICATION,
    InternalGateAuthorityError,
    build_deferred_internal_gate_authority,
    build_internal_gate_authority,
    main,
    validate_internal_gate_authority,
    write_deferred_internal_gate_authority,
    write_internal_gate_authority,
)
from benchmarks.run_task033_full3d_watchdog import (
    TASK035E_INTERNAL_PROBE_SCHEMA,
)
from src.test.test_232_task035e_candidate_output import (
    _write_candidate_run,
)
from src.adaptivity.blind_controller.state_machine import (
    BlindTrial,
    InternalGates,
    advance_blind_trial,
)
from src.test.test_223_task035e_blind_controller import _cycle, _goals


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_sha(value: Any, *, namespace: str | None = None) -> str:
    digest = hashlib.sha256()
    if namespace is not None:
        digest.update(namespace.encode("ascii"))
        digest.update(b"\0")
    digest.update(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    )
    return digest.hexdigest()


def _write_json(path: Path, value: Any, *, private: bool = False) -> str:
    path.write_text(
        json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    if private:
        path.chmod(0o600)
    return _file_sha(path)


def _qualified_gate_fields(summary: dict[str, Any]) -> None:
    local = summary["stage4_local_h_constraint_audit"]
    mesh = local["mesh"]
    forest = mesh["forest"]
    mesh.update(
        {
            "maximum_level": 2,
            "refinement_stage_count": 2,
            "true_multilevel": True,
            "user_mark_component_count": 2,
            "spatially_separated_user_patches": True,
            "hanging_patch_count": 3,
        }
    )
    forest.update(
        {
            "leaf_level_counts": {"0": 5, "1": 7, "2": 9},
            "strong_2_to_1_balance": True,
            "maximum_adjacent_level_jump": 1,
            "periodic_boundary_audit": {
                "pass": True,
                "checks": {"periodic_orbits_closed": True},
            },
            "material_interface_hanging_face_count": 0,
        }
    )
    local["physical_trace"] = {
        "schema_version": (
            "task035e.broken-hexa-variable-trace-authority.v1"
        ),
        "status": "broken_hexa_variable_trace_constraint_component_pass",
        "pass": True,
        "mpi_size": 8,
        "periodic_cycle_error": 1.0e-13,
        "maximum_relation_residual": 2.0e-13,
        "checks": {
            "periodic_cycle_closure": True,
            "all_hanging_patches_have_relations": True,
        },
        "failures": [],
    }
    local["trace_constraints"] = {
        "schema_version": "task035d.broken-hexa-cell-trace-map.v2",
        "status": "broken_hexa_cell_trace_binding_pass",
        "pass": True,
        "mpi_size": 8,
        "constraint_kinds": ["hanging", "floquet"],
        "contains_hanging_constraints": True,
        "contains_floquet_constraints": True,
        "hanging_slave_rows": 10,
        "periodic_slave_rows": 20,
        "cross_rank_hanging_patch_count": 2,
        "remote_resolution_sha256": "a" * 64,
        "pde_launch_ownership_gate": True,
        "hanging_or_floquet_slave_rows_globally_numbered": False,
        "checks": {
            "canonical_cell_graph_mpi_identity": True,
            "owner_routed_remote_cache_pass": True,
        },
        "failures": [],
    }
    summary["floquet_max_face_transform_fit_residual"] = 1.0e-13
    summary["floquet_edge_corner_constraint_phase_mismatch"] = 2.0e-13
    summary["stage4_dtn_surface_quadrature_degree"] = 25


def _rewrite_run(
    record_input: CandidateWatchdogInput,
    *,
    summary_mutator: Callable[[dict[str, Any]], None] | None = None,
    dtn_mutator: Callable[[dict[str, Any]], None] | None = None,
    record_mutator: Callable[[dict[str, Any]], None] | None = None,
) -> CandidateWatchdogInput:
    record_path = record_input.path
    record = json.loads(record_path.read_text(encoding="utf-8"))
    raw = record["raw_evidence"]
    summary_path = Path(raw["solver_summary"])
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if summary_mutator is not None:
        summary_mutator(summary)
    if dtn_mutator is not None:
        dtn_path = Path(raw["dtn_orders"])
        dtn = json.loads(dtn_path.read_text(encoding="utf-8"))
        dtn_mutator(dtn)
        record["dtn_orders_sha256"] = _write_json(dtn_path, dtn)
    record["solver_summary"] = summary
    record["solver_summary_sha256"] = _write_json(summary_path, summary)
    record["task035e_blind_candidate"]["config_sha256"] = (
        candidate_config_sha256(summary["config"])
    )
    if record_mutator is not None:
        record_mutator(record)
    record_sha = _write_json(record_path, record, private=True)
    Path(
        summary["stage4_local_h_constraint_audit"]["mesh"]["plan_path"]
    ).chmod(0o600)
    return CandidateWatchdogInput(record_path, record_sha)


def _extra_dtn_order(dtn: dict[str, Any]) -> None:
    for polarization in ("s", "p"):
        dtn["orders"].append(
            {
                "side": "top",
                "m": -8,
                "n": 0,
                "polarization": polarization,
                "propagating": False,
                "power_carrying": False,
                "kz": [0.0, 0.7],
                "beta": [0.0, 0.7],
                "outgoing_amplitude_at_boundary": [0.0, 0.0],
                "power_ratio": None,
            }
        )


def _snapshot(
    path: Path,
    *,
    current: Any,
    candidate: dict[str, Any],
) -> str:
    path.mkdir(parents=True)
    plan_path = current.plan_path.resolve()
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    shards = []
    rank_rows = []
    for rank in range(8):
        shard_path = path / f"rank{rank:04d}.npz"
        descriptor = os.open(
            shard_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(f"rank-{rank}-live-shard".encode("ascii"))
        local_sha = f"{rank + 1:064x}"
        shards.append(
            {
                "rank": rank,
                "path": shard_path.name,
                "file_sha256": _file_sha(shard_path),
                "local_identity_sha256": local_sha,
            }
        )
        rank_rows.append(
            {
                "rank": rank,
                "local_identity_sha256": local_sha,
            }
        )
    residual = {
        "linear_system_relative_residual": float(
            candidate["full_explicit_true_residual"]
        )
    }
    gate = {
        "full_active_residual": residual,
        "full_active_residual_sha256": _json_sha(
            residual,
            namespace="task035e.current-full-active-residual.v1",
        ),
    }
    common = {
        "fixture": "real-artifact-binding",
        "reduction": {
            "leaf_catalog_sha256": (
                current.forest_leaf_catalog_sha256
            ),
            "cell_degree_plan_sha256": (
                current.cell_degree_plan_sha256
            ),
        },
    }
    unsigned = {
        "schema_version": "task035e.multigoal-current-live-snapshot.v1",
        "status": "multigoal_current_live_snapshot_pass",
        "pass": True,
        "role": "current_blind_state",
        "source_sha": current.source_sha,
        "trial_id": current.trial_id,
        "cycle_index": current.cycle_index,
        "mpi_size": 8,
        "formal_mpi8_qualified": True,
        "diagnostic_serial_fixture": False,
        "plan_identity": {
            "path": str(plan_path),
            "file_sha256": current.plan_file_sha256,
            "payload_sha256": _json_sha(
                plan,
                namespace="task035e.executed-plan-payload.v1",
            ),
            "forest_leaf_catalog_sha256": (
                current.forest_leaf_catalog_sha256
            ),
            "cell_degree_plan_sha256": (
                current.cell_degree_plan_sha256
            ),
        },
        "common_identity": common,
        "common_identity_sha256": _json_sha(
            common,
            namespace="task035e.current-common-identity.v1",
        ),
        "qualified_primal_gate": gate,
        "qualified_primal_gate_sha256": _json_sha(
            gate,
            namespace="task035e.current-qualified-primal-gate.v1",
        ),
        "partitions": {},
        "matrix_operator": {"full_matrix_serialized": False},
        "rank_bound_identity_sha256": _json_sha(
            rank_rows,
            namespace="task035e.current-rank-bound-identity.v1",
        ),
        "shards": shards,
        "publication": "atomic private MPI8 fixture",
        "no_full_vector_python_allgather": True,
        "full_matrix_persisted": False,
        "capability_credit": {
            "current_primal_snapshot_complete": True,
            "accuracy_credit": False,
        },
        "ordinary_default_changed": False,
    }
    manifest = {
        **unsigned,
        "manifest_payload_sha256": _json_sha(
            unsigned,
            namespace="task035e.multigoal-current-manifest.v1",
        ),
    }
    return _write_json(path / "manifest.json", manifest, private=True)


def _fixture(
    tmp_path: Path,
    *,
    qualify_dtn: bool = True,
    include_serial: bool = False,
) -> dict[str, Any]:
    current_record = _rewrite_run(
        _write_candidate_run(tmp_path / "current"),
        summary_mutator=_qualified_gate_fields,
    )
    current = adapt_candidate_output(current_record)
    candidate_path = tmp_path / "candidate-output.json"
    write_candidate_output(candidate_path, current)
    snapshot_dir = tmp_path / "snapshot"
    snapshot_sha = _snapshot(
        snapshot_dir,
        current=current,
        candidate=dict(current.payload),
    )

    def probe_contract(
        kind: str,
        *,
        mpi_size: int = 8,
        overrides: dict[str, Any] | None = None,
    ) -> Callable[[dict[str, Any]], None]:
        def mutate(record: dict[str, Any]) -> None:
            record["task035e_internal_probe"] = {
                "schema_version": TASK035E_INTERNAL_PROBE_SCHEMA,
                "selected": True,
                "kind": kind,
                "mpi_size": mpi_size,
                "trial_id": current.trial_id,
                "cycle_index": current.cycle_index,
                "output_role": "current",
                "plan_file_sha256": current.plan_file_sha256,
                "current_snapshot_file_sha256": snapshot_sha,
                "config_overrides": dict(overrides or {}),
                "ordinary_default_changed": False,
            }

        return mutate

    algebraic = _rewrite_run(
        _write_candidate_run(tmp_path / "algebraic"),
        record_mutator=probe_contract("algebraic"),
    )

    def dtn_summary(summary: dict[str, Any]) -> None:
        summary["config"]["stage4_dtn_order_policy"] = "manual"
        summary["config"]["diffraction_order_max_m"] = 8
        summary["config"]["diffraction_order_max_n"] = 1

    dtn = _rewrite_run(
        _write_candidate_run(tmp_path / "dtn"),
        summary_mutator=dtn_summary,
        dtn_mutator=_extra_dtn_order if qualify_dtn else None,
        record_mutator=probe_contract(
            "dtn",
            overrides={
                "stage4_dtn_order_policy": "manual",
                "diffraction_order_max_m": 8,
                "diffraction_order_max_n": 1,
            },
        ),
    )

    def tighter_postprocess(summary: dict[str, Any]) -> None:
        summary["stage4_dtn_surface_quadrature_degree"] = 27
        summary["config"]["stage4_dtn_quadrature_degree"] = 27

    postprocess = _rewrite_run(
        _write_candidate_run(tmp_path / "postprocess"),
        summary_mutator=tighter_postprocess,
        record_mutator=probe_contract(
            "postprocess",
            overrides={"stage4_dtn_quadrature_degree": 27},
        ),
    )
    serial = None
    if include_serial:
        def serial_summary(summary: dict[str, Any]) -> None:
            summary["mpi_size"] = 1

        def serial_record(record: dict[str, Any]) -> None:
            record["mpi_size"] = 1
            probe_contract("serial_mpi1", mpi_size=1)(record)

        serial_input = _rewrite_run(
            _write_candidate_run(tmp_path / "serial"),
            summary_mutator=serial_summary,
            record_mutator=serial_record,
        )
        serial = BoundJSONInput(serial_input.path, serial_input.sha256)
    return {
        "candidate_record": BoundJSONInput(
            current_record.path,
            current_record.sha256,
        ),
        "candidate_output": BoundJSONInput(
            candidate_path,
            _file_sha(candidate_path),
        ),
        "current_plan": BoundJSONInput(
            current.plan_path,
            current.plan_file_sha256,
        ),
        "current_snapshot": BoundJSONInput(
            snapshot_dir / "manifest.json",
            snapshot_sha,
        ),
        "algebraic_probe_record": BoundJSONInput(
            algebraic.path,
            algebraic.sha256,
        ),
        "dtn_probe_record": BoundJSONInput(dtn.path, dtn.sha256),
        "postprocess_probe_record": BoundJSONInput(
            postprocess.path,
            postprocess.sha256,
        ),
        "serial_mpi1_record": serial,
    }


def _deferred_inputs(tmp_path: Path) -> dict[str, BoundJSONInput]:
    inputs = _fixture(tmp_path)
    return {
        name: inputs[name]
        for name in (
            "candidate_record",
            "candidate_output",
            "current_plan",
            "current_snapshot",
        )
        if isinstance(inputs[name], BoundJSONInput)
    }


def test_authority_recomputes_all_gates_and_defers_optional_mpi1(
    tmp_path: Path,
) -> None:
    inputs = _fixture(tmp_path)

    authority = build_internal_gate_authority(**inputs)

    assert authority["classification"] == FINAL_AUTHORITY_CLASSIFICATION
    assert authority["gates"] == {
        "full_explicit_residual": 1.0e-12,
        "energy_closure_error": pytest.approx(0.0),
        "absorption_volume": pytest.approx(
            authority["gates"]["absorption_volume"]
        ),
        "floquet_residual_pass": True,
        "hanging_residual_pass": True,
        "serial_mpi_identity_pass": False,
        "multilevel_mesh_pass": True,
        "separated_patch_count": 2,
        "all_local_levels_present": True,
        "algebraic_budget_fraction": pytest.approx(0.0),
        "dtn_budget_fraction": pytest.approx(0.0),
        "postprocess_budget_fraction": pytest.approx(0.0),
    }
    assert authority["measurements"]["mpi_identity"]["status"] == "not_run"
    assert (
        authority["recomputed_checks"][
            "mpi8_candidate_plan_snapshot_identity"
        ]
        is True
    )
    assert set(authority["candidate_identity"]) == {
        "watchdog_record_file_sha256",
        "candidate_output_file_sha256",
        "candidate_output_payload_sha256",
        "plan_file_sha256",
        "plan_payload_sha256",
        "mesh_forest_sha256",
        "degree_map_sha256",
        "current_snapshot_file_sha256",
        "current_snapshot_payload_sha256",
        "snapshot_rank_bound_identity_sha256",
        "snapshot_full_residual_sha256",
        "raw_artifact_sha256",
        "raw_artifact_inventory_sha256",
        "structural_inventory",
    }
    assert authority["authority_sha256"] == _json_sha(
        {
            key: value
            for key, value in authority.items()
            if key != "authority_sha256"
        },
        namespace=AUTHORITY_NAMESPACE,
    )
    validate_internal_gate_authority(authority)


def test_deferred_authority_replays_current_but_cannot_freeze(
    tmp_path: Path,
) -> None:
    authority = build_deferred_internal_gate_authority(
        **_deferred_inputs(tmp_path)
    )

    gates = InternalGates(**authority["gates"])
    assert authority["status"] == DEFERRED_AUTHORITY_STATUS
    assert (
        authority["classification"]
        == DEFERRED_AUTHORITY_CLASSIFICATION
    )
    assert authority["probe_identities"] == []
    assert gates.passed is True
    assert gates.freeze_passed is False
    assert gates.serial_mpi_identity_pass is False
    assert (
        authority["recomputed_checks"]["budget_probe_qualified"]
        == {"algebraic": False, "dtn": False, "postprocess": False}
    )
    for kind, gate_name in (
        ("algebraic", "algebraic_budget_fraction"),
        ("dtn", "dtn_budget_fraction"),
        ("postprocess", "postprocess_budget_fraction"),
    ):
        detail = authority["measurements"]["budgets"][kind]
        assert detail["status"] == "deferred_not_run"
        assert detail["probe_credit"] is False
        assert detail["qualified_comparison"] is False
        assert detail["budget_fraction"] >= 1.0
        assert authority["gates"][gate_name] >= 1.0
    validate_internal_gate_authority(authority)

    trial = BlindTrial(
        trial_id="deferred-cycle",
        algorithm_id="multilevel-hp-v1",
        source_sha="a" * 40,
        initial_path_id="coarse-a",
        initial_mesh_forest_sha256="1" * 64,
        physical_identity_sha256="e" * 64,
    )
    cycle = replace(
        _cycle(0, _goals(), strength=0.1, final=True),
        gates=gates,
    )
    result = advance_blind_trial(trial, cycle).results[-1]
    assert result.accepted_current_state is True
    assert result.freeze_ready is False


def test_deferred_authority_rejects_rehashed_probe_credit_tamper(
    tmp_path: Path,
) -> None:
    authority = build_deferred_internal_gate_authority(
        **_deferred_inputs(tmp_path)
    )
    authority["recomputed_checks"]["budget_probe_qualified"][
        "algebraic"
    ] = True
    authority["authority_sha256"] = _json_sha(
        {
            key: value
            for key, value in authority.items()
            if key != "authority_sha256"
        },
        namespace=AUTHORITY_NAMESPACE,
    )

    with pytest.raises(
        InternalGateAuthorityError,
        match="algebraic budget authority does not replay",
    ):
        validate_internal_gate_authority(authority)


def test_deferred_authority_cli_never_accepts_or_requires_probe_input(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    inputs = _deferred_inputs(tmp_path)
    output = tmp_path / "deferred-authority.json"
    arguments = ["--deferred"]
    for name in (
        "candidate_record",
        "candidate_output",
        "current_plan",
        "current_snapshot",
    ):
        option = name.replace("_", "-")
        bound = inputs[name]
        arguments.extend(
            [
                f"--{option}",
                str(bound.path),
                f"--{option}-sha256",
                bound.sha256,
            ]
        )
    arguments.extend(["--output", str(output)])

    assert main(arguments) == 0
    receipt = json.loads(capsys.readouterr().out)
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert receipt["status"] == "completed"
    assert (
        receipt["classification"]
        == DEFERRED_AUTHORITY_CLASSIFICATION
    )
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert payload["probe_identities"] == []
    validate_internal_gate_authority(payload)


def test_authority_is_private_immutable_and_rejects_free_boolean_tamper(
    tmp_path: Path,
) -> None:
    inputs = _fixture(tmp_path)
    output = tmp_path / "internal-gates-authority.json"

    receipt = write_internal_gate_authority(output, **inputs)

    assert receipt.classification == FINAL_AUTHORITY_CLASSIFICATION
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert receipt.file_sha256 == _file_sha(output)
    assert str(tmp_path) not in output.read_text(encoding="utf-8")
    with pytest.raises(FileExistsError):
        write_internal_gate_authority(output, **inputs)

    authority = json.loads(output.read_text(encoding="utf-8"))
    authority["gates"]["serial_mpi_identity_pass"] = True
    with pytest.raises(
        InternalGateAuthorityError,
        match="self-hash differs",
    ):
        validate_internal_gate_authority(authority)


def test_deferred_writer_is_private_and_immutable(tmp_path: Path) -> None:
    output = tmp_path / "deferred-authority.json"
    inputs = _deferred_inputs(tmp_path)

    receipt = write_deferred_internal_gate_authority(output, **inputs)

    assert receipt.classification == DEFERRED_AUTHORITY_CLASSIFICATION
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    with pytest.raises(FileExistsError):
        write_deferred_internal_gate_authority(output, **inputs)


def test_optional_mpi1_same_plan_output_recomputes_final_identity(
    tmp_path: Path,
) -> None:
    authority = build_internal_gate_authority(
        **_fixture(tmp_path, include_serial=True)
    )

    assert authority["gates"]["serial_mpi_identity_pass"] is True
    assert authority["measurements"]["mpi_identity"]["status"] == "qualified"
    assert authority["measurements"]["mpi_identity"][
        "maximum_normalized_goal_distance"
    ] == pytest.approx(0.0)
    assert [row["kind"] for row in authority["probe_identities"]] == [
        "algebraic",
        "dtn",
        "postprocess",
        "serial_mpi1",
    ]
    validate_internal_gate_authority(authority)


def test_unqualified_dtn_probe_fails_budget_closed_without_crashing(
    tmp_path: Path,
) -> None:
    authority = build_internal_gate_authority(
        **_fixture(tmp_path, qualify_dtn=False)
    )

    assert (
        authority["recomputed_checks"]["budget_probe_qualified"]["dtn"]
        is False
    )
    assert authority["gates"]["dtn_budget_fraction"] == 1.0
    validate_internal_gate_authority(authority)


def test_probe_launch_contract_and_physical_identity_fail_closed(
    tmp_path: Path,
) -> None:
    missing_contract = _fixture(tmp_path / "missing")
    bound = missing_contract["algebraic_probe_record"]
    assert isinstance(bound, BoundJSONInput)
    rewritten = _rewrite_run(
        CandidateWatchdogInput(bound.path, bound.sha256),
        record_mutator=lambda record: record.pop(
            "task035e_internal_probe",
            None,
        ),
    )
    missing_contract["algebraic_probe_record"] = BoundJSONInput(
        rewritten.path,
        rewritten.sha256,
    )
    authority = build_internal_gate_authority(**missing_contract)
    assert authority["gates"]["algebraic_budget_fraction"] == 1.0
    assert authority["measurements"]["budgets"]["algebraic"][
        "formal_probe_launch_replayed"
    ] is False

    physical_drift = _fixture(tmp_path / "physical")
    drift_bound = physical_drift["algebraic_probe_record"]
    assert isinstance(drift_bound, BoundJSONInput)

    def change_wavelength(summary: dict[str, Any]) -> None:
        summary["config"]["lambda0"] = 14.0

    drifted = _rewrite_run(
        CandidateWatchdogInput(drift_bound.path, drift_bound.sha256),
        summary_mutator=change_wavelength,
    )
    physical_drift["algebraic_probe_record"] = BoundJSONInput(
        drifted.path,
        drifted.sha256,
    )
    authority = build_internal_gate_authority(**physical_drift)
    assert authority["gates"]["algebraic_budget_fraction"] == 1.0
    assert authority["measurements"]["budgets"]["algebraic"][
        "same_physics_config"
    ] is False


def test_bound_input_requires_exact_mode_0600_and_hash(
    tmp_path: Path,
) -> None:
    inputs = _fixture(tmp_path)
    record = inputs["candidate_record"]
    assert isinstance(record, BoundJSONInput)
    record.path.chmod(0o644)

    with pytest.raises(
        InternalGateAuthorityError,
        match="mode-0600",
    ):
        build_internal_gate_authority(**inputs)

    record.path.chmod(0o600)
    inputs["candidate_record"] = BoundJSONInput(
        record.path,
        "f" * 64,
    )
    with pytest.raises(
        InternalGateAuthorityError,
        match="file SHA-256 differs",
    ):
        build_internal_gate_authority(**inputs)
