"""Research-only Task037 V6-E1 M120 modal-basis component gate.

This module rebuilds the frozen 240-candidate QEP basis, constructs 120
forward and 120 backward owner-local Full3D active columns, extends the two
endcaps, stitches canonical packets, repeats the columns, releases local
factors, and audits the fine matrix-free action. It never starts a KSP solve
or produces an official scattering result.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from dolfinx import fem
import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from ..common.config_3d import target_stage4_config
from ..coupling.hybrid_internal_modes import (
    _DistributedTwoDimensionalEvaluator,
    build_hybrid_internal_mode_coupling,
)
from ..modes.cross_section_spaces import (
    build_cross_section_spaces,
    build_matching_cross_section,
)
from ..modes.mode_classification import (
    PoyntingFluxEvaluator,
    build_biorthogonal_mode_basis,
    pair_reciprocal_mode_bases,
    select_passive_direction_modes,
)
from ..modes.quadratic_beta_eigenproblem import (
    analytic_homogeneous_beta,
    assemble_quadratic_beta_operators,
    solve_quadratic_beta_modes,
)
from .hcurl_canonical_vector_dolfinx import (
    extract_canonical_active_trace_packets,
    reconstruct_canonical_active_trace_vector,
)
from .condensed_dtn import create_matrix_free_condensed_operator
from ..geometry.tetra_mesh_audit import mesh_coordinate_tolerance
from .hybrid_local_dtn import assemble_hybrid_local_dtn_system
from .hybrid_strong_trace_direct import build_hybrid_strong_trace_interface_map
from .static_modal_coarse_basis import (
    ActionSpaceAudit,
    HomogeneousEndcapExtender,
    OwnerLocalBasis,
    audit_owner_local_action_space,
    build_middle_modal_active_column,
    normalize_owner_local_columns,
    stitch_canonical_active_trace_packets,
)

E1_AUXILIARY_MODE_COUNT = 80
E1_CANDIDATE_MODE_COUNT = 240
E1_SELECTED_MODE_COUNT = 120
E1_TOTAL_COLUMN_COUNT = 240
E1_MIN_ACTION_RANK = 180
E1_REPEAT_TOLERANCE = 1.0e-12
E1_ACTION_TOLERANCE = 1.0e-11
E1_EXPECTED_ACTIVE_ROWS = 51192
E1_MAX_ABS_BETA_PER_NM = 1.0e3
E1_NEAR_DEGENERATE_TOLERANCE = 1.0e-6
E1_BOTTOM_INTERFACE_NM = 10.0
E1_TOP_INTERFACE_NM = 110.0
E1_PROPAGATION_MODEL = "full3d_uniform_cg"
E1_TRACTION_MODEL = "scalar_cg_discrete_derivative"


class _E2LiveCallbackError(RuntimeError):
    """Keep an E2 callback failure separate from the completed E1 audit."""


@dataclass
class _E1Resources:
    """Owned modal and endcap objects with one explicit release order."""

    cross_section: Any = None
    spaces: Any = None
    operators: Any = None
    positive: Any = None
    negative: Any = None
    bottom: Any = None
    top: Any = None
    coupling: Any = None
    bottom_map: Any = None
    top_map: Any = None
    bottom_extender: Any = None
    top_extender: Any = None

    def release_endcap_stage(self) -> dict[str, Any]:
        """Release local factors before the owner-local action stage."""

        for name in ("bottom_extender", "top_extender"):
            value = getattr(self, name)
            if value is not None:
                value.destroy()
                setattr(self, name, None)
        for name in ("bottom_map", "top_map"):
            value = getattr(self, name)
            if value is not None:
                value.destroy()
                setattr(self, name, None)
        if self.coupling is not None:
            self.coupling.destroy()
            self.coupling = None
        for name in ("bottom", "top"):
            value = getattr(self, name)
            if value is not None:
                value.destroy()
                setattr(self, name, None)
        if self.positive is not None:
            self.positive.destroy()
            self.positive = None
        if self.negative is not None:
            self.negative.destroy()
            self.negative = None
        if self.operators is not None:
            self.operators.destroy()
            self.operators = None
        return {
            "factor_released": True,
            "interface_maps_released": True,
            "coupling_released": True,
            "local_systems_released": True,
            "modal_bases_released": True,
            "qep_operators_released": True,
        }

    def release_all(self) -> None:
        """Idempotent cleanup for partial construction and normal completion."""

        self.release_endcap_stage()


def _require_research_opt_in(research_opt_in: bool) -> None:
    if research_opt_in is not True:
        raise ValueError(
            "Task037 E1 modal-basis gate is research-only; "
            "pass research_opt_in=True explicitly."
        )


def _comm_from_basis(basis: OwnerLocalBasis) -> MPI.Comm:
    return basis.columns[0].getComm().tompi4py()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _audit_to_dict(audit: ActionSpaceAudit) -> dict[str, Any]:
    return {
        "global_rows": int(audit.global_rows),
        "column_count": int(audit.column_count),
        "effective_rank": int(audit.effective_rank),
        "retained_condition_number": float(audit.retained_condition_number),
        "singular_values": [float(value) for value in audit.singular_values],
        "rank_tolerance": float(audit.rank_tolerance),
        "local_qr_method": audit.local_qr_method,
        "stacked_r_svd_method": audit.stacked_r_svd_method,
        "stacked_r_shape": [int(value) for value in audit.stacked_r_shape],
        "normal_equations_used": bool(audit.normal_equations_used),
    }


def audit_owner_local_basis(
    basis: OwnerLocalBasis,
    *,
    research_opt_in: bool = False,
) -> dict[str, Any]:
    """Run the existing rank-revealing owner-local action audit."""

    _require_research_opt_in(research_opt_in)
    return _audit_to_dict(
        audit_owner_local_action_space(
            basis,
            rank_tolerance=1.0e-12,
            research_opt_in=True,
        )
    )


def _call_e2_live_callback(
    callback: Callable[[OwnerLocalBasis, OwnerLocalBasis, PETSc.Mat], None] | None,
    z_basis: OwnerLocalBasis,
    y_basis: OwnerLocalBasis,
    a6_operator: PETSc.Mat,
) -> None:
    """Pass borrowed E2 live objects once without transferring ownership."""

    if callback is not None:
        callback(z_basis, y_basis, a6_operator)


def save_owner_local_basis_shard(
    basis: OwnerLocalBasis,
    directory: str | Path,
    *,
    source_sha: str,
    prefix: str,
    research_opt_in: bool = False,
) -> dict[str, Any]:
    """Write one rank's owner-local columns and a root hash manifest.

    Each rank writes only its own local rows. The returned manifest is
    identical on every rank and contains no replicated basis values.
    """

    _require_research_opt_in(research_opt_in)
    if not isinstance(source_sha, str) or len(source_sha) != 40:
        raise ValueError("source_sha must be a 40-character commit SHA")
    directory = Path(directory)
    comm = _comm_from_basis(basis)
    rank = comm.Get_rank()
    directory.mkdir(parents=True, exist_ok=True)
    first, last = map(int, basis.ownership_range)
    path = directory / f"{prefix}.rank{rank:04d}.npz"
    np.savez(
        path,
        local_values=np.asarray(basis.local_matrix(), dtype=np.complex128),
        global_rows=np.asarray([basis.global_rows], dtype=np.int64),
        ownership=np.asarray([first, last], dtype=np.int64),
        column_count=np.asarray([basis.column_count], dtype=np.int64),
        source_sha=np.asarray([source_sha]),
        label=np.asarray([basis.label]),
    )
    local_entry = {
        "rank": rank,
        "path": path.as_posix(),
        "sha256": _sha256_file(path),
        "bytes": path.stat().st_size,
        "global_rows": int(basis.global_rows),
        "ownership": [first, last],
        "column_count": int(basis.column_count),
        "label": basis.label,
    }
    entries = comm.allgather(local_entry)
    manifest = {
        "schema_version": "task037.e1.owner-local-basis-shards.v1",
        "source_sha": source_sha,
        "prefix": prefix,
        "global_rows": int(basis.global_rows),
        "column_count": int(basis.column_count),
        "owner_local": True,
        "replicated_global_basis": False,
        "shards": sorted(entries, key=lambda entry: int(entry["rank"])),
    }
    manifest_path = directory / f"{prefix}.manifest.json"
    if rank == 0:
        _write_json(manifest_path, manifest)
    comm.barrier()
    return manifest


def load_owner_local_basis_shard(
    path: str | Path,
    *,
    expected_sha256: str | None = None,
) -> dict[str, Any]:
    """Load and validate one previously written owner-local shard."""

    path = Path(path)
    actual_sha = _sha256_file(path)
    if expected_sha256 is not None and actual_sha != expected_sha256:
        raise ValueError("owner-local shard SHA256 does not match its manifest")
    with np.load(path, allow_pickle=False) as data:
        local_values = np.asarray(data["local_values"], dtype=np.complex128)
        global_rows = int(np.asarray(data["global_rows"]).ravel()[0])
        ownership = tuple(int(value) for value in np.asarray(data["ownership"]).ravel())
        column_count = int(np.asarray(data["column_count"]).ravel()[0])
        source_sha = str(np.asarray(data["source_sha"]).ravel()[0])
        label = str(np.asarray(data["label"]).ravel()[0])
    if local_values.ndim != 2 or local_values.shape[1] != column_count:
        raise ValueError("owner-local shard column metadata is inconsistent")
    if len(ownership) != 2 or ownership[1] - ownership[0] != local_values.shape[0]:
        raise ValueError("owner-local shard ownership metadata is inconsistent")
    if not np.all(np.isfinite(local_values)):
        raise ValueError("owner-local shard contains non-finite values")
    return {
        "path": path.as_posix(),
        "sha256": actual_sha,
        "bytes": path.stat().st_size,
        "local_values": local_values,
        "global_rows": global_rows,
        "ownership": ownership,
        "column_count": column_count,
        "source_sha": source_sha,
        "label": label,
    }


def _json_complex(value: complex) -> list[float]:
    value = complex(value)
    return [float(value.real), float(value.imag)]


def _complex_hash(values: Any) -> str:
    array = np.asarray(values, dtype=np.dtype("<c16"))
    return hashlib.sha256(array.tobytes(order="C")).hexdigest()


def _relative_vector_error(observed: PETSc.Vec, expected: PETSc.Vec) -> float:
    difference = observed.duplicate()
    try:
        expected.copy(difference)
        difference.axpy(PETSc.ScalarType(-1.0), observed)
        return float(
            difference.norm(PETSc.NormType.NORM_2)
            / max(
                expected.norm(PETSc.NormType.NORM_2),
                np.finfo(float).tiny,
            )
        )
    finally:
        difference.destroy()


def _complete_single_column_packets(
    local_packets: tuple[Any, ...],
    comm: MPI.Comm,
) -> tuple[Any, ...]:
    packets = comm.allgather(local_packets)
    return tuple(packet for rank_packets in packets for packet in rank_packets)


def _diagnose_interface_packets(
    middle_packets: tuple[Any, ...],
    local_packets: tuple[Any, ...],
    *,
    interface_keys: set[Any],
    label: str,
    propagation_factor: complex | None = None,
    effective_beta: complex | None = None,
    propagation_length_nm: float = 100.0,
    log_magnitude: float | None = None,
    roundoff_growth_clipped: bool | None = None,
) -> dict[str, Any]:
    """Report one complete-column interface mismatch before the hard Gate."""

    middle_map = {key: complex(value) for key, value in middle_packets}
    local_map = {key: complex(value) for key, value in local_packets}
    expected = set(interface_keys)
    missing = expected - set(local_map)
    common = tuple(sorted(expected & set(local_map) & set(middle_map), key=repr))
    if not common:
        raise ValueError(f"{label} diagnostic has no common interface packet keys")
    middle_values = np.asarray([middle_map[key] for key in common], dtype=np.complex128)
    local_values = np.asarray([local_map[key] for key in common], dtype=np.complex128)
    difference = local_values - middle_values
    middle_norm = float(np.linalg.norm(middle_values))
    local_norm = float(np.linalg.norm(local_values))
    absolute_difference = float(np.linalg.norm(difference))
    scale = max(local_norm, middle_norm, np.finfo(float).tiny)
    relative_difference = float(absolute_difference / scale)
    middle_inner = np.vdot(middle_values, middle_values)
    scalar = (
        complex(np.vdot(middle_values, local_values) / middle_inner)
        if abs(middle_inner) > np.finfo(float).tiny
        else None
    )
    scalar_residual = (
        float(np.linalg.norm(local_values - scalar * middle_values) / scale)
        if scalar is not None
        else None
    )

    def subgroup(indices: list[int]) -> dict[str, Any]:
        if not indices:
            return {
                "count": 0,
                "absolute_l2_difference": 0.0,
                "relative_l2_difference": 0.0,
            }
        selected = np.asarray(indices, dtype=np.int64)
        selected_difference = difference[selected]
        selected_local = local_values[selected]
        selected_middle = middle_values[selected]
        selected_scale = max(
            float(np.linalg.norm(selected_local)),
            float(np.linalg.norm(selected_middle)),
            np.finfo(float).tiny,
        )
        return {
            "count": int(len(indices)),
            "absolute_l2_difference": float(np.linalg.norm(selected_difference)),
            "relative_l2_difference": float(
                np.linalg.norm(selected_difference) / selected_scale
            ),
        }

    dimensions: dict[str, list[int]] = {"edge": [], "face": []}
    basis_indices: dict[str, list[int]] = {}
    for index, key in enumerate(common):
        dimension = str(key[1])
        if dimension == "1":
            dimensions["edge"].append(index)
        elif dimension == "2":
            dimensions["face"].append(index)
        basis_indices.setdefault(str(int(key[3])), []).append(index)
    largest = np.argsort(-np.abs(difference), kind="stable")[:4]
    largest_differences = [
        {
            "key": repr(common[int(index)]),
            "local": [float(local_values[index].real), float(local_values[index].imag)],
            "middle": [
                float(middle_values[index].real),
                float(middle_values[index].imag),
            ],
            "absolute_difference": float(abs(difference[index])),
        }
        for index in largest
    ]
    tiny = np.finfo(float).tiny
    factor_audit: dict[str, Any] = {}
    if propagation_factor is not None and effective_beta is not None:
        factor = complex(propagation_factor)
        expected_factor = complex(
            np.exp(1j * complex(effective_beta) * float(propagation_length_nm))
        )
        factor_scale = max(abs(factor), abs(expected_factor), np.finfo(float).tiny)
        factor_audit = {
            "stable_factor": [float(factor.real), float(factor.imag)],
            "pointwise_expected_factor": [
                float(expected_factor.real),
                float(expected_factor.imag),
            ],
            "relative_difference": float(abs(factor - expected_factor) / factor_scale),
            "magnitude": float(abs(factor)),
            "log_magnitude": (
                None if log_magnitude is None else float(log_magnitude)
            ),
            "roundoff_growth_clipped": (
                None
                if roundoff_growth_clipped is None
                else bool(roundoff_growth_clipped)
            ),
        }
    return {
        "label": label,
        "interface_key_count": int(len(expected)),
        "common_key_count": int(len(common)),
        "missing_key_count": int(len(missing)),
        "middle_norm": middle_norm,
        "local_norm": local_norm,
        "absolute_l2_difference": absolute_difference,
        "relative_l2_difference": relative_difference,
        "best_global_complex_scalar": (
            None
            if scalar is None
            else [float(scalar.real), float(scalar.imag)]
        ),
        "relative_residual_after_best_global_scalar": scalar_residual,
        "dimension_errors": {
            name: subgroup(indices) for name, indices in dimensions.items()
        },
        "basis_index_errors": {
            name: subgroup(indices) for name, indices in basis_indices.items()
        },
        "largest_differences": largest_differences,
        "identifiability": {
            "scale": float(scale),
            "norms_near_underflow": bool(scale <= np.sqrt(tiny)),
            "numerically_identifiable": bool(
                np.isfinite(scale) and scale > np.sqrt(tiny)
            ),
        },
        "factor": factor_audit,
    }


def _normalize_single_active_vector(
    active: PETSc.Vec,
) -> tuple[PETSc.Vec, dict[str, Any]]:
    source_basis = OwnerLocalBasis.from_vectors(
        (active,),
        label="E1_column",
        research_opt_in=True,
    )
    normalized_basis = None
    try:
        normalized_basis, audits = normalize_owner_local_columns(
            source_basis,
            research_opt_in=True,
        )
        normalized = normalized_basis.columns[0].duplicate()
        normalized_basis.columns[0].copy(normalized)
        audit = audits[0]
        return normalized, {
            "norm_before": float(audit.norm_before),
            "norm_after": float(audit.norm_after),
            "pivot_global_row": int(audit.pivot_global_row),
        }
    finally:
        if normalized_basis is not None:
            normalized_basis.destroy()
        source_basis.destroy()


def _mode_basis_summary(
    basis: Any,
    solve_report: Any,
    selection_report: Any,
    *,
    direction: str,
) -> dict[str, Any]:
    modes = tuple(basis.modes)
    betas = np.asarray([complex(mode.beta) for mode in modes], dtype=np.complex128)
    beta_abs = np.abs(betas)
    beta_real = betas.real
    beta_imag = betas.imag
    right_residuals = [float(mode.right.polynomial_relative_residual) for mode in modes]
    left_residuals = [float(mode.left_polynomial_relative_residual) for mode in modes]
    return {
        "direction": direction,
        "right_count": int(len(modes)),
        "left_count": int(len(modes)),
        "candidate_count": int(selection_report.candidate_modes),
        "selected_count": int(selection_report.selected_modes),
        "solve_converged_modes": int(solve_report.converged_modes),
        "beta_hash": _complex_hash(betas),
        "beta_abs_min": float(np.min(beta_abs)) if len(betas) else 0.0,
        "beta_abs_max": float(np.max(beta_abs)) if len(betas) else 0.0,
        "beta_real_min": float(np.min(beta_real)) if len(betas) else 0.0,
        "beta_real_max": float(np.max(beta_real)) if len(betas) else 0.0,
        "beta_imag_min": float(np.min(beta_imag)) if len(betas) else 0.0,
        "beta_imag_max": float(np.max(beta_imag)) if len(betas) else 0.0,
        "right_qep_residual_max": max(right_residuals, default=0.0),
        "left_qep_residual_max": max(left_residuals, default=0.0),
        "left_pair_relative_error_max": max(
            (float(value) for value in basis.left_pair_relative_errors),
            default=0.0,
        ),
        "biorthogonality_max": float(basis.max_entry_identity_error),
        "biorthogonality_identity_error": float(basis.max_identity_error),
        "near_degenerate_group_count": int(len(basis.groups)),
        "near_degenerate_group_sizes": [
            int(len(group.indices)) for group in basis.groups
        ],
        "passive_branch_valid": all(bool(mode.passive_branch_valid) for mode in modes),
        "selection": {
            "direction_counts": dict(selection_report.direction_counts),
            "passive_candidate_count": int(selection_report.passive_candidate_count),
            "finite_candidate_count": int(selection_report.finite_candidate_count),
            "numerically_infinite_candidate_count": int(
                selection_report.numerically_infinite_candidate_count
            ),
            "flux_tolerance": float(selection_report.flux_tolerance),
        },
    }


def _build_e1_resources(request: Any) -> tuple[_E1Resources, dict[str, Any]]:
    config = request.config
    comm = request.b.getComm().tompi4py()
    if int(config.nedelec_degree) != 6:
        raise ValueError("E1 requires the frozen p6 Full3D request")
    if not np.isclose(float(config.mesh_target_size), 10.0):
        raise ValueError("E1 requires the frozen h10 Full3D request")
    if str(config.polarization_kind) != "s":
        raise ValueError("E1 requires the frozen S-polarized request")
    if not np.isclose(float(config.lambda0), 13.5):
        raise ValueError("E1 requires the frozen 13.5 nm wavelength")
    if not np.isclose(float(config.incident_theta_deg), 80.0):
        raise ValueError("E1 requires the frozen 80 degree incidence theta")
    if not np.isclose(float(config.incident_phi_deg), 0.0):
        raise ValueError("E1 requires the frozen zero azimuth")
    if int(request.n_aux) != E1_AUXILIARY_MODE_COUNT:
        raise ValueError("E1 requires exactly 80 auxiliary modes")
    if int(request.n_fe) != E1_EXPECTED_ACTIVE_ROWS:
        raise ValueError("E1 requires exactly 51192 active FE rows")
    if request.fine_operator.getSize() != (
        E1_EXPECTED_ACTIVE_ROWS,
        E1_EXPECTED_ACTIVE_ROWS,
    ):
        raise ValueError("E1 fine action must be a 51192 by 51192 operator")
    if request.operator.getSize() != (
        E1_EXPECTED_ACTIVE_ROWS + E1_AUXILIARY_MODE_COUNT,
        E1_EXPECTED_ACTIVE_ROWS + E1_AUXILIARY_MODE_COUNT,
    ):
        raise ValueError("E1 augmented action must be a 51272 by 51272 operator")

    modal_config = target_stage4_config(degree=6, h_nm=10.0)
    modal_config.incident_theta_deg = float(config.incident_theta_deg)
    modal_config.incident_phi_deg = float(config.incident_phi_deg)
    modal_config.polarization_kind = str(config.polarization_kind)
    modal_config.custom_polarization = config.custom_polarization
    modal_config.use_floquet_xy = bool(config.use_floquet_xy)
    modal_config.stage4_full3d_assembly_backend = config.stage4_full3d_assembly_backend
    resources = _E1Resources()
    positive_right = None
    negative_right = None
    try:
        resources.cross_section = build_matching_cross_section(
            modal_config,
            "stage4_xy",
            comm=comm,
        )
        resources.spaces = build_cross_section_spaces(
            resources.cross_section,
            transverse_degree=6,
            longitudinal_degree=6,
        )
        resources.operators = assemble_quadratic_beta_operators(
            modal_config,
            resources.cross_section,
            resources.spaces,
        )
        poynting = PoyntingFluxEvaluator(
            modal_config,
            resources.cross_section,
            resources.spaces,
        )
        target_beta = analytic_homogeneous_beta(
            modal_config,
            modal_config.n_air,
        )
        positive_right, positive_report = solve_quadratic_beta_modes(
            resources.operators,
            target=target_beta,
            requested_modes=E1_CANDIDATE_MODE_COUNT,
        )
        positive_right, positive_selection = select_passive_direction_modes(
            positive_right,
            desired_direction="forward",
            requested_modes=E1_SELECTED_MODE_COUNT,
            poynting_evaluator=poynting,
            maximum_abs_beta=E1_MAX_ABS_BETA_PER_NM,
        )
        if len(positive_right) != E1_SELECTED_MODE_COUNT:
            raise RuntimeError("positive QEP did not deliver 120 forward modes")
        try:
            resources.positive = build_biorthogonal_mode_basis(
                modal_config,
                resources.cross_section,
                resources.spaces,
                resources.operators,
                positive_right,
                adjoint_target=np.conj(target_beta),
                requested_left_modes=E1_CANDIDATE_MODE_COUNT,
                near_degenerate_tolerance=E1_NEAR_DEGENERATE_TOLERANCE,
                block_rotation_tolerance=E1_NEAR_DEGENERATE_TOLERANCE,
                poynting_evaluator=poynting,
            )
        finally:
            positive_right = None

        negative_right, negative_report = solve_quadratic_beta_modes(
            resources.operators,
            target=-target_beta,
            requested_modes=E1_CANDIDATE_MODE_COUNT,
        )
        negative_right, negative_selection = select_passive_direction_modes(
            negative_right,
            desired_direction="backward",
            requested_modes=E1_SELECTED_MODE_COUNT,
            poynting_evaluator=poynting,
            maximum_abs_beta=E1_MAX_ABS_BETA_PER_NM,
        )
        if len(negative_right) != E1_SELECTED_MODE_COUNT:
            raise RuntimeError("negative QEP did not deliver 120 backward modes")
        try:
            resources.negative = build_biorthogonal_mode_basis(
                modal_config,
                resources.cross_section,
                resources.spaces,
                resources.operators,
                negative_right,
                adjoint_target=-np.conj(target_beta),
                requested_left_modes=E1_CANDIDATE_MODE_COUNT,
                near_degenerate_tolerance=E1_NEAR_DEGENERATE_TOLERANCE,
                block_rotation_tolerance=E1_NEAR_DEGENERATE_TOLERANCE,
                poynting_evaluator=poynting,
            )
        finally:
            negative_right = None
        pairs = pair_reciprocal_mode_bases(
            resources.operators,
            resources.positive,
            resources.negative,
        )
        resources.bottom = assemble_hybrid_local_dtn_system(
            config,
            "bottom",
            bottom_interface_z_nm=E1_BOTTOM_INTERFACE_NM,
            top_interface_z_nm=E1_TOP_INTERFACE_NM,
            comm=comm,
        )
        resources.top = assemble_hybrid_local_dtn_system(
            config,
            "top",
            bottom_interface_z_nm=E1_BOTTOM_INTERFACE_NM,
            top_interface_z_nm=E1_TOP_INTERFACE_NM,
            comm=comm,
        )
        coupling = build_hybrid_internal_mode_coupling(
            config,
            resources.spaces,
            resources.positive,
            resources.negative,
            resources.bottom,
            resources.top,
            length_nm=100.0,
            propagation_model=E1_PROPAGATION_MODEL,
            modal_traction_model=E1_TRACTION_MODEL,
        )
        resources.coupling = coupling
        resources.bottom_map = build_hybrid_strong_trace_interface_map(
            resources.bottom,
            coupling,
            research_opt_in=True,
        )
        resources.top_map = build_hybrid_strong_trace_interface_map(
            resources.top,
            coupling,
            research_opt_in=True,
        )
        resources.bottom_extender = HomogeneousEndcapExtender.from_system(
            resources.bottom,
            resources.bottom_map,
            research_opt_in=True,
        )
        resources.top_extender = HomogeneousEndcapExtender.from_system(
            resources.top,
            resources.top_map,
            research_opt_in=True,
        )
        propagation = coupling.propagation
        mode_audit = {
            "target_beta_per_nm": _json_complex(target_beta),
            "candidate_count_per_direction": E1_CANDIDATE_MODE_COUNT,
            "selected_count_per_direction": E1_SELECTED_MODE_COUNT,
            "near_degenerate_tolerance": E1_NEAR_DEGENERATE_TOLERANCE,
            "block_rotation_tolerance": E1_NEAR_DEGENERATE_TOLERANCE,
            "positive": _mode_basis_summary(
                resources.positive,
                positive_report,
                positive_selection,
                direction="forward",
            ),
            "negative": _mode_basis_summary(
                resources.negative,
                negative_report,
                negative_selection,
                direction="backward",
            ),
            "reciprocal_pair_count": int(len(pairs)),
            "reciprocal_pair_index_hash": hashlib.sha256(
                np.asarray(
                    [
                        (int(pair.positive_index), int(pair.negative_index))
                        for pair in pairs
                    ],
                    dtype=np.dtype("<i8"),
                ).tobytes(order="C")
            ).hexdigest(),
            "reciprocal_max_beta_error": max(
                (float(pair.relative_beta_error) for pair in pairs),
                default=float("inf"),
            ),
            "reciprocal_min_overlap": min(
                (float(pair.electric_mass_overlap) for pair in pairs),
                default=0.0,
            ),
            "reciprocal_opposite_direction": all(
                bool(pair.opposite_direction) for pair in pairs
            ),
            "reciprocal_passive_branches": all(
                bool(pair.passive_branches_valid) for pair in pairs
            ),
            "forward_beta_per_nm_hash": _complex_hash(propagation.forward.beta_per_nm),
            "forward_beta_per_nm_count": int(len(propagation.forward.beta_per_nm)),
            "backward_beta_per_nm_hash": _complex_hash(
                propagation.backward.beta_per_nm
            ),
            "backward_beta_per_nm_count": int(len(propagation.backward.beta_per_nm)),
            "forward_effective_beta_per_nm_hash": _complex_hash(
                propagation.forward.effective_beta_per_nm
            ),
            "forward_effective_beta_per_nm_count": int(
                len(propagation.forward.effective_beta_per_nm)
            ),
            "backward_effective_beta_per_nm_hash": _complex_hash(
                propagation.backward.effective_beta_per_nm
            ),
            "backward_effective_beta_per_nm_count": int(
                len(propagation.backward.effective_beta_per_nm)
            ),
            "positive_traction_beta_per_nm_hash": _complex_hash(
                coupling.positive_traction_beta_per_nm
            ),
            "positive_traction_beta_per_nm_count": int(
                len(coupling.positive_traction_beta_per_nm)
            ),
            "negative_traction_beta_per_nm_hash": _complex_hash(
                coupling.negative_traction_beta_per_nm
            ),
            "negative_traction_beta_per_nm_count": int(
                len(coupling.negative_traction_beta_per_nm)
            ),
            "forward_factor_hash": _complex_hash(propagation.forward.factors),
            "backward_factor_hash": _complex_hash(propagation.backward.factors),
            "forward_factor_min_abs": float(min(map(abs, propagation.forward.factors))),
            "forward_factor_max_abs": float(max(map(abs, propagation.forward.factors))),
            "backward_factor_min_abs": float(
                min(map(abs, propagation.backward.factors))
            ),
            "backward_factor_max_abs": float(
                max(map(abs, propagation.backward.factors))
            ),
            "propagation_model": propagation.propagation_model,
            "modal_traction_model": coupling.modal_traction_model,
        }
        return resources, mode_audit
    except Exception:
        if positive_right is not None:
            for mode in positive_right:
                mode.destroy()
        if negative_right is not None:
            for mode in negative_right:
                mode.destroy()
        resources.release_all()
        raise


def _set_e1_modal_source(
    mode: Any,
    source: fem.Function,
    transverse: fem.Function,
    longitudinal: fem.Function,
    spaces: Any,
    evaluator: _DistributedTwoDimensionalEvaluator,
) -> None:
    mode.right.right_full.copy(source.x.petsc_vec)
    source.x.scatter_forward()
    transverse.x.array[:] = source.x.array[spaces.transverse_to_mixed]
    longitudinal.x.array[:] = source.x.array[spaces.longitudinal_to_mixed]
    transverse.x.scatter_forward()
    longitudinal.x.scatter_forward()
    evaluator.set_source(
        source,
        components=(transverse, longitudinal),
    )


def _build_e1_column(
    request: Any,
    resources: _E1Resources,
    evaluator: _DistributedTwoDimensionalEvaluator,
    source: fem.Function,
    transverse: fem.Function,
    longitudinal: fem.Function,
    *,
    mode_index: int,
    direction: str,
    geometry_tolerance: float,
    run_dir: Path | None = None,
) -> tuple[PETSc.Vec, dict[str, Any]]:
    if direction == "forward":
        mode = resources.positive.modes[mode_index]
        bottom_coefficients = np.zeros(E1_SELECTED_MODE_COUNT, dtype=np.complex128)
        top_coefficients = np.zeros_like(bottom_coefficients)
        bottom_coefficients[mode_index] = 1.0
        top_coefficients[mode_index] = resources.coupling.propagation.forward.factors[
            mode_index
        ]
    elif direction == "backward":
        mode = resources.negative.modes[mode_index]
        negative_trace = resources.coupling.negative_trace_to_positive[:, mode_index]
        bottom_coefficients = (
            resources.coupling.propagation.backward.factors[mode_index] * negative_trace
        )
        top_coefficients = np.asarray(negative_trace, dtype=np.complex128)
    else:
        raise ValueError("E1 column direction must be forward or backward")
    _set_e1_modal_source(
        mode,
        source,
        transverse,
        longitudinal,
        resources.spaces,
        evaluator,
    )
    middle_active, middle_audit = build_middle_modal_active_column(
        request.static_condensed_system,
        request.function_space,
        request.floquet_data,
        evaluator,
        resources.coupling.propagation,
        mode_index=mode_index,
        direction=direction,
        bottom_z_nm=E1_BOTTOM_INTERFACE_NM,
        top_z_nm=E1_TOP_INTERFACE_NM,
        research_opt_in=True,
    )
    bottom_full = None
    top_full = None
    bottom_active = None
    top_active = None
    try:
        middle_packets_local, _ = extract_canonical_active_trace_packets(
            request.static_condensed_system,
            request.function_space,
            request.floquet_data,
            middle_active,
            geometry_tolerance=geometry_tolerance,
        )
        bottom_full, bottom_audit = resources.bottom_extender.apply(
            bottom_coefficients,
            research_opt_in=True,
        )
        top_full, top_audit = resources.top_extender.apply(
            top_coefficients,
            research_opt_in=True,
        )
        bottom_active = resources.bottom_extender.extract_active_fe_prefix(
            bottom_full,
            research_opt_in=True,
        )
        top_active = resources.top_extender.extract_active_fe_prefix(
            top_full,
            research_opt_in=True,
        )
        bottom_packets_local, _ = extract_canonical_active_trace_packets(
            resources.bottom.static_condensation.condensed,
            resources.bottom.V,
            resources.bottom.floquet_data,
            bottom_active,
            geometry_tolerance=geometry_tolerance,
        )
        top_packets_local, _ = extract_canonical_active_trace_packets(
            resources.top.static_condensation.condensed,
            resources.top.V,
            resources.top.floquet_data,
            top_active,
            geometry_tolerance=geometry_tolerance,
        )
        comm = request.function_space.mesh.comm
        middle_packets = _complete_single_column_packets(
            middle_packets_local,
            comm,
        )
        bottom_packets = _complete_single_column_packets(
            bottom_packets_local,
            comm,
        )
        top_packets = _complete_single_column_packets(top_packets_local, comm)
        if (
            run_dir is not None
            and direction == "forward"
            and int(mode_index) == 0
        ):
            bottom_plane = int(
                np.rint(E1_BOTTOM_INTERFACE_NM / geometry_tolerance)
            )
            top_plane = int(np.rint(E1_TOP_INTERFACE_NM / geometry_tolerance))
            middle_map = {key: complex(value) for key, value in middle_packets}
            bottom_interface_keys = {
                key
                for key in middle_map
                if all(int(point[2]) == bottom_plane for point in key[2])
            }
            top_interface_keys = {
                key
                for key in middle_map
                if all(int(point[2]) == top_plane for point in key[2])
            }
            if not bottom_interface_keys or not top_interface_keys:
                raise ValueError(
                    "first-column diagnostic requires non-empty middle "
                    "interface keys"
                )
            top_factor = resources.coupling.propagation.forward.factors[mode_index]
            top_block = resources.coupling.propagation.forward
            interface_diagnostic = {
                "bottom": _diagnose_interface_packets(
                    middle_packets,
                    bottom_packets,
                    interface_keys=bottom_interface_keys,
                    label="bottom",
                ),
                "top": _diagnose_interface_packets(
                    middle_packets,
                    top_packets,
                    interface_keys=top_interface_keys,
                    label="top",
                    propagation_factor=top_factor,
                    effective_beta=top_block.effective_beta_per_nm[mode_index],
                    propagation_length_nm=(
                        E1_TOP_INTERFACE_NM - E1_BOTTOM_INTERFACE_NM
                    ),
                    log_magnitude=top_block.log_magnitudes[mode_index],
                    roundoff_growth_clipped=top_block.roundoff_growth_clipped[
                        mode_index
                    ],
                ),
            }
            top_diagnostic = interface_diagnostic["top"]
            factor_diagnostic = top_diagnostic["factor"]
            diagnostic = {
                "source": "pre_stitch_forward_j0",
                "direction": direction,
                "mode_index": int(mode_index),
                "middle": middle_audit,
                "bottom_extension": bottom_audit,
                "top_extension": top_audit,
                "bottom": interface_diagnostic["bottom"],
                "top": top_diagnostic,
                "forward_factor": factor_diagnostic,
            }
            if comm.rank == 0:
                run_dir.mkdir(parents=True, exist_ok=True)
                _write_json(
                    run_dir / "task037_e1_first_column_diagnostic.json",
                    diagnostic,
                )
            comm.barrier()
        stitched_packets, stitch_audit = stitch_canonical_active_trace_packets(
            middle_packets,
            bottom_packets,
            top_packets,
            bottom_interface_z=E1_BOTTOM_INTERFACE_NM,
            top_interface_z=E1_TOP_INTERFACE_NM,
            geometry_tolerance=geometry_tolerance,
            research_opt_in=True,
        )
        reconstructed, reconstruct_audit = reconstruct_canonical_active_trace_vector(
            request.static_condensed_system,
            request.function_space,
            request.floquet_data,
            stitched_packets,
            geometry_tolerance=geometry_tolerance,
        )
        normalized, normalization_audit = _normalize_single_active_vector(reconstructed)
        packet_audit = {
            "direction": direction,
            "mode_index": int(mode_index),
            "middle": middle_audit,
            "bottom_extension": bottom_audit,
            "top_extension": top_audit,
            "stitch": stitch_audit,
            "reconstruct": reconstruct_audit,
            "normalization": normalization_audit,
            "finite": bool(np.all(np.isfinite(normalized.getArray(readonly=True)))),
            "nonzero": bool(normalized.norm(PETSc.NormType.NORM_2) > 0.0),
        }
        return normalized, packet_audit
    finally:
        middle_active.destroy()
        if bottom_full is not None:
            bottom_full.destroy()
        if top_full is not None:
            top_full.destroy()
        if bottom_active is not None:
            bottom_active.destroy()
        if top_active is not None:
            top_active.destroy()


def qualify_e1_modal_basis_audit(
    audit: dict[str, Any],
    *,
    solver_summary: dict[str, Any] | None = None,
    return_code: int = 0,
    no_swap: bool = True,
) -> dict[str, Any]:
    """Independently classify a completed E1 raw audit without recomputing Z."""

    if not isinstance(audit, dict):
        audit = {}
    solver_summary = solver_summary if isinstance(solver_summary, dict) else {}
    materialization = audit.get("materialization")
    materialization = materialization if isinstance(materialization, dict) else {}
    action_space = audit.get("action_space")
    action_space = action_space if isinstance(action_space, dict) else {}
    column_summary = audit.get("column_audit_summary")
    column_summary = column_summary if isinstance(column_summary, dict) else {}
    factor_inventory = audit.get("factor_inventory")
    factor_inventory = factor_inventory if isinstance(factor_inventory, dict) else {}
    bottom_factor = factor_inventory.get("bottom")
    bottom_factor = bottom_factor if isinstance(bottom_factor, dict) else {}
    top_factor = factor_inventory.get("top")
    top_factor = top_factor if isinstance(top_factor, dict) else {}
    interface_values = (
        audit.get("max_bottom_retained_residual"),
        audit.get("max_top_retained_residual"),
        audit.get("max_local_interface_mismatch"),
        audit.get("max_stitch_interface_mismatch"),
    )
    interface_gate = all(
        isinstance(value, (int, float, np.integer, np.floating))
        and not isinstance(value, bool)
        and np.isfinite(float(value))
        and float(value) <= 1.0e-10
        for value in interface_values
    )
    raw_effective_rank = action_space.get("effective_rank")
    effective_rank = None
    if (
        isinstance(raw_effective_rank, (int, float, np.integer, np.floating))
        and not isinstance(raw_effective_rank, bool)
        and np.isfinite(float(raw_effective_rank))
    ):
        effective_rank = int(raw_effective_rank)
    checks = {
        "return_code_zero": int(return_code) == 0,
        "research_only": audit.get("research_only") is True,
        "ordinary_default_unchanged": audit.get("ordinary_default_changed") is False,
        "implementation_gate_pass": audit.get("implementation_gate_pass") is True,
        "audit_gate_pass": audit.get("gate_pass") is True,
        "n_aux_80": audit.get("n_aux") == E1_AUXILIARY_MODE_COUNT,
        "column_count_240": (
            audit.get("column_count") == E1_TOTAL_COLUMN_COUNT
            and audit.get("forward_column_count") == E1_SELECTED_MODE_COUNT
            and audit.get("backward_column_count") == E1_SELECTED_MODE_COUNT
        ),
        "column_recreation_240": (
            column_summary.get("first_pass_column_count") == E1_TOTAL_COLUMN_COUNT
            and column_summary.get("second_pass_column_count") == E1_TOTAL_COLUMN_COUNT
            and column_summary.get("all_columns_recreated") is True
        ),
        "active_rows_51192": audit.get("global_active_rows") == E1_EXPECTED_ACTIVE_ROWS,
        "finite_nonzero_columns": audit.get("finite_nonzero_columns") is True,
        "coverage_zero": (
            audit.get("missing") == 0
            and audit.get("extra") == 0
            and audit.get("duplicate") == 0
        ),
        "repeat_gate": (
            isinstance(audit.get("max_repeat_error"), (int, float))
            and float(audit["max_repeat_error"]) <= E1_REPEAT_TOLERANCE
        ),
        "action_gate": (
            isinstance(audit.get("random_action_relative_error"), (int, float))
            and float(audit["random_action_relative_error"]) <= E1_ACTION_TOLERANCE
        ),
        "rank_gate": (
            effective_rank is not None and effective_rank >= E1_MIN_ACTION_RANK
        ),
        "normal_equations_forbidden": (
            action_space.get("normal_equations_used") is False
        ),
        "global_A_not_materialized": (
            materialization.get("global_A_materialized") is False
        ),
        "global_F_not_materialized": (
            materialization.get("global_F_materialized") is False
        ),
        "factors_released": audit.get("factors_released") is True,
        "interface_gate": interface_gate,
        "factor_setup_once": (
            bottom_factor.get("setup_count") == 1 and top_factor.get("setup_count") == 1
        ),
        "no_swap": bool(no_swap),
        "no_official_result": (
            audit.get("official_result") is False
            and solver_summary.get("official_result") is False
        ),
        "no_ksp_iterations": (
            audit.get("ksp_iterations") == 0
            and solver_summary.get("ksp_iterations") == 0
        ),
        "external_component_profile": (
            solver_summary.get("external_solver_profile") == "task037_e1_component_only"
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    if audit.get("implementation_gate_pass") is not True:
        classification = "M120_GLOBAL_MODAL_BASIS_IMPLEMENTATION_FAILED"
    elif effective_rank is None:
        classification = "M120_GLOBAL_MODAL_BASIS_IMPLEMENTATION_FAILED"
    elif effective_rank < E1_MIN_ACTION_RANK:
        classification = "M120_GLOBAL_ACTION_BASIS_COLLAPSED"
    elif failures:
        classification = "M120_GLOBAL_MODAL_BASIS_IMPLEMENTATION_FAILED"
    else:
        classification = "M120_GLOBAL_MODAL_BASIS_GATE_PASSED"
    return {
        "pass": not failures,
        "checks": checks,
        "failures": failures,
        "classification": classification,
    }


def _run_e1_modal_basis_gate(
    request: Any,
    *,
    run_dir: Path,
    source_sha: str,
    e2_live_callback: (
        Callable[[OwnerLocalBasis, OwnerLocalBasis, PETSc.Mat], None] | None
    ) = None,
) -> dict[str, Any]:
    comm = request.b.getComm().tompi4py()
    resources, mode_audit = _build_e1_resources(request)
    z_basis = None
    y_basis = None
    a6_operator = None
    _a6_context = None
    pending_columns: list[PETSc.Vec] = []
    source = None
    transverse = None
    longitudinal = None
    evaluator = None
    geometry_tolerance = None
    first_pass_count = 0
    second_pass_count = 0
    finite_nonzero_local = True
    max_stitch_mismatch = 0.0
    max_bottom_residual = 0.0
    max_top_residual = 0.0
    max_interface_mismatch = 0.0
    max_reconstruction_missing = 0
    max_reconstruction_extra = 0
    max_reconstruction_duplicate = 0
    max_repeat_error = 0.0
    try:
        source = fem.Function(resources.spaces.mixed)
        transverse = fem.Function(resources.spaces.transverse)
        longitudinal = fem.Function(resources.spaces.longitudinal)
        evaluator = _DistributedTwoDimensionalEvaluator(
            source,
            padding=1.0e-10,
            components=(transverse, longitudinal),
        )
        geometry_tolerance = mesh_coordinate_tolerance(request.function_space.mesh)
        for direction in ("forward", "backward"):
            for mode_index in range(E1_SELECTED_MODE_COUNT):
                column, audit = _build_e1_column(
                    request,
                    resources,
                    evaluator,
                    source,
                    transverse,
                    longitudinal,
                    mode_index=mode_index,
                    direction=direction,
                    geometry_tolerance=geometry_tolerance,
                    run_dir=run_dir,
                )
                pending_columns.append(column)
                first_pass_count += 1
                finite_nonzero_local = bool(
                    finite_nonzero_local and audit["finite"] and audit["nonzero"]
                )
                stitch = audit["stitch"]
                max_stitch_mismatch = max(
                    max_stitch_mismatch,
                    float(stitch["interface_relative_mismatch"]),
                )
                max_interface_mismatch = max(
                    max_interface_mismatch,
                    float(audit["bottom_extension"]["interface_relative_mismatch"]),
                    float(audit["top_extension"]["interface_relative_mismatch"]),
                )
                max_bottom_residual = max(
                    max_bottom_residual,
                    float(audit["bottom_extension"]["retained_residual_relative"]),
                )
                max_top_residual = max(
                    max_top_residual,
                    float(audit["top_extension"]["retained_residual_relative"]),
                )
                reconstruction = audit["reconstruct"]
                max_reconstruction_missing = max(
                    max_reconstruction_missing,
                    int(reconstruction["global_missing_key_count"]),
                    int(reconstruction["missing_active_row_count"]),
                )
                max_reconstruction_extra = max(
                    max_reconstruction_extra,
                    int(reconstruction["global_extra_key_count"]),
                    int(reconstruction["extra_active_row_count"]),
                )
                max_reconstruction_duplicate = max(
                    max_reconstruction_duplicate,
                    int(reconstruction["global_duplicate_key_count"]),
                    int(reconstruction["active_row_write_duplicate_count"]),
                )
        if first_pass_count != E1_TOTAL_COLUMN_COUNT:
            raise RuntimeError("E1 first pass did not produce exactly 240 columns")
        z_basis = OwnerLocalBasis.from_vectors(
            pending_columns,
            label="Z",
            research_opt_in=True,
        )
        pending_columns = []
        finite_nonzero = bool(comm.allreduce(finite_nonzero_local, op=MPI.LAND))
        column_index = 0
        for direction in ("forward", "backward"):
            for mode_index in range(E1_SELECTED_MODE_COUNT):
                repeated, _repeat_audit = _build_e1_column(
                    request,
                    resources,
                    evaluator,
                    source,
                    transverse,
                    longitudinal,
                    mode_index=mode_index,
                    direction=direction,
                    geometry_tolerance=geometry_tolerance,
                    run_dir=run_dir,
                )
                try:
                    repeat_error = _relative_vector_error(
                        repeated,
                        z_basis.columns[column_index],
                    )
                    max_repeat_error = max(max_repeat_error, repeat_error)
                finally:
                    repeated.destroy()
                column_index += 1
        second_pass_count = column_index
        factor_inventory = {
            "bottom": {
                "setup_count": int(resources.bottom_extender.factor_setup_count),
                "apply_count": int(resources.bottom_extender.apply_count),
                "inventory": resources.bottom_extender.factor_inventory,
            },
            "top": {
                "setup_count": int(resources.top_extender.factor_setup_count),
                "apply_count": int(resources.top_extender.apply_count),
                "inventory": resources.top_extender.factor_inventory,
            },
        }
        release_audit = resources.release_endcap_stage()
        a6_operator, _a6_context = create_matrix_free_condensed_operator(
            request.blocks,
            fine_operator=request.fine_operator,
        )
        y_basis = z_basis.apply(
            a6_operator,
            label="Y",
            research_opt_in=True,
        )
        action_space = audit_owner_local_basis(
            y_basis,
            research_opt_in=True,
        )
        rng = np.random.default_rng(17037)
        coefficients = (
            rng.standard_normal(E1_TOTAL_COLUMN_COUNT)
            + 1j * rng.standard_normal(E1_TOTAL_COLUMN_COUNT)
        ).astype(np.complex128)
        z_combined = z_basis.combine(
            coefficients,
            research_opt_in=True,
        )
        y_combined = y_basis.combine(
            coefficients,
            research_opt_in=True,
        )
        expected_action = request.fine_operator.createVecLeft()
        try:
            a6_operator.mult(z_combined, expected_action)
            random_action_error = _relative_vector_error(
                y_combined,
                expected_action,
            )
        finally:
            z_combined.destroy()
            y_combined.destroy()
            expected_action.destroy()
        z_manifest = save_owner_local_basis_shard(
            z_basis,
            run_dir / "e1_owner_local",
            source_sha=source_sha,
            prefix="Z",
            research_opt_in=True,
        )
        y_manifest = save_owner_local_basis_shard(
            y_basis,
            run_dir / "e1_owner_local",
            source_sha=source_sha,
            prefix="Y",
            research_opt_in=True,
        )
        z_manifest_path = run_dir / "e1_owner_local" / "Z.manifest.json"
        y_manifest_path = run_dir / "e1_owner_local" / "Y.manifest.json"
        z_manifest_sha = _sha256_file(z_manifest_path) if comm.rank == 0 else None
        y_manifest_sha = _sha256_file(y_manifest_path) if comm.rank == 0 else None
        z_manifest_sha = comm.bcast(z_manifest_sha, root=0)
        y_manifest_sha = comm.bcast(y_manifest_sha, root=0)
        local_rows = int(z_basis.columns[0].getLocalSize())
        complex_bytes = np.dtype(np.complex128).itemsize
        z_local_bytes = int(local_rows * E1_TOTAL_COLUMN_COUNT * complex_bytes)
        y_local_bytes = int(local_rows * E1_TOTAL_COLUMN_COUNT * complex_bytes)
        local_qr_input_bytes = z_local_bytes
        local_qr_q_bytes = int(local_rows * E1_TOTAL_COLUMN_COUNT * complex_bytes)
        local_qr_r_bytes = int(
            E1_TOTAL_COLUMN_COUNT * E1_TOTAL_COLUMN_COUNT * complex_bytes
        )
        root_stacked_r_bytes = int(
            comm.size * E1_TOTAL_COLUMN_COUNT * E1_TOTAL_COLUMN_COUNT * complex_bytes
        )
        root_svd_bytes = int(
            E1_TOTAL_COLUMN_COUNT * E1_TOTAL_COLUMN_COUNT * complex_bytes
        )
        metadata_bytes = int(len(json.dumps(mode_audit, sort_keys=True)))
        z_manifest_summary = {
            "path": str(z_manifest_path),
            "sha256": z_manifest_sha,
            "shard_count": len(z_manifest["shards"]),
            "total_shard_bytes": int(
                sum(int(item["bytes"]) for item in z_manifest["shards"])
            ),
            "owner_local": bool(z_manifest["owner_local"]),
        }
        y_manifest_summary = {
            "path": str(y_manifest_path),
            "sha256": y_manifest_sha,
            "shard_count": len(y_manifest["shards"]),
            "total_shard_bytes": int(
                sum(int(item["bytes"]) for item in y_manifest["shards"])
            ),
            "owner_local": bool(y_manifest["owner_local"]),
        }
        storage = {
            "owner_local": True,
            "global_basis_replicated": False,
            "z_local_bytes_estimate": z_local_bytes,
            "y_local_bytes_estimate": y_local_bytes,
            "local_qr_input_bytes_estimate": local_qr_input_bytes,
            "local_qr_q_bytes_estimate": local_qr_q_bytes,
            "local_qr_r_bytes_estimate": local_qr_r_bytes,
            "root_stacked_r_bytes_estimate": root_stacked_r_bytes,
            "root_svd_bytes_estimate": root_svd_bytes,
            "metadata_bytes_estimate": metadata_bytes,
            "accounted_dense_arrays_working_set_bytes_estimate": int(
                z_local_bytes
                + y_local_bytes
                + local_qr_input_bytes
                + local_qr_q_bytes
                + local_qr_r_bytes
                + root_stacked_r_bytes
                + root_svd_bytes
                + metadata_bytes
            ),
            "estimate_kind": "derived_accounted_dense_arrays_not_measured",
            "z_manifest": z_manifest_summary,
            "y_manifest": y_manifest_summary,
        }
        action_checks = {
            "random_action_relative_error": float(random_action_error),
            "action_rank": int(action_space["effective_rank"]),
            "action_condition": float(action_space["retained_condition_number"]),
            "normal_equations_used": bool(action_space["normal_equations_used"]),
            "rank_pass": int(action_space["effective_rank"]) >= E1_MIN_ACTION_RANK,
            "random_action_pass": (float(random_action_error) <= E1_ACTION_TOLERANCE),
        }
        implementation_checks = {
            "n_aux_80": int(request.n_aux) == E1_AUXILIARY_MODE_COUNT,
            "global_active_rows": (
                int(request.n_fe) == E1_EXPECTED_ACTIVE_ROWS
                and int(z_basis.global_rows) == E1_EXPECTED_ACTIVE_ROWS
            ),
            "column_count_240": z_basis.column_count == E1_TOTAL_COLUMN_COUNT,
            "column_recreation_240": (
                first_pass_count == E1_TOTAL_COLUMN_COUNT
                and second_pass_count == E1_TOTAL_COLUMN_COUNT
            ),
            "forward_backward_counts": (
                mode_audit["positive"]["selected_count"] == E1_SELECTED_MODE_COUNT
                and mode_audit["negative"]["selected_count"] == E1_SELECTED_MODE_COUNT
            ),
            "finite_nonzero_columns": finite_nonzero,
            "coverage_zero": (
                max_reconstruction_missing == 0
                and max_reconstruction_extra == 0
                and max_reconstruction_duplicate == 0
            ),
            "repeat_gate": max_repeat_error <= E1_REPEAT_TOLERANCE,
            "interface_gate": (
                max_bottom_residual <= 1.0e-10
                and max_top_residual <= 1.0e-10
                and max_interface_mismatch <= 1.0e-10
                and max_stitch_mismatch <= 1.0e-10
            ),
            "factor_setup_once": (
                factor_inventory["bottom"]["setup_count"] == 1
                and factor_inventory["top"]["setup_count"] == 1
            ),
            "factor_released": all(release_audit.values()),
        }
        implementation_gate_pass = all(implementation_checks.values())
        gate_pass = bool(
            implementation_gate_pass
            and action_checks["rank_pass"]
            and action_checks["random_action_pass"]
            and action_checks["normal_equations_used"] is False
        )
        if not implementation_gate_pass:
            classification = "M120_GLOBAL_MODAL_BASIS_IMPLEMENTATION_FAILED"
        else:
            try:
                effective_rank = int(action_space["effective_rank"])
            except (KeyError, TypeError, ValueError, OverflowError):
                effective_rank = None
            if effective_rank is None:
                classification = "M120_GLOBAL_MODAL_BASIS_IMPLEMENTATION_FAILED"
            elif effective_rank < E1_MIN_ACTION_RANK:
                classification = "M120_GLOBAL_ACTION_BASIS_COLLAPSED"
            elif not gate_pass:
                classification = "M120_GLOBAL_MODAL_BASIS_IMPLEMENTATION_FAILED"
            else:
                classification = "M120_GLOBAL_MODAL_BASIS_GATE_PASSED"
        audit = {
            "schema_version": "task037.e1.modal-basis-audit.v1",
            "source_sha": source_sha,
            "research_only": True,
            "ordinary_default_changed": False,
            "status": classification,
            "classification": classification,
            "reason": classification,
            "implementation_gate_pass": bool(implementation_gate_pass),
            "gate_pass": gate_pass,
            "n_aux": int(request.n_aux),
            "global_active_rows": int(request.n_fe),
            "column_count": int(z_basis.column_count),
            "forward_column_count": E1_SELECTED_MODE_COUNT,
            "backward_column_count": E1_SELECTED_MODE_COUNT,
            "finite_nonzero_columns": finite_nonzero,
            "missing": int(max_reconstruction_missing),
            "extra": int(max_reconstruction_extra),
            "duplicate": int(max_reconstruction_duplicate),
            "max_repeat_error": float(max_repeat_error),
            "random_action_relative_error": float(random_action_error),
            "max_stitch_interface_mismatch": float(max_stitch_mismatch),
            "max_bottom_retained_residual": float(max_bottom_residual),
            "max_top_retained_residual": float(max_top_residual),
            "max_local_interface_mismatch": float(max_interface_mismatch),
            "mode_audit": mode_audit,
            "implementation_checks": implementation_checks,
            "action_checks": action_checks,
            "action_space": action_space,
            "materialization": {
                "global_A_materialized": False,
                "global_F_materialized": False,
                "p6_retained_factor_count": 0,
                "p6_retained_factor_nnz": 0,
                "action_operator": "matrix_free_condensed_F_minus_C_Hinv_D",
                "dtn_included": True,
            },
            "factor_inventory": factor_inventory,
            "resources_released_before_action": release_audit,
            "factors_released": bool(release_audit["factor_released"]),
            "storage": storage,
            "official_result": False,
            "ksp_iterations": 0,
            "snapshot_profile": "task037_e1_component_only",
            "column_audit_summary": {
                "first_pass_column_count": int(first_pass_count),
                "second_pass_column_count": int(second_pass_count),
                "all_columns_recreated": (
                    first_pass_count == E1_TOTAL_COLUMN_COUNT
                    and second_pass_count == E1_TOTAL_COLUMN_COUNT
                ),
            },
        }
        if comm.rank == 0:
            run_dir.mkdir(parents=True, exist_ok=True)
            _write_json(run_dir / "task037_e1_modal_basis_audit.json", audit)
        comm.barrier()
        if gate_pass:
            try:
                _call_e2_live_callback(
                    e2_live_callback,
                    z_basis,
                    y_basis,
                    a6_operator,
                )
            except Exception as error:
                raise _E2LiveCallbackError(
                    "E2 live callback failed after E1 audit completion"
                ) from error
        return audit
    finally:
        if a6_operator is not None:
            a6_operator.destroy()
            a6_operator = None
        if y_basis is not None:
            y_basis.destroy()
        if z_basis is not None:
            z_basis.destroy()
        else:
            for column in pending_columns:
                column.destroy()
        resources.release_all()


def _write_e1_failure_audit(
    request: Any,
    *,
    run_dir: Path,
    source_sha: str,
    error: Exception,
) -> None:
    comm = request.b.getComm().tompi4py()
    try:
        if comm.rank == 0:
            run_dir.mkdir(parents=True, exist_ok=True)
            _write_json(
                run_dir / "task037_e1_modal_basis_audit.json",
                {
                    "schema_version": "task037.e1.modal-basis-audit.v1",
                    "source_sha": source_sha,
                    "research_only": True,
                    "ordinary_default_changed": False,
                    "status": "implementation_failure",
                    "implementation_gate_pass": False,
                    "gate_pass": False,
                    "reason": "M120_GLOBAL_MODAL_BASIS_IMPLEMENTATION_FAILED",
                    "exception_type": type(error).__name__,
                    "exception_message": str(error),
                    "n_aux": int(getattr(request, "n_aux", -1)),
                    "global_active_rows": int(getattr(request, "n_fe", -1)),
                    "column_count": None,
                    "materialization": {
                        "global_A_materialized": False,
                        "global_F_materialized": False,
                        "p6_retained_factor_count": 0,
                        "p6_retained_factor_nnz": 0,
                        "action_operator": "matrix_free_condensed_F_minus_C_Hinv_D",
                        "dtn_included": True,
                    },
                    "official_result": False,
                    "ksp_iterations": 0,
                },
            )
    except Exception:
        pass


def run_e1_modal_basis_gate(
    request: Any,
    *,
    run_dir: str | Path,
    source_sha: str,
    research_opt_in: bool = False,
    e2_live_callback: (
        Callable[[OwnerLocalBasis, OwnerLocalBasis, PETSc.Mat], None] | None
    ) = None,
) -> Any:
    """Construct, audit, and return the zero E1 component snapshot.

    The optional E2 callback receives borrowed Z, Y=A6 Z, and A6 exactly once
    after the E1 Gate passes; it must not retain or destroy them.
    """

    _require_research_opt_in(research_opt_in)
    run_dir = Path(run_dir)
    try:
        _run_e1_modal_basis_gate(
            request,
            run_dir=run_dir,
            source_sha=source_sha,
            e2_live_callback=e2_live_callback,
        )
        from .dtn_port_3d import Stage4ExternalLinearSolverSnapshot

        zero = request.operator.createVecRight()
        zero.set(PETSc.ScalarType(0.0))
        zero.assemble()
        if zero.getSize() != request.operator.getSize()[0]:
            zero.destroy()
            raise RuntimeError("E1 zero snapshot does not match augmented operator")
        return Stage4ExternalLinearSolverSnapshot(
            x=zero,
            converged_reason=-1,
            iterations=0,
            reported_relative_residual=None,
            condensed_true_residual=None,
            full_augmented_true_residual=None,
            ksp_type="not_run",
            pc_type="not_run",
            residual_limit=E1_ACTION_TOLERANCE,
            no_global_factor=True,
            solver_profile="task037_e1_component_only",
            assembled_matrix_released_before_solve=False,
            reduced_residual_norm=None,
        )
    except _E2LiveCallbackError:
        raise
    except Exception as error:
        _write_e1_failure_audit(
            request,
            run_dir=run_dir,
            source_sha=source_sha,
            error=error,
        )
        raise
