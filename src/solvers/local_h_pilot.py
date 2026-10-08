"""Thin V64 stage adapter: one frozen mesh, existing complete tetra solves."""
import gc
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from src.runners.task042_shared import write_json
from . import local_h_pilot_scope as scope
from .scattering_anchor import Journal,save_arrays,relative
from .scattering_anchor_checks import checked_arrays
from . import independent_tetra_reference as core


def preflight(folder,journal):
    from . import fine_tetra_scope as prior
    from .tetra_local_marking import freeze_marking
    from src.geometry.tetra_mesh_audit import owned_tetra_cell_geometry,mesh_coordinate_tolerance,canonical_entity_key,audit_periodic_tetra_mesh
    from src.adaptivity.periodic_tetra_refinement import refine_periodic_marked_tetra_mesh
    from src.geometry.mesh_builder_3d import AirBox3DMesh
    a,b=prior.stage('A'),prior.stage('B')
    pair_path=prior.ARTIFACT/'A_B_gate.json';pair=json.loads(pair_path.read_text())
    if pair['parent_array_sha256']!=[a['arrays']['sha256'],b['arrays']['sha256']]:raise ValueError('frozen A/B marking parents')
    values=checked_arrays(pair['arrays']);v=checked_arrays(b['arrays'])
    d=values['per_cell_difference'];norm=checked_arrays(b['output']['integrals'][-1]['arrays'])['per_cell_analytic_squared'].sum(axis=0)[:2,0]
    target=np.array([pair['fields'][k]['difference_squared'] for k in ('E_scattered','H_scattered','curl_scattered')])
    operation=relative(d.sum(axis=0)-target,target)
    if operation>1e-10 or not np.array_equal(values['common_parent_first'],np.arange(len(d))):raise ValueError('saved A/B common-cell numerator identity')
    s=core.make_setup(a['spec'],a['physical'],journal)
    if not np.array_equal(s['geometry']['geometry_dofmap'],v['geometry_dofmap']) or not np.array_equal(s['geometry']['geometry_x'],v['geometry_x']):raise ValueError('marking actual parent geometry')
    tolerance=mesh_coordinate_tolerance(s['mesh']);records=owned_tetra_cell_geometry(s['mesh'],tolerance=tolerance)
    keys=[r.key for r in records];mark=freeze_marking(d,norm,keys)
    arrays=save_arrays(folder/'frozen_marking.npz',**{k:mark[k] for k in ('indices','eta_squared','order','reference_squared','denominator_squared')},
        geometry_x=v['geometry_x'],geometry_dofmap=v['geometry_dofmap'],parent_cell_tags=v['cell_tags'])
    marking={k:value for k,value in mark.items() if k not in ('indices','eta_squared','order')}
    marking.update(arrays=arrays,parent_arrays=[a['arrays'],b['arrays']],parent_pair=str(pair_path),numerator_reproduction=operation,
        region_counts={str(int(tag)):int(np.sum(v['cell_tags'][mark['indices']]==tag)) for tag in np.unique(v['cell_tags'])})
    write_json(folder/'frozen_marking.json',marking)
    template=AirBox3DMesh(mesh=s['mesh'],cell_tags=s['data'].cell_tags,facet_tags=s['data'].facet_tags,boundary_facets=np.asarray([],np.int32),
        mesh_cell_type_resolved='tetrahedron',mesh_cells_resolved=(8,8,20),z_alignment_warnings=[],mesh_spacing_mode_resolved='frozen_parent',
        mesh_axis_cell_stats={},material_plane_alignment={},local_refinement_regions={})
    attempts=[];local=dict(admitted=False,status='MESH_NOT_QUALIFIED')
    for sync in (False,True):
        with journal.measured('local_mesh_mate_only' if not sync else 'local_mesh_full_boundary_fallback'):
            try:
                data,report=refine_periodic_marked_tetra_mesh(template,s['cfg'],mark['indices'],full_boundary_synchronization=sync,return_parent_map=True)
                parent=np.asarray(report.pop('original_parent_cells'),np.int64)
                tags=v['cell_tags'][parent];regular=v['regular_tags'][parent]
                # The old wrapper retags regular geometry; independently bind
                # the true NOTCH inherited from the original parent labels.
                from dolfinx import mesh as dm
                data.cell_tags=dm.meshtags(data.mesh,3,np.arange(len(parent),dtype=np.int32),tags.astype(np.int32))
                audit=audit_periodic_tetra_mesh(data.mesh,data.cell_tags,data.facet_tags,s['cfg'])
                report['true_material_periodic_audit']=audit;report['pass']=bool(report['pass'] and audit['pass'])
                receipt=save_arrays(folder/('mesh_sync.npz' if sync else 'mesh_mate.npz'),geometry_x=data.mesh.geometry.x.copy(),geometry_dofmap=data.mesh.geometry.dofmap.copy(),
                    cell_tags=tags,regular_tags=regular,original_parent_cell=parent)
                attempts.append(dict(sync=sync,report=report,arrays=receipt));write_json(folder/'mesh_attempts.json',attempts)
                if not report['pass']:continue
                spec=dict(scope.plan_record()['cases']['L4'],cells=len(parent),independent=None,rows=None,mesh_override=receipt,notch_tetrahedra=int(np.sum((tags==s['cfg'].tags.air)&(regular==s['cfg'].tags.grating))))
                new=core.make_setup(spec,dict(a['physical']),journal)
                spec.update(cells=new['mesh'].topology.index_map(3).size_local,independent=new['P'].shape[1],rows=new['P'].shape[1]+828)
                new['spec']=spec;cap=core.assembly_capacity(new,journal)
                material_volume_check(s,new,parent)
                local=dict(status='MESH_QUALIFIED' if spec['cells']<=19200 and spec['rows']<=800000 and cap['admitted'] else 'L4_CAPACITY_NOT_ADMITTED',
                    admitted=bool(spec['cells']<=19200 and spec['rows']<=800000 and cap['admitted']),spec=spec,capacity=cap,attempts=attempts)
                path=folder/'local_mesh_spec.json';write_json(path,spec)
                write_json(scope.ARTIFACT/'local_mesh_spec.json',dict(path=str(path),sha256=__import__('hashlib').sha256(path.read_bytes()).hexdigest()))
                del new;gc.collect();break
            except (ValueError,RuntimeError) as exc:
                attempts.append(dict(sync=sync,error=repr(exc)));write_json(folder/'mesh_attempts.json',attempts)
    # P6 is independent of the local-refinement capacity result.
    p6=core.make_setup(scope.case_spec('P6'),scope.physical_for('P6'),journal)
    cap=core.assembly_capacity(p6,journal)
    local['attempts']=attempts
    return dict(status='COMPLETED',pass_gate=True,marking=marking,local_mesh=local,P6_capacity=cap,
        inherited_FLAT_and_boundary_qualification='V63 unchanged mathematical core',new_numeric_factors=0,new_complete_solves=0,
        source=journal.source_state,timings=journal.timings)


