"""Unweighted, lossless FE diagnostics on MPI1 independent coordinates.

Uses the actual fine quadrature metadata and finalized Floquet constraints.
No positive-PC material coefficient or identity slave row enters the metric.
"""
import hashlib
import numpy as np


def interpolate_known_error(space,floquet,cfg,indices):
    """The predeclared two-harmonic three-component Floquet field."""
    from dolfinx import fem
    def values(coordinates):
        x,y,z=coordinates
        u=(x-cfg.x_min)/(cfg.x_max-cfg.x_min)
        v=(y-cfg.y_min)/(cfg.y_max-cfg.y_min)
        t=(z-cfg.domain_z_min)/(cfg.domain_z_max-cfg.domain_z_min)
        phase=np.exp(1j*(cfg.kx*x+cfg.ky*y))*np.sin(np.pi*t)
        a=np.array([1,1j,1+1j])[:,None]
        b=np.array([1-1j,2,-1j])[:,None]
        return phase*(a*np.exp(2j*np.pi*(u+v))+b*np.sin(2*np.pi*t)*np.exp(2j*np.pi*(2*u-v)))
    field=fem.Function(floquet.mpc.function_space)
    field.interpolate(values)
    field.x.scatter_forward()
    floquet.mpc.homogenize(field)
    field.x.scatter_forward()
    result=np.array(field.x.array[indices],copy=True)
    if not np.isfinite(result).all() or np.linalg.norm(result)==0:
        raise ValueError('known-error interpolation failed')
    return result


class SerialAction:
    """Bridge an existing PETSc action to compact independent array callbacks."""

    def __init__(self, space, floquet, action, *, result='target', target_space=None,
                 target_floquet=None):
        from dolfinx.la.petsc import create_vector
        from .fullspace_physical_intermediate_runtime import owned_slave_indices
        if space.mesh.comm.size != 1:
            raise ValueError('this diagnostic bridge is explicitly MPI1')
        target_space = space if target_space is None else target_space
        target_floquet = floquet if target_floquet is None else target_floquet
        self.source = create_vector([(space.dofmap.index_map,space.dofmap.index_map_bs)])
        self.target = create_vector([(target_space.dofmap.index_map,target_space.dofmap.index_map_bs)])
        self.indices = np.setdiff1d(np.arange(self.source.getLocalSize()),owned_slave_indices(space,floquet))
        self.source_slaves=owned_slave_indices(space,floquet)
        self.target_slaves=owned_slave_indices(target_space,target_floquet)
        self.target_indices = np.setdiff1d(np.arange(self.target.getLocalSize()),self.target_slaves)
        self.action,self.result = action,result
        self.audit=dict(calls_started=0,calls_completed=0,result_contract=result,
                        source_independent_rows=int(self.indices.size),target_independent_rows=int(self.target_indices.size))

    def __call__(self,x):
        if np.shape(x) != self.indices.shape or not np.isfinite(x).all():
            raise ValueError('invalid independent diagnostic input')
        self.source.set(0)
        self.source.array[self.indices] = x
        self.audit['calls_started']+=1
        if self.result == 'target':
            self.action(self.source,self.target)
            value = self.target
        else:
            value = self.action(self.source)
        try:
            if self.audit['calls_completed']==0:
                unchanged=bool(np.array_equal(self.source.array[self.indices],x) and
                               np.all(self.source.array[self.source_slaves]==0))
                legal=bool(np.all(value.array[self.target_slaves]==0))
                self.audit.update(first_input_unchanged=unchanged,first_output_slave_zero=legal)
                if not unchanged or not legal:
                    raise RuntimeError('diagnostic bridge first-call input/constraint check failed')
            # Copy before another component action can reuse this buffer.
            output=np.array(value.array[self.target_indices],copy=True)
            if not np.isfinite(output).all():raise RuntimeError('nonfinite diagnostic bridge output')
            self.audit['calls_completed']+=1
            return output
        finally:
            if self.result == 'owned':
                value.destroy()

    def destroy(self):
        self.source.destroy()
        self.target.destroy()


def _physical_basis(basis, cell, permutation):
    """Same covariant Piola/orientation convention as the existing diagonal."""
    space = basis.space
    mesh = space.mesh
    x = mesh.geometry.x[mesh.geometry.dofmap[cell]]
    jacobians = np.einsum('aqi,ib->qba',basis.geometry_derivatives,x)
    jacobian = jacobians[0]
    scale = max(float(np.max(np.abs(jacobian))),np.finfo(float).tiny)
    if np.max(np.abs(jacobians-jacobian)) > 128*np.finfo(float).eps*scale:
        raise ValueError('lossless metric requires the qualified affine geometry')
    determinant = float(np.linalg.det(jacobian))
    if not np.isfinite(determinant) or determinant <= 0:
        raise ValueError('invalid metric cell geometry')
    values = np.ascontiguousarray(basis.values @ np.linalg.inv(jacobian))
    curls = np.ascontiguousarray(basis.curls @ jacobian.T/determinant)
    if space.element.needs_dof_transformations:
        for data in (values,curls):
            space.element.T_apply(data.reshape(-1),np.asarray([permutation],dtype=np.uint32),data.shape[1]*3)
    return values,curls,basis.weights*determinant


