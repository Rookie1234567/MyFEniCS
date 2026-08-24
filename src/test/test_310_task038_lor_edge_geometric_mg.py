"""Focused S4-A3 adapter and independent-checker tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

from benchmarks.task038_full3d_lor_edge_geometric_mg_checker import (
    _check_watchdog,
    _dynamic_action_bound,
    _provenance_match,
    _within_dynamic_action_bound,
    check_record,
)
from benchmarks.run_task038_full3d_lor_edge_geometric_mg import (
    _launch_command,
    _partition_invariant_identities,
)
from src.solvers.fullspace_lor_edge_geometric_mg_global import (
    HighLORGeometricVcyclePC,
    ImplicitLORTransferCase,
)
from src.solvers.fullspace_lor_native_hx_fixture import RealL2PositiveHXFixture


BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"
SOURCE_SHA = "a" * 40


def _relative(left, right) -> float:
    diff = left.copy()
    diff.axpy(-1.0, right)
    try:
        return float(diff.norm() / max(right.norm(), np.finfo(float).tiny))
    finally:
        diff.destroy()


def _check_high_pc(degree: int) -> None:
    comm = MPI.COMM_WORLD
    fixture = RealL2PositiveHXFixture(
        degree, comm, variant="sequential-v1", build_hx=False
    )
    case = ImplicitLORTransferCase(fixture)
    pc = HighLORGeometricVcyclePC(case)
    vectors = []
    try:
        assert fixture.build_hx is False
        assert fixture.node_matrix is None
        assert fixture.hx is None
        source1, _ = fixture.build_l2_source("random")
        vectors.append(source1)
        source2, _ = fixture.build_l2_source("curl")
        vectors.append(source2)
        rhs1 = fixture.apply_high_action_copy(source1)
        vectors.append(rhs1)
        rhs2 = fixture.apply_high_action_copy(source2)
        vectors.append(rhs2)
        before1 = rhs1.array.copy()
        before2 = rhs2.array.copy()
        output1 = pc.apply(rhs1)
        vectors.append(output1)
        output2 = pc.apply(rhs2)
        vectors.append(output2)
        combined = rhs1.copy()
        vectors.append(combined)
        alpha = 0.375 + 0.25j
        beta = -0.625 + 0.5j
        combined.scale(alpha)
        combined.axpy(beta, rhs2)
        output_combined = pc.apply(combined)
        vectors.append(output_combined)
        repeated = pc.apply(rhs1)
        vectors.append(repeated)
        expected = output1.copy()
        vectors.append(expected)
        expected.scale(alpha)
        expected.axpy(beta, output2)
        assert _relative(output_combined, expected) <= 1.0e-12
        assert _relative(repeated, output1) <= 1.0e-13
        assert np.array_equal(rhs1.array, before1)
        assert np.array_equal(rhs2.array, before2)
        local_finite = all(
            np.all(np.isfinite(vector.getArray(readonly=True)))
            for vector in (output1, output2, output_combined, repeated)
        )
        assert comm.allreduce(int(local_finite), op=MPI.MIN) == 1
        assert pc.apply_count == 4
        assert pc.vcycle.apply_count == 4
    finally:
        for vector in vectors:
            vector.destroy()
        pc.destroy()
        assert case._destroyed is True
        assert pc._destroyed is True


@pytest.mark.parametrize("degree", (2, 3))
def test_high_pc_real_mpi1_or_p2_mpi2(degree: int) -> None:
    if MPI.COMM_WORLD.size == 2 and degree != 2:
        pytest.skip("MPI2 focused A3 probe is p2 only")
    _check_high_pc(degree)


def _write_array(path: Path, values: np.ndarray) -> dict[str, object]:
    np.save(path, values, allow_pickle=False)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "relative_path": path.name,
        "bytes": path.stat().st_size,
        "sha256": digest,
        "dtype": str(values.dtype),
        "shape": list(values.shape),
    }


def _synthetic_record(tmp_path: Path) -> tuple[Path, Path, dict[str, object]]:
    raw = tmp_path / "raw"
    raw.mkdir()
    record_path = tmp_path / "record.json"
    watchdog_raw = tmp_path / "watchdog.raw.jsonl"
    watchdog = tmp_path / "watchdog.json"
    keys = np.asarray(["k0", "k1"], dtype="<U2")
    canonical_values = {
        "source": np.asarray([3.0 + 0.0j, 4.0 + 0.0j]),
        "rhs": np.asarray([1.0 + 0.0j, 2.0 + 0.0j]),
        "rhs_repeat": np.asarray([1.0 + 0.0j, 2.0 + 0.0j]),
        "final_solution": np.asarray([0.0 + 0.0j, 0.0 + 0.0j]),
        "final_action": np.asarray([0.999999998 + 0.0j, 1.999999996 + 0.0j]),
        "final_true_residual": np.asarray([2.0e-9 + 0.0j, 4.0e-9 + 0.0j]),
    }
    canonical = {}
    for role, values in canonical_values.items():
        key_desc = _write_array(raw / f"{role}.rank0.keys.npy", keys)
        value_desc = _write_array(raw / f"{role}.rank0.values.npy", values)
        canonical[role] = {
            "role": "primal" if role in ("source", "final_solution") else "dual",
            "shards": [{"rank": 0, "keys": key_desc, "values": value_desc}],
        }
    zeros = np.zeros(2, dtype=np.complex128)
    inputs = {
        "first": np.asarray([1.0 + 0.0j, 0.0 + 0.0j]),
        "second": np.asarray([0.0 + 0.0j, 2.0 + 0.0j]),
        "combined": np.asarray([0.375 + 0.25j, -1.25 + 1.0j]),
    }
    pc_artifacts = {}
    for role in (
        "pc_input_first_before", "pc_input_first_after",
        "pc_input_second_before", "pc_input_second_after",
        "pc_input_combined_before", "pc_input_combined_after",
    ):
        name = role.removeprefix("pc_input_").removesuffix("_before").removesuffix("_after")
        values = inputs[name] if "before" in role or "after" in role else zeros
        descriptor = _write_array(raw / f"{role}.rank0.values.npy", values)
        pc_artifacts[role] = {"shards": [{"rank": 0, "ownership_range": [0, 2], "global_size": 2, "values": descriptor}]}
    for role in ("pc_output_first", "pc_output_second", "pc_output_combined", "pc_output_repeat"):
        descriptor = _write_array(raw / f"{role}.rank0.values.npy", zeros)
        pc_artifacts[role] = {"shards": [{"rank": 0, "ownership_range": [0, 2], "global_size": 2, "values": descriptor}]}
    expected_command = [
        "/opt/qualified/bin/python",
        "-m",
        "benchmarks.run_task038_full3d_lor_edge_geometric_mg",
        "--stage",
        "s4-a3",
        "--case",
        "p2-mpi1",
        "--source",
        "random",
        "--raw-dir",
        str(raw.resolve()),
        "--record",
        str(record_path.resolve()),
        "--expected-source-sha",
        SOURCE_SHA,
        "--expected-mpi-size",
        "1",
    ]
    source = {
        "expected_sha": SOURCE_SHA,
        "commit_sha_start": SOURCE_SHA,
        "branch": BRANCH,
        "clean_start": True,
    }
    source_end = {
        "expected_sha": SOURCE_SHA,
        "commit_sha_end": SOURCE_SHA,
        "branch": BRANCH,
        "clean_end": True,
    }
    sample = {"authority": {"process_tree": {"all_status_readable": True, "rss_bytes": 100, "swap_bytes": 0}}}
    watchdog_raw.write_text(json.dumps(sample) + "\n", encoding="utf-8")
    compact = {
        "schema": "task038.lor-native-complex-hx.foundation-e-watchdog.v1",
        "source_sha": SOURCE_SHA,
        "worker_command": expected_command,
        "worker_raw_dir": str(raw.resolve()),
        "worker_record": str(record_path.resolve()),
        "watchdog_raw": str(watchdog_raw.resolve()),
        "returncode": 0,
        "natural_exit": True,
        "no_orphan": True,
        "stop_reason": "natural_exit",
        "sample_count": 1,
        "all_status_readable": True,
        "peak_process_tree_rss_bytes": 100,
        "max_process_tree_swap_bytes": 0,
        "watchdog_poll_seconds": 0.25,
        "watchdog_rss_limit_bytes": 500_000_000,
        "raw_sha256": hashlib.sha256(watchdog_raw.read_bytes()).hexdigest(),
    }
    watchdog.write_text(json.dumps(compact), encoding="utf-8")
    record = {
        "schema": "task038.lor-edge-geometric-mg.s4-a3-record.v1",
        "case": "p2-mpi1",
        "degree": 2,
        "h_nm": 50.0,
        "mpi_size": 1,
        "source_name": "random",
        "variant": "sequential-v1",
        "method": "lor_edge_geometric_mg_v1",
        "settings": {
            "ksp_type": "gmres",
            "pc_side": "right",
            "norm_type": "unpreconditioned",
            "restart": 20,
            "cycle_max_it": 20,
            "max_it": 10000,
            "zero_initial_guess": True,
            "residual_replacement": True,
            "residual_limit": 1.0e-8,
            "checkpoint_writer": None,
        },
        "vcycle_settings": {"chebyshev_degree": 3, "power_steps": 10, "lambda_hi_factor": 1.10, "lambda_lo_factor": 0.10, "pre": 1, "post": 1, "vcycle": 1, "coarse_backend": "petsc-preonly-lu-mumps", "coarse_scope": "p2_p3_small_oracle_only"},
        "source": source,
        "source_end": source_end,
        "runtime": {"qualified_activation": "1", "petsc_scalar_type": "complex128", "petsc_int_type": "int32", "mpi_size": 1, "sys_executable": expected_command[0]},
        "command": expected_command,
        "launch_command": expected_command,
        "raw_dir": str(raw.resolve()),
        "record_path": str(record_path.resolve()),
        "provenance": {"input_identity_sha256": "b" * 64, "operator_identity_sha256": "c" * 64, "physical_model_sha256": "d" * 64},
        "source_unchanged": True,
        "production": {name: False for name in ("build_hx", "scalar_node_matrix", "high_order_global_aij", "global_dense_transfer", "global_numeric_allgather", "global_direct_coarse", "pcgamg_hierarchy_built", "p6_exact_edge_factor_built", "numeric_allgather")},
        "fixture_audit": {"high_order_global_aij": False, "global_transfer_matrix": False, "global_numeric_allgather": False, "hx_audit": {"constructed": False, "high_order_aij": False, "global_transfer_matrix": False, "global_numeric_allgather": False}},
        "rank_facts": [{"rank": 0, "node_audit": {"scalar_node_matrix": False, "global_numeric_allgather": False}, "source_unchanged": True, "outer_scalar": {"iterations": 20, "matvec_count": 1, "pc_apply_count": 1, "explicit_action_count": 2, "ksp_destroy_count": 1, "final_true_residual": 2.0e-9}}],
        "canonical_artifacts": canonical,
        "pc_legality": {"artifacts": pc_artifacts, "input_unchanged": True, "finite": True, "linearity_relative": 0.0, "repeat_relative": 0.0, "slave_constraint_absolute": 0.0, "slave_local_indices_by_rank": {"0": []}},
        "outer": {"cycles": [{"start_iteration": 0, "end_iteration": 20, "iterations": 20, "reason": -3, "reported_final_residual": 2.0e-9, "explicit_true_residual": 2.0e-9, "matvec_count": 1, "pc_apply_count": 1, "wall_seconds": 0.1, "ksp_destroyed": True}], "iterations": 20, "reason": -3, "final_true_residual": 2.0e-9, "matvec_count": 1, "pc_apply_count": 1, "explicit_action_count": 2, "ksp_destroy_count": 1, "elapsed_seconds": 0.1},
    }
    record_path.write_text(json.dumps(record), encoding="utf-8")
    return record_path, watchdog, record


def test_checker_normal_and_residual_tamper(tmp_path: Path) -> None:
    record_path, watchdog, record = _synthetic_record(tmp_path)
    result = check_record(record_path, watchdog)
    assert result["passed"] is True
    record["outer"]["final_true_residual"] = 1.0e-12
    tampered = tmp_path / "tampered.json"
    tampered.write_text(json.dumps(record), encoding="utf-8")
    failed = check_record(tampered, watchdog)
    assert failed["passed"] is False
    assert any("stored and raw final residual" in item for item in failed["contract_errors"])


@pytest.mark.parametrize("field,value", (("swap_bytes", 1), ("rss_bytes", 500_000_000)))
def test_checker_watchdog_missing_cycle_and_dynamic_bound(tmp_path: Path, field: str, value: int) -> None:
    record_path, watchdog, record = _synthetic_record(tmp_path)
    watchdog_raw = Path(json.loads(watchdog.read_text(encoding="utf-8"))["watchdog_raw"])
    sample = json.loads(watchdog_raw.read_text(encoding="utf-8"))
    sample["authority"]["process_tree"][field] = value
    watchdog_raw.write_text(json.dumps(sample) + "\n", encoding="utf-8")
    compact = json.loads(watchdog.read_text(encoding="utf-8"))
    compact["raw_sha256"] = hashlib.sha256(watchdog_raw.read_bytes()).hexdigest()
    compact["peak_process_tree_rss_bytes"] = value if field == "rss_bytes" else 100
    compact["max_process_tree_swap_bytes"] = value if field == "swap_bytes" else 0
    watchdog.write_text(json.dumps(compact), encoding="utf-8")
    failed_watchdog = check_record(record_path, watchdog)
    assert failed_watchdog["passed"] is False
    assert any("watchdog" in item for item in failed_watchdog["gate_failures"])

    record["outer"]["cycles"][0]["start_iteration"] = 1
    missing_cycle = tmp_path / "missing-cycle.json"
    missing_cycle.write_text(json.dumps(record), encoding="utf-8")
    failed_cycle = check_record(missing_cycle, watchdog)
    assert failed_cycle["passed"] is False
    assert any("cycle" in item for item in failed_cycle["contract_errors"])

    missing_role = dict(record)
    missing_role["canonical_artifacts"] = dict(record["canonical_artifacts"])
    missing_role["canonical_artifacts"].pop("source")
    missing_role_path = tmp_path / "missing-role.json"
    missing_role_path.write_text(json.dumps(missing_role), encoding="utf-8")
    failed_role = check_record(missing_role_path, watchdog)
    assert failed_role["passed"] is False
    assert any("canonical source" in item for item in failed_role["contract_errors"])

    bound = _dynamic_action_bound(2.0e-9, 3.0e-9, 0.0)
    assert bound == 2.0e-9 + 3.0e-9 + 1.0e-11
    assert _within_dynamic_action_bound(bound + 1.0e-6, 2.0e-9, 3.0e-9, 0.0) is False


def test_mpi_launch_binding_is_exact() -> None:
    direct = ["/opt/qualified/bin/python", "-m", "benchmarks.run_task038_full3d_lor_edge_geometric_mg"]
    assert _launch_command(direct, 1) == direct
    mpi2 = _launch_command(direct, 2, mpiexec_path="/usr/bin/mpiexec")
    assert mpi2 == ["/usr/bin/mpiexec", "-n", "2", *direct]


def test_watchdog_binds_launch_command_not_direct_command(tmp_path: Path) -> None:
    record_path, watchdog, record = _synthetic_record(tmp_path)
    launch = ["/usr/bin/mpiexec", "-n", "2", *record["command"]]
    record["launch_command"] = launch
    compact = json.loads(watchdog.read_text(encoding="utf-8"))
    compact["worker_command"] = launch
    watchdog.write_text(json.dumps(compact), encoding="utf-8")
    errors: list[str] = []
    gates: list[str] = []
    resource = _check_watchdog(record, record_path, watchdog, errors, gates)
    assert not any("worker command" in item for item in errors)
    assert not gates
    assert resource["worker_launch_command"] == launch


def test_pair_provenance_mismatch_fails() -> None:
    left = {"provenance": {"input_identity_sha256": "a" * 64, "operator_identity_sha256": "b" * 64, "physical_model_sha256": "c" * 64}}
    right = {"provenance": dict(left["provenance"])}
    assert _provenance_match(left, right) is True
    right["provenance"]["physical_model_sha256"] = "d" * 64
    assert _provenance_match(left, right) is False
    p2_random = _partition_invariant_identities(2, "random")
    p2_curl = _partition_invariant_identities(2, "curl")
    p3_random = _partition_invariant_identities(3, "random")
    assert p2_random["input_identity_sha256"] != p2_curl["input_identity_sha256"]
    assert p2_random["operator_identity_sha256"] == p2_curl["operator_identity_sha256"]
    assert p2_random["physical_model_sha256"] == p3_random["physical_model_sha256"]
