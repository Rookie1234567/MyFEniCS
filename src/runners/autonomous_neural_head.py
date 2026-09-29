"""Thin V10 stage adapter reusing the Task042 shared subreaper and FE audit."""

import ctypes
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

from src.io.autonomous_neural_head import (
    PLAN_PATH,
    V10_ROOT,
    load_autonomous,
    plan_and_operator,
    publish,
    read_result,
)
from src.io.neural_fe_continuation import V7_ROOT, read_index
from src.io.task042_profile import ROOT
from src.runners.task042_shared import write_json
from src.solvers.autonomous_batch_window import (
    guard_worker_parent,
    journal,
    window_snapshot,
)
from src.solvers.neural_fe_action_packet import array_hash, file_hash


def owned(record, root):
    path = Path(record["path"]).resolve()
    if not path.is_relative_to(root) or file_hash(path) != record["sha256"]:
        raise ValueError("owned artifact path/hash mismatch")
    return path


def original_packet(fe):
    from src.solvers.neural_fe_pilot import load_packet

    return load_packet(owned(fe["packet"], V7_ROOT))


def frozen_nn(packet, fe, *, parameters=False):
    record, result_path = read_index("frozen_neural")
    if (
        record["operator_packet"] != fe["packet"]
        or record["physical"] != fe["physical"]
    ):
        raise ValueError("NN7 saved physical/operator identity differs")
    path = owned(record["state"], result_path.parent)
    with np.load(path, allow_pickle=False) as contents:
        z = np.array(contents["z"])
        weights = np.array(contents["network_parameters"]) if parameters else None
    if z.shape != (packet.size,) or array_hash(z) != record["state"]["z_sha256"]:
        raise ValueError("NN7 saved z identity differs")
    return (
        z,
        weights,
        {
            "state": record["state"],
            "source_sha": record["source_sha"],
            "acceptance_state": "V7_ACCEPTANCE_STATE_UNKNOWN_UNCHANGED",
        },
    )


def original_gate(audit):
    fields = (
        "schur_relative",
        "native_relative",
        "augmented_relative",
        "original_total_augmented_relative",
        "port_full_rhs_relative",
        "port_operation_relative",
    )
    passed = all(np.isfinite(audit[k]) and audit[k] <= 1e-6 for k in fields)
    passed &= audit["recovery_relative"] <= 1e-10 and audit["slave_storage_max"] == 0
    passed &= audit["schur_original_identity_operation_relative"] <= 1e-10
    return {
        "status": "ORIGINAL_EQUATION_PASS" if passed else "ORIGINAL_EQUATION_FAILED",
        "rho": max(
            audit[k]
            for k in ("schur_relative", "native_relative", "port_full_rhs_relative")
        ),
        "thresholds": {
            "equation": 1e-6,
            "recovery": 1e-10,
            "slave_zero": 0,
            "identity": 1e-10,
        },
    }


class Stage:
    def __init__(self, specification, directory):
        self.specification, self.directory = specification, directory
        self.plan, self.design, _, self.fe = plan_and_operator()
        self.stage = specification.derived["stage"][4:]
        self.artifact = V10_ROOT / directory.name
        self.artifact.mkdir(parents=True)
        self.packet = original_packet(self.fe)
        self.began = time.perf_counter()
        self.meta = {
            "source_sha": (directory / "source_sha.txt").read_text().strip(),
            "plan_sha256": file_hash(PLAN_PATH),
            "input_sha256": specification.input_sha256,
            "artifact_directory": str(self.artifact),
            "physical": self.fe["physical"],
            "operator_packet": self.fe["packet"],
            "stage": self.stage,
            "shared_workstation": True,
            "reference_arrays_read": False,
            "global_p4_factor_constructed": False,
            "global_S_or_CSR_constructed": False,
            "hidden_fallback": False,
            "complete_ports": 40,
        }
        if specification.derived["environment_mode"] == "ml":
            from src.solvers.neural_trace_torch import qualify_threads

            self.meta["threads"] = qualify_threads()
        else:
            from src.runners.task042_experiment import thread_qualification

            self.meta["threads"] = thread_qualification()

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
            if (
                time.time_ns() - sample["timestamp_ns"] > 5_000_000_000
                or sample["swap_bytes"]
            ):
                raise RuntimeError("own tree supervision stale or swap nonzero")
            if sample["rss_bytes"] >= 12 * 2**30:
                raise RuntimeError("own warning reached; no new large allocation")
            if window_snapshot()["heavy_remaining_seconds"] <= 0:
                raise RuntimeError("original heavy deadline reached")
            return sample
        raise RuntimeError("no valid own supervision sample")

    def heartbeat(self, event, **fields):
        sample = self.sample()
        row = journal(event, stage=self.stage, rss_bytes=sample["rss_bytes"], **fields)
        print(json.dumps(row), flush=True)

    def freeze(self, name, z, **arrays):
        if not np.isfinite(z).all():
            raise ValueError("nonfinite frozen physical z")
        path = self.artifact / (name + "_state.npz")
        np.savez(path, z=z, **arrays)
        return {
            "path": str(path),
            "sha256": file_hash(path),
            "z_sha256": array_hash(z),
            "z_kind": "physical_canonical_trace_plus_original_forty_ports",
            "shape": list(z.shape),
            "arrays": {
                k: {"shape": list(v.shape), "sha256": array_hash(v)}
                for k, v in arrays.items()
            },
        }

    def finish(self, name, result):
        result.update(
            self.meta,
            action_counts=self.packet.counts,
            action_costs_seconds=self.packet.costs,
            stage_worker_seconds=time.perf_counter() - self.began,
        )
        path = self.artifact / "stage_result.json"
        write_json(path, result)
        publish(name, path)
        write_json(
            self.directory / "artifact_index.json",
            {"path": str(path), "sha256": file_hash(path)},
        )
        self.heartbeat(
            "candidate_or_diagnostic_frozen", result_name=name, status=result["status"]
        )


