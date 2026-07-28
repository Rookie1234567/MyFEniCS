from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import stat
from typing import Any, Mapping

import pytest

import benchmarks.task035e_trial_metadata as trial_metadata
from benchmarks.task035e_initial_space import write_initial_space_bundle
from benchmarks.task035e_trial_metadata import (
    QUALIFIED_SOLVER_CONFIG_SCHEMA,
    TRIAL_ALGORITHM_ID,
    TRIAL_MAXIMUM_CYCLES,
    TRIAL_METADATA_SCHEMA,
    TrialMetadataError,
    load_qualified_solver_config,
    load_trial_metadata,
    main,
    write_qualified_solver_config,
    write_trial_metadata,
)
from src.common.config_3d import (
    ASSEMBLY_TIME_VARIABLE_P_CONDENSED_BACKEND,
    target_stage4_config,
)


SOURCE_SHA = "a" * 40
FULL_SOLVE_PLANES_NM = (10.0, 30.0, 60.0, 90.0, 110.0)


def _json_sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _private_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            payload,
            sort_keys=True,
            indent=2,
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _config_authority(
    *,
    plan_path: Path,
    source_sha: str,
    path_id: str,
) -> dict[str, Any]:
    h_nm = {"A": 20.0, "B": 15.0}[path_id]
    config = replace(
        target_stage4_config(degree=6, h_nm=h_nm),
        polarization_kind="s",
        custom_polarization=None,
        stage4_full3d_assembly_backend=(
            ASSEMBLY_TIME_VARIABLE_P_CONDENSED_BACKEND
        ),
        stage4_local_h_refinement_plan=str(plan_path.resolve()),
        matrix_diagnostics_assemble_only=False,
        matrix_diagnostics_factorization_only=False,
        full3d_reference_export=True,
        full3d_reference_plane_z=FULL_SOLVE_PLANES_NM,
        full3d_reference_sample_count_x=40,
        full3d_reference_sample_count_y=20,
        unique_output=False,
    ).as_jsonable()
    unsigned = {
        "schema_version": QUALIFIED_SOLVER_CONFIG_SCHEMA,
        "status": "qualified",
        "pass": True,
        "source_sha": source_sha,
        "formal_mpi_size": 8,
        "run_kind": "full-solve",
        "output_role": "blind_current_solve",
        "cycle_index": 0,
        "assembly_backend": (
            ASSEMBLY_TIME_VARIABLE_P_CONDENSED_BACKEND
        ),
        "initial_plan_file_sha256": _file_sha(plan_path),
        "source_clean_verified": True,
        "source_stable_during_run": True,
        "qualified_activation": True,
        "petsc_scalar_type": "complex128",
        "petsc_int_type": "int32",
        "ordinary_default_changed": False,
        "config": config,
        "config_payload_sha256": _json_sha(config),
    }
    return {
        **unsigned,
        "authority_payload_sha256": _json_sha(unsigned),
    }


def _refresh_config_authority(payload: dict[str, Any]) -> None:
    payload["config_payload_sha256"] = _json_sha(payload["config"])
    unsigned = dict(payload)
    unsigned.pop("authority_payload_sha256", None)
    payload["authority_payload_sha256"] = _json_sha(unsigned)


def _bundle(
    tmp_path: Path,
    *,
    path_id: str = "A",
) -> tuple[Path, Path, Path]:
    plan_path = tmp_path / "inputs" / "initial-plan.json"
    authority_path = tmp_path / "inputs" / "initial-authority.json"
    write_initial_space_bundle(
        path_id=path_id,
        source_sha=SOURCE_SHA,
        plan_path=plan_path,
        authority_path=authority_path,
        mpi_size=8,
    )
    config_path = tmp_path / "inputs" / "solver-config.json"
    _private_json(
        config_path,
        _config_authority(
            plan_path=plan_path,
            source_sha=SOURCE_SHA,
            path_id=path_id,
        ),
    )
    return plan_path, authority_path, config_path


def _write(
    tmp_path: Path,
    *,
    plan_path: Path,
    authority_path: Path,
    config_path: Path,
) -> Path:
    output = tmp_path / "output" / "trial.json"
    write_trial_metadata(
        output,
        initial_plan_path=plan_path,
        initial_space_authority_path=authority_path,
        qualified_solver_config_path=config_path,
    )
    return output


