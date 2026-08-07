from __future__ import annotations

import basix
import numpy as np
import pytest
import scipy.sparse as sp

from src.solvers.hcurl_affine_isotropic_tensor import (
    AffineIsotropicMaxwellTensorFactory,
    AffineIsotropicMaxwellTensorSpec,
)
from src.solvers.static_lor_hcurl_proxy import build_shifted_lor_proxy
from src.solvers.static_lor_hcurl_transfer import (
    build_affine_lor_parent_topology,
    build_lor_slab_edge_space,
)
from src.test.test_259_task037_extra_lor_slab_edges import (
    _empty_floquet,
    _parent_vertices,
    _synthetic_floquet,
    _topology,
)


_TOLERANCE = 1.0e-12


def _spec() -> AffineIsotropicMaxwellTensorSpec:
    return AffineIsotropicMaxwellTensorSpec(
        curl_coefficient=1.25 + 0.15j,
        mass_coefficient_by_tag={3: 0.75 - 0.2j},
    )


def _factory(spec: AffineIsotropicMaxwellTensorSpec):
    element = basix.ufl.element(
        "N1curl",
        "hexahedron",
        1,
    ).basix_element
    return AffineIsotropicMaxwellTensorFactory(element, spec)


def _child_widths(topology, cell_index: int) -> tuple[float, float, float]:
    points = topology.vertices[topology.cells[cell_index]]
    return tuple(float(value) for value in np.ptp(points, axis=0))


def _independent_base_matrix(topologies, edge_space, spec):
    factory = _factory(spec)
    active_count = len(edge_space.active_edge_keys)
    rows = []
    columns = []
    values = []
    for parent_index, topology in enumerate(topologies):
        expansion = edge_space._parent_expansions[parent_index]
        for cell_index in range(len(topology.cells)):
            local_columns = []
            local_coefficients = []
            for edge_id_value, orientation_value in zip(
                topology.cell_edge_ids[cell_index],
                topology.cell_edge_orientations[cell_index],
                strict=True,
            ):
                edge_id = int(edge_id_value)
                start = int(expansion.indptr[edge_id])
                end = int(expansion.indptr[edge_id + 1])
                assert end - start == 1
                local_columns.append(int(expansion.indices[start]))
                local_coefficients.append(
                    complex(expansion.data[start]) * int(orientation_value)
                )
            local_coefficients = np.asarray(
                local_coefficients,
                dtype=np.complex128,
            )
            tensor = factory.tensor(
                tag=topology.material_tag,
                widths=_child_widths(topology, cell_index),
            )
            for local_row, row in enumerate(local_columns):
                for local_column, column in enumerate(local_columns):
                    rows.append(row)
                    columns.append(column)
                    values.append(
                        np.conjugate(local_coefficients[local_row])
                        * tensor[local_row, local_column]
                        * local_coefficients[local_column]
                    )
    return sp.csr_matrix(
        (values, (rows, columns)),
        shape=(active_count, active_count),
        dtype=np.complex128,
    )


def _shifted_reference(base: sp.csr_matrix) -> sp.csr_matrix:
    expected = base.copy()
    diagonal = np.asarray(expected.diagonal(), dtype=np.complex128)
    scale = float(np.max(np.abs(diagonal)))
    shift = -1j * 0.1 * np.maximum(np.abs(diagonal), 1.0e-12 * scale)
    expected.setdiag(diagonal + shift)
    expected.sum_duplicates()
    expected.sort_indices()
    expected.eliminate_zeros()
    return expected


def _relative_sparse(observed: sp.spmatrix, expected: sp.spmatrix) -> float:
    difference = (observed - expected).tocsr()
    return float(
        np.linalg.norm(difference.data)
        / max(float(np.linalg.norm(expected.data)), np.finfo(float).tiny)
    )


def _assert_same_csr(first: sp.csr_matrix, second: sp.csr_matrix) -> None:
    assert np.array_equal(first.indptr, second.indptr)
    assert np.array_equal(first.indices, second.indices)
    assert np.array_equal(first.data, second.data)


