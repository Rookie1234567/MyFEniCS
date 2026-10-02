"""Qualified same-mesh p1 -> p3 interpolation, then canonical trace restriction.

Uses the certified active-column DOLFINx interpolation with drop tolerance ZERO.
MPI1 only. Owners assign a shared entity once; interpolation handles Piola and
all orientation transformations. No Maxwell form or accurate solve is built.
"""
from dataclasses import replace
from time import perf_counter
import numpy as np
from scipy.sparse import csr_matrix

from src.solvers.neural_fe_action_packet import array_hash
from src.solvers.p1_trace_galerkin import normalize_transfer,sparse_payload


def build_transfer(design,packet,*,guard=lambda:None,event=lambda **kw:None):
    import basix
    import basix.ufl
    import ufl
    from dolfinx import fem
    from mpi4py import MPI
    from petsc4py import PETSc
    from src.constraints.floquet_3d import build_double_floquet_mpc
    from src.solvers.neural_trace_dolfinx import pilot_space
    from src.solvers.neural_fe_pilot import physical_config
    from src.solvers.hcurl_multilevel import build_nonmatching_active_transfer,build_active_dof_map

    if MPI.COMM_WORLD.size!=1 or PETSc.ScalarType!=np.complex128:
        raise ValueError('existing complex128 MPI1 FE stack required')
    began=perf_counter();cfg,_=physical_config(design)
    _,data,fine,_,_,_,_=pilot_space(design)
    if (fine.dofmap.index_map.size_global!=packet.full_rows
        or not np.array_equal(fine.dofmap.list[:,packet.a['tpositions']],packet.a['tdofs'])
        or not np.array_equal(fine.dofmap.list[:,packet.a['ipositions']],packet.a['idofs'])):
        raise ValueError('recreated mesh/native p3 cell numbering changed')
    fine_bc=build_double_floquet_mpc(fine,data,cfg)
    coarse=fem.functionspace(data.mesh,basix.ufl.element('N1curl','hexahedron',1))
    coarse_cfg=replace(cfg,nedelec_degree=1,floquet_constraint_mode='auto')
    coarse_bc=build_double_floquet_mpc(coarse,data,coarse_cfg)
    active=build_active_dof_map(coarse_bc.mpc.function_space,np.asarray(coarse_bc.mpc.slaves))
    n1=active.global_active_size
    if not 0<n1<=2048:raise MemoryError('real p1 independent DOFs exceed 2048; no deletion')
    index={int(row):j for j,row in enumerate(active.local_full_dofs)}
    cr,cc,cv=[],[],[]
    for row,col in index.items():cr.append(row);cc.append(col);cv.append(1.+0j)
    coefficients,offsets=coarse_bc.mpc.coefficients()
    for slave in coarse_bc.mpc.slaves:
        masters=coarse_bc.mpc.masters.links(int(slave));vals=coefficients[offsets[slave]:offsets[slave+1]]
        for master,val in zip(masters,vals,strict=True):
            if int(master) not in index:raise ValueError('p1 MPC has unresolved slave master')
            cr.append(int(slave));cc.append(index[int(master)]);cv.append(val)
    E1=csr_matrix((cv,(cr,cc)),shape=(active.global_full_size,n1))
    supports=[len(np.unique(E1[coarse.dofmap.cell_dofs(cell)].indices)) for cell in range(packet.nc)]
    full_nnz_upper=sum(supports)*fine.element.space_dimension
    trace_nnz_upper=sum(supports)*packet.lt
    plan=dict(n1=n1,coarse_full_rows=active.global_full_size,
        full_transfer_nnz_upper=full_nnz_upper,full_transfer_sparse_bytes_upper=full_nnz_upper*24+(packet.full_rows+1)*8,
        trace_sparse_bytes_upper=trace_nnz_upper*24+(packet.nt+1)*8,
        support_bound='sum over p1 MPC-expanded cell support times complete fine cell dimension; shared rows not added twice',
        new_workspace_upper_bytes=7*n1*n1*16+full_nnz_upper*72+64*2**20)
    if plan['trace_sparse_bytes_upper']>128*2**20 or plan['new_workspace_upper_bytes']>2**30:
        raise MemoryError('p1 interpolation allocation plan exceeds reviewed capacity')
    event(event='p1_transfer_preallocation',capacity=plan)
    def progress(done,total):
        guard()
        if done%64==0 or done==total:event(event='p1_interpolation_column',done=done,total=total)
    transfer=build_nonmatching_active_transfer(fine_space=fine,coarse_space=coarse,
        fine_local_slave_dofs=np.asarray(fine_bc.mpc.slaves),coarse_local_slave_dofs=np.asarray(coarse_bc.mpc.slaves),
        fine_mpc=fine_bc.mpc,coarse_mpc=coarse_bc.mpc,relative_drop_tolerance=0.,progress=progress)
    try:
        indptr,indices,values=transfer.matrix.getValuesCSR()
        full=csr_matrix((values.copy(),indices.copy(),indptr.copy()),shape=transfer.matrix.getSize())
        if full.nnz>full_nnz_upper:raise MemoryError('interpolation support exceeded capacity model')
        slave=np.asarray(fine_bc.mpc.slaves,dtype=np.int64)
        if not np.array_equal(slave,np.sort(packet.a['slaves'])):
            if not np.array_equal(np.sort(slave),np.sort(packet.a['slaves'])):raise ValueError('p3 MPC inventory changed')
        witnesses=[];cf=fem.Function(coarse_bc.mpc.function_space);ff=fem.Function(fine_bc.mpc.function_space)
        independent=fem.Function(fine_bc.mpc.function_space)
        q,_=basix.make_quadrature(basix.CellType.hexahedron,15)
        def field_and_curl(f):
            curl=ufl.curl(f)
            expression=fem.Expression(ufl.as_vector([f[j] for j in range(3)]+[curl[j] for j in range(3)]),q)
            return expression
        coarse_expr=field_and_curl(cf);fine_expr=field_and_curl(ff)
        cells=np.arange(packet.nc,dtype=np.int32)
        for name,seed in [('p1-random-422201',422201),('p1-random-422202',422202),('single-edge',None)]:
            guard();rng=np.random.default_rng(seed)
            w=rng.normal(size=n1)+1j*rng.normal(size=n1) if seed else np.zeros(n1,complex)
            if seed is None:w[0]=.7+.3j
            cf.x.array[:]=0;cf.x.array[active.local_full_dofs]=w;coarse_bc.mpc.backsubstitution(cf);cf.x.scatter_forward()
            ff.x.array[:]=full@w;fine_bc.mpc.backsubstitution(ff);ff.x.scatter_forward()
            independent.x.array[:]=0;independent.interpolate(cf);independent.x.scatter_forward()
            expected=independent.x.array.copy();expected[slave]=0
            stored=full@w
            coefficient=float(np.linalg.norm(stored-expected)/max(np.linalg.norm(stored)+np.linalg.norm(expected),1e-300))
            ec=coarse_expr.eval(data.mesh,cells).reshape(packet.nc,len(q),6)
            ef=fine_expr.eval(data.mesh,cells).reshape(packet.nc,len(q),6)
            field=float(np.linalg.norm(ef[:,:,:3]-ec[:,:,:3])/max(np.linalg.norm(ef[:,:,:3])+np.linalg.norm(ec[:,:,:3]),1e-300))
            curl=float(np.linalg.norm(ef[:,:,3:]-ec[:,:,3:])/max(np.linalg.norm(ef[:,:,3:])+np.linalg.norm(ec[:,:,3:]),1e-300))
            coeff,off=fine_bc.mpc.coefficients();defects=[]
            for s in slave:
                ms=fine_bc.mpc.masters.links(int(s));defects.append(ff.x.array[s]-coeff[off[s]:off[s+1]]@ff.x.array[ms])
            mpc=float(np.linalg.norm(defects)/max(np.linalg.norm(ff.x.array),1e-300))
            witnesses.append(dict(name=name,coefficient_operation_relative=coefficient,field_operation_relative=field,
                curl_operation_relative=curl,MPC_expansion_relative=mpc,slave_zero_storage=float(np.max(abs(stored[slave]),initial=0)),
                complete_high_order_moments=True,independent_DOLFINx_same_mesh_interpolation=True))
        rng=np.random.default_rng(422204);x=rng.normal(size=n1)+1j*rng.normal(size=n1)
        y=rng.normal(size=packet.full_rows)+1j*rng.normal(size=packet.full_rows)
        Px=full@x;PHy=full.conj().T@y
        dual=float(abs(np.vdot(y,Px)-np.vdot(PHy,x))/max(np.linalg.norm(y)*np.linalg.norm(Px)+np.linalg.norm(PHy)*np.linalg.norm(x),1e-300))
        data.mesh.topology.create_entity_permutations();permutation=data.mesh.topology.get_cell_permutation_info()
        if not np.any(permutation):raise ValueError('actual interpolation contains no nonidentity direction witness')
        T0=full[packet.a['masters']];T,norms,rank=normalize_transfer(T0)
        checks=dict(status='PASS',capacity=plan,full_transfer_payload_bytes=sparse_payload(full),
            full_transfer_data_sha256=array_hash(full.data),full_transfer_shape=list(full.shape),
            p1_active_native_sha256=array_hash(active.local_full_dofs),fine_master_sha256=array_hash(packet.a['masters']),
            fine_cell_dofs_sha256=array_hash(fine.dofmap.list),p1_cell_dofs_sha256=array_hash(coarse.dofmap.list),
            Floquet_phase_x=coarse_bc.phase_x,Floquet_phase_y=coarse_bc.phase_y,
            nonidentity_orientation_cells=int(np.count_nonzero(permutation)),orientation_classes=len(np.unique(permutation)),
            full_complex_dual_operation_relative=dual,witnesses=witnesses,trace_rank=rank,
            no_drop_tolerance=0.,whole_transfer_seconds=perf_counter()-began,
            trace_restriction_is_not_interior_recovery=True,master_entity_owner='certified DOLFINx interpolation: assigned once, no additive owner sum')
        checks['qualified']=bool(dual<=1e-10 and all(max(r[k] for k in ('coefficient_operation_relative','field_operation_relative','curl_operation_relative','MPC_expansion_relative'))<=1e-10 and r['slave_zero_storage']==0 for r in witnesses))
        return T,norms,checks
    finally:
        transfer.matrix.destroy()
