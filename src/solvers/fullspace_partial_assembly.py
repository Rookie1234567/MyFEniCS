"""Explicit experimental local action; shares exact positive reference tables.

No cell matrix or physical basis table is formed. The caller retains the
kernel; FullspaceMpcFormAction owns constraints, ghosts and PETSc resources.
"""
from __future__ import annotations

import numpy as np
import ufl
from dolfinx import fem

from .fullspace_quadrature_diagonal import PositiveCellBasis, ReferenceCellBasis


class IsotropicPartialAssembly:
    """Positive sum or one split volume component; fixed eight-cell workspace.

    Explicit split forms must carry the original component quadrature rule.
    Coefficients and reference basis objects are borrowed by the action.
    """

    batch_size = 8

    def __init__(self, space, mu, mass, *, component_form=None, component=None):
        self.space = space
        if component_form is None:
            if component is not None:
                raise ValueError("split component requires original form")
            self.basis = PositiveCellBasis(space, mu, mass, action_rule=True)
        else:
            if component not in ("curl", "mass"):
                raise ValueError("split component must be curl or mass")
            self.basis = ReferenceCellBasis(space, ufl.action(component_form, fem.Function(space)),
                                            allow_subdomains=True)
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
        n, q, _ = self.basis.values.shape
        self.dofs = np.asarray([space.dofmap.cell_dofs(c) for c in range(self.cell_count)],
                               dtype=np.int32).reshape(self.cell_count, n)
        self.material_indices = np.asarray([[f.function_space.dofmap.cell_dofs(c)[0]
            for f in (mass, mu)] for c in range(self.cell_count)], dtype=np.int32).reshape(-1, 2)
        self.metrics = np.empty((self.cell_count, 2, 3, 3))
        for cell in range(self.cell_count):
            x = mesh.geometry.x[mesh.geometry.dofmap[cell]]
            jacobians = np.einsum('aqi,ib->qba', self.basis.geometry_derivatives, x)
            jacobian = jacobians[0]
            scale = max(float(np.max(np.abs(jacobian))), np.finfo(float).tiny)
            if np.max(np.abs(jacobians-jacobian)) > 128*np.finfo(float).eps*scale:
                raise NotImplementedError("only affine geometry is qualified")
            determinant = float(np.linalg.det(jacobian))
            if not np.isfinite(determinant) or determinant <= 0:
                raise ValueError("positive finite Jacobian required")
            inv = np.linalg.inv(jacobian)
            self.metrics[cell, 0] = inv @ inv.T * determinant
            self.metrics[cell, 1] = jacobian.T @ jacobian / determinant
        for array in (self.dofs, self.material_indices, self.metrics):
            array.flags.writeable = False
        self.audit = dict(self.basis.audit,
            backend="isotropic_partial_assembly_v1", component=component or "positive_sum",
            batch_size=self.batch_size,
            reference_table_bytes=sum(a.nbytes for a in (self.basis.values,
                self.basis.curls, self.basis.weights, self.basis.geometry_derivatives)),
            cell_metadata_bytes=sum(a.nbytes for a in (self.dofs, self.material_indices,
                self.metrics, self.permutations)),
            temporary_budget_bytes=self.batch_size*(64*n+256*q+512),
            dense_cell_tensor=False, physical_basis_materialized=False)

    def apply(self, coefficients, output):
        basis, space = self.basis, self.space
        element = space.element
        # The reference tables are real. Transform real and imaginary columns
        # together: the actual DOLFINx orientation API accepts float arrays.
        values = basis.values.reshape(basis.values.shape[0], -1)
        curls = basis.curls.reshape(basis.curls.shape[0], -1)
        for start in range(0, self.cell_count, self.batch_size):
            cells = range(start, min(start+self.batch_size, self.cell_count))
            dofs = self.dofs[start:start+self.batch_size]
            local = np.ascontiguousarray(coefficients[dofs])
            for row, cell in enumerate(cells):
                if element.needs_dof_transformations:
                    element.Tt_apply(local[row].view(np.float64),
                                     self.permutations[cell:cell+1], 2)
            result = np.zeros_like(local)
            for k, (table, kind) in enumerate(((values, "mass"), (curls, "curl"))):
                if self.component is not None and kind != self.component:
                    continue
                # Real GEMM avoids an implicit complex copy of the large
                # reference table in mixed real/complex NumPy matmul.
                flux = (local.real @ table + 1j*(local.imag @ table)).reshape(len(dofs), -1, 3)
                for row, cell in enumerate(cells):
                    function = basis.mass if kind == "mass" else basis.mu
                    material = function.x.array[self.material_indices[cell, k]]
                    flux[row] = (flux[row] @ self.metrics[cell, k]) * (material*basis.weights[:, None])
                flat = flux.reshape(len(dofs), -1)
                result += flat.real @ table.T + 1j*(flat.imag @ table.T)
            for row, cell in enumerate(cells):
                if element.needs_dof_transformations:
                    element.T_apply(result[row].view(np.float64),
                                    self.permutations[cell:cell+1], 2)
            np.add.at(output, dofs.ravel(), result.ravel())
