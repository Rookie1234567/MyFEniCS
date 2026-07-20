from __future__ import annotations

import argparse
from collections.abc import Mapping
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

from benchmarks.run_direct_memory_forensics import (
    TIMELINE_FIELDS,
    _add_cpu_core_equivalents,
    _sample,
)
from benchmarks.run_task031_memory_forensics import _sampler_summary
from benchmarks.run_task033_qep_matrix import _resource_environment_snapshot
from benchmarks.task033_qep_measurement import task033_left_candidate_pool_size
from benchmarks.task033_qep_qualification import (
    resource_authority_gate,
    source_identity_gate,
)
from benchmarks.task034_wsl_resources import (
    effective_memory_limit,
    resource_authority_sample,
)
from benchmarks.task034_workstation_resource_gates import (
    task034_workstation_hybrid_launch_gate,
)
from benchmarks.task033_watchdog_launch import (
    DEFAULT_RESOURCE_MATRIX,
    high_order_core_evidence_gate,
    hybrid_launch_gate,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT_ROOT = ROOT / "benchmarks" / "artifacts" / "cases" / "091"
REDUCED_EQUAL_ACCURACY_RESOURCE_MATRIX = (
    ROOT
    / "benchmarks"
    / "cases"
    / "091_hybrid_hp_adaptivity_feasibility"
    / "records"
    / "stage5_equal_accuracy"
    / "resource_matrix.json"
)
TASK034_WORKSTATION_RESOURCE_AUTHORITY = (
    ROOT
    / "benchmarks"
    / "cases"
    / "092_workstation_wsl_adaptive_scalability"
    / "records"
    / "workstation_hybrid_launch_authority.json"
)

CASE090_CORE_COMPATIBLE_DESCENDANT_FILES = frozenset(
    {
        "README.md",
        "benchmarks/cases/090_high_order_3d_floquet_hcurl/README.md",
        "benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/README.md",
        "benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/"
        "stage1_high_order/stage_summary.json",
        "benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/"
        "stage2_matched_trace/phaseB_summary.json",
        "benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/"
        "stage2_matched_trace/p4_four_mode_summary.json",
        "benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/"
        "stage3_p3_h5/full3d_reference.json",
        "benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/"
        "stage3_p3_h5/full3d_closure_summary.json",
        "benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/"
        "stage3_p3_h5/phaseC1_full3d_assembly_summary.json",
        "benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/"
        "stage3_p3_h5/phaseC_summary.json",
        "benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/"
        "stage4_p4_h5/calibration_summary.json",
        "benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/"
        "stage5_equal_accuracy/full3d_reference_p3_h10.json",
        "benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/"
        "stage5_equal_accuracy/full3d_reference_p3_h7p5.json",
        "benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/"
        "stage5_equal_accuracy/resource_matrix.json",
        "benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/"
        "stage5_equal_accuracy/resource_matrix.csv",
        "benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/"
        "stage5_equal_accuracy/source_compatibility_audit.json",
        "benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/"
        "variable_p_capability_audit.json",
        "benchmarks/cases/README.md",
        "benchmarks/run_task032_phase6_augmented.py",
        "benchmarks/run_task033_full3d_watchdog.py",
        "benchmarks/run_task033_matched_trace.py",
        "benchmarks/run_task033_memory_watchdog.py",
        "benchmarks/run_task033_phaseC.py",
        "benchmarks/run_task033_resource_matrix.py",
        "benchmarks/run_task033_source_compatibility.py",
        "benchmarks/run_task034_wsl_qualification.py",
        "benchmarks/task034_p3_h3_reranking.py",
        "benchmarks/task034_mpi_identity.py",
        "benchmarks/task034_numerical_blob_checker.py",
        "benchmarks/task033_resource_gates.py",
        "benchmarks/task033_matched_trace_qualification.py",
        "benchmarks/task033_phaseC.py",
        "benchmarks/task033_qep_qualification.py",
        "benchmarks/task033_source_compatibility.py",
        "benchmarks/task033_watchdog_launch.py",
        "benchmarks/task034_workstation_resource_gates.py",
        "benchmarks/cases/092_workstation_wsl_adaptive_scalability/expected.json",
        "benchmarks/cases/092_workstation_wsl_adaptive_scalability/README.md",
        "benchmarks/cases/092_workstation_wsl_adaptive_scalability/records/"
        "workstation_hybrid_launch_authority.json",
        # Phase B changed only the Hybrid 3D/2D interface trace projection.
        # It is numerical source for Hybrid, but it is component-disjoint from
        # the already accepted pure-3D Case090 Floquet core.  Phase C creates
        # fresh target Hybrid evidence at the new SHA; this exception reuses
        # Case090 only as the high-order Floquet launch prerequisite.
        "src/coupling/modal_trace_projection.py",
        "src/common/distributed_matrix_diagnostics.py",
        "src/modes/mode_classification.py",
        "src/solvers/hybrid_fem_modal_schur_direct.py",
    }
)

CASE090_COMPONENT_DISJOINT_NUMERICAL_FILES = frozenset(
    {
        "benchmarks/run_task032_phase6_augmented.py",
        "benchmarks/task034_mpi_identity.py",
        "src/common/distributed_matrix_diagnostics.py",
        "src/modes/mode_classification.py",
        "src/coupling/modal_trace_projection.py",
        "src/solvers/hybrid_fem_modal_schur_direct.py",
    }
)

TASK034_AUTHORITY_COMPONENT_DISJOINT_NUMERICAL_FILES = frozenset(
    {
        "benchmarks/run_task032_phase6_augmented.py",
        "benchmarks/run_task033_full3d_watchdog.py",
        "benchmarks/task034_mpi_identity.py",
        "src/common/distributed_matrix_diagnostics.py",
        "src/modes/mode_classification.py",
        "src/solvers/hybrid_fem_modal_schur_direct.py",
    }
)
TASK034_AUTHORITY_COMPATIBLE_CHANGED_FILES = frozenset(
    {
        "benchmarks/run_task033_memory_watchdog.py",
        "benchmarks/run_task034_wsl_qualification.py",
        "benchmarks/task034_numerical_blob_checker.py",
        "benchmarks/task034_workstation_resource_gates.py",
        *TASK034_AUTHORITY_COMPONENT_DISJOINT_NUMERICAL_FILES,
    }
)


def _git(*args: str) -> str | None:
    try:
        return subprocess.check_output(
            ["git", *args], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _case090_source_compatibility(
    evidence: Mapping[str, Any] | None,
    *,
    current_source_sha: str | None,
) -> dict[str, Any]:
    """Audit whether Case090 may be reused by a core-compatible descendant.

    The legacy ``numerical_source_unchanged`` field is retained for consumers
    of the accepted Phase A record.  Its precise scope is the pure-3D Case090
    Floquet core, not every numerical component in the repository.
    """

    payload = evidence if isinstance(evidence, Mapping) else {}
    identity = payload.get("identity")
    identity = identity if isinstance(identity, Mapping) else {}
    evidence_source_sha = identity.get("source_commit_full_sha")
    if not (
        isinstance(evidence_source_sha, str)
        and len(evidence_source_sha) == 40
        and isinstance(current_source_sha, str)
        and len(current_source_sha) == 40
    ):
        return {
            "pass": False,
            "evidence_source_sha": evidence_source_sha,
            "current_source_sha": current_source_sha,
            "numerical_source_unchanged": False,
            "case090_core_source_unchanged": False,
            "compatibility_scope": "case090_pure3d_floquet_core",
            "changed_paths": [],
            "component_disjoint_numerical_changed_paths": [],
            "disallowed_changed_paths": [],
            "failures": ["source_sha_missing_or_invalid"],
        }
    if evidence_source_sha == current_source_sha:
        return {
            "pass": True,
            "evidence_source_sha": evidence_source_sha,
            "current_source_sha": current_source_sha,
            "numerical_source_unchanged": True,
            "case090_core_source_unchanged": True,
            "compatibility_scope": "case090_pure3d_floquet_core",
            "changed_paths": [],
            "component_disjoint_numerical_changed_paths": [],
            "disallowed_changed_paths": [],
            "failures": [],
        }
    merge_base = _git("merge-base", evidence_source_sha, current_source_sha)
    rendered_paths = _git(
        "diff", "--name-only", f"{evidence_source_sha}..{current_source_sha}"
    )
    changed_paths = (
        [] if rendered_paths is None else rendered_paths.splitlines()
    )

    def allowed(path: str) -> bool:
        return bool(
            path in CASE090_CORE_COMPATIBLE_DESCENDANT_FILES
            or path.startswith(
                "benchmarks/cases/092_workstation_wsl_adaptive_scalability/"
                "records/"
            )
            or path.startswith("docs/")
            or path.startswith("notes/")
            or path.startswith("src/test/")
        )

    disallowed = [path for path in changed_paths if not allowed(path)]
    component_disjoint = [
        path
        for path in changed_paths
        if path in CASE090_COMPONENT_DISJOINT_NUMERICAL_FILES
    ]
    failures = []
    if merge_base != evidence_source_sha:
        failures.append("case090_source_is_not_ancestor_of_current_source")
    if rendered_paths is None:
        failures.append("case090_source_diff_unreadable")
    if disallowed:
        failures.append("numerical_or_unapproved_source_changed_since_case090")
    return {
        "pass": not failures,
        "evidence_source_sha": evidence_source_sha,
        "current_source_sha": current_source_sha,
        "case090_source_is_ancestor": merge_base == evidence_source_sha,
        "compatibility_scope": "case090_pure3d_floquet_core",
        "case090_core_source_unchanged": (
            not disallowed and rendered_paths is not None
        ),
        # Historical compatibility key; see the function docstring.
        "numerical_source_unchanged": not disallowed and rendered_paths is not None,
        "changed_paths": changed_paths,
        "component_disjoint_numerical_changed_paths": component_disjoint,
        "disallowed_changed_paths": disallowed,
        "failures": failures,
    }


def _task034_authority_source_compatibility(
    authority: Mapping[str, Any] | None,
    *,
    degree: int,
    h_nm: float,
    polarization_kind: str = "s",
    current_source_sha: str | None,
) -> dict[str, Any]:
    """Audit a Case092 measured authority against the current clean source."""

    payload = authority if isinstance(authority, Mapping) else {}
    entries = payload.get("entries")
    entries = entries if isinstance(entries, list) else []
    matches = [
        item
        for item in entries
        if isinstance(item, Mapping)
        and item.get("degree") == degree
        and math.isclose(float(item.get("h_nm", math.nan)), float(h_nm))
        and item.get("polarization_kind") == polarization_kind
    ]
    reference = matches[0].get("full3d_reference", {}) if len(matches) == 1 else {}
    reference = reference if isinstance(reference, Mapping) else {}
    if not reference and len(matches) == 1:
        reference = matches[0].get("assembly_resource_anchor", {})
        reference = reference if isinstance(reference, Mapping) else {}
    reference_source_sha = reference.get("source_sha")
    if not (
        isinstance(reference_source_sha, str)
        and len(reference_source_sha) == 40
        and isinstance(current_source_sha, str)
        and len(current_source_sha) == 40
    ):
        return {
            "pass": False,
            "reference_source_sha": reference_source_sha,
            "current_source_sha": current_source_sha,
            "changed_paths": [],
            "disallowed_changed_paths": [],
            "component_disjoint_numerical_changed_paths": [],
            "failures": ["source_sha_missing_or_invalid"],
        }
    if reference_source_sha == current_source_sha:
        return {
            "pass": True,
            "reference_source_sha": reference_source_sha,
            "current_source_sha": current_source_sha,
            "reference_source_is_ancestor": True,
            "changed_paths": [],
            "disallowed_changed_paths": [],
            "component_disjoint_numerical_changed_paths": [],
            "failures": [],
        }
    merge_base = _git("merge-base", reference_source_sha, current_source_sha)
    rendered_paths = _git(
        "diff", "--name-only", f"{reference_source_sha}..{current_source_sha}"
    )
    changed_paths = [] if rendered_paths is None else rendered_paths.splitlines()

    def allowed(path: str) -> bool:
        return bool(
            path in TASK034_AUTHORITY_COMPATIBLE_CHANGED_FILES
            or path.startswith(
                "benchmarks/cases/092_workstation_wsl_adaptive_scalability/"
            )
            or path.startswith("docs/")
            or path.startswith("notes/")
            or path.startswith("src/test/")
        )

    disallowed = [path for path in changed_paths if not allowed(path)]
    component_disjoint = [
        path
        for path in changed_paths
        if path in TASK034_AUTHORITY_COMPONENT_DISJOINT_NUMERICAL_FILES
    ]
    failures = []
    if merge_base != reference_source_sha:
        failures.append("reference_source_is_not_ancestor_of_current_source")
    if rendered_paths is None:
        failures.append("reference_source_diff_unreadable")
    if disallowed:
        failures.append("numerical_or_unapproved_source_changed_since_reference")
    return {
        "pass": not failures,
        "reference_source_sha": reference_source_sha,
        "current_source_sha": current_source_sha,
        "reference_source_is_ancestor": merge_base == reference_source_sha,
        "changed_paths": changed_paths,
        "disallowed_changed_paths": disallowed,
        "component_disjoint_numerical_changed_paths": component_disjoint,
        "failures": failures,
    }


def _watchdog_source_before(verified_clean_sha: str) -> dict[str, Any]:
    head = _git("rev-parse", "HEAD")
    worktree = _git("status", "--short", "--untracked-files=all")
    untracked = [
        line[3:]
        for line in (worktree or "").splitlines()
        if line.startswith("?? ")
    ]
    return {
        "commit_sha": head,
        "head_before_sha": head,
        "head_after_sha": None,
        "verified_clean_sha": verified_clean_sha,
        # Retain the historical key consumed by source_identity_gate, but its
        # value now covers tracked changes plus all nonignored untracked paths.
        "tracked_status_before": worktree,
        "tracked_status_after": None,
        "worktree_status_before": worktree,
        "worktree_status_after": None,
        "nonignored_untracked_before": untracked,
        "nonignored_untracked_after": None,
        "cleanliness_semantics": (
            "git status including all nonignored untracked paths; ignored artifacts excluded"
        ),
        "source_stable_during_run": False,
        "source_clean_verified": bool(
            head == verified_clean_sha and worktree == ""
        ),
    }


def _watchdog_source_after(source: dict[str, Any]) -> dict[str, Any]:
    head = _git("rev-parse", "HEAD")
    worktree = _git("status", "--short", "--untracked-files=all")
    untracked = [
        line[3:]
        for line in (worktree or "").splitlines()
        if line.startswith("?? ")
    ]
    updated = {
        **source,
        "head_after_sha": head,
        "tracked_status_after": worktree,
        "worktree_status_after": worktree,
        "nonignored_untracked_after": untracked,
    }
    updated["source_stable_during_run"] = bool(
        source.get("head_before_sha") == head
        and source.get("tracked_status_before") == ""
        and worktree == ""
    )
    updated["source_clean_verified"] = source_identity_gate(updated)["pass"]
    return updated


def _environment_preflight(snapshot: dict[str, Any]) -> dict[str, Any]:
    checks = {
        "cgroup_current_readable": snapshot.get("memory_current_bytes") is not None,
        "container_limit_readable": snapshot.get("memory_limit_bytes") is not None,
        "host_available_readable": (
            snapshot.get("host_available_memory_bytes") is not None
        ),
        "container_current_swap_zero": snapshot.get("swap_current_bytes") == 0,
        "pswpin_readable": snapshot.get("pswpin_pages") is not None,
        "pswpout_readable": snapshot.get("pswpout_pages") is not None,
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {"pass": not failures, "checks": checks, "failures": failures}


def _worker_command(
    args: argparse.Namespace,
    record_path: Path,
    stage_path: Path,
) -> list[str]:
    if args.target == "qep":
        # ``run`` installs the live effective limit after reading cgroup and
        # host authorities.  Keep the pure command helper usable by contract
        # tests and tooling without ever spelling a bogus ``None`` limit.
        effective_limit_gib = getattr(args, "_qep_effective_limit_gib", None)
        command = [
            "mpiexec",
            "-n",
            str(args.mpi_size),
            sys.executable,
            "-m",
            "benchmarks.run_task033_qep_matrix",
            "--execute",
            "--degree",
            str(args.degree),
            "--h-nm",
            str(args.h_nm),
            "--material-kind",
            args.material_kind,
            "--requested-modes",
            str(args.requested_modes),
            "--left-candidate-modes",
            str(args.candidate_modes),
            "--verified-clean-sha",
            args.verified_clean_sha,
            "--watchdog-enabled-verified",
            "--one-large-case-verified",
            "--output",
            str(record_path),
            "--container-image",
            args.container_image,
            "--container-digest",
            args.container_digest,
            "--host-environment-id",
            args.host_environment_id,
        ]
        if effective_limit_gib is not None:
            command.extend(
                ("--container-limit-gib", str(effective_limit_gib))
            )
        if getattr(args, "_no_swap_verified", True):
            command.append("--no-swap-verified")
        if args.high_order_core_evidence_sha256 is not None:
            command.extend(
                (
                    "--high-order-core-evidence-sha256",
                    args.high_order_core_evidence_sha256,
                )
            )
        return command

    command = [
        "mpiexec",
        "-n",
        str(args.mpi_size),
        sys.executable,
        "-m",
        "benchmarks.run_task032_phase6_augmented",
        "--degree",
        str(args.degree),
        "--h-nm",
        str(args.h_nm),
        "--bottom-interface-nm",
        str(args.bottom_interface_nm),
        "--top-interface-nm",
        str(args.top_interface_nm),
        "--incident-grazing-deg",
        str(args.incident_grazing_deg),
        "--polarization-kind",
        args.polarization_kind,
        "--requested-modes",
        str(args.requested_modes),
        "--candidate-modes",
        str(args.candidate_modes),
        "--solver-path",
        args.solver_path,
        "--comparison-solver-path",
        args.comparison_solver_path,
        "--verified-clean-sha",
        args.verified_clean_sha,
        "--output",
        str(record_path),
        "--memory-stages",
        str(stage_path),
        "--container-image",
        args.container_image,
        "--container-digest",
        args.container_digest,
        "--host-environment-id",
        args.host_environment_id,
    ]
    if args.full3d_reference is not None:
        command.extend(
            ("--full3d-reference", str(args.full3d_reference))
        )
    if args.compare_modal_schur:
        command.append("--compare-modal-schur")
    if args.graded_reference_h is not None:
        command.extend(
            (
                "--graded-reference-h",
                str(args.graded_reference_h),
                "--graded-coarse-factor",
                str(args.graded_coarse_factor),
                "--graded-profile",
                args.graded_profile,
            )
        )
    return command


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json_object(path: Path | None) -> tuple[dict[str, Any] | None, str | None]:
    if path is None:
        return None, "path_not_supplied"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"{type(exc).__name__}: {exc}"
    if not isinstance(payload, dict):
        return None, "json_root_is_not_an_object"
    return payload, None


def _task034_terminal_record_is_complete(record_path: Path) -> bool:
    payload, error = _read_json_object(record_path)
    if error is not None or payload is None:
        return False
    return bool(
        payload.get("schema_version") == 1
        and isinstance(payload.get("benchmark_id"), str)
        and isinstance(payload.get("timestamp_utc"), str)
        and isinstance(payload.get("status"), str)
        and isinstance(payload.get("qualification"), dict)
        and isinstance(payload.get("solve"), dict)
        and isinstance(payload.get("gates"), dict)
    )


def _task034_terminal_worker_drain(
    *,
    task034_workstation_gate: bool,
    process_running: bool,
    authority_readable: bool,
    stage: str | None,
    terminal_record_complete: bool,
    live_worker_count: int | None,
) -> bool:
    """Recognize only the normal worker-before-launcher MPI exit window."""

    return bool(
        task034_workstation_gate
        and process_running
        and not authority_readable
        and stage == "record_and_release"
        and terminal_record_complete
        and live_worker_count == 0
    )


def _resource_readability_sample_is_formal(
    *,
    task034_workstation_gate: bool,
    process_running: bool,
    terminal_worker_drain: bool = False,
) -> bool:
    """Exclude only Task034 samples observed during or after terminal drain.

    A process-tree read racing with ``Popen.poll`` may contain a disappearing
    worker or launcher PID and report ``all_status_readable=False``. Once the
    complete terminal worker record exists and no worker remains, it is not a
    live authority sample. Task033's historical default semantics remain
    unchanged.
    """

    return bool(
        (process_running and not terminal_worker_drain)
        or not task034_workstation_gate
    )


def _authority_unreadable_requires_termination(
    *,
    process_running: bool,
    readability_sample_is_formal: bool,
    authority_readable: bool,
) -> bool:
    """Terminate only when a formal live authority sample is unreadable."""

    return bool(
        process_running
        and readability_sample_is_formal
        and not authority_readable
    )


def _live_task033_worker_rss(
    root_pid: int, target: str
) -> tuple[float | None, list[dict[str, Any]]]:
    """Read the live RSS sum of this watchdog's MPI Python workers.

    The shared legacy sampler does not classify the Task033 QEP module as a
    worker.  Scan ``/proc`` here so both QEP and Hybrid use the same authority
    instead of silently treating the QEP worker sum as zero.
    """

    marker = (
        "benchmarks.run_task033_qep_matrix"
        if target == "qep"
        else "benchmarks.run_task032_phase6_augmented"
    )
    proc = Path("/proc")
    try:
        entries = list(proc.iterdir())
    except OSError:
        return None, []
    workers: list[dict[str, Any]] = []
    for entry in entries:
        if not entry.name.isdigit() or int(entry.name) == root_pid:
            continue
        try:
            cmdline = (
                (entry / "cmdline")
                .read_bytes()
                .replace(b"\0", b" ")
                .decode("utf-8", errors="ignore")
            )
            if marker not in cmdline or "mpiexec" in cmdline.lower():
                continue
            rss_kib = None
            for line in (entry / "status").read_text(
                encoding="utf-8", errors="ignore"
            ).splitlines():
                if line.startswith("VmRSS:"):
                    rss_kib = float(line.split()[1])
                    break
            if rss_kib is None:
                continue
            workers.append(
                {
                    "pid": int(entry.name),
                    "rss_mb": rss_kib / 1024.0,
                }
            )
        except (OSError, ValueError, IndexError):
            continue
    return sum(item["rss_mb"] for item in workers), workers


def _hybrid_measurements(record: dict[str, Any]) -> dict[str, Any]:
    physical = record.get("physical_field_reconstruction") or {}
    validation = record.get("validation") or {}
    return {
        "status": record.get("status"),
        "case": record.get("case"),
        "qep": {
            key: record.get("qep", {}).get(key)
            for key in (
                "full_shape",
                "reduced_shape",
                "field_degree",
                "geometry_degree",
                "coefficient_degree",
                "quadrature_degree",
                "quadrature_policy",
            )
        },
        "hybrid_system": {
            key: record.get("hybrid_system", {}).get(key)
            for key in (
                "primary_solver_path",
                "matrix_size",
                "matrix_stats",
                "bottom_matrix_stats",
                "top_matrix_stats",
                "bottom_global_size",
                "top_global_size",
                "bottom_local_fe_dofs",
                "top_local_fe_dofs",
                "bottom_local_mesh_cells",
                "top_local_mesh_cells",
                "bottom_local_thickness_nm",
                "top_local_thickness_nm",
                "internal_unknown_count",
                "qep_to_interface_quadrature_degree",
                "dense_interface_square_formed",
                "full_field_or_mode_gathered",
                "modal_schur",
            )
        },
        "solve": record.get("solve"),
        "validation": {
            "port_power": validation.get("port_power"),
            "external_diffraction_orders": validation.get(
                "external_diffraction_orders"
            ),
        },
        "physical_field_reconstruction": {
            "interface_continuity": physical.get("interface_continuity"),
            "volume_absorption": physical.get("volume_absorption"),
            "selected_plane_full3d_comparison": physical.get(
                "selected_plane_full3d_comparison"
            ),
            "sample_payload_bytes": physical.get("sample_payload_bytes"),
            "sample_grid_shape_z_y_x_component": physical.get(
                "sample_grid_shape_z_y_x_component"
            ),
            "full_middle_volume_reconstructed": physical.get(
                "full_middle_volume_reconstructed"
            ),
        },
        "full3d_reference_comparison": record.get(
            "full3d_reference_comparison"
        ),
        "modal_schur_comparison": record.get("modal_schur_comparison"),
        "modal_basis_capacity": record.get("modal_basis_capacity"),
        "object_payload_ledger": {
            key: (record.get("object_payload_ledger") or {}).get(key)
            for key in (
                "scalar_bytes",
                "index_bytes",
                "interface_active_dofs",
                "mode_count_per_direction",
                "retained_right_left_eigenvector_bytes",
                "projection_matrix",
                "modal_schur_bytes",
                "local_or_augmented_factor_inventory",
                "storage_complexity_contract",
                "dense_interface_square_formed",
            )
        },
        "gates": record.get("gates"),
        "qualification": record.get("qualification"),
        "timing_seconds_max_rank": record.get("timing_seconds_max_rank"),
    }


def _external_resource_authority(
    rows: list[dict[str, Any]],
    memory: dict[str, Any],
    *,
    environment_before: dict[str, Any],
    environment_after: dict[str, Any],
    live_authority_all_readable: bool,
) -> dict[str, Any]:
    worker_gib = memory.get("max_simultaneous_worker_rss_gib")
    cgroup_gib = memory.get("max_container_cgroup_current_gib")
    worker_bytes = (
        None if worker_gib is None else int(float(worker_gib) * 1024**3)
    )
    cgroup_bytes = (
        None if cgroup_gib is None else int(float(cgroup_gib) * 1024**3)
    )
    dedicated_cgroup = memory.get("dedicated_job_cgroup_observed") is True
    authority = (
        None
        if worker_bytes is None or (dedicated_cgroup and cgroup_bytes is None)
        else max(worker_bytes, cgroup_bytes if dedicated_cgroup else 0)
    )
    limits = [
        environment_before.get("memory_limit_bytes"),
        environment_after.get("memory_limit_bytes"),
    ]
    host_available = [
        environment_before.get("host_available_memory_bytes"),
        environment_after.get("host_available_memory_bytes"),
    ]
    sampled_swap_all_readable = memory.get("job_swap_all_samples_readable") is True
    swap_current = (
        0
        if sampled_swap_all_readable
        and int(memory.get("max_process_tree_swap_bytes") or 0) == 0
        and int(memory.get("max_dedicated_cgroup_swap_bytes") or 0) == 0
        else None
    )
    record = {
        "simultaneous_live_worker_rss_sum_bytes": worker_bytes,
        "container_cgroup_current_bytes": cgroup_bytes,
        "memory_authority_bytes": authority,
        "memory_authority_gib": (
            None if authority is None else authority / 1024**3
        ),
        "memory_authority_semantics": (
            "max(simultaneous live MPI worker RSS sum, container cgroup current)"
        ),
        "container_memory_limit_bytes": (
            None
            if any(value is None for value in limits)
            else min(int(value) for value in limits)
        ),
        "host_available_memory_bytes": (
            None
            if any(value is None for value in host_available)
            else min(int(value) for value in host_available)
        ),
        "container_swap_current_bytes": swap_current,
        "pswpin_delta_pages": memory.get("wsl_pswpin_delta_pages"),
        "pswpout_delta_pages": memory.get("wsl_pswpout_delta_pages"),
        "job_cgroup_dedicated": dedicated_cgroup,
        "wsl_global_pswp_formal": False,
        "wsl_global_pswp_role": "diagnostic_only",
        "job_process_tree_swap_bytes": memory.get("max_process_tree_swap_bytes"),
        "environment_before": environment_before,
        "environment_after": environment_after,
        "all_live_authority_samples_readable": live_authority_all_readable,
        "all_live_swap_samples_readable": sampled_swap_all_readable,
    }
    gate = resource_authority_gate(record)
    extra_checks = {
        "all_live_authority_samples_readable": live_authority_all_readable,
        "all_live_swap_samples_readable": sampled_swap_all_readable,
    }
    gate["checks"].update(extra_checks)
    gate["failures"] = [
        name for name, passed in gate["checks"].items() if not passed
    ]
    gate["pass"] = not gate["failures"]
    record["gate"] = gate
    return record


def _available_physical_core_count() -> int | None:
    allowed = (
        set(os.sched_getaffinity(0))
        if hasattr(os, "sched_getaffinity")
        else set(range(os.cpu_count() or 0))
    )
    try:
        completed = subprocess.run(
            ["lscpu", "-p=CPU,CORE,SOCKET,ONLINE"],
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    physical_cores: set[tuple[int, int]] = set()
    for line in completed.stdout.splitlines():
        if not line or line.startswith("#"):
            continue
        try:
            cpu, core, socket, online = line.split(",")
            if (
                int(cpu) in allowed
                and online.strip().lower() in {"y", "yes"}
            ):
                physical_cores.add((int(socket), int(core)))
        except (TypeError, ValueError):
            return None
    return len(physical_cores) or None


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Task033 external RSS/cgroup/swap/wall-time watchdog for one "
            "QEP or Hybrid shard."
        )
    )
    parser.add_argument("--target", choices=("qep", "hybrid"), required=True)
    parser.add_argument("--case-label", required=True)
    parser.add_argument("--degree", type=int, choices=(1, 2, 3, 4), required=True)
    parser.add_argument("--h-nm", type=float, required=True)
    parser.add_argument(
        "--mpi-size",
        type=int,
        choices=(1, 2, 4, 8, 16, 32),
        required=True,
    )
    parser.add_argument("--requested-modes", type=int, default=8)
    parser.add_argument("--candidate-modes", type=int, default=16)
    parser.add_argument("--material-kind", choices=("air", "lossy_homogeneous", "stage4_xy"))
    parser.add_argument(
        "--solver-path",
        choices=("augmented", "modal-schur-fast", "modal-schur-memory-minimal"),
        default="modal-schur-memory-minimal",
    )
    parser.add_argument("--compare-modal-schur", action="store_true")
    parser.add_argument(
        "--comparison-solver-path",
        choices=("fast", "minimal"),
        default="fast",
        help=(
            "Comparison builder passed to Task32. Task033 augmented comparison "
            "records must explicitly select minimal."
        ),
    )
    parser.add_argument("--bottom-interface-nm", type=float, default=10.0)
    parser.add_argument("--top-interface-nm", type=float, default=110.0)
    parser.add_argument("--graded-reference-h", type=float, choices=(5.0, 3.0))
    parser.add_argument("--graded-coarse-factor", type=float, default=2.0)
    parser.add_argument(
        "--graded-profile",
        choices=("mechanism", "conservative", "balanced", "aggressive"),
        default="mechanism",
    )
    parser.add_argument(
        "--full3d-reference",
        type=Path,
        help="Explicit same-p/h full3D descriptor for Hybrid field closure.",
    )
    parser.add_argument("--incident-grazing-deg", type=float, default=10.0)
    parser.add_argument(
        "--polarization-kind", choices=("s", "p"), default="s"
    )
    parser.add_argument("--m160-funnel-evidence-file", type=Path)
    parser.add_argument("--m160-funnel-evidence-sha256")
    parser.add_argument("--high-order-core-evidence-sha256")
    parser.add_argument("--high-order-core-evidence-file", type=Path)
    parser.add_argument(
        "--resource-matrix",
        type=Path,
        default=DEFAULT_RESOURCE_MATRIX,
        help=(
            "Checked Case091 resource matrix. Hybrid launches are fail-closed "
            "when the matching p/h decision cannot be verified."
        ),
    )
    parser.add_argument(
        "--task034-workstation-gate",
        action="store_true",
        help=(
            "Explicitly use the Task034 WSL dynamic workstation Gate. Task033's "
            "14 GiB Case091 policy remains unchanged when this flag is absent."
        ),
    )
    parser.add_argument(
        "--task034-workstation-resource-authority",
        type=Path,
        default=TASK034_WORKSTATION_RESOURCE_AUTHORITY,
        help="Tracked Case092 measured launch-authority record.",
    )
    parser.add_argument("--task034-workstation-resource-authority-sha256")
    parser.add_argument(
        "--task034-workstation-resource-anchor",
        type=Path,
        help=(
            "Explicit p4/h5 E0 assembly watchdog record used only as the "
            "pre-E2 Task034 launch resource anchor."
        ),
    )
    parser.add_argument(
        "--task033-same-sha-anchor-requalification",
        action="store_true",
        help=(
            "Explicitly authorize one p2/h3 10/110 nm primary minimal M80/M120/M160 "
            "shard for Task033 same-SHA formal requalification. The default still "
            "reuses and does not rerun the Task032 anchor."
        ),
    )
    parser.add_argument("--verified-clean-sha", required=True)
    parser.add_argument("--poll-interval", type=float, default=0.25)
    parser.add_argument("--warning-gib", type=float, default=11.211267857142857)
    parser.add_argument("--terminate-gib", type=float, default=12.673607142857142)
    parser.add_argument("--timeout-seconds", type=float, default=900.0)
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--summary-output", type=Path)
    parser.add_argument("--container-image", default="myfenics-stage4:task28")
    parser.add_argument(
        "--container-digest",
        default=(
            "sha256:08c61b2cde742442b0031437dbc5160db979494587e6b6364f7935beb29dd76d"
        ),
    )
    parser.add_argument("--host-environment-id", default="windows-docker-desktop")
    args = parser.parse_args(argv)
    if (
        args.mpi_size not in (1, 2, 4)
        and not args.task034_workstation_gate
    ):
        parser.error("MPI8/16/32 require --task034-workstation-gate.")
    if args.target == "qep" and args.material_kind is None:
        parser.error("--target qep requires --material-kind.")
    if args.target == "hybrid" and args.requested_modes < 2:
        parser.error("Hybrid requested modes must be at least two.")
    if not 0.0 < args.incident_grazing_deg < 90.0:
        parser.error("--incident-grazing-deg must lie strictly between 0 and 90.")
    if args.candidate_modes < args.requested_modes:
        parser.error("--candidate-modes must be at least --requested-modes.")
    if (
        args.target == "hybrid"
        and args.candidate_modes != 2 * args.requested_modes
    ):
        parser.error(
            "Hybrid --candidate-modes must equal exactly twice "
            "--requested-modes so Task32 can retain M forward and M backward "
            "modes."
        )
    if (
        args.target == "qep"
        and args.candidate_modes
        < task033_left_candidate_pool_size(args.requested_modes)
    ):
        parser.error(
            "QEP --candidate-modes must satisfy the audited adjoint-pool "
            "oversampling policy."
        )
    if args.target == "hybrid" and args.requested_modes == 240:
        if (
            args.m160_funnel_evidence_file is None
            or args.m160_funnel_evidence_sha256 is None
        ):
            parser.error(
                "Conditional M240 requires the M80/M120/M160 funnel evidence "
                "file and its raw SHA-256."
            )
    if not args.warning_gib < args.terminate_gib:
        parser.error("--warning-gib must be lower than --terminate-gib.")
    if args.timeout_seconds <= 0.0:
        parser.error("--timeout-seconds must be positive.")
    if args.task033_same_sha_anchor_requalification:
        scoped = bool(
            args.target == "hybrid"
            and args.degree == 2
            and math.isclose(args.h_nm, 3.0)
            and args.requested_modes in (80, 120, 160)
            and args.candidate_modes == 2 * args.requested_modes
            and args.solver_path == "modal-schur-memory-minimal"
            and not args.compare_modal_schur
            and args.graded_reference_h is None
            and math.isclose(args.bottom_interface_nm, 10.0)
            and math.isclose(args.top_interface_nm, 110.0)
            and math.isclose(args.incident_grazing_deg, 10.0)
            and args.polarization_kind == "s"
        )
        if not scoped:
            parser.error(
                "--task033-same-sha-anchor-requalification is restricted to the "
                "uniform p2/h3 10/110 nm primary modal-schur-memory-minimal "
                "M80/M120/M160 funnel with an exact 2M candidate pool."
            )
    if args.task034_workstation_gate:
        p4_anchor_is_exclusive = bool(
            (args.full3d_reference is None)
            != (args.task034_workstation_resource_anchor is None)
        )
        p2_h1_resource_anchor_scope = bool(
            args.degree == 2
            and math.isclose(args.h_nm, 1.0)
            and args.polarization_kind == "s"
            and args.mpi_size == 8
            and args.requested_modes == 160
            and args.full3d_reference is None
            and args.task034_workstation_resource_anchor is not None
        )
        p3_h2_resource_anchor_scope = bool(
            args.degree == 3
            and math.isclose(args.h_nm, 2.0)
            and args.polarization_kind == "s"
            and args.mpi_size == 8
            and args.requested_modes == 160
            and args.full3d_reference is None
            and args.task034_workstation_resource_anchor is not None
        )
        p4_h3_resource_anchor_scope = bool(
            args.degree == 4
            and math.isclose(args.h_nm, 3.0)
            and args.polarization_kind == "s"
            and args.mpi_size == 8
            and args.requested_modes == 160
            and args.full3d_reference is None
            and args.task034_workstation_resource_anchor is not None
        )
        phase_f_matrix = {
            (2, 5.0), (2, 3.0), (2, 2.0), (2, 1.0),
            (3, 10.0), (3, 7.5), (3, 5.0), (3, 3.0), (3, 2.0),
            (4, 10.0), (4, 7.5), (4, 5.0), (4, 3.0),
        }
        anchor_selection_valid = bool(
            (
                (args.degree, args.h_nm) in phase_f_matrix
                and not (
                    args.degree == 2 and math.isclose(args.h_nm, 1.0)
                    or (
                        args.degree == 3
                        and math.isclose(args.h_nm, 2.0)
                    )
                    or (
                        args.degree == 4
                        and math.isclose(args.h_nm, 3.0)
                    )
                )
                and args.full3d_reference is not None
                and args.task034_workstation_resource_anchor is None
            )
            or (
                args.degree == 4
                and math.isclose(args.h_nm, 5.0)
                and p4_anchor_is_exclusive
            )
            or p2_h1_resource_anchor_scope
            or p3_h2_resource_anchor_scope
            or p4_h3_resource_anchor_scope
        )
        approved_p_scope = bool(
            args.polarization_kind == "p"
            and args.degree == 2
            and math.isclose(args.h_nm, 5.0)
            and args.mpi_size == 8
            and args.requested_modes == 160
        )
        approved_p2_h1_scope = bool(
            not (args.degree == 2 and math.isclose(args.h_nm, 1.0))
            or p2_h1_resource_anchor_scope
        )
        approved_p3_h2_scope = bool(
            not (args.degree == 3 and math.isclose(args.h_nm, 2.0))
            or p3_h2_resource_anchor_scope
        )
        approved_p4_h3_scope = bool(
            not (args.degree == 4 and math.isclose(args.h_nm, 3.0))
            or p4_h3_resource_anchor_scope
        )
        scoped = bool(
            args.target == "hybrid"
            and (args.degree, args.h_nm) in phase_f_matrix
            and args.requested_modes in (80, 120, 160, 240)
            and args.candidate_modes == 2 * args.requested_modes
            and args.solver_path == "modal-schur-memory-minimal"
            and args.comparison_solver_path == "fast"
            and not args.compare_modal_schur
            and args.graded_reference_h is None
            and math.isclose(args.bottom_interface_nm, 10.0)
            and math.isclose(args.top_interface_nm, 110.0)
            and math.isclose(args.incident_grazing_deg, 10.0)
            and (args.polarization_kind == "s" or approved_p_scope)
            and approved_p2_h1_scope
            and approved_p3_h2_scope
            and approved_p4_h3_scope
            and anchor_selection_valid
            and args.host_environment_id == "WSL2-Ubuntu-24.04"
            and isinstance(
                args.task034_workstation_resource_authority_sha256, str
            )
            and len(args.task034_workstation_resource_authority_sha256) == 64
        )
        if not scoped:
            parser.error(
                "--task034-workstation-gate is restricted to the Task034 fixed "
                "p2/p3/p4 Phase F matrix, WSL Hybrid M80/M120/M160 "
                "(conditional M240) funnel, exact 2M pool, a same-p/h Full-3D "
                "watchdog/descriptor reference (or an explicitly authorized "
                "assembly-only resource anchor), canonical resource authority, "
                "and WSL2-Ubuntu-24.04 identity."
                " The only P-polarized exception is the user-approved "
                "p2/h5 MPI8 M160 capability example. The p2/h1 S added point "
                "and the p3/h2 S added point are each restricted to MPI8 M160 "
                "with their candidate-specific assembly resource anchor. The "
                "p4/h3 S added point has the same MPI8 M160-only restriction."
            )
    return args


def _formal_shard_pass(
    *,
    return_code: int,
    numerical_pass: bool,
    resource_gate_pass: bool,
    source_gate_pass: bool,
    launch_gate_pass: bool,
    terminated_for_memory: bool,
    terminated_for_timeout: bool,
    terminated_for_authority_unreadable: bool,
) -> bool:
    """Centralize the fail-closed measured-shard promotion contract."""

    return bool(
        return_code == 0
        and numerical_pass
        and resource_gate_pass
        and source_gate_pass
        and launch_gate_pass
        and not terminated_for_memory
        and not terminated_for_timeout
        and not terminated_for_authority_unreadable
    )


def run(args: argparse.Namespace) -> int:
    source_before = _watchdog_source_before(args.verified_clean_sha)
    environment_before = _resource_environment_snapshot()
    environment_preflight = _environment_preflight(environment_before)
    effective = effective_memory_limit()
    if args.task034_workstation_gate:
        warning_bytes = effective.get("warning_bytes")
        termination_bytes = effective.get("termination_bytes")
        if (
            type(warning_bytes) is int
            and warning_bytes > 0
            and type(termination_bytes) is int
            and termination_bytes > warning_bytes
        ):
            args.warning_gib = warning_bytes / 1024**3
            args.terminate_gib = termination_bytes / 1024**3
    finite_authorities = (
        effective.get("effective_limit_bytes"),
        environment_before.get("host_available_memory_bytes"),
    )
    environment_before["task034_effective_limit"] = effective
    args._qep_effective_limit_gib = (
        None
        if any(
            not isinstance(value, int) or value <= 0
            for value in finite_authorities
        )
        else min(int(value) for value in finite_authorities) / 1024**3
    )
    source_preflight_gate = {
        "pass": source_before["source_clean_verified"],
        "failures": (
            []
            if source_before["source_clean_verified"]
            else ["pre_run_full_sha_or_complete_nonignored_worktree_clean_gate_failed"]
        ),
    }
    core_path = args.high_order_core_evidence_file
    if core_path is not None and not core_path.is_absolute():
        core_path = ROOT / core_path
    core_evidence, core_read_error = (
        _read_json_object(core_path)
        if args.degree >= 3
        else (None, None)
    )
    core_source_compatibility = _case090_source_compatibility(
        core_evidence,
        current_source_sha=source_before.get("commit_sha"),
    )
    m160_funnel_path = args.m160_funnel_evidence_file
    if m160_funnel_path is not None and not m160_funnel_path.is_absolute():
        m160_funnel_path = ROOT / m160_funnel_path
    m160_funnel_evidence, m160_funnel_read_error = (
        _read_json_object(m160_funnel_path)
        if args.target == "hybrid" and args.requested_modes == 240
        else (None, None)
    )
    observed_m160_funnel_sha256 = (
        _sha256(m160_funnel_path)
        if m160_funnel_path is not None
        else None
    )
    if args.target == "hybrid":
        if args.task034_workstation_gate:
            authority_path = args.task034_workstation_resource_authority
            if not authority_path.is_absolute():
                authority_path = ROOT / authority_path
            authority_path = authority_path.resolve()
            authority_is_canonical = (
                authority_path == TASK034_WORKSTATION_RESOURCE_AUTHORITY.resolve()
            )
            try:
                authority_relative = authority_path.relative_to(ROOT).as_posix()
            except ValueError:
                authority_relative = None
            authority_is_tracked = bool(
                authority_relative is not None
                and _git(
                    "ls-files", "--error-unmatch", "--", authority_relative
                )
                is not None
            )
            authority, authority_read_error = _read_json_object(authority_path)
            authority_observed_sha256 = _sha256(authority_path)
            authority_source_compatibility = (
                _task034_authority_source_compatibility(
                    authority,
                    degree=args.degree,
                    h_nm=args.h_nm,
                    polarization_kind=args.polarization_kind,
                    current_source_sha=source_before.get("commit_sha"),
                )
            )
            full3d_path = args.full3d_reference
            if full3d_path is not None and not full3d_path.is_absolute():
                full3d_path = ROOT / full3d_path
            full3d_path = None if full3d_path is None else full3d_path.resolve()
            full3d_reference_sha256 = (
                None if full3d_path is None else _sha256(full3d_path)
            )
            resource_anchor_path = args.task034_workstation_resource_anchor
            if (
                resource_anchor_path is not None
                and not resource_anchor_path.is_absolute()
            ):
                resource_anchor_path = ROOT / resource_anchor_path
            resource_anchor_path = (
                None
                if resource_anchor_path is None
                else resource_anchor_path.resolve()
            )
            resource_anchor_sha256 = (
                None
                if resource_anchor_path is None
                else _sha256(resource_anchor_path)
            )
            core_gate = high_order_core_evidence_gate(
                args.degree,
                core_evidence,
                expected_sha256=args.high_order_core_evidence_sha256,
                current_source_sha=source_before.get("commit_sha"),
                source_compatibility=core_source_compatibility,
            )
            launch_gate = task034_workstation_hybrid_launch_gate(
                authority,
                authority_expected_sha256=(
                    args.task034_workstation_resource_authority_sha256
                ),
                authority_observed_sha256=authority_observed_sha256,
                degree=args.degree,
                h_nm=args.h_nm,
                requested_modes=args.requested_modes,
                candidate_modes=args.candidate_modes,
                solver_path=args.solver_path,
                comparison_solver_path=args.comparison_solver_path,
                bottom_interface_nm=args.bottom_interface_nm,
                top_interface_nm=args.top_interface_nm,
                incident_grazing_deg=args.incident_grazing_deg,
                polarization_kind=args.polarization_kind,
                effective_limit=effective,
                warning_gib=args.warning_gib,
                terminate_gib=args.terminate_gib,
                core_gate=core_gate,
                mpi_size=args.mpi_size,
                available_physical_core_count=_available_physical_core_count(),
                current_source_sha=source_before.get("commit_sha"),
                source_compatibility=authority_source_compatibility,
                source_clean_verified=source_before["source_clean_verified"],
                authority_is_canonical=authority_is_canonical,
                authority_is_tracked=authority_is_tracked,
                external_watchdog_active=True,
                full3d_reference_sha256=full3d_reference_sha256,
                resource_anchor_sha256=resource_anchor_sha256,
                m160_funnel_evidence=m160_funnel_evidence,
                expected_m160_funnel_sha256=(
                    args.m160_funnel_evidence_sha256
                ),
                observed_m160_funnel_sha256=observed_m160_funnel_sha256,
            )
            launch_gate.update(
                {
                    "resource_authority_path": str(authority_path),
                    "resource_authority_read_error": authority_read_error,
                    "resource_authority_observed_sha256": (
                        authority_observed_sha256
                    ),
                    "full3d_reference_path": (
                        None if full3d_path is None else str(full3d_path)
                    ),
                    "full3d_reference_observed_sha256": (
                        full3d_reference_sha256
                    ),
                    "resource_anchor_path": (
                        None
                        if resource_anchor_path is None
                        else str(resource_anchor_path)
                    ),
                    "resource_anchor_observed_sha256": resource_anchor_sha256,
                    "m160_funnel_evidence_path": (
                        None
                        if m160_funnel_path is None
                        else str(m160_funnel_path)
                    ),
                    "m160_funnel_evidence_read_error": (
                        m160_funnel_read_error
                    ),
                }
            )
            launch_gate["checks"].update(
                {
                    "task034_resource_authority_readable": (
                        authority_read_error is None
                    ),
                    "task034_measured_resource_anchor_readable": (
                        full3d_reference_sha256 is not None
                        or resource_anchor_sha256 is not None
                    ),
                }
            )
            launch_gate["failures"] = [
                name
                for name, passed in launch_gate["checks"].items()
                if not passed
            ]
            launch_gate["pass"] = not launch_gate["failures"]
            launch_gate["launch_eligible_recomputed"] = launch_gate["pass"]
        else:
            resource_matrix_path = args.resource_matrix
            if not resource_matrix_path.is_absolute():
                resource_matrix_path = ROOT / resource_matrix_path
            resource_matrix_path = resource_matrix_path.resolve()
            canonical_resource_matrices = {
                DEFAULT_RESOURCE_MATRIX.resolve(),
                REDUCED_EQUAL_ACCURACY_RESOURCE_MATRIX.resolve(),
            }
            resource_matrix_is_canonical = (
                resource_matrix_path in canonical_resource_matrices
            )
            try:
                matrix_relative = resource_matrix_path.relative_to(ROOT).as_posix()
            except ValueError:
                matrix_relative = None
            resource_matrix_is_tracked = bool(
                matrix_relative is not None
                and _git("ls-files", "--error-unmatch", "--", matrix_relative)
                is not None
            )
            resource_matrix, resource_matrix_read_error = _read_json_object(
                resource_matrix_path
            )
            launch_gate = hybrid_launch_gate(
                resource_matrix,
                degree=args.degree,
                h_nm=args.h_nm,
                requested_modes=args.requested_modes,
                candidate_modes=args.candidate_modes,
                solver_path=args.solver_path,
                compare_modal_schur=args.compare_modal_schur,
                comparison_solver_path=args.comparison_solver_path,
                bottom_interface_nm=args.bottom_interface_nm,
                top_interface_nm=args.top_interface_nm,
                graded_reference_h=args.graded_reference_h,
                incident_grazing_deg=args.incident_grazing_deg,
                polarization_kind=args.polarization_kind,
                container_limit_bytes=environment_before.get("memory_limit_bytes"),
                host_available_memory_bytes=environment_before.get(
                    "host_available_memory_bytes"
                ),
                warning_gib=args.warning_gib,
                terminate_gib=args.terminate_gib,
                core_evidence=core_evidence,
                expected_core_sha256=args.high_order_core_evidence_sha256,
                current_source_sha=source_before.get("commit_sha"),
                source_compatibility=core_source_compatibility,
                m160_funnel_evidence=m160_funnel_evidence,
                expected_m160_funnel_sha256=(
                    args.m160_funnel_evidence_sha256
                ),
                observed_m160_funnel_sha256=observed_m160_funnel_sha256,
                task033_same_sha_anchor_requalification=(
                    args.task033_same_sha_anchor_requalification
                ),
                source_clean_verified=source_before["source_clean_verified"],
                resource_matrix_is_canonical=resource_matrix_is_canonical,
                resource_matrix_is_tracked=resource_matrix_is_tracked,
                external_watchdog_active=True,
            )
            launch_gate["resource_matrix_path"] = str(resource_matrix_path)
            launch_gate["resource_matrix_read_error"] = resource_matrix_read_error
            launch_gate["m160_funnel_evidence_path"] = (
                None if m160_funnel_path is None else str(m160_funnel_path)
            )
            launch_gate["m160_funnel_evidence_read_error"] = (
                m160_funnel_read_error
            )
            launch_gate["checks"].update(
                {
                    "canonical_case091_resource_matrix_path": (
                        resource_matrix_is_canonical
                    ),
                    "case091_resource_matrix_is_git_tracked": (
                        resource_matrix_is_tracked
                    ),
                }
            )
            launch_gate["failures"] = [
                name
                for name, passed in launch_gate["checks"].items()
                if not passed
            ]
            launch_gate["pass"] = not launch_gate["failures"]
            launch_gate["launch_eligible_recomputed"] = launch_gate["pass"]
    else:
        core_gate = high_order_core_evidence_gate(
            args.degree,
            core_evidence,
            expected_sha256=args.high_order_core_evidence_sha256,
            current_source_sha=source_before.get("commit_sha"),
            source_compatibility=core_source_compatibility,
        )
        launch_gate = {
            "pass": bool(
                core_gate["pass"]
                and args._qep_effective_limit_gib is not None
            ),
            "launch_eligible_recomputed": bool(
                core_gate["pass"]
                and args._qep_effective_limit_gib is not None
            ),
            "scope": "qep_component_uses_its_own_two_center_preflight",
            "qep_effective_limit_gib_forwarded_to_worker": (
                args._qep_effective_limit_gib
            ),
            "high_order_core_evidence": core_gate,
            "failures": [
                *core_gate["failures"],
                *(
                    []
                    if args._qep_effective_limit_gib is not None
                    else ["finite_qep_effective_limit_unavailable"]
                ),
            ],
        }
    launch_gate["high_order_core_evidence_file"] = (
        None if core_path is None else str(core_path)
    )
    launch_gate["high_order_core_evidence_read_error"] = core_read_error
    if args.degree >= 3 and core_read_error is not None:
        launch_gate["pass"] = False
        launch_gate["launch_eligible_recomputed"] = False
        launch_gate.setdefault("failures", []).append(
            "high_order_core_evidence_file_unreadable"
        )
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = (
        args.run_dir
        or args.artifact_root
        / f"{args.case_label}_{args.target}_p{args.degree}_h{args.h_nm:g}_mpi{args.mpi_size}_{timestamp}"
    ).resolve()
    run_dir.mkdir(parents=True, exist_ok=False)
    preflight_pass = bool(
        source_preflight_gate["pass"]
        and environment_preflight["pass"]
        and launch_gate["pass"]
    )
    if not preflight_pass:
        summary = {
            "schema_version": "task033.memory-watchdog.v2",
            "benchmark_id": "task033_external_memory_watchdog",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "status": "formal_not_pass",
            "target": args.target,
            "case_label": args.case_label,
            "launch_state": "not_run_preflight_failed",
            "formal_pass": False,
            "memory_authority_pass": False,
            "physical_qualified": False,
            "source": source_before,
            "source_gate": source_preflight_gate,
            "launch_gate": launch_gate,
            "task033_anchor_requalification": launch_gate.get(
                "task033_anchor_requalification"
            ),
            "resource_authority": {
                "environment_before": environment_before,
                "preflight": environment_preflight,
                "gate": {"pass": False, "failures": ["run_not_started"]},
            },
            "requested_modes": args.requested_modes,
            "measurements": None,
        }
        rendered = json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
        (run_dir / "memory_sampler_summary.json").write_text(
            rendered, encoding="utf-8"
        )
        if args.summary_output is not None:
            promoted = (
                args.summary_output
                if args.summary_output.is_absolute()
                else ROOT / args.summary_output
            )
            promoted.parent.mkdir(parents=True, exist_ok=True)
            promoted.write_text(rendered, encoding="utf-8")
        print(rendered, end="")
        return 2

    core_gate = launch_gate.get("high_order_core_evidence", {})
    if args.degree >= 3:
        args.high_order_core_evidence_sha256 = core_gate.get("evidence_sha256")
    args._no_swap_verified = True
    record_path = run_dir / "solver_record.json"
    stage_path = run_dir / "memory_stages.jsonl"
    timeline_path = run_dir / "memory_timeline.csv"
    stdout_path = run_dir / "worker_stdout.txt"
    command = _worker_command(args, record_path, stage_path)
    environment = os.environ.copy()
    environment.update(
        {
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
            "BENCHMARK_EXACT_COMMAND": " ".join(command),
        }
    )

    rows: list[dict[str, Any]] = []
    started = time.perf_counter()
    warning_triggered = False
    terminated_for_memory = False
    terminated_for_timeout = False
    terminated_for_authority_unreadable = False
    live_authority_all_readable = True
    job_swap_all_samples_readable = True
    max_process_tree_swap_bytes = 0
    max_dedicated_cgroup_swap_bytes = 0
    dedicated_job_cgroup_observed = False
    post_exit_readability_samples_excluded = 0
    terminal_worker_drain_samples_excluded = 0
    max_live_authority_gib = 0.0
    with stdout_path.open("w", encoding="utf-8") as stdout:
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            stdout=stdout,
            stderr=subprocess.STDOUT,
            text=True,
            env=environment,
        )
        previous: dict[str, Any] | None = None
        while True:
            elapsed = time.perf_counter() - started
            row = _sample(process.pid, stage_path, elapsed)
            job_sample = resource_authority_sample(process.pid)
            process_tree = job_sample["process_tree"]
            job_cgroup = job_sample["job_cgroup"]
            live_worker_rss_mb = float(process_tree["rss_bytes"]) / 1024**2
            live_workers = [
                {"pid": pid, "scope": "process_tree"}
                for pid in process_tree["pids"]
            ]
            row["worker_rank_rss_sum_mb"] = live_worker_rss_mb
            row["worker_rank_rss_mb_json"] = json.dumps(
                live_workers, separators=(",", ":")
            )
            row["mpi_process_tree_swap_mb"] = (
                float(process_tree["swap_bytes"]) / 1024**2
            )
            row["job_cgroup_path"] = job_cgroup["path"]
            row["job_cgroup_dedicated"] = job_cgroup["dedicated_job_cgroup"]
            if job_cgroup["dedicated_job_cgroup"]:
                row["container_cgroup_current_mb"] = (
                    None if job_cgroup["memory_current_bytes"] is None
                    else float(job_cgroup["memory_current_bytes"]) / 1024**2
                )
                row["container_swap_current_mb"] = (
                    None if job_cgroup["swap_current_bytes"] is None
                    else float(job_cgroup["swap_current_bytes"]) / 1024**2
                )
            else:
                row["container_cgroup_current_mb"] = None
                row["container_swap_current_mb"] = None
            process_running = process.poll() is None
            cgroup_current_mb = row.get("container_cgroup_current_mb")
            authority_readable = bool(
                process_tree["all_status_readable"]
                and (
                    not job_cgroup["dedicated_job_cgroup"]
                    or cgroup_current_mb is not None
                )
            )
            live_worker_count: int | None = None
            terminal_record_complete = False
            if (
                args.task034_workstation_gate
                and process_running
                and not authority_readable
                and row.get("stage") == "record_and_release"
            ):
                terminal_record_complete = (
                    _task034_terminal_record_is_complete(record_path)
                )
                live_worker_rss, discovered_workers = (
                    _live_task033_worker_rss(process.pid, args.target)
                )
                if live_worker_rss is not None:
                    process_tree_pids = set(process_tree["pids"])
                    live_worker_count = sum(
                        int(worker["pid"]) in process_tree_pids
                        for worker in discovered_workers
                    )
            terminal_worker_drain = _task034_terminal_worker_drain(
                task034_workstation_gate=args.task034_workstation_gate,
                process_running=process_running,
                authority_readable=authority_readable,
                stage=row.get("stage"),
                terminal_record_complete=terminal_record_complete,
                live_worker_count=live_worker_count,
            )
            readability_sample_is_formal = _resource_readability_sample_is_formal(
                task034_workstation_gate=args.task034_workstation_gate,
                process_running=process_running,
                terminal_worker_drain=terminal_worker_drain,
            )
            if readability_sample_is_formal:
                job_swap_all_samples_readable &= bool(
                    process_tree["all_status_readable"]
                )
                max_process_tree_swap_bytes = max(
                    max_process_tree_swap_bytes, int(process_tree["swap_bytes"])
                )
                if job_cgroup["dedicated_job_cgroup"]:
                    dedicated_job_cgroup_observed = True
                    if job_cgroup["swap_current_bytes"] is None:
                        job_swap_all_samples_readable = False
                    else:
                        max_dedicated_cgroup_swap_bytes = max(
                            max_dedicated_cgroup_swap_bytes,
                            int(job_cgroup["swap_current_bytes"]),
                        )
            elif terminal_worker_drain:
                terminal_worker_drain_samples_excluded += 1
            else:
                post_exit_readability_samples_excluded += 1
            _add_cpu_core_equivalents(row, previous)
            previous = row
            rows.append(row)
            if readability_sample_is_formal:
                live_authority_all_readable &= authority_readable
            live_authority_gib = (
                None
                if not readability_sample_is_formal or not authority_readable
                else max(
                    float(live_worker_rss_mb), float(cgroup_current_mb or 0.0)
                ) / 1024.0
            )
            if live_authority_gib is not None:
                max_live_authority_gib = max(
                    max_live_authority_gib, live_authority_gib
                )
                warning_triggered |= live_authority_gib >= args.warning_gib
            if _authority_unreadable_requires_termination(
                process_running=process_running,
                readability_sample_is_formal=readability_sample_is_formal,
                authority_readable=authority_readable,
            ):
                terminated_for_authority_unreadable = True
                process.terminate()
            if (
                process_running
                and live_authority_gib is not None
                and live_authority_gib >= args.terminate_gib
            ):
                terminated_for_memory = True
                process.terminate()
            if process_running and elapsed >= args.timeout_seconds:
                terminated_for_timeout = True
                process.terminate()
            if not process_running:
                break
            time.sleep(max(args.poll_interval, 0.05))
        return_code = int(process.returncode or 0)

    with timeline_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=TIMELINE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    solver_record = (
        json.loads(record_path.read_text(encoding="utf-8"))
        if record_path.is_file()
        else {}
    )
    memory = _sampler_summary(rows, poll_interval=args.poll_interval)
    memory.update(
        {
            "job_swap_all_samples_readable": job_swap_all_samples_readable,
            "max_process_tree_swap_bytes": max_process_tree_swap_bytes,
            "max_dedicated_cgroup_swap_bytes": max_dedicated_cgroup_swap_bytes,
            "dedicated_job_cgroup_observed": dedicated_job_cgroup_observed,
            "post_exit_readability_samples_excluded": (
                post_exit_readability_samples_excluded
            ),
            "terminal_worker_drain_samples_excluded": (
                terminal_worker_drain_samples_excluded
            ),
        }
    )
    environment_after = _resource_environment_snapshot()
    environment_after["task034_effective_limit"] = effective_memory_limit()
    source = _watchdog_source_after(source_before)
    resource_authority = _external_resource_authority(
        rows,
        memory,
        environment_before=environment_before,
        environment_after=environment_after,
        live_authority_all_readable=live_authority_all_readable,
    )
    resource_authority["live_control_peak_authority_gib"] = max_live_authority_gib
    resource_authority["live_control_semantics"] = (
        "Every warning and controlled termination decision used "
        "max(live Task033 MPI worker RSS sum, cgroup memory.current)."
    )
    resource_gate = resource_authority["gate"]
    source_gate = source_identity_gate(source)
    no_swap = bool(
        resource_gate["checks"].get("container_current_swap_zero")
        and resource_gate["checks"].get("all_live_swap_samples_readable")
        and max_process_tree_swap_bytes == 0
        and max_dedicated_cgroup_swap_bytes == 0
    )
    if args.target == "qep":
        numerical_pass = solver_record.get("status") == "measured_shard_pass"
        measurements: dict[str, Any] = solver_record
    else:
        qualification = solver_record.get("qualification", {})
        numerical_pass = bool(
            qualification.get("integration_pass")
            and qualification.get("task033_physical_truncation_allowed")
        )
        measurements = _hybrid_measurements(solver_record)
    formal_pass = _formal_shard_pass(
        return_code=return_code,
        numerical_pass=numerical_pass,
        resource_gate_pass=resource_gate["pass"],
        source_gate_pass=source_gate["pass"],
        launch_gate_pass=launch_gate["pass"],
        terminated_for_memory=terminated_for_memory,
        terminated_for_timeout=terminated_for_timeout,
        terminated_for_authority_unreadable=(
            terminated_for_authority_unreadable
        ),
    )
    summary = {
        "schema_version": "task033.memory-watchdog.v2",
        "benchmark_id": "task033_external_memory_watchdog",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "status": "measured_shard_pass" if formal_pass else "formal_not_pass",
        "target": args.target,
        "case_label": args.case_label,
        "command": command,
        "return_code": return_code,
        "numeric_pass": numerical_pass,
        "formal_pass": formal_pass,
        "memory_authority_pass": resource_gate["pass"],
        "physical_qualified": False,
        "qualification_identity": (
            "measured_shard_pass_requires_funnel_aggregate_for_physical_qualification"
        ),
        "requested_modes": args.requested_modes,
        "candidate_modes": args.candidate_modes,
        "no_swap": no_swap,
        "warning_threshold_gib": args.warning_gib,
        "termination_threshold_gib": args.terminate_gib,
        "wall_time_limit_seconds": args.timeout_seconds,
        "warning_triggered": warning_triggered,
        "terminated_for_memory": terminated_for_memory,
        "terminated_for_timeout": terminated_for_timeout,
        "terminated_for_authority_unreadable": (
            terminated_for_authority_unreadable
        ),
        "memory": memory,
        "resource_authority": resource_authority,
        "launch_gate": launch_gate,
        "task033_anchor_requalification": launch_gate.get(
            "task033_anchor_requalification"
        ),
        "source": source,
        "source_gate": source_gate,
        "worker_source": solver_record.get("metadata")
        or solver_record.get("provenance"),
        "solver_record_sha256": _sha256(record_path),
        "solver_record_ignored_path": str(record_path.relative_to(ROOT)),
        "timeline_ignored_path": str(timeline_path.relative_to(ROOT)),
        "stdout_ignored_path": str(stdout_path.relative_to(ROOT)),
        "measurements": measurements,
        "memory_semantics": (
            "Authority is max(simultaneous live MPI worker RSS sum, container "
            "dedicated job cgroup current when present); process-tree VmSwap and "
            "dedicated cgroup swap must be zero. WSL-global pswp is diagnostic only."
        ),
    }
    summary_path = run_dir / "memory_sampler_summary.json"
    rendered = json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    summary_path.write_text(rendered, encoding="utf-8")
    if args.summary_output is not None:
        promoted = (
            args.summary_output
            if args.summary_output.is_absolute()
            else ROOT / args.summary_output
        )
        promoted.parent.mkdir(parents=True, exist_ok=True)
        promoted.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if formal_pass else (return_code or 2)


def main(argv: list[str] | None = None) -> int:
    return run(_parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
