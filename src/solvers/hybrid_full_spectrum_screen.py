"""V7 full-spectrum identity continuation and V8 fixed-source screen."""

from __future__ import annotations

import math
import time
from collections.abc import Mapping
from itertools import pairwise
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

__all__ = (
    "run_v7_full_spectrum_continuation",
    "run_v8_full_spectrum_two_source",
)
_NX, _NY, _CHANNELS, _HARMONICS = 15, 7, 72, 105
_PLANE_ROWS, _SAFE = _NX * _NY * _CHANNELS, 1.0e-300
_PAIR_SEQUENCE = (0, 1, 2, 1, 0)
_SCREEN_LABELS = ("external_dtn_coupling", "fixed_random_repeat_0")
_V8_HOLDOUT_LABELS = (
    "modal_traction_positive",
    "modal_traction_negative",
    "fixed_random_repeat_1",
)
_V8_STRONG_LABELS = (
    "external_dtn_coupling",
    "modal_traction_positive",
    "modal_traction_negative",
)
_V8_ALL_LABELS = _SCREEN_LABELS + _V8_HOLDOUT_LABELS
_V8_MARKER_ALIASES = {
    "external_dtn_coupling": "external",
    "fixed_random_repeat_0": "random0",
    "modal_traction_positive": "modal_positive",
    "modal_traction_negative": "modal_negative",
    "fixed_random_repeat_1": "random1",
}
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
        self.apply_count = 0
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
            self.apply_count += 1
            self.audit["apply_count"] = int(self.apply_count)
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


_V8_SCHEMA = "task040.v8.full_spectrum_two_source.v1"
_V8_CHECKPOINTS = (8, 16, 32, 64)
_V8_CONDITIONAL = 128
_V8_CONDITIONAL_ELAPSED_LIMIT = 9000.0
_V8_TIMEOUT = 10800.0
_V8_UNSTABLE_REASONS = frozenset(
    {
        "NANORINF",
        "BREAKDOWN",
        "INDEFINITE",
        "DIVERGED_BREAKDOWN",
        "SOLVER_EXCEPTION",
        "PC_ERROR",
        "COLLECTIVE_ERROR",
    }
)


def _v8_mark(
    payload: Mapping[str, Any],
    stage: str,
    started: float,
    resource_callback: Any,
    action: Any,
    *,
    source: str | None = None,
    checkpoint: int | None = None,
    pc_apply_count: int | None = None,
    action_apply_count: int | None = None,
    stage_clock_start: float | None = None,
    **detail: Any,
) -> dict[str, Any]:
    resource = _json_safe(resource_callback())
    now = time.perf_counter()
    clocks = payload.get("_v8_marker_clocks")
    if not isinstance(clocks, dict):
        clocks = {}
        if isinstance(payload, dict):
            payload["_v8_marker_clocks"] = clocks
    if stage.endswith("_one_apply_begin"):
        stage_start = now
        clocks[stage] = now
    elif stage.endswith("_one_apply_end"):
        stage_start = clocks.get(f"{stage[:-4]}_begin", now)
    elif stage_clock_start is not None:
        stage_start = float(stage_clock_start)
        clocks[stage] = now
    else:
        stage_start = clocks.get("_last", now)
        clocks[stage] = now
    clocks["_last"] = now
    marker_status = detail.pop("status", None)
    if marker_status is None:
        marker_status = "begin" if stage.endswith("_begin") else "complete"
    diagnostics = getattr(action, "diagnostics", {})
    lifecycle = _json_safe(diagnostics.get("factor_lifecycle", {}))
    if action_apply_count is None:
        action_apply_count = diagnostics.get("apply_count")
    record = {
        "process_start_wall_seconds": float(now - started),
        "stage_wall_seconds": float(now - stage_start),
        "rss_bytes": resource.get("rss_bytes"),
        "swap_bytes": resource.get("swap_bytes"),
        "resource": resource,
        "factor_lifecycle": lifecycle,
        "status": marker_status,
        "pc_apply_count": pc_apply_count,
        "action_apply_count": action_apply_count,
        "source": source,
        "checkpoint": checkpoint,
        **detail,
    }
    marker_callback = payload.get("marker_callback")
    if callable(marker_callback):
        marker_callback(stage, record)
    return record


