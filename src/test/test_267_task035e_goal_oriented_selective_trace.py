from __future__ import annotations

from mpi4py import MPI
import numpy as np

from src.adaptivity.dyadic_hexa_broken_mesh import (
    build_broken_dyadic_hexa_carrier,
)
from src.adaptivity.dyadic_hexa_refinement import (
    build_root_dyadic_hexa_forest,
)
from src.adaptivity.goal_oriented_selective_trace import (
    build_p5_to_global_p6_root_injection,
    build_periodic_face_quotient,
    decompose_face_residual,
    signed_orbit_pairings,
)
from src.adaptivity.hcurl_broken_trace_graph import (
    build_broken_hexa_trace_constraint_authority,
)


def _periodic_authorities():
    boxes = [
        (
            float(i),
            float(j),
            0.0,
            float(i + 1),
            float(j + 1),
            1.0,
        )
        for j in range(2)
        for i in range(2)
    ]
    forest = build_root_dyadic_hexa_forest(
        boxes,
        [1] * len(boxes),
        periodic_axes=("x", "y"),
    )
    carrier = build_broken_dyadic_hexa_carrier(
        forest,
        comm=MPI.COMM_WORLD,
    )
    kwargs = {
        "phase_x": np.exp(0.2j),
        "phase_y": np.exp(-0.3j),
    }
    coarse = build_broken_hexa_trace_constraint_authority(
        forest,
        carrier,
        degree=5,
        **kwargs,
    )
    fine = build_broken_hexa_trace_constraint_authority(
        forest,
        carrier,
        degree=6,
        **kwargs,
    )
    all_faces = tuple(
        sorted(
            entity.geometry_key
            for entity in fine.entities
            if entity.dimension == 2
        )
    )
    selective = build_broken_hexa_trace_constraint_authority(
        forest,
        carrier,
        degree=5,
        selected_p6_face_geometry_keys=all_faces,
        **kwargs,
    )
    return coarse, selective, fine


def test_periodic_face_quotient_closes_signed_pairing() -> None:
    coarse, selective, fine = _periodic_authorities()
    injection = build_p5_to_global_p6_root_injection(coarse, fine)
    quotient = build_periodic_face_quotient(
        coarse,
        selective,
        fine,
        injection,
    )
    assert injection.audit["pass"] is True
    assert quotient.audit["pass"] is True
    assert (
        quotient.audit["physical_face_count"]
        > quotient.audit["periodic_physical_face_orbit_count"]
    )
    assert quotient.generators.shape[1] == (
        20 * quotient.audit["periodic_physical_face_orbit_count"]
    )
    assert injection.audit["dimension_delta"] > quotient.generators.shape[1]
    assert quotient.audit["B_to_S_to_F_composition_error_max"] <= 5.0e-10
    assert quotient.audit["S_independent_trace_rows"] == (
        quotient.audit["B_independent_trace_rows"]
        + quotient.generators.shape[1]
    )
    assert quotient.audit["F_independent_trace_rows"] > (
        quotient.audit["S_independent_trace_rows"]
    )

    rng = np.random.default_rng(935)
    coefficients = (
        rng.standard_normal(quotient.generators.shape[1])
        + 1j * rng.standard_normal(quotient.generators.shape[1])
    )
    residual = np.asarray(quotient.generators @ coefficients)
    partition = decompose_face_residual(quotient, residual)
    assert partition.audit["pass"] is True
    np.testing.assert_allclose(
        partition.face_projection,
        residual,
        rtol=2.0e-10,
        atol=2.0e-10,
    )
    assert np.linalg.norm(partition.unexplained) <= 2.0e-9

    adjoint = (
        rng.standard_normal(quotient.generators.shape[0])
        + 1j * rng.standard_normal(quotient.generators.shape[0])
    )
    pairings = signed_orbit_pairings(
        quotient,
        partition,
        adjoint,
    )
    np.testing.assert_allclose(
        np.sum(pairings),
        np.vdot(adjoint, residual),
        rtol=2.0e-10,
        atol=2.0e-10,
    )
    coarse_cross = (
        injection.trace_injection.conj().T
        @ quotient.generators
    )
    assert (
        0.0
        if coarse_cross.nnz == 0
        else np.max(np.abs(coarse_cross.data))
    ) <= 5.0e-10
