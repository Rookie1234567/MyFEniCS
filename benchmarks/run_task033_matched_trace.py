"""Measured Task033 Phase-B matching-interface component shard."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time
from typing import Any

import basix
from basix.ufl import element
import dolfinx
from dolfinx import default_real_type, fem
from mpi4py import MPI
import numpy as np
from petsc4py import PETSc

try:
    import resource
except ModuleNotFoundError:  # pragma: no cover - Windows host research path
    resource = None

from benchmarks.task033_matched_trace_qualification import (
    matched_trace_shard_gate,
)
from src.common.config_3d import target_stage4_config
from src.common.high_order_quadrature import high_order_quadrature_policy
from src.constraints.high_order_floquet_trace import high_order_trace_layout
from src.coupling.modal_trace_projection import (
    ModalTraceProjection,
    build_matched_interface_trace,
    extract_tangential_trace,
)
from src.geometry.mesh_builder_3d import _structured_hexa_mesh, stage4_axis_plan
from src.modes.cross_section_spaces import (
    build_cross_section_spaces,
    build_matching_cross_section,
)
from src.modes.mode_classification import build_biorthogonal_mode_basis
from src.modes.quadratic_beta_eigenproblem import (
    analytic_homogeneous_beta,
    assemble_quadratic_beta_operators,
    solve_quadratic_beta_modes,
)


ROOT = Path(__file__).resolve().parents[1]
CONTAINER_DIGEST = (
    "sha256:08c61b2cde742442b0031437dbc5160db979494587e6b6364f7935beb29dd76d"
)


def _git(*args: str) -> str | None:
    try:
        return subprocess.check_output(
            ["git", *args],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _source_start(
    comm: MPI.Intracomm,
    verified_clean_sha: str | None,
    allow_dirty_research: bool,
) -> dict[str, Any]:
    if comm.rank == 0:
        head = _git("rev-parse", "HEAD")
        branch = _git("branch", "--show-current")
        status = _git("status", "--porcelain", "--untracked-files=no")
        payload = (head, branch, status)
    else:
        payload = None
    head, branch, tracked_status = comm.bcast(payload, root=0)
    if head is None or tracked_status is None:
        raise SystemExit("Cannot establish Task033 Phase-B source identity.")
    if verified_clean_sha is not None:
        verified = verified_clean_sha.strip().lower()
        if (
            len(verified) != 40
            or any(character not in "0123456789abcdef" for character in verified)
            or head.lower() != verified
        ):
            raise SystemExit(
                "--verified-clean-sha must be the full current HEAD SHA."
            )
        if tracked_status:
            raise SystemExit(
                "Tracked source is dirty despite the clean-source attestation."
            )
        verification = "host_and_container_git_clean_attestation"
    else:
        if tracked_status and not allow_dirty_research:
            raise SystemExit(
                "Tracked source is dirty. Commit Phase-B code first or use "
                "--allow-dirty-research for a non-qualifying run."
            )
        verification = (
            "dirty_research_opt_in"
            if tracked_status
            else "container_local_git_status"
        )
    return {
        "commit_sha": head,
        "branch": branch,
        "tracked_status_before": tracked_status,
        "source_clean_verified": not bool(tracked_status),
        "verified_clean_sha": verified_clean_sha,
        "verification": verification,
    }


def _source_finish(
    comm: MPI.Intracomm,
    source: dict[str, Any],
) -> dict[str, Any]:
    if comm.rank == 0:
        payload = (
            _git("rev-parse", "HEAD"),
            _git("status", "--porcelain", "--untracked-files=no"),
        )
    else:
        payload = None
    head_after, status_after = comm.bcast(payload, root=0)
    stable = (
        head_after == source["commit_sha"]
        and status_after == source["tracked_status_before"]
    )
    return {
        **source,
        "head_after_sha": head_after,
        "tracked_status_after": status_after,
        "source_stable_during_run": bool(stable),
    }


def _historical_peak_rss_mb() -> float | None:
    if resource is None:
        return None
    return float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) / 1024.0


def _distributed_relative_error(
    actual: fem.Function,
    expected: fem.Function,
) -> float:
    index_map = actual.function_space.dofmap.index_map
    owned = int(index_map.size_local * actual.function_space.dofmap.index_map_bs)
    difference = actual.x.array[:owned] - expected.x.array[:owned]
    local_num = float(np.vdot(difference, difference).real)
    local_den = float(
        np.vdot(expected.x.array[:owned], expected.x.array[:owned]).real
    )
    comm = actual.function_space.mesh.comm
    numerator = float(comm.allreduce(local_num, op=MPI.SUM))
    denominator = float(comm.allreduce(local_den, op=MPI.SUM))
    return float(np.sqrt(numerator / max(denominator, 1.0e-30)))


def _matrix_relative_difference(first: PETSc.Mat, second: PETSc.Mat) -> float:
    difference = first.copy()
    try:
        difference.axpy(
            -1.0,
            second,
            structure=PETSc.Mat.Structure.SAME_NONZERO_PATTERN,
        )
        return float(
            difference.norm(PETSc.NormType.FROBENIUS)
            / max(first.norm(PETSc.NormType.FROBENIUS), 1.0e-30)
        )
    finally:
        difference.destroy()


def _complex_pair(value: complex) -> list[float]:
    return [float(value.real), float(value.imag)]


def _matching_mesh_hash(
    x_values: np.ndarray,
    y_values: np.ndarray,
    *,
    bottom_z_nm: float,
    top_z_nm: float,
) -> str:
    digest = hashlib.sha256()
    for name, values in (
        ("x", x_values),
        ("y", y_values),
        ("z", np.asarray([bottom_z_nm, top_z_nm], dtype=np.float64)),
    ):
        digest.update(name.encode("ascii"))
        canonical = np.asarray(values, dtype="<f8")
        digest.update(np.asarray(canonical.shape, dtype="<i8").tobytes())
        digest.update(canonical.tobytes())
    return digest.hexdigest()


def _space_owned_and_ghost_dofs(space: fem.FunctionSpace) -> tuple[int, int]:
    index_map = space.dofmap.index_map
    block_size = int(space.dofmap.index_map_bs)
    return (
        int(index_map.size_local * block_size),
        int(index_map.num_ghosts * block_size),
    )


def _affine_trace_validation(
    cfg,
    cross_section,
    spaces,
    *,
    degree: int,
) -> tuple[
    fem.FunctionSpace,
    list[dict[str, Any]],
    dict[str, Any],
    str,
]:
    comm = cross_section.mesh.comm
    plan = stage4_axis_plan(cfg, comm.size)
    source_mesh = _structured_hexa_mesh(
        comm,
        plan.x_values,
        plan.y_values,
        plan.z_values,
    )
    source_space = fem.functionspace(
        source_mesh,
        element(
            "N1curl",
            source_mesh.basix_cell(),
            degree,
            dtype=default_real_type,
        ),
    )
    source = fem.Function(
        source_space,
        name=f"task033_phaseB_p{degree}_affine_source",
    )

    def field(x):
        return np.vstack(
            (
                1.0 + 0.25j + 0.02 * x[1] + 0.01 * x[2],
                -0.4 + 0.15j + 0.03 * x[0] - 0.005 * x[2],
                0.2 - 0.1j + 0.01 * x[0],
            )
        )

    source.interpolate(field)
    source.x.scatter_forward()
    interfaces: list[dict[str, Any]] = []
    logical_axis_bytes = 0
    for side in ("bottom", "top"):
        interface = build_matched_interface_trace(
            cfg,
            cross_section,
            spaces,
            source_mesh,
            side,
        )
        actual, extraction = extract_tangential_trace(source, interface)
        z_nm = interface.convention.z_nm
        expected = fem.Function(spaces.transverse)
        expected.interpolate(
            lambda x, z=z_nm: np.vstack(
                (
                    1.0 + 0.25j + 0.02 * x[1] + 0.01 * z,
                    -0.4 + 0.15j + 0.03 * x[0] - 0.005 * z,
                )
            )
        )
        expected.x.scatter_forward()
        sample = np.asarray([[2.0 + 0.5j, -3.0 + 0.25j]])
        local_fem = interface.convention.n_cross_tangential(
            sample,
            domain="local_fem",
        )
        modal = interface.convention.n_cross_tangential(
            sample,
            domain="modal",
        )
        interfaces.append(
            {
                "side": side,
                "z_nm": float(z_nm),
                "canonical_trace": "(E_x,E_y)",
                "local_fem_outward_normal": list(
                    interface.convention.local_fem_outward_normal
                ),
                "modal_outward_normal": list(
                    interface.convention.modal_outward_normal
                ),
                "middle_adjacent_cell_sign": int(
                    interface.convention.middle_adjacent_cell_sign
                ),
                "global_interface_facets": int(
                    interface.global_interface_facet_count
                ),
                "global_middle_adjacent_cells": int(
                    interface.global_middle_adjacent_cell_count
                ),
                "global_trace_dofs": int(interface.global_trace_dofs),
                "global_query_points": int(extraction.global_query_points),
                "global_source_evaluations": int(
                    extraction.global_source_evaluations
                ),
                "unresolved_points": int(extraction.unresolved_points),
                "relative_trace_coefficient_error": (
                    _distributed_relative_error(actual, expected)
                ),
                "normal_opposition_error": float(
                    np.linalg.norm(local_fem + modal)
                ),
                "field_vector_gathered": extraction.field_vector_gathered,
                "tangential_value_bytes_sent": int(
                    extraction.tangential_value_bytes_sent
                ),
                "tangential_value_bytes_received": int(
                    extraction.tangential_value_bytes_received
                ),
            }
        )
        local_axis_entries = sum(
            len(np.unique(np.asarray(source_mesh.geometry.x[:, axis])))
            for axis in range(3)
        )
        global_axis_entries = int(
            comm.allreduce(local_axis_entries, op=MPI.SUM)
        )
        logical_axis_bytes += int(
            global_axis_entries
            * np.dtype(np.float64).itemsize
            * max(comm.size - 1, 0)
        )
    source_owned, source_ghost = _space_owned_and_ghost_dofs(source_space)
    trace_owned, trace_ghost = _space_owned_and_ghost_dofs(spaces.transverse)
    local_ownership = {
        "rank": int(comm.rank),
        "source_owned_dofs": source_owned,
        "source_ghost_dofs": source_ghost,
        "trace_owned_dofs": trace_owned,
        "trace_ghost_dofs": trace_ghost,
    }
    mesh_hash = _matching_mesh_hash(
        cross_section.x_values,
        cross_section.y_values,
        bottom_z_nm=interfaces[0]["z_nm"],
        top_z_nm=interfaces[1]["z_nm"],
    )
    communication = {
        "tangential_value_bytes_sent": int(
            sum(item["tangential_value_bytes_sent"] for item in interfaces)
        ),
        "tangential_value_bytes_received": int(
            sum(item["tangential_value_bytes_received"] for item in interfaces)
        ),
        "coordinate_axis_allgather_logical_payload_bytes": logical_axis_bytes,
        "coordinate_axis_payload_note": (
            "Logical float64 axis-metadata payload across peers; transport "
            "protocol overhead is not counted."
        ),
    }
    return source_space, interfaces, {
        "local_ownership": local_ownership,
        "communication": communication,
        "matching_xy_axes": bool(
            np.array_equal(plan.x_values, cross_section.x_values)
            and np.array_equal(plan.y_values, cross_section.y_values)
        ),
    }, mesh_hash


def _modal_projection_validation(
    cfg,
    cross_section,
    spaces,
    *,
    degree: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    policy = high_order_quadrature_policy(
        field_degree=degree,
        geometry_degree=1,
        coefficient_degree=0,
    )
    operators = assemble_quadratic_beta_operators(
        cfg,
        cross_section,
        spaces,
    )
    target = analytic_homogeneous_beta(cfg, cfg.n_air)
    right_modes, solve_report = solve_quadratic_beta_modes(
        operators,
        target=target,
        requested_modes=2,
    )
    basis = None
    base = None
    raised = None
    try:
        basis = build_biorthogonal_mode_basis(
            cfg,
            cross_section,
            spaces,
            operators,
            right_modes,
            adjoint_target=np.conj(target),
            requested_left_modes=2,
        )
        base = ModalTraceProjection(
            spaces,
            basis,
            quadrature_degree=policy.selected_degree,
        )
        raised = ModalTraceProjection(
            spaces,
            basis,
            quadrature_degree=policy.raised_comparison_degree,
        )
        coefficients = np.asarray([0.7 + 0.2j, -0.3 + 0.4j])
        base_round_trip = base.round_trip(coefficients)
        raised_round_trip = raised.round_trip(coefficients)
        base_trace = base.reconstruct(coefficients)
        raised_trace = raised.reconstruct(coefficients)
        left_unit_errors = []
        for mode_index, trace in enumerate(base.right_traces):
            expected = np.zeros(len(base.right_traces), dtype=np.complex128)
            expected[mode_index] = 1.0
            actual = base.project(trace)
            left_unit_errors.append(
                float(
                    np.linalg.norm(actual - expected)
                    / max(np.linalg.norm(expected), 1.0e-30)
                )
            )
        mass_info = base.mass.getInfo(PETSc.Mat.InfoType.GLOBAL_SUM)
        gram_singular_values = np.linalg.svd(
            base.gram,
            compute_uv=False,
        )
        mode_diagnostics = []
        for index, mode in enumerate(basis.modes):
            mode_diagnostics.append(
                {
                    "mode_index": index,
                    "beta_per_nm": _complex_pair(complex(mode.beta)),
                    "direction": mode.direction,
                    "kind": mode.kind,
                    "passive_branch_valid": bool(mode.passive_branch_valid),
                    "right_polynomial_relative_residual": float(
                        mode.right.polynomial_relative_residual
                    ),
                    "left_polynomial_relative_residual": float(
                        mode.left_polynomial_relative_residual
                    ),
                    "left_right_beta_pair_relative_error": float(
                        basis.left_pair_relative_errors[index]
                    ),
                    "qprime_left_right_overlap_after": _complex_pair(
                        complex(mode.qprime_overlap_after)
                    ),
                    "left_unit_projection_relative_error": left_unit_errors[index],
                }
            )
        block_diagnostics = [
            {
                "indices": list(group.indices),
                "beta_center_per_nm": _complex_pair(group.beta_center),
                "max_relative_beta_spread": float(
                    group.max_relative_beta_spread
                ),
                "overlap_condition": float(group.overlap_condition),
                "normalization_method": group.normalization_method,
                "post_normalization_identity_error": float(
                    group.post_normalization_identity_error
                ),
            }
            for group in basis.groups
        ]
        projection_record = {
            "material_kind": cross_section.material_kind,
            "mode_count": len(base.right_traces),
            "qep_requested_modes": 2,
            "qep_converged_modes": int(solve_report.converged_modes),
            "reconstruction_shape": list(base.reconstruction_shape),
            "projection_shape": list(base.projection_shape),
            "small_dense_gram_shape": list(base.small_dense_shape),
            "gram_rank": int(np.linalg.matrix_rank(base.gram)),
            "gram_condition": float(base.gram_condition),
            "gram_singular_values": [
                float(value) for value in gram_singular_values
            ],
            "coefficient_relative_error": float(
                base_round_trip.coefficient_relative_error
            ),
            "trace_reconstruction_relative_residual": float(
                base_round_trip.trace_relative_residual
            ),
            "right_reconstruction_base_raised_relative_error": (
                _distributed_relative_error(base_trace, raised_trace)
            ),
            "left_unit_projection_relative_errors": left_unit_errors,
            "trace_mass_nz_used": int(mass_info["nz_used"]),
            "mode_diagnostics": mode_diagnostics,
            "block_diagnostics": block_diagnostics,
            "biorthogonality_max_entry_identity_error": float(
                basis.max_entry_identity_error
            ),
            "full_vector_gathered": bool(
                base.full_vector_gathered or basis.full_vector_gathered
            ),
            "dense_interface_operator_formed": bool(
                base.dense_interface_operator_formed
            ),
            "storage": {
                "distributed_right_trace_bytes": int(
                    base.global_trace_dofs
                    * len(base.right_traces)
                    * np.dtype(PETSc.ScalarType).itemsize
                ),
                "distributed_left_trace_bytes": int(
                    base.global_trace_dofs
                    * len(base.left_traces)
                    * np.dtype(PETSc.ScalarType).itemsize
                ),
                "replicated_gram_bytes_per_rank": int(base.gram.nbytes),
                "dense_NGamma_squared_bytes": 0,
            },
        }
        denominator = max(np.linalg.norm(base.gram), 1.0e-30)
        coefficient_denominator = max(
            np.linalg.norm(base_round_trip.projected_coefficients),
            1.0e-30,
        )
        quadrature_record = {
            "policy": policy.policy,
            "field_degree": policy.field_degree,
            "geometry_degree": policy.geometry_degree,
            "coefficient_degree": policy.coefficient_degree,
            "selected_degree": policy.selected_degree,
            "raised_degree": policy.raised_comparison_degree,
            "qep_selected_degree": int(operators.quadrature_degree),
            "trace_mass_matrix_relative_delta": _matrix_relative_difference(
                base.mass,
                raised.mass,
            ),
            "gram_relative_delta": float(
                np.linalg.norm(base.gram - raised.gram) / denominator
            ),
            "coefficient_round_trip_relative_delta": float(
                np.linalg.norm(
                    base_round_trip.projected_coefficients
                    - raised_round_trip.projected_coefficients
                )
                / coefficient_denominator
            ),
        }
        return projection_record, quadrature_record
    finally:
        if raised is not None:
            raised.destroy()
        if base is not None:
            base.destroy()
        if basis is not None:
            basis.destroy()
        else:
            for mode in right_modes:
                mode.destroy()
        operators.destroy()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run one Task033 Phase-B matched-trace component shard."
    )
    parser.add_argument("--degree", type=int, choices=(2, 3, 4), required=True)
    parser.add_argument("--h-nm", type=float, default=10.0)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verified-clean-sha")
    parser.add_argument("--allow-dirty-research", action="store_true")
    parser.add_argument("--container-image", default="myfenics-stage4:task28")
    parser.add_argument("--container-digest", default=CONTAINER_DIGEST)
    parser.add_argument(
        "--host-environment-id",
        default=os.environ.get("TASK033_HOST_ENVIRONMENT_ID", "SK-20260601OSDE"),
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    comm = MPI.COMM_WORLD
    started = time.perf_counter()
    source = _source_start(
        comm,
        args.verified_clean_sha,
        args.allow_dirty_research,
    )
    cfg = target_stage4_config(degree=args.degree, h_nm=args.h_nm)
    cross_section = build_matching_cross_section(cfg, "stage4_xy")
    spaces = build_cross_section_spaces(
        cross_section,
        transverse_degree=args.degree,
    )

    trace_started = time.perf_counter()
    source_space, interfaces, trace_runtime, mesh_hash = (
        _affine_trace_validation(
            cfg,
            cross_section,
            spaces,
            degree=args.degree,
        )
    )
    trace_seconds = float(
        comm.allreduce(time.perf_counter() - trace_started, op=MPI.MAX)
    )
    projection_started = time.perf_counter()
    projection, quadrature = _modal_projection_validation(
        cfg,
        cross_section,
        spaces,
        degree=args.degree,
    )
    projection_seconds = float(
        comm.allreduce(time.perf_counter() - projection_started, op=MPI.MAX)
    )
    source = _source_finish(comm, source)

    layout = high_order_trace_layout(args.degree)
    quadrilateral = element(
        "N1curl",
        "quadrilateral",
        args.degree,
    ).basix_element
    trace_map = spaces.transverse.dofmap.index_map
    source_map = source_space.dofmap.index_map
    source_global_dofs = int(
        source_map.size_global * source_space.dofmap.index_map_bs
    )
    trace_global_dofs = int(
        trace_map.size_global * spaces.transverse.dofmap.index_map_bs
    )
    ownership = comm.gather(
        trace_runtime["local_ownership"],
        root=0,
    )
    rss = comm.gather(
        {
            "rank": comm.rank,
            "historical_peak_rss_mb": _historical_peak_rss_mb(),
        },
        root=0,
    )
    total_seconds = float(
        comm.allreduce(time.perf_counter() - started, op=MPI.MAX)
    )
    interface_geometry = {
        "matching_mesh_sha256": mesh_hash,
        "matching_xy_axes": trace_runtime["matching_xy_axes"],
        "x_cells": int(len(cross_section.x_values) - 1),
        "y_cells": int(len(cross_section.y_values) - 1),
        "geometry_degree": 1,
        "canonical_trace_orientation": "(E_x,E_y)",
        "bottom_top_local_normals_are_opposites": True,
        "local_modal_normals_are_opposites": True,
        "normal_conventions": [
            {
                "side": item["side"],
                "local_fem_outward_normal": item[
                    "local_fem_outward_normal"
                ],
                "modal_outward_normal": item["modal_outward_normal"],
            }
            for item in interfaces
        ],
    }
    signature_payload = {
        "degree": args.degree,
        "space_global_dofs": [source_global_dofs, trace_global_dofs],
        "interface_geometry": interface_geometry,
        "interfaces": interfaces,
        "projection": projection,
        "quadrature": quadrature,
    }
    local_signature = hashlib.sha256(
        json.dumps(
            signature_payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    rank_signatures = comm.gather(local_signature, root=0)

    status = None
    if comm.rank == 0:
        timestamp = datetime.now(timezone.utc).isoformat()
        record: dict[str, Any] = {
            "schema_version": "task033.phaseB-matched-trace.v1",
            "record_type": "measured_phaseB_matched_trace_component",
            "status": "pending_recomputation",
            "timestamp_utc": timestamp,
            "metadata": {
                "source": source,
                "timestamp_utc": timestamp,
                "command": "python -m benchmarks.run_task033_matched_trace "
                + " ".join(shlex.quote(value) for value in sys.argv[1:]),
                "mpi_size": comm.size,
                "container_image": args.container_image,
                "container_digest": args.container_digest,
                "host_environment_id": args.host_environment_id,
                "scalar_dtype": str(np.dtype(PETSc.ScalarType)),
                "basix_version": basix.__version__,
                "dolfinx_version": dolfinx.__version__,
            },
            "configuration": {
                "degree": args.degree,
                "h_nm": args.h_nm,
                "fixture": "small_matching_stage4_xy_interface",
                "material_kind": "stage4_xy",
                "requested_modes": 2,
            },
            "space_identity": {
                "source_3d": {
                    "family": "N1curl",
                    "cell": "hexahedron",
                    "degree": args.degree,
                    "global_dofs": source_global_dofs,
                    "element_dimension": layout.hexahedron_dimension,
                    "edge_dofs_per_entity": layout.edge_dofs,
                    "face_interior_dofs_per_entity": (
                        layout.face_interior_dofs
                    ),
                    "cell_interior_dofs": layout.cell_interior_dofs,
                    "face_trace_dofs_per_cell": layout.face_trace_dofs,
                },
                "trace_2d": {
                    "family": "N1curl",
                    "cell": "quadrilateral",
                    "degree": args.degree,
                    "global_dofs": trace_global_dofs,
                    "cell_dofs": int(quadrilateral.dim),
                    "edge_dofs_per_entity": int(
                        len(quadrilateral.entity_dofs[1][0])
                    ),
                    "cell_interior_dofs": int(
                        len(quadrilateral.entity_dofs[2][0])
                    ),
                },
                "trace_identity_check": (
                    layout.face_trace_dofs == int(quadrilateral.dim)
                ),
            },
            "interface_geometry": interface_geometry,
            "algebra": {
                "three_d_to_two_d_lifting_shape": [
                    trace_global_dofs,
                    source_global_dofs,
                ],
                "lifting_realization": (
                    "distributed point ownership and interpolation; "
                    "rectangular matrix not materialized"
                ),
                "projection_shape": projection["projection_shape"],
                "reconstruction_shape": projection["reconstruction_shape"],
                "trace_mass_nz_used": projection["trace_mass_nz_used"],
                "gram_rank": projection["gram_rank"],
                "gram_condition": projection["gram_condition"],
            },
            "accuracy": {
                "affine_tangential_trace": interfaces,
                "coefficient_round_trip_relative_error": projection[
                    "coefficient_relative_error"
                ],
                "right_reconstruction_relative_residual": projection[
                    "trace_reconstruction_relative_residual"
                ],
                "left_projection_relative_errors": projection[
                    "left_unit_projection_relative_errors"
                ],
                "normal_or_E_cross_normal_error": max(
                    item["normal_opposition_error"] for item in interfaces
                ),
            },
            "modal_projection": projection,
            "quadrature": quadrature,
            "mpi": {
                "ownership_by_rank": ownership,
                "source_scatter_forward": True,
                "trace_scatter_forward": True,
                "point_ownership_method": (
                    "dolfinx.geometry.determine_point_ownership"
                ),
                "ghost_handling": (
                    "distributed meshes use shared-facet ghosts; source and "
                    "trace coefficients call scatter_forward before evaluation"
                ),
                **trace_runtime["communication"],
                "rank_signatures": rank_signatures,
            },
            "scalability": {
                "full_3d_field_gathered": False,
                "full_mode_vector_gathered": False,
                "dense_interface_square_formed": False,
                "only_small_dense_object": list(
                    projection["small_dense_gram_shape"]
                ),
                "historical_peak_rss_by_rank": rss,
                "trace_seconds_max_rank": trace_seconds,
                "projection_seconds_max_rank": projection_seconds,
                "total_seconds_max_rank": total_seconds,
            },
            "scope": {
                "target_full3d_solve": "not_run",
                "target_hybrid_solve": "not_run",
                "case090": "not_rerun",
                "qep36_campaign": "not_rerun",
                "phaseC": "not_started",
            },
        }
        first_report = matched_trace_shard_gate(record)
        record["status"] = first_report["status"]
        final_report = matched_trace_shard_gate(record)
        record["recomputed_gate_report"] = final_report
        status = record["status"]
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(
            json.dumps(
                {
                    "status": status,
                    "degree": args.degree,
                    "mpi_size": comm.size,
                    "failed_checks": final_report["failed_checks"],
                },
                indent=2,
            )
        )
    status = comm.bcast(status, root=0)
    if status != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
