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
from types import SimpleNamespace
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
from benchmarks.task033_case090_pde_core import (
    attach_evidence_sha256,
    evidence_sha256_is_valid,
)


GIB = 1024**3
H1_RSS_LIMIT_BYTES = int(1.25 * GIB)
H1_POLL_SECONDS = 0.25
H1_TIMEOUT_SECONDS = 1800.0
DUAL_RELATIVE_TOLERANCE = 1.0e-11
H1R_PROGRESS_SCHEMA = "task037_extra_h1r_progress.v1"
H1R2_SOURCE_LABEL = "seed_17037"
H1R2_TIMEOUT_SECONDS = 600.0
H1R2_REFERENCE_APPLY_COUNT = 1
H1R2_CANDIDATE_APPLY_COUNT = 2
H1R2_PAYLOAD_LIMIT_BYTES = int(0.50 * GIB)
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _h1r2_numerical_gate(
    relative_error: float,
    finite: bool,
    deterministic: bool,
) -> bool:
    return bool(
        finite is True
        and deterministic is True
        and math.isfinite(float(relative_error))
        and 0.0 <= float(relative_error) <= DUAL_RELATIVE_TOLERANCE
    )


def _h1r2_source_definition_hash(definition: dict[str, Any]) -> str:
    unsigned = dict(definition)
    unsigned.pop("definition_sha256", None)
    return hashlib.sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


def _h1r2_runtime_identity() -> dict[str, str | None]:
    return {
        "_MYFENICS_WSL_QUALIFIED_ACTIVATION": os.environ.get(
            "_MYFENICS_WSL_QUALIFIED_ACTIVATION"
        ),
        "sys.executable": sys.executable,
        "OMP_NUM_THREADS": os.environ.get("OMP_NUM_THREADS"),
        "OPENBLAS_NUM_THREADS": os.environ.get("OPENBLAS_NUM_THREADS"),
        "MKL_NUM_THREADS": os.environ.get("MKL_NUM_THREADS"),
        "NUMEXPR_NUM_THREADS": os.environ.get("NUMEXPR_NUM_THREADS"),
    }


def _h1r2_runtime_identity_is_valid(
    identity: object,
) -> bool:
    return bool(
        isinstance(identity, dict)
        and isinstance(identity.get("sys.executable"), str)
        and identity.get("sys.executable")
        and identity.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION") == "1"
        and identity.get("OMP_NUM_THREADS") == "1"
        and identity.get("OPENBLAS_NUM_THREADS") == "1"
        and identity.get("MKL_NUM_THREADS") == "1"
        and identity.get("NUMEXPR_NUM_THREADS") == "1"
    )


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


def _proc_memory_field(path: Path, field: str) -> int | None:
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith(field):
                fields = line.split()
                return int(fields[1]) * 1024
    except (OSError, IndexError, ValueError):
        return None
    return None


def _self_memory_bytes() -> tuple[int | None, int | None, int | None]:
    rss = _proc_memory_field(Path("/proc/self/status"), "VmRSS:")
    smaps_rollup = Path("/proc/self/smaps_rollup")
    pss = _proc_memory_field(smaps_rollup, "Pss:")
    private_clean = _proc_memory_field(smaps_rollup, "Private_Clean:")
    private_dirty = _proc_memory_field(smaps_rollup, "Private_Dirty:")
    uss = (
        None
        if private_clean is None or private_dirty is None
        else int(private_clean + private_dirty)
    )
    return rss, pss, uss


