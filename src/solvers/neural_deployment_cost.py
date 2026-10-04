"""Pure cold-N=1 cost consumption; no model, matrix or solver imports.

An ordering of known lower bounds is not an ordering of complete costs. Only
identical, evidenced, once-consumed unknown terms may cancel for an ordering;
they never cancel from the denominator of a percentage improvement.
"""

import hashlib
import json
import math
import re
from pathlib import Path
from statistics import mean

PHASES = (
    "data_teacher",
    "setup",
    "training",
    "loading",
    "common_prefix",
    "inference",
    "post_cleanup",
    "audit_io",
    "failures",
)
BOUNDARY = "cold_N1_complete_lifecycle"


def file_receipt(path, *, source):
    path = Path(path)
    return {
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "source_sha": source,
    }


def _validate_term(term):
    if term["unit"] != "s" or term["phase"] not in PHASES:
        raise ValueError("cost unit/phase inventory")
    if term["boundary"] != BOUNDARY or not term["consumed_object"]:
        raise ValueError("cold boundary/actual consumption")
    evidence = term["evidence"]
    if not re.fullmatch(r"[0-9a-f]{64}", evidence["sha256"]) or not re.fullmatch(
        r"[0-9a-f]{40}", evidence["source_sha"]
    ):
        raise ValueError("cost source/evidence hash")
    status, value = term["classification"], term["value"]
    if status not in ("measured", "derived", "unknown"):
        raise ValueError("cost classification")
    if status == "unknown":
        if value is not None:
            raise ValueError("unknown cost must not be zero-filled")
    elif (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
    ):
        raise ValueError("nonfinite/negative cost")


def summarize(route):
    terms = route["terms"]
    for term in terms:
        _validate_term(term)
    ids = [t["consumption_id"] for t in terms]
    if len(set(ids)) != len(ids) or {t["phase"] for t in terms} != set(PHASES):
        raise ValueError("duplicate consumption or incomplete phase inventory")
    if route["boundary"] != BOUNDARY:
        raise ValueError("inconsistent cold N=1 boundary")
    unknown = [t for t in terms if t["classification"] == "unknown"]
    return {
        "known_lower_seconds": math.fsum(
            t["value"] for t in terms if t["value"] is not None
        ),
        "complete_seconds": None if unknown else math.fsum(t["value"] for t in terms),
        "unknown_terms": unknown,
        "boundary": BOUNDARY,
    }


def _unknown_signature(term):
    proof = term.get("common_unknown_proof")
    if (
        not proof
        or proof.get("same_consumption_count") != 1
        or not proof.get("same_object_and_lifetime")
    ):
        return None
    required = ("object_hash", "source_sha", "evidence_sha256", "lifetime", "boundary")
    if any(not proof.get(k) for k in required) or proof["boundary"] != BOUNDARY:
        return None
    if any(
        len(proof[k]) != n
        for k, n in (("object_hash", 64), ("source_sha", 40), ("evidence_sha256", 64))
    ):
        return None
    # A proof also binds the actual term, rather than an arbitrary shared label.
    if (
        proof["object_hash"] != term["consumed_object"]
        or proof["source_sha"] != term["evidence"]["source_sha"]
        or proof["evidence_sha256"] != term["evidence"]["sha256"]
    ):
        return None
    return json.dumps({k: proof[k] for k in required}, sort_keys=True)


def select_cold_n1(routes, correctness, *, required=8):
    eligible = {
        name: value
        for name, value in routes.items()
        if correctness.get(name) == required
    }
    if not eligible:
        return {
            "status": "NO_ALL_EIGHT_CORRECT_ROUTE",
            "selected": None,
            "eligible": [],
            "NN20": "NOT_QUALIFIED",
        }
    summaries = {name: summarize(route) for name, route in eligible.items()}
    signatures = []
    for row in summaries.values():
        unknown = row["unknown_terms"]
        keys = [_unknown_signature(t) for t in unknown]
        if any(k is None for k in keys):
            return {
                "status": "COST_ORDER_UNRESOLVED",
                "selected": None,
                "eligible": sorted(eligible),
                "summaries": summaries,
                "reason": "unknown cost lacks same-source/object/lifetime cancellation proof",
                "NN20": "NOT_QUALIFIED",
            }
        signatures.append(sorted(keys))
    if any(s != signatures[0] for s in signatures):
        return {
            "status": "COST_ORDER_UNRESOLVED",
            "selected": None,
            "eligible": sorted(eligible),
            "summaries": summaries,
            "reason": "unmatched unknown consumption",
            "NN20": "NOT_QUALIFIED",
        }
    selected = min(
        summaries, key=lambda name: (summaries[name]["known_lower_seconds"], name)
    )
    return {
        "status": "COMMON_UNKNOWN_CANCELLED_FOR_ORDER_ONLY"
        if signatures[0]
        else "COMPLETE_COST_ORDER",
        "selected": selected,
        "eligible": sorted(eligible),
        "summaries": summaries,
        "NN20": "NOT_QUALIFIED"
        if signatures[0]
        else "REQUIRES_SEPARATE_CORRECTNESS_AND_RESOURCE_CHECK",
    }


