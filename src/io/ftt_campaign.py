"""Explicit new FTT schema, isolated from wave models and metric heuristics."""

import hashlib
import json
from pathlib import Path
from src.io.input_loader import InputError
from src.io.neural_wave_campaign import ROOT, digest

DESIGN = ROOT / "input/task042extra_feinn_5nm/design_v38.json"
STAGES = {
    "v38_ftt_checks": ("ml", 5400, "ftt_checks", None, None),
    "v38_fttnn_native": ("ml", 3600, "ftt_train", "fttnn", "native_euc"),
    "v38_chebtt_native": ("ml", 3600, "ftt_train", "chebtt", "native_euc"),
    "v38_ftt_reconstruct": ("ml", 1800, "ftt_reconstruct", None, "native_euc"),
    "v38_ftt_compare": ("fe", 1800, "ftt_compare", None, "native_euc"),
    "v38_fttnn_reference_fit": ("ml", 1800, "ftt_train", "fttnn", "reference_fit_G"),
    "v38_chebtt_reference_fit": ("ml", 1800, "ftt_train", "chebtt", "reference_fit_G"),
    "v38_ftt_fit_compare": ("pure", 2400, "ftt_fit_compare", None, "reference_fit_G"),
}


def load_ftt(path, data, raw):
    if set(data) != {"schema_version", "neural_wave"} or data["schema_version"] != 8:
        raise InputError("FTT_EXPLICIT_SCHEMA_REQUIRED")
    item = data["neural_wave"]
    if set(item) != {"stage", "design_sha256"} or item["stage"] not in STAGES:
        raise InputError("FTT_UNKNOWN_STAGE_OR_TRAINING_LABEL")
    if item["design_sha256"] != digest(DESIGN):
        raise InputError("FTT_FROZEN_DESIGN_CHANGED")
    design = json.loads(DESIGN.read_text())
    if (
        design["ranks"] != [1, 8, 8, 1]
        or design["seed"] != 4213701
        or design["point_batch"] != 512
    ):
        raise InputError("FTT_FIXED_MODEL_CONTRACT_CHANGED")
    mode, seconds, role, kind, metric = STAGES[item["stage"]]
    return dict(
        stage=item["stage"],
        mode=mode,
        max_seconds=seconds,
        role=role,
        model_kind=kind,
        metric_kind=metric,
        input=str(Path(path).resolve().relative_to(ROOT)),
        input_sha256=hashlib.sha256(raw).hexdigest(),
        design_sha256=item["design_sha256"],
        campaign_version=38,
        case="M5",
        schema="ftt.one-run.v1",
    )


def usage_flags(spec):
    """The verifier inherits the fitted models' permanent label exposure."""
    labelled = (
        spec.get("metric_kind") == "reference_fit_G"
        or spec["role"] == "ftt_fit_compare"
    )
    return dict(
        reference_used_for_training=labelled,
        features_reference_exposed=labelled,
        pde_only_solve=spec["role"] == "ftt_train" and not labelled,
        production_initialization_allowed=False,
        official_candidate_results=False,
        pde_only_solver_qualified=False,
    )


def load_files(design, labelled=False):
    allowed = {"native", "moments_q30", "moments_q60"}
    if set(design["files"]) != allowed:
        raise ValueError("FTT_UNLABELLED_FILE_WHITELIST_FAILED")
    entries = dict(design["files"])
    if labelled:
        entries.update(reference=design["reference"], gram=design["gram"])
    for key, entry in entries.items():
        path = (ROOT / entry["path"]).resolve()
        if (
            not path.is_relative_to(ROOT / "benchmarks/artifacts/task42extra")
            or digest(path) != entry["sha256"]
        ):
            raise ValueError("FTT_INPUT_HASH_OR_SCOPE_FAILED:" + key)
    return {key: ROOT / entry["path"] for key, entry in entries.items()}
