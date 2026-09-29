"""Small algebra and failure tests for the opt-in Gram coordinate change."""

import numpy as np
import pytest
from scipy import sparse

from src.solvers.feinn_scaling import GramDiagonalCoordinates, _synthetic_checks
from src.io.feinn_pilot import ROOT, load_pilot


def test_complex_synthetic_gradient_and_adjoint():
    checks = _synthetic_checks()
    assert checks["A_is_complex_nonhermitian"]
    assert checks["G_is_complex_hermitian_positive"]
    assert checks["roundtrip_relative"] <= 1e-10
    assert checks["AD_adjoint_relative"] <= 1e-10
    assert checks["gradient_relative"] <= 1e-5


def test_original_global_gram_diagonal_without_clipping():
    G = sparse.csr_matrix(np.array([[4, 1j], [-1j, 9]], dtype=np.complex128))
    scale = GramDiagonalCoordinates(G)
    assert np.array_equal(scale.D, [0.5, 1 / 3])
    y = np.array([2 + 1j, -3 + 2j])
    assert np.array_equal(scale.to_c(y), scale.D * y)
    assert np.array_equal(scale.to_y(scale.to_c(y)), y)
    assert np.array_equal(scale.gradient(y), scale.D * y)
    assert scale.normalized_diagonal_relative_max <= 1e-15
    with pytest.raises(ValueError, match="SCALING_DEFINITION_FAILED"):
        GramDiagonalCoordinates(sparse.diags([1, 0], dtype=np.complex128))
    with pytest.raises(ValueError, match="SCALING_DEFINITION_FAILED"):
        GramDiagonalCoordinates(sparse.diags([1 + 1j, 2], dtype=np.complex128))


def test_four_v2_one_run_inputs_keep_original_design():
    folder = ROOT / "input/task042extra_feinn_5nm"
    expected = {
        "v2_state_diagnostic": "ml",
        "v2_scaling_checks": "ml",
        "v2_free_fe_dual_gram_diag": "ml",
        "v2_compare_only": "fe",
    }
    for stem, mode in expected.items():
        spec = load_pilot(folder / (stem + ".dat"))
        assert spec.derived["environment_mode"] == mode
        assert spec.derived["design_sha256"] == "650af0bade61c4ef89583398624b375245691109a6778c168dd46d8c0e70524e"
