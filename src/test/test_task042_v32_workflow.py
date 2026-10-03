"""V32 wiring and storage boundaries; all numeric payloads are synthetic."""
import hashlib
import json
import shutil
from types import SimpleNamespace
import pytest
from src.test.task042_v31_workflow_fixture import workflow
from src.solvers.bounded_diagnostic_window import DiagnosticWindow
from src.solvers.return_block_window import CAPS
from benchmarks.task042_return_certificates import EXPECTED


def test_storage_scope_and_boundary(tmp_path):
    from src.runners.diagnostic_storage import inventory, inventory_paths, enforce, CUMULATIVE_LIMIT
    names=('tmp/task042/v27/raw.log', 'tmp/task042/v32/test.log',
           'tmp/task042/review_v24/raw.log', 'tmp/task042/review_v29/raw.log',
           'benchmarks/artifacts/task042/v28/evidence.json',
           'results/task042/task042_v32_diagnostic/run.log',
           'docs/task042_neural_coarse_inverse/outcomes/records/costs_v32.json',
           'docs/task042_neural_coarse_inverse/outcomes/records/review_v29_checks.json')
    for name in names:
        p=tmp_path/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'12345')
    result=inventory(tmp_path,include_files=True)
    assert result['cumulative']['bytes']==40 and result['cumulative']['file_count']==8
    assert result['new']['bytes']==15 and result['new']['file_count']==3
    alias=tmp_path/'alias';alias.symlink_to(tmp_path/'tmp/task042/v32',target_is_directory=True)
    assert inventory_paths((tmp_path/'tmp',tmp_path/'tmp/task042/v32',alias),tmp_path)['bytes']==20
    # Sparse synthetic file: stat only, never read or allocate the large payload.
    big=tmp_path/'tmp/task042/review_v29/limit.bin'
    with big.open('wb') as f:f.truncate(CUMULATIVE_LIMIT-40)
    assert enforce(tmp_path)['cumulative']['bytes']==CUMULATIVE_LIMIT
    with pytest.raises(MemoryError,match='cumulative'):
        enforce(tmp_path,reserve_bytes=1)
    shutil.rmtree(tmp_path)


def test_v32_actual_workflow_through_independent_checker(tmp_path,monkeypatch):
    result,checked,book=workflow(tmp_path,monkeypatch,batch='v32')
    assert result['budget_counts']==EXPECTED and result['action_counts']==dict(S=34,SH=2,audit=0)
    assert checked['status']=='CHECKED' and len(checked['rows'])==2
    assert all(row['cancellation']['operation_relative']<=1e-10 for row in result['rows'])
    assert book['active'] is None and len(book['runs'])==1
    assert (tmp_path/'records/return_direction_checker_v32.json').is_file()
    assert not (tmp_path/'records/return_direction_checker_v31.json').exists()
    shutil.rmtree(tmp_path)


def test_attempt_accounting_is_deduplicated_and_not_reset(tmp_path):
    w=DiagnosticWindow(tmp_path,CAPS,'V32',carried_auxiliary_seconds=52.68017605994828)
    for name,value in [('aux_pre_001',2.5),('aux_pre_002',3.5),('aux_check_001',1.)]:
        p=tmp_path/name/'summary.json';p.parent.mkdir();p.write_text(json.dumps(dict(elapsed_seconds=value)))
    assert w.auxiliary_wall()==pytest.approx(59.68017605994828)
    assert json.loads((tmp_path/'aux_pre_001/summary.json').read_text())['elapsed_seconds']==2.5


