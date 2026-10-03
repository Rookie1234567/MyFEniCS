"""Replay CPU admission from saved filtered observations; no host re-probe."""
import numpy as np
from src.runners.task042_shared import spare_cores,cpu_exclusions


def replay(receipt):
    fractions={int(k):v for k,v in receipt['cpu_busy_fractions'].items()}
    deltas={int(k):v for k,v in receipt['thread_delta_ticks'].items()}
    ticks0={int(k):v for k,v in receipt['cpu_ticks_before'].items()}
    ticks1={int(k):v for k,v in receipt['cpu_ticks_after'].items()}
    for cpu,first in ticks0.items():
        last=ticks1[cpu];elapsed=max(sum(last)-sum(first),1)
        value=1-(last[3]-first[3]+last[4]-first[4])/elapsed
        if not np.isfinite(value) or abs(value-fractions[cpu])>1e-15:raise ValueError('CPU sample fraction differs')
    tb={int(k):v for k,v in receipt['thread_ticks_before'].items()}
    ta={int(k):v for k,v in receipt['thread_ticks_after'].items()}
    for tid,last in ta.items():
        if tid in tb and last[0]==tb[tid][0] and deltas.get(tid)!=last[1]-tb[tid][1]:raise ValueError('thread start/delta identity differs')
    topology=receipt['topology'];neighbors=receipt['neighbor_processes']
    if receipt['allowed_cpus']!=[x['cpu'] for x in topology] or receipt['sample_interval_seconds']<=0:raise ValueError('allowed CPU/sample inventory')
    candidates=spare_cores(topology,neighbors,fractions,deltas)
    if candidates!=receipt['candidate_cpus'] or cpu_exclusions(topology,neighbors,fractions,deltas)!=receipt['cpu_decisions']:raise ValueError('CPU exclusion replay differs')
    gate='PASS' if candidates else 'FAIL'
    if receipt['gates']['CPU_SMT']!=gate:raise ValueError('CPU gate replay differs')
    if not candidates and any(receipt['gates'][k]!='NOT_CHECKED' for k in ('MEMORY','DISK','PSI','CGROUP_GPU_SNAPSHOT')):raise ValueError('unvisited resource gate claimed checked')
    if receipt['status']=='ADMITTED' and (not candidates or receipt['selected_cpu']!=candidates[0]):raise ValueError('wrong selected CPU')
    return dict(status='CPU_RECEIPT_REPLAYED',candidate_cpus=candidates,CPU_SMT=gate,other_gates=receipt['gates'],
        no_live_probe=True,no_reinterpretation_as_zero_interference=True)
