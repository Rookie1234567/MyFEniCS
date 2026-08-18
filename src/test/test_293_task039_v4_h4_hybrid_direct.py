"""V4 h4 Hybrid-direct identity, phase, and packet-consumer contracts."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from benchmarks import task039_v4_h4_hybrid_direct as v4
from src.geometry.mesh_builder_3d import stage4_axis_plan
from src.io.execution_plan import dry_run_payload, method_adapter_identity
from src.io.input_loader import InputError
from src.io.input_validation import (
    load_and_resolve,
    simulation_config_3d_from_normalized,
)
from src.postprocessing.hybrid_field_reconstruction import element_safe_middle_offsets
from src.runners import task039_hybrid_direct as direct_adapter
from src.runners.task039_hybrid_iterative import (
    make_task039_hybrid_iterative_profile,
)

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / v4.TASK039_V4_H4_HYBRID_DIRECT_INPUT
SOURCE_SHA = "a" * 40


def _spec():
    return load_and_resolve(INPUT)


def _iterative_spec():
    return load_and_resolve(ROOT / v4.TASK039_V4_H4_HYBRID_ITERATIVE_INPUT)


def test_v4_h4_module_import_does_not_load_solver_runtime():
    probe = (
        "import sys; "
        "import benchmarks.task039_v4_h4_hybrid_direct; "
        "assert not any(name == 'mpi4py' or name.startswith('mpi4py.') "
        "for name in sys.modules); "
        "assert not any(name == 'petsc4py' or name.startswith('petsc4py.') "
        "for name in sys.modules); "
        "assert not any(name == 'dolfinx' or name.startswith('dolfinx.') "
        "for name in sys.modules)"
    )
    completed = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_v4_h4_input_profile_and_dynamic_inventory_are_exact():
    specification = _spec()
    payload = v4.validate_v4_h4_specification(specification)
    identity = v4.build_v4_h4_mode_identity(specification, SOURCE_SHA)

    assert payload["model_id"] == v4.TASK039_V4_H4_HYBRID_DIRECT_MODEL_ID
    assert specification.discretization["mesh_target_nm"] == 4.0
    assert specification.method["requested_modes_per_direction"] == 480
    assert specification.execution["mpi_size"] == 8
    assert len(identity["external_keys"]) == 2
    assert identity["external_keys"]["count"] == 600
    assert dry_run_payload(specification)["requested_modes_per_direction"] == 480
    assert method_adapter_identity("hybrid_direct", payload["model_id"]) == (
        "task039.hybrid_direct"
    )


def test_shared_mode_identity_reads_resolved_provenance_physical_sha():
    specification = _spec()
    payload = specification.as_jsonable()
    identity = v4.build_v4_h4_mode_identity(specification, SOURCE_SHA)

    assert "physical_model_sha256" not in payload
    assert identity["physical_sha256"] == payload["provenance"]["physical_model_sha256"]
    v4._validate_shared_h4_mode_identity(identity, payload)


def test_v4_h4_iterative_profile_and_phase_use_exact_side_contract(tmp_path):
    direct_specification = _spec()
    specification = _iterative_spec()
    payload = v4.validate_v4_h4_specification(specification)
    profile = make_task039_hybrid_iterative_profile(480, 8, mesh_target_nm=4.0)
    identity_path = tmp_path / "mode_identity.json"
    identity, identity_sha = v4.write_v4_h4_mode_identity(
        direct_specification, SOURCE_SHA, identity_path
    )
    v4._validate_shared_h4_mode_identity(identity, payload)
    manifest = tmp_path / "manifest.json"
    manifest.write_bytes(b"manifest")
    manifest_sha = hashlib.sha256(manifest.read_bytes()).hexdigest()
    plan = v4.build_v4_h4_phase_plan(
        specification,
        tmp_path / "iterative-consumer",
        SOURCE_SHA,
        phase="iterative-consumer",
        identity_json=identity_path,
        manifest=manifest,
        manifest_sha256=manifest_sha,
        mpiexec_command="mpiexec",
    )

    assert payload["model_id"] == v4.TASK039_V4_H4_HYBRID_ITERATIVE_MODEL_ID
    assert profile.profile_id == "task039.hybrid_iterative.p6-h4.v1"
    assert profile.max_it == 4000
    assert profile.preconditioner_identity == (
        "fixed_exact_side_lu_plus_dynamic_dtn_woodbury"
    )
    assert plan.method == "hybrid_iterative"
    assert plan.adapter_identity == v4.TASK039_V4_H4_ITERATIVE_ADAPTER_IDENTITY
    assert plan.argv[plan.argv.index("--phase") + 1] == "iterative-consumer"
    assert identity_sha == hashlib.sha256(identity_path.read_bytes()).hexdigest()
    assert "--selected-mode-packet-consumer-manifest" not in v4._phase_argv(
        direct_specification,
        tmp_path / "mode-prep",
        SOURCE_SHA,
        "mode-prep",
        identity_json=identity_path,
        packet_directory=tmp_path / "packet",
    )


def test_v4_h4_iterative_packet_gate_requires_measured_release():
    qep_release = {
        "qep_calls": 0,
        "consumer_qep_required": False,
        "packet_manifest_sha256": "m" * 64,
        "packet_identity_sha256": "i" * 64,
        "packet_mmap_released": True,
        "packet_references_released": True,
    }
    assert v4._v4_h4_packet_consumer_gate(
        qep_release,
        manifest_sha256="m" * 64,
        identity_sha256="i" * 64,
    )
    for field in ("packet_mmap_released", "packet_references_released"):
        failed = dict(qep_release, **{field: False})
        assert not v4._v4_h4_packet_consumer_gate(
            failed,
            manifest_sha256="m" * 64,
            identity_sha256="i" * 64,
        )


def test_v4_h4_resolved_axis_supports_non_aligned_offsets_without_pde():
    specification = _spec()
    cfg = simulation_config_3d_from_normalized(specification.as_jsonable())
    axis_plan = stage4_axis_plan(cfg, 8)
    bottom, top = element_safe_middle_offsets(
        axis_plan,
        bottom_z_nm=specification.method["bottom_interface_nm"],
        top_z_nm=specification.method["top_interface_nm"],
    )
    assert (bottom["z_nm"], top["z_nm"]) == (11.0, 109.0)
    assert bottom["z_nm"] < top["z_nm"]
    assert 10.0 < bottom["z_nm"] < 110.0
    assert 10.0 < top["z_nm"] < 110.0
    assert not np.any(np.isclose(axis_plan.z_values, 10.0))
    assert not np.any(np.isclose(axis_plan.z_values, 110.0))
    assert (bottom["element_id"], top["element_id"]) == (
        np.searchsorted(axis_plan.z_values, 10.0, side="right") - 1,
        np.searchsorted(axis_plan.z_values, 110.0, side="right") - 1,
    )
    assert bottom["source"] == "nonaligned_interface_subinterval"
    assert top["source"] == "nonaligned_interface_subinterval"


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("model_id", "task039_5nm_v3_1deg_s5_hybrid_direct_m480"),
        ("mesh_target_nm", 5.0),
        ("requested_modes_per_direction", 240),
    ),
)
def test_v4_h4_scope_rejects_identity_mutations(field, value):
    specification = _spec()
    payload = specification.as_jsonable()
    if field == "model_id":
        payload[field] = value
    elif field == "mesh_target_nm":
        payload["discretization"][field] = value
    else:
        payload["method"][field] = value
    mutated = specification.__class__(
        identity={key: payload[key] for key in specification.identity},
        geometry=payload["geometry"],
        materials=payload["materials"],
        incidence=payload["incidence"],
        discretization=payload["discretization"],
        boundary=payload["boundary"],
        method=payload["method"],
        solver=payload["solver"],
        execution=payload["execution"],
        output=payload["output"],
        derived=payload["derived"],
        source_path=specification.source_path,
        raw_input_bytes=specification.raw_input_bytes,
        input_sha256=specification.input_sha256,
        physical_model_sha256=specification.physical_model_sha256,
        expected_output_parent=specification.expected_output_parent,
    )
    with pytest.raises(InputError):
        v4.validate_v4_h4_specification(mutated)


def test_v4_phases_share_identity_and_direct_packet_contract(tmp_path):
    specification = _spec()
    identity_path = tmp_path / "mode_identity.json"
    identity, identity_sha = v4.write_v4_h4_mode_identity(
        specification, SOURCE_SHA, identity_path
    )
    packet_dir = tmp_path / "packet"
    producer = v4.build_v4_h4_phase_plan(
        specification,
        tmp_path / "producer",
        SOURCE_SHA,
        phase="mode-prep",
        identity_json=identity_path,
        packet_directory=packet_dir,
        mpiexec_command="mpiexec",
    )
    manifest = packet_dir / "manifest.json"
    manifest.parent.mkdir()
    manifest.write_bytes(b"manifest")
    manifest_sha = hashlib.sha256(manifest.read_bytes()).hexdigest()
    consumer = v4.build_v4_h4_phase_plan(
        specification,
        tmp_path / "consumer",
        SOURCE_SHA,
        phase="direct-consumer",
        identity_json=identity_path,
        manifest=manifest,
        manifest_sha256=manifest_sha,
        mpiexec_command="mpiexec",
    )

    assert producer.argv[producer.argv.index("--phase") + 1] == "mode-prep"
    assert consumer.argv[consumer.argv.index("--phase") + 1] == "direct-consumer"
    assert producer.argv[producer.argv.index("--identity-json") + 1] == str(
        identity_path
    )
    assert consumer.argv[consumer.argv.index("--identity-json") + 1] == str(
        identity_path
    )
    assert producer.mpi_size == consumer.mpi_size == 8
    assert identity["scope"] == v4.TASK039_V4_H4_MODE_SCOPE
    assert identity_sha == hashlib.sha256(identity_path.read_bytes()).hexdigest()
    assert "--manifest-sha256" in consumer.argv
    assert "--retained-subspace-dual-rotation" not in consumer.argv


def test_direct_adapter_passes_optional_packet_identity_without_qep(
    monkeypatch, tmp_path
):
    specification = _spec()
    payload = specification.as_jsonable()
    captured = {}

    def fake_runner(argv, _cfg, *_args):
        captured["argv"] = argv
        return {}

    result = direct_adapter.run_task039_hybrid_direct(
        payload,
        tmp_path,
        runner=fake_runner,
        source_sha=SOURCE_SHA,
        selected_mode_packet_consumer_manifest=tmp_path / "manifest.json",
        selected_mode_packet_consumer_identity_json=tmp_path / "identity.json",
        selected_mode_packet_consumer_manifest_sha256="c" * 64,
    )

    assert result["argv"] == captured["argv"]
    assert "--selected-mode-packet-consumer-manifest" in captured["argv"]
    assert "--selected-mode-packet-consumer-manifest-sha256" in captured["argv"]


def test_direct_worker_forwards_same_manifest_identity_and_zero_qep(
    monkeypatch, tmp_path
):
    specification = _spec()
    resolved = tmp_path / "resolved_config.json"
    resolved.write_text(json.dumps(specification.as_jsonable()), encoding="utf-8")
    identity = tmp_path / "identity.json"
    identity.write_text("{}", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_bytes(b"manifest")
    manifest_sha = hashlib.sha256(manifest.read_bytes()).hexdigest()
    captured = {}

    def fake_direct(payload, directory, **kwargs):
        captured.update(kwargs)
        return {"passed": True, "packet_consumer_diagnostics": {"qep_calls": 0}}

    monkeypatch.setattr(v4, "run_task039_hybrid_direct", fake_direct)
    result = v4.run_v4_h4_worker(
        resolved,
        tmp_path / "consumer",
        SOURCE_SHA,
        phase="direct-consumer",
        identity_json=identity,
        manifest=manifest,
        manifest_sha256=manifest_sha,
    )

    assert result["packet_consumer_diagnostics"]["qep_calls"] == 0
    assert captured["selected_mode_packet_consumer_manifest"] == manifest
    assert captured["selected_mode_packet_consumer_identity_json"] == identity
    assert captured["selected_mode_packet_consumer_manifest_sha256"] == manifest_sha


def test_mode_prep_worker_enters_existing_task032_producer(monkeypatch, tmp_path):
    specification = _spec()
    resolved = tmp_path / "resolved_config.json"
    resolved.write_text(json.dumps(specification.as_jsonable()), encoding="utf-8")
    identity = tmp_path / "identity.json"
    v4.write_v4_h4_mode_identity(specification, SOURCE_SHA, identity)
    captured = {}

    def fake_task032(argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return {"status": "controlled_stop_packet_written"}

    from benchmarks import run_task032_phase6_augmented as task032

    monkeypatch.setattr(task032, "main", fake_task032)
    result = v4.run_v4_h4_worker(
        resolved,
        tmp_path / "producer",
        SOURCE_SHA,
        phase="mode-prep",
        identity_json=identity,
        packet_directory=tmp_path / "packet",
    )

    assert result["status"] == "controlled_stop_packet_written"
    assert "--selected-mode-packet-producer-dir" in captured["argv"]
    assert "--selected-mode-packet-identity-json" in captured["argv"]
    assert "--retained-subspace-dual-rotation" in captured["argv"]
    assert (
        task032._parse_args(
            captured["argv"], allow_task039=True
        ).retained_subspace_dual_rotation
        is True
    )
    assert captured["kwargs"]["canonical_export_prefix"] == "task039_v4_mode_prep"
    assert captured["kwargs"]["task039_stage_marker_path"].name == (
        "memory_stage_markers.raw.jsonl"
    )
    assert (
        v4.main(
            [
                "--worker",
                "--phase",
                "mode-prep",
                "--resolved-config",
                str(resolved),
                "--output-directory",
                str(tmp_path / "producer-main"),
                "--source-sha",
                SOURCE_SHA,
                "--identity-json",
                str(identity),
                "--packet-directory",
                str(tmp_path / "packet-main"),
            ]
        )
        == 0
    )


def test_parent_phase_uses_task038_process_tree_worker(monkeypatch, tmp_path):
    specification = _spec()
    identity = tmp_path / "identity.json"
    v4.write_v4_h4_mode_identity(specification, SOURCE_SHA, identity)
    captured = {}

    def fake_run_worker(plan, _specification, _run_directory, **kwargs):
        captured["plan"] = plan
        captured["poll_interval"] = kwargs["poll_interval"]
        return {"exit_status": 0, "result_classification": "not_run"}

    import src.runners.task038_launcher as launcher

    monkeypatch.setattr(launcher, "_run_worker", fake_run_worker)
    result = v4.launch_v4_h4_phase(
        specification,
        tmp_path / "mode-prep-run",
        SOURCE_SHA,
        phase="mode-prep",
        identity_json=identity,
        packet_directory=tmp_path / "packet",
        mpiexec_command="mpiexec",
    )

    assert result["exit_status"] == 0
    assert captured["poll_interval"] == 0.25
    assert captured["plan"].worker_module == "benchmarks.task039_v4_h4_hybrid_direct"