def _emit_h1r_progress(
    writer: Any,
    *,
    event: str,
    worker_started: float,
    rank: int,
    source_label: str | None = None,
    apply_count: int | None = None,
    cell_count: int | None = None,
    local_rows: int | None = None,
    global_rows: int | None = None,
) -> None:
    rss_bytes, pss_bytes, uss_bytes = _self_memory_bytes()
    record = {
        "schema": H1R_PROGRESS_SCHEMA,
        "event": str(event),
        "elapsed_wall_seconds": float(time.perf_counter() - worker_started),
        "rank": int(rank),
        "rss_bytes": rss_bytes,
        "pss_bytes": pss_bytes,
        "uss_bytes": uss_bytes,
        "source_label": source_label,
        "apply_count": apply_count,
        "cell_count": cell_count,
        "local_rows": local_rows,
        "global_rows": global_rows,
    }
    writer.write(json.dumps(record, sort_keys=True) + "\n")
    writer.flush()


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
    progress_writer: Any | None = None,
    progress_started: float | None = None,
    progress_rank: int | None = None,
    progress_cell_count: int | None = None,
    progress_local_rows: int | None = None,
    progress_global_rows: int | None = None,
) -> dict[str, Any]:
    import numpy as np
    from mpi4py import MPI

    reference_output = source.duplicate()
    candidate_output = source.duplicate()
    candidate_repeat = source.duplicate()
    difference = source.duplicate()
    try:
        if progress_writer is not None:
            _emit_h1r_progress(
                progress_writer,
                event="reference_apply_started",
                worker_started=float(progress_started),
                rank=int(progress_rank),
                source_label=label,
                apply_count=getattr(reference_context, "apply_count", None),
                cell_count=progress_cell_count,
                local_rows=progress_local_rows,
                global_rows=progress_global_rows,
            )
        reference_start = time.perf_counter()
        reference_context.mult(None, source, reference_output)
        reference_seconds = time.perf_counter() - reference_start
        if progress_writer is not None:
            _emit_h1r_progress(
                progress_writer,
                event="reference_apply_ready",
                worker_started=float(progress_started),
                rank=int(progress_rank),
                source_label=label,
                apply_count=getattr(reference_context, "apply_count", None),
                cell_count=progress_cell_count,
                local_rows=progress_local_rows,
                global_rows=progress_global_rows,
            )
            _emit_h1r_progress(
                progress_writer,
                event="candidate_apply_1_started",
                worker_started=float(progress_started),
                rank=int(progress_rank),
                source_label=label,
                apply_count=1,
                cell_count=progress_cell_count,
                local_rows=progress_local_rows,
                global_rows=progress_global_rows,
            )
        candidate_start = time.perf_counter()
        candidate_action.matrix.mult(source, candidate_output)
        candidate_seconds = time.perf_counter() - candidate_start
        if progress_writer is not None:
            _emit_h1r_progress(
                progress_writer,
                event="candidate_apply_1_ready",
                worker_started=float(progress_started),
                rank=int(progress_rank),
                source_label=label,
                apply_count=1,
                cell_count=progress_cell_count,
                local_rows=progress_local_rows,
                global_rows=progress_global_rows,
            )
            _emit_h1r_progress(
                progress_writer,
                event="candidate_apply_2_started",
                worker_started=float(progress_started),
                rank=int(progress_rank),
                source_label=label,
                apply_count=2,
                cell_count=progress_cell_count,
                local_rows=progress_local_rows,
                global_rows=progress_global_rows,
            )
        candidate_action.matrix.mult(source, candidate_repeat)
        if progress_writer is not None:
            _emit_h1r_progress(
                progress_writer,
                event="candidate_apply_2_ready",
                worker_started=float(progress_started),
                rank=int(progress_rank),
                source_label=label,
                apply_count=2,
                cell_count=progress_cell_count,
                local_rows=progress_local_rows,
                global_rows=progress_global_rows,
            )
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
        rank = function_space.mesh.comm.rank
        candidate_shard = source_dir / f"candidate_rank{rank}.jsonl"
        if progress_writer is not None:
            _emit_h1r_progress(
                progress_writer,
                event="canonical_export_started",
                worker_started=float(progress_started),
                rank=int(progress_rank),
                source_label=label,
                apply_count=2,
                cell_count=progress_cell_count,
                local_rows=progress_local_rows,
                global_rows=progress_global_rows,
            )
        source_dir.mkdir(parents=True, exist_ok=True)
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
        if progress_writer is not None:
            _emit_h1r_progress(
                progress_writer,
                event="canonical_export_ready",
                worker_started=float(progress_started),
                rank=int(progress_rank),
                source_label=label,
                apply_count=2,
                cell_count=progress_cell_count,
                local_rows=progress_local_rows,
                global_rows=progress_global_rows,
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


def _h1r2_action_record(
    reference_context,
    candidate_action,
    source,
    *,
    run_dir: Path,
    cfg,
    function_space,
    mpc,
    tolerance: float,
    progress_writer: Any | None = None,
    progress_started: float | None = None,
    progress_rank: int | None = None,
    progress_cell_count: int | None = None,
    progress_local_rows: int | None = None,
    progress_global_rows: int | None = None,
) -> dict[str, Any]:
    """Measure one fixed H1R.2 source and export only after numeric gates."""

    import numpy as np
    from mpi4py import MPI
    from src.solvers.hcurl_canonical_vector_dolfinx import (
        iter_canonical_full_fe_dual_packets,
    )

    label = H1R2_SOURCE_LABEL
    source_definition = _source_definition(label, cfg)
    reference_output = source.duplicate()
    candidate_output = source.duplicate()
    candidate_repeat = source.duplicate()
    difference = source.duplicate()
    try:
        if progress_writer is not None:
            _emit_h1r_progress(
                progress_writer,
                event="reference_apply_started",
                worker_started=float(progress_started),
                rank=int(progress_rank),
                source_label=label,
                apply_count=H1R2_REFERENCE_APPLY_COUNT,
                cell_count=progress_cell_count,
                local_rows=progress_local_rows,
                global_rows=progress_global_rows,
            )
        reference_started = time.perf_counter()
        reference_context.mult(None, source, reference_output)
        reference_seconds = time.perf_counter() - reference_started
        if progress_writer is not None:
            _emit_h1r_progress(
                progress_writer,
                event="reference_apply_ready",
                worker_started=float(progress_started),
                rank=int(progress_rank),
                source_label=label,
                apply_count=H1R2_REFERENCE_APPLY_COUNT,
                cell_count=progress_cell_count,
                local_rows=progress_local_rows,
                global_rows=progress_global_rows,
            )
            _emit_h1r_progress(
                progress_writer,
                event="candidate_apply_1_started",
                worker_started=float(progress_started),
                rank=int(progress_rank),
                source_label=label,
                apply_count=1,
                cell_count=progress_cell_count,
                local_rows=progress_local_rows,
                global_rows=progress_global_rows,
            )
        candidate_started = time.perf_counter()
        candidate_action.mult(source)
        candidate_seconds = time.perf_counter() - candidate_started
        candidate_action.output_vector.copy(result=candidate_output)
        if progress_writer is not None:
            _emit_h1r_progress(
                progress_writer,
                event="candidate_apply_1_ready",
                worker_started=float(progress_started),
                rank=int(progress_rank),
                source_label=label,
                apply_count=1,
                cell_count=progress_cell_count,
                local_rows=progress_local_rows,
                global_rows=progress_global_rows,
            )
            _emit_h1r_progress(
                progress_writer,
                event="candidate_apply_2_started",
                worker_started=float(progress_started),
                rank=int(progress_rank),
                source_label=label,
                apply_count=H1R2_CANDIDATE_APPLY_COUNT,
                cell_count=progress_cell_count,
                local_rows=progress_local_rows,
                global_rows=progress_global_rows,
            )
        candidate_repeat_started = time.perf_counter()
        candidate_action.mult(source)
        candidate_repeat_seconds = time.perf_counter() - candidate_repeat_started
        candidate_action.output_vector.copy(result=candidate_repeat)
        if progress_writer is not None:
            _emit_h1r_progress(
                progress_writer,
                event="candidate_apply_2_ready",
                worker_started=float(progress_started),
                rank=int(progress_rank),
                source_label=label,
                apply_count=H1R2_CANDIDATE_APPLY_COUNT,
                cell_count=progress_cell_count,
                local_rows=progress_local_rows,
                global_rows=progress_global_rows,
            )

        candidate_repeat_equal = np.array_equal(
            candidate_output.getArray(readonly=True),
            candidate_repeat.getArray(readonly=True),
        )
        candidate_output.copy(result=difference)
        difference.axpy(-1.0, reference_output)
        reference_norm = reference_output.norm()
        relative_error = difference.norm() / max(reference_norm, 1.0e-30)
        local_finite = bool(
            np.all(np.isfinite(reference_output.getArray(readonly=True)))
            and np.all(np.isfinite(candidate_output.getArray(readonly=True)))
            and np.all(np.isfinite(candidate_repeat.getArray(readonly=True)))
            and math.isfinite(float(relative_error))
        )
        comm = function_space.mesh.comm
        finite = bool(comm.allreduce(local_finite, op=MPI.LAND))
        deterministic = bool(comm.allreduce(candidate_repeat_equal, op=MPI.LAND))
        numeric_gate = _h1r2_numerical_gate(
            float(relative_error), finite, deterministic
        )

        candidate_manifest_data = None
        if numeric_gate:
            rank = comm.rank
            source_dir = run_dir / "canonical" / label
            candidate_shard = source_dir / f"candidate_rank{rank}.jsonl"
            if progress_writer is not None:
                _emit_h1r_progress(
                    progress_writer,
                    event="canonical_export_started",
                    worker_started=float(progress_started),
                    rank=int(progress_rank),
                    source_label=label,
                    apply_count=H1R2_CANDIDATE_APPLY_COUNT,
                    cell_count=progress_cell_count,
                    local_rows=progress_local_rows,
                    global_rows=progress_global_rows,
                )
            source_dir.mkdir(parents=True, exist_ok=True)
            candidate_metadata = write_canonical_packet_shard(
                candidate_shard,
                iter_canonical_full_fe_dual_packets(
                    function_space,
                    mpc,
                    candidate_output,
                    geometry_tolerance=tolerance,
                ),
            )
            shard_metadata = comm.gather(candidate_metadata, root=0)
            if rank == 0:
                candidate_manifest_path = source_dir / "candidate_manifest.json"
                candidate_manifest = canonical_shard_manifest(
                    role="full_fe_dual",
                    mpi_size=comm.size,
                    shard_metadata=shard_metadata,
                    extractor_audit={
                        "source": label,
                        "method": "H1R2-direct-rank-one-MPC",
                    },
                )
                candidate_sha = write_canonical_manifest(
                    candidate_manifest_path, candidate_manifest
                )
                candidate_manifest_data = {
                    "path": str(candidate_manifest_path.relative_to(run_dir)),
                    "sha256": candidate_sha,
                    "packet_count": int(
                        candidate_manifest["global_summed_packet_count"]
                    ),
                }
            candidate_manifest_data = comm.bcast(candidate_manifest_data, root=0)
            if progress_writer is not None:
                _emit_h1r_progress(
                    progress_writer,
                    event="canonical_export_ready",
                    worker_started=float(progress_started),
                    rank=int(progress_rank),
                    source_label=label,
                    apply_count=H1R2_CANDIDATE_APPLY_COUNT,
                    cell_count=progress_cell_count,
                    local_rows=progress_local_rows,
                    global_rows=progress_global_rows,
                )

        return {
            "label": label,
            "kind": "physical_coordinate_analytic_primal",
            "iteration": None,
            "source_definition": source_definition,
            "source_definition_sha256": source_definition["definition_sha256"],
            "reference_apply_count": H1R2_REFERENCE_APPLY_COUNT,
            "candidate_apply_count": H1R2_CANDIDATE_APPLY_COUNT,
            "reference_apply_seconds": float(reference_seconds),
            "candidate_apply_seconds": float(candidate_seconds),
            "candidate_repeat_apply_seconds": float(candidate_repeat_seconds),
            "candidate_repeat_apply_count": H1R2_CANDIDATE_APPLY_COUNT,
            "candidate_repeat_equal": bool(candidate_repeat_equal),
            "finite": finite,
            "deterministic": deterministic,
            "reference_vs_candidate_relative_error": float(relative_error),
            "canonical_export": bool(numeric_gate),
            "candidate_canonical_packet_count": (
                None
                if candidate_manifest_data is None
                else int(candidate_manifest_data["packet_count"])
            ),
            "candidate_manifest": candidate_manifest_data,
        }
    finally:
        difference.destroy()
        candidate_repeat.destroy()
        candidate_output.destroy()
        reference_output.destroy()


def _evaluate_h1r2_worker_qualification(
    measurements: list[dict[str, Any]],
    candidate_audit: dict[str, Any],
    *,
    scope: dict[str, Any],
) -> dict[str, Any]:
    """Recompute the fixed H1R.2 worker contract from raw summary fields."""

    expected_packet_count = int(scope.get("global_rows", -1)) - int(
        scope.get("constraint_count", -1)
    )
    source_keys_fixed = tuple(item.get("label") for item in measurements) == (
        H1R2_SOURCE_LABEL,
    )
    measurement = measurements[0] if source_keys_fixed else None
    source_definition = {} if measurement is None else measurement.get(
        "source_definition", {}
    )
    source_checks = {
        "source_label": measurement is not None
        and measurement.get("label") == H1R2_SOURCE_LABEL,
        "source_definition_label": source_definition.get("label")
        == H1R2_SOURCE_LABEL,
        "source_seed": source_definition.get("seed") == 17037,
        "source_definition_sha256": measurement is not None
        and measurement.get("source_definition_sha256")
        == source_definition.get("definition_sha256")
        == _h1r2_source_definition_hash(source_definition),
        "source_frequency": tuple(source_definition.get("frequency", ()))
        == (1, 1, 0),
        "source_envelope": json.dumps(
            source_definition.get("envelope_coefficients"), sort_keys=True
        )
        == json.dumps(
            SOURCE_DEFINITIONS[H1R2_SOURCE_LABEL]["envelope_coefficients"],
            sort_keys=True,
        ),
        "source_formula": source_definition.get("formula")
        == SOURCE_DEFINITIONS[H1R2_SOURCE_LABEL]["formula"],
    }
    timing_values = {
        "reference_apply_seconds": float(
            measurement.get("reference_apply_seconds", float("nan"))
        )
        if measurement is not None
        else float("nan"),
        "candidate_apply_seconds": float(
            measurement.get("candidate_apply_seconds", float("nan"))
        )
        if measurement is not None
        else float("nan"),
        "candidate_repeat_apply_seconds": float(
            measurement.get("candidate_repeat_apply_seconds", float("nan"))
        )
        if measurement is not None
        else float("nan"),
    }
    timing_checks = {
        name: math.isfinite(value) and value > 0.0
        for name, value in timing_values.items()
    }
    error = float(
        measurement.get("reference_vs_candidate_relative_error", float("inf"))
        if measurement is not None
        else float("inf")
    )
    action_checks = {
        "finite": measurement is not None and measurement.get("finite") is True,
        "deterministic": measurement is not None
        and measurement.get("deterministic") is True
        and measurement.get("candidate_repeat_equal") is True,
        "relative_error": math.isfinite(error)
        and 0.0 <= error <= DUAL_RELATIVE_TOLERANCE,
        "reference_apply_count": measurement is not None
        and measurement.get("reference_apply_count") == H1R2_REFERENCE_APPLY_COUNT,
        "candidate_apply_count": measurement is not None
        and measurement.get("candidate_apply_count") == H1R2_CANDIDATE_APPLY_COUNT,
        "candidate_repeat_apply_count": measurement is not None
        and measurement.get("candidate_repeat_apply_count")
        == H1R2_CANDIDATE_APPLY_COUNT,
        "second_within_reference_bound": (
            timing_values["candidate_repeat_apply_seconds"]
            <= 2.0 * timing_values["reference_apply_seconds"]
        ),
    }
    numerical_gate = _h1r2_numerical_gate(
        error,
        bool(measurement is not None and measurement.get("finite") is True),
        bool(
            measurement is not None
            and measurement.get("deterministic") is True
        ),
    )
    action_checks["numerical_gate"] = numerical_gate
    canonical_manifest = None if measurement is None else measurement.get(
        "candidate_manifest"
    )
    canonical_checks = {
        "export_after_numeric_gate": (
            measurement is not None
            and measurement.get("canonical_export") is numerical_gate
        ),
        "manifest_presence": (
            canonical_manifest is not None
            if numerical_gate
            else canonical_manifest is None
        ),
        "packet_count": (
            measurement is not None
            and measurement.get("candidate_canonical_packet_count")
            == expected_packet_count
            if numerical_gate
            else measurement is not None
            and measurement.get("candidate_canonical_packet_count") is None
        ),
        "manifest_path": (
            canonical_manifest is not None
            and canonical_manifest.get("path")
            == f"canonical/{H1R2_SOURCE_LABEL}/candidate_manifest.json"
            if numerical_gate
            else True
        ),
    }
    components = candidate_audit.get("retained_numeric_payload_components", {})
    component_sum = sum(int(value) for value in components.values())
    payload_local = candidate_audit.get(
        "retained_numeric_payload_local_bytes", float("nan")
    )
    payload = candidate_audit.get(
        "retained_numeric_payload_global_sum_bytes", float("nan")
    )
    payload_max = candidate_audit.get(
        "retained_numeric_payload_global_max_bytes", float("nan")
    )
    payload_gate = bool(
        math.isfinite(float(payload))
        and 0.0 < float(payload) <= H1R2_PAYLOAD_LIMIT_BYTES
        and component_sum == payload_local == payload == payload_max
    )
    scope_checks = {
        "degree": scope.get("degree") == 6,
        "h_nm": scope.get("h_nm") == 10.0,
        "mpi_size": scope.get("mpi_size") == 1,
        "timeout_seconds": scope.get("timeout_seconds") == H1R2_TIMEOUT_SECONDS,
        "payload_limit_bytes": scope.get("payload_limit_bytes")
        == H1R2_PAYLOAD_LIMIT_BYTES,
        "source_labels": scope.get("source_labels") == [H1R2_SOURCE_LABEL],
        "reference_apply_count": scope.get("reference_apply_count")
        == H1R2_REFERENCE_APPLY_COUNT,
        "candidate_apply_count": scope.get("candidate_apply_count")
        == H1R2_CANDIDATE_APPLY_COUNT,
        "field_formulation": scope.get("field_formulation")
        == "total_field_dtn_port",
        "operator": scope.get("operator")
        == "A_h=curl-curl-k0^2*epsilon*mass",
        "condensation": scope.get("condensation") is False,
        "ksp": scope.get("ksp") is False,
        "dtn_surface_term": scope.get("dtn_surface_term") is False,
        "dtn": scope.get("dtn") is False,
        "canonical_after_gate": scope.get("canonical_after_gate") is True,
        "ordinary_default_changed": scope.get("ordinary_default_changed") is False,
    }
    backend = (
        "dolfinx.fem.assemble_vector(existing ndarray, rank-one form)"
        " + vectorized MPC R^H"
    )
    audit_checks = {
        "backend": candidate_audit.get("backend") == backend,
        "form_rank": candidate_audit.get("form_rank") == 1,
        "coefficient_count": candidate_audit.get("coefficient_count") == 1,
        "apply_count": candidate_audit.get("apply_count")
        == H1R2_CANDIDATE_APPLY_COUNT,
        "storage_closure": candidate_audit.get("local_storage_entries")
        == candidate_audit.get("local_owned_rows", -1)
        + candidate_audit.get("local_ghost_rows", -1),
        "global_rows": candidate_audit.get("global_rows")
        == scope.get("global_rows"),
        "constraint_count": candidate_audit.get("constraint_count")
        == scope.get("constraint_count"),
        "constraint_nnz_closes": candidate_audit.get("constraint_nnz_closes")
        is True,
        "global_matrix_materialized": candidate_audit.get(
            "global_matrix_materialized"
        )
        is False,
        "global_A_materialized": candidate_audit.get(
            "global_matrix_materialized"
        )
        is False,
        "global_constraint_matrix_materialized": candidate_audit.get(
            "global_constraint_matrix_materialized"
        )
        is False,
        "global_condensed_schur_materialized": candidate_audit.get(
            "global_condensed_schur_materialized"
        )
        is False,
        "retained_dense_cell_tensor_count": candidate_audit.get(
            "retained_dense_cell_tensor_count"
        )
        == 0,
        "dense_cell_tensor_materialized_per_apply": candidate_audit.get(
            "dense_cell_tensor_materialized_per_apply"
        )
        is False,
        "cell_metadata_retained": candidate_audit.get("cell_metadata_retained")
        is False,
        "factor_count": candidate_audit.get("factor_count") == 0,
        "ksp_created": candidate_audit.get("ksp_created") is False,
        "dtn_used": candidate_audit.get("dtn_used") is False,
        "ordinary_default_changed": candidate_audit.get(
            "ordinary_default_changed"
        )
        is False,
    }
    checks = {
        **{f"source.{name}": value for name, value in source_checks.items()},
        **{f"timing.{name}": value for name, value in timing_checks.items()},
        **{f"action.{name}": value for name, value in action_checks.items()},
        **{
            f"canonical.{name}": value
            for name, value in canonical_checks.items()
        },
        **{f"scope.{name}": value for name, value in scope_checks.items()},
        **{f"candidate.{name}": value for name, value in audit_checks.items()},
        "payload": payload_gate,
        "payload_component_closure": component_sum
        == payload_local
        == payload
        == payload_max,
        "source_keys_fixed": source_keys_fixed,
    }
    problems = [name for name, value in checks.items() if not value]
    return {
        "pass": not problems,
        "status": "pass" if not problems else "gate_failed",
        "source_keys_fixed": source_keys_fixed,
        "source_checks": source_checks,
        "timing_checks": timing_checks,
        "action_checks": action_checks,
        "canonical_checks": canonical_checks,
        "scope_checks": scope_checks,
        "candidate_audit_checks": audit_checks,
        "payload_gate_pass": payload_gate,
        "payload_component_sum_bytes": component_sum,
        "candidate_payload_local_bytes": payload_local,
        "candidate_payload_global_sum_bytes": payload,
        "expected_canonical_packet_count": expected_packet_count,
        "problems": problems,
        "eligible_for_H1R2": not problems,
    }


def run_worker(
    run_dir: Path,
    *,
    mode: str = "h1_2",
) -> bool:
    worker_started = time.perf_counter()
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

    if mode not in {"h1_2", "h1r2"}:
        raise ValueError(f"unsupported Candidate-H worker mode: {mode}")
    h1r2 = mode == "h1r2"
    if h1r2:
        from src.solvers.hcurl_rank_one_mpc_action import (
            build_task037_extra_h1r2_mpc_action,
        )

    comm = MPI.COMM_WORLD
    progress_writer = sys.stdout
    progress_cell_count: int | None = None
    progress_local_rows: int | None = None
    progress_global_rows: int | None = None

    def emit_progress(
        event: str,
        *,
        source_label: str | None = None,
        apply_count: int | None = None,
    ) -> None:
        _emit_h1r_progress(
            progress_writer,
            event=event,
            worker_started=worker_started,
            rank=comm.rank,
            source_label=source_label,
            apply_count=apply_count,
            cell_count=progress_cell_count,
            local_rows=progress_local_rows,
            global_rows=progress_global_rows,
        )

    cfg = target_stage4_config(degree=6, h_nm=10.0)
    if cfg.stage4_boundary_model != "dtn_port":
        raise RuntimeError("Candidate-H requires the frozen dtn_port configuration identity")
    if cfg.divergence_penalty != 0.0:
        raise RuntimeError("Candidate-H H1.2 excludes divergence penalty")
    if comm.rank == 0:
        run_dir.mkdir(parents=True, exist_ok=True)
    comm.barrier()
    emit_progress("mesh_build_started")
    mesh_data = build_airbox_mesh_3d(cfg, run_dir / "mesh")
    progress_cell_count = int(
        mesh_data.mesh.topology.index_map(mesh_data.mesh.topology.dim).size_local
    )
    emit_progress("mesh_build_ready")
    emit_progress("function_space_started")
    function_space = _create_nedelec_space(mesh_data.mesh, cfg)
    progress_local_rows = int(function_space.dofmap.index_map.size_local)
    progress_global_rows = int(function_space.dofmap.index_map.size_global)
    emit_progress("function_space_ready")
    emit_progress("floquet_mpc_started")
    floquet = build_double_floquet_mpc(function_space, mesh_data, cfg)
    emit_progress("floquet_mpc_ready")
    if h1r2:
        emit_progress("form_definition_started")
        a_ufl, _ = _build_variational_forms(
            mesh_data.mesh,
            mesh_data,
            cfg,
            function_space,
            field_formulation="total_field_dtn_port",
            incident_field=None,
        )
        emit_progress("form_definition_ready")
    else:
        emit_progress("form_compile_started")
        a_ufl, _ = _build_variational_forms(
            mesh_data.mesh,
            mesh_data,
            cfg,
            function_space,
            field_formulation="total_field_dtn_port",
            incident_field=None,
        )
        a_compiled = fem.form(a_ufl)
        emit_progress("form_compile_ready")
    tolerance = floquet_geometry_tolerance(cfg)
    emit_progress("candidate_build_started")
    if h1r2:
        candidate = build_task037_extra_h1r2_mpc_action(
            a_ufl,
            floquet.mpc,
            task037_extra_h1r2=True,
        )
    else:
        candidate = build_task037_extra_candidate_h_fullspace_action(
            a_compiled,
            function_space,
            mesh_data.cell_tags,
            mpc=floquet.mpc,
            task037_extra_candidate_h=True,
            geometry_tolerance=tolerance,
        )
    progress_local_rows = int(candidate.audit["local_owned_rows"])
    progress_global_rows = int(candidate.audit["global_rows"])
    emit_progress("candidate_build_ready")
    emit_progress("reference_build_started")
    reference = MpcFormActionContext(a_ufl, floquet.mpc)
    emit_progress("reference_build_ready")
    try:
        source_results = []
        source_labels = (H1R2_SOURCE_LABEL,) if h1r2 else tuple(SOURCE_DEFINITIONS)
        for label in source_labels:
            emit_progress(
                "source_interpolation_started",
                source_label=label,
                apply_count=0,
            )
            source = _make_primal_source(function_space, floquet.mpc, cfg, label)
            emit_progress(
                "source_interpolation_ready",
                source_label=label,
                apply_count=0,
            )
            try:
                if h1r2:
                    source_results.append(
                        _h1r2_action_record(
                            reference,
                            candidate,
                            source,
                            run_dir=run_dir,
                            cfg=cfg,
                            function_space=function_space,
                            mpc=floquet.mpc,
                            tolerance=tolerance,
                            progress_writer=progress_writer,
                            progress_started=worker_started,
                            progress_rank=comm.rank,
                            progress_cell_count=progress_cell_count,
                            progress_local_rows=progress_local_rows,
                            progress_global_rows=progress_global_rows,
                        )
                    )
                else:
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
                            progress_writer=progress_writer,
                            progress_started=worker_started,
                            progress_rank=comm.rank,
                            progress_cell_count=progress_cell_count,
                            progress_local_rows=progress_local_rows,
                            progress_global_rows=progress_global_rows,
                        )
                    )
            finally:
                source.destroy()
        comm.barrier()
        candidate_audit = dict(candidate.audit)
        if h1r2:
            candidate_audit["retained_numeric_payload_components"] = dict(
                candidate.audit["retained_numeric_payload_components"]
            )
        else:
            candidate_audit["candidate_owned_numeric_payload_components"] = dict(
                candidate.audit["candidate_owned_numeric_payload_components"]
            )
        global_rows = int(candidate.audit["global_rows"])
        constraint_count = int(floquet.num_constraints)
        runtime_identity = _h1r2_runtime_identity() if h1r2 else None
        emit_progress("worker_summary_started")
        if comm.rank == 0:
            if h1r2:
                scope = {
                    "degree": 6,
                    "h_nm": 10.0,
                    "mpi_size": int(comm.size),
                    "global_rows": global_rows,
                    "constraint_count": constraint_count,
                    "source_labels": [H1R2_SOURCE_LABEL],
                    "reference_apply_count": H1R2_REFERENCE_APPLY_COUNT,
                    "candidate_apply_count": H1R2_CANDIDATE_APPLY_COUNT,
                    "field_formulation": "total_field_dtn_port",
                    "operator": "A_h=curl-curl-k0^2*epsilon*mass",
                    "dtn_surface_term": False,
                    "condensation": False,
                    "ksp": False,
                    "dtn": False,
                    "canonical_after_gate": True,
                    "payload_limit_bytes": H1R2_PAYLOAD_LIMIT_BYTES,
                    "timeout_seconds": H1R2_TIMEOUT_SECONDS,
                    "ordinary_default_changed": False,
                }
                qualification = _evaluate_h1r2_worker_qualification(
                    source_results,
                    candidate_audit,
                    scope=scope,
                )
                summary = {
                    "schema": "task037.candidate_h.h1r2.worker.v1",
                    "runtime_identity": runtime_identity,
                    "status": (
                        "pass" if qualification["pass"] else "gate_failed"
                    ),
                    "mpi_size": int(comm.size),
                    "global_rows": global_rows,
                    "constraint_count": constraint_count,
                    "scope": scope,
                    "source_definitions": {
                        H1R2_SOURCE_LABEL: _source_definition(
                            H1R2_SOURCE_LABEL, cfg
                        )
                    },
                    "measurements": source_results,
                    "candidate_action_audit": candidate_audit,
                    "reference_action": {
                        "type": "MpcFormActionContext",
                        "same_worker": True,
                        "apply_count": int(reference.apply_count),
                        "global_matrix_materialized": False,
                    },
                    "retained_numeric_payload_components": candidate_audit[
                        "retained_numeric_payload_components"
                    ],
                    "qualification": qualification,
                }
            else:
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
            if h1r2:
                summary = attach_evidence_sha256(summary)
            (run_dir / "run_summary.json").write_text(
                json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2)
                + "\n",
                encoding="utf-8",
            )
            worker_pass = bool(qualification["pass"])
        else:
            worker_pass = None
        worker_pass = bool(comm.bcast(worker_pass, root=0))
        emit_progress("worker_summary_ready")
        return worker_pass
    finally:
        reference.destroy()
        candidate.destroy()


