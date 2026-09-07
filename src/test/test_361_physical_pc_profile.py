"""Pure-array profile contracts; no FE assembly, factorization or PDE."""

import hashlib
import json
from types import SimpleNamespace

import numpy as np
import pytest

from src.solvers.physical_pc_timing import PCTiming, _TimedMatrix
from src.runners.physical_intermediate import WorkflowLedger
from src.runners import physical_pc_profile as profile


def test_nested_timing_exception_and_borrowed_identity():
    clock = [0.0]
    timing = PCTiming(lambda: clock[0])
    borrowed = object()

    class Action:
        def apply(self, fail=False):
            clock[0] += 2
            if fail:
                raise ValueError('original error')
            return borrowed

    action = Action()
    timing.wrap(action, 'apply', 'action')
    with timing.scope('parent'):
        clock[0] += 1
        assert action.apply() is borrowed
        with pytest.raises(ValueError, match='original error'):
            action.apply(True)
    rows = timing.snapshot()
    assert rows['parent']['inclusive_seconds'] == 5
    assert rows['parent']['exclusive_seconds'] == 1
    assert rows['parent/action'] == dict(calls=2, failures=1, inclusive_seconds=4, exclusive_seconds=4)
    assert not timing.stack
    timing.close()
    assert 'apply' not in vars(action)
    assert action.apply() is borrowed


def test_matrix_proxy_and_method_restore_do_not_destroy_or_copy_results():
    events = []
    matrix = SimpleNamespace(mult=lambda x, y: y.__setitem__(slice(None), 2*x),
                             destroy=lambda: events.append('destroy'))
    timing = PCTiming()
    owner = SimpleNamespace(matrix=matrix)
    timing.replace(owner, 'matrix', _TimedMatrix(matrix, timing, 'B3'))
    out = np.zeros(3, complex)
    owner.matrix.mult(np.arange(3), out)
    np.testing.assert_array_equal(out, [0, 2, 4])
    assert timing.snapshot()['B3']['calls'] == 1
    timing.close()
    assert owner.matrix is matrix and events == []


class ArrayVec:
    live = 0

    def __init__(self, array):
        self.array = np.array(array, dtype=complex)
        self.destroyed = False
        ArrayVec.live += 1

    def copy(self):
        return ArrayVec(self.array)

    def duplicate(self):
        return ArrayVec(np.zeros_like(self.array))

    def norm(self):
        return np.linalg.norm(self.array)

    def axpy(self, factor, source):
        self.array += factor*source.array

    def scale(self, factor):
        self.array *= factor

    def getSize(self):
        return self.array.size

    getLocalSize = getSize

    def getOwnershipRange(self):
        return (0, self.getSize())

    def getArray(self, readonly=False):
        return self.array

    def destroy(self):
        assert not self.destroyed
        self.destroyed = True
        ArrayVec.live -= 1


