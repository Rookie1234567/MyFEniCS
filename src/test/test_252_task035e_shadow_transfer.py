from __future__ import annotations

import math
from types import SimpleNamespace

from basix.ufl import element
from mpi4py import MPI
import numpy as np
import pytest

from dolfinx import default_real_type, fem, mesh

from src.adaptivity.task035e_shadow_transfer import (
    _interpolate_nonmatching,
    _relative_coefficient_error,
    _relative_form_error,
    _require_world_communicator,
    _shadow_transition_identity,
)


def _polynomial(x: np.ndarray) -> np.ndarray:
    values = np.empty((3, x.shape[1]), dtype=np.complex128)
    values[0] = 1.0 + 0.25 * x[1] + 0.1j * x[2]
    values[1] = -0.4 * x[0] + 0.2 * x[2]
    values[2] = 0.3 * x[0] - 0.15j * x[1]
    return values


def _space(domain: mesh.Mesh, degree: int = 2):
    return fem.functionspace(
        domain,
        element(
            "N1curl",
            domain.basix_cell(),
            degree,
            dtype=default_real_type,
        ),
    )


def test_world_communicator_gate_accepts_dolfinx_duplicate() -> None:
    domain = mesh.create_unit_cube(
        MPI.COMM_WORLD,
        1,
        1,
        max(1, MPI.COMM_WORLD.size),
        cell_type=mesh.CellType.hexahedron,
    )
    relation = _require_world_communicator(domain.comm)
    assert relation in {MPI.IDENT, MPI.CONGRUENT}
    assert MPI.Comm.Compare(domain.comm, MPI.COMM_WORLD) == MPI.CONGRUENT


def test_world_communicator_gate_rejects_true_subcommunicator() -> None:
    if MPI.COMM_WORLD.size == 1:
        pytest.skip("a one-rank COMM_SELF is congruent to COMM_WORLD")
    with pytest.raises(ValueError, match="congruent duplicate"):
        _require_world_communicator(MPI.COMM_SELF)


def test_nonmatching_nedelec_roundtrip_preserves_field_and_curl() -> None:
    comm = MPI.COMM_WORLD
    coarse_mesh = mesh.create_box(
        comm,
        [np.zeros(3), np.ones(3)],
        [1, 1, max(1, comm.size)],
        cell_type=mesh.CellType.hexahedron,
    )
    fine_mesh = mesh.create_box(
        comm,
        [np.zeros(3), np.ones(3)],
        [2, 2, max(2, 2 * comm.size)],
        cell_type=mesh.CellType.hexahedron,
    )
    coarse_space = _space(coarse_mesh)
    fine_space = _space(fine_mesh)
    coarse = fem.Function(coarse_space)
    coarse.interpolate(_polynomial)
    coarse.x.scatter_forward()
    lifted = _interpolate_nonmatching(
        coarse,
        fine_space,
        name="task035e_test_lift",
        padding=1.0e-10,
    )
    round_trip = _interpolate_nonmatching(
        lifted,
        coarse_space,
        name="task035e_test_roundtrip",
        padding=1.0e-10,
    )
    coefficient = _relative_coefficient_error(coarse, round_trip)
    field = _relative_form_error(coarse, round_trip, curl=False)
    curl = _relative_form_error(coarse, round_trip, curl=True)
    assert coefficient[0] <= 5.0e-12
    assert field[0] <= 5.0e-12
    assert curl[0] <= 5.0e-12


def test_nonmatching_transfer_rejects_nonfinite_source() -> None:
    domain = mesh.create_unit_cube(
        MPI.COMM_WORLD,
        1,
        1,
        max(1, MPI.COMM_WORLD.size),
        cell_type=mesh.CellType.hexahedron,
    )
    source = fem.Function(_space(domain))
    source.x.petsc_vec.getArray()[0] = np.nan
    with pytest.raises(ValueError, match="invalid"):
        _relative_coefficient_error(source, fem.Function(_space(domain)))


def test_module_does_not_accept_endpoint_or_reference_inputs() -> None:
    import inspect

    from src.adaptivity import task035e_shadow_transfer as module

    signature = inspect.signature(
        module.transfer_task035e_snapshot_to_shadow_p6
    )
    forbidden = {
        "reference",
        "reference_values",
        "actual_goal_delta",
        "shadow_endpoint",
    }
    assert forbidden.isdisjoint(signature.parameters)
    assert math.isclose(
        float(signature.parameters["relative_tolerance"].default),
        5.0e-9,
    )
    assert not hasattr(SimpleNamespace(), "hidden_reference")


def test_shadow_kind_uses_executed_forest_and_degree_identities() -> None:
    current_forest = "1" * 64
    current_hanging = "2" * 64
    current_degree = "3" * 64

    p_shadow = _shadow_transition_identity(
        current_forest_sha256=current_forest,
        current_hanging_sha256=current_hanging,
        current_degree_sha256=current_degree,
        shadow_forest_sha256=current_forest,
        shadow_hanging_sha256=current_hanging,
        shadow_degree_sha256="4" * 64,
    )
    assert p_shadow["observed_shadow_kind"] == "p-shadow"
    assert p_shadow["same_forest_geometry"] is True
    assert p_shadow["same_degree_plan"] is False

    h_shadow = _shadow_transition_identity(
        current_forest_sha256=current_forest,
        current_hanging_sha256=current_hanging,
        current_degree_sha256=current_degree,
        shadow_forest_sha256="5" * 64,
        shadow_hanging_sha256="6" * 64,
        shadow_degree_sha256="7" * 64,
    )
    assert h_shadow["observed_shadow_kind"] == "h-shadow"
    assert h_shadow["same_forest_geometry"] is False

    no_op = _shadow_transition_identity(
        current_forest_sha256=current_forest,
        current_hanging_sha256=current_hanging,
        current_degree_sha256=current_degree,
        shadow_forest_sha256=current_forest,
        shadow_hanging_sha256=current_hanging,
        shadow_degree_sha256=current_degree,
    )
    assert no_op["observed_shadow_kind"] == "no-op-shadow"
    assert no_op["whole_plan_file_sha_used_for_shadow_classification"] is False