def _clean_source_state(
    source_sha: str = SOURCE_SHA,
) -> dict[str, Any]:
    return {
        "repo_root": str(trial_metadata.ROOT),
        "head_sha": source_sha,
        "status_lines": (),
    }


def _qualified_config_from_producer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    path_id: str = "A",
) -> tuple[Path, Path]:
    plan, _authority, _manual_config = _bundle(
        tmp_path,
        path_id=path_id,
    )
    monkeypatch.setattr(
        trial_metadata,
        "_git_source_state",
        lambda: _clean_source_state(),
    )
    output = tmp_path / "qualified" / "solver-config.json"
    write_qualified_solver_config(
        output,
        initial_plan_path=plan,
        verified_clean_source_sha=SOURCE_SHA,
        path_id=path_id,
    )
    return plan, output


@pytest.mark.parametrize(
    ("path_id", "h_nm"),
    (
        ("A", 20.0),
        ("B", 15.0),
    ),
)
def test_qualified_solver_config_producer_closes_cycle0_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    path_id: str,
    h_nm: float,
) -> None:
    plan, output = _qualified_config_from_producer(
        tmp_path,
        monkeypatch,
        path_id=path_id,
    )
    payload = load_qualified_solver_config(
        output,
        initial_plan_path=plan,
        verified_clean_source_sha=SOURCE_SHA,
        path_id=path_id,
    )
    config = payload["config"]
    assert payload["schema_version"] == QUALIFIED_SOLVER_CONFIG_SCHEMA
    assert payload["source_clean_verified"] is True
    assert payload["source_stable_during_run"] is True
    assert payload["qualified_activation"] is True
    assert payload["formal_mpi_size"] == 8
    assert payload["output_role"] == "blind_current_solve"
    assert payload["cycle_index"] == 0
    assert payload["ordinary_default_changed"] is False
    assert config["mesh_target_size"] == h_nm
    assert config["nedelec_degree"] == 6
    assert config["petsc_direct_solver_profile"] == "default"
    assert config["stage4_variable_p_cell_degree_plan"] is None
    assert (
        config["stage4_local_h_refinement_plan"]
        == str(plan.resolve())
    )
    assert config["matrix_diagnostics_assemble_only"] is False
    assert config["matrix_diagnostics_factorization_only"] is False
    assert config["full3d_reference_export"] is True
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    with pytest.raises(FileExistsError):
        write_qualified_solver_config(
            output,
            initial_plan_path=plan,
            verified_clean_source_sha=SOURCE_SHA,
            path_id=path_id,
        )


def test_qualified_solver_config_rejects_abi_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan, _authority, _config = _bundle(tmp_path)
    monkeypatch.setattr(
        trial_metadata,
        "_git_source_state",
        lambda: _clean_source_state(),
    )
    live = dict(trial_metadata._qualified_abi_preflight())
    live["petsc_int_type"] = "int64"
    live["mpi4py_module_path"] = r"C:\Python\mpi4py.pyd"
    monkeypatch.setattr(
        trial_metadata,
        "_qualified_abi_preflight",
        lambda: live,
    )
    with pytest.raises(TrialMetadataError, match="ABI gate failed"):
        write_qualified_solver_config(
            tmp_path / "qualified" / "solver-config.json",
            initial_plan_path=plan,
            verified_clean_source_sha=SOURCE_SHA,
            path_id="A",
        )


def test_qualified_solver_config_rejects_plan_path_and_mode_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan, _authority, _config = _bundle(tmp_path, path_id="A")
    monkeypatch.setattr(
        trial_metadata,
        "_git_source_state",
        lambda: _clean_source_state(),
    )
    with pytest.raises(TrialMetadataError, match="source/Path B"):
        write_qualified_solver_config(
            tmp_path / "qualified-b" / "solver-config.json",
            initial_plan_path=plan,
            verified_clean_source_sha=SOURCE_SHA,
            path_id="B",
        )

    plan.chmod(0o644)
    with pytest.raises(TrialMetadataError, match="mode 0600"):
        write_qualified_solver_config(
            tmp_path / "qualified-mode" / "solver-config.json",
            initial_plan_path=plan,
            verified_clean_source_sha=SOURCE_SHA,
            path_id="A",
        )
    plan.chmod(0o600)
    plan_payload = json.loads(plan.read_text(encoding="utf-8"))
    plan_payload["trace_degree"] = 5
    _private_json(plan, plan_payload)
    with pytest.raises(TrialMetadataError, match="does not replay"):
        write_qualified_solver_config(
            tmp_path / "qualified-plan" / "solver-config.json",
            initial_plan_path=plan,
            verified_clean_source_sha=SOURCE_SHA,
            path_id="A",
        )


