"""V36 explicit audit-only stages; historical V35 inputs remain unchanged."""

import hashlib
import json
from pathlib import Path

from src.io.input_loader import InputError
from src.io.neural_wave_campaign import ROOT, digest

DESIGN = ROOT / "input/task042extra_feinn_5nm/design_v36.json"
STAGES = {
    "v36_oracle_kernel_checks": ("pure", 1200, "blocked_checks"),
    "v36_learned_space_oracle": ("ml", 5400, "blocked_oracle"),
    "v36_learned_oracle_verify": ("fe", 1800, "blocked_verify"),
    "v36_control_space_oracle": ("ml", 5400, "blocked_oracle"),
    "v36_control_oracle_verify": ("fe", 1800, "blocked_verify"),
    "v36_neural_route_decision": ("pure", 900, "blocked_decision"),
}


def load_blocked(path, data, raw):
    if set(data) != {"schema_version", "neural_wave"} or data["schema_version"] != 7:
        raise InputError("V36_EXPLICIT_BLOCKED_ORACLE_SCHEMA_REQUIRED")
    item = data["neural_wave"]
    if set(item) != {"stage", "design_sha256"} or item["stage"] not in STAGES:
        raise InputError("V36_NO_TRAINING_OR_NEW_SPACE_INPUT")
    if digest(DESIGN) != item["design_sha256"]:
        raise InputError("V36_FROZEN_DESIGN_CHANGED")
    design = json.loads(DESIGN.read_text())
    if (
        design["campaign_version"] != 36
        or design["columns"] != 1377
        or design["rcond"] != 1e-12
        or design["G_panel"] != 32
    ):
        raise InputError("V36_FIXED_SPACE_OR_NUMERICAL_CONTRACT_CHANGED")
    mode, seconds, role = STAGES[item["stage"]]
    return dict(
        stage=item["stage"],
        mode=mode,
        max_seconds=seconds,
        role=role,
        input=str(Path(path).relative_to(ROOT)),
        input_sha256=hashlib.sha256(raw).hexdigest(),
        design_sha256=item["design_sha256"],
        campaign_version=36,
        case="M5",
        schema="neural-wave.blocked-oracle.one-run.v1",
    )
