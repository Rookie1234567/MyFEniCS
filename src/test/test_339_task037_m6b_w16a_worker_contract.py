from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from benchmarks import run_task037_extra_m6b as runner
from src.solvers.hcurl_m6b_w16_global_shifted_inner_pc import (
    evaluate_w16a_global_shifted_gate,
)
from src.test.test_338_task037_m6b_w16_global_shifted_inner import (
    _synthetic_summary,
)


def test_w16a_worker_parser_is_fixed_and_has_no_other_solver_authorities():
    parser = runner._parser()
    args = parser.parse_args(
        [
            "m6b-w16a-global-shifted-inner-diagnostic",
            "--run-dir",
            "/tmp/w16a-run",
            "--w7-compact",
            "/tmp/w7.json",
            "--w7-raw-dir",
            "/tmp/w7-raw",
            "--shifted-factor-manifest",
            "/tmp/shifted/manifest.json",
            "--jit-cache-source",
            "/tmp/jit",
            "--expected-source-sha",
            "0123456789abcdef0123456789abcdef01234567",
        ]
    )
    assert args.command == "m6b-w16a-global-shifted-inner-diagnostic"
    assert args.shifted_factor_manifest.endswith("shifted/manifest.json")
    assert not hasattr(args, "w5_compact")
    assert not hasattr(args, "m3y_manifest")
    assert not hasattr(args, "b0_jit_cache_source")

    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "m6b-w16a-global-shifted-inner-diagnostic",
                "--run-dir",
                "/tmp/w16a-run",
            ]
        )


def test_w16a_worker_scope_authority_prediction_and_core_contract():
    scope = runner._m6b_w16a_scope()
    prediction = runner._m6b_w16a_predicted_live_set()
    factor_path = runner.M6B_W16A_SHIFTED_FACTOR_MANIFEST_RELATIVE_PATH

    assert factor_path.endswith(
        "m6b_d98254f_formal_run5/shifted_lu_store/manifest.json"
    )
    assert runner.M6B_W16A_SHIFTED_FACTOR_MANIFEST_SHA256 == (
        "5394db24e96f611870c104fe7367e15163cb89a2943cd455f5c69e39eadf7363"
    )
    assert runner.M6B_W16A_SHIFTED_FACTOR_SOURCE_SHA == (
        "d98254fecddc41940f50f72753ec9f0f80407793"
    )
    assert scope["auxiliary_operator"] == "beta=1 shifted volume-only"
    assert scope["auxiliary_pc"] == (
        "direct_beta1_shifted_row_complete_local_patch"
    )
    assert scope["auxiliary_dtn_used"] is False
    assert scope["projected_range_used"] is False
    assert scope["b0_used"] is False
    assert scope["m3y_used"] is False
    assert scope["inner_cycles"] == 2
    assert scope["inner_max_steps"] == 20
    assert scope["inner_checkpoints"] == [20]
    assert scope["auxiliary_physical_overlap"] is False
    assert prediction["bytes"] == 1_739_986_075
    assert prediction["limit_bytes"] == 1_750_000_000
    assert prediction["gate"] is True
    assert prediction["per_run_scratch_bytes"] == 114_014_112
    assert prediction["two_run_scratch_bytes"] == 228_028_224
    assert prediction["scratch_is_disk_not_rss"] is True
    assert evaluate_w16a_global_shifted_gate(_synthetic_summary())["pass"] is True


def test_w16a_worker_emits_fixed_lifecycle_and_writes_scalar_artifacts_only():
    source = inspect.getsource(runner._run_m6b_w16a_diagnostic)
    events = runner.M6B_W16A_EVENTS
    literal_events = tuple(
        event for event in events if not event.startswith("inner_checkpoint_")
    )
    legacy_start = source.index(
        'action_audit["lifecycle_events"].append("auxiliary_constructed")',
        source.index("core_result = w16b_result"),
    )
    legacy = source[legacy_start:]
    positions = [source.index(f'"{event}"') for event in literal_events[:5]]
    positions.extend(
        legacy_start + legacy.index(f'"{event}"')
        for event in literal_events[5:]
    )
    assert positions == sorted(positions)
    assert 'f"inner_checkpoint_{run_index}_ready"' in source
    assert 'action_audit["lifecycle_events"].append("auxiliary_released")' in source
    assert 'action_audit["lifecycle_events"].append("physical_released")' in source

    assert "M6BScreenCheckpointWriter" in source
    assert "allowed_iterations=(20,)" in source
    assert 'f"w16a_physical_p{index}.npy"' in source
    assert "checkpoint_artifacts" in source
    assert "p_artifacts" in source
    assert "_attach_evidence" in source

    auxiliary_end = legacy.index('"auxiliary_released"')
    auxiliary = legacy[:auxiliary_end]
    assert "build_fullspace_dtn" not in auxiliary
    assert "build_m6b_outer_mat" not in auxiliary
    assert "beta=0.0" not in auxiliary
    assert "ProjectedRangePC" not in source
    assert "beta=0.5" not in source
    assert "M3Y" not in source


