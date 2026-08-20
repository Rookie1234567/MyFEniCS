"""Pure contracts for the T5 authority bridge and its composite forwarding."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from benchmarks import run_task038_full3d_t5 as runner
from benchmarks import task038_full3d_t5_checker as checker
from benchmarks.canonical_vector_artifacts import (
    canonical_shard_manifest,
    write_canonical_manifest,
    write_canonical_packet_shard,
)
from src.solvers.fullspace_physical_action import FullspacePhysicalAction


def _write_dual_manifest(root: Path, name: str, value: complex) -> Path:
    directory = root / name
    directory.mkdir(parents=True)
    key = (
        "full_fe_dual",
        1,
        ((0, 0, 0), (1, 0, 0)),
        0,
        ("canonical_edge", "contract"),
        None,
        (1.0, 0.0),
    )
    shard_path = directory / "rank0000.jsonl"
    shard = write_canonical_packet_shard(
        shard_path, ((key, value),), audit_packets=True
    )
    manifest = canonical_shard_manifest(
        role="full_fe_dual",
        mpi_size=1,
        shard_metadata=[shard],
        extractor_audit={"contract": True},
    )
    manifest_path = directory / "manifest.json"
    write_canonical_manifest(manifest_path, manifest)
    return manifest_path


def _manifest_descriptor(root: Path, path: Path) -> dict[str, object]:
    packets, facts = checker._read_packet_manifest(path)
    del packets
    return {
        "manifest_relative_path": str(path.relative_to(root)),
        "manifest_sha256": facts["manifest_sha256"],
        "packet_count": facts["packet_count"],
        "role": "full_fe_dual",
    }


def _residual_artifacts(root: Path, values: dict[str, complex]) -> dict[str, object]:
    paths = {
        name: _write_dual_manifest(root, name, value)
        for name, value in values.items()
    }
    return {
        "status": "pass",
        **{name: _manifest_descriptor(root, path) for name, path in paths.items()},
    }


def test_residual_bridge_has_two_stage_qualification_and_canonical_gate(tmp_path):
    mpi1 = _write_dual_manifest(tmp_path, "mpi1", 1.0 + 0.0j)
    mpi2 = _write_dual_manifest(tmp_path, "mpi2", 1.0 + 0.0j)
    errors, facts = checker._check_residual_mpi_identity(
        tmp_path, {"mpi1_manifest_path": str(mpi1)}
    )
    assert not errors
    assert facts["qualified_for_mpi2"] is True
    errors, facts = checker._check_residual_mpi_identity(
        tmp_path,
        {
            "mpi1_manifest_path": str(mpi1),
            "mpi2_reextract_manifest_path": str(mpi2),
        },
    )
    assert not errors
    assert facts["relative_l2"] <= checker.T5_CANONICAL_LIMIT
    high_error = _write_dual_manifest(tmp_path, "mpi2_high_error", 1.0 + 2.0e-12j)
    errors, _facts = checker._check_residual_mpi_identity(
        tmp_path,
        {
            "mpi1_manifest_path": str(mpi1),
            "mpi2_reextract_manifest_path": str(high_error),
        },
    )
    assert any("canonical gate" in error for error in errors)


def test_manifest_comparator_uses_right_reference_norm():
    difference = checker._packet_difference({"key": 1.0 + 0.0j}, {"key": 2.0 + 0.0j})
    assert difference["relative_l2"] == pytest.approx(0.5)


def test_residual_action_authority_recomputes_four_raw_manifests(tmp_path):
    artifacts = _residual_artifacts(
        tmp_path,
        {
            "source": 1.0 + 0.0j,
            "action": 2.0 + 0.0j,
            "repeat": 2.0 + 0.0j,
            "reference": 2.0 + 0.0j,
        },
    )
    errors, facts = checker._check_residual_authority(tmp_path, artifacts)
    assert not errors
    assert facts["action_reference"]["comparison"]["relative_l2"] == 0.0
    record = {
        "raw_dir": str(tmp_path),
        "artifacts": {"residual": artifacts},
        "residual": {
            "finite": False,
            "norm": 0.0,
            "action_relative_error": 1.0,
        },
    }
    checked = checker.check_t5_record(record)
    assert checked["gates"]["residual_physical_action"] is True


def test_pair_uses_each_record_raw_dir_for_cross_mpi_manifests(tmp_path):
    raw1 = tmp_path / "raw" / "mpi1"
    raw2 = tmp_path / "raw" / "mpi2"
    raw1.mkdir(parents=True)
    raw2.mkdir(parents=True)
    first_artifacts = _residual_artifacts(
        raw1,
        {name: 1.0 + 0.0j for name in ("source", "action", "repeat", "reference")},
    )
    second_artifacts = _residual_artifacts(
        raw2,
        {name: 1.0 + 0.0j for name in ("source", "action", "repeat", "reference")},
    )
    first_path = tmp_path / "records" / "mpi1.json"
    second_path = tmp_path / "records" / "mpi2.json"
    first_path.parent.mkdir()
    base = {
        "schema": checker.T5_SCHEMA,
        "profile": checker.T5_PROFILE,
        "raw_dir": str(raw1),
        "artifacts": {"residual": first_artifacts},
        "residual_bridge": {
            "mpi1_manifest_path": str(raw1 / "source" / "manifest.json")
        },
        "mpi": {"size": 1},
    }
    first_path.write_text(json.dumps(base), encoding="utf-8")
    second = dict(base)
    second["raw_dir"] = str(raw2)
    second["artifacts"] = {"residual": second_artifacts}
    second["residual_bridge"] = {
        "mpi1_manifest_path": str(raw1 / "source" / "manifest.json"),
        "mpi2_reextract_manifest_path": str(raw2 / "source" / "manifest.json"),
    }
    second["mpi"] = {"size": 2}
    second_path.write_text(json.dumps(second), encoding="utf-8")
    result = checker.check_t5_pair(first_path, second_path)
    assert result["derived"]["residual_cross_mpi"]["source"]["pass"] is True


def test_worker_rhs_preflight_is_fail_closed_before_residual_input(tmp_path):
    old_dir = tmp_path / "old"
    current = _write_dual_manifest(tmp_path, "current", 1.0 + 0.0j)
    old = _write_dual_manifest(tmp_path, "old", 1.0 + 0.0j)
    old_target = old_dir / "mpi1_candidate_physical_rhs_dual_manifest.json"
    old_target.parent.mkdir(exist_ok=True)
    old_target.write_bytes(old.read_bytes())
    result = runner._rhs_bridge_preflight(
        old_dir,
        tmp_path,
        {"manifest_relative_path": "current/manifest.json"},
    )
    assert result["pass"] is True
    current_bad = _write_dual_manifest(tmp_path, "current_bad", 1.0 + 2.0e-12j)
    result = runner._rhs_bridge_preflight(
        old_dir,
        tmp_path,
        {"manifest_relative_path": str(current_bad.relative_to(tmp_path))},
    )
    assert result["pass"] is False


def test_mesh_witness_comparison_is_explicit_and_tamper_evident():
    fields = {
        "cell_type": "hexahedron",
        "cells_global": 2,
        "vertices_global": 12,
        "geometry_shape": [12, 3],
        "canonical_connectivity_sha256": "a" * 64,
        "canonical_geometry_sha256": "b" * 64,
        "axis_counts": [3, 2, 2],
        "digest_algorithm": "sorted-cell-coordinate-metadata-v1",
    }
    witnesses = {
        name: {"source": name, **fields}
        for name in ("old_exact", "current_generated", "current_rebuild")
    }
    witnesses["old_exact"]["source"] = "old_exact_xdmf"
    record = {
        "mesh_witnesses": {
            **witnesses,
            "identity_fields": list(checker.T5_MESH_IDENTITY_FIELDS),
        }
    }
    errors, _facts = checker._check_mesh_witnesses(record)
    assert not errors
    record["mesh_witnesses"]["current_rebuild"]["canonical_geometry_sha256"] = "c" * 64
    errors, _facts = checker._check_mesh_witnesses(record)
    assert any("identity differs" in error for error in errors)


def test_runner_scope_and_watchdog_contract():
    source = inspect.getsource(runner._build_authority_case)
    assert "from mpi4py import MPI" in source
    assert "compose_physical_rhs(base_incident, incident_projections, source)" in source
    assert "old_dir" in source and "mpi1_residual_manifest" in source
    assert "task038_full3d_t5_checker" not in inspect.getsource(runner)
    assert not hasattr(runner, "build_small_fixture_record")
    watchdog_source = inspect.getsource(runner._watchdog_main)
    assert "resource_authority_sample" in watchdog_source
    assert "terminate_process_tree" in watchdog_source
    args = runner._parser().parse_args(
        [
            "--raw-dir",
            "raw",
            "--record",
            "record.json",
            "--expected-source-sha",
            "a" * 40,
            "--expected-mpi-size",
            "1",
        ]
    )
    assert args.watchdog_mode == "external_process_tree"
    assert args.process_tree_memory_ceiling_bytes == 6 * 1024**3
    assert args.hard_stop_memory_bytes == 12 * 1024**3


def test_runtime_identity_and_preflight_are_fail_closed(monkeypatch):
    repo_root = Path(runner.__file__).resolve().parents[1]
    monkeypatch.setenv("_MYFENICS_WSL_QUALIFIED_ACTIVATION", "contract-marker")
    assert runner._runtime_identity()["qualified_activation"] == "contract-marker"

    monkeypatch.setenv("_MYFENICS_WSL_QUALIFIED_ACTIVATION", "0")
    with pytest.raises(RuntimeError, match="activation marker"):
        runner._runtime_preflight(repo_root)

    runtime = {
        "qualified_activation": "1",
        "python": str((repo_root / ".venv").resolve() / "bin" / "python"),
        "petsc_scalar_type": "complex128",
        "petsc_int_type": "int64",
    }
    monkeypatch.setenv("_MYFENICS_WSL_QUALIFIED_ACTIVATION", "1")
    monkeypatch.setattr(runner, "_runtime_identity", lambda: runtime)
    assert runner._runtime_preflight(repo_root) is runtime
    good_runtime = dict(runtime)
    provenance = {
        "old_source_sha": checker.OLD_SOURCE_SHA,
        "old_api": "iter_canonical_full_fe_dual_packets",
        "current_api": "extract_canonical_full_fe_dual_packets",
        "entity_transform": "transform.conj().T",
        "cell_transform": "Tt_apply",
        "slave_exclusion": True,
        "old_source_blob_sha256": "a" * 64,
        "runtime": good_runtime,
    }
    checked = checker.check_t5_record(
        {
            "schema": checker.T5_SCHEMA,
            "profile": checker.T5_PROFILE,
            "extractor_provenance": provenance,
        }
    )
    assert checked["gates"]["extractor_provenance"] is True
    runtime["petsc_scalar_type"] = "float64"
    with pytest.raises(RuntimeError, match="complex128"):
        runner._runtime_preflight(repo_root)
    provenance["runtime"]["qualified_activation"] = "0"
    checked = checker.check_t5_record(
        {
            "schema": checker.T5_SCHEMA,
            "profile": checker.T5_PROFILE,
            "extractor_provenance": provenance,
        }
    )
    assert checked["gates"]["extractor_provenance"] is False


def test_resource_gate_recomputes_hash_bound_process_tree_evidence(tmp_path):
    raw_path = tmp_path / "watchdog" / "raw.json"
    compact_path = tmp_path / "watchdog" / "compact.json"
    sample = {
        "elapsed_seconds": 1.0,
        "process_tree": {
            "rss_bytes": 1024,
            "swap_bytes": 0,
            "all_status_readable": True,
        },
        "job_cgroup": {
            "dedicated_job_cgroup": False,
            "swap_current_bytes": 123456,
        },
        "memory_authority_bytes": 1024,
        "job_no_swap": True,
    }
    raw = {
        "schema": "task038.t5.external-process-tree-raw.v1",
        "samples": [sample],
        "returncode": 0,
        "stop_reason": None,
        "termination": {"process_group_exited": True, "sigkill_required": False},
    }
    raw_path.parent.mkdir()
    raw_path.write_bytes(runner._canonical_json(raw) + b"\n")
    compact = {
        "schema": "task038.t5.external-process-tree-compact.v1",
        "status": "measured_pass",
        "process_tree_peak_rss_bytes": 1024,
        "process_tree_peak_swap_bytes": 0,
        "dedicated_cgroup_peak_swap_bytes": 0,
        "memory_authority_peak_bytes": 1024,
        "process_tree_memory_ceiling_bytes": 6 * 1024**3,
        "hard_stop_memory_bytes": 12 * 1024**3,
        "swap_required_bytes": 0,
        "sample_count": 1,
        "all_status_readable": True,
        "stop_reason": None,
        "returncode": 0,
        "termination": raw["termination"],
        "raw_report_sha256": checker._sha256_path(raw_path),
    }
    compact_path.write_bytes(runner._canonical_json(compact) + b"\n")
    record = {
        "raw_dir": str(tmp_path),
        "resource_contract": {
            **compact,
            "watchdog": "external_process_tree",
            "raw_report_relative_path": "watchdog/raw.json",
            "compact_report_relative_path": "watchdog/compact.json",
            "compact_report_sha256": checker._sha256_path(compact_path),
        },
    }
    errors, _facts = checker._check_resource_contract(record)
    assert not errors
    raw["samples"][0]["process_tree"]["rss_bytes"] = 2048
    raw_path.write_bytes(runner._canonical_json(raw) + b"\n")
    errors, _facts = checker._check_resource_contract(record)
    assert any("raw watchdog report SHA mismatch" in error for error in errors)


def test_composite_forwards_physical_rhs_without_extra_ownership_logic():
    calls = []

    class FakeDtn:
        def compose_physical_rhs(self, base, amplitudes, target):
            calls.append((base, tuple(amplitudes), target))

        def destroy(self):
            calls.append("dtn_destroy")

        @property
        def audit(self):
            return {}

    class FakeVolume:
        def destroy(self):
            calls.append("volume_destroy")

        @property
        def audit(self):
            return {}

    action = FullspacePhysicalAction(FakeVolume(), FakeDtn())
    action.compose_physical_rhs("base", (1.0 + 0.0j,), "target")
    assert calls[0] == ("base", (1.0 + 0.0j,), "target")
    action.destroy()
    with pytest.raises(RuntimeError, match="destroyed"):
        action.compose_physical_rhs("base", (), "target")


def test_composite_apply_accumulates_dtn_and_volume_once():
    class Vec:
        def __init__(self, value=0.0):
            self.value = value

        def axpy(self, scale, other):
            self.value += scale * other.value

    class Dtn:
        def __init__(self):
            self.applies = 0

        def apply(self, source, target):
            self.applies += 1
            target.value = 2.0 * source.value

        def destroy(self):
            pass

        @property
        def audit(self):
            return {"kind": "dtn"}

    class Volume:
        def __init__(self):
            self.applies = 0

        def apply(self, source):
            self.applies += 1
            return Vec(3.0 * source.value)

        def destroy(self):
            pass

        @property
        def audit(self):
            return {"kind": "volume"}

    dtn = Dtn()
    volume = Volume()
    action = FullspacePhysicalAction(volume, dtn)
    target = Vec()
    action.apply(Vec(4.0), target)
    assert target.value == 20.0
    assert dtn.applies == volume.applies == 1
    assert action.audit["apply_count"] == 1
    action.destroy()
