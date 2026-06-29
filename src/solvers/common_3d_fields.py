from __future__ import annotations

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from dolfinx import default_scalar_type, fem, geometry

from ..common.analytic_fields_3d import electric_field_code_values, fresnel_reference
from ..common.config_3d import SimulationConfig3D


def plane_wave_electric_field(V, cfg: SimulationConfig3D) -> fem.Function:
    field = fem.Function(V, name="E_exact")

    def eval_field(x):
        return electric_field_code_values(cfg, x.T).T

    field.interpolate(eval_field)
    field.x.scatter_forward()
    return field

def stage4_layered_background_field(V, cfg: SimulationConfig3D) -> fem.Function:
    """Stage-4 layered background used only inside the physical domain.

    The 2D scattered solver uses the background to form the grating contrast
    source and to reconstruct the physical total field.  It does not need a
    meaningful background field in the artificial PML.  Keeping the analytic
    Fresnel background in the PML made the ParaView total field look nonzero at
    the outer truncation boundary even when the scattered field was absorbed.
    For Stage 4, zero the background outside the physical z interval and let
    the PML display the solved scattered field only.
    """

    field = fem.Function(V, name="E_background_layered_physical_only")

    def eval_field(x):
        coords = x.T
        values = electric_field_code_values(cfg, coords)
        mask = (coords[:, 2] >= cfg.physical_z_min - 1.0e-12) & (
            coords[:, 2] <= cfg.physical_z_max + 1.0e-12
        )
        values[~mask] = 0.0
        return values.T

    field.interpolate(eval_field)
    field.x.scatter_forward()
    return field

def _add_reference_field_to_solution(E: fem.Function, cfg: SimulationConfig3D) -> None:
    """Reconstruct total field from a correction solve on E's own dof layout.

    ``dolfinx_mpc.LinearProblem`` may return a Function whose local vector
    layout differs from the original unconstrained function space used for
    boundary data.  Interpolate the analytic reference field on the solution
    space before adding it, so MPI-local array lengths always match.
    """

    reference = plane_wave_electric_field(E.function_space, cfg)
    if E.x.array.shape != reference.x.array.shape:
        raise RuntimeError(
            "Cannot reconstruct 3D reference-correction total field because the "
            "solution and reference-field local vectors still have different "
            f"shapes: {E.x.array.shape} vs {reference.x.array.shape}."
        )
    E.x.array[:] += reference.x.array
    E.x.scatter_forward()

def _combine_fields(primary: fem.Function, added: fem.Function, name: str) -> fem.Function:
    if primary.x.array.shape != added.x.array.shape:
        raise RuntimeError(
            f"Cannot combine fields {primary.name!r} and {added.name!r}; local vector shapes differ: "
            f"{primary.x.array.shape} vs {added.x.array.shape}."
        )
    total = fem.Function(primary.function_space, name=name)
    total.x.array[:] = primary.x.array
    total.x.array[:] += added.x.array
    total.x.scatter_forward()
    return total

def _function_coefficient_norm(field: fem.Function) -> float:
    index_map = field.function_space.dofmap.index_map
    block_size = field.function_space.dofmap.index_map_bs
    owned_size = index_map.size_local * block_size
    owned = np.asarray(field.x.array[:owned_size], dtype=np.complex128)
    local = float(np.real(np.vdot(owned, owned)))
    return float(np.sqrt(field.function_space.mesh.comm.allreduce(local, op=MPI.SUM)))

