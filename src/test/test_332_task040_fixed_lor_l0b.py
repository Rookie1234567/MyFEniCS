"""Task040 L0b focused tests for the fixed local p6 transfer."""

from __future__ import annotations

import basix
import basix.ufl
import numpy as np
import pytest

from src.solvers.hcurl_fixed_lor_transfer import (
    FixedP6LORReferenceTransfer,
    build_fixed_p6_lor_reference_transfer,
)

_N = 6
_N1 = _N + 1
_EDGE_BLOCK = _N * _N1 * _N1
_TINY = np.finfo(np.float64).tiny


@pytest.fixture(scope="module")
def transfer() -> FixedP6LORReferenceTransfer:
    return build_fixed_p6_lor_reference_transfer()


def test_l0b_schema_and_independent_commuting_audit(transfer):
    audit = transfer.audit
    assert audit["schema_version"] == "task040.fixed-lor.l0b.v1"
    assert audit["scope"] == "research_local_only_reference_transfer"
    assert audit["degree"] == 6
    assert audit["subdivision"] == (6, 6, 6)
    for name, array, shape in (
        ("R0", transfer.R0, (343, 343)),
        ("R1", transfer.R1, (882, 882)),
        ("p6_discrete_gradient", transfer.p6_discrete_gradient, (882, 343)),
    ):
        assert array.shape == shape
        assert not array.flags.writeable
        assert np.all(np.isfinite(array))
        assert audit["shapes"][name] == shape
    assert audit["numeric_rank"] == {"R0": 343, "R1": 882, "p6_gradient": 342}
    assert audit["p6_gradient_nullity"] == 1
    assert audit["p6_gradient_condition_status"] == (
        "rank_deficient_by_design_constant_kernel"
    )
    quadrature = audit["quadrature"]
    assert quadrature["primary_degree"] == 8
    assert quadrature["cross_check_degree"] == 10
    assert quadrature["axis_blocks_tabulated_separately"] is True
    assert all(
        np.isfinite(audit["full_rank_condition_estimate"][name])
        for name in ("R0", "R1")
    )
    assert audit["quadrature_defect"]["relative"] <= 1.0e-12

    p6_image = transfer.R1 @ transfer.p6_discrete_gradient
    lor_image = transfer.reference.gradient_incidence @ transfer.R0
    absolute = float(np.linalg.norm(p6_image - lor_image))
    source = float(np.linalg.norm(p6_image))
    output = float(np.linalg.norm(lor_image))
    relative = absolute / max(source, output, _TINY)
    expected = audit["commuting_defect"]
    names = ("absolute", "source_norm", "output_norm", "relative")
    np.testing.assert_allclose(
        (absolute, source, output, relative),
        tuple(expected[name] for name in names),
        rtol=2.0e-13,
        atol=2.0e-14,
    )
    assert relative <= 2.0e-10
    assert audit["checks"]["reference_complex_pass"]
    assert audit["pass"]
    print(
        f"TASK040_L0B ranks={audit['numeric_rank']} "
        f"nullity={audit['p6_gradient_nullity']} q_rel="
        f"{audit['quadrature_defect']['relative']:.3e} "
        f"comm=({absolute:.3e},{source:.3e},{output:.3e},{relative:.3e})"
    )


def test_l0b_constant_fields_follow_edge_axes_and_length(transfer):
    hcurl = basix.ufl.element("N1curl", "hexahedron", _N).basix_element
    interpolation = np.asarray(hcurl.interpolation_matrix, dtype=np.float64)
    points = np.asarray(hcurl.points, dtype=np.float64)
    assert interpolation.shape == (882, 3 * len(points))
    edge_axes = np.asarray(
        ["xyz".index(key[0]) for key in transfer.reference.edge_keys], dtype=np.int64
    )
    assert np.array_equal(edge_axes, np.repeat(np.arange(3), _EDGE_BLOCK))
    assert transfer.audit["quadrature"]["edge_length_factor"] == 1.0 / _N

    for component in range(3):
        values = np.zeros((3, len(points)), dtype=np.float64)
        values[component, :] = 1.0
        coefficients = interpolation @ values.reshape(-1)
        image = transfer.R1 @ coefficients
        same_axis = edge_axes == component
        np.testing.assert_allclose(
            image[same_axis], 1.0 / _N, rtol=5.0e-13, atol=5.0e-13
        )
        np.testing.assert_allclose(image[~same_axis], 0.0, rtol=0.0, atol=5.0e-13)

    scalar = basix.ufl.element(
        "Lagrange",
        "hexahedron",
        _N,
        lagrange_variant=basix.LagrangeVariant.gll_warped,
    ).basix_element
    scalar_points = np.asarray(scalar.points, dtype=np.float64)
    scalar_interpolation = np.asarray(scalar.interpolation_matrix, dtype=np.float64)
    assert scalar_interpolation.shape == (343, len(scalar_points))
    gradient = np.asarray((1.25, -0.75, 0.5), dtype=np.float64)
    scalar_values = 0.37 + scalar_points @ gradient
    coefficients = scalar_interpolation @ scalar_values
    vertex_points = np.asarray(transfer.reference.vertex_keys, dtype=np.float64) / _N
    vertex_values = 0.37 + vertex_points @ gradient
    np.testing.assert_allclose(
        transfer.R0 @ coefficients, vertex_values, rtol=5.0e-13, atol=5.0e-13
    )
    edge_values = gradient[edge_axes] / _N
    np.testing.assert_allclose(
        transfer.R1 @ (transfer.p6_discrete_gradient @ coefficients),
        edge_values,
        rtol=5.0e-13,
        atol=5.0e-13,
    )


def test_l0b_complex_roundtrips_and_adjoint(transfer):
    rng = np.random.default_rng(331040)
    for matrix in (transfer.R0, transfer.R1):
        coefficients = rng.standard_normal(matrix.shape[1]) + 1j * rng.standard_normal(
            matrix.shape[1]
        )
        image = rng.standard_normal(matrix.shape[0]) + 1j * rng.standard_normal(
            matrix.shape[0]
        )

        mapped_coefficients = matrix @ coefficients
        recovered = np.linalg.solve(matrix, mapped_coefficients)
        coefficient_error = np.linalg.norm(recovered - coefficients) / max(
            np.linalg.norm(coefficients), _TINY
        )
        reconstructed = matrix @ np.linalg.solve(matrix, image)
        image_error = np.linalg.norm(reconstructed - image) / max(
            np.linalg.norm(image), _TINY
        )
        assert coefficient_error <= 2.0e-10
        assert image_error <= 2.0e-10

        adjoint_image = matrix.conj().T @ image
        left = np.vdot(mapped_coefficients, image)
        right = np.vdot(coefficients, adjoint_image)
        adjoint_scale = max(
            np.linalg.norm(mapped_coefficients) * np.linalg.norm(image),
            np.linalg.norm(coefficients) * np.linalg.norm(adjoint_image),
            _TINY,
        )
        adjoint_error = abs(left - right) / adjoint_scale
        assert adjoint_error <= 2.0e-11
