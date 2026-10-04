"""Pure, explicit layered engine/predictor acceptance, never a solver adapter."""

import hashlib
import json
import math
import re
from pathlib import Path

LAYERS = (
    "physics",
    "discretization",
    "problem",
    "correctness",
    "engineering",
    "neural",
)


def _leaves(value, prefix=""):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _leaves(item, prefix + "." + key if prefix else key)
    else:
        yield prefix, value


def check_engine(request, offered):
    """Match explicit values; unknown and partial evidence are real failures."""
    rows = []
    for layer in LAYERS:
        requirements = dict(_leaves(request.get(layer, {})))
        actual = dict(_leaves(offered.get(layer, {})))
        if not requirements:
            rows.append(
                {
                    "layer": layer,
                    "field": "inventory",
                    "reason": "EMPTY_REQUIRED_LAYER",
                    "passed": False,
                }
            )
        for field, expected in requirements.items():
            value = actual.get(field)
            known = expected is not None and expected != "unknown"
            passed = known and type(value) is type(expected) and value == expected
            rows.append(
                {
                    "layer": layer,
                    "field": field,
                    "required": expected,
                    "offered": value,
                    "passed": passed,
                    "reason": "MATCH"
                    if passed
                    else "UNRESOLVED_REQUIREMENT"
                    if not known
                    else "MISSING_OR_DIFFERENT",
                }
            )
    # A schema or compatible=true flag never substitutes for these identities.
    evidence = offered.get("evidence", {})
    if not re.fullmatch(
        r"[0-9a-f]{40}", evidence.get("source_sha", "")
    ) or not re.fullmatch(r"[0-9a-f]{64}", evidence.get("sha256", "")):
        rows.append(
            {
                "layer": "engineering",
                "field": "evidence",
                "passed": False,
                "reason": "UNBOUND_ENGINE_EVIDENCE",
            }
        )
    good = all(row["passed"] for row in rows)
    return {
        "status": "MATCHED_CONTRACT_ONLY" if good else "NO_MATCHED_QUALIFIED_ENGINE",
        "accepted": good,
        "rows": rows,
        "layer_pass": {
            layer: all(r["passed"] for r in rows if r["layer"] == layer)
            for layer in LAYERS
        },
        "numeric_actions": 0,
        "solver_qualification_granted": False,
    }


def consume_contract(request, offered, consumer):
    result = check_engine(request, offered)
    if not result["accepted"]:
        return result
    result["consumer_result"] = consumer(offered)
    return result


def memory_condition(baseline_objects, neural_objects, *, time_seconds):
    """Object lifetimes define simultaneous peaks; saved archives are excluded."""

    def peak(objects):
        if any(o["bytes"] is None for o in objects):
            return None
        for o in objects:
            if o["bytes"] < 0 or o["end"] < o["start"] or o["kind"] == "archive_only":
                raise ValueError("memory live object inventory")
        edges = sorted({o[k] for o in objects for k in ("start", "end")})
        return max(
            (
                sum(o["bytes"] for o in objects if o["start"] <= t < o["end"])
                for t in edges
            ),
            default=0,
        )

    b, n = peak(baseline_objects), peak(neural_objects)
    if b is None or n is None or time_seconds is None:
        return {
            "status": "UNKNOWN",
            "NN20": "NOT_QUALIFIED",
            "baseline_peak_bytes": b,
            "neural_peak_bytes": n,
        }
    if not math.isfinite(time_seconds) or time_seconds < 0:
        raise ValueError("unknown/nonfinite full time")
    return {
        "status": "DERIVED_NECESSARY_CONDITION_ONLY",
        "baseline_peak_bytes": b,
        "neural_peak_bytes": n,
        "memory_condition": n <= 0.8 * b,
        "time_condition": time_seconds <= 172800,
        "NN20": "NOT_QUALIFIED",
    }


def read_metadata(receipt, root, *, limit=4 * 2**20):
    """Read only hash-bound small metadata; no model/array deserialization."""
    path = (Path(root) / receipt["path"]).resolve()
    if not path.is_relative_to(Path(root).resolve()) or path.stat().st_size > limit:
        raise ValueError("metadata path/capacity")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != receipt["sha256"]:
        raise ValueError("metadata receipt hash")
    return json.loads(raw)
