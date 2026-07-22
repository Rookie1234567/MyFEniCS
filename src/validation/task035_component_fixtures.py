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


def _global_scalar(msh: mesh.Mesh, expression) -> complex:
    local = fem.assemble_scalar(fem.form(expression))
    return complex(msh.comm.allreduce(local, op=MPI.SUM))


def _space(msh: mesh.Mesh, degree: int):
    return fem.functionspace(
        msh, element("N1curl", msh.basix_cell(), degree, dtype=default_real_type)
    )


def _analytic_field(x: np.ndarray) -> np.ndarray:
    values = np.empty((3, x.shape[1]), dtype=np.complex128)
    values[0] = np.sin(math.pi * x[2]) * np.exp(0.2j * x[0])
    values[1] = np.sin(math.pi * x[0]) * np.exp(-0.15j * x[2])
    values[2] = 0.25 * np.cos(math.pi * x[1])
    return values


def _cell_tag_values(msh: mesh.Mesh) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    cell_map = msh.topology.index_map(msh.topology.dim)
    count = cell_map.size_local + cell_map.num_ghosts
    cells = np.arange(count, dtype=np.int32)
    centers = mesh.compute_midpoints(msh, msh.topology.dim, cells)
    # L-shaped inclusion: two material faces meet at the x=z=0.5 corner line.
    values = np.where((centers[:, 0] <= 0.5) & (centers[:, 2] <= 0.5), 2, 1)
    return cells, centers, values.astype(np.int32)


def _piecewise_epsilon(msh: mesh.Mesh, cell_values: np.ndarray, *, fault: bool = False):
    space = fem.functionspace(msh, ("DG", 0))
    coefficient = fem.Function(space)
    materials = {1: 1.0 + 0.0j, 2: 2.2 + 0.35j}
    if fault:
        materials = {1: 1.0 + 0.0j, 2: 1.0 + 0.0j}
    for cell, tag in enumerate(cell_values):
        coefficient.x.array[space.dofmap.cell_dofs(cell)[0]] = materials[int(tag)]
    coefficient.x.scatter_forward()
    return coefficient


def _correlation(left: np.ndarray, right: np.ndarray) -> float:
    return float(np.corrcoef(left.astype(float), right.astype(float))[0, 1])


