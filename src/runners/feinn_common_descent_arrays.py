"""One saved-array campaign, isolated from the heavy FE/ML dispatcher."""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from time import monotonic

import numpy as np

from src.solvers.feinn_common_descent import (
    analyze_configuration, atomic_json, provenance_columns, require, residual_candidate,
)

ROOT = Path(__file__).resolve().parents[2]
MATRICES = ("P", "X", "GX", "Y", "WY")


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while data := stream.read(1024 * 1024):
            digest.update(data)
    return digest.hexdigest()


def array_sha(value):
    return hashlib.sha256(np.ascontiguousarray(value).tobytes()).hexdigest()


def read_checked(entry):
    path = ROOT / entry["path"]
    require(path.resolve().is_relative_to(ROOT), "INPUT_PATH_ESCAPE")
    require(sha(path) == entry["sha256"], "FROZEN_INPUT_HASH")
    return path


def inputs(design, *, evaluation=True):
    checked = {key: read_checked(entry) for key, entry in design["inputs"].items()}
    if not evaluation:
        # Hashing bytes checks immutable identity; interpreting reference-bearing
        # result/geometry fields is explicitly postponed until candidate fsync.
        return checked, None
    index = json.loads(checked["index"].read_text())
    result = json.loads(checked["result"].read_text())
    require(index["source_sha"] == design["original_C1_source"], "C1_SOURCE_IDENTITY")
    require(index["files"]["vectors"]["sha256"] == design["inputs"]["vectors"]["sha256"], "C1_ARRAY_BINDING")
    require(index["files"]["result"]["sha256"] == design["inputs"]["result"]["sha256"], "C1_RESULT_BINDING")
    require(result["reference"] == design["packet_identity"], "PACKET_REFERENCE_IDENTITY")
    geometry = json.loads(checked["field_geometry"].read_text())
    geometry_index = json.loads(checked["field_geometry_index"].read_text())
    require(geometry_index["files"]["result"]["sha256"] == design["inputs"]["field_geometry"]["sha256"], "NATIVE_DENOMINATOR_BINDING")
    require(geometry["reference"] == result["reference"], "PHYSICAL_IDENTITY_CHANGED")
    for state in design["states"]:
        m = result["states"][state]
        require({k: m[k] for k in design["states"][state]} == design["states"][state], "STATE_METADATA_IDENTITY")
        require(geometry["rows"][state]["native_denominator"] == design["native_denominator"], "NATIVE_DENOMINATOR_CHANGED")
    return checked, result


def extract(npz, state, keys, design, columns=None):
    """Only the explicit member whitelist is accessed on lazy NPZ loading."""
    raw = {}
    for key in keys:
        value = npz[state + "_" + key]
        dtype = np.float64 if key in ("P", "theta") else np.complex128
        shape = (design["parameter_count"],) if key == "theta" else (design["FE_count"],)
        if key in MATRICES:
            shape = (design["parameter_count"] if key == "P" else design["FE_count"], 16)
        require(value.shape == shape and value.dtype == dtype, "FROZEN_ARRAY_LAYOUT")
        if key in MATRICES and columns is not None:
            value = value[:, columns].copy()
        require(np.isfinite(value).all(), "FROZEN_ARRAY_NONFINITE")
        raw[key] = value
    return raw


def metadata(state, design):
    row = design["states"][state]
    return dict(name=state, directions=row["directions"], identity=dict(
        parameter_sha256=row["parameter_sha256"], complete_c_sha256=row["complete_c_sha256"]))


