"""Thin P0 physical Maxwell worker on the selected p6 same-mesh hierarchy.

The setup, positive auxiliary cycle, physical volume action, streaming
Fourier-DtN action, and recovery live in ``src``.  This worker only owns
fresh paths, the fixed restart-20 driver, raw arrays, markers, and facts.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
import gc
from pathlib import Path
import sys
import time
from typing import Any

import numpy as np

from benchmarks.run_task038_full3d_same_mesh_hcurl_pmg_p6_positive import (
    _array_sha,
    _jsonable,
    _prepare_paths,
    _resource_sample,
    _sha256_file,
    _source_facts,
    _stable_sha,
    _vector_facts,
    _vector_values,
    _write_json,
)


BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"
MODULE = "benchmarks.run_task038_full3d_same_mesh_hcurl_pmg_p0_physical"
STAGE = "p0-physical"
CASE = "p6-h10-mpi1"
SOURCE = "physical_rhs"
RECORD_SCHEMA = "task038.full3d.same-mesh-hcurl-pmg.p0-physical-record.v2"
MARKER_SCHEMA = "task038.full3d.same-mesh-hcurl-pmg.p0-physical-marker.v2"
INPUT_SHA256 = "819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41"
PHYSICAL_MODEL_SHA256 = "9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f"
MODE_MANIFEST_SHA256 = "dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2"
MARKERS = (
    "paths_ready",
    "bundle_built",
    "source_built",
    "solve_started",
    "solve_complete",
    "retained_ready",
    "retained_observed",
    "krylov_destroyed",
    "solver_stack_release_started",
    "solver_stack_release_complete",
    "release_observation",
    "recovery_started",
    "recovery_built",
    "official_outputs_written",
    "bundle_destroyed",
    "record_written",
)
LEVELS = (6, 3, 1)
PAIRS = ((6, 3), (3, 1))
RESTART = 20
CYCLE_MAX_IT = 20
MAX_IT = 20_000
CHECKPOINT_INTERVAL = 500
RESIDUAL_LIMIT = 1.0e-6
COLD_RSS_LIMIT = 2_000_000_000
RETAINED_WARNING = 1_800_000_000
RETAINED_DWELL_SECONDS = 2.0
RELEASE_OBSERVATION_SECONDS = 1.0
DIRECT_AUTHORITY = {
    "status": "scalar_only",
    "record_path": (
        "benchmarks/cases/102_hybrid_iterative_robustness/records/"
        "task037c_mpi8_three_way_qualification_v1.json"
    ),
    "record_sha256": (
        "eec638b833679937252982ae394012e88e679c058cccc0c4f6c091d33754fbd8"
    ),
    "profile": "p6/h10/13.5nm/s/grazing1/phi0",
    "arrays_included": False,
    "selected_eh_nearfield_available": False,
    "significant_12_power_and_12_amplitude_available": False,
}
SIGNIFICANT_GATE_SEMANTICS = {
    "identity_set_count": 12,
    "power_gate_count": 12,
    "complex_boundary_amplitude_gate_count": 12,
    "same_identity_set": True,
    "definition": (
        "one set of 12 significant diffraction identities: 12 power gates "
        "and 12 complex boundary-amplitude gates"
    ),
    "authority": "benchmarks/task035d_case097_checker.py::significant_12_power_and_12_amplitude",
}


def validate_profile(stage: str, case: str, source: str, mpi_size: int) -> None:
    if stage != STAGE or case != CASE or source != SOURCE or int(mpi_size) != 1:
        raise ValueError("P0 physical lane is fixed to p6-h10-mpi1 physical_rhs")


def _frozen_input_identity(
    specification: Any, payload: Mapping[str, Any], cfg: Any, mode_manifest_sha: str
) -> dict[str, Any]:
    incidence = payload["incidence"]
    internal = payload["derived"]["internal"]
    actual = {
        "model_id": str(specification.identity["model_id"]),
        "run_id": str(specification.identity["run_id"]),
        "comparison_group": str(specification.identity["comparison_group"]),
        "wavelength_nm": float(incidence["wavelength_nm"]),
        "grazing_angle_deg": float(incidence["grazing_angle_deg"]),
        "incident_theta_deg": float(internal["incident_theta_deg"]),
        "incident_phi_deg": float(internal["incident_phi_deg"]),
        "polarization": str(incidence["polarization"]),
        "nedelec_degree": int(cfg.nedelec_degree),
        "mesh_target_size_nm": float(cfg.mesh_target_size),
        "boundary_model": str(cfg.stage4_boundary_model),
        "dtn_order_policy": str(cfg.stage4_dtn_order_policy),
        "dtn_assembly": str(cfg.stage4_dtn_assembly),
    }
    expected = {
        "model_id": "euv_grazing1_phi0",
        "run_id": "euv_grazing1_phi0_full3d_iterative_mpi1",
        "comparison_group": "euv_grazing1_phi0",
        "wavelength_nm": 13.5,
        "grazing_angle_deg": 1.0,
        "incident_theta_deg": 89.0,
        "incident_phi_deg": 0.0,
        "polarization": "s",
        "nedelec_degree": 6,
        "mesh_target_size_nm": 10.0,
        "boundary_model": "dtn_port",
        "dtn_order_policy": "auto_propagating",
        "dtn_assembly": "auxiliary",
    }
    if specification.input_sha256 != INPUT_SHA256:
        raise RuntimeError("frozen Task038 input SHA does not match")
    if specification.physical_model_sha256 != PHYSICAL_MODEL_SHA256:
        raise RuntimeError("frozen Task038 physical-model SHA does not match")
    if str(mode_manifest_sha) != MODE_MANIFEST_SHA256:
        raise RuntimeError("frozen Task038 ordered mode manifest SHA does not match")
    if actual != expected:
        raise RuntimeError(f"frozen Task038 physical configuration does not match: {actual}")
    return {
        **actual,
        "input_adapter": "src.io.load_and_resolve",
        "config_adapter": "src.io.input_validation.simulation_config_3d_from_normalized",
        "input_sha256": str(specification.input_sha256),
        "physical_model_sha256": str(specification.physical_model_sha256),
        "mode_manifest_sha256": str(mode_manifest_sha),
    }


def _command(args: argparse.Namespace) -> list[str]:
    return [
        str(Path(sys.executable)),
        "-m",
        MODULE,
        "--stage",
        str(args.stage),
        "--case",
        str(args.case),
        "--source",
        str(args.source),
        "--raw-dir",
        str(Path(args.raw_dir).resolve()),
        "--jit-cache-dir",
        str(Path(args.jit_cache_dir).resolve()),
        "--checkpoint-root",
        str(Path(args.checkpoint_root).resolve()),
        "--record",
        str(Path(args.record).resolve()),
        "--expected-source-sha",
        str(args.expected_source_sha),
        "--expected-mpi-size",
        "1",
        "--input",
        str(Path(args.input).resolve()),
    ]


def _emit_marker(raw_dir: Path, name: str, source_sha: str, **facts: Any) -> None:
    if name not in MARKERS:
        raise ValueError(f"unknown P0 marker: {name}")
    _write_json(
        Path(raw_dir) / "markers" / f"{name}.json",
        {
            "schema": MARKER_SCHEMA,
            "marker": name,
            "source_sha": source_sha,
            "wall_time_ns": time.time_ns(),
            "facts": facts,
        },
    )


def _owned_slaves(setup: Mapping[str, Any]) -> np.ndarray:
    mpc = setup["floquets"][6].mpc
    index_map = mpc.function_space.dofmap.index_map
    owned = int(index_map.size_local) * int(
        mpc.function_space.dofmap.index_map_bs
    )
    values = np.asarray(mpc.slaves, dtype=np.int64)
    return np.asarray(values[(values >= 0) & (values < owned)], dtype=np.int32)


def _write_probe_npz(raw_dir: Path, arrays: Mapping[str, np.ndarray]) -> dict[str, Any]:
    path = Path(raw_dir) / "physical_probe.npz"
    if path.exists():
        raise FileExistsError(f"physical probe already exists: {path}")
    np.savez_compressed(
        path,
        **{
            key: np.asarray(value, dtype=np.complex128)
            for key, value in arrays.items()
        },
    )
    return {
        "relative_path": path.name,
        "bytes": int(path.stat().st_size),
        "sha256": _sha256_file(path),
        "roles": list(arrays),
        "solution_only": False,
    }


def _artifact_facts(directory: Path) -> list[dict[str, Any]]:
    return [
        {
            "relative_path": str(path.relative_to(directory)),
            "bytes": int(path.stat().st_size),
            "sha256": _sha256_file(path),
        }
        for path in sorted(path for path in directory.rglob("*") if path.is_file())
    ]


def _record(
    *,
    raw_dir: Path,
    checkpoint_root: Path,
    record_path: Path,
    command: list[str],
    source: Mapping[str, Any],
    rhs_facts: Mapping[str, Any],
    rhs_after_facts: Mapping[str, Any],
    owned_slave_indices: np.ndarray,
    setup_audit: Mapping[str, Any],
    physical_audit: Mapping[str, Any],
    architecture: Mapping[str, Any],
    rhs_generation: Mapping[str, Any],
    provenance: Mapping[str, Any],
    identities: Mapping[str, Any],
    result: Mapping[str, Any],
    pc_apply_facts: list[Mapping[str, Any]],
    npz_facts: Mapping[str, Any],
    recovery: Mapping[str, Any],
    action_calls: int,
) -> dict[str, Any]:
    krylov = {
        key: _jsonable(value)
        for key, value in result.items()
        if key != "final_solution"
    }
    driver_explicit = int(result["explicit_action_count"])
    final_recheck = 1
    explicit_total = driver_explicit + final_recheck
    krylov.update(
        {
            "driver_explicit_action_count": driver_explicit,
            "rhs_action_count": 0,
            "final_action_recheck_count": final_recheck,
            "extra_action_count": final_recheck,
            "explicit_action_count_total": explicit_total,
            "action_calls_total": int(action_calls),
            "pc_apply_facts": _jsonable(pc_apply_facts),
        }
    )
    architecture = dict(architecture)
    architecture["setup_audit"] = _jsonable(setup_audit)
    return {
        "schema": RECORD_SCHEMA,
        "stage": STAGE,
        "case": CASE,
        "source_name": SOURCE,
        "mpi_size": 1,
        "branch": BRANCH,
        "command": list(command),
        "raw_dir": str(Path(raw_dir).resolve()),
        "record_path": str(Path(record_path).resolve()),
        "checkpoint_root": str(Path(checkpoint_root).resolve()),
        "provenance": _jsonable(dict(provenance)),
        "identities": _jsonable(dict(identities)),
        "architecture": _jsonable(architecture),
        "source": _jsonable(
            {
                "facts": dict(source),
                "generation": str(rhs_generation["generation"]),
                "role": str(rhs_generation["role"]),
                "phase_application": str(rhs_generation["phase_application"]),
                "before": dict(rhs_facts),
                "after": dict(rhs_after_facts),
                "owned_slave_indices": [int(value) for value in owned_slave_indices],
            }
        ),
        "physical": {
            "audit": _jsonable(physical_audit),
            "recovery": _jsonable(dict(recovery)),
        },
        "npz": _jsonable(npz_facts),
        "settings": {
            "ksp_type": "gmres",
            "pc_side": "right",
            "norm_type": "unpreconditioned",
            "restart": RESTART,
            "cycle_max_it": CYCLE_MAX_IT,
            "max_it": MAX_IT,
            "residual_replacement": True,
            "zero_initial_guess": True,
            "checkpoint_interval": CHECKPOINT_INTERVAL,
            "first_checkpoint_iteration": None,
            "residual_limit": RESIDUAL_LIMIT,
        },
        "krylov": krylov,
        "lifecycle": {
            "marker_relative_dir": "markers",
            "marker_names": list(MARKERS),
            "retained_dwell_seconds": RETAINED_DWELL_SECONDS,
            "release_order": [
                "source_rhs",
                "retained_window",
                "krylov_result",
                "solver_stack",
                "recovery",
                "bundle",
            ],
            "external_process_tree_authority": True,
        },
        "raw_facts_only": True,
    }


def run_worker(args: argparse.Namespace) -> None:
    root = Path(__file__).resolve().parents[1]
    raw_dir = Path(args.raw_dir).resolve()
    jit_cache_dir = Path(args.jit_cache_dir).resolve()
    checkpoint_root = Path(args.checkpoint_root).resolve()
    record_path = Path(args.record).resolve()
    input_path = Path(args.input).resolve()
    if not input_path.is_file():
        raise FileNotFoundError(f"input template does not exist: {input_path}")
    command = _command(args)
    _prepare_paths(raw_dir, jit_cache_dir, checkpoint_root, record_path)
    _emit_marker(
        raw_dir,
        "paths_ready",
        args.expected_source_sha,
        worker_raw_dir=str(raw_dir),
        marker_dir=str(raw_dir / "markers"),
        jit_cache_dir=str(jit_cache_dir),
        checkpoint_root=str(checkpoint_root),
        record_path=str(record_path),
        isolated_jit_cache=True,
    )

    from mpi4py import MPI
    from petsc4py import PETSc

    from src.io import load_and_resolve
    from src.io.input_validation import simulation_config_3d_from_normalized
    from src.solvers.fullspace_memory_first_krylov import (
        destroy_krylov_result,
        run_restart20_cycles,
        write_solution_checkpoint,
    )
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
        audit_p6_same_mesh_physical_bundle,
        build_p6_same_mesh_physical_bundle,
        build_physical_rhs,
        destroy_p6_same_mesh_physical_bundle,
        release_p6_same_mesh_solver_stack,
        recover_p0_outputs,
    )

    comm = MPI.COMM_WORLD
    validate_profile(args.stage, args.case, args.source, comm.size)
    source = _source_facts(root, args.expected_source_sha, comm, PETSc)
    specification = load_and_resolve(input_path)
    payload = specification.as_jsonable()
    cfg = simulation_config_3d_from_normalized(payload)
    bundle: dict[str, Any] = {}
    result: dict[str, Any] | None = None
    rhs: Any = None
    final_action: Any = None
    final_residual: Any = None
    recovery_solution: Any = None
    record: dict[str, Any] | None = None
    try:
        bundle = build_p6_same_mesh_physical_bundle(cfg, comm)
        frozen_identity = _frozen_input_identity(
            specification, payload, cfg, bundle["mode_sha256"]
        )
        bundle_audit = audit_p6_same_mesh_physical_bundle(bundle)
        setup_audit = dict(bundle_audit["setup_audit"])
        physical_audit = dict(bundle_audit["physical_action"])
        architecture = dict(bundle_audit["architecture"])
        _emit_marker(
            raw_dir,
            "bundle_built",
            args.expected_source_sha,
            levels=list(LEVELS),
            physical_action=True,
            positive_auxiliary_pc=True,
        )
        rhs, rhs_generation = build_physical_rhs(bundle)
        rhs_before = _vector_values(rhs)
        slaves = _owned_slaves(bundle["setup"])
        rhs_before_facts = _vector_facts(rhs_before, slaves)
        _emit_marker(
            raw_dir,
            "source_built",
            args.expected_source_sha,
            generation=rhs_generation["generation"],
            role=rhs_generation["role"],
            mode_manifest_sha256=rhs_generation["mode_manifest_sha256"],
        )
        operator_authority = {
            "profile": PHYSICAL_PROFILE,
            "levels": list(LEVELS),
            "pairs": [list(pair) for pair in PAIRS],
            "setup_audit": _jsonable(setup_audit),
            "physical_action": _jsonable(physical_audit),
            "frozen_input": _jsonable(frozen_identity),
            "mode_manifest_sha256": str(bundle["mode_sha256"]),
        }
        physical_model_authority = {
            "profile": PHYSICAL_PROFILE,
            **_jsonable(frozen_identity),
            "same_physical_mesh": True,
            "form": "exact_maxwell_volume_plus_streaming_fourier_dtn",
            "coefficient_audit": _jsonable(bundle["setup"]["coefficient_audit"]),
        }
        input_authority = {
            **_jsonable(frozen_identity),
            "source_generation": rhs_generation,
            "rhs_array_sha256": _array_sha(rhs_before),
            "input_path": str(input_path),
        }
        identities = {
            "input_identity_authority": input_authority,
            "input_identity_sha256": _stable_sha(input_authority),
            "operator_identity_authority": operator_authority,
            "operator_identity_sha256": _stable_sha(operator_authority),
            "physical_model_authority": physical_model_authority,
            "physical_model_authority_sha256": _stable_sha(physical_model_authority),
            "physical_model_sha256": PHYSICAL_MODEL_SHA256,
        }
        provenance = dict(source)
        provenance.update(
            {
                "stage": STAGE,
                "case": CASE,
                "source_name": SOURCE,
                "raw_dir": str(raw_dir),
                "jit_cache_dir": str(jit_cache_dir),
                "checkpoint_root": str(checkpoint_root),
                "record_path": str(record_path),
                "input_path": str(input_path),
                "input_sha256": INPUT_SHA256,
                "physical_model_sha256": PHYSICAL_MODEL_SHA256,
                "mode_manifest_sha256": MODE_MANIFEST_SHA256,
                "command": list(command),
                "isolated_jit_cache": True,
            }
        )
        _emit_marker(
            raw_dir,
            "solve_started",
            args.expected_source_sha,
            ksp_type="gmres",
            restart=RESTART,
            cycle_max_it=CYCLE_MAX_IT,
            max_it=MAX_IT,
            zero_initial_guess=True,
            residual_limit=RESIDUAL_LIMIT,
        )
        action_calls = 0
        pc_apply_facts: list[dict[str, Any]] = []
        physical_action = bundle["physical_action"]
        upper_cycle = bundle["setup"]["upper_cycle"]

        def apply_action(vector: Any) -> Any:
            nonlocal action_calls
            target = rhs.duplicate()
            physical_action.apply(vector, target)
            action_calls += 1
            return target

        def apply_preconditioner(vector: Any) -> Any:
            output = upper_cycle.apply(vector)
            facts = dict(upper_cycle.last_apply_facts)
            lower = dict(facts["lower_cycle_facts"])
            pc_apply_facts.append(
                {
                    "apply_index": len(pc_apply_facts),
                    "p6_smoother_apply_count": int(facts["p6_smoother_apply_count"]),
                    "p63_adjoint_count": int(facts["p63_adjoint_count"]),
                    "p63_primal_count": int(facts["p63_primal_count"]),
                    "lower_cycle_count": int(facts["lower_cycle_count"]),
                    "p1_solve_count": int(facts["p1_solve_count"]),
                    "p1_relative_residual": float(lower["p1_relative_residual"]),
                    "output_finite": bool(facts["output_finite"]),
                    "owned_slave_max": float(facts["owned_slave_max"]),
                }
            )
            return output

        def checkpoint_writer(iteration: int, solution: Any, residual: float) -> Mapping[str, Any]:
            return write_solution_checkpoint(
                checkpoint_root / f"checkpoint-{int(iteration)}",
                solution,
                iteration=int(iteration),
                explicit_true_residual=float(residual),
                input_identity_sha256=identities["input_identity_sha256"],
                operator_identity_sha256=identities["operator_identity_sha256"],
                physical_model_sha256=identities["physical_model_sha256"],
                source_sha=args.expected_source_sha,
                ownership={
                    "rank": int(comm.rank),
                    "ownership_range": list(map(int, solution.getOwnershipRange())),
                    "local_size": int(solution.getLocalSize()),
                    "global_size": int(solution.getSize()),
                },
                comm=comm,
            )

        result = run_restart20_cycles(
            rhs,
            apply_action,
            apply_preconditioner,
            max_it=MAX_IT,
            residual_limit=RESIDUAL_LIMIT,
            resource_sample=_resource_sample,
            start_iteration=0,
            checkpoint_writer=checkpoint_writer,
            first_checkpoint_iteration=None,
            checkpoint_interval=CHECKPOINT_INTERVAL,
            stop_on_true_residual=True,
        )
        final_action = apply_action(result["final_solution"])
        final_residual = rhs.copy()
        final_residual.axpy(PETSc.ScalarType(-1.0), final_action)
        rhs_after = _vector_values(rhs)
        final_solution_values = _vector_values(result["final_solution"])
        final_action_values = _vector_values(final_action)
        final_residual_values = _vector_values(final_residual)
        npz_facts = _write_probe_npz(
            raw_dir,
            {
                "rhs_before": rhs_before,
                "rhs_after": rhs_after,
                "final_solution": final_solution_values,
                "final_action": final_action_values,
                "final_residual": final_residual_values,
            },
        )
        rhs_after_facts = _vector_facts(rhs_after, slaves)
        result_snapshot = {
            key: value for key, value in result.items() if key != "final_solution"
        }
        result_snapshot["final_output"] = _vector_facts(final_solution_values, slaves)
        result_snapshot["final_action"] = _vector_facts(final_action_values, slaves)
        result_snapshot["final_residual_facts"] = _vector_facts(
            final_residual_values, slaves
        )
        _emit_marker(
            raw_dir,
            "solve_complete",
            args.expected_source_sha,
            iterations=int(result["iterations"]),
            final_true_residual=float(result["final_true_residual"]),
            checkpoint_count=len(result["checkpoint_facts"]),
        )
        recovery_solution = result["final_solution"].copy()
        result_arrays = (
            rhs_before,
            rhs_after,
            final_solution_values,
            final_action_values,
            final_residual_values,
        )
        del result_arrays
        final_action.destroy()
        final_action = None
        final_residual.destroy()
        final_residual = None
        rhs.destroy()
        rhs = None
        del rhs_before, rhs_after, final_solution_values
        del final_action_values, final_residual_values
        _emit_marker(
            raw_dir,
            "retained_ready",
            args.expected_source_sha,
            retained_dwell_seconds=RETAINED_DWELL_SECONDS,
            retained_authority="external_foundation_watchdog_process_tree",
            retained_warning_bytes=RETAINED_WARNING,
        )
        time.sleep(RETAINED_DWELL_SECONDS)
        _emit_marker(
            raw_dir,
            "retained_observed",
            args.expected_source_sha,
            retained_dwell_seconds=RETAINED_DWELL_SECONDS,
        )
        destroy_krylov_result(result)
        result = None
        _emit_marker(raw_dir, "krylov_destroyed", args.expected_source_sha)
        _emit_marker(
            raw_dir,
            "solver_stack_release_started",
            args.expected_source_sha,
            preserved_objects=[
                "spaces",
                "floquets",
                "mesh_data",
                "cfg",
                "physical_action",
                "dtn_action",
                "volume_action",
                "recovery_solution",
            ],
        )
        release_p6_same_mesh_solver_stack(bundle)
        _emit_marker(
            raw_dir,
            "solver_stack_release_complete",
            args.expected_source_sha,
            released_objects=[
                "upper_cycle",
                "lower_cycle",
                "p63_owner_transfer",
                "p31_owner_transfer",
                "p6_shell",
                "p3_matrix",
                "p1_matrix",
            ],
        )
        from src.solvers.common_3d_utils import _trim_process_heap

        gc.collect()
        PETSc.garbage_cleanup(comm)
        gc.collect()
        heap_trim = _trim_process_heap()
        _emit_marker(
            raw_dir,
            "release_observation",
            args.expected_source_sha,
            observation_seconds=RELEASE_OBSERVATION_SECONDS,
            authority="external_foundation_watchdog_process_tree",
            cleanup={
                "gc_collect": True,
                "petsc_garbage_cleanup": True,
                "heap_trim": _jsonable(heap_trim),
            },
        )
        time.sleep(RELEASE_OBSERVATION_SECONDS)
        _emit_marker(raw_dir, "recovery_started", args.expected_source_sha)

        recovery: dict[str, Any]
        if float(result_snapshot["final_true_residual"]) <= RESIDUAL_LIMIT:
            official_dir = raw_dir / "official"
            official = recover_p0_outputs(bundle, recovery_solution, official_dir)
            if comm.rank == 0:
                _write_json(official_dir / "dtn_port_power_metrics_3d.json", official["port_metrics"])
            comm.barrier()
            recovery = {
                "status": "complete",
                "field_model": official["field_model"],
                "electric_finite": bool(official["electric_finite"]),
                "auxiliary_finite": bool(official["auxiliary_finite"]),
                "auxiliary_facts": _vector_facts(official["auxiliary"]),
                "port_metrics": official["port_metrics"],
                "volume_metrics": official["volume_metrics"],
                "diffraction_metrics": official["diffraction_metrics"],
                "diffraction_channel_count": int(official["diffraction_channel_count"]),
                "field_export": official["field_export"],
                "direct_authority": DIRECT_AUTHORITY,
                "significant_gate_semantics": SIGNIFICANT_GATE_SEMANTICS,
                "artifacts": _artifact_facts(official_dir) if comm.rank == 0 else [],
            }
            _emit_marker(
                raw_dir,
                "recovery_built",
                args.expected_source_sha,
                field_model="total_field",
                auxiliary_finite=bool(official["auxiliary_finite"]),
            )
            _emit_marker(
                raw_dir,
                "official_outputs_written",
                args.expected_source_sha,
                artifact_count=len(recovery["artifacts"]),
                dtn_mode_count=int(official["port_metrics"]["dtn_port_mode_count"]),
            )
        else:
            recovery = {
                "status": "not_run",
                "reason": "final explicit true residual did not meet P0 recovery threshold",
            }
            _emit_marker(
                raw_dir,
                "recovery_built",
                args.expected_source_sha,
                status="not_run",
                reason=recovery["reason"],
            )
            _emit_marker(
                raw_dir,
                "official_outputs_written",
                args.expected_source_sha,
                status="not_run",
                artifact_count=0,
            )
        recovery_solution.destroy()
        recovery_solution = None
        destroy_p6_same_mesh_physical_bundle(bundle)
        bundle = {}
        _emit_marker(raw_dir, "bundle_destroyed", args.expected_source_sha)
        record = _record(
            raw_dir=raw_dir,
            checkpoint_root=checkpoint_root,
            record_path=record_path,
            command=command,
            source=source,
            rhs_facts=rhs_before_facts,
            rhs_after_facts=rhs_after_facts,
            owned_slave_indices=slaves,
            setup_audit=setup_audit,
            physical_audit=physical_audit,
            architecture=architecture,
            rhs_generation=rhs_generation,
            provenance=provenance,
            identities=identities,
            result=result_snapshot,
            pc_apply_facts=pc_apply_facts,
            npz_facts=npz_facts,
            recovery=recovery,
            action_calls=action_calls,
        )
        _write_json(record_path, record)
        _emit_marker(
            raw_dir,
            "record_written",
            args.expected_source_sha,
            record_path=str(record_path),
            record_sha256=_sha256_file(record_path),
        )
    finally:
        if result is not None:
            destroy_krylov_result(result)
        for vector in (final_action, final_residual, rhs, recovery_solution):
            if vector is not None:
                vector.destroy()
        if bundle:
            destroy_p6_same_mesh_physical_bundle(bundle)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=(STAGE,), required=True)
    parser.add_argument("--case", choices=(CASE,), required=True)
    parser.add_argument("--source", choices=(SOURCE,), required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--jit-cache-dir", type=Path, required=True)
    parser.add_argument("--checkpoint-root", type=Path, required=True)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--expected-mpi-size", type=int, required=True)
    parser.add_argument("--input", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.expected_mpi_size != 1:
        raise ValueError("P0 physical worker is MPI1-only")
    run_worker(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "BRANCH",
    "CASE",
    "CHECKPOINT_INTERVAL",
    "COLD_RSS_LIMIT",
    "MARKER_SCHEMA",
    "MARKERS",
    "MAX_IT",
    "MODULE",
    "RECORD_SCHEMA",
    "RESIDUAL_LIMIT",
    "SOURCE",
    "STAGE",
    "build_parser",
    "main",
    "run_worker",
    "validate_profile",
]
