"""V7 full-spectrum identity continuation and fixed two-source screen."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from src.common.modes_3d import positive_sqrt
from src.solvers.hybrid_exact_qualification import (
    load_and_condense_exact_rhs,
    run_exact_interface_fgmres,
)
from src.solvers.hybrid_full_spectrum_continuation import (
    run_v7_full_spectrum_transform_identity,
)
from src.solvers.hybrid_full_spectrum_trace import (
    CanonicalModalArray,
    build_canonical_full_spectrum_trace_transform,
)
from src.solvers.hybrid_side_impedance import (
    assemble_reduced_artificial_interface_tangential_mass,
)

__all__ = ("run_v7_full_spectrum_continuation",)
_NX, _NY, _CHANNELS, _HARMONICS = 15, 7, 72, 105
_PLANE_ROWS, _SAFE = _NX * _NY * _CHANNELS, 1.0e-300
_PAIR_SEQUENCE = (0, 1, 2, 1, 0)
_SCREEN_LABELS = ("external_dtn_coupling", "fixed_random_repeat_0")
_MODES = tuple((round(m * _NX), round(n * _NY))
               for m in np.fft.fftfreq(_NX) for n in np.fft.fftfreq(_NY))


def _json_safe(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        value = value.tolist()
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_safe(item) for item in value]
    if isinstance(value, complex):
        return [float(value.real), float(value.imag)]
    return value if isinstance(value, (str, int, float, bool)) or value is None else str(value)


def _row_reorder(values: np.ndarray, source_rows: Any, target_rows: Any) -> np.ndarray:
    source, target = (np.asarray(source_rows, dtype=np.int64),
                       np.asarray(target_rows, dtype=np.int64))
    if values.ndim != 1 or values.size != source.size:
        raise ValueError("Gamma values do not match their row identity")
    index = {int(row): i for i, row in enumerate(source)}
    if len(index) != source.size or set(index) != set(map(int, target)):
        raise RuntimeError("group and plane Gamma row identities are not bijective")
    return np.asarray([values[index[int(row)]] for row in target], dtype=np.complex128)


def _face_families(system: Any) -> dict[int, str]:
    element = getattr(getattr(system, "V", None), "element", None)
    basix = getattr(element, "basix_element", None)
    dofs, points, moments = (getattr(basix, name, None)
                             for name in ("entity_dofs", "x", "M"))
    if dofs is None or points is None or moments is None:
        raise RuntimeError("canonical trace identity lacks Basix face moment metadata")
    found = []
    for face, coordinates in enumerate(points[2]):
        coordinates = np.asarray(coordinates, dtype=np.float64)
        if coordinates.ndim != 2 or coordinates.shape[1] < 3 or np.argmin(np.ptp(coordinates[:, :3], axis=0)) != 2:
            continue
        if len(dofs[2][face]) != 60:
            raise RuntimeError("z-face Basix metadata does not expose 60 moments")
        array = np.asarray(moments[2][face])
        if array.shape[0] != 60:
            raise RuntimeError("z-face Basix interpolation metadata has the wrong size")
        current = {}
        for basis in range(60):
            moment = np.abs(np.asarray(array[basis]))
            axes = [axis for axis, size in enumerate(moment.shape) if size in (2, 3)]
            if not axes:
                raise RuntimeError("z-face Basix moment lacks tangential components")
            axis = axes[0]
            weights = np.sum(moment, axis=tuple(i for i in range(moment.ndim) if i != axis))
            if weights.size < 2 or np.isclose(weights[0], weights[1]):
                raise RuntimeError("z-face Basix moment has ambiguous tangential family")
            current[basis] = "x" if weights[0] > weights[1] else "y"
        found.append(current)
    if not found or any(item != found[0] for item in found[1:]):
        raise RuntimeError("z-face Basix tangential family metadata is incomplete")
    counts = {name: sum(value == name for value in found[0].values()) for name in ("x", "y")}
    if counts != {"x": 30, "y": 30}:
        raise RuntimeError(f"z-face Basix tangential families are not 30+30: {counts}")
    return found[0]


def _pairs(system: Any) -> tuple[tuple[int, int], ...]:
    families = _face_families(system)
    x = sorted(basis for basis, name in families.items() if name == "x")
    y = sorted(basis for basis, name in families.items() if name == "y")
    pairs = [(i, 6 + i) for i in range(6)]
    pairs.extend((12 + a, 12 + b) for a, b in zip(x, y, strict=True))
    if len(pairs) != 36 or len({channel for pair in pairs for channel in pair}) != 72:
        raise RuntimeError("canonical trace tangential pairing does not cover 36 pairs")
    return tuple(pairs)


def _mass_scale(mass: PETSc.Mat, comm: MPI.Intracomm) -> float:
    diagonal = mass.createVecLeft()
    try:
        mass.getDiagonal(diagonal)
        local = float(np.asarray(diagonal.array, dtype=np.complex128).real.sum())
    finally:
        diagonal.destroy()
    scale = float(comm.allreduce(local, op=MPI.SUM)) / _PLANE_ROWS
    if not np.isfinite(scale) or scale <= 0.0:
        raise RuntimeError("ArtificialZTraceMass has no finite positive trace scale")
    return scale


def _material_audit(system: Any, support: Mapping[str, Any], comm: MPI.Intracomm) -> dict[str, Any]:
    topology = system.V.mesh.topology
    topology.create_connectivity(topology.dim - 1, topology.dim)
    links = topology.connectivity(topology.dim - 1, topology.dim)
    tags = system.local_mesh.mesh_data.cell_tags
    tag_by_cell = {int(i): int(v) for i, v in zip(tags.indices, tags.values, strict=True)}
    local = set()
    for facet in support["facet_tags"].indices:
        local.update(tag_by_cell[int(cell)] for cell in links.links(int(facet))
                     if int(cell) in tag_by_cell)
    values = sorted({tag for part in comm.allgather(tuple(sorted(local))) for tag in part})
    if not values:
        raise RuntimeError("V7 support has no readable adjacent material tags")
    return {
        "support_material_tags": values,
        "heterogeneous": len(values) > 1,
        "background": "cfg.substrate_index",
        "averaged": False,
        "metadata_allgather": True,
        "numeric_allgather": False,
    }


def _symbol(system: Any, scales: tuple[float, float]) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    cfg = system.cfg
    k0n = complex(cfg.k0) * complex(cfg.substrate_index)
    floor = 1.0e-12 * max(
        abs(k0n), 2.0 * np.pi / float(cfg.period_x), 2.0 * np.pi / float(cfg.period_y)
    )
    q, phases, cutoff = np.empty((_HARMONICS, 2), complex), np.empty(_HARMONICS, complex), 0
    dz = abs(float(system.local_mesh.z_values[4]) - float(system.local_mesh.z_values[2]))
    for index, (m, n) in enumerate(_MODES):
        kx = complex(cfg.kx) + 2.0 * np.pi * m / float(cfg.period_x)
        ky = complex(cfg.ky) + 2.0 * np.pi * n / float(cfg.period_y)
        beta = positive_sqrt(k0n**2 - kx**2 - ky**2)
        if abs(beta) < floor:
            beta, cutoff = complex(floor), cutoff + 1
        q[index] = (-1j * beta, -1j * k0n**2 / beta)
        phases[index] = np.exp(1j * beta * dz)
    return q, phases, {
        "harmonic_count": _HARMONICS,
        "near_cutoff_floor": floor,
        "near_cutoff_count": cutoff,
        "background": [k0n.real / float(cfg.k0), k0n.imag / float(cfg.k0)],
        "q_convention": {"TE": "-i*beta", "TM": "-i*(k0*n_bg)^2/beta"},
        "pair_sequence": list(_PAIR_SEQUENCE),
        "mass_scales": list(scales),
    }


def _rotate(values: np.ndarray, kx: complex, ky: complex) -> tuple[complex, complex]:
    norm = math.sqrt(abs(kx) ** 2 + abs(ky) ** 2)
    if norm < _SAFE:
        te, tm = np.asarray((0.0, 1.0), complex), np.asarray((1.0, 0.0), complex)
    else:
        te, tm = np.asarray((-ky, kx), complex) / norm, np.asarray((kx, ky), complex) / norm
    return complex(np.vdot(te, values)), complex(np.vdot(tm, values))


def _unrotate(te: complex, tm: complex, kx: complex, ky: complex) -> np.ndarray:
    norm = math.sqrt(abs(kx) ** 2 + abs(ky) ** 2)
    if norm < _SAFE:
        return np.asarray((tm, te), complex)
    return np.asarray((-ky, kx), complex) * te / norm + np.asarray((kx, ky), complex) * tm / norm


def _kernel(lower: np.ndarray, upper: np.ndarray, q: np.ndarray, phase: complex, scales: tuple[float, float], kx: complex, ky: complex) -> tuple[np.ndarray, np.ndarray]:
    lower_p, upper_p = _rotate(lower, kx, ky), _rotate(upper, kx, ky)
    left, right = [], []
    for polarization in range(2):
        base = lower_p[polarization] / (2.0 * scales[0] * q[polarization])
        top = upper_p[polarization] / (2.0 * scales[1] * q[polarization]) + 0.5 * phase * base
        left.append(base + 0.5 * phase * top)
        right.append(top)
    return _unrotate(left[0], left[1], kx, ky), _unrotate(right[0], right[1], kx, ky)


class _PairSpectralPC:
    def __init__(self, action, lower, upper, lower_rows, upper_rows, pairs, scales, q, phases, system, comm):
        self.action, self.lower, self.upper = action, lower, upper
        self.lower_rows = np.asarray(lower_rows, dtype=np.int64).copy()
        self.upper_rows = np.asarray(upper_rows, dtype=np.int64).copy()
        self.pairs, self.scales, self.q, self.phases = pairs, scales, q, phases
        self.comm = comm
        self.kx, self.ky = complex(system.cfg.kx), complex(system.cfg.ky)
        self.lx, self.ly = float(system.cfg.period_x), float(system.cfg.period_y)
        self.closed = False
        self.owner = {channel: pair % comm.size for pair, item in enumerate(pairs) for channel in item}
        self.audit = {
            "sequence": list(_PAIR_SEQUENCE),
            "numeric_allgather": False,
            "full_plane_numeric_replica": False,
            "numeric_collective_count": 2,
            "numeric_collective_types": ["Alltoallv", "Alltoallv"],
        }

    def _route(self, lower, upper):
        if (tuple(lower.channel_ids) != tuple(upper.channel_ids)
                or tuple(lower.grid) != tuple(upper.grid)
                or bool(lower.dual) != bool(upper.dual)):
            raise ValueError("lower/upper modal arrays have inconsistent identity")
        channels, width = tuple(map(int, lower.channel_ids)), 2 * _HARMONICS

        def exchange(out, incoming, values):
            send_counts = np.asarray([width * len(bucket) for bucket in out], np.int32)
            recv_counts = np.asarray([width * len(bucket) for bucket in incoming], np.int32)
            send_disp = np.cumsum(np.r_[0, send_counts[:-1]], dtype=np.int32)
            recv_disp = np.cumsum(np.r_[0, recv_counts[:-1]], dtype=np.int32)
            send = np.empty(int(send_counts.sum()), complex)
            if values is not None:
                for destination, bucket in enumerate(out):
                    for index, channel in enumerate(bucket):
                        start = int(send_disp[destination]) + width * index
                        send[start : start + _HARMONICS] = values[channel][0]
                        send[start + _HARMONICS : start + width] = values[channel][1]
            receive = np.empty(int(recv_counts.sum()), complex)
            self.comm.Alltoallv(
                [send, send_counts, send_disp, MPI.C_DOUBLE_COMPLEX],
                [receive, recv_counts, recv_disp, MPI.C_DOUBLE_COMPLEX],
            )
            return send, receive, recv_disp

        local_index = {channel: i for i, channel in enumerate(channels)}
        outbound = [[channel for channel in channels if self.owner[channel] == destination]
                    for destination in range(self.comm.size)]
        inbound = [[channel for channel in range(_CHANNELS)
                    if channel % self.comm.size == source
                    and self.owner[channel] == self.comm.rank]
                   for source in range(self.comm.size)]
        values = {channel: (lower.values[local_index[channel]].reshape(-1),
                            upper.values[local_index[channel]].reshape(-1))
                  for channel in channels}
        send, receive, recv_disp = exchange(outbound, inbound, values)
        buffers = [max(send.size, receive.size)]
        incoming_values = {}
        for source, bucket in enumerate(inbound):
            for index, channel in enumerate(bucket):
                start = int(recv_disp[source]) + width * index
                incoming_values[channel] = (receive[start : start + _HARMONICS],
                                             receive[start + _HARMONICS : start + width])
        out_l = {channel: np.empty(_HARMONICS, complex) for channel in incoming_values}
        out_u = {channel: np.empty(_HARMONICS, complex) for channel in incoming_values}
        for pair, (x_channel, y_channel) in enumerate(self.pairs):
            if pair % self.comm.size != self.comm.rank:
                continue
            if x_channel not in incoming_values or y_channel not in incoming_values:
                raise RuntimeError("pair owner did not receive both tangential channels")
            for harmonic, (m, n) in enumerate(_MODES):
                lower_xy = np.asarray((incoming_values[x_channel][0][harmonic], incoming_values[y_channel][0][harmonic]))
                upper_xy = np.asarray((incoming_values[x_channel][1][harmonic], incoming_values[y_channel][1][harmonic]))
                left, right = _kernel(lower_xy, upper_xy, self.q[harmonic], self.phases[harmonic], self.scales,
                                      self.kx + 2.0 * np.pi * m / self.lx, self.ky + 2.0 * np.pi * n / self.ly)
                out_l[x_channel][harmonic], out_l[y_channel][harmonic] = left
                out_u[x_channel][harmonic], out_u[y_channel][harmonic] = right
        back_out = [[channel for channel in range(_CHANNELS)
                     if channel % self.comm.size == destination
                     and self.owner[channel] == self.comm.rank]
                    for destination in range(self.comm.size)]
        back_in = [[channel for channel in range(_CHANNELS)
                    if channel % self.comm.size == self.comm.rank
                    and self.owner[channel] == source]
                   for source in range(self.comm.size)]
        send, receive, recv_disp = exchange(
            back_out, back_in, {channel: (out_l[channel], out_u[channel]) for channel in out_l}
        )
        buffers.append(max(send.size, receive.size))
        result_l, result_u = np.empty_like(lower.values), np.empty_like(upper.values)
        for source, bucket in enumerate(back_in):
            for index, channel in enumerate(bucket):
                start = int(recv_disp[source]) + width * index
                result_l[local_index[channel]] = receive[start : start + _HARMONICS].reshape(_NX, _NY)
                result_u[local_index[channel]] = receive[start + _HARMONICS : start + width].reshape(_NX, _NY)
        local_buffer = max(buffers)
        self.audit.update({
            "local_numeric_buffer_entries": int(local_buffer),
            "max_numeric_buffer_entries": int(self.comm.allreduce(local_buffer, op=MPI.MAX)),
        })
        return (CanonicalModalArray(result_l, lower.channel_ids, lower.grid, False),
                CanonicalModalArray(result_u, upper.channel_ids, upper.grid, False))

    def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        if self.closed:
            raise RuntimeError("V7 spectral preconditioner is closed")
        lower_vec = upper_vec = None
        try:
            lower_vec, upper_vec = self.action.restrict_interface(source)
            lower_rows = self.action.group_gamma_rows_local(0)
            upper_rows = self.action.group_gamma_rows_local(2)
            lower_raw = _row_reorder(np.asarray(lower_vec.array), lower_rows, self.lower_rows)
            upper_raw = _row_reorder(np.asarray(upper_vec.array), upper_rows, self.upper_rows)
            lower_modal = self.lower.forward_dual(lower_raw)
            upper_modal = self.upper.forward_dual(upper_raw)
            lower_modal, upper_modal = self._route(lower_modal, upper_modal)
            lower_raw = self.lower.inverse_primal(lower_modal)
            upper_raw = self.upper.inverse_primal(upper_modal)
            lower_vec.array[:] = _row_reorder(lower_raw, self.lower_rows, lower_rows)
            upper_vec.array[:] = _row_reorder(upper_raw, self.upper_rows, upper_rows)
            lower_vec.assemble()
            upper_vec.assemble()
            self.action.prolong_interface(lower_vec, upper_vec, target)
        finally:
            if upper_vec is not None:
                upper_vec.destroy()
            if lower_vec is not None:
                lower_vec.destroy()

    def close(self) -> None:
        self.closed = True


def _factor(action: Any) -> dict[str, Any]:
    value = getattr(action, "diagnostics", {}).get("factor_lifecycle")
    if not isinstance(value, Mapping) or int(value.get("ready", 0)) != 3 or bool(value.get("destroyed")):
        raise RuntimeError("V7 screen requires three live group factors")
    return _json_safe(value)


def _residuals(result: Mapping[str, Any]) -> dict[str, float]:
    rows = {int(row["iteration"]): float(row.get("full_true_residual_relative", np.nan))
            for row in result.get("checkpoint_history", ())
            if isinstance(row, Mapping) and "iteration" in row}
    return {str(iteration): rows.get(iteration, float("nan")) for iteration in (8, 16, 32, 64)}


def _classify(records: Mapping[str, Mapping[str, Any]]) -> tuple[str, str, dict[str, Any]]:
    values = [records[label]["residuals"] for label in _SCREEN_LABELS]
    if not all(np.isfinite(float(value)) for row in values for value in row.values()):
        return "NO_SIGNAL_NONFINITE", "moving_pml_required", {"finite": False}
    drop_16_32 = [math.log10(max(row["16"], _SAFE) / max(row["32"], _SAFE)) for row in values]
    drop_32_64 = [math.log10(max(row["32"], _SAFE) / max(row["64"], _SAFE)) for row in values]
    positive = (all(row["32"] <= 0.7 for row in values)
                or all(value >= 0.15 for value in drop_16_32)
                or all(row["64"] <= 0.5 for row in values))
    strict_negative = all(row["64"] > 0.8 for row in values) and all(value < 0.10 for value in drop_32_64)
    detail = {"finite": True, "drop_16_32": drop_16_32, "drop_32_64": drop_32_64,
              "positive": positive, "strict_negative": strict_negative}
    if positive:
        return "V7_FULL_SPECTRUM_TWO_SOURCE_POSITIVE", "five_source_required", detail
    if strict_negative:
        return "FULL_SPECTRUM_SWEEP_NO_SIGNAL", "moving_pml_required", detail
    return "NO_POSITIVE_SIGNAL", "moving_pml_required", detail


def run_v7_full_spectrum_continuation(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Run the identity-approved fixed two-source V7 screen."""
    identity = run_v7_full_spectrum_transform_identity(payload)
    if identity.get("pass") is not True:
        raise RuntimeError("V7 screen requires a passing transform identity")
    system, action = payload["system"], payload["schur_action"]
    comm = system.local_mesh.mesh.comm
    configuration = payload.get("formal_exact_configuration")
    if not isinstance(configuration, Mapping):
        raise TypeError("V7 screen lacks the bound formal exact configuration")
    descriptors = configuration.get("descriptors", payload.get("frozen_rhs_descriptors"))
    if not isinstance(descriptors, Mapping) or any(label not in descriptors for label in _SCREEN_LABELS):
        raise RuntimeError("V7 screen lacks the two frozen RHS authority descriptors")
    callback = configuration.get("resource_callback", payload.get("resource_callback"))
    if not callable(callback):
        raise TypeError("V7 screen lacks the resource callback")
    resource_before, factor_before = _json_safe(callback()), _factor(action)
    masses, transforms, pc, records = [], [], None, {}
    try:
        coverage = identity.get("coverage")
        expected = {"lower_rows": _PLANE_ROWS, "upper_rows": _PLANE_ROWS,
                    "channel_count": _CHANNELS, "harmonic_count": _HARMONICS}
        if not isinstance(coverage, Mapping) or any(coverage.get(k) != v for k, v in expected.items()):
            raise RuntimeError("V7 transform identity coverage is not 7560/7560/72/105")
        pairs, sides = _pairs(system), []
        for layout_key, support_key in (("lower_gamma_layout", "lower"), ("upper_gamma_layout", "upper")):
            mass = assemble_reduced_artificial_interface_tangential_mass(
                system.V, system.static_condensation.condensed,
                payload["interface_supports"][support_key], bare_operator=payload["bare_operator"])
            masses.append(mass)
            transform = build_canonical_full_spectrum_trace_transform(system, payload[layout_key], comm)
            transforms.append(transform)
            sides.append((mass, transform, _material_audit(system, payload["interface_supports"][support_key], comm)))
        scales = (_mass_scale(sides[0][0].matrix, comm), _mass_scale(sides[1][0].matrix, comm))
        q, phases, symbol = _symbol(system, scales)
        pc = _PairSpectralPC(action, sides[0][1], sides[1][1],
                             payload["lower_gamma_layout"].gamma_rows_local,
                             payload["upper_gamma_layout"].gamma_rows_local,
                             pairs, scales, q, phases, system, comm)
        for label in _SCREEN_LABELS:
            bundle = None
            try:
                roundtrip = configuration.get("canonical_roundtrip")
                if isinstance(roundtrip, Mapping):
                    roundtrip = roundtrip[label]
                validation = dict(configuration.get("validation", {}))
                validation["expected_label"] = label
                bundle = load_and_condense_exact_rhs(
                    descriptors[label], base_directory=configuration["base_directory"],
                    action=action, canonical_roundtrip=roundtrip, comm=comm, **validation)
                fgmres = run_exact_interface_fgmres(
                    interface_operator=payload["interface_operator"], schur_action=action,
                    bare_operator=payload["bare_operator"], condensed_rhs=bundle.condensed_rhs,
                    active_rhs=bundle.active_rhs, interior_rhs_by_group=bundle.interior_rhs_by_group,
                    right_preconditioner=pc, label=label, mandatory_checkpoints=(8, 16, 32, 64),
                    conditional_checkpoints=(), max_iterations=64, resource_callback=callback)
                accepted = fgmres.pop("accepted_solution", None)
                if accepted is not None:
                    accepted.destroy()
                records[label] = {"residuals": _residuals(fgmres), "fgmres": _json_safe(fgmres)}
            finally:
                if bundle is not None:
                    bundle.destroy()
        classification, next_stage, screen = _classify(records)
        screen_positive = next_stage == "five_source_required"
        return _json_safe({
            "status": "completed_v7_full_spectrum_two_source_screen",
            "classification": classification, "executed": True,
            "formal_adjudication": True, "pass": screen_positive,
            "transform_identity": identity, "sources": records,
            "screen": {"mandatory_checkpoints": [8, 16, 32, 64],
                        "conditional_checkpoints": [], "screen_completed": True,
                        "screen_positive": screen_positive, **screen},
            "symbol": symbol, "material": {"lower": sides[0][2], "upper": sides[1][2]},
            "communication": pc.audit,
            "resource": {"before": resource_before, "after": _json_safe(callback())},
            "factor_lifecycle": {"before": factor_before, "after": _factor(action)},
            "next_required_stage": next_stage, "numeric_allgather": False,
            "full_plane_numeric_replica": False,
        })
    finally:
        if pc is not None:
            pc.close()
        for transform in reversed(transforms):
            transform.close()
        for mass in reversed(masses):
            mass.destroy()