def test_w16a_worker_uses_frozen_w7_loader_and_final_release_before_summary():
    source = inspect.getsource(runner._run_m6b_w16a_diagnostic)
    assert "_m6b_w9a_load_w7(" in source
    assert "w7_authority[\"residual\"]" in source
    assert "build_fullspace_dtn_action" in source
    legacy_start = source.index(
        'action_audit["lifecycle_events"].append("auxiliary_constructed")',
        source.index("core_result = w16b_result"),
    )
    legacy = source[legacy_start:]
    assert legacy.index('"physical_released"') < legacy.index(
        'core_result = {'
    )
    assert "shifted_action_total_count" in source
    assert '"global_shifted_action_count"' in source
    assert '"local_exact_shifted_volume_action_count"' in source
    assert '"physical_dtn_action_count"' in source


def _write_factor_authority_fixture(tmp_path, *, compiler=None, dirty=False):
    factor_root = tmp_path / "factor"
    store_dir = factor_root / "shifted_lu_store"
    store_dir.mkdir(parents=True)
    manifest_path = store_dir / "manifest.json"
    builder_path = factor_root / "m6b_builder_summary.json"
    source_sha = "d98254fecddc41940f50f72753ec9f0f80407793"
    manifest = {
        "schema": "task037.extra.h2b.m6b.shifted-lu-store.v1",
        "beta": 1.0,
        "audit": {
            "beta": 1.0,
            "cell_count": 252,
            "factor_count": 84,
            "factor_order": 882,
            "finite": True,
            "retained_total_gate": True,
            "retained_total_bytes": 1_047_654_868,
            "full_dense_patch_matrix_retained": False,
            "ordinary_default_changed": False,
        },
        "identity": {
            "beta": 1.0,
            "operator": "B_beta=Kcurl-k0^2*M_epsilon+i*k0^2*M_abs_epsilon",
            "source_identity": {
                "source_commit_full_sha": source_sha,
                "source_worktree_dirty": False,
                "tracked_source_dirty": False,
            },
        },
        "materialization_identity": {
            "global_matrix": False,
            "global_constraint_matrix": False,
        },
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    frozen_compiler = compiler or {
        "probe_command": ["gcc", "--version"],
        "sysconfig_cc": "gcc",
        "version_line": "gcc test",
    }
    source = {
        "source_commit_full_sha": source_sha,
        "source_worktree_dirty": False,
        "tracked_source_dirty": dirty,
    }
    builder = {
        "schema": "task037.extra.h2b.m6b.v1.builder",
        "status": "measurement_complete",
        "source_at_start": source,
        "source_at_end": source,
        "runtime_identity": {"compiler": frozen_compiler},
        "factor_store": {
            "path": "shifted_lu_store/manifest.json",
            "present": True,
            "sha256": "5394db24e96f611870c104fe7367e15163cb89a2943cd455f5c69e39eadf7363",
        },
    }
    builder_path.write_text(
        json.dumps(runner._attach_evidence(builder)), encoding="utf-8"
    )
    return factor_root, manifest_path


def _patch_factor_authority(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(
        runner,
        "M6B_W16A_SHIFTED_FACTOR_MANIFEST_RELATIVE_PATH",
        "factor/shifted_lu_store/manifest.json",
    )
    manifest_sha = (
        "5394db24e96f611870c104fe7367e15163cb89a2943cd455f5c69e39eadf7363"
    )
    monkeypatch.setattr(runner, "M6B_W16A_SHIFTED_FACTOR_MANIFEST_SHA256", manifest_sha)
    monkeypatch.setattr(
        runner,
        "_sha256_file",
        lambda path: manifest_sha
        if Path(path).name == "manifest.json"
        else "builder-file-sha",
    )


def test_w16a_factor_authority_binds_builder_summary_and_compiler(tmp_path, monkeypatch):
    compiler = {
        "probe_command": ["gcc", "--version"],
        "sysconfig_cc": "gcc",
        "version_line": "gcc test",
    }
    factor_root, manifest_path = _write_factor_authority_fixture(
        tmp_path, compiler=compiler
    )
    _patch_factor_authority(monkeypatch, tmp_path)
    authority = runner._m6b_w16a_factor_authority(manifest_path)
    assert authority["builder_summary"]["path"] == "m6b_builder_summary.json"
    assert authority["builder_summary"]["sha256"] == "builder-file-sha"
    assert authority["factor_compiler"] == compiler
    assert authority["source_commit_full_sha"] == runner.M6B_W16A_SHIFTED_FACTOR_SOURCE_SHA
    assert factor_root == tmp_path / "factor"


@pytest.mark.parametrize("tamper", ["dirty", "missing_compiler"])
def test_w16a_factor_authority_rejects_builder_binding_tamper(
    tmp_path, monkeypatch, tamper
):
    factor_root, manifest_path = _write_factor_authority_fixture(
        tmp_path, dirty=tamper == "dirty"
    )
    if tamper == "missing_compiler":
        builder_path = factor_root / "m6b_builder_summary.json"
        builder = json.loads(builder_path.read_text(encoding="utf-8"))
        builder["runtime_identity"]["compiler"] = None
        builder_path.write_text(
            json.dumps(runner._attach_evidence(builder)), encoding="utf-8"
        )
    _patch_factor_authority(monkeypatch, tmp_path)
    with pytest.raises(ValueError):
        runner._m6b_w16a_factor_authority(manifest_path)


def test_w16a_worker_binds_runtime_cache_refresh_and_final_audits():
    source = inspect.getsource(runner._run_m6b_w16a_diagnostic)
    legacy_start = source.index(
        'action_audit["lifecycle_events"].append("auxiliary_constructed")',
        source.index("core_result = w16b_result"),
    )
    legacy = source[legacy_start:]
    assert 'factor_authority["factor_compiler"]' in source
    assert "_m6b_w6a_runtime_valid(runtime, frozen_compiler=frozen_compiler)" in source
    assert "runtime: dict[str, Any] | None = None" not in source
    assert source.count("runtime = _m6b_runtime_identity(") == 1
    assert "local_pc.apply_count" not in source
    assert "source_cache_final = _m6b_w2_cache_record(h2b, jit_cache_source)" in source
    assert '"target_final": cache_final' in source
    assert "source_git_unchanged" in source
    assert legacy.index(
        "physical_audit = h2a._jsonable(physical_action.audit)"
    ) > legacy.index("measurements = [")
    assert 'bridge_audit["forward_apply_count"] == 2' in source
    assert 'shifted_action_final_audit["apply_count"] == 82' in source
    assert legacy.index("shifted_action_final_audit =") < legacy.index(
        "shifted_action.destroy()"
    )
    assert 'action_audit["shifted_action_total_count"]' in source
    assert "local_exact_shifted_count = (" in source
    assert "global_shifted_count + local_pc_count" in source
    assert "shifted_epsilon" in source
    assert "physical_epsilon" in source
    assert legacy.index("shifted_epsilon,") < legacy.index(
        'emit("auxiliary_released")'
    )
    assert legacy.index("physical_epsilon,") < legacy.index(
        'action_audit["lifecycle_events"].append("physical_released")'
    )
    assert "W16A_EXECUTION_OR_EVIDENCE_FAIL" in source


def test_w16a_final_classification_separates_numeric_and_evidence_failure():
    checks = {
        name: True
        for name in (
            "schema",
            "fixed_identity",
            "inner_audits",
            "inner_records",
            "inner_residual",
            "z_identity",
            "p_identity",
            "measurements",
            "action_counts",
            "architecture",
            "lifecycle",
            "prediction",
            "source",
            "cache",
            "execution",
        )
    }
    assert runner._m6b_w16a_final_status(checks, None)[2] == (
        "W16A_GLOBAL_SHIFTED_INNER_PASS"
    )
    checks["inner_residual"] = False
    assert runner._m6b_w16a_final_status(checks, None)[2] == (
        "W16A_GLOBAL_SHIFTED_INNER_NUMERIC_FAIL"
    )
    checks["architecture"] = False
    assert runner._m6b_w16a_final_status(checks, None)[2] == (
        "W16A_EXECUTION_OR_EVIDENCE_FAIL"
    )
    incomplete = {"inner_residual": False, "measurements": False}
    assert runner._m6b_w16a_final_status(incomplete, None)[2] == (
        "W16A_EXECUTION_OR_EVIDENCE_FAIL"
    )
    assert runner._m6b_w16a_final_status(
        {"inner_residual": True, "measurements": True}, None
    )[2] == "W16A_EXECUTION_OR_EVIDENCE_FAIL"
