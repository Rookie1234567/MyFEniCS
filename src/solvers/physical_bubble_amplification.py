"""One saved-direction left-restriction diagnosis, never a solver/PC entry."""
from pathlib import Path
import time
import numpy as np
from .physical_bubble_particular import (saved_packet_reader,expand_primal,gram_report,
    ROOT,READOUT,READOUT_SHA)
from .condensed_fine_reference import project_unconstrained_mpc_dual
from .physical_bubble_global import BubbleEnrichedSpace

PARTICULAR_SOURCE='55a795e5b31b5c6b0323b92c517f6e989faf5803'
PARTICULAR_ROOT=Path('benchmarks/artifacts/task39extra/v6_bubble_particular_diagnostic')/PARTICULAR_SOURCE/'a2r160_g1'
PARTICULAR_READOUT=Path('benchmarks/artifacts/task39extra/v6_recursive/bubble_particular_readout.json')
PARTICULAR_HASH='a64486272a45e6449e6da606115b8c2f2a2dcf64535de416d61975ee0ced7150'


def combine_full_pq(Eg,Cg,delta):
    """CUg=Eg+Cg-CW(AEg); W^H is not the non-Hermitian left restriction."""
    if not (Eg.shape==Cg.shape==delta.shape) or not all(np.isfinite(v).all() for v in (Eg,Cg,delta)):
        raise ValueError('invalid fixed-direction vectors')
    return Eg+Cg-delta


def saved_cell_action(value,mapping,cells,classes):
    """Row-complete cell sum followed by exactly one conjugate MPC dual map."""
    expanded=expand_primal(value,mapping);out=np.zeros_like(expanded)
    for rows,key in zip(mapping['dofmap'],cells,strict=True):
        np.add.at(out,rows,classes[key]['S']@expanded[rows])
    return project_unconstrained_mpc_dual(out,mapping)


class SavedBubbleSpace(BubbleEnrichedSpace):
    """Borrow insertion/lifetime code, without running the class constructor."""
    def __init__(self,levels,classes,cells,mapping,dtn,*,sample,save,fixed_serial_owner_route=False):
        from .fullspace_same_mesh_hcurl_pmg import build_same_mesh_hcurl_transfer
        from .fullspace_same_mesh_hcurl_pmg_runtime import SameMeshHcurlOwnerTransfer
        from .fullspace_physical_intermediate_runtime import AlgebraicOwnerTransfer
        self.owner=None;self.levels=levels;self.classes=classes
        self.cells=dict(enumerate(cells));self.mapping=mapping;self.dtn=dtn
        self.sample=sample;self.save=save;self.action_count=0;self.action_seconds=0.
        self.retained_bytes=sum(v[k].nbytes for v in classes.values() for k in ('W','delta','S'))+16*1024**2
        def provider(cell,info,base):
            item=classes[cells[cell]]
            if info!=item['cell_info'] or np.linalg.norm((item['W']-base)[:192])>1e-12*np.linalg.norm(base):
                raise ValueError('saved W orientation/trace differs')
            return item['W']
        self.owner=SameMeshHcurlOwnerTransfer(levels['spaces'][4],levels['floquets'][4],
            levels['spaces'][2],levels['floquets'][2],build_same_mesh_hcurl_transfer(4,2),cell_matrix_provider=provider,
            fixed_serial_owner_route=fixed_serial_owner_route)
        self.transfer=AlgebraicOwnerTransfer(self.owner)

    def apply_into(self,source,target):
        self.sample();self.action_count+=1;start=time.perf_counter()
        try:
            self.dtn.apply(source,target)
            target.array[:]+=saved_cell_action(source.array,self.mapping,list(self.cells.values()),self.classes)
            self.sample()
        finally:self.action_seconds+=time.perf_counter()-start


