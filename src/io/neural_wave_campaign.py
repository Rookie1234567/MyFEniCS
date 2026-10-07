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
    "v30_wave_fast_checks": ("ml", 1800, "fast_checks"),
    "v30_wave_local_action_checks": ("ml", 3600, "local_action_checks"),
    "v30_wave_projection_checks": ("ml", 3600, "projection_checks"),
    "v30_wave_screening_checks": ("ml", 3600, "screening_checks"),
    "v30_wave_calibration_5nm": ("fe", 1800, "calibration"),
    "v30_wave_calibration_0p7nm": ("fe", 1800, "calibration"),
    "v30_m5_fixed_wave": ("ml", 172800, "FIXED_WAVE_GREEDY_CONTROL"),
    "v30_m5_learned_wave": ("ml", 172800, "LEARNED_WAVE_GREEDY"),
    "v30_m5_verify": ("fe", 7200, "verify"),
    "v30_m5_saved_audit": ("pure", 7200, "saved_audit"),
    "v30_m5_verify_final": ("fe", 7200, "verify"),
    "v30_m5_saved_audit_final": ("pure", 7200, "saved_audit"),
    "v30_m5_verify_recovery": ("fe", 3600, "verify_recovery"),
    "v30_m5_saved_audit_recovery": ("pure", 3600, "saved_audit"),
}


def profile_paths(spec):
    if spec.get("campaign_version") in (31, 32):
        version = spec["campaign_version"]
        root = ROOT / f"tmp/task42extra/v{version}"
        return dict(
            root=root,
            window=root / "batch_window.json",
            design=ROOT / f"input/task042extra_feinn_5nm/design_v{version}.json",
            artifacts=ROOT / f"benchmarks/artifacts/task42extra/v{version}",
            reserve=3600,
        )
    return dict(
        root=ROOT / "tmp/task42extra/v30",
        window=WINDOW,
        design=DESIGN,
        artifacts=ARTIFACTS,
        reserve=1800,
    )


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
    if data.get("schema_version") == 3:
        from src.io.multiscale_wave_campaign import load_multiscale

        return load_multiscale(path, data, raw)
    if data.get("schema_version") == 2:
        from src.io.block_wave_campaign import load_block_wave

        return load_block_wave(path, data, raw)
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
    if design.get("campaign_version") == 32 and file.is_relative_to(
        ROOT / "benchmarks/artifacts/task42extra"
    ):
        allowed = {
            (ROOT / entry["path"]).resolve() for entry in design["files"].values()
        }
        active = Path(design["active_training_artifact"]).resolve()
        if (
            file not in allowed
            and not file.is_relative_to(active)
            and file
            != ROOT
            / "benchmarks/artifacts/task42extra/v32/v32_multiscale_wave_checks/result.json"
        ):
            return False
    if file.suffix in (".pt", ".pth"):
        return False
    if design.get("campaign_version") == 31 and file.is_relative_to(ARTIFACTS):
        return False
    artifacts = (
        ROOT / "benchmarks/artifacts/task42extra/v31"
        if design.get("campaign_version") == 31
        else ARTIFACTS
    )
    if file.is_relative_to(artifacts) and any(
        part.startswith(
            (
                "v30_m5_verify",
                "v30_m5_saved_audit",
                "v31_saved_field",
                "v31_block_reconstruct",
                "v31_block_compare",
            )
        )
        for part in file.parts
    ):
        return False
    if file.suffix == ".npz":
        allowed = {
            (ROOT / entry["path"]).resolve() for entry in design["files"].values()
        }
        return file in allowed or (
            file.is_relative_to(Path(design.get("active_training_artifact", artifacts)))
            and ("basis" in file.parts or file.name.startswith("final_state"))
        )
    if file.name.startswith("index_e3_reference") or file.name == "reference_state.npz":
        return False
    return True
