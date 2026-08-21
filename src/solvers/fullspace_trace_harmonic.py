"""Owner-local trace-harmonic definition for the adaptive D1 lane.

The auxiliary form is the fixed coercive Maxwell energy

    (mu_r**-1 curl(u), curl(v))_Omega_i
    + k0**2 (abs(epsilon_r) u, v)_Omega_i.

This module only defines the local form and the small algebra used by the
p2/p3 fixture oracle.  The fixture may assemble small PETSc matrices.  A
future p6 backend must keep the same definition while applying owner-local
matrix-free actions; it must not depend on a global AIJ, Schur complement, or
growing factor.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Any, Mapping

import numpy as np
import ufl

from dolfinx import mesh

from .fullspace_mpc_action import build_fullspace_mpc_form_action


D1_PROFILE = "adaptive_trace_harmonic_two_level_v1"
D1_FIXED_TRACE_RANK = 16
D1_AUXILIARY_FORM = "curl_curl_plus_k0_squared_abs_epsilon_mass"


def _material_epsilon(cfg: Any, tag: int) -> complex:
    tag = int(tag)
    if tag == int(cfg.tags.air):
        return complex(cfg.eps_air)
    if tag == int(cfg.tags.substrate):
        return complex(cfg.eps_substrate)
    if tag == int(cfg.tags.grating):
        return complex(cfg.eps_grating)
    raise ValueError(f"unsupported physical cell tag {tag}")


def _physical_cell_tags(topology: Any, mesh_data: Any, slab_id: int) -> Any:
    """Filter existing owned cell tags by the real interface-z partition."""

    if int(slab_id) not in (0, 1):
        raise ValueError("D1 has exactly two slab ids")
    msh = topology.mesh
    cell_map = msh.topology.index_map(msh.topology.dim)
    owned_count = int(cell_map.size_local)
    indices = np.asarray(mesh_data.cell_tags.indices, dtype=np.int32)
    values = np.asarray(mesh_data.cell_tags.values, dtype=np.int32)
    owned = indices < owned_count
    owned_indices = indices[owned]
    owned_values = values[owned]
    slab_ids = np.asarray(topology.owned_slab_ids, dtype=np.int8)
    selected = slab_ids[owned_indices] == int(slab_id)
    selected_indices = owned_indices[selected]
    selected_values = owned_values[selected]
    order = np.argsort(selected_indices, kind="stable")
    return mesh.meshtags(
        msh,
        msh.topology.dim,
        selected_indices[order],
        selected_values[order],
    )


def _physical_tags(cfg: Any) -> tuple[int, ...]:
    return tuple(
        sorted(
            {
                int(cfg.tags.air),
                int(cfg.tags.substrate),
                int(cfg.tags.grating),
            }
        )
    )


def _tangential_trace(value: Any) -> Any:
    plus = value("+")
    return ufl.as_vector((plus[0], plus[1], 0.0))


class TraceHarmonicDefinition:
    """Forms and audits for one real owner-local slab/interface pair."""

    __slots__ = (
        "topology",
        "mesh_data",
        "raw_function_space",
        "mpc",
        "slab_id",
        "cell_tags",
        "auxiliary_form",
        "interface_mass_form",
        "_audit",
    )

    def __init__(
        self,
        topology: Any,
        mesh_data: Any,
        raw_function_space: Any,
        mpc: Any,
        slab_id: int,
    ) -> None:
        self.topology = topology
        self.mesh_data = mesh_data
        self.raw_function_space = raw_function_space
        self.mpc = mpc
        self.slab_id = int(slab_id)
        self.cell_tags = _physical_cell_tags(topology, mesh_data, self.slab_id)
        msh = topology.mesh

        u = ufl.TrialFunction(raw_function_space)
        v = ufl.TestFunction(raw_function_space)
        dx = ufl.Measure("dx", domain=msh, subdomain_data=self.cell_tags)
        mu_r = complex(topology.cfg.mu_r)
        k0_squared = float(topology.cfg.k0) ** 2
        curl_term = 0
        mass_term = 0
        for tag in _physical_tags(topology.cfg):
            epsilon_abs = abs(_material_epsilon(topology.cfg, tag))
            cell_measure = dx(tag)
            curl_term += (1.0 / mu_r) * ufl.inner(
                ufl.curl(u), ufl.curl(v)
            ) * cell_measure
            mass_term += (
                k0_squared
                * epsilon_abs
                * ufl.inner(u, v)
                * cell_measure
            )
        self.auxiliary_form = curl_term + mass_term

        u_t = _tangential_trace(u)
        v_t = _tangential_trace(v)
        dS = ufl.Measure(
            "dS",
            domain=msh,
            subdomain_data=topology.interface_facet_tags,
        )
        interface_mass = 0
        for tag, _lower, _upper in topology.global_material_pairs:
            interface_mass += ufl.inner(u_t, v_t) * dS(int(tag))
        self.interface_mass_form = interface_mass
        self._audit = MappingProxyType(
            {
                "schema": "fullspace.trace-harmonic-definition.v1",
                "profile": D1_PROFILE,
                "slab_id": self.slab_id,
                "slab_partition": "owned_cells_from_cfg.interface_z",
                "auxiliary_form": D1_AUXILIARY_FORM,
                "coercive_coefficient": "k0**2*abs(epsilon_r(x))",
                "source_independent": True,
                "restriction_prolongation": "owner_active_rows_unit_weight_euclidean",
                "interface_mass": "broken_tangential_facet_mass_dS",
                "phase_application": "finalized_floquet_mpc_once",
                "slave_rows_excluded_from_action": True,
                "fixture_assembled_oracle": "p2_p3_only",
                "future_p6_backend": "owner_local_matrix_free",
                "global_numeric_allgather": False,
                "global_aij_materialized": False,
                "global_schur_materialized": False,
                "growing_factor_materialized": False,
            }
        )

    @property
    def audit(self) -> Mapping[str, object]:
        return self._audit

    def build_actions(self) -> tuple[Any, Any]:
        """Build reusable actions; no assembled matrix is retained here."""

        auxiliary = build_fullspace_mpc_form_action(
            self.auxiliary_form,
            self.raw_function_space,
            mpc=self.mpc,
            slave_row_identity=False,
        )
        interface_mass = build_fullspace_mpc_form_action(
            self.interface_mass_form,
            self.raw_function_space,
            mpc=self.mpc,
            slave_row_identity=False,
        )
        return auxiliary, interface_mass


def build_trace_harmonic_definition(
    topology: Any,
    mesh_data: Any,
    raw_function_space: Any,
    mpc: Any,
    slab_id: int,
) -> TraceHarmonicDefinition:
    """Build the fixed D1 forms for one real slab."""

    return TraceHarmonicDefinition(
        topology,
        mesh_data,
        raw_function_space,
        mpc,
        slab_id,
    )


def harmonic_extension_from_blocks(
    matrix: np.ndarray,
    trace_rows: np.ndarray,
    trace_values: np.ndarray,
    interior_rows: np.ndarray | None = None,
) -> np.ndarray:
    """Return the fixture-only minimum-energy extension from a local block.

    ``matrix`` contains only interior and active trace rows.  External shell
    rows are deliberately not accepted.  The p2/p3 test uses this routine
    after independently assembling the small local block; a future p6 path
    must replace the dense solve with an owner-local backend without changing
    the boundary-value definition.
    """

    block = np.asarray(matrix, dtype=np.complex128)
    traces = np.asarray(trace_rows, dtype=np.int64)
    values = np.asarray(trace_values, dtype=np.complex128)
    if block.ndim != 2 or block.shape[0] != block.shape[1]:
        raise ValueError("harmonic block must be square")
    if traces.ndim != 1 or values.ndim != 1 or traces.size != values.size:
        raise ValueError("trace rows and values have incompatible shapes")
    if traces.size == 0 or np.any(traces < 0) or np.any(traces >= block.shape[0]):
        raise ValueError("trace rows are outside the local harmonic block")
    if np.unique(traces).size != traces.size:
        raise ValueError("trace rows contain duplicates")
    if not np.all(np.isfinite(block)) or not np.all(np.isfinite(values)):
        raise ValueError("harmonic input is non-finite")
    if interior_rows is None:
        interior = np.asarray(
            [row for row in range(block.shape[0]) if row not in set(traces)],
            dtype=np.int64,
        )
    else:
        interior = np.asarray(interior_rows, dtype=np.int64)
    if interior.size and (
        np.any(interior < 0)
        or np.any(interior >= block.shape[0])
        or np.intersect1d(interior, traces).size
        or np.unique(interior).size != interior.size
    ):
        raise ValueError("interior rows do not close the local block")
    result = np.zeros(block.shape[0], dtype=np.complex128)
    result[traces] = values
    if interior.size:
        interior_block = block[np.ix_(interior, interior)]
        coupling = block[np.ix_(interior, traces)]
        result[interior] = np.linalg.solve(interior_block, -coupling @ values)
    if not np.all(np.isfinite(result)):
        raise FloatingPointError("harmonic extension is non-finite")
    return result


def generalized_trace_eigenpairs(
    stiffness: np.ndarray,
    mass: np.ndarray,
    *,
    rank: int = D1_FIXED_TRACE_RANK,
) -> tuple[np.ndarray, np.ndarray]:
    """Solve the small fixture generalized problem with fixed rank selection."""

    stiffness = np.asarray(stiffness, dtype=np.complex128)
    mass = np.asarray(mass, dtype=np.complex128)
    if (
        stiffness.ndim != 2
        or stiffness.shape[0] != stiffness.shape[1]
        or mass.shape != stiffness.shape
    ):
        raise ValueError("generalized eigenproblem shapes do not close")
    if not np.all(np.isfinite(stiffness)) or not np.all(np.isfinite(mass)):
        raise ValueError("generalized eigenproblem is non-finite")
    chol = np.linalg.cholesky(mass)
    whitened = np.linalg.solve(chol, stiffness)
    whitened = np.linalg.solve(chol.conj(), whitened.T).T
    eigenvalues, whitened_vectors = np.linalg.eigh(whitened)
    vectors = np.linalg.solve(chol.conj().T, whitened_vectors)
    order = np.argsort(eigenvalues, kind="stable")
    eigenvalues = np.asarray(eigenvalues[order].real, dtype=np.float64)
    vectors = np.asarray(vectors[:, order], dtype=np.complex128)
    for column in range(vectors.shape[1]):
        nonzero = np.flatnonzero(np.abs(vectors[:, column]) > 1.0e-14)
        if nonzero.size:
            pivot = int(nonzero[0])
            vectors[:, column] *= np.exp(-1j * np.angle(vectors[pivot, column]))
            if vectors[pivot, column].real < 0.0:
                vectors[:, column] *= -1.0
    selected = min(int(rank), vectors.shape[1])
    vectors = vectors[:, :selected]
    eigenvalues = eigenvalues[:selected]
    return eigenvalues, vectors


__all__ = [
    "D1_AUXILIARY_FORM",
    "D1_FIXED_TRACE_RANK",
    "D1_PROFILE",
    "TraceHarmonicDefinition",
    "build_trace_harmonic_definition",
    "generalized_trace_eigenpairs",
    "harmonic_extension_from_blocks",
]
