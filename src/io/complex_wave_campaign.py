"""Opt-in V34 identity; unlabelled oscillation/decay input firewall."""

import hashlib
import json
from pathlib import Path

from src.io.input_loader import InputError
from src.io.neural_wave_campaign import ROOT, digest

DESIGN = ROOT / "input/task042extra_feinn_5nm/design_v34.json"
STAGES = {
    "v34_complex_wave_checks": ("ml", 7200, "complex_wave_checks"),
    "v34_complex_wave_calibration": ("fe", 1800, "complex_wave_calibration"),
    "v34_deterministic_complex_backfit": (
        "ml",
        14400,
        "DETERMINISTIC_COMPLEX_WAVE_BACKFIT",
    ),
    "v34_learned_complex_backfit": ("ml", 14400, "LEARNED_COMPLEX_WAVE_BACKFIT"),
    "v34_complex_reconstruct": ("fe", 5400, "complex_reconstruct"),
    "v34_complex_compare": ("pure", 1800, "complex_compare"),
    "v34_0p7_complex_prepare": ("fe", 3600, "complex_pilot_prepare"),
    "v34_0p7_complex_solve": ("ml", 10800, "complex_pilot_solve"),
    "v34_0p7_complex_compare": ("fe", 3600, "complex_pilot_compare"),
}
for route in ("deterministic", "learned"):
    for node in (1, 2):
        STAGES[f"v34_{route}_validate_{node}"] = ("fe", 1800, "complex_early_validate")


def load_complex(path, data, raw):
    if set(data) != {"schema_version", "neural_wave"} or data["schema_version"] != 5:
        raise InputError("explicit V34 schema5 required")
    item = data["neural_wave"]
    if set(item) - {"stage", "design_sha256", "native_target"} or not {
        "stage",
        "design_sha256",
    } <= set(item):
        raise InputError("V34 unknown field / label input rejected")
    if item["stage"] not in STAGES or digest(DESIGN) != item["design_sha256"]:
        raise InputError("V34 stage/frozen design mismatch")
    design = json.loads(DESIGN.read_text())
    if (
        design["campaign_version"] != 34
        or design["anchor"]["columns"] != 1377
        or design["anchor"]["boundary_sha256"]
        != "737dd067f2cc3ebe021f3c7f445992c87d993e562213c62cc7a40b148a33501e"
        or design["decay"]["representation"] != "oscillation+decay.v1"
    ):
        raise InputError("V34 sole fixed anchor / explicit real decay required")
    if set(design["files"]) != {"native", "moments_q15", "moments_q30"}:
        raise InputError("V34 training file whitelist violated")
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
        case="reduced_0p7" if "0p7" in item["stage"] else "M5",
        campaign_version=34,
        schema="neural-wave.one-run.v5",
    )


def training_open_allowed(path, design, *, qualification=False):
    try:
        file = Path(path).resolve()
    except TypeError:
        return True
    if (
        file.name.startswith("index_e3_reference")
        or file.name == "reference_state.npz"
        or file.suffix in (".pt", ".pth")
    ):
        return False
    base = ROOT / "benchmarks/artifacts/task42extra"
    if file.is_relative_to(base):
        allowed = {(ROOT / e["path"]).resolve() for e in design["files"].values()}
        allowed |= {
            (ROOT / e["path"]).resolve() for e in design["anchor"]["bound_files"]
        }
        allowed |= {
            base / "v34" / s / "result.json"
            for s in ("v34_complex_wave_checks", "v34_complex_wave_calibration")
        }
        if qualification:
            allowed.add((ROOT / design["qualification_q60"]["path"]).resolve())
        active = Path(design["active_training_artifact"]).resolve()
        return file in allowed or file.is_relative_to(active)
    return True
