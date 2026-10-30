"""Train/dev workflow and single-use, strategy-bound blind evaluation gate."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path

from .data import select_records, validate_qualification
from .design import digest, validate_design
from .models import cross_validate, evaluation_report, fit_model, predict_model


def read_json(path):
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


def save_new(path, value):
    """Never overwrite a frozen design/model/evaluation receipt."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def implementation_digest():
    return digest({p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in sorted(Path(__file__).parent.glob("*.py"))})


def fit_experiment(design, qualification, train_records, dev_records, *, strategy=None,
                   allow_synthetic=False):
    # There is intentionally no argument for blind data in the training interface.
    x, y, ordered, q = select_records(design, train_records, qualification, "train",
                                     len(train_records), allow_synthetic=allow_synthetic)
    dx, dy, dev, _ = select_records(design, dev_records, qualification, "dev",
                                    len(dev_records), allow_synthetic=allow_synthetic)
    if len(ordered) < 4:
        raise ValueError("A-D must all be available")
    model = fit_model(x, y, strategy)
    prediction = predict_model(model, dx)
    report = evaluation_report(model, dev, dy, prediction, q)
    report["split"] = "development; not independent final blind"
    report["six_dimensional_evidence"] = ("insufficient affine rank; diagnostic only" if model["linear_rank"] < 7
                                            else "full affine rank alone is not generalization evidence")
    report["cross_validation"] = cross_validate(x, y, strategy)
    return {"schema": "sixlayer-experiment-v1", "data_kind": q["data_kind"],
            "design_sha256": digest(design), "qualification_sha256": digest(qualification),
            "train_records_sha256": digest(ordered), "dev_records_sha256": digest(dev),
            "source_sha256": implementation_digest(), "model": model, "report": report,
            "train_count": len(ordered), "dev_count": len(dev), "blind_labels_read": False}


def freeze_strategy(experiment, design, qualification, *, reason, blind_count=None):
    validate_design(design)
    validate_qualification(qualification, allow_synthetic=experiment["data_kind"] == "synthetic_test")
    if experiment["source_sha256"] != implementation_digest():
        raise ValueError("implementation changed; refit before freeze")
    runtime = {name: metadata.version(distribution) for name, distribution in
               (("numpy", "numpy"), ("scipy", "scipy"), ("sklearn", "scikit-learn"))}
    if runtime != experiment["model"]["packages"]:
        raise ValueError("statistical runtime packages changed before blind-label access")
    if experiment["design_sha256"] != digest(design) or experiment["qualification_sha256"] != digest(qualification):
        raise ValueError("design/qualification changed")
    if experiment["blind_labels_read"] is not False or not experiment["report"]["cross_validation"]:
        raise ValueError("CV and unexposed blind labels required")
    if not isinstance(reason, str) or len(reason.strip()) < 20:
        raise ValueError("record an actual train-CV/dev/variation-based freeze decision")
    count = design["planned_counts"]["blind"] if blind_count is None else blind_count
    if type(count) is not int or not 1 <= count <= design["planned_counts"]["blind"]:
        raise ValueError("freeze blind count before seeing any labels")
    points = [p for p in design["points"] if p["split"] == "blind"][:count]
    return {"schema": "sixlayer-strategy-freeze-v1", "experiment_sha256": digest(experiment),
            "source_sha256": implementation_digest(), "design_sha256": digest(design),
            "qualification_sha256": digest(qualification), "blind_count": count,
            "blind_geometry_sha256": digest(points), "decision_reason": reason,
            "frozen_utc": datetime.now(timezone.utc).isoformat(),
            "data_kind": experiment["data_kind"],
            "scope": "small pilot on fixed unseen points; no whole-six-dimensional-domain guarantee",
            "after_blind_change_rule": "any tuning after label exposure invalidates independent-final interpretation"}


def evaluate_blind(experiment, design, qualification, freeze, blind_path):
    """Validate everything BEFORE opening blind labels; persist exposure first.

    This guards this workflow, not a malicious caller reading the file elsewhere.
    Keep blind labels outside train/dev directories and do not precompute reports.
    """
    expected = freeze_strategy(experiment, design, qualification,
                               reason=freeze["decision_reason"], blind_count=freeze["blind_count"])
    for key in expected:
        if key != "frozen_utc" and freeze.get(key) != expected[key]:
            raise ValueError(f"invalid freeze binding: {key}")
    # Canonical path, not caller-selected: changing output/freeze filenames cannot
    # accidentally reopen the same label file. This is not a hostile-user sandbox.
    ledger_path = str(Path(blind_path).resolve()) + ".evaluation_started.json"
    ledger = {"status": "evaluation_started", "freeze_sha256": digest(freeze),
              "data_kind": experiment["data_kind"], "started_utc": datetime.now(timezone.utc).isoformat(),
              "independent_final_available_for_reuse": False}
    # Exclusive creation prevents concurrent/repeated use of this same blind gate.
    save_new(ledger_path, ledger)
    try:
        rows = read_json(blind_path)
        x, y, ordered, q = select_records(design, rows, qualification, "blind", freeze["blind_count"],
                                           allow_synthetic=experiment["data_kind"] == "synthetic_test")
        predictions = predict_model(experiment["model"], x)
        report = evaluation_report(experiment["model"], ordered, y, predictions, q)
        report.update({"split": "final_blind", "n": len(rows), "freeze_sha256": digest(freeze),
                       "blind_records_sha256": digest(ordered), "data_kind": experiment["data_kind"],
                       "independent_interpretation": "valid only if no prior external access and no later tuning"})
        # Append-only receipt beside the started ledger; a failed write stays exposed.
        save_new(str(ledger_path) + ".completed.json", report)
        return report
    except Exception as exc:
        try:
            save_new(str(ledger_path) + ".failed.json", {
                **ledger, "status": "failed_after_evaluation_started", "error": repr(exc),
                "rule": "preserve exposure; diagnostic retry cannot silently regain final-blind status"})
        except Exception as receipt_error:
            exc.add_note(f"failure receipt also failed; permanent started ledger retained: {receipt_error!r}")
        raise


def learning_curve(experiments):
    """Compact development curve, retaining count and all raw-unit metrics."""
    if not experiments:
        return []
    reference = experiments[0]
    if any(e["dev_records_sha256"] != reference["dev_records_sha256"] or
           e["qualification_sha256"] != reference["qualification_sha256"] for e in experiments):
        raise ValueError("learning curve requires the SAME development set and generator qualification")
    ordered = sorted(experiments, key=lambda e: e["train_count"])
    for previous, current in zip(ordered, ordered[1:]):
        count = previous["train_count"]
        if current["model"]["x_train_nm"][:count] != previous["model"]["x_train_nm"]:
            raise ValueError("training geometries are not nested")
        if current["model"]["y_train_raw"][:count] != previous["model"]["y_train_raw"]:
            raise ValueError("earlier training labels changed")
        if current["model"]["strategy"] != previous["model"]["strategy"]:
            raise ValueError("changed strategies need a labelled model-comparison report, not this learning curve")
    return [{"train_count": e["train_count"], "dev_count": e["dev_count"],
             "experiment_sha256": digest(e), "outputs": e["report"]["outputs"]}
            for e in ordered]
