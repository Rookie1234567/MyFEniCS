"""Read-only V35 scalar receipts; no matrix, factor or reference loads."""
from copy import deepcopy

import pytest

from benchmarks.check_full_input_online import consumption
from src.io.full_input_online import read_result
from src.solvers.full_input_online_window import ledger


def actual_record():
    """Ignored evidence is an explicit dependency, never assumed on checkout."""
    from src.io.full_input_online import ARTIFACT_ROOT
    if not (ARTIFACT_ROOT/'ONLINE.json').exists():
        pytest.skip('artifact-dependent V35 cache receipt not available on clean checkout')
    return read_result('ONLINE')[0]

def test_actual_deployment_full_consumption_and_legacy_counter_scope():
    record=actual_record();out=consumption(record,ledger())
    assert out['status']=='CONSUMPTION_CHECKED'
    assert out['equivalent_actions']==record['actual_equivalent_actions']
    assert out['field_recovery_calls_derived']==len(record['cycles'])


@pytest.mark.parametrize('fault',['erase_fast','PC_zero','factor_order','unsafe_factor','factor_RHS',
    'missing_SH','wrong_source','not_cleared','erased_charge','fake_Arnoldi','nan_PC'])
def test_saved_consumption_rejects_inventory_source_and_numeric_tampering(fault):
    record=actual_record();r=deepcopy(record);book=deepcopy(ledger())
    if fault=='erase_fast':r['actual_equivalent_actions']=r['all_batch_equivalent_actions']
    elif fault=='PC_zero':r['pc_zero_calls']+=1
    elif fault=='factor_order':r['factor_reloads'].reverse()
    elif fault=='unsafe_factor':r['factor_reloads'][0]['witnesses'][0]['solve_relative']=1e-5
    elif fault=='factor_RHS':r['factor_reloads'][1]['RHS_columns']-=1
    elif fault=='missing_SH':r['fast_action_counts']['SH']=0
    elif fault=='wrong_source':book['runs'][0]['source_sha']='f'*40
    elif fault=='not_cleared':book['runs'][0]['descendants_cleared']=False
    elif fault=='erased_charge':book['charged']['actions']-=1
    elif fault=='fake_Arnoldi':r['cycles'][0]['inner']['inner_iterations']-=1
    elif fault=='nan_PC':r['PC_qualification']['J_balance'][0]['operation_relative']=float('nan')
    with pytest.raises(ValueError):consumption(r,book)


def test_verify_barrier_does_not_read_reference_after_numeric_negative(monkeypatch,tmp_path):
    from types import SimpleNamespace

    from src.io import full_input_online as io
    from src.io.input_loader import InputError
    from src.runners.task042_shared import write_json
    from src.solvers import neural_fe_blind_reference as reference
    from src.solvers.full_input_online_window import OnlineWindow
    monkeypatch.setattr(reference,'independent_physics',lambda *a,**kw:pytest.fail('unqualified reference access'))
    # This is a fresh isolated scope, not a reopened V35 production ledger.
    scope=OnlineWindow(tmp_path)
    scope.snapshot=lambda:dict(heavy_remaining_seconds=1000.,total_remaining_seconds=1500.)
    monkeypatch.setattr(io.window,'require_live',scope.require_live)
    monkeypatch.setattr(io.window,'ledger',scope.ledger)
    plan=tmp_path/'plan.json';write_json(plan,dict(action_sha256='p',physical_sha256='q'))
    monkeypatch.setattr(io,'PLAN_PATH',plan)
    monkeypatch.setattr(io,'plan_and_operator',lambda:(dict(physical_model_sha256='q'),{},
        SimpleNamespace(provenance=dict(material_table_id='SI_OPTICAL_CONSTANTS_USER_20260929_V1')),
        dict(packet=dict(sha256='p'))))
    monkeypatch.setattr(io,'read_result',lambda *a:(dict(status='ONLINE_BLOCK_PC_PROGRESS_INSUFFICIENT'),None))
    with pytest.raises(InputError,match='requires original equation pass'):
        io.load_online('input/task042_neural_coarse_inverse/v35_verify.dat')
    book=scope.ledger();book['closed']=True;write_json(scope.LEDGER_PATH,book)
    with pytest.raises(InputError,match='closed/active'):
        io.load_online('input/task042_neural_coarse_inverse/v35_verify.dat')
