"""Generic 2D cross-section QEP infrastructure for Task032 references.

The current shift-invert MUMPS path is validated at the Task032 13.5 nm scale.
Requesting all target modes this way is experimental and is not scalable to the
0.7 nm service target without distributed spectrum slicing or continuation.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np
import ufl
from dolfinx import fem
from dolfinx.fem import petsc as fem_petsc
from petsc4py import PETSc
from slepc4py import SLEPc

from ..common.config_3d import SimulationConfig3D
from ..common.high_order_quadrature import high_order_quadrature_policy
from ..constraints.cross_section_floquet import (
    CrossSectionFloquetConstraints,
    DistributedConstraintTransform,
    build_cross_section_floquet_constraints,
    build_distributed_constraint_transform,
    reduce_matrix_hermitian,
)
from .cross_section_spaces import CrossSectionMesh, CrossSectionSpaces


@dataclass(frozen=True)
class QuadraticBetaOperators:
    """Distributed sparse coefficients of ``K0 + beta K1 + beta^2 K2``."""

    K0: PETSc.Mat
    K1: PETSc.Mat
    K2: PETSc.Mat
    electric_mass: PETSc.Mat
    transform: DistributedConstraintTransform
    constraints: CrossSectionFloquetConstraints
    full_shape: tuple[int, int]
    reduced_shape: tuple[int, int]
    scalar_dtype: str
    field_degree: int
    geometry_degree: int
    coefficient_degree: int
    quadrature_degree: int
    quadrature_policy: str = "2p_plus_2g_plus_c_plus_2"
    formulation: str = "mixed_transverse_N1curl_longitudinal_Lagrange_QEP"
    polynomial_order: int = 2
    leading_coefficient_singular_by_design: bool = True

    def destroy(self) -> None:
        self.K0.destroy()
        self.K1.destroy()
        self.K2.destroy()
        self.electric_mass.destroy()
        self.transform.matrix.destroy()


@dataclass(frozen=True)
class EigenvectorOwnership:
    comm_size: int
    reduced_local_size: int
    reduced_ownership_range: tuple[int, int]
    full_local_size: int
    full_ownership_range: tuple[int, int]
    gathered_to_root: bool = False


@dataclass
class QuadraticBetaMode:
    beta: complex
    right_reduced: PETSc.Vec
    right_full: PETSc.Vec
    polynomial_relative_residual: float
    slepc_relative_error: float
    normalization_kind: str
    normalization_factor: float
    electric_l2_norm_after: float
    ownership: EigenvectorOwnership

    def destroy(self) -> None:
        self.right_reduced.destroy()
        self.right_full.destroy()


@dataclass(frozen=True)
class QuadraticBetaSolveReport:
    solver: str
    problem_type: str
    spectral_transform: str
    target: complex
    requested_modes: int
    converged_modes: int
    iteration_count: int
    convergence_reason: int


def analytic_homogeneous_beta(
    cfg: SimulationConfig3D,
    refractive_index: complex,
    *,
    order_m: int = 0,
    order_n: int = 0,
) -> complex:
    """Return the principal ``+z`` branch for one homogeneous Floquet order."""

    kx_order = complex(cfg.kx) + 2.0 * np.pi * order_m / cfg.period_x
    ky_order = complex(cfg.ky) + 2.0 * np.pi * order_n / cfg.period_y
    beta = complex(
        np.sqrt(
            (cfg.k0 * complex(refractive_index)) ** 2
            - kx_order**2
            - ky_order**2
            + 0j
        )
    )
    # Principal sqrt already has Im(beta)>=0.  At the real-axis branch choose
    # positive phase propagation for the explicitly named +z reference.
    if beta.imag < -1.0e-14 or (
        abs(beta.imag) <= 1.0e-14 and beta.real < 0.0
    ):
        beta = -beta
    return beta


def qep_quadrature_degree(
    *,
    field_degree: int,
    geometry_degree: int,
    coefficient_degree: int,
) -> int:
    """Return the conservative planar high-order QEP quadrature degree.

    The extra two orders preserve the reviewed p=2 value of eight on the
    current linear-geometry, piecewise-constant-material meshes while making
    the p=3/p=4 policy explicit.  Curved production geometry remains outside
    Task033 and must be qualified separately rather than relying on this
    polynomial rule alone.
    """

    return high_order_quadrature_policy(
        field_degree=field_degree,
        geometry_degree=geometry_degree,
        coefficient_degree=coefficient_degree,
    ).selected_degree


def _qep_degree_context(
    cross_section: CrossSectionMesh,
    spaces: CrossSectionSpaces,
    requested_quadrature_degree: int | None,
) -> dict[str, int]:
    field_degree = max(
        int(spaces.transverse_degree), int(spaces.longitudinal_degree)
    )
    geometry_degree = int(getattr(cross_section.mesh.geometry.cmap, "degree", 1))
    coefficient_degree = int(
        getattr(
            cross_section.epsilon_r.function_space.element.basix_element,
            "degree",
            0,
        )
    )
    recommended = qep_quadrature_degree(
        field_degree=field_degree,
        geometry_degree=geometry_degree,
        coefficient_degree=coefficient_degree,
    )
    selected = (
        recommended
        if requested_quadrature_degree is None
        else int(requested_quadrature_degree)
    )
    if selected < recommended:
        raise ValueError(
            "QEP quadrature degree cannot be lower than the Task033 policy: "
            f"requested={selected}, recommended={recommended}."
        )
    return {
        "field_degree": field_degree,
        "geometry_degree": geometry_degree,
        "coefficient_degree": coefficient_degree,
        "recommended_quadrature_degree": recommended,
        "quadrature_degree": selected,
    }


def _task42_array_basis(value: Any, label: str) -> dict[str, Any]:
    """Describe an existing contiguous numeric array without copying its bytes."""

    raw = getattr(value, "array", value)
    array = np.asarray(raw)
    if array.dtype.kind == "O" or not array.flags.c_contiguous:
        raise ValueError(f"Task42 K0 basis array {label} is not contiguous numeric data")
    return {
        "shape": [int(size) for size in array.shape],
        "dtype": array.dtype.str,
        "itemsize_bytes": int(array.dtype.itemsize),
        "count": int(array.size),
        "sha256": hashlib.sha256(memoryview(array).cast("B")).hexdigest(),
    }


def _task42_index_map_basis(
    index_map: Any,
    label: str,
    *,
    mpi_size: int,
    max_local_to_global_entries: int,
) -> tuple[dict[str, Any], np.ndarray, int]:
    local_range = getattr(index_map, "local_range", None)
    if callable(local_range):
        local_range = local_range()
    if not isinstance(local_range, (tuple, list)) or len(local_range) != 2:
        raise ValueError(f"Task42 K0 basis {label} lacks its owned range")
    size_local = int(index_map.size_local)
    num_ghosts = int(index_map.num_ghosts)
    size_global = int(index_map.size_global)
    owned_start, owned_end = int(local_range[0]), int(local_range[1])
    if (
        owned_start < 0
        or owned_end < owned_start
        or owned_end - owned_start != size_local
        or owned_end > size_global
        or num_ghosts < 0
    ):
        raise ValueError(f"Task42 K0 basis {label} has an invalid owned range")
    local_entry_count = size_local + num_ghosts
    if (
        max_local_to_global_entries <= 0
        or size_global > max_local_to_global_entries
        or local_entry_count > max_local_to_global_entries
    ):
        raise ValueError(
            f"Task42 K0 basis {label} local-to-global map exceeds the "
            f"calibrated {max_local_to_global_entries}-entry profile"
        )
    local_to_global = getattr(index_map, "local_to_global", None)
    if not callable(local_to_global):
        raise TypeError(f"Task42 K0 basis {label} lacks local_to_global")
    local_indices = np.arange(size_local + num_ghosts, dtype=np.int32)
    global_ids = np.asarray(local_to_global(local_indices))
    if (
        global_ids.shape != local_indices.shape
        or global_ids.dtype.kind not in "iu"
        or not global_ids.flags.c_contiguous
        or np.any(global_ids < 0)
        or np.any(global_ids >= size_global)
    ):
        raise ValueError(
            f"Task42 K0 basis {label} local_to_global has an invalid shape or dtype"
        )
    owners = getattr(index_map, "owners", None)
    if callable(owners):
        owners = owners()
    owners_array = np.asarray(owners) if owners is not None else None
    if (
        owners_array is None
        or owners_array.shape != (num_ghosts,)
        or owners_array.dtype.kind not in "iu"
        or (owners_array.size and np.any(owners_array < 0))
        or (owners_array.size and np.any(owners_array >= mpi_size))
    ):
        raise ValueError(f"Task42 K0 basis {label} lacks ghost-owner data")
    if any(
        int(global_ids[index]) != owned_start + index
        for index in range(size_local)
    ):
        raise ValueError(
            f"Task42 K0 basis {label} owned local-to-global IDs differ from its range"
        )
    local_to_global_basis = _task42_array_basis(
        global_ids, f"{label}.local_to_global"
    )
    local_to_global_basis.update(
        {
            "owned_count": size_local,
            "owned_global_ids_sha256": hashlib.sha256(
                memoryview(global_ids[:size_local]).cast("B")
            ).hexdigest(),
            "ghost_count": num_ghosts,
            "ghost_global_ids_sha256": hashlib.sha256(
                memoryview(global_ids[size_local:]).cast("B")
            ).hexdigest(),
        }
    )
    # NumPy comparisons used by the validation predicates allocate one
    # temporary boolean mask at a time. Include the largest mask below.
    comparison_mask_bytes = max(
        int(global_ids.size), int(owners_array.size)
    ) * int(np.dtype(np.bool_).itemsize)
    result = {
        "size_local": size_local,
        "num_ghosts": num_ghosts,
        "size_global": size_global,
        "max_local_to_global_entries": int(max_local_to_global_entries),
        "local_range": [owned_start, owned_end],
        "local_to_global": local_to_global_basis,
        "local_to_global_index_temporary_bytes": int(
            local_indices.nbytes + global_ids.nbytes
        ),
        "comparison_mask_temporary_bytes_upper": int(comparison_mask_bytes),
        "ghost_owners": _task42_array_basis(owners_array, f"{label}.owners"),
    }
    temporary_bytes = int(
        local_indices.nbytes
        + global_ids.nbytes
        + owners_array.nbytes
        + comparison_mask_bytes
    )
    # The caller uses this live mapping to classify cell candidates and then
    # releases it. Its input/output allocation is included in the returned
    # temporary-byte count.
    del local_indices
    return result, global_ids, temporary_bytes


def _task42_cell_dof_layout(
    dofmap: Any,
    label: str,
    *,
    local_cell_count: int,
) -> tuple[np.ndarray, np.ndarray, list[int], int, dict[str, Any]]:
    """Read owned and ghost cell rows through DOLFINx's public DofMap API."""

    if type(local_cell_count) is not int or local_cell_count < 0:
        raise ValueError(
            f"Task42 K0 basis {label} has invalid owned+ghost cell count"
        )
    cell_dofs_reader = getattr(dofmap, "cell_dofs", None)
    if not callable(cell_dofs_reader):
        raise TypeError(
            f"Task42 K0 basis {label} lacks public cell_dofs(cell_index)"
        )

    pet_int_dtype = np.dtype(PETSc.IntType)
    row_lengths = np.empty(local_cell_count, dtype=np.int64)
    maximum_returned_row_bytes = 0
    returned_types: set[str] = set()
    for cell_index in range(local_cell_count):
        try:
            raw_row = cell_dofs_reader(cell_index)
            returned_types.add(
                f"{type(raw_row).__module__}.{type(raw_row).__qualname__}"
            )
            row = np.asarray(raw_row)
        except Exception as exc:
            raise ValueError(
                f"Task42 K0 basis {label} public cell_dofs({cell_index}) failed: "
                f"{type(exc).__name__}: {exc}"
            ) from exc
        if row.ndim != 1 or row.dtype.kind not in "iu" or row.dtype != pet_int_dtype:
            raise ValueError(
                f"Task42 K0 basis {label} public cell_dofs({cell_index}) must return "
                f"a 1D {pet_int_dtype} integer row; got shape={row.shape}, "
                f"dtype={row.dtype}"
            )
        row_lengths[cell_index] = int(row.size)
        maximum_returned_row_bytes = max(
            maximum_returned_row_bytes, int(row.nbytes)
        )

    offsets = np.empty(local_cell_count + 1, dtype=np.int64)
    offsets[0] = 0
    for cell_index, row_length in enumerate(row_lengths):
        next_offset = int(offsets[cell_index]) + int(row_length)
        if next_offset > np.iinfo(offsets.dtype).max:
            raise ValueError(
                f"Task42 K0 basis {label} cell-dof offsets overflow int64"
            )
        offsets[cell_index + 1] = next_offset

    cell_dofs = np.empty(int(offsets[-1]), dtype=pet_int_dtype)
    for cell_index in range(local_cell_count):
        try:
            raw_row = cell_dofs_reader(cell_index)
            return_type = f"{type(raw_row).__module__}.{type(raw_row).__qualname__}"
            if return_type not in returned_types:
                raise ValueError(
                    f"Task42 K0 basis {label} public cell_dofs({cell_index}) "
                    "changed return type during normalization"
                )
            row = np.asarray(raw_row)
        except Exception as exc:
            raise ValueError(
                f"Task42 K0 basis {label} public cell_dofs({cell_index}) changed "
                f"during normalization: {type(exc).__name__}: {exc}"
            ) from exc
        expected_length = int(row_lengths[cell_index])
        if (
            row.ndim != 1
            or row.dtype != pet_int_dtype
            or row.size != expected_length
        ):
            raise ValueError(
                f"Task42 K0 basis {label} public cell_dofs({cell_index}) changed "
                "shape or integer ABI during normalization"
            )
        begin = int(offsets[cell_index])
        end = int(offsets[cell_index + 1])
        cell_dofs[begin:end] = row

    cell_rows = [int(value) for value in row_lengths]
    normalization_peak_bytes = int(
        row_lengths.nbytes
        + offsets.nbytes
        + cell_dofs.nbytes
        + maximum_returned_row_bytes
    )
    source = {
        "api": "DofMap.cell_dofs(cell_index)",
        "dofmap_type": f"{type(dofmap).__module__}.{type(dofmap).__qualname__}",
        "returned_row_types": sorted(returned_types),
        "row_dimensions": 1,
        "row_count": local_cell_count,
        "offsets_derived_from_actual_row_lengths": True,
        "normalized_value_dtype": pet_int_dtype.str,
        "offset_dtype": offsets.dtype.str,
    }
    return cell_dofs, offsets, cell_rows, normalization_peak_bytes, source


