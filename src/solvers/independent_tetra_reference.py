"""Opt-in complete tetrahedral phase Maxwell reference, without condensation.

Production is a standard UFL matrix; the oracle integrates a vector directly
with public Basix. Neither path consumes hex tensors, local factors or traces.
"""
from dataclasses import replace
from types import SimpleNamespace
import numpy as np
from scipy import sparse

from .scattering_anchor import relative, save_arrays
from .fixed_phase_fem import carrier, envelope_configuration


def configuration(spec, physical):
    from .scattering_anchor import configuration as base
    cfg = base(spec['case'], spec['degree'])
    axes = physical['geometry']['axes_nm']
    modes=spec.get('complete_modes',828)
    if modes not in (828,1188):raise ValueError('unknown complete tetra mode inventory')
    mm,nn={828:(11,4),1188:(13,5)}[modes]
    return replace(cfg, case_name='task042_v62_'+spec['case'].lower()+'_p'+str(spec['degree']),
        mesh_cell_type='tetrahedron', diffraction_order_max_m=mm, diffraction_order_max_n=nn,
        mesh_axis_x_values=tuple(axes['x']), mesh_axis_y_values=tuple(axes['y']),
        mesh_axis_z_values=tuple(axes['z']), mesh_axis_cell_counts=tuple(len(axes[a])-1 for a in ('x','y','z')))


def periodic_expansion(V, mpc):
    """Actual finalized complex primal P; only periodic redundant rows vanish."""
    from .target_boundary_witness import dual_maps
    n = V.dofmap.index_map.size_local
    masters = np.setdiff1d(np.arange(n), mpc.slaves)
    compact = np.full(n, -1, np.int64); compact[masters] = np.arange(len(masters))
    rr, cc, vv = [], [], []
    for row, (ids, dual) in enumerate(dual_maps(V, mpc)):
        if np.any(compact[ids] < 0): raise ValueError('unresolved periodic master')
        rr.extend([row]*len(ids)); cc.extend(compact[ids]); vv.extend(np.conj(dual))
    P = sparse.csr_matrix((vv, (rr, cc)), shape=(n, len(masters)), dtype=complex)
    return P, masters


def make_setup(spec, physical, journal):
    from mpi4py import MPI
    from dolfinx import fem, mesh as dm, default_real_type
    from basix.ufl import element
    from src.geometry.mesh_builder_3d import _structured_tet_mesh_from_axes, _mark_boundary_facets, _mark_cells
    from src.constraints.floquet_3d import build_double_floquet_mpc
    cfg = configuration(spec, physical); kappa = carrier(cfg)
    with journal.measured('tetra_mesh_materials_full_periodic_space'):
        mesh = _structured_tet_mesh_from_axes(MPI.COMM_SELF, *[np.asarray(physical['geometry']['axes_nm'][a]) for a in ('x','y','z')])
        facets, _ = _mark_boundary_facets(mesh, cfg); tags = _mark_cells(mesh, cfg)
        centers = dm.compute_midpoints(mesh, 3, tags.indices)
        regular = tags.values.copy(); values = regular.copy()
        if spec['case'] == 'FLAT': values[centers[:,2] > 0] = cfg.tags.air
        else:
            box = np.asarray(physical['geometry']['notch_box_nm']).reshape(3,2)
            hit = np.all((centers >= box[:,0]) & (centers <= box[:,1]), axis=1) & (regular == cfg.tags.grating)
            if hit.sum() != 24*spec['h_ratio']**3: raise ValueError('tet inherited true NOTCH volume inventory')
            values[hit] = cfg.tags.air
        tags = dm.meshtags(mesh, 3, tags.indices, values)
        V = fem.functionspace(mesh, element('N1curl', mesh.basix_cell(), spec['degree'], dtype=default_real_type))
        data = SimpleNamespace(mesh=mesh, cell_tags=tags, facet_tags=facets)
        floquet = build_double_floquet_mpc(V, data, envelope_configuration(cfg,kappa))
        P, masters = periodic_expansion(V, floquet.mpc)
        if P.shape[1] != spec['independent'] or mesh.topology.index_map(3).size_local != spec['cells']:
            raise ValueError('actual tetra FE/MPC inventory differs from planned topology')
    return dict(cfg=cfg, mesh=mesh, data=data, V=V, floquet=floquet, P=P, masters=masters, kappa=kappa,
        physical=physical, spec=spec, geometry=dict(geometry_x=mesh.geometry.x.copy(),geometry_dofmap=mesh.geometry.dofmap.copy(),
        cell_centers=centers,cell_tags=values,regular_tags=regular))


