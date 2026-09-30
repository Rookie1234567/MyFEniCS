"""V12 one-run orchestration over the original action and frozen V11 state."""

from __future__ import annotations

import gc
import ctypes
import json
import os
import signal
import subprocess
import sys
import time
import traceback
from pathlib import Path

import numpy as np

from src.io.actual_loss_block_descent import V12_ROOT, load_actual_loss, publish, read_result
from src.io.autonomous_neural_head import plan_and_operator
from src.io.neural_fe_continuation import V7_ROOT, read_index
from src.io.stable_head_varpro import PLAN_PATH, V11_ROOT, read_result as read_v11
from src.runners.autonomous_neural_head import original_gate, original_packet, owned
from src.runners.task042_shared import write_json
from src.solvers.actual_loss_block_descent import (
    FixedHeadObjective, actual_loss, armijo_accept, qualified_audit, resolution,
    trial_steps,
)
from src.solvers.actual_loss_window import guard_worker_parent, journal, snapshot
from src.solvers.neural_fe_action_packet import array_hash, file_hash


class Stage:
    def __init__(self, specification, directory):
        self.specification, self.directory = specification, directory
        self.plan, self.design, self.material, self.fe = plan_and_operator()
        self.packet = original_packet(self.fe)
        self.name = specification.derived["stage"].split("-", 1)[1]
        self.artifact = V12_ROOT / directory.name
        self.artifact.mkdir(parents=True, exist_ok=False)
        self.began = time.perf_counter()
        self.source = (directory / "source_sha.txt").read_text().strip()
        self.counts = dict(loss_forward=0, VJP=0, PA_builds=0, thin_head_resolves=0,
                           original_audits=0, FD_points=0, trials=0,
                           accepted_hidden=0, head_proposals=0)
        self.carry_actions = 0
        if self.name in {"DESCENT", "VERIFY"}:
            previous, _ = read_result("ROUND")
            self.carry_actions = previous["all_batch_equivalent_actions"]
            for key, value in previous["budget_counts"].items():
                self.counts[key] += value
        if self.name == "VERIFY":
            previous, _ = read_result("DESCENT")
            self.carry_actions = previous["all_batch_equivalent_actions"]
            self.counts = previous["budget_counts"].copy()
        self.meta = dict(source_sha=self.source, input_sha256=specification.input_sha256,
                         plan_sha256=file_hash(PLAN_PATH), physical_identity=self.fe["physical"],
                         operator_packet=self.fe["packet"], complete_ports=40,
                         shared_workstation=True, reference_arrays_read=False,
                         global_p4_factor_constructed=False, global_S_or_CSR_constructed=False,
                         hidden_fallback=False)

    def sample(self):
        path = self.directory / "supervision/resources.jsonl"
        with path.open("rb") as stream:
            stream.seek(max(0, path.stat().st_size - 65536))
            lines = stream.read().splitlines()
        for line in reversed(lines):
            try:
                sample = json.loads(line)
            except json.JSONDecodeError:
                continue
            if time.time_ns() - sample["timestamp_ns"] > 5_000_000_000 or sample["swap_bytes"]:
                raise RuntimeError("own supervision stale or own swap nonzero")
            if sample["rss_bytes"] >= 12 * 2**30:
                raise RuntimeError("own RSS warning reached")
            if snapshot()["heavy_remaining_seconds"] <= 0:
                raise RuntimeError("V12 heavy stop reached")
            return sample
        raise RuntimeError("no fresh own process-tree resource sample")

    def guard(self, *, extra_actions=0, large=False):
        self.sample()
        if snapshot()["heavy_remaining_seconds"] < (300 if large else 10):
            raise RuntimeError("V12 heavy deadline/cleanup margin")
        limits = dict(loss_forward=900, VJP=240, PA_builds=4, thin_head_resolves=8,
                      original_audits=100)
        for key, bound in limits.items():
            if self.counts[key] > bound:
                raise RuntimeError(f"V12 {key} budget exceeded")
        if self.carry_actions + self.packet.counts["S"] + self.packet.counts["SH"] + extra_actions > 15000:
            raise RuntimeError("V12 15000 original equivalent action budget")

    def event(self, name, **fields):
        sample = self.sample()
        row = journal(name, source_sha=self.source, stage=self.name,
                      rss_bytes=sample["rss_bytes"], counts=self.counts.copy(), **fields)
        print(json.dumps(row, ensure_ascii=False), flush=True)
        return row

    def audit(self, z):
        self.guard()
        if self.counts["original_audits"] >= 100:
            raise RuntimeError("V12 100 original audit budget")
        result = self.packet.audit(z)
        self.counts["original_audits"] += 1
        return result

    def freeze(self, name, hidden, gamma, point, history=()):
        from src.solvers.neural_trace_checks import parameters

        path = self.artifact / (name + ".npz")
        np.savez(path, z=point["z"], hidden=hidden, gamma=gamma,
                 port=point["port_coefficients"], network_parameters=parameters(self.model),
                 history_s=np.array([s for s, _ in history]).reshape(-1, 8576),
                 history_y=np.array([y for _, y in history]).reshape(-1, 8576))
        return dict(path=str(path), sha256=file_hash(path), z_sha256=array_hash(point["z"]),
                    hidden_sha256=array_hash(hidden), gamma_sha256=array_hash(gamma),
                    port_sha256=array_hash(point["port_coefficients"]),
                    network_parameters_sha256=array_hash(parameters(self.model)))

    def finish(self, result):
        result.update(self.meta, status=result.get("status", "FINISHED"),
                      action_counts=self.packet.counts.copy(), action_costs_seconds=self.packet.costs.copy(),
                      all_batch_equivalent_actions=self.carry_actions + self.packet.counts["S"] + self.packet.counts["SH"],
                      budget_counts=self.counts.copy(), worker_wall_seconds=time.perf_counter() - self.began)
        path = self.artifact / "stage_result.json"
        write_json(path, result)
        publish(self.name, path)
        write_json(self.directory / "artifact_index.json", dict(path=str(path), sha256=file_hash(path)))
        self.event("stage_artifact_frozen", status=result["status"], result=str(path))


def _guard_pure_child():
    expected=int(os.environ["TASK042_NUMERICAL_PARENT_PID"])
    library=ctypes.CDLL(None,use_errno=True)
    if library.prctl(1,signal.SIGTERM,0,0,0) or os.getppid()!=expected:
        raise RuntimeError("V12 pure numerical child lost own ML parent")
    if snapshot()["heavy_remaining_seconds"]<=0:
        raise RuntimeError("V12 heavy deadline reached in pure child")


