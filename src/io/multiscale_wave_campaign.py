"""Explicit V32 profiles, isolated from previous immutable one-run inputs."""

import json

from src.io.input_loader import InputError
from src.io.neural_wave_campaign import ROOT, digest

DESIGN = ROOT / "input/task042extra_feinn_5nm/design_v32.json"
STAGES = {
    "v32_saved_support_audit": ("pure", 5400, "support_audit"),
    "v32_support_reference_bound": ("pure", 1800, "support_bound"),
    "v32_support_direction_witness": ("ml", 5400, "support_witness"),
    "v32_multiscale_wave_checks": ("ml", 7200, "multiscale_checks"),
    "v32_fixed_multiscale_wave": ("ml", 14400, "FIXED_MULTISCALE_WAVE_BLOCK"),
    "v32_learned_multiscale_wave": ("ml", 14400, "LEARNED_MULTISCALE_WAVE_BLOCK"),
    "v32_multiscale_reconstruct": ("fe", 7200, "multiscale_reconstruct"),
    "v32_multiscale_compare": ("pure", 3600, "multiscale_compare"),
    "v32_fixed_original_qr_checks": ("ml", 1800, "readout_repair_checks"),
    "v32_learned_original_qr_checks": ("ml", 1800, "readout_repair_checks"),
}
for route in ("fixed", "learned"):
    for node in (1, 2):
        STAGES[f"v32_{route}_validate_{node}"] = ("fe", 1800, "early_validate")


def load_multiscale(path, data, raw):
    if set(data) != {"schema_version", "neural_wave"} or data["schema_version"] != 3:
        raise InputError("V32 explicit schema3 required")
    item = data["neural_wave"]
    if set(item) - {"stage", "design_sha256", "native_target"} or not {
        "stage",
        "design_sha256",
    } <= set(item):
        raise InputError("unknown V32 keys / label path")
    if item["stage"] not in STAGES or digest(DESIGN) != item["design_sha256"]:
        raise InputError("V32 stage/design mismatch")
    design = json.loads(DESIGN.read_text())
    if design["campaign_version"] != 32 or not design["multiscale_support_policy"]:
        raise InputError("V32 policy required")
    if set(design["files"]) != {"native", "moments_q15", "moments_q30"}:
        raise InputError("training whitelist violated")
    target = item.get("native_target", 1e-8)
    if target not in (1e-8, 1e-10):
        raise InputError("original residual target changed")
    mode, seconds, role = STAGES[item["stage"]]
    import hashlib

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
        campaign_version=32,
        schema="neural-wave.one-run.v3",
    )
