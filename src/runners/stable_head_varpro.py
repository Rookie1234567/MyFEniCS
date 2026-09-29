"""Thin V11 orchestration; stable algebra and optimization live in src/solvers."""

from __future__ import annotations

import ctypes
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import traceback
from contextlib import suppress
from pathlib import Path

import numpy as np

from src.io.autonomous_neural_head import plan_and_operator, read_result as read_v10
from src.io.stable_head_varpro import PLAN_PATH, V11_ROOT, load_stable_head, publish, read_result
from src.io.task042_profile import ROOT
from src.runners.autonomous_neural_head import original_gate, original_packet, owned
from src.runners.task042_shared import write_json
from src.solvers.neural_fe_action_packet import array_hash, file_hash
from src.solvers.stable_head_window import guard_worker_parent, journal, snapshot


def _guard_numerical_parent():
    expected = int(os.environ["TASK042_NUMERICAL_PARENT_PID"])
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, signal.SIGTERM, 0, 0, 0) or os.getppid() != expected:
        raise RuntimeError("qualified numerical child lost own parent")


def basis_child(work):
    """Qualified SciPy-only process; no Torch or target reference is imported."""
    _guard_numerical_parent()
    from src.runners.task042_experiment import thread_qualification
    from src.solvers.neural_linear_head import thin_lstsq
    from src.solvers.stable_head_varpro import StableBasis

    threads = thread_qualification()
    _, _, _, fe = plan_and_operator()
    packet = original_packet(fe)
    b0, _ = read_v10("B0")
    ports_result, _ = read_v10("A")
    ports = np.load(owned(ports_result["original_port_columns"], V11_ROOT.parent / "v10"),
                    mmap_mode="r", allow_pickle=False)
    P = np.load(work / "P.npy", mmap_mode="r", allow_pickle=False)
    if file_hash(work / "P.npy") != json.loads((work / "request.json").read_text())["P_sha256"]:
        raise ValueError("input P hash changed")
    rhs_file = work / "rhs.npz"
    with np.load(rhs_file, allow_pickle=False) as raw:
        rhs = {k: np.array(raw[k]) for k in raw.files}
    initial = json.loads((work / "request.json").read_text())["initial"]
    counts0 = packet.counts.copy()
    began = time.perf_counter()
    record = {"status": "STARTED", "initial": initial, "threads": threads,
              "P_sha256": file_hash(work / "P.npy"), "rhs_sha256": file_hash(rhs_file),
              "source_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()}

    def heartbeat(event, **fields):
        journal(event, evaluation=str(work), **fields)
        print(json.dumps(dict(event=event, **fields)), flush=True)

    try:
        if snapshot()["heavy_remaining_seconds"] < 300:
            raise RuntimeError("V11 remaining time below safety cleanup margin")
        basis = StableBasis(packet, P, ports, heartbeat=heartbeat)
        np.save(work / "A.npy", basis.A)
        np.save(work / "U.npy", basis.U)
        np.save(work / "RA.npy", basis.RA)
        solutions = {}
        solved = {}
        for name, right in rhs.items():
            row = basis.solve(right)
            solutions[name + "_gamma"] = row.pop("gamma")
            solutions[name + "_alpha"] = row.pop("alpha")
            solutions[name + "_trace_p"] = row.pop("trace_p")
            solutions[name + "_trace_z"] = row.pop("trace_z")
            solutions[name + "_bar_residual"] = row.pop("bar_residual")
            solutions[name + "_bar_rhs"] = row.pop("bar_rhs")
            solved[name] = row
        raw_results = {}
        if initial:
            W = np.load(owned(b0["W"], V11_ROOT.parent / "v10"), mmap_mode="r", allow_pickle=False)
            for name in ("M1", "M2"):
                if name not in rhs:
                    continue
                eta, info = thin_lstsq(W, rhs[name])
                # Existing raw record remains untouched; this is a new RHS replay.
                info.pop("exact_full_space_optimum_claimed", None)
                info["numerical_full_column_rank"] = info["effective_rank"] == 1600
                solutions[name + "_raw_eta"] = eta
                raw_results[name] = info
            del W
        np.savez(work / "solutions.npz", **solutions)
        record.update(status="PASS", P_reassembly=basis.P_reassembly,
                      Z_orthogonality=basis.Z_orthogonality,
                      P_rank=basis.P_rank, P_singular_range=basis.P_singular_range,
                      H_condition=basis.ports.cond_H, H_port_pair=basis.ports.port_column_pair,
                      basis_times_seconds=basis.times, solutions=solved, raw=raw_results)
        del basis
    except Exception as error:
        record.update(status="FAILED", error=type(error).__name__ + ": " + str(error),
                      traceback=traceback.format_exc(limit=3))
        raise
    finally:
        record.update(child_wall_seconds=time.perf_counter() - began,
                      action_counts={k: packet.counts[k] - counts0[k] for k in counts0},
                      action_costs_seconds=packet.costs)
        write_json(work / "child_result.json", record)


def correction_child(work):
    """One permitted same-A residual correction, isolated from Torch/reference."""
    _guard_numerical_parent()
    from src.runners.task042_experiment import thread_qualification
    from src.solvers.stable_head_varpro import PortBlocks, one_same_basis_residual_correction

    threads = thread_qualification()
    _, _, _, fe = plan_and_operator()
    packet = original_packet(fe)
    prior = json.loads((work / "request.json").read_text())
    for name in ("P.npy", "A.npy", "U.npy", "solutions.npz", "rhs.npz", "residuals.npz"):
        if file_hash(work / name) != prior["files"][name]:
            raise ValueError("same-decomposition replay input hash differs: " + name)
    P = np.load(work / "P.npy", mmap_mode="r", allow_pickle=False)
    A = np.load(work / "A.npy", mmap_mode="r", allow_pickle=False)
    a, _ = read_v10("A")
    columns = np.load(owned(a["original_port_columns"], V11_ROOT.parent / "v10"), mmap_mode="r")
    ports = PortBlocks(packet, columns)
    with np.load(work / "solutions.npz", allow_pickle=False) as previous:
        old = {name: np.array(previous[name]) for name in previous.files}
    with np.load(work / "residuals.npz", allow_pickle=False) as residuals:
        exact = {name: np.array(residuals[name]) for name in residuals.files}
    corrections = {}
    records = {}
    start = time.perf_counter()
    try:
        cache = None
        for name in ("M2", "physical"):
            gamma, trace_delta, bar_delta, info, cache = one_same_basis_residual_correction(
                packet, P, A, ports, old[name + "_gamma"], exact[name], qr_cache=cache
            )
            corrections[name + "_gamma"] = gamma
            corrections[name + "_trace_p"] = P @ gamma
            corrections[name + "_trace_z"] = old[name + "_trace_z"] + trace_delta
            corrections[name + "_bar_residual"] = old[name + "_bar_residual"] - bar_delta
            records[name] = info
        np.savez(work / "corrections.npz", **corrections)
        status = "PASS"
    except Exception:
        status = "FAILED"
        raise
    finally:
        write_json(work / "correction_result.json", {
            "status": status, "source_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
            "prior_source_sha": prior["prior_source_sha"],
            "same_A_sha256": prior["files"]["A.npy"], "corrections": records,
            "threads": threads, "wall_seconds": time.perf_counter() - start,
            "action_counts": packet.counts, "action_costs_seconds": packet.costs,
            "thin_LS_resolves": len(records), "full_A_rebuilds": 0,
        })


class Stage:
    def __init__(self, specification, directory):
        self.specification, self.directory = specification, directory
        self.plan, self.design, self.material, self.fe = plan_and_operator()
        self.packet = original_packet(self.fe)
        self.artifact = V11_ROOT / directory.name
        self.artifact.mkdir(parents=True, exist_ok=False)
        self.began = time.perf_counter()
        self.stats = {"full_PA_builds": 0, "thin_LS_head_resolves": 0,
                      "equivalent_S_SH": 0, "FD_perturbed_points": 0,
                      "trial_points": 0, "accepted_updates": 0}
        if specification.derived["stage"] == "V11-REPLAY":
            previous, _ = read_result("MAIN")
            self.stats.update(previous["budget_counts"])
            self.stats["equivalent_S_SH"] += previous["action_counts"]["S"]
            self.stats["equivalent_S_SH"] += previous["action_counts"]["SH"]
        self.meta = {"source_sha": (directory / "source_sha.txt").read_text().strip(),
                     "plan_sha256": file_hash(PLAN_PATH),
                     "input_sha256": specification.input_sha256,
                     "physical_identity": self.fe["physical"], "operator_packet": self.fe["packet"],
                     "shared_workstation": True, "complete_ports": 40,
                     "reference_arrays_read": False, "global_p4_factor_constructed": False,
                     "global_S_or_CSR_constructed": False, "hidden_fallback": False}

    def sample(self):
        path = self.directory / "supervision/resources.jsonl"
        with path.open("rb") as stream:
            stream.seek(max(0, path.stat().st_size - 65536))
            lines = stream.read().splitlines()
        for line in reversed(lines):
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if time.time_ns() - item["timestamp_ns"] > 5_000_000_000 or item["swap_bytes"]:
                raise RuntimeError("own supervision stale or own swap nonzero")
            if item["rss_bytes"] >= 12 * 2**30:
                raise RuntimeError("own RSS warning reached")
            if snapshot()["heavy_remaining_seconds"] <= 0:
                raise RuntimeError("V11 heavy stop reached")
            return item
        raise RuntimeError("no fresh own process-tree supervision sample")

    def event(self, name, **fields):
        sample = self.sample()
        row = journal(name, rss_bytes=sample["rss_bytes"], stats=self.stats.copy(), **fields)
        print(json.dumps(row), flush=True)

    def capacity(self, *, additional_builds=1, additional_ls=1):
        if self.stats["full_PA_builds"] + additional_builds > 40:
            raise RuntimeError("V11 40 P/A rebuild limit")
        if self.stats["thin_LS_head_resolves"] + additional_ls > 48:
            raise RuntimeError("V11 48 head resolve limit")
        parent_actions = self.packet.counts["S"] + self.packet.counts["SH"]
        if self.stats["equivalent_S_SH"] + parent_actions + 1600 * additional_builds > 65000:
            raise RuntimeError("V11 65000 action limit")
        if snapshot()["heavy_remaining_seconds"] < 600:
            raise RuntimeError("V11 less than conservative evaluation plus 300s cleanup")
        self.sample()

    def call_child(self, work, *, initial=False):
        request = {"initial": initial, "P_sha256": file_hash(work / "P.npy")}
        write_json(work / "request.json", request)
        with np.load(work / "rhs.npz", allow_pickle=False) as rhs:
            rhs_count = len(rhs.files)
        self.capacity(additional_builds=1, additional_ls=rhs_count + (2 if initial else 0))
        self.event("head_build_start", evaluation=str(work), rhs_count=rhs_count)
        command = ["bash", "-c",
                   'source scripts/activate_task042.sh pure; exec python -m src.runners.stable_head_varpro --basis "$1"',
                   "task042-v11-pure", str(work)]
        result = subprocess.run(command, check=False,
                                env=dict(os.environ, TASK042_NUMERICAL_PARENT_PID=str(os.getpid())))
        record = json.loads((work / "child_result.json").read_text()) if (work / "child_result.json").exists() else {}
        self.stats["full_PA_builds"] += 1
        self.stats["thin_LS_head_resolves"] += len(record.get("solutions", {})) + len(record.get("raw", {}))
        self.stats["equivalent_S_SH"] += record.get("action_counts", {}).get("S", 0)
        self.stats["equivalent_S_SH"] += record.get("action_counts", {}).get("SH", 0)
        write_json(self.artifact / "budget.json", self.stats)
        if result.returncode or record.get("status") != "PASS":
            raise RuntimeError("qualified stable head child failed; see retained child_result.json")
        self.event("head_build_done", evaluation=str(work), child_wall=record["child_wall_seconds"])
        return record

    def freeze(self, name, z, **arrays):
        path = self.artifact / (name + ".npz")
        np.savez(path, z=z, **arrays)
        return {"path": str(path), "sha256": file_hash(path), "z_sha256": array_hash(z),
                "arrays": {k: {"shape": list(v.shape), "sha256": array_hash(v)} for k, v in arrays.items()}}

    def finish(self, name, result):
        result.update(self.meta, status=result.get("status", "FINISHED"),
                      action_counts=self.packet.counts, action_costs_seconds=self.packet.costs,
                      budget_counts=self.stats, worker_wall_seconds=time.perf_counter() - self.began)
        path = self.artifact / "stage_result.json"
        write_json(path, result)
        publish(name, path)
        write_json(self.directory / "artifact_index.json", {"path": str(path), "sha256": file_hash(path)})
        self.event("stage_artifact_frozen", result_name=name, status=result["status"])


class MainExperiment:
    def __init__(self, stage):
        from src.runners.neural_fe_continuation import read_moments
        from src.solvers.neural_linear_head_torch import head_coefficients
        from src.solvers.neural_trace_batched import BatchedMoments
        from src.solvers.neural_trace_torch import NeuralTrace, qualify_threads
        from src.solvers.stable_head_varpro import PortBlocks

        self.stage = stage
        self.packet = stage.packet
        self.threads = qualify_threads()
        self.b0, _ = read_v10("B0")
        self.v10root = V11_ROOT.parent / "v10"
        self.old_P = owned(self.b0["P"], self.v10root)
        self.old_W = owned(self.b0["W"], self.v10root)
        a, _ = read_v10("A")
        self.original_port_columns = owned(a["original_port_columns"], self.v10root)
        self.ports = PortBlocks(self.packet, np.load(self.original_port_columns, mmap_mode="r"))
        self.moments, self.moment_identity = read_moments()
        self.model = NeuralTrace(stage.design["geometry"]["bounds_nm"], 0.7, seed=420906)
        self.cache = BatchedMoments(self.model, self.moments, resource_sample=stage.sample())
        if len(head_coefficients(self.model)) != 1560:
            raise ValueError("original random network head inventory changed")
        self.initial_hidden = None
        self.initial_witnesses = []
        self.states = []
        self.progress = stage.artifact / "varpro_progress.jsonl"

    def log(self, kind, **fields):
        row = dict(kind=kind, utc=time.time(), source_sha=self.stage.meta["source_sha"],
                   remaining_seconds=snapshot()["heavy_remaining_seconds"],
                   counts=self.stage.stats.copy(), shared_workstation=True, **fields)
        with self.progress.open("a") as stream:
            stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        return row

    def pre_mapping_witnesses(self):
        from src.solvers.neural_linear_head_torch import assign_head
        from src.solvers.stable_head_varpro_torch import hidden_vector

        self.initial_hidden = hidden_vector(self.model)
        P = np.load(self.old_P, mmap_mode="r", allow_pickle=False)
        for seed in (421011, 421012, 421013):
            rng = np.random.default_rng(seed)
            gamma = 0.001 * (rng.standard_normal(1560) + 1j * rng.standard_normal(1560))
            assign_head(self.model, gamma)
            actual = self.cache.forward(self.model)
            predicted = P @ gamma
            relative = float(np.linalg.norm(actual - predicted) / max(np.linalg.norm(actual), 1e-300))
            self.initial_witnesses.append(dict(seed=seed, relative=relative,
                                               nonzero_trace_norm=float(np.linalg.norm(actual))))
        if max(row["relative"] for row in self.initial_witnesses) > 1e-10:
            raise ValueError("three original Nedelec mapping witnesses failed before solve")
        self.log("three_mapping_witnesses", rows=self.initial_witnesses)

    def manufactured_rhs(self):
        from src.solvers.stable_head_varpro_torch import actual_trace

        rng = np.random.default_rng(421101)
        gamma1 = rng.standard_normal(1560) + 1j * rng.standard_normal(1560)
        alpha1 = rng.standard_normal(40) + 1j * rng.standard_normal(40)
        gamma1 /= np.linalg.norm(gamma1)
        alpha1 /= np.linalg.norm(alpha1)
        t1 = actual_trace(self.model, self.cache, gamma1)
        z1 = np.r_[t1, alpha1]
        rhs = {"M1": self.packet.apply(z1)}
        states = {"M1": z1}
        b0_state = owned(self.b0["state"], self.v10root)
        with np.load(b0_state, allow_pickle=False) as saved:
            gamma2 = np.array(saved["gamma"])
            alpha2 = np.array(saved["port_coefficients"])
            z2_saved = np.array(saved["z"])
        t2 = actual_trace(self.model, self.cache, gamma2)
        z2 = np.r_[t2, alpha2]
        pair = float(np.linalg.norm(z2 - z2_saved) / max(np.linalg.norm(z2_saved), 1e-300))
        if pair > 1e-10:
            raise ValueError("V10 B0 unlabelled state does not regenerate from saved head")
        rhs["M2"] = self.packet.apply(z2)
        states["M2"] = z2
        identity = {"M1_seed": 421101, "M1_gamma_norm": float(np.linalg.norm(gamma1)),
                    "M1_alpha_norm": float(np.linalg.norm(alpha1)),
                    "M2_saved_B0_state": self.b0["state"], "M2_gamma_norm": float(np.linalg.norm(gamma2)),
                    "M2_reproduced_relative": pair,
                    "rhs_from_original_action_apply": True, "physical_packet_b_overwritten": False,
                    "reference_arrays_read": False}
        self.log("manufactured_rhs_frozen", identity=identity,
                 rhs_hashes={name: array_hash(value) for name, value in rhs.items()})
        return rhs, states, identity

    def _prepare_work(self, name, hidden, rhs, *, reuse_P=False):
        from src.solvers.neural_linear_head_torch import build_head_mapping
        from src.solvers.stable_head_varpro_torch import set_hidden

        work = self.stage.artifact / name
        work.mkdir(exist_ok=False)
        set_hidden(self.model, hidden)
        if reuse_P:
            os.symlink(self.old_P, work / "P.npy")
            mapping = {"reused_verified_V10_B0_P": True, "path": str(self.old_P),
                       "sha256": file_hash(self.old_P)}
        else:
            P, mapping = build_head_mapping(self.model, self.cache, work / "P.npy")
            del P
        np.savez(work / "rhs.npz", **rhs)
        return work, mapping

    def _actual_solution(self, work, key, right, known=None):
        from src.solvers.stable_head_varpro import homogeneous_recovery_pair, rhs_residual
        from src.solvers.stable_head_varpro_torch import actual_trace

        with np.load(work / "solutions.npz", allow_pickle=False) as values:
            gamma = np.array(values[key + "_gamma"])
            tP = np.array(values[key + "_trace_p"])
            tZ = np.array(values[key + "_trace_z"])
            predicted_r = np.array(values[key + "_bar_residual"])
            barb = np.array(values[key + "_bar_rhs"])
        tnet = actual_trace(self.model, self.cache, gamma)
        z, action_t = self.ports.closed(tnet, right)
        bar_r = barb - (action_t[: self.packet.nt] - self.ports.C @ np.linalg.solve(
            self.ports.H, action_t[self.packet.nt :]
        ))
        full = rhs_residual(self.packet, z, right)
        U = np.load(work / "U.npy", mmap_mode="r", allow_pickle=False)
        A = np.load(work / "A.npy", mmap_mode="r", allow_pickle=False)
        point = {
            "name": key, "gamma": gamma, "z": z, "bar_residual": bar_r,
            "Phi": float(np.vdot(bar_r, bar_r).real / (2 * self.packet.bnorm**2)),
            "Schur_relative_fixed_physical_b": float(np.linalg.norm(right - self.packet.apply(z)) / self.packet.bnorm),
            "port_fixed_physical_b": float(full["port_absolute"] / self.packet.bnorm),
            "full_rhs_residual": full,
            "network_vs_Pgamma_trace_relative": float(
                np.linalg.norm(tnet - tP) / max(np.linalg.norm(tnet), np.linalg.norm(tP), 1e-300)),
            "Pgamma_vs_Zc_trace_relative": float(
                np.linalg.norm(tP - tZ) / max(np.linalg.norm(tP), np.linalg.norm(tZ), 1e-300)),
            "actual_vs_thin_residual_fixed_physical_b": float(
                np.linalg.norm(bar_r - predicted_r) / self.packet.bnorm),
            "actual_stationarity_UHr_fixed_physical_b": float(
                np.linalg.norm(U.conj().T @ bar_r) / self.packet.bnorm),
            "actual_AHr_absolute": float(np.linalg.norm(A.conj().T @ bar_r)),
            "actual_gamma_norm": float(np.linalg.norm(gamma)),
            "actual_port_norm": float(np.linalg.norm(z[self.packet.nt :])),
        }
        if known is not None:
            point["known_z_relative"] = float(
                np.linalg.norm(z - known) / max(np.linalg.norm(known), 1e-300)
            )
            point["homogeneous_recovery_pair"] = homogeneous_recovery_pair(self.packet, known, z)
        return point

    @staticmethod
    def _public_point(point):
        return {k: v for k, v in point.items() if k not in {"gamma", "z", "bar_residual"}}

    def initial(self):
        from src.solvers.stable_head_varpro import homogeneous_recovery_pair, rhs_residual
        from src.solvers.stable_head_varpro_torch import actual_trace

        self.pre_mapping_witnesses()
        witness_rhs, known, identity = self.manufactured_rhs()
        all_rhs = {"physical": self.packet.a["b"], **witness_rhs}
        self.stage.capacity(additional_builds=1, additional_ls=5)
        work, mapping = self._prepare_work("initial", self.initial_hidden, all_rhs, reuse_P=True)
        child = self.stage.call_child(work, initial=True)
        rows = {}
        with np.load(work / "solutions.npz", allow_pickle=False) as values:
            for key in ("M1", "M2"):
                right = witness_rhs[key]
                stable = self._actual_solution(work, key, right, known[key])
                eta = np.array(values[key + "_raw_eta"])
                raw_t = actual_trace(self.model, self.cache, eta[:1560])
                raw_z = np.r_[raw_t, eta[1560:]]
                raw = rhs_residual(self.packet, raw_z, right)
                raw["known_z_relative"] = float(
                    np.linalg.norm(raw_z - known[key]) / max(np.linalg.norm(known[key]), 1e-300)
                )
                raw["homogeneous_recovery_pair"] = homogeneous_recovery_pair(self.packet, known[key], raw_z)
                rows[key] = {"raw": raw, "stable": self._public_point(stable),
                             "stable_gate": bool(stable["full_rhs_residual"]["relative"] <= 1e-8
                                                 and stable["known_z_relative"] <= 1e-6
                                                 and stable["homogeneous_recovery_pair"] <= 1e-10),
                             "manufactured_rhs_sha256": array_hash(right),
                             "known_z_sha256": array_hash(known[key])}
        physical = self._actual_solution(work, "physical", self.packet.a["b"])
        audit = self.packet.audit(physical["z"])
        physical["original_audit"] = audit
        physical["original_gate"] = original_gate(audit)
        self.log("S1_S2_actual_baseline", physical=self._public_point(physical),
                 manufactured=rows)
        state = self.stage.freeze("S2_stable_random_baseline", physical["z"],
                                  network_parameters=self._network_parameters(),
                                  hidden=self.initial_hidden, gamma=physical["gamma"],
                                  port=physical["z"][self.packet.nt :])
        self.states.append(dict(name="S2_BASELINE", state=state, audit=audit,
                                Phi=physical["Phi"], hidden_updates=0))
        result = {"manufactured": rows, "manufactured_identity": identity,
                  "three_prior_nonzero_mapping_witnesses": self.initial_witnesses,
                  "stable_basis": {k: child[k] for k in (
                      "P_reassembly", "Z_orthogonality", "P_rank", "P_singular_range",
                      "H_condition", "H_port_pair", "basis_times_seconds", "solutions", "raw")},
                  "mapping": mapping, "moments": self.moment_identity,
                  "threads": self.threads, "cache": self.cache.identity(),
                  "physical": self._public_point(physical), "baseline_state": state}
        result["S1_gate"] = all(row["stable_gate"] for row in rows.values())
        result["S2_gate"] = bool(child["solutions"]["physical"]["numerical_full_column_rank"]
                                 and physical["network_vs_Pgamma_trace_relative"] <= 1e-8
                                 and physical["Pgamma_vs_Zc_trace_relative"] <= 1e-8
                                 and physical["actual_vs_thin_residual_fixed_physical_b"] <= 1e-8
                                 and physical["actual_stationarity_UHr_fixed_physical_b"] <= 1e-8)
        return result, physical

    def _network_parameters(self):
        from src.solvers.neural_trace_checks import parameters
        return parameters(self.model)

    def _gradient_initial(self, baseline):
        from src.solvers.stable_head_varpro_torch import envelope_gradient

        gradient, metadata = envelope_gradient(
            self.cache, self.model, self.ports, baseline["bar_residual"], self.packet.bnorm
        )
        self.log("initial_scalar_envelope_gradient", metadata=metadata,
                 gradient_sha256=array_hash(gradient))
        return gradient, metadata

    def evaluate(self, hidden, name, *, keep=False, fd=False):
        from src.solvers.stable_head_varpro_torch import envelope_gradient

        if fd and self.stage.stats["FD_perturbed_points"] >= 18:
            raise RuntimeError("V11 18 FD perturbation limit")
        self.stage.capacity(additional_builds=1, additional_ls=1)
        work, mapping = self._prepare_work(name, hidden, {"physical": self.packet.a["b"]})
        try:
            child = self.stage.call_child(work)
            point = self._actual_solution(work, "physical", self.packet.a["b"])
            row = child["solutions"]["physical"]
            gated = bool(row["numerical_full_column_rank"] and
                         point["network_vs_Pgamma_trace_relative"] <= 1e-8 and
                         point["Pgamma_vs_Zc_trace_relative"] <= 1e-8 and
                         point["actual_vs_thin_residual_fixed_physical_b"] <= 1e-8 and
                         point["actual_stationarity_UHr_fixed_physical_b"] <= 1e-8)
            point["head_numeric_gate"] = gated
            point["P_rank"] = child["P_rank"]
            point["A_rank"] = row["rank_A"]
            point["mapping_seconds"] = mapping.get("seconds", 0.0)
            point["head_child_seconds"] = child["child_wall_seconds"]
            if gated and not fd:
                gradient, gradient_meta = envelope_gradient(
                    self.cache, self.model, self.ports, point["bar_residual"], self.packet.bnorm
                )
                point["gradient"] = gradient
                point["gradient_meta"] = gradient_meta
            self.log("full_varpro_evaluation", name=name, point=self._public_point(point),
                     retained=keep, FD_perturbation=fd)
            if fd:
                self.stage.stats["FD_perturbed_points"] += 1
            return point
        finally:
            # Only recreatable thin workspaces are dropped; child result, RHS,
            # identities, small parameter records and accepted states survive.
            if not keep:
                for item in ("P.npy", "A.npy", "U.npy", "RA.npy"):
                    with suppress(FileNotFoundError):
                        (work / item).unlink()


def _field_gate(point):
    return (point["network_vs_Pgamma_trace_relative"] <= 1e-8
            and point["actual_vs_thin_residual_fixed_physical_b"] <= 1e-8
            and point["actual_stationarity_UHr_fixed_physical_b"] <= 1e-8)


def main_stage(stage, *, experiment=None, initial_data=None):
    from src.solvers.stable_head_varpro import armijo_steps, lbfgs_direction
    from src.solvers.stable_head_varpro_torch import fixed_directions

    experiment = MainExperiment(stage) if experiment is None else experiment
    p_bytes = stage.packet.nt * 1560 * 16
    packet_bytes = sum(value.nbytes for value in stage.packet.a.values())
    resident_plan = 8 * p_bytes + 2 * 1560**2 * 16 + 2 * 2**30 + packet_bytes + experiment.cache.cache_bytes
    if resident_plan > 8 * 2**30:
        raise RuntimeError("V11 simultaneous resident capacity plan exceeds 8GiB")
    stage.event("pre_thin_resident_plan", resident_plan_bytes=resident_plan,
                cap_bytes=8 * 2**30, packet_bytes=packet_bytes,
                lifecycle="P/Z/A/U plus QR/GELSD copies, parent ML/cache, packet and small factors")
    result, baseline = experiment.initial() if initial_data is None else initial_data
    result["resident_plan_bytes"] = resident_plan
    result["accepted_updates"] = 0
    result["states"] = experiment.states
    result["reference_barrier"] = "REF7 inaccessible to MAIN; independent VERIFY only after queue frozen"
    if not result["S1_gate"] or not result["S2_gate"]:
        result.update(status="STABLE_RECOVERY_OR_HEAD_GATE_FAILED",
                      S3="NOT_RUN_DEPENDENT_GATE", S4="NOT_RUN_DEPENDENT_GATE")
        experiment.log("stop", reason=result["status"])
        return result

    psi = experiment.initial_hidden.copy()
    repeat = experiment.evaluate(psi, "samepoint_repeat")
    delta_repeat = abs(repeat["Phi"] - baseline["Phi"])
    result["samepoint_repeat"] = {"Phi": repeat["Phi"], "absolute_difference": delta_repeat,
                                  "limit": 1e-10 * max(1, baseline["Phi"])}
    if not repeat["head_numeric_gate"] or delta_repeat > result["samepoint_repeat"]["limit"]:
        result.update(status="SAMEPOINT_REPEAT_GATE_FAILED", S3="NOT_RUN", S4="NOT_RUN")
        experiment.log("stop", reason=result["status"])
        return result
    gradient, gradient_meta = experiment._gradient_initial(baseline)
    result["initial_gradient"] = gradient_meta
    if not np.isfinite(gradient).all() or np.linalg.norm(gradient) <= 1e-14:
        result.update(status="INITIAL_GRADIENT_NO_RELIABLE_DESCENT", S3="NOT_RUN", S4="NOT_RUN")
        experiment.log("stop", reason=result["status"])
        return result
    directions = fixed_directions(gradient)
    fd_rows = []
    for direction_name, direction in directions:
        analytic = float(np.dot(gradient, direction))
        samples = []
        for step in (1e-4, 1e-5, 1e-6):
            if len(samples) >= 2 and any(item["passed"] for item in samples):
                break
            plus = experiment.evaluate(psi + step * direction,
                                       f"fd_{direction_name}_{step:g}_plus", fd=True)
            minus = experiment.evaluate(psi - step * direction,
                                        f"fd_{direction_name}_{step:g}_minus", fd=True)
            measured = (plus["Phi"] - minus["Phi"]) / (2 * step)
            error = abs(measured - analytic)
            near_zero = abs(analytic) <= 1e-10
            passed = bool(plus["head_numeric_gate"] and minus["head_numeric_gate"]
                          and (error <= 1e-10 if near_zero else error / abs(analytic) <= 1e-5))
            samples.append(dict(step=step, analytic=analytic, finite_difference=measured,
                                absolute_error=error, relative_error=None if near_zero else error / abs(analytic),
                                plus_rank=[plus["P_rank"], plus["A_rank"]],
                                minus_rank=[minus["P_rank"], minus["A_rank"]], passed=passed))
        fd_rows.append(dict(direction=direction_name, samples=samples,
                            passed=any(row["passed"] for row in samples)))
        experiment.log("FD_direction_complete", direction=direction_name, samples=samples)
    result["S3_finite_difference"] = fd_rows
    result["S3_gate"] = bool(all(row["passed"] for row in fd_rows)
                              and any(abs(row["samples"][0]["analytic"]) > 1e-10 for row in fd_rows))
    if not result["S3_gate"]:
        result.update(status="VARPRO_GRADIENT_UNTRUSTED", S4="NOT_RUN_DEPENDENT_GATE")
        experiment.log("stop", reason=result["status"])
        return result

    # Complete VarPro commit point: hidden, head, port, physical z and memory.
    current = baseline
    current["gradient"] = gradient
    history = []
    accepted = []
    trial_rows = []
    for outer in range(1, 6):
        if outer > 3:
            base_native = baseline["original_audit"]["native_relative"]
            if not (current["Phi"] <= 0.99 * baseline["Phi"]
                    and current["original_audit"]["native_relative"] <= 1.05 * base_native
                    and current["original_audit"]["port_full_rhs_relative"] <= 1e-6):
                experiment.log("extra_two_not_admitted", after_accepted=len(accepted))
                break
        direction = lbfgs_direction(current["gradient"], history)
        gtd = float(np.dot(current["gradient"], direction))
        accepted_trial = None
        for trial_id, alpha in enumerate(armijo_steps(psi, direction)):
            stage.stats["trial_points"] += 1
            trial_name = f"outer{outer}_trial{trial_id}"
            try:
                trial = experiment.evaluate(psi + alpha * direction, trial_name)
                sufficient = trial["Phi"] <= current["Phi"] + 1e-4 * alpha * gtd
                improvement = current["Phi"] - trial["Phi"]
                passed = bool(trial["head_numeric_gate"] and sufficient and
                              improvement > max(1e-12, 10 * delta_repeat))
                reason = "ARMIJO_ACCEPT" if passed else "HEAD_OR_ARMIJO_OR_NOISE_REJECT"
                point_summary = experiment._public_point(trial)
            except (ValueError, RuntimeError, FloatingPointError) as exc:
                trial = None
                passed = False
                reason = type(exc).__name__ + ": " + str(exc)
                point_summary = None
            record = dict(outer=outer, trial=trial_id, alpha=alpha, g_dot_d=gtd,
                          accepted=passed, reason=reason, point=point_summary,
                          counts=stage.stats.copy(), remaining=snapshot()["heavy_remaining_seconds"])
            trial_rows.append(record)
            experiment.log("armijo_trial", **record)
            if passed:
                accepted_trial = trial
                break
        if accepted_trial is None:
            result["S4_stop"] = "FOUR_ARMIJO_TRIALS_REJECTED_OR_BUDGET"
            break
        old_psi, old_gradient = psi.copy(), current["gradient"].copy()
        psi = psi + alpha * direction
        current = accepted_trial
        new_gradient = current["gradient"]
        s, y = psi - old_psi, new_gradient - old_gradient
        curvature = float(np.dot(s, y))
        if curvature > 1e-12 * np.linalg.norm(s) * np.linalg.norm(y):
            history.append((s.copy(), y.copy()))
            history = history[-5:]
        audit = stage.packet.audit(current["z"])
        current["original_audit"] = audit
        current["original_gate"] = original_gate(audit)
        checkpoint = stage.freeze(f"S4_accepted_{outer}", current["z"],
                                  network_parameters=experiment._network_parameters(),
                                  hidden=psi, gamma=current["gamma"],
                                  port=current["z"][stage.packet.nt :],
                                  memory_s=np.array([pair[0] for pair in history]).reshape(-1, len(psi)),
                                  memory_y=np.array([pair[1] for pair in history]).reshape(-1, len(psi)))
        stage.stats["accepted_updates"] += 1
        item = dict(name=f"S4_ACCEPT_{outer}", state=checkpoint, Phi=current["Phi"],
                    audit=audit, hidden_updates=outer, curvature=curvature,
                    history_pairs=len(history), original_gate=current["original_gate"])
        accepted.append(item)
        experiment.states.append(item)
        experiment.log("varpro_accepted_commit", outer=outer, state=checkpoint,
                       Phi=current["Phi"], original_gate=current["original_gate"])
        if current["original_gate"]["status"] == "ORIGINAL_EQUATION_PASS":
            result["S4_stop"] = "STRICT_EQUATION_PASS_ENTER_S5"
            break
    result.update(status="SOLVER_QUEUE_FROZEN", accepted_updates=len(accepted),
                  accepted=accepted, trial_records=trial_rows,
                  final_Phi=current["Phi"], final_audit=current["original_audit"],
                  final_original_gate=current["original_gate"], states=experiment.states)
    experiment.log("solver_queue_frozen", accepted=len(accepted), final_Phi=current["Phi"],
                   reason=result.get("S4_stop", "PREDECLARED_UPDATE_LIMIT"))
    return result


def replay_stage(stage):
    """One justified correction of the retained initial decomposition, then gates."""
    experiment = MainExperiment(stage)
    old, old_path = read_result("MAIN")
    old_work = old_path.parent / "initial"
    if old["status"] != "STABLE_RECOVERY_OR_HEAD_GATE_FAILED":
        raise ValueError("residual correction is only for the retained failed initial gate")
    experiment.pre_mapping_witnesses()
    witness_rhs, known, identity = experiment.manufactured_rhs()
    for name in ("M1", "M2"):
        if array_hash(witness_rhs[name]) != old["manufactured"][name]["manufactured_rhs_sha256"]:
            raise ValueError("manufactured RHS differs from frozen initial run")
    work = stage.artifact / "same_basis_correction"
    work.mkdir()
    for name in ("P.npy", "A.npy", "U.npy"):
        os.symlink((old_work / name).resolve(), work / name)
    shutil.copyfile(old_work / "solutions.npz", work / "solutions.npz")
    shutil.copyfile(old_work / "rhs.npz", work / "rhs.npz")
    old_points = {}
    old_points["M2"] = experiment._actual_solution(work, "M2", witness_rhs["M2"], known["M2"])
    old_points["physical"] = experiment._actual_solution(work, "physical", stage.packet.a["b"])
    np.savez(work / "residuals.npz",
             M2=old_points["M2"]["bar_residual"],
             physical=old_points["physical"]["bar_residual"])
    stage.capacity(additional_builds=0, additional_ls=2)
    files = {name: file_hash(work / name) for name in (
        "P.npy", "A.npy", "U.npy", "solutions.npz", "rhs.npz", "residuals.npz")}
    write_json(work / "request.json", {
        "prior_source_sha": old["source_sha"], "files": files,
        "scope": "one same-decomposition residual correction for M2 and physical; no A rebuild"
    })
    stage.event("same_decomposition_correction_start", prior_source=old["source_sha"],
                old_A_sha256=files["A.npy"])
    child = subprocess.run(
        ["bash", "-c",
         'source scripts/activate_task042.sh pure; exec python -m src.runners.stable_head_varpro --correct "$1"',
         "task042-v11-correct", str(work)],
        check=False, env=dict(os.environ, TASK042_NUMERICAL_PARENT_PID=str(os.getpid())),
    )
    correction = json.loads((work / "correction_result.json").read_text())
    stage.stats["thin_LS_head_resolves"] += correction["thin_LS_resolves"]
    stage.stats["equivalent_S_SH"] += correction["action_counts"]["S"]
    stage.stats["equivalent_S_SH"] += correction["action_counts"]["SH"]
    write_json(stage.artifact / "budget.json", stage.stats)
    if child.returncode or correction["status"] != "PASS":
        raise RuntimeError("same-decomposition correction failed; original negative retained")
    with np.load(work / "solutions.npz", allow_pickle=False) as source:
        merged = {key: np.array(source[key]) for key in source.files}
    with np.load(work / "corrections.npz", allow_pickle=False) as source:
        merged.update({key: np.array(source[key]) for key in source.files})
    np.savez(work / "solutions.npz", **merged)
    m1 = old["manufactured"]["M1"]
    m2 = experiment._actual_solution(work, "M2", witness_rhs["M2"], known["M2"])
    physical = experiment._actual_solution(work, "physical", stage.packet.a["b"])
    audit = stage.packet.audit(physical["z"])
    physical["original_audit"] = audit
    physical["original_gate"] = original_gate(audit)
    m2_gate = bool(m2["full_rhs_residual"]["relative"] <= 1e-8
                   and m2["known_z_relative"] <= 1e-6
                   and m2["homogeneous_recovery_pair"] <= 1e-10)
    numeric_gate = bool(old["stable_basis"]["solutions"]["physical"]["numerical_full_column_rank"]
                        and _field_gate(physical)
                        and physical["Pgamma_vs_Zc_trace_relative"] <= 1e-8)
    state = stage.freeze("S2_corrected_random_baseline", physical["z"],
                         network_parameters=experiment._network_parameters(),
                         hidden=experiment.initial_hidden, gamma=physical["gamma"],
                         port=physical["z"][stage.packet.nt :])
    experiment.states.append(dict(name="S2_BASELINE", state=state, audit=audit,
                                  Phi=physical["Phi"], hidden_updates=0))
    result = {
        "status": "CORRECTED_BASELINE_FROZEN", "prior_MAIN": {"path": str(old_path),
            "sha256": file_hash(old_path), "source_sha": old["source_sha"]},
        "same_decomposition_correction": correction,
        "M1_unchanged_original_pass": m1,
        "M2_before": experiment._public_point(old_points["M2"]),
        "M2_after": experiment._public_point(m2),
        "physical_before": experiment._public_point(old_points["physical"]),
        "physical_baseline": experiment._public_point(physical),
        "manufactured_identity": identity,
        "three_prior_nonzero_mapping_witnesses": experiment.initial_witnesses,
        "S1_gate": bool(m1["stable_gate"] and m2_gate),
        "S2_gate": numeric_gate,
        "baseline_state": state,
        "states": experiment.states,
        "reference_arrays_read": False,
        "no_new_A_build": True,
    }
    experiment.log("single_residual_correction_result", M2=result["M2_after"],
                   physical=result["physical_baseline"], S1_gate=result["S1_gate"],
                   S2_gate=result["S2_gate"])
    if not result["S1_gate"] or not result["S2_gate"]:
        result.update(status="SAME_DECOMPOSITION_CORRECTION_STILL_FAILED",
                      S3="NOT_RUN_DEPENDENT_GATE", S4="NOT_RUN_DEPENDENT_GATE")
        experiment.log("stop", reason=result["status"])
        return result
    return main_stage(stage, experiment=experiment, initial_data=(result, physical))


def verify_stage(stage):
    """Only this separate, post-freeze FE process can read the saved p3 reference."""
    from src.io.neural_fe_continuation import V7_ROOT, read_index
    from src.solvers.neural_fe_blind_reference import independent_physics

    try:
        main, _ = read_result("REPLAY")
    except FileNotFoundError:
        main, _ = read_result("MAIN")
    if main["source_sha"] != stage.meta["source_sha"]:
        # A newer clean implementation source requires an explicit provenance
        # statement; there is no warm-start or candidate rewrite here.
        raise ValueError("V11 verifier and solver sources differ")
    if not main.get("states"):
        return {"status": "NOT_RUN_NO_FROZEN_CANDIDATE", "reference_arrays_read": False}
    reference_record, _ = read_index("blind_reference")
    ref_path = owned(reference_record["reference_state"], V7_ROOT)
    if file_hash(ref_path) != "a0610a5a55e7508196b17277e706595c33e4398ace82b245f70b656e6b9ed355":
        raise ValueError("saved independent p3 reference hash differs")
    with np.load(ref_path, allow_pickle=False) as values:
        reference = np.array(values["z"])
    stage.meta["reference_arrays_read"] = True
    candidates = {}
    for state in main["states"]:
        path = Path(state["state"]["path"]).resolve()
        if not path.is_relative_to(V11_ROOT) or file_hash(path) != state["state"]["sha256"]:
            raise ValueError("frozen candidate path/hash changed")
        with np.load(path, allow_pickle=False) as values:
            z = np.array(values["z"])
        if array_hash(z) != state["state"]["z_sha256"]:
            raise ValueError("frozen canonical state changed")
        candidates[state["name"]] = z
    stage.event("reference_opened_after_solver_queue_frozen", inventory=list(candidates))
    physics, comparisons = independent_physics(stage.design, stage.packet, reference,
                                                candidates, stage.artifact)
    rows = {}
    for name, z in candidates.items():
        item = physics["rows"][name]
        comparison = comparisons[name]
        audit = item["audit"]
        eq = original_gate(audit)
        fields = {key: item[key] for key in (
            "full_FE_L2_relative", "full_FE_scaled_curl_relative",
            "scattered_FE_L2_relative", "scattered_scaled_curl_relative",
            "selected_E_relative", "selected_H_relative")}
        same = bool(eq["status"] == "ORIGINAL_EQUATION_PASS" and physics["reference_native_pass"])
        same &= all(np.isfinite(value) and value <= 1e-4 for value in fields.values())
        same &= audit["independent_DOLFINx_total_native_relative"] <= 1e-6
        same &= comparison["ordered_complex_ports_relative"] <= 1e-4
        same &= all(value <= 1e-5 for value in comparison["power_absolute_differences"].values())
        same &= comparison["max_channel_power_difference"] <= 1e-6
        same &= comparison["energy_closure_absolute"] <= 1e-5
        rows[name] = {"status": "SAME_DISCRETE_QUALIFIED" if same else "NOT_QUALIFIED",
                      "original_equation_gate": eq, "audit": audit, "fields": fields,
                      "ordered_complex_total_ports": item["ordered_complex_port_vector"],
                      "ordered_complex_scattered_ports": item["ordered_complex_scattered_port_vector"],
                      "selected_E": item["selected_E"], "selected_H_code": item["selected_H_code"],
                      "power": item["port"], "volume_absorption": item["volume"],
                      "comparison": comparison,
                      "official_candidate_results": bool(same)}
    baseline = rows["S2_BASELINE"]
    latest = rows[list(candidates)[-1]]
    base_rho = baseline["original_equation_gate"]["rho"]
    final_rho = latest["original_equation_gate"]["rho"]
    positive = bool(final_rho <= 0.5 * base_rho
                    and latest["fields"]["scattered_FE_L2_relative"] <= 0.5
                    and latest["fields"]["scattered_scaled_curl_relative"] <= 0.5
                    and latest["fields"]["scattered_FE_L2_relative"] <=
                    0.75 * baseline["fields"]["scattered_FE_L2_relative"]
                    and latest["fields"]["scattered_scaled_curl_relative"] <=
                    0.75 * baseline["fields"]["scattered_scaled_curl_relative"])
    return {"status": "SAME_DISCRETE_QUALIFIED" if all(r["status"] == "SAME_DISCRETE_QUALIFIED"
                                                    for r in rows.values()) else "NEGATIVE_OR_PARTIAL",
            "rows": rows, "reference_identity": reference_record["reference_state"],
            "reference_only_after_MAIN_frozen": True,
            "research_positive_signal": positive,
            "reference_feedback_to_solver": False,
            "official_results_only_if_each_candidate_passes": True,
            "full_channel_inventory": 40,
            "comparative_baseline_rho": base_rho, "comparative_final_rho": final_rho,
            "no_p4_enrichment": True}


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--basis":
        basis_child(Path(sys.argv[2]).resolve())
        return
    if len(sys.argv) == 3 and sys.argv[1] == "--correct":
        correction_child(Path(sys.argv[2]).resolve())
        return
    if len(sys.argv) != 3:
        raise SystemExit("one Task042 V11 dat and output directory required")
    guard_worker_parent()
    specification = load_stable_head(sys.argv[1])
    if specification is None:
        raise ValueError("V11 input loader rejected dat")
    directory = Path(sys.argv[2]).resolve()
    stage = Stage(specification, directory)
    try:
        if specification.derived["stage"] == "V11-MAIN":
            result = main_stage(stage)
            stage.finish("MAIN", result)
        elif specification.derived["stage"] == "V11-REPLAY":
            result = replay_stage(stage)
            stage.finish("REPLAY", result)
        else:
            result = verify_stage(stage)
            stage.finish("VERIFY", result)
    except Exception as error:
        write_json(stage.artifact / "worker_failure.json", {
            "error": type(error).__name__ + ": " + str(error),
            "traceback": traceback.format_exc(limit=8),
            "budget_counts": stage.stats,
            "source_sha": stage.meta["source_sha"],
            "window": snapshot(),
        })
        raise


if __name__ == "__main__":
    main()
