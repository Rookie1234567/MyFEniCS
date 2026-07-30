from __future__ import annotations

import numpy as np
import pytest

from benchmarks.task033_reduced_equal_accuracy import (
    ReducedEqualAccuracyError,
    _execution_contract,
    _factor_inventory_nnz,
    classify_resource_reduction,
    compare_full3d_to_reference,
    hybrid_dimension_costs,
)


@pytest.mark.parametrize(
    ("ratio", "expected"),
    [
        (1.0, "weak"),
        (1.299999, "weak"),
        (1.3, "useful_positive"),
        (2.0, "clear_success"),
        (3.0, "engineering_target"),
    ],
)
def test_review_v5_resource_reduction_boundaries(ratio: float, expected: str) -> None:
    assert classify_resource_reduction(ratio) == expected


def test_factor_inventory_prefers_corrected_mumps_count() -> None:
    assert (
        _factor_inventory_nnz(
            {
                "factor_nnz_corrected": 2_277_000_000,
                "matrix_stats": {
                    "matrix_nnz_used": -2_017_967_296.0,
                },
            },
            label="fixture",
        )
        == 2_277_000_000
    )


def _full3d(scale: float) -> dict:
    coordinates = {
        "x_nm": np.array([0.0, 1.0]),
        "y_nm": np.array([0.0]),
        "z_nm": np.array([10.0, 30.0]),
        "interface_z_nm": np.array([10.0, 30.0]),
    }
    arrays = {
        **coordinates,
        "E_V_per_m": np.full((2, 1, 2, 3), scale, dtype=np.complex128),
        "H_A_per_m": np.full((2, 1, 2, 3), 2.0 * scale, dtype=np.complex128),
        "E_t_interface_V_per_m": np.full(
            (2, 1, 2, 2), scale, dtype=np.complex128
        ),
        "H_t_interface_A_per_m": np.full(
            (2, 1, 2, 2), 2.0 * scale, dtype=np.complex128
        ),
    }
    order = {
        "power_ratio": 0.2 * scale,
        "outgoing_amplitude_at_boundary": [scale, 0.0],
    }
    return {
        "arrays": arrays,
        "orders": {("top", 0, 0, "s"): order},
        "descriptor": {
            "results": {
                "R_total": 0.1 * scale,
                "T_total": 0.2 * scale,
                "A_balance": 1.0 - 0.3 * scale,
                "A_volume_total": 1.0 - 0.3 * scale,
                "linear_system_true_relative_residual": 1.0e-12,
            }
        },
    }


def test_direct_comparison_computes_planes_interfaces_orders_and_scalars() -> None:
    result = compare_full3d_to_reference(_full3d(1.0), _full3d(1.1))
    assert result["selected_planes"]["max_electric_relative_l2"] == pytest.approx(0.1)
    assert result["selected_planes"]["max_magnetic_relative_l2"] == pytest.approx(0.1)
    assert result["interfaces"]["max_electric_tangential_relative_l2"] == pytest.approx(
        0.1
    )
    assert result["scalar_observables"]["R_total"]["absolute_error"] == pytest.approx(
        0.01
    )
    assert result["diffraction_orders"]["significant_order_count"] == 1
    assert result["full_true_relative_residual"] == pytest.approx(1.0e-12)


def test_direct_comparison_rejects_different_sample_coordinates() -> None:
    reference = _full3d(1.0)
    candidate = _full3d(1.0)
    candidate["arrays"]["x_nm"] = np.array([0.0, 2.0])
    with pytest.raises(ReducedEqualAccuracyError, match="sample coordinates differ"):
        compare_full3d_to_reference(reference, candidate)


