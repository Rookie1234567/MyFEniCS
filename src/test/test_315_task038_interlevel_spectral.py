"""Small pure/local tests for the V12 Route-A numerical core."""

from __future__ import annotations

import copy
from types import SimpleNamespace

import numpy as np
import pytest

import src.solvers.fullspace_lor_interlevel_spectral as spectral_core
from src.solvers.fullspace_lor_interlevel_spectral import (
    audit_route_a_spectrum,
    build_route_a_material_class,
    build_route_a_probe_extension,
    build_route_a_probe_extension_from_foundation,
    route_a_spectrum_gate,
    signed_permutation_similarity,
)
from src.solvers.fullspace_lor_transfer import (
    _assemble_lor_matrix,
    _gll_nodes,
    build_local_lor_transfer,
)
from src.test.test_312_task038_lor_hierarchy_capacity import (
    _FakeMatrix,
    _FakeS5Level,
    _fake_local_transfer,
)


def test_optional_coefficients_and_default_matrix_regression() -> None:
    nodes = _gll_nodes(2)
    default = _assemble_lor_matrix(2, nodes, (1.0, 1.0, 1.0))
    qualified_default = build_local_lor_transfer(2).lor_matrix
    np.testing.assert_array_equal(default, qualified_default)
    mass_two = _assemble_lor_matrix(
        2, nodes, (1.0, 1.0, 1.0), mass_coefficient=2.0
    )
    mixed = _assemble_lor_matrix(
        2, nodes, (1.0, 1.0, 1.0), curl_coefficient=2.0, mass_coefficient=3.0
    )
    np.testing.assert_allclose(mixed, default + mass_two)


@pytest.fixture(scope="module")
def local_route_a_result():
    return build_route_a_material_class()


def test_target_p63_direct_spectrum_and_retained_roles(local_route_a_result) -> None:
    result = local_route_a_result
    audit = result.audit
    assert tuple(audit["p63_shape"]) == (882, 144)
    assert tuple(audit["b3_shape"]) == (144, 144)
    assert tuple(audit["b6p_shape"]) == (882, 144)
    assert audit["rank"] == 144
    assert np.isfinite(audit["sigma_min"])
    assert np.isfinite(audit["sigma_max"])
    assert np.isfinite(audit["lambda_min"])
    assert np.isfinite(audit["lambda_max"])
    assert np.isfinite(audit["spectral_condition"])
    assert audit["endpoint_residual_min"] <= 1.0e-10
    assert audit["endpoint_residual_max"] <= 1.0e-10
    assert audit["gate_passed"] is True
    assert audit["gate_failures"] == []
    assert set(result.retained) == {
        "p63", "b3", "b6p", "eigenvector_min", "eigenvector_max",
    }
    assert audit["b6_dense_retained"] is False
    for array in result.retained.values():
        assert array.dtype == np.complex128
        assert array.flags.writeable is False


def _synthetic_gate_facts() -> dict[str, object]:
    return {
        "rank": 144,
        "hermitian_defect_b3": 0.0,
        "hermitian_defect_g63": 0.0,
        "minimum_eigenvalue_b3": 1.0,
        "minimum_eigenvalue_g63": 1.0,
        "lambda_min": 0.2,
        "lambda_max": 2.0,
        "spectral_condition": 10.0,
        "endpoint_residual_min": 0.0,
        "endpoint_residual_max": 0.0,
        "finite": True,
    }


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("rank", 143),
        ("hermitian_defect_b3", 1.1e-12),
        ("hermitian_defect_g63", 1.1e-12),
        ("minimum_eigenvalue_b3", 0.0),
        ("minimum_eigenvalue_g63", 0.0),
        ("lambda_min", 0.09),
        ("lambda_max", 10.1),
        ("spectral_condition", 100.1),
        ("spectral_condition", None),
        ("endpoint_residual_min", 1.1e-10),
        ("endpoint_residual_max", 1.1e-10),
        ("finite", False),
    ),
)
def test_route_a_synthetic_gate_boundaries(field: str, value: object) -> None:
    facts = _synthetic_gate_facts()
    assert route_a_spectrum_gate(facts)["passed"] is True
    mutated = copy.deepcopy(facts)
    mutated[field] = value
    assert route_a_spectrum_gate(mutated)["passed"] is False


