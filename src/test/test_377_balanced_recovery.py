"""Output-only terminal recovery gates, with a tiny PETSc checkpoint fixture."""
import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

from src.io import load_and_resolve
from src.io.input_validation import simulation_config_3d_from_normalized
from src.io.physical_balanced_profile import BALANCED_PROFILES
from src.runners.physical_balanced_recovery import (
    ORIGINAL_SOURCE, validate_output_only, fresh_root, restore_field)


@pytest.mark.parametrize('prefix,profile',
    [(prefix,profile) for prefix in ('original','nonseparable') for profile in BALANCED_PROFILES]
    + [('nonseparable','fine_reference')])
def test_only_external_probes_change(prefix,profile,tmp_path):
    path=Path('input/task39extra')/f'{prefix}_13p5nm_p6h10_{profile}.dat'
    new=load_and_resolve(path).as_jsonable()
    prior=tmp_path/'prior.dat'
    prior.write_text(path.read_text().replace('top_probe_z_nm = 127.5','top_probe_z_nm = 110.0')
                     .replace('bottom_probe_z_nm = -7.5','bottom_probe_z_nm = 10.0'))
    old=load_and_resolve(prior).as_jsonable()
    validate_output_only(old,new)
    assert old['provenance']['physical_model_sha256']==new['provenance']['physical_model_sha256']
    assert old['provenance']['input_sha256']!=new['provenance']['input_sha256']
    assert new['output']['reference_plane_z_nm']==[10.,30.,60.,90.,110.]
    from src.postprocessing.diffraction_3d import _probe_z_locations
    cfg=simulation_config_3d_from_normalized(new)
    assert _probe_z_locations(cfg)==(127.5,-7.5)
    cfg.diffraction_top_probe_z=110.
    with pytest.raises(ValueError,match='above the block'):_probe_z_locations(cfg)
    cfg.diffraction_top_probe_z=127.5;cfg.diffraction_bottom_probe_z=10.
    with pytest.raises(ValueError,match='substrate'):_probe_z_locations(cfg)
    changed=copy.deepcopy(new);changed['solver']['max_it']=999
    with pytest.raises(ValueError,match='non-output'):validate_output_only(old,changed)


def test_recovery_root_cannot_overwrite_old_or_existing(tmp_path):
    original=tmp_path/'old';original.mkdir();raw=original/'raw';raw.write_bytes(b'unchanged')
    with pytest.raises(ValueError):fresh_root(original/'recovery',original)
    with pytest.raises(ValueError):fresh_root(original,original)
    new=tmp_path/'new';fresh_root(new,original)
    with pytest.raises(FileExistsError):fresh_root(new,original)
    assert raw.read_bytes()==b'unchanged'


def test_terminal_restore_rejects_changed_action_and_shard(tmp_path,monkeypatch):
    from src.solvers.fullspace_memory_first_krylov import write_solution_checkpoint
    rhs=PETSc.Vec().createSeq(3);rhs.array[:]=[1+2j,3-1j,2]
    physical='a'*64;mode='b'*64;quadrature=({'quadrature_degree':4},)*2
    operator=hashlib.sha256(json.dumps(dict(source_sha=ORIGINAL_SOURCE,physical=physical,
        modes=mode,quadrature=quadrature),sort_keys=True).encode()).hexdigest()
    cp=tmp_path/'checkpoints/iteration_000564'
    cp.parent.mkdir()
    facts=write_solution_checkpoint(cp,rhs,iteration=564,explicit_true_residual=0.,
        input_identity_sha256='c'*64,operator_identity_sha256=operator,
        physical_model_sha256=physical,source_sha=ORIGINAL_SOURCE,
        ownership=dict(rank=0,ownership_range=[0,3],local_size=3,global_size=3),comm=MPI.COMM_WORLD)
    np.savez(tmp_path/'raw.npz',rhs=rhs.array,action=rhs.array,solution=rhs.array)
    summary=dict(mode_sha256=mode,last_safe_checkpoint=dict(checkpoint=facts),
        final_solution_sha256=hashlib.sha256(rhs.array.tobytes()).hexdigest(),
        residual_arrays=dict(input_sha256='c'*64,operator_identity_sha256=operator,
            physical_model_sha256=physical,filename='raw.npz'))
    fine=dict(mode_sha256=mode,physical_action=None)
    scale=[1.]
    def action(_,source):
        out=source.copy();out.scale(scale[0]);return out
    monkeypatch.setattr('src.solvers.fullspace_physical_intermediate.apply_owned',action)
    try:
        solution,ax,identity=restore_field(fine,rhs,tmp_path,summary,quadrature,MPI.COMM_WORLD)
        assert identity['full_explicit_true_residual']==0.
        solution.destroy();ax.destroy()
        scale[0]=2.
        with pytest.raises(ValueError,match='A/b/true'):restore_field(fine,rhs,tmp_path,summary,quadrature,MPI.COMM_WORLD)
        scale[0]=1.
        with (cp/'solution_rank0.npy').open('ab') as f:f.write(b'tamper')
        with pytest.raises(ValueError,match='byte count'):restore_field(fine,rhs,tmp_path,summary,quadrature,MPI.COMM_WORLD)
    finally:rhs.destroy()


