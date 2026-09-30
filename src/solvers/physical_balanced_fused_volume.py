"""Explicit opt-in tensor-product physical volume action prototype.

This prototype keeps the Task041 UFL/MPC action as its oracle.  It applies
the isotropic curl and mass integrals with bounded cell batches, one local
coefficient gather, one Basix orientation transform in each direction, and
one shared coefficient/polynomial transform pair.  It never forms a cell
matrix or a mesh-sized field tensor.  The external DtN action is deliberately
left to ``_FullSpacePhysicalAction``.
"""

from __future__ import annotations

import hashlib
from typing import Any

import basix
import ffcx.analysis
import numpy as np
import ufl
from basix import polynomials
from ffcx.element_interface import create_quadrature
from numpy.polynomial.legendre import Legendre
from petsc4py import PETSc

from .physical_balanced_mpc_action import FullspaceMpcFormAction
from .physical_balanced_positive_kernel import (
    _cell_jacobians,
    _validate_affine_cell_jacobians,
)


def _normalized_legendre_derivatives(points: np.ndarray, degree: int) -> np.ndarray:
    coordinate = 2.0 * np.asarray(points, dtype=np.float64) - 1.0
    return np.asarray(
        [
            2.0 * np.sqrt(2 * index + 1) * Legendre.basis(index).deriv()(coordinate)
            for index in range(int(degree) + 1)
        ],
        dtype=np.float64,
    )


class _TensorProductRule:
    """FFCx-derived quadrature and 1D Legendre tables for one integral."""

    def __init__(
        self,
        space: Any,
        form: Any,
        *,
        expected_rule: str,
        expected_degree: int,
    ) -> None:
        dof_element = space.element
        element = dof_element.basix_element
        analysis = ffcx.analysis.analyze_ufl_objects([form], np.dtype(PETSc.ScalarType))
        data = analysis.form_data[0]
        integrals = [
            integral for group in data.integral_data for integral in group.integrals
        ]
        if len(integrals) != 1 or integrals[0].integral_type() != "cell":
            raise NotImplementedError(
                "the fused volume prototype requires one cell-rule probe"
            )
        metadata = integrals[0].metadata()
        rule = str(metadata["quadrature_rule"])
        degree = int(metadata["quadrature_degree"])
        if (rule, degree) != (str(expected_rule), int(expected_degree)):
            raise ValueError("probe form differs from the original volume rule")
        if rule in ("custom", "vertex"):
            raise NotImplementedError(
                "the fused volume prototype requires tensor-product quadrature"
            )

        points, input_weights = create_quadrature(
            "hexahedron", degree, rule, data.argument_elements
        )
        points = np.asarray(points, dtype=np.float64)
        input_weights = np.asarray(input_weights, dtype=np.float64)
        axes = tuple(np.unique(points[:, axis]) for axis in range(3))
        shape = tuple(int(axis.size) for axis in axes)
        if int(np.prod(shape)) != len(points):
            raise NotImplementedError(
                "the original hexahedron quadrature is not a tensor product"
            )
        axis_indices = np.column_stack(
            [np.searchsorted(axes[axis], points[:, axis]) for axis in range(3)]
        )
        natural_indices = np.ravel_multi_index(axis_indices.T, shape)
        reconstructed = np.column_stack(
            [axes[axis][axis_indices[:, axis]] for axis in range(3)]
        )
        if len(np.unique(natural_indices)) != len(points) or not np.allclose(
            reconstructed, points, rtol=0.0, atol=2.0e-14
        ):
            raise NotImplementedError(
                "the original quadrature points do not form a regular tensor grid"
            )
        weights = np.empty_like(input_weights)
        weights[natural_indices] = input_weights

        polynomial_degree = int(element.embedded_superdegree)
        values_1d = []
        derivatives_1d = []
        for axis in axes:
            axis_points = np.ascontiguousarray(axis[:, None], dtype=np.float64)
            values = np.asarray(
                polynomials.tabulate_polynomials(
                    basix.PolynomialType.legendre,
                    basix.CellType.interval,
                    polynomial_degree,
                    axis_points,
                ),
                dtype=np.float64,
            )
            if values.shape != (polynomial_degree + 1, len(axis)):
                raise RuntimeError("Basix returned an unexpected 1D table")
            values_1d.append(np.ascontiguousarray(values.T))
            derivatives_1d.append(
                np.ascontiguousarray(
                    _normalized_legendre_derivatives(axis, polynomial_degree).T
                )
            )

        geometry_element = basix.create_element(
            basix.ElementFamily.P,
            basix.CellType.hexahedron,
            1,
            basix.LagrangeVariant.equispaced,
        )
        geometry_derivatives = geometry_element.tabulate(1, points)[1:, :, :, 0]
        self.shape = shape
        self.weights = np.ascontiguousarray(weights.reshape(shape))
        self.values_1d = tuple(values_1d)
        self.derivatives_1d = tuple(derivatives_1d)
        self.geometry_derivatives = np.ascontiguousarray(geometry_derivatives)
        self.rule = rule
        self.degree = degree
        self.points_sha256 = hashlib.sha256(points.tobytes()).hexdigest()
        self.weights_sha256 = hashlib.sha256(weights.tobytes()).hexdigest()