def run(design_path, directory):
    started = monotonic()
    design_path, directory = Path(design_path), Path(directory)
    require(os.environ.get("TASK42EXTRA_ENV_MODE") == "pure", "PURE_ACTIVATION_REQUIRED")
    require(not directory.exists(), "IMMUTABLE_RUN_DIRECTORY")
    source = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip()
    clean = subprocess.check_output(["git", "status", "--porcelain=v1"], cwd=ROOT, text=True)
    require(branch == "task42extra_feinn_5nm" and not clean, "CLEAN_EXACT_SOURCE_REQUIRED")
    design = json.loads(design_path.read_text())
    checked, _ = inputs(design, evaluation=False)
    directory.mkdir(parents=True)
    candidates, events = {}, []
    configurations, unknown = [], []
    # Phase1: no e/Ge/gF/X/GX, nor any reference_G column, enters construction.
    with np.load(checked["vectors"], allow_pickle=False) as saved:
        for state in design["states"]:
            row = design["states"][state]
            try:
                columns = provenance_columns(row["directions"], 16, "PDE8")
                require(len(columns) == 8, "FIXED_PDE8_COUNT")
                raw = extract(saved, state, ("P", "Y", "WY", "r", "qr", "theta"), design, columns)
                require(array_sha(raw["theta"]) == row["parameter_sha256"], "THETA_HASH")
                require(abs(np.linalg.norm(raw["theta"]) - row["parameter_norm"]) <= 1e-12, "THETA_NORM_IDENTITY")
            except (ValueError, KeyError) as error:
                unknown.append(dict(state=state, subset="PDE8", phase="state_construction", status="UNKNOWN", reason=str(error)))
                continue
            packet = {k: raw[k] for k in ("P", "Y", "WY", "r", "qr")}
            packet["theta_norm"] = row["parameter_norm"]
            for rcond in design["rconds"]:
                key = f"{state}_{rcond:g}"
                try:
                    candidate = residual_candidate(packet, rcond)
                    candidate.update(state=state, columns=columns, source_sha=source,
                                     state_identity=metadata(state, design)["identity"],
                                     array_sha256=design["inputs"]["vectors"]["sha256"],
                                     construction_array_members=[state + "_" + k for k in ("P", "Y", "WY", "r", "qr", "theta")],
                                     reference_members_accessed=False)
                    path = directory / (key + "_candidate.json")
                    digest = atomic_json(path, candidate)
                    candidates[key] = dict(path=str(path.resolve()), sha256=digest)
                    events.append(dict(event="UNLABELED_CANDIDATE_FSYNC_HASHED", key=key, sha256=digest,
                                       monotonic_since_start=monotonic() - started))
                except ValueError as error:
                    unknown.append(dict(state=state, subset="PDE8", rcond=rcond, phase="construction", status="UNKNOWN", reason=str(error)))
            del raw, packet
        ledger_sha = atomic_json(directory / "candidate_freeze.json", dict(candidates=candidates, events=events))
        # Phase2 begins only after ALL candidate files and the ledger are durable.
        events.append(dict(event="REFERENCE_ARRAY_EVALUATION_BEGINS", monotonic_since_start=monotonic() - started,
                           preceding_candidate_ledger_sha256=ledger_sha))
        _, old = inputs(design)
        for state in design["states"]:
            try:
                raw = extract(saved, state, (*MATRICES, "e", "Ge", "r", "qr", "c"), design)
                require(array_sha(raw["c"]) == design["states"][state]["complete_c_sha256"], "COMPLETE_C_HASH")
            except (ValueError, KeyError) as error:
                unknown.append(dict(state=state, phase="state_evaluation", status="UNKNOWN", reason=str(error)))
                continue
            for subset in ("PDE8", "ALL16"):
                columns = provenance_columns(design["states"][state]["directions"], 16, subset)
                selected = {k: v[:, columns].copy() if k in MATRICES else v for k, v in raw.items()}
                for rcond in design["rconds"]:
                    try:
                        candidate = None
                        entry = candidates.get(f"{state}_{rcond:g}") if subset == "PDE8" else None
                        if subset == "PDE8":
                            require(entry is not None, "CANDIDATE_NOT_FROZEN")
                            candidate = json.loads(read_checked(entry).read_text())
                        config = analyze_configuration(selected, design["states"][state]["parameter_norm"], rcond,
                                                       design["native_denominator"], candidate)
                        config.update(state=state, subset=subset, columns=columns, state_identity=metadata(state, design)["identity"],
                                      residual_candidate_unlabeled=subset == "PDE8", frozen_candidate=entry,
                                      oracle_data_role="REFERENCE_EXPOSED_LOCAL_ORACLE")
                        configurations.append(config)
                    except ValueError as error:
                        unknown.append(dict(state=state, subset=subset, rcond=rcond, phase="evaluation", status="UNKNOWN", reason=str(error)))
                del selected
            del raw
    result = dict(schema="feinn.saved-common-descent.v1", source_sha=source, original_C1_source=old.get("source_sha", design["original_C1_source"]),
                  review_sha=design["review_sha"], design=dict(path=str(design_path.resolve()), sha256=sha(design_path)),
                  inputs=design["inputs"], configurations=configurations, unknown=unknown, candidates=candidates, events=events,
                  elapsed_worker_seconds=monotonic() - started, completed_utc=datetime.now(timezone.utc).isoformat(),
                  environment=dict(python=sys.executable, activation=os.environ.get("TASK42EXTRA_ENV_MODE"),
                                   affinity=sorted(os.sched_getaffinity(0)), mathematical_threads=1),
                  new_actions=dict(FE=0, A=0, AH=0, G=0, Gsolve=0, network_forward=0, training=0, factor=0, reference_solve=0),
                  value_kind="DERIVED_LOCAL_LINEAR_MODEL", main_solver="FEINN_MAIN_SOLVER_ON_HOLD", NN_increment="NO_VERIFIED_NN_INCREMENT")
    atomic_json(directory / "result.json", result)
    print(json.dumps(dict(result=str((directory / "result.json").resolve()), configurations=len(configurations), unknown=unknown,
                          lambda_evaluations=sum(c["common"]["lambda_evaluations"] for c in configurations))))


