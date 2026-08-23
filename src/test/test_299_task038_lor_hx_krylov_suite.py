"""Focused synthetic contracts for the parameterized K1 Krylov suite."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from benchmarks.task038_full3d_lor_hx_krylov_checker import (
    K0_GMRES_MAX_IT,
    K0_GMRES_RESTART,
    K0_GMRES_RTOL,
    K1_CASE_SPECS,
    K1_CHECKER_SCHEMA,
    K1_LINEARITY_STATUS,
    K1_SOURCE_FORMULAS,
    K1_SOURCE_NAMES,
    OLD_L2_CLASSIFICATION,
    OLD_L2_RECORD_SHA,
    OLD_L2_RHO,
    check_suite_record,
    check_suite_records,
)


def _write_array(
    raw_dir: Path,
    name: str,
    values: np.ndarray,
    descriptors: list[dict[str, object]],
) -> dict[str, str]:
    values = np.asarray(values)
    path = raw_dir / f"{name}.npy"
    np.save(path, values, allow_pickle=False)
    descriptors.append(
        {
            "name": name,
            "relative_path": path.name,
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "dtype": str(values.dtype),
            "shape": list(values.shape),
        }
    )
    return {"keys": f"{name}_keys", "values": name}


def _role(
    raw_dir: Path,
    name: str,
    keys: np.ndarray,
    values: np.ndarray,
    descriptors: list[dict[str, object]],
) -> dict[str, str]:
    key_name = f"{name}_keys"
    value_name = f"{name}_values"
    _write_array(raw_dir, key_name, np.asarray(keys, dtype="<U64"), descriptors)
    _write_array(
        raw_dir,
        value_name,
        np.asarray(values, dtype=np.complex128),
        descriptors,
    )
    return {"keys": key_name, "values": value_name}


def _synthetic_record(
    tmp_path: Path,
    case: str = "p2-mpi1",
    source_name: str = "random",
    *,
    iterations: int = 1,
    permute_dual: bool = False,
    mutate_final_solution: bool = False,
    mutate_final_action: bool = False,
) -> Path:
    degree, mpi_size = K1_CASE_SPECS[case]
    raw_dir = tmp_path / f"{case}-{source_name}"
    raw_dir.mkdir(parents=True)
    record_path = tmp_path / f"{case}-{source_name}.json"
    descriptors: list[dict[str, object]] = []
    source_keys = np.asarray(["source-a", "source-b", "source-c"], dtype="<U64")
    source_values = np.asarray([1.0 + 0.5j, -0.5 + 1.0j, 0.25 - 0.75j])
    dual_keys = np.asarray(["dual-a", "dual-b", "dual-c", "dual-d"], dtype="<U64")
    residual = np.asarray([2.0 + 0.5j, -1.0 + 1.0j, 0.5 - 2.0j, 1.0 + 0.25j])
    output_keys = np.asarray(["primal-a", "primal-b", "primal-c"], dtype="<U64")
    output = np.asarray([1.0 + 0.25j, -0.5 + 1.0j, 2.0 - 0.75j])
    dual_order = np.asarray([2, 0, 3, 1]) if permute_dual else np.arange(4)
    stored_dual_keys = dual_keys[dual_order]
    stored_residual = residual[dual_order]
    if mutate_final_action:
        stored_residual = 1.25 * stored_residual
    applied = stored_residual.copy()
    true_residual = stored_residual - applied
    final_relative = float(np.linalg.norm(true_residual) / np.linalg.norm(stored_residual))
    stored_output = output.copy()
    if mutate_final_solution:
        stored_output[0] += 0.125

    one_apply = {
        "source_before": _role(raw_dir, "source_before", source_keys, source_values, descriptors),
        "source_after": _role(raw_dir, "source_after", source_keys, source_values, descriptors),
        "residual_before": _role(raw_dir, "residual_before", stored_dual_keys, stored_residual, descriptors),
        "residual_after": _role(raw_dir, "residual_after", stored_dual_keys, stored_residual, descriptors),
        "residual": _role(raw_dir, "residual", stored_dual_keys, stored_residual, descriptors),
        "pc_output": _role(raw_dir, "pc_output", output_keys, output, descriptors),
        "pc_repeat": _role(raw_dir, "pc_repeat", output_keys, output, descriptors),
        "applied_output": _role(raw_dir, "applied_output", stored_dual_keys, stored_residual, descriptors),
        "true_residual": _role(raw_dir, "true_residual", stored_dual_keys, np.zeros(4, dtype=np.complex128), descriptors),
    }

    checkpoint_records: dict[str, dict[str, object]] = {}
    history: list[dict[str, object]] = []
    for iteration in range(iterations + 1):
        passed = iteration == iterations
        history.append(
            {
                "iteration": iteration,
                "reported_unpreconditioned_relative": final_relative if passed else 1.0,
                "explicit_true_residual": final_relative if passed else 1.0,
                "matvec_count": iteration,
                "pc_apply_count": 2 * iteration,
                "monitor_action_count": iteration + 1,
                "elapsed_seconds": float(iteration),
            }
        )
    for checkpoint in (0, 1, 2, 5, 10, 20, 40, 80, 120, 160, 200):
        if checkpoint <= iterations:
            measured_action = applied if checkpoint == iterations else np.zeros(4, dtype=np.complex128)
            measured_true = stored_residual - measured_action
            checkpoint_records[str(checkpoint)] = {
                "status": "measured",
                "artifacts": {
                    "solution": _role(
                        raw_dir,
                        f"checkpoint_{checkpoint}_solution",
                        output_keys,
                        stored_output if checkpoint == iterations else np.zeros(3, dtype=np.complex128),
                        descriptors,
                    ),
                    "action": _role(
                        raw_dir,
                        f"checkpoint_{checkpoint}_action",
                        stored_dual_keys,
                        measured_action,
                        descriptors,
                    ),
                    "true_residual": _role(
                        raw_dir,
                        f"checkpoint_{checkpoint}_true",
                        stored_dual_keys,
                        measured_true,
                        descriptors,
                    ),
                },
            }
        else:
            checkpoint_records[str(checkpoint)] = {
                "status": "not_run_after_convergence"
            }

    rank_facts = [
        {
            "rank": rank,
            "runtime": {
                "qualified_activation": "1",
                "mpi_size": mpi_size,
                "petsc_scalar_type": "complex128",
                "petsc_int_type": "int32",
                "sys_executable": "/usr/bin/python3",
                "qualified_venv_bin_resolved": "/usr/bin",
            },
            "matvec_count": iterations,
            "pc_apply_count": 2 * iterations,
            "monitor_action_count": iterations + 1,
            "iterations": iterations,
            "reason": 2,
        }
        for rank in range(mpi_size)
    ]
    final_roles = {
        "solution": _role(raw_dir, "final_solution", output_keys, stored_output, descriptors),
        "action": _role(raw_dir, "final_action", stored_dual_keys, applied, descriptors),
        "true_residual": _role(raw_dir, "final_true", stored_dual_keys, true_residual, descriptors),
    }
    record = {
        "schema": "task038.lor-native-complex-hx.k1-suite-record.v1",
        "stage": "k1-suite",
        "scope": "krylov_requalification_suite",
        "case": case,
        "degree": degree,
        "source_name": source_name,
        "mpi_size": mpi_size,
        "raw_dir": str(raw_dir.resolve()),
        "command": [
            "/usr/bin/python3",
            "-m",
            "benchmarks.run_task038_full3d_lor_hx_krylov",
            "--stage",
            "k1-suite",
            "--case",
            case,
            "--source",
            source_name,
            "--raw-dir",
            str(raw_dir.resolve()),
            "--record",
            str(record_path.resolve()),
            "--expected-source-sha",
            "a" * 40,
            "--expected-mpi-size",
            str(mpi_size),
        ],
        "source": {
            "expected_sha": "a" * 40,
            "commit_sha_start": "a" * 40,
            "commit_sha_end": "a" * 40,
            "branch": "codex/20260820-task38-extra-full3d-iterative-0p7nm",
            "clean_start": True,
            "clean_end": True,
            "probe_rank": 0,
            "probe_scope": "rank0_git_probe_broadcast",
        },
        "runtime": rank_facts[0]["runtime"],
        "rank_facts": rank_facts,
        "settings": {
            "ksp_type": "gmres",
            "pc_side": "right",
            "norm_type": "unpreconditioned",
            "restart": K0_GMRES_RESTART,
            "max_it": K0_GMRES_MAX_IT,
            "rtol": K0_GMRES_RTOL,
            "atol": 0.0,
            "initial_guess_nonzero": False,
        },
        "old_l2_reference": {
            "record_sha256": OLD_L2_RECORD_SHA,
            "rho": OLD_L2_RHO,
            "limit": 0.45,
            "classification": OLD_L2_CLASSIFICATION,
        },
        "linearity_authority": {
            "status": K1_LINEARITY_STATUS,
            "record_sha256": "87594e2c06de8ea031dad0ce8ac364626dcc2dbb6d9ff8846ad6f19663d9098d",
            "checker_sha256": "0ad2b91aceb08b5cdd5ae68944f3625689f0a3f38c2ae0dfeb43461a827df807",
            "old_one_apply_rho": OLD_L2_RHO,
            "old_one_apply_classification": OLD_L2_CLASSIFICATION,
        },
        "source_facts": {
            "name": source_name,
            "formula": K1_SOURCE_FORMULAS[source_name],
            "phase_application": "algebraic_slave_zero_action_internal_finalized_mpc_once",
        },
        "one_apply": {
            "artifacts": one_apply,
            "input_role": "dual",
            "output_role": "primal",
            "rho": 0.0,
            "rho_status": "diagnostic_only_not_a_gate",
            "residual_norm": float(np.linalg.norm(stored_residual)),
            "finite": True,
            "source_unchanged": True,
            "residual_input_unchanged": True,
            "repeat_relative": 0.0,
            "alpha_status": "not_repeated_by_contract",
        },
        "krylov": {
            "history": history,
            "checkpoints": checkpoint_records,
            "final_artifacts": final_roles,
            "reason": 2,
            "iterations": iterations,
            "first_true_pass_iteration": iterations,
            "late_true_pass_iteration": None,
            "qualification_pass": True,
            "reported_final_residual": 0.0,
            "final_true_residual": final_relative,
            "matvec_count": iterations,
            "pc_apply_count": 2 * iterations,
            "monitor_action_count": iterations + 1,
            "final_action_count": 1,
        },
        "count_ranges": {
            "matvec_count": {"min": iterations, "max": iterations},
            "pc_apply_count": {"min": 2 * iterations, "max": 2 * iterations},
            "monitor_action_count": {"min": iterations + 1, "max": iterations + 1},
        },
        "production": {
            "production_pc_alpha_applied": False,
            "global_numeric_allgather": False,
            "high_order_global_aij": False,
            "global_dense_transfer": False,
            "global_direct_coarse": False,
        },
        "forbidden": {
            "production_pc_alpha_applied": False,
            "global_numeric_allgather": False,
            "high_order_global_aij": False,
            "global_dense_transfer": False,
            "global_direct_coarse": False,
        },
        "artifacts": descriptors,
        "status": "facts_written_no_worker_classification",
    }
    record_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record_path


def _rewrite_role_values(record_path: Path, role: str, values: np.ndarray) -> None:
    record = json.loads(record_path.read_text(encoding="utf-8"))
    role_descriptor_names = record["one_apply"]["artifacts"][role]
    value_name = role_descriptor_names["values"]
    descriptor = next(
        item for item in record["artifacts"] if item["name"] == value_name
    )
    path = Path(record["raw_dir"]) / descriptor["relative_path"]
    values = np.asarray(values, dtype=np.complex128)
    np.save(path, values, allow_pickle=False)
    descriptor["bytes"] = path.stat().st_size
    descriptor["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    descriptor["dtype"] = str(values.dtype)
    descriptor["shape"] = list(values.shape)
    record_path.write_text(json.dumps(record, indent=2), encoding="utf-8")


def test_k1_synthetic_record_accepts_nested_final_and_checkpoint_facts(tmp_path: Path) -> None:
    result = check_suite_record(_synthetic_record(tmp_path))
    assert result["schema"] == K1_CHECKER_SCHEMA
    assert result["passed"] is True, result


def test_k1_checker_rejects_mutated_raw_rho_alpha_and_old_l2(tmp_path: Path) -> None:
    record_path = _synthetic_record(tmp_path)
    record = json.loads(record_path.read_text())
    record["one_apply"]["rho"] = 0.25
    record["one_apply"]["alpha_status"] = "repeated"
    record["one_apply"]["rho_alpha"] = 0.0
    record["old_l2_reference"]["rho"] = 0.0
    record["old_l2_reference"]["limit"] = 0.4
    record_path.write_text(json.dumps(record), encoding="utf-8")
    result = check_suite_record(record_path)
    assert result["passed"] is False
    assert any("rho" in item for item in result["contract_errors"])
    assert any("alpha" in item for item in result["contract_errors"])
    assert any("old L2 rho" in item for item in result["contract_errors"])
    assert any("old L2 limit" in item for item in result["contract_errors"])


def test_k1_one_apply_numeric_failures_are_gate_failures(tmp_path: Path) -> None:
    finite_path = _synthetic_record(tmp_path, source_name="gradient")
    finite_record = json.loads(finite_path.read_text())
    _rewrite_role_values(
        finite_path,
        "pc_output",
        np.asarray([np.nan + 0.0j, -0.5 + 1.0j, 2.0 - 0.75j]),
    )
    finite_record = json.loads(finite_path.read_text())
    finite_record["one_apply"]["finite"] = False
    finite_path.write_text(json.dumps(finite_record, indent=2), encoding="utf-8")
    result = check_suite_record(finite_path)
    assert result["passed"] is False
    assert result["contract_errors"] == []
    assert any("non-finite" in item for item in result["gate_failures"])

    source_path = _synthetic_record(tmp_path, source_name="curl")
    source_record = json.loads(source_path.read_text())
    source_values = np.asarray([1.0 + 0.5j, -0.5 + 1.0j, 0.25 - 0.75j])
    source_values[0] += 1.0
    _rewrite_role_values(source_path, "source_after", source_values)
    source_record = json.loads(source_path.read_text())
    source_record["one_apply"]["source_unchanged"] = False
    source_path.write_text(json.dumps(source_record, indent=2), encoding="utf-8")
    result = check_suite_record(source_path)
    assert result["passed"] is False
    assert result["contract_errors"] == []
    assert any("primal source" in item for item in result["gate_failures"])

    repeat_path = _synthetic_record(tmp_path, source_name="checkerboard")
    repeat_record = json.loads(repeat_path.read_text())
    repeat_values = np.asarray([1.0 + 0.25j, -0.5 + 1.0j, 2.0 - 0.75j])
    repeat_values[0] += 0.01
    _rewrite_role_values(repeat_path, "pc_repeat", repeat_values)
    repeat_record = json.loads(repeat_path.read_text())
    reference = np.asarray([1.0 + 0.25j, -0.5 + 1.0j, 2.0 - 0.75j])
    repeat_record["one_apply"]["repeat_relative"] = float(
        np.linalg.norm(repeat_values - reference) / np.linalg.norm(reference)
    )
    repeat_path.write_text(json.dumps(repeat_record, indent=2), encoding="utf-8")
    result = check_suite_record(repeat_path)
    assert result["passed"] is False
    assert result["contract_errors"] == []
    assert any("PC repeat" in item for item in result["gate_failures"])


def test_k1_aggregate_accepts_all_16_and_mpi_packet_permutation(tmp_path: Path) -> None:
    paths = []
    for case in K1_CASE_SPECS:
        for source in K1_SOURCE_NAMES:
            paths.append(
                _synthetic_record(
                    tmp_path,
                    case,
                    source,
                    iterations=2 if case.startswith("p3") else 1,
                    permute_dual=case.endswith("mpi2"),
                )
            )
    result = check_suite_records(paths)
    assert result["passed"] is True, result
    assert set(result["cross_mpi_relative"]) == {
        f"p{degree}/{source}/{role}"
        for degree in (2, 3)
        for source in K1_SOURCE_NAMES
        for role in ("solution", "action", "residual")
    }


def test_k1_aggregate_rejects_missing_duplicate_and_mpi_identity(tmp_path: Path) -> None:
    paths = [
        _synthetic_record(tmp_path, case, source)
        for case in K1_CASE_SPECS
        for source in K1_SOURCE_NAMES
    ]
    missing = check_suite_records(paths[:-1])
    assert missing["passed"] is False
    assert any("exactly 16" in item or "missing" in item for item in missing["contract_errors"])
    duplicate = check_suite_records(paths[:-1] + [paths[0]])
    assert duplicate["passed"] is False
    assert any("duplicate" in item for item in duplicate["contract_errors"])


def test_k1_aggregate_rejects_cross_mpi_solution_action_and_iteration_mutations(
    tmp_path: Path,
) -> None:
    paths = []
    for case in K1_CASE_SPECS:
        for source in K1_SOURCE_NAMES:
            mutate_solution = case == "p2-mpi2" and source == "random"
            mutate_action = case == "p3-mpi2" and source == "gradient"
            iterations = 12 if case == "p3-mpi1" and source == "curl" else 1
            paths.append(
                _synthetic_record(
                    tmp_path,
                    case,
                    source,
                    iterations=iterations,
                    mutate_final_solution=mutate_solution,
                    mutate_final_action=mutate_action,
                )
            )
    result = check_suite_records(paths)
    assert result["passed"] is False
    assert any("cross-MPI solution" in item for item in result["gate_failures"])
    assert any("cross-MPI action" in item for item in result["gate_failures"])
    assert any("p3 iterations exceed" in item for item in result["gate_failures"])


def test_k1_numeric_failure_keeps_cross_mpi_facts(tmp_path: Path) -> None:
    paths = []
    for case in K1_CASE_SPECS:
        for source in K1_SOURCE_NAMES:
            paths.append(_synthetic_record(tmp_path, case, source))
    failing = paths[0]
    record = json.loads(failing.read_text())
    _rewrite_role_values(
        failing,
        "pc_output",
        np.asarray([np.nan + 0.0j, -0.5 + 1.0j, 2.0 - 0.75j]),
    )
    record = json.loads(failing.read_text())
    record["one_apply"]["finite"] = False
    failing.write_text(json.dumps(record, indent=2), encoding="utf-8")
    result = check_suite_records(paths)
    assert result["passed"] is False
    assert result["contract_errors"] == []
    assert any("non-finite" in item for item in result["gate_failures"])
    assert len(result["cross_mpi_relative"]) == 24


def test_k1_checker_rejects_formula_and_settings_mutations(tmp_path: Path) -> None:
    record_path = _synthetic_record(tmp_path)
    record = json.loads(record_path.read_text())
    record["source_facts"]["formula"] = "changed"
    record["settings"]["pc_side"] = "left"
    record_path.write_text(json.dumps(record), encoding="utf-8")
    result = check_suite_record(record_path)
    assert result["passed"] is False
    assert any("source formula" in item for item in result["contract_errors"])
    assert any("setting pc_side" in item for item in result["contract_errors"])
