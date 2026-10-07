"""Read-only old internal service and separately identified new face response.

The old lift is checked by the original reader, never relabelled. New cross
blocks come from the saved child Schur matrices, not the old 432-row response.
"""
import hashlib
import json
from pathlib import Path
import numpy as np
from scipy import sparse
from scipy.linalg import lu_solve
from .subcell_response_kernel import MacroResponse,ChildBlock
from .subcell_preparation_checkpoint import file_hash,complex_value
from .scattering_anchor import array_hash,relative,save_arrays
from .scattering_anchor_checks import checked_arrays
from src.runners.task042_shared import write_json


class ReadonlyInternalService:
    def __init__(self,parent,journal,table):
        self.parent,self.journal,self.table=parent,journal,table;self.children={};self.macros={};self.child_hits=0;self.macro_hits=0
        b=parent['local_schur_bank'];path=Path(b['path'])
        if file_hash(path)!=b['sha256']:raise ValueError('H2 bank identity')
        bank=json.loads(path.read_text());self.bank=bank
        if bank['trace_rows']!=32832 or bank['cell_count']!=160 or len(bank['cells'])!=160:raise ValueError('H2 internal service inventory')
        # Only the explicitly bound old preparation and successful H2 folder.
        from .local_subcell_scope import window as old_window,PLAN as old_plan
        inv=old_window.TMP/'H2_preparation_resume.json';snapshot=json.loads(inv.read_text())
        if snapshot['plan_sha256']!=file_hash(old_plan):raise ValueError('H2 original preparation plan')
        for name,h in snapshot['unchanged_math'].items():
            if file_hash(Path(__file__).resolve().parents[2]/name)!=h:raise ValueError('internal service original math changed')
        metadata=[Path(r['metadata_path']) for r in snapshot['children']]
        metadata+=sorted((Path(parent['arrays']['path']).parent/'child_complete_packets').glob('*.json'))
        for p in metadata:
            r=json.loads(p.read_text())
            if r['producer'] not in (snapshot['producer'],bank['source_sha']):raise ValueError('H2 child producer binding')
            if r['degree']!=table.element.degree or r['element_hash']!=int(table.element.hash()) or r['k0']!=table.k0 or complex_value(r['mu'])!=table.mu or complex_value(r['epsilon'])!=table.epsilon[r['tag']]:raise ValueError('H2 child live physical/basis identity')
            key=(r['tag'],r['permutation'],r['arrays']['members']['widths']['sha256'])
            if key in self.children and self.children[key]['arrays']['sha256']!=r['arrays']['sha256']:raise ValueError('different child packets for one exact identity')
            self.children[key]=r
        for cell in bank['cells']:
            packet=bank['classes'][cell['class']];meta=Path(packet['path']).with_suffix('.json');r=json.loads(meta.read_text())
            self.macros[(r['key'],r['tag'])]=(r,packet)
        self.binding=dict(parent_H2_arrays_sha256=parent['arrays']['sha256'],bank=dict(path=str(path),sha256=b['sha256']),
            stopped_preparation=dict(path=str(inv),sha256=file_hash(inv)),old_manifest_unchanged=True)
        journal.event('readonly_H2_internal_service_bound',**self.binding,child_classes=len(self.children),macro_classes=len(self.macros))

    def child(self,tag,widths,permutation):
        r=self.children.get((int(tag),int(permutation),array_hash(widths)))
        if r is None:return None
        a=checked_arrays(r['arrays'])
        if not np.array_equal(a['widths'],widths) or not np.array_equal(a['kappa'],self.table.kappa):raise ValueError('child exact live dimensions/carrier')
        with self.journal.measured('readonly_H2_child_factor_load'):obj=ChildBlock.from_checkpoint(a,self.table.element)
        self.child_hits+=1;return obj

    def macro(self,layout,tag,blocks):
        pair=self.macros.get((layout.key,int(tag)))
        if pair is None:return None
        r,receipt=pair
        with self.journal.measured('readonly_H2_second_factor_load'):
            obj=MacroResponse.from_checkpoint(layout,blocks,checked_arrays(receipt),r['capacity'])
        self.macro_hits+=1;return obj,receipt

    def record(self):return dict(**self.binding,child_factor_hits=self.child_hits,macro_factor_hits=self.macro_hits,new_LU_when_hit=0,
        old_lift_qualified_before_new_response=True,new_response_identity_separate=True)


