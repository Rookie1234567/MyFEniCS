"""Focused T1 contracts for the unconnected Full3D iterative profile."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from scripts.run_case import main as run_case_main
from src.io import load_and_resolve
from src.io.execution_plan import (
    build_execution_plan,
    method_adapter_available,
    method_adapter_identity,
)
from src.io.input_loader import InputError
from src.io.resolved_config import canonical_json_bytes, resolved_config_bytes
from src.runners.task038_full3d_iterative import run_full3d_iterative
from src.runners.task038_input_worker import (
    _dispatch_resolved_payload,
    validate_worker_contract,
)


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "input/templates/full3d_iterative_example.dat"
ORDINARY = ROOT / "input/templates/ordinary_2d_example.dat"


def _variant(tmp_path: Path, name: str, replacements: tuple[tuple[str, str], ...]) -> Path:
    text = TEMPLATE.read_text(encoding="utf-8")
    for old, new in replacements:
        assert old in text
        text = text.replace(old, new, 1)
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def _worker_kwargs(tmp_path: Path) -> dict[str, object]:
    specification = load_and_resolve(
        ROOT / "input/templates/full3d_direct_example.dat"
    )
    run_directory = tmp_path / "worker"
    run_directory.mkdir()
    resolved_bytes = resolved_config_bytes(specification)
    resolved_path = run_directory / "resolved_config.json"
    resolved_path.write_bytes(resolved_bytes)
    input_path = run_directory / "input_original.dat"
    input_path.write_bytes(specification.raw_input_bytes)
    resolved_sha = hashlib.sha256(resolved_bytes).hexdigest()
    snapshot = specification.as_jsonable()
    source_sha = "a" * 40
    mpi_size = specification.execution["mpi_size"]
    manifest = {
        "model_id": snapshot["model_id"],
        "run_id": snapshot["run_id"],
        "comparison_group": snapshot["comparison_group"],
        "input_path": snapshot["provenance"]["source_path"],
        "method": "full3d_direct",
        "solver": snapshot["solver"],
        "mpi_size": mpi_size,
        "requested_modes": None,
        "input_sha256": specification.input_sha256,
        "physical_model_sha256": specification.physical_model_sha256,
        "source_sha": source_sha,
        "resolved_config_sha256": resolved_sha,
        "resolved_method_adapter": method_adapter_identity("full3d_direct"),
        "output_directory": str(run_directory),
        "numerical_output_directory": str(run_directory / "numerical_output"),
    }
    manifest_path = run_directory / "run_manifest.json"
    manifest_path.write_bytes(canonical_json_bytes(manifest) + b"\n")
    return {
        "resolved_config": resolved_path,
        "manifest": manifest_path,
        "expected_input_sha256": specification.input_sha256,
        "expected_physical_model_sha256": specification.physical_model_sha256,
        "expected_source_sha": source_sha,
        "expected_mpi_size": mpi_size,
        "expected_method": "full3d_direct",
        "expected_adapter": method_adapter_identity("full3d_direct"),
        "expected_output_directory": run_directory,
        "expected_resolved_config_sha256": resolved_sha,
        "actual_mpi_size": mpi_size,
        "contract_probe": False,
    }


def test_full3d_iterative_profile_is_explicit_and_strategic_limits_are_distinct(
    tmp_path: Path,
):
    specification = load_and_resolve(TEMPLATE)
    assert specification.method["kind"] == "full3d_iterative"
    assert specification.solver["restart"] == 20
    assert specification.solver["max_iterations"] == 200
    assert specification.derived["full3d_iterative_resource_profile"] == {
        "strategic_memory_limit_gb": 2.0,
        "watchdog_warning_memory_gib": 10.0,
        "watchdog_terminate_memory_gib": 12.0,
        "formal_physics_wavelength_nm": 13.5,
    }
    extended = _variant(
        tmp_path,
        "task038_full3d_iterative_extended.dat",
        (("max_iterations = 200", "max_iterations = 240"),),
    )
    assert load_and_resolve(extended).solver["max_iterations"] == 240
    assert method_adapter_available("full3d_iterative") is False
    assert method_adapter_identity("full3d_iterative") == "task038.full3d_iterative"


@pytest.mark.parametrize(
    ("replacements", "message"),
    (
        (
            ((
                'preconditioner = "full3d_scalable_v1"',
                'preconditioner = "unknown"',
            ),),
            "solver.preconditioner",
        ),
        (
            (("linear_solver = \"iterative\"", "linear_solver = \"fgmres\""),),
            "full3d_iterative requires iterative",
        ),
        (
            (("max_iterations = 200", "max_iterations = 199"),),
            "max_iterations>=200",
        ),
        (
            (("wavelength_nm = 13.5", "wavelength_nm = 0.7"),),
            "0.7 nm full-PDE is not authorized",
        ),
    ),
)
def test_full3d_iterative_cross_field_contracts_fail_closed(
    tmp_path: Path, replacements: tuple[tuple[str, str], ...], message: str
):
    path = _variant(tmp_path, "invalid.dat", replacements)
    with pytest.raises(InputError, match=message):
        load_and_resolve(path)


def test_validate_only_and_dry_run_do_not_launch_numerical_adapter(capsys):
    assert run_case_main([str(TEMPLATE), "--validate-only"]) == 0
    assert run_case_main([str(TEMPLATE), "--dry-run"]) == 0
    output = capsys.readouterr().out
    assert '"method":"full3d_iterative"' in output
    assert "numerical_output" not in output
    assert load_and_resolve(ORDINARY).method["kind"] == "2d_scattered"


def test_iterative_stub_and_worker_dispatch_are_explicitly_not_connected(tmp_path):
    payload = load_and_resolve(TEMPLATE).as_jsonable()
    result = run_full3d_iterative(payload, tmp_path)
    assert result["passed"] is False
    assert "not connected in T1" in result["errors"][0]
    assert "T2-T5 qualification is required" in result["errors"][0]
    status, errors = _dispatch_resolved_payload(
        payload, expected_method="full3d_iterative", output_directory=tmp_path
    )
    assert status == 4
    assert "not connected in T1" in errors[0]
    plan = build_execution_plan(
        load_and_resolve(TEMPLATE),
        tmp_path / "plan",
        source_sha="b" * 40,
        mpiexec_command="mpiexec",
    )
    assert plan.adapter_available is False


def test_worker_contract_rejects_actual_mpi_mismatch(tmp_path):
    kwargs = _worker_kwargs(tmp_path)
    assert validate_worker_contract(**kwargs) == []
    kwargs["actual_mpi_size"] = kwargs["expected_mpi_size"] + 1
    errors = validate_worker_contract(**kwargs)
    assert "MPI.COMM_WORLD size mismatch" in errors