def test_worker_enters_fine_only_without_factor_pc_or_ksp(monkeypatch,tmp_path):
    import src.runners.physical_balanced_recovery as module
    import src.solvers.fullspace_same_mesh_hcurl_pmg_global as levels_module
    import src.solvers.fullspace_physical_intermediate_runtime as runtime
    import src.solvers.physical_balanced_runtime as pc
    import src.solvers.physical_balanced_fgmres as krylov
    calls=[]
    def forbidden(*a,**k):pytest.fail('recovery entered factor/PC/KSP path')
    monkeypatch.setattr(runtime,'build_physical_intermediate_solver',forbidden)
    monkeypatch.setattr(pc,'install_balanced_pc',forbidden)
    monkeypatch.setattr(krylov,'run_balanced_fgmres',forbidden)
    def fine(cfg,comm,degrees,**kwargs):
        calls.append(('levels',degrees,kwargs));return dict(floquets={6:None})
    monkeypatch.setattr(levels_module,'_build_same_mesh_levels',fine)
    monkeypatch.setattr(module,'validate_origin',lambda *a:(dict(residual_arrays={}),{}))
    import src.solvers.fullspace_same_mesh_hcurl_pmg_physical as physical
    quadrature=({'quadrature_degree':18},{'quadrature_degree':18})
    monkeypatch.setattr(runtime,'fine_volume_quadrature_metadata',lambda *a:(quadrature,[]))
    def build(levels,cfg,degree,**kwargs):
        calls.append(('fine',degree,kwargs));return {}
    monkeypatch.setattr(physical,'build_same_mesh_physical_action',build)
    def rhs(fine):
        calls.append(('rhs',));return PETSc.Vec().createSeq(1),{}
    monkeypatch.setattr(physical,'build_physical_rhs',rhs)
    monkeypatch.setattr(module,'restore_field',lambda fine,b,*a:(b.duplicate(),b.duplicate(),{}))
    monkeypatch.setattr(physical,'destroy_same_mesh_physical_action',lambda fine:None)
    monkeypatch.setattr(physical,'recover_p0_outputs',lambda *a,**k:{})
    monkeypatch.setattr('src.runners.physical_balanced_output.compare_balanced_output',lambda *a,**k:{})
    monkeypatch.setattr('benchmarks.physical_intermediate_checker.check',lambda *a:
        dict(classification='BALANCED_OUTPUT_PASS',independent_output_gates_passed=True))
    original=tmp_path/'old';original.mkdir()
    for name in ('pc_applies.jsonl','p4_decisions.jsonl','monitor_residuals.jsonl'):
        (original/name).write_text('historical evidence')
    monkeypatch.setenv('PHYSICAL_TIMEBASE_GUARD','1')
    monkeypatch.setenv('PHYSICAL_TIMEBASE_POLICY','conservative_realtime')
    monkeypatch.setenv('PHYSICAL_WATCHDOG_PHASE_PATH',str(tmp_path/'phase.json'))
    monkeypatch.setenv('PHYSICAL_WATCHDOG_PARENT_PID','1')
    monkeypatch.setenv('PHYSICAL_WATCHDOG_LAUNCH_CAP_BYTES',str(12_000_000_000))
    args=SimpleNamespace(input=Path('input/task39extra/original_13p5nm_p6h10_balanced_h6_p4_v5.dat'),
        original=tmp_path/'old',audit=tmp_path/'audit',audit_sha='a'*64,
        expected_sha='b'*40,directory=tmp_path,prior_seconds=6878.146713953)
    module.run_worker(args)
    assert calls==[('levels',(6,),{'include_positive_coefficients':False}),
                   ('fine',6,{'volume_quadrature_metadata':quadrature}),('rhs',)]
    summary=json.loads((tmp_path/'physical_intermediate_summary.json').read_text())
    assert summary['status']=='BALANCED_OUTPUT_PASS'
    assert summary['elapsed_conservative_seconds']>=args.prior_seconds
    assert all(summary['recovery'][k]==0 for k in ('new_factor_count','new_pc_count','new_ksp_count'))


