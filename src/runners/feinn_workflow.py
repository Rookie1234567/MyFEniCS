"""Task-local single-stage orchestration and immutable artifact provenance."""

import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from time import perf_counter

from benchmarks.subreaper_watchdog import supervise
from src.io.feinn_pilot import DESIGN, ROOT
from src.runners.feinn_resources import ARTIFACTS, Health, admission, envelope


def write_json(path, value):
    def convert(item):
        if isinstance(item, complex):
            return {"real": item.real, "imag": item.imag}
        if hasattr(item, "tolist"):
            return item.tolist()
        raise TypeError(type(item).__name__)

    # Array lists may contain complex numbers; JSON recursively invokes convert.
    Path(path).write_text(
        json.dumps(
            value, ensure_ascii=False, indent=2, allow_nan=False, default=convert
        )
        + "\n"
    )


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while block := stream.read(2**20):
            digest.update(block)
    return digest.hexdigest()


def index_path(stage):
    return ARTIFACTS / ("index_" + stage.lower().replace("-", "_") + ".json")


def load_index(stage):
    item = json.loads(index_path(stage).read_text())
    for key, entry in item["files"].items():
        path = Path(entry["path"]).resolve()
        if not path.is_relative_to(ARTIFACTS.resolve()) or sha(path) != entry["sha256"]:
            raise ValueError(f"ARTIFACT_IDENTITY_FAILED: {stage}/{key}")
    return item


def publish(stage, directory, result, files):
    record = dict(
        schema="task42extra.immutable-stage.v1",
        stage=stage,
        source_sha=json.loads((directory / "run_manifest.json").read_text())[
            "source_sha"
        ],
        run_directory=str(directory),
        result=result,
        files={k: dict(path=str(p.resolve()), sha256=sha(p)) for k, p in files.items()},
    )
    path = index_path(stage)
    if path.exists():
        raise RuntimeError("STAGE_ALREADY_PUBLISHED: no overwrite or automatic rerun")
    write_json(path, record)
    return record


def budget():
    entries = []
    for pattern, base in [
        ("*/summary.json", ROOT / "tmp/task42extra/checks"),
        ("*/run_summary.json", ROOT / "results/task42extra"),
    ]:
        for path in base.glob(pattern):
            item = json.loads(path.read_text())
            entries.append(dict(path=str(path), seconds=item.get("elapsed_seconds", 0)))
    used = sum(e["seconds"] for e in entries)
    v2_used = sum(e["seconds"] for e in entries if
                  "/task42extra_v2_" in e["path"] or
                  "/v2_" in e["path"].split("/checks/")[-1])
    return dict(
        limit_seconds=57600,
        used_seconds=used,
        remaining_seconds=57600 - max(used, 26240.100355625153 + v2_used),
        conservative_V1_base_seconds=26240.100355625153,
        v2_limit_seconds=14400,
        v2_used_seconds=v2_used,
        v2_remaining_seconds=14400 - v2_used,
        entries=entries,
    )