def amplitude_port(stage):
    from src.solvers.neural_linear_head import thin_lstsq

    packet = stage.packet
    z0, _, identity = frozen_nn(packet, stage.fe)
    audit0 = packet.audit(z0)
    columns = np.empty((packet.size, 41), np.complex128, order="F")
    value = np.zeros(packet.size, np.complex128)
    value[: packet.nt] = z0[: packet.nt]
    columns[:, 0] = packet.apply(value)
    value[:] = 0
    for j in range(40):
        value[packet.nt :] = 0
        value[packet.nt + j] = 1
        columns[:, 1 + j] = packet.apply(value)
    ports_path = stage.artifact / "original_port_columns.npy"
    np.save(ports_path, columns[:, 1:])
    eta0 = np.r_[1 + 0j, z0[packet.nt :]]
    delta, ls = thin_lstsq(columns, packet.a["b"] - columns @ eta0)
    eta = eta0 + delta
    z = np.r_[eta[0] * z0[: packet.nt], eta[1:]]
    audit = packet.audit(z)
    old_loss = 0.5 * audit0["schur_relative"] ** 2
    new_loss = 0.5 * audit["schur_relative"] ** 2
    if new_loss > old_loss + 1e-12 * max(old_loss, 1):
        z, eta, audit, new_loss = z0, eta0, audit0, old_loss
        ls["zero_increment_retained"] = True
    state = stage.freeze("A", z, amplitude=eta[:1], port_coefficients=eta[1:])
    if packet.counts["S"] > 48:
        raise RuntimeError("A original S budget exceeded")
    return {
        "status": "CANDIDATE_FROZEN",
        "state": state,
        "baseline": identity,
        "baseline_audit": audit0,
        "final_audit": audit,
        "original_gate": original_gate(audit),
        "complex_amplitude": eta[0],
        "least_squares": ls,
        "baseline_loss": old_loss,
        "final_loss": new_loss,
        "original_port_columns": {
            "path": str(ports_path),
            "sha256": file_hash(ports_path),
        },
        "internal_recovery": "original affine F(z); particular never scaled",
        "calibration_coefficients_from": "original S and b only",
    }


def model_for_head(stage):
    from src.solvers.neural_trace_checks import assign
    from src.solvers.neural_trace_torch import NeuralTrace

    model = NeuralTrace(stage.design["geometry"]["bounds_nm"], 0.7, seed=420906)
    if stage.stage == "B1":
        z0, parameters, identity = frozen_nn(stage.packet, stage.fe, parameters=True)
        assign(model, parameters)
    else:
        z0 = np.zeros(stage.packet.size, np.complex128)
        identity = {
            "seed": 420906,
            "hidden_origin": "original random initialization",
            "NN7_parameters_read": False,
            "accurate_reference_read": False,
        }
    return model, z0, identity


def solve_child(artifact):
    """Only qualified SciPy action/LS; no Torch, NN7 weights or reference."""
    from src.runners.task042_experiment import thread_qualification
    from src.solvers.neural_linear_head import construct_equation_head

    expected = int(os.environ["TASK042_NUMERICAL_PARENT_PID"])
    library = ctypes.CDLL(None, use_errno=True)
    if library.prctl(1, signal.SIGTERM, 0, 0, 0) or os.getppid() != expected:
        raise RuntimeError("thin LS own numerical parent disappeared")
    threads = thread_qualification()

    _, _, _, fe = plan_and_operator()
    packet = original_packet(fe)
    P = np.load(artifact / "P.npy", mmap_mode="r", allow_pickle=False)
    with np.load(artifact / "head_initial.npz", allow_pickle=False) as state:
        gamma, alpha = np.array(state["gamma"]), np.array(state["alpha"])
    port_path = artifact / "cached_ports.json"
    ports = None
    if port_path.exists():
        record = json.loads(port_path.read_text())
        ports = np.load(owned(record, V10_ROOT), mmap_mode="r", allow_pickle=False)

    def heartbeat(event, **fields):
        journal(event, stage=artifact.name, **fields)
        print(json.dumps(dict(event=event, **fields)), flush=True)

    eta, z, ls, W = construct_equation_head(
        packet,
        P,
        gamma,
        alpha,
        artifact / "W.npy",
        cached_ports=ports,
        heartbeat=heartbeat,
    )
    del W, P
    np.savez(artifact / "head_solution.npz", eta=eta, z=z)
    write_json(
        artifact / "head_ls.json",
        {
            "least_squares": ls,
            "action_counts": packet.counts,
            "action_costs_seconds": packet.costs,
            "threads": threads,
        },
    )


