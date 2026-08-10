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
import statistics
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
from benchmarks.task034_wsl_resources import process_tree_sample
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
H1R3_SOURCE_LABEL = "seed_17037"
H1R3_TIMEOUT_SECONDS = 180.0
H1R3_REFERENCE_APPLY_COUNT = 1
H1R3_CANDIDATE_APPLY_COUNT = 12
H1R3_STEADY_APPLY_START = 5
H1R3_STEADY_APPLY_END = 12
H1R3_STEADY_MEDIAN_LIMIT_SECONDS = 1.494291376147885
H1R3_RSS_SPAN_LIMIT_BYTES = 64 * 1024**2
H1R3_PEAK_LIMIT_BYTES = int(0.45 * GIB)
H1R3_ROOT_PID_FILE = "h1r3_root_pid.json"
H1R3_TELEMETRY_FILE = "apply_telemetry.jsonl"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
H1R31_SOURCE_LABEL = "seed_17037"
H1R31_TIMEOUT_SECONDS = 600.0
H1R31_REFERENCE_APPLY_COUNT = 1
H1R31_CANDIDATE_APPLY_COUNT = 2
H1R31_PEAK_LIMIT_BYTES = int(0.75 * GIB)
H1R31_CANDIDATE_SECOND_LIMIT_SECONDS = 2.390866201836616
H1R31_PAYLOAD_BYTES_PER_ROW_LIMIT = 45
H1R31_GLOBAL_ROWS = 173802
H1R31_CONSTRAINT_COUNT = 9210
H1R31_PACKET_COUNT = 164592
H1R31_CANONICAL_TOLERANCE = 1.0e-12
H1R31_HISTORICAL_RAW_DIR = (
    REPOSITORY_ROOT
    / "benchmarks/artifacts/task037_extra_h1r2_v4_66ccb589_mpi1_20260809_run1"
)
H1R31_HISTORICAL_RECORD = (
    REPOSITORY_ROOT
    / "benchmarks/cases/101_task37_extra_development/records/"
    "h1r2_single_source_action.json"
)
H1R31_HISTORICAL_SOURCE_SHA = (
    "66ccb5891b7f6caac3ebfe08f72cf525c40f3fef"
)
H1R31_HISTORICAL_MANIFEST_SHA256 = (
    "1dfdcbfcd73010234dcdb7438eb3d869c9cbd07ed6981fc0ba5275c170faf139"
)
H1R32_SOURCE_LABEL = "seed_17037"
H1R32_TIMEOUT_SECONDS = 1800.0
H1R32_REFERENCE_APPLY_COUNT = 1
H1R32_CANDIDATE_APPLY_COUNT = 2
H1R32_PEAK_LIMIT_BYTES = int(0.75 * GIB)
H1R32_GLOBAL_ROWS = 1127502
H1R32_GLOBAL_CELLS = 1680
H1R32_AXIS_CELL_COUNTS = (12, 5, 28)
H1R32_H1_AXIS_CELL_COUNTS = (51, 25, 140)
H1R32_H1_GLOBAL_ROWS = 116527176
H1R32_PAYLOAD_BYTES_PER_ROW_LIMIT = 45
H1R32_PACKED_BYTES_PER_ROW_LIMIT = 28
H1R32_ALPHA_PAYLOAD_LIMIT = 1.10
H1R32_ACTION_SECONDS_PER_ROW_LIMIT = 1.03171980264e-5
H1R32_PEAK_SLOPE_BYTES_PER_ROW_LIMIT = 512
H1R32_H10_RAW_DIR = (
    REPOSITORY_ROOT
    / "benchmarks/artifacts/task037_extra_h1r3_warm_repeat_v6_5529a01"
)
H1R32_H10_RECORD = (
    REPOSITORY_ROOT
    / "benchmarks/cases/101_task37_extra_development/records/"
    "h1r3_warm_repeat_v2.json"
)
H1R32_H10_RECORD_SHA256 = (
    "b2e347c1663df932ace40efdee898ca1c6a62790ce30b748e64fcb721bcac658"
)
H1R32_H10_SOURCE_SHA = "5529a0159ac5b1500b4ccbd17ad962e2a875f3f1"
H1R32_H10_GLOBAL_ROWS = 173802
H1R32_H10_PAYLOAD_BYTES = 6151104
H1R32_H10_PEAK_BYTES = 340541440
H1R32_H1R31_RECORD = (
    REPOSITORY_ROOT
    / "benchmarks/cases/101_task37_extra_development/records/"
    "h1r3_mpi2_partition_identity.json"
)
H1R32_H1R31_RECORD_SHA256 = (
    "2e927f1734c676a9df48972e0d4e353cabee085b91772e78159d48628a33020c"
)
H1R32_ROOT_PID_FILE = "h1r3_h5_root_pid.json"


def _h1r32_structured_hexa_identity(
    axis_cell_counts: tuple[int, int, int], degree: int = 6
) -> dict[str, Any]:
    """Return the fixed tensor-hexa H(curl) row decomposition for H1R3.2."""

    nx, ny, nz = (int(value) for value in axis_cell_counts)
    p = int(degree)
    if min(nx, ny, nz, p) <= 0:
        raise ValueError("structured hexa identity requires positive counts")
    edge_rows = p * (
        nx * (ny + 1) * (nz + 1)
        + (nx + 1) * ny * (nz + 1)
        + (nx + 1) * (ny + 1) * nz
    )
    face_rows = 2 * p * (p - 1) * (
        (nx + 1) * ny * nz
        + nx * (ny + 1) * nz
        + nx * ny * (nz + 1)
    )
    cell_rows = 3 * p * (p - 1) ** 2 * nx * ny * nz
    return {
        "axis_cell_counts": [nx, ny, nz],
        "degree": p,
        "global_cells": nx * ny * nz,
        "edge_rows": edge_rows,
        "face_rows": face_rows,
        "cell_rows": cell_rows,
        "global_rows": edge_rows + face_rows + cell_rows,
    }


def _h1r32_scope(
    *,
    global_rows: int,
    constraint_count: int,
    global_cells: int,
    axis_cell_counts: tuple[int, int, int],
) -> dict[str, Any]:
    return {
        "degree": 6,
        "h_nm": 5.0,
        "mpi_size": 1,
        "source_labels": [H1R32_SOURCE_LABEL],
        "reference_apply_count": H1R32_REFERENCE_APPLY_COUNT,
        "candidate_apply_count": H1R32_CANDIDATE_APPLY_COUNT,
        "timeout_seconds": H1R32_TIMEOUT_SECONDS,
        "process_tree_peak_limit_bytes": H1R32_PEAK_LIMIT_BYTES,
        "payload_bytes_per_global_row_limit": H1R32_PAYLOAD_BYTES_PER_ROW_LIMIT,
        "packed_bytes_per_global_row_limit": H1R32_PACKED_BYTES_PER_ROW_LIMIT,
        "alpha_payload_limit": H1R32_ALPHA_PAYLOAD_LIMIT,
        "action_seconds_per_global_row_limit": H1R32_ACTION_SECONDS_PER_ROW_LIMIT,
        "peak_slope_bytes_per_row_limit": H1R32_PEAK_SLOPE_BYTES_PER_ROW_LIMIT,
        "global_rows": int(global_rows),
        "constraint_count": int(constraint_count),
        "global_cells": int(global_cells),
        "axis_cell_counts": [int(value) for value in axis_cell_counts],
        "field_formulation": "total_field_dtn_port",
        "operator": "A_h=curl-curl-k0^2*epsilon*mass",
        "dtn_surface_term": False,
        "condensation": False,
        "ksp": False,
        "dtn": False,
        "canonical_export_enabled": False,
        "canonical_after_gate": False,
        "ordinary_default_changed": False,
        "h2": "locked",
    }


def _h1r32_fixed_scope_checks(scope: object) -> dict[str, bool]:
    scope = scope if isinstance(scope, dict) else {}
    constraint_count = scope.get("constraint_count")
    return {
        "degree": scope.get("degree") == 6,
        "h_nm": scope.get("h_nm") == 5.0,
        "mpi_size": scope.get("mpi_size") == 1,
        "source_labels": scope.get("source_labels") == [H1R32_SOURCE_LABEL],
        "reference_apply_count": scope.get("reference_apply_count")
        == H1R32_REFERENCE_APPLY_COUNT,
        "candidate_apply_count": scope.get("candidate_apply_count")
        == H1R32_CANDIDATE_APPLY_COUNT,
        "timeout_seconds": scope.get("timeout_seconds") == H1R32_TIMEOUT_SECONDS,
        "process_tree_peak_limit_bytes": scope.get(
            "process_tree_peak_limit_bytes"
        )
        == H1R32_PEAK_LIMIT_BYTES,
        "axis_cell_counts": scope.get("axis_cell_counts")
        == list(H1R32_AXIS_CELL_COUNTS),
        "global_cells": scope.get("global_cells") == H1R32_GLOBAL_CELLS,
        "global_rows": scope.get("global_rows") == H1R32_GLOBAL_ROWS,
        "constraint_count": isinstance(constraint_count, int)
        and not isinstance(constraint_count, bool)
        and constraint_count >= 0,
        "field_formulation": scope.get("field_formulation")
        == "total_field_dtn_port",
        "operator": scope.get("operator")
        == "A_h=curl-curl-k0^2*epsilon*mass",
        "dtn_surface_term": scope.get("dtn_surface_term") is False,
        "condensation": scope.get("condensation") is False,
        "ksp": scope.get("ksp") is False,
        "dtn": scope.get("dtn") is False,
        "canonical_export_enabled": scope.get("canonical_export_enabled")
        is False,
        "canonical_after_gate": scope.get("canonical_after_gate") is False,
        "ordinary_default_changed": scope.get("ordinary_default_changed")
        is False,
        "h2_locked": scope.get("h2") == "locked",
    }


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


def _h1r3_output_sha256(values: Any) -> str:
    import numpy as np

    array = np.asarray(values)
    if not array.flags.c_contiguous:
        raise RuntimeError("H1R3 output buffer is not contiguous")
    return hashlib.sha256(memoryview(array).cast("B")).hexdigest()


def _h1r3_copy_first_output(output: Any, first_output: Any) -> None:
    output.copy(result=first_output)


def _h1r3_smaps_rollup(pid: int) -> tuple[int, int] | None:
    path = Path(f"/proc/{int(pid)}/smaps_rollup")
    try:
        values: dict[str, int] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            fields = line.split()
            if len(fields) >= 2 and fields[0].rstrip(":") in {
                "Pss",
                "Private_Clean",
                "Private_Dirty",
                "Private_Hugetlb",
            }:
                values[fields[0].rstrip(":")] = int(fields[1]) * 1024
    except (OSError, IndexError, ValueError):
        return None
    required = ("Pss", "Private_Clean", "Private_Dirty")
    if any(name not in values for name in required):
        return None
    uss = sum(values.get(name, 0) for name in (
        "Private_Clean", "Private_Dirty", "Private_Hugetlb"
    ))
    return int(values["Pss"]), int(uss)


def _h1r3_process_tree_memory(root_pid: int, worker_pid: int) -> dict[str, Any]:
    tree = process_tree_sample(int(root_pid))
    if (
        int(worker_pid) not in tree.pids
        or tree.all_status_readable is not True
        or not tree.pids
    ):
        raise RuntimeError("H1R3 process-tree authority is unreadable")
    pss_total = 0
    uss_total = 0
    for pid in tree.pids:
        memory = _h1r3_smaps_rollup(pid)
        if memory is None:
            raise RuntimeError("H1R3 process-tree smaps authority is unreadable")
        pss_total += memory[0]
        uss_total += memory[1]
    return {
        "process_tree_root_pid": int(root_pid),
        "process_tree_pids": [int(pid) for pid in tree.pids],
        "worker_pid_in_process_tree": True,
        "process_tree_rss_bytes": int(tree.rss_bytes),
        "process_tree_pss_bytes": int(pss_total),
        "process_tree_uss_bytes": int(uss_total),
        "process_tree_swap_bytes": int(tree.swap_bytes),
        "process_tree_all_status_readable": True,
    }


def _h1r3_read_root_pid(run_dir: Path) -> int:
    record = json.loads(
        (Path(run_dir) / H1R3_ROOT_PID_FILE).read_text(encoding="utf-8")
    )
    if record.get("schema") != "task037.candidate_h.h1r3.root_pid.v1":
        raise RuntimeError("H1R3 root pid metadata schema is invalid")
    root_pid = record["root_pid"]
    if isinstance(root_pid, bool) or not isinstance(root_pid, int) or root_pid <= 0:
        raise RuntimeError("H1R3 root pid metadata is invalid")
    return int(root_pid)


def _h1r3_read_telemetry(run_dir: Path) -> list[dict[str, Any]]:
    telemetry: list[dict[str, Any]] = []
    with (Path(run_dir) / H1R3_TELEMETRY_FILE).open(
        "r", encoding="utf-8"
    ) as stream:
        for line in stream:
            if line.strip():
                telemetry.append(json.loads(line))
    return telemetry


def _h1r3_path_metadata(path: Path, name: str) -> dict[str, Any]:
    return _h1r2_path_metadata(path, name)


def _h1r3_file_metadata(run_dir: Path) -> dict[str, dict[str, Any]]:
    return {
        name: _h1r3_path_metadata(Path(run_dir) / name, name)
        for name in (
            "worker_stdout.txt",
            "watchdog_timeline.jsonl",
            "run_summary.json",
            H1R3_TELEMETRY_FILE,
            H1R3_ROOT_PID_FILE,
        )
    }


def _h1r31_file_metadata(
    run_dir: Path, manifest_relative_path: str | None = None
) -> dict[str, dict[str, Any]]:
    names = ("worker_stdout.txt", "watchdog_timeline.jsonl", "run_summary.json")
    metadata = {
        name: _h1r3_path_metadata(Path(run_dir) / name, name) for name in names
    }
    if manifest_relative_path is not None:
        metadata[manifest_relative_path] = _h1r3_path_metadata(
            Path(run_dir) / manifest_relative_path, manifest_relative_path
        )
    return metadata


def _h1r32_file_metadata(run_dir: Path) -> dict[str, dict[str, Any]]:
    return {
        name: _h1r3_path_metadata(Path(run_dir) / name, name)
        for name in (
            "worker_stdout.txt",
            "watchdog_timeline.jsonl",
            "run_summary.json",
            H1R32_ROOT_PID_FILE,
        )
    }


def _h1r3_scope() -> dict[str, Any]:
    return {
        "degree": 6,
        "h_nm": 10.0,
        "mpi_size": 1,
        "source_labels": [H1R3_SOURCE_LABEL],
        "reference_apply_count": H1R3_REFERENCE_APPLY_COUNT,
        "candidate_apply_count": H1R3_CANDIDATE_APPLY_COUNT,
        "steady_apply_indices": list(
            range(H1R3_STEADY_APPLY_START, H1R3_STEADY_APPLY_END + 1)
        ),
        "timeout_seconds": H1R3_TIMEOUT_SECONDS,
        "steady_median_limit_seconds": H1R3_STEADY_MEDIAN_LIMIT_SECONDS,
        "rss_span_limit_bytes": H1R3_RSS_SPAN_LIMIT_BYTES,
        "process_tree_peak_limit_bytes": H1R3_PEAK_LIMIT_BYTES,
        "field_formulation": "total_field_dtn_port",
        "operator": "A_h=curl-curl-k0^2*epsilon*mass",
        "dtn_surface_term": False,
        "condensation": False,
        "ksp": False,
        "dtn": False,
        "canonical_after_numerical_gate": True,
        "ordinary_default_changed": False,
    }


def _h1r3_fixed_scope_checks(scope: object) -> dict[str, bool]:
    expected = _h1r3_scope()
    if not isinstance(scope, dict):
        return {name: False for name in expected}
    return {
        name: scope.get(name) == value for name, value in expected.items()
    }


def _h1r31_scope(
    *, global_rows: int | None = None, constraint_count: int | None = None
) -> dict[str, Any]:
    scope = {
        "degree": 6,
        "h_nm": 10.0,
        "mpi_size": 2,
        "source_labels": [H1R31_SOURCE_LABEL],
        "reference_apply_count": H1R31_REFERENCE_APPLY_COUNT,
        "candidate_apply_count": H1R31_CANDIDATE_APPLY_COUNT,
        "timeout_seconds": H1R31_TIMEOUT_SECONDS,
        "process_tree_peak_limit_bytes": H1R31_PEAK_LIMIT_BYTES,
        "candidate_second_limit_seconds": H1R31_CANDIDATE_SECOND_LIMIT_SECONDS,
        "payload_bytes_per_global_row_limit": H1R31_PAYLOAD_BYTES_PER_ROW_LIMIT,
        "canonical_packet_count": H1R31_PACKET_COUNT,
        "canonical_compare_tolerance": H1R31_CANONICAL_TOLERANCE,
        "field_formulation": "total_field_dtn_port",
        "operator": "A_h=curl-curl-k0^2*epsilon*mass",
        "dtn_surface_term": False,
        "condensation": False,
        "ksp": False,
        "dtn": False,
        "canonical_after_gate": True,
        "ordinary_default_changed": False,
    }
    scope["global_rows"] = (
        H1R31_GLOBAL_ROWS if global_rows is None else int(global_rows)
    )
    scope["constraint_count"] = (
        H1R31_CONSTRAINT_COUNT
        if constraint_count is None
        else int(constraint_count)
    )
    return scope


def _h1r31_fixed_scope_checks(scope: object) -> dict[str, bool]:
    expected = _h1r31_scope()
    if not isinstance(scope, dict):
        return {name: False for name in expected}
    checks = {name: scope.get(name) == value for name, value in expected.items()}
    return checks