def twenty_percent_time(baseline, neural, *, same_correctness, measured_comparable):
    b, n = summarize(baseline), summarize(neural)
    if not same_correctness:
        return {"status": "NO_MATCHED_CORRECTNESS", "qualified": False}
    if b["complete_seconds"] is None or n["complete_seconds"] is None:
        return {"status": "UNKNOWN_FULL_COST_DENOMINATOR", "qualified": False}
    if not measured_comparable or b["complete_seconds"] <= 0:
        return {"status": "NO_COMPLETE_COMPARABLE_MEASUREMENT", "qualified": False}
    ratio = n["complete_seconds"] / b["complete_seconds"]
    return {
        "status": "TIME_NECESSARY_CONDITION_ONLY",
        "ratio": ratio,
        "time_20_percent": ratio <= 0.8,
        "qualified": False,
        "reason": "simultaneous memory and full physical qualification remain separate",
    }


def necessary_time_condition(*, common, unavoidable, variable, overhead, fraction):
    values = (common, unavoidable, variable, overhead, fraction)
    if any(v is None for v in values):
        return {
            "status": "UNKNOWN",
            "minimum_variable_seconds": None,
            "NN20": "NOT_QUALIFIED",
        }
    if any(not math.isfinite(v) or v < 0 for v in values) or fraction > 1:
        raise ValueError("invalid time necessary-condition inputs")
    baseline = common + unavoidable + variable
    saved = fraction * variable - overhead
    return {
        "status": "DERIVED_NECESSARY_CONDITION_ONLY",
        "baseline_seconds": baseline,
        "maximum_actual_saving_seconds": saved,
        "minimum_variable_seconds": 0.2 * baseline + overhead,
        "time_condition": saved >= 0.2 * baseline,
        "NN20": "NOT_QUALIFIED",
    }