@pytest.mark.parametrize("degree", (2, 3))
@pytest.mark.parametrize("two_parents", (False, True))
def test_direct_child_action_matches_independent_sum_and_shift(
    degree: int,
    two_parents: bool,
):
    left = _topology(degree, 10)
    topologies = [left]
    if two_parents:
        topologies.append(_topology(degree, 2, (1.0, 0.0, 0.0)))
    edge_space = build_lor_slab_edge_space(
        topologies,
        _empty_floquet(degree),
        phase_x=1.0 + 0.0j,
        phase_y=1.0 + 0.0j,
    )
    spec = _spec()
    proxy = build_shifted_lor_proxy(topologies, edge_space, spec)
    base = _independent_base_matrix(
        sorted(topologies, key=lambda topology: topology.canonical_cell_id),
        edge_space,
        spec,
    )
    expected = _shifted_reference(base)
    assert _relative_sparse(proxy.matrix, expected) <= _TOLERANCE
    rng = np.random.default_rng(2640 + degree + int(two_parents))
    values = rng.normal(size=expected.shape[1]) + 1j * rng.normal(
        size=expected.shape[1]
    )
    assert np.allclose(proxy.apply(values), expected @ values, rtol=0.0, atol=1.0e-12)
    assert proxy.audit["direct_child_cell"] is True
    assert proxy.audit["literal_p6_galerkin"] is False
    assert proxy.audit["factor_count"] == 0
    assert proxy.audit["global_dense"] is False
    assert proxy.audit["global_A"] is False
    assert proxy.audit["global_F"] is False
    assert proxy.audit["shift_fraction"] == 0.1
    assert proxy.audit["shift_floor_relative"] == 1.0e-12


@pytest.mark.parametrize("degree", (2, 3))
def test_periodic_phase_is_included_and_repeated_proxy_is_deterministic(degree):
    topology = _topology(degree, 7)
    phase_x = np.exp(0.23j)
    phase_y = np.exp(-0.41j)
    edge_space = build_lor_slab_edge_space(
        [topology],
        _synthetic_floquet(degree),
        phase_x=phase_x,
        phase_y=phase_y,
    )
    spec = _spec()
    first = build_shifted_lor_proxy([topology], edge_space, spec)
    second = build_shifted_lor_proxy([topology], edge_space, spec)
    expected = _shifted_reference(
        _independent_base_matrix([topology], edge_space, spec)
    )
    assert _relative_sparse(first.matrix, expected) <= _TOLERANCE
    _assert_same_csr(first.matrix, second.matrix)
    assert first.audit["matrix_fingerprint"] == second.audit["matrix_fingerprint"]
    assert first.audit["shift_sha256"] == second.audit["shift_sha256"]
    assert np.any(np.abs(edge_space._parent_expansions[0].data.imag) > 1.0e-12)
    assert first.matrix.data.flags.writeable is False
    assert first.matrix.indices.flags.writeable is False
    assert first.matrix.indptr.flags.writeable is False


@pytest.mark.parametrize("degree", (2, 3))
def test_reoriented_axis_aligned_parent_uses_edge_orientation(degree):
    reference = basix.geometry(basix.CellType.hexahedron)
    axes = np.asarray(
        ((-1.0, 0.0, 0.0), (0.0, -1.0, 0.0), (0.0, 0.0, 1.0))
    )
    vertices = np.asarray((2.0, 3.0, 4.0)) + reference @ axes.T
    topology = build_affine_lor_parent_topology(
        vertices,
        degree=degree,
        canonical_cell_id=4,
        material_tag=3,
        cell_permutation=0,
        coordinate_tolerance=_TOLERANCE,
    )
    assert np.any(topology.cell_edge_orientations == -1)
    edge_space = build_lor_slab_edge_space(
        [topology],
        _empty_floquet(degree),
        phase_x=1.0 + 0.0j,
        phase_y=1.0 + 0.0j,
    )
    spec = _spec()
    proxy = build_shifted_lor_proxy([topology], edge_space, spec)
    expected = _shifted_reference(
        _independent_base_matrix([topology], edge_space, spec)
    )
    assert _relative_sparse(proxy.matrix, expected) <= _TOLERANCE