def frozen_evidence(result_path, result, design):
    """Actual files and ledger, not vacuous 'all events precede reference'."""
    from benchmarks.check_feinn_common_descent import diagnostic_policy, same

    expected = {f"{state}_{rc:g}" for state in design["states"] for rc in design["rconds"]}
    errors, loaded = [], {}
    ledger_path = Path(result_path).parent / "candidate_freeze.json"
    digest = None
    try:
        require(ledger_path.resolve().is_relative_to(ROOT), "LEDGER_PATH_ESCAPE")
        digest = sha(ledger_path)
        ledger = json.loads(ledger_path.read_text())
        require(set(result["candidates"]) <= expected, "EXTRA_CANDIDATE_KEY")
        require(ledger["candidates"] == result["candidates"], "ACTUAL_LEDGER_CANDIDATES")
        events = result["events"]
        require(all(e["event"] in ("UNLABELED_CANDIDATE_FSYNC_HASHED", "REFERENCE_ARRAY_EVALUATION_BEGINS") for e in events), "UNKNOWN_EVENT_TYPE")
        reference = [e for e in events if e["event"] == "REFERENCE_ARRAY_EVALUATION_BEGINS"]
        require(len(reference) == 1, "UNIQUE_REFERENCE_BEGIN_EVENT")
        frozen = [e for e in events if e["event"] == "UNLABELED_CANDIDATE_FSYNC_HASHED"]
        require(ledger["events"] == frozen, "ACTUAL_LEDGER_EVENTS")
        require(len(frozen) == len(result["candidates"]) and len({e["key"] for e in frozen}) == len(frozen), "UNIQUE_FREEZE_EVENTS")
        require({e["key"] for e in frozen} == set(result["candidates"]), "CANDIDATE_EVENT_BIJECTION")
        times = [e["monotonic_since_start"] for e in events]
        require(all(np.isfinite(t) and t >= 0 for t in times) and all(a < b for a, b in zip(times, times[1:])), "FINITE_ORDERED_EVENT_TIMES")
        require(events[-1] == reference[0] and reference[0]["preceding_candidate_ledger_sha256"] == digest, "REFERENCE_LEDGER_HASH")
        for event in frozen:
            require(event["sha256"] == result["candidates"][event["key"]]["sha256"], "EVENT_CANDIDATE_HASH")
    except (ValueError, KeyError, OSError, TypeError) as error:
        errors.append(dict(phase="actual_ledger_and_events", reason=str(error)))
    for state in design["states"]:
        for rc in design["rconds"]:
            key = f"{state}_{rc:g}"
            try:
                entry = result["candidates"][key]
                candidate = json.loads(read_checked(entry).read_text())
                require(candidate["source_sha"] == result["source_sha"], "CANDIDATE_NUMERICAL_SOURCE")
                require(candidate["state"] == state and candidate["state_identity"] == metadata(state, design)["identity"], "CANDIDATE_STATE_IDENTITY")
                require(candidate["array_sha256"] == design["inputs"]["vectors"]["sha256"], "CANDIDATE_ARRAY_IDENTITY")
                columns = provenance_columns(design["states"][state]["directions"], 16, "PDE8")
                require(candidate["columns"] == columns and len(columns) == 8, "CANDIDATE_PDE_COLUMNS")
                require(candidate["construction_array_members"] == [state + "_" + k for k in ("P", "Y", "WY", "r", "qr", "theta")], "CANDIDATE_CONSTRUCTION_ALLOWLIST")
                require(candidate["data_role"] == "UNLABELED_PDE8_RESIDUAL_CANDIDATE"
                        and candidate["reference_used_for_construction"] is False
                        and candidate["reference_members_accessed"] is False, "CANDIDATE_LABEL_ROLE")
                # Optional solver flags are forbidden even in the candidate file.
                diagnostic_policy(dict(candidate, data_role="REFERENCE_EXPOSED_LOCAL_ORACLE",
                                       value_kind="DERIVED_LOCAL_LINEAR_MODEL",
                                       main_solver="FEINN_MAIN_SOLVER_ON_HOLD", NN_increment="NO_VERIFIED_NN_INCREMENT"), top=True)
                require(candidate["basis"]["rcond"] == rc, "CANDIDATE_RCOND")
                same(candidate["rho"], 1e-3 * max(design["states"][state]["parameter_norm"], 1), 1e-12)
                for config in [c for c in result["configurations"] if c["state"] == state and c["subset"] == "PDE8" and c["rcond"] == rc]:
                    require(config["frozen_candidate"] == entry, "CONFIG_CANDIDATE_FILE_BINDING")
                    same(config["points"]["residual"]["alpha"], candidate["alpha"], 1e-12)
                    same(config["points"]["residual"]["u"], candidate["u"], 1e-10)
                    same(config["T"], candidate["T"], 1e-10)
                    require(config["basis"] == candidate["basis"], "CANDIDATE_BASIS_BINDING")
                    for field in ("H", "a"):
                        same(config["quadratic_R"][field], candidate[field + "_R"], 1e-10)
                    same(config["common"]["endpoint_multipliers"]["R"], candidate["trust"]["mu"], 1e-10)
                loaded[key] = candidate
            except (ValueError, KeyError, OSError, TypeError) as error:
                errors.append(dict(key=key, phase="candidate_file_and_binding", reason=str(error)))
    for config in result["configurations"]:
        if config["subset"] == "ALL16":
            require(config["frozen_candidate"] is None, "ORACLE_CANNOT_BE_UNLABELED_CANDIDATE")
    qualified = not errors and set(loaded) == expected
    return dict(status="PASS" if qualified else "UNKNOWN", qualified=qualified,
                actual_ledger=dict(path=str(ledger_path.resolve()), sha256=digest), errors=errors,
                candidate_hashes={k: v["sha256"] for k, v in result["candidates"].items()},
                code_and_execution_order_tests_also_required=True,
                file_hash_alone_proves_no_label_access=False), loaded


