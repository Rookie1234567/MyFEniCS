"""Actual global two-level H(curl) correction estimator for Task035.

The estimator compares two solved finite-element fields. A coarse field is
interpolated into the enriched Nedelec space with DOLFINx's nonmatching-mesh
interpolation, then a non-negative L2 plus cell-scaled curl energy is assembled
once per owned fine cell. The implementation is independent of a benchmark
runner and does not alter the production solve path.
"""

from __future__ import annotations

from dataclasses import replace
import gc
import hashlib
import math
from pathlib import Path
import resource
import time
from typing import Any

import numpy as np
import ufl
from basix import ElementFamily, MapType, SobolevSpace
from basix.ufl import element
from mpi4py import MPI
from petsc4py import PETSc

from dolfinx import default_real_type, fem
from dolfinx.fem import petsc as fem_petsc

from .cell_indicator_snapshot import (
    build_cell_indicator_snapshot,
    validate_cell_indicator_snapshot,
)
from src.geometry.tetra_mesh_audit import (
    canonical_owned_cell_ids,
    geometry_key_sha256,
)


TINY = np.finfo(float).tiny


def _collective_fail_if_any(
    comm: MPI.Intracomm,
    local_error: str | None,
    *,
    context: str,
) -> None:
    errors = comm.allgather(local_error)
    failures = [
        f"rank {rank}: {error}"
        for rank, error in enumerate(errors)
        if error is not None
    ]
    if failures:
        raise ValueError(f"{context}: " + "; ".join(failures))


def _global_dorfler_mark(
    comm: MPI.Intracomm,
    global_cell_ids: np.ndarray,
    contributions: np.ndarray,
    *,
    theta: float,
) -> tuple[np.ndarray, dict[str, Any]]:
    ids = np.asarray(global_cell_ids, dtype=np.int64)
    values = np.asarray(contributions, dtype=np.float64)
    local_error = None
    if not 0.0 < float(theta) <= 1.0:
        local_error = "Dorfler theta must lie in (0, 1]"
    elif ids.shape != values.shape:
        local_error = "global cell ids and contributions have unequal shapes"
    elif not np.all(np.isfinite(values)) or np.any(values < 0.0):
        local_error = "Dorfler contributions must be finite and nonnegative"
    _collective_fail_if_any(
        comm,
        local_error,
        context="Dorfler local validation failed",
    )
    packets = comm.allgather((ids, values))
    all_ids = np.concatenate([packet[0] for packet in packets])
    all_values = np.concatenate([packet[1] for packet in packets])
    if len(np.unique(all_ids)) != len(all_ids):
        raise RuntimeError("owned-cell identifiers are not globally unique.")
    order = np.lexsort((all_ids, -all_values))
    total = float(np.sum(all_values))
    minimal_count = 0
    tie_tolerance = 0.0
    cutoff_normalized_contribution = 0.0
    if total <= TINY:
        marked = np.asarray([], dtype=np.int64)
    else:
        cutoff = float(theta) * total
        minimal_count = int(
            np.searchsorted(np.cumsum(all_values[order]), cutoff, side="left")
            + 1
        )
        count = minimal_count
        normalized = all_values / total
        cutoff_normalized_contribution = float(
            normalized[order[minimal_count - 1]]
        )
        tie_tolerance = max(
            1.0e-10 * abs(cutoff_normalized_contribution),
            64.0 * np.finfo(np.float64).eps,
        )
        while count < len(order) and (
            cutoff_normalized_contribution - normalized[order[count]]
            <= tie_tolerance
        ):
            count += 1
        marked = np.sort(all_ids[order[:count]])
    digest = hashlib.sha256(marked.astype("<i8", copy=False).tobytes()).hexdigest()
    return marked, {
        "theta": float(theta),
        "count": int(len(marked)),
        "minimal_count_before_tie_expansion": int(minimal_count),
        "cutoff_tie_expansion_count": int(len(marked) - minimal_count),
        "cutoff_normalized_contribution": cutoff_normalized_contribution,
        "cutoff_tie_absolute_tolerance": tie_tolerance,
        "tie_policy": "include_all_cutoff_contributions_within_relative_1e-10",
        "fraction": float(len(marked) / max(len(all_ids), 1)),
        "captured_fraction": (
            0.0
            if total <= TINY
            else float(np.sum(all_values[np.isin(all_ids, marked)]) / total)
        ),
        "global_cell_ids_sha256": digest,
    }