def _task42_space_basis(
    space: Any,
    label: str,
    *,
    local_cell_count: int,
    owned_cell_count: int,
    global_cell_count: int,
    mpi_size: int,
    max_global_dofs: int,
    scalar_bytes: int,
    count_matrix_candidates: bool = False,
) -> tuple[dict[str, Any], dict[str, Any], int]:
    dofmap = space.dofmap
    (
        cell_dofs,
        offsets,
        cell_rows,
        cell_dof_layout_normalization_peak_bytes,
        cell_dof_layout_source,
    ) = _task42_cell_dof_layout(
        dofmap,
        label,
        local_cell_count=local_cell_count,
    )
    index_map = dofmap.index_map
    if owned_cell_count < 0 or owned_cell_count > local_cell_count:
        raise ValueError(f"Task42 K0 basis {label} has invalid owned-cell count")
    if global_cell_count < 0:
        raise ValueError(f"Task42 K0 basis {label} has invalid global-cell count")
    index_map_basis, local_to_global_ids, index_map_temporary_bytes = (
        _task42_index_map_basis(
            index_map,
            f"{label}.index_map",
            mpi_size=mpi_size,
            max_local_to_global_entries=max_global_dofs,
        )
    )
    if cell_dofs.size and (
        int(cell_dofs.min()) < 0
        or int(cell_dofs.max()) >= local_to_global_ids.size
    ):
        raise ValueError(
            f"Task42 K0 basis {label} cell dof is outside local-to-global map"
        )
    block_size = int(getattr(dofmap, "index_map_bs", 1))
    summary: dict[str, Any] = {
        "owned_cell_count": int(owned_cell_count),
        "ghost_cell_count": int(local_cell_count - owned_cell_count),
        "owned_cell_dof_rows": cell_rows[:owned_cell_count],
        "ghost_cell_dof_rows": cell_rows[owned_cell_count:],
        "owned_cell_candidate_pair_contributions": int(
            sum(rows * rows for rows in cell_rows[:owned_cell_count])
        ),
    }
    if count_matrix_candidates:
        if block_size != 1:
            raise ValueError(
                "Task42 K0 calibrated mixed layout requires scalar dofmap block size 1"
            )
        owned_start, owned_end = index_map_basis["local_range"]
        diagonal_pairs = 0
        offdiagonal_pairs = 0
        remote_row_stash_pairs = 0
        for cell in range(owned_cell_count):
            begin, end = int(offsets[cell]), int(offsets[cell + 1])
            row_count = end - begin
            owned_dofs = 0
            for local_index_value in cell_dofs[begin:end]:
                local_index = int(local_index_value)
                if local_index < 0 or local_index >= local_to_global_ids.size:
                    raise ValueError(
                        f"Task42 K0 basis {label} cell dof is outside local-to-global map"
                    )
                global_index = int(local_to_global_ids[local_index])
                owned_dofs += int(owned_start <= global_index < owned_end)
            remote_dofs = row_count - owned_dofs
            diagonal_pairs += owned_dofs * owned_dofs
            offdiagonal_pairs += owned_dofs * remote_dofs
            remote_row_stash_pairs += remote_dofs * row_count
        total_pairs = int(summary["owned_cell_candidate_pair_contributions"])
        if diagonal_pairs + offdiagonal_pairs + remote_row_stash_pairs != total_pairs:
            raise ValueError(
                f"Task42 K0 basis {label} candidate-pair ownership did not close"
            )
        pet_int_bytes = int(np.dtype(PETSc.IntType).itemsize)
        diagonal_bytes = diagonal_pairs * (scalar_bytes + pet_int_bytes)
        offdiagonal_bytes = offdiagonal_pairs * (scalar_bytes + pet_int_bytes)
        row_pointer_bytes = 2 * (index_map_basis["size_local"] * block_size + 1) * pet_int_bytes
        garray_bytes_upper = offdiagonal_pairs * pet_int_bytes
        stash_bytes_upper = remote_row_stash_pairs * (
            scalar_bytes + 2 * pet_int_bytes
        )
        global_candidate_pairs = int(
            global_cell_count * max(cell_rows, default=0) ** 2
        )
        global_rows = int(index_map_basis["size_global"] * block_size)
        global_aij_values_and_columns_bytes = global_candidate_pairs * (
            scalar_bytes + pet_int_bytes
        )
        global_two_block_row_pointer_bytes = (
            2 * (index_map_basis["size_local"] * block_size + 1) * pet_int_bytes
        )
        global_garray_bytes = global_rows * pet_int_bytes
        global_remote_stash_bytes = global_candidate_pairs * (
            scalar_bytes + 2 * pet_int_bytes
        )
        summary["matrix_candidate_contributions"] = {
            "owned_cell_candidate_pair_contributions_local": total_pairs,
            "diagonal_entries": int(diagonal_pairs),
            "offdiagonal_entries": int(offdiagonal_pairs),
            "remote_row_stash_entries": int(remote_row_stash_pairs),
            "diagonal_payload_bytes_upper": int(diagonal_bytes),
            "offdiagonal_payload_bytes_upper": int(offdiagonal_bytes),
            "two_MPIAIJ_row_pointer_bytes": int(row_pointer_bytes),
            "remote_column_garray_bytes_upper": int(garray_bytes_upper),
            "remote_row_stash_triplet_bytes_upper": int(stash_bytes_upper),
            "local_candidate_sparse_payload_bytes_upper": int(
                diagonal_bytes
                + offdiagonal_bytes
                + row_pointer_bytes
                + garray_bytes_upper
                + stash_bytes_upper
            ),
            "local_contribution_classification": (
                "local owned-cell contributions only; excludes contributions received "
                "from other ranks and is not a final per-rank AIJ capacity bound"
            ),
            "global_cell_candidate_pair_contribution_bound": global_candidate_pairs,
            "global_cell_count_used": int(global_cell_count),
            "max_cell_dof_rows_used": int(max(cell_rows, default=0)),
            "per_rank_aij_values_and_column_indices_bytes_upper": int(
                global_aij_values_and_columns_bytes
            ),
            "per_rank_two_mpiaij_row_pointer_bytes_upper": int(
                global_two_block_row_pointer_bytes
            ),
            "per_rank_remote_column_garray_bytes_upper": int(global_garray_bytes),
            "per_rank_remote_row_stash_triplet_bytes_upper": int(
                global_remote_stash_bytes
            ),
            "candidate_sparse_payload_bytes_upper": int(
                global_aij_values_and_columns_bytes
                + global_two_block_row_pointer_bytes
                + global_garray_bytes
                + global_remote_stash_bytes
            ),
            "classification": (
                "global all-cell contribution bound applied conservatively to each "
                "rank's AIJ payload and remote stash; source-derived estimate, not "
                "MatInfo NNZ or a proven allocated-capacity bound"
            ),
        }
    local_tensor_bytes = int(
        summary["owned_cell_candidate_pair_contributions"] * scalar_bytes
    )
    summary["local_cell_tensor_payload_bytes"] = local_tensor_bytes
    summary["largest_single_cell_tensor_payload_bytes"] = int(
        max((rows * rows * scalar_bytes for rows in cell_rows[:owned_cell_count]), default=0)
    )
    summary["cell_dof_rows_python_metadata_bytes_upper"] = int(
        64 * (len(cell_rows) + 1)
    )
    summary["cell_dof_layout_normalization_peak_bytes"] = int(
        cell_dof_layout_normalization_peak_bytes
    )
    summary["cell_dof_layout_payload_bytes"] = int(
        cell_dofs.nbytes + offsets.nbytes
    )
    summary["cell_dof_layout_source"] = cell_dof_layout_source
    summary["source_basis_validation_scratch_peak_bytes"] = int(
        max(
            cell_dof_layout_normalization_peak_bytes,
            index_map_temporary_bytes + cell_dofs.nbytes + offsets.nbytes,
        )
    )
    basis = {
        "index_map": index_map_basis,
        "index_map_bs": block_size,
        "cell_dofmap": _task42_array_basis(cell_dofs, f"{label}.cell_dofmap"),
        "cell_dof_offsets": _task42_array_basis(offsets, f"{label}.cell_dof_offsets"),
        "cell_dof_rows": summary,
    }
    del local_to_global_ids
    return basis, summary, index_map_temporary_bytes


_TASK42_K0_IDENTITY_SHA_FIELDS = (
    "input_sha256",
    "physical_model_sha256",
    "resolved_config_sha256",
    "material_identity_sha256",
    "material_record_sha256",
)


def _task42_complex_pair(value: Any, label: str) -> list[float]:
    number = complex(value)
    pair = [float(number.real), float(number.imag)]
    if not all(np.isfinite(item) for item in pair):
        raise ValueError(f"Task42 K0 basis {label} is nonfinite")
    return pair


def _task42_k0_source_basis(
    cfg: SimulationConfig3D,
    cross_section: CrossSectionMesh,
    spaces: CrossSectionSpaces,
    degree_context: Mapping[str, int],
    task42_sizing_identity: Mapping[str, Any] | None,
    *,
    rank: int,
    mpi_size: int,
    compiled_form: Any | None = None,
) -> dict[str, Any]:
    if not isinstance(task42_sizing_identity, Mapping):
        raise TypeError("Task42 K0 sizing identity is missing")
    identity: dict[str, str] = {}
    for key in (
        "model_id",
        "run_id",
        "comparison_group",
        "canonical_export_prefix",
        *_TASK42_K0_IDENTITY_SHA_FIELDS,
        "source_sha",
    ):
        value = task42_sizing_identity.get(key)
        if not isinstance(value, str) or not value:
            raise ValueError(f"Task42 K0 sizing identity {key} is missing")
        identity[key] = value
    if identity["canonical_export_prefix"] != "task42_hybrid_direct":
        raise ValueError("Task42 K0 canonical output identity differs")
    if identity["model_id"] != str(cfg.case_name):
        raise ValueError("Task42 K0 model identity differs from the numerical config")
    for key in _TASK42_K0_IDENTITY_SHA_FIELDS:
        if re.fullmatch(r"[0-9a-f]{64}", identity[key]) is None:
            raise ValueError(f"Task42 K0 sizing identity {key} is not SHA256")
    if re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", identity["source_sha"]) is None:
        raise ValueError(
            "Task42 K0 source_sha does not match the accepted 40/64-hex format; "
            "Git source attestation is enforced by the public runner"
        )
    identity["source_sha_validation"] = (
        "format-only; this basis does not prove the Git source identity"
    )
    requested_modes = task42_sizing_identity.get("requested_modes_per_direction")
    if type(requested_modes) is not int or requested_modes <= 0:
        raise ValueError("Task42 K0 requested mode count is missing or invalid")

    mesh = cross_section.mesh
    topology = mesh.topology
    tdim = int(topology.dim)
    cell_map = topology.index_map(tdim)
    geometry = mesh.geometry
    geometry_coordinates = np.asarray(geometry.x)
    geometry_dofmap = geometry.dofmap
    coefficient_values = np.asarray(cross_section.epsilon_r.x.array)
    cell_layout, cell_local_to_global, cell_map_temp_bytes = (
        _task42_index_map_basis(
            cell_map,
            "cells",
            mpi_size=mpi_size,
            max_local_to_global_entries=36,
        )
    )
    cell_count_local_total = cell_layout["size_local"] + cell_layout["num_ghosts"]
    geometry_dim = int(geometry.dim)
    geometry_storage_dim = (
        int(geometry_coordinates.shape[1]) if geometry_coordinates.ndim == 2 else None
    )
    geometry_dofmap_array = np.asarray(geometry_dofmap)
    del cell_local_to_global
    x_axis = np.asarray(cross_section.x_values)
    y_axis = np.asarray(cross_section.y_values)
    if (
        geometry_dofmap_array.ndim != 2
        or geometry_dofmap_array.shape[0] != cell_count_local_total
    ):
        raise ValueError(
            "Task42 K0 geometry cell map does not match actual owned+ghost cells"
        )
    geometry_cell_map_integer = geometry_dofmap_array.dtype.kind in "iu"
    geometry_cell_map_indices_valid = bool(
        geometry_cell_map_integer
        and geometry_dofmap_array.shape[1] == 4
        and (
            geometry_dofmap_array.size == 0
            or (
                int(geometry_dofmap_array.min()) >= 0
                and int(geometry_dofmap_array.max()) < geometry_coordinates.shape[0]
            )
        )
    )
    coordinates_finite = bool(
        geometry_coordinates.ndim == 2
        and all(np.isfinite(float(value)) for value in geometry_coordinates.flat)
    )
    coordinates_z_zero = bool(
        geometry_storage_dim == 3
        and all(float(value) == 0.0 for value in geometry_coordinates[:, 2])
    )
    def axis_matches_profile(values: np.ndarray, expected: tuple[float, ...]) -> bool:
        return bool(
            values.ndim == 1
            and values.shape == (len(expected),)
            and all(np.isfinite(float(value)) for value in values)
            and all(
                abs(float(value) - expected_value) <= 1.0e-12
                for value, expected_value in zip(values, expected, strict=True)
            )
            and all(float(values[index + 1]) > float(values[index]) for index in range(values.size - 1))
        )

    axis_profile_matches = axis_matches_profile(
        x_axis, _TASK42_K0_PROFILE_X_AXIS_NM
    ) and axis_matches_profile(y_axis, _TASK42_K0_PROFILE_Y_AXIS_NM)
    coordinates_within_xy_axes = bool(
        coordinates_finite
        and x_axis.ndim == 1
        and y_axis.ndim == 1
        and x_axis.size > 0
        and y_axis.size > 0
        and geometry_storage_dim is not None
        and geometry_storage_dim >= 2
        and np.all(geometry_coordinates[:, 0] >= x_axis[0])
        and np.all(geometry_coordinates[:, 0] <= x_axis[-1])
        and np.all(geometry_coordinates[:, 1] >= y_axis[0])
        and np.all(geometry_coordinates[:, 1] <= y_axis[-1])
    )
    rank_value = int(mesh.comm.rank)
    size_value = int(mesh.comm.size)
    if rank_value != rank or size_value != mpi_size:
        raise ValueError("Task42 K0 MPI rank identity changed while forming basis")
    scalar_dtype = np.dtype(PETSc.ScalarType)
    int_dtype = np.dtype(PETSc.IntType)
    if scalar_dtype != np.dtype(np.complex128):
        raise ValueError("Task42 K0 requires the qualified complex128 scalar ABI")

    cell_name = getattr(topology, "cell_name", None)
    if callable(cell_name):
        cell_name = cell_name()
    if not isinstance(cell_name, str) or not cell_name:
        cell_name = getattr(topology, "cell_type", None)
        if callable(cell_name):
            cell_name = cell_name()
        if cell_name is None:
            raise ValueError("Task42 K0 basis lacks the actual mesh cell type")
        cell_name = str(cell_name)

    def optional_complex_pair(value: Any, label: str) -> list[float] | None:
        return None if value is None else _task42_complex_pair(value, label)

    mixed_basis, mixed_cell_rows, mixed_map_temp_bytes = _task42_space_basis(
        spaces.mixed,
        "mixed",
        local_cell_count=cell_count_local_total,
        owned_cell_count=cell_layout["size_local"],
        global_cell_count=cell_layout["size_global"],
        mpi_size=mpi_size,
        max_global_dofs=4033,
        scalar_bytes=int(scalar_dtype.itemsize),
        count_matrix_candidates=True,
    )
    mixed_index_map = mixed_basis["index_map"]
    mixed_block_size = mixed_basis["index_map_bs"]
    mixed_owned_range = mixed_index_map["local_range"]
    transverse_basis, transverse_cell_rows, transverse_map_temp_bytes = (
        _task42_space_basis(
            spaces.transverse,
            "transverse",
            local_cell_count=cell_count_local_total,
            owned_cell_count=cell_layout["size_local"],
            global_cell_count=cell_layout["size_global"],
            mpi_size=mpi_size,
            max_global_dofs=2664,
            scalar_bytes=int(scalar_dtype.itemsize),
        )
    )
    longitudinal_basis, longitudinal_cell_rows, longitudinal_map_temp_bytes = (
        _task42_space_basis(
            spaces.longitudinal,
            "longitudinal",
            local_cell_count=cell_count_local_total,
            owned_cell_count=cell_layout["size_local"],
            global_cell_count=cell_layout["size_global"],
            mpi_size=mpi_size,
            max_global_dofs=1369,
            scalar_bytes=int(scalar_dtype.itemsize),
        )
    )
    geometry_degree = int(degree_context["geometry_degree"])
    coefficient_degree = int(degree_context["coefficient_degree"])
    quadrature_degree_value = int(degree_context["quadrature_degree"])
    coefficient_layout_matches_cells = bool(
        coefficient_values.ndim == 1
        and coefficient_values.size == cell_count_local_total
    )
    material_n = complex(cfg.n_grating) if cfg.n_grating is not None else None
    expected_material_values = {complex(cfg.n_air) ** 2}
    if material_n is not None:
        expected_material_values.add(material_n**2)
    epsilon_values_match_profile = bool(
        coefficient_values.dtype.kind == "c"
        and all(
            np.isfinite(complex(value).real)
            and np.isfinite(complex(value).imag)
            and any(
                abs(complex(value) - expected) <= 1.0e-12
                for expected in expected_material_values
            )
            for value in coefficient_values
        )
    )
    source_derived_objects = {
        "owned_cells": int(cell_layout["size_local"]),
        "ghost_cells": int(cell_layout["num_ghosts"]),
        "dg0_local_coefficient_count": int(coefficient_values.size),
        "dg0_local_coefficient_layout_matches_cells": coefficient_layout_matches_cells,
        "mixed_cell_dof_rows": {
            "owned_per_cell": mixed_cell_rows["owned_cell_dof_rows"],
            "ghost_per_cell": mixed_cell_rows["ghost_cell_dof_rows"],
            "candidate_pair_contributions": mixed_cell_rows[
                "owned_cell_candidate_pair_contributions"
            ],
            "local_cell_tensor_payload_bytes_sum": mixed_cell_rows[
                "local_cell_tensor_payload_bytes"
            ],
            "largest_single_cell_tensor_payload_bytes": mixed_cell_rows[
                "largest_single_cell_tensor_payload_bytes"
            ],
        },
        "transverse_cell_dof_rows": {
            "owned_per_cell": transverse_cell_rows["owned_cell_dof_rows"],
            "ghost_per_cell": transverse_cell_rows["ghost_cell_dof_rows"],
        },
        "longitudinal_cell_dof_rows": {
            "owned_per_cell": longitudinal_cell_rows["owned_cell_dof_rows"],
            "ghost_per_cell": longitudinal_cell_rows["ghost_cell_dof_rows"],
        },
        "matrix_candidate_contributions": mixed_cell_rows.get(
            "matrix_candidate_contributions"
        ),
        "index_map_local_to_global_temporary_peak_bytes": int(
            max(
                cell_map_temp_bytes,
                mixed_map_temp_bytes,
                transverse_map_temp_bytes,
                longitudinal_map_temp_bytes,
            )
        ),
        "geometry_coordinate_validation_mask_bytes_upper": int(
            geometry_coordinates.shape[0]
            if geometry_coordinates.ndim == 2
            else 0
        ),
        "cell_dof_rows_python_metadata_bytes_upper": int(
            mixed_cell_rows["cell_dof_rows_python_metadata_bytes_upper"]
            + transverse_cell_rows["cell_dof_rows_python_metadata_bytes_upper"]
            + longitudinal_cell_rows["cell_dof_rows_python_metadata_bytes_upper"]
        ),
        "cell_dof_layout_normalization_temporary_peak_bytes": int(
            max(
                mixed_cell_rows["cell_dof_layout_normalization_peak_bytes"],
                transverse_cell_rows["cell_dof_layout_normalization_peak_bytes"],
                longitudinal_cell_rows["cell_dof_layout_normalization_peak_bytes"],
            )
        ),
        "source_basis_validation_scratch_peak_bytes": int(
            max(
                cell_map_temp_bytes,
                mixed_cell_rows["source_basis_validation_scratch_peak_bytes"],
                transverse_cell_rows["source_basis_validation_scratch_peak_bytes"],
                longitudinal_cell_rows["source_basis_validation_scratch_peak_bytes"],
                int(
                    geometry_coordinates.shape[0]
                    if geometry_coordinates.ndim == 2
                    else 0
                ),
            )
        ),
    }
    basis: dict[str, Any] = {
        "schema": "task42.qep_k0_rank_basis.v1",
        "phase_rank": rank,
        "mpi_size": mpi_size,
        "task42_identity": identity,
        "full_k0_row_partition": {
            "source": "mixed_dofmap_index_map_before_PETSc_Mat_creation",
            "block_size": mixed_block_size,
            "local_rows": mixed_index_map["size_local"] * mixed_block_size,
            "global_rows": mixed_index_map["size_global"] * mixed_block_size,
            "owned_range": [
                mixed_owned_range[0] * mixed_block_size,
                mixed_owned_range[1] * mixed_block_size,
            ],
        },
        "rank_partition": {
            "cell_index_map": cell_layout,
            "topology_dimension": tdim,
            "geometry_dimension": geometry_dim,
            "coordinate_storage_dimension": geometry_storage_dim,
            "coordinates_all_finite": coordinates_finite,
            "coordinate_z_column_all_zero": coordinates_z_zero,
            "geometry_cell_map_local_row_count": int(geometry_dofmap_array.shape[0]),
            "geometry_cell_map_shape": [
                int(value) for value in geometry_dofmap_array.shape
            ],
            "geometry_cell_map_integer_and_indices_valid": (
                geometry_cell_map_indices_valid
            ),
            "axis_profile_matches_calibrated_geometry": axis_profile_matches,
            "coordinates_within_xy_axes": coordinates_within_xy_axes,
            "geometry_xy_bounds_nm": (
                [
                    float(geometry_coordinates[:, 0].min()),
                    float(geometry_coordinates[:, 0].max()),
                    float(geometry_coordinates[:, 1].min()),
                    float(geometry_coordinates[:, 1].max()),
                ]
                if geometry_coordinates.ndim == 2
                and geometry_coordinates.shape[0] > 0
                and coordinates_finite
                and geometry_storage_dim is not None
                and geometry_storage_dim >= 2
                else None
            ),
            "geometry_coordinates": _task42_array_basis(
                geometry_coordinates, "geometry.coordinates"
            ),
            "geometry_cell_dofmap": _task42_array_basis(
                geometry_dofmap_array, "geometry.cell_dofmap"
            ),
            "x_axis": _task42_array_basis(x_axis, "x_axis"),
            "y_axis": _task42_array_basis(y_axis, "y_axis"),
        },
        "dof_layout": {
            "mixed": mixed_basis,
            "transverse": transverse_basis,
            "longitudinal": longitudinal_basis,
            "transverse_to_mixed": _task42_array_basis(
                spaces.transverse_to_mixed, "transverse_to_mixed"
            ),
            "longitudinal_to_mixed": _task42_array_basis(
                spaces.longitudinal_to_mixed, "longitudinal_to_mixed"
            ),
        },
        "abi": {
            "petsc_scalar_dtype": scalar_dtype.str,
            "petsc_scalar_bytes": int(scalar_dtype.itemsize),
            "petsc_int_dtype": int_dtype.str,
            "petsc_int_bytes": int(int_dtype.itemsize),
            "geometry_real_dtype": geometry_coordinates.dtype.str,
        },
        "discretization": {
            "transverse_degree_p": int(spaces.transverse_degree),
            "longitudinal_degree_p": int(spaces.longitudinal_degree),
            "geometry_degree_g": geometry_degree,
            "coefficient_degree_c": coefficient_degree,
            "quadrature_degree_q": quadrature_degree_value,
            "cell_type": cell_name,
            "topological_dimension": tdim,
            "global_cell_count": int(cell_map.size_global),
            "geometry_dimension": geometry_dim,
            "coordinate_storage_dimension": geometry_storage_dim,
        },
        "physics": {
            "case_name": str(cfg.case_name),
            "requested_modes_per_direction": requested_modes,
            "wavelength_nm": float(cfg.lambda0),
            "period_x_nm": float(cfg.period_x),
            "period_y_nm": float(cfg.period_y),
            "kx_per_nm": _task42_complex_pair(cfg.kx, "kx"),
            "ky_per_nm": _task42_complex_pair(cfg.ky, "ky"),
            "mu_r": _task42_complex_pair(cfg.mu_r, "mu_r"),
            "n_air": _task42_complex_pair(cfg.n_air, "n_air"),
            "n_grating": optional_complex_pair(cfg.n_grating, "n_grating"),
            "n_substrate": optional_complex_pair(cfg.n_substrate, "n_substrate"),
            "material_coefficients_match_air_or_configured_grating": (
                epsilon_values_match_profile
            ),
            "epsilon_r_coefficients": _task42_array_basis(
                coefficient_values, "epsilon_r.coefficients"
            ),
        },
        "source_derived_objects": source_derived_objects,
    }
    if compiled_form is not None:
        basis["compiled_form_type"] = (
            f"{type(compiled_form).__module__}.{type(compiled_form).__qualname__}"
        )
    return basis