def _v8_marker_alias(label: str) -> str:
    try:
        return _V8_MARKER_ALIASES[label]
    except KeyError as exc:
        raise ValueError(f"unknown V8 source label: {label}") from exc


def _v8_residuals(
    result: Mapping[str, Any], iterations: tuple[int, ...] = _V8_CHECKPOINTS
) -> dict[str, float | None]:
    values = {
        int(row["iteration"]): float(row["full_true_residual_relative"])
        for row in result.get("checkpoint_history", ())
        if isinstance(row, Mapping)
        and "iteration" in row
        and isinstance(row.get("full_true_residual_relative"), (int, float))
    }
    return {
        str(iteration): values.get(iteration)
        for iteration in iterations
    }


def _v8_replay_residuals(record: Mapping[str, Any]) -> dict[str, float | None]:
    values: Any = record.get("residuals")
    if not isinstance(values, Mapping):
        fgmres = record.get("fgmres")
        values = (
            fgmres.get("checkpoint_history")
            if isinstance(fgmres, Mapping)
            else ()
        )
    if not isinstance(values, Mapping):
        values = {
            str(row.get("iteration")): row.get("full_true_residual_relative")
            for row in values
            if isinstance(row, Mapping)
        }
    result: dict[str, float | None] = {}
    for iteration in (64, 128):
        value = values.get(str(iteration))
        try:
            value = float(value)
        except (TypeError, ValueError):
            value = None
        result[str(iteration)] = (
            value
            if value is not None and np.isfinite(value) and value >= 0.0
            else None
        )
    return result


def _v8_full_residual(
    action: Any,
    bare_operator: PETSc.Mat,
    solution: PETSc.Vec,
    active_rhs: PETSc.Vec,
    interior_rhs_by_group: Mapping[int, PETSc.Vec],
) -> tuple[float, float, float]:
    full_state = None
    residual = bare_operator.createVecLeft()
    try:
        full_state, _audit = action.build_full_state_from_condensed_solution(
            solution, interior_rhs_by_group
        )
        solution_norm = float(full_state.norm())
        bare_operator.mult(full_state, residual)
        residual.axpy(PETSc.ScalarType(-1.0), active_rhs)
        norm = float(residual.norm())
        rhs_norm = float(active_rhs.norm())
        return norm, norm / max(rhs_norm, _SAFE), solution_norm
    finally:
        residual.destroy()
        if full_state is not None:
            full_state.destroy()


def _v8_one_apply(
    payload: Mapping[str, Any],
    bundle: Any,
    pc: _PairSpectralPC,
    one_apply_started: float,
    callback: Any,
) -> dict[str, Any]:
    action = payload["schur_action"]
    pc_before = int(pc.apply_count)
    action_before = int(action.diagnostics.get("apply_count", 0))
    output = action.create_interface_vector()
    interface_image = action.create_interface_vector()
    try:
        pc.apply(bundle.condensed_rhs, output)
        pc_after = int(pc.apply_count)
        action.apply(output, interface_image)
        interface_image.axpy(PETSc.ScalarType(-1.0), bundle.condensed_rhs)
        condensed_rhs_norm = float(bundle.condensed_rhs.norm())
        active_rhs_norm = float(bundle.active_rhs.norm())
        interface_residual = float(interface_image.norm())
        interface_relative = interface_residual / max(condensed_rhs_norm, _SAFE)
        full_residual, full_relative, full_solution_norm = _v8_full_residual(
            action,
            payload["bare_operator"],
            output,
            bundle.active_rhs,
            bundle.interior_rhs_by_group,
        )
        interface_solution_norm = float(output.norm())
        action_after = int(action.diagnostics.get("apply_count", 0))
        return {
            "active_rhs_norm": active_rhs_norm,
            "full_rhs_norm": active_rhs_norm,
            "condensed_rhs_norm": condensed_rhs_norm,
            "interface_rhs_norm": condensed_rhs_norm,
            "interface_solution_norm": interface_solution_norm,
            "full_solution_norm": full_solution_norm,
            "interface_true_residual_norm": interface_residual,
            "interface_true_residual_relative": interface_relative,
            "full_bare_f_true_residual_norm": full_residual,
            "full_bare_f_true_residual_relative": full_relative,
            "pc_apply_count_before": pc_before,
            "pc_apply_count_after": pc_after,
            "pc_apply_count_delta": pc_after - pc_before,
            "action_apply_count_before": action_before,
            "action_apply_count_after": action_after,
            "action_apply_count_delta": action_after - action_before,
            "finite": bool(
                all(
                    np.isfinite(value) and value >= 0.0
                    for value in (
                        active_rhs_norm,
                        condensed_rhs_norm,
                        interface_solution_norm,
                        full_solution_norm,
                        interface_residual,
                        interface_relative,
                        full_residual,
                        full_relative,
                    )
                )
            ),
            "one_apply_elapsed_seconds": float(
                time.perf_counter() - one_apply_started
            ),
        }
    finally:
        interface_image.destroy()
        output.destroy()


