"""Reviewed fixed local libraries, independent equation solves and freeze barrier.

The only growing spaces are the two matched local libraries and two matched
G0 complements. No field reference is opened before ``verify``.
"""

import gc
import json
import os
import subprocess
import time
from pathlib import Path

import numpy as np

from src.io.local_trace_representation import ARTIFACT_ROOT, read_result
from src.io.orthonormal_trace_reprofile import read_frozen_state, V14_ROOT
from src.runners.orthonormal_trace_reprofile import atomic_arrays
from src.runners.task042_shared import write_json
from src.solvers.local_trace_decoder import BlockTraceDecoder, UnionTraceDecoder, complementary_space
from src.solvers.local_trace_features import build_local_library, polynomial_features, numpy_hidden_features
from src.solvers.local_trace_head import TraceLinearHead
from src.solvers.neural_fe_action_packet import array_hash, file_hash
from src.solvers.orthonormal_trace_reprofile import manufactured_witness
from src.solvers.stable_head_varpro import PortBlocks


def ports_for(stage):
    from src.io.autonomous_neural_head import V10_ROOT, read_result as old_result
    from src.runners.autonomous_neural_head import owned
    old,_ = old_result('A')
    columns = np.load(owned(old['original_port_columns'],V10_ROOT),mmap_mode='r')
    ports = PortBlocks(stage.packet,columns)
    if ports.cond_H > 1e10:
        raise ValueError('original condensed Hhat unsafe')
    return ports


def frozen_arrays(record,root=ARTIFACT_ROOT):
    return read_frozen_state(record,root)


def decoder_from(record):
    arrays = frozen_arrays(record)
    return BlockTraceDecoder([arrays['rows'+str(j)] for j in range(8)],
                             [arrays['Q'+str(j)] for j in range(8)],18144)


def saved_point(stage,name,point,decoder_identity):
    # Numerical payload first, then strict JSON metadata; never a raw gamma.
    state = atomic_arrays(stage.artifact/(name+'.npz'),c=point['c'],trace=point['trace'],
                          port=point['port'],z=point['z'],residual=point['residual'],thin_residual=point['thin_residual'])
    core = dict(name=name,source_sha=stage.source,state=state,numeric=point['numeric'],
                decoder_identity=decoder_identity,reference_arrays_read=False)
    write_json(stage.artifact/(name+'_core.json'),core)
    core['audit'] = stage.audit(point['z'])
    from src.runners.autonomous_neural_head import original_gate
    core['original_equation_gate'] = original_gate(core['audit'])
    return core


