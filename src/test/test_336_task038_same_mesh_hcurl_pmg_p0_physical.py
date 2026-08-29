"""Focused P0 physical worker/checker and release-contract tests."""

from __future__ import annotations

import ast
import copy
from collections.abc import Mapping
import hashlib
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest

from benchmarks import run_task038_full3d_same_mesh_hcurl_pmg_p0_physical as worker
from benchmarks import task038_full3d_same_mesh_hcurl_pmg_p0_physical_checker as checker
from src.solvers import fullspace_same_mesh_hcurl_pmg_physical as core


SOURCE_SHA = "a" * 40


def _array_sha(values: np.ndarray) -> str:
    return hashlib.sha256(
        np.ascontiguousarray(values, dtype=np.complex128).tobytes(order="C")
    ).hexdigest()


def _facts(values: np.ndarray, slaves: tuple[int, ...] = (2,)) -> dict[str, object]:
    values = np.asarray(values, dtype=np.complex128)
    slave_max = 0.0 if not slaves else float(np.max(np.abs(values[list(slaves)])))
    return {
        "shape": list(values.shape),
        "dtype": str(values.dtype),
        "finite": bool(np.all(np.isfinite(values))),
        "nonzero": bool(np.linalg.norm(values) > 0.0),
        "norm": float(np.linalg.norm(values)),
        "array_sha256": _array_sha(values),
        "owned_slave_max": slave_max,
    }