_TASK42_K0_RANK_BYTES = 64 * 1024**2
_TASK42_K0_COMPILER_SUBTREE_BYTES = 512 * 1024**2
_TASK42_K0_CONTROLLER_BYTES = 8 * 1024**2
_TASK42_K0_PROFILE_X_AXIS_NM = (0.0, 8.25, 16.5, 25.0, 33.5, 41.75, 50.0)
_TASK42_K0_PROFILE_Y_AXIS_NM = (0.0, 7.5, 15.0, 25.0, 35.0, 42.5, 50.0)
_TASK42_K0_SI_N = complex(0.999001296237, 0.00182646094)
_TASK42_K0_METADATA_MARGIN_BYTES = 64 * 1024


def _task42_json_utf8_size(value: Any) -> int:
    return len(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    )


def _task42_k0_calibration_scope_errors(
    basis: Mapping[str, Any], *, mpi_size: int
) -> list[str]:
    errors: list[str] = []
    rank_partition = basis["rank_partition"]
    discretization = basis["discretization"]
    dof_layout = basis["dof_layout"]
    physics = basis["physics"]
    abi = basis["abi"]
    objects = basis["source_derived_objects"]
    if mpi_size != 8:
        errors.append("qep_K0_profile_requires_MPI8")
    if discretization["topological_dimension"] != 2:
        errors.append("qep_K0_profile_requires_2D_quad_topology")
    if discretization["cell_type"] != "quadrilateral":
        errors.append("qep_K0_profile_requires_quadrilateral_cells")
    if discretization["global_cell_count"] != 36:
        errors.append("qep_K0_profile_requires_36_global_cells")
    matrix_candidates = objects["matrix_candidate_contributions"]
    if matrix_candidates["global_cell_candidate_pair_contribution_bound"] != 636804:
        errors.append("qep_K0_profile_global_cell_pair_bound_must_be_636804")
    if objects["owned_cells"] <= 0:
        errors.append("qep_K0_profile_requires_owned_cells_for_local_basis")
    if discretization["geometry_degree_g"] != 1:
        errors.append("qep_K0_profile_requires_linear_geometry_g1")
    if rank_partition["geometry_dimension"] != 2:
        errors.append("qep_K0_profile_requires_geometry_dim_2")
    if rank_partition["coordinate_storage_dimension"] != 3:
        errors.append("qep_K0_profile_requires_three_coordinate_storage_columns")
    if rank_partition["geometry_cell_map_local_row_count"] != (
        rank_partition["cell_index_map"]["size_local"]
        + rank_partition["cell_index_map"]["num_ghosts"]
    ):
        errors.append("qep_K0_geometry_cell_map_count_mismatch")
    if rank_partition["geometry_cell_map_shape"][1:] != [4]:
        errors.append("qep_K0_geometry_cell_map_width_must_be_4")
    if not rank_partition["geometry_cell_map_integer_and_indices_valid"]:
        errors.append("qep_K0_geometry_cell_map_indices_invalid")
    if not rank_partition["coordinates_all_finite"]:
        errors.append("qep_K0_geometry_coordinates_nonfinite")
    if not rank_partition["coordinate_z_column_all_zero"]:
        errors.append("qep_K0_2D_geometry_z_column_not_zero")
    if not rank_partition["coordinates_within_xy_axes"]:
        errors.append("qep_K0_geometry_xy_outside_axes")
    if not rank_partition["axis_profile_matches_calibrated_geometry"]:
        errors.append("qep_K0_profile_axes_do_not_match_full_50x50_17x20_geometry")
    expected_degrees = {
        "transverse_degree_p": 6,
        "longitudinal_degree_p": 6,
        "geometry_degree_g": 1,
        "coefficient_degree_c": 0,
        "quadrature_degree_q": 16,
    }
    for name, expected in expected_degrees.items():
        if discretization[name] != expected:
            errors.append(f"qep_K0_profile_{name}_must_be_{expected}")
    expected_global_dofs = {
        "mixed": 4033,
        "transverse": 2664,
        "longitudinal": 1369,
    }
    for label, expected in expected_global_dofs.items():
        layout = dof_layout[label]
        global_rows = layout["index_map"]["size_global"] * layout["index_map_bs"]
        if global_rows != expected:
            errors.append(f"qep_K0_profile_{label}_global_dofs_must_be_{expected}")
    if dof_layout["mixed"]["index_map_bs"] != 1:
        errors.append("qep_K0_profile_mixed_index_map_block_size_must_be_1")
    cell_rows = objects["mixed_cell_dof_rows"]
    if any(value != 133 for value in cell_rows["owned_per_cell"]):
        errors.append("qep_K0_profile_owned_mixed_cell_dofs_must_be_133")
    if any(value != 133 for value in cell_rows["ghost_per_cell"]):
        errors.append("qep_K0_profile_ghost_mixed_cell_dofs_must_be_133")
    if any(value != 84 for value in objects["transverse_cell_dof_rows"]["owned_per_cell"]):
        errors.append("qep_K0_profile_owned_transverse_cell_dofs_must_be_84")
    if any(value != 84 for value in objects["transverse_cell_dof_rows"]["ghost_per_cell"]):
        errors.append("qep_K0_profile_ghost_transverse_cell_dofs_must_be_84")
    if any(value != 49 for value in objects["longitudinal_cell_dof_rows"]["owned_per_cell"]):
        errors.append("qep_K0_profile_owned_longitudinal_cell_dofs_must_be_49")
    if any(value != 49 for value in objects["longitudinal_cell_dof_rows"]["ghost_per_cell"]):
        errors.append("qep_K0_profile_ghost_longitudinal_cell_dofs_must_be_49")
    if abi["petsc_scalar_dtype"] != np.dtype(np.complex128).str:
        errors.append("qep_K0_profile_requires_PETSc_complex128")
    if abi["petsc_int_dtype"] != np.dtype(np.int32).str:
        errors.append("qep_K0_profile_requires_PETSc_Int32")
    if abi["geometry_real_dtype"] != np.dtype(np.float64).str:
        errors.append("qep_K0_profile_requires_float64_geometry")
    if physics["requested_modes_per_direction"] != 120:
        errors.append("qep_K0_profile_requires_M120")
    if physics["wavelength_nm"] != 13.5:
        errors.append("qep_K0_profile_requires_13p5nm")
    if physics["period_x_nm"] != 50.0 or physics["period_y_nm"] != 50.0:
        errors.append("qep_K0_profile_requires_50x50nm_period")
    if physics["mu_r"] != [1.0, 0.0] or physics["n_air"] != [1.0, 0.0]:
        errors.append("qep_K0_profile_air_or_mu_identity_mismatch")
    expected_si_pair = [float(_TASK42_K0_SI_N.real), float(_TASK42_K0_SI_N.imag)]
    if (
        physics["n_grating"] != expected_si_pair
        or physics["n_substrate"] != expected_si_pair
    ):
        errors.append("qep_K0_profile_user_Si_material_identity_mismatch")
    if not physics["material_coefficients_match_air_or_configured_grating"]:
        errors.append("qep_K0_DG0_coefficients_do_not_match_air_or_Si")
    if not objects["dg0_local_coefficient_layout_matches_cells"]:
        errors.append("qep_K0_DG0_local_coefficient_count_does_not_match_cells")
    if len(objects["mixed_cell_dof_rows"]["owned_per_cell"]) != objects["owned_cells"]:
        errors.append("qep_K0_owned_cell_dof_rows_count_mismatch")
    if len(objects["mixed_cell_dof_rows"]["ghost_per_cell"]) != objects["ghost_cells"]:
        errors.append("qep_K0_ghost_cell_dof_rows_count_mismatch")
    for label, rows in (
        ("transverse", objects["transverse_cell_dof_rows"]),
        ("longitudinal", objects["longitudinal_cell_dof_rows"]),
    ):
        if len(rows["owned_per_cell"]) != objects["owned_cells"]:
            errors.append(f"qep_K0_{label}_owned_cell_dof_rows_count_mismatch")
        if len(rows["ghost_per_cell"]) != objects["ghost_cells"]:
            errors.append(f"qep_K0_{label}_ghost_cell_dof_rows_count_mismatch")
    return errors


