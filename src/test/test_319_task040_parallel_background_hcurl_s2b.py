"""Task040 S2b: active-trace Bloch block-transform Gate."""

from __future__ import annotations

import json
import math
from dataclasses import replace

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

from src.common.config_3d import (
    ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND,
    STANDARD_FULL_ASSEMBLY_BACKEND,
    target_stage4_config,
)
from src.solvers.floquet_background_hcurl_block_transform import (
    _orientation,
    build_active_trace_bloch_layout,
    create_active_trace_bloch_transforms,
)
from src.solvers.solve_maxwell_3d_stage_4b_block_grating import (
    run_stage4b_block_grating_3d_case,
)

_TINY = np.finfo(float).tiny


class _S2bAuditStop(RuntimeError):
    def __init__(self, evidence):
        super().__init__("S2b audit completed before the ordinary solver path")
        self.evidence = evidence


def _relative(actual, expected):
    difference = actual.duplicate()
    actual.copy(difference)
    difference.axpy(PETSc.ScalarType(-1.0), expected)
    value = float(difference.norm()) / max(float(expected.norm()), _TINY)
    difference.destroy()
    return value


def _fill(vec, *, mode_start=None, mode_stop=None):
    first, last = map(int, vec.getOwnershipRange())
    values = vec.getArray()
    values[:] = 0.0
    for local, global_id in enumerate(range(first, last)):
        if mode_start is None or mode_start <= global_id < mode_stop:
            values[local] = np.sin(0.017 * (global_id + 1.0)) + 1j * np.cos(
                0.011 * (global_id + 2.0)
            )


def _pair_gate(transforms, ownership):
    q, t = transforms.q, transforms.t
    modal = q.createVecRight()
    physical = q.createVecLeft()
    restored = t.createVecLeft()
    physical_repeat = q.createVecLeft()
    physical_input = t.createVecRight()
    modal_repeat = t.createVecLeft()
    vectors = [modal, physical, restored, physical_repeat, physical_input, modal_repeat]
    try:
        assert all(vector.getOwnershipRange() == ownership for vector in vectors)
        _fill(modal)
        q.mult(modal, physical)
        t.mult(physical, restored)
        t.mult(physical, modal_repeat)
        q.mult(modal, physical_repeat)
        tq_error = _relative(restored, modal)
        q_repeat_error = _relative(physical_repeat, physical)
        t_repeat_error = _relative(modal_repeat, restored)
        _fill(physical_input)
        modal_input = t.createVecLeft()
        physical_again = q.createVecLeft()
        vectors.extend((modal_input, physical_again))
        t.mult(physical_input, modal_input)
        q.mult(modal_input, physical_again)
        qt_error = _relative(physical_again, physical_input)
        left = q.createVecRight()
        right = q.createVecRight()
        combo = q.createVecRight()
        left_image = q.createVecLeft()
        right_image = q.createVecLeft()
        combo_image = q.createVecLeft()
        expected_image = q.createVecLeft()
        vectors.extend((left, right, combo, left_image, right_image, combo_image, expected_image))
        _fill(left, mode_start=0, mode_stop=80)
        _fill(right, mode_start=80, mode_stop=160)
        left.copy(combo)
        combo.scale(PETSc.ScalarType(0.7 - 0.1j))
        combo.axpy(PETSc.ScalarType(-0.2 + 0.4j), right)
        q.mult(left, left_image)
        q.mult(right, right_image)
        q.mult(combo, combo_image)
        left_image.copy(expected_image)
        expected_image.scale(PETSc.ScalarType(0.7 - 0.1j))
        expected_image.axpy(PETSc.ScalarType(-0.2 + 0.4j), right_image)
        q_linearity_error = _relative(combo_image, expected_image)
        assert tq_error <= 1.0e-12
        assert qt_error <= 1.0e-12
        assert q_repeat_error <= 1.0e-12
        assert t_repeat_error <= 1.0e-12
        assert q_linearity_error <= 1.0e-12
        return {
            "TQ_error": tq_error,
            "QT_error": qt_error,
            "Q_repeat_error": q_repeat_error,
            "T_repeat_error": t_repeat_error,
            "Q_linearity_error": q_linearity_error,
        }
    finally:
        for vector in vectors:
            vector.destroy()


def _leakage_gate(request, transforms, layout):
    q, t = transforms.q, transforms.t
    leakages = []
    for mode_index in range(layout.nx * layout.ny):
        start = mode_index * layout.rows_per_harmonic
        stop = start + layout.rows_per_harmonic
        modal = q.createVecRight()
        physical = q.createVecLeft()
        applied = request.A.createVecLeft()
        back = t.createVecLeft()
        off = back.duplicate()
        try:
            _fill(modal, mode_start=start, mode_stop=stop)
            if mode_index == 0:
                first, last = map(int, modal.getOwnershipRange())
                values = modal.getArray()
                for local, global_id in enumerate(range(first, last)):
                    if layout.active_rows <= global_id < layout.augmented_rows:
                        values[local] = 0.25 + 0.1j * (global_id - layout.active_rows + 1)
            q.mult(modal, physical)
            request.A.mult(physical, applied)
            t.mult(applied, back)
            back.copy(off)
            first, last = map(int, off.getOwnershipRange())
            values = off.getArray()
            for local, global_id in enumerate(range(first, last)):
                in_block = start <= global_id < stop
                in_envelope_aux = mode_index == 0 and global_id >= layout.active_rows
                if in_block or in_envelope_aux:
                    values[local] = 0.0
            denominator = max(float(back.norm()), _TINY)
            leakage = float(off.norm()) / denominator
            assert math.isfinite(leakage)
            assert leakage <= 1.0e-10
            leakages.append(leakage)
        finally:
            for vector in (modal, physical, applied, back, off):
                vector.destroy()
    return leakages


