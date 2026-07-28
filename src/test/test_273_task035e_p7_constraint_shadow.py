from __future__ import annotations

import os

from mpi4py import MPI
import numpy as np
import pytest

from src.adaptivity.exact_sequence_variable_p import (
    HexaEntityDegreeMap,
)
from src.adaptivity.task035e_p7_constraint_shadow import (
    audit_mixed_p7_floquet_entity,
    build_mixed_selective_p7_shadow_space,
    build_p7_shadow_hanging_closure,
)


_MIXED_DEGREES = HexaEntityDegreeMap.dimension_uniform(
    edge_degree=4,
    face_degree=5,
    cell_degree=6,
)
_CELL_INFO = (
    1
    | (2 << 1)
    | (1 << (3 * 3 + 1))
    | (1 << (18 + 1))
    | (1 << (18 + 9))
)


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 1,
    reason="serial mathematical component contract",
)
@pytest.mark.parametrize("degree", (4, 5, 6))
def test_real_p_to_p7_hanging_complement_closes(degree: int) -> None:
    closure = build_p7_shadow_hanging_closure(degree)
    audit = closure.audit

    assert audit["component_pass"] is True
    assert audit["source_degree"] == degree
    assert audit["target_degree"] == 7
    assert audit["hcurl_hanging_injection_error_max"] < 5.0e-11
    assert audit["h1_hanging_injection_error_max"] < 5.0e-11
    assert audit["fine_gradient_injection_error_max"] < 5.0e-11
    assert audit["hcurl_complement_decomposition_error_max"] < 5.0e-11
    assert audit["h1_complement_decomposition_error_max"] < 5.0e-11
    assert audit["hcurl_d4_injection_error_max"] < 5.0e-11
    assert audit["h1_d4_injection_error_max"] < 5.0e-11
    assert audit["d4_action_count"] == 8
    assert audit["production_degrees_unchanged"] == [4, 5, 6]
    assert audit["p7_rows_globally_numbered"] is False
    assert audit["shadow_only"] is True
    assert audit["selectable_as_production"] is False


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 1,
    reason="serial mathematical component contract",
)
def test_mixed_p456_entity_injection_is_exact_sequence_closed() -> None:
    space = build_mixed_selective_p7_shadow_space(
        _MIXED_DEGREES,
        requested_edges=(0,),
        requested_faces=(5,),
        cell_infos=(0, _CELL_INFO),
    )
    audit = space.audit

    assert audit["component_pass"] is True
    assert audit["degree_map"]["signature"] == _MIXED_DEGREES.signature
    assert audit["selected_edges"] == [0]
    assert set(audit["selected_faces"]).issuperset({5})
    assert len(audit["selected_faces"]) == 3
    assert audit["checks"]["edge_to_face_closure_complete"] is True
    assert audit["cell_selected_by_exact_sequence_closure"] is True
    assert audit["hcurl_injection_direct_error_max"] < 5.0e-11
    assert audit["h1_injection_direct_error_max"] < 5.0e-11
    assert audit["gradient_injection_commuting_error_max"] < 5.0e-11
    assert audit["gradient_range_error_max"] < 5.0e-11
    assert audit["hcurl_orientation_commuting_error_max"] < 5.0e-11
    assert audit["h1_orientation_commuting_error_max"] < 5.0e-11
    assert audit["gradient_rank"] == audit["shadow_h1_dimension"] - 1
    assert audit["p7_rows_globally_numbered"] is False
    assert audit["production_degrees_unchanged"] == [4, 5, 6]


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 1,
    reason="serial mathematical component contract",
)
def test_actual_floquet_phase_closes_mixed_entity_complements() -> None:
    for degree in (4, 5, 6):
        for dimension, phase in (
            (1, np.exp(0.2j)),
            (2, np.exp(-0.3j)),
        ):
            audit = audit_mixed_p7_floquet_entity(
                degree,
                dimension,
                phase,
            )
            assert audit["component_pass"] is True
            assert audit["maximum_injection_error"] < 5.0e-11
            assert audit["maximum_complement_error"] < 5.0e-11
            assert audit["p7_rows_globally_numbered"] is False


@pytest.mark.skipif(
    os.environ.get("MYFENICS_RUN_TASK035E_P7_CONSTRAINT_MPI8") != "1"
    or MPI.COMM_WORLD.size != 8,
    reason="set the opt-in flag and launch this fixture with MPI8",
)
def test_mixed_p7_constraint_component_has_one_mpi8_digest() -> None:
    comm = MPI.COMM_WORLD
    space = build_mixed_selective_p7_shadow_space(
        _MIXED_DEGREES,
        requested_edges=(0,),
        requested_faces=(5,),
        cell_infos=(0, _CELL_INFO),
    )
    hanging = tuple(
        build_p7_shadow_hanging_closure(degree).audit[
            "component_sha256"
        ]
        for degree in (4, 5, 6)
    )
    packet = (
        space.audit["component_sha256"],
        hanging,
        space.audit["gradient_range_error_max"],
        space.audit["hcurl_orientation_commuting_error_max"],
    )
    packets = comm.allgather(packet)

    assert len(packets) == 8
    assert len(set(packets)) == 1
    assert space.audit["component_pass"] is True
    assert space.audit["p7_rows_globally_numbered"] is False
