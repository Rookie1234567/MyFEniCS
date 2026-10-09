"""V35 fixed-space audit identity, without a nonlinear/pilot entry point."""

import json
from pathlib import Path

from src.io.input_loader import InputError
from src.io.neural_wave_campaign import ROOT, digest

DESIGN = ROOT / "input/task042extra_feinn_5nm/design_v35.json"
STAGES = {
    "v35_space_audit_checks": ("pure", 900, "space_checks"),
    "v35_unlabelled_readout_audit": ("ml", 3000, "space_unlabelled"),
    "v35_labelled_field_oracle": ("ml", 7200, "space_oracle"),
    "v35_space_decision_compare": ("fe", 3600, "space_compare"),
}
POLICY = dict(
    reference_used_for_coefficient_fit=True,
    reference_used_for_training=True,
    pde_only_solve=False,
    production_initialization_allowed=False,
    pde_only_solver_qualified=False,
    official_candidate_results=False,
    scope="FROZEN_NEURAL_SPACE_ORACLE_DIAGNOSTIC",
)


def require_oracle_policy(value):
    """Saved consumers reject altered flags, including truth-like strings/ints."""
    if any(
        type(value.get(k)) is not type(v) or value.get(k) != v
        for k, v in POLICY.items()
    ):
        raise InputError("ORACLE_LABEL_POLICY_DAMAGED")
    return True


def field_policy(name):
    if name.endswith(("_ORACLE", "_ORACLE_PRODUCER")):
        return dict(POLICY)
    return dict(
        reference_used_for_training=False,
        reference_used_for_coefficient_fit=False,
        pde_only_solve=True,
        production_initialization_allowed=False,
        pde_only_solver_qualified=False,
        official_candidate_results=False,
        scope="FROZEN_NEURAL_SPACE_UNLABELLED_READOUT",
    )


def load_space(path, data, raw):
    if set(data) != {"schema_version", "neural_wave"} or data["schema_version"] != 6:
        raise InputError("V35_EXPLICIT_AUDIT_SCHEMA_REQUIRED")
    item = data["neural_wave"]
    if set(item) != {"stage", "design_sha256"} or item["stage"] not in STAGES:
        raise InputError("V35_NO_TRAINING_OR_LABEL_PATH_INPUT")
    if digest(DESIGN) != item["design_sha256"]:
        raise InputError("V35_FROZEN_DESIGN_CHANGED")
    design = json.loads(DESIGN.read_text())
    if (
        design["campaign_version"] != 35
        or design["columns"] != 1377
        or design["rcond"] != 1e-12
    ):
        raise InputError("V35_FIXED_SPACE_OR_CUTOFF_CHANGED")
    mode, seconds, role = STAGES[item["stage"]]
    import hashlib

    return dict(
        stage=item["stage"],
        mode=mode,
        max_seconds=seconds,
        role=role,
        input=str(Path(path).relative_to(ROOT)),
        input_sha256=hashlib.sha256(raw).hexdigest(),
        design_sha256=item["design_sha256"],
        campaign_version=35,
        case="M5",
        schema="neural-wave.space-audit.one-run.v1",
    )


def unlabelled_open_allowed(path, design, artifact):
    try:
        path = Path(path).resolve()
    except TypeError:
        return True
    if path.name == "reference_state.npz" or path.name.startswith("index_e3_reference"):
        return False
    root = ROOT / "benchmarks/artifacts/task42extra"
    if not path.is_relative_to(root):
        return True
    allowed = {(ROOT / e["path"]).resolve() for e in design["files"].values()}
    allowed |= {(ROOT / e["path"]).resolve() for e in design["unlabelled_bound_files"]}
    return path in allowed or path.is_relative_to(Path(artifact).resolve())