@pytest.mark.skipif(MPI.COMM_WORLD.size not in (1, 2), reason="serial/MPI2 only")
def test_task040_s2b_actual_active_trace_bloch_block_transform(tmp_path):
    comm = MPI.COMM_WORLD
    ordinary = target_stage4_config(degree=2, h_nm=100.0)
    assert ordinary.stage4_full3d_assembly_backend == STANDARD_FULL_ASSEMBLY_BACKEND
    cfg = replace(
        ordinary,
        case_name="task040_v9_e_s2b_active_trace_p2_h100",
        matrix_diagnostics_assemble_only=False,
        matrix_diagnostics_factorization_only=False,
        stage4_full3d_assembly_backend=ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND,
        stage4_dtn_order_policy="zero_order",
        n_grating=ordinary.n_air,
        grating_width_x=ordinary.period_x,
        grating_width_y=ordinary.period_y,
        grating_height=ordinary.grating_height,
        mesh_axis_cell_counts=(3, 2, 4),
        mesh_spacing_mode="auto",
        unique_output=False,
    )
    assert cfg.n_grating == cfg.n_air
    assert cfg.grating_width_x == ordinary.period_x
    assert cfg.grating_width_y == ordinary.period_y
    assert cfg.grating_height == ordinary.grating_height > 0.0
    evidence = {}

    def audit_port(request):
        transforms = None
        try:
            layout = build_active_trace_bloch_layout(request)
            axes = layout.axis_values
            assert tuple(map(len, axes)) == (4, 3, 5)
            assert np.allclose(np.diff(axes[0]), np.diff(axes[0])[0], rtol=0.0, atol=1.0e-12)
            assert np.allclose(np.diff(axes[1]), np.diff(axes[1])[0], rtol=0.0, atol=1.0e-12)
            assert layout.nx * layout.ny == 6
            assert layout.rows_per_harmonic == 80
            assert layout.active_rows == 480
            assert layout.auxiliary_rows == 4
            transforms = create_active_trace_bloch_transforms(layout)
            ownership = tuple(map(int, request.A.getOwnershipRange()))
            pair = _pair_gate(transforms, ownership)
            leakages = _leakage_gate(request, transforms, layout)
            orientation_error = max(
                float(
                    np.linalg.norm(
                        np.linalg.solve(_orientation(block), np.eye(len(block.active_ids)))
                        @ _orientation(block)
                        - np.eye(len(block.active_ids))
                    )
                )
                for block in layout.blocks
            )
            phase_errors = (
                abs(np.exp(1j * layout.k_b[0] * layout.lengths[0]) - layout.phase_x),
                abs(np.exp(1j * layout.k_b[1] * layout.lengths[1]) - layout.phase_y),
            )
            orbit_rows = {
                str(orbit): sum(
                    len(block.active_ids)
                    for (candidate_orbit, _base), block in layout.block_by_orbit_base.items()
                    if candidate_orbit == orbit
                )
                for orbit in sorted({block.orbit for block in layout.blocks})
            }
            evidence.update(
                {
                    "axes": axes,
                    "cells": layout.nx * layout.ny * layout.nz,
                    "orbits": orbit_rows,
                    "active_rows": layout.active_rows,
                    "auxiliary_rows": layout.auxiliary_rows,
                    "augmented_rows": layout.augmented_rows,
                    "ownership": list(ownership),
                    "phase_errors": phase_errors,
                    "orientation_inverse_error": orientation_error,
                    "pair": pair,
                    "leakages": leakages,
                    "q_nnz": transforms.q.getInfo().get("nz_used"),
                    "t_nnz": transforms.t.getInfo().get("nz_used"),
                }
            )
        finally:
            if transforms is not None:
                transforms.destroy()
            evidence["lifecycle"] = {
                "borrowed_A_not_destroyed": True,
                "Q_destroyed": transforms is None or transforms._destroyed,
                "T_destroyed": transforms is None or transforms._destroyed,
                "ksp_created": False,
                "factor_created": False,
            }
        raise _S2bAuditStop(evidence)

    with pytest.raises(_S2bAuditStop) as caught:
        run_stage4b_block_grating_3d_case(
            cfg,
            tmp_path / "s2b",
            linear_solver_port=audit_port,
        )
    rank_evidence = comm.allgather(caught.value.evidence)
    assert all(item["active_rows"] == 480 for item in rank_evidence)
    assert all(item["auxiliary_rows"] == 4 for item in rank_evidence)
    if comm.rank == 0:
        print(
            "S2B_ACTUAL_ACTIVE_TRACE_BLOCH_BLOCK_PASS "
            + json.dumps(rank_evidence, default=str, sort_keys=True)
        )
