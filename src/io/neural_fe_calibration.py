"""One-run V8 opt-ins, frozen V7 identity, and current cumulative billing."""

import json
from pathlib import Path

import tomllib

from src.common.optical_material_table import load_si_optical_constants
from src.io.input_loader import InputError
from src.io.neural_fe_continuation import DESIGN_PATH, read_index
from src.io.run_specification import RunSpecification
from src.io.task042_profile import ROOT
from src.solvers.neural_fe_action_packet import file_hash

PLAN_PATH = ROOT / "input/task042_neural_coarse_inverse/calibration_v8.json"
V8_ROOT = ROOT / "benchmarks/artifacts/task042/v8"
STAGES = {
    "reuse_inventory": ("task042_v8_reuse_inventory", "V8-C0", "pure", 600),
    "column_setup": ("task042_v8_column_setup", "V8-C2-SETUP", "fe", 3600),
    "scaled_lsqr": ("task042_v8_scaled_lsqr", "V8-C2-LSQR", "fe", 7200),
    "scaled_verification": (
        "task042_v8_scaled_verification",
        "V8-C2-VERIFY",
        "fe",
        1800,
    ),
    "batch_equivalence": (
        "task042_v8_batch_equivalence",
        "V8-C3-EQUIVALENCE",
        "ml",
        1200,
    ),
    "batch_microbenchmark": (
        "task042_v8_batch_microbenchmark",
        "V8-C3-MICRO",
        "ml",
        600,
    ),
}


def frozen_plan():
    plan = json.loads(PLAN_PATH.read_text())
    if file_hash(DESIGN_PATH) != plan["design"]["sha256"]:
        raise ValueError("V7 design changed")
    design = json.loads(DESIGN_PATH.read_text())
    material = load_si_optical_constants(design["wavelength_nm"])
    fe, _ = read_index("qualified_real_fe")
    gradient, _ = read_index("qualified_real_gradient")
    if (
        fe["status"] != "PASS"
        or gradient["status"] != "PASS"
        or material.provenance["material_table_sha256"] != plan["material_table_sha256"]
        or fe["physical"]["physical_model_sha256"] != plan["physical_model_sha256"]
        or fe["physical"]["mode_manifest_sha256"] != plan["mode_manifest_sha256"]
        or fe["design_sha256"] != plan["design"]["sha256"]
        or gradient["design_sha256"] != plan["design"]["sha256"]
    ):
        raise ValueError("qualified unchanged material/operator/N1 required")
    return plan, design, material, fe


def read_v8_index(name):
    entry = json.loads((V8_ROOT / (name + ".json")).read_text())
    path = Path(entry["path"]).resolve()
    if not path.is_relative_to(V8_ROOT) or file_hash(path) != entry["sha256"]:
        raise ValueError("V8 indexed path/hash ownership failure")
    result = json.loads(path.read_text())
    if result["plan_sha256"] != file_hash(PLAN_PATH):
        raise ValueError("V8 plan changed after qualification")
    return result, path


def budget_snapshot():
    from src.runners.neural_fe_continuation import budget_snapshot as prior_budget

    prior = prior_budget()
    records = []
    for base, pattern in (
        (ROOT / "results/task042", "task042_v8_*/run_summary.json"),
        (ROOT / "tmp/task042/v8", "*/summary.json"),
    ):
        for path in sorted(base.glob(pattern)):
            value = json.loads(path.read_text())
            billed = value.get("launch_wall_seconds", value["elapsed_seconds"])
            timing = path.parent / "launcher_cost.json"
            if timing.exists():
                billed = json.loads(timing.read_text())["total_seconds"]
            records.append(
                dict(
                    path=str(path),
                    seconds=billed,
                    supervised_seconds=value["elapsed_seconds"],
                )
            )
    used = sum(r["seconds"] for r in records)
    return dict(
        carry_in_seconds=prior["used_seconds"],
        new_seconds=used,
        cumulative_seconds=prior["used_seconds"] + used,
        records=records,
        remaining_seconds=min(14400 - used, 36000 - prior["used_seconds"] - used),
        batch_limit_seconds=14400,
        cumulative_limit_seconds=36000,
        shared_workstation=True,
    )


def load_calibration(path):
    path = Path(path).resolve()
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if b"[task042_v8]" not in raw:
        return None
    try:
        config = tomllib.loads(raw.decode())
        item = config["task042_v8"]
        keys = {"stage", "run_id", "material_table_id"}
        if item["stage"] == "batch_microbenchmark":
            keys |= {"batch_size", "pair_id"}
        if (
            set(config) != {"schema_version", "task042_v8"}
            or config["schema_version"] != 1
            or set(item) != keys
        ):
            raise ValueError("one explicit V8 stage/options required")
        if (
            item["stage"] not in STAGES
            or not item["run_id"].startswith("task042_v8_")
            or Path(item["run_id"]).name != item["run_id"]
        ):
            raise ValueError("unregistered V8 stage/run id")
        if item["stage"] == "batch_microbenchmark" and (
            item["batch_size"] not in (1, 8) or item["pair_id"] not in (1, 2, 3)
        ):
            raise ValueError("only the preregistered batch1/8 and three pairs")
        plan, design, material, _ = frozen_plan()
        if item["material_table_id"] != material.provenance["material_table_id"]:
            raise ValueError("canonical material id mismatch")
        profile, stage, mode, timeout = STAGES[item["stage"]]
    except (OSError, KeyError, ValueError, tomllib.TOMLDecodeError) as error:
        raise InputError(f"Task042 V8 identity/input error: {error}") from error
    return RunSpecification(
        identity=dict(
            model_id="task042_v8_0p7nm_p3_micro",
            run_id=item["run_id"],
            batch=plan["batch"],
        ),
        geometry=design["geometry"],
        materials=material.provenance,
        incidence=design["incidence"],
        discretization=design["finite_element"],
        boundary=design["boundary"],
        method=dict(kind="fixed_scaling_and_execution_calibration_research_opt_in"),
        solver=dict(preconditioner=profile),
        execution=dict(
            mpi_size=1,
            timeout_seconds=timeout,
            warning_memory_gib=12,
            terminate_memory_gib=16,
            require_zero_swap=True,
        ),
        output=dict(results_root="results/task042"),
        derived=dict(
            stage=stage,
            environment_mode=mode,
            plan_sha256=file_hash(PLAN_PATH),
            physical_model_complete=True,
            physical_operator_sha256=plan["physical_model_sha256"],
            identity_hash_meaning="unchanged V7 complete physical/operator recipe; arrays separately bound",
            batch_size=item.get("batch_size"),
            pair_id=item.get("pair_id"),
        ),
        source_path=path,
        raw_input_bytes=raw,
        input_sha256=file_hash(path),
        physical_model_sha256=plan["physical_model_sha256"],
        expected_output_parent=ROOT / "results/task042",
    )