def setup(stage):
    from src.runners.neural_fe_continuation import read_moments
    from src.solvers.neural_trace_dolfinx import pilot_space
    from src.solvers.neural_fe_pilot import physical_config
    from src.constraints.floquet_3d import build_double_floquet_mpc
    from src.solvers.common_3d_fields import _mode_basis
    from src.solvers.local_trace_geometry import canonical_entity_map, independent_local_interpolation
    from src.solvers.local_trace_decoder import matched_local_spaces
    from src.runners.task042_experiment import thread_qualification

    began = time.perf_counter(); stage.guard(large=True)
    moments,moment_identity = read_moments()
    cfg = physical_config(stage.design)[0]
    _,data,space,_,_,_,_ = pilot_space(stage.design)
    mpc = build_double_floquet_mpc(space,data,cfg).mpc
    mapping, entity_checks = canonical_entity_map(space,moments,mpc,stage.design)
    map_record = atomic_arrays(stage.artifact/'canonical_entity_map.npz',**mapping)
    wavevector = np.asarray(_mode_basis(cfg,cfg.n_air,vertical_sign=-1)[0],np.complex128)
    if wavevector.shape != (3,) or not np.isfinite(wavevector).all():
        raise ValueError('original incoming carrier identity differs')
    request = dict(bounds=stage.design['geometry']['bounds_nm'],wavelength_nm=.7,seed=420906,
                   directory=str(stage.directory),source_sha=stage.source)
    write_json(stage.artifact/'hidden_request.json',request)
    child = subprocess.run(['bash','-c',
        'source scripts/activate_task042.sh ml; exec python -m src.runners.local_trace_representation --hidden-child "$1"',
        'task042-v15-hidden',str(stage.artifact)],check=False,
        env=dict(os.environ,TASK042_NUMERICAL_PARENT_PID=str(os.getpid())))
    if child.returncode:
        raise ValueError('isolated fixed random hidden initialization failed')
    initialization = json.loads((stage.artifact/'hidden_initialization.json').read_text())
    weights = frozen_arrays(initialization['weights'])
    libraries, library_checks = {},{}
    for family,features in [('POLY',polynomial_features),('NN',lambda x:numpy_hidden_features(x,weights))]:
        stage.count('local_raw_bases')
        libraries[family],library_checks[family] = build_local_library(moments,mapping,wavevector,features,heartbeat=stage.event)
    interpolation = independent_local_interpolation(moments,mapping,space,mpc,wavevector,weights,libraries)
    rows = [np.flatnonzero(mapping['patch_id']==j) for j in range(8)]
    decoders,capacity = matched_local_spaces(libraries,rows,18144,count=stage.count)
    identities,checks = {},{}
    for family,decoder in decoders.items():
        identities[family] = atomic_arrays(stage.artifact/(family+'_block_decoder.npz'),
            **{'rows'+str(j):r for j,r in enumerate(decoder.rows)},
            **{'Q'+str(j):q for j,q in enumerate(decoder.blocks)})
        checks[family] = decoder.identity_checks()
    # Rank arrays are small but kept with ignored setup, not hand copied into Git.
    qualified = all(row['qualified'] for row in interpolation) and all(
        max(c['forward_relative'],c['adjoint_operation_relative'],c['orthogonality'])<=1e-10 for c in checks.values())
    stage.event('L0_fixed_libraries_frozen',qualified=qualified,actual_columns=capacity['actual_columns'])
    return dict(status='LOCAL_SETUP_QUALIFIED' if qualified else 'LOCAL_SETUP_FAILED',
        local_setup_qualified=qualified,entity_map=map_record,entity_checks=entity_checks,
        incoming_wavevector=wavevector,moments=moment_identity,initialization=initialization,
        libraries=library_checks,capacity=capacity,interpolation_checks=interpolation,
        decoder_checks=checks,decoders=identities,setup_wall_seconds=time.perf_counter()-began,
        hidden_training=False,physical_channels_removed=False,threads=thread_qualification(),
        global_S_assembled=False,reference_used=False)


def local_solve(stage,family):
    setup_record,_ = read_result('SETUP')
    if not setup_record['local_setup_qualified']:
        return dict(status='NOT_RUN_LOCAL_SETUP_GATE',family=family,queue_frozen=True)
    stage.guard(large=True)
    ports = ports_for(stage)
    decoder_identity = setup_record['decoders'][family]
    decoder = decoder_from(decoder_identity)
    basis = TraceLinearHead(stage.packet,decoder,ports,count=stage.count,guard=stage.guard,event=stage.event)
    # One independent manufactured RHS, with all forty nonzero ports.
    rng = np.random.default_rng(421501)
    c = rng.standard_normal(decoder.shape[1])+1j*rng.standard_normal(decoder.shape[1]);c/=np.linalg.norm(c)
    alpha = rng.standard_normal(40)+1j*rng.standard_normal(40);alpha/=np.linalg.norm(alpha)
    stage.guard(extra_actions=16)
    known = np.r_[decoder@c,alpha]
    recovered,rhs,witness = manufactured_witness(basis,known,'LOCAL-'+family+'-M1')
    witness['state'] = atomic_arrays(stage.artifact/'manufactured.npz',known=known,rhs=rhs,z=recovered['z'],c=recovered['c'])
    write_json(stage.artifact/'manufactured_check.json',witness)
    if not witness['qualified']:
        return dict(status='LOCAL_MANUFACTURED_UNQUALIFIED',family=family,
            decoder_qualified=False,witness=witness,basis=basis.decomposition(),queue_frozen=True)
    point = basis.solve(stage.packet.a['b'])
    physical = saved_point(stage,'LOCAL-'+family,point,decoder_identity)
    qualified = bool(point['numeric']['decoder_gate'])
    result = dict(status='PHYSICAL_SOLVE_COMPLETE',family=family,decoder_qualified=qualified,
                  physical=physical,witness=witness,basis=basis.decomposition(),queue_frozen=True,
                  hidden_training=False,zero_start=True,other_candidate_warm_start=False)
    if family == 'NN':
        first,_ = read_result('LOCAL_POLY')
        admitted = bool(first.get('decoder_qualified') and qualified and
            first['physical']['original_equation_gate']['status']!='ORIGINAL_EQUATION_PASS' and
            physical['original_equation_gate']['status']!='ORIGINAL_EQUATION_PASS')
        result['union_dispatch'] = dict(admitted=admitted,reason='BOTH_NUMERICALLY_QUALIFIED_PHYSICAL_NEGATIVE' if admitted else 'LOCAL_OR_EQUATION_GATE',reference_used=False)
    return result


