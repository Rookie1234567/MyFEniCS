"""Opt-in halo-only Maxwell Schur sums and real triangle impedance.

The input cell Schurs are the sealed original equation. Only saved halo cells
contribute to a local problem. Periodic mates are joined before deciding which
faces receive the fixed outgoing -i*k0*n boundary condition.
"""
from collections import OrderedDict

import numpy as np
from scipy import sparse


def classify_faces(facet_cells, mates, halo, physical_z):
    halo = set(map(int, halo)); physical_z = set(map(int, physical_z))
    boundary = []; internal = []; seen = set()
    for f, cells in enumerate(facet_cells):
        if f in seen: continue
        neighbor = list(map(int, cells)); pair = mates.get(f)
        if pair is not None:
            seen.add(pair); neighbor += list(map(int, facet_cells[pair]))
        inside = [c for c in neighbor if c in halo]
        if len(inside) == 2:
            internal.append((f, pair, inside[0], inside[1]))
        elif len(inside) == 1:
            if len(neighbor) == 1 and f not in physical_z:
                raise ValueError('unclassified exterior face: periodic mate missing')
            cell = inside[0]
            actual = f if cell in cells else pair
            boundary.append((actual, cell, 'physical_z' if actual in physical_z else 'artificial'))
        seen.add(f)
    return boundary, internal


def tangent_mass(values, weights, normal):
    """Physical basis rows, conjugate test, positive surface measure."""
    n = np.asarray(normal); n = n / np.linalg.norm(n)
    tang = values - np.einsum('qjc,c->qj', values, n)[:, :, None]*n
    return np.einsum('qja,qka,q->jk', tang.conj(), tang, weights)


def outward_symbol(normal, electric, k0, refractive_index):
    n = np.asarray(normal); n = n/np.linalg.norm(n)
    e = np.asarray(electric); e = e-n*np.dot(n,e)
    return np.cross(n, 1j*np.cross(k0*refractive_index*n, e)) + 1j*k0*refractive_index*e


