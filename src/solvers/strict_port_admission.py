"""Fail-closed field qualification, separate from readable research evidence.

The caller supplies a frozen expected identity and file bindings. A record's
own PASS/file-present assertions are never execution authorization. This
research batch has no Maxwell factor/solve permission, even for valid inputs.
"""

import hashlib
import math
from pathlib import Path


IDENTITY_FIELDS = (
    "material",
    "modes",
    "background",
    "total_lo",
    "native",
    "source",
)
LIMITS = {
    "stored_operator_arithmetic": 1e-10,
    "oracle_self_consistency": 1e-10,
    "actual_vector_projection": 1e-10,
    "original_equation": 1e-6,
    "MPC": 1e-10,
    "affine": 1e-10,
}


def digest_file(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def qualification(record, expected):
    """Recompute the conjunction; no producer status aliases are consumed."""
    errors = []
    if not isinstance(record, dict) or not isinstance(expected, dict):
        raise ValueError("STRICT_CALLER_EXPECTED_AND_EVIDENCE_REQUIRED")
    if record.get("schema") != "strict_port_qualification.v1":
        errors.append("schema")
    identity = record.get("identity", {})
    if not isinstance(identity, dict):
        raise ValueError("STRICT_IDENTITY_MAPPING_REQUIRED")
    identity_valid = all(
        isinstance(expected.get(k), str)
        and len(expected[k]) == (40 if k == "source" else 64)
        and all(c in "0123456789abcdef" for c in expected[k])
        and identity.get(k) == expected[k]
        for k in IDENTITY_FIELDS
    )
    if not identity_valid:
        errors.append("caller_expected_identity")
    bindings = record.get("files", {})
    expected_files = expected.get("files", {})
    if not isinstance(bindings, dict) or not isinstance(expected_files, dict):
        raise ValueError("STRICT_FILE_BINDING_MAPPINGS_REQUIRED")
    files_valid = bool(expected_files) and set(bindings) == set(expected_files)
    for name, original in expected_files.items():
        actual = bindings.get(name)
        try:
            path = Path(original["path"])
            valid = (
                actual == original
                and path.is_file()
                and path.stat().st_size == original["bytes"]
                and digest_file(path) == original["sha256"]
            )
        except (KeyError, OSError, TypeError):
            valid = False
        files_valid = files_valid and valid
    if not files_valid:
        errors.append("actual_hash_bound_files")
    metrics = record.get("metrics", {})
    if not isinstance(metrics, dict):
        raise ValueError("STRICT_METRIC_MAPPING_REQUIRED")
    gates = {}
    for key, limit in LIMITS.items():
        value = metrics.get(key)
        gates[key] = (
            type(value) in (int, float) and math.isfinite(value) and 0 <= value <= limit
        )
        if not gates[key]:
            errors.append(key)
    for key in ("shared_physics", "role_component", "all_consumers"):
        gates[key] = record.get(key) is True
        if not gates[key]:
            errors.append(key)
    readable = bool(identity_valid and files_valid and record.get("schema") == "strict_port_qualification.v1")
    return dict(
        component_passed=bool(readable and gates["shared_physics"] and gates["role_component"]),
        negative_field_readable=readable,
        strict_complete_qualified=bool(not errors and readable and all(gates.values())),
        solve_admitted=False,
        execution_authority="review_report_v22.md: all new Maxwell factors/solves=0",
        gates=gates,
        failed=errors,
    )


def require_no_maxwell_execution(record, expected):
    state = qualification(record, expected)
    if not state["strict_complete_qualified"]:
        raise RuntimeError("STRICT_PORT_ROLE_REJECTED:" + ",".join(state["failed"]))
    raise RuntimeError("REVIEW_V22_MAXWELL_FACTOR_SOLVE_NOT_AUTHORIZED")