def material_volume_check(old,new,parent):
    def volume(s):
        x=s['geometry']['geometry_x'][s['geometry']['geometry_dofmap']]
        return np.abs(np.linalg.det(np.transpose(x[:,1:]-x[:,:1],(0,2,1))))/6
    before=volume(old);after=volume(new)
    indices=new['geometry'].get('original_parent_cell')
    if indices is None:raise ValueError('actual overridden parent map missing')
    delta=np.bincount(indices,weights=after,minlength=len(before))-before
    if np.max(np.abs(delta)/before)>1e-10:raise ValueError('composed parent map physical volume')
    for tag in np.unique(old['geometry']['cell_tags']):
        a=before[old['geometry']['cell_tags']==tag].sum();b=after[new['geometry']['cell_tags']==tag].sum()
        if abs(a-b)>1e-10*max(a,1e-24):raise ValueError('inherited physical material volume')


def execute(role,folder,state):
    budget=scope.memory_budget(role)
    if state.get('memory_budget')!=budget:raise ValueError('V64 live role memory propagation')
    journal=Journal(folder,window_scope=scope.window,planning_limit_bytes=budget['planning_gib']*2**30);journal.source_state=state
    if role=='PREFLIGHT':return preflight(folder,journal)
    if role in scope.SOLVES:
        from .independent_tetra_study import solve
        return solve(role,folder,journal,state,scope_module=scope)
    if role=='VERIFY_COST':
        from benchmarks.collect_local_h_pilot import verify
        return verify(folder,journal)
    raise ValueError('V64 explicit stage')
