"""Thin V8 stages using the existing public runner and supervision."""

import json
import os
import subprocess
import time
from pathlib import Path

import numpy as np

from src.io.neural_fe_calibration import (
    PLAN_PATH,
    V8_ROOT,
    budget_snapshot,
    frozen_plan,
    read_v8_index,
)
from src.io.neural_fe_continuation import DESIGN_PATH, V7_ROOT, read_index
from src.runners.neural_fe_continuation import read_moments
from src.runners.task042_shared import write_json
from src.solvers.neural_fe_action_packet import array_hash, file_hash


def owned_file(record, parent):
    path = Path(record["path"]).resolve()
    if not path.is_relative_to(parent) or file_hash(path) != record["sha256"]:
        raise ValueError("array path/hash ownership failure")
    return path


def publish(name, path):
    with (V8_ROOT / (name + ".json")).open("x") as stream:
        json.dump(dict(path=str(path), sha256=file_hash(path)), stream, indent=2)


def reuse_inventory(packet, moments, moment_record, fe):
    rows = []
    for route, name in (
        ("NEURAL-TRACE", "frozen_neural"),
        ("FREE-FE-OPT", "frozen_free"),
        ("FE-LSQR", "frozen_lsqr"),
    ):
        try:
            frozen, parent = read_index(name)
            path = owned_file(frozen["state"], parent.parent)
            if (
                frozen["operator_packet"] != fe["packet"]
                or frozen["physical"] != fe["physical"]
            ):
                raise ValueError("frozen state operator identity differs")
            with np.load(path, allow_pickle=False) as state:
                shapes = {
                    k: dict(
                        shape=list(state[k].shape),
                        dtype=str(state[k].dtype),
                        sha256=array_hash(state[k]),
                    )
                    for k in state.files
                }
                if array_hash(state["z"]) != frozen["state"]["z_sha256"] or state[
                    "z"
                ].shape != (packet.size,):
                    raise ValueError("frozen z identity differs")
            history = parent.parent / "scalar_history.jsonl"
            rows.append(
                dict(
                    route=route,
                    available=True,
                    result_path=str(parent),
                    result_sha256=file_hash(parent),
                    source_sha=frozen["source_sha"],
                    state=dict(path=str(path), sha256=file_hash(path), arrays=shapes),
                    scalar_history=dict(path=str(history), sha256=file_hash(history)),
                    acceptance_state="NOT_APPLICABLE_LSQR"
                    if route == "FE-LSQR"
                    else "V7_ACCEPTANCE_STATE_UNKNOWN",
                    old_audited_vector_unchanged=True,
                )
            )
        except (OSError, KeyError, ValueError) as error:
            rows.append(dict(route=route, available=False, reason=str(error)))
    try:
        reference, parent = read_index("blind_reference")
        path = owned_file(reference["reference_state"], V7_ROOT)
        reference_record = dict(
            available=True,
            path=str(path),
            sha256=file_hash(path),
            z_sha256=reference["reference_state"]["z_sha256"],
            source_sha=reference["source_sha"],
            solution_decoded=False,
        )
    except (OSError, KeyError, ValueError) as error:
        reference_record = dict(
            available=False, reason=str(error), solution_decoded=False
        )
    return dict(
        status="PASS",
        original_action=dict(
            path=fe["packet"]["path"],
            sha256=fe["packet"]["sha256"],
            source_sha=fe["source_sha"],
            arrays={
                k: dict(
                    shape=list(v.shape),
                    dtype=str(v.dtype),
                    bytes=v.nbytes,
                    sha256=array_hash(v),
                )
                for k, v in packet.a.items()
            },
        ),
        moment_packet=moment_record,
        moment_arrays={
            k: dict(
                shape=list(v.shape),
                dtype=str(v.dtype),
                bytes=v.nbytes,
                sha256=array_hash(v),
            )
            for k, v in moments.items()
        },
        frozen_routes=rows,
        reference_identity=reference_record,
        material_independent_interface_witness_parameters_saved=False,
        witness_fallback="registered seed420908 perturbation; no V6 parameter artifact was persisted",
        operator=dict(
            size=packet.size, trace=packet.nt, ports=packet.np, cells=packet.nc
        ),
        accurate_solution_read=False,
        training_replayed=False,
    )


