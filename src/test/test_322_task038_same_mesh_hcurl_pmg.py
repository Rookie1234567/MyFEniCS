"""Focused local C1 same-mesh N1E transfer tests."""

from __future__ import annotations

import ast
from pathlib import Path

import basix
import numpy as np
import pytest
from basix.ufl import element as ufl_element

from src.solvers.fullspace_same_mesh_hcurl_pmg import (
    MATERIAL_ENERGY_LIMIT,
    MATERIAL_HERMITIAN_LIMIT,
    SAME_MESH_TRANSFER_PAIRS,
    build_same_mesh_hcurl_transfer,
    build_same_mesh_material_class,
    same_mesh_material_gate,
    same_mesh_transfer_gate,
)


@pytest.fixture(scope="module")
def transfers() -> dict[tuple[int, int], object]:
    return {
        pair: build_same_mesh_hcurl_transfer(*pair)
        for pair in ((3, 1), (6, 3))
    }


def test_c1_module_is_local_and_does_not_import_failed_task030_pc() -> None:
    path = Path(__file__).parents[1] / "solvers" / "fullspace_same_mesh_hcurl_pmg.py"
    source = path.read_text(encoding="utf-8")
    assert "mpi4py" not in source
    assert "petsc4py" not in source
    assert "dolfinx" not in source
    assert "GalerkinMultilevelPc" not in source
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name not in {"mpi4py", "petsc4py", "dolfinx"} for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.module not in {"mpi4py", "petsc4py", "dolfinx"}


def test_fixed_pairs_and_basix_metadata_are_explicit(transfers: dict[tuple[int, int], object]) -> None:
    assert SAME_MESH_TRANSFER_PAIRS == ((3, 1), (6, 3))
    for pair, transfer in transfers.items():
        fine, coarse = pair
        assert transfer.audit["pair_fine_to_coarse"] == [fine, coarse]
        assert transfer.audit["shape"] == list(transfer.matrix.shape)
        assert transfer.audit["map_type"] == "covariantPiola"
        assert transfer.audit["fine_lagrange_variant"] == "legendre"
        assert transfer.audit["coarse_lagrange_variant"] == "legendre"
        assert transfer.audit["basix_interpolation"] is True
        assert transfer.audit["dof_functional_independent_audit"] is True
        assert transfer.audit["gate_passed"] is True
        assert transfer.audit["gate_failures"] == []
        assert transfer.audit["rank"] == transfer.audit["expected_rank"]
        assert transfer.audit["full_column_rank"] is True
        for name, limit in (
            ("edge_functional_relative", 1.0e-11),
            ("gradient_commuting_relative", 1.0e-11),
            ("curl_commuting_relative", 1.0e-11),
            ("adjoint_work_relative", 1.0e-11),
            ("linearity_relative", 1.0e-12),
            ("repeat_relative", 1.0e-13),
        ):
            assert transfer.audit[name] <= limit
        assert transfer.matrix.dtype == np.complex128
        assert transfer.matrix.flags.writeable is False
        fine_element = ufl_element(
            "N1curl", "hexahedron", fine, dtype=np.float64
        ).basix_element
        coarse_element = ufl_element(
            "N1curl", "hexahedron", coarse, dtype=np.float64
        ).basix_element
        assert transfer.audit["fine_lagrange_variant"] == (
            fine_element.lagrange_variant.name
        )
        assert transfer.audit["coarse_lagrange_variant"] == (
            coarse_element.lagrange_variant.name
        )
        np.testing.assert_allclose(
            transfer.matrix,
            basix.compute_interpolation_operator(coarse_element, fine_element),
            rtol=0.0,
            atol=0.0,
        )


def test_apply_adjoint_batch_and_input_contract(transfers: dict[tuple[int, int], object]) -> None:
    for transfer in transfers.values():
        coarse_size = transfer.matrix.shape[1]
        fine_size = transfer.matrix.shape[0]
        first = np.arange(1, coarse_size + 1, dtype=np.float64).astype(np.complex128)
        first += 0.25j
        second = np.arange(2, coarse_size + 2, dtype=np.float64).astype(np.complex128)
        second -= 0.5j
        before = first.copy()
        alpha = 0.75 - 0.25j
        beta = -0.5 + 0.5j
        direct = transfer.apply(first)
        repeated = transfer.apply(first)
        combo = transfer.apply(alpha * first + beta * second)
        expected = alpha * direct + beta * transfer.apply(second)
        fine = np.arange(1, fine_size + 1, dtype=np.float64).astype(np.complex128)
        fine += 0.125j
        lhs = np.vdot(direct, fine)
        rhs = np.vdot(first, transfer.apply_adjoint(fine))
        assert np.array_equal(first, before)
        assert np.all(np.isfinite(direct))
        assert np.array_equal(direct, repeated)
        assert np.linalg.norm(combo - expected) <= 1.0e-12 * max(np.linalg.norm(expected), 1.0)
        assert abs(lhs - rhs) <= 1.0e-11 * max(abs(rhs), 1.0)
        batch = transfer.apply_many(np.vstack((first, second)))
        np.testing.assert_array_equal(batch[0], direct)
        np.testing.assert_allclose(
            transfer.apply_adjoint_many(batch)[0],
            transfer.matrix.conj().T @ direct,
            rtol=0.0,
            atol=0.0,
        )