def linear_head(stage):
    from src.runners.neural_fe_continuation import read_moments
    from src.solvers.neural_linear_head import thin_capacity
    from src.solvers.neural_linear_head_torch import (
        assign_head,
        build_head_mapping,
        head_coefficients,
    )
    from src.solvers.neural_trace_batched import BatchedMoments
    from src.solvers.neural_trace_checks import parameters
    from src.solvers.neural_trace_torch import packet_forward

    model, z0, baseline = model_for_head(stage)
    moments, moment_identity = read_moments()
    cache = BatchedMoments(model, moments, resource_sample=stage.sample())
    regenerated = cache.forward(model)
    pair = float(
        np.linalg.norm(regenerated - z0[: stage.packet.nt])
        / max(np.linalg.norm(regenerated), np.linalg.norm(z0[: stage.packet.nt]), 1e-12)
    )
    if pair > 1e-10:
        raise ValueError(
            "NN7 parameters do not regenerate saved trace; B1 blocked only"
        )
    audit0 = stage.packet.audit(z0)
    capacity = thin_capacity(
        stage.packet.size,
        1600,
        stage.packet.nt,
        1560,
        sum(a.nbytes for a in stage.packet.a.values()),
        cache.cache_bytes,
    )
    stage.heartbeat("pre_thin_allocation", capacity=capacity)
    gamma0 = head_coefficients(model)
    P, mapping = build_head_mapping(
        model, cache, stage.artifact / "P.npy", stage.heartbeat
    )
    # A nonzero deterministic witness checks coefficient order and original
    # packet_forward even for B0's zero starting output, before any solving.
    rng = np.random.default_rng(421011)
    witness = 0.001 * (rng.normal(size=1560) + 1j * rng.normal(size=1560))
    assign_head(model, witness)
    actual = packet_forward(model, moments)
    witness_pair = float(
        np.linalg.norm(actual - P @ witness) / max(np.linalg.norm(actual), 1e-12)
    )
    assign_head(model, gamma0)
    if witness_pair > 1e-10:
        raise ValueError("real original Nedelec head mapping witness failed")
    del P
    np.savez(
        stage.artifact / "head_initial.npz", gamma=gamma0, alpha=z0[stage.packet.nt :]
    )
    try:
        result_A, _ = read_result("A")
        ports = result_A["original_port_columns"]
        owned(ports, V10_ROOT)
        write_json(stage.artifact / "cached_ports.json", ports)
    except FileNotFoundError:
        pass
    # Reuse an existing qualified environment rather than contaminating ML.
    # bash exec preserves this child identity for the inherited subreaper.
    child = subprocess.run(
        [
            "bash",
            "-c",
            'source scripts/activate_task042.sh pure; exec python -m src.runners.autonomous_neural_head --linear-solve "$1"',
            "task042-qualified-ls",
            str(stage.artifact),
        ],
        check=False,
        env=dict(os.environ, TASK042_NUMERICAL_PARENT_PID=str(os.getpid())),
    )
    if child.returncode:
        raise RuntimeError("qualified thin LS child failed; retain partial evidence")
    head = json.loads((stage.artifact / "head_ls.json").read_text())
    with np.load(stage.artifact / "head_solution.npz", allow_pickle=False) as solution:
        eta, solved_z = np.array(solution["eta"]), np.array(solution["z"])
    assign_head(model, eta[:1560])
    true_trace = packet_forward(model, moments)
    z = np.r_[true_trace, eta[1560:]]
    output_pair = float(
        np.linalg.norm(z - solved_z)
        / max(np.linalg.norm(z), np.linalg.norm(solved_z), 1e-12)
    )
    if output_pair > 1e-10:
        raise ValueError(
            "solved output head cannot regenerate its actual original trace"
        )
    audit = stage.packet.audit(z)
    state = stage.freeze(
        stage.stage,
        z,
        network_parameters=parameters(model),
        gamma=eta[:1560],
        port_coefficients=eta[1560:],
    )
    totalS = stage.packet.counts["S"] + head["action_counts"]["S"]
    if totalS > 1700:
        raise RuntimeError("B equivalent original S budget exceeded")
    return {
        "status": "CANDIDATE_FROZEN",
        "state": state,
        "baseline": baseline,
        "baseline_audit": audit0,
        "final_audit": audit,
        "original_gate": original_gate(audit),
        "baseline_trace_saved_pair": pair,
        "head_original_moment_witness_pair": witness_pair,
        "rewritten_output_trace_pair": output_pair,
        "least_squares": head["least_squares"],
        "child_action_counts": head["action_counts"],
        "child_action_costs_seconds": head["action_costs_seconds"],
        "total_S_calls": totalS,
        "capacity": capacity,
        "mapping": mapping,
        "cache": cache.identity(),
        "original_moments": moment_identity,
        "P": {
            "path": str(stage.artifact / "P.npy"),
            "sha256": file_hash(stage.artifact / "P.npy"),
            "shape": [stage.packet.nt, 1560],
        },
        "W": {
            "path": str(stage.artifact / "W.npy"),
            "sha256": file_hash(stage.artifact / "W.npy"),
            "shape": [stage.packet.size, 1600],
        },
    }