def test_composite_notch_dependency_preserves_original_failure(tmp_path,monkeypatch):
    from src.runners.physical_balanced_budget import launch_notch_after_recovery
    import src.runners.physical_balanced_budget as budget_module
    path=tmp_path/'budget.json';root=tmp_path/'recovery';root.mkdir()
    (root/'physical_intermediate_summary.json').write_text(json.dumps(dict(status='BALANCED_OUTPUT_PASS',
        checker=dict(classification='BALANCED_OUTPUT_PASS',independent_output_gates_passed=True))))
    original=dict(kind='original',profile=BALANCED_PROFILES[0],run_directory=str(tmp_path/'old'),
                  status='WORKER_FAILED',qualified=False,elapsed_seconds=6878.146713953)
    recovery=dict(kind='original_recovery',status='COMPLETED',qualified=True,
        run_directory=str(root),original_directory=original['run_directory'],original_plus_recovery_seconds=7000,
        supervision=dict(descendants_cleared=True,remaining_child_pids=[]))
    budget=dict(attempts=[original,recovery]);before=copy.deepcopy(original);calls=[]
    def once(b,p,spec,kind):
        calls.append((spec.solver['preconditioner'],kind))
        entry=dict(kind=kind,independent_output_gates_passed=False);b['attempts'].append(entry)
        return dict(result_classification='worker_exit_nonzero'),entry
    monkeypatch.setattr(budget_module,'_once',once)
    launch_notch_after_recovery(budget,path,recovery)
    assert original==before and calls==[(BALANCED_PROFILES[0],'notch')]
    with pytest.raises(ValueError):launch_notch_after_recovery(budget,path,recovery)


@pytest.mark.parametrize('changed',['solution','rhs_and_action'])
def test_checker_rejects_rehashed_recovery_arrays(tmp_path,changed):
    from benchmarks.physical_intermediate_checker import check
    old_root=tmp_path/'old';old_root.mkdir()
    root=tmp_path/'recovery';root.mkdir()
    vector=np.array([1+2j,3-1j],dtype=np.complex128)
    np.savez(old_root/'raw.npz',rhs=vector,action=vector,solution=vector)
    def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
    summary=dict(status='RESIDUAL_PASS',source_sha=ORIGINAL_SOURCE,
        profile=dict(identity=BALANCED_PROFILES[0],reference_only=False),
        solve=dict(final_true_residual=0.,reason=2),solve_monotonic_seconds=1.,
        elapsed_monotonic_seconds=2.,auxiliary_stack_released_before_recovery=True,
        official_result=None,final_solution_sha256=hashlib.sha256(vector.tobytes()).hexdigest(),
        residual_arrays=dict(filename='raw.npz',sha256=sha(old_root/'raw.npz')))
    (old_root/'physical_intermediate_summary.json').write_text(json.dumps(summary))
    hashes={name:sha(old_root/name) for name in ('raw.npz','physical_intermediate_summary.json')}
    for name in ('pc_applies.jsonl','p4_decisions.jsonl','monitor_residuals.jsonl'):
        (old_root/name).write_text('');(root/name).write_text('');hashes[name]=sha(old_root/name)
    audit=tmp_path/'audit.json';audit.write_text(json.dumps(dict(run_directory=str(old_root),artifact_sha256=hashes)))
    summary['recovery']=dict(original_directory=str(old_root),original_audit_path=str(audit),
        original_audit_sha256=sha(audit),original_source_sha=ORIGINAL_SOURCE,
        new_factor_count=0,new_pc_count=0,new_ksp_count=0)
    np.savez(root/'raw.npz',rhs=vector,action=vector,solution=vector)
    summary['residual_arrays']['sha256']=sha(root/'raw.npz')
    (root/'physical_intermediate_summary.json').write_text(json.dumps(summary))
    assert check(root)['gate_failures']==['official outputs unavailable']
    np.savez(root/'raw.npz',rhs=vector*(2 if changed=='rhs_and_action' else 1),
        action=vector*(2 if changed=='rhs_and_action' else 1),
        solution=vector*(2 if changed=='solution' else 1))
    summary['residual_arrays']['sha256']=sha(root/'raw.npz')
    (root/'physical_intermediate_summary.json').write_text(json.dumps(summary))
    errors=check(root)['gate_failures']
    if changed=='solution':
        assert 'recovery actual solution bytes hash mismatch' in errors
    else:
        assert 'recovery original rhs relative difference exceeds 1e-10' in errors
        assert 'recovery original action relative difference exceeds 1e-10' in errors


