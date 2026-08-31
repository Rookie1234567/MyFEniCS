"""Owner-local canonical full-spectrum transforms for one Gamma plane."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np
from mpi4py import MPI

from .hybrid_interface_packet_dolfinx import GammaCanonicalLayout

__all__ = (
    "CanonicalFullSpectrumTraceTransform",
    "CanonicalModalArray",
    "build_canonical_full_spectrum_trace_transform",
)

_SAFE = 1.0e-300
_COUNTS = {"x_edge": 6, "y_edge": 6, "face": 60}
_OFFSETS = {"x_edge": 0, "y_edge": 6, "face": 12}


def _displacements(counts: np.ndarray) -> np.ndarray:
    result = np.zeros(len(counts), dtype=np.int32)
    if len(counts) > 1:
        result[1:] = np.cumsum(counts[:-1], dtype=np.int32)
    return result


def _points(value: Any) -> tuple[tuple[int, int, int], ...]:
    if isinstance(value, (Mapping, str, bytes)):
        raise TypeError("Gamma physical_entity must be a coordinate tuple")
    try:
        result = tuple(tuple(int(part) for part in point) for point in value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Gamma physical_entity is not coordinate geometry") from exc
    if not result or any(len(point) != 3 for point in result):
        raise ValueError("Gamma physical_entity must contain 3D points")
    return result


def _kind(points: tuple[tuple[int, int, int], ...], dimension: int) -> str:
    spans = np.ptp(np.asarray(points, dtype=np.float64)[:, :2], axis=0)
    if int(dimension) == 1 and spans[0] > 0.0 and spans[1] == 0.0:
        return "x_edge"
    if int(dimension) == 1 and spans[0] == 0.0 and spans[1] > 0.0:
        return "y_edge"
    if int(dimension) == 2 and np.all(spans > 0.0):
        return "face"
    raise ValueError("Gamma entity is not an x-edge, y-edge, or plane face")


def _basis(key: str) -> int:
    try:
        return int(json.loads(key)["entity_local_basis_index"])
    except (TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        raise ValueError("Gamma canonical key lacks a basis index") from exc


def _channel(kind: str, basis: int) -> int:
    if not 0 <= int(basis) < _COUNTS[kind]:
        raise ValueError(f"{kind} basis index is outside its channel range")
    return _OFFSETS[kind] + int(basis)


def _local_records(layout: GammaCanonicalLayout) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for placement in layout.blocks:
        block = placement.block
        points = _points(block.physical_entity)
        kind = _kind(points, block.entity_dimension)
        if len(placement.positions) != len(block.canonical_keys):
            raise ValueError("Gamma placement and block sizes differ")
        for position, key in zip(placement.positions, block.canonical_keys, strict=True):
            records.append(
                {
                    "position": int(position),
                    "kind": kind,
                    "basis": _basis(key),
                    "points": points,
                }
            )
    return records


def _wire(buckets: list[list[dict[str, Any]]], fields: tuple[str, ...]) -> tuple:
    return tuple(
        tuple(tuple(int(item[field]) for field in fields) for item in bucket)
        for bucket in buckets
    )


def _routes(
    gathered: list[list[dict[str, Any]]], nx: int, ny: int, size: int
) -> list[dict[str, Any]]:
    records = []
    for rank, local in enumerate(gathered):
        for item in local:
            record = dict(item)
            record["rank"] = int(rank)
            records.append(record)
    if not records:
        raise ValueError("Gamma canonical layout has no records")
    x_levels = sorted(
        {point[0] for item in records for point in item["points"]}
    )
    y_levels = sorted(
        {point[1] for item in records for point in item["points"]}
    )
    if len(x_levels) != nx + 1 or len(y_levels) != ny + 1:
        raise ValueError(
            "Gamma level inventory requires "
            f"{nx + 1} x-levels and {ny + 1} y-levels; "
            f"got {len(x_levels)} and {len(y_levels)}"
        )
    x_index = {value: index for index, value in enumerate(x_levels)}
    y_index = {value: index for index, value in enumerate(y_levels)}
    seen: set[tuple[int, int, int]] = set()
    for item in records:
        kind = str(item["kind"])
        point_indices = {
            (x_index[point[0]], y_index[point[1]])
            for point in item["points"]
        }
        x_positions = sorted({point[0] for point in point_indices})
        y_positions = sorted({point[1] for point in point_indices})
        adjacent = {
            "x_edge": (
                len(point_indices) == 2
                and len(x_positions) == 2
                and x_positions[1] == x_positions[0] + 1
                and len(y_positions) == 1
            ),
            "y_edge": (
                len(point_indices) == 2
                and len(x_positions) == 1
                and len(y_positions) == 2
                and y_positions[1] == y_positions[0] + 1
            ),
            "face": (
                len(point_indices) == 4
                and len(x_positions) == 2
                and x_positions[1] == x_positions[0] + 1
                and len(y_positions) == 2
                and y_positions[1] == y_positions[0] + 1
            ),
        }[kind]
        if not adjacent:
            raise ValueError(
                f"Gamma {kind} entity is non-adjacent or has the wrong level span"
            )
        ix, iy = x_positions[0], y_positions[0]
        channel = _channel(kind, int(item["basis"]))
        route = (channel, ix, iy)
        if route in seen:
            raise ValueError("Gamma channel/grid route is duplicated")
        seen.add(route)
        item.update({"channel": channel, "ix": ix, "iy": iy, "owner": channel % size})
    expected = {
        (channel, ix, iy)
        for channel in range(72)
        for ix in range(nx)
        for iy in range(ny)
    }
    if seen != expected:
        raise ValueError("Gamma coverage is not the complete 72-channel plane")
    forward = [[[] for _ in range(size)] for _ in range(size)]
    for item in records:
        forward[int(item["rank"])][int(item["owner"])].append(item)
    for row in forward:
        for bucket in row:
            bucket.sort(key=lambda item: (item["channel"], item["ix"], item["iy"]))
    payloads = []
    for rank in range(size):
        outbound = _wire(forward[rank], ("position", "channel", "ix", "iy"))
        inbound = _wire(
            [forward[source][rank] for source in range(size)],
            ("channel", "ix", "iy"),
        )
        reverse_outbound = _wire(
            [forward[destination][rank] for destination in range(size)],
            ("channel", "ix", "iy", "position"),
        )
        reverse_inbound = _wire(
            [forward[rank][source] for source in range(size)],
            ("position", "channel", "ix", "iy"),
        )
        payloads.append(
            {
                "outbound": outbound,
                "inbound": inbound,
                "reverse_outbound": reverse_outbound,
                "reverse_inbound": reverse_inbound,
                "channels": tuple(channel for channel in range(72) if channel % size == rank),
                "coverage": {
                    "channel_count": 72,
                    "grid": [nx, ny],
                    "global_plane_entries": 72 * nx * ny,
                    "modal_bound_entries": nx * ny * ((72 + size - 1) // size),
                },
            }
        )
    return payloads


@dataclass(frozen=True)
class CanonicalModalArray:
    """Caller-owned modal values held only by their channel owners."""

    values: np.ndarray
    channel_ids: tuple[int, ...]
    grid: tuple[int, int]
    dual: bool


class CanonicalFullSpectrumTraceTransform:
    """Canonicalize blocks, route channel grids, and apply a 2-D FFT."""

    def __init__(self, layout, comm, payload, nx, ny) -> None:
        self._layout, self._comm = layout, comm
        self._nx, self._ny = int(nx), int(ny)
        self._payload = payload
        self._channels = tuple(int(value) for value in payload["channels"])
        self._reverse_offsets = {channel: [] for channel in self._channels}
        offset = 0
        for bucket in payload["reverse_outbound"]:
            for channel, ix, iy, _position in bucket:
                self._reverse_offsets[int(channel)].append((offset, int(ix), int(iy)))
                offset += 1
        self._observations: dict[str, dict[str, Any]] = {}
        self._closed = False

    @classmethod
    def from_layout(cls, system, layout, comm=None):
        if not isinstance(layout, GammaCanonicalLayout):
            raise TypeError("full-spectrum transform requires GammaCanonicalLayout")
        if comm is None:
            comm = system.local_mesh.mesh.comm
        cells = tuple(int(value) for value in system.local_mesh.mesh_cells[:2])
        if cells != (15, 7):
            raise ValueError("full-spectrum trace requires mesh_cells=(15, 7)")
        gathered = comm.gather(_local_records(layout), root=0)
        payloads, error = None, None
        if comm.rank == 0:
            try:
                payloads = _routes(gathered, cells[0], cells[1], comm.size)
            except Exception as exc:  # noqa: BLE001
                error = str(exc)
        error = comm.bcast(error, root=0)
        if error is not None:
            raise ValueError(f"full-spectrum metadata failed: {error}")
        return cls(layout, comm, comm.scatter(payloads, root=0), *cells)

    def _live(self):
        if self._closed:
            raise RuntimeError("full-spectrum trace transform is closed")

    def _raw(self, values):
        self._live()
        result = np.asarray(values, dtype=np.complex128)
        if result.ndim != 1 or result.size != len(self._layout.gamma_rows_local):
            raise ValueError("owner-local raw coefficients have the wrong shape")
        if not np.isfinite(result).all():
            raise ValueError("owner-local raw coefficients are nonfinite")
        return result

    def _blocks(self, values, *, dual, inverse):
        result = np.empty_like(values)
        for placement in self._layout.blocks:
            block = placement.block
            if dual:
                matrix = block.raw_to_canonical.conj().T if inverse else block.canonical_to_raw.conj().T
            else:
                matrix = block.canonical_to_raw if inverse else block.raw_to_canonical
            result[placement.positions] = matrix @ values[placement.positions]
        return result

    def _alltoallv(self, send, outbound, inbound):
        send_counts = np.asarray([len(bucket) for bucket in outbound], dtype=np.int32)
        recv_counts = np.asarray([len(bucket) for bucket in inbound], dtype=np.int32)
        send_disp, recv_disp = _displacements(send_counts), _displacements(recv_counts)
        receive = np.empty(int(np.sum(recv_counts)), dtype=np.complex128)
        self._comm.Alltoallv(
            [send, send_counts, send_disp, MPI.C_DOUBLE_COMPLEX],
            [receive, recv_counts, recv_disp, MPI.C_DOUBLE_COMPLEX],
        )
        return receive, recv_disp

    def _record_route(self, name, send, receive, modal_entries):
        local = (int(send.size), int(receive.size), int(modal_entries))
        maximum = tuple(int(self._comm.allreduce(value, op=MPI.MAX)) for value in local)
        self._observations[name] = {
            "local_send_entries": local[0],
            "local_receive_entries": local[1],
            "local_modal_entries": local[2],
            "max_send_entries": maximum[0],
            "max_receive_entries": maximum[1],
            "max_modal_entries": maximum[2],
            "numeric_collective_count": 1,
            "numeric_collective_types": ["Alltoallv"],
        }

    def _forward(self, raw, *, dual):
        canonical = self._blocks(self._raw(raw), dual=dual, inverse=False)
        outbound, inbound = self._payload["outbound"], self._payload["inbound"]
        counts = np.asarray([len(bucket) for bucket in outbound], dtype=np.int32)
        disp = _displacements(counts)
        send = np.empty(int(np.sum(counts)), dtype=np.complex128)
        for destination, bucket in enumerate(outbound):
            for index, (position, _channel, _ix, _iy) in enumerate(bucket):
                send[int(disp[destination]) + index] = canonical[int(position)]
        receive, recv_disp = self._alltoallv(send, outbound, inbound)
        channels = {channel: index for index, channel in enumerate(self._channels)}
        values = np.zeros((len(self._channels), self._nx, self._ny), dtype=np.complex128)
        for source, bucket in enumerate(inbound):
            for index, (channel, ix, iy) in enumerate(bucket):
                values[channels[int(channel)], int(ix), int(iy)] = receive[int(recv_disp[source]) + index]
        for index in range(len(self._channels)):
            values[index] = np.fft.fft2(values[index], norm="ortho")
        self._record_route("forward", send, receive, values.size)
        return CanonicalModalArray(values, self._channels, (self._nx, self._ny), dual)

    def forward_primal(self, raw_owner_local):
        return self._forward(raw_owner_local, dual=False)

    def forward_dual(self, raw_covector_owner_local):
        return self._forward(raw_covector_owner_local, dual=True)

    def _inverse(self, modal, *, dual):
        self._live()
        if not isinstance(modal, CanonicalModalArray) or modal.dual is not dual:
            raise ValueError("modal array transform identity does not match")
        if modal.channel_ids != self._channels or modal.grid != (self._nx, self._ny):
            raise ValueError("modal ownership or grid does not match")
        values = np.asarray(modal.values, dtype=np.complex128)
        if values.shape != (len(self._channels), self._nx, self._ny) or not np.isfinite(values).all():
            raise ValueError("modal arrays have the wrong shape or are nonfinite")
        outbound, inbound = self._payload["reverse_outbound"], self._payload["reverse_inbound"]
        counts = np.asarray([len(bucket) for bucket in outbound], dtype=np.int32)
        send = np.empty(int(np.sum(counts)), dtype=np.complex128)
        positions = {channel: index for index, channel in enumerate(self._channels)}
        for channel in self._channels:
            grid = np.fft.ifft2(values[positions[channel]], norm="ortho")
            for offset, ix, iy in self._reverse_offsets[channel]:
                send[offset] = grid[ix, iy]
        receive, recv_disp = self._alltoallv(send, outbound, inbound)
        canonical = np.empty(len(self._layout.gamma_rows_local), dtype=np.complex128)
        for source, bucket in enumerate(inbound):
            for index, (position, _channel, _ix, _iy) in enumerate(bucket):
                canonical[int(position)] = receive[int(recv_disp[source]) + index]
        self._record_route("inverse", send, receive, values.size)
        return self._blocks(canonical, dual=dual, inverse=True)

    def inverse_primal(self, modal):
        return self._inverse(modal, dual=False)

    def inverse_dual(self, modal):
        return self._inverse(modal, dual=True)

    def identity_diagnostics(self, raw_primal, raw_dual_covector):
        raw, dual = self._raw(raw_primal), self._raw(raw_dual_covector)
        local_block = 0.0
        local_total_blocks = len(self._layout.blocks)
        local_identity_blocks = 0
        local_nontrivial_blocks = 0
        local_metadata_mismatches = 0
        local_master_nonnull = 0
        local_mismatch_reasons: dict[str, int] = {}
        for placement in self._layout.blocks:
            block = placement.block
            canonical = block.raw_to_canonical @ raw[placement.positions]
            local_block = max(local_block, float(np.max(np.abs(block.canonical_to_raw @ canonical - raw[placement.positions]), initial=0.0)))
            declared_phase = complex(block.floquet_coefficient)
            phase_finite = bool(np.isfinite([declared_phase.real, declared_phase.imag]).all())
            if not phase_finite:
                local_metadata_mismatches += 1
                local_mismatch_reasons["block_phase_nonfinite"] = local_mismatch_reasons.get("block_phase_nonfinite", 0) + 1
            elif abs(declared_phase - 1.0) <= 1.0e-12:
                local_identity_blocks += 1
            else:
                local_nontrivial_blocks += 1
            for key in block.canonical_keys:
                try:
                    record = json.loads(key)
                    pair = record["floquet_coefficient"]
                    if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                        raise ValueError("floquet_coefficient is not a pair")
                    key_phase = complex(float(pair[0]), float(pair[1]))
                    if not np.isfinite([key_phase.real, key_phase.imag]).all():
                        raise ValueError("floquet_coefficient is nonfinite")
                    if abs(key_phase - declared_phase) > 1.0e-12:
                        raise ValueError("key/block phase mismatch")
                    if "floquet_master" not in record:
                        raise ValueError("floquet_master is missing")
                    if record["floquet_master"] is not None:
                        local_master_nonnull += 1
                except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                    local_metadata_mismatches += 1
                    reason = str(exc)
                    local_mismatch_reasons[reason] = local_mismatch_reasons.get(reason, 0) + 1
        block_error = float(self._comm.allreduce(local_block, op=MPI.MAX))
        total_block_count = int(self._comm.allreduce(local_total_blocks, op=MPI.SUM))
        identity_block_count = int(self._comm.allreduce(local_identity_blocks, op=MPI.SUM))
        nontrivial_block_count = int(self._comm.allreduce(local_nontrivial_blocks, op=MPI.SUM))
        key_metadata_mismatches = int(self._comm.allreduce(local_metadata_mismatches, op=MPI.SUM))
        master_nonnull_count = int(self._comm.allreduce(local_master_nonnull, op=MPI.SUM))
        gathered_reasons = self._comm.allgather(local_mismatch_reasons)
        mismatch_reasons: dict[str, int] = {}
        for reasons in gathered_reasons:
            for reason, count in reasons.items():
                mismatch_reasons[reason] = mismatch_reasons.get(reason, 0) + int(count)
        plane_identity = self._layout.plane_identity
        phase_convention = (
            plane_identity.get("phase_convention")
            if isinstance(plane_identity, Mapping)
            else None
        )
        phase_convention_ok = bool(
            self._comm.allreduce(
                phase_convention == "stored_raw=phase*E*canonical", op=MPI.LAND
            )
        )
        if not phase_convention_ok:
            mismatch_reasons["plane_identity.phase_convention"] = 1
        metadata_mismatch_count = key_metadata_mismatches + int(not phase_convention_ok)
        all_master_null = master_nonnull_count == 0
        if total_block_count == 0:
            phase_mode = "invalid_empty_block_inventory"
        elif metadata_mismatch_count:
            phase_mode = "invalid_phase_metadata"
        elif (
            identity_block_count == total_block_count
            and nontrivial_block_count == 0
            and all_master_null
        ):
            phase_mode = "all_active_master_identity_phase"
        elif (
            nontrivial_block_count > 0
            and identity_block_count + nontrivial_block_count == total_block_count
        ):
            phase_mode = "nontrivial_block_phase"
        else:
            phase_mode = "invalid_phase_metadata"
        phase_blocks = nontrivial_block_count
        primal = self.forward_primal(raw)
        dual_modal = self.forward_dual(dual)
        primal_back, dual_back = self.inverse_primal(primal), self.inverse_dual(dual_modal)
        primal_error = float(self._comm.allreduce(float(np.max(np.abs(primal_back - raw), initial=0.0)), op=MPI.MAX))
        dual_error = float(self._comm.allreduce(float(np.max(np.abs(dual_back - dual), initial=0.0)), op=MPI.MAX))
        dft_error = 0.0
        for values in primal.values:
            physical = np.fft.ifft2(values, norm="ortho")
            dft_error = max(dft_error, float(np.max(np.abs(np.fft.fft2(physical, norm="ortho") - values), initial=0.0)))
        dft_error = float(self._comm.allreduce(dft_error, op=MPI.MAX))
        raw_pair = self._comm.allreduce(np.vdot(raw, dual), op=MPI.SUM)
        modal_pair = self._comm.allreduce(np.vdot(primal.values, dual_modal.values), op=MPI.SUM)
        pairing = abs(complex(raw_pair) - complex(modal_pair))
        observations = dict(self._observations)
        max_numeric_buffer_entries = max(
            (
                max(
                    item["max_send_entries"],
                    item["max_receive_entries"],
                    item["max_modal_entries"],
                )
                for item in observations.values()
            ),
            default=0,
        )
        numeric_allgather = any(
            "Allgather" in item["numeric_collective_types"]
            for item in observations.values()
        )
        fft_phase_applications = 0
        phase_once = bool(
            total_block_count > 0
            and metadata_mismatch_count == 0
            and phase_convention_ok
            and fft_phase_applications == 0
            and phase_mode
            in {"all_active_master_identity_phase", "nontrivial_block_phase"}
        )
        return {
            "schema": "task040.v7.full_spectrum_trace_transform.v1",
            "block_roundtrip_max": block_error,
            "primal_roundtrip_max": primal_error,
            "dual_roundtrip_max": dual_error,
            "dft_roundtrip_max": dft_error,
            "fft_norm": "ortho",
            "raw_pairing": [float(np.real(raw_pair)), float(np.imag(raw_pair))],
            "modal_pairing": [float(np.real(modal_pair)), float(np.imag(modal_pair))],
            "parseval_pairing_abs_error": float(pairing),
            "parseval_pairing_relative_error": float(pairing / max(abs(complex(raw_pair)), _SAFE)),
            "phase_once": phase_once,
            "phase_once_audit": {
                "total_block_count": total_block_count,
                "nontrivial_block_count": phase_blocks,
                "identity_block_count": identity_block_count,
                "metadata_mismatch_count": metadata_mismatch_count,
                "metadata_mismatch_reasons": mismatch_reasons,
                "phase_convention": phase_convention,
                "all_key_floquet_master_null": all_master_null,
                "mode": phase_mode,
                "block_transform_applications": "GammaEntityBlock matrices",
                "fft_phase_applications": fft_phase_applications,
            },
            "coverage": self._payload["coverage"],
            "harmonic_inventory": [[ix, iy] for ix in range(self._nx) for iy in range(self._ny)],
            "channel_inventory": [{"channel": channel, "owner": channel % self._comm.size} for channel in range(72)],
            "numeric_allgather": numeric_allgather,
            "max_numeric_buffer_entries": max_numeric_buffer_entries,
            "full_plane_numeric_replica": bool(
                self._comm.size > 1
                and max_numeric_buffer_entries >= self._payload["coverage"]["global_plane_entries"]
            ),
            "numeric_route": "bounded_channel_owner_alltoallv",
            "numeric_collectives": observations,
        }

    def close(self):
        if not self._closed:
            self._payload = {}
            self._reverse_offsets.clear()
            self._closed = True


def build_canonical_full_spectrum_trace_transform(
    system, layout, comm=None
) -> CanonicalFullSpectrumTraceTransform:
    return CanonicalFullSpectrumTraceTransform.from_layout(system, layout, comm)
