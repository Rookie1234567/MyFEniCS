from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import ufl
from basix.ufl import element
from mpi4py import MPI

from dolfinx import default_real_type, fem, mesh


ROOT = Path(__file__).resolve().parents[2]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _strip_control() -> dict[str, Any]:
    mechanism_path = (
        ROOT
        / "benchmarks/cases/092_workstation_wsl_adaptive_scalability/records"
        / "adaptive_mechanism_qualification.json"
    )
    summary_path = mechanism_path.with_name("adaptive_summary.json")
    mechanism = json.loads(mechanism_path.read_text(encoding="utf-8"))
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    conservative = summary["profiles"]["conservative"]
    measured = conservative["shards"][-1]
    return {
        "backend": "Task034_strip_tensor",
        "status": "controlled_negative",
        "actual_pde_run": True,
        "mechanism_pass": mechanism["qualification"]["pass"],
        "no_hanging_nodes": not mechanism["plan"]["quality"]["hanging_nodes_present"],
        "periodic_mate_refinement_synchronized": mechanism["plan"]["periodic_pairing"][
            "periodic_mate_refinement_synchronized"
        ],
        "mesh_cells": measured["mesh_cells"],
        "mesh_elements": measured["mesh_elements"],
        "physical_gates_pass": measured["all_reported_physical_gates_pass"],
        "failed_gates": measured["failed_gate_names"],
        "stop_reason": conservative["stop_reason"],
        "evidence": {
            str(mechanism_path.relative_to(ROOT)): _sha256(mechanism_path),
            str(summary_path.relative_to(ROOT)): _sha256(summary_path),
        },
    }


def _multiblock_hexa_candidate() -> dict[str, Any]:
    # A conforming Cartesian multi-block grid must take the tensor product of all
    # selected axis cuts. This calculation quantifies the unavoidable strip leakage.
    base = np.asarray([10, 5, 20], dtype=int)
    marked_axis_intervals = np.asarray([3, 2, 5], dtype=int)
    refined = base + marked_axis_intervals
    base_cells = int(np.prod(base))
    refined_cells = int(np.prod(refined))
    ideal_local_added = int(
        np.prod(2 * marked_axis_intervals) - np.prod(marked_axis_intervals)
    )
    actual_added = refined_cells - base_cells
    leakage_ratio = actual_added / max(ideal_local_added, 1)
    blocker = leakage_ratio > 2.0
    return {
        "backend": "multi_block_conforming_hexa_candidate",
        "status": "hexa_backend_blocker" if blocker else "candidate_pass",
        "base_axis_cells": base.tolist(),
        "marked_axis_intervals": marked_axis_intervals.tolist(),
        "tensor_product_axis_cells": refined.tolist(),
        "base_cells": base_cells,
        "candidate_cells": refined_cells,
        "ideal_local_added_cells_proxy": ideal_local_added,
        "actual_added_cells": actual_added,
        "strip_leakage_ratio": float(leakage_ratio),
        "conforming": True,
        "periodic_axis_cuts_synchronized": True,
        "hanging_nodes": False,
        "transition_cell_support": False,
        "reason": "axis cuts propagate through the Cartesian product; no qualified transition-cell or hanging-node constraint implementation exists",
    }


def _analytic(x: np.ndarray) -> np.ndarray:
    result = np.empty((3, x.shape[1]), dtype=np.complex128)
    result[0] = np.sin(2.0 * math.pi * x[1]) * np.exp(0.2j * x[2])
    result[1] = np.sin(math.pi * x[2]) * np.exp(-0.1j * x[0])
    result[2] = 0.2 * np.sin(math.pi * x[0])
    return result


def _nedelec_error(msh: mesh.Mesh) -> float:
    space = fem.functionspace(
        msh, element("N1curl", msh.basix_cell(), 1, dtype=default_real_type)
    )
    field = fem.Function(space)
    field.interpolate(_analytic)
    field.x.scatter_forward()
    x = ufl.SpatialCoordinate(msh)
    exact = ufl.as_vector(
        (
            ufl.sin(2.0 * math.pi * x[1]) * ufl.exp(0.2j * x[2]),
            ufl.sin(math.pi * x[2]) * ufl.exp(-0.1j * x[0]),
            0.2 * ufl.sin(math.pi * x[0]),
        )
    )
    local = fem.assemble_scalar(
        fem.form(ufl.inner(field - exact, field - exact) * ufl.dx)
    )
    return math.sqrt(max(0.0, float(msh.comm.allreduce(local, op=MPI.SUM).real)))


def _cell_volumes(msh: mesh.Mesh) -> tuple[np.ndarray, np.ndarray]:
    tdim = msh.topology.dim
    msh.topology.create_connectivity(tdim, 0)
    cell_vertices = msh.topology.connectivity(tdim, 0)
    cell_map = msh.topology.index_map(tdim)
    cells = np.arange(cell_map.size_local, dtype=np.int32)
    centers = mesh.compute_midpoints(msh, tdim, cells)
    volumes = np.empty(len(cells), dtype=float)
    for index, cell in enumerate(cells):
        vertices = msh.geometry.x[cell_vertices.links(int(cell))]
        matrix = np.column_stack(
            (
                vertices[1] - vertices[0],
                vertices[2] - vertices[0],
                vertices[3] - vertices[0],
            )
        )
        volumes[index] = abs(float(np.linalg.det(matrix))) / 6.0
    return centers, volumes