def global_basis(stage):
    record = stage.own_plan['G0']; path = Path(record['path']).resolve()
    if not path.is_relative_to(V14_ROOT) or file_hash(path)!=record['sha256']:
        raise ValueError('frozen V14 ORIGIN global Q missing or identity differs')
    G = np.load(path,mmap_mode='r',allow_pickle=False)
    if G.shape!=(18144,1560) or G.dtype!=np.complex128:
        raise ValueError('frozen G0 canonical inventory differs')
    return G,record


def build_unions(stage):
    setup_record,_=read_result('SETUP')
    G,Gidentity=global_basis(stage); inventory={}
    for family in ('POLY','NN'):
        stage.guard(large=True)
        local=decoder_from(setup_record['decoders'][family])
        began=time.perf_counter()
        U,record=complementary_space(G,local,count=stage.count,heartbeat=stage.event)
        stage.count('union_bases')
        path=stage.artifact/(family+'_complement.npy')
        np.save(path,U)
        inventory[family]=dict(path=str(path),sha256=file_hash(path),shape=list(U.shape),
            decomposition=record,seconds=time.perf_counter()-began)
        del U,local;gc.collect()
    q=min(inventory['POLY']['decomposition']['raw_q'],inventory['NN']['decomposition']['raw_q'])
    for family in inventory:
        item=inventory[family]
        item['common_q']=q;item['actual_union_columns']=1560+q
    write_json(stage.artifact/'paired_union_inventory.json',dict(G0=Gidentity,q=q,spaces=inventory))
    return dict(G0=Gidentity,q=q,spaces=inventory)


