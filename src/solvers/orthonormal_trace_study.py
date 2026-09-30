"""Finite, pre-registered orthonormal profiles and a one-way reference barrier.

Feature construction uses the existing FE moment mapper; all LS/QR workspace
is held by one pure-array subprocess. No hidden gradient or raw head decoder.
"""

import gc
import time
from pathlib import Path

import numpy as np

from src.io.orthonormal_trace_reprofile import V14_ROOT, read_frozen_state, read_result
from src.io.tangent_head_compensation import V13_ROOT
from src.runners.task042_shared import write_json
from src.solvers.neural_fe_action_packet import array_hash, file_hash
from src.solvers.orthonormal_trace_reprofile import FAMILY, profile_progress, ray_identity


def inventory(stage):
    rows = {}
    for item in stage.own_plan["frozen_points"]:
        try:
            saved = read_frozen_state(item["state"], V13_ROOT)
            if saved["hidden"].shape != (8576,) or not np.isfinite(saved["hidden"]).all():
                raise ValueError("hidden inventory differs")
            rows[item["name"]] = dict(item, hidden=saved["hidden"])
        except (OSError, ValueError, KeyError) as error:
            rows[item["name"]] = dict(item, missing=str(error))
    return rows


def mapper(stage):
    from src.runners.actual_loss_block_descent import make_experiment
    objective, _, _, _, _, threads, moment = make_experiment(stage)
    return objective.model, objective.cache, threads, moment


def release_workspace(work, *, retain_Q=False):
    """Only this new V14 workspace, pre-declared regenerable; never history."""
    work = Path(work).resolve()
    if not work.is_relative_to(V14_ROOT):
        raise ValueError("workspace ownership differs")
    removed = []
    for name in ("P.npy", "Q.npy"):
        path = work/name
        if path.exists() and not (name == "Q.npy" and retain_Q):
            removed.append(dict(path=str(path), sha256=file_hash(path), bytes=path.stat().st_size))
            path.unlink()
    write_json(work/"workspace_lifecycle.json", dict(removed_regenerable=removed,
        Q_retained=retain_Q, historical_artifacts_deleted=False))


def decoder(stage):
    frozen = inventory(stage)
    origin = frozen["ORIGIN"]
    if "missing" in origin:
        return dict(status="MISSING_FROZEN_ORIGIN", missing=origin["missing"], points=[], decoder_qualified=False)
    P = Path(stage.own_plan["original_P"]["path"])
    A = Path(stage.own_plan["original_A"]["path"])
    for path, record in ((P, stage.own_plan["original_P"]),(A, stage.own_plan["original_A"])):
        if file_hash(path) != record["sha256"]:
            raise ValueError("original same-hidden thin workspace hash differs")
    if array_hash(origin["hidden"]) != stage.own_plan["original_basis_hidden_sha256"]:
        raise ValueError("origin/basis hidden identity differs")
    stage.event("decoder_origin_start", historical_hidden=origin["state"], reference_read=False)
    record, work = stage.child("ORIGIN",origin["hidden"],P,saved_A=A,witnesses=True)
    point = record["physical"]
    point.update(historical=origin["state"], historical_raw_Phi=origin["historical_raw_Phi"], s=0.)
    sensitivity = dict(status="NOT_RUN", delta_basis=0.)
    if record["decoder_qualified"]:
        reverse, reverse_work = stage.child("REVERSE_ROWS",origin["hidden"],P,reverse=True)
        regular = read_frozen_state(point["state"],V14_ROOT)
        witness = read_frozen_state(reverse["physical"]["state"],V14_ROOT)
        sensitivity = dict(status="COMPLETED", delta_basis=abs(
            point["numeric"]["Phi"]-reverse["physical"]["numeric"]["Phi"]),
            trace_relative=float(np.linalg.norm(regular["trace"]-witness["trace"])/np.linalg.norm(regular["trace"])),
            z_relative=float(np.linalg.norm(regular["z"]-witness["z"])/np.linalg.norm(regular["z"])),
            residual_difference=float(np.linalg.norm(regular["residual"]-witness["residual"])),
            main=record["basis"], reverse=reverse["basis"], reverse_point=reverse["physical"],
            reverse_decoder_qualified=reverse["decoder_qualified"],
            canonical_rows_restored=True, reverse_selected_as_main=False,
            observed_sensitivity_not_error_bound=True)
        release_workspace(reverse_work)
    stage.event("decoder_gate",qualified=record["decoder_qualified"], sensitivity=sensitivity["delta_basis"])
    return dict(status="DECODER_QUALIFIED" if record["decoder_qualified"] else "STABLE_DECODER_UNQUALIFIED",
        decoder_qualified=record["decoder_qualified"], origin=point, witnesses=record["witnesses"],
        basis=record["basis"], sensitivity=sensitivity, origin_Q_path=str(work/"Q.npy"),
        threads=record["threads"], inventory=[{k:v for k,v in row.items() if k!="hidden"} for row in frozen.values()])