@pytest.mark.parametrize('ending', ['complete', 'partial', 'mutated', 'repeat_bad'])
def test_seven_apply_artifacts_repeat_gates_and_partial_cleanup(tmp_path, monkeypatch, ending):
    from src.solvers import physical_pc_timing

    n = 173802
    rhs = ArrayVec(np.ones(n))
    rhs.array[0] = 0
    checkpoint = tmp_path/'solution.npy'
    np.save(checkpoint, rhs.array*.25)
    manifest = dict(explicit_true_residual=.5,
                    ranks=[dict(ownership=dict(ownership_range=[0, n]))])
    monkeypatch.setattr(profile, 'verified_checkpoint', lambda *args: (manifest, checkpoint))
    action = SimpleNamespace(apply=lambda source, target: target.array.__setitem__(slice(None), 2*source.array))
    calls = []
    class PC:
        def apply(self, source):
            raise AssertionError('uninstrumented fake PC')
    pc = PC()
    pc.last_apply_facts = dict(intermediate={}, direction_facts=[], wall_seconds=1)

    def instrument(bundle, timing, capture):
        def apply(source):
            calls.append(len(calls)+1)
            capture('S6', source)
            if ending == 'partial' and len(calls) == 3:
                raise InterruptedError('injected mid-PC signal')
            result = source.copy()
            if ending == 'mutated' and len(calls) == 2:
                source.array[2] += 1
            if ending == 'repeat_bad' and len(calls) == 3:
                result.array[2] += .1
            capture('S6', source)
            return result
        timing.replace(pc, 'apply', apply)

    monkeypatch.setattr(physical_pc_timing, 'instrument_reference_pc', instrument)
    bundle = dict(pc=pc, fine=dict(physical_action=action, mode_sha256=profile.MODE_SHA),
                  levels={'floquets': {6: SimpleNamespace(mpc=SimpleNamespace(slaves=[0]))}})
    ledger = WorkflowLedger(tmp_path, tmp_path/'phase.json')
    config = dict(checkpoint=str(tmp_path), deadline_monotonic=float('inf'))
    # JSON provenance must remain finite, including development fake deadlines.
    config['deadline_monotonic'] = 1e15
    try:
        if ending == 'complete':
            assert profile.run_pc_profile(bundle, rhs, {'provenance': {'physical_model_sha256': profile.PHYSICAL_SHA}},
                tmp_path, ledger, 'a'*40, config)['passed']
        else:
            with pytest.raises((InterruptedError, ValueError)):
                profile.run_pc_profile(bundle, rhs, {'provenance': {'physical_model_sha256': profile.PHYSICAL_SHA}},
                    tmp_path, ledger, 'a'*40, config)
        state = json.loads((tmp_path/'pc_profile/state.json').read_text())
        if ending == 'complete':
            assert len(calls) == state['completed'] == 7
            assert state['status'] == 'PROFILE_COMPLETED'
            records = [json.loads(line) for line in (tmp_path/'profile_applies.jsonl').read_text().splitlines()]
            assert sum(r['warmup'] for r in records) == 1
            assert sum('repeat_comparison' in r for r in records) == 3
            assert all(r['input_unchanged'] and r['output_finite'] and r['output_slave_zero'] for r in records)
            assert all(r['pc_compute_seconds'] <= r['pc_inclusive_seconds'] for r in records)
            assert all(r['pc_compute_seconds'] <= r['pc_wall_excluding_diagnostic_capture_seconds']
                       <= r['pc_inclusive_seconds'] for r in records)
            markers = [json.loads(line)['stage'] for line in (tmp_path/'stages.jsonl').read_text().splitlines()]
            assert markers.count('profile_pc_started') == markers.count('profile_pc_complete') == 7
            for capture in state['captures']:
                assert hashlib.sha256((tmp_path/'pc_profile'/capture['path']).read_bytes()).hexdigest() == capture['sha256']
        elif ending == 'partial':
            assert state['completed'] == 2 and state['active_apply']['index'] == 3
            assert state['last_safe']['index'] == 2
            assert state['timings']['PC']['failures'] == 1
            assert (tmp_path/'pc_profile/apply_03/S6_01.npy').exists()
        else:
            assert state['status'] == 'FAILED'
        assert 'apply' not in vars(pc)
        assert ArrayVec.live == 1
    finally:
        rhs.destroy()


def test_profile_budget_records_failed_attempt_and_forbids_rebuild(tmp_path, monkeypatch):
    from src.runners import physical_profile_budget as budget
    from src.runners import task038_launcher
    from src.io.input_loader import InputError
    from src.io.physical_intermediate_profile import REFERENCE_PROFILE

    monkeypatch.setattr(budget, 'verified_checkpoint', lambda *args: None)
    def failed(*args, **kwargs):
        assert kwargs['pc_profile']['complete_pc_limit'] == 7
        raise OSError('injected launch failure')
    monkeypatch.setattr(task038_launcher, 'launch_specification', failed)
    spec = SimpleNamespace(solver={'preconditioner': REFERENCE_PROFILE},
        physical_model_sha256=profile.PHYSICAL_SHA, input_sha256=profile.INPUT_SHA)
    path = tmp_path/'budget.json'
    with pytest.raises(OSError, match='injected'):
        budget.launch_profile(spec, tmp_path, path)
    record = json.loads(path.read_text())['attempts'][0]
    assert record['status'] == 'FAILED' and record['elapsed_seconds'] >= 0
    with pytest.raises(InputError, match='already reserved'):
        budget.launch_profile(spec, tmp_path, path)


