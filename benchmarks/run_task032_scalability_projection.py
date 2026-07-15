from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


TIB = 1024**4

# Clean h3/M160 Task032 reference.  These constants are intentionally explicit:
# the projection is an analytical scaling aid, not a PDE run or a fitted solver
# success model.
REFERENCE = {
    "wavelength_nm": 13.5,
    "period_x_nm": 50.0,
    "period_y_nm": 25.0,
    "mesh_target_nm": 3.0,
    "local_thickness_nm": 40.0,
    "local_fe_rows": 68_396,
    "external_auxiliary_rows": 80,
    "local_system_rows": 68_476,
    "qep_full_dofs": 2_053,
    "modes_per_direction": 160,
    "retained_right_left_eigenvector_bytes": 40_929_280,
}


def _ceil(value: float) -> int:
    return int(math.ceil(value))


def build_projection(
    *,
    wavelength_nm: float,
    period_x_nm: float,
    period_y_nm: float,
    local_thickness_nm: float,
    mesh_target_nm: float,
    mode_safety_factor: float,
    mpi_size: int,
) -> dict:
    values = (
        wavelength_nm,
        period_x_nm,
        period_y_nm,
        local_thickness_nm,
        mesh_target_nm,
        mode_safety_factor,
    )
    if any(value <= 0.0 for value in values):
        raise ValueError("All physical inputs and mode_safety_factor must be positive.")
    if mpi_size <= 0:
        raise ValueError("mpi_size must be positive.")

    generic_orders = math.pi * period_x_nm * period_y_nm / wavelength_nm**2
    generic_modes = 2.0 * generic_orders
    retained_modes = _ceil(mode_safety_factor * generic_modes)
    modal_unknowns = 2 * retained_modes

    transverse_scale = (REFERENCE["mesh_target_nm"] / mesh_target_nm) ** 2
    volume_scale = (
        (REFERENCE["mesh_target_nm"] / mesh_target_nm) ** 3
        * local_thickness_nm
        / REFERENCE["local_thickness_nm"]
    )
    qep_dofs = _ceil(REFERENCE["qep_full_dofs"] * transverse_scale)
    local_fe_rows = _ceil(REFERENCE["local_fe_rows"] * volume_scale)
    local_system_rows_proxy = _ceil(REFERENCE["local_system_rows"] * volume_scale)

    complex_bytes = 16
    one_modal_square = modal_unknowns**2 * complex_bytes
    replicated_four_squares_total = one_modal_square * 4 * mpi_size
    all_mode_multi_rhs = (
        local_system_rows_proxy * (modal_unknowns + 1) * complex_bytes
    )
    eigenvector_scale = (
        transverse_scale
        * retained_modes
        / REFERENCE["modes_per_direction"]
    )
    current_layout_eigenvectors = _ceil(
        REFERENCE["retained_right_left_eigenvector_bytes"] * eigenvector_scale
    )
    cumulative_explicit_object_volume = (
        replicated_four_squares_total
        + all_mode_multi_rhs
        + current_layout_eigenvectors
    )
    largest_single_explicit_object = max(
        replicated_four_squares_total,
        all_mode_multi_rhs,
        current_layout_eigenvectors,
    )

    # This diagnostic is deliberately excluded from generic service budgeting.
    y_invariant_two_pol = 4.0 * period_x_nm / wavelength_nm

    return {
        "record_type": "analytical_resource_projection",
        "identity": {
            "is_pde_run": False,
            "is_solver_pass": False,
            "deterministic": True,
            "model_scope": "mechanical_uniform_grid_and_current_layout_scaling",
        },
        "inputs": {
            "wavelength_nm": wavelength_nm,
            "period_x_nm": period_x_nm,
            "period_y_nm": period_y_nm,
            "local_thickness_nm": local_thickness_nm,
            "mesh_target_nm": mesh_target_nm,
            "mode_safety_factor": mode_safety_factor,
            "mpi_size": mpi_size,
        },
        "reference": REFERENCE,
        "generic_2d_modal_estimate": {
            "reciprocal_orders": generic_orders,
            "two_polarization_modes_per_direction_lower_bound": generic_modes,
            "retained_modes_per_direction_after_safety_factor": retained_modes,
            "internal_modal_amplitudes_2m": modal_unknowns,
            "includes_evanescent_buffer_by_physics": False,
        },
        "optional_current_geometry_diagnostic": {
            "y_invariant_two_polarization_modes_per_direction": y_invariant_two_pol,
            "allowed_for_future_service_budget": False,
        },
        "uniform_grid_estimates": {
            "cross_section_qep_full_dofs": qep_dofs,
            "local_fe_rows": local_fe_rows,
            "local_system_rows_mechanical_proxy": local_system_rows_proxy,
            "external_fourier_dtn_auxiliary_count_projected": False,
            "transverse_scale_from_h3": transverse_scale,
            "volume_and_thickness_scale_from_h3": volume_scale,
        },
        "current_explicit_layout_payload": {
            "one_complex_2m_square_bytes": one_modal_square,
            "four_replicated_modal_squares_all_ranks_bytes": (
                replicated_four_squares_total
            ),
            "all_mode_dense_multi_rhs_bytes": all_mode_multi_rhs,
            "retained_right_left_eigenvector_bytes": current_layout_eigenvectors,
            "largest_single_explicit_object_bytes": largest_single_explicit_object,
            "largest_single_explicit_object_tib": (
                largest_single_explicit_object / TIB
            ),
            "cumulative_explicit_object_volume_bytes": (
                cumulative_explicit_object_volume
            ),
            "cumulative_explicit_object_volume_tib": (
                cumulative_explicit_object_volume / TIB
            ),
            "excludes_sparse_matrices_factors_mesh_and_krylov": True,
        },
        "engineering_gates": {
            "current_direct_hybrid_at_target": "not_resource_feasible",
            "one_tib_local_rows_preferred_max": 200_000_000,
            "one_tib_local_rows_candidate_max": 350_000_000,
            "one_tib_local_rows_high_risk_max": 500_000_000,
            "whole_solver_bytes_per_fe_dof_preferred_max": 2_000,
            "whole_solver_bytes_per_fe_dof_exploratory_ceiling": 3_000,
            "required_redesign": [
                "h/p_adaptive_local_fem",
                "matrix_free_low_storage_iterative_local_solver",
                "distributed_streamed_generic_modal_core",
                "no_replicated_dense_m_squared_arrays",
                "no_all_mode_dense_multi_rhs",
            ],
        },
        "limitations": [
            "Mode count is an analytical lower-bound scaling, not a converged M.",
            "Uniform-grid row scaling is not an adaptive-mesh prediction.",
            "The local-system proxy mechanically scales a baseline that includes 80 external auxiliary rows.",
            "Future external Fourier-DtN truncation and auxiliary counts are not projected.",
            "Explicit payload estimates extrapolate the current object layout.",
            "Cumulative object volume is not a simultaneous process-peak estimate.",
            "No material-dispersion, angle, cutoff, convergence, or runtime model is applied.",
        ],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Write a deterministic, non-PDE Task032 resource projection."
    )
    parser.add_argument("--wavelength-nm", type=float, required=True)
    parser.add_argument("--period-x-nm", type=float, default=50.0)
    parser.add_argument("--period-y-nm", type=float, default=25.0)
    parser.add_argument("--local-thickness-nm", type=float, default=20.0)
    parser.add_argument("--mesh-target-nm", type=float, default=0.1)
    parser.add_argument("--mode-safety-factor", type=float, default=3.7)
    parser.add_argument("--mpi-size", type=int, default=4)
    parser.add_argument("--output", type=Path)
    return parser


def main() -> None:
    args = _parser().parse_args()
    record = build_projection(
        wavelength_nm=args.wavelength_nm,
        period_x_nm=args.period_x_nm,
        period_y_nm=args.period_y_nm,
        local_thickness_nm=args.local_thickness_nm,
        mesh_target_nm=args.mesh_target_nm,
        mode_safety_factor=args.mode_safety_factor,
        mpi_size=args.mpi_size,
    )
    payload = json.dumps(record, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(payload, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")


if __name__ == "__main__":
    main()