def profile(stage):
    prior, decoder_path = read_result("DECODER")
    if not prior["decoder_qualified"]:
        return dict(status="STABLE_DECODER_UNQUALIFIED", points=prior.get("points",[]),
                    queue_frozen=True, selected=None, O3=dict(status="NOT_RUN_DECODER_GATE"))
    points = [prior["origin"]]
    origin = points[0]
    delta_basis = prior["sensitivity"]["delta_basis"]
    frozen = inventory(stage)
    model, cache, threads, moment = mapper(stage)
    from src.solvers.neural_linear_head_torch import build_head_mapping
    from src.solvers.stable_head_varpro_torch import set_hidden
    selected = origin
    selected_workspace = None
    missing, failures = [], []

    def evaluate(name, hidden, s, historical=None):
        nonlocal selected, selected_workspace
        stage.guard(extra_actions=1560, large=True)
        temporary = stage.artifact/(name+"_mapping"); temporary.mkdir()
        set_hidden(model,hidden)  # Raw output layer is intentionally unused.
        began = time.perf_counter()
        P, mapping = build_head_mapping(model,cache,temporary/"P.npy",heartbeat=stage.event)
        mapping["sha256"] = file_hash(temporary/"P.npy")
        del P; gc.collect()
        record, work = stage.child(name,hidden,temporary/"P.npy")
        point = record["physical"]
        point.update(s=s, basis=record["basis"], mapping=mapping,
            profile_wall_seconds=time.perf_counter()-began, source_sha=stage.source,
            historical=historical["state"] if historical else None,
            historical_raw_Phi=historical["historical_raw_Phi"] if historical else None)
        point["progress_vs_origin"] = profile_progress(origin,point,delta_basis)
        points.append(point)
        better = (point["progress_vs_origin"]["qualified_for_selection"]
                  and point["numeric"]["Phi"] < selected["numeric"]["Phi"])
        if better:
            if selected_workspace:
                release_workspace(selected_workspace)
            selected, selected_workspace = point, work
        release_workspace(work,retain_Q=better)
        release_workspace(temporary)
        stage.event("profile_point_frozen",name=name,Phi=point["numeric"]["Phi"],
                    decoder_gate=point["numeric"]["decoder_gate"],progress=point["progress_vs_origin"])
        return point

    for name in ("TRIAL_4","TRIAL_3","TRIAL_2","TRIAL_1","TRIAL_0"):
        row = frozen[name]
        if "missing" in row:
            missing.append(dict(name=name,reason=row["missing"])); continue
        try:
            evaluate(name,row["hidden"],row["s"],row)
        except ValueError as error:
            # A failed current decoder is isolated; resource/deadline failures
            # are RuntimeError and stop the owned load instead of continuing.
            failures.append(dict(name=name,reason=str(error)))
            stage.event("profile_isolated",name=name,reason=str(error))
    ray = []
    if "missing" not in frozen["TRIAL_0"]:
        for row in frozen.values():
            if row["name"]!="ORIGIN" and "missing" not in row:
                ray.append(ray_identity(frozen["ORIGIN"]["hidden"],frozen["TRIAL_0"]["hidden"],row["hidden"],row["s"]))
    progress = profile_progress(origin,selected,delta_basis)
    from src.runners.autonomous_neural_head import original_gate
    dispatch = dict(status="NOT_RUN_NO_PRE_REGISTERED_PROGRESS",progress=progress,ray_checks=ray,
                    no_reference_used_for_selection=True)
    strict = original_gate(selected["audit"])["status"]=="ORIGINAL_EQUATION_PASS"
    if progress["O3_admitted"] and ray and all(row["consistent"] for row in ray) and not strict:
        best_s = selected["s"]
        known_s = sorted(point["s"] for point in points)
        if best_s == 1.:
            requests = [2.,4.]
        else:
            i = known_s.index(best_s)
            requests = [(best_s+known_s[i+1])/2,(best_s+known_s[i-1])/2]
        dispatch.update(status="O3_ADMITTED",requested_s=requests,evaluated_s=[])
        v = frozen["TRIAL_0"]["hidden"]-frozen["ORIGIN"]["hidden"]
        last = selected
        for s in requests:
            if best_s==1. and s==4. and not profile_progress(last,selected,delta_basis)["O3_admitted"]:
                break
            hidden = frozen["ORIGIN"]["hidden"]+s*v
            if np.linalg.norm(hidden-frozen["ORIGIN"]["hidden"]) > 1e-3*max(1.,np.linalg.norm(frozen["ORIGIN"]["hidden"])):
                dispatch["stop_reason"]="HIDDEN_CHANGE_BOUND"; break
            stage.count("new_profiles")
            previous = selected
            evaluate("NEW_S_"+str(s).replace(".","p"),hidden,s)
            dispatch["evaluated_s"].append(s)
            if best_s==1.:
                if not profile_progress(previous,selected,delta_basis)["O3_admitted"]:
                    dispatch["stop_reason"]="S2_NO_QUALIFIED_IMPROVEMENT"; break
                last = previous
    del model, cache; gc.collect()
    result = dict(status="FIXED_PROFILE_QUEUE_FROZEN",points=points,missing=missing,failures=failures,
        selected=selected["name"],selected_state=selected["state"],sensitivity=prior["sensitivity"],
        decoder_result=str(decoder_path),queue_frozen=True,O3=dispatch,threads=threads,moments=moment,
        origin_Q_path=prior["origin_Q_path"],selected_Q_path=str(selected_workspace/"Q.npy") if selected_workspace else prior["origin_Q_path"],
        raw_gamma_forward_used=False,decoder_family=FAMILY,reference_used_for_selection=False)
    write_json(stage.artifact/"solver_queue_frozen.json",result)
    stage.event("all_profiles_frozen_before_reference",states=len(points),selected=selected["name"],O3=dispatch)
    return result


