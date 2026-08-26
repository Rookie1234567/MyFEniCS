"""Focused V6-2 runner, resource-plan, and raw-checker contracts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc
import pytest

import benchmarks.check_task040_v6_2_interface_schur as checker
import benchmarks.task040_level_a as level_a
import benchmarks.task040_level_a_watchdog as watchdog
import benchmarks.task040_v6_2_interface_schur as runner


FORMAL_SOURCE_SHA = "a" * 40
CHECKER_SOURCE_SHA = "b" * 40
HEX = "c" * 64


def _write_json(path: Path, payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, indent=2).encode() + b"\n"
    path.write_bytes(encoded)
    return hashlib.sha256(encoded).hexdigest()


def _qualification_plan() -> dict[str, Any]:
    return runner.build_v6_2_exact_qualification_plan()


def _identity_gate() -> dict[str, bool]:
    return {
        "zero_map": True,
        "repeat": True,
        "linearity": True,
        "restriction_prolongation": True,
        "full_elimination_gamma": True,
        "full_elimination_interior": True,
        "three_deterministic_vectors": True,
        "group_solve_count": True,
        "joint_size": True,
        "numeric_allgather": True,
        "full_interface_replica": True,
        "layout_coverage_exact": True,
        "layout_counts_7560_plus_7560": True,
        "layout_canonical_l_then_u": True,
        "layout_owner_distributed": True,
        "layout_position_bijection": True,
        "factor_ready_three_observed": True,
        "factor_simultaneous_max_three_observed": True,
        "factor_after_cleanup_zero_observed": True,
        "factor_action_destroyed": True,
    }


def _deterministic_vectors() -> list[dict[str, Any]]:
    return [
        {
            "vector_index": index,
            "gamma_action_error": 0.0,
            "full_interior_residual_error": 0.0,
            "solve_count": 3,
            "roundtrip_error": 0.0,
            "repeat_error": 0.0,
        }
        for index in range(3)
    ]


def _rank_artifact(rank: int, identity: dict[str, bool]) -> dict[str, Any]:
    layout = {
        "global_size": checker.EXPECTED_JOINT_COUNT,
        "owner_local_mapping_count": 1890,
        "owner_distributed": True,
        "coverage_exact": True,
        "canonical_position_bijection": True,
    }
    return {
        "schema": checker.EXPECTED_RANK_SCHEMA,
        "rank": rank,
        "mpi_size": checker.EXPECTED_MPI_SIZE,
        "source_sha": FORMAL_SOURCE_SHA,
        "input_sha256": HEX,
        "physical_model_sha256": HEX,
        "bare_f_operator_hash": HEX,
        "identity_preflight": {"pass": True, "checks": {"source": True}},
        "resource_preflight_pass": True,
        "system_inventory": {},
        "matrix_objects": {"C": 0, "D": 0, "H": 0},
        "qep_calls": 0,
        "canonical_interface_layout": layout,
        "canonical_mapping_sha256": HEX,
        "canonical_mapping_count": 1890,
        "group_rows": {},
        "support_audits": {},
        "support_metadata_replicated": True,
        "deterministic_vectors": _deterministic_vectors(),
        "zero_error": 0.0,
        "linearity_error": 0.0,
        "identity_gate": identity,
        "factor_lifecycle_before": {
            "ready": 3,
            "after_cleanup": None,
            "simultaneous_max": 3,
        },
        "factor_lifecycle_after": {
            "ready": 3,
            "after_cleanup": 0,
            "simultaneous_max": 3,
        },
        "full_side_exact_factor_count": 0,
        "global_direct_factor_count": 0,
        "numeric_allgather": False,
        "fe_numeric_allgather": False,
        "full_interface_numeric_replica": False,
        "raw_global_row_remap": False,
        "exact_output_vectors_loaded": 0,
        "pde_solve": "not_run",
        "exact_qualification_plan": _qualification_plan(),
    }


def _make_checker_fixture(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "formal"
    root.mkdir()
    audit_sha = _write_json(root / "operator_semantics_audit.json", {"pass": True})
    identity = _identity_gate()
    descriptors = []
    artifacts = []
    for rank in range(checker.EXPECTED_MPI_SIZE):
        artifact = _rank_artifact(rank, identity)
        path = root / f"rank{rank:04d}.json"
        artifact_sha = _write_json(path, artifact)
        descriptors.append(
            {
                "rank": rank,
                "path": path.name,
                "sha256": artifact_sha,
                "canonical_mapping_count": artifact["canonical_mapping_count"],
                "canonical_mapping_sha256": HEX,
                "factor_lifecycle_after": artifact["factor_lifecycle_after"],
            }
        )
        artifacts.append(artifact)
    after = [artifact["factor_lifecycle_after"] for artifact in artifacts]
    manifest = {
        "schema": checker.EXPECTED_FORMAL_SCHEMA,
        "method": "task040_v6_2_full_interface_schur",
        "profile": "task040.v6_2.h4.full_interface.v1",
        "mpi_size": checker.EXPECTED_MPI_SIZE,
        "status": "completed_v6_2_identity",
        "classification": "ignored_prefilled_value",
        "source_sha": FORMAL_SOURCE_SHA,
        "input_sha256": HEX,
        "physical_model_sha256": HEX,
        "identity_preflight": {"pass": True, "checks": {"source": True}},
        "resource_preflight": {"pass": True, "checks": {"resource": True}},
        "operator_semantics_audit": {
            "path": "operator_semantics_audit.json",
            "sha256": audit_sha,
        },
        "system_created": True,
        "system_inventory": {},
        "matrix_objects": {"C": 0, "D": 0, "H": 0},
        "qep_calls": 0,
        "bare_f_operator_hash": HEX,
        "factored_operator": "none",
        "full_side_exact_factor_count": 0,
        "global_direct_factor_count": 0,
        "exact_output_vectors_loaded": 0,
        "pde_solve": "not_run",
        "canonical_interface_layout": {
            "global_size": checker.EXPECTED_JOINT_COUNT,
            "lower_global_rows": checker.EXPECTED_LOWER_COUNT,
            "upper_global_rows": checker.EXPECTED_UPPER_COUNT,
            "canonical_order": "Gamma_L_then_Gamma_U_by_physical_key",
            "canonical_position_bijection": True,
            "coverage_exact": True,
            "owner_distributed": True,
            "root_metadata_gather": True,
            "per_rank_full_interface_replica": False,
            "numeric_allgather": False,
            "value_basis": "current_raw_active_coefficients",
            "canonical_block_transforms_applied": False,
        },
        "gamma_counts": {
            "Gamma_L": checker.EXPECTED_LOWER_COUNT,
            "Gamma_U": checker.EXPECTED_UPPER_COUNT,
            "joint": checker.EXPECTED_JOINT_COUNT,
        },
        "group_rows": {},
        "support_audits": {},
        "support_metadata_replicated": True,
        "deterministic_vectors": _deterministic_vectors(),
        "zero_error": 0.0,
        "linearity_error": 0.0,
        "identity_gate": identity,
        "factor_lifecycle": {
            "before": {"ready": 3, "after_cleanup": None, "simultaneous_max": 3},
            "after_by_rank": after,
            "construction_count": 3,
            "destruction_count": 3,
            "simultaneous_max": 3,
            "rank_consensus": True,
        },
        "numeric_allgather": False,
        "fe_numeric_allgather": False,
        "full_interface_numeric_replica": False,
        "root_metadata_gather": True,
        "per_rank_full_interface_replica": False,
        "raw_global_row_remap": False,
        "rank_artifacts": descriptors,
        "downstream": {},
        "exact_qualification_plan": _qualification_plan(),
        "research_only": True,
    }
    manifest_path = root / "v6_2_manifest.json"
    _write_json(manifest_path, manifest)
    return root, manifest_path


def test_v6_2_linearity_probe_copies_source_into_combined() -> None:
    matrix = PETSc.Mat().createAIJ(
        size=((PETSc.DECIDE, 4), (PETSc.DECIDE, 4)),
        nnz=1,
        comm=PETSc.COMM_SELF,
    )
    for row in range(4):
        matrix.setValue(row, row, PETSc.ScalarType(1.0 + 0.0j))
    matrix.assemble()

    captured_sources: list[np.ndarray] = []

    class _RecordingMatrix:
        @staticmethod
        def createVecLeft() -> PETSc.Vec:
            return matrix.createVecLeft()

        @staticmethod
        def mult(source: PETSc.Vec, target: PETSc.Vec) -> None:
            captured_sources.append(np.asarray(source.array).copy())
            matrix.mult(source, target)

    class _IdentityAction:
        @staticmethod
        def create_interface_vector() -> PETSc.Vec:
            return matrix.createVecRight()

    try:
        assert runner._linearity_probe(
            MPI.COMM_SELF, _RecordingMatrix, _IdentityAction
        ) <= runner.V6_2_ROUNDTRIP_TOLERANCE
        positions = np.arange(4, dtype=np.float64)
        expected = PETSc.ScalarType(
            11 * (0.125 + 0.00001 * positions)
            + 1j * (0.03125 * 11 + 0.000003 * positions)
        )
        assert len(captured_sources) == 3
        np.testing.assert_allclose(captured_sources[0], expected)
    finally:
        matrix.destroy()


def test_v6_2_linearity_probe_distributed_owner_rows() -> None:
    if MPI.COMM_WORLD.size != 2:
        pytest.skip("run this owner-row smoke with mpiexec -n 2")
    matrix = PETSc.Mat().createAIJ(
        size=((PETSc.DECIDE, 4), (PETSc.DECIDE, 4)),
        nnz=1,
        comm=MPI.COMM_WORLD,
    )
    first, last = map(int, matrix.getOwnershipRange())
    for row in range(first, last):
        matrix.setValue(row, row, PETSc.ScalarType(1.0 + 0.0j))
    matrix.assemble()

    class _IdentityAction:
        @staticmethod
        def create_interface_vector() -> PETSc.Vec:
            return matrix.createVecRight()

    try:
        assert runner._linearity_probe(
            MPI.COMM_WORLD, matrix, _IdentityAction
        ) <= runner.V6_2_ROUNDTRIP_TOLERANCE
    finally:
        matrix.destroy()


def test_v6_2_plan_binds_resource_and_post_identity_qualification(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "input.dat"
    spool_root = tmp_path / "frozen-spool"
    run_root = tmp_path / "run"
    watchdog_root = tmp_path / "watchdog"
    plan = level_a.build_task040_level_a_plan(
        input_path=input_path,
        exact_spool_root=spool_root,
        run_directory=run_root,
        source_sha=FORMAL_SOURCE_SHA,
        v6_2_interface_schur=True,
    )
    assert plan["mpi_size"] == 8
    assert plan["threads"] == 1
    assert plan["absolute_terminate_memory_bytes"] == 45 * 2**30
    assert plan["minimum_mem_available_bytes"] == 49 * 2**30
    assert plan["exact_qualification_plan"]["status"] == "designed_not_run"
    assert plan["exact_qualification_plan"]["checkpoints"] == [16, 32, 64, 128]
    assert (
        plan["exact_qualification_plan"]["frozen_owner_row_arrays"]
        == "not_loaded; complex PETSc owner-order values, never row ids"
    )
    assert "raw_global_row_remap" in plan["forbidden"]
    assert "full_side_factor" in plan["forbidden"]

    watched = watchdog.build_task040_level_a_watchdog_plan(
        input_path=input_path,
        exact_spool_root=spool_root,
        run_directory=watchdog_root,
        source_sha=FORMAL_SOURCE_SHA,
        v6_2_interface_schur=True,
    )
    assert watched["watchdog"]["hard_stop_bytes"] == 45 * 2**30
    assert watched["watchdog"]["minimum_mem_available_bytes"] == 49 * 2**30
    assert watched["watchdog"]["process_tree_watchdog_enabled"] is True
    assert watched["watchdog"]["v6_2_identity_only"] is True
    assert "v6_2_preflight_only" not in watched["watchdog"]
    assert "--watchdog-hard-stop-bytes" in watched["worker_argv"]
    assert watched["worker_argv"].count("--v6-2-interface-schur") == 1


def test_v6_2_resource_preflight_uses_observed_environment_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import benchmarks.task034_wsl_resources as resources

    hard_stop = 45 * 2**30
    monkeypatch.setenv("_MYFENICS_WSL_QUALIFIED_ACTIVATION", "1")
    for name in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
        "BLIS_NUM_THREADS",
    ):
        monkeypatch.setenv(name, "1")
    monkeypatch.setattr(
        resources,
        "wsl_memory_snapshot",
        lambda: {"mem_available_bytes": 50 * 2**30},
    )
    monkeypatch.setattr(
        level_a,
        "_worker_current_resource",
        lambda comm, hard_limit_bytes: {
            "swap_bytes": 0,
            "all_status_readable": True,
            "pass": True,
        },
    )
    monkeypatch.setattr(
        runner.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(free=21 * 2**30),
    )

    observed = runner._resource_preflight(
        MPI.COMM_SELF,
        tmp_path,
        hard_stop_bytes=hard_stop,
        watchdog_hard_stop_bytes=hard_stop,
    )
    assert observed["checks"]["mem_available_at_least_minimum"] is True
    assert observed["checks"]["watchdog_hard_stop_matches_worker"] is True
    assert observed["checks"]["swap_zero"] is True
    assert observed["minimum_mem_available_bytes"] == 49 * 2**30
    assert observed["watchdog_hard_stop_bytes"] == hard_stop
    assert observed["pass"] is False
    assert observed["checks"]["mpi_size_8"] is False


def test_v6_2_checker_validates_rank_artifacts_and_gate(tmp_path: Path) -> None:
    root, _manifest_path = _make_checker_fixture(tmp_path)
    output = tmp_path / "checker.json"
    result = checker.check_v6_2_interface_schur(
        formal_root=root,
        formal_source_sha=FORMAL_SOURCE_SHA,
        checker_source_sha=CHECKER_SOURCE_SHA,
        output=output,
    )
    assert result["evidence_valid"] is True
    assert result["checker_pass"] is True
    assert result["gate_pass"] is True
    assert result["classification"] == "V6_2_FULL_INTERFACE_SCHUR_PASS"
    assert result["evidence_checks"]["evidence_rank_mapping_count_observed"] is True
    assert result["gate_checks"]["rank_deterministic_scalars"] is True
    assert result["gate_checks"]["rank_mapping_count_sum"] is True
    assert all(not item["path"].endswith(".npy") for item in result["read_files"])


def test_v6_2_checker_rejects_rank_scalar_tamper_after_descriptor_update(
    tmp_path: Path,
) -> None:
    root, manifest_path = _make_checker_fixture(tmp_path)
    tampered = root / "rank0003.json"
    payload = json.loads(tampered.read_text())
    payload["zero_error"] = 1.0e-4
    tampered_sha = _write_json(tampered, payload)
    manifest = json.loads(manifest_path.read_text())
    for descriptor in manifest["rank_artifacts"]:
        if descriptor["path"] == tampered.name:
            descriptor["sha256"] = tampered_sha
            break
    else:
        raise AssertionError("tampered rank descriptor was not found")
    _write_json(manifest_path, manifest)
    output = tmp_path / "checker-tampered.json"
    exit_code = checker.main(
        [
            "--formal-root",
            str(root),
            "--formal-source-sha",
            FORMAL_SOURCE_SHA,
            "--checker-source-sha",
            CHECKER_SOURCE_SHA,
            "--output",
            str(output),
        ]
    )
    assert exit_code == 2
    observed = json.loads(output.read_text())
    assert observed["checker_pass"] is False
    assert observed["classification"] == "IMPLEMENTATION_FAILURE"
    assert observed["evidence_checks"]["evidence_rank_zero_linearity_consistent"] is False


def test_v6_2_checker_accepts_complete_evidence_with_identity_gate_negative(
    tmp_path: Path,
) -> None:
    root, manifest_path = _make_checker_fixture(tmp_path)
    manifest = json.loads(manifest_path.read_text())
    for descriptor in manifest["rank_artifacts"]:
        rank_path = root / descriptor["path"]
        artifact = json.loads(rank_path.read_text())
        artifact["zero_error"] = 1.0e-4
        descriptor["sha256"] = _write_json(rank_path, artifact)
    manifest["zero_error"] = 1.0e-4
    _write_json(manifest_path, manifest)
    output = tmp_path / "checker-negative.json"
    exit_code = checker.main(
        [
            "--formal-root",
            str(root),
            "--formal-source-sha",
            FORMAL_SOURCE_SHA,
            "--checker-source-sha",
            CHECKER_SOURCE_SHA,
            "--output",
            str(output),
        ]
    )
    assert exit_code == 0
    observed = json.loads(output.read_text())
    assert observed["evidence_valid"] is True
    assert observed["checker_pass"] is True
    assert observed["gate_pass"] is False
    assert observed["classification"] == "V6_2_FULL_INTERFACE_SCHUR_IDENTITY_FAIL"
    assert observed["evidence_checks"]["rank_integrity"] is True
    assert observed["gate_checks"]["zero_map_le_1e-13"] is False


def test_v6_2_checker_rejects_nonmapping_lifecycle_entry(tmp_path: Path) -> None:
    root, manifest_path = _make_checker_fixture(tmp_path)
    manifest = json.loads(manifest_path.read_text())
    manifest["factor_lifecycle"]["after_by_rank"][0] = None
    _write_json(manifest_path, manifest)
    output = tmp_path / "checker-lifecycle.json"
    exit_code = checker.main(
        [
            "--formal-root",
            str(root),
            "--formal-source-sha",
            FORMAL_SOURCE_SHA,
            "--checker-source-sha",
            CHECKER_SOURCE_SHA,
            "--output",
            str(output),
        ]
    )
    assert exit_code == 2
    observed = json.loads(output.read_text())
    assert observed["checker_pass"] is False
    assert observed["classification"] == "IMPLEMENTATION_FAILURE"
    assert observed["evidence_checks"]["factor_lifecycle_recorded"] is False


def test_v6_2_checker_rejects_rank_root_lifecycle_mismatch(tmp_path: Path) -> None:
    root, manifest_path = _make_checker_fixture(tmp_path)
    manifest = json.loads(manifest_path.read_text())
    descriptor = next(
        item for item in manifest["rank_artifacts"] if item["rank"] == 2
    )
    rank_path = root / descriptor["path"]
    artifact = json.loads(rank_path.read_text())
    artifact["factor_lifecycle_after"]["after_cleanup"] = 1
    descriptor["factor_lifecycle_after"] = artifact["factor_lifecycle_after"]
    descriptor["sha256"] = _write_json(rank_path, artifact)
    _write_json(manifest_path, manifest)
    output = tmp_path / "checker-lifecycle-mismatch.json"
    exit_code = checker.main(
        [
            "--formal-root",
            str(root),
            "--formal-source-sha",
            FORMAL_SOURCE_SHA,
            "--checker-source-sha",
            CHECKER_SOURCE_SHA,
            "--output",
            str(output),
        ]
    )
    assert exit_code == 2
    observed = json.loads(output.read_text())
    assert observed["checker_pass"] is False
    assert observed["classification"] == "IMPLEMENTATION_FAILURE"
    assert observed["evidence_checks"]["evidence_rank_factor_lifecycle_consistent"] is False


def test_v6_2_checker_rejects_manifest_rank_lifecycle_tamper(tmp_path: Path) -> None:
    root, manifest_path = _make_checker_fixture(tmp_path)
    manifest = json.loads(manifest_path.read_text())
    manifest["factor_lifecycle"]["after_by_rank"][4]["after_cleanup"] = 1
    _write_json(manifest_path, manifest)
    output = tmp_path / "checker-manifest-lifecycle-tamper.json"
    exit_code = checker.main(
        [
            "--formal-root",
            str(root),
            "--formal-source-sha",
            FORMAL_SOURCE_SHA,
            "--checker-source-sha",
            CHECKER_SOURCE_SHA,
            "--output",
            str(output),
        ]
    )
    assert exit_code == 2
    observed = json.loads(output.read_text())
    assert observed["checker_pass"] is False
    assert observed["classification"] == "IMPLEMENTATION_FAILURE"
    assert observed["evidence_checks"]["evidence_rank_factor_lifecycle_consistent"] is False


def test_v6_2_checker_rejects_output_inside_formal_root(tmp_path: Path) -> None:
    root, _manifest_path = _make_checker_fixture(tmp_path)
    output = root / "not-allowed.json"
    exit_code = checker.main(
        [
            "--formal-root",
            str(root),
            "--formal-source-sha",
            FORMAL_SOURCE_SHA,
            "--checker-source-sha",
            CHECKER_SOURCE_SHA,
            "--output",
            str(output),
        ]
    )
    assert exit_code == 2
    assert not output.exists()