def test_qualified_solver_config_rejects_source_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan, _authority, _config = _bundle(tmp_path)
    dirty = _clean_source_state()
    dirty["status_lines"] = (" M src/common/config_3d.py",)
    monkeypatch.setattr(
        trial_metadata,
        "_git_source_state",
        lambda: dirty,
    )
    with pytest.raises(TrialMetadataError, match="clean source identity"):
        write_qualified_solver_config(
            tmp_path / "qualified-dirty" / "solver-config.json",
            initial_plan_path=plan,
            verified_clean_source_sha=SOURCE_SHA,
            path_id="A",
        )

    states = iter(
        (
            _clean_source_state(),
            _clean_source_state("b" * 40),
        )
    )
    monkeypatch.setattr(
        trial_metadata,
        "_git_source_state",
        lambda: next(states),
    )
    with pytest.raises(TrialMetadataError, match="after.*clean source"):
        write_qualified_solver_config(
            tmp_path / "qualified-changing" / "solver-config.json",
            initial_plan_path=plan,
            verified_clean_source_sha=SOURCE_SHA,
            path_id="A",
        )

    monkeypatch.setattr(
        trial_metadata,
        "_git_source_state",
        lambda: _clean_source_state("b" * 40),
    )
    with pytest.raises(TrialMetadataError, match="source/Path A"):
        write_qualified_solver_config(
            tmp_path / "qualified-source" / "solver-config.json",
            initial_plan_path=plan,
            verified_clean_source_sha="b" * 40,
            path_id="A",
        )


