"""Owner-local bounded harmonic factors for the narrow S2c Gate."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc
from scipy.linalg import lu_factor, lu_solve

from .floquet_background_hcurl_block_transform import (
    ActiveTraceBlochLayout,
    ActiveTraceBlochTransforms,
)

__all__ = (
    "BoundedHarmonicFactorPacket",
    "BoundedHarmonicService",
    "build_bounded_harmonic_packet",
    "canonical_layout_hash",
    "create_bounded_harmonic_service",
)

_TINY = np.finfo(float).tiny
_BLOCK_TOL = 1.0e-10


@dataclass(frozen=True)
class BoundedHarmonicFactorPacket:
    """Background-only data that is safe to carry between runner callbacks."""

    layout_hash: str
    blocks: tuple[dict[str, Any], ...]
    setup_audit: dict[str, Any]
    additional_absorbing_shift: complex = 0.0j


class _BlockRoute:
    def __init__(self, parent: PETSc.Vec, indices: tuple[int, ...], owner: int) -> None:
        self.indices = np.asarray(indices, dtype=PETSc.IntType)
        self.owner = int(owner)
        local_indices = self.indices if parent.getComm().tompi4py().rank == self.owner else np.empty(0, dtype=PETSc.IntType)
        self.values = PETSc.Vec().createSeq(len(local_indices), comm=PETSc.COMM_SELF)
        source_is = PETSc.IS().createGeneral(local_indices, comm=PETSc.COMM_SELF)
        target_is = PETSc.IS().createStride(
            len(local_indices), first=0, step=1, comm=PETSc.COMM_SELF
        )
        try:
            self.scatter = PETSc.Scatter().create(parent, source_is, self.values, target_is)
        finally:
            target_is.destroy()
            source_is.destroy()

    def gather(self, source: PETSc.Vec) -> None:
        self.values.set(0.0)
        self.scatter.scatter(
            source,
            self.values,
            addv=PETSc.InsertMode.INSERT_VALUES,
            mode=PETSc.ScatterMode.FORWARD,
        )

    def inject(self, target: PETSc.Vec) -> None:
        self.scatter.scatter(
            self.values,
            target,
            addv=PETSc.InsertMode.ADD_VALUES,
            mode=PETSc.ScatterMode.REVERSE,
        )

    def destroy(self) -> None:
        self.scatter.destroy()
        self.values.destroy()


def _jsonable(value: Any) -> Any:
    if isinstance(value, complex):
        return [float(value.real), float(value.imag)]
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return float(value)
    return value


def _layout_metadata(layout: ActiveTraceBlochLayout) -> dict[str, Any]:
    return {
        "active_rows": layout.active_rows,
        "auxiliary_rows": layout.auxiliary_rows,
        "augmented_rows": layout.augmented_rows,
        "nx": layout.nx,
        "ny": layout.ny,
        "nz": layout.nz,
        "rows_per_harmonic": layout.rows_per_harmonic,
        "axis_values": layout.axis_values,
        "phase_x": layout.phase_x,
        "phase_y": layout.phase_y,
        "k_b": layout.k_b,
        "lengths": layout.lengths,
        "blocks": [
            {
                "key": block.key,
                "orbit": block.orbit,
                "base": block.base,
                "active_ids": block.active_ids,
            }
            for block in sorted(layout.blocks, key=lambda item: repr(item.key))
        ],
    }


def canonical_layout_hash(layout: ActiveTraceBlochLayout) -> str:
    payload = json.dumps(
        _jsonable(_layout_metadata(layout)),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _block_indices(layout: ActiveTraceBlochLayout) -> tuple[tuple[int, ...], ...]:
    if layout.auxiliary_rows != 4:
        raise RuntimeError("S2c requires four auxiliary rows")
    blocks = []
    for mode in range(layout.nx * layout.ny):
        first = mode * layout.rows_per_harmonic
        indices = list(range(first, first + layout.rows_per_harmonic))
        if mode == 0:
            indices.extend(range(layout.active_rows, layout.augmented_rows))
        blocks.append(tuple(indices))
    flat = [index for block in blocks for index in block]
    if sorted(flat) != list(range(layout.augmented_rows)):
        raise RuntimeError("S2c modal blocks do not cover each augmented row once")
    if tuple(map(len, blocks)) != (84, 80, 80, 80, 80, 80):
        raise RuntimeError("S2c modal block cardinality is not (84,80,80,80,80,80)")
    return tuple(blocks)


def _finite(values: np.ndarray) -> bool:
    return bool(np.all(np.isfinite(np.asarray(values))))


def _factor_gate(matrix: np.ndarray, lu, pivots) -> dict[str, float]:
    size = matrix.shape[0]
    rhs = np.asarray(
        [np.sin(0.013 * (index + 1)) + 1j * np.cos(0.017 * (index + 2)) for index in range(size)],
        dtype=np.complex128,
    )
    first = np.asarray(lu_solve((lu, pivots), rhs, check_finite=True), dtype=np.complex128)
    repeated = np.asarray(lu_solve((lu, pivots), rhs, check_finite=True), dtype=np.complex128)
    second_rhs = np.asarray(
        [np.cos(0.019 * (index + 1)) - 1j * np.sin(0.023 * (index + 2)) for index in range(size)],
        dtype=np.complex128,
    )
    left = np.asarray(
        lu_solve((lu, pivots), 0.7 * rhs - (0.2 - 0.4j) * second_rhs, check_finite=True),
        dtype=np.complex128,
    )
    right = 0.7 * first - (0.2 - 0.4j) * np.asarray(
        lu_solve((lu, pivots), second_rhs, check_finite=True), dtype=np.complex128
    )
    if not all(_finite(values) for values in (first, repeated, left, right)):
        raise RuntimeError("S2c factor solve produced a nonfinite value")
    residual_norm = float(np.linalg.norm(matrix @ first - rhs))
    solve_relative = residual_norm / max(float(np.linalg.norm(rhs)), _TINY)
    normwise = residual_norm / max(
        float(np.linalg.norm(matrix, ord=2)) * float(np.linalg.norm(first))
        + float(np.linalg.norm(rhs)),
        _TINY,
    )
    repeat = float(np.linalg.norm(repeated - first)) / max(float(np.linalg.norm(first)), _TINY)
    linearity = float(np.linalg.norm(left - right)) / max(float(np.linalg.norm(left)), _TINY)
    values = {
        "solve_relative_residual": solve_relative,
        "normwise_backward_error": normwise,
        "repeat_error": repeat,
        "linearity_error": linearity,
    }
    if any(value > _BLOCK_TOL for value in values.values()):
        raise RuntimeError(f"S2c factor identity Gate failed: {values}")
    return values


def _new_routes(parent: PETSc.Vec, blocks: tuple[tuple[int, ...], ...]) -> tuple[_BlockRoute, ...]:
    size = int(parent.getComm().tompi4py().size)
    return tuple(_BlockRoute(parent, indices, mode % size) for mode, indices in enumerate(blocks))


def build_bounded_harmonic_packet(
    request,
    transforms: ActiveTraceBlochTransforms,
) -> BoundedHarmonicFactorPacket:
    """Extract and factor six background blocks without retaining PETSc objects."""

    layout = transforms.layout
    comm = layout.comm
    blocks = _block_indices(layout)
    modes = len(blocks)
    local_factors: list[dict[str, Any]] = []
    off_block_max: list[float] = []
    column_apply_count = 0
    started = time.perf_counter()
    modal = transforms.q.createVecRight()
    physical = transforms.q.createVecLeft()
    applied = request.A.createVecLeft()
    transformed = transforms.t.createVecLeft()
    routes = _new_routes(transformed, blocks)
    try:
        if physical.getOwnershipRange() != request.A.getOwnershipRange():
            raise RuntimeError("S2c background Q and A ownership differ")
        if transformed.getOwnershipRange() != modal.getOwnershipRange():
            raise RuntimeError("S2c background Q/T modal ownership differs")
        start, stop = map(int, transformed.getOwnershipRange())
        local_ids = np.arange(start, stop, dtype=np.int64)
        for mode, indices in enumerate(blocks):
            matrix = np.empty((len(indices), len(indices)), dtype=np.complex128) if comm.rank == mode % comm.size else None
            route = routes[mode]
            off_max = 0.0
            selected = set(indices)
            for column_position, column in enumerate(indices):
                modal.set(0.0)
                modal_start, modal_stop = map(int, modal.getOwnershipRange())
                if modal_start <= column < modal_stop:
                    modal.getArray()[column - modal_start] = PETSc.ScalarType(1.0)
                transforms.q.mult(modal, physical)
                request.A.mult(physical, applied)
                column_apply_count += 1
                transforms.t.mult(applied, transformed)
                values = np.asarray(transformed.getArray(readonly=True), dtype=np.complex128)
                if not _finite(values):
                    raise RuntimeError("S2c background column action is nonfinite")
                off_values = values[[index not in selected for index in local_ids]]
                off_sq = float(np.vdot(off_values, off_values).real)
                off_norm = float(np.sqrt(comm.allreduce(off_sq, op=MPI.SUM)))
                route.gather(transformed)
                local_block_values = np.asarray(
                    route.values.getArray(readonly=True), dtype=np.complex128
                )
                if not _finite(local_block_values):
                    raise RuntimeError("S2c background block column is nonfinite")
                block_sq = float(np.vdot(local_block_values, local_block_values).real)
                block_norm = float(np.sqrt(comm.allreduce(block_sq, op=MPI.SUM)))
                off_max = max(off_max, off_norm / max(block_norm, _TINY))
                if matrix is not None:
                    matrix[:, column_position] = local_block_values
            off_block_max.append(float(comm.allreduce(off_max, op=MPI.MAX)))
            if off_block_max[-1] > _BLOCK_TOL:
                raise RuntimeError(
                    f"S2c background mode {mode} has off-block leakage {off_block_max[-1]}"
                )
            local_factor = {"mode": mode, "indices": indices, "owner": mode % comm.size}
            if matrix is not None:
                if not _finite(matrix):
                    raise RuntimeError("S2c background dense block is nonfinite")
                lu, pivots = lu_factor(matrix, check_finite=True)
                factor_audit = _factor_gate(matrix, lu, pivots)
                local_factor.update(
                    {
                        "lu": np.asarray(lu, dtype=np.complex128).copy(),
                        "pivots": np.asarray(pivots, dtype=np.int32).copy(),
                        "factor_audit": factor_audit,
                    }
                )
            else:
                local_factor.update(
                    {
                        "lu": None,
                        "pivots": None,
                        "factor_audit": None,
                    }
                )
            local_factors.append(local_factor)
        factor_errors = [
            item["factor_audit"]
            for item in local_factors
            if item["factor_audit"] is not None
        ]
        audit = {
            "background_column_apply_count": column_apply_count,
            "background_mode_count": modes,
            "block_rows": list(map(len, blocks)),
            "block_owners": [mode % comm.size for mode in range(modes)],
            "off_block_max": off_block_max,
            "factor_solve_audit": factor_errors,
            "factor_count_local": len(factor_errors),
            "factor_count_global": int(comm.allreduce(len(factor_errors), op=MPI.SUM)),
            "factor_lifecycle": "dense blocks released after LU setup",
            "background_petcs_released": True,
            "setup_wall_seconds": time.perf_counter() - started,
            "additional_absorbing_shift": 0.0,
        }
        if audit["background_column_apply_count"] != 484:
            raise RuntimeError("S2c background did not perform exactly 484 column actions")
        if audit["factor_count_global"] != modes:
            raise RuntimeError("S2c did not create exactly six owner-local factors")
        return BoundedHarmonicFactorPacket(
            layout_hash=canonical_layout_hash(layout),
            blocks=tuple(local_factors),
            setup_audit=audit,
        )
    finally:
        for route in routes:
            route.destroy()
        transformed.destroy()
        applied.destroy()
        physical.destroy()
        modal.destroy()


class BoundedHarmonicService:
    """Target-side Q/T service backed by owner-local bounded LU factors."""

    def __init__(
        self,
        packet: BoundedHarmonicFactorPacket,
        transforms: ActiveTraceBlochTransforms,
    ) -> None:
        if packet.layout_hash != canonical_layout_hash(transforms.layout):
            raise RuntimeError("S2c background and target layout hashes differ")
        self.packet = packet
        self.transforms = transforms
        self.layout = transforms.layout
        self._destroyed = False
        self.apply_count = 0
        self.solve_count = 0
        self._modal_input = transforms.t.createVecLeft()
        self._modal_output = self._modal_input.duplicate()
        self._routes = _new_routes(self._modal_input, _block_indices(self.layout))
        expected_ownership = tuple(map(int, self.layout.ownership))
        if self._modal_input.getOwnershipRange() != expected_ownership:
            self.destroy()
            raise RuntimeError("S2c target physical/modal ownership differs")

    @property
    def destroyed(self) -> bool:
        return self._destroyed

    def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        if self._destroyed:
            raise RuntimeError("S2c harmonic service has been destroyed")
        expected = tuple(map(int, self.layout.ownership))
        if (
            source.getSize() != self.layout.augmented_rows
            or target.getSize() != source.getSize()
            or source.getOwnershipRange() != expected
            or target.getOwnershipRange() != expected
        ):
            raise RuntimeError("S2c harmonic service Vec size mismatch")
        self.transforms.t.mult(source, self._modal_input)
        self._modal_output.set(0.0)
        for route, factor in zip(self._routes, self.packet.blocks, strict=True):
            route.gather(self._modal_input)
            if factor["lu"] is not None:
                values = np.asarray(route.values.getArray(readonly=True), dtype=np.complex128).copy()
                solved = np.asarray(
                    lu_solve((factor["lu"], factor["pivots"]), values, check_finite=True),
                    dtype=np.complex128,
                )
                if not _finite(solved):
                    raise RuntimeError("S2c target factor solve is nonfinite")
                route.values.getArray()[:] = solved
                self.solve_count += 1
            route.inject(self._modal_output)
        self.transforms.q.mult(self._modal_output, target)
        self.apply_count += 1

    def destroy(self) -> None:
        if self._destroyed:
            return
        for route in self._routes:
            route.destroy()
        self._modal_output.destroy()
        self._modal_input.destroy()
        self._destroyed = True


def create_bounded_harmonic_service(
    packet: BoundedHarmonicFactorPacket,
    transforms: ActiveTraceBlochTransforms,
) -> BoundedHarmonicService:
    """Create target-owned routes/work vectors from a background-only packet."""

    expected = _block_indices(transforms.layout)
    if tuple(tuple(item["indices"]) for item in packet.blocks) != expected:
        raise RuntimeError("S2c packet block indices differ from target layout")
    return BoundedHarmonicService(packet, transforms)
