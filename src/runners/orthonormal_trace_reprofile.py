"""Thin V14 stage adapter; ML feature generation and pure thin LS stay isolated."""

import gc
import json
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path

import numpy as np

from src.io.orthonormal_trace_reprofile import (
    PLAN_PATH, V14_ROOT, load_orthonormal_trace, publish, read_result,
)
from src.io.autonomous_neural_head import plan_and_operator
from src.io.task042_profile import ROOT
from src.runners.autonomous_neural_head import original_packet, owned
from src.runners.task042_shared import write_json
from src.solvers.neural_fe_action_packet import array_hash, file_hash
from src.solvers.orthonormal_trace_reprofile import FAMILY, LIMITS
from src.solvers.orthonormal_trace_window import guard_worker_parent, journal, snapshot


def own_sample(directory):
    path = directory/"supervision/resources.jsonl"
    with path.open("rb") as stream:
        stream.seek(max(0, path.stat().st_size-65536)); lines = stream.read().splitlines()
    for line in reversed(lines):
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if time.time_ns()-row["timestamp_ns"] > 5_000_000_000 or row["swap_bytes"]:
            raise RuntimeError("V14 own supervisor stale or own swap")
        if row["rss_bytes"] >= 12*2**30:
            raise RuntimeError("V14 own RSS warning; no new allocations")
        return row
    raise RuntimeError("V14 own resource sample absent")


def atomic_arrays(path, **arrays):
    temporary = path.with_suffix(".npz.partial")
    with temporary.open("wb") as stream:
        np.savez(stream, **arrays); stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, path)
    return dict(path=str(path), sha256=file_hash(path),
                **{key+"_sha256": array_hash(value) for key,value in arrays.items()})