def _watchdog_command(args, *, mode: str = "h1_2") -> list[str]:
    if mode == "h1r2":
        return [
            "mpiexec",
            "-n",
            "1",
            sys.executable,
            "-m",
            "benchmarks.run_task037_extra_candidate_h",
            "h1r2-worker",
            "--run-dir",
            str(Path(args.run_dir).resolve()),
        ]
    if mode != "h1_2":
        raise ValueError(f"unsupported Candidate-H watchdog mode: {mode}")
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


def _h1r2_source_is_clean(source: dict[str, Any]) -> bool:
    commit = source.get("source_commit_full_sha")
    return bool(
        isinstance(commit, str)
        and len(commit) == 40
        and all(character in "0123456789abcdef" for character in commit)
        and source.get("tracked_source_dirty") is False
        and source.get("source_worktree_dirty") is False
        and source.get("nonignored_untracked_paths") == []
        and source.get("worktree_status_porcelain") == []
        and source.get("git_error") is None
    )


def _h1r2_path_metadata(path: Path, name: str) -> dict[str, Any]:
    if not path.exists():
        return {
            "path": name,
            "present": False,
            "bytes": None,
            "sha256": None,
        }
    payload = path.read_bytes()
    return {
        "path": name,
        "present": True,
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def _h1r2_file_metadata(run_dir: Path) -> dict[str, dict[str, Any]]:
    metadata: dict[str, dict[str, Any]] = {}
    for name in ("worker_stdout.txt", "watchdog_timeline.jsonl", "run_summary.json"):
        metadata[name] = _h1r2_path_metadata(Path(run_dir) / name, name)
    return metadata


def _h1r2_memory_authority(peak_bytes: int | None = None) -> dict[str, Any]:
    peak = None if peak_bytes is None else int(peak_bytes)
    return {
        "review_v4_process_tree_peak_limit_bytes": H1_RSS_LIMIT_BYTES,
        "review_v4_process_tree_peak_limit_gib": 1.25,
        "review_v4_peak_gate_pass": (
            None if peak is None else peak <= H1_RSS_LIMIT_BYTES
        ),
        "user_lt_2GB_target_bytes": 2_000_000_000,
        "user_lt_2GB_target_evaluated": peak is not None,
        "user_lt_2GB_target_pass": (
            None if peak is None else peak < 2_000_000_000
        ),
        "user_lt_2GB_target_note": (
            "broader user target; not the Review V4 qualification authority"
        ),
    }


def _h1r2_scope_boundary() -> dict[str, str]:
    return {
        "H1R3": "locked_pending_review",
        "H2": "locked",
    }


def run_watchdog(args, *, mode: str = "h1_2") -> int:
    if mode not in {"h1_2", "h1r2"}:
        raise ValueError(f"unsupported Candidate-H watchdog mode: {mode}")
    h1r2 = mode == "h1r2"
    timeout_seconds = H1R2_TIMEOUT_SECONDS if h1r2 else H1_TIMEOUT_SECONDS
    poll_seconds = H1_POLL_SECONDS
    rss_limit_bytes = H1_RSS_LIMIT_BYTES
    run_dir = Path(args.run_dir).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = run_dir / "worker_stdout.txt"
    timeline_path = run_dir / "watchdog_timeline.jsonl"
    command = _watchdog_command(args, mode=mode)
    watchdog_runtime_identity = (
        _h1r2_runtime_identity() if h1r2 else None
    )
    source_at_start = _inspect_candidate_source()
    started = time.perf_counter()
    controlled_stop = None
    live_samples: list[dict[str, Any]] = []
    termination = {"requested": False, "method": None}
    process: subprocess.Popen[Any] | None = None
    completion_elapsed_seconds: float | None = None
    with (
        stdout_path.open("w", encoding="utf-8") as stdout,
        timeline_path.open("w", encoding="utf-8") as timeline,
    ):
        source_start_json = source_at_start.as_jsonable()
        source_start_allowed = (
            _h1r2_source_is_clean(source_start_json)
            if h1r2
            else not source_at_start.tracked_source_dirty
            and source_at_start.source_commit_full_sha is not None
        )
        if not source_start_allowed:
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
            timeline.write(json.dumps(sample, sort_keys=True) + "\n")
            timeline.flush()
            if return_code is not None:
                if h1r2:
                    completion_elapsed_seconds = time.perf_counter() - started
                    if completion_elapsed_seconds > timeout_seconds:
                        controlled_stop = "timeout"
                break
            live_samples.append(sample)
            if not _live_sample_is_readable(sample):
                controlled_stop = "resource_authority_unreadable"
            else:
                process_tree_rss = int(sample["worker_tree_rss_sum_bytes"])
                swap = _live_sample_swap(sample)
                if process_tree_rss > rss_limit_bytes:
                    controlled_stop = "process_tree_rss_over_1.25_GiB"
                elif swap != 0:
                    controlled_stop = "worker_process_tree_swap_nonzero"
                elif time.perf_counter() - started > timeout_seconds:
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
    worker_runtime_identity = (
        worker_summary.get("runtime_identity")
        if h1r2 and worker_summary is not None
        else None
    )
    worker_runtime_identity_match = bool(
        h1r2
        and worker_runtime_identity == watchdog_runtime_identity
    )
    source_start_json = source_at_start.as_jsonable()
    source_end_json = source_at_end.as_jsonable()
    source_stable_clean = (
        bool(
            _h1r2_source_is_clean(source_start_json)
            and _h1r2_source_is_clean(source_end_json)
            and source_start_json["source_commit_full_sha"]
            == source_end_json["source_commit_full_sha"]
        )
        if h1r2
        else bool(
            source_at_start.source_commit_full_sha is not None
            and source_at_start.source_commit_full_sha
            == source_at_end.source_commit_full_sha
            and not source_at_start.tracked_source_dirty
            and not source_at_end.tracked_source_dirty
        )
    )
    worker_summary_evidence_sha256_valid = bool(
        worker_summary is not None
        and evidence_sha256_is_valid(worker_summary)
    )
    worker_qualification_recomputed = None
    if h1r2 and worker_summary is not None:
        if worker_summary.get("schema") == "task037.candidate_h.h1r2.worker.v1":
            worker_qualification_recomputed = (
                _evaluate_h1r2_worker_qualification(
                    worker_summary.get("measurements", []),
                    worker_summary.get("candidate_action_audit", {}),
                    scope=worker_summary.get("scope", {}),
                )
            )
    worker_qualification_pass = bool(
        worker_summary is not None
        and (
            worker_qualification_recomputed["pass"]
            if h1r2 and worker_qualification_recomputed is not None
            else worker_summary.get("qualification", {}).get("pass") is True
        )
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
        and peak_process_tree_rss <= rss_limit_bytes
        and (
            not h1r2
            or (
                completion_elapsed_seconds is not None
                and completion_elapsed_seconds <= timeout_seconds
                and worker_summary_evidence_sha256_valid
                and worker_qualification_recomputed is not None
                and _h1r2_runtime_identity_is_valid(
                    watchdog_runtime_identity
                )
                and _h1r2_runtime_identity_is_valid(worker_runtime_identity)
                and worker_runtime_identity_match
            )
        )
    )
    wall_seconds = float(time.perf_counter() - started)
    if h1r2:
        watchdog_summary = {
            "schema": "task037.candidate_h.h1r2.watchdog.v1",
            "command": command,
            "mpi_size": 1,
            "return_code": None if return_code is None else int(return_code),
            "status": "pass" if watchdog_pass else (
                "controlled_stop" if controlled_stop is not None else "worker_failed"
            ),
            "controlled_stop": controlled_stop,
            "timeout_seconds": timeout_seconds,
            "poll_interval_seconds": poll_seconds,
            "rss_limit_bytes": rss_limit_bytes,
            "termination": termination,
            "wall_seconds": wall_seconds,
            "completion_elapsed_seconds": completion_elapsed_seconds,
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
            "worker_summary_evidence_sha256_valid": (
                worker_summary_evidence_sha256_valid
            ),
            "worker_qualification_recomputed": worker_qualification_recomputed,
            "worker_qualification_pass": worker_qualification_pass,
            "watchdog_runtime_identity": watchdog_runtime_identity,
            "worker_runtime_identity_match": worker_runtime_identity_match,
            "source_at_start": source_start_json,
            "source_at_end": source_end_json,
            "source_stable_clean": source_stable_clean,
            "reference_and_candidate_same_worker": True,
            "raw_artifacts": _h1r2_file_metadata(run_dir),
        }
        watchdog_summary = attach_evidence_sha256(watchdog_summary)
    else:
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
            "wall_seconds": wall_seconds,
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
            "source_at_start": source_start_json,
            "source_at_end": source_end_json,
            "source_stable_clean": source_stable_clean,
            "reference_and_candidate_same_worker": True,
        }
    (run_dir / "watchdog_summary.json").write_text(
        json.dumps(watchdog_summary, ensure_ascii=False, sort_keys=True, indent=2)
        + "\n",
        encoding="utf-8",
    )
    return 0 if watchdog_pass else 1


