"""Focused P0 memory-first checkpoint, cycle, and checker contracts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import tempfile

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

from benchmarks import run_task038_full3d_lor_hx_p0 as p0_runner
from benchmarks.task038_full3d_lor_hx_p0_checker import (
    check_record,
    residual_pair_bound,
)
from benchmarks.run_task038_full3d_lor_hx_p0 import (
    _checkpoint_expected as runner_checkpoint_expected,
)
from src.solvers.fullspace_memory_first_krylov import (
    destroy_krylov_result,
    read_solution_checkpoint,
    run_restart20_cycles,
    write_solution_checkpoint,
)


BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"
SOURCE_SHA = "a" * 40
HASH = "b" * 64
PC_NAMES = (
    "input_first_before",
    "input_first_after",
    "input_second_before",
    "input_second_after",
    "input_combined_before",
    "input_combined_after",
    "output_first",
    "output_second",
    "output_combined",
    "output_repeat",
)


def _write_shard(raw_dir: Path, name: str, values: np.ndarray) -> dict[str, object]:
    path = raw_dir / f"{name}.rank0.npy"
    values = np.asarray(values, dtype=np.complex128)
    np.save(path, values, allow_pickle=False)
    payload = path.read_bytes()
    return {
        "rank": 0,
        "relative_path": path.name,
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "dtype": str(values.dtype),
        "shape": list(values.shape),
    }


def _artifact(raw_dir: Path, name: str, values: np.ndarray) -> dict[str, object]:
    return {
        "name": name,
        "role": name,
        "root": str(raw_dir.resolve()),
        "shards": [_write_shard(raw_dir, name, values)],
    }


def _resource() -> dict[str, object]:
    return {
        "process_tree_rss_bytes": 1,
        "process_tree_swap_bytes": 0,
        "memory_authority_bytes": 1,
        "all_status_readable": True,
        "dedicated_cgroup_observed": False,
        "dedicated_cgroup_path": "/init.scope",
        "dedicated_cgroup_readable": True,
        "dedicated_cgroup_swap_bytes": None,
        "job_no_swap": True,
    }


def _cycle(index: int, start: int, end: int) -> dict[str, object]:
    return {
        "cycle_index": index,
        "start_iteration": start,
        "end_iteration": end,
        "iterations": end - start,
        "reason": -3,
        "initial_guess_nonzero": start > 0,
        "reported_final_residual": 0.5,
        "explicit_true_residual": 0.25,
        "matvec_count": 20,
        "pc_apply_count": 20,
        "wall_seconds": 0.1,
        "resource": _resource(),
        "ksp_destroyed": True,
    }


def _write_checkpoint_fixture(raw_dir: Path, provenance: dict[str, str]) -> dict[str, object]:
    checkpoint_root = raw_dir / "checkpoint-20"
    checkpoint_root.mkdir()
    values = np.asarray([0.0 + 0.0j, 1.0 + 0.5j], dtype=np.complex128)
    descriptor = _write_shard(checkpoint_root, "solution", values)
    manifest = {
        "schema": "fixed-memory-krylov.solution-checkpoint.v1",
        "iteration": 20,
        "explicit_true_residual": 0.25,
        **provenance,
        "mpi_size": 1,
        "solution_only": True,
        "numeric_allgather": False,
        "vector_roles": ["solution"],
        "forbidden_vector_roles": ["action", "residual", "krylov_basis"],
        "ranks": [
            {
                "rank": 0,
                "ownership": {
                    "rank": 0,
                    "ownership_range": [0, 2],
                    "local_size": 2,
                    "global_size": 2,
                },
                "solution": descriptor,
            }
        ],
    }
    manifest_path = checkpoint_root / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    return {
        "manifest_path": str(manifest_path.resolve()),
        "manifest_sha256": digest,
        "iteration": 20,
        "explicit_true_residual": 0.25,
        "mpi_size": 1,
        "roundtrip_relative": 0.0,
    }


def _synthetic_record(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "evidence-root"
    raw_dir = root / "raw"
    raw_dir.mkdir(parents=True)
    record_path = root / "record.json"
    provenance = {
        "input_identity_sha256": HASH,
        "operator_identity_sha256": "c" * 64,
        "physical_model_sha256": "d" * 64,
        "source_sha": SOURCE_SHA,
    }
    first_input = np.asarray([1.0 + 0.0j, 0.0 + 0.0j])
    second_input = np.asarray([0.0 + 0.0j, 2.0 + 0.0j])
    alpha = 0.375 + 0.125j
    beta = -0.25 + 0.5j
    combined_input = alpha * first_input + beta * second_input
    first_output = np.asarray([0.0 + 0.0j, 1.0 + 0.0j])
    second_output = np.asarray([0.0 + 0.0j, 2.0 + 0.0j])
    combined_output = alpha * first_output + beta * second_output
    artifacts: dict[str, dict[str, object]] = {
        "source": _artifact(raw_dir, "source", np.asarray([1.0, 2.0])),
        "residual": _artifact(raw_dir, "residual", np.asarray([2.0, -1.0 + 1.0j])),
    }
    arrays = {
        "input_first_before": first_input,
        "input_first_after": first_input,
        "input_second_before": second_input,
        "input_second_after": second_input,
        "input_combined_before": combined_input,
        "input_combined_after": combined_input,
        "output_first": first_output,
        "output_second": second_output,
        "output_combined": combined_output,
        "output_repeat": combined_output,
    }
    for name, values in arrays.items():
        artifacts[name] = _artifact(raw_dir, name, values)
    checkpoint = _write_checkpoint_fixture(raw_dir, provenance)
    first_norm = float(np.linalg.norm(first_input))
    second_norm = float(np.linalg.norm(second_input))
    combined_norm = float(np.linalg.norm(combined_input))
    fixture_audit = {
        "slave_master_complete": True,
        "phase_application": "finalized_floquet_mpc_once",
        "high_order_global_aij": False,
        "global_numeric_allgather": False,
        "hx_audit": {
            "high_order_aij": False,
            "global_direct_coarse": False,
            "global_numeric_allgather": False,
        },
    }
    cycle_first = _cycle(0, 0, 20)
    cycle_second = _cycle(1, 20, 40)
    record = {
        "schema": "task038.lor-native-complex-hx.memory-first-p0-record.v1",
        "stage": "p0",
        "case": "p2-mpi1",
        "degree": 2,
        "h_nm": 50.0,
        "source_name": "random",
        "source": {
            "expected_sha": SOURCE_SHA,
            "branch": BRANCH,
            "commit_sha_start": SOURCE_SHA,
            "commit_sha_end": SOURCE_SHA,
            "clean_start": True,
            "clean_end": True,
        },
        "runtime": {
            "qualified_activation": "1",
            "petsc_scalar_type": "complex128",
            "petsc_int_type": "int32",
            "mpi_size": 1,
        },
        "raw_dir": str(raw_dir.resolve()),
        "settings": {
            "variant": "sequential-v1",
            "restart": 20,
            "cycle_max_it": 20,
            "max_it": 40,
            "right_preconditioned": True,
            "norm_type": "unpreconditioned",
            "residual_replacement": True,
            "additive_v2": False,
        },
        "provenance": provenance,
        "fixture_audit": fixture_audit,
        "pc_legality": {
            "direction_construction": "PETSc_global_row_parity",
            "alpha": [alpha.real, alpha.imag],
            "beta": [beta.real, beta.imag],
            "first_global_norm": first_norm,
            "second_global_norm": second_norm,
            "combined_global_norm": combined_norm,
            "linearity_relative": 0.0,
            "repeat_relative": 0.0,
            "input_unchanged_relative": 0.0,
            "finite": True,
            "slave_constraint_absolute": 0.0,
            "slave_local_indices": [0],
            "slave_master_complete": True,
            "phase_application": "finalized_floquet_mpc_once",
            "high_order_global_aij": False,
            "global_direct_coarse": False,
            "numeric_allgather": False,
            "artifact_names": sorted(PC_NAMES),
        },
        "artifacts": artifacts,
        "outer": {
            "production_first_cycle": {
                "cycles": [cycle_first],
                "final_true_residual": 0.25,
                "iterations": 20,
                "reason": -3,
                "matvec_count": 20,
                "pc_apply_count": 20,
                "explicit_action_count": 2,
                "ksp_destroy_count": 1,
            },
            "restart": {
                "cycles": [cycle_second],
                "final_true_residual": 0.125,
                "initial_true_residual": 0.25,
                "iterations": 40,
                "reason": -3,
                "matvec_count": 20,
                "pc_apply_count": 20,
                "explicit_action_count": 2,
                "ksp_destroy_count": 1,
            },
            "continuous_reference": {
                "cycles": [_cycle(0, 0, 20), _cycle(1, 20, 40)],
                "final_true_residual": 0.125,
                "iterations": 40,
                "reason": -3,
                "matvec_count": 40,
                "pc_apply_count": 40,
                "explicit_action_count": 3,
                "ksp_destroy_count": 2,
            },
            "checkpoint": checkpoint,
            "boundary_true_residual": 0.25,
            "restart_boundary_true_residual_relative": 0.0,
            "post_rebuild_solution_roundtrip_relative": 0.0,
            "rebuilt_provenance": dict(provenance),
            "next_cycle_first_true_residual_relative": 0.0,
        },
        "old_authorities": {
            "old_l2_one_apply_rho": 1.7348663090876784,
            "old_l2_classification": "CONTROLLED_NEGATIVE_BY_POSITIVE_AUXILIARY_CONTRACTION_GATE",
            "old_k1_v1_80_step": "FAIL",
            "additive_v2": "CLOSED",
        },
    }
    record_path.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return record_path, raw_dir


def _real_checkpoint(tmp_path: Path) -> tuple[Path, PETSc.Vec, dict[str, object]]:
    solution = PETSc.Vec().createSeq(2, comm=PETSc.COMM_SELF)
    solution.array[:] = np.asarray([1.0 + 0.25j, -2.0 + 0.5j])
    directory = tmp_path / "real-checkpoint"
    facts = write_solution_checkpoint(
        directory,
        solution,
        iteration=20,
        explicit_true_residual=0.25,
        input_identity_sha256=HASH,
        operator_identity_sha256="c" * 64,
        physical_model_sha256="d" * 64,
        source_sha=SOURCE_SHA,
        ownership={
            "rank": 0,
            "ownership_range": [0, 2],
            "local_size": 2,
            "global_size": 2,
        },
        comm=MPI.COMM_SELF,
    )
    return directory, solution, facts


def _checkpoint_expected(facts: dict[str, object], **changes: object) -> dict[str, object]:
    expected: dict[str, object] = {
        "iteration": 20,
        "explicit_true_residual": 0.25,
        "input_identity_sha256": HASH,
        "operator_identity_sha256": "c" * 64,
        "physical_model_sha256": "d" * 64,
        "source_sha": SOURCE_SHA,
        "mpi_size": 1,
        "manifest_sha256": facts["manifest_sha256"],
    }
    expected.update(changes)
    return expected


def test_runner_resume_checkpoint_expected_binds_boundary_residual() -> None:
    provenance = {
        "input_identity_sha256": HASH,
        "operator_identity_sha256": "c" * 64,
        "physical_model_sha256": "d" * 64,
        "source_sha": SOURCE_SHA,
    }
    expected = runner_checkpoint_expected(
        provenance,
        iteration=20,
        explicit_true_residual=0.25,
        manifest_sha256="e" * 64,
        mpi_size=1,
    )
    assert set(expected) == {
        "iteration",
        "explicit_true_residual",
        "input_identity_sha256",
        "operator_identity_sha256",
        "physical_model_sha256",
        "source_sha",
        "mpi_size",
        "manifest_sha256",
    }
    assert expected["explicit_true_residual"] == pytest.approx(0.25)


def test_pair_bound_requires_measured_nonnegative_facts() -> None:
    assert residual_pair_bound(0.1, 0.2, 1.0e-12, physical=False) == pytest.approx(0.30000000001)
    with pytest.raises(ValueError):
        residual_pair_bound(0.1, float("nan"), 0.0, physical=False)


def test_restart20_cycles_destroy_cycles_and_count_initial_action(tmp_path: Path) -> None:
    size = 64
    matrix = PETSc.Mat().createAIJ([size, size], nnz=1, comm=PETSc.COMM_SELF)
    matrix.setUp()
    for index in range(size):
        matrix.setValue(index, index, 1.0 + 0.01 * index)
    matrix.assemble()
    rhs = matrix.createVecRight()
    rhs.array[:] = np.linspace(1.0, 2.0, size) + 0.25j
    checkpoint_facts: list[dict[str, object]] = []

    def action(vector: PETSc.Vec) -> PETSc.Vec:
        output = matrix.createVecLeft()
        matrix.mult(vector, output)
        return output

    def precondition(vector: PETSc.Vec) -> PETSc.Vec:
        return vector.copy()

    def resources() -> dict[str, object]:
        return _resource()

    def checkpoint_writer(
        iteration: int, solution: PETSc.Vec, explicit_true_residual: float
    ) -> dict[str, object]:
        directory = tmp_path / f"checkpoint-{iteration}"
        facts = write_solution_checkpoint(
            directory,
            solution,
            iteration=iteration,
            explicit_true_residual=explicit_true_residual,
            input_identity_sha256=HASH,
            operator_identity_sha256="c" * 64,
            physical_model_sha256="d" * 64,
            source_sha=SOURCE_SHA,
            ownership={
                "rank": 0,
                "ownership_range": list(solution.getOwnershipRange()),
                "local_size": solution.getLocalSize(),
                "global_size": solution.getSize(),
            },
            comm=MPI.COMM_SELF,
        )
        restored = matrix.createVecRight()
        try:
            read_solution_checkpoint(
                directory,
                restored,
                expected={
                    "iteration": iteration,
                    "explicit_true_residual": explicit_true_residual,
                    "input_identity_sha256": HASH,
                    "operator_identity_sha256": "c" * 64,
                    "physical_model_sha256": "d" * 64,
                    "source_sha": SOURCE_SHA,
                    "mpi_size": 1,
                    "manifest_sha256": facts["manifest_sha256"],
                },
                ownership={
                    "rank": 0,
                    "ownership_range": list(restored.getOwnershipRange()),
                    "local_size": restored.getLocalSize(),
                    "global_size": restored.getSize(),
                },
                comm=MPI.COMM_SELF,
            )
            facts["roundtrip_relative"] = float(
                np.linalg.norm(restored.array - solution.array)
                / max(np.linalg.norm(solution.array), np.finfo(float).tiny)
            )
        finally:
            restored.destroy()
        checkpoint_facts.append(facts)
        return facts

    result = run_restart20_cycles(
        rhs,
        action,
        precondition,
        max_it=40,
        start_iteration=0,
        residual_limit=1.0e-30,
        resource_sample=resources,
        checkpoint_writer=checkpoint_writer,
        stop_on_true_residual=False,
    )
    try:
        assert [cycle["start_iteration"] for cycle in result["cycles"]] == [0, 20]
        assert [cycle["end_iteration"] for cycle in result["cycles"]] == [20, 40]
        assert result["explicit_action_count"] == 3
        assert result["ksp_destroy_count"] == len(result["cycles"])
        assert all(cycle["ksp_destroyed"] is True for cycle in result["cycles"])
        assert "reported_history" not in result
        assert len(checkpoint_facts) == 1
        assert checkpoint_facts[0]["roundtrip_relative"] == pytest.approx(0.0)
    finally:
        destroy_krylov_result(result)
        rhs.destroy()
        matrix.destroy()


def test_checker_recomputes_pc_and_uses_outer_record_with_raw_subdirectory(tmp_path: Path) -> None:
    record_path, raw_dir = _synthetic_record(tmp_path)
    checked = check_record(record_path)
    assert checked["passed"], checked
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["raw_dir"] = str(record_path.parent.resolve())
    record_path.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    wrong_root = check_record(record_path)
    assert not wrong_root["passed"]
    assert any("artifact root mismatch" in error for error in wrong_root["contract_errors"])
    record["raw_dir"] = str(raw_dir.resolve())
    record_path.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    record["outer"]["rebuilt_provenance"]["input_identity_sha256"] = "e" * 64
    record_path.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    rebuilt_tamper = check_record(record_path)
    assert not rebuilt_tamper["passed"]
    assert any("rebuilt_provenance" in error for error in rebuilt_tamper["contract_errors"])
    record["outer"]["rebuilt_provenance"]["input_identity_sha256"] = HASH
    record_path.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    record["source"]["commit_sha_end"] = "f" * 40
    record_path.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    end_identity_tamper = check_record(record_path)
    assert not end_identity_tamper["passed"]
    assert any("commit SHA" in error for error in end_identity_tamper["contract_errors"])
    record["source"]["commit_sha_end"] = SOURCE_SHA
    record_path.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    record["pc_legality"]["phase_application"] = "not-finalized"
    record_path.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    audit_mismatch = check_record(record_path)
    assert not audit_mismatch["passed"]
    assert any("phase_application" in error for error in audit_mismatch["contract_errors"])
    record["pc_legality"]["phase_application"] = "finalized_floquet_mpc_once"
    record_path.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    combined_path = raw_dir / "output_combined.rank0.npy"
    values = np.load(combined_path, allow_pickle=False)
    values[1] += 0.25
    np.save(combined_path, values, allow_pickle=False)
    mutated = check_record(record_path)
    assert not mutated["passed"]
    assert mutated["contract_errors"]


def test_pc_artifact_descriptor_names_match_logical_keys(tmp_path: Path) -> None:
    record_path, _raw_dir = _synthetic_record(tmp_path)
    record = json.loads(record_path.read_text(encoding="utf-8"))
    for name in PC_NAMES:
        artifact = record["artifacts"][name]
        assert artifact["name"] == name
        assert artifact["role"] == name
    record["artifacts"]["output_first"]["name"] = "pc_output_first"
    record_path.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    checked = check_record(record_path)
    assert not checked["passed"]
    assert any("name/role identity" in error for error in checked["contract_errors"])


def test_shared_cgroup_swap_diagnostic_is_not_a_swap_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    authority = {
        "process_tree": {
            "root_pid": 1,
            "rss_bytes": 2,
            "swap_bytes": 0,
            "all_status_readable": True,
        },
        "job_cgroup": {
            "dedicated_job_cgroup": False,
            "path": "/init.scope",
            "readable": True,
            "swap_current_bytes": 13_799_424,
        },
        "memory_authority_bytes": 2,
        "job_no_swap": True,
    }
    monkeypatch.setattr(p0_runner, "resource_authority_sample", lambda _pid: authority)
    sample = p0_runner._resource_sample()
    assert sample["dedicated_cgroup_observed"] is False
    assert sample["dedicated_cgroup_path"] == "/init.scope"
    assert sample["dedicated_cgroup_swap_bytes"] is None


def test_dedicated_cgroup_nonzero_swap_is_a_gate(tmp_path: Path) -> None:
    record_path, _raw_dir = _synthetic_record(tmp_path)
    record = json.loads(record_path.read_text(encoding="utf-8"))
    for label in ("production_first_cycle", "restart", "continuous_reference"):
        for cycle in record["outer"][label]["cycles"]:
            cycle["resource"]["dedicated_cgroup_observed"] = True
            cycle["resource"]["dedicated_cgroup_path"] = "/job.slice/test"
            cycle["resource"]["dedicated_cgroup_readable"] = True
            cycle["resource"]["dedicated_cgroup_swap_bytes"] = 1
    record_path.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    checked = check_record(record_path)
    assert not checked["passed"]
    assert not checked["contract_errors"]
    assert any("dedicated cgroup swap is nonzero" in failure for failure in checked["gate_failures"])


def test_checkpoint_checker_rejects_extra_numeric_file(tmp_path: Path) -> None:
    record_path, raw_dir = _synthetic_record(tmp_path)
    (raw_dir / "checkpoint-20" / "unexpected.npy").write_bytes(b"extra")
    checked = check_record(record_path)
    assert not checked["passed"]
    assert any("directory contents" in error for error in checked["contract_errors"])


def test_checkpoint_explicit_residual_and_identity_sha_contracts(tmp_path: Path) -> None:
    record_path, raw_dir = _synthetic_record(tmp_path)
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["outer"]["checkpoint"]["explicit_true_residual"] = 0.5
    record_path.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    mismatch = check_record(record_path)
    assert not mismatch["passed"]
    assert any("explicit residual" in error for error in mismatch["contract_errors"])

    record["outer"]["checkpoint"]["explicit_true_residual"] = 0.25
    manifest_path = raw_dir / "checkpoint-20" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.pop("explicit_true_residual")
    manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
    missing = check_record(record_path)
    assert not missing["passed"]
    assert any("explicit_true_residual" in error for error in missing["contract_errors"])

    record["provenance"]["input_identity_sha256"] = "invalid"
    record_path.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    invalid_identity = check_record(record_path)
    assert not invalid_identity["passed"]
    assert any("64-character" in error for error in invalid_identity["contract_errors"])


def test_checkpoint_writer_rejects_non_hex_identity(tmp_path: Path) -> None:
    directory, solution, _facts = _real_checkpoint(tmp_path)
    try:
        with pytest.raises(ValueError):
            write_solution_checkpoint(
                tmp_path / "invalid-checkpoint",
                solution,
                iteration=20,
                explicit_true_residual=0.25,
                input_identity_sha256="invalid",
                operator_identity_sha256="c" * 64,
                physical_model_sha256="d" * 64,
                source_sha=SOURCE_SHA,
                ownership={
                    "rank": 0,
                    "ownership_range": [0, 2],
                    "local_size": 2,
                    "global_size": 2,
                },
                comm=MPI.COMM_SELF,
            )
    finally:
        solution.destroy()


def test_checker_rejects_checkpoint_outside_raw_checkpoint20(tmp_path: Path) -> None:
    record_path, raw_dir = _synthetic_record(tmp_path)
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["outer"]["checkpoint"]["manifest_path"] = str(
        (raw_dir.parent / "external" / "manifest.json").resolve()
    )
    record_path.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    checked = check_record(record_path)
    assert not checked["passed"]
    assert any("checkpoint manifest is not raw_dir/checkpoint-20" in error for error in checked["contract_errors"])


def test_checkpoint_reader_rejects_corruption_and_each_identity_mismatch(tmp_path: Path) -> None:
    directory, solution, facts = _real_checkpoint(tmp_path)
    restored = solution.duplicate()
    try:
        read_solution_checkpoint(
            directory,
            restored,
            expected=_checkpoint_expected(facts),
            ownership={
                "rank": 0,
                "ownership_range": [0, 2],
                "local_size": 2,
                "global_size": 2,
            },
            comm=MPI.COMM_SELF,
        )
        assert np.array_equal(restored.array, solution.array)
        for key, value in {
            "input_identity_sha256": "e" * 64,
            "operator_identity_sha256": "f" * 64,
            "physical_model_sha256": "1" * 64,
            "source_sha": "2" * 40,
            "mpi_size": 2,
        }.items():
            with pytest.raises(ValueError):
                read_solution_checkpoint(
                    directory,
                    restored,
                    expected=_checkpoint_expected(facts, **{key: value}),
                    ownership={
                        "rank": 0,
                        "ownership_range": [0, 2],
                        "local_size": 2,
                        "global_size": 2,
                    },
                    comm=MPI.COMM_SELF,
                )
        with pytest.raises(ValueError):
            read_solution_checkpoint(
                directory,
                restored,
                expected=_checkpoint_expected(facts),
                ownership={
                    "rank": 0,
                    "ownership_range": [0, 1],
                    "local_size": 1,
                    "global_size": 2,
                },
                comm=MPI.COMM_SELF,
            )
        shard_path = directory / "solution_rank0.npy"
        shard_bytes = shard_path.read_bytes()
        shard_path.write_bytes(b"corrupt-shard")
        with pytest.raises((ValueError, OSError)):
            read_solution_checkpoint(
                directory,
                restored,
                expected=_checkpoint_expected(facts),
                ownership={
                    "rank": 0,
                    "ownership_range": [0, 2],
                    "local_size": 2,
                    "global_size": 2,
                },
                comm=MPI.COMM_SELF,
            )
        shard_path.write_bytes(shard_bytes)
        manifest_path = directory / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["input_identity_sha256"] = "9" * 64
        manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
        with pytest.raises(ValueError):
            read_solution_checkpoint(
                directory,
                restored,
                expected=_checkpoint_expected(facts),
                ownership={
                    "rank": 0,
                    "ownership_range": [0, 2],
                    "local_size": 2,
                    "global_size": 2,
                },
                comm=MPI.COMM_SELF,
            )
    finally:
        restored.destroy()
        solution.destroy()


def test_checkpoint_is_one_solution_shard_without_forbidden_roles(tmp_path: Path) -> None:
    directory, solution, _facts = _real_checkpoint(tmp_path)
    try:
        assert {path.name for path in directory.iterdir()} == {
            "manifest.json",
            "solution_rank0.npy",
        }
        assert not any(
            token in path.name.lower()
            for path in directory.iterdir()
            for token in ("basis", "action", "residual")
        )
    finally:
        solution.destroy()


def test_resume_start_iteration_and_initial_solution_are_explicit(tmp_path: Path) -> None:
    vector = PETSc.Vec().createSeq(2, comm=PETSc.COMM_SELF)
    rhs = vector.copy()
    rhs.set(1.0 + 0.0j)

    def identity(value: PETSc.Vec) -> PETSc.Vec:
        return value.copy()

    with pytest.raises(ValueError):
        run_restart20_cycles(
            rhs,
            identity,
            identity,
            max_it=40,
            residual_limit=1.0e-8,
            resource_sample=_resource,
        )
    with pytest.raises(ValueError):
        run_restart20_cycles(
            rhs,
            identity,
            identity,
            max_it=40,
            start_iteration=20,
            residual_limit=1.0e-8,
            resource_sample=_resource,
        )
    with pytest.raises(ValueError):
        run_restart20_cycles(
            rhs,
            identity,
            identity,
            max_it=40,
            start_iteration=10,
            residual_limit=1.0e-8,
            resource_sample=_resource,
        )
    wrong_size = PETSc.Vec().createSeq(3, comm=PETSc.COMM_SELF)
    try:
        with pytest.raises(ValueError):
            run_restart20_cycles(
                rhs,
                identity,
                identity,
                max_it=40,
                start_iteration=20,
                initial_solution=wrong_size,
                residual_limit=1.0e-8,
                resource_sample=_resource,
            )
    finally:
        wrong_size.destroy()
        rhs.destroy()
        vector.destroy()


def test_pair_checker_requires_measured_facts_and_uses_both_margins(tmp_path: Path) -> None:
    record_path, _raw_dir = _synthetic_record(tmp_path)
    from benchmarks.task038_full3d_lor_hx_p0_checker import check_pair

    missing = check_pair(record_path, record_path, physical=False)
    assert not missing["passed"]
    assert any("pair_metrics" in error for error in missing["contract_errors"])
    assert residual_pair_bound(0.1, 0.2, 0.3, physical=False) == pytest.approx(0.60000000001)
    assert residual_pair_bound(0.1, 0.2, 0.3, physical=True) == pytest.approx(0.600000001)


def test_two_rank_record_closeout_smoke() -> None:
    if MPI.COMM_WORLD.Get_size() != 2:
        pytest.skip("run this lifecycle smoke with mpiexec -n 2")
    from benchmarks.run_task038_full3d_lor_hx_p0 import _closeout

    root_text = tempfile.mkdtemp(prefix="task038-p0-closeout-") if MPI.COMM_WORLD.rank == 0 else None
    root_text = MPI.COMM_WORLD.bcast(root_text, root=0)
    root = Path(root_text)
    raw_dir = root / "raw"
    record_path = root / "record.json"
    raw_dir.mkdir(parents=True, exist_ok=True)
    MPI.COMM_WORLD.barrier()
    _closeout(
        MPI.COMM_WORLD,
        raw_dir,
        record_path,
        {"schema": "p0-closeout-smoke"},
        {"rank": MPI.COMM_WORLD.rank, "value": 1},
    )
    assert record_path.is_file()
    MPI.COMM_WORLD.barrier()
    if MPI.COMM_WORLD.rank == 0:
        shutil.rmtree(root)