def union_solve(stage,family):
    locals_record,_=read_result('LOCAL_NN')
    if not locals_record.get('union_dispatch',{}).get('admitted'):
        return dict(status='NOT_RUN_LOCAL_GATE',family=family,queue_frozen=True)
    if family=='POLY':
        # Preserve time for the second paired solve, independent FE and delivery.
        if stage.window.snapshot()['heavy_remaining_seconds']<1800:
            return dict(status='NOT_RUN_UNION_TIME_RESERVE',family=family,queue_frozen=True)
        try:
            inventory=build_unions(stage)
        except (OSError,ValueError) as error:
            return dict(status='NOT_RUN_G0_OR_COMPLEMENT_GATE',family=family,reason=str(error),queue_frozen=True)
    else:
        prior,_=read_result('UNION_POLY')
        if 'union_inventory' not in prior:
            return dict(status='NOT_RUN_PAIRED_UNION_DEPENDENCY',family=family,queue_frozen=True)
        inventory=prior['union_inventory']
    if inventory['q']==0:
        return dict(status='NO_NEW_INDEPENDENT_DIRECTIONS',family=family,union_inventory=inventory,queue_frozen=True)
    stage.guard(large=True)
    G,Gidentity=global_basis(stage);item=inventory['spaces'][family]
    path=Path(item['path']).resolve()
    if not path.is_relative_to(ARTIFACT_ROOT) or file_hash(path)!=item['sha256']:
        raise ValueError('union complement identity differs')
    U=np.load(path,mmap_mode='r',allow_pickle=False)[:,:inventory['q']]
    decoder=UnionTraceDecoder(G,U)
    origin=frozen_arrays(stage.own_plan['historical_states'][0]['state'],V14_ROOT)
    coefficient=np.r_[origin['c'],np.zeros(U.shape[1],complex)]
    reconstruction=float(np.linalg.norm(decoder@coefficient-origin['trace'])/np.linalg.norm(origin['trace']))
    if reconstruction>1e-10 or decoder.orthogonality()>1e-10:
        return dict(status='UNION_DECODER_UNQUALIFIED',family=family,union_inventory=inventory,G0_reconstruction=reconstruction,queue_frozen=True)
    basis=TraceLinearHead(stage.packet,decoder,ports_for(stage),count=stage.count,guard=stage.guard,event=stage.event)
    point=basis.solve(stage.packet.a['b'])
    identity=dict(G0=Gidentity,complement=item,matched_q=inventory['q'],main_forward='G0_times_cG_plus_U_times_cU')
    physical=saved_point(stage,'UNION-'+family,point,identity)
    origin_phi=stage.own_plan['historical_states'][0]['numeric']['Phi']
    margin=max(1e-8,100*point['numeric']['delta_i'])
    phi_check=bool(point['numeric']['Phi']<=origin_phi+margin)
    return dict(status='PHYSICAL_SOLVE_COMPLETE',family=family,physical=physical,
        decoder_qualified=bool(point['numeric']['decoder_gate'] and phi_check),basis=basis.decomposition(),
        union_inventory=inventory,checks=dict(G0_reconstruction=reconstruction,Phi_not_worse_than_G0=phi_check,
            origin_Phi=origin_phi,margin=margin),queue_frozen=True,hidden_training=False,
        increased_capacity_is_not_neural_gain=True,other_candidate_warm_start=False)


def physical_qualification(item,comparison,reference_pass):
    from src.runners.autonomous_neural_head import original_gate
    audit=item['audit'];eq=original_gate(audit)
    fields={k:item[k] for k in ('full_FE_L2_relative','full_FE_scaled_curl_relative',
        'scattered_FE_L2_relative','scattered_scaled_curl_relative','selected_E_relative','selected_H_relative')}
    passed=bool(eq['status']=='ORIGINAL_EQUATION_PASS' and reference_pass
        and len(item['ordered_complex_port_vector'])==40 and len(item['ordered_complex_scattered_port_vector'])==40
        and all(np.isfinite(v) and v<=1e-4 for v in fields.values())
        and audit['independent_DOLFINx_total_native_relative']<=1e-6
        and comparison['ordered_complex_ports_relative']<=1e-4
        and all(v<=1e-5 for v in comparison['power_absolute_differences'].values())
        and comparison['max_channel_power_difference']<=1e-6 and comparison['energy_closure_absolute']<=1e-5)
    return dict(status='SAME_DISCRETE_QUALIFIED' if passed else 'NOT_QUALIFIED',
        original_equation_gate=eq,audit=audit,fields=fields,comparison=comparison,
        ordered_complex_total_ports=item['ordered_complex_port_vector'],
        ordered_complex_scattered_ports=item['ordered_complex_scattered_port_vector'],
        selected_E=item['selected_E'],selected_H_code=item['selected_H_code'],
        power=item['port'],volume_absorption=item['volume'],official_candidate_results=passed)