def _evaluate_h1r31_worker_qualification(
    measurement: object,
    candidate_audit: object,
    *,
    scope: object,
) -> dict[str, Any]:
    """Recompute the fixed H1R.3.1 MPI2 worker contract from raw fields."""

    measurement = measurement if isinstance(measurement, dict) else {}
    candidate_audit = (
        candidate_audit if isinstance(candidate_audit, dict) else {}
    )
    scope_checks = _h1r31_fixed_scope_checks(scope)
    source_definition = measurement.get("source_definition")
    source_checks = {
        "label": measurement.get("label") == H1R31_SOURCE_LABEL,
        "definition_present": isinstance(source_definition, dict),
        "definition_hash": False,
        "seed": False,
        "frequency": False,
        "formula": False,
        "envelope": False,
    }
    if isinstance(source_definition, dict):
        source_checks.update(
            {
                "definition_hash": (
                    measurement.get("source_definition_sha256")
                    == source_definition.get("definition_sha256")
                    == _h1r2_source_definition_hash(source_definition)
                ),
                "seed": source_definition.get("seed") == 17037,
                "frequency": tuple(source_definition.get("frequency", ()))
                == (1, 1, 0),
                "formula": source_definition.get("formula")
                == SOURCE_DEFINITIONS[H1R31_SOURCE_LABEL]["formula"],
                "envelope": json.dumps(
                    source_definition.get("envelope_coefficients"),
                    sort_keys=True,
                )
                == json.dumps(
                    SOURCE_DEFINITIONS[H1R31_SOURCE_LABEL][
                        "envelope_coefficients"
                    ],
                    sort_keys=True,
                ),
            }
        )

    def finite_positive(value: object) -> bool:
        return bool(
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(float(value))
            and float(value) > 0.0
        )

    reference_seconds = measurement.get("reference_apply_seconds")
    first_seconds = measurement.get("candidate_apply_seconds")
    second_seconds = measurement.get("candidate_repeat_apply_seconds")
    relative_error = measurement.get("reference_vs_candidate_relative_error")
    timing_checks = {
        "timing_reduction": measurement.get("timing_reduction") == "mpi_max",
        "reference_positive_finite": finite_positive(reference_seconds),
        "candidate_first_positive_finite": finite_positive(first_seconds),
        "candidate_second_positive_finite": finite_positive(second_seconds),
        "second_within_reference": bool(
            finite_positive(second_seconds)
            and finite_positive(reference_seconds)
            and float(second_seconds) <= 2.0 * float(reference_seconds)
        ),
        "second_fixed_limit": bool(
            finite_positive(second_seconds)
            and float(second_seconds) <= H1R31_CANDIDATE_SECOND_LIMIT_SECONDS
        ),
    }
    action_checks = {
        "finite": measurement.get("finite") is True,
        "deterministic": measurement.get("deterministic") is True
        and measurement.get("candidate_repeat_equal") is True,
        "relative_error": bool(
            isinstance(relative_error, (int, float))
            and not isinstance(relative_error, bool)
            and math.isfinite(float(relative_error))
            and 0.0 <= float(relative_error) <= DUAL_RELATIVE_TOLERANCE
        ),
        "reference_apply_count": measurement.get("reference_apply_count")
        == H1R31_REFERENCE_APPLY_COUNT,
        "candidate_apply_count": measurement.get("candidate_apply_count")
        == H1R31_CANDIDATE_APPLY_COUNT,
        "candidate_repeat_apply_count": measurement.get(
            "candidate_repeat_apply_count"
        )
        == H1R31_CANDIDATE_APPLY_COUNT,
    }
    global_rows = candidate_audit.get("global_rows")

    def nonnegative_int(value: object) -> bool:
        return isinstance(value, int) and not isinstance(value, bool) and value >= 0

    components = candidate_audit.get("retained_numeric_payload_components")
    components_valid = bool(
        isinstance(components, dict)
        and bool(components)
        and all(nonnegative_int(value) for value in components.values())
    )
    payload_local = candidate_audit.get("retained_numeric_payload_local_bytes")
    payload_sum = candidate_audit.get(
        "retained_numeric_payload_global_sum_bytes"
    )
    payload_max = candidate_audit.get(
        "retained_numeric_payload_global_max_bytes"
    )
    payload_checks = {
        "components_valid": components_valid,
        "component_sum_local": bool(
            components_valid
            and sum(int(value) for value in components.values()) == payload_local
        ),
        "local_nonnegative": nonnegative_int(payload_local)
        and payload_local > 0,
        "global_sum_nonnegative": nonnegative_int(payload_sum)
        and payload_sum > 0,
        "global_max_nonnegative": nonnegative_int(payload_max)
        and payload_max >= 0,
        "local_le_global_max": bool(
            nonnegative_int(payload_local)
            and nonnegative_int(payload_max)
            and payload_local <= payload_max
        ),
        "global_sum_row_limit": bool(
            nonnegative_int(payload_sum)
            and isinstance(global_rows, int)
            and not isinstance(global_rows, bool)
            and global_rows > 0
            and payload_sum
            <= H1R31_PAYLOAD_BYTES_PER_ROW_LIMIT * global_rows
        ),
        "global_max_is_bounded": bool(
            nonnegative_int(payload_max)
            and nonnegative_int(payload_sum)
            and payload_max <= payload_sum
        ),
    }
    local_storage_fields_nonnegative = all(
        nonnegative_int(candidate_audit.get(name))
        for name in (
            "local_storage_entries",
            "local_owned_rows",
            "local_ghost_rows",
        )
    )
    inventory_checks = {
        "backend": candidate_audit.get("backend")
        == (
            "dolfinx.fem.assemble_vector(existing ndarray, rank-one form)"
            " + vectorized MPC R^H"
        ),
        "form_rank": candidate_audit.get("form_rank") == 1,
        "coefficient_count": candidate_audit.get("coefficient_count") == 1,
        "apply_count": candidate_audit.get("apply_count")
        == H1R31_CANDIDATE_APPLY_COUNT,
        "local_storage_fields_nonnegative": local_storage_fields_nonnegative,
        "local_storage_closure": (
            local_storage_fields_nonnegative
            and candidate_audit.get("local_storage_entries")
            == candidate_audit.get("local_owned_rows")
            + candidate_audit.get("local_ghost_rows")
        ),
        "global_rows": candidate_audit.get("global_rows")
        == (scope.get("global_rows") if isinstance(scope, dict) else None),
        "constraint_count": candidate_audit.get("constraint_count")
        == (
            scope.get("constraint_count")
            if isinstance(scope, dict)
            else None
        ),
        "constraint_nnz_closes": candidate_audit.get("constraint_nnz_closes")
        is True,
        "global_matrix_materialized": candidate_audit.get(
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
        "cell_schur_matrix_nnz": candidate_audit.get("cell_schur_matrix_nnz")
        == 0,
        "slab_matrix_nnz": candidate_audit.get("slab_matrix_nnz") == 0,
        "cell_schur_matrix_materialized": candidate_audit.get(
            "cell_schur_matrix_materialized"
        )
        is False,
        "slab_matrix_materialized": candidate_audit.get(
            "slab_matrix_materialized"
        )
        is False,
        "factor_count": candidate_audit.get("factor_count") == 0,
        "ksp_created": candidate_audit.get("ksp_created") is False,
        "dtn_used": candidate_audit.get("dtn_used") is False,
        "ordinary_default_changed": candidate_audit.get(
            "ordinary_default_changed"
        )
        is False,
    }
    canonical_record = measurement.get("candidate_manifest")
    canonical_checks = {
        "export_after_numeric_gate": measurement.get("canonical_export") is True,
        "manifest_present": isinstance(canonical_record, dict),
        "measurement_packet_count": measurement.get(
            "candidate_canonical_packet_count"
        )
        == H1R31_PACKET_COUNT,
        "manifest_packet_count": isinstance(canonical_record, dict)
        and canonical_record.get("packet_count") == H1R31_PACKET_COUNT,
        "measurement_manifest_packet_count": (
            isinstance(canonical_record, dict)
            and measurement.get("candidate_canonical_packet_count")
            == canonical_record.get("packet_count")
        ),
        "path": isinstance(canonical_record, dict)
        and canonical_record.get("path")
        == f"canonical/{H1R31_SOURCE_LABEL}/candidate_manifest.json",
    }
    checks = {
        **{f"scope.{name}": value for name, value in scope_checks.items()},
        **{f"source.{name}": value for name, value in source_checks.items()},
        **{f"timing.{name}": value for name, value in timing_checks.items()},
        **{f"action.{name}": value for name, value in action_checks.items()},
        **{f"payload.{name}": value for name, value in payload_checks.items()},
        **{f"inventory.{name}": value for name, value in inventory_checks.items()},
        **{f"canonical.{name}": value for name, value in canonical_checks.items()},
    }
    numerical_gate = all(action_checks.values())
    problems = [name for name, value in checks.items() if value is not True]
    return {
        "status": "pass" if not problems else "gate_failed",
        "pass": not problems,
        "problems": problems,
        "checks": checks,
        "scope_checks": scope_checks,
        "source_checks": source_checks,
        "timing_checks": timing_checks,
        "action_checks": action_checks,
        "payload_checks": payload_checks,
        "inventory_checks": inventory_checks,
        "canonical_checks": canonical_checks,
        "numerical_gate_pass": numerical_gate,
        "relative_error": relative_error,
        "retained_payload_global_sum_bytes": payload_sum,
        "retained_payload_global_max_bytes": payload_max,
        "expected_canonical_packet_count": H1R31_PACKET_COUNT,
    }


def _evaluate_h1r32_worker_qualification(
    measurement: object,
    candidate_audit: object,
    *,
    scope: object,
) -> dict[str, Any]:
    """Recompute the fixed H1R3.2 h5 action and payload contract."""

    measurement = measurement if isinstance(measurement, dict) else {}
    candidate_audit = (
        candidate_audit if isinstance(candidate_audit, dict) else {}
    )

    def nonnegative_int(value: object) -> bool:
        return (
            isinstance(value, int)
            and not isinstance(value, bool)
            and value >= 0
        )

    def positive_number(value: object) -> bool:
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(float(value))
            and float(value) > 0.0
        )

    scope_checks = _h1r32_fixed_scope_checks(scope)
    source_definition = measurement.get("source_definition")
    source_checks = {
        "label": measurement.get("label") == H1R32_SOURCE_LABEL,
        "definition_mapping": isinstance(source_definition, dict),
        "definition_hash": False,
        "seed": False,
        "frequency": False,
        "formula": False,
    }
    if isinstance(source_definition, dict):
        source_checks.update(
            {
                "definition_hash": (
                    measurement.get("source_definition_sha256")
                    == source_definition.get("definition_sha256")
                    == _h1r2_source_definition_hash(source_definition)
                ),
                "seed": source_definition.get("seed") == 17037,
                "frequency": tuple(source_definition.get("frequency", ()))
                == (1, 1, 0),
                "formula": source_definition.get("formula")
                == SOURCE_DEFINITIONS[H1R32_SOURCE_LABEL]["formula"],
            }
        )

    reference_seconds = measurement.get("reference_apply_seconds")
    candidate_seconds = measurement.get("candidate_apply_seconds")
    second_seconds = measurement.get("candidate_repeat_apply_seconds")
    timing_checks = {
        "reference_positive": positive_number(reference_seconds),
        "candidate_first_positive": positive_number(candidate_seconds),
        "candidate_second_positive": positive_number(second_seconds),
        "timing_reduction": measurement.get("timing_reduction") == "mpi_max",
        "second_seconds_per_row": bool(
            positive_number(second_seconds)
            and float(second_seconds) / H1R32_GLOBAL_ROWS
            <= H1R32_ACTION_SECONDS_PER_ROW_LIMIT
        ),
    }
    relative_error = measurement.get(
        "reference_vs_candidate_relative_error", float("nan")
    )
    action_checks = {
        "finite": measurement.get("finite") is True,
        "deterministic": measurement.get("deterministic") is True
        and measurement.get("candidate_repeat_equal") is True,
        "relative_error": (
            isinstance(relative_error, (int, float))
            and not isinstance(relative_error, bool)
            and math.isfinite(float(relative_error))
            and 0.0 <= float(relative_error) <= DUAL_RELATIVE_TOLERANCE
        ),
        "reference_apply_count": measurement.get("reference_apply_count")
        == H1R32_REFERENCE_APPLY_COUNT,
        "candidate_apply_count": measurement.get("candidate_apply_count")
        == H1R32_CANDIDATE_APPLY_COUNT,
        "candidate_repeat_apply_count": measurement.get(
            "candidate_repeat_apply_count"
        )
        == H1R32_CANDIDATE_APPLY_COUNT,
        "canonical_disabled": measurement.get("canonical_export") is False
        and measurement.get("candidate_canonical_packet_count") is None
        and measurement.get("candidate_manifest") is None,
    }
    components = candidate_audit.get("retained_numeric_payload_components")
    components_valid = bool(
        isinstance(components, dict)
        and bool(components)
        and all(nonnegative_int(value) for value in components.values())
    )
    payload_local = candidate_audit.get("retained_numeric_payload_local_bytes")
    payload_sum = candidate_audit.get(
        "retained_numeric_payload_global_sum_bytes"
    )
    payload_max = candidate_audit.get(
        "retained_numeric_payload_global_max_bytes"
    )
    packed_bytes = candidate_audit.get("last_packed_coefficient_bytes")
    bounded_bytes = candidate_audit.get("per_apply_bounded_temporary_bytes")
    component_sum = (
        sum(int(value) for value in components.values())
        if components_valid
        else None
    )
    payload_checks = {
        "components_valid": components_valid,
        "component_sum_closes": components_valid
        and component_sum == payload_local,
        "local_nonnegative": nonnegative_int(payload_local)
        and payload_local > 0,
        "global_sum_nonnegative": nonnegative_int(payload_sum)
        and payload_sum > 0,
        "global_max_nonnegative": nonnegative_int(payload_max)
        and payload_max > 0,
        "mpi1_payload_closure": (
            component_sum == payload_local == payload_sum == payload_max
        ),
        "payload_row_limit": (
            nonnegative_int(payload_sum)
            and payload_sum <= H1R32_PAYLOAD_BYTES_PER_ROW_LIMIT
            * H1R32_GLOBAL_ROWS
        ),
        "packed_nonnegative": nonnegative_int(packed_bytes)
        and packed_bytes >= 0,
        "packed_bound_matches": nonnegative_int(bounded_bytes)
        and bounded_bytes == packed_bytes,
        "packed_row_limit": (
            nonnegative_int(packed_bytes)
            and packed_bytes <= H1R32_PACKED_BYTES_PER_ROW_LIMIT
            * H1R32_GLOBAL_ROWS
        ),
    }
    local_storage_checks = {
        name: nonnegative_int(candidate_audit.get(name))
        for name in (
            "local_storage_entries",
            "local_owned_rows",
            "local_ghost_rows",
        )
    }
    local_storage_checks["storage_closure"] = bool(
        all(local_storage_checks.values())
        and candidate_audit.get("local_storage_entries")
        == candidate_audit.get("local_owned_rows")
        + candidate_audit.get("local_ghost_rows")
    )
    inventory_expected = {
        "global_matrix_materialized": False,
        "global_constraint_matrix_materialized": False,
        "global_condensed_schur_materialized": False,
        "cell_schur_matrix_nnz": 0,
        "slab_matrix_nnz": 0,
        "cell_schur_matrix_materialized": False,
        "slab_matrix_materialized": False,
        "retained_dense_cell_tensor_count": 0,
        "dense_cell_tensor_materialized_per_apply": False,
        "cell_metadata_retained": False,
        "factor_count": 0,
        "ksp_created": False,
        "dtn_used": False,
        "ordinary_default_changed": False,
    }
    inventory_checks = {
        name: candidate_audit.get(name) == expected
        for name, expected in inventory_expected.items()
    }
    audit_checks = {
        "backend": candidate_audit.get("backend")
        == (
            "dolfinx.fem.assemble_vector(existing ndarray, rank-one form)"
            " + vectorized MPC R^H"
        ),
        "form_rank": candidate_audit.get("form_rank") == 1,
        "coefficient_count": candidate_audit.get("coefficient_count") == 1,
        "apply_count": candidate_audit.get("apply_count")
        == H1R32_CANDIDATE_APPLY_COUNT,
        "global_rows": candidate_audit.get("global_rows")
        == H1R32_GLOBAL_ROWS,
        "constraint_count": candidate_audit.get("constraint_count")
        == (scope.get("constraint_count") if isinstance(scope, dict) else None),
        "constraint_nnz_closes": candidate_audit.get("constraint_nnz_closes")
        is True,
        "local_storage": all(local_storage_checks.values()),
    }
    checks = {
        **{f"scope.{name}": value for name, value in scope_checks.items()},
        **{f"source.{name}": value for name, value in source_checks.items()},
        **{f"timing.{name}": value for name, value in timing_checks.items()},
        **{f"action.{name}": value for name, value in action_checks.items()},
        **{f"payload.{name}": value for name, value in payload_checks.items()},
        **{
            f"local_storage.{name}": value
            for name, value in local_storage_checks.items()
        },
        **{f"audit.{name}": value for name, value in audit_checks.items()},
        **{
            f"inventory.{name}": value
            for name, value in inventory_checks.items()
        },
    }
    problems = [name for name, value in checks.items() if value is not True]
    return {
        "status": "pass" if not problems else "gate_failed",
        "pass": not problems,
        "problems": problems,
        "checks": checks,
        "scope_checks": scope_checks,
        "source_checks": source_checks,
        "timing_checks": timing_checks,
        "action_checks": action_checks,
        "payload_checks": payload_checks,
        "local_storage_checks": local_storage_checks,
        "audit_checks": audit_checks,
        "inventory_checks": inventory_checks,
        "retained_payload_global_sum_bytes": payload_sum,
        "retained_payload_global_max_bytes": payload_max,
        "packed_temporary_bytes": packed_bytes,
        "relative_error": relative_error,
    }


