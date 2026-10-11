"""Saved harmonic dual/Galerkin checker, then the shared independent field audit."""
import json
import numpy as np
from src.solvers import harmonic_trace_scope as scope
from src.solvers.harmonic_trace_coarse import HarmonicTransfer
from src.solvers.bounded_trace_pc import csr_load
from src.solvers.scattering_anchor_checks import checked_arrays
from src.solvers.scattering_anchor import relative
from src.runners.task042_shared import write_json


def verify(folder,journal):
    H=scope.stage('HARMONIC_PREPARE');T=HarmonicTransfer.load(H['transfer']);EH=csr_load(H['coarse_matrix']);rows=[]
    owner=checked_arrays(H['partition']['partition'])['owner']
    for r in H['qualification']:
        a=checked_arrays(r['arrays']);v=T.prolong(a['w']);y=T.restrict(a['original']);target=EH@a['w']
        e=dict(prolonged=relative(v-a['prolonged'],v),dual_pullback=relative(y-a['pulled'],y),
            saved_coarse=relative(target-a['coarse_action'],target),Galerkin=relative(y-target,target),
            homogeneous=relative(a['original'][:len(owner)][owner>=0],a['original']),
            dual=float(abs(np.vdot(v,a['original'])-np.vdot(a['w'],y))/max(np.linalg.norm(v)*np.linalg.norm(a['original']),1e-300)))
        rows.append(e)
    mathematical=all(max(r.values())<=1e-10 for r in rows)
    if not mathematical:raise ValueError('saved harmonic Galerkin/full complex dual consumption')
    write_json(folder/'saved_harmonic_checks.json',dict(rows=rows,pass_gate=mathematical,coarse_rows=EH.shape[0]))
    from benchmarks.collect_restart_feedback import verify as shared
    result=shared(folder,journal,scope_module=scope);result['harmonic_checks']=rows;return result
