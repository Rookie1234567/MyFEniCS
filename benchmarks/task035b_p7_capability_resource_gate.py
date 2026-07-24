"""Build the Task035b h10/p7 capability and resource controlled-stop record.

This is a pure Basix/topology/artifact audit.  It never builds a DOLFINx mesh,
compiles a form, launches MPI, assembles a matrix, or starts a PDE solve.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from typing import Any, Iterable, Sequence

import basix
from basix.ufl import element
import dolfinx
from mpi4py import MPI
import mpi4py
import numpy as np
from petsc4py import PETSc
import petsc4py

from src.common.config_3d import target_stage4_config
from src.constraints.floquet_3d import _qualified_constraint_mode
from src.constraints.high_order_floquet_trace import high_order_trace_layout


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_BRANCH = (
    "codex/20260723-task35b-high-order-local-hp-resource-envelope"
)
DEFAULT_OUTPUT = Path(
    "benchmarks/cases/095_high_order_local_hp_resource_envelope/"
    "records/p7_h10_capability_resource_gate.json"
)
P7_DEGREE = 7
H10_AXIS_CELLS = (6, 3, 14)
DTN_AUXILIARY_ROWS = 80
FULL3D_EQUIVALENT_DOF_LIMIT = 90_000
CALIBRATION_SOURCES = (
    {
        "degree": 4,
        "record_path": (
            "benchmarks/cases/095_high_order_local_hp_resource_envelope/"
            "records/global_hexa_p4_p5_h10_assembly_time_condensed_"
            "independent_mpi8.json"
        ),
        "field": "coarse",
        "record_sha256": (
            "6e2bb2e6779f2d037fd17495f2beee2a8ef69d4dea076dbc98a71aea35d1abd4"
        ),
        "source_commit_sha": (
            "a5cf24758e31143d25ddb8ae8cb2e731abfffdae"
        ),
    },
    {
        "degree": 5,
        "record_path": (
            "benchmarks/cases/095_high_order_local_hp_resource_envelope/"
            "records/global_hexa_p4_p5_h10_assembly_time_condensed_"
            "independent_mpi8.json"
        ),
        "field": "enriched",
        "record_sha256": (
            "6e2bb2e6779f2d037fd17495f2beee2a8ef69d4dea076dbc98a71aea35d1abd4"
        ),
        "source_commit_sha": (
            "a5cf24758e31143d25ddb8ae8cb2e731abfffdae"
        ),
    },
    {
        "degree": 6,
        "record_path": (
            "benchmarks/cases/095_high_order_local_hp_resource_envelope/"
            "records/global_hexa_p5_p6_h10_assembly_time_condensed_"
            "independent_mpi8.json"
        ),
        "field": "enriched",
        "record_sha256": (
            "9f7f44efb52b44c587ef59a57524849e08da81a6fcd5d90ec18e7b69e4f33ded"
        ),
        "source_commit_sha": (
            "e9d35bb77636302e18112bf1ab81fdc40f64efba"
        ),
    },
)
_H10_MESH_IDENTITY = {
    "mesh_cell_type": "hexahedron",
    "global_cell_count": 252,
    "mesh_cells_resolved": [6, 3, 14],
    "partition_independent_mesh_sha256": (
        "f0eef2aa28e86014b661a921993bcfd45e6db1892da350402f2be11ec64dd857"
    ),
    "cell_tag_sha256": (
        "42f511fc7ffddcbc2972d641018e16a845f48c11067ccd9a9686695ad5cfc131"
    ),
    "facet_tag_sha256": (
        "0adbcfed35e1840460f826cb1ca1695ed87c0c3960e2073377d2f50871c3c0bd"
    ),
}
_H10_DEGREE_RESOURCE_IDENTITY = {
    4: {"rows": 21824, "nnz": 8184464},
    5: {"rows": 35000, "nnz": 20140928},
    6: {"rows": 51272, "nnz": 41989040},
}
SOURCE_FILES = (
    "benchmarks/task035b_p7_capability_resource_gate.py",
    "src/common/config_3d.py",
    "src/constraints/floquet_3d.py",
    "src/constraints/high_order_floquet_trace.py",
    "src/solvers/hcurl_assembly_time_condensation.py",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _git(repo_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout.strip()


def _verified_source_identity(
    repo_root: Path,
    verified_clean_sha: str,
) -> dict[str, Any]:
    head = _git(repo_root, "rev-parse", "HEAD")
    branch = _git(repo_root, "branch", "--show-current")
    status = _git(
        repo_root,
        "status",
        "--short",
        "--untracked-files=all",
    )
    checks = {
        "full_verified_sha": (
            len(verified_clean_sha) == 40
            and all(
                character in "0123456789abcdef"
                for character in verified_clean_sha.lower()
            )
        ),
        "head_matches_verified_sha": head == verified_clean_sha,
        "expected_branch": branch == EXPECTED_BRANCH,
        "tracked_and_untracked_worktree_clean": status == "",
    }
    if not all(checks.values()):
        raise SystemExit(
            "p7 capability/resource source gate failed: "
            + ", ".join(
                name for name, passed in checks.items() if not passed
            )
        )
    return {
        "commit_sha": head,
        "verified_clean_sha": verified_clean_sha,
        "branch": branch,
        "tracked_source_dirty": False,
        "stable_and_clean_before": True,
        "checks": checks,
    }


def _environment_identity(repo_root: Path) -> dict[str, Any]:
    executable = Path(sys.executable).resolve()
    expected_python = (repo_root / ".venv/bin/python").resolve()
    checks = {
        "qualified_activation_marker": (
            os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION") == "1"
        ),
        "repo_virtualenv_python": executable == expected_python,
        "linux_runtime": sys.platform.startswith("linux"),
        "complex128_petsc": np.dtype(PETSc.ScalarType) == np.dtype(
            np.complex128
        ),
        "int32_petsc": np.dtype(PETSc.IntType) == np.dtype(np.int32),
        "serial_preflight_only": MPI.COMM_WORLD.size == 1,
    }
    if not all(checks.values()):
        raise RuntimeError(
            "p7 capability/resource ABI gate failed: "
            + ", ".join(
                name for name, passed in checks.items() if not passed
            )
        )
    return {
        "checks": checks,
        "python_executable": str(executable),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "basix_version": basix.__version__,
        "dolfinx_version": dolfinx.__version__,
        "petsc4py_version": petsc4py.__version__,
        "mpi4py_version": mpi4py.__version__,
        "petsc_scalar_type": np.dtype(PETSc.ScalarType).name,
        "petsc_int_type": np.dtype(PETSc.IntType).name,
        "mpi_world_size": MPI.COMM_WORLD.size,
    }


def _raw_basix_layout(degree: int) -> dict[str, Any]:
    hexa = element("N1curl", "hexahedron", degree).basix_element

    def uniform_count(entity_dimension: int) -> int:
        counts = {
            len(entity_dofs)
            for entity_dofs in hexa.entity_dofs[entity_dimension]
        }
        if len(counts) != 1:
            raise RuntimeError(
                "Basix returned a non-uniform N1curl entity layout"
            )
        return int(next(iter(counts)))

    observed = {
        "element_dimension": int(hexa.dim),
        "edge_dofs_per_entity": uniform_count(1),
        "face_dofs_per_entity": uniform_count(2),
        "cell_interior_dofs_per_entity": uniform_count(3),
    }
    expected = {
        "element_dimension": 3 * degree * (degree + 1) ** 2,
        "edge_dofs_per_entity": degree,
        "face_dofs_per_entity": 2 * degree * (degree - 1),
        "cell_interior_dofs_per_entity": (
            3 * degree * (degree - 1) ** 2
        ),
    }
    if observed != expected:
        raise RuntimeError(
            "raw Basix p7 layout differs from tensor-product formulas: "
            f"observed={observed}, expected={expected}"
        )
    return {
        "available": True,
        **observed,
        "local_trace_dimension": (
            observed["element_dimension"]
            - observed["cell_interior_dofs_per_entity"]
        ),
        "dof_transformations_are_identity": bool(
            hexa.dof_transformations_are_identity
        ),
        "dof_transformations_are_permutations": bool(
            hexa.dof_transformations_are_permutations
        ),
    }


def _rejected_probe(callable_: Any) -> dict[str, Any]:
    try:
        callable_()
    except (NotImplementedError, ValueError) as error:
        return {
            "rejected": True,
            "exception_type": type(error).__name__,
            "message": str(error),
        }
    return {
        "rejected": False,
        "exception_type": None,
        "message": None,
    }


def _capability_audit() -> dict[str, Any]:
    cfg = target_stage4_config(degree=P7_DEGREE, h_nm=10.0)
    layout_probe = _rejected_probe(
        lambda: high_order_trace_layout(P7_DEGREE)
    )
    dispatcher_probe = _rejected_probe(
        lambda: _qualified_constraint_mode(
            P7_DEGREE,
            tetrahedral=False,
            fixed_target_high_order=True,
        )
    )
    explicit_mode_probe = _rejected_probe(
        lambda: type(cfg)(
            **{
                **cfg.__dict__,
                "floquet_constraint_mode": "topological_trace_p7",
            }
        ).floquet_constraint_mode_requested
    )
    checks = {
        "raw_basix_hexa_n1curl_p7_available": True,
        "qualified_trace_layout_rejects_p7": layout_probe["rejected"],
        "fixed_target_floquet_dispatcher_rejects_p7": dispatcher_probe[
            "rejected"
        ],
        "explicit_p7_floquet_mode_rejected": explicit_mode_probe["rejected"],
        "end_to_end_p7_floquet_qualified": False,
        "end_to_end_p7_assembly_time_condensation_qualified": False,
    }
    if not all(
        checks[name]
        for name in (
            "raw_basix_hexa_n1curl_p7_available",
            "qualified_trace_layout_rejects_p7",
            "fixed_target_floquet_dispatcher_rejects_p7",
            "explicit_p7_floquet_mode_rejected",
        )
    ):
        raise RuntimeError("p7 capability probes changed unexpectedly")
    return {
        "candidate_capability_pass": False,
        "checks": checks,
        "raw_basix_layout": _raw_basix_layout(P7_DEGREE),
        "qualified_trace_layout_probe": layout_probe,
        "fixed_target_floquet_dispatcher_probe": dispatcher_probe,
        "explicit_p7_floquet_mode_probe": explicit_mode_probe,
        "assembly_time_condensation_interpretation": (
            "The local Schur implementation is written in entity-layout "
            "terms, but no p7 end-to-end Floquet transform, orientation, "
            "preallocation, residual, or MPI8 qualification exists. The "
            "Floquet capability gate is reached before a formal condensed "
            "p7 solve could be authorized."
        ),
    }


def _structured_entity_counts(
    axis_cells: tuple[int, int, int],
) -> dict[str, int]:
    nx, ny, nz = axis_cells
    return {
        "vertices": (nx + 1) * (ny + 1) * (nz + 1),
        "edges": (
            nx * (ny + 1) * (nz + 1)
            + (nx + 1) * ny * (nz + 1)
            + (nx + 1) * (ny + 1) * nz
        ),
        "faces": (
            (nx + 1) * ny * nz
            + nx * (ny + 1) * nz
            + nx * ny * (nz + 1)
        ),
        "cells": nx * ny * nz,
    }


def _periodic_quotient_entity_counts(
    axis_cells: tuple[int, int, int],
) -> dict[str, int]:
    nx, ny, nz = axis_cells
    return {
        "vertices": nx * ny * (nz + 1),
        "edges": (
            2 * nx * ny * (nz + 1)
            + nx * ny * nz
        ),
        "faces": (
            nx * ny * (nz + 1)
            + 2 * nx * ny * nz
        ),
        "cells": nx * ny * nz,
    }


def _trace_entities_by_cell(
    axis_cells: tuple[int, int, int],
) -> Iterable[tuple[tuple[Any, ...], ...]]:
    nx, ny, nz = axis_cells
    for i in range(nx):
        for j in range(ny):
            for k in range(nz):
                i_plus = (i + 1) % nx
                j_plus = (j + 1) % ny
                yield (
                    ("edge_x", i, j, k),
                    ("edge_x", i, j_plus, k),
                    ("edge_x", i, j, k + 1),
                    ("edge_x", i, j_plus, k + 1),
                    ("edge_y", i, j, k),
                    ("edge_y", i_plus, j, k),
                    ("edge_y", i, j, k + 1),
                    ("edge_y", i_plus, j, k + 1),
                    ("edge_z", i, j, k),
                    ("edge_z", i_plus, j, k),
                    ("edge_z", i, j_plus, k),
                    ("edge_z", i_plus, j_plus, k),
                    ("face_xy", i, j, k),
                    ("face_xy", i, j, k + 1),
                    ("face_xz", i, j, k),
                    ("face_xz", i, j_plus, k),
                    ("face_yz", i, j, k),
                    ("face_yz", i_plus, j, k),
                )


def _base_trace_schur_nnz(
    axis_cells: tuple[int, int, int],
    degree: int,
) -> tuple[int, int]:
    adjacency: defaultdict[
        tuple[Any, ...], set[tuple[Any, ...]]
    ] = defaultdict(set)
    for entities in _trace_entities_by_cell(axis_cells):
        if len(set(entities)) != 18:
            raise ValueError(
                "axis plan is too small for the periodic quotient audit"
            )
        for row_entity in entities:
            adjacency[row_entity].update(entities)

    def dofs(entity: tuple[Any, ...]) -> int:
        if str(entity[0]).startswith("edge"):
            return degree
        return 2 * degree * (degree - 1)

    nnz = sum(
        dofs(row_entity)
        * sum(dofs(column_entity) for column_entity in columns)
        for row_entity, columns in adjacency.items()
    )
    max_row_width = max(
        sum(dofs(column_entity) for column_entity in columns)
        for columns in adjacency.values()
    )
    return int(nnz), int(max_row_width)


def _load_calibration(repo_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    records: dict[str, dict[str, Any]] = {}
    for specification in CALIBRATION_SOURCES:
        path = repo_root / specification["record_path"]
        record = json.loads(path.read_text(encoding="utf-8"))
        records[specification["record_path"]] = record
        candidate = record[specification["field"]]
        degree = int(specification["degree"])
        condensation = candidate.get("cell_static_condensation") or {}
        matrix_resource = (
            candidate.get("high_order_resource_audit") or {}
        ).get("matrix_factor_resource") or {}
        common_mesh = record.get("common_mesh_identity") or {}
        source = record.get("source") or {}
        full_residual = (
            (
                condensation.get("full_explicit_true_residual")
                or {}
            ).get("linear_system_relative_residual")
        )
        matrix_stats = candidate.get("matrix_stats") or {}
        expected_resource = _H10_DEGREE_RESOURCE_IDENTITY[degree]
        actual_record_sha256 = _sha256(path)
        checks = {
            "record_sha256_frozen": (
                actual_record_sha256
                == specification["record_sha256"]
            ),
            "source_commit_and_cleanliness_frozen": (
                source.get("commit_sha")
                == specification["source_commit_sha"]
                and source.get("verified_clean_sha")
                == specification["source_commit_sha"]
                and source.get("head_after_sha")
                == specification["source_commit_sha"]
                and source.get("tracked_source_dirty") is False
                and source.get("stable_and_clean_after") is True
                and source.get("status_after_before_record_write") == ""
            ),
            "formal_record_pass": (
                record.get("status") == "actual_global_r5_pass"
                and (record.get("qualification") or {}).get("pass") is True
            ),
            "fixed_geometry": (
                (record.get("target_identity") or {}).get("geometry")
                == "Task034 fixed rectangular block grating"
            ),
            "degree": int(candidate.get("degree", -1)) == degree,
            "h10": float(candidate.get("h_nm", -1.0)) == 10.0,
            "frozen_mesh_and_tag_identity": (
                all(
                    common_mesh.get(key) == value
                    for key, value in _H10_MESH_IDENTITY.items()
                )
                and (
                    common_mesh.get("material_plane_alignment") or {}
                ).get("all_aligned")
                is True
                and candidate.get("mesh_cell_type_actual")
                == "hexahedron"
                and int(candidate.get("num_mesh_cells", -1)) == 252
            ),
            "mpi8_official_result": (
                candidate.get("mpi_size") == 8
                and candidate.get("official_result") is True
            ),
            "assembly_time_condensation": (
                candidate.get(
                    "stage4_assembly_time_cell_static_condensation"
                )
                is True
            ),
            "floquet_slave_elimination": (
                candidate.get("stage4_floquet_slave_elimination") is True
            ),
            "eighty_appended_rows": (
                int(condensation.get("appended_rows", -1))
                == DTN_AUXILIARY_ROWS
            ),
            "full_explicit_true_residual_le_1e-9": (
                isinstance(full_residual, (int, float))
                and np.isfinite(full_residual)
                and float(full_residual) <= 1.0e-9
            ),
            "measured_rows_and_nnz_frozen": (
                int(matrix_stats.get("matrix_rows", -1))
                == expected_resource["rows"]
                and int(matrix_stats.get("matrix_nnz_used", -1))
                == expected_resource["nnz"]
            ),
        }
        if not all(checks.values()):
            raise ValueError(
                f"p{degree} calibration authority failed: "
                + ", ".join(
                    name for name, passed in checks.items() if not passed
                )
            )
        core_nnz, core_max_width = _base_trace_schur_nnz(
            H10_AXIS_CELLS,
            degree,
        )
        matrix_nnz = int(matrix_stats["matrix_nnz_used"])
        rows.append(
            {
                "degree": degree,
                "record_path": specification["record_path"],
                "record_sha256": actual_record_sha256,
                "record_field": specification["field"],
                "checks": checks,
                "full3d_equivalent_dofs": int(
                    candidate["num_nedelec_dofs"]
                ),
                "active_rows_with_dtn": int(
                    matrix_stats["matrix_rows"]
                ),
                "matrix_nnz_measured": matrix_nnz,
                "base_trace_schur_nnz_exact": core_nnz,
                "dtn_port_nnz_correction_measured": (
                    matrix_nnz - core_nnz
                ),
                "matrix_max_row_width_measured": int(
                    matrix_stats[
                        "matrix_maximum_nnz_per_row"
                    ]
                ),
                "base_max_row_width_exact": core_max_width,
                "factor_nnz_measured": int(
                    matrix_resource["factor_nnz"]
                ),
                "factor_fill_ratio_measured": float(
                    matrix_resource["factor_fill_ratio"]
                ),
            }
        )
    if [row["degree"] for row in rows] != [4, 5, 6]:
        raise RuntimeError("p7 projection requires ordered p4/p5/p6 anchors")
    p45_path = CALIBRATION_SOURCES[0]["record_path"]
    p56_path = CALIBRATION_SOURCES[2]["record_path"]
    p5_from_p45 = records[p45_path]["enriched"]
    p5_from_p56 = records[p56_path]["coarse"]
    duplicate_fields = (
        "degree",
        "h_nm",
        "mpi_size",
        "num_mesh_cells",
        "num_nedelec_dofs",
        "official_result",
        "stage4_assembly_time_cell_static_condensation",
        "stage4_floquet_slave_elimination",
    )
    duplicate_p5_closure = bool(
        all(
            p5_from_p45.get(field) == p5_from_p56.get(field)
            for field in duplicate_fields
        )
        and all(
            (p5_from_p45.get("matrix_stats") or {}).get(field)
            == (p5_from_p56.get("matrix_stats") or {}).get(field)
            for field in (
                "matrix_rows",
                "matrix_cols",
                "matrix_nnz_used",
                "matrix_maximum_nnz_per_row",
            )
        )
    )
    if not duplicate_p5_closure:
        raise ValueError(
            "the repeated p5 calibration does not close across authorities"
        )
    rows[1]["checks"]["duplicate_p5_authority_closure"] = True
    rows[1]["duplicate_p5_authority_closure"] = {
        "pass": True,
        "p4_p5_record": p45_path,
        "p5_p6_record": p56_path,
        "fields": list(duplicate_fields),
    }
    return rows


def _resource_projection(repo_root: Path) -> dict[str, Any]:
    degree = P7_DEGREE
    entities = _structured_entity_counts(H10_AXIS_CELLS)
    quotient = _periodic_quotient_entity_counts(H10_AXIS_CELLS)
    edge_per_entity = degree
    face_per_entity = 2 * degree * (degree - 1)
    cell_per_entity = 3 * degree * (degree - 1) ** 2
    full_dofs = (
        entities["edges"] * edge_per_entity
        + entities["faces"] * face_per_entity
        + entities["cells"] * cell_per_entity
    )
    full_trace_rows = (
        entities["edges"] * edge_per_entity
        + entities["faces"] * face_per_entity
    )
    periodic_trace_rows = (
        quotient["edges"] * edge_per_entity
        + quotient["faces"] * face_per_entity
    )
    matrix_rows = periodic_trace_rows + DTN_AUXILIARY_ROWS
    base_nnz, base_max_width = _base_trace_schur_nnz(
        H10_AXIS_CELLS,
        degree,
    )
    calibration = _load_calibration(repo_root)
    corrections = [
        row["dtn_port_nnz_correction_measured"] for row in calibration
    ]
    first_difference_45 = corrections[1] - corrections[0]
    first_difference_56 = corrections[2] - corrections[1]
    second_difference = first_difference_56 - first_difference_45
    projected_port_correction = (
        corrections[2] + first_difference_56 + second_difference
    )
    projected_matrix_nnz = base_nnz + projected_port_correction
    nx, ny, _nz = H10_AXIS_CELLS
    boundary_trace_rows_both_ports = 4 * nx * ny * degree**2
    modes_per_port = DTN_AUXILIARY_ROWS // 2
    conservative_port_nnz = (
        2 * boundary_trace_rows_both_ports * modes_per_port
        + 2 * modes_per_port**2
    )
    conservative_matrix_nnz_upper = base_nnz + conservative_port_nnz
    fill_ratios = [
        row["factor_fill_ratio_measured"] for row in calibration
    ]
    candidate_resource_pass = full_dofs <= FULL3D_EQUIVALENT_DOF_LIMIT
    checks = {
        "h10_axis_plan_is_frozen_6_3_14": (
            H10_AXIS_CELLS == (6, 3, 14)
        ),
        "cell_count_is_252": entities["cells"] == 252,
        "p4_p5_p6_calibration_authorities_pass": all(
            all(row["checks"].values()) for row in calibration
        ),
        "full3d_equivalent_dofs_le_90000": candidate_resource_pass,
    }
    return {
        "candidate_resource_pass": candidate_resource_pass,
        "checks": checks,
        "mesh": {
            "h_nm": 10.0,
            "axis_cells": list(H10_AXIS_CELLS),
            "entity_counts_before_periodic_identification": entities,
            "periodic_quotient_entity_counts": quotient,
        },
        "p7_layout": {
            "edge_dofs_per_entity": edge_per_entity,
            "face_dofs_per_entity": face_per_entity,
            "cell_interior_dofs_per_entity": cell_per_entity,
            "local_element_dimension": 3 * degree * (degree + 1) ** 2,
            "local_trace_dimension": 12 * degree**2,
            "local_interior_dimension": cell_per_entity,
            "one_dense_local_tensor_entries": (
                3 * degree * (degree + 1) ** 2
            )
            ** 2,
            "one_dense_complex128_local_tensor_mib": (
                (3 * degree * (degree + 1) ** 2) ** 2
                * np.dtype(np.complex128).itemsize
                / 2**20
            ),
            "one_dense_complex128_trace_schur_mib": (
                (12 * degree**2) ** 2
                * np.dtype(np.complex128).itemsize
                / 2**20
            ),
            "interior_lu_cubic_work_ratio_vs_p6": (
                cell_per_entity / (3 * 6 * 5**2)
            )
            ** 3,
        },
        "row_projection": {
            "full3d_equivalent_dofs": full_dofs,
            "full_trace_rows_before_floquet": full_trace_rows,
            "floquet_slave_rows_projected": (
                full_trace_rows - periodic_trace_rows
            ),
            "periodic_independent_trace_rows": periodic_trace_rows,
            "dtn_auxiliary_rows": DTN_AUXILIARY_ROWS,
            "active_matrix_rows_with_dtn": matrix_rows,
            "full3d_equivalent_dof_limit": (
                FULL3D_EQUIVALENT_DOF_LIMIT
            ),
            "dof_limit_excess": (
                full_dofs - FULL3D_EQUIVALENT_DOF_LIMIT
            ),
            "dof_to_limit_ratio": (
                full_dofs / FULL3D_EQUIVALENT_DOF_LIMIT
            ),
        },
        "matrix_projection": {
            "semantics": "predicted_not_measured_no_matrix_assembled",
            "base_trace_schur_nnz_exact_topology": base_nnz,
            "dtn_port_nnz_correction_projected": (
                projected_port_correction
            ),
            "matrix_nnz_used_projected": projected_matrix_nnz,
            "matrix_nnz_conservative_structural_upper": (
                conservative_matrix_nnz_upper
            ),
            "average_row_width_projected": (
                projected_matrix_nnz / matrix_rows
            ),
            "maximum_base_row_width_exact": base_max_width,
            "factor_nnz_planning_envelope": {
                "semantics": (
                    "derived_not_measured; p4/p5/p6 measured fill-ratio "
                    "envelope applied to the projected p7 matrix NNZ"
                ),
                "lower": int(projected_matrix_nnz * min(fill_ratios)),
                "upper": int(projected_matrix_nnz * max(fill_ratios)),
            },
            "used_structure_storage_planning_assumption_gib": (
                projected_matrix_nnz * 24 / 2**30
            ),
            "used_structure_storage_planning_assumption": {
                "bytes_per_nnz": 24,
                "semantics": (
                    "conservative planning convention, not a lower bound "
                    "and not a measured PETSc allocation"
                ),
                "components": (
                    "complex128 value plus column-index and sparse-"
                    "structure/allocator allowance"
                ),
            },
            "peak_memory": None,
            "peak_memory_reason": (
                "No p7 factorization or lifecycle was authorized; matrix "
                "storage and factor-NNZ projections cannot be promoted to a "
                "simultaneous process-tree peak."
            ),
            "projection_method": (
                "Exact periodic-quotient cell-trace adjacency plus a "
                "second-finite-difference extrapolation of the measured "
                "p4/p5/p6 DtN-port NNZ corrections."
            ),
        },
        "calibration": calibration,
    }


def build_p7_capability_resource_gate(
    repo_root: Path,
    *,
    source: dict[str, Any],
) -> dict[str, Any]:
    """Build one evidence record without constructing or solving a PDE."""

    repo_root = repo_root.resolve()
    environment = _environment_identity(repo_root)
    capability = _capability_audit()
    resources = _resource_projection(repo_root)
    source_checks = source.get("checks") or {}
    source_identity_pass = bool(
        source.get("branch") == EXPECTED_BRANCH
        and source.get("commit_sha") == source.get("verified_clean_sha")
        and isinstance(source.get("commit_sha"), str)
        and len(source["commit_sha"]) == 40
        and all(
            character in "0123456789abcdef"
            for character in source["commit_sha"].lower()
        )
        and source.get("tracked_source_dirty") is False
        and source.get("stable_and_clean_before") is True
        and bool(source_checks)
        and all(value is True for value in source_checks.values())
    )
    gate_checks = {
        "clean_source_identity_hash_bound": source_identity_pass,
        "environment_qualified": all(environment["checks"].values()),
        "raw_basix_probe_complete": (
            capability["raw_basix_layout"]["available"] is True
        ),
        "capability_blocker_reproduced": (
            capability["candidate_capability_pass"] is False
        ),
        "resource_blocker_reproduced": (
            resources["candidate_resource_pass"] is False
        ),
        "formal_pde_not_authorized": True,
        "ordinary_default_unchanged": True,
    }
    evidence_valid = all(gate_checks.values())
    return {
        "schema_version": (
            "task035b.p7-h10-capability-resource-controlled-stop.v1"
        ),
        "benchmark_id": "task035b_p7_h10_capability_resource_gate",
        "status": (
            "p7_not_run_by_capability_or_resource_gate"
            if evidence_valid
            else "p7_gate_evidence_invalid"
        ),
        "pass": evidence_valid,
        "classification": "controlled_stop_before_pde",
        "candidate": {
            "geometry": "Task034 fixed rectangular block grating",
            "mesh": "structured hexa h10",
            "axis_cells": list(H10_AXIS_CELLS),
            "nedelec_degree": P7_DEGREE,
            "planned_mpi_size_if_qualified": 8,
        },
        "pde": {
            "status": "not_run",
            "heavy_case_started": False,
            "mesh_built": False,
            "form_compiled": False,
            "matrix_assembled": False,
            "factorization_started": False,
            "solver_failure": False,
        },
        "source": source,
        "source_file_sha256": {
            path: _sha256(repo_root / path) for path in SOURCE_FILES
        },
        "environment": environment,
        "capability_gate": capability,
        "resource_gate": resources,
        "qualification": {
            "evidence_valid": evidence_valid,
            "candidate_capability_pass": False,
            "candidate_resource_pass": False,
            "p7_pde_authorized": False,
            "checks": gate_checks,
        },
        "decision": {
            "status": "p7_not_run_by_capability_or_resource_gate",
            "independent_stop_reasons": [
                (
                    "The current qualified high-order trace/Floquet path "
                    "ends at p6; raw Basix p7 availability is not an "
                    "end-to-end solver qualification."
                ),
                (
                    "Global p7/h10 has 273581 Full3D-equivalent DoF, "
                    "which exceeds the Task035b 90000-DoF ceiling before "
                    "accuracy or factor-memory testing."
                ),
            ],
            "reopen_conditions": [
                (
                    "Qualify p7 trace transformations, double-Floquet "
                    "constraints, assembly-time Schur recovery, full "
                    "explicit residual, MPI identity, and all physics gates."
                ),
                (
                    "Provide a physically reduced local/regionwise p7 "
                    "candidate whose Full3D-equivalent DoF is <=90000; "
                    "retaining a global p7 storage space and zeroing "
                    "coefficients does not satisfy this condition."
                ),
            ],
            "ordinary_default_changed": False,
            "scientific_gate_relaxed": False,
        },
    }


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--verified-clean-sha", required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    repo_root = args.repo_root.resolve()
    source = _verified_source_identity(
        repo_root,
        args.verified_clean_sha,
    )
    output = (
        args.output
        if args.output.is_absolute()
        else repo_root / args.output
    ).resolve()
    if not output.is_relative_to(repo_root):
        raise SystemExit("p7 gate output must remain inside the repository")
    output.parent.mkdir(parents=True, exist_ok=True)
    record = build_p7_capability_resource_gate(
        repo_root,
        source=source,
    )
    with output.open("x", encoding="utf-8") as stream:
        json.dump(record, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return 0 if record["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
