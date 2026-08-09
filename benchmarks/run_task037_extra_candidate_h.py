"""Thin Candidate-H H1.2 action-only worker and watchdog.

The worker builds the frozen p6 full-space volume form, a reference
"MpcFormActionContext", and the independent element-local Candidate-H
action in one process. It never enters condensation, DtN assembly, KSP, or
field recovery. Large outputs belong under the ignored artifact directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

from benchmarks.canonical_vector_artifacts import (
    canonical_shard_manifest,
    compare_canonical_manifests,
    read_canonical_manifest,
    write_canonical_manifest,
    write_canonical_packet_shard,
)
from benchmarks.run_task033_case090_watchdog import (
    inspect_tracked_source,
    sample_memory,
    terminate_process_tree,
)


GIB = 1024**3
H1_RSS_LIMIT_BYTES = int(1.25 * GIB)
H1_POLL_SECONDS = 0.25
H1_TIMEOUT_SECONDS = 1800.0
DUAL_RELATIVE_TOLERANCE = 1.0e-11
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

SOURCE_DEFINITIONS = {
    "seed_17037": {
        "seed": 17037,
        "frequency": (1, 1, 0),
        "envelope_coefficients": {
            "constant": (1.0, 0.0),
            "xi": (0.15, 0.0),
            "eta": (0.0, 0.05),
            "zeta": (0.03, 0.0),
        },
        "formula": (
            "polarization_vector*(constant+xi_coeff*xi+eta_coeff*eta+"
            "zeta_coeff*zeta)*exp(2j*pi*dot(frequency,(xi,eta,zeta)))"
        ),
    },
    "seed_27037": {
        "seed": 27037,
        "frequency": (2, 1, 1),
        "envelope_coefficients": {
            "constant": (1.0, 0.0),
            "xi": (0.10, 0.0),
            "eta": (0.0, 0.08),
            "zeta": (0.0, 0.04),
        },
        "formula": (
            "polarization_vector*(constant+xi_coeff*xi+eta_coeff*eta+"
            "zeta_coeff*zeta)*exp(2j*pi*dot(frequency,(xi,eta,zeta)))"
        ),
    },
    "seed_37037": {
        "seed": 37037,
        "frequency": (4, 3, 2),
        "envelope_coefficients": {
            "constant": (1.0, 0.0),
            "xi": (0.07, 0.0),
            "eta": (0.06, 0.0),
            "zeta": (0.0, 0.05),
        },
        "formula": (
            "polarization_vector*(constant+xi_coeff*xi+eta_coeff*eta+"
            "zeta_coeff*zeta)*exp(2j*pi*dot(frequency,(xi,eta,zeta)))"
        ),
    },
    "physical_rhs_like_primal": {
        "seed": None,
        "frequency": None,
        "formula": (
            "incident_amplitude*polarization_vector*"
            "exp(j*dot(wavevector,physical_coordinate))"
        ),
    },
}


def _inspect_candidate_source() -> Any:
    previous_git_dir = os.environ.get("GIT_DIR")
    previous_git_work_tree = os.environ.get("GIT_WORK_TREE")
    os.environ["GIT_DIR"] = str(REPOSITORY_ROOT / ".git-codex")
    os.environ["GIT_WORK_TREE"] = str(REPOSITORY_ROOT)
    try:
        return inspect_tracked_source(REPOSITORY_ROOT)
    finally:
        if previous_git_dir is None:
            os.environ.pop("GIT_DIR", None)
        else:
            os.environ["GIT_DIR"] = previous_git_dir
        if previous_git_work_tree is None:
            os.environ.pop("GIT_WORK_TREE", None)
        else:
            os.environ["GIT_WORK_TREE"] = previous_git_work_tree


def _json_pair(value: complex) -> list[float]:
    number = complex(value)
    return [float(number.real), float(number.imag)]


def _source_definition(label: str, cfg) -> dict[str, Any]:
    definition = dict(SOURCE_DEFINITIONS[label])
    definition["label"] = label
    definition["incident_wavevector"] = [
        _json_pair(value) for value in cfg.wavevector
    ]
    definition["incident_polarization"] = [
        _json_pair(value) for value in cfg.polarization_vector
    ]
    definition["incident_amplitude"] = _json_pair(cfg.incident_amplitude)
    definition["constraint_application"] = "dolfinx_mpc.backsubstitution"
    definition["frozen_bloch_handling"] = (
        "coordinate analytic interpolation followed by MPC backsubstitution"
    )
    definition["primal_semantics"] = (
        "incident electric plane-wave N1curl probe, not assembled traction RHS"
        if label == "physical_rhs_like_primal"
        else "coordinate-scaled analytic vector primal probe"
    )
    definition["definition_sha256"] = hashlib.sha256(
        json.dumps(definition, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return definition


def _source_values(label: str, cfg, coordinates):
    import numpy as np

    x = np.asarray(coordinates, dtype=np.float64)
    if label == "physical_rhs_like_primal":
        phase = np.exp(
            1j
            * np.sum(
                np.asarray(cfg.wavevector, dtype=np.complex128)[:, None] * x,
                axis=0,
            )
        )
        return (
            complex(cfg.incident_amplitude)
            * np.asarray(cfg.polarization_vector, dtype=np.complex128)[:, None]
            * phase[None, :]
        )
    scale = np.asarray(
        (
            cfg.x_max - cfg.x_min,
            cfg.y_max - cfg.y_min,
            cfg.domain_z_max - cfg.domain_z_min,
        ),
        dtype=np.float64,
    )
    xi = (x[0] - float(cfg.x_min)) / scale[0]
    eta = (x[1] - float(cfg.y_min)) / scale[1]
    zeta = (x[2] - float(cfg.domain_z_min)) / scale[2]
    source_definition = SOURCE_DEFINITIONS[label]
    frequency = source_definition["frequency"]
    phase = np.exp(
        2j
        * np.pi
        * (
            frequency[0] * xi
            + frequency[1] * eta
            + frequency[2] * zeta
        )
    )
    coefficients = source_definition["envelope_coefficients"]
    envelope = sum(
        complex(*coefficients[name]) * values
        for name, values in (
            ("constant", 1.0),
            ("xi", xi),
            ("eta", eta),
            ("zeta", zeta),
        )
    )
    polarization = np.asarray(cfg.polarization_vector, dtype=np.complex128)
    return polarization[:, None] * envelope[None, :] * phase[None, :]


def _make_primal_source(function_space, mpc, cfg, label):
    from dolfinx import fem
    from dolfinx.la.petsc import create_vector
    from petsc4py import PETSc

    field = fem.Function(function_space)
    field.interpolate(lambda coordinates: _source_values(label, cfg, coordinates))
    field.x.scatter_forward()
    index_map = mpc.function_space.dofmap.index_map
    source = create_vector([(index_map, mpc.function_space.dofmap.index_map_bs)])
    owned_size = int(index_map.size_local)
    with source.localForm() as local:
        local.set(0.0)
        local.array_w[:owned_size] = field.x.array[:owned_size]
    source.ghostUpdate(
        addv=PETSc.InsertMode.INSERT_VALUES,
        mode=PETSc.ScatterMode.FORWARD,
    )
    mpc.backsubstitution(source)
    source.ghostUpdate(
        addv=PETSc.InsertMode.INSERT_VALUES,
        mode=PETSc.ScatterMode.FORWARD,
    )
    del field
    return source


def _action_record(
    reference_context,
    candidate_action,
    source,
    *,
    run_dir: Path,
    label: str,
    cfg,
    function_space,
    mpc,
    tolerance: float,
) -> dict[str, Any]:
    import numpy as np
    from mpi4py import MPI

    reference_output = source.duplicate()
    candidate_output = source.duplicate()
    candidate_repeat = source.duplicate()
    difference = source.duplicate()
    try:
        reference_start = time.perf_counter()
        reference_context.mult(None, source, reference_output)
        reference_seconds = time.perf_counter() - reference_start
        candidate_start = time.perf_counter()
        candidate_action.matrix.mult(source, candidate_output)
        candidate_seconds = time.perf_counter() - candidate_start
        candidate_action.matrix.mult(source, candidate_repeat)
        candidate_repeat_equal = np.array_equal(
            candidate_output.getArray(readonly=True),
            candidate_repeat.getArray(readonly=True),
        )
        difference.set(0.0)
        candidate_output.copy(result=difference)
        difference.axpy(-1.0, reference_output)
        relative_error = difference.norm() / max(reference_output.norm(), 1.0e-30)
        local_finite = bool(
            np.all(np.isfinite(reference_output.getArray(readonly=True)))
            and np.all(np.isfinite(candidate_output.getArray(readonly=True)))
        )
        finite = bool(
            function_space.mesh.comm.allreduce(local_finite, op=MPI.LAND)
        )
        deterministic = bool(
            function_space.mesh.comm.allreduce(candidate_repeat_equal, op=MPI.LAND)
        )

        source_definition = _source_definition(label, cfg)
        source_dir = run_dir / "canonical" / label
        source_dir.mkdir(parents=True, exist_ok=True)
        rank = function_space.mesh.comm.rank
        candidate_shard = source_dir / f"candidate_rank{rank}.jsonl"
        candidate_metadata = write_canonical_packet_shard(
            candidate_shard,
            iter_canonical_full_fe_dual_packets(
                function_space,
                mpc,
                candidate_output,
                geometry_tolerance=tolerance,
            ),
        )
        shard_metadata = function_space.mesh.comm.gather(candidate_metadata, root=0)
        candidate_manifest_data = None
        if rank == 0:
            candidate_manifest_path = source_dir / "candidate_manifest.json"
            candidate_manifest = canonical_shard_manifest(
                role="full_fe_dual",
                mpi_size=function_space.mesh.comm.size,
                shard_metadata=shard_metadata,
                extractor_audit={"source": label, "method": "Candidate-H"},
            )
            candidate_sha = write_canonical_manifest(
                candidate_manifest_path, candidate_manifest
            )
            candidate_manifest_data = {
                "path": str(candidate_manifest_path.relative_to(run_dir)),
                "sha256": candidate_sha,
                "packet_count": int(candidate_manifest["global_summed_packet_count"]),
            }
        candidate_manifest_data = function_space.mesh.comm.bcast(
            candidate_manifest_data, root=0
        )
        return {
            "label": label,
            "kind": "physical_coordinate_analytic_primal",
            "iteration": None,
            "source_definition": source_definition,
            "source_definition_sha256": source_definition["definition_sha256"],
            "reference_apply_seconds": float(reference_seconds),
            "candidate_apply_seconds": float(candidate_seconds),
            "candidate_repeat_apply_count": 2,
            "candidate_repeat_equal": deterministic,
            "deterministic": deterministic,
            "finite": finite,
            "reference_vs_candidate_relative_error": float(relative_error),
            "candidate_canonical_packet_count": int(
                candidate_manifest_data["packet_count"]
            ),
            "candidate_manifest": candidate_manifest_data,
        }
    finally:
        difference.destroy()
        candidate_repeat.destroy()
        candidate_output.destroy()
        reference_output.destroy()


def _evaluate_worker_qualification(
    measurements: list[dict[str, Any]],
    candidate_audit: dict[str, Any],
    *,
    global_rows: int,
    constraint_count: int,
) -> dict[str, Any]:
    """Recompute the fixed H1.2 worker qualification from compact raw fields."""

    expected_labels = tuple(SOURCE_DEFINITIONS)
    measured_labels = tuple(item.get("label") for item in measurements)
    source_keys_fixed = measured_labels == expected_labels
    by_label = {item.get("label"): item for item in measurements}
    expected_packet_count = int(global_rows) - int(constraint_count)
    action_checks: dict[str, bool] = {}
    packet_checks: dict[str, bool] = {}
    source_checks: dict[str, bool] = {}
    for label in expected_labels:
        measurement = by_label.get(label)
        relative_error = (
            float("inf")
            if measurement is None
            else float(
                measurement.get(
                    "reference_vs_candidate_relative_error", float("inf")
                )
            )
        )
        action_checks[label] = bool(
            measurement is not None
            and math.isfinite(relative_error)
            and 0.0 <= relative_error <= DUAL_RELATIVE_TOLERANCE
            and measurement.get("finite") is True
            and measurement.get("deterministic") is True
        )
        packet_checks[label] = bool(
            measurement is not None
            and measurement.get("candidate_canonical_packet_count")
            == expected_packet_count
        )
        source_checks[label] = action_checks[label] and packet_checks[label]

    inventory_checks = {
        "global_matrix_materialized": candidate_audit.get(
            "global_matrix_materialized"
        ) is False,
        "global_A_materialized": candidate_audit.get("global_A_materialized") is False,
        "global_condensed_schur_materialized": candidate_audit.get(
            "global_condensed_schur_materialized"
        ) is False,
        "p6_cell_dof_count": candidate_audit.get("cell_dof_count") == 882,
        "retained_cell_dense_882x882_count": candidate_audit.get(
            "retained_cell_dense_882x882_count"
        ) == 0,
        "cell_tensor_scratch_count": candidate_audit.get("cell_tensor_scratch_count")
        == 1,
        "cell_schur_matrix_nnz": candidate_audit.get("cell_schur_matrix_nnz") == 0,
        "slab_matrix_nnz": candidate_audit.get("slab_matrix_nnz") == 0,
        "slab_factor_count": candidate_audit.get("slab_factor_count") == 0,
        "dtn_probe": candidate_audit.get("dtn_probe") is False,
        "explicit_C_nnz": candidate_audit.get("explicit_C_nnz") == 0,
        "explicit_D_nnz": candidate_audit.get("explicit_D_nnz") == 0,
        "ksp_create_count": candidate_audit.get("ksp_create_count") == 0,
        "ksp_solve_count": candidate_audit.get("ksp_solve_count") == 0,
        "official_field": candidate_audit.get("official_field") is False,
        "official_RTA": candidate_audit.get("official_RTA") is False,
        "ordinary_default_changed": candidate_audit.get("ordinary_default_changed")
        is False,
    }
    payload_sum = candidate_audit.get(
        "candidate_owned_numeric_payload_global_sum_bytes"
    )
    payload_gate = isinstance(payload_sum, int) and payload_sum <= int(0.50 * GIB)
    action_gate = all(action_checks.values()) if source_keys_fixed else False
    packet_gate = all(packet_checks.values()) if source_keys_fixed else False
    inventory_gate = all(inventory_checks.values())
    return {
        "pass": bool(action_gate and packet_gate and inventory_gate and payload_gate),
        "source_keys_fixed": source_keys_fixed,
        "action_checks": action_checks,
        "action_gate_pass": action_gate,
        "canonical_packet_count_checks": packet_checks,
        "canonical_packet_count_gate_pass": packet_gate,
        "source_checks": source_checks,
        "expected_canonical_packet_count": expected_packet_count,
        "inventory_checks": inventory_checks,
        "inventory_gate_pass": inventory_gate,
        "payload_gate_pass": payload_gate,
        "candidate_owned_numeric_payload_global_sum_bytes": payload_sum,
        "candidate_owned_numeric_payload_global_max_bytes": candidate_audit.get(
            "candidate_owned_numeric_payload_global_max_bytes"
        ),
        "retained_payload_limit_bytes": int(0.50 * GIB),
    }


def run_worker(
    run_dir: Path,
) -> bool:
    from dolfinx import fem
    from mpi4py import MPI

    from src.common.config_3d import target_stage4_config
    from src.constraints.floquet_3d import build_double_floquet_mpc
    from src.constraints.floquet_3d_high_order import floquet_geometry_tolerance
    from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
    from src.solvers.common_3d_forms import _build_variational_forms
    from src.solvers.common_3d_solve import _create_nedelec_space
    from src.solvers.fullspace_matrix_free_hcurl import (
        build_task037_extra_candidate_h_fullspace_action,
    )
    from src.solvers.mpc_form_action import MpcFormActionContext

    comm = MPI.COMM_WORLD
    cfg = target_stage4_config(degree=6, h_nm=10.0)
    if cfg.stage4_boundary_model != "dtn_port":
        raise RuntimeError("Candidate-H requires the frozen dtn_port configuration identity")
    if cfg.divergence_penalty != 0.0:
        raise RuntimeError("Candidate-H H1.2 excludes divergence penalty")
    if comm.rank == 0:
        run_dir.mkdir(parents=True, exist_ok=True)
    comm.barrier()
    mesh_data = build_airbox_mesh_3d(cfg, run_dir / "mesh")
    function_space = _create_nedelec_space(mesh_data.mesh, cfg)
    floquet = build_double_floquet_mpc(function_space, mesh_data, cfg)
    a_ufl, _ = _build_variational_forms(
        mesh_data.mesh,
        mesh_data,
        cfg,
        function_space,
        field_formulation="total_field_dtn_port",
        incident_field=None,
    )
    a_compiled = fem.form(a_ufl)
    tolerance = floquet_geometry_tolerance(cfg)
    candidate = build_task037_extra_candidate_h_fullspace_action(
        a_compiled,
        function_space,
        mesh_data.cell_tags,
        mpc=floquet.mpc,
        task037_extra_candidate_h=True,
        geometry_tolerance=tolerance,
    )
    reference = MpcFormActionContext(a_ufl, floquet.mpc)
    try:
        source_results = []
        for label in SOURCE_DEFINITIONS:
            source = _make_primal_source(function_space, floquet.mpc, cfg, label)
            try:
                source_results.append(
                    _action_record(
                        reference,
                        candidate,
                        source,
                        run_dir=run_dir,
                        label=label,
                        cfg=cfg,
                        function_space=function_space,
                        mpc=floquet.mpc,
                        tolerance=tolerance,
                    )
                )
            finally:
                source.destroy()
        comm.barrier()
        candidate_audit = dict(candidate.audit)
        candidate_audit["candidate_owned_numeric_payload_components"] = dict(
            candidate.audit["candidate_owned_numeric_payload_components"]
        )
        global_rows = int(candidate.audit["global_rows"])
        constraint_count = int(floquet.num_constraints)
        if comm.rank == 0:
            qualification = _evaluate_worker_qualification(
                source_results,
                candidate_audit,
                global_rows=global_rows,
                constraint_count=constraint_count,
            )
            summary = {
                "schema": "task037.candidate_h.h1_2.worker.v1",
                "status": "pass" if qualification["pass"] else "gate_failed",
                "mpi_size": int(comm.size),
                "global_rows": global_rows,
                "constraint_count": constraint_count,
                "scope": {
                    "degree": 6,
                    "h_nm": 10.0,
                    "mpi_size": int(comm.size),
                    "global_rows": global_rows,
                    "constraint_count": constraint_count,
                    "field_formulation": "total_field_dtn_port",
                    "operator": "A_h=curl-curl-k0^2*epsilon*mass",
                    "dtn_surface_term": False,
                    "condensation": False,
                    "ksp": False,
                    "ordinary_default_changed": False,
                },
                "source_definitions": {
                    label: _source_definition(label, cfg)
                    for label in SOURCE_DEFINITIONS
                },
                "measurements": source_results,
                "candidate_action_audit": candidate_audit,
                "reference_action": {
                    "type": "MpcFormActionContext",
                    "same_worker": True,
                    "apply_count": int(reference.apply_count),
                    "global_matrix_materialized": False,
                },
                "candidate_owned_payload": candidate_audit[
                    "candidate_owned_numeric_payload_components"
                ],
                "qualification": qualification,
            }
            (run_dir / "run_summary.json").write_text(
                json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2)
                + "\n",
                encoding="utf-8",
            )
            worker_pass = bool(qualification["pass"])
        else:
            worker_pass = None
        return bool(comm.bcast(worker_pass, root=0))
    finally:
        reference.destroy()
        candidate.destroy()


def _watchdog_command(args) -> list[str]:
    return [
        "mpiexec",
        "-n",
        str(args.mpi_size),
        sys.executable,
        "-m",
        "benchmarks.run_task037_extra_candidate_h",
        "worker",
        "--run-dir",
        str(args.run_dir),
    ]


def _live_sample_swap(sample: dict[str, Any]) -> int | None:
    value = sample.get("process_tree_swap_bytes")
    if value is None:
        value = sample.get("swap_current_bytes")
    return value if isinstance(value, int) and value >= 0 else None


def _live_sample_is_readable(sample: dict[str, Any]) -> bool:
    if sample.get("worker_tree_rss_sum_bytes") is None:
        return False
    if _live_sample_swap(sample) is None:
        return False
    if (
        "process_tree_all_status_readable" in sample
        and sample.get("process_tree_all_status_readable") is not True
    ):
        return False
    return True


def run_watchdog(args) -> int:
    run_dir = Path(args.run_dir).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = run_dir / "worker_stdout.txt"
    timeline_path = run_dir / "watchdog_timeline.jsonl"
    command = _watchdog_command(args)
    source_at_start = _inspect_candidate_source()
    started = time.perf_counter()
    controlled_stop = None
    samples: list[dict[str, Any]] = []
    live_samples: list[dict[str, Any]] = []
    termination = {"requested": False, "method": None}
    process: subprocess.Popen[Any] | None = None
    with (
        stdout_path.open("w", encoding="utf-8") as stdout,
        timeline_path.open("w", encoding="utf-8") as timeline,
    ):
        if source_at_start.tracked_source_dirty or source_at_start.source_commit_full_sha is None:
            controlled_stop = "source_not_clean_or_unreadable"
        else:
            try:
                process = subprocess.Popen(
                    command,
                    stdout=stdout,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                    text=True,
                )
            except OSError as exc:
                controlled_stop = f"worker_launch_failed:{type(exc).__name__}"
                stdout.write(f"{type(exc).__name__}: {exc}\n")
        while process is not None:
            return_code = process.poll()
            sample = sample_memory(process.pid, worker_alive=return_code is None)
            samples.append(sample)
            timeline.write(json.dumps(sample, sort_keys=True) + "\n")
            timeline.flush()
            if return_code is not None:
                break
            live_samples.append(sample)
            if not _live_sample_is_readable(sample):
                controlled_stop = "resource_authority_unreadable"
            else:
                process_tree_rss = int(sample["worker_tree_rss_sum_bytes"])
                swap = _live_sample_swap(sample)
                if process_tree_rss > H1_RSS_LIMIT_BYTES:
                    controlled_stop = "process_tree_rss_over_1.25_GiB"
                elif swap != 0:
                    controlled_stop = "worker_process_tree_swap_nonzero"
                elif time.perf_counter() - started > H1_TIMEOUT_SECONDS:
                    controlled_stop = "timeout"
            if controlled_stop is not None:
                termination = terminate_process_tree(process)
                break
            time.sleep(H1_POLL_SECONDS)
        return_code = None if process is None else process.wait()
        final_sample = sample_memory(
            process.pid if process is not None else -1,
            worker_alive=False,
        )
        timeline.write(json.dumps(final_sample, sort_keys=True) + "\n")
        timeline.flush()
    source_at_end = _inspect_candidate_source()
    summary_path = run_dir / "run_summary.json"
    worker_summary = (
        json.loads(summary_path.read_text(encoding="utf-8"))
        if summary_path.exists()
        else None
    )
    source_stable_clean = bool(
        source_at_start.source_commit_full_sha is not None
        and source_at_start.source_commit_full_sha
        == source_at_end.source_commit_full_sha
        and not source_at_start.tracked_source_dirty
        and not source_at_end.tracked_source_dirty
    )
    worker_qualification_pass = bool(
        worker_summary is not None
        and worker_summary.get("qualification", {}).get("pass") is True
    )
    live_swap_values = tuple(
        _live_sample_swap(sample) for sample in live_samples
    )
    live_authority_readable = bool(
        live_samples
        and all(_live_sample_is_readable(sample) for sample in live_samples)
    )
    peak_process_tree_rss = int(
        max(
            (int(sample["worker_tree_rss_sum_bytes"]) for sample in live_samples),
            default=0,
        )
    )
    worker_swap_zero = bool(
        live_authority_readable
        and all(value == 0 for value in live_swap_values)
    )
    watchdog_pass = bool(
        controlled_stop is None
        and return_code == 0
        and worker_summary is not None
        and worker_qualification_pass
        and source_stable_clean
        and live_authority_readable
        and worker_swap_zero
        and peak_process_tree_rss <= H1_RSS_LIMIT_BYTES
    )
    watchdog_summary = {
        "schema": "task037.candidate_h.h1_2.watchdog.v1",
        "command": command,
        "mpi_size": int(args.mpi_size),
        "return_code": None if return_code is None else int(return_code),
        "status": "pass" if watchdog_pass else (
            "controlled_stop" if controlled_stop is not None else "worker_failed"
        ),
        "controlled_stop": controlled_stop,
        "timeout_seconds": H1_TIMEOUT_SECONDS,
        "poll_interval_seconds": H1_POLL_SECONDS,
        "rss_limit_bytes": H1_RSS_LIMIT_BYTES,
        "termination": termination,
        "wall_seconds": float(time.perf_counter() - started),
        "peak_process_tree_rss_bytes": peak_process_tree_rss,
        "peak_includes_only_worker_alive_samples": True,
        "worker_live_sample_count": len(live_samples),
        "worker_process_tree_swap_bytes": (
            None if not live_swap_values else max(live_swap_values)
        ),
        "worker_swap_zero": worker_swap_zero,
        "resource_authority_readable": live_authority_readable,
        "final_sample": final_sample,
        "worker_summary_present": worker_summary is not None,
        "worker_summary_status": None
        if worker_summary is None
        else worker_summary.get("status"),
        "worker_qualification_pass": worker_qualification_pass,
        "source_at_start": source_at_start.as_jsonable(),
        "source_at_end": source_at_end.as_jsonable(),
        "source_stable_clean": source_stable_clean,
        "reference_and_candidate_same_worker": True,
    }
    (run_dir / "watchdog_summary.json").write_text(
        json.dumps(watchdog_summary, ensure_ascii=False, sort_keys=True, indent=2)
        + "\n",
        encoding="utf-8",
    )
    return 0 if watchdog_pass else 1


def _read_compare_run_identity(
    run_dir: Path, expected_mpi_size: int
) -> dict[str, Any]:
    run_dir = Path(run_dir)
    watchdog = json.loads(
        (run_dir / "watchdog_summary.json").read_text(encoding="utf-8")
    )
    summary = json.loads(
        (run_dir / "run_summary.json").read_text(encoding="utf-8")
    )
    source_start = watchdog.get("source_at_start", {})
    source_end = watchdog.get("source_at_end", {})
    source_sha = source_start.get("source_commit_full_sha")
    source_sha_valid = bool(
        isinstance(source_sha, str)
        and len(source_sha) == 40
        and all(character in "0123456789abcdef" for character in source_sha)
    )
    source_stable = bool(
        source_sha_valid
        and source_sha == source_end.get("source_commit_full_sha")
        and source_start.get("tracked_source_dirty") is False
        and source_end.get("tracked_source_dirty") is False
    )
    scope = summary.get("scope", {})
    measurements = summary.get("measurements", [])
    measured_labels = tuple(item.get("label") for item in measurements)
    source_keys_fixed = measured_labels == tuple(SOURCE_DEFINITIONS)
    manifest_records: dict[str, dict[str, str]] = {}
    manifest_checks: dict[str, bool] = {}
    if source_keys_fixed:
        for label, measurement in zip(SOURCE_DEFINITIONS, measurements):
            record = measurement["candidate_manifest"]
            expected_relative_path = f"canonical/{label}/candidate_manifest.json"
            relative_path = str(record["path"])
            manifest_path = run_dir / relative_path
            manifest = read_canonical_manifest(
                manifest_path,
                expected_sha256=str(record["sha256"]),
            )
            extractor = manifest.get("extractor_audit", {})
            manifest_records[label] = {
                "path": relative_path,
                "sha256": str(record["sha256"]),
            }
            manifest_checks[label] = bool(
                relative_path == expected_relative_path
                and manifest.get("role") == "full_fe_dual"
                and manifest.get("mpi_size") == int(expected_mpi_size)
                and extractor.get("source") == label
                and extractor.get("method") == "Candidate-H"
                and manifest.get("summed_local_duplicate_count") == 0
            )
    checks = {
        "watchdog_status_pass": watchdog.get("status") == "pass",
        "watchdog_mpi_size": watchdog.get("mpi_size") == int(expected_mpi_size),
        "worker_qualification_pass": watchdog.get("worker_qualification_pass") is True,
        "source_stable_clean": watchdog.get("source_stable_clean") is True,
        "source_sha_valid_and_stable": source_stable,
        "run_summary_qualification_pass": summary.get("qualification", {}).get(
            "pass"
        ) is True,
        "scope_mpi_size": scope.get("mpi_size") == int(expected_mpi_size),
        "scope_dimensions_present": isinstance(scope.get("global_rows"), int)
        and isinstance(scope.get("constraint_count"), int),
        "source_keys_fixed": source_keys_fixed,
        "manifest_checks": all(manifest_checks.values()) if source_keys_fixed else False,
    }
    return {
        "expected_mpi_size": int(expected_mpi_size),
        "source_sha": source_sha if source_sha_valid else None,
        "checks": checks,
        "manifest_records": manifest_records,
        "manifest_checks": manifest_checks,
        "pass": all(checks.values()),
    }


def compare_run_directories(mpi1_run_dir: Path, mpi2_run_dir: Path) -> dict[str, Any]:
    mpi1_identity = _read_compare_run_identity(mpi1_run_dir, 1)
    mpi2_identity = _read_compare_run_identity(mpi2_run_dir, 2)
    source_sha_match = bool(
        mpi1_identity["source_sha"] is not None
        and mpi1_identity["source_sha"] == mpi2_identity["source_sha"]
    )
    comparisons = {}
    for label in SOURCE_DEFINITIONS:
        mpi1_record = mpi1_identity["manifest_records"].get(label)
        mpi2_record = mpi2_identity["manifest_records"].get(label)
        if mpi1_record is None or mpi2_record is None:
            comparisons[label] = {
                "pass": False,
                "missing_key_count": 0,
                "extra_key_count": 0,
                "duplicate_left_count": 0,
                "duplicate_right_count": 0,
                "relative_coefficient_l2": None,
                "manifest_records_present": False,
            }
            continue
        comparisons[label] = {
            "manifest_records_present": True,
            "mpi1_manifest_sha256": mpi1_record["sha256"],
            "mpi2_manifest_sha256": mpi2_record["sha256"],
            **compare_canonical_manifests(
                Path(mpi1_run_dir) / mpi1_record["path"],
                Path(mpi2_run_dir) / mpi2_record["path"],
                left_sha256=mpi1_record["sha256"],
                right_sha256=mpi2_record["sha256"],
                relative_tolerance=DUAL_RELATIVE_TOLERANCE,
            ),
        }
    run_identity_pass = bool(
        mpi1_identity["pass"] and mpi2_identity["pass"] and source_sha_match
    )
    return {
        "schema": "task037.candidate_h.h1_2.cross_mpi_compare.v1",
        "source_order": list(SOURCE_DEFINITIONS),
        "relative_tolerance": DUAL_RELATIVE_TOLERANCE,
        "run_identity_checks": {
            "mpi1": mpi1_identity["checks"],
            "mpi2": mpi2_identity["checks"],
            "common_source_sha": mpi1_identity["source_sha"]
            if source_sha_match
            else None,
            "source_sha_match": source_sha_match,
            "pass": run_identity_pass,
        },
        "comparisons": comparisons,
        "missing_key_count": sum(
            int(item["missing_key_count"]) for item in comparisons.values()
        ),
        "extra_key_count": sum(
            int(item["extra_key_count"]) for item in comparisons.values()
        ),
        "duplicate_left_count": sum(
            int(item["duplicate_left_count"]) for item in comparisons.values()
        ),
        "duplicate_right_count": sum(
            int(item["duplicate_right_count"]) for item in comparisons.values()
        ),
        "pass": bool(
            run_identity_pass and all(item["pass"] for item in comparisons.values())
        ),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    worker = subparsers.add_parser("worker")
    worker.add_argument("--run-dir", type=Path, required=True)
    watchdog = subparsers.add_parser("watchdog")
    watchdog.add_argument("--run-dir", type=Path, required=True)
    watchdog.add_argument("--mpi-size", type=int, choices=(1, 2), required=True)
    compare = subparsers.add_parser("compare")
    compare.add_argument("--mpi1-run-dir", type=Path, required=True)
    compare.add_argument("--mpi2-run-dir", type=Path, required=True)
    compare.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "worker":
        return 0 if run_worker(args.run_dir) else 1
    if args.command == "watchdog":
        return run_watchdog(args)
    result = compare_run_directories(args.mpi1_run_dir, args.mpi2_run_dir)
    payload = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output is None:
        print(payload, end="")
    else:
        args.output.write_text(payload, encoding="utf-8")
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