def _evaluate_h1r3_warm_worker_qualification(
    measurement: object,
    candidate_audit: object,
    telemetry: object,
    *,
    scope: object,
) -> dict[str, Any]:
    """Recompute the fixed H1R.3.0 worker Gate from raw fields."""

    measurement = measurement if isinstance(measurement, dict) else {}
    candidate_audit = candidate_audit if isinstance(candidate_audit, dict) else {}
    telemetry = (
        telemetry
        if isinstance(telemetry, list)
        and all(isinstance(item, dict) for item in telemetry)
        else []
    )

    def nonnegative_int(value: object) -> bool:
        return isinstance(value, int) and not isinstance(value, bool) and value >= 0

    def positive_int(value: object) -> bool:
        return isinstance(value, int) and not isinstance(value, bool) and value > 0

    scope_checks = _h1r3_fixed_scope_checks(scope)
    source_definition = measurement.get("source_definition")
    source_checks = {
        "label": measurement.get("label") == H1R3_SOURCE_LABEL,
        "source_definition": isinstance(source_definition, dict),
        "source_hash": False,
        "seed": False,
        "frequency": False,
        "formula": False,
    }
    if isinstance(source_definition, dict):
        source_checks.update(
            {
                "source_hash": (
                    measurement.get("source_definition_sha256")
                    == source_definition.get("definition_sha256")
                    == _h1r2_source_definition_hash(source_definition)
                ),
                "seed": source_definition.get("seed") == 17037,
                "frequency": tuple(source_definition.get("frequency", ()))
                == (1, 1, 0),
                "formula": source_definition.get("formula")
                == SOURCE_DEFINITIONS[H1R3_SOURCE_LABEL]["formula"],
            }
        )

    expected_indices = list(
        range(H1R3_REFERENCE_APPLY_COUNT, H1R3_CANDIDATE_APPLY_COUNT + 1)
    )
    indices = [
        item.get("apply_index")
        for item in telemetry
        if isinstance(item, dict)
    ]
    telemetry_shape = indices == expected_indices
    output_hashes = [
        item.get("output_sha256") for item in telemetry
    ]
    hash_checks = bool(
        len(output_hashes) == H1R3_CANDIDATE_APPLY_COUNT
        and all(
            isinstance(value, str)
            and len(value) == 64
            and all(character in "0123456789abcdef" for character in value)
            for value in output_hashes
        )
    )
    output_hash_identity = bool(
        hash_checks
        and len(set(output_hashes)) == 1
    )
    telemetry_schema = bool(
        len(telemetry) == H1R3_CANDIDATE_APPLY_COUNT
        and all(
            item.get("schema") == "task037.candidate_h.h1r3.apply_telemetry.v1"
            for item in telemetry
        )
    )
    finite_checks = [item.get("finite") is True for item in telemetry]
    deterministic_checks = [
        item.get("bitwise_equal_to_first") is True for item in telemetry
    ]
    timings = [item.get("seconds") for item in telemetry]
    rss_values = [item.get("process_tree_rss_bytes") for item in telemetry]
    packed_values = [item.get("packed_temporary_bytes") for item in telemetry]
    components = [item.get("retained_numeric_payload_components") for item in telemetry]
    payload_local = [item.get("retained_numeric_payload_local_bytes") for item in telemetry]
    payload_sum = [item.get("retained_numeric_payload_global_sum_bytes") for item in telemetry]
    payload_max = [item.get("retained_numeric_payload_global_max_bytes") for item in telemetry]
    retained_components_valid = bool(
        len(components) == H1R3_CANDIDATE_APPLY_COUNT
        and all(
            isinstance(value, dict)
            and bool(value)
            and all(nonnegative_int(item) for item in value.values())
            for value in components
        )
        and isinstance(candidate_audit.get("retained_numeric_payload_components"), dict)
        and bool(candidate_audit["retained_numeric_payload_components"])
        and all(
            nonnegative_int(item)
            for item in candidate_audit["retained_numeric_payload_components"].values()
        )
    )
    payload_values_valid = bool(
        len(payload_local) == H1R3_CANDIDATE_APPLY_COUNT
        and len(payload_sum) == H1R3_CANDIDATE_APPLY_COUNT
        and len(payload_max) == H1R3_CANDIDATE_APPLY_COUNT
        and all(nonnegative_int(value) for value in payload_local)
        and all(nonnegative_int(value) for value in payload_sum)
        and all(nonnegative_int(value) for value in payload_max)
        and all(
            nonnegative_int(candidate_audit.get(name))
            for name in (
                "retained_numeric_payload_local_bytes",
                "retained_numeric_payload_global_sum_bytes",
                "retained_numeric_payload_global_max_bytes",
            )
        )
    )
    process_tree_root_pids = [
        item.get("process_tree_root_pid") for item in telemetry
    ]
    process_tree_pids_valid = bool(
        len(telemetry) == H1R3_CANDIDATE_APPLY_COUNT
        and all(
            positive_int(item.get("process_tree_root_pid"))
            and isinstance(item.get("process_tree_worker_pid"), int)
            and not isinstance(item.get("process_tree_worker_pid"), bool)
            and item.get("process_tree_worker_pid") > 0
            and isinstance(item.get("process_tree_pids"), list)
            and all(positive_int(pid) for pid in item["process_tree_pids"])
            and item.get("process_tree_root_pid") in item["process_tree_pids"]
            and item.get("process_tree_worker_pid") in item["process_tree_pids"]
            for item in telemetry
        )
        and telemetry
        and all(
            value == process_tree_root_pids[0] for value in process_tree_root_pids
        )
    )
    resource_checks = bool(
        len(telemetry) == H1R3_CANDIDATE_APPLY_COUNT
        and all(
            nonnegative_int(item.get(name))
            for item in telemetry
            for name in (
                "process_tree_rss_bytes",
                "process_tree_pss_bytes",
                "process_tree_uss_bytes",
                "process_tree_swap_bytes",
            )
        )
        and all(item.get("worker_pid_in_process_tree") is True for item in telemetry)
        and all(
            item.get("process_tree_all_status_readable") is True
            for item in telemetry
        )
        and process_tree_pids_valid
    )
    finite_timing = bool(
        len(timings) == H1R3_CANDIDATE_APPLY_COUNT
        and all(
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(float(value))
            and float(value) > 0.0
            for value in timings
        )
    )
    stable_components = bool(
        retained_components_valid
        and all(value == components[0] for value in components[1:])
        and components[0] == candidate_audit.get(
            "retained_numeric_payload_components"
        )
    )
    stable_payload = bool(
        payload_values_valid
        and all(value == payload_local[0] for value in payload_local[1:])
        and all(value == payload_sum[0] for value in payload_sum[1:])
        and all(value == payload_max[0] for value in payload_max[1:])
        and payload_local[0]
        == candidate_audit.get("retained_numeric_payload_local_bytes")
        and payload_sum[0]
        == candidate_audit.get("retained_numeric_payload_global_sum_bytes")
        and payload_max[0]
        == candidate_audit.get("retained_numeric_payload_global_max_bytes")
    )
    component_sum = (
        sum(int(value) for value in components[0].values())
        if retained_components_valid
        else None
    )
    payload_closure = bool(
        stable_payload
        and component_sum == payload_local[0] == payload_sum[0] == payload_max[0]
    )
    stable_packed = bool(
        len(packed_values) == H1R3_CANDIDATE_APPLY_COUNT
        and all(value == packed_values[0] for value in packed_values[1:])
        and nonnegative_int(packed_values[0])
        and nonnegative_int(candidate_audit.get("last_packed_coefficient_bytes"))
        and packed_values[0] == candidate_audit.get(
            "last_packed_coefficient_bytes"
        )
    )
    first_error = measurement.get("first_vs_reference_relative_error")
    last_error = measurement.get("last_vs_reference_relative_error")
    error_checks = {
        "first": isinstance(first_error, (int, float))
        and not isinstance(first_error, bool)
        and math.isfinite(float(first_error))
        and 0.0 <= float(first_error) <= DUAL_RELATIVE_TOLERANCE,
        "last": isinstance(last_error, (int, float))
        and not isinstance(last_error, bool)
        and math.isfinite(float(last_error))
        and 0.0 <= float(last_error) <= DUAL_RELATIVE_TOLERANCE,
    }
    measurement_seconds = measurement.get("candidate_apply_seconds")
    telemetry_seconds = [item.get("seconds") for item in telemetry]
    error_binding = bool(
        len(telemetry) == H1R3_CANDIDATE_APPLY_COUNT
        and measurement.get("first_vs_reference_relative_error")
        == telemetry[0].get("reference_relative_error")
        and measurement.get("last_vs_reference_relative_error")
        == telemetry[-1].get("reference_relative_error")
        and all(
            item.get("reference_relative_error") is None
            for item in telemetry[1:-1]
        )
    )
    candidate_seconds_binding = measurement_seconds == telemetry_seconds
    reference_timing = measurement.get("reference_apply_seconds")
    reference_timing_valid = bool(
        isinstance(reference_timing, (int, float))
        and not isinstance(reference_timing, bool)
        and math.isfinite(float(reference_timing))
        and float(reference_timing) > 0.0
    )
    raw_telemetry_binding = bool(
        telemetry_schema and candidate_seconds_binding and error_binding
    )
    steady_values = [
        float(timings[index - 1])
        for index in range(H1R3_STEADY_APPLY_START, H1R3_STEADY_APPLY_END + 1)
        if len(timings) >= index
        and isinstance(timings[index - 1], (int, float))
        and not isinstance(timings[index - 1], bool)
        and math.isfinite(float(timings[index - 1]))
    ]
    steady_median = (
        statistics.median(steady_values) if len(steady_values) == 8 else None
    )
    rss_steady = [
        rss_values[index - 1]
        for index in range(H1R3_STEADY_APPLY_START, H1R3_STEADY_APPLY_END + 1)
        if len(rss_values) >= index and nonnegative_int(rss_values[index - 1])
    ]
    rss_span = max(rss_steady) - min(rss_steady) if len(rss_steady) == 8 else None
    inventory_checks = {
        "backend": candidate_audit.get("backend")
        == (
            "dolfinx.fem.assemble_vector(existing ndarray, rank-one form)"
            " + vectorized MPC R^H"
        ),
        "form_rank": candidate_audit.get("form_rank") == 1,
        "coefficient_count": candidate_audit.get("coefficient_count") == 1,
        "apply_count": candidate_audit.get("apply_count")
        == H1R3_CANDIDATE_APPLY_COUNT,
        "constraint_nnz_closes": candidate_audit.get("constraint_nnz_closes")
        is True,
        "local_storage_closes": candidate_audit.get("local_storage_entries")
        == candidate_audit.get("local_owned_rows", -1)
        + candidate_audit.get("local_ghost_rows", -1)
        if all(
            nonnegative_int(candidate_audit.get(name))
            for name in (
                "local_storage_entries",
                "local_owned_rows",
                "local_ghost_rows",
            )
        )
        else False,
        "global_rows": candidate_audit.get("global_rows")
        == (scope.get("global_rows") if isinstance(scope, dict) else None),
        "constraint_count": candidate_audit.get("constraint_count")
        == (scope.get("constraint_count") if isinstance(scope, dict) else None),
        "global_matrix_materialized": candidate_audit.get(
            "global_matrix_materialized"
        ) is False,
        "global_constraint_matrix_materialized": candidate_audit.get(
            "global_constraint_matrix_materialized"
        ) is False,
        "global_condensed_schur_materialized": candidate_audit.get(
            "global_condensed_schur_materialized"
        ) is False,
        "retained_dense_cell_tensor_count": candidate_audit.get(
            "retained_dense_cell_tensor_count"
        ) == 0,
        "dense_cell_tensor_materialized_per_apply": candidate_audit.get(
            "dense_cell_tensor_materialized_per_apply"
        ) is False,
        "cell_metadata_retained": candidate_audit.get("cell_metadata_retained")
        is False,
        "cell_schur_matrix_nnz": candidate_audit.get("cell_schur_matrix_nnz")
        == 0,
        "slab_matrix_nnz": candidate_audit.get("slab_matrix_nnz") == 0,
        "factor_count": candidate_audit.get("factor_count") == 0,
        "ksp_created": candidate_audit.get("ksp_created") is False,
        "dtn_used": candidate_audit.get("dtn_used") is False,
        "ordinary_default_changed": candidate_audit.get(
            "ordinary_default_changed"
        ) is False,
    }
    numerical_gate = bool(
        telemetry_shape
        and telemetry_schema
        and hash_checks
        and output_hash_identity
        and measurement.get("reference_apply_count")
        == H1R3_REFERENCE_APPLY_COUNT
        and measurement.get("candidate_apply_count")
        == H1R3_CANDIDATE_APPLY_COUNT
        and all(finite_checks)
        and all(deterministic_checks)
        and error_binding
        and all(error_checks.values())
    )
    timing_gate = bool(
        finite_timing
        and reference_timing_valid
        and candidate_seconds_binding
        and steady_median is not None
        and steady_median <= H1R3_STEADY_MEDIAN_LIMIT_SECONDS
    )
    payload_gate = bool(stable_components and payload_closure and stable_packed)
    resource_gate = bool(
        rss_span is not None
        and rss_span <= H1R3_RSS_SPAN_LIMIT_BYTES
        and resource_checks
        and all(item.get("process_tree_swap_bytes") == 0 for item in telemetry)
        and max(rss_values, default=H1R3_PEAK_LIMIT_BYTES + 1)
        <= H1R3_PEAK_LIMIT_BYTES
    )
    canonical_present = measurement.get("candidate_manifest") is not None
    canonical_gate = bool(
        measurement.get("canonical_export") is True
        and measurement.get("canonical_export_count") == 1
        if numerical_gate
        else measurement.get("canonical_export") is False
        and measurement.get("canonical_export_count") == 0
        and not canonical_present
    )
    checks = {
        "scope": all(scope_checks.values()),
        "source": all(source_checks.values()),
        "numerical": numerical_gate,
        "timing": timing_gate,
        "payload": payload_gate,
        "resource": resource_gate,
        "inventory": all(inventory_checks.values()),
        "raw_telemetry": raw_telemetry_binding,
        "canonical_after_numerical_gate": canonical_gate,
    }
    problems = [name for name, value in checks.items() if value is not True]
    return {
        "status": "pass" if not problems else "gate_failed",
        "pass": not problems,
        "problems": problems,
        "checks": checks,
        "scope_checks": scope_checks,
        "source_checks": source_checks,
        "inventory_checks": inventory_checks,
        "numerical_gate_pass": numerical_gate,
        "timing_gate_pass": timing_gate,
        "payload_gate_pass": payload_gate,
        "resource_gate_pass": resource_gate,
        "canonical_gate_pass": canonical_gate,
        "steady_median_apply_seconds": steady_median,
        "steady_rss_span_bytes": rss_span,
        "first_vs_reference_relative_error": first_error,
        "last_vs_reference_relative_error": last_error,
        "retained_components_stable": stable_components,
        "retained_payload_closure": payload_closure,
        "packed_temporary_stable": stable_packed,
        "output_hash_identity": output_hash_identity,
        "telemetry_schema": telemetry_schema,
        "raw_telemetry_binding": raw_telemetry_binding,
        "candidate_seconds_binding": candidate_seconds_binding,
        "error_binding": error_binding,
        "reference_timing_valid": reference_timing_valid,
        "resource_checks": resource_checks,
    }


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