def verify_candidate(stage):
    from src.solvers.neural_fe_blind_reference import independent_physics

    name = stage.specification.derived["candidate"]
    candidate, _ = read_result(name)
    state_path = owned(candidate["state"], V10_ROOT)
    with np.load(state_path, allow_pickle=False) as data:
        z = np.array(data["z"])
    if array_hash(z) != candidate["state"]["z_sha256"]:
        raise ValueError("candidate changed after freeze")
    reference_record, _ = read_index("blind_reference")
    ref_path = owned(reference_record["reference_state"], V7_ROOT)
    with np.load(ref_path, allow_pickle=False) as data:
        reference = np.array(data["z"])
    if (
        file_hash(ref_path)
        != "a0610a5a55e7508196b17277e706595c33e4398ace82b245f70b656e6b9ed355"
    ):
        raise ValueError("reviewed saved p3 reference differs")
    stage.meta["reference_arrays_read"] = True
    stage.heartbeat("post_freeze_independent_physics", candidate=name)
    physics, comparisons = independent_physics(
        stage.design, stage.packet, reference, {name: z}, stage.artifact
    )
    row, ref = physics["rows"][name], physics["rows"]["REFERENCE"]
    field_keys = (
        "full_FE_L2_relative",
        "full_FE_scaled_curl_relative",
        "scattered_FE_L2_relative",
        "scattered_scaled_curl_relative",
        "selected_E_relative",
        "selected_H_relative",
    )
    eq = original_gate(row["audit"])
    same = bool(
        eq["status"] == "ORIGINAL_EQUATION_PASS" and physics["reference_native_pass"]
    )
    same &= all(np.isfinite(row[k]) and row[k] <= 1e-4 for k in field_keys)
    same &= row["audit"]["independent_DOLFINx_total_native_relative"] <= 1e-6
    comparison = comparisons[name]
    same &= comparison["ordered_complex_ports_relative"] <= 1e-4
    same &= all(v <= 1e-5 for v in comparison["power_absolute_differences"].values())
    same &= (
        comparison["max_channel_power_difference"] <= 1e-6
        and comparison["energy_closure_absolute"] <= 1e-5
    )
    baseline = candidate["baseline_audit"]
    base_rho = original_gate(baseline)["rho"]
    strong = (
        eq["rho"] <= 0.1
        and row["scattered_FE_L2_relative"] <= 0.25
        and row["scattered_scaled_curl_relative"] <= 0.25
    )
    positive = (
        eq["rho"] <= 0.5 * base_rho
        and row["scattered_FE_L2_relative"] <= 0.5
        and row["audit"]["native_relative"] <= baseline["native_relative"]
    )
    signal = (
        "P+"
        if strong
        else "P"
        if positive
        else "F"
        if row["scattered_FE_L2_relative"] <= 0.25
        else "NEGATIVE"
    )
    return {
        "status": "SAME_DISCRETE_QUALIFIED" if same else "NOT_QUALIFIED",
        "candidate": name,
        "candidate_frozen_identity": candidate["state"],
        "candidate_source_sha": candidate["source_sha"],
        "reference_identity": reference_record["reference_state"],
        "reference_only_after_candidate_freeze": True,
        "original_gate": eq,
        "baseline_rho": base_rho,
        "progress_signal": signal,
        "E_admitted": signal in ("P+", "P") and not same,
        "physics": physics,
        "comparison": comparison,
        "actual_scattered_curl_gate_checked": True,
        "field_errors": {k: row[k] for k in field_keys},
        "reference_actual_audit": ref["audit"],
        "official_candidate_results": bool(same),
    }