@pytest.mark.parametrize('qualified',[False,True])
def test_next_original_requires_exact_qualified_recovery_after_notch_failure(tmp_path,monkeypatch,qualified):
    import src.runners.physical_balanced_budget as module
    oldroot=tmp_path/'old';oldroot.mkdir();newroot=tmp_path/'recovery';newroot.mkdir()
    solve=dict(status='TRUE_RESIDUAL_PASS',iterations=564,final_true_residual=9.93e-7)
    old=dict(source_sha=ORIGINAL_SOURCE,failed_phase='recovery',exception_type='ValueError',
        exception_message='Top diffraction probe z=110 nm must be above the block top z=120 nm.',solve=solve)
    (oldroot/'physical_intermediate_summary.json').write_text(json.dumps(old))
    worker=dict(status='BALANCED_OUTPUT_PASS',source_sha=ORIGINAL_SOURCE,solve=solve,
        recovery=dict(original_source_sha=ORIGINAL_SOURCE,original_directory=str(oldroot)),
        checker=dict(classification='BALANCED_OUTPUT_PASS',independent_output_gates_passed=True))
    (newroot/'physical_intermediate_summary.json').write_text(json.dumps(worker))
    original=dict(kind='original',profile=BALANCED_PROFILES[0],run_directory=str(oldroot),
        worker_status='FAILED',parent_classification='WORKER_FAILED',elapsed_seconds=6878.146713953)
    recovery=dict(kind='original_recovery',status='COMPLETED',qualified=qualified,
        run_directory=str(newroot),original_directory=str(oldroot),original_plus_recovery_seconds=7000,
        supervision=dict(descendants_cleared=True,remaining_child_pids=[]),elapsed_seconds=100)
    notch=dict(kind='notch',worker_status='PERFORMANCE_CONTROLLED_STOP',
        parent_classification='PERFORMANCE_CONTROLLED_STOP',qualified=False,elapsed_seconds=8000)
    budget=dict(schema=module.SCHEMA,limit_seconds=43200,attempts=[original,recovery,notch])
    path=tmp_path/'budget.json';path.write_text(json.dumps(budget));before=copy.deepcopy(original);calls=[]
    def once(b,p,spec,kind):
        calls.append((kind,spec.solver['preconditioner']))
        assert b['attempts'][0]==before
        return {},dict(qualified=False)
    monkeypatch.setattr(module,'_once',once)
    spec=load_and_resolve('input/task39extra/original_13p5nm_p6h10_balanced_s6_p4_v5.dat')
    if qualified:
        module.launch_balanced_workflow(spec,path)
        assert calls==[('original',BALANCED_PROFILES[1])]
        recovery['supervision']['descendants_cleared']=False
        assert not module.qualified_original_recovery(budget,original)
    else:
        with pytest.raises(ValueError,match='engineering blocker'):module.launch_balanced_workflow(spec,path)
        assert calls==[]
    assert original==before
