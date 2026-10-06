"""Opt-in, no-JIT material absorption from the authoritative total envelope.

Each cell is integrated with the original covariant Piola field. Completed
blocks carry a complete input identity and can be read without recomputation.
The existing UFL absorption backend and its default callers stay unchanged.
"""
import hashlib
import json
from pathlib import Path
import numpy as np
from src.runners.task042_shared import write_json
from src.solvers.scattering_anchor import save_arrays


def array_hash(a):
    return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()


def checked_block(path, identity):
    from src.solvers.scattering_anchor_checks import checked_arrays
    row=json.loads(Path(path).read_text())
    if row['identity']!=identity:raise ValueError('quadrature block input identity changed')
    return checked_arrays(row['arrays'])


def material_metrics(cfg, rows, incident_power, port_metrics=None):
    """Pure reduction: total |u|^2, both absorbing regions, no clipping."""
    if not np.isfinite(rows).all() or incident_power<=0:raise ValueError('finite absorption and positive incident power')
    regions={}
    for name,tag,eps,n,label in (
        ('grating',cfg.tags.grating,cfg.eps_grating,cfg.grating_index,cfg.grating_material_label),
        ('substrate',cfg.tags.substrate,cfg.eps_substrate,cfg.substrate_index,cfg.substrate_material_label)):
        mask=rows[:,0]==tag;power=float(.5*cfg.k0*complex(eps).imag*rows[mask,1].sum())
        regions[name]=dict(name=name,tag=int(tag),cell_count=int(mask.sum()),volume_nm3=float(rows[mask,2].sum()),
            n_complex=[complex(n).real,complex(n).imag],epsilon_r_complex=[complex(eps).real,complex(eps).imag],
            Im_epsilon_r=complex(eps).imag,material_label=label,status='ok' if mask.any() else 'missing',
            reason=None,absorbed_power_code_units=power,A_volume=power/incident_power)
    a=regions['grating']['A_volume'];b=regions['substrate']['A_volume'];total=a+b;pm=port_metrics or {}
    energy=None if not {'R_total','T_total'}<=pm.keys() else pm['R_total']+pm['T_total']+total-1
    return dict(method='volume_absorption',role='absorption_check',status='ok',backend='direct_phase_quadrature',
        power_source='volume_integral_Im_epsilon_E2',field_model_for_absorption='total_field',
        incident_power_code_units=incident_power,formula_code_units='k0/(2 P_inc) sum Im(epsilon) integral |u_total|^2',
        epsilon_definition='epsilon=n*n; no clipping, no replacement by 1-R-T',
        pml_cells_excluded=True,air_cells_excluded=True,regions=regions,A_grating=a,A_substrate=b,
        A_volume_grating=a,A_volume_substrate=b,A_volume_total=total,
        A_port_balance_minus_A_volume_total=None if 'A_balance' not in pm else pm['A_balance']-total,
        energy_closure_error_port_volume=energy)


def phase_volume_absorption(mesh_data,cfg,function,kappa,folder,*,incident_power,port_metrics=None,journal,
                            rules=(23,31),point_block=256,cell_block=8):
    from src.solvers.phase_evaluation_cache import CachedPhaseEvaluator,ExactTabulations
    if point_block>256 or point_block<1:raise ValueError('bounded absorption point block')
    kappa=np.asarray(kappa)
    if kappa.shape!=(3,) or not np.isrealobj(kappa) or not np.isfinite(kappa).all():raise ValueError('real phase for |g|=1')
    V=function.function_space;m=V.mesh
    if m.comm.size!=1:raise ValueError('qualified saved-consumer MPI1 only')
    nc=m.topology.index_map(3).size_local;tags=np.empty(nc,np.int32)
    if not np.array_equal(np.sort(mesh_data.cell_tags.indices),np.arange(nc)):raise ValueError('complete physical material cell partition')
    tags[mesh_data.cell_tags.indices]=mesh_data.cell_tags.values
    if not np.isin(tags,[cfg.tags.air,cfg.tags.grating,cfg.tags.substrate]).all():raise ValueError('unqualified physical region')
    base=dict(u_full_sha256=array_hash(function.x.array),geometry_sha256=array_hash(m.geometry.x),
        geometry_dofmap_sha256=array_hash(m.geometry.dofmap),tag_sha256=array_hash(tags),kappa_sha256=array_hash(kappa),
        basis_coefficients_sha256=array_hash(V.element.basix_element.coefficient_matrix),degree=V.element.basix_element.degree,
        source_module_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),cells=nc,
        epsilon={str(t):[complex(e).real,complex(e).imag] for t,e in ((cfg.tags.air,cfg.eps_air),(cfg.tags.grating,cfg.eps_grating),(cfg.tags.substrate,cfg.eps_substrate))})
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True);results=[];receipts=[]
    cache=ExactTabulations(64*2**20)
    for q in rules:
        ev=CachedPhaseEvaluator(V,q,kappa,cache=cache,quadrature_tables=False)
        identity=dict(base,q_degree=q,point_sha256=array_hash(ev.points),weight_sha256=array_hash(ev.weights),point_count=len(ev.points))
        sub=folder/f'volume_q{q}';sub.mkdir(exist_ok=True);rows=np.empty((nc,3));reused=0
        with journal.measured(f'direct_volume_absorption_q{q}'):
            for start in range(0,nc,cell_block):
                stop=min(start+cell_block,nc);path=sub/f'block_{start:06d}_{stop:06d}.json'
                expected=dict(identity,start=start,stop=stop)
                if path.exists():
                    saved=checked_block(path,expected)
                    if not np.array_equal(saved['cell_ids'],np.arange(start,stop)):raise ValueError('absorption block inventory')
                    rows[start:stop]=saved['rows'];reused+=stop-start;continue
                for c in range(start,stop):
                    J,o,det=ev.geometry[c];total=0.
                    for j in range(0,len(ev.points),point_block):
                        pts=ev.points[j:j+point_block]@J.T+o
                        e=ev.at(function,c,pts,cfg.k0)['E']
                        total+=float(det*np.sum(ev.weights[j:j+point_block,None]*np.abs(e)**2))
                    rows[c]=[tags[c],total,det*ev.weights.sum()]
                receipt=save_arrays(path.with_suffix('.npz'),cell_ids=np.arange(start,stop),rows=rows[start:stop])
                write_json(path,dict(identity=expected,arrays=receipt))
                journal.event('absorption_cell_block_committed',q=q,start=start,stop=stop)
        metrics=material_metrics(cfg,rows,incident_power,port_metrics)
        receipt=save_arrays(folder/f'volume_integrals_q{q}.npz',rows=rows,points=ev.points,weights=ev.weights,cell_ids=np.arange(nc))
        metrics.update(quadrature=identity,arrays=receipt,reused_cells=reused,independent_native_eval_max=max(ev.eval_checks,default=0.))
        write_json(folder/f'volume_absorption_q{q}.json',metrics);results.append(metrics);receipts.append(receipt)
    high=results[-1];values=np.asarray([r['A_volume_total'] for r in results])
    qdef=float(np.max(np.abs(values-values[-1]))/max(abs(values[-1]),1e-30))
    high.update(q_pair=list(rules),quadrature_operation_scaled=qdef,quadrature_pass=qdef<=1e-10,
        bounded_workspace=dict(point_block=point_block,cell_block=cell_block,table_cache=cache.record(),limit_bytes=2*2**30),all_rule_arrays=receipts)
    write_json(folder/'volume_absorption.json',high)
    return high
