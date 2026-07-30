#!/usr/bin/env python3
"""One-shot Task035e goal-oriented selective-trace worker.

This helper has four narrow operations: prepare the two same-mesh plans,
capture one exact M1 reduced snapshot, reuse one global-p6 factor for the six
deduplicated failed-goal adjoints, and run/evaluate the single frozen actual
candidate.  It is not a campaign controller.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
import gc
import hashlib
import json
import os
from pathlib import Path
import subprocess
from typing import Any, Mapping

from mpi4py import MPI
import numpy as np
from petsc4py import PETSc
from scipy import sparse


ROOT = Path(__file__).resolve().parents[3]
SIGNIFICANT_AUTHORITY = (
    ROOT
    / "benchmarks/cases/095_high_order_local_hp_resource_envelope/"
    "records/significant_channel_reference_v1.json"
)
REFERENCE_PLANES_NM = (10.0, 30.0, 60.0, 90.0, 110.0)
FAILED_GOALS = (
    "top:m0:n0:power",
    "top:m0:n0:co_amp_imag",
    "top:m-1:n0:power",
    "bottom:m-1:n0:power",
    "bottom:m-7:n0:co_amp_imag",
    "scalar/R_total",
)
M1_BASE_PEAK_MIB = 10067.86328125
PER_ORBIT_MATRIX_NNZ = (24696176 - 20140928) / 200.0
PER_ORBIT_FACTOR_NNZ = (116348600 - 101141150) / 200.0
PER_ORBIT_PEAK_MIB = (13357.5546875 - 10067.86328125) / 200.0
PREDICTED_PEAK_LIMIT_MIB = 10.5 * 1024.0
PREDICTION_SAFETY_MARGIN_MIB = 100.0
MAX_ORBITS = int(
    (
        PREDICTED_PEAK_LIMIT_MIB
        - PREDICTION_SAFETY_MARGIN_MIB
        - M1_BASE_PEAK_MIB
    )
    // PER_ORBIT_PEAK_MIB
)
FINE_H10_AUXILIARY_SHA256 = (
    "81de45f3f0917806e7a2f5b6e9e250be2ccfb72ee8027e0f6e433cd163143d15"
)
STRUCTURED_PAYLOAD_SHA256 = (
    "1e336fbd2990348c681a0b1a4b350ac227e11d0ca7264231d00b63920e641c7d"
)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def _validate_candidate_plan(payload: Mapping[str, Any]) -> None:
    expected = payload.get("expected_forest") or {}
    base = payload.get("base_config") or {}
    selected = payload.get("selected_p6_face_geometry_keys") or ()
    checks = {
        "schema": (
            payload.get("schema_version")
            == "task035d.stage4-local-h-refinement-plan.v1"
        ),
        "marked_root_boxes_empty": payload.get("marked_root_boxes") == [],
        "trace_p5": payload.get("trace_degree") == 5,
        "interior_p6": payload.get("cell_interior_degree") == 6,
        "252_root_cells": expected.get("root_cell_count") == 252,
        "252_leaves": expected.get("leaf_cell_count") == 252,
        "zero_hanging": expected.get("hanging_patch_count") == 0,
        "structured_6_3_14": base.get("mesh_cells_resolved")
        == [6, 3, 14],
        "selected_faces_nonempty": bool(selected),
        "ordinary_default_unchanged": (
            payload.get("ordinary_default_changed") is False
        ),
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise ValueError(
            "candidate plan left the one-shot h10 selective-face scope: "
            + ", ".join(failed)
        )


def _load_dwr_report(
    path: Path,
    *,
    expected_sha256: str,
    source_sha: str,
    plan_sha256: str,
) -> dict[str, Any]:
    if _file_sha256(path) != expected_sha256:
        raise ValueError("DWR report SHA-256 changed")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (
        payload.get("source_sha") != source_sha
        or payload.get("candidate_plan", {}).get("sha256")
        != plan_sha256
        or payload.get("second_batch_authorized") is not False
        or payload.get("ranking", {}).get("selected_orbit_count", 0) <= 0
    ):
        raise ValueError("DWR report identity or one-batch contract changed")
    return payload


def _clean_source_preflight(source_sha: str, comm: MPI.Intracomm) -> None:
    if comm.rank == 0:
        head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True,
        ).strip()
        status = subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=ROOT,
            text=True,
        ).strip()
        error = (
            None
            if head == source_sha and not status
            else f"source preflight differs: HEAD={head!r}, status={status!r}"
        )
    else:
        error = None
    error = comm.bcast(error, root=0)
    if error is not None:
        raise RuntimeError(error)
    if os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION") != "1":
        raise RuntimeError("qualified WSL activation is required")
    if np.dtype(PETSc.ScalarType) != np.dtype(np.complex128):
        raise RuntimeError("PETSc scalar type must be complex128")
    if np.dtype(PETSc.IntType) != np.dtype(np.int32):
        raise RuntimeError("PETSc integer type must be int32")


def _complex(row: Any) -> complex:
    if isinstance(row, Mapping):
        return complex(float(row["real"]), float(row["imag"]))
    return complex(float(row[0]), float(row[1]))


def _structured_rows(path: Path, endpoint: str) -> dict[str, dict[str, Any]]:
    document = json.loads(path.read_text(encoding="utf-8"))
    payload = document["payload"]
    observed = hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    ).hexdigest()
    if observed != str(document["payload_sha256"]):
        raise ValueError("structured anchor payload SHA-256 is invalid")
    if observed != STRUCTURED_PAYLOAD_SHA256:
        raise ValueError("structured anchor payload identity changed")
    if endpoint == "M1":
        rows = payload["M1_H10_fixed_p5trace_p6interior"][
            "formal_59_goal"
        ]["goals"]
    else:
        rows = payload["p6_three_mesh_consistency_gate"]["endpoints"][
            endpoint
        ]["formal_59_goal"]["goals"]
    goal_ids = [str(row["goal_id"]) for row in rows]
    if len(rows) != 59 or len(set(goal_ids)) != 59:
        raise ValueError(
            f"{endpoint} formal inventory is not 59 unique goals"
        )
    return {
        goal_id: dict(row)
        for goal_id, row in zip(goal_ids, rows, strict=True)
    }


def _load_auxiliary(path: Path, modes: tuple[Any, ...]) -> np.ndarray:
    rows = json.loads(path.read_text(encoding="utf-8"))
    rows = sorted(rows, key=lambda row: int(row["auxiliary_index"]))
    if len(rows) != len(modes):
        raise ValueError("stored fine endpoint has a different mode count")
    values = np.empty(len(rows), dtype=np.complex128)
    for index, (row, mode) in enumerate(zip(rows, modes, strict=True)):
        identity = (
            str(row["side"]),
            int(row["m"]),
            int(row["n"]),
            str(row["polarization"]),
        )
        expected = (
            str(mode.side),
            int(mode.m),
            int(mode.n),
            str(mode.polarization),
        )
        if identity != expected or int(row["auxiliary_index"]) != index:
            raise ValueError("stored fine endpoint mode ordering changed")
        values[index] = _complex(
            row["auxiliary_amplitude_total_projection"]
        )
    return values


def _base_config(plan: Path, tensor_cache: Path):
    from src.common.config_3d import target_stage4_config

    base = target_stage4_config(degree=6, h_nm=10.0)
    return replace(
        base,
        polarization_kind="s",
        custom_polarization=None,
        stage4_full3d_assembly_backend=(
            "assembly_time_variable_p_condensed"
        ),
        stage4_raw_tensor_cache_directory=str(tensor_cache),
        stage4_raw_tensor_cache_namespace=(
            f"git-{subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()}"
        ),
        stage4_local_h_refinement_plan=str(plan),
        petsc_direct_solver_profile="default",
        matrix_diagnostics_assemble_only=False,
        matrix_diagnostics_factorization_only=False,
        direct_release_base_after_augmentation=True,
        direct_release_solver_before_postprocess=True,
        unique_output=False,
    )


def _prepare(args: argparse.Namespace) -> None:
    from src.adaptivity.stage4_local_h import (
        stage4_local_h_refinement_plan_payload,
    )
    from src.common.config_3d import target_stage4_config

    _clean_source_preflight(args.source_sha, MPI.COMM_SELF)
    if args.artifact_root.exists():
        raise FileExistsError(
            f"immutable artifact root already exists: {args.artifact_root}"
        )
    args.artifact_root.mkdir(parents=True)
    cfg = target_stage4_config(degree=6, h_nm=10.0)
    plans = {}
    for label, trace_degree in (("m1_p5_trace", 5), ("fine_p6_trace", 6)):
        payload = stage4_local_h_refinement_plan_payload(
            cfg,
            (),
            comm_size=8,
            trace_degree=trace_degree,
            cell_interior_degree=6,
            provenance={
                "purpose": (
                    "Task035e one-shot goal-oriented selective-trace "
                    f"{label}"
                ),
                "accuracy_credit": False,
                "ordinary_default_changed": False,
            },
            zero_h_fixed_trace_anchor=True,
        )
        path = args.artifact_root / f"{label}_plan.json"
        _write_json(path, payload)
        plans[label] = {
            "path": str(path),
            "sha256": _file_sha256(path),
        }
    _write_json(
        args.artifact_root / "prepared_plans.json",
        {
            "status": "prepared",
            "source_sha": args.source_sha,
            "mpi_size": 8,
            "plans": plans,
            "ordinary_default_changed": False,
        },
    )


def _snapshot(args: argparse.Namespace) -> None:
    from src.adaptivity.variable_p_selective_face_dwr import (
        write_selective_face_coarse_snapshot,
    )
    from src.solvers.solve_maxwell_3d_stage_4b_block_grating import (
        run_stage4b_block_grating_3d_case,
    )

    comm = MPI.COMM_WORLD
    if comm.size != 8:
        raise RuntimeError("M1 support snapshot requires MPI8")
    _clean_source_preflight(args.source_sha, comm)
    plan = args.plan.resolve()
    plan_sha = _file_sha256(plan)
    if plan_sha != args.plan_sha256:
        raise ValueError("M1 plan SHA-256 changed")
    run_dir = args.run_dir.resolve()
    snapshot_dir = args.snapshot_dir.resolve()
    if comm.rank == 0 and (run_dir.exists() or snapshot_dir.exists()):
        error = "M1 run or snapshot output already exists"
    else:
        error = None
    error = comm.bcast(error, root=0)
    if error is not None:
        raise FileExistsError(error)

    authority_sha = _file_sha256(SIGNIFICANT_AUTHORITY)

    def observer(view) -> None:
        write_selective_face_coarse_snapshot(
            view,
            artifact_directory=snapshot_dir,
            candidate_id="H10_fixed_p5trace_p6interior_support_snapshot",
            expected_plan_sha256=plan_sha,
            source_sha=args.source_sha,
            significant_channel_authority_path=SIGNIFICANT_AUTHORITY,
            significant_channel_authority_sha256=authority_sha,
        )

    cfg = replace(
        _base_config(plan, args.tensor_cache.resolve()),
        full3d_reference_export=False,
    )
    result = run_stage4b_block_grating_3d_case(
        cfg,
        run_dir,
        variable_p_live_observer=observer,
    )
    if comm.rank == 0:
        print(
            json.dumps(
                {
                    "case_status": result.get("case_status"),
                    "official_result": result.get("official_result"),
                    "snapshot_manifest": str(
                        snapshot_dir / "manifest.json"
                    ),
                    "snapshot_manifest_sha256": _file_sha256(
                        snapshot_dir / "manifest.json"
                    ),
                },
                sort_keys=True,
            ),
            flush=True,
        )


def _gradient_and_value(
    view: Any,
    goal_id: str,
    auxiliary: np.ndarray,
) -> tuple[PETSc.Vec, float, dict[str, Any]]:
    from src.adaptivity.dtn_goal_adjoint import (
        DtnChannelGoal,
        build_dtn_channel_goal_gradient,
        build_dtn_power_goal_gradient,
    )

    context = dict(view.goal_context)
    context["auxiliary_values"] = np.asarray(
        auxiliary,
        dtype=np.complex128,
    )
    if goal_id == "top:m0:n0:power":
        gradient, metadata = build_dtn_power_goal_gradient(
            view.x_template,
            view.config,
            context,
            goal="R00_total",
        )
        return (
            gradient,
            float(metadata["goal_value_from_quadratic_form"]),
            metadata,
        )
    if goal_id == "scalar/R_total":
        gradient, metadata = build_dtn_power_goal_gradient(
            view.x_template,
            view.config,
            context,
            goal="R_total",
        )
        return (
            gradient,
            float(metadata["goal_value_from_quadratic_form"]),
            metadata,
        )
    prefix, quantity_label = goal_id.rsplit(":", 1)
    side, m_label, _n_label = prefix.split(":")
    m = int(m_label.removeprefix("m"))
    if quantity_label == "power":
        components = []
        rows = []
        try:
            for polarization in ("s", "p"):
                vector, row = build_dtn_channel_goal_gradient(
                    view.x_template,
                    view.config,
                    context,
                    goal=DtnChannelGoal(
                        side,
                        m,
                        0,
                        polarization,
                        "power",
                    ),
                )
                components.append(vector)
                rows.append(row)
            gradient = components[0].copy()
            gradient.axpy(PETSc.ScalarType(1.0), components[1])
            value = float(sum(float(row["goal_value"]) for row in rows))
        finally:
            for vector in components:
                vector.destroy()
        return gradient, value, {"components": rows}
    if quantity_label != "co_amp_imag":
        raise ValueError(f"unsupported failed goal: {goal_id}")
    gradient, metadata = build_dtn_channel_goal_gradient(
        view.x_template,
        view.config,
        context,
        goal=DtnChannelGoal(
            side,
            m,
            0,
            "s",
            "amplitude_imag",
        ),
    )
    return gradient, float(metadata["goal_value"]), metadata


def _root_call(
    comm: MPI.Intracomm,
    callback,
) -> Any:
    result = None
    error = None
    if comm.rank == 0:
        try:
            result = callback()
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
    error = comm.bcast(error, root=0)
    if error is not None:
        raise RuntimeError(error)
    return result


def _adjoint(args: argparse.Namespace) -> None:
    from src.adaptivity.dtn_goal_adjoint import (
        solve_hermitian_discrete_adjoint,
    )
    from src.adaptivity.goal_oriented_selective_trace import (
        build_p5_to_global_p6_root_injection,
        build_periodic_face_quotient,
        decompose_face_residual,
        signed_orbit_pairings,
    )
    from src.adaptivity.hcurl_broken_trace_graph import (
        build_broken_hexa_trace_constraint_authority,
    )
    from src.adaptivity.stage4_local_h import (
        stage4_local_h_refinement_plan_payload,
    )
    from src.adaptivity.variable_p_nested_dwr import (
        _global_petsc_values,
        _temporary_vector_from_global,
    )
    from src.adaptivity.variable_p_selective_face_dwr import (
        load_selective_face_coarse_snapshot,
    )
    from src.common.config_3d import target_stage4_config
    from src.solvers.solve_maxwell_3d_stage_4b_block_grating import (
        run_stage4b_block_grating_3d_case,
    )

    comm = MPI.COMM_WORLD
    if comm.size != 8:
        raise RuntimeError("fine-space adjoints require MPI8")
    _clean_source_preflight(args.source_sha, comm)
    plan = args.plan.resolve()
    if _file_sha256(plan) != args.plan_sha256:
        raise ValueError("fine plan SHA-256 changed")
    if _file_sha256(args.fine_auxiliary) != args.fine_auxiliary_sha256:
        raise ValueError("fine p6/h10 auxiliary SHA-256 changed")
    if args.fine_auxiliary_sha256 != FINE_H10_AUXILIARY_SHA256:
        raise ValueError("fine auxiliary is not the frozen p6/h10 endpoint")
    if _file_sha256(args.structured_record) != args.structured_record_sha256:
        raise ValueError("structured anchor record SHA-256 changed")
    m1_rows = _structured_rows(args.structured_record, "M1")
    observed_failed = {
        goal_id
        for goal_id, row in m1_rows.items()
        if not bool(row["pass"])
    }
    expected_failed = set(FAILED_GOALS) | {"scalar/R00_total"}
    if observed_failed != expected_failed:
        raise ValueError(
            "M1 frozen seven-failure identity changed: "
            f"{sorted(observed_failed)}"
        )
    if comm.rank == 0 and (
        args.run_dir.exists()
        or args.report.exists()
        or args.candidate_plan.exists()
    ):
        error = "fine run, DWR report, or candidate plan already exists"
    else:
        error = None
    error = comm.bcast(error, root=0)
    if error is not None:
        raise FileExistsError(error)

    snapshot_sha = _file_sha256(args.snapshot_manifest)
    authority_sha = _file_sha256(SIGNIFICANT_AUTHORITY)

    def observer(view) -> None:
        snapshot = load_selective_face_coarse_snapshot(
            args.snapshot_manifest,
            communicator=comm,
            expected_manifest_sha256=snapshot_sha,
            expected_source_sha=args.source_sha,
            expected_significant_channel_authority_sha256=authority_sha,
        )
        fine_authority = (
            view.reduction.system.trace_constraints.authority
        )
        context = view.mesh_data.local_h_context
        all_face_geometry_keys = tuple(
            sorted(
                entity.geometry_key
                for entity in fine_authority.entities
                if entity.dimension == 2
            )
        )
        selective_authority = (
            build_broken_hexa_trace_constraint_authority(
                context.forest,
                context.carrier,
                degree=5,
                phase_x=view.floquet_data.phase_x,
                phase_y=view.floquet_data.phase_y,
                selected_p6_face_geometry_keys=all_face_geometry_keys,
            )
        )

        def root_setup():
            injection = build_p5_to_global_p6_root_injection(
                snapshot.authority,
                fine_authority,
            )
            coarse_trace = int(
                snapshot.manifest["independent_trace_rows"]
            )
            fine_trace = int(
                view.reduction.system.active_trace_rows
            )
            auxiliary_rows = int(view.reduction.system.appended_rows)
            if (
                injection.trace_injection.shape
                != (fine_trace, coarse_trace)
                or len(snapshot.state_b)
                != coarse_trace + auxiliary_rows
            ):
                raise RuntimeError("M1/fine root dimensions do not close")
            state = np.concatenate(
                (
                    np.asarray(
                        injection.trace_injection
                        @ snapshot.state_b[:coarse_trace]
                    ),
                    snapshot.state_b[coarse_trace:],
                )
            )
            return injection, state

        setup = _root_call(comm, root_setup)
        state_global = comm.bcast(
            None if setup is None else setup[1],
            root=0,
        )
        x_m1 = _temporary_vector_from_global(
            view.x_template,
            state_global,
        )
        action = view.x_template.duplicate()
        residual = view.b.copy()
        try:
            view.A.mult(x_m1, action)
            residual.axpy(PETSc.ScalarType(-1.0), action)
            residual_global, ownership = _global_petsc_values(
                residual,
                comm,
            )
            rhs_global, _ = _global_petsc_values(view.b, comm)

            probe_actions = []
            for column in range(snapshot.probe_vectors.shape[1]):
                if comm.rank == 0:
                    injection = setup[0].trace_injection
                    coarse_trace = injection.shape[1]
                    probe = np.concatenate(
                        (
                            np.asarray(
                                injection
                                @ snapshot.probe_vectors[
                                    :coarse_trace,
                                    column,
                                ]
                            ),
                            snapshot.probe_vectors[
                                coarse_trace:,
                                column,
                            ],
                        )
                    )
                else:
                    probe = None
                probe = comm.bcast(probe, root=0)
                source = _temporary_vector_from_global(
                    view.x_template,
                    probe,
                )
                target = view.x_template.duplicate()
                try:
                    view.A.mult(source, target)
                    values, _ = _global_petsc_values(target, comm)
                    probe_actions.append(values)
                finally:
                    target.destroy()
                    source.destroy()

            fine_auxiliary = _load_auxiliary(
                args.fine_auxiliary,
                tuple(view.goal_context["modes"]),
            )
            coarse_auxiliary = np.asarray(
                snapshot.auxiliary_values_b,
                dtype=np.complex128,
            )
            midpoint = 0.5 * (coarse_auxiliary + fine_auxiliary)
            goal_packets: dict[str, dict[str, Any]] = {}
            for goal_id in FAILED_GOALS:
                gradient, _midpoint_value, metadata = (
                    _gradient_and_value(view, goal_id, midpoint)
                )
                coarse_gradient = fine_gradient = None
                adjoint = None
                try:
                    coarse_gradient, coarse_value, _ = (
                        _gradient_and_value(
                            view,
                            goal_id,
                            coarse_auxiliary,
                        )
                    )
                    fine_gradient, fine_value, _ = (
                        _gradient_and_value(
                            view,
                            goal_id,
                            fine_auxiliary,
                        )
                    )
                    adjoint, solve = solve_hermitian_discrete_adjoint(
                        view.A,
                        view.ksp,
                        gradient,
                        template=view.x_template,
                    )
                    values, _ = _global_petsc_values(adjoint, comm)
                    goal_packets[goal_id] = {
                        "coarse_value": coarse_value,
                        "fine_value": fine_value,
                        "actual_fine_minus_coarse": (
                            fine_value - coarse_value
                        ),
                        "adjoint": values,
                        "solve": solve,
                        "gradient_metadata": metadata,
                    }
                finally:
                    if adjoint is not None:
                        adjoint.destroy()
                    if fine_gradient is not None:
                        fine_gradient.destroy()
                    if coarse_gradient is not None:
                        coarse_gradient.destroy()
                    gradient.destroy()

            def root_finalize():
                injection = setup[0]
                fine_trace = injection.trace_injection.shape[0]
                auxiliary_rows = len(residual_global) - fine_trace
                total_injection = sparse.block_diag(
                    (
                        injection.trace_injection,
                        sparse.eye(
                            auxiliary_rows,
                            dtype=np.complex128,
                            format="csr",
                        ),
                    ),
                    format="csr",
                )
                rhs_restricted = np.asarray(
                    total_injection.conj().T @ rhs_global
                )
                rhs_error = float(
                    np.linalg.norm(rhs_restricted - snapshot.rhs_b)
                )
                probe_rows = []
                for index, values in enumerate(probe_actions):
                    restricted = np.asarray(
                        total_injection.conj().T @ values
                    )
                    error = float(
                        np.linalg.norm(
                            restricted
                            - snapshot.probe_actions[:, index]
                        )
                    )
                    probe_rows.append(
                        {"probe": index, "l2_error": error}
                    )
                coarse_residual = np.asarray(
                    total_injection.conj().T @ residual_global
                )
                coarse_residual_error = float(
                    np.linalg.norm(
                        coarse_residual - snapshot.residual_b
                    )
                )
                if max(
                    rhs_error,
                    coarse_residual_error,
                    *(row["l2_error"] for row in probe_rows),
                ) > 2.0e-8:
                    raise RuntimeError(
                        "M1/global-p6 Galerkin identity failed"
                    )
                quotient = build_periodic_face_quotient(
                    snapshot.authority,
                    selective_authority,
                    fine_authority,
                    injection,
                )
                if (
                    quotient.audit["physical_face_count"] != 900
                    or quotient.audit[
                        "periodic_physical_face_orbit_count"
                    ] != 774
                    or quotient.audit["B_independent_trace_rows"] != 34920
                    or quotient.audit["S_independent_trace_rows"] != 50400
                    or quotient.audit["F_independent_trace_rows"] != 51192
                    or quotient.audit["face_quotient_rows"] != 774 * 20
                    or (
                        quotient.audit["S_independent_trace_rows"]
                        - quotient.audit["B_independent_trace_rows"]
                    )
                    != quotient.audit["face_quotient_rows"]
                    or (
                        quotient.audit["F_independent_trace_rows"]
                        - quotient.audit["S_independent_trace_rows"]
                    )
                    != 792
                ):
                    raise RuntimeError(
                        "structured h10 B/S/F trace dimensions changed"
                    )
                partition = decompose_face_residual(
                    quotient,
                    residual_global[:fine_trace],
                )
                structured = _structured_rows(
                    args.structured_record,
                    "M1",
                )
                structured_fine = _structured_rows(
                    args.structured_record,
                    "p6_h10",
                )
                contributions = {}
                goal_rows = {}
                for goal_id in FAILED_GOALS:
                    packet = goal_packets[goal_id]
                    adjoint = packet.pop("adjoint")
                    pairings = signed_orbit_pairings(
                        quotient,
                        partition,
                        adjoint[:fine_trace],
                    )
                    global_pairing = complex(
                        np.vdot(adjoint, residual_global)
                    )
                    face_pairing = complex(np.sum(pairings))
                    unexplained_pairing = complex(
                        global_pairing - face_pairing
                    )
                    actual = float(
                        packet["actual_fine_minus_coarse"]
                    )
                    coarse_identity_error = abs(
                        float(packet["coarse_value"])
                        - float(structured[goal_id]["value"])
                    )
                    fine_identity_error = abs(
                        float(packet["fine_value"])
                        - float(structured_fine[goal_id]["value"])
                    )
                    closure = float(global_pairing.real - actual)
                    tau = float(
                        structured[goal_id]["reference_tolerance"]
                    )
                    reference = float(
                        structured[goal_id]["reference_center"]
                    )
                    adjoint_residual = float(
                        packet["solve"]["adjoint_residual"][
                            "relative_residual"
                        ]
                    )
                    if (
                        adjoint_residual > 1.0e-9
                        or abs(closure) / tau > 0.02
                        or coarse_identity_error
                        > max(1.0e-10 * tau, 5.0e-12)
                        or fine_identity_error
                        > max(1.0e-10 * tau, 5.0e-12)
                    ):
                        raise RuntimeError(
                            f"adjoint/DWR closure failed for {goal_id}"
                        )
                    contributions[goal_id] = pairings.real
                    goal_rows[goal_id] = {
                        **{
                            key: value
                            for key, value in packet.items()
                            if key != "solve"
                        },
                        "reference_center": reference,
                        "reference_tolerance": tau,
                        "initial_normalized_error": (
                            (
                                float(packet["coarse_value"])
                                - reference
                            )
                            / tau
                        ),
                        "global_signed_dwr": float(
                            global_pairing.real
                        ),
                        "face_signed_dwr_sum": float(
                            face_pairing.real
                        ),
                        "unexplained_edge_or_roundoff_signed_dwr": float(
                            unexplained_pairing.real
                        ),
                        "actual_endpoint_delta": actual,
                        "global_endpoint_closure_error": closure,
                        "M1_endpoint_identity_error": (
                            coarse_identity_error
                        ),
                        "p6_h10_endpoint_identity_error": (
                            fine_identity_error
                        ),
                        "adjoint_solve": packet["solve"],
                    }

                errors = np.asarray(
                    [
                        goal_rows[goal_id][
                            "initial_normalized_error"
                        ]
                        for goal_id in FAILED_GOALS
                    ],
                    dtype=np.float64,
                )
                initial_errors = np.asarray(errors, copy=True)
                eta = np.vstack(
                    [contributions[goal_id] for goal_id in FAILED_GOALS]
                )
                tau = np.asarray(
                    [
                        goal_rows[goal_id]["reference_tolerance"]
                        for goal_id in FAILED_GOALS
                    ]
                )
                selected: list[int] = []
                ranking_steps = []
                remaining = set(range(eta.shape[1]))
                for step in range(MAX_ORBITS):
                    candidates = []
                    for orbit in remaining:
                        proposed = errors + eta[:, orbit] / tau
                        benefit = float(
                            np.dot(errors, errors)
                            - np.dot(proposed, proposed)
                        )
                        candidates.append((benefit, -orbit, proposed))
                    benefit, negative_orbit, proposed = max(
                        candidates,
                        key=lambda row: (row[0], row[1]),
                    )
                    orbit = -negative_orbit
                    if benefit <= 0.0:
                        break
                    selected.append(orbit)
                    remaining.remove(orbit)
                    errors = proposed
                    ranking_steps.append(
                        {
                            "step": step + 1,
                            "orbit": orbit,
                            "geometry_keys": [
                                list(key)
                                for key in quotient.orbit_geometry_keys[
                                    orbit
                                ]
                            ],
                            "marginal_normalized_squared_error_benefit": (
                                benefit
                            ),
                            "predicted_normalized_errors_after_step": {
                                goal_id: float(value)
                                for goal_id, value in zip(
                                    FAILED_GOALS,
                                    errors,
                                    strict=True,
                                )
                            },
                        }
                    )
                    if np.all(np.abs(errors) <= 1.0):
                        break
                if not selected:
                    raise RuntimeError(
                        "goal-oriented ranking has no positive face orbit"
                    )
                predicted_peak = (
                    M1_BASE_PEAK_MIB
                    + len(selected) * PER_ORBIT_PEAK_MIB
                )
                if predicted_peak >= PREDICTED_PEAK_LIMIT_MIB:
                    raise RuntimeError(
                        "frozen DWR batch exceeds predicted 10.5 GiB"
                    )
                selected_geometry = tuple(
                    sorted(
                        {
                            key
                            for orbit in selected
                            for key in quotient.orbit_geometry_keys[
                                orbit
                            ]
                        }
                    )
                )
                initial_benefits = np.empty(
                    eta.shape[1],
                    dtype=np.float64,
                )
                for orbit in range(eta.shape[1]):
                    proposed = initial_errors + eta[:, orbit] / tau
                    initial_benefits[orbit] = float(
                        np.dot(initial_errors, initial_errors)
                        - np.dot(proposed, proposed)
                    )
                initial_order = sorted(
                    range(eta.shape[1]),
                    key=lambda orbit: (
                        -initial_benefits[orbit],
                        orbit,
                    ),
                )
                initial_rank = {
                    orbit: rank
                    for rank, orbit in enumerate(initial_order, start=1)
                }
                selected_step = {
                    int(row["orbit"]): int(row["step"])
                    for row in ranking_steps
                }
                orbit_scores = []
                for orbit in range(eta.shape[1]):
                    orbit_scores.append(
                        {
                            "orbit": orbit,
                            "geometry_keys": [
                                list(key)
                                for key in quotient.orbit_geometry_keys[
                                    orbit
                                ]
                            ],
                            "signed_goal_dwr": {
                                goal_id: float(eta[index, orbit])
                                for index, goal_id in enumerate(
                                    FAILED_GOALS
                                )
                            },
                            "tolerance_normalized_signed_goal_dwr": {
                                goal_id: float(
                                    eta[index, orbit] / tau[index]
                                )
                                for index, goal_id in enumerate(
                                    FAILED_GOALS
                                )
                            },
                            "initial_normalized_squared_error_benefit": (
                                float(initial_benefits[orbit])
                            ),
                            "benefit_per_peak_mib_proxy": float(
                                initial_benefits[orbit]
                                / PER_ORBIT_PEAK_MIB
                            ),
                            "initial_rank": initial_rank[orbit],
                            "selected": orbit in selected_step,
                            "selected_greedy_step": selected_step.get(
                                orbit
                            ),
                        }
                    )
                plan_payload = (
                    stage4_local_h_refinement_plan_payload(
                        target_stage4_config(degree=6, h_nm=10.0),
                        (),
                        comm_size=8,
                        trace_degree=5,
                        cell_interior_degree=6,
                        provenance={
                            "purpose": (
                                "Task035e one-shot signed multi-goal "
                                "DWR selective trace"
                            ),
                            "ranking": (
                                "six deduplicated failed physical goals; "
                                "frozen tolerance normalized benefit/cost"
                            ),
                        "maximum_periodic_face_orbits": (
                            MAX_ORBITS
                        ),
                        "prediction_safety_margin_mib": (
                            PREDICTION_SAFETY_MARGIN_MIB
                        ),
                            "ordinary_default_changed": False,
                        },
                        selected_p6_face_geometry_keys=(
                            selected_geometry
                        ),
                    )
                )
                _write_json(args.candidate_plan, plan_payload)
                report = {
                    "status": "goal_oriented_selective_trace_batch_frozen",
                    "source_sha": args.source_sha,
                    "mpi_size": 8,
                    "failed_rows": 7,
                    "deduplicated_physical_goal_count": 6,
                    "deduplication": {
                        "top:m0:n0:power": [
                            "top:m0:n0:power",
                            "scalar/R00_total",
                        ]
                    },
                    "goals": goal_rows,
                    "galerkin_audit": {
                        "rhs_restriction_l2_error": rhs_error,
                        "coarse_residual_restriction_l2_error": (
                            coarse_residual_error
                        ),
                        "operator_probes": probe_rows,
                    },
                    "root_injection": dict(injection.audit),
                    "face_quotient": dict(quotient.audit),
                    "face_residual_partition": dict(partition.audit),
                    "input_identity": {
                        "snapshot_manifest": {
                            "path": str(args.snapshot_manifest),
                            "sha256": snapshot_sha,
                        },
                        "fine_p6_h10_auxiliary": {
                            "path": str(args.fine_auxiliary),
                            "sha256": args.fine_auxiliary_sha256,
                        },
                        "structured_anchor_record": {
                            "path": str(args.structured_record),
                            "sha256": (
                                args.structured_record_sha256
                            ),
                            "payload_sha256": (
                                STRUCTURED_PAYLOAD_SHA256
                            ),
                        },
                        "significant_channel_authority": {
                            "path": str(SIGNIFICANT_AUTHORITY),
                            "sha256": authority_sha,
                        },
                    },
                    "ranking": {
                        "formula": (
                            "marginal reduction in sum((J-ref)/tau)^2 "
                            "per empirically calibrated structural cost"
                        ),
                        "selected_orbit_indices": selected,
                        "selected_orbit_count": len(selected),
                        "selected_geometry_key_count": len(
                            selected_geometry
                        ),
                        "steps": ranking_steps,
                        "all_774_orbit_scores": orbit_scores,
                        "predicted_final_normalized_errors": {
                            goal_id: float(value)
                            for goal_id, value in zip(
                                FAILED_GOALS,
                                errors,
                                strict=True,
                            )
                        },
                        "cost_per_orbit": {
                            "added_rows": 20,
                            "matrix_nnz_proxy": PER_ORBIT_MATRIX_NNZ,
                            "factor_nnz_proxy": PER_ORBIT_FACTOR_NNZ,
                            "whole_job_peak_mib_proxy": (
                                PER_ORBIT_PEAK_MIB
                            ),
                        },
                        "predicted_structure": {
                            "rows": 35000 + 20 * len(selected),
                            "matrix_nnz": (
                                20140928
                                + PER_ORBIT_MATRIX_NNZ
                                * len(selected)
                            ),
                            "factor_nnz": (
                                101141150
                                + PER_ORBIT_FACTOR_NNZ
                                * len(selected)
                            ),
                            "whole_job_peak_mib": predicted_peak,
                            "budget_limit_mib": (
                                PREDICTED_PEAK_LIMIT_MIB
                            ),
                            "prediction_safety_margin_mib": (
                                PREDICTION_SAFETY_MARGIN_MIB
                            ),
                        },
                    },
                    "candidate_plan": {
                        "path": str(args.candidate_plan),
                        "sha256": _file_sha256(args.candidate_plan),
                    },
                    "second_batch_authorized": False,
                    "ordinary_default_changed": False,
                }
                _write_json(args.report, report)
                return {
                    "report": str(args.report),
                    "candidate_plan": str(args.candidate_plan),
                    "selected_orbits": len(selected),
                }

            result = _root_call(comm, root_finalize)
            result = comm.bcast(result, root=0)
            if comm.rank == 0:
                print(json.dumps(result, sort_keys=True), flush=True)
        finally:
            residual.destroy()
            action.destroy()
            x_m1.destroy()
            gc.collect()

    cfg = replace(
        _base_config(plan, args.tensor_cache.resolve()),
        matrix_diagnostics_factorization_only=True,
        full3d_reference_export=False,
    )
    run_stage4b_block_grating_3d_case(
        cfg,
        args.run_dir.resolve(),
        variable_p_factorization_observer=observer,
    )


def _candidate(args: argparse.Namespace) -> None:
    from src.solvers.solve_maxwell_3d_stage_4b_block_grating import (
        run_stage4b_block_grating_3d_case,
    )

    comm = MPI.COMM_WORLD
    if comm.size != 8:
        raise RuntimeError("actual selective-trace candidate requires MPI8")
    _clean_source_preflight(args.source_sha, comm)
    plan = args.plan.resolve()
    if _file_sha256(plan) != args.plan_sha256:
        raise ValueError("candidate plan SHA-256 changed")
    plan_payload = json.loads(plan.read_text(encoding="utf-8"))
    _validate_candidate_plan(plan_payload)
    _load_dwr_report(
        args.dwr_report.resolve(),
        expected_sha256=args.dwr_report_sha256,
        source_sha=args.source_sha,
        plan_sha256=args.plan_sha256,
    )
    if comm.rank == 0 and args.run_dir.exists():
        error = "actual candidate run directory already exists"
    else:
        error = None
    error = comm.bcast(error, root=0)
    if error is not None:
        raise FileExistsError(error)
    cfg = replace(
        _base_config(plan, args.tensor_cache.resolve()),
        full3d_reference_export=True,
        full3d_reference_plane_z=REFERENCE_PLANES_NM,
        full3d_reference_sample_count_x=40,
        full3d_reference_sample_count_y=20,
    )
    result = run_stage4b_block_grating_3d_case(
        cfg,
        args.run_dir.resolve(),
    )
    if comm.rank == 0:
        print(
            json.dumps(
                {
                    "case_status": result.get("case_status"),
                    "official_result": result.get("official_result"),
                    "elapsed_seconds": result.get("elapsed_seconds"),
                },
                sort_keys=True,
            ),
            flush=True,
        )


def _candidate_values(run_dir: Path) -> dict[str, float]:
    orders_payload = json.loads(
        (run_dir / "dtn_port_diffraction_orders_3d.json").read_text(
            encoding="utf-8"
        )
    )
    orders = {
        (
            str(row["side"]),
            int(row["m"]),
            int(row["n"]),
            str(row["polarization"]),
        ): row
        for row in orders_payload["orders"]
    }
    values = {}
    for side in ("top", "bottom"):
        for m in (0, -1, -2, -3, -4, -5, -6, -7):
            s = orders[(side, m, 0, "s")]
            p = orders[(side, m, 0, "p")]
            prefix = f"{side}:m{m}:n0"
            values[f"{prefix}:power"] = float(
                s["power_ratio"] + p["power_ratio"]
            )
            amplitude = _complex(
                s["outgoing_amplitude_at_boundary"]
            )
            values[f"{prefix}:co_amp_real"] = float(amplitude.real)
            values[f"{prefix}:co_amp_imag"] = float(amplitude.imag)
    metrics = orders_payload["metrics"]
    values["scalar/R00_total"] = float(metrics["R00_total"])
    values["scalar/R_total"] = float(metrics["R_total"])
    values["scalar/T_total"] = float(metrics["T_total"])
    values["scalar/A_closure"] = float(
        1.0 - metrics["R_total"] - metrics["T_total"]
    )
    volume = json.loads(
        (run_dir / "volume_absorption.json").read_text(
            encoding="utf-8"
        )
    )
    values["scalar/A_volume"] = float(volume["A_volume_total"])
    metadata = json.loads(
        (run_dir / "full3d_reference_samples.json").read_text(
            encoding="utf-8"
        )
    )
    archive_path = run_dir / str(metadata["archive"])
    if (
        metadata.get("array_shape_z_y_x_component") != [5, 20, 40, 3]
        or [
            float(row["z_nm"])
            for row in metadata.get("plane_metrics", ())
        ]
        != list(REFERENCE_PLANES_NM)
        or _file_sha256(archive_path)
        != str(metadata.get("archive_sha256"))
    ):
        raise ValueError("candidate field archive identity is invalid")
    with np.load(
        archive_path,
        allow_pickle=False,
    ) as archive:
        field = np.asarray(archive["E_V_per_m"], dtype=np.complex128)
        interface = np.asarray(
            archive["E_t_interface_V_per_m"],
            dtype=np.complex128,
        )
    if (
        field.shape != (5, 20, 40, 3)
        or interface.shape != (2, 20, 40, 2)
    ):
        raise ValueError("candidate field sample shapes changed")
    middle = np.asarray(metadata["middle_plane_indices"], dtype=np.int64)
    values["scalar/interface_probe_l2"] = float(
        np.linalg.norm(interface.ravel())
    )
    values["scalar/volume_probe_l2"] = float(
        np.linalg.norm(field[middle].ravel())
    )
    interface_mean = complex(np.mean(interface))
    volume_mean = complex(np.mean(field[middle]))
    values["complex/interface_probe_complex/real"] = float(
        interface_mean.real
    )
    values["complex/interface_probe_complex/imag"] = float(
        interface_mean.imag
    )
    values["complex/volume_probe_complex/real"] = float(
        volume_mean.real
    )
    values["complex/volume_probe_complex/imag"] = float(
        volume_mean.imag
    )
    return values


def _evaluate(args: argparse.Namespace) -> None:
    run_dir = args.run_dir.resolve()
    if _file_sha256(args.structured_record) != args.structured_record_sha256:
        raise ValueError("structured anchor record SHA-256 changed")
    plan = args.plan.resolve()
    plan_sha = _file_sha256(plan)
    if plan_sha != args.plan_sha256:
        raise ValueError("actual candidate plan SHA-256 changed")
    plan_payload = json.loads(plan.read_text(encoding="utf-8"))
    _validate_candidate_plan(plan_payload)
    dwr_report = _load_dwr_report(
        args.dwr_report.resolve(),
        expected_sha256=args.dwr_report_sha256,
        source_sha=args.source_sha,
        plan_sha256=args.plan_sha256,
    )
    references = _structured_rows(args.structured_record, "p6_h10")
    values = _candidate_values(run_dir)
    if len(values) != 59 or set(values) != set(references):
        raise ValueError("candidate and frozen 59-goal inventories differ")
    rows = []
    for index, (goal_id, reference_row) in enumerate(
        references.items()
    ):
        value = float(values[goal_id])
        reference = float(reference_row["reference_center"])
        tolerance = float(reference_row["reference_tolerance"])
        normalized = (value - reference) / tolerance
        rows.append(
            {
                "index": index,
                "goal_id": goal_id,
                "category": reference_row["category"],
                "value": value,
                "reference_center": reference,
                "reference_tolerance": tolerance,
                "signed_normalized_error": normalized,
                "absolute_normalized_error": abs(normalized),
                "pass": abs(normalized) <= 1.0,
            }
        )
    summary = json.loads(
        (run_dir / "run_summary.json").read_text(encoding="utf-8")
    )
    progress = [
        json.loads(line)
        for line in (
            run_dir / "progress_3d.jsonl"
        ).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    peak = max(float(row["total_peak_rss_mb"]) for row in progress)
    swap = max(float(row.get("swap_used_mb") or 0.0) for row in progress)
    stages = [str(row["stage"]) for row in progress]
    release_index = (
        stages.index("solver_objects_released_before_postprocess")
        if "solver_objects_released_before_postprocess" in stages
        else None
    )
    field_index = (
        stages.index("after_field_output")
        if "after_field_output" in stages
        else None
    )
    residual = float(summary["linear_system_relative_residual"])
    energy = abs(float(summary["energy_closure_error_port_volume"]))
    floquet_names = (
        "floquet_x_face_mismatch",
        "floquet_y_face_mismatch",
        "floquet_edge_corner_mismatch",
    )
    floquet_values = [
        summary.get(name)
        for name in floquet_names
    ]
    floquet = (
        max(abs(float(value)) for value in floquet_values)
        if all(value is not None for value in floquet_values)
        else None
    )
    mesh_audit = summary.get("stage4_local_h_mesh_audit") or {}
    constraint_audit = (
        summary.get("stage4_local_h_constraint_audit") or {}
    )
    factor_inventory = summary.get("stage4_dtn_factor_inventory") or {}
    factor_stats = factor_inventory.get("matrix_stats") or {}
    selected_plan_faces = tuple(
        sorted(
            tuple(map(int, row))
            for row in plan_payload["selected_p6_face_geometry_keys"]
        )
    )
    selected_summary_faces = tuple(
        sorted(
            tuple(map(int, row))
            for row in mesh_audit.get(
                "selected_p6_face_geometry_keys",
                (),
            )
        )
    )
    checks = {
        "case_completed_official": (
            summary.get("case_status") == "completed"
            and summary.get("official_result") is True
        ),
        "59_of_59": all(row["pass"] for row in rows),
        "full_explicit_true_residual_le_1e_9": residual <= 1.0e-9,
        "energy_closure_le_1e_9": energy <= 1.0e-9,
        "floquet_le_1e_9": (
            floquet is not None and floquet <= 1.0e-9
        ),
        "local_h_mesh_and_constraint_audits_pass": (
            mesh_audit.get("pass") is True
            and constraint_audit.get("pass") is True
        ),
        "candidate_plan_identity": (
            str(mesh_audit.get("plan_file_sha256")) == plan_sha
            and selected_summary_faces == selected_plan_faces
            and int(mesh_audit.get("selected_p6_face_count", -1))
            == len(selected_plan_faces)
            and plan_payload.get("marked_root_boxes") == []
            and plan_payload.get("trace_degree") == 5
            and plan_payload.get("cell_interior_degree") == 6
            and plan_payload.get("expected_forest", {}).get(
                "leaf_cell_count"
            )
            == 252
        ),
        "hanging_patch_count_zero": (
            mesh_audit.get("hanging_patch_count") == 0
            and constraint_audit.get("hanging_slave_rows") == 0
        ),
        "mpi8": bool(progress)
        and all(int(row["rank_count"]) == 8 for row in progress),
        "whole_job_peak_le_11_gib": peak <= 11.0 * 1024.0,
        "zero_swap": swap == 0.0,
        "solver_released_before_field_output": (
            release_index is not None
            and field_index is not None
            and release_index < field_index
            and summary[
                "solver_objects_released_before_postprocess"
            ]
            is True
        ),
    }
    passed = all(checks.values())
    raw_names = (
        "run_summary.json",
        "progress_3d.jsonl",
        "dtn_port_diffraction_orders_3d.json",
        "dtn_auxiliary_amplitudes_3d.json",
        "volume_absorption.json",
        "full3d_reference_samples.json",
        str(
            json.loads(
                (run_dir / "full3d_reference_samples.json").read_text(
                    encoding="utf-8"
                )
            )["archive"]
        ),
    )
    raw_artifacts = {}
    for name in raw_names:
        path = run_dir / name
        if not path.is_file():
            raise FileNotFoundError(f"missing candidate raw artifact: {path}")
        try:
            relative_path = path.relative_to(
                Path("/home/Projects/MyFEniCS")
            )
            rendered_path = str(relative_path)
        except ValueError:
            rendered_path = str(path)
        raw_artifacts[name] = {
            "path": rendered_path,
            "sha256": _file_sha256(path),
            "bytes": path.stat().st_size,
        }
    payload = {
        "status": (
            "goal_oriented_selective_trace_actual_pass"
            if passed
            else "controlled_negative_goal_oriented_selective_trace"
        ),
        "pass": passed,
        "direct_selective_trace_lane_closed": not passed,
        "second_batch_authorized": False,
        "source_sha": args.source_sha,
        "run_directory": str(run_dir),
        "formal_59_goal": {
            "passed": sum(row["pass"] for row in rows),
            "total": 59,
            "maximum_absolute_normalized_error": max(
                row["absolute_normalized_error"] for row in rows
            ),
            "failed_goal_ids": [
                row["goal_id"] for row in rows if not row["pass"]
            ],
            "goals": rows,
        },
        "physics": {
            "full_explicit_true_relative_residual": residual,
            "energy_closure_error_port_volume": energy,
            "maximum_floquet_mismatch": floquet,
        },
        "resource": {
            "semantics": "sum_rank_historical_peaks_upper_bound",
            "whole_job_peak_mib": peak,
            "whole_job_peak_gib": peak / 1024.0,
            "swap_used_mib": swap,
            "release_stage_index": release_index,
            "field_output_stage_index": field_index,
        },
        "structure": {
            "active_fe_dof": summary.get(
                "num_actual_conforming_active_fe_dofs"
            ),
            "storage_carrier_fe_dof": summary.get("num_nedelec_dofs"),
            "rows": summary["matrix_stats"].get("matrix_rows"),
            "matrix_nnz": summary["matrix_stats"].get(
                "matrix_nnz_used"
            ),
            "factor_nnz": (
                factor_stats.get("matrix_nnz_used")
            ),
            "selected_physical_face_geometry_key_count": len(
                selected_plan_faces
            ),
            "selected_periodic_physical_face_orbit_count": (
                dwr_report["ranking"]["selected_orbit_count"]
            ),
        },
        "input_identity": {
            "candidate_plan": {
                "path": str(plan),
                "sha256": plan_sha,
            },
            "DWR_report": {
                "path": str(args.dwr_report),
                "sha256": args.dwr_report_sha256,
            },
            "structured_record": {
                "path": str(args.structured_record),
                "sha256": args.structured_record_sha256,
            },
        },
        "raw_artifacts": raw_artifacts,
        "checks": checks,
        "ordinary_default_changed": False,
    }
    _write_json(args.output, payload)
    print(json.dumps({"status": payload["status"], "pass": passed}))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--source-sha", required=True)
    prepare.add_argument("--artifact-root", type=Path, required=True)

    snapshot = subparsers.add_parser("snapshot")
    snapshot.add_argument("--source-sha", required=True)
    snapshot.add_argument("--plan", type=Path, required=True)
    snapshot.add_argument("--plan-sha256", required=True)
    snapshot.add_argument("--tensor-cache", type=Path, required=True)
    snapshot.add_argument("--run-dir", type=Path, required=True)
    snapshot.add_argument("--snapshot-dir", type=Path, required=True)

    adjoint = subparsers.add_parser("adjoint")
    adjoint.add_argument("--source-sha", required=True)
    adjoint.add_argument("--plan", type=Path, required=True)
    adjoint.add_argument("--plan-sha256", required=True)
    adjoint.add_argument("--tensor-cache", type=Path, required=True)
    adjoint.add_argument("--run-dir", type=Path, required=True)
    adjoint.add_argument("--snapshot-manifest", type=Path, required=True)
    adjoint.add_argument("--fine-auxiliary", type=Path, required=True)
    adjoint.add_argument("--fine-auxiliary-sha256", required=True)
    adjoint.add_argument("--structured-record", type=Path, required=True)
    adjoint.add_argument("--structured-record-sha256", required=True)
    adjoint.add_argument("--report", type=Path, required=True)
    adjoint.add_argument("--candidate-plan", type=Path, required=True)

    candidate = subparsers.add_parser("candidate")
    candidate.add_argument("--source-sha", required=True)
    candidate.add_argument("--plan", type=Path, required=True)
    candidate.add_argument("--plan-sha256", required=True)
    candidate.add_argument("--dwr-report", type=Path, required=True)
    candidate.add_argument("--dwr-report-sha256", required=True)
    candidate.add_argument("--tensor-cache", type=Path, required=True)
    candidate.add_argument("--run-dir", type=Path, required=True)

    evaluate = subparsers.add_parser("evaluate")
    evaluate.add_argument("--source-sha", required=True)
    evaluate.add_argument("--run-dir", type=Path, required=True)
    evaluate.add_argument("--plan", type=Path, required=True)
    evaluate.add_argument("--plan-sha256", required=True)
    evaluate.add_argument("--dwr-report", type=Path, required=True)
    evaluate.add_argument("--dwr-report-sha256", required=True)
    evaluate.add_argument("--structured-record", type=Path, required=True)
    evaluate.add_argument("--structured-record-sha256", required=True)
    evaluate.add_argument("--output", type=Path, required=True)
    return parser


def main() -> None:
    args = _parser().parse_args()
    {
        "prepare": _prepare,
        "snapshot": _snapshot,
        "adjoint": _adjoint,
        "candidate": _candidate,
        "evaluate": _evaluate,
    }[args.command](args)


if __name__ == "__main__":
    main()