def test_checkpoint_hash_rejects_mutation_before_vector_load(tmp_path):
    (tmp_path/'manifest.json').write_text('{}')
    np.save(tmp_path/'solution_rank0.npy', np.zeros(1, complex))
    with pytest.raises(ValueError, match='hash mismatch'):
        profile.verified_checkpoint(tmp_path, profile.PHYSICAL_SHA)


def test_instrumented_reference_composition_preserves_values_and_call_counts():
    from src.solvers.physical_pc_timing import instrument_reference_pc
    from src.solvers.fullspace_physical_intermediate import PhysicalIntermediatePreconditioner

    noop = lambda *args: None
    transfer = lambda: SimpleNamespace(apply_primal_into=lambda x, y: np.copyto(y, x),
        apply_adjoint_into=lambda x, y: np.copyto(y, x))
    class SlottedMPC:
        __slots__ = ()

        def homogenize(self, value):
            return None

        def backsubstitution(self, value):
            return None

    mpc = SlottedMPC()
    b6 = SimpleNamespace(_mpc=mpc, _pack_coefficients=lambda x: x,
                         _assemble_vector=lambda x: x.copy())
    def b6_apply(x):
        b6._mpc.homogenize(x)
        b6._mpc.backsubstitution(x)
        return b6._assemble_vector(b6._pack_coefficients(x))
    b6.apply = b6_apply
    matrix = SimpleNamespace(mult=lambda x, y: np.copyto(y, x))
    lower = SimpleNamespace(fine_matrix=matrix, coarse_matrix=matrix,
        smoother=SimpleNamespace(matrix=matrix), owner_transfer=transfer(),
        coarse_solver=SimpleNamespace(solve_lean=lambda x: (x.copy(), {})))
    def lower_apply(x, y):
        for _ in range(6):
            lower.fine_matrix.mult(x, y)
        lower.owner_transfer.apply_adjoint_into(x, y)
        lower.coarse_solver.solve_lean(x)
        lower.coarse_matrix.mult(x, y)
        lower.owner_transfer.apply_primal_into(x, y)
    lower.apply_into = lower_apply
    upper = SimpleNamespace(p63_transfer=transfer())
    def upper_apply(x, y):
        for _ in range(6):
            b6.apply(x)
        upper.p63_transfer.apply_adjoint_into(x, y)
        lower.apply_into(x, y)
        upper.p63_transfer.apply_primal_into(x, y)
    upper.apply_into = upper_apply
    volume = SimpleNamespace(apply=lambda x: np.array([2., 3., 5.])*x)
    dtn = SimpleNamespace(apply=lambda x, y: y.fill(0))
    fine = SimpleNamespace()
    def action(x, y):
        dtn.apply(x, y)
        y += volume.apply(x)
    fine.apply = action
    p64 = SimpleNamespace(apply_primal=lambda x: np.array(x), apply_adjoint=lambda x: np.array(x))
    reference = SimpleNamespace(factor=SimpleNamespace(solve_repeated=lambda x: x.copy()),
                                action=SimpleNamespace(apply=action), marker=noop, sample=noop)
    releases = []
    class OwnedArray(np.ndarray):
        def destroy(self):
            releases.append('reference_solution')
    def solve(x):
        y = reference.factor.solve_repeated(x).view(OwnedArray)
        work = np.empty_like(x)
        reference.action.apply(y, work)
        reference.marker('check', {})
        reference.sample()
        return dict(final_solution=y)
    reference.solve_intermediate = solve
    pc = PhysicalIntermediatePreconditioner(fine, upper, p64, reference, stage_callback=noop)
    bundle = dict(pc=pc, positive=dict(upper_cycle=upper, lower_cycle=lower,
        p6_shell=SimpleNamespace(action=b6)), reference_factor=reference,
        actions={'transfers': {(6, 4): p64}},
        fine=dict(physical_action=fine, volume_action=volume, dtn_action=dtn))
    source = np.array([1+1j, 2-1j, 3+.5j])
    expected = pc.apply(source)
    timing, captured = PCTiming(), []
    try:
        instrument_reference_pc(bundle, timing, lambda role, vector: captured.append((role, vector.copy())))
        actual = pc.apply(source)
        np.testing.assert_array_equal(actual, expected)
        counts = {}
        for path, row in timing.snapshot().items():
            label = path.split('/')[-1]
            counts[label] = counts.get(label, 0)+row['calls']
        for label, count in dict(S6=2, S3=2, B6=12, B3=12, P63=2, PH63=2,
                                  P31=2, PH31=2, P64=1, PH64=1, MR=3, A6=3,
                                  factor_backsolve=1, **{'MPC.homogenize': 12,
                                                        'MPC.backsubstitution': 12}).items():
            assert counts[label] == count
        assert [role for role, _ in captured].count('S6') == 2
    finally:
        timing.close()
    assert lower.fine_matrix is matrix
    assert b6._mpc is mpc
    np.testing.assert_array_equal(pc.apply(source), expected)
    assert releases == ['reference_solution']*3