def _sample_field_at_points(function, points: np.ndarray) -> np.ndarray:
    msh = function.function_space.mesh
    comm = msh.comm
    points = np.asarray(points, dtype=np.float64).reshape((-1, 3))
    tree = geometry.bb_tree(msh, msh.topology.dim)
    candidates = geometry.compute_collisions_points(tree, points)
    collisions = geometry.compute_colliding_cells(msh, candidates, points)
    local_indices: list[int] = []
    local_cells: list[int] = []
    for i in range(len(points)):
        links = collisions.links(i)
        if len(links) >= 1:
            local_indices.append(i)
            local_cells.append(int(links[0]))

    if local_indices:
        local_points = points[np.asarray(local_indices, dtype=np.int32)]
        local_values = function.eval(local_points, np.asarray(local_cells, dtype=np.int32))
        local_values = np.asarray(local_values, dtype=np.complex128)
        if local_values.ndim == 1:
            local_values = local_values.reshape((len(local_points), -1))
    else:
        local_values = np.zeros((0, 0), dtype=np.complex128)

    packets = comm.allgather((local_indices, local_values))
    width = 0
    for _, values in packets:
        if values.size:
            width = int(values.shape[1])
            break
    if width == 0:
        raise RuntimeError("No rank could evaluate the requested 3D probe points.")

    values = np.zeros((len(points), width), dtype=np.complex128)
    filled = np.zeros(len(points), dtype=bool)
    for indices, packet_values in packets:
        for row, point_index in enumerate(indices):
            if not filled[point_index]:
                values[int(point_index)] = packet_values[row]
                filled[int(point_index)] = True
    if not np.all(filled):
        missing = np.flatnonzero(~filled)[:5]
        examples = ", ".join(str(points[i].tolist()) for i in missing)
        raise RuntimeError(f"No mesh cell found for {np.count_nonzero(~filled)} 3D probe points: {examples}")
    return values[:, :3]

def _positive_sqrt(value: complex) -> complex:
    root = np.sqrt(complex(value))
    if root.imag < -1.0e-14 or (abs(root.imag) < 1.0e-14 and root.real < 0.0):
        root = -root
    return complex(root)

def _mode_basis(cfg: SimulationConfig3D, n_medium: complex, vertical_sign: int) -> tuple[np.ndarray, np.ndarray]:
    q = _positive_sqrt((cfg.k0 * complex(n_medium)) ** 2 - cfg.kx**2 - cfg.ky**2)
    kvec = np.asarray((cfg.kx, cfg.ky, vertical_sign * q), dtype=np.complex128)
    kind = cfg.polarization_kind.lower()
    if cfg.geometry_kind == "fresnel_interface" and kind != "p":
        # Fresnel reference fields are defined for s/p polarizations.  Treat a
        # legacy "custom" preset as s so the numerical modal fit uses the same
        # basis as analytic_fields_3d._fresnel_components.
        polarization = cfg.s_polarization_vector
    elif kind == "s":
        polarization = cfg.s_polarization_vector
    elif kind == "p":
        direction = kvec / (cfg.k0 * complex(n_medium))
        polarization = np.cross(direction, cfg.s_polarization_vector)
    else:
        polarization = np.asarray(cfg.polarization_vector, dtype=np.complex128)
        if abs(kvec[0]) + abs(kvec[1]) > 1.0e-14:
            denom = np.dot(kvec, kvec)
            if abs(denom) > 1.0e-30:
                polarization = polarization - kvec * (np.dot(kvec, polarization) / denom)
    norm = np.sqrt(np.sum(np.abs(polarization) ** 2))
    if norm <= 0.0:
        raise ValueError("Cannot build a nonzero 3D modal polarization vector.")
    return kvec, polarization / norm

def incident_air_plane_wave_field(V, cfg: SimulationConfig3D) -> fem.Function:
    """Incident air-region plane wave used by the Fresnel scattered-field solve.

    This field contains only the known incoming wave in the air background.  It
    deliberately excludes Fresnel reflected and transmitted analytic fields.
    """

    k_inc, p_inc = _mode_basis(cfg, cfg.n_air, vertical_sign=-1)
    amplitude = complex(cfg.incident_amplitude)
    field = fem.Function(V, name="E_incident_air")

    def eval_field(x):
        coords = x.T
        phase = np.exp(1j * (k_inc[0] * coords[:, 0] + k_inc[1] * coords[:, 1] + k_inc[2] * coords[:, 2]))
        return (amplitude * phase[:, None] * p_inc[None, :]).T

    field.interpolate(eval_field)
    field.x.scatter_forward()
    return field

def _interpolated_mode_field(function_space, mode_k: np.ndarray, mode_polarization: np.ndarray) -> fem.Function:
    field = fem.Function(function_space, name="mode_calibration")

    def eval_field(x):
        coords = x.T
        phase = np.exp(1j * (mode_k[0] * coords[:, 0] + mode_k[1] * coords[:, 1] + mode_k[2] * coords[:, 2]))
        return (phase[:, None] * mode_polarization[None, :]).T

    field.interpolate(eval_field)
    return field
