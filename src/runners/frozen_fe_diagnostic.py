"""One offline fixed-state stage; reuse public launch and shared watchdog."""

import json
import os
import subprocess
import time
from time import perf_counter

import numpy as np

from src.io.frozen_fe_diagnostic import (
    PLAN_PATH,
    V9_ROOT,
    budget_snapshot,
    plan_and_operator,
    read_frozen_states,
)
from src.io.neural_fe_calibration import read_v8_index
from src.runners.task042_shared import write_json
from src.solvers.neural_fe_action_packet import array_hash, file_hash


def run(specification, directory):
    from src.runners.task042_experiment import thread_qualification
    from src.solvers.frozen_fe_error import (
        FrozenActions,
        error_diagnostics,
        state_audits,
    )
    from src.solvers.frozen_fe_field_localization import field_localization
    from src.solvers.neural_fe_pilot import load_packet

    source = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    manifest = json.loads((directory / "run_manifest.json").read_text())
    if source != manifest["source_sha"]:
        raise RuntimeError("source changed after clean launch")
    artifact = V9_ROOT / directory.name
    artifact.mkdir(parents=True, exist_ok=False)
    began = perf_counter()
    budget = budget_snapshot()
    write_json(artifact / "cumulative_budget_before.json", budget)
    if budget["remaining_seconds"] <= 0:
        raise RuntimeError("V9/cumulative numerical budget exhausted")
    plan, design, _, fe = plan_and_operator()
    threads = thread_qualification()
    timeline = directory / "supervision/resources.jsonl"
    with timeline.open("rb") as stream:
        stream.seek(max(0, timeline.stat().st_size - 65536))
        last = json.loads(stream.read().splitlines()[-1])
    upper = sum(plan["memory_preallocation"].values())
    if (
        time.time_ns() - last["timestamp_ns"] > 5_000_000_000
        or last["swap_bytes"]
        or last["rss_bytes"] + upper >= 12 * 2**30
    ):
        raise MemoryError(
            "own watchdog/capacity prerequisite failed before packet/FE allocations"
        )
    capacity = dict(
        status="PREALLOCATION_PASS",
        allocation_upper_bytes=upper,
        current_sampled_tree_rss_bytes=last["rss_bytes"],
        warning_bytes=12 * 2**30,
        scope="packet copies, worst-case cell gathers, vectors/fields, FE/JIT; derived bound not RSS",
    )
    write_json(artifact / "preallocation_capacity.json", capacity)
    before = perf_counter()
    packet = load_packet(fe["packet"]["path"])
    if file_hash(fe["packet"]["path"]) != plan["action_packet_sha256"]:
        raise ValueError("actual original packet file hash differs")
    reused, _ = read_v8_index("reuse_inventory")
    array_inventory = {}
    for key, value in packet.a.items():
        expected = reused["original_action"]["arrays"][key]
        if (
            array_hash(value) != expected["sha256"]
            or list(value.shape) != expected["shape"]
        ):
            raise ValueError(
                f"original operator/background/RHS/MPC array changed: {key}"
            )
        array_inventory[key] = expected
    states, inventory = read_frozen_states(packet, fe, plan)
    costs = dict(packet_and_six_states_IO_identity=perf_counter() - before)
    write_json(
        artifact / "frozen_state_inventory.json",
        dict(
            states=inventory,
            packet=fe["packet"],
            arrays=array_inventory,
            moment_arrays_loaded=False,
            torch_loaded=False,
            scale_D_loaded=False,
        ),
    )
    actions = FrozenActions(packet)
    before = perf_counter()
    cache, audits = state_audits(actions, states)
    costs["original_state_audits_including_actions"] = perf_counter() - before
    ref_valid = "REF7" in audits and all(
        audits["REF7"][key] <= 1e-10
        for key in (
            "schur_relative",
            "native_relative",
            "augmented_relative",
            "total_augmented_relative",
            "port_operation_relative",
            "recovery_relative",
        )
    )
    errors, checks, fields = {}, {}, None
    if ref_valid:
        before = perf_counter()
        errors, checks = error_diagnostics(actions, cache)
        costs["error_identities_and_equation_components_including_actions"] = (
            perf_counter() - before
        )
        write_json(
            artifact / "error_identity_checks.json", dict(audits=audits, errors=checks)
        )
        valid = all(
            row[key]["operation_relative"] <= 1e-10
            for row in checks.values()
            for key in (
                "residual_identity",
                "homogeneous_recovery",
                "affine_difference",
                "background_cancellation",
                "augmented_identity",
                "native_identity",
            )
        )
        if valid:
            before = perf_counter()
            fields = field_localization(design, packet, cache, errors, fe)
            costs["one_FE_environment_and_all_integrals"] = perf_counter() - before
        else:
            write_json(artifact / "D1_failure.json", checks)
    raw = dict(
        b=packet.a["b"],
        masters=packet.a["masters"],
        Hp=packet.a["Hp"],
        idofs=packet.a["idofs"],
    )
    for name, state in cache.items():
        raw.update({name + "." + key: value for key, value in state.items()})
    for name, row in errors.items():
        raw.update({name + ".error." + key: value for key, value in row.items()})
    before = perf_counter()
    raw_path = artifact / "raw_fixed_error_vectors.npz"
    np.savez(raw_path, **raw)
    raw_sha256 = file_hash(raw_path)
    costs["raw_vector_save_and_hash"] = perf_counter() - before
    port_rows = []
    for name, row in errors.items():
        for index, mode in enumerate(fe["physical"]["full_channel_inventory"]):
            e = row["e"][packet.nt + index]
            ref = states["REF7"][packet.nt + index]
            candidate = states[name][packet.nt + index]
            port_rows.append(
                dict(
                    state=name,
                    index=index,
                    side=mode["side"],
                    m=mode["m"],
                    n=mode["n"],
                    polarization=mode["polarization"],
                    error_real=float(e.real),
                    error_imag=float(e.imag),
                    error_absolute=float(abs(e)),
                    reference_real=float(ref.real),
                    reference_imag=float(ref.imag),
                    candidate_real=float(candidate.real),
                    candidate_imag=float(candidate.imag),
                    reference_plane_nm=design["geometry"]["bounds_nm"][2][
                        1 if mode["side"] == "top" else 0
                    ],
                    normalization="original electric tangential modal projection; no phase fit",
                    mode_manifest_sha256=plan["mode_manifest_sha256"],
                )
            )
    report = dict(
        status="DIAGNOSTIC_MEASUREMENTS_FROZEN",
        stage="V9-D0-D3",
        source_sha=source,
        input_sha256=specification.input_sha256,
        input_path=str(specification.source_path),
        plan_sha256=file_hash(PLAN_PATH),
        physical_model_sha256=plan["physical_model_sha256"],
        mode_manifest_sha256=plan["mode_manifest_sha256"],
        material_table_sha256=plan["material_table_sha256"],
        operator_packet=fe["packet"],
        operator_source_sha=fe["source_sha"],
        state_inventory=inventory,
        array_inventory=array_inventory,
        trace_rows=packet.nt,
        ports=packet.np,
        full_rows=packet.full_rows,
        audits=audits,
        errors=checks,
        fields=fields,
        port_errors=port_rows,
        reference_actual_residual_retained=True,
        raw_vectors=dict(
            path=str(raw_path),
            sha256=raw_sha256,
            payload_bytes=sum(v.nbytes for v in raw.values()),
            arrays={
                k: dict(shape=list(v.shape), dtype=str(v.dtype), sha256=array_hash(v))
                for k, v in raw.items()
            },
        ),
        action_counts=actions.counts,
        action_seconds_nested_not_additive=actions.seconds,
        costs_exclusive_top_level_seconds=costs,
        reference_failure="REFERENCE_ARTIFACT_UNAVAILABLE"
        if "REF7" not in states
        else None
        if ref_valid
        else "REFERENCE_ORIGINAL_RECHECK_FAILED",
        new_training=False,
        new_target_solve=False,
        new_factor=False,
        global_CSR=False,
        moments_loaded=False,
        torch_loaded=False,
        D_loaded=False,
        reference_role="offline diagnostic; no basis/PC/loss/initial state feedback",
        old_fresh_pool="UNCONSUMED_NOT_READ",
        actual_threads=threads,
        affinity=sorted(os.sched_getaffinity(0)),
        mpi_size=1,
        math_threads=1,
        shared_workstation=True,
        artifact_directory=str(artifact),
        preallocation_capacity=capacity,
        worker_wall_seconds=perf_counter() - began,
    )
    from benchmarks.frozen_fe_error_check import check_report

    report["gate"] = check_report(report, raw)
    report["status"] = report["gate"]["status"]
    report["worker_wall_before_final_json_IO_seconds"] = perf_counter() - began
    path = artifact / "stage_result.json"
    write_json(path, report)
    write_json(directory / "stage_result.json", report)
    index = V9_ROOT / "frozen_error_localization.json"
    with index.open("x") as stream:
        json.dump(dict(path=str(path), sha256=file_hash(path)), stream, indent=2)
    print(
        json.dumps(
            dict(
                status=report["status"],
                states=len(states),
                artifact=str(artifact),
                source=source,
            )
        ),
        flush=True,
    )
    if not report["gate"]["identities_pass"]:
        raise SystemExit(3)
