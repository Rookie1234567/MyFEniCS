"""Focused local Route-B nested 6->2->1 transfer and spectrum tests."""

from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pytest

from src.solvers.fullspace_lor_edge_geometric_mg import (
    build_local_lor_edge_geometric_transfer,
)
from src.solvers.fullspace_lor_interlevel_spectral import signed_permutation_similarity
from src.solvers.fullspace_lor_memory_hierarchy import (
    INTERLEVEL_PAIRS,
    _structural_trace_mask,
    audit_local_interlevel_transfer,
    build_local_interlevel_edge_transfer,
)
from src.solvers.fullspace_lor_nested_interlevel import (
    NESTED_CONDITION_LIMIT,
    NESTED_EDGE_SHAPE,
    NESTED_ENERGY_LIMIT,
    NESTED_ENDPOINT_LIMIT,
    NESTED_HERMITIAN_LIMIT,
    NESTED_LAMBDA_MAX_LIMIT,
    NESTED_LAMBDA_MIN_LIMIT,
    NESTED_RANK,
    audit_nested_spectrum,
    build_nested_material_class,
    nested_spectrum_gate,
)


def _nested_facts() -> dict[str, object]:
    return {
        "rank": NESTED_RANK,
        "sigma_min": 1.0,
        "sigma_max": 1.0,
        "hermitian_defect_b2": 0.0,
        "hermitian_defect_g62": 0.0,
        "minimum_eigenvalue_b2": 1.0,
        "minimum_eigenvalue_g62": 1.0,
        "strict_spd_b2": True,
        "strict_spd_g62": True,
        "lambda_min": 1.0,
        "lambda_max": 1.0,
        "spectral_condition": 1.0,
        "endpoint_residual_min": 0.0,
        "endpoint_residual_max": 0.0,
        "nested_energy_relative": 0.0,
        "finite": True,
    }


@pytest.fixture(scope="module")
def local_transfers() -> dict[str, object]:
    """Build each fixed local pair at most once for this test module."""

    return {
        "62": build_local_interlevel_edge_transfer(6, 2),
        "21": build_local_interlevel_edge_transfer(2, 1),
        "63": build_local_interlevel_edge_transfer(6, 3),
        "31": build_local_interlevel_edge_transfer(3, 1),
    }


@pytest.fixture(scope="module")
def nested_result(local_transfers: dict[str, object]):
    return build_nested_material_class(p62=local_transfers["62"].edge_transfer)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("rank", 53),
        ("hermitian_defect_b2", NESTED_HERMITIAN_LIMIT * 1.1),
        ("hermitian_defect_g62", NESTED_HERMITIAN_LIMIT * 1.1),
        ("minimum_eigenvalue_b2", 0.0),
        ("minimum_eigenvalue_g62", 0.0),
        ("lambda_min", NESTED_LAMBDA_MIN_LIMIT - 1.0e-12),
        ("lambda_max", NESTED_LAMBDA_MAX_LIMIT + 1.0e-12),
        ("spectral_condition", NESTED_CONDITION_LIMIT + 1.0e-12),
        ("spectral_condition", None),
        ("endpoint_residual_min", NESTED_ENDPOINT_LIMIT * 1.1),
        ("endpoint_residual_max", NESTED_ENDPOINT_LIMIT * 1.1),
        ("nested_energy_relative", NESTED_ENERGY_LIMIT * 1.1),
        ("finite", False),
    ),
)
def test_nested_spectrum_gate_boundaries(field: str, value: object) -> None:
    facts = _nested_facts()
    assert nested_spectrum_gate(facts)["passed"] is True
    facts[field] = value
    assert nested_spectrum_gate(facts)["passed"] is False


def test_nested_module_is_local_and_fixed() -> None:
    path = Path(__file__).parents[1] / "solvers" / "fullspace_lor_nested_interlevel.py"
    source = path.read_text(encoding="utf-8").lower()
    assert "mpi4py" not in source
    assert "petsc4py" not in source
    assert "dolfinx" not in source
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name not in {"mpi4py", "petsc4py", "dolfinx"} for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.module not in {"mpi4py", "petsc4py", "dolfinx"}


def test_new_pair_contract_is_explicit() -> None:
    assert INTERLEVEL_PAIRS == ((6, 3), (3, 1), (6, 2), (2, 1))
    with pytest.raises(ValueError):
        build_local_interlevel_edge_transfer(6, 1)


