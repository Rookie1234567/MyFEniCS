"""Pure proof-receipt contracts; no component assembly or PDE qualification."""
import copy
import hashlib
import json
from pathlib import Path
import pytest
from src.solvers.y_orbit_live_boundary_contract import validate_live_receipt,shared_discrete_contract,EXPECTED_GATES


def _receipt():
    keys=[[j,'top' if j<266 else 'bottom',j//4,j%7,'s' if j%2==0 else 'p'] for j in range(532)]
    identity={'physical_generator_manifest_sha256':'physical','assembly_mode_manifest_sha256':'assembly',
      'assembly_context_sha256':'context','carrier_numeric_sha256':'numeric','mode_count':532,'ordered_mode_keys':keys}
    eq={k:0.0 for k in ('raw_C_equivalence','raw_D_equivalence','raw_H_equivalence','per_mode_raw_action_equivalence')}
    rows=[{'index':j,'key':key,'new_C_entries':1,'new_D_entries':1,'equivalence':eq.copy(),
      'new_stored_relative_operator_bound':0.0,'power_operation_scaled_defect':0.0,
      'production_recovery_operation_scaled_defects':{'new_stored':[0.0]*5},
      'raw_recovery_operation_scaled_defects':[0.0]*5} for j,key in enumerate(keys)]
    outputs=[{'arbitrary_state_column':j,'mode_count':532,'status':'representable_global_output',
      'global_output_component_consistency_checked':True,'official_results':False} for j in range(5)]
    kernel={'restoration_exact':True,'numerical_assembly_during_probe':False,'num_constants':3,
      'constant_roles':[{'role':role,'packed_slot':j} for j,role in enumerate(('alpha','gamma','kz'))]}
    r={'status':'PASS_COMPONENT_ONLY','full_case_pass':True,'PDE_solved':False,'official_results':False,
      'completed_gates':list(EXPECTED_GATES),'mode_count':532,'degree':2,'azimuth_deg':5.0,'seed':4053202,'tolerance':1e-10,
      'identity':identity,'carrier_digest_before':'numeric','carrier_digest_after':'numeric','per_mode':rows,
      'output_component_gates':outputs,'raw_vs_centered_action_defect':0.0,'new_stored_vs_raw_action_defect':0.0,
      'physical_FE_RHS_literal_raw_defect':0.0,
      'primary_compiled_gauss':{name:{'loaded_kernel':copy.deepcopy(kernel)} for name in ('top/0','top/1','bottom/0','bottom/1')}}
    context=_context()
    for record in r['primary_compiled_gauss'].values():
        record['rules']=copy.deepcopy(context['gauss']['compiled_forms_verified']['top/0']['rules'])
    context['gauss']['compiled_forms_verified']=copy.deepcopy(r['primary_compiled_gauss'])
    r['raw_discrete_context']=context
    identity['assembly_context_sha256']=hashlib.sha256(json.dumps(context,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode('ascii')).hexdigest()
    r.update({field:identity[field] for field in ('physical_generator_manifest_sha256','assembly_mode_manifest_sha256','assembly_context_sha256')})
    r['independent_oracle_compiled_gauss']={g+'/'+name:{'rules':copy.deepcopy(record['rules'])}
       for g in ('global_z','boundary_plane') for name,record in r['primary_compiled_gauss'].items()}
    r['incident_literal_gauss']={'rules':copy.deepcopy(r['primary_compiled_gauss']['top/0']['rules'])}
    return r,keys


def test_complete_live_receipt_binds_its_exact_numeric_carrier_identity():
    r,keys=_receipt()
    assert validate_live_receipt(r,physical_manifest='physical',ordered_keys=keys,identity=r['identity'])
    different={**r['identity'],'assembly_context_sha256':'another_loaded_kernel_context'}
    with pytest.raises(ValueError,match='this exact'):
        validate_live_receipt(r,physical_manifest='physical',ordered_keys=keys,identity=different)


@pytest.mark.parametrize('failure',('missing_mode','missing_gate','missing_recovery','bad_output','changed_digest','failed_bound'))
def test_partial_or_swapped_live_proof_never_qualifies(failure):
    r,keys=_receipt()
    if failure=='missing_mode':r['per_mode'].pop()
    elif failure=='missing_gate':r['completed_gates'].pop()
    elif failure=='missing_recovery':r['per_mode'][0]['raw_recovery_operation_scaled_defects'].pop()
    elif failure=='bad_output':r['output_component_gates'][0]['status']='controlled_stop_global_output_inconsistent'
    elif failure=='changed_digest':r['carrier_digest_after']='changed'
    else:r['per_mode'][0]['equivalence']['raw_D_equivalence']=1e-8
    with pytest.raises(ValueError):validate_live_receipt(r,physical_manifest='physical',ordered_keys=keys)


def _context():
    names=('schema','source_sha256','mesh','cell_dofmap_sha256','orientation','basix_coefficients','MPC',
      'config_sha256','ABI','element_degree','element_map_type','needs_dof_transformations')
    c={k:k for k in names}
    c['element_degree']=2
    c['gauss']={'degree':19,'rule':'current','facet_cell':'quadrilateral',
      'compiled_forms_verified':{name:{'rules':[{'degree':19,'points':{'sha256':'nodes','shape':[100,2]},'weights':{'sha256':'weights','shape':[100]}}],
      'compiled_C_sha256':'raw_old','loaded_kernel':{'module_name':'old'}} for name in ('top/0','top/1','bottom/0','bottom/1')}}
    return c


def test_shared_contract_preserves_discrete_inputs_and_keeps_raw_contexts_distinct():
    a=_context();b=copy.deepcopy(a)
    b['gauss']['compiled_forms_verified']['bottom/1']['compiled_C_sha256']='raw_new'
    b['gauss']['compiled_forms_verified']['bottom/1']['loaded_kernel']['module_name']='new'
    assert a!=b
    assert shared_discrete_contract(a)==shared_discrete_contract(b)
    b['MPC']='different actual constraint'
    assert shared_discrete_contract(a)!=shared_discrete_contract(b)
    # Sharing the fixed contract above is never a live numerical proof.
    r,keys=_receipt()
    with pytest.raises(ValueError,match='this exact'):
        validate_live_receipt(r,physical_manifest='physical',ordered_keys=keys,identity={**r['identity'],'assembly_context_sha256':'another_context'})


def test_new_discrete_context_fields_require_explicit_review():
    c=_context();c['unreviewed_new_discretization']='change'
    with pytest.raises(ValueError,match='unrecognized'):shared_discrete_contract(c)


@pytest.mark.parametrize('failure',('missing_literal','changed_context','detached_primary','changed_incident','top_identity'))
def test_detached_or_missing_independent_gauss_context_proof_is_rejected(failure):
    r,keys=_receipt()
    if failure=='missing_literal':r['independent_oracle_compiled_gauss'].pop('global_z/top/0')
    elif failure=='changed_context':r['raw_discrete_context']['MPC']='changed'
    elif failure=='detached_primary':r['primary_compiled_gauss']['bottom/1']['rules'][0]['degree']=18
    elif failure=='changed_incident':r['incident_literal_gauss']['rules'][0]['degree']=18
    else:r['assembly_mode_manifest_sha256']='detached'
    with pytest.raises(ValueError):validate_live_receipt(r,physical_manifest='physical',ordered_keys=keys)


def test_actual_immutable_live_receipt_normalizes_before_json_context_validation():
    from types import MappingProxyType
    def freeze(value):
        if isinstance(value,dict):return MappingProxyType({k:freeze(v) for k,v in value.items()})
        if isinstance(value,list):return tuple(freeze(v) for v in value)
        return value
    r,keys=_receipt();live=freeze(r)
    assert validate_live_receipt(live,physical_manifest='physical',ordered_keys=keys,identity=live['identity'])
    assert isinstance(live['raw_discrete_context'],MappingProxyType)


def test_saved_live_receipt_accepts_exact_seven_source_inventory_and_rejects_a_mutation(tmp_path):
    from src.solvers.y_orbit_live_boundary_contract import load_bound_live_receipt
    from src.solvers.y_orbit_centered_evidence import COMPONENT_SOURCE_FILES
    r,keys=_receipt()
    paths={Path(p).name:p for p in COMPONENT_SOURCE_FILES}
    paths['dtn_boundary_plane_qualification.py']='src/solvers/dtn_boundary_plane_qualification.py'
    sources={name:'source_'+str(j) for j,name in enumerate(paths)}
    r['raw_discrete_context']['source_sha256']=sources
    r['qualification_source_sha256']=sources['dtn_boundary_plane_qualification.py']
    digest=hashlib.sha256(json.dumps(r['raw_discrete_context'],sort_keys=True,separators=(',',':'),ensure_ascii=True).encode('ascii')).hexdigest()
    r['identity']['assembly_context_sha256']=digest;r['assembly_context_sha256']=digest
    path=tmp_path/'live_component_receipt.json';path.write_text(json.dumps(r))
    identity={**r['identity'],'actual_mode_keys':keys,'actual_context':r['raw_discrete_context'],
      'shared_discrete_contract':shared_discrete_contract(r['raw_discrete_context']),
      'live_component_receipt':{'filename':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}}
    worker={'files_sha256':{paths[name]:sha for name,sha in sources.items()}}
    assert load_bound_live_receipt(tmp_path,identity,worker_source=worker)['full_case_pass']
    worker['files_sha256']['src/solvers/dtn_port_3d.py']='changed'
    with pytest.raises(ValueError,match='raw numerical context source differs'):
        load_bound_live_receipt(tmp_path,identity,worker_source=worker)