def _v8_load_bundle(
    configuration: Mapping[str, Any],
    label: str,
    payload: Mapping[str, Any],
) -> Any:
    descriptors = configuration["descriptors"]
    roundtrip = configuration.get("canonical_roundtrip")
    if isinstance(roundtrip, Mapping):
        roundtrip = roundtrip[label]
    validation = dict(configuration.get("validation", {}))
    validation["expected_label"] = label
    return load_and_condense_exact_rhs(
        descriptors[label],
        base_directory=configuration["base_directory"],
        action=payload["schur_action"],
        canonical_roundtrip=roundtrip,
        comm=payload["system"].local_mesh.mesh.comm,
        **validation,
    )


def _v8_numerical_exception_reason(exc: Exception) -> str | None:
    text = str(exc).upper()
    for reason, markers in (
        ("NANORINF", ("NAN", "NONFINITE", "INFINITE")),
        ("BREAKDOWN", ("BREAKDOWN",)),
        ("INDEFINITE", ("INDEFINITE",)),
        ("PC_ERROR", ("PC_ERROR", "PRECONDITIONER")),
    ):
        if any(marker in text for marker in markers):
            return reason
    return None


def _v8_run_source(
    payload: Mapping[str, Any],
    label: str,
    pc: _PairSpectralPC,
    started: float,
    callback: Any,
    *,
    mandatory: tuple[int, ...] = _V8_CHECKPOINTS,
    max_iterations: int = 64,
    one_apply: bool = True,
    run_kind: str = "mandatory_fgmres",
) -> dict[str, Any]:
    configuration = payload["formal_exact_configuration"]
    action = payload["schur_action"]
    pc_before = int(pc.apply_count)
    bundle = None
    one = None
    fgmres_pc_before: int | None = None
    solve_started = time.perf_counter()
    try:
        bundle = _v8_load_bundle(configuration, label, payload)
        if one_apply:
            marker = _v8_marker_alias(label)
            _v8_mark(
                payload,
                f"v8_full_spectrum_{marker}_one_apply_begin",
                started,
                callback,
                action,
                source=label,
                status="begin",
                run_kind=run_kind,
                pc_apply_count=pc.apply_count,
                action_apply_count=action.diagnostics.get("apply_count"),
            )
            one_apply_started = time.perf_counter()
            one = _v8_one_apply(payload, bundle, pc, one_apply_started, callback)
            _v8_mark(
                payload,
                f"v8_full_spectrum_{marker}_one_apply_end",
                started,
                callback,
                action,
                source=label,
                status="complete",
                run_kind=run_kind,
                one_apply=one,
                pc_apply_count=pc.apply_count,
                action_apply_count=action.diagnostics.get("apply_count"),
            )
            fgmres_pc_before = int(pc.apply_count)
        else:
            fgmres_pc_before = int(pc.apply_count)

        def checkpoint(row: Mapping[str, Any]) -> None:
            marker = _v8_marker_alias(label)
            _v8_mark(
                payload,
                f"v8_full_spectrum_{marker}_r{int(row['iteration'])}",
                started,
                callback,
                action,
                source=label,
                checkpoint=int(row["iteration"]),
                status="complete",
                run_kind=run_kind,
                pc_apply_count=pc.apply_count,
                residual=_json_safe(row),
            )

        solve_started = time.perf_counter()
        fgmres = run_exact_interface_fgmres(
            interface_operator=payload["interface_operator"],
            schur_action=action,
            bare_operator=payload["bare_operator"],
            condensed_rhs=bundle.condensed_rhs,
            active_rhs=bundle.active_rhs,
            interior_rhs_by_group=bundle.interior_rhs_by_group,
            right_preconditioner=pc,
            label=label,
            mandatory_checkpoints=mandatory,
            conditional_checkpoints=(),
            max_iterations=max_iterations,
            restart=32,
            resource_callback=callback,
            checkpoint_callback=checkpoint,
        )
        accepted = fgmres.pop("accepted_solution", None)
        if accepted is not None:
            accepted.destroy()
        final_iteration = int(fgmres.get("final_iteration", 0))
        reason = (
            "HAPPY_BREAKDOWN"
            if fgmres.get("stopped_at_happy_breakdown")
            else "MAX_IT"
            if final_iteration >= max_iterations
            else "DIVERGED_ITS"
        )
        residuals = _v8_residuals(fgmres, mandatory)
        return {
            "label": label,
            "run_kind": run_kind,
            "one_apply": one,
            "fgmres": _json_safe(fgmres),
            "fgmres_elapsed_seconds": float(time.perf_counter() - solve_started),
            "residuals": residuals,
            "solver_reason": reason,
            "pc_apply_count_before": pc_before,
            "pc_apply_count_after": int(pc.apply_count),
            "pc_apply_count_delta": int(pc.apply_count) - pc_before,
            "fgmres_pc_apply_count_before": int(fgmres_pc_before),
            "fgmres_pc_apply_count_after": int(pc.apply_count),
            "fgmres_pc_apply_count_delta": int(pc.apply_count)
            - int(fgmres_pc_before),
            "finite": bool(
                one is None
                or one["finite"]
            ) and all(
                value is not None and np.isfinite(float(value)) and value >= 0.0
                for value in residuals.values()
            ),
            "implementation_failure": False,
        }
    # Preserve the exception as implementation/numerical evidence for the screen.
    except Exception as exc:  # noqa: BLE001
        numerical_reason = _v8_numerical_exception_reason(exc)
        return {
            "label": label,
            "run_kind": run_kind,
            "one_apply": one,
            "fgmres": {"error": f"{type(exc).__name__}: {exc}"},
            "fgmres_elapsed_seconds": float(time.perf_counter() - solve_started),
            "residuals": {str(iteration): None for iteration in mandatory},
            "solver_reason": numerical_reason or "IMPLEMENTATION_EXCEPTION",
            "error": f"{type(exc).__name__}: {exc}",
            "implementation_failure": numerical_reason is None,
            "pc_apply_count_before": pc_before,
            "pc_apply_count_after": int(pc.apply_count),
            "pc_apply_count_delta": int(pc.apply_count) - pc_before,
            "fgmres_pc_apply_count_before": fgmres_pc_before,
            "fgmres_pc_apply_count_after": int(pc.apply_count),
            "fgmres_pc_apply_count_delta": (
                None
                if fgmres_pc_before is None
                else int(pc.apply_count) - int(fgmres_pc_before)
            ),
            "finite": False,
        }
    finally:
        if bundle is not None:
            bundle.destroy()


