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


def replay_closure_deadline(manifest):
    """Charge worker import/loading to the launch clock; leave 150s for exit.

    The extra 30s covers a closure already in flight at the 120s save boundary.
    This does not authorize another formal replay.
    """
    origin = float(manifest["supervision_budget_origin_monotonic"])
    limit = min(10800.0, float(manifest["supervised_limit_seconds"]))
    if not origin > 0 or limit <= 150:
        raise ValueError("REPLAY_SAVE_RESERVE_UNAVAILABLE")
    return origin + limit - 150


def authority_watchdog_window(manifest, now):
    """Bound native calls as well as Python checkpoints; leave 150s to exit."""
    remaining = replay_closure_deadline(manifest) - float(now)
    if remaining <= 0:
        raise RuntimeError("V7_BUDGET_RESERVE_UNAVAILABLE")
    return remaining


def bind_authority_packet(state, operator):
    """Publish the qualified p4 identity before a potentially interrupted run."""
    identity = operator["result"]["identity"]
    if identity["degree"] != 4:
        raise ValueError("AUTHORITY_PACKET_MUST_BE_P4")
    state.update(
        p3_dependency_native_sha256=state.get("actual_operator_packet_sha256"),
        physical_model_sha256=operator["files"]["native"]["sha256"],
        actual_operator_packet_sha256=operator["files"]["native"]["sha256"],
        mesh_sha256=identity["mesh_coordinates_sha256"],
        cell_tags_sha256=identity["cell_tags_sha256"],
        mode_sha256=identity["mode_manifest_sha256"],
        actual_discretization_degree=4,
        authoritative_packet_stage="v7_p_transfer_checks",
        physical_hash_meaning="actual original full independent FE packet and fixed affine rhs",
    )


def index_path(stage):
    return ARTIFACTS / ("index_" + stage.lower().replace("-", "_") + ".json")


def load_index(stage, *, file_keys=None):
    item = json.loads(index_path(stage).read_text())
    if file_keys is not None:
        item["files"] = {key: item["files"][key] for key in file_keys}
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
            entries.append(
                dict(
                    path=str(path),
                    seconds=max(
                        item.get("elapsed_seconds", 0),
                        item.get("launch_to_summary_seconds_monotonic", 0),
                    ),
                )
            )
    interruption_path = (
        ROOT / "docs/task042extra_feinn_5nm/outcomes/records/fit_interruption_v3.json"
    )
    if interruption_path.exists():
        interrupted = json.loads(interruption_path.read_text())
        original = ROOT / "results/task42extra" / interrupted["run_directory_name"]
        if not (original / "run_summary.json").exists():
            entries.append(
                dict(
                    path=str(interruption_path),
                    seconds=interrupted["conservative_charged_seconds"],
                    classification=interrupted["classification"],
                )
            )
    used = sum(e["seconds"] for e in entries)
    v2_used = sum(
        e["seconds"]
        for e in entries
        if "/task42extra_v2_" in e["path"] or "/checks/v2_" in e["path"]
    )
    v3_used = sum(
        e["seconds"]
        for e in entries
        if "/task42extra_v3_" in e["path"]
        or "/checks/v3_" in e["path"]
        or e["path"].endswith("/fit_interruption_v3.json")
    )
    v4_used = sum(
        e["seconds"]
        for e in entries
        if "/task42extra_v4_" in e["path"] or "/checks/v4_" in e["path"]
    )
    v5_used = sum(
        e["seconds"]
        for e in entries
        if "/task42extra_v5_" in e["path"] or "/checks/v5_" in e["path"]
    )
    s0_used = sum(
        e["seconds"]
        for e in entries
        if "/task42extra_v5_readout_checks_" in e["path"]
        or "/checks/v5_s0_" in e["path"]
    )
    v6_used = sum(
        e["seconds"]
        for e in entries
        if "/task42extra_v6_" in e["path"] or "/checks/v6_" in e["path"]
    )
    t0_used = sum(
        e["seconds"]
        for e in entries
        if "/task42extra_v6_operator_readout_checks_" in e["path"]
        or "/checks/v6_t0_" in e["path"]
    )
    v7_used = sum(
        e["seconds"]
        for e in entries
        if "/task42extra_v7_" in e["path"] or "/checks/v7_" in e["path"]
    )
    u0_used = sum(
        e["seconds"]
        for e in entries
        if "/task42extra_v7_p_transfer_checks_" in e["path"]
        or "/checks/v7_u0_" in e["path"]
    )
    return dict(
        v7_used_seconds=v7_used,
        v7_remaining_seconds=7200 - v7_used - 120,
        v7_u0_remaining_seconds=1200 - u0_used,
        conservative_through_V6_seconds=45161.81665198447,
        v6_used_seconds=v6_used,
        v6_remaining_seconds=3600 - v6_used - 120,
        v6_t0_remaining_seconds=600 - t0_used,
        conservative_through_V5_seconds=44815.22461795143,
        limit_seconds=57600,
        used_seconds=used,
        remaining_seconds=57600
        - max(
            used,
            29227.93927047425 + v3_used,
            33070.52670758043 + v4_used + 120,
            44119.848638203344 + v5_used + 120,
            44815.22461795143 + v6_used + 120,
            45161.81665198447 + v7_used + 120,
        ),
        conservative_V1_V2_V3_V4_base_seconds=44119.848638203344,
        v5_used_seconds=v5_used,
        v5_limit_seconds=7200,
        v5_remaining_seconds=7200 - v5_used - 120,
        v5_s0_remaining_seconds=1200 - s0_used,
        v5_direct_final_allowance_seconds=120,
        conservative_V1_V2_V3_base_seconds=33070.52670758043,
        v4_limit_seconds=14400,
        v4_used_seconds=v4_used,
        v4_direct_final_tail_allowance_seconds=120,
        v4_remaining_seconds=14400 - v4_used - 120,
        conservative_V1_base_seconds=26240.100355625153,
        v2_limit_seconds=14400,
        v2_used_seconds=v2_used,
        v2_remaining_seconds=14400 - v2_used,
        v3_limit_seconds=14400,
        v3_used_seconds=v3_used,
        v3_remaining_seconds=14400 - v3_used,
        conservative_V1_V2_base_seconds=29225.912270474248,
        entries=entries,
    )


