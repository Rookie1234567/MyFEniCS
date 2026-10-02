"""One frozen, offline warm-error representation diagnostic, never a PC."""
from time import perf_counter
import numpy as np
from scipy.linalg import solve
from src.solvers.augmented_trace_lsqr import operation_pair


def homogeneous_projection(packet,bar,T,reference,warm):
    e=reference-warm;Gram=(T.conj().T@T).toarray()
    c=solve(Gram,np.asarray(T.conj().T@e[:packet.nt]),assume_a='pos',check_finite=True)
    qt=np.asarray(T@c);qz=bar.close(qt,np.zeros(packet.size,complex));complement=e-qz
    F0=packet.recover(np.zeros(packet.size,complex));Fe=packet.recover(e)-F0
    Fq=packet.recover(qz)-F0;Fc=Fe-Fq
    difference=packet.recover(reference)-packet.recover(warm)
    Ae,Aq,Ac=[bar.apply(v[:packet.nt]) for v in (e,qz,complement)]
    record=dict(recovery_pair=operation_pair(Fe,difference),original_action_pair=operation_pair(Ae,Aq+Ac),
        trace_euclidean_norm=float(np.linalg.norm(e[:packet.nt])),projected_trace_norm=float(np.linalg.norm(qt)),
        complement_trace_norm=float(np.linalg.norm(complement[:packet.nt])),
        trace_Gram_stationarity=float(np.linalg.norm(T.conj().T@complement[:packet.nt])/max(np.linalg.norm(e[:packet.nt]),1e-300)),
        original_bar_action_norm=float(np.linalg.norm(Ae)),projected_bar_action_norm=float(np.linalg.norm(Aq)),complement_bar_action_norm=float(np.linalg.norm(Ac)),
        original_action_complex_cross=np.vdot(Aq,Ac),
        operation_cross_sum_defect=float(abs(np.linalg.norm(Ae)**2-np.linalg.norm(Aq)**2-np.linalg.norm(Ac)**2-2*np.vdot(Aq,Ac).real)/max(np.linalg.norm(Ae)**2+np.linalg.norm(Aq)**2+np.linalg.norm(Ac)**2,1e-300)),
        projection_metric='trace Euclidean Gram; not physical L2 optimal',
        affine_particular_removed=True,reference_feedback=False)
    if max(record['recovery_pair']['operation_relative'],record['original_action_pair']['operation_relative'])>1e-10:
        raise ValueError('offline homogeneous/projection identity failed')
    return dict(e=e,q=qz,complement=complement,c=c,Fe=Fe,Fq=Fq,Fc=Fc),record


def frozen_callback(stage):
    setup,_=stage.io.read_result('SETUP')
    try:primary,_=stage.io.read_result('P')
    except OSError:return None
    if not setup.get('PC_qualified') or 'final' not in primary or primary['first_pass_cycle'] is not None:return None
    if primary['start']['original_equation_gate']['rho']/primary['final']['original_equation_gate']['rho']>=10:return None
    def diagnose(context):
        from scipy.sparse import load_npz
        import ufl
        from dolfinx import fem
        from src.runners.task042_shared import write_json
        from src.runners.orthonormal_trace_reprofile import atomic_arrays
        from src.solvers.neural_fe_action_packet import file_hash
        from src.solvers.p1_trace_study import bars
        start=perf_counter();stage.guard(large=True);stage.count('field_states',3)
        if file_hash(setup['T']['path'])!=setup['T']['sha256']:raise ValueError('offline T identity')
        T=load_npz(setup['T']['path']);old,_=bars(stage)
        stage.pc_count('coarse_triangular',2)
        arrays,row=homogeneous_projection(stage.packet,old,T,context['reference'],context['states']['V21-C-FINAL'])
        row['state']=atomic_arrays(stage.artifact/'OFFLINE_WARM_ERROR.npz',**arrays)
        fields=[context['restore'](arrays[k]) for k in ('Fe','Fq','Fc')]
        measured=[context['norms'](f) for f in fields]
        q,comp=fields[1:];dx=context['dx'];k0=context['k0']
        crossE=fem.assemble_scalar(fem.form(ufl.inner(comp,q)*dx))
        crossC=fem.assemble_scalar(fem.form(ufl.inner(ufl.curl(comp)/k0,ufl.curl(q)/k0)*dx))
        cross=np.array([crossE,crossC]);squares=np.asarray(measured)**2
        defect=abs(squares[0]-squares[1]-squares[2]-2*cross.real)/np.maximum(squares.sum(axis=0),1e-300)
        row.update(field_L2_scaled_curl_norms=dict(zip(('full_error','T_projection','complement'),measured)),
            relative_to_full_error=np.asarray(measured[1:])/np.maximum(measured[0],1e-300),
            complex_cross_L2_scaled_curl=cross,field_square_sum_relative=defect,
            diagnostic_seconds=perf_counter()-start,additional_offline_Gram_factor='bounded Cholesky solve; never candidate PC/loss',
            original_Ac_PC_not_changed=True,not_a_solution=True,solver_frozen=True)
        if row['diagnostic_seconds']>120:row['status']='DIAGNOSTIC_120_SECOND_LIMIT_EXCEEDED'
        elif np.max(defect)>1e-10:row['status']='DIAGNOSTIC_FIELD_IDENTITY_FAILED'
        else:row['status']='OFFLINE_DIAGNOSTIC_COMPLETE'
        write_json(stage.artifact/'offline_projection.json',row);return row
    return diagnose