def _v8_classify(
    records: Mapping[str, Mapping[str, Any]],
) -> tuple[str, str, dict[str, Any]]:
    if any(
        bool(records.get(label, {}).get("implementation_failure"))
        or bool(
            records.get(label, {}).get("conditional_replay_implementation_failure")
        )
        for label in _SCREEN_LABELS
    ):
        return (
            "FULL_SPECTRUM_IMPLEMENTATION_FAILURE",
            "v8_full_spectrum_implementation_fix_required",
            {"implementation_failure": True},
        )
    residuals = [records[label]["residuals"] for label in _SCREEN_LABELS]
    finite = all(
        bool(records[label].get("finite"))
        and all(
            value is not None
            and np.isfinite(float(value))
            and float(value) >= 0.0
            for value in records[label]["residuals"].values()
        )
        for label in _SCREEN_LABELS
    )
    finite = finite and all(
        value is not None and np.isfinite(float(value)) and float(value) >= 0.0
        for row in residuals
        for value in row.values()
    )
    unstable = any(_v8_record_unstable(records[label]) for label in _SCREEN_LABELS)
    if not finite or unstable:
        return (
            "FULL_SPECTRUM_SWEEP_UNSTABLE",
            "v8_adaptive_spectral_schwarz_required",
            {"finite": finite, "unstable": unstable},
        )
    drop_16_32 = [
        math.log10(max(float(row["16"]), _SAFE) / max(float(row["32"]), _SAFE))
        for row in residuals
    ]
    drop_32_64 = [
        math.log10(max(float(row["32"]), _SAFE) / max(float(row["64"]), _SAFE))
        for row in residuals
    ]
    positive = bool(
        all(float(row["32"]) <= 0.7 for row in residuals)
        or all(value >= 0.15 for value in drop_16_32)
        or all(float(row["64"]) <= 0.5 for row in residuals)
    )
    strict_negative = bool(
        all(float(row["64"]) > 0.8 for row in residuals)
        and all(value < 0.10 for value in drop_32_64)
    )
    detail = {
        "finite": True,
        "unstable": unstable,
        "drop_16_to_32_decade": drop_16_32,
        "drop_32_to_64_decade": drop_32_64,
        "positive": positive,
        "strict_negative": strict_negative,
        "r64_inconclusive": not positive and not strict_negative,
        "v3_2_r64_baseline_available": False,
        "holdout_not_worse": None,
    }
    if positive:
        return (
            "V8_FULL_SPECTRUM_TWO_SOURCE_POSITIVE",
            "v8_five_source_required",
            detail,
        )
    if strict_negative:
        return (
            "FULL_SPECTRUM_SWEEP_NO_SIGNAL",
            "v8_adaptive_spectral_schwarz_required",
            detail,
        )
    return (
        "FULL_SPECTRUM_SWEEP_NO_BOUNDED_POSITIVE_SIGNAL",
        "v8_adaptive_spectral_schwarz_required",
        detail,
    )


