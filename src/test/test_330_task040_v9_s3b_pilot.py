"""Focused Task040 V9-E S3b pilot contracts."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

import src.solvers.floquet_background_hcurl_s3_formal as s3_formal
import src.solvers.floquet_background_hcurl_s3_pilot as s3_pilot
from benchmarks.task040_level_a import (
    V9_E_S3_B1_SCHEMA,
    V9_E_S3_INPUT_RELATIVE_PATH,
    V9_E_S3_INPUT_SHA256,
    V9_E_S3_J1_BASELINE_MANIFEST_OPTION,
    V9_E_S3_J1_BASELINE_MANIFEST_SHA256_OPTION,
    V9_E_S3_J1_BASELINE_ONLY_FLAG,
    V9_E_S3_J1_BASELINE_SCHEMA,
    V9_E_S3_STRUCTURED_B1_ONLY_FLAG,
    _load_s3_j1_baseline_manifest,
    build_task040_level_a_plan,
)
from src.common.config_3d import target_stage4_config
from src.solvers.floquet_background_hcurl_s3_formal import (
    compare_s3_candidate_source_to_baseline,
    validate_s3_j1_baseline_manifest,
)
from src.solvers.floquet_background_hcurl_s3_pilot import (
    S3B_CANDIDATE_R64_LIMIT,
    S3B_CANDIDATE_R256_LIMIT,
    S3B_CONDITIONAL_PASS,
    S3B_CONDITIONAL_UNSTABLE,
    S3B_EXPECTED_ACTIVE_ROWS,
    S3B_EXPECTED_MODE_COUNT,
    S3B_EXPECTED_ROWS_PER_MODE,
    S3B_EXTERNAL_SOURCE_COLUMN,
    S3B_EXTERNAL_SOURCE_LABEL,
    S3B_EXTERNAL_SOURCE_SEED,
    S3B_EXTERNAL_SOURCE_SIGN,
    S3B_FGMRES_CONDITIONAL_TOTAL_IT,
    S3B_FGMRES_INITIAL_MAX_IT,
    S3B_FGMRES_RESTART,
    S3B_FIVE_SOURCE_INCOMPLETE,
    S3B_FIVE_SOURCE_MAX_IT,
    S3B_FIVE_SOURCE_NO_SIGNAL,
    S3B_FIVE_SOURCE_PASS,
    S3B_FIVE_SOURCE_RESIDUAL_LIMIT,
    S3B_FIVE_SOURCE_RESOURCE_STOP,
    S3B_FIVE_SOURCE_STRICT_RESIDUAL_LIMIT,
    S3B_FIVE_SOURCE_UNSTABLE,
    S3B_INITIAL_NO_SIGNAL,
    S3B_INITIAL_POSITIVE,
    S3B_INITIAL_UNSTABLE,
    S3B_MAX_LOCAL_ROWS,
    S3B_NEXT_CONDITIONAL_256,
    S3B_NEXT_FACTOR_FREE_PRODUCTIONIZATION,
    S3B_NEXT_FIVE_SOURCE_BOTTOM,
    S3B_NEXT_FIXED_LOR,
    S3CurrentLayoutSourceFactory,
    S3FixedRightFgmres,
    adjudicate_s3_b1_conditional_gate,
    adjudicate_s3_b1_final_five_source_bare_f_gate,
    adjudicate_s3_b1_initial_gate,
    build_s3_b1_background_config,
)
from src.solvers.hybrid_bare_f_authority import V5_BARE_F_SOURCE_LABELS

_SOURCE_SHA = "a" * 40
_INPUT_PATH = "/tmp/task040_s3b_input.dat"
_INPUT_SHA256 = "b" * 64
_PHYSICAL_MODEL_SHA256 = "c" * 64
_MANIFEST_SHA256 = "d" * 64
_HASHES = {
    "canonical_key_set_sha256": "1" * 64,
    "canonical_value_sha256": "2" * 64,
    "source_definition_sha256": "3" * 64,
    "source_canonical_identity_sha256": "4" * 64,
}


def _s3_runner_paths(tmp_path: Path) -> dict[str, object]:
    repository_root = Path(__file__).resolve().parents[2]
    return {
        "input_path": repository_root / V9_E_S3_INPUT_RELATIVE_PATH,
        "exact_spool_root": tmp_path / "spool",
        "run_directory": tmp_path / "run",
        "source_sha": "a" * 40,
    }


def test_s3b_runner_plan_contracts(tmp_path: Path) -> None:
    paths = _s3_runner_paths(tmp_path)
    baseline = build_task040_level_a_plan(
        **paths,
        v9_e_s3_j1_baseline_only=True,
    )
    assert baseline["schema"] == V9_E_S3_J1_BASELINE_SCHEMA
    assert baseline["route"] == "V9_E_S3B"
    assert baseline["input"] == str(paths["input_path"].resolve())
    assert baseline["input_expected"] == {
        "relative_path": V9_E_S3_INPUT_RELATIVE_PATH,
        "sha256": V9_E_S3_INPUT_SHA256,
    }
    assert baseline["mpi_size"] == 8
    assert baseline["threads"] == 1
    assert baseline["timeout_seconds"] == 10800
    assert baseline["absolute_terminate_memory_bytes"] == 45 * 2**30
    assert baseline["swap_limit_bytes"] == 0
    assert baseline["watchdog_required"] is True
    assert baseline["bottom_route_only_required"] is True
    assert baseline["fixed_configuration"]["bottom_operator"] == "bare_F"
    assert baseline["fixed_configuration"]["active_rows"] == (
        S3B_EXPECTED_ACTIVE_ROWS
    )
    assert baseline["fixed_configuration"]["operator_identity"] == (
        "system.fine_action"
    )
    assert baseline["factor_inventory"]["j1_layer_factor_count_ready"] == 6

    manifest_path = tmp_path / "j1" / "run_summary.json"
    candidate = build_task040_level_a_plan(
        **paths,
        v9_e_s3_structured_b1_only=True,
        v9_e_s3_j1_baseline_manifest=manifest_path,
        v9_e_s3_j1_baseline_manifest_sha256="d" * 64,
    )
    assert candidate["schema"] == V9_E_S3_B1_SCHEMA
    assert candidate["route"] == "V9_E_S3B"
    assert candidate["baseline_manifest"] == {
        "path": str(manifest_path.resolve()),
        "sha256": "d" * 64,
    }
    assert candidate["factor_inventory"]["owner_local_bounded_factor_count"] == 18
    assert candidate["factor_inventory"]["max_local_rows"] == 468
    assert candidate["factor_inventory"]["full_side_factor_count"] == 0
    assert candidate["factor_inventory"]["full_cross_section_factor_count"] == 0
    assert candidate["watchdog_required"] is True
    assert candidate["bottom_route_only_required"] is True
    assert candidate["fixed_configuration"]["bottom_operator"] == "bare_F"
    assert candidate["fixed_configuration"]["active_rows"] == (
        S3B_EXPECTED_ACTIVE_ROWS
    )
    assert candidate["fixed_configuration"]["fgmres_restart"] == 64
    assert candidate["fixed_configuration"]["fgmres_initial_max_it"] == 64
    assert candidate["fixed_configuration"]["fgmres_conditional_total_it"] == 256
    assert candidate["fixed_configuration"]["exact_physical_fft"] is False
    assert candidate["structure_gate"]["phase_model"] == (
        "topological_orbit_dft_approximation"
    )
    assert candidate["structure_gate"][
        "fe_sized_topology_coordinate_metadata_allgather"
    ] is True
    assert candidate["structure_gate"]["production"] is False


def test_s3b_runner_manifest_pair_and_route_guards(tmp_path: Path) -> None:
    paths = _s3_runner_paths(tmp_path)
    manifest = tmp_path / "baseline.json"
    with pytest.raises(ValueError, match="together"):
        build_task040_level_a_plan(
            **paths,
            v9_e_s3_structured_b1_only=True,
            v9_e_s3_j1_baseline_manifest=manifest,
        )
    with pytest.raises(ValueError, match="candidate-only"):
        build_task040_level_a_plan(
            **paths,
            v9_e_s3_j1_baseline_only=True,
            v9_e_s3_j1_baseline_manifest=manifest,
            v9_e_s3_j1_baseline_manifest_sha256="d" * 64,
        )
    with pytest.raises(ValueError, match="requires the J1 baseline"):
        build_task040_level_a_plan(
            **paths,
            v9_e_s3_structured_b1_only=True,
        )
    with pytest.raises(ValueError, match="lowercase SHA256"):
        build_task040_level_a_plan(
            **paths,
            v9_e_s3_structured_b1_only=True,
            v9_e_s3_j1_baseline_manifest=manifest,
            v9_e_s3_j1_baseline_manifest_sha256="D" * 64,
        )
    with pytest.raises(ValueError, match="mutually exclusive"):
        build_task040_level_a_plan(
            **paths,
            v9_e_s3_j1_baseline_only=True,
            v9_source_bridge_only=True,
        )
    with pytest.raises(ValueError, match="mutually exclusive"):
        build_task040_level_a_plan(
            **paths,
            v9_e_s3_j1_baseline_only=True,
            v9_e_s3_structured_b1_only=True,
            v9_e_s3_j1_baseline_manifest=manifest,
            v9_e_s3_j1_baseline_manifest_sha256="d" * 64,
        )


def test_s3b_runner_flag_names_are_frozen() -> None:
    assert V9_E_S3_J1_BASELINE_ONLY_FLAG == "--v9-e-s3-j1-baseline-only"
    assert V9_E_S3_STRUCTURED_B1_ONLY_FLAG == "--v9-e-s3-structured-b1-only"
    assert V9_E_S3_J1_BASELINE_MANIFEST_OPTION == (
        "--v9-e-s3-j1-baseline-manifest"
    )
    assert V9_E_S3_J1_BASELINE_MANIFEST_SHA256_OPTION == (
        "--v9-e-s3-j1-baseline-manifest-sha256"
    )


def test_s3b_runner_direct_json_loader_binds_raw_byte_sha(tmp_path: Path) -> None:
    manifest_path = tmp_path / "baseline.json"
    raw = b'{"schema":"direct"}\n'
    manifest_path.write_bytes(raw)

    manifest, observed_sha256, resolved_path = _load_s3_j1_baseline_manifest(
        MPI.COMM_WORLD,
        manifest_path,
    )

    assert manifest == {"schema": "direct"}
    assert observed_sha256 == hashlib.sha256(raw).hexdigest()
    assert resolved_path == str(manifest_path.resolve())


def _baseline_manifest() -> tuple[dict[str, object], dict[str, object]]:
    checkpoints = {
        str(iteration): {
            "true_residual_absolute": absolute,
            "true_residual_relative": relative,
            "finite": True,
        }
        for iteration, absolute, relative in (
            (8, 0.8, 0.08),
            (16, 0.4, 0.04),
            (32, 0.2, 0.02),
            (64, 0.1, 0.01),
        )
    }
    source = {
        "label": S3B_EXTERNAL_SOURCE_LABEL,
        "seed": S3B_EXTERNAL_SOURCE_SEED,
        "column": S3B_EXTERNAL_SOURCE_COLUMN,
        "resolved_column": S3B_EXTERNAL_SOURCE_COLUMN,
        "sign": S3B_EXTERNAL_SOURCE_SIGN,
        "canonical_key_count": S3B_EXPECTED_ACTIVE_ROWS,
        **_HASHES,
        "source_norm": 2.0,
        "source_finite": True,
        "source_nonzero": True,
        "sign_application_count": 1,
        "extra_sign_applied": False,
        "additional_sign_scale": 1.0,
        "sign_embedded_in": "current_DtnBlockAssembler_C_traction_values",
        "raw_global_row_remap": False,
        "numeric_allgather": False,
        "full_vector_replication": False,
    }
    provenance = {
        "source_sha": _SOURCE_SHA,
        "input_path": _INPUT_PATH,
        "input_sha256": _INPUT_SHA256,
        "physical_model_sha256": _PHYSICAL_MODEL_SHA256,
        "mpi_size": 8,
        "threads": 1,
        "side": "bottom",
        "operator_identity": "system.fine_action",
        "full_A_used": False,
        "qep_calls": 0,
    }
    manifest = {
        "schema": "task040.v9_e.s3b_j1_baseline_formal.v1",
        "method": "task040_v9_e_s3b_j1_baseline_formal",
        "route": "V9_E_S3B",
        "classification": "S3B_J1_BASELINE_MEASURED",
        "baseline_only": True,
        "provenance": provenance,
        "fixed_contract": {
            "active_rows": S3B_EXPECTED_ACTIVE_ROWS,
            "source_label": S3B_EXTERNAL_SOURCE_LABEL,
            "source_seed": S3B_EXTERNAL_SOURCE_SEED,
            "source_column": S3B_EXTERNAL_SOURCE_COLUMN,
            "source_sign": S3B_EXTERNAL_SOURCE_SIGN,
            "fgmres_restart": S3B_FGMRES_RESTART,
            "fgmres_initial_max_it": S3B_FGMRES_INITIAL_MAX_IT,
            "rss_hard_bytes": 45 * 2**30,
            "swap_limit_bytes": 0,
            "wall_cap_seconds": 10800,
        },
        "source": source,
        "source_norm": source["source_norm"],
        "source_canonical_key_set_sha256": source["canonical_key_set_sha256"],
        "source_canonical_value_sha256": source["canonical_value_sha256"],
        "fgmres": {
            "checkpoint_complete": True,
            "finite": True,
            "breakdown": False,
            "iterations": S3B_FGMRES_INITIAL_MAX_IT,
            "setup_count": 1,
            "setup_reused": False,
            "checkpoints": checkpoints,
        },
        "j1": {"r64": checkpoints["64"]["true_residual_relative"]},
        "structure": {
            "j1_layer_factor_count_ready": 6,
            "j1_layer_factor_count_after_cleanup": 0,
            "full_cross_section_factor_count_ready": 6,
            "full_cross_section_factor_count_after_cleanup": 0,
            "candidate_max_local_rows_gate_status": "not_applicable",
        },
    }
    binding = {
        "source_sha": _SOURCE_SHA,
        "input_path": _INPUT_PATH,
        "input_sha256": _INPUT_SHA256,
        "physical_model_sha256": _PHYSICAL_MODEL_SHA256,
    }
    return manifest, binding


def _validated_baseline() -> tuple[dict[str, object], dict[str, object]]:
    manifest, binding = _baseline_manifest()
    validated = validate_s3_j1_baseline_manifest(
        manifest,
        _MANIFEST_SHA256,
        _MANIFEST_SHA256,
        **binding,
    )
    return validated, binding


def test_s3b_b1_fixed_background_copy_and_two_level_gates() -> None:
    assert S3B_NEXT_FIXED_LOR == "V9_E_STRUCTURED_BACKGROUND_FIXED_LOR"
    cfg = target_stage4_config(degree=2, h_nm=100.0)
    background, audit = build_s3_b1_background_config(cfg)

    assert audit["material_model"] == "volume_average"
    assert audit["additional_absorbing_shift"] == 0.0
    assert audit["volume_average_weights"] == {"grating": 17.0 / 50.0, "air": 33.0 / 50.0}
    assert set(audit["changed_fields"]).issubset(
        {"case_name", "n_air", "n_grating"}
    )
    assert background.n_air == background.n_grating
    assert background.n_substrate == cfg.n_substrate
    assert S3B_EXPECTED_ACTIVE_ROWS == 8424
    assert S3B_EXPECTED_MODE_COUNT == 18
    assert S3B_EXPECTED_ROWS_PER_MODE == 468
    assert S3B_MAX_LOCAL_ROWS == 1024

    initial_positive = adjudicate_s3_b1_initial_gate(
        0.8,
        0.1,
        finite=True,
        breakdown=False,
        resource_ok=True,
    )
    assert initial_positive["classification"] == S3B_INITIAL_POSITIVE
    assert initial_positive["positive"] is True
    assert initial_positive["next_stage"] == S3B_NEXT_CONDITIONAL_256
    assert initial_positive["candidate_r64"] <= S3B_CANDIDATE_R64_LIMIT

    initial_no_signal = adjudicate_s3_b1_initial_gate(
        0.8,
        0.3,
        finite=True,
        breakdown=False,
        resource_ok=True,
    )
    assert initial_no_signal["classification"] == S3B_INITIAL_NO_SIGNAL
    assert initial_no_signal["next_stage"] == S3B_NEXT_FIXED_LOR

    initial_unstable = adjudicate_s3_b1_initial_gate(
        0.8,
        None,
        finite=False,
        breakdown=True,
        resource_ok=True,
    )
    assert initial_unstable["classification"] == S3B_INITIAL_UNSTABLE
    assert initial_unstable["next_stage"] == S3B_NEXT_FIXED_LOR

    conditional_pass = adjudicate_s3_b1_conditional_gate(
        0.5 * S3B_CANDIDATE_R256_LIMIT,
        finite=True,
        resource_ok=True,
    )
    assert conditional_pass["classification"] == S3B_CONDITIONAL_PASS
    assert conditional_pass["positive"] is True
    assert conditional_pass["next_stage"] == S3B_NEXT_FIVE_SOURCE_BOTTOM

    conditional_unstable = adjudicate_s3_b1_conditional_gate(
        None,
        finite=False,
        resource_ok=True,
    )
    assert conditional_unstable["classification"] == S3B_CONDITIONAL_UNSTABLE
    assert conditional_unstable["next_stage"] == S3B_NEXT_FIXED_LOR

    strict_labels = {
        "modal_traction_positive",
        "modal_traction_negative",
        "external_dtn_coupling",
    }
    five_source_outcomes = {
        label: {
            "postsolve": {
                "true_residual_relative": (
                    S3B_FIVE_SOURCE_STRICT_RESIDUAL_LIMIT
                    if label in strict_labels
                    else S3B_FIVE_SOURCE_RESIDUAL_LIMIT
                ),
                "iteration": S3B_FIVE_SOURCE_MAX_IT,
                "finite": True,
            },
            "finite": True,
            "checkpoint_complete": True,
            "breakdown": False,
            "happy_breakdown": False,
        }
        for label in V5_BARE_F_SOURCE_LABELS
    }
    five_pass = adjudicate_s3_b1_final_five_source_bare_f_gate(
        five_source_outcomes,
        resource_ok=True,
    )
    assert five_pass["classification"] == S3B_FIVE_SOURCE_PASS
    assert five_pass["next_stage"] == S3B_NEXT_FACTOR_FREE_PRODUCTIONIZATION
    assert five_pass["labels_complete"] is True
    assert five_pass["iteration_pass"] is True

    five_no_signal_outcomes = deepcopy(five_source_outcomes)
    five_no_signal_outcomes["fixed_random_repeat_0"]["postsolve"][
        "true_residual_relative"
    ] = S3B_FIVE_SOURCE_RESIDUAL_LIMIT + 1.0e-6
    five_no_signal = adjudicate_s3_b1_final_five_source_bare_f_gate(
        five_no_signal_outcomes,
        resource_ok=True,
    )
    assert five_no_signal["classification"] == S3B_FIVE_SOURCE_NO_SIGNAL
    assert five_no_signal["next_stage"] == S3B_NEXT_FIXED_LOR

    five_unstable_outcomes = deepcopy(five_source_outcomes)
    five_unstable_outcomes["external_dtn_coupling"]["breakdown"] = True
    five_unstable = adjudicate_s3_b1_final_five_source_bare_f_gate(
        five_unstable_outcomes,
        resource_ok=True,
    )
    assert five_unstable["classification"] == S3B_FIVE_SOURCE_UNSTABLE
    assert five_unstable["next_stage"] == S3B_NEXT_FIXED_LOR

    five_incomplete_solve_outcomes = deepcopy(five_source_outcomes)
    five_incomplete_solve_outcomes["external_dtn_coupling"]["checkpoint_complete"] = (
        False
    )
    five_incomplete_solve = adjudicate_s3_b1_final_five_source_bare_f_gate(
        five_incomplete_solve_outcomes,
        resource_ok=True,
    )
    assert five_incomplete_solve["classification"] == S3B_FIVE_SOURCE_UNSTABLE
    assert five_incomplete_solve["next_stage"] == S3B_NEXT_FIXED_LOR

    five_resource = adjudicate_s3_b1_final_five_source_bare_f_gate(
        five_source_outcomes,
        resource_ok=False,
    )
    assert five_resource["classification"] == S3B_FIVE_SOURCE_RESOURCE_STOP
    assert five_resource["next_stage"] == S3B_NEXT_FIXED_LOR

    five_missing_outcomes = dict(five_source_outcomes)
    five_missing_outcomes.pop("fixed_random_repeat_1")
    five_missing = adjudicate_s3_b1_final_five_source_bare_f_gate(
        five_missing_outcomes,
        resource_ok=True,
    )
    assert five_missing["classification"] == S3B_FIVE_SOURCE_INCOMPLETE
    assert five_missing["next_stage"] == S3B_NEXT_FIXED_LOR

    five_early_outcomes = deepcopy(five_source_outcomes)
    five_early_outcomes["fixed_random_repeat_1"] = {
        "postsolve": {
            "true_residual_relative": S3B_FIVE_SOURCE_RESIDUAL_LIMIT,
            "iteration": 7,
            "finite": True,
        },
        "finite": False,
        "checkpoint_complete": False,
        "breakdown": False,
        "happy_breakdown": True,
    }
    five_early = adjudicate_s3_b1_final_five_source_bare_f_gate(
        five_early_outcomes,
        resource_ok=True,
    )
    assert five_early["classification"] == S3B_FIVE_SOURCE_PASS
    assert five_early["checks"]["fixed_random_repeat_1"]["actual_final_iteration"] == 7


def test_s3b_baseline_validator_and_candidate_comparator_real_schema() -> None:
    validated, binding = _validated_baseline()

    assert validated["validated"] is True
    assert validated["manifest_sha256"] == _MANIFEST_SHA256
    assert validated["source_norm"] == 2.0
    assert validated["source_definition_sha256"] == _HASHES["source_definition_sha256"]
    assert validated["source_canonical_identity_sha256"] == _HASHES[
        "source_canonical_identity_sha256"
    ]
    assert validated["provenance"] == _baseline_manifest()[0]["provenance"]

    candidate = deepcopy(validated["source"])
    comparison = compare_s3_candidate_source_to_baseline(candidate, validated)
    assert comparison["pass"] is True
    assert comparison["relative_norm_error"] == 0.0
    assert comparison["checks"]

    with pytest.raises(ValueError, match="1e-12"):
        compare_s3_candidate_source_to_baseline(
            candidate,
            validated,
            relative_tolerance=1.0e-10,
        )

    bad_alias_manifest = deepcopy(_baseline_manifest()[0])
    del bad_alias_manifest["source"]["source_definition_sha256"]
    bad_alias_manifest["source"]["canonical_definition_sha256"] = "3" * 64
    with pytest.raises(ValueError, match="source_definition_sha256"):
        validate_s3_j1_baseline_manifest(
            bad_alias_manifest,
            _MANIFEST_SHA256,
            _MANIFEST_SHA256,
            **binding,
        )


@pytest.mark.parametrize(
    ("field", "value", "check"),
    (
        ("column", S3B_EXTERNAL_SOURCE_COLUMN - 1, "column_matches_baseline_and_fixed"),
        ("extra_sign_applied", True, "extra_sign_applied_matches_baseline_and_fixed"),
        ("source_norm", 2.0 + 1.0e-9, "source_norm_relative_error_within_1e-12"),
    ),
)
def test_s3b_candidate_comparator_reports_representative_mismatches(
    field: str,
    value: object,
    check: str,
) -> None:
    validated, _ = _validated_baseline()
    candidate = deepcopy(validated["source"])
    candidate[field] = value

    comparison = compare_s3_candidate_source_to_baseline(candidate, validated)
    assert comparison["pass"] is False
    assert comparison["checks"][check] is False


class _FactoryTarget:
    def __init__(self) -> None:
        self.cfg = object()
        self.side = "bottom"
        self.local_mesh = object()
        self.V = object()
        self.floquet_data = object()
        self.static_condensation = SimpleNamespace(condensed=object())
        self.fine_action = object()
        self.full_fe_rhs = object()
        self.external_modes = []
        self.blocks = SimpleNamespace(C=object(), D=object(), H=object())
        self.destroy_calls = 0

    def destroy(self) -> None:
        self.destroy_calls += 1


def test_s3_current_layout_source_factory_dispatch_and_nonowning_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = _FactoryTarget()
    calls: list[tuple[str, object, str | None]] = []

    def fake_external(system: object) -> tuple[object, dict[str, object]]:
        calls.append(("external", system, None))
        return object(), {"label": S3B_EXTERNAL_SOURCE_LABEL}

    def fake_v5(system: object, label: str) -> tuple[object, dict[str, object]]:
        calls.append(("v5", system, label))
        return object(), {"label": label}

    monkeypatch.setattr(s3_pilot, "build_s3_external_dtn_source", fake_external)
    monkeypatch.setattr(
        "src.solvers.hybrid_bare_f_authority.build_current_bare_f_rhs",
        fake_v5,
    )
    factory = S3CurrentLayoutSourceFactory(target)
    assert not hasattr(factory, "destroy")
    assert factory.source_order == tuple(V5_BARE_F_SOURCE_LABELS)
    for name in ("fine_action", "V", "floquet_data", "local_mesh", "full_fe_rhs"):
        assert getattr(factory, name) is getattr(target, name)
    for label in factory.source_order:
        _source, audit = factory.build(label)
        assert audit["source_factory"] == "S3CurrentLayoutSourceFactory"
        assert audit["metadata_collective_present"] is True
        assert audit["numeric_allgather"] is False
        json.dumps(audit)
    assert calls == [
        ("v5", factory, V5_BARE_F_SOURCE_LABELS[0]),
        ("v5", factory, V5_BARE_F_SOURCE_LABELS[1]),
        ("external", target, None),
        ("v5", factory, V5_BARE_F_SOURCE_LABELS[3]),
        ("v5", factory, V5_BARE_F_SOURCE_LABELS[4]),
    ]
    assert factory.source_inventory["source_build_counts"] == {
        label: 1 for label in V5_BARE_F_SOURCE_LABELS
    }
    assert factory.dtn_objects_constructed == {"C": 0, "D": 0, "H": 0}
    assert factory.source_inventory["target_action_blocks_borrowed"] == {
        "C": True,
        "D": True,
        "H": True,
    }
    summary = factory.release()
    assert summary["non_owning"] is True
    assert summary["target_destroy_called_by_factory"] is False
    assert summary["petsc_objects_destroyed_by_factory"] is False
    assert target.destroy_calls == 0
    assert factory._target is None
    assert factory.F is None
    assert factory.release() == summary
    with pytest.raises(RuntimeError, match="released"):
        factory.build(S3B_EXTERNAL_SOURCE_LABEL)
    with pytest.raises(ValueError, match="unknown"):
        S3CurrentLayoutSourceFactory(target).build("unknown")


def test_s3_source_factory_audit_failure_destroys_source_and_preserves_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = _FactoryTarget()

    class _Source:
        def __init__(self) -> None:
            self.destroy_calls = 0

        def destroy(self) -> None:
            self.destroy_calls += 1
            raise RuntimeError("cleanup failure")

    source = _Source()
    monkeypatch.setattr(
        s3_pilot,
        "build_s3_external_dtn_source",
        lambda _target: (source, {"unsupported": object()}),
    )
    factory = S3CurrentLayoutSourceFactory(target)
    with pytest.raises(TypeError, match="unsupported") as caught:
        factory.build(S3B_EXTERNAL_SOURCE_LABEL)
    assert source.destroy_calls == 1
    assert "cleanup failure" in "\n".join(caught.value.__notes__)
    assert factory.source_inventory["source_build_counts"][S3B_EXTERNAL_SOURCE_LABEL] == 0


class _BorrowedIdentityAction:
    def __init__(self) -> None:
        self.apply_count = 0
        self.destroyed = False

    def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        if self.destroyed:
            raise RuntimeError("test borrowed action was destroyed")
        source.copy(target)
        self.apply_count += 1

    def destroy(self) -> None:
        self.destroyed = True


def _diagonal_operator(size: int, comm: MPI.Comm) -> PETSc.Mat:
    matrix = PETSc.Mat().createAIJ(
        size=((PETSc.DECIDE, size), (PETSc.DECIDE, size)),
        nnz=1,
        comm=comm,
    )
    first, last = map(int, matrix.getOwnershipRange())
    for row in range(first, last):
        # Distinct unit-circle eigenvalues prevent Krylov closure before 256 steps.
        phase = 2.0 * np.pi * (row + 0.5) / float(size)
        value = PETSc.ScalarType(np.exp(1j * phase))
        matrix.setValue(row, row, value)
    matrix.assemble()
    return matrix


@pytest.mark.skipif(MPI.COMM_WORLD.size not in (1, 2), reason="serial/MPI2 only")
def test_s3b_four_source_fixed_continuation_orchestration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    comm = MPI.COMM_WORLD
    operator = _diagonal_operator(512, comm)
    service = _BorrowedIdentityAction()
    markers: list[str] = []
    captured_gates: list[dict[str, object]] = []

    class _FourSourceFactory:
        def __init__(self) -> None:
            self.build_order, self.source_refs = [], []
            self.destroy_calls = self.release_calls = 0

        def build(self, label: str) -> tuple[PETSc.Vec, dict[str, object]]:
            self.build_order.append(label)
            source = operator.createVecRight()
            source.set(PETSc.ScalarType(1.0 + 0.1j))
            source.assemble()
            self.source_refs.append(source)
            return source, {"label": label, "source_kind": "focused_test"}

        def destroy(self) -> None:
            self.destroy_calls += 1

        def release(self) -> None:
            self.release_calls += 1

    factory = _FourSourceFactory()

    def marker(stage: str, _payload: dict[str, object]) -> None:
        markers.append(stage)

    def capture_gate(
        source_outcomes: dict[str, object], *, resource_ok: bool
    ) -> dict[str, object]:
        assert resource_ok is True
        captured_gates.append(source_outcomes)
        return {
            "classification": S3B_FIVE_SOURCE_PASS,
            "positive": True,
            "gate_pass": True,
            "next_stage": S3B_NEXT_FACTOR_FREE_PRODUCTIONIZATION,
            "task40_open": True,
        }

    monkeypatch.setattr(
        s3_formal,
        "adjudicate_s3_b1_final_five_source_bare_f_gate",
        capture_gate,
    )
    external_outcome = {
        "postsolve": {
            "true_residual_relative": 1.0e-6,
            "finite": True,
            "iteration": S3B_FGMRES_CONDITIONAL_TOTAL_IT,
        },
        "finite": True,
        "checkpoint_complete": True,
        "breakdown": False,
        "happy_breakdown": False,
    }
    external_gate = {
        "classification": S3B_CONDITIONAL_PASS,
        "positive": True,
        "next_stage": S3B_NEXT_FIVE_SOURCE_BOTTOM,
    }
    try:
        result = s3_formal._qualify_s3_b1_remaining_sources(
            operator,
            service,
            factory,
            external_outcome,
            external_gate,
            marker_callback=marker,
        )
        remaining = [
            label
            for label in V5_BARE_F_SOURCE_LABELS
            if label != S3B_EXTERNAL_SOURCE_LABEL
        ]
        assert factory.build_order == remaining
        assert len(factory.source_refs) == 4
        assert tuple(captured_gates[0]) == tuple(V5_BARE_F_SOURCE_LABELS)
        assert all(value is not None for value in captured_gates[0].values())
        assert result["source_order"] == list(V5_BARE_F_SOURCE_LABELS)
        for label in remaining:
            per_source = result["per_source"][label]
            assert per_source["continuation_attempted"] is True
            assert (
                per_source["initial"]["iterations"],
                per_source["conditional"]["total_iterations"],
                per_source["setup_count"],
            ) == (64, 256, 1)
            assert (
                per_source["conditional"]["fixed_five_source_qualification"] is True
            )
            assert (
                per_source["conditional"]["qualification_authorization"]["authorized"]
                is True
            )
            assert (
                per_source["setup_reused"],
                per_source["service_setup_reused"],
                per_source["ksp_reused"],
                per_source["solver_destroyed"],
                per_source["source_destroyed"],
            ) == (True, True, False, True, True)
        assert result["service_apply_count_delta"] > 0
        assert result["operator_borrowed"] is True
        assert result["service_borrowed"] is True
        assert result["factory_released"] is False
        assert operator.getSize() == (512, 512)
        assert service.destroyed is False
        assert factory.destroy_calls == factory.release_calls == 0
        assert markers[0] == "s3b_b1_four_source_begin"
        cursor = 1
        for label in remaining:
            suffixes = (
                "begin",
                "ready",
                "fgmres_setup",
                "r0",
                "r8",
                "r16",
                "r32",
                "r64",
                "r128",
                "r192",
                "r256",
                "solve_end",
                "cleanup",
            )
            for suffix in suffixes:
                cursor = (
                    markers.index(f"s3b_b1_four_source_{label}_{suffix}", cursor) + 1
                )
        assert markers[-1] == "s3b_b1_four_source_final_gate"

        negative_factory = _FourSourceFactory()
        negative_markers: list[str] = []
        with pytest.raises(RuntimeError, match="passed five-source Gate"):
            s3_formal._qualify_s3_b1_remaining_sources(
                operator,
                service,
                negative_factory,
                external_outcome,
                {
                    "classification": s3_pilot.S3B_CONDITIONAL_UNSTABLE,
                    "positive": False,
                    "next_stage": S3B_NEXT_FIXED_LOR,
                },
                marker_callback=lambda stage, _payload: negative_markers.append(
                    stage
                ),
            )
        assert (
            negative_factory.build_order,
            negative_factory.source_refs,
            negative_markers,
            len(captured_gates),
        ) == ([], [], [], 1)
    finally:
        service.destroy()
        operator.destroy()


@pytest.mark.skipif(MPI.COMM_WORLD.size not in (1, 2), reason="serial/MPI2 only")
def test_s3b_fixed_right_fgmres_tiny_diagonal_setup_reuse_and_lifecycle() -> None:
    comm = MPI.COMM_WORLD
    operator = None
    rhs = None
    solver = None
    fixed_solver = None
    misuse_solver = None
    none_gate_solver = None
    action = _BorrowedIdentityAction()
    try:
        operator = _diagonal_operator(512, comm)
        rhs = operator.createVecRight()
        first, last = map(int, rhs.getOwnershipRange())
        rhs.array[:] = np.asarray(
            0.7 + 0.03j * (np.arange(first, last) + 1.0),
            dtype=PETSc.ScalarType,
        )
        rhs.assemble()

        solver = S3FixedRightFgmres(operator, action)
        ksp_identity = id(solver.ksp)
        solution_identity = id(solver.solution)
        diagnostics = solver.diagnostics
        assert diagnostics["setup_count"] == 1
        assert diagnostics["ksp_type"] == "fgmres"
        assert diagnostics["pc_side"] == "right"
        assert diagnostics["restart"] == S3B_FGMRES_RESTART
        assert diagnostics["max_it"] == S3B_FGMRES_INITIAL_MAX_IT
        assert diagnostics["zero_initial_guess"] is True
        assert diagnostics["operator_borrowed"] is True
        assert diagnostics["action_borrowed"] is True

        initial = solver.solve_initial(rhs, "tiny_diagonal")
        assert initial["iterations"] == S3B_FGMRES_INITIAL_MAX_IT
        assert initial["checkpoint_complete"] is True
        assert initial["finite"] is True
        assert initial["setup_count"] == 1
        assert initial["setup_reused"] is False

        explicit_gate = adjudicate_s3_b1_initial_gate(
            1.0,
            0.1,
            finite=True,
            breakdown=False,
            resource_ok=True,
        )
        assert explicit_gate["classification"] == S3B_INITIAL_POSITIVE
        conditional = solver.solve_conditional_to_256(
            rhs,
            "tiny_diagonal",
            explicit_gate,
        )
        assert conditional["total_iterations"] == 256
        assert conditional["checkpoint_complete"] is True
        assert conditional["finite"] is True
        assert conditional["setup_count"] == 1
        assert conditional["setup_reused"] is True
        assert conditional["fixed_five_source_qualification"] is False
        assert conditional["continuation_strategy"] == (
            "same_ksp_pc_service_nonzero_initial_restart_continuation"
        )
        assert id(solver.ksp) == ksp_identity
        assert id(solver.solution) == solution_identity
        assert action.apply_count == solver.diagnostics["pc_apply_count"]
        assert action.apply_count > 0
        assert solver.diagnostics["initial_solve_count"] == 1
        assert solver.diagnostics["conditional_solve_count"] == 1

        fixed_solver = S3FixedRightFgmres(operator, action)
        fixed_initial = fixed_solver.solve_initial(rhs, "tiny_diagonal_fixed")
        assert fixed_initial["iterations"] == S3B_FGMRES_INITIAL_MAX_IT
        assert fixed_initial["checkpoint_complete"] is True
        assert fixed_initial["finite"] is True
        fixed_conditional = fixed_solver.solve_conditional_to_256(
            rhs,
            "tiny_diagonal_fixed",
            initial_gate=None,
            fixed_five_source_qualification=True,
        )
        assert fixed_conditional["total_iterations"] == 256
        assert fixed_conditional["checkpoint_complete"] is True
        assert fixed_conditional["finite"] is True
        assert fixed_conditional["fixed_five_source_qualification"] is True
        assert fixed_conditional["qualification_authorization"] == {
            "kind": "fixed_five_source_qualification",
            "basis": "initial_full64_finite_checkpoints",
            "authorized": True,
        }
        assert "S3B_INITIAL_POSITIVE" not in str(fixed_conditional)

        misuse_solver = S3FixedRightFgmres(operator, action)
        misuse_solver.solve_initial(rhs, "tiny_diagonal_misuse")
        with pytest.raises(RuntimeError, match="initial_gate=None"):
            misuse_solver.solve_conditional_to_256(
                rhs,
                "tiny_diagonal_misuse",
                initial_gate={},
                fixed_five_source_qualification=True,
            )

        none_gate_solver = S3FixedRightFgmres(operator, action)
        none_gate_solver.solve_initial(rhs, "tiny_diagonal_none_gate")
        with pytest.raises(RuntimeError, match="initial_gate must be a mapping"):
            none_gate_solver.solve_conditional_to_256(
                rhs,
                "tiny_diagonal_none_gate",
                initial_gate=None,
            )
    finally:
        for extra_solver in (fixed_solver, misuse_solver, none_gate_solver):
            if extra_solver is not None:
                extra_solver.destroy()
        if solver is not None:
            solver.destroy()
            solver.destroy()
            assert solver.diagnostics["destroyed"] is True
            assert solver.diagnostics["pc_context_destroyed"] is True
            assert action.destroyed is False
        if operator is not None:
            assert operator.getSize() == (512, 512)
        if rhs is not None:
            rhs.destroy()
        if operator is not None:
            operator.destroy()
        action.destroy()