def _pure_blas_threads():
    """Read actual OpenBLAS pools without importing FE/MPI into a QR child."""
    pools=[]
    for path in sorted({line.split()[-1] for line in Path("/proc/self/maps").read_text().splitlines()
                        if "openblas" in line and line.split()[-1].startswith("/")}):
        library=ctypes.CDLL(path)
        for name in ("openblas_get_num_threads","openblas_get_num_threads64_",
                     "scipy_openblas_get_num_threads","scipy_openblas_get_num_threads64_"):
            if hasattr(library,name):
                function=getattr(library,name); function.restype=ctypes.c_int
                count=function()
                if count!=1:
                    raise RuntimeError("V12 pure BLAS pool is not single-threaded")
                pools.append(dict(path=path,function=name,threads=count))
                break
    if not pools:
        raise RuntimeError("V12 pure BLAS thread probe unavailable")
    return pools


def round_qr_child(work):
    """Original nonpivoting Householder P=ZR, isolated from ML/Torch."""
    _guard_pure_child()
    from scipy.linalg import qr

    request=json.loads((work/"request.json").read_text())
    if file_hash(work/"P.npy")!=request["P_sha256"]:
        raise ValueError("T1 retained P changed before QR")
    P=np.load(work/"P.npy",mmap_mode="r",allow_pickle=False)
    begun=time.perf_counter()
    Z,R=qr(P,mode="economic",pivoting=False,check_finite=False)
    reassembly=float(np.linalg.norm(P-Z@R)/max(np.linalg.norm(P),1e-300))
    if reassembly>1e-10:
        raise ValueError("T1 P QR reconstruction failed")
    np.save(work/"Z.npy",Z)
    np.save(work/"R.npy",R)
    write_json(work/"child_result.json",dict(status="PASS",threads=_pure_blas_threads(),
               P_sha256=request["P_sha256"],Z_sha256=file_hash(work/"Z.npy"),
               R_sha256=file_hash(work/"R.npy"),P_reassembly=reassembly,
               child_wall_seconds=time.perf_counter()-begun,no_new_A_columns=True))


def head_child(work):
    """Fresh original-action A=barS Z and GELSD; pure SciPy child, no Torch/ref."""
    _guard_pure_child()
    from src.solvers.stable_head_varpro import StableBasis

    request=json.loads((work/"request.json").read_text())
    if file_hash(work/"P.npy")!=request["P_sha256"]:
        raise ValueError("V12 head P changed before pure child")
    _,_,_,fe=plan_and_operator()
    packet=original_packet(fe)
    port_result,_=__import__("src.io.autonomous_neural_head",fromlist=["read_result"]).read_result("A")
    columns=np.load(owned(port_result["original_port_columns"],V11_ROOT.parent/"v10"),mmap_mode="r")
    P=np.load(work/"P.npy",mmap_mode="r",allow_pickle=False)
    begun=time.perf_counter()
    try:
        basis=StableBasis(packet,P,columns,
                          heartbeat=lambda event,**fields: print(json.dumps(dict(event=event,**fields)),flush=True))
        solution=basis.solve(packet.a["b"])
        gamma=solution.pop("gamma")
        np.save(work/"gamma.npy",gamma)
        status="PASS"
    except Exception:
        status="FAILED"
        raise
    finally:
        record=dict(status=status,threads=_pure_blas_threads(),
                    P_sha256=request["P_sha256"],
                    action_counts=packet.counts.copy(),action_costs_seconds=packet.costs.copy(),
                    child_wall_seconds=time.perf_counter()-begun)
        if status=="PASS":
            record.update(solution={key:value for key,value in solution.items()
                                    if not isinstance(value,np.ndarray)},
                          gamma_sha256=array_hash(gamma),
                          rank_P=basis.P_rank,P_singular_range=basis.P_singular_range,
                          P_reassembly=basis.P_reassembly,Z_orthogonality=basis.Z_orthogonality,
                          H_condition=basis.ports.cond_H,basis_times=basis.times,
                          P_payload_bytes=P.nbytes,A_payload_bytes=basis.A.nbytes,
                          Z_payload_bytes=basis.Z.nbytes,U_payload_bytes=basis.U.nbytes,
                          no_global_S_or_factor=True)
        write_json(work/"child_result.json",record)


def prior_state(stage):
    previous, _ = read_v11("REPLAY")
    record = previous["baseline_state"]
    path = owned(record, V11_ROOT)
    with np.load(path, allow_pickle=False) as saved:
        arrays = {key: np.array(saved[key]) for key in saved.files}
    if array_hash(arrays["z"]) != record["z_sha256"]:
        raise ValueError("V11 corrected physical z hash differs")
    for key in ("hidden", "gamma", "port", "network_parameters"):
        if array_hash(arrays[key]) != record["arrays"][key]["sha256"]:
            raise ValueError("V11 corrected physical " + key + " hash differs")
    if previous["operator_packet"] != stage.fe["packet"] or previous["physical_identity"] != stage.fe["physical"]:
        raise ValueError("V11 corrected state operator/physical identity differs")
    return arrays, record, previous


def make_experiment(stage):
    from src.runners.neural_fe_continuation import read_moments
    from src.solvers.neural_trace_batched import BatchedMoments
    from src.solvers.neural_trace_checks import assign, parameters
    from src.solvers.neural_trace_torch import NeuralTrace, qualify_threads
    from src.solvers.stable_head_varpro import PortBlocks

    threads = qualify_threads()
    arrays, record, previous = prior_state(stage)
    port_result, _ = __import__("src.io.autonomous_neural_head", fromlist=["read_result"]).read_result("A")
    columns_path = owned(port_result["original_port_columns"], V11_ROOT.parent / "v10")
    ports = PortBlocks(stage.packet, np.load(columns_path, mmap_mode="r", allow_pickle=False))
    moments, moment_identity = read_moments()
    model = NeuralTrace(stage.design["geometry"]["bounds_nm"], 0.7, seed=420906)
    assign(model, arrays["network_parameters"])
    if array_hash(parameters(model)) != array_hash(arrays["network_parameters"]):
        raise ValueError("V11 actual network parameters did not restore")
    cache = BatchedMoments(model, moments, resource_sample=stage.sample())
    objective = FixedHeadObjective(stage.packet, ports, model, cache, stage.packet.a["b"])
    stage.model = model
    return objective, moments, arrays, record, previous, threads, moment_identity


def public(point):
    return {key: value for key, value in point.items()
            if key not in {"z", "trace", "bar_residual", "port_coefficients"}}