def run_b3_material_corner_fixture() -> dict[str, Any]:
    comm = MPI.COMM_WORLD
    msh = mesh.create_box(
        comm,
        [np.zeros(3), np.ones(3)],
        [4, 4, 4],
        cell_type=mesh.CellType.hexahedron,
    )
    cells, centers, tag_values = _cell_tag_values(msh)
    cell_map = msh.topology.index_map(msh.topology.dim)
    owned_count = cell_map.size_local
    owned_cells = cells[:owned_count]
    tags = mesh.meshtags(msh, msh.topology.dim, owned_cells, tag_values[:owned_count])
    msh.topology.create_connectivity(msh.topology.dim - 1, msh.topology.dim)
    facet_cells = msh.topology.connectivity(msh.topology.dim - 1, msh.topology.dim)
    facet_map = msh.topology.index_map(msh.topology.dim - 1)
    interface_facets = []
    for facet in range(facet_map.size_local):
        adjacent = facet_cells.links(facet)
        if len(adjacent) == 2 and tag_values[adjacent[0]] != tag_values[adjacent[1]]:
            interface_facets.append(facet)
    interface_facets_array = np.asarray(interface_facets, dtype=np.int32)
    interface_tags = mesh.meshtags(
        msh,
        msh.topology.dim - 1,
        interface_facets_array,
        np.ones(len(interface_facets_array), dtype=np.int32),
    )
    dS = ufl.Measure("dS", domain=msh, subdomain_data=interface_tags)

    fields = []
    point_errors = []
    point_values = []
    for degree in (1, 2):
        function = fem.Function(_space(msh, degree), name=f"B3_corner_p{degree}")
        function.interpolate(_analytic_field)
        function.x.scatter_forward()
        values = np.asarray(function.eval(centers[:owned_count], owned_cells)).reshape(
            (-1, 3)
        )
        exact = _analytic_field(centers[:owned_count].T).T
        error = np.linalg.norm(values - exact, axis=1)
        fields.append(function)
        point_values.append(values)
        point_errors.append(error)

    epsilon = _piecewise_epsilon(msh, tag_values)
    epsilon_fault = _piecewise_epsilon(msh, tag_values, fault=True)
    k0 = 2.1
    strong = ufl.curl(ufl.curl(fields[0])) - k0**2 * epsilon * fields[0]
    strong_fault = ufl.curl(ufl.curl(fields[0])) - k0**2 * epsilon_fault * fields[0]
    residual_norm = math.sqrt(
        max(0.0, _global_scalar(msh, ufl.inner(strong, strong) * ufl.dx).real)
    )
    fault_norm = math.sqrt(
        max(
            0.0,
            _global_scalar(msh, ufl.inner(strong_fault, strong_fault) * ufl.dx).real,
        )
    )
    normal = ufl.FacetNormal(msh)
    jump = ufl.cross(normal("+"), ufl.curl(fields[0])("+") - ufl.curl(fields[0])("-"))
    interface_jump = math.sqrt(
        max(0.0, _global_scalar(msh, ufl.inner(jump, jump) * dS(1)).real)
    )

    enriched = np.linalg.norm(point_values[0] - point_values[1], axis=1)
    local_proxy = (
        point_errors[0] + 0.25 * enriched + 0.05 * (tag_values[:owned_count] == 2)
    )
    local_rows = np.column_stack(
        (
            cell_map.local_range[0] + np.arange(owned_count),
            centers[:owned_count],
            local_proxy,
            point_errors[1],
        )
    )
    gathered = comm.gather(local_rows, root=0)
    metrics = None
    if comm.rank == 0:
        rows = np.vstack(gathered)
        order = np.argsort(rows[:, 0])
        rows = rows[order]
        indicator = rows[:, 4]
        truth = rows[:, 5]
        xyz = rows[:, 1:4]
        weighted_mean = np.average(xyz, axis=0, weights=indicator + 1.0e-30)
        directional = np.average(
            np.abs(xyz - weighted_mean), axis=0, weights=indicator + 1.0e-30
        )
        names = ("x", "y", "z")
        metrics = {
            "local_error_correlation": _correlation(indicator, truth),
            "directional_scores": {
                name: float(value) for name, value in zip(names, directional)
            },
            "selected_direction": names[int(np.argmax(directional))],
            "selection_rule": "argmax indicator-weighted coordinate absolute deviation",
            "compact_scalar_rows_gathered": int(len(rows)),
        }
    metrics = comm.bcast(metrics, root=0)
    global_tag_counts = {
        str(tag): int(
            comm.allreduce(
                np.count_nonzero(tag_values[:owned_count] == tag), op=MPI.SUM
            )
        )
        for tag in (1, 2)
    }
    global_interface_facets = int(comm.allreduce(len(interface_facets), op=MPI.SUM))
    fine_error = math.sqrt(
        float(comm.allreduce(np.sum(point_errors[1] ** 2), op=MPI.SUM))
    )
    coarse_error = math.sqrt(
        float(comm.allreduce(np.sum(point_errors[0] ** 2), op=MPI.SUM))
    )
    passed = (
        all(value > 0 for value in global_tag_counts.values())
        and global_interface_facets > 0
        and residual_norm > 0.0
        and interface_jump > 0.0
        and abs(fault_norm - residual_norm) > 1.0e-3
        and fine_error < coarse_error
        and math.isfinite(metrics["local_error_correlation"])
    )
    return {
        "name": "B3_real_material_interface_corner",
        "status": "component_fixture_pass" if passed else "component_fixture_fail",
        "real_fe": True,
        "pde_run": False,
        "mpi_size": comm.size,
        "mesh": "4x4x4 conforming hexahedra",
        "actual_cell_tags": global_tag_counts,
        "actual_cell_meshtags_dim": tags.dim,
        "actual_material_interface_facets": global_interface_facets,
        "r1_global_norm": residual_norm,
        "material_tag_fault_norm": fault_norm,
        "material_tag_fault_detected": abs(fault_norm - residual_norm) > 1.0e-3,
        "interface_curl_jump_norm": interface_jump,
        "p1_center_error_l2": coarse_error,
        "p2_center_error_l2": fine_error,
        "enriched_proxy_improves": fine_error < coarse_error,
        **metrics,
    }