@pytest.mark.parametrize('closed,active,runs',[(True,None,[]),(False,{'directory':'x'},[]),(False,None,[{}])])
def test_v32_namespace_and_closed_rejection(tmp_path,monkeypatch,closed,active,runs):
    from src.io import return_block_v32 as io,return_block_v31 as old
    from src.io.input_loader import InputError
    monkeypatch.setattr(io,'window',SimpleNamespace(TMP=tmp_path,require_qualification=lambda: {},
        require_live=lambda **kw:dict(heavy_remaining_seconds=4000),
        ledger=lambda:dict(closed=closed,active=active,runs=runs,actor_wall_seconds=0.),
        auxiliary_wall=lambda:52.68017605994828))
    dat='input/task042_neural_coarse_inverse/v32_return_direction_diagnostic.dat'
    assert old.load_return_diagnostic(dat) is None
    assert io.load_return_diagnostic('input/task042_neural_coarse_inverse/v31_return_direction_diagnostic.dat') is None
    with pytest.raises(InputError,match='closed/active/already consumed'):io.load_return_diagnostic(dat)


def test_actor_budget_reserves_checker_and_cleanup(monkeypatch):
    from src.solvers import return_block_v32_window as w
    monkeypatch.setattr(w,'auxiliary_wall',lambda:52.68017605994828+65)
    assert w.actor_timeout(dict(heavy_remaining_seconds=1000),dict(actor_wall_seconds=0))==pytest.approx(452.3198239400517)
    assert w.actor_timeout(dict(heavy_remaining_seconds=100),dict(actor_wall_seconds=0))==100


def test_current_code_qualification_not_arbitrary_old_pass(tmp_path,monkeypatch):
    from src.solvers import return_block_v32_window as w
    monkeypatch.setattr(w,'TMP',tmp_path)
    monkeypatch.setattr(w,'implementation_hashes',lambda:dict(current='b'*64))
    folder=tmp_path/'aux_pre_002';tests=folder/'tests';tests.mkdir(parents=True)
    entry=tests/'entry_result.json';entry.write_text('{"status":"PASSED"}')
    proof=dict(status='PASSED',source_sha='a'*40,coverage=list(w.REQUIRED_COVERAGE),
               implementation_hashes={'current':'b'*64},test_receipt=dict(path=str(entry),sha256=hashlib.sha256(entry.read_bytes()).hexdigest()))
    path=tests/'qualification.json'
    def save():
        path.write_text(json.dumps(proof))
        (tmp_path/'pre_qualification.json').write_text(json.dumps(dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())))
    (folder/'summary.json').write_text(json.dumps(dict(classification='COMPLETED',leader_exit_code=0,source_state=dict(source_sha='a'*40))))
    save();assert w.require_qualification()['source_sha']=='a'*40
    proof['implementation_hashes']['current']='c'*64;save()
    with pytest.raises(ValueError,match='current implementation'):w.require_qualification()
    proof['implementation_hashes']['current']='b'*64;proof['coverage']=[];save()
    with pytest.raises(ValueError,match='current implementation'):w.require_qualification()


def test_v32_registered_timeout_and_single_admission(tmp_path,monkeypatch):
    from src.io import return_block_v32 as io
    from src.io.input_loader import InputError
    from src.io.task042_profile import TASK042_PROFILES
    w=SimpleNamespace(TMP=tmp_path,require_qualification=lambda: {},
        require_live=lambda **kw:dict(heavy_remaining_seconds=4000),
        ledger=lambda:dict(closed=False,active=None,runs=[],actor_wall_seconds=0.),
        auxiliary_wall=lambda:52.68017605994828,actor_timeout=lambda *a:480.)
    monkeypatch.setattr(io,'window',w)
    dat='input/task042_neural_coarse_inverse/v32_return_direction_diagnostic.dat'
    spec=io.load_return_diagnostic(dat)
    assert spec.derived['stage']==TASK042_PROFILES['task042_v32_diagnostic']=='V32-DIAGNOSTIC'
    assert spec.execution['timeout_seconds']==480.
    (tmp_path/'formal_admission_attempt.json').write_text('{}')
    with pytest.raises(InputError,match='formal admission already consumed'):io.load_return_diagnostic(dat)
