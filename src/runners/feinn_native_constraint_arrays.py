"""Separate construction, scoring, and checker processes for saved PDE8 data."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
from time import monotonic

import numpy as np

from src.runners.feinn_common_descent_arrays import (
    array_sha,
    extract,
    inputs,
    read_checked,
    sha,
)
from src.solvers.feinn_common_descent import atomic_json, provenance_columns, require

ROOT = Path(__file__).resolve().parents[2]
POLICY = dict(
    reference_used_for_training=False,
    reference_used_for_diagnostic=True,
    features_reference_exposed=True,
    pde_only_solve=False,
    benchmark_previously_seen=True,
    production_initialization_allowed=False,
    pde_only_solver_qualified=False,
    official_candidate_results=False,
    diagnostic_only=True,
    data_role="REFERENCE_EXPOSED_DIAGNOSTIC",
)


def source():
    require(
        os.environ.get("TASK42EXTRA_ENV_MODE") == "pure", "PURE_ACTIVATION_REQUIRED"
    )
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    branch = subprocess.check_output(
        ["git", "branch", "--show-current"], cwd=ROOT, text=True
    ).strip()
    clean = subprocess.check_output(
        ["git", "status", "--porcelain=v1"], cwd=ROOT, text=True
    )
    require(
        branch == "task42extra_feinn_5nm" and not clean, "CLEAN_EXACT_SOURCE_REQUIRED"
    )
    return head


def design_input(path):
    path = Path(path)
    campaign = json.loads(path.read_text())
    design = campaign["A"]
    require(
        list(design["states"]) == ["M3600", "Mfinal"]
        and design["rconds"] == [1e-10, 1e-12],
        "FIXED_CONFIGURATION_INVENTORY",
    )
    require(
        design["native_denominator"] == 0.29104200262261154, "FIXED_NATIVE_DENOMINATOR"
    )
    clock = json.loads((ROOT / campaign["batch_clock"]).read_text())
    require(monotonic() + 600 < clock["hard_deadline_monotonic"], "BATCH_SAVE_RESERVE")
    return campaign, design


def build(design_path, directory):
    from src.solvers.feinn_native_constraint import native_candidate

    started = monotonic()
    head = source()
    campaign, design = design_input(design_path)
    checked, _ = inputs(design, evaluation=False)
    directory = Path(directory)
    require(not directory.exists(), "IMMUTABLE_RUN_DIRECTORY")
    directory.mkdir(parents=True)
    candidates, events, unknown = {}, [], []
    with np.load(checked["vectors"], allow_pickle=False) as saved:
        for state, identity in design["states"].items():
            columns = provenance_columns(identity["directions"], 16, "PDE8")
            require(len(columns) == 8, "FIXED_PDE8_COUNT")
            raw = extract(
                saved, state, ("P", "Y", "WY", "r", "qr", "theta"), design, columns
            )
            require(
                array_sha(raw["theta"]) == identity["parameter_sha256"],
                "FROZEN_THETA_HASH",
            )
            require(
                abs(np.linalg.norm(raw["theta"]) - identity["parameter_norm"]) <= 1e-12,
                "FROZEN_THETA_NORM",
            )
            packet = {key: raw[key] for key in ("P", "Y", "WY", "r", "qr")}
            packet["theta_norm"] = identity["parameter_norm"]
            for rcond in design["rconds"]:
                require(monotonic() - started < 750, "ARRAY_CONSTRUCTION_SAVE_RESERVE")
                key = f"{state}_{rcond:g}"
                try:
                    candidate = native_candidate(packet, rcond)
                    candidate.update(
                        state=state,
                        rcond=rcond,
                        columns=columns,
                        source_sha=head,
                        parameter_sha256=identity["parameter_sha256"],
                        complete_c_sha256=identity["complete_c_sha256"],
                        array_sha256=design["inputs"]["vectors"]["sha256"],
                        construction_array_members=[
                            state + "_" + name
                            for name in ("P", "Y", "WY", "r", "qr", "theta")
                        ],
                        reference_members_accessed=False,
                    )
                    path = directory / (key + "_native_candidate.json")
                    digest = atomic_json(path, candidate)
                    candidates[key] = dict(path=str(path.resolve()), sha256=digest)
                    events.append(
                        dict(
                            event="UNLABELED_CANDIDATE_FSYNC_HASHED",
                            key=key,
                            sha256=digest,
                            pid=os.getpid(),
                            elapsed_seconds=monotonic() - started,
                        )
                    )
                except ValueError as error:
                    unknown.append(
                        dict(
                            state=state,
                            rcond=rcond,
                            phase="construction",
                            status="UNKNOWN",
                            reason=str(error),
                        )
                    )
            del raw, packet
    ledger = directory / "candidate_freeze.json"
    ledger_sha = atomic_json(
        ledger,
        dict(
            candidates=candidates,
            events=events,
            source_sha=head,
            all_construction_finished_before_reference_process=True,
        ),
    )
    record = dict(
        source_sha=head,
        review_publication=campaign["review_publication"],
        design=dict(path=str(Path(design_path).resolve()), sha256=sha(design_path)),
        inputs=design["inputs"],
        original_C1_source=design["original_C1_source"],
        candidates=candidates,
        ledger=dict(path=str(ledger.resolve()), sha256=ledger_sha),
        unknown=unknown,
        events=events,
        pid=os.getpid(),
        elapsed_seconds=monotonic() - started,
        constructed_utc=datetime.now(timezone.utc).isoformat(),
        reference_members_accessed=False,
        new_actions=dict(
            A=0, AH=0, G=0, Gsolve=0, factor=0, network_forward=0, training=0
        ),
        **POLICY,
    )
    atomic_json(directory / "construction.json", record)
    print(
        json.dumps(
            dict(
                status="CANDIDATES_FROZEN",
                candidates=len(candidates),
                unknown=len(unknown),
            )
        )
    )


def frozen(directory):
    directory = Path(directory)
    record = json.loads((directory / "construction.json").read_text())
    _, design = design_input(read_checked(record["design"]))
    ledger = json.loads(read_checked(record["ledger"]).read_text())
    require(
        ledger["candidates"] == record["candidates"]
        and ledger["events"] == record["events"],
        "ACTUAL_FREEZE_LEDGER",
    )
    require(
        ledger["all_construction_finished_before_reference_process"] is True
        and record["reference_members_accessed"] is False,
        "FREEZE_ORDER",
    )
    candidates = {
        key: json.loads(read_checked(entry).read_text())
        for key, entry in record["candidates"].items()
    }
    for key, c in candidates.items():
        state = c["state"]
        require(key == f"{state}_{c['rcond']:g}", "CANDIDATE_KEY")
        require(
            c["source_sha"] == record["source_sha"]
            and c["array_sha256"] == design["inputs"]["vectors"]["sha256"],
            "CANDIDATE_SOURCE_INPUT",
        )
        require(
            c["parameter_sha256"] == design["states"][state]["parameter_sha256"]
            and c["complete_c_sha256"] == design["states"][state]["complete_c_sha256"],
            "CANDIDATE_STATE_IDENTITY",
        )
        require(c["reference_members_accessed"] is False, "LABEL_BOUNDARY")
    require(
        len(record["events"]) == len(candidates)
        and {e["key"] for e in record["events"]} == set(candidates),
        "FREEZE_EVENT_COVERAGE",
    )
    require(
        ledger["source_sha"] == record["source_sha"]
        and all(record[k] == v for k, v in POLICY.items()),
        "LEDGER_SOURCE_USE_POLICY",
    )
    for event in record["events"]:
        require(
            event["event"] == "UNLABELED_CANDIDATE_FSYNC_HASHED"
            and event["sha256"] == record["candidates"][event["key"]]["sha256"]
            and event["pid"] == record["pid"]
            and event["elapsed_seconds"] >= 0,
            "FREEZE_EVENT_HASH_PID",
        )
    return record, design, candidates


def score(directory):
    from benchmarks.check_feinn_native_constraint import direct_points

    started = monotonic()
    source()
    record, design, candidates = frozen(directory)
    require(record["pid"] != os.getpid(), "INDEPENDENT_SCORING_PROCESS_REQUIRED")
    checked, _ = inputs(design)
    rows = []
    with np.load(checked["vectors"], allow_pickle=False) as saved:
        for key, candidate in candidates.items():
            state = candidate["state"]
            columns = provenance_columns(
                design["states"][state]["directions"], 16, "PDE8"
            )
            require(candidate["columns"] == columns, "PDE8_COLUMN_IDENTITY")
            raw = extract(
                saved,
                state,
                ("P", "Y", "WY", "X", "GX", "r", "qr", "e", "Ge"),
                design,
                columns,
            )
            # This is the original saved R-minimum, never recomputed or adjusted.
            old_entry = design["original_R_candidates"][key]
            old = json.loads(read_checked(old_entry).read_text())
            require(
                old["state"] == state and old["columns"] == columns,
                "ORIGINAL_R_CANDIDATE_IDENTITY",
            )
            old_alpha = np.asarray(old["alpha"])
            points = {
                name: direct_points(raw, alpha, design["native_denominator"])
                for name, alpha in (
                    ("zero", np.zeros(len(columns))),
                    ("original_R_minimum", old_alpha),
                    ("native_constrained", np.asarray(candidate["alpha"])),
                )
            }
            rows.append(
                dict(
                    key=key,
                    state=state,
                    rcond=candidate["rcond"],
                    candidate=record["candidates"][key],
                    original_R_candidate=old_entry,
                    points=points,
                    **POLICY,
                )
            )
    result = dict(
        **record,
        configurations=rows,
        scoring_pid=os.getpid(),
        scoring_utc=datetime.now(timezone.utc).isoformat(),
        scoring_elapsed_seconds=monotonic() - started,
        candidate_construction_finished_before_scoring=True,
    )
    atomic_json(Path(directory) / "result.json", result)
    print(
        json.dumps(
            dict(
                status="INDEPENDENT_POST_FREEZE_FIELD_SCORING_COMPLETE",
                configurations=len(rows),
            )
        )
    )


def check(directory, output):
    from benchmarks.check_feinn_native_constraint import verify

    source()
    record, design, candidates = frozen(directory)
    result = json.loads((Path(directory) / "result.json").read_text())
    require(
        result["source_sha"] == record["source_sha"]
        and all(result[k] == v for k, v in POLICY.items()),
        "RESULT_SOURCE_USE_POLICY",
    )
    require(
        result["candidates"] == record["candidates"]
        and result["ledger"] == record["ledger"],
        "RESULT_FREEZE_BINDING",
    )
    require(
        result["scoring_pid"] != record["pid"]
        and result["candidate_construction_finished_before_scoring"] is True,
        "SCORING_ORDER",
    )
    checked, _ = inputs(design)
    keys = [row["key"] for row in result["configurations"]]
    require(
        len(set(keys)) == len(keys) and set(keys) == set(candidates),
        "CONFIGURATION_COVERAGE",
    )
    rows, delta, stability = {}, {}, {}
    with np.load(checked["vectors"], allow_pickle=False) as saved:
        for row in result["configurations"]:
            key, state = row["key"], row["state"]
            c = candidates[key]
            require(
                row["candidate"] == record["candidates"][key]
                and row["rcond"] == c["rcond"],
                "ROW_CANDIDATE_BINDING",
            )
            require(all(row[k] == v for k, v in POLICY.items()), "RESULT_USE_POLICY")
            columns = provenance_columns(
                design["states"][state]["directions"], 16, "PDE8"
            )
            require(c["columns"] == columns, "PDE8_COLUMN_IDENTITY")
            raw = extract(
                saved,
                state,
                ("P", "Y", "WY", "X", "GX", "r", "qr", "e", "Ge"),
                design,
                columns,
            )
            old_entry = design["original_R_candidates"][key]
            require(
                row["original_R_candidate"] == old_entry, "ORIGINAL_CONTROL_BINDING"
            )
            old = json.loads(read_checked(old_entry).read_text())
            rows[key] = verify(
                c,
                raw,
                row["points"],
                np.asarray(old["alpha"]),
                design["native_denominator"],
            )
            delta[key] = raw["P"] @ np.asarray(c["alpha"])
        for state in design["states"]:
            main, sense = state + "_1e-10", state + "_1e-12"
            if main not in rows or sense not in rows:
                stability[state] = dict(
                    status="UNKNOWN",
                    admitted=False,
                    reason="MISSING_MAIN_OR_SENSITIVITY",
                )
                continue
            defect = float(
                np.linalg.norm(delta[main] - delta[sense])
                / max(np.linalg.norm(delta[main]), np.finfo(float).tiny)
            )
            robust = rows[main]["rank"] == rows[sense]["rank"] == 8 and defect <= 1e-8
            stability[state] = dict(
                status="PASS" if robust else "UNKNOWN",
                rank_main=rows[main]["rank"],
                rank_sensitivity=rows[sense]["rank"],
                physical_step_relative=defect,
                admitted=bool(robust and rows[main]["threshold_candidate"]),
            )
    admitted = len(stability) == 2 and all(
        row["admitted"] for row in stability.values()
    )
    entry = dict(
        status="COMPLETE" if len(rows) == 4 else "PARTIAL",
        configurations=rows,
        sensitivity=stability,
        C_admitted=admitted,
        C_gate="BOTH_STATES_LINEAR_ADMITTED" if admitted else "NOT_ADMITTED",
        result=dict(
            path=str((Path(directory) / "result.json").resolve()),
            sha256=sha(Path(directory) / "result.json"),
        ),
        construction_sha256=sha(Path(directory) / "construction.json"),
        ledger=record["ledger"],
        candidates=record["candidates"],
        checker_source_sha=source(),
        optimize_calls=0,
        **POLICY,
    )
    atomic_json(output, entry)
    print(
        json.dumps(
            dict(
                status=entry["status"], C_gate=entry["C_gate"], configurations=len(rows)
            )
        )
    )
