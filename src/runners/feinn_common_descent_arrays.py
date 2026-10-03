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


def check(result_path, output):
    from benchmarks.check_feinn_common_descent import verify_configuration, same

    result_path = Path(result_path)
    result = json.loads(result_path.read_text())
    design_path = read_checked(result["design"])
    design = json.loads(design_path.read_text())
    require(result["inputs"] == design["inputs"], "RESULT_INPUT_BINDING")
    checked, _ = inputs(design)
    rows = []
    with np.load(checked["vectors"], allow_pickle=False) as saved:
        for state in design["states"]:
            raw = extract(saved, state, (*MATRICES, "e", "Ge", "r", "qr", "c", "theta"), design)
            m = metadata(state, design)
            require(array_sha(raw["c"]) == m["identity"]["complete_c_sha256"] and array_sha(raw["theta"]) == m["identity"]["parameter_sha256"], "RAW_STATE_HASH")
            for config in [c for c in result["configurations"] if c["state"] == state]:
                if config["subset"] == "PDE8":
                    candidate = json.loads(read_checked(config["frozen_candidate"]).read_text())
                    require(candidate["state"] == state and not candidate["reference_members_accessed"], "CANDIDATE_LABEL_BOUNDARY")
                    require(candidate["state_identity"] == m["identity"] and candidate["columns"] == config["columns"], "CANDIDATE_IDENTITY")
                    same(config["points"]["residual"]["alpha"], candidate["alpha"], 1e-12)
                    same(config["points"]["residual"]["u"], candidate["u"], 1e-10)
                    same(config["T"], candidate["T"], 1e-10)
                rows.append(verify_configuration(config, raw, m, design["states"][state]["parameter_norm"], design["native_denominator"]))
            del raw
    frozen = [e for e in result["events"] if e["event"] == "UNLABELED_CANDIDATE_FSYNC_HASHED"]
    first_reference = next(e for e in result["events"] if e["event"] == "REFERENCE_ARRAY_EVALUATION_BEGINS")
    require(all(e["monotonic_since_start"] < first_reference["monotonic_since_start"] for e in frozen), "FREEZE_BEFORE_LABEL_EVALUATION")
    atomic_json(output, dict(schema="feinn.saved-common-descent.checker.v1", result_sha256=sha(result_path),
                             rows=rows, unknown=result["unknown"], status="RAW_ARRAY_CERTIFICATES_VERIFIED",
                             optimize_calls=0, new_FE_or_network_actions=0, candidate_freeze_order_verified=True))
    print(json.dumps(dict(status="RAW_ARRAY_CERTIFICATES_VERIFIED", configurations=len(rows))))