def verify(stage):
    from src.io.neural_fe_continuation import read_index,V7_ROOT
    from src.runners.autonomous_neural_head import owned,original_gate
    from src.solvers.neural_fe_blind_reference import independent_physics
    from src.runners.task042_experiment import thread_qualification
    prior, prior_path = read_result("PROFILE")
    if not prior["queue_frozen"]:
        raise ValueError("reference barrier: solver queue not frozen")
    candidates, sources, seen = {}, {}, set()
    all_rows = list(stage.own_plan["historical_validation_states"])+prior["points"]
    for item in all_rows:
        allowed = V14_ROOT if Path(item["state"]["path"]).resolve().is_relative_to(V14_ROOT) else V13_ROOT
        try:
            arrays = read_frozen_state(item["state"],allowed)
        except (OSError,ValueError,KeyError) as error:
            stage.event("missing_validation_state",name=item["name"],reason=str(error)); continue
        identity = array_hash(arrays["z"])
        if identity in seen: continue
        seen.add(identity); candidates[item["name"]]=arrays["z"]
        sources[item["name"]]=dict(state=item["state"],source_sha=item.get("source_sha"),decoder_identity=item.get("decoder_identity"))
    if not 1<=len(candidates)<=10:
        raise ValueError("one to ten frozen states required")
    stage.count("field_states",len(candidates))
    stage.event("solver_queue_frozen_before_REF7",states=list(candidates),profile_record_sha256=file_hash(prior_path))
    reference_record,_=read_index("blind_reference")
    path=owned(reference_record["reference_state"],V7_ROOT)
    if file_hash(path)!=stage.own_plan["reference_sha256"]:
        raise ValueError("REF7 identity differs")
    with np.load(path,allow_pickle=False) as data:
        reference=np.array(data["z"])
    stage.meta["reference_arrays_read"]=True
    stage.count("original_audits",len(candidates)+1)
    physics,comparisons=independent_physics(stage.design,stage.packet,reference,candidates,stage.artifact)
    rows={}
    for name in candidates:
        item=physics["rows"][name];comparison=comparisons[name];audit=item["audit"]
        eq=original_gate(audit)
        fields={key:item[key] for key in ("full_FE_L2_relative","full_FE_scaled_curl_relative",
            "scattered_FE_L2_relative","scattered_scaled_curl_relative","selected_E_relative","selected_H_relative")}
        same=(eq["status"]=="ORIGINAL_EQUATION_PASS" and physics["reference_native_pass"]
            and len(item["ordered_complex_port_vector"])==40
            and len(item["ordered_complex_scattered_port_vector"])==40
            and audit["schur_original_identity_operation_relative"]<=1e-10
            and all(np.isfinite(v) and v<=1e-4 for v in fields.values())
            and audit["independent_DOLFINx_total_native_relative"]<=1e-6
            and comparison["ordered_complex_ports_relative"]<=1e-4
            and all(v<=1e-5 for v in comparison["power_absolute_differences"].values())
            and comparison["max_channel_power_difference"]<=1e-6
            and comparison["energy_closure_absolute"]<=1e-5)
        rows[name]=dict(status="SAME_DISCRETE_QUALIFIED" if same else "NOT_QUALIFIED",
            original_equation_gate=eq,audit=audit,fields=fields,comparison=comparison,
            ordered_complex_total_ports=item["ordered_complex_port_vector"],
            ordered_complex_scattered_ports=item["ordered_complex_scattered_port_vector"],
            selected_E=item["selected_E"],selected_H_code=item["selected_H_code"],
            power=item["port"],volume_absorption=item["volume"],official_candidate_results=bool(same))
    return dict(status="FROZEN_VALIDATION_COMPLETE",rows=rows,states_read=len(candidates),
        state_sources=sources,reference_identity=reference_record["reference_state"],
        reference_only_after_solver_frozen=True,reference_feedback_to_solver=False,
        threads=thread_qualification(),no_new_solve=True,no_p4_enrichment=True)
