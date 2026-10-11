"""Right-coordinate algebra and full old-map fixtures, not PDE evidence."""

from copy import deepcopy
import json
import numpy as np
import pytest
import torch

from src.solvers.ftt_feature_coordinates import (
    FeatureCoordinates, FeatureCoordinateCache, coordinate_policy, coordinate_trend,
)
from src.solvers.ftt_core_refinement import solve_refined, segment
from src.solvers.ftt_conditional_core import (
    ConditionalCoreAction, DirectionField, output_coefficients,
    set_output_coefficients, relative_pair, verify_and_apply_core,
)
from src.solvers.ftt_factored_moments import FactoredMomentMap
from src.solvers.ftt_moments import StreamingMomentMap
from src.test.test_ftt_width import pair, MatrixOperator
from src.test.test_ftt_structure import fixture
from src.test.test_ftt_conditional_core import TinyAction


def random_features(n=23, m=6):
    rng = np.random.default_rng(4214501)
    return rng.normal(size=(n,m))+1j*rng.normal(size=(n,m))


@pytest.mark.parametrize("case", ["full", "duplicate", "scaled", "few_nodes"])
def test_small_complex_right_transform_and_independent_svd(case):
    f = random_features(3 if case == "few_nodes" else 23)
    if case == "duplicate":
        f[:,-1] = f[:,0]
    if case == "scaled":
        f *= np.logspace(-4,2,6)
    t = FeatureCoordinates(f,(6,1,1,1))
    assert len(t.record["singular_values"]) == 6
    assert t.record["all_directions_retained"] and t.record["truncated_directions"] == 0
    assert np.linalg.matrix_rank(t.matrix,tol=1e-8)==6
    assert t.record["svd_backward_relative"] <= 1e-12
    if case in ("duplicate","few_nodes"):
        assert t.record["gain_cap_count"] > 0
    rng=np.random.default_rng(71)
    v=rng.normal(size=6)+1j*rng.normal(size=6)
    assert relative_pair(t.inverse(t.forward(v)),v)["relative"] < 1e-8
    B=random_features(17)
    if case == "duplicate":
        B[:,-1]=B[:,0]
    # Keep LS numerical conditioning distinct from feature scaling; original
    # target/field is compared, not the nonunique minimum parameter norm.
    b=rng.normal(size=17)+1j*rng.normal(size=17)
    d,record=solve_refined(MatrixOperator(B),b,iteration_allowance=1200,
        persist_first=lambda *_:None,coordinate_transform=t)
    exact=np.linalg.lstsq(B,b,rcond=1e-12)[0]
    assert abs(np.linalg.norm(b-B@d)-np.linalg.norm(b-B@exact))/np.linalg.norm(b)<1e-7
    assert record["original_coordinates_used_for_quality"]
    assert record["coordinate_adjoint_initial_norm"]>0


def test_identity_exact_old_segment_regression():
    B=random_features(17)
    b=random_features(17,1).ravel()
    transform=FeatureCoordinates(random_features(),(6,1,1,1),identity=True)
    old,row,_=segment(MatrixOperator(B),b,300,1e-8)
    new,changed,_=segment(MatrixOperator(B),b,300,1e-8,transform)
    assert np.array_equal(old,new) and row["iterations"]==changed["iterations"]
    assert row["true_adjoint_residual_norm"]==changed["true_adjoint_residual_norm"]


def test_wrong_conjugate_and_y_as_delta_are_rejected():
    t=FeatureCoordinates(random_features(),(6,1,1,1))
    rng=np.random.default_rng(7)
    y=rng.normal(size=6)+1j*rng.normal(size=6)
    v=rng.normal(size=6)+1j*rng.normal(size=6)
    lhs=np.vdot(t.forward(y),v)
    assert abs(lhs-np.vdot(y,t.adjoint(v)))<1e-12*max(1,abs(lhs))
    assert abs(lhs-np.vdot(y,t.matrix.T@v))>1e-5
    with pytest.raises(ValueError,match="NOT_ORIGINAL_DELTA"):
        t.verify_retained(y,y,t.sha256)
    with pytest.raises(ValueError,match="IDENTITY_MISMATCH"):
        t.verify_retained(t.forward(y),y,"bad")
    assert t.verify_retained(t.forward(y),y,t.sha256)==0


