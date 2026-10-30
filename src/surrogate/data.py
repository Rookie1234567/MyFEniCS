"""Fail-closed, hash-addressed FE sample import; synthetic data stay labelled."""
from __future__ import annotations

import math
import re

from .design import ANCHORS, OUTPUTS, digest, geometry_key, validate_design

CHECKS = {"propagation_mesh", "layer_z_mesh", "dtn_evanescent", "top_air_gap"}
FIXED_PHYSICS = {
    "lambda0_nm": 0.7, "incident_theta_deg": 89, "incident_phi_deg": 90,
    "polarization": "s", "degree": 6, "period_nm": [2.5, 2.5],
    "pillar_xy_nm": [0.85, 1.0], "substrate_nm": 0.5,
    "material_layers": ["Si", "SiGe", "Si", "SiGe", "Si", "SiO2"],
}


def _validate_physics(physics, thickness, materials_sha):
    expected = {**FIXED_PHYSICS, "thickness_nm": list(thickness), "materials_sha256": materials_sha}
    # Canonical JSON distinguishes true from 1, and carries all six geometry inputs.
    if digest(physics) != digest(expected):
        raise ValueError("frozen six-layer physical contract mismatch")
    geometry_key(physics["thickness_nm"])


def _comparison_contract(check, q):
    reference, candidate = check["reference_run"], check["candidate_run"]
    allowed = {"propagation_mesh": "y_subdivisions", "layer_z_mesh": "layer_subdivisions",
               "dtn_evanescent": "dtn_evanescent_orders", "top_air_gap": "top_gap_nm"}[check["kind"]]
    for run in (reference, candidate):
        _validate_physics(run["physics"], check["thickness_nm"], q["materials_sha256"])
        if run["source_sha256"] != q["source_sha256"] or run["data_kind"] != q["data_kind"]:
            raise ValueError("comparison source/data-kind mismatch")
        for key in ("generator_sha256", "config_sha256", "evidence_sha256", "physical_model_sha256"):
            _sha(run[key])
        _run_quality(run)
    if reference["generator_sha256"] != q["generator_sha256"]:
        raise ValueError("qualification baseline is not this generator")
    a, b = reference["numerical_configuration"], candidate["numerical_configuration"]
    keys = {"x_subdivisions", "y_subdivisions", "layer_subdivisions", "dtn_evanescent_orders", "top_gap_nm"}
    if set(a) != keys or set(b) != keys:
        raise ValueError("incomplete numerical configuration")
    for settings in (a, b):
        if any(type(settings[key]) is not int or settings[key] < 1
               for key in ("x_subdivisions", "y_subdivisions")):
            raise ValueError("invalid horizontal subdivision counts")
        layers, modes = settings["layer_subdivisions"], settings["dtn_evanescent_orders"]
        if len(layers) != 8 or any(type(n) is not int or n < 1 for n in layers):
            raise ValueError("eight positive layer subdivision counts required")
        if len(modes) != 2 or any(type(n) is not int or n < 0 for n in modes):
            raise ValueError("two nonnegative evanescent extension counts required")
        if _number(settings["top_gap_nm"], minimum=0) not in (0.5, 1.0):
            raise ValueError("unexpected top gap in qualification")
    if {key for key in keys if a[key] != b[key]} != {allowed}:
        raise ValueError("qualification changed something other than its declared numerical control")
    left = a[allowed] if isinstance(a[allowed], list) else [a[allowed]]
    right = b[allowed] if isinstance(b[allowed], list) else [b[allowed]]
    if len(left) != len(right) or any(_number(y, minimum=0) < _number(x, minimum=0) for x, y in zip(left, right)):
        raise ValueError("comparison is not an extension/refinement")
    for prefix, run in (("reference", reference), ("candidate", candidate)):
        if check[f"{prefix}_config_sha256"] != run["config_sha256"]:
            raise ValueError("comparison configuration SHA mismatch")
        if any(check[f"{prefix}_outputs"][name] != run["outputs"][name] for name in OUTPUTS):
            raise ValueError("comparison outputs not bound to qualified runs")
    if check["kind"] == "top_air_gap" and (a["top_gap_nm"], b["top_gap_nm"]) != (0.5, 1.0):
        raise ValueError("actual top gap values differ")