class LosslessFEMetric:
    """Own M0 and k0^-2 curl forms, borrowing mesh/space/MPC from the solver."""

    def __init__(self, levels, degree, k0, quadrature):
        import ufl
        from dolfinx import fem
        from .fullspace_mpc_action import build_fullspace_mpc_form_action
        from .fullspace_quadrature_diagonal import ReferenceCellBasis
        from .fullspace_same_mesh_hcurl_pmg_setup import SAME_MESH_JIT_OPTIONS
        self.space,self.floquet = levels['spaces'][degree],levels['floquets'][degree]
        self.tags = levels['mesh_data'].cell_tags
        self.k0 = k0
        u,v = ufl.TrialFunction(self.space),ufl.TestFunction(self.space)
        forms = dict(mass=ufl.inner(u,v)*ufl.dx(domain=self.space.mesh,metadata=quadrature[1]),
                     curl=ufl.inner(ufl.curl(u),ufl.curl(v))/k0**2 *
                          ufl.dx(domain=self.space.mesh,metadata=quadrature[0]))
        self.actions,self.bridges,self.bases = {},{},{}
        try:
            for name,form in forms.items():
                a = build_fullspace_mpc_form_action(form,self.space,mpc=self.floquet.mpc,
                    slave_row_identity=False,jit_options=SAME_MESH_JIT_OPTIONS)
                self.actions[name] = a
                self.bridges[name] = SerialAction(self.space,self.floquet,a.apply,result='borrowed')
                self.bases[name] = ReferenceCellBasis(self.space,ufl.action(form,fem.Function(self.space)))
            self.mass,self.curl = self.bridges['mass'],self.bridges['curl']
            self.audit = dict(definition='integral conj(E) dot E; no epsilon, k0 or slave identity',
                curl_definition='integral abs(curl E)^2 / k0^2',degree=degree,
                quadrature={k:b.audit for k,b in self.bases.items()},
                independent_rows=int(self.mass.indices.size),mpi_size=1)
        except BaseException:
            self.destroy()
            raise

    def diagonal(self, *, checkpoint=lambda: None):
        """Exact constrained mass diagonal by cell quadrature, no global AIJ."""
        from .fullspace_same_mesh_hcurl_pmg_p6 import _cell_expansion_workspace,_fill_cell_expansion
        from .fullspace_quadrature_diagonal import accumulate_basis_energy
        work = self.floquet.mpc.function_space
        storage = work.dofmap.index_map.size_local + work.dofmap.index_map.num_ghosts
        _,mask,targets,coefficients = _cell_expansion_workspace(self.floquet.mpc,storage,work.element.space_dimension)
        mesh = work.mesh
        mesh.topology.create_entity_permutations()
        permutations = mesh.topology.get_cell_permutation_info()
        diagonal = np.zeros(storage,dtype=np.complex128)
        for cell in range(mesh.topology.index_map(mesh.topology.dim).size_local):
            checkpoint()
            dofs = np.asarray(work.dofmap.cell_dofs(cell),dtype=np.int32)
            _fill_cell_expansion(dofs,self.floquet.mpc,storage,mask,targets,coefficients)
            values,curls,weights = _physical_basis(self.bases['mass'],cell,permutations[cell])
            accumulate_basis_energy(values,curls,weights,targets,coefficients,diagonal,
                                    curl_coefficient=0,mass_coefficient=1)
        result = diagonal[self.mass.indices].real.copy()
        if not np.isfinite(result).all() or np.any(result<=0):
            raise ValueError('invalid lossless mass diagonal')
        self.audit['diagonal_sha256'] = hashlib.sha256(result.tobytes()).hexdigest()
        return result

    def cell_energies(self,x, *, checkpoint=lambda: None):
        """Owned-cell integrals; shared DoFs are never counted as energy twice."""
        from dolfinx import fem
        field = fem.Function(self.floquet.mpc.function_space)
        field.x.array[:] = 0
        field.x.array[self.mass.indices] = x
        field.x.scatter_forward()
        self.floquet.mpc.backsubstitution(field)
        field.x.scatter_forward()
        mesh = self.space.mesh
        mesh.topology.create_entity_permutations()
        permutations = mesh.topology.get_cell_permutation_info()
        count = mesh.topology.index_map(mesh.topology.dim).size_local
        tags = np.full(count,-1,dtype=int)
        for cell,tag in zip(self.tags.indices,self.tags.values):
            if cell<count: tags[cell]=tag
        centers = np.array([mesh.geometry.x[mesh.geometry.dofmap[c]].mean(axis=0) for c in range(count)])
        energies = {name:np.zeros(count) for name in self.bases}
        for cell in range(count):
            checkpoint()
            coefficients = field.x.array[field.function_space.dofmap.cell_dofs(cell)]
            for name,basis in self.bases.items():
                values,curls,weights = _physical_basis(basis,cell,permutations[cell])
                sampled = np.einsum('i,iqk->qk',coefficients,values if name=='mass' else curls)
                energies[name][cell] = np.dot(weights,np.sum(np.abs(sampled)**2,axis=1))/(1 if name=='mass' else self.k0**2)
        return dict(cell_centers=centers,material_tags=tags,**energies,
                    partition_rule='sum owned cell integrals by material tag or exact coordinate layer')

    def destroy(self):
        for bridge in self.bridges.values(): bridge.destroy()
        for action in self.actions.values(): action.destroy()
        self.bridges.clear()
        self.actions.clear()