def _owned_cell_contributions(
    delta: fem.Function,
) -> tuple[np.ndarray, np.ndarray, dict[str, float]]:
    msh = delta.function_space.mesh
    comm = msh.comm
    tdim = msh.topology.dim
    cell_map = msh.topology.index_map(tdim)
    owned_cells = np.arange(cell_map.size_local, dtype=np.int32)
    global_cell_ids = np.asarray(
        cell_map.local_to_global(owned_cells), dtype=np.int64
    )

    scalar_space = fem.functionspace(msh, ("DG", 0))
    test = ufl.TestFunction(scalar_space)
    cell_diameter = ufl.CellDiameter(msh)
    density = ufl.real(
        ufl.inner(delta, delta)
        + cell_diameter**2 * ufl.inner(ufl.curl(delta), ufl.curl(delta))
    )
    vector = fem_petsc.assemble_vector(fem.form(ufl.inner(density, test) * ufl.dx))
    vector.ghostUpdate(
        addv=PETSc.InsertMode.ADD_VALUES,
        mode=PETSc.ScatterMode.REVERSE,
    )
    values = np.asarray(vector.getArray(readonly=True), dtype=np.complex128)
    owned_dof_count = int(scalar_space.dofmap.index_map.size_local)
    contributions = np.empty(len(owned_cells), dtype=np.float64)
    max_imaginary = 0.0
    local_ownership_error = None
    for index, cell in enumerate(owned_cells):
        dofs = scalar_space.dofmap.cell_dofs(int(cell))
        if len(dofs) != 1 or int(dofs[0]) >= owned_dof_count:
            local_ownership_error = (
                "DG0 owned-cell/dof ownership is not one-to-one"
            )
            break
        value = complex(values[int(dofs[0])])
        max_imaginary = max(max_imaginary, abs(value.imag))
        contributions[index] = value.real
    vector.destroy()
    _collective_fail_if_any(
        comm,
        local_ownership_error,
        context="cell-energy ownership validation failed",
    )

    direct_local = fem.assemble_scalar(fem.form(density * ufl.dx))
    direct_global = float(comm.allreduce(float(np.real(direct_local)), op=MPI.SUM))
    vector_global = float(comm.allreduce(float(np.sum(contributions)), op=MPI.SUM))
    scale = max(abs(direct_global), abs(vector_global), TINY)
    negative_tolerance = 1.0e-11 * scale
    local_minimum = float(np.min(contributions)) if len(contributions) else math.inf
    minimum = float(comm.allreduce(local_minimum, op=MPI.MIN))
    if minimum < -negative_tolerance:
        raise RuntimeError(
            "two-level cell energy contains a material negative contribution: "
            f"minimum={minimum:.6e}, tolerance={negative_tolerance:.6e}"
        )
    contributions = np.maximum(contributions, 0.0)
    vector_global_clamped = float(
        comm.allreduce(float(np.sum(contributions)), op=MPI.SUM)
    )
    closure = abs(vector_global_clamped - direct_global) / scale
    return global_cell_ids, contributions, {
        "direct_global_energy": direct_global,
        "cell_sum_global_energy": vector_global_clamped,
        "relative_closure_error": float(closure),
        "minimum_raw_cell_contribution": minimum,
        "maximum_imaginary_cell_contribution": float(
            comm.allreduce(max_imaginary, op=MPI.MAX)
        ),
    }


def _cell_coefficient_energies(
    field: fem.Function,
) -> np.ndarray:
    """Return the squared local coefficient norm on every owned cell."""

    msh = field.function_space.mesh
    owned_cells = int(msh.topology.index_map(msh.topology.dim).size_local)
    values = np.asarray(field.x.array, dtype=np.complex128)
    energies = np.empty(owned_cells, dtype=np.float64)
    for cell in range(owned_cells):
        dofs = field.function_space.dofmap.cell_dofs(cell)
        coefficients = values[dofs]
        energies[cell] = float(np.vdot(coefficients, coefficients).real)
    return energies


