"""Public-input and ledger boundaries of the single V19 original experiment."""

import hashlib
import json
from pathlib import Path

import pytest

from src.io import load_and_resolve
from src.io.input_loader import InputError
from src.io.physical_intermediate_profile import (
    CELL_CONDENSED_EXACT_PROFILE, DUAL_CELL_CONDENSED_PROFILE, profile_facts,
)
from src.runners import task038_launcher as launcher
from src.runners.physical_v14_budget import read_v14_effective_budget

ROOT = Path(__file__).resolve().parents[2]
CASE = ROOT / "input/task39extra/v19_x2_dual_condensed_original.dat"


def test_new_input_is_one_original_and_does_not_mutate_v18():
    old = profile_facts(CELL_CONDENSED_EXACT_PROFILE)
    spec = load_and_resolve(CASE)
    facts = profile_facts(DUAL_CELL_CONDENSED_PROFILE)
    assert spec.solver["stage"] == "X2_ORIGINAL"
    assert facts["outer"]["unknowns"] == "independent p6 trace plus original 80 ports"
    assert facts["resources"]["time_policy"] == "observe_only"
    assert set(facts["resources"]["stage_budgets"]) == {"X2_ORIGINAL"}
    assert facts["direct_controls"]["icntl"] == {"10": 0, "35": 0}
    assert profile_facts(CELL_CONDENSED_EXACT_PROFILE) == old
    facts["resources"]["tree_cap_bytes"] = 1
    assert profile_facts(CELL_CONDENSED_EXACT_PROFILE) == old


@pytest.mark.parametrize("before,after", [
    ('stage = "X2_ORIGINAL"', 'stage = "U5_NOTCH"'),
    ('restart = 32', 'restart = 64'),
    ('max_iterations = 2048', 'max_iterations = 4096'),
    ('require_zero_swap = true', 'require_zero_swap = false'),
    ('nedelec_degree = 6', 'nedelec_degree = 5'),
    ('[geometry]', '[geometry]\ncell_notch = "positive_x_middle_y_z40_80"'),
])
def test_public_input_rejects_changes_outside_the_single_candidate(tmp_path, before, after):
    candidate = tmp_path / "candidate.dat"
    candidate.write_text(CASE.read_text().replace(before, after))
    with pytest.raises(InputError):
        load_and_resolve(candidate)


@pytest.fixture
def prepared_ledger_root(tmp_path, monkeypatch):
    prior = tmp_path / "benchmarks/artifacts/task39extra/p4_cell_condensed_v18/root_engineering/user_closed_final_ledger.json"
    prior.parent.mkdir(parents=True)
    prior.write_text(json.dumps({
        "schema": "task039extra.v18.shared-workflow-ledger.v1",
        "batch_identity": "review_v18_p4_cell_condensed", "elapsed_seconds": 7709.0,
        "total_budget_seconds": 43200.0, "conservative_allowance_seconds": 0.0,
        "policy_debits": [{"seconds": 43200.0, "actual_elapsed_seconds": None}],
        "stages": {"U5_NOTCH": {"active_attempt": None, "attempts": [
            {"status": "EXTERNAL_PARENT_LOSS", "reserved_seconds": 43200.0,
             "actual_elapsed_seconds": None}]}},
        "predecessors": {"v14": {"policy_debits": [
            {"seconds": 600.0, "actual_elapsed_seconds": None}]}},
    }))
    monkeypatch.setattr(launcher, "V19_PREDECESSOR_V18_LEDGER_SHA256",
                        hashlib.sha256(prior.read_bytes()).hexdigest())
    admission = launcher._dual_condensed_v19_shared_ledger_path(tmp_path).parent.parent / "root_engineering/x0_admission.json"
    admission.parent.mkdir(parents=True)
    admission.write_text(json.dumps({"status": "PASS", "source_sha": "a" * 40}))
    return tmp_path, prior, admission


def reserve(root, *, source="a" * 40, stage="X2_ORIGINAL", policy="observe_only"):
    return launcher._reserve_v19_shared_budget(
        root, root / "new_original", source_sha=source, stage=stage,
        stage_budget={"workflow_seconds": 43200, "solve_seconds": 43200},
        workflow_clock_start={"monotonic": 1.0, "boottime": 1.0, "utc_ns": 1_000_000_000},
        time_policy=policy,
    )


def test_old_unknown_policy_cost_is_preserved_not_relabelled_as_new_measurement(prepared_ledger_root):
    root, prior, _ = prepared_ledger_root
    original = prior.read_bytes()
    lease = reserve(root)
    ledger = json.loads(Path(lease["path"]).read_text())
    old = ledger["predecessors"]["v18"]
    assert prior.read_bytes() == original
    assert old["effective_budget_snapshot"]["policy_debit_seconds"] == 43200.0
    assert old["unknown_elapsed_attempts"][0]["actual_elapsed_seconds"] is None
    assert old["historical_predecessors"]["v14"]["policy_debits"][0]["actual_elapsed_seconds"] is None
    assert read_v14_effective_budget(ledger)["measured_elapsed_seconds"] == 0.0
    assert ledger["fresh_worker_count"] == 1
    with pytest.raises(InputError, match="unsettled"):
        reserve(root)


@pytest.mark.parametrize("kind", ["notch", "enforce", "source", "prior_hash"])
def test_no_unqualified_or_wrong_scope_launch(prepared_ledger_root, kind):
    root, prior, _ = prepared_ledger_root
    args = {}
    if kind == "notch":
        args["stage"] = "U5_NOTCH"
    elif kind == "enforce":
        args["policy"] = "enforce"
    elif kind == "source":
        args["source"] = "b" * 40
    else:
        prior.write_text(prior.read_text() + " ")
    with pytest.raises(InputError):
        reserve(root, **args)
    assert not launcher._dual_condensed_v19_shared_ledger_path(root).exists()