def test_mpc_proxy_preserves_real_slotted_abi_and_complex_constraint():
    from mpi4py import MPI
    from dolfinx import fem, mesh
    import dolfinx_mpc
    from src.solvers.physical_pc_timing import _TimedMPC

    # Two interval cells exercise the actual MPC ABI; no form assembly or PDE.
    domain = mesh.create_unit_interval(MPI.COMM_SELF, 2)
    space = fem.functionspace(domain, ('Lagrange', 1))
    mpc = dolfinx_mpc.MultiPointConstraint(space)
    mpc.add_constraint(space, np.array([0], np.int32), np.array([1, 2], np.int64),
        np.array([.25+.5j, -.1+.2j], np.complex128), np.array([0, 0], np.int32),
        np.array([0, 2], np.int32))
    mpc.finalize()
    with pytest.raises(TypeError):
        vars(mpc)
    owner, shared = SimpleNamespace(_mpc=mpc), SimpleNamespace(_mpc=mpc)
    timing = PCTiming()
    original_methods = (type(mpc).homogenize, type(mpc).backsubstitution)
    direct, measured = fem.Function(mpc.function_space), fem.Function(mpc.function_space)
    original = np.array([1+2j, 3-.5j, -.25+1j])
    direct.x.array[:] = original
    measured.x.array[:] = original
    try:
        timing.replace(owner, '_mpc', _TimedMPC(mpc, timing))
        assert shared._mpc is mpc and owner._mpc.mpc is mpc
        assert owner._mpc.function_space is mpc.function_space
        mpc.homogenize(direct)
        owner._mpc.homogenize(measured)
        np.testing.assert_array_equal(measured.x.array, direct.x.array)
        mpc.backsubstitution(direct)
        owner._mpc.backsubstitution(measured)
        np.testing.assert_array_equal(measured.x.array, direct.x.array)
        assert timing.snapshot()['MPC.homogenize']['calls'] == 1
        assert timing.snapshot()['MPC.backsubstitution']['calls'] == 1
        assert (type(mpc).homogenize, type(mpc).backsubstitution) == original_methods
    finally:
        timing.close()
    assert owner._mpc is shared._mpc is mpc


def test_remaining_instrumentation_owner_classes_have_instance_dictionaries():
    from src.solvers.fullspace_mpc_action import FullspaceMpcFormAction
    from src.solvers.fullspace_same_mesh_hcurl_pmg_p6 import SameMeshP6NestedVcycle
    from src.solvers.fullspace_same_mesh_hcurl_pmg_global import SameMeshHcurlPmg
    from src.solvers.fullspace_lor_edge_geometric_mg_global import FixedChebyshevJacobiPETSc
    from src.solvers.fullspace_same_mesh_hcurl_pmg_runtime import SameMeshHcurlOwnerTransfer
    from src.solvers.fullspace_physical_intermediate_runtime import AlgebraicOwnerTransfer
    from src.solvers.fullspace_physical_intermediate import PhysicalIntermediatePreconditioner
    from src.solvers.fullspace_bounded_mumps import BoundedP1Factor
    from src.solvers.fullspace_p4_reference import PhysicalP4Reference
    from src.solvers.fullspace_v17_p3_oracle import _MumpsFactor
    from src.solvers.fullspace_physical_action import FullspacePhysicalAction, FullspaceSplitVolumeAction
    from src.solvers.fullspace_dtn_action import FullspaceDtnAction

    for cls in (FullspaceMpcFormAction, SameMeshP6NestedVcycle, SameMeshHcurlPmg,
                FixedChebyshevJacobiPETSc, SameMeshHcurlOwnerTransfer, AlgebraicOwnerTransfer,
                PhysicalIntermediatePreconditioner, BoundedP1Factor, PhysicalP4Reference,
                _MumpsFactor, FullspacePhysicalAction, FullspaceSplitVolumeAction,
                FullspaceDtnAction, WorkflowLedger):
        assert cls.__dictoffset__ != 0, cls.__name__


