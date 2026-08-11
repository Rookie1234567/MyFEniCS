"""Research-only exact one-cell traction-column audit for Task37c X2."""

from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import resource
import subprocess
import time
from typing import Any

import numpy as np
import ufl
from basix.ufl import element
from dolfinx import default_real_type, fem, mesh
from dolfinx.fem import petsc as fem_petsc
from mpi4py import MPI
from petsc4py import PETSc

from benchmarks.task037c_robustness import make_task37c_profile
from src.common.config_3d import (
    ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND,
    SimulationConfig3D,
    target_stage4_config,
)
from src.constraints.floquet_3d import build_double_floquet_mpc
from src.coupling.hybrid_internal_modes import _ReusableModeTractionEvaluator
from src.coupling.modal_trace_projection import (
    ModalTraceProjection,
    _trace_from_full_mode_vector,
)
from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
from src.modes.cross_section_spaces import (
    build_cross_section_spaces,
    build_matching_cross_section,
)
from src.modes.mode_classification import (
    PoyntingFluxEvaluator,
    build_biorthogonal_mode_basis,
    pair_reciprocal_mode_bases,
    select_passive_direction_modes,
)
from src.modes.quadratic_beta_eigenproblem import (
    analytic_homogeneous_beta,
    assemble_quadratic_beta_operators,
    solve_quadratic_beta_modes,
)
from src.modes.stable_propagation import (
    build_two_sided_propagation,
    scalar_cg_discrete_traction_beta,
)
from src.solvers.common_3d_forms import _build_variational_forms
from src.solvers.hcurl_assembly_time_condensation import (
    build_unconstrained_assembly_time_condensation,
)
from src.solvers.one_cell_trace_schur import (
    EndpointModeLifter,
    apply_directional_endpoint_columns,
    build_one_cell_two_port_schur_action,
    identify_endpoint_active_rows,
    lifted_endpoint_columns,
)


X2_SCHEMA = "task037c.x2-exact-traction-column-audit.v1"
X2_PHI_DEG = -5.0
X2_REQUESTED_MODES = 160
X2_MPI_SIZE = 8
X2_REPEATABILITY_BOUND = 1.2524e-8
X2_BETA_H_CUTOFF = 1.0e4


def _split_normalize_four_blocks(
    forward_flux: np.ndarray,
    backward_flux: np.ndarray,
    *,
    left_rows: int,
    right_rows: int,
    forward_factors: np.ndarray,
    backward_factors: np.ndarray,
) -> dict[str, np.ndarray]:
    """Split full endpoint flux columns into local-amplitude four blocks."""

    forward = np.asarray(forward_flux, dtype=np.complex128)
    backward = np.asarray(backward_flux, dtype=np.complex128)
    expected_rows = int(left_rows) + int(right_rows)
    if (
        forward.ndim != 2
        or backward.ndim != 2
        or forward.shape != backward.shape
        or forward.shape[0] != expected_rows
    ):
        raise ValueError("Forward/backward flux columns have incompatible shapes.")
    lam = np.asarray(forward_factors, dtype=np.complex128)
    mu = np.asarray(backward_factors, dtype=np.complex128)
    if (
        lam.ndim != 1
        or mu.ndim != 1
        or lam.shape != (forward.shape[1],)
        or mu.shape != lam.shape
    ):
        raise ValueError("Propagation factors must have one entry per column.")
    if (
        not np.all(np.isfinite(lam))
        or not np.all(np.isfinite(mu))
        or np.any(np.abs(lam) <= 1.0e-14)
        or np.any(np.abs(mu) <= 1.0e-14)
    ):
        raise ValueError("Propagation factors must be finite and nonzero.")
    left = int(left_rows)
    return {
        "bottom_forward": forward[:left].copy(),
        "top_forward": (forward[left:] / lam[None, :]).copy(),
        "bottom_backward": (backward[:left] / mu[None, :]).copy(),
        "top_backward": backward[left:].copy(),
    }


