"""One fixed-state V9 inventory; no training packets, scale search or solves."""

import json
from pathlib import Path

import numpy as np
import tomllib

from src.io.input_loader import InputError
from src.io.neural_fe_calibration import frozen_plan, read_v8_index
from src.io.neural_fe_continuation import read_index
from src.io.run_specification import RunSpecification
from src.io.task042_profile import ROOT
from src.solvers.neural_fe_action_packet import array_hash, file_hash

PLAN_PATH = ROOT / "input/task042_neural_coarse_inverse/frozen_error_v9.json"
V9_ROOT = ROOT / "benchmarks/artifacts/task042/v9"


def budget_snapshot():
    prior = json.loads(
        (
            ROOT
            / "docs/task042_neural_coarse_inverse/outcomes/records/resource_costs_v8.json"
        ).read_text()
    )
    carry = prior["budget"]["cumulative_seconds"]
    records = []
    for base, pattern in (
        (ROOT / "tmp/task042/v9", "*/summary.json"),
        (ROOT / "results/task042", "task042_v9_*/run_summary.json"),
    ):
        for path in sorted(base.glob(pattern)):
            value = json.loads(path.read_text())
            seconds = value.get("launch_wall_seconds", value["elapsed_seconds"])
            timing = path.parent / "launcher_cost.json"
            if timing.exists():
                seconds = json.loads(timing.read_text())["total_seconds"]
            records.append(
                dict(
                    path=str(path),
                    seconds=seconds,
                    supervised_seconds=value["elapsed_seconds"],
                )
            )
    used = sum(row["seconds"] for row in records)
    return dict(
        carry_in_seconds=carry,
        new_seconds=used,
        cumulative_seconds=carry + used,
        remaining_seconds=min(3600 - used, 36000 - carry - used),
        records=records,
        batch_limit_seconds=3600,
        cumulative_limit_seconds=36000,
        shared_workstation=True,
    )


def plan_and_operator():
    plan = json.loads(PLAN_PATH.read_text())
    _, design, material, fe = frozen_plan()
    if any(
        fe["physical"][key] != plan[key]
        for key in ("physical_model_sha256", "mode_manifest_sha256")
    ):
        raise ValueError("fixed V9 operator identity changed")
    if fe["packet"]["sha256"] != plan["action_packet_sha256"]:
        raise ValueError("original action packet differs from reviewed identity")
    return plan, design, material, fe


def load_diagnostic(path):
    path = Path(path).resolve()
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if b"[task042_v9]" not in raw:
        return None
    try:
        cfg = tomllib.loads(raw.decode())
        item = cfg["task042_v9"]
        plan, design, material, _ = plan_and_operator()
        if (
            set(cfg) != {"schema_version", "task042_v9"}
            or cfg["schema_version"] != 1
            or set(item) != {"stage", "run_id", "material_table_id"}
            or item["stage"] != "frozen_error_localization"
            or item["run_id"] != "task042_v9_frozen_error"
            or item["material_table_id"] != material.provenance["material_table_id"]
        ):
            raise ValueError("one reviewed operator and fixed six-state inventory only")
    except (OSError, ValueError, KeyError, tomllib.TOMLDecodeError) as error:
        raise InputError(f"Task042 V9 input/identity error: {error}") from error
    return RunSpecification(
        identity=dict(
            model_id="task042_v9_0p7nm_p3_micro",
            run_id=item["run_id"],
            batch=plan["batch"],
        ),
        geometry=design["geometry"],
        materials=material.provenance,
        incidence=design["incidence"],
        discretization=design["finite_element"],
        boundary=design["boundary"],
        method=dict(kind="frozen_FE_error_offline_diagnostic_research_opt_in"),
        solver=dict(preconditioner="task042_v9_frozen_error_localization"),
        execution=dict(
            mpi_size=1,
            timeout_seconds=3600,
            warning_memory_gib=12,
            terminate_memory_gib=16,
            require_zero_swap=True,
        ),
        output=dict(results_root="results/task042"),
        derived=dict(
            stage="V9-D0-D3",
            environment_mode="fe",
            plan_sha256=file_hash(PLAN_PATH),
            physical_model_complete=True,
            physical_operator_sha256=plan["physical_model_sha256"],
            identity_hash_meaning="unchanged frozen V7 micro-pilot, offline fixed errors only",
        ),
        source_path=path,
        raw_input_bytes=raw,
        input_sha256=file_hash(path),
        physical_model_sha256=plan["physical_model_sha256"],
        expected_output_parent=ROOT / "results/task042",
    )


