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
from mpi4py import MPI
from petsc4py import PETSc

from dolfinx import fem
from dolfinx.fem import petsc as fem_petsc


TINY = np.finfo(float).tiny


def _global_dorfler_mark(
    comm: MPI.Intracomm,
    global_cell_ids: np.ndarray,
    contributions: np.ndarray,
    *,
    theta: float,
) -> tuple[np.ndarray, dict[str, Any]]:
    if not 0.0 < float(theta) <= 1.0:
        raise ValueError("Dorfler theta must lie in (0, 1].")
    ids = np.asarray(global_cell_ids, dtype=np.int64)
    values = np.asarray(contributions, dtype=np.float64)
    if ids.shape != values.shape:
        raise ValueError("global cell ids and contributions must have equal shapes.")
    packets = comm.allgather((ids, values))
    all_ids = np.concatenate([packet[0] for packet in packets])
    all_values = np.concatenate([packet[1] for packet in packets])
    if len(np.unique(all_ids)) != len(all_ids):
        raise RuntimeError("owned-cell identifiers are not globally unique.")
    order = np.lexsort((all_ids, -all_values))
    total = float(np.sum(all_values))
    if total <= TINY:
        marked = np.asarray([], dtype=np.int64)
    else:
        cutoff = float(theta) * total
        count = int(
            np.searchsorted(np.cumsum(all_values[order]), cutoff, side="left")
            + 1
        )
        marked = np.sort(all_ids[order[:count]])
    digest = hashlib.sha256(marked.astype("<i8", copy=False).tobytes()).hexdigest()
    return marked, {
        "theta": float(theta),
        "count": int(len(marked)),
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
    for index, cell in enumerate(owned_cells):
        dofs = scalar_space.dofmap.cell_dofs(int(cell))
        if len(dofs) != 1 or int(dofs[0]) >= owned_dof_count:
            vector.destroy()
            raise RuntimeError("DG0 owned-cell/dof ownership is not one-to-one.")
        value = complex(values[int(dofs[0])])
        max_imaginary = max(max_imaginary, abs(value.imag))
        contributions[index] = value.real
    vector.destroy()

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


def localize_global_two_level_correction(
    coarse_field: fem.Function,
    enriched_field: fem.Function,
    *,
    theta: float = 0.5,
    interpolation_padding: float = 1.0e-10,
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
    ownership_counts = [int(value) for value in comm.allgather(len(ids))]
    elapsed = float(comm.allreduce(time.perf_counter() - started, op=MPI.MAX))
    rss_after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return {
        "schema_version": "task035.actual-global-two-level-r5.v1",
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
        "estimator_wall_seconds": elapsed,
        "process_peak_rss_kib_before": int(rss_before),
        "process_peak_rss_kib_after": int(rss_after),
        "interpolation": {
            "method": "dolfinx_nonmatching_hcurl_interpolation",
            "padding": float(interpolation_padding),
            "same_communicator": True,
        },
    }


def _require_official_summary(summary: dict[str, Any], label: str) -> None:
    residual = summary.get("linear_system_relative_residual")
    failures = []
    if summary.get("official_result") is not True:
        failures.append("official_result")
    if summary.get("case_status") != "completed":
        failures.append("case_status")
    if not isinstance(residual, (int, float)) or float(residual) > 1.0e-9:
        failures.append("true_residual_le_1e-9")
    for name in ("R_total", "T_total", "A_volume_total"):
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
    polarization_kind: str = "s",
    mesh_cell_type: str = "hexahedron",
    progress_observer=None,
) -> dict[str, Any]:
    """Solve the fixed Task034 target twice and compute an actual global R5."""

    from src.common.config_3d import target_stage4_config
    from src.solvers.solve_maxwell_3d_stage_4b_block_grating import (
        run_stage4b_block_grating_3d_case,
    )

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
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
        return replace(
            base,
            case_name=f"task035_actual_r5_p{degree}_h{h_nm:g}".replace(".", "p"),
            polarization_kind=polarization_kind,
            custom_polarization=None,
            mesh_cell_type=mesh_cell_type,
            matrix_diagnostics_assemble_only=False,
            matrix_diagnostics_factorization_only=False,
            full3d_reference_export=False,
            direct_release_base_after_augmentation=True,
            unique_output=False,
        )

    def progress(stage: str, status: str) -> None:
        if progress_observer is not None:
            progress_observer(stage, status)

    started = time.perf_counter()
    progress("actual_r5_coarse_solve", "begin")
    coarse_summary = run_stage4b_block_grating_3d_case(
        config(int(coarse_degree)),
        out_dir / f"coarse_p{coarse_degree}",
        solution_observer=observer("coarse"),
    )
    _require_official_summary(coarse_summary, "coarse")
    progress("actual_r5_coarse_solve", "end")
    gc.collect()
    progress("actual_r5_enriched_solve", "begin")
    enriched_summary = run_stage4b_block_grating_3d_case(
        config(int(enriched_degree)),
        out_dir / f"enriched_p{enriched_degree}",
        solution_observer=observer("enriched"),
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
    return {
        "schema_version": "task035.target-actual-global-r5.v1",
        "status": "actual_global_r5_pass",
        "target_identity": {
            "wavelength_nm": 13.5,
            "incidence_theta_deg": 80.0,
            "grazing_angle_deg": 10.0,
            "polarization": polarization_kind.upper(),
            "geometry": "Task034 fixed rectangular block grating",
            "mesh_backend": f"boundary-fitted conforming {mesh_cell_type}",
        },
        "coarse": {
            "degree": int(coarse_degree),
            "h_nm": float(h_nm),
            "summary": coarse_summary,
        },
        "enriched": {
            "degree": int(enriched_degree),
            "h_nm": float(h_nm),
            "summary": enriched_summary,
        },
        "official_observable_delta_l2": float(observable_delta),
        "R5": estimate,
        "elapsed_seconds": float(
            MPI.COMM_WORLD.allreduce(time.perf_counter() - started, op=MPI.MAX)
        ),
        "ordinary_default_changed": False,
    }
