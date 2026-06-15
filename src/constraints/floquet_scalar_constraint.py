from __future__ import annotations

import numpy as np
from dolfinx import fem

from ..common.config import SimulationConfig
from .floquet_constraint import FloquetConstraintData, _local_dof_global_info


def _boundary_dofs(V, mesh_data, tag: int) -> np.ndarray:
    msh = mesh_data.mesh
    facet_dim = msh.topology.dim - 1
    facets = np.asarray(mesh_data.facet_tags.find(tag), dtype=np.int32)
    if len(facets) == 0:
        raise RuntimeError(f"No Floquet facets were found for tag={tag}.")
    dofs = fem.locate_dofs_topological(V, facet_dim, facets)
    dofs = np.unique(np.asarray(dofs, dtype=np.int32))
    if len(dofs) == 0:
        raise RuntimeError(f"No scalar dofs were found on Floquet tag={tag}.")
    return dofs


def build_scalar_floquet_constraints(V, mesh_data, cfg: SimulationConfig) -> FloquetConstraintData:
    """Constrain scalar right-boundary dofs to scalar left-boundary dofs.

    This is the serial manual counterpart of the scalar periodic constraint used
    for TE Ez.  Unlike Nedelec edge dofs, scalar Lagrange dofs do not carry an
    orientation sign, so the constraint is simply Ez_right = phase * Ez_left for
    matching y coordinates.
    """
    comm = mesh_data.mesh.comm
    if comm.size != 1:
        raise RuntimeError(
            "The scalar manual Floquet constraint builder is serial-only. "
            "Use constraint_backend='mpc_official' for MPI TE runs."
        )

    left_dofs = _boundary_dofs(V, mesh_data, cfg.tags.left)
    right_dofs = _boundary_dofs(V, mesh_data, cfg.tags.right)
    if len(left_dofs) != len(right_dofs):
        raise RuntimeError(
            f"Scalar Floquet dof counts differ: left={len(left_dofs)}, right={len(right_dofs)}."
        )

    coords = V.tabulate_dof_coordinates()
    left_order = np.lexsort((coords[left_dofs, 0], coords[left_dofs, 1]))
    right_order = np.lexsort((coords[right_dofs, 0], coords[right_dofs, 1]))
    left_dofs = left_dofs[left_order]
    right_dofs = right_dofs[right_order]
    left_y = coords[left_dofs, 1]
    right_y = coords[right_dofs, 1]

    max_pair_y_error = float(np.max(np.abs(left_y - right_y))) if len(left_y) else 0.0
    if max_pair_y_error > 1e-10:
        raise RuntimeError(
            "Scalar Floquet left/right dofs cannot be paired by y coordinate; "
            f"max error={max_pair_y_error:g}."
        )

    global_left, owners_left, _ = _local_dof_global_info(V, left_dofs)
    coefficients = np.full(len(right_dofs), cfg.floquet_phase, dtype=np.complex128)
    offsets = np.arange(len(right_dofs) + 1, dtype=np.int32)
    orientation_factors = np.ones(len(right_dofs), dtype=np.complex128)

    return FloquetConstraintData(
        slave_dofs=np.asarray(right_dofs, dtype=np.int32),
        master_dofs=np.asarray(global_left, dtype=np.int64),
        coefficients=coefficients,
        offsets=offsets,
        phase=cfg.floquet_phase,
        orientation_factors=orientation_factors,
        max_pair_y_error=max_pair_y_error,
        max_probe_error=0.0,
        master_owners=np.asarray(owners_left, dtype=np.int32),
        master_dofs_are_global=False,
    )
