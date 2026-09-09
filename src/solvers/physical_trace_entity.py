"""Fixed physical edge/face subspaces; matrix-free F=(I-EA)J, no trace matrix."""
import time
import warnings
import numpy as np
from scipy.linalg import lu_factor,lu_solve,LinAlgWarning
from .physical_bubble_particular import expand_primal
from .condensed_fine_reference import project_unconstrained_mpc_dual


def relative_defect(error,*terms):
    return float(np.linalg.norm(error)/max(sum(np.linalg.norm(t) for t in terms),np.finfo(float).tiny))


def checked_lu(matrix):
    """Physical pivoted LU only; no shifts or singular-factor fallback."""
    with warnings.catch_warnings():
        warnings.simplefilter('error',LinAlgWarning)
        factor=lu_factor(matrix)
    if not np.isfinite(factor[0]).all():raise ValueError('nonfinite physical LU')
    permuted=matrix.copy()
    for i,j in enumerate(factor[1]):permuted[[i,j]]=permuted[[j,i]]
    product=(np.tril(factor[0],-1)+np.eye(len(matrix)))@np.triu(factor[0])
    defect=relative_defect(permuted-product,permuted,product)
    if not np.isfinite(defect) or defect>1e-11:raise ValueError('physical LU factor residual failed')
    return factor,defect


def entity_injection(restrictions,dimension):
    """Fixed nullity of stacked geometric R restrictions; never reference-fitted."""
    stacked=np.vstack(restrictions)
    _,sigma,vh=np.linalg.svd(stacked,full_matrices=False)
    rank=stacked.shape[1]-dimension
    if rank<=0 or sigma[rank-1]<=1e-12*sigma[0] or (rank<len(sigma) and sigma[rank]>1e-12*sigma[0]):
        raise ValueError('fixed entity nullity/rank gap failed')
    J=vh[rank:].conj().T
    defect=relative_defect(stacked@J,stacked)*1/max(np.linalg.norm(J),np.finfo(float).tiny)
    if not np.isfinite(defect) or defect>1e-11:raise ValueError('RJ entity gate failed')
    return J,dict(rank=rank,nullity=dimension,singular_values=sigma,RJ_relative=defect)


def condensed_entity_block(A,Q,factor,columns):
    """Non-Hermitian local trace block and a physical F identity witness."""
    J=np.eye(len(A),dtype=complex)[:,columns]
    B=Q.conj().T@A@J;T=lu_solve(factor,B);F=J-Q@T
    schur=J.conj().T@A@J-(J.conj().T@A@Q)@T
    direct=F.conj().T@A@F
    facts=dict(QAF=relative_defect(Q.conj().T@A@F,B,(Q.conj().T@A@Q)@T),
        Schur=relative_defect(direct-schur,direct,schur),
        local_solve=relative_defect((Q.conj().T@A@Q)@T-B,B,(Q.conj().T@A@Q)@T))
    if not all(np.isfinite(v) and v<=1e-11 for v in facts.values()):raise ValueError('local physical trace Schur identity failed')
    return schur,facts


def cell_volume(value,mapping,cells,classes,*,adjoint=False):
    expanded=expand_primal(value,mapping);out=np.zeros_like(expanded)
    for rows,key in zip(mapping['dofmap'],cells,strict=True):
        A=classes[key]['A'];np.add.at(out,rows,(A.conj().T if adjoint else A)@expanded[rows])
    return project_unconstrained_mpc_dual(out,mapping)


def complete_pq(value,internal,internal_volume,coarse):
    """Generic CU(r); every callback uses this actual RHS, no saved fields."""
    e=internal(value)
    return e+coarse(value-internal_volume(e))


class CachedPhysicalTraceAction:
    """Borrow qualified cell A and the original streaming DtN; own no factors."""
    def __init__(self,mapping,cells,classes,dtn):
        self.mapping,self.cells,self.classes,self.dtn=mapping,cells,classes,dtn
        self.counts=dict(started=0,completed=0)
        self.seconds=dict(volume=0.,dtn=0.)

    def apply_into(self,source,target):
        self.counts['started']+=1
        start=time.perf_counter()
        try:value=cell_volume(source.array,self.mapping,self.cells,self.classes)
        finally:self.seconds['volume']+=time.perf_counter()-start
        start=time.perf_counter()
        try:self.dtn.apply(source,target)
        finally:self.seconds['dtn']+=time.perf_counter()-start
        target.array[:]+=value
        self.counts['completed']+=1


