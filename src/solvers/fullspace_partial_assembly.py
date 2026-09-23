"""Explicit experimental local action; shares exact positive reference tables.

No cell matrix or physical basis table is formed. The caller retains the
kernel; FullspaceMpcFormAction owns constraints, ghosts and PETSc resources.
"""
from __future__ import annotations

import time

import numpy as np
import ufl
from dolfinx import fem

from .fullspace_quadrature_diagonal import (
    PositiveCellBasis, ReferenceCellBasis, _affine_cell_jacobian,
)
from .fullspace_n1e_sum_factor import N1ESumFactorizedAction


class IsotropicPartialAssembly:
    """Positive sum or one split volume component; fixed eight-cell workspace.

    Explicit split forms must carry the original component quadrature rule.
    Coefficients and reference basis objects are borrowed by the action.
    """

    batch_size = 8

    def __init__(
        self,
        space,
        mu,
        mass,
        *,
        component_form=None,
        component=None,
        contiguous_work=False,
        preallocated_work=False,
        sum_factorized_work=False,
    ):
        self.space = space
        self.contiguous_work = bool(contiguous_work)
        self.preallocated_work = bool(preallocated_work)
        self.sum_factorized_work = bool(sum_factorized_work)
        if component_form is None:
            if component is not None:
                raise ValueError("split component requires original form")
            self.basis = PositiveCellBasis(
                space,
                mu,
                mass,
                action_rule=True,
                store_reference_tables=not self.sum_factorized_work,
            )
        else:
            if component not in ("curl", "mass"):
                raise ValueError("split component must be curl or mass")
            self.basis = ReferenceCellBasis(
                space,
                ufl.action(component_form, fem.Function(space)),
                allow_subdomains=True,
                store_reference_tables=not self.sum_factorized_work,
            )
            for function in (mu, mass):
                e = function.function_space.element.basix_element
                if (function.function_space.mesh is not space.mesh or e.degree != 0
                        or not e.discontinuous or e.dim != 1):
                    raise NotImplementedError("same-mesh scalar DG0 required")
                if not np.all(np.isfinite(function.x.array)):
                    raise ValueError("finite material required")
            self.basis.mu, self.basis.mass = mu, mass
        self.component = component
        mesh = space.mesh
        mesh.topology.create_entity_permutations()
        self.permutations = mesh.topology.get_cell_permutation_info()
        self.cell_count = mesh.topology.index_map(mesh.topology.dim).size_local
        if self.sum_factorized_work:
            n = int(space.element.space_dimension)
            q = len(self.basis.points)
            self._sum_factorized = N1ESumFactorizedAction(
                space, self.basis, batch_size=self.batch_size
            )
        else:
            n, q, _ = self.basis.values.shape
            self._sum_factorized = None
        self.dofs = np.asarray([space.dofmap.cell_dofs(c) for c in range(self.cell_count)],
                               dtype=np.int32).reshape(self.cell_count, n)
        self.material_indices = np.asarray([[f.function_space.dofmap.cell_dofs(c)[0]
            for f in (mass, mu)] for c in range(self.cell_count)], dtype=np.int32).reshape(-1, 2)
        self.metrics = np.empty((self.cell_count, 2, 3, 3))
        for cell in range(self.cell_count):
            x = mesh.geometry.x[mesh.geometry.dofmap[cell]]
            jacobian = _affine_cell_jacobian(self.basis.geometry_derivatives, x)
            determinant = float(np.linalg.det(jacobian))
            inv = np.linalg.inv(jacobian)
            self.metrics[cell, 0] = inv @ inv.T * determinant
            self.metrics[cell, 1] = jacobian.T @ jacobian / determinant
        for array in (self.dofs, self.material_indices, self.metrics):
            array.flags.writeable = False
        if self.sum_factorized_work:
            batch_capacity = max(1, self.batch_size)
            self._local_work = np.empty((batch_capacity, n), dtype=np.complex128)
            self._result_work = None
            self._flux_work = None
            self._forward_real_work = None
            self._forward_imag_work = None
            self._back_real_work = None
            self._back_imag_work = None
            self._coefficient_real_work = None
            self._coefficient_imag_work = None
            self._flux_real_work = None
            self._flux_imag_work = None
            batch_workspace_bytes = int(
                self._local_work.nbytes + self._sum_factorized.audit["batch_workspace_bytes"]
            )
        elif self.preallocated_work:
            # Keep the existing fixed batch cap, but retain its small
            # numerical workspace between applies.  This opt-in path removes
            # repeated batch allocations without creating a mesh-sized matrix
            # or cell tensor.  The source gather itself remains explicitly
            # accounted for in the bounded workspace contract.
            batch_capacity = max(1, self.batch_size)
            flat_width = int(q * 3)
            self._local_work = np.empty((batch_capacity, n), dtype=np.complex128)
            self._result_work = np.empty((batch_capacity, n), dtype=np.complex128)
            self._flux_work = np.empty((batch_capacity, q, 3), dtype=np.complex128)
            self._forward_real_work = np.empty((batch_capacity, flat_width), dtype=np.float64)
            self._forward_imag_work = np.empty((batch_capacity, flat_width), dtype=np.float64)
            self._back_real_work = np.empty((batch_capacity, n), dtype=np.float64)
            self._back_imag_work = np.empty((batch_capacity, n), dtype=np.float64)
            if self.contiguous_work:
                self._coefficient_real_work = np.empty((batch_capacity, n), dtype=np.float64)
                self._coefficient_imag_work = np.empty((batch_capacity, n), dtype=np.float64)
                self._flux_real_work = np.empty((batch_capacity, flat_width), dtype=np.float64)
                self._flux_imag_work = np.empty((batch_capacity, flat_width), dtype=np.float64)
            else:
                self._coefficient_real_work = None
                self._coefficient_imag_work = None
                self._flux_real_work = None
                self._flux_imag_work = None
            batch_workspace_bytes = sum(
                int(array.nbytes)
                for array in (
                    self._local_work,
                    self._result_work,
                    self._flux_work,
                    self._forward_real_work,
                    self._forward_imag_work,
                    self._back_real_work,
                    self._back_imag_work,
                    self._coefficient_real_work,
                    self._coefficient_imag_work,
                    self._flux_real_work,
                    self._flux_imag_work,
                )
                if array is not None
            )
        else:
            batch_capacity = 0
            batch_workspace_bytes = 0
            self._local_work = None
            self._result_work = None
            self._flux_work = None
            self._forward_real_work = None
            self._forward_imag_work = None
            self._back_real_work = None
            self._back_imag_work = None
            self._coefficient_real_work = None
            self._coefficient_imag_work = None
            self._flux_real_work = None
            self._flux_imag_work = None
        if self._sum_factorized is not None:
            sum_factorized_reference_components = {
                "coefficient_matrix_bytes": self._sum_factorized.audit[
                    "coefficient_matrix_bytes"
                ],
                "one_dimensional_reference_tables_bytes": self._sum_factorized.audit[
                    "one_dimensional_reference_tables_bytes"
                ],
                "points_bytes": int(self.basis.points.nbytes),
                "weights_bytes": int(self.basis.weights.nbytes),
                "geometry_derivatives_bytes": int(
                    self.basis.geometry_derivatives.nbytes
                ),
                "quadrature_order_indices_bytes": int(
                    self._sum_factorized.natural_to_input.nbytes
                    + self._sum_factorized.input_to_natural.nbytes
                ),
            }
            sum_factorized_reference_bytes = sum(
                sum_factorized_reference_components.values()
            )
            sum_factorized_temporary_bytes = self._sum_factorized.audit[
                "temporary_workspace_upper_bound_bytes"
            ]
        else:
            sum_factorized_reference_components = None
            sum_factorized_reference_bytes = 0
            sum_factorized_temporary_bytes = 0
        self.audit = dict(self.basis.audit,
            backend=(
                "isotropic_sum_factorized_n1e_v26"
                if self.sum_factorized_work
                else "isotropic_partial_assembly_bounded_preallocated_v25"
                if self.preallocated_work
                else "isotropic_partial_assembly_v1"
            ), component=component or "positive_sum",
            batch_size=self.batch_size,
            reference_table_bytes=(
                sum_factorized_reference_bytes
                if self.sum_factorized_work
                else sum(a.nbytes for a in (self.basis.values,
                    self.basis.curls, self.basis.weights, self.basis.geometry_derivatives))
            ),
            reference_table_components=sum_factorized_reference_components,
            sum_factorized_opt_in=self.sum_factorized_work,
            sum_factorized_audit=(
                self._sum_factorized.audit if self._sum_factorized is not None else None
            ),
            cell_metadata_bytes=sum(a.nbytes for a in (self.dofs, self.material_indices,
                self.metrics, self.permutations)),
            contiguous_real_imag_work=self.contiguous_work,
            preallocated_work_opt_in=self.preallocated_work,
            preallocated_batch_capacity=batch_capacity,
            preallocated_batch_workspace_bytes=batch_workspace_bytes,
            batch_workspace_scope="one fixed local batch; no global matrix/tensor",
            packing_workspace_upper_bound_bytes=(
                self.batch_size*(16*n+48*q)
                if self.contiguous_work and not self.sum_factorized_work
                else 0
            ),
            temporary_budget_bytes=(
                sum_factorized_temporary_bytes
                if self.sum_factorized_work
                else self.batch_size*(64*n+256*q+512)
                + (self.batch_size*(16*n+48*q) if self.contiguous_work else 0)
            ),
            dense_cell_tensor=False, physical_basis_materialized=False)
        self.audit["timing_cumulative_seconds"] = {
            "apply": 0.0,
            "gather": 0.0,
            "coefficient_transform": 0.0,
            "reference_forward": 0.0,
            "metric": 0.0,
            "reference_backward": 0.0,
            "scatter": 0.0,
        }
        self.audit["timing_scope"] = (
            "opt-in local-kernel path only; cumulative local-kernel wall clock"
        )

    def _apply_sum_factorized(self, coefficients, output):
        basis, space = self.basis, self.space
        element = space.element
        timing = self.audit["timing_cumulative_seconds"]
        for start in range(0, self.cell_count, self.batch_size):
            stop = min(start + self.batch_size, self.cell_count)
            count = stop - start
            cells = range(start, stop)
            dofs = self.dofs[start:stop]
            apply_started = time.perf_counter()
            gather_started = time.perf_counter()
            local = self._local_work[:count]
            local[...] = coefficients[dofs]
            timing["gather"] += time.perf_counter() - gather_started
            for row, cell in enumerate(cells):
                if element.needs_dof_transformations:
                    element.Tt_apply(
                        local[row].view(np.float64),
                        self.permutations[cell:cell + 1],
                        2,
                    )
            materials = np.empty((count, 2), dtype=np.complex128)
            materials[:, 0] = basis.mass.x.array[
                self.material_indices[start:stop, 0]
            ]
            materials[:, 1] = basis.mu.x.array[
                self.material_indices[start:stop, 1]
            ]
            result = self._sum_factorized.apply(
                local,
                self.metrics[start:stop],
                materials,
                component=self.component,
            )
            for key, value in self._sum_factorized.timing.items():
                timing[key] = float(value)
            for row, cell in enumerate(cells):
                if element.needs_dof_transformations:
                    element.T_apply(
                        result[row].view(np.float64),
                        self.permutations[cell:cell + 1],
                        2,
                    )
            scatter_started = time.perf_counter()
            np.add.at(output, dofs.ravel(), result.ravel())
            timing["scatter"] += time.perf_counter() - scatter_started
            timing["apply"] += time.perf_counter() - apply_started
        return None

    def apply(self, coefficients, output):
        if self.sum_factorized_work:
            return self._apply_sum_factorized(coefficients, output)
        if not self.preallocated_work:
            # Preserve the qualified V24 packed path byte-for-byte in its
            # default mode so old evidence and paired baselines remain valid.
            basis, space = self.basis, self.space
            element = space.element
            values = basis.values.reshape(basis.values.shape[0], -1)
            curls = basis.curls.reshape(basis.curls.shape[0], -1)
            for start in range(0, self.cell_count, self.batch_size):
                cells = range(start, min(start + self.batch_size, self.cell_count))
                dofs = self.dofs[start:start + self.batch_size]
                local = np.ascontiguousarray(coefficients[dofs])
                for row, cell in enumerate(cells):
                    if element.needs_dof_transformations:
                        element.Tt_apply(
                            local[row].view(np.float64),
                            self.permutations[cell:cell + 1],
                            2,
                        )
                result = np.zeros_like(local)
                real = (
                    np.ascontiguousarray(local.real)
                    if self.contiguous_work
                    else local.real
                )
                imag = (
                    np.ascontiguousarray(local.imag)
                    if self.contiguous_work
                    else local.imag
                )
                for k, (table, kind) in enumerate(
                    ((values, "mass"), (curls, "curl"))
                ):
                    if self.component is not None and kind != self.component:
                        continue
                    flux = (real @ table + 1j * (imag @ table)).reshape(
                        len(dofs), -1, 3
                    )
                    for row, cell in enumerate(cells):
                        function = basis.mass if kind == "mass" else basis.mu
                        material = function.x.array[self.material_indices[cell, k]]
                        flux[row] = (
                            flux[row] @ self.metrics[cell, k]
                        ) * (material * basis.weights[:, None])
                    flat = flux.reshape(len(dofs), -1)
                    fr = (
                        np.ascontiguousarray(flat.real)
                        if self.contiguous_work
                        else flat.real
                    )
                    fi = (
                        np.ascontiguousarray(flat.imag)
                        if self.contiguous_work
                        else flat.imag
                    )
                    result += fr @ table.T + 1j * (fi @ table.T)
                for row, cell in enumerate(cells):
                    if element.needs_dof_transformations:
                        element.T_apply(
                            result[row].view(np.float64),
                            self.permutations[cell:cell + 1],
                            2,
                        )
                np.add.at(output, dofs.ravel(), result.ravel())
            return

        basis, space = self.basis, self.space
        element = space.element
        # The reference tables are real. Transform real and imaginary columns
        # together: the actual DOLFINx orientation API accepts float arrays.
        values = basis.values.reshape(basis.values.shape[0], -1)
        curls = basis.curls.reshape(basis.curls.shape[0], -1)
        for start in range(0, self.cell_count, self.batch_size):
            stop = min(start + self.batch_size, self.cell_count)
            count = stop - start
            cells = range(start, stop)
            dofs = self.dofs[start:stop]
            apply_started = time.perf_counter()
            started = time.perf_counter()
            local = self._local_work[:count]
            local[...] = coefficients[dofs]
            self.audit["timing_cumulative_seconds"]["gather"] += (
                time.perf_counter() - started
            )
            for row, cell in enumerate(cells):
                if element.needs_dof_transformations:
                    element.Tt_apply(local[row].view(np.float64),
                                     self.permutations[cell:cell+1], 2)
            result = self._result_work[:count]
            result.fill(0.0)
            if self.contiguous_work:
                real = self._coefficient_real_work[:count]
                imag = self._coefficient_imag_work[:count]
                np.copyto(real, local.real)
                np.copyto(imag, local.imag)
            else:
                real = local.real
                imag = local.imag
            for k, (table, kind) in enumerate(((values, "mass"), (curls, "curl"))):
                if self.component is not None and kind != self.component:
                    continue
                # NumPy 1.26 matrix-matrix BLAS requires a unit inner stride.
                # Only the fixed batch operands are packed, never reference tables.
                started = time.perf_counter()
                np.matmul(real, table, out=self._forward_real_work[:count])
                np.matmul(imag, table, out=self._forward_imag_work[:count])
                flux = self._flux_work[:count]
                np.copyto(flux.real.reshape(count, -1), self._forward_real_work[:count])
                np.copyto(flux.imag.reshape(count, -1), self._forward_imag_work[:count])
                self.audit["timing_cumulative_seconds"]["reference_forward"] += (
                    time.perf_counter() - started
                )
                started = time.perf_counter()
                for row, cell in enumerate(cells):
                    function = basis.mass if kind == "mass" else basis.mu
                    material = function.x.array[self.material_indices[cell, k]]
                    flux[row] = (flux[row] @ self.metrics[cell, k]) * (material*basis.weights[:, None])
                self.audit["timing_cumulative_seconds"]["metric"] += (
                    time.perf_counter() - started
                )
                flat = flux.reshape(len(dofs), -1)
                if self.contiguous_work:
                    fr = self._flux_real_work[:count]
                    fi = self._flux_imag_work[:count]
                    np.copyto(fr, flat.real)
                    np.copyto(fi, flat.imag)
                else:
                    fr = flat.real
                    fi = flat.imag
                started = time.perf_counter()
                np.matmul(fr, table.T, out=self._back_real_work[:count])
                np.matmul(fi, table.T, out=self._back_imag_work[:count])
                result.real += self._back_real_work[:count]
                result.imag += self._back_imag_work[:count]
                self.audit["timing_cumulative_seconds"]["reference_backward"] += (
                    time.perf_counter() - started
                )
            for row, cell in enumerate(cells):
                if element.needs_dof_transformations:
                    element.T_apply(result[row].view(np.float64),
                                    self.permutations[cell:cell+1], 2)
            started = time.perf_counter()
            np.add.at(output, dofs.ravel(), result.ravel())
            self.audit["timing_cumulative_seconds"]["scatter"] += (
                time.perf_counter() - started
            )
            self.audit["timing_cumulative_seconds"]["apply"] += (
                time.perf_counter() - apply_started
            )