def _relative_metrics(reference: np.ndarray, candidate: np.ndarray) -> dict[str, Any]:
    """Return rectangular relative Frobenius and per-column diagnostics."""

    left = np.asarray(reference, dtype=np.complex128)
    right = np.asarray(candidate, dtype=np.complex128)
    if left.ndim != 2 or right.shape != left.shape:
        raise ValueError("Relative metrics require equal rectangular matrices.")
    if not np.all(np.isfinite(left)) or not np.all(np.isfinite(right)):
        raise ValueError("Relative metrics require finite matrices.")
    difference = left - right
    scale = max(float(np.linalg.norm(left)), float(np.linalg.norm(right)), 1.0e-30)
    column_scales = np.maximum(
        np.maximum(np.linalg.norm(left, axis=0), np.linalg.norm(right, axis=0)),
        1.0e-30,
    )
    column_relative = np.linalg.norm(difference, axis=0) / column_scales
    return {
        "relative_frobenius": float(np.linalg.norm(difference) / scale),
        "per_column_relative_min": float(np.min(column_relative)),
        "per_column_relative_median": float(np.median(column_relative)),
        "per_column_relative_p90": float(np.percentile(column_relative, 90.0)),
        "per_column_relative_max": float(np.max(column_relative)),
        "per_column_relative": [float(value) for value in column_relative],
        "max_absolute": float(np.max(np.abs(difference))),
        "norm_scale": float(scale),
    }


def _array_descriptor(name: str, values: np.ndarray) -> dict[str, Any]:
    """Describe an ignored rectangular complex array without serializing values."""

    array = np.ascontiguousarray(np.asarray(values))
    return {
        "name": str(name),
        "shape": [int(value) for value in array.shape],
        "dtype": str(array.dtype),
        "bytes": int(array.nbytes),
        "sha256": hashlib.sha256(array.view(np.uint8)).hexdigest(),
        "finite": bool(np.all(np.isfinite(array))),
    }


def _build_modal_basis(profile, comm: MPI.Intracomm, log=None):
    """Build the reviewed forward/backward QEP bases, without local endcaps."""

    cfg = target_stage4_config(
        degree=profile.modal_degree,
        h_nm=profile.modal_h_nm,
    )
    cfg = replace(
        cfg,
        incident_theta_deg=89.0,
        incident_phi_deg=float(profile.incident_phi_deg),
        polarization_kind=profile.polarization_kind,
        stage4_full3d_assembly_backend=ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND,
    )
    cross_section = build_matching_cross_section(cfg, "stage4_xy", comm=comm)
    spaces = build_cross_section_spaces(
        cross_section,
        transverse_degree=profile.modal_degree,
    )
    operators = assemble_quadratic_beta_operators(
        cfg,
        cross_section,
        spaces,
        log=log,
    )
    poynting = PoyntingFluxEvaluator(cfg, cross_section, spaces)
    target = analytic_homogeneous_beta(cfg, cfg.n_air)
    try:
        positive_right, positive_selection = solve_quadratic_beta_modes(
            operators,
            target=target,
            requested_modes=profile.candidate_modes,
        )
        positive_right, positive_selection = select_passive_direction_modes(
            positive_right,
            desired_direction="forward",
            requested_modes=profile.requested_modes,
            poynting_evaluator=poynting,
            maximum_abs_beta=X2_BETA_H_CUTOFF / profile.modal_h_nm,
        )
        if len(positive_right) != profile.requested_modes:
            raise RuntimeError(
                "X2 forward QEP selection did not deliver the requested mode count."
            )
        positive = build_biorthogonal_mode_basis(
            cfg,
            cross_section,
            spaces,
            operators,
            positive_right,
            adjoint_target=np.conj(target),
            requested_left_modes=profile.candidate_modes,
            near_degenerate_tolerance=profile.near_degenerate_tolerance,
            block_rotation_tolerance=profile.block_rotation_tolerance,
            poynting_evaluator=poynting,
            log=log,
        )
        negative_right, negative_selection = solve_quadratic_beta_modes(
            operators,
            target=-target,
            requested_modes=profile.candidate_modes,
        )
        negative_right, negative_selection = select_passive_direction_modes(
            negative_right,
            desired_direction="backward",
            requested_modes=profile.requested_modes,
            poynting_evaluator=poynting,
            maximum_abs_beta=X2_BETA_H_CUTOFF / profile.modal_h_nm,
        )
        if len(negative_right) != profile.requested_modes:
            raise RuntimeError(
                "X2 backward QEP selection did not deliver the requested mode count."
            )
        negative = build_biorthogonal_mode_basis(
            cfg,
            cross_section,
            spaces,
            operators,
            negative_right,
            adjoint_target=-np.conj(target),
            requested_left_modes=profile.candidate_modes,
            near_degenerate_tolerance=profile.near_degenerate_tolerance,
            block_rotation_tolerance=profile.block_rotation_tolerance,
            poynting_evaluator=poynting,
            log=log,
        )
        reciprocal = pair_reciprocal_mode_bases(operators, positive, negative)
        if len(reciprocal) != profile.requested_modes:
            raise RuntimeError("X2 reciprocal QEP pairing is incomplete.")
    finally:
        operators.destroy()
    return (
        cfg,
        cross_section,
        spaces,
        positive,
        negative,
        positive_selection,
        negative_selection,
    )