def boundary_schur(layout,blocks):
    """Reassemble only local Sbb, with all shared child contributions."""
    position={int(r):i for i,r in enumerate(layout.boundary)};rr=[];cc=[];vv=[]
    for rows,B in zip(layout.child_traces,blocks,strict=True):
        selected=np.asarray([j for j,r in enumerate(rows) if int(r) in position],int)
        ids=np.asarray([position[int(rows[j])] for j in selected],int)
        rr.append(np.repeat(ids,len(ids)));cc.append(np.tile(ids,len(ids)));vv.append(B.S[np.ix_(selected,selected)].ravel())
    S=sparse.coo_matrix((np.concatenate(vv),(np.concatenate(rr),np.concatenate(cc))),shape=(len(layout.boundary),)*2).tocsr();S.sum_duplicates();S.sort_indices()
    return S


class FaceMacroResponse(MacroResponse):
    def __init__(self,layout,service,journal):
        if len(layout.boundary)!=1728 or len(layout.inside)!=756 or layout.lift.shape[1] not in (840,1248):raise ValueError('fixed enriched local inventory')
        old=service.layout
        for k in ('cells','native_rows','trace','boundary','inside'):
            if not np.array_equal(getattr(old,k),getattr(layout,k)):raise ValueError('new lift changed internal service layout')
        self.layout=layout;self.blocks=service.blocks;self.factor=service.factor;self.solve=lambda rhs:lu_solve(self.factor,rhs);self.Sib=service.Sib;self.Sbi=service.Sbi
        self.bi=service.bi;self.ji=service.ji;self.X=None;self.Sii=self.Sbb=None;self.response=True;self.sparse_inner=False
        self.backward=service.backward;self.rhs_relative=service.rhs_relative;self.capacity=dict(service.capacity)
        Sbb=boundary_schur(layout,self.blocks);columns=layout.lift.shape[1];self.low_schur=np.empty((columns,columns),complex)
        Lh=layout.lift.conj().T
        with journal.measured('new_face_response_16_columns_original_child_Sbb'):
            for j in range(0,columns,16):
                L=layout.lift[:,j:j+16].toarray();X=-self.solve(self.Sib@L)
                self.low_schur[:,j:j+16]=Lh@(Sbb@L+self.Sbi@X)
        self.low_schur.setflags(write=False)
        self.capacity.update(new_columns=columns,reused_internal_LU=True,column_batch_cap=16,full_dense_macro_D_resident=False,
            new_lift_data_hash=array_hash(layout.lift.data),old_lift_hash=array_hash(old.lift))
        # The old 432 columns must still reproduce the saved original response.
        old_pair=relative(self.low_schur[:432,:432]-service.low_schur,service.low_schur)
        self.qualification=dict(old_H2_local_Schur_relative=old_pair,old_LU_backward=self.backward,
            pass_gate=old_pair<=1e-10 and self.backward<=1e-10)
        if not self.qualification['pass_gate']:raise ValueError('new local response does not reproduce old H2 columns')
        self.local_witness=[]
        rng=np.random.default_rng(61029)
        for j in range(2):
            t=rng.normal(size=columns)+1j*rng.normal(size=columns);f=np.zeros(len(layout.native_rows),complex)
            if j==1:f=rng.normal(size=len(f))+1j*rng.normal(size=len(f))
            low,ft=self.reduce(f);u=self.recover(t,f)
            reaction=layout.lift.conj().T@(Sbb@u[layout.boundary]+self.Sbi@u[layout.inside]-ft[self.bi])
            err=relative(reaction-(self.low_schur@t-low),np.abs(self.low_schur)@np.abs(t)+np.abs(low))
            self.local_witness.append(err)
        if max(self.local_witness)>1e-10:raise ValueError('new face affine reaction/recovery not qualified')

    def bytes(self):
        L=self.layout.lift
        return (self.capacity['actual_second_factor_bytes']+self.low_schur.nbytes+sum(a.nbytes for a in (L.data,L.indices,L.indptr))+
            sum(a.nbytes for m in (self.Sib,self.Sbi) for a in (m.data,m.indices,m.indptr)))