class TriangleImpedance:
    """Exact-key bounded face tables; never use axis-aligned hex formulas."""
    def __init__(self, setup, *, cache_bytes=2*2**30):
        import basix
        from dolfinx.mesh import entities_to_geometry
        from .independent_tetra_reference import TetraEvaluator
        self.s=setup; self.ev=TetraEvaluator(setup['V'],0,setup['kappa'],quadrature_tables=False)
        self.element=setup['V'].element.basix_element
        self.verts=basix.cell.geometry(basix.CellType.tetrahedron)
        self.faces=basix.cell.topology(basix.CellType.tetrahedron)[2]
        self.tables={}; self.cache=OrderedDict(); self.cache_bytes=0; self.cap=cache_bytes
        mesh=setup['mesh']; mesh.topology.create_connectivity(2,3); mesh.topology.create_connectivity(3,2)
        self.fc=mesh.topology.connectivity(2,3); self.cf=mesh.topology.connectivity(3,2)
        nf=mesh.topology.index_map(2).size_local
        self.cells=[list(map(int,self.fc.links(f))) for f in range(nf)]
        xyz=mesh.geometry.x[entities_to_geometry(mesh,2,np.arange(nf,dtype=np.int32),False)]
        cfg=setup['cfg']; pending={}; self.mates={}
        for f,cells in enumerate(self.cells):
            if len(cells)!=1: continue
            points=xyz[f].copy()
            for axis,L in ((0,cfg.period_x),(1,cfg.period_y)):
                if np.all(points[:,axis]==0) or np.all(points[:,axis]==L):
                    points[:,axis]=0
                    key=(axis,tuple(sorted(map(tuple,points))))
                    if key in pending:
                        mate=pending.pop(key); self.mates[f]=mate; self.mates[mate]=f
                    else: pending[key]=f
                    break
        if pending: raise ValueError('exact periodic triangle mate inventory incomplete')
        self.physical_z=set(map(int,np.r_[setup['data'].facet_tags.find(cfg.tags.z_min),
                                         setup['data'].facet_tags.find(cfg.tags.z_max)]))
        self.trace=np.setdiff1d(np.arange(self.element.dim),self.element.entity_dofs[3][0])
        self.interior=np.asarray(self.element.entity_dofs[3][0])
        self.trace_index=np.full(self.element.dim,-1,np.int64); self.trace_index[self.trace]=np.arange(len(self.trace))
        self.structure_checked=set(); self.structure_rows=[]

    def geometry(self,c,facet,q):
        import basix
        local=int(np.flatnonzero(self.cf.links(c)==facet)[0])
        if q not in self.tables:
            xy,w=basix.make_quadrature(basix.CellType.triangle,q); table=[]
            for face in self.faces:
                tri=self.verts[face]
                ref=tri[0]+xy[:,0,None]*(tri[1]-tri[0])+xy[:,1,None]*(tri[2]-tri[0])
                table.append((self.element.tabulate(0,ref)[0],w))
            self.tables[q]=table
        tab,w=self.tables[q][local]; J,_,_=self.ev.geometry[c]; tri=self.verts[self.faces[local]]
        cross=np.cross(J@(tri[1]-tri[0]),J@(tri[2]-tri[0])); area=np.linalg.norm(cross); n=cross/area
        physical=tri@J.T+self.ev.geometry[c][1]
        center=self.s['geometry']['cell_centers'][c]
        if np.dot(n,physical.mean(axis=0)-center)<0: n=-n
        return local,tab,w*area,n,J

    def mass(self,c,facet,q=13):
        local,tab,w,n,J=self.geometry(c,facet,q)
        key=(q,local,J.tobytes(),int(self.ev.permutations[c]))
        closure=np.asarray(self.element.entity_closure_dofs[2][local],np.int64)
        if key in self.cache:
            M=self.cache.pop(key); self.cache[key]=M
            return closure,M,n
        T=self.ev.transform(c)
        basis=np.einsum('ij,qja->qia',T,tab)@np.linalg.inv(J)
        tang=basis-np.einsum('qjc,c->qj',basis,n)[:,:,None]*n
        if key not in self.structure_checked:
            outside=np.setdiff1d(np.arange(self.element.dim),closure)
            error=float(np.linalg.norm(tang[:,outside])/max(np.linalg.norm(tang[:,closure]),1e-300))
            self.structure_rows.append(dict(cell=c,local_face=local,q=q,omitted_tangential_relative=error,
                                           topology_closure_rows=len(closure),interior_rows=len(self.interior)))
            if error>1e-10: raise ValueError('interior/nonclosure trace is not structurally zero')
            self.structure_checked.add(key)
        M=tangent_mass(basis[:,closure],w,n)
        while self.cache and self.cache_bytes+M.nbytes>self.cap:
            _,old=self.cache.popitem(last=False); self.cache_bytes-=old.nbytes
        if M.nbytes>self.cap: raise MemoryError('one facet mass exceeds bounded cache')
        self.cache[key]=M; self.cache_bytes+=M.nbytes
        return closure,M,n

    def apply_direct(self,c,facet,coefficients,q=15):
        """Coefficient-first independent face vector, not the saved mass."""
        _,tab,w,n,J=self.geometry(c,facet,q)
        T=self.ev.transform(c); inverse=np.linalg.inv(J)
        u=np.einsum('qja,j->qa',tab,T.T@coefficients)@inverse
        tang=u-np.einsum('qa,a->q',u,n)[:,None]*n
        test=np.einsum('qa,ba->qb',tang,inverse)*w[:,None]
        r=np.einsum('qja,qa->j',tab.conj(),test)
        return T.conj()@r

    def impedance(self,c):
        cfg=self.s['cfg']; eps={cfg.tags.air:cfg.eps_air,cfg.tags.substrate:cfg.eps_substrate,cfg.tags.grating:cfg.eps_grating}
        n=np.sqrt(eps[int(self.s['data'].cell_tags.values[c])]/cfg.mu_r)
        if n.imag<0 or (n.imag==0 and n.real<0): n=-n
        return -1j*cfg.k0*n

    def boundary(self,patch):
        return classify_faces(self.cells,self.mates,patch['halo_cells'],self.physical_z)


