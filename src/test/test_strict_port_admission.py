"""Actual entry guards reject incomplete evidence before any solver import."""

from copy import deepcopy
import hashlib

import pytest

from src.solvers.strict_port_admission import IDENTITY_FIELDS, LIMITS, qualification


def fixture(tmp_path):
    path = tmp_path / "frozen.json"
    path.write_text('{"frozen":true}\n')
    binding = dict(
        path=str(path),
        bytes=path.stat().st_size,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
    )
    expected = {k: ("a" * (40 if k == "source" else 64)) for k in IDENTITY_FIELDS}
    expected["files"] = dict(evidence=binding)
    record = dict(
        schema="strict_port_qualification.v1",
        identity={k: expected[k] for k in IDENTITY_FIELDS},
        files=deepcopy(expected["files"]),
        metrics={k: v / 2 for k, v in LIMITS.items()},
        shared_physics=True,
        role_component=True,
        all_consumers=True,
    )
    return record, expected


@pytest.mark.parametrize(
    "failure",
    list(LIMITS)
    + list(IDENTITY_FIELDS)
    + ["file", "oracle_UNKNOWN", "consumers", "shared", "schema", "p6_only"],
)
def test_real_campaign_and_direct_solver_guards(tmp_path, monkeypatch, failure):
    from src.runners import fixed_phase_campaign as campaign
    from src.solvers import fixed_phase_reliable_ports as work

    r, e = fixture(tmp_path)
    if failure in LIMITS:
        r["metrics"][failure] = LIMITS[failure] * 1.01
    elif failure in IDENTITY_FIELDS:
        r["identity"][failure] = "b" * len(e[failure])
    elif failure == "file":
        (tmp_path / "frozen.json").unlink()
    elif failure == "oracle_UNKNOWN":
        r["metrics"]["oracle_self_consistency"] = "UNKNOWN"
    elif failure == "consumers":
        r["all_consumers"] = False
    elif failure == "shared":
        r["shared_physics"] = False
    elif failure == "schema":
        r["schema"] = "unsupported.schema"
    else:
        r["p6_failed"] = True  # An unrelated role is not a shared failure.
    state = qualification(r, e)
    assert state["strict_complete_qualified"] is (failure == "p6_only")
    monkeypatch.setattr(
        campaign,
        "selected",
        lambda *_: pytest.fail("dependency/solver sentinel reached"),
    )
    reason = "NOT_AUTHORIZED" if failure == "p6_only" else "STRICT_PORT_ROLE_REJECTED"
    for stage in ("v22_e3_correction", "v22_e4_correction"):
        with pytest.raises(RuntimeError, match=reason):
            campaign.v22_admission(stage, [], strict_evidence=r, current_expected=e)
    with pytest.raises(RuntimeError, match=reason):
        work.correction(
            None, None, None, None, None, None, strict_evidence=r, current_expected=e
        )


def test_missing_caller_expected_and_boolean_shortcut_rejected(tmp_path):
    r, e = fixture(tmp_path)
    with pytest.raises(ValueError, match="CALLER_EXPECTED"):
        qualification(r, None)
    r.update(files_present=True, identity_matches=True)
    r["files"] = {}
    r["metrics"]["actual_vector_projection"] = True
    state = qualification(r, e)
    assert (
        not state["strict_complete_qualified"] and not state["negative_field_readable"]
    )
    assert "actual_vector_projection" in state["failed"]


def test_low_bytes_corrupted_after_binding(tmp_path):
    r, e = fixture(tmp_path)
    assert qualification(r, e)["strict_complete_qualified"]
    (tmp_path / "frozen.json").write_text('{"frozen":null}\n')
    assert "actual_hash_bound_files" in qualification(r, e)["failed"]


@pytest.mark.parametrize("key", ["identity", "files", "metrics"])
def test_corrupted_mapping_rejected_before_entry(tmp_path, key):
    from src.runners.fixed_phase_campaign import v22_admission

    r, e = fixture(tmp_path)
    r[key] = None
    with pytest.raises(ValueError, match="MAPPING"):
        v22_admission("v22_e3_correction", [], strict_evidence=r, current_expected=e)
