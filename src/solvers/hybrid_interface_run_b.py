"""Small Run-B glue for the reviewed V1-2/V1-3 research path."""

from __future__ import annotations

from typing import Any

import numpy as np
from petsc4py import PETSc

from .hybrid_interface_schur import (
    PetscDistributedPetrovAction,
    PetscFixedProjectedGroupInverse,
    build_fixed_projected_group_inverse,
)
from .hybrid_side_impedance import build_level_a_oracle

__all__ = (
    "build_v1_3_projected_group_inverse",
    "build_v1_3_projected_transmission",
)


def build_v1_3_projected_group_inverse(
    template: PETSc.Vec,
    base_factor: Any,
    petrov: PetscDistributedPetrovAction,
) -> PetscFixedProjectedGroupInverse:
    """Build ``B + U V^H`` inverse from a distributed Petrov audit.

    ``U`` is the exact-minus-scalar span action and ``V`` is formed by the
    carrier as ``Y G^-H`` using its stable Gram SVD.  The returned carrier
    borrows ``base_factor`` and must be destroyed before that factor.
    """

    factors = petrov.projected_woodbury_factors()
    return build_fixed_projected_group_inverse(
        template,
        base_factor,
        factors["U"],
        factors["V"],
    )


def _embed_gamma_factors(
    group_rows: np.ndarray,
    gamma_rows: np.ndarray,
    gamma_factors: dict[str, np.ndarray],
) -> tuple[np.ndarray, np.ndarray]:
    """Embed one owner-local Gamma correction in its group-row order."""

    rows = np.asarray(group_rows, dtype=np.int64)
    gamma = np.asarray(gamma_rows, dtype=np.int64)
    if rows.ndim != 1 or gamma.ndim != 1 or len(np.unique(rows)) != len(rows):
        raise ValueError("projected group rows must be unique one-dimensional arrays")
    positions = {int(row): index for index, row in enumerate(rows)}
    if any(int(row) not in positions for row in gamma):
        raise ValueError("projected Gamma rows are not contained in group rows")
    u_gamma = np.asarray(gamma_factors["U"], dtype=np.complex128)
    v_gamma = np.asarray(gamma_factors["V"], dtype=np.complex128)
    if u_gamma.shape != v_gamma.shape or u_gamma.shape[0] != len(gamma):
        raise ValueError("projected Gamma factors have the wrong local shape")
    u_group = np.zeros((len(rows), u_gamma.shape[1]), dtype=np.complex128)
    v_group = np.zeros_like(u_group)
    for gamma_index, row in enumerate(gamma):
        group_index = positions[int(row)]
        u_group[group_index] = u_gamma[gamma_index]
        v_group[group_index] = v_gamma[gamma_index]
    return u_group, v_group


def build_v1_3_projected_transmission(
    *,
    bare_f: PETSc.Mat,
    group_rows: tuple[np.ndarray, ...] | list[np.ndarray],
    interface_masses: tuple[Any, Any] | list[Any],
    beta: complex,
    group_audit: dict[str, Any],
    petrov_actions: tuple[PetscDistributedPetrovAction, ...]
    | list[PetscDistributedPetrovAction],
) -> tuple[Any, Any, dict[str, Any]]:
    """Build the conditional V1-3 projected sweep over one factor set.

    The existing Level-A builder constructs the three scalar base factors and
    the PETSc VecScatter sweep.  This opt-in factory replaces only the three
    local solves with fixed Woodbury inverses whose owner-local corrections
    come from the reviewed Petrov carriers.  The base factors and projected
    inverses are never a six-factor resident set: all three inverses borrow
    the same three scalar factors and the owner destroys sweep, inverses, then
    factors in that order.
    """

    if len(group_rows) != 3 or len(petrov_actions) != 3:
        raise ValueError("V1-3 projected transmission needs three groups/actions")
    gamma_rows_list: list[np.ndarray] = []
    for action in petrov_actions:
        rows = action.gamma_rows_local
        if rows is None:
            raise ValueError("Petrov carriers must expose public Gamma row identities")
        gamma_rows_list.append(np.asarray(rows, dtype=np.int64))
    gamma_rows = tuple(gamma_rows_list)
    inverses: list[PetscFixedProjectedGroupInverse] = []

    def projected_factory(
        base_factors: Any,
    ) -> tuple[tuple[Any, ...], tuple[Any, ...], dict[str, Any]]:
        local_solves: list[Any] = []
        try:
            for group, factor in enumerate(base_factors):
                operator = factor.operator
                if operator is None:
                    raise RuntimeError("base factor has no retained solve operator")
                template = operator.createVecRight()
                try:
                    projected_factors = petrov_actions[
                        group
                    ].projected_woodbury_factors()
                    local_u, local_v = _embed_gamma_factors(
                        np.asarray(group_rows[group], dtype=np.int64),
                        gamma_rows[group],
                        projected_factors,
                    )
                    inverse = build_fixed_projected_group_inverse(
                        template, factor, local_u, local_v
                    )
                finally:
                    template.destroy()
                inverses.append(inverse)
                local_solves.append(inverse.apply)
            return (
                tuple(local_solves),
                tuple(inverses),
                {
                    "v1_3_projected": True,
                    "projected_factor_count_ready": len(inverses),
                    "simultaneous_factor_count_max": 3,
                    "nested_ksp_count": 0,
                    "fe_numeric_allgather": False,
                },
            )
        except Exception:
            for inverse in reversed(inverses):
                inverse.destroy()
            inverses.clear()
            raise

    try:
        return build_level_a_oracle(
            bare_f=bare_f,
            group_rows=group_rows,
            interface_masses=interface_masses,
            beta=beta,
            group_audit=group_audit,
            _projected_local_solve_factory=projected_factory,
        )
    except Exception:
        for inverse in reversed(inverses):
            inverse.destroy()
        raise