def _one_cell_config(cfg: SimulationConfig3D) -> SimulationConfig3D:
    """Restrict the Task37c target config to its fixed 10 nm middle cell."""

    return replace(
        cfg,
        case_name="task037c_x2_exact_traction_one_cell",
        z_min=0.0,
        z_max=10.0,
        air_height=10.0,
        substrate_thickness=0.0,
        interface_z=0.0,
        grating_height=10.0,
        mesh_axis_cell_counts=(6, 3, 1),
        mesh_axis_z_values=(0.0, 10.0),
        mesh_cell_type="hexahedron",
        mesh_spacing_mode="boundary_fitted",
        stage4_full3d_assembly_backend=ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND,
    )


def _assemble_scalar_modal_dual(
    modes,
    spaces,
    left_traces,
    comm: MPI.Intracomm,
    *,
    sign: int,
    beta_eff: np.ndarray,
) -> np.ndarray:
    """Assemble weak scalar-CG traction pairings against positive left traces."""

    if sign not in {-1, 1}:
        raise ValueError("Scalar traction sign must be -1 or +1.")
    effective = np.asarray(beta_eff, dtype=np.complex128)
    if effective.shape != (len(modes),):
        raise ValueError("Scalar effective beta shape does not match mode count.")
    evaluator = _ReusableModeTractionEvaluator(spaces)
    test = ufl.TestFunction(spaces.transverse)
    form = fem.form(ufl.inner(evaluator.traction, test) * ufl.dx)
    ownership = left_traces[0].x.petsc_vec.getOwnershipRange()
    left_owned = np.column_stack(
        [
            np.asarray(
                trace.x.petsc_vec.getArray(readonly=True), dtype=np.complex128
            ).copy()
            for trace in left_traces
        ]
    )
    if any(trace.x.petsc_vec.getOwnershipRange() != ownership for trace in left_traces):
        raise ValueError("Scalar trace vectors do not share an ownership range.")
    result = np.empty((len(left_traces), len(modes)), dtype=np.complex128)
    for column, (mode, beta) in enumerate(zip(modes, effective, strict=True)):
        evaluator.evaluate(
            mode,
            local_outward_normal_sign=sign,
            beta_override=complex(beta),
        )
        vector = fem_petsc.assemble_vector(form)
        try:
            vector.ghostUpdate(
                addv=PETSc.InsertMode.ADD_VALUES,
                mode=PETSc.ScatterMode.REVERSE,
            )
            vector.ghostUpdate(
                addv=PETSc.InsertMode.INSERT_VALUES,
                mode=PETSc.ScatterMode.FORWARD,
            )
            owned = np.asarray(vector.getArray(readonly=True), dtype=np.complex128)
            local = left_owned.conj().T @ owned
            result[:, column] = comm.allreduce(local, op=MPI.SUM)
        finally:
            vector.destroy()
    return result