class TetraEvaluator:
    """Real affine 3x3 Jacobian, covariant Piola and native DOF orientation."""
    def __init__(self, V, q, kappa, *, quadrature_tables=True):
        import basix
        self.space=V; self.mesh=V.mesh; self.kappa=np.asarray(kappa,float)
        self.points,self.weights=basix.make_quadrature(basix.CellType.tetrahedron,q)
        self.mesh.topology.create_entity_permutations()
        self.permutations=self.mesh.topology.get_cell_permutation_info()
        self.geometry=[];self.transforms={};self.eval_checks=[]
        for ds in self.mesh.geometry.dofmap:
            x=self.mesh.geometry.x[ds];J=(x[1:]-x[0]).T;det=np.linalg.det(J)
            if not np.isfinite(det) or det==0: raise ValueError('degenerate tetra geometry')
            self.geometry.append((J,x[0].copy(),det))
        self.bounds=np.asarray([[self.mesh.geometry.x[d].min(axis=0),self.mesh.geometry.x[d].max(axis=0)] for d in self.mesh.geometry.dofmap])
        if quadrature_tables:
            tab=V.element.basix_element.tabulate(1,self.points)
            self.values=tab[0];self.curls=self.curl_table(tab)

    @staticmethod
    def curl_table(tab):
        return np.stack((tab[2,:,:,2]-tab[3,:,:,1],tab[3,:,:,0]-tab[1,:,:,2],tab[1,:,:,1]-tab[2,:,:,0]),axis=2)

    def transform(self,c):
        key=int(self.permutations[c])
        if key not in self.transforms:
            n=self.space.element.space_dimension;T=np.eye(n)
            self.space.element.T_apply(T.ravel(),self.permutations[c:c+1],n)
            self.transforms[key]=T
        return self.transforms[key]

    def physical(self,points,u,curl,k0):
        g=np.exp(1j*points@self.kappa)[:,None];ck=curl+1j*np.cross(self.kappa,u)
        return dict(E=g*u,H=g*ck/(1j*k0),curl=g*ck)

    def at(self,f,c,points,k0):
        J,o,det=self.geometry[c];ref=(np.asarray(points)-o)@np.linalg.inv(J).T
        tab=self.space.element.basix_element.tabulate(1,ref)
        coefficient=self.transform(c).T@f.x.array[self.space.dofmap.cell_dofs(c)]
        u=np.einsum('qjc,j->qc',tab[0],coefficient)@np.linalg.inv(J)
        curl=np.einsum('qjc,j->qc',self.curl_table(tab),coefficient)@J.T/det
        if len(self.eval_checks)<8:
            ix=np.unique([0,len(points)//2,len(points)-1]);native=f.eval(np.asarray(points)[ix],np.full(len(ix),c,np.int32))
            error=relative(u[ix]-native,native);self.eval_checks.append(error)
            if error>1e-11: raise ValueError('tetra native Piola/orientation witness')
        return self.physical(np.asarray(points),u,curl,k0)

    def cell(self,f,c,k0):
        J,o,det=self.geometry[c];p=self.points@J.T+o
        coef=self.transform(c).T@f.x.array[self.space.dofmap.cell_dofs(c)]
        u=np.einsum('qjc,j->qc',self.values,coef)@np.linalg.inv(J)
        curl=np.einsum('qjc,j->qc',self.curls,coef)@J.T/det
        return p,abs(det)*self.weights,self.physical(p,u,curl,k0)


class CachedTetraEvaluator(TetraEvaluator):
    """Reuse the qualified exact Basix polyset contraction on real tetra J."""
    def __init__(self,V,q,kappa,*,quadrature_tables=True):
        from .phase_evaluation_cache import ExactTabulations
        super().__init__(V,q,kappa,quadrature_tables=quadrature_tables)
        self.cache=ExactTabulations(limit_bytes=256*2**20);self.element=V.element.basix_element
        self.basis_coefficients=self.element.coefficient_matrix
        self.inverse=[np.linalg.inv(J) for J,_,_ in self.geometry];self.coefficients={}

    def at(self,f,c,points,k0):
        from .phase_evaluation_cache import CachedPhaseEvaluator
        return CachedPhaseEvaluator.at(self,f,c,points,k0)


class TriangleComponents:
    """Fresh complete Fourier functionals on actual tetra boundary triangles."""
    def __init__(self, setup, q, modes, *, compact=False):
        import basix
        from .target_boundary_witness import dual_maps
        self.s=setup;self.mpc=setup['floquet'].mpc;self.q=q;self.cache={}
        self.ev=TetraEvaluator(setup['V'],0,setup['kappa'],quadrature_tables=False)
        V=setup['V'];mesh=setup['mesh'];n=V.dofmap.index_map.size_local
        maps=dual_maps(V,self.mpc)
        from .tetra_boundary_support import side_supports,compact_index,support_row
        supports=side_supports(setup) if compact else {}
        self.support_inventory={}
        xy,w=basix.make_quadrature(basix.CellType.triangle,q)
        verts=basix.cell.geometry(basix.CellType.tetrahedron);faces=basix.cell.topology(basix.CellType.tetrahedron)[2]
        mesh.topology.create_connectivity(2,3);mesh.topology.create_connectivity(3,2)
        fc=mesh.topology.connectivity(2,3);cf=mesh.topology.connectivity(3,2)
        cfg=setup['cfg'];modes=list(modes)
        self.side_data={}
        for side,tag in (('top',cfg.tags.z_max),('bottom',cfg.tags.z_min)):
            selected={}
            for m in modes:
                if m.side==side:selected[(complex(m.alpha),complex(m.gamma),complex(m.k_vector[2]))]=m
            if side=='top':
                incident=SimpleNamespace(k_vector=cfg.wavevector)
                selected[(complex(cfg.kx),complex(cfg.ky),complex(cfg.kz))]=incident
            keys=list(selected);wave=np.array([selected[key].k_vector for key in keys])-setup['kappa']
            support=supports[side] if compact else np.arange(n,dtype=np.int64)
            index=compact_index(support,n)
            out=np.zeros((len(keys),len(support),2),complex)
            self.support_inventory[side]=dict(native=n,reachable_rows=len(support),keys=len(keys),buffer_bytes=out.nbytes,compact=compact)
            for facet in setup['data'].facet_tags.find(tag):
                cell=int(fc.links(int(facet))[0]);local=int(np.flatnonzero(cf.links(cell)==facet)[0])
                tri=verts[faces[local]];ref=tri[0]+xy[:,0,None]*(tri[1]-tri[0])+xy[:,1,None]*(tri[2]-tri[0])
                J,o,_=self.ev.geometry[cell];physical=ref@J.T+o
                area=np.linalg.norm(np.cross(J@(tri[1]-tri[0]),J@(tri[2]-tri[0])))
                basis=V.element.basix_element.tabulate(0,ref)[0]@np.linalg.inv(J)
                phase=np.exp(1j*wave@physical.T)*(w*area)[None,:]
                val=np.stack([phase@basis[:,:,j] for j in (0,1)],axis=2)
                val=np.einsum('ij,mjc->mic',self.ev.transform(cell),val)
                for j,row in enumerate(V.dofmap.cell_dofs(cell)):
                    masters,co=maps[int(row)]
                    for master,a in zip(masters,co,strict=True):out[:,support_row(index,int(master)),:]+=a*val[:,j,:]
            for i,key in enumerate(keys):
                rows=np.flatnonzero(np.any(out[i]!=0,axis=1));self.cache[(side,*key)]=(support[rows],out[i,rows].copy())
            self.side_data[side]=len(keys)
            del out

    def assemblers(self):
        provider=self
        class Component:
            def __init__(self,j): self.j=j
            def assemble_entries(self,mode,mpc):
                if mpc is not provider.mpc: raise ValueError('triangle MPC changed')
                rows,values=provider.cache[(mode.side,complex(mode.alpha),complex(mode.gamma),complex(mode.k_vector[2]))]
                return rows,values[:,self.j]
        return {(side,j):Component(j) for side in ('top','bottom') for j in (0,1)}

    def incident_traction(self):
        cfg=self.s['cfg'];rows,values=self.cache[('top',complex(cfg.kx),complex(cfg.ky),complex(cfg.kz))]
        ein=cfg.incident_amplitude*np.asarray(cfg.polarization_vector)
        traction=np.cross(1j*np.cross(np.asarray(cfg.wavevector),ein),[0.,0.,1.])
        result=np.zeros(self.s['P'].shape[0],complex);result[rows]=values@traction[:2]
        return result


def boundary(setup,q,journal,folder):
    from .fullspace_dtn_action import build_dynamic_mode_inventory,build_fullspace_dtn_carrier_from_surface
    from .scattering_accuracy_boundary import pack_carrier
    from .dtn_port_3d import _incident_projection_onto_top_mode
    modes,ids,digest=build_dynamic_mode_inventory(setup['cfg'])
    if len(modes)!=setup['spec']['complete_modes']:raise ValueError('tetra complete mode inventory mismatch')
    with journal.measured('fresh_triangle_all828_q'+str(q)):
        source=TriangleComponents(setup,q,modes,compact=setup['spec'].get('triangle_backend')=='reachable_owner_support')
        c=build_fullspace_dtn_carrier_from_surface(modes,source.assemblers(),setup['floquet'].mpc,setup['cfg'],retain_all_nonzero=True)
        incident=source.incident_traction()
    receipt=save_arrays(folder/('triangle_q'+str(q)+'.npz'),**pack_carrier(c),incident_traction=incident)
    projections=np.asarray([_incident_projection_onto_top_mode(m,setup['cfg']) for m in modes])
    return dict(carrier=c,modes=modes,identities=ids,digest=digest,incident=incident,projections=projections,arrays=receipt,q=q,support=source.support_inventory)


def boundary_matrices(s,b):
    masters=s['masters'];idx=np.full(s['P'].shape[0],-1,np.int64);idx[masters]=np.arange(len(masters))
    rr=[];cc=[];vv=[];dr=[];dc=[];dv=[]
    for j,e in enumerate(b['carrier'].entries):
        if np.any(idx[e.coupling_rows]<0) or np.any(idx[e.projection_rows]<0):raise ValueError('port on slave row')
        rr.extend(idx[e.coupling_rows]);cc.extend([j]*len(e.coupling_rows));vv.extend(e.coupling_values)
        dr.extend([j]*len(e.projection_rows));dc.extend(idx[e.projection_rows]);dv.extend(e.projection_values)
    n=len(masters);m=len(b['modes'])
    return sparse.csr_matrix((vv,(rr,cc)),shape=(n,m)),sparse.csr_matrix((dv,(dr,dc)),shape=(m,n)),np.array([e.normalization_h for e in b['carrier'].entries])


def production_body(s,journal):
    import ufl
    from dolfinx import fem
    import dolfinx.fem.petsc
    from petsc4py import PETSc
    V=s['V'];cfg=s['cfg'];mesh=s['mesh']
    dg=fem.functionspace(mesh,('DG',0));eps=fem.Function(dg)
    table={cfg.tags.air:cfg.eps_air,cfg.tags.substrate:cfg.eps_substrate,cfg.tags.grating:cfg.eps_grating}
    for c,t in zip(s['data'].cell_tags.indices,s['data'].cell_tags.values,strict=True):eps.x.array[dg.dofmap.cell_dofs(c)]=table[int(t)]
    u=ufl.TrialFunction(V);v=ufl.TestFunction(V);k=ufl.as_vector(tuple(PETSc.ScalarType(x) for x in s['kappa']))
    ck=lambda f:ufl.curl(f)+1j*ufl.cross(k,f)
    q=2*cfg.nedelec_degree+3
    if q<2*V.element.basix_element.embedded_superdegree:raise ValueError('tet body degree does not cover actual superdegree')
    form=(ufl.inner(ck(u),ck(v))/cfg.mu_r-cfg.k0**2*eps*ufl.inner(u,v))*ufl.dx(metadata={'quadrature_degree':q})
    with journal.measured('standard_UFL_FFCx_full_uncondensed_body'):
        a=fem.form(form,jit_options={'cache_dir':__import__('os').environ['FFCX_CACHE_DIR']})
        K=fem.petsc.assemble_matrix(a);K.assemble()
    try:
        ia,ja,va=K.getValuesCSR();native=sparse.csr_matrix((va.copy(),ja.copy(),ia.copy()),shape=K.getSize())
    finally:K.destroy()
    P=s['P'];pulled=(P.conj().T@native@P).tocsr()
    return pulled,dict(q=q,embedded_superdegree=V.element.basix_element.embedded_superdegree,
        form='inner(Ckappa(u),Ckappa(v))/mu-k0^2*eps*inner(u,v)',native_nnz=native.nnz,independent_nnz=pulled.nnz)


def body_action(s,x,q):
    """Public Basix vector integration; never reads a production matrix."""
    ev=TetraEvaluator(s['V'],q,s['kappa']);P=s['P'];native=P@np.asarray(x);out=np.zeros(P.shape[0],complex)
    cfg=s['cfg'];table={cfg.tags.air:cfg.eps_air,cfg.tags.substrate:cfg.eps_substrate,cfg.tags.grating:cfg.eps_grating}
    # Small exact-geometry/orientation basis cache; no local matrices or factors.
    from collections import OrderedDict
    cache=OrderedDict();cache_bytes=0;limit=512*2**20
    for c,tag in zip(s['data'].cell_tags.indices,s['data'].cell_tags.values,strict=True):
        J,_,det=ev.geometry[c];key=(J.tobytes(),int(ev.permutations[c]))
        if key not in cache:
            T=ev.transform(c);b=np.einsum('ij,qjc->qic',T,ev.values)@np.linalg.inv(J)
            curl=np.einsum('ij,qjc->qic',T,ev.curls)@J.T/det+1j*np.cross(s['kappa'],b)
            required=b.nbytes+curl.nbytes
            while cache and cache_bytes+required>limit:
                _,old=cache.popitem(last=False);cache_bytes-=sum(t.nbytes for t in old)
            if required>limit:raise MemoryError('one tetra oracle table exceeds bounded workspace')
            cache[key]=(b,curl);cache_bytes+=required
        cache.move_to_end(key)
        b,ck=cache[key];rows=s['V'].dofmap.cell_dofs(c);coef=native[rows]
        u=np.einsum('qjc,j->qc',b,coef);cu=np.einsum('qjc,j->qc',ck,coef)
        local=abs(det)*(np.einsum('q,qjc,qc->j',ev.weights,np.conj(ck),cu/cfg.mu_r)-cfg.k0**2*table[int(tag)]*np.einsum('q,qjc,qc->j',ev.weights,np.conj(b),u))
        np.add.at(out,rows,local)
    return P.conj().T@out


def full_action(s,b,x,*,q):
    n=s['P'].shape[1];u=x[:n];a=x[n:];C,D,H=boundary_matrices(s,b)
    return np.r_[body_action(s,u,q)+C@a,-D@u+H*a]


def rhs_vector(s,b):
    C,_,_=boundary_matrices(s,b)
    return np.r_[b['incident'][s['masters']]+C@b['projections'],np.zeros(len(b['modes']),complex)]


def assembly_capacity(s,journal):
    n=s['P'].shape[1];cells=s['spec']['cells'];dim=s['V'].element.space_dimension
    modes=s['spec']['complete_modes'];rows=n+modes
    compact=s['spec'].get('triangle_backend')=='reachable_owner_support'
    if compact:
        from .tetra_boundary_support import side_supports
        support=side_supports(s);sizes={k:len(v) for k,v in support.items()}
        if np.max(np.diff(s['P'].indptr))!=1:raise ValueError('capacity requires actual one-master tetra MPC')
        coupling=sum(2*(modes//2)*v for v in sizes.values())
        triangle=sum((modes//4+1)*v*2*16 for v in sizes.values())*3
    else:
        sizes={'full_native':s['P'].shape[0]};coupling=4*n*modes;triangle=6*s['P'].shape[0]*modes*16
    upper=cells*dim**2+coupling+modes
    components=dict(four_full_csr_envelopes=4*(upper*24+(rows+1)*8),
        triangle_functionals_and_copies=triangle,bounded_basis_evaluation_workspace=2*2**30,runtime_mesh_MPC_JIT_reserve=2*2**30)
    budget=s['spec'].get('memory_budget',dict(planning_gib=64,warning_gib=80,sampled_stop_gib=96))
    total=sum(components.values());r=dict(rows=rows,native=s['P'].shape[0],independent=n,cells=cells,local_dim=dim,
        graph_nnz_upper=upper,reachable_side_rows=sizes,body_cell_contribution_upper=cells*dim**2,boundary_coupling_upper=coupling,
        components=components,planned_bytes=total,memory_budget=budget,admitted=rows<=s['spec'].get('assembly_row_cap',200000) and total<=budget['planning_gib']*2**30,
        factor='SYMBOLIC_PENDING',condensation=False,compact_actual_allocation=compact)
    journal.event('full_tetra_assembly_capacity',**r);return r


def restore_field(s,x):
    from dolfinx import fem
    f=fem.Function(s['V']);f.x.array[:]=s['P']@x;f.x.scatter_forward();return f


def complete_residual_metrics(C,D,H,x,b,r):
    """Original closed equation, augmented equation and projected port scale.

    A zero physical port RHS must be measured against the nonzero projected
    field, never against its almost-zero balance residual.
    """
    n=D.shape[1];projected=D@x[:n]+b[n:]
    closed=r[:n]-C@(r[n:]/H)
    return dict(true=relative(closed,b[:n]),native=relative(closed,b[:n]),
        augmented=relative(r[:n],b[:n]),port=relative(r[n:],projected),
        full_augmented=relative(r,b)),closed,projected


def audit(s,oracle,x,rhs,journal):
    with journal.measured('independent_PUBLIC_BASIX_full_body_triangle_q63'):
        a=full_action(s,oracle,x,q=2*s['spec']['degree']+5);b=rhs_vector(s,oracle);r=b-a
    n=s['P'].shape[1];bn=max(np.linalg.norm(b),1e-300)
    identity=relative(rhs-b,rhs);C,D,H=boundary_matrices(s,oracle)
    metrics,closed,projected=complete_residual_metrics(C,D,H,x,b,r)
    coefficients,offsets=s['floquet'].mpc.coefficients();field=s['P']@x[:n];defects=[]
    for slave in s['floquet'].mpc.slaves:
        masters=s['floquet'].mpc.masters.links(int(slave))
        defects.append(field[slave]-np.dot(coefficients[offsets[slave]:offsets[slave+1]],field[masters]))
    constraint=float(np.linalg.norm(defects)/max(np.linalg.norm(field),1e-300))
    result=dict(**metrics,direct_target=max(metrics[k] for k in ('true','native','augmented','port'))<=1e-10,
        rhs_q47_q63=identity,MPC_identity=constraint,
        absolute_residual=float(np.linalg.norm(r)),original_rhs_norm=float(bn),backend='PUBLIC_BASIX_FULL_TETRA_VECTOR_Q'+str(2*s['spec']['degree']+5)+'_TRIANGLE63',
        closed_physical_residual_norm=float(np.linalg.norm(closed)),projected_port_norm=float(np.linalg.norm(projected)),
        pass_gate=max(metrics[k] for k in ('true','native','augmented','port'))<=1e-6 and identity<=1e-10 and constraint<=1e-10)
    journal.calls['A']+=1;return result,r,b