@pytest.mark.parametrize("axis", [0,1,2])
@pytest.mark.parametrize("kind", ["complex","imaginary","bias"])
def test_three_axis_old_point_map_and_complex_adjoint(axis,kind):
    _,model=pair()
    p=fixture(True,False)
    mapping=FactoredMomentMap(p)
    raw=StreamingMomentMap(p)
    action=TinyAction(np.eye(6,dtype=complex))
    c=mapping.forward(model)
    saved=deepcopy(model.state_dict())
    op=ConditionalCoreAction(model,mapping,action,axis)
    t=FeatureCoordinateCache().get(model,mapping,axis,op.shape)
    rng=np.random.default_rng(42)
    y=rng.normal(size=op.shape)+1j*rng.normal(size=op.shape)
    if kind=="imaginary": y=1j*y.imag
    if kind=="bias": y[:-1]=0
    delta=t.forward(y)
    y=y.ravel()/np.linalg.norm(delta); delta=t.forward(y)
    dual=rng.normal(size=6)+1j*rng.normal(size=6)
    kd=op.K(delta)
    point=raw.forward(DirectionField(model,axis,delta.reshape(op.shape)))
    assert relative_pair(kd,point)["relative"]<1e-10
    assert abs(np.vdot(kd,dual)-np.vdot(y,t.adjoint(op.KH(dual)))) < 1e-10*max(1,abs(np.vdot(kd,dual)))
    before=output_coefficients(model,axis)
    set_output_coefficients(model,axis,before+delta.reshape(op.shape))
    mapping.invalidate()
    assert relative_pair(mapping.forward(model),c+kd)["relative"]<1e-10
    with pytest.raises(ValueError,match="VERSION_CHANGED"): op.K(delta)
    model.load_state_dict(saved); mapping.invalidate()


def test_cache_axis_dependencies_and_restored_state():
    _,model=pair(); mapping=FactoredMomentMap(fixture())
    shape=output_coefficients(model,0).shape
    cache=FeatureCoordinateCache()
    t=cache.get(model,mapping,0,shape)
    saved=deepcopy(model.state_dict())
    coeff=output_coefficients(model,0)
    set_output_coefficients(model,0,coeff+1e-4)
    assert cache.get(model,mapping,0,shape) is t
    with torch.no_grad(): model.cores[0][0].bias.add_(1e-4)
    assert cache.get(model,mapping,0,shape).sha256!=t.sha256
    model.load_state_dict(saved)
    assert cache.get(model,mapping,0,shape) is t
    with torch.no_grad(): model.phase_wavevector[0].add_(1e-4)
    assert cache.get(model,mapping,0,shape).sha256!=t.sha256
    model.load_state_dict(saved)
    nodes=mapping.nodes[0].copy(); mapping.nodes[0]=nodes+1e-5
    assert cache.get(model,mapping,0,shape).sha256!=t.sha256
    mapping.nodes[0]=nodes
    assert cache.get(model,mapping,0,shape) is t


def test_retained_two_segment_original_increment_and_identity(tmp_path):
    B=random_features(17); b=random_features(17,1).ravel()
    t=FeatureCoordinates(random_features(),(6,1,1,1))
    saved=[]
    def persist(d,record,residual):
        np.savez(tmp_path/"first.npz",delta=d,solve_y=t.last_solve_y,b=b)
        saved.append(record)
    d,row=solve_refined(MatrixOperator(B),b,iteration_allowance=1200,persist_first=persist,coordinate_transform=t)
    with np.load(tmp_path/"first.npz") as data:
        original=data["delta"].copy(); y=data["solve_y"].copy()
    assert t.verify_retained(original,y,t.sha256)<1e-10
    reopened,record=solve_refined(MatrixOperator(B),b,iteration_allowance=1200,
        persist_first=lambda *_:pytest.fail("first replayed"),resume_first=(original,saved[0]),coordinate_transform=t)
    assert relative_pair(B@d,B@reopened)["relative"]<1e-9
    broken=deepcopy(saved[0]); broken["coordinate_transform_sha256"]="wrong"
    with pytest.raises(ValueError,match="TRANSFORM_IDENTITY"):
        solve_refined(MatrixOperator(B),b,iteration_allowance=1200,persist_first=lambda *_:None,
                      resume_first=(original,broken),coordinate_transform=t)