def launch(spec):
    launch_origin = perf_counter()
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
        raise RuntimeError(
            "STAGE_ALREADY_PUBLISHED: no duplicate candidate or overwrite"
        )
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
        pre = (
            ROOT / "docs/task042extra_feinn_5nm/outcomes/records/scaling_design_v2.json"
        )
        state["v2_pre_registered_design_sha256"] = sha(pre)
        state["v2_review_sha"] = "0b61816c0189a2c05812044ab8e1d1513ef0407d"
    v3 = stage.startswith("v3_") or stage == "FEINN-REFERENCE-FIT-G"
    v4 = stage.startswith("v4_") or stage == "FEINN-REFERENCE-FIT-G-ADAM500-REPLAY"
    v5 = stage.startswith("v5_") or stage == "FEINN-FROZEN-HIDDEN-READOUT-G"
    v6 = stage.startswith("v6_") or stage == "FEINN-FROZEN-FEATURE-RESIDUAL-READOUT"
    v7 = stage.startswith("v7_")
    v8 = stage.startswith("v8_")
    v11 = stage.startswith("v11_")
    v12 = stage.startswith("v12_")
    v13 = stage.startswith("v13_")
    v18 = stage.startswith("v18_")
    v10 = stage.startswith("v10_")
    v9 = stage.startswith(("v9_", "v10_", "v11_", "v12_", "v13_", "v18_"))
    gn_version = (
        "V18"
        if v18
        else "V13"
        if v13
        else "V12"
        if v12
        else "V11"
        if v11
        else "V10"
        if v10
        else "V9"
    )
    if v12 or v13 or v18:
        from src.runners import feinn_attribution_campaign as gn_campaign
    elif v11:
        from src.runners import feinn_metric_campaign as gn_campaign
    elif v10:
        from src.runners import feinn_cached_gn_campaign as gn_campaign
    elif v9:
        from src.runners import feinn_gn_campaign as gn_campaign
    if v9:
        GN_AUTHORITY = gn_campaign.AUTHORITY
        GN_REVIEW = (
            gn_campaign.V18_REVIEW_SHA
            if v18
            else gn_campaign.CLOSURE_REVIEW_SHA
            if v13
            else gn_campaign.REVIEW_SHA
        )
        SUPERVISED = gn_campaign.SUPERVISED
        from src.solvers.feinn_discretization_audit import POLICY

        namespace = os.environ.get("TASK42EXTRA_DURABLE_NAMESPACE", stage)
        if namespace != stage and namespace not in {
            stage + "_attempt" + str(k) for k in (2, 3, 4)
        }:
            raise RuntimeError("UNAUTHORIZED_DURABLE_ATTEMPT_NAMESPACE")
        proof = ROOT / "tmp/task42extra/durable" / namespace / "terminal_identity.json"
        if not proof.exists():
            raise RuntimeError("DURABLE_TERMINAL_PROOF_REQUIRED")
        state.update(
            run_id=directory.name,
            v9_review_sha=GN_REVIEW,
            v9_campaign_design_sha256=sha(
                gn_campaign.V18_DESIGN_RECORD
                if v18
                else gn_campaign.CLOSURE_DESIGN_RECORD
                if v13
                else gn_campaign.DESIGN_RECORD
                if v12
                else ROOT
                / (
                    "docs/task042extra_feinn_5nm/outcomes/records/campaign_design_"
                    + gn_version.lower()
                    + ".json"
                )
            ),
            supervision_budget_origin_monotonic=launch_origin,
            durable_terminal_identity_sha256=sha(proof),
        )
        if v10:
            state["v10_review_sha"] = state.pop("v9_review_sha")
            state["v10_campaign_design_sha256"] = state.pop("v9_campaign_design_sha256")
            frozen = json.loads(
                (
                    ROOT
                    / "docs/task042extra_feinn_5nm/outcomes/records/campaign_design_v10.json"
                ).read_text()
            )["frozen_states"]
            key = ("phase" if "phase" in stage else "plain") + (
                "_fit_gn" if "fit" in stage else "_gn"
            )
            chosen = (
                {key: frozen[key]}
                if stage
                in (
                    "v10_plain_cached_gn",
                    "v10_phase_cached_gn",
                    "v10_plain_cached_fit_gn",
                    "v10_phase_cached_fit_gn",
                    "v10_phase_resource_freeze",
                )
                else frozen
            )
            for entry in chosen.values():
                for file_key in ("checkpoint", "durable_final", "checkpoint_index"):
                    if sha(entry[file_key]["path"]) != entry[file_key]["sha256"]:
                        raise RuntimeError("V9_FINAL_BYTES_CHANGED_BEFORE_WORKER")
            state["V9_final_states_bound_before_worker"] = chosen
        if v11:
            state["v11_review_sha"] = state.pop("v9_review_sha")
            state["v11_campaign_design_sha256"] = state.pop("v9_campaign_design_sha256")
            frozen = gn_campaign.anchor()
            for key in ("checkpoint", "durable_final", "checkpoint_index"):
                if sha(frozen[key]["path"]) != frozen[key]["sha256"]:
                    raise RuntimeError("PHASE75_BYTES_CHANGED_BEFORE_WORKER")
            state["V10_phase75_bound_before_worker"] = frozen
        if v12 or v13 or v18:
            prefix = "v18" if v18 else "v13" if v13 else "v12"
            state[prefix + "_review_sha"] = state.pop("v9_review_sha")
            state[prefix + "_diagnostic_design_sha256"] = state.pop(
                "v9_campaign_design_sha256"
            )
            state.update(**gn_campaign.DIAGNOSTIC_POLICY)
            state.update(
                data_role="REFERENCE_EXPOSED_DIAGNOSTIC_ONLY",
                no_training=True,
                optimizer_steps=0,
            )
        if stage in GN_AUTHORITY:
            state.update(**POLICY)
        elif not (v12 or v13 or v18):
            supervised = stage in SUPERVISED
            state.update(
                reference_used_for_training=supervised,
                features_reference_exposed=supervised,
                pde_only_solve=not supervised,
                benchmark_previously_seen=True,
                production_initialization_allowed=False,
                pde_only_solver_qualified=False,
                official_candidate_results=False,
            )
    if v8:
        from src.runners.feinn_campaign import AUTHORITY, REVIEW_SHA
        from src.solvers.feinn_discretization_audit import POLICY

        proof = ROOT / "tmp/task42extra/durable" / stage / "terminal_identity.json"
        if not proof.exists():
            raise RuntimeError("DURABLE_TERMINAL_PROOF_REQUIRED")
        state.update(
            run_id=directory.name,
            v8_review_sha=REVIEW_SHA,
            v8_campaign_design_sha256=sha(
                ROOT
                / "docs/task042extra_feinn_5nm/outcomes/records/campaign_design_v8.json"
            ),
            supervision_budget_origin_monotonic=launch_origin,
            durable_terminal_identity_sha256=sha(proof),
            **(POLICY if stage in AUTHORITY else {}),
        )
        if stage not in AUTHORITY:
            supervised = stage in (
                "v8_plain_reference_fit",
                "v8_phase_reference_fit",
                "v8_representation_reconstruct",
                "v8_representation_compare",
            )
            state.update(
                reference_used_for_training=supervised,
                features_reference_exposed=supervised,
                pde_only_solve=not supervised,
                benchmark_previously_seen=True,
                production_initialization_allowed=False,
                pde_only_solver_qualified=False,
                official_candidate_results=False,
            )
    if v7:
        from src.solvers.feinn_discretization_audit import POLICY

        pre = (
            ROOT
            / "docs/task042extra_feinn_5nm/outcomes/records/discretization_design_v7.json"
        )
        proof = ROOT / "tmp/task42extra/durable" / stage / "terminal_identity.json"
        if not proof.exists():
            raise RuntimeError("DURABLE_TERMINAL_PROOF_REQUIRED")
        state.update(
            run_id=directory.name,
            v7_pre_registered_design_sha256=sha(pre),
            v7_review_sha="ecabef960cdf1ac194ef293ff83c65b14e8b7ba3",
            supervision_budget_origin_monotonic=launch_origin,
            durable_terminal_identity_sha256=sha(proof),
            **POLICY,
        )
    if v6:
        from src.solvers.feinn_restricted_residual import POLICY

        pre = (
            ROOT
            / "docs/task042extra_feinn_5nm/outcomes/records/residual_readout_design_v6.json"
        )
        state.update(
            run_id=directory.name,
            v6_pre_registered_design_sha256=sha(pre),
            v6_review_sha="3ab4a251c76208897729473add43f1e91c9d634a",
            supervision_budget_origin_monotonic=launch_origin,
            **POLICY,
        )
        namespace = (
            "v6_frozen_feature_residual"
            if stage == "FEINN-FROZEN-FEATURE-RESIDUAL-READOUT"
            else stage
        )
        proof = ROOT / "tmp/task42extra/durable" / namespace / "terminal_identity.json"
        if not proof.exists():
            raise RuntimeError("DURABLE_TERMINAL_PROOF_REQUIRED")
        state["durable_terminal_identity_sha256"] = sha(proof)
    if v5:
        pre = (
            ROOT / "docs/task042extra_feinn_5nm/outcomes/records/readout_design_v5.json"
        )
        state.update(
            run_id=directory.name,
            v5_pre_registered_design_sha256=sha(pre),
            v5_review_sha="28fabffd41f042c8a4bdda6339810bb1f98a887d",
            reference_used_for_training=True,
            pde_only_solve=False,
            production_initialization_allowed=False,
            pde_only_solver_qualified=False,
            official_candidate_results=False,
            data_role="REFERENCE_EXPOSED_DIAGNOSTIC_ONLY",
            supervision_budget_origin_monotonic=launch_origin,
        )
        namespace = (
            "v5_frozen_hidden_readout"
            if stage == "FEINN-FROZEN-HIDDEN-READOUT-G"
            else stage
        )
        proof = ROOT / "tmp/task42extra/durable" / namespace / "terminal_identity.json"
        if not proof.exists():
            raise RuntimeError("DURABLE_TERMINAL_PROOF_REQUIRED")
        state["durable_terminal_identity_sha256"] = sha(proof)
    if v4:
        pre = (
            ROOT / "docs/task042extra_feinn_5nm/outcomes/records/replay_design_v4.json"
        )
        state.update(
            run_id=directory.name,
            v4_pre_registered_design_sha256=sha(pre),
            v4_review_sha="4dc7c38b60acf2a5ee3d9c6b9770b084a874fb04",
            reference_used_for_training=True,
            pde_only_solve=False,
            production_initialization_allowed=False,
            pde_only_solver_qualified=False,
            official_candidate_results=False,
            data_role="REFERENCE_EXPOSED_DIAGNOSTIC_ONLY",
        )
        if stage == "FEINN-REFERENCE-FIT-G-ADAM500-REPLAY":
            proof = (
                ROOT / "tmp/task42extra/durable/v4_formal_replay/terminal_identity.json"
            )
            if not proof.exists():
                raise RuntimeError("DURABLE_TERMINAL_PROOF_REQUIRED")
            state["durable_terminal_identity_sha256"] = sha(proof)
    if v3:
        pre = (
            ROOT
            / "docs/task042extra_feinn_5nm/outcomes/records/representation_design_v3.json"
        )
        state.update(
            v3_pre_registered_design_sha256=sha(pre),
            v3_review_sha="a668fb20dcf49f105cc4c7dfeeda145ee492ae14",
            reference_used_for_training=stage != "v3_error_geometry",
            pde_only_solve=False,
            production_initialization_allowed=False,
            data_role="REFERENCE_EXPOSED_DIAGNOSTIC_ONLY",
        )
        interruption = (
            ROOT
            / "docs/task042extra_feinn_5nm/outcomes/records/fit_interruption_v3.json"
        )
        if interruption.exists():
            state["fit_interruption_record_sha256"] = sha(interruption)
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
        tree_limit = (
            2 * 2**30
            if stage
            in (
                "v4_boundary_checks",
                "v5_readout_checks",
                "v6_operator_readout_checks",
                "v12_saved_state_freeze",
            )
            else 16 * 2**30
        )
        try:
            if v11 or v12 or v13 or v18:
                from src.runners.feinn_resources import stable_window

                state["pressure_stable_window"] = stable_window(directory, tree_limit)
            baseline = admission(tree_limit)
        except RuntimeError as error:
            result = dict(
                classification="RESOURCE_WINDOW_UNAVAILABLE",
                reason=str(error),
                stage=stage,
                elapsed_seconds=perf_counter() - launch_origin
                if v11 or v12 or v13 or v18
                else 0,
                leader_exit_code=None,
                descendants_cleared=True,
            )
            write_json(directory / "run_summary.json", result)
            return result
        ledger = budget()
        if v8:
            from src.runners.feinn_campaign import campaign_budget

            ledger["V8"] = campaign_budget(ledger["entries"])
            ledger["remaining_seconds"] = ledger["V8"]["new_remaining_seconds"]
        if v9:
            ledger[gn_version] = (
                gn_campaign.v18_budget
                if v18
                else gn_campaign.closure_budget
                if v13
                else gn_campaign.campaign_budget
            )(ledger["entries"])
            ledger["remaining_seconds"] = ledger[gn_version]["new_remaining_seconds"]
            if (v11 or v12) and gn_campaign.STAGES[stage][2] == "E":
                ledger["remaining_seconds"] += 1200
        if (
            ledger["remaining_seconds"] <= 120
            or (stage.startswith("v2_") or stage == "FREE-FE-DUAL-GRAM-DIAG")
            and ledger["v2_remaining_seconds"] <= 120
            or v3
            and ledger["v3_remaining_seconds"] <= 120
            or v4
            and ledger["v4_remaining_seconds"] <= 120
            or v5
            and ledger["v5_remaining_seconds"] <= 150
            or v6
            and ledger["v6_remaining_seconds"] <= 150
            or v7
            and ledger["v7_remaining_seconds"] <= 150
        ):
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
            "v7_p_transfer_checks": ["e1_fe", "e3_reference"],
            "v7_p4_reference": ["e1_fe", "e3_reference", "v7_p_transfer_checks"],
            "v7_p3_p4_compare": [
                "e1_fe",
                "e3_reference",
                "v7_p_transfer_checks",
                "v7_p4_reference",
            ],
            "v6_operator_readout_checks": [
                "e1_fe",
                "e1_grad",
                "v5_readout_checks",
                "FEINN-FROZEN-HIDDEN-READOUT-G",
            ],
            "FEINN-FROZEN-FEATURE-RESIDUAL-READOUT": [
                "e1_fe",
                "e1_grad",
                "v5_readout_checks",
                "FEINN-FROZEN-HIDDEN-READOUT-G",
                "v6_operator_readout_checks",
            ],
            "v6_residual_readout_reconstruct": [
                "e1_fe",
                "e1_grad",
                "FEINN-FROZEN-FEATURE-RESIDUAL-READOUT",
            ],
            "v6_residual_readout_compare_only": [
                "e1_fe",
                "e3_reference",
                "FEINN-FROZEN-FEATURE-RESIDUAL-READOUT",
                "v6_residual_readout_reconstruct",
                "FEINN-FROZEN-HIDDEN-READOUT-G",
            ],
            "e1_grad": ["e1_fe"],
            "FEINN-EUC": ["e1_fe", "e1_grad"],
            "FEINN-DUAL": ["e1_fe", "e1_grad"],
            "FREE-FE-DUAL": ["e1_fe", "e1_grad"],
            "e3_reference": ["e1_fe", "FEINN-EUC", "FEINN-DUAL", "FREE-FE-DUAL"],
            "e4_p4": ["e1_fe", "e3_reference"],
            "v2_state_diagnostic": [
                "e1_fe",
                "e1_grad",
                "FEINN-EUC",
                "FEINN-DUAL",
                "FREE-FE-DUAL",
            ],
            "v2_scaling_checks": ["e1_fe", "e1_grad", "v2_state_diagnostic"],
            "FREE-FE-DUAL-GRAM-DIAG": [
                "e1_fe",
                "e1_grad",
                "v2_state_diagnostic",
                "v2_scaling_checks",
            ],
            "v2_compare_only": [
                "e1_fe",
                "e3_reference",
                "v2_state_diagnostic",
                "FREE-FE-DUAL-GRAM-DIAG",
            ],
            "v3_error_geometry": [
                "e1_fe",
                "e3_reference",
                "FREE-FE-DUAL",
                "FREE-FE-DUAL-GRAM-DIAG",
                "FEINN-DUAL",
            ],
            "v3_fit_checks": ["e1_fe", "e1_grad", "e3_reference"],
            "FEINN-REFERENCE-FIT-G": [
                "e1_fe",
                "e1_grad",
                "e3_reference",
                "v3_fit_checks",
            ],
            "v3_retained_snapshot": [
                "e1_fe",
                "e1_grad",
                "e3_reference",
                "v3_fit_checks",
            ],
            "v3_fit_reconstruct": ["e1_fe", "e1_grad", "v3_retained_snapshot"],
            "v3_fit_compare_only": [
                "e1_fe",
                "e3_reference",
                "v3_retained_snapshot",
                "v3_fit_reconstruct",
            ],
            "v4_boundary_checks": [
                "e1_fe",
                "e1_grad",
                "e3_reference",
                "v3_retained_snapshot",
                "v3_fit_checks",
            ],
            "FEINN-REFERENCE-FIT-G-ADAM500-REPLAY": [
                "e1_fe",
                "e1_grad",
                "e3_reference",
                "v3_retained_snapshot",
                "v4_boundary_checks",
            ],
            "v4_fit_reconstruct": [
                "e1_fe",
                "e1_grad",
                "FEINN-REFERENCE-FIT-G-ADAM500-REPLAY",
            ],
            "v4_fit_compare_only": [
                "e1_fe",
                "e3_reference",
                "FEINN-REFERENCE-FIT-G-ADAM500-REPLAY",
                "v4_fit_reconstruct",
            ],
            "v5_readout_checks": [
                "e1_fe",
                "e1_grad",
                "e3_reference",
                "FEINN-REFERENCE-FIT-G-ADAM500-REPLAY",
            ],
            "FEINN-FROZEN-HIDDEN-READOUT-G": [
                "e1_fe",
                "e1_grad",
                "e3_reference",
                "FEINN-REFERENCE-FIT-G-ADAM500-REPLAY",
                "v5_readout_checks",
            ],
            "v5_readout_reconstruct": [
                "e1_fe",
                "e1_grad",
                "FEINN-FROZEN-HIDDEN-READOUT-G",
            ],
            "v5_readout_compare_only": [
                "e1_fe",
                "e3_reference",
                "FEINN-FROZEN-HIDDEN-READOUT-G",
                "v5_readout_reconstruct",
            ],
        }
        prerequisite_stages = prereqs.get(stage, [])
        if v8:
            from src.runners.feinn_campaign import DEPENDENCIES

            prerequisite_stages = DEPENDENCIES[stage]
        if v9:
            prerequisite_stages = gn_campaign.DEPENDENCIES[stage]
            if v11 and gn_campaign.STAGES[stage][2] == "C":
                prerequisite_stages = prerequisite_stages + [
                    gn_campaign.qualified_checks_stage()
                ]
            if v11 and stage in ("v11_metric_reconstruct", "v11_metric_compare"):
                prerequisite_stages = prerequisite_stages + list(
                    gn_campaign.selected_routes(load_index)
                )
            if v10 and stage in (
                "v10_gn_reconstruct",
                "v10_gn_compare",
                "v10_fit_reconstruct",
                "v10_fit_compare",
            ):
                actual = gn_campaign.selected_routes(
                    load_index, supervised="fit" in stage
                )
                prerequisite_stages = prerequisite_stages + list(actual)
        dependency_loader = (
            (lambda name: gn_campaign.v18_index(name, stage))
            if v18
            else gn_campaign.closure_index
            if v13
            else gn_campaign.selected_index
            if v12
            else load_index
        )
        for dependency in prerequisite_stages:
            item = dependency_loader(dependency)
            dependencies[dependency] = dict(
                index_sha256=sha(index_path(dependency)),
                source_sha=item["source_sha"],
                files=item["files"],
            )
        if "e1_fe" in dependencies:
            operator = dependency_loader("e1_fe")
            identity = operator["result"]["identity"]
            state.update(
                physical_model_sha256=operator["files"]["native"]["sha256"],
                actual_operator_packet_sha256=operator["files"]["native"]["sha256"],
                mesh_sha256=identity["mesh_coordinates_sha256"],
                cell_tags_sha256=identity["cell_tags_sha256"],
                mode_sha256=identity["mode_manifest_sha256"],
                gram_sha256=operator["files"]["gram"]["sha256"]
                if stage != "FEINN-EUC"
                and "gram" in operator["files"]
                and not v13
                and not v7
                and not (v8 and stage in AUTHORITY)
                and not (v9 and stage in GN_AUTHORITY)
                else None,
                gram_loaded_by_route=stage
                in (
                    "FEINN-DUAL",
                    "FREE-FE-DUAL",
                    "e1_grad",
                    "v2_state_diagnostic",
                    "v2_scaling_checks",
                    "FREE-FE-DUAL-GRAM-DIAG",
                    "v2_compare_only",
                    "v3_error_geometry",
                    "v3_fit_checks",
                    "FEINN-REFERENCE-FIT-G",
                    "v3_fit_compare_only",
                    "v4_boundary_checks",
                    "FEINN-REFERENCE-FIT-G-ADAM500-REPLAY",
                    "v4_fit_compare_only",
                    "v5_readout_checks",
                    "FEINN-FROZEN-HIDDEN-READOUT-G",
                    "v5_readout_compare_only",
                    "v6_operator_readout_checks",
                    "FEINN-FROZEN-FEATURE-RESIDUAL-READOUT",
                    "v6_residual_readout_compare_only",
                ),
                physical_hash_meaning="actual original full independent FE packet and fixed affine rhs",
            )
            (directory / "physical_model_sha256.txt").write_text(
                state["physical_model_sha256"] + "\n"
            )
        if v7 and "v7_p_transfer_checks" in dependencies:
            bind_authority_packet(state, load_index("v7_p_transfer_checks"))
            (directory / "physical_model_sha256.txt").write_text(
                state["physical_model_sha256"] + "\n"
            )
        if v13:
            bind_authority_packet(state, dependency_loader("v7_p_transfer_checks"))
            state.update(
                source_p3_operator_packet_sha256=dependencies["e1_fe"]["files"][
                    "native"
                ]["sha256"],
                saved_C2_vector_sha256=dependencies["v12_test_space_witness"]["files"][
                    "vectors"
                ]["sha256"],
                new_operator_assembly=False,
                new_factor=False,
                new_reference_solve=False,
                no_network_forward=True,
            )
            (directory / "physical_model_sha256.txt").write_text(
                state["physical_model_sha256"] + "\n"
            )
        if v8 and stage in AUTHORITY:
            bind_authority_packet(state, load_index("v7_p_transfer_checks"))
            state.update(
                physics_identity=dict(
                    design_sha256=state["design_sha256"],
                    material_sha256=state["material_table_sha256"],
                    mesh_sha256=state["mesh_sha256"],
                    mode_sha256=state["mode_sha256"],
                ),
                discretization_identity=dict(
                    degree=4,
                    volume_quadrature_degree=15,
                    DtN_quadrature_degree=15,
                    independent_complex_FE=75264,
                ),
                operator_packet_sha256=state["actual_operator_packet_sha256"],
            )
            (directory / "physical_model_sha256.txt").write_text(
                state["physical_model_sha256"] + "\n"
            )
        if v8 and stage not in AUTHORITY:
            state["gram_loaded_by_route"] = stage in (
                "v8_phase_checks",
                "v8_plain_dual",
                "v8_phase_dual",
                "v8_pde_compare",
                "v8_plain_reference_fit",
                "v8_phase_reference_fit",
                "v8_representation_compare",
            )
            state.update(
                physics_identity=dict(
                    design_sha256=state["design_sha256"],
                    material_sha256=state["material_table_sha256"],
                    mesh_sha256=state["mesh_sha256"],
                    mode_sha256=state["mode_sha256"],
                ),
                discretization_identity=dict(
                    degree=3,
                    volume_quadrature_degree=15,
                    DtN_quadrature_degree=15,
                    independent_complex_FE=31968,
                ),
                operator_packet_sha256=state["actual_operator_packet_sha256"],
            )
            if "v8_phase_checks" in dependencies:
                qualification = load_index("v8_phase_checks")
                state.update(
                    network_quadrature_degree=qualification["result"][
                        "network_quadrature_degree"
                    ],
                    network_moments_sha256=qualification["files"]["moments"]["sha256"],
                    initial_parameters_sha256=qualification["result"][
                        "initial_parameters_sha256"
                    ],
                )
        state["frozen_dependencies_before_worker_launch"] = dependencies
        if v9:
            state.update(
                discretization_identity=dict(
                    degree=5 if stage in GN_AUTHORITY else 3,
                    volume_quadrature_degree=15,
                    DtN_quadrature_degree=15,
                ),
                gram_loaded_by_route=stage not in GN_AUTHORITY
                and "reconstruct" not in stage,
                network_quadrature_degree=15,
            )
            if v12 or v13 or v18:
                state["gram_loaded_by_route"] = stage in (
                    "v12_saved_field_attribution",
                    "v12_local_parameter_diagnostic",
                    "v18_native_network_witness",
                )
            if v13:
                state["discretization_identity"] = dict(
                    trial_degree=3,
                    test_degree=4,
                    volume_quadrature_degree=15,
                    DtN_quadrature_degree=15,
                    source_complex_FE=31968,
                    test_complex_FE=75264,
                    channels=40,
                )
            if stage in GN_AUTHORITY:
                state.update(
                    gram_sha256=None,
                    actual_discretization_degree=5,
                    physical_hash_meaning="frozen physics plus explicitly distinct p5 operator; initial capacity checks before export",
                )
                state.update(
                    p3_dependency_native_sha256=state["actual_operator_packet_sha256"],
                    actual_operator_packet_sha256=None,
                    physical_model_sha256=state["design_sha256"],
                )
                if "v9_p5_checks" in dependencies:
                    p5 = load_index("v9_p5_checks")
                    state.update(
                        actual_operator_packet_sha256=p5["files"]["native"]["sha256"],
                        physical_model_sha256=p5["files"]["native"]["sha256"],
                        authoritative_packet_stage="v9_p5_checks",
                        physical_hash_meaning="actual p5 full independent FE packet and fixed affine rhs",
                    )
            elif not (v12 or v13 or v18):
                q = load_index("v8_phase_checks")
                state.update(
                    network_moments_sha256=q["files"]["moments"]["sha256"],
                    initial_parameters_sha256=q["result"]["initial_parameters_sha256"],
                )
                if stage in (
                    "v9_plain_gn",
                    "v9_phase_gn",
                    "v9_plain_fit_gn",
                    "v9_phase_fit_gn",
                    "v9_gn_checks",
                ):
                    prefixes = json.loads(
                        (
                            ROOT
                            / "docs/task042extra_feinn_5nm/outcomes/records/prefix_identity_v9.json"
                        ).read_text()
                    )["checkpoints"]
                    keys = (
                        ["plain_dual", "phase_dual"]
                        if stage == "v9_gn_checks"
                        else [
                            ("phase" if stage.startswith("v9_phase") else "plain")
                            + ("_reference_fit" if "fit_gn" in stage else "_dual")
                        ]
                    )
                    state["Adam500_prefixes_bound_before_worker"] = {}
                    for key in keys:
                        prefix = prefixes[key]
                        if sha(prefix["path"]) != prefix["sha256"]:
                            raise RuntimeError("PREFIX_BYTES_CHANGED_BEFORE_WORKER")
                        state["Adam500_prefixes_bound_before_worker"][key] = prefix
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
        if v8:
            from src.runners.feinn_campaign import STAGES as V8_STAGES

            group = V8_STAGES[stage][2]
            limit = min(limit, ledger["V8"]["groups_remaining_seconds"][group])
            if limit <= 150 or launch_origin + limit - 150 <= perf_counter():
                raise RuntimeError("V8_BUDGET_RESERVE_UNAVAILABLE")
        if v9:
            group = gn_campaign.STAGES[stage][2]
            limit = min(limit, ledger[gn_version]["groups_remaining_seconds"][group])
            if v11 and group == "C":
                prior = [
                    r
                    for r in ledger["entries"]
                    if Path(r["path"]).parent.name.startswith(
                        "task42extra_" + stage + "_"
                    )
                ]
                prior_seconds = sum(r["seconds"] for r in prior)
                limit = min(limit, 5400 - prior_seconds)
                state["route_inherited_failed_attempt_seconds"] = prior_seconds
                if prior:
                    from src.runners.feinn_gn_recovery import recovery_boundary

                    state["V11_fault_recovery"] = recovery_boundary(ROOT, stage, prior)
                    if state["V11_fault_recovery"] is None:
                        raise RuntimeError(
                            "V11_COMPLETE_RECOVERY_BOUNDARY_NOT_RETAINED"
                        )
            if v10 and stage == "v10_phase_resource_freeze":
                from src.runners.feinn_gn_recovery import recovery_boundary

                prior = [
                    row
                    for row in ledger["entries"]
                    if Path(row["path"]).parent.name.startswith(
                        "task42extra_v10_phase_cached_gn_"
                    )
                ]
                state["resource_boundary"] = recovery_boundary(
                    ROOT, "v10_phase_cached_gn", prior
                )
                if state["resource_boundary"] is None:
                    raise RuntimeError("OWN_PHASE_COMPLETE_STATE_NOT_RETAINED")
                state["phase_training_attempt_seconds"] = (
                    gn_campaign.route_spent_seconds(
                        "v10_phase_cached_gn", ledger["entries"]
                    )
                )
            if v10 and group in ("C", "D"):
                inherited_attempt_seconds = gn_campaign.route_spent_seconds(
                    stage, ledger["entries"]
                )
                route_limit = (
                    gn_campaign.C_EQUAL_ROUTE_SECONDS if group == "C" else 3600
                )
                limit = min(limit, route_limit - inherited_attempt_seconds)
                state["preregistered_route_limit_seconds"] = route_limit
                if group == "C":
                    state["C_preregistered_equal_route_limit_seconds"] = route_limit
                state["route_inherited_failed_attempt_seconds"] = (
                    inherited_attempt_seconds
                )
                if inherited_attempt_seconds:
                    prior = [
                        row
                        for row in ledger["entries"]
                        if Path(row["path"]).parent.name.startswith(
                            "task42extra_" + stage + "_"
                        )
                    ]
                    from src.runners.feinn_gn_recovery import recovery_boundary

                    recovery = recovery_boundary(ROOT, stage, prior)
                    if recovery is not None:
                        state["V10_fault_recovery"] = recovery
                        state["retry_boundary"] = "LATEST_OWN_V10_FULL_COMMITTED_GN"
                    else:
                        for row in prior:
                            previous_artifact = (
                                ROOT
                                / "benchmarks/artifacts/task42extra"
                                / Path(row["path"]).parent.name
                            )
                            history = previous_artifact / "history.jsonl"
                            if history.exists() and history.stat().st_size:
                                raise RuntimeError(
                                    "V10_FULL_STATE_RECOVERY_REQUIRED_NO_V9_REPLAY"
                                )
                        state["retry_boundary"] = "SAME_V9_FINAL_BEFORE_ANY_NEW_GN_WORK"
            if group != "E" and not (v12 or v13 or v18):
                limit = min(limit, ledger["remaining_seconds"] - 1200)
            if limit <= 150 or launch_origin + limit - 150 <= perf_counter():
                raise RuntimeError("V9_BUDGET_RESERVE_UNAVAILABLE")
        if stage.startswith("v2_") or stage == "FREE-FE-DUAL-GRAM-DIAG":
            limit = min(limit, ledger["v2_remaining_seconds"])
            if stage == "FREE-FE-DUAL-GRAM-DIAG":
                limit = min(limit, ledger["v2_remaining_seconds"] - 900)
            if limit <= 120:
                raise RuntimeError("V2_BUDGET_RESERVE_UNAVAILABLE")
        if v3:
            limit = min(limit, ledger["v3_remaining_seconds"])
            if stage == "FEINN-REFERENCE-FIT-G":
                limit = min(limit, ledger["v3_remaining_seconds"] - 900)
            if limit <= 120:
                raise RuntimeError("V3_BUDGET_RESERVE_UNAVAILABLE")
        if v4:
            limit = min(limit, ledger["v4_remaining_seconds"])
            if stage == "FEINN-REFERENCE-FIT-G-ADAM500-REPLAY":
                limit = min(limit, ledger["v4_remaining_seconds"] - 900)
            if stage == "v4_boundary_checks":
                limit = min(limit, 1800 - ledger["v4_used_seconds"])
            if limit <= 120:
                raise RuntimeError("V4_BUDGET_RESERVE_UNAVAILABLE")
        if v5:
            limit = min(limit, ledger["v5_remaining_seconds"])
            if stage == "FEINN-FROZEN-HIDDEN-READOUT-G":
                limit = min(limit, ledger["v5_remaining_seconds"] - 900)
            if stage == "v5_readout_checks":
                limit = min(limit, ledger["v5_s0_remaining_seconds"])
            if limit <= 150 or launch_origin + limit - 150 <= perf_counter():
                raise RuntimeError("V5_BUDGET_RESERVE_UNAVAILABLE")
        if v6:
            limit = min(limit, ledger["v6_remaining_seconds"])
            if stage == "FEINN-FROZEN-FEATURE-RESIDUAL-READOUT":
                limit = min(limit, ledger["v6_remaining_seconds"] - 900)
            if stage == "v6_operator_readout_checks":
                limit = min(limit, ledger["v6_t0_remaining_seconds"])
            if limit <= 150 or launch_origin + limit - 150 <= perf_counter():
                raise RuntimeError("V6_BUDGET_RESERVE_UNAVAILABLE")
        if v7:
            limit = min(limit, ledger["v7_remaining_seconds"])
            if stage == "v7_p_transfer_checks":
                limit = min(limit, ledger["v7_u0_remaining_seconds"])
            if stage == "v7_p4_reference":
                limit = min(limit, ledger["v7_remaining_seconds"] - 1200)
            if limit <= 150 or launch_origin + limit - 150 <= perf_counter():
                raise RuntimeError("V7_BUDGET_RESERVE_UNAVAILABLE")
        state["supervised_limit_seconds"] = limit
        if v4 and not v5:
            state["supervision_budget_origin_monotonic"] = perf_counter()
        write_json(directory / "run_manifest.json", state)
        command = [sys.executable, "-m", "src.runners.feinn_workflow", str(directory)]
        if v4 or v5 or v6 or v7 or v8 or v9:
            from src.runners.guarded_exec import ticks

            command = [
                sys.executable,
                "-m",
                "src.runners.guarded_exec",
                str(os.getpid()),
                str(ticks(os.getpid())),
                *command,
            ]
        watchdog_seconds = (
            authority_watchdog_window(state, perf_counter())
            if v7 or v8 or v9
            else limit - (perf_counter() - launch_origin)
            if v5 or v6
            else limit
        )
        if v7 or v8 or v9:
            state["watchdog_terminal_cutoff_reserve_seconds"] = 150
            write_json(directory / "run_manifest.json", state)
        result = supervise(
            command,
            directory / "supervision",
            wall_seconds=watchdog_seconds,
            interval=0.5,
            rss_hard_limit_bytes=tree_limit,
            rss_warning_bytes=int(1.75 * 2**30)
            if tree_limit == 2 * 2**30
            else 12 * 2**30,
            hard_stop_immediate=True,
            memory_envelope_provider=lambda: envelope(tree_limit),
            health_check=Health(directory, tree_limit, baseline["neighbor_processes"]),
            include_pss=False,
            stop_on_global_swap=False,
            source_state=state,
        )
    result.update(directory=str(directory), stage=stage)
    if v5 or v6 or v7 or v8 or v9:
        result.update(
            launch_to_summary_seconds_monotonic=perf_counter() - launch_origin,
            launch_exit_remaining_seconds=limit - (perf_counter() - launch_origin),
        )
    write_json(directory / "run_summary.json", result)
    return result