def test_signed_permutation_preserves_generalized_endpoints() -> None:
    p63 = np.eye(2, dtype=np.complex128)
    b3 = np.diag([2.0, 3.0]).astype(np.complex128)
    b6p = b3.copy()
    identity = {"class_digest": "synthetic", "material_coefficient_identity": {}, "geometry_jacobian_identity": {}}
    original = audit_route_a_spectrum(p63, b3, b6p, class_identity=identity)
    transformed = signed_permutation_similarity(
        p63, b3, b6p, np.asarray([1, 0]), np.asarray([1.0, -1.0])
    )
    permuted = audit_route_a_spectrum(*transformed, class_identity=identity)
    assert permuted.audit["lambda_min"] == pytest.approx(original.audit["lambda_min"])
    assert permuted.audit["lambda_max"] == pytest.approx(original.audit["lambda_max"])
    assert permuted.audit["spectral_condition"] == pytest.approx(original.audit["spectral_condition"])


def test_level6_level3_probe_extension_owner_work_and_destroy() -> None:
    fine = _FakeS5Level(6, 882, 2, _FakeMatrix("level6"))
    coarse = _FakeS5Level(3, 144, 2, _FakeMatrix("level3"))
    extension = build_route_a_probe_extension(
        fine, coarse, _fake_local_transfer(6, 3)
    )
    assert tuple(extension.audit["levels"]) == (6, 3)
    assert extension.audit["recovery"] is False
    assert extension.audit["p1_built"] is False
    assert extension.audit["smoother_built"] is False
    assert extension.audit["ksp_created"] is False
    source = np.arange(288, dtype=np.float64).astype(np.complex128)
    before = source.copy()
    output = extension.apply_primal(source)
    fine_source = np.arange(1764, dtype=np.float64).astype(np.complex128)
    adjoint = extension.apply_adjoint(fine_source)
    assert output.shape == fine_source.shape
    assert adjoint.shape == source.shape
    assert np.array_equal(source, before)
    from benchmarks.run_task038_full3d_interlevel_spectral import _forbidden_architecture

    case_audit = {
        name: False
        for name in (
            "global_high_order_aij", "global_dense_transfer", "global_numeric_allgather",
            "numeric_allgather", "scalar_node_matrix_built", "global_direct_coarse_built",
            "recovery_field_arrays_built", "p6_exact_edge_factor_built", "hx_hierarchy_built",
            "pcgamg_hierarchy_built", "physical_solve", "recovery", "global_transfer_matrix",
        )
    }
    forbidden = _forbidden_architecture(case_audit, dict(extension.audit))
    assert forbidden and all(value is False for value in forbidden.values())
    lhs = np.vdot(output, fine_source)
    rhs = np.vdot(source, adjoint)
    assert abs(lhs - rhs) / max(abs(rhs), np.finfo(float).tiny) <= 1.0e-12
    extension.destroy()
    extension.destroy()
    assert fine.destroy_count == 0
    assert coarse.destroy_count == 0
    with pytest.raises(RuntimeError, match="destroyed"):
        extension.apply_primal(source)


def test_route_a_probe_extension_from_foundation_owns_only_level3(monkeypatch) -> None:
    calls = []
    foundation_matrix = _FakeMatrix("foundation-low")
    level6 = _FakeS5Level(6, 882, 2, foundation_matrix)
    level6.foundation_owned = True
    level3 = _FakeS5Level(3, 144, 2, _FakeMatrix("level3-owned"))
    fake_transfer = _fake_local_transfer(6, 3)

    monkeypatch.setattr(spectral_core, "_foundation_parent_axes", lambda _: ())
    monkeypatch.setattr(
        spectral_core, "build_local_interlevel_edge_transfer",
        lambda fine, coarse: fake_transfer,
    )
    runtime = __import__(
        "src.solvers.fullspace_lor_memory_hierarchy_runtime",
        fromlist=["_build_level6", "_build_level"],
    )
    monkeypatch.setattr(runtime, "_build_level6", lambda foundation: calls.append(6) or level6)
    monkeypatch.setattr(
        runtime, "_build_level",
        lambda foundation, degree, axes: calls.append(degree) or level3,
    )
    foundation = SimpleNamespace(low_matrix=foundation_matrix)
    extension = build_route_a_probe_extension_from_foundation(foundation)
    assert calls == [6, 3]
    assert extension.audit["owns_level3"] is True
    assert extension.audit["foundation_caller_owned"] is True
    assert extension.audit["p1_built"] is False
    assert extension.audit["smoother_built"] is False
    assert extension.audit["ksp_created"] is False
    extension.destroy()
    extension.destroy()
    assert level3.destroy_count == 1
    assert level6.destroy_count == 1
    assert foundation_matrix.destroy_count == 0
    assert extension.levels == ()
