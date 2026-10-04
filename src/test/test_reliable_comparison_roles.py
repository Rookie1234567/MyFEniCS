"""Aliased operator controls do not become an independent reference."""

import numpy as np
import pytest
from scipy import sparse
from src.solvers.affine_field_output import SplitVector
from benchmarks.fixed_phase_checker import compare_from_arrays, complex_mode_differences


def observation():
    keys = np.array(
        [
            [side, str(m), str(n), pol]
            for side in ("top", "bottom")
            for m in range(-8, 9)
            for n in range(-2, 3)
            for pol in ("s", "p")
        ]
    )
    E = np.array([[[1.0, 0, 0]]], complex)
    C = np.array([[[0, 1j, 0]]], complex)
    k = np.zeros((340, 3))
    k[:, 2] = np.where(keys[:, 0] == "top", 1.0, -1.0)
    e = np.zeros((340, 3), complex)
    e[:, 0] = 1
    out = np.zeros(340, complex)
    i = np.flatnonzero(np.all(keys == ["bottom", "0", "0", "s"], axis=1))[0]
    out[i] = np.sqrt(2.0)
    powers = np.zeros(340)
    powers[i] = 1.0
    z = dict(
        quadrature_weights_nm3=np.ones((1, 1)),
        total_E=E,
        scattered_E=E,
        total_curl=C,
        scattered_curl=C,
        total_H=C / 1j,
        scattered_H=C / 1j,
        cell_epsilon=np.ones(1, complex),
        k0=np.array(1.0),
        mu_r=np.array(1.0 + 0j),
        incident_power=np.array(1.0),
        port_area=np.array(1.0),
        mode_keys=keys,
        mode_k=k,
        mode_e=e,
        mode_boundary_z=np.zeros(340),
        outgoing_boundary=out,
        per_level_power=powers,
        physical_field_norms=np.ones(4),
    )
    for key in ("total_projection", "scattered_projection", "outgoing_origin"):
        z[key] = out.copy()
    for key, val in (
        ("selected_total_E", E),
        ("selected_scattered_E", E),
        ("selected_total_H", C / 1j),
        ("selected_scattered_H", C / 1j),
    ):
        z[key] = np.tile(val[0, 0], (6, 1))
    return z


@pytest.mark.parametrize("projection_dtype", [np.complex128, np.clongdouble])
def test_same_role_controls_cannot_grant_reference_or_finite_p(projection_dtype):
    names = ("old_E3", "new_E3", "old_E4", "new_E4")
    pairs = [("old_E3", "new_E3"), ("old_E4", "new_E4"), ("new_E3", "new_E4")]
    z = {n: observation() for n in names}
    for val in z.values():
        val["total_projection"] = val["total_projection"].astype(projection_dtype)
    a = {
        n: dict(
            native_relative=0.0,
            augmented_relative=0.0,
            original_total_augmented_relative=0.0,
            recovery=0.0,
            independent_physical_weak=0.0,
            channels=340,
            full_FE_recovered=True,
        )
        for n in names
    }
    integrals = {}
    for x, y in pairs:
        v = np.ones((6, 4, 3))
        v[:, :, 0] = 0
        for q in (15, 30):
            integrals[f"{x}_vs_{y}_q{q}"] = v.copy()
    r = compare_from_arrays(
        integrals, z, a, role_aliases={n: n[4:] for n in names}, comparison_pairs=pairs
    )
    assert not r["reference_qualified"] and not r["target_qualified"]
    assert not r["comparisons"]["old_E3_vs_new_E3"]["qualified"]
    assert not r["comparisons"]["old_E4_vs_new_E4"]["qualified"]
    assert r["comparisons"]["new_E3_vs_new_E4"]["qualified"]
    assert r["missing_roles"] == ["O3", "O6"]
    with pytest.raises(ValueError, match="DUPLICATE"):
        compare_from_arrays(
            integrals,
            z,
            a,
            role_aliases={n: n[4:] for n in names},
            comparison_pairs=pairs + pairs,
        )


def test_both_sparse_linear_components_before_guard_digit_combination():
    # Combining in either binary64 or clongdouble BEFORE this map loses lo.
    a = sparse.csr_matrix(np.array([[1e20, -1e20]], complex))
    v = SplitVector(np.ones(2, complex), np.array([1e-20, 0], complex))
    assert v.map(lambda x: a @ x).physical_values()[0] == 1
    assert (a @ (v.hi + v.lo))[0] == 0


def test_mode_comparison_retains_guard_digits_only_when_explicitly_allowed():
    reference = np.ones(340, dtype=np.clongdouble)
    candidate = reference.copy()
    candidate[23] += np.longdouble("1e-18")
    keys = observation()["mode_keys"]
    assert candidate.astype(np.complex128)[23] == reference[23]
    with pytest.raises(ValueError, match="FULL_COMPLEX_MODE_LAYOUT"):
        complex_mode_differences(candidate, reference, keys)
    result = complex_mode_differences(
        candidate, reference, keys, guard_digits_allowed=True
    )
    assert result["worst_key"] == keys[23].tolist()
    assert result["max_relative"] == float(abs(candidate[23] - reference[23]))
    assert result["max_relative"] > 0


@pytest.mark.parametrize("invalid_dtype", [np.float64, np.complex64, object])
def test_guard_digit_opt_in_does_not_accept_invalid_complex_layout(invalid_dtype):
    reference = np.ones(340, complex)
    with pytest.raises(ValueError, match="FULL_COMPLEX_MODE_LAYOUT"):
        complex_mode_differences(
            np.ones(340, dtype=invalid_dtype),
            reference,
            observation()["mode_keys"],
            guard_digits_allowed=True,
        )