class ParentMicroBoundaryProvider:
    """Rebind an immutable q47/q63 packet to the actual new live micro MPC."""
    def __init__(self,cfg,setup,folder,journal,parent):
        from .phase_boundary_checkpoint import StudyBoundaryProvider
        self.live=StudyBoundaryProvider(cfg,setup,folder,journal,entity_face_support=True)
        self.parent=parent;self.folder=Path(parent['boundary']['provider_folder']);self.loads={}
        self.live.load=self.load
    def load(self,q):
        from .phase_boundary_checkpoint import LoadedSurface
        p=self.folder/f'q{q}.json';r=json.loads(p.read_text());identity=self.live.identity(q)
        producer=self.parent.get('solve_source_sha',self.parent['source_sha'])
        if r['identity']['producer_source']!=producer:raise ValueError('parent micro boundary original producer')
        identity['producer_source']=producer
        with self.live.journal.measured(f'readonly_parent_micro_boundary_q{q}'):
            obj=LoadedSurface(p,self.live.V,self.live.mpc,self.live.cfg,q,self.live.k,identity)
        self.loads[q]=self.loads.get(q,0)+1;return obj
    def bundle(self,q):return self.live.bundle(q)
    def generate_pair(self):
        # The actual identity and byte arrays are checked in each independent
        # reload. The old mathematical quadrature qualification is retained.
        self.load(47);self.load(63)
        r=dict(self.parent['boundary']);r.update(parent_qualification_only=True,parent_provider_folder=str(self.folder),
            provider_folder=str(self.folder),generated_this_case=0,live_reloads=dict(self.loads),parent_H2_array_sha256=self.parent['arrays']['sha256'])
        write_json(self.live.folder/'readonly_parent_binding.json',r);return r


def prepare_responses(mapping,W,mgeo,raw_factory,journal,folder,parent):
    from .subcell_macro_response import blocks_for
    reader=ReadonlyInternalService(parent,journal,raw_factory);children={};responses=[];packets={};checks=[];new_secondary=0
    for c,(old,new) in enumerate(zip(mapping.original_layouts,mapping.layouts,strict=True)):
        tag=int(mgeo['cell_tags'][c]);blocks=blocks_for(W,old,tag,raw_factory,children,journal,checkpoint_reader=reader,retain_raw=False)
        previous=reader.macro(old,tag,blocks)
        if previous is None:
            # Only a genuinely missing class, never a wholesale new H2.
            previous=(MacroResponse(old,blocks,journal),None)
            new_secondary+=1
            journal.event('missing_H2_internal_class_built_once',cell=c,tag=tag,key=old.key)
        service,oldpacket=previous;response=FaceMacroResponse(new,service,journal)
        d=folder/'local_response_packets';d.mkdir(exist_ok=True)
        packet=save_arrays(d/(str(c)+'.npz'),macro_schur=response.low_schur)
        metadata=dict(key=new.key,internal_key=old.key,tag=tag,internal_parent_arrays=oldpacket,capacity=response.capacity,
            qualification=response.qualification,recovery_witness=response.local_witness,new_global_factor=False)
        write_json(d/(str(c)+'.json'),metadata);packets[id(response)]=packet;responses.append(response);checks.append(response.qualification)
        current=sum(r.bytes() for r in responses)+sum(b.bytes() for b in children.values())+sum(l.lift.nbytes for l in mapping.original_layouts)+mapping.check['csr_primal_dual_bytes']
        # Shared basis blocks and old service matrices remain included in this
        # conservative cache envelope (not confused with sampled tree RSS).
        owners={}
        for f in mapping.faces:
            for v in (f['P'],f['G'],f['Z']):owners[(v.__array_interface__['data'][0],v.nbytes)]=v.nbytes
        current+=sum(owners.values())
        if current>16*2**30:raise MemoryError('face cache exceeds frozen 16GiB local cap')
        journal.event('new_face_local_response_committed',cell=c,classes=len(responses),child_classes=len(children),cache_explicit_upper_bytes=current)
    record=dict(internal_service=reader.record(),class_qualifications=checks,cache_explicit_upper_bytes=current,
        new_secondary_LU=new_secondary,new_child_LU=len(children)-reader.child_hits)
    write_json(folder/'internal_service_consumption.json',record)
    return responses,packets,record


