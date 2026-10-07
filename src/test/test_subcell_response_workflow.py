"""Actual subcell workflow wiring, not only a dense block identity."""
import unittest
import numpy as np
from scipy.linalg import lu_solve
from src.solvers.subcell_macro_response import small_mesh
from src.solvers.subcell_response_kernel import MacroLayout,MacroResponse,ChildBlock,child_interpolation,transform


class Journal:
    from contextlib import nullcontext
    def measured(self,name):return self.nullcontext()
    def allocation(self,*args):pass


class SubcellWorkflow(unittest.TestCase):
    def test_actual_nonzero_legal_edge_to_face_cannot_be_dropped(self):
        import basix
        from src.solvers.local_trace_assembly import entity_trace_support
        from src.solvers.phase_p_order_consistency import interpolation_operator
        a=basix.create_element(basix.ElementFamily.N1E,basix.CellType.hexahedron,2)
        b=basix.create_element(basix.ElementFamily.N1E,basix.CellType.hexahedron,3)
        I=interpolation_operator(a,b);support=entity_trace_support(a,b);edge_rows=np.concatenate(a.entity_dofs[1])
        face_rows=np.concatenate(b.entity_dofs[2]);legal=I[np.ix_(face_rows,edge_rows)];mask=support[np.ix_(face_rows,edge_rows)]
        self.assertGreater(np.max(np.abs(legal[mask])),1e-6)
        self.assertTrue(np.array_equal(np.where(support,I,0)[np.ix_(face_rows,edge_rows)][mask],legal[mask]))
        self.assertGreater(np.linalg.norm(legal[mask]-np.zeros_like(legal[mask])),1e-6) # face-only support is a real counterexample

    def test_real_r2_native_map_and_nonzero_source_two_stage(self):
        V=small_mesh(np.array([[0.,0.,0.],[1.,1.,1.]]),2,2);el=V.element.basix_element
        layout=MacroLayout.build(V,np.arange(8),np.array([[0.,0.,0.],[1.,1.,1.]]))
        rng=np.random.default_rng(60027);blocks=[];A=np.zeros((len(layout.native_rows),len(layout.native_rows)),complex)
        for c,rows in zip(layout.cells,layout.child_rows,strict=True):
            raw=rng.normal(size=(el.dim,el.dim))+1j*rng.normal(size=(el.dim,el.dim))+100*np.eye(el.dim)
            B=ChildBlock(raw,el);blocks.append(B);A[np.ix_(rows,rows)]+=raw
        response=MacroResponse(layout,blocks,Journal(),response=True)
        inside=np.setdiff1d(np.arange(len(layout.native_rows)),layout.boundary);columns=layout.lift.shape[1]
        J=np.zeros((len(layout.native_rows),len(inside)+columns),complex);J[inside,np.arange(len(inside))]=1.;J[np.ix_(layout.boundary,np.arange(len(inside),J.shape[1]))]=layout.lift
        f=rng.normal(size=len(A))+1j*rng.normal(size=len(A));low,_=response.reduce(f)
        t=np.linalg.solve(response.low_schur,low);u=response.recover(t,f);direct=J@np.linalg.solve(J.conj().T@A@J,J.conj().T@f)
        self.assertLess(np.linalg.norm(u-direct)/np.linalg.norm(direct),1e-11)
        reaction,res=response.reaction(u,f);self.assertLess(np.linalg.norm(J.conj().T@res)/np.linalg.norm(J.conj().T@f),1e-11)
        self.assertGreater(np.linalg.norm(res),1e-6) # restricted solution has a real ambient defect
        # The deployed macro inverse consumes the actual two-stage response,
        # nonmutual 40-port blocks and nonzero internal/port particular loads.
        from types import SimpleNamespace as NS
        from scipy import sparse
        from petsc4py import PETSc
        from src.solvers.subcell_macro_deployment import MacroInverse
        C=np.zeros((len(A),40),complex);D=np.zeros((40,len(A)),complex)
        C[layout.boundary]=rng.normal(size=(len(layout.boundary),40))+1j*rng.normal(size=(len(layout.boundary),40))
        D[:,layout.boundary]=rng.normal(size=(40,len(layout.boundary)))+1j*rng.normal(size=(40,len(layout.boundary)))
        H=80*np.eye(40);reduced=np.block([[response.low_schur,layout.lift.conj().T@C[layout.boundary]],[-D[:,layout.boundary]@layout.lift,H]])
        M=NS(ninternal=len(inside),nt=columns,nmixed=J.shape[1],J=sparse.csr_matrix(J),pull_native=lambda v:J.conj().T@v,
            layouts=[layout],data=[(np.arange(columns),sparse.eye(columns),True)],transforms=[sparse.eye(columns)],internal_offsets=np.array([0,len(inside)]))
        class Factor:
            def solve_repeated(self,b,z):z.array[:]=np.linalg.solve(reduced,b.array)
        committed=[];inv=MacroInverse(M,[response],Factor(),ports=40,state_callback=lambda z,b,f:committed.append(z.copy()))
        rhs=PETSc.Vec().createSeq(len(A));rhs.array[:]=f;g=rng.normal(size=40)+1j*rng.normal(size=40)
        try:
            result=inv.apply(rhs,g);JA=np.block([[J,np.zeros((len(A),40))],[np.zeros((40,J.shape[1])),np.eye(40)]])
            full=np.block([[A,C],[-D,H]]);expected=JA@np.linalg.solve(JA.conj().T@full@JA,JA.conj().T@np.r_[f,g])
            self.assertEqual(len(committed),1);self.assertEqual(len(inv.last_port_solution),40)
            self.assertLess(np.linalg.norm(result.array-expected[:len(A)])/np.linalg.norm(expected),1e-11)
            self.assertLess(np.linalg.norm(inv.last_port_solution-expected[len(A):])/np.linalg.norm(expected),1e-11);result.destroy()
        finally:rhs.destroy()
        # Field interpolation uses the actual child geometry and T transforms.
        co=rng.normal(size=el.dim)+1j*rng.normal(size=el.dim);values={}
        for c,rows in zip(layout.cells,layout.child_rows,strict=True):
            x=V.mesh.geometry.x[V.mesh.geometry.dofmap[c]];lo=x.min(axis=0);h=x.max(axis=0)-lo
            M=transform(V,int(c))@child_interpolation(el,lo,h);v=M@co
            for row,value in zip(rows,v,strict=True):
                if int(row) in values:self.assertLess(abs(values[int(row)]-value),1e-10)
                else:values[int(row)]=value
        self.assertLess(layout.shared_boundary_operation,1e-12)


if __name__=='__main__':unittest.main()
