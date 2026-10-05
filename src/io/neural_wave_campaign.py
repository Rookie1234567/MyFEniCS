"""Explicit V30 wave-network inputs, isolated from all legacy case defaults."""

import hashlib
import json
from pathlib import Path
import tomllib

from src.io.input_loader import InputError

ROOT = Path(__file__).resolve().parents[2]
DESIGN = ROOT / "input/task042extra_feinn_5nm/design_v30.json"
WINDOW = ROOT / "tmp/task42extra/v30/batch_window.json"
ARTIFACTS = ROOT / "benchmarks/artifacts/task42extra/v30"
STAGES = {
    "v30_wave_checks": ("fe", 7200, "checks"),
    "v30_wave_calibration_5nm": ("fe", 1800, "calibration"),
    "v30_wave_calibration_0p7nm": ("fe", 1800, "calibration"),
    "v30_m5_fixed_wave": ("ml", 172800, "FIXED_WAVE_GREEDY_CONTROL"),
    "v30_m5_learned_wave": ("ml", 172800, "LEARNED_WAVE_GREEDY"),
    "v30_m5_verify": ("fe", 7200, "verify"),
}


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(2**20), b""):
            h.update(block)
    return h.hexdigest()


def load_wave(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    if b"[neural_wave]" not in raw:
        return None
    try:
        data = tomllib.loads(raw.decode())
    except (UnicodeError, tomllib.TOMLDecodeError) as error:
        raise InputError(str(error)) from error
    if set(data) != {"schema_version", "neural_wave"} or data["schema_version"] != 1:
        raise InputError("V30 accepts one explicit wave-network stage")
    item = data["neural_wave"]
    allowed = {"stage", "design_sha256", "native_target"}
    if set(item) - allowed or not {"stage", "design_sha256"} <= set(item):
        raise InputError("V30 unknown/missing keys; no reference/teacher path accepted")
    stage = item["stage"]
    if stage not in STAGES or digest(DESIGN) != item["design_sha256"]:
        raise InputError("unknown V30 stage or changed frozen design")
    design = json.loads(DESIGN.read_text())
    if design["schema"] != "neural-wave.unlabelled-design.v1":
        raise InputError("V30 design identity changed")
    if set(design["files"]) != {"native", "moments_q15", "moments_q30"}:
        raise InputError("training data whitelist excludes Gram/reference/legacy NN")
    target = item.get("native_target", design["strategy"]["native_target"])
    if target not in (1e-8, 1e-10):
        raise InputError("only original residual goals preauthorized by Review V29")
    mode, seconds, role = STAGES[stage]
    return dict(
        stage=stage,
        mode=mode,
        role=role,
        max_seconds=seconds,
        input=str(path.relative_to(ROOT)),
        input_sha256=hashlib.sha256(raw).hexdigest(),
        design_sha256=item["design_sha256"],
        native_target=target,
        case="reduced_0p7" if "reduced" in stage else "M5",
        schema="neural-wave.one-run.v1",
    )


def load_training_files(design):
    """Only original action and complete moments; no helper reads a label."""
    if set(design["files"]) != {"native", "moments_q15", "moments_q30"}:
        raise ValueError("TRAINING_FILE_WHITELIST_VIOLATION")
    for entry in design["files"].values():
        path = (ROOT / entry["path"]).resolve()
        if not path.is_relative_to(ROOT / "benchmarks/artifacts/task42extra"):
            raise ValueError("TRAINING_DATA_OUTSIDE_TASK")
        if digest(path) != entry["sha256"]:
            raise ValueError("ORIGINAL_M5_DATA_HASH_FAILED: " + entry["path"])
    return {key: ROOT / entry["path"] for key, entry in design["files"].items()}


def training_open_allowed(path, design):
    """Runtime isolation of numerical training files, including hidden helpers."""
    try:
        file = Path(path).resolve()
    except TypeError:
        return True  # file descriptor, not a new filename
    if file.suffix in (".pt", ".pth"):
        return False
    if file.suffix == ".npz":
        allowed = {
            (ROOT / entry["path"]).resolve() for entry in design["files"].values()
        }
        return file in allowed or (
            file.is_relative_to(ARTIFACTS)
            and ("basis" in file.parts or file.name.startswith("final_state"))
        )
    if file.name.startswith("index_e3_reference") or file.name == "reference_state.npz":
        return False
    return True
