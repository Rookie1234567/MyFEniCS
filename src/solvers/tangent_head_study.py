"""Bounded tangent-qualified fixed/head-compensated local residual steps.

All trial values come from the actual network and original action.  The study
never opens a reference.  Tall/thin workspace is delegated to one pure child.
"""

from pathlib import Path

import numpy as np

from src.io.stable_head_varpro import read_result as read_v11
from src.io.tangent_head_compensation import read_result,V13_ROOT
from src.solvers.actual_loss_block_descent import actual_loss,qualified_audit
from src.solvers.neural_fe_action_packet import array_hash,file_hash
from src.solvers.neural_trace_tangent import moment_tangent,parameter_direction,dot_pair
from src.solvers.tangent_head_model import (bar_action,loss_resolution,fixed_head_scale,
    real_local_step,common_radius,predicted_gain,accept_step)
from src.solvers.tangent_head_window import snapshot


class TangentStudy:
    def __init__(self,stage):
        self.stage=stage
        self.obj,self.moments,self.initial,self.threads,self.moment_identity=stage.context()
        self.hidden=self.initial['hidden'].copy();self.gamma=self.initial['gamma'].copy()
        self.bnorm=self.obj.bnorm

    def evaluate(self,hidden,gamma,fd=False):
        self.stage.count('forward')
        if fd:
            self.stage.count('FD_points')
        return self.obj.evaluate(hidden,gamma)

    def resolved(self,hidden,gamma):
        from src.solvers.neural_trace_torch import packet_forward
        a=self.evaluate(hidden,gamma);b=self.evaluate(hidden,gamma)
        self.stage.count('forward');self.obj.assign(hidden,gamma)
        trace=packet_forward(self.obj.model,self.moments)
        c=actual_loss(self.stage.packet,self.obj.ports,trace,self.obj.rhs)
        full=self.stage.packet.apply(a['z'])
        direct=dict(a,bar_residual=self.obj.rhs[:self.stage.packet.nt]-full[:self.stage.packet.nt])
        direct['loss']=float(np.vdot(direct['bar_residual'],direct['bar_residual']).real/(2*self.bnorm**2))
        report=loss_resolution([a,b,c,direct],self.bnorm)
        report.update(batch8=[a['loss'],b['loss']],batch1=c['loss'],direct_full_S=direct['loss'],
                      batch1_trace_relative=float(np.linalg.norm(c['trace']-a['trace'])/max(np.linalg.norm(a['trace']),1e-300)),
                      actual_parameter_hash=a['hidden_hash'],gamma_hash=a['gamma_hash'])
        audit=self.stage.audit(a['z'])
        if not qualified_audit(audit) or report['batch1_trace_relative']>1e-10:
            raise ValueError('actual objective/port/original identity unavailable')
        self.obj.assign(hidden,gamma)
        return a,report,audit

    def tangent(self,hidden,gamma,direction,head_direction=None):
        self.obj.assign(hidden,gamma)
        self.stage.count('JVP');self.stage.count('forward')
        return moment_tangent(self.obj.model,self.obj.cache,direction,head_direction)

    def duals(self,hidden,gamma,point):
        self.obj.assign(hidden,gamma)
        pairs=[]
        for seed in (421301,421302):
            rng=np.random.default_rng(seed)
            q=rng.standard_normal(len(point['trace']))+1j*rng.standard_normal(len(point['trace']))
            self.stage.count('VJP');back=self.obj.cache.vjp(self.obj.model,q)
            pairs.append((str(seed),q,back))
        q=self.obj.ports.adjoint(point['bar_residual'])
        self.stage.count('VJP');back=self.obj.cache.vjp(self.obj.model,q)
        pairs.append(('actual_loss_barS_adjoint',q,back))
        gradient=-back[:8576]/self.bnorm**2
        directions=[]
        for seed in (421201,421202):
            d=np.random.default_rng(seed).standard_normal(8576);d/=np.linalg.norm(d)
            directions.append((str(seed),d))
        if np.linalg.norm(gradient)>1e-14:
            directions.append(('analytic_gradient',gradient/np.linalg.norm(gradient)))
        else:
            d=np.random.default_rng(421203).standard_normal(8576);d/=np.linalg.norm(d)
            directions.append(('421203_nearzero_fallback',d))
        return pairs,gradient,directions

    def vector_fd(self,hidden,gamma,point,d,dt,head=None,steps=None,tag='FD'):
        head=np.zeros(1560,np.complex128) if head is None else head
        steps=[1e-4,1e-5,1e-6,1e-7] if steps is None else list(steps)
        rows=[];raw={}
        for index,h in enumerate(steps):
            self.stage.guard()
            plus=self.evaluate(hidden+h*d,gamma+h*head,fd=True)
            minus=self.evaluate(hidden-h*d,gamma-h*head,fd=True)
            difference=plus['trace']-minus['trace'];observed=difference/(2*h)
            relative=float(np.linalg.norm(observed-dt)/max(np.linalg.norm(dt),1e-300))
            theta_difference=float(np.linalg.norm((hidden+h*d)-(hidden-h*d)))
            trace_difference=float(np.linalg.norm(difference))
            trace_scale=float(np.linalg.norm(plus['trace'])+np.linalg.norm(minus['trace']))
            resolved=bool(theta_difference>100*np.finfo(np.float64).eps*max(1.,np.linalg.norm(hidden))
                      and trace_difference>100*np.finfo(np.float64).eps*max(trace_scale,1e-300))
            row=dict(h=float(h),vector_relative=relative,tangent_norm=float(np.linalg.norm(dt)),
                     plus_trace_norm=float(np.linalg.norm(plus['trace'])),minus_trace_norm=float(np.linalg.norm(minus['trace'])),
                     trace_difference_norm=trace_difference,actual_hidden_difference=theta_difference,
                     plus_loss=plus['loss'],minus_loss=minus['loss'],
                     plus_Taylor_remainder=float(np.linalg.norm(plus['trace']-point['trace']-h*dt)),
                     minus_Taylor_remainder=float(np.linalg.norm(minus['trace']-point['trace']+h*dt)),
                     parameter_and_trace_resolved=resolved,head_fixed=bool(not np.any(head)),
                     plus_gamma_hash=plus['gamma_hash'],minus_gamma_hash=minus['gamma_hash'])
            rows.append(row);raw[f'plus_{index}']=plus['trace'];raw[f'minus_{index}']=minus['trace']
        good=[]
        for index in range(len(rows)-1):
            first,second=rows[index:index+2]
            if (first['vector_relative']<=1e-5 and second['vector_relative']<=1e-5
                and first['parameter_and_trace_resolved'] and second['parameter_and_trace_resolved']):
                good.append([index,index+1])
        path=self.stage.artifact/(tag+'.npz');np.savez(path,tangent=dt,direction=d,head_direction=head,**raw)
        self.obj.assign(hidden,gamma)
        return dict(rows=rows,adjacent_stable_pairs=good,qualified=bool(good),
                    array_path=str(path),array_sha256=file_hash(path),
                    old_V12_scalar_FD_gate='FAIL_UNCHANGED',independent_vector_check=True)

    def state_row(self,name,hidden,gamma,point,audit,**fields):
        self.obj.assign(hidden,gamma)
        return dict(name=name,state=self.stage.freeze(name,hidden,gamma,point),
                    loss=point['loss'],audit=audit,**fields)

    def base_result(self):
        return dict(status='STARTED',states=[],threads=self.threads,moments=self.moment_identity,
                    initial_identity=self.stage.initial_identity,
                    original_head_gate_1e8='FAIL_UNCHANGED',original_scalar_FD_gate='FAIL_UNCHANGED',
                    exact_VarPro_qualified=False,independent_JVP_kind='EXPLICIT_LAYERWISE_TANH',
                    scalar_loss_from_actual_network=True,reference_arrays_read=False)

    def check(self):
        from time import perf_counter
        began=perf_counter()
        point,resolution,audit=self.resolved(self.hidden,self.gamma)
        pairs,gradient,directions=self.duals(self.hidden,self.gamma,point)
        result=self.base_result()
        result.update(initial_loss=point['loss'],initial_resolution=resolution,initial_audit=audit,
                      gradient_hash=array_hash(gradient),gradient_norm=float(np.linalg.norm(gradient)),directions=[])
        result['states'].append(self.state_row('INITIAL_V12_PHYSICAL',self.hidden,self.gamma,point,audit))
        payload={'hidden':self.hidden,'gamma':self.gamma,'gradient':gradient}
        for index,(name,d) in enumerate(directions):
            self.stage.guard()
            if perf_counter()-began>=1800:
                raise RuntimeError('A1 1800s diagnostic limit reached')
            value,dt=self.tangent(self.hidden,self.gamma,d)
            value_error=float(np.linalg.norm(value-point['trace'])/max(np.linalg.norm(point['trace']),1e-300))
            response,dz=bar_action(self.stage.packet,self.obj.ports,dt)
            complete=self.stage.packet.apply(dz)
            predicted=np.r_[response,np.zeros(40,np.complex128)]
            op_scale=max(np.linalg.norm(complete),np.linalg.norm(predicted),1e-300)
            port_identity=float(np.linalg.norm(complete-predicted)/op_scale)
            backchecks={key:dot_pair(q,dt,back,parameter_direction(d)) for key,q,back in pairs}
            fd=self.vector_fd(self.hidden,self.gamma,point,d,dt,tag='A1_'+name)
            if not fd['qualified']:
                self.stage.event('A1_bounded_extra_vector_scales',direction=name,
                                 new_steps=[1e-8,1e-9],reason='no adjacent stable region in four registered scales')
                extra=self.vector_fd(self.hidden,self.gamma,point,d,dt,steps=[1e-8,1e-9],tag='A1_'+name+'_extra')
                fd['extra']=extra;fd['qualified']=bool(extra['qualified'])
            from src.solvers.stable_head_varpro import homogeneous_recovery_pair
            recovery=homogeneous_recovery_pair(self.stage.packet,point['z']+dz,point['z'])
            qualified=(value_error<=1e-10 and port_identity<=1e-10 and recovery<=1e-10
                       and all(check['operation_relative']<=1e-9 for check in backchecks.values())
                       and fd['qualified'])
            row=dict(name=name,qualified=bool(qualified),status='TANGENT_VECTOR_VERIFIED' if qualified else 'TANGENT_UNTRUSTWORTHY',
                     value_rebuild_relative=value_error,port_tangent_identity=port_identity,
                     homogeneous_recovery_pair=recovery,port_tangent_norm=float(np.linalg.norm(dz[-40:])),
                     JVP_VJP=backchecks,vector_FD=fd,gradient_directional=float(np.dot(gradient,d)),
                     direction_hash=array_hash(d),trace_tangent_hash=array_hash(dt),response_hash=array_hash(response))
            result['directions'].append(row)
            payload['direction_'+str(index)]=d;payload['tangent_'+str(index)]=dt;payload['response_'+str(index)]=response
            self.stage.event('A1_direction_done',direction=name,qualified=bool(qualified),
                             vector_errors=[r['vector_relative'] for r in fd['rows']],
                             real_dual_relative=backchecks['actual_loss_barS_adjoint']['operation_relative'])
        path=self.stage.artifact/'qualified_directions.npz';np.savez(path,**payload)
        result.update(direction_arrays=dict(path=str(path),sha256=file_hash(path)),
                      qualified_direction_count=sum(r['qualified'] for r in result['directions']),
                      status='TANGENT_CHECK_COMPLETE',A1_wall_seconds=perf_counter()-began)
        return result

    def origin_directions(self):
        check,_=read_result('TANGENT')
        path=Path(check['direction_arrays']['path']).resolve()
        if not path.is_relative_to(V13_ROOT) or file_hash(path)!=check['direction_arrays']['sha256']:
            raise ValueError('qualified tangent array inventory differs')
        with np.load(path,allow_pickle=False) as saved:
            payload={k:np.array(saved[k]) for k in saved.files}
        if array_hash(payload['hidden'])!=array_hash(self.hidden) or array_hash(payload['gamma'])!=array_hash(self.gamma):
            raise ValueError('B/C must use the same V12 physical origin')
        return check,payload

    def try_trial(self,tag,hidden,gamma,old,old_resolution,old_audit,new_hidden,new_gamma,linear_response,alpha):
        trial=self.evaluate(new_hidden,new_gamma)
        prediction=predicted_gain(old['bar_residual'],alpha*linear_response,self.bnorm)
        audit=self.stage.audit(trial['z'])
        # A tentative loss descent gets a repeat, batch1 and complete S check.
        trial_delta=old_resolution
        resolved_report=None
        if old['loss']-trial['loss']>max(1e-12,20*old_resolution):
            trial,resolved_report,audit=self.resolved(new_hidden,new_gamma)
            trial_delta=resolved_report['delta_J']
        acceptance=accept_step(old,trial,prediction,old_resolution,trial_delta,old_audit,audit)
        row=dict(tag=tag,alpha=float(alpha),old_loss=old['loss'],trial_loss=trial['loss'],
                 old_native=old_audit['native_relative'],trial_audit=audit,
                 hidden_change=float(np.linalg.norm(new_hidden-hidden)),head_change=float(np.linalg.norm(new_gamma-gamma)),
                 actual_network_candidate=True,linear_only_candidate=False,
                 head_fixed=bool(array_hash(gamma)==array_hash(new_gamma)),
                 hidden_step_real=bool(not np.iscomplexobj(new_hidden)),resolution=resolved_report,
                 Taylor_residual_norm=float(np.linalg.norm(trial['bar_residual']-old['bar_residual']+alpha*linear_response)),
                 remaining_budget_seconds=snapshot()['heavy_remaining_seconds'],**acceptance)
        row['state']=self.stage.freeze(tag,new_hidden,new_gamma,trial)
        self.stage.event('actual_trial',**{k:v for k,v in row.items() if k not in ('trial_audit','resolution','state')})
        if not row['accepted']:
            self.obj.assign(hidden,gamma)
            from src.solvers.stable_head_varpro_torch import hidden_vector
            from src.solvers.neural_linear_head_torch import head_coefficients
            if (array_hash(hidden_vector(self.obj.model))!=array_hash(hidden)
                or array_hash(head_coefficients(self.obj.model))!=array_hash(gamma)):
                raise ValueError('rejected hidden/head rollback failed')
            row['rollback_hidden_hash']=array_hash(hidden_vector(self.obj.model))
            row['rollback_gamma_hash']=array_hash(head_coefficients(self.obj.model))
        return trial,row

    def response(self):
        check,payload=self.origin_directions()
        result=self.base_result();result.update(direction_scales=[],trials=[],accepted_B=0)
        point,resolution,audit=self.resolved(self.hidden,self.gamma)
        best=None
        for index,row in enumerate(check['directions']):
            scale=fixed_head_scale(self.hidden,point['bar_residual'],payload['response_'+str(index)],
                                   self.bnorm,row['gradient_directional'])
            scale.update(direction=row['name'],tangent_qualified=row['qualified'],
                         minimum_prediction=max(1e-12,100*resolution['delta_J']))
            result['direction_scales'].append(scale)
            if row['qualified'] and scale['sign_trustworthy'] and scale['pred']>scale['minimum_prediction']:
                if best is None or scale['pred']>best[1]['pred']:
                    best=(index,scale)
        if best is None:
            result.update(status='PREDICTED_GAIN_UNRESOLVED_CONTINUE_C',initial_loss=point['loss'])
            self.stage.event('B_no_resolved_prediction_continue_C',scales=result['direction_scales'])
            return result
        index,scale=best
        d=scale['sign']*payload['direction_'+str(index)];v=scale['sign']*payload['response_'+str(index)]
        for trial_index in range(4):
            alpha=scale['alpha']/4**trial_index
            if predicted_gain(point['bar_residual'],alpha*v,self.bnorm)<=max(1e-12,100*resolution['delta_J']):
                break
            candidate,row=self.try_trial('B_trial_'+str(trial_index),self.hidden,self.gamma,point,
                resolution['delta_J'],audit,self.hidden+alpha*d,self.gamma,v,alpha)
            result['trials'].append(row)
            if row['accepted']:
                result['states'].append(self.state_row('B_ACCEPTED',self.hidden+alpha*d,self.gamma,candidate,
                                                     row['trial_audit'],pred=row['pred'],ared=row['ared']))
                result['accepted_B']=1;break
        result.update(status='B_ACCEPTED' if result['accepted_B'] else 'B_BOUNDED_NEGATIVE',initial_loss=point['loss'])
        return result

    def compensate(self):
        from src.solvers.neural_linear_head_torch import build_head_mapping
        check,payload=self.origin_directions()
        result=self.base_result();result.update(rounds=[],trials=[],accepted_C=0,head_only_twins=[],
                                               B_is_not_warm_start=True)
        selected=[i for i,r in enumerate(check['directions']) if r['qualified']]
        if not selected:
            result['status']='C_NOT_RUN_NO_TRUSTWORTHY_TANGENT';return result
        hidden=self.hidden.copy();gamma=self.gamma.copy()
        point,resolution,audit=self.resolved(hidden,gamma)
        initial_loss=point['loss'];initial_audit=audit
        result['initial_loss']=initial_loss
        initial_main,initial_path=read_v11('MAIN')
        for round_index in range(1,4):
            self.stage.guard(large=True)
            pairs,gradient,proposed=self.duals(hidden,gamma,point)
            if round_index==1:
                directions=[payload['direction_'+str(i)] for i in selected]
                fixed_t=[payload['tangent_'+str(i)] for i in selected]
                fixed_v=[payload['response_'+str(i)] for i in selected]
                P_path=initial_path.parent/'initial/P.npy';A_path=initial_path.parent/'initial/A.npy'
                P_meta=dict(reused_initial_P=True,P_sha256=file_hash(P_path),A_sha256=file_hash(A_path))
            else:
                directions=[];fixed_t=[];fixed_v=[]
                for i in selected:
                    d=proposed[i][1];_,dt=self.tangent(hidden,gamma,d)
                    v,_=bar_action(self.stage.packet,self.obj.ports,dt)
                    directions.append(d);fixed_t.append(dt);fixed_v.append(v)
                self.stage.count('PA_builds');self.stage.guard(extra_actions=1560,large=True)
                P_path=self.stage.artifact/('round_'+str(round_index)+'_P.npy');A_path=None
                self.obj.assign(hidden,gamma)
                P,P_meta=build_head_mapping(self.obj.model,self.obj.cache,P_path,
                     heartbeat=lambda event,**fields:self.stage.event(event,**fields))
                del P
            try:
                answer,head_record=self.stage.child_compensation(P_path,A_path,np.column_stack(fixed_v),
                                                               'compensation_'+str(round_index))
            except (ValueError,FileNotFoundError) as error:
                result.update(status='C_HEAD_COMPENSATION_BLOCKED',stop_reason=str(error))
                self.obj.assign(hidden,gamma)
                break
            model_columns=[];good_d=[];good_g=[];joint_records=[]
            for col,d in enumerate(directions):
                dg=answer['dot_gamma'][:,col]
                _,dt_joint=self.tangent(hidden,gamma,d,dg)
                combined=fixed_t[col]+answer['P_dot_gamma'][:,col]
                operation=max(np.linalg.norm(fixed_t[col])+np.linalg.norm(answer['P_dot_gamma'][:,col]),1e-300)
                combination_error=float(np.linalg.norm(dt_joint-combined)/operation)
                vjoint,_=bar_action(self.stage.packet,self.obj.ports,dt_joint)
                vscale=max(np.linalg.norm(fixed_v[col])+np.linalg.norm(fixed_v[col]-answer['thin'][:,col]),1e-300)
                model_error=float(np.linalg.norm(vjoint-answer['thin'][:,col])/vscale)
                back={key:dot_pair(q,dt_joint,gback,parameter_direction(d,dg)) for key,q,gback in pairs}
                h=min(1e-5,1e-3*max(1.,np.linalg.norm(gamma))/max(np.linalg.norm(dg),1e-300))
                fd=self.vector_fd(hidden,gamma,point,d,dt_joint,dg,[h,h/4],
                                  tag=f'C{round_index}_joint_{col}')
                trusted=(combination_error<=1e-9 and model_error<=1e-9 and fd['qualified']
                         and all(v['operation_relative']<=1e-9 for v in back.values()))
                rec=dict(direction=check['directions'][selected[col]]['name'],
                         combination_operation_relative=combination_error,
                         actual_vs_thin_operation_relative=model_error,
                         joint_trace_norm=float(np.linalg.norm(dt_joint)),fixed_trace_norm=float(np.linalg.norm(fixed_t[col])),
                         joint_response_norm=float(np.linalg.norm(vjoint)),fixed_response_norm=float(np.linalg.norm(fixed_v[col])),
                         head_compensation_norm=float(np.linalg.norm(dg)),JVP_VJP=back,vector_Taylor=fd,qualified=bool(trusted))
                joint_records.append(rec)
                if trusted:
                    model_columns.append(vjoint);good_d.append(d);good_g.append(dg)
            round_record=dict(round=round_index,P=P_meta,head_compensation=head_record,joint_checks=joint_records,
                              origin_hidden_hash=array_hash(hidden),origin_gamma_hash=array_hash(gamma))
            result['rounds'].append(round_record)
            if not model_columns:
                result['status']='C_JOINT_TANGENT_UNRESOLVED';break
            self.stage.count('small_real_LS')
            dh,dg,v,small=real_local_step(np.column_stack(good_d),np.column_stack(good_g),
                                        np.column_stack(model_columns),point['bar_residual'])
            tau=common_radius(hidden,gamma,dh,dg)
            round_record.update(small_real_LS=small,common_tau=tau,
                hidden_unscaled_step=float(np.linalg.norm(dh)),head_unscaled_step=float(np.linalg.norm(dg)))
            accepted=None
            for trial_index in range(6):
                step=tau/4**trial_index
                pred=predicted_gain(point['bar_residual'],step*v,self.bnorm)
                if pred<=max(1e-12,100*resolution['delta_J']):
                    round_record['stop_reason']='PREDICTED_GAIN_UNRESOLVED';break
                trial,row=self.try_trial(f'C{round_index}_trial_{trial_index}',hidden,gamma,point,
                       resolution['delta_J'],initial_audit,hidden+step*dh,gamma+step*dg,v,step)
                result['trials'].append(row)
                if row['accepted']:
                    accepted=(hidden+step*dh,gamma+step*dg,trial,row);break
            if accepted is None:
                result['status']='C_BOUNDED_TRIALS_NEGATIVE';self.obj.assign(hidden,gamma);break
            old_hidden=hidden.copy();old_gamma=gamma.copy();old_point=point
            hidden,gamma,point,row=accepted;result['accepted_C']+=1
            result['states'].append(self.state_row('C_'+str(round_index)+'_ACCEPTED',hidden,gamma,point,
                                  row['trial_audit'],pred=row['pred'],ared=row['ared']))
            twin=self.evaluate(old_hidden,gamma);twin_audit=self.stage.audit(twin['z'])
            twinrow=self.state_row('C_'+str(round_index)+'_HEAD_ONLY_TWIN',old_hidden,gamma,twin,twin_audit,
                                 diagnostic_only=True,joint_loss=point['loss'],
                                 head_only_loss=twin['loss'],previous_loss=old_point['loss'],
                                 hidden_incremental_loss_gain=twin['loss']-point['loss'])
            result['states'].append(twinrow);result['head_only_twins'].append(twinrow)
            self.obj.assign(hidden,gamma)
            point,resolution,audit=self.resolved(hidden,gamma)
            progress=(old_point['loss']-point['loss'])/max(old_point['loss'],1e-300)
            cumulative=(initial_loss-point['loss'])/max(initial_loss,1e-300)
            round_record.update(accepted=True,relative_loss_progress=progress,cumulative_loss_progress=cumulative,
                                head_only_loss=twin['loss'],actual_joint_loss=point['loss'])
            result['status']='C_BOUNDED_ACCEPTED'
            self.stage.event('C_joint_accepted',round=round_index,loss=point['loss'],
                             native=audit['native_relative'],twin_loss=twin['loss'],progress=progress)
            if progress<1e-4 or audit['native_relative']>1.05*initial_audit['native_relative']:
                round_record['stop_reason']='NEXT_ROUND_PROGRESS_GATE_FAILED';break
            if round_index==2 and cumulative<.01:
                round_record['stop_reason']='THIRD_ROUND_CUMULATIVE_GATE_FAILED';break
            # Release reconstructible tall workspace once its child exited.
            if round_index>1:
                P_path.unlink(missing_ok=True)
        result['final_loss']=point['loss']
        self.obj.assign(hidden,gamma)
        return result