def run_round(stage):
    """T1: reuse old P/A; no new 1560-column construction or fresh RHS."""
    from src.solvers.stable_head_varpro import homogeneous_recovery_pair

    objective, _, initial, record, previous, threads, moment = make_experiment(stage)
    main, main_path = read_v11("MAIN")
    prior = main_path.parent / "initial"
    replay_path = Path(previous["baseline_state"]["path"]).parent / "same_basis_correction"
    result = dict(status="PARTIAL", threads=threads, moments=moment, prior_state=record,
                  previous_V11_gate=dict(S1=previous["S1_gate"], S2=previous["S2_gate"]),
                  rows={}, T1_limit_seconds=600, T1_original_action_limit=32,
                  reference_arrays_read=False, new_A_columns=0)
    began = time.perf_counter()
    try:
        for name in ("P.npy", "A.npy"):
            if file_hash(prior / name) != file_hash(replay_path / name):
                raise ValueError("V11 retained P/A identity mismatch")
        P = np.load(prior / "P.npy", mmap_mode="r", allow_pickle=False)
        A = np.load(prior / "A.npy", mmap_mode="r", allow_pickle=False)
        qr_work=stage.artifact/"T1_same_householder_QR"
        qr_work.mkdir()
        os.symlink((prior/"P.npy").resolve(),qr_work/"P.npy")
        write_json(qr_work/"request.json",dict(P_sha256=file_hash(prior/"P.npy"),
                   old_A_sha256=file_hash(prior/"A.npy"),no_A_rebuild=True))
        child=subprocess.run(["bash","-c",
            'source scripts/activate_task042.sh pure; exec python -m src.runners.actual_loss_block_descent --round-qr "$1"',
            "task042-v12-QR",str(qr_work)],check=False,
            env=dict(os.environ,TASK042_NUMERICAL_PARENT_PID=str(os.getpid())))
        if child.returncode:
            raise RuntimeError("T1 qualified pure QR child failed")
        result["same_P_QR_child"]=json.loads((qr_work/"child_result.json").read_text())
        Z=np.load(qr_work/"Z.npy",mmap_mode="r",allow_pickle=False)
        R=np.load(qr_work/"R.npy",mmap_mode="r",allow_pickle=False)
        with np.load(replay_path / "solutions.npz", allow_pickle=False) as saved, \
             np.load(replay_path / "rhs.npz", allow_pickle=False) as rhs:
            for name in ("M2", "physical"):
                stage.guard()
                if time.perf_counter() - began >= 600 or stage.packet.counts["S"] >= 32:
                    raise RuntimeError("T1 bounded action/wall limit reached")
                gamma = np.array(saved[name + "_gamma"])
                right = np.array(rhs[name])
                if name == "physical" and array_hash(right) != array_hash(stage.packet.a["b"]):
                    raise ValueError("physical RHS changed in V11 replay")
                c_diag = R @ gamma
                tZ = Z @ c_diag
                tP = P @ gamma
                objective.assign(initial["hidden"], gamma)
                tN = objective.cache.forward(objective.model)
                rN = actual_loss(stage.packet, objective.ports, tN, right)
                rP = actual_loss(stage.packet, objective.ports, tP, right)
                rZ = actual_loss(stage.packet, objective.ports, tZ, right)
                rhat = objective.ports.reduced_rhs(right) - A @ c_diag
                scale = max(np.linalg.norm(right), 1e-300)
                d1 = rN["bar_residual"] - rP["bar_residual"]
                d2 = rP["bar_residual"] - rZ["bar_residual"]
                d3 = rZ["bar_residual"] - rhat
                closure = d1 + d2 + d3 - (rN["bar_residual"] - rhat)
                result["rows"][name] = dict(
                    rhs_sha256=array_hash(right), gamma_sha256=array_hash(gamma),
                    c_coordinate="R_gamma_new_diagnostic", c_sha256=array_hash(c_diag),
                    actual_vs_Pgamma_trace_relative=float(np.linalg.norm(tN-tP)/max(np.linalg.norm(tN), 1e-300)),
                    Pgamma_vs_Zc_trace_relative=float(np.linalg.norm(tP-tZ)/max(np.linalg.norm(tP), 1e-300)),
                    residual_norms=dict(network_writeback=float(np.linalg.norm(d1)/scale),
                                        QR_triangular=float(np.linalg.norm(d2)/scale),
                                        original_action_vs_thin=float(np.linalg.norm(d3)/scale),
                                        total=float(np.linalg.norm(rN["bar_residual"]-rhat)/scale),
                                        vector_reassembly=float(np.linalg.norm(closure)/scale)),
                    homogeneous_recovery_N_vs_P=homogeneous_recovery_pair(stage.packet, rN["z"], rP["z"]),
                    relative_original_rhs_residual=rN["full_residual_relative"],
                    reference_arrays_read=False)
                stage.event("T1_case_done", case=name, norms=result["rows"][name]["residual_norms"])
        result["status"] = "COMPLETE"
    except (FileNotFoundError, OSError, ValueError, RuntimeError) as error:
        result["status"] = "PARTIAL"
        result["partial_reason"] = type(error).__name__ + ": " + str(error)
    result["T1_wall_seconds"] = time.perf_counter() - began
    result["T1_original_actions"] = stage.packet.counts["S"] + stage.packet.counts["SH"]
    return result


def evaluate(stage, objective, hidden, gamma, *, fd=False, trial=False):
    stage.guard()
    if stage.counts["loss_forward"] >= 900:
        raise RuntimeError("V12 900 actual-loss forward budget")
    if fd and stage.counts["FD_points"] >= 42:
        raise RuntimeError("V12 bounded FD perturbation budget")
    stage.counts["loss_forward"] += 1
    if fd:
        stage.counts["FD_points"] += 1
    if trial:
        stage.counts["trials"] += 1
    result = objective.evaluate(hidden, gamma)
    stage.guard()
    return result


def evaluate_gradient(stage, objective, point):
    stage.guard()
    if stage.counts["VJP"] >= 240:
        raise RuntimeError("V12 240 VJP budget")
    stage.counts["VJP"] += 1
    gradient, info = objective.gradient(point)
    stage.guard()
    return gradient, info


def value_resolution(stage, objective, moments, hidden, gamma):
    """Two batch8 plus the unchanged, full q15 batch1 path at one point."""
    from src.solvers.neural_trace_torch import packet_forward

    first = evaluate(stage, objective, hidden, gamma)
    second = evaluate(stage, objective, hidden, gamma)
    objective.assign(hidden, gamma)
    stage.counts["loss_forward"] += 1
    trace_one = packet_forward(objective.model, moments)
    one = actual_loss(stage.packet, objective.ports, trace_one, objective.rhs)
    delta = resolution([first["loss"], second["loss"], one["loss"]])
    result = dict(batch8_first=first["loss"], batch8_repeat=second["loss"],
                  batch1=one["loss"], delta_eval=delta,
                  batch1_batch8_trace_relative=float(np.linalg.norm(trace_one-first["trace"])/
                                                       max(np.linalg.norm(first["trace"]), 1e-300)),
                  function_value_resolved=delta <= 1e-6 * max(1.0, first["loss"]),
                  gamma_sha256=array_hash(gamma), port_relative=first["port_relative"])
    objective.assign(hidden, gamma)
    return first, result