def head_inventory_checks(stage):
    from src.runners.neural_fe_continuation import read_moments
    from src.solvers.neural_linear_head_torch import assign_head, head_coefficients
    from src.solvers.neural_trace_checks import assign
    from src.solvers.neural_trace_torch import NeuralTrace, packet_forward

    moments, moment_identity = read_moments()
    rows = []
    for name in ("B1", "B0"):
        try:
            result, _ = read_result(name)
        except FileNotFoundError:
            rows.append({"candidate": name, "status": "UNAVAILABLE"})
            continue
        P = np.load(owned(result["P"], V10_ROOT), mmap_mode="r", allow_pickle=False)
        with np.load(owned(result["state"], V10_ROOT), allow_pickle=False) as data:
            parameters = np.array(data["network_parameters"])
            z = np.array(data["z"])
        model = NeuralTrace(stage.design["geometry"]["bounds_nm"], 0.7, seed=420906)
        assign(model, parameters)
        gamma = head_coefficients(model)
        final_trace = packet_forward(model, moments)
        final_pair = float(
            np.linalg.norm(final_trace - z[: stage.packet.nt])
            / max(np.linalg.norm(final_trace), 1e-12)
        )
        final_P_pair = float(
            np.linalg.norm(final_trace - P @ gamma)
            / max(np.linalg.norm(final_trace), 1e-12)
        )
        witnesses = []
        for seed in (421011, 421012, 421013):
            rng = np.random.default_rng(seed)
            witness = 0.001 * (rng.normal(size=1560) + 1j * rng.normal(size=1560))
            assign_head(model, witness)
            actual = packet_forward(model, moments)
            predicted = P @ witness
            scale = max(np.linalg.norm(actual), np.linalg.norm(predicted), 1e-12)
            pair = float(np.linalg.norm(actual - predicted) / scale)
            witnesses.append(
                {
                    "seed": seed,
                    "nonzero_trace_norm": float(np.linalg.norm(actual)),
                    "original_moment_relative": pair,
                    "passed": pair <= 1e-10,
                }
            )
        passed = (
            all(x["passed"] for x in witnesses)
            and max(final_pair, final_P_pair) <= 1e-10
        )
        rows.append(
            {
                "candidate": name,
                "status": "PASS" if passed else "FAIL",
                "P_identity": result["P"],
                "frozen_state": result["state"],
                "witnesses": witnesses,
                "regenerated_saved_trace_pair": final_pair,
                "regenerated_P_gamma_trace_pair": final_P_pair,
                "original_source_sha": result["source_sha"],
                "thin_factorization_repeated": False,
            }
        )
        del P, model
    return {
        "status": "PASS"
        if rows and all(r["status"] == "PASS" for r in rows)
        else "PARTIAL_OR_FAILED",
        "rows": rows,
        "original_moments": moment_identity,
        "threshold": 1e-10,
        "purpose": "complete three fixed nonzero real witnesses without rerunning B LS",
    }


def rewrite_head(artifact, base_name):
    from src.runners.neural_fe_continuation import read_moments
    from src.solvers.neural_linear_head_torch import assign_head
    from src.solvers.neural_trace_checks import assign, parameters
    from src.solvers.neural_trace_torch import (
        NeuralTrace,
        packet_forward,
        qualify_threads,
    )

    threads = qualify_threads()
    _, design, _, _ = plan_and_operator()
    base, _ = read_result(base_name)
    with np.load(owned(base["state"], V10_ROOT), allow_pickle=False) as data:
        weights = np.array(data["network_parameters"])
    with np.load(artifact / "head_solution.npz", allow_pickle=False) as data:
        gamma = np.array(data["gamma"])
        expected = np.array(data["z"])
    model = NeuralTrace(design["geometry"]["bounds_nm"], 0.7, seed=420906)
    assign(model, weights)
    assign_head(model, gamma)
    moments, _ = read_moments()
    trace = packet_forward(model, moments)
    nt = len(trace)
    pair = float(
        np.linalg.norm(trace - expected[:nt])
        / max(np.linalg.norm(trace), np.linalg.norm(expected[:nt]), 1e-12)
    )
    np.savez(
        artifact / "rewritten_network.npz",
        network_parameters=parameters(model),
        trace=trace,
    )
    write_json(
        artifact / "rewrite_check.json",
        {
            "status": "PASS" if pair <= 1e-10 else "FAIL",
            "trace_pair": pair,
            "threads": threads,
        },
    )


def closed_candidate(stage):
    from src.solvers.neural_port_closed_head import (
        close_ports,
        real_port_algebra,
        solve_closed_head,
    )

    checks, _ = read_result("HEAD_CHECK")
    if checks["status"] != "PASS":
        return {"status": "BLOCKED_REAL_HEAD_MAPPING_GATE", "head_checks": checks}
    try:
        base, _ = read_result("B1")
        base_name = "B1"
    except FileNotFoundError:
        base, _ = read_result("B0")
        base_name = "B0"
    P = np.load(owned(base["P"], V10_ROOT), mmap_mode="r", allow_pickle=False)
    W = np.load(owned(base["W"], V10_ROOT), mmap_mode="r", allow_pickle=False)
    with np.load(owned(base["state"], V10_ROOT), allow_pickle=False) as state:
        gamma0 = np.array(state["gamma"])
    stage.heartbeat("C_original_Hhat_algebra", base_candidate=base_name)
    algebra = real_port_algebra(stage.packet, W[:, 1560:])
    if algebra["status"] != "PASS":
        return {"status": algebra["status"], "port_closure_checks": algebra}
    gamma, z, ls = solve_closed_head(
        stage.packet, P, W, gamma0, heartbeat=stage.heartbeat
    )
    del P, W
    np.savez(stage.artifact / "head_solution.npz", gamma=gamma, z=z)
    # Original neural output-layer writing in the isolated CPU ML environment.
    child = subprocess.run(
        [
            "bash",
            "-c",
            'source scripts/activate_task042.sh ml; exec python -m src.runners.autonomous_neural_head --rewrite-head "$1" "$2"',
            "task042-qualified-head",
            str(stage.artifact),
            base_name,
        ],
        check=False,
        env=dict(os.environ, TASK042_NUMERICAL_PARENT_PID=str(os.getpid())),
    )
    if child.returncode:
        raise RuntimeError("C actual network rewrite child failed")
    rewrite = json.loads((stage.artifact / "rewrite_check.json").read_text())
    with np.load(stage.artifact / "rewritten_network.npz", allow_pickle=False) as state:
        weights = np.array(state["network_parameters"])
        trace = np.array(state["trace"])
    z, true_port_seconds = close_ports(stage.packet, trace)
    ls["real_rewritten_trace_port_closure_seconds"] = true_port_seconds
    audit = stage.packet.audit(z)
    frozen = stage.freeze(
        "C",
        z,
        network_parameters=weights,
        gamma=gamma,
        port_coefficients=z[stage.packet.nt :],
    )
    if stage.packet.counts["S"] > 100:
        raise RuntimeError("C new original S budget exceeded")
    return {
        "status": "CANDIDATE_FROZEN"
        if rewrite["status"] == "PASS"
        else "HEAD_REWRITE_IDENTITY_FAILED",
        "state": frozen,
        "baseline": {"candidate": base_name, "state": base["state"]},
        "baseline_audit": base["final_audit"],
        "final_audit": audit,
        "original_gate": original_gate(audit),
        "port_closure_checks": algebra,
        "rewrite_check": rewrite,
        "least_squares": ls,
        "feature_origin": base_name,
        "P": base["P"],
        "W": base["W"],
        "cached_thin_action_reused": True,
        "Hhat_not_Hp": True,
    }