def localize_p6_hcurl_projection_signals(
    p5_field: fem.Function,
    p6_field: fem.Function,
) -> dict[str, Any]:
    """Build nested p4/p5/p6 shell and conforming projection sensors.

    The standard Basix basis is not assumed to be ordered hierarchically.
    Instead, the p6 field is interpolated into globally conforming p4 and p5
    spaces and lifted back to p6.  The two physical shell fields
    ``I6(I5(u6))-I6(I4(u6))`` and ``u6-I6(I5(u6))`` define the measured
    hierarchy.  Cell energies use the positive
    ``L2 + h_K^2 curl`` Gram form.
    """

    started = time.perf_counter()
    rss_before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    p5_space = p5_field.function_space
    p6_space = p6_field.function_space
    msh = p6_space.mesh
    comm = msh.comm
    local_contract_error = None
    try:
        p5_element = p5_space.element.basix_element
        p6_element = p6_space.element.basix_element
        elements = (p5_element, p6_element)
        if p5_space.mesh is not msh:
            local_contract_error = "p5/p6 fields do not share one mesh object"
        elif tuple(int(item.degree) for item in elements) != (5, 6):
            local_contract_error = "field degrees are not p5/p6"
        elif any(item.family != ElementFamily.N1E for item in elements):
            local_contract_error = "element family is not N1E"
        elif any(item.map_type != MapType.covariantPiola for item in elements):
            local_contract_error = "element map is not covariant Piola"
        elif any(
            item.sobolev_space != SobolevSpace.HCurl for item in elements
        ):
            local_contract_error = "element Sobolev space is not HCurl"
        elif any(bool(item.discontinuous) for item in elements):
            local_contract_error = "projection input is discontinuous"
        elif any(
            list(item.value_shape) != [msh.topology.dim]
            for item in elements
        ):
            local_contract_error = "element value shape is not the mesh dimension"
        elif any(item.cell_type != msh.basix_cell() for item in elements):
            local_contract_error = "element cell type differs from the mesh"
        elif p5_field.x.array.dtype != p6_field.x.array.dtype:
            local_contract_error = "p5/p6 scalar dtypes differ"
        elif not np.issubdtype(
            p6_field.x.array.dtype,
            np.complexfloating,
        ):
            local_contract_error = "projection signals require complex fields"
    except (AttributeError, TypeError, ValueError) as exc:
        local_contract_error = f"element contract inspection failed: {exc}"
    _collective_fail_if_any(
        comm,
        local_contract_error,
        context="p6 projection input contract failed",
    )

    p4_space = fem.functionspace(
        msh,
        element(
            "N1curl",
            msh.basix_cell(),
            4,
            dtype=default_real_type,
        ),
    )
    p4_projection = fem.Function(
        p4_space,
        name="E_p6_interpolated_to_p4",
    )
    p5_projection = fem.Function(
        p5_space,
        name="E_p6_interpolated_to_p5",
    )
    p4_projection.interpolate(p6_field)
    p5_projection.interpolate(p6_field)
    p4_projection.x.scatter_forward()
    p5_projection.x.scatter_forward()

    p4_lift = fem.Function(p6_space, name="E_p4_projection_lifted_to_p6")
    p5_lift = fem.Function(p6_space, name="E_p5_projection_lifted_to_p6")
    p4_lift.interpolate(p4_projection)
    p5_lift.interpolate(p5_projection)
    p4_lift.x.scatter_forward()
    p5_lift.x.scatter_forward()

    p5_input_lift = fem.Function(
        p6_space,
        name="E_p5_input_lifted_to_p6",
    )
    p5_roundtrip = fem.Function(
        p5_space,
        name="E_p5_input_roundtrip",
    )
    p5_input_lift.interpolate(p5_field)
    p5_input_lift.x.scatter_forward()
    p5_roundtrip.interpolate(p5_input_lift)
    p5_roundtrip.x.scatter_forward()
    local_roundtrip_error = float(
        np.linalg.norm(p5_field.x.array - p5_roundtrip.x.array)
    )
    local_p5_norm = float(np.linalg.norm(p5_field.x.array))
    roundtrip_error = math.sqrt(
        comm.allreduce(local_roundtrip_error**2, op=MPI.SUM)
    )
    p5_norm = math.sqrt(comm.allreduce(local_p5_norm**2, op=MPI.SUM))
    p5_roundtrip_relative_error = roundtrip_error / max(
        p5_norm,
        np.finfo(float).tiny,
    )

    shell_p5 = fem.Function(p6_space, name="E_hierarchical_shell_p5")
    shell_p6 = fem.Function(p6_space, name="E_hierarchical_shell_p6")
    defect_p4 = fem.Function(p6_space, name="E_projection_defect_p4")
    shell_p5.x.array[:] = p5_lift.x.array - p4_lift.x.array
    shell_p6.x.array[:] = p6_field.x.array - p5_lift.x.array
    defect_p4.x.array[:] = p6_field.x.array - p4_lift.x.array
    for field in (shell_p5, shell_p6, defect_p4):
        field.x.scatter_forward()

    global_ids, high_energy, high_closure = _owned_cell_contributions(
        p6_field
    )
    shell5_ids, shell5_energy, shell5_closure = (
        _owned_cell_contributions(shell_p5)
    )
    shell6_ids, shell6_energy, shell6_closure = (
        _owned_cell_contributions(shell_p6)
    )
    defect4_ids, defect4_energy, defect4_closure = (
        _owned_cell_contributions(defect_p4)
    )
    if not (
        np.array_equal(global_ids, shell5_ids)
        and np.array_equal(global_ids, shell6_ids)
        and np.array_equal(global_ids, defect4_ids)
    ):
        raise RuntimeError("projection sensor cell identities are not aligned")

    canonical_ids, _records, ordered_keys = canonical_owned_cell_ids(msh)
    mesh_geometry_sha256 = geometry_key_sha256(ordered_keys)
    shell5_dimension = int(p5_element.dim) - int(
        p4_space.element.basix_element.dim
    )
    shell6_dimension = int(p6_element.dim) - int(p5_element.dim)
    if shell5_dimension <= 0 or shell6_dimension <= 0:
        raise RuntimeError("p4/p5/p6 element dimensions are not nested")
    shell5_rms = np.sqrt(shell5_energy / shell5_dimension)
    shell6_rms = np.sqrt(shell6_energy / shell6_dimension)
    local_high_scale = float(np.max(np.sqrt(high_energy), initial=0.0))
    global_high_scale = float(comm.allreduce(local_high_scale, op=MPI.MAX))
    shell_floor = max(
        1.0e-12 * global_high_scale,
        np.finfo(np.float64).tiny,
    )
    shell_ratio_resolved = (shell5_rms > shell_floor) | (
        shell6_rms > shell_floor
    )
    hierarchical_decay_ratio = np.where(
        shell_ratio_resolved,
        shell6_rms / np.maximum(shell5_rms, shell_floor),
        0.0,
    )
    p4_relative_defect = np.sqrt(
        defect4_energy / np.maximum(high_energy, np.finfo(float).tiny)
    )
    p5_relative_defect = np.sqrt(
        shell6_energy / np.maximum(high_energy, np.finfo(float).tiny)
    )

    high_coefficient_energy = _cell_coefficient_energies(p6_field)
    shell5_coefficient_energy = _cell_coefficient_energies(shell_p5)
    shell6_coefficient_energy = _cell_coefficient_energies(shell_p6)
    shell5_coefficient_rms = np.sqrt(
        shell5_coefficient_energy / shell5_dimension
    )
    shell6_coefficient_rms = np.sqrt(
        shell6_coefficient_energy / shell6_dimension
    )
    coefficient_floor = max(
        1.0e-12
        * float(
            comm.allreduce(
                float(
                    np.max(
                        np.sqrt(high_coefficient_energy),
                        initial=0.0,
                    )
                ),
                op=MPI.MAX,
            )
        ),
        np.finfo(np.float64).tiny,
    )
    coefficient_ratio_resolved = (
        shell5_coefficient_rms > coefficient_floor
    ) | (shell6_coefficient_rms > coefficient_floor)
    coefficient_decay_ratio = np.where(
        coefficient_ratio_resolved,
        shell6_coefficient_rms
        / np.maximum(shell5_coefficient_rms, coefficient_floor),
        0.0,
    )

    reconstructed = (
        p4_lift.x.array + shell_p5.x.array + shell_p6.x.array
    )
    local_reconstruction_error = float(
        np.linalg.norm(p6_field.x.array - reconstructed)
    )
    local_field_norm = float(np.linalg.norm(p6_field.x.array))
    reconstruction_error = math.sqrt(
        comm.allreduce(local_reconstruction_error**2, op=MPI.SUM)
    )
    field_norm = math.sqrt(
        comm.allreduce(local_field_norm**2, op=MPI.SUM)
    )
    reconstruction_relative_error = reconstruction_error / max(
        field_norm,
        np.finfo(float).tiny,
    )

    def snapshot(name: str, values: np.ndarray) -> dict[str, Any]:
        return build_cell_indicator_snapshot(
            comm,
            canonical_ids,
            np.asarray(values, dtype=np.float64),
            indicator_name=name,
            mesh_geometry_sha256=mesh_geometry_sha256,
        )

    snapshots = {
        "shell_p5_energy": snapshot(
            "hierarchical_shell_p5_L2_plus_h2curl_energy",
            shell5_energy,
        ),
        "shell_p6_energy": snapshot(
            "hierarchical_shell_p6_L2_plus_h2curl_energy",
            shell6_energy,
        ),
        "hierarchical_decay_ratio": snapshot(
            "hierarchical_shell_p6_over_p5_rms_decay",
            hierarchical_decay_ratio,
        ),
        "hierarchical_decay_resolved": snapshot(
            "hierarchical_shell_decay_resolved_mask",
            shell_ratio_resolved.astype(np.float64),
        ),
        "coefficient_decay_ratio": snapshot(
            "hierarchical_coefficient_shell_p6_over_p5_rms_decay",
            coefficient_decay_ratio,
        ),
        "coefficient_decay_resolved": snapshot(
            "hierarchical_coefficient_decay_resolved_mask",
            coefficient_ratio_resolved.astype(np.float64),
        ),
        "p4_relative_projection_defect": snapshot(
            "global_conforming_p4_relative_projection_defect",
            p4_relative_defect,
        ),
        "p5_relative_projection_defect": snapshot(
            "global_conforming_p5_relative_projection_defect",
            p5_relative_defect,
        ),
    }
    snapshot_hashes = {
        name: value["canonical_ids_and_values_sha256"]
        for name, value in snapshots.items()
    }
    snapshot_validation = {
        name: validate_cell_indicator_snapshot(
            value,
            expected_mesh_geometry_sha256=mesh_geometry_sha256,
            expected_cell_count=len(ordered_keys),
        )
        for name, value in snapshots.items()
    }
    energy_closures = {
        "p6_field": high_closure,
        "shell_p5": shell5_closure,
        "shell_p6": shell6_closure,
        "p4_projection_defect": defect4_closure,
    }
    element_contract = {
        "family": "N1E",
        "map_type": "covariantPiola",
        "sobolev_space": "HCurl",
        "value_shape": [int(msh.topology.dim)],
        "cell_type": str(p6_element.cell_type.name),
        "scalar_dtype": str(p6_field.x.array.dtype),
        "continuous": True,
    }
    checks = {
        "element_contract": True,
        "p5_roundtrip_interpolation_le_1e-12": (
            p5_roundtrip_relative_error <= 1.0e-12
        ),
        "reconstruction_le_1e-12": (
            reconstruction_relative_error <= 1.0e-12
        ),
        "all_energy_closures_le_1e-10": all(
            math.isfinite(float(closure["relative_closure_error"]))
            and float(closure["relative_closure_error"]) <= 1.0e-10
            and math.isfinite(float(closure["direct_global_energy"]))
            and float(closure["direct_global_energy"]) >= 0.0
            and math.isfinite(
                float(closure["minimum_raw_cell_contribution"])
            )
            and float(closure["maximum_imaginary_cell_contribution"])
            <= 1.0e-12
            for closure in energy_closures.values()
        ),
        "all_snapshots_content_valid": all(
            all(validation.values())
            for validation in snapshot_validation.values()
        ),
        "all_cells_physically_resolved": all(
            value == 1.0
            for value in snapshots["hierarchical_decay_resolved"][
                "indicator_values"
            ]
        ),
        "projection_defect_decreases_p4_to_p5": all(
            p5 <= p4
            for p4, p5 in zip(
                snapshots["p4_relative_projection_defect"][
                    "indicator_values"
                ],
                snapshots["p5_relative_projection_defect"][
                    "indicator_values"
                ],
                strict=True,
            )
        ),
    }
    passed = all(checks.values())
    elapsed = float(
        comm.allreduce(time.perf_counter() - started, op=MPI.MAX)
    )
    rss_after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return {
        "schema_version": "task035b.p6-hcurl-local-hp-signals.v1",
        "status": (
            "p6_hcurl_projection_signals_pass"
            if passed
            else "p6_hcurl_projection_signals_failed"
        ),
        "pass": passed,
        "ordinary_default_changed": False,
        "mesh_geometry_sha256": mesh_geometry_sha256,
        "cell_count": int(len(ordered_keys)),
        "degrees": {"lower": 4, "intermediate": 5, "high": 6},
        "element_dimensions": {
            "p4": int(p4_space.element.basix_element.dim),
            "p5": int(p5_element.dim),
            "p6": int(p6_element.dim),
            "shell_p5": shell5_dimension,
            "shell_p6": shell6_dimension,
        },
        "positive_gram": "L2_plus_cell_diameter_squared_curl_energy",
        "element_contract": element_contract,
        "hierarchy_definition": (
            "global conforming nested interpolation shells; no Basix "
            "basis-index hierarchy is assumed"
        ),
        "projection_definition": (
            "p6 field interpolated to a global conforming p4/p5 space and "
            "lifted back to p6, preserving shared trace moments"
        ),
        "shell_significance_floor": shell_floor,
        "coefficient_significance_floor": coefficient_floor,
        "reconstruction_relative_coefficient_error": (
            reconstruction_relative_error
        ),
        "p5_roundtrip_relative_coefficient_error": (
            p5_roundtrip_relative_error
        ),
        "energy_closures": energy_closures,
        "snapshots": snapshots,
        "snapshot_hashes": snapshot_hashes,
        "snapshot_validation": snapshot_validation,
        "qualification_checks": checks,
        "diagnostic_wall_seconds": elapsed,
        "process_peak_rss_kib_before": int(rss_before),
        "process_peak_rss_kib_after": int(rss_after),
        "limitations": [
            "global p6 is the discrete reference, not continuum truth",
            "interpolation shells are nested but not G-orthogonalized",
            "projection defect is a primal smoothness signal, not goal error",
            (
                "raw coefficient-shell decay is diagnostic only because "
                "cell coefficient Euclidean norms are not orientation-"
                "canonical physical Gram energies"
            ),
        ],
    }


