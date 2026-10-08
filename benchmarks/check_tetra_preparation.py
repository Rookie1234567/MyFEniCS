"""Saved preparation and exact cache inventory; no body action or solve."""
from collections import OrderedDict
import hashlib
import json
from pathlib import Path

import numpy as np

from src.runners.task042_shared import write_json
from src.solvers.scattering_anchor import array_hash
from src.solvers.scattering_anchor_checks import checked_arrays


def exact_cache_inventory(geometry, permutations, *, bytes_per_class, limit=512*2**20):
    """Simulate only the existing exact-J/orientation LRU, never a new action."""
    if len(geometry) != len(permutations) or bytes_per_class <= 0 or bytes_per_class > limit:
        raise ValueError('exact cache inventory capacity')
    cache=OrderedDict();used=0;hits=0;misses=0;all_keys=set()
    for J,p in zip(geometry,permutations,strict=True):
        J=np.asarray(J)
        if J.shape!=(3,3) or not np.isfinite(J).all():raise ValueError('actual affine J')
        key=(J.tobytes(),int(p));all_keys.add(key)
        if key in cache:hits+=1;cache.move_to_end(key);continue
        misses+=1
        while cache and used+bytes_per_class>limit:
            cache.popitem(last=False);used-=bytes_per_class
        cache[key]=True;used+=bytes_per_class
    return dict(cells=len(geometry),unique_exact_keys=len(all_keys),hits=hits,misses=misses,
        repeated_rebuilds=misses-len(all_keys),bytes_per_class=bytes_per_class,
        limit_bytes=limit,resident_class_capacity=limit//bytes_per_class,
        all_unique_table_bytes=len(all_keys)*bytes_per_class,
        classification='DERIVED_EXACT_CACHE_WALK_NOT_RUNTIME_PROFILE',
        rounding=False,new_body_actions=0,new_numeric_factors=0,new_complete_solves=0)


def array_receipt(path):
    path=Path(path);members={}
    with np.load(path,allow_pickle=False) as saved:
        for name in saved.files:
            a=saved[name];members[name]=dict(shape=list(a.shape),dtype=str(a.dtype),sha256=array_hash(a))
    return dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),members=members,
        hash_first_recorded_at_saved_consumer=True)


def partial_saved_check(scope,folder,journal):
    """Consume partial P6 plus the frozen mesh without restarting their PDE."""
    from src.solvers import independent_tetra_reference as core
    from src.solvers.independent_tetra_study import load_boundary
    from src.solvers.fullspace_dtn_action import build_dynamic_mode_inventory
    from src.solvers.scattering_accuracy_boundary import carrier_pair
    from src.solvers.scattering_anchor import relative
    pre=scope.stage('PREFLIGHT');mark=checked_arrays(pre['marking']['arrays'])
    ids=mark['indices'];order=mark['order'];eta=mark['eta_squared'];n=len(ids)
    total=float(eta.sum());coverage=float(eta[ids].sum()/total)
    if not np.array_equal(ids,order[:n]) or len(np.unique(order))!=len(eta) or coverage<.5 or float(eta[order[:n-1]].sum())>=.5*total:
        raise ValueError('saved fixed minimum marking prefix')
    mesh=checked_arrays(pre['local_mesh']['attempts'][0]['arrays'])
    original=mark['geometry_x'][mark['geometry_dofmap']]
    fine=mesh['geometry_x'][mesh['geometry_dofmap']]
    volume=lambda x:np.abs(np.linalg.det(np.transpose(x[:,1:]-x[:,:1],(0,2,1))))/6
    parent=mesh['original_parent_cell'];v0=volume(original);v1=volume(fine)
    operation=float(np.max(np.abs(np.bincount(parent,weights=v1,minlength=len(v0))-v0)/v0))
    tags_equal=bool(np.array_equal(mesh['cell_tags'],mark['parent_cell_tags'][parent]))
    if operation>1e-10 or not tags_equal:raise ValueError('saved local ancestry/volume/material')
    local=dict(selected=n,coverage=coverage,minimum_prefix=True,cells=len(fine),
        actual_rows=pre['local_mesh']['spec']['rows'],parent_volume_operation=operation,tags_equal=tags_equal,
        capacity_admitted=len(fine)<=19200 and pre['local_mesh']['spec']['rows']<=800000)
    if local['capacity_admitted']!=pre['local_mesh']['admitted']:raise ValueError('L4 published capacity differs from actual counts')
    write_json(folder/'local_mesh_independent.json',local)
    run=next(r for r in scope.window.ledger()['runs'] if r['role']=='P6')
    producer=scope.ARTIFACT/Path(run['folder']).name
    stop=json.loads((scope.window.TMP/'P6_case_reserve_stop.json').read_text())
    events=[json.loads(line) for line in (producer/'events.jsonl').read_text().splitlines()]
    if any(e['event']=='h_bounded_numeric_factor_begin' for e in events) or (producer/'returned_audit_pending.json').exists():
        raise ValueError('partial-only consumer cannot hide a numeric attempt or returned field')
    with journal.measured('saved_preparation_boundary_and_cache_inventory'):
        s=core.make_setup(scope.case_spec('P6'),scope.physical_for('P6'),journal)
        ev=core.TetraEvaluator(s['V'],17,s['kappa'])
        # The current kernel stores real b and complex Ckappa(b); no matrices.
        per_class=ev.values.size*(ev.values.dtype.itemsize+np.dtype(np.complex128).itemsize)
        cache=exact_cache_inventory([g[0] for g in ev.geometry],ev.permutations,bytes_per_class=per_class)
        cache.update(degree=s['spec']['degree'],basis_dimension=s['V'].element.space_dimension,
            actual_quadrature_points=len(ev.points),quadrature_degree=17,
            body_kernel_sha256=hashlib.sha256(Path(core.__file__).read_bytes()).hexdigest(),
            whole_original_gate_pass=False,causal_runtime_attribution='not measured; exact-key churn is a candidate cost explanation')
        write_json(folder/'exact_oracle_cache_inventory.json',cache)
        receipts={q:array_receipt(producer/('triangle_'+q+'.npz')) for q in ('q47','q63')}
        _,_,mode_hash=build_dynamic_mode_inventory(s['cfg'])
        first=load_boundary(s,receipts,mode_hash,q='q47');second=load_boundary(s,receipts,mode_hash,q='q63')
        pair=carrier_pair(first['carrier'],second['carrier'],first['identities'],expected_modes=828)
        incident=relative(first['incident']-second['incident'],second['incident'])
        if not pair['pass'] or incident>1e-11:raise ValueError('saved complete boundary qualification')
        write_json(folder/'saved_boundary_pair_full.json',dict(pair=pair,incident=incident))
    result=dict(status='PARTIAL_PREPARATION_AND_MESH_ONLY',local_mesh=local,cache_inventory=cache,
        boundary=dict(arrays=receipts,complete_modes=828,mode_sha256=mode_hash,pass_gate=pair['pass'],
            max_operation_scaled=pair['max_operation_scaled'],max_relative=pair['max_relative'],incident=incident),
        controlled_stop=stop,new_numeric_factors=0,new_complete_solves=0,new_body_actions=0,
        interpretation_mesh_space_reconstructions=1,whole_original_gate='NOT_COMPLETED',
        P6_field='NOT_RETURNED',field_accuracy='NOT_RUN',NN20=False)
    write_json(folder/'partial_preparation_checker.json',result);return result
