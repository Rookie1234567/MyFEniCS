"""Economical Maxwell-harmonic columns for the bounded adaptive pilot.

This is the paper's fixed vector-spherical-harmonic route.  It streams one
owned cell patch at a time, converts the boundary data to oriented Nedelec
coefficients, pairs it on Gamma, and reuses the existing impedance factor.
No generalized eigenproblem or global prolongation is constructed here.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import basix
import numpy as np
from mpi4py import MPI
from petsc4py import PETSc
from scipy.special import sph_harm

from .hcurl_assembly_time_condensation import (
    _canonical_axis_aligned_coordinates,
)
from .hybrid_adaptive_impedance_mass import (
    ActualHcurlCellTangentialMassProvider,
)
from .hybrid_adaptive_impedance_schwarz import (
    build_cell_active_trace_expansion,
)

PAPER_DIMENSIONLESS_KAPPA = 6.0 * np.pi
PAPER_BETA = 0.6
PAPER_LINEAR_P = 1
PAPER_RHO = PAPER_DIMENSIONLESS_KAPPA ** (-1.65)
PAPER_RHO2 = PAPER_RHO**2
PAPER_MU_RAW = PAPER_DIMENSIONLESS_KAPPA**0.7
PAPER_MU = 8
PAPER_CANDIDATE_COUNT = 160
DISCRETE_K0 = 2.0 * np.pi / 5.0
IDENTITY_GATE = 1.0e-10
_MACHINE_TOL = 64.0 * np.finfo(float).eps

__all__ = (
    "DISCRETE_K0",
    "EconomicalMaxwellHarmonicSpace",
    "EconomicalPatchRecord",
    "PAPER_BETA",
    "PAPER_CANDIDATE_COUNT",
    "PAPER_DIMENSIONLESS_KAPPA",
    "PAPER_LINEAR_P",
    "PAPER_MU",
    "PAPER_MU_RAW",
    "PAPER_RHO",
    "PAPER_RHO2",
    "EconomicalGammaRhsPreparation",
    "EconomicalPreparedPatch",
    "prepare_economical_gamma_rhs",
    "solve_prepared_economical_columns",
)


@dataclass
class EconomicalPatchRecord:
    """Origin-local harmonic trace columns and compact audit."""

    patch_id: tuple[int, int]
    cell_index: int
    rows: tuple[int, ...]
    weights: np.ndarray
    columns: np.ndarray | None
    audit: dict[str, Any]


@dataclass
class EconomicalPreparedPatch:
    """Origin-local Gamma right-hand side retained until action construction."""

    patch_id: tuple[int, int]
    cell_index: int
    rows: tuple[int, ...]
    rhs: np.ndarray | None
    audit: dict[str, Any]


@dataclass
class EconomicalGammaRhsPreparation:
    """Prepared Gamma columns without an action or harmonic solve."""

    local_patch_records: tuple[EconomicalPreparedPatch, ...]
    global_patch_metadata: tuple[tuple[Any, ...], ...]
    comm: MPI.Intracomm
    diagnostics: dict[str, Any]
    _destroyed: bool = False
    _consumed: bool = False

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._consumed = True
        for record in self.local_patch_records:
            record.rhs = None
            record.audit["prepared_rhs_released"] = True
        self.diagnostics.update(
            {
                "prepared_rhs_live": False,
                "prepared_rhs_released": True,
                "prepared_rhs_consumed": True,
                "prepared_rhs_destroyed": True,
            }
        )
        self._destroyed = True


@dataclass
class EconomicalMaxwellHarmonicSpace:
    """Distributed origin-local result; no global P or coarse matrix."""

    local_patch_records: tuple[EconomicalPatchRecord, ...]
    diagnostics: dict[str, Any]
    _destroyed: bool = False

    def destroy(self) -> None:
        if self._destroyed:
            return
        for record in self.local_patch_records:
            record.columns = None
        self._destroyed = True


def _scalar_harmonic(
    degree: int,
    order: int,
    theta: np.ndarray,
    phi: np.ndarray,
) -> np.ndarray:
    if abs(order) > degree:
        return np.zeros_like(theta, dtype=np.complex128)
    return np.asarray(
        sph_harm(order, degree, phi, theta),
        dtype=np.complex128,
    )


def _vsh_cartesian(
    directions: np.ndarray,
) -> tuple[np.ndarray, tuple[tuple[int, int, int], ...], dict[str, float]]:
    """Evaluate both tangential VSH families using Cartesian ladder values."""

    q = np.asarray(directions, dtype=np.float64)
    if q.ndim != 2 or q.shape[1] != 3:
        raise ValueError("VSH directions must have shape (n,3)")
    norms = np.linalg.norm(q, axis=1)
    if not np.all(np.isfinite(q)) or np.any(norms <= 0.0):
        raise ValueError("VSH directions must be finite and nonzero")
    q = q / norms[:, None]
    theta = np.arccos(np.clip(q[:, 2], -1.0, 1.0))
    phi = np.arctan2(q[:, 1], q[:, 0])
    columns: list[np.ndarray] = []
    keys: list[tuple[int, int, int]] = []
    cross_defect = 0.0
    tangent_defect = 0.0
    for degree in range(1, PAPER_MU + 1):
        for order in range(-degree, degree + 1):
            y = _scalar_harmonic(degree, order, theta, phi)
            ladder_plus = np.sqrt((degree - order) * (degree + order + 1)) * (
                _scalar_harmonic(degree, order + 1, theta, phi)
            )
            ladder_minus = np.sqrt((degree + order) * (degree - order + 1)) * (
                _scalar_harmonic(degree, order - 1, theta, phi)
            )
            angular_momentum = np.column_stack(
                (
                    0.5 * (ladder_plus + ladder_minus),
                    (ladder_plus - ladder_minus) / (2.0j),
                    order * y,
                )
            )
            gradient = -1.0j * np.cross(q, angular_momentum)
            toroidal = np.cross(gradient, q)
            denominator = max(float(np.linalg.norm(toroidal)), 1.0e-300)
            cross_defect = max(
                cross_defect,
                float(np.linalg.norm(toroidal + 1.0j * angular_momentum))
                / denominator,
            )
            for family, value in ((2, gradient), (3, toroidal)):
                columns.append(np.ascontiguousarray(value))
                keys.append((degree, order, family))
            tangent_defect = max(
                tangent_defect,
                float(
                    np.max(
                        np.abs(
                            np.sum(
                                q[:, :, None]
                                * np.stack((gradient, toroidal), axis=2),
                                axis=1,
                            )
                        )
                    )
                ),
            )
    values = np.stack(columns, axis=2)
    if values.shape[2] != PAPER_CANDIDATE_COUNT:
        raise RuntimeError("fixed VSH candidate count changed")
    return values, tuple(keys), {
        "vsh_tangential_defect": tangent_defect,
        "vsh_cross_identity_defect": cross_defect,
    }


def _radial_pullback(
    directions: np.ndarray,
    half_width: np.ndarray,
    values: np.ndarray,
) -> tuple[np.ndarray, dict[str, float | int]]:
    """Apply the fixed box-map ``J^{-T}`` and audit its branch identity."""

    q = np.asarray(directions, dtype=np.float64)
    half = np.asarray(half_width, dtype=np.float64)
    if values.shape != (len(q), 3, PAPER_CANDIDATE_COUNT):
        raise ValueError("VSH value block has the wrong shape")
    physical = np.empty_like(values)
    full_defect = 0.0
    tie_defect = 0.0
    tie_count = 0
    for point, direction in enumerate(q):
        radii = np.asarray(
            [
                half[axis] / abs(direction[axis])
                if direction[axis] != 0.0
                else np.inf
                for axis in range(3)
            ],
            dtype=np.float64,
        )
        radius = float(np.min(radii))
        if not np.isfinite(radius) or radius <= 0.0:
            raise ValueError("box radial map has an invalid boundary radius")
        active_axes = np.flatnonzero(
            np.abs(radii - radius)
            <= _MACHINE_TOL * max(abs(radius), 1.0)
        )
        if not len(active_axes):
            raise RuntimeError("box radial map has no deterministic face branch")
        chosen = int(active_axes[0])
        branch_values: list[np.ndarray] = []
        for axis in active_axes:
            axis = int(axis)
            jacobian = radius * (
                np.eye(3)
                + np.outer(
                    direction,
                    direction - np.eye(3, dtype=np.float64)[axis] / direction[axis],
                )
            )
            branch = np.linalg.solve(jacobian.T, values[point])
            branch_values.append(branch)
            simple = values[point] / radius
            full_defect = max(
                full_defect,
                float(np.linalg.norm(branch - simple))
                / max(float(np.linalg.norm(simple)), 1.0e-300),
            )
        if len(active_axes) > 1:
            tie_count += 1
            for branch in branch_values[1:]:
                tie_defect = max(
                    tie_defect,
                    float(np.linalg.norm(branch - branch_values[0]))
                    / max(float(np.linalg.norm(branch_values[0])), 1.0e-300),
                )
        physical[point] = values[point] / radius
        if chosen < 0:
            raise AssertionError("unreachable radial branch")
    if full_defect > IDENTITY_GATE or tie_defect > IDENTITY_GATE:
        raise ValueError("radial covariant pullback identity failed")
    return physical, {
        "radial_full_jacobian_identity_defect": full_defect,
        "radial_tie_invariance_defect": tie_defect,
        "radial_tie_point_count": tie_count,
    }


def _cell_affine_geometry(
    function_space: Any,
    cell: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
    mesh = function_space.mesh
    geometry_dofs = np.asarray(mesh.geometry.dofmap[int(cell)], dtype=np.int32)
    physical = np.asarray(mesh.geometry.x[geometry_dofs], dtype=np.float64)
    reference = np.asarray(
        basix.geometry(basix.CellType.hexahedron),
        dtype=np.float64,
    )
    if physical.shape != reference.shape or physical.shape != (8, 3):
        raise ValueError("economical route requires eight first-order hexa vertices")
    design = np.column_stack((reference, np.ones(len(reference))))
    fit, *_ = np.linalg.lstsq(design, physical, rcond=None)
    affine = np.asarray(fit[:3].T, dtype=np.float64)
    offset = np.asarray(fit[3], dtype=np.float64)
    reconstructed = reference @ affine.T + offset
    residual = float(np.linalg.norm(reconstructed - physical))
    scale = max(float(np.linalg.norm(physical)), 1.0)
    residual_relative = residual / scale
    if residual_relative > IDENTITY_GATE:
        raise ValueError("cell geometry is not affine")
    lower = physical.min(axis=0)
    upper = physical.max(axis=0)
    widths = upper - lower
    if np.any(widths <= 0.0):
        raise ValueError("cell has nonpositive widths")
    half_width = widths / 2.0
    center = (lower + upper) / 2.0
    off_diagonal = affine - np.diag(np.diag(affine))
    if float(np.linalg.norm(off_diagonal)) > IDENTITY_GATE * max(
        float(np.linalg.norm(affine)), 1.0
    ):
        raise ValueError("economical radial map requires an axis-aligned cell")
    determinant = float(np.linalg.det(affine))
    if not np.isfinite(determinant) or abs(determinant) <= 0.0:
        raise ValueError("cell affine map has a zero or non-finite determinant")
    _, canonical_widths = _canonical_axis_aligned_coordinates(
        mesh,
        int(cell),
        tolerance=1.0e-11,
    )
    if not np.allclose(widths, canonical_widths, rtol=0.0, atol=1.0e-11):
        raise ValueError("cell geometry width audit differs from canonical coordinates")
    return center, half_width, affine, offset, {
        "center": center.tolist(),
        "half_width": half_width.tolist(),
        "inradius": float(np.min(half_width)),
        "diameter_bound": float(np.linalg.norm(widths)),
        "positive_widths": bool(np.all(widths > 0.0)),
        "affine_map_residual_relative": residual_relative,
        "affine_determinant": determinant,
    }


def _physical_vsh_values(
    points: np.ndarray,
    center: np.ndarray,
    half_width: np.ndarray,
    candidate: int,
) -> np.ndarray:
    points = np.asarray(points, dtype=np.float64)
    displacement = points - np.asarray(center, dtype=np.float64)
    radius = np.linalg.norm(displacement, axis=1)
    values = np.zeros((len(points), 3), dtype=np.complex128)
    nonzero = radius > 0.0
    if np.any(nonzero):
        directions = displacement[nonzero] / radius[nonzero, None]
        vsh, _keys, _audit = _vsh_cartesian(directions)
        physical, _map_audit = _radial_pullback(
            directions,
            np.asarray(half_width, dtype=np.float64),
            vsh,
        )
        values[nonzero] = physical[:, :, int(candidate)]
    return values


def _oriented_vsh_coefficients(
    function_space: Any,
    condensed: Any,
    cell: int,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    element = function_space.element
    basix_element = element.basix_element
    dimension = int(element.space_dimension)
    if int(function_space.dofmap.index_map_bs) != 1:
        raise ValueError("economical interpolation requires scalar-blocked dofs")
    points = np.asarray(basix_element.points, dtype=np.float64)
    interpolation = np.asarray(basix_element.interpolation_matrix)
    if interpolation.shape != (dimension, 3 * len(points)):
        raise RuntimeError("Basix interpolation matrix is not component-major")
    center, half_width, affine, offset, geometry_audit = _cell_affine_geometry(
        function_space,
        int(cell),
    )
    reference_boundary = np.any(
        (np.abs(points) <= _MACHINE_TOL)
        | (np.abs(points - 1.0) <= _MACHINE_TOL),
        axis=1,
    )
    physical_points = points @ affine.T + offset
    boundary_points = physical_points[reference_boundary]
    displacement = boundary_points - center
    directions = displacement / np.linalg.norm(displacement, axis=1)[:, None]
    vsh, keys, vsh_audit = _vsh_cartesian(directions)
    physical_values, radial_audit = _radial_pullback(
        directions,
        half_width,
        vsh,
    )
    pullback_matrix = np.asarray(affine.T, dtype=np.float64)
    reference_values = np.einsum(
        "ij,njc->nic",
        pullback_matrix,
        physical_values,
    )
    reconstructed_physical = np.einsum(
        "ij,njc->nic",
        np.linalg.inv(pullback_matrix),
        reference_values,
    )
    pullback_defect = float(
        np.linalg.norm(reconstructed_physical - physical_values)
        / max(float(np.linalg.norm(physical_values)), 1.0e-300)
    )
    if not np.isfinite(pullback_defect) or pullback_defect > _MACHINE_TOL:
        raise ValueError("physical-to-reference H(curl) pullback identity failed")
    values = np.zeros(
        (len(points), 3, PAPER_CANDIDATE_COUNT),
        dtype=np.complex128,
    )
    values[reference_boundary] = reference_values
    component_major = np.ascontiguousarray(
        values.transpose(1, 0, 2).reshape(3 * len(points), PAPER_CANDIDATE_COUNT)
    )
    canonical = np.asarray(interpolation @ component_major, dtype=np.complex128)
    oriented = np.ascontiguousarray(canonical.copy())
    cell_info = np.asarray(
        function_space.mesh.topology.get_cell_permutation_info()[int(cell) : int(cell) + 1],
        dtype=np.uint32,
    )
    element.T_apply(oriented.ravel(), cell_info, PAPER_CANDIDATE_COUNT)

    interior = np.asarray(
        basix_element.entity_dofs[function_space.mesh.topology.dim][0],
        dtype=np.int32,
    )
    trace_positions = np.setdiff1d(
        np.arange(dimension, dtype=np.int32),
        interior,
        assume_unique=True,
    )
    local_dofs = np.asarray(function_space.dofmap.cell_dofs(int(cell)), dtype=np.int32)
    global_dofs = np.asarray(
        function_space.dofmap.index_map.local_to_global(local_dofs),
        dtype=PETSc.IntType,
    )
    expected_trace = np.asarray(
        condensed.cell_recovery_maps[int(cell)].trace_original_dofs,
        dtype=PETSc.IntType,
    )
    if not np.array_equal(global_dofs[trace_positions], expected_trace):
        raise ValueError("oriented cell trace does not match recovery trace rows")
    return oriented, trace_positions, {
        **geometry_audit,
        **vsh_audit,
        **radial_audit,
        "vsh_candidate_count": len(keys),
        "interpolation_boundary_point_count": int(np.count_nonzero(reference_boundary)),
        "interpolation_interior_point_count": int(np.count_nonzero(~reference_boundary)),
        "orientation_method": "Basix.interpolation_matrix_then_DOLFINx_T_apply",
        "physical_to_reference_pullback": "A.T @ v_phys",
        "physical_reference_reconstruction_defect": pullback_defect,
        "physical_reference_reconstruction_gate": _MACHINE_TOL,
        "trace_positions_identity": True,
    }


def _machine_range(
    rhs: np.ndarray,
) -> tuple[np.ndarray, dict[str, Any]]:
    if rhs.ndim != 2 or not rhs.size or not np.all(np.isfinite(rhs)):
        raise ValueError("economical Gamma RHS block is empty or non-finite")
    left, singular_values, _right = np.linalg.svd(rhs, full_matrices=False)
    if not singular_values.size or not np.isfinite(singular_values[0]):
        raise ValueError("economical Gamma RHS has no finite singular value")
    sigma_max = float(singular_values[0])
    if sigma_max <= 0.0:
        raise ValueError("economical Gamma pairing has zero candidate range")
    threshold = max(rhs.shape) * np.finfo(float).eps * sigma_max
    retained = singular_values > threshold
    rank = int(np.count_nonzero(retained))
    if rank == 0:
        raise ValueError("economical Gamma pairing has zero machine rank")
    kept = singular_values[retained]
    discarded = singular_values[~retained]
    return np.ascontiguousarray(left[:, :rank]), {
        "candidate_count": int(rhs.shape[1]),
        "retained_rank": rank,
        "discarded_count": int(len(discarded)),
        "sigma_max": sigma_max,
        "machine_rank_threshold": threshold,
        "smallest_retained_singular_value": float(np.min(kept)),
        "largest_discarded_singular_value": (
            float(np.max(discarded)) if len(discarded) else None
        ),
        "singular_gap": (
            float(np.min(kept) - np.max(discarded)) if len(discarded) else None
        ),
    }


def _patch_rhs(
    function_space: Any,
    condensed: Any,
    mass_provider: ActualHcurlCellTangentialMassProvider,
    cell: int,
    excluded_facets: set[int],
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    raw_rows, active_rows, expansion = build_cell_active_trace_expansion(
        condensed,
        int(cell),
    )
    oriented_coefficients, trace_positions, interpolation_audit = (
        _oriented_vsh_coefficients(function_space, condensed, int(cell))
    )
    lambda_raw = oriented_coefficients[trace_positions]
    connectivity = function_space.mesh.topology.connectivity(
        function_space.mesh.topology.dim,
        function_space.mesh.topology.dim - 1,
    )
    expected_facets = tuple(int(value) for value in connectivity.links(int(cell)))
    blocks = tuple(mass_provider.stream_facet_trace_blocks(int(cell)))
    if tuple(int(item[0]) for item in blocks) != tuple(range(6)):
        raise ValueError("economical provider did not return six local facets")
    if tuple(int(item[1]) for item in blocks) != expected_facets:
        raise ValueError("economical provider facet entities differ from topology")
    gamma_raw = np.zeros((len(raw_rows), len(raw_rows)), dtype=np.complex128)
    gamma_facets: list[int] = []
    for _local_facet, mesh_facet, block in blocks:
        block = np.asarray(block, dtype=np.complex128)
        if block.shape != gamma_raw.shape or not np.all(np.isfinite(block)):
            raise ValueError("economical Gamma facet block has invalid shape/value")
        if int(mesh_facet) not in excluded_facets:
            gamma_raw += block
            gamma_facets.append(int(mesh_facet))
    rhs = np.asarray(expansion.conj().T @ gamma_raw @ lambda_raw, dtype=np.complex128)
    range_rhs, rank_audit = _machine_range(rhs)
    return range_rhs, active_rows, {
        **interpolation_audit,
        **rank_audit,
        "raw_trace_rows": int(len(raw_rows)),
        "active_trace_rows": int(len(active_rows)),
        "gamma_facets": tuple(sorted(gamma_facets)),
        "gamma_facet_count": len(gamma_facets),
        "gamma_pairing": "expansion.conj().T @ M_Gamma_raw @ lambda_raw",
        "lambda_source": "oriented_Nedelec_cell_interpolation",
        "local_impedance_source": "existing_stage_a_patch_matrix",
        "pc_only_shift_in_energy_metric": False,
    }


def _sync_error(comm: MPI.Intracomm, local_error: str | None, stage: str) -> None:
    errors = comm.allgather(local_error)
    if any(error is not None for error in errors):
        first = next(error for error in errors if error is not None)
        raise RuntimeError(f"economical {stage} failed: {first}")


def prepare_economical_gamma_rhs(
    function_space: Any,
    condensed: Any,
    mass_provider: Any,
    facet_tags: Any,
    external_facet_tag: int,
) -> EconomicalGammaRhsPreparation:
    """Prepare origin-local Gamma RHS columns before constructing the action."""

    comm = function_space.mesh.comm
    local_records: list[EconomicalPreparedPatch] = []
    try:
        if not isinstance(mass_provider, ActualHcurlCellTangentialMassProvider):
            raise TypeError("economical route requires the exact actual H(curl) provider")
        if not hasattr(facet_tags, "find"):
            raise TypeError("economical route requires mesh facet tags")
        provider_before = mass_provider.collective_audit()
        if (
            provider_before.get("numeric_cache_released") is not False
            or provider_before.get("destroyed") is True
            or provider_before.get("served_cell_count_global") != 0
        ):
            raise RuntimeError("economical preparation requires a fresh live provider")
        topology = function_space.mesh.topology
        topology.create_connectivity(topology.dim, topology.dim - 1)
        excluded_facets = {
            int(value) for value in facet_tags.find(int(external_facet_tag))
        }
        owned_cells = int(topology.index_map(topology.dim).size_local)
        local_error: str | None = None
        for cell in range(owned_cells):
            try:
                rhs, active_rows, audit = _patch_rhs(
                    function_space,
                    condensed,
                    mass_provider,
                    int(cell),
                    excluded_facets,
                )
                patch_id = (int(comm.rank), int(cell))
                local_records.append(
                    EconomicalPreparedPatch(
                        patch_id=patch_id,
                        cell_index=int(cell),
                        rows=tuple(int(value) for value in active_rows),
                        rhs=np.ascontiguousarray(rhs.copy()),
                        audit={
                            **audit,
                            "patch_id": patch_id,
                            "cell_index": int(cell),
                            "prepared_rhs_released": False,
                        },
                    )
                )
            except Exception as exc:
                local_error = f"{type(exc).__name__}: {exc}"
                break
        _sync_error(comm, local_error, "Gamma RHS preparation")
        global_patch_count = int(comm.allreduce(owned_cells, MPI.SUM))
        if global_patch_count <= 0:
            raise RuntimeError("economical preparation found no owned cell patches")
        compact_local = tuple(
            (record.patch_id, record.cell_index, record.rows)
            for record in local_records
        )
        packets = comm.allgather(compact_local)
        global_metadata = tuple(
            sorted(
                (item for packet in packets for item in packet),
                key=lambda item: item[0],
            )
        )
        if len({item[0] for item in global_metadata}) != len(global_metadata):
            raise RuntimeError("economical preparation contains duplicate patch IDs")
        provider_after = mass_provider.collective_audit()
        if (
            provider_after.get("status") != "verified_exact_provider"
            or provider_after.get("numeric_cache_released") is not False
        ):
            raise RuntimeError(
                "economical preparation provider audit is not verified and unreleased"
            )
        diagnostics = {
            "schema": "task040.v8.economical_gamma_rhs_preparation.v1",
            "method": "paper_economical_vector_spherical_harmonics",
            "global_patch_count": len(global_metadata),
            "local_patch_count": len(local_records),
            "global_patch_metadata": global_metadata,
            "provider_audit_preparation": provider_after,
            "provider_audit_preparation_state": "verified_but_not_released",
            "prepared_rhs_live": True,
            "prepared_rhs_released": False,
            "prepared_rhs_consumed": False,
            "prepared_rhs_destroyed": False,
            "harmonic_multi_rhs_solve_count": 0,
        }
        return EconomicalGammaRhsPreparation(
            tuple(local_records),
            global_metadata,
            comm,
            diagnostics,
        )
    except Exception:
        for record in local_records:
            record.rhs = None
        raise


def solve_prepared_economical_columns(
    preparation: EconomicalGammaRhsPreparation,
    action: Any,
    provider_audit_after_action: Mapping[str, Any],
) -> EconomicalMaxwellHarmonicSpace:
    """Consume prepared RHS columns through the already-built live action."""

    comm = preparation.comm
    if preparation._destroyed:
        raise RuntimeError("economical prepared RHS has been destroyed")
    if preparation._consumed:
        raise RuntimeError("economical prepared RHS has already been consumed")
    preparation._consumed = True
    preparation.diagnostics["prepared_rhs_consumed"] = True
    local_records: list[EconomicalPatchRecord] = []
    try:
        local_error: str | None = None
        try:
            if not isinstance(provider_audit_after_action, Mapping):
                raise TypeError("economical post-action provider audit must be a mapping")
            if (
                provider_audit_after_action.get("status") != "verified_exact_provider"
                or provider_audit_after_action.get("numeric_cache_released") is not True
                or provider_audit_after_action.get("raw_cache_size_local") != 0
                or provider_audit_after_action.get("oriented_numeric_cache_size_local")
                != 0
            ):
                raise RuntimeError("economical post-action provider audit is incomplete")
            if not hasattr(action, "patch_metadata") or not hasattr(
                action, "solve_patch_multi_rhs"
            ):
                raise TypeError("economical route requires the bounded patch solve API")
        except Exception as exc:
            local_error = f"{type(exc).__name__}: {exc}"
        _sync_error(comm, local_error, "post-action preparation validation")

        local_action: dict[tuple[int, int], dict[str, Any]] = {}
        compact_local: list[tuple[Any, ...]] = []
        local_error = None
        try:
            for item in action.patch_metadata():
                patch_id = tuple(int(value) for value in item["patch_id"])
                rows = tuple(int(value) for value in item["rows"])
                weights = np.asarray(item["weights"], dtype=np.float64)
                if weights.shape != (len(rows),) or not np.all(np.isfinite(weights)):
                    raise ValueError("economical local PoU metadata is invalid")
                local_action[patch_id] = {
                    "cell_index": int(item["cell_index"]),
                    "rows": rows,
                    "weights": weights.copy(),
                    "class_key": str(item["class_key"]),
                    "owner_rank": int(item["owner_rank"]),
                }
                compact_local.append(
                    (
                        patch_id,
                        int(item["cell_index"]),
                        rows,
                        str(item["class_key"]),
                        int(item["owner_rank"]),
                    )
                )
        except Exception as exc:
            local_error = f"{type(exc).__name__}: {exc}"
        _sync_error(comm, local_error, "action metadata validation")
        packets = comm.allgather(tuple(compact_local))
        observed = tuple(
            sorted(
                (item for packet in packets for item in packet),
                key=lambda item: item[0],
            )
        )
        expected = tuple(preparation.global_patch_metadata)
        observed_shape = tuple((item[0], item[1], item[2]) for item in observed)
        if observed_shape != expected:
            raise RuntimeError("action patch metadata differs from prepared cells/rows")
        prepared_by_id = {
            record.patch_id: record for record in preparation.local_patch_records
        }
        for patch_id, cell, rows, class_key, owner_rank in observed:
            origin = int(patch_id[0])
            rhs = None
            local_error = None
            if comm.rank == origin:
                try:
                    prepared = prepared_by_id.get(tuple(patch_id))
                    metadata = local_action.get(tuple(patch_id))
                    if prepared is None or metadata is None:
                        raise RuntimeError("economical patch origin lacks prepared data")
                    if (
                        int(prepared.cell_index) != int(cell)
                        or tuple(prepared.rows) != tuple(rows)
                    ):
                        raise RuntimeError("prepared patch rows differ from action metadata")
                    if prepared.rhs is None:
                        raise RuntimeError("economical prepared RHS is already released")
                    rhs = prepared.rhs
                except Exception as exc:
                    local_error = f"{type(exc).__name__}: {exc}"
            _sync_error(comm, local_error, "prepared patch RHS validation")
            solution, ratios = action.solve_patch_multi_rhs(
                tuple(patch_id),
                str(class_key),
                int(owner_rank),
                rhs,
            )
            local_error = None
            if comm.rank == origin:
                try:
                    prepared = prepared_by_id[tuple(patch_id)]
                    metadata = local_action[tuple(patch_id)]
                    values = np.asarray(solution, dtype=PETSc.ScalarType)
                    if values.ndim != 2 or values.shape[0] != len(rows):
                        raise ValueError("economical harmonic solution has the wrong shape")
                    if not np.all(np.isfinite(values)):
                        raise ValueError("economical harmonic solution is non-finite")
                    ratio_values = tuple(float(value) for value in ratios or ())
                    if len(ratio_values) != values.shape[1] or not all(
                        np.isfinite(value) and value >= 0.0 for value in ratio_values
                    ):
                        raise ValueError("economical harmonic residual audit is invalid")
                    solve_residual = max(ratio_values, default=0.0)
                    if solve_residual > IDENTITY_GATE:
                        raise ValueError("economical harmonic solve accuracy gate failed")
                    audit = {
                        **prepared.audit,
                        "harmonic_solve_residual_max": solve_residual,
                        "harmonic_solve_residual_count": len(ratio_values),
                        "harmonic_solve_accuracy_gate": IDENTITY_GATE,
                        "prepared_rhs_released": True,
                        "solve_call_count": 1,
                        "selected_definition": "machine_rank_range_of_C^H_M_Gamma_lambda_raw",
                        "generalized_eigenproblem": False,
                        "global_prolongation_created": False,
                        "coarse_matrix_created": False,
                        "class_key": str(class_key),
                    }
                    local_records.append(
                        EconomicalPatchRecord(
                            patch_id=tuple(patch_id),
                            cell_index=int(cell),
                            rows=tuple(rows),
                            weights=np.asarray(metadata["weights"]).copy(),
                            columns=np.ascontiguousarray(values.copy()),
                            audit=audit,
                        )
                    )
                    prepared.rhs = None
                    prepared.audit["prepared_rhs_released"] = True
                except Exception as exc:
                    local_error = f"{type(exc).__name__}: {exc}"
            _sync_error(comm, local_error, "prepared patch harmonic solve")
        action_diagnostics = action.diagnostics
        solve_count = int(action_diagnostics["harmonic_multi_rhs_solve_count"])
        global_patch_count = len(expected)
        local_error = (
            None
            if solve_count == global_patch_count
            else f"harmonic solve count {solve_count} != patch count {global_patch_count}"
        )
        _sync_error(comm, local_error, "harmonic solve count")
        preparation.diagnostics.update(
            {
                "prepared_rhs_live": False,
                "prepared_rhs_released": True,
                "prepared_rhs_consumed": True,
                "harmonic_multi_rhs_solve_count": solve_count,
                "provider_audit_after_action": dict(provider_audit_after_action),
                "provider_audit_after_action_state": (
                    "verified_released_cache_empty"
                ),
            }
        )
        local_rank_total = sum(
            int(record.audit["retained_rank"]) for record in local_records
        )
        diagnostics = {
            "schema": "task040.v8.economical_maxwell_harmonic.v1",
            "method": "paper_economical_vector_spherical_harmonics",
            "paper_dimensionless_kappa": PAPER_DIMENSIONLESS_KAPPA,
            "paper_beta": PAPER_BETA,
            "paper_linear_p": PAPER_LINEAR_P,
            "paper_rho": PAPER_RHO,
            "paper_rho2": PAPER_RHO2,
            "mu_raw": PAPER_MU_RAW,
            "mu": PAPER_MU,
            "candidate_count_per_patch": PAPER_CANDIDATE_COUNT,
            "discrete_k0_separate": DISCRETE_K0,
            "global_patch_count": global_patch_count,
            "global_retained_rank": int(comm.allreduce(local_rank_total, MPI.SUM)),
            "local_patch_count": len(local_records),
            "owner_local_numeric_columns": True,
            "numeric_collective_type": "existing_bounded_patch_multi_rhs",
            "full_vector_numeric_allgather": False,
            "generalized_eigenproblem": False,
            "global_prolongation_created": False,
            "coarse_matrix_created": False,
            "outer_fgmres_run": False,
            "harmonic_multi_rhs_solve_count": solve_count,
            "exact_provider_audit": dict(provider_audit_after_action),
            "exact_provider_audit_preparation": preparation.diagnostics[
                "provider_audit_preparation"
            ],
            "patch_audits_local": [record.audit for record in local_records],
            "prepared_rhs_released": all(
                record.rhs is None
                for record in preparation.local_patch_records
            ),
        }
        return EconomicalMaxwellHarmonicSpace(tuple(local_records), diagnostics)
    except Exception:
        preparation._consumed = True
        for record in preparation.local_patch_records:
            record.rhs = None
            record.audit["prepared_rhs_released"] = True
        preparation.diagnostics.update(
            {
                "prepared_rhs_live": False,
                "prepared_rhs_released": True,
                "prepared_rhs_consumed": True,
            }
        )
        raise
