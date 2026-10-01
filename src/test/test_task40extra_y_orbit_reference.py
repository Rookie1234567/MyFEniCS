"""Contracts and optional evidence-only checks; no unapproved PDE launch."""

import ast
import os
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def test_y_orbit_core_and_runners_parse_without_execution():
    for path in (ROOT / "src/solvers/task40extra_y_orbit_reference.py",
                 ROOT / "benchmarks/run_y_orbit_reference_probe.py",
                 ROOT / "benchmarks/check_y_orbit_reference_probe.py"):
        ast.parse(path.read_text(), filename=str(path))


def test_full3d_identity_and_notch_contract_retains_interior_and_all_aliases():
    source = (ROOT / "src/solvers/task40extra_y_orbit_reference.py").read_text()
    assert "entity_dofs[3][0]" in source
    assert "physical_n % layout.ny" in source
    assert "projection_values ALREADY includes conjugation" in source
    assert "self.q.conj().T @ values" in source
    assert "full_original_true_residual" in source
    assert "notch physical forcing must generate nonzero transverse block content" in source
    assert "np.array(modal[rows, rows]" in source
    assert "global_factor" not in source
    assert "self.apply_array(source.getArray(readonly=True))" in source
    assert "self.apply(source.getArray(readonly=True))" in source


def test_phi5_is_a_bounded_real_bloch_case_with_unchanged_notch_gate():
    runner = (ROOT / "benchmarks/run_y_orbit_reference_probe.py").read_text()
    source = (ROOT / "src/solvers/task40extra_y_orbit_reference.py").read_text()
    assert "args.azimuth not in (0.0, 5.0)" in runner
    assert 'label == "physical" and packet["nonzero_q_primal_relative"]' in source
    assert 'abs(complex(cfg.ky).imag)' in source


@pytest.mark.skipif(not os.environ.get("Y_ORBIT_PILOT_EVIDENCE"), reason="parent-approved numerical pilot evidence not supplied")
def test_actual_full3d_pilot_evidence_is_independently_checked():
    from benchmarks.check_y_orbit_reference_probe import check
    result = check(Path(os.environ["Y_ORBIT_PILOT_EVIDENCE"]))
    assert result["evidence_valid"] and result["gate_pass"]
