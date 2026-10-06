import pytest

from src.runners.task40_v10_worker import _single_side_diffraction_order_count_passed


@pytest.mark.parametrize(
    ("reported_orders", "total_port_modes", "expected"),
    (
        (266, 532, True),
        (532, 532, False),
        (170, 340, True),
        (266, 340, False),
        (170, 532, False),
        (0, 0, False),
    ),
)
def test_output_gate_compares_single_face_orders_to_half_the_port_modes(
    reported_orders, total_port_modes, expected
):
    assert _single_side_diffraction_order_count_passed(
        {"diffraction_channel_count": reported_orders}, total_port_modes
    ) is expected