def halo_matrix(service,patch,faces):
    """Actual subdomain volume sum; no call to global local_principal."""
    from petsc4py import PETSc
    ids=patch['ids']; mapping=np.full(service.nt,-1,np.int64); mapping[ids]=np.arange(len(ids))
    halo=patch['halo_cells']; boundary,internal=faces.boundary(patch)
    parts=[]; graph=np.zeros(len(ids),np.int64)
    for c in halo:
        _,_,active,E,key=service.cell_records[int(c)]
        rows=mapping[active]
        if np.any(rows<0): raise ValueError('saved halo outside patch ids')
        np.add.at(graph,rows,len(rows)); parts.append((int(c),rows,E,key))
    graph=np.minimum(graph,len(ids))
    A=PETSc.Mat().createAIJ(size=(len(ids),)*2,nnz=graph,comm=PETSc.COMM_SELF)
    A.setOption(PETSc.Mat.Option.NEW_NONZERO_ALLOCATION_ERR,True)
    try:
        for c,rows,E,key in parts:
            dense=E.toarray(); S=service.cache[key]['schur']
            A.setValues(rows,rows,dense.conj().T@S@dense,addv=PETSc.InsertMode.ADD_VALUES)
        for facet,c,kind in boundary:
            _,_,active,E,_=service.cell_records[c]; closure,M,n=faces.mass(c,facet,13)
            pull=E[faces.trace_index[closure]].tocsr()
            cols=np.unique(pull.indices); rows=mapping[active[cols]]; dense=pull[:,cols].toarray()
            A.setValues(rows,rows,faces.impedance(c)*(dense.conj().T@M@dense),addv=PETSc.InsertMode.ADD_VALUES)
        A.assemblyBegin(); A.assemblyEnd()
        ptr,col,val=A.getValuesCSR(); result=sparse.csr_matrix((val.copy(),col.copy(),ptr.copy()),shape=A.getSize())
    finally: A.destroy()
    tags=faces.s['data'].cell_tags.values
    material_internal=sum(tags[c]!=tags[d] for _,_,c,d in internal)
    return result,dict(halo_cells=len(halo),body_cell_ids=halo.tolist(),body_cells_outside_halo=0,
        boundary_faces=[list(x) for x in boundary],internal_faces=len(internal),
        internal_material_interfaces_no_impedance=int(material_internal),periodic_pairs_total=len(faces.mates)//2,
        artificial_faces=sum(k=='artificial' for _,_,k in boundary),physical_z_faces=sum(k=='physical_z' for _,_,k in boundary),
        rows=len(ids),nnz=result.nnz,formation='HALO_BODY_SCHUR_MINUS_I_K0_PASSIVE_TRIANGLE_TANGENTIAL_MASS',
        global_fine_K_reads=0,global_fine_S_reads=0,old_principal_matrix_reads=0,numeric_factors=0)


def independent_patch_action(setup,service,patch,faces,vector):
    """Original body vector after local interior recovery plus q15 face action."""
    from .tetra_coefficient_action import CoefficientBodyAction
    body=CoefficientBodyAction(setup,15)
    mapping=np.full(service.nt,-1,np.int64); mapping[patch['ids']]=np.arange(len(vector))
    result=np.zeros_like(vector); volume=np.zeros_like(vector); surface=np.zeros_like(vector)
    values={}
    for c in patch['halo_cells']:
        c=int(c); _,_,active,E,key=service.cell_records[c]; cache=service.cache[key]
        t=E@vector[mapping[active]]
        xi=-service.solve_local(cache,cache['it']@t)
        coef=np.zeros(faces.element.dim,complex); coef[faces.trace]=t; coef[faces.interior]=xi
        native=body.cell(c,coef)
        np.add.at(volume,mapping[active],E.conj().T@native[faces.trace]); values[c]=coef
    boundary,_=faces.boundary(patch); qrows=[]
    for facet,c,_ in boundary:
        _,_,active,E,_=service.cell_records[c]
        q15=faces.apply_direct(c,facet,values[c],15)
        q13=faces.apply_direct(c,facet,values[c],13)
        qrows.append(float(np.linalg.norm(q15-q13)/max(np.linalg.norm(q15),1e-300)))
        np.add.at(surface,mapping[active],faces.impedance(c)*(E.conj().T@q15[faces.trace]))
    result[:]=volume+surface
    return result,volume,surface,max(qrows,default=0.)
