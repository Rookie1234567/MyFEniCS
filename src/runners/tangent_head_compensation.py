"""Thin V13 adapter: original packet, supervised stages, and frozen validation."""

import gc
import json
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path

import numpy as np

from src.io.tangent_head_compensation import V13_ROOT, load_tangent_head, publish, read_result
from src.io.stable_head_varpro import PLAN_PATH,V11_ROOT,read_result as read_v11
from src.io.actual_loss_block_descent import V12_ROOT,read_result as read_v12
from src.io.autonomous_neural_head import plan_and_operator
from src.runners.autonomous_neural_head import original_packet,owned,original_gate
from src.runners.actual_loss_block_descent import make_experiment,_pure_blas_threads
from src.runners.task042_shared import write_json
from src.solvers.neural_fe_action_packet import file_hash,array_hash
from src.solvers.tangent_head_window import snapshot,journal,guard_worker_parent

LIMITS=dict(forward=400,JVP=48,VJP=24,FD_points=60,PA_builds=3,
            thin_decompositions=6,thin_RHS_columns=18,small_real_LS=3,original_audits=60)


class Stage:
    def __init__(self,specification,directory):
        self.specification,self.directory=specification,directory
        self.name=specification.derived['stage'].split('-',1)[1]
        self.plan,self.design,self.material,self.fe=plan_and_operator()
        self.packet=original_packet(self.fe)
        self.source=(directory/'source_sha.txt').read_text().strip()
        self.artifact=V13_ROOT/directory.name;self.artifact.mkdir(parents=True,exist_ok=False)
        self.counts={key:0 for key in LIMITS};self.carry_actions=0
        previous={'RESPONSE':'TANGENT','COMPENSATE':'RESPONSE','VERIFY':'COMPENSATE'}.get(self.name)
        if specification.derived['refine_frozen_joint_taylor']:
            previous='COMPENSATE'
        if previous:
            prior,_=read_result(previous)
            self.counts=prior['budget_counts'].copy();self.carry_actions=prior['all_batch_equivalent_actions']
        self.began=time.perf_counter()
        self.meta=dict(source_sha=self.source,input_sha256=specification.input_sha256,
            plan_sha256=file_hash(PLAN_PATH),operator_packet=self.fe['packet'],
            physical_identity=self.fe['physical'],complete_ports=40,
            global_p4_factor_constructed=False,global_S_or_CSR_constructed=False,
            hidden_fallback=False,reference_arrays_read=False,shared_workstation=True)

    def sample(self):
        path=self.directory/'supervision/resources.jsonl'
        with path.open('rb') as stream:
            stream.seek(max(0,path.stat().st_size-65536));lines=stream.read().splitlines()
        for line in reversed(lines):
            try:
                row=json.loads(line)
            except json.JSONDecodeError:
                continue
            if time.time_ns()-row['timestamp_ns']>5_000_000_000 or row['swap_bytes']:
                raise RuntimeError('own V13 supervision stale or own swap')
            if row['rss_bytes']>=12*2**30:
                raise RuntimeError('V13 RSS warning, no new large allocation')
            return row
        raise RuntimeError('V13 resource sample unavailable')

    def guard(self,extra_actions=0,large=False):
        self.sample()
        if snapshot()['heavy_remaining_seconds'] < (300 if large else 10):
            raise RuntimeError('V13 deadline/cleanup margin reached')
        if any(self.counts[key]>limit for key,limit in LIMITS.items()):
            raise RuntimeError('V13 operation count limit reached')
        if self.carry_actions+self.packet.counts['S']+self.packet.counts['SH']+extra_actions>8000:
            raise RuntimeError('V13 8000 original equivalent actions reached')

    def count(self,key,n=1):
        self.guard()
        if self.counts[key]+n>LIMITS[key]:
            raise RuntimeError('V13 '+key+' budget reached')
        self.counts[key]+=n

    def event(self,event,**fields):
        row=journal(event,stage=self.name,source_sha=self.source,counts=self.counts.copy(),
                    rss_bytes=self.sample()['rss_bytes'],**fields)
        print(json.dumps(row,ensure_ascii=False),flush=True)
        return row

    def audit(self,z):
        self.count('original_audits')
        return self.packet.audit(z)

    def freeze(self,name,hidden,gamma,point):
        from src.solvers.neural_trace_checks import parameters
        path=self.artifact/(name+'.npz')
        params=parameters(self.model)
        np.savez(path,hidden=hidden,gamma=gamma,port=point['port_coefficients'],
                 z=point['z'],network_parameters=params)
        return dict(path=str(path),sha256=file_hash(path),z_sha256=array_hash(point['z']),
                    hidden_sha256=array_hash(hidden),gamma_sha256=array_hash(gamma),
                    port_sha256=array_hash(point['port_coefficients']),network_parameters_sha256=array_hash(params))

    def context(self):
        objective,moments,initial,record,prior,threads,moment_identity=make_experiment(self)
        v12,_=read_v12('DESCENT')
        source_row=v12['states'][0]
        if source_row['name']!='INITIAL_V11_CORRECTED':
            raise ValueError('V12 physical initial identity differs')
        frozen=source_row['state'];path=owned(frozen,V12_ROOT)
        with np.load(path,allow_pickle=False) as saved:
            for name in ('hidden','gamma','port','z','network_parameters'):
                if array_hash(saved[name])!=array_hash(initial[name]):
                    raise ValueError('V12 and V11 original physical parameters differ: '+name)
        self.initial_identity=dict(v12_state=frozen,v11_parent_state=record,
                    original_V12_head_gate='FAIL_UNCHANGED',original_V12_scalar_FD_gate='FAIL_UNCHANGED')
        return objective,moments,initial,threads,moment_identity

    def child_compensation(self,P_path,A_path,responses,tag):
        self.guard(extra_actions=3 if A_path else 1560,large=True)
        self.count('thin_decompositions');self.count('thin_RHS_columns',responses.shape[1])
        work=self.artifact/tag;work.mkdir()
        np.save(work/'responses.npy',responses)
        write_json(work/'request.json',dict(P_path=str(P_path),P_sha256=file_hash(P_path),
             A_path=str(A_path) if A_path else None,A_sha256=file_hash(A_path) if A_path else None,
             responses_sha256=file_hash(work/'responses.npy'),resident_upper_bytes=7600000000))
        child=subprocess.run(['bash','-c',
          'source scripts/activate_task042.sh pure; exec python -m src.runners.tangent_head_compensation --head-child "$1"',
          'task042-v13-pure',str(work)],check=False,
          env=dict(os.environ,TASK042_NUMERICAL_PARENT_PID=str(os.getpid())))
        record=json.loads((work/'child_result.json').read_text()) if (work/'child_result.json').is_file() else {}
        self.carry_actions+=record.get('equivalent_actions',0)
        if child.returncode or record.get('status')!='PASS':
            raise ValueError('head compensation child failed: '+record.get('error','no record'))
        self.guard()
        with np.load(work/'directions.npz',allow_pickle=False) as saved:
            answer={key:np.array(saved[key]) for key in saved.files}
        return answer,record

    def frozen_compensation(self):
        identity=self.specification.derived['refinement_identity']
        result_path=Path(identity['result_path']);directions=Path(identity['directions_path'])
        if file_hash(result_path)!=identity['result_sha256'] or file_hash(directions)!=identity['directions_sha256']:
            raise ValueError('frozen joint compensation refinement input changed')
        previous=json.loads(result_path.read_text())
        record=previous['rounds'][0]['head_compensation'].copy()
        with np.load(directions,allow_pickle=False) as saved:
            answer={key:np.array(saved[key]) for key in saved.files}
        record.update(reused_frozen_compensation=True,new_decompositions=0,
                      original_source_sha=identity['source_sha'],directions_sha256=identity['directions_sha256'])
        return answer,record

    def finish(self,result):
        result.update(self.meta,budget_counts=self.counts.copy(),action_counts=self.packet.counts.copy(),
            action_costs_seconds=self.packet.costs.copy(),
            all_batch_equivalent_actions=self.carry_actions+self.packet.counts['S']+self.packet.counts['SH'],
            worker_wall_seconds=time.perf_counter()-self.began)
        path=self.artifact/'stage_result.json';write_json(path,result);publish(self.name,path)
        write_json(self.directory/'artifact_index.json',dict(path=str(path),sha256=file_hash(path)))
        self.event('stage_frozen',status=result['status'],artifact=str(path))