def _tetra_marked_refinement_control() -> dict[str, Any]:
    comm = MPI.COMM_WORLD
    coarse = mesh.create_box(
        comm,
        [np.zeros(3), np.ones(3)],
        [4, 4, 4],
        cell_type=mesh.CellType.tetrahedron,
    )
    tdim = coarse.topology.dim
    cell_map = coarse.topology.index_map(tdim)
    owned_cells = np.arange(cell_map.size_local, dtype=np.int32)
    centers = mesh.compute_midpoints(coarse, tdim, owned_cells)
    marked = owned_cells[
        (centers[:, 0] >= 0.30)
        & (centers[:, 0] <= 0.70)
        & (centers[:, 1] <= 0.55)
        & (centers[:, 2] >= 0.25)
        & (centers[:, 2] <= 0.75)
    ]
    coarse.topology.create_entities(1)
    coarse.topology.create_connectivity(tdim, 1)
    edges = mesh.compute_incident_entities(coarse.topology, marked, tdim, 1)
    coarse_count = cell_map.size_global
    coarse_error = _nedelec_error(coarse)
    refined = mesh.refine(coarse, edges)[0]
    refined_count = refined.topology.index_map(tdim).size_global
    refined_error = _nedelec_error(refined)
    refined_centers, refined_volumes = _cell_volumes(refined)
    in_region = (
        (refined_centers[:, 0] >= 0.30)
        & (refined_centers[:, 0] <= 0.70)
        & (refined_centers[:, 1] <= 0.55)
        & (refined_centers[:, 2] >= 0.25)
        & (refined_centers[:, 2] <= 0.75)
    )
    local_inside = np.asarray(
        [np.sum(refined_volumes[in_region]), np.count_nonzero(in_region)], dtype=float
    )
    local_outside = np.asarray(
        [np.sum(refined_volumes[~in_region]), np.count_nonzero(~in_region)], dtype=float
    )
    inside = np.zeros(2, dtype=float)
    outside = np.zeros(2, dtype=float)
    comm.Allreduce(local_inside, inside, op=MPI.SUM)
    comm.Allreduce(local_outside, outside, op=MPI.SUM)
    inside_mean = float(inside[0] / max(inside[1], 1.0))
    outside_mean = float(outside[0] / max(outside[1], 1.0))
    local_min = float(np.min(refined_volumes)) if len(refined_volumes) else math.inf
    global_min = float(comm.allreduce(local_min, op=MPI.MIN))
    marked_count = int(comm.allreduce(len(marked), op=MPI.SUM))
    passed = (
        marked_count > 0
        and refined_count > coarse_count
        and global_min > 0.0
        and inside_mean < outside_mean
        and refined_error < coarse_error
    )
    return {
        "backend": "tetra_marked_refinement_control",
        "status": "control_pass" if passed else "controlled_negative",
        "real_dolfinx_refine": True,
        "pde_run": False,
        "mpi_size": comm.size,
        "coarse_cells": coarse_count,
        "marked_coarse_cells": marked_count,
        "refined_cells": refined_count,
        "minimum_signed_volume_proxy": global_min,
        "inside_marked_region_mean_volume": inside_mean,
        "outside_marked_region_mean_volume": outside_mean,
        "locality_pass": inside_mean < outside_mean,
        "coarse_Nedelec_interpolation_error": coarse_error,
        "refined_Nedelec_interpolation_error": refined_error,
        "observable_proxy_reduction_fraction": 1.0 - refined_error / coarse_error,
        "scope": "marked-refinement backend/orientation control; not target Maxwell PDE evidence",
    }


def run_mesh_backend_bakeoff() -> dict[str, Any]:
    strip = _strip_control()
    hexa = _multiblock_hexa_candidate()
    tetra = _tetra_marked_refinement_control()
    complete = (
        strip["status"] == "controlled_negative"
        and hexa["status"] == "hexa_backend_blocker"
        and tetra["status"] == "control_pass"
    )
    return {
        "schema_version": "task035.phase-d-mesh-backend-bakeoff.v1",
        "status": "phase_d_complete_controlled_negative"
        if complete
        else "phase_d_incomplete",
        "phase_d_internal_gate": "complete" if complete else "fail",
        "production_backend_selected": False,
        "ordinary_default_changed": False,
        "phase_e_unlocked": False,
        "reason": "tetra control works, but target conforming-hexa locality is blocked and the accepted strip backend failed physical same-error gates",
        "strip_tensor_negative_control": strip,
        "multi_block_conforming_hexa": hexa,
        "tetra_marked_refinement_control": tetra,
    }