def _task42_k0_phase_inventory(
    phase: str,
    cfg: SimulationConfig3D,
    cross_section: CrossSectionMesh,
    spaces: CrossSectionSpaces,
    degree_context: Mapping[str, int],
    task42_sizing_identity: Mapping[str, Any] | None,
    *,
    compiled_form: Any | None = None,
    allocation_boundary: str | None = None,
    constraints_transform_resident: bool = False,
    local_basis_errors: tuple[str, ...] = (),
) -> dict[str, Any]:
    from ..common.task42_phase_admission import task42_phase_inventory

    inventory = task42_phase_inventory(phase)
    rank = int(cross_section.mesh.comm.rank)
    mpi_size = int(cross_section.mesh.comm.size)
    admission_errors: list[str] = list(local_basis_errors)
    basis: dict[str, Any] = {}
    if not admission_errors:
        try:
            basis = _task42_k0_source_basis(
                cfg,
                cross_section,
                spaces,
                degree_context,
                task42_sizing_identity,
                rank=rank,
                mpi_size=mpi_size,
                compiled_form=compiled_form,
            )
            admission_errors.extend(
                _task42_k0_calibration_scope_errors(basis, mpi_size=mpi_size)
            )
        except Exception as exc:  # noqa: BLE001 - local basis errors must reach collective refusal
            admission_errors.append(
                f"task42_k0_source_basis_unavailable:{type(exc).__name__}:{exc}"
            )
    default_boundaries = {
        "qep_operator_K0_ffcx_form": "before_ufl_form_context_and_form",
        "qep_operator_K0_full": "after_fem_form_jit_before_petsc_matrix",
    }
    selected_boundary = allocation_boundary or default_boundaries.get(phase)
    allowed_boundaries = {
        "qep_operator_K0_ffcx_form": {
            "before_ufl_form_context_and_form",
            "before_fem_form_jit_after_constraints_transform",
        },
        "qep_operator_K0_full": {"after_fem_form_jit_before_petsc_matrix"},
    }
    if selected_boundary not in allowed_boundaries.get(phase, set()):
        admission_errors.append("task42_k0_allocation_boundary_is_invalid_for_phase")
        basis = {}
    if (
        selected_boundary == "before_fem_form_jit_after_constraints_transform"
        and not constraints_transform_resident
    ):
        admission_errors.append(
            "qep_K0_constraints_transform_context_missing_at_fresh_ffcx_boundary"
        )

    if phase == "qep_operator_K0_ffcx_form":
        rank_amounts = {
            "qep_k0_ffcx_rank_payload": _TASK42_K0_RANK_BYTES,
            "qep_k0_ffcx_rank0_compiler_subtree": (
                _TASK42_K0_COMPILER_SUBTREE_BYTES if rank == 0 else 0
            ),
            "qep_k0_ffcx_controller_allowance": (
                _TASK42_K0_CONTROLLER_BYTES if rank == 0 else 0
            ),
        }
    elif phase == "qep_operator_K0_full":
        rank_amounts = {
            "full_K0_sparse_matrix": _TASK42_K0_RANK_BYTES,
            "qep_k0_full_controller_allowance": (
                _TASK42_K0_CONTROLLER_BYTES if rank == 0 else 0
            ),
        }
    else:
        raise ValueError(f"unsupported source-derived Task42 K0 phase {phase!r}")

    uncertainty = (
        "predicted only for the source-derived 36-quad, p6/g1, DG0/c0, q16, "
        "4033-row, 133-mixed-dofs-per-cell, MPI8 profile; not a hard upper bound "
        "or measured peak; native compiler/PETSc workspace remains uncalibrated; "
        "controller allowance is charged once on rank 0"
    )
    rank_known_bytes = 0
    controller_known_bytes = 0
    if basis:
        source_objects = basis["source_derived_objects"]
        cell_rows = source_objects["mixed_cell_dof_rows"]
        matrix_candidates = source_objects["matrix_candidate_contributions"]
        basis_scratch = source_objects[
            "source_basis_validation_scratch_peak_bytes"
        ]
        python_cell_metadata = source_objects[
            "cell_dof_rows_python_metadata_bytes_upper"
        ]
        if phase == "qep_operator_K0_ffcx_form":
            phase_objects_bytes = int(
                cell_rows["local_cell_tensor_payload_bytes_sum"]
            )
        else:
            phase_objects_bytes = int(
                cell_rows["local_cell_tensor_payload_bytes_sum"]
                + matrix_candidates["candidate_sparse_payload_bytes_upper"]
            )
        basis["phase_prediction"] = {
            "phase": phase,
            "known_source_derived_rank_payload_bytes": int(
                phase_objects_bytes + basis_scratch + python_cell_metadata
            ),
            "source_derived_rank_payload_formula": (
                "sum over actual owned mixed-cell rows of rows^2*ScalarType_bytes "
                "as a conservative local-tensor candidate payload, plus actual "
                "local_to_global/coordinate-validation scratch peak and row metadata; FFCx "
                "and compiler subtree remain predicted inside their envelopes"
                if phase == "qep_operator_K0_ffcx_form"
                else "sum over actual owned mixed-cell rows of rows^2*ScalarType_bytes "
                "+ source-derived AIJ and remote-stash payload using the global "
                "36*133^2 all-cell contribution bound for each rank (not only that "
                "rank's owned-cell subtotal) + local_to_global/coordinate-validation "
                "scratch peak + row metadata; no matrix is created while inventory is formed"
            ),
            "rank_envelope_bytes": _TASK42_K0_RANK_BYTES,
            "rank_allowance_is_hard_bound": False,
            "component_count": len(inventory["components"]),
        }
        for _ in range(4):
            basis_json_bytes = _task42_json_utf8_size(basis)
            component_count = len(inventory["components"])
            per_component_basis_bytes_upper = basis_json_bytes + 1024
            rank_inventory_bytes_upper = (
                component_count * per_component_basis_bytes_upper
                + _TASK42_K0_METADATA_MARGIN_BYTES
            )
            rank_gate_metadata_bytes = int(
                2 * rank_inventory_bytes_upper
                + mpi_size * rank_inventory_bytes_upper
                + _TASK42_K0_METADATA_MARGIN_BYTES
            )
            controller_receipt_metadata_bytes = int(
                2 * mpi_size * rank_inventory_bytes_upper
                + _TASK42_K0_METADATA_MARGIN_BYTES
            )
            new_accounting = {
                **basis["phase_prediction"],
                "basis_json_probe_bytes": basis_json_bytes,
                "rank_inventory_metadata_bytes_upper": rank_inventory_bytes_upper,
                "allgather_and_rank_local_gate_metadata_bytes_upper": rank_gate_metadata_bytes,
                "root_controller_receipt_metadata_bytes_upper": controller_receipt_metadata_bytes,
                "metadata_probe_peak_included_in_rank_payload": True,
                "allocation_prediction_is_not_a_cumulative_charge": True,
            }
            if basis["phase_prediction"] == new_accounting:
                break
            basis["phase_prediction"] = new_accounting
        rank_known_bytes = int(
            basis["phase_prediction"]["known_source_derived_rank_payload_bytes"]
            + basis["phase_prediction"][
                "allgather_and_rank_local_gate_metadata_bytes_upper"
            ]
        )
        controller_known_bytes = int(
            basis["phase_prediction"][
                "root_controller_receipt_metadata_bytes_upper"
            ]
        )
        if rank_known_bytes > _TASK42_K0_RANK_BYTES:
            admission_errors.append(
                "qep_K0_source_derived_rank_objects_exceed_64MiB_envelope"
            )
        if controller_known_bytes > _TASK42_K0_CONTROLLER_BYTES:
            admission_errors.append(
                "qep_K0_source_derived_controller_metadata_exceeds_8MiB_envelope"
            )
        for component in inventory["components"]:
            name = str(component["name"])
            component["sizing_basis"] = {**basis, "component": name}

    if allocation_boundary is None:
        allocation_boundary = selected_boundary
    resident_objects = {
        "before_ufl_form_context_and_form": [
            "cross_section_mesh_and_DG0_coefficients",
            "mixed_and_collapsed_spaces",
        ],
        "before_fem_form_jit_after_constraints_transform": [
            "cross_section_mesh_and_DG0_coefficients",
            "mixed_and_collapsed_spaces",
            "UFL_QEP_forms",
        ],
        "after_fem_form_jit_before_petsc_matrix": [
            "cross_section_mesh_and_DG0_coefficients",
            "mixed_and_collapsed_spaces",
            "UFL_QEP_forms",
            "compiled_K0_form",
        ],
    }.get(str(allocation_boundary), [])
    if constraints_transform_resident and allocation_boundary in {
        "before_fem_form_jit_after_constraints_transform",
        "after_fem_form_jit_before_petsc_matrix",
    }:
        resident_objects.extend(
            ("Floquet_constraints", "distributed_constraint_transform")
        )
    if allocation_boundary == "before_fem_form_jit_after_constraints_transform":
        resident_objects.append("UFL_K0_form")
    components = []
    for component in inventory["components"]:
        item = dict(component)
        name = str(item["name"])
        item["delta_bytes"] = (
            None if admission_errors else int(rank_amounts[name])
        )
        item["sizing_basis"] = (
            {**basis, "component": name} if basis else {}
        )
        item["uncertainty"] = uncertainty
        item["classification"] = "predicted"
        item["upper_bound_proven"] = False
        components.append(item)
    inventory.update(
        {
            "schema": "task42.direct_phase_delta_inventory.v1",
            "status": "source-derived-prediction",
            "estimate_uncertainty": uncertainty,
            "evidence": {
                "source": "live QEP config, cross-section, mixed/collapsed dofmaps, and ABI",
                "rank": rank,
                "mpi_size": mpi_size,
                "basis_schema": "task42.qep_k0_rank_basis.v1",
                "allocation_boundary": allocation_boundary,
                "resident_objects_at_fresh_snapshot": resident_objects,
                "same_phase_delta_semantics": (
                    "a second FFCx gate rechecks the same manifest-bound Delta "
                    "against a fresh J after constraints/transform; it is not an "
                    "additional cumulative phase charge"
                ),
                "source_sha_semantics": (
                    "40/64-hex format is checked in this helper; actual Git source "
                    "attestation remains the public-runner responsibility"
                ),
            },
            "components": components,
            "admission_errors": admission_errors,
        }
    )
    return inventory


def _task42_k1_collective_errors(comm, local_errors: list[str], label: str):
    rank_rows = comm.allgather(tuple(str(error) for error in local_errors))
    return [
        f"rank_{rank}_{label}:{error}"
        for rank, errors in enumerate(rank_rows)
        for error in errors
    ]


def _task42_k1_exact_integer(value: Any, label: str) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value, (int, np.integer)
    ):
        raise TypeError(f"{label} is not an exact integer")
    return int(value)


def _task42_k1_matrix_layout(
    matrix: Any,
    label: str,
    comm,
    *,
    max_global_nz_used: int | None = None,
):
    local_errors: list[str] = []
    descriptor: dict[str, Any] = {"rank": int(comm.rank), "label": label}
    try:
        shape = matrix.getSize()
        row_range = matrix.getOwnershipRange()
        column_range = matrix.getOwnershipRangeColumn()
        if not isinstance(shape, (tuple, list)) or len(shape) != 2:
            raise ValueError("global matrix shape must contain two integers")
        if not isinstance(row_range, (tuple, list)) or len(row_range) != 2:
            raise ValueError("matrix row ownership must contain two integers")
        if not isinstance(column_range, (tuple, list)) or len(column_range) != 2:
            raise ValueError("matrix column ownership must contain two integers")
        rows, columns = (
            _task42_k1_exact_integer(value, f"{label} shape") for value in shape
        )
        row_start, row_end = (
            _task42_k1_exact_integer(value, f"{label} row range")
            for value in row_range
        )
        column_start, column_end = (
            _task42_k1_exact_integer(value, f"{label} column range")
            for value in column_range
        )
        if rows < 0 or columns < 0:
            raise ValueError("global matrix shape cannot be negative")
        if not (0 <= row_start <= row_end <= rows):
            raise ValueError("matrix row ownership is outside the global shape")
        if not (0 <= column_start <= column_end <= columns):
            raise ValueError("matrix column ownership is outside the global shape")
        info = matrix.getInfo(PETSc.Mat.InfoType.LOCAL)
        local_nnz_raw = info.get("nz_used") if isinstance(info, Mapping) else None
        if (
            isinstance(local_nnz_raw, (bool, np.bool_))
            or local_nnz_raw is None
            or not np.isfinite(float(local_nnz_raw))
            or int(local_nnz_raw) != float(local_nnz_raw)
            or int(local_nnz_raw) < 0
        ):
            raise ValueError("PETSc local nz_used is missing or invalid")
        descriptor.update(
            {
                "shape": [int(rows), int(columns)],
                "row_range": [int(row_start), int(row_end)],
                "column_range": [int(column_start), int(column_end)],
                "local_nz_used": int(local_nnz_raw),
            }
        )
    except Exception as exc:  # noqa: BLE001 - rank-local failures must reach the same gate
        local_errors.append(f"{type(exc).__name__}:{exc}")
    rank_errors = _task42_k1_collective_errors(comm, local_errors, f"{label}_layout")
    descriptors = comm.allgather(descriptor)
    if rank_errors:
        return None, rank_errors
    shape_set = {tuple(row.get("shape", ())) for row in descriptors}
    if len(shape_set) != 1 or any(row.get("label") != label for row in descriptors):
        return None, [f"{label}_MPI_shape_or_label_differs"]
    shape = next(iter(shape_set))
    for range_name, axis in (("row_range", 0), ("column_range", 1)):
        cursor = 0
        for rank, row in enumerate(descriptors):
            values = row.get(range_name)
            if (
                row.get("rank") != rank
                or not isinstance(values, list)
                or len(values) != 2
                or type(values[0]) is not int
                or type(values[1]) is not int
                or values[0] != cursor
                or values[1] < values[0]
            ):
                return None, [f"{label}_{range_name}_is_not_a_contiguous_partition"]
            cursor = values[1]
        if cursor != shape[axis]:
            return None, [f"{label}_{range_name}_does_not_cover_global_extent"]
    layout = {
        "shape": list(shape),
        "rank_layouts": descriptors,
        "global_nz_used": sum(int(row["local_nz_used"]) for row in descriptors),
    }
    if max_global_nz_used is not None:
        maximum = _task42_k1_exact_integer(
            max_global_nz_used, f"{label} profile NNZ limit"
        )
        if maximum < 0 or layout["global_nz_used"] > maximum:
            return None, [f"{label}_global_nz_used_exceeds_profile_bound"]
    return layout, []


def _task42_k1_global_row_supports(
    matrix: Any,
    *,
    label: str,
    global_rows: int,
    global_columns: int,
    comm,
    support_memory_limit_bytes: int,
    max_global_nz_used: int,
    layout: Mapping[str, Any] | None = None,
):
    if layout is None:
        layout, errors = _task42_k1_matrix_layout(
            matrix,
            label,
            comm,
            max_global_nz_used=max_global_nz_used,
        )
    else:
        errors = []
    if errors:
        return None, None, errors
    if layout["shape"] != [global_rows, global_columns]:
        return None, layout, [f"{label}_shape_is_outside_the_Task42_p6_profile"]

    pet_int_bytes = int(np.dtype(PETSc.IntType).itemsize)
    support_estimate = int(
        layout["global_nz_used"] * (pet_int_bytes + 48)
        + global_rows * 64
    )
    # Each rank holds the gathered support rows and a normalized row map while
    # deriving the product counts. This is an inventory scratch estimate, not
    # an additional matrix or a measured peak.
    gathered_support_peak = 3 * support_estimate
    if gathered_support_peak > support_memory_limit_bytes:
        return None, layout, [
            f"{label}_row_support_scratch_exceeds_64MiB_before_capture"
        ]

    rank_layout = layout["rank_layouts"][int(comm.rank)]
    local_rows: list[tuple[int, tuple[int, ...]]] = []
    local_errors: list[str] = []
    captured_local_nnz = 0
    row_start, row_end = rank_layout["row_range"]
    try:
        for row in range(row_start, row_end):
            columns, values = matrix.getRow(row)
            column_array = np.asarray(columns)
            value_array = np.asarray(values)
            if (
                column_array.ndim != 1
                or value_array.ndim != 1
                or column_array.size != value_array.size
                or column_array.dtype.kind not in "iu"
                or value_array.dtype.kind not in "fc"
                or not np.all(np.isfinite(value_array))
            ):
                raise ValueError(f"row {row} has invalid CSR support/value arrays")
            selected_columns = tuple(int(value) for value in column_array)
            if (
                any(value < 0 or value >= global_columns for value in selected_columns)
                or len(set(selected_columns)) != len(selected_columns)
            ):
                raise ValueError(f"row {row} has duplicate or out-of-range columns")
            captured_local_nnz += len(selected_columns)
            if captured_local_nnz > rank_layout["local_nz_used"]:
                raise ValueError("row support exceeds PETSc local nz_used")
            local_rows.append((int(row), selected_columns))
            del column_array, value_array, columns, values
        if captured_local_nnz != rank_layout["local_nz_used"]:
            raise ValueError("row support differs from PETSc local nz_used")
    except Exception as exc:  # noqa: BLE001 - all ranks meet the refusal point
        local_errors.append(f"{type(exc).__name__}:{exc}")
    capture_errors = _task42_k1_collective_errors(
        comm, local_errors, f"{label}_row_capture"
    )
    if capture_errors:
        return None, layout, capture_errors

    gathered_rows = comm.allgather(local_rows)
    row_supports: dict[int, tuple[int, ...]] = {}
    for rank_rows in gathered_rows:
        for row, columns in rank_rows:
            if row in row_supports:
                return None, layout, [f"{label}_row_support_is_duplicated"]
            row_supports[row] = columns
    if set(row_supports) != set(range(global_rows)):
        return None, layout, [f"{label}_row_support_does_not_cover_global_rows"]
    digest = hashlib.sha256()
    for row in range(global_rows):
        digest.update(int(row).to_bytes(8, "little", signed=False))
        for column in row_supports[row]:
            digest.update(int(column).to_bytes(8, "little", signed=False))
        digest.update(b"\0")
    summary = {
        "global_rows": global_rows,
        "global_columns": global_columns,
        "global_nz_used": layout["global_nz_used"],
        "row_support_sha256": digest.hexdigest(),
        "row_support_capture_scratch_estimate_bytes": gathered_support_peak,
        "support_estimate_formula": (
            "3*(global_nz_used*(PetscInt_bytes+48)+global_rows*64); includes gathered row tuples, normalized row map, and serialized collective buffer on each rank; source estimate, not a proven upper bound"
        ),
    }
    return row_supports, {**layout, **summary}, []