def head_child(work):
    from src.solvers.stable_head_varpro import PortBlocks
    from src.solvers.tangent_head_model import compensation_solve
    from src.io.autonomous_neural_head import read_result as old_result

    guard_worker_parent('TASK042_NUMERICAL_PARENT_PID')
    request=json.loads((work/'request.json').read_text())
    for key in ('P','A'):
        if request[key+'_path'] and file_hash(Path(request[key+'_path']))!=request[key+'_sha256']:
            raise ValueError('current compensation '+key+' identity differs')
    if request['resident_upper_bytes']>8*2**30:
        raise ValueError('basis/decomposition planning exceeds 8GiB')
    _,_,_,fe=plan_and_operator();packet=original_packet(fe)
    port_record,_=old_result('A')
    columns=np.load(owned(port_record['original_port_columns'],V11_ROOT.parent/'v10'),mmap_mode='r')
    ports=PortBlocks(packet,columns)
    P=np.load(request['P_path'],mmap_mode='r',allow_pickle=False)
    if P.shape!=(packet.nt,1560):
        raise ValueError('V13 original 1560-column head must not change')
    A=np.load(request['A_path'],mmap_mode='r',allow_pickle=False) if request['A_path'] else None
    responses=np.load(work/'responses.npy',allow_pickle=False)
    began=time.perf_counter()
    record={}
    try:
        dg,pt,thin,record=compensation_solve(packet,ports,P,responses,A,
                         heartbeat=lambda event,**kw: print(json.dumps(dict(event=event,**kw)),flush=True))
        np.savez(work/'directions.npz',dot_gamma=dg,P_dot_gamma=pt,thin=thin)
        record.update(status='PASS',threads=_pure_blas_threads(),head_columns=1560,
                      Hhat_condition=ports.cond_H,resident_upper_bytes=7600000000)
    except Exception as error:
        record.update(status='FAILED',error=type(error).__name__+': '+str(error))
        raise
    finally:
        record.update(equivalent_actions=packet.counts['S']+packet.counts['SH'],
                      action_counts=packet.counts.copy(),action_seconds=packet.costs.copy(),
                      child_wall_seconds=time.perf_counter()-began,reference_arrays_read=False)
        write_json(work/'child_result.json',record)