def localize_global_two_level_correction(
    coarse_field: fem.Function,
    enriched_field: fem.Function,
    *,
    theta: float = 0.5,
    interpolation_padding: float = 1.0e-10,
    include_p6_projection_signals: bool = False,
) -> dict[str, Any]:
    """Interpolate a solved coarse H(curl) field and localize its correction."""

    fine_space = enriched_field.function_space
    coarse_space = coarse_field.function_space
    comm = fine_space.mesh.comm
    relation = MPI.Comm.Compare(comm, coarse_space.mesh.comm)
    if relation not in (MPI.IDENT, MPI.CONGRUENT):
        raise ValueError("coarse and enriched fields must use congruent communicators.")

    started = time.perf_counter()
    rss_before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    tdim = fine_space.mesh.topology.dim
    fine_cell_map = fine_space.mesh.topology.index_map(tdim)
    interpolation_cells = np.arange(
        fine_cell_map.size_local + fine_cell_map.num_ghosts,
        dtype=np.int32,
    )
    interpolation_data = fem.create_interpolation_data(
        fine_space,
        coarse_space,
        interpolation_cells,
        padding=float(interpolation_padding),
    )
    coarse_on_enriched = fem.Function(fine_space, name="E_coarse_on_enriched")
    coarse_on_enriched.interpolate_nonmatching(
        coarse_field,
        interpolation_cells,
        interpolation_data,
    )
    coarse_on_enriched.x.scatter_forward()

    correction = fem.Function(fine_space, name="E_two_level_correction")
    correction.x.array[:] = enriched_field.x.array - coarse_on_enriched.x.array
    correction.x.scatter_forward()
    ids, contributions, closure = _owned_cell_contributions(correction)
    marked, marked_summary = _global_dorfler_mark(
        comm,
        ids,
        contributions,
        theta=float(theta),
    )
    canonical_ids, _geometry_records, ordered_geometry_keys = (
        canonical_owned_cell_ids(fine_space.mesh)
    )
    mesh_geometry_sha256 = geometry_key_sha256(ordered_geometry_keys)
    marked_canonical, canonical_marking = _global_dorfler_mark(
        comm,
        canonical_ids,
        contributions,
        theta=float(theta),
    )
    cell_indicator_snapshot = build_cell_indicator_snapshot(
        comm,
        canonical_ids,
        contributions,
        indicator_name="R5_actual_global_two_level_correction_energy",
        mesh_geometry_sha256=mesh_geometry_sha256,
    )
    ownership_counts = [int(value) for value in comm.allgather(len(ids))]
    elapsed = float(comm.allreduce(time.perf_counter() - started, op=MPI.MAX))
    rss_after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    result = {
        "schema_version": "task035.actual-global-two-level-r5.v2",
        "estimator": "R5_actual_global_two_level_correction_energy",
        "formal_hierarchical_fe_r5": True,
        "coarse_global_dofs": int(
            coarse_space.dofmap.index_map.size_global
            * coarse_space.dofmap.index_map_bs
        ),
        "enriched_global_dofs": int(
            fine_space.dofmap.index_map.size_global
            * fine_space.dofmap.index_map_bs
        ),
        "owned_cell_contribution_count": int(sum(ownership_counts)),
        "owned_cell_counts_by_rank": ownership_counts,
        "distributed_ownership_unique": True,
        "finite_cell_contributions": bool(np.all(np.isfinite(contributions))),
        "nonnegative_cell_contributions": bool(np.all(contributions >= 0.0)),
        "correction_energy": closure,
        "correction_energy_norm": math.sqrt(
            max(closure["direct_global_energy"], 0.0)
        ),
        "marking": marked_summary,
        "marked_global_cell_ids": marked.tolist(),
        "canonical_marking": canonical_marking,
        "marked_canonical_cell_ids": marked_canonical.tolist(),
        "mesh_geometry_sha256": mesh_geometry_sha256,
        "cell_indicator_snapshot": cell_indicator_snapshot,
        "estimator_wall_seconds": elapsed,
        "process_peak_rss_kib_before": int(rss_before),
        "process_peak_rss_kib_after": int(rss_after),
        "interpolation": {
            "method": "dolfinx_nonmatching_hcurl_interpolation",
            "padding": float(interpolation_padding),
            "same_communicator": True,
        },
    }
    if include_p6_projection_signals:
        result["p6_local_hp_signals"] = (
            localize_p6_hcurl_projection_signals(
                coarse_field,
                enriched_field,
            )
        )
    return result


