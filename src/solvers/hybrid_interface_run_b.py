"""Small Run-B glue for the reviewed V1-2/V1-3 research path."""

from __future__ import annotations

from collections.abc import Callable, Mapping
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
    "build_v2_packet_projected_transmission",
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


def _build_projected_transmission(
    *,
    bare_f: PETSc.Mat,
    group_rows: tuple[np.ndarray, ...] | list[np.ndarray],
    interface_masses: tuple[Any, Any] | list[Any],
    beta: complex,
    group_audit: dict[str, Any],
    gamma_rows: tuple[np.ndarray, ...] | list[np.ndarray],
    gamma_factor_getter: Callable[[int], Mapping[str, np.ndarray]],
    projected_diagnostics: Mapping[str, Any],
) -> tuple[Any, Any, dict[str, Any]]:
    """Build one projected sweep from owner-local Gamma factor payloads.

    The existing Level-A builder constructs the three scalar base factors and
    the PETSc VecScatter sweep.  Only the source of the owner-local Gamma
    corrections differs between the V1 Petrov route and the V2 packet route.
    """

    if len(group_rows) != 3 or len(gamma_rows) != 3:
        raise ValueError("projected transmission needs three groups/Gamma payloads")
    gamma_rows = tuple(np.asarray(rows, dtype=np.int64) for rows in gamma_rows)
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
                    projected_factors = gamma_factor_getter(group)
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
                    "projected_factor_count_ready": len(inverses),
                    "simultaneous_factor_count_max": 3,
                    "nested_ksp_count": 0,
                    "fe_numeric_allgather": False,
                    **dict(projected_diagnostics),
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
    """Build the existing conditional V1-3 projected sweep.

    The public V1 entry point and its diagnostics remain unchanged; only the
    owner-local factor plumbing is shared with the packet consumer below.
    """

    if len(group_rows) != 3 or len(petrov_actions) != 3:
        raise ValueError("V1-3 projected transmission needs three groups/actions")
    gamma_rows: list[np.ndarray] = []
    for action in petrov_actions:
        rows = action.gamma_rows_local
        if rows is None:
            raise ValueError("Petrov carriers must expose public Gamma row identities")
        gamma_rows.append(np.asarray(rows, dtype=np.int64))
    return _build_projected_transmission(
        bare_f=bare_f,
        group_rows=group_rows,
        interface_masses=interface_masses,
        beta=beta,
        group_audit=group_audit,
        gamma_rows=gamma_rows,
        gamma_factor_getter=lambda group: petrov_actions[
            group
        ].projected_woodbury_factors(),
        projected_diagnostics={"v1_3_projected": True},
    )


def build_v2_packet_projected_transmission(
    *,
    bare_f: PETSc.Mat,
    group_rows: tuple[np.ndarray, ...] | list[np.ndarray],
    interface_masses: tuple[Any, Any] | list[Any],
    beta: complex,
    group_audit: dict[str, Any],
    gamma_rows: tuple[np.ndarray, ...] | list[np.ndarray],
    gamma_factors: tuple[Mapping[str, np.ndarray], ...]
    | list[Mapping[str, np.ndarray]],
) -> tuple[Any, Any, dict[str, Any]]:
    """Build the research-only V2 packet consumer projected sweep.

    The packet already contains finalized owner-local raw ``U``/``V``.  This
    route builds only the three scalar base factors and three fixed projected
    inverses; it never constructs an exact-interface oracle or reads exact
    output vectors.
    """

    if len(gamma_factors) != 3:
        raise ValueError("V2 packet projected transmission needs three factor payloads")
    return _build_projected_transmission(
        bare_f=bare_f,
        group_rows=group_rows,
        interface_masses=interface_masses,
        beta=beta,
        group_audit=group_audit,
        gamma_rows=gamma_rows,
        gamma_factor_getter=lambda group: gamma_factors[group],
        projected_diagnostics={
            "v2_packet_projected": True,
            "packet_consumer": True,
            "scalar_base_factor_count": 3,
            "projected_inverse_factor_count": 3,
            "exact_interface_oracle_factor_count": 0,
            "full_side_exact_factor_count": 0,
            "global_direct_factor_count": 0,
            "nested_ksp_count": 0,
            "basis_global_replicated": False,
            "oracle_only": True,
        },
    )
