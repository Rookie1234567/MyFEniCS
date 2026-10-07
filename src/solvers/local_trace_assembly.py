"""Entity-supported local restriction, before the global trace assembly.

The ambient cell LU/recovery is the established condensation implementation.
Only low-trace local matrices are inserted globally; no high Schur or global
Hermitian sparse triple product is constructed. Ordinary paths are unchanged.
"""
from dataclasses import dataclass
import numpy as np
from scipy import sparse
from scipy.linalg import lu_solve
from .scattering_anchor import relative


def entity_trace_support(low,high):
    """Exact functional support; face moments include closure edge moments."""
    support=np.zeros((high.dim,low.dim),bool)
    for dim in (1,2):
        for entity,rows in enumerate(high.entity_dofs[dim]):
            columns=low.entity_closure_dofs[dim][entity]
            support[np.ix_(rows,columns)]=True
    # The interior interpolation is not restricted by this trace predicate.
    support[high.entity_dofs[3][0],:]=True
    return support


def restrict_local(schur,lift):
    """Complex primal/dual restriction, with no magnitude sparsification."""
    return np.ascontiguousarray(lift.conj().T@schur@lift)


def cell_data(restriction):
    from .hcurl_assembly_time_condensation import _cell_trace_expansion
    return tuple(_cell_trace_expansion(ar,restriction.low_constraints)
        for ar,br,p in restriction.rows)


def exact_graph(data,nt,port_trace_rows,ports=828):
    """Count only topology/MPC incidence, not floating matrix magnitudes."""
    patterns=[set() for _ in range(nt+ports)]
    for ids,_,_ in data:
        cols=list(map(int,ids))
        for row in cols:patterns[row].update(cols)
    boundary=set(map(int,port_trace_rows));pp=list(range(nt,nt+ports))
    for row in boundary:patterns[row].update(pp)
    for row in pp:patterns[row].update(boundary);patterns[row].update(pp)
    counts=np.asarray([len(x) for x in patterns],np.int32)
    return counts,dict(actual_topology_nnz_envelope=int(counts.sum()),
        macro_local_trace_max=max(len(x[0]) for x in data),
        physical_boundary_support_rows=len(boundary),conservative_review_upper=34360848,
        upper_is_derived=True,no_matrix_clipping=True)


def carrier_terms(system,carrier):
    """Read MPC-dual carrier once, retaining nonmutual internal port terms."""
    from .p4_cell_condensed_inverse import CellPortTerms
    inside={int(r):(c,i) for c,cell in enumerate(system.cell_recovery_maps)
        for i,r in enumerate(cell.interior_original_dofs)}
    bi={};di={}
    for p,entry in enumerate(carrier.entries):
        for side,rows,values in (('B',entry.coupling_rows,entry.coupling_values),
                ('D',entry.projection_rows,entry.projection_values)):
            store=bi if side=='B' else di
            for row,value in zip(rows,values,strict=True):
                if int(row) in inside:
                    c,i=inside[int(row)];store.setdefault(c,{}).setdefault(p,{})[i]=value
    result={}
    for c in sorted(set(bi)|set(di)):
        ports=np.asarray(sorted(set(bi.get(c,{}))|set(di.get(c,{}))),int)
        n=len(system.cell_recovery_maps[c].interior_original_dofs)
        B=np.zeros((n,len(ports)),complex);D=np.zeros((len(ports),n),complex)
        for j,p in enumerate(ports):
            for i,v in bi.get(c,{}).get(int(p),{}).items():B[i,j]=v
            for i,v in di.get(c,{}).get(int(p),{}).items():D[j,i]=v
        result[c]=CellPortTerms(Bi=B,Di=D,port_indices=ports)
    return result,inside


def row_lift(R,row):
    ids,co=R.high_constraints.expansion_by_original[int(row)]
    # Carrier rows must already have C^H. A slave would apply that dual twice.
    if int(row) not in R.high_constraints.original_to_active:raise ValueError('carrier slave row')
    value=R.R.getrow(int(ids[0]))
    return value.indices,value.data