def test_qualified_solver_config_loader_rejects_config_tamper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan, output = _qualified_config_from_producer(
        tmp_path,
        monkeypatch,
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    payload["config"]["petsc_direct_solver_profile"] = "mumps_ooc"
    _refresh_config_authority(payload)
    _private_json(output, payload)
    with pytest.raises(
        TrialMetadataError,
        match="complete cycle-0 configuration",
    ):
        load_qualified_solver_config(
            output,
            initial_plan_path=plan,
            verified_clean_source_sha=SOURCE_SHA,
            path_id="A",
        )


@pytest.mark.parametrize(
    ("path_id", "trial_id", "initial_path_id"),
    (
        ("A", "task035e-blind-path-a", "path-A-h20"),
        ("B", "task035e-blind-path-b", "path-B-h15"),
    ),
)
def test_trial_metadata_replays_both_initial_paths(
    tmp_path: Path,
    path_id: str,
    trial_id: str,
    initial_path_id: str,
) -> None:
    plan, authority, config = _bundle(tmp_path, path_id=path_id)
    output = _write(
        tmp_path,
        plan_path=plan,
        authority_path=authority,
        config_path=config,
    )
    payload = load_trial_metadata(output)
    identity = {
        name: payload[name]
        for name in (
            "geometry_sha256",
            "material_sha256",
            "incident_sha256",
            "dtn_definition_sha256",
            "postprocessing_sha256",
            "source_sha",
        )
    }
    assert payload["schema_version"] == TRIAL_METADATA_SCHEMA
    assert payload["trial_id"] == trial_id
    assert payload["algorithm_id"] == TRIAL_ALGORITHM_ID
    assert payload["initial_path_id"] == initial_path_id
    assert payload["maximum_cycles"] == TRIAL_MAXIMUM_CYCLES
    assert payload["physical_identity_sha256"] == _json_sha(identity)
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    with pytest.raises(FileExistsError):
        write_trial_metadata(
            output,
            initial_plan_path=plan,
            initial_space_authority_path=authority,
            qualified_solver_config_path=config,
        )


def test_trial_metadata_rejects_rehashed_physical_config_drift(
    tmp_path: Path,
) -> None:
    plan, authority, config = _bundle(tmp_path)
    payload = json.loads(config.read_text(encoding="utf-8"))
    payload["config"]["period_x"] = 51.0
    _refresh_config_authority(payload)
    _private_json(config, payload)
    with pytest.raises(
        TrialMetadataError,
        match="fixed grating|qualified target",
    ):
        _write(
            tmp_path,
            plan_path=plan,
            authority_path=authority,
            config_path=config,
        )


def test_trial_metadata_rejects_plan_and_authority_tamper(
    tmp_path: Path,
) -> None:
    plan, authority, config = _bundle(tmp_path)
    payload = json.loads(plan.read_text(encoding="utf-8"))
    payload["trace_degree"] = 5
    _private_json(plan, payload)
    with pytest.raises(TrialMetadataError, match="does not replay"):
        _write(
            tmp_path,
            plan_path=plan,
            authority_path=authority,
            config_path=config,
        )


def test_trial_metadata_rejects_source_and_path_drift(
    tmp_path: Path,
) -> None:
    plan, authority, config = _bundle(tmp_path)
    payload = json.loads(config.read_text(encoding="utf-8"))
    payload["source_sha"] = "b" * 40
    payload["config"]["mesh_target_size"] = 15.0
    _refresh_config_authority(payload)
    _private_json(config, payload)
    with pytest.raises(TrialMetadataError, match="authority gate differs"):
        _write(
            tmp_path,
            plan_path=plan,
            authority_path=authority,
            config_path=config,
        )

    payload["source_sha"] = SOURCE_SHA
    _refresh_config_authority(payload)
    _private_json(config, payload)
    with pytest.raises(
        TrialMetadataError,
        match="discretization/lifecycle",
    ):
        _write(
            tmp_path,
            plan_path=plan,
            authority_path=authority,
            config_path=config,
        )


def test_trial_metadata_rejects_nonprivate_and_symlink_inputs(
    tmp_path: Path,
) -> None:
    plan, authority, config = _bundle(tmp_path)
    config.chmod(0o644)
    with pytest.raises(TrialMetadataError, match="mode 0600"):
        _write(
            tmp_path,
            plan_path=plan,
            authority_path=authority,
            config_path=config,
        )
    config.chmod(0o600)

    link = tmp_path / "inputs" / "solver-config-link.json"
    link.symlink_to(config)
    with pytest.raises(TrialMetadataError, match="symlink"):
        _write(
            tmp_path,
            plan_path=plan,
            authority_path=authority,
            config_path=link,
        )


def test_trial_metadata_rejects_open_config_and_identity_tamper(
    tmp_path: Path,
) -> None:
    plan, authority, config = _bundle(tmp_path)
    payload = json.loads(config.read_text(encoding="utf-8"))
    payload["physical_identity_sha256"] = "f" * 64
    unsigned = dict(payload)
    unsigned.pop("authority_payload_sha256")
    payload["authority_payload_sha256"] = _json_sha(unsigned)
    _private_json(config, payload)
    with pytest.raises(TrialMetadataError, match="closed schema"):
        _write(
            tmp_path,
            plan_path=plan,
            authority_path=authority,
            config_path=config,
        )

    del payload["physical_identity_sha256"]
    unsigned = dict(payload)
    unsigned.pop("authority_payload_sha256")
    payload["authority_payload_sha256"] = _json_sha(unsigned)
    _private_json(config, payload)
    output = _write(
        tmp_path,
        plan_path=plan,
        authority_path=authority,
        config_path=config,
    )
    trial = json.loads(output.read_text(encoding="utf-8"))
    trial["physical_identity_sha256"] = "0" * 64
    _private_json(output, trial)
    with pytest.raises(TrialMetadataError, match="self-hash"):
        load_trial_metadata(output)


def test_trial_metadata_rejects_protected_output_and_cli_is_closed(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    plan, authority, config = _bundle(tmp_path)
    protected = tmp_path / "hidden" / "trial.json"
    with pytest.raises(TrialMetadataError, match="protected"):
        write_trial_metadata(
            protected,
            initial_plan_path=plan,
            initial_space_authority_path=authority,
            qualified_solver_config_path=config,
        )

    output = tmp_path / "cli" / "trial.json"
    assert (
        main(
            [
                "--initial-plan",
                str(plan),
                "--initial-space-authority",
                str(authority),
                "--qualified-solver-config",
                str(config),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["status"] == "completed"
    assert receipt["file_sha256"] == _file_sha(output)


def test_trial_metadata_rejects_input_symlink_even_with_private_target(
    tmp_path: Path,
) -> None:
    plan, authority, config = _bundle(tmp_path)
    plan_link = tmp_path / "inputs" / "plan-link.json"
    os.symlink(plan, plan_link)
    with pytest.raises(TrialMetadataError, match="symlink"):
        _write(
            tmp_path,
            plan_path=plan_link,
            authority_path=authority,
            config_path=config,
        )