def run(specification, directory):
    source = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    manifest = json.loads((directory / "run_manifest.json").read_text())
    if source != manifest["source_sha"]:
        raise RuntimeError("source changed after clean launch")
    plan, design, _, fe = frozen_plan()
    stage = specification.derived["stage"]
    artifact = V8_ROOT / stage / directory.name
    artifact.mkdir(parents=True, exist_ok=False)
    began = time.perf_counter()
    budget = budget_snapshot()
    write_json(artifact / "cumulative_budget_before.json", budget)
    if budget["remaining_seconds"] <= 0:
        raise RuntimeError("V8/cumulative budget exhausted")
    from src.solvers.neural_fe_pilot import load_packet

    _, fe_path = read_index("qualified_real_fe")
    packet_path = owned_file(fe["packet"], fe_path.parent)
    packet = load_packet(packet_path)
    moments, provenance = read_moments()
    if stage == "V8-C0":
        result = reuse_inventory(packet, moments, provenance, fe)
        index_name = "reuse_inventory"
    else:
        inventory, _ = read_v8_index("reuse_inventory")
        if inventory["original_action"]["sha256"] != fe["packet"]["sha256"]:
            raise ValueError("reuse inventory operator mismatch")
        if specification.derived["environment_mode"] == "ml":
            from src.solvers.neural_trace_torch import qualify_threads

            threads = qualify_threads()
        else:
            from src.runners.task042_experiment import thread_qualification

            threads = thread_qualification()

        def save(name, value):
            write_json(artifact / (name + ".json"), value)

        def sample():
            path = directory / "supervision/resources.jsonl"
            with path.open("rb") as stream:
                stream.seek(max(0, path.stat().st_size - 65536))
                lines = stream.read().splitlines()
            for line in reversed(lines):
                try:
                    observed = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if (
                    time.time_ns() - observed["timestamp_ns"] > 5_000_000_000
                    or observed["swap_bytes"]
                ):
                    raise RuntimeError("own tree supervision stale or own swap nonzero")
                return observed
            raise RuntimeError("no valid own process-tree sample")

        if stage == "V8-C2-SETUP":
            from src.solvers.neural_fe_column_scaling import prepare_column_scaling

            result = prepare_column_scaling(
                packet, plan["scaling"], artifact, sample=sample, save=save
            )
            index_name = (
                "column_scaling" if result["status"] == "COLUMN_SCALING_READY" else None
            )
        elif stage == "V8-C2-LSQR":
            from src.solvers.neural_fe_column_scaling import check_scaled_actions
            from src.solvers.neural_fe_optimization import optimize_route

            setup, parent = read_v8_index("column_scaling")
            path = owned_file(setup["scale"], parent.parent)
            with np.load(path, allow_pickle=False) as contents:
                D = contents["D"].copy()
            if array_hash(D) != setup["scale"]["D_sha256"]:
                raise ValueError("scale array identity mismatch")
            gate = check_scaled_actions(
                packet, D, plan["scaling"]["scaled_action_seed"]
            )
            save("scaled_action_gate", gate)
            if gate["status"] != "PASS":
                result = dict(
                    status="SCALED_ACTION_GATE_FAILED", scaled_action_gate=gate
                )
                index_name = None
            else:
                result = optimize_route(
                    design,
                    packet,
                    moments,
                    "FE-LSQR-COLUMN-SCALED",
                    artifact,
                    wall_seconds=min(
                        7200 - (time.perf_counter() - began),
                        budget["remaining_seconds"],
                    ),
                    column_scale=D,
                )
                result.update(
                    scaled_action_gate=gate,
                    scale=setup["scale"],
                    setup_result_sha256=file_hash(parent),
                    deployed_ownership="original action packet plus D only; no CSR/reference/factor",
                )
                index_name = "frozen_scaled_lsqr"
        elif stage == "V8-C2-VERIFY":
            from src.solvers.neural_fe_column_scaling import verify_scaled_candidate

            frozen, parent = read_v8_index("frozen_scaled_lsqr")
            reference, reference_path = read_index("blind_reference")
            result = verify_scaled_candidate(
                design,
                packet,
                frozen,
                parent,
                reference,
                reference_path,
                artifact,
                plan,
            )
            index_name = "scaled_verification"
        elif stage in {"V8-C3-EQUIVALENCE", "V8-C3-MICRO"}:
            from src.solvers.neural_fe_batch_calibration import (
                equivalence,
                microbenchmark,
            )

            old, parent = read_index("frozen_neural")
            path = owned_file(old["state"], parent.parent)
            if stage == "V8-C3-EQUIVALENCE":
                result = equivalence(
                    design,
                    packet,
                    moments,
                    path,
                    plan["batch_execution"],
                    sample=sample,
                )
                index_name = "batch_equivalence" if result["status"] == "PASS" else None
            else:
                gate, _ = read_v8_index("batch_equivalence")
                if gate["status"] != "PASS":
                    raise ValueError("batch equivalence Gate required")
                batch = specification.derived["batch_size"]
                pair = specification.derived["pair_id"]
                result = microbenchmark(
                    design,
                    packet,
                    moments,
                    path,
                    plan["batch_execution"],
                    batch,
                    sample=sample,
                )
                result["pair_id"] = pair
                index_name = f"batch_pair{pair}_size{batch}"
        else:
            raise RuntimeError("unregistered V8 stage")
        result["actual_threads"] = threads
    result.update(
        stage=stage,
        source_sha=source,
        input_sha256=specification.input_sha256,
        input_path=str(specification.source_path),
        plan_sha256=file_hash(PLAN_PATH),
        design_sha256=file_hash(DESIGN_PATH),
        physical=fe["physical"],
        operator_packet=fe["packet"],
        operator_source_sha=fe["source_sha"],
        moment_packet=provenance,
        worker_wall_seconds=time.perf_counter() - began,
        affinity=sorted(os.sched_getaffinity(0)),
        math_threads=1,
        mpi_size=1,
        shared_workstation=True,
        artifact_directory=str(artifact),
    )
    path = artifact / "stage_result.json"
    write_json(path, result)
    write_json(directory / "stage_result.json", result)
    if index_name is not None:
        publish(index_name, path)
    print(
        json.dumps(
            dict(
                stage=stage,
                status=result["status"],
                artifact=str(artifact),
                source_sha=source,
            )
        ),
        flush=True,
    )
    if index_name is None:
        raise SystemExit(3)
