"""P3 decisions cannot be manufactured by status labels or port denominators."""

import hashlib
import json
from copy import deepcopy

import pytest

from src.io.task042_v4_gate import (
    diagnostic_status,
    publish,
    select_route,
    strict_from_norms,
)


def rows(native=0.09, schur=0.09, port=0.8):
    result = []
    for index in (0, 10, 11):
        norms = {
            key + "_absolute": value
            for key, value in (
                ("native", native),
                ("port", port),
                ("internal", 1e-14),
                ("native_identity", 1e-14),
                ("Schur_port_identity", 1e-14),
            )
        }
        norms.update(
            {
                key + "_scale": 1.0
                for key in (
                    "native",
                    "port",
                    "internal",
                    "native_identity",
                    "Schur_port_identity",
                )
            }
        )
        norms.update(
            submitted_recovery_absolute=0.0,
            submitted_field_norm=1.0,
            finite=True,
            maximum_slave_storage=0.0,
        )
        result.append(
            {
                "index": index,
                "passed": False,
                "final_original_norms": norms,
                "final": {"explicit_Schur_relative_rhs": schur},
            }
        )
    return result


def test_positive_is_not_strict_and_port_change_cannot_unlock():
    positive = rows()
    assert diagnostic_status(positive) == "GLOBAL_SPACE_DIAGNOSTIC_POSITIVE"
    assert not strict_from_norms(positive[0]["final_original_norms"])
    negative = rows(native=0.89, schur=0.91, port=1e-14)
    assert diagnostic_status(negative) == "BOUNDED_TWOLEVEL_NEGATIVE"
    assert select_route({"ERROR": {"rows": negative}}) is None


def test_all_original_gates_and_independent_selection():
    strict = rows(native=1e-12, schur=1e-12, port=1e-12)
    assert diagnostic_status(strict) == "STRICT_DIAGNOSTIC_PASS"
    bad = deepcopy(strict)
    bad[1]["final_original_norms"]["submitted_recovery_absolute"] = 1.0
    assert not strict_from_norms(bad[1]["final_original_norms"])
    bad[1]["final_original_norms"]["native_identity_absolute"] = 1e-5
    assert diagnostic_status(bad) == "COARSE_SPACE_NUMERICAL_BLOCKED"
    assert (
        select_route({"OLDPOD": {"rows": rows()}, "ERROR": {"rows": strict}}) == "ERROR"
    )
    assert (
        select_route({"ERROR": {"rows": rows()}, "OLDPOD": {"rows": rows()}})
        == "OLDPOD"
    )


def test_missing_inventory_and_nonfinite_blocked():
    with pytest.raises(ValueError, match="Three registered"):
        diagnostic_status(rows()[:1])
    invalid = rows()
    invalid[1]["final_original_norms"]["native_absolute"] = float("nan")
    assert diagnostic_status(invalid) == "COARSE_SPACE_NUMERICAL_BLOCKED"


def test_stage_publication_requires_cleanup_and_binds_exact_files(tmp_path):
    index = tmp_path / "index.json"
    directory = tmp_path / "run"
    directory.mkdir()
    (directory / "run_manifest.json").write_text('{"source_sha":"a"}')
    (directory / "numerical_summary.json").write_text(
        '{"status":"BOUNDED_TWOLEVEL_NEGATIVE"}'
    )
    summary = {"leader_exit_code": 1, "descendants_cleared": True}
    (directory / "run_summary.json").write_text(json.dumps(summary))
    publish("V4-P3-ERROR", directory, index)
    assert not index.exists()
    summary["leader_exit_code"] = 0
    (directory / "run_summary.json").write_text(json.dumps(summary))
    publish("V4-P3-ERROR", directory, index)
    proof = json.loads(index.read_text())["V4-P3-ERROR"]
    assert (
        proof["files_sha256"]["numerical_summary.json"]
        == hashlib.sha256(
            (directory / "numerical_summary.json").read_bytes()
        ).hexdigest()
    )
    with pytest.raises(ValueError, match="already published"):
        publish("V4-P3-ERROR", directory, index)
