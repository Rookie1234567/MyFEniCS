import ast
from pathlib import Path

import pytest

from src.io.feinn_pilot import load_pilot
from src.runners.feinn_attribution_campaign import (
    STAGES,
    DIAGNOSTIC_POLICY,
    campaign_budget,
)


@pytest.mark.parametrize("stage", list(STAGES))
def test_diagnostics_cannot_be_pde_only_or_training(stage):
    spec = load_pilot(Path("input/task042extra_feinn_5nm") / (stage + ".dat"))
    assert spec.derived["environment_mode"] == STAGES[stage][0]
    assert spec.execution["timeout_seconds"] == STAGES[stage][1]
    for k, v in DIAGNOSTIC_POLICY.items():
        assert spec.derived[k] is v
    assert not spec.derived["reference_used_for_training"]
    assert not spec.derived["pde_only_solve"]


def test_fresh_and_inherited_costs_do_not_reset():
    rows = [
        dict(
            path="/x/task42extra_v12_saved_field_attribution_1/run_summary.json",
            seconds=100,
        ),
        dict(
            path="/x/task42extra_v12_saved_field_attribution_2/run_summary.json",
            seconds=200,
        ),
    ]
    ledger = campaign_budget(rows)
    assert ledger["groups_used_seconds"]["B"] == 300
    assert ledger["new_used_seconds"] == 300
    assert ledger["new_remaining_seconds"] == 21600 - 1800 - 300
    assert ledger["cumulative_seconds"] > 154319


def test_fe_dispatch_does_not_import_torch_at_top_level():
    tree = ast.parse(Path("src/runners/feinn_attribution_campaign.py").read_text())
    imports = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
    assert all("torch" not in ast.unparse(n) for n in imports)