def real_fixed_head_fd(stage, objective, hidden, gamma, gradient, delta_eval):
    """Three preregistered nonzero directions; every perturbed point recloses ports."""
    directions = []
    for seed in (421201, 421202):
        value = np.random.default_rng(seed).standard_normal(8576)
        directions.append((str(seed), value / np.linalg.norm(value)))
    if np.linalg.norm(gradient) > 1e-14:
        directions.append(("analytic_gradient", gradient / np.linalg.norm(gradient)))
    else:
        value = np.random.default_rng(421203).standard_normal(8576)
        directions.append(("421203_nearzero_fallback", value / np.linalg.norm(value)))
    rows = []
    start_points = stage.counts["FD_points"]
    for label, direction in directions:
        analytic = float(np.dot(gradient, direction))
        estimates = []
        for h in (1e-3, 1e-4, 1e-5, 1e-6, 1e-7):
            if stage.counts["FD_points"] - start_points >= 30:
                raise RuntimeError("T2 thirty perturbed forward limit")
            plus = evaluate(stage, objective, hidden + h * direction, gamma, fd=True)
            minus = evaluate(stage, objective, hidden - h * direction, gamma, fd=True)
            slope = (plus["loss"] - minus["loss"]) / (2 * h)
            signal_ratio = abs(plus["loss"] - minus["loss"]) / max(delta_eval, 1e-300)
            relative = abs(slope - analytic) / max(abs(analytic), abs(slope), 1e-12)
            estimates.append(dict(h=h, slope=slope, analytic=analytic,
                                  relative_error=relative, signal_over_delta=signal_ratio))
            if len(estimates) >= 2:
                prev = estimates[-2]
                trend = abs(slope-prev["slope"]) / max(abs(slope), abs(prev["slope"]), 1e-12)
                if (relative <= 1e-5 and prev["relative_error"] <= 1e-5
                        and trend <= 1e-5 and signal_ratio >= 10 and prev["signal_over_delta"] >= 10):
                    break
        stable = False
        for left, right in zip(estimates, estimates[1:]):
            trend = abs(left["slope"]-right["slope"]) / max(abs(left["slope"]), abs(right["slope"]), 1e-12)
            if (left["relative_error"] <= 1e-5 and right["relative_error"] <= 1e-5
                    and trend <= 1e-5 and left["signal_over_delta"] >= 10
                    and right["signal_over_delta"] >= 10):
                stable = True
                break
        if abs(analytic) <= 1e-10:
            stable = stable or any(abs(row["slope"]-analytic) <= 1e-10 and
                                   row["signal_over_delta"] >= 10 for row in estimates)
        rows.append(dict(direction=label, analytic=analytic, estimates=estimates,
                         nonzero=bool(abs(analytic) > 1e-14), qualified=stable))
        stage.event("T2_FD_direction", direction=label, qualified=stable,
                    best_relative=min(row["relative_error"] for row in estimates))
    objective.assign(hidden, gamma)
    return dict(directions=rows, qualified=all(row["qualified"] for row in rows),
                perturbation_points=stage.counts["FD_points"]-start_points,
                fixed_gamma_all_points=True, head_resolves=0, PA_builds=0,
                derivative_kind="FIXED_HEAD_PARTIAL_GRADIENT")


def row_for_state(stage, name, hidden, gamma, point, *, delta_eval, accepted_hidden,
                  head_refreshed=False, history=()):
    objective = stage.objective
    objective.assign(hidden, gamma)
    saved = stage.freeze(name, hidden, gamma, point, history)
    audit = stage.audit(point["z"])
    return dict(name=name, state=saved, loss=point["loss"],
                point=public(point), audit=audit, original_gate=original_gate(audit),
                hidden_updates=accepted_hidden, head_refreshed=head_refreshed,
                gamma_frozen_within_block=True, delta_eval=delta_eval,
                derivative_kind="FIXED_HEAD_PARTIAL_GRADIENT")


def head_proposal(stage, objective, hidden, old_gamma, old_point, delta_eval, block):
    """One fresh stable thin head after a changed hidden state; actual-loss acceptance."""
    from src.solvers.neural_linear_head_torch import build_head_mapping

    stage.guard(extra_actions=1564, large=True)
    if stage.counts["PA_builds"] >= 4 or stage.counts["thin_head_resolves"] >= 8:
        return old_gamma, old_point, dict(status="BUDGET_NO_HEAD_PROPOSAL")
    stage.counts["PA_builds"] += 1
    stage.counts["head_proposals"] += 1
    work = stage.artifact / f"block_{block}_head"
    work.mkdir()
    objective.assign(hidden, old_gamma)
    P, mapping = build_head_mapping(objective.model, objective.cache, work / "P.npy")
    P_bytes=P.nbytes
    del P
    gc.collect()
    write_json(work/"request.json",dict(P_sha256=file_hash(work/"P.npy"),
               physical_rhs_sha256=array_hash(objective.rhs),block=block))
    child=subprocess.run(["bash","-c",
        'source scripts/activate_task042.sh pure; exec python -m src.runners.actual_loss_block_descent --head "$1"',
        "task042-v12-head",str(work)],check=False,
        env=dict(os.environ,TASK042_NUMERICAL_PARENT_PID=str(os.getpid())))
    child_record=json.loads((work/"child_result.json").read_text()) if (work/"child_result.json").exists() else {}
    stage.carry_actions+=child_record.get("action_counts",{}).get("S",0)+child_record.get("action_counts",{}).get("SH",0)
    stage.guard()
    if child.returncode or child_record.get("status")!="PASS":
        raise ValueError("V12 pure stable-head child failed; retained child_result")
    stage.counts["thin_head_resolves"] += 1
    proposal=child_record["solution"]
    new_gamma=np.load(work/"gamma.npy",allow_pickle=False)
    if array_hash(new_gamma)!=child_record["gamma_sha256"]:
        raise ValueError("pure child gamma hash mismatch")
    record = dict(status="REJECTED", block=block, mapping=mapping,
                  P_sha256=file_hash(work / "P.npy"),
                  rank_P=child_record["rank_P"], rank_A=proposal["rank_A"],
                  numerical_full_column_rank=proposal["numerical_full_column_rank"],
                  old_head_gate_1e8=proposal["actual_vs_thin_residual_fixed_rhs"] <= 1e-8,
                  original_head_gate_retained_separately=True,
                  gamma_old_norm=float(np.linalg.norm(old_gamma)),
                  gamma_new_norm=float(np.linalg.norm(new_gamma)),
                  old_actual_loss=old_point["loss"],
                  isolated_pure_child=child_record,
                  P_payload_bytes=P_bytes,
                  no_global_S_or_factor=True)
    if np.linalg.norm(new_gamma) > 10 * max(1.0, stage.initial_gamma_norm):
        record["status"] = "COEFFICIENT_GROWTH_GUARD"
        objective.assign(hidden, old_gamma)
        return old_gamma, old_point, record
    new_point = evaluate(stage, objective, hidden, new_gamma)
    new_audit = stage.audit(new_point["z"])
    old_native = stage.audit(old_point["z"])["native_relative"]
    margin = max(1e-12, 20 * delta_eval)
    accepted = (new_point["loss"] <= old_point["loss"] - margin
                and new_audit["native_relative"] <= 1.05 * old_native
                and qualified_audit(new_audit) and new_point["port_relative"] <= 1e-6)
    record.update(new_actual_loss=new_point["loss"], new_native=new_audit["native_relative"],
                  old_native=old_native, margin=margin,
                  new_gamma_sha256=array_hash(new_gamma), accepted=bool(accepted),
                  status="ACCEPTED" if accepted else "REJECTED_ACTUAL_LOSS_OR_AUDIT")
    if not accepted:
        objective.assign(hidden, old_gamma)
        return old_gamma, old_point, record
    return new_gamma, new_point, record