def saved_reference():
    result, _ = read_index("blind_reference")
    path = owned(result["reference_state"], V7_ROOT)
    if (
        file_hash(path)
        != "a0610a5a55e7508196b17277e706595c33e4398ace82b245f70b656e6b9ed355"
    ):
        raise ValueError("reviewed reference hash differs")
    with np.load(path, allow_pickle=False) as data:
        reference = np.array(data["z"])
    if array_hash(reference) != result["reference_state"]["z_sha256"]:
        raise ValueError("reference z array hash differs")
    return reference, result["reference_state"]


def representation_diagnostic(stage):
    from src.solvers.neural_fe_blind_reference import independent_physics
    from src.solvers.neural_linear_head import thin_lstsq

    journal("D_REFERENCE_BARRIER", stage="D1", no_more_A_B_C_E_this_batch=True)
    reference, identity = saved_reference()
    stage.meta["reference_arrays_read"] = True
    states = {}
    records = []
    for name in ("B1", "B0"):
        try:
            base, _ = read_result(name)
        except FileNotFoundError:
            records.append({"candidate": name, "status": "P_UNAVAILABLE"})
            continue
        P = np.load(owned(base["P"], V10_ROOT), mmap_mode="r", allow_pickle=False)
        stage.heartbeat("D_reference_trace_fit", feature_origin=name)
        gamma, ls = thin_lstsq(P, reference[: stage.packet.nt])
        trace = P @ gamma
        relative = float(
            np.linalg.norm(trace - reference[: stage.packet.nt])
            / np.linalg.norm(reference[: stage.packet.nt])
        )
        diagnostic = name + "_REFERENCE_ASSISTED"
        states[diagnostic] = np.r_[trace, reference[stage.packet.nt :]]
        records.append(
            {
                "candidate": name,
                "status": "REFERENCE_ASSISTED_DIAGNOSTIC_ONLY",
                "trace_relative_error": relative,
                "least_squares": ls,
                "P_identity": base["P"],
                "trace_fit_weights_not_published_to_solver": True,
                "reference_ports_used": True,
            }
        )
        del P, gamma
    physics, comparison = independent_physics(
        stage.design, stage.packet, reference, states, stage.artifact
    )
    for record in records:
        if record["candidate"] + "_REFERENCE_ASSISTED" not in states:
            continue
        name = record["candidate"] + "_REFERENCE_ASSISTED"
        row = physics["rows"][name]
        record["scattered_FE_L2_relative"] = row["scattered_FE_L2_relative"]
        record["scattered_scaled_curl_relative"] = row["scattered_scaled_curl_relative"]
        record["diagnostic_state"] = stage.freeze(name, states[name])
        record["original_audit"] = row["audit"]
        record["representation_label"] = (
            "PHYSICS_OBJECTIVE_OR_OPTIMIZATION_LIMITATION_SUPPORTED"
            if max(
                row["scattered_FE_L2_relative"], row["scattered_scaled_curl_relative"]
            )
            <= 1e-4
            else "FROZEN_FEATURE_LIMITATION_SUPPORTED"
        )
        if record["least_squares"]["effective_rank"] < 1560:
            record["representation_label"] = "INCONCLUSIVE_NUMERICAL_RANK_TRUNCATION"
    return {
        "status": "DIAGNOSTIC_COMPLETED",
        "records": records,
        "reference_identity": identity,
        "physics": physics,
        "comparison": comparison,
        "reference_feedback_to_any_solver": False,
        "new_solve_qualification": False,
        "frozen_feature_not_entire_nonlinear_network_limit": True,
    }


