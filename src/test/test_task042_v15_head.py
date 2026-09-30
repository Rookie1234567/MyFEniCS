"""Original non-Hermitian action, full manufactured port RHS and barriers."""

import json

import numpy as np
import pytest

from src.solvers.local_trace_decoder import BlockTraceDecoder,UnionTraceDecoder
from src.solvers.local_trace_head import TraceLinearHead
from src.solvers.orthonormal_trace_reprofile import manufactured_witness
from src.solvers.stable_head_varpro import PortBlocks
from src.test.test_task042_v14_orthonormal import Packet


def test_block_head_original_action_and_affine_manufacture():
    packet=Packet();rng=np.random.default_rng(421501)
    rows=[np.arange(12),np.arange(12,24)]
    blocks=[np.linalg.qr(rng.normal(size=(12,3))+1j*rng.normal(size=(12,3)))[0] for _ in rows]
    decoder=BlockTraceDecoder(rows,blocks,24)
    counts={};count=lambda k,n=1:counts.__setitem__(k,counts.get(k,0)+n)
    head=TraceLinearHead(packet,decoder,PortBlocks(packet,packet.matrix[:,24:]),count=count)
    c=rng.normal(size=6)+1j*rng.normal(size=6)
    known=np.r_[decoder@c,rng.normal(size=40)+1j*rng.normal(size=40)]
    original=packet.a['b'].copy()
    point,rhs,witness=manufactured_witness(head,known,'LOCAL-M1')
    assert witness['qualified'] and np.linalg.norm(rhs[24:])>0
    assert head.solve(original)['numeric']['decoder_gate']
    assert counts['new_A_columns']==6 and len(head.pairing)==5
    assert np.array_equal(original,packet.a['b'])
    assert not head.decomposition()['exact_full_space_optimum_claimed']


def test_union_head_preserves_global_candidate_without_solution_addition():
    packet=Packet();rng=np.random.default_rng(421505)
    Q=np.linalg.qr(rng.normal(size=(24,9))+1j*rng.normal(size=(24,9)))[0]
    decoder=UnionTraceDecoder(Q[:,:4],Q[:,4:])
    head=TraceLinearHead(packet,decoder,PortBlocks(packet,packet.matrix[:,24:]))
    point=head.solve(packet.a['b'])
    assert point['numeric']['rank_A']==9 and point['numeric']['decoder_gate']
    assert np.allclose(point['trace'],decoder@point['c'])


def test_local_reference_barrier_and_frozen_hash(tmp_path,monkeypatch):
    import src.io.local_trace_representation as module
    from src.solvers.neural_fe_action_packet import file_hash
    plan=tmp_path/'plan.json';plan.write_text('{}')
    result=tmp_path/'result.json';result.write_text(json.dumps(dict(plan_sha256=file_hash(plan),reference_arrays_read=True)))
    (tmp_path/'LOCAL_NN.json').write_text(json.dumps(dict(path=str(result),sha256=file_hash(result))))
    monkeypatch.setattr(module,'ARTIFACT_ROOT',tmp_path);monkeypatch.setattr(module,'PLAN_PATH',plan)
    with pytest.raises(ValueError,match='reference barrier'):module.read_result('LOCAL_NN')


def test_explicit_one_run_inventory_six_stages():
    from src.io.local_trace_representation import STAGES,FAMILY
    from src.io.task042_profile import ROOT,TASK042_PROFILES
    import tomllib
    files=sorted((ROOT/'input/task042_neural_coarse_inverse').glob('v15_*.dat'))
    assert len(files)==6
    stages=set()
    for path in files:
        item=tomllib.loads(path.read_text())['task042_v15'];stages.add(item['stage'])
        assert item['decoder_family']==FAMILY
        assert TASK042_PROFILES['task042_v15_'+item['stage'].lower()]=='V15-'+item['stage']
    assert stages==set(STAGES)