def run_amplification_diagnostic(cfg,comm,binding_path,directory,*,sample,marker):
    from src.runners.physical_diagnosis_worker import save_packet
    from src.runners.physical_recursive_controls import load_p4_failure_input,verify_recursive_map
    from .fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels
    from .fullspace_same_mesh_hcurl_pmg_physical import _surface_assemblers
    from .fullspace_same_mesh_hcurl_pmg_setup import SAME_MESH_JIT_OPTIONS
    from .dtn_port_3d import _dtn_surface_quadrature_degree
    from .fullspace_dtn_action import build_dynamic_mode_inventory,build_fullspace_dtn_carrier_from_surface,build_fullspace_dtn_action
    from .fullspace_p4_reference import build_reference_matrix
    from .physical_recursive_coarse import PhysicalP2Inverse
    from .fullspace_physical_intermediate_runtime import level_vector
    from .fullspace_physical_intermediate import apply_owned
    from .condensed_fine_reference import native_map_arrays
    from .physical_error_metric import LosslessFEMetric
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=False)
    save=lambda n,f:save_packet(directory,n,f)
    space=matrix=bottom=dtn=metric=None;vectors=[]
    counts=dict(A4=0,H4=0,H6=0,I4=0,outer=0,local_LU=0,class_requalification=0,factor=0,metric_actions=0)
    elapsed={}
    def timed(name,fn):
        start=time.perf_counter()
        try:return fn()
        finally:elapsed[name]=elapsed.get(name,0.)+time.perf_counter()-start
    def keep(v):vectors.append(v);return v
    def check(name,actual,expected):
        rel=float(np.linalg.norm(actual-expected)/max(np.linalg.norm(expected),np.finfo(float).tiny))
        save(name,dict(actual=actual,expected=expected,relative=rel,limit=1e-10))
        if not np.isfinite(rel) or rel>1e-10:raise ValueError(name+' identity failed')
    try:
        if comm.size!=1:raise ValueError('fixed MPI1 diagnosis')
        old=saved_packet_reader(ROOT,READOUT,READOUT_SHA)
        particular=saved_packet_reader(PARTICULAR_ROOT,PARTICULAR_READOUT,PARTICULAR_HASH)
        data=load_p4_failure_input(binding_path);cg=old('bubble_Cg');eg=particular('particular_E_0')
        if not np.array_equal(eg['rhs'],cg['rhs']):raise ValueError('frozen g differs')
        marker('amplification_metadata_started',{})
        levels=_build_same_mesh_levels(cfg,comm,(4,2),include_positive_coefficients=False)
        mapping=verify_recursive_map(dict(levels=levels),4,data['map'])
        save('amplification_map_bridge',dict(relative_error=0.,mapping=mapping,binding=data['binding']))
        p2map=native_map_arrays(levels['spaces'][2],levels['floquets'][2]);save('amplification_p2_map',p2map)
        saved_map=particular('particular_class_map');cells=saved_map['cell_classes'];classes={};quadrature=None
        for i in range(18):
            sample();prefix=f'bubble_class_{i:03d}'
            identity=old(prefix+'_identity');key=identity['sha256'];retained=old(prefix+'_retained');h=old(prefix+'_bubble_harmonic')
            if identity['key']!=saved_map['identities'][key]:raise ValueError('saved class key differs')
            source_quadrature=identity['key']['quadrature']
            if quadrature is None:quadrature=source_quadrature
            if source_quadrature!=quadrature:raise ValueError('saved class quadratures differ')
            classes[key]=dict(W=retained['W'],delta=retained['delta'],S=h['S'],cell_info=identity['key']['orientation'])
            del h
        if quadrature!=[dict(quadrature_degree=15,quadrature_rule='default')]*2:
            raise ValueError('saved source quadrature is not frozen 15/default')
        save('amplification_quadrature_bridge',dict(quadrature=quadrature,source_readout_hash=READOUT_SHA,classes=18))
        modes,rows,sha=build_dynamic_mode_inventory(cfg)
        if sha!=data['binding']['mode_sha256'] or len(modes)!=80:raise ValueError('frozen 80 mode identity differs')
        marker('amplification_p2_carrier_started',{})
        assemblers=_surface_assemblers(levels['spaces'][2],levels['mesh_data'],cfg,
            _dtn_surface_quadrature_degree(cfg,list(modes)),jit_options=SAME_MESH_JIT_OPTIONS)
        carrier=build_fullspace_dtn_carrier_from_surface(modes,assemblers,levels['floquets'][2].mpc,cfg);del assemblers
        dtn=build_fullspace_dtn_action(carrier,comm=comm)
        save('amplification_carrier',dict(mode_sha256=sha,mode_rows=rows,global_rows=carrier.global_rows,
            entries=[dict(mode_key=e.mode_key,mode_identity=dict(e.mode_identity),coupling_rows=e.coupling_rows,
                coupling_values=e.coupling_values,projection_rows=e.projection_rows,projection_values=e.projection_values,
                normalization_h=e.normalization_h) for e in carrier.entries]))
        space=SavedBubbleSpace(levels,classes,cells,p2map,dtn,sample=sample,save=save)
        transfer=space.transfer
        matrix,facts=build_reference_matrix(levels,cfg,dict(dtn_action=dtn),quadrature,
            marker=marker,sample=sample,degree=2,row_cap=8192,cell_volume_correction=space.insert_volume,
            extra_local_bytes=space.retained_bytes)
        pointers,indices,values=matrix.getValuesCSR()
        save('amplification_S_CSR',dict(indptr=pointers,indices=indices,values=values,shape=matrix.getSize(),facts=facts))
        if matrix.getSize()!=(7326,7326) or facts['allocated_nnz']!=818100:raise ValueError('old S graph size differs')
        probe=old('bubble_S_assembly_identity');q=keep(level_vector(levels,2));q.array[:]=probe['q']
        image=keep(apply_owned(space,q));check('amplification_saved_S_action',image.array,probe['composed'])
        aug=keep(matrix.createVecRight());applied=keep(aug.duplicate());aug.set(0);n=q.getLocalSize();aug.array[:n]=q.array
        for j,e in enumerate(carrier.entries):aug.array[n+j]=np.dot(e.projection_values,q.array[e.projection_rows])/e.normalization_h
        matrix.mult(aug,applied);check('amplification_saved_S_matrix',applied.array,probe['assembled'])
        check('amplification_S_matrix_cell',applied.array[:n],image.array)
        range_probe=old('bubble_range_identity');q.array[:]=range_probe['q']
        w=keep(transfer.apply_primal(q));check('amplification_saved_Wq',w.array,range_probe['Wq'])
        ae=keep(level_vector(levels,4));ae.array[:]=eg['AEr'];b=keep(transfer.apply_adjoint(ae))
        unchanged=bool(np.array_equal(ae.array,eg['AEr']))
        left=w.dot(ae);right=q.dot(b)
        check('amplification_actual_adjoint',np.asarray([left]),np.asarray([right]))
        save('amplification_coarse_rhs',dict(AEg=ae.array.copy(),rhs=b.array.copy(),owner=dict(space.owner.audit),input_unchanged=unchanged))
        if not unchanged:raise ValueError('WH modified saved AEg')
        counts['factor']+=1
        bottom=PhysicalP2Inverse(matrix,space,transfer.coarse_slaves,sample=sample,marker=marker,save=save,
            action_identity='saved_S_cell_plus_p2_DtN',extra_local_bytes=space.retained_bytes)
        z=keep(timed('bottom_apply',lambda:bottom.apply(b)));delta=keep(transfer.apply_primal(z))
        cu=combine_full_pq(eg['Er'],cg['solution'],delta.array)
        y=np.zeros_like(cu);y[mapping['independent_indices']]=data['arrays']['y']
        validation=dict(finite=bool(np.isfinite(cu).all() and np.isfinite(delta.array).all()),
            slave_zero=bool(np.all(cu[transfer.fine_slaves]==0) and np.all(delta.array[transfer.fine_slaves]==0)),
            AEg_unchanged=unchanged)
        save('amplification_result_vectors',dict(y=y,Eg=eg['Er'],Cg=cg['solution'],AEg=eg['AEr'],
            coarse_rhs=b.array.copy(),z=z.array.copy(),delta=delta.array.copy(),CUg=cu,bottom=bottom.last_facts,validation=validation))
        if not all(validation.values()):raise ValueError('CUg/delta vector contract failed')
        if bottom.counts['logical']!=1:raise RuntimeError('only one logical RHS permitted')
        marker('amplification_metrics_started',{})
        metric=timed('metric_build',lambda:LosslessFEMetric(levels,4,cfg.k0,quadrature))
        fields=np.column_stack([y,cu,delta.array])[mapping['independent_indices']]
        expected=old('bubble_Cg_fields')['fields']
        for name,action in (('M0',metric.mass),('scaled_curl',metric.curl)):
            images=[]
            for j in range(3):sample();images.append(timed('metric_'+name,lambda:action(fields[:,j])));counts['metric_actions']+=1
            images=np.column_stack(images);gram=fields.conj().T@images;report=gram_report(gram)
            check('amplification_'+name+'_reference',np.asarray([gram[0,0].real]),np.asarray([expected[name]['reference_energy']]))
            report.update(field_labels=['y','CUg','delta'],metric_images=images,
                remaining_field_ratio=float(np.sqrt(max(gram[0,0].real+gram[1,1].real-2*gram[0,1].real,0)/gram[0,0].real)),
                delta_over_y=float(np.sqrt(max(gram[2,2].real,0)/gram[0,0].real)),
                delta_over_Eg=float(np.sqrt(max(gram[2,2].real,0)/eg['metrics'][name]['gram'][1,1].real)))
            save('amplification_'+name,report)
        save('amplification_summary',dict(status='DIAGNOSTIC_COMPLETED_NOT_SOLVER_QUALIFICATION',
            A4_CUg_residual='not_run',G5_closed=False,bottom=bottom.bottom.audit,counts=counts))
    finally:
        save('amplification_costs',dict(counts=counts,elapsed_seconds=elapsed,bottom=dict(bottom.counts) if bottom else {},
            S_action_seconds=space.action_seconds if space else 0.,
            S_actions=space.action_count if space else 0,transfer=dict(primal=space.transfer.primal_count,adjoint=space.transfer.adjoint_count) if space else {},
            scope='one fixed direction; no operator norm or solver qualification'))
        if metric is not None:metric.destroy()
        for v in reversed(vectors):v.destroy()
        if bottom is not None:bottom.destroy()
        if matrix is not None:matrix.destroy()
        if space is not None:space.destroy()
        if dtn is not None:dtn.destroy()
