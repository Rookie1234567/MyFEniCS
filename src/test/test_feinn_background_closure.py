"""Only new affine arithmetic, budget preservation and FE-free dispatch gates."""

from types import SimpleNamespace

import numpy as np
import pytest

from src.solvers.feinn_saved_field_diagnostics import (
    corrected_background_rows,
    RetainedA4Budget,
)
from benchmarks.check_task42extra_v12 import verify_background, raw_change


def background_fixture():
    rng = np.random.default_rng(4211301)
    A = rng.normal(size=(5, 5)) + 1j * rng.normal(size=(5, 5))
    b3 = rng.normal(size=5) + 1j * rng.normal(size=5)
    b4 = rng.normal(size=5) + 1j * rng.normal(size=5)
    f = rng.normal(size=5) + 1j * rng.normal(size=5)
    cs = {
        k: rng.normal(size=5) + 1j * rng.normal(size=5)
        for k in ("p3reference", "M3600", "Mfinal")
    }
    rs = {k: A @ c - f for k, c in cs.items()}
    db = b3 - b4
    rows, corrected = corrected_background_rows(rs, A @ db, f, f + A @ b4)
    raw = dict(
        P34b3=b3,
        b4=b4,
        d_b=db,
        A4_d_b=A @ db,
        f4=f,
        total_rhs4=f + A @ b4,
        direct_same_total_reference=A @ (cs["p3reference"] + db) - f,
    )
    raw.update({"original_" + k: v for k, v in rs.items()})
    raw.update({"corrected_" + k: v for k, v in corrected.items()})
    result = dict(
        rows=rows,
        A4=2,
        cumulative_A4_reserved=2,
        AH4=0,
        G_actions=0,
        Gsolve=0,
        new_reference_solves=0,
        network_forwards=0,
        G4_created=False,
        Gram_factor_created=False,
        Maxwell_factor_created=False,
        p3_background_MPC_relative=0.0,
        background_embedding=dict(
            common_E_scaled_curl_relative=[0.0, 0.0], MPC_operation_relative=0.0
        ),
    )
    return result, raw


def test_shared_affine_shift_nonhermitian_complex_direct_and_energy_pairing():
    result, raw = background_fixture()
    out = verify_background(result, raw)
    assert out["rows"]["M3600"]["error_image_invariance"] < 1e-10
    assert (
        result["rows"]["Mfinal"]["original_f4_denominator"]
        != result["rows"]["Mfinal"]["total_rhs_diagnostic_denominator"]
    )


@pytest.mark.parametrize(
    "corruption",
    ["shift", "cross", "denominator", "phase", "cap", "factor", "nonfinite"],
)
def test_affine_checker_rejects_corrupt_inputs_or_qualification(corruption):
    record, raw = background_fixture()
    row = record["rows"]["M3600"]
    if corruption == "shift":
        raw["d_b"][0] += 1
    elif corruption == "cross":
        row["signed_cross"] += 1
    elif corruption == "denominator":
        row["original_f4_denominator"] *= 2
    elif corruption == "phase":
        row["normalized_cross_complex"][1] += 1
    elif corruption == "cap":
        record["cumulative_A4_reserved"] = 5
    elif corruption == "factor":
        record["Maxwell_factor_created"] = True
    else:
        raw["A4_d_b"][0] = np.nan
    with pytest.raises(ValueError):
        verify_background(record, raw)


def test_cumulative_action_reservation_survives_failure_and_reload(tmp_path):
    def fail(c):
        raise RuntimeError("native_failure")

    p = SimpleNamespace(apply=fail)
    path = tmp_path / "used.npz"
    ops = RetainedA4Budget(path, p, "same input", lambda: None)
    with pytest.raises(RuntimeError, match="native_failure"):
        ops.apply(np.ones(3))
    p.apply = lambda c: c
    restored = RetainedA4Budget(path, p, "same input", lambda: None)
    assert restored.inherited == 1
    for _ in range(3):
        restored.apply(np.ones(3))
    with pytest.raises(RuntimeError, match="CUMULATIVE_A4_CAP"):
        restored.apply(np.ones(3))
    with pytest.raises(ValueError, match="IDENTITY_CHANGED"):
        RetainedA4Budget(path, p, "changed input", lambda: None)


def test_zero_energy_reports_undefined_fraction_and_signed_absolute_change():
    out = raw_change(
        np.zeros(2, complex),
        np.ones(2, complex),
        np.zeros(2, complex),
        np.ones(2, complex),
    )
    assert out["removed_energy_fraction"] is None and out["near_zero_before"]
    assert out["absolute_energy_removed"] == -2