def launch(spec):
    if Path.cwd().resolve() != ROOT or os.environ.get("TASK42EXTRA_ACTIVATION") != "1":
        raise RuntimeError("native task-local activation required")
    branch = subprocess.check_output(
        ["git", "branch", "--show-current"], text=True
    ).strip()
    status = subprocess.check_output(["git", "status", "--porcelain"], text=True)
    if branch != "task42extra_feinn_5nm" or status:
        raise RuntimeError("formal stage requires clean committed task42extra source")
    mode, stage = spec.derived["environment_mode"], spec.derived["stage"]
    if index_path(stage).exists():
        raise RuntimeError("STAGE_ALREADY_PUBLISHED: no duplicate candidate or overwrite")
    if os.environ.get("TASK42EXTRA_ENV_MODE") != mode:
        raise RuntimeError("independent FE/ML environment mismatch")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    directory = spec.expected_output_parent / (spec.identity["run_id"] + "_" + stamp)
    directory.mkdir(parents=True)
    source = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    state = dict(
        source_sha=source,
        branch=branch,
        git_status=status,
        stage=stage,
        environment_mode=mode,
        mpi_size=1,
        math_threads=1,
        cpu_only=True,
        input_sha256=spec.input_sha256,
        design_sha256=spec.derived["design_sha256"],
        physical_model_sha256=spec.physical_model_sha256,
        physical_hash_meaning=spec.derived["identity_hash_meaning"],
        material_table_sha256=spec.materials["material_table_sha256"],
        python_executable=sys.executable,
        environment=dict(os.environ),
        authorization="Task42extra controlled shared native Linux: own tree 16 GiB/zero swap",
        source_is_later_documentation_HEAD=False,
    )
    if stage.startswith("v2_") or stage == "FREE-FE-DUAL-GRAM-DIAG":
        pre = ROOT / "docs/task042extra_feinn_5nm/outcomes/records/scaling_design_v2.json"
        state["v2_pre_registered_design_sha256"] = sha(pre)
        state["v2_review_sha"] = "0b61816c0189a2c05812044ab8e1d1513ef0407d"
    # Never capture secrets: environment whitelist, not the entire process environment.
    state["environment"] = {
        k: v
        for k, v in state["environment"].items()
        if k.startswith(
            ("TASK42EXTRA_", "OMP_", "OPENBLAS_", "MKL_", "PETSC_", "FFCX_")
        )
        or k in ("CUDA_VISIBLE_DEVICES", "PYTHONPATH", "LD_LIBRARY_PATH", "VIRTUAL_ENV")
    }
    write_json(directory / "resolved_config.json", spec.as_jsonable())
    (directory / "input_original.dat").write_bytes(spec.raw_input_bytes)
    for filename, value in [
        ("source_sha.txt", source),
        ("input_sha256.txt", spec.input_sha256),
        ("physical_model_sha256.txt", spec.physical_model_sha256),
    ]:
        (directory / filename).write_text(value + "\n")
    write_json(directory / "run_manifest.json", state)
    with (ROOT / "tmp/task42extra/numerical.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            baseline = admission()
        except RuntimeError as error:
            result = dict(
                classification="RESOURCE_WINDOW_UNAVAILABLE",
                reason=str(error),
                stage=stage,
                elapsed_seconds=0,
                leader_exit_code=None,
                descendants_cleared=True,
            )
            write_json(directory / "run_summary.json", result)
            return result
        ledger = budget()
        if ledger["remaining_seconds"] <= 120 or (
            stage.startswith("v2_") or stage == "FREE-FE-DUAL-GRAM-DIAG"
        ) and ledger["v2_remaining_seconds"] <= 120:
            raise RuntimeError("Task42extra V1/V2 supervised wall budget exhausted")
        write_json(directory / "budget_at_launch.json", ledger)
        os.sched_setaffinity(0, {baseline["cpu"]})
        os.nice(10)
        subprocess.run(["ionice", "-c", "3", "-p", str(os.getpid())], check=True)
        state.update(cpu=baseline["cpu"], resource_baseline_sha256=None)
        write_json(directory / "resource_baseline.json", baseline)
        state["resource_baseline_sha256"] = sha(directory / "resource_baseline.json")
        dependencies = {}
        prereqs = {
            "e1_grad": ["e1_fe"],
            "FEINN-EUC": ["e1_fe", "e1_grad"],
            "FEINN-DUAL": ["e1_fe", "e1_grad"],
            "FREE-FE-DUAL": ["e1_fe", "e1_grad"],
            "e3_reference": ["e1_fe", "FEINN-EUC", "FEINN-DUAL", "FREE-FE-DUAL"],
            "e4_p4": ["e1_fe", "e3_reference"],
            "v2_state_diagnostic": ["e1_fe", "e1_grad", "FEINN-EUC", "FEINN-DUAL", "FREE-FE-DUAL"],
            "v2_scaling_checks": ["e1_fe", "e1_grad", "v2_state_diagnostic"],
            "FREE-FE-DUAL-GRAM-DIAG": ["e1_fe", "e1_grad", "v2_state_diagnostic", "v2_scaling_checks"],
            "v2_compare_only": ["e1_fe", "e3_reference", "v2_state_diagnostic", "FREE-FE-DUAL-GRAM-DIAG"],
        }
        prerequisite_stages = prereqs.get(stage, [])
        for dependency in prerequisite_stages:
            item = load_index(dependency)
            dependencies[dependency] = dict(
                index_sha256=sha(index_path(dependency)),
                source_sha=item["source_sha"],
                files=item["files"],
            )
        if "e1_fe" in dependencies:
            operator = load_index("e1_fe")
            identity = operator["result"]["identity"]
            state.update(
                physical_model_sha256=operator["files"]["native"]["sha256"],
                actual_operator_packet_sha256=operator["files"]["native"]["sha256"],
                mesh_sha256=identity["mesh_coordinates_sha256"],
                cell_tags_sha256=identity["cell_tags_sha256"],
                mode_sha256=identity["mode_manifest_sha256"],
                gram_sha256=operator["files"]["gram"]["sha256"]
                if stage != "FEINN-EUC"
                else None,
                gram_loaded_by_route=stage in ("FEINN-DUAL", "FREE-FE-DUAL", "e1_grad",
                                               "v2_state_diagnostic", "v2_scaling_checks",
                                               "FREE-FE-DUAL-GRAM-DIAG", "v2_compare_only"),
                physical_hash_meaning="actual original full independent FE packet and fixed affine rhs",
            )
            (directory / "physical_model_sha256.txt").write_text(
                state["physical_model_sha256"] + "\n"
            )
        state["frozen_dependencies_before_worker_launch"] = dependencies
        state["qualified_environment_record"] = {
            mode: dict(
                path=str(ROOT / "tmp/task42extra/setup" / f"{mode}_abi.json"),
                sha256=sha(ROOT / "tmp/task42extra/setup" / f"{mode}_abi.json"),
            )
        }
        state["numerical_module_sha256"] = {
            str(path.relative_to(ROOT)): sha(path)
            for path in sorted((ROOT / "src/solvers").glob("feinn_*"))
            if path.is_file()
        }
        write_json(directory / "run_manifest.json", state)
        limit = min(spec.execution["timeout_seconds"], ledger["remaining_seconds"])
        if stage.startswith("v2_") or stage == "FREE-FE-DUAL-GRAM-DIAG":
            limit = min(limit, ledger["v2_remaining_seconds"])
            if stage == "FREE-FE-DUAL-GRAM-DIAG":
                limit = min(limit, ledger["v2_remaining_seconds"] - 900)
            if limit <= 120:
                raise RuntimeError("V2_BUDGET_RESERVE_UNAVAILABLE")
        state["supervised_limit_seconds"] = limit
        write_json(directory / "run_manifest.json", state)
        result = supervise(
            [sys.executable, "-m", "src.runners.feinn_workflow", str(directory)],
            directory / "supervision",
            wall_seconds=limit,
            interval=0.5,
            rss_hard_limit_bytes=16 * 2**30,
            rss_warning_bytes=12 * 2**30,
            hard_stop_immediate=True,
            memory_envelope_provider=envelope,
            health_check=Health(directory, 16 * 2**30, baseline["neighbor_processes"]),
            include_pss=False,
            stop_on_global_swap=False,
            source_state=state,
        )
    result.update(directory=str(directory), stage=stage)
    write_json(directory / "run_summary.json", result)
    return result


def worker(directory):
    import numpy as np

    directory = Path(directory)
    manifest = json.loads((directory / "run_manifest.json").read_text())
    stage = manifest["stage"]
    artifact = ARTIFACTS / directory.name
    artifact.mkdir(parents=True)

    def marker(name, facts):
        with (directory / "stages.jsonl").open("a") as stream:
            stream.write(
                json.dumps(
                    dict(name=name, seconds=perf_counter() - began, facts=facts),
                    default=lambda x: x.tolist() if hasattr(x, "tolist") else str(x),
                )
                + "\n"
            )
        print(name, flush=True)

    began = perf_counter()
    try:
        if (
            subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
            != manifest["source_sha"]
        ):
            raise RuntimeError("source moved during formal stage")
        design = json.loads(DESIGN.read_text())
        if sha(DESIGN) != manifest["design_sha256"]:
            raise RuntimeError("design changed after admission")
        if stage == "e1_smoke":
            from src.solvers.feinn_fem import positive_smoke

            result = positive_smoke()
            if result["status"] != "PASS":
                raise RuntimeError(str(result))
            files = {}
        elif stage == "e1_fe":
            from scipy import sparse
            from src.solvers.feinn_fem import (
                build_model,
                export_native,
                native_gate,
                assemble_gram,
            )
            from src.solvers.feinn_interpolation import (
                build_full_moments,
                complete_interpolation_check,
            )
            from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
                destroy_same_mesh_physical_action,
            )

            if load_index("e1_smoke")["result"]["status"] != "PASS":
                raise RuntimeError("manufactured prerequisite failed")
            model = build_model(design, marker=marker)
            try:
                p15, witness = build_full_moments(
                    model["space"],
                    model["floquet"].mpc,
                    15,
                    design["geometry"]["cells"],
                )
                moments_gate = complete_interpolation_check(
                    p15, model["space"], witness, model["floquet"].mpc
                )
                marker("complete_moments", moments_gate)
                if moments_gate["status"] != "PASS":
                    raise RuntimeError("FULL_INTERPOLATION_FAILED")
                packet, identity = export_native(model, marker)
                action_gate = native_gate(model, packet)
                marker("native_gate", action_gate)
                if action_gate["status"] != "PASS":
                    raise RuntimeError("PORT_ELIMINATION_NOT_QUALIFIED")
                G, gram_record = assemble_gram(model, design)
                marker("gram_assembly", gram_record)
                p30, _ = build_full_moments(
                    model["space"],
                    model["floquet"].mpc,
                    30,
                    design["geometry"]["cells"],
                )
                files = {}
                for name, values in [
                    ("native", packet.a),
                    ("moments_q15", p15),
                    ("moments_q30", p30),
                ]:
                    path = artifact / (name + ".npz")
                    np.savez(path, **values)
                    files[name] = path
                path = artifact / "gram.npz"
                sparse.save_npz(path, G)
                files["gram"] = path
                result = dict(
                    status="FE_INTERFACE_PASS",
                    complete_moments=moments_gate,
                    native=action_gate,
                    identity=identity,
                    gram=gram_record,
                    target_reference_loaded=False,
                )
                manifest.update(
                    physical_model_sha256=sha(files["native"]),
                    actual_operator_packet_sha256=sha(files["native"]),
                    gram_sha256=sha(files["gram"]),
                    moments_sha256=sha(files["moments_q15"]),
                    mode_sha256=identity["mode_manifest_sha256"],
                    physical_hash_meaning="actual original full operator packet with fixed affine rhs",
                )
                write_json(directory / "run_manifest.json", manifest)
                (directory / "physical_model_sha256.txt").write_text(
                    manifest["physical_model_sha256"] + "\n"
                )
            finally:
                destroy_same_mesh_physical_action(model["bundle"])
        elif stage == "e1_grad":
            from src.solvers.feinn_validation import qualify

            result, files = qualify(design, load_index("e1_fe"), artifact, marker)
        elif stage == "v2_state_diagnostic":
            from src.solvers.feinn_scaling import state_diagnostic

            result, files = state_diagnostic(
                design, load_index("e1_fe"), load_index("e1_grad"),
                {r: load_index(r) for r in design["routes"]}, artifact, marker,
            )
        elif stage == "v2_scaling_checks":
            from src.solvers.feinn_scaling import scaling_checks

            result, files = scaling_checks(
                design, load_index("e1_fe"), load_index("e1_grad"),
                load_index("v2_state_diagnostic"),
                artifact, marker,
            )
        elif stage == "FREE-FE-DUAL-GRAM-DIAG":
            from src.solvers.feinn_optimization import run_route

            if load_index("v2_scaling_checks")["result"]["status"] != "SCALING_CHECKS_PASS":
                raise RuntimeError("V2 scaling interface did not qualify")
            result, files = run_route(
                stage, design, load_index("e1_fe"), load_index("e1_grad"),
                artifact, marker, scale_index=load_index("v2_state_diagnostic"),
                route_wall_seconds=manifest["supervised_limit_seconds"],
            )
        elif stage == "v2_compare_only":
            from src.solvers.feinn_reference import compare_frozen_without_solve

            result, files = compare_frozen_without_solve(
                design, load_index("e1_fe"),
                load_index("FREE-FE-DUAL-GRAM-DIAG"), load_index("e3_reference"),
                load_index("v2_state_diagnostic"), artifact, marker,
            )
        elif stage in design["routes"]:
            from src.solvers.feinn_optimization import run_route

            result, files = run_route(
                stage,
                design,
                load_index("e1_fe"),
                load_index("e1_grad"),
                artifact,
                marker,
            )
        elif stage == "e3_reference":
            from src.solvers.feinn_reference import validate_candidates

            frozen = {r: load_index(r) for r in design["routes"]}
            result, files = validate_candidates(
                design, load_index("e1_fe"), frozen, artifact, marker
            )
        elif stage == "e4_p4":
            from src.solvers.feinn_reference import p_check

            result, files = p_check(
                design,
                load_index("e1_fe"),
                load_index("e3_reference"),
                artifact,
                marker,
            )
        else:
            raise RuntimeError("unknown explicit stage")
        result.update(worker_elapsed_seconds=perf_counter() - began)
        manifest = json.loads((directory / "run_manifest.json").read_text())
        manifest["completed_outputs"] = {
            key: dict(path=str(path), sha256=sha(path)) for key, path in files.items()
        }
        write_json(directory / "run_manifest.json", manifest)
        path = artifact / "result.json"
        write_json(path, result)
        files["result"] = path
        record = publish(stage, directory, result, files)
        write_json(directory / "worker_result.json", record)
        print(
            json.dumps(
                dict(
                    stage=stage,
                    status=result["status"],
                    elapsed_seconds=result["worker_elapsed_seconds"],
                )
            ),
            flush=True,
        )
        return 0
    except BaseException as error:
        write_json(
            directory / "worker_failure.json",
            dict(
                stage=stage,
                kind=type(error).__name__,
                reason=str(error),
                elapsed_seconds=perf_counter() - began,
                traceback=traceback.format_exc(),
            ),
        )
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(worker(sys.argv[1]))