def public_local_witness(V,response,cfg,tag,kappa,folder):
    """One original micro macro, direct Basix integrals; no raw/Schur oracle."""
    import basix
    from .subcell_response_kernel import transform
    layout=response.layout;el=V.element.basix_element;p,w=basix.make_quadrature(basix.CellType.hexahedron,15)
    tab=el.tabulate(1,p);v=tab[0];c=np.stack((tab[2,:,:,2]-tab[3,:,:,1],tab[3,:,:,0]-tab[1,:,:,2],tab[1,:,:,1]-tab[2,:,:,0]),axis=2)
    rng=np.random.default_rng(61031);t=rng.normal(size=layout.lift.shape[1])+1j*rng.normal(size=layout.lift.shape[1]);f=rng.normal(size=len(layout.native_rows))+1j*rng.normal(size=len(layout.native_rows))
    u=response.recover(t,f);curl=np.zeros_like(u);mass=np.zeros_like(u)
    eps={cfg.tags.air:cfg.eps_air,cfg.tags.substrate:cfg.eps_substrate,cfg.tags.grating:cfg.eps_grating}[tag]
    for cell,rows in zip(layout.cells,layout.child_rows,strict=True):
        xyz=V.mesh.geometry.x[V.mesh.geometry.dofmap[cell]];h=xyz.max(axis=0)-xyz.min(axis=0);det=np.prod(h)
        b=v/h;ck=c*h/det+1j*np.cross(kappa,b);T=transform(V,int(cell));co=T.T@u[rows]
        E=np.einsum('qjc,j->qc',b,co);C=np.einsum('qjc,j->qc',ck,co)
        np.add.at(curl,rows,T@(det/cfg.mu_r*np.einsum('q,qjc,qc->j',w,np.conj(ck),C)))
        np.add.at(mass,rows,T@(-det*cfg.k0**2*eps*np.einsum('q,qjc,qc->j',w,np.conj(b),E)))
    reaction=layout.lift.conj().T@(curl+mass-f)[layout.boundary];low,_=response.reduce(f);pred=response.low_schur@t-low
    internal=np.setdiff1d(np.arange(len(u)),layout.boundary)
    scale=np.abs(curl)+np.abs(mass)+np.abs(f)
    r=dict(interface_operation=relative(reaction-pred,np.abs(layout.lift).T@scale[layout.boundary]),
        internal_operation=relative((curl+mass-f)[internal],scale[internal]),q=15,no_saved_raw_or_reference_Gram=True,
        arrays=save_arrays(folder/'one_macro_public_body_witness.npz',trace=t,source=f,field=u,curl_action=curl,mass_action=mass,interface=reaction,predicted=pred))
    r['pass_gate']=max(r['interface_operation'],r['internal_operation'])<=1e-10
    if not r['pass_gate']:raise ValueError('new face response differs from original PUBLIC_BASIX body')
    return r