def _h1r2_check_raw(run_dir: Path) -> dict[str, Any]:
    run_dir = Path(run_dir).resolve()
    watchdog = json.loads(
        (run_dir / "watchdog_summary.json").read_text(encoding="utf-8")
    )
    worker = json.loads(
        (run_dir / "run_summary.json").read_text(encoding="utf-8")
    )
    timeline = [
        json.loads(line)
        for line in (run_dir / "watchdog_timeline.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line
    ]
    expected_artifacts = _h1r2_file_metadata(run_dir)
    recorded_artifacts = watchdog.get("raw_artifacts", {})
    raw_artifact_checks = {
        name: isinstance(recorded_artifacts, dict)
        and recorded_artifacts.get(name) == metadata
        for name, metadata in expected_artifacts.items()
    }
    actual_file_artifacts = dict(expected_artifacts)
    actual_file_artifacts["watchdog_summary.json"] = _h1r2_path_metadata(
        run_dir / "watchdog_summary.json", "watchdog_summary.json"
    )

    source_start = watchdog.get("source_at_start", {})
    source_end = watchdog.get("source_at_end", {})
    source_sha = source_start.get("source_commit_full_sha")
    source_checks = {
        "start_clean": _h1r2_source_is_clean(source_start),
        "end_clean": _h1r2_source_is_clean(source_end),
        "same_commit": (
            _h1r2_source_is_clean(source_start)
            and _h1r2_source_is_clean(source_end)
            and source_start.get("source_commit_full_sha")
            == source_end.get("source_commit_full_sha")
        ),
        "recorded_stable_clean": watchdog.get("source_stable_clean") is True,
    }
    expected_command = _watchdog_command(
        SimpleNamespace(run_dir=run_dir), mode="h1r2"
    )
    watchdog_runtime_identity = watchdog.get("watchdog_runtime_identity")
    worker_runtime_identity = worker.get("runtime_identity")
    command = watchdog.get("command")
    runtime_identity_checks = {
        "watchdog_values": _h1r2_runtime_identity_is_valid(
            watchdog_runtime_identity
        ),
        "worker_values": _h1r2_runtime_identity_is_valid(
            worker_runtime_identity
        ),
        "identical": worker_runtime_identity == watchdog_runtime_identity,
        "command_python_executable": (
            isinstance(command, list)
            and len(command) > 3
            and command[3] == watchdog_runtime_identity.get("sys.executable")
            if isinstance(watchdog_runtime_identity, dict)
            else False
        ),
        "recorded_match": watchdog.get("worker_runtime_identity_match") is True,
    }
    timeout = H1R2_TIMEOUT_SECONDS
    rss_limit = H1_RSS_LIMIT_BYTES
    expected_manifest_path = (
        f"canonical/{H1R2_SOURCE_LABEL}/candidate_manifest.json"
    )
    watchdog_checks = {
        "schema": watchdog.get("schema")
        == "task037.candidate_h.h1r2.watchdog.v1",
        "evidence_sha256": evidence_sha256_is_valid(watchdog),
        "command": watchdog.get("command") == expected_command,
        "mpi_size": watchdog.get("mpi_size") == 1,
        "timeout_seconds": watchdog.get("timeout_seconds") == timeout,
        "poll_interval_seconds": watchdog.get("poll_interval_seconds")
        == H1_POLL_SECONDS,
        "rss_limit_bytes": watchdog.get("rss_limit_bytes") == rss_limit,
        "status": watchdog.get("status") == "pass",
        "return_code": watchdog.get("return_code") == 0,
        "controlled_stop": watchdog.get("controlled_stop") is None,
        "termination": watchdog.get("termination") == {
            "requested": False,
            "method": None,
        },
        "wall_seconds": math.isfinite(
            float(watchdog.get("wall_seconds", float("nan")))
        )
        and float(watchdog.get("wall_seconds")) >= 0.0,
        "completion_elapsed_seconds": (
            math.isfinite(
                float(watchdog.get("completion_elapsed_seconds", float("nan")))
            )
            and 0.0
            <= float(watchdog.get("completion_elapsed_seconds"))
            <= timeout
        ),
        "peak_scope": watchdog.get("peak_includes_only_worker_alive_samples")
        is True,
    }
    live_timeline = [
        sample for sample in timeline if sample.get("worker_alive") is True
    ]
    timeline_readable = bool(
        live_timeline
        and all(_live_sample_is_readable(sample) for sample in live_timeline)
    )
    timeline_swap = (
        None
        if not live_timeline
        else max(int(_live_sample_swap(sample)) for sample in live_timeline)
    )
    timeline_peak = max(
        (int(sample["worker_tree_rss_sum_bytes"]) for sample in live_timeline),
        default=0,
    )
    timeline_checks = {
        "live_samples_readable": timeline_readable,
        "live_sample_count": watchdog.get("worker_live_sample_count")
        == len(live_timeline),
        "peak_recomputed": watchdog.get("peak_process_tree_rss_bytes")
        == timeline_peak,
        "peak_limit": timeline_peak <= rss_limit,
        "swap_recomputed": watchdog.get("worker_process_tree_swap_bytes")
        == timeline_swap,
        "swap_zero": timeline_readable and timeline_swap == 0,
        "resource_authority": watchdog.get("resource_authority_readable")
        is timeline_readable,
        "worker_swap_zero": watchdog.get("worker_swap_zero")
        is (timeline_readable and timeline_swap == 0),
    }

    scope = worker.get("scope", {})
    candidate_audit = worker.get("candidate_action_audit", {})
    measurements = worker.get("measurements", [])
    fresh_qualification = _evaluate_h1r2_worker_qualification(
        measurements,
        candidate_audit,
        scope=scope,
    )
    reference_action = worker.get("reference_action", {})
    global_rows = worker.get("global_rows")
    constraint_count = worker.get("constraint_count")
    measurement = measurements[0] if measurements else {}
    source_definition_record = worker.get("source_definitions", {}).get(
        H1R2_SOURCE_LABEL
    )
    worker_checks = {
        "schema": worker.get("schema")
        == "task037.candidate_h.h1r2.worker.v1",
        "evidence_sha256": evidence_sha256_is_valid(worker),
        "mpi_size": worker.get("mpi_size") == 1,
        "scope_global_rows": isinstance(scope.get("global_rows"), int)
        and global_rows == scope.get("global_rows"),
        "scope_constraint_count": isinstance(scope.get("constraint_count"), int)
        and constraint_count == scope.get("constraint_count"),
        "source_definition_matches_measurement": source_definition_record
        == measurement.get("source_definition"),
        "top_level_status": worker.get("status") == "pass",
        "qualification_status_matches": worker.get("qualification", {}).get(
            "status"
        )
        == fresh_qualification["status"],
        "reference_action_type": reference_action.get("type")
        == "MpcFormActionContext",
        "reference_same_worker": reference_action.get("same_worker") is True
        and watchdog.get("reference_and_candidate_same_worker") is True,
        "reference_apply_count": reference_action.get("apply_count")
        == H1R2_REFERENCE_APPLY_COUNT,
        "reference_no_global_matrix": reference_action.get(
            "global_matrix_materialized"
        )
        is False,
        "fresh_qualification_pass": fresh_qualification["pass"] is True,
        "watchdog_recomputed_pass": watchdog.get(
            "worker_qualification_recomputed", {}
        ).get("pass")
        == fresh_qualification["pass"],
        "recorded_worker_pass_matches": worker.get("qualification", {}).get(
            "pass"
        )
        == fresh_qualification["pass"],
        "watchdog_worker_summary_present": watchdog.get(
            "worker_summary_present"
        )
        is True,
        "watchdog_worker_summary_status": watchdog.get(
            "worker_summary_status"
        )
        == worker.get("status"),
        "watchdog_worker_evidence_valid": watchdog.get(
            "worker_summary_evidence_sha256_valid"
        )
        is evidence_sha256_is_valid(worker),
        "watchdog_worker_qualification_pass": watchdog.get(
            "worker_qualification_pass"
        )
        is fresh_qualification["pass"],
    }

    numerical_gate = fresh_qualification["action_checks"].get(
        "numerical_gate", False
    )
    expected_packet_count = fresh_qualification[
        "expected_canonical_packet_count"
    ]
    canonical_checks: dict[str, Any]
    actual_file_artifacts[expected_manifest_path] = _h1r2_path_metadata(
        run_dir / expected_manifest_path, expected_manifest_path
    )
    if numerical_gate:
        manifest_record = measurement.get("candidate_manifest")
        manifest_path_ok = (
            isinstance(manifest_record, dict)
            and manifest_record.get("path") == expected_manifest_path
        )
        if manifest_path_ok:
            manifest = read_canonical_manifest(
                run_dir / expected_manifest_path,
                expected_sha256=str(manifest_record["sha256"]),
            )
            extractor = manifest.get("extractor_audit", {})
            canonical_checks = {
                "export_after_numerical_gate": measurement.get(
                    "canonical_export"
                )
                is True,
                "manifest_path": True,
                "role": manifest.get("role") == "full_fe_dual",
                "mpi_size": manifest.get("mpi_size") == 1,
                "dtype": manifest.get("dtype") == "complex128",
                "packet_count": manifest.get("global_summed_packet_count")
                == expected_packet_count,
                "record_packet_count": manifest_record.get("packet_count")
                == manifest.get("global_summed_packet_count")
                == expected_packet_count,
                "duplicate_count": manifest.get("summed_local_duplicate_count")
                == 0,
                "extractor_source": extractor.get("source")
                == H1R2_SOURCE_LABEL,
                "extractor_method": extractor.get("method")
                == "H1R2-direct-rank-one-MPC",
                "manifest_evidence": True,
            }
        else:
            canonical_checks = {
                "export_after_numerical_gate": False,
                "manifest_path": False,
            }
    else:
        canonical_checks = {
            "not_required_after_failed_numerical_gate": measurement.get(
                "canonical_export"
            ) is False
            and measurement.get("candidate_manifest") is None,
        }

    checks = {
        **{f"watchdog.{name}": value for name, value in watchdog_checks.items()},
        **{f"raw.{name}": value for name, value in raw_artifact_checks.items()},
        **{f"source.{name}": value for name, value in source_checks.items()},
        **{f"timeline.{name}": value for name, value in timeline_checks.items()},
        **{f"worker.{name}": value for name, value in worker_checks.items()},
        **{
            f"runtime.{name}": value
            for name, value in runtime_identity_checks.items()
        },
        **{
            f"canonical.{name}": value
            for name, value in canonical_checks.items()
        },
    }
    problems = [name for name, value in checks.items() if value is not True]
    manifest_record = measurement.get("candidate_manifest")
    raw_evidence_sha256 = {
        "worker_summary_bytes": actual_file_artifacts["run_summary.json"][
            "sha256"
        ],
        "watchdog_summary_bytes": actual_file_artifacts["watchdog_summary.json"][
            "sha256"
        ],
        "canonical_manifest_bytes": (
            actual_file_artifacts[expected_manifest_path]["sha256"]
            if actual_file_artifacts[expected_manifest_path]["present"]
            else None
        ),
    }
    compact_measurement = {
        "global_rows": global_rows,
        "constraint_count": constraint_count,
        "reference_first_apply_seconds": measurement.get(
            "reference_apply_seconds"
        ),
        "candidate_first_apply_seconds": measurement.get(
            "candidate_apply_seconds"
        ),
        "candidate_second_apply_seconds": measurement.get(
            "candidate_repeat_apply_seconds"
        ),
        "relative_error": measurement.get(
            "reference_vs_candidate_relative_error"
        ),
        "finite": measurement.get("finite"),
        "deterministic": measurement.get("deterministic"),
        "retained_payload": {
            "local_bytes": candidate_audit.get(
                "retained_numeric_payload_local_bytes"
            ),
            "global_sum_bytes": candidate_audit.get(
                "retained_numeric_payload_global_sum_bytes"
            ),
            "global_max_bytes": candidate_audit.get(
                "retained_numeric_payload_global_max_bytes"
            ),
        },
        "completion_elapsed_seconds": watchdog.get(
            "completion_elapsed_seconds"
        ),
        "process_tree_peak_rss_bytes": timeline_peak,
        "process_tree_swap_bytes": timeline_swap,
        "canonical_export": measurement.get("canonical_export"),
        "canonical_packet_count": measurement.get(
            "candidate_canonical_packet_count"
        ),
    }
    timeline_peak_for_authority = timeline_peak if live_timeline else None
    return {
        "schema": "task037.candidate_h.h1r2.compact_check.v1",
        "status": "pass" if not problems else "gate_failed",
        "pass": not problems,
        "checks": checks,
        "watchdog_checks": watchdog_checks,
        "raw_artifact_checks": raw_artifact_checks,
        "source_checks": source_checks,
        "timeline_checks": timeline_checks,
        "worker_checks": worker_checks,
        "runtime_identity_checks": runtime_identity_checks,
        "canonical_checks": canonical_checks,
        "worker_qualification_recomputed": fresh_qualification,
        "raw_run_directory": str(run_dir),
        "source_identity": {
            "source_commit_full_sha": source_sha
            if source_checks["same_commit"]
            else None,
            "start": source_start,
            "end": source_end,
        },
        "raw_artifacts": actual_file_artifacts,
        "raw_evidence_sha256": raw_evidence_sha256,
        "embedded_evidence_sha256": {
            "worker_summary": worker.get("evidence_sha256"),
            "watchdog_summary": watchdog.get("evidence_sha256"),
        },
        "runtime_identity": {
            "watchdog": watchdog_runtime_identity,
            "worker": worker_runtime_identity,
            "match": watchdog.get("worker_runtime_identity_match"),
        },
        "measurement": compact_measurement,
        "memory_authority": _h1r2_memory_authority(timeline_peak_for_authority),
        "scope_boundary": _h1r2_scope_boundary(),
        "problems": problems,
    }


def run_h1r2_check(run_dir: Path, output: Path) -> int:
    try:
        result = _h1r2_check_raw(Path(run_dir))
    except (OSError, KeyError, TypeError, ValueError, IndexError, AttributeError) as exc:
        result = {
            "schema": "task037.candidate_h.h1r2.compact_check.v1",
            "status": "gate_failed",
            "pass": False,
            "problems": [
                f"controlled_checker_failure:{type(exc).__name__}:{exc}"
            ],
            "memory_authority": _h1r2_memory_authority(),
            "scope_boundary": _h1r2_scope_boundary(),
        }
    result = attach_evidence_sha256(result)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0 if result["pass"] else 1


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
    h1r2_worker = subparsers.add_parser("h1r2-worker")
    h1r2_worker.add_argument("--run-dir", type=Path, required=True)
    watchdog = subparsers.add_parser("watchdog")
    watchdog.add_argument("--run-dir", type=Path, required=True)
    watchdog.add_argument("--mpi-size", type=int, choices=(1, 2), required=True)
    h1r2_watchdog = subparsers.add_parser("h1r2-watchdog")
    h1r2_watchdog.add_argument("--run-dir", type=Path, required=True)
    h1r2_check = subparsers.add_parser("h1r2-check")
    h1r2_check.add_argument("--run-dir", type=Path, required=True)
    h1r2_check.add_argument("--output", type=Path, required=True)
    compare = subparsers.add_parser("compare")
    compare.add_argument("--mpi1-run-dir", type=Path, required=True)
    compare.add_argument("--mpi2-run-dir", type=Path, required=True)
    compare.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "worker":
        return 0 if run_worker(args.run_dir) else 1
    if args.command == "h1r2-worker":
        return 0 if run_worker(args.run_dir, mode="h1r2") else 1
    if args.command == "watchdog":
        return run_watchdog(args)
    if args.command == "h1r2-watchdog":
        return run_watchdog(args, mode="h1r2")
    if args.command == "h1r2-check":
        return run_h1r2_check(args.run_dir, args.output)
    result = compare_run_directories(args.mpi1_run_dir, args.mpi2_run_dir)
    payload = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output is None:
        print(payload, end="")
    else:
        args.output.write_text(payload, encoding="utf-8")
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
