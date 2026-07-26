#!/usr/bin/env python3
"""Generate Task035d Phase-A compact reference and MPI fixture authorities.

This is not a physical PDE runner.  It builds reference-cell algebra and
small structured topology fixtures only.  The two modes are intentionally
separate so the MPI2 authority is produced by a real two-rank process rather
than inferred from the serial record.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

import basix
import dolfinx
import numpy as np
from dolfinx import mesh
from mpi4py import MPI
from petsc4py import PETSc

from src.adaptivity.exact_sequence_variable_p import (
    HexaEntityDegreeMap,
    allowed_dimension_degree_triples,
    build_p4_p6_entity_dof_catalog,
    build_variable_p_reference_space,
)
from src.adaptivity.variable_p_entity_map import (
    build_variable_p_global_entity_map,
    structural_sparsity_audit,
)
from src.adaptivity.variable_p_periodic_orbits import (
    audit_variable_p_periodic_orbits,
)
from src.solvers.hcurl_affine_isotropic_tensor import (
    AffineIsotropicMaxwellTensorFactory,
    AffineIsotropicMaxwellTensorSpec,
)
from src.solvers.hcurl_variable_p_local import (
    condense_variable_p_local_tensor,
    project_p6_local_tensor,
)


ROOT = Path(__file__).resolve().parents[3]
CASE = ROOT / "benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity"
RECORDS = CASE / "records"
SERIAL_RECORD = RECORDS / "reference_active_space_authority_v1.json"
MPI2_RECORD = RECORDS / "mpi2_fixture_authority_v1.json"
MANIFEST = RECORDS / "compact_authority_v1.json"
SOURCE_PATHS = (
    "src/adaptivity/exact_sequence_variable_p.py",
    "src/adaptivity/variable_p_entity_map.py",
    "src/adaptivity/variable_p_periodic_orbits.py",
    "src/solvers/hcurl_variable_p_local.py",
    "src/test/test_183_task035d_reference_active_space.py",
    "src/test/test_184_task035d_global_entity_numbering.py",
    (
        "benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/"
        "generate_reference_authority.py"
    ),
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _git_head() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
    ).strip()


def _source_identity() -> dict[str, Any]:
    return {
        "commit_sha": _git_head(),
        "file_sha256": {
            path: _sha256(ROOT / path) for path in SOURCE_PATHS
        },
        "ordinary_default_changed": False,
    }


def _environment() -> dict[str, Any]:
    return {
        "basix_version": str(basix.__version__),
        "dolfinx_version": str(dolfinx.__version__),
        "petsc_scalar_type": np.dtype(PETSc.ScalarType).name,
        "petsc_int_type": np.dtype(PETSc.IntType).name,
        "mpi_size": int(MPI.COMM_WORLD.size),
    }


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    return value


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(
        _json_safe(payload),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    path.write_text(text + "\n", encoding="utf-8")


def _degree_array(msh, dimension: int, degree: int) -> np.ndarray:
    msh.topology.create_entities(dimension)
    index_map = msh.topology.index_map(dimension)
    return np.full(
        int(index_map.size_local + index_map.num_ghosts),
        int(degree),
        dtype=np.int32,
    )


def _entity_fixture(msh) -> dict[str, Any]:
    variable = build_variable_p_global_entity_map(
        msh,
        edge_degrees=_degree_array(msh, 1, 4),
        face_degrees=_degree_array(msh, 2, 5),
        cell_degrees=_degree_array(msh, 3, 6),
    )
    control = build_variable_p_global_entity_map(
        msh,
        edge_degrees=_degree_array(msh, 1, 6),
        face_degrees=_degree_array(msh, 2, 6),
        cell_degrees=_degree_array(msh, 3, 6),
    )
    phase_x = np.exp(0.2j)
    phase_y = np.exp(-0.3j)
    return {
        "variable_entity_map": dict(variable.audit),
        "uniform_p6_entity_map": dict(control.audit),
        "variable_condensed_sparsity": structural_sparsity_audit(
            variable,
            condensed_trace=True,
        ),
        "uniform_p6_condensed_sparsity": structural_sparsity_audit(
            control,
            condensed_trace=True,
        ),
        "periodic_x": audit_variable_p_periodic_orbits(
            variable,
            axes=("x",),
            phase_x=phase_x,
            phase_y=phase_y,
        ),
        "periodic_y": audit_variable_p_periodic_orbits(
            variable,
            axes=("y",),
            phase_x=phase_x,
            phase_y=phase_y,
        ),
        "periodic_xy": audit_variable_p_periodic_orbits(
            variable,
            axes=("x", "y"),
            phase_x=phase_x,
            phase_y=phase_y,
        ),
    }


def _compact_space_audit(
    degree_map: HexaEntityDegreeMap,
) -> dict[str, Any]:
    space = build_variable_p_reference_space(degree_map)

    def orientation_summary(name: str) -> dict[str, Any]:
        values = dict(space.audit[name])
        generators = values.pop("generators")
        values["generator_block_sha256"] = [
            generator["block_sha256"] for generator in generators
        ]
        return values

    return {
        "degree_map": degree_map.to_dict(),
        "hcurl_dimension": space.hcurl_dimension,
        "h1_dimension": space.h1_dimension,
        "active_trace_dimension": space.audit["active_trace_dimension"],
        "active_cell_interior_dimension": space.audit[
            "active_cell_interior_dimension"
        ],
        "inactive_p6_local_modes": space.audit["inactive_p6_local_modes"],
        "hcurl_custom": space.audit["hcurl_construction"]["custom"],
        "h1_custom": space.audit["h1_construction"]["custom"],
        "hcurl_expansion_sha256": space.audit[
            "hcurl_expansion_sha256"
        ],
        "h1_expansion_sha256": space.audit["h1_expansion_sha256"],
        "discrete_gradient_sha256": space.audit[
            "discrete_gradient_sha256"
        ],
        "gradient_rank": space.audit["gradient_rank"],
        "expected_nonconstant_gradient_dimension": space.audit[
            "expected_nonconstant_gradient_dimension"
        ],
        "sampled_curl_nullity": space.audit["sampled_curl_nullity"],
        "gradient_embedding_error_max": space.audit[
            "gradient_embedding_error_max"
        ],
        "curl_gradient_error_max": space.audit[
            "curl_gradient_error_max"
        ],
        "hcurl_orientation": orientation_summary("hcurl_orientation"),
        "h1_orientation": orientation_summary("h1_orientation"),
        "pass": True,
    }


def _local_schur_authority() -> dict[str, Any]:
    degree_map = HexaEntityDegreeMap.dimension_uniform(
        edge_degree=4,
        face_degree=5,
        cell_degree=6,
    )
    active = build_variable_p_reference_space(degree_map)
    p6 = build_variable_p_reference_space(
        HexaEntityDegreeMap.uniform(6)
    )
    specification = AffineIsotropicMaxwellTensorSpec(
        curl_coefficient=1.25 + 0.0j,
        mass_coefficient_by_tag={1: 0.75 + 0.0j},
        quadrature_degree=12,
    )
    p6_tensor = AffineIsotropicMaxwellTensorFactory(
        p6.hcurl_element,
        specification,
    ).tensor(tag=1, widths=(0.8, 1.1, 1.4))
    direct_active = AffineIsotropicMaxwellTensorFactory(
        active.hcurl_element,
        specification,
    ).tensor(tag=1, widths=(0.8, 1.1, 1.4))
    projected = project_p6_local_tensor(active, p6_tensor)
    projection_relative_error = float(
        np.linalg.norm(projected - direct_active)
        / np.linalg.norm(direct_active)
    )
    rng = np.random.default_rng(35035)
    expected_active = (
        rng.standard_normal(active.hcurl_dimension)
        + 1j * rng.standard_normal(active.hcurl_dimension)
    )
    expected_p6 = active.expand_hcurl_coefficients(expected_active)
    condensed = condense_variable_p_local_tensor(
        active,
        p6_tensor,
        p6_tensor @ expected_p6,
    )
    trace = expected_active[active.trace_dofs]
    recovered_active = condensed.recover_active_coefficients(trace)
    recovered_p6 = condensed.recover_p6_coefficients(trace)
    schur_residual = condensed.schur_tensor @ trace - condensed.schur_rhs
    return {
        "status": "generalized_local_expansion_and_schur_pass",
        "pass": True,
        "projection_relative_error": projection_relative_error,
        "active_recovery_error_max": float(
            np.max(np.abs(recovered_active - expected_active))
        ),
        "p6_recovery_error_max": float(
            np.max(np.abs(recovered_p6 - expected_p6))
        ),
        "schur_equation_residual_max": float(
            np.max(np.abs(schur_residual))
        ),
        "audit": condensed.audit,
    }


def generate_serial() -> dict[str, Any]:
    if MPI.COMM_WORLD.size != 1:
        raise RuntimeError("serial authority must run without mpiexec")
    triples = []
    for edge, face, cell in allowed_dimension_degree_triples():
        triples.append(
            _compact_space_audit(
                HexaEntityDegreeMap.dimension_uniform(
                    edge_degree=edge,
                    face_degree=face,
                    cell_degree=cell,
                )
            )
        )
    heterogeneous = _compact_space_audit(
        HexaEntityDegreeMap(
            edges=(5,) + (4,) * 11,
            faces=(5,) * 6,
            cell=6,
        )
    )
    fixture_shapes = {}
    for shape in ((1, 1, 1), (2, 1, 1), (2, 2, 2)):
        msh = mesh.create_unit_cube(
            MPI.COMM_SELF,
            *shape,
            cell_type=mesh.CellType.hexahedron,
            ghost_mode=mesh.GhostMode.shared_facet,
        )
        fixture_shapes["x".join(map(str, shape))] = _entity_fixture(msh)
    record = {
        "schema_version": "task035d.reference-active-space-authority.v1",
        "status": "task035d_phase_a_serial_authority_pass",
        "pass": True,
        "source": _source_identity(),
        "environment": _environment(),
        "entity_dof_catalog": build_p4_p6_entity_dof_catalog(),
        "dimension_uniform_exact_sequence_spaces": triples,
        "heterogeneous_entity_space": heterogeneous,
        "local_expansion_and_schur": _local_schur_authority(),
        "serial_fixtures": fixture_shapes,
        "heavy_pde_started": False,
        "ordinary_default_changed": False,
    }
    _write(SERIAL_RECORD, record)
    return record


def generate_mpi2() -> dict[str, Any]:
    if MPI.COMM_WORLD.size != 2:
        raise RuntimeError("MPI fixture authority requires exactly two ranks")
    msh = mesh.create_unit_cube(
        MPI.COMM_WORLD,
        2,
        2,
        2,
        cell_type=mesh.CellType.hexahedron,
        ghost_mode=mesh.GhostMode.shared_facet,
    )
    fixture = _entity_fixture(msh)
    identity = fixture["variable_entity_map"][
        "canonical_degree_map_sha256"
    ]
    identities = MPI.COMM_WORLD.allgather(identity)
    record = {
        "schema_version": "task035d.mpi2-fixture-authority.v1",
        "status": "task035d_phase_a_mpi2_fixture_pass",
        "pass": len(set(identities)) == 1,
        "source": _source_identity(),
        "environment": _environment(),
        "fixture": fixture,
        "rank_identity_sha256": identities,
        "rank_identity_match": len(set(identities)) == 1,
        "owned_cell_count_sum": MPI.COMM_WORLD.allreduce(
            len(
                build_variable_p_global_entity_map(
                    msh,
                    edge_degrees=_degree_array(msh, 1, 4),
                    face_degrees=_degree_array(msh, 2, 5),
                    cell_degrees=_degree_array(msh, 3, 6),
                ).owned_cells
            ),
            op=MPI.SUM,
        ),
        "heavy_pde_started": False,
        "ordinary_default_changed": False,
    }
    if MPI.COMM_WORLD.rank == 0:
        _write(MPI2_RECORD, record)
    MPI.COMM_WORLD.Barrier()
    return record


def update_manifest() -> dict[str, Any]:
    if MPI.COMM_WORLD.size != 1:
        raise RuntimeError("manifest update is serial")
    rows = []
    for path in (SERIAL_RECORD, MPI2_RECORD):
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows.append(
            {
                "name": path.name,
                "sha256": _sha256(path),
                "schema_version": payload["schema_version"],
                "status": payload["status"],
            }
        )
    manifest = {
        "schema_version": "task035d.case097-compact-authority.v1",
        "status": "case097_phase_a_compact_authority",
        "pass": True,
        "record_count": len(rows),
        "records": rows,
        "source_commit_sha": _git_head(),
        "heavy_pde_started": False,
        "ordinary_default_changed": False,
    }
    _write(MANIFEST, manifest)
    return manifest


def check() -> dict[str, Any]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    failures: list[str] = []
    for row in manifest["records"]:
        path = RECORDS / row["name"]
        if _sha256(path) != row["sha256"]:
            failures.append(f"{row['name']}: sha256 mismatch")
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != row["schema_version"]:
            failures.append(f"{row['name']}: schema mismatch")
        if payload.get("status") != row["status"]:
            failures.append(f"{row['name']}: status mismatch")
        if payload.get("pass") is not True:
            failures.append(f"{row['name']}: pass is not true")
        if payload.get("heavy_pde_started") is not False:
            failures.append(f"{row['name']}: unexpected heavy PDE")
    return {
        "status": (
            "case097_compact_authority_pass"
            if not failures
            else "case097_compact_authority_fail"
        ),
        "pass": not failures,
        "record_count": len(manifest["records"]),
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=("serial", "mpi2", "manifest", "check"),
        required=True,
    )
    args = parser.parse_args()
    if args.mode == "serial":
        payload = generate_serial()
    elif args.mode == "mpi2":
        payload = generate_mpi2()
    elif args.mode == "manifest":
        payload = update_manifest()
    else:
        payload = check()
    if MPI.COMM_WORLD.rank == 0:
        print(json.dumps(_json_safe(payload), sort_keys=True))
    return 0 if payload.get("pass") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