def test_real_writeback_failure_restores_all_outputs(monkeypatch):
    _,model=pair(); mapping=FactoredMomentMap(fixture())
    action=TinyAction(np.eye(6,dtype=complex)); c=mapping.forward(model)
    op=ConditionalCoreAction(model,mapping,action,0)
    before=output_coefficients(model,0)
    old_forward=mapping.forward
    monkeypatch.setattr(mapping,"forward",lambda m:old_forward(m)+1e3)
    _,_,row=verify_and_apply_core(model,mapping,action,op,np.ones(op.size,dtype=complex)*1e-5,c)
    assert not row["accepted"] and np.array_equal(before,output_coefficients(model,0))


def test_fixed_extra_round_gate_and_initial_limits():
    parent=dict(native_relative=0.4,scattered_E_relative=0.1,scattered_H_relative=0.1)
    current=dict(native_relative=0.3,scattered_E_relative=0.075,scattered_H_relative=0.075)
    assert coordinate_trend(14,current,parent,coordinate_policy(True))["allowed"]
    assert not coordinate_trend(14,current,parent,coordinate_policy(False))["allowed"]
    assert not coordinate_trend(16,current,parent,coordinate_policy(True))["allowed"]
    assert not coordinate_trend(14,parent,parent,coordinate_policy(True))["allowed"]
    assert coordinate_policy(True)["initial_new_iteration_limit"]==7200


def test_new_schema_and_old_schema_reject_cross_identity(monkeypatch,tmp_path):
    from src.io import ftt_coordinate_campaign as io
    from src.io.ftt_width_campaign import load_width
    from src.io.input_loader import InputError
    from src.io.neural_wave_campaign import digest, profile_paths
    data=json.loads(io.DESIGN.read_text()); path=tmp_path/"design.json"
    path.write_text(json.dumps(data)); monkeypatch.setattr(io,"DESIGN",path)
    payload=dict(schema_version=15,neural_wave=dict(stage="v45_identity_frozen",design_sha256=digest(path)))
    original=io.ROOT/"input/task042extra_feinn_5nm/v45_identity_frozen.dat"
    assert io.load_coordinates(original,payload,b"fixture")["hidden_width"]==32
    with pytest.raises(InputError,match="SCHEMA"): load_width(original,payload,b"fixture")
    payload["neural_wave"]["reference_state"]="forbidden"
    with pytest.raises(InputError,match="LABEL"): io.load_coordinates(original,payload,b"fixture")
    del payload["neural_wave"]["reference_state"]
    data["coordinate_rule"]["directions_removed"]=1
    path.write_text(json.dumps(data)); payload["neural_wave"]["design_sha256"]=digest(path)
    with pytest.raises(InputError,match="POLICY"): io.load_coordinates(original,payload,b"fixture")
    assert profile_paths(dict(campaign_version=45))["reserve"]==3600


def test_numeric_role_and_window_budget():
    from src.runners.neural_wave_campaign import stage_deadline, window
    from src.io.ftt_coordinate_campaign import STAGES
    from src.runners.block_wave_admission import wait_limit
    from src.io.neural_wave_campaign import ROOT
    w=window(dict(campaign_version=45))
    assert w["budget_s"]==43200
    d,reserve=stage_deadline(dict(campaign_version=45),dict(deadline_monotonic=w["deadline_monotonic"]),w)
    assert reserve==3600 and d==w["deadline_monotonic"]-3600
    assert all(row[1]==7200 for row in STAGES.values() if row[3])
    assert wait_limit(ROOT/"tmp/task42extra/v45/test")==900


def test_round12_parent_actual_file_firewall_and_forbidden_labels():
    import subprocess
    import sys

    code = """
import json
from src.runners.ftt_core_worker import install_unlabelled_firewall
from src.io.ftt_coordinate_campaign import DESIGN, ROOT
d=json.loads(DESIGN.read_text())
records=install_unlabelled_firewall(d,ROOT/'benchmarks/artifacts/task42extra/v45/test_firewall')
assert len(records)==4 and all(x['actual_open_rejected'] for x in records)
with (ROOT/d['parent_checkpoint']['path']).open('rb') as stream:
    assert stream.read(0)==b''
print(json.dumps(records))
"""
    r=subprocess.run([sys.executable,"-c",code],capture_output=True,text=True)
    assert r.returncode==0,r.stderr
    assert len(json.loads(r.stdout))==4