def test_profile_grace_is_bounded_and_resource_stop_immediate():
    import signal
    from benchmarks.subreaper_watchdog import stop_signal

    assert stop_signal('PERFORMANCE_CONTROLLED_STOP', hard_stop_immediate=True,
                       elapsed=2.1, grace_seconds=30) == signal.SIGTERM
    assert stop_signal('PERFORMANCE_CONTROLLED_STOP', hard_stop_immediate=True,
                       elapsed=30, grace_seconds=30) == signal.SIGKILL
    assert stop_signal('RESOURCE_CONTROLLED_STOP', hard_stop_immediate=True,
                       elapsed=0, grace_seconds=30) == signal.SIGKILL
    assert stop_signal('RESOURCE_CONTROLLED_STOP', hard_stop_immediate=False,
                       elapsed=0, grace_seconds=2) == signal.SIGTERM


@pytest.mark.parametrize('primary', [False, True])
def test_profile_cleanup_failure_persists_primary_and_secondary(tmp_path, primary):
    summary = dict(status='FAILED' if primary else 'PROFILE_COMPLETED')
    if primary:
        summary.update(exception_type='ValueError', exception_message='setup primary')
    events = []
    def broken():
        # Minimal evidence must already exist before the first destructor.
        assert (tmp_path/'physical_intermediate_summary.json').exists()
        raise RuntimeError('cleanup secondary')
    error = profile.cleanup_profile(summary, tmp_path,
                                    [('factor', broken), ('next', lambda: events.append('next'))])
    saved = json.loads((tmp_path/'physical_intermediate_summary.json').read_text())
    assert isinstance(error, RuntimeError) and events == ['next']
    assert saved['status'] == 'FAILED'
    assert saved['cleanup_errors'][0]['exception_message'] == 'cleanup secondary'
    if primary:
        assert saved['exception_message'] == 'setup primary'