def _task42_k1_reduction_basis(
    matrix: Any,
    transform: Any,
    *,
    comm,
    full_size: int,
    reduced_size: int,
    expected_slave_count: int,
    basis: Mapping[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    constraint_matrix = transform.matrix
    k1_layout, errors = _task42_k1_matrix_layout(
        matrix,
        "full_K1",
        comm,
        max_global_nz_used=36 * 133**2,
    )
    if errors:
        return {}, errors

    local_layout_errors: list[str] = []
    try:
        if k1_layout["shape"] != [full_size, full_size]:
            local_layout_errors.append(
                "full_K1_shape_does_not_match_actual_mixed_space"
            )
        if _task42_k1_exact_integer(
            transform.full_global_size, "transform full global size"
        ) != full_size:
            local_layout_errors.append(
                "constraint_full_global_size_differs_from_mixed_space"
            )
        if _task42_k1_exact_integer(
            transform.reduced_global_size, "transform reduced global size"
        ) != reduced_size:
            local_layout_errors.append(
                "constraint_reduced_global_size_differs_from_profile"
            )
        if _task42_k1_exact_integer(
            transform.global_slave_count, "transform global slave count"
        ) != expected_slave_count:
            local_layout_errors.append(
                "constraint_slave_count_differs_from_profile"
            )
        local_k1_layout = k1_layout["rank_layouts"][int(comm.rank)]
        if _task42_k1_exact_integer(
            transform.full_local_size, "transform full local size"
        ) != local_k1_layout["row_range"][1] - local_k1_layout["row_range"][0]:
            local_layout_errors.append(
                "constraint_full_local_size_differs_from_K1_row_layout"
            )
        full_owned_range = basis.get("full_k0_row_partition", {}).get(
            "owned_range"
        )
        if (
            not isinstance(full_owned_range, list)
            or len(full_owned_range) != 2
            or any(type(value) is not int for value in full_owned_range)
            or full_owned_range != local_k1_layout["row_range"]
        ):
            local_layout_errors.append(
                "full_K1_rows_do_not_match_source_mixed_dofmap_ownership"
            )
    except Exception as exc:  # noqa: BLE001 - keep every rank at the safe point
        local_layout_errors.append(
            f"reduction_layout_metadata:{type(exc).__name__}:{exc}"
        )
    synchronized = _task42_k1_collective_errors(
        comm, local_layout_errors, "reduction_layout"
    )
    if synchronized:
        return {}, synchronized

    max_constraint_nnz = reduced_size + expected_slave_count * 6
    constraint_layout, errors = _task42_k1_matrix_layout(
        constraint_matrix,
        "constraint_transform",
        comm,
        max_global_nz_used=max_constraint_nnz,
    )
    if errors:
        return {}, errors
    local_constraint_layout = constraint_layout["rank_layouts"][int(comm.rank)]
    local_layout_errors = []
    try:
        if constraint_layout["shape"] != [full_size, reduced_size]:
            local_layout_errors.append(
                "constraint_transform_shape_does_not_match_profile"
            )
        if _task42_k1_exact_integer(
            transform.reduced_local_size, "transform reduced local size"
        ) != local_constraint_layout["column_range"][1] - local_constraint_layout[
            "column_range"
        ][0]:
            local_layout_errors.append(
                "constraint_reduced_local_size_differs_from_column_layout"
            )
        k1_ranges = [row["row_range"] for row in k1_layout["rank_layouts"]]
        k1_column_ranges = [
            row["column_range"] for row in k1_layout["rank_layouts"]
        ]
        constraint_ranges = [
            row["row_range"] for row in constraint_layout["rank_layouts"]
        ]
        if k1_ranges != constraint_ranges:
            local_layout_errors.append(
                "full_K1_and_constraint_row_ownership_differ"
            )
        if k1_ranges != k1_column_ranges:
            local_layout_errors.append(
                "full_K1_row_and_column_ownership_differ"
            )
    except Exception as exc:  # noqa: BLE001 - keep every rank at the safe point
        local_layout_errors.append(
            f"reduction_layout_metadata:{type(exc).__name__}:{exc}"
        )
    synchronized = _task42_k1_collective_errors(
        comm, local_layout_errors, "reduction_layout"
    )
    if synchronized:
        return {}, synchronized

    constraint_rows, constraint_layout, errors = _task42_k1_global_row_supports(
        constraint_matrix,
        label="constraint_transform",
        global_rows=full_size,
        global_columns=reduced_size,
        comm=comm,
        support_memory_limit_bytes=_TASK42_K0_RANK_BYTES,
        max_global_nz_used=max_constraint_nnz,
        layout=constraint_layout,
    )
    if errors:
        return {}, errors

    full_to_reduced_columns = constraint_rows
    intermediate_rows: list[tuple[int, int]] = []
    local_scan_errors: list[str] = []
    k1_support_digest = hashlib.sha256()
    k1_rank_layout = k1_layout["rank_layouts"][int(comm.rank)]
    k1_row_start, k1_row_end = k1_rank_layout["row_range"]
    max_k1_row_nnz = 0
    captured_k1_local_nnz = 0
    try:
        for row in range(k1_row_start, k1_row_end):
            columns, values = matrix.getRow(row)
            column_array = np.asarray(columns)
            value_array = np.asarray(values)
            if (
                column_array.ndim != 1
                or value_array.ndim != 1
                or column_array.size != value_array.size
                or column_array.dtype.kind not in "iu"
                or value_array.dtype.kind not in "fc"
                or not np.all(np.isfinite(value_array))
            ):
                raise ValueError(f"full K1 row {row} has invalid CSR arrays")
            full_columns = tuple(int(value) for value in column_array)
            if (
                any(value < 0 or value >= full_size for value in full_columns)
                or len(set(full_columns)) != len(full_columns)
            ):
                raise ValueError(f"full K1 row {row} has invalid column indices")
            captured_k1_local_nnz += len(full_columns)
            if captured_k1_local_nnz > k1_rank_layout["local_nz_used"]:
                raise ValueError("full K1 rows exceed PETSc local nz_used")
            missing_rows = [
                value for value in full_columns if value not in full_to_reduced_columns
            ]
            if missing_rows:
                raise ValueError(
                    f"full K1 row {row} references missing constraint rows"
                )
            k1_support_digest.update(int(row).to_bytes(8, "little", signed=False))
            for column in full_columns:
                k1_support_digest.update(
                    int(column).to_bytes(8, "little", signed=False)
                )
            k1_support_digest.update(b"\0")
            candidate_count = sum(
                len(full_to_reduced_columns[column]) for column in full_columns
            )
            intermediate_rows.append((int(row), int(candidate_count)))
            max_k1_row_nnz = max(max_k1_row_nnz, len(full_columns))
            del column_array, value_array, columns, values, full_columns, missing_rows
        if captured_k1_local_nnz != k1_rank_layout["local_nz_used"]:
            raise ValueError("full K1 rows differ from PETSc local nz_used")
    except Exception as exc:  # noqa: BLE001 - rank-local row errors meet one safe point
        local_scan_errors.append(f"{type(exc).__name__}:{exc}")
    scan_errors = _task42_k1_collective_errors(
        comm, local_scan_errors, "full_K1_product_support"
    )
    if scan_errors:
        return {}, scan_errors

    gathered_intermediate = comm.allgather(intermediate_rows)
    intermediate_candidate_by_full_row = [-1] * full_size
    k1_support_by_rank = comm.allgather(
        {
            "max_row_nnz": int(max_k1_row_nnz),
            "row_support_sha256": k1_support_digest.hexdigest(),
            "owned_row_count": len(intermediate_rows),
        }
    )
    for rank_rows in gathered_intermediate:
        for row, candidate_count in rank_rows:
            if (
                row < 0
                or row >= full_size
                or intermediate_candidate_by_full_row[row] != -1
                or candidate_count < 0
            ):
                errors.append("full_K1_product_candidate_rows_are_invalid_or_duplicated")
                continue
            intermediate_candidate_by_full_row[row] = candidate_count
    if any(value < 0 for value in intermediate_candidate_by_full_row):
        errors.append("full_K1_product_candidate_rows_do_not_cover_global_rows")
    if errors:
        return {}, errors

    reduced_start, reduced_end = local_constraint_layout["column_range"]
    local_reduced_candidate_by_row = [0] * (reduced_end - reduced_start)
    local_hermitian_nnz = 0
    for full_row, reduced_columns in full_to_reduced_columns.items():
        candidate_count = intermediate_candidate_by_full_row[full_row]
        for reduced_row in reduced_columns:
            if reduced_start <= reduced_row < reduced_end:
                local_hermitian_nnz += 1
                local_reduced_candidate_by_row[reduced_row - reduced_start] += (
                    candidate_count
                )

    scalar_bytes = int(np.dtype(PETSc.ScalarType).itemsize)
    int_bytes = int(np.dtype(PETSc.IntType).itemsize)
    local_k1_nnz = int(k1_rank_layout["local_nz_used"])
    local_constraint_nnz = int(local_constraint_layout["local_nz_used"])
    local_k1c_candidates = sum(
        count for _row, count in intermediate_rows
    )
    local_reduced_candidates = sum(local_reduced_candidate_by_row)
    local_full_rows = k1_row_end - k1_row_start
    local_reduced_rows = reduced_end - reduced_start

    def conservative_aij_bytes(entries: int, rows: int) -> int:
        # Treat every candidate as value/column storage, a possible remote
        # column, and a conservative remote-row stash entry. MatInfo from an
        # eventual MatMatMult remains the actual calibration source.
        return int(
            entries * (scalar_bytes + 2 * int_bytes + scalar_bytes + 2 * int_bytes)
            + 2 * (rows + 1) * int_bytes
        )

    local_k1c_bytes = conservative_aij_bytes(
        local_k1c_candidates, local_full_rows
    )
    local_hermitian_bytes = conservative_aij_bytes(
        local_hermitian_nnz, local_reduced_rows
    )
    local_reduced_bytes = conservative_aij_bytes(
        local_reduced_candidates, local_reduced_rows
    )
    max_row_scan_scratch_bytes = int(
        max(full_size, reduced_size)
        * (scalar_bytes + int_bytes + 1 + 96)
    )
    basis_errors: list[str] = []
    basis_scratch_bytes = 0
    try:
        source_objects = basis.get("source_derived_objects")
        if not isinstance(source_objects, Mapping):
            raise TypeError("source-derived object inventory is missing")
        basis_scratch_bytes = _task42_k1_exact_integer(
            source_objects.get("source_basis_validation_scratch_peak_bytes"),
            "source basis validation scratch bytes",
        )
        if basis_scratch_bytes < 0:
            raise ValueError("source basis validation scratch bytes is negative")
    except Exception as exc:  # noqa: BLE001 - basis failure reaches a collective safe point
        basis_errors.append(f"{type(exc).__name__}:{exc}")
    synchronized_basis_errors = _task42_k1_collective_errors(
        comm, basis_errors, "source_basis_scratch"
    )
    if synchronized_basis_errors:
        return {}, synchronized_basis_errors
    c_support_scratch = int(
        constraint_layout["row_support_capture_scratch_estimate_bytes"]
    )
    candidate_exchange_scratch = int(
        full_size * (128 + 8 + 32) + local_full_rows * 64
    )
    inventory_scratch_peak = int(
        c_support_scratch
        + candidate_exchange_scratch
        + max_row_scan_scratch_bytes
        + basis_scratch_bytes
    )
    simultaneous_product_payload = int(
        local_hermitian_bytes + local_k1c_bytes + local_reduced_bytes
    )
    rank_known_peak = max(inventory_scratch_peak, simultaneous_product_payload)
    return {
        "full_k1_local_nz_used": local_k1_nnz,
        "constraint_transform_local_nz_used": local_constraint_nnz,
        "constraint_transform_global_nz_used": constraint_layout["global_nz_used"],
        "constraint_transform_row_support_sha256": constraint_layout[
            "row_support_sha256"
        ],
        "full_k1_row_support_candidate_entries_local": local_k1c_candidates,
        "full_k1_row_support_candidate_entries_global": sum(
            intermediate_candidate_by_full_row
        ),
        "reduced_k1_candidate_entries_local_before_duplicate_merge": (
            local_reduced_candidates
        ),
        "reduced_k1_candidate_entries_global_before_duplicate_merge": sum(
            intermediate_candidate_by_full_row[full_row] * len(reduced_columns)
            for full_row, reduced_columns in full_to_reduced_columns.items()
        ),
        "hermitian_transform_nz_local": local_hermitian_nnz,
        "full_K1_nz_by_rank": [
            int(row["local_nz_used"]) for row in k1_layout["rank_layouts"]
        ],
        "constraint_nz_by_rank": [
            int(row["local_nz_used"])
            for row in constraint_layout["rank_layouts"]
        ],
        "K1_row_ranges_by_rank": [
            list(row["row_range"]) for row in k1_layout["rank_layouts"]
        ],
        "reduced_row_ranges_by_rank": [
            list(row["column_range"])
            for row in constraint_layout["rank_layouts"]
        ],
        "full_K1_row_support_sha256_by_rank": [
            str(value["row_support_sha256"]) for value in k1_support_by_rank
        ],
        "full_K1_row_support_owned_count_by_rank": [
            int(value["owned_row_count"]) for value in k1_support_by_rank
        ],
        "max_full_K1_row_nz_by_rank": [
            int(value["max_row_nnz"]) for value in k1_support_by_rank
        ],
        "local_payload_estimates_bytes": {
            "C_H_transpose": local_hermitian_bytes,
            "full_K1_times_C": local_k1c_bytes,
            "reduced_K1": local_reduced_bytes,
            "inventory_scratch_peak": inventory_scratch_peak,
            "bounded_one_row_input_CSR_scan_scratch": max_row_scan_scratch_bytes,
            "simultaneous_sparse_product_payload": simultaneous_product_payload,
            "product_payload_lifetime": (
                "C^H, K1*C, and reduced K1 may overlap during the second MatMult; "
                "support-capture scratch is released when inventory returns, before any "
                "product is created; no output-CSR validation copy is made in this gate"
            ),
            "predicted_peak": rank_known_peak,
        },
        "predicted_rank_peak_bytes": rank_known_peak,
        "rank_envelope_bytes": _TASK42_K0_RANK_BYTES,
        "rank_envelope_is_hard_bound": False,
        "uncertainty": (
            "source-derived CSR candidate counts use actual K1/C row structure and ownership; duplicate merging, PETSc MatMatMult workspace, remote communication, allocator overhead, and final MatInfo remain unmeasured"
        ),
    }, []


def _task42_k1_phase_inventory(
    phase: str,
    cfg: SimulationConfig3D,
    cross_section: CrossSectionMesh,
    spaces: CrossSectionSpaces,
    degree_context: Mapping[str, int],
    task42_sizing_identity: Mapping[str, Any] | None,
    *,
    compiled_form: Any | None = None,
    allocation_boundary: str | None = None,
    matrix: Any | None = None,
    transform: Any | None = None,
    call_context: str = "production_full_qep",
    local_basis_errors: tuple[str, ...] = (),
) -> dict[str, Any]:
    from ..common.task42_phase_admission import task42_phase_inventory

    inventory = task42_phase_inventory(phase)
    comm = cross_section.mesh.comm
    rank = int(comm.rank)
    mpi_size = int(comm.size)
    admission_errors: list[str] = list(local_basis_errors)
    source_basis: dict[str, Any] = {}
    caller_transform_ready = True
    if call_context not in {"production_full_qep", "k1_only_sizing"}:
        admission_errors.append("task42_k1_call_context_is_unknown")
    if call_context == "k1_only_sizing":
        local_transform_errors: list[str] = []
        if transform is None:
            local_transform_errors.append("caller_constraint_transform_is_missing")
        else:
            try:
                caller_matrix = getattr(transform, "matrix", None)
                if caller_matrix is None:
                    local_transform_errors.append(
                        "caller_constraint_transform_matrix_is_missing"
                    )
                else:
                    required_matrix_methods = (
                        "getSize",
                        "getOwnershipRange",
                        "getOwnershipRangeColumn",
                        "getInfo",
                    )
                    if phase == "qep_operator_K1_reduced":
                        required_matrix_methods += ("getRow",)
                    missing_methods = [
                        name
                        for name in required_matrix_methods
                        if not callable(getattr(caller_matrix, name, None))
                    ]
                    if missing_methods:
                        local_transform_errors.append(
                            "caller_constraint_transform_matrix_missing_methods:"
                            + ",".join(missing_methods)
                        )
                for field in (
                    "full_global_size",
                    "reduced_global_size",
                    "full_local_size",
                    "reduced_local_size",
                    "global_slave_count",
                ):
                    _task42_k1_exact_integer(
                        getattr(transform, field),
                        f"caller transform {field}",
                    )
            except Exception as exc:  # noqa: BLE001 - synchronize local API errors
                local_transform_errors.append(
                    "caller_constraint_transform_metadata_invalid:"
                    f"{type(exc).__name__}:{exc}"
                )
        synchronized_transform_errors = _task42_k1_collective_errors(
            comm, local_transform_errors, "K1_caller_transform"
        )
        admission_errors.extend(synchronized_transform_errors)
        caller_transform_ready = not synchronized_transform_errors
    try:
        shared_basis = _task42_k0_source_basis(
            cfg,
            cross_section,
            spaces,
            degree_context,
            task42_sizing_identity,
            rank=rank,
            mpi_size=mpi_size,
            compiled_form=compiled_form,
        )
        admission_errors.extend(
            error.replace("qep_K0", "qep_K1").replace(
                "Task42 K0", "Task42 K1"
            )
            for error in _task42_k0_calibration_scope_errors(
                shared_basis, mpi_size=mpi_size
            )
        )
        source_basis = {
            "schema": "task42.qep_k1_rank_basis.v1",
            "derived_from_shared_source_basis": "task42.qep_k0_rank_basis.v1",
            "shared_qep_source_basis": shared_basis,
            "component_phase": phase,
        }
    except Exception as exc:  # noqa: BLE001 - preserve local source-basis cause
        admission_errors.append(
            f"task42_k1_source_basis_unavailable:{type(exc).__name__}:{exc}"
        )

    boundaries = {
        "qep_operator_K1_ffcx_form": {
            "before_ufl_form_context_and_form",
            "before_fem_form_jit_after_constraints_transform",
        },
        "qep_operator_K1_full": {"after_fem_form_jit_before_petsc_matrix"},
        "qep_operator_K1_reduced": {"before_hermitian_transform_or_product"},
    }
    selected_boundary = allocation_boundary or phase
    if call_context == "k1_only_sizing":
        boundaries["qep_operator_K1_ffcx_form"].add(
            "before_fem_form_jit_with_caller_transform"
        )
    if selected_boundary not in boundaries.get(phase, set()):
        admission_errors.append("task42_k1_allocation_boundary_is_invalid_for_phase")
        source_basis = {}
    if (
        call_context == "k1_only_sizing"
        and phase != "qep_operator_K1_reduced"
        and caller_transform_ready
    ):
        c_layout, c_errors = _task42_k1_matrix_layout(
            transform.matrix,
            "caller_constraint_transform",
            comm,
            max_global_nz_used=3888 + 145 * 6,
        )
        admission_errors.extend(c_errors)
        if c_layout is not None:
            if c_layout["shape"] != [4033, 3888]:
                admission_errors.append(
                    "caller_constraint_transform_shape_differs_from_profile"
                )
            try:
                c_local = c_layout["rank_layouts"][rank]
                if _task42_k1_exact_integer(
                    transform.full_global_size,
                    "caller transform full global size",
                ) != 4033:
                    admission_errors.append(
                        "caller_transform_full_global_size_differs_from_profile"
                    )
                if _task42_k1_exact_integer(
                    transform.reduced_global_size,
                    "caller transform reduced global size",
                ) != 3888:
                    admission_errors.append(
                        "caller_transform_reduced_global_size_differs_from_profile"
                    )
                if _task42_k1_exact_integer(
                    transform.global_slave_count,
                    "caller transform global slave count",
                ) != 145:
                    admission_errors.append(
                        "caller_transform_slave_count_differs_from_profile"
                    )
                if _task42_k1_exact_integer(
                    transform.full_local_size,
                    "caller transform full local size",
                ) != c_local["row_range"][1] - c_local["row_range"][0]:
                    admission_errors.append(
                        "caller_transform_full_local_size_differs_from_layout"
                    )
                if _task42_k1_exact_integer(
                    transform.reduced_local_size,
                    "caller transform reduced local size",
                ) != (
                    c_local["column_range"][1]
                    - c_local["column_range"][0]
                ):
                    admission_errors.append(
                        "caller_transform_reduced_local_size_differs_from_layout"
                    )
            except Exception as exc:  # noqa: BLE001 - retain local cause for gate
                admission_errors.append(
                    "caller_transform_metadata_invalid:"
                    f"{type(exc).__name__}:{exc}"
                )
            source_basis["caller_constraint_transform_layout"] = c_layout
    if phase == "qep_operator_K1_reduced":
        if matrix is None or transform is None:
            admission_errors.append("task42_k1_reduction_requires_live_K1_and_transform")
            source_basis = {}
        # All ranks decide whether the source identity is valid before any
        # rank enters the matrix-support collectives below.
        source_errors = _task42_k1_collective_errors(
            comm, admission_errors, "K1_source_basis"
        )
        admission_errors = list(source_errors)
        if not source_errors and source_basis and matrix is not None and transform is not None:
            reduction_basis, reduction_errors = _task42_k1_reduction_basis(
                matrix,
                transform,
                comm=comm,
                full_size=4033,
                reduced_size=3888,
                expected_slave_count=145,
                basis=source_basis["shared_qep_source_basis"],
            )
            source_basis["reduction_support"] = reduction_basis
            admission_errors.extend(reduction_errors)
        elif source_errors:
            source_basis["reduction_support"] = {}

    if phase == "qep_operator_K1_ffcx_form":
        amounts = {
            "qep_k1_ffcx_rank_payload": _TASK42_K0_RANK_BYTES,
            "qep_k1_ffcx_rank0_compiler_subtree": (
                _TASK42_K0_COMPILER_SUBTREE_BYTES if rank == 0 else 0
            ),
            "qep_k1_ffcx_controller_allowance": (
                _TASK42_K0_CONTROLLER_BYTES if rank == 0 else 0
            ),
        }
    elif phase == "qep_operator_K1_full":
        amounts = {
            "full_K1_sparse_matrix": _TASK42_K0_RANK_BYTES,
            "qep_k1_full_controller_allowance": (
                _TASK42_K0_CONTROLLER_BYTES if rank == 0 else 0
            ),
        }
    elif phase == "qep_operator_K1_reduced":
        amounts = {
            "k1_hermitian_reduction_rank_payload": _TASK42_K0_RANK_BYTES,
            "qep_k1_reduction_controller_allowance": (
                _TASK42_K0_CONTROLLER_BYTES if rank == 0 else 0
            ),
        }
    else:
        raise ValueError(f"unsupported Task42 K1 phase {phase!r}")

    if source_basis and phase != "qep_operator_K1_reduced":
        shared_source = source_basis.get("shared_qep_source_basis")
        try:
            if not isinstance(shared_source, Mapping):
                raise TypeError("shared K0-derived source basis is missing")
            objects = shared_source["source_derived_objects"]
            cell_rows = objects["mixed_cell_dof_rows"]
            scratch = _task42_k1_exact_integer(
                objects["source_basis_validation_scratch_peak_bytes"],
                "source basis scratch bytes",
            )
            metadata = _task42_k1_exact_integer(
                objects["cell_dof_rows_python_metadata_bytes_upper"],
                "cell row metadata bytes",
            )
            known = _task42_k1_exact_integer(
                cell_rows["local_cell_tensor_payload_bytes_sum"],
                "local cell tensor payload bytes",
            ) + scratch + metadata
            if phase == "qep_operator_K1_full":
                known += _task42_k1_exact_integer(
                    objects["matrix_candidate_contributions"][
                        "candidate_sparse_payload_bytes_upper"
                    ],
                    "matrix candidate payload bytes",
                )
            if min(scratch, metadata, known) < 0:
                raise ValueError("source-derived K1 byte inventory is negative")
        except Exception as exc:  # noqa: BLE001 - retain cause, never substitute zero
            known = None
            admission_errors.append(
                f"qep_K1_source_basis_bytes_unavailable:{type(exc).__name__}:{exc}"
            )
        source_basis["phase_prediction"] = {
            "known_source_derived_rank_payload_bytes": known,
            "rank_envelope_bytes": _TASK42_K0_RANK_BYTES,
            "rank_allowance_is_hard_bound": False,
            "formula": (
                "K1 uses the live p6 mixed cell rows and shared K0 source-basis capture; full-K1 includes the all-cell 36*133^2 candidate sparse payload per rank; all native compiler/PETSc workspace remains predicted inside the accepted envelope"
            ),
        }
        if known is None:
            admission_errors.append("qep_K1_source_objects_have_unknown_bytes")
        elif known > _TASK42_K0_RANK_BYTES:
            admission_errors.append("qep_K1_source_objects_exceed_64MiB_envelope")

    if source_basis and phase == "qep_operator_K1_reduced":
        support = source_basis.get("reduction_support", {})
        if not support:
            admission_errors.append("qep_K1_reduction_support_inventory_is_missing")
            source_basis["phase_prediction"] = {
                "known_source_derived_rank_payload_bytes": None,
                "rank_envelope_bytes": _TASK42_K0_RANK_BYTES,
                "rank_allowance_is_hard_bound": False,
                "formula": (
                    "unavailable: source/layout/CSR support validation failed; no byte value is substituted and every K1 reduction Delta remains null"
                ),
                "inventory_scratch_peak_bytes": None,
            }
        else:
            prediction = support["local_payload_estimates_bytes"]
            source_basis["phase_prediction"] = {
                "known_source_derived_rank_payload_bytes": int(
                    support["predicted_rank_peak_bytes"]
                ),
                "rank_envelope_bytes": _TASK42_K0_RANK_BYTES,
                "rank_allowance_is_hard_bound": False,
                "formula": (
                    "max(pre-product support-inventory scratch, including one bounded input getRow row-scan temporary, simultaneous C^H + K1*C + reduced-K1 candidate sparse payload); support scratch is released when inventory returns before products are created; no output CSR copy is made here; MatMatMult native workspace is uncalibrated"
                ),
                "local_payload_estimates_bytes": prediction,
            }
            if int(support["predicted_rank_peak_bytes"]) > _TASK42_K0_RANK_BYTES:
                admission_errors.append("qep_K1_reduction_objects_exceed_64MiB_envelope")

    if source_basis:
        if not isinstance(source_basis.get("phase_prediction"), Mapping):
            source_basis["phase_prediction"] = {
                "known_source_derived_rank_payload_bytes": None,
                "rank_envelope_bytes": _TASK42_K0_RANK_BYTES,
                "rank_allowance_is_hard_bound": False,
                "formula": (
                    "unavailable: required source or reduction inventory is missing; "
                    "no byte value is substituted and the phase Delta remains null"
                ),
            }
            admission_errors.append("qep_K1_phase_prediction_is_unavailable")
        for _ in range(4):
            basis_json_bytes = _task42_json_utf8_size(source_basis)
            component_count = len(inventory["components"])
            per_component_basis_bytes = basis_json_bytes + 1024
            rank_metadata_bytes = (
                component_count * per_component_basis_bytes
                + _TASK42_K0_METADATA_MARGIN_BYTES
            )
            gate_metadata_bytes = int(
                2 * rank_metadata_bytes
                + mpi_size * rank_metadata_bytes
                + _TASK42_K0_METADATA_MARGIN_BYTES
            )
            controller_metadata_bytes = int(
                2 * mpi_size * rank_metadata_bytes
                + _TASK42_K0_METADATA_MARGIN_BYTES
            )
            source_basis["phase_prediction"].update(
                {
                    "basis_json_probe_bytes": basis_json_bytes,
                    "rank_inventory_metadata_bytes_upper": rank_metadata_bytes,
                    "allgather_and_rank_local_gate_metadata_bytes_upper": (
                        gate_metadata_bytes
                    ),
                    "root_controller_receipt_metadata_bytes_upper": (
                        controller_metadata_bytes
                    ),
                }
            )
        known_rank_payload = source_basis["phase_prediction"].get(
            "known_source_derived_rank_payload_bytes"
        )
        controller_known = int(
            source_basis["phase_prediction"][
                "root_controller_receipt_metadata_bytes_upper"
            ]
        )
        if type(known_rank_payload) is int:
            rank_known = int(
                known_rank_payload
                + source_basis["phase_prediction"][
                    "allgather_and_rank_local_gate_metadata_bytes_upper"
                ]
            )
        else:
            rank_known = None
            admission_errors.append("qep_K1_rank_inventory_bytes_are_unknown")
        if rank_known is not None and rank_known > _TASK42_K0_RANK_BYTES:
            admission_errors.append("qep_K1_rank_inventory_exceeds_64MiB_envelope")
        if controller_known > _TASK42_K0_CONTROLLER_BYTES:
            admission_errors.append("qep_K1_controller_inventory_exceeds_8MiB_envelope")

    if not source_basis:
        source_basis = {}
    if phase == "qep_operator_K1_ffcx_form":
        uncertainty = (
            "predicted only for the source-checked 36-quad p6/g1 DG0/c0 q16 4033-row MPI8 profile; rank payload 64MiB, rank-0 compiler subtree 512MiB, controller 8MiB once; not a hard bound or measured peak"
        )
    elif phase == "qep_operator_K1_full":
        uncertainty = (
            "predicted only for the same source-checked p6 profile; full-K1 64MiB per rank plus controller 8MiB once; actual K1 MatInfo is not yet measured and PETSc workspace is uncalibrated"
        )
    else:
        uncertainty = (
            "predicted from live K1/C sparse row support and ownership for the same source-checked p6 profile; 64MiB per rank plus controller 8MiB once; duplicate merging and native MatMatMult workspace are not yet measured"
        )

    admission_errors = _task42_k1_collective_errors(
        comm, admission_errors, "K1_phase_inventory"
    )
    component_rows = []
    for component in inventory["components"]:
        item = dict(component)
        name = str(item["name"])
        item["delta_bytes"] = None if admission_errors else int(amounts[name])
        item["sizing_basis"] = (
            {**source_basis, "component": name} if source_basis else {}
        )
        item["uncertainty"] = uncertainty
        item["classification"] = "predicted"
        item["upper_bound_proven"] = False
        component_rows.append(item)

    if call_context == "k1_only_sizing":
        resident_by_boundary = {
            "before_ufl_form_context_and_form": [
                "cross_section_mesh_and_DG0_coefficients",
                "mixed_and_collapsed_spaces",
                "caller_supplied_distributed_constraint_transform",
            ],
            "before_fem_form_jit_with_caller_transform": [
                "cross_section_mesh_and_DG0_coefficients",
                "mixed_and_collapsed_spaces",
                "caller_supplied_distributed_constraint_transform",
                "UFL_K1_form",
            ],
            "after_fem_form_jit_before_petsc_matrix": [
                "cross_section_mesh_and_DG0_coefficients",
                "mixed_and_collapsed_spaces",
                "caller_supplied_distributed_constraint_transform",
                "UFL_K1_form",
                "compiled_K1_form",
            ],
            "before_hermitian_transform_or_product": [
                "cross_section_mesh_and_DG0_coefficients",
                "mixed_and_collapsed_spaces",
                "caller_supplied_distributed_constraint_transform",
                "UFL_K1_form",
                "full_K1_sparse_matrix",
            ],
        }
    else:
        resident_by_boundary = {
            "before_ufl_form_context_and_form": [
                "cross_section_mesh_and_DG0_coefficients",
                "mixed_and_collapsed_spaces",
            ],
            "before_fem_form_jit_after_constraints_transform": [
                "cross_section_mesh_and_DG0_coefficients",
                "mixed_and_collapsed_spaces",
                "UFL_QEP_forms",
                "Floquet_constraints",
                "distributed_constraint_transform",
                "full_K0_sparse_matrix",
            ],
            "after_fem_form_jit_before_petsc_matrix": [
                "cross_section_mesh_and_DG0_coefficients",
                "mixed_and_collapsed_spaces",
                "UFL_QEP_forms",
                "Floquet_constraints",
                "distributed_constraint_transform",
                "full_K0_sparse_matrix",
                "compiled_K1_form",
            ],
            "before_hermitian_transform_or_product": [
                "cross_section_mesh_and_DG0_coefficients",
                "mixed_and_collapsed_spaces",
                "UFL_QEP_forms",
                "Floquet_constraints",
                "distributed_constraint_transform",
                "full_K0_sparse_matrix",
                "full_K1_sparse_matrix",
                "full_K2_sparse_matrix",
                "full_electric_mass_sparse_matrix",
                "reduced_K0_sparse_matrix",
            ],
        }
    inventory.update(
        {
            "schema": "task42.direct_phase_delta_inventory.v1",
            "status": "source-derived-prediction",
            "estimate_uncertainty": uncertainty,
            "evidence": {
                "source": "live QEP config, mixed/collapsed layouts, PETSc K1/C CSR support, and ABI",
                "rank": rank,
                "mpi_size": mpi_size,
                "basis_schema": "task42.qep_k1_rank_basis.v1",
                "call_context": call_context,
                "allocation_boundary": selected_boundary,
                "resident_objects_at_fresh_snapshot": resident_by_boundary.get(
                    selected_boundary, []
                ),
                "same_phase_delta_semantics": (
                    "FFCx admission is checked before UFL, then rechecked against fresh J immediately before compile; sizing entry also checks with its caller transform already resident. Rechecks use the same phase Delta and are not cumulative charges"
                ),
                "source_sha_semantics": (
                    "source hash format is checked in the helper; public-runner attestation binds the actual Git source"
                ),
            },
            "components": component_rows,
            "admission_errors": admission_errors,
        }
    )
    return inventory


def _qep_form_context(
    cfg: SimulationConfig3D,
    cross_section: CrossSectionMesh,
    spaces: CrossSectionSpaces,
):
    Et, Ez = ufl.TrialFunctions(spaces.mixed)
    Vt, Vz = ufl.TestFunctions(spaces.mixed)
    dx = ufl.Measure("dx", domain=cross_section.mesh)
    mu_inv = complex(1.0 / cfg.mu_r)
    k0_squared = float(cfg.k0**2)
    return Et, Ez, Vt, Vz, dx, mu_inv, k0_squared, cross_section.epsilon_r


def _build_full_k0_form(context):
    Et, Ez, Vt, Vz, dx, mu_inv, k0_squared, epsilon_r = context
    return (
        mu_inv * ufl.inner(ufl.curl(Et), ufl.curl(Vt))
        - k0_squared * ufl.inner(epsilon_r * Et, Vt)
        + mu_inv * ufl.inner(ufl.grad(Ez), ufl.grad(Vz))
        - k0_squared * ufl.inner(epsilon_r * Ez, Vz)
    ) * dx


def _build_full_k1_form(context):
    Et, Ez, Vt, Vz, dx, mu_inv = context[:6]
    return (
        1j * mu_inv * ufl.inner(ufl.grad(Ez), Vt)
        - 1j * mu_inv * ufl.inner(Et, ufl.grad(Vz))
    ) * dx


def _compile_unconstrained_form(form, *, quadrature_degree: int):
    return fem.form(
        form,
        form_compiler_options={"quadrature_degree": int(quadrature_degree)},
    )


def _assemble_compiled_unconstrained_matrix(compiled_form) -> PETSc.Mat:
    matrix = fem_petsc.assemble_matrix(compiled_form, bcs=[])
    try:
        matrix.assemble()
    except BaseException as primary_error:
        try:
            matrix.destroy()
        except BaseException as cleanup_error:  # noqa: BLE001 - preserve assembly failure
            primary_error.add_note(
                "Cleanup of the newly assembled-form matrix also failed: "
                f"{type(cleanup_error).__name__}: {cleanup_error}"
            )
        raise
    return matrix


def _assemble_unconstrained_matrix(form, *, quadrature_degree: int) -> PETSc.Mat:
    compiled_form = _compile_unconstrained_form(
        form, quadrature_degree=quadrature_degree
    )
    return _assemble_compiled_unconstrained_matrix(compiled_form)


def _admit_task42_k0_phase(
    task42_phase_gate,
    phase: str,
    cfg: SimulationConfig3D,
    cross_section: CrossSectionMesh,
    spaces: CrossSectionSpaces,
    degree_context: Mapping[str, int],
    task42_sizing_identity: Mapping[str, Any] | None,
    *,
    compiled_form: Any | None = None,
    allocation_boundary: str | None = None,
    constraints_transform_resident: bool = False,
    local_basis_errors: tuple[str, ...] = (),
) -> Mapping[str, Any]:
    from ..common.task42_phase_admission import require_task42_phase_admission

    inventory = _task42_k0_phase_inventory(
        phase,
        cfg,
        cross_section,
        spaces,
        degree_context,
        task42_sizing_identity,
        compiled_form=compiled_form,
        allocation_boundary=allocation_boundary,
        constraints_transform_resident=constraints_transform_resident,
        local_basis_errors=local_basis_errors,
    )
    return require_task42_phase_admission(task42_phase_gate, phase, inventory)


def _admit_task42_k1_phase(
    task42_phase_gate,
    phase: str,
    cfg: SimulationConfig3D,
    cross_section: CrossSectionMesh,
    spaces: CrossSectionSpaces,
    degree_context: Mapping[str, int],
    task42_sizing_identity: Mapping[str, Any] | None,
    **inventory_options,
) -> Mapping[str, Any]:
    from ..common.task42_phase_admission import require_task42_phase_admission

    inventory = _task42_k1_phase_inventory(
        phase,
        cfg,
        cross_section,
        spaces,
        degree_context,
        task42_sizing_identity,
        **inventory_options,
    )
    decision = require_task42_phase_admission(task42_phase_gate, phase, inventory)
    admission_errors = inventory.get("admission_errors", [])
    if admission_errors:
        raise RuntimeError(
            f"Task42 K1 phase {phase} refused before allocation: "
            f"{admission_errors}"
        )
    return decision


def _task42_degree_context_with_error(
    cross_section: CrossSectionMesh,
    spaces: CrossSectionSpaces,
    requested_quadrature_degree: int | None,
) -> tuple[dict[str, int], tuple[str, ...]]:
    try:
        return (
            _qep_degree_context(
                cross_section, spaces, requested_quadrature_degree
            ),
            (),
        )
    except Exception as exc:  # noqa: BLE001 - preserve the local cause for collective refusal
        return {}, (
            f"task42_qep_degree_context_failed:{type(exc).__name__}:{exc}",
        )


def _destroy_task42_transform_on_refusal(transform: Any, primary: RuntimeError) -> None:
    """Destroy a transform only after a unanimous pre-allocation refusal."""

    if "refused before allocation" not in str(primary):
        return
    try:
        transform.matrix.destroy()
    except BaseException as cleanup_error:  # noqa: BLE001 - keep the unanimous refusal primary
        primary.add_note(
            "Task42 K0 refusal transform cleanup also failed: "
            f"{type(cleanup_error).__name__}: {cleanup_error}"
        )


def _destroy_task42_partial_full_operators(
    full_matrices: list[PETSc.Mat], transform: Any, primary: BaseException
) -> None:
    for index, matrix in enumerate(reversed(full_matrices)):
        try:
            matrix.destroy()
        except BaseException as cleanup_error:  # noqa: BLE001 - preserve first failure
            primary.add_note(
                f"Cleanup of partial full QEP matrix {index} also failed: "
                f"{type(cleanup_error).__name__}: {cleanup_error}"
            )
    try:
        transform.matrix.destroy()
    except BaseException as cleanup_error:  # noqa: BLE001 - preserve first failure
        primary.add_note(
            "Cleanup of the owned Task42 constraint transform also failed: "
            f"{type(cleanup_error).__name__}: {cleanup_error}"
        )


def assemble_full_k0_for_sizing(
    cfg: SimulationConfig3D,
    cross_section: CrossSectionMesh,
    spaces: CrossSectionSpaces,
    *,
    task42_phase_gate=None,
    task42_sizing_identity: Mapping[str, Any] | None = None,
    quadrature_degree: int | None = None,
) -> PETSc.Mat:
    """Compile and assemble only full K0 behind both Task42 preallocation gates.

    This source-derived sizing entrypoint is intentionally unavailable without
    the public-worker phase callback. It does not build constraints, a reduced
    transform, K1/K2/mass, or an eigensolver object.
    """

    if not callable(task42_phase_gate):
        raise TypeError("Task42 full-K0 sizing requires the phase-gate callback")
    degree_context, degree_errors = _task42_degree_context_with_error(
        cross_section, spaces, quadrature_degree
    )
    _admit_task42_k0_phase(
        task42_phase_gate,
        "qep_operator_K0_ffcx_form",
        cfg,
        cross_section,
        spaces,
        degree_context,
        task42_sizing_identity,
        allocation_boundary="before_ufl_form_context_and_form",
        local_basis_errors=degree_errors,
    )
    form_context = _qep_form_context(cfg, cross_section, spaces)
    k0_form = _build_full_k0_form(form_context)
    compiled_form = None
    try:
        compiled_form = _compile_unconstrained_form(
            k0_form, quadrature_degree=degree_context["quadrature_degree"]
        )
        _admit_task42_k0_phase(
            task42_phase_gate,
            "qep_operator_K0_full",
            cfg,
            cross_section,
            spaces,
            degree_context,
            task42_sizing_identity,
            compiled_form=compiled_form,
            allocation_boundary="after_fem_form_jit_before_petsc_matrix",
        )
        return _assemble_compiled_unconstrained_matrix(compiled_form)
    finally:
        # fem.form has no explicit destroy method; dropping this sole local
        # reference releases its compiled wrapper on a rejected K0 gate.
        compiled_form = None


def assemble_reduced_k1_for_sizing(
    cfg: SimulationConfig3D,
    cross_section: CrossSectionMesh,
    spaces: CrossSectionSpaces,
    transform: DistributedConstraintTransform | None,
    *,
    task42_phase_gate=None,
    task42_sizing_identity: Mapping[str, Any] | None = None,
    quadrature_degree: int | None = None,
) -> PETSc.Mat:
    """Assemble and reduce only K1 using a caller-owned Floquet transform.

    This narrow sizing route never builds the full QEP operator bundle or
    constructs a constraint transform. The caller supplies an already
    admitted transform; this function compiles one K1 form, assembles one full
    K1 matrix, applies one Hermitian reduction, and returns reduced K1.
    """

    if not callable(task42_phase_gate):
        raise TypeError("Task42 reduced-K1 sizing requires the phase-gate callback")
    degree_context, degree_errors = _task42_degree_context_with_error(
        cross_section, spaces, quadrature_degree
    )
    _admit_task42_k1_phase(
        task42_phase_gate,
        "qep_operator_K1_ffcx_form",
        cfg,
        cross_section,
        spaces,
        degree_context,
        task42_sizing_identity,
        allocation_boundary="before_ufl_form_context_and_form",
        transform=transform,
        call_context="k1_only_sizing",
        local_basis_errors=degree_errors,
    )

    form_context = _qep_form_context(cfg, cross_section, spaces)
    k1_form = _build_full_k1_form(form_context)
    compiled_form = None
    full_k1 = None
    reduced_k1 = None
    try:
        _admit_task42_k1_phase(
            task42_phase_gate,
            "qep_operator_K1_ffcx_form",
            cfg,
            cross_section,
            spaces,
            degree_context,
            task42_sizing_identity,
            allocation_boundary="before_fem_form_jit_with_caller_transform",
            transform=transform,
            call_context="k1_only_sizing",
        )
        compiled_form = _compile_unconstrained_form(
            k1_form, quadrature_degree=degree_context["quadrature_degree"]
        )
        _admit_task42_k1_phase(
            task42_phase_gate,
            "qep_operator_K1_full",
            cfg,
            cross_section,
            spaces,
            degree_context,
            task42_sizing_identity,
            compiled_form=compiled_form,
            transform=transform,
            call_context="k1_only_sizing",
            allocation_boundary="after_fem_form_jit_before_petsc_matrix",
        )
        full_k1 = _assemble_compiled_unconstrained_matrix(compiled_form)
        _admit_task42_k1_phase(
            task42_phase_gate,
            "qep_operator_K1_reduced",
            cfg,
            cross_section,
            spaces,
            degree_context,
            task42_sizing_identity,
            matrix=full_k1,
            transform=transform,
            call_context="k1_only_sizing",
            allocation_boundary="before_hermitian_transform_or_product",
        )
        reduced_k1 = reduce_matrix_hermitian(full_k1, transform.matrix)

        owned_full_k1 = full_k1
        full_k1 = None
        owned_full_k1.destroy()
        result = reduced_k1
        reduced_k1 = None
        return result
    except BaseException as primary_error:
        for label, owned in (
            ("reduced K1 sizing result", reduced_k1),
            ("full K1 sizing matrix", full_k1),
        ):
            if owned is None:
                continue
            try:
                owned.destroy()
            except BaseException as cleanup_error:  # noqa: BLE001 - preserve first failure
                primary_error.add_note(
                    f"Cleanup of {label} also failed: "
                    f"{type(cleanup_error).__name__}: {cleanup_error}"
                )
        raise
    finally:
        # The compiled form wrapper has no explicit destroy API.
        compiled_form = None


def assemble_quadratic_beta_operators(
    cfg: SimulationConfig3D,
    cross_section: CrossSectionMesh,
    spaces: CrossSectionSpaces,
    *,
    quadrature_degree: int | None = None,
    log=None,
    task42_phase_gate=None,
    task42_sizing_identity: Mapping[str, Any] | None = None,
) -> QuadraticBetaOperators:
    """Assemble and explicitly Floquet-reduce the mixed Maxwell QEP.

    For ``E(x,y,z) = (Et(x,y), Ez(x,y)) exp(i beta z)`` the strong
    transverse/longitudinal split gives a genuine quadratic polynomial.  The
    beta-squared block acts only on ``Et``; its zero scalar block is physical,
    so the leading matrix is intentionally singular.
    """

    if np.dtype(PETSc.ScalarType) != np.dtype(np.complex128):
        raise RuntimeError("Task32 QEP requires PETSc complex128 scalar mode.")

    if task42_phase_gate is None:
        # Preserve the ordinary path's historical order: create the UFL
        # arguments/measure before selecting the compiler quadrature policy.
        form_context = _qep_form_context(cfg, cross_section, spaces)
        degree_context = _qep_degree_context(
            cross_section, spaces, quadrature_degree
        )
    else:
        degree_context, degree_errors = _task42_degree_context_with_error(
            cross_section, spaces, quadrature_degree
        )
        _admit_task42_k0_phase(
            task42_phase_gate,
            "qep_operator_K0_ffcx_form",
            cfg,
            cross_section,
            spaces,
            degree_context,
            task42_sizing_identity,
            allocation_boundary="before_ufl_form_context_and_form",
            local_basis_errors=degree_errors,
        )
        _admit_task42_k1_phase(
            task42_phase_gate,
            "qep_operator_K1_ffcx_form",
            cfg,
            cross_section,
            spaces,
            degree_context,
            task42_sizing_identity,
            allocation_boundary="before_ufl_form_context_and_form",
            local_basis_errors=degree_errors,
        )
        form_context = _qep_form_context(cfg, cross_section, spaces)

    # Task42's first K0 gate above precedes all UFL form construction.
    Et, Ez, Vt, Vz, dx, mu_inv = form_context[:6]
    a0 = _build_full_k0_form(form_context)
    a1 = _build_full_k1_form(form_context)
    a2 = mu_inv * ufl.inner(Et, Vt) * dx
    electric_mass = (ufl.inner(Et, Vt) + ufl.inner(Ez, Vz)) * dx

    if task42_phase_gate is not None:
        from src.common.task42_phase_admission import admit_task42_phase

        admit_task42_phase(task42_phase_gate, "qep_constraints")
    constraints = build_cross_section_floquet_constraints(
        cross_section,
        spaces,
        kx=complex(cfg.kx),
        ky=complex(cfg.ky),
    )
    if log is not None:
        log("QEP Floquet constraints built")
    if task42_phase_gate is not None:
        from src.common.task42_phase_admission import admit_task42_phase

        admit_task42_phase(task42_phase_gate, "qep_constraint_transform")
    transform = build_distributed_constraint_transform(spaces, constraints)
    if log is not None:
        log("QEP distributed constraint transform built")

    full_matrices = []
    for name, form in (
        ("K0", a0),
        ("K1", a1),
        ("K2", a2),
        ("electric_mass", electric_mass),
    ):
        if task42_phase_gate is not None:
            from src.common.task42_phase_admission import admit_task42_phase

            phase = (
                "qep_operator_electric_mass_full"
                if name == "electric_mass"
                else f"qep_operator_{name}_full"
            )
            if name == "K0":
                compiled_form = None
                try:
                    try:
                        _admit_task42_k0_phase(
                            task42_phase_gate,
                            "qep_operator_K0_ffcx_form",
                            cfg,
                            cross_section,
                            spaces,
                            degree_context,
                            task42_sizing_identity,
                            allocation_boundary=(
                                "before_fem_form_jit_after_constraints_transform"
                            ),
                            constraints_transform_resident=True,
                            local_basis_errors=degree_errors,
                        )
                    except RuntimeError as primary:
                        _destroy_task42_transform_on_refusal(transform, primary)
                        raise
                    compiled_form = _compile_unconstrained_form(
                        form,
                        quadrature_degree=degree_context["quadrature_degree"],
                    )
                    try:
                        _admit_task42_k0_phase(
                            task42_phase_gate,
                            phase,
                            cfg,
                            cross_section,
                            spaces,
                            degree_context,
                            task42_sizing_identity,
                            compiled_form=compiled_form,
                            allocation_boundary=(
                                "after_fem_form_jit_before_petsc_matrix"
                            ),
                            constraints_transform_resident=True,
                        )
                    except RuntimeError as primary:
                        _destroy_task42_transform_on_refusal(transform, primary)
                        raise
                    full_matrix = _assemble_compiled_unconstrained_matrix(
                        compiled_form
                    )
                finally:
                    compiled_form = None
            elif name == "K1":
                compiled_form = None
                try:
                    _admit_task42_k1_phase(
                        task42_phase_gate,
                        "qep_operator_K1_ffcx_form",
                        cfg,
                        cross_section,
                        spaces,
                        degree_context,
                        task42_sizing_identity,
                        allocation_boundary=(
                            "before_fem_form_jit_after_constraints_transform"
                        ),
                    )
                    compiled_form = _compile_unconstrained_form(
                        form,
                        quadrature_degree=degree_context["quadrature_degree"],
                    )
                    _admit_task42_k1_phase(
                        task42_phase_gate,
                        phase,
                        cfg,
                        cross_section,
                        spaces,
                        degree_context,
                        task42_sizing_identity,
                        compiled_form=compiled_form,
                        allocation_boundary=(
                            "after_fem_form_jit_before_petsc_matrix"
                        ),
                    )
                    full_matrix = _assemble_compiled_unconstrained_matrix(
                        compiled_form
                    )
                except BaseException as primary_error:
                    _destroy_task42_partial_full_operators(
                        full_matrices, transform, primary_error
                    )
                    raise
                finally:
                    compiled_form = None
            else:
                try:
                    admit_task42_phase(task42_phase_gate, phase)
                    full_matrix = _assemble_unconstrained_matrix(
                        form,
                        quadrature_degree=degree_context["quadrature_degree"],
                    )
                except BaseException as primary_error:
                    _destroy_task42_partial_full_operators(
                        full_matrices, transform, primary_error
                    )
                    raise
        else:
            full_matrix = _assemble_unconstrained_matrix(
                form, quadrature_degree=degree_context["quadrature_degree"]
            )
        full_matrices.append(full_matrix)
        if log is not None:
            log(f"QEP full {name} assembled")
    if task42_phase_gate is None:
        try:
            reduced_matrices = []
            transform_h = PETSc.Mat()
            transform.matrix.hermitianTranspose(transform_h)
            try:
                for name, matrix in zip(
                    ("K0", "K1", "K2", "electric_mass"), full_matrices
                ):
                    reduced_matrices.append(
                        reduce_matrix_hermitian(
                            matrix, transform.matrix, transform_h=transform_h
                        )
                    )
                    if log is not None:
                        log(f"QEP reduced {name} assembled")
            finally:
                transform_h.destroy()
        finally:
            for matrix in full_matrices:
                matrix.destroy()
    else:
        reduced_by_name: dict[str, PETSc.Mat] = {}
        try:
            for name, matrix in zip(
                ("K0", "K1", "K2", "electric_mass"), full_matrices
            ):
                phase = (
                    "qep_operator_electric_mass_reduced"
                    if name == "electric_mass"
                    else f"qep_operator_{name}_reduced"
                )
                if name == "K1":
                    _admit_task42_k1_phase(
                        task42_phase_gate,
                        phase,
                        cfg,
                        cross_section,
                        spaces,
                        degree_context,
                        task42_sizing_identity,
                        allocation_boundary="before_hermitian_transform_or_product",
                        matrix=matrix,
                        transform=transform,
                    )
                else:
                    from src.common.task42_phase_admission import admit_task42_phase

                    admit_task42_phase(task42_phase_gate, phase)
                # The Task42 gate precedes both the temporary C^H and the
                # first product. The ordinary path above retains its historic
                # shared transpose and matrix order.
                reduced_by_name[name] = reduce_matrix_hermitian(
                    matrix, transform.matrix
                )
                if log is not None:
                    log(f"QEP reduced {name} assembled")
        except BaseException as primary_error:
            for name, matrix in reversed(tuple(reduced_by_name.items())):
                try:
                    matrix.destroy()
                except BaseException as cleanup_error:  # noqa: BLE001 - preserve primary
                    primary_error.add_note(
                        f"Cleanup of partial reduced {name} also failed: "
                        f"{type(cleanup_error).__name__}: {cleanup_error}"
                    )
            for index, matrix in enumerate(reversed(full_matrices)):
                try:
                    matrix.destroy()
                except BaseException as cleanup_error:  # noqa: BLE001 - preserve primary
                    primary_error.add_note(
                        f"Cleanup of full QEP matrix {index} also failed: "
                        f"{type(cleanup_error).__name__}: {cleanup_error}"
                    )
            try:
                transform.matrix.destroy()
            except BaseException as cleanup_error:  # noqa: BLE001 - preserve primary
                primary_error.add_note(
                    "Cleanup of the owned Task42 constraint transform also failed: "
                    f"{type(cleanup_error).__name__}: {cleanup_error}"
                )
            raise
        else:
            for index, matrix in enumerate(reversed(full_matrices)):
                try:
                    matrix.destroy()
                except BaseException as cleanup_error:
                    for reduced in reduced_by_name.values():
                        try:
                            reduced.destroy()
                        except BaseException as nested_error:  # noqa: BLE001
                            cleanup_error.add_note(
                                "Cleanup of a reduced matrix also failed: "
                                f"{type(nested_error).__name__}: {nested_error}"
                            )
                    try:
                        transform.matrix.destroy()
                    except BaseException as nested_error:  # noqa: BLE001
                        cleanup_error.add_note(
                            "Cleanup of the owned transform also failed: "
                            f"{type(nested_error).__name__}: {nested_error}"
                        )
                    cleanup_error.add_note(
                        f"Cleanup of full QEP matrix {index} failed after reductions"
                    )
                    raise
            reduced_matrices = [
                reduced_by_name[name]
                for name in ("K0", "K1", "K2", "electric_mass")
            ]

    reduced_shape = tuple(map(int, reduced_matrices[0].getSize()))
    if reduced_shape[0] != reduced_shape[1]:
        raise RuntimeError(f"Reduced QEP matrices must be square, got {reduced_shape}.")
    if any(tuple(map(int, matrix.getSize())) != reduced_shape for matrix in reduced_matrices):
        raise RuntimeError("QEP coefficient and normalization matrix shapes differ.")

    return QuadraticBetaOperators(
        K0=reduced_matrices[0],
        K1=reduced_matrices[1],
        K2=reduced_matrices[2],
        electric_mass=reduced_matrices[3],
        transform=transform,
        constraints=constraints,
        full_shape=(transform.full_global_size, transform.full_global_size),
        reduced_shape=reduced_shape,
        scalar_dtype=str(np.dtype(PETSc.ScalarType)),
        field_degree=degree_context["field_degree"],
        geometry_degree=degree_context["geometry_degree"],
        coefficient_degree=degree_context["coefficient_degree"],
        quadrature_degree=degree_context["quadrature_degree"],
    )


def _polynomial_relative_residual(
    operators: QuadraticBetaOperators,
    beta: complex,
    vector: PETSc.Vec,
    *,
    operator_frobenius_norms: tuple[float, float, float] | None = None,
) -> float:
    residual = operators.K0.createVecLeft()
    work = operators.K0.createVecLeft()
    operators.K0.mult(vector, residual)
    operators.K1.mult(vector, work)
    residual.axpy(beta, work)
    operators.K2.mult(vector, work)
    residual.axpy(beta * beta, work)
    numerator = float(residual.norm(PETSc.NormType.NORM_2))
    vector_norm = float(vector.norm(PETSc.NormType.NORM_2))
    if operator_frobenius_norms is None:
        operator_frobenius_norms = tuple(
            float(matrix.norm(PETSc.NormType.FROBENIUS))
            for matrix in (operators.K0, operators.K1, operators.K2)
        )
    denominator = vector_norm * (
        operator_frobenius_norms[0]
        + abs(beta) * operator_frobenius_norms[1]
        + abs(beta) ** 2 * operator_frobenius_norms[2]
    )
    residual.destroy()
    work.destroy()
    return numerator / max(denominator, 1.0e-30)


def solve_quadratic_beta_modes(
    operators: QuadraticBetaOperators,
    *,
    target: complex,
    requested_modes: int = 8,
    tolerance: float = 1.0e-10,
    max_iterations: int = 500,
    operator_frobenius_norms: tuple[float, float, float] | None = None,
    task42_phase_gate=None,
    task42_eigensolve_phase: str = "qep_positive_eigensolve",
    task42_vectors_phase: str = "qep_positive_mode_vectors",
) -> tuple[list[QuadraticBetaMode], QuadraticBetaSolveReport]:
    """Solve a target slice with native distributed SLEPc PEP/TOAR."""

    if requested_modes < 1:
        raise ValueError("requested_modes must be positive.")
    if task42_phase_gate is not None:
        from src.common.task42_phase_admission import admit_task42_phase

        admit_task42_phase(task42_phase_gate, task42_eigensolve_phase)
    comm = operators.K0.comm
    pep = SLEPc.PEP().create(comm=comm)
    pep.setOperators([operators.K0, operators.K1, operators.K2])
    pep.setProblemType(SLEPc.PEP.ProblemType.GENERAL)
    pep.setType(SLEPc.PEP.Type.TOAR)
    pep.setDimensions(nev=int(requested_modes))
    pep.setTarget(complex(target))
    pep.setWhichEigenpairs(SLEPc.PEP.Which.TARGET_MAGNITUDE)
    pep.setTolerances(tol=float(tolerance), max_it=int(max_iterations))

    spectral_transform = pep.getST()
    spectral_transform.setType(SLEPc.ST.Type.SINVERT)
    ksp = spectral_transform.getKSP()
    ksp.setType(PETSc.KSP.Type.PREONLY)
    pc = ksp.getPC()
    pc.setType(PETSc.PC.Type.LU)
    pc.setFactorSolverType("mumps")
    pep.setFromOptions()
    pep.solve()

    converged = int(pep.getConverged())
    if operator_frobenius_norms is None:
        operator_frobenius_norms = tuple(
            float(matrix.norm(PETSc.NormType.FROBENIUS))
            for matrix in (operators.K0, operators.K1, operators.K2)
        )
    if task42_phase_gate is not None and converged:
        from src.common.task42_phase_admission import admit_task42_phase

        admit_task42_phase(task42_phase_gate, task42_vectors_phase)
    modes: list[QuadraticBetaMode] = []
    for index in range(converged):
        reduced = operators.K0.createVecRight()
        beta = complex(pep.getEigenpair(index, reduced))
        mass_action = operators.electric_mass.createVecLeft()
        operators.electric_mass.mult(reduced, mass_action)
        norm_squared = complex(reduced.dot(mass_action))
        if norm_squared.real <= 0.0 or abs(norm_squared.imag) > 1.0e-9 * max(
            abs(norm_squared.real), 1.0e-30
        ):
            mass_action.destroy()
            reduced.destroy()
            raise RuntimeError(
                f"Electric L2 normalization is not positive-real: {norm_squared!r}."
            )
        norm_before = float(np.sqrt(norm_squared.real))
        reduced.scale(1.0 / norm_before)
        operators.electric_mass.mult(reduced, mass_action)
        norm_after = float(np.sqrt(max(complex(reduced.dot(mass_action)).real, 0.0)))
        mass_action.destroy()
        full = operators.transform.matrix.createVecLeft()
        operators.transform.matrix.mult(reduced, full)
        ownership = EigenvectorOwnership(
            comm_size=comm.size,
            reduced_local_size=int(reduced.getLocalSize()),
            reduced_ownership_range=tuple(map(int, reduced.getOwnershipRange())),
            full_local_size=int(full.getLocalSize()),
            full_ownership_range=tuple(map(int, full.getOwnershipRange())),
        )
        modes.append(
            QuadraticBetaMode(
                beta=beta,
                right_reduced=reduced,
                right_full=full,
                polynomial_relative_residual=_polynomial_relative_residual(
                    operators,
                    beta,
                    reduced,
                    operator_frobenius_norms=operator_frobenius_norms,
                ),
                slepc_relative_error=float(
                    pep.computeError(index, SLEPc.PEP.ErrorType.RELATIVE)
                ),
                normalization_kind="cross_section_electric_L2",
                normalization_factor=norm_before,
                electric_l2_norm_after=norm_after,
                ownership=ownership,
            )
        )

    modes.sort(key=lambda mode: abs(mode.beta - target))
    if len(modes) > requested_modes:
        extras = modes[requested_modes:]
        modes = modes[:requested_modes]
        for mode in extras:
            mode.destroy()
    report = QuadraticBetaSolveReport(
        solver="SLEPc.PEP/TOAR",
        problem_type="general_quadratic_polynomial",
        spectral_transform="sinvert_with_MUMPS_LU",
        target=complex(target),
        requested_modes=int(requested_modes),
        converged_modes=converged,
        iteration_count=int(pep.getIterationNumber()),
        convergence_reason=int(pep.getConvergedReason()),
    )
    pep.destroy()
    return modes, report