def verify(stage):
    from src.io.neural_fe_continuation import read_index,V7_ROOT
    from src.runners.autonomous_neural_head import owned
    from src.solvers.neural_fe_blind_reference import independent_physics
    from src.runners.task042_experiment import thread_qualification
    candidates,sources,seen,solver_rows={},{},set(),[]
    for historical in stage.own_plan['historical_states']:
        solver_rows.append((historical,V14_ROOT))
    for name in ('LOCAL_POLY','LOCAL_NN','UNION_POLY','UNION_NN'):
        try:
            record,_=read_result(name)
        except FileNotFoundError:
            continue
        if not record.get('queue_frozen'):
            raise ValueError('reference barrier: solver state not frozen')
        if 'physical' in record:
            solver_rows.append((record['physical'],ARTIFACT_ROOT))
    for item,root in solver_rows:
        try:
            arrays=frozen_arrays(item['state'],root)
        except (OSError,ValueError,KeyError) as error:
            stage.event('missing_frozen_state',name=item['name'],reason=str(error));continue
        identity=array_hash(arrays['z'])
        if identity in seen:continue
        seen.add(identity);candidates[item['name']]=arrays['z'];sources[item['name']]=item
    stage.event('all_solver_states_and_decisions_frozen_before_REF7',states=list(candidates))
    ref_record,_=read_index('blind_reference');path=owned(ref_record['reference_state'],V7_ROOT)
    if file_hash(path)!=stage.own_plan['reference_sha256']:
        return dict(status='REFERENCE_IDENTITY_UNRESOLVED',states_read=len(candidates),no_new_reference=True)
    with np.load(path,allow_pickle=False) as saved:reference=np.array(saved['z'])
    stage.meta['reference_arrays_read']=True
    setup_record,_=read_result('SETUP');ports=ports_for(stage);projections={}
    for family in ('POLY','NN'):
        local,_=read_result('LOCAL_'+family)
        if local.get('physical',{}).get('original_equation_gate',{}).get('status')=='ORIGINAL_EQUATION_PASS':
            continue
        decoder=decoder_from(setup_record['decoders'][family])
        c=decoder.adjoint(reference[:stage.packet.nt]);trace=decoder@c
        z,_=ports.closed(trace,stage.packet.a['b'])
        name='PROJECTION-'+family
        state=atomic_arrays(stage.artifact/(name+'.npz'),c=c,trace=trace,port=z[stage.packet.nt:],z=z)
        candidates[name]=z
        projections[name]=dict(state=state,classification='REFERENCE_ASSISTED_REPRESENTATION_DIAGNOSTIC',
            trace_euclidean_relative=float(np.linalg.norm(trace-reference[:stage.packet.nt])/np.linalg.norm(reference[:stage.packet.nt])),
            physical_L2_optimal_claimed=False,initialization_or_training_used=False)
        sources[name]=dict(state=state,source_sha=stage.source,reference_assisted=True)
    if not 1<=len(candidates)<=10:raise ValueError('one to ten frozen field states required')
    stage.count('field_states',len(candidates));stage.count('original_audits',len(candidates)+1)
    stage.guard(extra_actions=3*(len(candidates)+1),large=True)
    physics,comparisons=independent_physics(stage.design,stage.packet,reference,candidates,stage.artifact)
    reference_audit=dict(reference_identity=ref_record['reference_state'],audit=physics['rows']['REFERENCE']['audit'],
        native_qualified=physics['reference_native_pass'],source_sha=stage.source)
    write_json(stage.artifact/'reference_audit_v15.json',reference_audit)
    rows={name:physical_qualification(physics['rows'][name],comparisons[name],physics['reference_native_pass']) for name in candidates}
    return dict(status='FROZEN_VALIDATION_COMPLETE',rows=rows,states_read=len(candidates),
        state_sources=sources,projections=projections,reference_identity=ref_record['reference_state'],
        reference_audit=reference_audit,reference_only_after_solver_frozen=True,reference_feedback_to_solver=False,
        threads=thread_qualification(),no_new_solve=True,no_p4_enrichment=True)