def test_round14_complete_audit_before_trend_and_hidden_freeze(tmp_path,monkeypatch):
    from time import monotonic
    from src.test.test_ftt_core_continuation import parent_fixture, scalar
    from src.solvers.ftt_core_training import CoreBoundary, run_core_training
    from src.solvers.optimization_checkpoint import capture, atomic_write, digest
    from src.solvers.ftt_conditional_core import hidden_parameters
    from src.solvers.ftt_feature_coordinates import FeatureCoordinateCache

    _,action,old,parent,binding=parent_fixture(tmp_path)
    _,model=pair()
    position=deepcopy(old["optimizer"])
    position.update(round=12,complete_rounds=12)
    counts=deepcopy(old["metadata"]["counts"])
    counts.update(core_visits=36,LSMR_iterations=19830,hidden_actual_calls=137)
    mapping=FactoredMomentMap(fixture());c=mapping.forward(model)
    meta=deepcopy(old["metadata"])
    meta.update(position=position,counts=counts,rounds=[dict(round=i,native=.7) for i in range(12)])
    state=capture(model,CoreBoundary(position),meta)
    state.update(c=c,r=action.apply(c)-action.f)
    path=tmp_path/"parent12.pt"
    atomic_write(path,lambda f:torch.save(state,f))
    parent.update(path=str(path),sha256=digest(path),bytes=path.stat().st_size,
        inherited_rounds=12,inherited_counts=counts,parent_scalars=scalar(.4,.1))
    hidden=[p.detach().clone() for p in hidden_parameters(model)]
    axes=[];callbacks=[]
    def solve(op,b,**kwargs):
        axes.append(op.axis)
        return np.zeros(op.size,complex),dict(iterations=1,charged_unretained_iterations=0,
            chosen_increment="first",inner_quality="INNER_ACCURACY_UNRESOLVED")
    monkeypatch.setattr("src.solvers.ftt_core_refinement.solve_refined",solve)
    cache=FeatureCoordinateCache(identity=True)
    def factory(m,map_,op):
        t=cache.get(m,map_,op.axis,op.shape)
        return t,t.record
    def validate(number,*_):
        callbacks.append(("scalar",number))
        return scalar(.3,.075)
    def joint(*_):
        callbacks.append(("complete_joint",14))
        return dict(joint_pass=False,mapping_and_quadrature_pass=True)
    result=run_core_training(action,fixture(),model,tmp_path/"route",binding,monotonic()+300,
        lambda *_:None,learned=False,parent_checkpoint=parent,execution_policy=coordinate_policy(False),
        coordinate_transform_factory=factory,validation_callback=validate,joint_validation_callback=joint)
    assert axes==[2,0,1,1,0,2] and callbacks==[("scalar",14),("complete_joint",14)]
    assert result["new_complete_rounds"]==2 and result["new_counts"]["core_visits"]==6
    assert result["new_counts"]["hidden_actual_calls"]==0
    assert result["rounds"][-1]["complete_joint_verdict"]["joint_pass"] is False
    assert result["position"].get("native_target",1e-8)==1e-8
    assert all(p.detach().equal(q) for p,q in zip(hidden_parameters(model),hidden,strict=True))
    assert result["official_candidate_results"] is False


def test_scalar_consumer_reuses_only_matching_completed_feedback(tmp_path,monkeypatch):
    from src.runners import ftt_bloch_worker as worker
    from src.postprocessing.ftt_bloch_scalars import FIELDS
    monkeypatch.setattr(worker,"ROOT",tmp_path)
    calls=[]
    def checker(command,directory,*_):
        calls.append(command)
        summary=dict(classification="COMPLETED",leader_exit_code=0,descendants_cleared=True,
            sampled_process_tree_rss_peak_bytes=100)
        (directory/"supervised").mkdir(parents=True)
        (directory/"supervised/summary.json").write_text(json.dumps(summary))
        request=json.loads((directory.parent/"request.json").read_text())
        value=dict(request,schema="ftt.bloch-validation.scalars.v1",
            native_relative=.4,augmented_relative=.4,scattered_E_relative=.1,
            scattered_H_relative=.1,scattered_curl_relative=.1,reference_feedback="scalars_only")
        value={k:v for k,v in value.items() if k in FIELDS}
        (directory.parent/"scalars.json").write_text(json.dumps(value))
        return summary
    monkeypatch.setattr("src.runners.saved_field_supervision.run_checker",checker)
    manifest=dict(spec=dict(stage="fixture"),source_sha="a"*40,design_sha256="b"*64,
        worker_stop_monotonic=1e20)
    artifact=tmp_path/"artifact";artifact.mkdir()
    directory=tmp_path/"run";directory.mkdir()
    validate=worker.training_options(manifest,artifact,lambda *_:None,directory,{},
        design_path=tmp_path/"design.json",scoring_root=tmp_path/"scoring",reuse_saved_feedback=True)["validation_callback"]
    cp=dict(generation=1,sha256="c"*64)
    c=np.arange(6,dtype=complex);r=c+1j
    first=validate(14,cp,c,r);second=validate(14,cp,c,r)
    assert first==second and len(calls)==1
    with pytest.raises(ValueError,match="SAVED_FIELD_CHANGED"):
        validate(14,cp,c+1,r)