class PhysicalTraceEntities:
    """Borrow frozen classes/map; own 18 internal and 1566 tiny entity factors."""
    def __init__(self,mapping,cells,classes,entities,entity_dofs,carrier,*,sample,save,marker):
        self.mapping=mapping;self.cells=cells;self.classes=classes;self.sample=sample;self.save=save
        self.factors={};self.blocks=[];self.elapsed={}
        self.counts=dict(Q_LU=0,Q_setup_rhs=0,entity_LU=0,entity_setup_rhs=0,E=0,EH=0,Q_apply_rhs=0,
            volume=0,volume_adjoint=0,HT=0,entity_apply_rhs=0,F=0,FH=0)
        self.members={key:np.flatnonzero(np.asarray(cells)==key) for key in classes}
        local_blocks={};trace=np.arange(192)
        for index,(key,item) in enumerate(classes.items()):
            sample();marker('trace_Q_factor_started',dict(index=index))
            factor,defect=checked_lu(item['D']);self.factors[key]=factor;self.counts['Q_LU']+=1
            schur,facts=condensed_entity_block(item['A'],item['Q'],factor,trace);self.counts['Q_setup_rhs']+=192
            local_blocks[key]={(d,e):schur[np.ix_(cols,cols)].copy() for d in (1,2) for e,cols in enumerate(entity_dofs[d])}
            save(f'trace_class_{index:02d}',dict(class_key=key,D=item['D'],LU=factor[0],pivots=factor[1],factor_relative=defect,
                schur_facts=facts,blocks={str(d)+','+str(e):v for (d,e),v in local_blocks[key].items()}))
        slaves=set(mapping['slaves'].tolist())
        def local_map(rows,canonical):
            lookup={r:i for i,r in enumerate(canonical)};L=np.zeros((len(rows),len(canonical)),complex)
            for i,row in enumerate(rows):
                if int(row) not in slaves:L[i,lookup[int(row)]]=1
                else:
                    a,b=mapping['offsets'][row:row+2]
                    for target,phase in zip(mapping['masters'][a:b],mapping['coefficients'][a:b]):
                        if phase!=0:L[i,lookup[int(target)]]+=phase
            return L
        for index,entity in enumerate(entities):
            if index%32==0:sample();marker('trace_entity_factor_started',dict(index=index,total=len(entities)))
            dim=entity['dim'];rows=np.asarray(entity['independent_rows'],int);parts=[];restrictions=[]
            for incidence in entity['incidences']:
                cell=incidence['cell'];eid=incidence['local_entity'];key=cells[cell];cols=entity_dofs[dim][eid]
                L=local_map(mapping['dofmap'][cell][cols],rows)
                restrictions.append(classes[key]['R'][:,cols]@L);parts.append((key,eid,L))
            J,rj=entity_injection(restrictions,2 if dim==1 else 20)
            D=np.zeros((J.shape[1],J.shape[1]),complex)
            for key,eid,L in parts:
                local=L@J;D+=local.conj().T@local_blocks[key][dim,eid]@local
            volume=D.copy()
            for entry in carrier.entries if any(s in ('2min','2max') for s in entity['boundary_sides']) else ():
                c=np.zeros(len(rows),complex);p=np.zeros(len(rows),complex)
                _,i,j=np.intersect1d(rows,entry.coupling_rows,return_indices=True);c[i]=entry.coupling_values[j]
                _,i,j=np.intersect1d(rows,entry.projection_rows,return_indices=True);p[i]=entry.projection_values[j]
                D+=np.outer(J.conj().T@c,p@J)/entry.normalization_h
            factor,defect=checked_lu(D);self.counts['entity_LU']+=1
            witness=np.arange(1,len(D)+1)+1j;rhs=D@witness;solution=lu_solve(factor,rhs)
            self.counts['entity_setup_rhs']+=1
            solve_defect=relative_defect(D@solution-rhs,D@solution,rhs)
            save(f'trace_entity_{index:04d}',dict(dim=dim,rows=rows,J=J,incidences=entity['incidences'],R_gate=rj,
                D=D,volume=volume,DtN=D-volume,LU=factor[0],pivots=factor[1],factor_relative=defect,
                test_rhs=rhs,test_solution=solution,test_relative=solve_defect))
            if not np.isfinite(solve_defect) or solve_defect>1e-11:raise ValueError('entity physical solve gate failed')
            self.blocks.append(dict(rows=rows,J=J,D=D,factor=factor))
        del local_blocks

    def timed(self,name,callback):
        start=time.perf_counter()
        try:return callback()
        finally:self.elapsed[name]=self.elapsed.get(name,0.)+time.perf_counter()-start

    def E(self,value,*,adjoint=False):
        self.sample();self.counts['EH' if adjoint else 'E']+=1
        if self.counts['E']+self.counts['EH']>263:raise RuntimeError('fixed E/EH call cap')
        def action():
            out=np.zeros_like(value)
            for key,members in self.members.items():
                item=self.classes[key];Q=item['Q'];rows=self.mapping['dofmap'][members]
                rhs=Q.conj().T@value[rows].T;self.counts['Q_apply_rhs']+=len(members)
                alpha=lu_solve(self.factors[key],rhs,trans=2 if adjoint else 0)
                D=item['D'].conj().T if adjoint else item['D']
                defect=relative_defect(D@alpha-rhs,D@alpha,rhs)
                if not np.isfinite(defect) or defect>1e-11:raise ValueError('E/EH actual local residual failed')
                # Q is exactly zero on shared trace rows; only uniquely owned
                # cell interiors receive nonzero values. This also keeps the
                # kernel testable on a small shared-row fixture.
                local=(Q@alpha).T;out[rows]=local
            return out
        return self.timed('EH' if adjoint else 'E',action)

    def volume(self,value,*,adjoint=False):
        self.sample();name='volume_adjoint' if adjoint else 'volume';self.counts[name]+=1
        if self.counts['volume']+self.counts['volume_adjoint']>263:raise RuntimeError('fixed cached volume cap')
        return self.timed(name,lambda:cell_volume(value,self.mapping,self.cells,self.classes,adjoint=adjoint))

    def J(self,coefficients):
        out=np.zeros(len(self.mapping['offsets'])-1,complex)
        for block,c in zip(self.blocks,coefficients,strict=True):out[block['rows']]+=block['J']@c
        return out

    def JH(self,value):return [b['J'].conj().T@value[b['rows']] for b in self.blocks]

    def F(self,coefficients):
        self.counts['F']+=1;v=self.J(coefficients);return v-self.E(self.volume(v))

    def FH(self,value):
        self.counts['FH']+=1;return self.JH(value-self.volume(self.E(value,adjoint=True),adjoint=True))

    def apply(self,value):
        self.counts['HT']+=1
        if self.counts['HT']>65:raise RuntimeError('fixed H_T call cap exceeded')
        def action():
            rhs=self.FH(value);coefficients=[]
            for index,(block,r) in enumerate(zip(self.blocks,rhs,strict=True)):
                if index%64==0:self.sample()
                z=lu_solve(block['factor'],r);self.counts['entity_apply_rhs']+=1
                defect=relative_defect(block['D']@z-r,block['D']@z,r)
                if not np.isfinite(defect) or defect>1e-11:raise ValueError('H_T entity residual failed')
                coefficients.append(z)
            return self.F(coefficients)
        return self.timed('HT',action)

    def payload_bytes(self):
        roots={}
        def visit(v):
            if isinstance(v,np.ndarray):
                while isinstance(v.base,np.ndarray):v=v.base
                roots[id(v)]=v.nbytes
            elif isinstance(v,dict):
                for x in v.values():visit(x)
            elif isinstance(v,(tuple,list)):
                for x in v:visit(x)
        visit([self.classes,self.mapping,self.factors,self.blocks]);return sum(roots.values())
