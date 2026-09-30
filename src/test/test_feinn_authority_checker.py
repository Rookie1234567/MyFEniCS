"""Reject corrupt arithmetic and false p authority qualification."""

from copy import deepcopy

import numpy as np
import pytest

from benchmarks.check_task42extra_v7 import error_pair, reference_gate, comparison_gate


def record(left, right, absolute, natural=1):
    denominator = max(right, 1e-12 * natural)
    return dict(
        p3_norm=left,
        p4_norm=right,
        absolute=absolute,
        natural_scale=natural,
        denominator=denominator,
        relative=absolute / denominator,
        near_zero=right < 1e-12 * natural,
    )


def test_checker_keeps_predeclared_near_zero_denominator():
    raw = record(1e-15, 0, 1e-15)
    assert error_pair(raw, 1e-15, 0, 1e-15)["relative"] == pytest.approx(1e-3)
    raw["denominator"] = 1e-15
    with pytest.raises(ValueError, match="COMPARISON_ARITHMETIC_denominator"):
        error_pair(raw, 1e-15, 0, 1e-15)


def reference():
    audit = {
        key: 1e-12
        for key in (
            "native_relative",
            "augmented_relative",
            "original_total_augmented_relative",
            "independent_DOLFINx_total_native_relative",
            "port_operation_relative",
            "port_full_rhs_relative",
        )
    }
    audit["slave_storage_max"] = 0
    return dict(
        reference_qualified=True,
        MPC_recovery_relative=1e-15,
        physics=dict(
            records=dict(
                REFERENCE=dict(
                    audit=audit,
                    port=dict(R_total=0.8, T_total=0.1, A_balance=0.1),
                    volume=dict(A_volume_total=0.1),
                )
            )
        ),
        direct=dict(
            rss_after_symbolic_bytes=1000000000,
            estimated_factor_bytes=1000000000,
            conversion_and_workspace_reserve_bytes=1000000000,
            factor_released=True,
            matrix_released=True,
            minimal_recovery_packet_saved_before_factor_release=True,
            rss_after_release_bytes=1000000000,
            rss_before_release_bytes=4000000000,
            original_port_recovery_relative=1e-14,
        ),
    )


@pytest.mark.parametrize("fault", ["energy", "release", "capacity", "residual"])
def test_reference_checker_cannot_qualify_incomplete_authority(fault):
    raw = reference()
    audit = raw["physics"]["records"]["REFERENCE"]["audit"]
    assert reference_gate(raw, audit)["qualified"]
    if fault == "energy":
        raw["physics"]["records"]["REFERENCE"]["volume"]["A_volume_total"] += 0.01
    elif fault == "release":
        raw["direct"]["rss_after_release_bytes"] = raw["direct"][
            "rss_before_release_bytes"
        ]
    elif fault == "capacity":
        raw["direct"]["estimated_factor_bytes"] = 16 * 2**30
    else:
        audit["native_relative"] = 1e-5
    with pytest.raises(ValueError, match="RAW_REFERENCE_GATE_DIFFERS"):
        reference_gate(raw, audit)
    raw["reference_qualified"] = False
    assert not reference_gate(raw, audit)["qualified"]


def test_comparison_checker_uses_saved_vectors_and_energy():
    raw = dict(
        status="P3_P4_SMALL_CHANGE_LIMITED",
        errors={},
        energy_pairs={},
        samples={},
        channels={},
        regions={},
        quadrature={},
        observables={},
        powers=dict(p3=[0] * 40, p4=[0] * 40, max_absolute=0),
    )
    def z(count):
        return [dict(real=1, imag=0) for _ in range(count)]
    for kind in ("total", "scattered"):
        raw["energy_pairs"][kind] = dict(p3=[1, 1], p4=[1, 1], difference=[0, 0])
        raw["quadrature"][kind] = dict(
            degree15=[0, 0],
            degree30=[0, 0],
            denominator_energy=[1, 1],
            normalized_absolute_difference=[0, 0],
        )
        for quantity in ("L2", "scaled_curl"):
            raw["errors"][kind + "_" + quantity] = record(1, 1, 0)
        raw["samples"][kind] = {p: dict(E=z(18), H_code=z(18)) for p in ("p3", "p4")}
        for quantity in ("E", "H_code"):
            key = kind + "_selected_" + quantity
            raw["errors"][key] = record(np.sqrt(18), np.sqrt(18), 0)
            for point in range(6):
                raw["errors"][key + "_point_" + str(point)] = record(
                    np.sqrt(3), np.sqrt(3), 0
                )
    for kind in ("total", "outgoing", "boundary_outgoing", "scattered"):
        error = record(np.sqrt(40), np.sqrt(40), 0)
        raw["channels"][kind] = dict(
            p3=z(40), p4=z(40), difference=[dict(real=0, imag=0)] * 40, error=error
        )
        raw["errors"]["channels_" + kind] = error
    for name in ("R_total", "T_total", "A_balance", "A_volume"):
        raw["observables"][name] = dict(p3=0, p4=0, absolute=0)
    assert comparison_gate(raw)["small_change_signal"]
    corrupt = deepcopy(raw)
    corrupt["channels"]["outgoing"]["p3"][0]["imag"] = 0.1
    with pytest.raises(ValueError, match="CHANNEL_DIFFERENCE_CHANGED"):
        comparison_gate(corrupt)
    corrupt = deepcopy(raw)
    corrupt["energy_pairs"]["scattered"]["difference"][0] = -1
    with pytest.raises(ValueError, match="INVALID_RAW_ENERGY"):
        comparison_gate(corrupt)
