"""One V39 continuation window; explicit mapping and hash-bound parents."""

import hashlib
import json
from pathlib import Path
from src.io.input_loader import InputError
from src.io.neural_wave_campaign import ROOT, digest

DESIGN = ROOT / "input/task042extra_feinn_5nm/design_v39.json"
STAGES = {
    "v39_ftt_factored_checks": ("ml", 5400, "ftt_factored_checks", None, None),
    "v39_ftt_factored_benchmark": ("ml", 3600, "ftt_factored_benchmark", None, None),
    "v39_fttnn_native_continue": ("ml", 7200, "ftt_train", "fttnn", "native_euc"),
    "v39_chebtt_native_continue": ("ml", 7200, "ftt_train", "chebtt", "native_euc"),
    "v39_ftt_independent_compare": (
        "pure",
        3600,
        "ftt_independent_compare",
        None,
        "native_euc",
    ),
    "v39_fttnn_fit_continue": ("ml", 1800, "ftt_train", "fttnn", "reference_fit_G"),
    "v39_chebtt_fit_continue": ("ml", 1800, "ftt_train", "chebtt", "reference_fit_G"),
    "v39_ftt_fit_compare": (
        "pure",
        3600,
        "ftt_independent_compare",
        None,
        "reference_fit_G",
    ),
}


def load_structure(path, data, raw):
    if set(data) != {"schema_version", "neural_wave"} or data["schema_version"] != 9:
        raise InputError("FTT_STRUCTURE_EXPLICIT_SCHEMA_REQUIRED")
    item = data["neural_wave"]
    if set(item) != {"stage", "design_sha256"} or item["stage"] not in STAGES:
        raise InputError("FTT_STRUCTURE_UNKNOWN_STAGE_OR_LABEL")
    if item["design_sha256"] != digest(DESIGN):
        raise InputError("FTT_STRUCTURE_FROZEN_DESIGN_CHANGED")
    d = json.loads(DESIGN.read_text())
    if (
        d["ranks"] != [1, 8, 8, 1]
        or d["seed"] != 4213701
        or d["mapping_kind"] != "factored_exact_moments"
    ):
        raise InputError("FTT_STRUCTURE_FIXED_MODEL_CHANGED")
    mode, seconds, role, kind, metric = STAGES[item["stage"]]
    return dict(
        stage=item["stage"],
        mode=mode,
        max_seconds=seconds,
        role=role,
        model_kind=kind,
        metric_kind=metric,
        mapping_kind=d["mapping_kind"],
        input=str(Path(path).resolve().relative_to(ROOT)),
        input_sha256=hashlib.sha256(raw).hexdigest(),
        design_sha256=item["design_sha256"],
        campaign_version=39,
        case="M5",
        schema="ftt.structure-one-run.v1",
    )


def parent(design, kind, fit):
    entry = design["parents"][kind + ("_fit" if fit else "_native")]
    for key in ("result", "checkpoint"):
        f = (ROOT / entry[key]["path"]).resolve()
        if (
            not f.is_relative_to(ROOT / "benchmarks/artifacts/task42extra/v38")
            or digest(f) != entry[key]["sha256"]
        ):
            raise ValueError("FTT_STRUCTURE_PARENT_SCOPE_OR_HASH:" + key)
    candidate = json.loads((ROOT / entry["result"]["path"]).read_text())
    if (
        candidate["source_sha"] != entry["source_sha"]
        or candidate["counts"] != entry["counts"]
    ):
        raise ValueError("FTT_STRUCTURE_PARENT_IDENTITY_MISMATCH")
    return entry, candidate
