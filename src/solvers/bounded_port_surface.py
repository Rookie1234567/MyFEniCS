"""Lazy adapter to the original MPC-aware surface assembler, no volume forms."""

from time import perf_counter

import numpy as np

from src.solvers.bounded_port_provider import PortFunctional


class SurfacePortSource:
    def __init__(
        self,
        modes,
        identities,
        assemblers,
        mpc,
        cfg,
        *,
        source_identity,
        maximum_local_surface_support,
    ):
        self.modes, self.identities = tuple(modes), tuple(identities)
        self.assemblers, self.mpc, self.cfg = assemblers, mpc, cfg
        self.source_identity = source_identity
        self.maximum_local_surface_support = int(maximum_local_surface_support)
        index = mpc.function_space.dofmap.index_map
        native_slots = int(index.size_local + index.num_ghosts)
        self.costs = {
            "generation_seconds": 0.0,
            "component_calls": 0,
            "creator_numeric_upper_bytes": 512 * self.maximum_local_surface_support
            + 64 * native_slots,
            "creator_bound_kind": "conditional NumPy/vector workspace bound; library/JIT allocator overhead measured in tree RSS",
            "native_vector_slots": native_slots,
            "persistent_functional_numeric_bytes": 0,
        }

    def upper_bytes(self, index):
        # Row+complex value (24 bytes) for C and D, H scalar (8).
        return 48 * self.maximum_local_surface_support + 8

    def __call__(self, index, source_identity):
        if source_identity != self.source_identity:
            raise ValueError("FE source/cache identity changed")
        from src.solvers.dtn_port_3d import _combine_owned_entries, _traction_vector

        mode = self.modes[index]
        began = perf_counter()
        components = tuple(
            self.assemblers[(mode.side, j)].assemble_entries(mode, self.mpc)
            for j in (0, 1)
        )
        self.costs["component_calls"] += 2
        comm = self.mpc.function_space.mesh.comm
        pr, pv = _combine_owned_entries(
            components, (mode.e_vector[0], mode.e_vector[1]), comm=comm
        )
        traction = _traction_vector(mode, self.cfg)
        cr, cv = _combine_owned_entries(
            components, (-traction[0], -traction[1]), comm=comm
        )
        del components
        cr, pr = np.asarray(cr, dtype=np.int64), np.asarray(pr, dtype=np.int64)
        cv, pv = (
            np.asarray(cv, dtype=np.complex128),
            np.asarray(pv.conj(), dtype=np.complex128),
        )
        for a in (cr, cv, pr, pv):
            a.flags.writeable = False
        self.costs["generation_seconds"] += perf_counter() - began
        row = self.identities[index]
        return PortFunctional(
            (index, mode.side, mode.m, mode.n, mode.polarization),
            cr,
            cv,
            pr,
            pv,
            float(row["projection_denominator"]),
            dict(row),
        )