def _require_official_summary(summary: dict[str, Any], label: str) -> None:
    residual = summary.get("linear_system_relative_residual")
    failures = []
    if summary.get("official_result") is not True:
        failures.append("official_result")
    if summary.get("case_status") != "completed":
        failures.append("case_status")
    if not isinstance(residual, (int, float)) or float(residual) > 1.0e-9:
        failures.append("true_residual_le_1e-9")
    for name in ("R00_total", "R_total", "T_total", "A_volume_total"):
        if not isinstance(summary.get(name), (int, float)):
            failures.append(name)
    if failures:
        raise RuntimeError(f"{label} solve failed actual-R5 prerequisites: {failures}")


def run_target_global_two_level_r5(
    out_dir: Path,
    *,
    coarse_degree: int = 2,
    enriched_degree: int = 3,
    h_nm: float = 10.0,
    theta: float = 0.5,
    incident_theta_deg: float = 80.0,
    polarization_kind: str = "s",
    mesh_cell_type: str = "hexahedron",
    progress_observer=None,
    mesh_data_override=None,
    reuse_single_mesh: bool = False,
    static_condensation_degrees: tuple[int, ...] = (),
    assembly_time_condensation_degrees: tuple[int, ...] = (),
    floquet_slave_elimination_degrees: tuple[int, ...] = (),
    include_p6_projection_signals: bool = False,
) -> dict[str, Any]:
    """Solve the fixed Task034 target twice and compute an actual global R5."""

    from src.common.config_3d import target_stage4_config
    from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
    from src.solvers.solve_maxwell_3d_stage_4b_block_grating import (
        run_stage4b_block_grating_3d_case,
    )
    from src.adaptivity.high_order_resource_audit import (
        build_high_order_resource_audit,
    )

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    requested_condensation = {
        int(value) for value in static_condensation_degrees
    }
    requested_slave_elimination = {
        int(value) for value in floquet_slave_elimination_degrees
    }
    requested_assembly_time = {
        int(value) for value in assembly_time_condensation_degrees
    }
    if not requested_condensation.issubset(
        {int(coarse_degree), int(enriched_degree)}
    ):
        raise ValueError(
            "static condensation degrees must belong to the global-p pair"
        )
    if not requested_slave_elimination.issubset(requested_condensation):
        raise ValueError(
            "Floquet slave elimination degrees must also request static "
            "condensation"
        )
    if not requested_assembly_time.issubset(requested_condensation):
        raise ValueError(
            "assembly-time condensation degrees must also request static "
            "condensation"
        )
    if not requested_assembly_time.issubset(requested_slave_elimination):
        raise ValueError(
            "assembly-time condensation directly builds the Floquet-"
            "independent trace system and requires slave elimination"
        )
    captures: dict[str, dict[str, Any]] = {}

    def observer(label: str):
        def capture(**state):
            captures[label] = {
                "field": state["field"],
                "mesh_data": state["mesh_data"],
            }

        return capture

    def config(degree: int):
        base = target_stage4_config(degree=degree, h_nm=h_nm)
        use_assembly_time = int(degree) in requested_assembly_time
        return replace(
            base,
            case_name=f"task035_actual_r5_p{degree}_h{h_nm:g}".replace(".", "p"),
            incident_theta_deg=float(incident_theta_deg),
            polarization_kind=polarization_kind,
            custom_polarization=None,
            mesh_cell_type=mesh_cell_type,
            matrix_diagnostics_assemble_only=False,
            matrix_diagnostics_factorization_only=False,
            full3d_reference_export=False,
            direct_release_base_after_augmentation=True,
            stage4_cell_static_condensation=(
                int(degree) in requested_condensation
            ),
            stage4_assembly_time_cell_static_condensation=(
                use_assembly_time
            ),
            direct_release_solver_before_postprocess=use_assembly_time,
            stage4_floquet_slave_elimination=(
                int(degree) in requested_slave_elimination
            ),
            petsc_extra_options={
                **base.petsc_extra_options,
                **(
                    {"mat_mumps_icntl_14": 100}
                    if use_assembly_time
                    else {}
                ),
            },
            unique_output=False,
        )

    def progress(stage: str, status: str) -> None:
        if progress_observer is not None:
            progress_observer(stage, status)

    started = time.perf_counter()
    shared_mesh_data = mesh_data_override
    if reuse_single_mesh and shared_mesh_data is None:
        progress("actual_r5_shared_mesh_build", "begin")
        shared_mesh_data = build_airbox_mesh_3d(
            config(int(coarse_degree)),
            out_dir / "shared_mesh",
        )
        progress("actual_r5_shared_mesh_build", "end")
    progress("actual_r5_coarse_solve", "begin")
    coarse_summary = run_stage4b_block_grating_3d_case(
        config(int(coarse_degree)),
        out_dir / f"coarse_p{coarse_degree}",
        solution_observer=observer("coarse"),
        mesh_data_override=shared_mesh_data,
    )
    _require_official_summary(coarse_summary, "coarse")
    progress("actual_r5_coarse_solve", "end")
    gc.collect()
    progress("actual_r5_enriched_solve", "begin")
    enriched_summary = run_stage4b_block_grating_3d_case(
        config(int(enriched_degree)),
        out_dir / f"enriched_p{enriched_degree}",
        solution_observer=observer("enriched"),
        mesh_data_override=shared_mesh_data,
    )
    _require_official_summary(enriched_summary, "enriched")
    progress("actual_r5_enriched_solve", "end")
    progress("actual_r5_localization", "begin")
    estimate = localize_global_two_level_correction(
        captures["coarse"]["field"],
        captures["enriched"]["field"],
        theta=float(theta),
    )
    progress("actual_r5_localization", "end")
    if include_p6_projection_signals:
        progress("actual_r5_p6_projection_signals", "begin")
        estimate["p6_local_hp_signals"] = (
            localize_p6_hcurl_projection_signals(
                captures["coarse"]["field"],
                captures["enriched"]["field"],
            )
        )
        progress("actual_r5_p6_projection_signals", "end")
    observable_names = ("R_total", "T_total", "A_volume_total")
    observable_delta = math.sqrt(
        sum(
            (float(enriched_summary[name]) - float(coarse_summary[name])) ** 2
            for name in observable_names
        )
    )
    estimate["effectivity_proxy"] = float(
        estimate["correction_energy_norm"] / max(observable_delta, TINY)
    )
    estimate["effectivity_proxy_semantics"] = (
        "global correction energy norm divided by coarse-to-enriched official "
        "R/T/A-volume change"
    )
    coarse_audit = build_high_order_resource_audit(
        captures["coarse"]["field"],
        captures["coarse"]["mesh_data"],
        coarse_summary,
    )
    enriched_audit = build_high_order_resource_audit(
        captures["enriched"]["field"],
        captures["enriched"]["mesh_data"],
        enriched_summary,
    )
    common_mesh_identity = coarse_audit["mesh_identity"]
    same_mesh_hashes = (
        common_mesh_identity == enriched_audit["mesh_identity"]
    )
    if not same_mesh_hashes:
        raise RuntimeError(
            "Coarse and enriched high-order solves do not share one exact "
            "geometry/tag identity."
        )
    single_in_memory_mesh_instance = (
        captures["coarse"]["mesh_data"].mesh
        is captures["enriched"]["mesh_data"].mesh
    )
    if reuse_single_mesh and not single_in_memory_mesh_instance:
        raise RuntimeError("Requested single-mesh pair rebuilt the mesh.")
    return {
        "schema_version": "task035.target-actual-global-r5.v1",
        "task035b_extension_schema_version": (
            "task035b.high-order-resource-extension.v1"
        ),
        "status": "actual_global_r5_pass",
        "target_identity": {
            "wavelength_nm": 13.5,
            "incidence_theta_deg": float(incident_theta_deg),
            "grazing_angle_deg": float(90.0 - incident_theta_deg),
            "polarization": polarization_kind.upper(),
            "geometry": "Task034 fixed rectangular block grating",
            "mesh_backend": f"boundary-fitted conforming {mesh_cell_type}",
        },
        "coarse": {
            "degree": int(coarse_degree),
            "h_nm": float(h_nm),
            "summary": coarse_summary,
            "high_order_resource_audit": coarse_audit,
        },
        "enriched": {
            "degree": int(enriched_degree),
            "h_nm": float(h_nm),
            "summary": enriched_summary,
            "high_order_resource_audit": enriched_audit,
        },
        "common_mesh_identity": common_mesh_identity,
        "same_mesh_hashes": same_mesh_hashes,
        "single_in_memory_mesh_instance": single_in_memory_mesh_instance,
        "reuse_single_mesh_requested": bool(reuse_single_mesh),
        "static_condensation_degrees": [
            int(value) for value in static_condensation_degrees
        ],
        "assembly_time_condensation_degrees": [
            int(value) for value in assembly_time_condensation_degrees
        ],
        "floquet_slave_elimination_degrees": [
            int(value) for value in floquet_slave_elimination_degrees
        ],
        "p6_projection_signals_requested": bool(
            include_p6_projection_signals
        ),
        "official_observable_delta_l2": float(observable_delta),
        "R5": estimate,
        "elapsed_seconds": float(
            MPI.COMM_WORLD.allreduce(time.perf_counter() - started, op=MPI.MAX)
        ),
        "ordinary_default_changed": False,
    }
