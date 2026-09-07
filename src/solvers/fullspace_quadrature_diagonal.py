"""Exact constrained positive H(curl) diagonal without dense cell tensors.

Restricted to the existing scalar DG0 curl+mass form on affine Q1 hexes.
FFCx analysis supplies the unchanged integration rule. Basis orientation is
applied before the complex MPC expansion; shared targets retain cross terms.
"""
from __future__ import annotations

import hashlib
import basix
import numpy as np
from dolfinx import fem
from dolfinx.la.petsc import create_vector
from petsc4py import PETSc

from .fullspace_same_mesh_hcurl_pmg_global import same_mesh_positive_form
from .fullspace_same_mesh_hcurl_pmg_p6 import (
    _cell_expansion_workspace, _fill_cell_expansion,
)


def accumulate_basis_energy(values, curls, weights, targets, coefficients, output,
                            *, curl_coefficient, mass_coefficient):
    """Add target energies after summing all raw basis rows for each target.

    Arrays have shape (raw DoF, quadrature point, vector component).
    No assumption about permutations, single masters or disjoint targets.
    """
    if (values.shape != curls.shape or values.ndim != 3 or
            weights.shape != (values.shape[1],) or targets.ndim != 2 or
            targets.shape != coefficients.shape or targets.shape[0] != values.shape[0]):
        raise ValueError('incompatible basis/expansion dimensions')
    if not all(np.all(np.isfinite(a)) for a in (values, curls, weights, coefficients)):
        raise ValueError('nonfinite basis or expansion')
    for target in np.unique(targets[targets >= 0]):
        if target >= output.size:
            raise ValueError('target outside output storage')
        rows, links = np.nonzero(targets == target)
        factors = coefficients[rows, links]
        value = np.einsum('i,iqk->qk', factors, values[rows])
        curl = np.einsum('i,iqk->qk', factors, curls[rows])
        output[target] += np.dot(weights,
            mass_coefficient * np.sum(np.abs(value)**2, axis=1)
            + curl_coefficient * np.sum(np.abs(curl)**2, axis=1))


class PositiveCellBasis:
    """Reference quadrature/bases only; cell workspaces are not retained."""

    def __init__(self, space, mu, mass):
        from ffcx.analysis import analyze_ufl_objects
        from ffcx.element_interface import create_quadrature
        self.space, self.mu, self.mass = space, mu, mass
        mesh = space.mesh
        element = space.element.basix_element
        if (mesh.basix_cell() != basix.CellType.hexahedron or
                element.map_type != basix.MapType.covariantPiola or
                element.family != basix.ElementFamily.N1E or
                mesh.geometry.cmap.degree != 1 or mesh.geometry.dim != 3 or
                space.dofmap.index_map_bs != 1):
            raise NotImplementedError('requires scalar-blocked N1curl on Q1 3D hexes')
        for coefficient in (mu, mass):
            e = coefficient.function_space.element.basix_element
            if (coefficient.function_space.mesh is not mesh or e.degree != 0 or
                    not e.discontinuous or e.dim != 1):
                raise NotImplementedError('requires same-mesh scalar DG0 coefficients')
            a = coefficient.x.array
            if not np.all(np.isfinite(a)) or np.any(a.imag != 0) or np.any(a.real <= 0):
                raise ValueError('positive real finite DG0 coefficients required')
        form = same_mesh_positive_form(space, curl_coefficient=mu, mass_coefficient=mass)
        analysis = analyze_ufl_objects([form], np.dtype(np.complex128))
        data = analysis.form_data[0]
        integrals = [i for group in data.integral_data for i in group.integrals]
        if len(integrals) != 1 or integrals[0].integral_type() != 'cell':
            raise NotImplementedError('requires one positive cell integral')
        md = integrals[0].metadata()
        if md['quadrature_rule'] in ('custom', 'vertex'):
            raise NotImplementedError('custom/vertex quadrature unsupported')
        points, self.weights = create_quadrature(
            'hexahedron', md['quadrature_degree'], md['quadrature_rule'], data.argument_elements)
        table = element.tabulate(1, points)
        self.values = np.ascontiguousarray(table[0].transpose(1, 0, 2))
        self.curls = np.ascontiguousarray(np.stack((
            table[2, :, :, 2]-table[3, :, :, 1],
            table[3, :, :, 0]-table[1, :, :, 2],
            table[1, :, :, 1]-table[2, :, :, 0]), axis=2).transpose(1, 0, 2))
        geometry_element = basix.create_element(basix.ElementFamily.P,
            basix.CellType.hexahedron, 1, basix.LagrangeVariant.equispaced)
        self.geometry_derivatives = geometry_element.tabulate(1, points)[1:, :, :, 0]
        self.audit = dict(quadrature_degree=int(md['quadrature_degree']),
            quadrature_rule=md['quadrature_rule'], points=len(points),
            points_sha256=hashlib.sha256(points.tobytes()).hexdigest(),
            weights_sha256=hashlib.sha256(self.weights.tobytes()).hexdigest(),
            authority='same-ABI FFCx analysis and create_quadrature', dense_cell_tensor=False)

    def cell(self, cell, permutation):
        """Return oriented physical basis values/curls, weights and DG0 data."""
        mesh = self.space.mesh
        x = mesh.geometry.x[mesh.geometry.dofmap[cell]]
        jacobians = np.einsum('aqi,ib->qba', self.geometry_derivatives, x)
        jacobian = jacobians[0]
        scale = max(float(np.max(np.abs(jacobian))), np.finfo(float).tiny)
        if np.max(np.abs(jacobians-jacobian)) > 128*np.finfo(float).eps*scale:
            raise NotImplementedError('only affine geometry is qualified')
        determinant = float(np.linalg.det(jacobian))
        if not np.isfinite(determinant) or determinant <= 0:
            raise ValueError('positive finite Jacobian required')
        values = np.ascontiguousarray(self.values @ np.linalg.inv(jacobian))
        curls = np.ascontiguousarray(self.curls @ jacobian.T / determinant)
        if self.space.element.needs_dof_transformations:
            info = np.asarray([permutation], dtype=np.uint32)
            for a in (values, curls):
                self.space.element.T_apply(a.reshape(-1), info, a.shape[1]*3)
        coefficients = [float(f.x.array[f.function_space.dofmap.cell_dofs(cell)[0]].real)
                        for f in (self.mu, self.mass)]
        return values, curls, self.weights * determinant, coefficients