def test_hybrid_dimension_costs_distinguish_fe_auxiliary_and_modal_rows() -> None:
    modern = hybrid_dimension_costs(
        {
            "bottom_global_size": 13339,
            "top_global_size": 13339,
            "bottom_local_fe_dofs": 13299,
            "top_local_fe_dofs": 13299,
            "internal_unknown_count": 320,
        },
        validation={},
    )
    assert modern == {
        "local_fe_dofs": 26598,
        "local_system_rows": 26678,
        "total_rows": 26998,
    }

    legacy = hybrid_dimension_costs(
        {
            "bottom_global_size": 34238,
            "top_global_size": 34238,
            "internal_unknown_count": 320,
        },
        validation={
            "external_auxiliary_amplitudes": {
                "bottom": [[0.0, 0.0]] * 40,
                "top": [[0.0, 0.0]] * 40,
            }
        },
    )
    assert legacy == {
        "local_fe_dofs": 68396,
        "local_system_rows": 68476,
        "total_rows": 68796,
    }


def test_cross_record_execution_contract_freezes_resource_semantics() -> None:
    common = {
        "container_image": "frozen:image",
        "container_digest": "sha256:" + "a" * 64,
        "mpi_size": 4,
        "solver_path": "modal-schur-memory-minimal",
        "no_swap": True,
        "memory_authority_semantics": (
            "max(simultaneous live MPI worker RSS sum, "
            "container cgroup current)"
        ),
    }
    direct = {
        "container_image": common["container_image"],
        "container_digest": common["container_digest"],
        "mpi_size": 4,
        "solver_path": "direct_lu_mumps",
        "no_swap": True,
    }
    hybrid = {
        key: {
            "execution": {
                **common,
                "source_commit_sha": (
                    "2" * 40 if "h7p5" in key else "1" * 40
                ),
            },
            "source_commit_sha": (
                "2" * 40 if "h7p5" in key else "1" * 40
            ),
        }
        for key in (
            "p3_h10_m120",
            "p3_h10_m160",
            "p3_h7p5_m120",
            "p3_h7p5_m160",
        )
    }
    result = _execution_contract(
        full3d={
            "candidate_p3_h10": {"execution": direct},
            "candidate_p3_h7p5": {"execution": direct},
        },
        hybrid=hybrid,
        p2_hybrid={
            "execution": {
                **common,
                "source_commit_sha": "0" * 40,
            },
            "source_commit_sha": "0" * 40,
        },
    )
    assert result["mpi_size"] == 4
    assert result["zero_swap_required_and_observed"]
    assert result["one_heavy_case_at_a_time"]
    assert result["clean_source_identity"]["sources_intentionally_different"]
    assert "indicative measured comparison" in result["wall_time_semantics"]


def test_cross_record_execution_contract_fails_closed_on_mixed_image() -> None:
    direct = {
        "container_image": "frozen:image",
        "container_digest": "sha256:" + "a" * 64,
        "mpi_size": 4,
        "solver_path": "direct_lu_mumps",
        "no_swap": True,
    }
    common_hybrid = {
        "container_image": "frozen:image",
        "container_digest": "sha256:" + "a" * 64,
        "mpi_size": 4,
        "solver_path": "modal-schur-memory-minimal",
        "no_swap": True,
    }
    hybrid = {
        key: {
            "execution": {
                **common_hybrid,
                "source_commit_sha": "2" * 40,
            },
            "source_commit_sha": "2" * 40,
        }
        for key in (
            "p3_h10_m120",
            "p3_h10_m160",
            "p3_h7p5_m120",
            "p3_h7p5_m160",
        )
    }
    hybrid["p3_h7p5_m160"]["execution"]["container_image"] = "wrong:image"
    with pytest.raises(
        ReducedEqualAccuracyError,
        match="single_frozen_container_image",
    ):
        _execution_contract(
            full3d={
                "candidate_p3_h10": {"execution": direct},
                "candidate_p3_h7p5": {"execution": direct},
            },
            hybrid=hybrid,
            p2_hybrid={
                "execution": {
                    **common_hybrid,
                    "source_commit_sha": "0" * 40,
                },
                "source_commit_sha": "0" * 40,
            },
        )
