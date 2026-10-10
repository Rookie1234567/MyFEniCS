"""Explicit affine tetra kernel with packed DG0 and one native orientation.

This provider only compiles/calls cell kernels. It never assembles a global
matrix and cannot consume a body/Schur checkpoint. Translation reuse is
opt-in after actual-cell qualification, with unrounded J and coefficient keys.
"""
import hashlib
import numpy as np

from .hcurl_assembly_time_condensation import _orient_cell_tensor


class TetraCellKernel:
    def __init__(self,setup,journal):
        from dolfinx import fem
        from .independent_tetra_reference import body_form
        self.s=setup;self.dim=setup['V'].element.space_dimension
        if self.dim!=140 or setup['V'].element.basix_element.cell_type.name!='tetrahedron':
            raise ValueError('explicit affine p5 tetra 140 kernel')
        form,self.epsilon,self.q=body_form(setup)
        with journal.measured('tetra_cell_JIT_form_no_global_matrix'):
            self.compiled=fem.form(form,jit_options={'cache_dir':__import__('os').environ['FFCX_CACHE_DIR']})
        a=self.compiled;uf=a.ufcx_form;self.ffi=a.module.ffi
        begin,end=[int(uf.form_integral_offsets[i]) for i in (0,1)]
        if end-begin!=1 or int(uf.form_integral_ids[begin])!=-1 or int(uf.num_coefficients)!=1:
            raise ValueError('single all-cell DG0 coefficient domain required')
        self.kernel=uf.form_integrals[begin].tabulate_tensor_complex128
        self.coefficients=np.ascontiguousarray(fem.pack_coefficients(a)[(fem.IntegralType.cell,-1)],dtype=np.complex128)
        self.constants=np.ascontiguousarray(fem.pack_constants(a),dtype=np.complex128)
        cfg=setup['cfg'];table={cfg.tags.air:cfg.eps_air,cfg.tags.substrate:cfg.eps_substrate,cfg.tags.grating:cfg.eps_grating}
        tags=setup['data'].cell_tags.values
        expected=np.asarray([table[int(tag)] for tag in tags])
        if self.coefficients.shape!=(len(tags),1) or not np.array_equal(self.coefficients[:,0],expected):
            raise ValueError('DG0 packed integral row/cell/material identity')
        setup['mesh'].topology.create_entity_permutations()
        self.permutations=setup['mesh'].topology.get_cell_permutation_info()
        self.calls=0
        code=a.code if isinstance(a.code,str) else '\n'.join(a.code)
        self.identity=dict(q=self.q,local_dim=self.dim,embedded_superdegree=setup['V'].element.basix_element.embedded_superdegree,
            form='inner(Ckappa(u),Ckappa(v))/mu-k0^2*eps*inner(u,v)',
            implementation='FFCx_complex128_packed_DG0_tetra_cell',compiled_code_sha256=hashlib.sha256(code.encode()).hexdigest(),
            coefficients_sha256=hashlib.sha256(self.coefficients.tobytes()).hexdigest(),num_coefficients=int(uf.num_coefficients),
            num_constants=int(uf.num_constants),full_body_assemble_matrix=0)

    def coordinates(self,c,*,translated=False):
        mesh=self.s['mesh'];x=mesh.geometry.x[mesh.geometry.dofmap[c]]
        if x.shape!=(4,3) or x.dtype!=np.float64:raise ValueError('actual tetra 4x3 float64 geometry')
        return np.ascontiguousarray(x-x[0] if translated else x)

    def key(self,c):
        # The weak form is independent of x for affine cells, constant kappa
        # and DG0 epsilon. No phase RHS or boundary is cached by this key.
        x=self.coordinates(c,translated=True)
        return hashlib.sha256(x.tobytes()+self.coefficients[c].tobytes()+
            np.asarray([self.permutations[c]],np.uint32).tobytes()).hexdigest()

    def tensor(self,c,*,translated=False):
        values=np.zeros((self.dim,self.dim),np.complex128)
        coords=self.coordinates(c,translated=translated);coef=self.coefficients[c]
        ffi=self.ffi
        ptr=lambda kind,array:ffi.cast(kind,ffi.from_buffer(array))
        self.kernel(ptr('double _Complex *',values),ptr('double _Complex *',coef),
            ptr('double _Complex *',self.constants) if self.constants.size else ffi.NULL,
            ptr('double *',coords),ffi.NULL,ffi.NULL,ffi.NULL)
        _orient_cell_tensor(self.s['V'].element,values,self.permutations[c:c+1])
        self.calls+=1
        if not np.isfinite(values).all():raise ValueError('nonfinite FFCx tetra tensor')
        return values
