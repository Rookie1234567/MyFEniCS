"""Explicit V33 contract, isolated input identity and training whitelist."""

import hashlib
import json

from src.io.input_loader import InputError
from src.io.neural_wave_campaign import ROOT, digest

DESIGN = ROOT / "input/task042extra_feinn_5nm/design_v33.json"
STAGES = {
    "v33_backfit_anchor_checks": ("ml", 3600, "backfit_anchor_checks"),
    "v33_backfit_math_checks": ("ml", 7200, "backfit_math_checks"),
    "v33_deterministic_backfit": ("ml", 10800, "DETERMINISTIC_WAVE_BACKFIT"),
    "v33_learned_varpro_backfit": ("ml", 10800, "LEARNED_VARPRO_BACKFIT"),
    "v33_backfit_reconstruct": ("fe", 3600, "backfit_reconstruct"),
    "v33_backfit_compare": ("pure", 3600, "backfit_compare"),
    "v33_0p7_transfer_prepare": ("fe", 3600, "backfit_transfer_prepare"),
    "v33_0p7_transfer_backfit": ("ml", 3600, "backfit_transfer"),
    "v33_0p7_transfer_compare": ("fe", 3600, "backfit_transfer_compare"),
}
for route in ("deterministic", "learned"):
    for node in (1, 2):
        STAGES[f"v33_{route}_validate_{node}"] = ("fe", 1800, "backfit_early_validate")


def load_backfit(path, data, raw):
    if set(data) != {"schema_version", "neural_wave"} or data["schema_version"] != 4:
        raise InputError("V33 explicit schema4 required")
    item = data["neural_wave"]
    if set(item) - {"stage", "design_sha256", "native_target"} or not {
        "stage",
        "design_sha256",
    } <= set(item):
        raise InputError("unknown V33 keys / reference label path")
    if item["stage"] not in STAGES or digest(DESIGN) != item["design_sha256"]:
        raise InputError("V33 stage/design mismatch")
    design = json.loads(DESIGN.read_text())
    if design["campaign_version"] != 33 or design["anchor"]["columns"] != 1377:
        raise InputError("V33 fixed anchor identity required")
    if set(design["files"]) != {"native", "moments_q15", "moments_q30"}:
        raise InputError("V33 training whitelist violated")
    target = item.get("native_target", 1e-8)
    if target not in (1e-8, 1e-10):
        raise InputError("original residual target changed")
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
        campaign_version=33,
        schema="neural-wave.one-run.v4",
    )


def training_open_allowed(path, design):
    from pathlib import Path

    try:
        file = Path(path).resolve()
    except TypeError:
        return True
    base = ROOT / "benchmarks/artifacts/task42extra"
    if file.name.startswith("index_e3_reference") or file.name == "reference_state.npz":
        return False
    if file.suffix in (".pt", ".pth"):
        return False
    if file.is_relative_to(base):
        allowed = {(ROOT / e["path"]).resolve() for e in design["files"].values()}
        allowed |= {
            (ROOT / e["path"]).resolve() for e in design["anchor"]["bound_files"]
        }
        allowed |= {
            base / "v33" / s / "result.json"
            for s in ("v33_backfit_anchor_checks", "v33_backfit_math_checks")
        }
        active = Path(design["active_training_artifact"]).resolve()
        return file in allowed or file.is_relative_to(active)
    return True