class Task041FusedPhysicalVolumeKernel:
    """Complex isotropic curl-plus-mass volume action for affine Q1 hexes."""

    batch_size = 2

    def __init__(
        self,
        *,
        space: Any,
        cell_tags: Any,
        cfg: Any,
        curl_rule: _TensorProductRule,
        mass_rule: _TensorProductRule,
    ) -> None:
        dof_element = space.element
        element = dof_element.basix_element
        mesh = space.mesh
        if (
            np.dtype(PETSc.ScalarType) != np.dtype(np.complex128)
            or element.family != basix.ElementFamily.N1E
            or element.cell_type != basix.CellType.hexahedron
            or element.map_type != basix.MapType.covariantPiola
            or element.polyset_type != basix.PolysetType.standard
            or int(element.degree) != int(element.embedded_superdegree)
            or int(space.dofmap.index_map_bs) != 1
            or mesh.geometry.cmap.degree != 1
            or mesh.geometry.dim != 3
        ):
            raise NotImplementedError(
                "the prototype requires complex N1E on affine Q1 hexes"
            )
        if bool(cfg.use_pml) or float(cfg.divergence_penalty) != 0.0:
            raise NotImplementedError(
                "PML and divergence-penalty terms are outside this volume slice"
            )

        self.space = space
        self.element = dof_element
        self.basix_element = element
        self.polynomial_degree = int(element.embedded_superdegree)
        width = self.polynomial_degree + 1
        polynomial_dimension = 3 * width**3
        coefficient_matrix = np.ascontiguousarray(
            np.asarray(element.coefficient_matrix, dtype=np.float64)
        )
        if coefficient_matrix.shape != (int(element.dim), polynomial_dimension):
            raise NotImplementedError(
                "N1E coefficient transform does not match three tensor blocks"
            )
        if not np.all(np.isfinite(coefficient_matrix)):
            raise ValueError("N1E coefficient transform must be finite")
        coefficient_matrix.flags.writeable = False
        self.coefficient_matrix = coefficient_matrix

        owned_cells = int(mesh.topology.index_map(mesh.topology.dim).size_local)
        local_dofs = int(element.dim)
        mesh.topology.create_entity_permutations()
        self.permutations = np.ascontiguousarray(
            mesh.topology.get_cell_permutation_info(), dtype=np.uint32
        )
        self.dofs = np.asarray(
            [space.dofmap.cell_dofs(cell) for cell in range(owned_cells)],
            dtype=np.int32,
        ).reshape(owned_cells, local_dofs)
        self.cell_tags = self._owned_cell_tags(cell_tags, owned_cells)

        tag_ids = {
            int(cfg.tags.air): complex(cfg.eps_r),
            int(cfg.tags.substrate): complex(cfg.substrate_index) ** 2,
            int(cfg.tags.grating): complex(cfg.grating_index) ** 2,
        }
        unknown_tags = sorted(set(self.cell_tags.tolist()) - set(tag_ids))
        if unknown_tags:
            raise NotImplementedError(
                f"non-isotropic cell tags are outside this prototype: {unknown_tags}"
            )
        self.curl_coefficient = complex(PETSc.ScalarType(1.0 / cfg.mu_r))
        self.mass_coefficients = np.asarray(
            [
                PETSc.ScalarType(-(cfg.k0**2) * tag_ids[int(tag)])
                for tag in self.cell_tags
            ],
            dtype=np.complex128,
        )
        if (
            not np.isfinite(self.curl_coefficient.real)
            or not np.isfinite(self.curl_coefficient.imag)
            or not np.all(np.isfinite(self.mass_coefficients.real))
            or not np.all(np.isfinite(self.mass_coefficients.imag))
        ):
            raise ValueError("physical material coefficients must be finite")

        self.curl_rule = curl_rule
        self.mass_rule = mass_rule
        self.curl_metrics = np.empty((owned_cells, 3, 3), dtype=np.float64)
        self.mass_metrics = np.empty_like(self.curl_metrics)
        for cell in range(owned_cells):
            coordinates = mesh.geometry.x[mesh.geometry.dofmap[cell]]
            jacobians = _cell_jacobians(curl_rule.geometry_derivatives, coordinates)
            jacobian, determinant = _validate_affine_cell_jacobians(jacobians)
            inverse = np.linalg.inv(jacobian)
            self.mass_metrics[cell] = inverse @ inverse.T * determinant
            self.curl_metrics[cell] = jacobian.T @ jacobian / determinant

        self.max_quadrature_shape = tuple(
            max(curl_rule.shape[axis], mass_rule.shape[axis]) for axis in range(3)
        )
        qx, qy, qz = self.max_quadrature_shape
        batch = self.batch_size
        self._local = np.empty((batch, local_dofs), dtype=np.complex128)
        self._polynomial = np.empty(
            (batch, 3, width, width, width), dtype=np.complex128
        )
        self._polynomial_result = np.empty_like(self._polynomial)
        self._result = np.empty_like(self._local)
        self._coefficient_real = np.empty((batch, local_dofs), dtype=np.float64)
        self._coefficient_imag = np.empty_like(self._coefficient_real)
        self._polynomial_real = np.empty(
            (batch, polynomial_dimension), dtype=np.float64
        )
        self._polynomial_imag = np.empty_like(self._polynomial_real)
        self._field = np.empty((batch, qx, qy, qz, 3), dtype=np.complex128)
        self._curl = np.empty_like(self._field)
        self._flux = np.empty_like(self._field)
        self._scalar = np.empty((batch, qx, qy, qz), dtype=np.complex128)
        self._forward_first = np.empty((batch, width, width, qz), dtype=np.complex128)
        self._forward_second = np.empty((batch, width, qy, qz), dtype=np.complex128)
        self._backward_first = np.empty((batch, qx, qy, width), dtype=np.complex128)
        self._backward_second = np.empty((batch, qx, width, width), dtype=np.complex128)
        self._polynomial_term = np.empty(
            (batch, width, width, width), dtype=np.complex128
        )
        self._curl_coefficients = np.full(
            batch, self.curl_coefficient, dtype=np.complex128
        )
        self._destroyed = False
        self.audit = {
            "backend": "task041_opt_in_sum_factorized_physical_volume",
            "curl_integral": {
                "rule": curl_rule.rule,
                "degree": curl_rule.degree,
                "points_sha256": curl_rule.points_sha256,
                "weights_sha256": curl_rule.weights_sha256,
            },
            "mass_integral": {
                "rule": mass_rule.rule,
                "degree": mass_rule.degree,
                "points_sha256": mass_rule.points_sha256,
                "weights_sha256": mass_rule.weights_sha256,
            },
            "shared_cell_gather_and_orientation": True,
            "shared_coefficient_forward_and_backward": True,
            "full_cell_matrix_materialized": False,
            "mesh_sized_field_tensor_materialized": False,
            "batch_size": int(batch),
            "owned_cells": int(owned_cells),
            "apply_count": 0,
            "batch_workspace_bytes": int(
                sum(
                    array.nbytes
                    for array in (
                        self._local,
                        self._polynomial,
                        self._polynomial_result,
                        self._result,
                        self._coefficient_real,
                        self._coefficient_imag,
                        self._polynomial_real,
                        self._polynomial_imag,
                        self._field,
                        self._curl,
                        self._flux,
                        self._scalar,
                        self._forward_first,
                        self._forward_second,
                        self._backward_first,
                        self._backward_second,
                        self._polynomial_term,
                        self._curl_coefficients,
                    )
                )
            ),
            "cell_metadata_bytes": int(
                sum(
                    array.nbytes
                    for array in (
                        self.dofs,
                        self.permutations,
                        self.cell_tags,
                        self.curl_metrics,
                        self.mass_metrics,
                        self.mass_coefficients,
                    )
                )
            ),
            "reference_bytes": int(
                coefficient_matrix.nbytes
                + self._rule_bytes(curl_rule)
                + self._rule_bytes(mass_rule)
            ),
        }

    @staticmethod
    def _owned_cell_tags(cell_tags: Any, owned_cells: int) -> np.ndarray:
        result = np.full(int(owned_cells), -1, dtype=np.int32)
        indices = np.asarray(cell_tags.indices, dtype=np.int64)
        values = np.asarray(cell_tags.values, dtype=np.int32)
        if indices.shape != values.shape:
            raise ValueError("cell-tag indices and values do not align")
        for cell, tag in zip(indices.tolist(), values.tolist(), strict=True):
            if 0 <= int(cell) < int(owned_cells):
                if result[int(cell)] != -1:
                    raise ValueError("owned cell has multiple material tags")
                result[int(cell)] = int(tag)
        if np.any(result < 0):
            raise ValueError("every owned physical cell needs one material tag")
        return result

    @staticmethod
    def _rule_bytes(rule: _TensorProductRule) -> int:
        return int(
            rule.weights.nbytes
            + rule.geometry_derivatives.nbytes
            + sum(array.nbytes for array in rule.values_1d)
            + sum(array.nbytes for array in rule.derivatives_1d)
        )

    def _forward_scalar(
        self,
        coefficients: np.ndarray,
        tables: tuple[np.ndarray, np.ndarray, np.ndarray],
        output: np.ndarray,
    ) -> None:
        count = int(coefficients.shape[0])
        x_table, y_table, z_table = tables
        qx, qy, qz = int(x_table.shape[0]), int(y_table.shape[0]), int(z_table.shape[0])
        first = self._forward_first[:count, :, :, :qz]
        second = self._forward_second[:count, :, :qy, :qz]
        np.einsum("bijk,zk->bijz", coefficients, z_table, out=first, optimize=True)
        np.einsum("bijz,yj->biyz", first, y_table, out=second, optimize=True)
        np.einsum(
            "biyz,xi->bxyz",
            second,
            x_table,
            out=output[:count, :qx, :qy, :qz],
            optimize=True,
        )

    def _backward_scalar(
        self,
        field: np.ndarray,
        tables: tuple[np.ndarray, np.ndarray, np.ndarray],
        output: np.ndarray,
    ) -> None:
        count = int(field.shape[0])
        x_table, y_table, z_table = tables
        qx, qy = int(x_table.shape[0]), int(y_table.shape[0])
        first = self._backward_first[:count, :qx, :qy, :]
        second = self._backward_second[:count, :qx, :, :]
        np.einsum("bxyz,zk->bxyk", field, z_table, out=first, optimize=True)
        np.einsum("bxyk,yj->bxjk", first, y_table, out=second, optimize=True)
        np.einsum("bxjk,xi->bijk", second, x_table, out=output, optimize=True)

    def _evaluate_vector(
        self, polynomial: np.ndarray, rule: _TensorProductRule
    ) -> np.ndarray:
        count = int(polynomial.shape[0])
        qx, qy, qz = rule.shape
        field = self._field[:count, :qx, :qy, :qz, :]
        for component in range(3):
            self._forward_scalar(
                polynomial[:, component],
                rule.values_1d,
                self._scalar[:count, :qx, :qy, :qz],
            )
            np.copyto(field[..., component], self._scalar[:count, :qx, :qy, :qz])
        return field

    def _evaluate_curl(
        self, polynomial: np.ndarray, rule: _TensorProductRule
    ) -> np.ndarray:
        count = int(polynomial.shape[0])
        qx, qy, qz = rule.shape
        curl = self._curl[:count, :qx, :qy, :qz, :]
        values = rule.values_1d
        derivatives = rule.derivatives_1d
        # curl_x = d_y E_z - d_z E_y
        self._forward_scalar(
            polynomial[:, 2],
            (values[0], derivatives[1], values[2]),
            self._scalar[:count, :qx, :qy, :qz],
        )
        np.copyto(curl[..., 0], self._scalar[:count, :qx, :qy, :qz])
        self._forward_scalar(
            polynomial[:, 1],
            (values[0], values[1], derivatives[2]),
            self._scalar[:count, :qx, :qy, :qz],
        )
        curl[..., 0] -= self._scalar[:count, :qx, :qy, :qz]
        # curl_y = d_z E_x - d_x E_z
        self._forward_scalar(
            polynomial[:, 0],
            (values[0], values[1], derivatives[2]),
            self._scalar[:count, :qx, :qy, :qz],
        )
        np.copyto(curl[..., 1], self._scalar[:count, :qx, :qy, :qz])
        self._forward_scalar(
            polynomial[:, 2],
            (derivatives[0], values[1], values[2]),
            self._scalar[:count, :qx, :qy, :qz],
        )
        curl[..., 1] -= self._scalar[:count, :qx, :qy, :qz]
        # curl_z = d_x E_y - d_y E_x
        self._forward_scalar(
            polynomial[:, 1],
            (derivatives[0], values[1], values[2]),
            self._scalar[:count, :qx, :qy, :qz],
        )
        np.copyto(curl[..., 2], self._scalar[:count, :qx, :qy, :qz])
        self._forward_scalar(
            polynomial[:, 0],
            (values[0], derivatives[1], values[2]),
            self._scalar[:count, :qx, :qy, :qz],
        )
        curl[..., 2] -= self._scalar[:count, :qx, :qy, :qz]
        return curl

    def _weighted_flux(
        self,
        field: np.ndarray,
        metrics: np.ndarray,
        coefficients: np.ndarray,
        rule: _TensorProductRule,
    ) -> np.ndarray:
        count = int(field.shape[0])
        qx, qy, qz = rule.shape
        flux = self._flux[:count, :qx, :qy, :qz, :]
        np.einsum(
            "bxyzc,bcd->bxyzd",
            field,
            metrics,
            out=flux,
            optimize=True,
        )
        flux *= coefficients[:, None, None, None, None]
        flux *= rule.weights[None, :, :, :, None]
        return flux

    def _project_add(
        self,
        destination: np.ndarray,
        field: np.ndarray,
        tables: tuple[np.ndarray, np.ndarray, np.ndarray],
        *,
        sign: float = 1.0,
    ) -> None:
        count = int(field.shape[0])
        term = self._polynomial_term[:count]
        self._backward_scalar(field, tables, term)
        if sign == 1.0:
            destination += term
        else:
            destination -= term

    def apply(self, coefficients: np.ndarray, output: np.ndarray) -> None:
        if self._destroyed:
            raise RuntimeError("fused physical volume kernel has been destroyed")
        if np.dtype(coefficients.dtype) != np.dtype(np.complex128):
            raise TypeError("fused physical volume input must be complex128")
        owned_cells = int(self.dofs.shape[0])
        width = self.polynomial_degree + 1
        coefficient_matrix = self.coefficient_matrix
        polynomial_size = int(coefficient_matrix.shape[1])
        for start in range(0, owned_cells, self.batch_size):
            stop = min(start + self.batch_size, owned_cells)
            count = stop - start
            dofs = self.dofs[start:stop]
            local = self._local[:count]
            np.take(coefficients, dofs, axis=0, out=local)
            for row, cell in enumerate(range(start, stop)):
                if self.element.needs_dof_transformations:
                    self.element.Tt_apply(
                        local[row].view(np.float64),
                        self.permutations[cell : cell + 1],
                        2,
                    )

            polynomial = self._polynomial[:count]
            self._coefficient_real[:count] = local.real
            self._coefficient_imag[:count] = local.imag
            np.matmul(
                self._coefficient_real[:count],
                coefficient_matrix,
                out=self._polynomial_real[:count],
            )
            np.matmul(
                self._coefficient_imag[:count],
                coefficient_matrix,
                out=self._polynomial_imag[:count],
            )
            np.copyto(
                polynomial.real,
                self._polynomial_real[:count].reshape(count, 3, width, width, width),
            )
            np.copyto(
                polynomial.imag,
                self._polynomial_imag[:count].reshape(count, 3, width, width, width),
            )
            polynomial_result = self._polynomial_result[:count]
            polynomial_result.fill(0.0)

            mass_rule = self.mass_rule
            mass_field = self._evaluate_vector(polynomial, mass_rule)
            mass_flux = self._weighted_flux(
                mass_field,
                self.mass_metrics[start:stop],
                self.mass_coefficients[start:stop],
                mass_rule,
            )
            for component in range(3):
                self._project_add(
                    polynomial_result[:, component],
                    mass_flux[..., component],
                    mass_rule.values_1d,
                )

            curl_rule = self.curl_rule
            curl_field = self._evaluate_curl(polynomial, curl_rule)
            curl_flux = self._weighted_flux(
                curl_field,
                self.curl_metrics[start:stop],
                self._curl_coefficients[:count],
                curl_rule,
            )
            values = curl_rule.values_1d
            derivatives = curl_rule.derivatives_1d
            self._project_add(
                polynomial_result[:, 0],
                curl_flux[..., 1],
                (values[0], values[1], derivatives[2]),
            )
            self._project_add(
                polynomial_result[:, 0],
                curl_flux[..., 2],
                (values[0], derivatives[1], values[2]),
                sign=-1.0,
            )
            self._project_add(
                polynomial_result[:, 1],
                curl_flux[..., 2],
                (derivatives[0], values[1], values[2]),
            )
            self._project_add(
                polynomial_result[:, 1],
                curl_flux[..., 0],
                (values[0], values[1], derivatives[2]),
                sign=-1.0,
            )
            self._project_add(
                polynomial_result[:, 2],
                curl_flux[..., 0],
                (values[0], derivatives[1], values[2]),
            )
            self._project_add(
                polynomial_result[:, 2],
                curl_flux[..., 1],
                (derivatives[0], values[1], values[2]),
                sign=-1.0,
            )

            result = self._result[:count]
            polynomial_flat = polynomial_result.reshape(count, polynomial_size)
            self._polynomial_real[:count] = polynomial_flat.real
            self._polynomial_imag[:count] = polynomial_flat.imag
            np.matmul(
                self._polynomial_real[:count],
                coefficient_matrix.T,
                out=self._coefficient_real[:count],
            )
            np.matmul(
                self._polynomial_imag[:count],
                coefficient_matrix.T,
                out=self._coefficient_imag[:count],
            )
            np.copyto(result.real, self._coefficient_real[:count])
            np.copyto(result.imag, self._coefficient_imag[:count])
            for row, cell in enumerate(range(start, stop)):
                if self.element.needs_dof_transformations:
                    self.element.T_apply(
                        result[row].view(np.float64),
                        self.permutations[cell : cell + 1],
                        2,
                    )
            np.add.at(output, dofs.ravel(), result.ravel())
        self.audit["apply_count"] += 1

    def destroy(self) -> None:
        self._destroyed = True