def function_only_poll(stage, objective, hidden, gamma, point, gradient, delta_eval):
    directions = []
    if gradient is not None and np.isfinite(gradient).all() and np.linalg.norm(gradient) > 0:
        directions.append(("negative_unqualified_gradient", -gradient/np.linalg.norm(gradient)))
    else:
        value = np.random.default_rng(421204).standard_normal(8576)
        directions.append(("421204", value/np.linalg.norm(value)))
    value = np.random.default_rng(421205).standard_normal(8576)
    directions.append(("421205", value/np.linalg.norm(value)))
    candidates = []
    size = max(1.0, np.linalg.norm(hidden))
    for label, direction in directions:
        for sign in (1, -1):
            for h in (1e-5, 1e-6):
                trial_hidden = hidden + sign*h*size*direction
                trial = evaluate(stage, objective, trial_hidden, gamma, trial=True)
                candidates.append((trial["loss"], trial_hidden, trial,
                                   dict(direction=label, sign=sign, relative_step=h,
                                        actual_loss=trial["loss"])))
    best_loss, best_hidden, best_point, best_row = min(candidates, key=lambda row: row[0])
    repeated = evaluate(stage, objective, best_hidden, gamma)
    native_before = stage.audit(point["z"])["native_relative"]
    audit = stage.audit(repeated["z"])
    margin = max(1e-12, 20*delta_eval, 1e-4*point["loss"])
    accepted = (best_loss <= point["loss"]-margin and
                abs(best_loss-repeated["loss"]) <= delta_eval and
                audit["native_relative"] <= 1.05*native_before and
                qualified_audit(audit) and repeated["port_relative"] <= 1e-6)
    record = dict(status="ACCEPTED" if accepted else "NEGATIVE", algorithm="FUNCTION_ONLY_POLL",
                  trial_count=8, trials=[row[3] for row in candidates], best=best_row,
                  repeated_loss=repeated["loss"], resolution=delta_eval, margin=margin,
                  native_before=native_before, native_best=audit["native_relative"],
                  accepted=bool(accepted))
    if accepted:
        stage.counts["accepted_hidden"] += 1
        return best_hidden, gamma, repeated, record
    objective.assign(hidden, gamma)
    return hidden, gamma, point, record


def synthetic_fixed_head_check():
    """Complex non-Hermitian, nonstationary head and nonzero port witness."""
    K = np.array([[2+1j, .4-.2j], [.1+.3j, 1-.7j]])
    C = np.array([[.3+.2j], [-.1+.4j]])
    F = np.array([[.2-.5j, .6+.1j]])
    H = np.array([[1.7+.2j]])
    b = np.array([.8+.3j, -.4+.2j, .2-.6j])
    gamma = 1.3-.7j  # deliberately not re-solved as psi moves
    def value(psi):
        t = gamma*np.array([psi+1j*psi**2, 1+.2j*psi])
        alpha = np.linalg.solve(H, b[2:]-F@t)
        r = b[:2]-K@t-C@alpha
        return float(np.vdot(r, r).real/(2*np.vdot(b,b).real)), r, alpha
    psi=.31
    actual, r, alpha=value(psi)
    dt=gamma*np.array([1+2j*psi, .2j])
    barS=K-C@np.linalg.solve(H,F)
    derivative=-float(np.vdot(r,barS@dt).real/np.vdot(b,b).real)
    h=1e-6
    fd=(value(psi+h)[0]-value(psi-h)[0])/(2*h)
    relative=abs(fd-derivative)/max(abs(fd),abs(derivative),1e-300)
    return dict(non_Hermitian=bool(np.linalg.norm(barS-barS.conj().T)>0.1),
                nonzero_port=bool(np.linalg.norm(alpha)>0.1),
                nonzero_fixed_gamma=bool(abs(gamma)>0),
                nonoptimal_head_by_design=True, actual_loss=actual,
                analytic=derivative, centered_FD=fd, relative=relative,
                qualified=bool(relative<=1e-7))


def post_head_direction_fd(stage, objective, hidden, gamma, point, delta_eval):
    gradient, _ = evaluate_gradient(stage, objective, point)
    if np.linalg.norm(gradient) <= 1e-14:
        return dict(qualified=False, reason="zero gradient cannot supply nonzero post-head direction")
    direction=gradient/np.linalg.norm(gradient)
    rows=[]
    for h in (1e-4, 1e-5):
        plus=evaluate(stage,objective,hidden+h*direction,gamma,fd=True)
        minus=evaluate(stage,objective,hidden-h*direction,gamma,fd=True)
        fd=(plus["loss"]-minus["loss"])/(2*h)
        actual=float(np.dot(gradient,direction))
        rows.append(dict(h=h, centered=fd, analytic=actual,
                         relative=abs(fd-actual)/max(abs(fd),abs(actual),1e-12),
                         signal_over_delta=abs(plus["loss"]-minus["loss"])/max(delta_eval,1e-300)))
    objective.assign(hidden,gamma)
    trend=abs(rows[0]["centered"]-rows[1]["centered"])/max(abs(rows[0]["centered"]),abs(rows[1]["centered"]),1e-12)
    passed=all(row["relative"]<=1e-5 and row["signal_over_delta"]>=10 for row in rows) and trend<=1e-5
    return dict(qualified=bool(passed), rows=rows, adjacent_trend=trend,
                derivative_kind="FIXED_HEAD_PARTIAL_GRADIENT")


