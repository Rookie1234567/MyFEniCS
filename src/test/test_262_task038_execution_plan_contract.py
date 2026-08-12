"""Serial contracts for the T3a execution plan and private worker payload."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from src.io import load_and_resolve
from src.io.execution_plan import (
    CONTRACT_PROBE_ADAPTER,
    WORKER_MODULE,
    build_execution_plan,
    dry_run_payload,
    method_adapter_identity,
)
from src.io.input_loader import InputError
from src.io.resolved_config import canonical_json_bytes, resolved_config_bytes
from src.runners.task038_input_worker import validate_worker_contract


ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = {
    "2d_scattered": ROOT / "input/templates/ordinary_2d_example.dat",
    "full3d_direct": ROOT / "input/templates/full3d_direct_example.dat",
    "hybrid_direct": ROOT / "input/templates/hybrid_direct_example.dat",
    "hybrid_iterative": ROOT / "input/templates/hybrid_iterative_example.dat",
}


def _spec(method: str):
    return load_and_resolve(TEMPLATES[method])


def _contract_bundle(tmp_path: Path, method: str = "full3d_direct"):
    specification = _spec(method)
    run_directory = tmp_path / "run"
    run_directory.mkdir()
    resolved_bytes = resolved_config_bytes(specification)
    resolved_path = run_directory / "resolved_config.json"
    resolved_path.write_bytes(resolved_bytes)
    (run_directory / "input_original.dat").write_bytes(specification.raw_input_bytes)
    source_sha = "test-source-sha"
    adapter = method_adapter_identity(method)
    snapshot = specification.as_jsonable()
    resolved_sha = hashlib.sha256(resolved_bytes).hexdigest()
    manifest = {
        "model_id": snapshot["model_id"],
        "run_id": snapshot["run_id"],
        "comparison_group": snapshot["comparison_group"],
        "input_path": snapshot["provenance"]["source_path"],
        "method": method,
        "solver": snapshot["solver"],
        "mpi_size": specification.execution["mpi_size"],
        "requested_modes": snapshot["method"].get("requested_modes_per_direction"),
        "input_sha256": specification.input_sha256,
        "physical_model_sha256": specification.physical_model_sha256,
        "source_sha": source_sha,
        "resolved_config_sha256": resolved_sha,
        "resolved_method_adapter": adapter,
        "output_directory": str(run_directory),
        "numerical_output_directory": str(run_directory / "numerical_output"),
    }
    manifest_path = run_directory / "run_manifest.json"
    manifest_path.write_bytes(canonical_json_bytes(manifest) + b"\n")
    kwargs = {
        "resolved_config": resolved_path,
        "manifest": manifest_path,
        "expected_input_sha256": specification.input_sha256,
        "expected_physical_model_sha256": specification.physical_model_sha256,
        "expected_source_sha": source_sha,
        "expected_mpi_size": specification.execution["mpi_size"],
        "expected_method": method,
        "expected_adapter": adapter,
        "expected_output_directory": run_directory,
        "expected_resolved_config_sha256": resolved_sha,
        "actual_mpi_size": specification.execution["mpi_size"],
        "contract_probe": False,
    }
    return specification, run_directory, kwargs


def test_plan_and_dry_run_cover_all_current_methods_with_connection_status(tmp_path):
    for method, template in TEMPLATES.items():
        specification = load_and_resolve(template)
        payload = dry_run_payload(specification)
        assert payload["method"] == method
        assert payload["mpi_size"] == specification.execution["mpi_size"]
        assert payload["physical_model_sha256"] == specification.physical_model_sha256
        assert payload["resolved_method_adapter"][
            "identity"
        ] == method_adapter_identity(method)
        expected_available = method in {
            "full3d_direct",
            "hybrid_direct",
            "hybrid_iterative",
        }
        assert payload["resolved_method_adapter"]["status"] == (
            "connected" if expected_available else "unavailable"
        )
        assert json.dumps(payload, sort_keys=True) == json.dumps(
            dry_run_payload(specification), sort_keys=True
        )

        plan = build_execution_plan(
            specification,
            tmp_path / method,
            source_sha="source-sha",
            python_executable="/opt/qualified-python",
            mpiexec_command="/opt/mpiexec",
        )
        assert plan.shell is False
        assert plan.adapter_available is expected_available
        assert plan.worker_module == WORKER_MODULE
        assert plan.argv[:6] == (
            "/opt/mpiexec",
            "-n",
            str(specification.execution["mpi_size"]),
            "/opt/qualified-python",
            "-m",
            WORKER_MODULE,
        )
        assert "--mpi-size" not in plan.argv
        assert not any(str(template) in arg for arg in plan.argv)


def test_contract_probe_is_explicit_and_not_a_public_method_override(tmp_path):
    specification = _spec("full3d_direct")
    plan = build_execution_plan(
        specification,
        tmp_path / "probe",
        source_sha="source-sha",
        adapter_identity=CONTRACT_PROBE_ADAPTER,
        contract_probe=True,
        mpiexec_command="mpiexec",
    )
    assert plan.contract_probe is True
    assert plan.adapter_available is True
    assert plan.adapter_identity == CONTRACT_PROBE_ADAPTER
    assert plan.argv[-1] == "--contract-probe"
    with pytest.raises(InputError, match="cannot be overridden"):
        build_execution_plan(
            specification,
            tmp_path / "bad",
            source_sha="source-sha",
            adapter_identity="task038.other",
        )


def test_worker_contract_accepts_matching_resolved_and_manifest(tmp_path):
    _specification, _run_directory, kwargs = _contract_bundle(tmp_path)
    assert validate_worker_contract(**kwargs) == []


@pytest.mark.parametrize(
    ("contract_probe", "adapter", "message"),
    (
        (
            True,
            "task038.full3d_direct",
            "contract-probe mode and adapter identity mismatch",
        ),
        (
            False,
            CONTRACT_PROBE_ADAPTER,
            "contract-probe mode and adapter identity mismatch",
        ),
    ),
)
def test_worker_contract_binds_probe_mode_to_probe_adapter(
    tmp_path, contract_probe, adapter, message
):
    _specification, _run_directory, kwargs = _contract_bundle(tmp_path)
    kwargs["contract_probe"] = contract_probe
    kwargs["expected_adapter"] = adapter
    errors = validate_worker_contract(**kwargs)
    assert message in errors


def test_worker_contract_rejects_spoofed_method_adapter_even_when_manifest_matches(
    tmp_path,
):
    _specification, _run_directory, kwargs = _contract_bundle(tmp_path)
    kwargs["expected_adapter"] = "task038.other"
    manifest_path = kwargs["manifest"]
    manifest = json.loads(manifest_path.read_bytes())
    manifest["resolved_method_adapter"] = kwargs["expected_adapter"]
    manifest_path.write_bytes(canonical_json_bytes(manifest) + b"\n")
    errors = validate_worker_contract(**kwargs)
    assert "adapter identity mismatch with expected method" in errors


@pytest.mark.parametrize(
    ("manifest_field", "value", "message"),
    (
        ("comparison_group", "wrong-group", "comparison group mismatch"),
        ("solver", {"linear_solver": "wrong"}, "solver payload mismatch"),
    ),
)
def test_worker_contract_rejects_manifest_payload_drift(
    tmp_path, manifest_field, value, message
):
    _specification, _run_directory, kwargs = _contract_bundle(tmp_path)
    manifest_path = kwargs["manifest"]
    manifest = json.loads(manifest_path.read_bytes())
    manifest[manifest_field] = value
    manifest_path.write_bytes(canonical_json_bytes(manifest) + b"\n")
    errors = validate_worker_contract(**kwargs)
    assert any(message in error for error in errors)


def test_worker_reads_each_contract_json_once(monkeypatch, tmp_path):
    _specification, _run_directory, kwargs = _contract_bundle(tmp_path)
    original_read_bytes = Path.read_bytes
    resolved_path = Path(kwargs["resolved_config"])
    manifest_path = Path(kwargs["manifest"])
    resolved_reads = []
    manifest_reads = []

    def read_bytes(path):
        if path == resolved_path:
            resolved_reads.append(path)
        if path == manifest_path:
            manifest_reads.append(path)
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", read_bytes)
    assert validate_worker_contract(**kwargs) == []
    assert resolved_reads == [resolved_path]
    assert manifest_reads == [manifest_path]


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("expected_input_sha256", "wrong-input", "input SHA mismatch"),
        (
            "expected_physical_model_sha256",
            "wrong-physical",
            "physical model SHA mismatch",
        ),
        ("expected_source_sha", "wrong-source", "source SHA mismatch"),
        ("expected_mpi_size", 99, "MPI size mismatch"),
        ("actual_mpi_size", 99, "MPI.COMM_WORLD size mismatch"),
        ("expected_method", "hybrid_direct", "method mismatch"),
        ("expected_adapter", "task038.other", "adapter identity mismatch"),
        ("expected_output_directory", "/wrong/run", "output directory mismatch"),
        ("expected_resolved_config_sha256", "wrong-resolved", "resolved config SHA"),
    ),
)
def test_worker_contract_rejects_identity_mismatch(tmp_path, field, value, message):
    _specification, _run_directory, kwargs = _contract_bundle(tmp_path)
    kwargs[field] = value
    errors = validate_worker_contract(**kwargs)
    assert any(message in error for error in errors)