def build_quadrature_positive_diagonal(space, mu, mass, mpc):
    """Full owner-cell accumulation; same identity/slave/ghost policy as oracle."""
    if PETSc.ScalarType is not np.complex128:
        raise TypeError('complex128 PETSc required')
    if mpc.function_space.mesh is not space.mesh:
        raise ValueError('MPC mesh mismatch')
    work = mpc.function_space
    if (work.dofmap.index_map.size_global != space.dofmap.index_map.size_global or
            work.element.space_dimension != space.element.space_dimension):
        raise ValueError('MPC space mismatch')
    basis = PositiveCellBasis(space, mu, mass)
    index_map = work.dofmap.index_map
    owned = int(index_map.size_local)
    storage = owned + int(index_map.num_ghosts)
    slaves, mask, targets, coefficients = _cell_expansion_workspace(
        mpc, storage, int(work.element.space_dimension))
    work.mesh.topology.create_entity_permutations()
    permutations = work.mesh.topology.get_cell_permutation_info()
    local = np.zeros(storage, dtype=np.complex128)
    count = int(work.mesh.topology.index_map(work.mesh.topology.dim).size_local)
    for cell in range(count):
        dofs = np.asarray(work.dofmap.cell_dofs(cell), dtype=np.int32)
        _fill_cell_expansion(dofs, mpc, storage, mask, targets, coefficients)
        values, curls, weights, (mu_cell, mass_cell) = basis.cell(cell, int(permutations[cell]))
        accumulate_basis_energy(values, curls, weights, targets, coefficients, local,
                                curl_coefficient=mu_cell, mass_coefficient=mass_cell)
        del values, curls, weights
    vector = create_vector([(index_map, int(work.dofmap.index_map_bs))])
    try:
        with vector.localForm() as form:
            form.array_w[:] = local
        vector.ghostUpdate(addv=PETSc.InsertMode.ADD_VALUES, mode=PETSc.ScatterMode.REVERSE)
        if not np.all(np.isfinite(vector.array)) or np.any(vector.array.real[~mask[:owned]] <= 0):
            raise ValueError('nonfinite/nonpositive constrained diagonal')
        with vector.localForm() as form:
            form.array_w[slaves[slaves < owned]] = 1
        vector.ghostUpdate(addv=PETSc.InsertMode.INSERT_VALUES, mode=PETSc.ScatterMode.FORWARD)
        return vector
    except BaseException:
        vector.destroy()
        raise