def _v8_record_unstable(record: Mapping[str, Any]) -> bool:
    if record.get("implementation_failure") is True:
        return False
    if record.get("finite") is False:
        return True
    if str(record.get("solver_reason")) in _V8_UNSTABLE_REASONS:
        return True
    values = record.get("residuals", {})
    try:
        residuals = [float(values[str(iteration)]) for iteration in _V8_CHECKPOINTS]
    except (KeyError, TypeError, ValueError):
        return True
    return bool(
        max(residuals) > 10.0
        and any(right > left for left, right in pairwise(residuals))
    )


def _v8_five_source_classify(
    records: Mapping[str, Mapping[str, Any]],
) -> tuple[str, str, dict[str, Any]]:
    missing = any(label not in records for label in _V8_ALL_LABELS)
    implementation_failure = missing or any(
        bool(records[label].get("implementation_failure"))
        for label in records
    )
    if implementation_failure:
        return (
            "FULL_SPECTRUM_IMPLEMENTATION_FAILURE",
            "v8_full_spectrum_implementation_fix_required",
            {"implementation_failure": True, "missing_sources": missing},
        )
    finite = all(
        bool(records.get(label, {}).get("finite"))
        and all(
            value is not None
            and np.isfinite(float(value))
            and float(value) >= 0.0
            for value in records[label].get("residuals", {}).values()
        )
        for label in _V8_ALL_LABELS
    )
    unstable = any(_v8_record_unstable(records[label]) for label in _V8_ALL_LABELS)
    primary = [records[label]["residuals"] for label in _V8_STRONG_LABELS]
    holdouts = [records[label]["residuals"] for label in _V8_HOLDOUT_LABELS]
    holdout_not_worse = bool(
        finite
        and all(
            float(row["64"])
            <= float(row["32"])
            + 8.0 * np.finfo(float).eps * max(1.0, abs(float(row["32"])))
            for row in holdouts
        )
    )
    all_r64_bounded = bool(finite and all(float(row["64"]) <= 0.5 for row in [
        records[label]["residuals"] for label in _V8_ALL_LABELS
    ]))
    primary_strong = bool(
        all_r64_bounded
        and all(float(row["64"]) <= 1.0e-2 for row in primary)
    )
    detail = {
        "finite": finite,
        "unstable": unstable,
        "v3_2_r64_baseline_available": False,
        "all_five_r64_le_0_5": all_r64_bounded,
        "four_x_baseline_gate": False,
        "holdout_not_worse": holdout_not_worse,
        "strong_primary_r64_le_1e-2": primary_strong,
        "all_five_labels": list(_V8_ALL_LABELS),
    }
    if not finite or unstable:
        return (
            "FULL_SPECTRUM_SWEEP_UNSTABLE",
            "v8_adaptive_spectral_schwarz_required",
            detail,
        )
    if all_r64_bounded and holdout_not_worse:
        return (
            "FULL_SPECTRUM_WAVE_LAYER_STRONG_POSITIVE"
            if primary_strong
            else "FULL_SPECTRUM_WAVE_LAYER_WEAK_POSITIVE",
            "v8_factor_free_local_service_required",
            detail,
        )
    return (
        "FULL_SPECTRUM_SWEEP_NO_BOUNDED_POSITIVE_SIGNAL",
        "v8_adaptive_spectral_schwarz_required",
        detail,
    )


