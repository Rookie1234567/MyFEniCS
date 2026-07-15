from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time
from typing import Any

from basix.ufl import element
from dolfinx import default_real_type, fem
from mpi4py import MPI
import numpy as np
from petsc4py import PETSc

try:
    import resource
except ModuleNotFoundError:  # pragma: no cover - Windows host research path
    resource = None

from src.common.config_3d import target_stage4_config
from src.coupling.modal_trace_projection import (
    ModalTraceProjection,
    build_matched_interface_trace,
    extract_tangential_trace,
    trace_subspace_report,
)
from src.geometry.mesh_builder_3d import _structured_hexa_mesh, stage4_axis_plan
from src.modes.cross_section_spaces import (
    build_cross_section_spaces,
    build_matching_cross_section,
)
from src.modes.mode_classification import build_biorthogonal_mode_basis
from src.modes.quadratic_beta_eigenproblem import (
    analytic_homogeneous_beta,
    assemble_quadratic_beta_operators,
    solve_quadratic_beta_modes,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = (
    ROOT
    / "benchmarks"
    / "artifacts"
    / "cases"
    / "080"
    / "phase5"
    / "matched_trace.json"
)


def _git(*args: str) -> str | None:
    try:
        return subprocess.check_output(
            ["git", *args], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _source_provenance(
    comm: MPI.Intracomm,
    verified_clean_sha: str | None,
    allow_dirty_research: bool,
) -> dict[str, Any]:
    if comm.rank == 0:
        head = _git("rev-parse", "HEAD")
        branch = _git("branch", "--show-current")
        tracked_status = (
            None
            if verified_clean_sha is not None
            else _git("status", "--porcelain", "--untracked-files=no")
        )
        payload = (head, branch, tracked_status)
    else:
        payload = None
    head, branch, tracked_status = comm.bcast(payload, root=0)
    if head is None or (verified_clean_sha is None and tracked_status is None):
        raise SystemExit("Cannot verify Task32 Phase5 source identity and cleanliness.")
    if verified_clean_sha is not None:
        verified = verified_clean_sha.strip().lower()
        if len(verified) != 40 or any(
            character not in "0123456789abcdef" for character in verified
        ):
            raise SystemExit("--verified-clean-sha must be a full Git SHA.")
        if head.lower() != verified:
            raise SystemExit(
                f"Clean-source attestation {verified} does not match HEAD {head}."
            )
        tracked_dirty = False
        verification = "host_git_clean_attestation"
    else:
        if tracked_status and not allow_dirty_research:
            raise SystemExit(
                "Tracked source is dirty. Commit Phase5 code first or pass "
                "--allow-dirty-research for a non-qualifying run."
            )
        tracked_dirty = bool(tracked_status)
        verification = "dirty_research_opt_in" if tracked_dirty else "local_git_status"
    return {
        "commit_sha": head,
        "branch": branch,
        "git_dirty": tracked_dirty,
        "tracked_source_dirty": tracked_dirty,
        "verification": verification,
        "verified_clean_sha": verified_clean_sha,
    }


def _historical_peak_rss_mb() -> float | None:
    if resource is None:
        return None
    return float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) / 1024.0


def _distributed_relative_error(
    actual: fem.Function, expected: fem.Function
) -> float:
    index_map = actual.function_space.dofmap.index_map
    owned = int(index_map.size_local * actual.function_space.dofmap.index_map_bs)
    difference = actual.x.array[:owned] - expected.x.array[:owned]
    local_num = float(np.vdot(difference, difference).real)
    local_den = float(np.vdot(expected.x.array[:owned], expected.x.array[:owned]).real)
    comm = actual.function_space.mesh.comm
    numerator = float(comm.allreduce(local_num, op=MPI.SUM))
    denominator = float(comm.allreduce(local_den, op=MPI.SUM))
    return float(np.sqrt(numerator / max(denominator, 1.0e-30)))


def _build_basis(cfg, material_kind: str):
    cross_section = build_matching_cross_section(cfg, material_kind)
    spaces = build_cross_section_spaces(cross_section, transverse_degree=2)
    operators = assemble_quadratic_beta_operators(cfg, cross_section, spaces)
    reference_index = cfg.n_air
    target = analytic_homogeneous_beta(cfg, reference_index)
    right_modes, _ = solve_quadratic_beta_modes(
        operators, target=target, requested_modes=2
    )
    basis = build_biorthogonal_mode_basis(
        cfg,
        cross_section,
        spaces,
        operators,
        right_modes,
        adjoint_target=np.conj(target),
        requested_left_modes=2,
    )
    return cross_section, spaces, operators, basis


def _affine_trace_validation(cfg, cross_section, spaces) -> dict[str, Any]:
    plan = stage4_axis_plan(cfg, MPI.COMM_WORLD.size)
    source_mesh = _structured_hexa_mesh(
        MPI.COMM_WORLD, plan.x_values, plan.y_values, plan.z_values
    )
    source_space = fem.functionspace(
        source_mesh,
        element(
            "N1curl", source_mesh.basix_cell(), 2, dtype=default_real_type
        ),
    )
    source = fem.Function(source_space, name="task032_phase5_affine_source")

    def field(x):
        return np.vstack(
            (
                1.0 + 0.25j + 0.02 * x[1] + 0.01 * x[2],
                -0.4 + 0.15j + 0.03 * x[0] - 0.005 * x[2],
                0.2 - 0.1j + 0.01 * x[0],
            )
        )

    source.interpolate(field)
    source.x.scatter_forward()
    interfaces = []
    extracted_fields = []
    for side in ("bottom", "top"):
        interface = build_matched_interface_trace(
            cfg, cross_section, spaces, source_mesh, side
        )
        actual, extraction = extract_tangential_trace(source, interface)
        z_nm = interface.convention.z_nm
        expected = fem.Function(spaces.transverse)
        expected.interpolate(
            lambda x, z=z_nm: np.vstack(
                (
                    1.0 + 0.25j + 0.02 * x[1] + 0.01 * z,
                    -0.4 + 0.15j + 0.03 * x[0] - 0.005 * z,
                )
            )
        )
        expected.x.scatter_forward()
        sample = np.asarray([[2.0 + 0.5j, -3.0 + 0.25j]])
        convention = interface.convention
        normal_opposition_error = float(
            np.linalg.norm(
                convention.n_cross_tangential(sample, domain="local_fem")
                + convention.n_cross_tangential(sample, domain="modal")
            )
        )
        interfaces.append(
            {
                "side": side,
                "z_nm": z_nm,
                "canonical_trace": "(E_x,E_y)",
                "local_fem_outward_normal": list(
                    convention.local_fem_outward_normal
                ),
                "modal_outward_normal": list(convention.modal_outward_normal),
                "middle_adjacent_cell_sign": convention.middle_adjacent_cell_sign,
                "global_interface_facets": interface.global_interface_facet_count,
                "global_middle_adjacent_cells": (
                    interface.global_middle_adjacent_cell_count
                ),
                "global_trace_dofs": interface.global_trace_dofs,
                "global_query_points": extraction.global_query_points,
                "global_source_evaluations": (
                    extraction.global_source_evaluations
                ),
                "unresolved_points": extraction.unresolved_points,
                "relative_trace_coefficient_error": _distributed_relative_error(
                    actual, expected
                ),
                "normal_opposition_error": normal_opposition_error,
                "field_vector_gathered": extraction.field_vector_gathered,
                "coordinate_axis_metadata_gathered": (
                    interface.coordinate_axis_metadata_gathered
                ),
            }
        )
        extracted_fields.append(actual)
    return {
        "source_space": "3D hexahedron N1curl p2",
        "trace_space": "matched 2D quadrilateral N1curl p2",
        "source_global_dofs": int(source_space.dofmap.index_map.size_global),
        "interfaces": interfaces,
        "top_bottom_physical_trace_relative_difference": (
            _distributed_relative_error(extracted_fields[1], extracted_fields[0])
        ),
        "communication_scope": (
            "interface_interpolation_points_and_two_complex_tangential_values_only"
        ),
        "full_3d_field_or_mode_gathered": False,
    }


def _projection_validation(cfg, cross_section, spaces, operators, basis):
    projection = ModalTraceProjection(spaces, basis)
    try:
        coefficients = np.asarray([0.7 + 0.2j, -0.3 + 0.4j])
        round_trip = projection.round_trip(coefficients)
        mass_info = projection.mass.getInfo(PETSc.Mat.InfoType.GLOBAL_SUM)
        constraints = operators.constraints
        return {
            "material_kind": cross_section.material_kind,
            "mode_count": len(projection.right_traces),
            "reconstruction_shape": list(projection.reconstruction_shape),
            "projection_shape": list(projection.projection_shape),
            "small_dense_gram_shape": list(projection.small_dense_shape),
            "gram_condition": projection.gram_condition,
            "expected_coefficients": [
                [float(value.real), float(value.imag)] for value in coefficients
            ],
            "projected_coefficients": [
                [float(value.real), float(value.imag)]
                for value in round_trip.projected_coefficients
            ],
            "coefficient_relative_error": (
                round_trip.coefficient_relative_error
            ),
            "trace_reconstruction_relative_residual": (
                round_trip.trace_relative_residual
            ),
            "trace_mass_nz_used": int(mass_info["nz_used"]),
            "full_vector_gathered": projection.full_vector_gathered,
            "dense_interface_operator_formed": (
                projection.dense_interface_operator_formed
            ),
            "periodic_constraint_source": (
                "Phase3 full vectors reconstructed through distributed T; "
                "collapsed transverse N1curl dofs retain Bloch slave values"
            ),
            "phase_x": [float(constraints.phase_x.real), float(constraints.phase_x.imag)],
            "phase_y": [float(constraints.phase_y.real), float(constraints.phase_y.imag)],
            "constraint_communication_scope": constraints.communication_scope,
            "storage": {
                "distributed_right_trace_bytes": (
                    projection.global_trace_dofs
                    * len(projection.right_traces)
                    * np.dtype(np.complex128).itemsize
                ),
                "distributed_left_trace_bytes": (
                    projection.global_trace_dofs
                    * len(projection.left_traces)
                    * np.dtype(np.complex128).itemsize
                ),
                "replicated_gram_bytes_per_rank": int(projection.gram.nbytes),
                "dense_NGamma_squared_bytes": 0,
            },
        }
    finally:
        projection.destroy()


def _near_degenerate_subspace_validation(cfg) -> dict[str, Any]:
    cross_section, spaces, operators, basis = _build_basis(cfg, "air")
    projection = None
    try:
        projection = ModalTraceProjection(spaces, basis)
        unitary = np.asarray(
            [[1.0, 1.0j], [1.0j, 1.0]], dtype=np.complex128
        ) / np.sqrt(2.0)
        rotated = []
        for column in range(2):
            field = fem.Function(spaces.transverse)
            field.x.array[:] = 0.0
            for row, original in enumerate(projection.right_traces):
                field.x.array[:] += unitary[row, column] * original.x.array
            field.x.scatter_forward()
            rotated.append(field)
        report = trace_subspace_report(
            projection.mass, projection.right_traces, rotated
        )
        return {
            "material_kind": "air",
            "phase3_group_indices": [list(group.indices) for group in basis.groups],
            "comparison": "mass_weighted_trace_subspace",
            "singular_values": list(report.singular_values),
            "max_principal_angle_rad": report.max_principal_angle_rad,
            "projector_error": report.projector_error,
            "first_vector_relative_difference": _distributed_relative_error(
                rotated[0], projection.right_traces[0]
            ),
            "individual_vector_equality_used_as_gate": False,
        }
    finally:
        if projection is not None:
            projection.destroy()
        basis.destroy()
        operators.destroy()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Task32 Phase5 matched Nedelec trace and modal projection validation"
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--verified-clean-sha")
    parser.add_argument("--allow-dirty-research", action="store_true")
    parser.add_argument("--h-nm", type=float, default=10.0)
    parser.add_argument("--container-image", default="myfenics-stage4:task28")
    parser.add_argument(
        "--container-digest",
        default="sha256:08c61b2cde742442b0031437dbc5160db979494587e6b6364f7935beb29dd76d",
    )
    parser.add_argument(
        "--host-environment-id",
        default=os.environ.get("TASK032_HOST_ENVIRONMENT_ID", "SK-20260601OSDE"),
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    comm = MPI.COMM_WORLD
    provenance = _source_provenance(
        comm, args.verified_clean_sha, args.allow_dirty_research
    )
    started = time.perf_counter()
    cfg = target_stage4_config(degree=2, h_nm=args.h_nm)
    cross_section, spaces, operators, stage4_basis = _build_basis(cfg, "stage4_xy")
    try:
        affine_trace = _affine_trace_validation(cfg, cross_section, spaces)
        projection = _projection_validation(
            cfg, cross_section, spaces, operators, stage4_basis
        )
    finally:
        stage4_basis.destroy()
        operators.destroy()
    near_degenerate = _near_degenerate_subspace_validation(cfg)

    interfaces = affine_trace["interfaces"]
    gates = {
        "matched_bottom_top_facets_and_middle_side_cells": all(
            item["global_interface_facets"]
            == item["global_middle_adjacent_cells"]
            > 0
            for item in interfaces
        ),
        "affine_3d_to_2d_trace_error_le_1e-10": all(
            item["relative_trace_coefficient_error"] <= 1.0e-10
            for item in interfaces
        ),
        "all_interface_points_resolved_without_field_gather": all(
            item["unresolved_points"] == 0
            and item["global_query_points"] == item["global_source_evaluations"]
            and item["field_vector_gathered"] is False
            for item in interfaces
        ),
        "top_bottom_local_and_modal_normals_are_opposites": all(
            item["normal_opposition_error"] <= 1.0e-14 for item in interfaces
        ),
        "left_right_modal_round_trip_le_1e-10": (
            projection["coefficient_relative_error"] <= 1.0e-10
            and projection["trace_reconstruction_relative_residual"] <= 1.0e-10
            and projection["gram_condition"] <= 1.0e12
        ),
        "near_degenerate_block_uses_subspace_error": (
            near_degenerate["projector_error"] <= 1.0e-7
            and near_degenerate["max_principal_angle_rad"] <= 1.0e-7
            and near_degenerate["first_vector_relative_difference"] >= 1.0e-2
            and near_degenerate["individual_vector_equality_used_as_gate"] is False
        ),
        "storage_has_no_dense_interface_square_or_full_gather": (
            projection["dense_interface_operator_formed"] is False
            and projection["full_vector_gathered"] is False
            and projection["storage"]["dense_NGamma_squared_bytes"] == 0
            and affine_trace["full_3d_field_or_mode_gathered"] is False
        ),
    }
    signature_payload = {
        "interfaces": interfaces,
        "projection": projection,
        "near_degenerate": near_degenerate,
        "gates": gates,
    }
    local_signature = hashlib.sha256(
        json.dumps(signature_payload, sort_keys=True).encode("utf-8")
    ).hexdigest()
    rank_signatures = comm.gather(local_signature, root=0)
    rank_agreement = comm.bcast(
        len(set(rank_signatures)) == 1 if comm.rank == 0 else None, root=0
    )
    gates["mpi_ranks_agree"] = bool(rank_agreement)
    elapsed = float(comm.allreduce(time.perf_counter() - started, op=MPI.MAX))
    rss = comm.gather(
        {"rank": comm.rank, "historical_peak_rss_mb": _historical_peak_rss_mb()},
        root=0,
    )
    status = "pass" if all(gates.values()) else "fail"
    if comm.rank == 0:
        timestamp = datetime.now(timezone.utc).isoformat()
        record = {
            "schema_version": 1,
            "benchmark_id": "case080_task032_phase5_matched_trace_projection",
            "status": status,
            "timestamp_utc": timestamp,
            "metadata": {
                **provenance,
                "timestamp_utc": timestamp,
                "command": "python -m benchmarks.run_task032_phase5_trace "
                + " ".join(shlex.quote(value) for value in sys.argv[1:]),
                "mpi_size": comm.size,
                "container_image": args.container_image,
                "container_digest": args.container_digest,
                "host_environment_id": args.host_environment_id,
                "scalar_dtype": str(np.dtype(PETSc.ScalarType)),
                "full_field_or_mode_vector_gather": False,
                "provenance": (
                    "clean_task032_phase5_matched_trace_projection"
                    if not provenance["tracked_source_dirty"]
                    else "dirty_task032_phase5_matched_trace_projection_research"
                ),
            },
            "configuration": {
                "h_nm": args.h_nm,
                "degree": 2,
                "bottom_interface_z_nm": 10.0,
                "top_interface_z_nm": 110.0,
                "middle_length_nm": 100.0,
            },
            "affine_trace_validation": affine_trace,
            "stage4_modal_projection": projection,
            "near_degenerate_subspace_validation": near_degenerate,
            "gates": gates,
            "mpi_rank_signatures": rank_signatures,
            "elapsed_seconds_max_rank": elapsed,
            "historical_peak_rss_by_rank": rss,
            "memory_note": (
                "Per-rank process-lifetime peaks are diagnostic only. The Phase5 "
                "storage claim is structural: sparse trace mass, distributed trace "
                "columns, small replicated Gram block, and no dense N_Gamma square."
            ),
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(json.dumps({"status": status, "gates": gates}, indent=2))
    if status != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
