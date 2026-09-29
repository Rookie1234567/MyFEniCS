"""Thin V7 stage adapter; numerical algorithms live in src.solvers."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

from src.io.neural_fe_continuation import (
    DESIGN_PATH,
    V7_ROOT,
    load_continuation,
    read_index,
)
from src.io.task042_profile import ROOT
from src.runners.task042_shared import ARTIFACTS, write_json
from src.solvers.neural_fe_action_packet import file_hash


def budget_snapshot():
    carry = json.loads(DESIGN_PATH.read_text())["budget_carry_in"][
        "V6_supervised_seconds"
    ]
    records = []
    for path in sorted(
        (ROOT / "results/task042").glob("task042_v7_*/run_summary.json")
    ):
        value = json.loads(path.read_text())
        records.append(dict(path=str(path), seconds=value["elapsed_seconds"]))
    for path in sorted((ROOT / "tmp/task042/v7").glob("*/summary.json")):
        value = json.loads(path.read_text())
        records.append(dict(path=str(path), seconds=value["elapsed_seconds"]))
    used = carry + sum(row["seconds"] for row in records)
    return dict(
        carry_in_v6_seconds=carry,
        v7_records=records,
        used_seconds=used,
        remaining_seconds=36000 - used,
        limit_seconds=36000,
        shared_workstation=True,
    )


def publish(name, path):
    V7_ROOT.mkdir(parents=True, exist_ok=True)
    with (V7_ROOT / (name + ".json")).open("x") as stream:
        json.dump(dict(path=str(path), sha256=file_hash(path)), stream, indent=2)


def read_moments():
    entry = json.loads((ARTIFACTS / "v6/qualified_fe_interface.json").read_text())
    result_path = Path(entry["path"]).resolve()
    if (
        not result_path.is_relative_to(ARTIFACTS / "v6")
        or file_hash(result_path) != entry["sha256"]
    ):
        raise ValueError("V6 material-independent moment qualification index mismatch")
    result = json.loads(result_path.read_text())
    record = result["packets"]["15"]
    path = Path(record["path"]).resolve()
    if (
        not path.is_relative_to(result_path.parent)
        or file_hash(path) != record["sha256"]
    ):
        raise ValueError("V6 q15 moment packet integrity failure")
    with np.load(path, allow_pickle=False) as contents:
        packet = {key: np.array(contents[key]) for key in contents.files}
    return packet, dict(
        path=str(path),
        sha256=record["sha256"],
        source_sha=result["source_sha"],
        q15_q30_qualification_reused=True,
        target_material_independent=True,
    )


def main():
    from src.io.frozen_fe_diagnostic import load_diagnostic

    diagnostic = load_diagnostic(sys.argv[1])
    if diagnostic is not None:
        from src.runners.frozen_fe_diagnostic import run

        run(diagnostic, Path(sys.argv[2]).resolve())
        return
    from src.io.neural_fe_calibration import load_calibration

    calibration = load_calibration(sys.argv[1])
    if calibration is not None:
        from src.runners.neural_fe_calibration import run

        run(calibration, Path(sys.argv[2]).resolve())
        return
    specification = load_continuation(sys.argv[1])
    directory = Path(sys.argv[2]).resolve()
    source = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    manifest = json.loads((directory / "run_manifest.json").read_text())
    if source != manifest["source_sha"]:
        raise RuntimeError("runtime source changed after clean launch")
    stage = specification.derived["stage"]
    artifact = V7_ROOT / stage / directory.name
    artifact.mkdir(parents=True, exist_ok=False)
    design = json.loads(DESIGN_PATH.read_text())
    began = time.perf_counter()
    budget = budget_snapshot()
    write_json(artifact / "cumulative_budget_before.json", budget)
    if budget["remaining_seconds"] <= 0:
        raise RuntimeError("cumulative V6+V7 numerical budget exhausted")
    if stage == "V7-M0":
        from src.runners.task042_experiment import thread_qualification
        from src.solvers.neural_fe_pilot import physical_inventory

        result, _ = physical_inventory(design)
        result["actual_blas_pools"] = thread_qualification()
    elif stage == "V7-M1-FE":
        from src.runners.task042_experiment import thread_qualification
        from src.solvers.neural_fe_pilot import build_and_check

        moments, provenance = read_moments()

        def heartbeat(name, value):
            write_json(artifact / (name + ".json"), value)
            print(json.dumps(dict(phase=name)), flush=True)

        packet, result = build_and_check(design, moments, stage_callback=heartbeat)
        result["actual_blas_pools"] = thread_qualification()
        result["moment_packet"] = provenance
        packet_path = artifact / "physical_action_packet.npz"
        start_io = time.perf_counter()
        np.savez(packet_path, **packet.a)
        result["packet"] = dict(
            path=str(packet_path),
            sha256=file_hash(packet_path),
            file_bytes=packet_path.stat().st_size,
        )
        result["costs_exclusive_seconds"]["packet_io_hash"] = (
            time.perf_counter() - start_io
        )
    elif stage == "V7-M1-GRAD":
        from src.solvers.neural_fe_gradient_check import check_real_gradient
        from src.solvers.neural_fe_pilot import load_packet
        from src.solvers.neural_trace_torch import qualify_threads

        threads = qualify_threads()
        fe, fe_path = read_index("qualified_real_fe")
        if (
            fe["status"] != "PASS"
            or fe["design_sha256"] != specification.derived["design_sha256"]
        ):
            raise RuntimeError("real FE N1 Gate required before real ML gradient")
        packet_path = Path(fe["packet"]["path"]).resolve()
        if (
            not packet_path.is_relative_to(fe_path.parent)
            or file_hash(packet_path) != fe["packet"]["sha256"]
        ):
            raise RuntimeError("real FE packet ownership/hash mismatch")
        packet = load_packet(packet_path)
        moments, provenance = read_moments()
        result = check_real_gradient(design, packet, moments)
        result.update(
            threads=threads,
            moment_packet=provenance,
            physical=fe["physical"],
            costs_exclusive_seconds=packet.costs,
            counts=packet.counts,
        )
    elif stage.startswith("V7-M2-"):
        from src.solvers.neural_fe_optimization import optimize_route
        from src.solvers.neural_fe_pilot import load_packet

        grad, _ = read_index("qualified_real_gradient")
        fe, fe_path = read_index("qualified_real_fe")
        if (
            grad["status"] != "PASS"
            or fe["status"] != "PASS"
            or grad["design_sha256"] != specification.derived["design_sha256"]
        ):
            raise RuntimeError("both true N1 Gates required before optimization")
        record = fe["packet"]
        path = Path(record["path"]).resolve()
        if (
            not path.is_relative_to(fe_path.parent)
            or file_hash(path) != record["sha256"]
        ):
            raise RuntimeError("frozen operator/RHS packet ownership/hash failure")
        threads = None
        if stage != "V7-M2-LSQR":
            from src.solvers.neural_trace_torch import qualify_threads

            threads = qualify_threads()
        else:
            from src.runners.task042_experiment import thread_qualification

            threads = thread_qualification()
        packet = load_packet(path)
        moments, provenance = read_moments()
        route = {
            "V7-M2-NEURAL": "NEURAL-TRACE",
            "V7-M2-FREE": "FREE-FE-OPT",
            "V7-M2-LSQR": "FE-LSQR",
        }[stage]
        result = optimize_route(
            design,
            packet,
            moments,
            route,
            artifact,
            wall_seconds=min(7200, budget["remaining_seconds"]),
        )
        result.update(
            threads=threads,
            moment_packet=provenance,
            physical=fe["physical"],
            operator_packet=record,
            operator_source_sha=fe["source_sha"],
            real_gradient_source_sha=grad["source_sha"],
        )
    elif stage in {"V7-M3-REFERENCE", "V7-M3-VERIFY"}:
        from src.runners.task042_experiment import thread_qualification
        from src.solvers.neural_fe_blind_reference import (
            blind_reference,
            verify_saved_reference,
        )
        from src.solvers.neural_fe_pilot import load_packet

        fe, fe_path = read_index("qualified_real_fe")
        record = fe["packet"]
        path = Path(record["path"]).resolve()
        if (
            fe["status"] != "PASS"
            or not path.is_relative_to(fe_path.parent)
            or file_hash(path) != record["sha256"]
        ):
            raise RuntimeError("qualified reference operator packet identity failure")
        routes = {}
        for route, index in (
            ("NEURAL-TRACE", "frozen_neural"),
            ("FREE-FE-OPT", "frozen_free"),
            ("FE-LSQR", "frozen_lsqr"),
        ):
            frozen, _ = read_index(index)
            if (
                frozen["route"] != route
                or frozen["design_sha256"] != specification.derived["design_sha256"]
                or frozen["physical"]["physical_model_sha256"]
                != specification.physical_model_sha256
                or frozen["operator_packet"] != record
            ):
                raise RuntimeError(
                    "three frozen candidates must share the same operator/RHS"
                )
            routes[route] = frozen

        def save(name, value):
            write_json(artifact / (name + ".json"), value)

        def marker(name, value):
            save(name, value)
            print(json.dumps(dict(phase=name)), flush=True)

        def sample():
            # Reuse our supervisor's recent whole-tree RSS, bounded tail only.
            sample_path = directory / "supervision/resources.jsonl"
            with sample_path.open("rb") as stream:
                stream.seek(max(0, sample_path.stat().st_size - 65536))
                lines = stream.read().splitlines()
            for line in reversed(lines):
                try:
                    observed = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if time.time_ns() - observed["timestamp_ns"] > 5_000_000_000:
                    raise RuntimeError("own process-tree supervision sample is stale")
                if observed["swap_bytes"] != 0:
                    raise RuntimeError(
                        "own swap Gate failed before reference factorization"
                    )
                return dict(
                    rss_bytes=observed["rss_bytes"],
                    launch_cap_bytes=observed["launch_cap_bytes"],
                    timestamp_ns=observed["timestamp_ns"],
                )
            raise RuntimeError("no complete own process-tree supervision sample")

        packet = load_packet(path)
        if stage == "V7-M3-VERIFY":
            identity, _ = read_index("reference_resume")
            if identity["physical_model_sha256"] != specification.physical_model_sha256:
                raise RuntimeError("saved reference operator identity mismatch")
            result = verify_saved_reference(design, packet, routes, identity, artifact)
        else:
            result = blind_reference(
                design,
                packet,
                routes,
                artifact,
                sample=sample,
                marker=marker,
                save=save,
            )
        if not any(
            value["status"] == "SAME_DISCRETE_QUALIFIED"
            for value in result["comparisons"].values()
        ):
            result["p4_enrichment"] = "NOT_RUN_NO_SAME_DISCRETE_QUALIFIED_ROUTE"
        result.update(
            actual_blas_pools=thread_qualification(),
            physical=fe["physical"],
            operator_packet=record,
            operator_source_sha=fe["source_sha"],
        )
    else:
        raise RuntimeError("unregistered V7 stage")
    result.update(
        stage=stage,
        source_sha=source,
        design_sha256=file_hash(DESIGN_PATH),
        input_sha256=specification.input_sha256,
        input_path=str(specification.source_path),
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
    if stage == "V7-M0":
        publish("material_inventory", path)
    elif stage in {"V7-M3-REFERENCE", "V7-M3-VERIFY"}:
        publish("blind_reference", path)
    elif stage.startswith("V7-M2-"):
        publish(
            {
                "V7-M2-NEURAL": "frozen_neural",
                "V7-M2-FREE": "frozen_free",
                "V7-M2-LSQR": "frozen_lsqr",
            }[stage],
            path,
        )
    elif result["status"] == "PASS":
        publish(
            "qualified_real_fe" if stage == "V7-M1-FE" else "qualified_real_gradient",
            path,
        )
    print(
        json.dumps(
            dict(
                stage=stage,
                status=result["status"],
                source_sha=source,
                artifact=str(artifact),
            )
        ),
        flush=True,
    )
    if (
        stage != "V7-M0"
        and stage not in {"V7-M3-REFERENCE", "V7-M3-VERIFY"}
        and not stage.startswith("V7-M2-")
        and result["status"] != "PASS"
    ):
        raise SystemExit(3)


if __name__ == "__main__":
    main()