def _v8_conditional_allowed(
    records: Mapping[str, Mapping[str, Any]], resource: Mapping[str, Any]
) -> bool:
    if any(not bool(records[label].get("finite")) for label in _SCREEN_LABELS):
        return False
    values = [records[label]["residuals"] for label in _SCREEN_LABELS]
    if not all(float(row["64"]) <= 0.8 for row in values):
        return False
    if not any(
        math.log10(max(float(row["32"]), _SAFE) / max(float(row["64"]), _SAFE))
        >= 0.05
        for row in values
    ):
        return False
    elapsed = resource.get("formal_sequence_elapsed_seconds")
    rss = resource.get("rss_bytes")
    swap = resource.get("swap_bytes")
    return bool(
        isinstance(elapsed, (int, float))
        and float(elapsed) < _V8_CONDITIONAL_ELAPSED_LIMIT
        and isinstance(rss, (int, float))
        and int(rss) < 42 * 2**30
        and swap == 0
    )


def _v8_classify_conditional(
    records: Mapping[str, Mapping[str, Any]], initial: Mapping[str, Any]
) -> tuple[str, str, dict[str, Any]]:
    if any(
        bool(records.get(label, {}).get("implementation_failure"))
        or bool(
            records.get(label, {}).get("conditional_replay_implementation_failure")
        )
        for label in _SCREEN_LABELS
    ):
        return (
            "FULL_SPECTRUM_IMPLEMENTATION_FAILURE",
            "v8_full_spectrum_implementation_fix_required",
            {"implementation_failure": True, "r64_gate": initial},
        )
    values = [records[label]["conditional_128"] for label in _SCREEN_LABELS]
    finite = all(
        value is not None and np.isfinite(float(value)) and float(value) >= 0.0
        for value in values
    )
    if not finite:
        return (
            "FULL_SPECTRUM_SWEEP_UNSTABLE",
            "v8_adaptive_spectral_schwarz_required",
            {"conditional_128_finite": False, "r64_gate": initial},
        )
    replay_consistent = all(
        records[label].get("conditional_replay_r64_matches") is True
        for label in _SCREEN_LABELS
    )
    if not replay_consistent:
        return (
            "FULL_SPECTRUM_SWEEP_UNSTABLE",
            "v8_adaptive_spectral_schwarz_required",
            {
                "conditional_128_finite": True,
                "conditional_replay_r64_matches": False,
                "r64_gate": initial,
            },
        )
    r64 = [records[label]["residuals"]["64"] for label in _SCREEN_LABELS]
    drops = [
        math.log10(max(float(old), _SAFE) / max(float(new), _SAFE))
        for old, new in zip(r64, values, strict=True)
    ]
    positive = bool(
        all(float(value) <= 0.5 for value in values)
        or all(value >= 0.15 for value in drops)
    )
    no_signal = bool(
        all(float(value) > 0.8 for value in values)
        and all(value < 0.10 for value in drops)
    )
    detail = {
        "conditional_128_finite": True,
        "conditional_replay_r64_matches": replay_consistent,
        "drop_64_to_128_decade": drops,
        "positive": positive,
        "strict_negative": no_signal,
        "r64_gate": initial,
    }
    if positive:
        return (
            "V8_FULL_SPECTRUM_TWO_SOURCE_POSITIVE",
            "v8_five_source_required",
            detail,
        )
    if no_signal:
        return (
            "FULL_SPECTRUM_SWEEP_NO_SIGNAL",
            "v8_adaptive_spectral_schwarz_required",
            detail,
        )
    return (
        "FULL_SPECTRUM_SWEEP_NO_BOUNDED_POSITIVE_SIGNAL",
        "v8_adaptive_spectral_schwarz_required",
        detail,
    )