def _project_exact_modal_dual(
    petrov: np.ndarray,
    flux: np.ndarray,
) -> np.ndarray:
    """Project active-row Schur flux columns onto a Petrov trace basis."""

    left = np.asarray(petrov, dtype=np.complex128)
    values = np.asarray(flux, dtype=np.complex128)
    if left.ndim != 2 or values.ndim != 2 or left.shape[0] != values.shape[0]:
        raise ValueError("Petrov and exact flux rows must agree.")
    if not np.all(np.isfinite(left)) or not np.all(np.isfinite(values)):
        raise ValueError("Petrov projection requires finite arrays.")
    return left.conj().T @ values


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--task037c-x2-exact-traction-audit",
        action="store_true",
        required=True,
    )
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verified-clean-sha", required=True)
    return parser.parse_args(argv)


def _json_value(value: Any) -> Any:
    if isinstance(value, complex):
        return {"real": float(value.real), "imag": float(value.imag)}
    if isinstance(value, np.ndarray):
        return [_json_value(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        return _json_value(value.item())
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _complex_record(value: complex) -> dict[str, float]:
    number = complex(value)
    return {"real": float(number.real), "imag": float(number.imag)}


def _source_identity(comm: MPI.Intracomm, expected_sha: str) -> dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[1]
    if comm.rank == 0:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        identity = {
            "head": head,
            "verified_clean_sha": expected_sha,
            "worktree_clean": not bool(dirty),
            "pass": head == expected_sha and not dirty,
        }
    else:
        identity = None
    identity = comm.bcast(identity, root=0)
    if identity["pass"] is not True:
        raise RuntimeError(f"X2 source identity failed: {identity!r}")
    return identity


def _top_columns(
    metrics: dict[str, Any],
    *,
    beta: np.ndarray,
    scalar_traction_beta: np.ndarray,
    propagation_effective_beta: np.ndarray,
    factors: np.ndarray,
) -> list[dict[str, Any]]:
    values = np.asarray(metrics["per_column_relative"], dtype=np.float64)
    order = np.argsort(values)[::-1][:10]
    return [
        {
            "mode_index": int(index),
            "beta": _complex_record(beta[index]),
            "scalar_traction_beta": _complex_record(scalar_traction_beta[index]),
            "propagation_effective_beta": _complex_record(
                propagation_effective_beta[index]
            ),
            "factor": _complex_record(factors[index]),
            "relative_difference": float(values[index]),
        }
        for index in order
    ]


def main(argv: list[str] | None = None) -> int:
    """Run the fixed X2 one-cell exact-versus-scalar traction audit."""

    args = _parse_args(argv)
    comm = MPI.COMM_WORLD
    if comm.size != X2_MPI_SIZE:
        raise RuntimeError(f"X2 requires MPI size {X2_MPI_SIZE}, got {comm.size}.")
    source = _source_identity(comm, args.verified_clean_sha)
    run_dir = args.run_dir.resolve()
    output = args.output.resolve()
    if comm.rank == 0:
        run_dir.mkdir(parents=True, exist_ok=True)
        output.parent.mkdir(parents=True, exist_ok=True)
    comm.Barrier()

    profile = make_task37c_profile(X2_PHI_DEG, X2_REQUESTED_MODES, X2_MPI_SIZE)
    if profile.mpi_size != X2_MPI_SIZE:
        raise RuntimeError("The X2 profile must be frozen to MPI8.")
    phase_times: dict[str, float] = {}
    started = time.perf_counter()
    (
        cfg,
        _cross_section,
        spaces,
        positive,
        negative,
        positive_selection,
        negative_selection,
    ) = _build_modal_basis(profile, comm, log=(print if comm.rank == 0 else None))
    phase_times["qep_and_basis"] = comm.allreduce(
        time.perf_counter() - started, op=MPI.MAX
    )
    positive_projection = ModalTraceProjection(spaces, positive)
    mode_count = int(profile.requested_modes)
    positive_inverse_gram = np.linalg.solve(
        positive_projection.gram, np.eye(mode_count, dtype=np.complex128)
    )

    one_cfg = _one_cell_config(cfg)
    condensed = None
    action = None
    try:
        started = time.perf_counter()
        mesh_data = build_airbox_mesh_3d(one_cfg, run_dir / "mesh")
        V = fem.functionspace(
            mesh_data.mesh,
            element(
                "N1curl",
                mesh_data.mesh.basix_cell(),
                one_cfg.nedelec_trace_degree_resolved,
                dtype=default_real_type,
            ),
        )
        variational, _ = _build_variational_forms(mesh_data.mesh, mesh_data, one_cfg, V)
        compiled = fem.form(variational)
        floquet = build_double_floquet_mpc(V, mesh_data, one_cfg)
        condensed = build_unconstrained_assembly_time_condensation(
            compiled,
            V,
            mesh_data.cell_tags,
            mpc=floquet.mpc,
            materialize_global_matrix=True,
        )
        if condensed.matrix is None:
            raise RuntimeError("X2 requires a materialized sparse condensed matrix.")
        phase_times["one_cell_assembly"] = comm.allreduce(
            time.perf_counter() - started, op=MPI.MAX
        )
        started = time.perf_counter()

        tdim = mesh_data.mesh.topology.dim
        bottom_facets = mesh.locate_entities_boundary(
            mesh_data.mesh,
            tdim - 1,
            lambda x: np.isclose(x[2], one_cfg.domain_z_min),
        )
        top_facets = mesh.locate_entities_boundary(
            mesh_data.mesh,
            tdim - 1,
            lambda x: np.isclose(x[2], one_cfg.domain_z_max),
        )
        rows = identify_endpoint_active_rows(
            V,
            condensed,
            left_facets=bottom_facets,
            right_facets=top_facets,
        )
        action = build_one_cell_two_port_schur_action(condensed.matrix, rows)
        lifter = EndpointModeLifter(V, max(one_cfg.period_x, one_cfg.period_y))
        right_sources = tuple(positive_projection.right_traces)
        negative_right_sources = tuple(
            _trace_from_full_mode_vector(
                mode.right.right_full,
                spaces,
                name=f"task037c_negative_right_trace_{index}",
            )
            for index, mode in enumerate(negative.modes)
        )
        left_sources = tuple(positive_projection.left_traces)
        all_sources = (
            *right_sources,
            *negative_right_sources,
            *left_sources,
        )
        lifted_left, lifted_right = lifted_endpoint_columns(
            all_sources,
            lifter,
            condensed,
            rows,
            mpc=floquet.mpc,
        )
        pos_e_left = lifted_left[:, :mode_count]
        pos_e_right = lifted_right[:, :mode_count]
        neg_e_left = lifted_left[:, mode_count : 2 * mode_count]
        neg_e_right = lifted_right[:, mode_count : 2 * mode_count]
        raw_petrov_left = lifted_left[:, 2 * mode_count :]
        raw_petrov_right = lifted_right[:, 2 * mode_count :]
        inverse_left = positive_inverse_gram.conj().T
        petrov_left = raw_petrov_left @ inverse_left
        petrov_right = raw_petrov_right @ inverse_left
        condensed.destroy()
        condensed = None

        propagation = build_two_sided_propagation(
            [*positive.modes, *negative.modes],
            10.0,
            propagation_model="full3d_uniform_cg",
            axial_fem_degree=one_cfg.nedelec_degree,
            axial_h_nm=10.0,
        )
        lam = np.asarray(propagation.forward.factors, dtype=np.complex128)
        mu = np.asarray(propagation.backward.factors, dtype=np.complex128)
        positive_beta = np.asarray(propagation.forward.beta_per_nm, dtype=np.complex128)
        positive_effective = np.asarray(
            propagation.forward.effective_beta_per_nm, dtype=np.complex128
        )
        negative_beta = np.asarray(
            propagation.backward.beta_per_nm, dtype=np.complex128
        )
        negative_effective = np.asarray(
            propagation.backward.effective_beta_per_nm, dtype=np.complex128
        )
        positive_traction = np.asarray(
            [
                scalar_cg_discrete_traction_beta(
                    mode.beta,
                    degree=one_cfg.nedelec_degree,
                    h_nm=10.0,
                    direction="forward",
                )
                for mode in positive.modes
            ],
            dtype=np.complex128,
        )
        negative_traction = np.asarray(
            [
                scalar_cg_discrete_traction_beta(
                    mode.beta,
                    degree=one_cfg.nedelec_degree,
                    h_nm=10.0,
                    direction="backward",
                )
                for mode in negative.modes
            ],
            dtype=np.complex128,
        )
        if any(array.shape != (mode_count,) for array in (lam, mu)):
            raise RuntimeError("X2 propagation did not produce one factor per mode.")

        exact_forward = apply_directional_endpoint_columns(
            action,
            pos_e_left,
            pos_e_right,
            multipliers=lam,
        )
        exact_backward = action.apply_columns(
            np.vstack((neg_e_left * mu[None, :], neg_e_right))
        )
        exact_blocks = _split_normalize_four_blocks(
            exact_forward,
            exact_backward,
            left_rows=len(rows.left_active),
            right_rows=len(rows.right_active),
            forward_factors=lam,
            backward_factors=mu,
        )

        scalar_raw = {
            "bottom_forward": _assemble_scalar_modal_dual(
                positive.modes,
                spaces,
                positive_projection.left_traces,
                comm,
                sign=-1,
                beta_eff=positive_traction,
            ),
            "top_forward": _assemble_scalar_modal_dual(
                positive.modes,
                spaces,
                positive_projection.left_traces,
                comm,
                sign=1,
                beta_eff=positive_traction,
            ),
            "bottom_backward": _assemble_scalar_modal_dual(
                negative.modes,
                spaces,
                positive_projection.left_traces,
                comm,
                sign=-1,
                beta_eff=negative_traction,
            ),
            "top_backward": _assemble_scalar_modal_dual(
                negative.modes,
                spaces,
                positive_projection.left_traces,
                comm,
                sign=1,
                beta_eff=negative_traction,
            ),
        }
        scalar_blocks = {
            "bottom_forward": positive_inverse_gram @ scalar_raw["bottom_forward"],
            "top_forward": positive_inverse_gram @ scalar_raw["top_forward"],
            "bottom_backward": positive_inverse_gram @ scalar_raw["bottom_backward"],
            "top_backward": positive_inverse_gram @ scalar_raw["top_backward"],
        }
        exact_dual = {
            "bottom_forward": _project_exact_modal_dual(
                petrov_left, exact_blocks["bottom_forward"]
            ),
            "top_forward": _project_exact_modal_dual(
                petrov_right, exact_blocks["top_forward"]
            ),
            "bottom_backward": _project_exact_modal_dual(
                petrov_left, exact_blocks["bottom_backward"]
            ),
            "top_backward": _project_exact_modal_dual(
                petrov_right, exact_blocks["top_backward"]
            ),
        }
        factors = {
            "bottom_forward": lam,
            "top_forward": lam,
            "bottom_backward": mu,
            "top_backward": mu,
        }
        betas = {
            "bottom_forward": positive_beta,
            "top_forward": positive_beta,
            "bottom_backward": negative_beta,
            "top_backward": negative_beta,
        }
        propagation_effective_betas = {
            "bottom_forward": positive_effective,
            "top_forward": positive_effective,
            "bottom_backward": negative_effective,
            "top_backward": negative_effective,
        }
        scalar_traction_betas = {
            "bottom_forward": positive_traction,
            "top_forward": positive_traction,
            "bottom_backward": negative_traction,
            "top_backward": negative_traction,
        }
        metrics = {}
        for name in exact_blocks:
            block_metrics = _relative_metrics(exact_dual[name], scalar_blocks[name])
            block_metrics["repeatability_bound_ratio"] = float(
                block_metrics["per_column_relative_max"] / X2_REPEATABILITY_BOUND
            )
            block_metrics["largest_columns"] = _top_columns(
                block_metrics,
                beta=betas[name],
                scalar_traction_beta=scalar_traction_betas[name],
                propagation_effective_beta=propagation_effective_betas[name],
                factors=factors[name],
            )
            metrics[name] = block_metrics

        def consistency(left: np.ndarray, right: np.ndarray) -> dict[str, Any]:
            if left.shape != right.shape:
                raise RuntimeError("X2 modal dual coordinates are incompatible.")
            scale = max(
                float(np.linalg.norm(left)), float(np.linalg.norm(right)), 1.0e-30
            )
            return {
                "relative_norm_of_outward_sum": float(
                    np.linalg.norm(left + right) / scale
                ),
                "finite": bool(
                    np.all(np.isfinite(left)) and np.all(np.isfinite(right))
                ),
            }

        consistency_records = {
            "forward": consistency(
                exact_dual["bottom_forward"], exact_dual["top_forward"]
            ),
            "backward": consistency(
                exact_dual["bottom_backward"], exact_dual["top_backward"]
            ),
        }
        arrays = {
            **{f"exact_{key}": value for key, value in exact_blocks.items()},
            **{f"exact_modal_{key}": value for key, value in exact_dual.items()},
            **{f"scalar_modal_{key}": value for key, value in scalar_blocks.items()},
            "positive_beta": positive_beta,
            "positive_effective_beta": positive_effective,
            "positive_scalar_traction_beta": positive_traction,
            "positive_factor": lam,
            "negative_beta": negative_beta,
            "negative_effective_beta": negative_effective,
            "negative_scalar_traction_beta": negative_traction,
            "negative_factor": mu,
            "left_active_rows": np.asarray(rows.left_active, dtype=PETSc.IntType),
            "right_active_rows": np.asarray(rows.right_active, dtype=PETSc.IntType),
            "interior_active_rows": np.asarray(
                rows.interior_active, dtype=PETSc.IntType
            ),
        }
        phase_times["action_and_scalar_dual"] = comm.allreduce(
            time.perf_counter() - started, op=MPI.MAX
        )
        rss_max_rank = int(
            comm.allreduce(
                resource.getrusage(resource.RUSAGE_SELF).ru_maxrss, op=MPI.MAX
            )
        )
        if comm.rank == 0:
            npz_path = run_dir / "x2_exact_traction_columns.npz"
            np.savez_compressed(npz_path, **arrays)
            npz_sha = hashlib.sha256(npz_path.read_bytes()).hexdigest()
            record = {
                "schema": X2_SCHEMA,
                "status": "measured_diagnostic_no_threshold",
                "profile": _json_value(asdict(profile)),
                "source": source,
                "rows": rows.to_record(),
                "mode_selection": {
                    "forward": _json_value(asdict(positive_selection)),
                    "backward": _json_value(asdict(negative_selection)),
                    "requested_modes": mode_count,
                },
                "action": {
                    "port_row_accounting_pass": bool(
                        action.port_rows == len(rows.port_active)
                        and action.port_rows == exact_forward.shape[0]
                    ),
                    "materialized_sparse_matrix": True,
                    "dense_endpoint_square_formed": bool(
                        action.dense_interface_square_formed
                    ),
                    "port_rows": int(action.port_rows),
                    "interior_rows": int(action.interior_rows),
                    "interior_matrix_nnz": int(action.interior_matrix_nnz),
                },
                "metrics": metrics,
                "outward_consistency": consistency_records,
                "arrays": {
                    name: _array_descriptor(name, value)
                    for name, value in arrays.items()
                },
                "npz": {
                    "path": str(npz_path),
                    "sha256": npz_sha,
                    "bytes": npz_path.stat().st_size,
                },
                "phase_elapsed_seconds": _json_value(phase_times),
                "resource": {
                    "scope": "historical_max_single_rank_ru_maxrss",
                    "unit": "KiB",
                    "ru_maxrss_kib_max_rank": rss_max_rank,
                },
            }
            output.write_text(
                json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
        comm.Barrier()
    finally:
        if action is not None:
            action.destroy()
        if condensed is not None:
            condensed.destroy()
        positive_projection.destroy()
        negative.destroy()
        positive.destroy()
    return 0


if __name__ == "__main__":
    main()
