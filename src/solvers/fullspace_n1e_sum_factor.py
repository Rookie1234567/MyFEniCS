"""One opt-in sum-factorized local action for the actual Basix N1E hex element.

Basix 0.10 does not expose a tensor-product representation for the N1E
hexahedron element used by the physical runner.  The element nevertheless
publishes a coefficient matrix in the standard hexahedron Legendre polyset.
This module uses that published matrix to transform local N1E coefficients to
three tensor-product polynomial blocks, evaluates them with one-dimensional
Legendre tables, and projects the weighted result back through the transpose
coefficient map.  It owns only fixed per-batch work arrays; it never forms a
cell matrix or a mesh-sized tensor.
"""

from __future__ import annotations

import hashlib
import time
from typing import Any

import basix
from basix import polynomials
import numpy as np
from numpy.polynomial.legendre import Legendre


def _normalized_legendre_derivatives(points: np.ndarray, degree: int) -> np.ndarray:
    """Return d/dx of Basix's normalized interval Legendre basis on [0, 1]."""

    coordinate = 2.0 * np.asarray(points, dtype=np.float64) - 1.0
    return np.asarray(
        [
            2.0 * np.sqrt(2 * index + 1)
            * Legendre.basis(index).deriv()(coordinate)
            for index in range(int(degree) + 1)
        ],
        dtype=np.float64,
    )


