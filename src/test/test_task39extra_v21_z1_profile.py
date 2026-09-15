"""Pure evidence-contract tests for the Review V21 Z1 plumbing."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil

import pytest

from benchmarks.check_dual_condensed_robustness_v21 import (
    _cache_description_facts_v21,
    _check_channels,
    _dimension_identity_facts,
    _field_output_facts_v21,
    _jit_preparation_facts_v21,
    MODE_SHA,
    _alias_v21_events,
    _mode_identity_facts_v21,
)
from benchmarks.check_p4_blr_v16 import _json, _jsonl
from src.io import load_and_resolve
from src.io.input_loader import InputError
from src.runners import task038_launcher as launcher


RUN_DIRECTORY = Path(
    "results/euv_grazing1_phi0/"
    "task39extra_v20_y3_lowmem_original__full3d_iterative__mpi1__Mna/"
    "20260914T163338.120918Z"
)
MODE_MANIFEST_SOURCE = Path(
    "benchmarks/artifacts/task39extra/v5_balanced/"
    "c4e86cfe1e6ba88ca5d26df82942e82f190e7eda/e1/mode_manifest.json"
)
V21_INPUTS = (
    ("v21_z2_notch_h10.dat", "Z2_NOTCH_H10", "v21_frozen_notch_h10", (6, 3, 14)),
    ("v21_z3_original_h7p5.dat", "Z3_ORIGINAL_H7P5", "v21_original_h7p5", (9, 5, 22)),
    ("v21_z4_notch_h7p5.dat", "Z4_NOTCH_H7P5", "v21_frozen_notch_h7p5", (9, 5, 22)),
)


def _saved_v20_fixture():
    if not RUN_DIRECTORY.is_dir():
        pytest.skip("the local saved V20 output fixture is unavailable")
    summary = _json(RUN_DIRECTORY / "physical_dual_condensed_memory_v20_summary.json")
    cache = _json(RUN_DIRECTORY / "v20_x1_p6_cache_identity.json")
    return summary, cache


def _digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def test_v21_cache_fixture_uses_actual_class_count_and_rejects_tampering():
    summary, cache = _saved_v20_fixture()
    audit = summary["operator_identity"]["retained_p6"]["p6_build_audit"]
    recipe = summary["operator_identity"]["retained_p6"]["p6_recipe"]
    checked = _cache_description_facts_v21(cache, audit, recipe)
    assert checked["passed"]
    assert checked["class_counts"] == {
        "recipe": 12,
        "retained_local_schur_sum": 12,
        "oriented_schur_sum": 12,
    }

    broken = deepcopy(cache)
    broken_semantic = broken["cache"]["identity_cache"]["semantic"]
    broken_semantic["logical_class_count"] = 13
    broken["cache"]["identity_cache"]["semantic_sha256"] = _digest(
        broken_semantic
    )
    broken["cache"]["identity_cache_semantic_sha256"] = _digest(broken_semantic)
    assert not _cache_description_facts_v21(broken, audit, recipe)["passed"]


@pytest.mark.parametrize("class_count", [26, 28])
def test_v21_cache_fixture_accepts_live_h7p5_class_count(class_count):
    _summary, cache = _saved_v20_fixture()
    audit = deepcopy(_summary["operator_identity"]["retained_p6"]["p6_build_audit"])
    recipe = deepcopy(_summary["operator_identity"]["retained_p6"]["p6_recipe"])
    audit["retained_local_schur_class_count_sum"] = class_count
    audit["oriented_schur_class_count_sum"] = class_count
    recipe["buffer_inventory"]["class_count"] = class_count
    semantic = cache["cache"]["identity_cache"]["semantic"]
    representation = cache["cache"]["identity_cache"]["representation"]
    semantic["logical_class_count"] = class_count
    representation["logical_class_count"] = class_count
    cache["cache"]["identity_cache"]["semantic_sha256"] = _digest(semantic)
    cache["cache"]["identity_cache"]["representation_sha256"] = _digest(
        representation
    )
    cache["cache"]["identity_cache_semantic_sha256"] = _digest(semantic)
    cache["cache"]["identity_cache_representation_sha256"] = _digest(
        representation
    )
    assert _cache_description_facts_v21(cache, audit, recipe)["passed"]
    audit["oriented_schur_class_count_sum"] = class_count - 1
    assert not _cache_description_facts_v21(cache, audit, recipe)["passed"]


def test_v21_jit_fixture_requires_local_roles_but_not_a_cold_miss():
    summary, _cache = _saved_v20_fixture()
    events = _jsonl(RUN_DIRECTORY / "v20_events.jsonl")
    complete = next(
        event
        for event in events
        if event["event"] == "v20_form_preparation_complete"
    )
    complete["facts"]["cache"]["cache_policy"] = "v21_reuse_all_qualified"
    complete["facts"]["cache"]["excluded_module_family"] = None
    complete["facts"]["cache"]["excluded_file_count"] = 0
    complete["facts"]["cache"]["excluded_bytes"] = 0
    checked = _jit_preparation_facts_v21(events, [])
    assert checked["passed"]
    assert checked["cold_reorder_status"] == "OBSERVATION_ONLY"

    complete["facts"]["cache"]["cache_policy"] = "v20_exclude_old_family"
    assert not _jit_preparation_facts_v21(events, [])[
        "checks"
    ]["v21_reuse_all_qualified"]


def test_v21_saved_physics_fixture_recomputes_channels_and_fields():
    summary, _cache = _saved_v20_fixture()
    channel_checks, channel_facts = _check_channels(
        RUN_DIRECTORY / "numerical_output", summary["output_facts"]
    )
    assert all(channel_checks.values())
    assert channel_facts["metrics"]["energy_closure_error"] <= 1.0e-5
    field_checks, _field_facts = _field_output_facts_v21(
        RUN_DIRECTORY / "numerical_output", summary["output_facts"]
    )
    assert all(field_checks.values())


def test_v21_dimension_fixture_uses_active_trace_plus_ports_for_retained_size():
    summary, _cache = _saved_v20_fixture()
    fixture = deepcopy(summary)
    p6_audit = fixture["operator_identity"]["retained_p6"]["p6_build_audit"]
    fixture["actual_dimension_identity"] = {
        "p6": {
            "expected_space_counts": [173802, 51192, 113400, 80],
            "cell_interior_dofs_sha256": "a" * 64,
            "slave_rows_sha256": "b" * 64,
        },
        "p4": {
            "expected_space_counts": [100, 20, 70, 80],
            "cell_interior_dofs_sha256": "c" * 64,
            "slave_rows_sha256": "d" * 64,
        },
    }
    fixture["operator_identity"]["p6_storage_rows"] = 173802
    fixture["operator_identity"]["p4_storage_rows"] = 100
    fixture["operator_identity"]["condensed_rows"] = 100
    fixture["operator_identity"]["partition"].update(
        {"storage_size": 100, "active_rows": 20, "appended_rows": 80}
    )
    fixture["interface_stack"]["condensation"].update(
        {
            "full_rows": 100,
            "active_rows": 20,
            "interior_rows": 70,
            "appended_rows": 80,
            "matrix_rows": 100,
        }
    )
    fixture["operator_identity"]["retained_p6"]["p6_build_audit"] = {
        **p6_audit,
        "full_rows": 173802,
        "active_rows": 51192,
        "interior_rows": 113400,
        "appended_rows": 80,
    }
    fixture["solver"]["retained_global_size"] = 51192 + 80
    fixture["solver"]["retained_outer"]["setup_checks"] = {
        "actual_space_counts": [173802, 51192, 113400, 80],
        "expected_space_counts": [173802, 51192, 113400, 80],
    }
    assert _dimension_identity_facts(fixture)["passed"]
    fixture["interface_stack"]["condensation"]["matrix_rows"] = 99
    assert not _dimension_identity_facts(fixture)["passed"]
    fixture["interface_stack"]["condensation"]["matrix_rows"] = 100
    fixture["solver"]["retained_global_size"] = 113400 + 80
    assert not _dimension_identity_facts(fixture)["passed"]


@pytest.mark.parametrize(
    ("stage", "prefix"),
    [
        ("Z2_NOTCH_H10", "z2"),
        ("Z3_ORIGINAL_H7P5", "z3"),
        ("Z4_NOTCH_H7P5", "z4"),
    ],
)
def test_v21_stage_event_aliases_preserve_worker_rows(stage, prefix):
    original_names = [
        f"{prefix}_independent_final_residual_complete",
        f"{prefix}_authority_limited_output_complete",
        f"{prefix}_physical_output_comparison_complete",
    ]
    events = [{"event": name, "timestamp_ns": index} for index, name in enumerate(original_names)]
    aliased = _alias_v21_events(events, stage=stage)
    names = [row["event"] for row in aliased]
    assert all(name in names for name in original_names)
    assert names.count("y3_independent_final_residual_complete") == 1
    assert names.count("y3_physical_output_comparison_complete") == 2
    assert all("aliased_from" not in row for row in events)


def test_v21_mode_identity_binds_manifest_bytes_and_output_order(tmp_path):
    if not MODE_MANIFEST_SOURCE.is_file() or not RUN_DIRECTORY.is_dir():
        pytest.skip("the saved mode/output fixture is unavailable")
    output_directory = tmp_path / "numerical_output"
    output_directory.mkdir()
    shutil.copyfile(
        RUN_DIRECTORY / "numerical_output/dtn_port_diffraction_orders_3d.json",
        output_directory / "dtn_port_diffraction_orders_3d.json",
    )
    manifest_path = tmp_path / "v21_ordered_mode_manifest.json"
    shutil.copyfile(MODE_MANIFEST_SOURCE, manifest_path)
    manifest_bytes = manifest_path.read_bytes()
    summary = {
        "operator_identity": {
            "ordered_mode_sha256": MODE_SHA,
            "retained_p6": {"ordered_mode_sha256": MODE_SHA},
        },
        "mode_manifest": {
            "path": str(manifest_path),
            "sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            "mode_sha256": MODE_SHA,
            "mode_count": 80,
        },
    }
    checked = _mode_identity_facts_v21(summary, tmp_path, output_directory)
    assert checked["passed"]

    broken = deepcopy(summary)
    payload = json.loads(manifest_bytes.decode("utf-8"))
    payload["modes"][0], payload["modes"][1] = payload["modes"][1], payload["modes"][0]
    manifest_path.write_text(
        json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")),
        encoding="ascii",
    )
    broken["mode_manifest"]["sha256"] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    assert not _mode_identity_facts_v21(broken, tmp_path, output_directory)["passed"]


@pytest.mark.parametrize(("filename", "stage", "geometry_identity", "axes"), V21_INPUTS)
def test_v21_input_profiles_bind_frozen_stage_geometry_and_axes(
    filename, stage, geometry_identity, axes
):
    spec = load_and_resolve(Path("input/task39extra") / filename)
    payload = spec.as_jsonable()
    assert spec.solver["stage"] == stage
    assert spec.geometry["geometry_identity"] == geometry_identity
    assert tuple(spec.discretization["mesh_axis_cell_counts"]) == axes
    identity = payload["derived"]["v21_identity"]
    assert identity["plan_id"] == "task039extra.v21.frozen-geometry-mesh-plan.v1"
    assert len(identity["geometry_entity_sha256"]) == 64
    assert len(identity["mesh_semantic_sha256"]) == 64


def test_v21_input_rejects_axis_plan_tampering(tmp_path):
    source = Path("input/task39extra/v21_z3_original_h7p5.dat")
    candidate = tmp_path / source.name
    candidate.write_text(
        source.read_text(encoding="utf-8").replace(
            "mesh_axis_cell_counts = [9, 5, 22]",
            "mesh_axis_cell_counts = [9, 5, 21]",
        ),
        encoding="utf-8",
    )
    with pytest.raises(InputError):
        load_and_resolve(candidate)


def _clock(seconds=0.0):
    return {
        "monotonic_seconds": float(seconds),
        "boottime_seconds": float(seconds),
        "utc_seconds": float(seconds),
    }


def _v21_predecessor_ledger(tmp_path):
    path = launcher._dual_condensed_lowmem_v20_shared_ledger_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema": "task039extra.v20.shared-workflow-ledger.v1",
                "batch_identity": "review_v20_dual_condensed_memory_lifecycle",
                "total_budget_seconds": 43200.0,
                "elapsed_seconds": 0.0,
                "conservative_allowance_seconds": 0.0,
                "policy_debits": [],
                "fresh_worker_count": 0,
                "source_attempts": [],
                "stages": {},
                "unique_bug_replay_count": 0,
                "predecessor_v19_ledger": {},
            }
        ),
        encoding="utf-8",
    )
    return path


def _settle_v21_worker_failure(lease, fixed_source):
    ledger = json.loads(Path(lease["path"]).read_text(encoding="utf-8"))
    attempt = ledger["stages"][lease["stage"]]["attempts"][lease["attempt_index"]]
    run_directory = Path(attempt["run_directory"])
    run_directory.mkdir(parents=True, exist_ok=True)
    failed_source = attempt["source_sha"]
    (run_directory / "implementation_bug_replay.json").write_text(
        json.dumps(
            {
                "classification": "IMPLEMENTATION_BUG",
                "stage": lease["stage"],
                "failed_source_sha": failed_source,
                "fixed_source_sha": fixed_source,
                "bug_and_fix": "V21 focused replay fixture",
            }
        ),
        encoding="utf-8",
    )
    (run_directory / "physical_dual_condensed_robustness_v21_summary.json").write_text(
        json.dumps(
            {
                "status": "FAILED",
                "result_classification": "WORKER_FAILED",
                "source_sha": failed_source,
                "error": "V21 focused worker exception",
            }
        ),
        encoding="utf-8",
    )
    launcher._settle_v14_shared_budget(
        lease,
        status="WORKER_FAILED",
        authority=None,
        parent_interval={"budget_seconds": 1.0},
        parent_clock_end=_clock(2.0),
    )


def test_v21_ledger_allows_one_changed_source_bug_replay_only(tmp_path, monkeypatch):
    predecessor_path = _v21_predecessor_ledger(tmp_path)
    monkeypatch.setattr(
        launcher,
        "V21_PREDECESSOR_V20_LEDGER_SHA256",
        hashlib.sha256(predecessor_path.read_bytes()).hexdigest(),
    )

    def reserve(source, run_directory):
        return launcher._reserve_v21_shared_budget(
            tmp_path,
            run_directory,
            source_sha=source,
            stage="Z2_NOTCH_H10",
            stage_budget={"workflow_seconds": 43200.0, "solve_seconds": 43200.0},
            workflow_clock_start=_clock(),
            time_policy="observe_only",
        )

    first = reserve("a" * 40, tmp_path / "z2_first")
    with pytest.raises(InputError, match="unsettled"):
        reserve("b" * 40, tmp_path / "z2_blocked")
    _settle_v21_worker_failure(first, "b" * 40)
    replay = reserve("b" * 40, tmp_path / "z2_replay")
    assert replay["replay"] is True
    _settle_v21_worker_failure(replay, "c" * 40)
    with pytest.raises(InputError, match="exhausted"):
        reserve("c" * 40, tmp_path / "z2_third")


def _write_v21_prerequisite_fixture(tmp_path, *, source_sha="a" * 40):
    run_directory = tmp_path / "z2_settled"
    run_directory.mkdir()
    summary_path = run_directory / "physical_dual_condensed_robustness_v21_summary.json"
    summary = {
        "schema": "task039extra.v21.worker-summary.v1",
        "stage": "Z2_NOTCH_H10",
        "source_sha": source_sha,
        "stage_pass": True,
    }
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    manifest_path = run_directory / "run_manifest.json"
    manifest = {
        "status": "finished",
        "source_sha": source_sha,
        "source_after": {
            "source_sha": source_sha,
            "tracked_and_nonignored_untracked_clean": True,
        },
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    result = {
        "schema": launcher.V21_CHECKER_SCHEMA,
        "status": "PASS",
        "evidence_valid": True,
        "stage_pass": True,
        "stage": "Z2_NOTCH_H10",
        "classification": "MATCHED_REFERENCE_PASS",
        "source_sha": source_sha,
        "worker_summary_path": str(summary_path.resolve()),
        "worker_summary_sha256": hashlib.sha256(summary_path.read_bytes()).hexdigest(),
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "checks": {"synthetic_complete": True},
    }
    (run_directory / launcher.V21_CHECKER_FILENAME).write_text(
        json.dumps(result), encoding="utf-8"
    )
    return run_directory, summary_path, manifest_path


def test_v21_checker_prerequisite_binds_predecessor_evidence_and_rejects_mutation(tmp_path):
    run_directory, summary_path, manifest_path = _write_v21_prerequisite_fixture(tmp_path)
    ledger_path = tmp_path / "shared_workflow_ledger.json"
    ledger_path.write_text(
        json.dumps(
            {
                "stages": {
                    "Z2_NOTCH_H10": {
                        "active_attempt": None,
                        "attempts": [
                            {
                                "attempt": 1,
                                "source_sha": "a" * 40,
                                "run_directory": str(run_directory),
                                "status": "EVIDENCE_ONLY",
                                "actual_elapsed_seconds": 1.0,
                            }
                        ],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    facts = launcher._validate_v21_checker_prerequisites(
        ledger_path, "Z3_ORIGINAL_H7P5", "b" * 40
    )
    assert facts["records"][0]["all_checker_checks_true"] is True
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["source_after"]["source_sha"] = "c" * 40
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(InputError, match="hash-bound"):
        launcher._validate_v21_checker_prerequisites(
            ledger_path, "Z3_ORIGINAL_H7P5", "b" * 40
        )