def _write_markers(
    marker_dir: Path, record_path: Path, marker_times: dict[str, int], record_sha: str
) -> None:
    for name in worker.MARKERS:
        facts: dict[str, object] = {}
        if name == "record_written":
            facts = {"record_path": str(record_path.resolve()), "record_sha256": record_sha}
        (marker_dir / f"{name}.json").write_text(
            json.dumps(
                {
                    "schema": worker.MARKER_SCHEMA,
                    "marker": name,
                    "source_sha": SOURCE_SHA,
                    "wall_time_ns": marker_times[name],
                    "facts": facts,
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )


def _fixture(tmp_path: Path) -> tuple[Path, Path, dict[str, object]]:
    case_root = tmp_path / "p0-case"
    raw_dir = case_root / "worker_raw"
    jit_cache = case_root / "jit_cache"
    checkpoint_root = case_root / "checkpoints"
    marker_dir = raw_dir / "markers"
    official_dir = raw_dir / "official"
    watchdog_raw = case_root / "watchdog.raw.jsonl"
    watchdog_log = case_root / "worker.log"
    compact_path = case_root / "watchdog.compact.json"
    record_path = tmp_path / "record.json"
    raw_dir.mkdir(parents=True)
    for path in (marker_dir, jit_cache, checkpoint_root, official_dir):
        path.mkdir()
    watchdog_log.write_bytes(b"")
    input_path = Path(__file__).resolve().parents[2] / "input/templates/full3d_iterative_example.dat"

    rhs = np.asarray([1.0 + 0.0j, 0.5 + 0.1j, 0.0 + 0.0j], dtype=np.complex128)
    solution = np.asarray([0.2 + 0.1j, 0.3 - 0.1j, 0.0 + 0.0j], dtype=np.complex128)
    residual = np.asarray([1.0e-7 * np.linalg.norm(rhs), 0.0j, 0.0j], dtype=np.complex128)
    action = rhs - residual
    npz_path = raw_dir / "physical_probe.npz"
    arrays = {
        "rhs_before": rhs,
        "rhs_after": rhs.copy(),
        "final_solution": solution,
        "final_action": action,
        "final_residual": residual,
    }
    np.savez_compressed(npz_path, **arrays)

    x_nm = (np.arange(40, dtype=np.float64) + 0.5) * 50.0 / 40.0
    y_nm = (np.arange(20, dtype=np.float64) + 0.5) * 25.0 / 20.0
    z_nm = np.asarray([10.0, 30.0, 60.0, 90.0, 110.0], dtype=np.float64)
    grid = np.arange(5 * 20 * 40 * 3, dtype=np.float64).reshape(5, 20, 40, 3)
    electric = np.asarray(1.0 + grid + 1j * (grid + 0.5), dtype=np.complex128)
    magnetic = np.asarray(0.5 + grid - 1j * (grid + 1.5), dtype=np.complex128)
    reference = official_dir / "full3d_reference_samples.npz"
    np.savez_compressed(
        reference,
        x_nm=x_nm,
        y_nm=y_nm,
        z_nm=z_nm,
        E_V_per_m=electric,
        H_A_per_m=magnetic,
        interface_z_nm=z_nm[[0, -1]],
        E_t_interface_V_per_m=electric[[0, -1], ..., :2],
        H_t_interface_A_per_m=magnetic[[0, -1], ..., :2],
    )
    reference_metadata = official_dir / "full3d_reference_samples.json"
    reference_metadata.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "archive": reference.name,
                "archive_sha256": checker._sha256_file(reference),
                "archive_bytes": reference.stat().st_size,
                "array_shape_z_y_x_component": list(electric.shape),
                "point_count": 4000,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    diffraction = official_dir / "diffraction_orders_3d.json"
    diffraction.write_text(
        json.dumps(
            {
                "metrics": {"diffraction_channel_count": 1},
                "orders": [
                    {
                        "m": 0,
                        "n": 0,
                        "polarization": "s",
                        "alpha": 0.0,
                        "gamma": 0.0,
                        "beta_top": 1.0,
                        "beta_bottom": 1.0,
                        "reflected_amplitude": "0.0e+00+0.0e+00j",
                        "transmitted_amplitude": "0.0e+00+0.0e+00j",
                        "R": 0.3656257891787136,
                        "T": 0.01299063241062439,
                    }
                ],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    rta = official_dir / "rta.json"
    rta.write_text("{}\n", encoding="utf-8")

    command = worker._command(
        SimpleNamespace(
            stage=worker.STAGE,
            case=worker.CASE,
            source=worker.SOURCE,
            raw_dir=raw_dir,
            jit_cache_dir=jit_cache,
            checkpoint_root=checkpoint_root,
            record=record_path,
            expected_source_sha=SOURCE_SHA,
            input=input_path,
        )
    )
    physical_fields = dict(checker.EXPECTED_PHYSICAL_FIELDS)
    input_authority = {
        **physical_fields,
        "input_sha256": checker.INPUT_SHA256,
        "mode_manifest_sha256": checker.MODE_MANIFEST_SHA256,
    }
    operator_authority = {
        "levels": [6, 3, 1],
        "mode_manifest_sha256": checker.MODE_MANIFEST_SHA256,
    }
    physical_authority = {
        **physical_fields,
        "mode_manifest_sha256": checker.MODE_MANIFEST_SHA256,
    }
    identities = {
        "input_identity_authority": input_authority,
        "input_identity_sha256": checker._stable_sha(input_authority),
        "operator_identity_authority": operator_authority,
        "operator_identity_sha256": checker._stable_sha(operator_authority),
        "physical_model_authority": physical_authority,
        "physical_model_authority_sha256": checker._stable_sha(physical_authority),
        "physical_model_sha256": checker.PHYSICAL_MODEL_SHA256,
    }
    cycles = []
    for index, (start, end, matvec, pc) in enumerate(((0, 20, 20, 21), (20, 40, 21, 21))):
        cycles.append(
            {
                "cycle_index": index,
                "start_iteration": start,
                "end_iteration": end,
                "iterations": 20,
                "reason": 4,
                "initial_guess_nonzero": bool(index),
                "reported_final_residual": 1.0e-7,
                "explicit_true_residual": 1.0e-7,
                "matvec_count": matvec,
                "pc_apply_count": pc,
                "ksp_destroyed": True,
            }
        )
    pc_facts = [
        {
            "apply_index": index,
            "p6_smoother_apply_count": 2,
            "p63_adjoint_count": 1,
            "p63_primal_count": 1,
            "lower_cycle_count": 1,
            "p1_solve_count": 1,
            "p1_relative_residual": 1.0e-15,
            "output_finite": True,
            "owned_slave_max": 0.0,
        }
        for index in range(42)
    ]
    setup_arch = {
        "p6_matrix_free": True,
        "p6_global_aij": False,
        "global_dense_transfer": False,
        "global_transfer_matrix": False,
        "numeric_allgather": False,
        "p6_factor": False,
        "physical_solve": False,
        "dtn": False,
        "recovery": False,
        "high_order_global_aij": False,
        "outer_ksp_created": False,
    }
    setup_audit = {
        "schema": "task038.same_mesh_hcurl_pmg.setup.v1",
        "profile": {"levels": [6, 3, 1], "same_physical_mesh": True},
        "architecture": setup_arch,
    }
    physical_audit = {
        "schema": "task038.fullspace-physical-action.v1",
        "global_aij_materialized": False,
        "numeric_allgather": False,
        "t4_transmission_included": False,
    }
    architecture = {
        "levels": [6, 3, 1],
        "same_physical_mesh": True,
        "p6_matrix_free": True,
        "p3_sparse_allowed": True,
        "p1_sparse_allowed": True,
        "outer_ksp_created": True,
        "physical_solve": True,
        "dtn": True,
        "recovery": True,
        "p6_global_aij": False,
        "high_order_global_aij": False,
        "global_dense_transfer": False,
        "global_transfer_matrix": False,
        "numeric_allgather": False,
        "p6_factor": False,
        "source_is_pde_rhs": True,
        "setup_audit": setup_audit,
    }
    direct = {
        "R": 0.3656257891787136,
        "T": 0.01299063241062439,
        "A": 0.621383578410662,
        "A_volume": 0.6213835795387049,
    }
    port = {
        "R_total": direct["R"],
        "T_total": direct["T"],
        "R_plus_T": direct["R"] + direct["T"],
        "A_balance": 1.0 - direct["R"] - direct["T"],
        "R00_s": 0.1,
        "R00_p": 0.1,
        "dtn_port_top_mode_count": 12,
        "dtn_port_bottom_mode_count": 12,
    }
    recovery = {
        "status": "complete",
        "field_model": "total_field",
        "electric_finite": True,
        "auxiliary_finite": True,
        "port_metrics": port,
        "volume_metrics": {
            "A_volume_total": direct["A_volume"],
            "energy_closure_error_port_volume": port["R_total"] + port["T_total"] + direct["A_volume"] - 1.0,
        },
        "diffraction_metrics": {"diffraction_channel_count": 1},
        "diffraction_channel_count": 1,
        "field_export": {
            "full3d_reference_exported": True,
            "full3d_reference_archive": str(reference.resolve()),
            "full3d_reference_metadata": str(reference_metadata.resolve()),
            "full3d_reference_archive_sha256": checker._sha256_file(reference),
            "full3d_reference_archive_bytes": reference.stat().st_size,
            "full3d_reference_array_shape": list(electric.shape),
            "full3d_reference_plane_z_nm": z_nm.tolist(),
            "full3d_reference_point_count": 4000,
        },
        "direct_authority": {
            "status": "scalar_only",
            "record_path": "benchmarks/cases/102_hybrid_iterative_robustness/records/task037c_mpi8_three_way_qualification_v1.json",
            "record_sha256": checker.DIRECT_AUTHORITY_SHA256,
            "profile": "p6/h10/13.5nm/s/grazing1/phi0",
            "arrays_included": False,
            "selected_eh_nearfield_available": False,
            "significant_12_power_and_12_amplitude_available": False,
        },
        "significant_gate_semantics": {
            "identity_set_count": 12,
            "power_gate_count": 12,
            "complex_boundary_amplitude_gate_count": 12,
            "same_identity_set": True,
            "definition": checker.SIGNIFICANT_GATE_DEFINITION,
            "authority": "benchmarks/task035d_case097_checker.py::significant_12_power_and_12_amplitude",
        },
        "artifacts": [],
    }
    recovery["artifacts"] = [
        {
            "relative_path": str(path.relative_to(official_dir)),
            "bytes": path.stat().st_size,
            "sha256": checker._sha256_file(path),
        }
        for path in sorted(official_dir.iterdir())
        if path.is_file()
    ]
    provenance = {
        "source_sha": SOURCE_SHA,
        "branch": worker.BRANCH,
        "clean_source_tree": True,
        "qualified_activation": "1",
        "python_executable": str(Path(sys.executable)),
        "python_prefix": str(Path(sys.prefix)),
        "mpi_size": 1,
        "petsc_scalar_type": "complex128",
        "petsc_int_type": "int32",
        "threads": {name: "1" for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")},
        "abi_modules": {name: str(Path(sys.executable)) for name in ("mpi4py", "petsc4py", "dolfinx", "basix")},
        "stage": worker.STAGE,
        "case": worker.CASE,
        "source_name": worker.SOURCE,
        "raw_dir": str(raw_dir.resolve()),
        "jit_cache_dir": str(jit_cache.resolve()),
        "checkpoint_root": str(checkpoint_root.resolve()),
        "record_path": str(record_path.resolve()),
        "input_path": str(input_path.resolve()),
        "input_sha256": checker.INPUT_SHA256,
        "physical_model_sha256": checker.PHYSICAL_MODEL_SHA256,
        "mode_manifest_sha256": checker.MODE_MANIFEST_SHA256,
        "command": command,
        "isolated_jit_cache": True,
    }
    record = {
        "schema": worker.RECORD_SCHEMA,
        "stage": worker.STAGE,
        "case": worker.CASE,
        "source_name": worker.SOURCE,
        "mpi_size": 1,
        "branch": worker.BRANCH,
        "command": command,
        "raw_dir": str(raw_dir.resolve()),
        "record_path": str(record_path.resolve()),
        "checkpoint_root": str(checkpoint_root.resolve()),
        "provenance": provenance,
        "identities": identities,
        "architecture": architecture,
        "source": {
            "facts": {"source_sha": SOURCE_SHA},
            "generation": "dtn_port_modal_physical_rhs",
            "role": "physical_maxwell_rhs",
            "phase_application": "finalized_floquet_mpc_once",
            "before": _facts(rhs),
            "after": _facts(rhs),
            "owned_slave_indices": [2],
        },
        "physical": {"audit": physical_audit, "recovery": recovery},
        "npz": {
            "relative_path": "physical_probe.npz",
            "bytes": npz_path.stat().st_size,
            "sha256": checker._sha256_file(npz_path),
            "roles": list(arrays),
            "solution_only": False,
        },
        "settings": {
            "ksp_type": "gmres",
            "pc_side": "right",
            "norm_type": "unpreconditioned",
            "restart": 20,
            "cycle_max_it": 20,
            "max_it": 20_000,
            "residual_replacement": True,
            "zero_initial_guess": True,
            "checkpoint_interval": 500,
            "first_checkpoint_iteration": None,
            "residual_limit": 1.0e-6,
        },
        "krylov": {
            "settings": {},
            "initial_true_residual": 1.0,
            "cycles": cycles,
            "checkpoint_facts": [],
            "iterations": 40,
            "reason": 4,
            "final_true_residual": 1.0e-7,
            "matvec_count": 41,
            "pc_apply_count": 42,
            "explicit_action_count": 3,
            "ksp_destroy_count": 2,
            "driver_explicit_action_count": 3,
            "rhs_action_count": 0,
            "final_action_recheck_count": 1,
            "extra_action_count": 1,
            "explicit_action_count_total": 4,
            "action_calls_total": 45,
            "pc_apply_facts": pc_facts,
            "final_output": _facts(solution),
            "final_action": _facts(action),
            "final_residual_facts": _facts(residual),
        },
        "lifecycle": {
            "marker_relative_dir": "markers",
            "marker_names": list(worker.MARKERS),
            "retained_dwell_seconds": 2.0,
            "release_order": ["source_rhs", "retained_window", "krylov_result", "solver_stack", "recovery", "bundle"],
            "external_process_tree_authority": True,
        },
        "raw_facts_only": True,
    }
    record_path.write_text(json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")
    marker_times = {
        "paths_ready": 1_000_000_000,
        "bundle_built": 2_000_000_000,
        "source_built": 3_000_000_000,
        "solve_started": 4_000_000_000,
        "solve_complete": 5_000_000_000,
        "retained_ready": 6_000_000_000,
        "retained_observed": 8_000_000_000,
        "krylov_destroyed": 9_000_000_000,
        "solver_stack_release_started": 10_000_000_000,
        "solver_stack_release_complete": 11_000_000_000,
        "release_observation": 12_000_000_000,
        "recovery_started": 13_250_000_000,
        "recovery_built": 13_500_000_000,
        "official_outputs_written": 14_000_000_000,
        "bundle_destroyed": 15_000_000_000,
        "record_written": 16_000_000_000,
    }
    _write_markers(marker_dir, record_path, marker_times, checker._sha256_file(record_path))
    watchdog_rows = [
        {"wall_time_ns": 7_000_000_000, "authority": {"process_tree": {"all_status_readable": True, "rss_bytes": 100, "swap_bytes": 0}}},
        {"wall_time_ns": 9_500_000_000, "authority": {"process_tree": {"all_status_readable": True, "rss_bytes": 120, "swap_bytes": 0}}},
        {"wall_time_ns": 12_500_000_000, "authority": {"process_tree": {"all_status_readable": True, "rss_bytes": 90, "swap_bytes": 0}}},
    ]
    watchdog_raw.write_text("".join(json.dumps(row) + "\n" for row in watchdog_rows), encoding="utf-8")
    compact = {
        "schema": checker.WATCHDOG_SCHEMA,
        "source_sha": SOURCE_SHA,
        "worker_command": command,
        "worker_raw_dir": str(raw_dir.resolve()),
        "worker_record": str(record_path.resolve()),
        "watchdog_poll_seconds": 0.25,
        "watchdog_rss_limit_bytes": 2_000_000_000,
        "watchdog_raw": str(watchdog_raw.resolve()),
        "watchdog_log": str(watchdog_log.resolve()),
        "raw_sha256": checker._sha256_file(watchdog_raw),
        "sample_count": 3,
        "all_status_readable": True,
        "peak_process_tree_rss_bytes": 120,
        "max_process_tree_swap_bytes": 0,
        "natural_exit": True,
        "no_orphan": True,
        "returncode": 0,
    }
    compact_path.write_text(json.dumps(compact, sort_keys=True) + "\n", encoding="utf-8")
    return record_path, compact_path, {
        "record": record,
        "compact": compact,
        "arrays": arrays,
        "npz": npz_path,
        "watchdog_raw": watchdog_raw,
        "marker_dir": marker_dir,
        "marker_times": marker_times,
    }


def _rewrite_record(record_path: Path, record: dict[str, object], marker_dir: Path) -> None:
    record_path.write_text(json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")
    marker_path = marker_dir / "record_written.json"
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    marker["facts"]["record_sha256"] = checker._sha256_file(record_path)
    marker_path.write_text(json.dumps(marker, sort_keys=True) + "\n", encoding="utf-8")


def _restore_fixture(
    record_path: Path, facts: dict[str, object], marker_dir: Path, compact_path: Path
) -> None:
    arrays = facts["arrays"]
    assert isinstance(arrays, dict)
    np.savez_compressed(facts["npz"], **arrays)
    record = copy.deepcopy(facts["record"])
    assert isinstance(record, dict)
    record["npz"]["bytes"] = facts["npz"].stat().st_size
    record["npz"]["sha256"] = checker._sha256_file(facts["npz"])
    _rewrite_record(record_path, record, marker_dir)
    _write_markers(
        marker_dir,
        record_path,
        facts["marker_times"],
        checker._sha256_file(record_path),
    )
    raw = (
        "{\"wall_time_ns\":7000000000,\"authority\":{\"process_tree\":{\"all_status_readable\":true,\"rss_bytes\":100,\"swap_bytes\":0}}}\n"
        "{\"wall_time_ns\":9500000000,\"authority\":{\"process_tree\":{\"all_status_readable\":true,\"rss_bytes\":120,\"swap_bytes\":0}}}\n"
        "{\"wall_time_ns\":12500000000,\"authority\":{\"process_tree\":{\"all_status_readable\":true,\"rss_bytes\":90,\"swap_bytes\":0}}}\n"
    )
    facts["watchdog_raw"].write_text(raw, encoding="utf-8")
    compact = copy.deepcopy(facts["compact"])
    compact["sample_count"] = 3
    compact["peak_process_tree_rss_bytes"] = 120
    compact["raw_sha256"] = checker._sha256_file(facts["watchdog_raw"])
    compact_path.write_text(json.dumps(compact, sort_keys=True) + "\n", encoding="utf-8")


def test_p0_checker_validates_raw_residual_release_and_direct_layer(tmp_path: Path) -> None:
    record_path, compact_path, facts = _fixture(tmp_path)
    result = checker.check_record(record_path, compact_path, SOURCE_SHA)
    assert result["passed"] is False
    assert result["classification"] == "P0_NUMERICAL_PASS_PHYSICS_QUALIFICATION_BLOCKED"
    assert result["gate_failures"] == []
    assert result["physics_blockers"]
    assert result["metrics"]["scalar_direct_authority"]["scalar_pass"] is True
    assert result["metrics"]["release_observation"]["rss_delta_bytes"] == -30

    wrong_interpreter = copy.deepcopy(facts["record"])
    wrong_interpreter["provenance"]["python_executable"] = "/usr/bin/python3.12"
    wrong_interpreter["provenance"]["python_prefix"] = "/usr"
    wrong_interpreter["command"][0] = "/usr/bin/python3.12"
    wrong_interpreter["provenance"]["command"] = wrong_interpreter["command"]
    _rewrite_record(record_path, wrong_interpreter, facts["marker_dir"])
    failed = checker.check_record(record_path, compact_path, SOURCE_SHA)
    assert any("lexical checkout .venv" in item for item in failed["contract_errors"])
    _restore_fixture(record_path, facts, facts["marker_dir"], compact_path)
    recovery_marker_path = facts["marker_dir"] / "recovery_started.json"
    recovery_marker = json.loads(recovery_marker_path.read_text())
    recovery_marker["wall_time_ns"] = 12_750_000_000
    recovery_marker_path.write_text(json.dumps(recovery_marker) + "\n")
    failed = checker.check_record(record_path, compact_path, SOURCE_SHA)
    assert any("shorter than one second" in item for item in failed["contract_errors"])

    _restore_fixture(record_path, facts, facts["marker_dir"], compact_path)
    rows = [json.loads(line) for line in facts["watchdog_raw"].read_text().splitlines()]
    rows[-1]["authority"]["process_tree"]["rss_bytes"] = 120
    facts["watchdog_raw"].write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    compact = copy.deepcopy(facts["compact"])
    compact["raw_sha256"] = checker._sha256_file(facts["watchdog_raw"])
    compact_path.write_text(json.dumps(compact) + "\n", encoding="utf-8")
    failed = checker.check_record(record_path, compact_path, SOURCE_SHA)
    assert any("RSS did not decrease" in item for item in failed["gate_failures"])

    _restore_fixture(record_path, facts, facts["marker_dir"], compact_path)
    rows = [json.loads(line) for line in facts["watchdog_raw"].read_text().splitlines()]
    rows[-1]["wall_time_ns"] = 13_500_000_000
    facts["watchdog_raw"].write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    compact = copy.deepcopy(facts["compact"])
    compact["raw_sha256"] = checker._sha256_file(facts["watchdog_raw"])
    compact_path.write_text(json.dumps(compact) + "\n", encoding="utf-8")
    failed = checker.check_record(record_path, compact_path, SOURCE_SHA)
    assert any("release-before/release-after" in item for item in failed["contract_errors"])
    _restore_fixture(record_path, facts, facts["marker_dir"], compact_path)

    mutated = copy.deepcopy(facts["record"])
    assert isinstance(mutated, dict)
    mutated["architecture"]["source_is_pde_rhs"] = False
    _rewrite_record(record_path, mutated, facts["marker_dir"])
    failed = checker.check_record(record_path, compact_path, SOURCE_SHA)
    assert failed["classification"] == "CONTRACT_INVALID"

    _restore_fixture(record_path, facts, facts["marker_dir"], compact_path)
    with np.load(facts["npz"], allow_pickle=False) as data:
        arrays = {name: np.asarray(data[name]).copy() for name in data.files}
    arrays["final_residual"][0] = 2.0e-6 * np.linalg.norm(arrays["rhs_before"])
    arrays["final_action"] = arrays["rhs_before"] - arrays["final_residual"]
    np.savez_compressed(facts["npz"], **arrays)
    mutated = copy.deepcopy(facts["record"])
    mutated["npz"]["bytes"] = facts["npz"].stat().st_size
    mutated["npz"]["sha256"] = checker._sha256_file(facts["npz"])
    _rewrite_record(record_path, mutated, facts["marker_dir"])
    failed = checker.check_record(record_path, compact_path, SOURCE_SHA)
    assert any("raw explicit true residual" in item for item in failed["gate_failures"])

    _restore_fixture(record_path, facts, facts["marker_dir"], compact_path)
    with np.load(facts["npz"], allow_pickle=False) as data:
        arrays = {name: np.asarray(data[name]).copy() for name in data.files}
    arrays["final_residual"][0] = 2.0e-6 * np.linalg.norm(arrays["rhs_before"])
    arrays["final_action"] = arrays["rhs_before"] - arrays["final_residual"]
    np.savez_compressed(facts["npz"], **arrays)
    mutated = copy.deepcopy(facts["record"])
    mutated["krylov"]["final_true_residual"] = 2.0e-6
    mutated["physical"]["recovery"] = {
        "status": "not_run",
        "reason": "final explicit true residual did not meet P0 recovery threshold",
    }
    mutated["npz"]["bytes"] = facts["npz"].stat().st_size
    mutated["npz"]["sha256"] = checker._sha256_file(facts["npz"])
    _rewrite_record(record_path, mutated, facts["marker_dir"])
    for name, marker_facts in {
        "recovery_built": {
            "status": "not_run",
            "reason": "final explicit true residual did not meet P0 recovery threshold",
        },
        "official_outputs_written": {"status": "not_run", "artifact_count": 0},
    }.items():
        marker_path = facts["marker_dir"] / f"{name}.json"
        marker = json.loads(marker_path.read_text())
        marker["facts"] = marker_facts
        marker_path.write_text(json.dumps(marker) + "\n")
    failed = checker.check_record(record_path, compact_path, SOURCE_SHA)
    assert failed["classification"] == "P0_PHYSICAL_GATE_FAIL"
    assert not any("marker" in item for item in failed["contract_errors"])

    _restore_fixture(record_path, facts, facts["marker_dir"], compact_path)
    missing = facts["marker_dir"] / "release_observation.json"
    marker_bytes = missing.read_bytes()
    missing.unlink()
    failed = checker.check_record(record_path, compact_path, SOURCE_SHA)
    assert failed["contract_errors"]
    missing.write_bytes(marker_bytes)

    ordered = json.loads((facts["marker_dir"] / "release_observation.json").read_text())
    ordered["wall_time_ns"] = 10_500_000_000
    (facts["marker_dir"] / "release_observation.json").write_text(json.dumps(ordered) + "\n")
    failed = checker.check_record(record_path, compact_path, SOURCE_SHA)
    assert failed["contract_errors"]
    _restore_fixture(record_path, facts, facts["marker_dir"], compact_path)

    raw_bytes = facts["watchdog_raw"].read_bytes()
    facts["watchdog_raw"].write_bytes(b"\n".join(raw_bytes.splitlines()[:2]) + b"\n")
    compact = copy.deepcopy(facts["compact"])
    compact["sample_count"] = 2
    compact["raw_sha256"] = checker._sha256_file(facts["watchdog_raw"])
    compact_path.write_text(json.dumps(compact) + "\n")
    failed = checker.check_record(record_path, compact_path, SOURCE_SHA)
    assert any("release-before/release-after" in item for item in failed["contract_errors"])
    _restore_fixture(record_path, facts, facts["marker_dir"], compact_path)

    wrong = copy.deepcopy(facts["record"])
    wrong["identities"]["physical_model_authority"]["grazing_angle_deg"] = 10.0
    wrong["identities"]["physical_model_authority_sha256"] = checker._stable_sha(
        wrong["identities"]["physical_model_authority"]
    )
    _rewrite_record(record_path, wrong, facts["marker_dir"])
    failed = checker.check_record(record_path, compact_path, SOURCE_SHA)
    assert any("grazing_angle_deg" in item for item in failed["contract_errors"])

    archive = Path(facts["record"]["physical"]["recovery"]["field_export"]["full3d_reference_archive"])
    metadata_path = Path(facts["record"]["physical"]["recovery"]["field_export"]["full3d_reference_metadata"])
    with np.load(archive, allow_pickle=False) as data:
        reference_arrays = {name: np.asarray(data[name]).copy() for name in data.files}
    reference_arrays["x_nm"] = np.arange(40, dtype=np.float64)
    np.savez_compressed(archive, **reference_arrays)
    metadata = json.loads(metadata_path.read_text())
    metadata["archive_sha256"] = checker._sha256_file(archive)
    metadata["archive_bytes"] = archive.stat().st_size
    metadata_path.write_text(json.dumps(metadata) + "\n")
    wrong = copy.deepcopy(facts["record"])
    export = wrong["physical"]["recovery"]["field_export"]
    export["full3d_reference_archive_sha256"] = checker._sha256_file(archive)
    export["full3d_reference_archive_bytes"] = archive.stat().st_size
    for artifact in wrong["physical"]["recovery"]["artifacts"]:
        if artifact["relative_path"] == archive.name:
            artifact["sha256"] = checker._sha256_file(archive)
            artifact["bytes"] = archive.stat().st_size
        elif artifact["relative_path"] == metadata_path.name:
            artifact["sha256"] = checker._sha256_file(metadata_path)
            artifact["bytes"] = metadata_path.stat().st_size
    _rewrite_record(record_path, wrong, facts["marker_dir"])
    failed = checker.check_record(record_path, compact_path, SOURCE_SHA)
    assert any("official complex E/H reference facts" in item for item in failed["gate_failures"])


def test_p0_recovery_calls_official_export_once_and_releases_stack_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = {"recover": 0, "export": 0}

    class FakeVec:
        def __init__(self, values: np.ndarray):
            self.values = np.asarray(values, dtype=np.complex128)

        def copy(self, target: object) -> None:
            target.array[:] = self.values

    class FakeField:
        def __init__(self, space: object):
            self.function_space = space
            self.x = SimpleNamespace(
                array=np.zeros(3, dtype=np.complex128),
                petsc_vec=SimpleNamespace(array=np.zeros(3, dtype=np.complex128)),
            )
            self.x.petsc_vec.array = self.x.array

            def scatter_forward() -> None:
                return None

            self.x.scatter_forward = scatter_forward

    fake_fem = ModuleType("dolfinx.fem")
    fake_fem.Function = lambda space, name=None: FakeField(space)
    fake_dolfinx = ModuleType("dolfinx")
    fake_dolfinx.fem = fake_fem
    monkeypatch.setitem(sys.modules, "dolfinx", fake_dolfinx)
    monkeypatch.setitem(sys.modules, "dolfinx.fem", fake_fem)

    postprocess = ModuleType("src.postprocessing.postprocess_3d")

    def save_fields(*args: object, **kwargs: object) -> dict[str, object]:
        calls["export"] += 1
        return {"full3d_reference_exported": True}

    postprocess.save_airbox_3d_fields = save_fields
    diffraction = ModuleType("src.postprocessing.diffraction_3d")
    diffraction.compute_diffraction_orders_3d = lambda *args, **kwargs: {"diffraction_channel_count": 12}
    rta = ModuleType("src.postprocessing.rta_3d")
    rta.compute_volume_absorption_3d = lambda *args, **kwargs: {"A_volume_total": 0.5}
    dtn_port = ModuleType("src.solvers.dtn_port_3d")
    dtn_port._port_power_metrics = lambda *args, **kwargs: {"R_total": 0.2, "T_total": 0.3}
    modes = ModuleType("src.common.modes_3d")
    modes.incident_power_3d = lambda cfg: 1.0
    for name, module in {
        "src.postprocessing.postprocess_3d": postprocess,
        "src.postprocessing.diffraction_3d": diffraction,
        "src.postprocessing.rta_3d": rta,
        "src.solvers.dtn_port_3d": dtn_port,
        "src.common.modes_3d": modes,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)

    class FakeMpc:
        function_space = SimpleNamespace()

        def homogenize(self, field: object) -> None:
            return None

        def backsubstitution(self, field: object) -> None:
            return None

    class FakeDtn:
        def recover_auxiliary(self, solution: object) -> np.ndarray:
            calls["recover"] += 1
            return np.asarray([1.0 + 0.0j], dtype=np.complex128)

    space = SimpleNamespace()
    floquet = SimpleNamespace(mpc=FakeMpc())
    bundle = {
        "setup": {"floquets": {6: floquet}, "mesh_data": SimpleNamespace()},
        "cfg": SimpleNamespace(),
        "dtn_action": FakeDtn(),
        "modes": (),
        "incident_projections": (),
    }
    bundle["setup"]["floquets"][6].mpc.function_space = space
    solution = FakeVec(np.asarray([1.0 + 0.0j, 2.0 + 0.0j, 3.0 + 0.0j]))
    result = core.recover_p0_outputs(bundle, solution, tmp_path / "official")
    assert calls == {"recover": 1, "export": 1}
    assert result["field_export"] == {"full3d_reference_exported": True}
    assert "direct_authority" not in result
    assert "significant_gate_semantics" not in result
    assert "physics_qualification" not in result

    class Counted:
        def __init__(self) -> None:
            self.count = 0

        def destroy(self) -> None:
            self.count += 1

    upper = Counted()
    p3 = Counted()
    p1 = Counted()
    kept = object()
    stack = {
        "upper_cycle": upper,
        "p3_matrix": p3,
        "p1_matrix": p1,
        "spaces": kept,
    }
    held = {"setup": stack, "physical_action": kept}
    core.release_p6_same_mesh_solver_stack(held)
    core.release_p6_same_mesh_solver_stack(held)
    assert (upper.count, p3.count, p1.count) == (1, 1, 1)
    assert held["physical_action"] is kept and held["setup"]["spaces"] is kept


def test_p0_stage_callback_order_and_optional_marker_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[tuple[str, dict[str, object]]] = []

    def callback(name: str, facts: Mapping[str, object]) -> None:
        events.append((name, dict(facts)))

    setup_module = ModuleType("src.solvers.fullspace_same_mesh_hcurl_pmg_setup")
    setup_module.build_p6_same_mesh_setup = lambda cfg, comm: {
        "spaces": {6: "p6-space"},
        "floquets": {6: SimpleNamespace(mpc=object())},
        "mesh_data": SimpleNamespace(mesh="mesh"),
    }
    dtn_action_module = ModuleType("src.solvers.fullspace_dtn_action")
    dtn_action_module.build_dynamic_mode_inventory = lambda cfg: (["m0", "m1"], [0, 1], "mode-sha")
    dtn_action_module.build_fullspace_dtn_carrier_from_surface = lambda *args, **kwargs: "carrier"
    dtn_action_module.build_fullspace_dtn_action = lambda *args, **kwargs: "dtn-action"
    mpc_module = ModuleType("src.solvers.fullspace_mpc_action")
    mpc_module.build_fullspace_mpc_form_action = lambda *args, **kwargs: "volume-action"
    physical_module = ModuleType("src.solvers.fullspace_physical_action")
    physical_module.FullspacePhysicalAction = lambda *args, **kwargs: "physical-action"
    forms_module = ModuleType("src.solvers.common_3d_forms")
    forms_module._build_variational_forms = lambda *args, **kwargs: ("bilinear", "rhs")
    dtn_port_module = ModuleType("src.solvers.dtn_port_3d")

    class FakeAssembler:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

    dtn_port_module._ReusableSurfaceComponentAssembler = FakeAssembler
    dtn_port_module._dtn_surface_quadrature_degree = lambda cfg, modes: 7
    dtn_port_module._incident_projection_onto_top_mode = lambda mode, cfg: f"projection-{mode}"
    for name, module in {
        "src.solvers.fullspace_same_mesh_hcurl_pmg_setup": setup_module,
        "src.solvers.fullspace_dtn_action": dtn_action_module,
        "src.solvers.fullspace_mpc_action": mpc_module,
        "src.solvers.fullspace_physical_action": physical_module,
        "src.solvers.common_3d_forms": forms_module,
        "src.solvers.dtn_port_3d": dtn_port_module,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)

    cfg = SimpleNamespace(tags=SimpleNamespace(z_max=1.0, z_min=0.0))
    bundle = core.build_p6_same_mesh_physical_bundle(
        cfg, SimpleNamespace(size=1), stage_callback=callback
    )
    assert [name for name, _facts in events] == [
        "positive_setup_started",
        "positive_setup_complete",
        "mode_inventory_started",
        "mode_inventory_complete",
        "surface_assemblers_started",
        "surface_assemblers_complete",
        "dtn_carrier_started",
        "dtn_carrier_complete",
        "dtn_action_complete",
        "physical_volume_action_started",
        "physical_volume_action_complete",
        "bundle_built",
    ]
    facts = dict(events)
    assert facts["mode_inventory_complete"] == {
        "mode_count": 2,
        "mode_manifest_sha256": "mode-sha",
        "dtn_quadrature_degree": 7,
    }
    assert facts["physical_volume_action_complete"]["volume_action"] is True
    assert bundle["physical_action"] == "physical-action"

    common = [
        "--stage", worker.STAGE,
        "--case", worker.CASE,
        "--source", worker.SOURCE,
        "--raw-dir", str(tmp_path / "raw"),
        "--jit-cache-dir", str(tmp_path / "jit"),
        "--checkpoint-root", str(tmp_path / "checkpoints"),
        "--record", str(tmp_path / "record.json"),
        "--expected-source-sha", SOURCE_SHA,
        "--expected-mpi-size", "1",
        "--input", str(tmp_path / "input.dat"),
    ]
    default_args = worker.build_parser().parse_args(common)
    v14_dir = tmp_path / "v14-markers"
    v14_args = worker.build_parser().parse_args(
        [*common, "--v14-marker-dir", str(v14_dir)]
    )
    assert "--v14-marker-dir" not in worker._command(default_args)
    assert worker._command(v14_args)[-2:] == ["--v14-marker-dir", str(v14_dir.resolve())]


def test_p0_input_angle_identity_and_lazy_import_boundary(tmp_path: Path) -> None:
    from src.io import load_and_resolve
    from src.io.input_validation import simulation_config_3d_from_normalized

    input_path = Path(__file__).resolve().parents[2] / "input/templates/full3d_iterative_example.dat"
    specification = load_and_resolve(input_path)
    cfg = simulation_config_3d_from_normalized(specification.as_jsonable())
    assert specification.input_sha256 == checker.INPUT_SHA256
    assert specification.physical_model_sha256 == checker.PHYSICAL_MODEL_SHA256
    assert cfg.incident_theta_deg == pytest.approx(89.0)

    altered = tmp_path / "altered.dat"
    altered.write_text(
        input_path.read_text(encoding="utf-8").replace(
            "grazing_angle_deg = 1.0", "grazing_angle_deg = 10.0"
        ),
        encoding="utf-8",
    )
    altered_specification = load_and_resolve(altered)
    altered_cfg = simulation_config_3d_from_normalized(altered_specification.as_jsonable())
    assert altered_specification.physical_model_sha256 != specification.physical_model_sha256
    assert altered_cfg.incident_theta_deg == pytest.approx(80.0)

    source = Path(worker.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    module_imports = [node for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))]
    imported = " ".join(ast.unparse(node) for node in module_imports)
    assert "dolfinx" not in imported
    assert "petsc4py" not in imported
    assert "mpi4py" not in imported
    assert worker.MAX_IT == 20_000
    assert worker.RESIDUAL_LIMIT == 1.0e-6
