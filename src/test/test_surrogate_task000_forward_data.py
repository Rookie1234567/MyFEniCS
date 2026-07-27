from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.forward_data import forward_model
from src.forward_data.forward_model import ForwardModel
from src.forward_data.schema import ForwardParameters, RunConfig, parameter_catalog
from src.forward_data.provenance import validate_dataset_identity


def _identity(root: Path, *, dirty: bool = True) -> dict[str, object]:
    return {
        "repository_root": str(root),
        "origin": "https://github.com/Rookie1234567/MyFEniCS.git",
        "branch": "codex/only-one-13p5nm-surrogate-inversion",
        "upstream": "origin/codex/only-one-13p5nm-surrogate-inversion",
        "source_sha": "a" * 40,
        "dirty": dirty,
        "status": "M task" if dirty else "",
    }


def _patch_preflight(
    monkeypatch: pytest.MonkeyPatch, root: Path, *, dirty: bool = True
) -> None:
    monkeypatch.setattr(
        forward_model, "source_identity", lambda value: _identity(value, dirty=dirty)
    )
    monkeypatch.setattr(
        forward_model, "_abi_identity", lambda value: {"checks": {"pass": True}}
    )
    monkeypatch.setattr(
        forward_model,
        "_resource_identity",
        lambda value, model_id: {"mem_available_bytes": 16 * 1024**3},
    )


def test_schema_is_fixed_to_real_tracked_presets() -> None:
    catalog = parameter_catalog()
    assert catalog["physics"]["wavelength_nm"]["allowed"] == [13.5]
    assert catalog["execution"]["mpi_ranks"]["allowed"] == [1]
    assert "invertible variable" in catalog["note"]
    with pytest.raises(ValueError, match="only wavelength"):
        ForwardParameters("euv_2d_complex_absorption_v1", 14.0).validate()
    with pytest.raises(ValueError, match="unsupported parameter fields"):
        ForwardParameters.from_mapping({"model_id": "euv_2d_complex_absorption_v1", "fake": 1})


def test_dry_run_writes_hashed_three_record_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    _patch_preflight(monkeypatch, root)
    output = root / "artifacts"
    result = ForwardModel(root).evaluate(
        ForwardParameters("euv_2d_complex_absorption_v1"),
        RunConfig(output=output, dry_run=True),
    )
    assert result.status == "dry_run_pass"
    assert result.return_code == 0
    manifest = json.loads(result.manifest_path.read_text())
    assert set(manifest["artifact_hashes"]) == {"raw_record.json", "compact_record.json"}
    assert (result.run_directory / "raw_record.json").is_file()
    assert (result.run_directory / "compact_record.json").is_file()


def test_formal_sample_fails_closed_on_dirty_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    _patch_preflight(monkeypatch, root)
    with pytest.raises(RuntimeError, match="clean source"):
        ForwardModel(root).evaluate(
            ForwardParameters("euv_3d_target_grating_v1"),
            RunConfig(output=root / "artifacts", dry_run=True, formal=True),
        )


def test_run_config_rejects_parallel_forward_solves(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="one serial"):
        RunConfig(output=tmp_path.resolve(), mpi_ranks=2).validate()


def test_2d_observables_select_authoritative_auxiliary_metrics() -> None:
    summaries = [{"record": [{
        "reduced_linear_residual": 2.0e-14,
        "power_metrics": {"R_total": 0.1, "T_total": 0.7, "A_balance": 0.2},
        "dtn_auxiliary_power_metrics": {
            "R_total": 0.01, "T_total": 0.79,
            "A_balance": 0.20, "A_volume": 0.20,
        },
    }]}]
    selected = forward_model._extract_observables(
        summaries, "euv_2d_complex_absorption_v1"
    )
    assert selected["R_total"] == 0.01
    assert selected["T_total"] == 0.79
    assert selected["true_residual"] == 2.0e-14


def test_dataset_identity_rejects_mixed_source_and_dirty_records() -> None:
    base = {
        "source": {"source_sha": "a" * 40, "dirty": False},
        "parameter_schema_version": "parameters.v1",
        "observable_schema_version": "observables.v1",
    }
    assert validate_dataset_identity([base, dict(base)])["source_sha"] == "a" * 40
    dirty = {**base, "source": {"source_sha": "a" * 40, "dirty": True}}
    with pytest.raises(ValueError, match="mix source"):
        validate_dataset_identity([base, dirty])
    other = {**base, "source": {"source_sha": "b" * 40, "dirty": False}}
    with pytest.raises(ValueError, match="mix source"):
        validate_dataset_identity([base, other])