class Stage:
    def __init__(self, specification, directory, *, io_module=None, window_module=None,
                 limits=None, action_limit=18000, family=FAMILY):
        if io_module is None:
            from src.io import orthonormal_trace_reprofile as io_module
        if window_module is None:
            from src.solvers import orthonormal_trace_window as window_module
        self.io, self.window = io_module, window_module
        self.limits = LIMITS if limits is None else limits
        self.action_limit, self.family = action_limit, family
        self.specification, self.directory = specification, directory
        self.name = specification.derived["stage"].split("-",1)[1]
        self.plan, self.design, self.material, self.fe = plan_and_operator()
        self.own_plan = json.loads(self.io.PLAN_PATH.read_text())
        self.packet = original_packet(self.fe)
        self.source = (directory/"source_sha.txt").read_text().strip()
        self.artifact = getattr(self.io,"ARTIFACT_ROOT",V14_ROOT)/directory.name; self.artifact.mkdir(parents=True)
        self.counts = dict.fromkeys(self.limits,0); self.carry_actions = 0
        self.began = time.perf_counter()
        previous = self.io.previous_name(self.name) if hasattr(self.io,"previous_name") else {"PROFILE":"DECODER", "VERIFY":"PROFILE"}.get(self.name)
        if previous:
            prior, _ = self.io.read_result(previous)
            self.counts = prior["budget_counts"].copy()
            self.carry_actions = prior["all_batch_equivalent_actions"]
        self.meta = dict(source_sha=self.source, input_sha256=specification.input_sha256,
            plan_sha256=file_hash(self.io.PLAN_PATH), physical_identity=self.fe["physical"],
            operator_packet=self.fe["packet"], decoder_family=self.family, complete_ports=40,
            shared_workstation=True, reference_arrays_read=False,
            global_p4_factor_constructed=False, global_S_or_CSR_constructed=False,
            normal_equations_constructed=False, hidden_fallback=False)

    def sample(self):
        return own_sample(self.directory)

    def guard(self, *, extra_actions=0, large=False):
        self.sample()
        if self.window.snapshot()["heavy_remaining_seconds"] < (300 if large else 10):
            raise RuntimeError("V14 deadline/cleanup margin reached")
        if self.carry_actions+self.packet.counts["S"]+self.packet.counts["SH"]+extra_actions > self.action_limit:
            raise RuntimeError("V14 original 18000 equivalent actions reached")

    def count(self,key,n=1):
        self.guard()
        if self.counts[key]+n > self.limits[key]:
            raise RuntimeError("V14 "+key+" budget reached")
        self.counts[key] += n

    def event(self,event,**fields):
        row = self.window.journal(event,stage=self.name,source_sha=self.source,counts=self.counts.copy(),
                      rss_bytes=self.sample()["rss_bytes"],**fields)
        print(json.dumps(row,ensure_ascii=False),flush=True)

    def audit(self,z):
        self.count("original_audits"); return self.packet.audit(z)

    def child(self,name,hidden,P_path,*,saved_A=None,reverse=False,witnesses=False):
        self.guard(extra_actions=1560,large=True)
        work = self.artifact/name; work.mkdir()
        np.save(work/"hidden.npy",hidden)
        request = dict(name=name,P_path=str(P_path),P_sha256=file_hash(P_path),
            hidden_sha256=array_hash(hidden),saved_A_path=str(saved_A) if saved_A else None,
            saved_A_sha256=file_hash(saved_A) if saved_A else None,
            reverse_rows=reverse,witnesses=witnesses,counts=self.counts,
            carry_actions=self.carry_actions+self.packet.counts["S"]+self.packet.counts["SH"],
            directory=str(self.directory),source_sha=self.source,plan_sha256=file_hash(PLAN_PATH),
            resident_upper_bytes=7600000000)
        write_json(work/"request.json",request)
        process = subprocess.run(["bash","-c",
            'source scripts/activate_task042.sh pure; exec python -m src.runners.orthonormal_trace_reprofile --basis-child "$1"',
            "task042-v14-pure",str(work)],check=False,
            env=dict(os.environ,TASK042_NUMERICAL_PARENT_PID=str(os.getpid())))
        record = json.loads((work/"child_result.json").read_text()) if (work/"child_result.json").exists() else {}
        self.counts = record.get("budget_counts",self.counts)
        self.carry_actions += record.get("equivalent_actions",0)
        if process.returncode or record.get("status") != "COMPLETED":
            raise ValueError("V14 basis child: "+record.get("error","no result"))
        self.guard()
        return record, work

    def finish(self,result):
        # Explicit adapter hook for exact alternate backends. Existing stages
        # retain their original oracle-only accounting when no hook is given.
        equivalent_total = (self.equivalent_actions_total() if hasattr(self,'equivalent_actions_total')
            else self.carry_actions+self.packet.counts['S']+self.packet.counts['SH'])
        result.update(self.meta,budget_counts=self.counts,
            action_counts=self.packet.counts.copy(),action_costs_seconds=self.packet.costs.copy(),
            all_batch_equivalent_actions=equivalent_total,
            worker_wall_seconds=time.perf_counter()-self.began)
        path = self.artifact/"stage_result.json"; write_json(path,result); self.io.publish(self.name,path)
        write_json(self.directory/"artifact_index.json",dict(path=str(path),sha256=file_hash(path)))
        self.event("stage_frozen",status=result["status"],artifact=str(path))