def worker(directory):
    import numpy as np

    directory = Path(directory)
    manifest = json.loads((directory / "run_manifest.json").read_text())
    stage = manifest["stage"]
    if stage.startswith(
        (
            "v4_",
            "v5_",
            "v6_",
            "v7_",
            "v8_",
            "v9_",
            "v10_",
            "v11_",
            "v12_",
            "v13_",
            "v18_",
        )
    ) or stage in (
        "FEINN-REFERENCE-FIT-G-ADAM500-REPLAY",
        "FEINN-FROZEN-HIDDEN-READOUT-G",
        "FEINN-FROZEN-FEATURE-RESIDUAL-READOUT",
    ):
        from src.runners.guarded_exec import ticks

        manifest["worker_lifecycle"] = dict(
            pid=os.getpid(),
            ppid=os.getppid(),
            start_ticks=ticks(os.getpid()),
            session=os.getsid(0),
            process_group=os.getpgrp(),
            stdout=os.readlink(f"/proc/{os.getpid()}/fd/1"),
            cgroup=Path("/proc/self/cgroup").read_text(),
            parent_death_guard=os.environ.get("TASK42EXTRA_PARENT_DEATH_GUARD"),
        )
        write_json(directory / "run_manifest.json", manifest)
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
        if stage.startswith(("v9_", "v10_", "v11_", "v12_", "v13_", "v18_")):
            if stage.startswith(("v12_", "v13_", "v18_")):
                from src.runners.feinn_attribution_campaign import dispatch
            elif stage.startswith("v11_"):
                from src.runners.feinn_metric_campaign import dispatch
            elif stage.startswith("v10_"):
                from src.runners.feinn_cached_gn_campaign import dispatch
            else:
                from src.runners.feinn_gn_campaign import dispatch

            result, files = dispatch(
                stage, design, artifact, marker, manifest, load_index
            )
            if "native" in files and "identity" in result:
                manifest.update(
                    actual_operator_packet_sha256=sha(files["native"]),
                    physical_model_sha256=sha(files["native"]),
                    physical_hash_meaning="actual p5 full independent FE packet and fixed affine rhs",
                    actual_discretization_degree=result["identity"]["degree"],
                )
                write_json(directory / "run_manifest.json", manifest)
        elif stage.startswith("v8_"):
            from src.runners.feinn_campaign import dispatch

            result, files = dispatch(
                stage, design, artifact, marker, manifest, load_index
            )
        elif stage.startswith("v7_"):
            from src.solvers.feinn_discretization_audit import (
                checks,
                reference,
                compare,
            )

            args = (design, load_index("e1_fe"), load_index("e3_reference"))
            if stage == "v7_p_transfer_checks":
                result, files = checks(*args, artifact, marker, manifest)
            elif stage == "v7_p4_reference":
                result, files = reference(
                    *args,
                    load_index("v7_p_transfer_checks"),
                    artifact,
                    marker,
                    manifest,
                )
            else:
                result, files = compare(
                    *args,
                    load_index("v7_p_transfer_checks"),
                    load_index("v7_p4_reference"),
                    artifact,
                    marker,
                    manifest,
                )
            packet_entry = files.get("native")
            native_sha = (
                sha(packet_entry)
                if packet_entry is not None
                else load_index("v7_p_transfer_checks")["files"]["native"]["sha256"]
            )
            manifest.update(
                actual_operator_packet_sha256=native_sha,
                physical_model_sha256=native_sha,
                physical_hash_meaning="actual p4 full independent FE packet; separate explicit physics_equivalence_fields prove same physical model",
                gram_sha256=None,
                gram_loaded_by_route=False,
                mode_sha256=result.get("identity", {}).get(
                    "mode_manifest_sha256", manifest.get("mode_sha256")
                ),
            )
            write_json(directory / "run_manifest.json", manifest)
            (directory / "physical_model_sha256.txt").write_text(native_sha + "\n")
        elif stage == "e1_smoke":
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
                design,
                load_index("e1_fe"),
                load_index("e1_grad"),
                {r: load_index(r) for r in design["routes"]},
                artifact,
                marker,
            )
        elif stage == "v2_scaling_checks":
            from src.solvers.feinn_scaling import scaling_checks

            result, files = scaling_checks(
                design,
                load_index("e1_fe"),
                load_index("e1_grad"),
                load_index("v2_state_diagnostic"),
                artifact,
                marker,
            )
        elif stage == "FREE-FE-DUAL-GRAM-DIAG":
            from src.solvers.feinn_optimization import run_route

            if (
                load_index("v2_scaling_checks")["result"]["status"]
                != "SCALING_CHECKS_PASS"
            ):
                raise RuntimeError("V2 scaling interface did not qualify")
            result, files = run_route(
                stage,
                design,
                load_index("e1_fe"),
                load_index("e1_grad"),
                artifact,
                marker,
                scale_index=load_index("v2_state_diagnostic"),
                route_wall_seconds=manifest["supervised_limit_seconds"],
            )
        elif stage == "v2_compare_only":
            from src.solvers.feinn_reference import compare_frozen_without_solve

            result, files = compare_frozen_without_solve(
                design,
                load_index("e1_fe"),
                load_index("FREE-FE-DUAL-GRAM-DIAG"),
                load_index("e3_reference"),
                load_index("v2_state_diagnostic"),
                artifact,
                marker,
            )
        elif stage == "v3_error_geometry":
            from src.solvers.feinn_error_geometry import run_geometry

            result, files = run_geometry(
                design,
                load_index("e1_fe"),
                load_index("e3_reference"),
                {
                    name: load_index(name)
                    for name in ("FREE-FE-DUAL", "FREE-FE-DUAL-GRAM-DIAG", "FEINN-DUAL")
                },
                artifact,
                marker,
            )
        elif stage == "v3_fit_checks":
            from src.solvers.feinn_reference_fit import fit_checks

            result, files = fit_checks(
                design,
                load_index("e1_fe"),
                load_index("e1_grad"),
                load_index("e3_reference"),
                artifact,
                marker,
            )
        elif stage == "FEINN-REFERENCE-FIT-G":
            from src.solvers.feinn_reference_fit import run_fit

            result, files = run_fit(
                design,
                load_index("e1_fe"),
                load_index("e1_grad"),
                load_index("e3_reference"),
                load_index("v3_fit_checks"),
                artifact,
                marker,
                manifest["supervised_limit_seconds"],
            )
        elif stage == "v3_retained_snapshot":
            from src.solvers.feinn_reference_fit import retained_interrupted_snapshot

            result, files = retained_interrupted_snapshot(
                design,
                load_index("e1_fe"),
                load_index("e1_grad"),
                load_index("e3_reference"),
                artifact,
                marker,
            )
        elif stage == "v3_fit_reconstruct":
            from src.solvers.feinn_reference_fit import reconstruct

            result, files = reconstruct(
                design,
                load_index("e1_fe"),
                load_index("e1_grad"),
                load_index("v3_retained_snapshot"),
                artifact,
                marker,
            )
        elif stage == "v3_fit_compare_only":
            from src.solvers.feinn_reference import compare_reference_fit_without_solve

            result, files = compare_reference_fit_without_solve(
                design,
                load_index("e1_fe"),
                load_index("e3_reference"),
                load_index("v3_retained_snapshot"),
                load_index("v3_fit_reconstruct"),
                artifact,
                marker,
            )
        elif stage == "v4_boundary_checks":
            from src.solvers.feinn_boundary_replay import boundary_checks

            result, files = boundary_checks(
                design,
                load_index("e1_fe"),
                load_index("e1_grad"),
                load_index("e3_reference"),
                load_index("v3_retained_snapshot"),
                artifact,
                marker,
            )
        elif stage == "FEINN-REFERENCE-FIT-G-ADAM500-REPLAY":
            from src.solvers.feinn_boundary_replay import run_replay

            result, files = run_replay(
                design,
                load_index("e1_fe"),
                load_index("e1_grad"),
                load_index("e3_reference"),
                load_index("v3_retained_snapshot"),
                load_index("v4_boundary_checks"),
                artifact,
                marker,
                manifest["supervised_limit_seconds"],
                manifest,
            )
        elif stage == "v4_fit_reconstruct":
            from src.solvers.feinn_reference_fit import reconstruct

            result, files = reconstruct(
                design,
                load_index("e1_fe"),
                load_index("e1_grad"),
                load_index("FEINN-REFERENCE-FIT-G-ADAM500-REPLAY"),
                artifact,
                marker,
            )
        elif stage == "v4_fit_compare_only":
            from src.solvers.feinn_reference import compare_reference_fit_without_solve

            result, files = compare_reference_fit_without_solve(
                design,
                load_index("e1_fe"),
                load_index("e3_reference"),
                load_index("FEINN-REFERENCE-FIT-G-ADAM500-REPLAY"),
                load_index("v4_fit_reconstruct"),
                artifact,
                marker,
                route="FEINN-REFERENCE-FIT-G-ADAM500-REPLAY",
            )
        elif stage == "v5_readout_checks":
            from src.solvers.feinn_readout import checks

            result, files = checks(
                design,
                load_index("e1_fe"),
                load_index("e1_grad"),
                load_index("e3_reference"),
                load_index("FEINN-REFERENCE-FIT-G-ADAM500-REPLAY"),
                artifact,
                marker,
                manifest,
            )
        elif stage == "FEINN-FROZEN-HIDDEN-READOUT-G":
            from src.solvers.feinn_readout import run

            result, files = run(
                design,
                load_index("e1_fe"),
                load_index("e1_grad"),
                load_index("e3_reference"),
                load_index("FEINN-REFERENCE-FIT-G-ADAM500-REPLAY"),
                load_index("v5_readout_checks"),
                artifact,
                marker,
                manifest,
            )
        elif stage == "v5_readout_reconstruct":
            from src.solvers.feinn_reference_fit import reconstruct

            candidate = load_index("FEINN-FROZEN-HIDDEN-READOUT-G")
            if candidate["result"]["status"] != "FROZEN_HIDDEN_READOUT_COMPLETE":
                raise RuntimeError("READOUT_STABILITY_NOT_QUALIFIED")
            result, files = reconstruct(
                design,
                load_index("e1_fe"),
                load_index("e1_grad"),
                candidate,
                artifact,
                marker,
            )
        elif stage == "v5_readout_compare_only":
            from src.solvers.feinn_reference import compare_reference_fit_without_solve

            candidate = load_index("FEINN-FROZEN-HIDDEN-READOUT-G")
            if candidate["result"]["status"] != "FROZEN_HIDDEN_READOUT_COMPLETE":
                raise RuntimeError("READOUT_STABILITY_NOT_QUALIFIED")
            result, files = compare_reference_fit_without_solve(
                design,
                load_index("e1_fe"),
                load_index("e3_reference"),
                candidate,
                load_index("v5_readout_reconstruct"),
                artifact,
                marker,
                route="FEINN-FROZEN-HIDDEN-READOUT-G",
            )
        elif stage in (
            "v6_operator_readout_checks",
            "FEINN-FROZEN-FEATURE-RESIDUAL-READOUT",
        ):
            from src.solvers.feinn_residual_readout import checks, run

            args = (
                design,
                load_index("e1_fe"),
                load_index("e1_grad"),
                load_index("v5_readout_checks"),
                load_index("FEINN-FROZEN-HIDDEN-READOUT-G"),
            )
            if stage == "v6_operator_readout_checks":
                result, files = checks(*args, artifact, marker, manifest)
            else:
                result, files = run(
                    *args,
                    load_index("v6_operator_readout_checks"),
                    artifact,
                    marker,
                    manifest,
                )
        elif stage == "v6_residual_readout_reconstruct":
            from src.solvers.feinn_reference_fit import reconstruct

            result, files = reconstruct(
                design,
                load_index("e1_fe"),
                load_index("e1_grad"),
                load_index("FEINN-FROZEN-FEATURE-RESIDUAL-READOUT"),
                artifact,
                marker,
            )
        elif stage == "v6_residual_readout_compare_only":
            from src.solvers.feinn_reference import (
                compare_residual_readout_without_solve,
            )

            result, files = compare_residual_readout_without_solve(
                design,
                load_index("e1_fe"),
                load_index("e3_reference"),
                load_index("FEINN-FROZEN-FEATURE-RESIDUAL-READOUT"),
                load_index("v6_residual_readout_reconstruct"),
                load_index("FEINN-FROZEN-HIDDEN-READOUT-G"),
                artifact,
                marker,
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
