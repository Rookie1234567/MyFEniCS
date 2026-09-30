"""Targeted audit opt-in, allocation bounds, scales and FE-only atomic data."""

from pathlib import Path
import numpy as np
import pytest

from src.io.feinn_pilot import ROOT, load_pilot
from src.solvers.feinn_discretization_audit import (
    atomic_npz, capacity_plan, channel_key, difference_record, positive_energy,
)


def test_p4_capacity_preserves_full_space_and_counts_bytes():
    p = capacity_plan([8, 6, 8], 4)
    assert p["independent_rows"] == 75264
    assert p["inventory"]["full_fe_rows"] == 78936
    assert p["inventory"]["periodic_slaves"] == 3672
    assert p["full_cell_tensor_bytes"] == 552960000
    assert p["allocation_upper_bytes"] < 12 * 2**30
    assert p["factor_bytes"] == "UNKNOWN_UNTIL_SYMBOLIC"


@pytest.mark.parametrize("energy", [-1e-6, 1 + 1e-5j, np.nan])
def test_comparison_never_hides_significant_bad_energy(energy):
    with pytest.raises(ValueError):
        positive_energy(energy, 1)
    assert positive_energy(-1e-16, 1) == 0


def test_p4_denominator_and_near_zero_natural_scale_are_explicit():
    r = difference_record(2, 4, 1, 10)
    assert r["relative"] == .25 and r["denominator"] == 4
    r = difference_record(0, 0, 1e-14, 1)
    assert r["near_zero"] and r["denominator"] == 1e-12


def test_channel_identity_uses_physics_not_file_row_number():
    row = dict(side="top", m=-3, n=1, polarization="s", mode_index=7)
    assert channel_key(row, 8.75, -1.25) == channel_key(dict(row, mode_index=2), 8.75, -1.25)
    assert channel_key(row, 8.75, -1.25) != channel_key(dict(row, side="bottom"), 8.75, -1.25)


def test_atomic_fe_packet_round_trip_and_no_torch_import(tmp_path):
    import sys
    path = tmp_path / "packet.npz"
    c = np.arange(9, dtype=float) * (1 + 2j)
    atomic_npz(path, c_scattered=c)
    with np.load(path, allow_pickle=False) as item:
        assert np.array_equal(item["c_scattered"], c)
    assert not list(tmp_path.glob("*.tmp-*"))
    assert "torch" not in sys.modules


def test_new_stages_require_explicit_audit_and_old_p4_gate_unchanged(tmp_path):
    from src.solvers.feinn_reference import p_check
    status, files = p_check(None, None, dict(result=dict(comparisons={"old": dict(qualified=False)})), None, None)
    assert status["p4_reference"] == "not_run" and files == {}
    for name in ("v7_p_transfer_checks", "v7_p4_reference", "v7_p3_p4_compare"):
        path = ROOT / "input/task042extra_feinn_5nm" / (name + ".dat")
        spec = load_pilot(path)
        assert spec.derived["audit_kind"] == "DISCRETIZATION_AUTHORITY_AUDIT"
        assert spec.derived["environment_mode"] == "fe"
        assert spec.discretization["degree"] == 4
        wrong = tmp_path / "wrong.dat"
        wrong.write_text(path.read_text().replace('audit_kind = "DISCRETIZATION_AUTHORITY_AUDIT"', 'audit_kind = "OTHER"'))
        with pytest.raises(ValueError):
            load_pilot(wrong)
    assert Path(ROOT / "benchmarks/artifacts/task42extra/index_e4_p4.json").exists()