def test_three_saved_same_parent_forks_and_third_route_corruption(tmp_path,monkeypatch):
    from src.postprocessing import ftt_common_wall as audit
    from src.runners import ftt_width_worker
    from src.io.ftt_coordinate_campaign import routes
    from src.solvers.ftt_core_training import CoreBoundary
    from src.solvers.ftt_conditional_core import hidden_parameters
    from src.solvers.optimization_checkpoint import capture,atomic_write,digest,load_checkpoint
    _,model=pair()
    parent=capture(model,CoreBoundary({}),{})
    parent.update(c=np.ones(6,complex),r=np.ones(6,complex))
    p=tmp_path/"parent.pt"
    atomic_write(p,lambda f:torch.save(parent,f))
    design=dict(campaign_version=45,parent_checkpoint=dict(path="parent.pt",sha256=digest(p)))
    monkeypatch.setattr(audit,"ROOT",tmp_path)
    monkeypatch.setattr(ftt_width_worker,"model_factory",lambda *_:pair()[1])
    root=tmp_path/"source"
    for stage,_ in routes():
        state=deepcopy(parent)
        state["metadata"].update(hidden_width=32,
            hidden_real_parameters=sum(q.numel() for q in hidden_parameters(model)),
            inherited_state=dict(inherited_counts={}),new_counts={})
        folder=root/stage/"checkpoints";folder.mkdir(parents=True)
        entries=[]
        for name in ("initial.pt","final.pt"):
            file=folder/name;atomic_write(file,lambda f:torch.save(state,f))
            entries.append(dict(name=name,sha256=digest(file)))
        (folder.parent/"checkpoint_index.json").write_text(json.dumps(entries))
        (folder.parent/"result.json").write_text(json.dumps(dict(checkpoint=entries[-1])))
    output=audit.initialize_output(tmp_path/"audit")
    audit.audit_saved_forks(output,root,design)
    result=json.loads((output/"initial_and_final_forks.json").read_text())
    assert len(result["records"])==3 and result["actual_initial_forks_bitwise_same"]
    assert set(result["hidden_real_parameter_counts"].values())=={3360}
    folder=root/routes()[-1][0]
    index=json.loads((folder/"checkpoint_index.json").read_text())
    file=folder/"checkpoints"/"initial.pt"
    state=load_checkpoint(file,digest(file));state["model"]["cores.2.0.bias"][0]+=1e-3
    atomic_write(file,lambda f:torch.save(state,f));index[0]["sha256"]=digest(file)
    (folder/"checkpoint_index.json").write_text(json.dumps(index))
    with pytest.raises(ValueError,match="SAVED_FORK_MODEL_FIELD"):
        audit.audit_saved_forks(output,root,design)


def test_conditional_pilot_requires_actual_and_producer_joint_pass(tmp_path,monkeypatch):
    from src.runners import ftt_coordinate_worker as worker
    monkeypatch.setattr(worker,"ART",tmp_path/"source")
    monkeypatch.setattr(worker,"compare_common_wall",lambda *_:{})
    records={}
    for stage,role in worker.routes():
        folder=worker.ART/stage;folder.mkdir(parents=True)
        (folder/"result.json").write_text(json.dumps(dict(position=dict(complete_rounds=14))))
        for suffix in ("","_PRODUCER"):
            records[role+suffix]=dict(m5_full_discrete_numerical_gate=True)
    artifact=tmp_path/"compare";artifact.mkdir()
    key="W32_R12_FEATURE_SCALED_LEARNED_PRODUCER"
    records[key]["m5_full_discrete_numerical_gate"]=False
    (artifact/"saved_checker.json").write_text(json.dumps(dict(records=records)))
    decision=worker.comparison_record({},artifact,lambda *_:None,tmp_path)["coordinate_decision"]
    assert not decision["conditional_0p7_numerical_gate"]
    assert decision["conditional_0p7_requires_separate_safe_admission_and_10800s_remaining"]
