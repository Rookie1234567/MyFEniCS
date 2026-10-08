"""Fourier--Legendre contractions for affine hex port faces.

This module contains only small dense reference-cell operations.  The live
function-space element and the physical face geometry remain owned by the
caller; no global matrix, factor, or mesh-sized coefficient array is created
here.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

SURFACE_LEGENDRE_BACKEND = "q160_affine_hex_fourier_legendre_v1"
SURFACE_POINTWISE_WEIGHTED_BACKEND = (
    "q160_affine_hex_pointwise_weighted_legendre_v2"
)
SURFACE_COMPONENT_PAIR_BACKEND = (
    "q160_affine_hex_pointwise_weighted_legendre_component_pair_v1"
)
SURFACE_WEIGHTED_MOMENT_CONTRACTION = "q160_weighted_moment_x_then_y_v1"
SURFACE_GEOMETRY_CACHE_MAX_BYTES = 4 * 1024**3


def surface_geometry_cache_payload_bytes(
    *, point_count: int, facet_count: int
) -> int:
    """Return the four-array numeric cache payload for actual face counts."""

    points = int(point_count)
    facets = int(facet_count)
    if points <= 0 or facets < 0:
        raise ValueError("surface geometry cache dimensions are invalid")
    # physical coordinates (3), determinant (1), cofactor (9), measure (1),
    # all float64. Metadata and small raw-coordinate identity snapshots are
    # accounted separately from this numeric cache payload.
    return facets * points * 14 * np.dtype(np.float64).itemsize


def validate_component_pair_degree(backend: str, degree: int) -> None:
    """Keep the opt-in paired backend on its qualified p6 lane only."""

    if backend == SURFACE_COMPONENT_PAIR_BACKEND and int(degree) != 6:
        raise NotImplementedError(
            "the paired pointwise surface backend is restricted to actual p6"
        )


def validate_weighted_moment_contraction(
    algorithm: str | None,
    *,
    backend: str,
    degree: int,
    quadrature_degree: int,
    reuse_geometry_cache: bool,
) -> None:
    """Restrict the x/y weighted contraction to its qualified opt-in lane."""

    if algorithm is None:
        return
    if algorithm != SURFACE_WEIGHTED_MOMENT_CONTRACTION:
        raise ValueError("unsupported weighted-moment contraction selection")
    if (
        backend != SURFACE_COMPONENT_PAIR_BACKEND
        or int(degree) != 6
        or int(quadrature_degree) != 160
        or not reuse_geometry_cache
    ):
        raise ValueError(
            "weighted-moment contraction requires cached p6 q160 component-pair assembly"
        )


SURFACE_RELATIVE_GATE = 1.0e-11
SURFACE_SUPPORT_RELATIVE_CUTOFF = 1.0e-13
SURFACE_MOMENT_CACHE_LIMIT = 64


def component_pair_explicit_array_payload_bounds(
    *,
    point_count: int,
    polynomial_width: int,
    local_dof_count: int,
    facet_count: int,
    owned_support_rows: int,
    row_index_bytes: int,
) -> dict[str, int | str]:
    """Bound explicit NumPy payloads for one paired component assembly.

    The bound is deliberately separate from RSS. It counts the named arrays
    allocated by the pointwise geometry/moment helpers and a conservative
    support-extraction allowance, but excludes PETSc storage, allocator and
    NumPy/BLAS internal scratch, Python object headers, and persistent context
    arrays.
    """

    q = int(point_count)
    width = int(polynomial_width)
    local_dofs = int(local_dof_count)
    facets = int(facet_count)
    support_rows = int(owned_support_rows)
    index_bytes = int(row_index_bytes)
    if min(q, width, local_dofs, facets, support_rows, index_bytes) < 0:
        raise ValueError("component-pair payload dimensions must be nonnegative")
    if min(q, width, local_dofs, facets, index_bytes) == 0:
        raise ValueError("component-pair payload dimensions must be positive")

    float_bytes = np.dtype(np.float64).itemsize
    complex_bytes = np.dtype(np.complex128).itemsize
    bool_bytes = np.dtype(np.bool_).itemsize

    coordinate_dofs = 8 * 3 * float_bytes
    mapped_coordinates_and_jacobians = q * (3 + 9) * float_bytes
    surface_named_arrays = q * (
        75 * float_bytes + 6 * complex_bytes + 20 * bool_bytes
    )
    surface_stage = (
        coordinate_dofs
        + mapped_coordinates_and_jacobians
        + surface_named_arrays
        + 3 * complex_bytes
    )

    # The fill stage retains the returned determinant/cofactor/measure/phase
    # alongside inverse-column, weighted-basis, one matrix product, pair
    # moments, and finite-check masks. Four local vectors conservatively allow
    # each component vector plus its standard-transform result to coexist.
    fill_stage = (
        coordinate_dofs
        + mapped_coordinates_and_jacobians
        + q * (11 + 3 + 3) * float_bytes
        + q * (2 + width) * complex_bytes
        + width * width * complex_bytes
        + 6 * width * width * (complex_bytes + bool_bytes)
        + 4 * local_dofs * complex_bytes
    )
    pointwise_pair_peak = max(surface_stage, fill_stage)

    staged_values = facets * local_dofs * complex_bytes
    staged_flags = facets * bool_bytes
    # This intentionally overcounts the gather, index conversion, finite mask,
    # and both returned sparse component arrays at up to the full support size.
    extraction_and_retained_outputs = support_rows * (
        16 * complex_bytes + 8 * index_bytes + 8 * float_bytes + bool_bytes
    )
    explicit_payload_upper = (
        staged_values
        + staged_flags
        + max(pointwise_pair_peak, extraction_and_retained_outputs)
    )
    return {
        "point_count": q,
        "polynomial_width": width,
        "local_dof_count": local_dofs,
        "facet_count": facets,
        "owned_support_rows": support_rows,
        "staging_complex_values_bytes": staged_values,
        "staging_filled_flags_bytes": staged_flags,
        "pointwise_helper_explicit_array_peak_bytes": pointwise_pair_peak,
        "support_extract_and_retained_outputs_upper_bytes": (
            extraction_and_retained_outputs
        ),
        "explicit_numpy_payload_upper_bytes": explicit_payload_upper,
        "scope": (
            "explicit NumPy arrays only; not process RSS; excludes PETSc Vec, "
            "allocator/BLAS scratch, persistent context arrays and Python overhead"
        ),
    }


@lru_cache(maxsize=1)
def _ffcx_float64_formatter_with_identity() -> tuple[Any, dict[str, str]]:
    """Create the active FFCx float64 formatter once and bind its source."""

    from ffcx.codegeneration.C import c_implementation

    source_path = Path(c_implementation.__file__).resolve()
    source_sha256 = hashlib.sha256(source_path.read_bytes()).hexdigest()
    formatter = c_implementation.CFormatter(np.float64)
    return formatter, {
        "class": "ffcx.codegeneration.C.c_implementation.CFormatter",
        "method": "_format_number",
        "scalar_dtype": np.dtype(np.float64).str,
        "module_path": str(source_path),
        "module_sha256": source_sha256,
    }


def ffcx_float64_formatter_facts() -> dict[str, str]:
    """Return the identity of the formatter used for generated C literals."""

    return dict(_ffcx_float64_formatter_with_identity()[1])


def roundtrip_ffcx_float64_array(values: np.ndarray, *, name: str) -> np.ndarray:
    """Format float64 values as FFCx C literals and parse them back.

    FFCx applies this scalar formatting after its coordinate-table clamp.  The
    returned array is newly allocated; the provider's input remains untouched.
    """

    source = np.asarray(values)
    if source.dtype != np.dtype(np.float64):
        raise ValueError(f"{name} must be a float64 array")
    if not np.isfinite(source).all():
        raise ValueError(f"{name} contains non-finite values")
    formatter, _ = _ffcx_float64_formatter_with_identity()
    result = np.fromiter(
        (float(formatter._format_number(float(value))) for value in source.flat),
        dtype=np.float64,
        count=source.size,
    ).reshape(source.shape)
    if not np.isfinite(result).all():
        raise ValueError(f"{name} FFCx formatter roundtrip is non-finite")
    return result


def borrow_readonly_array_view(array: np.ndarray, *, name: str) -> np.ndarray:
    """Return a read-only view without changing the provider array or dtype."""

    if not isinstance(array, np.ndarray):
        raise TypeError(f"{name} must be provided as a NumPy array")
    view = array.view()
    view.flags.writeable = False
    return view


def normalized_interval_legendre(points: np.ndarray, degree: int) -> np.ndarray:
    """Evaluate Basix's normalized standard Legendre polyset on ``[0, 1]``.

    The output has shape ``(npoint, degree + 1)``.  Basix normalizes
    ``P_k(2x-1)`` by ``sqrt(2k+1)`` on the unit interval.
    """

    points = np.asarray(points, dtype=np.float64).reshape(-1)
    degree = int(degree)
    if degree < 0 or not np.isfinite(points).all():
        raise ValueError("Legendre points/degree are invalid")
    coordinate = 2.0 * points - 1.0
    values = np.polynomial.legendre.legvander(coordinate, degree)
    values *= np.sqrt(2.0 * np.arange(degree + 1, dtype=np.float64) + 1.0)
    if not np.isfinite(values).all():
        raise ValueError("Legendre table contains non-finite values")
    return np.ascontiguousarray(values)


def face_trace_table(
    coefficient_matrix: np.ndarray,
    degree: int,
    component: int,
    zeta_face: float,
    *,
    endpoint_values: np.ndarray | None = None,
) -> np.ndarray:
    """Contract only the reference ``z`` endpoint of one live N1E C block.

    ``coefficient_matrix`` follows the actual Basix N1E coefficient ordering
    used by :mod:`fullspace_n1e_sum_factor`; this function does not apply a
    Piola factor, phase, orientation, or MPC transformation.
    """

    coefficient_matrix = np.asarray(coefficient_matrix)
    degree = int(degree)
    component = int(component)
    width = degree + 1
    if degree < 1 or component not in (0, 1):
        raise ValueError("surface trace requires p>=1 and tangential x/y component")
    if (
        coefficient_matrix.dtype != np.dtype(np.float64)
        or not coefficient_matrix.flags.c_contiguous
    ):
        raise ValueError("Basix coefficient matrix must be contiguous float64")
    if coefficient_matrix.ndim != 2 or coefficient_matrix.shape[1] != 3 * width**3:
        raise ValueError("Basix coefficient matrix has an unsupported tensor layout")
    if not np.isfinite(coefficient_matrix).all():
        raise ValueError("Basix coefficient matrix contains non-finite values")
    if zeta_face not in (0.0, 1.0):
        raise ValueError("only exact reference-cell z endpoints are supported")
    dof_count = int(coefficient_matrix.shape[0])
    blocks = coefficient_matrix.reshape(dof_count, 3, width, width, width)
    endpoint = (
        normalized_interval_legendre(np.asarray([zeta_face]), degree)[0]
        if endpoint_values is None
        else np.asarray(endpoint_values, dtype=np.float64).reshape(-1)
    )
    if endpoint.shape != (width,) or not np.isfinite(endpoint).all():
        raise ValueError("Basix endpoint polynomial table has an unexpected shape")
    table = np.einsum(
        "iabk,k->iab", blocks[:, component, :, :, :], endpoint, optimize=True
    )
    table = np.ascontiguousarray(table, dtype=np.float64)
    if not np.isfinite(table).all():
        raise ValueError("face trace table contains non-finite values")
    return table


def face_trace_reference_tensor(
    coefficient_matrix: np.ndarray,
    degree: int,
    zeta_face: float,
    *,
    endpoint_values: np.ndarray,
) -> np.ndarray:
    """Contract the live C matrix at a face endpoint, retaining all ref axes.

    The returned array is ``(local_dof, reference_component, a, b)``.  It
    deliberately keeps all three reference components: pointwise inverse
    Piola terms can couple a normal reference basis component into a
    tangential physical component through small but real off-diagonal terms.
    """

    coefficient_matrix = np.asarray(coefficient_matrix)
    degree = int(degree)
    width = degree + 1
    if degree < 1:
        raise ValueError("surface trace requires p>=1")
    if (
        coefficient_matrix.dtype != np.dtype(np.float64)
        or not coefficient_matrix.flags.c_contiguous
        or coefficient_matrix.ndim != 2
        or coefficient_matrix.shape[1] != 3 * width**3
    ):
        raise ValueError("Basix coefficient matrix has an unsupported tensor layout")
    if not np.isfinite(coefficient_matrix).all():
        raise ValueError("Basix coefficient matrix contains non-finite values")
    if zeta_face not in (0.0, 1.0):
        raise ValueError("only exact reference-cell z endpoints are supported")
    endpoint = np.asarray(endpoint_values, dtype=np.float64).reshape(-1)
    if endpoint.shape != (width,) or not np.isfinite(endpoint).all():
        raise ValueError("Basix endpoint polynomial table has an unexpected shape")
    blocks = coefficient_matrix.reshape(-1, 3, width, width, width)
    # Basix C ordering is (reference component k, x Legendre a, y Legendre
    # b, z Legendre).  Keep all three vector components: selecting a physical
    # output component belongs to the inverse-Piola moment, not this trace.
    trace = np.einsum("icabz,z->icab", blocks, endpoint, optimize=True)
    trace = np.ascontiguousarray(trace, dtype=np.float64)
    if not np.isfinite(trace).all():
        raise ValueError("face reference trace tensor contains non-finite values")
    return trace


def scalar_hex_coordinate_basix_element(
    mesh: Any, *, hexahedron_cell_type: Any
) -> tuple[Any, dict[str, Any]]:
    """Read and cross-check the scalar coordinate Basix element on a live mesh.

    DOLFINx ``mesh.geometry.cmap`` is a ``CoordinateElement`` wrapper and
    does not expose Basix ``tabulate``.  The UFL domain retains the element
    from which that wrapper was built; for the vector-valued coordinate field
    its ``basix_element`` is the scalar P1 component used for each geometry
    coordinate.
    """

    domain_getter = getattr(mesh, "ufl_domain", None)
    if not callable(domain_getter):
        raise NotImplementedError("live mesh does not expose its UFL domain")
    domain = domain_getter()
    if domain is None:
        raise NotImplementedError("live mesh has no retained UFL coordinate element")
    coordinate_ufl_element = domain.ufl_coordinate_element()
    scalar_element = getattr(coordinate_ufl_element, "basix_element", None)
    coordinate_map = mesh.geometry.cmap
    geometry_dofmap = np.asarray(mesh.geometry.dofmap)
    geometry_coordinates = np.asarray(mesh.geometry.x)
    try:
        value_shape = tuple(
            int(value)
            for value in coordinate_ufl_element.reference_value_shape
        )
        block_size = int(coordinate_ufl_element.block_size)
    except (AttributeError, TypeError, ValueError) as exc:
        raise NotImplementedError(
            "live UFL coordinate element has no checked vector-block metadata"
        ) from exc
    if scalar_element is None:
        raise NotImplementedError("live UFL coordinate element has no Basix scalar element")

    variant = getattr(scalar_element, "lagrange_variant", None)
    variant_value = getattr(variant, "value", variant)
    cmap_variant = getattr(coordinate_map, "variant", None)
    scalar_hash_method = getattr(scalar_element, "hash", None)
    cmap_hash_method = getattr(coordinate_map, "hash", None)
    if not callable(scalar_hash_method) or not callable(cmap_hash_method):
        raise NotImplementedError("coordinate scalar/cmap hash API is unavailable")
    scalar_hash = int(scalar_hash_method())
    cmap_hash = int(cmap_hash_method())
    scalar_degree = int(scalar_element.degree)
    scalar_dim = int(scalar_element.dim)
    scalar_value_size = int(scalar_element.value_size)
    cmap_degree = int(coordinate_map.degree)
    cmap_dim = int(coordinate_map.dim)
    cmap_variant_value = int(getattr(cmap_variant, "value", cmap_variant))
    scalar_variant_value = int(variant_value)
    geometry_shape = tuple(int(value) for value in geometry_dofmap.shape)
    coordinate_shape = tuple(int(value) for value in geometry_coordinates.shape)

    if (
        scalar_element.cell_type != hexahedron_cell_type
        or scalar_degree != 1
        or scalar_dim != 8
        or scalar_value_size != 1
        or cmap_degree != scalar_degree
        or cmap_dim != scalar_dim
        or cmap_variant_value != scalar_variant_value
        or cmap_hash != scalar_hash
        or value_shape != (3,)
        or block_size != 3
        or geometry_dofmap.ndim != 2
        or geometry_dofmap.shape[1] != scalar_dim
        or not np.issubdtype(geometry_dofmap.dtype, np.integer)
        or geometry_coordinates.ndim != 2
        or geometry_coordinates.shape[1] != 3
    ):
        raise NotImplementedError(
            "live coordinate element does not match scalar P1 hex/8-node 3D layout"
        )
    return scalar_element, {
        "element_source": "mesh.ufl_domain().ufl_coordinate_element().basix_element",
        "basix_element_value_size": scalar_value_size,
        "basix_element_dimension": scalar_dim,
        "basix_element_degree": scalar_degree,
        "basix_element_cell_type": str(scalar_element.cell_type),
        "basix_element_variant": scalar_variant_value,
        "basix_element_hash": scalar_hash,
        "coordinate_map_degree": cmap_degree,
        "coordinate_map_dimension": cmap_dim,
        "coordinate_map_variant": cmap_variant_value,
        "coordinate_map_hash": cmap_hash,
        "coordinate_ufl_reference_value_shape": list(value_shape),
        "coordinate_ufl_block_size": block_size,
        "geometry_dofmap_shape": list(geometry_shape),
        "geometry_coordinates_shape": list(coordinate_shape),
    }


def clamp_ffcx_coordinate_table(
    table: np.ndarray, *, rtol: float, atol: float
) -> np.ndarray:
    """Apply FFCx's in-place ``-1, 0, 1`` table cleanup to an owned copy."""

    from ffcx.ir.elementtables import clamp_table_small_numbers

    source = np.asarray(table, dtype=np.float64)
    if not np.isfinite(source).all():
        raise ValueError("coordinate Basix table contains non-finite values")
    if not np.isfinite([rtol, atol]).all() or rtol < 0.0 or atol < 0.0:
        raise ValueError("FFCx table clamp tolerances are invalid")
    result = np.array(source, dtype=np.float64, copy=True)
    clamp_table_small_numbers(result, rtol=float(rtol), atol=float(atol))
    if not np.isfinite(result).all():
        raise ValueError("FFCx-clamped coordinate table contains non-finite values")
    return result