def _h1r3_action_record(
    reference_context,
    candidate_action,
    source,
    *,
    run_dir: Path,
    cfg,
    function_space,
    mpc,
    tolerance: float,
    telemetry_writer: Any | None,
    progress_writer: Any | None = None,
    progress_started: float | None = None,
    progress_rank: int | None = None,
    progress_cell_count: int | None = None,
    progress_local_rows: int | None = None,
    progress_global_rows: int | None = None,
) -> dict[str, Any]:
    """Measure the fixed twelve-apply H1R.3.0 warm sequence."""

    import numpy as np
    from mpi4py import MPI
    from src.solvers.hcurl_canonical_vector_dolfinx import (
        iter_canonical_full_fe_dual_packets,
    )

    label = H1R3_SOURCE_LABEL
    source_definition = _source_definition(label, cfg)
    root_pid = _h1r3_read_root_pid(run_dir)
    reference_output = source.duplicate()
    candidate_first = source.duplicate()
    difference = source.duplicate()
    try:
        reference_start = time.perf_counter()
        reference_context.mult(None, source, reference_output)
        reference_seconds = time.perf_counter() - reference_start
        reference_norm = max(reference_output.norm(), 1.0e-30)
        telemetry: list[dict[str, Any]] = []
        candidate_seconds: list[float] = []
        first_error: float | None = None
        last_error: float | None = None
        first_output_sha256: str | None = None
        for apply_index in range(1, H1R3_CANDIDATE_APPLY_COUNT + 1):
            if progress_writer is not None:
                _emit_h1r_progress(
                    progress_writer,
                    event=(
                        "candidate_apply_1_started"
                        if apply_index == 1
                        else "candidate_apply_2_started"
                    ),
                    worker_started=float(progress_started),
                    rank=int(progress_rank),
                    source_label=label,
                    apply_count=apply_index,
                    cell_count=progress_cell_count,
                    local_rows=progress_local_rows,
                    global_rows=progress_global_rows,
                )
            apply_start = time.perf_counter()
            output = candidate_action.mult(source)
            elapsed = time.perf_counter() - apply_start
            candidate_seconds.append(float(elapsed))
            values = np.asarray(output.getArray(readonly=True))
            output_sha256 = _h1r3_output_sha256(values)
            if apply_index == 1:
                _h1r3_copy_first_output(output, candidate_first)
                first_output_sha256 = output_sha256
            bitwise_equal = bool(
                apply_index == 1
                or np.array_equal(
                    candidate_first.getArray(readonly=True), values
                )
            )
            local_finite = bool(np.all(np.isfinite(values)))
            finite = bool(
                function_space.mesh.comm.allreduce(local_finite, op=MPI.LAND)
            )
            error = None
            if apply_index in (1, H1R3_CANDIDATE_APPLY_COUNT):
                output.copy(result=difference)
                difference.axpy(-1.0, reference_output)
                error = float(difference.norm() / reference_norm)
                if apply_index == 1:
                    first_error = error
                else:
                    last_error = error
            audit = dict(candidate_action.audit)
            components = dict(audit["retained_numeric_payload_components"])
            memory = _h1r3_process_tree_memory(root_pid, os.getpid())
            record = {
                "schema": "task037.candidate_h.h1r3.apply_telemetry.v1",
                "apply_index": apply_index,
                "seconds": float(elapsed),
                "process_tree_worker_pid": int(os.getpid()),
                **memory,
                "retained_numeric_payload_components": components,
                "retained_numeric_payload_local_bytes": int(
                    audit["retained_numeric_payload_local_bytes"]
                ),
                "retained_numeric_payload_global_sum_bytes": int(
                    audit["retained_numeric_payload_global_sum_bytes"]
                ),
                "retained_numeric_payload_global_max_bytes": int(
                    audit["retained_numeric_payload_global_max_bytes"]
                ),
                "packed_temporary_bytes": int(
                    audit["per_apply_bounded_temporary_bytes"]
                ),
                "output_sha256": output_sha256,
                "finite": finite,
                "bitwise_equal_to_first": bitwise_equal,
                "reference_relative_error": error,
            }
            telemetry.append(record)
            if telemetry_writer is not None:
                telemetry_writer.write(
                    json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
                )
                telemetry_writer.flush()
            if progress_writer is not None:
                _emit_h1r_progress(
                    progress_writer,
                    event=(
                        "candidate_apply_1_ready"
                        if apply_index == 1
                        else "candidate_apply_2_ready"
                    ),
                    worker_started=float(progress_started),
                    rank=int(progress_rank),
                    source_label=label,
                    apply_count=apply_index,
                    cell_count=progress_cell_count,
                    local_rows=progress_local_rows,
                    global_rows=progress_global_rows,
                )

        candidate_audit = dict(candidate_action.audit)
        candidate_audit["retained_numeric_payload_components"] = dict(
            candidate_action.audit["retained_numeric_payload_components"]
        )
        measurement = {
            "label": label,
            "kind": "physical_coordinate_analytic_primal",
            "iteration": None,
            "source_definition": source_definition,
            "source_definition_sha256": source_definition["definition_sha256"],
            "reference_apply_count": H1R3_REFERENCE_APPLY_COUNT,
            "candidate_apply_count": H1R3_CANDIDATE_APPLY_COUNT,
            "reference_apply_seconds": float(reference_seconds),
            "candidate_apply_seconds": candidate_seconds,
            "first_vs_reference_relative_error": first_error,
            "last_vs_reference_relative_error": last_error,
            "canonical_export": False,
            "canonical_export_count": 0,
            "candidate_manifest": None,
        }
        numerical_scope = _h1r3_scope()
        numerical_scope.update(
            {
                "global_rows": candidate_audit["global_rows"],
                "constraint_count": candidate_audit["constraint_count"],
            }
        )
        numerical_gate = _evaluate_h1r3_warm_worker_qualification(
            measurement,
            candidate_audit,
            telemetry,
            scope=numerical_scope,
        )["numerical_gate_pass"]
        if numerical_gate:
            if progress_writer is not None:
                _emit_h1r_progress(
                    progress_writer,
                    event="canonical_export_started",
                    worker_started=float(progress_started),
                    rank=int(progress_rank),
                    source_label=label,
                    apply_count=H1R3_CANDIDATE_APPLY_COUNT,
                    cell_count=progress_cell_count,
                    local_rows=progress_local_rows,
                    global_rows=progress_global_rows,
                )
            rank = function_space.mesh.comm.rank
            source_dir = run_dir / "canonical" / label
            source_dir.mkdir(parents=True, exist_ok=True)
            candidate_metadata = write_canonical_packet_shard(
                source_dir / f"candidate_rank{rank}.jsonl",
                iter_canonical_full_fe_dual_packets(
                    function_space,
                    mpc,
                    candidate_action.output_vector,
                    geometry_tolerance=tolerance,
                ),
            )
            shard_metadata = function_space.mesh.comm.gather(
                candidate_metadata, root=0
            )
            candidate_manifest_data = None
            if rank == 0:
                candidate_manifest_path = source_dir / "candidate_manifest.json"
                candidate_manifest = canonical_shard_manifest(
                    role="full_fe_dual",
                    mpi_size=function_space.mesh.comm.size,
                    shard_metadata=shard_metadata,
                    extractor_audit={
                        "source": label,
                        "method": "H1R3-direct-rank-one-MPC",
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
            candidate_manifest_data = function_space.mesh.comm.bcast(
                candidate_manifest_data, root=0
            )
            measurement["canonical_export"] = True
            measurement["canonical_export_count"] = 1
            measurement["candidate_manifest"] = candidate_manifest_data
            if progress_writer is not None:
                _emit_h1r_progress(
                    progress_writer,
                    event="canonical_export_ready",
                    worker_started=float(progress_started),
                    rank=int(progress_rank),
                    source_label=label,
                    apply_count=H1R3_CANDIDATE_APPLY_COUNT,
                    cell_count=progress_cell_count,
                    local_rows=progress_local_rows,
                    global_rows=progress_global_rows,
                )
        return {
            "measurement": measurement,
            "telemetry": telemetry,
            "candidate_audit": candidate_audit,
            "first_output_sha256": first_output_sha256,
        }
    finally:
        difference.destroy()
        candidate_first.destroy()
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
    canonical_method: str = "H1R2-direct-rank-one-MPC",
    timing_global_max: bool = False,
    canonical_export_enabled: bool = True,
) -> dict[str, Any]:
    """Measure one fixed H1R.2 source and export only after numeric gates."""

    import numpy as np
    from mpi4py import MPI
    from src.solvers.hcurl_canonical_vector_dolfinx import (
        iter_canonical_full_fe_dual_packets,
    )

    label = H1R2_SOURCE_LABEL
    source_definition = _source_definition(label, cfg)
    comm = function_space.mesh.comm
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
        reference_elapsed = time.perf_counter() - reference_started
        reference_seconds = (
            float(comm.allreduce(reference_elapsed, op=MPI.MAX))
            if timing_global_max
            else reference_elapsed
        )
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
        candidate_elapsed = time.perf_counter() - candidate_started
        candidate_seconds = (
            float(comm.allreduce(candidate_elapsed, op=MPI.MAX))
            if timing_global_max
            else candidate_elapsed
        )
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
        candidate_repeat_elapsed = time.perf_counter() - candidate_repeat_started
        candidate_repeat_seconds = (
            float(comm.allreduce(candidate_repeat_elapsed, op=MPI.MAX))
            if timing_global_max
            else candidate_repeat_elapsed
        )
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
        finite = bool(comm.allreduce(local_finite, op=MPI.LAND))
        deterministic = bool(comm.allreduce(candidate_repeat_equal, op=MPI.LAND))
        numeric_gate = _h1r2_numerical_gate(
            float(relative_error), finite, deterministic
        )

        candidate_manifest_data = None
        if numeric_gate and canonical_export_enabled:
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
                        "method": canonical_method,
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
            "timing_reduction": (
                "mpi_max" if timing_global_max else "rank_local"
            ),
            "finite": finite,
            "deterministic": deterministic,
            "reference_vs_candidate_relative_error": float(relative_error),
            "canonical_export": bool(numeric_gate and canonical_export_enabled),
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
    from src.geometry.mesh_builder_3d import build_airbox_mesh_3d, stage4_axis_plan
    from src.solvers.common_3d_forms import _build_variational_forms
    from src.solvers.common_3d_solve import _create_nedelec_space
    from src.solvers.fullspace_matrix_free_hcurl import (
        build_task037_extra_candidate_h_fullspace_action,
    )
    from src.solvers.mpc_form_action import MpcFormActionContext

    if mode not in {
        "h1_2",
        "h1r2",
        "h1r3_warm",
        "h1r3_mpi2",
        "h1r3_h5",
    }:
        raise ValueError(f"unsupported Candidate-H worker mode: {mode}")
    h1r2 = mode == "h1r2"
    h1r3 = mode == "h1r3_warm"
    h1r31 = mode == "h1r3_mpi2"
    h1r32 = mode == "h1r3_h5"
    h1r2_or_h1r3 = h1r2 or h1r3 or h1r31 or h1r32
    if h1r2_or_h1r3:
        from src.solvers.hcurl_rank_one_mpc_action import (
            build_task037_extra_h1r2_mpc_action,
        )

    comm = MPI.COMM_WORLD
    progress_writer = sys.stdout
    progress_cell_count: int | None = None
    progress_local_rows: int | None = None
    progress_global_rows: int | None = None
    h1r3_source_at_start = (
        _inspect_candidate_source() if h1r3 or h1r31 or h1r32 else None
    )
    telemetry_writer = None

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

    cfg = target_stage4_config(degree=6, h_nm=5.0 if h1r32 else 10.0)
    if cfg.stage4_boundary_model != "dtn_port":
        raise RuntimeError("Candidate-H requires the frozen dtn_port configuration identity")
    if cfg.divergence_penalty != 0.0:
        raise RuntimeError("Candidate-H H1.2 excludes divergence penalty")
    if comm.rank == 0:
        run_dir.mkdir(parents=True, exist_ok=True)
    comm.barrier()
    emit_progress("mesh_build_started")
    mesh_data = build_airbox_mesh_3d(cfg, run_dir / "mesh")
    axis_cell_counts = None
    if h1r32:
        axis_plan = stage4_axis_plan(cfg, comm.size)
        axis_cell_counts = tuple(
            len(getattr(axis_plan, f"{axis_name}_values")) - 1
            for axis_name in ("x", "y", "z")
        )
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
    if h1r2_or_h1r3:
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
    if h1r32:
        emit_progress("form_compile_started")
    emit_progress("candidate_build_started")
    if h1r2_or_h1r3:
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
    if h1r32:
        emit_progress("form_compile_ready")
    try:
        if h1r3 and comm.rank == 0:
            telemetry_writer = (run_dir / H1R3_TELEMETRY_FILE).open(
                "w", encoding="utf-8"
            )
        source_results = []
        h1r3_telemetry: list[dict[str, Any]] = []
        source_labels = (
            (H1R2_SOURCE_LABEL,) if h1r2_or_h1r3 else tuple(SOURCE_DEFINITIONS)
        )
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
                if h1r3:
                    source_record = _h1r3_action_record(
                        reference,
                        candidate,
                        source,
                        run_dir=run_dir,
                        cfg=cfg,
                        function_space=function_space,
                        mpc=floquet.mpc,
                        tolerance=tolerance,
                        telemetry_writer=telemetry_writer,
                        progress_writer=progress_writer,
                        progress_started=worker_started,
                        progress_rank=comm.rank,
                        progress_cell_count=progress_cell_count,
                        progress_local_rows=progress_local_rows,
                        progress_global_rows=progress_global_rows,
                    )
                    source_results.append(source_record["measurement"])
                    h1r3_telemetry = source_record["telemetry"]
                elif h1r31:
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
                            canonical_method="H1R3.1-direct-rank-one-MPC",
                            timing_global_max=True,
                        )
                    )
                elif h1r32:
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
                            canonical_method="H1R3.2-disabled-canonical",
                            timing_global_max=True,
                            canonical_export_enabled=False,
                        )
                    )
                elif h1r2:
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
        if telemetry_writer is not None:
            telemetry_writer.close()
            telemetry_writer = None
        candidate_audit = dict(candidate.audit)
        if h1r2_or_h1r3:
            candidate_audit["retained_numeric_payload_components"] = dict(
                candidate.audit["retained_numeric_payload_components"]
            )
        else:
            candidate_audit["candidate_owned_numeric_payload_components"] = dict(
                candidate.audit["candidate_owned_numeric_payload_components"]
            )
        global_rows = int(candidate.audit["global_rows"])
        constraint_count = int(floquet.num_constraints)
        global_cells = (
            int(
                mesh_data.mesh.topology.index_map(
                    mesh_data.mesh.topology.dim
                ).size_global
            )
            if h1r32
            else None
        )
        runtime_identity = _h1r2_runtime_identity() if h1r2_or_h1r3 else None
        h1r3_source_at_end = (
            _inspect_candidate_source() if h1r3 or h1r31 or h1r32 else None
        )
        emit_progress("worker_summary_started")
        if comm.rank == 0:
            if h1r3:
                scope = _h1r3_scope()
                scope.update(
                    {
                        "global_rows": global_rows,
                        "constraint_count": constraint_count,
                    }
                )
                qualification = _evaluate_h1r3_warm_worker_qualification(
                    source_results[0],
                    candidate_audit,
                    h1r3_telemetry,
                    scope=scope,
                )
                summary = {
                    "schema": "task037.candidate_h.h1r3.warm.worker.v1",
                    "runtime_identity": runtime_identity,
                    "status": (
                        "pass" if qualification["pass"] else "gate_failed"
                    ),
                    "mpi_size": int(comm.size),
                    "global_rows": global_rows,
                    "constraint_count": constraint_count,
                    "scope": scope,
                    "source_definitions": {
                        H1R3_SOURCE_LABEL: _source_definition(
                            H1R3_SOURCE_LABEL, cfg
                        )
                    },
                    "measurements": source_results,
                    "apply_telemetry": {
                        "path": H1R3_TELEMETRY_FILE,
                        **_h1r3_file_metadata(run_dir)[H1R3_TELEMETRY_FILE],
                    },
                    "candidate_action_audit": candidate_audit,
                    "reference_action": {
                        "type": "MpcFormActionContext",
                        "same_worker": True,
                        "apply_count": int(reference.apply_count),
                        "global_matrix_materialized": False,
                    },
                    "source_at_start": h1r3_source_at_start.as_jsonable(),
                    "source_at_end": h1r3_source_at_end.as_jsonable(),
                    "qualification": qualification,
                }
            elif h1r31:
                scope = _h1r31_scope(
                    global_rows=global_rows,
                    constraint_count=constraint_count,
                )
                qualification = _evaluate_h1r31_worker_qualification(
                    source_results[0],
                    candidate_audit,
                    scope=scope,
                )
                summary = {
                    "schema": "task037.candidate_h.h1r3.mpi2.worker.v1",
                    "runtime_identity": runtime_identity,
                    "status": (
                        "pass" if qualification["pass"] else "gate_failed"
                    ),
                    "mpi_size": int(comm.size),
                    "global_rows": global_rows,
                    "constraint_count": constraint_count,
                    "scope": scope,
                    "source_definitions": {
                        H1R31_SOURCE_LABEL: _source_definition(
                            H1R31_SOURCE_LABEL, cfg
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
                    "qualification": qualification,
                    "source_at_start": h1r3_source_at_start.as_jsonable(),
                    "source_at_end": h1r3_source_at_end.as_jsonable(),
                }
            elif h1r32:
                assert axis_cell_counts is not None
                scope = _h1r32_scope(
                    global_rows=global_rows,
                    constraint_count=constraint_count,
                    global_cells=int(global_cells),
                    axis_cell_counts=axis_cell_counts,
                )
                qualification = _evaluate_h1r32_worker_qualification(
                    source_results[0],
                    candidate_audit,
                    scope=scope,
                )
                summary = {
                    "schema": "task037.candidate_h.h1r3.h5.worker.v1",
                    "runtime_identity": runtime_identity,
                    "status": (
                        "pass" if qualification["pass"] else "gate_failed"
                    ),
                    "mpi_size": int(comm.size),
                    "global_rows": global_rows,
                    "constraint_count": constraint_count,
                    "global_cells": int(global_cells),
                    "axis_cell_counts": list(axis_cell_counts),
                    "scope": scope,
                    "source_definitions": {
                        H1R32_SOURCE_LABEL: _source_definition(
                            H1R32_SOURCE_LABEL, cfg
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
                    "qualification": qualification,
                    "source_at_start": h1r3_source_at_start.as_jsonable(),
                    "source_at_end": h1r3_source_at_end.as_jsonable(),
                }
            elif h1r2:
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
            if h1r2 or h1r3 or h1r31 or h1r32:
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
        if telemetry_writer is not None:
            telemetry_writer.close()
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
    if mode == "h1r3_warm":
        return [
            "mpiexec",
            "-n",
            "1",
            sys.executable,
            "-m",
            "benchmarks.run_task037_extra_candidate_h",
            "h1r3-warm-worker",
            "--run-dir",
            str(Path(args.run_dir).resolve()),
        ]
    if mode == "h1r3_mpi2":
        return [
            "mpiexec",
            "-n",
            "2",
            sys.executable,
            "-m",
            "benchmarks.run_task037_extra_candidate_h",
            "h1r3-mpi2-worker",
            "--run-dir",
            str(Path(args.run_dir).resolve()),
        ]
    if mode == "h1r3_h5":
        return [
            "mpiexec",
            "-n",
            "1",
            sys.executable,
            "-m",
            "benchmarks.run_task037_extra_candidate_h",
            "h1r3-h5-worker",
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
    if mode not in {
        "h1_2",
        "h1r2",
        "h1r3_warm",
        "h1r3_mpi2",
        "h1r3_h5",
    }:
        raise ValueError(f"unsupported Candidate-H watchdog mode: {mode}")
    h1r2 = mode == "h1r2"
    h1r3 = mode == "h1r3_warm"
    h1r31 = mode == "h1r3_mpi2"
    h1r32 = mode == "h1r3_h5"
    timeout_seconds = (
        H1R3_TIMEOUT_SECONDS
        if h1r3
        else H1R31_TIMEOUT_SECONDS
        if h1r31
        else H1R32_TIMEOUT_SECONDS
        if h1r32
        else H1R2_TIMEOUT_SECONDS
        if h1r2
        else H1_TIMEOUT_SECONDS
    )
    poll_seconds = H1_POLL_SECONDS
    rss_limit_bytes = (
        H1R3_PEAK_LIMIT_BYTES
        if h1r3
        else H1R31_PEAK_LIMIT_BYTES
        if h1r31
        else H1R32_PEAK_LIMIT_BYTES
        if h1r32
        else H1_RSS_LIMIT_BYTES
    )
    run_dir = Path(args.run_dir).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = run_dir / "worker_stdout.txt"
    timeline_path = run_dir / "watchdog_timeline.jsonl"
    command = _watchdog_command(args, mode=mode)
    watchdog_runtime_identity = (
        _h1r2_runtime_identity()
        if h1r2 or h1r3 or h1r31 or h1r32
        else None
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
            if h1r2 or h1r3 or h1r31 or h1r32
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
                if h1r3 or h1r32:
                    root_pid_path = (
                        run_dir / H1R32_ROOT_PID_FILE
                        if h1r32
                        else run_dir / H1R3_ROOT_PID_FILE
                    )
                    root_pid_path.write_text(
                        json.dumps(
                            {
                                "schema": (
                                    "task037.candidate_h.h1r3.h5.root_pid.v1"
                                    if h1r32
                                    else "task037.candidate_h.h1r3.root_pid.v1"
                                ),
                                "root_pid": int(process.pid),
                            },
                            sort_keys=True,
                        )
                        + "\n",
                        encoding="utf-8",
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
                if h1r2 or h1r3 or h1r31 or h1r32:
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
                    controlled_stop = (
                        "process_tree_rss_over_0.45_GiB"
                        if h1r3
                        else "process_tree_rss_over_0.75_GiB"
                        if h1r31
                        else "process_tree_rss_over_0.75_GiB"
                        if h1r32
                        else "process_tree_rss_over_1.25_GiB"
                    )
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
        if (h1r2 or h1r3 or h1r31 or h1r32) and worker_summary is not None
        else None
    )
    worker_runtime_identity_match = bool(
        (h1r2 or h1r3 or h1r31 or h1r32)
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
        if h1r2 or h1r3 or h1r31 or h1r32
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
    elif h1r3 and worker_summary is not None:
        if worker_summary.get("schema") == "task037.candidate_h.h1r3.warm.worker.v1":
            worker_qualification_recomputed = _evaluate_h1r3_warm_worker_qualification(
                (worker_summary.get("measurements") or [{}])[0],
                worker_summary.get("candidate_action_audit", {}),
                _h1r3_read_telemetry(run_dir),
                scope=worker_summary.get("scope", {}),
            )
    elif h1r31 and worker_summary is not None:
        if worker_summary.get("schema") == "task037.candidate_h.h1r3.mpi2.worker.v1":
            worker_qualification_recomputed = _evaluate_h1r31_worker_qualification(
                (worker_summary.get("measurements") or [{}])[0],
                worker_summary.get("candidate_action_audit", {}),
                scope=worker_summary.get("scope", {}),
            )
    elif h1r32 and worker_summary is not None:
        if worker_summary.get("schema") == "task037.candidate_h.h1r3.h5.worker.v1":
            worker_qualification_recomputed = _evaluate_h1r32_worker_qualification(
                (worker_summary.get("measurements") or [{}])[0],
                worker_summary.get("candidate_action_audit", {}),
                scope=worker_summary.get("scope", {}),
            )
    worker_qualification_pass = bool(
        worker_summary is not None
        and (
            worker_qualification_recomputed["pass"]
            if (h1r2 or h1r3 or h1r31 or h1r32)
            and worker_qualification_recomputed is not None
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
    worker_process_tree_all_ranks = bool(
        live_samples
        and all(
            isinstance(sample.get("live_worker_process_count"), int)
            and not isinstance(sample.get("live_worker_process_count"), bool)
            and sample.get("live_worker_process_count") >= 0
            for sample in live_samples
        )
        and any(
            sample.get("live_worker_process_count") >= 3
            for sample in live_samples
        )
        and any(
            int(sample.get("worker_tree_rss_sum_bytes", -1))
            == peak_process_tree_rss
            and sample.get("live_worker_process_count") >= 3
            for sample in live_samples
        )
    )
    watchdog_pass = bool(
        controlled_stop is None
        and return_code == 0
        and worker_summary is not None
        and worker_qualification_pass
        and source_stable_clean
        and live_authority_readable
        and worker_swap_zero
        and (not h1r31 or worker_process_tree_all_ranks)
        and peak_process_tree_rss <= rss_limit_bytes
        and (
            not (h1r2 or h1r3 or h1r31 or h1r32)
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
                and (
                    not (h1r3 or h1r31 or h1r32)
                    or worker_summary.get("status") == "pass"
                )
            )
        )
    )
    wall_seconds = float(time.perf_counter() - started)
    if h1r3:
        h1r3_artifacts = _h1r3_file_metadata(run_dir)
        if worker_summary is not None:
            h1r3_measurement = (worker_summary.get("measurements") or [{}])[0]
            h1r3_manifest = h1r3_measurement.get("candidate_manifest")
            if isinstance(h1r3_manifest, dict) and h1r3_manifest.get("path"):
                manifest_path = str(h1r3_manifest["path"])
                h1r3_artifacts[manifest_path] = _h1r3_path_metadata(
                    run_dir / manifest_path, manifest_path
                )
        watchdog_summary = {
            "schema": "task037.candidate_h.h1r3.warm.watchdog.v1",
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
            "raw_artifacts": h1r3_artifacts,
        }
        watchdog_summary = attach_evidence_sha256(watchdog_summary)
    elif h1r31:
        h1r31_measurement = (
            (worker_summary.get("measurements") or [{}])[0]
            if worker_summary is not None
            else {}
        )
        h1r31_manifest = h1r31_measurement.get("candidate_manifest")
        h1r31_manifest_path = (
            str(h1r31_manifest["path"])
            if isinstance(h1r31_manifest, dict) and h1r31_manifest.get("path")
            else None
        )
        h1r31_artifacts = _h1r31_file_metadata(
            run_dir, h1r31_manifest_path
        )
        watchdog_summary = {
            "schema": "task037.candidate_h.h1r3.mpi2.watchdog.v1",
            "command": command,
            "mpi_size": 2,
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
            "worker_process_tree_all_ranks": worker_process_tree_all_ranks,
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
            "global_rows": (
                worker_summary.get("global_rows")
                if worker_summary is not None
                else None
            ),
            "constraint_count": (
                worker_summary.get("constraint_count")
                if worker_summary is not None
                else None
            ),
            "raw_artifacts": h1r31_artifacts,
        }
        watchdog_summary = attach_evidence_sha256(watchdog_summary)
    elif h1r32:
        h1r32_worker = worker_summary or {}
        h1r32_artifacts = _h1r32_file_metadata(run_dir)
        watchdog_summary = {
            "schema": "task037.candidate_h.h1r3.h5.watchdog.v1",
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
            "worker_summary_status": (
                None if worker_summary is None else worker_summary.get("status")
            ),
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
            "global_rows": h1r32_worker.get("global_rows"),
            "constraint_count": h1r32_worker.get("constraint_count"),
            "global_cells": h1r32_worker.get("global_cells"),
            "axis_cell_counts": h1r32_worker.get("axis_cell_counts"),
            "raw_artifacts": h1r32_artifacts,
        }
        watchdog_summary = attach_evidence_sha256(watchdog_summary)
    elif h1r2:
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


def _h1r3_check_raw(run_dir: Path) -> dict[str, Any]:
    run_dir = Path(run_dir).resolve()
    watchdog = json.loads(
        (run_dir / "watchdog_summary.json").read_text(encoding="utf-8")
    )
    worker = json.loads(
        (run_dir / "run_summary.json").read_text(encoding="utf-8")
    )
    telemetry = _h1r3_read_telemetry(run_dir)
    root_record = json.loads(
        (run_dir / H1R3_ROOT_PID_FILE).read_text(encoding="utf-8")
    )
    root_pid = root_record.get("root_pid")
    telemetry_root_pids = [
        item.get("process_tree_root_pid") for item in telemetry
    ]
    root_pid_valid = (
        isinstance(root_pid, int)
        and not isinstance(root_pid, bool)
        and root_pid > 0
    )
    telemetry_root_pids_valid = bool(
        len(telemetry_root_pids) == H1R3_CANDIDATE_APPLY_COUNT
        and all(
            isinstance(value, int)
            and not isinstance(value, bool)
            and value > 0
            for value in telemetry_root_pids
        )
    )
    root_pid_checks = {
        "schema": root_record.get("schema")
        == "task037.candidate_h.h1r3.root_pid.v1",
        "root_pid_positive": root_pid_valid,
        "telemetry_root_pid_consistent": bool(
            root_pid_valid
            and telemetry_root_pids_valid
            and all(value == root_pid for value in telemetry_root_pids)
        ),
    }
    timeline = [
        json.loads(line)
        for line in (run_dir / "watchdog_timeline.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    expected_artifacts = _h1r3_file_metadata(run_dir)
    measurement = (worker.get("measurements") or [{}])[0]
    manifest_record = measurement.get("candidate_manifest")
    manifest_relative_path = (
        manifest_record.get("path")
        if isinstance(manifest_record, dict)
        else None
    )
    if manifest_relative_path:
        expected_artifacts[manifest_relative_path] = _h1r3_path_metadata(
            run_dir / manifest_relative_path, manifest_relative_path
        )
    recorded_artifacts = watchdog.get("raw_artifacts", {})
    raw_artifact_checks = {
        name: isinstance(recorded_artifacts, dict)
        and recorded_artifacts.get(name) == metadata
        for name, metadata in expected_artifacts.items()
    }
    actual_file_artifacts = dict(expected_artifacts)
    actual_file_artifacts["watchdog_summary.json"] = _h1r3_path_metadata(
        run_dir / "watchdog_summary.json", "watchdog_summary.json"
    )
    source_start = watchdog.get("source_at_start", {})
    source_end = watchdog.get("source_at_end", {})
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
    worker_source_start = worker.get("source_at_start", {})
    worker_source_end = worker.get("source_at_end", {})
    worker_source_checks = {
        "start_clean": _h1r2_source_is_clean(worker_source_start),
        "end_clean": _h1r2_source_is_clean(worker_source_end),
        "same_commit": (
            _h1r2_source_is_clean(worker_source_start)
            and _h1r2_source_is_clean(worker_source_end)
            and worker_source_start.get("source_commit_full_sha")
            == worker_source_end.get("source_commit_full_sha")
        ),
        "matches_watchdog": (
            worker_source_start.get("source_commit_full_sha")
            == source_start.get("source_commit_full_sha")
            and worker_source_end.get("source_commit_full_sha")
            == source_end.get("source_commit_full_sha")
        ),
    }
    runtime_watchdog = watchdog.get("watchdog_runtime_identity")
    runtime_worker = worker.get("runtime_identity")
    command = watchdog.get("command")
    expected_command = _watchdog_command(
        SimpleNamespace(run_dir=run_dir), mode="h1r3_warm"
    )
    runtime_checks = {
        "watchdog_values": _h1r2_runtime_identity_is_valid(runtime_watchdog),
        "worker_values": _h1r2_runtime_identity_is_valid(runtime_worker),
        "identical": runtime_worker == runtime_watchdog,
        "command_python_executable": (
            isinstance(command, list)
            and len(command) > 3
            and isinstance(runtime_watchdog, dict)
            and command[3] == runtime_watchdog.get("sys.executable")
        ),
        "recorded_match": watchdog.get("worker_runtime_identity_match") is True,
    }
    live_timeline = [item for item in timeline if item.get("worker_alive") is True]
    timeline_peak = max(
        (
            int(item["worker_tree_rss_sum_bytes"])
            for item in live_timeline
            if isinstance(item.get("worker_tree_rss_sum_bytes"), int)
        ),
        default=None,
    )
    timeline_swap = max(
        (
            int(_live_sample_swap(item))
            for item in live_timeline
            if _live_sample_swap(item) is not None
        ),
        default=None,
    )
    timeline_checks = {
        "live_samples_present": bool(live_timeline),
        "live_samples_readable": bool(
            live_timeline
            and all(_live_sample_is_readable(item) for item in live_timeline)
        ),
        "peak_recomputed": watchdog.get("peak_process_tree_rss_bytes")
        == timeline_peak,
        "swap_recomputed": watchdog.get("worker_process_tree_swap_bytes")
        == timeline_swap,
        "swap_zero": timeline_swap == 0,
        "peak_limit": isinstance(timeline_peak, int)
        and timeline_peak <= H1R3_PEAK_LIMIT_BYTES,
        "live_sample_count": watchdog.get("worker_live_sample_count")
        == len(live_timeline),
    }
    fresh_qualification = _evaluate_h1r3_warm_worker_qualification(
        measurement,
        worker.get("candidate_action_audit", {}),
        telemetry,
        scope=worker.get("scope", {}),
    )
    worker_checks = {
        "schema": worker.get("schema")
        == "task037.candidate_h.h1r3.warm.worker.v1",
        "status_pass": worker.get("status") == "pass",
        "qualification_status": worker.get("qualification", {}).get("status")
        == fresh_qualification.get("status"),
        "qualification_pass": worker.get("qualification", {}).get("pass")
        == fresh_qualification.get("pass"),
        "fresh_pass": fresh_qualification.get("pass") is True,
        "mpi_size": worker.get("mpi_size") == 1,
        "scope_rows": worker.get("global_rows") == worker.get("scope", {}).get(
            "global_rows"
        ),
        "scope_constraints": worker.get("constraint_count")
        == worker.get("scope", {}).get("constraint_count"),
        "source_definition": worker.get("source_definitions", {}).get(
            H1R3_SOURCE_LABEL
        )
        == measurement.get("source_definition"),
        "reference_action": worker.get("reference_action", {}).get("type")
        == "MpcFormActionContext"
        and worker.get("reference_action", {}).get("same_worker") is True
        and worker.get("reference_action", {}).get("apply_count")
        == H1R3_REFERENCE_APPLY_COUNT
        and worker.get("reference_action", {}).get("global_matrix_materialized")
        is False,
        "telemetry_metadata": worker.get("apply_telemetry")
        == {
            "path": H1R3_TELEMETRY_FILE,
            **expected_artifacts.get(H1R3_TELEMETRY_FILE, {}),
        },
    }
    watchdog_checks = {
        "schema": watchdog.get("schema")
        == "task037.candidate_h.h1r3.warm.watchdog.v1",
        "evidence_sha256": evidence_sha256_is_valid(watchdog),
        "command": command == expected_command,
        "mpi_size": watchdog.get("mpi_size") == 1,
        "timeout_seconds": watchdog.get("timeout_seconds")
        == H1R3_TIMEOUT_SECONDS,
        "poll_interval_seconds": watchdog.get("poll_interval_seconds")
        == H1_POLL_SECONDS,
        "rss_limit_bytes": watchdog.get("rss_limit_bytes")
        == H1R3_PEAK_LIMIT_BYTES,
        "status": watchdog.get("status") == "pass",
        "return_code": watchdog.get("return_code") == 0,
        "controlled_stop": watchdog.get("controlled_stop") is None,
        "completion": isinstance(watchdog.get("completion_elapsed_seconds"), (int, float))
        and math.isfinite(float(watchdog["completion_elapsed_seconds"]))
        and watchdog["completion_elapsed_seconds"] <= H1R3_TIMEOUT_SECONDS,
        "wall_diagnostic": isinstance(watchdog.get("wall_seconds"), (int, float))
        and math.isfinite(float(watchdog["wall_seconds"]))
        and watchdog["wall_seconds"] >= 0.0,
        "worker_summary_present": watchdog.get("worker_summary_present") is True,
        "worker_summary_status": watchdog.get("worker_summary_status")
        == worker.get("status"),
        "worker_summary_evidence_valid": watchdog.get(
            "worker_summary_evidence_sha256_valid"
        )
        is True
        and evidence_sha256_is_valid(worker),
        "worker_qualification_pass": watchdog.get("worker_qualification_pass")
        == fresh_qualification.get("pass"),
        "worker_recomputation": watchdog.get("worker_qualification_recomputed")
        == fresh_qualification,
        "source_stable_clean": watchdog.get("source_stable_clean") is True,
        "termination": watchdog.get("termination", {}).get("requested") is False,
    }
    canonical_checks: dict[str, bool]
    expected_packet_count = int(worker.get("scope", {}).get("global_rows", -1)) - int(
        worker.get("scope", {}).get("constraint_count", -1)
    )
    if fresh_qualification["numerical_gate_pass"]:
        manifest = read_canonical_manifest(
            run_dir / str(manifest_relative_path),
            expected_sha256=str(manifest_record["sha256"]),
        )
        extractor = manifest.get("extractor_audit", {})
        canonical_checks = {
            "export_after_numerical_gate": measurement.get("canonical_export") is True,
            "export_count": measurement.get("canonical_export_count") == 1,
            "path": manifest_relative_path
            == f"canonical/{H1R3_SOURCE_LABEL}/candidate_manifest.json",
            "role": manifest.get("role") == "full_fe_dual",
            "mpi_size": manifest.get("mpi_size") == 1,
            "dtype": manifest.get("dtype") == "complex128",
            "packet_count": manifest.get("global_summed_packet_count")
            == expected_packet_count,
            "record_packet_count": manifest_record.get("packet_count")
            == expected_packet_count,
            "duplicate_count": manifest.get("summed_local_duplicate_count") == 0,
            "extractor_source": extractor.get("source") == H1R3_SOURCE_LABEL,
            "extractor_method": extractor.get("method")
            == "H1R3-direct-rank-one-MPC",
        }
    else:
        canonical_checks = {
            "not_exported_after_failed_numerical_gate": measurement.get(
                "canonical_export"
            ) is False
            and measurement.get("canonical_export_count") == 0
            and manifest_record is None
        }
    checks = {
        **{f"raw.{name}": value for name, value in raw_artifact_checks.items()},
        **{f"source.{name}": value for name, value in source_checks.items()},
        **{
            f"worker_source.{name}": value
            for name, value in worker_source_checks.items()
        },
        **{f"root_pid.{name}": value for name, value in root_pid_checks.items()},
        **{f"runtime.{name}": value for name, value in runtime_checks.items()},
        **{f"timeline.{name}": value for name, value in timeline_checks.items()},
        **{f"worker.{name}": value for name, value in worker_checks.items()},
        **{f"watchdog.{name}": value for name, value in watchdog_checks.items()},
        **{f"canonical.{name}": value for name, value in canonical_checks.items()},
    }
    problems = [name for name, value in checks.items() if value is not True]
    first_telemetry = telemetry[0] if telemetry else {}
    per_apply_telemetry = [
        {
            name: item.get(name)
            for name in (
                "apply_index",
                "seconds",
                "process_tree_rss_bytes",
                "process_tree_pss_bytes",
                "process_tree_uss_bytes",
                "process_tree_swap_bytes",
                "retained_numeric_payload_local_bytes",
                "retained_numeric_payload_global_sum_bytes",
                "retained_numeric_payload_global_max_bytes",
                "packed_temporary_bytes",
                "output_sha256",
                "finite",
                "bitwise_equal_to_first",
                "reference_relative_error",
            )
        }
        for item in telemetry
    ]
    return {
        "schema": "task037.candidate_h.h1r3.warm.compact_check.v1",
        "status": "pass" if not problems else "gate_failed",
        "pass": not problems,
        "checks": checks,
        "raw_artifacts": actual_file_artifacts,
        "raw_evidence_sha256": {
            "worker_summary_bytes": actual_file_artifacts["run_summary.json"][
                "sha256"
            ],
            "watchdog_summary_bytes": actual_file_artifacts[
                "watchdog_summary.json"
            ]["sha256"],
            "telemetry_bytes": actual_file_artifacts[H1R3_TELEMETRY_FILE][
                "sha256"
            ],
            "canonical_manifest_bytes": (
                actual_file_artifacts[manifest_relative_path]["sha256"]
                if manifest_relative_path in actual_file_artifacts
                else None
            ),
        },
        "embedded_evidence_sha256": {
            "worker_summary": worker.get("evidence_sha256"),
            "watchdog_summary": watchdog.get("evidence_sha256"),
        },
        "worker_qualification_recomputed": fresh_qualification,
        "source_identity": {
            "source_commit_full_sha": source_start.get("source_commit_full_sha")
            if source_checks["same_commit"]
            else None,
            "start": source_start,
            "end": source_end,
        },
        "worker_source_identity": {
            "start": worker_source_start,
            "end": worker_source_end,
        },
        "root_pid": {
            "recorded": root_pid,
            "checks": root_pid_checks,
        },
        "runtime_identity": {
            "watchdog": runtime_watchdog,
            "worker": runtime_worker,
            "match": watchdog.get("worker_runtime_identity_match"),
        },
        "measurement": {
            "global_rows": worker.get("scope", {}).get("global_rows"),
            "constraint_count": worker.get("scope", {}).get("constraint_count"),
            "reference_first_apply_seconds": measurement.get(
                "reference_apply_seconds"
            ),
            "candidate_apply_seconds": measurement.get("candidate_apply_seconds"),
            "first_vs_reference_relative_error": measurement.get(
                "first_vs_reference_relative_error"
            ),
            "last_vs_reference_relative_error": measurement.get(
                "last_vs_reference_relative_error"
            ),
            "finite": all(item.get("finite") is True for item in telemetry),
            "deterministic": all(
                item.get("bitwise_equal_to_first") is True for item in telemetry
            ),
            "retained_payload_components": worker.get(
                "candidate_action_audit", {}
            ).get("retained_numeric_payload_components"),
            "retained_payload_local_bytes": worker.get(
                "candidate_action_audit", {}
            ).get("retained_numeric_payload_local_bytes"),
            "retained_payload_global_sum_bytes": first_telemetry.get(
                "retained_numeric_payload_global_sum_bytes"
            ),
            "retained_payload_global_max_bytes": first_telemetry.get(
                "retained_numeric_payload_global_max_bytes"
            ),
            "steady_median_apply_seconds": fresh_qualification.get(
                "steady_median_apply_seconds"
            ),
            "steady_rss_span_bytes": fresh_qualification.get(
                "steady_rss_span_bytes"
            ),
            "per_apply_telemetry": per_apply_telemetry,
            "packed_temporary_bytes": [
                item.get("packed_temporary_bytes") for item in telemetry
            ],
            "canonical_export": measurement.get("canonical_export"),
            "canonical_packet_count": (
                measurement.get("candidate_manifest", {}).get("packet_count")
                if isinstance(measurement.get("candidate_manifest"), dict)
                else None
            ),
        },
        "memory_authority": {
            "completed_process_tree_peak_limit_bytes": H1R3_PEAK_LIMIT_BYTES,
            "completed_process_tree_peak_rss_bytes": timeline_peak,
            "review_v5_peak_gate_pass": all(
                timeline_checks[name]
                for name in ("live_samples_readable", "peak_limit", "swap_zero")
            ),
            "swap_bytes": timeline_swap,
            "completed_elapsed_seconds": watchdog.get(
                "completion_elapsed_seconds"
            ),
            "user_lt_2GB_target_evaluated": timeline_peak is not None,
            "user_lt_2GB_target_pass": (
                None if timeline_peak is None else timeline_peak < 2_000_000_000
            ),
        },
        "scope_boundary": {
            "H1R3.1": "eligible_by_review_v5_if_H1R3.0_pass",
            "H1R3.2": "locked_pending_H1R3.1_pass",
            "H2": "locked",
        },
        "problems": problems,
    }


def run_h1r3_check(run_dir: Path, output: Path) -> int:
    try:
        result = _h1r3_check_raw(Path(run_dir))
    except (OSError, KeyError, TypeError, ValueError, IndexError, AttributeError) as exc:
        result = {
            "schema": "task037.candidate_h.h1r3.warm.compact_check.v1",
            "status": "gate_failed",
            "pass": False,
            "problems": [
                f"controlled_checker_failure:{type(exc).__name__}:{exc}"
            ],
        }
    result = attach_evidence_sha256(result)
    Path(output).write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0 if result["pass"] else 1


def _h1r31_read_historical_authority() -> dict[str, Any]:
    raw_dir = Path(H1R31_HISTORICAL_RAW_DIR).resolve()
    record_path = Path(H1R31_HISTORICAL_RECORD).resolve()
    compact = json.loads(record_path.read_text(encoding="utf-8"))
    raw_watchdog = json.loads(
        (raw_dir / "watchdog_summary.json").read_text(encoding="utf-8")
    )
    raw_worker = json.loads(
        (raw_dir / "run_summary.json").read_text(encoding="utf-8")
    )
    manifest_path = raw_dir / "canonical/seed_17037/candidate_manifest.json"
    manifest = read_canonical_manifest(
        manifest_path, expected_sha256=H1R31_HISTORICAL_MANIFEST_SHA256
    )
    historical_artifacts = {
        "run_summary.json": _h1r3_path_metadata(
            raw_dir / "run_summary.json", "run_summary.json"
        ),
        "watchdog_summary.json": _h1r3_path_metadata(
            raw_dir / "watchdog_summary.json", "watchdog_summary.json"
        ),
        "canonical/seed_17037/candidate_manifest.json": _h1r3_path_metadata(
            manifest_path, "canonical/seed_17037/candidate_manifest.json"
        ),
    }
    recorded_historical_artifacts = compact.get("raw_artifacts")
    historical_artifact_checks = {
        name: (
            isinstance(recorded_historical_artifacts, dict)
            and recorded_historical_artifacts.get(name) == metadata
        )
        for name, metadata in historical_artifacts.items()
    }
    source_start = raw_watchdog["source_at_start"]
    source_end = raw_watchdog["source_at_end"]
    source_valid = bool(
        _h1r2_source_is_clean(source_start)
        and _h1r2_source_is_clean(source_end)
        and source_start["source_commit_full_sha"]
        == H1R31_HISTORICAL_SOURCE_SHA
        and source_end["source_commit_full_sha"]
        == H1R31_HISTORICAL_SOURCE_SHA
    )
    raw_checks = {
        "watchdog_schema": raw_watchdog.get("schema")
        == "task037.candidate_h.h1r2.watchdog.v1",
        "watchdog_status": raw_watchdog.get("status") == "pass",
        "watchdog_return_code": raw_watchdog.get("return_code") == 0,
        "worker_schema": raw_worker.get("schema")
        == "task037.candidate_h.h1r2.worker.v1",
        "worker_status": raw_worker.get("status") == "pass",
        "worker_qualification": raw_worker.get("qualification", {}).get(
            "pass"
        )
        is True,
        "source_clean_and_fixed": source_valid,
        "worker_evidence_sha256": evidence_sha256_is_valid(raw_worker),
        "watchdog_evidence_sha256": evidence_sha256_is_valid(raw_watchdog),
        "raw_artifacts_match_compact": all(historical_artifact_checks.values()),
    }
    compact_source = compact["source_identity"]
    compact_measurement = compact["measurement"]
    compact_checks = {
        "schema": compact.get("schema")
        == "task037.candidate_h.h1r2.compact_check.v1",
        "evidence": evidence_sha256_is_valid(compact),
        "pass": compact.get("status") == "pass"
        and compact.get("pass") is True,
        "raw_run_directory": Path(compact["raw_run_directory"]).resolve()
        == raw_dir,
        "source": compact_source.get("source_commit_full_sha")
        == H1R31_HISTORICAL_SOURCE_SHA,
        "source_clean": _h1r2_source_is_clean(compact_source["start"])
        and _h1r2_source_is_clean(compact_source["end"]),
        "manifest_record": (
            isinstance(recorded_historical_artifacts, dict)
            and recorded_historical_artifacts.get(
                "canonical/seed_17037/candidate_manifest.json", {}
            ).get("sha256")
            == H1R31_HISTORICAL_MANIFEST_SHA256
        ),
        "measurement_packet_count": compact_measurement[
            "canonical_packet_count"
        ]
        == H1R31_PACKET_COUNT,
    }
    manifest_checks = {
        "role": manifest.get("role") == "full_fe_dual",
        "mpi_size": manifest.get("mpi_size") == 1,
        "dtype": manifest.get("dtype") == "complex128",
        "packet_count": manifest.get("global_summed_packet_count")
        == H1R31_PACKET_COUNT,
        "duplicate_count": manifest.get("summed_local_duplicate_count") == 0,
        "extractor_source": manifest.get("extractor_audit", {}).get("source")
        == H1R31_SOURCE_LABEL,
        "extractor_method": manifest.get("extractor_audit", {}).get("method")
        == "H1R2-direct-rank-one-MPC",
    }
    checks = {
        **{f"raw.{name}": value for name, value in raw_checks.items()},
        **{f"compact.{name}": value for name, value in compact_checks.items()},
        **{f"manifest.{name}": value for name, value in manifest_checks.items()},
    }
    if not all(checks.values()):
        raise ValueError(
            "historical H1R2 MPI1 authority failed: "
            + ",".join(name for name, value in checks.items() if not value)
        )
    return {
        "raw_dir": raw_dir,
        "record_path": record_path,
        "compact": compact,
        "watchdog": raw_watchdog,
        "worker": raw_worker,
        "manifest_path": manifest_path,
        "manifest": manifest,
        "source_definition": raw_worker["measurements"][0][
            "source_definition"
        ],
        "checks": checks,
        "raw_artifacts": historical_artifacts,
        "raw_artifact_checks": historical_artifact_checks,
        "pass": True,
    }


def _h1r31_check_raw(run_dir: Path, mpi1_run_dir: Path) -> dict[str, Any]:
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
        if line.strip()
    ]
    measurement = (worker.get("measurements") or [{}])[0]
    manifest_record = measurement.get("candidate_manifest")
    manifest_relative_path = (
        manifest_record.get("path")
        if isinstance(manifest_record, dict)
        else None
    )
    expected_artifacts = _h1r31_file_metadata(
        run_dir, manifest_relative_path
    )
    recorded_artifacts = watchdog.get("raw_artifacts")
    raw_artifact_checks = {
        name: isinstance(recorded_artifacts, dict)
        and recorded_artifacts.get(name) == metadata
        for name, metadata in expected_artifacts.items()
    }
    actual_artifacts = dict(expected_artifacts)
    actual_artifacts["watchdog_summary.json"] = _h1r3_path_metadata(
        run_dir / "watchdog_summary.json", "watchdog_summary.json"
    )

    source_start = watchdog.get("source_at_start", {})
    source_end = watchdog.get("source_at_end", {})
    worker_source_start = worker.get("source_at_start", {})
    worker_source_end = worker.get("source_at_end", {})
    current_source_sha = source_start.get("source_commit_full_sha")
    source_checks = {
        "watchdog_start_clean": _h1r2_source_is_clean(source_start),
        "watchdog_end_clean": _h1r2_source_is_clean(source_end),
        "watchdog_same_commit": (
            _h1r2_source_is_clean(source_start)
            and _h1r2_source_is_clean(source_end)
            and current_source_sha == source_end.get("source_commit_full_sha")
        ),
        "worker_start_clean": _h1r2_source_is_clean(worker_source_start),
        "worker_end_clean": _h1r2_source_is_clean(worker_source_end),
        "worker_same_commit": (
            _h1r2_source_is_clean(worker_source_start)
            and _h1r2_source_is_clean(worker_source_end)
            and worker_source_start.get("source_commit_full_sha")
            == worker_source_end.get("source_commit_full_sha")
        ),
        "worker_matches_watchdog": (
            worker_source_start.get("source_commit_full_sha") == current_source_sha
            and worker_source_end.get("source_commit_full_sha")
            == source_end.get("source_commit_full_sha")
        ),
    }
    runtime_watchdog = watchdog.get("watchdog_runtime_identity")
    runtime_worker = worker.get("runtime_identity")
    command = watchdog.get("command")
    expected_command = _watchdog_command(
        SimpleNamespace(run_dir=run_dir), mode="h1r3_mpi2"
    )
    runtime_checks = {
        "watchdog_values": _h1r2_runtime_identity_is_valid(runtime_watchdog),
        "worker_values": _h1r2_runtime_identity_is_valid(runtime_worker),
        "identical": runtime_worker == runtime_watchdog,
        "command_python_executable": (
            isinstance(command, list)
            and len(command) > 3
            and isinstance(runtime_watchdog, dict)
            and command[3] == runtime_watchdog.get("sys.executable")
        ),
        "recorded_match": watchdog.get("worker_runtime_identity_match") is True,
    }
    live_timeline = [item for item in timeline if item.get("worker_alive") is True]
    timeline_peak = max(
        (
            item.get("worker_tree_rss_sum_bytes")
            for item in live_timeline
            if isinstance(item.get("worker_tree_rss_sum_bytes"), int)
            and not isinstance(item.get("worker_tree_rss_sum_bytes"), bool)
            and item.get("worker_tree_rss_sum_bytes") >= 0
        ),
        default=None,
    )
    live_swaps = [_live_sample_swap(item) for item in live_timeline]
    timeline_swap = (
        max(live_swaps) if live_swaps and all(value is not None for value in live_swaps)
        else None
    )
    timeline_checks = {
        "live_samples_present": bool(live_timeline),
        "live_samples_readable": bool(
            live_timeline
            and all(_live_sample_is_readable(item) for item in live_timeline)
        ),
        "process_count_fields_nonnegative": bool(
            live_timeline
            and all(
                isinstance(item.get("live_worker_process_count"), int)
                and not isinstance(item.get("live_worker_process_count"), bool)
                and item.get("live_worker_process_count") >= 0
                for item in live_timeline
            )
        ),
        "all_ranks_in_process_tree": bool(
            live_timeline
            and all(
                isinstance(item.get("live_worker_process_count"), int)
                and not isinstance(item.get("live_worker_process_count"), bool)
                and item.get("live_worker_process_count") >= 0
                for item in live_timeline
            )
            and any(
                item.get("live_worker_process_count") >= 3
                for item in live_timeline
            )
            and any(
                item.get("worker_tree_rss_sum_bytes") == timeline_peak
                and item.get("live_worker_process_count") >= 3
                for item in live_timeline
            )
        ),
        "peak_recomputed": watchdog.get("peak_process_tree_rss_bytes")
        == timeline_peak,
        "peak_limit": isinstance(timeline_peak, int)
        and timeline_peak <= H1R31_PEAK_LIMIT_BYTES,
        "swap_recomputed": watchdog.get("worker_process_tree_swap_bytes")
        == timeline_swap,
        "swap_zero": timeline_swap == 0,
        "live_sample_count": watchdog.get("worker_live_sample_count")
        == len(live_timeline),
        "resource_authority": watchdog.get("resource_authority_readable")
        is True,
    }
    scope = worker.get("scope", {})
    candidate_audit = worker.get("candidate_action_audit", {})
    fresh_qualification = _evaluate_h1r31_worker_qualification(
        measurement, candidate_audit, scope=scope
    )
    reference_action = worker.get("reference_action", {})
    historical = _h1r31_read_historical_authority()
    worker_checks = {
        "schema": worker.get("schema")
        == "task037.candidate_h.h1r3.mpi2.worker.v1",
        "evidence_sha256": evidence_sha256_is_valid(worker),
        "status_pass": worker.get("status") == "pass",
        "qualification_status": worker.get("qualification", {}).get("status")
        == fresh_qualification.get("status"),
        "qualification_pass": worker.get("qualification", {}).get("pass")
        == fresh_qualification.get("pass"),
        "fresh_pass": fresh_qualification.get("pass") is True,
        "mpi_size": worker.get("mpi_size") == 2,
        "scope_global_rows": worker.get("global_rows") == scope.get("global_rows"),
        "scope_constraint_count": worker.get("constraint_count")
        == scope.get("constraint_count"),
        "source_definition_matches_measurement": worker.get(
            "source_definitions", {}
        ).get(H1R31_SOURCE_LABEL)
        == measurement.get("source_definition"),
        "source_definition_matches_history": measurement.get("source_definition")
        == historical["source_definition"],
        "reference_action": reference_action.get("type") == "MpcFormActionContext"
        and reference_action.get("same_worker") is True
        and reference_action.get("apply_count") == H1R31_REFERENCE_APPLY_COUNT
        and reference_action.get("global_matrix_materialized") is False,
    }
    watchdog_checks = {
        "schema": watchdog.get("schema")
        == "task037.candidate_h.h1r3.mpi2.watchdog.v1",
        "evidence_sha256": evidence_sha256_is_valid(watchdog),
        "command": command == expected_command,
        "mpi_size": watchdog.get("mpi_size") == 2,
        "timeout_seconds": watchdog.get("timeout_seconds")
        == H1R31_TIMEOUT_SECONDS,
        "poll_interval_seconds": watchdog.get("poll_interval_seconds")
        == H1_POLL_SECONDS,
        "rss_limit_bytes": watchdog.get("rss_limit_bytes")
        == H1R31_PEAK_LIMIT_BYTES,
        "status": watchdog.get("status") == "pass",
        "return_code": watchdog.get("return_code") == 0,
        "controlled_stop": watchdog.get("controlled_stop") is None,
        "completion": (
            isinstance(watchdog.get("completion_elapsed_seconds"), (int, float))
            and not isinstance(watchdog.get("completion_elapsed_seconds"), bool)
            and math.isfinite(float(watchdog["completion_elapsed_seconds"]))
            and 0.0 <= watchdog["completion_elapsed_seconds"] <= H1R31_TIMEOUT_SECONDS
        ),
        "wall_diagnostic": (
            isinstance(watchdog.get("wall_seconds"), (int, float))
            and math.isfinite(float(watchdog["wall_seconds"]))
            and watchdog["wall_seconds"] >= 0.0
        ),
        "worker_summary_present": watchdog.get("worker_summary_present") is True,
        "worker_summary_status": watchdog.get("worker_summary_status")
        == worker.get("status"),
        "worker_summary_evidence_valid": watchdog.get(
            "worker_summary_evidence_sha256_valid"
        )
        is True
        and evidence_sha256_is_valid(worker),
        "process_tree_all_ranks": watchdog.get(
            "worker_process_tree_all_ranks"
        ) is True
        and timeline_checks["all_ranks_in_process_tree"],
        "worker_qualification_pass": watchdog.get("worker_qualification_pass")
        == fresh_qualification.get("pass"),
        "worker_recomputation": watchdog.get("worker_qualification_recomputed")
        == fresh_qualification,
        "source_stable_clean": watchdog.get("source_stable_clean") is True,
        "termination_not_requested": watchdog.get("termination", {}).get(
            "requested"
        )
        is False,
    }
    canonical_checks: dict[str, Any]
    canonical_comparison: dict[str, Any] | None = None
    current_manifest = None
    if fresh_qualification.get("numerical_gate_pass") is True:
        manifest_path_ok = (
            isinstance(manifest_record, dict)
            and manifest_relative_path
            == f"canonical/{H1R31_SOURCE_LABEL}/candidate_manifest.json"
        )
        if manifest_path_ok:
            current_manifest = read_canonical_manifest(
                run_dir / manifest_relative_path,
                expected_sha256=str(manifest_record["sha256"]),
            )
            extractor = current_manifest.get("extractor_audit", {})
            canonical_comparison = compare_canonical_manifests(
                run_dir / manifest_relative_path,
                historical["manifest_path"],
                left_sha256=str(manifest_record["sha256"]),
                right_sha256=H1R31_HISTORICAL_MANIFEST_SHA256,
                relative_tolerance=H1R31_CANONICAL_TOLERANCE,
            )
            canonical_checks = {
                "export_after_numeric_gate": measurement.get("canonical_export")
                is True,
                "packet_count": current_manifest.get("global_summed_packet_count")
                == H1R31_PACKET_COUNT,
                "record_packet_count": manifest_record.get("packet_count")
                == H1R31_PACKET_COUNT,
                "role": current_manifest.get("role") == "full_fe_dual",
                "mpi_size": current_manifest.get("mpi_size") == 2,
                "dtype": current_manifest.get("dtype") == "complex128",
                "duplicate_count": current_manifest.get(
                    "summed_local_duplicate_count"
                )
                == 0,
                "extractor_source": extractor.get("source") == H1R31_SOURCE_LABEL,
                "extractor_method": extractor.get("method")
                == "H1R3.1-direct-rank-one-MPC",
                "historical_authority": historical["pass"],
                "relative_l2": canonical_comparison.get(
                    "relative_coefficient_l2"
                )
                <= H1R31_CANONICAL_TOLERANCE,
                "missing_extra_duplicate": all(
                    canonical_comparison.get(name) == 0
                    for name in (
                        "missing_key_count",
                        "extra_key_count",
                        "duplicate_left_count",
                        "duplicate_right_count",
                    )
                ),
                "comparison_pass": canonical_comparison.get("pass") is True,
            }
        else:
            canonical_checks = {"manifest_path": False}
    else:
        canonical_checks = {"numerical_gate_required": False}
    checks = {
        **{f"raw.{name}": value for name, value in raw_artifact_checks.items()},
        **{f"source.{name}": value for name, value in source_checks.items()},
        **{f"runtime.{name}": value for name, value in runtime_checks.items()},
        **{f"timeline.{name}": value for name, value in timeline_checks.items()},
        **{f"worker.{name}": value for name, value in worker_checks.items()},
        **{f"watchdog.{name}": value for name, value in watchdog_checks.items()},
        **{f"canonical.{name}": value for name, value in canonical_checks.items()},
        "historical_authority": historical["pass"],
        "historical_path_argument": Path(mpi1_run_dir).resolve()
        == historical["raw_dir"],
        "worker_qualification": fresh_qualification.get("pass") is True,
    }
    problems = [name for name, value in checks.items() if value is not True]
    return {
        "schema": "task037.candidate_h.h1r3.mpi2.compact_check.v1",
        "status": "pass" if not problems else "gate_failed",
        "pass": not problems,
        "checks": checks,
        "raw_artifact_checks": raw_artifact_checks,
        "source_checks": source_checks,
        "runtime_checks": runtime_checks,
        "timeline_checks": timeline_checks,
        "worker_checks": worker_checks,
        "watchdog_checks": watchdog_checks,
        "canonical_checks": canonical_checks,
        "worker_qualification_recomputed": fresh_qualification,
        "historical_authority": {
            "raw_run_directory": str(historical["raw_dir"]),
            "record_path": str(historical["record_path"]),
            "source_commit_full_sha": H1R31_HISTORICAL_SOURCE_SHA,
            "manifest_sha256": H1R31_HISTORICAL_MANIFEST_SHA256,
            "packet_count": H1R31_PACKET_COUNT,
            "mpi_size": 1,
            "role": "full_fe_dual",
            "raw_artifacts": historical["raw_artifacts"],
            "raw_artifact_checks": historical["raw_artifact_checks"],
            "embedded_evidence_sha256_valid": {
                "worker_summary": historical["checks"][
                    "raw.worker_evidence_sha256"
                ],
                "watchdog_summary": historical["checks"][
                    "raw.watchdog_evidence_sha256"
                ],
            },
            "pass": historical["pass"],
        },
        "raw_run_directory": str(run_dir),
        "source_identity": {
            "source_commit_full_sha": current_source_sha
            if source_checks["watchdog_same_commit"]
            else None,
            "start": source_start,
            "end": source_end,
        },
        "raw_artifacts": actual_artifacts,
        "raw_evidence_sha256": {
            "worker_summary_bytes": actual_artifacts["run_summary.json"]["sha256"],
            "watchdog_summary_bytes": actual_artifacts["watchdog_summary.json"][
                "sha256"
            ],
            "canonical_manifest_bytes": (
                actual_artifacts[manifest_relative_path]["sha256"]
                if manifest_relative_path in actual_artifacts
                else None
            ),
        },
        "embedded_evidence_sha256": {
            "worker_summary": worker.get("evidence_sha256"),
            "watchdog_summary": watchdog.get("evidence_sha256"),
        },
        "measurement": {
            "global_rows": worker.get("global_rows"),
            "constraint_count": worker.get("constraint_count"),
            "timing_reduction": measurement.get("timing_reduction"),
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
            "retained_payload_components": candidate_audit.get(
                "retained_numeric_payload_components"
            ),
            "retained_payload_local_bytes": candidate_audit.get(
                "retained_numeric_payload_local_bytes"
            ),
            "retained_payload_global_sum_bytes": candidate_audit.get(
                "retained_numeric_payload_global_sum_bytes"
            ),
            "retained_payload_global_max_bytes": candidate_audit.get(
                "retained_numeric_payload_global_max_bytes"
            ),
            "completion_elapsed_seconds": watchdog.get(
                "completion_elapsed_seconds"
            ),
            "process_tree_peak_rss_bytes": timeline_peak,
            "process_tree_swap_bytes": timeline_swap,
            "canonical_packet_count": measurement.get(
                "candidate_canonical_packet_count"
            ),
            "canonical_comparison": canonical_comparison,
        },
        "memory_authority": {
            "process_tree_peak_limit_bytes": H1R31_PEAK_LIMIT_BYTES,
            "process_tree_peak_rss_bytes": timeline_peak,
            "swap_bytes": timeline_swap,
            "completion_elapsed_seconds": watchdog.get(
                "completion_elapsed_seconds"
            ),
            "user_lt_2GB_target_bytes": 2_000_000_000,
            "user_lt_2GB_target_evaluated": timeline_peak is not None,
            "user_lt_2GB_target_pass": (
                None if timeline_peak is None else timeline_peak < 2_000_000_000
            ),
        },
        "scope_boundary": {
            "H1R3.2": (
                "eligible_by_review_v6"
                if not problems
                else "locked_pending_H1R3.1_pass"
            ),
            "H2": "locked",
        },
        "problems": problems,
    }


def run_h1r31_check(
    run_dir: Path, mpi1_run_dir: Path, output: Path
) -> int:
    try:
        result = _h1r31_check_raw(Path(run_dir), Path(mpi1_run_dir))
    except (OSError, KeyError, TypeError, ValueError, IndexError, AttributeError) as exc:
        result = {
            "schema": "task037.candidate_h.h1r3.mpi2.compact_check.v1",
            "status": "gate_failed",
            "pass": False,
            "problems": [
                f"controlled_checker_failure:{type(exc).__name__}:{exc}"
            ],
        }
    result = attach_evidence_sha256(result)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0 if result["pass"] else 1


def _h1r32_read_h10_baseline() -> dict[str, Any]:
    raw_dir = Path(H1R32_H10_RAW_DIR).resolve()
    record_path = Path(H1R32_H10_RECORD).resolve()
    record_bytes = record_path.read_bytes()
    compact = json.loads(record_bytes.decode("utf-8"))
    recorded_artifacts = compact.get("raw_artifacts")
    manifest_paths = [
        name
        for name in (recorded_artifacts or {})
        if str(name).startswith("canonical/")
    ]
    if len(manifest_paths) != 1:
        raise ValueError("H1R3.0R h10 baseline must have one manifest")
    actual_artifacts = _h1r3_file_metadata(raw_dir)
    manifest_path = manifest_paths[0]
    actual_artifacts[manifest_path] = _h1r3_path_metadata(
        raw_dir / manifest_path, manifest_path
    )
    actual_artifacts["watchdog_summary.json"] = _h1r3_path_metadata(
        raw_dir / "watchdog_summary.json", "watchdog_summary.json"
    )
    raw_worker = json.loads(
        (raw_dir / "run_summary.json").read_text(encoding="utf-8")
    )
    raw_watchdog = json.loads(
        (raw_dir / "watchdog_summary.json").read_text(encoding="utf-8")
    )
    compact_measurement = compact.get("measurement", {})
    compact_memory = compact.get("memory_authority", {})
    source_identity = compact.get("source_identity", {})
    source_start = raw_watchdog.get("source_at_start", {})
    source_end = raw_watchdog.get("source_at_end", {})
    raw_artifact_checks = {
        "recorded_key_set": isinstance(recorded_artifacts, dict)
        and set(recorded_artifacts) == set(actual_artifacts),
        "record_sha256": hashlib.sha256(record_bytes).hexdigest()
        == H1R32_H10_RECORD_SHA256,
        "recorded_metadata": isinstance(recorded_artifacts, dict)
        and all(
            recorded_artifacts.get(name) == metadata
            for name, metadata in actual_artifacts.items()
        ),
    }
    raw_checks = {
        "compact_schema": compact.get("schema")
        == "task037.candidate_h.h1r3.warm.compact_check.v1",
        "compact_evidence": evidence_sha256_is_valid(compact),
        "compact_status": compact.get("status") == "pass"
        and compact.get("pass") is True,
        "compact_source": source_identity.get("source_commit_full_sha")
        == H1R32_H10_SOURCE_SHA,
        "compact_source_clean": _h1r2_source_is_clean(
            source_identity.get("start", {})
        )
        and _h1r2_source_is_clean(source_identity.get("end", {})),
        "compact_global_rows": compact_measurement.get("global_rows")
        == H1R32_H10_GLOBAL_ROWS,
        "compact_payload": compact_measurement.get(
            "retained_payload_global_sum_bytes"
        )
        == H1R32_H10_PAYLOAD_BYTES,
        "compact_peak": compact_memory.get(
            "completed_process_tree_peak_rss_bytes"
        )
        == H1R32_H10_PEAK_BYTES,
        "worker_schema": raw_worker.get("schema")
        == "task037.candidate_h.h1r3.warm.worker.v1",
        "worker_status": raw_worker.get("status") == "pass"
        and raw_worker.get("qualification", {}).get("pass") is True,
        "worker_evidence": evidence_sha256_is_valid(raw_worker),
        "worker_source": _h1r2_source_is_clean(
            raw_worker.get("source_at_start", {})
        )
        and _h1r2_source_is_clean(raw_worker.get("source_at_end", {}))
        and raw_worker.get("source_at_start", {}).get("source_commit_full_sha")
        == H1R32_H10_SOURCE_SHA
        and raw_worker.get("source_at_end", {}).get("source_commit_full_sha")
        == H1R32_H10_SOURCE_SHA,
        "worker_rows": raw_worker.get("global_rows") == H1R32_H10_GLOBAL_ROWS
        and raw_worker.get("candidate_action_audit", {}).get(
            "global_rows"
        )
        == H1R32_H10_GLOBAL_ROWS,
        "worker_payload": raw_worker.get(
            "candidate_action_audit", {}
        ).get("retained_numeric_payload_global_sum_bytes")
        == H1R32_H10_PAYLOAD_BYTES,
        "watchdog_schema": raw_watchdog.get("schema")
        == "task037.candidate_h.h1r3.warm.watchdog.v1",
        "watchdog_status": raw_watchdog.get("status") == "pass"
        and raw_watchdog.get("return_code") == 0,
        "watchdog_evidence": evidence_sha256_is_valid(raw_watchdog),
        "watchdog_source": _h1r2_source_is_clean(source_start)
        and _h1r2_source_is_clean(source_end)
        and source_start.get("source_commit_full_sha") == H1R32_H10_SOURCE_SHA
        and source_end.get("source_commit_full_sha") == H1R32_H10_SOURCE_SHA,
        "watchdog_peak": raw_watchdog.get("peak_process_tree_rss_bytes")
        == H1R32_H10_PEAK_BYTES,
        "raw_embedded_artifacts": isinstance(raw_watchdog.get("raw_artifacts"), dict)
        and all(
            raw_watchdog["raw_artifacts"].get(name) == metadata
            for name, metadata in actual_artifacts.items()
            if name != "watchdog_summary.json"
        ),
    }
    checks = {
        **{f"artifact.{name}": value for name, value in raw_artifact_checks.items()},
        **{f"raw.{name}": value for name, value in raw_checks.items()},
    }
    problems = [name for name, value in checks.items() if value is not True]
    if problems:
        raise ValueError("H1R3.0R h10 baseline failed: " + ",".join(problems))
    return {
        "raw_dir": raw_dir,
        "record_path": record_path,
        "record_sha256": H1R32_H10_RECORD_SHA256,
        "source_commit_full_sha": H1R32_H10_SOURCE_SHA,
        "global_rows": H1R32_H10_GLOBAL_ROWS,
        "payload_global_sum_bytes": H1R32_H10_PAYLOAD_BYTES,
        "peak_process_tree_rss_bytes": H1R32_H10_PEAK_BYTES,
        "manifest_path": manifest_path,
        "raw_artifacts": actual_artifacts,
        "raw_artifact_checks": raw_artifact_checks,
        "raw_checks": raw_checks,
        "compact": compact,
        "pass": True,
    }


def _h1r32_read_h1r31_prerequisite() -> dict[str, Any]:
    record_path = Path(H1R32_H1R31_RECORD).resolve()
    record_bytes = record_path.read_bytes()
    record = json.loads(record_bytes.decode("utf-8"))
    checks = {
        "record_sha256": hashlib.sha256(record_bytes).hexdigest()
        == H1R32_H1R31_RECORD_SHA256,
        "schema": record.get("schema")
        == "task037.candidate_h.h1r3.mpi2.compact_check.v1",
        "evidence": evidence_sha256_is_valid(record),
        "status_pass": record.get("status") == "pass"
        and record.get("pass") is True,
        "problems_empty": record.get("problems") == [],
        "h1r32_eligible": record.get("scope_boundary", {}).get("H1R3.2")
        == "eligible_by_review_v6",
        "h2_locked": record.get("scope_boundary", {}).get("H2") == "locked",
    }
    problems = [name for name, value in checks.items() if value is not True]
    if problems:
        raise ValueError("H1R3.1 prerequisite failed: " + ",".join(problems))
    return {
        "record_path": record_path,
        "record_sha256": H1R32_H1R31_RECORD_SHA256,
        "checks": checks,
        "source_commit_full_sha": record.get("source_identity", {}).get(
            "source_commit_full_sha"
        ),
        "pass": True,
    }


def _h1r32_check_raw(run_dir: Path, h10_run_dir: Path) -> dict[str, Any]:
    run_dir = Path(run_dir).resolve()
    h10_run_dir = Path(h10_run_dir).resolve()
    if h10_run_dir != Path(H1R32_H10_RAW_DIR).resolve():
        raise ValueError("H1R3.0R h10 path is not the frozen authority")
    h10 = _h1r32_read_h10_baseline()
    h1r31 = _h1r32_read_h1r31_prerequisite()
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
        if line.strip()
    ]
    root = json.loads(
        (run_dir / H1R32_ROOT_PID_FILE).read_text(encoding="utf-8")
    )
    actual_artifacts = _h1r32_file_metadata(run_dir)
    recorded_artifacts = watchdog.get("raw_artifacts")
    actual_artifacts["watchdog_summary.json"] = _h1r3_path_metadata(
        run_dir / "watchdog_summary.json", "watchdog_summary.json"
    )
    watchdog_artifacts = {
        name: metadata
        for name, metadata in actual_artifacts.items()
        if name != "watchdog_summary.json"
    }
    raw_artifact_checks = {
        "recorded_key_set": isinstance(recorded_artifacts, dict)
        and set(recorded_artifacts) == set(watchdog_artifacts),
        "recorded_metadata": isinstance(recorded_artifacts, dict)
        and all(
            recorded_artifacts.get(name) == metadata
            for name, metadata in watchdog_artifacts.items()
        ),
    }
    worker_source_start = worker.get("source_at_start", {})
    worker_source_end = worker.get("source_at_end", {})
    watchdog_source_start = watchdog.get("source_at_start", {})
    watchdog_source_end = watchdog.get("source_at_end", {})
    source_checks = {
        "watchdog_start_clean": _h1r2_source_is_clean(watchdog_source_start),
        "watchdog_end_clean": _h1r2_source_is_clean(watchdog_source_end),
        "worker_start_clean": _h1r2_source_is_clean(worker_source_start),
        "worker_end_clean": _h1r2_source_is_clean(worker_source_end),
        "same_current_commit": (
            watchdog_source_start.get("source_commit_full_sha")
            == watchdog_source_end.get("source_commit_full_sha")
            == worker_source_start.get("source_commit_full_sha")
            == worker_source_end.get("source_commit_full_sha")
        ),
        "watchdog_source_stable": watchdog.get("source_stable_clean") is True,
    }
    runtime_watchdog = watchdog.get("watchdog_runtime_identity")
    runtime_worker = worker.get("runtime_identity")
    command = watchdog.get("command")
    expected_command = _watchdog_command(
        SimpleNamespace(run_dir=run_dir), mode="h1r3_h5"
    )
    runtime_checks = {
        "watchdog_values": _h1r2_runtime_identity_is_valid(runtime_watchdog),
        "worker_values": _h1r2_runtime_identity_is_valid(runtime_worker),
        "identical": runtime_worker == runtime_watchdog,
        "command_python_executable": (
            isinstance(command, list)
            and len(command) > 3
            and isinstance(runtime_watchdog, dict)
            and command[3] == runtime_watchdog.get("sys.executable")
        ),
        "recorded_match": watchdog.get("worker_runtime_identity_match") is True,
    }
    live_timeline = [item for item in timeline if item.get("worker_alive") is True]
    timeline_peak = max(
        (
            item.get("worker_tree_rss_sum_bytes")
            for item in live_timeline
            if isinstance(item.get("worker_tree_rss_sum_bytes"), int)
            and not isinstance(item.get("worker_tree_rss_sum_bytes"), bool)
            and item.get("worker_tree_rss_sum_bytes") >= 0
        ),
        default=None,
    )
    live_swaps = [_live_sample_swap(item) for item in live_timeline]
    timeline_swap = (
        max(live_swaps)
        if live_swaps and all(value is not None for value in live_swaps)
        else None
    )
    timeline_checks = {
        "live_samples_present": bool(live_timeline),
        "live_samples_readable": bool(
            live_timeline
            and all(_live_sample_is_readable(item) for item in live_timeline)
        ),
        "peak_recomputed": watchdog.get("peak_process_tree_rss_bytes")
        == timeline_peak,
        "peak_limit": isinstance(timeline_peak, int)
        and timeline_peak <= H1R32_PEAK_LIMIT_BYTES,
        "swap_recomputed": watchdog.get("worker_process_tree_swap_bytes")
        == timeline_swap,
        "swap_zero": timeline_swap == 0,
        "live_sample_count": watchdog.get("worker_live_sample_count")
        == len(live_timeline),
        "resource_authority": watchdog.get("resource_authority_readable") is True,
    }
    root_checks = {
        "schema": root.get("schema") == "task037.candidate_h.h1r3.h5.root_pid.v1",
        "positive_root_pid": isinstance(root.get("root_pid"), int)
        and not isinstance(root.get("root_pid"), bool)
        and root.get("root_pid") > 0,
    }
    measurement = (worker.get("measurements") or [{}])[0]
    candidate_audit = worker.get("candidate_action_audit", {})
    fresh_qualification = _evaluate_h1r32_worker_qualification(
        measurement, candidate_audit, scope=worker.get("scope", {})
    )
    worker_checks = {
        "schema": worker.get("schema")
        == "task037.candidate_h.h1r3.h5.worker.v1",
        "evidence": evidence_sha256_is_valid(worker),
        "status_pass": worker.get("status") == "pass",
        "qualification_status": worker.get("qualification", {}).get("status")
        == fresh_qualification.get("status"),
        "qualification_pass": worker.get("qualification", {}).get("pass")
        == fresh_qualification.get("pass"),
        "fresh_pass": fresh_qualification.get("pass") is True,
        "mpi_size": worker.get("mpi_size") == 1,
        "global_rows": worker.get("global_rows") == H1R32_GLOBAL_ROWS,
        "global_cells": worker.get("global_cells") == H1R32_GLOBAL_CELLS,
        "axis_cell_counts": worker.get("axis_cell_counts")
        == list(H1R32_AXIS_CELL_COUNTS),
        "constraint_count": worker.get("constraint_count")
        == worker.get("scope", {}).get("constraint_count")
        == candidate_audit.get("constraint_count"),
        "source_definition_matches_measurement": worker.get(
            "source_definitions", {}
        ).get(H1R32_SOURCE_LABEL)
        == measurement.get("source_definition"),
        "reference_action": (
            worker.get("reference_action", {}).get("type")
            == "MpcFormActionContext"
            and worker.get("reference_action", {}).get("same_worker") is True
            and worker.get("reference_action", {}).get("apply_count")
            == H1R32_REFERENCE_APPLY_COUNT
            and worker.get("reference_action", {}).get(
                "global_matrix_materialized"
            )
            is False
        ),
    }
    watchdog_checks = {
        "schema": watchdog.get("schema")
        == "task037.candidate_h.h1r3.h5.watchdog.v1",
        "evidence": evidence_sha256_is_valid(watchdog),
        "command": command == expected_command,
        "mpi_size": watchdog.get("mpi_size") == 1,
        "timeout_seconds": watchdog.get("timeout_seconds")
        == H1R32_TIMEOUT_SECONDS,
        "rss_limit_bytes": watchdog.get("rss_limit_bytes")
        == H1R32_PEAK_LIMIT_BYTES,
        "status": watchdog.get("status") == "pass",
        "return_code": watchdog.get("return_code") == 0,
        "controlled_stop": watchdog.get("controlled_stop") is None,
        "completion": (
            isinstance(watchdog.get("completion_elapsed_seconds"), (int, float))
            and not isinstance(watchdog.get("completion_elapsed_seconds"), bool)
            and math.isfinite(float(watchdog["completion_elapsed_seconds"]))
            and 0.0 <= watchdog["completion_elapsed_seconds"]
            <= H1R32_TIMEOUT_SECONDS
        ),
        "worker_summary_present": watchdog.get("worker_summary_present") is True,
        "worker_summary_status": watchdog.get("worker_summary_status")
        == worker.get("status"),
        "worker_summary_evidence": watchdog.get(
            "worker_summary_evidence_sha256_valid"
        )
        is True
        and evidence_sha256_is_valid(worker),
        "worker_qualification_pass": watchdog.get("worker_qualification_pass")
        == fresh_qualification.get("pass"),
        "worker_recomputation": watchdog.get("worker_qualification_recomputed")
        == fresh_qualification,
        "source_stable_clean": watchdog.get("source_stable_clean") is True,
        "termination_not_requested": watchdog.get("termination", {}).get(
            "requested"
        )
        is False,
    }
    scale_values = {
        "M5_bytes": candidate_audit.get(
            "retained_numeric_payload_global_sum_bytes"
        ),
        "N5_rows": worker.get("global_rows"),
        "P5_bytes": timeline_peak,
        "M10_bytes": H1R32_H10_PAYLOAD_BYTES,
        "N10_rows": H1R32_H10_GLOBAL_ROWS,
        "P10_bytes": H1R32_H10_PEAK_BYTES,
    }
    alpha_payload = None
    b_peak = None
    p_h1_pred = None
    if (
        isinstance(scale_values["M5_bytes"], (int, float))
        and scale_values["M5_bytes"] > 0
        and isinstance(scale_values["N5_rows"], (int, float))
        and scale_values["N5_rows"] > H1R32_H10_GLOBAL_ROWS
    ):
        alpha_payload = math.log(
            float(scale_values["M5_bytes"]) / H1R32_H10_PAYLOAD_BYTES
        ) / math.log(float(scale_values["N5_rows"]) / H1R32_H10_GLOBAL_ROWS)
    if (
        isinstance(scale_values["P5_bytes"], (int, float))
        and not isinstance(scale_values["P5_bytes"], bool)
        and math.isfinite(float(scale_values["P5_bytes"]))
        and float(scale_values["P5_bytes"]) >= 0.0
        and isinstance(scale_values["P10_bytes"], (int, float))
        and not isinstance(scale_values["P10_bytes"], bool)
        and math.isfinite(float(scale_values["P10_bytes"]))
        and float(scale_values["P10_bytes"]) >= 0.0
        and isinstance(scale_values["N5_rows"], int)
        and not isinstance(scale_values["N5_rows"], bool)
        and scale_values["N5_rows"] > H1R32_H10_GLOBAL_ROWS
    ):
        b_peak = (
            float(scale_values["P5_bytes"]) - float(scale_values["P10_bytes"])
        ) / (float(scale_values["N5_rows"]) - H1R32_H10_GLOBAL_ROWS)
        p_h1_pred = float(scale_values["P10_bytes"]) + b_peak * (
            H1R32_H1_GLOBAL_ROWS - H1R32_H10_GLOBAL_ROWS
        )
    retained_payload_bytes_per_row = None
    packed_temporary_bytes_per_row = None
    action_seconds_per_row = None
    if (
        isinstance(scale_values["M5_bytes"], (int, float))
        and not isinstance(scale_values["M5_bytes"], bool)
        and math.isfinite(float(scale_values["M5_bytes"]))
        and isinstance(scale_values["N5_rows"], int)
        and not isinstance(scale_values["N5_rows"], bool)
        and scale_values["N5_rows"] > 0
    ):
        retained_payload_bytes_per_row = float(
            scale_values["M5_bytes"]
        ) / float(scale_values["N5_rows"])
    packed_temporary_bytes = candidate_audit.get(
        "last_packed_coefficient_bytes"
    )
    if (
        isinstance(packed_temporary_bytes, int)
        and not isinstance(packed_temporary_bytes, bool)
        and packed_temporary_bytes >= 0
        and isinstance(scale_values["N5_rows"], int)
        and not isinstance(scale_values["N5_rows"], bool)
        and scale_values["N5_rows"] > 0
    ):
        packed_temporary_bytes_per_row = float(packed_temporary_bytes) / float(
            scale_values["N5_rows"]
        )
    candidate_repeat_seconds = measurement.get(
        "candidate_repeat_apply_seconds"
    )
    if (
        isinstance(candidate_repeat_seconds, (int, float))
        and not isinstance(candidate_repeat_seconds, bool)
        and math.isfinite(float(candidate_repeat_seconds))
        and isinstance(scale_values["N5_rows"], int)
        and not isinstance(scale_values["N5_rows"], bool)
        and scale_values["N5_rows"] > 0
    ):
        action_seconds_per_row = float(candidate_repeat_seconds) / float(
            scale_values["N5_rows"]
        )
    scale_checks = {
        "payload_per_row": bool(
            isinstance(scale_values["M5_bytes"], (int, float))
            and math.isfinite(float(scale_values["M5_bytes"]))
            and float(scale_values["M5_bytes"]) / H1R32_GLOBAL_ROWS
            <= H1R32_PAYLOAD_BYTES_PER_ROW_LIMIT
        ),
        "packed_per_row": fresh_qualification.get("payload_checks", {}).get(
            "packed_row_limit"
        )
        is True,
        "alpha_payload": (
            alpha_payload is not None
            and math.isfinite(alpha_payload)
            and alpha_payload <= H1R32_ALPHA_PAYLOAD_LIMIT
        ),
        "action_seconds_per_row": fresh_qualification.get(
            "timing_checks", {}
        ).get("second_seconds_per_row")
        is True,
        "peak_slope": (
            b_peak is not None
            and math.isfinite(b_peak)
            and b_peak <= H1R32_PEAK_SLOPE_BYTES_PER_ROW_LIMIT
        ),
        "peak_limit": timeline_checks["peak_limit"],
        "swap_zero": timeline_checks["swap_zero"],
        "completion": watchdog_checks["completion"],
    }
    canonical_checks = {
        "canonical_export_false": measurement.get("canonical_export") is False,
        "canonical_packet_none": measurement.get(
            "candidate_canonical_packet_count"
        )
        is None,
        "manifest_none": measurement.get("candidate_manifest") is None,
        "canonical_directory_absent": not (run_dir / "canonical").exists(),
    }
    checks = {
        **{f"raw.{name}": value for name, value in raw_artifact_checks.items()},
        **{f"source.{name}": value for name, value in source_checks.items()},
        **{f"runtime.{name}": value for name, value in runtime_checks.items()},
        **{f"root.{name}": value for name, value in root_checks.items()},
        **{f"timeline.{name}": value for name, value in timeline_checks.items()},
        **{f"worker.{name}": value for name, value in worker_checks.items()},
        **{f"watchdog.{name}": value for name, value in watchdog_checks.items()},
        **{f"scale.{name}": value for name, value in scale_checks.items()},
        **{f"canonical.{name}": value for name, value in canonical_checks.items()},
        "h10_authority": h10["pass"],
        "h1r31_prerequisite": h1r31["pass"],
        "worker_qualification": fresh_qualification.get("pass") is True,
    }
    problems = [name for name, value in checks.items() if value is not True]
    return {
        "schema": "task037.candidate_h.h1r3.h5.compact_check.v1",
        "status": "pass" if not problems else "gate_failed",
        "pass": not problems,
        "checks": checks,
        "problems": problems,
        "raw_run_directory": str(run_dir),
        "raw_artifacts": actual_artifacts,
        "source_identity": {
            "start": watchdog_source_start,
            "end": watchdog_source_end,
            "worker_start": worker_source_start,
            "worker_end": worker_source_end,
            "source_commit_full_sha": watchdog_source_start.get(
                "source_commit_full_sha"
            ),
        },
        "runtime_identity": {
            "watchdog": runtime_watchdog,
            "worker": runtime_worker,
            "match": watchdog.get("worker_runtime_identity_match"),
        },
        "measurement": {
            "global_rows": worker.get("global_rows"),
            "global_cells": worker.get("global_cells"),
            "axis_cell_counts": worker.get("axis_cell_counts"),
            "constraint_count": worker.get("constraint_count"),
            "reference_apply_seconds": measurement.get("reference_apply_seconds"),
            "candidate_apply_seconds": measurement.get("candidate_apply_seconds"),
            "candidate_repeat_apply_seconds": measurement.get(
                "candidate_repeat_apply_seconds"
            ),
            "timing_reduction": measurement.get("timing_reduction"),
            "relative_error": measurement.get(
                "reference_vs_candidate_relative_error"
            ),
            "finite": measurement.get("finite"),
            "deterministic": measurement.get("deterministic"),
            "retained_payload_components": candidate_audit.get(
                "retained_numeric_payload_components"
            ),
            "retained_payload_local_bytes": candidate_audit.get(
                "retained_numeric_payload_local_bytes"
            ),
            "retained_payload_global_sum_bytes": candidate_audit.get(
                "retained_numeric_payload_global_sum_bytes"
            ),
            "retained_payload_global_max_bytes": candidate_audit.get(
                "retained_numeric_payload_global_max_bytes"
            ),
            "packed_temporary_bytes": candidate_audit.get(
                "last_packed_coefficient_bytes"
            ),
            "canonical_export": measurement.get("canonical_export"),
            "canonical_packet_count": measurement.get(
                "candidate_canonical_packet_count"
            ),
        },
        "scaling": {
            **scale_values,
            "retained_payload_bytes_per_row": retained_payload_bytes_per_row,
            "packed_temporary_bytes_per_row": packed_temporary_bytes_per_row,
            "action_seconds_per_row": action_seconds_per_row,
            "N_h1_rows": H1R32_H1_GLOBAL_ROWS,
            "N_h1_axis_cell_counts": list(H1R32_H1_AXIS_CELL_COUNTS),
            "retained_payload_bytes_per_row_limit": H1R32_PAYLOAD_BYTES_PER_ROW_LIMIT,
            "packed_temporary_bytes_per_row_limit": H1R32_PACKED_BYTES_PER_ROW_LIMIT,
            "action_seconds_per_row_limit": H1R32_ACTION_SECONDS_PER_ROW_LIMIT,
            "alpha_payload": alpha_payload,
            "b_peak_bytes_per_row": b_peak,
            "P_h1_pred_bytes": p_h1_pred,
            "P_h1_pred_scope": "action-only; not full solver/PDE qualification",
        },
        "memory_authority": {
            "completed_process_tree_peak_limit_bytes": H1R32_PEAK_LIMIT_BYTES,
            "completed_process_tree_peak_rss_bytes": timeline_peak,
            "swap_bytes": timeline_swap,
            "completion_elapsed_seconds": watchdog.get(
                "completion_elapsed_seconds"
            ),
            "action_only": True,
            "user_lt_2GB_not_inferred": True,
        },
        "h10_authority": {
            "raw_run_directory": str(h10["raw_dir"]),
            "record_path": str(h10["record_path"]),
            "record_sha256": h10["record_sha256"],
            "source_commit_full_sha": h10["source_commit_full_sha"],
            "global_rows": h10["global_rows"],
            "payload_global_sum_bytes": h10["payload_global_sum_bytes"],
            "peak_process_tree_rss_bytes": h10["peak_process_tree_rss_bytes"],
            "raw_artifact_checks": h10["raw_artifact_checks"],
            "raw_checks": h10["raw_checks"],
            "pass": h10["pass"],
        },
        "h1r31_prerequisite": {
            "record_path": str(h1r31["record_path"]),
            "record_sha256": h1r31["record_sha256"],
            "source_commit_full_sha": h1r31["source_commit_full_sha"],
            "checks": h1r31["checks"],
            "pass": h1r31["pass"],
        },
        "scope_boundary": {
            "H1R3.2": "pass" if not problems else "gate_failed",
            "H2": "locked",
        },
    }


def run_h1r32_check(
    run_dir: Path, h10_run_dir: Path, output: Path
) -> int:
    try:
        result = _h1r32_check_raw(Path(run_dir), Path(h10_run_dir))
    except (OSError, KeyError, TypeError, ValueError, IndexError, AttributeError) as exc:
        result = {
            "schema": "task037.candidate_h.h1r3.h5.compact_check.v1",
            "status": "gate_failed",
            "pass": False,
            "problems": [
                f"controlled_checker_failure:{type(exc).__name__}:{exc}"
            ],
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
    h1r3_worker = subparsers.add_parser("h1r3-warm-worker")
    h1r3_worker.add_argument("--run-dir", type=Path, required=True)
    h1r3_watchdog = subparsers.add_parser("h1r3-warm-watchdog")
    h1r3_watchdog.add_argument("--run-dir", type=Path, required=True)
    h1r3_check = subparsers.add_parser("h1r3-warm-check")
    h1r3_check.add_argument("--run-dir", type=Path, required=True)
    h1r3_check.add_argument("--output", type=Path, required=True)
    h1r31_worker = subparsers.add_parser("h1r3-mpi2-worker")
    h1r31_worker.add_argument("--run-dir", type=Path, required=True)
    h1r31_watchdog = subparsers.add_parser("h1r3-mpi2-watchdog")
    h1r31_watchdog.add_argument("--run-dir", type=Path, required=True)
    h1r31_check = subparsers.add_parser("h1r3-mpi2-check")
    h1r31_check.add_argument("--run-dir", type=Path, required=True)
    h1r31_check.add_argument("--mpi1-run-dir", type=Path, required=True)
    h1r31_check.add_argument("--output", type=Path, required=True)
    h1r32_worker = subparsers.add_parser("h1r3-h5-worker")
    h1r32_worker.add_argument("--run-dir", type=Path, required=True)
    h1r32_watchdog = subparsers.add_parser("h1r3-h5-watchdog")
    h1r32_watchdog.add_argument("--run-dir", type=Path, required=True)
    h1r32_check = subparsers.add_parser("h1r3-h5-check")
    h1r32_check.add_argument("--run-dir", type=Path, required=True)
    h1r32_check.add_argument("--h10-run-dir", type=Path, required=True)
    h1r32_check.add_argument("--output", type=Path, required=True)
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
    if args.command == "h1r3-warm-worker":
        return 0 if run_worker(args.run_dir, mode="h1r3_warm") else 1
    if args.command == "h1r3-warm-watchdog":
        return run_watchdog(args, mode="h1r3_warm")
    if args.command == "h1r3-warm-check":
        return run_h1r3_check(args.run_dir, args.output)
    if args.command == "h1r3-mpi2-worker":
        return 0 if run_worker(args.run_dir, mode="h1r3_mpi2") else 1
    if args.command == "h1r3-mpi2-watchdog":
        return run_watchdog(args, mode="h1r3_mpi2")
    if args.command == "h1r3-mpi2-check":
        return run_h1r31_check(args.run_dir, args.mpi1_run_dir, args.output)
    if args.command == "h1r3-h5-worker":
        return 0 if run_worker(args.run_dir, mode="h1r3_h5") else 1
    if args.command == "h1r3-h5-watchdog":
        return run_watchdog(args, mode="h1r3_h5")
    if args.command == "h1r3-h5-check":
        return run_h1r32_check(args.run_dir, args.h10_run_dir, args.output)
    result = compare_run_directories(args.mpi1_run_dir, args.mpi2_run_dir)
    payload = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output is None:
        print(payload, end="")
    else:
        args.output.write_text(payload, encoding="utf-8")
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