def verify(stage):
    from src.io.neural_fe_continuation import read_index,V7_ROOT
    from src.solvers.neural_fe_blind_reference import independent_physics
    from src.runners.task042_experiment import thread_qualification

    candidates={};seen=set();sources={}
    for name in ('TANGENT','RESPONSE','COMPENSATE'):
        result,path=read_result(name)
        for row in result.get('states',[]):
            rec=row['state']
            if rec['z_sha256'] in seen:
                continue
            state_path=owned(rec,V13_ROOT)
            with np.load(state_path,allow_pickle=False) as data:
                for key in ('hidden','gamma','port','z','network_parameters'):
                    field='z_sha256' if key=='z' else key+'_sha256'
                    if array_hash(data[key])!=rec[field]:
                        raise ValueError('V13 frozen '+key+' hash mismatch')
                candidates[row['name']]=np.array(data['z'])
            seen.add(rec['z_sha256']);sources[row['name']]=dict(state=rec,result=str(path))
    if not 1<=len(candidates)<=8:
        raise ValueError('V13 one to eight unique frozen states required')
    stage.event('solver_queue_frozen_before_REF7',states=list(candidates))
    reference_record,_=read_index('blind_reference')
    path=owned(reference_record['reference_state'],V7_ROOT)
    if file_hash(path)!='a0610a5a55e7508196b17277e706595c33e4398ace82b245f70b656e6b9ed355':
        raise ValueError('saved REF7 identity differs')
    with np.load(path,allow_pickle=False) as data:
        reference=np.array(data['z'])
    stage.meta['reference_arrays_read']=True
    physics,comparisons=independent_physics(stage.design,stage.packet,reference,candidates,stage.artifact)
    stage.count('original_audits',len(candidates)+1)
    rows={}
    for name in candidates:
        item=physics['rows'][name];comparison=comparisons[name];audit=item['audit']
        eq=original_gate(audit)
        fields={key:item[key] for key in ('full_FE_L2_relative','full_FE_scaled_curl_relative',
                 'scattered_FE_L2_relative','scattered_scaled_curl_relative','selected_E_relative','selected_H_relative')}
        same=eq['status']=='ORIGINAL_EQUATION_PASS' and physics['reference_native_pass']
        same &= all(np.isfinite(v) and v<=1e-4 for v in fields.values())
        same &= audit['independent_DOLFINx_total_native_relative']<=1e-6
        same &= comparison['ordered_complex_ports_relative']<=1e-4
        same &= all(v<=1e-5 for v in comparison['power_absolute_differences'].values())
        same &= comparison['max_channel_power_difference']<=1e-6 and comparison['energy_closure_absolute']<=1e-5
        rows[name]=dict(status='SAME_DISCRETE_QUALIFIED' if same else 'NOT_QUALIFIED',
            original_equation_gate=eq,audit=audit,fields=fields,comparison=comparison,
            ordered_complex_total_ports=item['ordered_complex_port_vector'],
            ordered_complex_scattered_ports=item['ordered_complex_scattered_port_vector'],
            selected_E=item['selected_E'],selected_H_code=item['selected_H_code'],
            power=item['port'],volume_absorption=item['volume'],official_candidate_results=bool(same))
    return dict(status='FROZEN_VALIDATION_COMPLETE',rows=rows,states_read=len(candidates),
                state_sources=sources,reference_identity=reference_record['reference_state'],
                reference_only_after_solver_frozen=True,reference_feedback_to_solver=False,
                threads=thread_qualification(),no_new_solve=True,no_p4_enrichment=True)


def main():
    if len(sys.argv)==3 and sys.argv[1]=='--head-child':
        head_child(Path(sys.argv[2]).resolve());return
    guard_worker_parent()
    specification=load_tangent_head(sys.argv[1]);directory=Path(sys.argv[2]).resolve()
    stage=Stage(specification,directory)
    try:
        if stage.name=='VERIFY':
            result=verify(stage)
        else:
            from src.solvers.tangent_head_study import TangentStudy
            study=TangentStudy(stage)
            result={'TANGENT':study.check,'RESPONSE':study.response,'COMPENSATE':study.compensate}[stage.name]()
        stage.finish(result)
    except Exception as error:
        write_json(stage.artifact/'failure.json',dict(error=type(error).__name__+': '+str(error),
                   counts=stage.counts,source_sha=stage.source,reference_arrays_read=stage.meta['reference_arrays_read']))
        traceback.print_exc();raise
    finally:
        gc.collect()


if __name__=='__main__':
    main()