class N1ESumFactorizedAction:
    """Apply one isotropic N1E cell action with fixed batch workspace."""

    def __init__(self, space: Any, basis: Any, *, batch_size: int) -> None:
        batch_size = int(batch_size)
        if batch_size < 1:
            raise ValueError("sum-factorized batch_size must be positive")
        self.batch_size = batch_size
        element = space.element.basix_element
        if (
            element.family != basix.ElementFamily.N1E
            or element.cell_type != basix.CellType.hexahedron
            or element.map_type != basix.MapType.covariantPiola
            or element.polyset_type != basix.PolysetType.standard
            or int(element.value_size) != 3
        ):
            raise NotImplementedError(
                "sum-factorized action requires the actual standard N1E hex element"
            )
        degree = int(element.embedded_superdegree)
        if int(element.degree) != degree or degree < 1:
            raise NotImplementedError(
                "sum-factorized action requires degree == embedded superdegree"
            )
        points = np.asarray(getattr(basis, "points"), dtype=np.float64)
        weights = np.asarray(basis.weights, dtype=np.float64)
        if points.ndim != 2 or points.shape[1] != 3 or len(points) != len(weights):
            raise ValueError("quadrature points and weights have incompatible shapes")
        axes = tuple(np.unique(points[:, axis]) for axis in range(3))
        shape = tuple(len(axis) for axis in axes)
        if int(np.prod(shape)) != len(points):
            raise NotImplementedError("quadrature is not a full tensor product")
        axis_indices = np.column_stack(
            [np.searchsorted(axes[axis], points[:, axis]) for axis in range(3)]
        )
        natural_indices = np.ravel_multi_index(axis_indices.T, shape)
        if len(np.unique(natural_indices)) != len(points):
            raise NotImplementedError("quadrature tensor-product indices are not unique")
        reconstructed = np.column_stack(
            [axes[axis][axis_indices[:, axis]] for axis in range(3)]
        )
        if not np.allclose(reconstructed, points, rtol=0.0, atol=2.0e-14):
            raise NotImplementedError("quadrature tensor-product coordinates changed")
        natural_to_input = np.empty(len(points), dtype=np.int64)
        natural_to_input[natural_indices] = np.arange(len(points), dtype=np.int64)
        input_to_natural = np.empty(len(points), dtype=np.int64)
        input_to_natural[natural_to_input] = np.arange(len(points), dtype=np.int64)

        coefficient_matrix = np.ascontiguousarray(
            basis.coefficient_matrix, dtype=np.float64
        )
        polynomial_dimension = (degree + 1) ** 3
        expected_shape = (int(element.dim), 3 * polynomial_dimension)
        if coefficient_matrix.shape != expected_shape:
            raise NotImplementedError(
                "actual N1E coefficient matrix is not a 3-block hexahedron polyset"
            )
        if not np.all(np.isfinite(coefficient_matrix)):
            raise ValueError("N1E coefficient matrix contains non-finite values")
        coefficient_matrix.flags.writeable = False

        values_1d = []
        derivatives_1d = []
        for axis in axes:
            axis_points = np.ascontiguousarray(axis[:, None], dtype=np.float64)
            values = np.asarray(
                polynomials.tabulate_polynomials(
                    basix.PolynomialType.legendre,
                    basix.CellType.interval,
                    degree,
                    axis_points,
                ),
                dtype=np.float64,
            )
            derivatives = _normalized_legendre_derivatives(axis, degree)
            if values.shape != (degree + 1, len(axis)):
                raise RuntimeError("Basix interval Legendre table has an unexpected shape")
            # Basix returns (polynomial, quadrature); contractions below use
            # (quadrature, polynomial).
            values_1d.append(np.ascontiguousarray(values.T))
            derivatives_1d.append(np.ascontiguousarray(derivatives.T))

        tensor_points_upper_bound = int(
            np.prod([max(len(axis), degree + 1) for axis in axes])
        )
        temporary_einsum_bytes = int(
            3 * self.batch_size * max(shape) * (degree + 1) ** 2 * 16
            + self.batch_size * len(points) * 3 * 16
        )
        # Bound live local intermediates by lifecycle rather than summing all
        # historical allocations: gather/reordered coefficients, metric
        # products for both terms, projection differences, materials, and a
        # possible BLAS copy of the transposed real coefficient operand.
        temporary_local_bytes = int(
            16 * (
                2 * self.batch_size * int(element.dim)
                + 6 * self.batch_size * tensor_points_upper_bound * 3
                + 6 * self.batch_size * 3 * polynomial_dimension
                + 2 * self.batch_size
            )
            + coefficient_matrix.nbytes
        )

        self.space = space
        self.element = element
        self.degree = degree
        self.polynomial_dimension = polynomial_dimension
        self.batch_size = int(batch_size)
        self.shape = shape
        self.points = points
        # Keep FFCx's native point order for metric multiplication.  The
        # field conversion helpers alone cross the natural tensor ordering.
        self.weights = np.ascontiguousarray(weights)
        self.natural_to_input = natural_to_input
        self.input_to_natural = input_to_natural
        self.coefficient_matrix = coefficient_matrix
        self.values_1d = tuple(values_1d)
        self.derivatives_1d = tuple(derivatives_1d)
        self._poly = np.empty(
            (self.batch_size, 3, polynomial_dimension), dtype=np.complex128
        )
        self._values = np.empty(
            (self.batch_size, len(points), 3), dtype=np.complex128
        )
        self._curls = np.empty_like(self._values)
        self._flux = np.empty_like(self._values)
        self._curl_flux = np.empty_like(self._values)
        self._derivatives = np.empty(
            (self.batch_size, len(points), 3, 3), dtype=np.complex128
        )
        self._poly_result = np.empty_like(self._poly)
        self._result = np.empty(
            (self.batch_size, int(element.dim)), dtype=np.complex128
        )
        # These four contiguous real arrays are reused for both coefficient
        # transforms.  They avoid stride-2 complex views as BLAS operands and
        # avoid promoting the real coefficient matrix to a complex temporary.
        self._coefficient_real_work = np.empty(
            (self.batch_size, int(element.dim)), dtype=np.float64
        )
        self._coefficient_imag_work = np.empty_like(self._coefficient_real_work)
        self._polynomial_real_work = np.empty(
            (self.batch_size, 3 * polynomial_dimension), dtype=np.float64
        )
        self._polynomial_imag_work = np.empty_like(self._polynomial_real_work)
        self.timing = {
            "coefficient_transform": 0.0,
            "reference_forward": 0.0,
            "metric": 0.0,
            "reference_backward": 0.0,
        }
        self.audit = {
            "backend": "isotropic_sum_factorized_n1e_v26",
            "element_family": element.family.name,
            "element_variant": getattr(
                getattr(element, "lagrange_variant", None), "name", "unknown"
            ),
            "map_type": element.map_type.name,
            "polyset_type": element.polyset_type.name,
            "degree": degree,
            "embedded_superdegree": int(element.embedded_superdegree),
            "element_dimension": int(element.dim),
            "coefficient_matrix_shape": list(coefficient_matrix.shape),
            "coefficient_matrix_bytes": int(coefficient_matrix.nbytes),
            "coefficient_matrix_sha256": hashlib.sha256(
                coefficient_matrix.tobytes()
            ).hexdigest(),
            "quadrature_points": len(points),
            "quadrature_shape": list(shape),
            "quadrature_order": "actual_points_to_tensor_grid_checked",
            "quadrature_weights_sha256": hashlib.sha256(
                weights.tobytes()
            ).hexdigest(),
            "one_dimensional_reference_tables_bytes": int(
                sum(values.nbytes + derivatives.nbytes
                    for values, derivatives in zip(values_1d, derivatives_1d, strict=True))
            ),
            "batch_workspace_bytes": int(
                sum(array.nbytes for array in (
                    self._poly,
                    self._values,
                    self._curls,
                    self._flux,
                    self._curl_flux,
                    self._derivatives,
                    self._poly_result,
                    self._result,
                    self._coefficient_real_work,
                    self._coefficient_imag_work,
                    self._polynomial_real_work,
                    self._polynomial_imag_work,
                ))
            ),
            "temporary_einsum_workspace_upper_bound_bytes": temporary_einsum_bytes,
            "temporary_local_intermediate_upper_bound_bytes": temporary_local_bytes,
            "temporary_workspace_upper_bound_bytes": int(
                temporary_einsum_bytes + temporary_local_bytes
            ),
            "workspace_scope": "one fixed local batch; no global matrix or cell tensor",
            "native_tensor_product_api": bool(element.has_tensor_product_factorisation),
            "coefficient_transform_real_imag": True,
        }

    @staticmethod
    def _evaluate(
        coefficients: np.ndarray,
        x_table: np.ndarray,
        y_table: np.ndarray,
        z_table: np.ndarray,
    ) -> np.ndarray:
        first = np.einsum("xi,bijk->bxjk", x_table, coefficients, optimize=True)
        second = np.einsum("yj,bxjk->bxyk", y_table, first, optimize=True)
        result = np.einsum("zk,bxyk->bxyz", z_table, second, optimize=True)
        return result.reshape(
            coefficients.shape[0],
            x_table.shape[0] * y_table.shape[0] * z_table.shape[0],
        )

    @staticmethod
    def _project(
        values: np.ndarray,
        x_table: np.ndarray,
        y_table: np.ndarray,
        z_table: np.ndarray,
    ) -> np.ndarray:
        first = np.einsum("bxyz,zk->bxyk", values, z_table, optimize=True)
        second = np.einsum("bxyk,yj->bxjk", first, y_table, optimize=True)
        return np.einsum("bxjk,xi->bijk", second, x_table, optimize=True).reshape(
            values.shape[0],
            (x_table.shape[1] * y_table.shape[1] * z_table.shape[1]),
        )

    def _field_from_polynomial(self, coefficients: np.ndarray, tables) -> np.ndarray:
        natural = self._evaluate(coefficients, *tables)
        return natural[:, self.input_to_natural]

    def _polynomial_from_field(self, values: np.ndarray, tables) -> np.ndarray:
        natural = values[:, self.natural_to_input].reshape(
            values.shape[0], *self.shape
        )
        return self._project(natural, *tables)

    def apply(
        self,
        local: np.ndarray,
        metrics: np.ndarray,
        materials: np.ndarray,
        *,
        component: str | None = None,
    ) -> np.ndarray:
        """Apply ``curl_coefficient*curl^H curl + mass_coefficient*mass``."""

        local = np.asarray(local, dtype=np.complex128)
        metrics = np.asarray(metrics, dtype=np.float64)
        materials = np.asarray(materials, dtype=np.complex128)
        count = int(local.shape[0])
        if (
            local.ndim != 2
            or local.shape[1] != self.coefficient_matrix.shape[0]
            or count > self.batch_size
            or metrics.shape != (count, 2, 3, 3)
            or materials.shape != (count, 2)
            or component not in (None, "curl", "mass")
        ):
            raise ValueError("sum-factorized local action has incompatible inputs")
        started = time.perf_counter()
        # C is real.  Transforming the real and imaginary parts separately
        # keeps the real coefficient matrix from being promoted or copied to
        # a full complex temporary on every batch.
        coefficient_real = self._coefficient_real_work[:count]
        coefficient_imag = self._coefficient_imag_work[:count]
        polynomial_real = self._polynomial_real_work[:count]
        polynomial_imag = self._polynomial_imag_work[:count]
        np.copyto(coefficient_real, local.real)
        np.copyto(coefficient_imag, local.imag)
        np.matmul(coefficient_real, self.coefficient_matrix, out=polynomial_real)
        np.matmul(coefficient_imag, self.coefficient_matrix, out=polynomial_imag)
        polynomial_work = self._poly[:count].reshape(count, -1)
        np.copyto(polynomial_work.real, polynomial_real)
        np.copyto(polynomial_work.imag, polynomial_imag)
        self.timing["coefficient_transform"] += time.perf_counter() - started
        polynomial = self._poly[:count].reshape(
            count, 3, self.degree + 1, self.degree + 1, self.degree + 1
        )
        started = time.perf_counter()
        if component != "curl":
            for vector_component in range(3):
                self._values[:count, :, vector_component] = self._field_from_polynomial(
                    polynomial[:, vector_component], self.values_1d
                )
        if component != "mass":
            # Only the six cross derivatives entering curl are evaluated.
            # The diagonal derivatives never enter the H(curl) curl and are
            # deliberately left out of this opt-in path.
            dx = (self.derivatives_1d[0], self.values_1d[1], self.values_1d[2])
            dy = (self.values_1d[0], self.derivatives_1d[1], self.values_1d[2])
            dz = (self.values_1d[0], self.values_1d[1], self.derivatives_1d[2])
            derivatives = self._derivatives[:count]
            derivatives[:, :, 1, 2] = self._field_from_polynomial(
                polynomial[:, 1], dz
            )
            derivatives[:, :, 2, 1] = self._field_from_polynomial(
                polynomial[:, 2], dy
            )
            derivatives[:, :, 0, 2] = self._field_from_polynomial(
                polynomial[:, 0], dz
            )
            derivatives[:, :, 2, 0] = self._field_from_polynomial(
                polynomial[:, 2], dx
            )
            derivatives[:, :, 1, 0] = self._field_from_polynomial(
                polynomial[:, 1], dx
            )
            derivatives[:, :, 0, 1] = self._field_from_polynomial(
                polynomial[:, 0], dy
            )
            self._curls[:count, :, 0] = (
                derivatives[:, :, 2, 1] - derivatives[:, :, 1, 2]
            )
            self._curls[:count, :, 1] = (
                derivatives[:, :, 0, 2] - derivatives[:, :, 2, 0]
            )
            self._curls[:count, :, 2] = (
                derivatives[:, :, 1, 0] - derivatives[:, :, 0, 1]
            )
        self.timing["reference_forward"] += time.perf_counter() - started

        started = time.perf_counter()
        self._flux[:count] = 0.0
        self._curl_flux[:count] = 0.0
        weights = self.weights[None, :, None]
        if component != "curl":
            mass_flux = np.einsum(
                "bqc,bcd->bqd", self._values[:count], metrics[:, 0], optimize=True
            )
            self._flux[:count] += mass_flux * materials[:, 0, None, None] * weights
        if component != "mass":
            curl_flux = np.einsum(
                "bqc,bcd->bqd", self._curls[:count], metrics[:, 1], optimize=True
            )
            self._curl_flux[:count] = (
                curl_flux * materials[:, 1, None, None] * weights
            )
        self.timing["metric"] += time.perf_counter() - started

        started = time.perf_counter()
        self._poly_result[:count] = 0.0
        for vector_component in range(3):
            if component != "curl":
                self._poly_result[:count, vector_component] += (
                    self._polynomial_from_field(
                        self._flux[:count, :, vector_component], self.values_1d
                    )
                )
        if component != "mass":
            fx = self._curl_flux[:count, :, 0]
            fy = self._curl_flux[:count, :, 1]
            fz = self._curl_flux[:count, :, 2]
            self._poly_result[:count, 0] += (
                self._polynomial_from_field(
                    fy,
                    (self.values_1d[0], self.values_1d[1], self.derivatives_1d[2]),
                )
                - self._polynomial_from_field(
                    fz,
                    (self.values_1d[0], self.derivatives_1d[1], self.values_1d[2]),
                )
            )
            self._poly_result[:count, 1] += (
                self._polynomial_from_field(
                    fz,
                    (self.derivatives_1d[0], self.values_1d[1], self.values_1d[2]),
                )
                - self._polynomial_from_field(
                    fx,
                    (self.values_1d[0], self.values_1d[1], self.derivatives_1d[2]),
                )
            )
            self._poly_result[:count, 2] += (
                self._polynomial_from_field(
                    fx,
                    (self.values_1d[0], self.derivatives_1d[1], self.values_1d[2]),
                )
                - self._polynomial_from_field(
                    fy,
                    (self.derivatives_1d[0], self.values_1d[1], self.values_1d[2]),
                )
            )
        polynomial_result = self._poly_result[:count].reshape(count, -1)
        np.copyto(polynomial_real, polynomial_result.real)
        np.copyto(polynomial_imag, polynomial_result.imag)
        np.matmul(
            polynomial_real,
            self.coefficient_matrix.T,
            out=coefficient_real,
        )
        np.matmul(
            polynomial_imag,
            self.coefficient_matrix.T,
            out=coefficient_imag,
        )
        np.copyto(self._result[:count].real, coefficient_real)
        np.copyto(self._result[:count].imag, coefficient_imag)
        self.timing["reference_backward"] += time.perf_counter() - started
        return self._result[:count]