def run_v8_full_spectrum_two_source(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Run the dedicated V8 full-spectrum screen."""

    system, action = payload["system"], payload["schur_action"]
    comm = system.local_mesh.mesh.comm
    callback = payload.get("resource_callback")
    if not callable(callback):
        raise TypeError("V8 full-spectrum screen lacks resource callback")
    started = float(payload.get("formal_sequence_started", time.perf_counter()))
    resource_before = _json_safe(callback())
    identity = run_v7_full_spectrum_transform_identity(payload)
    if identity.get("pass") is not True:
        raise RuntimeError("V8 full-spectrum transform identity did not pass")
    configuration = payload.get("formal_exact_configuration")
    if not isinstance(configuration, Mapping):
        raise TypeError("V8 full-spectrum screen lacks exact configuration")
    masses: list[Any] = []
    transforms: list[Any] = []
    pc: _PairSpectralPC | None = None
    records: dict[str, dict[str, Any]] = {}
    material_audits: dict[str, Any] = {}
    conditional_used = False
    try:
        pairs = _pairs(system)
        sides = []
        for layout_key, support_key in (
            ("lower_gamma_layout", "lower"),
            ("upper_gamma_layout", "upper"),
        ):
            mass = assemble_reduced_artificial_interface_tangential_mass(
                system.V,
                system.static_condensation.condensed,
                payload["interface_supports"][support_key],
                bare_operator=payload["bare_operator"],
            )
            masses.append(mass)
            material_audits[support_key] = _material_audit(
                system, payload["interface_supports"][support_key], comm
            )
            transform = build_canonical_full_spectrum_trace_transform(
                system, payload[layout_key], comm
            )
            transforms.append(transform)
            _v8_mark(
                payload,
                f"v8_full_spectrum_{support_key}_transform_ready",
                started,
                callback,
                action,
                side=support_key,
                coverage=identity["coverage"],
            )
            sides.append((mass, transform))
        scales = (_mass_scale(sides[0][0].matrix, comm), _mass_scale(sides[1][0].matrix, comm))
        q, phases, symbol = _symbol(system, scales)
        _v8_mark(
            payload,
            "v8_full_spectrum_symbol_ready",
            started,
            callback,
            action,
            harmonic_count=_HARMONICS,
            symbol=symbol,
        )
        pc = _PairSpectralPC(
            action,
            sides[0][1],
            sides[1][1],
            payload["lower_gamma_layout"].gamma_rows_local,
            payload["upper_gamma_layout"].gamma_rows_local,
            pairs,
            scales,
            q,
            phases,
            system,
            comm,
        )
        for label in _SCREEN_LABELS:
            records[label] = _v8_run_source(
                payload, label, pc, started, callback
            )
        classification, next_stage, screen = _v8_classify(records)
        screen_detail: dict[str, Any] = {"two_source": screen}
        resource_after_64 = _json_safe(callback())
        if screen.get("r64_inconclusive") and _v8_conditional_allowed(
            records, resource_after_64
        ):
            conditional_used = True
            conditional_started = time.perf_counter()
            for label in _SCREEN_LABELS:
                conditional = _v8_run_source(
                    payload,
                    label,
                    pc,
                    started,
                    callback,
                    mandatory=(64, _V8_CONDITIONAL),
                    max_iterations=_V8_CONDITIONAL,
                    one_apply=False,
                    run_kind="conditional_replay",
                )
                conditional_values = _v8_replay_residuals(conditional)
                records[label]["conditional_replay_implementation_failure"] = bool(
                    conditional.get("implementation_failure")
                )
                records[label]["conditional_replay_r64"] = conditional_values["64"]
                records[label]["conditional_128"] = conditional_values["128"]
                original = records[label]["residuals"]["64"]
                replay = conditional_values["64"]
                records[label]["conditional_replay_r64_matches"] = bool(
                    original is not None
                    and replay is not None
                    and abs(float(original) - float(replay))
                    <= 1.0e-10 * max(1.0, abs(float(original)))
                )
                records[label][
                    "conditional_strategy"
                ] = "same_setup_zero_start_replay_to_128"
                records[label]["conditional_replay_elapsed_seconds"] = float(
                    conditional.get("fgmres_elapsed_seconds", 0.0)
                )
                records[label]["conditional_replay_pc_apply_count_delta"] = (
                    conditional.get("fgmres_pc_apply_count_delta")
                )
                records[label]["conditional_fgmres"] = conditional
            conditional_elapsed = time.perf_counter() - conditional_started
            classification, next_stage, screen = _v8_classify_conditional(
                records, screen
            )
            screen["conditional_authorization_resource"] = resource_after_64
            screen["conditional_authorization_formal_elapsed_seconds"] = (
                resource_after_64.get("formal_sequence_elapsed_seconds")
            )
            screen["conditional_replay_elapsed_seconds"] = float(
                conditional_elapsed
            )
            screen["conditional_authorized"] = True
            screen_detail["conditional"] = screen
        if next_stage == "v8_five_source_required":
            for label in _V8_HOLDOUT_LABELS:
                records[label] = _v8_run_source(
                    payload, label, pc, started, callback
                )
            classification, next_stage, screen = _v8_five_source_classify(records)
            screen_detail["five_source"] = screen
        screen_detail["final"] = screen
        return _json_safe(
            {
                "schema": _V8_SCHEMA,
                "status": "completed_v8_full_spectrum_screen",
                "classification": classification,
                "executed": True,
                "formal_adjudication": False,
                "pass": bool(
                    next_stage == "v8_factor_free_local_service_required"
                ),
                "next_required_stage": next_stage,
                "transform_identity": identity,
                "symbol": _json_safe(symbol),
                "material": _json_safe(material_audits),
                "sources": records,
                "screen": {
                    "source_order": list(records),
                    "planned_source_order": list(_V8_ALL_LABELS),
                    "initial_source_order": list(_SCREEN_LABELS),
                    "mandatory_checkpoints": list(_V8_CHECKPOINTS),
                    "conditional_checkpoints": (
                        [_V8_CONDITIONAL] if conditional_used else []
                    ),
                    "conditional_used": conditional_used,
                    "conditional_strategy": (
                        "same_setup_zero_start_replay_to_128"
                        if conditional_used
                        else None
                    ),
                    "conditional_changes_r64_gate": False,
                    **screen_detail,
                },
                "fixed_configuration": {
                    "restart": 32,
                    "zero_initial_guess": True,
                    "selected_operator": "D0_lower_memory",
                },
                "resource_limits": {
                    "minimum_mem_available_bytes": 96 * 2**30,
                    "preferred_process_tree_rss_bytes": 40 * 2**30,
                    "hard_process_tree_rss_bytes": 45 * 2**30,
                    "swap_bytes": 0,
                    "setup_target_seconds": 1800,
                    "transform_target_seconds": 900,
                    "one_apply_target_seconds": 1200,
                    "conditional_elapsed_limit_seconds": _V8_CONDITIONAL_ELAPSED_LIMIT,
                    "total_wall_seconds": _V8_TIMEOUT,
                },
                "selected_operator": payload.get("selected_operator"),
                "resource": {
                    "before": resource_before,
                    "after_64": resource_after_64,
                    "after": _json_safe(callback()),
                },
                "factor_lifecycle": {
                    "before": _json_safe(payload["factor_lifecycle"]),
                    "after_screen": _json_safe(
                        action.diagnostics.get("factor_lifecycle", {})
                    ),
                },
                "communication": _json_safe(pc.audit),
                "numeric_allgather": False,
                "full_interface_numeric_replica": False,
                "root_metadata_gather": True,
                "metadata_only_descriptor_gather": True,
                "rhs_vectors_loaded": len(records),
                "exact_output_vectors_loaded": 0,
                "qep_calls": 0,
                "full_side_exact_factor_count": 0,
                "global_direct_factor_count": 0,
            }
        )
    finally:
        if pc is not None:
            pc.close()
        for transform in reversed(transforms):
            transform.close()
        for mass in reversed(masses):
            mass.destroy()
