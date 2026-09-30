"""Only new scope/budget/layout checks; no old FE campaign replay."""

from pathlib import Path
import json

import numpy as np

from src.runners.feinn_campaign import (
    campaign_budget,
    OLD_SECONDS,
    AUTHORITY,
    STAGES,
    DEPENDENCIES,
)
from src.io.feinn_pilot import load_pilot
from src.solvers.feinn_authority_assembly import packet_csr
from src.solvers.feinn_native import FullNativePacket


def test_profile_logs_complex_and_numpy_physical_facts():
    from src.solvers.feinn_authority_assembly import profile_fact_json

    record = json.loads(
        profile_fact_json("form_begin", dict(phase=1 + 2j, array=np.array([1j])), 3.0)
    )
    assert record["facts"]["phase"] == "(1+2j)"
    assert record["facts"]["array"] == ["1j"]


def test_new_budget_does_not_reuse_old_16h_remaining():
    entries = [
        dict(
            path="/results/task42extra/task42extra_v7_old/summary.json", seconds=49000
        ),
        dict(
            path="/results/task42extra/task42extra_v8_p4_reference_recovery_stamp/run_summary.json",
            seconds=200,
        ),
        dict(path="/tmp/task42extra/checks/v8_b_unit_stamp/summary.json", seconds=5),
    ]
    result = campaign_budget(entries)
    assert result["new_used_seconds"] == 205
    assert result["cumulative_seconds"] == OLD_SECONDS + 205
    assert result["groups_used_seconds"]["A"] == 200
    assert result["groups_used_seconds"]["B"] == 5
    assert result["new_remaining_seconds"] == 43200 - 205 - 120


def test_new_inputs_have_explicit_reference_only_identity():
    root = Path(__file__).resolve().parents[2]
    for stage in AUTHORITY:
        spec = load_pilot(root / "input/task042extra_feinn_5nm" / (stage + ".dat"))
        assert spec.derived["audit_kind"] == "DISCRETIZATION_AUTHORITY_AUDIT"
        assert spec.discretization["degree"] == 4
        assert spec.derived["environment_mode"] == "fe"


def test_neural_inputs_keep_label_routes_separate_and_PDE_has_no_reference_dependency():
    root = Path(__file__).resolve().parents[2]
    for stage in STAGES.keys() - AUTHORITY:
        spec = load_pilot(root / "input/task042extra_feinn_5nm" / (stage + ".dat"))
        supervised = "reference_fit" in stage or "representation" in stage
        assert spec.derived["reference_used_for_training"] == supervised
        assert spec.derived["pde_only_solve"] != supervised
        assert not spec.derived["production_initialization_allowed"]
    for stage in ("v8_plain_dual", "v8_phase_dual"):
        assert "e3_reference" not in DEPENDENCIES[stage]


def test_CSR_multimaster_complex_MPC_and_ports():
    rng = np.random.default_rng(421801)
    n, d = 5, 3
    arrays = dict(
        F=rng.normal(size=(2, d, d)) + 1j * rng.normal(size=(2, d, d)),
        classes=np.array([0, 1]),
        cell_dofs=np.array([[0, 1, 2], [2, 3, 4]]),
        masters=np.arange(n),
        slaves=np.array([], np.int64),
        full_rows=np.array(n),
        idofs=np.array([[2], [4]]),
        erows=np.array([0, 1, 2, 3, 3, 4, 5]),
        eids=np.array([0, 1, 2, 2, 1, 3, 4]),
        evals=np.array([1, 1, 1, 0.3 + 0.4j, 0.7 - 0.2j, 1, 1], np.complex128),
        br=np.array([0, 4]),
        bp=np.array([0, 0]),
        bv=np.array([0.2 + 0.5j, 0.6 - 0.4j]),
        dr=np.array([1, 3]),
        dp=np.array([0, 0]),
        dv=np.array([0.5 + 0.7j, -0.2 + 0.1j]),
        H=np.array([2.0]),
        g=np.ones(n, np.complex128),
        gp=np.array([0.1j]),
        total_g=np.ones(n, np.complex128),
        background=np.zeros(n, np.complex128),
        background_alpha=np.array([0j]),
    )
    p = FullNativePacket(arrays)
    M, pair = packet_csr(None, p)
    assert pair < 1e-14
    for _ in range(3):
        c = rng.normal(size=n) + 1j * rng.normal(size=n)
        alpha = rng.normal(size=1) + 1j * rng.normal(size=1)
        np.testing.assert_allclose(
            M @ np.r_[c, alpha],
            np.r_[p.volume(c) + p.B(alpha), -p.D(c) + p.a["H"] * alpha],
            atol=1e-13,
        )
