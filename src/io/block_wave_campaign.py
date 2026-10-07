"""V31 opt-in contracts; old V30 inputs and mathematical defaults stay intact."""

import hashlib
import json
from pathlib import Path

from src.io.input_loader import InputError

ROOT = Path(__file__).resolve().parents[2]
DESIGN = ROOT / "input/task042extra_feinn_5nm/design_v31.json"
STAGES = {
    "v31_saved_field_audit": ("fe", 10800, "saved_field_audit"),
    "v31_saved_field_check": ("pure", 1800, "saved_field_check"),
    "v31_reconstruction_stability": ("ml", 7200, "reconstruction_stability"),
    "v31_roundoff_witness": ("pure", 900, "roundoff_witness"),
    "v31_block_wave_checks": ("ml", 7200, "block_checks"),
    "v31_fixed_block_wave": ("ml", 21600, "FIXED_WAVE_BLOCK_GREEDY"),
    "v31_learned_block_wave": ("ml", 21600, "LEARNED_WAVE_BLOCK_GREEDY"),
    "v31_block_reconstruct": ("fe", 10800, "block_reconstruct"),
    "v31_block_compare": ("pure", 3600, "block_compare"),
}


def load_block_wave(path, data, raw):
    if set(data) != {"schema_version", "neural_wave"} or data["schema_version"] != 2:
        raise InputError("V31 requires its own explicit schema2")
    item = data["neural_wave"]
    if set(item) - {"stage", "design_sha256", "native_target"} or not {
        "stage",
        "design_sha256",
    } <= set(item):
        raise InputError("V31 unknown keys or teacher path")
    if (
        item["stage"] not in STAGES
        or hashlib.sha256(DESIGN.read_bytes()).hexdigest() != item["design_sha256"]
    ):
        raise InputError("unknown V31 stage or frozen design changed")
    design = json.loads(DESIGN.read_text())
    if (
        design["schema"] != "neural-wave.unlabelled-design.v2"
        or design["campaign_version"] != 31
    ):
        raise InputError("V31 design/profile mismatch")
    if set(design["files"]) != {"native", "moments_q15", "moments_q30"}:
        raise InputError("training whitelist excludes labels and inverses")
    target = item.get("native_target", design["strategy"]["native_target"])
    if target not in (1e-8, 1e-10):
        raise InputError("unsupported original residual target")
    mode, seconds, role = STAGES[item["stage"]]
    return dict(
        stage=item["stage"],
        mode=mode,
        role=role,
        max_seconds=seconds,
        input=str(path.relative_to(ROOT)),
        input_sha256=hashlib.sha256(raw).hexdigest(),
        design_sha256=item["design_sha256"],
        native_target=target,
        case="M5",
        campaign_version=31,
        schema="neural-wave.one-run.v2",
    )
