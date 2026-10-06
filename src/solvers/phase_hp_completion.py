"""Thin V53 queue over the existing complete physical Maxwell authority."""
import hashlib
import json
import numpy as np
from src.runners.task042_shared import write_json
from . import phase_hp_completion_scope as scope
from .phase_notch_hp import configured_setup,restore_record,compare_saved,solve_case,verify_cost
from .phase_notch_hp_capacity import assembly_capacity
from .phase_explicit_accuracy_capacity import numeric_plan
from .phase_explicit_accuracy_fields import PhaseEvaluator
from .phase_evaluation_cache import CachedPhaseEvaluator,cached_evaluator_factory
from .scattering_anchor import Journal,save_arrays,relative


def cache_qualification(folder,journal):
    """One small pairing from the real saved H/P, then a p7 complex witness."""
    from dolfinx import fem
    from .phase_notch_hp_fields import common_boxes,mesh_bounds
    hp=[restore_record(scope.parent(role),journal,scope=scope) for role in ('H','P')]
    boxes,pa,pb=common_boxes(*[mesh_bounds(row[3].function_space) for row in hp])
    rows=[];witness={}
    for side,(cfg,setup,geo,field) in enumerate(hp):
        old=PhaseEvaluator(field.function_space,15,np.array([cfg.kx,cfg.ky,0]))
        new=CachedPhaseEvaluator(field.function_space,15,old.kappa)
        for b in (0,len(boxes)//2):
            c=int((pa,pb)[side][b]);box=boxes[b]
            points=old.points*(box[1]-box[0])+box[0];weights=old.weights*np.prod(box[1]-box[0])
            x=old.at(field,c,points,cfg.k0);y=new.at(field,c,points,cfg.k0)
            # A second literal call tests an actual cache hit, without rounding
            # coordinates or constructing another old complete comparison.
            z=new.at(field,c,points,cfg.k0)
            for k in ('E','H','curl'):
                operation=relative(y[k]-x[k],x[k]);square=np.sum(weights[:,None]*np.abs(x[k])**2)
                delta=np.sum(weights[:,None]*(np.abs(y[k])**2-np.abs(x[k])**2))
                rows.append(dict(role=('H','P')[side],common_box=b,parent=c,component=k,
                    operation=operation,max_absolute=float(np.max(np.abs(y[k]-x[k]))),
                    weighted_square_operation=float(abs(delta)/max(square,1e-30)),repeat=relative(z[k]-y[k],y[k])))
                witness[f'{side}_{b}_{k}_old']=x[k];witness[f'{side}_{b}_{k}_cached']=y[k]
    cfg,setup,geo=configured_setup(scope.case_spec('B'),journal,scope=scope)
    V=setup['spaces'][7];element=V.element.basix_element
    if element.dim!=1344 or len(element.entity_dofs[3][0])!=756:raise ValueError('actual p7 basis/interior dimensions')
    mem=scope.plan_record()['memory_budget']
    capacity=assembly_capacity(setup,cfg,journal,scope.case_spec('B'),planning_limit_bytes=mem['planning_gib']*2**30,
        sampled_stop_bytes=mem['sampled_stop_gib']*2**30,extra_workspace_bytes=mem['extra_cache_workspace_gib']*2**30)
    f=fem.Function(V);rng=np.random.default_rng(5307);f.x.array[:]=rng.standard_normal(len(f.x.array))+1j*rng.standard_normal(len(f.x.array))
    old=PhaseEvaluator(V,5,np.array([cfg.kx,cfg.ky,0]));new=CachedPhaseEvaluator(V,5,old.kappa)
    cells=np.unique(old.permutations,return_index=True)[1][:2]
    for c in cells:
        J,o,_=old.geometry[c];points=old.points@J.T+o
        x=old.at(f,int(c),points,cfg.k0);y=new.at(f,int(c),points,cfg.k0)
        for k in x:
            rows.append(dict(role='P7_COMPLEX',parent=int(c),permutation=int(old.permutations[c]),component=k,
                operation=relative(y[k]-x[k],x[k]),max_absolute=float(np.max(np.abs(y[k]-x[k])))))
    return dict(rows=rows,pass_gate=all(r['operation']<=1e-11 for r in rows),
        witness=save_arrays(folder/'exact_field_cache_qualification.npz',**witness),
        native_eval_max=max(old.eval_checks+new.eval_checks,default=0.),
        p7_dimension=element.dim,p7_interior=756,p7_capacity=capacity,
        parent_hashes={r:scope.parent(r)['arrays']['sha256'] for r in ('H','P')},
        scope='few frozen real subcells only; no old full integral replay',
        extra_cache_workspace_limit_bytes=2*2**30)


def preflight(folder,journal):
    p=scope.plan_record();old=json.loads((scope.ROOT/p['old_hp_symbolic_record']).read_text())
    old16=numeric_plan(old['tree']['rss_bytes'],old['info'],16*2**30)
    new32=numeric_plan(old['tree']['rss_bytes'],old['info'],32*2**30)
    over32=numeric_plan(32*2**30,old['info'],32*2**30)
    if old16['admitted'] or not new32['admitted'] or over32['admitted']:raise ValueError('explicit 16/32/over32 capacity regression')
    cache=cache_qualification(folder,journal)
    # A cache failure cannot block the trusted original evaluation route.
    write_json(scope.window.TMP/'cache_qualification.json',cache)
    return dict(status='COMPLETED',role='SETUP',pass_gate=True,capacity_regression=dict(old16=old16,new32=new32,over32=over32),
        cache=cache,memory_budget=p['memory_budget'],new_factor_count=0,new_complete_solves=0,
        parents={r:scope.parent(r)['arrays']['sha256'] for r in ('H','P')},timings=journal.timings,calls=journal.calls)


def finish_comparisons(role,result,journal):
    cache=scope.ARTIFACT/'comparisons';cache.mkdir(exist_ok=True)
    qualification=json.loads((scope.window.TMP/'cache_qualification.json').read_text())
    rows=[]
    for left in scope.plan_record()['comparison_partners'][role]:
        previous=result['projected_parent828'] if role=='M' else scope.read(left)
        if not previous.get('equation_pass'):continue
        name=left+'_'+role;path=cache/(name+'.json')
        if path.exists():
            r=json.loads(path.read_text())
            if r['parent_array_sha256']!=[previous['arrays']['sha256'],result['arrays']['sha256']]:raise ValueError('V53 cached pair identity')
        else:
            sub=cache/(name+'_'+journal.folder.name);sub.mkdir(exist_ok=False)
            factory=cached_evaluator_factory() if qualification['pass_gate'] else None
            r=compare_saved(previous,result,sub,journal,scope=scope,evaluator_factory=factory)
            write_json(path,r)
        rows.append(dict(pair=[left,role],comparison_path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),pass_gate=r['pass_gate']))
    return rows


