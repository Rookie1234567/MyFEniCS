"""A false saved PASS cannot override raw mismatch or unstable gradients."""

from benchmarks.neural_fe_calibration_gate_check import check_equivalence


def test_saved_pass_does_not_override_raw_equivalence_defect():
    record = dict(
        status="PASS",
        cache=dict(new_persistent_cache_bytes=1, all_points_retained=True),
        states=[
            dict(
                state="NONZERO",
                status="PASS",
                comparisons=dict(
                    trace=dict(absolute=1.0, reference_norm=1.0, passed=True)
                ),
                finite_difference=[],
                gradient_block_norms=dict(hidden=1, output=1, ports=1),
            )
        ],
    )
    assert check_equivalence(record)["status"] == "FAIL"


def test_finite_difference_and_absolute_zero_are_recomputed():
    state = dict(
        state="NONZERO",
        comparisons=dict(trace=dict(absolute=1e-13, reference_norm=0)),
        finite_difference=[
            dict(
                analytic=2.0,
                samples=[
                    dict(finite_difference=2.0),
                    dict(finite_difference=2.0),
                    dict(finite_difference=2.0),
                ],
            )
        ],
        gradient_block_norms=dict(hidden=1, output=1, ports=1),
    )
    record = dict(
        cache=dict(new_persistent_cache_bytes=1, all_points_retained=True),
        states=[state],
    )
    assert check_equivalence(record)["status"] == "PASS"
    state["finite_difference"][0]["samples"][1]["finite_difference"] = 3.0
    assert check_equivalence(record)["status"] == "FAIL"
