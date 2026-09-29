"""Explicit one-run V7 inputs; no changes to ordinary solver defaults."""

import hashlib
import json
from pathlib import Path

import tomllib

from src.common.optical_material_table import load_si_optical_constants
from src.io.input_loader import InputError
from src.io.run_specification import RunSpecification
from src.io.task042_profile import ROOT

DESIGN_PATH = ROOT / "input/task042_neural_coarse_inverse/neural_fe_design_v7.json"
V7_ROOT = ROOT / "benchmarks/artifacts/task042/v7"
STAGES = {
    "same_mesh_p3_reference": (
        "task042_v7_same_mesh_p3_reference",
        "V7-M3-REFERENCE",
        "fe",
        7200,
    ),
    "neural_trace": ("task042_v7_neural_trace", "V7-M2-NEURAL", "ml", 7200),
    "free_fe_opt": ("task042_v7_free_fe_opt", "V7-M2-FREE", "ml", 7200),
    "fe_lsqr": ("task042_v7_fe_lsqr", "V7-M2-LSQR", "fe", 7200),
    "material_inventory": ("task042_v7_material_inventory", "V7-M0", "fe", 600),
    "real_fe_interface": ("task042_v7_real_fe_interface", "V7-M1-FE", "fe", 1800),
    "real_equation_gradient": (
        "task042_v7_real_equation_gradient",
        "V7-M1-GRAD",
        "ml",
        1800,
    ),
}


def read_index(name):
    index_path = V7_ROOT / (name + ".json")
    entry = json.loads(index_path.read_text())
    path = Path(entry["path"]).resolve()
    if (
        not path.is_relative_to(V7_ROOT)
        or hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]
    ):
        raise ValueError(f"V7 {name} path/hash identity failure")
    return json.loads(path.read_text()), path


def load_continuation(path):
    path = Path(path).resolve()
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if b"[task042_v7]" not in raw:
        return None
    try:
        config = tomllib.loads(raw.decode())
        item = config["task042_v7"]
        if (
            set(config) != {"schema_version", "task042_v7"}
            or config["schema_version"] != 1
            or set(item) != {"stage", "run_id", "material_table_id"}
            or item["stage"] not in STAGES
        ):
            raise ValueError("V7 one-run explicit stage inventory mismatch")
        if (
            not item["run_id"].startswith("task042_v7_")
            or Path(item["run_id"]).name != item["run_id"]
        ):
            raise ValueError("V7 run_id must be a local filename")
        design = json.loads(DESIGN_PATH.read_text())
        material = load_si_optical_constants(design["wavelength_nm"])
        if (
            item["material_table_id"] != material.provenance["material_table_id"]
            or design["materials"]["material_table_sha256"]
            != material.provenance["material_table_sha256"]
        ):
            raise ValueError("V7 material table identity mismatch")
        design_hash = hashlib.sha256(DESIGN_PATH.read_bytes()).hexdigest()
        physical_hash = None
        if item["stage"] != "material_inventory":
            inventory, _ = read_index("material_inventory")
            if inventory["design_sha256"] != design_hash:
                raise ValueError("V7 physical inventory design mismatch")
            physical_hash = inventory["physical_model_sha256"]
        profile, stage, mode, timeout = STAGES[item["stage"]]
    except (KeyError, ValueError, OSError, tomllib.TOMLDecodeError) as exc:
        raise InputError(f"V7 continuation input/identity error: {exc}") from exc
    return RunSpecification(
        identity=dict(
            model_id="task042_v7_0p7nm_p3_micro",
            run_id=item["run_id"],
            batch=design["batch"],
        ),
        geometry=design["geometry"],
        materials=material.provenance,
        incidence=design["incidence"],
        discretization=design["finite_element"],
        boundary=design["boundary"],
        method=dict(kind="neural_fe_single_solve_research_opt_in"),
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
            design_path=str(DESIGN_PATH),
            design_sha256=design_hash,
            physical_model_complete=physical_hash is not None,
            physical_operator_sha256=physical_hash,
            identity_hash_meaning="complete material/geometric/operator channel recipe"
            if physical_hash
            else "M0 inventory pending; design hash only",
        ),
        source_path=path,
        raw_input_bytes=raw,
        input_sha256=hashlib.sha256(raw).hexdigest(),
        physical_model_sha256=physical_hash or design_hash,
        expected_output_parent=ROOT / "results/task042",
    )
