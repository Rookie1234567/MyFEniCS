from __future__ import annotations

import json
import os
from pathlib import Path
import stat
from typing import Any

import pytest

import benchmarks.task035e_campaign_bootstrap as bootstrap
import benchmarks.task035e_trial_metadata as trial_metadata
from benchmarks.run_task033_full3d_watchdog import _parse_args as watchdog_args
from benchmarks.task035e_campaign_bootstrap import (
    BOOTSTRAP_SCHEMA,
    CampaignBootstrapError,
    load_campaign_bootstrap_manifest,
    main,
    write_campaign_bootstrap,
)
from benchmarks.task035e_campaign_handlers import _parser as handler_parser


SOURCE_SHA = "a" * 40


def _clean_state(source_sha: str = SOURCE_SHA) -> dict[str, Any]:
    return {
        "repo_root": str(bootstrap.ROOT),
        "head_sha": source_sha,
        "status_lines": (),
    }


def _mock_clean_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        bootstrap,
        "_git_source_state",
        lambda: _clean_state(),
    )
    monkeypatch.setattr(
        trial_metadata,
        "_git_source_state",
        lambda: _clean_state(),
    )


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def _formal_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
) -> Path:
    artifacts = tmp_path / "benchmarks" / "artifacts"
    artifacts.mkdir(parents=True)
    artifacts.chmod(0o700)
    formal_root = artifacts / "task035e"
    monkeypatch.setattr(
        bootstrap,
        "FORMAL_ARTIFACT_ROOT",
        formal_root,
    )
    monkeypatch.setattr(
        bootstrap,
        "_git_path_is_ignored",
        lambda _path: True,
    )
    return formal_root / name


def test_bootstrap_closes_two_private_paths_and_handler_argv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_clean_source(monkeypatch)
    output_root = _formal_output(
        tmp_path,
        monkeypatch,
        "formal-bootstrap",
    )
    receipt = write_campaign_bootstrap(
        output_root,
        verified_clean_source_sha=SOURCE_SHA,
    )
    manifest = load_campaign_bootstrap_manifest(
        receipt.manifest_path
    )

    assert manifest["schema_version"] == BOOTSTRAP_SCHEMA
    assert manifest["source_sha"] == SOURCE_SHA
    assert manifest["abi_sha256"] == receipt.abi_sha256
    assert manifest["formal_mpi_size"] == 8
    assert manifest["maximum_cycles"] == 6
    assert manifest["source_clean_verified"] is True
    assert manifest["source_stable_during_bootstrap"] is True
    assert manifest["abi_stable_during_bootstrap"] is True
    assert manifest["protected_inputs_consumed"] is False
    assert manifest["pde_executed"] is False
    assert manifest["ordinary_default_changed"] is False
    assert [row["path_id"] for row in manifest["paths"]] == ["A", "B"]
    assert [row["nominal_h_nm"] for row in manifest["paths"]] == [
        20.0,
        15.0,
    ]
    assert _mode(output_root) == 0o700
    assert _mode(receipt.manifest_path) == 0o600

    for row in manifest["paths"]:
        for key in (
            "initial_plan_path",
            "initial_space_authority_path",
            "qualified_solver_config_path",
        ):
            assert _mode(Path(row[key])) == 0o600
    runtime = manifest["runtime"]
    for key in (
        "campaign_root",
        "artifact_root",
        "tensor_cache_directory",
    ):
        assert _mode(Path(runtime[key])) == 0o700
    assert _mode(Path(runtime["campaign_identity_path"])) == 0o600
    assert _mode(Path(runtime["campaign_root"]) / "receipts") == 0o700
    assert _mode(Path(runtime["campaign_root"]) / "attempts") == 0o700

    argv = manifest["handler"]["argv"]
    assert tuple(argv) == receipt.handler_argv
    assert argv[:3] == [
        os.path.abspath(os.sys.executable),
        "-m",
        "benchmarks.task035e_campaign_handlers",
    ]
    assert argv[0].endswith("/.venv/bin/python")
    parsed = handler_parser().parse_args(argv[3:])
    assert parsed.source_sha == SOURCE_SHA
    assert parsed.abi_sha256 == receipt.abi_sha256
    assert parsed.path_a_trial_id == "task035e-blind-path-a"
    assert parsed.path_b_trial_id == "task035e-blind-path-b"
    assert parsed.maximum_new_stages is None


def test_bootstrap_refuses_overwrite_before_reprobing_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_clean_source(monkeypatch)
    output_root = _formal_output(
        tmp_path,
        monkeypatch,
        "formal-bootstrap",
    )
    write_campaign_bootstrap(
        output_root,
        verified_clean_source_sha=SOURCE_SHA,
    )
    monkeypatch.setattr(
        bootstrap,
        "_git_source_state",
        lambda: pytest.fail("overwrite must fail before a source probe"),
    )
    with pytest.raises(FileExistsError):
        write_campaign_bootstrap(
            output_root,
            verified_clean_source_sha=SOURCE_SHA,
        )