def build_task041_fused_physical_volume_context(
    *,
    cfg: Any,
    side: str,
    local_mesh: Any,
    V: Any,
    floquet_data: Any,
    bilinear_form: Any,
    volume_quadrature_contract: tuple[Any, ...],
) -> FullspaceMpcFormAction:
    """Build the explicitly requested local-kernel/MPC volume context."""

    if bool(cfg.use_pml) or float(cfg.divergence_penalty) != 0.0:
        raise NotImplementedError(
            "only the standard Task041 isotropic volume is covered"
        )
    if str(side) not in ("bottom", "top"):
        raise ValueError("physical side must be bottom or top")
    cell_specs = tuple(
        spec for spec in volume_quadrature_contract if str(spec.integral_type) == "cell"
    )
    rules = {
        (str(spec.quadrature_rule), int(spec.quadrature_degree)) for spec in cell_specs
    }
    if not cell_specs or len(rules) != 1:
        raise NotImplementedError(
            "the Task041 volume prototype needs one original cell rule shared by its terms"
        )
    quadrature_rule, quadrature_degree = next(iter(rules))
    measure = ufl.Measure(
        "dx",
        domain=local_mesh.mesh,
        metadata={
            "quadrature_rule": quadrature_rule,
            "quadrature_degree": quadrature_degree,
        },
    )
    trial = ufl.TrialFunction(V)
    test = ufl.TestFunction(V)
    curl_probe = ufl.inner(ufl.curl(trial), ufl.curl(test)) * measure
    mass_probe = ufl.inner(trial, test) * measure
    curl_data = _TensorProductRule(
        V,
        curl_probe,
        expected_rule=quadrature_rule,
        expected_degree=quadrature_degree,
    )
    mass_data = _TensorProductRule(
        V,
        mass_probe,
        expected_rule=quadrature_rule,
        expected_degree=quadrature_degree,
    )
    kernel = Task041FusedPhysicalVolumeKernel(
        space=floquet_data.mpc.function_space,
        cell_tags=local_mesh.mesh_data.cell_tags,
        cfg=cfg,
        curl_rule=curl_data,
        mass_rule=mass_data,
    )
    return FullspaceMpcFormAction(
        bilinear_form,
        V,
        mpc=floquet_data.mpc,
        local_kernel=kernel,
    )


__all__ = (
    "Task041FusedPhysicalVolumeKernel",
    "build_task041_fused_physical_volume_context",
)