@dataclass
class LocalRestrictedSystem:
    ambient: object
    restriction: object
    matrix: object
    local_low: dict
    cell_data: tuple
    port_terms: dict
    build_audit: dict

    def body_action(self,t):
        y=np.zeros_like(t)
        for c,(ids,E,_) in enumerate(self.cell_data):
            key=self.ambient.cell_recovery_maps[c].class_key
            np.add.at(y,ids,E.conj().T@(self.local_low[key]@(E@t[ids])))
        return y

    def destroy(self):
        if self.matrix is not None:self.matrix.destroy();self.matrix=None
        self.ambient.destroy()


def assemble_local_restricted(ambient,R,carrier,journal):
    from petsc4py import PETSc
    data=cell_data(R);nt=R.R.shape[1];ports=len(carrier.entries)
    terms,inside=carrier_terms(ambient,carrier)
    boundary=set()
    for e in carrier.entries:
        for row in np.r_[e.coupling_rows,e.projection_rows]:
            if int(row) not in inside:boundary.update(map(int,row_lift(R,row)[0]))
    # Internal terms also have the trace support of their owning surface cell.
    for c in terms:boundary.update(map(int,data[c][0]))
    counts,graph=exact_graph(data,nt,boundary,ports)
    if graph['actual_topology_nnz_envelope']>graph['conservative_review_upper']:raise ValueError('local graph exceeds proven entity envelope')
    journal.allocation('low_entity_matrix',dict(matrix_payload_bytes=graph['actual_topology_nnz_envelope']*24,
        workspace_bytes=graph['actual_topology_nnz_envelope']*24))
    matrix=PETSc.Mat().createAIJ(size=(nt+ports,nt+ports),nnz=counts,comm=PETSc.COMM_SELF)
    matrix.setOption(PETSc.Mat.Option.NEW_NONZERO_ALLOCATION_ERR,True)
    local={}
    with journal.measured('local_restriction_direct_low_assembly'):
        for c,cell in enumerate(ambient.cell_recovery_maps):
            key=cell.class_key
            if key not in local:
                p=R.rows[c][2];local[key]=restrict_local(ambient.retained_local_schur_by_class[key],R.local[p])
                local[key].setflags(write=False)
            ids,E,_=data[c];block=np.ascontiguousarray(E.conj().T@(local[key]@E))
            matrix.setValues(ids,ids,block,addv=PETSc.InsertMode.ADD_VALUES)
        for p,e in enumerate(carrier.entries):
            matrix.setValue(nt+p,nt+p,e.normalization_h,addv=PETSc.InsertMode.ADD_VALUES)
            for side,rows,values in (('B',e.coupling_rows,e.coupling_values),('D',e.projection_rows,e.projection_values)):
                for row,value in zip(rows,values,strict=True):
                    if int(row) in inside:continue
                    ids,co=row_lift(R,row)
                    if side=='B':matrix.setValues(ids,[nt+p],np.ascontiguousarray(np.conj(co)*value),addv=PETSc.InsertMode.ADD_VALUES)
                    else:matrix.setValues([nt+p],ids,np.ascontiguousarray(-value*co),addv=PETSc.InsertMode.ADD_VALUES)
        for c,term in terms.items():
            cell=ambient.cell_recovery_maps[c];key=cell.class_key;p=R.rows[c][2];L=R.local[p]
            ids,E,_=data[c];xiB=lu_solve(ambient.interior_lu_by_class[key],term.Bi)
            b=L.conj().T@ambient.trace_from_interior_rhs_by_class[key]@term.Bi
            d=term.Di@ambient.interior_from_trace_by_class[key]@L
            matrix.setValues(ids,nt+term.port_indices,np.ascontiguousarray(E.conj().T@b),addv=PETSc.InsertMode.ADD_VALUES)
            matrix.setValues(nt+term.port_indices,ids,np.ascontiguousarray(-d@E),addv=PETSc.InsertMode.ADD_VALUES)
            matrix.setValues(nt+term.port_indices,nt+term.port_indices,np.ascontiguousarray(term.Di@xiB),addv=PETSc.InsertMode.ADD_VALUES)
        matrix.assemble()
    graph.update(measured_nnz=int(matrix.getInfo()['nz_used']),global_high_schur_present=False,global_sparse_projection_present=False,
        local_low_classes=len(local),local_low_payload_bytes=sum(x.nbytes for x in local.values()))
    journal.event('local_entity_assembly_inventory',**graph)
    return LocalRestrictedSystem(ambient,R,matrix,local,data,terms,graph)