def cached_comparisons():
    rows=[]
    for path in sorted((scope.ARTIFACT/'comparisons').glob('*.json')):
        r=json.loads(path.read_text());rows.append(dict(pair=path.stem.split('_'),path=str(path),
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),pass_gate=r['pass_gate'],fields=r['fields'],
            selected=r['selected'],power_differences=r['power_differences'],quadrature_operation_scaled=r['quadrature_operation_scaled']))
    return rows


def execute(role,folder,state):
    p=scope.plan_record();journal=Journal(folder,window_scope=scope.window,planning_limit_bytes=p['memory_budget']['planning_gib']*2**30)
    journal.source_state=state
    if state.get('memory_budget')!=p['memory_budget']:raise ValueError('live numerical memory budget mismatch')
    if role=='SETUP':return preflight(folder,journal)
    if role in scope.SOLVES:
        result=solve_case(role,folder,journal,scope=scope)
        # Persist the final complete solve before pairwise postprocessing. A
        # failed presentation/comparison can resume without another factor.
        write_json(folder/'completed_before_comparison.json',result)
        if result.get('equation_pass'):result['comparisons']=finish_comparisons(role,result,journal)
        result.update(timings=journal.timings,calls=journal.calls)
        return result
    if role=='VERIFY_COST':return verify_cost(folder,journal,scope=scope)
    raise ValueError('V53 stage inventory')
