"""One bounded full-body cross-space defect; no inverse or new PDE solve."""
import json
from pathlib import Path
import numpy as np
from src.runners.task042_shared import write_json
from .scattering_anchor import relative,save_arrays
from .scattering_anchor_checks import checked_arrays


def consume_defect(folder,journal,scope):
    from .phase_notch_hp import restore_record
    from .phase_p_order_consistency import FullBodyEmbedding
    from .fullspace_same_mesh_hcurl_pmg_physical import restore_p0_full_field
    from .phase_saved_uncondensed import uncondensed_vectors
    from .phase_boundary_checkpoint import packed_action
    from .phase_deployment import old_high_body
    low,high=[scope.parent(k) for k in ('R6','R7')]
    a,b=[restore_record(r,journal,scope=scope) for r in (low,high)]
    vl,vh=[checked_arrays(r['arrays']) for r in (low,high)]
    if low['mode_sha256']!=high['mode_sha256'] or not np.array_equal(vl['kappa'],vh['kappa']):raise ValueError('full P diagnostic mode/carrier identity')
    for k in a[2]:
        if not np.array_equal(a[2][k],b[2][k]):raise ValueError('full P diagnostic geometry '+k)
    embedding=FullBodyEmbedding(a[1]['floquets'][6],b[1]['floquets'][7]);mapped=embedding.forward(vl['u_storage'])
    delta=vh['u_storage']-mapped;out=[]
    degree=17 if scope.stage('P')['body_low_q_pass'].get('7') else 31
    for name,coeff in (('mapped_R6',mapped),('delta',delta)):
        field=restore_p0_full_field(b[1]['floquets'][7],coeff)
        value=uncondensed_vectors(field,b[0],vh['kappa'],b[1]['floquets'][7].mpc,b[1]['mesh_data'],folder/name,journal,q=degree,
            identity=dict(low=low['arrays']['sha256'],high=high['arrays']['sha256'],full_body_embedding=True,label=name))
        out.append(value['volume'][:,0])
    bound=checked_arrays(high['boundary']['arrays'][1]);high_original=checked_arrays(old_high_body('R7'))
    Ap=out[0]+packed_action(bound,mapped);Ad=out[1]+packed_action(bound,delta)
    A7=high_original['volume_action']+packed_action(bound,vh['u_storage']);rhs=vh['rhs']
    defect=rhs-Ap;r7=rhs-A7;identity=defect-r7-Ad
    operation=float(np.linalg.norm(identity)/max(sum(np.linalg.norm(v) for v in (rhs,Ap,A7,Ad)),1e-30))
    dual=embedding.adjoint(defect);ids=high_original['internal_rows'];masters=np.setdiff1d(np.arange(len(mapped)),vh['slaves']);trace=np.setdiff1d(masters,ids)
    arrays=save_arrays(folder/'full_saved_defect.npz',u6=vl['u_storage'],u7=vh['u_storage'],Pu6=mapped,delta=delta,
        A7Pu6=Ap,A7delta=Ad,A7u7=A7,b7=rhs,defect=defect,r7=r7,identity=identity,P_H_defect=dual,
        internal_rows=ids,trace_rows=trace,physical_port_residual=high_original['port_residual'])
    r=dict(status='COMPLETED',role='S',arrays=arrays,parents={k:v['arrays']['sha256'] for k,v in (('R6',low),('R7',high))},
        full_body_transfer=True,body_q=degree,port_q=63,shared_embedding_defect=embedding.shared_defect,
        identity_operation_scaled=operation,identity_pass=operation<=1e-10,
        full_defect_norm=float(np.linalg.norm(defect)),original_rhs_norm=float(np.linalg.norm(rhs)),
        original_rhs_relative=float(np.linalg.norm(defect)/max(np.linalg.norm(rhs),1e-30)),
        pulled_defect_norm=float(np.linalg.norm(dual)),internal_defect_norm=float(np.linalg.norm(defect[ids])),
        trace_defect_norm=float(np.linalg.norm(defect[trace])),high_saved_residual_norm=float(np.linalg.norm(r7)),
        physical_DtN_form='ports exactly eliminated using original q63 CD/H; saved augmented port residual separately retained',
        no_condition_number_no_error_bound=True,new_complete_solves=0,new_factor_count=0)
    write_json(folder/'full_saved_defect.json',r);return r