def test_nontrivial_basix_hexa_orientation_is_not_identity() -> None:
    identity = build_same_mesh_hcurl_transfer(3, 1)
    oriented = build_same_mesh_hcurl_transfer(3, 1, coarse_cell_info=1, fine_cell_info=1)
    assert oriented.audit["fine_element"]["dof_transformations_are_identity"] is False
    assert oriented.audit["orientation_transform"] == "basix_FiniteElement_T_apply"
    assert oriented.audit["fine_orientation_relative_identity"] > 0.0
    assert identity.audit["fine_orientation_relative_identity"] == 0.0
    np.testing.assert_allclose(
        np.linalg.svd(identity.matrix, compute_uv=False),
        np.linalg.svd(oriented.matrix, compute_uv=False),
        rtol=1.0e-12,
        atol=1.0e-13,
    )
    assert same_mesh_transfer_gate(dict(oriented.audit))["passed"] is True
    material = build_same_mesh_material_class(
        oriented,
        class_name="air_tag_1",
        material_role="air",
        widths=(1.0, 1.1, 0.9),
        curl_coefficient=1.0,
        mass_coefficient=0.2166168318483261,
    )
    assert material.audit["gate_passed"] is True
    assert material.audit["strict_spd_coarse"] is True
    assert material.audit["strict_spd_galerkin"] is True
    assert material.audit["hermitian_defect_coarse"] <= MATERIAL_HERMITIAN_LIMIT
    assert material.audit["hermitian_defect_galerkin"] <= MATERIAL_HERMITIAN_LIMIT
    assert material.audit["rediscretized_energy_relative"] <= MATERIAL_ENERGY_LIMIT


def test_three_positive_material_roles_and_energy(transfers: dict[tuple[int, int], object]) -> None:
    material_coefficients = {
        "air": (1.0, 0.2166168318483261),
        "grating": (1.0, 0.2161855349974538),
        "substrate": (1.0, 0.2161855349974538),
    }
    for transfer in transfers.values():
        for role, (curl_coefficient, mass_coefficient) in material_coefficients.items():
            result = build_same_mesh_material_class(
                transfer,
                class_name=f"{role}_local",
                material_role=role,
                widths=(1.0, 1.1, 0.9),
                curl_coefficient=curl_coefficient,
                mass_coefficient=mass_coefficient,
            )
            assert result.audit["gate_passed"] is True
            assert result.audit["gate_failures"] == []
            assert result.audit["galerkin_matrix_relative"] <= MATERIAL_ENERGY_LIMIT
            assert result.audit["rediscretized_energy_relative"] <= MATERIAL_ENERGY_LIMIT
            assert result.audit["hermitian_defect_coarse"] <= MATERIAL_HERMITIAN_LIMIT
            assert result.audit["hermitian_defect_galerkin"] <= MATERIAL_HERMITIAN_LIMIT
            assert result.audit["minimum_eigenvalue_coarse"] > 0.0
            assert result.audit["minimum_eigenvalue_galerkin"] > 0.0
            assert set(result.retained) == {"transfer", "coarse_matrix", "galerkin_matrix"}
            for array in result.retained.values():
                assert array.dtype == np.complex128
                assert array.flags.writeable is False


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("rank", 1),
        ("full_column_rank", False),
        ("gradient_commuting_relative", 1.0e-11 * 1.01),
        ("curl_commuting_relative", 1.0e-11 * 1.01),
        ("adjoint_work_relative", 1.0e-11 * 1.01),
        ("finite", False),
        ("edge_functional_relative", None),
    ),
)
def test_transfer_gate_rejects_boundary_or_missing_fact(field: str, value: object) -> None:
    facts = {
        "rank": 12,
        "expected_rank": 12,
        "full_column_rank": True,
        "edge_functional_relative": 0.0,
        "gradient_commuting_relative": 0.0,
        "curl_commuting_relative": 0.0,
        "adjoint_work_relative": 0.0,
        "linearity_relative": 0.0,
        "repeat_relative": 0.0,
        "input_unchanged": True,
        "finite": True,
    }
    assert same_mesh_transfer_gate(facts)["passed"] is True
    facts[field] = value
    assert same_mesh_transfer_gate(facts)["passed"] is False


def test_material_gate_rejects_algebraic_boundaries() -> None:
    facts = {
        "hermitian_defect_coarse": 0.0,
        "hermitian_defect_galerkin": 0.0,
        "minimum_eigenvalue_coarse": 1.0,
        "minimum_eigenvalue_galerkin": 1.0,
        "strict_spd_coarse": True,
        "strict_spd_galerkin": True,
        "galerkin_matrix_relative": 0.0,
        "rediscretized_energy_relative": 0.0,
        "finite": True,
    }
    assert same_mesh_material_gate(facts)["passed"] is True
    for field, value in (
        ("hermitian_defect_galerkin", MATERIAL_HERMITIAN_LIMIT * 1.1),
        ("minimum_eigenvalue_galerkin", 0.0),
        ("strict_spd_galerkin", False),
        ("galerkin_matrix_relative", MATERIAL_ENERGY_LIMIT * 1.1),
        ("rediscretized_energy_relative", MATERIAL_ENERGY_LIMIT * 1.1),
        ("strict_spd_coarse", False),
        ("finite", False),
    ):
        mutated = dict(facts)
        mutated[field] = value
        assert same_mesh_material_gate(mutated)["passed"] is False
