"""Pure contract tests for the R4.1 Route-B setup/positive evidence layer."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from benchmarks import run_task038_full3d_lor_nested_positive as runner
from benchmarks import task038_full3d_lor_nested_positive_checker as checker


ROOT = Path(__file__).resolve().parents[2]
SOURCE_SHA = "a" * 40
INPUT_PATH = (ROOT / "input/templates/full3d_iterative_example.dat").resolve()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _array_sha(values: np.ndarray) -> str:
    values = np.ascontiguousarray(values)
    return hashlib.sha256(values.view(np.uint8)).hexdigest()


def _audit_sources() -> tuple[dict, dict, dict]:
    forbidden = {name: False for name in checker.FORBIDDEN_FIELDS}
    case = {name: False for name in (
        "global_dense_transfer", "global_numeric_allgather", "scalar_node_matrix_built",
        "p6_exact_edge_factor_built", "global_direct_coarse_built",
        "recovery_field_arrays_built", "hx_or_node_action_built",
        "production_local_spectral_built",
    )}
    action = {key: False for key in checker.IMMUTABLE_OPERATOR_ACTION_KEYS}
    action.update({
        "schema": "synthetic-high-positive-action.v1", "backend": "synthetic",
        "matrix_type": "python", "operator": "synthetic_positive",
        "mpc_enabled": True, "slave_row_identity": True,
        "global_rows": 2, "local_owned_rows": 2, "local_ghost_rows": 0,
        "local_storage_entries": 2, "constraint_count": 0,
        "constraint_nnz": 0, "form_rank": 2, "coefficient_count": 1,
        "phase_application": "none", "orientation": "synthetic",
        "owner_local": True, "numeric_allgather": False,
        "global_matrix_materialized": False, "factor_count": 0,
        "ksp_created": False, "dtn_used": False,
        "ordinary_default_changed": False, "fresh_packed_arrays_released": True,
        "jit_options_explicit": False, "apply_count": 0,
    })
    case["high_positive_action"] = action
    extension = {name: False for name in (
        "global_transfer_matrix", "numeric_allgather", "p6_exact_factor",
        "hx_hierarchy_built", "pcgamg_hierarchy_built", "physical_solve", "recovery",
    )}
    vcycle = {name: False for name in (
        "global_high_order_aij", "level2_exact_factor", "global_direct_coarse",
        "retains_per_apply_history",
    )}
    return case, extension, vcycle | {"p1_exact_factor": True, "p1_factor_ksp_created": True}


def _ledger(stage: str, factor_memory: int, reserve_bytes: int) -> dict:
    foundation_known = {"foundation_array_bytes": 10}
    route_known = {
        "level2_matrix_index_bytes": 1, "level1_matrix_index_bytes": 1,
        "transfer_6_2_edge_bytes": 1, "transfer_6_2_node_bytes": 1,
        "transfer_2_1_edge_bytes": 1, "transfer_2_1_node_bytes": 1,
        "level6_smoother_work_vector_bytes": 128,
        "level2_smoother_work_vector_bytes": 128,
        "vcycle_work_vector_bytes": 64,
        "p1_factor_memory_bytes": factor_memory,
        "restart_reserve_numeric_bytes": reserve_bytes,
    }
    known = {**{f"foundation_{key}": value for key, value in foundation_known.items()}, **route_known}
    return {
        "scope": "synthetic measured components",
        "foundation": {"known_bytes": foundation_known, "known_total_bytes": 10},
        "route_b": {
            "known_bytes": route_known,
            "smoother_work_vectors": {
                "level6": {"vector_count": 8, "local_entries": [1] * 8, "complex128_bytes": 128},
                "level2": {"vector_count": 8, "local_entries": [1] * 8, "complex128_bytes": 128},
            },
            "vcycle_work_vectors": {"vector_count": 4, "local_entries": [1] * 4, "complex128_bytes": 64},
            "p1_factor_memory_bytes": factor_memory,
            "restart_reserve_numeric_bytes": reserve_bytes,
        },
        "known_bytes": known,
        "known_total_bytes": sum(known.values()),
        "measured_process_tree_rss_bytes": 9004,
        "unattributed_remainder_bytes": 9004 - sum(known.values()),
        "estimates_included": False,
    }


def _fixed_architecture() -> dict:
    case, extension, vcycle = _audit_sources()
    return {
        "case_audit": case,
        "high_coefficient_audit": {"schema": "synthetic-high-coefficient.v1", "finite": True},
        "extension_audit": extension,
        "vcycle_audit": vcycle | {
            "global_high_order_aij": False,
            "p1_exact_factor": True, "p1_factor_ksp_created": True,
            "p6_exact_factor": False,
        },
        "forbidden": {name: False for name in checker.FORBIDDEN_FIELDS},
        "current_anchor_p1_exact_oracle": True,
        "level1_factor": {
            "backend": "petsc-preonly-lu-mumps", "factor_solver_type": "mumps",
            "matrix_rows": 4, "matrix_cols": 4, "matrix_nnz": 4,
            "factor_matrix_nnz": 4, "setup_count": 1, "solve_count": 10,
            "petsc_reported_factor_memory_available": True,
            "petsc_reported_factor_memory_bytes": 4096,
            "petsc_reported_factor_memory_local_bytes": 4096,
            "petsc_reported_factor_memory_global_bytes": 4096,
        },
    }


def _descriptor(path: Path, values: np.ndarray) -> dict:
    values = np.ascontiguousarray(values)
    return {
        "relative_path": path.name, "bytes": int(values.nbytes),
        "sha256": _array_sha(values), "dtype": str(values.dtype),
        "shape": list(values.shape),
    }


def _file_descriptor(path: Path, values: np.ndarray) -> dict:
    values = np.ascontiguousarray(values)
    return {
        "relative_path": path.name, "bytes": int(path.stat().st_size),
        "sha256": _sha(path), "dtype": str(values.dtype),
        "shape": list(values.shape),
    }


def _write_checkpoint(raw: Path, iteration: int, identity: dict, source_sha: str) -> dict:
    directory = raw / f"checkpoint-{iteration}"
    directory.mkdir()
    values = np.asarray([0.0 + 0.0j, 0.0 + 0.0j], dtype=np.complex128)
    shard = directory / "solution_rank0.npy"
    np.save(shard, values, allow_pickle=False)
    manifest = {
        "schema": checker.CHECKPOINT_SCHEMA, "iteration": iteration,
        "explicit_true_residual": 0.0,
        "input_identity_sha256": identity["input_identity_sha256"],
        "operator_identity_sha256": identity["operator_identity_sha256"],
        "physical_model_sha256": identity["physical_model_sha256"],
        "source_sha": source_sha, "mpi_size": 1, "solution_only": True,
        "numeric_allgather": False, "vector_roles": ["solution"],
        "forbidden_vector_roles": ["action", "residual", "krylov_basis"],
        "ranks": [{"rank": 0, "ownership": {"rank": 0, "ownership_range": [0, 2], "local_size": 2, "global_size": 2},
                   "solution": _file_descriptor(shard, values)}],
    }
    manifest_path = directory / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, allow_nan=False) + "\n", encoding="utf-8")
    return {
        "iteration": iteration, "manifest_path": str(manifest_path.resolve()),
        "manifest_sha256": _sha(manifest_path), "rank": 0, "mpi_size": 1,
        "explicit_true_residual": 0.0,
    }


def _record_base(tmp_path: Path, stage: str, positive_iterations: int = 500) -> tuple[Path, Path, dict]:
    raw = tmp_path / "worker_raw"
    raw.mkdir()
    record_path = tmp_path / "record.json"
    watchdog_path = tmp_path / "watchdog.json"
    watchdog_raw = tmp_path / "watchdog.raw.jsonl"
    command = runner.canonical_worker_command(
        raw, record_path, INPUT_PATH, SOURCE_SHA, stage,
        "random" if stage == "positive" else None,
        executable=str(ROOT / ".venv/bin/python"),
    )
    source_identity = {"expected_sha": SOURCE_SHA, "commit_sha": SOURCE_SHA, "branch": checker.BRANCH, "clean": True}
    input_identity = {
        "path_absolute": str(INPUT_PATH), "raw_bytes": INPUT_PATH.stat().st_size,
        "raw_sha256": _sha(INPUT_PATH), "resolved_bytes": 1, "resolved_sha256": "c" * 64,
        "physical_model_sha256": "d" * 64,
    }
    architecture = _fixed_architecture()
    architecture["level1_factor"]["solve_count"] = 10 if stage == "setup" else positive_iterations
    before = None
    source_generation = None
    if stage == "setup":
        input_payload = {
            "stage": "setup", "resolved_config_sha256": "c" * 64,
            "input_raw_sha256": input_identity["raw_sha256"],
            "physical_model_sha256": input_identity["physical_model_sha256"],
        }
    else:
        before = np.asarray([1.0 + 1.0j, 2.0 - 1.0j], dtype=np.complex128)
        source_generation = {"name": "random", "formula": "l2_source_formula", "phase_application": "once"}
        input_payload = {
            "source_generation": source_generation,
            "source_before": {
                "sha256": _array_sha(before), "dtype": str(before.dtype), "shape": list(before.shape),
                "ownership_range": [0, 2], "local_size": 2, "global_size": 2,
                "finite": True, "nonzero": True,
            },
            "resolved_config_sha256": "c" * 64,
            "input_raw_sha256": input_identity["raw_sha256"],
            "physical_model_sha256": input_identity["physical_model_sha256"],
        }
    operator_authority = {
        "resolved_config_sha256": "c" * 64,
        "input_raw_sha256": input_identity["raw_sha256"],
        "physical_model_sha256": input_identity["physical_model_sha256"],
        "high_coefficient_audit": architecture["high_coefficient_audit"],
        "high_positive_action_audit": checker._immutable_operator_action_audit(
            architecture["case_audit"]["high_positive_action"]
        ),
        "matrix_free_action_identity": "S2FoundationCase.high_positive.apply",
    }
    identity = {
        "input_identity_sha256": checker._stable_sha(input_payload),
        "operator_identity_sha256": checker._stable_sha(operator_authority),
        "physical_model_sha256": input_identity["physical_model_sha256"],
    }
    record = {
        "schema": checker.SCHEMA, "stage": stage, "case": checker.CASE,
        "degree": 6, "h_nm": 10.0, "wavelength_nm": 13.5, "mpi_size": 1,
        "raw_dir": str(raw.resolve()), "record_path": str(record_path.resolve()), "command": command,
        "source": {"start": source_identity, "end": dict(source_identity)},
        "runtime": {"qualified_activation": "1", "mpi_size": 1, "sys_executable": command[0],
                    "petsc_scalar_type": "<class 'numpy.complex128'>", "petsc_int_type": "<class 'numpy.int32'>",
                    "threads": {"OMP_NUM_THREADS": None, "OPENBLAS_NUM_THREADS": None, "MKL_NUM_THREADS": None}},
        "input_identity": input_identity,
        "provenance": {"source_sha": SOURCE_SHA, "branch": checker.BRANCH, **identity, "resolved_config_sha256": "c" * 64},
        "settings": {"levels": [6, 2, 1], "pairs": [[6, 2], [2, 1]], "chebyshev_degree": 3, "power_steps": 10,
                     "pre_sweeps": 1, "post_sweeps": 1, "vcycle_count": 1, "restart": 20, "max_it": 10000,
                     "residual_replacement": True, "checkpoint_interval": 500, "cold_rss_limit_bytes": checker.COLD_LIMIT,
                     "retained_rss_limit_bytes": checker.RETAINED_LIMIT, "setup_growth_limit_bytes": checker.GROWTH_LIMIT},
        "architecture": architecture,
        "retained_ledger": _ledger(stage, 4096, 1600 if stage == "setup" else 0),
        "retained_ready_wall_time_ns": 1_000_000_000,
        "retained_observed_wall_time_ns": 3_000_000_000,
        "retained_dwell_seconds": 2.0,
        "resource_authority": "external_foundation_watchdog_process_tree",
        "markers": {"relative_dir": "markers", "names": list(checker.MARKERS[stage]),
                    "wall_time_ns": {name: index * 100 for index, name in enumerate(checker.MARKERS[stage][:-1], 1)}},
        "lifecycle": {"destroy_order": ["vcycle", "reserve", "foundation"] if stage == "setup" else ["vcycle", "foundation"], "normal_closeout": True},
        "resource": {"hierarchy_setup_before": {"rss_bytes": 900, "swap_bytes": 0, "all_status_readable": True},
                     "hierarchy_setup_after": {"rss_bytes": 1000, "swap_bytes": 0, "all_status_readable": True},
                     "retained_ready": {"rss_bytes": 9000, "swap_bytes": 0, "all_status_readable": True},
                     "retained_observed": {"rss_bytes": 9004, "swap_bytes": 0, "all_status_readable": True}},
    }
    if stage == "setup":
        reserve = {"basis_count": 21, "auxiliary_vector_count": 4, "vector_count": 25, "touched": True, "local_numeric_bytes": 1600}
        apply = [{"label": label, "input_unchanged": True, "output_finite": True, "primal_constraint_relative": 0.0,
                  "p1_relative_residual": 0.0, "p1_solve_count": index, "resource": {"rss_bytes": 1000 + index, "swap_bytes": 0, "all_status_readable": True}}
                 for index, label in enumerate(checker.SETUP_LABELS, 1)]
        record["reserve"] = reserve
        record["stage_facts"] = {**identity, "input_identity_authority": input_payload,
                                 "operator_identity_authority": operator_authority,
                                 "identity_authority": {"resolved_config_sha256": "c" * 64, "input_raw_sha256": input_identity["raw_sha256"], "physical_model_sha256": "d" * 64},
                                 "apply_count": 10, "vcycle_apply_count": 10, "apply_facts": apply,
                                 "linearity_relative": 0.0, "repeat_relative": 0.0, "independent_input_relative": 0.5,
                                 "finite": True, "input_unchanged": True, "legal_high_primal": True,
                                 "rss_span_bytes": 9, "max_swap_bytes": 0, "max_p1_relative_residual": 0.0,
                                 "p1_solve_count": 10, "outer_ksp_create_count": 0, "outer_ksp_destroy_count": 0,
                                 "transfer_counts": {f"{a}_{b}_{kind}": 10 for a, b in checker.PAIRS for kind in ("primal", "adjoint")},
                                 "reserve": reserve}
    else:
        rhs = np.asarray([1.0 + 0.0j, 2.0 - 1.0j], dtype=np.complex128)
        solution = np.zeros(2, dtype=np.complex128)
        action = rhs.copy()
        residual = rhs - action
        values = {"source_before": before, "source_after": before.copy(), "rhs": rhs, "rhs_repeat": rhs.copy(),
                  "final_solution": solution, "final_action": action, "final_true_residual": residual}
        raw_path = raw / "positive_rank0.npz"
        np.savez(raw_path, **values)
        arrays = {name: _descriptor(raw_path, value) for name, value in values.items()}
        cycle_count = positive_iterations // 20
        cycles = [{"cycle_index": index, "start_iteration": index * 20, "end_iteration": (index + 1) * 20,
                   "iterations": 20, "reason": 1, "initial_guess_nonzero": index > 0,
                   "reported_final_residual": 0.0, "explicit_true_residual": 0.0,
                   "matvec_count": 20, "pc_apply_count": 20, "wall_seconds": 0.1, "ksp_destroyed": True,
                   "resource": {"rss_bytes": 1000, "swap_bytes": 0, "all_status_readable": True}}
                  for index in range(cycle_count)]
        checkpoints = [_write_checkpoint(raw, iteration, identity, SOURCE_SHA)
                       for iteration in range(500, positive_iterations + 1, 500)]
        record["reserve"] = None
        record["stage_facts"] = {"source": source_generation, **identity,
                                 "input_identity_authority": input_payload,
                                 "operator_identity_authority": operator_authority,
                                 "identity_authority": {"resolved_config_sha256": "c" * 64, "input_raw_sha256": input_identity["raw_sha256"], "physical_model_sha256": "d" * 64},
                                 "source_finite": True, "source_nonzero": True,
                                 "source_before_finite": True, "source_before_nonzero": True,
                                 "source_unchanged": True, "rhs_repeat_relative": 0.0,
                                 "settings": {"ksp_type": "gmres", "pc_side": "right", "norm_type": "unpreconditioned", "restart": 20, "cycle_max_it": 20, "max_it": 10000, "start_iteration": 0, "initial_guess_nonzero": False, "residual_limit": 1.0e-8, "residual_replacement": True, "first_checkpoint_iteration": None, "checkpoint_interval": 500},
                                 "initial_true_residual": 1.0,
                                 "cycles": cycles, "iterations": positive_iterations, "reason": 1, "final_true_residual": 0.0,
                                 "matvec_count": positive_iterations, "pc_apply_count": positive_iterations, "explicit_action_count": cycle_count + 4, "rhs_action_count": 1,
                                 "final_action_recheck_count": 1, "rhs_repeat_action_count": 1, "ksp_create_count": cycle_count, "ksp_destroy_count": cycle_count,
                                 "outer_ksp_create_count": cycle_count, "outer_ksp_destroy_count": cycle_count, "vcycle_apply_count": positive_iterations, "p1_solve_count": positive_iterations,
                                 "max_p1_relative_residual": 0.0, "transfer_counts": {f"{a}_{b}_{kind}": positive_iterations for a, b in checker.PAIRS for kind in ("primal", "adjoint")},
                                 "raw": {"relative_path": raw_path.name, "sha256": _sha(raw_path), "arrays": arrays,
                                         "rank": 0, "ownership_range": [0, 2], "local_size": 2, "global_size": 2},
                                 "checkpoint_facts": checkpoints,
                                 "milestones": {str(value): ("measured" if value <= positive_iterations else "not_reached") for value in checker.MILESTONE_KEYS}}
    watchdog_raw.write_text("".join(json.dumps({"wall_time_ns": index * 500_000_000, "authority": {"process_tree": {"rss_bytes": 8998 + index, "swap_bytes": 0, "all_status_readable": True}}}, allow_nan=False) + "\n" for index in range(1, 8)), encoding="utf-8")
    samples = watchdog_raw.read_text(encoding="utf-8").splitlines()
    compact = {"schema": checker.WATCHDOG_SCHEMA, "source_sha": SOURCE_SHA, "worker_command": command,
               "worker_raw_dir": str(raw.resolve()), "worker_record": str(record_path.resolve()), "watchdog_raw": str(watchdog_raw.resolve()),
               "returncode": 0, "natural_exit": True, "no_orphan": True, "stop_reason": "natural_exit", "sample_count": len(samples),
               "all_status_readable": True, "peak_process_tree_rss_bytes": 9005, "max_process_tree_swap_bytes": 0,
               "watchdog_poll_seconds": 0.25, "watchdog_rss_limit_bytes": checker.COLD_LIMIT, "raw_sha256": _sha(watchdog_raw)}
    watchdog_path.write_text(json.dumps(compact, allow_nan=False) + "\n", encoding="utf-8")
    record_path.write_text(json.dumps(record, allow_nan=False) + "\n", encoding="utf-8")
    marker_dir = raw / "markers"
    marker_dir.mkdir()
    for index, name in enumerate(checker.MARKERS[stage], 1):
        facts = {}
        if name == "record_written":
            facts = {"record_path": str(record_path.resolve()), "record_sha256": _sha(record_path)}
        (marker_dir / f"{name}.json").write_text(json.dumps({"schema": checker.MARKER_SCHEMA, "marker": name, "source_sha": SOURCE_SHA, "wall_time_ns": index * 100, "facts": facts}, allow_nan=False) + "\n", encoding="utf-8")
    return record_path, watchdog_path, record


def _write_record_with_closeout(record_path: Path, record: dict) -> None:
    record_path.write_text(json.dumps(record, allow_nan=False) + "\n", encoding="utf-8")
    marker_path = Path(record["raw_dir"]) / "markers" / "record_written.json"
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    marker["facts"]["record_sha256"] = _sha(record_path)
    marker_path.write_text(json.dumps(marker, allow_nan=False) + "\n", encoding="utf-8")


def _sync_positive_raw(record: dict) -> None:
    raw = Path(record["raw_dir"])
    raw_path = raw / str(record["stage_facts"]["raw"]["relative_path"])
    with np.load(raw_path, allow_pickle=False) as bundle:
        values = {name: np.asarray(bundle[name]).copy() for name in bundle.files}
    record["stage_facts"]["raw"]["sha256"] = _sha(raw_path)
    record["stage_facts"]["raw"]["arrays"] = {
        name: _descriptor(raw_path, value) for name, value in values.items()
    }


def test_setup_copies_dual_source_and_keeps_inputs_independent(tmp_path, monkeypatch):
    class Vec:
        def __init__(self, values):
            self.values = np.asarray(values, dtype=np.complex128).copy()
            self.destroyed = False

        def duplicate(self):
            return Vec(self.values)

        def copy(self, target):
            target.values[...] = self.values

        def set(self, value):
            self.values[...] = value

        def axpy(self, scale, other):
            self.values[...] += scale * other.values

        def getArray(self, readonly=True):
            return self.values

        def destroy(self):
            self.destroyed = True

    case = type("Case", (), {
        "high_primal_source": Vec([1.0 + 0.0j, 0.0j]),
        "high_dual_source": Vec([0.0j, 1.0 + 0.0j]),
    })()
    vcycle = type("Vcycle", (), {
        "apply_count": 10,
        "last_apply_facts": {"transfer_6_2_primal_total": 10},
    })()
    seen = {}

    def fake_probe(_vcycle, vector, label, _resource):
        values = {
            "x": np.array([1.0, 0.0], dtype=np.complex128),
            "y": np.array([0.0, 1.0], dtype=np.complex128),
            "x_repeat": np.array([1.0, 0.0], dtype=np.complex128),
            "combo": np.array([0.75 - 0.25j, -0.5 + 0.5j], dtype=np.complex128),
            "ax": np.array([0.75 - 0.25j, 0.0], dtype=np.complex128),
            "by": np.array([0.0, -0.5 + 0.5j], dtype=np.complex128),
        }
        values.setdefault(label, values["x"])
        seen[label] = np.asarray(vector.getArray(readonly=True)).copy()
        index = len(seen)
        return ({"label": label, "input_unchanged": True, "output_finite": True,
                 "p1_relative_residual": 0.0, "p1_solve_count": index,
                 "primal_constraint_relative": 0.0, "legal_high_primal": True,
                 "resource": {"rss_bytes": 1000 + index, "swap_bytes": 0,
                              "all_status_readable": True}}, values[label])

    monkeypatch.setattr(runner, "_apply_setup_probe", fake_probe)
    facts = runner._setup_stage(
        case, vcycle, tmp_path, lambda: {"process_tree": {"rss_bytes": 1000,
        "swap_bytes": 0, "all_status_readable": True}}, {"local_numeric_bytes": 1}
    )
    assert np.array_equal(seen["y"], case.high_dual_source.values)
    assert facts["independent_input_relative"] > 0.0
    assert not case.high_dual_source.destroyed


def test_borrowed_action_copy_does_not_destroy_action_owned_vec():
    class Borrowed:
        def copy(self):
            return Owned()

        def destroy(self):
            raise AssertionError("borrowed action result was destroyed")

    class Owned:
        def __init__(self):
            self.destroyed = False

        def destroy(self):
            self.destroyed = True

    class Action:
        def __init__(self):
            self.borrowed = Borrowed()

        def apply(self, _source):
            return self.borrowed

    action = Action()
    owned = runner._copy_borrowed_action(action, object())
    assert owned is not action.borrowed
    owned.destroy()
    assert owned.destroyed


@pytest.mark.parametrize("mutation", ("missing", "extra"))
def test_checkpoint_inventory_uses_all_500_multiples(tmp_path, mutation):
    record_path, watchdog_path, record = _record_base(tmp_path, "positive", positive_iterations=1500)
    assert [item["iteration"] for item in record["stage_facts"]["checkpoint_facts"]] == [500, 1000, 1500]
    if mutation == "missing":
        record["stage_facts"]["checkpoint_facts"].pop(1)
    else:
        record["stage_facts"]["checkpoint_facts"].append(
            dict(record["stage_facts"]["checkpoint_facts"][-1], iteration=2000)
        )
    _write_record_with_closeout(record_path, record)
    result = checker.check_record(record_path, watchdog_path, SOURCE_SHA)
    assert not result["passed"]
    assert any("exact 500-step set" in error for error in result["contract_errors"])


def test_source_raw_change_fails_even_when_outer_raw_sha_is_synchronized(tmp_path):
    record_path, watchdog_path, record = _record_base(tmp_path, "positive")
    raw_path = Path(record["raw_dir"]) / "positive_rank0.npz"
    with np.load(raw_path, allow_pickle=False) as bundle:
        values = {name: np.asarray(bundle[name]).copy() for name in bundle.files}
    values["source_before"][0] += 0.25
    values["source_after"][0] += 0.25
    np.savez(raw_path, **values)
    _sync_positive_raw(record)
    _write_record_with_closeout(record_path, record)
    result = checker.check_record(record_path, watchdog_path, SOURCE_SHA)
    assert not result["passed"]
    assert any("input identity authority" in error for error in result["contract_errors"])


def test_operator_identity_excludes_mutable_apply_count_but_binds_authority(tmp_path):
    record_path, watchdog_path, record = _record_base(tmp_path, "setup")
    record["architecture"]["case_audit"]["high_positive_action"]["apply_count"] = 999
    _write_record_with_closeout(record_path, record)
    assert checker.check_record(record_path, watchdog_path, SOURCE_SHA)["passed"]

    authority_root = tmp_path / "authority"
    authority_root.mkdir()
    record_path, watchdog_path, record = _record_base(authority_root, "setup")
    record["stage_facts"]["operator_identity_authority"]["matrix_free_action_identity"] = "tampered"
    record["stage_facts"]["operator_identity_sha256"] = checker._stable_sha(
        record["stage_facts"]["operator_identity_authority"]
    )
    record["provenance"]["operator_identity_sha256"] = record["stage_facts"]["operator_identity_sha256"]
    _write_record_with_closeout(record_path, record)
    result = checker.check_record(record_path, watchdog_path, SOURCE_SHA)
    assert not result["passed"]
    assert any("operator identity authority" in error for error in result["contract_errors"])


def test_checkpoint_summary_contains_only_returned_fields(tmp_path):
    identity = {"input_identity_sha256": "a" * 64, "operator_identity_sha256": "b" * 64,
                "physical_model_sha256": "c" * 64}
    summary = _write_checkpoint(tmp_path, 500, identity, SOURCE_SHA)
    assert set(summary) == {"iteration", "manifest_path", "manifest_sha256", "rank", "mpi_size", "explicit_true_residual"}


def test_checkpoint_descriptor_binds_file_bytes_and_sha(tmp_path):
    record_path, watchdog_path, record = _record_base(tmp_path, "positive")
    fact = record["stage_facts"]["checkpoint_facts"][0]
    manifest_path = Path(fact["manifest_path"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    descriptor = manifest["ranks"][0]["solution"]
    shard = manifest_path.parent / descriptor["relative_path"]
    values = np.load(shard, allow_pickle=False)
    assert descriptor["bytes"] == shard.stat().st_size
    assert descriptor["sha256"] == _sha(shard)
    assert descriptor["bytes"] != int(values.nbytes)
    assert descriptor["sha256"] != _array_sha(values)
    with shard.open("ab") as stream:
        stream.write(b"file-tamper")
    result = checker.check_record(record_path, watchdog_path, SOURCE_SHA)
    assert not result["passed"], result
    assert any("checkpoint solution descriptor mismatch" in error for error in result["contract_errors"])


@pytest.mark.parametrize("stage", ("setup", "positive"))
def test_valid_setup_and_positive_evidence(tmp_path, stage):
    record, watchdog, _ = _record_base(tmp_path, stage)
    result = checker.check_record(record, watchdog, SOURCE_SHA)
    assert result["passed"], result


@pytest.mark.parametrize(
    "stage,mutation,needle",
    (
        ("positive", "initial", "zero-initial"),
        ("positive", "cycle_initial", "initial-guess"),
        ("setup", "p1_count", "p1 solve count"),
        ("setup", "swap", "maximum swap"),
        ("setup", "ledger", "retained ledger RSS"),
        ("positive", "checkpoint_roles", "solution-only"),
    ),
)
def test_lifecycle_count_window_and_checkpoint_bindings_fail_closed(tmp_path, stage, mutation, needle):
    record_path, watchdog_path, record = _record_base(tmp_path, stage)
    if mutation == "initial":
        record["stage_facts"]["initial_true_residual"] = 0.5
    elif mutation == "cycle_initial":
        record["stage_facts"]["cycles"][0]["initial_guess_nonzero"] = True
    elif mutation == "p1_count":
        record["stage_facts"]["p1_solve_count"] = 9
    elif mutation == "swap":
        record["stage_facts"]["apply_facts"][0]["resource"]["swap_bytes"] = 1
    elif mutation == "ledger":
        record["retained_ledger"]["measured_process_tree_rss_bytes"] += 1
    else:
        fact = record["stage_facts"]["checkpoint_facts"][0]
        manifest_path = Path(fact["manifest_path"])
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["forbidden_vector_roles"] = ["action"]
        manifest_path.write_text(json.dumps(manifest, allow_nan=False) + "\n", encoding="utf-8")
        fact["manifest_sha256"] = _sha(manifest_path)
    _write_record_with_closeout(record_path, record)
    result = checker.check_record(record_path, watchdog_path, SOURCE_SHA)
    assert not result["passed"], result
    assert any(needle in error for error in result["contract_errors"] + result["gate_failures"]), result


@pytest.mark.parametrize("mutation", ("missing", "residual", "resource", "raw"))
def test_representative_contract_and_gate_mutations_fail_closed(tmp_path, mutation):
    record_path, watchdog_path, record = _record_base(tmp_path, "positive")
    if mutation == "missing":
        del record["stage_facts"]["cycles"]
    elif mutation == "residual":
        record["stage_facts"]["final_true_residual"] = 1.0e-4
    elif mutation == "resource":
        rows = [json.loads(line) for line in (watchdog_path.parent / "watchdog.raw.jsonl").read_text().splitlines()]
        rows[-1]["authority"]["process_tree"]["rss_bytes"] = checker.COLD_LIMIT
        raw_path = watchdog_path.parent / "watchdog.raw.jsonl"
        raw_path.write_text("".join(json.dumps(row, allow_nan=False) + "\n" for row in rows), encoding="utf-8")
        compact = json.loads(watchdog_path.read_text())
        compact["raw_sha256"] = _sha(raw_path)
        compact["peak_process_tree_rss_bytes"] = checker.COLD_LIMIT
        watchdog_path.write_text(json.dumps(compact, allow_nan=False) + "\n", encoding="utf-8")
    else:
        with np.load(Path(record["raw_dir"]) / "positive_rank0.npz", allow_pickle=False) as bundle:
            values = {name: np.asarray(bundle[name]) for name in bundle.files}
        values["rhs"] = values["rhs"].copy()
        values["rhs"][0] += 0.25
        np.savez(Path(record["raw_dir"]) / "positive_rank0.npz", **values)
        record["stage_facts"]["raw"]["sha256"] = _sha(Path(record["raw_dir"]) / "positive_rank0.npz")
    record_path.write_text(json.dumps(record, allow_nan=False) + "\n", encoding="utf-8")
    result = checker.check_record(record_path, watchdog_path, SOURCE_SHA)
    assert not result["passed"], result


def test_same_worker_root_is_fail_closed(tmp_path):
    class Comm:
        rank = 0

        @staticmethod
        def bcast(value, root=0):
            return value

        @staticmethod
        def barrier():
            return None

    raw = tmp_path / "worker_raw"
    record = tmp_path / "record.json"
    runner._prepare_worker_paths(raw, record, Comm())
    with pytest.raises(FileExistsError):
        runner._prepare_worker_paths(raw, record, Comm())


def test_source_and_high_lift_contracts_are_slave_zero_ordered():
    source = (ROOT / "src/solvers/fullspace_lor_native_hx_fixture.py").read_text(encoding="utf-8")
    l2 = source[source.index("def build_l2_source"):source.index("def apply_high_action_copy")]
    assert "build_frozen_fullspace_primal_source" in l2
    helper = source[source.index("def build_frozen_fullspace_primal_source"):source.index("class L2HighActionShellContext")]
    assert "build_l2_source" in source and "homogenize" in helper
    assert "backsubstitution" not in helper
    fill = (ROOT / "src/solvers/fullspace_lor_memory_first_foundation.py").read_text(encoding="utf-8")
    body = fill[fill.index("def _fill_high_from_unique"):fill.index("def build_s2_foundation_case")]
    assert body.index("backsubstitution") < body.index("homogenize") < body.index("scatter_forward")


def test_import_boundaries_and_ast_duplicate_keys():
    for relative in ("benchmarks/run_task038_full3d_lor_nested_positive.py", "benchmarks/task038_full3d_lor_nested_positive_checker.py"):
        tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                keys = [key.value for key in node.keys if isinstance(key, ast.Constant) and isinstance(key.value, str)]
                assert len(keys) == len(set(keys)), relative
    checker_tree = ast.parse((ROOT / "benchmarks/task038_full3d_lor_nested_positive_checker.py").read_text(encoding="utf-8"))
    imports = []
    for node in checker_tree.body:
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    assert not any(name.startswith(("src", "benchmarks.run_task", "petsc4py", "mpi4py", "dolfinx")) for name in imports)