def run_descent(stage):
    """T2 fixed-head gradient, T3 bounded hidden blocks, or one F poll."""
    from src.solvers.stable_head_varpro import lbfgs_direction

    objective, moments, initial, prior_record, prior, threads, moment_identity = make_experiment(stage)
    stage.objective = objective
    stage.initial_gamma_norm=float(np.linalg.norm(initial["gamma"]))
    hidden=initial["hidden"].copy()
    gamma=initial["gamma"].copy()
    result=dict(status="STARTED", initial_V11_corrected_physical_state=prior_record,
                old_M2_1e8_gate="FAIL_UNCHANGED", old_actual_head_1e8_gate="FAIL_UNCHANGED",
                derivative_kind="FIXED_HEAD_PARTIAL_GRADIENT", exact_VarPro_qualified=False,
                threads=threads, moments=moment_identity, candidate="ACTUAL-LOSS-PORT-CLOSED-BLOCK-DESCENT",
                reference_arrays_read=False, states=[], block_rows=[], head_proposals=[],
                finite_difference=None, function_only_poll=None,
                precommitted_source_sha=stage.source, full_PA_builds_this_stage=0)
    baseline, repeat=value_resolution(stage,objective,moments,hidden,gamma)
    initial_z_error=float(np.linalg.norm(baseline["z"]-initial["z"])/max(np.linalg.norm(initial["z"]),1e-300))
    if initial_z_error>1e-8:
        raise ValueError("V11 corrected physical network state did not regenerate")
    audit=stage.audit(baseline["z"])
    if not qualified_audit(audit):
        raise ValueError("initial original recovery/port/identity self-check failed")
    delta=repeat["delta_eval"]
    result.update(repeated_loss=repeat, initial_z_regeneration_relative=initial_z_error,
                  initial_original_audit=audit, initial_loss=baseline["loss"])
    result["states"].append(row_for_state(stage,"INITIAL_V11_CORRECTED",hidden,gamma,baseline,
                                          delta_eval=delta,accepted_hidden=0))
    stage.event("T2_initial_actual_loss", loss=baseline["loss"], delta_eval=delta,
                Schur=audit["schur_relative"], native=audit["native_relative"])
    if not repeat["function_value_resolved"]:
        result["status"]="FUNCTION_VALUE_UNRESOLVED"
        result["T2_gradient_qualified"]=False
        result["T3"]="NOT_RUN_UNRESOLVED_FUNCTION_VALUE"
        result["F"]="NOT_RUN_UNRESOLVED_FUNCTION_VALUE"
        return result
    synthetic=synthetic_fixed_head_check()
    result["synthetic_nonHermitian_fixed_head"]=synthetic
    if not synthetic["qualified"]:
        result["status"]="SYNTHETIC_GRADIENT_FAILED"
        result["T3"]="NOT_RUN_GRADIENT_UNTRUSTWORTHY"
        result["F"]="NOT_RUN_SYNTHETIC_FUNCTION_CHAIN_UNTRUSTWORTHY"
        return result
    objective.assign(hidden,gamma)
    gradient, gradient_meta=evaluate_gradient(stage,objective,baseline)
    result["initial_gradient"]={**gradient_meta,"sha256":array_hash(gradient)}
    fd=real_fixed_head_fd(stage,objective,hidden,gamma,gradient,delta)
    result["finite_difference"]=fd
    result["T2_gradient_qualified"]=bool(fd["qualified"])
    point=baseline
    accepted_total=0
    if not fd["qualified"]:
        stage.event("T2_gradient_not_qualified_enter_F", FD=fd)
        hidden,gamma,point,poll=function_only_poll(stage,objective,hidden,gamma,point,gradient,delta)
        result["function_only_poll"]=poll
        result["F"]="EXECUTED"
        result["T3"]="NOT_RUN_UNQUALIFIED_GRADIENT"
        if poll["accepted"]:
            accepted_total=1
            result["states"].append(row_for_state(stage,"F_ACCEPTED",hidden,gamma,point,
                                                  delta_eval=delta,accepted_hidden=1))
            proposed_gamma,proposed_point,proposal=head_proposal(stage,objective,hidden,gamma,point,delta,"F")
            result["head_proposals"].append(proposal)
            if proposal.get("accepted"):
                gamma,point=proposed_gamma,proposed_point
                result["states"].append(row_for_state(stage,"F_HEAD_ACCEPTED",hidden,gamma,point,
                                                      delta_eval=delta,accepted_hidden=1,head_refreshed=True))
        result["status"]="FUNCTION_ONLY_POLL_DONE"
        result["final_loss"]=point["loss"]
        return result

    result["F"]="NOT_RUN_GRADIENT_QUALIFIED"
    result["T3"]="STARTED"
    initial_loss=baseline["loss"]
    stop_reason="THREE_BLOCK_LIMIT"
    for block in range(1,4):
        stage.guard()
        history=[]
        block_start_loss=point["loss"]
        block_start_native=stage.audit(point["z"])["native_relative"]
        block_start_gamma_hash=array_hash(gamma)
        block_accepted=0
        rejected_all=False
        for step in range(1,21):
            stage.guard()
            objective.assign(hidden,gamma)
            direction=lbfgs_direction(gradient,history)
            gd=float(np.dot(gradient,direction))
            if gd>=0 or not np.isfinite(gd) or np.linalg.norm(direction)==0:
                stop_reason="STATIONARY_BUT_NOT_SOLVED"
                break
            chosen=None
            for index,alpha in enumerate(trial_steps(hidden,direction)):
                candidate_hidden=hidden+alpha*direction
                candidate=evaluate(stage,objective,candidate_hidden,gamma,trial=True)
                if candidate["gamma_hash"] != block_start_gamma_hash:
                    raise ValueError("gamma changed in fixed-head hidden trial")
                accepted=armijo_accept(point["loss"],candidate["loss"],alpha,gd,delta)
                if accepted and candidate["port_relative"]<=1e-6:
                    repeated=evaluate(stage,objective,candidate_hidden,gamma)
                    if abs(repeated["loss"]-candidate["loss"])<=delta:
                        candidate=repeated
                        chosen=(candidate_hidden,candidate,alpha,index)
                        break
                    delta=max(delta,abs(repeated["loss"]-candidate["loss"]))
            if chosen is None:
                rejected_all=True
                stop_reason="EIGHT_ARMIJO_TRIALS_REJECTED"
                stage.event("T3_all_steps_rejected",block=block,step=step,loss=point["loss"],delta_eval=delta)
                break
            new_hidden,new_point,alpha,index=chosen
            audited=stage.audit(new_point["z"])
            if not qualified_audit(audited):
                stop_reason="ACCEPTED_POINT_ORIGINAL_IDENTITY_FAILED"
                stage.event("T3_trial_identity_failed",block=block,step=step,alpha=alpha)
                break
            new_gradient,new_meta=evaluate_gradient(stage,objective,new_point)
            s=new_hidden-hidden
            y=new_gradient-gradient
            if np.dot(s,y)>1e-12*np.linalg.norm(s)*np.linalg.norm(y):
                history.append((s.copy(),y.copy()))
                history=history[-5:]
            hidden,point,gradient=new_hidden,new_point,new_gradient
            block_accepted+=1
            accepted_total+=1
            stage.counts["accepted_hidden"]+=1
            row=dict(block=block,step=step,alpha=alpha,backtracks=index,
                     derivative_kind="FIXED_HEAD_PARTIAL_GRADIENT",
                     hidden_sha256=array_hash(hidden),gamma_sha256=array_hash(gamma),
                     gamma_frozen=True,loss=point["loss"],native=audited["native_relative"],
                     Schur=audited["schur_relative"],port=audited["port_full_rhs_relative"],
                     delta_eval=delta,lbfgs_history=len(history),
                     actual_loss_accepted=True,head_refreshed=False,
                     action_counts=stage.packet.counts.copy())
            with (stage.artifact/"block_descent_progress.jsonl").open("a") as stream:
                stream.write(json.dumps(row,allow_nan=False)+"\n")
                stream.flush(); os.fsync(stream.fileno())
            stage.event("T3_hidden_accepted",**row)
            if block_accepted%5==0:
                stage.freeze(f"block_{block}_accepted_{block_accepted}_checkpoint",hidden,gamma,point,history)
            if original_gate(audited)["status"]=="ORIGINAL_EQUATION_PASS":
                stop_reason="ORIGINAL_EQUATION_GATE_REACHED"
                break
        if block_accepted:
            result["states"].append(row_for_state(stage,f"BLOCK_{block}_HIDDEN_END",hidden,gamma,point,
                                                   delta_eval=delta,accepted_hidden=accepted_total,history=history))
            try:
                proposal_gamma,proposal_point,proposal=head_proposal(stage,objective,hidden,gamma,point,delta,block)
            except ValueError as error:
                proposal_gamma,proposal_point=gamma,point
                proposal=dict(block=block,status="HEAD_NUMERICAL_GATE_FAILED",error=str(error),accepted=False)
            result["head_proposals"].append(proposal)
            if proposal.get("accepted"):
                gamma,point=proposal_gamma,proposal_point
                history=[]
                result["states"].append(row_for_state(stage,f"BLOCK_{block}_HEAD_ACCEPTED",hidden,gamma,point,
                                                       delta_eval=delta,accepted_hidden=accepted_total,
                                                       head_refreshed=True,history=history))
                point,repeat=value_resolution(stage,objective,moments,hidden,gamma)
                delta=repeat["delta_eval"]
                post_fd=post_head_direction_fd(stage,objective,hidden,gamma,point,delta)
                proposal["post_accept_fixed_head_FD"]=post_fd
                if not post_fd["qualified"]:
                    stop_reason="POST_HEAD_GRADIENT_NOT_QUALIFIED"
                else:
                    objective.assign(hidden,gamma)
                    gradient,_=evaluate_gradient(stage,objective,point)
        else:
            objective.assign(hidden,gamma)
        end_audit=stage.audit(point["z"])
        progress=(block_start_loss-point["loss"])/max(block_start_loss,1e-300)
        block_row=dict(block=block,accepted_hidden=block_accepted,start_loss=block_start_loss,
                       end_loss=point["loss"],relative_decrease=progress,
                       start_native=block_start_native,end_native=end_audit["native_relative"],
                       port=end_audit["port_full_rhs_relative"],
                       next_block_gate=bool(progress>=1e-4 and block_start_loss-point["loss"]>20*delta
                                            and end_audit["native_relative"]<=1.05*block_start_native
                                            and end_audit["port_full_rhs_relative"]<=1e-6),
                       rejected_all=rejected_all,head_proposed=bool(block_accepted))
        result["block_rows"].append(block_row)
        stage.event("T3_block_end",**block_row)
        if block==1 and block_accepted==0 and rejected_all:
            hidden,gamma,point,poll=function_only_poll(stage,objective,hidden,gamma,point,gradient,delta)
            result["function_only_poll"]=poll
            result["F"]="EXECUTED_AFTER_EIGHT_REJECTIONS"
            if poll["accepted"]:
                accepted_total+=1
                result["states"].append(row_for_state(stage,"F_ACCEPTED",hidden,gamma,point,
                                                      delta_eval=delta,accepted_hidden=accepted_total))
                proposal_gamma,proposal_point,proposal=head_proposal(stage,objective,hidden,gamma,point,delta,"F")
                result["head_proposals"].append(proposal)
                if proposal.get("accepted"):
                    gamma,point=proposal_gamma,proposal_point
                    result["states"].append(row_for_state(stage,"F_HEAD_ACCEPTED",hidden,gamma,point,
                                                           delta_eval=delta,accepted_hidden=accepted_total,
                                                           head_refreshed=True))
            stop_reason="FUNCTION_ONLY_POLL_AFTER_REJECTION"
            break
        if stop_reason in {"ORIGINAL_EQUATION_GATE_REACHED","POST_HEAD_GRADIENT_NOT_QUALIFIED",
                           "STATIONARY_BUT_NOT_SOLVED","ACCEPTED_POINT_ORIGINAL_IDENTITY_FAILED"}:
            break
        if not block_row["next_block_gate"]:
            stop_reason="BLOCK_PROGRESS_GATE_NOT_MET"
            break
        if block==2 and (initial_loss-point["loss"])/max(initial_loss,1e-300)<0.01:
            stop_reason="THIRD_BLOCK_ONE_PERCENT_GATE_NOT_MET"
            break
    result.update(status="SOLVER_QUEUE_FROZEN",T3="EXECUTED",accepted_hidden_updates=accepted_total,
                  accepted_head_proposals=sum(bool(row.get("accepted")) for row in result["head_proposals"]),
                  final_loss=point["loss"], final_gamma_sha256=array_hash(gamma),
                  final_hidden_sha256=array_hash(hidden),stop_reason=stop_reason,
                  full_PA_builds_this_stage=stage.counts["PA_builds"])
    return result


