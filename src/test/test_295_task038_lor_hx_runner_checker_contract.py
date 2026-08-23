"""Pure contracts for the thin L1 LOR/HX runner and checker."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from benchmarks import task038_full3d_lor_hx_checker as checker
from benchmarks import run_task038_full3d_lor_hx as runner


def _identity_record(case: str, status: str) -> dict:
    degree = int(case[1])
    mpi_size = int(case[-1])
    runtime = {
        "qualified_activation": "1",
        "mpi_size": mpi_size,
        "petsc_scalar_type": "complex128",
        "petsc_int_type": "int32",
        "sys_executable": "/repo/.venv/bin/python",
    }
    topology_audit = {
        "owner_local_maps": True,
        "global_transfer_matrix": False,
        "numeric_allgather": False,
        "phase_application": "once_in_canonical_owner_route",
        "edge_orientation": "dolfinx_cell_permutation_Tt_then_T",
        "cell_permutation": "Tt_before_high_to_lor_and_T_after_lor_to_high",
        "mpc_slave_master": "finalized_mpc_homogenize_backsubstitution",
        "floquet_phase": "complete_slave_edge_mapped_to_master_once",
        "slave_master_complete": True,
    }
    record = {
        "schema": checker.SCHEMA,
        "stage": "l1",
        "case": case,
        "degree": degree,
        "mpi_size": mpi_size,
        "source": {
            "expected_sha": "a" * 40,
            "commit_sha_start": "a" * 40,
            "commit_sha_end": "a" * 40,
            "branch": checker.BRANCH,
            "clean_start": True,
            "clean_end": True,
        },
        "runtime": {
            **runtime,
        },
        "rank_facts": [
            {"rank": rank, "runtime": {**runtime}}
            for rank in range(mpi_size)
        ],
        "canonical_mpi_identity": {
            "status": status,
            "production_numeric_allgather": False,
            "audit": {"topology_audit": topology_audit} if degree in {2, 3} else {},
        },
        "forbidden": {
            "global_numeric_allgather": False,
            "global_aij_in_production": False,
            "global_schur": False,
            "global_direct_coarse": False,
            "per_rank_full_basis_replication": False,
            "production_dense_transfer": False,
        },
        "production": {
            "global_transfer_matrix": False,
            "local_tensor_action": True,
            "owner_local_maps": True,
            "numeric_allgather": False,
            "retained_dense_transfer_bytes": 0,
            "local_dense_oracle_only": True,
        },
    }
    return record


def _canonical_arrays() -> dict[str, np.ndarray]:
    source_key = "0123456789abcdef" * 4
    action_key = "fedcba9876543210" * 4
    values = {
        "canonical_source": (source_key, 1.0 + 2.0j),
        "canonical_mapped_source": (source_key, 1.0 + 2.0j),
        "canonical_action": (action_key, 3.0 + 4.0j),
        "canonical_mapped_action": (action_key, 3.0 + 4.0j),
        "canonical_repeat": (action_key, 3.0 + 4.0j),
    }
    arrays: dict[str, np.ndarray] = {}
    for name, (key, value) in values.items():
        arrays[f"{name}_keys"] = np.asarray([key], dtype="<U64")
        arrays[f"{name}_values"] = np.asarray([value], dtype=np.complex128)
    arrays["canonical_lor_keys"] = np.asarray([7], dtype=np.uint32)
    arrays["canonical_lor_values"] = np.asarray([5.0 + 6.0j], dtype=np.complex128)
    return arrays


def _reference_arrays(degree: int = 2) -> tuple[dict[str, np.ndarray], dict]:
    block = degree * (degree + 1) ** 2
    edge_count = 3 * block
    dense = np.eye(edge_count, dtype=np.complex128)
    arrays = {
        "high_to_lor": dense,
        "lor_to_high": dense.copy(),
        "probe": np.arange(edge_count, dtype=np.float64) + 1j,
        "reference_probe_forward_1": np.arange(edge_count, dtype=np.float64) + 1j,
        "reference_probe_forward_2": np.arange(edge_count, dtype=np.float64) + 1j,
        "reference_probe_inverse_1": np.arange(edge_count, dtype=np.float64) + 1j,
        "reference_probe_inverse_2": np.arange(edge_count, dtype=np.float64) + 1j,
    }
    shapes = (
        (degree, degree + 1, degree + 1),
        (degree + 1, degree, degree + 1),
        (degree + 1, degree + 1, degree),
    )
    for axis, shape in enumerate(shapes):
        group = np.arange(axis * block, (axis + 1) * block, dtype=np.int32)
        arrays[f"reference_group_{axis}"] = group
        arrays[f"reference_forward_tensor_{axis}"] = np.eye(block, dtype=np.complex128).reshape(
            (block,) + shape
        )
        arrays[f"reference_inverse_tensor_{axis}"] = np.eye(block, dtype=np.complex128).reshape(
            (block,) + shape
        )
    record = {
        "degree": degree,
        "production": {"retained_dense_transfer_bytes": 0},
    }
    return arrays, record


def _write_record(tmp_path: Path, name: str, record: dict) -> Path:
    raw = tmp_path / f"{name}.raw"
    raw.mkdir()
    artifacts = []
    for artifact_name, array in record.pop("_arrays", {}).items():
        path = raw / f"{artifact_name}.npy"
        np.save(path, array, allow_pickle=False)
        artifacts.append(
            {
                "name": artifact_name,
                "relative_path": path.name,
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "dtype": str(array.dtype),
                "shape": list(array.shape),
            }
        )
    record["raw_dir"] = str(raw)
    record["artifacts"] = artifacts
    path = tmp_path / f"{name}.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    return path


def test_l1_checker_requires_exact_five_cases_and_accepts_p6_na(tmp_path: Path) -> None:
    p6 = _identity_record("p6-mpi1", "not_applicable_by_frozen_case")
    assert checker._identity_errors(p6) == []
    p2 = _identity_record("p2-mpi1", "measured")
    result = checker.check_records([])
    assert result["passed"] is False
    assert checker._identity_errors(p2) == []
    bad_production = {
        **p2,
        "production": {**p2["production"], "owner_local_maps": False},
    }
    assert any("owner_local_maps" in error for error in checker._identity_errors(bad_production))
    bad_topology = json.loads(json.dumps(p2))
    bad_topology["canonical_mpi_identity"]["audit"]["topology_audit"]["slave_master_complete"] = False
    assert any("slave_master_complete" in error for error in checker._identity_errors(bad_topology))
    bad_rank = json.loads(json.dumps(p2))
    bad_rank["rank_facts"][0]["runtime"]["petsc_int_type"] = "int64"
    assert any("rank fact PETSc ABI" in error for error in checker._identity_errors(bad_rank))
    duplicate = _identity_record("p2-mpi1", "measured")
    duplicate_path = _write_record(tmp_path, "duplicate", duplicate)
    result = checker.check_records([duplicate_path, duplicate_path])
    assert result["records"][0]["raw_record_sha256"] == hashlib.sha256(
        duplicate_path.read_bytes()
    ).hexdigest()
    assert result["records"][0]["source_sha"] == "a" * 40
    assert any("duplicate cases" in error for error in result["errors"])
    assert any("aggregate missing cases" in error for error in result["errors"])


def test_l1_stage_markers_are_per_rank_append_only_and_flush(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    runner._append_stage_marker(raw_dir, "paths_ready", 1)
    runner._append_stage_marker(raw_dir, "source_identity_closed", 1)
    marker_path = raw_dir / "stage-rank1.jsonl"
    lines = marker_path.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["stage"] for line in lines] == [
        "paths_ready",
        "source_identity_closed",
    ]
    assert all(json.loads(line)["rank"] == 1 for line in lines)
    assert all(isinstance(json.loads(line)["time"], float) for line in lines)


def test_l1_apply_copy_preserves_borrowed_action_output() -> None:
    class Borrowed:
        def __init__(self) -> None:
            self.value = None
            self.destroy_calls = 0

        def copy(self):
            return type("OwnedCopy", (), {"value": self.value})()

        def destroy(self) -> None:
            self.destroy_calls += 1

    class FakeAction:
        def __init__(self) -> None:
            self.output = Borrowed()

        def apply(self, value):
            self.output.value = value
            return self.output

    action = FakeAction()
    first = runner._apply_copy(action, 1)
    second = runner._apply_copy(action, 2)
    assert first.value == 1
    assert second.value == 2
    assert first is not second
    assert action.output.destroy_calls == 0


def test_l1_checker_canonical_internal_and_mpi_mutations_fail() -> None:
    record = _identity_record("p2-mpi1", "measured")
    arrays = _canonical_arrays()
    assert checker._canonical_identity(record, arrays)["errors"] == []
    arrays["canonical_mapped_source_keys"] = np.asarray(
        ["f" * 64], dtype="<U64"
    )
    assert checker._canonical_identity(record, arrays)["errors"]
    arrays = _canonical_arrays()
    arrays["canonical_mapped_action_values"][0] += 1.0e-6
    assert checker._canonical_identity(record, arrays)["errors"]
    arrays = _canonical_arrays()
    arrays["canonical_lor_values"][0] += 1.0e-6
    assert not np.allclose(
        arrays["canonical_lor_values"], _canonical_arrays()["canonical_lor_values"], rtol=0.0, atol=1.0e-12
    )


def test_l1_checker_reconstructs_reference_axis_blocks_and_catches_mutation() -> None:
    arrays, record = _reference_arrays()
    checked = checker._check_reference_factor(record, arrays)
    assert not checked["errors"]
    arrays["reference_forward_tensor_1"] = arrays["reference_forward_tensor_1"].copy()
    arrays["reference_forward_tensor_1"][0, 0, 0, 0] += 1.0e-4
    checked = checker._check_reference_factor(record, arrays)
    assert any("packed reference action" in error for error in checked["errors"])


def test_l1_checker_gates_hermitian_before_generalized_spectrum() -> None:
    degree = 2
    edge_count = 3 * degree * (degree + 1) ** 2
    identity = np.eye(edge_count, dtype=np.complex128)
    zero = np.zeros(edge_count, dtype=np.complex128)
    arrays = {
        "high_to_lor": identity.copy(),
        "lor_to_high": identity.copy(),
        "probe": np.arange(edge_count, dtype=np.float64) + 1j,
        "local_probe_forward_1": np.arange(edge_count, dtype=np.float64) + 1j,
        "local_probe_forward_2": np.arange(edge_count, dtype=np.float64) + 1j,
        "local_probe_roundtrip": np.arange(edge_count, dtype=np.float64) + 1j,
        "high_matrix": identity.copy(),
        "lor_matrix": identity.copy(),
        "high_gradient_edge": zero.copy(),
        "lor_gradient": identity.copy(),
        "h1_transfer": zero.copy(),
        "lor_curl_incidence": np.zeros((edge_count, edge_count), dtype=np.complex128),
        "high_curl_face": np.zeros((edge_count, edge_count), dtype=np.complex128),
    }
    checked = checker._check_local_algebra({"degree": degree}, arrays)
    assert not checked["errors"]
    arrays["high_matrix"] = identity.copy()
    arrays["high_matrix"][0, 1] = 1.0e-3
    checked = checker._check_local_algebra({"degree": degree}, arrays)
    assert any("Hermitian/SPD prerequisite" in error for error in checked["errors"])
    assert "spectral_lambda_min" not in checked


def test_l1_checker_recomputes_real_p2_derham_from_raw_gradient() -> None:
    from src.solvers.fullspace_lor_transfer import build_local_lor_transfer

    local = build_local_lor_transfer(2)
    edge_count = local.high_to_lor_matrix.shape[0]
    probe = np.arange(edge_count, dtype=np.float64) + 1j
    arrays = {
        "high_to_lor": local.high_to_lor_matrix,
        "lor_to_high": local.lor_to_high_matrix,
        "probe": probe,
        "local_probe_forward_1": local.high_to_lor_matrix @ probe,
        "local_probe_forward_2": local.high_to_lor_matrix @ probe,
        "local_probe_roundtrip": local.lor_to_high_matrix @ (local.high_to_lor_matrix @ probe),
        "high_matrix": local.high_matrix,
        "lor_matrix": local.lor_matrix,
        "high_gradient_edge": local.high_gradient_edge,
        "lor_gradient": local.lor_gradient,
        "h1_transfer": local.h1_transfer,
        "lor_curl_incidence": local.lor_curl_incidence,
        "high_curl_face": local.high_curl_face,
    }
    checked = checker._check_local_algebra({"degree": 2}, arrays)
    assert not checked["errors"]
    assert checked["de_rham_gradient_commuting_relative"] <= 1.0e-12
    assert checked["curl_transferred_gradient_relative"] <= 1.0e-12

    mutated = {name: value.copy() for name, value in arrays.items()}
    mutated["high_gradient_edge"][0] += 1.0e-3
    checked = checker._check_local_algebra({"degree": 2}, mutated)
    assert any("gradient commuting error" in error for error in checked["errors"])


def test_l1_checker_cross_mpi_keys_and_values_are_real_pair_gates(tmp_path: Path) -> None:
    left = _identity_record("p2-mpi1", "measured")
    left["_arrays"] = _canonical_arrays()
    right = _identity_record("p2-mpi2", "measured")
    right["_arrays"] = _canonical_arrays()
    left_path = _write_record(tmp_path, "left", left)
    right_path = _write_record(tmp_path, "right", right)
    metrics, errors = checker._compare_canonical_records(left_path, right_path)
    assert not errors
    assert metrics["source_mpi_relative"] <= 1.0e-12
    right_mutated = _identity_record("p2-mpi2", "measured")
    right_mutated["_arrays"] = _canonical_arrays()
    right_mutated["_arrays"]["canonical_action_values"][0] += 1.0e-4
    right_mutated_path = _write_record(tmp_path, "right_mutated", right_mutated)
    _metrics, errors = checker._compare_canonical_records(left_path, right_mutated_path)
    assert any("action canonical MPI relative" in error for error in errors)
    right_lor_mutated = _identity_record("p2-mpi2", "measured")
    right_lor_mutated["_arrays"] = _canonical_arrays()
    right_lor_mutated["_arrays"]["canonical_lor_values"][0] += 1.0e-4
    right_lor_path = _write_record(tmp_path, "right_lor_mutated", right_lor_mutated)
    _metrics, errors = checker._compare_canonical_records(left_path, right_lor_path)
    assert any("owner-LOR canonical MPI relative" in error for error in errors)


def _l2_synthetic_arrays(
    measured_names: tuple[str, ...],
    applied_fraction: float = 1.0,
    cg_solution_offset: complex = 0.0j,
    cg_action_offset: complex = 0.0j,
) -> dict[str, np.ndarray]:
    primal_keys = np.asarray(["p0", "p1"], dtype="<U64")
    dual_keys = np.asarray(["d0", "d1"], dtype="<U64")
    source = np.asarray([1.0 + 0.5j, -2.0 + 0.25j], dtype=np.complex128)
    pc_output = np.asarray([0.5 - 0.25j, 1.0 + 0.125j], dtype=np.complex128)
    residual = np.asarray([2.0 + 1.0j, 4.0 - 0.5j], dtype=np.complex128)
    applied = applied_fraction * residual
    true_residual = residual - applied
    cg_solution = np.asarray([1.0 + 0.25j, 2.0 - 0.5j], dtype=np.complex128)
    cg_solution += cg_solution_offset
    cg_action = residual + cg_action_offset
    cg_true_residual = residual - cg_action
    arrays: dict[str, np.ndarray] = {}
    for name in measured_names:
        names = checker._l2_artifact_names(name)
        for label, keys, values in (
            ("source_before", primal_keys, source),
            ("source_after", primal_keys, source),
            ("pc_output", primal_keys, pc_output),
            ("pc_repeat", primal_keys, pc_output),
            ("residual", dual_keys, residual),
            ("applied_output", dual_keys, applied),
            ("true_residual", dual_keys, true_residual),
            ("cg_solution", primal_keys, cg_solution),
            ("cg_action", dual_keys, cg_action),
            ("cg_true_residual", dual_keys, cg_true_residual),
        ):
            arrays[f"{names[label]}_keys"] = keys.copy()
            arrays[f"{names[label]}_values"] = values.copy()
    return arrays


def _l2_synthetic_record(
    case: str,
    iterations: int = 4,
    measured_names: tuple[str, ...] = checker.L2_SOURCE_NAMES,
    applied_fraction: float = 1.0,
    cg_solution_offset: complex = 0.0j,
    cg_action_offset: complex = 0.0j,
) -> dict:
    degree = int(case[1])
    mpi_size = int(case[-1])
    runtime = {
        "qualified_activation": "1",
        "mpi_size": mpi_size,
        "petsc_scalar_type": "complex128",
        "petsc_int_type": "int32",
        "sys_executable": "/repo/.venv/bin/python",
    }
    hx_audit = {
        "edge_jacobi_omega": 2.0 / 3.0,
        "edge_jacobi_pre": True,
        "edge_jacobi_post": True,
        "gradient_correction_count": 1,
        "vector_correction_order": "x_then_y_then_z",
        "nodal_correction_count": 4,
        "one_v_cycle_per_nodal_correction": True,
        "one_shared_scalar_hierarchy": True,
        "hierarchy_object_count": 1,
        "pc_type": "gamg",
        "pc_gamg_type": "agg",
        "maximum_levels": 8,
        "observed_levels": 2,
        "coarse_ksp_type": "preonly",
        "coarse_pc_type": "jacobi",
        "global_transfer_matrix": False,
        "global_numeric_allgather": False,
        "global_direct_coarse": False,
        "high_order_aij": False,
        "real_imag_split": False,
        "hypre_ams": False,
    }
    source_facts = []
    synthetic_residual = np.asarray(
        [2.0 + 1.0j, 4.0 - 0.5j], dtype=np.complex128
    )
    synthetic_cg_true = synthetic_residual - (
        synthetic_residual + cg_action_offset
    )
    cg_true_residual_relative = float(
        np.linalg.norm(synthetic_cg_true) / np.linalg.norm(synthetic_residual)
    )
    for name in checker.L2_SOURCE_NAMES:
        names = checker._l2_artifact_names(name)
        if name in measured_names:
            rho = abs(1.0 - applied_fraction)
            source_facts.append(
                {
                    "name": name,
                    "status": "measured",
                    "formula": checker.L2_SOURCE_FORMULAS[name],
                    "artifact_names": names,
                    "phase_application": checker.L2_PHASE_APPLICATION,
                    "rho": rho,
                    "rho_limit": checker.L2_RHO_LIMITS[name],
                    "repeat_relative": 0.0,
                    "repeat_limit": checker.L2_REPEAT_LIMIT,
                    "input_unchanged": True,
                    "finite": True,
                    "source_identity": {
                        "before": names["source_before"],
                        "after": names["source_after"],
                    },
                    "cg": {
                        "status": "measured"
                        if len(measured_names) == len(checker.L2_SOURCE_NAMES)
                        else "not_run_by_prior_contraction_gate",
                        "reason": 1,
                        "iterations": iterations,
                        "ksp_type": checker.L2_CG_KSP_TYPE,
                        "rtol": checker.L2_CG_RTOL,
                        "max_it": checker.L2_CG_MAX_IT,
                        "reported_residual_norm": 0.0,
                        "true_residual_relative": cg_true_residual_relative,
                        "true_residual_limit": checker.L2_CG_TRUE_RESIDUAL_LIMIT,
                    },
                }
            )
        else:
            source_facts.append(
                {
                    "name": name,
                    "status": "not_run_by_prior_contraction_gate",
                    "formula": checker.L2_SOURCE_FORMULAS[name],
                    "artifact_names": names,
                    "cg": {"status": "not_run_by_prior_contraction_gate"},
                }
            )
    return {
        "schema": checker.L2_SCHEMA,
        "stage": "l2",
        "scope": "l2_positive_auxiliary_one_apply_and_fixed_cg",
        "case": case,
        "degree": degree,
        "mpi_size": mpi_size,
        "command": ["synthetic-l2"],
        "source": {
            "expected_sha": "a" * 40,
            "commit_sha_start": "a" * 40,
            "commit_sha_end": "a" * 40,
            "branch": checker.BRANCH,
            "clean_start": True,
            "clean_end": True,
        },
        "runtime": runtime,
        "rank_facts": [
            {"rank": rank, "runtime": {**runtime}}
            for rank in range(mpi_size)
        ],
        "fixture_audit": {
            "high_order_matrix_free": True,
            "high_order_global_aij": False,
            "global_transfer_matrix": False,
            "global_numeric_allgather": False,
            "metadata_allgather": False,
            "phase_application": "finalized_floquet_mpc_once",
            "slave_master_complete": True,
            "hx_audit": hx_audit,
        },
        "sources": source_facts,
        "control_flow": {
            "early_stop": len(measured_names) != len(checker.L2_SOURCE_NAMES),
            "stop_reason": "rho_above_source_fixed_limit"
            if len(measured_names) != len(checker.L2_SOURCE_NAMES)
            else None,
        },
        "canonical_roles": {
            "source_before": "full_fe_primal",
            "source_after": "full_fe_primal",
            "pc_output": "full_fe_primal",
            "pc_repeat": "full_fe_primal",
            "residual": "full_fe_dual",
            "applied_output": "full_fe_dual",
            "true_residual": "full_fe_dual",
            "cg_solution": "full_fe_primal",
            "cg_action": "full_fe_dual",
            "cg_true_residual": "full_fe_dual",
        },
        "canonical_evidence": {
            "root_gather_evidence_only": True,
            "production_numeric_allgather": False,
        },
        "forbidden": {
            "physical_action": False,
            "dynamic_dtn": False,
            "global_numeric_allgather": False,
            "high_order_global_aij": False,
            "global_transfer_matrix": False,
            "global_direct_coarse": False,
            "real_imag_split": False,
            "hypre_ams": False,
        },
        "production": {
            "positive_auxiliary_only": True,
            "high_order_matrix_free": True,
            "numeric_allgather": False,
            "global_high_order_aij": False,
            "global_transfer_matrix": False,
            "global_direct_coarse": False,
            "physical_action": False,
            "dynamic_dtn": False,
        },
        "status": "facts_written_not_qualified",
        "_arrays": _l2_synthetic_arrays(
            measured_names,
            applied_fraction,
            cg_solution_offset,
            cg_action_offset,
        ),
    }


def test_l2_checker_accepts_four_case_synthetic_and_serializes_nested_cg(
    tmp_path: Path,
) -> None:
    configurations = (
        ("p2-mpi1", 2),
        ("p2-mpi2", 3),
        ("p3-mpi1", 4),
        ("p3-mpi2", 5),
    )
    paths = [
        _write_record(
            tmp_path,
            f"l2_{case}",
            _l2_synthetic_record(case, iterations),
        )
        for case, iterations in configurations
    ]
    result = checker.check_l2_records(paths)
    assert result["passed"] is True
    assert result["hard_stop"] is False
    for item, (_case, iterations) in zip(result["records"], configurations):
        assert item["source_metrics"][0]["iterations"] == iterations
        assert item["source_metrics"][0]["cg_solution_keys"] == ["p0", "p1"]
        assert item["source_metrics"][0]["cg_solution_values"]
    json.dumps(result, allow_nan=False)


def test_l2_checker_recomputes_raw_gate_and_rejects_formula_phase_mutations(
    tmp_path: Path,
) -> None:
    bad = _l2_synthetic_record(
        "p2-mpi1", measured_names=("random",), applied_fraction=0.0
    )
    bad["status"] = "worker_claimed_pass"
    bad["sources"][0]["rho"] = 0.0
    bad_path = _write_record(tmp_path, "l2_bad_raw", bad)
    checked = checker.check_l2_record(bad_path)
    assert checked["passed"] is False
    assert any("rho_above_source_fixed_limit" in error for error in checked["gate_failures"])

    for field in ("formula", "phase_application"):
        mutated = _l2_synthetic_record("p2-mpi1")
        mutated["sources"][0][field] = "mutated"
        path = _write_record(tmp_path, f"l2_bad_{field}", mutated)
        assert checker.check_l2_record(path)["contract_errors"]

    bad_cg = _l2_synthetic_record("p2-mpi1")
    bad_cg["sources"][0]["cg"]["rtol"] = 1.0e-7
    path = _write_record(tmp_path, "l2_bad_cg_contract", bad_cg)
    assert any("rtol" in error for error in checker.check_l2_record(path)["contract_errors"])


def test_l2_checker_accepts_only_single_first_case_contraction_hard_stop(
    tmp_path: Path,
) -> None:
    first = _l2_synthetic_record(
        "p2-mpi1", measured_names=("random",), applied_fraction=0.0
    )
    first_path = _write_record(tmp_path, "l2_hard_stop_first", first)
    result = checker.check_l2_records([first_path])
    assert result["hard_stop"] is True
    assert result["later_cases_status"] == "not_run_by_gate"
    assert result["later_cases"] == ["p2-mpi2", "p3-mpi1", "p3-mpi2"]
    assert result["contract_errors"] == []

    later = _l2_synthetic_record("p2-mpi2")
    later_path = _write_record(tmp_path, "l2_hard_stop_later", later)
    result = checker.check_l2_records([first_path, later_path])
    assert any("later case" in error for error in result["contract_errors"])


def test_l2_checker_gates_p3_iterations_per_mpi(tmp_path: Path) -> None:
    configurations = (
        ("p2-mpi1", 1),
        ("p2-mpi2", 1),
        ("p3-mpi1", 12),
        ("p3-mpi2", 12),
    )
    paths = [
        _write_record(
            tmp_path,
            f"l2_iterations_{case}",
            _l2_synthetic_record(case, iterations),
        )
        for case, iterations in configurations
    ]
    result = checker.check_l2_records(paths)
    assert result["passed"] is False
    assert any("p3-mpi1 iterations" in error for error in result["gate_failures"])
    assert any("p3-mpi2 iterations" in error for error in result["gate_failures"])


def test_l2_checker_gates_cross_mpi_action_and_solution_mutations(
    tmp_path: Path,
) -> None:
    for label, kwargs, expected in (
        ("action", {"cg_action_offset": 1.0e-10 + 0.0j}, "cg_action"),
        ("solution", {"cg_solution_offset": 1.0e-3 + 0.0j}, "cg_solution"),
    ):
        paths = []
        for case in checker.L2_CASE_ORDER:
            options = kwargs if case == "p2-mpi2" else {}
            paths.append(
                _write_record(
                    tmp_path,
                    f"l2_mutation_{label}_{case}",
                    _l2_synthetic_record(case, **options),
                )
            )
        result = checker.check_l2_records(paths)
        assert result["passed"] is False
        assert any(expected in error for error in result["gate_failures"])