def frozen_v45_costs(report, comparison, *, evidence, inherited_evidence):
    """Normalize the published frozen scalar scenario without rerunning it.

    Online mean is partitioned into prefix/inference/remaining cleanup. Nested
    CSR load is not charged again; the inclusive load/start/IO term owns it.
    CL44 inherits only preparation and training, never the old online N1.
    """
    out = {}
    for name, r in report["route_costs"].items():
        rows = [x for x in comparison["rows"] if x["route"] == name]
        if len(rows) != 8 or {x["sample"] for x in rows} != set(range(8)):
            raise ValueError("frozen eight-case cost inventory")
        prefix = mean(x["common_prefix_seconds"] for x in rows)
        inference = mean(x["inference_seconds"] for x in rows)
        online = r["per_rhs_observed_online_mean"]
        values = {
            "data_teacher": r["prefix_train_validation_measured_seconds"]
            + r["DATA_overhead_allocated_to_training_seconds"],
            "setup": r["one_time_SETUP_seconds"]
            + r["one_time_gradient_qualification_seconds"],
            "training": r["selected_model_train_wall_measured_lower_seconds"],
            "loading": r["eval_load_start_IO_overhead_charged_once_seconds"],
            "common_prefix": prefix,
            "inference": inference,
            "post_cleanup": online - prefix - inference,
            "audit_io": r["full_CHECK_group_allocation_charged_once_seconds"],
            "failures": 0.0,
        }
        terms = [
            {
                "phase": phase,
                "value": value,
                "unit": "s",
                "classification": "derived",
                "boundary": BOUNDARY,
                "consumption_id": name + ":current:" + phase,
                "consumed_object": name + ":frozen_current_" + phase,
                "evidence": evidence,
                "semantics": "published conservative single-candidate allocation; not measured complete cold N1",
            }
            for phase, value in values.items()
        ]
        if name == "CL44":
            old = r["inherited_V44_CL44_preparation_training_cost"]
            inherited = {
                "data_teacher": old["prefix_train_validation_measured_seconds"]
                + old["DATA_overhead_allocated_to_training_seconds"],
                "setup": old["one_time_SETUP_seconds"]
                + old["one_time_gradient_qualification_seconds"],
                "training": old["selected_model_train_wall_measured_lower_seconds"],
            }
            if not math.isclose(
                math.fsum(inherited.values()),
                r["inherited_known_lower_preparation_training_seconds"],
                abs_tol=1e-9,
            ):
                raise ValueError("CL44 inherited preparation/training identity")
            terms += [
                {
                    "phase": p,
                    "value": v,
                    "unit": "s",
                    "classification": "derived",
                    "boundary": BOUNDARY,
                    "consumption_id": name + ":inherited:" + p,
                    "consumed_object": "V44:CL-E:" + p,
                    "evidence": inherited_evidence,
                    "semantics": "only old consumed preparation/training, excludes old online/loading/CHECK",
                }
                for p, v in inherited.items()
            ]
        unknown_phase = {
            "original FE/CSR cold setup": "setup",
            "manual implementation": "setup",
            "unsupervised Git/IO": "audit_io",
            "fresh unseen RHS preparation/load": "data_teacher",
            "full physical validation": "audit_io",
        }
        terms += [
            {
                "phase": unknown_phase[u],
                "value": None,
                "unit": "s",
                "classification": "unknown",
                "boundary": BOUNDARY,
                "consumption_id": name + ":unknown:" + u,
                "consumed_object": name + ":" + u,
                "evidence": evidence,
                "semantics": u,
                "common_unknown_proof": None,
            }
            for u in r["unknown"]
        ]
        terms.append(
            {
                "phase": "failures",
                "value": None,
                "unit": "s",
                "classification": "unknown",
                "boundary": BOUNDARY,
                "consumption_id": name + ":unknown:failure_attribution",
                "consumed_object": name + ":unallocated_historical_failure_replays",
                "evidence": evidence,
                "semantics": "known scenario has no separate failure allocation; complete per-candidate historical failure cost is unknown, not zero",
                "common_unknown_proof": None,
            }
        )
        route = {
            "route": name,
            "boundary": BOUNDARY,
            "terms": terms,
            "scope": "frozen failed finite-A diagnostic; not qualified target baseline",
        }
        total = summarize(route)["known_lower_seconds"]
        if not math.isclose(
            total, r["N1_known_lower_scenario_seconds"], rel_tol=1e-12, abs_tol=1e-9
        ):
            raise ValueError("published N1 cost mismatch")
        out[name] = route
    return out


def consume_timing(study, folder, budget, kind):
    """The actual numerical timing consumer refuses before any evaluate call."""
    if kind not in ("NN", "CONTROL"):
        raise ValueError("timing candidate kind")
    gate, _ = study.scope.stage("CHECK")
    frozen = study.frozen_models()
    selected_nn = min(
        ("NL", "NH"),
        key=lambda c: tuple(
            frozen[c]["selected"][k]
            for k in ("median_qe", "max_qe", "median_qr", "update")
        ),
    )
    correctness = gate["full_pass_by_route"]
    if correctness[study.routes[selected_nn]] != 8:
        raise ValueError("validation-preselected NN lacks all-eight correctness")
    routes = study.scope.deployment_cost_contract()
    controls = {name: routes[name] for name in study.control_routes}
    decision = select_cold_n1(controls, correctness)
    if decision["selected"] is None:
        raise ValueError(decision["status"])
    codes = {name: c for c, name in study.routes.items()}
    code = selected_nn if kind == "NN" else codes[decision["selected"]]
    result = study.evaluate(folder, budget, code)
    result.update(
        status="CONDITIONAL_INDEPENDENT_PROCESS_TIMING",
        validation_preselected_NN=selected_nn,
        selected_control=codes[decision["selected"]],
        cold_N1_cost_decision=decision,
        after_frozen_checker=True,
        NN20="NOT_QUALIFIED_BY_COST_ORDERING",
    )
    return result