def check(result_path, output, *, run_index_path=None, expected_result_sha256=None,
          native_attribution=False):
    from benchmarks.check_feinn_common_descent import (
        admission, configuration_coverage, diagnostic_policy, verify_configuration,
    )
    from src.solvers.feinn_diagnostic_algebra import frozen_direction_attribution

    require(os.environ.get("TASK42EXTRA_ENV_MODE") == "pure", "PURE_ACTIVATION_REQUIRED")
    checker_source = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if run_index_path is not None:
        branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip()
        clean = subprocess.check_output(["git", "status", "--porcelain=v1"], cwd=ROOT, text=True)
        require(branch == "task42extra_feinn_5nm" and not clean, "CLEAN_EXACT_CHECKER_SOURCE_REQUIRED")
    result_path = Path(result_path)
    result_sha = sha(result_path)
    if expected_result_sha256 is not None:
        require(result_sha == expected_result_sha256, "AUTHORIZED_RESULT_HASH")
    result = json.loads(result_path.read_text())
    design_path = read_checked(result["design"])
    design = json.loads(design_path.read_text())
    require(result["inputs"] == design["inputs"], "RESULT_INPUT_BINDING")
    require(result["original_C1_source"] == design["original_C1_source"]
            and result["review_sha"] == design["review_sha"], "RESULT_SOURCE_REVIEW_BINDING")
    diagnostic_policy(result, top=True)
    require(set(result["new_actions"]) == {"FE", "A", "AH", "G", "Gsolve", "network_forward", "training", "factor", "reference_solve"}
            and all(v == 0 for v in result["new_actions"].values()), "DIAGNOSTIC_ACTION_SCOPE")
    index_entry = None
    if run_index_path is not None:
        index_path = Path(run_index_path)
        index = json.loads(index_path.read_text())
        require(read_checked(index["result"]).resolve() == result_path.resolve(), "RUN_INDEX_RESULT")
        require(index["source"] == result["source_sha"] and index["candidates"] == result["candidates"]
                and index["inputs"] == result["inputs"], "RUN_INDEX_SOURCE_CANDIDATES")
        index_entry = dict(path=str(index_path.resolve()), sha256=sha(index_path))
    expected, _, unknown = configuration_coverage(result, design)
    freeze, candidates = frozen_evidence(result_path, result, design)
    checked, _ = inputs(design)
    rows = []
    with np.load(checked["vectors"], allow_pickle=False) as saved:
        for state in design["states"]:
            raw = extract(saved, state, (*MATRICES, "e", "Ge", "r", "qr", "c", "theta"), design)
            m = metadata(state, design)
            require(array_sha(raw["c"]) == m["identity"]["complete_c_sha256"] and array_sha(raw["theta"]) == m["identity"]["parameter_sha256"], "RAW_STATE_HASH")
            for config in [c for c in result["configurations"] if c["state"] == state]:
                rows.append(verify_configuration(config, raw, m, design["states"][state]["parameter_norm"], design["native_denominator"]))
            del raw
    complete = not unknown and len(rows) == len(expected) and freeze["qualified"]
    status = "COMPLETE_RECORDS_VERIFIED" if complete else "PARTIAL" if rows else "UNKNOWN"
    attribution = []
    if native_attribution and complete:
        with np.load(checked["vectors"], allow_pickle=False) as saved:
            for state in design["states"]:
                raw = extract(saved, state, ("X", "GX", "Y", "WY", "e", "Ge", "r", "qr"), design)
                candidate = candidates[f"{state}_1e-10"]
                columns = candidate["columns"]
                selected = {k: v[:, columns] if k in MATRICES else v for k, v in raw.items()}
                attribution.append(dict(state=state, rcond=1e-10,
                                        frozen_candidate=result["candidates"][f"{state}_1e-10"],
                                        **frozen_direction_attribution(selected, candidate["alpha"], design["native_denominator"])))
                del raw, selected
    require(sha(result_path) == result_sha, "ORIGINAL_RESULT_CHANGED_DURING_CHECK")
    require(subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip() == checker_source, "CHECKER_SOURCE_CHANGED_DURING_CHECK")
    record = dict(schema="feinn.saved-common-descent.checker.v2", result_sha256=result_sha,
                  original_numerical_source=result["source_sha"], original_C1_source=result["original_C1_source"],
                  checker_source=checker_source, design=result["design"], run_index=index_entry,
                  environment=dict(python=sys.executable, activation=os.environ.get("TASK42EXTRA_ENV_MODE"),
                                   affinity=sorted(os.sched_getaffinity(0)), mathematical_threads=1),
                  inputs=result["inputs"], rows=rows, unknown=list(unknown.values()), status=status,
                  configuration_and_comparison_coverage=dict(status="COMPLETE" if not unknown else "PARTIAL" if rows else "UNKNOWN",
                      expected_configurations=len(expected), verified_configurations=len(rows), unknown_configurations=len(unknown),
                      verified_comparison_points=4 * len(rows), expected_keys=[list(k) for k in sorted(expected)]),
                  raw_vector_and_certificate_validity=dict(status="PASS" if not unknown else "PARTIAL" if rows else "UNKNOWN",
                                                           verified_configurations=len(rows)),
                  common_descent_threshold_evidence=[dict(state=r["state"], subset=r["subset"], rcond=r["rcond"],
                      status=r["classification"], L=r["L"], margin=r["margin"], U=r["U"]) for r in rows],
                  bound_width_qualification=[dict(state=r["state"], subset=r["subset"], rcond=r["rcond"],
                      status=r["bound_width_qualification"], width=r["bound_width"], target=1e-8) for r in rows],
                  unlabeled_two_state_admission=admission(rows, design["states"], design["rconds"], complete),
                  frozen_evidence=freeze, candidate_freeze_order_verified=freeze["qualified"],
                  native_direction_attribution=attribution,
                  native_attribution_status="COMPLETED" if attribution else "NOT_RUN" if not native_attribution else "NOT_RUN_P0_NOT_QUALIFIED",
                  optimize_calls=0, new_FE_or_network_actions=0, value_kind="DERIVED_LOCAL_LINEAR_MODEL",
                  effective_usage_flags=dict(pde_only_solve=False, production_initialization_allowed=False,
                      official_candidate_results=False, true_NN_increment=False),
                  legacy_top_flags_checked_via_explicit_rows=True,
                  main_solver="FEINN_MAIN_SOLVER_ON_HOLD", NN_increment="NO_VERIFIED_NN_INCREMENT")
    atomic_json(output, record)
    print(json.dumps(dict(status=status, configurations=len(rows), points=4 * len(rows),
                         frozen_evidence=freeze["status"], unlabeled_admission=record["unlabeled_two_state_admission"]["status"])))
    return record
