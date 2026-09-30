"""Native-call cutoff and pre-worker p4 provenance survive interruption."""

import pytest

from src.runners.feinn_workflow import authority_watchdog_window, bind_authority_packet


@pytest.mark.parametrize("delay", [0, 20, 100])
def test_authority_native_watchdog_charges_import_delay(delay):
    manifest = dict(
        supervision_budget_origin_monotonic=1000, supervised_limit_seconds=3600
    )
    window = authority_watchdog_window(manifest, 1000 + delay)
    assert 1000 + delay + window == 4450
    assert 4600 - (1000 + delay + window) == 150
    with pytest.raises(RuntimeError, match="V7_BUDGET_RESERVE_UNAVAILABLE"):
        authority_watchdog_window(manifest, 4450)


def test_interrupted_p4_manifest_uses_actual_packet_before_worker():
    state = dict(actual_operator_packet_sha256="p3", gram_sha256=None)
    packet = dict(
        files=dict(native=dict(sha256="p4")),
        result=dict(
            identity=dict(
                degree=4,
                mesh_coordinates_sha256="mesh",
                cell_tags_sha256="tags",
                mode_manifest_sha256="modes",
            )
        ),
    )
    bind_authority_packet(state, packet)
    assert (
        state["physical_model_sha256"] == state["actual_operator_packet_sha256"] == "p4"
    )
    assert state["p3_dependency_native_sha256"] == "p3"
    assert state["actual_discretization_degree"] == 4
    assert state["gram_sha256"] is None
    packet["result"]["identity"]["degree"] = 3
    with pytest.raises(ValueError, match="AUTHORITY_PACKET_MUST_BE_P4"):
        bind_authority_packet(state, packet)