@pytest.mark.parametrize('recovery_field', ['cache_recovery_from', 'recovery_from'])
def test_profile_manifest_is_hash_bound_before_worker_launch(tmp_path, monkeypatch, recovery_field):
    import time
    from pathlib import Path
    from src.io import load_and_resolve
    from src.runners import task038_launcher as launcher
    from src.runners.physical_profile_budget import RECOVERY_HASHES, RECOVERY_SOURCE
    from benchmarks import subreaper_watchdog

    root = Path(__file__).resolve().parents[2]
    spec = load_and_resolve(root/'input/task39extra/original_13p5nm_p6h10_p4_reference.dat')
    run = tmp_path/'run'
    run.mkdir()
    shared = tmp_path/'shared_cache'
    shared.mkdir()
    sentinel = shared/'unfinished.c'
    sentinel.write_bytes(b'untouched shared cache')
    monkeypatch.setenv('XDG_CACHE_HOME', str(shared))
    monkeypatch.setattr(launcher, '_timestamp_directory', lambda *args: run)
    monkeypatch.setattr(launcher, '_physical_source_gate', lambda *args: {'source_sha': 'a'*40})
    def supervise(*args, **kwargs):
        manifest = json.loads((run/'run_manifest.json').read_text())
        diagnostic = manifest['pc_profile']
        content = (run/diagnostic['config']).read_bytes()
        assert hashlib.sha256(content).hexdigest() == diagnostic['sha256']
        config = json.loads(content)
        assert config['schedule'] == [list(row) for row in profile.SCHEDULE]
        assert config['checkpoint_solution_sha256'] == profile.CHECKPOINT_SOLUTION_SHA
        assert config['batch_limit_seconds'] == 1800
        assert config[recovery_field]['raw_hashes'] == RECOVERY_HASHES
        assert json.loads(kwargs['worker_environment']['PHYSICAL_PC_PROFILE']) == config
        assert config['cache_empty_before_launch']
        cache = Path(config['cache_home'])
        assert cache == run/'jit_cache' and not list(cache.iterdir())
        assert kwargs['worker_environment']['XDG_CACHE_HOME'] == str(cache)
        assert kwargs['cache_path'] == cache
        assert kwargs['grace_seconds'] == 30 and kwargs['hard_stop_immediate']
        return dict(leader_exit_code=0, classification='COMPLETED', launch_envelope={},
                    memory_scope='test', job_swap_activity='zero_supported_by_zero_global_activity')
    monkeypatch.setattr(subreaper_watchdog, 'supervise', supervise)
    launcher.launch_specification(spec, source_sha='a'*40, pc_profile=dict(
        checkpoint=str(tmp_path), complete_pc_limit=7, variant='R0', batch_limit_seconds=1800,
        deadline_monotonic=time.monotonic()+1800, **{recovery_field: dict(
            source_sha=RECOVERY_SOURCE, raw_hashes=RECOVERY_HASHES)}))
    assert sentinel.read_bytes() == b'untouched shared cache'
    assert sorted(p.name for p in shared.iterdir()) == ['unfinished.c']


def _reviewed_failure(tmp_path, monkeypatch, kind='R0_profile'):
    from src.runners import physical_profile_budget as budget
    permission = budget.REVIEWED_FAILURES[kind]
    directory = tmp_path/'failed'
    (directory/'watchdog').mkdir(parents=True)
    records = {'run_manifest.json': {'source_sha': permission['source_sha']},
        'physical_intermediate_summary.json': dict(source_sha=permission['source_sha'], status='FAILED',
            exception_type=permission['exception_type'], failed_phase=permission['phase'], failed_stage=permission['stage']),
        'watchdog/summary.json': dict(classification='WORKER_FAILED', descendants_cleared=True)}
    if kind == 'R0_profile_cache_recovery_once':
        (directory/'pc_profile').mkdir()
        records['pc_profile/state.json'] = dict(completed=0, active_apply=None)
    hashes = {}
    for name, data in records.items():
        content = json.dumps(data).encode()
        (directory/name).write_bytes(content)
        hashes[name] = hashlib.sha256(content).hexdigest()
    monkeypatch.setitem(budget.REVIEWED_FAILURES, kind, dict(permission, hashes=hashes))
    old = dict(kind=kind, status='WORKER_FAILED', run_directory=str(directory),
               elapsed_seconds=105.19980926497374)
    return directory, old


@pytest.mark.parametrize('kind', ['R0_profile', 'R0_profile_cache_recovery_once'])
@pytest.mark.parametrize('mutation', ['hash', 'source', 'stage', 'pc', 'entry', 'again', 'state', 'missing_state_count'])
def test_recovery_rejects_wrong_evidence_or_second_reservation(tmp_path, monkeypatch, mutation, kind):
    from src.runners import physical_profile_budget as budget
    from src.io.input_loader import InputError
    directory, old = _reviewed_failure(tmp_path, monkeypatch, kind)
    permission = budget.REVIEWED_FAILURES[kind]
    attempts = [old]
    if mutation in ('hash', 'source', 'stage'):
        path = directory/'physical_intermediate_summary.json'
        record = json.loads(path.read_text())
        record['source_sha' if mutation == 'source' else 'failed_stage'] = 'incorrect'
        path.write_text(json.dumps(record))
        if mutation != 'hash':
            permission['hashes'][path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    elif mutation == 'pc':
        (directory/'pc_applies.jsonl').write_text('{}\n')
    elif mutation == 'entry':
        old['status'] = 'COMPLETED'
    elif mutation in ('state', 'missing_state_count'):
        path = directory/'pc_profile/state.json'
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(dict(completed=1, active_apply=None) if mutation == 'state'
                                   else dict(active_apply=None)))
        if kind == 'R0_profile_cache_recovery_once':
            permission['hashes']['pc_profile/state.json'] = hashlib.sha256(path.read_bytes()).hexdigest()
    else:
        attempts.append(dict(kind=permission['reservation_kind']))
    with pytest.raises(InputError):
        budget.verify_profile_recovery(directory, attempts)