def run_verify(stage):
    """Independent post-freeze FE process; this is the only REF7 reader in V12."""
    from src.solvers.neural_fe_blind_reference import independent_physics
    from src.runners.task042_experiment import thread_qualification

    solver, solver_path=read_result("DESCENT")
    if solver["source_sha"]!=stage.source or solver["status"] not in {
        "SOLVER_QUEUE_FROZEN","FUNCTION_ONLY_POLL_DONE","FUNCTION_VALUE_UNRESOLVED",
        "SYNTHETIC_GRADIENT_FAILED"}:
        raise ValueError("V12 solver queue not cleanly frozen at same numerical source")
    if len(solver["states"])>8:
        raise ValueError("more than eight V12 frozen verification states")
    candidates={}
    identities={}
    for row in solver["states"]:
        record=row["state"]
        path=owned(record,V12_ROOT)
        with np.load(path,allow_pickle=False) as saved:
            z=np.array(saved["z"])
            if array_hash(np.array(saved["hidden"]))!=record["hidden_sha256"] or array_hash(np.array(saved["gamma"]))!=record["gamma_sha256"]:
                raise ValueError("V12 frozen hidden/head identity mismatch")
        if array_hash(z)!=record["z_sha256"]:
            raise ValueError("V12 frozen z identity mismatch")
        if record["z_sha256"] not in identities:
            candidates[row["name"]]=z
            identities[record["z_sha256"]]=row["name"]
    stage.event("T4_solver_queue_frozen_before_reference",states=list(candidates),
                descent_result_sha256=file_hash(solver_path))
    reference_record,_=read_index("blind_reference")
    reference_path=owned(reference_record["reference_state"],V7_ROOT)
    if file_hash(reference_path)!="a0610a5a55e7508196b17277e706595c33e4398ace82b245f70b656e6b9ed355":
        raise ValueError("saved REF7 p3 identity differs")
    with np.load(reference_path,allow_pickle=False) as saved:
        reference=np.array(saved["z"])
    stage.meta["reference_arrays_read"]=True
    physics,comparisons=independent_physics(stage.design,stage.packet,reference,candidates,stage.artifact)
    rows={}
    for name,z in candidates.items():
        item=physics["rows"][name]
        comparison=comparisons[name]
        audit=item["audit"]
        eq=original_gate(audit)
        fields={key:item[key] for key in (
            "full_FE_L2_relative","full_FE_scaled_curl_relative",
            "scattered_FE_L2_relative","scattered_scaled_curl_relative",
            "selected_E_relative","selected_H_relative")}
        same=eq["status"]=="ORIGINAL_EQUATION_PASS" and physics["reference_native_pass"]
        same &= all(np.isfinite(value) and value<=1e-4 for value in fields.values())
        same &= audit["independent_DOLFINx_total_native_relative"]<=1e-6
        same &= comparison["ordered_complex_ports_relative"]<=1e-4
        same &= all(value<=1e-5 for value in comparison["power_absolute_differences"].values())
        same &= comparison["max_channel_power_difference"]<=1e-6
        same &= comparison["energy_closure_absolute"]<=1e-5
        rows[name]=dict(status="SAME_DISCRETE_QUALIFIED" if same else "NOT_QUALIFIED",
                        original_equation_gate=eq,audit=audit,fields=fields,
                        ordered_complex_total_ports=item["ordered_complex_port_vector"],
                        ordered_complex_scattered_ports=item["ordered_complex_scattered_port_vector"],
                        selected_E=item["selected_E"],selected_H_code=item["selected_H_code"],
                        power=item["port"],volume_absorption=item["volume"],
                        comparison=comparison,official_candidate_results=bool(same))
    names=list(candidates)
    baseline=rows[names[0]]
    latest=rows[names[-1]]
    rho0=baseline["original_equation_gate"]["rho"]
    rho1=latest["original_equation_gate"]["rho"]
    f0=baseline["fields"]
    f1=latest["fields"]
    positive=(rho1<=0.5*rho0 and f1["scattered_FE_L2_relative"]<=0.5
              and f1["scattered_scaled_curl_relative"]<=0.5
              and f1["scattered_FE_L2_relative"]<=0.75*f0["scattered_FE_L2_relative"]
              and f1["scattered_scaled_curl_relative"]<=0.75*f0["scattered_scaled_curl_relative"])
    field_improved=(f1["scattered_FE_L2_relative"]<f0["scattered_FE_L2_relative"]
                    and f1["scattered_scaled_curl_relative"]<f0["scattered_scaled_curl_relative"])
    objective_only=solver.get("final_loss",solver["initial_loss"])<solver["initial_loss"] and not field_improved
    dispatch=("SAME_DISCRETE_QUALIFIED" if all(row["status"]=="SAME_DISCRETE_QUALIFIED" for row in rows.values())
              else "OBJECTIVE_ONLY_IMPROVEMENT" if objective_only
              else "BOUNDED_HIDDEN_UPDATE_NEGATIVE" if solver.get("accepted_hidden_updates",0)>0
              else "NO_QUALIFIED_HIDDEN_UPDATE")
    return dict(status=dispatch,threads=thread_qualification(),
                solver_result_path=str(solver_path),solver_result_sha256=file_hash(solver_path),
                reference_identity=reference_record["reference_state"],
                reference_only_after_solver_frozen=True,reference_feedback_to_solver=False,
                states_read=len(candidates),rows=rows,
                baseline_rho=rho0,final_rho=rho1,research_positive_signal=bool(positive),
                objective_only=bool(objective_only),full_channel_inventory=40,
                no_p4_enrichment=True,no_new_solve=True)


