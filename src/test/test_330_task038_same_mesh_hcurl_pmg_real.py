"""Real small p3/h50 smoke for the same-mesh C1 candidate."""

from __future__ import annotations

import numpy as np
from mpi4py import MPI

from benchmarks.run_task038_full3d_same_mesh_hcurl_pmg import (
    _matrix_facts,
    qualify_one_vcycle,
)
from src.common.config_3d import target_stage4_config
from src.solvers.fullspace_same_mesh_hcurl_pmg_global import (
    audit_small_same_mesh_structure,
    build_small_same_mesh_positive_case,
    destroy_small_same_mesh_positive_case,
)


def test_real_small_same_mesh_structure_and_vcycle():
    cfg = target_stage4_config(degree=3, h_nm=50.0)
    case = build_small_same_mesh_positive_case(
        cfg, MPI.COMM_WORLD, source_name="random"
    )
    try:
        assert case["fine_space"].mesh is case["coarse_space"].mesh
        fine_facts = _matrix_facts(case["fine_matrix"])
        coarse_facts = _matrix_facts(case["coarse_matrix"])
        for facts in (fine_facts, coarse_facts):
            assert facts["rows"] == facts["cols"] > 0
            assert facts["global_nnz"] > 0
            assert facts["finite_diagonal"] is True
            assert facts["positive_diagonal"] is True
            assert np.isfinite(facts["global_nnz"])
        positive = case["coefficient_audit"]["positive_coefficients"]
        assert positive
        assert all(
            np.isfinite(values["mu_inverse"])
            and np.isfinite(values["k0_squared_abs_epsilon"])
            and values["mu_inverse"] > 0.0
            and values["k0_squared_abs_epsilon"] > 0.0
            for values in positive.values()
        )
        structure = audit_small_same_mesh_structure(case)
        assert structure["assembled_form_action_relative"] <= 1.0e-11
        assert structure["global_adjoint_work_relative"] <= 1.0e-11
        assert structure["galerkin_energy_relative"] <= 1.0e-9
        assert structure["full_primal_constraint_residual"] <= 1.0e-11
        assert structure["algebraic_slave_storage_max"] == 0.0
        assert structure["finite"] is True
        assert structure["projected_repeat_relative"] <= 1.0e-13
        assert structure["source_input_unchanged"] is True
        assert structure["projected_finite"] is True
        assert structure["fine_matrix_hermitian"] is True
        assert structure["coarse_matrix_hermitian"] is True
        assert structure["fine_matrix_hermitian_defect"] <= 1.0e-12
        assert structure["coarse_matrix_hermitian_defect"] <= 1.0e-12
        for energy in (structure["coarse_energy"], structure["galerkin_energy"]):
            assert np.isfinite(energy).all()
            assert energy[0] > 0.0
            assert abs(energy[1]) <= 1.0e-11 * max(energy[0], 1.0e-300)

        local = case["local_transfer"].audit
        owner = case["owner_transfer"].audit
        assert tuple(local["pair_fine_to_coarse"]) == (3, 1)
        assert local["full_column_rank"] is True
        assert local["rank"] == local["expected_rank"]
        assert local["fine_lagrange_variant"] == "legendre"
        assert local["coarse_lagrange_variant"] == "legendre"
        assert local["edge_functional_relative"] <= 1.0e-11
        assert local["gradient_commuting_relative"] <= 1.0e-11
        assert local["curl_commuting_relative"] <= 1.0e-11
        assert local["adjoint_work_relative"] <= 1.0e-11
        assert owner["global_transfer_matrix"] is False
        assert owner["numeric_allgather"] is False
        assert owner["phase_application"] == "finalized_floquet_mpc_once"
        assert owner["fine_global_rows"] == fine_facts["rows"]
        assert owner["coarse_global_rows"] == coarse_facts["rows"]

        case["structure_audit"] = structure
        qualification = qualify_one_vcycle(case)
        assert qualification["probe_apply_count"] == 4
        assert qualification["finite"] is True
        assert qualification["input_unchanged"] is True
        assert qualification["each_apply_counts"] is True
        assert qualification["repeat_relative"] <= 1.0e-13
        assert qualification["linearity_relative"] <= 1.0e-12
        assert qualification["p1_relative_residual_max"] <= 1.0e-11
        assert qualification["smoother_apply_total"] == 8
        assert qualification["transfer_3_1_adjoint_total"] == 4
        assert qualification["transfer_3_1_primal_total"] == 4
        assert qualification["p1_solve_total"] == 4
    finally:
        destroy_small_same_mesh_positive_case(case)
        for name in (
            "source",
            "rhs",
            "fine_action",
            "fine_matrix",
            "coarse_matrix",
            "pmg",
        ):
            assert name not in case
