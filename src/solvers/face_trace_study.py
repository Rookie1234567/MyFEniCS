"""Thin V61 queue over the existing local deployment and saved consumers."""
import numpy as np
from src.runners.task042_shared import write_json
from . import face_trace_scope as scope
from .scattering_anchor import Journal,save_arrays,relative
from .scattering_anchor_checks import checked_arrays
from .phase_notch_hp import configured_setup
from .face_trace_mapping import FaceEnrichedMap
from .face_trace_basis import dense_face_witness


def preflight(folder,journal):
    spec=scope.case_spec('FXY');cfg,setup,geo=configured_setup(spec,journal,scope=scope)
    m=dict(spec,splits=[1,1,2],cells=160,independent=104832,trace=32832,internal=72000,rows=33660)
    _,macro,mgeo=configured_setup(m,journal,scope=scope)
    with journal.measured('geometric_face_map_qualified_once_before_PDE'):
        mapping=FaceEnrichedMap(macro['floquets'][6],setup['floquets'][6],mgeo,geo,journal,axes=[0,1],folder=folder)
    physical=mapping.face_trace_witness();small=dense_face_witness()
    parent=scope.parent('H2');v=checked_arrays(parent['independent']['ambient_original']['arrays'])
    defects=mapping.saved_face_defects(v['residual'],folder,parent=parent['independent']['ambient_original']['arrays']['sha256'])
    from .subcell_preparation_checkpoint import LazyPhaseTable
    from .subcell_macro_response import blocks_for
    from .face_trace_response import ReadonlyInternalService,FaceMacroResponse,public_local_witness
    W=setup['spaces'][6];table=LazyPhaseTable(W,cfg,journal);reader=ReadonlyInternalService(parent,journal,table);old=mapping.original_layouts[0];tag=int(mgeo['cell_tags'][0])
    child=blocks_for(W,old,tag,table,{},journal,checkpoint_reader=reader,retain_raw=False);service=reader.macro(old,tag,child)
    if service is None:raise ValueError('P actual saved H2 macro service is missing')
    response=FaceMacroResponse(mapping.layouts[0],service[0],journal);localpublic=public_local_witness(W,response,cfg,tag,setup['numerical_carrier'],folder)
    # Two different internal extensions have identical feedback once the
    # saved solution's internal equations are satisfied. This is a bounded
    # witness, not another local or global solve.
    rng=np.random.default_rng(61033);extension=[]
    for f in mapping.faces[:2]:
        d=defects['norm'];rows=mapping.internal_rows[:4356]
        a=rng.normal(size=(len(rows),2))+1j*rng.normal(size=(len(rows),2));a/=np.linalg.norm(a,axis=0)
        delta=a.conj().T@v['residual'][rows]
        operation=float(np.linalg.norm(delta)/max(np.linalg.norm(v['volume_curl'][rows])+np.linalg.norm(v['volume_mass'][rows]),1e-30))
        extension.append(dict(face=f['index'],absolute_difference=float(np.linalg.norm(delta)),internal_operation=operation,base_face_norm=d))
    mr=mapping.save(folder/'macro_mapping.npz')
    # Original zero-tangent z ports cannot acquire new support. Independent
    # saved q47/q63 generation is retained; this checks the live new dual.
    from .face_trace_response import ParentMicroBoundaryProvider
    provider=ParentMicroBoundaryProvider(cfg,setup,folder,journal,parent);boundary=provider.generate_pair();carrier=provider.bundle(63)['dtn_action'].carrier
    zero=0.
    for e in carrier.entries:
        for rows,values,dual in ((e.coupling_rows,e.coupling_values,True),(e.projection_rows,e.projection_values,False)):
            z=mapping.pull_port(rows,values,dual=dual)
            zero=max(zero,float(np.linalg.norm(z[mapping.ninternal+32832:])/max(np.linalg.norm(values),1e-30)))
    passed=mapping.check['pass_gate'] and physical['pass_gate'] and boundary['pass_gate'] and localpublic['pass_gate'] and zero<=1e-10 and max(small['mixed'],small['recovery'])<=1e-10 and small['ambient']>1e-3 and max(e['internal_operation'] for e in extension)<=1e-10
    r=dict(status='COMPLETED',role='PREFLIGHT',pass_gate=passed,mapping_check=mapping.check,face_inventory=mapping.face_receipt,trace_mapping=mr,
        physical=physical,small=small,H2_face_defects=defects,internal_extension_pair=extension,full_828_new_face_port_operation=zero,
        boundary=boundary,parent_H2_array_sha256=parent['arrays']['sha256'],new_global_factors=0,new_complete_solves=0,source=journal.source_state,timings=journal.timings,calls=journal.calls)
    r.update(local_original_witness=localpublic,old_space_local_reproduction=response.qualification,internal_service=reader.record())
    write_json(folder/'preflight_checks.json',r);return r


def execute(role,folder,state):
    journal=Journal(folder,window_scope=scope.window,planning_limit_bytes=64*2**30);journal.source_state=state
    if state.get('memory_budget')!=scope.plan_record()['memory_budget']:raise ValueError('V61 resolved/live memory budget')
    if role=='PREFLIGHT':return preflight(folder,journal)
    if role in scope.SOLVES:
        from .subcell_macro_deployment import solve_h2
        return solve_h2(folder,journal,scope,role=role)
    if role=='VERIFY_COST':
        from benchmarks.collect_face_trace import verify
        return verify(folder,journal)
    raise ValueError('V61 one-run fixed inventory')