def basis_child(work):
    from src.io.autonomous_neural_head import V10_ROOT, read_result as read_v10
    from src.runners.actual_loss_block_descent import _pure_blas_threads
    from src.solvers.stable_head_varpro import PortBlocks
    from src.solvers.orthonormal_trace_reprofile import OrthonormalTraceBasis, manufactured_witness

    guard_worker_parent("TASK042_NUMERICAL_PARENT_PID")
    request = json.loads((work/"request.json").read_text())
    if request["resident_upper_bytes"] > 8*2**30:
        raise MemoryError("V14 preallocation plan exceeds 8GiB")
    _,_,_,fe = plan_and_operator(); packet = original_packet(fe)
    counts = request["counts"].copy(); began = time.perf_counter(); result = {}
    def guard(*,extra_actions=0,large=False):
        own_sample(Path(request["directory"]))
        if snapshot()["heavy_remaining_seconds"] < (300 if large else 10):
            raise RuntimeError("V14 pure child deadline")
        if request["carry_actions"]+packet.counts["S"]+packet.counts["SH"]+extra_actions>18000:
            raise RuntimeError("V14 original action cap")
    def count(key,n=1):
        guard()
        if counts[key]+n>LIMITS[key]: raise RuntimeError("V14 "+key+" cap")
        counts[key]+=n
    def event(name,**fields):
        guard(); print(json.dumps(dict(event=name,**fields)),flush=True)
    try:
        for key in ("P", "saved_A"):
            if request[key+"_path"] and file_hash(request[key+"_path"])!=request[key+"_sha256"]:
                raise ValueError("V14 current "+key+" file hash differs")
        hidden = np.load(work/"hidden.npy",allow_pickle=False)
        if array_hash(hidden)!=request["hidden_sha256"]: raise ValueError("hidden changed")
        old, _ = read_v10("A")
        columns = np.load(owned(old["original_port_columns"],V10_ROOT),mmap_mode="r")
        ports = PortBlocks(packet,columns)
        P = np.load(request["P_path"],mmap_mode="r",allow_pickle=False)
        A = np.load(request["saved_A_path"],mmap_mode="r",allow_pickle=False) if request["saved_A_path"] else None
        basis = OrthonormalTraceBasis(packet,P,ports,reverse_rows=request["reverse_rows"],
                saved_A=A,count=count,guard=guard,event=event)
        np.save(work/"Q.npy",basis.Q)
        Qidentity = dict(sha256=file_hash(work/"Q.npy"),shape=list(basis.Q.shape),
                         canonical_rows_restored=True,reverse_rows=request["reverse_rows"],
                         source_P_sha256=request["P_sha256"],temporary_regenerable_workspace=True)
        point = basis.solve(packet.a["b"])
        # Publish the minimal numerical state before any derived metadata.
        state = atomic_arrays(work/"physical_state.npz",hidden=hidden,c=point["c"],
            trace=point["trace"],port=point["port"],z=point["z"],
            residual=point["residual"],thin_residual=point["thin_residual"])
        core = dict(name=request["name"],family=FAMILY,source_sha=request["source_sha"],
                    state=state,numeric=point["numeric"],decoder_identity=Qidentity,
                    physical_identity=fe["physical"],reference_arrays_read=False)
        write_json(work/"core_record.json",core)
        count("original_audits"); audit = packet.audit(point["z"])
        result.update(physical=dict(name=request["name"],source_sha=request["source_sha"],state=state,numeric=point["numeric"],audit=audit,
                                    decoder_identity=Qidentity),basis=basis.decomposition(),witnesses=[])
        if request["witnesses"]:
            rng = np.random.default_rng(421401)
            c = rng.standard_normal(1560)+1j*rng.standard_normal(1560); c/=np.linalg.norm(c)
            alpha = rng.standard_normal(40)+1j*rng.standard_normal(40); alpha/=np.linalg.norm(alpha)
            for name,coefficient in (("ORTHO-M1",c),("ORTHO-M2",point["c"])):
                known = np.r_[basis.Q@coefficient,alpha]
                recovered,rhs,row = manufactured_witness(basis,known,name)
                row["state"] = atomic_arrays(work/(name+".npz"),known=known,rhs=rhs,z=recovered["z"],c=recovered["c"])
                result["witnesses"].append(row)
        result.update(status="COMPLETED",threads=_pure_blas_threads(),
            decoder_qualified=bool(point["numeric"]["decoder_gate"] and all(row["qualified"] for row in result["witnesses"])))
    except Exception as error:
        result.update(status="FAILED",error=type(error).__name__+": "+str(error))
        raise
    finally:
        result.update(budget_counts=counts,action_counts=packet.counts.copy(),
            action_costs_seconds=packet.costs.copy(),equivalent_actions=packet.counts["S"]+packet.counts["SH"],
            child_wall_seconds=time.perf_counter()-began,source_sha=request["source_sha"],
            reference_arrays_read=False)
        write_json(work/"child_result.json",result)
        gc.collect()


def main():
    if len(sys.argv)==3 and sys.argv[1]=="--basis-child":
        basis_child(Path(sys.argv[2]).resolve()); return
    guard_worker_parent()
    stage = Stage(load_orthonormal_trace(sys.argv[1]),Path(sys.argv[2]).resolve())
    if subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip()!=stage.source:
        raise RuntimeError("V14 runtime source changed after clean launch")
    try:
        from src.solvers.orthonormal_trace_study import decoder,profile,verify
        result = {"DECODER":decoder,"PROFILE":profile,"VERIFY":verify}[stage.name](stage)
        stage.finish(result)
    except Exception as error:
        write_json(stage.artifact/"failure.json",dict(error=type(error).__name__+": "+str(error),
            counts=stage.counts,source_sha=stage.source,action_counts=stage.packet.counts,
            reference_arrays_read=stage.meta["reference_arrays_read"]))
        traceback.print_exc(); raise
    finally:
        gc.collect()


if __name__=="__main__": main()