def main():
    if len(sys.argv)==3 and sys.argv[1]=="--round-qr":
        round_qr_child(Path(sys.argv[2]).resolve())
        return
    if len(sys.argv)==3 and sys.argv[1]=="--head":
        head_child(Path(sys.argv[2]).resolve())
        return
    if len(sys.argv)!=3:
        raise SystemExit("one V12 dat and one watchdog-owned output directory required")
    guard_worker_parent()
    specification=load_actual_loss(sys.argv[1])
    if specification is None:
        raise ValueError("V12 explicit dat loader rejected input")
    directory=Path(sys.argv[2]).resolve()
    source=subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip()
    manifest=json.loads((directory/"run_manifest.json").read_text())
    if source!=manifest["source_sha"]:
        raise RuntimeError("V12 runtime source changed after clean launch")
    stage=Stage(specification,directory)
    try:
        if stage.name=="ROUND":
            result=run_round(stage)
        elif stage.name=="DESCENT":
            result=run_descent(stage)
        elif stage.name=="VERIFY":
            result=run_verify(stage)
        else:
            raise ValueError("unknown V12 stage")
        stage.finish(result)
    except Exception as error:
        write_json(stage.artifact/"worker_failure.json",dict(
            error=type(error).__name__+": "+str(error),traceback=traceback.format_exc(limit=8),
            source_sha=stage.source,budget_counts=stage.counts,
            action_counts=stage.packet.counts,window=snapshot()))
        raise


if __name__=="__main__":
    main()