@pytest.mark.parametrize('kind', ['R0_profile', 'R0_profile_cache_recovery_once'])
def test_recovery_appends_once_and_preserves_old_cost(tmp_path, monkeypatch, kind):
    from src.runners import physical_profile_budget as budget, task038_launcher
    from src.io.input_loader import InputError
    from src.io.physical_intermediate_profile import REFERENCE_PROFILE
    directory, old = _reviewed_failure(tmp_path, monkeypatch, kind)
    permission = budget.REVIEWED_FAILURES[kind]
    # Timing is accounting data, not a recovery qualification password.
    old['elapsed_seconds'] = 105.2
    path = tmp_path/'budget.json'
    earlier = dict(kind='R0_profile', status='WORKER_FAILED', elapsed_seconds=105.19980926497374,
                   run_directory=str(tmp_path/'earlier'))
    original = [earlier, old] if kind != 'R0_profile' else [old]
    path.write_text(json.dumps(dict(limit_seconds=36000, attempts=original)))
    monkeypatch.setattr(budget, 'verified_checkpoint', lambda *args: None)
    def launch(*args, **kwargs):
        recovery = kwargs['pc_profile'][permission['recovery_field']]
        assert recovery['raw_hashes'] == permission['hashes']
        assert recovery['completed_pc'] == 0
        assert kwargs['pc_profile']['complete_pc_limit'] == 7
        return dict(result_classification='worker_exit0', run_directory=str(tmp_path/'new'))
    monkeypatch.setattr(task038_launcher, 'launch_specification', launch)
    spec = SimpleNamespace(solver={'preconditioner': REFERENCE_PROFILE},
        physical_model_sha256=profile.PHYSICAL_SHA, input_sha256=profile.INPUT_SHA)
    budget.launch_profile(spec, tmp_path, path, recovery_from=directory)
    attempts = json.loads(path.read_text())['attempts']
    assert attempts[:-1] == original
    assert attempts[-1]['kind'] == permission['reservation_kind']
    assert attempts[-1]['elapsed_seconds'] >= 0
    with pytest.raises(InputError, match='already reserved'):
        budget.launch_profile(spec, tmp_path, path, recovery_from=directory)
    with pytest.raises(InputError, match='already reserved'):
        budget.launch_profile(spec, tmp_path, path)


def test_single_recovery_cli_keeps_old_flag_as_alias():
    from scripts.run_case import _parser

    for option in ('--profile-recovery-from', '--profile-cache-recovery-from'):
        args = _parser().parse_args(['input.dat', '--physical-pc-profile', 'checkpoint', option, 'failed'])
        assert str(args.profile_recovery_from) == 'failed'


def test_cache_environment_applies_before_real_abi_import_without_fe(tmp_path):
    import os
    import subprocess
    import sys

    cache = tmp_path/'isolated'
    cache.mkdir()
    environment = dict(os.environ, XDG_CACHE_HOME=str(cache))
    code = '''
import os,json
from pathlib import Path
import numpy as np
from petsc4py import PETSc
import slepc4py, mpi4py
from dolfinx import jit
assert PETSc.ScalarType is np.complex128
assert Path(jit.get_options()['cache_dir']) == Path(os.environ['XDG_CACHE_HOME'])/'fenics'
print(json.dumps({'cache_dir':str(jit.get_options()['cache_dir']), 'scalar':'complex128'}))
'''
    result = subprocess.run([sys.executable, '-c', code], env=environment, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['cache_dir'] == str(cache/'fenics')
    assert not list(cache.rglob('*.c')) and not list(cache.rglob('*.so'))