def owned_vector(record, allowed_root, expected_size):
    path = Path(record["path"]).resolve()
    if not path.is_relative_to(allowed_root) or file_hash(path) != record["sha256"]:
        raise ValueError("saved state path/hash ownership mismatch")
    # Only z is decoded. NN parameters, moments, Torch and scaled y are unused.
    with np.load(path, allow_pickle=False) as contents:
        z = np.array(contents["z"])
    if (
        z.shape != (expected_size,)
        or z.dtype != np.complex128
        or not np.isfinite(z).all()
    ):
        raise ValueError("canonical complex128 physical z inventory mismatch")
    if array_hash(z) != record["z_sha256"]:
        raise ValueError("saved physical z array hash mismatch")
    z.setflags(write=False)
    return z


def read_frozen_states(packet, fe, plan):
    from src.io.neural_fe_calibration import V8_ROOT
    from src.io.neural_fe_continuation import V7_ROOT

    indices = {}
    for version in (7, 8):
        path = (
            ROOT
            / f"docs/task042_neural_coarse_inverse/outcomes/records/run_index_v{version}.json"
        )
        value = json.loads(path.read_text())
        rows = value["formal_runs"] if version == 7 else value["runs"]
        indices.update({Path(row["directory"]): row for row in rows})
    states = {"Z0": np.zeros(packet.size, np.complex128)}
    inventory = [
        dict(
            id="Z0",
            available=True,
            generated="only reduced trace and ports zero",
            z_sha256=array_hash(states["Z0"]),
            shape=[packet.size],
            dtype="complex128",
        )
    ]
    for item in plan["states"]:
        name = item["id"]
        try:
            read = read_v8_index if item["version"] == 8 else read_index
            value, path = read(item["index"])
            original = indices[
                next(key for key in indices if key.name == path.parent.name)
            ]
            manifest_path = Path(original["directory"]) / "run_manifest.json"
            expected_manifest_hash = (
                original["run_manifest_sha256"]
                if item["version"] == 8
                else original["manifest"]["sha256"]
            )
            if file_hash(manifest_path) != expected_manifest_hash:
                raise ValueError(
                    "original run manifest differs from committed run index"
                )
            manifest = json.loads(manifest_path.read_text())
            if (
                value["operator_packet"] != fe["packet"]
                or value["physical"] != fe["physical"]
                or value["source_sha"] != item["source_sha"]
                or value["source_sha"] != manifest["source_sha"]
                or manifest["git_status"] != ""
                or manifest["physical_model_sha256"] != plan["physical_model_sha256"]
                or value["design_sha256"] != fe["design_sha256"]
            ):
                raise ValueError(
                    "state source/operator/physical/background/RHS identity mismatch"
                )
            state = value["reference_state"] if name == "REF7" else value["state"]
            if (
                state["sha256"] != item["npz_sha256"]
                or state["z_sha256"] != item["z_sha256"]
            ):
                raise ValueError("preregistered frozen vector changed")
            if name == "LSQR8" and (
                value["column_scaling"] is not True
                or value["state_kind"] != "LSQR_ITERATE"
            ):
                raise ValueError("LSQR8 saved coordinate is not confirmed original z")
            if name == "REF7" and (
                not value["factor"]["factor_released"]
                or value["factor"]["numeric_calls"] != 1
            ):
                raise ValueError("saved reference factor identity/lifecycle mismatch")
            z = owned_vector(
                state, V8_ROOT if item["version"] == 8 else V7_ROOT, packet.size
            )
            states[name] = z
            inventory.append(
                dict(
                    id=name,
                    available=True,
                    result_path=str(path),
                    result_sha256=file_hash(path),
                    manifest_path=str(
                        Path(original["directory"]) / "run_manifest.json"
                    ),
                    manifest_sha256=file_hash(
                        Path(original["directory"]) / "run_manifest.json"
                    ),
                    source_sha=value["source_sha"],
                    state=state,
                    shape=list(z.shape),
                    dtype=str(z.dtype),
                    physical_coordinates="z; D not loaded or applied",
                    offline_reference=name == "REF7",
                    acceptance_state="UNKNOWN"
                    if name in ("NN7", "FREE7")
                    else "NOT_APPLICABLE",
                )
            )
        except (OSError, KeyError, ValueError, StopIteration) as error:
            inventory.append(
                dict(
                    id=name, available=False, reason=f"{type(error).__name__}: {error}"
                )
            )
    return states, inventory