def run_b4_hybrid_trace_fixture() -> dict[str, Any]:
    comm = MPI.COMM_WORLD
    sample = (
        ROOT
        / "benchmarks/artifacts/task034/phase_f/full3d"
        / "p2_h3_full-solve_mpi8_20260719T022046Z/full3d_reference_samples.npz"
    )
    funnel_path = (
        ROOT
        / "benchmarks/artifacts/task034/phase_f/records/p2_h3_hybrid_funnel_mpi8_2141788.json"
    )
    matched_path = (
        ROOT
        / "benchmarks/artifacts/task034/phase_c/matched_trace_32464ab/task034_matched_trace_aggregate.json"
    )
    with np.load(sample) as archive:
        electric = np.asarray(archive["E_t_interface_V_per_m"])
        magnetic = 376.730313668 * np.asarray(archive["H_t_interface_A_per_m"])
    funnel = json.loads(funnel_path.read_text(encoding="utf-8"))
    matched = json.loads(matched_path.read_text(encoding="utf-8"))
    et_norm = float(np.linalg.norm(electric))
    ht_norm = float(np.linalg.norm(magnetic))
    trace_residual = float(
        np.linalg.norm(electric - magnetic) / max(et_norm + ht_norm, 1.0e-30)
    )
    dtn_fault = float(
        np.linalg.norm(electric - 1.2 * magnetic) / max(et_norm + ht_norm, 1.0e-30)
    )
    comparisons = [
        {
            "previous_M": row["previous_mode_count"],
            "current_M": row["current_mode_count"],
            "max_absolute_total_delta": row["max_absolute_total_delta"],
        }
        for row in funnel["comparisons"]
    ]
    spatial_perturbation = float(
        np.linalg.norm(electric[:, :, 1:] - electric[:, :, :-1]) / max(et_norm, 1.0e-30)
    )
    qep_diagnostic = {
        "status": matched["status"],
        "p3_beta_assignment_max_relative_delta": matched["mpi_identity_diagnostics"][
            "p3"
        ]["beta_assignment"]["maximum_relative_delta"],
        "p4_beta_assignment_max_relative_delta": matched["mpi_identity_diagnostics"][
            "p4"
        ]["beta_assignment"]["maximum_relative_delta"],
        "policy": "diagnostic_only_not_an_estimator_marking_term",
    }
    passed = (
        et_norm > 0.0
        and ht_norm > 0.0
        and abs(dtn_fault - trace_residual) > 1.0e-4
        and spatial_perturbation > 0.0
        and len(comparisons) >= 2
        and all(row["max_absolute_total_delta"] < 1.0e-5 for row in comparisons)
        and matched["status"] == "passed"
    )
    return {
        "name": "B4_measured_Hybrid_Et_Ht_M_DtN_microfixture",
        "status": "component_fixture_pass" if passed else "component_fixture_fail",
        "real_target_trace": True,
        "new_pde_run": False,
        "mpi_size": comm.size,
        "Et_norm": et_norm,
        "Ht_impedance_scaled_norm": ht_norm,
        "spatial_perturbation": spatial_perturbation,
        "DtN_trace_residual": trace_residual,
        "DtN_operator_fault_residual": dtn_fault,
        "M_perturbations": comparisons,
        "QEP_diagnostic": qep_diagnostic,
        "artifact_bindings": {
            str(sample.relative_to(ROOT)): _sha256(sample),
            str(funnel_path.relative_to(ROOT)): _sha256(funnel_path),
            str(matched_path.relative_to(ROOT)): _sha256(matched_path),
        },
    }


def run_component_fixture_suite() -> dict[str, Any]:
    b3 = run_b3_material_corner_fixture()
    b4 = run_b4_hybrid_trace_fixture()
    passed = (
        b3["status"] == "component_fixture_pass"
        and b4["status"] == "component_fixture_pass"
    )
    return {
        "schema_version": "task035.phase-c-component-fixtures.v1",
        "status": "B3_B4_pass" if passed else "B3_B4_controlled_negative",
        "production_qualified": False,
        "ordinary_default_changed": False,
        "mpi_size": MPI.COMM_WORLD.size,
        "b3": b3,
        "b4": b4,
    }