def _sha(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError("missing/invalid sha256")


def _number(value, *, minimum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("missing/nonfinite numeric measurement")
    if minimum is not None and value < minimum:
        raise ValueError("numeric measurement below allowed minimum")
    return float(value)


def validate_qualification(q, *, allow_synthetic=False):
    """Checks the compact evidence, not just its status; not an FE recomputation."""
    if q["schema"] != "sixlayer-qualification-v1":
        raise ValueError("unknown qualification schema")
    kind = q["data_kind"]
    if kind != "measured_fe" and not (allow_synthetic and kind == "synthetic_test"):
        raise ValueError("FE qualification required; synthetic cannot be promoted")
    for key in ("generator_sha256", "materials_sha256", "source_sha256"):
        _sha(q[key])
    checks = q["checks"]
    if len(checks) < 4 or {r["kind"] for r in checks} != CHECKS:
        raise ValueError("four required qualification comparison kinds")
    observed = {name: 0.0 for name in OUTPUTS}
    for check in checks:
        if geometry_key(check["thickness_nm"]) not in [geometry_key(a) for a in ANCHORS]:
            raise ValueError("qualification point is not A-D")
        for key in ("reference_config_sha256", "candidate_config_sha256", "evidence_sha256"):
            _sha(check[key])
        if check["reference_config_sha256"] == check["candidate_config_sha256"]:
            raise ValueError("qualification must compare distinct configurations")
        _comparison_contract(check, q)
        if check["kind"] == "top_air_gap":
            if check["gaps_nm"] != [0.5, 1.0] or check["bottom_reference_nm"] != -0.5:
                raise ValueError("top-gap/bottom-reference comparison changed")
        for name in OUTPUTS:
            delta = abs(_number(check["candidate_outputs"][name])
                        - _number(check["reference_outputs"][name]))
            if delta > 2e-4:
                raise ValueError(f"numerical stability failed: {check['kind']} {name} {delta}")
            observed[name] = max(observed[name], delta)
    # A repeat-noise estimate is distinct from refinement differences.
    repeat = q.get("repeat_noise_indicator")
    if repeat is not None:
        _sha(repeat["evidence_sha256"])
        for name in OUTPUTS:
            _number(repeat["max_absolute_difference"][name], minimum=0)
    return {"qualification_sha256": digest(q), "data_kind": kind,
            "checked_point_refinement_difference": observed,
            "repeat_noise_indicator": repeat,
            "scope": "only checked A-D/configurations; not a whole-domain error/noise bound"}


def validate_record(record, point, q, qualification_sha):
    if record["sample_id"] != point["sample_id"]:
        raise ValueError("sample ID mismatch")
    if geometry_key(record["thickness_nm"]) != geometry_key(point["thickness_nm"]):
        raise ValueError("sample geometry mismatch")
    if record["data_kind"] != q["data_kind"] or record["status"] != "completed":
        raise ValueError("incomplete/failed or mixed synthetic/measured sample")
    for key in ("generator_sha256", "materials_sha256", "source_sha256"):
        if record[key] != q[key]:
            raise ValueError(f"mixed data-generation version: {key}")
    if record["qualification_sha256"] != qualification_sha:
        raise ValueError("wrong numerical qualification")
    for key in ("input_sha256", "physical_model_sha256", "run_manifest_sha256",
                "evidence_sha256", "mesh_sha256", "dtn_modes_sha256"):
        _sha(record[key])
    _validate_physics(record["physics"], record["thickness_nm"], q["materials_sha256"])
    return _run_quality(record)


def _run_quality(record):
    if type(record["dofs"]) is not int or record["dofs"] < 1:
        raise ValueError("actual DOFs missing")
    if _number(record["full_true_residual"], minimum=0) > 1e-6:
        raise ValueError("full explicit residual failed")
    out = record["outputs"]
    for name in (*OUTPUTS, "R00_s", "R00_p", "A_balance", "A_volume"):
        _number(out[name])
    for name in (*OUTPUTS, "R00_s", "R00_p", "A_volume"):
        if out[name] < -1e-12:
            raise ValueError("negative power; do not silently clip")
    if abs(out["R00_total"] - out["R00_s"] - out["R00_p"]) > 1e-12:
        raise ValueError("R00 components do not sum")
    if out["R00_total"] > out["R_total"] + 1e-12:
        raise ValueError("zero order exceeds total reflection")
    if abs(out["R_total"] + out["T_total"] + out["A_volume"] - 1) > 1e-5:
        raise ValueError("volume-energy closure failed")
    if abs(out["A_balance"] - (1 - out["R_total"] - out["T_total"])) > 1e-12:
        raise ValueError("A_balance mismatch")
    resource = record["resources"]
    if _number(resource["task_swap_bytes"], minimum=0) != 0:
        raise ValueError("nonzero task swap")
    peak = _number(resource["process_tree_peak_bytes"], minimum=1)
    if peak > 10_000_000_000:
        raise ValueError("memory hard cap exceeded")
    wall = _number(resource["full_wall_seconds"], minimum=0)
    if wall <= 0:
        raise ValueError("invalid/missing full-pipeline wall time")
    stages = resource["stage_seconds"]
    if not stages:
        raise ValueError("stage costs missing")
    for seconds in stages.values():
        _number(seconds, minimum=0)
    _sha(resource["supervision_sha256"])
    if resource["measurement_scope"] != "simultaneous_process_tree_full_pipeline":
        raise ValueError("wrong peak-memory accounting scope")
    if type(resource["exit_code"]) is not int or resource["exit_code"] != 0 or resource["cleanup_complete"] is not True:
        raise ValueError("unclean/incomplete execution")
    for key in ("sampling_complete", "swap_samples_complete", "available_memory_gate_passed"):
        if resource[key] is not True:
            raise ValueError(f"resource evidence incomplete: {key}")
    if type(resource["sample_count"]) is not int or resource["sample_count"] < 1:
        raise ValueError("actual supervision samples missing")
    _number(resource["minimum_available_bytes"], minimum=1_073_741_824)
    return [out[name] for name in OUTPUTS]


def select_records(design, records, q, split, count, *, allow_synthetic=False):
    if type(count) is not int or count < 1:
        raise ValueError("positive exact integer sample count required")
    points = validate_design(design)
    qualification = validate_qualification(q, allow_synthetic=allow_synthetic)
    if split not in ("train", "dev", "blind"):
        raise ValueError("unknown split")
    if any(r["sample_id"] not in points or points[r["sample_id"]]["split"] != split for r in records):
        raise ValueError("wrong-split labels supplied; no silent filtering")
    by_id = {r["sample_id"]: r for r in records}
    if len(by_id) != len(records):
        raise ValueError("duplicate sample records")
    wanted = [p for p in design["points"] if p["split"] == split and p["order"] <= count]
    if len(wanted) != count or set(by_id) != {p["sample_id"] for p in wanted}:
        raise ValueError("exact contiguous prefix required; no deleted failures/interpolation")
    ordered = [by_id[p["sample_id"]] for p in wanted]
    y = [validate_record(r, p, q, qualification["qualification_sha256"])
         for r, p in zip(ordered, wanted)]
    return [r["thickness_nm"] for r in ordered], y, ordered, qualification