def test_bootstrap_preserves_partial_evidence_on_source_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    states = iter(
        (
            _clean_state(),
            {
                **_clean_state(),
                "status_lines": (" M tracked-file.py",),
            },
        )
    )
    monkeypatch.setattr(
        bootstrap,
        "_git_source_state",
        lambda: next(states),
    )
    monkeypatch.setattr(
        trial_metadata,
        "_git_source_state",
        lambda: _clean_state(),
    )
    output_root = _formal_output(
        tmp_path,
        monkeypatch,
        "source-drift",
    )
    with pytest.raises(
        CampaignBootstrapError,
        match="source identity after campaign bootstrap",
    ):
        write_campaign_bootstrap(
            output_root,
            verified_clean_source_sha=SOURCE_SHA,
        )
    assert output_root.is_dir()
    assert (
        output_root / "inputs/path-a/initial-plan.json"
    ).is_file()
    assert not (output_root / bootstrap.MANIFEST_NAME).exists()


def test_bootstrap_preserves_partial_evidence_on_abi_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_clean_source(monkeypatch)
    identities = iter(("b" * 64, "c" * 64))
    monkeypatch.setattr(
        bootstrap,
        "live_qualified_abi_sha256",
        lambda: next(identities),
    )
    output_root = _formal_output(
        tmp_path,
        monkeypatch,
        "abi-drift",
    )
    with pytest.raises(
        CampaignBootstrapError,
        match="qualified ABI identity changed",
    ):
        write_campaign_bootstrap(
            output_root,
            verified_clean_source_sha=SOURCE_SHA,
        )
    assert output_root.is_dir()
    assert (
        output_root / "runtime/campaign/campaign.json"
    ).is_file()
    assert not (output_root / bootstrap.MANIFEST_NAME).exists()


@pytest.mark.parametrize(
    "output_root",
    (
        bootstrap.ROOT / "forbidden-bootstrap-output",
        bootstrap.ROOT / "docs" / "forbidden-bootstrap-output",
        bootstrap.ROOT
        / "benchmarks"
        / "cases"
        / "forbidden-bootstrap-output",
    ),
)
def test_bootstrap_rejects_nonartifact_repository_outputs(
    output_root: Path,
) -> None:
    with pytest.raises(CampaignBootstrapError, match="direct child"):
        write_campaign_bootstrap(
            output_root,
            verified_clean_source_sha=SOURCE_SHA,
        )


def test_bootstrap_rejects_windows_mount_output() -> None:
    with pytest.raises(
        CampaignBootstrapError,
        match="WSL Linux filesystem",
    ):
        write_campaign_bootstrap(
            Path("/mnt/c/task035e-forbidden-bootstrap"),
            verified_clean_source_sha=SOURCE_SHA,
        )


def test_formal_artifact_scope_is_git_ignored() -> None:
    candidate = (
        bootstrap.FORMAL_ARTIFACT_ROOT
        / "future-private-bootstrap"
    )
    assert bootstrap._git_path_is_ignored(candidate) is True


def test_bootstrap_rejects_nonignored_formal_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = _formal_output(
        tmp_path,
        monkeypatch,
        "not-ignored",
    )
    monkeypatch.setattr(
        bootstrap,
        "_git_path_is_ignored",
        lambda _path: False,
    )
    with pytest.raises(
        CampaignBootstrapError,
        match="not Git-ignored",
    ):
        write_campaign_bootstrap(
            output_root,
            verified_clean_source_sha=SOURCE_SHA,
        )
    assert not output_root.exists()


def test_bootstrap_cli_fails_closed_without_creating_invalid_root(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output_root = tmp_path / "invalid-source"
    assert (
        main(
            [
                "--output-root",
                str(output_root),
                "--verified-clean-sha",
                "not-a-source-sha",
            ]
        )
        == 2
    )
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "failed"
    assert report["pde_executed"] is False
    assert report["ordinary_default_changed"] is False
    assert not output_root.exists()


def test_task035e_formal_features_remain_explicit_opt_ins() -> None:
    ordinary = watchdog_args(["--degree", "3"])
    assert ordinary.task035e_reference_certifier_gate is False
    assert ordinary.task035e_blind_candidate_gate is False
    assert ordinary.stage4_raw_tensor_cache is False
    assert ordinary.stage4_variable_p_cell_degree_plan is None
    assert ordinary.stage4_local_h_refinement_plan is None
    assert ordinary.stage4_full3d_assembly_backend == "standard_full"
    assert ordinary.run_kind == "assembly-only"