def body_balance_diagnostic(stage):
    from src.io.neural_fe_calibration import V8_ROOT, read_v8_index
    from src.solvers.neural_volume_balance import volume_balance

    reference, identity = saved_reference()
    stage.meta["reference_arrays_read"] = True
    old = json.loads(
        (ROOT / "input/task042_neural_coarse_inverse/frozen_error_v9.json").read_text()
    )
    row = next(x for x in old["states"] if x["id"] == "LSQR8")
    scaled, _ = read_v8_index(row["index"])
    with np.load(owned(scaled["state"], V8_ROOT), allow_pickle=False) as data:
        z = np.array(data["z"])
    if array_hash(z) != row["z_sha256"]:
        raise ValueError(
            "original LSQR8 physical z differs; D must not be applied again"
        )
    states = {"LSQR8": z}
    candidates = []
    for name in ("A", "B1", "B0", "C", "E1", "E2"):
        try:
            check, _ = read_result("VERIFY_" + name)
            candidates.append((check["original_gate"]["rho"], name))
        except FileNotFoundError:
            pass
    if candidates:
        _, name = min(candidates)
        result, _ = read_result(name)
        with np.load(owned(result["state"], V10_ROOT), allow_pickle=False) as data:
            states[name] = np.array(data["z"])
    result = volume_balance(
        stage.design,
        stage.packet,
        reference,
        states,
        stage.artifact,
        heartbeat=stage.heartbeat,
    )
    result.update(
        reference_identity=identity,
        LSQR8_identity=scaled["state"],
        new_candidate_inventory=list(states)[1:],
        candidate_selection="lowest original rho only, at most one",
        accurate_reference_feedback=False,
    )
    return result


def body_balance_replay(stage):
    """One saved-vector audit after D2's metadata-only serialization failure."""
    from src.io.neural_fe_calibration import V8_ROOT, read_v8_index

    directories = sorted(
        (ROOT / "results/task042").glob("task042_v10_d2_*/run_summary.json")
    )
    if len(directories) != 1:
        raise ValueError(
            "exactly one original failed D2 run required; no best-run selection"
        )
    path = directories[0]
    run = json.loads(path.read_text())
    manifest = json.loads((path.parent / "run_manifest.json").read_text())
    log = (path.parent / "supervision/worker.log").read_text()
    if (
        run["classification"] != "WORKER_FAILED"
        or not run["descendants_cleared"]
        or "TypeError: mappingproxy" not in log
        or manifest["plan_sha256"] != file_hash(PLAN_PATH)
    ):
        raise ValueError("replay restricted to saved complete D2 serialization failure")
    old_artifact = V10_ROOT / path.parent.name
    files = {
        name: old_artifact / (name.lower() + "_volume_actions.npz")
        for name in ("REF7_SCATTERED", "LSQR8_ERROR", "C_ERROR")
    }
    inventory = {
        name: {"path": str(file), "sha256": file_hash(file)}
        for name, file in files.items()
    }
    write_json(stage.artifact / "raw_inventory_before_decode.json", inventory)
    reference, ref_identity = saved_reference()
    reference_field = stage.packet.recover(reference)
    old = json.loads(
        (ROOT / "input/task042_neural_coarse_inverse/frozen_error_v9.json").read_text()
    )
    row = next(x for x in old["states"] if x["id"] == "LSQR8")
    scaled, _ = read_v8_index(row["index"])
    with np.load(owned(scaled["state"], V8_ROOT), allow_pickle=False) as data:
        scaled_z = np.array(data["z"])
    C, _ = read_result("C")
    with np.load(owned(C["state"], V10_ROOT), allow_pickle=False) as data:
        C_z = np.array(data["z"])
    expected = {"REF7_SCATTERED": reference_field}
    homogeneous = {}
    for name, z in (("LSQR8", scaled_z), ("C", C_z)):
        field = stage.packet.recover(
            reference - z, rhs_i=np.zeros_like(stage.packet.a["i_rhs"])
        )
        full_difference = reference_field - stage.packet.recover(z)
        pair = float(
            np.linalg.norm(field - full_difference) / max(np.linalg.norm(field), 1e-12)
        )
        if pair > 1e-10:
            raise ValueError("saved-vector replay homogeneous identity failed")
        expected[name + "_ERROR"] = field
        homogeneous[name] = {
            "homogeneous_recovery_pair": pair,
            "error_z_sha256": array_hash(reference - z),
        }
    rows = []
    for name, record in inventory.items():
        with np.load(owned(record, old_artifact), allow_pickle=False) as data:
            field = np.array(data["field"])
            curl = np.array(data["curl"])
            mass = np.array(data["negative_epsilon_mass"])
            original = np.array(data["original_V"])
        arrays = (field, curl, mass, original)
        if not all(
            a.shape == (stage.packet.full_rows,)
            and a.dtype == np.complex128
            and np.isfinite(a).all()
            for a in arrays
        ):
            raise ValueError("saved original full FE split action inventory differs")
        field_pair = float(
            np.linalg.norm(field - expected[name]) / max(np.linalg.norm(field), 1e-12)
        )
        total = curl + mass
        cross = np.vdot(curl, mass)
        norms = [
            float(np.linalg.norm(value)) for value in (curl, mass, original, total)
        ]
        pair = float(np.linalg.norm(total - original) / max(sum(norms[:3]), 1e-12))
        expanded = float(norms[0] ** 2 + norms[1] ** 2 + 2 * cross.real)
        square_pair = abs(expanded - norms[3] ** 2) / max(
            norms[0] ** 2 + norms[1] ** 2 + 2 * abs(cross), 1e-24
        )
        if max(pair, square_pair, field_pair) > 1e-10:
            raise ValueError("saved split action/field identity failed")
        rows.append(
            {
                "state": name,
                "field_coefficient_norm": float(np.linalg.norm(field)),
                "curl_norm": norms[0],
                "negative_epsilon_mass_norm": norms[1],
                "original_V_norm": norms[2],
                "combined_norm": norms[3],
                "complex_curl_mass_inner_product": cross,
                "expanded_square": expanded,
                "combined_square": norms[3] ** 2,
                "split_original_V_operation_relative": pair,
                "cross_identity_operation_relative": square_pair,
                "split_original_V_result_relative": float(
                    np.linalg.norm(total - original) / max(norms[2], 1e-12)
                ),
                "cancellation_ratio": norms[3] / max(norms[0] + norms[1], 1e-12),
                "saved_field_recovery_pair": field_pair,
                "raw": record,
                "array_sha256": {
                    k: array_hash(a)
                    for k, a in zip(
                        ("field", "curl", "mass", "original_V"), arrays, strict=True
                    )
                },
                "original_boundary_body_norm": 0.0,
                "boundary_reason": "original no-PML/no-Robin DtN body; port coupling retained separately",
                "shared_contributions_assembled_before_norm": True,
                "condition_number_claimed": False,
            }
        )
    stage.meta["reference_arrays_read"] = True
    return {
        "status": "DIAGNOSTIC_REPLAYED_FROM_SAVED_VECTORS",
        "rows": rows,
        "homogeneous_recovery": homogeneous,
        "failed_original_run": {
            "path": str(path),
            "sha256": file_hash(path),
            "manifest": manifest,
        },
        "original_numerical_source_sha": manifest["source_sha"],
        "raw_hash_anchor": "first frozen during replay; original JSON publication failed",
        "operator_actions_original": {
            "curl": 3,
            "mass": 3,
            "packet_V": 3,
            "kind": "derived from complete saved inventory and source loop",
        },
        "operator_actions_replay": {"curl": 0, "mass": 0, "packet_V": 0},
        "component_original_costs_seconds": "UNKNOWN_NOT_PERSISTED_BEFORE_METADATA_FAILURE",
        "original_inclusive_supervised_seconds": run["elapsed_seconds"],
        "reference_identity": ref_identity,
        "FE_environment_rebuilt": False,
        "global_factor_constructed": False,
        "numerical_vectors_changed": False,
        "accurate_reference_feedback": False,
    }


