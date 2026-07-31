"""Task036 Review V4 exact one-z-cell discrete Bloch audit.

The runner is intentionally narrow: one frozen A004-S material/input identity,
one real p5 ``6 x 4 x 1`` H(curl) layer, and an optional single same-input
Full3D solve used only by the exact interface oracle.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
import time
from typing import Any, Sequence

import dolfinx_mpc
import numpy as np
from dolfinx import fem
from mpi4py import MPI
from petsc4py import PETSc

from src.common.config_3d import (
    ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND,
    target_stage4_config,
)
from src.constraints.floquet_3d import build_double_floquet_mpc
from src.constraints.floquet_3d_high_order import (
    build_high_order_constraint_data,
)
from src.coupling.modal_trace_projection import (
    ModalTraceProjection,
    _mass_norm,
    _overlap_matrix,
    _trace_from_full_mode_vector,
    build_matched_interface_trace,
    extract_tangential_trace,
)
from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
from src.modes.cross_section_spaces import (
    build_cross_section_spaces,
    build_matching_cross_section,
)
from src.modes.mode_classification import (
    PoyntingFluxEvaluator,
    build_biorthogonal_mode_basis,
    build_scalar_stage4_reciprocal_negative_basis,
    select_passive_direction_modes,
)
from src.modes.quadratic_beta_eigenproblem import (
    analytic_homogeneous_beta,
    assemble_quadratic_beta_operators,
    solve_quadratic_beta_modes,
)
from src.modes.stable_propagation import (
    build_two_sided_propagation,
)
from src.postprocessing.hybrid_field_reconstruction import (
    ModalFieldReconstructor,
)
from src.solvers.common_3d_forms import _build_variational_forms
from src.solvers.common_3d_solve import _create_nedelec_space
from src.solvers.hcurl_assembly_time_condensation import (
    build_unconstrained_assembly_time_condensation,
)
from src.solvers.hcurl_cell_static_condensation import (
    build_explicit_cell_static_condensation,
    build_floquet_independent_trace_system,
    owned_hcurl_cell_interior_dofs,
)
from src.solvers.one_cell_discrete_bloch import (
    EndpointModeLifter,
    bloch_residual_metrics,
    build_projected_two_port_schur,
    identify_endpoint_active_rows,
    lifted_endpoint_columns,
    scalar_cg_sign_fixture,
)
from src.solvers.solve_maxwell_3d_stage_4b_block_grating import (
    run_stage4b_block_grating_3d_case,
)


ROOT = Path(__file__).resolve().parents[1]
A004_SAMPLE = (
    ROOT
    / "benchmarks"
    / "artifacts"
    / "task036"
    / "6d5e9781bcb1458ecac7a77af22fa2d420f0cd55"
    / "v2_robustness"
    / "A004-S"
    / "full3d"
    / "full3d_reference_samples.npz"
)


def _git(*arguments: str) -> str:
    return subprocess.check_output(
        ["git", *arguments],
        cwd=ROOT,
        text=True,
    ).strip()


def _complex_pair(value: complex) -> list[float]:
    number = complex(value)
    return [float(number.real), float(number.imag)]


def _jsonable(value: Any) -> Any:
    if isinstance(value, complex):
        return _complex_pair(value)
    if isinstance(value, np.complexfloating):
        return _complex_pair(complex(value))
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.ndarray):
        if np.iscomplexobj(value):
            return [_complex_pair(item) for item in value.ravel()]
        return value.tolist()
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value


def _write_json(path: Path, payload: dict[str, Any], comm: MPI.Intracomm) -> None:
    error = None
    if comm.rank == 0:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(_jsonable(payload), indent=2, ensure_ascii=False)
                + "\n",
                encoding="utf-8",
            )
        except Exception as caught:
            error = f"{type(caught).__name__}: {caught}"
    error = comm.bcast(error, root=0)
    if error is not None:
        raise RuntimeError(f"Task036 JSON write failed: {error}")
    comm.Barrier()


def _write_small_npz(
    path: Path,
    arrays: dict[str, np.ndarray],
    comm: MPI.Intracomm,
    *,
    semantics: str,
) -> dict[str, Any]:
    payload = None
    error = None
    if comm.rank == 0:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(path, **arrays)
            payload = {
                "path": str(path),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "size_bytes": path.stat().st_size,
                "arrays": {
                    name: list(np.asarray(value).shape)
                    for name, value in arrays.items()
                },
                "semantics": semantics,
            }
        except Exception as caught:
            error = f"{type(caught).__name__}: {caught}"
    error = comm.bcast(error, root=0)
    if error is not None:
        raise RuntimeError(f"Task036 NPZ write failed: {error}")
    return comm.bcast(payload, root=0)


def _max_elapsed(comm: MPI.Intracomm, started: float) -> float:
    return float(comm.allreduce(time.perf_counter() - started, op=MPI.MAX))


def _progress(comm: MPI.Intracomm, message: str) -> None:
    if comm.rank == 0:
        print(f"Task036 one-cell: {message}", flush=True)


def _authority_config():
    cfg = target_stage4_config(degree=5, h_nm=10.0)
    cfg.stage4_full3d_assembly_backend = (
        ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND
    )
    cfg.matrix_diagnostics_assemble_only = False
    cfg.matrix_diagnostics_factorization_only = False
    cfg.incident_theta_deg = 89.5
    cfg.incident_phi_deg = 45.0
    cfg.polarization_kind = "s"
    cfg.grating_height = 120.0
    cfg.grating_width_x = 17.0
    cfg.mesh_axis_cell_counts = (6, 4, 14)
    cfg.dtn_y_invariant_n0_alias_preflight = True
    cfg.dtn_auxiliary_direct_projection_audit = True
    cfg.direct_release_solver_before_postprocess = True
    cfg.unique_output = False
    return cfg


def _one_cell_config(authority):
    return replace(
        authority,
        case_name="task036_a004_s_exact_one_z_cell",
        z_min=0.0,
        z_max=10.0,
        air_height=10.0,
        substrate_thickness=0.0,
        interface_z=0.0,
        grating_height=10.0,
        mesh_axis_cell_counts=(6, 4, 1),
        dtn_y_invariant_n0_alias_preflight=False,
        dtn_auxiliary_direct_projection_audit=False,
    )


def _owned_global_slave_rows(V, floquet_data) -> np.ndarray:
    index_map = V.dofmap.index_map
    local = np.unique(
        np.asarray(floquet_data.local_slave_dofs, dtype=np.int64)
    )
    local = local[(local >= 0) & (local < int(index_map.size_local))]
    owned = np.asarray(
        index_map.local_to_global(local.astype(np.int32)),
        dtype=np.int64,
    )
    packets = V.mesh.comm.allgather(owned)
    return np.asarray(
        sorted({int(value) for packet in packets for value in packet}),
        dtype=PETSc.IntType,
    )


def _global_integer_identity(
    local_values: Sequence[int],
    comm: MPI.Intracomm,
) -> dict[str, Any]:
    packets = comm.allgather(np.asarray(local_values, dtype=np.int64))
    values = np.asarray(
        sorted({int(value) for packet in packets for value in packet}),
        dtype=np.int64,
    )
    return {
        "count": int(len(values)),
        "sha256": hashlib.sha256(
            np.ascontiguousarray(values).view(np.uint8)
        ).hexdigest(),
    }


def _trace_constraint_identity(condensed) -> dict[str, Any]:
    constraints = condensed.trace_constraints
    digest = hashlib.sha256()
    for original in sorted(constraints.expansion_by_original):
        rows, coefficients = constraints.expansion_by_original[original]
        digest.update(np.asarray([original], dtype=np.int64).tobytes())
        digest.update(np.asarray(rows, dtype=np.int64).tobytes())
        digest.update(
            np.asarray(coefficients, dtype=np.complex128).tobytes()
        )
    comm = condensed.matrix.getComm().tompi4py()
    cell_interior = np.concatenate(
        [
            np.asarray(item.interior_original_dofs, dtype=np.int64)
            for item in condensed.cell_recovery_maps
        ]
    ) if condensed.cell_recovery_maps else np.empty(0, dtype=np.int64)
    return {
        "full_trace_original_rows": _global_integer_identity(
            condensed.owned_trace_original_dofs,
            comm,
        ),
        "active_root_original_rows": _global_integer_identity(
            constraints.owned_active_original_dofs,
            comm,
        ),
        "cell_interior_original_rows": _global_integer_identity(
            cell_interior,
            comm,
        ),
        "original_to_active_expansion_sha256": digest.hexdigest(),
        "slave_rows": int(constraints.slave_rows),
    }


def _standard_static_crosscheck(
    V,
    form,
    floquet_data,
    candidate,
) -> dict[str, Any]:
    """Compare the exact one-cell static matrix with assembled standard FEM."""

    embedded = dolfinx_mpc.assemble_matrix(
        fem.form(form),
        floquet_data.mpc,
        bcs=[],
    )
    embedded.assemble()
    zero = embedded.createVecRight()
    zero.set(PETSc.ScalarType(0.0))
    zero.assemble()
    post = build_explicit_cell_static_condensation(
        embedded,
        zero,
        owned_hcurl_cell_interior_dofs(V),
    )
    reference = build_floquet_independent_trace_system(
        post.matrix,
        post.rhs,
        owned_slave_original_dofs=_owned_global_slave_rows(
            V,
            floquet_data,
        ),
        original_to_trace=post.original_to_trace,
    )
    difference = candidate.matrix.copy()
    try:
        difference.axpy(
            PETSc.ScalarType(-1.0),
            reference.matrix,
            structure=PETSc.Mat.Structure.DIFFERENT_NONZERO_PATTERN,
        )
        relative = float(
            difference.norm()
            / max(reference.matrix.norm(), 1.0e-30)
        )
        return {
            "status": "pass" if relative <= 1.0e-11 else "fail",
            "relative_frobenius": relative,
            "standard_full_rows": int(embedded.getSize()[0]),
            "post_assembly_trace_rows": int(post.trace_rows),
            "independent_rows": int(reference.active_rows),
        }
    finally:
        difference.destroy()
        reference.destroy()
        post.destroy()
        zero.destroy()
        embedded.destroy()


def _mode_basis(
    cfg,
    *,
    requested_modes: int,
    candidate_modes: int,
    comm: MPI.Intracomm,
):
    cross_section = build_matching_cross_section(cfg, "stage4_xy")
    spaces = build_cross_section_spaces(
        cross_section,
        transverse_degree=5,
    )
    operators = assemble_quadratic_beta_operators(
        cfg,
        cross_section,
        spaces,
    )
    poynting = PoyntingFluxEvaluator(
        cfg,
        cross_section,
        spaces,
    )
    target = analytic_homogeneous_beta(cfg, cfg.n_air)
    right, solve_report = solve_quadratic_beta_modes(
        operators,
        target=target,
        requested_modes=candidate_modes,
        strict_profile=True,
    )
    right, selection = select_passive_direction_modes(
        right,
        desired_direction="forward",
        requested_modes=requested_modes,
        poynting_evaluator=poynting,
        maximum_abs_beta=1000.0,
    )
    if len(right) != requested_modes:
        raise RuntimeError(
            "Positive QEP did not deliver the requested finite modes: "
            f"{len(right)}/{requested_modes}."
        )
    positive = build_biorthogonal_mode_basis(
        cfg,
        cross_section,
        spaces,
        operators,
        right,
        adjoint_target=np.conj(target),
        requested_left_modes=candidate_modes,
        near_degenerate_tolerance=1.0e-6,
        block_rotation_tolerance=1.0e-6,
        task036_scalar_stage4_partition_repair=True,
        strict_qep_profile=True,
        poynting_evaluator=poynting,
        log=lambda message: _progress(comm, message),
    )
    negative = build_scalar_stage4_reciprocal_negative_basis(
        cfg,
        cross_section,
        spaces,
        operators,
        positive,
        poynting_evaluator=poynting,
    )
    return (
        cross_section,
        spaces,
        operators,
        positive,
        negative,
        {
            "target_beta_per_nm": _complex_pair(target),
            "solver_converged": int(solve_report.converged_modes),
            "requested_modes": requested_modes,
            "candidate_modes": candidate_modes,
            "right": solve_report.profile_provenance(),
            "adjoint": (
                positive.adjoint_solver_report.profile_provenance()
            ),
            "selected_indices": list(selection.selected_candidate_indices),
            "positive_groups": [
                list(group.indices) for group in positive.groups
            ],
            "negative_basis_origin": negative.basis_origin,
        },
    )


def _numerical_nnz(matrix: np.ndarray) -> int:
    scale = max(float(np.max(np.abs(matrix), initial=0.0)), 1.0e-30)
    return int(np.count_nonzero(np.abs(matrix) > 1.0e-13 * scale))


def _project_negative_traces(
    projection: ModalTraceProjection,
    negative,
    spaces,
) -> tuple[list[fem.Function], np.ndarray, dict[str, Any]]:
    traces = [
        _trace_from_full_mode_vector(
            mode.right.right_full,
            spaces,
            name=f"task036_negative_trace_{index}",
        )
        for index, mode in enumerate(negative.modes)
    ]
    coordinates = np.column_stack(
        [projection.project(trace) for trace in traces]
    )
    residuals = [
        projection.relative_residual(trace, coordinates[:, column])
        for column, trace in enumerate(traces)
    ]
    return traces, coordinates, {
        "per_trace_projection_relative_residual": residuals,
        "max_projection_relative_residual": float(
            np.max(residuals, initial=0.0)
        ),
        "coordinate_condition": float(np.linalg.cond(coordinates)),
        "coordinate_identity_relative_frobenius": float(
            np.linalg.norm(coordinates - np.eye(len(traces)), ord="fro")
            / np.sqrt(max(len(traces), 1))
        ),
        "coordinate_sha256": hashlib.sha256(
            np.ascontiguousarray(coordinates).view(np.uint8)
        ).hexdigest(),
    }


def _complex_vector(values: Sequence[complex]) -> list[list[float]]:
    return [_complex_pair(value) for value in values]


def _global_function_values(function: fem.Function) -> tuple[np.ndarray, dict[str, Any]]:
    """Return canonical owned DoFs without ghost duplication."""

    index_map = function.function_space.dofmap.index_map
    block_size = int(function.function_space.dofmap.index_map_bs)
    local_start, local_stop = map(int, index_map.local_range)
    owned_blocks = int(index_map.size_local)
    owned_values = np.asarray(
        function.x.array[: owned_blocks * block_size],
        dtype=np.complex128,
    ).copy()
    global_indices = np.asarray(
        [
            block * block_size + component
            for block in range(local_start, local_stop)
            for component in range(block_size)
        ],
        dtype=np.int64,
    )
    packets = function.function_space.mesh.comm.allgather(
        (global_indices, owned_values)
    )
    indices = np.concatenate([packet[0] for packet in packets])
    values = np.concatenate([packet[1] for packet in packets])
    order = np.argsort(indices, kind="stable")
    indices = indices[order]
    values = values[order]
    expected = int(index_map.size_global * block_size)
    if (
        len(indices) != expected
        or len(np.unique(indices)) != expected
        or not np.array_equal(indices, np.arange(expected, dtype=np.int64))
    ):
        raise RuntimeError("Canonical exact trace ownership does not close.")
    return values, {
        "global_scalar_dofs": expected,
        "block_size": block_size,
        "ownership_ranges": [
            [int(packet[0][0]), int(packet[0][-1]) + 1]
            if len(packet[0])
            else [0, 0]
            for packet in packets
        ],
        "values_sha256": hashlib.sha256(
            np.ascontiguousarray(values).view(np.uint8)
        ).hexdigest(),
    }


def _write_exact_trace_archive(
    path: Path,
    *,
    electric_traces: Sequence[fem.Function],
    z_nm: Sequence[float],
    comm: MPI.Intracomm,
) -> dict[str, Any]:
    canonical = [_global_function_values(trace) for trace in electric_traces]
    values = np.stack([item[0] for item in canonical])
    arrays = {
        "z_nm": np.asarray(z_nm, dtype=np.float64),
        "Et_canonical_owned_dofs": values,
    }
    payload = None
    error = None
    if comm.rank == 0:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(path, **arrays)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            payload = {
                "path": str(path),
                "sha256": digest,
                "size_bytes": path.stat().st_size,
                "arrays": {
                    name: list(values.shape)
                    for name, values in arrays.items()
                },
                "ownership": [item[1] for item in canonical],
                "semantics": (
                    "live post-MPC Full3D exact tangential E traces on all "
                    "eleven structured middle-region planes; canonical owned "
                    "DoFs only, no ghosts or sampled visualization field"
                ),
            }
        except Exception as caught:
            error = f"{type(caught).__name__}: {caught}"
    error = comm.bcast(error, root=0)
    if error is not None:
        raise RuntimeError(f"Task036 exact trace write failed: {error}")
    return comm.bcast(payload, root=0)


def _sampled_total_e_coefficients(
    reconstructor: ModalFieldReconstructor,
    reference_npz: Path,
) -> tuple[dict[float, np.ndarray], dict[str, Any]]:
    """Project sampled E onto the positive trace span for comparison only."""

    with np.load(reference_npz) as archive:
        x_nm = np.asarray(archive["x_nm"], dtype=np.float64)
        y_nm = np.asarray(archive["y_nm"], dtype=np.float64)
        z_nm = np.asarray(archive["z_nm"], dtype=np.float64)
        electric = np.asarray(archive["E_V_per_m"], dtype=np.complex128)
    yy, xx = np.meshgrid(y_nm, x_nm, indexing="ij")
    points = np.column_stack((xx.ravel(), yy.ravel()))
    e_basis, _h_basis = reconstructor._sample_mode_bases(points)
    count = reconstructor.mode_count_per_direction
    matrix = (
        reconstructor.cfg.electric_field_scale_V_per_m
        * e_basis[:count, ..., :2]
    ).reshape(count, -1).T
    comm = reconstructor.cross_section.mesh.comm
    payload = None
    if comm.rank == 0:
        values: dict[float, np.ndarray] = {}
        reports: dict[str, Any] = {}
        for index, z_value in enumerate(z_nm):
            target = electric[index, ..., :2].reshape(-1)
            coefficients, residual, rank, singular = np.linalg.lstsq(
                matrix,
                target,
                rcond=1.0e-10,
            )
            values[float(z_value)] = coefficients
            reports[f"{float(z_value):.12g}"] = {
                "rank": int(rank),
                "columns": int(matrix.shape[1]),
                "condition": float(singular[0] / singular[-1]),
                "relative_l2_residual": float(
                    np.sqrt(float(residual[0]))
                    / max(float(np.linalg.norm(target)), 1.0e-30)
                )
                if len(residual)
                else None,
            }
        payload = (values, reports)
    values, reports = comm.bcast(payload, root=0)
    return (
        {
            float(key): np.asarray(value, dtype=np.complex128)
            for key, value in values.items()
        },
        reports,
    )


def _local_two_way_multiplane_diagnostic(
    exact_coefficients: np.ndarray,
    forward_multiplier: Sequence[complex],
    backward_multiplier: Sequence[complex],
    negative_trace_coordinates: np.ndarray,
    *,
    groups: Sequence[Sequence[int]],
    positive_trace_metric: np.ndarray,
) -> dict[str, Any]:
    """Resolve each adjacent plane pair, then test cross-cell consistency.

    In positive Petrov coordinates, ``c_n = a_n + C Mu b_{n+1}`` and
    ``c_{n+1} = Lambda a_n + C b_{n+1}``, where ``C=D R_-`` maps the
    reciprocal negative traces into the positive trace basis.  Each pair is
    solved independently, so consistency is tested only across cells.
    """

    coefficients = np.asarray(exact_coefficients, dtype=np.complex128)
    lam = np.asarray(forward_multiplier, dtype=np.complex128)
    mu = np.asarray(backward_multiplier, dtype=np.complex128)
    coordinates = np.asarray(
        negative_trace_coordinates,
        dtype=np.complex128,
    )
    if coefficients.ndim != 2 or coefficients.shape[1] != len(lam):
        raise ValueError("Multiplane coefficient/multiplier shapes differ.")
    if mu.shape != lam.shape:
        raise ValueError("Forward/backward multiplier shapes differ.")
    if coordinates.shape != (len(lam), len(lam)):
        raise ValueError("Negative trace coordinate shape differs.")
    cells = coefficients.shape[0] - 1
    pair_matrix = coordinates - (
        lam[:, np.newaxis] * coordinates * mu[np.newaxis, :]
    )
    matrix_condition = float(np.linalg.cond(pair_matrix))
    if (
        not np.isfinite(matrix_condition)
        or matrix_condition > 1.0e12
    ):
        raise RuntimeError(
            "Exact Petrov multiplane directional resolver is ill-conditioned: "
            f"pair_matrix_cond={matrix_condition:.6e}."
        )
    forward_left = np.empty((cells, len(lam)), dtype=np.complex128)
    backward_right = np.empty_like(forward_left)
    reconstruction_residual = 0.0
    for cell in range(cells):
        left = coefficients[cell]
        right = coefficients[cell + 1]
        backward_right[cell] = np.linalg.solve(
            pair_matrix,
            right - lam * left,
        )
        forward_left[cell] = (
            left - coordinates @ (mu * backward_right[cell])
        )
        recovered_left = (
            forward_left[cell]
            + coordinates @ (mu * backward_right[cell])
        )
        recovered_right = (
            lam * forward_left[cell]
            + coordinates @ backward_right[cell]
        )
        reconstruction_residual = max(
            reconstruction_residual,
            float(
                np.linalg.norm(recovered_left - left)
                / max(np.linalg.norm(left), 1.0e-30)
            ),
            float(
                np.linalg.norm(recovered_right - right)
                / max(np.linalg.norm(right), 1.0e-30)
            ),
        )

    forward_delta = (
        lam[np.newaxis, :] * forward_left[:-1] - forward_left[1:]
    )
    backward_delta = (
        mu[np.newaxis, :] * backward_right[1:] - backward_right[:-1]
    )
    forward_scale = np.maximum(
        np.maximum(
            np.abs(lam[np.newaxis, :] * forward_left[:-1]),
            np.abs(forward_left[1:]),
        ),
        1.0e-30,
    )
    backward_scale = np.maximum(
        np.maximum(
            np.abs(mu[np.newaxis, :] * backward_right[1:]),
            np.abs(backward_right[:-1]),
        ),
        1.0e-30,
    )
    forward_per_mode = np.linalg.norm(forward_delta, axis=0) / np.maximum(
        np.linalg.norm(forward_left[1:], axis=0),
        1.0e-30,
    )
    backward_per_mode = np.linalg.norm(backward_delta, axis=0) / np.maximum(
        np.linalg.norm(backward_right[:-1], axis=0),
        1.0e-30,
    )
    negative_trace_metric = (
        coordinates.conj().T
        @ np.asarray(positive_trace_metric, dtype=np.complex128)
        @ coordinates
    )

    def physical_norm(values: np.ndarray, metric: np.ndarray) -> float:
        return float(
            np.sqrt(
                max(
                    float(
                        np.real(
                            np.einsum(
                                "ni,ij,nj->",
                                values.conj(),
                                metric,
                                values,
                            )
                        )
                    ),
                    0.0,
                )
            )
        )

    forward_predicted_all = (
        lam[np.newaxis, :] * forward_left[:-1]
    )
    forward_observed_all = forward_left[1:]
    backward_predicted_all = (
        mu[np.newaxis, :] * backward_right[1:]
    )
    backward_observed_all = backward_right[:-1]
    forward_trace_metric_relative = (
        physical_norm(
            forward_predicted_all - forward_observed_all,
            positive_trace_metric,
        )
        / max(
            physical_norm(forward_predicted_all, positive_trace_metric),
            physical_norm(forward_observed_all, positive_trace_metric),
            1.0e-30,
        )
    )
    backward_trace_metric_relative = (
        physical_norm(
            backward_predicted_all - backward_observed_all,
            negative_trace_metric,
        )
        / max(
            physical_norm(backward_predicted_all, negative_trace_metric),
            physical_norm(backward_observed_all, negative_trace_metric),
            1.0e-30,
        )
    )
    group_reports = []
    for group_values in groups:
        indices = np.asarray(tuple(group_values), dtype=np.int64)
        positive_metric_group = np.asarray(positive_trace_metric)[
            np.ix_(indices, indices)
        ]
        negative_metric_group = negative_trace_metric[
            np.ix_(indices, indices)
        ]
        forward_predicted = (
            lam[np.newaxis, indices] * forward_left[:-1, indices]
        )
        forward_observed = forward_left[1:, indices]
        backward_predicted = (
            mu[np.newaxis, indices] * backward_right[1:, indices]
        )
        backward_observed = backward_right[:-1, indices]
        group_reports.append(
            {
                "indices": indices.tolist(),
                "forward_trace_metric_relative_l2": (
                    physical_norm(
                        forward_predicted - forward_observed,
                        positive_metric_group,
                    )
                    / max(
                        physical_norm(
                            forward_predicted,
                            positive_metric_group,
                        ),
                        physical_norm(
                            forward_observed,
                            positive_metric_group,
                        ),
                        1.0e-30,
                    )
                ),
                "backward_trace_metric_relative_l2": (
                    physical_norm(
                        backward_predicted - backward_observed,
                        negative_metric_group,
                    )
                    / max(
                        physical_norm(
                            backward_predicted,
                            negative_metric_group,
                        ),
                        physical_norm(
                            backward_observed,
                            negative_metric_group,
                        ),
                        1.0e-30,
                    )
                ),
                "contract": (
                    "physical B_gamma trace norm on the frozen certified "
                    "near-degenerate group"
                ),
            }
        )
    return {
        "resolver": (
            "each adjacent exact-Petrov plane pair solves the full 2M "
            "positive/negative trace-coordinate block using C=D R_minus; "
            "propagation is tested only between independently resolved cells"
        ),
        "condition_limit": 1.0e12,
        "pair_matrix_condition": matrix_condition,
        "pair_reconstruction_relative_l2": reconstruction_residual,
        "forward_coefficients_left_planes": _complex_matrix(forward_left),
        "backward_coefficients_right_planes": _complex_matrix(
            backward_right
        ),
        "forward_cross_cell_relative_l2": float(
            np.linalg.norm(forward_delta)
            / max(np.linalg.norm(forward_left[1:]), 1.0e-30)
        ),
        "backward_cross_cell_relative_l2": float(
            np.linalg.norm(backward_delta)
            / max(np.linalg.norm(backward_right[:-1]), 1.0e-30)
        ),
        "forward_cross_cell_trace_metric_relative_l2": (
            forward_trace_metric_relative
        ),
        "backward_cross_cell_trace_metric_relative_l2": (
            backward_trace_metric_relative
        ),
        "forward_max_per_entry_relative": float(
            np.max(np.abs(forward_delta) / forward_scale, initial=0.0)
        ),
        "backward_max_per_entry_relative": float(
            np.max(np.abs(backward_delta) / backward_scale, initial=0.0)
        ),
        "forward_per_mode_relative_l2": forward_per_mode.tolist(),
        "backward_per_mode_relative_l2": backward_per_mode.tolist(),
        "near_degenerate_group_trace_metric_mismatch": group_reports,
        "forward_significant_weights": np.max(
            np.abs(forward_left) ** 2,
            axis=0,
        ).tolist(),
        "backward_significant_weights": np.max(
            np.abs(backward_right) ** 2,
            axis=0,
        ).tolist(),
    }


def _complex_matrix(values: np.ndarray) -> list[list[list[float]]]:
    matrix = np.asarray(values, dtype=np.complex128)
    return [
        [_complex_pair(value) for value in row]
        for row in matrix
    ]


def _sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_standard_static_authority(
    path: Path,
    *,
    current_source_sha: str,
) -> dict[str, Any]:
    """Reuse the existing MPI1 exact-matrix comparison in an MPI audit."""

    resolved = path.resolve()
    record = json.loads(resolved.read_text(encoding="utf-8"))
    expected_case = {
        "identity": "A004-S",
        "degree": 5,
        "h_z_nm": 10.0,
        "mesh_axis_cell_counts": [6, 4, 1],
        "material": "stage4_xy",
        "incident_grazing_deg": 0.5,
        "incident_phi_deg": 45.0,
        "polarization": "S",
    }
    equivalence = record.get("standard_static_equivalence")
    authority_sha = str(record.get("metadata", {}).get("source_sha", ""))
    authority_digest = _sha256_path(resolved)
    expected_digest = (
        "95deeb8d6f0e133b328ab59f4e2de08b40aae0f4b44363bea178d6ddf9598c44"
    )
    command = str(record.get("metadata", {}).get("command", ""))
    relative = (
        float(equivalence.get("relative_frobenius", float("nan")))
        if isinstance(equivalence, dict)
        else float("nan")
    )
    ancestry = subprocess.run(
        [
            "git",
            "merge-base",
            "--is-ancestor",
            authority_sha,
            current_source_sha,
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    kernel_paths = [
        "src/common/config_3d.py",
        "src/constraints/floquet_3d.py",
        "src/geometry/mesh_builder_3d.py",
        "src/solvers/common_3d_forms.py",
        "src/solvers/common_3d_solve.py",
        "src/solvers/hcurl_assembly_time_condensation.py",
        "src/solvers/hcurl_cell_static_condensation.py",
    ]
    kernel_diff = subprocess.run(
        [
            "git",
            "diff",
            "--name-only",
            authority_sha,
            current_source_sha,
            "--",
            *kernel_paths,
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    failures: list[str] = []
    if authority_digest != expected_digest:
        failures.append("frozen_sha256")
    if record.get("schema_version") != (
        "task036.one-cell-discrete-bloch-audit.v1"
    ):
        failures.append("schema_version")
    if record.get("status") != "row_audit_complete":
        failures.append("top_level_status")
    if record.get("case") != expected_case:
        failures.append("case_identity")
    if not isinstance(equivalence, dict):
        failures.append("standard_static_equivalence")
    elif (
        equivalence.get("status") != "pass"
        or not np.isfinite(relative)
        or not 0.0 <= relative <= 1.0e-11
    ):
        failures.append("equivalence_gate")
    elif (
        equivalence.get("standard_full_rows") != 10755
        or equivalence.get("post_assembly_trace_rows") != 4995
        or equivalence.get("independent_rows") != 4440
    ):
        failures.append("equivalence_row_identity")
    if record.get("metadata", {}).get("mpi_size") != 1:
        failures.append("mpi1_authority")
    if (
        record.get("metadata", {}).get("scalar_type") != "complex128"
        or record.get("metadata", {}).get("int_type") != "int32"
    ):
        failures.append("abi")
    if (
        "benchmarks.run_task036_one_cell_discrete_bloch" not in command
        or "--row-audit-only" not in command
        or "--standard-static-crosscheck" not in command
        or "--allow-dirty-research" in command
    ):
        failures.append("command_identity")
    rows = record.get("row_identity", {})
    assembly = record.get("assembly", {})
    if (
        rows.get("full_rows") != 10755
        or rows.get("cell_interior_rows") != 5760
        or rows.get("trace_rows_before_floquet") != 4995
        or rows.get("floquet_independent_active_rows") != 4440
        or rows.get("left_active_rows") != 1200
        or rows.get("right_active_rows") != 1200
        or rows.get("left_right_disjoint") is not True
        or assembly.get("matrix_rows") != 4440
        or assembly.get("matrix_nnz") != 1987800
    ):
        failures.append("matrix_identity")
    if not authority_sha or ancestry.returncode != 0:
        failures.append("source_ancestry")
    if kernel_diff.returncode != 0 or kernel_diff.stdout.strip():
        failures.append("matrix_kernel_identity")
    if failures:
        raise RuntimeError(
            "Existing standard/static authority failed: "
            + ", ".join(failures)
        )
    return {
        **equivalence,
        "authority_kind": "existing_mpi1_exact_matrix_equivalence",
        "authority_relative_path": str(resolved.relative_to(ROOT)),
        "authority_sha256": authority_digest,
        "authority_source_sha": authority_sha,
        "current_source_sha": current_source_sha,
        "source_ancestry_verified": True,
        "matrix_kernel_identity_verified": True,
        "measurement_mpi_size": 1,
        "mpi8_live_standard_static_crosscheck": (
            "not_run_distributed_slave_ownership_limitation"
        ),
        "reused_as_phase_a_foundation": True,
        "reuse_reason": (
            "The post-assembly comparison is serial-only; the MPI8 formal "
            "audit reuses this exact-matrix authority instead of repeating "
            "the 21-minute MPI1 comparison."
        ),
    }


def _run_exact_full3d_oracle(
    authority,
    cross_section,
    spaces,
    positive,
    negative,
    projection: ModalTraceProjection,
    scalar_one_cell,
    continuous_one_cell,
    negative_trace_coordinates: np.ndarray,
    *,
    sample_reference: Path,
    run_dir: Path,
    comm: MPI.Intracomm,
) -> tuple[
    dict[str, Any],
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
]:
    """Run one Full3D solve and audit eleven exact Petrov trace planes."""

    count = len(positive.modes)
    scalar_full_length = build_two_sided_propagation(
        [*positive.modes, *negative.modes],
        100.0,
        propagation_model="full3d_uniform_cg",
        axial_fem_degree=5,
        axial_h_nm=10.0,
    )
    continuous_full_length = build_two_sided_propagation(
        [*positive.modes, *negative.modes],
        100.0,
        propagation_model="continuous_beta",
    )
    reconstructor = ModalFieldReconstructor(
        authority,
        cross_section,
        spaces,
        positive,
        negative,
        bottom_z_nm=10.0,
        top_z_nm=110.0,
        propagation=continuous_full_length,
    )
    sampled_coefficients, sampled_fit = _sampled_total_e_coefficients(
        reconstructor,
        sample_reference,
    )

    def factor_identity(one_cell, full_length) -> dict[str, float]:
        forward_expected = np.asarray(one_cell.forward.factors) ** 10
        backward_expected = np.asarray(one_cell.backward.factors) ** 10
        forward_actual = np.asarray(full_length.forward.factors)
        backward_actual = np.asarray(full_length.backward.factors)
        return {
            "forward_max_relative": float(
                np.max(
                    np.abs(forward_expected - forward_actual)
                    / np.maximum(
                        np.maximum(
                            np.abs(forward_expected),
                            np.abs(forward_actual),
                        ),
                        1.0e-30,
                    ),
                    initial=0.0,
                )
            ),
            "backward_max_relative": float(
                np.max(
                    np.abs(backward_expected - backward_actual)
                    / np.maximum(
                        np.maximum(
                            np.abs(backward_expected),
                            np.abs(backward_actual),
                        ),
                        1.0e-30,
                    ),
                    initial=0.0,
                )
            ),
        }

    factor_identities = {
        "scalar_cg": factor_identity(
            scalar_one_cell,
            scalar_full_length,
        ),
        "continuous_beta": factor_identity(
            continuous_one_cell,
            continuous_full_length,
        ),
    }
    gram_singular = np.linalg.svd(projection.gram, compute_uv=False)
    mass_info = projection.mass.getInfo(PETSc.Mat.InfoType.GLOBAL_SUM)
    right_payloads = [
        _global_function_values(trace) for trace in projection.right_traces
    ]
    left_payloads = [
        _global_function_values(trace) for trace in projection.left_traces
    ]
    right_matrix = np.column_stack([item[0] for item in right_payloads])
    left_matrix = np.column_stack([item[0] for item in left_payloads])
    positive_trace_metric = _overlap_matrix(
        projection.mass,
        projection.right_traces,
        projection.right_traces,
    )
    gram_inverse_identity = float(
        np.linalg.norm(
            np.linalg.solve(projection.gram, projection.gram)
            - np.eye(count),
            ord="fro",
        )
        / np.sqrt(count)
    )
    z_planes = np.linspace(10.0, 110.0, 11)
    observed: dict[str, Any] = {}
    scalar_forward_weights = np.zeros(count, dtype=np.float64)
    scalar_backward_weights = np.zeros(count, dtype=np.float64)
    continuous_forward_weights = np.zeros(count, dtype=np.float64)
    continuous_backward_weights = np.zeros(count, dtype=np.float64)

    def observer(*, field, mesh_data, **_kwargs) -> None:
        traces: list[fem.Function] = []
        extraction: list[dict[str, Any]] = []
        coefficients: list[np.ndarray] = []
        for plane, z_value in enumerate(z_planes):
            side = "top" if plane == len(z_planes) - 1 else "bottom"
            interface = build_matched_interface_trace(
                authority,
                cross_section,
                spaces,
                mesh_data.mesh,
                side,
                bottom_z_nm=(
                    10.0 if side == "top" else float(z_value)
                ),
                top_z_nm=110.0,
            )
            trace, report = extract_tangential_trace(field, interface)
            coefficient = projection.project(trace)
            traces.append(trace)
            extraction.append(report.__dict__)
            coefficients.append(coefficient)
        exact = np.stack(coefficients)
        trace_archive = _write_exact_trace_archive(
            run_dir / "exact_interface_traces.npz",
            electric_traces=traces,
            z_nm=z_planes,
            comm=comm,
        )
        coefficient_archive = _write_small_npz(
            run_dir / "exact_petrov_plane_coefficients.npz",
            {
                "z_nm": z_planes,
                "coefficients": exact,
            },
            comm,
            semantics=(
                "exact D=G^-1 W^H B_gamma coefficients written before "
                "projection-residual, side-consistency, or propagation "
                "diagnostics"
            ),
        )
        projection_residuals = [
            projection.relative_residual(trace, coefficient)
            for trace, coefficient in zip(
                traces,
                coefficients,
                strict=True,
            )
        ]
        internal_side_consistency: list[dict[str, Any]] = []
        for plane, z_value in enumerate(z_planes[1:-1], start=1):
            opposite_interface = build_matched_interface_trace(
                authority,
                cross_section,
                spaces,
                mesh_data.mesh,
                "top",
                bottom_z_nm=10.0,
                top_z_nm=float(z_value),
            )
            opposite_trace, opposite_report = extract_tangential_trace(
                field,
                opposite_interface,
            )
            difference = fem.Function(spaces.transverse)
            difference.x.array[:] = (
                traces[plane].x.array - opposite_trace.x.array
            )
            difference.x.scatter_forward()
            relative = _mass_norm(
                projection.mass,
                difference,
            ) / max(
                _mass_norm(projection.mass, traces[plane]),
                _mass_norm(projection.mass, opposite_trace),
                1.0e-30,
            )
            internal_side_consistency.append(
                {
                    "z_nm": float(z_value),
                    "B_gamma_relative": float(relative),
                    "upper_cell_extraction": extraction[plane],
                    "lower_cell_extraction": opposite_report.__dict__,
                }
            )
        try:
            scalar_diagnostic = _local_two_way_multiplane_diagnostic(
                exact,
                scalar_one_cell.forward.factors,
                scalar_one_cell.backward.factors,
                negative_trace_coordinates,
                groups=[group.indices for group in positive.groups],
                positive_trace_metric=positive_trace_metric,
            )
            continuous_diagnostic = _local_two_way_multiplane_diagnostic(
                exact,
                continuous_one_cell.forward.factors,
                continuous_one_cell.backward.factors,
                negative_trace_coordinates,
                groups=[group.indices for group in positive.groups],
                positive_trace_metric=positive_trace_metric,
            )
            resolver_error = None
        except Exception as error:
            scalar_diagnostic = {}
            continuous_diagnostic = {}
            resolver_error = f"{type(error).__name__}: {error}"
        scalar_forward_weights[:] = np.asarray(
            scalar_diagnostic.get(
                "forward_significant_weights",
                np.zeros(count),
            ),
            dtype=np.float64,
        )
        scalar_backward_weights[:] = np.asarray(
            scalar_diagnostic.get(
                "backward_significant_weights",
                np.zeros(count),
            ),
            dtype=np.float64,
        )
        continuous_forward_weights[:] = np.asarray(
            continuous_diagnostic.get(
                "forward_significant_weights",
                np.zeros(count),
            ),
            dtype=np.float64,
        )
        continuous_backward_weights[:] = np.asarray(
            continuous_diagnostic.get(
                "backward_significant_weights",
                np.zeros(count),
            ),
            dtype=np.float64,
        )
        sample_bottom = sampled_coefficients[10.0]
        sample_top = sampled_coefficients[110.0]
        observed.update(
            {
                "authority_contract": {
                    "formula": "D = G^-1 W^H B_gamma; c_n = D g_n",
                    "direction_resolver": (
                        "eleven exact E-trace planes; each adjacent pair is "
                        "resolved independently, so cross-cell mismatch is "
                        "not an endpoint-fit identity and uses no traction"
                    ),
                    "uses_scalar_cg_in_exact_projection": False,
                    "uses_sampled_field_in_exact_projection": False,
                    "one_cell_to_100nm_factor_identity": factor_identities,
                },
                "trace_mass_and_basis": {
                    "quadrature_degree": projection.quadrature_degree,
                    "mass_shape": list(projection.mass.getSize()),
                    "mass_nnz": int(mass_info.get("nz_used", 0.0)),
                    "mass_frobenius_norm": float(projection.mass.norm()),
                    "gram_shape": list(projection.gram.shape),
                    "gram_sha256": hashlib.sha256(
                        np.ascontiguousarray(projection.gram).view(np.uint8)
                    ).hexdigest(),
                    "gram_condition": projection.gram_condition,
                    "gram_smallest_singular_value": float(gram_singular[-1]),
                    "D_times_R_identity_residual": gram_inverse_identity,
                    "right_trace_columns_sha256": hashlib.sha256(
                        np.ascontiguousarray(right_matrix).view(np.uint8)
                    ).hexdigest(),
                    "left_trace_columns_sha256": hashlib.sha256(
                        np.ascontiguousarray(left_matrix).view(np.uint8)
                    ).hexdigest(),
                    "right_trace_metric_sha256": hashlib.sha256(
                        np.ascontiguousarray(positive_trace_metric).view(
                            np.uint8
                        )
                    ).hexdigest(),
                    "right_column_ownership": right_payloads[0][1],
                    "left_column_ownership": left_payloads[0][1],
                },
                "exact_petrov_planes": {
                    "z_nm": z_planes.tolist(),
                    "coefficients": _complex_matrix(exact),
                    "projection_relative_residual": projection_residuals,
                    "max_projection_relative_residual": float(
                        np.max(projection_residuals, initial=0.0)
                    ),
                    "trace_extraction": extraction,
                    "internal_two_sided_trace_consistency": (
                        internal_side_consistency
                    ),
                    "max_internal_two_sided_B_gamma_relative": float(
                        max(
                            (
                                item["B_gamma_relative"]
                                for item in internal_side_consistency
                            ),
                            default=0.0,
                        )
                    ),
                    "coefficient_archive": coefficient_archive,
                },
                "selected_scalar_cg_propagation": scalar_diagnostic,
                "continuous_beta_propagation": continuous_diagnostic,
                "direction_resolver_error": resolver_error,
                "sampled_vs_exact": {
                    "sample_path": str(sample_reference),
                    "sample_sha256": _sha256_path(sample_reference),
                    "sample_size_bytes": sample_reference.stat().st_size,
                    "sample_fit": sampled_fit,
                    "sampled_bottom_total_E_coefficients": _complex_vector(
                        sample_bottom
                    ),
                    "sampled_top_total_E_coefficients": _complex_vector(
                        sample_top
                    ),
                    "exact_bottom_total_E_coefficients": _complex_vector(
                        exact[0]
                    ),
                    "exact_top_total_E_coefficients": _complex_vector(
                        exact[-1]
                    ),
                    "bottom_total_E_coefficient_relative_l2": float(
                        np.linalg.norm(sample_bottom - exact[0])
                        / max(
                            np.linalg.norm(sample_bottom),
                            np.linalg.norm(exact[0]),
                            1.0e-30,
                        )
                    ),
                    "top_total_E_coefficient_relative_l2": float(
                        np.linalg.norm(sample_top - exact[-1])
                        / max(
                            np.linalg.norm(sample_top),
                            np.linalg.norm(exact[-1]),
                            1.0e-30,
                        )
                    ),
                    "sampled_authority": (
                        "diagnostic 40x20 E collocation only"
                    ),
                    "exact_authority": (
                        "live FE B_gamma/Petrov projection on 11 exact "
                        "structured z planes"
                    ),
                },
                "trace_archive": trace_archive,
            }
        )

    summary = run_stage4b_block_grating_3d_case(
        authority,
        run_dir,
        solution_observer=observer,
    )
    if not observed:
        raise RuntimeError("The Full3D exact trace observer was not called.")
    residual = summary.get("linear_system_relative_residual")
    energy = summary.get("energy_closure_error_dtn_port_modal_volume")
    full3d_pass = bool(
        summary.get("case_status") == "completed"
        and summary.get("official_result") is True
        and residual is not None
        and float(residual) <= 1.0e-9
        and summary.get("stage4_energy_balance_pass") is True
        and energy is not None
        and abs(float(energy)) <= 1.0e-5
    )
    observed["full3d_solve"] = {
        "status": "pass" if full3d_pass else "fail",
        "case_status": summary.get("case_status"),
        "official_result": summary.get("official_result"),
        "true_relative_residual": residual,
        "true_residual_gate": 1.0e-9,
        "stage4_energy_balance_pass": summary.get(
            "stage4_energy_balance_pass"
        ),
        "energy_closure_error_dtn_port_modal_volume": energy,
        "energy_gate": 1.0e-5,
        "R_total": summary.get("R_total"),
        "T_total": summary.get("T_total"),
        "A_closure": (
            None
            if summary.get("R_total") is None
            or summary.get("T_total") is None
            else 1.0 - summary["R_total"] - summary["T_total"]
        ),
    }
    observed["status"] = "pass" if full3d_pass else "failed_full3d_gate"
    return (
        observed,
        scalar_forward_weights,
        scalar_backward_weights,
        continuous_forward_weights,
        continuous_backward_weights,
    )


def _phase_a_decision(
    *,
    standard_crosscheck: dict[str, Any] | None,
    trace_basis: dict[str, Any],
    scalar_metrics: dict[str, Any],
    exact_oracle: dict[str, Any],
) -> dict[str, Any]:
    forward = scalar_metrics["forward"]
    backward = scalar_metrics["backward"]
    negative = trace_basis["negative_trace_representation"]
    exact_scalar = exact_oracle.get(
        "selected_scalar_cg_propagation",
        {},
    )
    foundation_gates = {
        "standard_static_equivalence": bool(
            standard_crosscheck is not None
            and standard_crosscheck.get("status") == "pass"
        ),
        "full3d_exact_oracle": bool(
            exact_oracle.get("status") == "pass"
        ),
        "trace_gram_condition": bool(
            float(trace_basis["gram_condition"]) <= 1.0e12
        ),
        "trace_round_trip": bool(
            float(trace_basis["projection_round_trip_coefficient_error"])
            <= 1.0e-10
        ),
        "exact_D_times_R_identity": bool(
            float(
                exact_oracle.get("trace_mass_and_basis", {}).get(
                    "D_times_R_identity_residual",
                    float("inf"),
                )
            )
            <= 1.0e-10
        ),
        "exact_full3d_trace_projection": bool(
            float(
                exact_oracle.get("exact_petrov_planes", {}).get(
                    "max_projection_relative_residual",
                    float("inf"),
                )
            )
            <= 1.0e-8
        ),
        "internal_plane_two_sided_trace_identity": bool(
            float(
                exact_oracle.get("exact_petrov_planes", {}).get(
                    "max_internal_two_sided_B_gamma_relative",
                    float("inf"),
                )
            )
            <= 1.0e-10
        ),
        "one_cell_factor_identity": bool(
            max(
                exact_oracle.get("authority_contract", {})
                .get("one_cell_to_100nm_factor_identity", {})
                .get("scalar_cg", {})
                .get("forward_max_relative", float("inf")),
                exact_oracle.get("authority_contract", {})
                .get("one_cell_to_100nm_factor_identity", {})
                .get("scalar_cg", {})
                .get("backward_max_relative", float("inf")),
            )
            <= 1.0e-12
        ),
        "right_lift_floquet_orientation_closure": bool(
            float(
                trace_basis[
                    "right_basis_floquet_orientation_closure"
                ]["max_global_normwise_relative"]
            )
            <= 1.0e-10
        ),
        "left_lift_floquet_orientation_closure": bool(
            float(
                trace_basis[
                    "left_basis_floquet_orientation_closure"
                ]["max_global_normwise_relative"]
            )
            <= 1.0e-10
        ),
        "negative_trace_span": bool(
            float(negative["max_projection_relative_residual"]) <= 1.0e-10
            and float(negative["coordinate_condition"]) <= 1.0e12
        ),
        "multiplane_pair_reconstruction": bool(
            float(
                exact_scalar.get(
                    "pair_reconstruction_relative_l2",
                    float("inf"),
                )
            )
            <= 1.0e-10
            and float(
                exact_scalar.get(
                    "pair_matrix_condition",
                    float("inf"),
                )
            )
            <= 1.0e12
        ),
    }
    residual_gates = {
        "forward_significant_rho": bool(
            float(forward.get("significant_max_rho", float("inf")))
            <= 1.0e-10
        ),
        "backward_significant_rho": bool(
            float(backward.get("significant_max_rho", float("inf")))
            <= 1.0e-10
        ),
        "forward_projected_offdiagonal": bool(
            float(forward["projected_offdiagonal_ratio"]) <= 1.0e-8
        ),
        "backward_projected_offdiagonal": bool(
            float(backward["projected_offdiagonal_ratio"]) <= 1.0e-8
        ),
        "no_connected_forward_mixing": bool(
            forward["connected_mixing"]["component_count"] == 0
        ),
        "no_connected_backward_mixing": bool(
            backward["connected_mixing"]["component_count"] == 0
        ),
        "actual_fe_wrong_sign_rejected": bool(
            float(
                forward[
                    "wrong_outward_sign_negative_control_relative"
                ]
            )
            > 1.0e-6
            and float(
                backward[
                    "wrong_outward_sign_negative_control_relative"
                ]
            )
            > 1.0e-6
        ),
    }
    foundation_pass = all(foundation_gates.values())
    diagonal_pass = all(residual_gates.values())
    exact_mismatch = max(
        float(
            exact_scalar.get(
                "forward_cross_cell_trace_metric_relative_l2",
                float("inf"),
            )
        ),
        float(
            exact_scalar.get(
                "backward_cross_cell_trace_metric_relative_l2",
                float("inf"),
            )
        ),
    )
    exact_supports = False
    if not foundation_pass:
        classification = "D_OR_PHASE_A_INDETERMINATE"
        phase_b = False
        reason = (
            "An exact trace-space, Full3D, Floquet, or directional-resolver "
            "foundation Gate failed; matrix propagation is not authorized."
        )
    elif diagonal_pass:
        classification = "A_CURRENT_PROPAGATION_PASSES_ONE_CELL_AUDIT"
        phase_b = False
        reason = (
            "The actual one-cell projected operator is diagonal to the "
            "frozen thresholds. Any remaining multiplane coefficient "
            "mismatch is not aligned with an off-diagonal mixing block."
        )
    else:
        forward_components = forward["connected_mixing"]["components"]
        backward_components = backward["connected_mixing"]["components"]
        components = [*forward_components, *backward_components]
        certified_forward_groups = [
            set(item["indices"]) for item in forward["group_residuals"]
        ]
        certified_backward_groups = [
            set(item["indices"]) for item in backward["group_residuals"]
        ]
        localized = bool(components) and (
            all(
                any(
                    set(item["indices"]).issubset(group)
                    for group in certified_forward_groups
                )
                for item in forward_components
            )
            and all(
                any(
                    set(item["indices"]).issubset(group)
                    for group in certified_backward_groups
                )
                for item in backward_components
            )
        )
        exact_groups = exact_scalar.get(
            "near_degenerate_group_trace_metric_mismatch",
            [],
        )

        def component_supported(
            component: dict[str, Any],
            direction: str,
        ) -> bool:
            component_indices = set(component["indices"])
            key = f"{direction}_trace_metric_relative_l2"
            return any(
                component_indices.issubset(set(item["indices"]))
                and float(item[key]) > 4.0e-4
                for item in exact_groups
            )

        supported = [
            *[
                component_supported(item, "forward")
                for item in forward_components
            ],
            *[
                component_supported(item, "backward")
                for item in backward_components
            ],
        ]
        exact_supports = bool(supported) and all(supported)
        if components and localized and exact_supports:
            classification = "B_NEAR_DEGENERATE_BLOCK_MIXING"
            phase_b = True
            reason = (
                "The same certified near-degenerate blocks exceed both the "
                "projected one-cell and exact B_gamma multiplane thresholds."
            )
        else:
            classification = "PHASE_A_INCOMPLETE_NO_CLEAR_MIXING_ALIGNMENT"
            phase_b = False
            reason = (
                "A one-cell Gate failed without matching exact-field and "
                "connected-block evidence; projected propagation is forbidden."
            )
    return {
        "classification": classification,
        "phase_b_authorized": phase_b,
        "foundation_gates": foundation_gates,
        "one_cell_diagonal_gates": residual_gates,
        "exact_petrov_multiplane_max_cross_cell_relative_l2": exact_mismatch,
        "exact_mismatch_supports_matrix_mixing": exact_supports,
        "reason": reason,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--verified-clean-sha", required=True)
    parser.add_argument("--requested-modes", type=int, default=120)
    parser.add_argument("--candidate-modes", type=int, default=240)
    parser.add_argument("--row-audit-only", action="store_true")
    parser.add_argument("--standard-static-crosscheck", action="store_true")
    parser.add_argument("--standard-static-authority-json", type=Path)
    parser.add_argument("--full3d-exact-oracle", action="store_true")
    parser.add_argument("--sample-reference", type=Path, default=A004_SAMPLE)
    parser.add_argument("--allow-dirty-research", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    comm = MPI.COMM_WORLD
    if comm.size not in {1, 2, 8}:
        raise SystemExit("The Review V4 audit permits only MPI1, MPI2, or MPI8.")
    if np.dtype(PETSc.ScalarType) != np.dtype(np.complex128):
        raise SystemExit("The one-cell audit requires PETSc complex128.")
    if (
        args.standard_static_crosscheck
        and args.standard_static_authority_json is not None
    ):
        raise SystemExit(
            "Choose either a live standard/static crosscheck or an existing "
            "authority JSON, not both."
        )
    if (
        args.full3d_exact_oracle
        and not args.standard_static_crosscheck
        and args.standard_static_authority_json is None
    ):
        raise SystemExit(
            "The formal exact oracle requires a live standard/static "
            "crosscheck or --standard-static-authority-json."
        )
    if args.full3d_exact_oracle and not args.sample_reference.is_file():
        raise SystemExit(
            f"Sampled comparison artifact is missing: {args.sample_reference}"
        )
    source_sha = _git("rev-parse", "HEAD")
    if source_sha != args.verified_clean_sha:
        raise SystemExit(
            f"Source SHA {source_sha} != {args.verified_clean_sha}."
        )
    dirty = _git(
        "status",
        "--short",
        "--untracked-files=all",
        "--",
        "src",
        "benchmarks",
    )
    if dirty and not args.allow_dirty_research:
        raise SystemExit(
            "Formal one-cell audit requires clean src/benchmarks:\n" + dirty
        )
    started = time.perf_counter()
    timings: dict[str, float] = {}
    authority = _authority_config()
    one_cell = _one_cell_config(authority)
    work_dir = args.work_dir.resolve()
    work_dir.mkdir(parents=True, exist_ok=True)

    stage = time.perf_counter()
    mesh_data = build_airbox_mesh_3d(
        one_cell,
        work_dir / "one_cell_mesh",
    )
    V = _create_nedelec_space(mesh_data.mesh, one_cell)
    floquet = build_double_floquet_mpc(
        V,
        mesh_data,
        one_cell,
        lambda message: _progress(comm, message),
    )
    floquet_closure_data = build_high_order_constraint_data(
        V,
        mesh_data,
        one_cell,
    )
    a, _L = _build_variational_forms(
        mesh_data.mesh,
        mesh_data,
        one_cell,
        V,
        field_formulation="total_field_dtn_port",
    )
    condensed = build_unconstrained_assembly_time_condensation(
        fem.form(a),
        V,
        mesh_data.cell_tags,
        mpc=floquet.mpc,
    )
    rows = identify_endpoint_active_rows(
        V,
        condensed,
        left_facets=mesh_data.facet_tags.find(one_cell.tags.z_min),
        right_facets=mesh_data.facet_tags.find(one_cell.tags.z_max),
    )
    timings["one_cell_static_assembly"] = _max_elapsed(comm, stage)
    _progress(
        comm,
        "static layer assembled "
        f"full={condensed.full_rows}, active={condensed.active_rows}, "
        f"ports={len(rows.left_active)}+{len(rows.right_active)}, "
        f"axial-I={len(rows.interior_active)}",
    )
    standard_crosscheck = None
    if args.standard_static_crosscheck:
        stage = time.perf_counter()
        standard_crosscheck = _standard_static_crosscheck(
            V,
            a,
            floquet,
            condensed,
        )
        timings["standard_static_crosscheck"] = _max_elapsed(comm, stage)
    elif args.standard_static_authority_json is not None:
        standard_crosscheck = _load_standard_static_authority(
            args.standard_static_authority_json,
            current_source_sha=source_sha,
        )

    payload: dict[str, Any] = {
        "schema_version": "task036.one-cell-discrete-bloch-audit.v1",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "status": "row_audit_complete",
        "metadata": {
            "source_sha": source_sha,
            "branch": _git("branch", "--show-current"),
            "mpi_size": comm.size,
            "scalar_type": str(np.dtype(PETSc.ScalarType)),
            "int_type": str(np.dtype(PETSc.IntType)),
            "command": "python -m "
            "benchmarks.run_task036_one_cell_discrete_bloch "
            + " ".join(shlex.quote(value) for value in sys.argv[1:]),
            "command_scope": (
                "exact one-z-cell Review V4 audit; no Hybrid anchor"
            ),
        },
        "case": {
            "identity": "A004-S",
            "degree": 5,
            "h_z_nm": 10.0,
            "mesh_axis_cell_counts": [6, 4, 1],
            "material": "stage4_xy",
            "incident_grazing_deg": 0.5,
            "incident_phi_deg": 45.0,
            "polarization": "S",
        },
        "sign_fixture": scalar_cg_sign_fixture(0.8 + 0.02j),
        "row_identity": {
            "full_rows": condensed.full_rows,
            "cell_interior_rows": condensed.interior_rows,
            "trace_rows_before_floquet": condensed.trace_rows,
            "floquet_independent_active_rows": condensed.active_rows,
            **rows.to_record(),
            "constraint_and_numbering_identity": (
                _trace_constraint_identity(condensed)
            ),
        },
        "floquet": {
            "constraints": floquet.num_constraints,
            "edge_constraints": floquet.num_edge_constraints,
            "face_constraints": floquet.num_face_constraints,
            "phase_x": _complex_pair(floquet.phase_x),
            "phase_y": _complex_pair(floquet.phase_y),
            "max_face_pairing_coordinate_error": (
                floquet.max_face_pairing_coordinate_error
            ),
            "max_edge_midpoint_pairing_error": (
                floquet.max_edge_midpoint_pairing_error
            ),
            "max_face_midpoint_pairing_error": (
                floquet.max_face_midpoint_pairing_error
            ),
            "orientation_factor_stats": floquet.orientation_factor_stats,
            "dense_boundary_square_formed": (
                floquet.created_dense_boundary_square
            ),
        },
        "assembly": {
            "matrix_rows": int(condensed.matrix.getSize()[0]),
            "matrix_nnz": int(
                condensed.matrix.getInfo(
                    PETSc.Mat.InfoType.GLOBAL_SUM
                ).get("nz_used", 0.0)
            ),
            "primary_one_cell_path_full_global_matrix_allocated": False,
            "primary_one_cell_path_full_trace_matrix_allocated": False,
            "standard_static_crosscheck_transient_full_matrix_allocated": bool(
                args.standard_static_crosscheck
            ),
            "standard_static_crosscheck_transient_trace_matrix_allocated": bool(
                args.standard_static_crosscheck
            ),
            "any_full_global_matrix_allocated_for_fixture": bool(
                args.standard_static_crosscheck
            ),
            "dense_interface_square_formed": False,
        },
        "standard_static_equivalence": standard_crosscheck,
        "timing_seconds_max_rank": timings,
    }
    if args.row_audit_only:
        payload["status"] = "row_audit_complete"
        payload["timing_seconds_max_rank"]["total"] = _max_elapsed(
            comm,
            started,
        )
        _write_json(args.output, payload, comm)
        condensed.destroy()
        return

    stage = time.perf_counter()
    (
        cross_section,
        spaces,
        operators,
        positive,
        negative,
        qep_record,
    ) = _mode_basis(
        authority,
        requested_modes=args.requested_modes,
        candidate_modes=args.candidate_modes,
        comm=comm,
    )
    timings["qep_and_biorthogonal_bases"] = _max_elapsed(comm, stage)
    projection = ModalTraceProjection(
        spaces,
        positive,
        quadrature_degree=14,
    )
    (
        negative_traces,
        negative_coordinates,
        negative_representation,
    ) = _project_negative_traces(
        projection,
        negative,
        spaces,
    )
    scalar = build_two_sided_propagation(
        [*positive.modes, *negative.modes],
        10.0,
        propagation_model="full3d_uniform_cg",
        axial_fem_degree=5,
        axial_h_nm=10.0,
    )
    continuous = build_two_sided_propagation(
        [*positive.modes, *negative.modes],
        10.0,
        propagation_model="continuous_beta",
    )
    stage = time.perf_counter()
    lifter = EndpointModeLifter(
        V,
        axis_scale_nm=max(one_cell.period_x, one_cell.period_y),
    )
    right_constraint_residuals: list[float] = []
    left_constraint_residuals: list[float] = []
    right_left, right_right = lifted_endpoint_columns(
        projection.right_traces,
        lifter,
        condensed,
        rows,
        mpc=floquet.mpc,
        constraint_data=floquet_closure_data,
        constraint_residuals=right_constraint_residuals,
    )
    raw_left, raw_right = lifted_endpoint_columns(
        projection.left_traces,
        lifter,
        condensed,
        rows,
        mpc=floquet.mpc,
        constraint_data=floquet_closure_data,
        constraint_residuals=left_constraint_residuals,
    )
    inverse_gram = np.linalg.inv(projection.gram)
    petrov_left = raw_left @ inverse_gram.conj().T
    petrov_right = raw_right @ inverse_gram.conj().T

    def lift_closure_summary(
        reports: Sequence[dict[str, float]],
    ) -> dict[str, Any]:
        relative = np.asarray(
            [item["global_normwise_relative"] for item in reports],
            dtype=np.float64,
        )
        worst = int(np.argmax(relative)) if len(relative) else -1
        return {
            "max_global_normwise_relative": float(
                np.max(relative, initial=0.0)
            ),
            "worst_mode_index": worst,
            "per_mode_global_normwise_relative": relative.tolist(),
            "worst_mode_detail": (
                None if worst < 0 else reports[worst]
            ),
            "contract": (
                "direct physical 2D-mode lift compared with one exact 3D "
                "Floquet homogenize/backsubstitution recovery"
            ),
        }

    right_lift_closure = lift_closure_summary(
        right_constraint_residuals
    )
    left_lift_closure = lift_closure_summary(
        left_constraint_residuals
    )
    timings["endpoint_right_left_lifts"] = _max_elapsed(comm, stage)
    stage = time.perf_counter()
    projected = build_projected_two_port_schur(
        condensed.matrix,
        rows,
        right_left=right_left,
        right_right=right_right,
        petrov_left=petrov_left,
        petrov_right=petrov_right,
    )
    timings["second_schur_and_projection"] = _max_elapsed(comm, stage)
    scalar_metrics = bloch_residual_metrics(
        projected,
        scalar.forward.factors,
        backward_multipliers=scalar.backward.factors,
        negative_trace_coordinates=negative_coordinates,
        forward_groups=[group.indices for group in positive.groups],
        backward_groups=[group.indices for group in negative.groups],
    )
    continuous_metrics = bloch_residual_metrics(
        projected,
        continuous.forward.factors,
        backward_multipliers=continuous.backward.factors,
        negative_trace_coordinates=negative_coordinates,
        forward_groups=[group.indices for group in positive.groups],
        backward_groups=[group.indices for group in negative.groups],
    )
    round_trip = projection.round_trip(
        np.asarray(
            [
                np.exp(0.17j * index) / (1.0 + index)
                for index in range(args.requested_modes)
            ],
            dtype=np.complex128,
        )
    )
    payload.update(
        {
            "status": "one_cell_audit_complete_exact_oracle_pending",
            "qep": qep_record,
            "trace_basis": {
                "global_trace_dofs": projection.global_trace_dofs,
                "mode_count": args.requested_modes,
                "gram_condition": projection.gram_condition,
                "projection_round_trip_coefficient_error": (
                    round_trip.coefficient_relative_error
                ),
                "projection_round_trip_trace_residual": (
                    round_trip.trace_relative_residual
                ),
                "right_left_shape": list(right_left.shape),
                "right_right_shape": list(right_right.shape),
                "petrov_left_shape": list(petrov_left.shape),
                "petrov_right_shape": list(petrov_right.shape),
                "negative_trace_representation": negative_representation,
                "right_basis_floquet_orientation_closure": (
                    right_lift_closure
                ),
                "left_basis_floquet_orientation_closure": (
                    left_lift_closure
                ),
                "right_left_sha256": hashlib.sha256(
                    np.ascontiguousarray(right_left).view(np.uint8)
                ).hexdigest(),
                "right_right_sha256": hashlib.sha256(
                    np.ascontiguousarray(right_right).view(np.uint8)
                ).hexdigest(),
                "petrov_left_sha256": hashlib.sha256(
                    np.ascontiguousarray(petrov_left).view(np.uint8)
                ).hexdigest(),
                "petrov_right_sha256": hashlib.sha256(
                    np.ascontiguousarray(petrov_right).view(np.uint8)
                ).hexdigest(),
            },
            "projected_schur": {
                "block_shape": list(projected.S_LL.shape),
                "block_numerical_nnz": {
                    "S_LL": _numerical_nnz(projected.S_LL),
                    "S_LR": _numerical_nnz(projected.S_LR),
                    "S_RL": _numerical_nnz(projected.S_RL),
                    "S_RR": _numerical_nnz(projected.S_RR),
                },
                "port_rows": projected.port_rows,
                "axial_internal_rows": projected.interior_rows,
                "axial_internal_matrix_nnz": (
                    projected.interior_matrix_nnz
                ),
                "dense_interface_square_formed": False,
                "small_projected_archive": _write_small_npz(
                    work_dir / "projected_one_cell_blocks.npz",
                    {
                        "S_LL": projected.S_LL,
                        "S_LR": projected.S_LR,
                        "S_RL": projected.S_RL,
                        "S_RR": projected.S_RR,
                        "negative_trace_coordinates": negative_coordinates,
                    },
                    comm,
                    semantics=(
                        "replicated MxM Petrov blocks and negative trace "
                        "coordinate map; no full trace-space dense square"
                    ),
                ),
            },
            "scalar_cg": {
                "one_cell_forward_multipliers": _complex_vector(
                    scalar.forward.factors
                ),
                "one_cell_backward_multipliers": _complex_vector(
                    scalar.backward.factors
                ),
                "metrics": scalar_metrics,
            },
            "continuous_beta": {
                "one_cell_forward_multipliers": _complex_vector(
                    continuous.forward.factors
                ),
                "one_cell_backward_multipliers": _complex_vector(
                    continuous.backward.factors
                ),
                "metrics": continuous_metrics,
            },
        }
    )

    # The exact Full3D oracle is appended below.  Keeping it in this same
    # process reuses the live QEP basis without serializing distributed modes.
    if args.full3d_exact_oracle:
        condensed.destroy()
        condensed = None
        operators.destroy()
        operators = None
        (
            exact_oracle,
            scalar_forward_weights,
            scalar_backward_weights,
            continuous_forward_weights,
            continuous_backward_weights,
        ) = _run_exact_full3d_oracle(
            authority,
            cross_section,
            spaces,
            positive,
            negative,
            projection,
            scalar,
            continuous,
            negative_coordinates,
            sample_reference=args.sample_reference,
            run_dir=work_dir / "full3d_exact_trace",
            comm=comm,
        )
        scalar_metrics = bloch_residual_metrics(
            projected,
            scalar.forward.factors,
            backward_multipliers=scalar.backward.factors,
            negative_trace_coordinates=negative_coordinates,
            significant_weights=scalar_forward_weights,
            backward_significant_weights=scalar_backward_weights,
            forward_groups=[group.indices for group in positive.groups],
            backward_groups=[group.indices for group in negative.groups],
        )
        continuous_metrics = bloch_residual_metrics(
            projected,
            continuous.forward.factors,
            backward_multipliers=continuous.backward.factors,
            negative_trace_coordinates=negative_coordinates,
            significant_weights=continuous_forward_weights,
            backward_significant_weights=continuous_backward_weights,
            forward_groups=[group.indices for group in positive.groups],
            backward_groups=[group.indices for group in negative.groups],
        )
        payload["scalar_cg"]["metrics"] = scalar_metrics
        payload["continuous_beta"]["metrics"] = continuous_metrics
        payload["exact_full3d_oracle"] = exact_oracle
        decision = _phase_a_decision(
            standard_crosscheck=standard_crosscheck,
            trace_basis=payload["trace_basis"],
            scalar_metrics=scalar_metrics,
            exact_oracle=exact_oracle,
        )
        payload["phase_a_decision"] = decision
        if decision["phase_b_authorized"]:
            payload["status"] = "phase_a_complete_phase_b_authorized"
        elif decision["classification"].startswith("A_"):
            payload["status"] = "phase_a_complete_phase_b_forbidden"
        else:
            payload["status"] = "phase_a_incomplete_phase_b_forbidden"

    payload["timing_seconds_max_rank"].update(timings)
    payload["timing_seconds_max_rank"]["total"] = _max_elapsed(
        comm,
        started,
    )
    _write_json(args.output, payload, comm)
    projection.destroy()
    negative.destroy()
    positive.destroy()
    if operators is not None:
        operators.destroy()
    if condensed is not None:
        condensed.destroy()


if __name__ == "__main__":
    main()
