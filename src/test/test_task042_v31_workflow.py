"""V31 actual workflow, accounting and namespace gates; no real payload reads."""
import json,shutil
from types import SimpleNamespace
import pytest
from src.solvers.bounded_diagnostic_window import DiagnosticWindow
from src.solvers.return_block_window import CAPS
from src.test.task042_v31_workflow_fixture import workflow
from benchmarks.task042_return_certificates import EXPECTED


def test_actual_study_two_states_through_collector(tmp_path,monkeypatch):
    result,checked,book=workflow(tmp_path,monkeypatch)
    assert result['budget_counts']==EXPECTED
    assert result['action_counts']==dict(S=34,SH=2,audit=0)
    assert checked['status']=='CHECKED' and len(checked['rows'])==2
    assert all(x['cancellation']['operation_relative']<=1e-10 for x in result['rows'])
    assert len(result['factor_reloads'])==7 and book['active'] is None
    assert (tmp_path/'records/return_direction_checker_v31.json').exists()
    assert not (tmp_path/'records/return_direction_checker_v28.json').exists()
    # Dispose only successful synthetic payloads; failed fixtures remain intact.
    shutil.rmtree(tmp_path)


def test_fixed_summary_charged_exactly_once(tmp_path):
    p=tmp_path/'aux_pre/auxiliary_summary.json';p.parent.mkdir();p.write_text('{"elapsed_seconds":3.25}')
    w=DiagnosticWindow(tmp_path,CAPS,'V31',carried_auxiliary_seconds=39.94901336694602,fixed_auxiliary_summaries=(p,p))
    assert w.auxiliary_wall()==pytest.approx(43.19901336694602)
    q=tmp_path/'aux_check/summary.json';q.parent.mkdir();q.write_text('{"elapsed_seconds":2}')
    assert w.auxiliary_wall()==pytest.approx(45.19901336694602)


def test_actual_workflow_reader_failure_preserves_partial_accounting(tmp_path,monkeypatch):
    result,checked,book=workflow(tmp_path,monkeypatch,reject_state=True)
    assert result['status']=='FAILED' and result['error']=='synthetic state reader rejection'
    assert checked['status']=='PARTIAL_UNRESOLVED'
    assert result['budget_counts']['actions']==4 and result['budget_counts']['factor_readers']==1
    assert result['budget_counts']['joint_lu_solve']==2 and book['active'] is None
    assert book['runs'][0]['exact_counts'] is False and book['charged']['actions']==4


@pytest.mark.parametrize('closed,active,runs',[(True,None,[]),(False,{'directory':'x'},[]),(False,None,[{}])])
def test_v31_rejects_old_or_consumed_boundaries(tmp_path,monkeypatch,closed,active,runs):
    from src.io import return_block_v31 as io
    from src.io.input_loader import InputError
    (tmp_path/'aux_pre').mkdir();(tmp_path/'aux_pre/auxiliary_summary.json').write_text('{"classification":"COMPLETED","leader_exit_code":0}')
    monkeypatch.setattr(io,'window',SimpleNamespace(TMP=tmp_path,require_live=lambda **k:dict(heavy_remaining_seconds=4000),
        ledger=lambda:dict(closed=closed,active=active,runs=runs,actor_wall_seconds=0.),auxiliary_wall=lambda:39.94901336694602))
    with pytest.raises(InputError,match='closed/active/already consumed'):
        io.load_return_diagnostic('input/task042_neural_coarse_inverse/v31_return_direction_diagnostic.dat')


def test_v31_schema_and_old_routes_are_separate(tmp_path,monkeypatch):
    from src.io import return_block_v31 as io,return_block_diagnostic as v27,return_block_continuation as v28
    from src.io.task042_profile import TASK042_PROFILES
    (tmp_path/'aux_pre').mkdir();(tmp_path/'aux_pre/auxiliary_summary.json').write_text('{"classification":"COMPLETED","leader_exit_code":0}')
    monkeypatch.setattr(io,'window',SimpleNamespace(TMP=tmp_path,require_live=lambda **k:dict(heavy_remaining_seconds=4000),
        ledger=lambda:dict(closed=False,active=None,runs=[],actor_wall_seconds=0.),auxiliary_wall=lambda:39.94901336694602))
    spec=io.load_return_diagnostic('input/task042_neural_coarse_inverse/v31_return_direction_diagnostic.dat')
    assert spec.derived['stage']==TASK042_PROFILES['task042_v31_diagnostic']=='V31-DIAGNOSTIC'
    assert spec.execution['timeout_seconds']==480
    for old in ('v27','v28'):
        assert io.load_return_diagnostic('input/task042_neural_coarse_inverse/'+old+'_return_direction_diagnostic.dat') is None
    assert v27.load_return_diagnostic(spec.source_path) is None and v28.load_return_diagnostic(spec.source_path) is None
    (tmp_path/'formal_admission_attempt.json').write_text('{}')
    from src.io.input_loader import InputError
    with pytest.raises(InputError,match='formal admission already consumed'):io.load_return_diagnostic(spec.source_path)


def test_failed_prequalification_stops_formal_route(tmp_path,monkeypatch):
    from src.io import return_block_v31 as io
    from src.io.input_loader import InputError
    (tmp_path/'aux_pre').mkdir();(tmp_path/'aux_pre/auxiliary_summary.json').write_text('{"classification":"COMPLETED","leader_exit_code":1}')
    def forbidden_after_failed_precheck(*args,**kwargs):
        raise AssertionError('failed pre-test must stop before live clock or ledger use')
    monkeypatch.setattr(io,'window',SimpleNamespace(TMP=tmp_path,
        require_live=forbidden_after_failed_precheck,ledger=forbidden_after_failed_precheck,
        auxiliary_wall=forbidden_after_failed_precheck))
    with pytest.raises(InputError,match='pre-test qualification failed'):
        io.load_return_diagnostic('input/task042_neural_coarse_inverse/v31_return_direction_diagnostic.dat')