def main():
    if sys.argv[1] == "--linear-solve":
        solve_child(Path(sys.argv[2]).resolve())
        return
    if sys.argv[1] == "--rewrite-head":
        expected = int(os.environ["TASK042_NUMERICAL_PARENT_PID"])
        library = ctypes.CDLL(None, use_errno=True)
        if library.prctl(1, signal.SIGTERM, 0, 0, 0) or os.getppid() != expected:
            raise RuntimeError("own head rewrite parent disappeared")
        rewrite_head(Path(sys.argv[2]).resolve(), sys.argv[3])
        return
    guard_worker_parent()
    specification = load_autonomous(sys.argv[1])
    directory = Path(sys.argv[2]).resolve()
    stage = Stage(specification, directory)
    if stage.stage in ("A", "B1", "B0", "C", "E1", "E2"):
        barrier = ROOT / "tmp/task042/v10/progress_journal.jsonl"
        if barrier.exists() and any(
            json.loads(line)["event"] == "D_REFERENCE_BARRIER"
            for line in barrier.read_text().splitlines()
        ):
            raise RuntimeError(
                "reference diagnostic barrier closed every solver/training path tonight"
            )
    stage.heartbeat("worker_admitted", original_S_shape=[stage.packet.size] * 2)
    if stage.stage == "A":
        result, name = amplitude_port(stage), "A"
    elif stage.stage in ("B1", "B0"):
        result, name = linear_head(stage), stage.stage
    elif stage.stage == "VERIFY":
        result, name = (
            verify_candidate(stage),
            "VERIFY_" + specification.derived["candidate"],
        )
    elif stage.stage == "HEAD_CHECK":
        result, name = head_inventory_checks(stage), "HEAD_CHECK"
    elif stage.stage == "C":
        result, name = closed_candidate(stage), "C"
    elif stage.stage == "D1":
        result, name = representation_diagnostic(stage), "D1"
    elif stage.stage == "D2":
        result, name = body_balance_diagnostic(stage), "D2"
    elif stage.stage == "D2_REPLAY":
        result, name = body_balance_replay(stage), "D2_REPLAY"
    else:
        raise RuntimeError(
            "backup interface not yet implemented; never start unimplemented stage"
        )
    stage.finish(name, result)


if __name__ == "__main__":
    main()