def test_nested_local_transfer_and_unit_spectrum_target(
    local_transfers: dict[str, object], nested_result: object
) -> None:
    transfer62 = local_transfers["62"]
    transfer21 = local_transfers["21"]
    transfer63 = local_transfers["63"]
    transfer31 = local_transfers["31"]

    assert transfer62.edge_shape == (882, 54)
    assert transfer62.node_transfer.shape == (343, 27)
    assert transfer21.edge_shape == (54, 12)
    assert transfer21.node_transfer.shape == (27, 8)
    assert transfer63.edge_shape == (882, 144)
    assert transfer31.edge_shape == (144, 12)
    assert transfer62.audit["gll_subset_exact"] is True
    assert transfer62.audit["coarse_gll_subset_indices"] == [0, 3, 6]
    assert transfer62.audit["coarse_gll_subset_coordinate_identity"] == transfer62.audit[
        "fine_gll_subset_coordinate_identity"
    ]
    assert transfer62.audit["nested_tiled_geometric"] is True
    assert transfer62.audit["generic_high_polynomial_reconstruction"] is False
    assert transfer62.audit["deterministic_owner_policy"] == (
        "fine_edge_half_open_parent_cell"
    )
    assert transfer62.audit["shared_consistency"] is True
    assert transfer62.audit["edge_nnz"] == 2178
    assert transfer62.audit["node_nnz"] == 1331
    assert transfer62.audit["p62_p21_composition_relative"] <= 1.0e-11
    for transfer in (transfer62, transfer21, transfer63, transfer31):
        assert transfer.audit["edge_line_integral_relative"] <= 1.0e-11
        assert transfer.audit["curl_flux_relative"] <= 1.0e-11
        assert transfer.audit["gradient_commuting_relative"] <= 1.0e-11
        assert transfer.audit["adjoint_work_relative"] <= 1.0e-12
        assert transfer.audit["linearity_relative"] <= 1.0e-12
        assert transfer.audit["repeat_relative"] <= 1.0e-13
        assert transfer.audit["input_unchanged"] is True
        assert transfer.audit["finite"] is True
        assert transfer.edge_transfer.dtype == np.complex128
        assert transfer.node_transfer.dtype == np.complex128
        assert transfer.edge_transfer.flags.writeable is False
        assert transfer.node_transfer.flags.writeable is False

    authority21 = build_local_lor_edge_geometric_transfer(2)
    columns = np.argsort(authority21.coarse_basix_to_lor_order)
    authority_edge = np.asarray(authority21.edge_transfer[:, columns], dtype=np.complex128).copy()
    authority_edge[~_structural_trace_mask(2, 1)] = 0.0
    np.testing.assert_array_equal(
        transfer21.edge_transfer, authority_edge
    )
    bad = transfer62.edge_transfer.copy()
    forbidden_row, forbidden_column = np.argwhere(
        ~_structural_trace_mask(6, 2)
    )[0]
    bad[forbidden_row, forbidden_column] = 0.125 + 0.25j
    with pytest.raises(ValueError):
        audit_local_interlevel_transfer(6, 2, bad, transfer62.node_transfer)

    result = nested_result
    assert result.audit["method"] == "lor_edge_geometric_mg_6_2_1_nested_v1"
    assert result.audit["gate_passed"] is True
    assert result.audit["gate_failures"] == []
    assert result.audit["rank"] == 54
    assert result.audit["nested_energy_relative"] <= NESTED_ENERGY_LIMIT
    assert set(result.retained) == {
        "p62", "b2", "b6p", "eigenvector_min", "eigenvector_max",
    }
    assert result.audit["b6_dense_audit_only"] is True
    assert result.audit["b6_dense_retained"] is False
    assert result.audit["g62_dense_audit_only"] is True
    assert result.audit["g62_dense_retained"] is False
    for array in result.retained.values():
        assert array.dtype == np.complex128
        assert array.flags.writeable is False


def test_nested_signed_permutation_preserves_spectrum_and_energy(
    local_transfers: dict[str, object], nested_result: object
) -> None:
    transfer62 = local_transfers["62"]
    original = nested_result
    permutation = np.arange(NESTED_RANK - 1, -1, -1)
    signs = np.where(np.arange(NESTED_RANK) % 2, -1.0, 1.0).astype(np.complex128)
    p62, b2, b6p = signed_permutation_similarity(
        original.retained["p62"],
        original.retained["b2"],
        original.retained["b6p"],
        permutation,
        signs,
    )
    transformed = audit_nested_spectrum(
        p62,
        b2,
        b6p,
        class_identity={
            "class_digest": original.audit["class_digest"],
            "material_coefficient_identity": original.audit[
                "material_coefficient_identity"
            ],
            "geometry_jacobian_identity": original.audit[
                "geometry_jacobian_identity"
            ],
        },
    )
    np.testing.assert_allclose(
        transformed.audit["lambda_min"], original.audit["lambda_min"], rtol=1.0e-12
    )
    np.testing.assert_allclose(
        transformed.audit["lambda_max"], original.audit["lambda_max"], rtol=1.0e-12
    )
    np.testing.assert_allclose(
        transformed.audit["nested_energy_relative"],
        original.audit["nested_energy_relative"],
        rtol=1.0e-12,
    )