def map_coordinate_quadrature(
    coordinate_dofs: np.ndarray,
    coordinate_values: np.ndarray,
    coordinate_derivatives: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Map reference quadrature points and form their live geometry Jacobians.

    Inputs use the current Basix coordinate element's local dof order.  The
    caller obtains both tabulations from the live mesh coordinate element and
    passes the corresponding raw coordinate-dof row; no idealized axis
    Jacobian is substituted.
    """

    coordinate_dofs = np.asarray(coordinate_dofs, dtype=np.float64)
    coordinate_values = np.asarray(coordinate_values, dtype=np.float64)
    coordinate_derivatives = np.asarray(coordinate_derivatives, dtype=np.float64)
    if (
        coordinate_dofs.ndim != 2
        or coordinate_dofs.shape[0] != 8
        or coordinate_dofs.shape[1] != 3
        or coordinate_values.ndim != 2
        or coordinate_values.shape[1] != coordinate_dofs.shape[0]
        or coordinate_derivatives.shape
        != (coordinate_values.shape[0], coordinate_dofs.shape[0], 3)
    ):
        raise ValueError("live coordinate element arrays have incompatible shapes")
    if not all(
        np.isfinite(array).all()
        for array in (coordinate_dofs, coordinate_values, coordinate_derivatives)
    ):
        raise ValueError("live coordinate element arrays contain non-finite values")
    point_count = int(coordinate_values.shape[0])
    physical_coordinates = np.zeros((point_count, 3), dtype=np.float64)
    jacobians = np.zeros((point_count, 3, 3), dtype=np.float64)
    # Match the generated FFCx coordinate/Jacobian loops: one scalar
    # accumulation per geometry DOF in local order, without a BLAS reduction
    # that can change the tiny cross terms used by the row-support gate.
    for coordinate_dof in range(8):
        for physical_axis in range(3):
            physical_coordinates[:, physical_axis] += (
                coordinate_dofs[coordinate_dof, physical_axis]
                * coordinate_values[:, coordinate_dof]
            )
            for reference_axis in range(3):
                jacobians[:, physical_axis, reference_axis] += (
                    coordinate_dofs[coordinate_dof, physical_axis]
                    * coordinate_derivatives[
                        :, coordinate_dof, reference_axis
                    ]
                )
    if not np.isfinite(physical_coordinates).all() or not np.isfinite(jacobians).all():
        raise ValueError("live coordinate map produced non-finite points or Jacobians")
    return physical_coordinates, jacobians


def _validated_pointwise_inputs(
    physical_coordinates: np.ndarray,
    jacobians: np.ndarray,
    quadrature_weights: np.ndarray,
    polynomial_x: np.ndarray,
    polynomial_y: np.ndarray,
    *,
    facet_jacobian: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Validate and normalize inputs shared by one or both component moments."""

    physical_coordinates = np.asarray(physical_coordinates, dtype=np.float64)
    jacobians = np.asarray(jacobians, dtype=np.float64)
    quadrature_weights = np.asarray(quadrature_weights, dtype=np.float64).reshape(-1)
    polynomial_x = np.asarray(polynomial_x, dtype=np.float64)
    polynomial_y = np.asarray(polynomial_y, dtype=np.float64)
    facet_jacobian = np.asarray(facet_jacobian, dtype=np.float64)
    point_count = quadrature_weights.size
    if (
        physical_coordinates.shape != (point_count, 3)
        or jacobians.shape != (point_count, 3, 3)
        or polynomial_x.ndim != 2
        or polynomial_y.ndim != 2
        or polynomial_x.shape[0] != point_count
        or polynomial_y.shape[0] != point_count
        or polynomial_x.shape[1] != polynomial_y.shape[1]
        or facet_jacobian.shape != (3, 2)
    ):
        raise ValueError("pointwise face data has incompatible shapes")
    if not all(
        np.isfinite(array).all()
        for array in (
            physical_coordinates,
            jacobians,
            quadrature_weights,
            polynomial_x,
            polynomial_y,
            facet_jacobian,
        )
    ):
        raise ValueError("pointwise face data contains non-finite values")

    return (
        physical_coordinates,
        jacobians,
        quadrature_weights,
        polynomial_x,
        polynomial_y,
        facet_jacobian,
    )


def _pointwise_surface_geometry_terms(
    jacobians: np.ndarray, facet_jacobian: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Build generated-C determinant, cofactor and surface measure arrays."""

    # Match the generated C kernel's cofactor/determinant grouping rather than
    # invoking a batch of tiny LU factorizations. J is physical-by-reference.
    a = jacobians[:, 0, 0]
    b = jacobians[:, 0, 1]
    c = jacobians[:, 0, 2]
    d = jacobians[:, 1, 0]
    e = jacobians[:, 1, 1]
    f = jacobians[:, 1, 2]
    g = jacobians[:, 2, 0]
    h = jacobians[:, 2, 1]
    i = jacobians[:, 2, 2]

    det_0 = c * h
    det_1 = -b
    det_2 = i * det_1
    det_3 = det_0 + det_2
    det_4 = e * i
    det_5 = f * h
    det_6 = -det_5
    det_7 = det_4 + det_6
    det_8 = a * det_7
    det_9 = d * i
    det_10 = f * g
    det_11 = -det_10
    det_12 = det_9 + det_11
    det_13 = det_12 * det_1
    det_14 = det_8 + det_13
    det_15 = d * h
    det_16 = e * g
    det_17 = -det_16
    det_18 = det_15 + det_17
    det_19 = c * det_18
    determinant = det_14 + det_19

    cofactors = np.empty_like(jacobians)
    cofactors[:, 0, 0] = det_7
    cofactors[:, 0, 1] = det_3
    cof_02_0 = b * f
    cof_02_1 = -(c * e)
    cofactors[:, 0, 2] = cof_02_0 + cof_02_1
    cof_10_0 = f * g
    cof_10_1 = -(d * i)
    cofactors[:, 1, 0] = cof_10_0 + cof_10_1
    cof_11_0 = a * i
    cof_11_1 = g * (-c)
    cofactors[:, 1, 1] = cof_11_0 + cof_11_1
    cof_12_0 = c * d
    cof_12_1 = -(a * f)
    cofactors[:, 1, 2] = cof_12_0 + cof_12_1
    cofactors[:, 2, 0] = det_18
    cof_21_0 = b * g
    cof_21_1 = h * (-a)
    cofactors[:, 2, 1] = cof_21_0 + cof_21_1
    cof_22_0 = a * e
    cof_22_1 = -(b * d)
    cofactors[:, 2, 2] = cof_22_0 + cof_22_1
    if (
        not np.isfinite(cofactors).all()
        or not np.isfinite(determinant).all()
        or np.any(determinant <= 0.0)
    ):
        raise ValueError("pointwise surface Jacobian is invalid")

    # FFCx's generated CellFacetJacobian is a 3x2 map from the reference face
    # to the reference cell. Reproduce its three cross-product minors and
    # summation order from fullspace_surface_legendre's recorded C excerpt.
    t0x_0 = jacobians[:, 0, 0] * facet_jacobian[0, 0]
    t0x_1 = jacobians[:, 0, 1] * facet_jacobian[1, 0]
    t0x = (t0x_0 + t0x_1) + jacobians[:, 0, 2] * facet_jacobian[2, 0]
    t0y_0 = facet_jacobian[0, 0] * jacobians[:, 1, 0]
    t0y_1 = facet_jacobian[1, 0] * jacobians[:, 1, 1]
    t0y = (t0y_0 + t0y_1) + jacobians[:, 1, 2] * facet_jacobian[2, 0]
    t0z_0 = facet_jacobian[0, 0] * jacobians[:, 2, 0]
    t0z_1 = facet_jacobian[1, 0] * jacobians[:, 2, 1]
    t0z = (t0z_0 + t0z_1) + facet_jacobian[2, 0] * jacobians[:, 2, 2]
    t1x_0 = jacobians[:, 0, 0] * facet_jacobian[0, 1]
    t1x_1 = jacobians[:, 0, 1] * facet_jacobian[1, 1]
    t1x = (t1x_0 + t1x_1) + jacobians[:, 0, 2] * facet_jacobian[2, 1]
    t1y_0 = facet_jacobian[0, 1] * jacobians[:, 1, 0]
    t1y_1 = jacobians[:, 1, 1] * facet_jacobian[1, 1]
    t1y = (t1y_0 + t1y_1) + jacobians[:, 1, 2] * facet_jacobian[2, 1]
    t1z_0 = facet_jacobian[0, 1] * jacobians[:, 2, 0]
    t1z_1 = facet_jacobian[1, 1] * jacobians[:, 2, 1]
    t1z = (t1z_0 + t1z_1) + jacobians[:, 2, 2] * facet_jacobian[2, 1]
    cross_x_0 = t0y * t1z
    cross_x_1 = -(t1y * t0z)
    cross_x = cross_x_0 + cross_x_1
    cross_y_0 = t1x * t0z
    cross_y_1 = -(t0x * t1z)
    cross_y = cross_y_0 + cross_y_1
    cross_z_0 = t0x * t1y
    cross_z_1 = -(t1x * t0y)
    cross_z = cross_z_0 + cross_z_1
    measure_x2 = cross_x * cross_x
    measure_y2 = cross_y * cross_y
    measure_z2 = cross_z * cross_z
    measure_xy = measure_x2 + measure_y2
    measure_squared = measure_xy + measure_z2
    surface_measure = np.sqrt(measure_squared)

    return determinant, cofactors, surface_measure


def _pointwise_surface_phase(
    physical_coordinates: np.ndarray,
    alpha: complex,
    gamma: complex,
    kz: complex,
) -> np.ndarray:
    """Evaluate the original generated-C phase expression in its exact order."""

    phase_rates = np.asarray(
        [complex(alpha), complex(gamma), complex(kz)], dtype=np.complex128
    )
    if not np.isfinite(phase_rates.real).all() or not np.isfinite(phase_rates.imag).all():
        raise ValueError("surface phase rates contain non-finite values")
    # The compiled UFL expression is (i*gamma)*y + (i*alpha)*x, then
    # +(i*kz)*z. Keep that order and the rate-before-coordinate products.
    phase_y_rate = 1j * phase_rates[1]
    phase_x_rate = 1j * phase_rates[0]
    phase_z_rate = 1j * phase_rates[2]
    phase_y = physical_coordinates[:, 1] * phase_y_rate
    phase_x = physical_coordinates[:, 0] * phase_x_rate
    phase_xy = phase_y + phase_x
    phase_z = physical_coordinates[:, 2] * phase_z_rate
    phase_argument = phase_xy + phase_z
    phase = np.exp(phase_argument)
    if not np.isfinite(phase).all():
        raise ValueError("pointwise surface phase is non-finite")
    return phase


def _pointwise_surface_terms(
    physical_coordinates: np.ndarray,
    jacobians: np.ndarray,
    facet_jacobian: np.ndarray,
    alpha: complex,
    gamma: complex,
    kz: complex,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Build generated-C determinant, cofactor, measure and phase once."""

    # Preserve the original validation order: phase-rate shape/finite checks
    # precede generated geometry arithmetic.
    phase_rates = np.asarray(
        [complex(alpha), complex(gamma), complex(kz)], dtype=np.complex128
    )
    if not np.isfinite(phase_rates.real).all() or not np.isfinite(phase_rates.imag).all():
        raise ValueError("surface phase rates contain non-finite values")
    determinant, cofactors, surface_measure = _pointwise_surface_geometry_terms(
        jacobians, facet_jacobian
    )
    # Use the validated rates while retaining the exact rate-before-coordinate
    # products and expression grouping used by the original kernel.
    phase_y_rate = 1j * phase_rates[1]
    phase_x_rate = 1j * phase_rates[0]
    phase_z_rate = 1j * phase_rates[2]
    phase_y = physical_coordinates[:, 1] * phase_y_rate
    phase_x = physical_coordinates[:, 0] * phase_x_rate
    phase_xy = phase_y + phase_x
    phase_z = physical_coordinates[:, 2] * phase_z_rate
    phase_argument = phase_xy + phase_z
    phase = np.exp(phase_argument)
    if not np.isfinite(surface_measure).all() or not np.isfinite(phase).all():
        raise ValueError("pointwise surface measure or phase is non-finite")
    return determinant, cofactors, surface_measure, phase


def _fill_pointwise_weighted_moments(
    quadrature_weights: np.ndarray,
    polynomial_x: np.ndarray,
    polynomial_y: np.ndarray,
    determinant: np.ndarray,
    cofactors: np.ndarray,
    surface_measure: np.ndarray,
    phase: np.ndarray,
    component: int,
    moments: np.ndarray,
) -> None:
    """Fill one physical-component output with the original q/reduction order."""

    point_count = int(quadrature_weights.size)
    width = int(polynomial_x.shape[1])
    if component not in (0, 1, 2):
        raise ValueError("pointwise physical component must be 0, 1 or 2")
    if moments.shape != (3, width, width):
        raise ValueError("pointwise moment output has an incompatible shape")

    inverse_column = np.empty((point_count, 3), dtype=np.float64)
    for reference_component in range(3):
        inverse_column[:, reference_component] = (
            cofactors[:, reference_component, component] / determinant
        )
    if not np.isfinite(inverse_column).all():
        raise ValueError("pointwise inverse Piola column is non-finite")
    # The caller supplies q-ordered expanded x/y tables, built once from the
    # verified Basix outer-product ordering.
    basis_x = polynomial_x
    basis_y = polynomial_y
    weighted = np.empty(point_count, dtype=np.complex128)
    weighted_basis = np.empty((width, point_count), dtype=np.complex128)
    for reference_component in range(3):
        # Preserve the generated C multiply order: K * phase, then surface
        # measure, then the single Basix product-rule weight.
        np.multiply(inverse_column[:, reference_component], phase, out=weighted)
        weighted *= surface_measure
        weighted *= quadrature_weights
        np.multiply(
            basis_x.T, weighted[None, :], out=weighted_basis
        )
        moments[reference_component] = weighted_basis @ basis_y
    if not np.isfinite(moments).all():
        raise ValueError("pointwise weighted Legendre moments are non-finite")


def pointwise_weighted_legendre_moments(
    physical_coordinates: np.ndarray,
    jacobians: np.ndarray,
    quadrature_weights: np.ndarray,
    polynomial_x: np.ndarray,
    polynomial_y: np.ndarray,
    *,
    facet_jacobian: np.ndarray,
    alpha: complex,
    gamma: complex,
    kz: complex,
    physical_component: int,
) -> np.ndarray:
    """Integrate one component using the generated-C pointwise arithmetic.

    For a reference z face this forms
    ``M[k,a,b] = sum_q w[q] * measure[q] * phase[q] *
    invJ[q,k,c] * L_a(xi[q]) * L_b(eta[q])``.  The quadrilateral product
    weight is multiplied once; no origin phase or axis-width correction is
    applied.
    """

    (
        physical_coordinates,
        jacobians,
        quadrature_weights,
        polynomial_x,
        polynomial_y,
        facet_jacobian,
    ) = _validated_pointwise_inputs(
        physical_coordinates,
        jacobians,
        quadrature_weights,
        polynomial_x,
        polynomial_y,
        facet_jacobian=facet_jacobian,
    )
    component = int(physical_component)
    if component not in (0, 1, 2):
        raise ValueError("pointwise face data has incompatible shapes")
    determinant, cofactors, surface_measure, phase = _pointwise_surface_terms(
        physical_coordinates, jacobians, facet_jacobian, alpha, gamma, kz
    )
    moments = np.empty(
        (3, polynomial_x.shape[1], polynomial_x.shape[1]), dtype=np.complex128
    )
    _fill_pointwise_weighted_moments(
        quadrature_weights,
        polynomial_x,
        polynomial_y,
        determinant,
        cofactors,
        surface_measure,
        phase,
        component,
        moments,
    )
    return moments


def pointwise_weighted_legendre_moments_pair(
    physical_coordinates: np.ndarray,
    jacobians: np.ndarray,
    quadrature_weights: np.ndarray,
    polynomial_x: np.ndarray,
    polynomial_y: np.ndarray,
    *,
    facet_jacobian: np.ndarray,
    alpha: complex,
    gamma: complex,
    kz: complex,
) -> np.ndarray:
    """Form x/y physical-component moments from one shared facet geometry."""

    (
        physical_coordinates,
        jacobians,
        quadrature_weights,
        polynomial_x,
        polynomial_y,
        facet_jacobian,
    ) = _validated_pointwise_inputs(
        physical_coordinates,
        jacobians,
        quadrature_weights,
        polynomial_x,
        polynomial_y,
        facet_jacobian=facet_jacobian,
    )
    determinant, cofactors, surface_measure, phase = _pointwise_surface_terms(
        physical_coordinates, jacobians, facet_jacobian, alpha, gamma, kz
    )
    width = int(polynomial_x.shape[1])
    moments = np.empty((2, 3, width, width), dtype=np.complex128)
    for output_index, component in enumerate((0, 1)):
        _fill_pointwise_weighted_moments(
            quadrature_weights,
            polynomial_x,
            polynomial_y,
            determinant,
            cofactors,
            surface_measure,
            phase,
            component,
            moments[output_index],
        )
    return moments


def pointwise_weighted_legendre_moments_pair_from_geometry(
    physical_coordinates: np.ndarray,
    quadrature_weights: np.ndarray,
    polynomial_x: np.ndarray,
    polynomial_y: np.ndarray,
    determinant: np.ndarray,
    cofactors: np.ndarray,
    surface_measure: np.ndarray,
    *,
    alpha: complex,
    gamma: complex,
    kz: complex,
) -> np.ndarray:
    """Reuse bound raw geometry arrays while recomputing each mode's phase."""

    physical_coordinates = np.asarray(physical_coordinates)
    quadrature_weights = np.asarray(quadrature_weights)
    polynomial_x = np.asarray(polynomial_x)
    polynomial_y = np.asarray(polynomial_y)
    determinant = np.asarray(determinant)
    cofactors = np.asarray(cofactors)
    surface_measure = np.asarray(surface_measure)
    point_count = int(quadrature_weights.size)
    if (
        physical_coordinates.dtype != np.dtype(np.float64)
        or physical_coordinates.shape != (point_count, 3)
        or quadrature_weights.ndim != 1
        or polynomial_x.dtype != np.dtype(np.float64)
        or polynomial_y.dtype != np.dtype(np.float64)
        or polynomial_x.ndim != 2
        or polynomial_y.shape != polynomial_x.shape
        or polynomial_x.shape[0] != point_count
        or determinant.dtype != np.dtype(np.float64)
        or determinant.shape != (point_count,)
        or cofactors.dtype != np.dtype(np.float64)
        or cofactors.shape != (point_count, 3, 3)
        or surface_measure.dtype != np.dtype(np.float64)
        or surface_measure.shape != (point_count,)
    ):
        raise ValueError("cached pointwise surface geometry has incompatible shapes")
    if not all(
        np.isfinite(array).all()
        for array in (
            physical_coordinates,
            quadrature_weights,
            polynomial_x,
            polynomial_y,
            determinant,
            cofactors,
            surface_measure,
        )
    ):
        raise ValueError("cached pointwise surface geometry contains non-finite values")
    phase = _pointwise_surface_phase(physical_coordinates, alpha, gamma, kz)
    width = int(polynomial_x.shape[1])
    moments = np.empty((2, 3, width, width), dtype=np.complex128)
    for output_index, component in enumerate((0, 1)):
        _fill_pointwise_weighted_moments(
            quadrature_weights,
            polynomial_x,
            polynomial_y,
            determinant,
            cofactors,
            surface_measure,
            phase,
            component,
            moments[output_index],
        )
    return moments


def validate_q160_expanded_interval_tables(
    polynomial_values: np.ndarray,
    polynomial_x: np.ndarray,
    polynomial_y: np.ndarray,
) -> dict[str, Any]:
    """Verify immutable x-major/y-minor expansions of the q160 basis once."""

    polynomial_values = np.asarray(polynomial_values)
    polynomial_x = np.asarray(polynomial_x)
    polynomial_y = np.asarray(polynomial_y)
    interval_count = 81
    width = 7
    point_count = interval_count * interval_count
    arrays = (polynomial_values, polynomial_x, polynomial_y)
    if any(
        array.dtype != np.dtype(np.float64)
        or not array.flags.c_contiguous
        or array.flags.writeable
        for array in arrays
    ):
        raise ValueError(
            "q160 interval basis metadata must be immutable contiguous float64"
        )
    if (
        polynomial_values.shape != (interval_count, width)
        or polynomial_x.shape != (point_count, width)
        or polynomial_y.shape != (point_count, width)
    ):
        raise ValueError("q160 expanded interval basis has incompatible dimensions")
    if not all(np.isfinite(array).all() for array in arrays):
        raise ValueError("q160 expanded interval basis contains non-finite values")
    x_rows = polynomial_x.reshape(interval_count, interval_count, width)
    y_rows = polynomial_y.reshape(interval_count, interval_count, width)
    expected_x = np.broadcast_to(polynomial_values[:, None, :], x_rows.shape)
    expected_y = np.broadcast_to(polynomial_values[None, :, :], y_rows.shape)
    if not np.array_equal(x_rows, expected_x):
        raise ValueError("q160 x basis is not the exact x-major repeated interval table")
    if not np.array_equal(y_rows, expected_y):
        raise ValueError("q160 y basis is not the exact y-minor tiled interval table")
    return {
        "interval_point_count": interval_count,
        "quadrature_shape": [interval_count, interval_count],
        "polynomial_width": width,
        "flatten_order": "x-major/y-minor; y is the fastest index",
        "x_expansion_exact_repeat": True,
        "y_expansion_exact_tile": True,
        "arrays_immutable": True,
    }


def pointwise_weighted_legendre_moments_pair_from_geometry_x_then_y(
    physical_coordinates: np.ndarray,
    quadrature_weights: np.ndarray,
    polynomial_values: np.ndarray,
    determinant: np.ndarray,
    cofactors: np.ndarray,
    surface_measure: np.ndarray,
    *,
    alpha: complex,
    gamma: complex,
    kz: complex,
) -> np.ndarray:
    """Contract the original q160 pointwise weights first in x, then y.

    Every q-point still uses its original pointwise inverse-Piola entry,
    phase, surface measure, and complete product weight. Only reduction
    grouping changes to ``(P_x.T @ W) @ P_y`` for each reference and physical
    component.
    """

    physical_coordinates = np.asarray(physical_coordinates)
    quadrature_weights = np.asarray(quadrature_weights)
    polynomial_values = np.asarray(polynomial_values)
    determinant = np.asarray(determinant)
    cofactors = np.asarray(cofactors)
    surface_measure = np.asarray(surface_measure)
    interval_count = 81
    width = 7
    point_count = interval_count * interval_count
    if (
        physical_coordinates.dtype != np.dtype(np.float64)
        or physical_coordinates.shape != (point_count, 3)
        or quadrature_weights.dtype != np.dtype(np.float64)
        or quadrature_weights.shape != (point_count,)
        or polynomial_values.dtype != np.dtype(np.float64)
        or polynomial_values.shape != (interval_count, width)
        or determinant.dtype != np.dtype(np.float64)
        or determinant.shape != (point_count,)
        or cofactors.dtype != np.dtype(np.float64)
        or cofactors.shape != (point_count, 3, 3)
        or surface_measure.dtype != np.dtype(np.float64)
        or surface_measure.shape != (point_count,)
    ):
        raise ValueError("cached q160 weighted-moment inputs have incompatible shapes")
    if not all(
        np.isfinite(array).all()
        for array in (
            physical_coordinates,
            quadrature_weights,
            polynomial_values,
            determinant,
            cofactors,
            surface_measure,
        )
    ):
        raise ValueError("cached q160 weighted-moment input is non-finite")

    phase = _pointwise_surface_phase(physical_coordinates, alpha, gamma, kz)
    if not np.isfinite(phase).all():
        raise ValueError("cached q160 phase is non-finite")
    inverse_values = np.empty(point_count, dtype=np.float64)
    weighted_values = np.empty(point_count, dtype=np.complex128)
    x_contraction = np.empty((width, interval_count), dtype=np.complex128)
    moments = np.empty((2, 3, width, width), dtype=np.complex128)
    px_transpose = polynomial_values.T
    for output_index, physical_component in enumerate((0, 1)):
        for reference_component in range(3):
            np.divide(
                cofactors[:, reference_component, physical_component],
                determinant,
                out=inverse_values,
            )
            if not np.isfinite(inverse_values).all():
                raise ValueError("q160 inverse Piola entries are non-finite")
            # Preserve the old pointwise multiply order before regrouping sums.
            np.multiply(inverse_values, phase, out=weighted_values)
            weighted_values *= surface_measure
            weighted_values *= quadrature_weights
            if not np.isfinite(weighted_values.real).all() or not np.isfinite(
                weighted_values.imag
            ).all():
                raise ValueError("q160 pointwise weighted values are non-finite")
            weighted_matrix = weighted_values.reshape(
                interval_count, interval_count
            )
            np.matmul(px_transpose, weighted_matrix, out=x_contraction)
            np.matmul(
                x_contraction,
                polynomial_values,
                out=moments[output_index, reference_component],
            )
    if not np.isfinite(moments.real).all() or not np.isfinite(moments.imag).all():
        raise ValueError("q160 weighted moments are non-finite")
    return moments


def assemble_face_from_weighted_moments(
    trace_tensor: np.ndarray, moments: np.ndarray
) -> np.ndarray:
    """Contract all three reference-component endpoint coefficients once."""

    trace_tensor = np.asarray(trace_tensor, dtype=np.float64)
    moments = np.asarray(moments, dtype=np.complex128)
    if (
        trace_tensor.ndim != 4
        or trace_tensor.shape[1:] != moments.shape
        or moments.ndim != 3
        or moments.shape[0] != 3
    ):
        raise ValueError("face trace and pointwise moment tensors differ")
    if not np.isfinite(trace_tensor).all() or not np.isfinite(moments).all():
        raise ValueError("face trace or pointwise moments contain non-finite values")
    result = np.einsum("ikab,kab->i", trace_tensor, moments, optimize=True)
    if not np.isfinite(result).all():
        raise ValueError("pointwise face functional contains non-finite values")
    return np.asarray(result, dtype=np.complex128)


def fourier_legendre_moment(
    points: np.ndarray,
    weights: np.ndarray,
    degree: int,
    rate: complex,
    width: float,
    *,
    polynomial_values: np.ndarray | None = None,
) -> np.ndarray:
    """Compute ``sum_q w_q exp(i rate width x_q) L_a(x_q)``."""

    points = np.asarray(points, dtype=np.float64).reshape(-1)
    weights = np.asarray(weights, dtype=np.float64).reshape(-1)
    rate = complex(rate)
    width = float(width)
    if points.shape != weights.shape or not points.size:
        raise ValueError("interval quadrature points and weights differ")
    if not np.isfinite(points).all() or not np.isfinite(weights).all():
        raise ValueError("interval quadrature contains non-finite values")
    if not np.isfinite([rate.real, rate.imag, width]).all() or width <= 0.0:
        raise ValueError("Fourier rate or cell width is invalid")
    basis = (
        normalized_interval_legendre(points, int(degree))
        if polynomial_values is None
        else np.asarray(polynomial_values, dtype=np.float64)
    )
    if basis.shape != (points.size, int(degree) + 1) or not np.isfinite(basis).all():
        raise ValueError("Basix interval polynomial table has an unexpected shape")
    phase = np.exp(1j * rate * width * points)
    result = basis.T @ (weights.astype(np.complex128) * phase)
    if not np.isfinite(result).all():
        raise ValueError("Fourier--Legendre moments contain non-finite values")
    return np.asarray(result, dtype=np.complex128)


def assemble_face_from_moments(
    trace_table: np.ndarray,
    x_moments: np.ndarray,
    y_moments: np.ndarray,
    *,
    hx: float,
    hy: float,
    h_component: float,
    phase_origin: complex,
) -> np.ndarray:
    """Evaluate one affine-hex face functional from separable moments."""

    trace_table = np.asarray(trace_table, dtype=np.float64)
    x_moments = np.asarray(x_moments, dtype=np.complex128).reshape(-1)
    y_moments = np.asarray(y_moments, dtype=np.complex128).reshape(-1)
    hx = float(hx)
    hy = float(hy)
    h_component = float(h_component)
    phase_origin = complex(phase_origin)
    if (
        trace_table.ndim != 3
        or trace_table.shape[1:] != (x_moments.size, y_moments.size)
    ):
        raise ValueError("trace table and Fourier moments have incompatible shapes")
    if not np.isfinite(trace_table).all() or not np.isfinite(x_moments).all():
        raise ValueError("surface contraction has non-finite x data")
    if not np.isfinite(y_moments).all():
        raise ValueError("surface contraction has non-finite y data")
    if (
        not np.isfinite([hx, hy, h_component, phase_origin.real, phase_origin.imag]).all()
        or hx <= 0.0
        or hy <= 0.0
        or h_component <= 0.0
    ):
        raise ValueError("surface Jacobian/Piola scale is invalid")
    # This is the single covariant-Piola/surface-measure factor.  The caller
    # supplies h_component=hx for x or hy for y, exactly once.
    scale = (hx * hy / h_component) * phase_origin
    result = scale * np.einsum(
        "iab,a,b->i", trace_table, x_moments, y_moments, optimize=True
    )
    if not np.isfinite(result).all():
        raise ValueError("surface face functional contains non-finite values")
    return np.asarray(result, dtype=np.complex128)


def assemble_face_from_prevalidated_moments(
    trace_table: np.ndarray,
    x_moments: np.ndarray,
    y_moments: np.ndarray,
    *,
    hx: float,
    hy: float,
    h_component: float,
    phase_origin: complex,
) -> np.ndarray:
    """Hot contraction after the immutable table and moments were validated."""

    scale = (float(hx) * float(hy) / float(h_component)) * complex(phase_origin)
    return np.asarray(
        scale
        * np.einsum(
            "iab,a,b->i", trace_table, x_moments, y_moments, optimize=True
        ),
        dtype=np.complex128,
    )


def add_complex_mpc_cell_contribution(
    local_vector: np.ndarray,
    local_storage: np.ndarray,
    cell_dofs: Sequence[int],
    slave_rows: Sequence[int],
    master_rows_by_slave: Mapping[int, Sequence[int]],
    coefficients_by_slave: Mapping[int, Sequence[complex]],
) -> None:
    """Apply the qualified complex MPC cell-vector scatter in place.

    This mirrors ``dolfinx_mpc::modify_mpc_vec``: copy the already-oriented
    cell vector, add ``conj(coefficient)`` times each slave entry to its
    masters, zero that slave entry, then add the remaining cell vector to the
    local owned+ghost storage.  The caller performs reverse-add/forward-insert
    ghost updates after all local facets.
    """

    local_vector = np.asarray(local_vector, dtype=np.complex128).reshape(-1)
    local_storage = np.asarray(local_storage)
    cell_dofs = np.asarray(cell_dofs, dtype=np.int64).reshape(-1)
    if local_storage.ndim != 1 or not np.issubdtype(local_storage.dtype, np.complexfloating):
        raise ValueError("complex MPC scatter requires one complex local Vec array")
    if local_vector.size != cell_dofs.size or np.unique(cell_dofs).size != cell_dofs.size:
        raise ValueError("cell vector and unique local DOFs must have equal size")
    if cell_dofs.size and (cell_dofs.min() < 0 or cell_dofs.max() >= local_storage.size):
        raise ValueError("cell DOF lies outside owned+ghost local storage")
    if not np.isfinite(local_vector).all():
        raise ValueError("cell surface vector contains non-finite values")
    original = local_vector.copy()
    positions = {int(dof): index for index, dof in enumerate(cell_dofs)}
    for slave_value in slave_rows:
        slave = int(slave_value)
        if slave not in positions:
            raise ValueError("MPC cell slave is absent from the cell DOF map")
        masters = np.asarray(master_rows_by_slave.get(slave, ()), dtype=np.int64)
        coefficients = np.asarray(
            coefficients_by_slave.get(slave, ()), dtype=np.complex128
        )
        if masters.ndim != 1 or coefficients.ndim != 1 or masters.size != coefficients.size:
            raise ValueError("MPC master/coefficient rows are inconsistent")
        if masters.size == 0:
            raise ValueError("MPC slave row has no masters")
        if masters.size and (masters.min() < 0 or masters.max() >= local_storage.size):
            raise ValueError("MPC master lies outside owned+ghost local storage")
        if not np.isfinite(coefficients).all():
            raise ValueError("MPC coefficients contain non-finite values")
        slave_value_local = original[positions[slave]]
        for master, coefficient in zip(masters, coefficients, strict=True):
            local_storage[int(master)] += np.conjugate(coefficient) * slave_value_local
        local_vector[positions[slave]] = 0.0
    local_storage[cell_dofs] += local_vector


def add_prevalidated_complex_mpc_cell_contribution(
    local_vector: np.ndarray,
    local_storage: np.ndarray,
    cell_dofs: np.ndarray,
    slave_positions: np.ndarray,
    master_rows: Sequence[np.ndarray],
    coefficient_rows: Sequence[np.ndarray],
) -> None:
    """Hot-path MPC scatter using once-validated cell metadata."""

    original = local_vector.copy()
    for position, masters, coefficients in zip(
        slave_positions, master_rows, coefficient_rows, strict=True
    ):
        slave_value = original[int(position)]
        for master, coefficient in zip(masters, coefficients, strict=True):
            local_storage[int(master)] += np.conjugate(coefficient) * slave_value
        local_vector[int(position)] = 0.0
    local_storage[cell_dofs] += local_vector


def validate_boundary_mpc_row(
    slave: int,
    offsets: np.ndarray,
    coefficients: np.ndarray,
    is_slave: np.ndarray,
    masters: np.ndarray,
    local_storage_size: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Validate and freeze one actually used boundary MPC adjacency row.

    The global arrays remain in their native dtypes and are indexed only at
    ``slave``/``slave + 1`` and that row's masters. No global cast, diff, or
    finite scan is performed.
    """

    slave = int(slave)
    if (
        offsets.ndim != 1
        or not np.issubdtype(offsets.dtype, np.integer)
        or coefficients.ndim != 1
        or not np.issubdtype(coefficients.dtype, np.complexfloating)
        or is_slave.ndim != 1
        or not np.issubdtype(is_slave.dtype, np.integer)
        or masters.ndim != 1
        or not np.issubdtype(masters.dtype, np.integer)
        or slave < 0
        or slave >= is_slave.size
        or slave + 1 >= offsets.size
        or not bool(is_slave[slave])
        or masters.size == 0
    ):
        raise ValueError("boundary MPC slave/master row is malformed")
    start = int(offsets[slave])
    end = int(offsets[slave + 1])
    if start < 0 or end < start or end > coefficients.size:
        raise ValueError("boundary MPC offset pair is invalid")
    coefficient_row = coefficients[start:end]
    if end - start != masters.size or coefficient_row.size != masters.size:
        raise ValueError("boundary MPC master/coefficient counts differ")
    if not np.isfinite(coefficient_row).all():
        raise ValueError("boundary MPC coefficient row is non-finite")
    if (
        np.any(masters < 0)
        or np.any(masters >= int(local_storage_size))
        or np.any(masters >= is_slave.size)
    ):
        raise ValueError("boundary MPC master lies outside local storage")
    if np.any(is_slave[masters.astype(np.intp, copy=False)]):
        raise ValueError("boundary MPC master row contains a nested slave")
    master_row = np.array(masters, copy=True)
    coefficient_copy = np.array(coefficient_row, copy=True)
    master_row.flags.writeable = False
    coefficient_copy.flags.writeable = False
    return master_row, coefficient_copy


def relative_vector_defect(candidate: np.ndarray, reference: np.ndarray) -> tuple[float, float]:
    """Return finite absolute/relative defects; zero reference is exact-only."""

    candidate = np.asarray(candidate, dtype=np.complex128)
    reference = np.asarray(reference, dtype=np.complex128)
    if candidate.shape != reference.shape:
        raise ValueError("candidate and reference vector shapes differ")
    if not np.isfinite(candidate).all() or not np.isfinite(reference).all():
        raise ValueError("candidate/reference vector contains non-finite values")
    difference = candidate - reference
    if not np.isfinite(difference).all():
        raise ValueError("candidate/reference difference contains non-finite values")
    with np.errstate(over="ignore", invalid="ignore"):
        absolute = float(np.linalg.norm(difference.ravel()))
        reference_norm = float(np.linalg.norm(reference.ravel()))
    if not np.isfinite(absolute) or not np.isfinite(reference_norm):
        raise ValueError("candidate/reference norm is non-finite")
    if reference_norm == 0.0:
        if np.any(candidate != 0.0):
            return absolute, float("inf")
        return 0.0, 0.0
    return absolute, absolute / reference_norm


def significant_rows(
    rows: np.ndarray,
    values: np.ndarray,
    *,
    global_maximum: float,
    relative_tolerance: float = SURFACE_SUPPORT_RELATIVE_CUTOFF,
) -> tuple[np.ndarray, np.ndarray, float]:
    """Apply the existing global relative support cutoff without changing rows."""

    rows = np.asarray(rows, dtype=np.int64).reshape(-1)
    values = np.asarray(values, dtype=np.complex128).reshape(-1)
    global_maximum = float(global_maximum)
    relative_tolerance = float(relative_tolerance)
    if rows.shape != values.shape or np.unique(rows).size != rows.size:
        raise ValueError("surface row/value inventory is inconsistent")
    if not np.isfinite(values).all() or not np.isfinite(global_maximum):
        raise ValueError("surface support data contains non-finite values")
    if global_maximum < 0.0 or relative_tolerance < 0.0:
        raise ValueError("surface support cutoff parameters must be nonnegative")
    cutoff = max(1.0e-30, relative_tolerance * global_maximum)
    keep = np.abs(values) > cutoff
    return rows[keep].copy(), values[keep].copy(), cutoff


def apply_standard_dof_transform(
    element: object,
    local_vector: np.ndarray,
    cell_info: int,
    *,
    check_finite: bool = True,
) -> np.ndarray:
    """Apply the live DOLFINx element's standard cell transform once."""

    local_vector = np.ascontiguousarray(local_vector, dtype=np.complex128).reshape(-1)
    if check_finite and not np.isfinite(local_vector).all():
        raise ValueError("standard element transform input is non-finite")
    if not bool(getattr(element, "needs_dof_transformations", True)):
        return local_vector
    info = np.asarray([int(cell_info)], dtype=np.uint32)
    transform = getattr(element, "T_apply", None)
    if not callable(transform):
        raise NotImplementedError("live element has no standard T_apply transform")
    # Match the existing complex partial-assembly path: Basix transforms each
    # real scalar lane in the complex buffer, with vector block size two.
    transform(local_vector.view(np.float64), info, 2)
    if check_finite and not np.isfinite(local_vector).all():
        raise ValueError("standard element transform produced non-finite entries")
    return local_vector
