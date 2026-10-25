"""D07C direct package identity survives the real manifest and worker gate."""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from src.io.execution_plan import build_execution_plan
from src.io.input_validation import load_and_resolve
from src.io.run_specification import thaw
from src.runners.task038_input_worker import _load_and_validate_worker_payload
from src.runners.task038_launcher import _write_bootstrap

ROOT = Path(__file__).resolve().parents[2]
INPUT_DIR = ROOT / "input/task40para_phi90_mesh_modes_direct"
SOURCE_SHA = "d07c" * 10
CASES = ("b", "y1", "y2")
MINIMUM_AVAILABLE = 64 * 1024**3


def _build_real_manifest(tmp_path, case):
    specification = load_and_resolve(
        INPUT_DIR / f"d07c_{case}_m32_nminus143_to1_p6_direct.dat"
    )
    run_directory = (tmp_path / f"run-{case}").resolve()
    run_directory.mkdir()
    specification = replace(
        specification,
        expected_output_parent=run_directory.parent,
    )
    plan = build_execution_plan(
        specification,
        run_directory,
        source_sha=SOURCE_SHA,
        python_executable=sys.executable,
        mpiexec_command="/usr/bin/mpiexec",
    )
    manifest, resolved_sha = _write_bootstrap(
        specification,
        run_directory,
        source_sha=SOURCE_SHA,
        adapter_identity=plan.adapter_identity,
        start_time="2026-10-25T00:00:00Z",
    )
    return specification, run_directory, manifest, resolved_sha, plan


def _worker_validate(specification, run_directory, resolved_sha, plan):
    return _load_and_validate_worker_payload(
        resolved_config=run_directory / "resolved_config.json",
        manifest=run_directory / "run_manifest.json",
        expected_input_sha256=specification.input_sha256,
        expected_physical_model_sha256=specification.physical_model_sha256,
        expected_source_sha=SOURCE_SHA,
        expected_mpi_size=1,
        expected_method="full3d_direct",
        expected_adapter=plan.adapter_identity,
        expected_output_directory=run_directory,
        expected_resolved_config_sha256=resolved_sha,
        actual_mpi_size=1,
    )


@pytest.mark.parametrize("case", CASES)
def test_d07c_formal_profile_roundtrips_through_worker(case, tmp_path):
    specification, run_directory, manifest, resolved_sha, plan = _build_real_manifest(
        tmp_path, case
    )
    profile = specification.derived["native_capacity_profile"]
    contract = manifest["native_capacity_contract"]

    assert manifest["native_capacity_profile_identity"] == profile["identity"]
    assert contract["resource_stop_policy"] == "host_available_floor_v1"
    assert contract["rss_hard_limit_bytes"] is None
    assert contract["minimum_available_bytes"] == MINIMUM_AVAILABLE
    assert contract["direct_route"]["active_signed_bounds_mn"] == [-32, 32, -143, 1]
    assert contract["direct_route"]["surface_quadrature_degree"] == 81
    assert contract["direct_route"]["surface_quadrature_reference_degree"] == 161
    resolved, errors = _worker_validate(
        specification, run_directory, resolved_sha, plan
    )
    assert errors == []
    assert resolved is not None
    assert resolved["derived"]["native_capacity_profile"] == thaw(profile)


def test_d07c_worker_rejects_profile_resource_contract_drift(tmp_path):
    specification, run_directory, manifest, resolved_sha, plan = _build_real_manifest(
        tmp_path, "b"
    )
    manifest_path = run_directory / "run_manifest.json"
    manifest["native_capacity_contract"]["rss_hard_limit_bytes"] = 128 * 1024**3
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    resolved, errors = _worker_validate(
        specification, run_directory, resolved_sha, plan
    )
    assert resolved is not None
    assert errors == ["manifest condensed-direct RSS hard limit mismatch"]