class LocalRestrictedInverse:
    """Original high-cell recovery and low global solve, including affine load."""
    def __init__(self,system,factor=None):
        self.system=system;self.factor=factor;self.last_low_solution=None;self.last_port_solution=None
        self.xiB={c:lu_solve(system.ambient.interior_lu_by_class[system.ambient.cell_recovery_maps[c].class_key],t.Bi)
            for c,t in system.port_terms.items()}

    def reduce(self,rhs):
        s=self.system;R=s.restriction;a=s.ambient;high=np.asarray(rhs)[R.high_native_rows].copy()
        ports=np.zeros(a.appended_rows,complex)
        for c,cell in enumerate(a.cell_recovery_maps):
            gi=np.asarray(rhs)[cell.interior_original_dofs]
            correction=a.trace_from_interior_rhs_by_class[cell.class_key]@gi
            for row,value in zip(cell.trace_original_dofs,correction,strict=True):
                ids,co=a.trace_constraints.expansion_by_original[int(row)];np.add.at(high,ids,np.conj(co)*value)
            if c in s.port_terms:
                term=s.port_terms[c];ports[term.port_indices]+=term.Di@lu_solve(a.interior_lu_by_class[cell.class_key],gi)
        return np.r_[R.R.conj().T@high,ports]

    def recover(self,z,rhs):
        s=self.system;R=s.restriction;a=s.ambient;high=R.R@z[:R.R.shape[1]]
        out=np.zeros(a.full_rows,complex);out[R.high_native_rows]=high
        for c,cell in enumerate(a.cell_recovery_maps):
            t=np.asarray([np.dot(co,high[ids]) for row in cell.trace_original_dofs
                for ids,co in [a.trace_constraints.expansion_by_original[int(row)]]])
            v=a.interior_from_trace_by_class[cell.class_key]@t+lu_solve(a.interior_lu_by_class[cell.class_key],np.asarray(rhs)[cell.interior_original_dofs])
            if c in s.port_terms:v-=self.xiB[c]@z[R.R.shape[1]+s.port_terms[c].port_indices]
            out[cell.interior_original_dofs]=v
        return out

    def apply(self,rhs):
        from petsc4py import PETSc
        f=self.reduce(rhs.array);b=PETSc.Vec().createSeq(len(f),comm=PETSc.COMM_SELF);z=b.duplicate();b.array[:]=f
        try:
            self.factor.solve_repeated(b,z);self.last_low_solution=z.array.copy()
            self.last_port_solution=z.array[self.system.restriction.R.R.shape[1]:].copy()
            u=rhs.duplicate();u.array[:]=self.recover(z.array,rhs.array);return u
        finally:b.destroy();z.destroy()

    def destroy(self):
        self.xiB.clear();self.system.destroy()


def local_condense(bundle,R,journal,raw_tensor_provider):
    from dolfinx import fem
    from .hcurl_assembly_time_condensation import build_unconstrained_assembly_time_condensation
    V=bundle['setup']['spaces'][bundle['degree']];f=bundle['setup']['floquets'][bundle['degree']]
    with journal.measured('ambient_local_only_condensation'):
        a=build_unconstrained_assembly_time_condensation(fem.form(bundle['volume_action'].bilinear_form),V,
            bundle['setup']['mesh_data'].cell_tags,mpc=f.mpc,appended_global_rows=len(bundle['modes']),
            sum_duplicate_cell_integrals=True,strict_local_checks=True,geometry_identity_policy='raw_unrounded',share_identity_cache=True,
            retain_local_schur_for_matrix_free=True,retain_local_original_for_native_audit=True,materialize_global_matrix=False,
            raw_tensor_provider=raw_tensor_provider)
    if not np.array_equal(a.trace_constraints.owned_active_original_dofs,R.high_native_rows):raise ValueError('local ambient canonical trace identity')
    s=assemble_local_restricted(a,R,bundle['dtn_action'].carrier,journal)
    journal.owners('ambient_local_and_restricted_caches',s)
    return s,LocalRestrictedInverse(s)
